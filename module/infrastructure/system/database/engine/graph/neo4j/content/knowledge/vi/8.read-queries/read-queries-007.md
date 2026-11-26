# ORDER BY, SKIP và LIMIT để sắp xếp và chia trang

## 1. Vì sao phải sắp xếp trước khi chia trang?

Trong Neo4j, câu lệnh Cypher thường trả về nhiều **dòng kết quả** sau khi `MATCH` tìm node, relationship hoặc đường đi thỏa mãn mẫu truy vấn. Khi xây dựng màn hình danh sách bài viết, người dùng, giao dịch hoặc những node liên quan, ứng dụng thường cần:

- **Sắp xếp** theo thời gian, điểm số, tên hoặc nhiều tiêu chí.
- **Chia trang** để mỗi lần chỉ lấy một nhóm kết quả có kích thước phù hợp.
- **Đảm bảo thứ tự ổn định** để tránh bỏ sót hoặc lặp bản ghi khi người dùng chuyển trang.

Cypher cung cấp ba thành phần cơ bản:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `ORDER BY` | Sắp xếp các dòng kết quả theo một hoặc nhiều biểu thức | `ORDER BY createdAt DESC, postId ASC` |
| `SKIP` | Bỏ qua số dòng đầu tiên của tập kết quả ở vị trí áp dụng | `SKIP 20` |
| `LIMIT` | Giới hạn số dòng được trả về hoặc chuyển sang phần truy vấn tiếp theo | `LIMIT 10` |

Với một trang danh sách thông thường, thứ tự viết là:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 20
LIMIT 10;
```

Truy vấn yêu cầu sắp xếp từ mới đến cũ, dùng `postId` để phân biệt các bài viết có cùng thời điểm, bỏ qua 20 dòng đầu và trả tối đa 10 dòng tiếp theo. **Không có `ORDER BY`, Neo4j không bảo đảm thứ tự trả về**, dù một truy vấn nhỏ đôi lúc tình cờ cho kết quả giống nhau khi chạy lại.

> **Phạm vi bài học:** Các ví dụ dùng mô hình property graph của Neo4j và cú pháp Cypher phổ biến trong Neo4j 5. Bài tập tập trung vào truy vấn đọc; node, relationship, index, constraint, Java Driver và Spring Data Neo4j được đề cập khi ảnh hưởng trực tiếp đến việc sắp xếp hoặc phân trang.

## 2. Chuẩn bị dữ liệu mẫu có thể chạy lại

Giả sử ứng dụng có các node `:Post` với thuộc tính `id`, `title`, `category`, `createdAt`. Mỗi bài viết có mã duy nhất; hai bài viết có thể được tạo vào đúng cùng một thời điểm.

Chạy đoạn sau trong **cơ sở dữ liệu thực hành**:

```cypher
CREATE CONSTRAINT post_id_unique IF NOT EXISTS
FOR (p:Post) REQUIRE p.id IS UNIQUE;

UNWIND [
  {id: 'P101', title: 'Khởi đầu với Neo4j', category: 'Graph', createdAt: '2026-11-10T10:00:00Z'},
  {id: 'P102', title: 'Node và relationship', category: 'Graph', createdAt: '2026-11-09T09:00:00Z'},
  {id: 'P103', title: 'Đọc dữ liệu bằng Cypher', category: 'Graph', createdAt: '2026-11-09T09:00:00Z'},
  {id: 'P104', title: 'Tối ưu truy vấn', category: 'Graph', createdAt: '2026-11-08T13:00:00Z'},
  {id: 'P105', title: 'Java Driver', category: 'Java', createdAt: '2026-11-08T12:00:00Z'},
  {id: 'P106', title: 'Spring Data Neo4j', category: 'Java', createdAt: '2026-11-07T09:00:00Z'},
  {id: 'P107', title: 'Index và constraint', category: 'Graph', createdAt: '2026-11-06T10:00:00Z'},
  {id: 'P108', title: 'Vận hành Neo4j', category: 'Ops', createdAt: '2026-11-05T11:00:00Z'}
] AS item
MERGE (p:Post {id: item.id})
SET p.title = item.title,
    p.category = item.category,
    p.createdAt = datetime(item.createdAt);
