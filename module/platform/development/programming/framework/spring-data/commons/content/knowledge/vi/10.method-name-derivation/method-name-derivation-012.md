# Đối chiếu từ khóa Commons với danh sách được store thực sự triển khai

Danh sách từ khóa của Spring Data Commons mô tả một bộ từ vựng dùng trong việc phân tích tên phương thức repository. Danh sách đó không phải lời cam kết rằng mọi module Spring Data đều tạo được truy vấn cho mọi từ khóa.

Ví dụ, `Regex` có thể được parser nhận diện thành một loại điều kiện, nhưng repository JPA thông thường không vì thế mà có khả năng suy diễn truy vấn biểu thức chính quy. MongoDB lại có cơ chế truy vấn regex riêng. Ngay cả khi một store hỗ trợ toán tử, kiểu thuộc tính, chữ ký phương thức, mapping, index và mô hình khóa vẫn ảnh hưởng tới tính hợp lệ và hành vi thực tế.

Trong phạm vi Spring Data Commons, kỹ năng cần rèn là đọc bộ từ vựng chung, sau đó đối chiếu với module cụ thể thay vì áp dụng nguyên danh sách vào mọi repository.

Sau bài học, bạn cần có khả năng:

- Phân biệt từ khóa chủ đề, toán tử điều kiện và modifier.
- Giải thích vì sao parse được không đồng nghĩa thực thi được.
- Đối chiếu từ khóa với đúng module, phiên bản, kiểu thuộc tính và store.
- Nhận ra khác biệt giữa `existsBy...` và hậu tố `...Exists`.
- Chọn derived query, truy vấn khai báo hoặc repository fragment theo khả năng thực tế.

## 1. Bốn lớp phải đi qua trước khi có kết quả

Một tên phương thức đi qua nhiều lớp:

```text
Tên phương thức
       ↓
Commons nhận diện cấu trúc và từ khóa
       ↓
Phân giải thuộc tính trên domain, kiểm tra tham số
       ↓
Module của store chuyển các phần điều kiện thành query
       ↓
Store thực thi, module ánh xạ kết quả
```

Có thể phân biệt bốn câu hỏi:

| Lớp | Câu hỏi | Ví dụ vấn đề |
|---|---|---|
| Cú pháp tên | Tên được tách thành chủ đề và điều kiện nào? | `Regex` được nhận diện là toán tử |
| Domain và chữ ký | Thuộc tính, kiểu và tham số có phù hợp không? | Tên thuộc tính sai, thiếu đối số |
| Module store | Bộ tạo truy vấn có triển khai loại điều kiện đó không? | Parser biết `REGEX` nhưng JPA không dịch nó thành derived query |
| Hệ thống lưu trữ | Query có hợp lệ và đáp ứng yêu cầu không? | Thiếu partition key hoặc thiếu index cần thiết |

Thành công ở một lớp không chứng minh những lớp còn lại thành công. Ngược lại, một lỗi về đường dẫn thuộc tính không phải bằng chứng rằng store không hỗ trợ toán tử.

## 2. Chia đúng nhóm từ khóa trước khi đối chiếu

### 2.1. Từ khóa chủ đề

Phần trước `By` mô tả ý định tổng quát của phương thức:

| Nhóm | Ví dụ | Ý định |
|---|---|---|
| Đọc | `findBy...`, `readBy...`, `getBy...` | Tìm dữ liệu |
| Đếm | `countBy...` | Đếm dữ liệu thỏa điều kiện |
| Tồn tại | `existsBy...` | Kiểm tra có kết quả thỏa điều kiện |
| Xóa | `deleteBy...`, `removeBy...` | Xóa theo điều kiện |
| Giới hạn | `findFirstBy...`, `findTop10By...` | Giới hạn kết quả nếu module hỗ trợ |
| Loại trùng | `findDistinctBy...` | Yêu cầu distinct theo khả năng và ngữ nghĩa của module |

Bộ từ vựng chủ đề còn có các biến thể như `query`, `search`, `stream`. Không suy ra rằng mọi biến thể đều có cùng khả năng về kiểu trả về, streaming hoặc quản lý tài nguyên ở mọi store.

Các phương thức kế thừa như `CrudRepository.findById` còn có hợp đồng dành riêng cho định danh. Không dùng việc một phương thức CRUD tồn tại làm bằng chứng rằng mọi từ khóa suy diễn đều được module triển khai.

### 2.2. Toán tử điều kiện

Các từ khóa sau có thể được Commons nhận diện trong phần điều kiện. Bảng chỉ liệt kê các dạng tiêu biểu, không phải mọi alias.

