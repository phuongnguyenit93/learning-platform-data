# Truy vấn nhiều bước, đường đi và giới hạn số bước duyệt

Trong Neo4j, một truy vấn thường đi theo các mối quan hệ từ node bắt đầu đến những node liên quan. Khi nghiệp vụ cần tìm dữ liệu qua nhiều bước, Cypher cho phép mô tả một đường đi gồm nhiều node và relationship, hoặc dùng mẫu relationship có độ dài thay đổi để duyệt một số bước nhất định. Biết cách giới hạn độ sâu giúp truy vấn thể hiện đúng yêu cầu và tránh tạo ra quá nhiều đường đi không cần thiết.

Với Spring Data Neo4j (SDN), các mẫu truy vấn này thường được đặt trong repository bằng `@Query`. Vì vậy, cần hiểu ngữ nghĩa Cypher trước khi ánh xạ kết quả về entity hoặc projection trong Java.

## 1. Mô tả đường đi qua nhiều relationship

Một đường đi trong Neo4j là chuỗi node được nối với nhau bằng relationship. Trong Cypher, pattern thể hiện node bằng dấu ngoặc tròn và relationship bằng dấu gạch ngang, mũi tên hoặc biểu thức relationship đặt trong cặp dấu ngoặc vuông.

Ví dụ, một khách hàng đặt đơn hàng và đơn hàng chứa sản phẩm:

```cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
      -[:CONTAINS]->(p:Product)
RETURN c, o, p;
```

Pattern trên mô tả hai bước liên tiếp:

1. Từ `Customer`, đi theo relationship `PLACED` có hướng đến `Order`.
2. Từ `Order`, đi theo relationship `CONTAINS` có hướng đến `Product`.

Các biến `c`, `o` và `p` được dùng lại trong `RETURN` để lấy dữ liệu của từng node. Việc ghi rõ label, relationship type và hướng đi giúp truy vấn diễn đạt chính xác cấu trúc đồ thị cần tìm.

Ta cũng có thể chia pattern thành nhiều mệnh đề `MATCH`. Các mệnh đề được nối với nhau thông qua biến chung:

```cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
MATCH (o)-[:CONTAINS]->(p:Product)
RETURN DISTINCT p;
```

Ở đây, biến `o` nối hai phần pattern. Nếu các pattern không chia sẻ biến và không có điều kiện liên kết, truy vấn có thể tạo tích Descartes giữa các kết quả của chúng. Khi muốn nối các bước duyệt, hãy dùng lại biến node hoặc relationship phù hợp.

## 2. Lưu toàn bộ đường đi vào một biến

Cypher cho phép gán một đường đi cho biến bằng cú pháp `pathVariable = pathPattern`. Sau đó có thể trả về đường đi hoặc sử dụng các hàm làm việc với đường đi.

```cypher
MATCH p = (c:Customer {customerId: $customerId})
          -[:PLACED]->(o:Order)
          -[:CONTAINS]->(product:Product)
RETURN p;
```

Trong ví dụ này, `p` là biến đường đi. Các hàm thường dùng gồm:

| Hàm | Giá trị trả về | Mục đích |
|---|---|---|
| `length(p)` | Số relationship trong đường đi | Đếm số bước liên kết |
| `nodes(p)` | Danh sách node trên đường đi | Kiểm tra các thực thể đã đi qua |
| `relationships(p)` | Danh sách relationship trên đường đi | Kiểm tra loại hoặc thuộc tính liên kết |

Ví dụ lấy số bước và tên các node:

```cypher
MATCH p = (c:Customer {customerId: $customerId})
          -[:PLACED]->(o:Order)
          -[:CONTAINS]->(product:Product)
RETURN length(p) AS hops,
       [n IN nodes(p) | labels(n)] AS nodeLabels;
```

`length(p)` đếm relationship, không đếm node. Một đường đi có hai relationship thông thường đi qua ba node. `nodes(p)` bao gồm cả node đầu và node cuối.

## 3. Duyệt relationship với độ dài thay đổi

