# Phân biệt lời gọi hàng loạt với đảm bảo về hiệu năng hàng loạt

Bài học này thuộc chương **Repository CRUD** của module **SPRING_DATA_NEO4J**. Khi cần ghi nhiều node vào Neo4j, Spring Data Neo4j cung cấp `saveAll()` để lưu một tập entity qua repository hoặc `Neo4jTemplate`. Tuy nhiên, tên phương thức và việc truyền nhiều entity trong một lần gọi không tự động đảm bảo rằng toàn bộ dữ liệu được ghi bằng một câu Cypher, một network round trip hoặc một transaction có kích thước phù hợp.

Để lựa chọn đúng, cần phân biệt ba cấp độ: **API hàng loạt** là cách ứng dụng gọi một thao tác cho nhiều entity; **truy vấn hàng loạt** là cách gửi nhiều dòng dữ liệu vào một câu Cypher, thường dùng `UNWIND`; **chia lô transaction** là cách chia tập dữ liệu lớn thành các nhóm nhỏ có ranh giới commit riêng. Ba cấp độ có thể kết hợp nhưng không đồng nghĩa với nhau.

## 1. `saveAll()` đảm bảo điều gì?

Repository Spring Data Neo4j kế thừa CRUD API và cung cấp `saveAll(Iterable<S> entities)`. Ví dụ:

```java
import com.example.graph.domain.Person;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Ứng dụng có thể lưu nhiều người trong một lời gọi:

```java
import java.util.List;

List<Person> people = List.of(
    new Person("p-101", "An"),
    new Person("p-102", "Bình"),
    new Person("p-103", "Chi")
);

List<Person> saved = personRepository.saveAll(people);
```

Hợp đồng của `saveAll()` là lưu nhiều instance thuộc cùng kiểu entity và trả về các instance đã lưu. Theo API `Neo4jOperations`, thao tác này bao gồm cả những entity liên quan được khai báo trong graph mapping. Vì vậy, nếu mỗi `Person` có nhiều relationship hoặc node liên quan, khối lượng công việc có thể lớn hơn số lượng node gốc trong danh sách.

`saveAll()` giúp code thể hiện ý định lưu nhiều entity trong một thao tác repository. Nó không cam kết:

- Chỉ phát sinh một câu Cypher cho toàn bộ dữ liệu.
- Chỉ có một lần trao đổi mạng với Neo4j trong mọi trường hợp.
- Mỗi entity được ghi bằng một batch statement tối ưu.
- Dữ liệu lớn bất kỳ đều có thể được giữ trong một transaction mà không ảnh hưởng bộ nhớ hoặc thời gian xử lý.
- Thời gian thực thi tăng tuyến tính hoặc đạt một throughput cố định.

Đây là API persistence cấp domain. Spring Data Neo4j cần giữ đúng semantics của entity, ID, version và các relationship được ánh xạ. Các yêu cầu đó có thể khiến framework phải tạo nhiều statement khác nhau.

## 2. Vì sao saveAll có thể dùng cách thực thi khác nhau?

Tài liệu query creation của Spring Data Neo4j 8.2 mô tả hai trường hợp quan trọng khi lưu nhiều entity:

1. Nếu entity dùng ID sinh tự động hoặc optimistic locking, mỗi entity có thể dẫn tới một lệnh `CREATE` riêng.
2. Trong các trường hợp khác, SDN có thể tạo danh sách tham số chứa thông tin của nhiều entity và thực thi bằng một mẫu `UNWIND` kết hợp `MERGE`.

Ví dụ dạng Cypher được tài liệu minh họa:

```cypher
UNWIND $__entities__ AS entity
MERGE (n:Person {customId: entity.$__id__})
SET n = entity.__properties__
RETURN collect(n.customId) AS $__ids__;
```

Đây là một tối ưu hóa có điều kiện của cơ chế persistence. Không nên dựa vào chi tiết triển khai này như một hợp đồng hiệu năng cố định cho mọi entity hoặc mọi phiên bản. Entity có relationship, generated ID, version hoặc mapping phức tạp có thể cần các thao tác bổ sung.

### Vai trò của ID và optimistic locking

Giả sử entity dùng ID do ứng dụng cấp:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;
}
```

SDN có thể dùng thuộc tính `id` làm khóa nhận diện để tạo truy vấn `MERGE` cho nhiều entity. Nếu entity sử dụng ID nội bộ do Neo4j sinh, framework cần xử lý việc tạo và nhận lại ID cho từng entity.

