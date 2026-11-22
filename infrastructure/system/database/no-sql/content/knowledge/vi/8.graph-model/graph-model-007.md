# Nút có quá nhiều quan hệ và chi phí mở rộng phép duyệt

Trong mô hình **đồ thị (graph)** của NoSQL, dữ liệu được biểu diễn bằng **nút (vertex/node)**, **cạnh (edge/relationship)** và các thuộc tính. Lợi ích của mô hình này là diễn đạt và truy vấn trực tiếp các mối liên hệ: người dùng theo dõi ai, đơn hàng liên quan tới thiết bị nào, tài khoản có chung phương thức thanh toán không, hoặc một dịch vụ phụ thuộc vào những dịch vụ khác ra sao.

Tuy nhiên, một truy vấn có ít bước duyệt không nhất thiết rẻ. Nếu một nút có hàng trăm nghìn hay hàng triệu quan hệ, từ nút đó mở rộng thêm một bước có thể tạo ra khối lượng dữ liệu rất lớn. Loại nút này thường được gọi là **hub**, **nút bậc cao (high-degree vertex)** hoặc **supernode**. Khi nhiều bước duyệt lần lượt đi qua các nút bậc cao, số cạnh và đường đi trung gian có thể tăng nhanh hơn nhiều so với số kết quả cuối cùng.

Bài học giải thích cách ước lượng **fan-out**, nhận diện rủi ro ở traversal, đọc kế hoạch thực thi và chọn chiến lược hạn chế chi phí. Điểm xuyên suốt là phải phân biệt **truy vấn cần kết quả đầy đủ, chính xác** với **truy vấn được phép lấy mẫu hoặc trả kết quả gần đúng**. Cắt bớt quan hệ có thể làm truy vấn nhanh hơn nhưng cũng có thể làm sai bài toán.

## 1. Khái niệm nút bậc cao và supernode

Xét đồ thị mạng xã hội với quan hệ có hướng **FOLLOWS**:

~~~text
(An)   ──FOLLOWS──> (Trang)
(Bình) ──FOLLOWS──> (Trang)
(Hà)   ──FOLLOWS──> (Trang)
...
(2.000.000 người) ──FOLLOWS──> (Trang)
~~~

Nút Trang có **in-degree** rất lớn vì có nhiều người theo dõi. Nhưng Trang có thể chỉ theo dõi 150 người, nghĩa là **out-degree** nhỏ hơn nhiều. Phân biệt chiều cạnh rất quan trọng khi dự báo chi phí:

- **In-degree:** số cạnh đi vào một nút, ví dụ lượng follower của một tài khoản.
- **Out-degree:** số cạnh đi ra từ một nút, ví dụ số tài khoản mà người đó đang theo dõi.
- **Degree:** số cạnh kề của một nút theo quy ước đồ thị; với cạnh có hướng, cần nói rõ là tổng hay theo từng chiều.
- **Degree theo loại quan hệ:** một tài khoản có thể có nhiều cạnh **FOLLOWS**, ít cạnh **PURCHASED**, và rất ít cạnh **ADMIN_OF**.
- **Degree có điều kiện:** số cạnh thỏa thêm tiêu chí như trạng thái còn hiệu lực, khoảng thời gian, tenant hoặc phạm vi quyền.

Không tồn tại một ngưỡng bậc duy nhất phù hợp cho mọi hệ để gọi là supernode. Một nút có 20.000 cạnh có thể xử lý tốt nếu chỉ cần lấy 10 cạnh qua một đường index phù hợp. Ngược lại, một nút có 2.000 cạnh đã có thể gây khó khăn nếu từ mỗi cạnh lại duyệt tiếp 1.000 cạnh khác trong một truy vấn đồng bộ.

**Bậc cao chỉ trở thành vấn đề hiệu năng khi workload và đường thực thi phải khai thác phần lớn hoặc toàn bộ quan hệ đó.**

### Những supernode thường gặp

| Miền nghiệp vụ | Supernode tiềm năng | Truy vấn dễ phình to |
| --- | --- | --- |
| Mạng xã hội | Người nổi tiếng, fanpage, nhóm lớn | Bạn của bạn, follower của follower, gợi ý theo kết nối |
| Thương mại điện tử | Sản phẩm nổi tiếng, danh mục phổ biến | Người mua cùng sản phẩm, các sản phẩm được mua chung |
| Chống gian lận | IP công cộng, thiết bị chung, địa chỉ giao hàng phổ biến | Tìm tất cả tài khoản liên hệ gián tiếp với một giao dịch |
| Phân quyền | Nhóm người dùng lớn, vai trò mặc định | Tìm quyền kế thừa qua nhiều nhóm |
| Đồ thị tri thức | Thực thể chung như quốc gia, lĩnh vực, tổ chức | Tìm đường liên quan giữa hai thực thể |
| Phụ thuộc phần mềm | Thư viện lõi, API gateway, dịch vụ dùng chung | Phân tích ảnh hưởng khi thành phần bị lỗi |

Một hub có thể phản ánh quan hệ thật của nghiệp vụ. Không nên tự ý xóa hoặc chia nhỏ nó nếu làm thay đổi ngữ nghĩa dữ liệu.

## 2. Chi phí phép duyệt phụ thuộc fan-out và độ sâu

**Fan-out** là số hàng xóm/cạnh được xem xét khi từ một trạng thái mở rộng sang bước tiếp theo. Giả sử mỗi nút tạo trung bình **b** nhánh và traversal đi sâu **k** bước trên cấu trúc dạng cây không trùng lặp. Số trạng thái có thể đạt xấp xỉ:

\[
1+b+b^2+\cdots+b^k
\]

Với b lớn hơn 1, đây là mức tăng bậc **O(b^k)**. Công thức này minh họa khả năng phình ra của frontier, không phải độ phức tạp cố định của mọi graph database; đồ thị thật có chu trình, nhiều đường trùng và bậc của mỗi nút không đồng đều.

Nếu b = 100:

| Độ sâu | Ứng viên mới tại bước đó | Tổng trạng thái ước tính kể cả gốc |
| --- | ---: | ---: |
| 0 | 1 | 1 |
| 1 | 100 | 101 |
| 2 | 10.000 | 10.101 |
| 3 | 1.000.000 | 1.010.101 |

