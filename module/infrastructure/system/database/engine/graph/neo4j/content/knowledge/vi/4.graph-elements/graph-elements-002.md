# Quan hệ có hướng, loại quan hệ và hai nút đầu–cuối

## 1. Mục tiêu và vị trí của chủ đề trong Neo4j

Trong mô hình **property graph** của Neo4j, một **nút** (*node*) biểu diễn thực thể, còn **quan hệ** (*relationship*) nối hai nút và diễn đạt cách các thực thể liên hệ với nhau. Quan hệ là thành phần thiết yếu để mô hình hóa dữ liệu liên kết, từ đó truy vấn quan hệ và đường đi bằng **Cypher**.

Trong chương **Thành phần đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`, bài này tập trung vào ba đặc điểm cốt lõi của quan hệ:

1. **Tính có hướng**: mỗi quan hệ được lưu theo chiều từ **nút đầu** đến **nút cuối**.
2. **Loại quan hệ** (*relationship type*): một tên mô tả ý nghĩa của liên kết, chẳng hạn `FOLLOWS`, `WORKS_AT` hoặc `PURCHASED`.
3. **Hai đầu mút**: một quan hệ nối đúng hai nút; các nút có thể mang nhãn và thuộc tính của riêng mình.

Học xong, bạn sẽ tạo và truy vấn quan hệ theo hướng, đọc loại và hai đầu mút, cập nhật thuộc tính của quan hệ, phân biệt các trường hợp dễ nhầm và biết cách thiết kế hướng liên kết phù hợp với ứng dụng Java Driver, Spring Data Neo4j và các truy vấn đường đi sau này.

## 2. Quan hệ là gì trong property graph?

Xét một mạng xã hội có hai người:

```text
(:Person {personId: 'P001', name: 'An'})
                 |
                 |  [:FOLLOWS {since: 2024-01-20}]
                 v
