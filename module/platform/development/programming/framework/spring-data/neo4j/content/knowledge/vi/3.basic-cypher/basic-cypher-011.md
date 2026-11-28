# CALL, truy vấn con và gọi procedure trong phạm vi hỗ trợ của phiên bản

## Mục tiêu bài học

Cypher có hai cơ chế thường được viết bằng từ khóa `CALL`: gọi một **procedure** đã được Neo4j hoặc plugin cung cấp, và thực thi một **subquery** (truy vấn con) được viết trực tiếp bằng Cypher. Hai cơ chế có cách khai báo, mục đích và yêu cầu tương thích khác nhau.

Trong ứng dụng Spring Data Neo4j (SDN), bạn có thể dùng chúng trong `@Query` để lấy dữ liệu tổng hợp, kết hợp nhiều nhánh truy vấn, gọi chức năng quản trị hoặc xử lý tập dữ liệu lớn theo từng transaction. Bài học này trình bày cách đọc cú pháp, truyền dữ liệu giữa truy vấn ngoài và truy vấn con, nhận kết quả bằng `YIELD` hoặc `RETURN`, và kiểm tra hỗ trợ theo phiên bản Neo4j đang chạy.

## 1. Phân biệt procedure và subquery

| Cơ chế | Nội dung được gọi | Mục đích thường gặp |
|---|---|---|
| Gọi procedure | Một thủ tục có tên, được cài đặt trong Neo4j hoặc plugin | Lấy metadata, gọi chức năng tích hợp hoặc mở rộng |
| Gọi subquery | Một khối câu lệnh Cypher nằm trong `CALL { ... }` | Tách một phần truy vấn, dùng biến từ truy vấn ngoài, tổng hợp hoặc xử lý theo nhóm |

Procedure có tên định danh như `db.labels` hoặc `apoc.path.expandConfig`. Neo4j cung cấp các procedure tích hợp; plugin như APOC bổ sung procedure riêng nếu đã được cài đặt và cấu hình. Mỗi procedure có chữ ký đầu vào và đầu ra cụ thể.

Subquery không phải plugin hay hàm được cài đặt. Nó là một khối Cypher có thể chứa `MATCH`, `WHERE`, `WITH`, `CREATE`, `SET`, `DELETE` và các mệnh đề Cypher phù hợp khác. Subquery thường được dùng để xử lý từng dòng đầu vào, gom dữ liệu liên quan hoặc kết hợp nhiều tập kết quả.

Cùng dùng từ khóa `CALL`, nhưng không thể thay thế hai cơ chế cho nhau: procedure được gọi bằng tên và nhận đối số; subquery được bao trong dấu ngoặc nhọn và trả dữ liệu ra qua `RETURN`.

## 2. Gọi procedure với CALL và YIELD

### Cấu trúc cơ bản

Cú pháp tổng quát:

```cypher
CALL ten.namespace.procedureName(arg1, arg2)
YIELD outputField1, outputField2
RETURN outputField1, outputField2;
```

- `CALL` gọi procedure theo tên đầy đủ và truyền các đối số theo chữ ký của nó.
- `YIELD` chọn những cột đầu ra mà truy vấn muốn sử dụng.
- Có thể lọc các cột được yield bằng `WHERE`, rồi tiếp tục xử lý hoặc trả kết quả bằng `RETURN`.

Ví dụ dùng procedure tích hợp để liệt kê label đang có trong graph:

```cypher
CALL db.labels() YIELD label
RETURN label
ORDER BY label;
```

Tương tự, có thể liệt kê các kiểu relationship:

```cypher
CALL db.relationshipTypes() YIELD relationshipType
RETURN relationshipType
ORDER BY relationshipType;
```

Lọc ngay sau `YIELD` giúp giảm dữ liệu đi qua các bước tiếp theo:

```cypher
CALL db.labels() YIELD label
WHERE label STARTS WITH 'P'
RETURN label;
```

