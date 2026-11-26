# Chia trang ổn định và lựa chọn chiến lược cho tập dữ liệu lớn trong Neo4j

## Mục tiêu học tập

Neo4j là cơ sở dữ liệu **property graph**: truy vấn Cypher khớp mẫu node, relationship hoặc đường đi, sau đó xử lý **các dòng kết quả**. Màn hình danh sách bài viết, sản phẩm, lịch sử giao dịch hoặc những node có quan hệ với người dùng đều cần chia trang. Khi tập dữ liệu lớn hoặc thay đổi liên tục, một truy vấn trả đúng 20 dòng vẫn có thể vừa **chậm** vừa khiến người dùng thấy dòng bị lặp hay bỏ sót.

Bài thuộc chương **Tối ưu truy vấn** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`. Trọng tâm là chọn cách chia trang phù hợp với dữ liệu liên kết của Neo4j, từ `ORDER BY`, `SKIP` và `LIMIT` đến **keyset/cursor pagination**, index, `EXPLAIN`/`PROFILE` và tích hợp Java Driver/Spring Data Neo4j.

Sau bài này, bạn có thể:

1. Thiết lập **thứ tự xác định** bằng khóa sắp xếp và khóa phân xử duy nhất.
2. Phân biệt lỗi do **thứ tự không xác định**, do **dữ liệu thay đổi** và do **nhân dòng qua relationship**.
3. Viết offset pagination và keyset pagination đúng chiều so sánh, kể cả khi nhiều node cùng thời gian.
4. Chọn chiến lược theo nhu cầu đi đến trang bất kỳ, cuộn xem tiếp, kích thước tập dữ liệu và tần suất ghi.
5. Đánh giá kế hoạch thực thi, thiết kế index, hạn chế các bước mở rộng đồ thị và trả cursor an toàn cho client.

> **Phiên bản:** Ví dụ dùng cú pháp phổ biến của Neo4j Cypher 5 và Java Driver 5.x. Khả năng tận dụng index để phục vụ `ORDER BY` và tên operator trong kế hoạch thực thi có thể khác giữa phiên bản, cấu hình và loại truy vấn; luôn kiểm chứng trên hệ thống đang dùng.

## 1. Bản chất của phân trang ổn định

Giả sử tập bài viết gồm:

```text
:Post {tenantId, id, title, published, createdAt}
    ↑
[:LIKED]
    │
:User {id}
```

Ứng dụng muốn hiển thị bài mới nhất của một tenant, mỗi trang 2 hoặc 20 bài. Trước khi chọn `SKIP` hay cursor, phải giải quyết **ba câu hỏi khác nhau**:

- **Thứ tự:** Hai bài có cùng `createdAt` thì bài nào đứng trước?
- **Đơn vị phân trang:** Một dòng của truy vấn là **một bài viết** hay một lần khớp relationship `LIKED`?
- **Ảnh chụp dữ liệu:** Nếu giữa hai lần gọi API có bài mới, sửa bài hoặc xóa bài, danh sách có còn giống thời điểm tải trang đầu không?

Hình dung thứ tự danh sách:

```text
ORDER BY createdAt DESC, id ASC

P101 (11-24 10:00)
P102 (11-23 09:00)  ┐ cùng createdAt
P103 (11-23 09:00)  ┘ id phân xử
P104 (11-22 08:00)
P105 (11-21 08:00)
...
```

**Thứ tự xác định** là điều kiện cần để phân trang đáng tin cậy. Nó chưa bảo đảm một **snapshot bất biến giữa các request** nếu cơ sở dữ liệu bị ghi trong lúc người dùng chuyển trang.

## 2. Chuẩn bị dữ liệu thực hành có khóa duy nhất

Chạy trên cơ sở dữ liệu thực hành. Khóa định danh bài viết ở ví dụ là cặp `(tenantId, id)`, vì mã bài viết có thể trùng giữa các tenant.

```cypher
CREATE CONSTRAINT post_tenant_id_unique IF NOT EXISTS
FOR (p:Post) REQUIRE (p.tenantId, p.id) IS UNIQUE;
```

Tạo tám bài cho tenant `T1` và một bài riêng của tenant `T2`. `MERGE` theo khóa giúp tránh nhân đôi node khi chạy lại; `SET` cập nhật dữ liệu mẫu:

```cypher
UNWIND [
  {tenant: 'T1', id: 'P101', ts: '2026-11-24T10:00:00Z', title: 'Tổng quan graph'},
  {tenant: 'T1', id: 'P102', ts: '2026-11-23T09:00:00Z', title: 'Node và nhãn'},
  {tenant: 'T1', id: 'P103', ts: '2026-11-23T09:00:00Z', title: 'Relationship'},
  {tenant: 'T1', id: 'P104', ts: '2026-11-22T08:00:00Z', title: 'Cypher cơ bản'},
  {tenant: 'T1', id: 'P105', ts: '2026-11-21T08:00:00Z', title: 'Index'},
  {tenant: 'T1', id: 'P106', ts: '2026-11-20T08:00:00Z', title: 'Constraint'},
  {tenant: 'T1', id: 'P107', ts: '2026-11-19T08:00:00Z', title: 'Java Driver'},
  {tenant: 'T1', id: 'P108', ts: '2026-11-18T08:00:00Z', title: 'Spring Data'},
  {tenant: 'T2', id: 'P101', ts: '2026-11-25T10:00:00Z', title: 'Tenant khác'}
] AS item
MERGE (p:Post {tenantId: item.tenant, id: item.id})
SET p.title = item.title,
    p.published = true,
    p.createdAt = datetime(item.ts);