Một bước duyệt bổ sung có thể tăng khối lượng công việc thêm gần hai bậc độ lớn. Nếu trong lớp thứ hai có một nút sở hữu **1 triệu** cạnh, việc dùng degree trung bình bằng 100 sẽ bỏ qua rủi ro cực trị này.

### Frontier là gì?

**Frontier** là tập các trạng thái hoặc nút chờ được mở rộng ở bước tiếp theo, đặc biệt rõ trong BFS (breadth-first search).

~~~text
Bước 0:        A
              /|\
Bước 1:      B C D                 -> frontier 3 nút
             /|\ ...
Bước 2:  hàng trăm ứng viên         -> frontier lớn hơn
Bước 3:  có thể lên tới hàng triệu -> bộ nhớ và CPU tăng
~~~

Cần quan sát kích thước frontier theo từng hop, không chỉ số nút ở output cuối cùng.

### Vì sao số đường đi khác số nút kết quả?

~~~text
       ┌──> B ──┐
A ─────┤        ├──> D
       └──> C ──┘
~~~

Có **hai đường đi** dài hai cạnh từ A đến D nhưng chỉ có **một nút D**. Nếu yêu cầu liệt kê đường đi, hai path là hai kết quả khác nhau. Nếu chỉ yêu cầu các nút có thể tới được, việc duyệt cả hai path rồi khử trùng có thể tạo công việc dư thừa.

Cần phân biệt:

1. **Edges expanded:** số cạnh mà engine đã thực sự kiểm tra/duyệt.
2. **Traversers/path states:** số trạng thái trung gian được tạo để xử lý các đường.
3. **Unique vertices visited:** số nút duy nhất đã tới.
4. **Returned rows:** số dòng cuối cùng trả cho client.

Một truy vấn **trả 20 dòng** hoàn toàn có thể đã xử lý **hàng triệu cạnh**.

## 3. Đồ thị có phân bố degree lệch làm dự báo theo trung bình sai lệch

Trong nhiều hệ thống thực, đa số nút có ít quan hệ, nhưng một số ít nút có lượng quan hệ cực lớn. Không phải đồ thị nào cũng tuân theo chính xác phân bố power-law; điểm vận hành cần quan tâm là **độ lệch giữa mean, median, p95, p99 và max degree**.

Ví dụ giả lập:

~~~text
Median out-degree = 40
P95 out-degree    = 500
P99 out-degree    = 7.000
Max out-degree    = 1.500.000
~~~

Nếu chọn 100 người dùng ngẫu nhiên, đa số phép duyệt có thể nhanh. Nhưng một request xuất phát từ hub hoặc chạm hub ở bước thứ hai có thể tạo p99 cực cao. Hơn nữa, khi chọn **cạnh ngẫu nhiên**, ta thường có xác suất gặp nút bậc cao lớn hơn khi chọn **nút ngẫu nhiên**, vì hub tham gia nhiều cạnh hơn.

Bởi vậy, benchmark traversal cần nhóm các điểm xuất phát theo **degree bucket**, phân biệt loại cạnh và chiều. Chỉ báo cáo “độ trễ trung bình khi chạy trên 1.000 tài khoản ngẫu nhiên” chưa đủ.

## 4. Những truy vấn Cypher có thể tạo fan-out lớn

### 4.1. Variable-length traversal

Ví dụ dưới đây dùng ngữ nghĩa Cypher thường gặp trong Neo4j:

~~~cypher
MATCH (u:User {userId: $userId})
MATCH path = (u)-[:FOLLOWS*1..3]->(other:User)
RETURN DISTINCT other
LIMIT 50;
~~~

Truy vấn đi qua **1–3** cạnh FOLLOWS từ một nút. Một hub xuất hiện tại bước thứ hai có thể làm số path trung gian phình ra. **LIMIT 50 ở cuối không tự bảo đảm chỉ 50 cạnh đã được đọc**. Engine có thể phải mở rộng nhiều đường trước khi DISTINCT hoặc LIMIT được áp dụng; mức tối ưu cụ thể tùy phiên bản, kế hoạch thực thi và điều kiện truy vấn.

Nếu nghiệp vụ cần đúng hai hop, không nên cho phép cả ba hop:

~~~cypher
MATCH (me:User {userId: $userId})
MATCH (me)-[:FOLLOWS]->(:User)-[:FOLLOWS]->(candidate:User)
RETURN DISTINCT candidate.userId
LIMIT 50;
~~~

Truy vấn đã hạn chế độ sâu nhưng vẫn có nguy cơ đi qua những người trung gian có bậc ra rất cao.

### 4.2. Mở rộng không chỉ rõ loại cạnh hoặc chiều

~~~cypher
MATCH (u:User {userId: $userId})-[*1..3]-(x)
RETURN DISTINCT x
LIMIT 100;
~~~

Nếu nút User còn có cạnh LIKES, PURCHASED, MEMBER_OF, VIEWED và BLOCKED, pattern tổng quát có thể mở rộng lượng quan hệ lớn không cần thiết. Chỉ rõ **loại quan hệ** và **chiều duyệt** khi bài toán cho phép là cách thu hẹp không gian tìm kiếm ở mức ngữ nghĩa.

### 4.3. Lọc quá muộn

~~~cypher
MATCH p = (u:User {userId: $userId})-[:RELATED_TO*1..4]->(x)
WHERE x.active = true
RETURN DISTINCT x
LIMIT 20;
~~~

Điều kiện active trên **nút cuối** không nhất thiết giúp giảm số cạnh được duyệt ở các bước giữa. Ngay cả khi đặt WHERE ở một vị trí khác trong câu query, optimizer có thể phải đọc các cạnh trước khi đánh giá điều kiện. Cần xem **EXPLAIN/PROFILE** để biết filter được thực thi khi nào.

Nếu việc lọc bắt buộc phải xảy ra trước khi duyệt, có thể phải thay mô hình: phân loại cạnh, tạo đường index theo thời gian/trạng thái, hoặc dùng bộ ứng viên được tiền tính.

### 4.4. Nhân số hàng khi ghép hai pattern

