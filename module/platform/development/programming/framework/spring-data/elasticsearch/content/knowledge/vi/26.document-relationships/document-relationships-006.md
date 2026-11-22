# @JoinTypeRelations, JoinField và cách ánh xạ

Spring Data Elasticsearch hỗ trợ quan hệ parent-child của Elasticsearch thông qua join field. Hai thành phần chính ở phía Java là:

- **@JoinTypeRelations** khai báo sơ đồ quan hệ: loại document nào là parent và những loại document nào là child của nó.
- **JoinField<ID>** biểu diễn vai trò của một document cụ thể trong quan hệ: tên relation của document và ID của parent nếu document đó là child.

Cặp annotation và kiểu dữ liệu này giúp Spring Data tạo mapping có kiểu join và chuyển đổi giá trị quan hệ khi ghi/đọc document. Nó không tạo association object như JPA. Parent và child vẫn là các document độc lập trong cùng index; Elasticsearch duy trì liên kết bằng join field và routing.

## 1. Parent-child trong Elasticsearch

Giả sử một diễn đàn có câu hỏi và câu trả lời. Một câu hỏi có thể có nhiều câu trả lời:

~~~text
Question Q-100
    ├── Answer A-101
    ├── Answer A-102
    └── Answer A-103
~~~

Có thể lưu mỗi phần tử thành một document riêng trong cùng index:

| Document ID | Relation name | Parent ID |
| --- | --- | --- |
| Q-100 | question | Không có |
| A-101 | answer | Q-100 |
| A-102 | answer | Q-100 |
| A-103 | answer | Q-100 |

Document parent mang tên relation của parent. Document child mang tên relation của child cùng ID của parent.

Join field là mapping đặc biệt của Elasticsearch để mô tả các loại document và quan hệ giữa chúng. Nó cho phép dùng những query như has_child, has_parent và parent_id để tìm document theo quan hệ.

Parent-child không giống foreign key hoặc JOIN của cơ sở dữ liệu quan hệ:

- Các document vẫn được index và cập nhật độc lập.
- Quan hệ chỉ tồn tại trong phạm vi một index.
- Parent và child phải nằm trên cùng một shard.
- Elasticsearch không tự tải toàn bộ object graph như ORM.
- Mỗi lần dùng join query phải trả thêm chi phí xử lý so với truy vấn document đã được denormalize.

Vì vậy, chỉ nên chọn join khi cần cập nhật parent và child độc lập, đồng thời một parent có thể có số lượng child lớn. Nếu dữ liệu ít thay đổi và có thể sao chép thông tin parent vào child, denormalization thường đơn giản và nhanh hơn.

## 2. @JoinTypeRelations khai báo sơ đồ quan hệ

Spring Data Elasticsearch dùng annotation @JoinTypeRelations trên property JoinField để khai báo các cặp parent-child.

Ví dụ một câu hỏi có thể có câu trả lời và bình luận:

~~~java
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "question",
            children = {"answer", "comment"}
        )
    }
)
private JoinField<String> relation;
~~~

Trong đó:

- parent = "question": tên relation của document cha.
- children = {"answer", "comment"}: những relation được phép làm con trực tiếp của question.
- relation: tên property Java chứa giá trị join cho từng document.

Có thể khai báo nhiều quan hệ trong cùng annotation. Ví dụ answer có thể có vote:

~~~java
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "question",
            children = {"answer", "comment"}
        ),
        @JoinTypeRelation(
            parent = "answer",
            children = "vote"
        )
    }
)
private JoinField<String> relation;
~~~

Sơ đồ quan hệ:

~~~text
question
   ├── answer
   │      └── vote
   └── comment
~~~

Tên relation là tên logic trong mapping Elasticsearch, không bắt buộc trùng tên class Java. Trong ví dụ này, nhiều loại document có thể được biểu diễn bằng cùng một entity Java và phân biệt bằng giá trị relation.

### 2.1. Quy tắc khai báo

Một annotation @JoinTypeRelations có thể chứa nhiều @JoinTypeRelation. Mỗi @JoinTypeRelation định nghĩa một parent và một hoặc nhiều child type.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| parent | Tên relation của parent document. |
| children | Một hoặc nhiều tên relation được phép làm child trực tiếp của parent. |
| relations | Mảng các định nghĩa @JoinTypeRelation đặt trong @JoinTypeRelations. |

