# Phân biệt ID số nội bộ, elementId và ID lưu trong property

Trong Neo4j, một node hoặc relationship có thể được nhận diện bằng ID nội bộ do database cấp, bằng chuỗi `elementId()` hoặc bằng một property do ứng dụng quản lý. Ba giá trị này đều có thể giúp tìm một phần tử đồ thị trong một ngữ cảnh nhất định, nhưng chúng có phạm vi ổn định và mục đích sử dụng khác nhau.

Với `SPRING_DATA_NEO4J`, việc chọn đúng loại định danh ảnh hưởng trực tiếp đến cách khai báo `@Id`, cách framework ánh xạ entity, cách viết `MATCH`/`MERGE` và khả năng giữ tham chiếu khi dữ liệu được cập nhật hoặc di chuyển. Quy tắc quan trọng là: ID nội bộ phục vụ database quản lý phần tử; định danh lưu trong property phục vụ mô hình và nghiệp vụ của ứng dụng.

## 1. Ba loại định danh ở ba lớp khác nhau

Giả sử đồ thị có một node `Person`:

```cypher
CREATE (p:Person {id: 'person-7f2a', name: 'An'})
RETURN p, id(p) AS internalId, elementId(p) AS elementId;
```

Kết quả minh họa có thể gồm ba giá trị:

| Giá trị | Ví dụ minh họa | Nơi quản lý | Ý nghĩa |
|---|---|---|---|
| ID số nội bộ | `42` | Neo4j | Định danh kỹ thuật dạng số cho node hoặc relationship |
| `elementId` | `"4:...:42"` | Neo4j | Định danh kỹ thuật dạng chuỗi, dùng thay cho cách biểu diễn cũ trong các truy vấn hiện đại |
| Property ID | `"person-7f2a"` | Ứng dụng lưu trên node | Khóa ổn định để nhận diện `Person` theo quy tắc của ứng dụng |

Các giá trị trên chỉ là ví dụ để phân biệt khái niệm. Không suy luận cấu trúc, thứ tự, độ dài hay quy tắc sinh ID từ chuỗi `elementId` mà Neo4j trả về.

### ID số nội bộ: `id(n)`

Neo4j cấp một ID số nội bộ khi tạo node hoặc relationship. Trong Cypher cũ, có thể đọc nó bằng `id()`:

```cypher
MATCH (p:Person)
RETURN id(p) AS internalId, p.name AS name;
```

ID này thuộc quyền quản lý của Neo4j. Nó không phải mã nghiệp vụ và không được lưu như một property thông thường của node. Neo4j có thể tái sử dụng ID nội bộ sau khi phần tử cũ bị xóa; vì vậy, một số từng đại diện cho người này có thể đại diện cho phần tử khác ở thời điểm sau.

Trong các phiên bản Neo4j hiện đại, `id()` đã bị đánh dấu deprecated và được thay thế bằng `elementId()`. Nếu đang bảo trì truy vấn cũ, hãy xem `id()` là dấu hiệu cần rà soát, đặc biệt khi giá trị đó đã được lưu vào hệ thống bên ngoài hoặc dùng trong URL lâu dài.

### `elementId(n)`: ID nội bộ dạng chuỗi

Neo4j cung cấp `elementId()` để trả về định danh phần tử dưới dạng chuỗi:

```cypher
MATCH (p:Person)
RETURN elementId(p) AS elementId, p.name AS name;
```

`elementId()` áp dụng cho cả node và relationship. Giá trị này được bảo đảm duy nhất giữa các node và relationship trong cùng DBMS trong phạm vi một transaction. Ngoài transaction đó, Neo4j không bảo đảm cùng một chuỗi sẽ tiếp tục ánh xạ đến cùng một phần tử. Do đó, không nên lưu `elementId` vào hệ thống khác để dùng như khóa bền vững hoặc coi nó là mã định danh nghiệp vụ.

Có thể dùng `elementId()` trong một thao tác ngắn hạn khi cần truyền tham chiếu phần tử giữa các bước của cùng transaction. Nhưng nếu cần tham chiếu một người qua nhiều request, nhiều phiên chạy hoặc qua thời gian dài, hãy dùng property ID do ứng dụng quản lý.

### ID lưu trong property

Ứng dụng có thể lưu một ID trên node như `id`, `personId`, `externalId` hoặc `uuid`:

```cypher
MATCH (p:Person {id: $personId})
RETURN p;
```

