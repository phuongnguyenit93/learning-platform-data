# Kiểm thử tải với phân bố quan hệ gần dữ liệu thực tế

## 1. Vì sao graph có cùng số node và relationship vẫn chạy khác nhau?

Một hệ thống Neo4j không chỉ chịu tải theo số lượng **node** và **relationship**. Hiệu năng còn phụ thuộc **relationship tập trung vào node nào, chiều đi của cạnh, kiểu liên kết, số bước duyệt, thuộc tính được lọc và các truy vấn ứng dụng thực sự gửi tới database**.

Hãy so hai graph đều có 100.000 node và 1.000.000 relationship:

- **Graph A — tương đối đồng đều:** phần lớn node có khoảng 10 relationship.
- **Graph B — lệch mạnh:** phần lớn node có rất ít relationship, nhưng vài trăm node “nổi tiếng” nhận hàng nghìn hoặc hàng chục nghìn relationship.

Hai graph có cùng số node và cạnh, nhưng truy vấn `MATCH (u)<-[:FOLLOWS]-(f)` trên một node rất nổi tiếng có thể duyệt nhiều liên kết hơn hẳn cùng truy vấn trên node thông thường. Truy vấn hai bước có thể nhân số hàng theo số nhánh ở từng bước; ghi/xóa relationship trên các node có mức độ kết nối cao có thể có đặc tính tranh chấp tài nguyên khác.

Vì vậy, **“tạo đủ một triệu cạnh ngẫu nhiên” không có nghĩa là đã tạo bộ dữ liệu đại diện cho hệ thống thật**. Bài học này xây dựng một quy trình kiểm thử tải phản ánh tương đối đúng **phân bố quan hệ** trong mô hình property graph Neo4j, kết hợp:

1. Đo đặc điểm của graph nguồn một cách an toàn.
2. Sinh hoặc chọn dữ liệu thử giữ được các đặc điểm quan trọng.
3. Thiết kế workload đọc/ghi theo hành vi thật của ứng dụng.
4. Kiểm thử tải, độ trễ đuôi, hub, contention và đường đi nhiều bước.
5. Đối chiếu kế hoạch Cypher, kết quả và chỉ số vận hành.
6. Ghi lại giới hạn của mô hình thử để không kết luận quá mức.

Mục tiêu không phải sao chép dữ liệu nhạy cảm từ production, mà là **bảo tồn những cấu trúc ảnh hưởng đến truy vấn** trên bộ dữ liệu có thể kiểm soát và tái lập.

## 2. Các đặc điểm graph cần đo trước khi thiết kế tải

Trong Neo4j, node có label và property; relationship có type, hướng và có thể có property. Một graph dành cho kiểm thử truy vấn liên kết cần được mô tả nhiều chiều.

| Đặc điểm | Ví dụ | Vì sao quan trọng với hiệu năng? |
|---|---|---|
| Số node theo label | User, Post, Topic, Order | Xác định quy mô tìm kiếm và index |
| Số relationship theo type | FOLLOWS, AUTHORED, LIKED | Các kiểu cạnh có fan-out và truy vấn khác nhau |
| **In-degree** | User được bao nhiêu người theo dõi | Truy vấn follower, node nổi tiếng |
| **Out-degree** | User theo dõi bao nhiêu người | Truy vấn following và tạo feed |
| Phân bố degree | Median, p95, p99, max, tỷ lệ degree = 0 | Phân biệt đám đông thông thường và hub |
| Độ lệch in/out | Nhiều người nhận link nhưng ít link ra | Định hướng duyệt quyết định tải |
| Cộng đồng/nhóm | User cùng tổ chức, vùng địa lý hoặc sở thích | Quyết định xác suất cạnh nằm trong/ngoài nhóm |
| Tương quan degree | Hub thường nối đến hub hay node nhỏ? | Ảnh hưởng số nhánh và đường đi nhiều bước |
| Cạnh trùng và self-loop | Cùng hai đầu mút có nhiều quan hệ? | Ảnh hưởng số hàng MATCH và phép đếm |
| Phân bố thời gian | Phần lớn tương tác gần đây | Ảnh hưởng lọc theo ngày và hot data |
| Độ chọn lọc property | 1% User ACTIVE hay 80%? | Ảnh hưởng index, Filter, Estimated Rows |
| Hỗn hợp truy vấn | 80% đọc, 20% ghi, nhiều endpoint | Ảnh hưởng cache, CPU, khóa và latency |

**Degree** là số relationship gắn với node trong **phạm vi label/type/hướng đã chọn**. Không nên báo “mỗi node trung bình có 10 quan hệ” rồi kết luận graph đồng đều: trung bình che khuất hoàn toàn phần đuôi phân bố.

### 2.1. Degree được tính theo mối quan hệ nào?

Với mô hình:

~~~text
(u:User)-[:FOLLOWS]->(v:User)
(u:User)-[:AUTHORED]->(p:Post)
(u:User)-[:LIKED]->(p:Post)
(p:Post)-[:IN_TOPIC]->(t:Topic)
~~~

một User có thể:

- Theo dõi 20 User khác (**out-degree FOLLOWS = 20**).
- Được 10.000 User theo dõi (**in-degree FOLLOWS = 10.000**).
- Viết 4 bài (**out-degree AUTHORED = 4**).
- Thích 200 bài (**out-degree LIKED = 200**).

Không cộng các loại relationship thành một degree duy nhất nếu truy vấn của ứng dụng chỉ dùng `FOLLOWS`. Cần đo **theo từng loại quan hệ và hướng có ý nghĩa với workload**.

### 2.2. Cộng đồng và số cạnh giữa các nhóm

Một graph xã hội thường không phân phối cạnh hoàn toàn ngẫu nhiên: người dùng có xu hướng theo dõi những người cùng lĩnh vực, vùng hoặc nhóm. Nếu bộ dữ liệu thử gán cạnh đều giữa mọi User, truy vấn gợi ý “bạn của bạn” có thể gặp số ứng viên và độ trùng khác thực tế.

Có thể đo **tỷ lệ cạnh nội bộ nhóm** và tỷ lệ cạnh đi ra nhóm ngoài. Khi tạo dữ liệu thay thế, cần bảo tồn tương quan này ở mức phù hợp, thay vì chỉ giữ tổng số cạnh.

## 3. Dùng Cypher đo phân bố in-degree và out-degree

Các truy vấn sau dùng nhãn `LoadUser` và relationship `FOLLOWS` để minh họa phép đo. Trong môi trường thật, thay bằng nhãn/type nghiệp vụ **sau khi đã đánh giá quyền và chi phí truy vấn**.

**Cảnh báo:** Đo degree cho toàn graph lớn có thể tốn tài nguyên, đặc biệt khi cần duyệt nhiều relationship. Nên chạy trên bản sao/staging hoặc trong cửa sổ được phê duyệt; không mặc định đo toàn graph production trong giờ cao điểm.

### 3.1. Thống kê in-degree theo từng node

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS inDegree
RETURN count(*) AS userCount,
       sum(inDegree) AS followsRelationships,
       min(inDegree) AS minInDegree,
       avg(inDegree) AS meanInDegree,
       percentileCont(inDegree, 0.50) AS p50InDegree,
       percentileCont(inDegree, 0.95) AS p95InDegree,
       percentileCont(inDegree, 0.99) AS p99InDegree,
       max(inDegree) AS maxInDegree;
~~~

Một vài điểm quan trọng:

- `OPTIONAL MATCH` giữ cả User không có follower; những node này nhận **inDegree = 0**.
- `count(r)` đếm **relationship**, không phải số follower phân biệt. Nếu có hai cạnh FOLLOWS từ cùng một nguồn đến đích, nó đếm 2.
- `sum(inDegree)` là tổng cạnh FOLLOWS mà cả hai đầu mút nằm trong phạm vi nhãn được chọn.
- `percentileCont(..., 0.99)` là phân vị nội suy, có thể không phải degree nguyên thực sự của một node. Có thể dùng `percentileDisc` nếu cần phân vị quan sát được.

**Không dùng `count(*)` thay cho `count(r)` trong OPTIONAL MATCH** để đếm degree: khi node không có cạnh, OPTIONAL MATCH vẫn tạo một hàng có `r = null`, khiến `count(*) = 1` thay vì 0.

### 3.2. Thống kê out-degree

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (u)-[r:FOLLOWS]->(:LoadUser)
WITH u, count(r) AS outDegree
RETURN count(*) AS userCount,
       avg(outDegree) AS meanOutDegree,
       percentileCont(outDegree, 0.50) AS p50OutDegree,
       percentileCont(outDegree, 0.95) AS p95OutDegree,
       percentileCont(outDegree, 0.99) AS p99OutDegree,
       max(outDegree) AS maxOutDegree;
~~~

Trong graph có chỉ một loại User→User FOLLOWS được xét, **tổng in-degree bằng tổng out-degree** vì mỗi relationship có đúng một đầu nguồn và một đầu đích. Nhưng **phân bố** in-degree và out-degree có thể rất khác. Một mạng có số ít tài khoản cực kỳ nổi tiếng thường có đuôi **in-degree** nặng hơn đuôi out-degree.

### 3.3. Phân nhóm degree thành histogram

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS degree
WITH CASE
       WHEN degree = 0 THEN '0'
       WHEN degree <= 5 THEN '1-5'
       WHEN degree <= 20 THEN '6-20'
       WHEN degree <= 100 THEN '21-100'
       ELSE '101+'
     END AS bucket,
     CASE
       WHEN degree = 0 THEN 0
       WHEN degree <= 5 THEN 1
       WHEN degree <= 20 THEN 2
       WHEN degree <= 100 THEN 3
       ELSE 4
     END AS bucketOrder
RETURN bucket, count(*) AS users
ORDER BY bucketOrder;
~~~

Các ngưỡng 5, 20, 100 chỉ để minh họa. Trong hệ thống thực, chọn bucket sao cho tách được **đa số node**, **các mức fan-out quan trọng với truy vấn** và **những hub cực trị**. Chỉ một p99 cũng có thể chưa cho biết chuyện gì xảy ra với 0,01% node đầu bảng.

### 3.4. Nhận diện hub lớn nhất

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS inDegree
RETURN u.userId AS userId, inDegree
ORDER BY inDegree DESC, userId
LIMIT 20;
~~~

Top 20 giúp chọn bộ khóa `userId` cho các kịch bản tải trên hub. Tránh đưa ID thật/sensitive của tài khoản người dùng vào log benchmark hoặc tài liệu công khai; có thể dùng mã ẩn danh có ánh xạ nội bộ phù hợp.

### 3.5. Quan sát degree theo cộng đồng

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u.community AS community, u, count(r) AS inDegree
RETURN community,
       count(*) AS users,
       avg(inDegree) AS meanInDegree,
       percentileCont(inDegree, 0.95) AS p95InDegree,
       max(inDegree) AS maxInDegree
ORDER BY users DESC;
~~~

Đây là cách phát hiện các nhóm có mật độ cạnh khác nhau. Một workload chỉ chọn User của cộng đồng nhỏ có thể không đại diện cho cộng đồng lớn hoặc nhóm có rất nhiều hub.

## 4. Kiểm tra cấu trúc mà histogram chưa cho biết

Giữ đúng phân bố degree là **cần thiết nhưng chưa đủ**. Hai graph có cùng số node với từng degree giống nhau vẫn có thể có cấu trúc đường đi khác xa nhau.

### 4.1. Tỷ lệ cạnh trong và ngoài cộng đồng

~~~cypher
MATCH (a:LoadUser)-[r:FOLLOWS]->(b:LoadUser)
RETURN a.community AS sourceCommunity,
       b.community AS targetCommunity,
       count(r) AS relationships
ORDER BY relationships DESC;
~~~

Nếu dữ liệu thật tập trung cạnh trong cùng cộng đồng còn dữ liệu thử nối hoàn toàn ngẫu nhiên, truy vấn đề xuất follower hai bước có thể sinh ra tập ứng viên khác hẳn.

### 4.2. Mẫu nối hub–hub và hub–node thường

Cần xem các node có degree cao chủ yếu trỏ tới nhau hay chủ yếu tới node nhỏ. Một graph “được giữ đúng số follower” nhưng nối hub với mọi node ngẫu nhiên vẫn có thể sai về số đường đi dài hai hoặc ba bước.

Có thể tạo bảng degree theo từng node, rồi đối chiếu cặp `sourceOutDegree` và `targetInDegree` của từng cạnh trong môi trường phân tích. Khi graph lớn, việc join những thống kê này nên được thực hiện bằng pipeline/graph analytics phù hợp thay vì ghép các mẫu MATCH gây nhân hàng không chủ đích.

### 4.3. Cạnh trùng và self-loop

~~~cypher
MATCH (a:LoadUser)-[r:FOLLOWS]->(b:LoadUser)
WITH a.userId AS sourceId,
     b.userId AS targetId,
     count(r) AS n
WHERE n > 1
RETURN sourceId, targetId, n
ORDER BY n DESC
LIMIT 20;
~~~

~~~cypher
MATCH (u:LoadUser)-[r:FOLLOWS]->(u)
RETURN count(r) AS selfFollows;
~~~

Nếu nghiệp vụ chỉ cho một FOLLOWS mỗi cặp và không chấp nhận self-follow, các trường hợp trên là lỗi cần làm sạch. Nếu hệ thống cho phép nhiều relationship cùng cặp với mục đích riêng, không được tự xóa chúng chỉ để graph “đẹp hơn”. Kiểm thử phải bảo tồn **quy tắc bội số thực sự**.

### 4.4. Số nhánh của đường đi nhiều bước

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (u)<-[:FOLLOWS]-(a:LoadUser)
      <-[:FOLLOWS]-(b:LoadUser)
RETURN count(*) AS twoHopPaths,
       count(DISTINCT b) AS distinctSecondHopUsers;
~~~

`twoHopPaths` đếm **đường đi theo các mẫu relationship**, còn `distinctSecondHopUsers` đếm node đích phân biệt. Hai số có thể chênh lệch rất lớn trong cộng đồng chặt chẽ có nhiều đường đi tới cùng một người.

**Chỉ chạy trên dataset thử hoặc điểm bắt đầu được phép.** Với hub lớn, ngay cả truy vấn đếm đường đi hai bước cũng có thể tạo rất nhiều hàng trung gian; cần giới hạn mức thử và theo dõi timeout/CPU.

## 5. Lập hồ sơ workload từ hành vi ứng dụng

Phân bố graph giống thật vẫn không đủ nếu tập truy vấn gửi tới Neo4j khác thực tế. Cần thu thập ở mức tổng hợp, ẩn danh và trong phạm vi được phép:

- Tỷ lệ truy vấn tìm theo khóa đơn, mở rộng một bước, hai bước, aggregation, tìm đường đi.
- Tỷ lệ đọc/ghi, số request trên giây và số request đồng thời.
- Distribution của **điểm bắt đầu traversal**: bao nhiêu request nhắm vào hub, bao nhiêu vào node thường, bao nhiêu vào node cô lập?
- Các tham số: `LIMIT`, lọc thời gian, bộ lọc trạng thái, phân trang, số type relationship.
- Số item/bản ghi cập nhật trong mỗi transaction.
- Tỷ lệ cache hit do người dùng thường truy cập lại cùng đối tượng.
- Hành vi theo thời gian: giờ cao điểm, burst sau sự kiện, lô nhập, job định kỳ.

### 5.1. Ví dụ nhóm truy vấn của một dịch vụ xã hội

| Nhóm workload | Truy vấn đại diện | Yếu tố nhạy với phân bố quan hệ |
|---|---|---|
| Đọc hồ sơ | Tìm User theo userId | Độ chọn lọc index, property size |
| Danh sách following | User → FOLLOWS → User | Out-degree và phân trang |
| Danh sách follower | User ← FOLLOWS ← User | In-degree; hub nổi tiếng |
| Gợi ý người theo dõi | Duyệt 2 bước và loại trùng | Degree correlation, community, số hàng trung gian |
| Feed cá nhân | Following → AUTHORED → Post | Out-degree, post per author, thời gian |
| Tương tác | Tạo LIKED hoặc bình luận | Cạnh tranh ghi node/relationship |
| Theo dõi/bỏ theo dõi | MERGE/DELETE FOLLOWS | Cùng cặp đầu mút, write contention |
| Job tổng hợp | Đếm like/follower theo nhóm | Scan/aggregation, tải nền |

Tỷ trọng phải lấy từ môi trường nghiệp vụ mục tiêu; không tự dùng tỷ lệ “80% đọc, 20% ghi” chỉ vì đó là một ví dụ thường gặp. Một hệ thống nhắn tin, mạng xã hội và graph phụ thuộc phần mềm có workload hoàn toàn khác nhau.

### 5.2. Mẫu tham số phải có độ lệch

Nếu 5% request thực tế truy cập 0,1% tài khoản nổi tiếng, một bộ kiểm thử chọn userId đều từ toàn bộ danh sách sẽ **hiếm khi chạm hub**. Điều này khiến p95/p99 có vẻ đẹp hơn thực tế.

Để mô phỏng, dùng phân bố tham số có trọng số theo nhóm:

- Một tỷ lệ request vào các **hub** nổi tiếng.
- Một tỷ lệ vào **node trung bình**.
- Một tỷ lệ vào **node ít kết nối hoặc cô lập**.
- Các nhóm đặc biệt như user vừa đăng ký, tài khoản có nhiều post, khách hàng có nhiều đơn.

Cần mô phỏng **cả xác suất được chọn lẫn độ lớn degree của node được chọn**. Hai yếu tố này độc lập về logic: một node có degree lớn chưa chắc được request truy cập thường xuyên, và một node có degree nhỏ vẫn có thể là điểm nóng vì được hỏi lặp lại nhiều lần.

## 6. Lựa chọn quy mô và cách tạo dữ liệu thử có thể tái lập

### 6.1. Hai lựa chọn thường dùng

**Bản sao được ẩn danh và giảm nhạy cảm:** có thể giữ cấu trúc thật tốt hơn, nhưng cần sự cho phép, kiểm soát bảo mật, chính sách dữ liệu và cách che/loại bỏ PII. Không chép trực tiếp graph production vào môi trường kiểm thử thiếu kiểm soát.

**Graph tổng hợp (synthetic):** giúp tái lập, điều khiển tỷ lệ hub và quy mô, tránh dữ liệu cá nhân. Tuy nhiên, nếu generator đơn giản quá mức, số node/relationship trông đúng nhưng cấu trúc cộng đồng và đường đi vẫn sai.

Thông thường cần kết hợp **thống kê nguồn ở mức tổng hợp** với **generator sinh graph có tham số**, rồi đối chiếu.

### 6.2. Không chỉ áp dụng kết nối ngẫu nhiên đều

Mẫu “với mỗi cạnh, chọn hai node ngẫu nhiên độc lập theo phân bố đều” tạo ra một kiểu degree distribution gần đồng đều hơn nhiều mạng thực tế có tail nặng. Nó cũng không tự bảo tồn cộng đồng, tương quan độ nổi tiếng hay tỷ lệ User có degree bằng 0.

Một cách sinh graph có cấu trúc hơn:

1. Sinh danh sách node theo tỷ lệ từng label/segment/community.
2. Với mỗi node, lấy **out-degree mục tiêu** từ một phân bố đã đo theo segment.
3. Chọn node đích theo xác suất phù hợp **in-degree mục tiêu** và các điều kiện như cùng cộng đồng, độ hoạt động, thời gian.
4. Không cho self-loop hoặc cạnh trùng nếu nghiệp vụ cấm; nếu có loại bỏ, cần bù/điều chỉnh để phân bố không lệch mạnh.
5. Tạo nhiều type relationship theo cardinality riêng; không dùng cùng một phân bố cho FOLLOWS, LIKED và AUTHORED.
6. Đo lại kết quả cuối. Generator chỉ là một giả thuyết về graph, **không phải bằng chứng nó giống thật**.

### 6.3. Tư duy theo “degree sequence”

Một chiến lược khởi đầu là tạo danh sách degree mục tiêu của từng node, ví dụ:

~~~text
User 1: in-degree 10000, out-degree 20
User 2: in-degree 5000,  out-degree 12
User 3: in-degree 40,    out-degree 25
...
User N: in-degree 0,     out-degree 1
~~~

Với graph có hướng chỉ gồm FOLLOWS giữa các User, tổng in-degree phải bằng tổng out-degree, và bằng số relationship. Nếu hai tổng khác nhau thì danh sách degree mục tiêu không thể được thực hiện nguyên vẹn.

Có thể thử ghép “đầu ra” vào “đầu vào” theo số lượng degree (mô hình degree sequence), rồi điều chỉnh để tăng tỷ lệ cạnh nội bộ cộng đồng. Tuy vậy, không phải mọi degree sequence đều khả thi dưới các ràng buộc **không self-loop** và **không cạnh trùng**. Generator phải phát hiện thiếu cạnh và báo rõ tỷ lệ thực hiện mục tiêu, không âm thầm tự coi đã đạt.

### 6.4. Ba quy mô nên giữ tách biệt

| Quy mô thử | Mục tiêu | Giới hạn diễn giải |
|---|---|---|
| **Mini fixture** vài chục node | Kiểm tra Cypher, chiều cạnh, tính đúng | Không đại diện tải hay cache production |
| **Representative subset** | So sánh kết quả theo loại node, degree, community | Cắt graph có thể làm thay đổi đường đi và degree |
| **Scale-like dataset** gần tỷ lệ mục tiêu | Kiểm tra bộ nhớ, I/O, p95/p99, tranh chấp | Vẫn phải đối chiếu workload, index, cấu hình |

Một subset chọn User ngẫu nhiên có thể **làm mất hub** hoặc cắt đi phần lớn cạnh của hub. Nếu bắt buộc giảm quy mô, cần nêu rõ cách lấy mẫu và sai lệch so với graph gốc.

## 7. Tạo fixture nhỏ để kiểm tra mô hình, không dùng để kết luận hiệu năng

