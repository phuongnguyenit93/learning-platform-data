# Has parent, has child và yêu cầu cùng shard

Elasticsearch thường lưu dữ liệu theo document độc lập. Khi hai loại document có quan hệ cha-con, ví dụ một câu hỏi có nhiều câu trả lời hoặc một phòng ban có nhiều nhân viên, có thể mô hình hóa quan hệ bằng **join field**. Từ mapping này, Elasticsearch cung cấp `has_parent` và `has_child` query để tìm document dựa trên điều kiện của document liên quan.

Điểm bắt buộc của mô hình parent-child là document cha và document con phải nằm trên **cùng một shard của cùng một index**. Elasticsearch bảo đảm điều đó bằng routing: khi index parent và child, ứng dụng phải dùng cùng một routing value, thông thường là ID của parent. Nếu bỏ qua routing hoặc dùng giá trị khác nhau, hai document có thể được phân phối sang các shard khác nhau và quan hệ không thể hoạt động đúng.

Parent-child phù hợp khi hai loại document cần được cập nhật độc lập và một parent có thể có nhiều child. Nó có chi phí truy vấn và quản lý cao hơn mô hình document phẳng hoặc nested, vì vậy chỉ nên dùng khi vòng đời dữ liệu thực sự cần quan hệ độc lập.

## 1. Mô hình quan hệ parent-child

Ví dụ một diễn đàn có:

- Một document `question` đại diện cho câu hỏi.
- Nhiều document `answer` đại diện cho câu trả lời thuộc câu hỏi đó.

Một câu hỏi có thể có nhiều câu trả lời:

~~~text
Question Q-100
   |
   +---- Answer A-1
   |
   +---- Answer A-2
   |
   +---- Answer A-3
~~~

Trong Elasticsearch, parent và child vẫn là hai document riêng. Chúng không được lưu thành một JSON object lồng nhau như nested object. Join field lưu loại quan hệ và ID của parent trên document child.

Ví dụ dữ liệu:

~~~json
{
  "_id": "Q-100",
  "question": "How does routing work?",
  "relation": "question"
}
~~~

~~~json
{
  "_id": "A-1",
  "answer": "Routing keeps related documents on one shard.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  }
}
~~~

Document parent lưu tên relation dưới dạng chuỗi. Document child lưu object có `name` là tên child relation và `parent` là ID của document cha.

## 2. Join field mapping

Elasticsearch dùng field có kiểu `join` để khai báo quan hệ. Mapping phải định nghĩa các relation hợp lệ trước khi index dữ liệu:

~~~http
PUT /forum
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "relation": {
        "type": "join",
        "relations": {
          "question": "answer"
        }
      },
      "question": {
        "type": "text"
      },
      "answer": {
        "type": "text"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Ở đây `question` là parent relation và `answer` là child relation. Tên relation là tên logic trong join field; nó không nhất thiết trùng với tên field nội dung hoặc tên class Java.

Một index chỉ có thể có một join field. Join field có thể mô tả nhiều cặp parent-child, nhưng tất cả quan hệ phải được khai báo trong cùng field đó.

### 2.1. Một parent có nhiều child

Quan hệ `"question": "answer"` cho phép một document question có nhiều document answer. Mỗi answer chỉ thuộc về một parent question.

- Một parent có thể có 0, 1 hoặc nhiều child.
- Mỗi child có đúng một parent trong quan hệ đã khai báo.
- Parent và child là document độc lập, có ID riêng.
- Quan hệ được xác định bằng join field, không phải bằng cách tự đặt một field JSON bất kỳ có tên `parentId`.

Có thể lưu thêm field nghiệp vụ `questionId` để tiện hiển thị hoặc tích hợp, nhưng field đó không thay thế join field và routing.

### 2.2. Nhiều cấp quan hệ

Join field hỗ trợ nhiều cấp quan hệ, ví dụ question → answer → comment:

~~~json
{
  "relations": {
    "question": {
      "answer": "comment"
    }
  }
}
~~~

Trong mô hình này, question là parent của answer và answer là parent của comment. Các document trong một chuỗi quan hệ vẫn phải được route về cùng shard theo routing của ancestor root. Nhiều cấp join làm truy vấn và quản lý phức tạp hơn; tránh lạm dụng quan hệ nhiều tầng vì chi phí join tăng.

## 3. Vì sao parent và child phải cùng shard?

Elasticsearch chia index thành nhiều primary shard. Mỗi shard là một phân vùng độc lập, và join field được thực hiện trong phạm vi shard. Elasticsearch không thực hiện parent-child join xuyên shard.

Nếu parent nằm ở shard 1 nhưng child nằm ở shard 3, shard chứa child không thể dùng quan hệ join để tìm parent ở shard khác. Vì vậy, cùng index thôi chưa đủ; hai document còn phải được phân phối vào cùng một shard.

### 3.1. Routing quyết định shard

Khi index một document, Elasticsearch dùng ID hoặc routing value để xác định shard. Nếu không truyền routing, ID document thường được dùng làm đầu vào định tuyến. Parent và child có ID khác nhau nên mặc định có thể rơi vào các shard khác nhau.

Để giữ quan hệ:

~~~text
parent Q-100: routing = Q-100
child  A-1:   routing = Q-100
child  A-2:   routing = Q-100
child  A-3:   routing = Q-100
~~~

Tất cả document trong cùng quan hệ dùng routing value `Q-100`. Elasticsearch từ đó đưa chúng về cùng shard.

### 3.2. Routing của parent và child

Khi index parent, truyền routing bằng ID của parent:

~~~http
PUT /forum/_doc/Q-100?routing=Q-100
Content-Type: application/json

{
  "question": "How does routing work?",
  "relation": "question",
  "createdAt": "2026-11-13T08:00:00Z"
}
~~~

Khi index child, cũng truyền đúng routing value của parent:

~~~http
PUT /forum/_doc/A-1?routing=Q-100
Content-Type: application/json

{
  "answer": "Routing keeps related documents on one shard.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  },
  "createdAt": "2026-11-13T08:10:00Z"
}
~~~

Một child khác cùng parent:

~~~http
PUT /forum/_doc/A-2?routing=Q-100
Content-Type: application/json

{
  "answer": "The child must use the same routing value as its parent.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  },
  "createdAt": "2026-11-13T08:15:00Z"
}
~~~

Lưu ý có hai giá trị riêng:

- `relation.parent` ghi ID của parent trong join field.
- Tham số URL `routing` quyết định shard.

Trong ví dụ này, cả hai cùng có giá trị `Q-100`, nhưng chúng có vai trò khác nhau. Chỉ ghi `parent` trong JSON mà bỏ `routing` không bảo đảm child nằm cùng shard với parent.

### 3.3. Cùng index nhưng routing khác nhau vẫn sai

Ví dụ sau không an toàn:

~~~http
PUT /forum/_doc/A-1?routing=A-1
Content-Type: application/json

{
  "answer": "This child may be routed to a different shard.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  }
}
~~~

Child đang dùng routing `A-1`, trong khi parent dùng `Q-100`. Hai giá trị routing có thể dẫn đến shard khác nhau. Elasticsearch yêu cầu routing của child bằng routing của parent để join hoạt động.

Không nên dựa vào việc hai document tình cờ rơi cùng shard khi dùng routing mặc định. Hãy truyền routing rõ ràng cho mọi thao tác index parent và child.

## 4. Truy vấn has_child

`has_child` tìm document parent dựa trên điều kiện của document child. Ví dụ tìm câu hỏi có ít nhất một câu trả lời chứa từ khóa routing:

~~~http
GET /forum/_search
Content-Type: application/json

{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "answer": "routing"
        }
      }
    }
  }
}
~~~

Kết quả là các document `question` có ít nhất một child `answer` khớp truy vấn match. Kết quả trả về parent document; nếu cần nội dung child đã khớp, có thể dùng `inner_hits`.

### 4.1. has_child với điều kiện số lượng

Có thể giới hạn số child khớp bằng `min_children` và `max_children`:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "min_children": 2,
      "max_children": 10,
      "query": {
        "term": {
          "approved": true
        }
      }
    }
  }
}
~~~

