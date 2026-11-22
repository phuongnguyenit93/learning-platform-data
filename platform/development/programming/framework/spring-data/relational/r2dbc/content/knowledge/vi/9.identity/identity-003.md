# Ảnh hưởng của kiểu nguyên thủy, kiểu bao và giá trị null đến định danh

Trong Spring Data Relational R2DBC, kiểu Java của thuộc tính định danh ảnh hưởng trực tiếp đến cách ứng dụng biểu diễn một entity mới, cách Spring Data quyết định thực hiện INSERT hay UPDATE và cách giá trị được ánh xạ với cột database. Sự khác biệt giữa kiểu nguyên thủy như `long` và kiểu bao như `Long` đặc biệt quan trọng vì kiểu nguyên thủy luôn có giá trị mặc định, trong khi kiểu bao có thể là `null`.

Với một khóa chính do database tự sinh, `Long id` thường là lựa chọn dễ hiểu: entity mới có `id == null`; sau khi INSERT thành công, Spring Data nhận định danh được sinh và gán lại vào entity. Với `long id`, giá trị mặc định là `0`, nên Spring Data phải dùng quy ước giá trị 0 như dấu hiệu entity mới trong chiến lược mặc định dành cho thuộc tính định danh kiểu nguyên thủy. Quy ước này có giới hạn nếu 0 là một định danh hợp lệ hoặc nếu ứng dụng tự gán ID.

## 1. Định danh trong entity Spring Data Relational

Một entity thường có thuộc tính được đánh dấu bằng `@Id` để Spring Data xác định cột định danh:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;
}
```

`@Id` ở đây là annotation của Spring Data (`org.springframework.data.annotation.Id`). Nó cho mapping layer biết thuộc tính nào đại diện cho định danh của hàng trong bảng. Khi repository thực hiện `save`, Spring Data cần biết entity đã tồn tại hay vẫn là entity mới để chọn thao tác lưu thích hợp.

Với `ReactiveCrudRepository`, API lưu có dạng:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

```java
Mono<Customer> result = customerRepository.save(customer);
```

`save` không đơn giản luôn luôn là INSERT hoặc luôn luôn là UPDATE. Spring Data kiểm tra trạng thái mới/cũ của entity theo chiến lược nhận diện newness. Kiểu định danh, giá trị hiện tại của nó và thuộc tính `@Version` nếu có đều có thể ảnh hưởng đến quyết định đó.

## 2. Kiểu nguyên thủy và kiểu bao trong Java

Java có các kiểu nguyên thủy như `byte`, `short`, `int`, `long`, `float`, `double`, `boolean` và `char`. Mỗi kiểu có giá trị mặc định khi field chưa được gán:

| Kiểu nguyên thủy | Giá trị mặc định của field |
|---|---:|
| `byte` | `0` |
| `short` | `0` |
| `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `boolean` | `false` |
| `char` | `\u0000` |

Kiểu bao (wrapper) tương ứng là `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `Boolean` và `Character`. Chúng là object reference nên có thể mang giá trị `null`.

```java
private long primitiveId;  // Mặc định là 0L
private Long wrapperId;    // Mặc định là null

private int primitiveAge; // Mặc định là 0
private Integer age;      // Mặc định là null
```

Sự khác nhau này quan trọng khi một giá trị chưa được cung cấp cần được phân biệt với một giá trị hợp lệ bằng 0 hoặc `false`.

## 3. Vì sao Long thường phù hợp với ID tự sinh?

Với cột khóa chính được database tạo tự động, entity thường chưa có ID trước khi INSERT. `Long` biểu diễn trạng thái này tự nhiên:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }
}
```

Khi tạo mới:

```java
Customer customer = new Customer("An");
// customer.getId() == null
```

Giá trị `null` cho biết ứng dụng chưa có định danh. Theo chiến lược mặc định khi không có thuộc tính version, Spring Data xem entity có ID null là entity mới. Repository có thể thực hiện INSERT; nếu database tạo ID, R2DBC driver và Spring Data có thể lấy giá trị được sinh và gán lại vào entity trả về.

```java
Mono<Customer> saved = customerRepository.save(customer)
    .doOnNext(value -> {
    // Sau khi INSERT thành công, value.getId() có thể chứa ID do database sinh.
    System.out.println(value.getId());
    });
```

