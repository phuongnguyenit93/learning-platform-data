# Gọi thủ tục bằng EntityManager khi cần điều khiển chi tiết

## Mục tiêu

Spring Data JPA có thể gọi stored procedure bằng `@Procedure` trên repository method. Cách này gọn khi procedure có chữ ký ổn định, số tham số đơn giản và kết quả dễ ánh xạ. Khi cần kiểm soát chi tiết hơn, JPA cung cấp `EntityManager` cùng `StoredProcedureQuery` để đăng ký tham số, chọn mode `IN`/`OUT`/`INOUT`/`REF_CURSOR`, đọc output, xử lý result set và update count, đặt hint hoặc phối hợp với persistence context.

Chủ đề này tập trung vào việc gọi procedure trực tiếp bằng EntityManager, đồng thời chỉ ra khi nào nên dùng `@Procedure` và những điểm cần kiểm tra để tránh dữ liệu entity bị cũ sau khi procedure cập nhật database.

Ví dụ xuyên suốt: PostgreSQL có procedure `adjust_inventory` nhận SKU và lượng thay đổi, cập nhật tồn kho trong database và trả số lượng còn lại qua tham số `INOUT`.

## 1. Khi nào nên gọi stored procedure?

Stored procedure phù hợp khi logic cần chạy sát database hoặc đã được quản lý ở tầng database:

- Quy tắc dữ liệu cần được dùng chung bởi nhiều ứng dụng hoặc nhiều hệ thống.
- Một thao tác gồm nhiều câu SQL và cần thực thi gần dữ liệu.
- Cần dùng tính năng đặc thù của database như PL/pgSQL, T-SQL, cursor hoặc logic tối ưu riêng.
- Có thủ tục đã tồn tại trong schema và ứng dụng cần tích hợp.
- Cần quyền thực thi procedure thay vì cấp quyền trực tiếp lên một số bảng.

Không nên chuyển mọi query sang stored procedure. Derived query, JPQL và Criteria API thường dễ kiểm thử, refactor và di chuyển database hơn. Procedure cũng tạo thêm phụ thuộc vào dialect, schema migration, quyền database và cách mapping kết quả.

## 2. @Procedure và EntityManager khác nhau thế nào?

Spring Data JPA cung cấp `@Procedure` để gắn một repository method với stored procedure. EntityManager cung cấp API chuẩn JPA `StoredProcedureQuery` để kiểm soát từng bước gọi.

| Tiêu chí | `@Procedure` | `EntityManager` + `StoredProcedureQuery` |
| --- | --- | --- |
| Cách gọi | Khai báo method repository và annotation | Tạo query, đăng ký tham số rồi gọi `execute()` |
| Chữ ký đơn giản | Rất phù hợp | Nhiều mã hơn cần thiết |
| IN/OUT đơn giản | Hỗ trợ qua method parameter/return mapping | Hỗ trợ trực tiếp qua `ParameterMode` |
| Nhiều OUT parameter | Có thể cần kiểu trả về `Map` và mapping rõ ràng | Đọc từng output theo tên hoặc vị trí |
| Nhiều result set/cursor | Phụ thuộc mapping và khả năng hỗ trợ của provider | Có API duyệt result set và update count |
| Điều khiển execution | Ít chi tiết hơn | Có thể flush, execute, đọc kết quả, refresh entity và xử lý từng bước |
| Khi phù hợp | Một procedure ổn định, hợp đồng method rõ | Cần kiểm soát tham số, result mapping, cursor, persistence context hoặc luồng thực thi |

Ví dụ method repository đơn giản có thể dùng `@Procedure`. Khi cần đọc nhiều output parameter, duyệt nhiều result set hoặc phối hợp với entity đang managed, EntityManager thường dễ kiểm soát hơn.

## 3. StoredProcedureQuery là gì?

`StoredProcedureQuery` là query object của Jakarta Persistence dùng để gọi stored procedure trong database. Có thể tạo bằng EntityManager:

```java
StoredProcedureQuery query = entityManager
        .createStoredProcedureQuery("adjust_inventory");
```

