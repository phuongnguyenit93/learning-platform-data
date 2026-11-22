# Ánh xạ hệ phân cấp bằng TABLE_PER_CLASS

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Kế thừa

Trong Java, kế thừa giúp mô hình hóa những đối tượng có thuộc tính và hành vi chung. Ví dụ, hệ thống quản lý phương tiện có lớp cha `Vehicle` và các lớp con `Car`, `Motorcycle`. Cả hai đều có mã tài sản và tên hiển thị, nhưng ô tô có số chỗ ngồi, còn xe máy có dung tích động cơ.

Khi các lớp đó là **entity JPA**, câu hỏi không chỉ là “Java class nào kế thừa class nào?”, mà còn là **dữ liệu của từng loại được lưu trong những bảng nào**. Một trong ba chiến lược ánh xạ hệ phân cấp entity là `InheritanceType.TABLE_PER_CLASS`: **mỗi lớp entity cụ thể (*concrete entity class*) có một bảng riêng chứa cả các cột kế thừa lẫn cột riêng của lớp đó**.

Chiến lược này có ưu điểm là mỗi bảng tự chứa dữ liệu đầy đủ cho một loại cụ thể, nhưng phải đánh đổi bằng sự trùng lặp schema, cách sinh ID cần được thiết kế cẩn thận, và truy vấn đa hình thường phải kết hợp dữ liệu từ nhiều bảng. Bài học trình bày cơ chế, ví dụ code và các quyết định thiết kế thực tế để sử dụng `TABLE_PER_CLASS` đúng mục đích.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ngữ nghĩa của `@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)`.
2. Phân biệt **lớp cha Java**, **entity cha trừu tượng** và **`@MappedSuperclass`** trong JPA.
3. Ánh xạ một hệ phân cấp bằng `@Entity` trên lớp cha và các lớp con, dùng `@Table` cho từng lớp cụ thể.
4. Vẽ schema mà mỗi bảng con chứa **các cột được kế thừa** cùng **các cột riêng**.
5. Hiểu vì sao truy vấn JPQL trên kiểu cha có thể cần `UNION`/`UNION ALL`.
6. Viết các thao tác `persist`, `find` và truy vấn cho kiểu con, cũng như truy vấn đa hình trên kiểu cha.
7. Chọn chiến lược sinh khóa phù hợp, đặc biệt là **sequence dùng chung** để tránh xung đột định danh trong hệ phân cấp.
8. Nhận biết khó khăn khi một bảng khác cần **foreign key đến kiểu cha đa hình**.
9. So sánh `TABLE_PER_CLASS` với `SINGLE_TABLE`, `JOINED` và `@MappedSuperclass`.
10. Nhận biết tác động đến index, constraint, schema migration, hiệu năng, optimistic locking và mở rộng hệ phân cấp.

## 2. Từ mô hình Java đến mô hình quan hệ

### 2.1. Mô hình đối tượng

Giả sử miền nghiệp vụ quản lý phương tiện:

```text
              Vehicle
        (abstract @Entity)
       /                  \
      /                    \
    Car                  Motorcycle
  - seatCount            - engineCc

Thuộc tính chung của Vehicle:
  - id
  - assetCode
  - displayName
  - version
```

Trong Java:

```java
Vehicle first = new Car("CAR-001", "Sedan A", 5);
Vehicle second = new Motorcycle("BIKE-001", "Bike B", 150);
```

Cả hai có thể được dùng qua biến kiểu `Vehicle`. Tuy nhiên, thông tin loại cụ thể quyết định những thuộc tính riêng nào tồn tại và thao tác nào hợp lệ.

### 2.2. Mô hình bảng với TABLE_PER_CLASS

Nếu chọn `TABLE_PER_CLASS`, schema có thể là:

```text
cars
+----+------------+--------------+---------+------------+
| id | asset_code | display_name | version | seat_count |
+----+------------+--------------+---------+------------+
|  1 | CAR-001    | Sedan A      |       0 |          5 |
+----+------------+--------------+---------+------------+

motorcycles
+----+------------+--------------+---------+-----------+
| id | asset_code | display_name | version | engine_cc |
+----+------------+--------------+---------+-----------+
|  2 | BIKE-001   | Bike B       |       0 |       150 |
+----+------------+--------------+---------+-----------+
```

**Không bắt buộc có bảng `vehicles` riêng** khi `Vehicle` là một entity cha **abstract** và chỉ hai lớp con cụ thể mới có bản ghi. Mỗi bảng chứa:

- Các cột được kế thừa từ `Vehicle`: `id`, `asset_code`, `display_name`, `version`.
- Các cột đặc thù của lớp con: `seat_count` hoặc `engine_cc`.

Đây chính là ý nghĩa “table per concrete class”.

### 2.3. So với JOINED trong một hình

```text
TABLE_PER_CLASS

cars                      motorcycles
  id                        id
  asset_code                asset_code
  display_name              display_name
  version                   version
  seat_count                engine_cc

Không phải JOIN với bảng cha để đọc đầy đủ một Car.


JOINED

vehicles
  id, asset_code, display_name, version

cars                      motorcycles
  id (PK + FK)              id (PK + FK)
  seat_count                engine_cc

Đọc đầy đủ một Car thường cần JOIN vehicles + cars.
```

`TABLE_PER_CLASS` lặp các cột chung ở nhiều bảng. `JOINED` tách phần chung thành bảng cha. Hai thiết kế khác nhau cả về schema, foreign key và chi phí truy vấn.

## 3. Quy tắc ánh xạ cốt lõi của TABLE_PER_CLASS

Chọn chiến lược ở **root của hệ phân cấp entity**:

```java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Vehicle {
    // Các thuộc tính chung.
}
```

Sau đó, mỗi lớp con cụ thể khai báo `@Entity` và bảng riêng:

```java
@Entity
@Table(name = "cars")
public class Car extends Vehicle {
    // Các thuộc tính chỉ có ở Car.
}

@Entity
@Table(name = "motorcycles")
public class Motorcycle extends Vehicle {
    // Các thuộc tính chỉ có ở Motorcycle.
}
```

Có một số điểm cần hiểu đúng:

- `@Inheritance` đặt tại root entity để quyết định chiến lược cho hệ phân cấp.
- Lớp cha vẫn là `@Entity`, dù được khai báo `abstract`. Vì vậy nó có thể đóng vai trò **kiểu entity đa hình** trong JPQL, theo khả năng hỗ trợ của provider.
- Các lớp con có `@Entity` riêng, nhưng **không khai báo lại `@Id`** nếu định danh đã được thừa kế từ root.
- Mỗi lớp con cụ thể có bảng chứa cả field inherited và field riêng.
- Nếu root là **concrete** (có thể tạo instance của chính root), root cũng thuộc nhóm concrete entity và cần bảng tương ứng.
- `TABLE_PER_CLASS` không có nghĩa database sử dụng tính năng “table inheritance” riêng của PostgreSQL hoặc hệ quản trị cụ thể. Nó là **chiến lược ORM**, có thể được triển khai trên các bảng quan hệ thông thường.

**Lưu ý tính tương thích:** mức độ hỗ trợ và tối ưu `TABLE_PER_CLASS` có thể khác nhau giữa các JPA provider. Hibernate ORM hỗ trợ mô hình này, nhưng cách dựng SQL, sinh khóa và giới hạn một số truy vấn/association phụ thuộc provider và phiên bản. Hãy kiểm tra với stack thực tế trước khi dùng một hành vi provider-specific làm giả định thiết kế.

## 4. Ví dụ hoàn chỉnh: lớp cha Vehicle

Ta dùng Jakarta Persistence với ID `Long` được sinh bằng **một sequence dùng chung**. Việc dùng sequence chung là lựa chọn có chủ đích: mọi lớp con dùng một dải ID để tránh việc hai bảng tự sinh những ID trùng nhau khi truy vấn và tham chiếu đa hình.

File `Vehicle.java`:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Version;

import java.util.Objects;

