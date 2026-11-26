# SET để cập nhật thuộc tính, bổ sung bản đồ và quản lý nhãn trong Neo4j

> **Chương:** Tạo và cập nhật  
> **Mô-đun:** `DATABASE_ENGINE_GRAPH_NEO4J` — mô hình hóa dữ liệu liên kết theo *property graph*, thao tác nút và quan hệ bằng Cypher.

Trong Neo4j, thông tin của nút (*node*) và quan hệ (*relationship*) thường thay đổi theo thời gian: nhân viên chuyển bộ phận, sản phẩm đổi giá, quan hệ tham gia dự án đổi vai trò, hoặc một nút được gắn thêm nhãn phân loại. Lệnh **`SET`** của Cypher dùng để thực hiện các thay đổi này. `SET` có thể cập nhật từng thuộc tính, đặt nhiều thuộc tính cùng lúc, **bổ sung hoặc thay thế toàn bộ bản đồ thuộc tính**, và **thêm nhãn cho nút**.

Khác biệt giữa `SET n.property = value`, `SET n += map` và `SET n = map` đặc biệt quan trọng khi đồng bộ dữ liệu từ hệ thống bên ngoài: dùng sai toán tử có thể xóa mất thuộc tính, ghi đè khóa nghiệp vụ hoặc tạo trạng thái không mong muốn.

## 1. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Viết truy vấn `MATCH ... SET` để cập nhật thuộc tính nút hoặc quan hệ đã tồn tại.
2. Dùng `SET` với nhiều phép gán, biểu thức, kiểu dữ liệu và giá trị `null`.
3. Phân biệt **thay thế toàn bộ thuộc tính** (`=`) với **bổ sung/cập nhật từng khóa** (`+=`).
4. Thêm nhãn cho nút bằng `SET n:Label` và hiểu mối liên hệ với `REMOVE`.
5. Kết hợp `SET` với `CREATE`, `MERGE`, `ON CREATE SET` và `ON MATCH SET`.
6. Tránh lỗi đồng bộ liên quan đến constraint, khóa định danh, dữ liệu thiếu, danh sách và thao tác ghi hàng loạt.
7. Vận dụng truy vấn `SET` trong ứng dụng Java Driver và truy vấn tùy biến của Spring Data Neo4j.

## 2. SET tác động đến thành phần nào của property graph?

Ví dụ đồ thị:

~~~text
(:Person {personId: 'P01', name: 'An', department: 'Data'})
        |
        | [:WORKS_ON {role: 'Developer', active: true}]
        v
(:Project {projectId: 'PR01', title: 'Atlas'})
~~~

| Thành phần | Cú pháp | Tác động |
|---|---|---|
| Thuộc tính của nút | `SET p.name = 'An Nguyễn'` | Thêm hoặc cập nhật một khóa–giá trị của nút `p` |
| Nhiều thuộc tính nút | `SET p.name = 'An', p.active = true` | Gán nhiều thuộc tính trong một `SET` |
| Thuộc tính quan hệ | `SET r.role = 'Tech Lead'` | Cập nhật thuộc tính quan hệ `r` |
| Bổ sung/cập nhật bằng map | `SET p += {city: 'Hà Nội'}` | Cập nhật các khóa xuất hiện trong map, giữ khóa khác |
| Thay thế thuộc tính bằng map | `SET p = {personId: 'P01'}` | Thay toàn bộ tập thuộc tính bằng map mới |
| Thêm nhãn nút | `SET p:Employee` | Thêm nhãn `Employee` cho nút `p` |

**Phạm vi:** `SET` đổi thuộc tính của nút hoặc quan hệ; thao tác thêm nhãn chỉ áp dụng cho **nút**. `SET` không tạo quan hệ mới, không xóa nút và không trực tiếp đổi kiểu quan hệ hiện có.

Điểm quan trọng khác: `SET` cần một **biến tham chiếu đến thành phần cụ thể**. Biến đó thường được xác định bằng `MATCH`, `MERGE`, `CREATE` hoặc một mệnh đề trước trong cùng truy vấn.

## 3. Cập nhật một hoặc nhiều thuộc tính

### 3.1. Cập nhật một thuộc tính trên nút

Giả sử đã có nút `Person` mang `personId = 'P01'`:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.department = 'Engineering'
RETURN p.personId AS personId,
       p.name AS name,
       p.department AS department;
~~~

Đọc truy vấn từ trên xuống:

1. `MATCH` tìm và gán biến `p` cho nút thỏa nhãn `Person` cùng khóa `personId`.
2. `SET` ghi giá trị `Engineering` vào thuộc tính `department` của nút đã tìm.
3. `RETURN` đọc lại các thuộc tính để kiểm tra.

Nếu `department` đã có, giá trị cũ bị thay thế. Nếu chưa có, thuộc tính được thêm mới. Nếu `MATCH` không tìm được nút nào, `SET` không thực thi cho nút đó và truy vấn không tự tạo một nút mới.

### 3.2. Cập nhật nhiều thuộc tính cùng lúc

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.name = 'Nguyễn An',
    p.department = 'Engineering',
    p.active = true,
    p.updatedAt = datetime()
RETURN p;
~~~