Ở đây `label` là tên cột do procedure trả về. Tên cột và kiểu dữ liệu đầu ra phụ thuộc chữ ký của từng procedure; hãy dùng đúng tên mà procedure công bố.

### Kiểm tra procedure có sẵn

Có thể xem danh sách procedure mà máy chủ công bố bằng lệnh quản trị:

```cypher
SHOW PROCEDURES
YIELD name, signature, description
RETURN name, signature, description
ORDER BY name;
```

Danh sách này giúp xác định tên, tham số và kiểu kết quả trước khi gọi. Một số thông tin hoặc thao tác quản trị có thể yêu cầu quyền phù hợp. Nếu gọi procedure không tồn tại, lỗi thường liên quan đến tên sai, plugin chưa cài, plugin chưa được cấu hình cho phép, hoặc phiên bản máy chủ không cung cấp procedure đó.

Không nên mặc định mọi máy Neo4j đều có APOC. Trước khi dùng một procedure APOC, hãy xác minh plugin đã được cài và cấu hình đúng cho phiên bản Neo4j của môi trường đích. Với ứng dụng triển khai ở nhiều môi trường, cần kiểm tra khả năng hỗ trợ khi khởi động hoặc trong bước kiểm tra triển khai thay vì chỉ dựa vào môi trường phát triển.

### Quyền và tác động của procedure

Procedure có thể chỉ đọc dữ liệu, ghi dữ liệu, thực hiện thao tác quản trị hoặc truy cập chức năng mở rộng. Quyền gọi phụ thuộc loại procedure và cấu hình bảo mật của Neo4j. Chỉ cấp quyền cần thiết cho tài khoản ứng dụng; không cấp quyền quản trị rộng chỉ để một truy vấn thông thường hoạt động.

Hãy đọc tài liệu hoặc chữ ký của procedure trước khi dùng, đặc biệt với procedure có tác động ghi hoặc thao tác trên nhiều node. Không đưa dữ liệu đầu vào trực tiếp vào chuỗi Cypher để tạo tên procedure hay câu lệnh động; tên procedure nên được xác định trong mã, còn giá trị đầu vào được truyền bằng tham số theo chữ ký hỗ trợ.

## 3. Subquery với CALL { ... }

### Cấu trúc và phạm vi biến

Subquery được đặt trong cặp dấu ngoặc nhọn:

```cypher
CALL {
    // Các mệnh đề Cypher bên trong subquery.
    MATCH (n:Person)
    RETURN n
}
RETURN n;
```

Các biến được tạo bên trong chỉ có phạm vi trong subquery, trừ những cột được đưa ra bằng `RETURN`. Truy vấn ngoài có thể sử dụng các cột đó như kết quả của một phần truy vấn.

Subquery có thể độc lập với dữ liệu bên ngoài hoặc có thể nhận biến từ từng dòng đầu vào. Trường hợp thứ hai được gọi là subquery tương quan (correlated subquery): khối `CALL` được thực thi theo từng dòng mà truy vấn ngoài truyền vào.

### Truyền biến từ truy vấn ngoài

Cú pháp nhập biến truyền thống dùng `WITH` ngay đầu subquery:

```cypher
MATCH (p:Person)
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:MEMBER_OF]->(g:Group)
    RETURN collect(g.name) AS groupNames
}
RETURN p.name AS personName, groupNames
ORDER BY personName;
```

Diễn giải:

1. Truy vấn ngoài tìm từng node `Person` và đặt node hiện tại vào biến `p`.
2. `WITH p` đưa biến `p` vào phạm vi của subquery.
3. `OPTIONAL MATCH` tìm các nhóm mà người đó tham gia; nếu không có nhóm, truy vấn vẫn giữ kết quả.
4. `collect(g.name)` gom tên nhóm thành một danh sách.
5. `RETURN` trong subquery xuất `groupNames` ra ngoài; truy vấn ngoài kết hợp danh sách đó với tên người.