@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
@SequenceGenerator(
    name = "vehicle_id_generator",
    sequenceName = "vehicle_id_seq",
    allocationSize = 1
)
public abstract class Vehicle {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "vehicle_id_generator"
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, length = 40)
    private String assetCode;

    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Vehicle() {
        // JPA cần constructor không tham số.
    }

    protected Vehicle(String assetCode, String displayName) {
        this.assetCode = requireText(assetCode, "assetCode");
        this.displayName = requireText(displayName, "displayName");
    }

    private static String requireText(String input, String field) {
        Objects.requireNonNull(input, field);

        String normalized = input.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                field + " must not be blank");
        }
        return normalized;
    }

    public Long getId() {
        return id;
    }

    public String getAssetCode() {
        return assetCode;
    }

    public String getDisplayName() {
        return displayName;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String replacement) {
        this.displayName = requireText(replacement, "displayName");
    }
}
```

**Phân tích:**

1. `Vehicle` là abstract entity, không phải `@MappedSuperclass`.
2. `@Inheritance(TABLE_PER_CLASS)` chỉ ra chiến lược mapping cho các subclass entity.
3. `@Id` nằm tại root; `Car` và `Motorcycle` thừa kế định nghĩa ID.
4. `@SequenceGenerator` đặt ở root để các subtype sử dụng **cùng một sequence** trong ví dụ.
5. `allocationSize = 1` giúp việc minh họa cấp ID đơn giản; trong hệ thống ghi nhiều cần cân nhắc cấp phát theo nhóm tương thích với sequence/database và provider.
6. `@Version` cũng được kế thừa. Mỗi bảng concrete chứa một cột version để phục vụ optimistic locking trên bản ghi của subtype đó.
7. `rename` là hành vi chung của Vehicle; khi gọi trên managed `Car` hoặc `Motorcycle`, provider sẽ cập nhật bảng của lớp cụ thể.
8. Trường `id` không có setter công khai. Không tự sửa định danh của managed entity.

### 4.1. Entity Car

File `Car.java`:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "cars")
public class Car extends Vehicle {

    @Column(name = "seat_count", nullable = false)
    private int seatCount;

    protected Car() {
        // JPA
    }

    public Car(String assetCode,
               String displayName,
               int seatCount) {
        super(assetCode, displayName);

        if (seatCount <= 0) {
            throw new IllegalArgumentException(
                "Seat count must be positive");
        }

        this.seatCount = seatCount;
    }

    public int getSeatCount() {
        return seatCount;
    }

    public void changeSeatCount(int replacement) {
        if (replacement <= 0) {
            throw new IllegalArgumentException(
                "Seat count must be positive");
        }

        this.seatCount = replacement;
    }
}
```

`Car` chỉ khai báo field `seatCount`. JPA vẫn ánh xạ các field inherited từ `Vehicle` vào **cùng bảng `cars`**. Không cần định nghĩa lại `assetCode`, `displayName` hoặc `id` ở `Car`.

### 4.2. Entity Motorcycle

File `Motorcycle.java`:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "motorcycles")
public class Motorcycle extends Vehicle {

    @Column(name = "engine_cc", nullable = false)
    private int engineCc;

    protected Motorcycle() {
        // JPA
    }

    public Motorcycle(String assetCode,
                      String displayName,
                      int engineCc) {
        super(assetCode, displayName);

        if (engineCc <= 0) {
            throw new IllegalArgumentException(
                "Engine capacity must be positive");
        }

        this.engineCc = engineCc;
    }

    public int getEngineCc() {
        return engineCc;
    }

    public void changeEngineCc(int replacement) {
        if (replacement <= 0) {
            throw new IllegalArgumentException(
                "Engine capacity must be positive");
        }

        this.engineCc = replacement;
    }
}
```

Cả hai subtype kế thừa Java behavior và persistent attributes từ `Vehicle`, nhưng dữ liệu được lưu ở **hai bảng vật lý khác nhau**.

## 5. Schema và sequence được tạo như thế nào?

Một schema minh họa cho H2/PostgreSQL có thể là:

```sql
CREATE SEQUENCE vehicle_id_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE cars (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    version BIGINT NOT NULL,
    seat_count INTEGER NOT NULL,
    CONSTRAINT chk_cars_seats
        CHECK (seat_count > 0)
);

CREATE TABLE motorcycles (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    version BIGINT NOT NULL,
    engine_cc INTEGER NOT NULL,
    CONSTRAINT chk_motorcycle_engine
        CHECK (engine_cc > 0)
);
```

DDL này phục vụ mục đích minh họa: cú pháp sequence, cách khai báo constraint và kiểu dữ liệu phụ thuộc database. Trên hệ thống thật, migration phải tạo sequence và bảng đúng với cấu hình provider.

Các điểm quan trọng:

- **Không có bảng `vehicles` trong ví dụ.** Root abstract chỉ định nghĩa mapping và kiểu đa hình.
- `cars.id` và `motorcycles.id` là PK của **từng bảng**.
- Mỗi bảng chứa đầy đủ cột chung `asset_code`, `display_name`, `version`.
- Cột chuyên biệt chỉ có ở bảng subtype tương ứng.
- `vehicle_id_seq` là một đối tượng sinh khóa dùng chung, không phải bảng chứa dữ liệu Vehicle.
- Không có DB-level FK từ `cars.id` hoặc `motorcycles.id` về `vehicles.id` vì không tồn tại bảng cha ở thiết kế này.

### 5.1. Vì sao mỗi bảng đều lặp cột chung?

`TABLE_PER_CLASS` ưu tiên **mỗi loại concrete có dữ liệu tự chứa**, nên đọc một Car không phải JOIN với bảng Vehicle. Đổi lại, nếu muốn thêm một thuộc tính chung mới như `registeredAt`, bạn thường phải thêm cột đó vào **mọi bảng concrete**.

Ví dụ khi yêu cầu mới thêm `registered_at` vào `Vehicle`:

```sql
ALTER TABLE cars
ADD COLUMN registered_at DATE;

ALTER TABLE motorcycles
ADD COLUMN registered_at DATE;
```

Với hệ phân cấp có 20 subtype, việc thay đổi một field chung có thể đòi hỏi cập nhật 20 bảng, index, migration và dữ liệu cũ. Đây là một trong những chi phí kiến trúc quan trọng của `TABLE_PER_CLASS`.

### 5.2. Không tự động có constraint unique xuyên tất cả bảng

Giả sử domain yêu cầu `assetCode` duy nhất **trên toàn bộ hệ phân cấp**, tức không được có:

```text
cars.asset_code = "X-001"
motorcycles.asset_code = "X-001"
```

Đặt:

```sql
UNIQUE (asset_code)
```

riêng trên bảng `cars` và riêng trên `motorcycles` **chỉ ngăn trùng trong từng bảng**. Nó không tự kiểm tra uniqueness giữa hai bảng.

Nếu tính duy nhất toàn hệ phân cấp là invariant quan trọng, cần cơ chế khác, chẳng hạn một bảng registry chung quản lý mã, policy cấp mã với constraint phù hợp, hoặc chọn `SINGLE_TABLE`/`JOINED` để có một nơi dùng chung cho định danh. Không kỳ vọng `TABLE_PER_CLASS` tự tạo global unique constraint từ một annotation trên root.

## 6. Persist một instance: chỉ ghi bảng concrete

Một đối tượng có kiểu runtime `Car`:

```java
Car car = new Car("CAR-001", "Sedan A", 5);
em.persist(car);
```

được lưu trong bảng `cars`. JPA không lưu một hàng chung vào bảng `vehicles` vì root của ví dụ không có bảng.

Dòng dữ liệu:

```text
Java:
    new Car("CAR-001", "Sedan A", 5)
      |
      +-- inherited assetCode, displayName
      +-- Car-specific seatCount
      |
      v
JPA:
    persist(car)
      |
      +-- Lấy ID từ shared sequence
      +-- INSERT vào cars
      |
      v
Database:
    cars(id, asset_code, display_name, version, seat_count)
```

SQL minh họa:

```sql
-- Tùy dialect/provider, cú pháp lấy sequence có thể khác.
SELECT NEXT VALUE FOR vehicle_id_seq;

INSERT INTO cars (
    id, asset_code, display_name, version, seat_count
)
VALUES (
    1, 'CAR-001', 'Sedan A', 0, 5
);
```

Một `Motorcycle` tương tự được INSERT vào `motorcycles`, không vào `cars`:

```sql
INSERT INTO motorcycles (
    id, asset_code, display_name, version, engine_cc
)
VALUES (
    2, 'BIKE-001', 'Bike B', 0, 150
);
```

`SELECT NEXT VALUE` chỉ là SQL mô phỏng; PostgreSQL có thể dùng `nextval(...)`, database khác dùng cú pháp khác. Hibernate có thể cấp phát ID theo một thuật toán tối ưu, chứ không nhất thiết phát một câu SELECT cho mỗi entity nếu cấu hình generator cho phép.

### 6.1. Một chương trình Java SE hoàn chỉnh

Giả sử persistence unit có tên `vehiclePU`, khai báo cả ba entity trong package `demo.domain`, dùng provider tương thích cùng JDBC driver. Chương trình có thể tạo hai loại Vehicle trong một transaction:

```java
package demo;