```

Kiểm tra danh sách của `T1`:

```cypher
MATCH (p:Post {tenantId: 'T1'})
WHERE p.published = true
RETURN p.id AS postId, p.createdAt AS createdAt, p.title AS title
ORDER BY createdAt DESC, postId ASC;
```

Với chỉ dữ liệu mẫu của `T1`, thứ tự là `P101, P102, P103, P104, P105, P106, P107, P108`. `P102` và `P103` có cùng `createdAt`. Nếu có dữ liệu cũ trong cơ sở dữ liệu thử nghiệm, lọc chính xác theo tenant/mã bài trước khi đối chiếu kết quả.

## 3. Bước bắt buộc: xác định thứ tự toàn phần

### 3.1. ORDER BY một trường có thể chưa đủ

```cypher
MATCH (p:Post {tenantId: 'T1'})
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC
LIMIT 2;
```

Trong tập mẫu, `P101` luôn có thời gian mới nhất, còn `P102` và `P103` bằng nhau. Khi chỉ xét `createdAt`, Neo4j **không bắt buộc** chọn thứ tự nào giữa hai bài bằng nhau. Điều này càng quan trọng nếu ranh giới hai trang nằm ngay giữa các phần tử có cùng khóa.

Thêm khóa phân xử:

```cypher
MATCH (p:Post {tenantId: 'T1'})
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

Lúc này trang hai dòng đầu là `P101, P102`; `P103` đứng ngay sau `P102`. Cần chọn `id` có **giá trị duy nhất trong tập đã lọc** và không thay đổi trong suốt vòng đời bản ghi. Nếu phân trang qua nhiều tenant cùng lúc, `id` riêng lẻ chưa chắc đủ duy nhất; phải bổ sung khóa khác để phân xử.

### 3.2. Trường dùng trong ORDER BY cần nhất quán

- Dùng cùng kiểu dữ liệu cho một property, ví dụ `createdAt` lưu bằng `datetime`; đừng trộn chuỗi ngày giờ có định dạng khác nhau với kiểu thời gian.
- Quyết định xử lý property thiếu. Ví dụ bài học chỉ phân trang bản ghi có `createdAt IS NOT NULL`; nếu nghiệp vụ cần hiển thị những bài thiếu thời điểm, phải thiết kế chính sách sắp xếp và cursor riêng.
- Khóa phân xử cần **ổn định**. `elementId(p)` đại diện định danh kỹ thuật của thực thể, không nên dùng như khóa cursor nghiệp vụ bền vững; ưu tiên một ID nghiệp vụ có unique constraint.
- Giữ nguyên bộ lọc, hướng sắp xếp và khóa phân xử giữa những lần lấy trang.

## 4. Offset pagination: ORDER BY, SKIP và LIMIT

Cách truyền thống là bỏ qua `offset = (pageNumber - 1) * pageSize` dòng đầu sau khi sắp xếp.

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true
  AND p.createdAt IS NOT NULL
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

Với `tenantId = 'T1'` và `pageSize = 2`, trên tập mẫu ban đầu:

| Trang | `offset` | Dữ liệu trả về |
| ---: | ---: | --- |
| 1 | 0 | `P101, P102` |
| 2 | 2 | `P103, P104` |
| 3 | 4 | `P105, P106` |
| 4 | 6 | `P107, P108` |

**Ưu điểm:** dễ hiểu, dễ đi thẳng đến một trang bất kỳ; thích hợp bảng quản trị có số trang và tập dữ liệu tương đối nhỏ hoặc ít biến động.

**Hai giới hạn khác nhau:**

1. **Chi phí trang sâu.** `SKIP 100000 LIMIT 20` không có nghĩa Neo4j chỉ phải đọc 20 dòng: hệ thống có thể phải duyệt/bỏ qua rất nhiều dòng ứng viên, thậm chí sắp xếp một tập lớn tùy kế hoạch.
2. **Độ ổn định khi dữ liệu thay đổi.** Bài mới được chèn đầu danh sách làm dịch vị trí của các bản ghi, dù `ORDER BY` có khóa phân xử đầy đủ.