Các phép gán trong cùng `SET` được phân tách bằng dấu phẩy. Ngoài chuỗi và boolean, thuộc tính có thể dùng số, ngày, thời điểm, vị trí không gian và danh sách các giá trị thuộc tính hợp lệ.

Nên dùng tên thuộc tính nhất quán như `personId`, `updatedAt`. Cypher phân biệt chữ hoa/chữ thường: `p.userId` và `p.userid` là hai khóa khác nhau.

### 3.3. Cập nhật thuộc tính trên quan hệ

Giả sử quan hệ `WORKS_ON` đã tồn tại:

~~~cypher
MATCH (p:Person {personId: 'P01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR01'})
SET r.role = 'Tech Lead',
    r.active = true,
    r.updatedAt = datetime()
RETURN p.name AS employee,
       pr.title AS project,
       r.role AS role,
       r.updatedAt AS updatedAt;
~~~

`r` tham chiếu tới **quan hệ**, vì vậy `r.role` là thông tin về sự tham gia dự án, không phải thuộc tính của riêng người hay dự án. Không thể viết `SET r:Manager` để “đổi nhãn” quan hệ; quan hệ có **kiểu**, không có nhãn giống nút.

### 3.4. Cập nhật bằng biểu thức

Giá trị ở vế phải có thể là biểu thức Cypher:

~~~cypher
MATCH (p:Product {sku: 'SKU-001'})
SET p.price = 125000,
    p.stock = coalesce(p.stock, 0) + 10,
    p.lastRestockedOn = date()
RETURN p.sku AS sku, p.price AS price, p.stock AS stock;
~~~

`coalesce(p.stock, 0)` trả `p.stock` nếu khác `null`, nếu không trả `0`. Do đó phép cộng không mất kết quả khi thuộc tính `stock` chưa tồn tại.

**Cẩn thận với thao tác tăng số đếm:** nếu cùng một yêu cầu được gửi lại do retry, `stock = stock + 10` sẽ cộng thêm lần nữa. Khi nghiệp vụ đòi hỏi xử lý mỗi sự kiện một lần, cần có khóa sự kiện và quy tắc chống lặp, không chỉ một câu lệnh `SET`.

## 4. Giá trị null có nghĩa là xóa thuộc tính

Trong Neo4j, thuộc tính không lưu một giá trị `null` theo cách thông thường. Khi gán thuộc tính bằng `null`, thuộc tính đó được **loại bỏ** khỏi nút hoặc quan hệ.

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.nickname = null
RETURN p.nickname AS nickname;
~~~

Nếu trước đó có `nickname` thì sau thao tác thuộc tính này không còn tồn tại; kết quả đọc `p.nickname` sẽ là `null`. `REMOVE p.nickname` là cú pháp khác để loại bỏ thuộc tính có chủ đích.

Điều này đặc biệt quan trọng khi dữ liệu đến từ API: trường bị bỏ qua, trường có giá trị `null` và yêu cầu xóa hẳn trường có thể mang **ba ý nghĩa khác nhau**.

Ví dụ, nếu `$department` bằng `null`:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p.department = $department;
~~~

câu lệnh sẽ xóa `department`. Nếu quy tắc đồng bộ là *bỏ qua null và giữ nguyên giá trị hiện có*, có thể dùng:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p.department = coalesce($department, p.department)
RETURN p.department AS department;
~~~

Nếu cả hai đối số đều `null`, kết quả là `null` và thuộc tính vẫn vắng mặt. Cách dùng `coalesce` phù hợp với chính sách “null nghĩa là không cập nhật”, nhưng **không phù hợp** khi null phải được hiểu là yêu cầu xóa dữ liệu.

## 5. Bản đồ thuộc tính và ba kiểu gán quan trọng

Một *map* trong Cypher là tập các cặp khóa–giá trị:

~~~cypher
{
  name: 'Nguyễn An',
  department: 'Engineering',
  active: true
}
~~~

Đối với thuộc tính của một nút `p`, so sánh ba kiểu cập nhật:

~~~cypher
// Chỉ cập nhật một thuộc tính
SET p.name = 'Nguyễn An'
~~~

~~~cypher
// Bổ sung hoặc cập nhật các khóa được liệt kê
SET p += {name: 'Nguyễn An', active: true}
~~~

~~~cypher
// Thay thế TOÀN BỘ tập thuộc tính bằng map mới
SET p = {name: 'Nguyễn An', active: true}
~~~

Hai phép gán bản đồ phía sau có hiệu ứng **rất khác nhau**.

### 5.1. SET n += map: bổ sung hoặc cập nhật một phần

Giả sử nút ban đầu:

~~~text
(:Person {
  personId: 'P01',
  name: 'An',
  department: 'Data',
  active: false,
  createdAt: 2026-01-01T00:00:00Z
})
~~~

Truy vấn:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p += {
  name: 'Nguyễn An',
  active: true,
  city: 'Đà Nẵng'
}
RETURN properties(p) AS props;
~~~

Kết quả về mặt ý nghĩa:

~~~text
{
  personId: 'P01',         // giữ nguyên
  name: 'Nguyễn An',       // cập nhật
  department: 'Data',      // giữ nguyên
  active: true,            // cập nhật
  createdAt: ...,          // giữ nguyên
  city: 'Đà Nẵng'          // thêm mới
}
~~~

