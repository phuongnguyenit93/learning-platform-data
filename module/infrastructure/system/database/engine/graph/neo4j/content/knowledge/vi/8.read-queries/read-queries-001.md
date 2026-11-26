# MATCH để tìm nút theo nhãn và thuộc tính

Trong mô hình **property graph** của Neo4j, dữ liệu được lưu dưới dạng nút (node), quan hệ (relationship) và thuộc tính (property). Nút có thể mang một hoặc nhiều nhãn (label), chẳng hạn `:Person` hoặc `:Employee`; thuộc tính lưu các giá trị như `name`, `age`, `city`. Ngôn ngữ Cypher dùng mệnh đề **`MATCH`** để tìm các mẫu đồ thị phù hợp, sau đó dùng `WHERE` để lọc và `RETURN` để lấy kết quả.

Bài thuộc chương **Truy vấn đọc**, tập trung vào cách dùng `MATCH` để tìm **nút theo nhãn và thuộc tính**. Đây là nền tảng trước khi truy vấn quan hệ, đường đi, tối ưu bằng index, hoặc gọi Neo4j từ Java Driver và Spring Data Neo4j.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Viết `MATCH (n:Label)` để tìm các nút mang một nhãn và phân biệt nhãn với thuộc tính.
2. Tìm nút theo một hoặc nhiều thuộc tính bằng mẫu `{key: value}` và mệnh đề `WHERE`.
3. Kết hợp điều kiện số, chuỗi, boolean, danh sách và kiểm tra thuộc tính thiếu.
4. Dùng tham số `$parameter`, sắp xếp, giới hạn kết quả và đọc số lượng nút.
5. Đọc kế hoạch truy vấn với `EXPLAIN`/`PROFILE` và xác định khi nào index có ích.

## 2. Cấu trúc cơ bản của MATCH

```cypher
MATCH (p:Person)
WHERE p.age >= 18
RETURN p.name AS name, p.age AS age;
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `MATCH` | Tìm những mẫu đồ thị thỏa điều kiện mô tả. |
| `(p:Person)` | Tìm nút có nhãn `Person`, gán biến `p` cho mỗi nút khớp. |
| `p.age` | Truy cập thuộc tính `age` của nút `p`. |
| `WHERE p.age >= 18` | Chỉ giữ các nút có `age` từ 18 trở lên. |
| `RETURN ... AS ...` | Chọn các giá trị trả về và đặt bí danh cho cột. |

Một nút có thể mang **nhiều nhãn**; nhãn dùng để phân loại nút, còn thuộc tính diễn tả dữ liệu của nút. Việc đặt tên biến `p` chỉ có hiệu lực trong phạm vi câu truy vấn và không tạo hay sửa dữ liệu.

> **Lưu ý:** Cypher phân biệt chữ hoa/chữ thường trong tên nhãn, tên thuộc tính và so sánh chuỗi thông thường. `:Person` khác `:person`; `p.name` khác `p.Name`. Giá trị thuộc tính còn phải khớp kiểu dữ liệu, ví dụ số `25` khác chuỗi `'25'`.

## 3. Dữ liệu thực hành

Thực hiện phần tạo dữ liệu sau trong **cơ sở dữ liệu thực hành** của Neo4j. `MERGE` theo `id` giúp tránh tạo lặp cùng một nút trong bộ dữ liệu mẫu khi chạy lại, với giả định dữ liệu ban đầu không có các `id` trùng nhau.

```cypher
UNWIND [
  {id: 'p01', name: 'An',   age: 25, city: 'Hà Nội',           active: true},
  {id: 'p02', name: 'Bình', age: 31, city: 'Đà Nẵng',          active: true},
  {id: 'p03', name: 'Chi',  age: 28, city: 'Hà Nội',           active: false},
  {id: 'p04', name: 'Dũng', age: 35, city: 'TP. Hồ Chí Minh', active: true},
  {id: 'p05', name: 'An',   age: 30, city: 'Hà Nội',           active: true}
] AS row
MERGE (p:Person {id: row.id})
SET p.name = row.name,
    p.age = row.age,
    p.city = row.city,
    p.active = row.active;