Query chọn parent có ít nhất 2 và nhiều nhất 10 child answer được duyệt. Nếu không đặt các tham số này, parent chỉ cần có ít nhất một child khớp.

### 4.2. has_child và score_mode

Nếu query child có relevance score, `score_mode` quy định cách score của các child khớp được tổng hợp thành score của parent:

| Giá trị | Ý nghĩa |
|---|---|
| `none` | Không đưa score child vào score parent |
| `min` | Dùng score nhỏ nhất trong các child khớp |
| `max` | Dùng score lớn nhất |
| `sum` | Cộng score của các child |
| `avg` | Lấy trung bình score child |

Ví dụ:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "score_mode": "max",
      "query": {
        "match": {
          "answer": "Elasticsearch routing"
        }
      }
    }
  }
}
~~~

Parent được chấm điểm theo child có mức độ phù hợp cao nhất. Nếu chỉ cần lọc parent có child phù hợp và không cần score child ảnh hưởng thứ hạng, dùng `score_mode: "none"`.

### 4.3. inner_hits để lấy child khớp

`has_child` có thể dùng `inner_hits` để trả thêm những child đã khớp query:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "answer": "routing"
        }
      },
      "inner_hits": {
        "name": "matching_answers",
        "size": 5
      }
    }
  }
}
~~~

Hits chính là parent. Trong mỗi parent hit, inner hits có thể chứa tối đa 5 answer khớp truy vấn. Điều này hữu ích cho trang câu hỏi muốn hiển thị những câu trả lời liên quan ngay dưới câu hỏi.

## 5. Truy vấn has_parent

`has_parent` làm chiều ngược lại: tìm document child dựa trên điều kiện của document parent.

Ví dụ tìm các câu trả lời thuộc câu hỏi có category là `spring`:

~~~http
GET /forum/_search
Content-Type: application/json

{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "term": {
          "category": "spring"
        }
      }
    }
  }
}
~~~

Kết quả là các document `answer` có parent `question` thỏa điều kiện category. Điều kiện trong `has_parent` được đánh giá trên parent, nhưng document trả về là child.

### 5.1. has_parent và score

Theo mặc định, score của parent không nhất thiết được truyền sang child. Có thể bật `score: true` nếu muốn score parent ảnh hưởng đến score child:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "score": true,
      "query": {
        "match": {
          "question": "Spring Data Elasticsearch"
        }
      }
    }
  }
}
~~~

Dùng score khi relevance của parent có ý nghĩa đối với thứ hạng của child. Nếu parent chỉ được dùng như điều kiện lọc, không cần truyền score.

### 5.2. inner_hits để xem parent

Có thể yêu cầu `inner_hits` để lấy parent khớp với điều kiện:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "term": {
          "category": "spring"
        }
      },
      "inner_hits": {
        "name": "parent_question",
        "size": 1
      }
    }
  }
}
~~~

Hits chính là answer; inner hits cho phép lấy question parent tương ứng. Điều này hữu ích khi kết quả API hiển thị câu trả lời cùng thông tin câu hỏi gốc.

## 6. Truy vấn parent_id khi đã biết parent

Nếu đã biết ID của parent và chỉ muốn tìm các child thuộc parent đó, dùng `parent_id` query:

~~~json
{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "Q-100"
    }
  }
}
~~~

Query trả các child có relation type `answer` và parent ID `Q-100`. Đây là cách trực tiếp hơn `has_child` khi không cần điều kiện tìm kiếm phức tạp trên nội dung child để xác định parent.

Nếu biết parent ID và có routing value, có thể truyền routing vào search request để giới hạn tìm kiếm vào shard chứa quan hệ:

~~~http
GET /forum/_search?routing=Q-100
Content-Type: application/json

{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "Q-100"
    }
  }
}
~~~

Việc truyền routing khi search là một tối ưu phạm vi shard khi ứng dụng biết routing value. Nó không thay thế việc lưu parent và child với routing đúng ngay từ đầu.

## 7. Cập nhật và xóa parent-child

Vì parent và child là document riêng, có thể cập nhật chúng độc lập. Tuy nhiên, các thao tác ghi cần dùng đúng routing value.

