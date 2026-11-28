# Kiểm tra biểu diễn dữ liệu để tránh sai so sánh hoặc sắp xếp

Một truy vấn Cypher có thể đúng cú pháp nhưng vẫn trả về kết quả sai nếu dữ liệu được lưu không đúng kiểu. Ví dụ, tuổi được lưu thành chuỗi khiến phép so sánh số không khớp; ngày tháng được lưu dưới nhiều định dạng khiến sắp xếp không theo thời gian; giá tiền dùng số thực có thể phát sinh sai số làm tròn. Những lỗi này thường khó phát hiện vì dữ liệu vẫn hiển thị bình thường trên giao diện.

Khi làm việc với Spring Data Neo4j, cần kiểm tra cả kiểu property trong Neo4j lẫn kiểu Java được truyền vào repository. Bài học này hướng dẫn cách kiểm tra biểu diễn dữ liệu, nhận diện các trường hợp so sánh và sắp xếp sai, chuẩn hóa dữ liệu cũ và chọn kiểu Java phù hợp.

## 1. Kiểu dữ liệu ảnh hưởng trực tiếp đến truy vấn

Neo4j lưu property bằng các kiểu dữ liệu được hỗ trợ như chuỗi, số nguyên, số thực, boolean, kiểu thời gian, điểm không gian và danh sách các giá trị property phù hợp. Node và relationship có thể chứa nhiều kiểu property khác nhau, nhưng một property cụ thể vẫn cần có biểu diễn nhất quán theo ý nghĩa nghiệp vụ.

Ví dụ, hai node sau nhìn gần giống nhau khi hiển thị:

```cypher
CREATE (:Person {name: 'An', age: 18})
CREATE (:Person {name: 'Bình', age: '18'})
```

Node thứ nhất có `age` là số nguyên (`INTEGER`), còn node thứ hai có `age` là chuỗi (`STRING`). Vì vậy, điều kiện số học:

```cypher
MATCH (p:Person)
WHERE p.age >= 18
RETURN p.name, p.age
```

không có nghĩa là Neo4j sẽ tự chuyển mọi chuỗi có nội dung là chữ số thành số nguyên. Phép so sánh cần dùng các giá trị cùng kiểu và cùng ý nghĩa. Không nên dựa vào ép kiểu ngầm hoặc thứ tự so sánh giữa các kiểu khác nhau để diễn đạt quy tắc nghiệp vụ.

Một quy ước hữu ích là xác định kiểu chuẩn ngay khi thiết kế model: tuổi là số nguyên, giá tiền là số nguyên theo đơn vị nhỏ nhất hoặc biểu diễn thập phân có quy tắc rõ ràng, ngày sinh là `DATE`, thời điểm tạo giao dịch là `DATETIME`, trạng thái kích hoạt là boolean.

## 2. Kiểm tra kiểu property trong Neo4j

Khi nghi ngờ dữ liệu không đồng nhất, hãy kiểm tra kiểu thực tế trước khi sửa truy vấn. Trong các phiên bản Neo4j hỗ trợ hàm `valueType()`, có thể xem kiểu của một biểu thức:

```cypher
MATCH (p:Person)
WHERE p.age IS NOT NULL
RETURN p.name AS name,
       p.age AS age,
       valueType(p.age) AS ageType
ORDER BY name
```

`valueType(p.age)` trả về mô tả kiểu của giá trị, chẳng hạn `INTEGER NOT NULL` hoặc `STRING NOT NULL`. Có thể thống kê số node theo kiểu:

```cypher
MATCH (p:Person)
RETURN CASE
         WHEN p.age IS NULL THEN 'MISSING'
         ELSE valueType(p.age)
       END AS ageType,
       count(*) AS total
ORDER BY total DESC
```

Trong Neo4j, property không tồn tại được đọc như `null`; gán `null` cho property cũng có tác dụng loại bỏ property khỏi node hoặc relationship. Vì vậy, nhãn `MISSING` trong truy vấn trên bao gồm trường hợp property không có trên node.