Một child chỉ có một parent trong mô hình join. Một parent có thể có nhiều child document và có thể có nhiều loại child khác nhau.

Tên relation trong annotation phải thống nhất với tên được truyền vào JoinField khi tạo document. Nếu mapping khai báo child là answer nhưng code tạo JoinField với tên response, Elasticsearch không thể coi response là loại child đã khai báo.

## 3. JoinField biểu diễn quan hệ của từng document

JoinField là kiểu dữ liệu của Spring Data Elasticsearch:

~~~java
org.springframework.data.elasticsearch.core.join.JoinField<ID>
~~~

Tham số generic ID phải cùng kiểu với property được đánh dấu @Id của entity.

Ví dụ entity dùng:

~~~java
@Id
private String id;
~~~

thì property quan hệ nên là:

~~~java
private JoinField<String> relation;
~~~

Nếu ID là Long thì dùng JoinField<Long>. Không nên khai báo JoinField<Object> hoặc dùng một kiểu ID khác với entity ID vì Spring Data cần chuyển đổi parent ID đúng kiểu.

JoinField có các constructor thường dùng:

~~~java
new JoinField<>("question")
new JoinField<>("answer", parentId)
~~~

Constructor chỉ có tên relation được dùng cho document parent. Constructor có thêm parent ID được dùng cho document child.

| Java value | Ý nghĩa | Dữ liệu join trong _source |
| --- | --- | --- |
| new JoinField<>("question") | Document là question parent. | "question" hoặc object relation tương ứng. |
| new JoinField<>("answer", "Q-100") | Document là answer child của Q-100. | {"name":"answer","parent":"Q-100"} |
| new JoinField<>("comment", "Q-100") | Document là comment child của Q-100. | {"name":"comment","parent":"Q-100"} |

JoinField không chứa danh sách child ID. Khi tạo parent, chỉ cần tên relation. Mỗi child tự giữ parent ID của nó.

## 4. Khai báo entity Spring Data Elasticsearch

Ví dụ một index statements chứa question, answer và comment. Tất cả dùng chung một entity class:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "statements")
public class Statement {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String text;

    @JoinTypeRelations(
        relations = {
            @JoinTypeRelation(
                parent = "question",
                children = {"answer", "comment"}
            )
        }
    )
    private JoinField<String> relation;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }

    public JoinField<String> getRelation() {
        return relation;
    }

    public void setRelation(JoinField<String> relation) {
        this.relation = relation;
    }
}
~~~

Điểm cần chú ý:

- @Document xác định index chứa các document.
- @Id xác định ID của từng document.
- @JoinTypeRelations nằm trên property JoinField.
- JoinField generic String khớp với kiểu ID String.
- Không cần tạo property Java dạng List<Answer> để khai báo quan hệ. Join mapping được định nghĩa bởi annotation.

Không đặt @JoinTypeRelations lên class hoặc lên một field text thông thường. Annotation này mô tả mapping cho property JoinField.

## 5. Mapping Elasticsearch được tạo

Từ entity ở trên, Spring Data Elasticsearch tạo mapping join tương ứng. Phần quan trọng có dạng:

~~~json
{
  "mappings": {
    "properties": {
      "text": {
        "type": "text"
      },
      "relation": {
        "type": "join",
        "eager_global_ordinals": true,
        "relations": {
          "question": ["answer", "comment"]
        }
      }
    }
  }
}
~~~

Tên field relation trong mapping là tên property Java, trừ khi mapping được tùy chỉnh bằng cấu hình tương ứng. Trong ví dụ, property relation trở thành field có type join. Property được đánh dấu @Id là metadata ID của document (Elasticsearch _id), không phải field thông thường trong properties của mapping.

Một số điểm quan trọng:

- type: join đánh dấu field quan hệ.
- relations định nghĩa parent-child types.
- eager_global_ordinals thường được bật trong mapping join do Spring Data tạo.
- Join field là một field mapping duy nhất cho sơ đồ quan hệ của index.

Nếu tạo mapping thủ công bằng JSON, cấu trúc relations phải tương ứng với annotation và tên relation trong JoinField. Tránh để mapping JSON và annotation mô tả hai sơ đồ khác nhau.

### 5.1. Một index chỉ có một join field mapping

