# Property không tồn tại, giá trị null và kiểu nguyên thủy Java

Khi ánh xạ dữ liệu giữa Neo4j và Java, một trường có thể không có property trong node, có thể được đọc thành `null`, hoặc có thể mang một giá trị mặc định như `0` hay `false`. Những trạng thái này ảnh hưởng trực tiếp tới kết quả truy vấn Cypher và cách Spring Data Neo4j (SDN) ánh xạ entity.

Neo4j không lưu property có giá trị `null`: gán `null` cho một property sẽ xóa property đó khỏi node hoặc relationship. Vì vậy, trong graph đã lưu, “property không tồn tại” và “property có giá trị null” không phải hai trạng thái dữ liệu riêng biệt. Khi đọc vào Java, kiểu tham chiếu như `Integer` có thể biểu diễn trạng thái không có giá trị bằng `null`, còn kiểu nguyên thủy như `int` luôn có một giá trị số và không thể giữ trạng thái đó.

Bài học này giải thích semantics của property trong Neo4j, cách kiểm tra giá trị null bằng Cypher, khác biệt giữa Java primitive và wrapper, cùng cách thiết kế entity và luồng cập nhật để không vô tình biến dữ liệu thiếu thành giá trị mặc định.

## 1. Property trong Neo4j có thể tồn tại hoặc không tồn tại

Neo4j lưu thuộc tính trên node và relationship dưới dạng các cặp tên–giá trị. Ví dụ, một node `Person` có thể chứa `name`, `age` và `email`:

```cypher
CREATE (p:Person {
    personId: 'P-100',
    name: 'An',
    age: 28,
    email: 'an@example.com'
});
```

Một node khác có thể chưa có `email`:

```cypher
CREATE (p:Person {
    personId: 'P-101',
    name: 'Binh',
    age: 31
});
```

Trong node thứ hai, property `email` không tồn tại. Neo4j không lưu một cặp `email = null` để biểu diễn trạng thái này. Nếu một biểu thức Cypher đọc `p.email`, kết quả là `null` vì không tìm thấy property.

Một số thao tác thường gặp:

| Thao tác | Trạng thái sau thao tác |
|---|---|
| `SET p.age = 28` | Property `age` tồn tại và có giá trị `28` |
| `SET p.age = 0` | Property `age` tồn tại và có giá trị `0` |
| `SET p.age = null` | Property `age` bị xóa |
| `REMOVE p.age` | Property `age` bị xóa |
| Đọc `p.age` khi property không tồn tại | Biểu thức trả về `null` |

Điểm quan trọng: `0`, `false` và chuỗi rỗng `''` là những giá trị thực có thể lưu. Chúng khác với việc property không tồn tại. Không dùng các giá trị này để thay thế cho `null` trừ khi đó thực sự là quy tắc nghiệp vụ.

## 2. Đọc và lọc property null bằng Cypher

Trong Cypher, dùng `IS NULL` và `IS NOT NULL` để kiểm tra property:

```cypher
// Tìm người chưa có email.
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p.personId, p.name;

// Tìm người đã có email.
MATCH (p:Person)
WHERE p.email IS NOT NULL
RETURN p.personId, p.email;
```

Không viết `p.email = null` để kiểm tra giá trị thiếu:

```cypher
// Không dùng phép so sánh này để tìm property thiếu.
MATCH (p:Person)
WHERE p.email = null
RETURN p;
```

Trong logic ba giá trị của Cypher, phép so sánh với `null` cho kết quả `null`, không phải `true` hoặc `false`. Mệnh đề `WHERE` chỉ giữ các dòng có điều kiện là `true`, do đó truy vấn trên không trả về các node thiếu email. Dùng `IS NULL` là cách đúng.

Để xem property nào thực sự có mặt, có thể kiểm tra map thuộc tính của node:

```cypher
MATCH (p:Person)
RETURN p.personId AS personId,
       p.email AS emailValue,
       'email' IN keys(p) AS hasEmailProperty,
       properties(p) AS storedProperties;
```

`keys(p)` trả về tên các property đang được lưu trên node; `properties(p)` trả về map các property hiện có. Với property của node đã lưu, `p.email IS NULL` tương ứng với việc property không có giá trị, còn `'email' IN keys(p)` cho biết key có hiện diện hay không.

## 3. Gán null là xóa property

Giả sử một người đổi địa chỉ email và ứng dụng muốn xóa email cũ. Có thể dùng:

```cypher
MATCH (p:Person {personId: 'P-100'})
SET p.email = null
RETURN p.personId, p.email;
```