| Nhóm | Ví dụ trong tên phương thức | Ý định khái quát |
|---|---|---|
| Bằng/khác | `Is`, `Equals`, `Not` | So sánh giá trị |
| Khoảng/so sánh | `Between`, `LessThan`, `GreaterThanEqual` | Điều kiện trên giá trị có thứ tự |
| Thời gian | `Before`, `After` | So sánh trước/sau nếu module và kiểu hỗ trợ |
| Null | `IsNull`, `IsNotNull` | Kiểm tra null |
| Tập hợp | `In`, `NotIn` | So sánh với một tập giá trị |
| Mẫu chuỗi | `Like`, `StartingWith`, `EndingWith`, `Containing` | So khớp chuỗi theo cách module định nghĩa |
| Collection rỗng | `IsEmpty`, `IsNotEmpty` | Kiểm tra rỗng trong ngữ cảnh được hỗ trợ |
| Boolean | `True`, `False` | Điều kiện boolean |
| Biểu thức chính quy | `Regex`, `MatchesRegex` | Điều kiện regex nếu store hỗ trợ |
| Không gian | `Near`, `Within` | Điều kiện địa lý/không gian |
| Sự hiện diện | `Exists` | Kiểm tra tồn tại của thuộc tính/trường nếu module triển khai |

Không đọc bảng này như danh sách “bật sẵn” trên JPA, JDBC, MongoDB, Cassandra hoặc Redis.

### 2.3. Kết hợp, modifier và thứ tự

Các thành phần khác cũng cần được đối chiếu:

- `And`, `Or`: kết hợp các phần điều kiện.
- `IgnoreCase`, `AllIgnoreCase`: yêu cầu xử lý chữ hoa/thường trong phạm vi thích hợp.
- `OrderBy...Asc`, `OrderBy...Desc`: sắp xếp tĩnh.
- `First`, `Top`: giới hạn, không tự tạo một thứ tự kết quả ổn định.
- `Distinct`: không có một cách diễn giải về loại trùng áp dụng đồng nhất cho mọi loại kết quả.

Hỗ trợ từng toán tử riêng lẻ chưa bảo đảm mọi tổ hợp của chúng đều hợp lệ. Chẳng hạn, khả năng so sánh bằng không tự chứng minh store hỗ trợ `Or`, và hỗ trợ đọc không tự chứng minh hỗ trợ xóa suy diễn.

## 3. Đọc một tên phương thức thành các yêu cầu độc lập

Xét:

```java
findTop5ByStatusAndEmailContainingIgnoreCaseOrderByCreatedAtDesc(...)
```

Để phương thức này hoạt động đúng, cần nhiều khả năng:

| Thành phần | Điều cần có |
|---|---|
| `find...By` | Module hỗ trợ phương thức đọc suy diễn |
| `Top5` | Hỗ trợ giới hạn theo cách này |
| `Status` | Thuộc tính `status` hợp lệ, có thể truy vấn |
| `And` | Kết hợp điều kiện được hỗ trợ |
| `EmailContaining` | Hỗ trợ phép chứa trên kiểu của `email` |
| `IgnoreCase` | Hỗ trợ xử lý không phân biệt hoa/thường |
| `OrderByCreatedAtDesc` | Hỗ trợ sắp xếp trên `createdAt` |
| Kiểu trả về | Phù hợp số lượng kết quả và cách thực thi |

Một lỗi có thể nằm ở bất kỳ hàng nào. Không nên sửa bằng cách thử thêm alias ngẫu nhiên mà chưa biết lớp nào đang từ chối.

Khi tên có thuộc tính lồng nhau, còn cần phân giải đường dẫn, chẳng hạn `Customer_Address_ZipCode`. Parser hiểu ranh giới đó không có nghĩa mọi store đều có thể join, đi qua reference hoặc lọc trên cấu trúc tương ứng.

## 4. Hợp đồng thực tế là giao của nhiều khả năng

Có thể dùng cách kiểm tra sau:

```text
Một derived query dùng được khi đồng thời:
  - Commons hiểu đúng cấu trúc tên.
  - Thuộc tính và tham số đúng.
  - Module triển khai những toán tử/modifier được yêu cầu.
  - Store chấp nhận query theo schema/mapping hiện tại.
  - Kết quả và chi phí truy cập đáp ứng use case.
```

Một ô “có hỗ trợ” trong tài liệu thường chưa nói hết:

- Toán tử có áp dụng cho cả chuỗi, số và collection không?
- Tham số cần một giá trị, hai giá trị, boolean hay collection?
- Giá trị null và collection rỗng được hiểu ra sao?
- Trường thiếu có khác trường mang null không?
- Có yêu cầu index hoặc khóa đặc thù không?
- Hỗ trợ trên repository đọc đồng bộ có đồng nghĩa hỗ trợ cùng kiểu trả về reactive không?

Vì vậy, phải đối chiếu cả **từ khóa**, **kiểu thuộc tính**, **chữ ký**, **mapping** và **ràng buộc store**.

## 5. Đối chiếu cụ thể giữa JPA và MongoDB

Bảng sau minh họa những khác biệt quan trọng của cơ chế suy diễn thông thường. Nó không phải danh sách đầy đủ hay chứng nhận cho mọi phiên bản, provider và cấu hình.