```

`MERGE` dùng `id` để tránh nhân đôi node khi chạy lại dữ liệu mẫu; `SET` cập nhật các thuộc tính của bài viết đó. `datetime()` chuyển chuỗi ISO 8601 thành kiểu thời gian để việc sắp xếp phản ánh thứ tự thời điểm. **Không nên lưu ngày tháng theo chuỗi có định dạng tùy ý** nếu truy vấn cần so sánh thời gian chính xác.

Để kiểm tra dữ liệu:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

Với đúng tám node mẫu trên và chưa có node `:Post` khác, thứ tự là `P101, P102, P103, P104, P105, P106, P107, P108`. Hai bài `P102` và `P103` có cùng `createdAt`; mã bài viết quyết định thứ tự của chúng.

## 3. ORDER BY: sắp xếp một hay nhiều tiêu chí

### 3.1. ASC và DESC

`ASC` là tăng dần và cũng là hướng mặc định; `DESC` là giảm dần.

```cypher
// Mới nhất trước.
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

```cypher
// Mã bài viết tăng dần; viết ASC tường minh để dễ đọc.
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title
ORDER BY postId ASC;
```

Các tiêu chí được áp dụng **từ trái sang phải**: chỉ khi hai dòng bằng nhau theo tiêu chí đầu thì tiêu chí tiếp theo mới phân định thứ tự. Đây là điều quan trọng khi thiết kế phân trang ổn định.

### 3.2. Cần tiêu chí phân xử khi giá trị trùng nhau

Xem truy vấn sau:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC
LIMIT 2;
```

`P101` chắc chắn đứng trước các bài còn lại trong tập mẫu, nhưng `P102` và `P103` có cùng thời gian. Không có cơ sở để yêu cầu Neo4j luôn chọn một trong hai làm dòng thứ hai khi chỉ sắp xếp bằng `createdAt`. Nếu hai trang có ranh giới nằm giữa các giá trị trùng, có thể gặp bản ghi lặp hoặc thiếu ngay cả khi dữ liệu không đổi do thứ tự của nhóm bằng nhau chưa được xác định.

Thêm khóa phân xử duy nhất:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

Lúc này kết quả trong tập mẫu là `P101`, `P102`; dòng tiếp theo sẽ là `P103`. Thuộc tính `id` được ràng buộc duy nhất bằng constraint, phù hợp để cố định thứ tự. Trong dữ liệu thực tế, hãy dùng một khóa **duy nhất và không thay đổi** phù hợp với nghiệp vụ.

**Lưu ý:** Sắp xếp toàn phần giải quyết thứ tự của dữ liệu tại một thời điểm. Nó không ngăn các dòng di chuyển giữa các trang khi có bài viết mới, bản ghi bị xóa hoặc thay đổi giá trị sắp xếp; vấn đề này sẽ được giải quyết riêng ở phần phân trang bằng con trỏ.

### 3.3. Sắp xếp kết quả tổng hợp

`ORDER BY` có thể sắp xếp cả kết quả của `count()`, `sum()` hoặc biểu thức tính toán, không chỉ thuộc tính trực tiếp của node.

```cypher
MATCH (p:Post)
RETURN p.category AS category, count(*) AS totalPosts
ORDER BY totalPosts DESC, category ASC;
```

Trong tập mẫu, `Graph` có 5 bài, `Java` có 2 bài và `Ops` có 1 bài. Nếu phân trang **sau khi tổng hợp**, một dòng là một nhóm danh mục; `SKIP` và `LIMIT` lúc ấy áp dụng trên số **nhóm**, không phải số bài viết gốc.

### 3.4. Giá trị thiếu và các kiểu dữ liệu khác nhau

Nếu một số bài thiếu `createdAt`, cần xác định chính sách nghiệp vụ: loại khỏi danh sách, đặt cuối, hoặc dùng thời điểm mặc định. Ví dụ chỉ lấy bài có thời điểm tạo:

```cypher
MATCH (p:Post)
WHERE p.createdAt IS NOT NULL
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

