# Yêu cầu cột được sinh từ thao tác ghi

Khi ghi dữ liệu vào cơ sở dữ liệu quan hệ, không phải mọi giá trị của hàng đều do ứng dụng tự tạo. Database có thể tự sinh khóa chính identity, lấy giá trị từ sequence, điền thời điểm mặc định, tính một cột generated/computed hoặc bổ sung dữ liệu qua trigger. Sau thao tác `INSERT` hoặc `UPDATE`, ứng dụng đôi khi cần nhận lại những giá trị đó để trả response, tiếp tục xử lý nghiệp vụ hoặc cập nhật object trong bộ nhớ.

Với Spring Data R2DBC, cần phân biệt hai việc: **yêu cầu database trả các giá trị được sinh ra** và **ánh xạ các giá trị trả về vào entity/DTO**. Repository và `R2dbcEntityTemplate` hỗ trợ luồng generated ID thông thường. Với SQL trực tiếp qua `DatabaseClient`, có thể yêu cầu generated values qua R2DBC SPI hoặc dùng cú pháp riêng của database như `RETURNING` hay `OUTPUT`. Nếu driver không hỗ trợ trả về các cột cần thiết, ứng dụng phải đọc lại hàng sau khi ghi.

## 1. Những loại cột có thể được database sinh ra

Một thao tác ghi có thể tạo ra nhiều giá trị khác nhau:

| Loại giá trị | Cách database tạo | Ví dụ |
|---|---|---|
| Identity / auto-increment | Database cấp số mới khi insert | `id` tăng tự động |
| Sequence | Lấy số tiếp theo từ sequence | `nextval('person_id_seq')` trong PostgreSQL |
| Default value | Áp dụng biểu thức mặc định khi insert không cung cấp cột | `created_at DEFAULT CURRENT_TIMESTAMP` |
| Generated / computed column | Tính từ các cột khác theo biểu thức khai báo | `normalized_name GENERATED ALWAYS AS (lower(name))` |
| Trigger-generated value | Trigger thay đổi hoặc bổ sung dữ liệu trong thao tác ghi | Mã tham chiếu, thời điểm hoặc trạng thái được trigger gán |
| Giá trị do thao tác cập nhật tạo ra | Database tính lại cột trong `UPDATE` | `updated_at`, số dư hoặc cột computed |

Không phải mọi giá trị đều được trả về theo cùng một cơ chế. Khóa identity thường được driver hỗ trợ lấy lại qua generated values. Default, generated column và giá trị do trigger tạo ra có thể cần chỉ định tên cột rõ ràng hoặc dùng câu SQL có `RETURNING`/`OUTPUT`.

## 2. Phân biệt DEFAULT với generated/computed column

Hai khái niệm này thường bị nhầm:

**DEFAULT** cung cấp giá trị khi câu lệnh insert không đưa ra giá trị cho cột đó. Ứng dụng vẫn có thể chủ động cung cấp một giá trị khác nếu schema và quyền cho phép.

**Generated/computed column** được database tính từ biểu thức đã khai báo. Thông thường ứng dụng không được tự ghi giá trị vào cột này; database tự tính lại theo dữ liệu nguồn.

Ví dụ PostgreSQL:

```sql
CREATE TABLE person (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    normalized_name VARCHAR(200)
        GENERATED ALWAYS AS (lower(name)) STORED
);
```

Trong bảng này:

- `id` được database cấp khi insert.
- `created_at` nhận thời điểm hiện tại nếu câu insert bỏ qua cột này.
- `normalized_name` được tính từ `name`; ứng dụng không nên đưa giá trị vào cột này.

Nếu câu SQL ghi rõ `created_at = NULL`, database nhận giá trị null thay vì tự áp dụng `DEFAULT`, trừ khi cột có constraint hoặc biểu thức khác xử lý. Muốn default được áp dụng, hãy bỏ cột khỏi danh sách insert hoặc dùng từ khóa `DEFAULT` theo cú pháp database.

Với generated column, hãy bỏ cột đó khỏi danh sách insert/update. Việc cố ghi giá trị trực tiếp có thể bị database từ chối.