`+=` là phép gán **từng khóa có trong map**:

- Khóa có trong map và trong nút: cập nhật bằng giá trị map.
- Khóa có trong map nhưng chưa có trong nút: thêm thuộc tính.
- Khóa của nút không xuất hiện trong map: giữ nguyên.
- Khóa trong map có giá trị `null`: xóa thuộc tính đó.

Đây thường là lựa chọn phù hợp cho API cập nhật từng phần (*PATCH*), với điều kiện ứng dụng kiểm soát các khóa được phép thay đổi.

### 5.2. SET n = map: thay thế toàn bộ thuộc tính

Vẫn với nút ban đầu như trên:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p = {
  personId: 'P01',
  name: 'Nguyễn An',
  active: true
}
RETURN properties(p) AS props;
~~~

Sau thao tác, nút chỉ còn các thuộc tính `personId`, `name` và `active`. Các thuộc tính `department`, `city` (nếu từng có) và `createdAt` **bị xóa** vì không có trong map thay thế.

| Tiêu chí | `SET n += map` | `SET n = map` |
|---|---|---|
| Thuộc tính có trong map | Thêm hoặc cập nhật | Thêm hoặc cập nhật |
| Thuộc tính cũ vắng mặt trong map | **Giữ nguyên** | **Bị loại bỏ** |
| Thuộc tính nhận `null` trong map | Bị loại bỏ | Không được lưu |
| Khả năng làm mất `createdAt`/khóa nghiệp vụ | Có thể nếu map chứa giá trị ghi đè hoặc null | Rất dễ nếu map thiếu các khóa này |
| Trường hợp phù hợp | Cập nhật một phần, bổ sung trường | Thay toàn bộ trạng thái thuộc tính từ nguồn đáng tin cậy |
| Nhãn của nút | Không đổi | Không đổi |
| Quan hệ nối nút | Không đổi | Không đổi |

**Quy tắc:** chỉ dùng `SET n = map` khi map đầu vào thực sự đại diện cho **toàn bộ tập thuộc tính mong muốn**, và bạn biết các thuộc tính cũ không có trong map cần phải bị loại bỏ.

### 5.3. Tham số map từ ứng dụng

Thay vì viết cố định tên và giá trị thuộc tính trong Cypher, truyền qua tham số:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p += $patch
RETURN p.personId AS personId, properties(p) AS properties;
~~~

Ví dụ:

~~~json
{
  "personId": "P01",
  "patch": {
    "name": "Nguyễn An",
    "active": true,
    "city": "Đà Nẵng"
  }
}
~~~

Ứng dụng cần kiểm tra `$patch` là map hợp lệ và **chỉ chứa các trường cho phép**. Không nên cho client truyền thẳng map không kiểm soát, vì một patch như `{"personId": null}` có thể xóa khóa định danh hoặc gây lỗi constraint. Nên loại các trường như `personId`, `createdAt`, `role` đặc biệt nếu nguồn không được phép cập nhật chúng.

### 5.4. Khi nào dùng SET n = $map?

Nếu một nguồn bên ngoài là hệ thống quản lý **toàn bộ thuộc tính** của một kiểu thực thể, có thể thay thế ảnh chụp trạng thái:

~~~cypher
MATCH (p:Product {sku: $sku})
SET p = $fullSnapshot
RETURN properties(p) AS properties;
~~~

Ví dụ này chỉ an toàn khi `$fullSnapshot` bao gồm `sku` và mọi thuộc tính cần giữ. Nếu `sku` bị thiếu hoặc sai, thuộc tính khóa có thể bị xóa/thay thế hoặc gây lỗi constraint. Cách thiết kế tốt hơn cho phần lớn hệ thống là định nghĩa rõ danh sách trường do nguồn quản lý và cập nhật từng trường hoặc bằng map đã lọc.

### 5.5. Một số chi tiết về map

Có thể tạo map từ thuộc tính của nút hoặc quan hệ khác:

~~~cypher
MATCH (source:Product {sku: 'SKU-001'})
MATCH (target:Product {sku: 'SKU-002'})
SET target += {
  name: source.name,
  price: source.price
}
RETURN target;
~~~

Khi chỉ muốn sao chép một số trường, liệt kê rõ tên thuộc tính như trên. Nếu dùng `SET target += properties(source)`, toàn bộ khóa thuộc tính của `source` có thể ghi đè thuộc tính tương ứng của `target`, **bao gồm khóa nghiệp vụ** nếu cả hai có cùng tên khóa.

Các giá trị trong map phải là **giá trị thuộc tính Neo4j hỗ trợ** khi ghi xuống nút hoặc quan hệ. Không thể lưu nguyên một map lồng nhau hay danh sách các map làm một thuộc tính của nút theo cách thông thường. Ví dụ `address: {city: 'Hà Nội'}` không phải thuộc tính có thể lưu trực tiếp. Hãy dùng `city`, `addressCity` hoặc mô hình địa chỉ thành nút riêng tùy nhu cầu truy vấn.

## 6. SET và quản lý nhãn nút