| Yêu cầu trong tên | Spring Data JPA | Spring Data MongoDB |
|---|---|---|
| `Email`, `EmailIs`, `EmailEquals` | So sánh bằng trên thuộc tính persistent thích hợp | So sánh giá trị trường qua mapping |
| `EmailContaining` với thuộc tính chuỗi | Phép tìm chuỗi con, dựa trên cơ chế LIKE | Phép so khớp chuỗi theo cơ chế của module MongoDB |
| `EmailContainingIgnoreCase` | Có hỗ trợ với kiểu chuỗi thích hợp | Có hỗ trợ, cách thực hiện không phải SQL LIKE |
| `EmailRegex` | Không phải toán tử derived query được JPA triển khai thông thường | Có hỗ trợ regex |
| `EmailExists(boolean)` | Không có hợp đồng suy diễn kiểm tra “sự hiện diện cột” tương ứng | Có thể kiểm tra trường tồn tại bằng điều kiện exists |
| `existsByEmail(value)` | Kiểm tra có entity khớp điều kiện | Kiểm tra có document khớp điều kiện |
| `LocationNear`, `LocationWithin` | Không có hỗ trợ suy diễn không gian tương ứng trong JPA thông thường | Có cơ chế truy vấn địa lý với ràng buộc kiểu, toán tử và index |

Nếu dùng extension, custom fragment hoặc truy vấn khai báo đặc thù, ứng dụng có thể có thêm khả năng. Đó không phải bằng chứng rằng derived query mặc định của module đã hỗ trợ cùng từ khóa.

### 5.1. “Cùng được hỗ trợ” chưa có nghĩa hành vi giống hệt

Với `ContainingIgnoreCase`, không nên chỉ so sánh tên:

- JPA phải chuyển yêu cầu thành biểu thức mà provider và cơ sở dữ liệu quan hệ thực thi.
- MongoDB sử dụng cơ chế tìm mẫu chuỗi của module và store.
- Quy tắc collation, Unicode, giá trị null và cách sử dụng index có thể khác.
- Ký tự đầu vào được hiểu là chuỗi literal hay mẫu phụ thuộc toán tử; không tráo `Containing`, `Like` và `Regex` tùy ý.

Một ứng dụng chuyển store cần kiểm chứng những ví dụ dữ liệu thực tế, không chỉ kiểm tra phương thức còn biên dịch.

## 6. Ví dụ JPA: chọn từ khóa đã được triển khai

Giả sử `JpaCustomer` là entity JPA có thuộc tính `email` kiểu `String`, với mapping và repository scanning đã được cấu hình.

```java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

interface JpaCustomerRepository
        extends JpaRepository<JpaCustomer, Long> {

    List<JpaCustomer> findByEmailContainingIgnoreCase(String fragment);

    boolean existsByEmail(String email);
}
```

Hai phương thức có mục đích khác nhau:

- Phương thức đầu tìm các entity có email thỏa phép tìm chuỗi.
- Phương thức thứ hai kiểm tra tồn tại của entity thỏa phép so sánh email.

### 6.1. Parser nhận Regex không làm JPA triển khai Regex

Một khai báo không nên thêm vào repository JPA thông thường với kỳ vọng tự suy diễn được:

```java
// Ví dụ không được JPA derived query hỗ trợ thông thường:
List<JpaCustomer> findByEmailRegex(String pattern);
```

Đổi thành `findByEmailMatchesRegex(...)` không giải quyết bản chất nếu cả hai alias cùng được parser nhận diện là loại điều kiện `REGEX`.

Có thể quan sát riêng lớp parser bằng Commons, với một kiểu chỉ dùng để mô tả cấu trúc:

```java
import org.springframework.data.repository.query.parser.PartTree;

class CustomerShape {
    String email;
}

PartTree tree = new PartTree(
    "findByEmailRegex",
    CustomerShape.class
);

tree.getParts().forEach(part -> {
    System.out.println(part.getProperty().toDotPath());
    // email

    System.out.println(part.getType().name());
    // REGEX
});
```

Đoạn này không mở kết nối, không gọi bộ tạo query JPA và không gửi query tới database. Nó chỉ cho thấy Commons đã nhận diện được đường dẫn và loại điều kiện.

Nếu thật sự cần regex với cơ sở dữ liệu quan hệ, phải chọn giải pháp phù hợp như native query hoặc fragment sử dụng khả năng của hệ quản trị. Khi đó cần xem lại tính phụ thuộc dialect, cách bind và hiệu năng.

### 6.2. Đúng từ khóa nhưng sai kiểu thuộc tính vẫn thất bại

Giả sử entity có collection persistent `orders` và một chuỗi `email`:

```java
// Dùng cho collection persistent phù hợp trong JPA:
List<JpaCustomer> findByOrdersIsEmpty();

// Không hiểu IsEmpty như phép kiểm tra chuỗi rỗng trên email:
List<JpaCustomer> findByEmailIsEmpty();
```

