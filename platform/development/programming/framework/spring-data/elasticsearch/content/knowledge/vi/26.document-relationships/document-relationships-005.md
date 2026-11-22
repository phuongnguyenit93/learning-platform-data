# Join field cho mô hình cha-con khi có nhu cầu phù hợp

Elasticsearch hỗ trợ quan hệ cha-con (parent-child) giữa các document trong cùng một index thông qua kiểu field `join`. Một document cha có thể liên kết với nhiều document con; mỗi document con thuộc về một document cha. Quan hệ được lưu trong join field và Elasticsearch dùng routing để bảo đảm cha và con nằm trên cùng shard.

Join field hữu ích khi dữ liệu cha và con cần được lưu, cập nhật hoặc truy vấn độc lập. Ví dụ một câu hỏi có rất nhiều câu trả lời; một sản phẩm có nhiều đánh giá được thêm liên tục; một bài viết có nhiều bình luận. Khi cập nhật một document con, ứng dụng không phải ghi lại toàn bộ document cha như cách thường gặp với mảng `nested`.

Tuy nhiên, parent-child có chi phí truy vấn và vận hành cao hơn mô hình document phẳng hoặc `nested` trong nhiều trường hợp. Chỉ nên dùng khi có nhu cầu độc lập thực sự giữa cha và con, và các truy vấn `has_child`/`has_parent` là một phần quan trọng của nghiệp vụ. Nếu quan hệ đơn giản, dữ liệu con thường được đọc cùng cha và cập nhật cùng nhau, `nested` hoặc denormalization thường dễ vận hành hơn.

## 1. Mô hình cha-con trong Elasticsearch

Một index có thể khai báo một join field để định nghĩa các quan hệ giữa các tên relation. Ví dụ:

```text
question
   |
   +---- answer
   +---- answer
   +---- answer
```

Ở đây:

- `question` là tên relation cha.
- `answer` là tên relation con.
- Một document `question` có thể có nhiều document `answer`.
- Mỗi document `answer` chỉ có một parent.
- Document cha và con là các document riêng biệt trong cùng index.

Join field không tạo ra một bảng quan hệ như trong cơ sở dữ liệu quan hệ. Nó lưu metadata quan hệ trong document và cung cấp các query chuyên biệt để tìm cha theo con hoặc con theo cha.

### Ví dụ dữ liệu

Một câu hỏi và các câu trả lời có thể được biểu diễn như sau:

```json
{
  "_id": "q-100",
  "title": "Spring Data Elasticsearch là gì?",
  "relation": "question"
}
```

```json
{
  "_id": "a-201",
  "text": "Đây là module tích hợp Spring Data với Elasticsearch.",
  "relation": {
    "name": "answer",
    "parent": "q-100"
  }
}
```

```json
{
  "_id": "a-202",
  "text": "Nó cung cấp repository và ElasticsearchOperations.",
  "relation": {
    "name": "answer",
    "parent": "q-100"
  }
}
```

Document cha lưu relation bằng tên cha. Document con lưu cả tên relation con và ID của parent.

## 2. Khi nào nên chọn Join field?

Parent-child phù hợp khi các điều kiện sau có ý nghĩa với mô hình dữ liệu:

- Document con có vòng đời riêng, thường xuyên được thêm, cập nhật hoặc xóa độc lập.
- Một parent có thể có số lượng child lớn hoặc tăng theo thời gian.
- Không muốn mỗi thay đổi child phải ghi lại toàn bộ document cha.
- Ứng dụng cần truy vấn cha dựa trên điều kiện của con (`has_child`).
- Ứng dụng cần truy vấn con dựa trên điều kiện của cha (`has_parent`).
- Dữ liệu cha và con có thể được định tuyến cùng shard.

Ví dụ:

| Mô hình | Lý do có thể cân nhắc parent-child |
|---|---|
| Câu hỏi – câu trả lời | Câu trả lời được thêm và kiểm duyệt độc lập; cần tìm câu hỏi có câu trả lời được chấp nhận |
| Sản phẩm – đánh giá | Đánh giá liên tục được thêm; cần tìm sản phẩm có đánh giá đạt điều kiện |
| Bài viết – bình luận | Bình luận có vòng đời riêng và có thể rất nhiều |
| Tài khoản – sự kiện hoạt động | Sự kiện được ghi độc lập; cần tìm tài khoản theo loại sự kiện |