Không nên phụ thuộc vào vị trí tình cờ của giá trị `null` trong một truy vấn mà nghiệp vụ chưa quy định rõ. Tránh trộn chuỗi, số và giá trị thời gian trong cùng thuộc tính cần sắp xếp: thứ tự giữa các kiểu không đồng nhất có thể đúng theo quy tắc Cypher nhưng không có ý nghĩa với người dùng. Với tiêu đề tiếng Việt, cần kiểm thử cách so sánh chuỗi/hoa thường theo yêu cầu sản phẩm; `ORDER BY` thông thường không thay cho bộ quy tắc sắp xếp ngôn ngữ tự nhiên chuyên dụng.

## 4. SKIP và LIMIT: phân trang theo vị trí (offset pagination)

### 4.1. Cơ chế hoạt động

`SKIP n` bỏ qua `n` dòng ở đầu tập đã được sắp xếp; `LIMIT m` giữ tối đa `m` dòng tiếp theo. Khi `SKIP` đứng sau `ORDER BY`, ứng dụng có thể truy cập trang số 1, 2, 3 với kích thước cố định.

Nếu người dùng chọn trang theo số bắt đầu từ 1:

```text
offset = (pageNumber - 1) * pageSize
```

Ví dụ `pageSize = 3` trên tám bài viết mẫu:

| Trang | `SKIP` | `LIMIT` | Mã bài viết trả về |
| ---: | ---: | ---: | --- |
| 1 | 0 | 3 | P101, P102, P103 |
| 2 | 3 | 3 | P104, P105, P106 |
| 3 | 6 | 3 | P107, P108 |
| 4 | 9 | 3 | Không có dòng nào |

Truy vấn của trang 2:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 3
LIMIT 3;
```

Không có `SKIP` thì `LIMIT 3` chỉ lấy ba dòng đầu của thứ tự sắp xếp. Không có `LIMIT` thì `SKIP 3` trả toàn bộ các dòng còn lại. `LIMIT 0` tạo kết quả rỗng; giá trị của `SKIP` và `LIMIT` phải là số nguyên không âm hợp lệ.

### 4.2. Dùng tham số thay vì ghép chuỗi truy vấn

Khi người dùng thay đổi số trang hoặc kích thước trang, truyền `offset` và `pageSize` bằng tham số Cypher:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

Ví dụ backend truyền `{offset: 3, pageSize: 3}` cho trang thứ hai. Tại ứng dụng, nên kiểm tra `pageNumber >= 1`, `pageSize >= 1`, đặt giới hạn trên cho `pageSize` và kiểm tra phép nhân khi tính `offset` để tránh tràn số hoặc yêu cầu trang quá lớn. Không nối trực tiếp dữ liệu đầu vào vào chuỗi Cypher.

Với bộ lọc, giữ cùng điều kiện trong tất cả các trang:

```cypher
MATCH (p:Post)
WHERE p.category = $category
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

Nếu `category = 'Graph'`, chỉ năm bài thuộc danh mục `Graph` tham gia sắp xếp và chia trang. Cần giữ cả **điều kiện lọc lẫn thứ tự sắp xếp** giống nhau giữa các lần lấy trang.

### 4.3. Đếm tổng số dòng để hiển thị số trang

`LIMIT` không tự trả về tổng số dòng phù hợp với bộ lọc. Nếu giao diện cần hiển thị “5 kết quả / 2 trang”, có thể chạy thêm truy vấn đếm:

```cypher
MATCH (p:Post)
WHERE p.category = $category
RETURN count(*) AS total;
```