## 3. Giá trị sinh tự động khi dùng ReactiveCrudRepository

Với entity có khóa chính identity, Spring Data R2DBC có thể lấy ID do database sinh sau khi insert và đưa ID vào entity được trả về.

```java
@Table("person")
public record Person(
    @Id Long id,
    String name
) {}
```

Repository:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {
}
```

Service:

```java
public Mono<Person> create(String name) {
    Person person = new Person(null, name);
    return personRepository.save(person);
}
```

Khi `id` là null và mapping/database xác định đây là entity mới, `save` thực hiện insert. Giá trị ID được sinh từ database được lấy lại qua cơ chế generated values của driver và được gán vào entity kết quả. Publisher phát ra entity đã có ID sau khi thao tác hoàn tất.

Nên dùng kiểu tham chiếu như `Long` cho ID được sinh tự động để biểu diễn trạng thái chưa có giá trị bằng `null`. Với kiểu primitive như `long`, giá trị mặc định `0` không biểu đạt rõ trạng thái chưa được cấp ID và có thể ảnh hưởng chiến lược nhận diện entity mới.

Không nên giả định mọi entity có ID khác null đều được insert. `save` chọn insert hoặc update theo chiến lược xác định entity mới của Spring Data, có thể dựa trên ID, `@Version` hoặc cơ chế `Persistable` tùy entity. Nếu ID được ứng dụng gán trước, hãy thiết kế newness detection phù hợp.

## 4. Dùng R2dbcEntityTemplate để nhận ID sinh tự động

Nếu ứng dụng dùng `R2dbcEntityTemplate`, thao tác insert cũng trả về entity sau khi ghi:

```java
public Mono<Person> create(String name) {
    Person person = new Person(null, name);
    return template.insert(Person.class).using(person);
}
```

Đây là cách phù hợp khi muốn dùng API entity của Spring Data thay vì SQL trực tiếp. Template sử dụng mapping metadata và dialect để tạo câu insert, đồng thời phối hợp với R2DBC driver để lấy generated ID theo khả năng của database.

Nếu mục tiêu chỉ là lấy ID identity, Repository hoặc Template thường là lựa chọn đơn giản. Khi cần lấy thêm các cột database-generated khác như `created_at`, `normalized_name` hoặc giá trị do trigger tạo, cần xác minh phiên bản Spring Data, dialect và driver có trả những cột đó trong thao tác insert hay không. Không nên suy luận rằng việc ID được gán tự động đồng nghĩa toàn bộ cột generated đã được làm mới trong entity.

## 5. Đánh dấu cột chỉ đọc bằng @ReadOnlyProperty

Spring Data Relational cung cấp `@ReadOnlyProperty` để đánh dấu thuộc tính được đọc từ database nhưng không được ghi trong thao tác insert hoặc update do Spring Data thực hiện.

Ví dụ entity:

```java
@Table("person")
public record Person(
    @Id Long id,
    String name,
    @ReadOnlyProperty
    @Column("created_at")
    OffsetDateTime createdAt,
    @ReadOnlyProperty
    @Column("normalized_name")
    String normalizedName
) {}
```

`createdAt` và `normalizedName` được đọc khi truy vấn entity, nhưng Spring Data không đưa chúng vào câu insert/update. Cách này hữu ích cho cột default hoặc generated column mà ứng dụng không được phép tự ghi.

`@ReadOnlyProperty` kiểm soát việc ghi thuộc tính qua mapping Spring Data; annotation này không tự bảo đảm driver trả các giá trị đó ngay sau insert. Nếu cần dùng giá trị vừa sinh trong cùng request, hãy yêu cầu generated values rõ ràng hoặc truy vấn lại hàng sau khi ghi.

Không dùng `@ReadOnlyProperty` cho cột mà ứng dụng cần chủ động cập nhật. Nếu chỉ muốn cột được ghi khi insert nhưng không ghi khi update, hãy xem xét annotation và semantics khác như `@InsertOnlyProperty` nếu phiên bản Spring Data của dự án hỗ trợ.

## 6. Yêu cầu generated values qua R2DBC SPI

R2DBC SPI định nghĩa `Statement.returnGeneratedValues(String... columns)` để yêu cầu driver trả về các giá trị được database sinh trong quá trình thực thi statement.

Khi dùng `DatabaseClient`, có thể thêm `StatementFilterFunction` để cấu hình statement trước khi thực thi:

```java
public Mono<PersonCreated> insertPerson(String name) {
    return databaseClient.sql("""
            INSERT INTO person (name)
            VALUES (:name)
            """)
        .bind("name", name)
        .filter((statement, next) -> {
            statement.returnGeneratedValues(
                "id",
                "created_at",
                "normalized_name"
            );
            return next.execute(statement);
        })
        .map((row, metadata) -> new PersonCreated(
            row.get("id", Long.class),
            row.get("created_at", OffsetDateTime.class),
            row.get("normalized_name", String.class)
        ))
        .one();
}
```

DTO:

```java
public record PersonCreated(
    Long id,
    OffsetDateTime createdAt,
    String normalizedName
) {}
```

Luồng xử lý:

1. `sql(...)` khai báo câu insert; cột `id`, `created_at` và `normalized_name` được bỏ khỏi danh sách insert.
2. `bind(...)` gắn giá trị cho tham số `name`.
3. `filter(...)` nhận statement trước khi thực thi và gọi `returnGeneratedValues(...)`.
4. `next.execute(statement)` chuyển statement đã cấu hình cho bước thực thi tiếp theo.
5. `map(...)` ánh xạ hàng generated values thành DTO.
6. `one()` yêu cầu một kết quả và trả `Mono<PersonCreated>`.

`returnGeneratedValues` thuộc R2DBC SPI, nhưng khả năng hỗ trợ thực tế phụ thuộc driver và hệ quản trị. Một driver có thể chỉ trả generated identity, không hỗ trợ tên cột tùy ý hoặc có giới hạn riêng về loại cột được trả. Hãy kiểm tra tài liệu của đúng phiên bản driver và chạy integration test trên database đích.

Nếu driver không hỗ trợ cột generated bổ sung, đừng giả định `row` sẽ chứa đầy đủ các cột đã yêu cầu. Chọn một trong các cách thay thế: dùng SQL `RETURNING`/`OUTPUT` của database hoặc thực hiện truy vấn `SELECT` sau khi insert.

## 7. Dùng RETURNING trong PostgreSQL

PostgreSQL hỗ trợ mệnh đề `RETURNING` cho `INSERT`, `UPDATE` và `DELETE`. Đây là cách trực tiếp để nhận lại các cột của hàng vừa bị thay đổi.

Ví dụ insert và nhận cả ID, default timestamp và generated column:

```java
public Mono<PersonCreated> insertPerson(String name) {
    return databaseClient.sql("""
            INSERT INTO person (name)
            VALUES (:name)
            RETURNING id, created_at, normalized_name
            """)
        .bind("name", name)
        .map((row, metadata) -> new PersonCreated(
            row.get("id", Long.class),
            row.get("created_at", OffsetDateTime.class),
            row.get("normalized_name", String.class)
        ))
        .one();
}
```

Ở đây, `RETURNING` là cú pháp SQL PostgreSQL, không phải cú pháp portable cho mọi database. Ưu điểm là câu lệnh ghi và việc lấy giá trị sinh ra diễn ra trong một thao tác, tránh thêm round trip chỉ để đọc lại hàng.

Có thể dùng `RETURNING *`, nhưng thường nên liệt kê các cột cần thiết để tránh truyền dữ liệu thừa và làm rõ hợp đồng DTO. Nếu schema có cột nhạy cảm hoặc dữ liệu lớn, càng nên chỉ trả những cột cần dùng.

### UPDATE RETURNING

Một cột có thể thay đổi sau update, ví dụ `updated_at` do database default/trigger hoặc generated expression cập nhật. PostgreSQL có thể trả lại giá trị sau cập nhật:

```java
public Mono<PersonUpdated> rename(Long id, String newName) {
    return databaseClient.sql("""
            UPDATE person
            SET name = :name
            WHERE id = :id
            RETURNING id, name, created_at, normalized_name
            """)
        .bind("name", newName)
        .bind("id", id)
        .map((row, metadata) -> new PersonUpdated(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("created_at", OffsetDateTime.class),
            row.get("normalized_name", String.class)
        ))
        .one();
}
```

Nếu ID không tồn tại hoặc điều kiện không khớp, `one()` hoàn tất rỗng. Service có thể chuyển kết quả rỗng thành lỗi not found hoặc coi là no-op tùy hợp đồng API.

### DELETE RETURNING

PostgreSQL cũng có thể trả các cột của hàng đã xóa:

```java
public Flux<Long> deleteAndReturnIds(String status) {
    return databaseClient.sql("""
            DELETE FROM person
            WHERE status = :status
            RETURNING id
            """)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
}
```

Đây là tính năng hữu ích khi cần ghi audit hoặc phát sự kiện dựa trên các ID bị xóa. Cần cân nhắc số lượng hàng trả về để không gom một tập kết quả quá lớn vào bộ nhớ.

## 8. Cú pháp OUTPUT của SQL Server

SQL Server hỗ trợ mệnh đề `OUTPUT` để lấy các giá trị từ hàng được insert, update hoặc delete. Ví dụ:

```sql
INSERT INTO person (name)
OUTPUT INSERTED.id,
       INSERTED.created_at,
       INSERTED.normalized_name