Không nên chọn join field chỉ vì dữ liệu có quan hệ cha-con trong nghiệp vụ. Quan hệ trong mô hình nghiệp vụ không nhất thiết phải được biểu diễn bằng join field của Elasticsearch.

## 3. So sánh Join field với Nested và Denormalization

Ba cách phổ biến để biểu diễn dữ liệu liên quan có trade-off khác nhau.

| Tiêu chí | Join field (parent-child) | Nested | Denormalization |
|---|---|---|---|
| Lưu trữ | Cha và con là document riêng | Các object con nằm trong cùng document cha | Sao chép field cần thiết vào document |
| Cập nhật child | Có thể cập nhật riêng | Thường phải cập nhật document cha chứa nested object | Cập nhật các bản sao liên quan nếu cần nhất quán |
| Truy vấn quan hệ | `has_child`, `has_parent`, `parent_id` | `nested` query | Query trực tiếp trên field đã sao chép |
| Một parent có nhiều child | Có | Có | Có thể biểu diễn tùy thiết kế |
| Chi phí truy vấn | Join query tốn kém hơn query thông thường | Có overhead nested nhưng thường phù hợp truy vấn trong một document | Thường thấp nhất khi query trực tiếp |
| Routing | Cha và con phải cùng shard | Không cần routing quan hệ | Không cần routing quan hệ |
| Phù hợp | Child độc lập và cần join theo quan hệ | Child thường được đọc cùng cha và cần giữ quan hệ giữa field trong object | Ưu tiên tốc độ đọc, chấp nhận sao chép dữ liệu |

### Chọn Nested khi

- Số lượng object con vừa phải.
- Object con thường được đọc cùng document cha.
- Cần đảm bảo các điều kiện khớp trên cùng một object con.
- Cập nhật document cha cùng các object con là chấp nhận được.

### Chọn Denormalization khi

- Truy vấn cần tốc độ cao và đơn giản.
- Chỉ cần sao chép một vài thuộc tính cha/con để lọc hoặc hiển thị.
- Có thể quản lý cập nhật và đồng bộ dữ liệu lặp.

### Chọn Join field khi

- Child có vòng đời và tần suất cập nhật độc lập.
- Số lượng child có thể lớn.
- Cần tìm parent dựa trên child hoặc ngược lại.
- Đội phát triển chấp nhận chi phí join query và quy tắc routing.

## 4. Khai báo mapping Join field bằng Elasticsearch

Join field được khai báo trong mapping của index:

```http
PUT /qa-index
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "text": {
        "type": "text"
      },
      "relation": {
        "type": "join",
        "relations": {
          "question": "answer"
        }
      }
    }
  }
}
```

Tên field `relation` là tên join field. Trong mapping `relations`, key `question` là parent relation và value `answer` là child relation.

Có thể khai báo nhiều quan hệ trong cùng join field:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "question": ["answer", "comment"],
        "article": "comment"
      }
    }
  }
}
```

Trong ví dụ, `question` có thể là cha của `answer` và `comment`; `article` cũng có thể là cha của `comment`. Tên relation là nhãn trong mapping, không phải tên index hoặc tên class Java.

Một index chỉ có một join field mapping. Nếu cần nhiều kiểu quan hệ, hãy mô hình hóa các relation trong cùng join field hoặc cân nhắc index khác nếu cấu trúc quan hệ độc lập.

## 5. Khai báo Join field trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ join mapping thông qua `FieldType.Join`, `@JoinTypeRelations`, `@JoinTypeRelation` và kiểu `JoinField<T>`.

Ví dụ một document class dùng chung cho parent và child:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.mapping.JoinField;

@Document(indexName = "qa-index")
public class QaDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String text;

    @Field(type = FieldType.Join)
    @JoinTypeRelations(
        relations = {
            @JoinTypeRelation(parent = "question", children = {"answer"})
        }
    )
    private JoinField<String> relation;

    @Routing
    private String routing;

    // Constructors, getters and setters
}
```

`JoinField<String>` lưu tên relation và parent ID đối với document con. Với document cha, parent ID không cần có. `@JoinTypeRelations` định nghĩa quan hệ mà Spring Data dùng khi tạo mapping. `@Routing` đánh dấu thuộc tính Java được dùng làm routing value cho thao tác index/search theo hỗ trợ của Spring Data.