Truy vấn đếm cần dùng **cùng bộ lọc** với truy vấn trang. Với `total = 5` và `pageSize = 3`, số trang là `ceil(5 / 3) = 2` ở phía ứng dụng. Hai truy vấn tách biệt có thể thấy hai trạng thái dữ liệu khác nhau nếu có ghi/xóa xảy ra giữa chúng; không nên mặc định tổng đếm và trang dữ liệu luôn cùng một snapshot.

Trong giao diện chỉ cần nút “Xem thêm”, có thể lấy `pageSize + 1` dòng, hiển thị `pageSize` dòng và dùng dòng dư để xác định có trang kế tiếp. Cách đó tránh một truy vấn `count(*)` trong nhiều tình huống, nhưng cũng không tự giải quyết sự thay đổi dữ liệu giữa các lần yêu cầu.

## 5. Thứ tự các clause thay đổi ý nghĩa kết quả

Trong Cypher, `WITH` tạo ranh giới trung gian cho các dòng; `ORDER BY`, `SKIP`, `LIMIT` áp dụng tại vị trí của chúng trong luồng truy vấn. Hai câu dưới đây có ý nghĩa khác nhau.

**Lấy ba bài mới nhất:**

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 3;
```

**Chọn ba bài bất kỳ trước, sau đó mới sắp xếp ba bài ấy:**

```cypher
MATCH (p:Post)
WITH p
LIMIT 3
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

Ở truy vấn thứ hai, `LIMIT` phía trước đã giảm tập dòng khi **chưa có thứ tự xác định**. `ORDER BY` phía sau không thể biến ba dòng đã chọn thành ba bài mới nhất của toàn bộ dữ liệu. Đây là lỗi rất phổ biến khi tách truy vấn thành nhiều `WITH`.

`WITH ... ORDER BY` cũng hữu ích khi cần chuẩn bị thứ tự cho bước tiếp theo. Chẳng hạn, `ORDER BY` trong `WITH` bảo đảm các dòng được chuyển tới clause liền sau theo thứ tự đã xác định; điều này đặc biệt quan trọng khi clause tiếp theo sử dụng phép tổng hợp nhạy với thứ tự như `collect()`.

### LIMIT đếm dòng kết quả, không đếm node riêng biệt

Nếu truy vấn mở rộng qua nhiều relationship, một node có thể xuất hiện ở nhiều dòng:

```cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(a:Author)-[:WROTE]->(p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 10;
```

Nếu một bài viết được khớp qua nhiều đường đi hoặc nhiều node `:Author`, kết quả có thể có nhiều dòng cùng `postId`. Khi yêu cầu là **10 bài viết khác nhau**, loại trùng trước khi sắp xếp và phân trang:

```cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(a:Author)-[:WROTE]->(p:Post)
WITH DISTINCT p
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 10;
```

Việc `DISTINCT` có thể làm tăng chi phí thực thi; chỉ dùng khi mẫu truy vấn thực sự có khả năng tạo nhiều dòng cho cùng một thực thể và yêu cầu cần loại trùng.

## 6. Nhược điểm của OFFSET khi dữ liệu lớn hoặc thay đổi liên tục

### 6.1. Trang sâu có thể đắt

Với `SKIP 100000 LIMIT 20`, cơ sở dữ liệu vẫn phải tìm và bỏ qua đủ các dòng đứng trước trang cần lấy, theo kế hoạch truy vấn được chọn. `LIMIT 20` **không có nghĩa toàn bộ truy vấn chỉ xử lý 20 dòng**. Khi có nhiều ứng viên phải sắp xếp, thao tác sort có thể tiêu tốn bộ nhớ và thời gian đáng kể.

Mức độ ảnh hưởng phụ thuộc chỉ mục, điều kiện lọc, kế hoạch thực thi và dữ liệu. Trước khi kết luận một truy vấn chậm do `SKIP`, hãy kiểm tra kế hoạch bằng `EXPLAIN` và chi phí thực tế bằng `PROFILE` trên môi trường thử nghiệm.

### 6.2. Bản ghi mới có thể làm lệch các trang

