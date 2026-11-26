# Giảm collect lớn, sắp xếp không cần thiết và dữ liệu trả về trong Neo4j

Khi tối ưu truy vấn Cypher, nhiều người chỉ tìm cách thêm index để tăng tốc `MATCH`. Nhưng ngay cả khi Neo4j tìm đúng node rất nhanh, một truy vấn vẫn có thể chậm vì **tạo quá nhiều hàng trung gian**, **gom danh sách quá lớn bằng `collect()`**, **sắp xếp quá nhiều phần tử bằng `ORDER BY`** hoặc **chuyển về ứng dụng những node, relationship và property không cần thiết**.

Bài học thuộc chương **Tối ưu truy vấn** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Trọng tâm là thay đổi **cách tạo và trả kết quả** khi làm việc với property graph Neo4j: chỉ mở rộng phần đồ thị cần thiết, gom nhóm có kiểm soát, sắp xếp đúng chỗ và giảm kích thước payload. Những nguyên tắc này áp dụng cho truy vấn Cypher trực tiếp, ứng dụng dùng Neo4j Java Driver và Spring Data Neo4j.

## 1. Ba nguồn chi phí dễ bị bỏ qua

| Vấn đề | Dấu hiệu trong truy vấn | Hệ quả thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| **`collect()` lớn** | `collect(a)` hoặc `collect(path)` trên hàng nghìn/hàng triệu kết quả | Danh sách lớn được vật hóa để tổng hợp, tăng bộ nhớ của truy vấn và ứng dụng | Giới hạn phạm vi trước khi gom; dùng `count()`/`EXISTS` nếu không cần danh sách; trả từng hàng nếu có thể |
| **Sắp xếp không cần thiết** | `ORDER BY` ở nhiều chặng, hoặc sắp xếp toàn tập rồi không dùng thứ tự | Thêm công việc cho `Sort`/`Top`, có thể tăng bộ nhớ và độ trễ | Chỉ sắp khi yêu cầu đầu ra hay lựa chọn top-k đòi hỏi; dùng index phù hợp nếu có |
| **Trả quá nhiều dữ liệu** | `RETURN a`, `RETURN *`, `RETURN path` khi màn hình chỉ cần vài trường | Tăng tuần tự hóa dữ liệu, băng thông, cấp phát và ánh xạ đối tượng phía ứng dụng | Trả projection nhỏ, phân trang, chỉ lấy property và số liệu cần thiết |

Cần phân biệt **số hàng** (*cardinality*) với **độ rộng mỗi hàng**. Một truy vấn trả 20 hàng chứa cả nội dung tài liệu dài và toàn bộ đường đi vẫn có thể nặng hơn 200 hàng chỉ gồm mã và tiêu đề.

Một hình dung đơn giản:

```text
Neo4j tìm node
     ↓
Mở rộng relationship → số hàng có thể tăng
     ↓
Filter / DISTINCT / aggregation → có thể phải xử lý lượng trung gian lớn
     ↓
Sort / LIMIT → có thể giữ hoặc sắp nhiều hàng
     ↓
RETURN → tạo payload qua Bolt, Driver, ứng dụng
```

`LIMIT` cuối cùng chỉ đảm bảo **số hàng kết quả cuối**, không tự động chứng minh mọi bước trước đó xử lý ít dữ liệu. Neo4j có thể tối ưu một số kế hoạch để dừng sớm, nhưng phải nhìn execution plan để biết có áp dụng được không.

## 2. Bộ dữ liệu thử: người dùng, bài viết, tag và bình luận

Chạy `CREATE` sau **một lần trên database thử nghiệm**. Các label và relationship type có tiền tố `OptDemo` nhằm tách ví dụ với dữ liệu sản phẩm. Không chạy lại `CREATE` trong cùng database nếu muốn tái hiện chính xác các số đếm.