Publisher là lazy: thao tác lưu chỉ được thực thi khi có subscriber. Vì vậy, cần compose `save` vào reactive pipeline hoặc để framework subscribe; không nên đọc ID ngay sau khi gọi `save` mà chưa có kết quả hoàn tất.

`Long` không có nghĩa database cho phép khóa chính null. Giá trị null là trạng thái ở phía object trước khi lưu. Database vẫn có thể khai báo cột ID là `PRIMARY KEY` và `NOT NULL`; database tạo giá trị thật trong lúc INSERT.

## 4. Hành vi mặc định khi xác định entity mới

Spring Data cần một quy tắc để phân biệt entity mới và entity đã được lưu. Với chiến lược mặc định dựa trên metadata, có hai điểm cần hiểu:

1. Nếu entity có thuộc tính `@Version`, thuộc tính version được ưu tiên để xác định newness.
2. Nếu không có version property, Spring Data xét thuộc tính định danh.

Với thuộc tính được dùng để xác định newness:

- Giá trị `null` được xem là dấu hiệu entity mới.
- Nếu kiểu thuộc tính là kiểu nguyên thủy số, giá trị mặc định `0` được dùng làm dấu hiệu entity mới.
- Với kiểu tham chiếu không null, Spring Data mặc định xem giá trị đó là dấu hiệu entity đã tồn tại.

Điểm thứ hai giải thích vì sao `long` và `Long` có thể dẫn đến kết quả khác nhau khi cùng mang giá trị số 0.

### 4.1. Bảng so sánh ID primitive và wrapper

Giả sử entity không có thuộc tính `@Version` và dùng chiến lược newness mặc định:

| Khai báo ID | Giá trị hiện tại | Diễn giải mặc định |
|---|---:|---|
| `long id` | `0L` | Entity mới theo quy ước primitive numeric zero |
| `long id` | `25L` | Entity đã tồn tại |
| `Long id` | `null` | Entity mới |
| `Long id` | `25L` | Entity đã tồn tại |
| `Long id` | `0L` | Giá trị khác null, mặc định được xem là entity đã tồn tại |

Đây là quy tắc nhận diện entity của Spring Data, không phải quy tắc SQL. Database không hiểu rằng số 0 có nghĩa là entity mới; đó là quyết định ở tầng persistence trước khi câu lệnh được tạo.

### 4.2. Vì sao Long bằng 0 khác long bằng 0?

Hai khai báo sau có cùng giá trị số học nhưng khác kiểu:

```java
long primitiveId = 0L;
Long wrapperId = 0L;
```

Với `long`, Spring Data có thể nhận biết đây là kiểu nguyên thủy và áp dụng quy ước zero-value. Với `Long`, `0L` là một object không null, do đó chiến lược mặc định dựa trên ID xem nó như một định danh đã có.

Điều này có thể gây bất ngờ nếu ứng dụng tạo entity mới bằng `new Customer(0L, ...)` với field kiểu `Long`. Nếu ID là do database tự sinh, hãy để wrapper ở trạng thái null thay vì gán 0.

## 5. ID primitive có những giới hạn gì?

Ví dụ:

```java
@Table("customer")
public class Customer {

    @Id
    private long id;

    private String name;
}
```

Khi tạo object mới, `id` mặc định bằng `0`. Spring Data có thể dùng giá trị đó để nhận diện entity mới. Cách làm này có thể hoạt động khi hệ thống quy ước 0 không bao giờ là ID hợp lệ và database tạo các ID dương.

Nhưng có các giới hạn:

- Không thể biểu diễn trạng thái chưa có ID bằng `null`.
- Không phân biệt được ID chưa được cấp với ID thực sự bằng 0.
- Nếu ứng dụng dùng khóa tự gán và 0 là giá trị hợp lệ, chiến lược mặc định có thể coi entity là mới.
- Nếu code vô tình gán 0 cho một entity đã tồn tại, `save` có thể đi theo nhánh INSERT thay vì UPDATE.
- Khi ánh xạ cột nullable vào field primitive, Java không thể giữ lại trạng thái SQL NULL.

Vì vậy, với ID được database sinh tự động, kiểu bao `Long` thường biểu đạt ý định rõ hơn. Dùng primitive chỉ khi quy ước ID và chiến lược newness của ứng dụng thực sự phù hợp.

## 6. Giá trị null và cột database nullable

Giá trị `null` trong Java và SQL `NULL` có liên hệ nhưng không hoàn toàn đồng nhất với trạng thái entity mới.