Phần thực hành sau tạo một graph **nhỏ và cố ý lệch**, chỉ để minh họa cách đo. Thực hiện trên **database thử nghiệm riêng**. Nhãn `LoadUser` tách biệt khỏi `User` nghiệp vụ.

### 7.1. Chuẩn bị constraint

~~~cypher
CREATE CONSTRAINT load_user_id_unique IF NOT EXISTS
FOR (u:LoadUser)
REQUIRE u.userId IS UNIQUE;
~~~

### 7.2. Tạo 12 User với hai cộng đồng

~~~cypher
UNWIND range(1, 12) AS i
MERGE (u:LoadUser {userId: 'U' + toString(i)})
SET u.community = CASE
  WHEN i <= 8 THEN 'A'
  ELSE 'B'
END,
u.segment = CASE
  WHEN i IN [1, 2] THEN 'HUB'
  ELSE 'REGULAR'
END;
~~~

`MERGE` theo khóa và constraint hỗ trợ nhập lại fixture mà không nhân bản User. Khi test cạnh tranh ghi, phải có cơ chế điều phối/constraint phù hợp; fixture trên không tự thay thế kiểm thử concurrency.

### 7.3. Tạo một số cạnh tập trung vào U1

~~~cypher
UNWIND [
  {from: 'U2',  to: 'U1'},
  {from: 'U3',  to: 'U1'},
  {from: 'U4',  to: 'U1'},
  {from: 'U5',  to: 'U1'},
  {from: 'U6',  to: 'U1'},
  {from: 'U7',  to: 'U1'},
  {from: 'U8',  to: 'U1'},
  {from: 'U9',  to: 'U1'},
  {from: 'U10', to: 'U1'},
  {from: 'U11', to: 'U1'},
  {from: 'U12', to: 'U1'},
  {from: 'U2',  to: 'U3'},
  {from: 'U3',  to: 'U4'},
  {from: 'U4',  to: 'U5'},
  {from: 'U5',  to: 'U6'},
  {from: 'U6',  to: 'U7'},
  {from: 'U7',  to: 'U8'},
  {from: 'U9',  to: 'U10'},
  {from: 'U10', to: 'U11'},
  {from: 'U11', to: 'U12'}
] AS edge
MATCH (a:LoadUser {userId: edge.from})
MATCH (b:LoadUser {userId: edge.to})
MERGE (a)-[:FOLLOWS]->(b);
~~~

Với dữ liệu trống ban đầu và chỉ thực thi các câu trên, fixture có **12 LoadUser và 20 FOLLOWS**. `U1` nhận **11** cạnh đi vào, còn đa số User khác chỉ nhận **0 hoặc 1**. Vì vậy, `U1` là một điểm bắt đầu có **in-degree cao trong phạm vi fixture**, nhưng tuyệt đối **không có quy mô đủ để làm benchmark throughput/latency thực tế**.

### 7.4. Kiểm tra phân bố vừa tạo

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS followers
RETURN u.userId AS userId,
       u.community AS community,
       followers
ORDER BY followers DESC, userId;
~~~

Đếm tổng relationship:

~~~cypher
MATCH (:LoadUser)-[r:FOLLOWS]->(:LoadUser)
RETURN count(r) AS followsCount;
~~~

Nếu fixture đã có dữ liệu LoadUser từ lần chạy trước hoặc được sửa thêm, không dùng kỳ vọng 12/20 như một khẳng định không cần kiểm tra.

### 7.5. Dọn fixture có chủ đích

Nếu muốn xóa **toàn bộ node mang nhãn LoadUser của bài thực hành** trong database thử được cô lập:

~~~cypher
MATCH (u:LoadUser)
DETACH DELETE u;
~~~

Đây là lệnh xóa dữ liệu thật và xóa mọi relationship trực tiếp của những node được tìm thấy. Chỉ chạy khi chắc chắn nhãn `LoadUser` không được dùng cho dữ liệu cần giữ; **không áp dụng lên nhãn nghiệp vụ production**.

## 8. Nạp dataset thực tế hơn bằng danh sách cạnh có kiểm soát

Sau khi generator bên ngoài tạo danh sách cạnh theo phân bố mong muốn, ứng dụng Java có thể truyền dữ liệu đã chia lô vào Cypher. Ví dụ tham số `$edgePairs`:

~~~json
[
  {"fromId": "U2", "toId": "U1"},
  {"fromId": "U3", "toId": "U1"},
  {"fromId": "U4", "toId": "U1"}
]
~~~

Query nhập theo lô:

~~~cypher
UNWIND $edgePairs AS edge
MATCH (a:LoadUser {userId: edge.fromId})
MATCH (b:LoadUser {userId: edge.toId})
WHERE a <> b
MERGE (a)-[:FOLLOWS]->(b)
RETURN count(*) AS processedRows;
~~~

Điều cần nhớ:

- `processedRows` đếm **hàng mẫu được xử lý qua truy vấn**, không phải số relationship **mới tạo**.
- `MATCH` không tìm thấy đầu mút sẽ bỏ hàng; phải đối chiếu số cạnh nguồn và số cạnh thực tạo, không được âm thầm chấp nhận thiếu.
- `MERGE` relationship giúp chạy lại từng cặp theo mô hình một cạnh/cặp trong luồng nhập kiểm soát, nhưng **không tự chứng minh duy nhất dưới mọi lịch ghi đồng thời** nếu ứng dụng cho nhiều worker ghi cùng cặp và không có bảo vệ phù hợp.
- Sinh node và constraint **trước** khi nhập relationship; dùng khóa nghiệp vụ ổn định.
- Chia lô vừa phải để tránh transaction quá lớn; khi cần throughput cao, đo cả chi phí retry và lock contention.
- Nếu mô hình cho phép nhiều relationship giữa cùng cặp đầu mút, cần mô hình định danh khác, không dùng MERGE theo đúng mẫu trên để vô tình gộp dữ liệu.

Một generator ngoài database nên xuất **seed, tham số phân bố, số cạnh theo type và checksum/manifest** để test có thể tái lập. Nếu dùng `rand()` trong Cypher để tạo graph, kết quả giữa các lần chạy thường khác nhau và khó so sánh phiên bản truy vấn.

## 9. Biến đặc điểm dữ liệu thành các kịch bản truy vấn

Một bộ kiểm thử cần vừa có **câu Cypher đúng mục đích**, vừa có các nhóm tham số được chọn theo phân bố thực.

### 9.1. Truy vấn một bước vào hub

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
LIMIT $pageSize;
~~~

Với `$userId = 'U1'` trong fixture, truy vấn duyệt những người theo dõi hub. Với `'U12'`, số người theo dõi ít hơn. `LIMIT` giới hạn số hàng trả về, nhưng **không bảo đảm tổng chi phí xử lý chỉ bằng pageSize trong mọi kế hoạch và trường hợp**.

Nếu API cần phân trang có thứ tự ổn định:

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
ORDER BY followerId
LIMIT $pageSize;
~~~

Thao tác sắp xếp có thể buộc hệ thống xử lý nhiều ứng viên trước khi chọn trang. Hãy thử đúng truy vấn ứng dụng đang dùng, không thay bằng phiên bản không ORDER BY để làm benchmark đẹp hơn.

### 9.2. Truy vấn hai bước: rủi ro nhân hàng

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (u)<-[:FOLLOWS]-(first:LoadUser)
      <-[:FOLLOWS]-(second:LoadUser)
