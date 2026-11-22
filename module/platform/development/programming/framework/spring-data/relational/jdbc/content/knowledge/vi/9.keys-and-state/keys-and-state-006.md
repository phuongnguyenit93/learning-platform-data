# Điều khiển isNew bằng Persistable

## 1. Vì sao Spring Data JDBC cần biết entity có mới hay không?

Trong Spring Data JDBC, phương thức `repository.save(entity)` có thể thực hiện `INSERT` hoặc `UPDATE`. Framework phải quyết định đường ghi nào phù hợp trước khi tạo câu SQL. Quyết định đó dựa trên **trạng thái mới của entity** (*new state*), thường được biểu diễn qua `isNew`.

Với khóa chính được database sinh tự động, việc nhận diện khá đơn giản: một entity mới chưa có ID, còn entity đã được lưu thường có ID. Nhưng nhiều hệ thống **tự cấp ID trước khi ghi dữ liệu**:

- ID là UUID được tạo bằng `UUID.randomUUID()` ở ứng dụng.
- ID là mã nghiệp vụ hoặc khóa tự nhiên đã có từ đầu.
- Dữ liệu được tạo từ một nguồn bên ngoài đã cung cấp khóa.

Khi đó, entity vừa tạo đã có ID khác `null`. Nếu chỉ dựa vào ID, Spring Data JDBC có thể hiểu nhầm entity này là đã tồn tại và chọn `UPDATE`. Ta cần một cách diễn đạt trạng thái rõ ràng hơn.

`Persistable<ID>` là hợp đồng của Spring Data cho phép entity **tự cung cấp câu trả lời cho câu hỏi “tôi có phải entity mới không?”** thông qua phương thức `isNew()`. Bài này giải thích cách dùng hợp đồng đó, quản lý cờ trạng thái trong bộ nhớ và tránh các lỗi insert/update thường gặp.

## 2. Cơ chế nhận diện trạng thái mặc định

Nếu entity không triển khai `Persistable`, Spring Data sử dụng chiến lược nhận diện trạng thái mặc định. Về cơ bản:

1. Nếu entity có thuộc tính version phù hợp, version được dùng trước: version chưa có giá trị cho biết entity còn mới; sau khi được lưu, version có giá trị.
2. Nếu không có version property, Spring Data xét ID: ID `null` thường có nghĩa là entity mới; ID khác `null` thường được coi là entity đã tồn tại.

Quy tắc cụ thể về version còn phụ thuộc kiểu thuộc tính và phiên bản Spring Data; với version kiểu tham chiếu như `Long`, giá trị `null` là dấu hiệu phổ biến cho entity mới. Khi dùng `Persistable`, Spring Data ủy quyền quyết định cho `isNew()` của chính entity.

### Ví dụ: UUID đã có trước khi insert

```java
UUID id = UUID.randomUUID();
Customer customer = new Customer(id, "Lan");
repository.save(customer);
```

Tại thời điểm gọi `save`, `customer.getId()` đã có giá trị. Nếu không có version property hoặc chiến lược tùy chỉnh, cơ chế mặc định có thể nhận diện đây là entity cũ và đi theo đường update. Nhưng hàng có UUID đó chưa tồn tại trong database.

**ID có giá trị không đồng nghĩa bản ghi đã được lưu.** ID chỉ nhận diện một bản ghi; trạng thái mới cho biết framework cần tạo bản ghi hay cập nhật bản ghi.

## 3. `Persistable<ID>` là gì?

`Persistable` nằm trong package `org.springframework.data.domain`:

```java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
```

Đây là hợp đồng đơn giản:

- `getId()` trả về khóa của entity.
- `isNew()` trả lời entity hiện tại có cần được insert hay không.

Khi một entity triển khai `Persistable`, Spring Data dùng `isNew()` để xác định thao tác lưu:

| Kết quả `isNew()` | Hướng lưu được chọn | Ý nghĩa |
| --- | --- | --- |
| `true` | `INSERT` | Entity được xem là mới, kể cả khi ID đã được gán. |
| `false` | `UPDATE` | Entity được xem là đã tồn tại; framework thực hiện cập nhật theo ID. |