Một số phiên bản Spring Data có khác biệt nhỏ về package hoặc API mapping. Hãy dùng các annotation và lớp `JoinField` từ đúng phiên bản dependency của dự án.

## 6. Tạo document cha

Document cha có relation name bằng tên parent đã khai báo trong mapping:

```java
QaDocument question = new QaDocument();
question.setId("q-100");
question.setTitle("Spring Data Elasticsearch là gì?");
question.setText("Câu hỏi về tích hợp Spring Data với Elasticsearch.");
question.setRelation(new JoinField<>("question", null));
question.setRouting("q-100");
```

Với parent, routing thường được đặt bằng ID của chính parent. Elasticsearch mặc định dùng `_id` làm routing nếu không chỉ định routing khác, nhưng đặt tường minh giúp mô hình dễ hiểu và bảo đảm child dùng cùng giá trị.

Lưu document:

```java
QaDocument savedQuestion = operations.save(question);
```

Hoặc dùng repository kế thừa `ElasticsearchRepository<QaDocument, String>`:

```java
qaRepository.save(question);
```

Parent và child phải nằm trong cùng index. Join field không liên kết document giữa hai index khác nhau.

## 7. Tạo document con và routing

Document con khai báo relation name là `answer` và parent ID là `q-100`:

```java
QaDocument answer = new QaDocument();
answer.setId("a-201");
answer.setTitle("Câu trả lời thứ nhất");
answer.setText("Spring Data cung cấp repository và template API.");
answer.setRelation(new JoinField<>("answer", "q-100"));
answer.setRouting("q-100");

operations.save(answer);
```

Hai thông tin quan trọng:

- `new JoinField<>("answer", "q-100")` khai báo child relation và ID của parent.
- `routing = "q-100"` yêu cầu Elasticsearch đặt child vào cùng shard với parent.

**Routing là bắt buộc đối với thao tác index child.** Nếu child được gửi tới shard khác parent, Elasticsearch không thể thực hiện quan hệ cha-con đúng cách và có thể trả lỗi parent không tồn tại trên shard đó.

Nên index parent trước rồi mới index child. Khi index hàng loạt, bảo đảm parent đã tồn tại trước các child tương ứng và mọi child dùng routing value bằng parent ID.

### Tạo nhiều child

```java
List<QaDocument> answers = List.of(
    createAnswer("a-201", "q-100", "Câu trả lời A"),
    createAnswer("a-202", "q-100", "Câu trả lời B"),
    createAnswer("a-203", "q-100", "Câu trả lời C")
);

qaRepository.saveAll(answers);
```

Hàm `createAnswer` phải luôn đặt cả `JoinField` parent ID và routing value. Không chỉ đặt relation mà bỏ routing.

## 8. Đọc document cha và con

Có thể đọc parent theo ID như document thông thường, nhưng cần dùng đúng index và routing nếu request cần routing tường minh:

```http
GET /qa-index/_doc/q-100?routing=q-100
```

Đọc child:

```http
GET /qa-index/_doc/a-201?routing=q-100
```

Vì child được route theo parent ID, khi get child phải dùng routing tương ứng. Nếu không biết routing, thao tác get theo ID có thể không tìm thấy document vì request chỉ truy vấn shard được tính từ routing mặc định.

Trong Spring Data, có thể cấu hình routing trên entity bằng `@Routing` hoặc dùng API thao tác hỗ trợ routing. Khi đọc document child, đặt giá trị routing về parent ID.

## 9. Tìm parent dựa trên điều kiện của child: `has_child`

`has_child` query trả về document cha có ít nhất một document con khớp query bên trong.

Ví dụ tìm các câu hỏi có ít nhất một câu trả lời chứa cụm từ `repository`:

```http
POST /qa-index/_search
Content-Type: application/json

{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "repository"
        }
      },
      "score_mode": "none"
    }
  }
}
```

`type` là tên child relation đã khai báo trong mapping, không phải tên Java class. `query` là điều kiện áp dụng cho child. Kết quả là parent document.

### `score_mode`

`has_child` có thể kết hợp score của child khớp vào score của parent. Các chế độ thường gặp gồm:

| Giá trị | Ý nghĩa |
|---|---|
| `none` | Không dùng score của child để tính score parent |
| `avg` | Trung bình score của các child khớp |
| `max` | Lấy score lớn nhất |
| `min` | Lấy score nhỏ nhất |
| `sum` | Cộng score của các child khớp |