JPA hỗ trợ kiểm tra collection rỗng không có nghĩa cùng toán tử áp dụng cho chuỗi. Nếu nghiệp vụ muốn email bằng chuỗi rỗng, phải biểu diễn phép so sánh phù hợp và phân biệt với email null.

Tương tự, `Containing` trên một collection được hỗ trợ có thể mang ý nghĩa thành viên của collection, không phải tìm chuỗi con trong biểu diễn văn bản của collection.

## 7. Ví dụ MongoDB: Regex và Exists có ngữ nghĩa riêng

Giả sử `MongoCustomer` là document có mapping phù hợp, trong đó `email` là trường chuỗi:

```java
import java.util.List;

import org.springframework.data.mongodb.repository.MongoRepository;

interface MongoCustomerRepository
        extends MongoRepository<MongoCustomer, String> {

    List<MongoCustomer> findByEmailRegex(String pattern);

    List<MongoCustomer> findByEmailExists(boolean exists);

    boolean existsByEmail(String email);
}
```

### 7.1. Exists ở chủ đề khác Exists ở điều kiện

So sánh:

```java
repository.existsByEmail("ann@example.com");
repository.findByEmailExists(true);
```

Lời gọi thứ nhất hỏi: “Có document nào có email bằng giá trị đã cho không?”

Lời gọi thứ hai hỏi: “Những document nào có trường email tồn tại?”

Dữ liệu ví dụ:

```javascript
{ "_id": "c1", "email": "ann@example.com" }
{ "_id": "c2", "email": null }
{ "_id": "c3" }
```

Với ngữ nghĩa tồn tại trường của MongoDB:

- Điều kiện email tồn tại bao gồm cả `c1` và `c2`.
- Điều kiện đó không bao gồm `c3`.
- `existsByEmail("ann@example.com")` tìm sự tồn tại của document thỏa giá trị, không phải sự tồn tại của mọi trường email.

Không chuyển `findByEmailExists(true)` thành `findByEmailIsNotNull()` rồi coi chúng luôn tương đương. Trường có giá trị null vẫn là trường tồn tại.

### 7.2. Regex không phải phép tìm literal mặc định

Khi chọn `Regex`, đầu vào có ngữ nghĩa của mẫu regex. Các ký tự như `.`, `*`, `^`, `$` không chỉ là ký tự văn bản.

Nếu yêu cầu là tìm một đoạn văn bản người dùng nhập, hãy xác định rõ có cho phép cú pháp regex không. Không thay `Containing` bằng `Regex` chỉ vì cả hai có thể tìm chuỗi.

Cũng không thay cú pháp SQL LIKE với `%`, `_` bằng cú pháp regex một cách máy móc. Hành vi tìm kiếm cần được thiết kế theo toán tử thực sự được chọn.

### 7.3. Near và Within cần đúng điều kiện không gian

Việc module có từ khóa địa lý chưa đủ để một phương thức bất kỳ hoạt động. Cần xem:

- Thuộc tính lưu vị trí và kiểu geometry nào.
- Toán tử được tạo và hệ tọa độ được dùng.
- Tham số khoảng cách, đơn vị và kiểu kết quả.
- Yêu cầu index, đặc biệt với các phép near cần index địa lý phù hợp.

Không có đường tắt từ “Commons liệt kê Near” tới “mọi repository dùng được Near trên mọi trường”.

## 8. Cassandra: hỗ trợ toán tử vẫn phải khớp mô hình khóa

Cassandra cho thấy rõ khoảng cách giữa “toán tử có thể dịch” và “query hợp lệ cho cách tổ chức dữ liệu”.

Giả sử bảng được thiết kế như sau:

```sql
CREATE TABLE event_by_tenant (
    tenant_id text,
    created_at timestamp,
    event_id uuid,
    description text,
    PRIMARY KEY (tenant_id, created_at, event_id)
);
```

Giả sử domain ánh xạ trực tiếp các thuộc tính `tenantId`, `createdAt`, `eventId` vào các cột tương ứng. Một phương thức minh họa trong Cassandra repository:

```java
List<TenantEvent> findByTenantIdAndCreatedAtGreaterThanEqual(
    String tenantId,
    Instant createdFrom
);
```

Ý định tương ứng với điều kiện CQL:

```sql
WHERE tenant_id = ? AND created_at >= ?
```

Các bind marker trên mô tả CQL prepared statement, không phải một chuỗi annotation dùng chung cho mọi module.

Ở đây, điều kiện cung cấp partition key `tenant_id` và giới hạn trên clustering column `created_at`. Nếu entity dùng một đối tượng khóa lồng nhau thay vì các thuộc tính trực tiếp, tên đường dẫn phương thức cũng phải phù hợp mô hình Java đó.

### 8.1. Bỏ partition key không phải chỉ đổi tên phương thức

Không thể kết luận rằng:

```java
List<TenantEvent> findByCreatedAtGreaterThanEqual(Instant createdFrom);
```