**Nhãn (label)** mô tả phân loại của nút trong property graph; ví dụ cùng một người có nhãn `Person`, `Employee` hoặc `Manager`. Nhãn khác với **thuộc tính** như `role` hay `department`.

### 6.1. Thêm một nhãn mới

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p:Employee
RETURN labels(p) AS labels;
~~~

Nếu nút ban đầu chỉ có `:Person`, sau câu lệnh có cả `:Person` và `:Employee`. `SET p:Employee` **không xóa** các nhãn hiện có.

Có thể thêm nhiều nhãn trong một mệnh đề:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p:Employee:Manager
RETURN labels(p) AS labels;
~~~

Ở ví dụ này, `:Employee` và `:Manager` là nhãn thêm vào cùng nút. Việc gắn một nhãn đã có không tạo thêm một bản sao nhãn trên nút.

### 6.2. Nhãn và thuộc tính không hoán đổi cho nhau

~~~cypher
SET p:Manager
~~~

khác với:

~~~cypher
SET p.role = 'Manager'
~~~

- `:Manager` là **nhãn** để phân loại, phục vụ mẫu truy vấn và có thể liên quan index/constraint theo nhãn.
- `role = 'Manager'` là **thuộc tính** chứa giá trị, hữu ích khi vai trò là dữ liệu nhiều giá trị hoặc thường xuyên thay đổi.

Tùy nhu cầu, cùng một nút có thể vừa có nhãn `Employee` vừa có thuộc tính `role`. Nhưng nếu mỗi vai trò được mô tả bằng một nhãn riêng, cần quy tắc nhất quán để không làm nhãn và thuộc tính mâu thuẫn.

### 6.3. Đổi phân loại: thêm nhãn mới và REMOVE nhãn cũ

`SET` chỉ **thêm** nhãn. Nếu muốn chuyển người từ `Candidate` sang `Employee`, cần bỏ nhãn cũ bằng `REMOVE`:

~~~cypher
MATCH (p:Person {personId: 'P01'})
REMOVE p:Candidate
SET p:Employee
RETURN labels(p) AS labels;
~~~

Nếu chỉ chạy `SET p:Employee`, nhãn `Candidate` vẫn còn. `REMOVE p:Candidate` không xóa nút `p` hay các quan hệ của nó; chỉ bỏ một nhãn. `REMOVE p.department` cũng có thể loại một thuộc tính, nhưng đó là thao tác khác với loại nhãn.

### 6.4. Nhãn có ảnh hưởng đến constraint và index

Giả sử cơ sở dữ liệu có constraint duy nhất trên `:Employee(employeeId)`. Khi thêm nhãn `Employee` cho một nút có `employeeId` trùng với một nút đã mang nhãn này, thao tác gắn nhãn có thể vi phạm constraint và thất bại.

Nhãn cũng tác động đến cách truy vấn tìm nút:

~~~cypher
MATCH (p:Employee)
RETURN p.employeeId AS employeeId, p.name AS name;
~~~

Nút chỉ mang nhãn `Person` sẽ không được `MATCH (p:Employee)` lựa chọn cho đến khi được gắn thêm nhãn `Employee`.

### 6.5. Nhãn động và đầu vào không tin cậy

Với bài toán chỉ có vài loại cố định, nên dùng truy vấn với nhãn cố định đã được thiết kế:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p:Employee
RETURN p;
~~~

Một số phiên bản Cypher/Neo4j mới hỗ trợ cú pháp nhãn động, nhưng tính khả dụng phụ thuộc phiên bản. Dù sử dụng cú pháp nào, **không nối trực tiếp tên nhãn do người dùng nhập vào chuỗi Cypher** mà không kiểm soát. Khi bắt buộc cho phép phân loại động, hãy xác thực theo danh sách tên nhãn được phép và kiểm tra khả năng hỗ trợ của phiên bản đang chạy.

## 7. Cập nhật danh sách và biểu thức điều kiện

### 7.1. Thay toàn bộ danh sách

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.skills = ['Java', 'Cypher', 'Spring']
RETURN p.skills AS skills;
~~~

`skills` là một thuộc tính dạng danh sách chuỗi. Phép gán này **thay toàn bộ danh sách cũ**.

### 7.2. Thêm phần tử vào danh sách

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.skills = coalesce(p.skills, []) + ['Neo4j']
RETURN p.skills AS skills;
~~~

Nếu danh sách đã có, phần tử mới được nối vào cuối. Nếu chưa có, kết quả là danh sách chứa `Neo4j`. Lệnh này **có thể tạo phần tử trùng** khi chạy lại.

Muốn chỉ thêm khi phần tử chưa xuất hiện:

~~~cypher
MATCH (p:Person {personId: 'P01'})
WITH p, coalesce(p.skills, []) AS currentSkills
SET p.skills = CASE
  WHEN 'Neo4j' IN currentSkills THEN currentSkills
  ELSE currentSkills + ['Neo4j']
END
RETURN p.skills AS skills;
~~~

Ở đây `CASE` tạo nhánh điều kiện trong biểu thức gán. Tránh sử dụng thuộc tính danh sách dài như một tập quan hệ cần truy vấn phức tạp; nếu kỹ năng là thực thể được chia sẻ bởi nhiều người, có thể mô hình hóa `(:Person)-[:HAS_SKILL]->(:Skill)`.