~~~cypher
MATCH (u:User {userId: $userId})-[:FOLLOWS]->(a)
MATCH (u)-[:LIKES]->(b)
RETURN a, b;
~~~

Nếu u theo dõi 10.000 tài khoản và thích 20.000 bài viết, hai tập được ghép có thể tạo đến **200 triệu cặp** khi không có ràng buộc nối phù hợp. Đây là rủi ro **Cartesian product**/nhân cardinality, khác với việc chỉ mở rộng thêm một hop. Có thể cần tách từng tập rồi tổng hợp, ràng buộc phạm vi hoặc định nghĩa rõ quan hệ giữa a và b.

## 5. Ví dụ thực tế: gợi ý “bạn của bạn”

Giả sử hệ thống gợi ý người dùng mà A chưa theo dõi, nhưng được những người A đang theo dõi cùng quan tâm.

~~~text
                ┌──FOLLOWS──> B ──FOLLOWS──> D
(A: người dùng) ┤
                └──FOLLOWS──> C ──FOLLOWS──> D
                                  │
                                  ├──FOLLOWS──> E
                                  └──FOLLOWS──> ... 100.000 người
~~~

Có hai đường đi từ A đến D, nên D có thể được xếp hạng cao hơn ứng viên chỉ có một người trung gian kết nối. Một truy vấn chính xác đếm số người trung gian khác nhau:

~~~cypher
MATCH (me:User {userId: $userId})
MATCH (me)-[:FOLLOWS]->(friend:User)-[:FOLLOWS]->(candidate:User)
WHERE candidate <> me
  AND NOT EXISTS {
      MATCH (me)-[:FOLLOWS]->(candidate)
  }
WITH candidate, count(DISTINCT friend) AS mutualCount
ORDER BY mutualCount DESC, candidate.userId ASC
LIMIT $limit
RETURN candidate.userId AS userId, mutualCount;
~~~

Query này mô tả logic xếp hạng; nó **không mặc nhiên đáp ứng thời gian phản hồi của ứng dụng**. Muốn biết ứng viên có mutualCount cao nhất, engine có thể phải duyệt rất nhiều đường đi, gom nhóm rồi sắp xếp. LIMIT đặt sau phép tính chỉ giảm số kết quả trả ra.

Khi C có 100.000 cạnh ra, một mình C có thể tạo 100.000 path ứng viên. Nếu 100 người trung gian cùng trỏ tới một hub khác, số path trung gian còn lớn hơn nhiều trong khi tập candidate duy nhất tăng ít.

### Chốt ngữ nghĩa trước khi tối ưu

- Chức năng cần **tất cả ứng viên chính xác** hay chỉ cần **20 đề xuất phù hợp**?
- Có thể bỏ qua quan hệ qua tài khoản nổi tiếng để giảm nhiễu không?
- Có thể giới hạn vào người dùng tích cực trong 30 ngày gần nhất không?
- Có cần loại tài khoản bị chặn, người dùng riêng tư và quan hệ vượt tenant không?
- Điểm xếp hạng là số mutual friends hay kết hợp thời gian, chất lượng tương tác và độ đa dạng?
- Kết quả chậm cập nhật một vài phút có được chấp nhận không?

Nếu sản phẩm chỉ yêu cầu 20 gợi ý có chất lượng, có thể dùng heuristic, sampling hoặc cache. Nếu ứng dụng phải tìm **tất cả đường đi** để điều tra gian lận, cắt nhánh có thể khiến kết quả không còn đúng.

## 6. Giới hạn độ sâu, loại cạnh và chiều duyệt

Ba thông số nên xuất hiện rõ trong hợp đồng truy vấn:

| Thông số | Ví dụ | Vai trò |
| --- | --- | --- |
| **Max depth** | 2 hop | Không tạo những đường đi xa hơn nhu cầu. |
| **Relationship type** | FOLLOWS, INTERACTED | Không duyệt các cạnh không liên quan. |
| **Direction** | Đi ra, đi vào, hoặc cả hai | Tránh nhân bậc do chọn sai chiều. |

Giới hạn depth giúp giảm công việc nhưng không chặn được fan-out cực lớn tại depth 1 hoặc 2. Một query “chỉ 1 hop” trên nút có hai triệu cạnh đi vào vẫn có thể rất tốn tài nguyên nếu yêu cầu trả đủ hai triệu follower.

Chọn hướng đúng còn ảnh hưởng chất lượng kết quả. “Người A theo dõi” và “người theo dõi A” là hai tập khác nhau; đổi chiều để tăng tốc mà không xét nghiệp vụ có thể làm sai ý nghĩa.

## 7. Giới hạn tập mở rộng ở từng bước

**Giới hạn kết quả cuối** và **giới hạn số hàng xóm ở mỗi bước** là hai cách khác nhau.

Giả sử chọn tối đa **M = 100** người trung gian, với mỗi người lấy tối đa **N = 200** ứng viên. Khi đó tập được giữ trước khử trùng có trần M × N = 20.000 ứng viên, thay vì mở rộng tất cả quan hệ. Mẫu Cypher khái niệm dùng subquery:

~~~cypher
MATCH (me:User {userId: $userId})
CALL {
    WITH me
    MATCH (me)-[:FOLLOWS]->(friend:User)
    WITH friend
    ORDER BY friend.lastActiveAt DESC, friend.userId ASC
    LIMIT $maxFriends
    RETURN friend
}
CALL {
    WITH friend
    MATCH (friend)-[:FOLLOWS]->(candidate:User)
    WHERE candidate.active = true
    WITH candidate
    ORDER BY candidate.lastActiveAt DESC, candidate.userId ASC
    LIMIT $maxPerFriend
    RETURN candidate
}
WITH DISTINCT candidate
RETURN candidate.userId AS userId
LIMIT $resultLimit;
~~~

Mẫu này giúp minh họa **trần kết quả trung gian được giữ** sau mỗi subquery, nhưng có hai giới hạn quan trọng:

1. **Độ đúng:** chỉ duyệt một tập con. Kết quả không còn đầy đủ, không đảm bảo tìm chính xác top-K của toàn bộ graph.
2. **Chi phí I/O:** ORDER BY trước LIMIT có thể buộc database **đọc và sắp xếp rất nhiều cạnh** để chọn M/N phần tử. Không được cho rằng M × N là giới hạn chắc chắn cho số cạnh thực sự đọc từ storage.