sẽ là một truy vấn truy cập hợp lệ và hiệu quả như phương thức có tenant. Cùng từ khóa `GreaterThanEqual` nhưng phạm vi truy cập dữ liệu đã khác.

Nếu use case cần đọc theo thời gian trên nhiều tenant, phải xem lại thiết kế bảng, phương án truy vấn và giới hạn vận hành. Không mặc định thêm cơ chế filtering sẽ sửa được thiết kế.

### 8.2. And và Or không phải khả năng đối xứng ở mọi store

Commons biết cách tách cả `And` và `Or`. CQL không có phép `OR` tổng quát như SQL, nên không suy rằng một phương thức Cassandra có `Or` được hỗ trợ chỉ vì phương thức tương tự trong JPA hoạt động.

Các toán tử chuỗi của store quan hệ cũng không tự trở thành phép tìm kiếm chuỗi portable trên Cassandra. Cần đối chiếu bảng keyword của module và mô hình truy cập mà Cassandra cho phép.

## 9. Redis: index repository không phải toàn bộ khả năng của Redis

Một Redis server có nhiều cấu trúc dữ liệu và lệnh. Redis repository của Spring Data chỉ cung cấp một tập khả năng suy diễn dựa trên cơ chế mà module triển khai, đặc biệt là các index repository.

Ví dụ đơn giản:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
class RedisCustomer {
    @Id
    String id;

    @Indexed
    String tenantId;

    @Indexed
    String email;
}
```

Repository:

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

interface RedisCustomerRepository
        extends CrudRepository<RedisCustomer, String> {

    List<RedisCustomer> findByTenantIdAndEmail(
        String tenantId,
        String email
    );
}
```

Ví dụ giả định repository scanning và hạ tầng Redis đã cấu hình, dữ liệu được ghi theo cơ chế duy trì index của repository.

Điều cần đối chiếu không chỉ là phép bằng và `And`, mà còn là hai trường đã có index thích hợp. Không suy rằng module tự quét mọi key để bù cho việc thiếu index.

### 9.1. Không lấy GreaterThan hoặc Regex từ Commons rồi áp dụng tùy ý

Redis repository thông thường không tự cung cấp một ngôn ngữ range/regex đầy đủ chỉ vì Commons nhận diện các loại điều kiện này. Ví dụ, một nhu cầu xếp hạng theo điểm có thể phù hợp với sorted set và một phần triển khai riêng hơn là phương thức `findByScoreGreaterThan(...)` suy diễn từ index bằng.

Nếu dùng một tính năng tìm kiếm bổ sung của hệ sinh thái Redis hoặc một fragment tự viết, phải chỉ rõ đó là cơ chế khác với bộ suy diễn repository mặc định.

Thông điệp quan trọng: **khả năng của server, khả năng của client/template và khả năng derived query là ba phạm vi liên quan nhưng khác nhau.**

## 10. JDBC/R2DBC, Neo4j và Elasticsearch cũng cần đối chiếu riêng

Không thể rút ra danh sách hỗ trợ từ việc store có một toán tử trong ngôn ngữ gốc.

| Module | Suy luận cần tránh | Điều phải đối chiếu |
|---|---|---|
| JDBC | Database có hàm regex nên derived query chắc hỗ trợ `Regex` | Bộ query derivation của Spring Data JDBC, dialect và kiểu thuộc tính |
| R2DBC | Cùng SQL với JDBC nên mọi keyword và kiểu trả về giống nhau | Module R2DBC, driver, cơ chế truy vấn và hợp đồng reactive |
| Neo4j | Cypher biểu diễn được một điều kiện nên tên phương thức bất kỳ sẽ được dịch | Query creator của Spring Data Neo4j, node/relationship và kiểu tham số |
| Elasticsearch | Query DSL có nhiều loại query nên mọi keyword Commons đều dùng được | Bảng keyword module, index mapping, analyzer và loại query thực tế |

Ví dụ, trong Elasticsearch, tìm theo trường `text` có analyzer và trường `keyword` có mục đích khác nhau. Không lấy kết quả đúng trên một mapping làm bằng chứng cho mọi mapping cùng tên thuộc tính.

Trong Neo4j, một đường dẫn qua relationship không chỉ là phép nối tên field Java. Nó còn phụ thuộc cách domain được ánh xạ vào graph và khả năng suy diễn của module.

Với JDBC/R2DBC, việc SQL khai báo có thể viết một phép join không chứng minh derived query sẽ tự xây cùng phép join khi đi qua đối tượng lồng nhau.

## 11. Quy trình đối chiếu theo đúng dự án

### Bước 1: Xác định module thực sự tạo repository

Đừng chỉ nhìn việc interface kế thừa `Repository` hoặc `CrudRepository`. Cần biết repository factory nào quản lý interface đó và domain được mapping vào store nào.