### Ví dụ dịch trang khi thêm hoặc xóa dữ liệu

Giả sử trang đầu `P101, P102` đã được hiển thị. Trước khi người dùng gọi trang 2, thêm bài `P099` với `createdAt` mới hơn `P101`. Danh sách mới là:

```text
P099, P101, P102, P103, P104, ...
                  ↑ SKIP 2 bắt đầu tại P102
```

Trang 2 theo `SKIP 2 LIMIT 2` trở thành `P102, P103`: **P102 bị lặp** dù ứng dụng đã thấy nó ở trang 1. Nếu một dòng của trang đầu bị xóa, offset có thể **bỏ sót** một dòng ở trang sau.

Trước khi gửi yêu cầu tới Neo4j, backend phải kiểm tra `pageNumber >= 1`, `pageSize` trong giới hạn được cho phép, phép nhân tính `offset` không tràn số, và tất cả giá trị được truyền bằng **parameter**. Khi số trang lớn, việc giới hạn độ sâu offset hoặc đề nghị cơ chế cursor là một lựa chọn vận hành hợp lý.

## 5. Keyset/cursor pagination: phân trang theo giá trị khóa

Keyset lưu khóa của **dòng cuối thực sự trả cho client** trong trang hiện tại. Trang tiếp theo không hỏi “bỏ qua N dòng”, mà hỏi “những dòng đứng **sau khóa này** trong cùng thứ tự”.

### 5.1. Trang đầu

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true
  AND p.createdAt IS NOT NULL
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

Với `tenantId = 'T1'`, `pageSize = 2`, backend có thể dùng `fetchSize = 3` (xem mục 5.3). Hai dòng **được hiển thị** là `P101` và `P102`, từ đó cursor lưu:

```json
{
  "createdAt": "2026-11-23T09:00:00Z",
  "postId": "P102"
}
```

`createdAt` là thời điểm của **P102**, không phải thời điểm hệ thống phát hành cursor. Kết quả `P103` được lấy thêm chỉ để kiểm tra còn trang sau.

### 5.2. Trang tiếp theo với DESC và ASC kết hợp

Thứ tự đang dùng:

```cypher
ORDER BY createdAt DESC, postId ASC
```

Một dòng ở **sau** cursor khi:

1. `createdAt` của nó **nhỏ hơn** `createdAt` trong cursor, **hoặc**
2. `createdAt` bằng nhau, nhưng `postId` **lớn hơn** `postId` trong cursor.

Truy vấn:

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true
  AND p.createdAt IS NOT NULL
  AND (
    p.createdAt < datetime($cursorCreatedAt)
    OR (
      p.createdAt = datetime($cursorCreatedAt)
      AND p.id > $cursorPostId
    )
  )
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

Tham số minh họa:

```json
{
  "tenantId": "T1",
  "cursorCreatedAt": "2026-11-23T09:00:00Z",
  "cursorPostId": "P102",
  "fetchSize": 3
}
```

Hai dòng **được hiển thị** là `P103, P104`, dù `P103` có thời điểm bằng `P102`. Nếu chỉ lọc `p.createdAt < datetime($cursorCreatedAt)`, `P103` bị **bỏ sót**.

> **Cẩn thận chiều so sánh:** Sắp xếp `createdAt DESC` thì trang sau dùng `createdAt < cursorCreatedAt`. Riêng khóa phụ `id ASC` thì khi bằng thời điểm, trang sau dùng `id > cursorId`. Đổi hướng sắp xếp đồng nghĩa phải đổi toán tử của phần điều kiện tương ứng.

| Thứ tự | Điều kiện trang sau (với khóa `time` và `id`) |
| --- | --- |
| `time DESC, id ASC` | `time < t OR (time = t AND id > i)` |
| `time ASC, id ASC` | `time > t OR (time = t AND id > i)` |
| `time DESC, id DESC` | `time < t OR (time = t AND id < i)` |

Nếu nhiều hơn hai trường tạo thứ tự, điều kiện keyset phải xét **đủ các tiền tố bằng nhau** rồi mới so sánh trường tiếp theo; thiếu một trường có thể khiến bản ghi bị lặp hoặc bỏ sót.

### 5.3. hasNext và nextCursor bằng LIMIT pageSize + 1

Một API thường trả:

```json
{
  "items": ["P103", "P104"],
  "hasNext": true,
  "nextCursor": "<opaque-token>"
}
```

Cách xử lý:

1. Backend giới hạn `pageSize`, tính `fetchSize = pageSize + 1` và thực thi truy vấn với tham số.
2. Nếu có hơn `pageSize` dòng, đặt `hasNext = true`; **chỉ trả về** `pageSize` dòng đầu.
3. Tạo `nextCursor` từ **dòng cuối được trả về**, không phải dòng dư dùng để kiểm tra `hasNext`.
4. Nếu không có dòng dư, `hasNext = false`. Thông thường có thể trả `nextCursor = null` để báo đã hết dữ liệu.

