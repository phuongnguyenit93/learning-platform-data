# DELETE và DETACH DELETE cùng tác động đến quan hệ

Trong Neo4j, dữ liệu được lưu dưới dạng **property graph**: node biểu diễn thực thể, relationship biểu diễn liên kết giữa hai node, và cả node lẫn relationship đều có thể mang thuộc tính. Vì relationship nối trực tiếp hai node, việc xóa một node luôn đặt ra câu hỏi: **những relationship gắn với node đó sẽ ra sao?**

Cypher cung cấp hai cách xóa thường gặp:

- **DELETE** xóa trực tiếp node hoặc relationship được chỉ định. Nếu muốn xóa một node, node đó phải **không còn relationship nào**; nếu vẫn còn, Neo4j từ chối thao tác.
- **DETACH DELETE** xóa node được chỉ định **cùng toàn bộ relationship nối trực tiếp với node đó**, bất kể hướng hoặc loại relationship.

Điểm cốt lõi: **cả hai lệnh đều có thể tác động đến relationship**, nhưng phạm vi và điều kiện xóa khác nhau. DELETE cho phép chọn relationship để xóa riêng; DETACH DELETE cho phép xóa node có liên kết bằng cách tự xóa các relationship kề node.

## 1. Quan hệ là dữ liệu có vòng đời riêng

Xét đồ thị:

~~~text
(An) --[:FOLLOWS]--> (Bình)
(An) --[:AUTHORED]--> (Bài viết)
(Bình) --[:LIKES]--> (Bài viết)
~~~

Ba relationship trên là ba bản ghi quan hệ riêng biệt trong graph. Chúng không chỉ là các trường chứa ID nằm bên trong node. Một relationship có thể có thuộc tính, ví dụ:

~~~cypher
(an)-[:FOLLOWS {since: 2024, source: 'community'}]->(binh)
~~~

Một relationship trong Neo4j phải có hai đầu mút tồn tại. Vì vậy, Neo4j không cho phép xóa node An trong khi vẫn để lại relationship **FOLLOWS** hoặc **AUTHORED** trỏ tới một node không còn tồn tại.

Hãy phân biệt ba hành động:

1. Xóa **relationship FOLLOWS**: An và Bình vẫn tồn tại; liên kết theo dõi biến mất.
2. Xóa **node An bằng DELETE**: chỉ thực hiện được khi An không còn relationship.
3. Xóa **node An bằng DETACH DELETE**: An, FOLLOWS và AUTHORED biến mất; Bình, Bài viết và LIKES giữa chúng vẫn tồn tại.

DETACH DELETE chỉ xử lý **các relationship nối trực tiếp tới node bị xóa**. Nó không tự động xóa các node hàng xóm, các relationship khác của hàng xóm hoặc cả chuỗi đường đi có liên quan gián tiếp.

## 2. DELETE: xóa chính xác đối tượng được chỉ định

### 2.1. Xóa một relationship, giữ nguyên các node

~~~cypher
MATCH (a:Person {personId: 'an'})-[r:FOLLOWS]->(b:Person {personId: 'binh'})
DELETE r;
~~~

Trong ví dụ này, **r** là relationship được MATCH tìm thấy; DELETE r xóa relationship đó. Cả **a** và **b** vẫn còn, bao gồm nhãn, thuộc tính và các relationship khác của chúng.

Nếu mẫu MATCH khớp nhiều relationship FOLLOWS giữa các node được chỉ định, các relationship khớp đều có thể bị xóa. Vì vậy, phải kiểm tra điều kiện MATCH khi chỉ muốn xóa một liên kết cụ thể. Các thuộc tính của relationship, chẳng hạn **since**, có thể được dùng để lọc thêm nếu cần.

### 2.2. Xóa một node không có relationship

~~~cypher
MATCH (p:Person {personId: 'khong-lien-ket'})
DELETE p;
~~~

Lệnh hợp lệ nếu node **p** không có relationship ở thời điểm xóa. Node và các thuộc tính của nó biến mất. Neo4j cũng cập nhật các cấu trúc chỉ mục liên quan tới node theo cơ chế của cơ sở dữ liệu.

### 2.3. Xóa một node đang có relationship: lỗi

~~~cypher
MATCH (p:Person {personId: 'an'})
DELETE p;
~~~