Entity có optimistic locking:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;
}
```

`@Version` giúp phát hiện cập nhật dựa trên version hiện tại. Mỗi entity có thể có version khác nhau và cần kiểm tra tính hợp lệ của từng lần cập nhật. Đây là một lý do khiến SDN có thể thực thi thao tác riêng cho từng entity thay vì gộp mọi bản ghi vào một lệnh `MERGE` chung.

| Điều kiện | Cách SDN có thể thực thi | Hệ quả cần hiểu |
|---|---|---|
| ID do ứng dụng cấp, không dùng optimistic locking | Có thể gom tham số và dùng `UNWIND`/`MERGE` | Có cơ hội giảm số lần gửi truy vấn |
| ID sinh tự động | Có thể tạo riêng cho từng entity | Không giả định một statement cho toàn bộ danh sách |
| Có `@Version` | Có thể thực hiện `CREATE` riêng cho từng entity | Giữ được kiểm tra version theo từng instance |
| Entity có graph quan hệ phức tạp | Có thể cần thêm thao tác cho node và relationship liên quan | Chi phí phụ thuộc cấu trúc graph, không chỉ số entity gốc |

## 3. API hàng loạt và truy vấn hàng loạt khác nhau thế nào?

API hàng loạt tập trung vào entity và mapping. Truy vấn hàng loạt tập trung vào dữ liệu đầu vào và cách Cypher xử lý nhiều dòng trong một lần thực thi.

| Tiêu chí | `repository.saveAll()` | Cypher `UNWIND` |
|---|---|---|
| Mức trừu tượng | Entity/domain model | Câu truy vấn và parameter |
| Ánh xạ entity | Dùng metadata Spring Data Neo4j | Ứng dụng tự quyết định thao tác và kết quả |
| Relationship mapping | Bao gồm các quan hệ theo graph mapping | Phải viết rõ `MATCH`, `MERGE`, `CREATE`, `SET` cho cạnh |
| ID và version | Framework xử lý theo metadata | Ứng dụng tự thiết kế khóa và kiểm tra version nếu cần |
| Số statement | Phụ thuộc điều kiện và graph được lưu | Một lời gọi Cypher có thể xử lý nhiều dòng đầu vào |
| Phù hợp với | Lưu aggregate và domain entity | Import/update dữ liệu lớn có cấu trúc rõ, thao tác lặp theo từng dòng |

`UNWIND` biến một list tham số thành các dòng dữ liệu để phần còn lại của truy vấn xử lý. Thay vì gửi một câu lệnh cho từng người, ứng dụng gửi danh sách và thực thi một câu Cypher có thể `MERGE` hoặc `CREATE` theo từng dòng.

Ví dụ đơn giản:

```cypher
UNWIND $rows AS row
MERGE (p:Person {externalId: row.id})
SET p.name = row.name;
```

Một query như vậy có thể giảm đáng kể số lần round trip so với vòng lặp gọi một truy vấn cho mỗi dòng. Tuy nhiên, nó vẫn phải xử lý từng dòng, kiểm tra index/constraint, ghi transaction log và lấy lock cần thiết. Một câu query không đồng nghĩa với công việc miễn phí hoặc throughput không giới hạn.

## 4. Dùng Neo4jClient để gửi một batch UNWIND

Khi dữ liệu đầu vào là các bản ghi đơn giản và thao tác có thể mô tả trực tiếp bằng Cypher, `Neo4jClient` cho phép bind một danh sách map thành tham số `$rows`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record PersonRow(String id, String name) {
}

@Service
public class PersonBulkWriter {

    private final Neo4jClient neo4jClient;

    public PersonBulkWriter(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void writeBatch(List<PersonRow> people) {
        List<Map<String, Object>> rows = people.stream()
            .map(person -> Map.<String, Object>of(
                "id", person.id(),
                "name", person.name()
            ))
            .toList();

        neo4jClient.query("""
                UNWIND $rows AS row
                MERGE (p:Person {externalId: row.id})
                SET p.name = row.name
                """)
            .bind(rows).to("rows")
            .run();
    }
}
```

Trong ví dụ:

- Java tạo một list map có cùng cấu trúc với các cột đầu vào.
- `.bind(rows).to("rows")` truyền danh sách bằng parameter, không ghép dữ liệu vào chuỗi Cypher.
- `UNWIND $rows AS row` biến từng phần tử thành biến `row`.
- `MERGE` tìm node theo `externalId` hoặc tạo node nếu chưa tồn tại.
- `SET` cập nhật property cần ghi.
- `@Transactional` đặt toàn bộ batch trong một transaction Spring quản lý.

Ví dụ giả định `id` và `name` không null. Nếu trường đầu vào có thể thiếu, cần định nghĩa rõ việc giữ nguyên, xóa hoặc bỏ qua property đó; không để một giá trị null vô tình xóa dữ liệu mà không có chủ ý.

### Tạo constraint cho khóa dùng trong MERGE

Nếu `externalId` là khóa nhận diện của `Person`, nên bảo vệ tính duy nhất bằng constraint:

```cypher
CREATE CONSTRAINT person_external_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.externalId IS UNIQUE;
```

Constraint bảo vệ dữ liệu khỏi các node trùng khóa. Index hỗ trợ việc tìm node theo khóa trong `MERGE` hiệu quả hơn. Cần tạo constraint trước khi chạy batch và xử lý dữ liệu trùng hiện có nếu database đã có dữ liệu.

`MERGE` theo khóa ổn định cũng làm cho thao tác có tính lặp lại tốt hơn: chạy lại cùng một batch không tạo node mới cho một `externalId` đã tồn tại. Tuy nhiên, nếu nhiều worker đồng thời ghi cùng một khóa, vẫn phải thiết kế và kiểm tra hành vi cạnh tranh bằng constraint cùng transaction phù hợp.

## 5. Khi nào nên chọn saveAll?

Ưu tiên `saveAll()` khi ứng dụng đang làm việc với domain entity và cần giữ các semantics của Spring Data Neo4j:

- Lưu aggregate cùng relationship đã khai báo trong entity.
- Dùng ID và version theo metadata.
- Muốn nhận lại các entity đã lưu.
- Cần giữ logic domain và cách mapping nhất quán với repository CRUD thông thường.
- Tập dữ liệu vừa phải hoặc đã đo được hiệu năng đáp ứng yêu cầu.

Ví dụ một service lưu các đơn hàng cùng những dòng hàng được ánh xạ:

```java
import java.util.List;

import com.example.graph.domain.Order;
import com.example.graph.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public List<Order> saveOrders(List<Order> orders) {
        return orderRepository.saveAll(orders);
    }
}
```

Ở đây, mỗi `Order` là aggregate root và các relationship được quản lý qua entity mapping. Dùng `saveAll()` giúp framework xử lý phần graph được mô tả bởi domain model. Nếu thay bằng Cypher thuần, ứng dụng phải tự triển khai toàn bộ quy tắc tạo node, cập nhật relationship properties, version và các điều kiện nghiệp vụ liên quan.

## 6. Khi nào nên dùng UNWIND?

Ưu tiên một truy vấn `UNWIND` khi thao tác có tính lặp theo từng dòng và có thể biểu diễn rõ bằng Cypher:

- Import nhiều bản ghi từ file hoặc API.
- Cập nhật một tập property đơn giản theo khóa.
- Đồng bộ dữ liệu từ hệ thống ngoài.
- Tạo nhiều node có cấu trúc đồng nhất.
- Tạo hoặc cập nhật relationship theo một tập khóa đã chuẩn hóa.

Ví dụ tạo quan hệ thành viên giữa team và person từ danh sách đầu vào:

```cypher
UNWIND $rows AS row
MATCH (t:Team {externalId: row.teamId})
MATCH (p:Person {externalId: row.personId})
MERGE (t)-[r:HAS_MEMBER]->(p)
SET r.role = row.role;
```

Để truy vấn này chạy đúng và ổn định, `Team.externalId` và `Person.externalId` cần có index hoặc unique constraint phù hợp. Nếu không tìm thấy node ở một trong hai phía, dòng đó không tạo relationship. Nếu cần báo cáo dòng nào bị bỏ qua, hãy thiết kế `RETURN` hoặc bước kiểm tra dữ liệu riêng.

Với `UNWIND`, ứng dụng chịu trách nhiệm cho các quy tắc mà entity mapping thường xử lý giúp:

- Chọn khóa định danh và bảo vệ tính duy nhất.
- Cập nhật hoặc xóa property theo đúng semantics nghiệp vụ.
- Tạo relationship đúng type và direction.
- Kiểm tra version nếu cần optimistic locking.
- Phát domain event hoặc gọi logic nghiệp vụ cần thiết.
- Kiểm tra số dòng đầu vào, số dòng được xử lý và số dòng không tìm thấy node.

Không nên chuyển một thao tác aggregate phức tạp sang Cypher chỉ vì muốn có một câu lệnh duy nhất. Khi đó, chi phí tự duy trì semantics có thể lớn hơn lợi ích hiệu năng.

## 7. Chia lô dữ liệu và transaction

Một câu `UNWIND` có thể nhận một list rất lớn, nhưng gửi toàn bộ dữ liệu trong một request cũng có giới hạn. Ứng dụng phải tạo object đầu vào, serialize payload, gửi qua mạng và Neo4j phải giữ trạng thái transaction cho các thay đổi chưa commit.

Neo4j khuyến nghị chia dữ liệu phía client thành các batch. Tài liệu ingestion guide gợi ý bắt đầu thử trong khoảng một nghìn đến vài nghìn dòng, sau đó điều chỉnh theo lượng thao tác trên mỗi dòng và kết quả đo thực tế. Kích thước phù hợp phụ thuộc vào số property, số relationship, index, lock contention, transaction timeout và tài nguyên máy chủ.

Ví dụ chia `saveAll()` thành các transaction riêng, mỗi batch khoảng 1.000 entity:

```java
import java.util.List;

import com.example.graph.domain.Person;
import org.springframework.stereotype.Service;

@Service
public class PersonImportService {

    private static final int BATCH_SIZE = 1_000;

    private final PersonChunkWriter chunkWriter;

    public PersonImportService(PersonChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public void importPeople(List<Person> people) {
        for (int start = 0; start < people.size(); start += BATCH_SIZE) {
            int end = Math.min(start + BATCH_SIZE, people.size());
            chunkWriter.saveChunk(people.subList(start, end));
        }
    }
}
```

```java
import java.util.List;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonChunkWriter {

    private final PersonRepository personRepository;

    public PersonChunkWriter(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public void saveChunk(List<Person> chunk) {
        personRepository.saveAll(chunk);
    }
}
```

`PersonImportService` điều phối các chunk. Mỗi lần gọi `PersonChunkWriter.saveChunk()` đi qua Spring proxy và mở một transaction riêng; khi chunk kết thúc thành công, transaction đó commit. Cách tách service giúp tránh self-invocation làm mất hiệu lực proxy transaction.

Không đánh dấu `importPeople()` bằng một `@Transactional` bao trùm nếu mục tiêu là commit riêng từng chunk. Nếu có transaction ngoài, các transaction mặc định bên trong sẽ tham gia transaction đang tồn tại và toàn bộ công việc có thể chỉ commit khi method ngoài kết thúc.

Chia lô tạo ra ranh giới phục hồi rõ hơn: nếu batch thứ 8 thất bại, các batch đã commit trước đó vẫn được giữ lại. Vì vậy, quy trình import nên có khóa ổn định, khả năng chạy lại an toàn, checkpoint hoặc log tiến độ để tiếp tục từ phần chưa thành công.

## 8. Batch size và concurrency ảnh hưởng hiệu năng thế nào?

Batch nhỏ và batch lớn có các trade-off khác nhau:

| Kích thước batch | Ưu điểm | Rủi ro |
|---|---|---|
| Quá nhỏ | Transaction ngắn, dễ retry, ít dữ liệu tạm | Nhiều round trip và commit; overhead tăng |
| Vừa phải | Cân bằng payload, bộ nhớ và transaction | Cần đo theo workload thực tế |
| Quá lớn | Ít lần gửi và commit hơn | Payload lớn, transaction state lớn, lock giữ lâu, timeout hoặc OOM |

Đừng chọn batch size chỉ dựa vào số node. Một dòng có thể tạo một node và hai property, nhưng dòng khác có thể tạo nhiều node, relationship và index update. Chi phí transaction của chúng rất khác nhau.

Không tăng concurrency ngay khi batch đơn luồng chưa được tối ưu. Nhiều transaction cùng sửa các node nóng có thể tranh chấp write lock hoặc deadlock. Khi import relationship, một node có degree cao có thể trở thành điểm nghẽn vì nhiều batch cùng nối cạnh vào node đó.