`Persistable` không phải lệnh SQL, cũng không truy vấn database để kiểm tra xem ID đã tồn tại hay chưa. Nó là **thông tin trạng thái do entity cung cấp**. Vì vậy, implementation phải phản ánh đúng vòng đời của đối tượng.

## 4. Khi nào nên dùng Persistable?

`Persistable` hữu ích khi:

- Ứng dụng tạo UUID hoặc khóa khác trước khi insert.
- Khóa chính là mã tự nhiên đã có từ dữ liệu đầu vào.
- Quy tắc nhận diện mới/cũ không thể biểu diễn chính xác bằng ID-null hoặc version.
- Muốn kiểm soát tường minh thời điểm một object chuyển từ trạng thái mới sang đã lưu.

Ví dụ điển hình là hệ thống nhận một mã định danh do dịch vụ upstream tạo ra. Khi tạo aggregate mới, mã đã tồn tại trong bộ nhớ, nhưng database chưa có hàng tương ứng.

Không cần triển khai `Persistable` trong mọi entity. Nếu database tự sinh ID và entity mới có ID `null`, cơ chế mặc định thường đơn giản và ít trạng thái phải quản lý hơn. Nếu version property đã diễn đạt được trạng thái mới một cách phù hợp, hãy cân nhắc dùng nó trước khi thêm một cờ tùy chỉnh.

## 5. Thiết kế cờ trạng thái bằng @Transient

Một cách triển khai phổ biến là giữ một cờ boolean chỉ tồn tại trong bộ nhớ:

- Entity mới được tạo qua factory/constructor nghiệp vụ sẽ đặt cờ `newEntity = true`.
- Sau khi insert thành công, ứng dụng chuyển cờ thành `false`.
- Khi entity được đọc từ database, cờ không được load từ bảng và mặc định là `false`.

Để cờ không trở thành một cột SQL, đánh dấu nó bằng `org.springframework.data.annotation.Transient`.

### Vì sao không dùng một cột boolean trong database?

Trạng thái `isNew` phục vụ quyết định kỹ thuật trong một vòng đời persistence. Nó không phải dữ liệu nghiệp vụ cần lưu lâu dài. Nếu lưu cờ đó thành cột:

- Cờ có thể bị lệch so với sự tồn tại thật của hàng.
- Mỗi lần đọc lại entity phải xử lý cờ trong database.
- Cột persistence state bị trộn với schema nghiệp vụ.
- Hai hệ thống ghi cùng bảng có thể hiểu cờ theo những cách khác nhau.

Vì vậy, cờ này nên là trạng thái transient trong object.

## 6. Ví dụ đầy đủ: UUID tự cấp và Persistable

Giả sử hệ thống quản lý khách hàng. Ứng dụng tạo UUID ngay khi bắt đầu đăng ký, trước khi gửi lệnh insert. Ta dùng Spring Data JDBC và H2 để minh họa.

### 6.1. Dependency và cấu hình database

Với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Tạo `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:persistable_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

logging.level.org.springframework.jdbc=DEBUG
```

Tạo `src/main/resources/schema.sql`:

```sql
CREATE TABLE "customers" (
    "id" UUID PRIMARY KEY,
    "name" VARCHAR(120) NOT NULL
);
```

H2 hỗ trợ kiểu `UUID`. Schema dùng tên bảng/cột được quote nhất quán với mapping trong ví dụ. Khi chuyển sang database khác, hãy xác nhận kiểu UUID và cách quote identifier theo dialect tương ứng.

### 6.2. Entity triển khai Persistable

Tạo `src/main/java/com/example/persistable/Customer.java`:

```java
package com.example.persistable;

import java.util.Objects;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer implements Persistable<UUID> {

    @Id
    private UUID id;

    private String name;

    // Không ánh xạ thành cột database.
    // Mặc định false: object được materialize từ database là object đã tồn tại.
    @Transient
    private boolean newEntity;

    // Constructor dành cho Spring Data JDBC khi đọc dữ liệu.
    protected Customer() {
    }

    private Customer(UUID id, String name) {
        this.id = Objects.requireNonNull(id, "id is required");
        this.name = requireName(name);
        this.newEntity = true;
    }

    public static Customer register(String name) {
        return new Customer(UUID.randomUUID(), name);
    }

    public static Customer registerWithId(UUID id, String name) {
        return new Customer(id, name);
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    // Chỉ gọi sau khi repository.save(...) hoàn tất thành công.
    void markNotNew() {
        this.newEntity = false;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = requireName(newName);
    }

    private static String requireName(String value) {
        Objects.requireNonNull(value, "name is required");
        String normalized = value.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return normalized;
    }
}
```