Cách này tránh phải chạy thêm `count(*)` cho mỗi lần bấm “Xem thêm”. Tuy nhiên `hasNext` phản ánh thời điểm của **truy vấn hiện tại**; dữ liệu có thể thay đổi ngay sau đó.

## 6. Ổn định trước thay đổi không đồng nghĩa snapshot bất biến

### 6.1. Chèn bài mới

Sau khi trang đầu trả `P101, P102`, nếu thêm `P099` với thời gian mới hơn, offset trang 2 có thể lặp `P102`. Keyset vẫn hỏi các dòng có thứ tự **sau P102**, nên trong ví dụ sẽ trả `P103, P104`. Đây là lợi thế lớn đối với feed có dữ liệu mới liên tục.

Nhưng nếu chèn **bài được đặt thời gian cũ** sau cursor, trang tiếp theo vẫn có thể xuất hiện bài mới đó. Keyset không đóng băng toàn bộ tập dữ liệu.

### 6.2. Xóa hoặc sửa khóa sắp xếp

- Nếu `P103` bị xóa trước khi tải trang sau, keyset sẽ không trả P103; nó không thể hiển thị một node đã mất.
- Nếu `createdAt` của một bài bị sửa để di chuyển qua ranh giới cursor, bài đó có thể được thấy hai lần hoặc bị bỏ qua.
- Nếu trường lọc như `published` hoặc `tenantId` thay đổi, một bài có thể vào/ra danh sách giữa các lần lấy trang.

Để hạn chế vấn đề, chọn khóa sắp xếp **không thay đổi** như thời điểm tạo thực tế cộng ID bất biến. Không dùng `lastModifiedAt` nếu giao diện yêu cầu một lần duyệt không lặp và thuộc tính ấy liên tục thay đổi.

### 6.3. Khi thật sự cần một snapshot nhất quán

Với báo cáo tài chính, đối soát, xuất dữ liệu hoặc yêu cầu “đọc đúng tập tại mốc T”, chỉ dùng cursor thường **chưa đủ**. Có thể cần một trong các thiết kế nghiệp vụ:

- Ghi nhận một **phiên bản/snapshot ID** và truy vấn trên dữ liệu đã được version hóa.
- Tạo một danh sách ID đã cố định cho một job xuất dữ liệu, rồi duyệt danh sách ấy theo checkpoint.
- Lưu một mốc `asOf` và quy định dữ liệu nào được phép thay đổi trước/sau mốc ấy; việc lọc `createdAt <= asOf` chỉ giữ đúng snapshot nếu mô hình dữ liệu bảo đảm những thay đổi khác không làm sai kết quả.

**Bookmark** của Neo4j hỗ trợ phối hợp thứ tự quan sát giao dịch giữa các session; nó không tự biến hàng loạt HTTP request thành **một snapshot đọc bất biến**. Một transaction đọc dài qua nhiều trang cũng có chi phí và ràng buộc vận hành, không nên mặc định dùng cho toàn bộ phiên duyệt của người dùng.

## 7. Chia trang node trước khi mở rộng relationship

Trong property graph, một node có thể khớp nhiều relationship và vì thế xuất hiện trên nhiều **dòng**. `SKIP` và `LIMIT` luôn áp dụng trên **dòng truy vấn tại vị trí của chúng**, không mặc nhiên tính số node `:Post` khác nhau.

Ví dụ người dùng thích nhiều bài:

```cypher
MATCH (u:User)-[:LIKED]->(p:Post {tenantId: $tenantId})
WHERE p.published = true
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 20;
```

Nếu một bài nhận 100 lượt thích, có thể có 100 dòng cùng `postId` và chiếm hết `LIMIT 20`. Nếu nghiệp vụ muốn phân trang **20 bài khác nhau**, cần loại trùng **trước khi** phân trang:

```cypher
MATCH (:User)-[:LIKED]->(p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
WITH DISTINCT p
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

`DISTINCT` có thể tốn chi phí, nhất là khi fan-out relationship lớn. Nếu mục tiêu là “mọi bài đã xuất bản của tenant cùng số lượt thích”, một cách thường tốt hơn là **chọn các node của trang trước**, rồi mới mở rộng:

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
WITH p
ORDER BY p.createdAt DESC, p.id ASC
SKIP $offset
LIMIT $pageSize
OPTIONAL MATCH (:User)-[r:LIKED]->(p)
WITH p, count(r) AS likes
RETURN p.id AS postId, p.title AS title,
       p.createdAt AS createdAt, likes
ORDER BY createdAt DESC, postId ASC;
```