Nếu An còn FOLLOWS, AUTHORED hoặc bất kỳ relationship nào khác (kể cả relationship đi vào node), Neo4j báo lỗi vì node vẫn còn liên kết. Không có cơ chế mặc định nào âm thầm xóa các relationship chỉ vì câu lệnh dùng DELETE p.

Điều kiện này áp dụng cho cả relationship **đi ra**, **đi vào** và **tự nối** từ node tới chính nó. Xóa một vài relationship nhưng còn sót một relationship cũng chưa đủ để DELETE node thành công.

## 3. DETACH DELETE: xóa node và tất cả relationship kề node

~~~cypher
MATCH (p:Person {personId: 'an'})
DETACH DELETE p;
~~~

Giả sử đồ thị vẫn có ba relationship ban đầu, lệnh trên gây ra kết quả:

~~~text
Trước:
(An) --[:FOLLOWS]--> (Bình)
(An) --[:AUTHORED]--> (Bài viết)
(Bình) --[:LIKES]--> (Bài viết)

Sau DETACH DELETE An:
(Bình) --[:LIKES]--> (Bài viết)
~~~

Những gì bị xóa là **node An**, **FOLLOWS** và **AUTHORED**. Những gì còn lại là **node Bình**, **node Bài viết** và **LIKES**. Nếu một relationship đi từ Bình **vào** An hoặc An có relationship tự nối, nó cũng bị xóa vì vẫn kề An.

Cú pháp này không cần nêu trước tên, loại hay hướng của relationship. Chính sự tiện lợi đó cũng là lý do cần thận trọng: một node có nhiều kết nối có thể khiến DETACH DELETE xóa một lượng lớn dữ liệu quan hệ.

## 4. Bảng so sánh hành vi

| Tình huống | DELETE | DETACH DELETE |
|---|---|---|
| Xóa node không có relationship | Xóa node thành công | Xóa node thành công |
| Xóa node còn relationship | Báo lỗi, không xóa được node | Xóa node và các relationship kề node |
| Relationship đi vào node | Ngăn DELETE node | Bị xóa cùng node |
| Relationship đi ra khỏi node | Ngăn DELETE node | Bị xóa cùng node |
| Relationship tự nối node | Ngăn DELETE node | Bị xóa cùng node |
| Node láng giềng | Không bị xóa nếu chỉ DELETE relationship | Không bị xóa khi DETACH DELETE node đích |
| Relationship giữa các node láng giềng | Không bị ảnh hưởng nếu không chọn xóa | Không bị ảnh hưởng nếu không kề node đích |
| Mục đích điển hình | Xóa một liên kết cụ thể hoặc node đã tách hết liên kết | Xóa một thực thể cùng toàn bộ liên kết trực tiếp của thực thể |

**Lưu ý:** Cột DELETE với node còn relationship nói về **DELETE node**. Nếu biến đại diện cho relationship, như DELETE r, thì lệnh vẫn có thể xóa relationship đó một cách trực tiếp mà không xóa hai node đầu mút.

## 5. Thực hành với một đồ thị nhỏ

Các truy vấn dưới đây nên chạy trong **database thử nghiệm**. Nhãn **DeleteLabPerson** và **DeleteLabArticle** được đặt riêng để không trộn ví dụ với dữ liệu nghiệp vụ. Thực hiện tuần tự các bước để thấy sự khác biệt.

### Bước 1. Tạo dữ liệu minh họa

~~~cypher
CREATE
  (an:DeleteLabPerson {personId: 'an', name: 'An'}),
  (binh:DeleteLabPerson {personId: 'binh', name: 'Bình'}),
  (bai:DeleteLabArticle {articleId: 'bai-1', title: 'Cypher cơ bản'})
CREATE
  (an)-[:FOLLOWS {since: 2024}]->(binh),
  (an)-[:AUTHORED]->(bai),
  (binh)-[:LIKES]->(bai);
~~~

Dữ liệu vừa tạo có ba node và ba relationship. Để xem các kết nối:

~~~cypher
MATCH (n)-[r]->(m)
WHERE n:DeleteLabPerson OR n:DeleteLabArticle
RETURN labels(n) AS nhanNguon,
       coalesce(n.personId, n.articleId) AS idNguon,
       type(r) AS quanHe,
       coalesce(m.personId, m.articleId) AS idDich;