Phân tích:

1. `Customer implements Persistable<UUID>` nên Spring Data gọi `isNew()` thay cho việc chỉ nhìn vào ID để quyết định trạng thái mới.
2. `id` được gán ngay trong factory bằng `UUID.randomUUID()`, do đó không null ngay cả trước insert.
3. `newEntity` mặc định là `false`. Khi tạo qua `register(...)`, constructor đặt nó thành `true`.
4. `@Transient` loại cờ này khỏi mapping database. Bảng `customers` không cần cột `new_entity`.
5. Khi Spring Data JDBC đọc một hàng và tạo lại `Customer` bằng constructor không tham số, cờ transient giữ giá trị mặc định `false`. Entity vừa đọc được xem là entity đã tồn tại.
6. `markNotNew()` là thao tác nội bộ để hoàn tất vòng đời sau khi insert.

Ta dùng class thay vì record vì cờ `newEntity` phải thay đổi sau khi lưu. Một record bất biến không thích hợp để giữ trạng thái vòng đời này trực tiếp.

### 6.3. Repository

Tạo `src/main/java/com/example/persistable/CustomerRepository.java`:

```java
package com.example.persistable;

import java.util.UUID;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}
```

Repository cung cấp các thao tác cơ bản. Không cần viết implementation cho `save`, `findById` hoặc `deleteById`.

### 6.4. Service quản lý vòng đời cờ isNew

Tạo `src/main/java/com/example/persistable/CustomerService.java`:

```java
package com.example.persistable;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public UUID register(String name) {
        Customer candidate = Customer.register(name);

        // candidate có UUID khác null nhưng isNew() == true.
        Customer saved = customers.save(candidate);

        // Chỉ đánh dấu đã tồn tại sau khi thao tác save thành công.
        saved.markNotNew();
        return saved.getId();
    }

    @Transactional(readOnly = true)
    public Customer find(UUID id) {
        return customers.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found"));
    }

    @Transactional
    public void rename(UUID id, String newName) {
        Customer customer = customers.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found"));

        customer.rename(newName);
        customers.save(customer);
    }
}
```

Ở đây, service đảm bảo trình tự:

1. Tạo object có ID và `isNew() == true`.
2. Gọi `save`; Spring Data chọn `INSERT`.
3. Khi save trả về thành công, gọi `markNotNew()` trên object được trả về.
4. Khi đọc lại, object mới được materialize với `newEntity == false`.
5. Khi đổi tên và gọi `save`, Spring Data chọn `UPDATE`.

Việc cập nhật cờ nằm ngay sau lệnh insert thành công, giúp tránh trường hợp một object đã lưu vẫn tự nhận là mới và lần gọi `save` kế tiếp tiếp tục thử insert.

> Ví dụ này dùng transaction thông thường để minh họa. Cờ `newEntity` là trạng thái trong bộ nhớ; nếu transaction bị rollback sau khi object đã được đánh dấu, không nên tái sử dụng object đó như một nguồn sự thật. Hãy đọc lại aggregate trong transaction mới hoặc tạo lại object từ trạng thái nghiệp vụ.

### 6.5. Chạy thử

Tạo `src/main/java/com/example/persistable/PersistableApplication.java`:

```java
package com.example.persistable;

import java.util.UUID;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PersistableApplication {

    public static void main(String[] args) {
        SpringApplication.run(PersistableApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerService service) {
        return args -> {
            UUID id = service.register("Lan");
            System.out.println("Registered id = " + id);

            Customer loaded = service.find(id);
            System.out.println("Loaded name = " + loaded.getName());
            System.out.println("Loaded isNew = " + loaded.isNew());

            service.rename(id, "Lan Nguyen");

            Customer changed = service.find(id);
            System.out.println("Updated name = " + changed.getName());
            System.out.println("Updated isNew = " + changed.isNew());
        };
    }
}
```