```cypher
CREATE
  (an:OptDemoUser {userId: 'U01', name: 'An'}),
  (binh:OptDemoUser {userId: 'U02', name: 'Bình'}),
  (chi:OptDemoUser {userId: 'U03', name: 'Chi'}),
  (a1:OptDemoArticle {
    articleId: 'A101', title: 'Neo4j và Cypher',
    body: 'Nội dung dài của bài A101...',
    published: true, publishedAt: date('2026-01-10')
  }),
  (a2:OptDemoArticle {
    articleId: 'A102', title: 'Java Driver',
    body: 'Nội dung dài của bài A102...',
    published: true, publishedAt: date('2026-01-09')
  }),
  (a3:OptDemoArticle {
    articleId: 'A103', title: 'Mô hình đồ thị',
    body: 'Nội dung dài của bài A103...',
    published: true, publishedAt: date('2026-01-08')
  }),
  (a4:OptDemoArticle {
    articleId: 'A104', title: 'Bài viết nháp',
    body: 'Nội dung dài của bài A104...',
    published: false, publishedAt: date('2026-01-07')
  }),
  (t1:OptDemoTag {name: 'Neo4j'}),
  (t2:OptDemoTag {name: 'Cypher'}),
  (t3:OptDemoTag {name: 'Java'}),
  (c1:OptDemoComment {commentId: 'C01', text: 'Bình luận 1'}),
  (c2:OptDemoComment {commentId: 'C02', text: 'Bình luận 2'}),
  (c3:OptDemoComment {commentId: 'C03', text: 'Bình luận 3'}),
  (c4:OptDemoComment {commentId: 'C04', text: 'Bình luận 4'}),
  (c5:OptDemoComment {commentId: 'C05', text: 'Bình luận 5'}),
  (an)-[:OPT_DEMO_LIKED]->(a1),
  (an)-[:OPT_DEMO_LIKED]->(a2),
  (binh)-[:OPT_DEMO_LIKED]->(a1),
  (a1)-[:OPT_DEMO_TAGGED]->(t1),
  (a1)-[:OPT_DEMO_TAGGED]->(t2),
  (a2)-[:OPT_DEMO_TAGGED]->(t3),
  (a3)-[:OPT_DEMO_TAGGED]->(t1),
  (a1)-[:OPT_DEMO_HAS_COMMENT]->(c1),
  (a1)-[:OPT_DEMO_HAS_COMMENT]->(c2),
  (a1)-[:OPT_DEMO_HAS_COMMENT]->(c3),
  (a2)-[:OPT_DEMO_HAS_COMMENT]->(c4),
  (a3)-[:OPT_DEMO_HAS_COMMENT]->(c5);
```

Sơ đồ phần dữ liệu liên quan:

```text
An ────────LIKED────────► A101 ──TAGGED────► Neo4j, Cypher
  └────────LIKED────────► A102 ──TAGGED────► Java
Bình ──────LIKED────────► A101
Chi ───────(chưa thích bài nào)

A101 ──HAS_COMMENT─────► C01, C02, C03
A102 ──HAS_COMMENT─────► C04
A103 ──HAS_COMMENT─────► C05
A104 ──(không có tag/bình luận)
```

Trong ví dụ, An thích 2 bài, Bình thích 1 bài, Chi không thích bài nào; A101 có **2 tag và 3 bình luận**. Những nhánh một-nhiều này sẽ cho thấy vì sao lượng dữ liệu trung gian có thể tăng nhanh.

## 3. Nhìn thấy cardinality tăng trước khi collect

Xét truy vấn tìm người đã thích bài viết, cùng tag và bình luận của bài:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
RETURN u.userId AS userId, a.articleId AS articleId,
       t.name AS tag, c.commentId AS commentId
ORDER BY userId, articleId, tag, commentId;
```

Theo dõi số hàng trong bộ dữ liệu mẫu:

| Chặng | An | Bình | Chi | Tổng |
| --- | ---: | ---: | ---: | ---: |
| `MATCH user→liked→article` | 2 | 1 | 0 | **3** |
| `OPTIONAL MATCH article→tag` | 3 | 2 | 0 | **5** |
| `OPTIONAL MATCH article→comment` | 7 | 6 | 0 | **13** |

Với A101, mỗi người thích bài đó sẽ sinh `2 tag × 3 bình luận = 6` hàng. Từ **3 lượt thích** ban đầu, truy vấn sinh **13 hàng** khi ghép hai nhánh độc lập. Nếu viết tiếp `collect(DISTINCT t.name)` và `collect(DISTINCT c.commentId)`, số hàng kết quả cuối có thể giảm, nhưng **các tổ hợp trung gian đã được tạo**.

Đếm từng chặng để tự kiểm chứng:

```cypher
// 3 hàng: lượt thích
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
RETURN count(*) AS rows;
```

```cypher
// 5 hàng: mỗi lượt thích mở rộng thành các tag
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
RETURN count(*) AS rows;
```

```cypher
// 13 hàng: cùng lúc mở rộng cả tag và bình luận
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
RETURN count(*) AS rows;
```

**Bài học quan trọng:** tối ưu `collect` không chỉ là làm danh sách ngắn hơn; còn phải tránh sinh những tổ hợp không cần thiết trước bước tổng hợp.

## 4. Chỉ dùng collect khi thực sự cần danh sách

### 4.1. Anti-pattern: gom toàn bộ node

Giả sử API danh sách bài viết chỉ hiển thị tiêu đề và ngày xuất bản. Truy vấn sau gom **toàn bộ node** thành một danh sách duy nhất:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
WITH collect(a) AS articles
RETURN articles;
```

Với 3 bài đã xuất bản của dữ liệu mẫu, truy vấn vẫn chạy được, nhưng khi số bài tăng lên hàng triệu, `collect(a)` tạo một collection có quy mô tương ứng. Việc kết quả chỉ có **một hàng chứa list** không chứng minh nó nhẹ: list đó giữ tham chiếu đến mọi node được gom, và khi trả về ứng dụng cần truyền/đọc một lượng dữ liệu lớn.