(:Person {personId: 'P002', name: 'Bình'})
```

Sơ đồ trên diễn đạt: **An theo dõi Bình**. Trong đó:

- Nút **An** là **nút đầu** (*start node*) của quan hệ.
- Nút **Bình** là **nút cuối** (*end node*) của quan hệ.
- `FOLLOWS` là **loại quan hệ**.
- `since` là **thuộc tính của quan hệ**, cho biết thời điểm việc theo dõi bắt đầu.

Mẫu Cypher tương ứng:

```cypher
(an:Person)-[:FOLLOWS]->(binh:Person)
```

Trong cách viết này, `an` và `binh` là biến dùng trong truy vấn, `:Person` là **nhãn của nút**, còn `:FOLLOWS` là **loại quan hệ**. Dấu `->` thể hiện chiều từ nút bên trái sang nút bên phải.

Một relationship trong Neo4j có các đặc điểm:

| Đặc điểm | Diễn giải |
| --- | --- |
| Hai đầu mút | Nối **đúng hai nút**: một nút đầu và một nút cuối |
| Hướng | Luôn có chiều lưu trữ từ đầu đến cuối |
| Loại | Mỗi quan hệ có **đúng một loại quan hệ** |
| Thuộc tính | Có thể mang không, một hoặc nhiều cặp khóa–giá trị |
| Danh tính | Là một phần tử riêng của đồ thị; hai quan hệ có cùng hai đầu mút và cùng loại vẫn có thể khác nhau |
| Phụ thuộc nút | Quan hệ phải nối các nút tồn tại trong đồ thị; không có quan hệ đứng riêng không gắn với nút |

Neo4j hỗ trợ **nhiều quan hệ giữa cùng một cặp nút**, kể cả cùng loại và cùng hướng. Vì vậy, không thể mặc định rằng cặp nút `(An, Bình)` chỉ có một cạnh duy nhất.

## 3. Tính có hướng: chiều được lưu và chiều được truy vấn

### 3.1. Hướng lưu trữ của quan hệ

Trong Neo4j, **mọi quan hệ đều có hướng**. Hai câu sau biểu diễn hai hướng khác nhau:

```cypher
(an)-[:FOLLOWS]->(binh)  // An theo dõi Bình
(an)<-[:FOLLOWS]-(binh)  // Bình theo dõi An
```

Nếu chỉ tồn tại quan hệ `(an)-[:FOLLOWS]->(binh)`, không thể suy ra có thêm quan hệ ngược chiều. Đặc biệt với các loại như `FOLLOWS`, `OWNS`, `MANAGES`, `PARENT_OF`, hướng có ý nghĩa nghiệp vụ và cần được lựa chọn cẩn thận.

Ví dụ:

- `(employee)-[:WORKS_AT]->(company)`: nhân viên làm việc tại công ty.
- `(customer)-[:PLACED]->(order)`: khách hàng đặt đơn hàng.
- `(order)-[:CONTAINS]->(product)`: đơn hàng chứa sản phẩm.
- `(serviceA)-[:CALLS]->(serviceB)`: dịch vụ A gọi dịch vụ B.

Đảo hướng những liên kết này mà không đổi cách hiểu sẽ làm sai ngữ nghĩa của dữ liệu.

### 3.2. Hướng trong mẫu truy vấn Cypher

Cypher cho phép truy vấn theo **chiều đi ra**, **chiều đi vào** hoặc **không ràng buộc chiều**. Giả sử `a` là nút đã biết:

| Mẫu | Ý nghĩa |
| --- | --- |
| `(a)-[:FOLLOWS]->(b)` | Tìm `b` mà `a` đang theo dõi |
| `(a)<-[:FOLLOWS]-(b)` | Tìm `b` đang theo dõi `a` |
| `(a)-[:FOLLOWS]-(b)` | Tìm `b` liên quan với `a` bằng `FOLLOWS` theo **bất kỳ chiều nào** |
| `(a)-[r]->(b)` | Tìm mọi loại quan hệ đi ra từ `a`; lưu quan hệ vào biến `r` |
| `(a)<-[r]-(b)` | Tìm mọi loại quan hệ đi vào `a` |
| `(a)-[r]-(b)` | Tìm quan hệ thuộc mọi loại và theo bất kỳ chiều nào |

**Cần phân biệt:** Mẫu `(a)-[:FOLLOWS]-(b)` **không biến** quan hệ thành vô hướng trong cơ sở dữ liệu. Nó chỉ cho phép truy vấn khớp cạnh theo cả hai hướng. Giá trị nút đầu và nút cuối đã lưu vẫn không thay đổi.

Ví dụ, nếu đồ thị có cả hai quan hệ `An -> Bình` và `Bình -> An`, truy vấn không ràng buộc hướng từ `An` sẽ thấy **cả hai quan hệ**. Khi truy vấn bắt đầu từ hai biến chưa bị ràng buộc, có thể xuất hiện các cách gán nút đầu–cuối đối xứng; hãy dùng hướng rõ ràng hoặc `DISTINCT` khi cần kết quả không trùng theo thực thể.

### 3.3. Quan hệ mang ý nghĩa hai chiều

Trong đời thực, có các liên kết mang nghĩa đối xứng như “là bạn bè với” hoặc “kết nối với”. Neo4j vẫn yêu cầu hướng lưu trữ. Có hai lựa chọn thiết kế thường gặp:

1. **Lưu một quan hệ**, chẳng hạn `(a)-[:FRIENDS_WITH]->(b)`, rồi truy vấn bằng mẫu không ràng buộc hướng `-[:FRIENDS_WITH]-`. Cần quy ước tránh tạo thêm cạnh đối xứng trùng nghĩa.
2. **Lưu hai quan hệ có hướng**, `(a)-[:FRIENDS_WITH]->(b)` và `(b)-[:FRIENDS_WITH]->(a)`, khi nghiệp vụ cần hai hành động hoặc hai bản ghi độc lập.

Không có lựa chọn đúng cho mọi bài toán: hãy thống nhất **ngữ nghĩa nghiệp vụ**, cách ghi và cách truy vấn. Ví dụ `FOLLOWS` vốn không đối xứng, nên chỉ thêm quan hệ ngược chiều khi người kia thực sự cũng theo dõi lại.

## 4. Relationship type: loại quan hệ diễn đạt ngữ nghĩa

**Relationship type** là tên dùng để phân biệt ý nghĩa các liên kết. Trong Cypher, viết loại sau dấu `:` trong dấu ngoặc vuông:

```cypher
(p:Person)-[:WORKS_AT]->(c:Company)
(p:Person)-[:FOLLOWS]->(q:Person)
(c:Company)-[:OPERATES_IN]->(city:City)
```

Một người có thể đồng thời làm việc tại công ty và theo dõi người khác, nhưng đây là **hai loại quan hệ khác nhau**. Không nên dồn mọi liên kết thành một loại chung như `:RELATED_TO` rồi phụ thuộc hoàn toàn vào thuộc tính `kind`, trừ khi có lý do mô hình hóa rõ ràng.

### 4.1. Một quan hệ có đúng một type

Đối chiếu với label của nút:

| Node label | Relationship type |
| --- | --- |
| Một nút có thể có nhiều label: `:Person:Employee` | Một quan hệ chỉ có một type: `:WORKS_AT` |
| Label phân loại thực thể/vai trò | Type mô tả bản chất mối liên kết |
| Đọc bằng `labels(n)` | Đọc bằng `type(r)` |
| Có thể thêm hoặc loại bỏ label bằng `SET`/`REMOVE` | Không cập nhật trực tiếp type của một quan hệ hiện có; khi cần đổi type, tạo quan hệ mới và xóa quan hệ cũ sau khi xử lý dữ liệu phù hợp |

Về quy ước, tên type thường viết chữ hoa có dấu gạch dưới: `WORKS_AT`, `PLACED_ORDER`, `DEPENDS_ON`. Đây là cách đặt tên để dễ đọc, không phải yêu cầu bắt buộc của Neo4j. Tên type có phân biệt chữ hoa và chữ thường; `FOLLOWS` khác `follows`.

### 4.2. Chọn tên type theo câu diễn đạt cụ thể

Hãy đọc mẫu `(a)-[:TYPE]->(b)` thành một câu:

| Mẫu | Câu mô tả |
| --- | --- |
| `(user)-[:FOLLOWS]->(author)` | Người dùng theo dõi tác giả |
| `(order)-[:CONTAINS]->(product)` | Đơn hàng chứa sản phẩm |
| `(developer)-[:CONTRIBUTES_TO]->(project)` | Lập trình viên đóng góp cho dự án |
| `(topic)-[:PREREQUISITE_OF]->(lesson)` | Chủ đề là điều kiện tiên quyết của bài học |

Nếu câu diễn đạt khó hiểu hoặc hướng có thể bị diễn giải ngược, hãy điều chỉnh **tên type**, **hướng** hoặc cả hai trước khi nhập nhiều dữ liệu.

## 5. Hai đầu mút: start node và end node

Mỗi relationship có **start node** và **end node**. Đây là vai trò của hai nút **đối với chính quan hệ đó**, không phải loại nút hay nhãn cố định.

Một nút có thể là **end node** của quan hệ này và đồng thời là **start node** của quan hệ khác:

```text
(:Person {name: 'An'})
        |
        |  [:FOLLOWS]
        v