Elasticsearch chỉ cho phép một join field mapping trong mỗi index. Field join đó có thể chứa nhiều quan hệ, nhưng không thể tạo nhiều field join độc lập để mô hình hóa các cây quan hệ không liên quan trong cùng index.

Nếu một index cần nhiều kiểu quan hệ, hãy thiết kế chúng trong cùng một relations map hoặc xem xét tách index / denormalize dữ liệu.

### 5.2. Mở rộng sơ đồ quan hệ

Có thể khai báo nhiều loại child cho cùng parent:

~~~java
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "product",
            children = {"offer", "review", "question"}
        )
    }
)
private JoinField<String> relation;
~~~

Sơ đồ:

~~~text
product
  ├── offer
  ├── review
  └── question
~~~

Nếu cần thêm quan hệ mới vào join field đã tồn tại, Elasticsearch có hỗ trợ bổ sung relation. Tuy nhiên, phải bảo đảm code, mapping và dữ liệu được cập nhật đồng bộ; kiểm tra API mapping và phiên bản cluster trước khi triển khai thay đổi.

## 6. Tạo và lưu parent document

Parent document được tạo với tên relation và không có parent ID:

~~~java
Statement question = new Statement();
question.setText("How is the weather?");
question.setRelation(new JoinField<>("question"));

Statement savedQuestion = repository.save(question);
~~~

Spring Data chuyển JoinField thành giá trị join trong document. Với parent, Elasticsearch cho phép biểu diễn ngắn gọn bằng tên relation:

~~~json
{
  "text": "How is the weather?",
  "relation": "question"
}
~~~

Có thể tự đặt ID trước khi save nếu ứng dụng cần ID ổn định. Nếu ID được Elasticsearch/Spring Data sinh hoặc được gán khi lưu, phải dùng ID thực tế của parent đã lưu khi tạo child.

## 7. Tạo và lưu child document

Child cần hai thông tin:

1. Tên relation của child đã khai báo trong @JoinTypeRelations.
2. ID của parent document.

Ví dụ tạo answer cho question vừa lưu:

~~~java
Statement answer = new Statement();
answer.setText("Sunny");
answer.setRelation(
    new JoinField<>("answer", savedQuestion.getId())
);

Statement savedAnswer = repository.save(answer);
~~~

Document child được biểu diễn trong _source theo dạng:

~~~json
{
  "text": "Sunny",
  "relation": {
    "name": "answer",
    "parent": "question-id"
  }
}
~~~

Trong đó question-id là ID thực tế của savedQuestion.

Một parent có thể có nhiều child:

~~~java
Statement firstAnswer = new Statement();
firstAnswer.setText("Sunny");
firstAnswer.setRelation(
    new JoinField<>("answer", savedQuestion.getId())
);
repository.save(firstAnswer);

Statement secondAnswer = new Statement();
secondAnswer.setText("Rainy");
secondAnswer.setRelation(
    new JoinField<>("answer", savedQuestion.getId())
);
repository.save(secondAnswer);
~~~

Mỗi child là một document độc lập. Lưu child không tự thêm child vào một collection trong parent entity.

## 8. Routing: parent và child phải ở cùng shard

Đây là quy tắc bắt buộc của Elasticsearch parent-child: parent và child phải nằm trên cùng shard. Elasticsearch dùng routing value để xác định shard của document.

Nếu parent được index theo ID Q-100 thì child của nó phải dùng routing value Q-100. Nếu không, Elasticsearch có thể lưu parent và child ở hai shard khác nhau và quan hệ không hoạt động đúng.

Với quan hệ một cấp, Spring Data Elasticsearch tự sử dụng giá trị parent trong JoinField làm routing khi lưu child.

Ví dụ:

~~~java
Statement answer = new Statement();
answer.setText("Sunny");
answer.setRelation(new JoinField<>("answer", questionId));

repository.save(answer);
~~~

Trong trường hợp này, parent ID được dùng làm routing value cho child.

### 8.1. Routing khi có nhiều cấp

Giả sử sơ đồ có ba tầng:

~~~text
question Q-100
    └── answer A-101
            └── vote V-201
~~~

JoinField của vote phải chứa ID của parent trực tiếp là answer A-101:

~~~java
new JoinField<>("vote", answerId)
~~~