Mỗi lần thực thi subquery tương quan nhận một dòng đầu vào. Khi có nhiều node `Person`, phần truy vấn con được áp dụng cho từng người. Đây là cách hữu ích để tính số lượng hoặc danh sách liên kết riêng cho từng node.

### Cú pháp phạm vi biến ở Neo4j mới hơn

Từ Neo4j 5.23, subquery hỗ trợ cú pháp khai báo biến ngay trong phần đầu `CALL`, thường gọi là *scope clause*:

```cypher
MATCH (p:Person)
CALL (p) {
    OPTIONAL MATCH (p)-[:MEMBER_OF]->(g:Group)
    RETURN collect(g.name) AS groupNames
}
RETURN p.name AS personName, groupNames
ORDER BY personName;
```

`CALL (p)` khai báo rõ biến ngoài được phép dùng bên trong. Cú pháp này giúp thể hiện phạm vi biến ngay tại điểm gọi và là lựa chọn nên ưu tiên khi phiên bản máy chủ hỗ trợ.

Với các phiên bản cũ hơn, dùng `CALL { WITH p ... }` như ví dụ trước. Không trộn hai cách khai báo trong cùng một subquery. Khi triển khai trên nhiều phiên bản Neo4j, hãy chọn cú pháp chung mà tất cả phiên bản đích hỗ trợ hoặc duy trì truy vấn riêng theo phiên bản.

### Kết hợp nhiều nhánh bằng UNION

Subquery có thể chứa `UNION` để kết hợp các truy vấn có cùng cấu trúc kết quả. Ví dụ, tạo một danh sách thống nhất gồm người mà một người theo dõi và nhóm mà người đó tham gia:

```cypher
CALL {
    MATCH (p:Person)-[:FOLLOWS]->(other:Person)
    RETURN p.name AS personName,
           'FOLLOWS' AS relationType,
           other.name AS relatedName

    UNION ALL

    MATCH (p:Person)-[:MEMBER_OF]->(g:Group)
    RETURN p.name AS personName,
           'MEMBER_OF' AS relationType,
           g.name AS relatedName
}
RETURN personName, relationType, relatedName
ORDER BY personName, relationType, relatedName;
```

Mỗi nhánh phải trả về cùng số cột, theo cùng thứ tự và có kiểu dữ liệu tương thích. `UNION` loại bỏ các dòng trùng nhau; `UNION ALL` giữ lại tất cả dòng, thường ít tốn công loại trùng hơn. Hãy chọn theo ý nghĩa dữ liệu, không chỉ theo thói quen.

## 4. Subquery theo transaction và xử lý dữ liệu lớn

### Chia một thao tác ghi thành nhiều transaction

Với tập dữ liệu lớn, một transaction duy nhất có thể giữ quá nhiều dữ liệu trong bộ nhớ hoặc kéo dài thời gian khóa. Subquery có thể được thực thi theo từng lô bằng `IN TRANSACTIONS`:

```cypher
MATCH (p:Person)
CALL {
    WITH p
    SET p.reviewed = true
} IN TRANSACTIONS OF 500 ROWS
RETURN count(*) AS processedPeople;
```

Ví dụ này lấy các node `Person` và cập nhật theo từng lô tối đa 500 dòng. Mỗi lô được xử lý trong transaction riêng, giúp giới hạn kích thước transaction. Kích thước lô cần được chọn dựa trên lượng dữ liệu, chi phí cập nhật và tài nguyên của máy chủ.

Subquery dạng này hữu ích cho thao tác bảo trì hoặc chuyển đổi dữ liệu hàng loạt. Nó cũng có thể kết hợp với `LOAD CSV` để nhập dữ liệu theo lô, nhưng cần thiết kế cách xử lý lỗi và khả năng chạy lại cẩn thận: các lô đã commit vẫn được giữ lại nếu một lô sau gặp lỗi.

### Giới hạn transaction khi tích hợp với Spring