(:Person {name: 'Bình'})
        |
        |  [:WORKS_AT]
        v
(:Company {name: 'GreenTech'})
```

Trong sơ đồ, **Bình** là nút cuối của quan hệ `An -[:FOLLOWS]-> Bình`, nhưng là nút đầu của quan hệ `Bình -[:WORKS_AT]-> GreenTech`.

Cypher có các hàm để kiểm tra trực tiếp:

```cypher
MATCH ()-[r:FOLLOWS]->()
RETURN type(r) AS relationshipType,
       startNode(r) AS startNode,
       endNode(r) AS endNode
LIMIT 10;
```

Với đồ thị lớn, thường nên chọn nút theo nhãn và định danh trước khi duyệt cạnh:

```cypher
MATCH (a:Person {personId: 'P001'})-[r:FOLLOWS]->(b:Person)
RETURN a.fullName AS follower,
       b.fullName AS followedPerson,
       type(r) AS relationshipType,
       startNode(r).personId AS fromId,
       endNode(r).personId AS toId;
```

`startNode(r)` và `endNode(r)` đọc hai đầu mút theo **hướng được lưu**, kể cả khi truy vấn đã tìm quan hệ bằng mẫu không ràng buộc hướng. Hai hàm này trả về **nút**, nên có thể truy cập thuộc tính của chúng như `startNode(r).personId`.

### 5.1. Self-loop: hai đầu mút có thể là một nút

Quan hệ vẫn có **hai vai trò đầu–cuối** ngay cả khi chúng cùng tham chiếu **một nút**. Trường hợp này gọi là **self-loop**:

```text
           ┌── [:RETRIES] ──┐
           │                │
           ▼                │
      (:Job {id: 'J001'}) ──┘