Giả sử `pageSize = 3` và trang 1 trả `P101, P102, P103`. Ngay sau đó, một bài `P109` có `createdAt` mới hơn tất cả được thêm vào. Trang 2 với `SKIP 3` lúc này bắt đầu tại `P103`, dẫn đến **lặp P103** dù mỗi truy vấn riêng lẻ đều có `ORDER BY` đầy đủ.

Tương tự, khi một bản ghi ở trang trước bị xóa hoặc thay đổi khóa sắp xếp, trang sau có thể bỏ qua dữ liệu. Sắp xếp bằng khóa duy nhất giúp ổn định thứ tự **trong cùng một trạng thái dữ liệu** nhưng không cố định trạng thái giữa các request riêng rẽ.

Nếu cần danh sách ít thay đổi và chuyển trực tiếp tới trang bất kỳ, offset pagination vẫn tiện lợi. Với luồng nội dung mới liên tục, tải lớn hoặc yêu cầu điều hướng theo “Xem tiếp”, hãy cân nhắc phân trang theo con trỏ.

## 7. Phân trang theo con trỏ (keyset/cursor pagination)

Thay vì nói “bỏ qua 1000 dòng”, ứng dụng truyền khóa của **dòng cuối đã xem** và yêu cầu những dòng đứng sau khóa đó trong cùng thứ tự sắp xếp.

Giả sử thứ tự được định nghĩa là:

```cypher
ORDER BY createdAt DESC, postId ASC
```

Nghĩa là thời gian giảm dần; nếu cùng thời gian thì mã tăng dần. Vì thế, một bài viết đứng **sau** dòng con trỏ khi:

1. `createdAt` của nó **nhỏ hơn** thời gian của con trỏ; hoặc
2. `createdAt` **bằng** thời gian của con trỏ và `postId` **lớn hơn** mã của con trỏ.

### 7.1. Trang đầu tiên

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $pageSize;
```

Với `$pageSize = 2`, kết quả là `P101, P102`. Ứng dụng lưu khóa của **dòng cuối**: `(createdAt = 2026-11-09T09:00:00Z, postId = 'P102')`.

### 7.2. Trang tiếp theo

```cypher
MATCH (p:Post)
WHERE p.createdAt < datetime($cursorCreatedAt)
   OR (p.createdAt = datetime($cursorCreatedAt) AND p.id > $cursorPostId)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $pageSize;