Hoặc dùng overload có result class/result set mapping nếu procedure trả về hàng dữ liệu:

```java
StoredProcedureQuery query = entityManager
        .createStoredProcedureQuery("list_inventory", InventoryItem.class);
```

Procedure name là tên object trong database. Đây không phải JPQL và không phải tên entity. Tên procedure không thể bind như một giá trị parameter; nếu ứng dụng chọn procedure theo input, hãy dùng whitelist tên đã được lập trình sẵn.

### Gọi procedure theo tên trực tiếp

`createStoredProcedureQuery("adjust_inventory")` tạo query theo tên database. Cách này hữu ích khi procedure được gọi ở một nơi hoặc tên procedure phụ thuộc cấu hình deployment.

### Gọi procedure đã khai báo bằng metadata

Nếu procedure được dùng lặp lại và có chữ ký cố định, có thể khai báo `@NamedStoredProcedureQuery` trên entity:

```java
@NamedStoredProcedureQuery(
    name = "InventoryItem.adjustInventory",
    procedureName = "adjust_inventory",
    parameters = {
        @StoredProcedureParameter(name = "p_sku", type = String.class, mode = ParameterMode.IN),
        @StoredProcedureParameter(name = "p_delta", type = Integer.class, mode = ParameterMode.IN),
        @StoredProcedureParameter(name = "p_remaining", type = Integer.class, mode = ParameterMode.INOUT)
    }
)
```

Sau đó gọi bằng:

```java
StoredProcedureQuery query = entityManager
        .createNamedStoredProcedureQuery("InventoryItem.adjustInventory");
```

Named metadata giúp tập trung tên procedure và chữ ký tham số. Nếu cần điều khiển linh hoạt ở từng nơi, tạo query trực tiếp vẫn phù hợp.

## 4. Đăng ký tham số và ParameterMode

Trước khi gọi procedure, đăng ký mọi tham số bằng `registerStoredProcedureParameter`. JPA định nghĩa bốn mode chính:

| Mode | Ý nghĩa |
| --- | --- |
| `ParameterMode.IN` | Giá trị đầu vào cho procedure. |
| `ParameterMode.OUT` | Giá trị procedure trả ra. |
| `ParameterMode.INOUT` | Caller truyền giá trị ban đầu và procedure cập nhật giá trị đó. |
| `ParameterMode.REF_CURSOR` | Tham số cursor để đọc result set; hỗ trợ tùy database/provider. |

Ví dụ procedure nhận SKU, delta và trả lượng còn lại qua INOUT:

```java
query.registerStoredProcedureParameter(1, String.class, ParameterMode.IN);
query.registerStoredProcedureParameter(2, Integer.class, ParameterMode.IN);
query.registerStoredProcedureParameter(3, Integer.class, ParameterMode.INOUT);
```

Tham số có thể đăng ký theo vị trí (1-based) hoặc tên nếu database/provider hỗ trợ mapping tương ứng. Vị trí thường dễ đối chiếu với chữ ký procedure và tránh khác biệt tên parameter giữa dialect.

Sau khi đăng ký, gán giá trị IN và giá trị ban đầu cho INOUT:

```java
query.setParameter(1, "SKU-1");
query.setParameter(2, -2);
query.setParameter(3, 0);
```

Với INOUT, caller phải cung cấp giá trị đầu vào theo hợp đồng procedure; sau khi thực thi, đọc lại giá trị đầu ra bằng `getOutputParameterValue`.

### Kiểu Java phải khớp kiểu SQL

Chọn kiểu Java tương ứng với kiểu tham số database: `String` cho VARCHAR, `Integer` cho INTEGER, `Long` cho BIGINT, `BigDecimal` cho NUMERIC/DECIMAL, `LocalDate`/`LocalDateTime` hoặc kiểu thời gian phù hợp cho DATE/TIMESTAMP. Một số driver trả output dưới dạng lớp con của `Number`; có thể kiểm tra và chuyển đổi bằng `Number` thay vì ép kiểu cứng khi driver khác nhau.