RETURN count(*) AS twoHopPaths,
       count(DISTINCT second) AS uniqueSecondHopUsers;
~~~

Hai bước có thể tạo số đường đi tăng mạnh khi nhiều first-hop node cũng có nhiều follower. Nếu ứng dụng chỉ cần biết một node ứng viên **có tồn tại quan hệ** hay không, cân nhắc `EXISTS` thay vì mở rộng rồi tạo tất cả tổ hợp.

Trên graph thật, traversal hai bước từ một hub có thể đủ nặng để gây stress. Đừng bắt đầu test bằng toàn bộ hub lớn nhất và mức song song cao nhất; hãy tăng tải có kiểm soát và giới hạn thời gian.

### 9.3. Truy vấn theo cộng đồng

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (u)-[:FOLLOWS]->(v:LoadUser)
WHERE v.community = $community
RETURN v.userId AS followedUserId
LIMIT $pageSize;
~~~

Tỷ lệ cạnh nội bộ/ngoài cộng đồng quyết định số hàng qua Filter, dù out-degree bằng nhau. Một generator sai về cộng đồng có thể làm test query theo `community` quá dễ hoặc quá khó.

### 9.4. Truy vấn EXISTS để tìm liên kết

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (candidate:LoadUser {userId: $candidateId})
RETURN EXISTS {
  MATCH (u)-[:FOLLOWS]->(candidate)
} AS isFollowing;
~~~

Câu hỏi chỉ cần **true/false** không cần phát tất cả hàng hay relationship. Với nhiều cặp đầu mút được kiểm tra đồng thời, độ trễ chịu ảnh hưởng index tìm node, mức cache và cấu trúc relationship.

### 9.5. Ghi thêm quan hệ hoặc xóa quan hệ

~~~cypher
MATCH (a:LoadUser {userId: $fromId})
MATCH (b:LoadUser {userId: $toId})
WHERE a <> b
MERGE (a)-[:FOLLOWS]->(b);
~~~

~~~cypher
MATCH (a:LoadUser {userId: $fromId})
      -[r:FOLLOWS]->
      (b:LoadUser {userId: $toId})
DELETE r;
~~~

Ghi relationship có thể cần đồng bộ cấu trúc kết nối của các node đầu mút. Nếu mọi worker cùng tạo cạnh tới hub `U1`, contention có thể khác so với khi mỗi worker ghi một cặp User độc lập.

**Không test create/delete với ID production**. Dùng danh sách node dành riêng cho môi trường test và có chính sách dọn dữ liệu sau các thử nghiệm ghi.

## 10. Tham số thử tải phải phản ánh độ lệch truy cập

Để so sánh hub và node thường một cách có cấu trúc, chia request thành **nhóm tham số** (parameter strata).

| Nhóm | Cách chọn | Loại vấn đề muốn phát hiện |
|---|---|---|
| Hub rất lớn | Các node ở đuôi phân bố degree | Fan-out, p99, bộ nhớ và khóa nóng |
| Degree trung bình | Các node gần p50/p75 | Độ trễ phổ biến |
| Degree thấp/0 | Node ít kết nối hoặc cô lập | OPTIONAL MATCH, trường hợp không có kết quả |
| Nhóm đông | Community có nhiều node/cạnh | Độ chọn lọc và số ứng viên |
| Nhóm nhỏ | Community ít node | Kế hoạch khác và tính chính xác |
| Node nóng theo traffic | Được truy cập lặp lại liên tục | Cache, đồng thời, contention |
| Node lạnh | Truy cập hiếm, ít trong cache | Page cache và I/O |

Không tự giả định “node nhiều follower = node nóng về traffic”. Hãy đo **xác suất được request chọn** nếu có số liệu. Nếu thiếu, nên báo rõ đây là giả định thử và chạy nhiều kịch bản khác nhau.

### 10.1. Kiểm thử từng nhóm rồi kiểm thử hỗn hợp

Quy trình hữu ích:

1. **Single-group test:** chỉ hub, chỉ node thường, chỉ node cô lập để biết đường cong độ trễ riêng.
2. **Mixed workload:** trộn theo tỷ lệ truy cập đã đo để đánh giá trải nghiệm tổng thể.
3. **Hotspot stress:** tăng tỷ lệ truy cập hub để tìm ngưỡng quá tải.
4. **Regression:** chạy lại cùng dataset/seed và cùng tham số sau khi thay đổi query/index.

Nhờ phân tách, p95 tổng có thể được giải thích: tăng latency do phần hub nặng hơn, do tỷ lệ request vào hub thay đổi, hay do truy vấn bị regress.

## 11. Thiết kế pha kiểm thử tải

Chạy benchmark có kế hoạch, không chỉ bấm “1.000 user ảo” rồi lấy một con số trung bình.

| Pha | Mục tiêu | Cách dùng |
|---|---|---|
| **Smoke** | Kiểm tra kết quả, quyền, dữ liệu, cấu hình | Ít request, độ song song thấp |
| **Warm-up** | Cho JVM, page cache, pool và kế hoạch truy vấn ổn định hơn | Không trộn tùy tiện với số liệu steady |
| **Ramp-up** | Tìm điểm latency bắt đầu tăng theo tải | Tăng RPS/concurrency từng nấc |
| **Steady-state** | Đo throughput, p95/p99, lỗi ở tải mục tiêu | Giữ workload đủ lâu để có mẫu |
| **Spike** | Mô phỏng một đợt truy cập đột ngột vào hub | Theo dõi queue, timeout, hồi phục |
| **Stress/breakpoint** | Tìm vùng hệ thống không còn đạt SLO | Có dừng an toàn, không ép production |
| **Soak** | Tìm rò rỉ memory/session và tích lũy độ trễ | Chạy dài trên môi trường cho phép |
| **Recovery** | Kiểm tra phục hồi sau khi giảm tải | Queue, lag, pool, transaction chờ có hết? |

### 11.1. RPS và concurrency không đồng nghĩa

Một hệ thống có 100 request đồng thời nhưng mỗi request mất 10 ms sẽ có thông lượng tiềm năng khác với 100 request đồng thời nhưng mỗi request mất 3 giây. Cần ghi **request arrival rate**, **concurrency đang thực hiện**, **response time**, **queue wait** và **throughput hoàn thành**.

Có hai cách mô hình tải:

- **Closed-loop:** mỗi client phát request mới sau khi request cũ hoàn tất. Khi server chậm, tốc độ phát yêu cầu tự giảm.
- **Open-loop / arrival-rate:** phát request theo lịch đến độc lập hơn với tốc độ phản hồi. Dễ phát hiện hệ thống tụt lại dưới tải dồn, nhưng cần đo request bị trễ hoặc bị bỏ.

Nếu chỉ dùng closed-loop, server chậm có thể tạo **coordinated omission**: ít request được phát đúng vào những thời điểm hệ thống đang bận, làm số liệu đuôi có vẻ tốt hơn thực tế. Chọn công cụ và cách đo phù hợp, ghi rõ những request không được gửi đúng lịch, timeout và tải bị từ chối.

### 11.2. Không bắt đầu từ tải cực đại

Nên bắt đầu từ smoke và ramp. Khi hệ thống đạt ngưỡng lỗi cao, tăng thêm tải có thể chỉ làm queue và timeout chồng chất, không tạo thêm hiểu biết. Đặt **giới hạn dừng** theo quyền sử dụng môi trường, thời gian, CPU/memory, tỷ lệ lỗi và tác động tới hệ thống liên quan.