~~~

Chạy bước tạo dữ liệu một lần trong database thử nghiệm trống hoặc dọn dữ liệu ví dụ cũ trước khi tạo lại, tránh trùng node do CREATE luôn tạo bản ghi mới.

### Bước 2. Thử DELETE node đang liên kết

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
DELETE an;
~~~

**Kết quả dự kiến:** câu lệnh báo lỗi vì An đang tham gia FOLLOWS và AUTHORED. Các node và relationship của đồ thị vẫn còn; không thể coi thao tác xóa này là thành công.

### Bước 3. DELETE một relationship có chủ đích

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
      -[r:FOLLOWS]->
      (binh:DeleteLabPerson {personId: 'binh'})
DELETE r;
~~~

Bây giờ **FOLLOWS** biến mất nhưng An và Bình vẫn tồn tại; An vẫn nối với Bài viết thông qua **AUTHORED**. Vì An chưa hoàn toàn tách khỏi đồ thị, **DELETE an** vẫn chưa thể thành công.

Kiểm tra những relationship còn nối với An:

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
OPTIONAL MATCH (an)-[r]-()
RETURN an.personId AS nguoi,
       count(DISTINCT r) AS soQuanHeConLai,
       collect(DISTINCT type(r)) AS loaiQuanHe;
~~~

Sau bước 3, **soQuanHeConLai = 1**, với loại quan hệ **AUTHORED**. Mẫu **-[r]-** bỏ qua hướng nên đếm cả relationship đi vào lẫn đi ra.

### Bước 4. DETACH DELETE node vẫn còn liên kết

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
DETACH DELETE an;
~~~

Neo4j xóa An và relationship AUTHORED còn lại. Bình, Bài viết và relationship LIKES của chúng vẫn còn:

~~~cypher
MATCH (binh:DeleteLabPerson {personId: 'binh'})
      -[r:LIKES]->
      (bai:DeleteLabArticle {articleId: 'bai-1'})
RETURN binh.name AS nguoi,
       type(r) AS quanHe,
       bai.title AS baiViet;
~~~

Kết quả có một hàng tương ứng với **Bình — LIKES — Cypher cơ bản**. Nếu chạy DETACH DELETE An **ngay sau bước 1**, lệnh sẽ xóa **cả FOLLOWS và AUTHORED** trong cùng thao tác.

### Bước 5. Dọn phần dữ liệu minh họa còn lại

Chỉ áp dụng trong database thử nghiệm sau khi hoàn thành bài thực hành:

~~~cypher
MATCH (n)
WHERE (n:DeleteLabPerson AND n.personId IN ['an', 'binh'])
   OR (n:DeleteLabArticle AND n.articleId = 'bai-1')
DETACH DELETE n;
~~~

Truy vấn này nhắm vào các ID minh họa. Trong hệ thống thực tế, cần dùng điều kiện nhận diện riêng biệt và kiểm tra các bản ghi khớp trước khi xóa.

## 6. Chọn lệnh phù hợp với nghiệp vụ

### 6.1. Người dùng bỏ theo dõi người khác

Yêu cầu: giữ cả hai tài khoản nhưng bỏ quan hệ theo dõi.

~~~cypher
MATCH (u:User {id: $followerId})-[r:FOLLOWS]->(v:User {id: $followeeId})
DELETE r;
~~~

Chọn **DELETE r** vì đối tượng cần loại bỏ chỉ là relationship FOLLOWS; xóa User bằng DETACH DELETE sẽ làm mất mọi quan hệ khác liên quan tới tài khoản.

### 6.2. Xóa hoàn toàn một thực thể đã được cho phép xóa

Yêu cầu: xóa một node bản nháp và mọi liên kết trực tiếp đang trỏ đến hoặc đi từ nó.

~~~cypher
MATCH (d:Draft {id: $draftId})
DETACH DELETE d;
~~~

Chọn **DETACH DELETE d** khi nghiệp vụ xác định rằng tất cả các liên kết của Draft đều phải bị loại bỏ cùng Draft. Cần kiểm tra xem có quan hệ nào mang ý nghĩa lịch sử, kiểm toán hoặc chia sẻ mà hệ thống cần giữ lại bằng một mô hình khác hay không.