Thứ tự thực thi ý nghĩa nghiệp vụ:

1. Chọn node `Post` theo bộ lọc và thứ tự.
2. Giữ tối đa `pageSize` node sau khi skip.
3. Chỉ sau đó mới tìm các relationship `LIKED` và tính tổng cho **những node đã nằm trong trang**.
4. `ORDER BY` cuối cùng tái khẳng định thứ tự hiển thị sau bước tổng hợp; đừng phụ thuộc vào thứ tự ngẫu nhiên của phép mở rộng.

Nếu muốn dùng **keyset**, thay `SKIP $offset` bằng điều kiện cursor ở trước `WITH ... ORDER BY ... LIMIT`. Khi nhu cầu chỉ là sắp xếp theo `likeCount`, việc tính count cho tất cả bài **trước** khi chia trang có thể rất đắt. Có thể cân nhắc một property `likeCount` được cập nhật và kiểm soát đồng bộ theo nghiệp vụ, rồi index hóa/sắp xếp trên property ấy; đổi lại phải quản lý tính nhất quán của giá trị tổng hợp.

## 8. Index và kế hoạch thực thi trên tập dữ liệu lớn

### 8.1. Thiết kế index theo bộ lọc và thứ tự

Unique constraint `(tenantId, id)` ở phần chuẩn bị bảo vệ định danh. Với truy vấn feed luôn lọc `tenantId`, `published` và sắp xếp `createdAt`, có thể **đánh giá thử** range index kết hợp:

```cypher
CREATE RANGE INDEX post_feed_sort IF NOT EXISTS
FOR (p:Post)
ON (p.tenantId, p.published, p.createdAt, p.id);
```

Một index chỉ hữu ích nếu bộ tối ưu có thể dùng được trong truy vấn cụ thể. Chẳng hạn, `ORDER BY createdAt DESC, id ASC` có **hướng hỗn hợp**; dù có composite index, không được khẳng định Neo4j sẽ loại bỏ bước sort hoặc luôn seek chính xác tới cursor. Điều kiện `OR` trong keyset, độ chọn lọc của `tenantId`, trường `published` và phân phối `createdAt` đều ảnh hưởng kế hoạch.

Nếu ứng dụng hỗ trợ nhiều kiểu sắp xếp (mới nhất, phổ biến nhất, theo tên), không nên lập index cho mọi hoán vị mà không có số liệu: index chiếm dung lượng và làm tăng chi phí khi ghi.

### 8.2. EXPLAIN trước, PROFILE để đo

Để xem kế hoạch dự kiến **mà không chạy truy vấn**:

```cypher
EXPLAIN
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

Để kiểm tra thực tế trên dữ liệu thử nghiệm:

```cypher
PROFILE
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
  AND (
    p.createdAt < datetime($cursorCreatedAt)
    OR (
      p.createdAt = datetime($cursorCreatedAt)
      AND p.id > $cursorPostId
    )
  )
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

Chú ý:

- Operator `NodeIndexSeek`/`NodeIndexScan`, `Sort`/`Top`/`Skip`, số hàng vào/ra và số lần đọc dữ liệu (DB Hits); tên operator phụ thuộc phiên bản và kế hoạch.
- Mức độ mở rộng relationship, số dòng trung gian và việc tạo danh sách `collect()` nếu query có thao tác graph.
- Chênh lệch giữa trang đầu và trang sâu (ví dụ `offset = 0` so với `offset = 100000`), với cùng `pageSize` và bộ lọc.
- Thời gian ở p50/p95/p99, lượng bộ nhớ, tốc độ trả kết quả và mức đồng thời. Kết luận chỉ đáng tin cậy với dữ liệu, index và cấu hình gần thực tế.

Keyset thường tránh **chi phí bỏ qua các trang trước** của offset, nhưng không mặc nhiên `O(pageSize)`. Nếu bộ tối ưu vẫn phải đọc hoặc sort một tập ứng viên rất lớn, keyset cũng có thể chậm. Hãy đo riêng điều kiện cursor và lựa chọn index trước khi cam kết hiệu năng.

### 8.3. Đếm tổng và “trang sâu”