Property này là dữ liệu thực của node. Neo4j không tự bảo đảm nó duy nhất chỉ vì tên property là `id`; ứng dụng cần tạo constraint phù hợp. Khi có unique constraint, property ID có thể được dùng ổn định trong API, sự kiện, log, liên kết giữa dịch vụ và các câu truy vấn.

ID property có thể do ứng dụng tự cấp, lấy từ hệ thống nguồn hoặc được sinh bằng UUID. Chọn một giá trị không đổi trong vòng đời thực thể. Không nên dùng tên hiển thị, vị trí trong danh sách hay email có thể thay đổi làm khóa chính nếu nghiệp vụ không bảo đảm chúng bất biến và duy nhất.

## 2. So sánh phạm vi và cách sử dụng

| Tiêu chí | ID số nội bộ (`id()`) | `elementId()` | Property ID của ứng dụng |
|---|---|---|---|
| Kiểu dữ liệu | Số nguyên | Chuỗi | Kiểu property được Neo4j hỗ trợ, thường là chuỗi |
| Ai cấp | Neo4j | Neo4j | Ứng dụng hoặc hệ thống nguồn |
| Được lưu thành property trên node | Không | Không | Có |
| Phạm vi bảo đảm duy nhất | Trong database và transaction theo loại phần tử; số có thể trùng giữa node và relationship | Giữa node và relationship trong DBMS, trong phạm vi transaction | Theo constraint và quy tắc nghiệp vụ do ứng dụng thiết lập |
| Ổn định để tham chiếu lâu dài | Không | Không | Có, nếu ứng dụng giữ nguyên và bảo đảm duy nhất |
| Cách dùng phù hợp | Tương thích mã cũ, chẩn đoán kỹ thuật | Tham chiếu tạm thời trong transaction | API, tích hợp, định danh entity và truy vấn nghiệp vụ |

Hai ID do Neo4j cấp là chi tiết triển khai của database. Dù `elementId()` là dạng chuỗi hiện đại hơn và thay thế `id()` trong Cypher, nó vẫn không trở thành khóa nghiệp vụ. Chuyển một giá trị từ số sang chuỗi không làm thay đổi phạm vi bảo đảm ổn định của định danh đó.

## 3. Spring Data Neo4j ánh xạ `@Id` như thế nào?

Trong Spring Data Neo4j, `@Id` đánh dấu thuộc tính mà framework dùng để nhận diện entity. Kết hợp với `@GeneratedValue`, kiểu thuộc tính và generator xác định ID được lấy từ đâu.

### Dùng ID nội bộ do Neo4j cấp

Với ID số nội bộ, có thể khai báo `Long` cùng `@Id` và `@GeneratedValue`:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
```

Trong cấu hình mặc định, Spring Data Neo4j dùng ID nội bộ do database cấp. Thuộc tính `id` trong Java không tương ứng với property `id` trên node. Vì ID chưa có trước khi lưu, kiểu wrapper `Long` hữu ích hơn kiểu primitive `long`: giá trị `null` biểu thị entity chưa được cấp ID.

Sau khi lưu, dùng entity mà repository trả về để lấy ID đã được gán:

```java
Person saved = personRepository.save(new Person("An"));
Long internalId = saved.getId();
```

Đoạn gọi giả định lớp có constructor nhận `name` và getter `getId()`; phần cài đặt được lược bỏ để tập trung vào ý nghĩa ID. Không đưa `internalId` này vào hợp đồng API hoặc bảng tham chiếu lâu dài nếu hệ thống cần định danh ổn định qua việc xóa, tạo lại hay di chuyển dữ liệu.

### Dùng `elementId` qua thuộc tính String được sinh

Trong Spring Data Neo4j trên Neo4j 5 trở lên, thuộc tính `String` kết hợp `@Id` và `@GeneratedValue` ánh xạ đến `elementId`:

```java
@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private String id;

    private String name;
}
```

Thuộc tính này cũng không được lưu thành property `id` trên node. Spring Data Neo4j sử dụng nó làm định danh kỹ thuật để theo dõi entity. Dù kiểu Java là `String`, giá trị này vẫn mang giới hạn vòng đời của `elementId()`; nó không phải UUID do ứng dụng tạo và không nên dùng làm mã định danh lâu dài.

Vì vậy, khi đọc một lớp entity có `String id`, hãy kiểm tra annotation đi kèm. `@Id` đơn lẻ và `@Id @GeneratedValue` có ý nghĩa lưu trữ khác nhau.

### Dùng ID property do ứng dụng cấp

Nếu muốn ID được lưu thành property trên node, khai báo `@Id` mà không dùng `@GeneratedValue`, rồi cấp giá trị trước khi lưu:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    public Person(String id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

Tạo ID ở tầng ứng dụng, ví dụ:

```java
String personId = java.util.UUID.randomUUID().toString();
Person person = new Person(personId, "An");
Person saved = personRepository.save(person);
```

Trong trường hợp này, property `id` được ghi lên node và có thể được truy vấn bằng Cypher. Giá trị ID do ứng dụng quyết định nên có thể được giữ ổn định khi dữ liệu được xuất, nhập hoặc chuyển sang database khác, miễn là quy trình di chuyển bảo toàn property đó.

Nếu muốn dùng một tên property khác trong Neo4j, có thể kết hợp `@Id` với `@Property`:

```java
@Id
@Property("personKey")
private String id;
```

Lúc này Java vẫn truy cập trường `id`, còn node lưu khóa dưới tên `personKey`.

### Dùng generator bên ngoài nhưng vẫn lưu property

Spring Data Neo4j có thể dùng `UUIDStringGenerator` để sinh UUID ở phía ứng dụng/framework. Đây là ID bên ngoài database và được lưu thành property trên node:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    private String name;
}
```