Sau câu lệnh này, property `email` không còn tồn tại. Cách viết tường minh tương đương là:

```cypher
MATCH (p:Person {personId: 'P-100'})
REMOVE p.email
RETURN p.personId, p.email;
```

`SET property = null` hữu ích khi tham số đến từ ứng dụng có thể là null. Ví dụ repository query nhận tham số `email`:

```java
public interface PersonEmailView {
    String getPersonId();
    String getEmail();
}
```

Thêm phương thức sau vào repository tương ứng:

```java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Person {personId: $personId})
    SET p.email = $email
    RETURN p.personId AS personId,
           p.email AS email
    """)
PersonEmailView updateEmail(
    @Param("personId") String personId,
    @Param("email") String email
);
```

Khi tham số `$email` là `null`, Neo4j xóa property `email`. Nếu nghiệp vụ yêu cầu giữ nguyên email khi client không gửi trường đó, service phải phân biệt “không gửi trường” với “gửi trường có giá trị null” trước khi gọi query. Không thể suy ra hai ý định này chỉ từ giá trị `String` sau khi framework đã bind cả hai thành `null`.

## 4. Java primitive không biểu diễn được null

Java có hai nhóm kiểu dữ liệu thường gặp khi ánh xạ property:

- **Primitive:** `int`, `long`, `double`, `boolean` và các kiểu nguyên thủy khác. Biến primitive luôn có giá trị; nó không thể nhận `null`.
- **Wrapper/reference:** `Integer`, `Long`, `Double`, `Boolean`, `String` và các kiểu đối tượng. Biến có thể nhận `null`.

Giá trị mặc định của primitive khi một field chưa được gán là:

| Kiểu | Giá trị mặc định |
|---|---:|
| `byte`, `short`, `int`, `long` | `0` |
| `float`, `double` | `0.0` |
| `char` | ký tự `\u0000` |
| `boolean` | `false` |

Ví dụ:

```java
public class PersonFlags {
    private int age;
    private boolean verified;

    private Integer score;
    private Boolean marketingOptIn;
}
```

Nếu các field trên được tạo bằng constructor mặc định và chưa được gán, `age` là `0`, `verified` là `false`, còn `score` và `marketingOptIn` là `null`. Primitive không có trạng thái thứ ba để biểu diễn “chưa biết” hoặc “không được cung cấp”.

Vì vậy, nếu `0` là tuổi hợp lệ hoặc `false` là lựa chọn có ý nghĩa, dùng primitive có thể làm mất thông tin: ứng dụng không biết giá trị `0`/`false` đến từ dữ liệu đã lưu hay chỉ là giá trị mặc định của Java. Với property có thể thiếu, wrapper thường phù hợp hơn.

## 5. Ánh xạ property tùy chọn trong Spring Data Neo4j

Trong SDN, entity là mô hình Java của node. Với một property có thể không tồn tại, hãy dùng kiểu tham chiếu tương ứng:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.GeneratedValue;

@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String personId;
    private String name;

    // Có thể chưa được lưu trên node.
    private Integer age;
    private Boolean verified;
    private String email;

    protected Person() {
    }

    public Integer getAge() {
        return age;
    }

    public Boolean getVerified() {
        return verified;
    }

    public String getEmail() {
        return email;
    }
}
```

Khi node không có property `age`, `verified` hoặc `email`, các field tham chiếu tương ứng có thể được biểu diễn bằng `null` trong entity được ánh xạ. Điều này giúp service phân biệt dữ liệu thiếu với giá trị `0` hoặc `false` đã được lưu.

Nếu thuộc tính bắt buộc và ứng dụng luôn gán giá trị ngay khi tạo node, primitive có thể là lựa chọn phù hợp:

```java
@Node("Account")
public class Account {
    @Id
    @GeneratedValue
    private Long id;

    private String accountNumber;

    // Quy tắc miền dữ liệu yêu cầu hai thuộc tính này luôn có giá trị.
    private int loginCount;
    private boolean enabled;