Chạy ở thư mục gốc dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giá trị console mong đợi:

```text
Registered id = <một UUID được tạo>
Loaded name = Lan
Loaded isNew = false
Updated name = Lan Nguyen
Updated isNew = false
```

Đây là kết quả minh họa. SQL log sẽ có hình dạng tương đương:

```sql
-- Lần save đầu tiên: isNew() == true
INSERT INTO "customers" ("id", "name")
VALUES (?, ?);

-- Lần đọc
SELECT "customers"."id", "customers"."name"
FROM "customers"
WHERE "customers"."id" = ?;

-- Lần save sau khi đổi tên: isNew() == false
UPDATE "customers"
SET "name" = ?
WHERE "id" = ?;
```

Tên cột, quoting và định dạng log cụ thể phụ thuộc dialect và phiên bản Spring Data JDBC. Điều cần quan sát là lần đầu có `INSERT` dù ID đã có giá trị; lần sau có `UPDATE`.

## 7. Tại sao phải cập nhật cờ sau khi save?

Giả sử ta tạo một customer:

```java
Customer customer = Customer.register("Lan");
System.out.println(customer.getId()); // UUID khác null
System.out.println(customer.isNew()); // true
```

Spring Data JDBC gọi `isNew()` và chọn insert. Sau insert, database đã có hàng mang UUID đó. Nếu cờ vẫn là `true`:

```java
customers.save(customer); // INSERT
customers.save(customer); // Vẫn có thể đi vào INSERT lần nữa
```

Lần lưu thứ hai có thể thất bại do vi phạm khóa chính. Vì vậy, cờ phải chuyển sang `false` sau khi insert hoàn tất:

```java
Customer saved = customers.save(customer);
saved.markNotNew();

customers.save(saved); // UPDATE
```

Không đặt `newEntity = false` **trước** khi gọi `save`. Nếu thao tác insert thất bại, object sẽ tự nhận là đã tồn tại dù chưa có hàng trong database.

### Tại sao không đặt cờ false ngay khi tạo ID?

ID được cấp trước insert chỉ chứng minh ứng dụng đã chọn một định danh. Nó không chứng minh database đã lưu entity. Đây chính là lý do `Persistable` tồn tại: trạng thái persistence và giá trị ID là hai thông tin độc lập.

## 8. Entity được tải lại có isNew() bằng false bằng cách nào?

Một câu hỏi thường gặp: `newEntity` là transient, database không lưu cờ này. Vậy khi đọc một hàng, vì sao `isNew()` không trở thành `true`?

Trong ví dụ, field được khai báo:

```java
@Transient
private boolean newEntity;
```

Giá trị mặc định của boolean Java là `false`. Constructor không tham số dành cho mapping không gán lại cờ thành true. Spring Data JDBC materialize các thuộc tính persistent từ hàng database; field `@Transient` không được đọc từ cột và vẫn giữ `false`.

Factory tạo object mới là nơi duy nhất đặt cờ thành true:

```java
private Customer(UUID id, String name) {
    this.id = id;
    this.name = name;
    this.newEntity = true;
}
```

Đây là một quy ước phải được giữ nhất quán: mọi luồng tạo entity mới phải đi qua factory/constructor đặt cờ; không tự khởi tạo object bằng đường khác rồi quên trạng thái.

Nếu dùng một constructor mapping tùy chỉnh, builder hoặc cơ chế copy, hãy bảo đảm transient state của object được khởi tạo đúng. Không đưa `newEntity` vào constructor persistent chỉ để framework đọc nó từ database, vì cột này không tồn tại.

## 9. So sánh Persistable với @Version và ID-null

Có ba hướng thường gặp:

| Cách nhận diện | Khi nào phù hợp | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- | --- |
| ID `null` | Database sinh ID sau insert | Đơn giản, không cần cờ riêng | Không phù hợp nếu ID luôn được cấp trước. |
| Thuộc tính `@Version` nullable | Entity có version và muốn optimistic locking | Version vừa hỗ trợ concurrency vừa giúp nhận diện trạng thái mới | Cần cột version và hiểu đúng quy tắc version của Spring Data. |
| `Persistable.isNew()` | ID được cấp trước hoặc có quy tắc state riêng | Chủ động kiểm soát insert/update | Phải quản lý cờ đúng vòng đời; trạng thái sai gây chọn sai SQL. |