```

Để minh họa một nút có thể mang nhiều nhãn, thêm nhãn `Employee` cho hai nút:

```cypher
MATCH (p:Person)
WHERE p.id IN ['p01', 'p03']
SET p:Employee;
```

Từ đây, bộ dữ liệu mẫu có năm nút `Person`. Hai nút `p01` và `p03` đồng thời mang nhãn `Employee`.

## 4. Tìm nút theo nhãn

### 4.1. Một nhãn

```cypher
MATCH (p:Person)
RETURN p.id AS id, p.name AS name, p.city AS city
ORDER BY id;
```

Với dữ liệu mẫu, truy vấn trả về năm dòng từ `p01` đến `p05`. `MATCH` chỉ xác định tập nút phù hợp; `RETURN` quyết định cột nào được hiển thị.

### 4.2. Nhiều nhãn trên cùng một nút

```cypher
MATCH (p:Person:Employee)
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

Kết quả là `p01` (An) và `p03` (Chi). Cú pháp `:Person:Employee` yêu cầu nút có **cả hai nhãn**, không phải một trong hai. Muốn tìm những nút chỉ cần có nhãn `Employee` thì dùng `MATCH (p:Employee)`.

### 4.3. Không chỉ rõ nhãn

```cypher
MATCH (n)
RETURN count(n) AS totalNodes;
```

`MATCH (n)` xét nút thuộc **mọi nhãn** của cơ sở dữ liệu. Vì vậy, `totalNodes` chỉ bằng 5 nếu cơ sở dữ liệu chỉ chứa năm nút của ví dụ này. Trong bài toán thực tế, nên chỉ rõ nhãn khi đã biết loại dữ liệu cần tìm để câu truy vấn rõ nghĩa và giúp bộ tối ưu có thêm thông tin.

## 5. Tìm nút theo thuộc tính chính xác

Có thể khai báo một bản đồ thuộc tính ngay bên trong mẫu nút:

```cypher
MATCH (p:Person {name: 'An'})
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

**Kết quả dự kiến:** `p01` và `p05`, vì hai nút đều có `name = 'An'`. Tên không nhất thiết là khóa duy nhất; muốn tìm đúng một người, hãy ưu tiên một định danh như `id` có ràng buộc duy nhất.

Khi có nhiều thuộc tính trong mẫu, **tất cả** phải khớp:

```cypher
MATCH (p:Person {name: 'An', city: 'Hà Nội'})
RETURN p.id AS id, p.age AS age
ORDER BY id;
```

Câu trên tương đương về điều kiện lọc với:

```cypher
MATCH (p:Person)
WHERE p.name = 'An' AND p.city = 'Hà Nội'
RETURN p.id AS id, p.age AS age
ORDER BY id;
```

Trong cả hai trường hợp, kết quả là `p01` (25 tuổi) và `p05` (30 tuổi). Mẫu `{key: value}` thuận tiện cho **so sánh bằng**; dùng `WHERE` khi cần toán tử khác hoặc biểu thức phức tạp.

## 6. Lọc nâng cao bằng WHERE

### 6.1. Toán tử thường dùng

| Nhóm | Ví dụ | Công dụng |
| --- | --- | --- |
| So sánh | `p.age = 30`, `p.age <> 30` | Bằng, khác. |
| Khoảng giá trị | `p.age >= 25 AND p.age < 35` | So sánh số hoặc các giá trị có thứ tự thích hợp. |
| Logic | `AND`, `OR`, `NOT` | Kết hợp hoặc phủ định điều kiện. |
| Danh sách | `p.city IN ['Hà Nội', 'Đà Nẵng']` | Khớp một trong các giá trị. |
| Tiền tố chuỗi | `p.name STARTS WITH 'A'` | Chuỗi bắt đầu bằng tiền tố. |
| Hậu tố chuỗi | `p.name ENDS WITH 'ng'` | Chuỗi kết thúc bằng hậu tố. |
| Chuỗi con | `p.name CONTAINS 'nh'` | Chuỗi có chứa đoạn ký tự. |
| Kiểm tra null | `p.email IS NULL` | Thuộc tính không có giá trị (gồm cả thuộc tính chưa tồn tại). |

Ví dụ tìm người từ 28 tuổi, sống ở Hà Nội và đang hoạt động:

```cypher
MATCH (p:Person)
WHERE p.city = 'Hà Nội'
  AND p.age >= 28
  AND p.active = true