VALUES (@name);
```

Khi dùng `DatabaseClient`, placeholder và cách bind cần phù hợp với R2DBC SQL Server driver đang sử dụng. Cú pháp `OUTPUT INSERTED...` là đặc thù SQL Server; không thể sao chép nguyên câu SQL PostgreSQL có `RETURNING` sang SQL Server.

Các hệ quản trị khác có thể dùng cú pháp hoặc API khác để lấy generated values. Vì vậy, khi ứng dụng cần hỗ trợ nhiều database, hãy cân nhắc dùng abstraction R2DBC SPI nếu driver hỗ trợ nhất quán, hoặc tách câu SQL theo dialect.

## 9. Giá trị mặc định chỉ được sinh khi cột bị bỏ qua

Database áp dụng default khi câu insert không cung cấp giá trị cho cột đó hoặc dùng từ khóa `DEFAULT` theo cú pháp của database.

Ví dụ:

```sql
-- DEFAULT được áp dụng cho created_at.
INSERT INTO person (name)
VALUES ('An');

-- Câu lệnh này ghi NULL tường minh; default không tự thay thế NULL.
INSERT INTO person (name, created_at)
VALUES ('Binh', NULL);
```

Trong SQL trực tiếp, hãy bỏ cột có default khỏi danh sách insert nếu muốn database sinh giá trị. Trong mapping entity, `@ReadOnlyProperty` có thể giúp loại thuộc tính khỏi các thao tác ghi của Spring Data. Với thuộc tính có thể null nhưng đôi khi cần truyền null có chủ đích, cần phân biệt rõ “không cung cấp giá trị để dùng default” với “ghi null”.

Không nên giả định bind một giá trị null tương đương với việc bỏ cột. Bind null là truyền một giá trị SQL null cho placeholder; nó không kích hoạt default.

## 10. Generated column không phải cột do ứng dụng cập nhật

Generated column được database tính từ các cột khác. Ví dụ:

```sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(19, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    line_total NUMERIC(19, 2)
        GENERATED ALWAYS AS (unit_price * quantity) STORED
);
```

Ứng dụng chỉ ghi `name`, `unit_price` và `quantity`. Database tự tính `line_total`. Nếu cố insert hoặc update `line_total`, database có thể báo lỗi vì đây là cột generated.

Trong entity, đánh dấu cột này read-only:

```java
@Table("product")
public record Product(
    @Id Long id,
    String name,
    BigDecimal unitPrice,
    Integer quantity,
    @ReadOnlyProperty
    @Column("line_total")
    BigDecimal lineTotal
) {}
```

Khi truy vấn `Product`, `lineTotal` có thể được đọc từ database. Sau insert/update, nếu framework/driver không trả cột đó trong generated values, hãy đọc lại hàng để nhận giá trị mới.

## 11. Trigger có thể sinh hoặc thay đổi giá trị

Trigger có thể gán giá trị trước hoặc sau thao tác ghi, tùy hệ quản trị và loại trigger. Ví dụ trigger có thể tự gán `updated_at`, chuẩn hóa dữ liệu hoặc tạo mã tham chiếu.

Khi cần lấy lại giá trị do trigger tạo, phải xác minh database và driver có trả giá trị đó trong generated values/`RETURNING` hay không. Hành vi có thể khác nhau giữa trigger chạy trước khi ghi, trigger chạy sau khi ghi và cơ chế trả kết quả của database.

Nếu giá trị không được trả về, cách tổng quát là truy vấn lại hàng sau thao tác ghi bằng ID hoặc một khóa nghiệp vụ duy nhất. Tránh dùng một câu `SELECT` chỉ dựa trên giá trị không duy nhất như tên người dùng hoặc timestamp gần đúng.

## 12. Đọc lại hàng sau khi ghi

Nếu driver không trả cột generated bổ sung, ứng dụng có thể thực hiện insert rồi select lại. Ví dụ, khi đã nhận được ID sinh tự động:

```java
public Mono<Person> createAndReload(String name) {
    Person person = new Person(null, name, null, null);

    return personRepository.save(person)
        .flatMap(saved -> personRepository.findById(saved.id()));
}
```

Ví dụ giả định entity `Person` có các thuộc tính read-only `createdAt` và `normalizedName`, đồng thời `save` trả lại ID được sinh. Truy vấn thứ hai tải đầy đủ các cột từ database, bao gồm default và generated column.

Đọc lại tạo thêm một round trip. Nếu response cần ngay các giá trị sinh ra và database hỗ trợ `RETURNING` hoặc `returnGeneratedValues`, nhận chúng trong cùng thao tác thường hiệu quả hơn.

Nếu cần insert rồi select trong cùng transaction, hãy đặt hai thao tác trong một reactive transaction và trả publisher liên tục. Điều này giúp truy vấn sau nhìn thấy thay đổi vừa ghi trong transaction theo isolation semantics của database.

Không nên dựa vào hàm kiểu `last_insert_id()` ở một câu lệnh độc lập trên connection pool nếu không bảo đảm hai lệnh dùng cùng connection/session. Một thao tác khác có thể được cấp connection khác. Dùng generated values, `RETURNING` hoặc transaction/connection được quản lý rõ ràng.

## 13. Dùng sequence khi cần chủ động lấy ID

Một số schema dùng sequence riêng thay vì identity. Với PostgreSQL:

```sql
CREATE SEQUENCE person_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE person (
    id BIGINT PRIMARY KEY DEFAULT nextval('person_id_seq'),
    name VARCHAR(200) NOT NULL
);
```

Thông thường, có thể để database dùng default sequence và yêu cầu generated ID sau insert. Nếu nghiệp vụ cần lấy ID trước khi insert, có thể truy vấn sequence:

```sql
SELECT nextval('person_id_seq');
```

Sau đó dùng giá trị nhận được để insert. Cách lấy trước có thể hữu ích khi cần tạo ID để gắn vào nhiều bản ghi trong cùng quy trình, nhưng phải bảo đảm sequence thuộc đúng schema và quyền truy cập phù hợp.

Không nên tự tính ID bằng `MAX(id) + 1`. Hai request đồng thời có thể cùng đọc một giá trị max và tạo ID trùng. Hãy dùng identity, sequence hoặc cơ chế sinh ID an toàn.

## 14. Generated values và nhiều hàng insert

Một câu insert có thể thêm nhiều hàng cùng lúc. Khả năng trả generated values cho mỗi hàng phụ thuộc database, driver và dạng statement.

Ví dụ PostgreSQL:

```sql
INSERT INTO person (name)
VALUES ('An'), ('Binh'), ('Chi')
RETURNING id, name, created_at;
```

Kết quả `RETURNING` có thể chứa một hàng cho mỗi hàng được insert. Trong `DatabaseClient`, dùng `.all()` để nhận nhiều hàng:

```java
public Flux<PersonCreated> insertMany(List<String> names) {
    // Ví dụ SQL cần được xây dựng theo số lượng hàng với bind parameter
    // hoặc dùng batch/statement phù hợp với driver.
    return databaseClient.sql("""
            INSERT INTO person (name)
            VALUES (:name)
            RETURNING id, name, created_at
            """)
        .bind("name", names.get(0))
        .map((row, metadata) -> new PersonCreated(
            row.get("id", Long.class),
            row.get("created_at", OffsetDateTime.class),
            row.get("name", String.class)
        ))
        .all();
}
```

Đoạn code trên chỉ minh họa một insert có `RETURNING`; nó chưa phải triển khai batch cho toàn bộ danh sách `names`. Với nhiều hàng, có thể dùng batch statement hoặc xây dựng câu insert nhiều bộ giá trị theo API/driver hỗ trợ. Cần xác nhận thứ tự và số hàng generated values trả về, không giả định mọi driver đều bảo toàn thứ tự trong mọi dạng batch.

Nếu cần ghép từng ID sinh ra với input tương ứng, hãy dùng khóa nghiệp vụ hoặc cột nhận diện được trả về cùng ID. Không nên chỉ dựa vào thứ tự nếu database/driver không cam kết.

## 15. Phân biệt generated values với rowsUpdated

`rowsUpdated()` cho biết số hàng bị tác động. Nó không tự trả về ID hoặc các cột generated.

Ví dụ:

```java
Mono<Long> count = databaseClient.sql("""
        INSERT INTO person (name)
        VALUES (:name)
        """)
    .bind("name", name)
    .fetch()
    .rowsUpdated();