```

Ví dụ minh họa bằng Cypher:

```cypher
CREATE (s:State {stateId: 'S001', name: 'Waiting'})
CREATE (s)-[:TRANSITIONS_TO {reason: 'retry'}]->(s)
RETURN s;
```

Đây là một quan hệ hợp lệ: `startNode(r) = endNode(r)`. Trong một ứng dụng cụ thể, self-loop có thể là hành vi có ý nghĩa hoặc lỗi dữ liệu; cần xác định quy tắc nghiệp vụ, không mặc định mọi vòng tự nối đều sai.

### 5.2. Hướng không phụ thuộc vị trí hiển thị

Trong trình trực quan hóa, công cụ có thể vẽ An ở bên phải Bình, đảo vị trí dọc/ngang hoặc sắp xếp lại toàn bộ sơ đồ. **Vị trí trên màn hình không quyết định hướng**; hướng được xác định bởi relationship được lưu và mẫu mũi tên trong Cypher. Luôn dựa vào `startNode(r)`, `endNode(r)` và type khi cần xác minh.

## 6. Thực hành với một đồ thị mẫu

Các ví dụ trong mục này có thể chạy trên một **database thử nghiệm**. Lệnh `CREATE` luôn tạo phần tử mới; chỉ chạy bước khởi tạo một lần để tránh trùng nút hoặc trùng quan hệ.

### 6.1. Tạo nút và các quan hệ có hướng

```cypher
CREATE (an:Person {personId: 'P001', fullName: 'An'})
CREATE (binh:Person {personId: 'P002', fullName: 'Bình'})
CREATE (company:Company {companyId: 'C001', name: 'GreenTech'})
CREATE (an)-[:FOLLOWS {since: date('2024-01-20')}]->(binh)
CREATE (binh)-[:FOLLOWS {since: date('2025-04-12')}]->(an)
CREATE (an)-[:WORKS_AT {
  since: date('2022-09-01'),
  position: 'Developer'
}]->(company)
RETURN an, binh, company;
```

Ta đã tạo **ba nút** và **ba quan hệ**:

```text
 (An:Person) -[:FOLLOWS]-> (Bình:Person)
 (An:Person) <-[:FOLLOWS]- (Bình:Person)
 (An:Person) -[:WORKS_AT]-> (GreenTech:Company)
```

Hai cạnh `FOLLOWS` có hướng ngược nhau nên mang hai ý nghĩa khác nhau: An theo dõi Bình, và Bình theo dõi An.

### 6.2. Tìm quan hệ đi ra

```cypher
MATCH (an:Person {personId: 'P001'})-[r:FOLLOWS]->(other:Person)
RETURN an.fullName AS source,
       other.fullName AS target,
       r.since AS followedSince;
```

Kết quả dự kiến theo dữ liệu mẫu: `An` → `Bình`, bắt đầu ngày `2024-01-20`.

### 6.3. Tìm quan hệ đi vào

```cypher
MATCH (an:Person {personId: 'P001'})<-[r:FOLLOWS]-(follower:Person)
RETURN follower.fullName AS follower,
       an.fullName AS followedPerson,
       r.since AS followedSince;
```

Kết quả dự kiến: `Bình` → `An`, bắt đầu ngày `2025-04-12`. Chỉ khác chiều mũi tên trong mẫu, ý nghĩa truy vấn đã thay đổi.

### 6.4. Truy vấn không ràng buộc hướng

```cypher
MATCH (an:Person {personId: 'P001'})-[r:FOLLOWS]-(other:Person)
RETURN type(r) AS type,
       startNode(r).fullName AS fromName,
       endNode(r).fullName AS toName,
       r.since AS since
ORDER BY since;
```

Truy vấn này thấy **hai quan hệ `FOLLOWS`** nối An với Bình. Hàm `startNode(r)` và `endNode(r)` vẫn cho thấy hướng riêng của từng cạnh; chúng không phụ thuộc vào hướng mà truy vấn dùng để tìm thấy cạnh.

### 6.5. Duyệt các loại quan hệ đi ra

```cypher
MATCH (an:Person {personId: 'P001'})-[r]->(destination)
RETURN type(r) AS type,
       labels(destination) AS targetLabels,
       properties(destination) AS targetProperties
ORDER BY type;
```

Ở dữ liệu mẫu, An có quan hệ `FOLLOWS` đến Bình và quan hệ `WORKS_AT` đến GreenTech. Hàm `type(r)` trả về một chuỗi biểu thị loại của từng quan hệ; `labels(destination)` trả về danh sách nhãn của **nút cuối**.

### 6.6. Đếm quan hệ theo loại và chiều

```cypher
MATCH (p:Person {personId: 'P001'})-[r]->()
RETURN type(r) AS relationshipType, count(r) AS outgoingCount
ORDER BY relationshipType;
```

Trong ví dụ này, An có một `FOLLOWS` đi ra và một `WORKS_AT` đi ra. Nếu muốn thống kê người theo dõi An, phải đếm quan hệ đi **vào** bằng mẫu `(p)<-[r:FOLLOWS]-()`.

## 7. Thuộc tính của quan hệ và cách thao tác

Relationship trong Neo4j cũng có các **property** như node. Thuộc tính thuộc về liên kết khi nó mô tả **chính mối liên kết**, chẳng hạn:

- `FOLLOWS.since`: theo dõi từ ngày nào.
- `WORKS_AT.position`: chức vụ của một người **tại công ty này**.
- `TRANSFERRED.amount`: số tiền **trong lần chuyển tiền này**.
- `DEPENDS_ON.reason`: lý do thành phần A phụ thuộc thành phần B.

Nếu cùng một người làm việc cho nhiều công ty, `position` có thể khác nhau ở từng quan hệ `WORKS_AT`; gắn chức vụ trực tiếp lên nút `Person` có thể làm mất bối cảnh.

### 7.1. Đọc thuộc tính từ relationship

```cypher
MATCH (an:Person {personId: 'P001'})-[r:WORKS_AT]->(c:Company)
RETURN c.name AS company,
       r.position AS position,
       r.since AS startDate,
       properties(r) AS allRelationshipProperties;