`CALL { ... } IN TRANSACTIONS` yêu cầu được thực thi trong implicit transaction (transaction ngầm định) do driver mở cho một câu lệnh. Nó không chạy bên trong một explicit transaction (transaction tường minh) đã được mở trước, chẳng hạn ranh giới transaction do `@Transactional` quản lý.

Vì vậy, không đặt truy vấn dùng `IN TRANSACTIONS` vào một service method đang chạy trong transaction tường minh. Khi dùng Spring Data Neo4j, cần xác minh đường gọi thực tế của phiên bản SDN và Neo4j Java Driver: repository method hoặc `Neo4jClient` có thể tham gia transaction Spring hiện tại. Với tác vụ theo lô, hãy chọn cách thực thi implicit transaction được hỗ trợ trong kiến trúc ứng dụng, ví dụ một luồng driver riêng không tham gia transaction đang mở, và kiểm tra kỹ hành vi commit/rollback.

Đối với nghiệp vụ cần tất cả thay đổi cùng thành công hoặc cùng rollback, dùng transaction thông thường do Spring quản lý và tránh chia nhỏ bằng `IN TRANSACTIONS`. Với nhập hoặc cập nhật hàng loạt có thể chấp nhận commit theo từng lô, thiết kế quy trình có thể tiếp tục hoặc chạy lại an toàn.

## 5. Sử dụng CALL trong Spring Data Neo4j

SDN cho phép đặt Cypher trong `@Query`. Kết quả procedure hoặc subquery cần được ánh xạ theo đúng các cột mà câu lệnh trả về.

### Ánh xạ kết quả subquery sang projection

Ví dụ truy vấn trả về số nhóm của mỗi người:

```java
public interface PersonGroupCount {
    String getPersonName();
    Long getGroupCount();
}
```

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("MATCH (p:Person) " +
           "CALL { " +
           "  WITH p " +
           "  OPTIONAL MATCH (p)-[:MEMBER_OF]->(g:Group) " +
           "  RETURN count(g) AS groupCount " +
           "} " +
           "RETURN p.name AS personName, groupCount " +
           "ORDER BY personName")
    List<PersonGroupCount> findPersonGroupCounts();
}
```

Các alias `personName` và `groupCount` cần khớp với getter của projection. Nếu dùng scope clause của Neo4j 5.23 trở lên, phần subquery có thể viết `CALL (p) { ... }`; hãy cân nhắc phiên bản Neo4j đang triển khai trước khi thay cú pháp.

### Ánh xạ kết quả procedure

Ví dụ đọc danh sách label thông qua procedure tích hợp:

```java
public interface LabelView {
    String getLabel();
}
```

```java
public interface GraphMetadataRepository extends Neo4jRepository<Person, String> {