Để giảm chi phí vật lý, có thể cần đường truy cập theo thời gian/thứ tự được index, bộ top-neighbor tiền tính hoặc chiến lược lấy mẫu có thể dừng sớm. Cần đo bằng profile của engine.

Nếu sản phẩm cần kết quả chính xác, **không được cắt neighbor tùy ý**. Khi đó phải chuyển sang thuật toán và hệ thống xử lý khối lượng lớn phù hợp.

## 8. Chọn lọc cạnh, thời gian và trạng thái

Giả sử ứng dụng chỉ gợi ý những người có tương tác gần đây. Có thể lưu quan hệ có nghĩa riêng:

~~~text
User A ──INTERACTED {lastInteractionAt, strength}──> User B

User A ──FOLLOWS {createdAt}──> User C
~~~

Truy vấn đi qua **INTERACTED** có thể chọn lọc hơn FOLLOWS nếu nghiệp vụ có thể dùng loại cạnh này. Nhưng chỉ thêm điều kiện **lastInteractionAt > cutoff** không đủ để bảo đảm nhanh: engine có thể phải đọc hết adjacency list rồi mới lọc, tùy khả năng index/partition.

Tối ưu dựa trên filter chỉ thực sự giảm chi phí khi có **đường truy cập vật lý** cho phép tránh những cạnh không phù hợp. Những lựa chọn có thể gồm:

- Index trên thuộc tính node/cạnh nếu engine và phiên bản hỗ trợ hiệu quả.
- Danh sách quan hệ mới nhất hoặc phổ biến nhất được tiền tính.
- Bucket theo thời gian hoặc loại cạnh trong cấu trúc phục vụ truy vấn.
- Bắt đầu từ tập đích có chọn lọc cao rồi kiểm tra cạnh nối, nếu ngữ nghĩa tương đương.
- Chia truy vấn thành hai pha: tìm ứng viên phù hợp, sau đó chỉ kiểm tra kết nối của ứng viên đó.

Riêng dữ liệu có yếu tố **phân quyền hoặc tenant**, điều kiện lọc phải bảo vệ cả các bước duyệt trung gian khi cần thiết; không chỉ lọc đầu ra để tránh trả những nút trái phép.

## 9. DISTINCT, chu trình và visited set

Đồ thị có thể có chu trình:

~~~text
A -> B -> C -> A
~~~

Nếu truy vấn mở rộng nhiều bước mà không định nghĩa rõ quy tắc lặp nút/cạnh, số path có thể tăng rất lớn. Ngôn ngữ truy vấn và thuật toán khác nhau về việc cho lặp node, lặp relationship hoặc yêu cầu **simple path**.

Ví dụ Gremlin theo TinkerPop:

~~~groovy
g.V().has('User', 'userId', userId)
  .repeat(out('FOLLOWS').simplePath())
  .times(3)
  .dedup()
  .limit(20)
~~~

Truy vấn minh họa lấy nút đích sau ba bước FOLLOWS, tránh lặp lại nút **trong cùng một path** nhờ simplePath, rồi loại nút đích trùng ở cuối. Nó không có nghĩa mọi path đến cùng một nút được gộp ngay từ đầu. Engine vẫn có thể tạo nhiều traverser/path trung gian trước bước dedup.

Phân biệt:

- **Simple path:** không gặp lại nút trong chính đường đi đang xét.
- **Visited set toàn cục:** một nút đã được khám phá có thể không cần mở rộng lại cho bài toán reachability/BFS, tùy thuật toán.
- **DISTINCT ở đầu ra:** loại các dòng kết quả trùng, nhưng không nhất thiết tránh chi phí tạo chúng.
- **Đếm đường đi:** không thể dùng visited toàn cục một cách tùy ý nếu nghiệp vụ cần đếm tất cả path.

Chọn cơ chế theo **thứ cần trả lời**: nút có thể tiếp cận, đường ngắn nhất, số đường đi hay mọi đường đi.

## 10. Supernode trong thuật toán BFS và shortest path

BFS (**breadth-first search**) dùng hàng đợi để mở rộng từng lớp nút:

~~~text
queue   <- [start]
visited <- {start}

while queue không rỗng:
    v <- dequeue(queue)
    if v == target:
        return FOUND

    for each neighbor in neighbors(v):
        if neighbor chưa visited:
            visited.add(neighbor)
            enqueue(queue, neighbor)

return NOT_FOUND
~~~

Đối với đồ thị không trọng số, BFS có thể tìm đường đi ít cạnh nhất khi các điều kiện thuật toán được giữ đúng. Với biểu diễn adjacency list, BFS đầy đủ trên đồ thị có độ phức tạp **O(|V| + |E|)** theo số nút và cạnh được thăm. Khi chỉ duyệt một phần đồ thị, lượng công việc là số cạnh/nút thực sự khám phá; hub làm frontier và bộ nhớ visited lớn nhanh.

Đặt một giới hạn ngẫu nhiên như “mỗi nút chỉ xét 100 cạnh đầu” **có thể bỏ sót đường đi ngắn nhất**. Trường hợp giới hạn vì UX vẫn được phép nếu API trả kết quả dạng “đã duyệt một phần” và không tuyên bố kết quả đầy đủ.

Đối với bài toán tìm đường giữa hai nút đã biết, có thể nghiên cứu **bidirectional BFS**: tìm từ gốc và đích rồi gặp nhau ở giữa. Nó có thể giảm số lớp cần mở rộng, nhưng hiệu quả phụ thuộc hướng cạnh, degree phân bố, khả năng duyệt ngược và cách engine thực thi. Không được giả định mọi lệnh shortest path của mọi sản phẩm đều tự động dùng thuật toán này.

Các bài toán shortest path có trọng số, ràng buộc loại cạnh hoặc đường đi hợp lệ còn có thuật toán và ngữ nghĩa khác. Hãy giữ đúng điều kiện tối ưu trước khi áp dụng pruning.

## 11. Tìm điểm bắt đầu có chọn lọc

Một truy vấn thường có hai phần:

1. **Tìm nút bắt đầu** theo ID hoặc thuộc tính.
2. **Mở rộng quan hệ** từ nút đó.

Trong Neo4j, ràng buộc uniqueness cho định danh có thể cung cấp đường tìm nút ban đầu phù hợp:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

Ràng buộc này có thể giúp truy vấn tìm **User** theo userId, nhưng **không làm nhỏ** tập cạnh kề của User. Có index tốt ở nút xuất phát mà truy vấn vẫn đắt nếu bước kế tiếp mở rộng qua hub.

Nếu bài toán là tìm mối liên hệ giữa **một giao dịch đã bị gắn cờ** và nhóm tài khoản quan tâm, có thể bắt đầu từ tập giao dịch cụ thể thay vì bắt đầu từ một IP công cộng liên kết với hàng triệu giao dịch:

~~~text
Cách mở rộng quá rộng:
  IP công cộng
      -> mọi giao dịch
      -> mọi tài khoản
      -> mọi thiết bị

Cách chọn lọc hơn khi nghiệp vụ cho phép:
  50 giao dịch đã gắn cờ
      -> thiết bị / phương thức thanh toán
      -> tài khoản có liên hệ
      -> kiểm tra điều kiện rủi ro
~~~

Đổi điểm bắt đầu có thể giảm fan-out nếu vẫn bảo toàn tập kết quả cần tìm hoặc hợp đồng nghiệp vụ chấp nhận phạm vi mới. Không được đổi phạm vi một cách âm thầm trong kiểm toán.

## 12. Đọc EXPLAIN và PROFILE để thấy chi phí thực

Trong Neo4j, **EXPLAIN** cho kế hoạch ước lượng; **PROFILE** thực thi query và cung cấp số liệu các operator ở phiên bản tương ứng:

~~~cypher
EXPLAIN
MATCH (me:User {userId: $userId})-[:FOLLOWS]->(friend:User)
      -[:FOLLOWS]->(candidate:User)
RETURN DISTINCT candidate.userId
LIMIT 20;
~~~

~~~cypher
PROFILE
MATCH (me:User {userId: $userId})-[:FOLLOWS]->(friend:User)
      -[:FOLLOWS]->(candidate:User)
RETURN DISTINCT candidate.userId
LIMIT 20;
~~~

Khi đọc plan, quan tâm đến những điểm sau:

| Dấu hiệu trong plan/metric | Điều cần xác định |
| --- | --- |
| **NodeIndexSeek/NodeScan** hoặc tương đương | Nút gốc đã được tìm bằng index hay phải quét rộng? |
| **Expand/VarLengthExpand** | Bước nào mở rộng nhiều hàng và cạnh nhất? |
| **Estimated rows vs actual rows** | Planner có đánh giá thấp hub/degree skew không? |
| **Filter** | Điều kiện được áp dụng trước hay sau bước mở rộng tốn kém? |
| **Distinct/Aggregation/Sort** | Có giữ/sắp xếp hàng triệu kết quả trước LIMIT không? |
| **Db hits/page cache** | Nút thắt do I/O hay dữ liệu đã nằm trong cache? |
| **Memory/CPU/remote traffic** | Chi phí do bộ nhớ, tính toán hay shard/network? |

Tên operator và metric không giống nhau ở mọi graph database. Với Gremlin, JanusGraph, Neptune hoặc graph engine khác, dùng công cụ explain/profile/tracing riêng của nhà cung cấp. Cần kiểm tra **đúng phiên bản, đúng query shape và đúng dữ liệu**.

Nên chạy profile trên ít nhất ba nhóm nút: bậc thấp, bậc trung bình và **hub cực trị**. Một profile với nút ngẫu nhiên có degree nhỏ không đại diện cho rủi ro tail latency.

## 13. Chi phí lưu trữ và phân mảnh của supernode

Một nút có nhiều quan hệ không chỉ làm thuật toán xử lý nhiều hơn. Nó còn tạo những vấn đề vật lý:

- **Adjacency list lớn:** phải đọc nhiều entry hoặc block khi liệt kê cạnh.
- **Cache và bộ nhớ:** một nút lớn hoặc frontier lớn chiếm bộ nhớ, đẩy dữ liệu khác ra khỏi cache.
- **Hot partition/shard:** nếu các cạnh liên quan tập trung ở cùng vùng lưu trữ, một node có thể quá tải trong khi phần còn lại của cụm nhàn rỗi.
- **Đọc phân tán:** nếu cạnh trải nhiều shard, truy vấn có thể phải fan-out qua mạng rồi hợp nhất.
- **Write contention:** nhiều thao tác follow/unfollow vào cùng hub có thể tranh chấp cập nhật metadata/index hoặc khóa, tùy engine.
- **Compaction, GC, index maintenance:** tạo và xóa nhiều cạnh có thể phát sinh việc nền, khiến p99 thay đổi theo thời gian.
- **Replication và failover:** ghi hoặc truy vấn liên quan hub phải tuân theo cấu hình sao chép, độ bền và khôi phục của hệ.

Ví dụ:

~~~text
Giải pháp lưu A:
  1 hub + phần lớn cạnh cùng shard
  -> có thể thành một điểm nóng.

Giải pháp lưu B:
  cạnh của hub được phân phối trên nhiều shard
  -> tải có thể phân tán hơn,
     nhưng quét hết cạnh có thể phải gom từ nhiều shard.
~~~

Không có quy tắc phổ quát “cứ shard hub là nhanh hơn”. Kết quả phụ thuộc workload: lấy vài quan hệ gần nhất, thống kê degree, đi hai hop hay cần toàn bộ adjacency.

## 14. Mô hình dữ liệu để giảm chi phí từ hub

### 14.1. Tách quan hệ theo ý nghĩa nghiệp vụ

Nếu mọi tương tác chỉ được lưu dưới tên **RELATED_TO**, ứng dụng phải phân biệt quan hệ theo thuộc tính và có thể mở rộng nhiều cạnh không cần thiết. Dùng loại cạnh có nghĩa rõ như **FOLLOWS**, **INTERACTED**, **PURCHASED**, **MEMBER_OF** giúp viết query chính xác hơn.