```

Kết quả cho biết số hàng được insert, nhưng không cung cấp giá trị ID. Nếu cần ID, hãy yêu cầu generated values, dùng SQL `RETURNING`/`OUTPUT` hoặc đọc lại hàng bằng khóa duy nhất.

Không thể suy ra ID mới bằng cách lấy `MAX(id)` sau insert, vì các transaction khác có thể insert đồng thời. Cũng không nên giả định ID là số hàng đã insert hoặc tự tăng đúng một đơn vị so với ID trước đó.

## 16. Tác động của driver và database dialect

R2DBC SPI định nghĩa hợp đồng chung, nhưng database và driver quyết định cách thực hiện việc trả generated values. Khi lựa chọn cách triển khai, hãy xem xét:

- Driver có hỗ trợ `Statement.returnGeneratedValues(...)` hay không.
- Driver trả những cột nào: chỉ identity, các cột được yêu cầu hay toàn bộ hàng.
- Database có cú pháp `RETURNING`, `OUTPUT` hoặc cơ chế tương đương không.
- Driver có hỗ trợ generated values cho insert nhiều hàng, update và delete không.
- Kiểu dữ liệu trả về có ánh xạ được sang kiểu Java mong muốn không.
- Generated column hoặc trigger có được phản ánh trong kết quả trả về không.
- Hành vi có khác giữa các phiên bản driver hoặc database server không.

Nếu ứng dụng hỗ trợ nhiều hệ quản trị, không nên đặt một câu `RETURNING` của PostgreSQL vào lớp dùng chung rồi kỳ vọng SQL Server hoặc Oracle chạy được. Có thể tạo implementation theo dialect, hoặc dùng abstraction chung khi driver hỗ trợ đủ tính năng cần thiết.

## 17. Xử lý giá trị null và kiểu dữ liệu generated

Generated value có thể null nếu schema cho phép hoặc biểu thức tạo giá trị trả null. Mapper cần dùng kiểu tham chiếu phù hợp:

```java
Long id = row.get("id", Long.class);
OffsetDateTime createdAt = row.get("created_at", OffsetDateTime.class);
```

Không dùng kiểu primitive khi cột có thể null. Với timestamp, cần khớp kiểu SQL và hỗ trợ của driver. Với numeric, dùng `BigDecimal` nếu cần độ chính xác thập phân. Với UUID, enum, JSON hoặc kiểu database riêng, kiểm tra converter và kiểu trả về thực tế.

Tên cột trong `returnGeneratedValues` và tên dùng trong `row.get(...)` cần khớp với khả năng driver trả metadata. Khi dùng `RETURNING`, alias rõ ràng giúp mapper ổn định:

```sql
INSERT INTO person (name)
VALUES (:name)
RETURNING id AS person_id,
          created_at AS created_time;