### 7.3. Cập nhật có điều kiện

~~~cypher
MATCH (p:Product {sku: 'SKU-001'})
SET p.status = CASE
  WHEN coalesce(p.stock, 0) > 0 THEN 'available'
  ELSE 'out_of_stock'
END
RETURN p.status AS status;
~~~

Với yêu cầu kiểm soát thông tin từ nhiều nguồn hoặc chính sách chuyển trạng thái phức tạp, điều kiện cần được xây dựng theo quy tắc nghiệp vụ cụ thể.

## 8. Kết hợp SET với CREATE và MERGE

### 8.1. SET ngay sau CREATE

~~~cypher
CREATE (pr:Project {projectId: 'PR-SET-001'})
SET pr.title = 'Nền tảng đồ thị',
    pr.active = true,
    pr.createdAt = datetime()
RETURN pr;
~~~

`CREATE` tạo nút mới, `SET` bổ sung các thuộc tính của nút đó. Nếu chắc chắn tất cả thuộc tính đã biết từ trước, cũng có thể khai báo chúng trực tiếp bên trong mẫu `CREATE`.

### 8.2. MERGE theo khóa, SET thuộc tính thay đổi

`MERGE` giúp tìm hoặc tạo thực thể theo khóa ổn định:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.createdAt = datetime()
SET p.name = $name,
    p.department = $department,
    p.lastSyncedAt = datetime()
RETURN p;
~~~

Nếu nút chưa tồn tại, `MERGE` tạo nó và `ON CREATE SET` đặt `createdAt`. Nếu nút đã có, vẫn dùng nút đó. `SET` ở cuối cập nhật các trường nghiệp vụ **ở cả hai trường hợp**.

Khi cần chạy nhánh riêng cho bản ghi cũ:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.createdAt = datetime()
ON MATCH SET p.lastMatchedAt = datetime()
SET p.name = $name
RETURN p;
~~~

`ON MATCH SET` chỉ chạy khi mẫu của `MERGE` **đã khớp**. Nó không tự kiểm tra dữ liệu nguồn mới hơn hay cũ hơn; nếu cần đồng bộ có phiên bản, hãy thêm quy tắc so sánh thời điểm hoặc version.

### 8.3. MERGE từng nút, SET trên quan hệ

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.name = $personName

MERGE (pr:Project {projectId: $projectId})
ON CREATE SET pr.title = $projectTitle

MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.joinedOn = date()
SET r.role = $role,
    r.lastSyncedAt = datetime()

RETURN p.personId AS personId,
       pr.projectId AS projectId,
       r.role AS role;
~~~

Mỗi `MERGE` ràng buộc một thành phần theo đúng mẫu của nó. Vì `p` và `pr` được tìm/tạo trước, `MERGE` quan hệ ở cuối chỉ tìm/tạo quan hệ **giữa hai đầu mút đã xác định**. `SET r.role` có thể cập nhật vai trò của quan hệ mà không tạo thêm quan hệ mới chỉ vì `role` đổi.

**Lưu ý:** cần constraint phù hợp để bảo vệ khóa nút khi hệ thống ghi đồng thời; `MERGE` một mình không là lời hứa rằng dữ liệu mọi trường hợp đều duy nhất.

## 9. Constraint, khóa nghiệp vụ và rủi ro ghi đè

### 9.1. Ràng buộc khóa định danh

Một khóa nghiệp vụ nên được bảo vệ bằng constraint khi mô hình yêu cầu duy nhất:

~~~cypher
CREATE CONSTRAINT person_personId_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

Nếu tồn tại hai nút `:Person` cùng `personId` không phải `null`, việc tạo constraint có thể thất bại. Nếu constraint đã có, cố thay `personId` của một nút thành giá trị đã thuộc về nút khác cũng có thể thất bại.

Constraint giúp phát hiện vi phạm toàn vẹn, nhưng không thay thế kiểm tra tính đúng đắn của map đầu vào hoặc quyền sở hữu trường.

### 9.2. Đừng cho patch ghi đè khóa và metadata

Truy vấn:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p += $patch;
~~~

rất tiện, nhưng sẽ nguy hiểm nếu `$patch` chứa `personId`, `createdAt`, `verified` hoặc một trường do bộ phận khác quản lý. Ứng dụng nên **lọc danh sách trường được phép cập nhật** trước khi gửi tham số.

Ví dụ chính sách đơn giản:

| Trường | Quy tắc đồng bộ |
|---|---|
| `personId` | Chỉ dùng nhận diện; không cho bản vá tự sửa |
| `name` | Cho phép cập nhật |
| `department` | Cho phép cập nhật khi nguồn HR là nguồn có thẩm quyền |
| `active` | Cho phép cập nhật theo nguồn chính thức |
| `createdAt` | Giữ nguyên sau lần tạo |
| `lastSyncedAt` | Do ứng dụng ghi dữ liệu quản lý |
| `securityRole` | Chỉ dịch vụ phân quyền được sửa |

Phân quyền trường thuộc lớp thiết kế ứng dụng và quy tắc vận hành, không tự phát sinh từ `SET` hay `MERGE`.