Nếu giao diện offset cần số trang, nó thường chạy thêm một truy vấn:

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
RETURN count(p) AS totalPosts;
```

Truy vấn đếm phải dùng **cùng bộ lọc** với truy vấn dữ liệu. Nếu mẫu graph có thể nhân dòng, đôi khi phải dùng `count(DISTINCT p)` để đếm đúng số node. Đếm lớn và liên tục cũng tốn tài nguyên; với feed cursor, thường chỉ cần `hasNext` và tránh đếm trên mỗi lần tải.

Kết quả `totalPosts` của một request và kết quả trang của request khác có thể khác nhau khi dữ liệu bị ghi liên tục. Muốn con số chặt chẽ tại cùng thời điểm, cần thiết kế transaction/snapshot phù hợp hoặc chấp nhận tổng số **gần đúng/thay đổi** tùy yêu cầu giao diện.

## 9. Thiết kế API cursor và tích hợp Java

### 9.1. Cursor là dữ liệu ứng dụng phải xác thực

Cursor tối thiểu chứa `createdAt` và `postId` của dòng cuối; một API thực tế còn nên gắn:

```json
{
  "v": 1,
  "sort": "createdAt_desc_id_asc",
  "tenantId": "T1",
  "filtersHash": "hash-of-canonical-filters",
  "createdAt": "2026-11-23T09:00:00Z",
  "postId": "P102"
}
```

Đây là **payload minh họa trước khi đóng gói**, không phải token dùng trực tiếp. Có thể mã hóa bằng Base64URL và ký bằng HMAC, hoặc dùng một ID tham chiếu tới dữ liệu cursor phía server. **Base64 đơn thuần không bảo đảm tính toàn vẹn**. Backend phải xác thực/đối chiếu tenant, quyền truy cập, cấu hình lọc, kiểu giá trị và phiên bản cursor; không tin tenant hoặc điều kiện bảo mật chỉ vì chúng nằm trong token.

Khi cursor không hợp lệ hoặc không tương ứng bộ lọc/sort hiện tại, trả lỗi rõ ràng để client tải lại trang đầu. Nếu người dùng được chọn trường sắp xếp, ánh xạ từ một **allowlist cố định** sang câu Cypher đã kiểm soát; không ghép thẳng tên trường hay mệnh đề từ đầu vào người dùng.

### 9.2. Java Driver: truyền tham số và lấy thêm một dòng

Ví dụ Java 17+, Neo4j Java Driver 5.x. `Driver` đã được khởi tạo ở cấu hình ứng dụng; ví dụ chưa bao gồm kết nối, xác thực hoặc đóng gói cursor:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class PostPaging {
    private static final String NEXT_PAGE = """
        MATCH (p:Post {tenantId: $tenantId})
        WHERE p.published = true
          AND p.createdAt IS NOT NULL
          AND (
            p.createdAt < datetime($cursorCreatedAt)
            OR (
              p.createdAt = datetime($cursorCreatedAt)
              AND p.id > $cursorPostId
            )
          )
        RETURN p.id AS postId, p.title AS title,
               p.createdAt AS createdAt
        ORDER BY createdAt DESC, postId ASC
        LIMIT $fetchSize
        """;

    public static List<Record> readNext(
        Driver driver, String tenantId,
        String cursorCreatedAt, String cursorPostId,
        int pageSize
    ) {
        if (tenantId == null || tenantId.isBlank()
            || cursorCreatedAt == null || cursorPostId == null
            || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid cursor request");
        }

        Map<String, Object> parameters = Map.of(
            "tenantId", tenantId,
            "cursorCreatedAt", cursorCreatedAt,
            "cursorPostId", cursorPostId,
            "fetchSize", pageSize + 1
        );

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(
                tx -> tx.run(NEXT_PAGE, parameters).list()
            );
        }
    }
}
```

Sau khi `readNext` trả về, ứng dụng dùng tối đa `pageSize` record để tạo DTO, so sánh số record với `pageSize` để tính `hasNext` và tạo cursor từ record cuối **được trả cho client**. `Record` của driver có thể chuyển sang kiểu ngày giờ thích hợp, rồi mã hóa theo chuẩn API thống nhất.

Với trang đầu, dùng một query tương tự **không có điều kiện cursor**. Truy vấn `RETURN` chọn rõ thuộc tính cần thiết thay vì trả cả node lớn; driver vẫn cần đọc kết quả về ứng dụng, nên kích thước dữ liệu trả về cũng ảnh hưởng độ trễ.

### 9.3. Spring Data Neo4j

`Pageable`/`Sort` thuận tiện với trang theo số ở những repository method được SDN hỗ trợ. `Page` có thể yêu cầu truy vấn đếm bổ sung, còn `Slice` thường phù hợp hơn khi chỉ cần biết còn trang sau; hãy kiểm tra hành vi đúng với repository/phiên bản SDN đang dùng.

Đối với keyset nhiều trường hoặc query graph có fan-out, có thể viết Cypher rõ ràng bằng `@Query` hoặc `Neo4jClient`, truyền tham số cursor, rồi xây dựng DTO và `nextCursor` ở tầng service. Không nên giả định cách SDN ánh xạ node và relationship tự loại trùng đúng với số **dòng Cypher** dùng để `SKIP`/`LIMIT`. Kiểm thử riêng trên node có nhiều relationship.

## 10. Chọn chiến lược theo tình huống