Nếu chỉ cần lọc parent có child thỏa điều kiện, `none` thường đủ. Nếu relevance của câu trả lời ảnh hưởng thứ hạng câu hỏi, chọn mode phù hợp và đánh giá score.

## 10. Tìm child dựa trên điều kiện của parent: `has_parent`

`has_parent` query trả về document con có parent khớp điều kiện.

Ví dụ tìm các câu trả lời thuộc câu hỏi có tiêu đề chứa `Spring Data`:

```http
POST /qa-index/_search
Content-Type: application/json

{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "match": {
          "title": "Spring Data"
        }
      },
      "score": false
    }
  }
}
```

`parent_type` là tên relation cha. `score: false` có nghĩa score của parent không được truyền vào score của child. Nếu cần xếp hạng child dựa trên độ liên quan của parent, có thể bật score và kiểm tra kết quả.

## 11. Lấy child theo một parent cụ thể: `parent_id`

Nếu đã biết parent ID và muốn tìm các child thuộc parent đó, có thể dùng `parent_id` query:

```http
POST /qa-index/_search?routing=q-100
Content-Type: application/json

{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "q-100"
    }
  }
}
```

Query trả về các document thuộc child relation `answer` có parent ID là `q-100`. Tham số `routing` giới hạn request vào shard chứa parent và child, giúp tránh tìm trên các shard không liên quan khi biết parent ID.

`parent_id` phù hợp hơn `has_child` khi chỉ cần lấy các con của một parent cụ thể. `has_child` phù hợp khi muốn tìm parent dựa trên điều kiện phức tạp của child.

## 12. Dùng các query Join trong Spring Data `NativeQuery`

Spring Data Elasticsearch có thể xây dựng các query join thông qua `NativeQuery` và Elasticsearch Java API Client.

Ví dụ `has_child`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.hasChild(h -> h
        .type("answer")
        .query(childQuery -> childQuery.match(m -> m
            .field("text")
            .query("repository")
        ))
        .scoreMode(co.elastic.clients.elasticsearch._types.query_dsl.ChildScoreMode.None)
    ))
    .build();
```

Ví dụ `has_parent`:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.hasParent(h -> h
        .parentType("question")
        .query(parentQuery -> parentQuery.match(m -> m
            .field("title")
            .query("Spring Data")
        ))
        .score(false)
    ))
    .build();
```

Tên enum và builder có thể khác nhẹ giữa các phiên bản Elasticsearch Java API Client. Hai ví dụ thể hiện cách biểu diễn query; hãy dùng đúng package và kiểu enum của client mà phiên bản Spring Data trong dự án quản lý. Có thể dùng REST Query DSL trực tiếp để kiểm chứng logic trước khi chuyển sang Java builder.

Khi thực thi query, dùng `ElasticsearchOperations.search(...)` hoặc repository method tương ứng. Nếu biết routing, hãy truyền routing qua API/query metadata hoặc annotation `@Routing` để giới hạn shard.

## 13. Routing và nguyên tắc cùng shard

Parent-child chỉ hoạt động khi parent và child nằm trên cùng shard. Elasticsearch không thực hiện join giữa shard khác nhau.

Quy tắc phổ biến:

```text
Parent ID: q-100
Parent routing: q-100
Child ID: a-201
Child routing: q-100
Child relation parent: q-100
```

Routing value của child phải là ID parent. Điều này bảo đảm cả hai document được băm tới cùng shard.

### Nếu bỏ routing thì sao?

Nếu index child không có routing đúng, Elasticsearch có thể tính shard từ child `_id`, khiến child rơi vào shard khác parent. Khi đó quan hệ không hợp lệ và thao tác có thể trả lỗi. Đối với parent, routing mặc định dựa trên ID thường trùng với routing parent ID, nhưng đặt routing tường minh cho cả parent và child giúp code nhất quán.

### Routing trong Spring Data

`@Routing` đánh dấu thuộc tính chứa routing value. Với child, gán thuộc tính này bằng parent ID. Với parent, thường gán bằng chính ID parent.

Nếu một repository thao tác cả parent lẫn child, không thể giả định một routing mặc định chung cho mọi entity. Hãy bảo đảm mỗi document được tạo với routing value đúng trước khi gọi `save`/`saveAll`.

## 14. Một parent có nhiều cấp quan hệ