Nhưng routing của vote phải là ID của ancestor cao nhất, tức question Q-100, để cả question, answer và vote nằm cùng shard.

Không dùng answerId làm routing của vote trong ví dụ nhiều cấp. Parent ID trong JoinField và routing value có thể khác nhau:

| Giá trị | Vote |
| --- | --- |
| JoinField name | vote |
| JoinField parent | A-101 |
| Routing | Q-100 |

Spring Data tự lấy parent property của JoinField làm routing đúng cho quan hệ một cấp. Với cây nhiều cấp, cần khai báo routing tùy chỉnh để dùng ID của root ancestor.

### 8.2. Khai báo @Routing

Spring Data Elasticsearch hỗ trợ @Routing trên entity để chỉ định property chứa routing value:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "statements")
@Routing("routing")
public class Statement {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String text;

    @Field(type = FieldType.Keyword)
    private String routing;

    @JoinTypeRelations(
        relations = {
            @JoinTypeRelation(parent = "question", children = {"answer", "comment"}),
            @JoinTypeRelation(parent = "answer", children = "vote")
        }
    )
    private JoinField<String> relation;

    // getters và setters
}
~~~

Khi @Routing nhận một chuỗi property name như "routing", Spring Data lấy giá trị từ property routing để gửi làm routing cho request.

Có thể tạo dữ liệu nhiều cấp như sau:

~~~java
Statement question = new Statement();
question.setText("How is the weather?");
question.setRelation(new JoinField<>("question"));
question.setRouting(null);

Statement savedQuestion = repository.save(question);

Statement answer = new Statement();
answer.setText("Sunny");
answer.setRelation(new JoinField<>("answer", savedQuestion.getId()));
answer.setRouting(savedQuestion.getId());

Statement savedAnswer = repository.save(answer);

Statement vote = new Statement();
vote.setText("+1 for the sun");
vote.setRelation(new JoinField<>("vote", savedAnswer.getId()));
vote.setRouting(savedQuestion.getId());

repository.save(vote);
~~~

Đây là minh họa về dữ liệu routing. Trong ứng dụng thực tế, cần thống nhất cách route cả parent và child từ đầu. Với parent root, routing mặc định theo ID của document; child dùng cùng giá trị ID đó. Với vote, routing vẫn là ID của question dù JoinField parent là ID của answer.

Nếu custom routing được khai báo, mọi thao tác get, update hoặc delete cần dùng cùng routing value đã sử dụng khi index document.

### 8.3. Lấy hoặc xóa document có routing

Khi thao tác theo ID mà không truyền entity, cần cung cấp routing tương ứng:

~~~java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;

String childId = "A-101";
String routingValue = "Q-100";

Statement answer = operations
    .withRouting(RoutingResolver.just(routingValue))
    .get(childId, Statement.class);

operations
    .withRouting(RoutingResolver.just(routingValue))
    .delete(childId);
~~~

Tên API có thể thay đổi theo phiên bản Spring Data Elasticsearch. Nguyên tắc không đổi: get, update và delete phải định tuyến đến đúng shard chứa document.

## 9. Truy vấn parent-child

Spring Data Elasticsearch không cung cấp derived repository method thông thường để tự suy ra join query từ tên method. Cần dùng native query hoặc custom repository implementation.

Elasticsearch hỗ trợ các truy vấn quan hệ chính:

| Query | Mục đích |
| --- | --- |
| has_child | Tìm parent document có child thỏa query. |
| has_parent | Tìm child document có parent thỏa query. |
| parent_id | Tìm child document theo ID của parent. |

### 9.1. has_child

Tìm các question có ít nhất một answer chứa từ Sunny:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "Sunny"
        }
      }
    }
  }
}
~~~

has_child chạy query bên trong trên child type đã khai báo. Kết quả là document parent của child phù hợp.

### 9.2. has_parent

Tìm answer có question parent chứa cụm How is the weather:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "match": {
          "text": "How is the weather"
        }
      }
    }
  }
}
~~~

Kết quả là các child document thuộc parent thỏa query.

### 9.3. parent_id

Nếu đã biết parent ID và muốn lấy child của parent đó:

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

Trong đó type là tên child relation và id là ID của parent. Query này hữu ích khi chỉ cần lấy các child trực tiếp của một parent đã biết.

### 9.4. NativeQuery trong Spring Data