Khác biệt quan trọng nằm ở generator: `@GeneratedValue` mặc định dùng ID nội bộ; chỉ định `UUIDStringGenerator` sẽ sinh ID ngoài và lưu nó như property. Nếu dùng UUID, hãy xác định rõ generator đang được dùng để tránh nhầm chuỗi UUID với `elementId`.

## 4. Tạo constraint cho ID property

`@Id` giúp Spring Data Neo4j nhận diện entity trong quá trình ánh xạ. Để database bảo vệ tính duy nhất của property khi nhiều request hoặc instance ứng dụng cùng ghi, cần tạo unique constraint trong Neo4j.

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.id IS UNIQUE;
```

Nếu khóa được đặt tên `personKey`, constraint phải tham chiếu đúng property:

```cypher
CREATE CONSTRAINT person_key_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personKey IS UNIQUE;
```

Khi một ID chỉ duy nhất trong phạm vi tenant, có thể dùng composite unique constraint:

```cypher
CREATE CONSTRAINT person_tenant_key_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.externalId) IS UNIQUE;
```

Khi dùng composite key, mọi truy vấn `MATCH` hoặc `MERGE` cần truyền đủ các thành phần để nhận diện đúng thực thể. Constraint chỉ có thể được tạo khi dữ liệu hiện tại đáp ứng điều kiện duy nhất; cần xử lý các bản ghi trùng trước khi áp dụng.

## 5. Viết truy vấn theo loại ID

### Truy vấn bằng property ID

Đây là cách phù hợp cho use case nghiệp vụ:

```cypher
MATCH (p:Person {id: $personId})
RETURN p;
```

Tạo hoặc cập nhật theo cùng khóa:

```cypher
MERGE (p:Person {id: $personId})
ON CREATE SET p.name = $name
ON MATCH SET p.name = $name
RETURN p;
```

Unique constraint trên `Person.id` giúp Neo4j bảo vệ quy tắc một ID tương ứng với tối đa một node `Person`.

### Truy vấn bằng `elementId`

Để minh họa cách truy vấn theo `elementId`, có thể viết:

```cypher
MATCH (p)
WHERE elementId(p) = $elementId
RETURN p;
```

Chỉ dùng cách này khi tham chiếu được tạo và sử dụng trong cùng transaction hoặc cho mục đích chẩn đoán tạm thời. Không dùng `elementId` làm khóa trong URL, thông điệp hàng đợi, bảng quan hệ ở dịch vụ khác hoặc dữ liệu cần tồn tại qua nhiều transaction.

### Rà soát truy vấn cũ dùng `id()`

Truy vấn cũ có thể dùng:

```cypher
MATCH (p:Person)
WHERE id(p) = $internalId
RETURN p;
```

`id()` đã deprecated trong Cypher hiện đại. Nếu chỉ cần định danh tạm thời trong transaction, xem xét `elementId()`. Nếu truy vấn phục vụ nghiệp vụ hoặc tham chiếu lâu dài, chuyển sang property ID và tạo unique constraint. Không thay máy móc `id(p)` bằng `elementId(p)` mà không đổi kiểu tham số và xem xét phạm vi vòng đời của giá trị.

## 6. Chọn ID nào cho từng tình huống?

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Entity nội bộ đơn giản, không cần công khai định danh | ID nội bộ qua `@Id @GeneratedValue` | Cấu hình đơn giản, database quản lý |
| Cần giá trị định danh Neo4j dạng chuỗi trong cùng transaction | `elementId()` | Dễ truyền trong các bước xử lý ngắn hạn |
| API cần ID ổn định qua nhiều request | Property ID do ứng dụng cấp | Không phụ thuộc ID vật lý của database |
| Nhiều dịch vụ cùng tham chiếu một thực thể | UUID hoặc khóa ngoài được lưu thành property | Có thể chia sẻ qua message, API và database khác |
| Dữ liệu đồng bộ từ hệ thống nguồn | External ID cùng unique constraint | Giữ được liên kết với bản ghi nguồn |
| Khóa chỉ duy nhất trong tenant | Composite property key và composite unique constraint | Phản ánh đúng phạm vi duy nhất của nghiệp vụ |

Không phải mọi entity đều bắt buộc phải có UUID. Hãy chọn theo vòng đời và ranh giới tích hợp của dữ liệu. Nếu entity chỉ tồn tại trong phạm vi xử lý nội bộ và không cần tham chiếu lâu dài, ID nội bộ có thể đủ. Nếu ID đi ra ngoài database hoặc được lưu ở nơi khác, property ID do ứng dụng quản lý là lựa chọn phù hợp hơn.

## 7. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| API trả ID rồi request sau không tìm được node | API dùng ID nội bộ hoặc `elementId` như khóa lâu dài | Dùng property ID ổn định và truy vấn bằng property |
| `@Id` có giá trị nhưng node không có property `id` | Trường được khai báo cùng `@GeneratedValue` nên là ID kỹ thuật nội bộ | Kiểm tra generator; bỏ `@GeneratedValue` nếu muốn lưu ID đã cấp thành property |
| Chuỗi `String id` bị hiểu nhầm là UUID | `@Id @GeneratedValue` dùng `elementId` trên Neo4j 5+ | Kiểm tra generator; dùng `UUIDStringGenerator` hoặc ID gán thủ công nếu cần UUID property |
| `MERGE` tạo thêm node cùng một người | Pattern dùng sai khóa hoặc property ID chưa có unique constraint | Chọn khóa ổn định, xử lý dữ liệu trùng và tạo unique constraint |
| Truy vấn cũ báo deprecated | Dùng hàm Cypher `id()` | Thay bằng `elementId()` cho tham chiếu tạm thời hoặc property ID cho nghiệp vụ |
| Tham chiếu sai sau khi xóa và tạo lại node | ID nội bộ có thể được tái sử dụng; `elementId` không có bảo đảm ánh xạ qua transaction | Dùng ID property được ứng dụng quản lý |

Khi chuyển từ ID nội bộ sang property ID, cần lập kế hoạch dữ liệu: bổ sung property cho các node hiện có, bảo đảm giá trị duy nhất, tạo constraint, cập nhật repository và các câu Cypher, rồi chuyển API hoặc message sang ID mới. Không thể chỉ đổi kiểu trường Java mà tự động biến ID nội bộ cũ thành property ID bền vững.

## 8. Tự kiểm tra

1. Vì sao một ID số do Neo4j cấp có thể được tái sử dụng sau khi node bị xóa?
2. `elementId()` trả về kiểu gì và phạm vi bảo đảm duy nhất của nó là gì?
3. Trong Spring Data Neo4j, khác biệt giữa `@Id` và `@Id @GeneratedValue` là gì?
4. Vì sao `String id` với `@Id @GeneratedValue` không đồng nghĩa với UUID lưu trong property?
5. Cần tạo constraint nào để bảo đảm property `Person.id` duy nhất?
6. Nếu một dịch vụ khác cần lưu ID của `Person` trong message để truy vấn lại vào ngày hôm sau, nên chọn loại định danh nào?

Hiểu đúng ba loại ID giúp tránh phụ thuộc vào chi tiết lưu trữ của Neo4j. Trong Spring Data Neo4j, hãy đọc cả kiểu dữ liệu lẫn annotation để biết `@Id` đang ánh xạ ID nội bộ, `elementId` hay property ID. Khi định danh cần tồn tại qua nhiều transaction và ranh giới hệ thống, hãy để ứng dụng quản lý một property ID ổn định và để unique constraint bảo vệ tính duy nhất ở database.

## Tài liệu tham khảo

- [Spring Data Neo4j — Handling and provisioning of unique IDs](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Neo4j Cypher Manual — Scalar functions: `elementId()` and `id()`](https://neo4j.com/docs/cypher-manual/current/functions/scalar/)