Những dấu hiệu cần xem trong một dự án gồm dependency, cấu hình repository scanning, interface cha đặc thù và annotation mapping domain. Trong ứng dụng nhiều store, repository có thể cần được phân vùng rõ để tránh gán nhầm module.

### Bước 2: Xác định phiên bản được sử dụng

Dùng phiên bản dependency đã được resolve trong dự án, kể cả khi được quản lý gián tiếp bởi một BOM. Không lấy tài liệu mới nhất trên mạng rồi mặc định nó khớp với ứng dụng.

Cần phân biệt ít nhất:

- Phiên bản Spring Data Commons.
- Phiên bản module store.
- Phiên bản driver/provider và server khi có giới hạn liên quan.

Một tính năng xuất hiện trong enum hoặc tài liệu của bản khác chưa chứng minh nó có trong môi trường hiện tại.

### Bước 3: Đọc đúng hai lớp tài liệu

Đối chiếu:

1. Danh sách keyword chung của Spring Data: giúp hiểu parser nhận diện gì.
2. Mục query methods/query creation và bảng keyword của module store đúng phiên bản: giúp biết những gì được triển khai.

Đồng thời xem ghi chú về kiểu tham số, giới hạn sorting/pagination và toán tử theo kiểu dữ liệu.

Nếu bảng không liệt kê một tổ hợp, đừng tự coi nó được hỗ trợ chỉ vì các thành phần xuất hiện ở nơi khác. Cần tìm giới hạn hoặc ví dụ tương ứng, rồi kiểm chứng ở đúng cấu hình trước khi dùng làm hợp đồng ứng dụng.

### Bước 4: Lập bảng cho các phương thức thật sự cần

Ví dụ cách ghi nhận, không phải ma trận hỗ trợ toàn bộ hệ sinh thái:

| Phương thức/use case | Module | Toán tử cần đối chiếu | Ràng buộc thêm | Kết luận thiết kế |
|---|---|---|---|---|
| Tìm email chứa đoạn văn bản | JPA | `Containing`, `IgnoreCase` | Thuộc tính chuỗi, quy tắc case/index | Có thể dùng derived query phù hợp |
| Tìm email theo regex | JPA | `Regex` | JPA derived query thông thường không triển khai | Chọn truy vấn đặc thù hoặc fragment nếu cần |
| Tìm document có trường email | MongoDB | `Exists` | Phân biệt trường thiếu và null | Dùng đúng điều kiện tồn tại trường |
| Đọc sự kiện tenant từ một thời điểm | Cassandra | `And`, `GreaterThanEqual` | Partition/clustering key | Dùng bảng phục vụ đường truy cập |
| Tìm khách hàng theo tenant và email | Redis | Bằng, `And` | Index repository trên hai trường | Bảo đảm mapping và index tương ứng |

Với dự án cụ thể, bổ sung phiên bản và căn cứ kiểm chứng. Không cần xây một bảng khổng lồ cho những toán tử ứng dụng không sử dụng.

### Bước 5: Kiểm chứng tên và hành vi ở hai mức

Ở mức parser, có thể quan sát `PartTree` để biết đường dẫn và `Part.Type`. Đây là kiểm tra cách tên được hiểu.

Ở mức module/store, cần kiểm chứng phương thức thực tế với mapping và dữ liệu đại diện. Một mock repository trả về dữ liệu được lập trình sẵn không kiểm tra được query creator có hỗ trợ toán tử hay không.

Những dữ liệu hữu ích gồm:

- Một giá trị khớp và một giá trị gần giống nhưng không được phép khớp.
- Khác biệt hoa/thường nếu có `IgnoreCase`.
- Chuỗi có ký tự đặc biệt nếu có phép tìm mẫu.
- Null và trường thiếu nếu store có sự phân biệt.
- Dữ liệu khác tenant hoặc partition.
- Nhiều bản ghi cùng giá trị sắp xếp nếu có giới hạn hoặc phân trang.

Các kiểm chứng này cần được thực hiện trong dự án sử dụng thực tế; việc đọc tên phương thức trong tài liệu không thay thế cho chúng.

## 12. Chọn cách xử lý khi keyword không được triển khai

Không có một cách sửa áp dụng cho mọi trường hợp.

| Nguyên nhân | Hướng xử lý phù hợp |
|---|---|
| Sai tên thuộc tính hoặc sai ranh giới | Sửa đường dẫn, có thể dùng `_` để chỉ rõ |
| Sai kiểu hoặc số tham số | Sửa chữ ký theo hợp đồng toán tử |
| Module không triển khai toán tử | Đổi cách diễn đạt nghiệp vụ hoặc chọn cơ chế truy vấn khác |
| Store không cho phép đường truy cập hiện tại | Xem lại schema, index, khóa hoặc mô hình dữ liệu |
| Query chạy nhưng khác ngữ nghĩa mong muốn | Làm rõ toán tử, null, case, collection và mapping |
| Tổ hợp quá phức tạp cho tên phương thức | Dùng API dựng truy vấn hoặc repository fragment |