- `null` trong Java là một object reference không trỏ đến object nào.
- `NULL` trong SQL biểu diễn giá trị chưa biết hoặc không có giá trị trong một cột.
- ID null trong entity thường được Spring Data dùng làm dấu hiệu entity mới.
- Cột khóa chính trong database thông thường không được phép chứa SQL NULL.

Một field wrapper có thể biểu diễn cả giá trị cụ thể và trạng thái chưa có giá trị:

```java
private Integer retryCount; // Có thể null, 0, 1, 2, ...
private Boolean verified;   // Có thể null, true hoặc false
```

Trong khi đó:

```java
private int retryCount;     // Không thể là null
private boolean verified;   // Không thể là null
```

Nếu cột database cho phép NULL và nghiệp vụ cần phân biệt “chưa xác định” với 0 hoặc false, hãy dùng kiểu bao. Ví dụ `verified = null` có thể có nghĩa chưa kiểm tra, `false` là đã kiểm tra và chưa xác minh, còn `true` là đã xác minh.

Với field primitive, Java không có trạng thái null. Tùy đường mapping và converter, giá trị SQL NULL có thể được chuyển thành giá trị mặc định hoặc gây lỗi khi gán/chuyển đổi. Không nên dựa vào hành vi mặc định đó để biểu diễn nghiệp vụ. Hãy dùng wrapper hoặc quy định cột là NOT NULL với giá trị mặc định phù hợp.

## 7. Null không đồng nghĩa với zero

Trong Java:

```java
Long idA = null;
Long idB = 0L;

System.out.println(idA == null); // true
System.out.println(idB == null); // false
```

Trong SQL, `NULL` cũng không bằng 0. Điều kiện `column = NULL` không kiểm tra được giá trị null vì SQL dùng logic ba giá trị. Cần dùng `IS NULL`:

```sql
SELECT id, name
FROM customer
WHERE external_code IS NULL;
```

Không viết:

```sql
-- Không phải cách kiểm tra SQL NULL.
SELECT id, name
FROM customer
WHERE external_code = NULL;
```

Nếu dùng `DatabaseClient` để bind một tham số null, cần chỉ rõ kiểu Java cho driver:

```java
databaseClient.sql("""
        SELECT id, name
        FROM customer
        WHERE external_code IS NULL
        """)
    .map((row, metadata) -> {
        Customer customer = new Customer(row.get("name", String.class));
        customer.setId(row.get("id", Long.class));
        return customer;
    })
    .all();
```

Nếu thực sự cần bind null trong một biểu thức SQL, có thể dùng `bindNull("parameter", String.class)` với kiểu tương ứng. Tuy nhiên, với điều kiện lọc null, `IS NULL` thường là cách rõ ràng nhất. Việc dùng `column = :value` với value null không có cùng ý nghĩa với `column IS NULL`.

## 8. Kiểu bao không tự động có nghĩa là ID được sinh

`Long id` có thể null, nhưng chỉ riêng kiểu dữ liệu không khiến database tự sinh ID. Việc sinh ID phụ thuộc schema, chiến lược ID của database, driver và thao tác INSERT.

Ví dụ bảng PostgreSQL:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
```

Entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;
}
```

Khi ID là null và entity được nhận diện là mới, Spring Data R2DBC có thể thực hiện INSERT theo cơ chế generated values của driver/database và cập nhật ID vào entity trả về.

```java
Mono<Customer> create(String name) {
    Customer customer = new Customer(name);

    return customerRepository.save(customer)
        .doOnNext(saved -> {
            // ID được kiểm tra sau khi thao tác INSERT hoàn tất.
            System.out.println("Generated id: " + saved.getId());
        });
}
```

Không nên gán `0L` cho wrapper ID với ý định yêu cầu database tự sinh. Trong chiến lược mặc định, `Long` khác null có thể khiến entity được coi là đã tồn tại và đi theo nhánh UPDATE.

Ngoài ra, `@GeneratedValue` là annotation quen thuộc của JPA. Spring Data Relational R2DBC không dựa vào JPA `@GeneratedValue` để xác định việc sinh khóa theo cách JPA làm. Hãy dùng `@Id`, cấu hình schema và cơ chế generated values mà Spring Data R2DBC/driver hỗ trợ.

## 9. ID tự gán và ID do database sinh

Có hai cách phổ biến để cấp ID:

| Kiểu cấp ID | Ví dụ | Trạng thái entity mới |
|---|---|---|
| Database-generated | Identity/sequence do database cấp | ID thường null trước INSERT |
| Application-assigned | UUID hoặc mã nghiệp vụ được tạo ở ứng dụng | ID có thể đã có trước INSERT |

Với database-generated ID, `Long id = null` là cách tự nhiên. Với application-assigned ID, entity có thể có ID ngay khi được tạo. Theo chiến lược mặc định dựa trên ID, ID khác null có thể làm entity bị coi là đã tồn tại, dù bản ghi chưa từng được INSERT.

Ví dụ:

```java
@Table("external_customer")
public class ExternalCustomer {

    @Id
    private String id;

    private String name;
}
```

Nếu ứng dụng tạo UUID/string ID trước khi lưu, `id` đã khác null. Cần có cách xác định newness phù hợp để lần lưu đầu tiên thực hiện INSERT.

### 9.1. Dùng Persistable khi cần kiểm soát newness

Spring Data hỗ trợ `Persistable<ID>` để entity tự cung cấp trạng thái mới thông qua `isNew()`:

```java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("external_customer")
public class ExternalCustomer implements Persistable<String> {

    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

Khi entity được tạo mới trong ứng dụng, `newEntity` có thể là true để `save` chọn INSERT dù ID đã được gán. Sau khi INSERT thành công, ứng dụng cần chuyển cờ sang false. Khi entity được tải từ database, cờ cũng phải được thiết lập thành false thông qua factory hoặc lifecycle callback phù hợp. Nếu quên bước này, một entity đã đọc có thể tiếp tục báo `isNew() == true` và bị INSERT lại.

Ví dụ minh họa việc đánh dấu sau khi lưu thành công:

```java
Mono<ExternalCustomer> saveNew(ExternalCustomer customer) {
    return repository.save(customer)
        .doOnNext(ExternalCustomer::markPersisted);
}
```

Đoạn code chỉ xử lý cờ sau khi lưu. Trong ứng dụng hoàn chỉnh, cần bảo đảm entity được tạo từ dữ liệu database cũng được khởi tạo với `newEntity = false`, ví dụ qua cơ chế callback/factory phù hợp với phiên bản Spring Data Relational. `@Transient` bảo đảm cờ này không trở thành cột database.

Không nên triển khai `Persistable` nếu chiến lược ID mặc định đã biểu đạt đúng trạng thái entity. Đây là công cụ cho trường hợp ID được gán trước hoặc quy tắc newness của nghiệp vụ khác quy tắc mặc định.

## 10. Ảnh hưởng của @Version đến việc xác định entity mới

Nếu entity có thuộc tính `@Version`, Spring Data ưu tiên thuộc tính version khi xác định entity mới/cũ. Điều này quan trọng với optimistic locking và cả entity có ID tự gán.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;
}
```

Với version kiểu wrapper, `version == null` là dấu hiệu entity mới theo chiến lược mặc định. Sau khi lưu, Spring Data quản lý version theo cơ chế optimistic locking. Với version kiểu nguyên thủy, giá trị 0 là dấu hiệu mới theo quy ước primitive.

| Version property | Giá trị | Newness mặc định |
|---|---:|---|
| `Long version` | `null` | Mới |
| `Long version` | `0L` | Đã tồn tại theo phép kiểm tra null |
| `long version` | `0L` | Mới theo quy ước primitive |
| `long version` | `3L` | Đã tồn tại |

Khi có `@Version`, không nên chỉ nhìn vào ID để kết luận `save` sẽ INSERT hay UPDATE. Một entity có ID đã được gán vẫn có thể được coi là mới nếu version đang ở trạng thái biểu thị entity mới.

Với entity dùng optimistic locking, không tự ý đặt version tùy tiện. Hãy để Spring Data quản lý version theo quy tắc của mapping và database, đồng thời xử lý lỗi optimistic locking khi dữ liệu đã bị cập nhật bởi transaction khác.

## 11. Kiểu ID nào nên chọn?

Lựa chọn kiểu ID dựa trên cách cấp ID và quy tắc dữ liệu:

| Kiểu Java | Khả năng biểu diễn null | Thường phù hợp khi | Lưu ý |
|---|---|---|---|
| `Long` | Có | ID số do database sinh | Khuyến nghị phổ biến cho generated ID; null biểu thị chưa có ID |
| `long` | Không | Hệ thống dùng 0 làm sentinel và 0 không phải ID hợp lệ | Không phân biệt được null và zero |
| `Integer` | Có | ID số nhỏ hoặc trường số nullable | Có thể null trước khi insert |
| `int` | Không | Trường số luôn có giá trị và quy ước zero rõ ràng | Không phù hợp khi cần biểu diễn trạng thái chưa có |
| `UUID` | Có | ID được tạo ở ứng dụng hoặc database | ID thường đã có trước INSERT nếu ứng dụng tạo UUID |
| `String` | Có | Mã nghiệp vụ hoặc định danh dạng chuỗi | ID tự gán cần chiến lược newness phù hợp |

Đối với khóa chính số tự sinh, `Long` là lựa chọn dễ hiểu vì không cần quy ước zero. Đối với UUID, `UUID` thường rõ nghĩa hơn `String` nếu schema và driver hỗ trợ kiểu UUID. Đối với mã nghiệp vụ, `String` có thể phù hợp nhưng cần xử lý newness nếu mã được cấp trước khi lưu.

## 12. Wrapper và null cho các thuộc tính không phải ID

Khác biệt primitive/wrapper cũng ảnh hưởng các thuộc tính khác trong entity:

```java
private int retryCount;
private Integer retryLimit;
private boolean active;
private Boolean verified;
```

Các trường hợp có ý nghĩa khác nhau:

- `retryCount = 0`: số lần retry hiện tại bằng 0.
- `retryLimit = null`: chưa cấu hình giới hạn retry.
- `active = false`: trạng thái rõ ràng là không hoạt động.
- `verified = null`: chưa có kết luận xác minh.

Nếu nghiệp vụ cần phân biệt “chưa biết” với false, `Boolean` là phù hợp hơn `boolean`. Nếu cột `retry_limit` cho phép NULL, `Integer` giữ được sự khác biệt giữa chưa cấu hình và giới hạn bằng 0.

Ngược lại, nếu cột luôn `NOT NULL` và database có default rõ ràng, primitive có thể phù hợp. Kiểu Java và nullability của schema nên thống nhất với quy tắc nghiệp vụ, tránh để null hoặc giá trị mặc định xuất hiện một cách ngẫu nhiên.

## 13. Tương tác với DatabaseClient và bind null

Khi dùng repository hoặc `R2dbcEntityTemplate`, Spring Data mapping xử lý việc chuyển đổi thuộc tính entity sang giá trị database. Khi dùng `DatabaseClient`, ứng dụng tự bind tham số và cần xử lý null rõ ràng.

Ví dụ bind giá trị:

```java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
        INSERT INTO customer(name, external_code)
        VALUES (:name, :externalCode)
        """)
    .bind("name", name);

if (externalCode == null) {
    spec = spec.bindNull("externalCode", String.class);
} else {
    spec = spec.bind("externalCode", externalCode);
}

Mono<Long> inserted = spec.fetch().rowsUpdated();
```

R2DBC bind cần biết kiểu dữ liệu khi giá trị null. Không thể gọi `.bind("externalCode", null)` như một giá trị thông thường; dùng `.bindNull(...)` với kiểu phù hợp. Ví dụ này giả định cột `external_code` cho phép SQL NULL.

Nếu cột là khóa chính được database sinh, thông thường không cần bind null vào cột ID trong câu INSERT. Câu lệnh nên để database áp dụng cơ chế sinh ID, theo cú pháp mà database hỗ trợ. `@Id` trên entity và chiến lược insert của Spring Data có thể xử lý việc này trong repository/template.

## 14. Các lỗi thường gặp liên quan đến ID và null