```

Ví dụ truyền:

```json
{
  "cursorCreatedAt": "2026-11-09T09:00:00Z",
  "cursorPostId": "P102",
  "pageSize": 2
}
```

Trang tiếp theo trả `P103, P104`. `P103` vẫn xuất hiện vì có cùng thời gian với `P102` nhưng mã lớn hơn. Nếu chỉ dùng điều kiện `p.createdAt < $cursorCreatedAt`, bài viết `P103` sẽ **bị bỏ sót**.

Những điểm cần nhớ:

- Con trỏ phải bao gồm **đủ các trường tạo thành thứ tự sắp xếp**; khi nhiều bài có cùng ngày tạo, không thể chỉ dùng ngày.
- Khi thay đổi bộ lọc hoặc thứ tự, con trỏ cũ có thể không còn phù hợp. API nên coi con trỏ là dữ liệu gắn với một cấu hình truy vấn cụ thể.
- Với các bài không có `createdAt`, cần chính sách riêng trước khi dùng phép so sánh trên; truy vấn mẫu giả định trường này luôn hiện diện và có kiểu `datetime`.
- Bản ghi mới được chèn **trước** con trỏ thường không làm những trang tiếp theo bị dịch như offset pagination. Tuy nhiên, nếu thuộc tính dùng sắp xếp của bản ghi đã có bị sửa, hoặc có các thao tác xóa/ghi khác, keyset vẫn không bảo đảm một snapshot bất biến.
- Keyset rất phù hợp với thao tác “Xem tiếp”; nhảy thẳng đến trang số 50 kém thuận tiện hơn `SKIP`.

### 7.3. Chọn giữa hai phương án

| Tiêu chí | Offset (`SKIP`) | Keyset (con trỏ) |
| --- | --- | --- |
| Đi đến một trang số bất kỳ | Dễ | Cần trạng thái hoặc cơ chế bổ sung |
| Truy vấn ban đầu | Đơn giản | Cần điều kiện so sánh theo khóa sắp xếp |
| Trang rất sâu | Có thể phải bỏ qua nhiều dòng | Không phải bỏ qua toàn bộ các dòng trước con trỏ |
| Dữ liệu thêm mới ở đầu danh sách | Dễ lặp hoặc bỏ sót khi sang trang | Thường ổn định hơn nếu khóa sắp xếp không thay đổi |
| Điều kiện cần | `ORDER BY` nhất quán | `ORDER BY` nhất quán, khóa phân xử duy nhất, cursor phù hợp |
| Trường hợp điển hình | Bảng quản trị cần số trang | News feed, danh sách giao dịch, “Load more” |

## 8. Tối ưu truy vấn có ORDER BY, SKIP, LIMIT

### 8.1. Dùng điều kiện lọc trước khi sắp xếp tập lớn

Khi chỉ cần bài `Graph`, đưa điều kiện vào trước `RETURN`:

```cypher
MATCH (p:Post)
WHERE p.category = 'Graph'
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 10;
```

Lọc sớm giúp giảm số ứng viên cần sắp xếp, tùy kế hoạch thực thi. Chỉ trả về những thuộc tính cần thiết và tránh mở rộng relationship không phục vụ màn hình đang tải.

### 8.2. Tìm hiểu chỉ mục thích hợp

Ràng buộc duy nhất trên `:Post(id)` đã tạo ở bước chuẩn bị bảo vệ dữ liệu và hỗ trợ truy cập theo `id`. Với truy vấn thường tìm bài theo thời điểm, có thể đánh giá range index:

```cypher
CREATE RANGE INDEX post_created_at IF NOT EXISTS
FOR (p:Post) ON (p.createdAt);
```

Nếu hệ thống thường lọc theo `category` và sắp xếp theo thời điểm, một chỉ mục kết hợp có thể đáng thử:

```cypher
CREATE RANGE INDEX post_category_created_at IF NOT EXISTS
FOR (p:Post) ON (p.category, p.createdAt);
```

**Không suy ra** cứ có index là Neo4j chắc chắn loại bỏ bước sắp xếp. Khả năng dùng chỉ mục phụ thuộc điều kiện lọc, cách viết `ORDER BY`, hướng sắp xếp, thứ tự các trường, phiên bản Neo4j và bộ tối ưu truy vấn. Trong ví dụ, tiêu chí phụ `postId ASC` còn phải được thỏa mãn, nên cần kiểm tra kế hoạch thực tế.

### 8.3. EXPLAIN và PROFILE

```cypher
EXPLAIN
MATCH (p:Post)
WHERE p.category = $category
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

`EXPLAIN` cho biết kế hoạch dự kiến mà không thực thi để trả kết quả. Khi cần đo trên môi trường phù hợp:

```cypher
PROFILE
MATCH (p:Post)
WHERE p.category = $category
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

Quan sát số hàng vào/ra, lượng truy cập dữ liệu, các bước mở rộng quan hệ nếu có, và operator như `Sort`, `Top`, `Skip` hoặc các toán tử dùng index. Tên và cách chọn operator có thể khác giữa các phiên bản. So sánh độ trễ tại nhiều giá trị `offset`, kích thước trang và phân phối dữ liệu trước khi kết luận tối ưu.

Một truy vấn có `LIMIT 20` vẫn có thể tốn nhiều tài nguyên nếu phải tạo hàng triệu dòng trung gian từ đường đi hoặc sort một tập rất lớn rồi mới lấy 20 dòng. **Giới hạn số dòng trả về không phải giới hạn cứng cho toàn bộ công việc truy vấn.**

## 9. Tích hợp phân trang với Java Driver và Spring Data Neo4j

Với **Neo4j Java Driver**, truyền các giá trị phân trang qua parameter để giữ truy vấn rõ ràng và tái sử dụng được. Ví dụ Java dưới đây giả định ứng dụng đã khởi tạo `Driver driver`:

```java
int pageNumber = 2; // Đếm trang từ 1.
int pageSize = 3;