Nếu chỉ cần danh sách trang đầu, hãy trả **mỗi bài một hàng với ít property**, và giới hạn số bài:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT 20;
```

Giá trị `LIMIT 20` ở đây là **yêu cầu của trang kết quả**, không phải giới hạn áp tùy tiện cho câu hỏi “lấy tất cả bài”. Nếu sản phẩm thực sự cần xuất toàn bộ dữ liệu, nên chia thành các lô có kiểm soát hoặc xử lý dòng kết quả theo luồng, tùy mục tiêu.

### 4.2. Chỉ cần số lượng? Dùng count

```cypher
// Không cần gom cả danh sách bài để đếm
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN count(*) AS publishedCount;
```

Kết quả là **3**. So với `size(collect(a))`, `count(*)` diễn đạt trực tiếp nhu cầu đếm mà không tạo danh sách node trong kết quả.

Đừng quên lựa chọn đơn vị đếm:

- `count(*)` đếm số hàng.
- `count(a)` đếm số giá trị `a` khác `null`.
- `count(DISTINCT a)` đếm node `a` khác nhau nếu một node xuất hiện trên nhiều hàng sau khi mở rộng quan hệ.

Nếu `MATCH` đã nhân hàng theo tag hoặc bình luận, `count(*)` có thể **không** còn là số bài viết.

### 4.3. Chỉ cần biết có tồn tại? Dùng EXISTS

Câu hỏi “bài viết có ít nhất một bình luận không?” không cần danh sách bình luận:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
  AND EXISTS {
    MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(:OptDemoComment)
  }
RETURN a.articleId AS articleId, a.title AS title
ORDER BY articleId;
```

Kết quả có **A101, A102, A103**, mỗi bài một hàng. Thay vì mở rộng mọi bình luận rồi `collect()` hoặc `DISTINCT` để khử bản sao, điều kiện tồn tại thể hiện rõ mục tiêu của truy vấn.

Với Cypher 5 hỗ trợ `COUNT` subquery, khi cần **số bình luận của từng bài** có thể viết:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       COUNT {
         (a)-[:OPT_DEMO_HAS_COMMENT]->(:OptDemoComment)
       } AS commentCount