### 7.1. Cập nhật child

~~~http
POST /forum/_update/A-1?routing=Q-100
Content-Type: application/json

{
  "doc": {
    "answer": "Updated answer about routing."
  }
}
~~~

Routing vẫn là ID của parent, không phải ID child. Nếu update child mà bỏ routing, Elasticsearch có thể tìm ở shard khác và trả về document không tồn tại dù child thực sự đang có trong index.

### 7.2. Xóa child

~~~http
DELETE /forum/_doc/A-1?routing=Q-100
~~~

Xóa child cũng phải dùng routing của parent. Hãy lưu routing key trong dữ liệu ứng dụng hoặc có cách xác định nó trước khi update/delete.

### 7.3. Xóa parent

Xóa parent không nên được hiểu là tự động xóa tất cả child. Ứng dụng cần xác định chính sách vòng đời:

- Xóa toàn bộ child trước, sau đó xóa parent.
- Dùng delete-by-query theo relation/parent ID với routing phù hợp, rồi xóa parent.
- Giữ child như dữ liệu lịch sử và chuyển trạng thái parent theo nghiệp vụ.

Không nên dựa vào giả định cascade delete. Hãy thiết kế quy trình xóa rõ ràng và kiểm thử trên phiên bản Elasticsearch đang chạy.

### 7.4. Bulk indexing

Khi dùng Bulk API, routing phải được đặt trên metadata action của từng document:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"index":{"_index":"forum","_id":"Q-100","routing":"Q-100"}}
{"question":"How does routing work?","relation":"question"}
{"index":{"_index":"forum","_id":"A-1","routing":"Q-100"}}
{"answer":"Routing keeps related documents on one shard.","relation":{"name":"answer","parent":"Q-100"}}
~~~

Nếu metadata action của child thiếu routing hoặc dùng routing khác, bulk request vẫn có thể được gửi nhưng quan hệ parent-child sẽ không được tạo đúng. Hãy kiểm tra kết quả từng item của bulk response, không chỉ kiểm tra HTTP status tổng thể.

## 8. Mô hình dữ liệu và ràng buộc cùng shard

Một quan hệ parent-child cần giữ ba yếu tố nhất quán:

1. Mapping join field định nghĩa đúng parent và child relation.
2. Child join value chứa đúng parent ID.
3. Routing của parent và child giống nhau để chúng nằm trên cùng shard.

Bảng ví dụ:

| Document | ID | Join field | Routing |
|---|---|---|---|
| Parent question | `Q-100` | `"question"` | `Q-100` |
| Child answer 1 | `A-1` | `{"name":"answer","parent":"Q-100"}` | `Q-100` |
| Child answer 2 | `A-2` | `{"name":"answer","parent":"Q-100"}` | `Q-100` |
| Child answer 3 | `A-3` | `{"name":"answer","parent":"Q-100"}` | `Q-100` |

Nếu parent có custom routing khác ID của nó, child phải dùng đúng routing value custom đó. Quy tắc cốt lõi là cùng routing value giữa parent và mọi descendant trong cùng quan hệ; dùng parent ID làm routing là quy ước phổ biến và dễ quản lý.

Không nên tạo child trước parent nếu ứng dụng chưa bảo đảm routing và quan hệ hợp lệ. Quy trình ghi thường tạo parent trước, sau đó mới tạo child. Nếu dữ liệu đến bất đồng bộ, cần xử lý trường hợp parent chưa tồn tại và retry hoặc đưa child vào hàng chờ.

## 9. Tích hợp parent-child với Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ join field qua `JoinField<T>`, annotation mapping quan hệ và routing metadata. Tên package hoặc chi tiết API có thể thay đổi theo release train, vì vậy cần đối chiếu Javadoc của dependency dự án.

### 9.1. Khai báo JoinField

Ví dụ model cho question và answer:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.mapping.JoinField;

@Document(indexName = "forum")
public class ForumDocument {

    @Id
    private String id;