### 12.1. Truy vấn khai báo có thể giải quyết một use case cụ thể

Nếu module hỗ trợ, có thể viết truy vấn khai báo bằng annotation hoặc named query thích hợp. Khi đó cần tôn trọng ngôn ngữ và cách bind riêng: JPQL/SQL, bộ lọc MongoDB, CQL, Cypher hoặc Query DSL không phải một ngôn ngữ chung.

Việc dùng truy vấn khai báo không bổ sung toán tử mới vào bộ suy diễn. Nó lựa chọn một cách triển khai khác cho phương thức.

Không mặc định module sẽ tự fallback sang full scan hoặc một truy vấn tương đương khi gặp keyword không được hỗ trợ.

### 12.2. Fragment phù hợp khi cần khả năng đặc thù

Ví dụ:

- Dùng một hàm regex native của hệ quản trị quan hệ.
- Xây pipeline MongoDB hoặc điều kiện cùng phần tử trong mảng.
- Truy cập Redis sorted set theo khoảng điểm.
- Tạo một truy vấn graph hoặc tìm kiếm có cấu trúc riêng.

Trong những trường hợp này, fragment giữ phần triển khai đặc thù ở nơi có thể kiểm soát, thay vì buộc tên phương thức thể hiện một hợp đồng mà store không cung cấp.

## 13. Không biến interface chung thành cam kết hỗ trợ giả

Xét một interface cơ sở:

```java
import java.util.List;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
interface UniversalCustomerRepository<T, ID>
        extends Repository<T, ID> {

    List<T> findByEmailRegex(String pattern);
}
```

Ngay cả khi mọi kiểu `T` đều có thuộc tính `email`, interface trên vẫn áp đặt yêu cầu regex lên mọi module kế thừa nó. Một repository MongoDB có thể phù hợp, còn một repository JPA thông thường không có triển khai suy diễn tương ứng.

`@NoRepositoryBean` ngăn việc tạo repository trực tiếp cho interface cơ sở; nó không biến từ khóa của interface thành khả năng portable.

Nếu ứng dụng cần thay store, có thể định nghĩa một hợp đồng nghiệp vụ ở lớp ứng dụng:

```java
interface CustomerLookup {
    List<CustomerSummary> searchByLiteralEmailFragment(String fragment);

    boolean hasExactEmail(String email);
}
```

Đây là API ứng dụng, không kế thừa `Repository` và không được kỳ vọng tự sinh query từ tên. Mỗi implementation gọi repository hoặc client cụ thể.

Điều cần thống nhất là nghĩa của “literal fragment”, quy tắc case, dữ liệu null và dạng kết quả. Hai implementation có thể dùng công cụ khác nhau, nhưng phải đáp ứng cùng những ví dụ nghiệp vụ.

Nếu yêu cầu thật sự là regex, hãy ghi rõ hợp đồng regex và giới hạn của nó. Không thay âm thầm bằng tìm chuỗi con khi store mới không cung cấp khả năng tương đương.

## 14. Chẩn đoán lỗi và những kết luận dễ nhầm

| Hiện tượng | Kết luận cần tránh | Kiểm tra tiếp |
|---|---|---|
| `PartTree` parse thành công | Store chắc chắn hỗ trợ | Query creator của module |
| Không tìm được property | Keyword chắc chưa triển khai | Đường dẫn domain và thứ tự nhận diện tên |
| Lỗi keyword không được hỗ trợ | Đổi alias chắc sẽ được | Các alias có cùng `Part.Type` không |
| Repository khởi tạo được | Mọi biến thể đều đúng | Thời điểm tạo query và lời gọi thực tế |
| Query chạy nhưng thiếu kết quả | Chỉ có thể do sai dữ liệu | Case, null, mapping, kiểu tham số |
| Query hợp lệ nhưng rất chậm | Keyword dùng được nên index không quan trọng | Kế hoạch truy cập, index và lượng dữ liệu |
| Engine có một toán tử | Repository sẽ tự tạo được toán tử đó | Phạm vi API derivation của module |
| Derived delete hoạt động | Có cùng lifecycle và transaction như mọi bulk delete | Cách module thực thi thao tác xóa |

Một lỗi từ store có thể được bọc bởi lỗi tạo repository hoặc tạo query. Đọc nguyên nhân bên trong giúp phân biệt lỗi cú pháp tên, đường dẫn, toán tử chưa triển khai và query bị hệ thống lưu trữ từ chối.

### 14.1. Top/First không bảo đảm thứ tự nếu thiếu OrderBy

Giới hạn số lượng và sắp xếp là hai yêu cầu riêng. Một phương thức lấy `Top5` nhưng không có thứ tự được xác định không nên được giải thích là “năm bản ghi mới nhất”.

Muốn lấy bản ghi mới nhất, cần thứ tự theo thời điểm và có thể cần thêm thuộc tính phân xử khi nhiều bản ghi có cùng thời điểm. Module và store phải hỗ trợ cách áp dụng thứ tự đó.