Có thể tạo has_child query bằng Elasticsearch Java API Client rồi gắn vào NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.ChildScoreMode;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query hasSunnyAnswer = Query.of(q -> q.hasChild(h -> h
    .type("answer")
    .query(child -> child.match(m -> m
        .field("text")
        .query("Sunny")))
    .scoreMode(ChildScoreMode.None)
));

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(hasSunnyAnswer)
    .build();

SearchHits<Statement> hits =
    operations.search(nativeQuery, Statement.class);
~~~

Trong ví dụ này:

- type("answer") xác định child relation cần tìm.
- query(...) là điều kiện chạy trên document answer.
- scoreMode điều khiển cách score của child ảnh hưởng tới parent.
- ElasticsearchOperations thực thi NativeQuery.

Nếu ứng dụng dùng Spring Data Elasticsearch phiên bản cũ với High Level REST Client, cách tạo native query khác. Hãy dùng API tương ứng với client mà phiên bản Spring Data đang quản lý.

## 10. Join field trong response

Khi search, Elasticsearch trả join field cùng document. Parent có thể có dạng:

~~~json
{
  "_id": "Q-100",
  "_source": {
    "text": "How is the weather?",
    "relation": "question"
  }
}
~~~

Child có thể có dạng:

~~~json
{
  "_id": "A-101",
  "_routing": "Q-100",
  "_source": {
    "text": "Sunny",
    "relation": {
      "name": "answer",
      "parent": "Q-100"
    }
  }
}
~~~

Join field không biến hai document thành một object lồng nhau. Khi đọc kết quả qua SearchHits<Statement>, mỗi hit là một Statement riêng. Nếu ứng dụng muốn trả Question cùng danh sách Answer, cần tự nhóm các document hoặc chạy truy vấn phù hợp rồi ghép kết quả ở tầng service.

## 11. Giới hạn của parent-child mapping

Elasticsearch đặt ra các giới hạn quan trọng:

1. Mỗi index chỉ được có một join field mapping.
2. Parent và child phải nằm cùng shard.
3. Một child chỉ có một parent.
4. Một parent có thể có nhiều child.
5. Child chỉ có thể được thêm vào một document đã đóng vai trò parent trong sơ đồ relation.
6. Quan hệ không nối qua hai index khác nhau.
7. Join query và join aggregation có chi phí đáng kể hơn truy vấn field thông thường.

Một document có thể đồng thời là child trong quan hệ với tầng trên và là parent của loại document ở tầng dưới, như answer trong ví dụ question → answer → vote.

## 12. Chi phí global ordinals

Join field sử dụng global ordinals để hỗ trợ truy vấn quan hệ. Global ordinals được xây dựng trên dữ liệu của shard và cần cập nhật sau khi shard thay đổi.

Trong mapping join, eager_global_ordinals thường được bật. Điều đó có nghĩa global ordinals được xây dựng trong quá trình refresh, giúp tránh độ trễ tăng đột ngột ở lần join query đầu tiên sau khi dữ liệu thay đổi. Đổi lại, refresh có thể tốn thêm thời gian.

Có thể cân nhắc eager_global_ordinals = false nếu:

- Index ghi dữ liệu thường xuyên.
- Join query rất ít khi được sử dụng.
- Có thể chấp nhận chi phí xây dựng ordinals ở lần truy vấn join đầu tiên sau refresh.

Ví dụ mapping thủ công:

~~~json
{
  "mappings": {
    "properties": {
      "relation": {
        "type": "join",
        "relations": {
          "question": ["answer", "comment"]
        },
        "eager_global_ordinals": false
      }
    }
  }
}
~~~

Không nên tắt eager loading chỉ để giảm thời gian refresh nếu join query là luồng truy cập chính. Cần benchmark cả write latency, refresh latency và query latency.

## 13. Parent-child hay denormalization?

Join mapping không nên được dùng như cách thay thế mọi quan hệ trong cơ sở dữ liệu quan hệ.