## 12. Đo đúng chỉ số và phân tích độ trễ đuôi

**Throughput** và **latency** là hai trục khác nhau. Một hệ thống có thể xử lý nhiều request/giây nhưng p99 rất cao khi truy vấn hub.

| Chỉ số | Diễn giải |
|---|---|
| Request/second phát ra và hoàn thành | Đầu vào so với năng lực thực hiện |
| p50 latency | Trải nghiệm điển hình |
| p95/p99 latency | Độ trễ đuôi; thường nhạy với hub và tranh chấp |
| Timeout/error rate | Mức ổn định tại tải mục tiêu |
| Queue/pool wait | Request chờ tài nguyên trước khi chạy query |
| Query rows / DB hits | Mức công việc Cypher đã thực hiện |
| CPU, RAM, GC, page cache và I/O | Giới hạn tài nguyên server |
| Active transactions, deadlocks, lock waits | Tranh chấp ghi và giao dịch dài |
| Bytes/records trả về | Chi phí Bolt, network và materialization |
| Retry count của Java Driver | Khả năng có lỗi transient và áp lực tải |
| Lag của consumer / batch import | Tải nền cạnh tranh với API |

Nếu một nhóm request hub chiếm số lượng nhỏ nhưng gây ra phần lớn timeout, chỉ báo cáo p50 hoặc thời gian trung bình sẽ che khuất vấn đề.

### 12.1. Kết hợp score tổng với score theo nhóm

Một báo cáo tốt có **cả**:

- p50/p95/p99 **toàn bộ workload**.
- p50/p95/p99 **riêng cho hub**.
- p50/p95/p99 **riêng cho node trung bình**.
- p50/p95/p99 **riêng cho node degree thấp**.
- Tỷ lệ request của từng nhóm trong lần chạy.

Khi thay đổi cách chọn tham số hoặc tỷ lệ hub, cần so sánh trong cùng nhóm trước khi kết luận phiên bản database đã nhanh/chậm hơn.

### 12.2. Đặt SLO theo nghiệp vụ, không lấy một ngưỡng tùy ý

Ví dụ minh họa một ứng dụng tự chọn mục tiêu:

~~~text
Endpoint followers
- tải mục tiêu: do đội vận hành xác định từ số liệu
- p95 latency dưới ngưỡng đã cam kết
- p99 latency dưới ngưỡng cảnh báo
- timeout rate không vượt giới hạn
- kết quả đúng với tập tham số và pagination
~~~

Không có một giá trị p95 “chuẩn” áp dụng cho mọi graph Neo4j. Ngưỡng phụ thuộc API, loại truy vấn, quy mô graph và yêu cầu người dùng. **Định nghĩa tiêu chí trước khi test**, không điều chỉnh tiêu chí sau khi nhìn kết quả.

## 13. Kiểm chứng kế hoạch Cypher trên các nhóm điểm bắt đầu

Neo4j có query planner, index và nhiều toán tử thực thi traversal. Bản thân biểu thức Cypher chưa cho biết chi phí thực tế.

### 13.1. EXPLAIN để xem kế hoạch mà không chạy truy vấn

~~~cypher
EXPLAIN
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
LIMIT $pageSize;
~~~

Các điểm cần xem:

- Truy vấn có bắt đầu bằng **index seek** trên `LoadUser.userId` không?
- Có quét toàn bộ label không?
- Planner dự đoán **Estimated Rows** bao nhiêu ở bước Expand?
- Có Sort/Top/Aggregation không, và xuất hiện tại đâu?
- Với truy vấn hai bước, số hàng ước lượng phình lên ở bước nào?

Constraint `LoadUser.userId` trong fixture tạo cơ sở cho tra cứu theo khóa. Nếu query thật có WHERE khác, index phù hợp còn phụ thuộc sự chọn lọc và kế hoạch truy vấn.

### 13.2. PROFILE để đo, nhưng chạy truy vấn thật

~~~cypher
PROFILE
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
LIMIT $pageSize;
~~~

Trên dữ liệu thử, PROFILE có thể hiển thị số hàng, DB hits và các thông tin thực thi khác tùy phiên bản Neo4j. Hãy thử với `userId` của hub và của node thường để thấy khác biệt.

**PROFILE thực thi truy vấn.** Không dùng PROFILE trên câu `CREATE`, `SET`, `DELETE` hoặc `DETACH DELETE` trong dữ liệu quan trọng chỉ để “xem thử”. Với truy vấn ghi, dùng EXPLAIN trước rồi chạy/đo trên database test.

### 13.3. Không suy ra nhanh/chậm chỉ từ thứ tự văn bản

Neo4j có thể đẩy predicate hoặc chọn điểm bắt đầu khác với thứ tự các dòng Cypher. Kết quả phụ thuộc thống kê, index, dữ liệu và phiên bản. Khi sửa query, cần:

1. Bảo đảm **hai query trả đúng cùng yêu cầu nghiệp vụ**.
2. So kế hoạch với cùng cấu hình dữ liệu.
3. Đo trên hub, node thường và node cô lập.
4. So p95/p99 theo workload hỗn hợp.
5. Kiểm tra thay đổi memory/DB hits và dữ liệu trả về.

Một thay đổi tối ưu cho truy vấn node thường có thể làm truy vấn hub xấu hơn; vì vậy không chỉ benchmark một `userId` “đẹp”.

## 14. Thử tải ghi: relationship và tranh chấp ở hub

Neo4j tự điều phối khóa khi transaction ghi node, relationship và cấu trúc graph. Với kịch bản:

~~~cypher
MATCH (a:LoadUser {userId: $fromId})
MATCH (b:LoadUser {userId: $toId})
MERGE (a)-[:FOLLOWS]->(b);
~~~

hai nhóm tải có thể khác nhau rõ rệt:

- **Phân tán:** mỗi worker ghi các cặp đầu mút khác nhau.
- **Tập trung:** nhiều worker cùng tạo/bỏ quan hệ tới một hub hoặc cùng cặp node.

Cần đo transaction latency, deadlock/retry, lock wait và tác động tới query đọc chạy song song. **MERGE relationship** không phải giấy bảo đảm rằng mọi bất biến quan hệ luôn đúng dưới mọi mức song song; nếu mỗi cặp chỉ được phép có đúng một FOLLOWS, thiết kế dữ liệu và xử lý concurrency riêng là cần thiết.

### 14.1. Ghi và đọc cùng lúc

Đừng chỉ benchmark đọc trên graph bất biến nếu production có nhiều ghi:

- Người dùng thường xuyên theo dõi/bỏ theo dõi.
- Worker tạo Post, Like, Comment.
- Job CDC đồng bộ trạng thái.
- Pipeline GDS/analytics đọc hoặc tải projection.
- Job dọn dữ liệu và cập nhật index/constraint theo lịch.

Thử workload pha trộn có thể bộc lộ latency cao hoặc transaction conflict mà đọc thuần không thấy.

### 14.2. Đừng dùng CREATE vô điều kiện khi muốn đo cập nhật lũy đẳng

Nếu benchmark phát cùng lệnh tạo relationship nhiều lần mà mọi lần đều `CREATE`, graph sẽ thay đổi theo hướng nhiều cạnh trùng và test không còn so sánh được với tải trước đó. Cần định nghĩa rõ nghiệp vụ cho phép nhiều relationship hay chỉ một; dùng khóa, MERGE/constraint và idempotency tương ứng.