```

`r` là biến đại diện cho relationship. `r.position` đọc property riêng của quan hệ, còn `properties(r)` trả về map thuộc tính hiện có.

### 7.2. Thêm, sửa và xóa property

```cypher
MATCH (:Person {personId: 'P001'})-[r:WORKS_AT]->
      (:Company {companyId: 'C001'})
SET r.position = 'Senior Developer',
    r.updatedAt = datetime()
RETURN properties(r) AS properties;
```

Xóa **một thuộc tính** không làm mất quan hệ:

```cypher
MATCH (:Person {personId: 'P001'})-[r:WORKS_AT]->
      (:Company {companyId: 'C001'})
REMOVE r.updatedAt
RETURN keys(r) AS remainingPropertyKeys;
```

Tương tự node, property của relationship không lưu giá trị `null` theo cách thông thường: `SET r.position = null` sẽ xóa thuộc tính đó. `SET r += {position: 'Lead'}` cập nhật/thêm các khóa trong map; `SET r = {...}` thay toàn bộ tập property nên cần thận trọng.

### 7.3. Xóa một quan hệ

```cypher
MATCH (an:Person {personId: 'P001'})-[r:FOLLOWS]->
      (binh:Person {personId: 'P002'})
DELETE r;
```

`DELETE r` xóa **quan hệ đã khớp**, không xóa hai nút An và Bình. Đây là thao tác thay đổi dữ liệu; nếu muốn tiếp tục sử dụng bộ dữ liệu mẫu nguyên trạng ở các phần sau, hãy bỏ qua lệnh này hoặc tạo lại quan hệ. Xóa một nút khi nó còn quan hệ yêu cầu xử lý các cạnh liên quan; `DETACH DELETE` sẽ xóa nút **và** các quan hệ nối vào nút đó.

## 8. Tạo quan hệ đúng: CREATE, MATCH và MERGE

### 8.1. Không tạo thừa nút khi chỉ cần thêm cạnh

Khi hai nút đã tồn tại, cách thông dụng là **MATCH hai nút trước**, rồi `CREATE` quan hệ giữa chúng:

```cypher
MATCH (a:Person {personId: 'P001'})
MATCH (b:Person {personId: 'P002'})
CREATE (a)-[r:COLLABORATES_WITH {since: date()}]->(b)
RETURN a.fullName, type(r), b.fullName;
```

Trong câu này, `a` và `b` đã được ràng buộc là hai nút hiện có. Nếu không tìm thấy một trong hai nút, truy vấn sẽ không tạo cạnh. Nếu chạy lại, `CREATE` có thể tạo thêm một quan hệ `COLLABORATES_WITH` cùng hai đầu mút.

### 8.2. MERGE để tìm hoặc tạo liên kết

Khi nghiệp vụ mong muốn tồn tại **một liên kết cùng loại, cùng hướng giữa hai nút**, có thể viết:

```cypher
MATCH (a:Person {personId: $fromId})
MATCH (b:Person {personId: $toId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.since = date()
RETURN a.personId AS fromId,
       b.personId AS toId,
       r.since AS since;
```

Hai tham số `$fromId` và `$toId` đến từ ứng dụng Java Driver, Spring Data Neo4j hoặc client gọi Cypher. Việc **khớp hai nút trước** giúp `MERGE` tập trung vào liên kết cần tạo, tránh mẫu tạo nhầm nút vì chưa ràng buộc định danh.

Một vài điểm quan trọng:

- `MERGE` khớp **hướng** và **type** của quan hệ. `(a)-[:FOLLOWS]->(b)` không phải `(b)-[:FOLLOWS]->(a)`.
- `ON CREATE SET` chỉ thiết lập thuộc tính khi tạo cạnh mới, không sửa ngày theo dõi của cạnh có sẵn.
- Nếu dữ liệu đã có **nhiều quan hệ cùng mẫu**, `MERGE` có thể khớp nhiều kết quả; nó không tự hợp nhất hay xóa cạnh trùng.
- Dùng `MERGE` không thay cho thiết kế chống trùng khi nhiều giao dịch ghi đồng thời. Cần quy ước khóa, ràng buộc khả dụng và xử lý giao dịch phù hợp.
- `WHERE a <> b` trong ví dụ thể hiện quy tắc **không tự theo dõi mình**. Neo4j vẫn cho phép self-loop nếu không có quy tắc này.

### 8.3. Có nhiều cạnh cùng loại có phải lỗi?

Không nhất thiết. Neo4j cho phép:

```text
(:Person {id: 'P001'})
      |-- [:VISITED {on: 2025-03-01}] --> (:Place {id: 'L001'})
      |-- [:VISITED {on: 2025-04-15}] --> (:Place {id: 'L001'})
```

Hai cạnh `VISITED` biểu diễn hai lần ghé thăm khác nhau. Ngược lại, hai cạnh `FOLLOWS` hoàn toàn giống nhau giữa cùng người theo cùng hướng thường là lỗi nhập trùng. Khi hành động có danh tính riêng, nhiều trường và vòng đời riêng, có thể cân nhắc mô hình **nút sự kiện** `:Visit` nối với `Person` và `Place` để quản lý tốt hơn.

## 9. Chọn mô hình quan hệ cho các bài toán thực tế

### 9.1. Hệ thống đặt hàng

```text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(:Product)
```

`PLACED` đi từ khách hàng đến đơn hàng vì người mua **đặt** đơn. `CONTAINS` đi từ đơn hàng đến sản phẩm vì đơn **chứa** sản phẩm. Việc đọc chuỗi quan hệ từ trái sang phải cho phép hiểu ngay nghiệp vụ.

Nếu một đơn chứa nhiều sản phẩm và cần `quantity`, hãy cân nhắc đặt số lượng trên quan hệ `CONTAINS`. Tuy nhiên, nếu có nhiều dòng hàng của cùng sản phẩm với giá/khuyến mãi khác nhau, một nút `:OrderLine` riêng có thể giúp biểu diễn chính xác hơn.

### 9.2. Đồ thị phụ thuộc dịch vụ

```text
(:Service {name: 'payment-api'})
            |
            | [:DEPENDS_ON]
            v
(:Service {name: 'database'})
```

Từ payment-api, mẫu `-[:DEPENDS_ON]->` tìm thành phần mà dịch vụ này phụ thuộc. Từ database, mẫu `<-[:DEPENDS_ON]-` tìm các dịch vụ phụ thuộc vào database. Hướng cần thống nhất vì nó ảnh hưởng trực tiếp đến truy vấn phân tích sự cố và lan truyền ảnh hưởng.

### 9.3. Đồ thị học tập

```text
(:Lesson {code: 'L01'})
            |
            | [:PREREQUISITE_OF]
            v
(:Lesson {code: 'L02'})
```

Ở đây, L01 là điều kiện tiên quyết của L02. Nếu hệ thống chọn tên `REQUIRES` thì hướng phù hợp lại là `(L02)-[:REQUIRES]->(L01)`. Hai cách đều mô tả cùng yêu cầu học trước–học sau, nhưng **tên type và hướng phải nhất quán** trong toàn bộ dữ liệu và truy vấn.

## 10. Quan hệ có hướng và truy vấn đường đi

Khi chuyển sang phân tích đường đi, hướng của từng cạnh ảnh hưởng đến khả năng di chuyển trên đồ thị.

Ví dụ chuỗi phụ thuộc:

```text
(:Service {name: 'A'}) -[:DEPENDS_ON]->
(:Service {name: 'B'}) -[:DEPENDS_ON]->
(:Service {name: 'C'})
```

Muốn tìm đường phụ thuộc từ A đến C theo **chiều phụ thuộc**, dùng mẫu đường đi có hướng:

```cypher
MATCH p = (:Service {name: 'A'})-[:DEPENDS_ON*1..3]->
          (:Service {name: 'C'})
RETURN p;
```

Mẫu độ dài biến thiên `*1..3` là cú pháp Cypher truyền thống, chỉ ra từ **một đến ba quan hệ** có hướng `DEPENDS_ON`; với bản Neo4j/Cypher mới còn có cú pháp quantified path patterns để mô tả các đường đi tương tự. Nếu thay `->` bằng mẫu không ràng buộc hướng, truy vấn sẽ có thể đi qua cạnh theo cả hai chiều, làm thay đổi ý nghĩa của “phụ thuộc từ A đến C”.

Khi cần tối ưu truy vấn, hãy bắt đầu từ các nút có định danh rõ ràng, chọn type và hướng cụ thể rồi kiểm tra `EXPLAIN` hoặc `PROFILE`. Việc duyệt không ràng buộc loại và chiều có thể mở rộng số cạnh cần xem xét, nhất là ở nút có bậc lớn.

## 11. Kiểm soát chất lượng dữ liệu và tích hợp ứng dụng

### 11.1. Kiểm tra điều gì khi nhập dữ liệu?

| Câu hỏi kiểm tra | Vì sao cần thiết? |
| --- | --- |
| Nút đầu và nút cuối có tồn tại? | Tránh liên kết đến thực thể chưa được nhận diện |
| Hướng đã đúng với cách gọi type? | Tránh đảo ý nghĩa nghiệp vụ |
| Type có đúng quy ước? | `WORKS_AT` khác `works_at`; truy vấn theo type sẽ không khớp |
| Cạnh trùng có được phép? | Phân biệt quan hệ trạng thái và những lần xảy ra sự kiện |
| Thuộc tính thuộc về nút hay quan hệ? | Giữ đúng ngữ cảnh khi một nút có nhiều liên kết |
| Có cần xác thực số lượng quan hệ? | Một nhân viên có thể có nhiều vai trò/công ty tùy mô hình; type không tự áp đặt số lượng cạnh |

Neo4j có index và constraint cho các thành phần phù hợp, nhưng **relationship type không tự định nghĩa cardinality** như “mỗi nhân viên chỉ được có một quan hệ `WORKS_AT` đang hiệu lực”. Quy tắc như vậy cần được thiết kế và thực thi bằng mô hình, truy vấn ghi, giao dịch và/hoặc kiểm soát ứng dụng.

### 11.2. Java Driver và Spring Data Neo4j

Khi ứng dụng Java tạo liên kết giữa hai thực thể, nên dùng **tham số** cho định danh nghiệp vụ và giá trị thuộc tính:

```cypher
MATCH (person:Person {personId: $personId})
MATCH (company:Company {companyId: $companyId})
MERGE (person)-[r:WORKS_AT]->(company)
ON CREATE SET r.since = date($startDate)
RETURN type(r) AS type,
       person.personId AS fromPersonId,
       company.companyId AS toCompanyId;
```

Client truyền các tham số như `personId`, `companyId` và `startDate`; không ghép trực tiếp dữ liệu đầu vào vào câu lệnh Cypher. Trong **Spring Data Neo4j**, khi ánh xạ quan hệ giữa entity, cần khai báo type và hướng phù hợp với dữ liệu lưu; hướng khai báo sai có thể khiến truy vấn ánh xạ không trả về quan hệ mong muốn.

### 11.3. Index và constraint có vai trò gì?

Thường nên tạo constraint duy nhất cho mã nút đầu–cuối như `Person.personId` và `Company.companyId`, sau đó dùng mã đó để tìm nút trước khi thêm cạnh. Các index phù hợp giúp truy vấn tìm nút theo property hiệu quả hơn. Với trường hợp thường xuyên tìm theo thuộc tính của relationship như `WORKS_AT.since`, có thể xem xét các loại index trên relationship mà phiên bản Neo4j đang dùng hỗ trợ. Không nên tạo index theo cảm tính; cần xem kế hoạch truy vấn thực tế.

## 12. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `(a)-[:FOLLOWS]->(b)` đồng nghĩa với `(b)-[:FOLLOWS]->(a)` | Suy luận sai ai theo dõi ai | Chọn đúng hướng và truy vấn với mũi tên phù hợp |
| Nghĩ `(a)-[r]-(b)` tạo quan hệ vô hướng | Hiểu sai dữ liệu được lưu | Ghi nhớ đây chỉ là mẫu **truy vấn không ràng buộc chiều** |
| Dùng type `RELATED_TO` cho mọi liên kết | Mất ngữ nghĩa và khó lọc truy vấn | Đặt type diễn đạt hành động/quan hệ cụ thể |
| Giả định một relationship có nhiều type | Thiết kế sai cấu trúc property graph | Dùng một type trên mỗi cạnh; tạo cạnh khác khi thực sự có liên kết khác |
| Lặp `CREATE` khi chỉ cần một liên kết | Sinh nhiều cạnh trùng | Dùng `MATCH` rồi `MERGE` phù hợp, kết hợp kiểm soát ghi đồng thời |
| Đặt thuộc tính của liên kết trên một nút | Mất bối cảnh khi nút liên kết với nhiều thực thể | Chuyển property sang relationship hoặc mô hình nút trung gian |
| Đổi tên type bằng `SET r:NEW_TYPE` | Sai cú pháp/mô hình cập nhật | Tạo relationship type mới và xóa loại cũ qua quy trình chuyển đổi dữ liệu |
| Xóa nút có quan hệ mà không xem xét tác động | Lỗi xóa hoặc mất liên kết khi `DETACH DELETE` | Xác định các cạnh liên quan và quy tắc nghiệp vụ trước khi xóa |
| Nhầm vị trí trên sơ đồ với hướng cạnh | Đọc ngược start/end | Kiểm tra `startNode(r)`, `endNode(r)` và type |

## 13. Bài tập tự kiểm tra

**Bài 1 – Đọc quan hệ.** Cho `(a:User)-[:SUBSCRIBES_TO]->(channel:Channel)`. Nút nào là start node, nút nào là end node? Nếu cần tìm người đăng ký một kênh xác định, mẫu truy vấn nào phù hợp?

<details>
<summary>Đáp án gợi ý</summary>

`a` là start node, `channel` là end node. Tìm người đăng ký theo chiều đi vào kênh:

```cypher
MATCH (u:User)-[:SUBSCRIBES_TO]->(c:Channel {channelId: $channelId})
RETURN u;
```

</details>

**Bài 2 – Phân biệt hướng.** Với hai nút An và Bình, cơ sở dữ liệu chỉ chứa `(An)-[:FOLLOWS]->(Bình)`. Truy vấn `(Bình)-[:FOLLOWS]->(An)` có khớp không? Mẫu nào khớp cạnh này khi bắt đầu từ Bình?

<details>
<summary>Đáp án gợi ý</summary>

Không khớp theo hướng ngược. Có thể truy vấn `(binh)<-[:FOLLOWS]-(an)` hoặc `(binh)-[:FOLLOWS]-(an)` nếu chỉ cần phát hiện liên kết không phân biệt hướng.

</details>

**Bài 3 – Kiểm tra type và hai đầu mút.** Viết truy vấn trả về `type`, mã nút đầu, mã nút cuối của mọi cạnh `WORKS_AT`.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH ()-[r:WORKS_AT]->()
RETURN type(r) AS relationshipType,
       startNode(r).personId AS fromPersonId,
       endNode(r).companyId AS toCompanyId;
```

Cách đặt tên cột giả định hướng và hai loại nút tuân theo mô hình `Person -[:WORKS_AT]-> Company`.

</details>

**Bài 4 – Thiết kế.** Quan hệ `(:Person)-[:BOOKED]->(:Flight)` cần lưu ngày đặt và hạng vé. Nên đặt các thuộc tính ở đâu? Nếu một người có thể đặt nhiều vé trên cùng chuyến bay trong các giao dịch khác nhau, mô hình nào phù hợp?

<details>
<summary>Đáp án gợi ý</summary>

Thông tin về việc đặt vé có thể nằm trên quan hệ `BOOKED` khi mỗi liên kết đại diện cho một lần đặt đơn giản. Nếu mỗi giao dịch có mã, trạng thái, thanh toán, hành khách và vòng đời riêng, nên cân nhắc nút `Booking`, ví dụ `(person)-[:MADE]->(booking)-[:FOR_FLIGHT]->(flight)`.

</details>

## 14. Tổng kết

- Mọi relationship trong Neo4j đều **có hướng lưu trữ** từ **start node** đến **end node**; hai đầu mút có thể là cùng một nút trong trường hợp self-loop.
- Mỗi relationship có **đúng một type** và có thể có các property mô tả riêng mối liên kết.
- `->` và `<-` giới hạn chiều duyệt; `-[]-` tìm quan hệ theo cả hai chiều nhưng **không thay đổi hướng đã lưu**.
- `type(r)`, `startNode(r)`, `endNode(r)` và `properties(r)` giúp kiểm tra loại, hai đầu mút và thuộc tính.
- Các thao tác `CREATE`, `MATCH`, `MERGE`, `SET`, `REMOVE` và `DELETE` cho phép quản lý quan hệ; cần phân biệt rõ việc tạo cạnh mới với việc tìm hoặc tạo cạnh theo mẫu.
- Tên type và hướng phải diễn đạt nhất quán ngữ nghĩa nghiệp vụ. Đây là tiền đề để mô hình hóa quan hệ, truy vấn đường đi, nhập dữ liệu, tối ưu truy vấn và ánh xạ đồ thị vào ứng dụng Java/Spring Data Neo4j.