Join field cho phép định nghĩa quan hệ nhiều cấp, ví dụ:

```text
company
   |
   +---- department
             |
             +---- employee
```

Mapping minh họa:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "company": "department",
        "department": "employee"
      }
    }
  }
}
```

Khi index employee, routing vẫn phải dùng ID của root parent (`company`) theo quy tắc routing của quan hệ nhiều cấp, không chỉ ID department trực tiếp. Điều này rất dễ bị cấu hình sai khi có nhiều tầng.

Mặc dù Elasticsearch hỗ trợ nhiều cấp, không nên tạo cây quan hệ sâu nếu có thể mô hình hóa đơn giản hơn. Mỗi tầng join làm truy vấn phức tạp và tốn chi phí hơn. Parent-child thường nên giữ ở một cấp cha-con.

## 15. Cập nhật và xóa document con

Một lợi ích của parent-child là có thể cập nhật child độc lập:

```http
PUT /qa-index/_doc/a-201?routing=q-100
Content-Type: application/json

{
  "title": "Câu trả lời đã chỉnh sửa",
  "text": "Nội dung trả lời mới.",
  "relation": {
    "name": "answer",
    "parent": "q-100"
  }
}
```

Document cha không cần được ghi lại khi chỉ sửa nội dung child. Khi update, vẫn phải gửi routing đúng và giữ relation đúng.

Xóa child:

```http
DELETE /qa-index/_doc/a-201?routing=q-100
```

Khi xóa parent, không nên giả định Elasticsearch tự động cascade delete toàn bộ child. Nếu nghiệp vụ yêu cầu xóa cả cây, ứng dụng cần chủ động tìm/xóa child bằng routing hoặc `delete_by_query` phù hợp, rồi xóa parent. Hãy thiết kế thứ tự xóa và retry để tránh để lại document con mồ côi.

### Đổi parent của child

Một child thuộc một parent. Nếu chuyển child sang parent khác, cần cập nhật cả join relation và routing sang parent mới. Do routing quyết định shard, thay đổi này có thể cần reindex document với routing mới thay vì chỉ update field relation.

## 16. Bulk indexing parent và child

Khi nạp dữ liệu lớn, có thể dùng Bulk API để index parent và child. Tuy nhiên, phải bảo đảm parent tồn tại trước khi index child và mỗi child có routing đúng.

Ví dụ thứ tự logic:

```text
1. Index question q-100, routing q-100
2. Index answer a-201, routing q-100, parent q-100
3. Index answer a-202, routing q-100, parent q-100
```

Bulk API không phải transaction nguyên tử. Nếu parent action thất bại nhưng child action vẫn được gửi, child có thể lỗi do không tìm thấy parent trên shard. Kiểm tra kết quả từng item và chỉ đánh dấu batch thành công khi các quan hệ cần thiết đã được tạo đúng.

Với nhiều parent, có thể chia batch theo parent để bảo đảm thứ tự và routing. Nếu pipeline chạy song song, các child của cùng parent vẫn phải dùng cùng routing value.

## 17. Hiệu năng và chi phí vận hành

Parent-child query thường tốn kém hơn query trực tiếp trên field. Join field sử dụng global ordinals để ánh xạ relation giữa parent và child; việc xây dựng hoặc cập nhật global ordinals có thể ảnh hưởng thời gian refresh và bộ nhớ.

Một số điểm cần cân nhắc:

- `has_child` có thể tốn kém, nhất là khi số child lớn hoặc query match nhiều child.
- `has_parent` cũng có chi phí join và cần đánh giá trên dữ liệu thực.
- Một parent có rất nhiều child có thể tạo skew shard nếu routing theo parent ID.
- Các document cùng parent bị dồn về cùng shard, nên một parent cực lớn có thể làm shard mất cân bằng.
- Refresh có thể làm global ordinals được xây dựng/cập nhật, ảnh hưởng latency.
- Số tầng join càng sâu, query càng phức tạp.
- Không nên chạy nhiều join query nặng đồng thời mà chưa đo tài nguyên.

### Global ordinals

Join field thường dùng global ordinals để thực hiện join query hiệu quả hơn. Có thể cấu hình `eager_global_ordinals` cho join field nếu muốn xây dựng ordinals trong refresh thay vì đợi query đầu tiên. Điều này có thể giảm latency query đầu tiên sau refresh nhưng làm tăng chi phí refresh và sử dụng bộ nhớ.

Ví dụ mapping:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "eager_global_ordinals": true,
      "relations": {
        "question": "answer"
      }
    }
  }
}
```