### Trường hợp có @Version

Ví dụ entity có:

```java
@Id
private UUID id;

@Version
private Long version;
```

Với một entity mới, `version == null` có thể được dùng để nhận diện trạng thái mới dù ID đã được gán. Khi lưu, framework cập nhật version. Nếu có version phù hợp, đây thường là một cách tự nhiên hơn để nhận diện trạng thái và phát hiện ghi cạnh tranh.

Khi entity triển khai `Persistable`, hãy nhớ rằng quyết định `isNew` được giao cho phương thức của bạn. Không giả định rằng version sẽ tự ghi đè một kết quả `isNew()` sai. Nếu chọn `Persistable`, hãy chịu trách nhiệm duy trì cờ và vẫn dùng `@Version` riêng cho optimistic locking nếu nghiệp vụ cần.

### Khi nào không nên dùng Persistable?

- ID mới đang là `null` và database sinh ID bình thường.
- Version property đã đáp ứng nhu cầu nhận diện và kiểm soát cạnh tranh.
- Đội phát triển không có quy ước tạo object/đánh dấu đã lưu rõ ràng.
- Entity bị dựng trực tiếp từ request hoặc deserialize ở nhiều nơi, khiến cờ có thể bị client điều khiển.

Tránh thêm `Persistable` chỉ vì muốn ép một lệnh SQL cụ thể. Hãy dùng nó khi mô hình trạng thái mới/cũ thực sự cần một nguồn quyết định riêng.

## 10. Persistable không phải upsert

`isNew()` chỉ quyết định framework đi theo nhánh insert hay update; nó không yêu cầu database tự kiểm tra rồi chọn thao tác.

| Tình trạng thực tế | `isNew()` | Hành vi dự kiến | Kết quả có thể xảy ra |
| --- | --- | --- | --- |
| ID chưa có trong DB | `true` | `INSERT` | Thành công nếu không vi phạm constraint. |
| ID đã tồn tại trong DB | `true` | `INSERT` | Lỗi trùng khóa chính. |
| ID đã tồn tại trong DB | `false` | `UPDATE` | Cập nhật hàng theo ID. |
| ID không có trong DB | `false` | `UPDATE` | Không thể tạo hàng mới; thao tác update có thể báo không cập nhật được hàng nào. |

Vì vậy:

- Đừng luôn trả về `true` chỉ vì entity có UUID.
- Đừng luôn trả về `false` chỉ vì entity có ID.
- Đừng dùng `isNew()` như một truy vấn kiểm tra tồn tại.
- Đừng kỳ vọng Spring Data JDBC tự thực hiện `INSERT ... ON CONFLICT DO UPDATE` hoặc `MERGE` khi dùng `Persistable`.

Nếu nghiệp vụ cần “tạo nếu chưa tồn tại, nếu đã tồn tại thì cập nhật”, đó là một use case upsert. Hãy thiết kế rõ semantics, constraint và câu SQL/database-specific phù hợp, hoặc tải entity rồi cập nhật theo một quy trình có kiểm soát.

## 11. Các lỗi thường gặp khi triển khai

### Lỗi 1: có UUID nhưng không triển khai Persistable

**Triệu chứng:** gọi `save` với object mới nhưng log cho thấy `UPDATE` hoặc báo không tìm thấy hàng cần cập nhật.

**Nguyên nhân:** ID đã khác null nên cơ chế mặc định xem object là cũ (khi không có version property thay thế chiến lược).

**Cách xử lý:** dùng `Persistable` với `isNew()` chính xác, hoặc dùng nullable `@Version` nếu phù hợp với mô hình.

### Lỗi 2: isNew() luôn trả về true

**Triệu chứng:** mỗi lần gọi `save` đều cố insert; lần thứ hai vi phạm khóa chính.