    @Field(type = FieldType.Join)
    @JoinTypeRelations(
            relations = {
                    @JoinTypeRelation(
                            parent = "question",
                            children = {"answer"}
                    )
            }
    )
    private JoinField<String> relation;

    @Routing
    private String routing;

    @Field(type = FieldType.Text)
    private String question;

    @Field(type = FieldType.Text)
    private String answer;

    // constructors, getters and setters
}
~~~

`JoinField<String>` giữ tên relation và parent ID nếu document là child. `@JoinTypeRelations` khai báo các loại relation hợp lệ. `@Routing` đánh dấu thuộc tính chứa routing value mà Spring Data cần dùng khi gửi thao tác index/search/update tương ứng.

Với parent:

~~~java
ForumDocument question = new ForumDocument();
question.setId("Q-100");
question.setQuestion("How does routing work?");
question.setRelation(new JoinField<>("question", null));
question.setRouting("Q-100");
~~~

Với child:

~~~java
ForumDocument answer = new ForumDocument();
answer.setId("A-1");
answer.setAnswer("Parent and child must share one shard.");
answer.setRelation(new JoinField<>("answer", "Q-100"));
answer.setRouting("Q-100");
~~~

Hai entity có ID khác nhau và nội dung khác nhau, nhưng dùng chung routing. Child relation tham chiếu parent ID trong JoinField.

### 9.2. Lưu entity

Khi entity đã được cấu hình join field và routing metadata, có thể dùng `ElasticsearchOperations` hoặc repository để lưu theo API phiên bản:

~~~java
operations.save(question);
operations.save(answer);
~~~

Ví dụ này giả định Spring Data mapping context nhận ra thuộc tính `@Routing` và lấy đúng giá trị routing từ entity. Hãy kiểm tra request được gửi ra thực tế hoặc xác nhận document nằm cùng shard trước khi triển khai. Nếu phiên bản đang dùng không tự áp dụng routing cho thao tác cụ thể, hãy truyền routing rõ ràng qua API index/query tương ứng của client.

Không chỉ set `JoinField` rồi mặc định rằng Spring Data sẽ tự suy ra routing từ parent ID. `JoinField` mô tả quan hệ; routing là thông tin riêng cần được đặt rõ ràng.

### 9.3. Truy vấn bằng NativeQuery

Các truy vấn `has_child`, `has_parent` và `parent_id` là Elasticsearch Query DSL. Với Spring Data Elasticsearch, có thể dùng `NativeQuery` và Elasticsearch Java Client để xây dựng query:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.hasChild(hc -> hc
                .type("answer")
                .query(childQuery)
                .scoreMode(ChildScoreMode.Max)
        ))
        .build();

SearchHits<ForumDocument> hits =
        operations.search(query, ForumDocument.class);
~~~

Đoạn code minh họa cấu trúc builder. Tên enum, package và overload của `hasChild`, `hasParent`, `parentId` phụ thuộc phiên bản Elasticsearch Java Client. Có thể dùng JSON DSL trong `@Query` cho cấu trúc cố định; với query động hoặc inner hits, NativeQuery thường linh hoạt hơn.

## 10. Routing trong Spring Data và Elasticsearch Java Client

Routing là một phần của hợp đồng dữ liệu parent-child. Ứng dụng nên có một quy tắc duy nhất để xác định routing value:

- Parent: routing value theo parent ID hoặc routing key đã chọn.
- Child: lấy routing key của parent.
- Update/delete child: dùng lại routing key của parent.
- Search theo một parent cụ thể: có thể truyền routing để giới hạn shard.

Nếu dùng Spring Data annotation `@Routing`, bảo đảm thuộc tính routing được gán trước khi gọi save. Nếu thao tác được thực hiện bằng Elasticsearch Java Client trực tiếp, phải set routing trong request options/builder tương ứng.

Không nên để mỗi service tự xây routing theo quy tắc khác nhau. Một helper hoặc domain method có thể trả về routing key để tất cả luồng ghi, cập nhật và xóa dùng thống nhất.

## 11. Hiệu năng và chi phí parent-child

Parent-child join cho phép cập nhật child độc lập mà không cần viết lại toàn bộ parent, nhưng có chi phí:

- Join query cần phối hợp dữ liệu relation trong shard.
- `has_child` và `has_parent` có thể tốn tài nguyên đáng kể so với query term/range thông thường.
- Join field sử dụng global ordinals; việc xây dựng hoặc cập nhật ordinals có thể ảnh hưởng chi phí refresh và bộ nhớ.
- Một parent có số lượng child rất lớn có thể làm query tổng hợp score hoặc inner hits nặng hơn.
- Routing theo parent có thể tạo phân phối shard không cân bằng nếu một parent có quá nhiều child.

Vì vậy, parent-child không phải cách thay thế mặc định cho nested object. Chỉ dùng khi lợi ích cập nhật độc lập hoặc cardinality parent-child đủ lớn để bù chi phí join.

### 11.1. Tránh parent nóng

Nếu một parent có hàng triệu child, tất cả document của quan hệ đó phải nằm cùng shard. Một parent như vậy có thể tạo hotspot: một shard nhận phần lớn dữ liệu và lưu lượng ghi/đọc của quan hệ.

Hãy ước lượng số child tối đa trên mỗi parent và phân bố parent trên shard. Nếu dữ liệu có một số parent cực lớn, cần cân nhắc mô hình khác như denormalization, tách index hoặc phân vùng nghiệp vụ.

### 11.2. So sánh với nested và denormalization

| Mô hình | Cách lưu | Ưu điểm | Chi phí/giới hạn |
|---|---|---|---|
| Object lồng thông thường | Một document có object/array | Đơn giản | Không bảo đảm quan hệ cùng phần tử khi truy vấn các object trong array |
| Nested | Child object được index như nested document trong cùng root | Truy vấn chính xác theo object con, không cần join giữa hai root document | Cập nhật nested object thường cần index lại root document |
| Parent-child | Parent và child là document riêng, join field | Cập nhật child độc lập, một parent có nhiều child | Cùng shard, join query tốn chi phí |
| Denormalization | Sao chép dữ liệu cần truy vấn vào document | Query đơn giản và nhanh | Phải đồng bộ dữ liệu trùng lặp |

Nếu dữ liệu con nhỏ, luôn được đọc cùng cha và thường cập nhật cùng nhau, nested thường phù hợp hơn. Nếu cần query nhanh và chấp nhận sao chép một số field parent vào child, denormalization có thể đơn giản hơn. Parent-child hữu ích khi child nhiều, thay đổi độc lập và quan hệ thực sự cần truy vấn hai chiều.

## 12. Thay đổi mapping và di chuyển dữ liệu

Join field phải được khai báo trong mapping trước khi index document. Không thể tùy ý thay một field thông thường thành join field trên index đang có dữ liệu và kỳ vọng mọi quan hệ tự xuất hiện.

Nếu cần bổ sung hoặc thay đổi mô hình parent-child:

1. Tạo index mới với join mapping hoàn chỉnh.
2. Xác định parent ID và routing key cho từng document.
3. Index parent với routing key đã chọn.
4. Index child với cùng routing key và join value chứa parent ID.
5. Kiểm tra parent-child cùng shard và truy vấn quan hệ.
6. Reindex/chuyển dữ liệu theo batch có kiểm soát.
7. Chuyển alias sang index mới khi dữ liệu đã sẵn sàng.

Khi reindex dữ liệu parent-child, cần giữ cả join field lẫn routing. Nếu script hoặc pipeline chỉ copy _source mà không bảo toàn routing metadata, document có thể bị phân phối sai shard và quan hệ bị hỏng.

## 13. Những lỗi thường gặp

### 13.1. Chỉ ghi parent ID mà quên routing

Join field child chứa đúng parent ID nhưng child vẫn có thể nằm shard khác nếu không truyền routing. Luôn đặt routing của child bằng routing của parent.

### 13.2. Routing child theo chính ID của child

Routing mặc định theo child ID có thể đưa child sang shard khác. Dùng routing key của parent cho mọi child.

### 13.3. Nghĩ cùng index là đủ

Parent và child phải cùng index và cùng shard. Cùng index nhưng khác shard vẫn không thể join.