Không nối chuỗi input vào tên procedure hoặc câu SQL động. Giá trị đầu vào phải được bind bằng `setParameter` để tránh SQL injection và lỗi quoting.

## 5. Thực thi procedure và đọc OUT/INOUT

`execute()` chạy procedure và trả về boolean cho biết kết quả đầu tiên có phải result set hay không:

```java
boolean hasResultSet = query.execute();
Object output = query.getOutputParameterValue(3);
```

Với procedure chỉ trả OUT/INOUT và không trả result set, có thể đọc output sau khi execute theo hợp đồng provider/database.

Ví dụ:

```java
Number remainingValue = (Number) query.getOutputParameterValue(3);
int remaining = remainingValue.intValue();
```

Output parameter phải được đăng ký trước khi execute. Không gọi `getOutputParameterValue` cho tham số chưa đăng ký hoặc không có mode OUT/INOUT/REF_CURSOR.

### Khi procedure trả result set

Nếu procedure trả result set, đọc bằng `getResultList()` hoặc `getSingleResult()` theo kiểu kết quả đã khai báo:

```java
boolean hasResultSet = query.execute();
if (hasResultSet) {
    List<?> rows = query.getResultList();
}
```

Với result set trả entity, có thể tạo query với result class. Với DTO hoặc nhiều cột, dùng `@SqlResultSetMapping` và tên mapping phù hợp.

## 6. Nhiều result set và update count

Một procedure có thể phát ra nhiều result set hoặc update count. API `StoredProcedureQuery` cho phép duyệt tuần tự:

```java
boolean hasResult = query.execute();

while (true) {
    if (hasResult) {
        List<?> rows = query.getResultList();
        // Map or process this result set.
    } else {
        int updateCount = query.getUpdateCount();
        if (updateCount == -1) {
            break;
        }
        // Record or inspect the update count.
    }

    hasResult = query.hasMoreResults();
}
```

Kết quả thực tế và số update count phụ thuộc database, JDBC driver và provider. Một số procedure không trả result set nào; một số procedure trả nhiều result set; một số provider yêu cầu cấu hình mapping cụ thể.

Với nhiều result set, cần đọc hết các kết quả theo thứ tự mà driver/provider cung cấp trước khi lấy output parameter nếu database yêu cầu. Kiểm thử với đúng engine và driver production.

## 7. REF_CURSOR và ánh xạ kết quả

Một số database, đặc biệt PostgreSQL và Oracle, hỗ trợ trả dữ liệu qua REF_CURSOR. JPA có `ParameterMode.REF_CURSOR`, nhưng khả năng và cách lấy cursor phụ thuộc database/provider.

Ví dụ đăng ký cursor:

```java
query.registerStoredProcedureParameter(
        1, void.class, ParameterMode.REF_CURSOR);
```

Với cursor, cần dùng mapping/result class phù hợp và kiểm thử việc đọc result set với provider cụ thể. Không giả định mọi database hỗ trợ REF_CURSOR giống nhau.

### Entity mapping và DTO mapping

Nếu result set có cấu trúc tương ứng entity, có thể truyền result class:

```java
StoredProcedureQuery query = entityManager.createStoredProcedureQuery(
        "list_inventory", InventoryItem.class);
```

Nếu result set gồm các cột tính toán hoặc DTO, khai báo `@SqlResultSetMapping` rồi tạo query với tên mapping:

```java
StoredProcedureQuery query = entityManager.createStoredProcedureQuery(
        "inventory_summary", "InventorySummaryMapping");
```

Mapping phải khớp tên cột, alias, kiểu dữ liệu và constructor/property của kết quả. Alias trong SQL nên ổn định để tránh lỗi khi procedure thay đổi.

## 8. Transaction và flush trước khi gọi procedure

Procedure có thể đọc hoặc ghi các bảng mà JPA cũng đang quản lý. Vì vậy, cần hiểu thứ tự đồng bộ giữa persistence context và database.

### Flush trước khi gọi

EntityManager có thể đang giữ thay đổi chưa gửi xuống database. Nếu procedure cần nhìn thấy các thay đổi đó, gọi `entityManager.flush()` trước khi thực thi:

```java
entityManager.flush();
query.execute();
```

Flush đồng bộ pending changes trong persistence context xuống database nhưng không commit transaction.

### Procedure ghi dữ liệu và entity đang managed

Procedure chạy SQL trực tiếp, không thông báo cho Hibernate rằng entity đang managed đã bị thay đổi. Entity trong persistence context có thể giữ giá trị cũ.

Có hai cách phổ biến:

- Gọi `entityManager.refresh(entity)` cho entity cụ thể sau procedure.
- Gọi `entityManager.clear()` để detach toàn bộ entity trong persistence context rồi đọc lại.

`clear()` có phạm vi rộng và có thể làm mất các thay đổi chưa flush. Vì vậy, nếu cần giữ những entity khác đang managed, hãy flush trước hoặc refresh đúng entity liên quan.

Ví dụ:

```java
entityManager.flush();
query.execute();
entityManager.refresh(inventoryItem);
```

### Transaction boundary

Procedure ghi dữ liệu nên được gọi trong transaction do Spring/JPA quản lý:

```java
@Transactional
public int adjustInventory(String sku, int delta) {
    // Register parameters, execute procedure and read output.
}
```

Không để procedure tự `COMMIT` hoặc `ROLLBACK` nếu nó được gọi trong transaction do JPA quản lý. Một số database không cho phép điều khiển transaction bên trong procedure đang chạy trong transaction block; hơn nữa việc commit riêng sẽ phá vỡ atomicity của use case.

Nếu procedure lỗi, exception cần thoát khỏi transactional method để transaction rollback. Nếu bắt exception và tiếp tục, transaction có thể đã bị đánh dấu rollback-only.

## 9. Khi nào @Procedure là đủ?

Với procedure đơn giản có input/output ổn định, repository method có thể khai báo:

```java
public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
    @Procedure(procedureName = "adjust_inventory")
    Integer adjustInventory(
            @Param("p_sku") String sku,
            @Param("p_delta") Integer delta,
            @Param("p_remaining") Integer initialRemaining
    );
}
```

Chữ ký cụ thể phụ thuộc cách procedure khai báo OUT/INOUT và database/provider. Hãy kiểm tra mapping parameter của Spring Data JPA version đang dùng. Với nhiều output parameter, Spring Data có thể dùng `Map<String, Object>` để trả về nhiều giá trị.

Dùng EntityManager khi:

- Cần đăng ký parameter mode rõ ràng theo vị trí hoặc tên.
- Cần lấy nhiều output parameter và kiểm soát thời điểm đọc.
- Cần duyệt nhiều result set hoặc REF_CURSOR.
- Cần chỉ định result class hoặc `@SqlResultSetMapping`.
- Cần flush trước, refresh/clear sau hoặc phối hợp nhiều thao tác trong một transaction.
- Cần điều khiển query hint, timeout hoặc các tùy chọn của `StoredProcedureQuery`.

## 10. Xử lý lỗi và bảo mật

### Exception

Procedure có thể phát sinh lỗi SQL, lỗi tham số, lỗi constraint hoặc lỗi nghiệp vụ do `RAISE`/`THROW`. JPA provider có thể ném `PersistenceException`; Spring exception translation có thể chuyển thành `DataAccessException` tương ứng.

Không nên bắt mọi exception rồi trả giá trị mặc định. Hãy phân biệt lỗi đầu vào, lỗi nghiệp vụ và lỗi database. Nếu procedure chạy trong transaction, để lỗi thoát ra khi cần rollback.

### Bind parameter

Luôn dùng `setParameter` cho giá trị đầu vào. Không ghép input vào dynamic SQL bên trong Java. Nếu procedure tự xây dynamic SQL, cần dùng cơ chế quote/identifier validation và parameter binding theo cú pháp database.

### Quyền thực thi

Database user của ứng dụng chỉ nên có quyền cần thiết để gọi procedure và truy cập các object liên quan. Stored procedure không tự động an toàn: kiểm tra `SECURITY DEFINER`/`EXECUTE AS`, search path, quyền trên bảng và dynamic SQL theo database.