RETURN p.id AS id, p.name AS name, p.age AS age;
```

**Kết quả:** `p05` (An, 30 tuổi). `p03` cũng thỏa thành phố và tuổi nhưng bị loại vì `active = false`.

Điều kiện `OR` và `IN`:

```cypher
MATCH (p:Person)
WHERE p.city IN ['Hà Nội', 'Đà Nẵng']
  AND p.age >= 30
RETURN p.id AS id, p.name AS name, p.city AS city
ORDER BY id;
```

**Kết quả:** `p02` (Bình, Đà Nẵng) và `p05` (An, Hà Nội). Với điều kiện dài, dùng dấu ngoặc để làm rõ ý định:

```cypher
MATCH (p:Person)
WHERE (p.city = 'Hà Nội' OR p.city = 'Đà Nẵng')
  AND p.active = true
RETURN p.id AS id
ORDER BY id;
```

Kết quả ở đây là `p01`, `p02`, `p05`.

### 6.2. Lọc chuỗi

```cypher
MATCH (p:Person)
WHERE p.name STARTS WITH 'A'
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

Kết quả là `p01` và `p05`. So sánh chuỗi thông thường có phân biệt hoa/thường: `STARTS WITH 'a'` không đồng nghĩa `STARTS WITH 'A'`.

Khi nghiệp vụ cần tìm không phân biệt hoa/thường, có thể chuẩn hóa cả hai vế:

```cypher
MATCH (p:Person)
WHERE toLower(p.name) = toLower($name)
RETURN p.id AS id, p.name AS name;
```

Tuy nhiên, gọi hàm trên thuộc tính có thể hạn chế khả năng dùng **range index** thông thường. Với hệ thống lớn, cân nhắc lưu thêm thuộc tính đã chuẩn hóa (ví dụ `nameNormalized`) và lập index cho thuộc tính đó. Phép chuẩn hóa hoa/thường cũng chưa giải quyết mọi khác biệt về dấu tiếng Việt hoặc quy tắc tìm kiếm ngôn ngữ tự nhiên.

### 6.3. Thuộc tính không tồn tại và null

Trong Neo4j, một nút có thể không chứa thuộc tính `email`. Đọc `p.email` ở nút đó cho giá trị `null`; Neo4j không lưu một thuộc tính có giá trị `null` như một giá trị property độc lập.

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p.id AS id
ORDER BY id;
```

Vì dữ liệu mẫu không khai báo `email`, truy vấn trả về cả năm nút `Person`. Để tìm nút **có** giá trị `email`, dùng `p.email IS NOT NULL`.

Không viết `p.email = null` hoặc `p.email <> null` để kiểm tra null. Trong logic ba giá trị của Cypher, các phép so sánh đó không trả về `true`, nên `WHERE` không giữ dòng tương ứng. Tương tự, `WHERE NOT p.active` chỉ chọn `false`; nút thiếu `active` không được tự động coi là `false`.

## 7. Dùng tham số thay vì ghép chuỗi truy vấn

Trong ứng dụng, giá trị lọc thường đến từ người dùng hoặc API. Sử dụng tham số giúp tách câu Cypher khỏi dữ liệu đầu vào, thuận tiện tái sử dụng truy vấn và tránh ghép chuỗi giá trị không an toàn.

```cypher
MATCH (p:Person)
WHERE p.city = $city AND p.age >= $minAge
RETURN p.id AS id, p.name AS name, p.age AS age
ORDER BY age DESC, id ASC;
```

Ví dụ nếu truyền `city = 'Hà Nội'` và `minAge = 28` thì kết quả theo thứ tự là `p05` (30 tuổi), `p03` (28 tuổi).

Trong Neo4j Java Driver, có thể truyền giá trị bằng map tham số. Ví dụ dưới đây giả định biến `driver` đã được cấu hình kết nối và sử dụng API Driver phiên bản hỗ trợ `executeRead`:

```java
try (var session = driver.session()) {
    var names = session.executeRead(tx ->
        tx.run("""
            MATCH (p:Person)
            WHERE p.city = $city AND p.age >= $minAge
            RETURN p.name AS name
            ORDER BY name
            """, java.util.Map.of("city", "Hà Nội", "minAge", 28))
          .list(record -> record.get("name").asString())
    );
    System.out.println(names); // [An, Chi]
}
```

`$city` và `$minAge` là **tham số giá trị**. Nhãn và tên thuộc tính thuộc cấu trúc truy vấn, cần được kiểm soát riêng khi xây dựng truy vấn động; khả năng tham số hóa chúng phụ thuộc vào cú pháp và phiên bản Cypher đang dùng. Trong Spring Data Neo4j, nguyên tắc tương tự áp dụng khi viết truy vấn `@Query` có binding tham số.

## 8. Chọn và sắp xếp kết quả

`RETURN` có thể trả về cả nút (`RETURN p`) hoặc chỉ những thuộc tính cần dùng (`RETURN p.id, p.name`). Trong API, chọn đúng cột thường giúp giảm dữ liệu truyền về.

```cypher
MATCH (p:Person)
WHERE p.active = true
RETURN p.id AS id, p.name AS name, p.age AS age
ORDER BY age DESC, id ASC
LIMIT 3;
```

Kết quả với bộ dữ liệu mẫu:

| id | name | age |
| --- | --- | ---: |
| p04 | Dũng | 35 |
| p02 | Bình | 31 |
| p05 | An | 30 |

Các mệnh đề hay đi cùng:

- `ORDER BY` sắp xếp kết quả, mặc định tăng dần; `DESC` là giảm dần.
- `LIMIT n` chỉ lấy tối đa `n` dòng. Nếu không có `ORDER BY`, **không nên giả định** những dòng nào sẽ được trả về trước.
- `SKIP n` bỏ qua `n` dòng sau khi đã sắp xếp, phù hợp cho phân trang đơn giản; với tập rất lớn nên cân nhắc phân trang theo khóa ổn định.
- `count(p)` đếm các dòng nút `p` khớp; `count(DISTINCT p)` hữu ích khi mẫu quan hệ có thể tạo nhiều dòng cho cùng một nút.

Ví dụ đếm số người ở Hà Nội:

```cypher
MATCH (p:Person {city: 'Hà Nội'})
RETURN count(p) AS total;
```

**Kết quả:** `total = 3`.

## 9. Hiệu năng: nhãn, index và kế hoạch truy vấn

Trong cơ sở dữ liệu nhỏ, một truy vấn có thể nhanh dù chưa có index. Khi số lượng nút lớn, tra cứu bằng thuộc tính có độ chọn lọc cao (như `id`) thường hưởng lợi từ index.

Trên **cơ sở dữ liệu thử nghiệm**, có thể tạo index và ràng buộc như sau:

```cypher
CREATE RANGE INDEX person_city_idx IF NOT EXISTS
FOR (p:Person) ON (p.city);
```

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;
```