    @Query("CALL db.labels() YIELD label RETURN label ORDER BY label")
    List<LabelView> findGraphLabels();
}
```

Projection giữ kết quả ở dạng dữ liệu ứng dụng cần dùng. Nếu một procedure trả nhiều cột, có thể tạo projection với getter tương ứng hoặc dùng kiểu kết quả phù hợp với mapping của SDN. Kiểm tra tên cột trong `YIELD` và `RETURN` trước khi xử lý lỗi ánh xạ.

Với truy vấn phức tạp hoặc cần điều khiển cách thực thi, `Neo4jClient` và Neo4j Java Driver cũng là các lựa chọn trong hệ sinh thái Spring Data Neo4j. Dù chọn cách nào, vẫn cần bảo đảm tham số được truyền riêng, kiểu kết quả được ánh xạ rõ và transaction phù hợp với loại câu lệnh.

## 6. Cân nhắc tương thích phiên bản

Cú pháp Cypher và tập procedure thay đổi theo phiên bản Neo4j, cấu hình máy chủ và plugin được cài. Bảng sau là mốc định hướng để chọn cú pháp; hãy đối chiếu với phiên bản Neo4j thực tế của môi trường triển khai.

| Tính năng | Mốc hỗ trợ cần lưu ý | Cách chọn |
|---|---|---|
| Gọi procedure bằng `CALL ... YIELD` | Phụ thuộc procedure cụ thể và phiên bản máy chủ | Kiểm tra procedure có trong danh sách và chữ ký của máy chủ |
| Subquery `CALL { ... }` | Có từ Neo4j 4.0 | Dùng cho các môi trường Neo4j hỗ trợ subquery |
| Subquery `IN TRANSACTIONS` | Có từ Neo4j 4.4 | Chỉ dùng cho tác vụ chia lô và thực thi bằng implicit transaction |
| Scope clause `CALL (p) { ... }` | Có từ Neo4j 5.23 | Dùng cú pháp này trên phiên bản hỗ trợ; phiên bản cũ dùng `WITH p` |
| Procedure của APOC | Phụ thuộc phiên bản và việc cài/cấu hình plugin | Xác minh APOC tương thích với Neo4j và được bật ở môi trường đích |

Khi ứng dụng cần hỗ trợ nhiều phiên bản, đừng chỉ kiểm tra phiên bản Spring Data Neo4j. Khả năng thực thi câu lệnh còn phụ thuộc phiên bản Neo4j server và Cypher mà server chấp nhận. Cần xác định phiên bản thấp nhất được hỗ trợ, chạy thử truy vấn trên phiên bản đó và cập nhật tài liệu khi nâng cấp.

## 7. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi procedure không tồn tại | Sai tên, plugin chưa cài hoặc không tương thích phiên bản | Kiểm tra `SHOW PROCEDURES`, chữ ký và cấu hình plugin |
| Dùng sai cột sau `YIELD` | Nhầm tên hoặc kiểu đầu ra của procedure | Đọc chữ ký procedure và chỉ yield các cột có thật |
| Biến ngoài không dùng được trong subquery | Chưa import biến bằng `WITH` hoặc scope clause | Dùng `WITH p` ở phiên bản cũ hoặc `CALL (p)` ở phiên bản mới |
| Truy vấn ngoài không thấy biến bên trong | Subquery chưa đưa biến ra qua `RETURN` | Trả về cột cần dùng và đặt alias rõ ràng |
| Các nhánh `UNION` không tương thích | Số cột, thứ tự hoặc kiểu dữ liệu khác nhau | Chuẩn hóa danh sách cột và kiểu trả về của từng nhánh |
| `IN TRANSACTIONS` lỗi trong service | Câu lệnh đang tham gia transaction tường minh | Thực thi bằng implicit transaction, ngoài ranh giới `@Transactional` |
| Projection không ánh xạ được kết quả | Alias Cypher không khớp getter hoặc kiểu dữ liệu | Đồng bộ alias, getter và kiểu Java |

## 8. Tự kiểm tra

1. Điểm khác nhau cơ bản giữa `CALL db.labels() YIELD label` và `CALL { MATCH ... RETURN ... }` là gì?
2. Vì sao truy vấn dùng `CALL { WITH p ... }` cần đưa `p` vào subquery?
3. Trường hợp nào nên dùng `UNION ALL` thay cho `UNION`?
4. Vì sao `CALL { ... } IN TRANSACTIONS` không phù hợp bên trong một transaction tường minh do `@Transactional` quản lý?
5. Nếu ứng dụng chạy trên Neo4j 5.22 và 5.23, cần chú ý gì khi chọn cú pháp truyền biến vào subquery?
6. Khi một procedure không tồn tại ở môi trường triển khai, bạn sẽ kiểm tra những thông tin nào trước khi thay đổi mã ứng dụng?

Thực hành: chạy `CALL db.labels() YIELD label RETURN label`; sau đó viết một subquery đếm số nhóm mà mỗi người tham gia. Thử lần lượt cú pháp `WITH p` và scope clause `CALL (p)` trên các máy chủ có phiên bản hỗ trợ tương ứng. Cuối cùng, thử một truy vấn cập nhật theo lô trong môi trường thử nghiệm để quan sát ranh giới commit của từng batch.