### 6.3. Chỉ muốn xóa node sau khi xử lý từng loại quan hệ

Có trường hợp nghiệp vụ đòi hỏi chuyển quyền sở hữu, lưu sự kiện hoặc xóa chọn lọc relationship trước khi xóa node. Khi đó, xử lý những quan hệ cần thiết theo quy tắc nghiệp vụ, xác nhận node đã không còn relationship rồi mới **DELETE node**.

Ví dụ, xóa mọi relationship còn nối với node bằng lệnh riêng biệt rồi xóa node:

~~~cypher
MATCH (d:Draft {id: $draftId})-[r]-()
DELETE r;
~~~

~~~cypher
MATCH (d:Draft {id: $draftId})
DELETE d;
~~~

Ví dụ này chỉ minh họa sự khác nhau về các bước. Nếu thực thi bằng **hai giao dịch riêng**, relationship mới có thể xuất hiện giữa hai lệnh và khiến DELETE d thất bại. Khi yêu cầu là xóa node cùng tất cả liên kết trực tiếp, DETACH DELETE thường diễn đạt mục đích rõ hơn và giúp thao tác được xử lý trong một câu lệnh.

## 7. Kiểm tra phạm vi xóa trước khi chạy

Trong ứng dụng, điểm nguy hiểm nhất thường không nằm ở từ khóa DELETE mà ở phần **MATCH** chọn sai hoặc chọn quá nhiều node.

### 7.1. Xác minh số node và số relationship sẽ bị ảnh hưởng

~~~cypher
MATCH (u:User {id: $userId})
OPTIONAL MATCH (u)-[r]-()
RETURN count(DISTINCT u) AS soNodeKhop,
       count(DISTINCT r) AS soQuanHeKe,
       collect(DISTINCT type(r)) AS cacLoaiQuanHe;
~~~

- **soNodeKhop** nên đúng với số thực thể dự kiến xóa, thường là 1 khi ID là duy nhất.
- **soQuanHeKe** ước lượng số relationship trực tiếp mà DETACH DELETE có thể xóa.
- **cacLoaiQuanHe** cho biết thao tác sẽ ảnh hưởng tới những loại liên kết nào, kể cả loại chưa được dự tính.

Để xem chi tiết các node hàng xóm trước khi xóa:

~~~cypher
MATCH (u:User {id: $userId})-[r]-(neighbor)
RETURN type(r) AS loaiQuanHe,
       labels(neighbor) AS nhanHangXom,
       properties(neighbor) AS thuocTinhHangXom;
~~~

Với node không có relationship, truy vấn MATCH bắt buộc có **-[r]-** sẽ trả về 0 hàng. Dùng **OPTIONAL MATCH** như truy vấn đếm phía trên để vẫn thấy node đó.

### 7.2. Tránh xóa hàng loạt ngoài ý muốn

~~~cypher
MATCH (n)
DETACH DELETE n;
~~~

Câu lệnh này có nghĩa là **xóa toàn bộ node và relationship của graph đang truy vấn**. Nó chỉ hợp lý khi chủ đích là làm trống cơ sở dữ liệu và đã có quyền thao tác tương ứng. Trong luồng nghiệp vụ thông thường, dùng nhãn và bộ lọc định danh cụ thể.

Nếu **MATCH** không tìm thấy node nào, câu lệnh DELETE/DETACH DELETE tương ứng không xóa được bản ghi nào. Ngược lại, nếu ID không được ràng buộc duy nhất và MATCH trả về nhiều node, tất cả node khớp đều có thể bị xóa.

### 7.3. Đọc kế hoạch truy vấn và cân nhắc tải hệ thống

~~~cypher
EXPLAIN
MATCH (u:User {id: $userId})
DETACH DELETE u;
~~~

**EXPLAIN** cho biết kế hoạch thực thi mà không chạy câu lệnh ghi; đây là cách kiểm tra an toàn hơn trước thao tác hủy dữ liệu. **PROFILE** thực thi truy vấn để lấy số liệu thực tế, vì vậy không dùng PROFILE để "xem thử" một lệnh xóa trên dữ liệu thật.