### Timeout và hint

`StoredProcedureQuery` kế thừa khả năng cấu hình một số query hint và timeout theo JPA/provider. Tên hint và khả năng hỗ trợ phụ thuộc provider/database; hãy xác nhận bằng integration test. Không giả định timeout JPA giống socket timeout hoặc transaction timeout.

## 11. Ví dụ chạy được với Java 17+, Spring Boot 3.4.5 và PostgreSQL

Ví dụ dùng procedure `adjust_inventory` để cộng/trừ tồn kho và trả lượng còn lại bằng INOUT parameter. PostgreSQL được chạy bằng Docker Compose.

### Cấu trúc dự án

```text
entitymanager-procedure/
├── docker-compose.yml
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/procedure/
        │   ├── ProcedureApplication.java
        │   ├── InventoryItem.java
        │   ├── InventoryRepository.java
        │   └── InventoryProcedureService.java
        └── resources/
            ├── application.properties
            ├── schema.sql
            └── data.sql
```

### `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: procedures
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d procedures"]
      interval: 5s
      timeout: 3s
      retries: 20
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>entitymanager-procedure</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/procedures
spring.datasource.username=app
spring.datasource.password=app
spring.jpa.hibernate.ddl-auto=none
spring.sql.init.mode=always
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`ddl-auto=none` để Hibernate không tạo lại schema. `schema.sql` và `data.sql` tạo bảng, procedure và dữ liệu mẫu khi ứng dụng khởi động.

### `src/main/resources/schema.sql`

```sql
create table if not exists inventory_items (
    id bigint generated by default as identity primary key,
    sku varchar(60) not null unique,
    available integer not null check (available >= 0)
);

create or replace procedure adjust_inventory(
    in p_sku varchar(60),
    in p_delta integer,
    inout p_remaining integer
)
language plpgsql
as $$
begin
    update inventory_items
       set available = available + p_delta
     where sku = p_sku
       and available + p_delta >= 0
    returning available into p_remaining;

    if not found then
        if exists (select 1 from inventory_items where sku = p_sku) then
            raise exception 'Insufficient inventory for SKU %', p_sku
                using errcode = 'P0001';
        else
            raise exception 'Unknown SKU %', p_sku
                using errcode = 'P0002';
        end if;
    end if;
end;
$$;
```

Procedure cập nhật tồn kho trong một câu UPDATE có điều kiện. Nếu SKU không tồn tại hoặc số lượng sau cập nhật âm, procedure phát sinh exception và transaction có thể rollback.

### `src/main/resources/data.sql`

```sql
insert into inventory_items(sku, available)
values ('SKU-1', 10)
on conflict (sku) do nothing;
```

### `InventoryItem.java`

```java
package com.example.procedure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false)
    private int available;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getAvailable() {
        return available;
    }
}
```

### `InventoryRepository.java`

```java
package com.example.procedure;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
    Optional<InventoryItem> findBySku(String sku);
}
```

### `InventoryProcedureService.java`

```java
package com.example.procedure;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryProcedureService {
    private final EntityManager entityManager;
    private final InventoryRepository inventoryRepository;

    public InventoryProcedureService(
            EntityManager entityManager, InventoryRepository inventoryRepository) {
        this.entityManager = entityManager;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public int adjust(String sku, int delta) {
        if (sku == null || sku.isBlank() || delta == 0) {
            throw new IllegalArgumentException("sku and non-zero delta are required");
        }

        InventoryItem item = inventoryRepository.findBySku(sku)
                .orElseThrow(() -> new IllegalArgumentException("Unknown SKU: " + sku));

        // Synchronize pending JPA changes before the procedure reads the table.
        entityManager.flush();

        StoredProcedureQuery procedure =
                entityManager.createStoredProcedureQuery("adjust_inventory");
        procedure.registerStoredProcedureParameter(1, String.class, ParameterMode.IN);
        procedure.registerStoredProcedureParameter(2, Integer.class, ParameterMode.IN);
        procedure.registerStoredProcedureParameter(3, Integer.class, ParameterMode.INOUT);

        procedure.setParameter(1, sku);
        procedure.setParameter(2, delta);
        procedure.setParameter(3, 0);

        boolean hasResultSet = procedure.execute();
        if (hasResultSet) {
            throw new IllegalStateException("Expected no result set from adjust_inventory");
        }

        Number output = (Number) procedure.getOutputParameterValue(3);
        int remaining = Objects.requireNonNull(output).intValue();

        // The procedure changed the row outside Hibernate's dirty checking.
        entityManager.refresh(item);
        if (item.getAvailable() != remaining) {
            throw new IllegalStateException("Procedure output does not match refreshed entity");
        }

        return remaining;
    }
}
```