Chỉ tách type khi có ý nghĩa nghiệp vụ và quy tắc bảo trì rõ ràng. Quá nhiều loại relationship tùy tiện cũng khiến schema, quản trị và truy vấn khó hiểu.

### 14.2. Tiền tính toán danh sách ứng viên

Với chức năng gợi ý, một background job có thể duyệt graph theo lô và tạo **top 100 hoặc top 1.000 candidates** cho mỗi người dùng.

~~~text
Graph gốc:
  lưu đủ quan hệ FOLLOWS, INTERACTED

Background job:
  cập nhật recommendationCandidates(userId, score, computedAt)

Online API:
  đọc tối đa 20–50 ứng viên đã chuẩn bị
  lọc quyền/chặn/trạng thái hiện hành
  trả kết quả kèm thời điểm cập nhật
~~~

Đường đọc online có thể nhanh hơn nhiều, nhưng kết quả có thể **chậm cập nhật**, phải xử lý cache invalidation, build lại dữ liệu và phân quyền. Những ràng buộc bắt buộc như tài khoản bị block hoặc quyền truy cập không thể bị bỏ qua vì dữ liệu cache chưa cập nhật.

### 14.3. Bucket theo thời gian hoặc loại cạnh

Nếu API chỉ cần “30 follower mới nhất”, ứng dụng có thể tổ chức thêm một cấu trúc theo **userId và khoảng thời gian**:

~~~text
followers_by_month:
  (targetUserId, 2026-11) -> các follower mới trong tháng 11
  (targetUserId, 2026-10) -> các follower mới trong tháng 10
~~~

Đường đọc chỉ cần bucket gần nhất rồi chuyển bucket cũ khi chưa đủ kết quả. Nhưng cấu trúc phụ này phải được duy trì khi follow/unfollow, có thể bị stale và cần xử lý pagination, duplicate, bù trừ hoặc rebuild. Nó là một lựa chọn **denormalization phục vụ truy vấn** chứ không tự thay thế toàn bộ đồ thị.

### 14.4. Vertex-centric index hoặc phân vùng đỉnh khi hệ hỗ trợ

Một số graph engine phân tán cung cấp cơ chế **vertex-centric index** hoặc partitioned vertex để quản lý quan hệ của nút bậc cao. Trong hệ sinh thái JanusGraph, cần xem các tính năng và giới hạn theo **phiên bản, storage backend và cấu hình cụ thể**.

Nếu ứng dụng tự chia một nút thành nhiều nút con logic, các thuật toán degree, shortest path, centrality hoặc uniqueness có thể cho kết quả sai nếu không tái lập đúng ngữ nghĩa gốc. Phân vùng hub là một quyết định kiến trúc cần thiết kế truy vấn và phương án đối soát, không chỉ đổi tên key.

### 14.5. Chọn thuật toán theo mục tiêu

- **BFS:** phù hợp cho reachability/shortest unweighted path với ngữ nghĩa rõ.
- **Bidirectional BFS:** cân nhắc khi biết cả hai đầu và có thể duyệt hợp lệ từ hai phía.
- **Top-K heuristics:** phù hợp với đề xuất gần đúng có thể chấp nhận sai số.
- **Sampling:** phù hợp phân tích/thống kê có chính sách sai số.
- **Batch graph processing:** phù hợp tác vụ phải duyệt lượng lớn, có checkpoint và không cần phản hồi tương tác tức thì.
- **Materialized recommendation index:** phù hợp API latency thấp, chấp nhận độ trễ cập nhật.

## 15. Ranh giới giữa kết quả chính xác và kết quả gần đúng

| Bài toán | Có thể cắt nhánh để nhanh hơn? | Điều kiện |
| --- | --- | --- |
| Gợi ý 20 tài khoản để theo dõi | Có thể | Định nghĩa kết quả gần đúng và đo chất lượng. |
| Trực quan hóa một vùng đồ thị trên UI | Có thể | Ghi rõ “hiển thị một phần” và cho phép tải tiếp. |
| Thống kê số liên kết theo mẫu | Có thể | Báo sai số/khoảng tin cậy phù hợp. |
| Kiểm toán toàn bộ tài khoản liên quan | Không được tùy ý | Phải bảo toàn độ đầy đủ hoặc trả trạng thái chưa hoàn tất. |
| Tìm shortest path chính xác | Không được tùy ý | Bỏ cạnh có thể loại mất đường tối ưu. |
| Kiểm tra quyền trên đường quan hệ | Không được tùy ý | Kết quả thiếu có thể dẫn đến quyết định sai về quyền. |

Đặc biệt trong hệ thống chống gian lận, một hub như IP nhà mạng có thể là **tín hiệu yếu vì nhiều tài khoản hợp lệ cùng dùng nó**. Có thể giảm trọng số tín hiệu, yêu cầu thêm bằng chứng độc lập hoặc giới hạn khung thời gian. Nhưng “tín hiệu yếu” không đồng nghĩa “không tồn tại cạnh”. Nếu cần điều tra đầy đủ, vẫn phải lưu giữ và truy xuất dữ liệu gốc theo chính sách.

## 16. So sánh hướng tối ưu và các đánh đổi

| Biện pháp | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Giới hạn depth | Không duyệt đường quá xa | Hub ở depth thấp vẫn nặng. |
| Chỉ rõ type/direction | Loại bỏ cạnh không liên quan | Phụ thuộc mô hình quan hệ chính xác. |
| Filter có index phù hợp | Có thể giảm số cạnh phải đọc | Tốn chi phí ghi/index; filter không phải lúc nào cũng được push down. |
| Cap hàng xóm mỗi hop | Giảm số trạng thái được giữ | Có thể mất kết quả; ORDER BY để chọn top vẫn có thể đắt. |
| Sampling | Giảm chi phí khám phá | Có sai số, có thể bias về hub hoặc nhóm phổ biến. |
| Precompute/cache | Đường đọc online nhanh | Tốn pipeline nền, stale result và invalidation. |
| Bucket/denormalize | Đọc phạm vi xác định | Tăng số bản ghi, cập nhật đồng bộ phức tạp. |
| Phân mảnh hub | Phân tán một số hot spot | Tăng network/coordination, thay đổi truy vấn. |
| Bidirectional traversal | Có thể giảm frontier cho tìm đường | Không phù hợp mọi hướng cạnh hoặc điều kiện. |
| Async/background processing | Không chặn request tương tác | Phải quản lý job, tiến độ và thời gian xử lý. |