Ràng buộc duy nhất của `Person.id` đồng thời hỗ trợ truy vấn theo định danh và ngăn các nút `Person` có cùng giá trị `id` (với các nút có `id`). Việc tạo constraint sẽ thất bại nếu dữ liệu hiện có đã vi phạm tính duy nhất.

Để kiểm tra cách Neo4j dự kiến thực thi một truy vấn:

```cypher
EXPLAIN
MATCH (p:Person {id: 'p05'})
RETURN p.name AS name;
```

`EXPLAIN` tạo kế hoạch mà **không thực thi** câu truy vấn; `PROFILE` thực thi và bổ sung thống kê thực tế để đánh giá hiệu năng. Tùy phiên bản, số lượng nút, thống kê và index hiện có, kế hoạch có thể dùng thao tác quét nhãn hoặc tìm kiếm bằng index. Không nên mặc định rằng mọi câu `MATCH` đều sử dụng index.

Một số nguyên tắc:

1. Ghi nhãn đúng mục tiêu, chẳng hạn `(p:Person)`, thay vì quét tất cả nút với `(p)` khi không cần thiết.
2. Đặt index hoặc constraint trên các thuộc tính được tra cứu thường xuyên, đặc biệt định danh duy nhất.
3. Dùng tham số và lọc đủ sớm; chỉ trả về những thuộc tính cần sử dụng.
4. Kiểm tra kế hoạch và dữ liệu thực tế trước khi kết luận index nào hiệu quả. Các biểu thức biến đổi thuộc tính (chẳng hạn `toLower(p.name)`) hoặc tìm chuỗi con không có cùng khả năng tối ưu như phép so sánh trực tiếp với index thường.

## 10. Từ tìm nút đến tìm quan hệ

Sau khi nắm `MATCH` với nhãn và thuộc tính, có thể mở rộng mẫu để đi theo quan hệ của property graph:

```cypher
MATCH (p:Person {id: $personId})-[:WORKS_AT]->(c:Company)
RETURN p.name AS person, c.name AS company;
```