Hãy bắt đầu với các batch tuần tự, đo thời gian và bộ nhớ, sau đó mới thử concurrency. Nếu cần chạy song song, phân vùng dữ liệu theo khóa hoặc nhóm node để giảm khả năng nhiều worker cùng ghi vào một node. Luôn có chiến lược retry cho lỗi transient và ghi nhận batch nào đã commit.

## 9. Những yếu tố quyết định hiệu năng ngoài số lần gọi

Một câu query duy nhất vẫn có thể chậm nếu phần truy vấn bên trong không được thiết kế tốt. Các yếu tố quan trọng gồm:

1. **Index và constraint:** khóa được dùng trong `MATCH` hoặc `MERGE` nên có index phù hợp; khóa duy nhất nên có unique constraint.
2. **Kích thước graph mỗi dòng:** cập nhật một node khác với tạo node cùng nhiều relationship và các node liên quan.
3. **Số property được ghi:** tránh ghi lại toàn bộ map nếu chỉ cần thay đổi một vài thuộc tính.
4. **Lock contention:** nhiều transaction cùng sửa node hoặc relationship có thể phải chờ nhau.
5. **Transaction state và timeout:** transaction lớn giữ nhiều thay đổi chưa commit và lock lâu hơn.
6. **Kích thước kết quả trả về:** chỉ trả những giá trị cần thiết, không hydrate toàn bộ graph nếu batch chỉ cần xác nhận số dòng xử lý.
7. **Query plan:** dùng `EXPLAIN` để xem kế hoạch và `PROFILE` để đo các operator trên dữ liệu đại diện.

Trong truy vấn `UNWIND`, nên dùng `MERGE` trên khóa nhận diện ổn định rồi `SET` các property cần cập nhật. Tránh đưa quá nhiều thuộc tính thay đổi vào pattern `MERGE`, vì như vậy có thể làm thay đổi cách nhận diện và tạo node ngoài ý muốn.

## 10. Lưu ý về transaction và CALL IN TRANSACTIONS

Cypher hỗ trợ `CALL { ... } IN TRANSACTIONS` để chia một truy vấn lớn thành các transaction con. Cơ chế này hữu ích cho import rất lớn, nhưng có một khác biệt quan trọng: truy vấn dùng `IN TRANSACTIONS` phải chạy trong implicit/auto-commit transaction. Nó không thể chạy bên trong explicit transaction đang được `@Transactional` hoặc một transaction function quản lý.

Vì vậy, không đặt một truy vấn `CALL { ... } IN TRANSACTIONS` vào method đang tham gia Spring-managed transaction và kỳ vọng Neo4j tự chia nhỏ transaction. Hãy chọn rõ một trong hai chiến lược:

- Ứng dụng chia lô và gọi từng batch trong transaction Spring riêng.
- Neo4j tự chia transaction con bằng `CALL { ... } IN TRANSACTIONS`, được gửi qua một thao tác auto-commit phù hợp.

Với batch import thông thường từ ứng dụng Spring, cách chia lô phía client thường dễ quan sát, kiểm tra và retry hơn. Dùng server-side transaction batching khi có lý do rõ ràng và đã kiểm tra điều kiện chạy của truy vấn.

## 11. Khi nào cần công cụ import chuyên dụng?

Nếu phải nạp hàng triệu hoặc hàng tỷ node/relationship vào database mới hoặc database có thể đưa offline, repository `saveAll()` và `UNWIND` không phải lúc nào cũng là công cụ phù hợp nhất. `neo4j-admin database import` ghi dữ liệu trực tiếp vào định dạng lưu trữ native và được thiết kế cho initial bulk import khi có quyền truy cập server cùng dữ liệu đã chuẩn hóa.

Với import trực tuyến, database vẫn phục vụ ứng dụng và dữ liệu đến từ API, queue hoặc hệ thống ngoài, `UNWIND` kết hợp chia batch là lựa chọn thường gặp. Hãy chọn theo điều kiện vận hành, khả năng downtime, kích thước dữ liệu và yêu cầu cập nhật graph hiện có.

## 12. Cách đo và xác nhận một batch có thực sự hiệu quả

Không nên đánh giá bằng việc code chỉ có một lời gọi `saveAll()` hoặc một câu `UNWIND`. Hãy đo bằng một workload có thể lặp lại:

1. Tạo tập dữ liệu đại diện, gồm cả entity mới, entity cập nhật và graph có relationship.
2. Ghi nhận số entity, relationship, property và kích thước payload.
3. Đo thời gian toàn batch, throughput (bản ghi/giây), heap phía ứng dụng và mức sử dụng transaction memory phía Neo4j.
4. Kiểm tra số statement/transaction bằng logging hoặc quan sát transaction và query log phù hợp.
5. Dùng `EXPLAIN`/`PROFILE` để kiểm tra index seek, scan, số row và operator tốn chi phí.
6. Thử nhiều batch size, ví dụ 500, 1.000, 2.000 và 5.000 dòng; chọn điểm cân bằng theo kết quả.
7. Kiểm tra tính đúng đắn sau khi ghi: số node, relationship, khóa trùng, property và khả năng chạy lại batch.

Một batch nhanh nhưng tạo node trùng, mất relationship hoặc bỏ qua lỗi version không phải là một batch thành công. Hiệu năng cần được đánh giá cùng tính đúng đắn và khả năng phục hồi.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| `saveAll()` luôn chạy một câu Cypher | Cách thực thi phụ thuộc ID, version và graph mapping |
| Một method call nghĩa là một network round trip | API không cam kết số round trip cho mọi trường hợp |
| `UNWIND` làm mỗi dòng không tốn chi phí | Neo4j vẫn thực hiện thao tác cho từng dòng trong transaction |
| Batch càng lớn càng nhanh | Batch quá lớn có thể làm transaction memory, lock và timeout tăng |
| Chạy nhiều worker luôn tăng throughput | Node nóng và lock contention có thể làm throughput giảm hoặc phát sinh deadlock |
| `MERGE` tự bảo đảm duy nhất trong mọi tình huống cạnh tranh | Cần unique constraint phù hợp trên khóa nhận diện |
| Cypher hàng loạt tương đương entity save | Cypher thuần không tự thực hiện toàn bộ entity mapping và version semantics |
| Một transaction cho toàn bộ import luôn an toàn | Transaction quá lớn có thể giữ nhiều trạng thái chưa commit và khó phục hồi |

## 14. Nguyên tắc lựa chọn

- Dùng `saveAll()` khi cần lưu nhiều domain entity và các relationship theo mapping của Spring Data Neo4j.
- Đọc tài liệu query creation của đúng phiên bản SDN để hiểu các điều kiện ảnh hưởng cách `saveAll()` được thực thi.
- Dùng `UNWIND` khi thao tác có cấu trúc lặp rõ ràng và ứng dụng cần gửi nhiều dòng trong một truy vấn Cypher.
- Tạo index/unique constraint cho các khóa được dùng trong `MATCH` và `MERGE`.
- Chia dữ liệu lớn thành các chunk có kích thước đo được và transaction boundary rõ ràng.
- Không bọc toàn bộ quy trình import trong một transaction nếu muốn commit riêng từng chunk.
- Không giả định custom Cypher tự áp dụng `@Version`, entity lifecycle hoặc relationship mapping.
- Dùng `EXPLAIN`, `PROFILE` và số liệu thực tế để xác nhận hiệu năng.
- Chọn `neo4j-admin database import` cho initial bulk load cực lớn khi điều kiện vận hành phù hợp.

`saveAll()` trả lời câu hỏi “làm thế nào lưu nhiều entity qua repository?”. `UNWIND` trả lời câu hỏi “làm thế nào để một truy vấn xử lý nhiều dòng dữ liệu?”. Chia lô transaction trả lời câu hỏi “làm thế nào kiểm soát bộ nhớ, commit và khả năng phục hồi khi dữ liệu lớn?”. Tách bạch ba câu hỏi này giúp lựa chọn đúng công cụ mà vẫn giữ được semantics của domain và hiệu năng có thể đo lường.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2 – Query creation: Save and multiple entities](https://docs.spring.io/spring-data/neo4j/reference/appendix/query-creation.html)
- [Spring Data Neo4j 8.2 – Neo4jOperations API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jOperations.html)
- [Neo4j Data Ingestion Guide – Loading data with UNWIND](https://neo4j.com/docs/data-ingestion-guide/ingestion-methods/unwind/)
- [Neo4j Data Ingestion Guide – Transactional and concurrent Cypher ingestion](https://neo4j.com/docs/data-ingestion-guide/best-practices/transactional-and-concurrent-cypher-ingestion/)
- [Neo4j Operations Manual – Import](https://neo4j.com/docs/operations-manual/current/import/)