    protected Account() {
    }
}
```

Với `loginCount` và `enabled`, hãy đặt giá trị ban đầu theo nghiệp vụ khi tạo account, ví dụ `0` và `true` hoặc `false` theo chính sách. Không dựa vào giá trị mặc định của JVM để thay thế bước khởi tạo nghiệp vụ. Nếu dữ liệu cũ có thể thiếu các property này, cần migration/backfill trước khi chuyển entity sang primitive.

Lưu ý: `@Id` và `@GeneratedValue` trong ví dụ chỉ minh họa định danh node. Các getter, setter và constructor khác được lược bớt. Khi dùng constructor mapping hoặc record, hãy bảo đảm constructor cũng xử lý đúng trường hợp property không tồn tại; quy tắc “primitive không nhận null” vẫn áp dụng.

## 6. Tránh biến dữ liệu thiếu thành giá trị mặc định

Một lỗi dễ gặp là dùng primitive cho dữ liệu tùy chọn rồi hiểu giá trị mặc định là dữ liệu thật. Ví dụ:

```java
public class Profile {
    private int age;
}
```

Nếu `age` không được lưu trên node, một field `int` mới tạo có giá trị `0`. Khi service trả `age = 0`, client có thể hiểu nhầm rằng tuổi của người dùng thực sự bằng 0.

Sửa mô hình thành:

```java
public class Profile {
    private Integer age;
}
```

Lúc này, `null` có thể biểu diễn dữ liệu chưa có; `0` vẫn là một giá trị số cụ thể. Ở tầng API, hãy quyết định cách biểu diễn `null` trong JSON theo hợp đồng của ứng dụng.

Không nên thay mọi `null` bằng `0`, `false` hoặc `""` chỉ để tránh null check. Chỉ dùng giá trị mặc định khi nó có ý nghĩa nghiệp vụ rõ ràng. Nếu cần giá trị mặc định khi đọc, có thể dùng `coalesce` trong Cypher:

```cypher
MATCH (p:Person)
RETURN p.personId AS personId,
       p.age AS storedAge,
       coalesce(p.age, 18) AS ageForDisplay;
```

`coalesce` chỉ tạo giá trị thay thế trong kết quả truy vấn; nó không ghi `18` trở lại node. Nhờ vậy, dữ liệu lưu trữ vẫn giữ trạng thái thiếu. Chỉ dùng fallback này nếu `18` thực sự là giá trị phù hợp cho mục đích hiển thị hoặc tính toán đang thực hiện.

## 7. Phân biệt không gửi trường và yêu cầu xóa trường

Trong API cập nhật kiểu PATCH, có ba ý định thường gặp:

1. Client không gửi `email`: giữ nguyên email hiện tại.
2. Client gửi `email: null`: xóa email hiện tại.
3. Client gửi `email: "new@example.com"`: cập nhật email mới.

Nếu DTO chỉ có `String email`, sau khi deserialize, cả trường hợp không gửi và gửi `null` có thể cùng trở thành `null`. Service khi đó không đủ thông tin để phân biệt hai ý định.

Một DTO có thể lưu trạng thái hiện diện riêng:

```java
public class UpdatePersonRequest {
    private boolean emailProvided;
    private String email;

    public boolean isEmailProvided() {
        return emailProvided;
    }

    public String getEmail() {
        return email;
    }
}
```

Ứng dụng cần cấu hình deserialization hoặc setter để `emailProvided` chỉ thành `true` khi key `email` xuất hiện trong JSON, kể cả khi giá trị của key là `null`. Một lựa chọn khác là dùng kiểu dữ liệu hỗ trợ tri-state như `JsonNullable<T>` từ thư viện phù hợp. Chỉ dùng `Optional<String>` cho field DTO nếu framework và hợp đồng API định nghĩa rõ cách phân biệt missing với explicit null; `Optional` đơn thuần thường không tự giải quyết được cả hai trạng thái.

Service có thể xử lý theo trạng thái:

```java
if (request.isEmailProvided()) {
    // email null: xóa property trong Neo4j.
    // email khác null: ghi giá trị mới.
    personRepository.updateEmail(personId, request.getEmail());
}
// emailProvided=false: không cập nhật property.
```

Quy tắc này giúp tránh xóa dữ liệu ngoài ý muốn khi client chỉ cập nhật một trường khác, chẳng hạn tên hiển thị.

## 8. Mô hình hóa trạng thái nghiệp vụ khi cần nhiều hơn null

Trong Neo4j, property thiếu và property được gán null không thể được lưu như hai trạng thái riêng. Nếu nghiệp vụ cần phân biệt “chưa xác minh”, “không áp dụng” và “đã xác minh có giá trị”, hãy mô hình hóa trạng thái đó thành một property riêng.

Ví dụ hồ sơ ngày sinh:

```cypher
CREATE (p:Person {
    personId: 'P-200',
    birthDateStatus: 'UNKNOWN'
});
```

Khi người dùng cung cấp ngày sinh:

```cypher
MATCH (p:Person {personId: 'P-200'})
SET p.birthDate = date('1995-04-12'),
    p.birthDateStatus = 'KNOWN';