### 9.3. Nhiều nút cùng khớp MATCH

~~~cypher
MATCH (p:Person {name: 'An'})
SET p.active = true
RETURN count(p) AS updatedNodes;
~~~

Nếu có ba người tên An, truy vấn sẽ cập nhật cả ba. Neo4j không tự hiểu tên nào là người cần sửa. Hãy dùng khóa nghiệp vụ ổn định, chỉ số/constraint phù hợp và kiểm tra số dòng được khớp.

### 9.4. Ghi đồng thời và giao dịch

`SET` thực thi trong giao dịch ghi của Neo4j. Nếu nhiều thao tác cùng thay đổi một nút hoặc quan hệ, hệ thống cần quản lý giao dịch và chính sách xung đột phù hợp. Ví dụ, hai ứng dụng cùng ghi `department` với giá trị khác nhau có thể dẫn đến dữ liệu cuối cùng tùy thứ tự ghi; khóa duy nhất không tự quyết định nguồn nào có quyền ưu tiên.

Khi tích hợp nhiều nguồn, nên có quy tắc phiên bản, thời điểm nguồn cập nhật, xử lý retry hoặc kiểm tra xung đột. Các phép gán cộng dồn như `stock = stock + 1` cần thiết kế chống gửi lại sự kiện ngoài ý muốn.

## 10. Cập nhật hàng loạt bằng UNWIND

Giả sử ứng dụng nhận danh sách bản vá:

~~~json
{
  "people": [
    {
      "personId": "P01",
      "patch": {
        "name": "Nguyễn An",
        "active": true
      }
    },
    {
      "personId": "P02",
      "patch": {
        "department": "Data",
        "city": "Hà Nội"
      }
    }
  ]
}
~~~

Truy vấn cập nhật nút **đã tồn tại**:

~~~cypher
UNWIND $people AS row
MATCH (p:Person {personId: row.personId})
SET p += row.patch,
    p.lastSyncedAt = datetime()
RETURN count(*) AS processedRows;
~~~

`UNWIND` tạo một dòng cho mỗi phần tử, `MATCH` tìm nút theo khóa, `SET +=` cập nhật các trường được cung cấp. Nếu một `personId` không tồn tại, dòng đó **không cập nhật gì** và sẽ không được tính trong `count(*)` ở cuối.

Nếu yêu cầu **tự tạo nút khi chưa có**, thay `MATCH` bằng `MERGE`:

~~~cypher
UNWIND $people AS row
MERGE (p:Person {personId: row.personId})
ON CREATE SET p.createdAt = datetime()
SET p += row.patch,
    p.lastSyncedAt = datetime()
RETURN count(*) AS processedRows;
~~~

**Điều kiện an toàn:** map `row.patch` không được làm thay đổi `personId` hoặc `createdAt`. Dữ liệu đầu vào cần được xác thực, lọc trường và khử trùng khóa trước khi chạy. Nếu một khóa xuất hiện nhiều lần trong lô với các bản vá mâu thuẫn, kết quả có thể phụ thuộc thứ tự xử lý; `UNWIND` không bảo đảm thứ tự dòng nếu không có quy tắc sắp xếp tường minh.

### 10.1. Đọc kết quả và số lượng bản ghi

`count(*)` trong hai truy vấn trên là **số dòng được xử lý đến mệnh đề `RETURN`**, không nhất thiết là số nút mới tạo hay số khóa thuộc tính thay đổi. Một `MATCH` có thể trả nhiều nút khi thiếu constraint; vì vậy số đếm cũng có thể vượt số phần tử trong danh sách đầu vào.

### 10.2. Hiệu năng khi cập nhật nhiều dữ liệu

- Tạo index/constraint phù hợp với khóa tìm kiếm như `:Person(personId)` để tránh quét toàn bộ nút không cần thiết.
- Chia danh sách thành các lô hợp lý, tránh giao dịch quá lớn.
- Chỉ gửi và cập nhật các trường cần thay đổi, nhất là khi nút có nhiều thuộc tính.
- Xác thực các kiểu thuộc tính trước khi ghi; không dùng map lồng nhau như thuộc tính của nút.
- Dùng `EXPLAIN` để xem kế hoạch mà không thực thi ghi. `PROFILE` thực sự thực thi câu truy vấn, nên dùng với truy vấn ghi trên dữ liệu thử nghiệm có kiểm soát.

## 11. Sử dụng SET trong Neo4j Java Driver

Trong Java, truyền map thông qua tham số giúp tránh nối dữ liệu người dùng vào chuỗi Cypher. Ví dụ sau thực hiện cập nhật có chọn lọc đối với hồ sơ người đã tồn tại:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class PersonService {
    private final Driver driver;

    public PersonService(Driver driver) {
        this.driver = driver;
    }

    public boolean updateDepartment(String personId, String department) {
        String cypher = """
            MATCH (p:Person {personId: $personId})
            SET p.department = $department,
                p.updatedAt = datetime()
            RETURN p.personId AS id
            """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                tx.run(cypher, Map.of(
                    "personId", personId,
                    "department", department
                )).hasNext()
            );
        }
    }
}
~~~