Trong nhiều bài toán, số bước không cố định. Ví dụ, một người có thể kết nối với người khác qua một, hai hoặc ba mối quan hệ `KNOWS`. Cypher hỗ trợ mẫu relationship có độ dài thay đổi bằng dấu `*` và giới hạn số bước:

```cypher
MATCH p = (start:Person {employeeId: $employeeId})
          -[:KNOWS*1..3]->(target:Person)
RETURN p, target, length(p) AS hops;
```

`*1..3` nghĩa là đường đi có ít nhất một và nhiều nhất ba relationship thuộc loại `KNOWS`. Một số cách viết phổ biến:

| Mẫu | Ý nghĩa |
|---|---|
| `[:KNOWS*1]` | Chính xác một relationship `KNOWS` |
| `[:KNOWS*2..4]` | Từ hai đến bốn relationship |
| `[:KNOWS*..4]` | Từ một đến bốn relationship |
| `[:KNOWS*1..]` | Từ một relationship trở lên, không đặt giới hạn trên tường minh |
| `[:KNOWS*0..3]` | Từ không đến ba relationship |

Khi bỏ giới hạn dưới, cú pháp variable-length relationship truyền thống mặc định bắt đầu từ một bước. Nếu cần cho phép đường đi có độ dài bằng không, phải ghi rõ `0` ở giới hạn dưới.

### Ý nghĩa của đường đi không bước

`*0..3` cho phép kết quả có đường đi độ dài bằng không. Trong trường hợp này, node bắt đầu cũng có thể là node kết thúc mà không cần relationship nào. Điều này có thể phù hợp khi nghiệp vụ chấp nhận thực thể tự thỏa mãn điều kiện kết nối với chính nó.

Nếu yêu cầu bắt buộc phải đi qua ít nhất một relationship, hãy dùng `*1..3`. Việc chọn giới hạn dưới tránh trả về trường hợp không có bước duyệt ngoài ý muốn.

### Lọc node hoặc relationship trên đường đi

Sau khi đặt biến đường đi, có thể sử dụng `nodes(p)` hoặc `relationships(p)` để kiểm tra từng phần tử:

```cypher
MATCH p = (start:Person {employeeId: $employeeId})
          -[:KNOWS*1..3]->(target:Person)
WHERE all(n IN nodes(p) WHERE n.active = true)
RETURN p, target;
```

Điều kiện `all()` yêu cầu mọi node trên đường đi, bao gồm node đầu và node cuối, đều có `active = true`. Nếu chỉ cần kiểm tra node đích, có thể viết điều kiện trực tiếp trên `target`, ví dụ `WHERE target.active = true`.

Có thể lọc thuộc tính relationship theo cùng cách:

```cypher
MATCH p = (start:Person {employeeId: $employeeId})
          -[:KNOWS*1..3]->(target:Person)
WHERE all(r IN relationships(p) WHERE r.confirmed = true)
RETURN p;
```

Truy vấn này chỉ giữ những đường đi mà mọi relationship trên đường đi đều có `confirmed = true`. Nếu property không tồn tại hoặc không thỏa điều kiện, đường đi không đáp ứng biểu thức `all()`.

## 4. Tìm đường đi ngắn nhất

Một số nghiệp vụ cần tìm đường đi có ít relationship nhất giữa hai node, chẳng hạn tìm số kết nối trung gian tối thiểu giữa hai người. Cypher cung cấp `shortestPath()` để tìm một đường đi ngắn nhất và `allShortestPaths()` để lấy tất cả đường đi có cùng độ dài ngắn nhất.

```cypher
MATCH (source:Person {employeeId: $sourceId})
MATCH (target:Person {employeeId: $targetId})
MATCH p = shortestPath((source)-[:KNOWS*1..6]->(target))
RETURN p, length(p) AS hops;
```

Đường đi được tìm trong phạm vi pattern đã chỉ định: chỉ đi theo `KNOWS`, đúng hướng mũi tên và tối đa sáu relationship. Nếu có nhiều đường đi cùng độ dài ngắn nhất, `shortestPath()` trả về một đường đi ngắn nhất; dùng `allShortestPaths()` khi cần tất cả các đường đi ngắn nhất.