Nếu phiên bản Neo4j đang dùng không hỗ trợ `valueType()`, có thể kiểm tra dữ liệu bằng cách trả trực tiếp property qua Neo4j Browser hoặc dùng công cụ quản trị phù hợp. Dù dùng cách nào, hãy xác định cả kiểu dữ liệu lẫn các giá trị ngoại lệ trước khi chọn cách chuyển đổi.

### Kiểm tra dữ liệu thiếu và giá trị bất thường

```cypher
MATCH (p:Person)
WHERE p.age IS NULL
RETURN p.name AS name
```

Truy vấn tìm node chưa có property `age`. Với dữ liệu dạng chuỗi số, có thể tìm các giá trị không chuyển được thành số nguyên:

```cypher
MATCH (p:Person)
WHERE p.age IS NOT NULL
  AND toIntegerOrNull(p.age) IS NULL
RETURN p.name AS name, p.age AS invalidAge
```

Không nên chuyển đổi hàng loạt trước khi xem các giá trị không hợp lệ. Chúng có thể chứa chuỗi rỗng, ký hiệu, đơn vị đo hoặc lỗi nhập liệu cần xử lý theo quy tắc riêng.

## 3. Chuỗi và số: tránh so sánh hoặc sắp xếp theo thứ tự từ điển

Một lỗi phổ biến là lưu số dưới dạng chuỗi. So sánh và sắp xếp chuỗi thường theo thứ tự từ điển, tức so từng ký tự, không theo giá trị số.

Ví dụ:

```cypher
CREATE (:Product {sku: 'P-1', stockText: '3'})
CREATE (:Product {sku: 'P-2', stockText: '20'})
CREATE (:Product {sku: 'P-3', stockText: '100'})

MATCH (p:Product)
RETURN p.sku AS sku, p.stockText AS stock
ORDER BY p.stockText ASC
```

Kết quả sắp xếp chuỗi có thể là `100`, `20`, `3`, khác với thứ tự số mong muốn là `3`, `20`, `100`.

Nếu dữ liệu đã được xác nhận là chuỗi số hợp lệ, có thể chuyển kiểu ngay trong truy vấn để kiểm tra hoặc xử lý tạm thời:

```cypher
MATCH (p:Product)
WHERE toIntegerOrNull(p.stockText) IS NOT NULL
RETURN p.sku AS sku,
       toIntegerOrNull(p.stockText) AS stock
ORDER BY stock ASC
```

Đây là giải pháp chuyển kiểu trong lúc truy vấn. Với dữ liệu được dùng thường xuyên để lọc, so sánh hoặc sắp xếp, nên chuẩn hóa property thành kiểu số ngay trong database. Việc gọi hàm chuyển đổi trên từng dòng cũng có thể khiến truy vấn khó tận dụng index trên property gốc.

### Chuẩn hóa dữ liệu chuỗi số

Trước tiên, liệt kê giá trị không hợp lệ:

```cypher
MATCH (p:Product)
WHERE p.stockText IS NOT NULL
  AND toIntegerOrNull(p.stockText) IS NULL
RETURN p.sku AS sku, p.stockText AS invalidStock
```

Sau khi đã xử lý hoặc loại trừ các trường hợp bất thường, có thể ghi giá trị chuẩn hóa sang property số mới:

```cypher
MATCH (p:Product)
WHERE p.stockText IS NOT NULL
WITH p, toIntegerOrNull(p.stockText) AS parsedStock
WHERE parsedStock IS NOT NULL
SET p.stock = parsedStock
RETURN count(p) AS convertedCount
```

Ví dụ này giữ lại `stockText` để đối soát. Sau khi kiểm tra số lượng chuyển đổi và ứng dụng đã đọc property mới, nhóm phát triển mới quyết định có cần loại bỏ property cũ hay không. Không nên xóa dữ liệu nguồn trong cùng bước chuyển đổi đầu tiên.

## 4. Kiểu thời gian: lưu ngày và thời điểm bằng temporal type