Không bật eager global ordinals theo thói quen. Hãy đo latency sau refresh, tần suất refresh và bộ nhớ heap để quyết định.

## 18. Routing có thể tạo mất cân bằng shard

Vì mọi child của một parent phải cùng shard, một parent có hàng triệu child có thể làm shard chứa parent đó nặng hơn các shard khác. Đây là trade-off cấu trúc của parent-child.

Trước khi chọn join field, hãy ước lượng:

- Số lượng parent.
- Số child trung bình và lớn nhất trên mỗi parent.
- Tần suất index/update child.
- Số shard của index.
- Kích thước document và tốc độ tăng dữ liệu.

Nếu một parent có lượng child cực lớn, có thể cần tách dữ liệu theo index/partition hoặc dùng mô hình denormalized phù hợp hơn. Không thể phân tán child của cùng parent sang shard khác mà vẫn giữ quan hệ join field chuẩn.

## 19. Join field không phải quan hệ giữa hai index

Join field chỉ định nghĩa quan hệ cha-con giữa document trong cùng một index. Nó không thực hiện join giữa:

- Hai index Elasticsearch khác nhau.
- Elasticsearch và một database quan hệ.
- Hai cluster Elasticsearch.

Nếu parent và child nằm ở index khác nhau, hãy dùng application-side join, denormalization, enrichment hoặc một pipeline khác. Không thể khai báo join field trong một index để tham chiếu parent ở index khác.

## 20. Tích hợp trong service Spring

Một service nên chịu trách nhiệm tạo relation và routing nhất quán. Ví dụ:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class QaService {

    private final ElasticsearchOperations operations;

    public QaService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createQuestion(String id, String title, String text) {
        QaDocument question = new QaDocument();
        question.setId(id);
        question.setTitle(title);
        question.setText(text);
        question.setRelation(new JoinField<>("question", null));
        question.setRouting(id);

        operations.save(question);
    }

    public void addAnswer(String answerId, String questionId, String text) {
        QaDocument answer = new QaDocument();
        answer.setId(answerId);
        answer.setText(text);
        answer.setRelation(new JoinField<>("answer", questionId));
        answer.setRouting(questionId);

        operations.save(answer);
    }
}
```

Service này tập trung vào hai quy tắc: parent dùng relation `question`, child dùng relation `answer` cùng parent ID, và routing của cả hai dựa trên parent ID. Trong hệ thống thực tế, cần kiểm tra parent tồn tại trước khi thêm answer và xử lý lỗi khi index thất bại.

## 21. Kiểm tra mapping và dữ liệu

Kiểm tra mapping:

```http
GET /qa-index/_mapping
```

Kiểm tra document parent:

```http
GET /qa-index/_doc/q-100?routing=q-100
```

Kiểm tra child:

```http
GET /qa-index/_doc/a-201?routing=q-100
```

Kiểm tra parent/child query:

```http
POST /qa-index/_search
Content-Type: application/json