Khi đo khả năng ghi, cần ghi lại **số relationship cuối cùng, số transaction commit và số lần retry** chứ không chỉ “số câu lệnh được gửi”.

## 15. Java Driver trong bộ phát tải và API thử nghiệm

Một ứng dụng Java dùng Neo4j Java Driver có thể cần quan sát **tổng latency API**, không chỉ thời gian query bên trong Neo4j. Driver quản lý kết nối, session, transaction, retry và việc đọc các record trả về.

Ví dụ service chỉ đọc, ánh xạ trực tiếp kết quả:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class FollowerReadService {
    private final Driver driver;

    public FollowerReadService(Driver driver) {
        this.driver = driver;
    }

    public List<String> followers(String userId, int requestedLimit) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId is required");
        }
        int limit = Math.max(1, Math.min(requestedLimit, 100));

        String cypher = """
            MATCH (u:LoadUser {userId: $userId})
            MATCH (f:LoadUser)-[:FOLLOWS]->(u)
            RETURN f.userId AS followerId
            LIMIT $limit
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "userId", userId,
                    "limit", limit
                )).list(row -> row.get("followerId").asString())
            );
        }
    }
}
~~~

Trong bộ phát tải:

- **Driver được dùng lại** giữa các request; không tạo mới Driver mỗi lần.
- **Session có vòng đời ngắn** và không dùng chung tùy tiện giữa các thread.
- **Kết quả được tiêu thụ** trong transaction; nếu benchmark bỏ qua kết quả mà API thật phải đọc, kết luận sẽ sai.
- `executeRead` là managed transaction, có thể retry lỗi transient phù hợp; latency và số lần retry cần được tính vào trải nghiệm.
- `LIMIT` phản ánh hợp đồng endpoint và cần được kiểm soát; không đổi một query trả 1.000 record thành trả 10 record rồi tuyên bố hiệu năng đã cải thiện nếu sản phẩm vẫn cần 1.000.
- Java snippet mô tả service đọc; nó **không phải framework load test đầy đủ** và không tạo được phân bố traffic có arrival rate chỉ bằng cách gọi hàm một lần.

Khi API dùng **Spring Data Neo4j**, bộ thử tải nên chạy qua cùng endpoint và projection/DTO của ứng dụng, vì mapping entity và việc materialize relationship có thể làm thời gian ứng dụng khác đáng kể so với query Cypher độc lập.

### 15.1. Test trực tiếp Bolt hay HTTP API?

| Điểm kiểm thử | Phát hiện tốt | Không tự bao quát |
|---|---|---|
| Driver → Neo4j qua Bolt | Query, session, transaction, network Bolt | Auth HTTP, JSON serialization, routing ứng dụng |
| HTTP → Application → Neo4j | Trải nghiệm end-to-end, validation, pool, mapping | Khó tách nguyên nhân nếu thiếu tracing |
| GDS/analytics batch | Memory/CPU của thuật toán graph | Hành vi endpoint realtime |
| Import/CDC pipeline | Tốc độ tạo node/cạnh, checkpoint, replay | Độ trễ feed khi có tương tác người dùng |

Nên có bài benchmark **ở tầng database** để cô lập query và một bài **qua API** để thấy trải nghiệm thật. Cả hai dùng dữ liệu và phân bố tham số có thể đối chiếu.

## 16. Tách ảnh hưởng của cache và dữ liệu nóng/lạnh

Một kiểm thử lặp cùng 10 `userId` có thể tận dụng cache tốt hơn workload thực tế mà request đến từ hàng triệu User. Cần ghi rõ:

- **Warm cache:** phần lớn dữ liệu/index đã được truy cập trước đó.
- **Cold-ish cache:** nhiều khóa mới hoặc graph ít được đọc gần đây.
- **Hot-key workload:** tập key nhỏ được truy cập liên tục.
- **Broad-key workload:** key rải rộng trên graph.

Không nhất thiết phải “xóa sạch cache” cho mỗi phép thử; làm như vậy đôi khi không đại diện production. Nhưng phải giữ **điều kiện cache tương đương giữa các phiên bản** khi so regression.

### 16.1. Warm-up có thể thay đổi hình dạng kết quả

Trong giai đoạn warm-up, Neo4j có thể nạp trang dữ liệu, index và ứng dụng Java có thể khởi tạo pool, JIT. Nếu trộn thời gian warm-up vào steady-state, p95/p99 bị chi phối bởi điều kiện khởi động thay vì tải ổn định.

Ngược lại, nếu production có cold start hoặc deploy thường xuyên, cần có **kịch bản khởi động lạnh riêng**; không được bỏ qua vì con số steady đẹp hơn.

## 17. Tái lập kết quả kiểm thử

Một lần benchmark chỉ hữu ích nếu có thể giải thích và chạy lại. Manifest của mỗi lần test nên ghi:

~~~yaml
runId: neo4j-load-demo-001
purpose: compare-follower-query
dataset:
  kind: synthetic
  seed: fixed-seed
  nodeCounts: recorded-by-label
  relationshipCounts: recorded-by-type
  degreeDistribution: recorded-in-degree-out-degree
  communities: recorded-mixing-ratio
workload:
  queryMix: recorded-percentages
  keyDistribution: hub-medium-cold
  concurrency: configured-value
  arrivalRate: configured-value
  duration: configured-value
environment:
  neo4jVersion: recorded
  javaDriverVersion: recorded
  cpuMemoryStorage: recorded
  indexSchema: recorded
measurements:
  latencyP50P95P99: recorded
  throughputErrors: recorded
  dbHitsRows: recorded
~~~

Đây là **mẫu ghi chép minh họa**, không phải file manifest đã được tạo hay cấu hình bắt buộc của công cụ cụ thể. Nên ghi thêm phiên bản ứng dụng, commit query, seed generator, warm-up, cách đo timeout, dữ liệu đã được dùng lại hay tạo mới và tình trạng tải nền.

Không trộn các lần chạy dùng database size, cấp CPU, index, tỷ lệ truy cập hub hoặc phân bố query khác nhau rồi kết luận tốc độ chỉ thay đổi vì sửa Cypher.

## 18. Những sai lầm thường gặp khi giả lập phân bố quan hệ

| Sai lầm | Vì sao làm kết quả sai lệch? | Cách khắc phục |
|---|---|---|
| Chỉ khớp tổng số node/cạnh | Không phản ánh hub và tail | So degree histogram, p95/p99/max |
| Tạo cạnh ngẫu nhiên đều | Mất skew và community | Sinh theo degree sequence/nhóm |
| Chỉ đo degree trung bình | Hub bị che khuất | Đo zero-degree, p50, p95, p99, top hub |
| Chỉ giữ in-degree | Truy vấn following có thể sai workload | Đo riêng in/out và type |
| Giảm quy mô bằng lấy mẫu đều | Có thể cắt mất cạnh hub | Đối chiếu cấu trúc sau lấy mẫu |
| Dùng một query đơn giản với một ID | Không bao phủ workload ứng dụng | Trộn read/write và các nhóm tham số |
| Chọn ID đều khi traffic lệch | Không tạo hot key thực tế | Dùng phân bố request theo cohort |
| Chỉ đo latency trung bình | Không thấy tail query hub | p50/p95/p99 và timeout theo nhóm |
| Dùng LIMIT nhỏ hơn sản phẩm | Benchmark không còn đúng nghiệp vụ | Giữ payload/page size tương đương |
| Chỉ test warm cache | Thiếu điều kiện key lạnh và deploy | Tách warm, cold-ish, hot-key |
| Không consume Driver Result | Bỏ qua chi phí network/mapping | Đọc kết quả như API thật |
| Không đo lỗi/retry | Throughput đẹp dù nhiều request thất bại | Tính error, timeout, retry và completed RPS |
| Tạo/xóa cạnh liên tục nhưng không reset fixture | Dataset thay đổi giữa hai lần test | Snapshot/manifest và quy trình làm mới |
| PROFILE câu ghi trên production | Lệnh ghi thực sự được thực thi | EXPLAIN hoặc database thử |
| Không kiểm thử cộng đồng | Hai-hop candidates có thể sai mạnh | Bảo tồn mixing/correlation |
| Không ghi cấu hình môi trường | Kết quả khó tái lập | Manifest đầy đủ |

## 19. Bài tập vận dụng

### Bài 1 — Hai graph cùng số cạnh

Graph A và Graph B cùng có 100.000 User và 1.000.000 FOLLOWS. Graph A phân bố cạnh tương đối đều; Graph B có một số hub nhận rất nhiều follower.

**Câu hỏi:** Có thể dùng tốc độ của truy vấn follower trên A để dự đoán tải hub ở B không?

**Đáp án:** Không đáng tin. Hai graph có phân bố in-degree khác nhau; truy vấn bắt đầu từ hub trên B có thể mở rộng nhiều cạnh hơn. Cần benchmark theo cohort degree và xem kế hoạch/thời gian thực tế.

### Bài 2 — Đếm follower thiếu số 0

Một truy vấn dùng `OPTIONAL MATCH (f)-[r:FOLLOWS]->(u)` và `count(*)`. User không có follower được đếm là 1.

**Câu hỏi:** Sửa ra sao?

**Đáp án:** Dùng `count(r)` để chỉ đếm relationship không null. `count(*)` đếm cả hàng được OPTIONAL MATCH giữ lại.

### Bài 3 — Lệch hướng degree

Một tài khoản theo dõi 100 người nhưng chỉ có 2 follower.

**Câu hỏi:** Nếu API hiển thị danh sách người theo dõi, nên phân nhóm theo degree nào?

**Đáp án:** **In-degree FOLLOWS**, vì relationship có hướng follower → người được theo dõi. Out-degree liên quan danh sách following.

### Bài 4 — Đường đi hai bước

Một node có 1.000 follower, và mỗi follower lại có nhiều follower. Query hai-hop tạo rất nhiều path nhưng chỉ vài nghìn User phân biệt.

**Câu hỏi:** Vì sao `count(*)` và `count(DISTINCT second)` chênh nhau?

**Đáp án:** Có thể có nhiều đường đi khác nhau tới cùng một User. `count(*)` đếm path match, còn DISTINCT đếm node duy nhất; cả hai đại lượng phục vụ câu hỏi khác nhau.

### Bài 5 — Chỉ số benchmark “đẹp” bất thường

Một bài kiểm thử chọn `userId` ngẫu nhiên đều trên toàn graph, trong khi production có rất nhiều request vào 0,1% tài khoản nổi tiếng.

**Câu hỏi:** Kết quả p99 có thể bị sai lệch thế nào?

**Đáp án:** Bộ thử có thể gần như không chạm các hub nóng; tải trung bình và độ trễ đuôi có thể thấp hơn thực tế. Cần dùng phân bố key theo traffic hoặc kiểm thử hub riêng.

### Bài 6 — LOAD test mà không kiểm kết quả

Benchmark gửi request lấy follower nhưng không kiểm tra ID trả về, chỉ đo HTTP 200.

**Câu hỏi:** Đã đủ xác nhận query tối ưu chưa?

**Đáp án:** Chưa. Query có thể trả thiếu dữ liệu, phân trang sai hoặc bỏ qua follower. Cần kiểm chứng đúng hợp đồng đầu ra và số hàng trên dữ liệu thử.

### Bài 7 — Ghi đồng thời vào hub

Một nghìn worker đều thử tạo relationship FOLLOWS tới cùng User nổi tiếng.

**Câu hỏi:** Chỉ đo số transaction thành công có đủ không?

**Đáp án:** Không. Cần theo dõi latency, wait/timeout, deadlock/retry, số relationship thực tạo, cạnh trùng theo quy tắc nghiệp vụ và tác động tới truy vấn đọc song song.

### Bài 8 — Hai phép so sánh không cùng điều kiện

Chạy truy vấn mới trên graph 100.000 cạnh nóng cache, còn truy vấn cũ trên graph 1.000.000 cạnh và key lạnh.

**Câu hỏi:** Có thể khẳng định truy vấn mới nhanh hơn không?

**Đáp án:** Không. Dataset size, skew, key distribution và cache đều thay đổi. Cần so trong điều kiện có thể đối chiếu và ghi manifest.

## 20. Checklist trước khi chốt kết quả tải

- [ ] Có số node theo label và relationship theo type/hướng.
- [ ] Có histogram in-degree/out-degree, zero-degree, p50/p95/p99 và max.
- [ ] Có thống kê hub, community, cạnh trùng và tương quan cần thiết.
- [ ] Dataset thử có seed/nguồn gốc hợp lệ, không lộ dữ liệu cá nhân.
- [ ] Dữ liệu thử đã được đối chiếu với thống kê nguồn sau khi sinh/import.
- [ ] Các query và tham số phản ánh endpoint, LIMIT, filter và tỷ lệ truy cập thật.
- [ ] Có nhóm hub, thường, thấp/cô lập và hot/cold keys.
- [ ] Đã chạy smoke, warm-up, steady và kịch bản tải tăng có kiểm soát.
- [ ] Theo dõi completed RPS, p50/p95/p99, timeout, retry và kết quả đúng.
- [ ] Đã xem EXPLAIN/PROFILE trên môi trường an toàn cho các query đại diện.
- [ ] Thử cả đọc/ghi pha trộn nếu production có ghi tương ứng.
- [ ] Driver/session/pool, index, database version và tài nguyên được ghi lại.
- [ ] Có tiêu chí dừng và SLO đã định nghĩa trước.
- [ ] Có manifest tái lập và những giới hạn đã biết của graph tổng hợp.

## 21. Ghi nhớ

**Kiểm thử tải Neo4j với phân bố quan hệ gần dữ liệu thực tế** không dừng ở việc tạo đủ node và relationship. Cần giữ được **độ lệch in-degree/out-degree, hub, cộng đồng, bội số cạnh, kiểu relationship, thời gian và tính chọn lọc của property** theo những đặc điểm có ảnh hưởng tới workload. Một graph đồng đều giả lập cho một graph có vài hub khổng lồ sẽ dễ che khuất traversal đắt, đuôi độ trễ cao và tranh chấp ghi.

Hãy **đo phân bố nguồn bằng các phép thống kê an toàn, sinh graph thử có tham số và kiểm tra lại**, sau đó kiểm thử các truy vấn Cypher cùng phân bố tham số thực tế. Đánh giá **độ đúng của kết quả**, p50/p95/p99, throughput hoàn thành, retry/timeout, query plan và tài nguyên của Neo4j lẫn Java Driver hoặc Spring Data Neo4j. Khi ghi rõ seed, workload, cấu hình và giới hạn của dataset, kết quả mới đủ tin cậy để quyết định tối ưu query, index, mô hình graph và năng lực chịu tải của ứng dụng.