```

## 18. Kiểm thử generated columns

Nên kiểm tra trên đúng database và driver dự kiến triển khai:

- Insert không cung cấp identity và nhận được ID hợp lệ.
- Insert bỏ qua cột có default và database điền đúng giá trị.
- Insert truyền null tường minh không bị nhầm với việc bỏ qua cột.
- Generated/computed column được database tính đúng từ dữ liệu nguồn.
- Spring Data không ghi vào thuộc tính được đánh dấu `@ReadOnlyProperty`.
- `Statement.returnGeneratedValues` trả các cột mà driver cam kết hỗ trợ.
- `RETURNING`/`OUTPUT` trả đúng giá trị sau insert/update/delete.
- Đọc lại hàng trả đúng default, generated column và giá trị do trigger tạo.
- Nhiều thao tác đồng thời không làm ứng dụng ghép nhầm ID hoặc nhận nhầm giá trị.
- Transaction rollback không để lại dữ liệu dở dang.

Testcontainers hữu ích để chạy integration test với cùng loại database. H2 có thể khác PostgreSQL hoặc SQL Server về identity, generated column, trigger, cú pháp trả generated values và kiểu dữ liệu; test H2 không thay thế kiểm thử trên database production.

## 19. Quy trình lựa chọn cách lấy cột được sinh

Khi một thao tác ghi cần nhận lại giá trị từ database, có thể đi theo trình tự:

**Bước 1 — Liệt kê các cột sinh tự động.** Phân loại identity, sequence, default, generated/computed và trigger-generated value.

**Bước 2 — Xác định cột ứng dụng được phép ghi.** Bỏ các generated column khỏi danh sách insert/update; dùng `@ReadOnlyProperty` nếu mapping entity cần đánh dấu thuộc tính chỉ đọc.

**Bước 3 — Chọn abstraction phù hợp.** Với CRUD entity và ID tự sinh, ưu tiên Repository hoặc `R2dbcEntityTemplate`. Với SQL trực tiếp, dùng `DatabaseClient`.

**Bước 4 — Chọn cơ chế nhận giá trị.** Dùng generated ID tự động của Spring Data, `Statement.returnGeneratedValues`, `RETURNING`/`OUTPUT` hoặc SELECT lại sau ghi.

**Bước 5 — Kiểm tra driver và dialect.** Xác nhận chính xác các cột nào được trả, kiểu dữ liệu và giới hạn theo phiên bản.

**Bước 6 — Ánh xạ vào DTO/entity.** Dùng alias ổn định, kiểu Java phù hợp và xử lý null rõ ràng.

**Bước 7 — Kiểm thử tích hợp.** Xác nhận default, generated column, trigger, concurrency và transaction trên database thật.

## 20. Kết luận

Khi database sinh giá trị trong thao tác ghi, ứng dụng cần chủ động quyết định cách nhận lại giá trị đó. Spring Data Repository và `R2dbcEntityTemplate` hỗ trợ luồng generated ID phổ biến. Với SQL trực tiếp, `Statement.returnGeneratedValues(...)` cung cấp abstraction của R2DBC SPI, còn `RETURNING` và `OUTPUT` cho phép tận dụng cú pháp của từng hệ quản trị. Nếu driver không trả các cột cần thiết, có thể truy vấn lại hàng sau khi ghi.

Hãy phân biệt identity, default và generated column; bỏ các cột chỉ do database quản lý khỏi câu insert/update; dùng `@ReadOnlyProperty` cho thuộc tính chỉ đọc trong mapping; và không nhầm `rowsUpdated()` với generated values. Việc kiểm tra driver, dialect, kiểu dữ liệu và integration test trên database thật giúp ứng dụng nhận đúng ID, timestamp, computed value hoặc dữ liệu do trigger tạo ra sau mỗi thao tác ghi.