Ngày và thời điểm có ý nghĩa khác nhau. Neo4j hỗ trợ các kiểu thời gian như:

| Kiểu Cypher | Ý nghĩa | Ví dụ biểu diễn |
|---|---|---|
| `DATE` | Ngày lịch, không có giờ | `date('2026-11-26')` |
| `LOCAL TIME` | Giờ trong ngày, không có múi giờ | `localtime('09:30:00')` |
| `TIME` | Giờ trong ngày có offset múi giờ | `time('09:30:00+07:00')` |
| `LOCAL DATETIME` | Ngày và giờ, không có múi giờ | `localdatetime('2026-11-26T09:30:00')` |
| `DATETIME` | Ngày và giờ có thông tin múi giờ | `datetime('2026-11-26T09:30:00+07:00')` |
| `DURATION` | Khoảng thời gian | `duration('P2DT3H')` |

Nếu lưu ngày dưới dạng chuỗi với nhiều định dạng như `26/11/2026`, `2026-11-26` và `11-26-2026`, so sánh hoặc sắp xếp chuỗi sẽ không thể hiện đúng thứ tự thời gian. Hãy chọn một kiểu temporal theo ý nghĩa nghiệp vụ.

Ví dụ truy vấn đơn hàng trong một khoảng ngày:

```cypher
MATCH (o:Order)
WHERE o.createdDate >= date($fromDate)
  AND o.createdDate < date($toDate)
RETURN o.orderNumber AS orderNumber,
       o.createdDate AS createdDate
ORDER BY createdDate ASC
```

Nếu tham số đã được truyền dưới dạng `LocalDate` qua Java Driver, có thể so sánh trực tiếp với `$fromDate` và `$toDate` mà không cần gọi `date()` trong Cypher. Điều quan trọng là property và tham số cùng biểu diễn kiểu ngày.

### Chọn kiểu theo ý nghĩa thời gian

- Ngày sinh, ngày hiệu lực hoặc ngày kế toán thường phù hợp với `DATE`.
- Giờ mở cửa trong ngày có thể phù hợp với `LOCAL TIME` nếu không gắn với múi giờ cụ thể.
- Thời điểm tạo đơn, thanh toán hoặc ghi nhận sự kiện cần xác định múi giờ/offset; thường dùng `DATETIME`.
- `LOCAL DATETIME` chỉ phù hợp khi nghiệp vụ thực sự không cần gắn thời điểm với múi giờ, ví dụ một lịch hẹn địa phương chưa xác định địa điểm.

Không nên dùng `LocalDateTime` cho một thời điểm toàn cầu nếu hệ thống cần so sánh sự kiện giữa nhiều múi giờ. Ngược lại, không nên gắn offset giả định cho một ngày lịch vốn không có thời gian.

Chuỗi ISO 8601 có thể dễ đọc và hữu ích khi trao đổi dữ liệu, nhưng lưu chuỗi vẫn là lưu `STRING`. Đặc biệt, các chuỗi thời điểm có offset khác nhau không nên được sắp xếp theo từ điển để suy ra thứ tự thời gian. Dùng temporal type giúp Neo4j thực hiện so sánh theo ngữ nghĩa thời gian.

## 5. Boolean, enum và các giá trị phân loại

Một cờ bật/tắt nên được lưu bằng boolean:

```cypher
CREATE (:Account {accountId: 'A-01', active: true})
```

Truy vấn:

```cypher
MATCH (a:Account)
WHERE a.active = true
RETURN a.accountId AS accountId
```

Tránh lưu cùng một trường lúc là boolean `true`, lúc là chuỗi `'true'`, hoặc các giá trị tự do như `'yes'`, `'Y'`, `'1'`. Nếu dữ liệu cũ có nhiều cách biểu diễn, hãy chuẩn hóa chúng thành một quy ước boolean duy nhất.