`EntityManager` được inject bằng constructor. Spring cung cấp shared proxy phù hợp với transaction hiện tại. Service đọc entity trước khi gọi procedure để minh họa `refresh`; `flush()` bảo đảm thay đổi JPA đang chờ được đồng bộ trước khi procedure chạy.

Procedure cập nhật hàng trực tiếp nên Hibernate không tự biết giá trị `available` đã đổi. `refresh(item)` tải lại entity managed. Nếu procedure cập nhật nhiều entity hoặc caller không cần giữ object managed, có thể dùng `clear()` rồi truy vấn lại; cần nhớ `clear()` detach mọi entity trong persistence context.

### `ProcedureApplication.java`

```java
package com.example.procedure;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ProcedureApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProcedureApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(InventoryProcedureService service) {
        return args -> {
            int remaining = service.adjust("SKU-1", -2);
            System.out.println("Remaining inventory: " + remaining);
        };
    }
}
```

### Chạy chương trình

Khởi động PostgreSQL:

```bash
docker compose up -d --wait
```

Chạy Spring Boot:

```bash
mvn spring-boot:run
```

Stdout:

```text
Remaining inventory: 8
```

Dữ liệu ban đầu có 10 sản phẩm. Procedure nhận `p_delta = -2`, cập nhật tồn kho còn 8 và trả giá trị đó qua `p_remaining`. Service đọc OUT/INOUT parameter rồi refresh entity để trạng thái persistence context khớp database.

## 12. Kiểm thử stored procedure

Integration test cần chạy trên đúng database engine vì cú pháp procedure và parameter binding phụ thuộc dialect. Có thể dùng Testcontainers PostgreSQL hoặc database container trong CI.

Ví dụ test service:

```java
@SpringBootTest
class InventoryProcedureIntegrationTest {
    @Autowired
    private InventoryProcedureService service;

    @Autowired
    private InventoryRepository repository;

    @Test
    void readsInOutValueAndRefreshesManagedEntity() {
        repository.saveAndFlush(new InventoryItem("TEST-1", 5));

        int remaining = service.adjust("TEST-1", -2);

        assertThat(remaining).isEqualTo(3);
        assertThat(repository.findBySku("TEST-1").orElseThrow().getAvailable())
                .isEqualTo(3);
    }
}
```

Đoạn test minh họa assertion; để chạy độc lập cần thêm constructor tạo `InventoryItem(String sku, int available)` cùng getter như entity mẫu, thêm import JUnit/AssertJ và cấu hình database test. Nên kiểm thử thêm:

- SKU không tồn tại.
- Delta làm tồn kho âm.
- Delta dương để nhập thêm hàng.
- Procedure rollback khi phát sinh exception.
- OUT/INOUT parameter đúng kiểu và đúng giá trị.
- Entity managed được refresh sau khi procedure ghi.
- Nhiều result set hoặc REF_CURSOR nếu procedure thực tế có trả.

## 13. Lỗi thường gặp