| Lỗi | Vì sao xảy ra? | Cách xử lý |
|---|---|---|
| Dùng `long` cho ID nhưng cần phân biệt chưa cấp ID với ID 0 | Primitive không thể null | Dùng `Long` hoặc quy ước newness rõ ràng |
| Dùng `Long id = 0L` cho entity mới | Wrapper khác null nên mặc định có thể bị xem là entity cũ | Để ID null nếu database sinh khóa |
| Dùng ID tự gán nhưng không tùy chỉnh newness | ID khác null khiến entity bị xem là đã tồn tại | Dùng `Persistable` hoặc chiến lược version phù hợp |
| Coi `0` và `null` là giống nhau | Java và SQL phân biệt hai giá trị | Thiết kế kiểu dữ liệu và điều kiện SQL đúng ngữ nghĩa |
| Dùng primitive cho cột nullable | Primitive không thể giữ SQL NULL | Dùng wrapper hoặc đổi schema thành NOT NULL |
| Mong `@GeneratedValue` của JPA điều khiển R2DBC | Annotation thuộc Jakarta Persistence | Dùng `@Id`, schema và generated-value support của R2DBC |
| Đọc ID ngay sau khi gọi `save` | Reactive publisher chưa chắc đã được thực thi | Lấy ID từ entity phát ra sau khi save hoàn tất |
| Có `@Version` nhưng chỉ kiểm tra ID | Version được ưu tiên trong newness detection | Kiểm tra cả trạng thái version |
| Dùng `column = NULL` trong SQL | So sánh với NULL không cho kết quả true | Dùng `IS NULL` hoặc `IS NOT NULL` |
| Dùng `Persistable` nhưng không cập nhật cờ sau load/save | Entity cũ vẫn có thể báo `isNew()` | Quản lý cờ qua factory/callback/lifecycle phù hợp |

## 15. Ví dụ tổng hợp: ID database-generated và ID tự gán

### 15.1. ID database-generated

Schema:

```sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
```

Entity:

```java
@Table("product")
public class Product {

    @Id
    private Long id;

    private String name;

    public Product(String name) {
        this.name = name;
    }
}
```

Tạo mới và lưu:

```java
Mono<Product> createProduct(String name) {
    return productRepository.save(new Product(name));
}
```

Trạng thái ban đầu `id == null` giúp Spring Data nhận diện entity mới. Database cấp ID và kết quả lưu trả về entity có ID sau khi INSERT thành công.

### 15.2. ID được ứng dụng gán trước

Giả sử ứng dụng tạo mã `CUS-2026-001` trước khi lưu. ID khác null ngay từ đầu, nên cần xác định entity mới bằng một cơ chế khác nếu không có version property thích hợp.

```java
@Table("external_customer")
public class ExternalCustomer implements Persistable<String> {

    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        newEntity = false;
    }
}
```

Khi tạo object mới, `isNew()` trả về true. Sau khi lưu thành công, đánh dấu entity đã tồn tại. Khi tải entity từ database, cơ chế khởi tạo/callback cũng phải đặt `newEntity` thành false. Đây là trách nhiệm của cách triển khai `Persistable`, không tự xảy ra chỉ vì có `@Transient`.

## 16. Nguyên tắc thiết kế

- Với ID số do database tự sinh, ưu tiên wrapper như `Long` để biểu diễn trạng thái chưa có ID bằng null.
- Không dùng `0L` cho wrapper ID mới nếu đang dựa vào chiến lược newness mặc định.
- Chỉ dùng primitive ID khi quy ước zero-value là sentinel hợp lệ và không xung đột với dữ liệu thật.
- Phân biệt Java null, SQL NULL và giá trị số 0; chúng có ngữ nghĩa khác nhau.
- Dùng wrapper cho các cột nullable hoặc khi nghiệp vụ cần phân biệt “chưa biết” với giá trị mặc định.
- Nếu entity có `@Version`, xem xét version khi xác định newness vì version được ưu tiên trong chiến lược mặc định.
- Với ID tự gán, cân nhắc `Persistable<ID>` hoặc version property để kiểm soát entity mới/cũ.
- Nếu dùng `Persistable`, quản lý trạng thái `isNew` cả sau khi insert thành công và sau khi tải entity.
- Không dùng JPA `@GeneratedValue` như cơ chế sinh ID cho Spring Data Relational R2DBC.
- Với `DatabaseClient`, bind null bằng `bindNull` và kiểu dữ liệu phù hợp; trong SQL, dùng `IS NULL` để kiểm tra NULL.
- Kiểm tra hành vi save bằng integration test trên database và driver thực tế, bao gồm ID được sinh, ID tự gán, insert, update và optimistic locking.

Kiểu nguyên thủy và kiểu bao không chỉ là lựa chọn về cú pháp Java. Chúng quyết định khả năng biểu diễn null và có thể làm thay đổi cách Spring Data nhận diện entity mới. Khi chọn đúng kiểu ID, hiểu quy tắc version/newness và đồng bộ nullability giữa Java với schema, ứng dụng tránh được những lần INSERT/UPDATE sai nhánh, giữ đúng ý nghĩa của giá trị 0 và xử lý định danh do database hoặc ứng dụng cấp một cách rõ ràng.