| Yêu cầu | Offset với `SKIP/LIMIT` | Keyset/cursor |
| --- | --- | --- |
| Bấm thẳng “Trang 57” | Thuận tiện, có `offset` | Không thuận tiện nếu chưa có cursor trung gian |
| Luồng “Xem thêm” liên tục | Dùng được nhưng dễ lệch khi có bản ghi mới | Thường phù hợp hơn |
| Trang rất sâu của dữ liệu lớn | Có thể phải đọc/bỏ qua nhiều dòng | Có thể tốt hơn khi lọc và index hỗ trợ |
| Cần tổng số trang chính xác | Cần truy vấn đếm theo bộ lọc | Thường không cần, dùng `hasNext` |
| Thứ tự có khóa trùng | Phải thêm khóa phân xử | Phải thêm khóa phân xử **và** lưu nó trong cursor |
| Khóa sắp xếp bị sửa giữa các request | Có nguy cơ lặp/bỏ sót | Vẫn có nguy cơ lặp/bỏ sót |
| Cần snapshot tuyệt đối qua nhiều request | Cần cơ chế snapshot/version riêng | Cũng cần cơ chế snapshot/version riêng |
| Phải phân trang node sau mở rộng graph | Loại trùng hoặc chọn node trước | Tương tự; quan trọng là paginate đúng thực thể |

Gợi ý lựa chọn:

1. **Bảng quản trị có vài nghìn dòng, dữ liệu ít đổi, phải đi đến trang bất kỳ:** bắt đầu bằng offset, đo trang sâu và chi phí truy vấn đếm.
2. **Feed có hàng triệu bài, chèn mới liên tục, điều hướng “Xem thêm”:** ưu tiên keyset với `createdAt` bất biến + ID duy nhất; xác minh index/plan.
3. **Danh sách sắp xếp theo điểm tính từ nhiều relationship:** xem xét tính trước chỉ số, hạn chế số node cần mở rộng, hoặc triển khai index/materialized property phù hợp; không mặc định một query tổng hợp toàn graph sẽ nhanh.
4. **Xuất báo cáo hoặc đối soát cần đúng tập dữ liệu ở một mốc:** ưu tiên snapshot/version/checkpoint theo nghiệp vụ, sau đó mới quyết định offset hay keyset.

## 11. Lỗi thường gặp và phương án sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Cùng dữ liệu nhưng trang có dòng lúc hiện lúc mất | `ORDER BY` chỉ trên trường trùng | Thêm khóa duy nhất làm tie-breaker |
| Sau khi có bài mới, trang sau lặp bài trang trước | Offset bị dịch | Dùng keyset cho luồng “Xem thêm” nếu phù hợp |
| Bỏ sót P103 khi P102 và P103 cùng thời gian | Cursor chỉ so sánh `createdAt` | So sánh tiếp `id > cursorId` khi thời gian bằng |
| Truy vấn trả 20 dòng nhưng chỉ có 3 bài khác nhau | Fan-out relationship nhân dòng | `WITH DISTINCT p` hoặc paginate node trước khi mở rộng |
| Trang sâu tăng độ trễ mạnh | `SKIP` lớn, scan/sort nhiều ứng viên | Đo `PROFILE`, thử keyset và index đúng bộ lọc |
| Keyset vẫn chậm dù `LIMIT 20` | Kế hoạch phải sort/scan nhiều bản ghi | Kiểm tra operator, lựa chọn index và tính chọn lọc |
| Bài di chuyển qua lại giữa các trang | Thuộc tính sắp xếp thay đổi | Dùng khóa bất biến hoặc version/snapshot |
| Cursor cũ dùng được cho bộ lọc khác | Cursor không gắn với filter/sort | Xác thực và version hóa token |
| Số trang hiển thị sai | Truy vấn đếm khác bộ lọc hoặc đếm theo dòng graph | Dùng cùng bộ lọc và `count(DISTINCT p)` khi cần |
| Có index nhưng vẫn phải Sort | Query/hướng ORDER BY không phù hợp index | Xem kế hoạch thực tế, thử index thích hợp |

## 12. Bài thực hành có hướng dẫn

### Bài 1: Dự đoán trang offset

Với dữ liệu `T1`, `pageSize = 3` và thứ tự `createdAt DESC, id ASC`, hãy viết truy vấn trang 2 và cho biết kết quả.

```cypher
MATCH (p:Post {tenantId: 'T1'})
WHERE p.published = true
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 3
LIMIT 3;
```

**Đáp án:** `P104, P105, P106` trên tập dữ liệu mẫu ban đầu.

### Bài 2: Viết cursor khi hai bài cùng thời gian

Trang đầu gồm `P101, P102`. Viết truy vấn trang tiếp theo để vẫn giữ `P103`.