import demo.domain.Car;
import demo.domain.Motorcycle;
import demo.domain.Vehicle;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class VehicleDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("vehiclePU");

        try {
            persistVehicles(emf);
            queryVehicles(emf);
        } finally {
            emf.close();
        }
    }

    private static void persistVehicles(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            tx.begin();

            try {
                Car car = new Car("CAR-001", "Sedan A", 5);
                Motorcycle motorcycle =
                    new Motorcycle("BIKE-001", "Bike B", 150);

                em.persist(car);
                em.persist(motorcycle);

                tx.commit();

                System.out.println("Car ID: " + car.getId());
                System.out.println(
                    "Motorcycle ID: " + motorcycle.getId());
            } catch (RuntimeException failure) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            }
        } finally {
            em.close();
        }
    }

    private static void queryVehicles(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            java.util.List<Vehicle> all = em.createQuery(
                "select v from Vehicle v order by v.id",
                Vehicle.class
            ).getResultList();

            for (Vehicle vehicle : all) {
                System.out.println(
                    vehicle.getClass().getSimpleName()
                    + " id=" + vehicle.getId()
                    + " code=" + vehicle.getAssetCode()
                );
            }
        } finally {
            em.close();
        }
    }
}
```

Với một Hibernate configuration phổ biến, danh sách `all` gồm cả `Car` và `Motorcycle`, vì JPQL trên root entity `Vehicle` có tính đa hình. Thứ tự `order by v.id` là yêu cầu sắp xếp kết quả; nó không chứng minh ID tăng tương ứng thứ tự commit trong hệ thống đồng thời.

Mọi thao tác ghi cần transaction phù hợp. `EntityManager` được đóng ở từng phương thức; `EntityManagerFactory` chỉ đóng khi ứng dụng kết thúc.

### 6.2. persistence.xml tham khảo

File `src/main/resources/META-INF/persistence.xml`, dùng Hibernate ORM và H2 cho bài thực hành:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
             version="3.0">

    <persistence-unit name="vehiclePU"
                      transaction-type="RESOURCE_LOCAL">

        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.domain.Vehicle</class>
        <class>demo.domain.Car</class>
        <class>demo.domain.Motorcycle</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:vehicle_demo;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>

            <!-- Chỉ dùng với database thử nghiệm. -->
            <property name="hibernate.hbm2ddl.auto"
                      value="create-drop"/>
            <property name="hibernate.show_sql"
                      value="true"/>
            <property name="hibernate.format_sql"
                      value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Dự án phải có Jakarta Persistence API, Hibernate ORM và H2 driver tương thích. `hibernate.*` là cấu hình của Hibernate, không phải thuộc tính chuẩn cho mọi JPA provider.

Cấu hình `create-drop` có thể xóa dữ liệu thử nghiệm; **không dùng tùy tiện với database thật**. Môi trường production cần schema migration được quản lý và phải tạo sequence `vehicle_id_seq` cùng các bảng tương ứng.

## 7. Truy vấn đa hình: vì sao SQL có thể cần UNION?

Đây là điểm khác biệt lớn nhất về hiệu năng và cách vận hành của `TABLE_PER_CLASS`.

Giả sử query JPQL:

```java
List<Vehicle> vehicles = em.createQuery(
    "select v from Vehicle v", Vehicle.class
).getResultList();
```

Ứng dụng chỉ yêu cầu danh sách `Vehicle`, nhưng dữ liệu thực tế nằm ở **hai bảng không có bảng cha chung**. Provider cần kết hợp các hàng từ cả `cars` lẫn `motorcycles`.

Một SQL minh họa về mặt ý tưởng:

```sql
SELECT x.id,
       x.asset_code,
       x.display_name,
       x.version,
       x.seat_count,
       x.engine_cc,
       x.vehicle_type