Với lượng dữ liệu lớn, hiệu năng chịu ảnh hưởng bởi số node được MATCH, số relationship kề mỗi node và việc có chỉ mục/constraint hỗ trợ tìm node theo ID hay không. Một node bậc rất cao có thể khiến DETACH DELETE đắt hơn nhiều so với xóa node cô lập.

Nếu cần xóa hàng loạt, cân nhắc chia thành **các giao dịch theo lô**, theo dõi thời gian thực thi và áp lực bộ nhớ/khóa. Chẳng hạn, với phiên bản Neo4j hỗ trợ cú pháp subquery theo lô:

~~~cypher
MATCH (n:ArchivedEvent)
CALL (n) {
  DETACH DELETE n
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Cú pháp nhập biến vào subquery và khả năng dùng **IN TRANSACTIONS** có khác biệt giữa các phiên bản Neo4j. Cần đối chiếu phiên bản đang chạy và cơ chế giao dịch của Java Driver hoặc công cụ thực thi trước khi áp dụng; một số chế độ giao dịch tường minh không hỗ trợ cách chia lô này.

## 8. Các nhầm lẫn thường gặp

**Nhầm lẫn 1: DELETE node tự xóa các quan hệ giống DETACH DELETE.** Sai. DELETE node còn relationship sẽ thất bại; DETACH DELETE mới xóa cả các relationship kề node.

**Nhầm lẫn 2: DETACH DELETE xóa toàn bộ các node liên quan.** Sai. Nó xóa node được chọn và các relationship trực tiếp, không xóa node hàng xóm. Một relationship khác giữa hai hàng xóm vẫn tồn tại.

**Nhầm lẫn 3: Xóa relationship cũng xóa hai đầu mút.** Sai. DELETE r xóa đúng relationship r; các node ở hai đầu được giữ nguyên.

**Nhầm lẫn 4: Chỉ cần xóa relationship đi ra trước khi DELETE node.** Sai. Relationship đi vào và tự nối cũng khiến DELETE node thất bại.

**Nhầm lẫn 5: Xóa thuộc tính và xóa relationship là một.** Sai. Xóa một thuộc tính, ví dụ **REMOVE r.since**, không xóa relationship r; DELETE r mới xóa cả liên kết.

**Nhầm lẫn 6: DETACH DELETE tương đương xóa một kiểu quan hệ cụ thể.** Sai. DETACH DELETE node xóa **mọi kiểu quan hệ** nối trực tiếp node đó; nếu chỉ muốn loại **FOLLOWS**, hãy MATCH và DELETE relationship FOLLOWS.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Node A có ba relationship: hai đi ra và một đi vào. Điều gì xảy ra khi chạy DELETE A?

*Đáp án:* Neo4j từ chối xóa A vì A vẫn có relationship, bất kể hướng của chúng.

**Câu 2.** Khi chạy DETACH DELETE A, một node B đang nối với A có bị xóa không? Các quan hệ của B tới node C thì sao?

*Đáp án:* B không bị xóa. Relationship A–B bị xóa; relationship B–C vẫn còn nếu không kề một node khác cũng được chọn để xóa.

**Câu 3.** Muốn bỏ một quan hệ theo dõi giữa hai người dùng nhưng vẫn giữ hai tài khoản thì nên dùng lệnh nào?

*Đáp án:* MATCH đúng relationship theo dõi và DELETE biến relationship, ví dụ DELETE r.

**Câu 4.** Tại sao nên kiểm tra count(DISTINCT r) với mẫu OPTIONAL MATCH (n)-[r]-() trước khi DETACH DELETE?

*Đáp án:* Vì nó cho biết có bao nhiêu relationship trực tiếp bị ảnh hưởng, bao gồm liên kết đi vào, đi ra và tự nối; DISTINCT tránh đếm trùng khi một relationship có thể xuất hiện nhiều lần do mẫu truy vấn.

## 10. Ghi nhớ

**DELETE r** dùng để xóa một hoặc nhiều relationship đã chọn mà giữ lại các node đầu mút. **DELETE n** xóa node chỉ khi node không còn relationship. **DETACH DELETE n** xóa node kèm **tất cả relationship trực tiếp** của nó, nhưng không tự xóa các node láng giềng. Trước khi xóa dữ liệu, hãy kiểm tra phạm vi MATCH, các loại relationship bị ảnh hưởng và yêu cầu lưu giữ dữ liệu của nghiệp vụ.