Chọn giải pháp theo thứ tự ưu tiên **tính đúng nghiệp vụ → chi phí dưới workload thật → khả năng vận hành**, không chỉ theo số hàng kết quả trả về.

## 17. Những khác biệt giữa các sản phẩm đồ thị

Không thể suy luận cách lưu và duyệt quan hệ của một graph database sang mọi sản phẩm khác.

| Sản phẩm/giao diện | Điểm cần xác minh khi gặp hub |
| --- | --- |
| **Neo4j/Cypher** | Dense node/relationship grouping, index cho điểm xuất phát, variable-length expansion, EXPLAIN/PROFILE, version và memory budget. |
| **JanusGraph/Gremlin** | Storage backend, edge labels/direction, vertex-centric index, partitioned vertex, giới hạn truy vấn phân tán. |
| **Amazon Neptune** | Giao diện đang dùng (Gremlin/openCypher/SPARQL), explain/profile và timeout theo engine; không suy từ Neo4j sang Neptune. |
| **TigerGraph và graph analytics engine** | Chiến lược phân phối nút/cạnh, loại traversal, query plan, aggregation và tài nguyên qua shard. |
| **Graph trên document/relational DB** | Quan hệ có thể được thực thi qua lookup/join/recursive query với chi phí khác một graph engine chuyên dụng. |

Trong Neo4j, những phiên bản hỗ trợ **dense nodes** có thể tổ chức quan hệ theo type/direction để một số kiểu duyệt được hiệu quả hơn. Nhưng đây **không phải lời hứa rằng liệt kê 2 triệu cạnh chỉ tốn O(1)**. Kể cả truy cập adjacency hiệu quả, đọc và trả về 2 triệu bản ghi vẫn tiêu tốn tài nguyên.

Tương tự, Gremlin **limit** và **simplePath** được tối ưu khác nhau theo graph provider. Phải dùng tài liệu và profiler của đúng phiên bản đang chạy.

## 18. Thiết kế benchmark không bỏ sót supernode

Một bộ kiểm thử tải đại diện cần có các kịch bản theo **degree và query shape**, không chỉ số lượng node/cạnh tổng.

Ví dụ giả định:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Graph | 10 triệu User, 250 triệu cạnh FOLLOWS |
| Truy vấn | Gợi ý bạn của bạn, độ sâu 2, trả tối đa 20 người |
| Điểm bắt đầu | User degree thấp, p50, p95, p99, supernode lớn nhất |
| Offered load | 300 request/s hỗn hợp các nhóm |
| Mục tiêu p95 | ≤ 150 ms |
| Mục tiêu p99 | ≤ 400 ms |
| Correctness | Exact hoặc approximate được khai báo trước |
| Resource budget | Bộ nhớ/query, timeout và concurrency được giới hạn |

Đây chỉ là **bộ số giả định để minh họa cách viết tiêu chí nghiệm thu**, không phải mức hiệu năng chuẩn của một DBMS.

### Chỉ số nên đo

1. **Expanded edges** và **visited vertices** theo từng hop.
2. **Frontier size** tối đa và lượng path/traverser trung gian.
3. **Returned rows** và **distinct result count** để thấy lượng trùng lặp.
4. **Latency p50/p95/p99**, timeout và throughput đạt được ở offered load tương ứng.
5. **CPU, RAM, page cache, disk I/O, network và GC** nếu engine có số liệu.
6. **Số shard/node được truy cập** trong mỗi query phân tán.
7. **Ảnh hưởng ghi đồng thời**, cập nhật edge/index và contention.
8. **Độ chính xác hoặc chất lượng:** exact set match, recall@K, precision@K hoặc tiêu chí tương ứng.
9. **Độ tươi** của kết quả cache/tiền tính và việc thu hồi quyền.
10. **Hành vi timeout, cancel, failover**, retry và backpressure khi một hub quá lớn.

Một hệ có p95 100 ms trên 99% user nhưng timeout toàn bộ những user quan trọng có 1 triệu follower có thể vẫn không đáp ứng sản phẩm. Ngược lại, nếu 2 triệu follower chỉ cần hiển thị theo từng trang và kết quả không phải thời gian thực, mô hình dữ liệu phụ có thể xử lý kinh tế hơn duyệt graph đầy đủ.

### Các kịch bản tối thiểu

~~~text
Test A: bắt đầu ở nút degree nhỏ, duyệt 1 hop và 2 hop.
Test B: bắt đầu ở nút degree p95/p99.
Test C: nút thường nhưng hop thứ hai gặp supernode.
Test D: nhiều path cùng trỏ đến một candidate (trùng lặp lớn).
Test E: chu trình và quan hệ hai chiều.
Test F: vừa tạo/xóa cạnh vừa đọc.
Test G: cold cache, dữ liệu vượt RAM, nhiều query đồng thời.
Test H: hủy query, timeout, retry và failover.
Test I: precomputed candidates bị stale khi người dùng block/unfollow.
~~~

Đối với kết quả exact, chọn một dataset tham chiếu đủ nhỏ để đối chiếu độc lập, tránh dùng chính query cần kiểm tra làm “ground truth”. Với kết quả approximate, phải đặt ngưỡng chất lượng trước khi thử.

## 19. Bảo vệ hệ thống trước truy vấn đồ thị quá tốn kém

Một query nở lớn có thể chiếm hết memory/CPU và làm chậm dịch vụ chung. Cần thiết lập chính sách bảo vệ theo khả năng của hệ:

- **Deadline/timeout:** giới hạn thời gian mỗi query; hỗ trợ hủy truy vấn khi client không cần kết quả nữa.
- **Concurrency control:** không để quá nhiều fan-out query chạy cùng lúc.
- **Budget:** giới hạn depth, loại quan hệ, phạm vi ứng viên hoặc số edge expand nếu engine/thuật toán cung cấp.
- **Admission control:** chuyển tác vụ phân tích lớn sang hàng đợi thay vì chạy đồng bộ không giới hạn.
- **Pagination/streaming:** chỉ trả một phần có cursor và quy tắc thứ tự rõ, nhưng không tự suy rằng phân trang tránh được toàn bộ chi phí tính toán.
- **Observability:** ghi query shape, degree bucket, thời gian, số cạnh mở rộng và kết quả phân loại; tránh lưu dữ liệu nhạy cảm không cần thiết.
- **Backpressure/circuit breaker:** ngăn retry storm khi backend đang quá tải.
- **Trạng thái chưa hoàn tất:** nếu phải cắt phép duyệt vì ngân sách, trả thông tin rằng kết quả chưa đầy đủ nếu nghiệp vụ đòi hỏi completeness.

Đặc biệt, **timeout không đồng nghĩa đồ thị không có đường đi**. Với kiểm tra quyền, gian lận hoặc kiểm toán, ứng dụng phải phân biệt **NOT_FOUND được chứng minh** với **UNKNOWN/INCOMPLETE vì truy vấn bị hủy**.

## 20. Ba tình huống lựa chọn giải pháp

### Tình huống A — Danh sách follower mới nhất

Yêu cầu: hiển thị 30 follower mới nhất của một tài khoản có 2 triệu follower.

Giải pháp cần xem liệu engine có thể lấy **một phần adjacency theo createdAt** bằng index/thứ tự vật lý hay không. Nếu phải đọc và sort 2 triệu cạnh mỗi request, nên cân nhắc cấu trúc dữ liệu phụ **followers_by_time(targetId, time)**, index phù hợp hoặc cache phân trang. Khi unfollow, block hay tài khoản chuyển riêng tư, dữ liệu phụ phải phản ánh chính sách truy cập; cursor phải xác định đúng cách đi qua các lần cập nhật mới.

### Tình huống B — Gợi ý người quen

Yêu cầu: trả 20 ứng viên nhanh, chất lượng tốt, không bắt buộc đầy đủ.

Có thể giới hạn ứng viên theo tương tác gần đây, chọn hàng xóm có chất lượng, tiền tính top-K, hoặc lấy mẫu. Giữ graph gốc đầy đủ; đường online chỉ đọc tập ứng viên đã được chấp thuận. Đánh giá bằng độ trễ **và** chất lượng như recall@K hoặc tiêu chí sản phẩm phù hợp, đồng thời kiểm tra block/privacy tại thời điểm phục vụ.

### Tình huống C — Điều tra gian lận

Yêu cầu: tìm mọi tài khoản có liên hệ hợp lệ với một giao dịch trong tối đa 4 bước để phục vụ kiểm toán.

Cắt ngẫu nhiên 100 cạnh đầu của một hub **không giữ được completeness**. Cần định nghĩa quan hệ có ý nghĩa (thiết bị, IP, thời gian, loại bằng chứng), pruning chỉ khi được chứng minh tương đương, chọn điểm xuất phát có chọn lọc và chạy batch/asynchronous với checkpoint hoặc báo cáo tiến độ. Khi chưa duyệt hết, kết quả phải ghi **incomplete** thay vì kết luận không có quan hệ.

## 21. Quy trình xử lý khi một query gặp hub

~~~mermaid
flowchart TD
    A[Viết yêu cầu và tiêu chuẩn đúng của kết quả] --> B[Đo degree theo loại và chiều]
    B --> C[PROFILE query trên nút thường và supernode]
    C --> D{Frontier / path trung gian bùng nổ?}
    D -->|Có| E[Thu hẹp depth, type, direction, điểm xuất phát]
    D -->|Không| F[Kiểm tra I/O, sort, cache, network, lock]
    E --> G{Cho phép kết quả gần đúng?}
    G -->|Có| H[Cap per-hop, sampling, precompute, cache]
    G -->|Không| I[Chọn index/thuật toán/partition/batch chính xác]
    F --> I
    H --> J[Đo latency, tài nguyên và chất lượng]
    I --> J
    J --> K[Thử lại với hub, concurrent load và sự cố]
~~~

Áp dụng theo trình tự:

1. **Xác định mục tiêu:** mọi path, mọi nút reachable, đường ngắn nhất hay top-K gợi ý?
2. **Thu thập degree distribution:** phân bố in/out degree theo relationship type; tìm p95/p99/max và hub nằm trên path thực.
3. **Quan sát kế hoạch:** EXPLAIN/PROFILE để thấy nơi Expand, JOIN, DISTINCT hay SORT tạo lượng hàng lớn.
4. **Giảm công việc không cần thiết:** depth hữu hạn, loại/chiều cạnh, điểm bắt đầu chọn lọc, ràng buộc thời gian và index hữu ích.
5. **Nếu cho phép gần đúng:** giới hạn ứng viên hoặc tiền tính toán, đo chất lượng và gắn nhãn completeness rõ ràng.
6. **Nếu cần chính xác:** chọn thuật toán, cấu trúc phụ, phân mảnh hoặc xử lý batch có thể kiểm chứng độ đầy đủ.
7. **Thiết lập bảo vệ:** timeout, concurrency, retry policy, memory budget và trạng thái incomplete.
8. **Nghiệm thu trên workload lệch:** thử nút thường, hub, nhiều path trùng, cập nhật đồng thời và lỗi phân tán.

## Kết luận

Chi phí phép duyệt trong graph NoSQL phụ thuộc **số cạnh thực sự mở rộng**, **độ lớn frontier**, **số path trung gian**, **độ lệch degree** và **cách engine truy cập dữ liệu**. Một truy vấn chỉ hai hoặc ba hop có thể trở nên cực kỳ đắt khi đi qua supernode. LIMIT ở output, DISTINCT hoặc index tìm nút khởi đầu không mặc nhiên ngăn được chi phí này.

Thiết kế hiệu quả cần bắt đầu từ **ngữ nghĩa kết quả**: nếu chỉ cần gợi ý, có thể dùng sampling, cap theo hop và precompute; nếu cần reachability, shortest path hoặc kiểm toán chính xác, phải bảo toàn độ đầy đủ bằng thuật toán và hạ tầng phù hợp. Hãy đo fan-out thật, xem plan, kiểm thử trên hub và phân biệt rõ **kết quả đầy đủ** với **kết quả đã được cắt để tiết kiệm tài nguyên**.