FROM (
    SELECT c.id,
           c.asset_code,
           c.display_name,
           c.version,
           c.seat_count,
           CAST(NULL AS INTEGER) AS engine_cc,
           'CAR' AS vehicle_type
    FROM cars c

    UNION ALL

    SELECT m.id,
           m.asset_code,
           m.display_name,
           m.version,
           CAST(NULL AS INTEGER) AS seat_count,
           m.engine_cc,
           'MOTORCYCLE' AS vehicle_type
    FROM motorcycles m
) x;
```

**Đây không phải SQL cố định mà JPA cam kết phát ra.** Hibernate có thể tạo một dạng subquery UNION với mã phân biệt loại tổng hợp; provider khác có thể dùng cách khác. Ví dụ cho thấy logic cần thiết:

1. Cột chung xuất hiện ở cả hai nhánh query.
2. Cột riêng của Car không tồn tại trong bảng Motorcycle, nên nhánh Motorcycle có thể đưa giá trị `NULL` được cast sang kiểu phù hợp.
3. Provider cần biết mỗi hàng đại diện `Car` hay `Motorcycle` để tạo đúng object.
4. `UNION ALL` chỉ kết hợp hàng mà không tự loại trùng; cách lựa chọn `UNION`/`UNION ALL` tùy implementation và ngữ nghĩa SQL được provider đảm bảo.

### 7.1. Đọc subtype trực tiếp thường đơn giản hơn

Nếu use case chỉ cần Car, hãy truy vấn đúng entity subtype:

```java
List<Car> cars = em.createQuery(
    "select c from Car c where c.seatCount >= :minimum",
    Car.class
)
.setParameter("minimum", 4)
.getResultList();
```

Với schema ví dụ, provider thường chỉ cần truy cập bảng `cars` vì không phải tìm Motorcycle. Đây là lợi thế của `TABLE_PER_CLASS` khi **đường đọc chủ yếu theo từng subtype cụ thể**.

### 7.2. Query root với điều kiện chung

```java
List<Vehicle> matches = em.createQuery(
    "select v from Vehicle v " +
    "where v.assetCode like :prefix",
    Vehicle.class
)
.setParameter("prefix", "CAR-%")
.getResultList();
```

Dù dữ liệu phù hợp hiện chỉ nằm trong bảng Car, query gõ kiểu root có thể vẫn phải thực hiện một kế hoạch kết hợp dữ liệu các bảng. Provider/optimizer có thể đẩy predicate hoặc loại nhánh trong một số điều kiện, nhưng **không nên mặc định** rằng SQL chỉ đọc một bảng chỉ vì prefix trông giống một subtype.

Nếu nghiệp vụ biết chắc subtype cần tìm, truy vấn trực tiếp theo subtype có thể đơn giản và dễ tối ưu hơn.

### 7.3. TYPE và TREAT trong JPQL

JPQL có các công cụ phục vụ truy vấn hệ phân cấp:

- `TYPE(v)` biểu diễn kiểu entity của object trong query.
- `TREAT(...)` cho phép diễn đạt truy cập thuộc tính của subtype khi đang dùng biến ở kiểu cha, theo cú pháp và hỗ trợ của provider.

Ví dụ lọc theo loại:

```java
List<Vehicle> carsOnly = em.createQuery(
    "select v from Vehicle v where type(v) = Car",
    Vehicle.class
).getResultList();
```

Với thuộc tính chuyên biệt của Car, một cách rõ ràng và thường dễ tối ưu là truy vấn trực tiếp:

```java
List<Car> familyCars = em.createQuery(
    "select c from Car c where c.seatCount >= :seats",
    Car.class
)
.setParameter("seats", 5)
.getResultList();
```

Các truy vấn dùng `TYPE` hoặc `TREAT` trên `TABLE_PER_CLASS` có thể được provider chuyển thành SQL phức tạp hoặc bị giới hạn ở một số trường hợp. Khi query đa hình là đường quan trọng, hãy kiểm tra cú pháp JPQL và SQL sinh ra trên đúng phiên bản provider.

### 7.4. ORDER BY, GROUP BY và phân trang trên query đa hình

Khi query các subtype cùng lúc:

```java
List<Vehicle> page = em.createQuery(
    "select v from Vehicle v order by v.assetCode",
    Vehicle.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

Provider có thể cần sắp xếp một tập dữ liệu kết hợp từ nhiều bảng rồi mới chọn trang. Nếu hệ thống có hàng triệu Vehicle phân bổ qua nhiều bảng, việc phân trang đa hình có thể tốn tài nguyên hơn so với phân trang trên một bảng có index phù hợp.

Các thao tác aggregate như `count(v)`, `group by` hoặc lọc theo field chung cũng có thể yêu cầu tổng hợp qua nhiều bảng. Hãy quan sát query plan của SQL thực tế, không dự đoán hiệu năng chỉ từ cú pháp JPQL ngắn.

## 8. Cơ chế sinh ID: vì sao phải đặc biệt cẩn thận?

Giả sử mỗi bảng tự tăng ID riêng bằng IDENTITY:

```text
cars
  id=1 -> Car A
  id=2 -> Car B

motorcycles
  id=1 -> Motorcycle A
  id=2 -> Motorcycle B
```

Từng bảng có PK hợp lệ, nhưng trong một hệ phân cấp entity đa hình, `Vehicle#1` **không còn là một định danh đủ rõ ràng** nếu loại concrete không được xét cùng. Điều này gây khó cho polymorphic identity, lookup và những association tới root.

Với Hibernate và chiến lược table-per-class/union-subclass, **identity generator trên từng bảng thường không phù hợp** vì ID cần được xử lý trên toàn hệ phân cấp. Nhiều cấu hình Hibernate từ chối dùng `GenerationType.IDENTITY` cho kiểu inheritance này.

### 8.1. Dùng một sequence chung

Trong ví dụ chính:

```java
@SequenceGenerator(
    name = "vehicle_id_generator",
    sequenceName = "vehicle_id_seq",
    allocationSize = 1
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "vehicle_id_generator"
)
private Long id;
```

Các subtype cùng xin ID từ `vehicle_id_seq`:

```text
vehicle_id_seq
    |
    +-- Car        -> id=1
    +-- Motorcycle -> id=2
    +-- Car        -> id=3
    +-- Motorcycle -> id=4
```

Dải ID cấp ra là chung, nên một ID không bị cấp hai lần cho hai subtype trong quá trình cấp phát bình thường theo cấu hình này.

**Giới hạn quan trọng:** sequence chung giúp tổ chức việc cấp khóa nhưng **không tự tạo một database UNIQUE constraint xuyên hai bảng**. Nếu dữ liệu được import thủ công, sửa ID ngoài ứng dụng hoặc nhiều hệ thống dùng generator khác nhau, vẫn có nguy cơ hai bảng chứa cùng ID. Cần chính sách nhất quán cho tất cả đường ghi.

### 8.2. allocationSize và schema sequence

`allocationSize` là cấu hình cấp phát khóa ở phía JPA. Khi dùng `allocationSize > 1`, provider có thể áp dụng thuật toán tối ưu cấp ID theo nhóm. Cách phối hợp giữa cấu hình generator và increment của database phụ thuộc provider/phiên bản, và không nên đoán chỉ từ một thuộc tính.

Với bài học, `allocationSize = 1` và sequence tăng từng đơn vị giúp dễ theo dõi. Nếu ứng dụng ghi hàng loạt, có thể chọn cấu hình cấp phát lớn hơn, nhưng cần tạo/migrate sequence tương thích và đo SQL thực tế.

### 8.3. ID do ứng dụng cấp cũng là lựa chọn

Một thiết kế khác là cấp khóa bất biến ngay khi tạo object, ví dụ UUID:

```java
@Id
@Column(name = "id", nullable = false, updatable = false)
private UUID id;
```

Nếu ứng dụng cấp UUID trước khi persist và bảo đảm không thay đổi, định danh ít phụ thuộc database. Tuy nhiên, phải thiết kế constructor/factory, độ dài/kiểu cột, index, cách truyền ID và xử lý dữ liệu cũ tương ứng. Không được vừa tự gán ID vừa giữ cấu hình `@GeneratedValue(strategy=IDENTITY)` rồi giả định provider sẽ chấp nhận.

### 8.4. Vì sao không dựa mù quáng vào AUTO?

`GenerationType.AUTO` để provider chọn cách sinh khóa phù hợp. Với `TABLE_PER_CLASS`, lựa chọn thực tế có thể phụ thuộc dialect/provider, và không nên giả định nó sẽ dùng shared sequence theo mong muốn của hệ thống.

Nếu dải ID chung là một ràng buộc kiến trúc, khai báo generator rõ ràng và kiểm tra schema sẽ dễ kiểm soát hơn.

## 9. EntityManager quản lý identity và lifecycle ra sao?

Dù mỗi subtype lưu ở bảng riêng, `Car` và `Motorcycle` vẫn là entity JPA. Chúng tuân theo các trạng thái persistence thông thường:

```text
new/transient
    |
    | em.persist(...)
    v
managed
    |
    | flush / commit
    v
dữ liệu nằm trong bảng concrete
    |
    | em.detach(...) / em.close()
    v
detached
```

### 9.1. Tìm theo subtype

```java
Car car = em.find(Car.class, carId);
Motorcycle motorcycle = em.find(Motorcycle.class, motorcycleId);
```

Đây là các lookup rõ loại entity, thường có thể dùng trực tiếp bảng subtype tương ứng.

### 9.2. Tìm qua kiểu cha

Khi dùng kiểu cha entity `Vehicle`, provider hỗ trợ TABLE_PER_CLASS có thể thực hiện query/lookup đa hình. Nhưng vì các hàng ở nhiều bảng, truy xuất theo root thường phức tạp hơn. Đừng dựa vào một tên bảng `vehicles` không tồn tại.

Trong ứng dụng, nếu đã biết subtype từ nghiệp vụ hoặc API, dùng `em.find(Car.class, id)` có thể đơn giản hơn việc cần phân giải subtype qua root.

### 9.3. Cập nhật thuộc tính inherited

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Car car = em.find(Car.class, carId);

    if (car == null) {
        throw new IllegalArgumentException("Car not found");
    }

    car.rename("Sedan A - updated");
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
```

`rename` được định nghĩa trong `Vehicle`, nhưng SQL sẽ cập nhật **bảng `cars`**:

```sql
UPDATE cars
SET display_name = ?, version = ?
WHERE id = ? AND version = ?;
```

SQL này minh họa ngữ nghĩa optimistic locking; cú pháp thực tế, thứ tự field và giá trị version tùy provider. `@Version` đặt ở lớp cha nhưng cột version hiện diện trong từng bảng concrete.

### 9.4. Xóa một subtype

```java
Car car = em.find(Car.class, carId);

if (car != null) {
    em.remove(car);
}
```

Sau flush/commit thành công, hàng tương ứng ở `cars` bị xóa. Không có hàng cha trong `vehicles` phải xóa cùng. Tuy nhiên, các FK/association khác có thể ngăn việc xóa nếu còn tham chiếu và không có chính sách cascade phù hợp.

### 9.5. Không dùng chuyển kiểu Java để “đổi subtype” của một hàng

Ví dụ ứng dụng muốn chuyển một chiếc Car thành Motorcycle. Đây **không phải** một thao tác cập nhật field đơn giản:

```java
Vehicle vehicle = em.find(Car.class, id);

// Không thể biến instance Car đang managed
// thành instance Motorcycle chỉ bằng cast hoặc setter.
```

Trong TABLE_PER_CLASS, hai loại có **bảng khác nhau**. Nếu nghiệp vụ thực sự cho phép thay loại, thường phải thiết kế một quy trình tạo entity loại mới, chuyển dữ liệu và liên kết, xử lý identity/history và xóa/khóa entity cũ theo transaction. Điều này khác với đổi một thuộc tính như `displayName`.

## 10. Association trỏ tới kiểu cha: hạn chế về foreign key

Đây là một trong những vấn đề khó nhất của `TABLE_PER_CLASS`.

Giả sử muốn thêm entity `MaintenanceRecord` với một thuộc tính:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
private Vehicle vehicle;
```

Về domain, điều này hợp lý: một bản ghi bảo trì có thể thuộc Car **hoặc** Motorcycle. Nhưng về database, cột `maintenance_records.vehicle_id` phải tham chiếu bảng nào?

```text
maintenance_records.vehicle_id
       |
       +----> cars.id          ?
       |
       +----> motorcycles.id   ?
```

RDBMS thường yêu cầu một constraint `FOREIGN KEY` trỏ đến **một bảng đích xác định**. Không có bảng `vehicles` chung để một FK tiêu chuẩn tham chiếu tất cả subtype.

### 10.1. Hệ quả thực tế

- Một association đa hình đến root có thể được provider hỗ trợ về mặt ORM, nhưng **ràng buộc FK database chuẩn** đến nhiều bảng concrete không thể diễn đạt như một FK đơn giản.
- Hibernate hoặc provider khác có thể dùng SQL phức tạp, union hoặc chiến lược riêng cho association đa hình.
- Tự tạo bảng có cột `vehicle_id` mà không có FK kiểm chứng loại đích sẽ làm giảm mức bảo đảm toàn vẹn tham chiếu.
- Nếu các bảng subtype dùng ID trùng nhau, một cột `vehicle_id` đơn càng mơ hồ.
- Một mô hình cần rất nhiều association đến root thường không phù hợp với TABLE_PER_CLASS bằng một mô hình có **bảng cha dùng chung**.

### 10.2. Các phương án thiết kế

**Phương án A — Chuyển sang JOINED**

Giữ một bảng `vehicles` chứa ID chung, để các bảng như `maintenance_records` có thể FK đến `vehicles(id)`. Các subtype lưu field riêng trong bảng con.

**Phương án B — Chuyển sang SINGLE_TABLE**

Toàn bộ Vehicle nằm trong một bảng có discriminator. FK đơn trỏ tới `vehicles(id)`, nhưng bảng có các cột chỉ thích hợp với từng subtype.

**Phương án C — Quan hệ theo subtype cụ thể**

Nếu MaintenanceRecord chỉ áp dụng cho Car, khai báo `@ManyToOne Car` và FK đến `cars(id)`. Không cần đa hình khi nghiệp vụ chỉ cần một subtype.

**Phương án D — Mô hình tham chiếu riêng có kiểm soát**

Nếu buộc giữ các bảng concrete, ứng dụng có thể dùng một bảng registry chung cho identity, hoặc cơ chế polymorphic reference riêng của provider. Phương án này yêu cầu thiết kế transaction/constraint và thường kém portable; không nên chọn chỉ để tránh thay đổi inheritance strategy.

**Nguyên tắc:** nếu DB-level FK từ nhiều module đến một superclass là yêu cầu quan trọng, `JOINED` hoặc `SINGLE_TABLE` thường thuận tiện hơn `TABLE_PER_CLASS`.

## 11. So sánh ba chiến lược kế thừa entity JPA

JPA thường trình bày ba chiến lược chính:

- `InheritanceType.SINGLE_TABLE`
- `InheritanceType.JOINED`
- `InheritanceType.TABLE_PER_CLASS`

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Số bảng của hierarchy | Một bảng | Bảng cha + bảng con | Mỗi concrete entity một bảng |
| Dữ liệu field chung | Một lần trong bảng chung | Một lần trong bảng cha | Lặp ở mỗi bảng concrete |
| Dữ liệu field riêng | Cột subtype trong bảng chung | Bảng subtype | Bảng subtype |
| Phân biệt subtype | Discriminator | JOIN/metadata, tùy mapping | Bảng concrete/UNION |
| Đọc một subtype | Thường một bảng | Thường JOIN cha + con | Thường một bảng concrete |
| Đọc đa hình trên root | Thường một bảng | Có thể cần JOIN các subtype | Thường phải kết hợp nhiều bảng/UNION |
| Cột không áp dụng cho subtype khác | Có thể nhiều cột NULL | Ít cột không áp dụng | Không cần cột subtype khác |
| Thêm field chung | Một bảng | Một bảng cha | Mọi bảng concrete |
| FK từ bảng khác đến root | Thuận tiện | Thuận tiện | Khó có FK chuẩn đến nhiều bảng |
| Global UNIQUE trên field chung | Dễ đặt ở một bảng | Dễ đặt ở bảng cha | Không tự bảo đảm xuyên bảng |
| Nguy cơ SQL đa hình phức tạp | Thường thấp | Trung bình, tùy hierarchy | Cao hơn khi nhiều subtype |
| Khi phù hợp | Đọc đa hình thường xuyên; chấp nhận cột phân loại | Cần chuẩn hóa và FK root rõ ràng | Subtype tương đối độc lập, đọc theo subtype |

### 11.1. Khi nào chọn SINGLE_TABLE?

Phù hợp khi truy vấn đa hình rất thường xuyên và muốn một bảng dữ liệu chính. Ví dụ nhiều loại thông báo cùng được hiển thị trong một timeline.

Đổi lại, các cột chỉ dành cho subtype có thể phải để nullable, và constraint đặc thù từng subtype cần được thiết kế cẩn thận.

### 11.2. Khi nào chọn JOINED?

Phù hợp khi domain có identity chung rõ ràng, nhiều association trỏ đến root và muốn chuẩn hóa các field chung. Một bảng root hỗ trợ constraint và FK chung.

Đổi lại, đọc đầy đủ subtype thường cần JOIN, và hierarchy sâu có thể tạo truy vấn phức tạp.

### 11.3. Khi nào chọn TABLE_PER_CLASS?

Phù hợp hơn khi các subtype tương đối độc lập, có nhu cầu truy vấn cụ thể theo loại cao, ít association đa hình đến root, và việc lặp cấu trúc cột chung được chấp nhận.

Đổi lại, các query trên root có thể cần UNION nhiều bảng, migration field chung phải áp dụng nhiều lần và constraint cross-table khó biểu diễn.

**Không có chiến lược tối ưu trong mọi bối cảnh.** Sự lựa chọn phụ thuộc cách dữ liệu được truy cập và những ràng buộc phải bảo đảm ở database.

## 12. TABLE_PER_CLASS khác @MappedSuperclass

Hai mô hình có thể tạo **các bảng concrete chứa cột chung**, nhưng semantics JPA rất khác.

### 12.1. @MappedSuperclass

```java
@MappedSuperclass
public abstract class VehicleBase {

    @Id
    private Long id;

    private String assetCode;
}

@Entity
@Table(name = "cars")
public class Car extends VehicleBase {
    // ...
}

@Entity
@Table(name = "motorcycles")
public class Motorcycle extends VehicleBase {
    // ...
}
```

`VehicleBase` là nơi chia sẻ metadata mapping và code, **không phải một entity type**. Do đó:

- Không query `select v from VehicleBase v` như query một entity root.
- Không dùng `EntityManager.find(VehicleBase.class, id)` như tìm một entity.
- Không có entity inheritance polymorphism chuẩn của JPA trên VehicleBase.
- Việc có hai bảng cùng cột `id`/`assetCode` chỉ là tái sử dụng mapping.

### 12.2. @Entity + TABLE_PER_CLASS

```java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Vehicle {
    @Id
    private Long id;
}
```

`Vehicle` là một **entity root** và các subtype thuộc cùng hệ phân cấp entity. Provider có thể triển khai truy vấn polymorphic trên root bằng cách kết hợp các bảng concrete.

| Câu hỏi | @MappedSuperclass | TABLE_PER_CLASS với @Entity root |
|---|---|---|
| Lớp cha là entity? | Không | Có |
| Có kế thừa field mapping? | Có | Có |
| Có bảng riêng cho abstract root? | Không | Thường không |
| Query root polymorphic? | Không | Có theo hỗ trợ của provider |
| Association đến root như entity target? | Không | Có thể ánh xạ ORM nhưng FK database khó |
| Có chiến lược entity inheritance? | Không | Có |

Nếu chỉ muốn **tái sử dụng field** mà không cần kiểu root đa hình, `@MappedSuperclass` thường đơn giản hơn. Nếu cần root thật sự tham gia JPQL hoặc mô hình association, phải dùng entity hierarchy; khi đó vẫn cần chọn inheritance strategy phù hợp.

## 13. Discriminator và TYPE: không nhầm với SINGLE_TABLE

Với `SINGLE_TABLE`, discriminator column giúp phân biệt hàng thuộc subtype nào trong **một bảng chung**:

```text
vehicles:
  id | dtype | asset_code | seat_count | engine_cc
```

Với `TABLE_PER_CLASS`:

```text
cars:
  id | asset_code | seat_count

motorcycles:
  id | asset_code | engine_cc
```

Loại entity thường được biết từ **bảng concrete chứa hàng**, không nhất thiết cần một cột discriminator vật lý.

Provider có thể tạo **cột phân biệt loại tổng hợp trong SQL UNION** để dựng đúng instance Java; cột này không đồng nghĩa một cột `dtype` tồn tại trong mỗi bảng. Vì vậy, không nên mặc định phải đặt `@DiscriminatorColumn` hoặc `@DiscriminatorValue` giống cách thiết kế SINGLE_TABLE.

Nếu đang chuyển một hierarchy cũ từ SINGLE_TABLE sang TABLE_PER_CLASS, cần xem xét lại DDL, dữ liệu discriminator, cách migrates rows và SQL truy vấn, chứ không chỉ đổi giá trị enum trong `@Inheritance`.

## 14. Ảnh hưởng đến hiệu năng

### 14.1. Ưu điểm: truy vấn cụ thể theo subtype

```java
List<Car> cars = em.createQuery(
    "select c from Car c", Car.class
).getResultList();
```

Nếu phần lớn request chỉ liên quan `Car`, việc đọc bảng `cars` với đầy đủ cột thường đơn giản. Không cần JOIN với bảng cha để lấy `assetCode`, `displayName` và `seatCount`.

### 14.2. Nhược điểm: truy vấn đa hình nhiều nhánh

Khi subtype tăng từ 2 lên 30:

```text
select v from Vehicle v
    |
    +-- cars
    +-- motorcycles
    +-- trucks
    +-- bicycles
    +-- ...
    +-- 30 bảng concrete
```

SQL tổ hợp có thể rất dài, phải cân bằng kiểu dữ liệu giữa các nhánh, và thực hiện sort/aggregate trên tập kết quả hợp nhất. Cộng thêm phân trang, index và concurrency, chi phí query đa hình có thể lớn.

Không nhất thiết mỗi query đều tốn như nhau: database optimizer có thể áp dụng predicate pushdown, pruning hoặc các kế hoạch khác tùy điều kiện truy vấn. Nhưng **cấu trúc nhiều bảng là chi phí phải xem xét từ đầu**.

### 14.3. Thêm subtype làm thay đổi nhiều truy vấn root

Khi bổ sung:

```java
@Entity
@Table(name = "trucks")
public class Truck extends Vehicle {
    // ...
}
```

provider phải tính đến subtype mới trong các truy vấn polymorphic trên `Vehicle`. Việc thêm bảng `trucks` không chỉ ảnh hưởng code dùng `Truck`, mà còn có thể ảnh hưởng thống kê, query plan và thời gian phản hồi của mọi màn hình truy vấn danh sách Vehicle đa loại.

### 14.4. Index và thống kê bảng

Nếu truy vấn subtype thường tìm theo `assetCode`:

```sql
CREATE INDEX idx_cars_asset_code
    ON cars (asset_code);

CREATE INDEX idx_motorcycles_asset_code
    ON motorcycles (asset_code);
```

Với TABLE_PER_CLASS, cần cân nhắc index tương tự **trên từng bảng concrete**. Không có một index chung trên bảng root vì bảng root không tồn tại.

Nếu root query thường sắp xếp theo `displayName`, hãy đo xem index của các bảng con có được optimizer sử dụng hiệu quả trong phép UNION/ORDER BY hay không. Không nên phỏng đoán rằng mỗi bảng có index là query đa hình sẽ luôn nhanh.

### 14.5. Tối ưu bằng cách hỏi use case trước

Các câu hỏi quan trọng:

- 90% truy vấn là `Car` cụ thể hay `Vehicle` đa hình?
- Bao nhiêu subtype sẽ tồn tại trong vài năm tới?
- Có thường xuyên thêm field chung vào root không?
- Có cần phân trang trên hàng triệu record thuộc nhiều subtype không?
- Có nhiều relation đến superclass từ module khác không?
- Việc unique mã nghiệp vụ cần được bảo đảm xuyên các bảng không?
- Database/provider có tạo query plan tốt với UNION không?

Câu trả lời giúp chọn strategy có cơ sở hơn việc chỉ thấy một bảng subtype dễ đọc rồi quyết định TABLE_PER_CLASS.

## 15. Schema migration và khả năng tiến hóa hệ phân cấp

### 15.1. Thêm một field ở root

Giả sử thêm thuộc tính:

```java
@Column(name = "registered_at")
private LocalDate registeredAt;
```

vào `Vehicle`. Với TABLE_PER_CLASS, mọi bảng concrete cần cột `registered_at`:

```sql
ALTER TABLE cars
ADD COLUMN registered_at DATE;

ALTER TABLE motorcycles
ADD COLUMN registered_at DATE;
```

Nếu field bắt buộc, migration còn phải backfill dữ liệu cũ trước khi thêm `NOT NULL`, hoặc có default thích hợp. Không thể chỉ thêm cột ở một bảng root không tồn tại.

### 15.2. Thêm một subtype mới

Thêm `Truck` sẽ cần:

1. Tạo class `Truck extends Vehicle` có `@Entity`.
2. Tạo bảng `trucks` có **tất cả cột chung** từ Vehicle và field riêng của Truck.
3. Sử dụng **cùng chính sách sinh ID** để không tạo xung đột.
4. Thêm index/constraint tương thích với các bảng khác.
5. Cập nhật query, API serialization và business rules nếu có xử lý theo subtype.
6. Kiểm tra truy vấn JPQL đa hình, vì tập type kết quả được mở rộng.
7. Kiểm tra schema migration trong mọi môi trường triển khai.

Nếu ứng dụng dùng schema tự sinh trong môi trường thử nghiệm, vẫn phải hiểu các thay đổi cần thiết ở migration production.

### 15.3. Xóa một subtype

Khi một loại Vehicle không còn được hỗ trợ, không được xóa class hoặc bảng ngay nếu vẫn có dữ liệu lịch sử và các association đến nó. Cần quyết định archive, read-only, migration sang subtype khác hoặc mô hình lịch sử riêng.

Điều này nhắc lại rằng inheritance mapping là **quyết định cấu trúc lưu trữ dài hạn**, không chỉ cách giảm trùng lặp code Java.

### 15.4. Đổi inheritance strategy không phải một annotation edit đơn giản

Ví dụ đổi từ TABLE_PER_CLASS sang JOINED:

- Cần tạo bảng `vehicles` và chuyển cột chung từ mỗi bảng concrete vào đó.
- Cần bảo đảm ID toàn hierarchy nhất quán.
- Cần tạo PK/FK giữa parent và subtype table.
- Cần migrate dữ liệu hiện có và các association cũ.
- Cần kiểm tra tính toàn vẹn, rollback của migration và query performance.

Vì thế nên chọn strategy dựa trên hướng phát triển domain, thay vì chỉ dựa trên dữ liệu mẫu rất nhỏ lúc đầu.

## 16. Equality, hashCode và ID trên entity kế thừa

`Vehicle` là entity, không phải value object. Hai object `Car` có cùng tên không nhất thiết là cùng entity; một `Car` và một `Motorcycle` có cùng `assetCode` cũng không nên mặc nhiên được xem là cùng thực thể.

Nếu ứng dụng cần so sánh entity identity qua hai persistence context, `equals()/hashCode()` phải được thiết kế cẩn thận:

- ID do database hoặc sequence cấp có thể ban đầu là `null`.
- Hai transient entity khác nhau không được coi là bằng nhau chỉ vì cùng `id == null`.
- Hash không nên thay đổi khi entity đã nằm trong `HashSet`.
- Phải xử lý **loại entity** nhất quán với hierarchy và proxy của provider.
- Không đưa association lazy hoặc các field nghiệp vụ mutable vào hash một cách tùy tiện.

Một lỗi phổ biến:

```java
@Override
public int hashCode() {
    return Objects.hash(getId());
}
```

Khi entity mới được thêm vào `Set` trước `persist`, ID thay đổi từ null sang một giá trị, làm hash thay đổi và lookup có thể sai. Với hệ phân cấp, chính sách equality nên xác định **ID có nghĩa trong toàn hierarchy hay trong từng subtype**, đồng thời bảo đảm hợp đồng đối xứng và thống nhất với các proxy.

Không có yêu cầu JPA bắt buộc mọi entity phải override `equals/hashCode`. Nếu chỉ cần identity theo Java reference trong một persistence context, mặc định `Object.equals/hashCode` có thể đủ. Hãy đưa ra lựa chọn dựa trên cách entity được dùng trong Set, Map, detached graph và quan hệ nghiệp vụ.

## 17. Optimistic locking với @Version được kế thừa

Trong ví dụ, `Vehicle` có:

```java
@Version
@Column(name = "version", nullable = false)
private long version;
```

Khi một Car được quản lý, `version` của nó nằm trong bảng `cars`. Khi một Motorcycle được quản lý, version nằm trong `motorcycles`. Provider sử dụng version để phát hiện một số cập nhật đồng thời trên cùng entity.

Ví dụ:

```text
Transaction A đọc Car#1, version=3
Transaction B đọc Car#1, version=3

A đổi displayName, commit -> version=4

B đổi seatCount, commit
  -> version đã thay đổi
  -> có thể nhận OptimisticLockException
```

Điều này tương tự các chiến lược inheritance khác, nhưng cột version **được lặp ở từng bảng concrete**.

Nếu hệ thống có các thao tác bulk JPQL/SQL hoặc trigger sửa dữ liệu trực tiếp, hãy nhớ rằng chúng có thể không đi qua toàn bộ cơ chế entity lifecycle và version tracking như một thay đổi managed entity thông thường. Cần chính sách locking phù hợp với các đường ghi đó.

## 18. Những sai lầm và hiểu nhầm thường gặp

### 18.1. Nghĩ TABLE_PER_CLASS tạo một bảng cha và các bảng con

Điều đó mô tả `JOINED`, không phải TABLE_PER_CLASS. Với abstract root và mỗi subtype concrete một bảng, root thường không có bảng vật lý.

### 18.2. Chỉ đặt @Entity trên lớp con, quên root là entity

Nếu muốn query `Vehicle` đa hình, root phải là entity type được ánh xạ. `@MappedSuperclass` chỉ tái sử dụng metadata, không cung cấp entity root cho JPQL.

### 18.3. Dùng IDENTITY độc lập trên từng bảng

Nếu Car#1 và Motorcycle#1 cùng tồn tại, các luồng xử lý đa hình và association đến Vehicle có thể gặp vấn đề nhận diện. Hibernate TABLE_PER_CLASS thường không phù hợp với identity generator. Chọn cơ chế cấp ID chung như sequence hoặc ID ứng dụng quản lý, rồi kiểm tra schema.

### 18.4. Quên tạo sequence hoặc dùng sai tên sequence

Mapping:

```java
@SequenceGenerator(
    name = "vehicle_id_generator",
    sequenceName = "vehicle_id_seq"
)
```

phải khớp một sequence có thể truy cập trong database. `name` là tên generator ở phía JPA, còn `sequenceName` là tên sequence vật lý. Hai thuộc tính không cùng vai trò.

### 18.5. Tin rằng @Column(unique=true) ở root đảm bảo unique toàn hierarchy

Với TABLE_PER_CLASS, một unique constraint được tạo ở từng bảng concrete không thể tự bảo đảm uniqueness **giữa các bảng**. Nếu `assetCode` cần unique toàn cục, phải thiết kế cơ chế database khác.

### 18.6. Cho rằng query root chỉ đọc một bảng

`select v from Vehicle v` có thể kết hợp nhiều bảng concrete. Khi số subtype tăng, query đa hình có thể đắt hơn query subtype.

### 18.7. Cho rằng subtype không cần cột inherited

`Car extends Vehicle` thừa kế `assetCode`/`displayName` và các persistent fields, nên bảng `cars` phải chứa cột cho chúng. Nếu migration chỉ tạo `cars(id, seat_count)`, mapping không khớp.

### 18.8. Nghĩ có thể đặt FK chuẩn từ bảng khác đến root mà không có bảng root

FK quan hệ truyền thống cần một bảng đích. Khi mỗi subtype nằm ở bảng riêng, không có `vehicles(id)` để tham chiếu. Kiến trúc liên kết đến root phải được xem xét ngay khi chọn strategy.

### 18.9. Dùng @DiscriminatorColumn như thể là SINGLE_TABLE

Discriminator là cơ chế quan trọng của SINGLE_TABLE; với TABLE_PER_CLASS, subtype được phân biệt qua bảng và/hoặc SQL tổng hợp do provider tạo. Không tự tạo `dtype` ở mọi bảng chỉ vì có `@Inheritance`.

### 18.10. Không xem xét migration khi thêm field chung

Mỗi field chung mới có thể yêu cầu thêm cột ở mọi bảng concrete. Nếu migration thiếu một bảng, query hoặc persist subtype đó có thể lỗi khi truy cập.

### 18.11. Dùng một query đa hình khổng lồ để phân trang mọi subtype

UNION, sort và pagination có thể tạo chi phí lớn. Khi workload chủ yếu truy cập subtype cụ thể, truy vấn subtype là lựa chọn dễ tối ưu hơn.

### 18.12. Tưởng @Inheritance tự xử lý mọi khác biệt provider

Các behavior như generated-ID strategy, polymorphic association, JPQL TREAT và SQL UNION có thể khác theo implementation. Hãy kiểm tra khả năng hỗ trợ của provider/version trước khi thiết kế hệ thống phụ thuộc mạnh vào các tính năng này.

## 19. Thực hành: chứng minh cơ chế TABLE_PER_CLASS trên database

Bài thực hành nên chạy với một JPA provider hỗ trợ strategy, ví dụ Hibernate ORM, trên H2 cho môi trường học hoặc database quan hệ đang dùng trong dự án.

### Phần A — Tạo hierarchy và schema

1. Tạo `Vehicle` abstract entity có `@Inheritance(TABLE_PER_CLASS)`.
2. Tạo `Car`, `Motorcycle` với `@Entity` và `@Table` riêng.
3. Khai báo một sequence chung cho ID.
4. Tạo migration với bảng `cars`, `motorcycles` và `vehicle_id_seq`.
5. Bật SQL log ở môi trường học.
6. Chạy ứng dụng và kiểm tra **không cần bảng `vehicles`** với mô hình abstract root này.
7. Xem cả hai bảng có `asset_code`, `display_name`, `version`.

### Phần B — Persist và truy vấn subtype

1. Persist một Car và một Motorcycle trong cùng transaction.
2. Commit rồi đọc lại ID.
3. Dùng `em.find(Car.class, carId)`.
4. Dùng `em.find(Motorcycle.class, motorcycleId)`.
5. Quan sát bảng nào được truy vấn.
6. Kiểm tra ID đã cấp từ cùng một nguồn và không bị trùng trong dữ liệu mới tạo.

### Phần C — Truy vấn đa hình

1. Chạy `select v from Vehicle v`.
2. Ghi các kiểu Java thực tế được trả về.
3. Quan sát SQL và tìm các nhánh kết hợp dữ liệu từ `cars`, `motorcycles`.
4. So sánh với `select c from Car c`.
5. Thêm điều kiện `where v.assetCode like :prefix` và xem query plan.
6. Thử sắp xếp/phân trang `order by v.assetCode`, ghi thời gian trên tập dữ liệu đủ lớn.

### Phần D — Thêm subtype mới

1. Tạo `Truck extends Vehicle` với field `payloadKg`.
2. Tạo bảng `trucks` chứa tất cả các cột chung và field riêng.
3. Dùng cùng sequence `vehicle_id_seq`.
4. Persist Truck.
5. Chạy lại query `select v from Vehicle v`.
6. Quan sát query đa hình thay đổi ra sao và kết quả có thêm Truck.

### Phần E — Thêm field chung

1. Thêm `registeredAt` vào `Vehicle`.
2. Thử migration chỉ thêm cột ở `cars` mà quên `motorcycles` trong database thử nghiệm.
3. Quan sát mismatch nếu provider cần cột trên Motorcycle.
4. Sửa migration đầy đủ cho mọi bảng concrete.
5. Ghi lại checklist schema khi đổi root entity trong TABLE_PER_CLASS.

### Phần F — Optimistic locking

1. Persist một Car có version.
2. Mở hai persistence context để đọc cùng bản ghi.
3. Sửa ở context A và commit.
4. Sửa ở context B dựa trên version cũ, commit.
5. Quan sát optimistic locking conflict theo provider/configuration.
6. Giải thích vì sao version được lưu trong `cars`, không phải bảng root.

### Phần G — Đánh giá association tới root

1. Thiết kế entity `MaintenanceRecord` có thuộc tính liên kết đến Vehicle.
2. Vẽ FK cần có trong database.
3. Phân tích vì sao một cột FK không thể tham chiếu trực tiếp hai bảng concrete.
4. Đề xuất phương án dùng `JOINED` hoặc `SINGLE_TABLE` nếu cần DB-level FK bảo vệ toàn vẹn.
5. Thảo luận tác động đến API nếu vẫn chọn TABLE_PER_CLASS và tham chiếu đa hình theo cơ chế riêng.

**Ghi chép thực nghiệm:**

| Tác vụ | SQL/bảng có khả năng liên quan | Điều cần quan sát |
|---|---|---|
| Persist Car | Shared sequence + `cars` | ID và INSERT vào bảng Car |
| Persist Motorcycle | Shared sequence + `motorcycles` | ID và INSERT vào bảng Motorcycle |
| Query Car | `cars` | Truy vấn subtype cụ thể |
| Query Vehicle | `cars` và `motorcycles` | SQL đa hình, UNION/chiến lược provider |
| Rename Car | `cars` | UPDATE field inherited trong bảng concrete |
| Thêm field chung | Mọi bảng concrete | Migration phải đầy đủ |
| Thêm Truck | `trucks` + query root | Hệ phân cấp mở rộng |
| Query root nhiều dữ liệu | Nhiều bảng + sort/aggregate | Query plan và thời gian |
| Xóa Car | `cars` | DELETE theo entity subtype |

Bảng trên là khung quan sát; không khẳng định câu SQL chính xác đã chạy trong một dự án cụ thể. Khi tối ưu, cần dùng SQL log, JDBC metrics và `EXPLAIN`/execution plan từ database thật.

## 20. Bài tập thiết kế: hệ thống nhiều loại tài sản

Một công ty có các loại tài sản:

- `Laptop`: mã tài sản, tên, cấu hình CPU/RAM.
- `Printer`: mã tài sản, tên, số trang/phút.
- `OfficeDesk`: mã tài sản, tên, kích thước.
- Một màn hình riêng quản lý từng loại.
- Một màn hình tổng hợp tất cả tài sản.
- Bản ghi bảo trì có thể tham chiếu đến bất kỳ loại tài sản nào.
- Mã tài sản phải duy nhất trong toàn công ty.
- Hệ thống dự kiến tăng từ 3 lên 20 loại tài sản.

Hãy trả lời:

1. Nếu dùng TABLE_PER_CLASS, cần những bảng nào?
2. Những cột nào phải lặp ở mỗi bảng?
3. Mỗi bảng riêng có `UNIQUE(asset_code)` đã đủ bảo đảm unique toàn cục chưa?
4. Câu query tổng hợp mọi tài sản có thể dùng chiến lược SQL gì?
5. Một bảng `maintenance_records` sẽ tạo FK đến tài sản đa hình ra sao?
6. Khi thêm một field chung `purchaseDate`, cần bao nhiêu migration cột?
7. Shared sequence hoặc application-assigned ID giải quyết được phần nào của bài toán?
8. Trong ba strategy SINGLE_TABLE/JOINED/TABLE_PER_CLASS, lựa chọn nào phù hợp với ràng buộc bảo trì và global uniqueness?
9. Nếu vẫn chọn TABLE_PER_CLASS, cần những cơ chế bổ sung để bảo vệ toàn vẹn dữ liệu?
10. Nếu chỉ có màn hình riêng cho từng loại và không có association root, TABLE_PER_CLASS trở nên hấp dẫn hơn ở điểm nào?

Bài tập không yêu cầu một câu trả lời duy nhất. Mục tiêu là chứng minh bạn phân biệt được **tính tiện lợi của query subtype** và **chi phí của polymorphism/foreign key/schema chung**.

## 21. Câu hỏi ôn tập

1. `InheritanceType.TABLE_PER_CLASS` tạo một bảng cho mỗi lớp Java bất kỳ, hay cho mỗi lớp entity concrete?
2. Với root entity abstract, có bắt buộc tồn tại bảng root không?
3. Vì sao field của superclass xuất hiện trong bảng `cars` và `motorcycles`?
4. Khi persist `new Car(...)`, SQL INSERT đi vào bảng nào?
5. Vì sao `select v from Vehicle v` thường phức tạp hơn `select c from Car c`?
6. Hibernate có thể dùng `UNION ALL` theo cách nào để tạo kết quả polymorphic?
7. Khi bổ sung subtype mới, những query nào có thể bị ảnh hưởng?
8. Vì sao dùng IDENTITY độc lập cho mỗi bảng có thể gây vấn đề?
9. Sequence chung giải quyết được vấn đề nào, và không tự tạo được constraint nào?
10. Vì sao `@Column(unique=true)` trên field chung không đương nhiên tạo uniqueness giữa nhiều bảng?
11. `TABLE_PER_CLASS` khác `JOINED` ở cấu trúc bảng và cách đọc subtype ra sao?
12. `@MappedSuperclass` có cho phép JPQL query trên chính superclass không?
13. Vì sao foreign key từ bảng khác đến abstract root khó thiết kế trong TABLE_PER_CLASS?
14. Nếu thêm một field vào root, migration phải thay đổi những bảng nào?
15. Có cần một cột discriminator vật lý như SINGLE_TABLE không?
16. `@Version` kế thừa được lưu ở đâu trong TABLE_PER_CLASS?
17. Những yếu tố nào khiến TABLE_PER_CLASS phù hợp hoặc không phù hợp với một hệ thống thực tế?

## 22. Tóm tắt quyết định kỹ thuật

| Nếu yêu cầu chính là… | Nhận xét về TABLE_PER_CLASS |
|---|---|
| Mỗi subtype có bảng và tập dữ liệu độc lập | Phù hợp để cân nhắc |
| Đọc subtype riêng chiếm đa số | Có thể đơn giản hơn JOINED ở truy vấn subtype |
| Truy vấn root đa hình rất thường xuyên | Cần đánh giá chi phí UNION qua nhiều bảng |
| Có rất nhiều subtype, tiếp tục tăng | Cần tính chi phí migration và SQL đa hình |
| Field chung thay đổi thường xuyên | Mỗi bảng concrete cần cập nhật schema |
| Có FK từ nhiều module đến root | Thường bất tiện vì không có bảng root chung |
| Cần global UNIQUE trên field chung | Cần cơ chế bổ sung hoặc chiến lược khác |
| Dùng generated ID | Nên có generator thống nhất như shared sequence |
| Muốn chỉ tái sử dụng field, không cần entity root | Cân nhắc `@MappedSuperclass` |
| Cần bảng chung để giữ identity và FK | Cân nhắc `JOINED` |
| Muốn query đa hình đơn giản trên một bảng | Cân nhắc `SINGLE_TABLE` |
| Có workload lớn | Benchmark trên provider/database thực tế |

### Ghi nhớ bằng một sơ đồ

```text
Java:
  @Entity
  @Inheritance(TABLE_PER_CLASS)
  abstract Vehicle
      |
      +--> @Entity Car
      |
      +--> @Entity Motorcycle

Database:
  cars          motorcycles
    id            id
    asset_code    asset_code
    display_name  display_name
    version       version
    seat_count    engine_cc

Generator:
  vehicle_id_seq --> cấp ID cho cả hai bảng

Query:
  select c from Car c        --> thường một bảng
  select v from Vehicle v    --> kết hợp các bảng concrete

Trade-off:
  + subtype tự chứa; không cần JOIN bảng cha
  - lặp cột; thay đổi schema nhiều nơi
  - polymorphic query có thể cần UNION
  - FK/global constraint xuyên hierarchy khó
```

**Nguyên tắc cuối cùng:** `TABLE_PER_CLASS` là chiến lược ánh xạ **mỗi entity concrete vào một bảng chứa đầy đủ cả thuộc tính kế thừa**. Nó phát huy lợi thế khi các subtype tương đối độc lập và thường được truy vấn riêng. Ngược lại, nếu hệ thống cần truy vấn đa hình liên tục, khóa ngoại đến superclass hoặc constraint chung xuyên nhiều subtype, phải đánh giá kỹ chi phí của UNION, dải ID, schema trùng lặp và giới hạn toàn vẹn quan hệ trước khi chọn chiến lược này.