Không nên dùng shortest path chỉ vì muốn giảm số kết quả. Hãy dùng nó khi yêu cầu nghiệp vụ thực sự là tìm đường đi ít bước nhất. Nếu cần mọi đường đi thỏa điều kiện, hãy dùng pattern thông thường và đặt giới hạn độ sâu phù hợp.

## 5. Giới hạn độ sâu để kiểm soát truy vấn

Độ sâu duyệt là số relationship tối đa được đi qua từ node bắt đầu. Với cú pháp variable-length relationship, giới hạn trên được đặt sau dấu `..`, ví dụ `*1..4` cho phép tối đa bốn bước.

Giới hạn độ sâu có tác dụng rõ rệt khi một node có nhiều relationship. Mỗi bước tiếp theo có thể mở rộng sang nhiều node khác; số đường đi cần xét vì thế có thể tăng nhanh theo độ sâu và số liên kết trung bình của mỗi node.

Một số nguyên tắc khi thiết kế truy vấn:

1. Xác định node bắt đầu bằng label và property có tính chọn lọc, chẳng hạn `Person` cùng `employeeId`.
2. Chỉ duyệt relationship type cần thiết và chọn đúng hướng đi.
3. Đặt giới hạn trên theo phạm vi nghiệp vụ, ví dụ chỉ tìm trong ba hoặc bốn bước kết nối.
4. Chỉ trả về dữ liệu cần dùng. Nếu chỉ cần node đích, trả về `target` thay vì toàn bộ `p`.
5. Dùng `DISTINCT` khi muốn loại node đích trùng nhau do có nhiều đường đi khác nhau.
6. Kiểm tra kế hoạch và số liệu thực thi bằng `EXPLAIN` hoặc `PROFILE` trên dữ liệu gần với thực tế.

Ví dụ, truy vấn sau giới hạn tìm người trong tối đa ba kết nối từ một người cụ thể:

```cypher
MATCH (start:Person {employeeId: $employeeId})
      -[:KNOWS*1..3]->(target:Person)
RETURN DISTINCT target.employeeId, target.name;
```

`DISTINCT` ở đây loại các dòng trùng khi một người có thể được tiếp cận qua nhiều đường đi. Nếu mục tiêu là phân tích từng đường đi, hãy bỏ `DISTINCT` và trả về biến đường đi `p`.

`LIMIT` không thay thế giới hạn độ sâu. `LIMIT 20` giới hạn số dòng được trả về, nhưng không có nghĩa là Cypher chỉ duyệt tối đa 20 relationship hoặc tối đa 20 node. Muốn kiểm soát số bước, hãy đặt giới hạn trực tiếp trong pattern, ví dụ `*1..3`.

## 6. Kết hợp nhiều bước duyệt trong Spring Data Neo4j