```cypher
MATCH (p:Post {tenantId: 'T1'})
WHERE p.published = true
  AND (
    p.createdAt < datetime('2026-11-23T09:00:00Z')
    OR (
      p.createdAt = datetime('2026-11-23T09:00:00Z')
      AND p.id > 'P102'
    )
  )
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

**Đáp án:** `P103, P104`. Điều kiện bằng thời gian và lớn hơn ID của cursor giúp giữ P103.

### Bài 3: Phân trang trên node hay relationship?

Một bài có 50 relationship `LIKED`. Query `MATCH (u)-[:LIKED]->(p) ... LIMIT 10` có đảm bảo mười bài khác nhau không? Hãy sửa bằng hai bước.

**Gợi ý:** trước hết `MATCH (p:Post) ... WITH p ORDER BY ... LIMIT 10`, sau đó `OPTIONAL MATCH` lấy những relationship cần hiển thị cho **mười node đó**, cuối cùng `RETURN ... ORDER BY`. Nếu điều kiện “được user thích” là bắt buộc, xác định tập node thỏa điều kiện trước rồi dùng `WITH DISTINCT p` để không nhân dòng.

### Bài 4: Chọn chiến lược

Hệ thống A hiển thị danh sách 3.000 tài khoản quản trị và phải nhảy thẳng đến trang 35. Hệ thống B có 5 triệu sự kiện, chỉ có nút “Load more” và có bản ghi mới mỗi giây. Hệ thống C xuất một báo cáo phải phản ánh đúng dữ liệu tại thời điểm khóa sổ.

**Gợi ý đáp án:** A có thể thử offset và đo trang sâu; B thường phù hợp keyset với khóa sắp xếp bất biến; C cần snapshot/version hoặc danh sách ID cố định để bảo đảm tập dữ liệu, dù sau đó dùng cách chia trang nào.

### Bài 5: Đo hiệu năng thay vì đoán

Chạy `EXPLAIN` và `PROFILE` (trên môi trường thử nghiệm) với trang đầu, trang sâu và keyset có cursor hợp lệ. Ghi lại:

- Số dòng vào/ra ở các operator.
- Có hay không operator sort lớn, index seek/scan và các bước mở rộng relationship.
- Độ trễ, throughput, DB Hits, khác biệt khi tăng `offset`.

Giải thích vì sao một query có `LIMIT 20` vẫn có thể xử lý nhiều dòng hơn 20.

## 13. Checklist trước khi triển khai

- [ ] `ORDER BY` xác định đầy đủ thứ tự, có khóa phân xử duy nhất và ổn định.
- [ ] Các trường trong cursor có kiểu dữ liệu, timezone và chính sách `null` nhất quán.
- [ ] Bộ lọc tenant/quyền truy cập áp dụng trên mọi trang; cursor được kiểm tra và gắn với filter/sort.
- [ ] Trang sau keyset có toán tử so sánh phù hợp từng chiều `ASC`/`DESC`.
- [ ] `LIMIT pageSize+1` được tính phía backend; cursor lấy từ dòng cuối **hiển thị**.
- [ ] `SKIP`/`LIMIT` áp dụng trên đúng đơn vị cần paginate: node, relationship hay dòng tổng hợp.
- [ ] Đã thử thêm mới, xóa, sửa thuộc tính sắp xếp và thay đổi bộ lọc giữa các request.
- [ ] Đã quyết định có thực sự cần snapshot bất biến hay chỉ cần duyệt ổn định hơn.
- [ ] Đã đo `EXPLAIN`/`PROFILE` với dữ liệu, index và trang sâu đại diện.
- [ ] Truy vấn đếm và dữ liệu có cùng bộ lọc; chỉ đếm khi UI thực sự cần.

## Kết luận

Phân trang ổn định trong Neo4j bắt đầu từ việc **xác định thứ tự toàn phần trên đúng thực thể cần phân trang**. `SKIP/LIMIT` đơn giản và tiện đi đến trang số bất kỳ, nhưng chi phí có thể tăng ở trang sâu và vị trí dễ bị dịch khi dữ liệu thay đổi. **Keyset/cursor** dựa trên khóa của dòng cuối thường hợp lý hơn cho luồng lớn, thay đổi liên tục; nó đòi hỏi so sánh đúng nhiều trường, xác thực cursor và kiểm chứng rằng query/index thực sự hạn chế lượng công việc. Cả hai cách đều cần mô hình snapshot riêng nếu nghiệp vụ yêu cầu tập dữ liệu bất biến qua nhiều request. Cuối cùng, `EXPLAIN`, `PROFILE` và kiểm thử fan-out relationship giúp chọn chiến lược dựa trên hành vi thực tế của đồ thị.

### Tài liệu tham khảo

- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
- [Neo4j Cypher Manual — SKIP](https://neo4j.com/docs/cypher-manual/current/clauses/skip/)
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/)
- [Neo4j Cypher Manual — Search-performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