Với trạng thái hoặc enum, có thể lưu chuỗi mã ổn định như `PENDING`, `PAID`, `CANCELLED`. Không nên lưu ordinal phụ thuộc thứ tự khai báo enum trong mã Java, vì việc thêm hoặc sắp xếp lại phần tử enum có thể làm thay đổi ý nghĩa dữ liệu cũ.

Nếu cần hiển thị nhãn tiếng Việt, nên tách mã trạng thái khỏi nhãn giao diện. Ví dụ, `PAID` là mã lưu trữ ổn định, còn `Đã thanh toán` là nội dung hiển thị có thể thay đổi theo ngôn ngữ.

## 6. Kiểu số và độ chính xác của dữ liệu tiền tệ

Neo4j có kiểu số nguyên và số thực. Số thực dùng biểu diễn dấu phẩy động, vì vậy một số phép tính thập phân có thể có sai số làm tròn. Với tiền tệ, không nên mặc định dùng `FLOAT` để cộng dồn và đối soát số tiền cần độ chính xác thập phân.

Một cách phổ biến là lưu số tiền dưới dạng số nguyên theo đơn vị nhỏ nhất của đồng tiền. Ví dụ, 125.000 đồng được lưu là `125000` nếu đơn vị nhỏ nhất là đồng; với đồng tiền có đơn vị cent, lưu 12,34 đơn vị là `1234` cent. Cần lưu thêm mã tiền tệ nếu hệ thống hỗ trợ nhiều loại tiền:

```cypher
CREATE (:Payment {
    paymentId: 'PAY-001',
    amountMinor: 125000,
    currency: 'VND'
})
```

Không cộng trực tiếp các khoản tiền khác đơn vị tiền tệ. Trước khi tổng hợp, phải quy đổi theo tỷ giá và quy tắc làm tròn đã xác định.

Trong Java, `long` phù hợp với số nguyên theo đơn vị nhỏ nhất nếu giới hạn giá trị được kiểm soát. Nếu nghiệp vụ cần số thập phân chính xác, có thể cân nhắc lưu chuỗi thập phân chuẩn với converter rõ ràng hoặc một mô hình biểu diễn khác; cần kiểm thử việc chuyển đổi hai chiều và không để giá trị bị chuyển qua `double` làm mất độ chính xác.

## 7. Kiểm tra kiểu Java khi ánh xạ bằng Spring Data Neo4j

Spring Data Neo4j dùng metadata entity và cơ chế chuyển đổi của Spring Data/Neo4j Java Driver để ánh xạ property giữa Neo4j và Java. Kiểu Java nên phản ánh kiểu dữ liệu và ý nghĩa nghiệp vụ của property.

Ví dụ entity:

```java
import java.time.LocalDate;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String personId;

    private String name;

    private Integer age;

    private LocalDate birthDate;

    private Boolean active;

    private List<String> tags;
}
```

Trong ví dụ này:

- `String` ánh xạ dữ liệu chuỗi như `name` và `personId`.
- `Integer` phù hợp với tuổi nếu miền giá trị nằm trong giới hạn kiểu; dùng `Long` nếu cần phạm vi số nguyên lớn hơn.
- `LocalDate` biểu diễn ngày lịch, phù hợp với property Neo4j kiểu `DATE`.
- `Boolean` biểu diễn cờ bật/tắt; dùng wrapper `Boolean` nếu cần phân biệt `null` với `false`.
- `List<String>` phù hợp với danh sách tag dạng chuỗi được lưu như property list.

Neo4j property không phải JSON tùy ý. Các cấu trúc lồng nhau như map hoặc list lồng list không thể được lưu trực tiếp như một property node theo cách tùy ý; hãy mô hình hóa dữ liệu phức tạp thành node/relationship hoặc chuyển đổi có chủ đích.