ORDER BY articleId;
```

Kết quả tương ứng là **A101: 3**, **A102: 1**, **A103: 1**. `COUNT { ... }` trả một số trên mỗi bài, không cần mang toàn bộ node bình luận thành list. Nếu phiên bản Cypher cũ không hỗ trợ count subquery, có thể thay bằng `OPTIONAL MATCH` + `count(c)` với khóa nhóm thích hợp.

## 5. Nếu cần danh sách con, gom sau khi thu hẹp tập cha

Giả sử giao diện chỉ muốn **hai bài mới nhất An đã thích**, kèm các tag của từng bài. Một cách dễ gây lãng phí là mở rộng tất cả tag, gom mọi thứ, rồi mới cắt danh sách trong ứng dụng.

Thay vào đó, **chọn hai bài trước**, sau đó mới lấy tag:

```cypher
MATCH (:OptDemoUser {userId: 'U01'})
      -[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH DISTINCT a
ORDER BY a.publishedAt DESC, a.articleId ASC
LIMIT 2
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
WITH a, collect(t.name) AS tags
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt,
       tags
ORDER BY publishedAt DESC, articleId ASC;
```

Kết quả có 2 hàng: A101 với `['Neo4j','Cypher']` (thứ tự phần tử không được đảm bảo khi không sắp trước `collect`) và A102 với `['Java']`. Ngay cả với bài không có tag, `OPTIONAL MATCH` vẫn giữ bài, còn `collect(null)` cho danh sách rỗng.

**Vì sao giới hạn đúng chỗ quan trọng?** Nếu đặt `LIMIT 2` **sau khi mở rộng tag**, giới hạn đó áp trên **hàng chứa cặp bài–tag**, không phải “hai bài”. A101 có thể chiếm cả hai hàng, khiến A102 biến mất. Để giới hạn **số thực thể cha**, hãy thu hẹp tập `a` trước khi mở rộng quan hệ con.

`DISTINCT a` trong ví dụ bảo vệ trường hợp một bài được ghép nhiều lần ở bước trước. Dùng `DISTINCT` cũng có chi phí; nếu mô hình và câu `MATCH` đảm bảo mỗi bài chỉ xuất hiện một lần, có thể loại bỏ nó sau khi kiểm chứng.

### 5.1. Tránh tạo tích tổ hợp giữa nhiều danh sách con

Khi một bài có 2 tag và 3 bình luận, lấy đồng thời hai nhánh trong cùng một pipeline có thể sinh **6 hàng**. Nếu chỉ cần danh sách tag và **số bình luận**, giữ hai việc độc lập:

```cypher
MATCH (a:OptDemoArticle {articleId: 'A101'})
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
WITH a, collect(t.name) AS tags
RETURN a.articleId AS articleId,
       tags,
       COUNT {
         (a)-[:OPT_DEMO_HAS_COMMENT]->(:OptDemoComment)
       } AS commentCount;
```

Câu trên không mở rộng các bình luận thành từng hàng, nên tránh nhân tập tag với tập bình luận. Kết quả **một hàng**: tag của A101 và `commentCount = 3`.

Nếu cả hai danh sách đều cần thiết, có thể **tổng hợp từng nhánh riêng** rồi kết hợp chúng theo bài. Với Neo4j 5, ví dụ dùng subquery có biến ngữ cảnh:

```cypher
MATCH (a:OptDemoArticle {articleId: 'A101'})
CALL {
  WITH a
  OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
  RETURN collect(t.name) AS tags
}
CALL {
  WITH a
  OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
  RETURN collect(c.commentId) AS commentIds
}
RETURN a.articleId AS articleId, tags, commentIds;
```

Mỗi nhánh gom kết quả riêng rồi trả một danh sách cho mỗi bài; không cần 2×3 tổ hợp tag–comment. Dạng `CALL { WITH a ... }` dùng cú pháp import biến tương thích với nhiều bản Neo4j 5; các phiên bản Neo4j mới còn hỗ trợ dạng truyền biến bằng scope clause `CALL (a) { ... }`. Khi tối ưu, xem lại execution plan vì subquery cũng có chi phí thực thi.

## 6. Khi nào DISTINCT giúp, khi nào chỉ che triệu chứng?

`DISTINCT` có ích nếu nghiệp vụ cần **các node duy nhất**. Ví dụ:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
RETURN DISTINCT a.articleId AS articleId
ORDER BY articleId;
```

Kết quả chỉ có **A101** và **A102** dù A101 được hai người thích. Tuy nhiên, nếu truy vấn đã mở rộng cả tag và comment rồi mới `DISTINCT a`, Neo4j vẫn có thể phải xử lý rất nhiều tổ hợp trước khi loại trùng.

Hãy hỏi tại sao có trùng:

1. Một node có nhiều relationship hợp lệ nên xuất hiện nhiều lần? Nếu cần node duy nhất, `DISTINCT` phù hợp.
2. Có **hai nhánh độc lập** bị ghép tạo tích tổ hợp? Hãy gom mỗi nhánh riêng hoặc chỉ kiểm tra `EXISTS`/`COUNT`.
3. Các mẫu không có biến/điều kiện liên kết? Xem lại `CartesianProduct` trong execution plan.
4. Một relationship bị lặp trong dữ liệu? Phải giải quyết mô hình/constraint trước khi mặc nhiên khử trùng ở mọi truy vấn.

**Không nên dùng `DISTINCT` như biện pháp chữa hiệu năng mặc định.** Nó có thể làm thay đổi ngữ nghĩa nếu nghiệp vụ thực sự cần đếm số lượt khớp hoặc quan hệ song song.

## 7. Chỉ sắp xếp khi thứ tự có ý nghĩa

`ORDER BY` cần thiết khi yêu cầu nghiệp vụ muốn thứ tự xác định, chẳng hạn bài mới nhất, danh sách theo tên, top sản phẩm được quan tâm hoặc pagination. Nhưng mỗi lần yêu cầu sắp xếp có thể thêm chi phí CPU và bộ nhớ.

Ví dụ, nếu chỉ cần đếm số người đã thích mỗi bài, **không cần sắp theo tên người trước khi tổng hợp**:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH a, count(u) AS likeCount
RETURN a.articleId AS articleId, likeCount;
```

Nếu màn hình thật sự yêu cầu bài được thích nhiều nhất, hãy **sắp xếp sau khi đã gom nhóm**, rồi giới hạn:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH a, count(u) AS likeCount
RETURN a.articleId AS articleId,
       a.title AS title,
       likeCount
ORDER BY likeCount DESC, articleId ASC
LIMIT 10;
```

Ở bộ dữ liệu mẫu, A101 có **2 lượt thích**, A102 có **1 lượt thích**. Sắp xếp **hai hàng tổng hợp** rẻ hơn về quy mô so với cố sắp xếp toàn bộ các lượt thích, dù trên dữ liệu nhỏ khác biệt gần như không đáng kể.

### 7.1. ORDER BY kết hợp LIMIT: top-k, không phải lúc nào cũng sort toàn bộ

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT 2;
```

Một kế hoạch có thể dùng `Top` hoặc cơ chế top-k để giữ những ứng viên tốt nhất thay vì sắp xếp đầy đủ; nếu có index phù hợp với thứ tự và bộ lọc, planner đôi khi còn tận dụng thứ tự từ index. **Không được mặc định rằng chỉ thêm `LIMIT` sẽ tránh mọi thao tác đọc/sort**. Dùng `EXPLAIN` và `PROFILE` để kiểm tra.

Khi **không có `ORDER BY`**, tập kết quả áp `LIMIT` không có thứ tự xác định. Điều này có thể chấp nhận nếu nghiệp vụ chỉ cần một số phần tử bất kỳ, nhưng **không phù hợp** cho “mới nhất” hoặc phân trang ổn định.

### 7.2. Đặt ORDER BY đúng vị trí

Một lệnh sắp xếp đặt giữa các bước mở rộng lớn có thể bị mất ý nghĩa sau khi tạo nhiều hàng mới. Những chỗ thường hợp lý là:

- **Trước `LIMIT`** để chọn đúng top-k đối tượng theo tiêu chí.
- **Sau `Aggregation`** nếu tiêu chí sắp xếp là kết quả tổng hợp như `likeCount`.
- **Cuối `RETURN`** nếu khách hàng cần kết quả trình bày theo thứ tự.
- **Trước `collect()`** khi cần thứ tự phần tử danh sách, và bảo đảm thứ tự đến bước tổng hợp trực tiếp.

Ví dụ cần tag sắp theo tên trước khi gom:

```cypher
MATCH (a:OptDemoArticle {articleId: 'A101'})
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
WITH a, t
ORDER BY t.name ASC
RETURN a.articleId AS articleId,
       collect(t.name) AS orderedTags;
```

`ORDER BY` của `WITH` cung cấp thứ tự hàng cho bước tổng hợp ngay sau đó; danh sách dự kiến là `['Cypher', 'Neo4j']`. Với dữ liệu phức tạp hơn, cần đánh giá liệu yêu cầu thứ tự trong danh sách có thật sự cần thiết hay có thể sắp ở giao diện trên danh sách đã được giới hạn.

## 8. Phân trang để tránh gom và trả toàn bộ kết quả

Trong ứng dụng web, người dùng thường chỉ xem một số bản ghi mỗi lần. Phân trang giảm dữ liệu được gửi về, giảm công việc ánh xạ DTO và cho phép giao diện phản hồi nhanh hơn.

### 8.1. Trang đơn giản bằng SKIP và LIMIT

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP $offset
LIMIT $pageSize;
```

Bind `$offset` và `$pageSize` từ ứng dụng, ví dụ `offset = 0` và `pageSize = 20`. Dùng **khóa phụ ổn định** `articleId` khi hai bài có cùng `publishedAt` để tránh thay đổi thứ tự không rõ ràng.

Khi `offset` rất lớn, database vẫn có thể cần xử lý hoặc bỏ qua nhiều hàng trước trang mong muốn. `SKIP 100000 LIMIT 20` thường không rẻ như `SKIP 0 LIMIT 20`; nên đo với dữ liệu thật. Bản ghi mới chèn giữa các lần đọc có thể làm kết quả trang `SKIP` lặp hoặc bỏ sót.

### 8.2. Keyset (cursor) pagination khi tập dữ liệu lớn

Với thứ tự `publishedAt DESC, articleId ASC`, có thể dùng cặp giá trị cuối của trang trước làm cursor:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
  AND (
    a.publishedAt < date($cursorDate)
    OR (
      a.publishedAt = date($cursorDate)
      AND a.articleId > $cursorId
    )
  )
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT $pageSize;
```

Ví dụ `$cursorDate` là chuỗi ISO `'2026-01-10'`, `$cursorId = 'A101'`; truy vấn sẽ lấy những bài đứng **sau** A101 trong thứ tự đã thống nhất. Trang đầu không có cursor nên dùng truy vấn không có điều kiện cursor, rồi ghi lại `publishedAt` và `articleId` cuối cùng của trang làm cursor tiếp theo.

**Điều kiện:** khóa sắp xếp phải đủ ổn định và có giá trị cho mọi bản ghi thuộc phạm vi; `articleId` nên duy nhất theo nghiệp vụ. Nếu bản ghi bị cập nhật `publishedAt` giữa các trang, trang vẫn có thể thay đổi. Cần cân nhắc yêu cầu nhất quán của sản phẩm và index phù hợp với điều kiện/sắp xếp.

Keyset pagination không tự có nghĩa là mọi truy vấn sẽ nhanh; nó thường tránh phải bỏ qua offset lớn, nhưng phải kiểm tra index, selectivity và plan.

## 9. Giới hạn theo từng nhóm khác giới hạn toàn bộ kết quả

Một lỗi phổ biến: muốn “**hai bài mới nhất của mỗi người**” nhưng viết `LIMIT 2` cho toàn luồng:

```cypher
// Sai mục đích nếu muốn 2 bài CHO MỖI người
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH u, a
ORDER BY a.publishedAt DESC
LIMIT 2
RETURN u.userId AS userId, a.articleId AS articleId;
```

`LIMIT 2` trên chỉ lấy tối đa **hai hàng cho tất cả người dùng**, không phải mỗi người hai bài.

Nếu thật sự cần danh sách bài theo **từng người**, có thể dùng subquery có tương quan:

```cypher
MATCH (u:OptDemoUser)
CALL {
  WITH u
  MATCH (u)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
  WITH DISTINCT a
  ORDER BY a.publishedAt DESC, a.articleId ASC
  LIMIT 2
  RETURN collect(a.articleId) AS recentLikedArticleIds
}
RETURN u.userId AS userId,
       recentLikedArticleIds
ORDER BY userId;
```

Kết quả theo dữ liệu mẫu: An có `['A101','A102']`, Bình có `['A101']`, Chi có `[]`. `collect()` trong subquery được thực hiện **sau `LIMIT 2`** nên danh sách đầu ra tối đa hai mã cho mỗi người. Aggregation không có khóa nhóm trả một hàng với `[]` ngay cả khi `MATCH` trong subquery không tìm được bài, nên Chi được giữ trong kết quả.

**Giới hạn theo nhóm không miễn phí:** một subquery tương quan có thể được chạy theo từng hàng người dùng; trên tập người lớn, cần xem execution plan và chọn phương án batch/thiết kế phù hợp. Ví dụ minh họa **đúng phạm vi `LIMIT`**, không khẳng định nó luôn tối ưu nhất.

## 10. Giảm lượng dữ liệu trả về: projection nhỏ và đúng nhu cầu

Giả sử `a.body` là bài viết dài, còn màn hình danh sách chỉ cần mã, tiêu đề và ngày:

```cypher
// Trả toàn bộ node — có thể kèm property body lớn
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a
ORDER BY a.publishedAt DESC
LIMIT 20;
```

Truy vấn gọn về cú pháp nhưng trả entity chứa nhiều property hơn màn hình cần. Nên trả projection tối thiểu:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT 20;
```

Điểm cần lưu ý:

- `RETURN a` và `RETURN *` có thể kéo theo toàn bộ thực thể/biến trong phạm vi, dẫn tới payload không cần thiết. `properties(a)` càng thể hiện rõ việc lấy toàn bộ property.
- `RETURN path` có thể mang các node và relationship trên cả đường đi; chỉ trả path khi giao diện thật sự cần cấu trúc đường đi. Với thống kê, `length(path)` hoặc các giá trị tổng hợp có thể đủ.
- Chỉ lấy `a.articleId`, `a.title` không có nghĩa Neo4j sẽ không bao giờ phải đọc các property khác để lọc/sắp xếp; đây là tối ưu **hình dạng đầu ra**, không đảm bảo mọi phép đọc storage đều biến mất.
- Một `collect({id: a.articleId, title: a.title})` nhỏ hơn `collect(a)` nếu mỗi map chỉ có một số trường, nhưng vẫn là **một danh sách** phải gom. Nếu ứng dụng có thể đọc từng hàng thì có thể không cần `collect`.
- `LIMIT 20` giảm số hàng đưa về, nhưng nếu phía trước có expansion hoặc aggregation lớn, cần tối ưu phần đó riêng.

Khi ứng dụng hiển thị trang chi tiết, truy vấn thứ hai theo `articleId` có thể lấy `body` lúc cần. Đây là lựa chọn API: **list view** trả dữ liệu ngắn, **detail view** tải nội dung đầy đủ.

## 11. Java Driver, Spring Data Neo4j và chi phí phía ứng dụng

Đường đi dữ liệu không kết thúc ở `RETURN`. Neo4j còn phải truyền kết quả qua giao thức Bolt, phía Java Driver nhận các bản ghi, ứng dụng ánh xạ chúng sang DTO/entity, rồi dịch vụ gửi JSON hoặc nội dung tương đương cho giao diện.

Với **Neo4j Java Driver**, nên truyền tham số `$pageSize` và đọc kết quả từng record khi cần, thay vì gom toàn bộ vào một `List` lớn để mới xử lý. Ví dụ Java (đã có `Driver driver`):

```java
import java.util.Map;
import org.neo4j.driver.Record;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;

// Giả sử driver được quản lý ở vòng đời ứng dụng.
try (Session session = driver.session()) {
    Result result = session.run(
        "MATCH (a:OptDemoArticle) " +
        "WHERE a.published = true " +
        "RETURN a.articleId AS articleId, a.title AS title " +
        "ORDER BY a.publishedAt DESC, a.articleId ASC " +
        "LIMIT $pageSize",
        Map.of("pageSize", 20)
    );

    while (result.hasNext()) {
        Record row = result.next();
        String id = row.get("articleId").asString();
        String title = row.get("title").asString();
        // Xử lý từng record trong phạm vi session.
        System.out.println(id + ": " + title);
    }
}
```

Truy vấn trên chỉ trả **hai property** cho tối đa 20 bài, và code dùng cursor theo từng record. Tuy nhiên, cơ chế fetch/buffering của Driver và giao diện xuất dữ liệu vẫn có chi phí; không nên suy rằng chỉ dùng vòng lặp là đủ cho việc xử lý hàng triệu dòng trong mọi tình huống. Đối với export lớn, thiết kế phân lô và quản lý vòng đời transaction/session phù hợp.

Với **Spring Data Neo4j**, cân nhắc projection/DTO cho các endpoint chỉ cần một số trường và kiểm tra kỹ việc load quan hệ/đồ thị liên quan của entity. Ví dụ truy vấn projection (ý tưởng):

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId, a.title AS title
ORDER BY a.publishedAt DESC, a.articleId
LIMIT $pageSize;
```

Trên tầng Java, mapper nên lấy đúng `articleId` và `title` cho DTO danh sách. Việc trả một entity đầy đủ rồi chỉ bỏ bớt trường lúc chuyển sang JSON có thể đã gây chi phí truy vấn/ánh xạ không cần thiết.

Tránh mô hình **N+1**: lấy 20 bài, rồi chạy thêm 20 truy vấn riêng để lấy số bình luận. Có thể dùng một truy vấn tổng hợp hoặc `COUNT { ... }` theo từng bài, hoặc một truy vấn batch bằng `UNWIND $articleIds` khi dữ liệu/khung ứng dụng phù hợp.

## 12. EXPLAIN và PROFILE: kiểm chứng chỗ thật sự tốn tài nguyên

Tối ưu nên dựa trên kế hoạch và số liệu. `EXPLAIN` hiển thị kế hoạch dự tính mà không chạy câu truy vấn; `PROFILE` **thực sự chạy truy vấn** và cung cấp chỉ số như **Rows**, **DB Hits** và thông tin bộ nhớ/thời gian tùy runtime.

Ví dụ xem hiện tượng tăng số hàng:

```cypher
PROFILE
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
RETURN u.userId AS userId,
       a.articleId AS articleId,
       collect(DISTINCT t.name) AS tags,
       collect(DISTINCT c.commentId) AS comments;
```

Ở bộ dữ liệu thử, kế hoạch sẽ phải xử lý các lượt khớp phát sinh do hai nhánh tag/comment; cách nhóm theo `u.userId, a.articleId` đưa kết quả cuối về **3 hàng**. Trong thực thi, số hàng trung gian trước tổng hợp có thể là **13**, còn số hàng sau tổng hợp là **3**. Quan sát trực tiếp các operator `Expand`/`Optional`/`Aggregation` để xác nhận, vì hình dạng thực tế của plan phụ thuộc phiên bản và planner.

Một truy vấn chỉ lấy các trường cần thiết:

```cypher
PROFILE
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title
ORDER BY a.publishedAt DESC, a.articleId ASC
LIMIT 2;
```

Trong plan, chú ý `Sort` hoặc `Top`, toán tử access index và số **Rows** thực tế. Đừng so trực tiếp DB Hits giữa hai truy vấn có **ngữ nghĩa khác nhau** rồi tuyên bố truy vấn nào tối ưu hơn. Để đánh giá một cách viết lại, phải xác nhận **kết quả nghiệp vụ tương đương**, dùng dữ liệu đại diện và điều kiện đo phù hợp.

### Checklist khi đọc execution plan

| Điều quan sát | Câu hỏi cần trả lời |
| --- | --- |
| `Estimated Rows` cao bất thường | Đang bắt đầu quá rộng, hay cardinality tăng ở nhánh relationship nào? |
| `Rows` thực tế tăng sau `Expand` | Có nhân nhiều nhánh độc lập trước `collect` không? |
| `Aggregation` nhận nhiều hàng rồi xuất ít | Có thể đếm/tồn tại/gom sớm hoặc chọn cha trước không? |
| `Sort`/`Top` | Có thật sự cần thứ tự này? `ORDER BY` có thể đặt sau nhóm hoặc kết hợp `LIMIT` không? |
| `CartesianProduct` | Các mẫu có thiếu biến chung hoặc điều kiện nối không? |
| `DB Hits` nhiều | Có thể thu hẹp đầu vào, dùng index phù hợp hoặc tránh duyệt quan hệ không cần thiết? |
| Result trả nhiều property | Có thể giảm `RETURN` xuống DTO cho màn hình hiện tại không? |

**Giới hạn của `PROFILE`:** nó đo hoạt động trong database, không đo đầy đủ băng thông từ Neo4j tới ứng dụng, chi phí serialize JSON, cấp phát object trên JVM hoặc tốc độ render của giao diện. Với vấn đề payload lớn, cần đo thêm kích thước response và độ trễ đầu cuối ở ứng dụng.

## 13. Quy trình tối ưu từng bước

Khi gặp một truy vấn chậm có nhiều `collect`, `ORDER BY` và payload lớn, áp dụng trình tự sau:

1. **Xác định đầu ra thật sự:** màn hình cần danh sách toàn bộ hay chỉ 20 bản ghi? Cần node đầy đủ, tên, ID, số lượng hay trạng thái có/không?
2. **Đo hình dạng hiện tại:** chạy `EXPLAIN` rồi `PROFILE` với truy vấn đọc phù hợp; xem số hàng trung gian, operator mở rộng, tổng hợp và sort.
3. **Giảm đầu vào:** neo truy vấn vào label/khóa cụ thể, lọc sớm theo điều kiện đúng nghiệp vụ, dùng index khi phù hợp.
4. **Tránh nhân nhánh độc lập:** thay `MATCH` để đếm/tồn tại bằng `COUNT { ... }`/`EXISTS { ... }`; nếu cần hai danh sách, gom từng nhánh riêng.
5. **Giới hạn trước khi gom quan hệ con:** chọn top-k bài hoặc đối tượng cha trước bằng `WITH ... ORDER BY ... LIMIT` khi nghiệp vụ chỉ cần top-k.
6. **Sắp xếp đúng một lần ở vị trí cần thiết:** trước `LIMIT`, sau aggregation, hoặc trước `collect` nếu thứ tự phần tử danh sách là yêu cầu.
7. **Thu nhỏ projection:** trả đúng field, tránh `RETURN *`, `RETURN path` hoặc `collect(node)` nếu không cần.
8. **Phân trang và ánh xạ gọn:** dùng `SKIP/LIMIT` hoặc keyset phù hợp; Java Driver/Spring Data Neo4j chỉ tải kết quả dự kiến.
9. **Đo lại và so sánh đúng:** đối chiếu kết quả nghiệp vụ, **Rows**, DB Hits, bộ nhớ, thời gian chạy database và kích thước response phía ứng dụng.

## 14. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`collect()` trả một hàng nên chắc nhẹ.” | Một hàng có thể chứa danh sách cực lớn; bộ nhớ và payload phụ thuộc số phần tử. |
| “Cứ thêm `DISTINCT` cuối truy vấn là giải quyết hiệu năng.” | `DISTINCT` có thể khử trùng kết quả nhưng không loại bỏ chi phí của các tổ hợp đã sinh trước đó. |
| “`LIMIT 10` cuối truy vấn bảo đảm chỉ xử lý 10 hàng.” | Các bước trước có thể đã đọc/mở rộng/tổng hợp/sắp nhiều hàng; planner có thể dừng sớm trong một số trường hợp. |
| “`ORDER BY` ở bất kỳ đâu cũng có tác dụng tương đương.” | Thứ tự cần đặt đúng trước top-k, sau nhóm hoặc trước tổng hợp danh sách. |
| “Không có `ORDER BY` thì dữ liệu tự có thứ tự ổn định.” | Neo4j không bảo đảm thứ tự kết quả khi không chỉ định. |
| “`RETURN a` cũng nhẹ như `RETURN a.articleId`.” | Trả node có thể mang nhiều property hơn DTO cần, làm tăng dữ liệu truyền và xử lý. |
| “Giới hạn hai hàng sau ghép tag là giới hạn hai bài.” | Hai hàng có thể cùng thuộc một bài; phải giới hạn tập cha trước khi mở rộng. |
| “`PROFILE` chỉ xem plan.” | `PROFILE` thực thi truy vấn; với câu lệnh ghi nó có thể thay đổi dữ liệu. |

## 15. Bài luyện tập với dữ liệu mẫu

**Bài 1.** Viết câu Cypher liệt kê ba bài đã xuất bản mới nhất, chỉ gồm `articleId`, `title`. Dùng thứ tự theo `publishedAt DESC, articleId ASC`.

**Bài 2.** Đếm số bài mà mỗi người đã thích, kể cả người chưa thích bài nào, chỉ trả `userId` và `likeCount`. Gợi ý dùng `OPTIONAL MATCH` và `count(a)`:

```cypher
MATCH (u:OptDemoUser)
OPTIONAL MATCH (u)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
RETURN u.userId AS userId, count(a) AS likeCount
ORDER BY userId;
```

Kết quả: `U01 = 2`, `U02 = 1`, `U03 = 0`. Nếu dùng `count(*)`, hàng `OPTIONAL MATCH` với `a = null` của Chi vẫn bị tính là một hàng; vì vậy `count(a)` đúng hơn.

**Bài 3.** Sửa một truy vấn lấy cả tag và bình luận để không tạo tích tổ hợp giữa hai nhánh. Dùng `COUNT { ... }` cho số bình luận nếu màn hình không cần nội dung bình luận.

**Bài 4.** Lấy bài mới nhất của **mỗi** người, gồm người chưa thích bài nào. Giải thích vì sao `LIMIT 1` đặt trên toàn truy vấn không đáp ứng yêu cầu đó.

**Bài 5.** Chạy `EXPLAIN` và `PROFILE` cho truy vấn trả toàn bộ node so với truy vấn chỉ trả mã/tiêu đề của 2 bài. Ghi lại **Rows**, DB Hits, thời gian đo và kích thước payload ở ứng dụng. Nhận xét điểm nào giảm do truy vấn và điểm nào giảm do dữ liệu truyền.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/): `collect()`, `count()` và cách tổng hợp.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/): sắp xếp và bảo đảm thứ tự.
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/): giới hạn số hàng trả về.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): đọc operator và chỉ số `EXPLAIN`/`PROFILE`.
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/): query parameter, nhận kết quả và vòng đời session.

**Ghi nhớ:** tối ưu Cypher không chỉ là làm `MATCH` nhanh hơn. Một truy vấn tốt **không tạo danh sách lớn khi chỉ cần đếm**, **không sắp xếp khi không có yêu cầu thứ tự**, **giới hạn đúng đối tượng trước khi mở rộng nhiều nhánh**, và **chỉ trả lượng dữ liệu ứng dụng sẽ sử dụng**.