if (pageNumber < 1 || pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("Invalid pagination request");
}

long offset = Math.multiplyExact((long) pageNumber - 1L, (long) pageSize);

String cypher = """
    MATCH (p:Post)
    RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
    ORDER BY createdAt DESC, postId ASC
    SKIP $offset
    LIMIT $pageSize
    """;

var result = driver.executableQuery(cypher)
    .withParameters(java.util.Map.of("offset", offset, "pageSize", pageSize))
    .execute();

for (var record : result.records()) {
    System.out.println(record.get("postId").asString());
}
```

Ví dụ sử dụng API `executableQuery` của Java Driver 5.x và Java hỗ trợ text block. Ứng dụng thực cần quản lý vòng đời `Driver`, cấu hình kết nối, xử lý lỗi và quyền truy cập phù hợp.

Với **Spring Data Neo4j**, có thể dùng `Pageable`/`Sort` khi repository method và mapping thực tế hỗ trợ, hoặc viết `@Query` rõ ràng cho trường hợp cần duyệt quan hệ và thứ tự riêng. Không nên mặc định một truy vấn Cypher tùy chỉnh có cùng hành vi phân trang/đếm như truy vấn repository được sinh tự động; phải kiểm tra cách SDN xử lý `Pageable`, phép đếm và việc loại trùng node sau ánh xạ. Đặc biệt, hãy kiểm tra trên dữ liệu có nhiều relationship để tránh thấy số lượng dòng Cypher khác số thực thể mong muốn.

Với API cursor pagination, backend có thể trả `items` và `nextCursor` (khóa từ dòng cuối), thay cho `pageNumber`. Nếu cursor được đưa ra ngoài cho client, cần mã hóa/kiểm tra tính hợp lệ của cursor và gắn nó với bộ lọc, hướng sắp xếp và quyền truy cập của yêu cầu.

## 10. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Cùng truy vấn, thứ tự dòng thay đổi | Không có `ORDER BY` | Đặt thứ tự tường minh ở kết quả cần hiển thị |
| Dòng bị lặp giữa các trang dù dữ liệu không đổi | Sắp xếp bằng thuộc tính không duy nhất | Thêm khóa phân xử duy nhất như `postId` |
| Có bài mới, trang sau lặp bài cũ | Offset dịch khi tập dữ liệu thay đổi | Xem xét keyset pagination hoặc snapshot phù hợp |
| Truy vấn “top 10” sai kết quả | Dùng `LIMIT` trước bước `ORDER BY` | Sắp xếp trên tập ứng viên đầy đủ rồi mới giới hạn |
| Tưởng lấy 10 node nhưng chỉ có 6 node khác nhau | Một node khớp nhiều đường đi, tạo nhiều dòng | Dùng `WITH DISTINCT p` trước khi chia trang nếu phù hợp |
| Trang sau quá chậm | `SKIP` rất lớn, sort nhiều dòng hoặc duyệt mạng rộng | Lọc sớm, xem `PROFILE`, cân nhắc cursor và index |
| Tổng số trang khác số thực thể hiển thị | Truy vấn đếm khác bộ lọc hoặc có nhiều dòng trên một node | Đồng nhất điều kiện; cân nhắc `count(DISTINCT p)` theo ý nghĩa nghiệp vụ |
| Sắp xếp theo ngày không đúng | Thuộc tính lưu sai kiểu hoặc nhiều kiểu | Chuẩn hóa sang kiểu thời gian nhất quán |

## 11. Bài tập thực hành

### Bài 1: Từ mới đến cũ

Viết truy vấn lấy bốn bài mới nhất thuộc danh mục `Graph`, trả về `postId`, `title`, `createdAt`. Nếu hai bài có cùng thời gian, bài có `postId` nhỏ hơn đứng trước.

<details>
<summary>Gợi ý lời giải</summary>

```cypher
MATCH (p:Post)
WHERE p.category = 'Graph'
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 4;
```

Với dữ liệu mẫu: `P101`, `P102`, `P103`, `P104`.

</details>

### Bài 2: Chia trang theo số

Một trang chứa hai bài. Hãy truy vấn trang số 3 của toàn bộ danh sách, sắp xếp từ mới đến cũ và dùng `postId` để phân xử.

<details>
<summary>Gợi ý lời giải</summary>

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 4
LIMIT 2;
```