{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "term": {
          "status": "ACCEPTED"
        }
      }
    }
  }
}
```

Khi query không trả kết quả, kiểm tra theo thứ tự:

1. Mapping có join field và đúng relation names không?
2. Parent document đã tồn tại chưa?
3. Child có relation name đúng và parent ID đúng không?
4. Child đã được index với routing bằng parent ID chưa?
5. Query có dùng đúng tên relation trong `type`/`parent_type` không?
6. Field query có mapping phù hợp và document có giá trị mong đợi không?
7. Index đã refresh để search nhìn thấy dữ liệu chưa?

## 22. Kiểm thử parent-child

Integration test nên chạy với Elasticsearch tương thích và tạo mapping join thật. Mock repository không kiểm tra routing hoặc hành vi join của server.

Các tình huống cần kiểm thử:

- Tạo parent và đọc lại bằng routing.
- Tạo child với đúng parent ID và routing.
- Tạo child với routing sai để xác nhận lỗi được phát hiện.
- `has_child` trả đúng parent khi child khớp.
- `has_parent` trả đúng child khi parent khớp.
- `parent_id` trả đúng các child của một parent.
- Cập nhật child không làm thay đổi source parent.
- Xóa child dùng đúng routing.
- Quy trình xóa parent xử lý child theo quy tắc nghiệp vụ.
- Bulk index xử lý lỗi từng item và thứ tự parent/child.
- Các parent có số child rất khác nhau để quan sát phân bố shard.

Ví dụ test logic `has_child` ở cấp REST có thể được chuyển thành `NativeQuery` và kiểm tra ID parent trả về. Hãy dùng fixture có ít nhất hai parent, mỗi parent có child với trạng thái khác nhau để xác nhận query không trả nhầm parent.

## 23. Những lỗi thường gặp

### Quên routing khi index child

Child có thể bị gửi tới shard khác parent. Luôn gán routing bằng parent ID và kiểm tra request thực tế.

### Dùng tên class thay cho relation name

`type` trong `has_child`/`parent_type` trong `has_parent` là tên relation trong join mapping, ví dụ `answer` hoặc `question`, không nhất thiết là `AnswerDocument` hay `Question`.

### Đặt parent ID sai trong JoinField

Child phải chứa đúng ID của parent. Routing và `JoinField.parent` phải cùng tham chiếu một parent.

### Index child trước parent

Parent cần tồn tại trên shard tương ứng khi tạo child. Index parent trước, sau đó mới index các child.

### Mapping không phải `join`

Một field keyword chứa chuỗi `question` không thay thế join field mapping. Cần khai báo `type: join` và relations.

### Cố join giữa hai index

Join field không hỗ trợ quan hệ giữa index. Dùng application-side join hoặc denormalization.

### Coi Join field như Nested

Nested object nằm trong document cha; parent-child là các document độc lập cùng index. Cách query, update và routing khác nhau.

### Không kiểm soát số lượng child trên một parent

Routing dồn mọi child cùng parent về một shard. Parent quá lớn có thể gây skew và giới hạn khả năng phân tán.

### Giả định xóa parent tự cascade

Ứng dụng phải có quy trình xóa child rõ ràng nếu nghiệp vụ yêu cầu xóa cả cây.

## 24. Quy trình quyết định và triển khai

Trước khi dùng Join field, hãy thực hiện:

1. Xác định parent và child có vòng đời độc lập thực sự không.
2. So sánh với nested và denormalization theo workload đọc/ghi.
3. Ước lượng số child trên mỗi parent và nguy cơ shard skew.
4. Thiết kế relation names và mapping join field trong cùng index.
5. Tạo entity có `JoinField` và thuộc tính routing.
6. Index parent với routing ổn định, sau đó index child với `JoinField.parent` và routing bằng parent ID.
7. Dùng `has_child`, `has_parent` hoặc `parent_id` theo hướng truy vấn.
8. Kiểm soát update, delete, bulk và retry.
9. Theo dõi join query latency, global ordinals, heap và phân bố shard.
10. Kiểm thử routing đúng/sai và các trường hợp parent-child độc lập.

## 25. Kết luận

Join field cho phép biểu diễn quan hệ cha-con giữa các document riêng biệt trong cùng một Elasticsearch index. Mapping định nghĩa các relation name; document cha lưu tên relation cha; document con lưu tên relation con cùng parent ID. Parent và child phải nằm trên cùng shard, vì vậy routing của child phải bằng ID parent.

Trong Spring Data Elasticsearch, có thể khai báo bằng `FieldType.Join`, `@JoinTypeRelations` và `JoinField<T>`, đồng thời dùng `@Routing` để lưu routing value. `has_child` tìm parent theo điều kiện child, `has_parent` tìm child theo điều kiện parent và `parent_id` lấy child của một parent cụ thể. Parent-child phù hợp khi child cần được cập nhật độc lập và ứng dụng thực sự cần truy vấn quan hệ; nếu dữ liệu thường được đọc cùng nhau, `nested` hoặc denormalization thường đơn giản và hiệu quả hơn. Cần tính đến chi phí join query, global ordinals, routing, shard skew và quy trình xóa/đồng bộ trước khi chọn mô hình này.

## Tài liệu tham khảo

- [Elasticsearch – Parent-join field](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join)
- [Elasticsearch – Has child query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-has-child-query)
- [Elasticsearch – Has parent query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-has-parent-query)
- [Elasticsearch – Parent ID query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-parent-id-query)
- [Spring Data Elasticsearch – Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – `JoinField` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/mapping/JoinField.html)