Câu này chỉ trả kết quả nếu cơ sở dữ liệu có quan hệ `WORKS_AT` tương ứng; bộ dữ liệu mẫu ở trên **chưa tạo** `Company` hay quan hệ nên không có dòng nào. Ví dụ cho thấy phần `(p:Person {id: $personId})` vẫn là thao tác tìm nút theo nhãn/thuộc tính, được nối thêm một mẫu quan hệ.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không trả về nút nào | Sai chữ hoa/thường ở nhãn, tên thuộc tính, hoặc giá trị chuỗi. | Kiểm tra `:Person`, `p.name` và giá trị thực tế. |
| Kết quả nhiều hơn dự kiến | Thuộc tính lọc không duy nhất, như hai người đều tên An. | Dùng `id` và ràng buộc duy nhất nếu nghiệp vụ yêu cầu. |
| Không tìm được thuộc tính thiếu | So sánh `= null` thay vì `IS NULL`. | Dùng `IS NULL` hoặc `IS NOT NULL`. |
| `LIMIT` trả về các dòng thay đổi | Thiếu `ORDER BY` để xác định thứ tự. | Sắp xếp theo thuộc tính ổn định, thêm `id` để phá hòa. |
| Truy vấn chậm trên dữ liệu lớn | Thiếu nhãn phù hợp, index, hoặc điều kiện lọc có độ chọn lọc thấp. | Xem `EXPLAIN`/`PROFILE` rồi kiểm tra index và biểu thức lọc. |
| Ứng dụng lỗi khi dựng Cypher | Ghép chuỗi đầu vào, sai kiểu tham số hoặc dùng tên thuộc tính động không hợp lệ. | Binding tham số cho giá trị và xác thực cấu trúc truy vấn. |

## 12. Bài tập tự luyện

Sử dụng bộ dữ liệu `Person` từ mục 3. Hãy tự viết truy vấn trước khi xem gợi ý.

**Bài 1.** Tìm `id` và `name` của những người từ 30 tuổi trở lên, sắp theo tuổi giảm dần rồi `id` tăng dần.

**Bài 2.** Tìm những người có nhãn `Employee` và sống tại Hà Nội.

**Bài 3.** Đếm số người đang hoạt động (`active = true`) ở Hà Nội.

**Bài 4.** Tìm chính xác người có `id = 'p03'` bằng tham số `$id`. Bạn dự kiến trả về mấy dòng nếu `id` là duy nhất?

<details>
<summary>Gợi ý đáp án và kết quả mong đợi</summary>

**Bài 1**

```cypher
MATCH (p:Person)
WHERE p.age >= 30
RETURN p.id AS id, p.name AS name, p.age AS age
ORDER BY age DESC, id ASC;
```

Kết quả: `p04`, `p02`, `p05`.

**Bài 2**

```cypher
MATCH (p:Person:Employee {city: 'Hà Nội'})
RETURN p.id AS id, p.name AS name
ORDER BY id;
```

Kết quả: `p01` và `p03`.

**Bài 3**

```cypher
MATCH (p:Person)
WHERE p.active = true AND p.city = 'Hà Nội'
RETURN count(p) AS total;
```

Kết quả: `total = 2`.

**Bài 4**

```cypher
MATCH (p:Person {id: $id})
RETURN p.id AS id, p.name AS name;
```

Với `id = 'p03'`, kết quả là một dòng `p03` (Chi), nếu thuộc tính `id` có tính duy nhất.

</details>

## 13. Ghi nhớ

- `MATCH (n:Label)` tìm các nút có nhãn; `MATCH (n:Label {key: value})` kết hợp điều kiện bằng cho thuộc tính.
- `WHERE` diễn đạt điều kiện linh hoạt với số, chuỗi, boolean, `IN` và kiểm tra `IS NULL`.
- Tên hoặc thuộc tính phổ biến có thể tạo nhiều kết quả; dùng định danh duy nhất khi muốn xác định một nút.
- Luôn dùng tham số cho giá trị đầu vào ứng dụng, sắp xếp trước khi giới hạn/phân trang và đo hiệu năng bằng kế hoạch truy vấn.
- Các thao tác này là viên gạch cơ bản để truy vấn quan hệ, đường đi và triển khai dữ liệu đồ thị bằng Neo4j với Cypher.