Với dữ liệu mẫu: `P105`, `P106`.

</details>

### Bài 3: Chia trang bằng con trỏ khi trùng thời gian

Trang đầu kích thước hai gồm `P101`, `P102`. Hãy viết điều kiện `WHERE` để lấy trang kế, đồng thời giải thích vì sao chỉ dùng `createdAt < cursorCreatedAt` là chưa đủ.

<details>
<summary>Gợi ý lời giải</summary>

```cypher
MATCH (p:Post)
WHERE p.createdAt < datetime('2026-11-09T09:00:00Z')
   OR (p.createdAt = datetime('2026-11-09T09:00:00Z') AND p.id > 'P102')
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

Kết quả là `P103`, `P104`. `P103` có thời gian trùng con trỏ, nên phải so sánh thêm `id` để không bỏ sót.

</details>

### Bài 4: Chọn chiến lược cho yêu cầu thực tế

Ứng dụng A có bảng quản trị 2.000 sản phẩm với điều hướng trực tiếp đến trang bất kỳ. Ứng dụng B có luồng sự kiện tăng liên tục và chỉ có nút “Xem thêm”. Chọn `SKIP/LIMIT` hay keyset cho từng ứng dụng. Nêu ít nhất hai phép đo cần làm trước khi triển khai.

**Gợi ý:** A có thể bắt đầu bằng offset nếu benchmark đạt yêu cầu. B thường thích hợp keyset hơn. Với cả hai, cần đo độ trễ trang đầu/trang sâu, chi phí sort hoặc duyệt, đồng thời thử kịch bản thêm/xóa dữ liệu khi đang chuyển trang.

## 12. Tự kiểm tra trước khi đưa vào ứng dụng

- [ ] Truy vấn có `ORDER BY` tường minh và đủ khóa để phân xử các dòng cùng giá trị.
- [ ] `SKIP`/`LIMIT` được áp dụng **sau** bước sắp xếp đúng đối tượng cần chia trang.
- [ ] Các tham số trang được kiểm tra và giới hạn tại backend.
- [ ] Bộ lọc, thứ tự, truy vấn đếm và khóa con trỏ nhất quán với nhau.
- [ ] Đã xử lý khả năng một node xuất hiện trên nhiều đường đi nếu cần phân trang các node duy nhất.
- [ ] Đã đo truy vấn ở trang sâu và thử tình huống dữ liệu thay đổi khi chuyển trang.
- [ ] Các index/constraint được lựa chọn theo `EXPLAIN`/`PROFILE` và dữ liệu thực tế.

## Kết luận

`ORDER BY` xác định thứ tự các dòng, `SKIP` bỏ qua một đoạn đầu và `LIMIT` giới hạn số dòng lấy tiếp. Để phân trang Neo4j đáng tin cậy, cần **thứ tự có khóa phân xử duy nhất**, hiểu rằng `LIMIT` giới hạn **dòng** chứ không tự loại node trùng, và chọn giữa offset với cursor theo cách người dùng di chuyển trong danh sách. Khi dữ liệu tăng hoặc biến động mạnh, hiệu năng và tính ổn định phải được kiểm chứng bằng truy vấn thực tế cùng kế hoạch chạy của Neo4j.