1. **Dùng @Procedure cho luồng quá phức tạp:** chuyển sang EntityManager khi cần điều khiển nhiều output, result set, cursor hoặc persistence context.
2. **Quên register parameter:** đăng ký mọi tham số với đúng vị trí/tên, kiểu và mode trước khi execute.
3. **Nhầm OUT với INOUT:** INOUT cần giá trị đầu vào ban đầu và trả giá trị đã thay đổi.
4. **Đọc output trước khi execute:** chỉ đọc sau khi procedure đã chạy và provider đã hoàn tất xử lý kết quả cần thiết.
5. **Giả định procedure luôn trả result set:** `execute()` có thể trả false; kiểm tra kết quả đầu tiên và duyệt các kết quả tiếp theo nếu có.
6. **Ép kiểu output cứng:** driver có thể trả lớp con `Number`; kiểm tra kiểu hoặc chuyển đổi có kiểm soát.
7. **Không flush trước procedure:** procedure có thể không nhìn thấy thay đổi JPA chưa gửi xuống database.
8. **Không refresh entity sau procedure:** persistence context có thể giữ giá trị cũ vì procedure cập nhật trực tiếp database.
9. **Gọi clear mà chưa flush:** có thể detach entity và làm mất thay đổi chưa đồng bộ.
10. **Procedure tự commit trong transaction JPA:** có thể phá atomicity hoặc bị database từ chối.
11. **Dùng H2 để xác nhận PostgreSQL/Oracle cursor:** cú pháp, OUT parameter và REF_CURSOR phụ thuộc engine/driver.
12. **Ghép input vào dynamic SQL:** bind giá trị và kiểm soát identifier bằng whitelist.
13. **Không quản lý schema migration:** version procedure cần được triển khai cùng schema bằng Flyway/Liquibase hoặc migration tool tương đương.
14. **Cấp quyền database quá rộng:** chỉ cấp quyền EXECUTE và quyền cần thiết theo thiết kế bảo mật.

## 14. Checklist trước khi dùng EntityManager gọi procedure

- [ ] Procedure có thật trong schema và đúng tên theo database.
- [ ] Đã xác định rõ thứ tự hoặc tên, kiểu và mode của mọi parameter.
- [ ] INOUT có giá trị đầu vào và output được đọc sau execute.
- [ ] Result set, update count và REF_CURSOR được xử lý đúng nếu có.
- [ ] EntityManager flush trước procedure khi cần đồng bộ pending changes.
- [ ] Entity managed được refresh/clear sau khi procedure cập nhật dữ liệu.
- [ ] Procedure chạy trong transaction phù hợp và không tự commit/rollback ngoài hợp đồng.
- [ ] Input được bind parameter; procedure name/identifier được whitelist.
- [ ] Quyền EXECUTE và quyền truy cập bảng được cấp tối thiểu.
- [ ] Integration test chạy trên database engine và JDBC driver mục tiêu.

## 15. Nguyên tắc thực hành

- Dùng `@Procedure` cho chữ ký procedure đơn giản, ổn định và dễ ánh xạ vào method repository.
- Dùng `EntityManager.createStoredProcedureQuery` khi cần điều khiển parameter mode, output, result set, cursor hoặc persistence context.
- Đăng ký đầy đủ parameter trước khi gán giá trị và execute.
- Dùng `IN`, `OUT`, `INOUT` và `REF_CURSOR` đúng hợp đồng database.
- Dùng `execute()`, `getResultList()`, `hasMoreResults()`, `getUpdateCount()` và `getOutputParameterValue()` theo kiểu kết quả procedure trả về.
- Flush trước khi procedure cần nhìn thấy thay đổi JPA chưa đồng bộ.
- Refresh entity hoặc clear persistence context sau khi procedure cập nhật dữ liệu.
- Để Spring quản lý transaction; tránh transaction control bên trong procedure được gọi từ JPA.
- Kiểm thử trên đúng database/provider/driver vì stored procedure không portable hoàn toàn.

Điểm cốt lõi: **`@Procedure` phù hợp với lời gọi đơn giản; `EntityManager` và `StoredProcedureQuery` phù hợp khi cần điều khiển chi tiết tham số, output, result set/cursor và đồng bộ persistence context. Hãy bind tham số đúng mode, flush trước khi procedure cần dữ liệu mới, refresh entity sau khi procedure ghi và để transaction do Spring/JPA quản lý.**