Khi viết repository, kiểu tham số cũng cần phù hợp:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)
        WHERE p.age >= $minAge
          AND p.birthDate >= $fromDate
        RETURN p
        ORDER BY p.age ASC
        """)
    List<Person> findAdultsFromDate(
        @Param("minAge") Integer minAge,
        @Param("fromDate") LocalDate fromDate
    );
}
```

`minAge` là số nguyên và `fromDate` là ngày. Tránh khai báo `minAge` thành `String` chỉ vì dữ liệu đầu vào từ HTTP ban đầu là chuỗi; hãy parse và validate tại biên ứng dụng rồi truyền kiểu Java phù hợp vào repository.

## 8. Null, property không tồn tại và giá trị mặc định

Trong Neo4j, `null` thường biểu thị rằng property không có giá trị. Gán `null` cho property sẽ loại bỏ property khỏi node hoặc relationship. Vì vậy, `p.age IS NULL` có thể dùng để tìm node không có tuổi.

```cypher
MATCH (p:Person)
WHERE p.age IS NULL
RETURN p.personId AS personId
```

Không nên tự động thay mọi giá trị thiếu bằng `0`, `false` hoặc chuỗi rỗng nếu các giá trị đó mang ý nghĩa nghiệp vụ khác với “chưa biết”. Ví dụ, tuổi bằng 0 không đồng nghĩa với không có dữ liệu tuổi; `active = false` khác với trạng thái chưa xác định.

`coalesce()` trả về giá trị đầu tiên không phải `null`:

```cypher
MATCH (p:Person)
RETURN p.personId AS personId,
       coalesce(p.nickname, p.name, 'Chưa có tên') AS displayName
```

Chỉ dùng giá trị mặc định khi nghiệp vụ quy định rõ. Nếu báo cáo cần phân biệt dữ liệu thiếu, hãy trả về trạng thái thiếu riêng thay vì che đi bằng `coalesce()`.

Trong Java, wrapper như `Integer`, `Long`, `Boolean` có thể biểu diễn `null`; primitive như `int` và `boolean` không thể. Khi property có thể thiếu, dùng wrapper hoặc quy tắc mặc định rõ ràng ở tầng ứng dụng.

## 9. Sắp xếp đúng kiểu và kiểm tra kế hoạch truy vấn

`ORDER BY` sắp xếp theo giá trị biểu thức. Để kết quả có ý nghĩa, biểu thức cần mang đúng kiểu và dữ liệu cần nhất quán.

Ví dụ sắp xếp số nguyên:

```cypher
MATCH (p:Person)
WHERE p.age IS NOT NULL
RETURN p.name AS name, p.age AS age
ORDER BY age ASC
```

Ví dụ sắp xếp theo ngày:

```cypher
MATCH (o:Order)
WHERE o.createdAt IS NOT NULL
RETURN o.orderNumber AS orderNumber,
       o.createdAt AS createdAt
ORDER BY createdAt DESC
```

Nếu muốn sắp xếp tên không phân biệt chữ hoa/chữ thường, có thể dùng biểu thức chuẩn hóa:

```cypher
MATCH (p:Person)
RETURN p.name AS name
ORDER BY toLower(name) ASC
```

`toLower()` chỉ thay đổi cách so sánh chữ hoa/thường; nó không giải quyết mọi quy tắc sắp xếp theo ngôn ngữ hoặc dấu. Với nhu cầu sắp xếp theo locale phức tạp, cần xác định quy tắc collation ở tầng ứng dụng hoặc thiết kế khóa sắp xếp phù hợp.

Khi truy vấn chậm, hãy kiểm tra bằng `EXPLAIN` để xem kế hoạch và `PROFILE` để đo việc thực thi. Biểu thức như `toInteger(p.ageText)` hoặc `date(p.createdAtText)` có thể làm giảm khả năng tận dụng index trên property gốc. Nếu một trường thường xuyên được lọc hoặc sắp xếp, hãy lưu nó dưới kiểu chuẩn ngay từ đầu, tạo index phù hợp và kiểm tra kế hoạch thực thi với dữ liệu gần thực tế.

## 10. Quy trình chuẩn hóa dữ liệu an toàn

Khi phát hiện một property có nhiều kiểu hoặc nhiều định dạng, không nên sửa ngay trên toàn bộ dữ liệu. Có thể thực hiện theo trình tự:

1. **Thống kê hiện trạng:** dùng `valueType()`, truy vấn giá trị thiếu và các mẫu dữ liệu bất thường.
2. **Xác định kiểu chuẩn:** thống nhất kiểu Neo4j, kiểu Java và quy tắc nghiệp vụ.
3. **Liệt kê ngoại lệ:** tìm chuỗi rỗng, ký tự không hợp lệ, giá trị ngoài miền hoặc ngày không parse được.
4. **Chọn cách chuyển đổi:** chuyển trong ứng dụng khi ghi mới, hoặc chạy migration có kiểm soát cho dữ liệu cũ.
5. **Ghi sang property mới nếu cần:** giữ dữ liệu nguồn để đối soát trước khi loại bỏ.
6. **Kiểm tra số lượng và giá trị:** so sánh số bản ghi trước/sau, kiểm tra mẫu và các trường hợp biên.
7. **Chuyển ứng dụng sang property chuẩn:** cập nhật entity, repository, DTO và index.
8. **Theo dõi sau triển khai:** kiểm tra dữ liệu mới có tiếp tục tuân theo quy ước hay không.

Ở tầng ghi, validate dữ liệu trước khi gọi repository. Ví dụ, parse tuổi thành `Integer`, parse ngày thành `LocalDate`, từ chối giá trị không hợp lệ và không ghi chuỗi chưa chuẩn hóa vào property chuẩn. Như vậy, lỗi được chặn tại nơi phát sinh thay vì phải sửa ở mỗi truy vấn đọc.

## 11. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `WHERE age >= 18` bỏ sót node có `age: '18'` | Property đang là `STRING` | Kiểm tra bằng `valueType()`, chuyển sang kiểu số và chuẩn hóa luồng ghi. |
| `ORDER BY stock` cho thứ tự `100, 20, 3` | Sắp xếp chuỗi theo từ điển | Lưu `stock` thành số nguyên; chỉ chuyển kiểu trong truy vấn như giải pháp tạm. |
| Lọc ngày không đúng khoảng | Ngày lưu dưới dạng chuỗi hoặc lẫn kiểu thời gian | Dùng `DATE`/`DATETIME` nhất quán và tham số temporal tương ứng. |
| Boolean không khớp điều kiện | Dữ liệu lẫn `true`, `'true'`, `'Y'`, `'1'` | Chuẩn hóa thành boolean và thống nhất cách parse đầu vào. |
| Tổng tiền có sai số nhỏ | Dùng số thực cho giá trị cần độ chính xác | Dùng số nguyên theo đơn vị nhỏ nhất hoặc quy tắc decimal được kiểm soát. |
| Một số node không xuất hiện trong báo cáo | Property thiếu hoặc bị lọc bởi điều kiện | Kiểm tra `IS NULL`, phân biệt thiếu dữ liệu với giá trị mặc định. |
| Truy vấn chậm sau khi thêm ép kiểu | Hàm chuyển đổi chạy trên property ở mỗi dòng | Chuẩn hóa property, tạo index và kiểm tra bằng `EXPLAIN`/`PROFILE`. |

## 12. Ghi nhớ

So sánh và sắp xếp chính xác bắt đầu từ việc lưu đúng kiểu. Chuỗi số không tương đương số nguyên; chuỗi ngày không tương đương `DATE` hoặc `DATETIME`; boolean không nên trộn với các chuỗi biểu diễn bật/tắt. Dữ liệu thiếu cũng cần được phân biệt với số 0, `false` hoặc chuỗi rỗng.

Với Spring Data Neo4j, hãy giữ kiểu Java và kiểu property nhất quán, truyền tham số đúng kiểu vào repository, kiểm tra dữ liệu hiện có trước khi migration và dùng `EXPLAIN`/`PROFILE` khi cần tối ưu. Chuẩn hóa tại luồng ghi giúp truy vấn Cypher đơn giản hơn, kết quả dễ dự đoán hơn và index có cơ hội phát huy hiệu quả.