SDN cho phép khai báo Cypher tùy chỉnh bằng `@Query` trong repository. Ví dụ, repository sau tìm những người có thể tiếp cận từ một nhân viên qua tối đa ba relationship `KNOWS`:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (start:Person {employeeId: $employeeId})
              -[:KNOWS*1..3]->(target:Person)
        RETURN DISTINCT target
        """)
    List<Person> findPeopleWithinThreeConnections(
            @Param("employeeId") String employeeId);
}
```

Truy vấn dùng tham số `employeeId` để xác định node bắt đầu. `RETURN DISTINCT target` giúp SDN ánh xạ các node đích thành danh sách `Person` mà không lặp một người nhiều lần khi có nhiều đường đi dẫn đến cùng node.

Nếu service cần thực hiện nhiều truy vấn đọc/ghi như một đơn vị nghiệp vụ, có thể đặt lời gọi repository trong phương thức service được quản lý transaction bằng `@Transactional`. Còn với truy vấn duyệt đường đi chỉ đọc như ví dụ trên, việc đặt giới hạn độ sâu và chọn đúng dữ liệu trả về vẫn là trách nhiệm thiết kế truy vấn.

## 7. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `*` mà không xác định phạm vi độ sâu | Có thể tạo ra lượng đường đi lớn và tốn tài nguyên | Đặt giới hạn trên theo yêu cầu nghiệp vụ |
| Dùng `*0..N` khi phải có ít nhất một kết nối | Có thể nhận đường đi độ dài bằng không | Dùng `*1..N` |
| Nhầm `LIMIT` với giới hạn số bước | Số dòng trả về bị giới hạn nhưng phạm vi duyệt vẫn có thể rộng | Giới hạn ngay trong relationship pattern |
| Quên hướng relationship | Truy vấn có thể không tìm thấy đường đi theo hướng dữ liệu thực tế | Kiểm tra hướng được tạo và dùng đúng mũi tên; dùng pattern không hướng khi nghiệp vụ cho phép cả hai chiều |
| Dùng nhiều `MATCH` không có biến nối chung | Có thể tạo tích Descartes và tăng mạnh số kết quả | Dùng chung biến node hoặc relationship giữa các pattern |
| Trả về toàn bộ path dù chỉ cần node cuối | Tăng lượng dữ liệu truyền và xử lý ở ứng dụng | Chỉ `RETURN target` hoặc các property cần thiết |
| Dùng `shortestPath()` khi cần mọi đường đi | Bỏ qua các đường đi khác có thể quan trọng với nghiệp vụ | Dùng pattern thường hoặc `allShortestPaths()` đúng mục tiêu |

## 8. Thực hành: tìm người trong tối đa ba kết nối

Tạo một đồ thị nhỏ để mô phỏng mạng lưới quen biết:

```cypher
CREATE
  (lan:Person {employeeId: 'P-01', name: 'Lan', active: true}),
  (minh:Person {employeeId: 'P-02', name: 'Minh', active: true}),
  (hoa:Person {employeeId: 'P-03', name: 'Hoa', active: true}),
  (nam:Person {employeeId: 'P-04', name: 'Nam', active: false}),
  (lan)-[:KNOWS]->(minh),
  (minh)-[:KNOWS]->(hoa),
  (hoa)-[:KNOWS]->(nam),
  (lan)-[:KNOWS]->(hoa);
```

Thử các truy vấn sau:

```cypher
// A. Tìm người kết nối trực tiếp với Lan
MATCH (lan:Person {employeeId: 'P-01'})-[:KNOWS*1]->(target:Person)
RETURN target.name;

// B. Tìm người trong tối đa hai bước từ Lan
MATCH p = (lan:Person {employeeId: 'P-01'})-[:KNOWS*1..2]->(target:Person)
RETURN target.name, length(p) AS hops;

// C. Chỉ giữ đường đi mà mọi node đều active
MATCH p = (lan:Person {employeeId: 'P-01'})-[:KNOWS*1..3]->(target:Person)
WHERE all(n IN nodes(p) WHERE n.active = true)
RETURN target.name, length(p) AS hops;

// D. Tìm một đường đi ngắn nhất đến Hoa
MATCH (lan:Person {employeeId: 'P-01'}),
      (hoa:Person {employeeId: 'P-03'})
MATCH p = shortestPath((lan)-[:KNOWS*1..3]->(hoa))
RETURN p, length(p) AS hops;
```

Hãy giải thích vì sao truy vấn A tìm được Minh và Hoa, truy vấn B có thể tìm Hoa qua một hoặc hai bước, còn truy vấn C loại đường đi có node không active. Truy vấn D chọn một đường đi ngắn nhất trong phạm vi tối đa ba relationship. Từ kết quả đó, thử thay đổi giới hạn trên và quan sát số đường đi hoặc node đích được trả về.

## Kết luận

Cypher biểu diễn truy vấn nhiều bước bằng cách nối các node và relationship trong pattern. Biến đường đi giúp truy cập toàn bộ path, đếm số relationship và kiểm tra node hoặc relationship trên đường đi. Với quan hệ có độ dài thay đổi, cú pháp `*min..max` cho phép kiểm soát số bước duyệt; `shortestPath()` phù hợp khi cần đường đi ngắn nhất. Khi tích hợp với Spring Data Neo4j, hãy neo truy vấn vào node bắt đầu phù hợp, giới hạn độ sâu, trả về đúng dữ liệu cần dùng và kiểm tra hiệu năng bằng kế hoạch thực thi.