### 14.2. Distinct không tự chọn giá trị nghiệp vụ cần loại trùng

Một yêu cầu “đếm khách hàng khác nhau” khác với “đếm email khác nhau”. Hậu tố/phần chủ đề `Distinct` không thay thế việc xác định projection hay biểu thức đếm.

Cần kiểm tra module tạo distinct trên đối tượng gốc, định danh hay tập cột/giá trị nào. Đừng suy ra ngữ nghĩa đếm một trường chỉ bằng cách thấy từ `Distinct` trong tên.

### 14.3. Hỗ trợ không phải đánh giá về hiệu năng

Một truy vấn regex hoặc tìm chuỗi con có thể được module hỗ trợ nhưng không dùng index theo cách ứng dụng kỳ vọng. Hỗ trợ chức năng, độ đúng của kết quả và chi phí thực thi cần được đánh giá riêng.

## 15. Bài tập vận dụng

### Bài tập 1: Commons nhận diện, JPA từ chối

Một phương thức JPA `findByEmailRegex(String pattern)` được `PartTree` nhận diện thành `REGEX`. Có mâu thuẫn khi repository không tạo được truy vấn không?

**Gợi ý lời giải:** Không. Commons nhận diện bộ từ vựng chung, còn JPA query creator chỉ triển khai một tập điều kiện. Cần dùng một khả năng được module hỗ trợ hoặc một cách triển khai truy vấn đặc thù.

### Bài tập 2: Phân biệt hai loại Exists

Với ba document:

```javascript
{ "_id": "1", "email": "a@example.com" }
{ "_id": "2", "email": null }
{ "_id": "3" }
```

So sánh `existsByEmail("a@example.com")` với `findByEmailExists(true)`.

**Gợi ý lời giải:** Phương thức đầu trả lời có document khớp giá trị email. Phương thức sau trả về những document có trường email; với ngữ nghĩa tồn tại trường, document `1` và `2` đều đáp ứng. Không đồng nhất tồn tại trường với giá trị khác null.

### Bài tập 3: Cùng một keyword, khác đường truy cập

Với bảng `event_by_tenant`, tại sao phương thức có `TenantIdAndCreatedAtGreaterThanEqual` không chứng minh phương thức chỉ có `CreatedAtGreaterThanEqual` cũng phù hợp?

**Gợi ý lời giải:** Phương thức đầu cung cấp partition key và giới hạn clustering column. Phương thức sau bỏ phạm vi partition. Khả năng dịch phép so sánh không sửa được mô hình truy cập của Cassandra.

### Bài tập 4: Chọn keyword theo kiểu thuộc tính

Trong JPA, entity có `orders` là collection và `email` là chuỗi. Có thể dùng `IsEmpty` trên cả hai để kiểm tra “không có dữ liệu” không?

**Gợi ý lời giải:** Không. Kiểm tra collection rỗng là một hợp đồng khác với chuỗi rỗng hoặc null. Cần dùng toán tử đúng kiểu và đúng mục đích nghiệp vụ.

### Bài tập 5: Chuyển một repository sang Redis

Một interface dùng `findByScoreGreaterThan(...)` ở store cũ. Chuyển sang Redis repository có tự hoạt động vì Commons biết `GreaterThan` không?

**Gợi ý lời giải:** Không. Cần đối chiếu cơ chế index và danh sách suy diễn thực tế của Redis repository. Nếu use case là truy vấn khoảng điểm, một thiết kế với sorted set cùng phần triển khai riêng có thể phù hợp hơn.

### Bài tập 6: Đánh giá một tuyên bố hỗ trợ

Một đồng nghiệp nói: “Tài liệu Spring Data có `Within`, nên repository nào cũng dùng được.”

**Gợi ý lời giải:** Hỏi lại module và phiên bản cụ thể, kiểu thuộc tính không gian, kiểu tham số, toán tử được tạo và yêu cầu index. Danh sách chung không phải chứng nhận cho từng store.

## 16. Những điều cần ghi nhớ

- Danh sách keyword Commons là bộ từ vựng chung; danh sách module cho biết phần nào được triển khai.
- Tách riêng chủ đề, điều kiện, modifier, đường dẫn và kiểu trả về khi đối chiếu.
- Parse thành công chưa chứng minh query creator và store chấp nhận phương thức.
- `existsBy...` hỏi về kết quả thỏa điều kiện; `...Exists` có thể là toán tử kiểm tra sự hiện diện của trường trong module hỗ trợ.
- Cùng keyword vẫn có thể khác ngữ nghĩa theo kiểu thuộc tính, mapping, null, case và collection.
- Đối chiếu đúng phiên bản cùng schema/index/khóa của dự án; không lấy khả năng của server làm bằng chứng cho khả năng suy diễn.
- Khi derived query không đáp ứng, chọn truy vấn khai báo, API của store hoặc fragment với hợp đồng nghiệp vụ rõ ràng.