**Nguyên nhân:** cờ không được chuyển sang false sau insert, hoặc object được tạo lại từ factory trong lúc lẽ ra phải tải từ repository.

**Cách xử lý:** cập nhật cờ sau save thành công; entity đọc từ database phải có trạng thái new=false.

### Lỗi 3: isNew() luôn trả về false

**Triệu chứng:** entity chưa từng được lưu nhưng lại đi vào nhánh update.

**Nguyên nhân:** factory không đặt cờ true hoặc field được khởi tạo sai.

**Cách xử lý:** tập trung việc tạo entity mới vào factory/constructor; kiểm thử `isNew()` trước khi gọi repository.

### Lỗi 4: lưu cờ thành cột database

**Triệu chứng:** Spring Data tìm cột `new_entity` không tồn tại hoặc schema bị thêm một cột trạng thái kỹ thuật.

**Nguyên nhân:** quên `@Transient` hoặc dùng nhầm annotation.

**Cách xử lý:** dùng `org.springframework.data.annotation.Transient`, không nhầm với annotation cùng tên của thư viện khác; kiểm tra SQL mapping và schema.

### Lỗi 5: đặt cờ false trước khi insert

**Triệu chứng:** insert thất bại nhưng object vẫn báo đã tồn tại; lần retry tiếp theo đi vào update.

**Nguyên nhân:** trạng thái bị thay đổi trước khi thao tác persistence thành công.

**Cách xử lý:** chỉ chuyển cờ sau khi `save` trả về thành công; không dùng lại object sau transaction rollback như thể nó phản ánh trạng thái DB.

### Lỗi 6: request client điều khiển trực tiếp isNew

**Triệu chứng:** dữ liệu JSON có thể làm ứng dụng chọn insert/update ngoài dự kiến.

**Nguyên nhân:** dùng persistence entity làm request DTO hoặc cho phép binding vào field trạng thái.

**Cách xử lý:** nhận DTO/command riêng, kiểm tra quyền và định danh ở service, sau đó tạo entity qua factory. Cờ `isNew` phải do backend quản lý.

### Lỗi 7: nghĩ Persistable kiểm tra hàng tồn tại

**Triệu chứng:** `isNew()` trả false nhưng ID chưa có trong DB và update không thành công.

**Nguyên nhân:** nhầm state detection với existence check.

**Cách xử lý:** hiểu `isNew` là chỉ dẫn chọn thao tác. Nếu cần kiểm tra tồn tại, dùng repository hoặc thiết kế constraint/upsert theo yêu cầu.

## 12. Quản lý cờ bằng callback: khi nào cần?

Ví dụ trên cập nhật cờ tường minh trong service:

```java
Customer saved = repository.save(candidate);
saved.markNotNew();
```

Đây là cách dễ đọc và làm rõ trách nhiệm. Trong ứng dụng có nhiều nơi lưu cùng một loại aggregate, có thể cân nhắc cơ chế lifecycle callback của Spring Data Relational để tập trung việc đánh dấu sau khi save. Tuy nhiên, callback phải được đăng ký đúng API và đúng phiên bản Spring Data của dự án; cần bảo đảm:

- Callback chỉ đánh dấu object sau thao tác save thành công.
- Object được materialize từ database không bị đánh dấu nhầm là mới.
- Field vẫn được loại khỏi mapping bằng `@Transient`.
- Các test insert/update xác nhận callback được gọi đúng đường.

Không nên thêm callback chỉ để tránh một dòng `markNotNew()` nếu ứng dụng chỉ có một use case tạo entity. Callback là một cơ chế vòng đời dùng chung, nhưng làm luồng trạng thái khó nhìn thấy hơn khi nhóm chưa quen.

Một phương án khác là dùng factory kết hợp repository adapter chuyên trách để mọi lệnh insert/update đều đi qua cùng một điểm. Dù chọn cách nào, phải có **một nơi chịu trách nhiệm chuyển trạng thái**, tránh để controller, service và repository tự thay đổi cờ theo cách riêng.

## 13. Kiểm thử hành vi isNew và SQL thực tế

Kiểm thử nên xác nhận cả trạng thái trong object và kết quả persistence.