Ở ví dụ này:

- `MATCH` chỉ cập nhật nút đã tồn tại. Nếu không tìm thấy `personId`, truy vấn không cập nhật và phương thức trả `false`.
- `Map.of(...)` yêu cầu các giá trị không phải `null`. Nếu giao thức cho phép xóa thuộc tính bằng `null`, ứng dụng cần tạo map tham số tương thích và kiểm soát ý nghĩa dữ liệu.
- `executeWrite` thực thi callback trong giao dịch ghi do Driver quản lý; callback có thể được thử lại với một số lỗi tạm thời. Vì thế không nên đặt tác dụng phụ bên ngoài cơ sở dữ liệu vào callback mà không có cơ chế chống lặp.
- `Driver` nên được quản lý theo vòng đời ứng dụng; mỗi thao tác dùng `Session` phù hợp.
- Để bảo vệ định danh khi dữ liệu được nhiều tiến trình cập nhật, cần constraint và logic xử lý xung đột theo nghiệp vụ.

Nếu muốn thực hiện bản vá bằng map, thay phần `SET` thành `SET p += $patch` và gửi thêm tham số `patch` đã lọc bằng danh sách trường cho phép.

Trong **Spring Data Neo4j**, repository và entity mapping có thể giúp ánh xạ thực thể. Khi dùng truy vấn Cypher tùy biến, ví dụ qua `@Query`, ngữ nghĩa `SET`, `+=`, `=` và thao tác thêm nhãn vẫn giống Cypher thông thường. Khi dùng cơ chế lưu entity, cần hiểu cách thư viện quản lý trạng thái thuộc tính và quan hệ để tránh mất thông tin do dữ liệu Java chỉ chứa một phần các trường.

## 12. Thực hành theo kịch bản sản phẩm

Giả sử cơ sở dữ liệu đồ thị quản lý khóa học:

~~~text
(:Course {
  courseId: 'C001',
  title: 'Cypher căn bản',
  durationHours: 12,
  published: false,
  createdAt: <thời điểm tạo>
})
~~~

Để chuẩn bị dữ liệu thử, trên đồ thị chưa có mã `C001`:

~~~cypher
CREATE (c:Course {
  courseId: 'C001',
  title: 'Cypher căn bản',
  durationHours: 12,
  published: false,
  createdAt: datetime()
})
RETURN c;
~~~

Nếu hệ thống đã có mã này, không nên chạy lại `CREATE` vì sẽ tạo bản sao hoặc gây lỗi constraint.

### Bài tập 1 — Cập nhật riêng một thuộc tính

**Yêu cầu:** xuất bản khóa học `C001` bằng cách đặt `published = true` và `publishedAt` là ngày hiện tại. Không đụng tới `createdAt`.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (c:Course {courseId: 'C001'})
SET c.published = true,
    c.publishedAt = date()
RETURN c.courseId AS courseId,
       c.published AS published,
       c.publishedAt AS publishedAt;
~~~

Câu lệnh chỉ ghi các thuộc tính được chỉ định. `createdAt` được giữ nguyên.

</details>

### Bài tập 2 — Phân biệt hai toán tử map

**Ban đầu** nút C001 có: `courseId='C001'`, `title='Cypher căn bản'`, `durationHours=12` và `createdAt`.

So sánh hai truy vấn chạy trên **hai bản sao trạng thái ban đầu độc lập**:

~~~cypher
MATCH (c:Course {courseId: 'C001'})
SET c += {title: 'Cypher thực hành', published: true};
~~~

~~~cypher
MATCH (c:Course {courseId: 'C001'})
SET c = {courseId: 'C001', title: 'Cypher thực hành', published: true};
~~~

**Câu hỏi:** thao tác nào giữ `durationHours` và `createdAt`?

<details>
<summary>Đáp án</summary>

`SET c += {...}` giữ các thuộc tính không xuất hiện trong map, trong đó có `durationHours` và `createdAt`. `SET c = {...}` thay toàn bộ tập thuộc tính; vì map mới không chứa hai khóa đó, chúng bị loại khỏi nút. Nhãn `:Course` của nút không đổi trong cả hai trường hợp.

</details>

### Bài tập 3 — Thêm nhãn, xóa nhãn cũ

**Yêu cầu:** gắn nhãn `PublishedCourse` cho C001 và bỏ nhãn `DraftCourse` nếu có, không xóa nút hay các thuộc tính.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (c:Course {courseId: 'C001'})
REMOVE c:DraftCourse
SET c:PublishedCourse
RETURN labels(c) AS labels;
~~~

`REMOVE` ở đây bỏ nhãn `DraftCourse`, còn `SET` thêm `PublishedCourse`. Nhãn `Course` vẫn giữ nguyên.

</details>

### Bài tập 4 — Cập nhật quan hệ học viên tham gia khóa học

Giả sử đã có nút `Student {studentId: 'S001'}`, nút `Course {courseId: 'C001'}` và quan hệ `ENROLLED_IN` giữa chúng. Hãy cập nhật `status = 'completed'` và `completedOn` là ngày hiện tại.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (s:Student {studentId: 'S001'})
      -[r:ENROLLED_IN]->
      (c:Course {courseId: 'C001'})