### 13.4. Update hoặc delete mà thiếu routing

Thao tác có thể tìm sai shard và báo document không tồn tại. Lưu routing key hoặc tính lại được routing key trước thao tác.

### 13.5. Nhầm relation name với tên field

Trong `has_child`, `type` là tên child relation được khai báo trong join mapping, không phải tên field văn bản của child.

### 13.6. Dùng has_parent khi cần parent làm kết quả

`has_parent` trả child document khớp điều kiện parent. `has_child` trả parent document có child khớp. Chọn theo loại document muốn nhận.

### 13.7. Mong muốn cascade delete

Xóa parent không nên được giả định sẽ tự động xóa mọi child. Thiết kế quy trình xóa child và parent rõ ràng.

### 13.8. Dùng parent-child cho mọi quan hệ

Join query tốn chi phí và routing có thể gây hotspot. So sánh với nested và denormalization trước khi chọn.

## 14. Kiểm thử quan hệ cùng shard

Một integration test nên xác nhận cả mapping, routing và truy vấn:

1. Tạo index với join field relation question → answer.
2. Index parent `Q-100` với routing `Q-100`.
3. Index child `A-1` với parent `Q-100` và routing `Q-100`.
4. Refresh index hoặc dùng cơ chế chờ hiển thị dữ liệu phù hợp trong test.
5. Chạy `has_child` và xác nhận parent được trả về.
6. Chạy `has_parent` và xác nhận child được trả về.
7. Chạy `parent_id` với parent ID đã biết.
8. Update child với routing parent và xác nhận dữ liệu thay đổi.
9. Thử một child có routing sai để thấy thao tác không tạo quan hệ hợp lệ hoặc truy vấn không tìm thấy như mong đợi.
10. Kiểm tra response từng item khi dùng Bulk API.

Có thể kiểm tra shard của document bằng API explain hoặc search shard-level trong môi trường kiểm thử, nhưng quan trọng nhất là xác nhận routing được áp dụng nhất quán trên mọi thao tác. Không dựa vào việc một test nhỏ tình cờ đưa parent và child vào cùng shard khi dùng routing mặc định.

## 15. Quy trình thiết kế parent-child

Khi cân nhắc mô hình này:

1. Xác định hai loại document và quan hệ một-cha-nhiều-con.
2. Xác nhận child cần được cập nhật độc lập với parent.
3. So sánh với nested và denormalization.
4. Thiết kế một join field và khai báo relation mapping.
5. Chọn routing key ổn định; thường dùng ID của parent.
6. Bảo đảm parent, mọi child và các descendant dùng cùng routing value.
7. Lưu routing key trong domain model hoặc tính được từ quan hệ.
8. Dùng has_child, has_parent hoặc parent_id theo loại document cần tìm.
9. Thiết kế update/delete/reindex để giữ routing.
10. Đánh giá chi phí join, global ordinals và phân bố parent trên shard.
11. Kiểm thử dữ liệu thật với số lượng child đại diện.

## 16. Kết luận

`has_child` tìm parent dựa trên điều kiện của child; `has_parent` tìm child dựa trên điều kiện của parent. Join field khai báo loại quan hệ và parent ID trên child document. Parent và child vẫn là các document độc lập trong cùng index.

Điều kiện kỹ thuật không thể bỏ qua là parent và child phải nằm trên cùng shard. Hãy truyền cùng một routing value khi index parent và mọi child; quy ước phổ biến là routing bằng ID của parent. `relation.parent` trong join field ghi parent ID, còn tham số `routing` quyết định shard; hai giá trị có thể trùng nhau nhưng phục vụ hai vai trò khác nhau.

Trong Spring Data Elasticsearch, `JoinField`, `@JoinTypeRelations` và `@Routing` hỗ trợ biểu diễn quan hệ và routing metadata. Cần kiểm tra phiên bản thực tế và xác nhận routing được gửi đúng trong các thao tác save/update/delete. Parent-child hữu ích khi child cần vòng đời độc lập, nhưng phải cân nhắc chi phí join, global ordinals, hotspot shard và so sánh với nested hoặc denormalization trước khi áp dụng.