### Kiểm thử đơn vị cho factory

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class CustomerTest {

    @Test
    void newCustomerHasAssignedIdAndIsNew() {
        Customer customer = Customer.register("Lan");

        assertNotNull(customer.getId());
        assertTrue(customer.isNew());
    }

    @Test
    void markNotNewChangesPersistenceState() {
        Customer customer = Customer.register("Lan");

        customer.markNotNew();

        assertFalse(customer.isNew());
    }
}
```

Trong dự án thật, nếu `markNotNew()` chỉ package-private thì test có thể đặt cùng package. Test này chỉ kiểm tra quy tắc trạng thái trong bộ nhớ; nó chưa chứng minh SQL insert/update.

### Kiểm thử tích hợp với database

Một kiểm thử persistence nên xác nhận:

1. Tạo `Customer` bằng factory: ID khác null, `isNew() == true`.
2. Gọi `repository.save`: một hàng có UUID đó xuất hiện trong bảng.
3. Đánh dấu đã lưu theo cơ chế đã chọn.
4. Đọc lại bằng `findById`: tên đúng và `isNew() == false`.
5. Đổi tên, gọi `save`: vẫn chỉ một hàng cùng ID, tên được cập nhật.
6. Không có cột `newEntity` trong schema và không có dữ liệu cờ trong SQL.

Khi cần kiểm tra đường SQL, bật log `org.springframework.jdbc` hoặc dùng datasource proxy/SQL instrumentation của dự án. Đừng chỉ assert rằng `save` không ném exception; một update zero-row và một insert thành công là hai kết quả khác nhau về nghiệp vụ.

## 14. Bài tập thực hành

**Bài tập 1 — UUID cấp tại ứng dụng.** Tạo entity `Warehouse` có UUID được cấp bằng `UUID.randomUUID()` trước khi lưu. Triển khai `Persistable<UUID>` và kiểm tra lần save đầu là insert, lần save sau là update.

**Bài tập 2 — Cờ transient.** Thêm field `newEntity` với `@Transient`. Kiểm tra schema không có cột này. Đọc entity từ repository và xác nhận cờ mặc định là false.

**Bài tập 3 — Cố ý bỏ markNotNew.** Gọi save hai lần trên cùng object khi cờ vẫn true. Quan sát lỗi khóa chính. Sau đó chuyển cờ false sau lần đầu và so sánh SQL.

**Bài tập 4 — So sánh @Version.** Tạo một entity khác có ID UUID và thuộc tính `@Version Long version`. Kiểm tra cách Spring Data nhận diện entity mới theo version, sau đó so sánh với cách triển khai `Persistable`. Giải thích khi nào version là lựa chọn đơn giản hơn.

**Bài tập 5 — Mô phỏng trạng thái sai.** Cố ý tạo một object có ID của hàng đã tồn tại nhưng `isNew()` trả true; sau đó tạo object có ID chưa tồn tại nhưng `isNew()` trả false. Quan sát hai loại lỗi khác nhau và giải thích vì sao `isNew` không phải existence check.

## 15. Ghi nhớ

Spring Data JDBC phải biết entity mới hay đã tồn tại để chọn `INSERT` hoặc `UPDATE`. Cơ chế mặc định thường dùng version property trước rồi đến ID. Khi ứng dụng cấp ID trước khi insert, ID khác null không còn là dấu hiệu đáng tin cậy cho trạng thái mới.

`Persistable<ID>` cho phép entity tự cung cấp trạng thái đó qua `isNew()`. Một triển khai phổ biến giữ cờ `@Transient` trong bộ nhớ: factory tạo entity mới đặt cờ true, service đánh dấu false sau khi save thành công, và entity đọc từ database mặc định false. Cờ này phải được quản lý nhất quán vì nó quyết định đường ghi SQL.

Hãy dùng `Persistable` khi thực sự cần kiểm soát trạng thái mới/cũ, giữ quy tắc cập nhật cờ ở một nơi rõ ràng và kiểm thử cả insert lẫn update. **`Persistable` không tự kiểm tra sự tồn tại, không thay thế constraint và không phải cơ chế upsert.**

### Tài liệu tham khảo

- [Spring Data Commons – Persistable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Persistable.html)
- [Spring Data Relational – Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational – Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