SET r.status = 'completed',
    r.completedOn = date()
RETURN s.studentId AS studentId,
       c.courseId AS courseId,
       r.status AS status,
       r.completedOn AS completedOn;
~~~

`SET` cập nhật quan hệ đã tồn tại; nếu không tìm được quan hệ, truy vấn không tự tạo mới.

</details>

### Bài tập 5 — Tìm lỗi khi nhận patch từ API

Cho truy vấn:

~~~cypher
MERGE (c:Course {courseId: $courseId})
SET c = $patch;
~~~

Trong đó `$patch` chỉ có `title` và `published`. Vì sao sau khi đồng bộ, `courseId` có thể biến mất hoặc truy vấn có thể vi phạm constraint?

<details>
<summary>Đáp án tham khảo</summary>

`SET c = $patch` thay toàn bộ tập thuộc tính bằng map mới; map không chứa `courseId` thì thuộc tính khóa bị xóa (hoặc giao dịch báo lỗi nếu ràng buộc hiện diện không cho phép). Nếu muốn cập nhật một phần, dùng `SET c += $patch` sau khi lọc các trường hợp lệ, hoặc `SET c.title = $title, c.published = $published`.

</details>

## 13. Những lỗi hay gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `SET` không thay đổi gì | `MATCH` không tìm thấy nút/quan hệ | Kiểm tra nhãn, kiểu quan hệ và giá trị khóa; dùng `MERGE` khi cần tự tạo |
| Cập nhật một người nhưng nhiều người bị đổi | `MATCH` theo tên hoặc thuộc tính không duy nhất | Dùng khóa nghiệp vụ và constraint phù hợp |
| Các thuộc tính cũ tự biến mất | Dùng `SET n = map` với map thiếu trường | Dùng `+=` cho bản vá từng phần hoặc truyền snapshot đầy đủ |
| Khóa nghiệp vụ bị thay đổi hoặc mất | Map patch chứa khóa định danh hoặc null | Lọc trường, cấm ghi khóa và kiểm tra constraint |
| Một thuộc tính bị xóa khi gửi từ API | Tham số nhận `null` | Xác định rõ nghĩa của null, dùng chính sách bỏ qua/xóa tương ứng |
| Nhãn cũ vẫn còn sau khi thêm nhãn mới | `SET n:Label` chỉ thêm nhãn | Dùng `REMOVE n:OldLabel` khi cần |
| Không thể “SET nhãn” cho quan hệ | Quan hệ không dùng nhãn như nút | Sử dụng kiểu quan hệ và thuộc tính; thiết kế lại khi cần đổi loại kết nối |
| Cập nhật danh sách nhiều lần bị trùng phần tử | Nối phần tử bằng `+` mỗi lần chạy | Kiểm tra phần tử trước khi thêm hoặc mô hình hóa thành quan hệ |
| Thêm nhãn báo lỗi constraint | Nhãn mới áp dụng constraint cho khóa đang trùng | Kiểm tra dữ liệu và định danh trước khi thêm nhãn |
| Bản tin cũ ghi đè giá trị mới | Không có so sánh version hoặc thời gian nguồn | Bổ sung chính sách ưu tiên và kiểm soát giao dịch |

## 14. Tổng kết

Cần phân biệt các thao tác quan trọng sau:

| Mục đích | Mẫu Cypher |
|---|---|
| Cập nhật một thuộc tính | `MATCH (n:Label {id: $id}) SET n.name = $name` |
| Cập nhật nhiều thuộc tính | `SET n.name = $name, n.active = $active` |
| Bổ sung/cập nhật bằng map | `SET n += $patch` |
| Thay thế toàn bộ thuộc tính | `SET n = $fullSnapshot` |
| Xóa một thuộc tính | `SET n.property = null` hoặc `REMOVE n.property` |
| Thêm một hay nhiều nhãn nút | `SET n:Employee` hoặc `SET n:Employee:Manager` |
| Bỏ nhãn nút cũ | `REMOVE n:OldLabel` |
| Ghi trường ở cả lần tạo và lần khớp | `MERGE ... SET n.field = $value` |
| Chỉ ghi trường khi tạo mới | `MERGE ... ON CREATE SET n.createdAt = datetime()` |
| Cập nhật thuộc tính quan hệ | `MATCH (a)-[r:TYPE]->(b) SET r.role = $role` |

**Điểm cốt lõi:** `SET` là công cụ cập nhật thuộc tính và thêm nhãn; lựa chọn `=` hay `+=` quyết định việc **thay toàn bộ** hay **cập nhật từng phần**. Kết hợp `SET` với `MATCH`/`MERGE` theo khóa nghiệp vụ, constraint, tham số, giao dịch và quy tắc sở hữu dữ liệu sẽ giúp hệ thống Neo4j đồng bộ chính xác, dễ kiểm tra và vận hành ổn định.

Sau chủ đề này, nên tiếp tục tìm hiểu `REMOVE` để loại bỏ thuộc tính/nhãn, `DELETE`/`DETACH DELETE` để xóa thành phần đồ thị, đồng thời sử dụng index và `EXPLAIN` để tối ưu truy vấn ghi có điều kiện.