| Tiêu chí | Parent-child join | Denormalization |
| --- | --- | --- |
| Lưu parent và child | Document độc lập trong cùng index. | Có thể nhúng child hoặc sao chép field parent vào document. |
| Cập nhật child độc lập | Có. | Có thể cập nhật document child riêng nếu tách document, nhưng dữ liệu lặp cần đồng bộ. |
| Truy vấn theo quan hệ | has_child, has_parent, parent_id. | Query trực tiếp trên field đã sao chép/nhúng. |
| Chi phí truy vấn | Cao hơn do join và global ordinals. | Thường đơn giản và nhanh hơn. |
| Phù hợp | Một parent có rất nhiều child và cần cập nhật riêng. | Dữ liệu đọc nhiều, cấu trúc tương đối ổn định, chấp nhận sao chép dữ liệu. |

Ví dụ sản phẩm có hàng nghìn offer thường là trường hợp có thể cân nhắc parent-child nếu offer cần được cập nhật độc lập. Nếu mỗi sản phẩm chỉ có vài review và chủ yếu đọc cùng nhau, nhúng hoặc sao chép dữ liệu có thể phù hợp hơn.

## 14. Lỗi thường gặp khi ánh xạ JoinField

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Spring Data không tạo join mapping | Property không có kiểu JoinField hoặc thiếu @JoinTypeRelations. | Kiểm tra kiểu field và annotation trên đúng property. |
| Lỗi relation không được định nghĩa | Tên truyền vào JoinField không có trong children của annotation. | Đồng bộ tên relation trong mapping và code. |
| Child không tìm được parent | Parent và child nằm khác shard do routing sai. | Dùng cùng routing value của root parent. |
| Child được lưu nhưng has_child không trả parent | Query dùng sai child type hoặc parent ID/routing không đúng. | Kiểm tra mapping, _source và query type. |
| Không lấy được child bằng get(id) | Request thiếu routing đã dùng khi index. | Dùng withRouting hoặc routing resolver phù hợp. |
| JoinField generic không chuyển đổi đúng | Kiểu generic khác kiểu @Id. | Dùng cùng kiểu ID, ví dụ JoinField<String> với @Id String. |
| Cây nhiều cấp không hoạt động | Dùng ID parent trực tiếp làm routing thay vì root ancestor. | Giữ parent ID trong JoinField và route bằng ID ancestor cao nhất. |
| Refresh chậm sau khi ghi nhiều document | Global ordinals của join field phải được cập nhật. | Đo eager_global_ordinals và cân nhắc mô hình dữ liệu khác. |
| Repository derived query không hỗ trợ join | Join query cần native query. | Dùng NativeQuery và custom repository implementation. |

## 15. Quy trình triển khai mapping quan hệ

Khi thiết kế parent-child trong Spring Data Elasticsearch, hãy thực hiện theo trình tự:

1. Xác định parent type và child type theo nghiệp vụ.
2. Kiểm tra quan hệ có thực sự cần cập nhật parent/child độc lập không.
3. Khai báo một property JoinField trên entity.
4. Khai báo @JoinTypeRelations với đầy đủ parent và children.
5. Bảo đảm generic của JoinField khớp kiểu @Id.
6. Tạo mapping và kiểm tra field có type join cùng relations đúng.
7. Khi lưu parent, dùng JoinField với tên relation parent.
8. Khi lưu child, dùng JoinField với tên child và ID parent trực tiếp.
9. Bảo đảm routing của parent và toàn bộ lineage nằm cùng shard.
10. Với cây nhiều cấp, route child sâu bằng ID root ancestor.
11. Dùng NativeQuery cho has_child, has_parent hoặc parent_id.
12. Đo chi phí global ordinals và join query bằng dữ liệu gần production.

## 16. Tài liệu tham khảo

- [Spring Data Elasticsearch — Join-Type implementation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/join-types.html)
- [Spring Data Elasticsearch — Routing values](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/routing.html)
- [Spring Data Elasticsearch — JoinField API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/join/JoinField.html)
- [Spring Data Elasticsearch — JoinTypeRelations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/JoinTypeRelations.html)
- [Elasticsearch — Join field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join)

@JoinTypeRelations mô tả các loại parent-child được phép trong mapping; JoinField xác định vai trò và parent ID của từng document. Spring Data chuyển chúng thành Elasticsearch join field và hỗ trợ routing theo parent cho quan hệ một cấp. Khi có nhiều cấp, phải giữ routing theo root ancestor. Join query cần native query và có chi phí global ordinals, vì vậy chỉ dùng parent-child khi lợi ích cập nhật độc lập thực sự cần thiết.