```

Khi xác định thông tin không áp dụng:

```cypher
MATCH (p:Person {personId: 'P-200'})
REMOVE p.birthDate
SET p.birthDateStatus = 'NOT_APPLICABLE';
```

Ở đây, `birthDateStatus` lưu trạng thái nghiệp vụ; `birthDate` chỉ tồn tại khi có ngày cụ thể. Ứng dụng có thể dùng enum Java để giới hạn giá trị hợp lệ:

```java
public enum BirthDateStatus {
    UNKNOWN,
    KNOWN,
    NOT_APPLICABLE
}
```

Đừng dùng một ngày giả như `1900-01-01` hoặc số `-1` để đại diện cho thiếu dữ liệu. Giá trị giả có thể bị hiểu nhầm là dữ liệu thật trong truy vấn, báo cáo hoặc tích hợp.

## 9. Kiểm tra property thiếu trong công cụ truy vấn

Neo4j Browser và Cypher Shell có thể xác minh trạng thái property trực tiếp. Ví dụ tìm các node Person chưa có tuổi:

```cypher
MATCH (p:Person)
WHERE p.age IS NULL
RETURN p.personId AS personId,
       p.name AS name,
       'age' IN keys(p) AS hasAge;
```

Tìm các node có tuổi:

```cypher
MATCH (p:Person)
WHERE p.age IS NOT NULL
RETURN p.personId, p.age
ORDER BY p.age;
```

Đặt giá trị tuổi cho một người:

```cypher
MATCH (p:Person {personId: 'P-100'})
SET p.age = 29
RETURN p.personId, p.age;
```

Xóa tuổi:

```cypher
MATCH (p:Person {personId: 'P-100'})
SET p.age = null
RETURN p.personId, p.age,
       'age' IN keys(p) AS hasAge;
```

Sau thao tác xóa, `p.age` trả về `null` và `hasAge` là `false`. Nếu thay bằng `SET p.age = 0`, `hasAge` sẽ là `true` và giá trị được trả về là `0`.

## 10. Quy tắc lựa chọn kiểu Java

| Yêu cầu dữ liệu | Kiểu Java nên cân nhắc | Lý do |
|---|---|---|
| Tuổi có thể chưa biết | `Integer` | Biểu diễn được `null` và số `0` |
| Cờ xác minh có thể chưa được xác định | `Boolean` | Phân biệt `null`, `true` và `false` |
| Bộ đếm luôn có giá trị và được khởi tạo rõ ràng | `long` hoặc `int` | Giá trị luôn tồn tại theo quy tắc miền dữ liệu |
| Trạng thái bật/tắt bắt buộc | `boolean` | Phù hợp khi ứng dụng luôn xác định true/false |
| Email tùy chọn | `String` | Có thể biểu diễn `null`; chuỗi rỗng vẫn là giá trị riêng |
| Ngày tùy chọn | `LocalDate` | Có thể biểu diễn `null` khi chưa có ngày |

Một số nguyên tắc thực hành:

1. Dùng wrapper cho property có thể thiếu hoặc chưa được biết.
2. Dùng primitive cho property bắt buộc, luôn có giá trị và được khởi tạo rõ ràng.
3. Không dựa vào giá trị mặc định của JVM để thay thế quy tắc nghiệp vụ.
4. Dùng `IS NULL`/`IS NOT NULL` trong Cypher thay vì so sánh bằng `= null`.
5. Nhớ rằng `SET property = null` xóa property khỏi graph.
6. Với PATCH, lưu trạng thái hiện diện của field để phân biệt không cập nhật và yêu cầu xóa.
7. Nếu cần nhiều trạng thái nghiệp vụ, mô hình hóa bằng enum hoặc property trạng thái riêng.

## 11. Tự kiểm tra

1. Neo4j lưu một property có giá trị `null` như thế nào?
2. Khác biệt giữa `SET p.age = 0` và `SET p.age = null` là gì?
3. Vì sao `WHERE p.email = null` không phải cách đúng để tìm node chưa có email?
4. Khi property `age` không tồn tại, field Java kiểu `int` có thể gây hiểu nhầm gì?
5. Khi nào nên dùng `Integer` thay cho `int` trong một entity SDN?
6. Trong một API PATCH, làm sao phân biệt client không gửi `email` với client gửi `email: null`?
7. Nếu cần phân biệt `UNKNOWN` và `NOT_APPLICABLE`, vì sao nên lưu một property trạng thái riêng?
