# Phân biệt dữ liệu trong persistence context với dữ liệu đã ghi xuống database

## 1. Vấn đề: nhìn thấy giá trị mới trong Java chưa chắc SQL đã chạy

Trong Spring Data JPA, mỗi `EntityManager` làm việc với một **persistence context**. Các entity ở trạng thái *managed* được theo dõi trong bộ nhớ. Khi ta đổi thuộc tính của một managed entity, code Java thấy giá trị mới ngay; nhưng Hibernate/JPA có thể **chưa phát sinh câu `UPDATE` xuống database** cho đến một lần `flush`.

Ngược lại, nếu một câu SQL đã được gửi xuống database, điều đó **chưa có nghĩa giao dịch đã commit** và người dùng/giao dịch khác có thể nhìn thấy dữ liệu. Sau `flush`, dữ liệu thường đã thay đổi trong transaction hiện tại nhưng vẫn có thể bị rollback.

Những tình huống gây nhầm lẫn khi kiểm thử:

- `repository.findById(id)` trả entity mang giá trị mới nhưng SQL `UPDATE` chưa chạy; test xanh không chứng minh database row đã đổi.
- `repository.save(entity)` trả entity có ID, khiến người viết tưởng toàn bộ INSERT/UPDATE đã được commit.
- `repository.saveAndFlush(entity)` thực hiện flush và test nghĩ dữ liệu đã “lưu vĩnh viễn”; nhưng transaction của `@DataJpaTest` vẫn rollback mặc định.
- Gọi SQL trực tiếp bằng `JdbcTemplate` rồi `findById(id)` vẫn trả **giá trị cũ** do entity đang được giữ trong first-level cache.
- Gọi `entityManager.clear()` khi chưa flush làm mất những thay đổi chỉ tồn tại trong persistence context.
- Một truy vấn JPQL/native SQL có thể kích hoạt *AUTO flush*, khiến test “trước flush” lại vô tình chạy SQL.
- Dùng `@GeneratedValue(strategy = IDENTITY)` khiến INSERT phát sớm để lấy ID; không thể khẳng định mọi `save()` đều chỉ giữ dữ liệu trong RAM.
- Kiểm thử với H2 pass nhưng production PostgreSQL/MySQL khác ở isolation, constraints, SQL dialect hoặc ID strategy.

**Chủ đề chính:** phân biệt rõ ba trạng thái: **entity trong bộ nhớ (managed state)** → **SQL đã được đồng bộ vào database trong transaction (flushed state)** → **transaction đã commit (committed state)**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích persistence context/first-level cache và dirty checking.
2. Phân biệt `persist`, `merge`, `save`, `flush`, `clear`, `refresh` và `commit`.
3. Hiểu vì sao `findById` hoặc một query JPA không luôn chứng minh hàng trong database hiện có nội dung giống entity.
4. Kiểm tra **trạng thái thực của hàng trong database cùng transaction** bằng `JdbcTemplate` mà không vô tình kích hoạt JPA flush.
5. Phân biệt flush với commit, test rollback và visibility giữa các giao dịch.
6. Viết test Java 17+, Spring Boot 3.x, `@DataJpaTest`, H2 và JUnit Jupiter chứng minh những khác biệt này.
7. Tránh test xanh giả do cache, auto-flush, IDENTITY, query bulk, transaction rollback hoặc môi trường database khác.

## 2. Persistence context là gì?

Persistence context là tập hợp các entity đang được JPA `EntityManager` quản lý, cùng cơ chế nhận diện theo entity type + primary key. Trong một context, cùng một database row thường tương ứng **một managed entity instance** cho cùng khóa.

Ví dụ trong một transaction:

```java
PurchaseRecord first = entityManager.find(
        PurchaseRecord.class, id);
PurchaseRecord second = entityManager.find(
        PurchaseRecord.class, id);

assertThat(first).isSameAs(second);
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập; giả định có entity `PurchaseRecord`, `entityManager` và import AssertJ. Nó cho thấy **identity map** của persistence context: lần tìm thứ hai có thể dùng object đã được quản lý, không cần thực hiện một SELECT mới.

### 2.1. First-level cache không giống second-level cache

- **First-level cache:** gắn với `EntityManager`/persistence context, là một phần thiết yếu của JPA, giữ managed entity trong phạm vi context.
- **Second-level cache:** cache tùy chọn của provider, có thể chia sẻ giữa các persistence context; cần cấu hình/strategy riêng.
- **Database buffer/cache:** cache nội bộ của RDBMS, không phải Java managed entity state.
- **Spring Cache/Redis:** lớp cache ứng dụng khác, có thể hoàn toàn không biết entity đã flush/commit.

Bài này kiểm tra **first-level cache**. Ví dụ H2/Hibernate cơ bản không bật second-level cache. Khi project bật cache cấp hai, một lần `clear()` chỉ xóa **first-level cache**; vẫn cần quan tâm cơ chế cache cấp hai nếu muốn đảm bảo truy vấn mới lấy row mới.

### 2.2. Các trạng thái entity cần hiểu

| Trạng thái | Ý nghĩa | JPA tự theo dõi thay đổi? |
|---|---|---|
| Transient/new | Object Java chưa được gắn vào persistence context | Không |
| Managed/persistent | Object nằm trong persistence context và có identity quản lý | Có, khi đủ điều kiện dirty checking |
| Detached | Từng managed, nhưng context không còn quản lý | Không, cho tới khi được merge vào managed instance |
| Removed | Đã được đánh dấu xóa trong context | Xóa thường được đồng bộ khi flush |

Thao tác `new PurchaseRecord(...)` chưa tự ghi database. `entityManager.persist(entity)` đưa entity mới vào context và lên lịch INSERT (hoặc có thể INSERT sớm do ID generation/constraints). `entityManager.clear()` detach tất cả managed entities; `entityManager.detach(entity)` chỉ detach một object. `entityManager.refresh(entity)` nạp lại state của **managed entity** từ database, có thể làm mất thay đổi chưa flush trên object đó.

### 2.3. Dirty checking và write-behind

Với một managed entity:

```java
PurchaseRecord record = repository.findById(id)
        .orElseThrow();

record.setState("PAID");
```

Hibernate thường phát hiện sự thay đổi của thuộc tính `state` khi cần flush; không cần gọi `save(record)` lại chỉ để Hibernate nhìn thấy setter. Các câu SQL có thể được gom/batch thay vì thực thi ngay sau từng setter.

Tuy nhiên không nên tuyệt đối hóa: entity immutable/read-only, trường `@Transient`, mapping đặc biệt, bytecode enhancement, transaction read-only, trigger hoặc custom persistence provider có thể thay đổi cách dirty checking/SQL được phát. Điều ta cần kiểm tra là **hợp đồng của entity mapping và transaction thực tế**.

## 3. Ba mốc thời gian: RAM → database trong transaction → commit

Hãy tưởng tượng database ban đầu có hàng:

```text
id = 10, state = "NEW"
```

Một transaction JPA đọc hàng đó thành managed entity, sau đó gọi setter:

```text
T0: JPA SELECT row id=10
    Persistence context: state="NEW"
    Database (trong transaction): state="NEW"

T1: managed.setState("PAID")
    Persistence context: state="PAID"
    Database row: vẫn có thể state="NEW"
    Chưa có UPDATE SQL ở bước này

T2: entityManager.flush()
    Hibernate dirty checking -> UPDATE state="PAID" WHERE id=10
    Persistence context: state="PAID"
    Database trong transaction hiện tại: state="PAID"
    Giao dịch: CHƯA commit

T3a: transaction COMMIT
    Dữ liệu được xác nhận theo semantics của RDBMS

T3b: hoặc transaction ROLLBACK
    SQL UPDATE bị hoàn tác; trạng thái committed cũ được giữ
```

Ở T2, một query JDBC **trên chính transaction/connection đã thực thi UPDATE** thường thấy `"PAID"`. Nhưng một query ở giao dịch/connection khác có thể **không nhìn thấy** nó do isolation (ví dụ `READ_COMMITTED`); không thể kết luận về external visibility chỉ từ việc same-transaction query thấy row.

**Điểm mấu chốt:** `flush` không phải `commit`. Flush có thể khiến SQL chạy, constraint được kiểm tra và row trong transaction đổi; commit mới kết thúc giao dịch theo hướng xác nhận.

### 3.1. Một hình dung ba lớp

```text
┌──────────────────────────────┐
│ Java / JPA PersistenceContext│
│ Managed entity state="PAID"  │
└──────────────┬───────────────┘
               │ entityManager.flush()
               ▼
┌──────────────────────────────┐
│ RDBMS transaction chưa commit│
│ UPDATE row: state="PAID"     │
└──────────────┬───────────────┘
               │ commit() hoặc rollback()
               ▼
┌──────────────────────────────┐
│ Committed DB state           │
│ "PAID" nếu commit thành công  │
│ "NEW" nếu rollback           │
└──────────────────────────────┘
```

Hình này đơn giản hóa transaction isolation, triggers, lock, concurrency và provider internals để tập trung vào **khác biệt persistence context / SQL / commit**.

## 4. Ý nghĩa chính xác của các API

| API | Điều làm được | Điều không nên suy ra |
|---|---|---|
| `EntityManager.persist(entity)` | Gắn entity mới và chuẩn bị INSERT; có thể SQL sớm theo ID strategy | Mọi mapping/constraint đã được kiểm tra; transaction đã commit |
| `EntityManager.merge(detached)` | Sao chép state của object detached vào managed instance; trả về managed instance | Object truyền vào tự trở thành managed hoặc SQL phải chạy ngay |
| `JpaRepository.save(entity)` | Gọi persist/merge theo chiến lược xác định entity mới/cũ | Bất kỳ UPDATE/INSERT nào cũng chắc chắn đã flush và commit |
| `JpaRepository.saveAndFlush(entity)` | Save rồi flush các thay đổi đang chờ | Transaction đã commit hoặc mọi giao dịch khác thấy dữ liệu |
| `JpaRepository.flush()` | Flush persistence context tương ứng | Kết thúc transaction |
| `EntityManager.flush()` | Đồng bộ pending state bằng SQL (theo provider/mapping) | Xóa cache, refresh state hoặc commit |
| `EntityManager.clear()` | Detach toàn bộ entities đang managed | Tự flush trước khi detach, hay xóa rows khỏi DB |
| `EntityManager.detach(entity)` | Detach một managed entity | Tự ghi các dirty changes của entity |
| `EntityManager.refresh(entity)` | Đọc lại state từ DB vào managed entity | Tự commit hay giữ dirty state chưa flush trên entity |
| `EntityManager.find(Entity.class,id)` | Tìm theo primary key, có thể trả managed instance từ first-level cache | Một SELECT mới vừa được chạy |
| `JpaRepository.findById(id)` | Thường dựa trên `EntityManager.find` | Database row vừa được đọc trực tiếp, bỏ qua persistence context |
| `Transaction.commit()` | Xác nhận transaction nếu thành công; thường kéo theo flush trong chế độ thích hợp | Dữ liệu đã visible trước commit theo mọi isolation level |

Một số API khác như JPQL/criteria queries, bulk update, native SQL và `JdbcTemplate` có cơ chế flush/cache khác nhau. **Không dùng từ “query” như thể mọi lệnh đọc đều giống nhau.**

### 4.1. “Save thành công” không bằng “ghi SQL xong”

Spring Data JPA thường dùng `persist(...)` cho entity được xác định là mới và `merge(...)` cho entity được xác định đã tồn tại. Cách xác định “mới” phụ thuộc id, `@Version`, interface `Persistable` hoặc custom entity information. Nếu dùng `IDENTITY`, INSERT có thể được gửi **ngay khi persist để lấy ID**; vì vậy “save luôn chỉ giữ RAM” là sai.

Ngược lại, khi sửa **managed entity đã tồn tại**, Hibernate có thể đợi đến flush mới gửi UPDATE; vì thế “cứ thấy object khác đi là database row đã đổi” cũng sai.

### 4.2. SaveAndFlush cũng flush các thay đổi khác đang chờ

`saveAndFlush(entity)` không chỉ yêu cầu SQL riêng cho mỗi field của entity vừa truyền. Flush thường đồng bộ **pending work của persistence context** thuộc transaction. Một entity khác đã bị dirty trong cùng context cũng có thể được ghi SQL trong lần flush này.

Đừng dùng saveAndFlush để cố “chỉ lưu riêng entity A” trong transaction có nhiều entities dirty. Cần quản lý transaction boundary và entity state đúng mục tiêu.

## 5. Flush mode: tại sao query có thể làm SQL chạy trước lúc bạn mong?

JPA định nghĩa các chế độ flush phổ biến:

- `FlushModeType.AUTO`: provider bảo đảm query consistency theo các quy tắc flush tương ứng; Hibernate có thể flush trước truy vấn có liên quan pending changes.
- `FlushModeType.COMMIT`: provider có thể trì hoãn flush đến commit; độ hiển thị pending changes đối với query trước commit **không được JPA bảo đảm giống nhau ở mọi provider**.

Hibernate còn có các chế độ riêng như `ALWAYS` và `MANUAL`/`EXPLICIT` theo version/API. Đừng copy Hibernate-specific flush mode sang một provider JPA khác rồi kỳ vọng giống hệt.

### 5.1. Query JPQL có thể kích hoạt flush

Ví dụ:

```java
PurchaseRecord record = repository.findById(id)
        .orElseThrow();
record.setState("PAID");

List<PurchaseRecord> found = entityManager
        .createQuery(
                "select p from PurchaseRecord p "
                + "where p.state = :state",
                PurchaseRecord.class)
        .setParameter("state", "PAID")
        .getResultList();
```

Đây là **snippet minh họa** có imports `java.util.List` và JPA context. Với Hibernate `AUTO`, query trên entity/table có pending updates liên quan thường làm Hibernate **flush trước SELECT**. Test thấy `PAID` ở kết quả query **không chứng minh** row đã được cập nhật từ trước khi query bắt đầu.

Vì vậy, nếu mục tiêu là phân biệt RAM với SQL **trước explicit flush**, không dùng một truy vấn JPQL có thể làm thay đổi trạng thái bạn đang đo.

### 5.2. Native query qua EntityManager cũng không phải phép đo vô hại

Một số developer viết:

```java
entityManager.createNativeQuery(
        "select state from purchase_records where id = :id")
        .setParameter("id", id)
        .getSingleResult();
```

rồi cho rằng “native SQL chắc chắn không tự flush”. Điều đó **không đúng một cách tổng quát**. Khi Hibernate được bootstrap theo JPA và flush mode AUTO, native SQL query qua EntityManager có thể kích hoạt auto flush, thậm chí với query không có synchronized query spaces. Hành vi phụ thuộc provider/version/bootstrap/query configuration.

**Giải pháp trong ví dụ phần 7:** sử dụng `JdbcTemplate`, thực hiện SQL trực tiếp thông qua Spring-managed JDBC connection cùng transaction. Việc gọi `JdbcTemplate.queryForObject(...)` không tự ra lệnh cho Hibernate EntityManager flush; nhờ đó ta đo được database row trước và sau explicit JPA flush rõ ràng hơn.

### 5.3. JDBC khác với EntityManager, nhưng phải cùng transaction

Để một JDBC query có ý nghĩa khi so sánh:

1. `@DataJpaTest` phải đang chạy transaction test do Spring quản lý.
2. `JdbcTemplate` sử dụng cùng DataSource/transaction connection có thể tham gia transaction hiện tại (Spring sử dụng các tiện ích quản lý connection như `DataSourceUtils`).
3. Query phải đọc đúng table và record.
4. Không có bước JPA query/flush chen vào giữa thay đổi managed entity và JDBC SELECT.
5. Không tự mở connection ngoài transaction rồi diễn giải kết quả như “same transaction state”.

Trong trường hợp nhiều transaction managers, nhiều DataSources hoặc JTA, hãy thiết kế rõ boundary; ví dụ của bài cố ý dùng **một H2 DataSource và một JPA transaction manager**.

## 6. Chọn phương pháp test đúng mục tiêu

| Mục tiêu kiểm thử | Cách kiểm chứng đáng tin hơn |
|---|---|
| Entity được gắn vào persistence context | `entityManager.contains(entity)` |
| Entity instance được tái sử dụng trong một context | Assert object identity sau `findById`/`find` |
| Dirty value đã đổi trong Java | Kiểm tra getter trên managed entity |
| Database đã nhận UPDATE trong **cùng transaction** | JDBC SELECT trước/sau `entityManager.flush()` |
| Force SQL để phát hiện constraint errors sớm | `flush()` hoặc `saveAndFlush()` |
| Một new EntityManager phải reload từ DB | `flush(); clear(); find(...)` khi thích hợp |
| Database value thay đổi qua SQL ngoài JPA | JDBC UPDATE rồi `refresh(entity)` hoặc `clear(); find(...)` |
| Data thực sự được commit | Kết thúc transaction commit, quan sát bằng transaction mới, có cleanup |
| Data bị rollback | `TestTransaction.end()` khi flagged rollback, kiểm tra ở transaction mới |
| Isolation giữa hai transactions | TransactionTemplate/transactions khác với đúng DataSource và isolation |
| Constraint/locking/dialect giống production | Test trên database engine thật, ví dụ Testcontainers PostgreSQL |

### 6.1. Một bài test “kiểm tra findById” chưa đủ

Phản mẫu:

```java
PurchaseRecord record = repository.save(
        new PurchaseRecord("PO-100", "NEW"));
record.setState("PAID");

assertThat(repository.findById(record.getId()).orElseThrow()
        .getState()).isEqualTo("PAID");
```

Đây là **phản ví dụ**, chưa độc lập về imports/context. Nó có thể pass chỉ nhờ entity vẫn đang managed. Không có `flush()`, `clear()` hoặc JDBC verification; test **không đo** đã gửi UPDATE xuống database hay chưa.

Cách cải thiện phụ thuộc hợp đồng:

- Muốn kiểm tra dirty checking: `flush()` rồi JDBC query.
- Muốn kiểm tra state được nạp qua truy vấn database thay vì first-level cache: `flush(); clear(); findById(...)`.
- Muốn kiểm tra commit: cần rời transaction hiện tại và đọc bằng transaction mới.
- Muốn kiểm tra mapping/query: có thể dùng `@DataJpaTest` với H2 hoặc database phù hợp; assert giá trị và constraints.

## 7. Ví dụ chạy được: Spring Boot 3.x, JPA, H2, JUnit Jupiter

Đây là một bộ test **cố ý so sánh hai nguồn đọc**:

1. JPA managed entity / repository `findById`.
2. SQL trực tiếp của `JdbcTemplate` trong cùng transaction.

Sample sử dụng một record có status, một `JpaRepository`, Hibernate và H2. Không cần Web MVC/server, không có network service ngoài, không dùng Testcontainers và không truy cập production DB.

**Môi trường:** Java 17+, Spring Boot 3.x (ví dụ 3.4/3.5), Spring Data JPA + H2 runtime + Spring Boot Starter Test. Package gốc `com.example.jpaboundary`.

### 7.1. Dependencies

Gradle Groovy DSL — đoạn `dependencies` của project **đã có** Spring Boot Gradle plugin, dependency management, repositories và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — đoạn `dependencies` của `pom.xml` dùng Spring Boot parent/BOM và test plugin hỗ trợ JUnit Jupiter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **snippets**, không phải toàn bộ build files. Đừng thêm version trực tiếp cho Hibernate, Spring Data hoặc H2 nếu Boot BOM của dự án đã quản lý chúng. H2 là ví dụ để tái lập hành vi; không dùng test H2 để kết luận mọi trigger, isolation, sequence và constraint của PostgreSQL/MySQL hoạt động y hệt.

### 7.2. Cấu trúc file

```text
src/
├── main/java/com/example/jpaboundary/
│   ├── JpaBoundaryApplication.java
│   ├── PurchaseRecord.java
│   └── PurchaseRecordRepository.java
└── test/java/com/example/jpaboundary/
    └── PersistenceBoundaryTest.java
```

Trong ví dụ, tất cả entity/repository/test nằm trong package gốc có `@SpringBootApplication`, giúp `@DataJpaTest` tìm cấu hình và scan JPA components tương ứng.

### 7.3. Application bootstrap

**File `src/main/java/com/example/jpaboundary/JpaBoundaryApplication.java`:**

```java
package com.example.jpaboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaBoundaryApplication.class, args);
    }
}
```

Không có `@ComponentScan` riêng hay `@EnableJpaRepositories` thủ công. `@DataJpaTest` giới hạn phạm vi theo JPA slice, không nạp các service/controller không cần thiết.

### 7.4. JPA entity

**File `src/main/java/com/example/jpaboundary/PurchaseRecord.java`:**

```java
package com.example.jpaboundary;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code", nullable = false)
    private String referenceCode;

    @Column(name = "state", nullable = false)
    private String state;

    protected PurchaseRecord() {
        // JPA cần constructor không đối số có thể truy cập.
    }

    public PurchaseRecord(String referenceCode, String state) {
        this.referenceCode = referenceCode;
        this.state = state;
    }

    public Long getId() {
        return id;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getState() {
        return state;
    }

    public void setState(String state) {
        this.state = state;
    }
}
```

**Vì sao dùng IDENTITY mà vẫn dạy flush?** Với IDENTITY, Hibernate thường cần chạy INSERT sớm để lấy generated ID. Do đó các test **không cố chứng minh INSERT bị hoãn đến flush**. Chúng tạo một hàng baseline bằng `saveAndFlush()` rồi sửa **managed entity đã tồn tại** và đo UPDATE trước/sau flush. Cách này tránh khái quát sai về timing của INSERT.

Table name và column name được chỉ định rõ, nên JDBC queries trong test cùng đọc `purchase_records.state`. Không có `@Version` để mẫu đơn giản; với optimistic locking, cần xem thêm phần 11.

### 7.5. Repository

**File `src/main/java/com/example/jpaboundary/PurchaseRecordRepository.java`:**

```java
package com.example.jpaboundary;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRecordRepository
        extends JpaRepository<PurchaseRecord, Long> {
}
```

Spring Data tạo implementation của repository này ở JPA slice. `JpaRepository` có `save`, `saveAndFlush`, `flush`, `findById`; test sẽ dùng đúng những phương thức đó.

### 7.6. Lớp test hoàn chỉnh với 7 bài JUnit Jupiter

**File `src/test/java/com/example/jpaboundary/PersistenceBoundaryTest.java`:**

```java
package com.example.jpaboundary;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class PersistenceBoundaryTest {

    @Autowired
    PurchaseRecordRepository repository;

    @Autowired
    EntityManager entityManager;

    @Autowired
    JdbcTemplate jdbcTemplate;

    private PurchaseRecord seeded(String referenceCode) {
        return repository.saveAndFlush(
                new PurchaseRecord(referenceCode, "NEW"));
    }

    private String sqlState(Long id) {
        return jdbcTemplate.queryForObject(
                "select state from purchase_records where id = ?",
                String.class,
                id);
    }

    @Test
    void managedValueChangesBeforeDatabaseUpdateIsFlushed() {
        PurchaseRecord managed = seeded("PO-101");

        managed.setState("PAID");

        assertThat(entityManager.contains(managed)).isTrue();
        assertThat(managed.getState()).isEqualTo("PAID");

        // JDBC dùng cùng Spring transaction; không kích JPA auto-flush.
        assertThat(sqlState(managed.getId())).isEqualTo("NEW");

        entityManager.flush();

        assertThat(sqlState(managed.getId())).isEqualTo("PAID");
    }

    @Test
    void findByIdMayReturnCachedManagedInstance() {
        PurchaseRecord managed = seeded("PO-102");
        Long id = managed.getId();

        managed.setState("PACKING");

        PurchaseRecord found = repository.findById(id)
                .orElseThrow();

        assertThat(found).isSameAs(managed);
        assertThat(found.getState()).isEqualTo("PACKING");

        // Một findById trả entity managed không chứng minh SQL UPDATE.
        assertThat(sqlState(id)).isEqualTo("NEW");
    }

    @Test
    void directJdbcUpdateDoesNotRefreshManagedEntity() {
        PurchaseRecord managed = seeded("PO-103");
        Long id = managed.getId();

        int changed = jdbcTemplate.update(
                "update purchase_records set state = ? where id = ?",
                "SHIPPED",
                id);
        assertThat(changed).isEqualTo(1);

        // Row hiện tại đã đổi trong transaction.
        assertThat(sqlState(id)).isEqualTo("SHIPPED");

        // First-level cache vẫn giữ state của entity đang managed.
        PurchaseRecord cached = repository.findById(id)
                .orElseThrow();
        assertThat(cached).isSameAs(managed);
        assertThat(cached.getState()).isEqualTo("NEW");

        entityManager.clear();

        // Entity không còn managed; lần tìm này nạp lại từ DB.
        PurchaseRecord reloaded = repository.findById(id)
                .orElseThrow();
        assertThat(reloaded).isNotSameAs(managed);
        assertThat(reloaded.getState()).isEqualTo("SHIPPED");
    }

    @Test
    void clearWithoutFlushDiscardsPendingDirtyState() {
        PurchaseRecord managed = seeded("PO-104");
        Long id = managed.getId();

        managed.setState("CANCELLED");
        assertThat(managed.getState()).isEqualTo("CANCELLED");

        // KHÔNG flush: state mới chỉ nằm ở persistence context.
        entityManager.clear();

        assertThat(entityManager.contains(managed)).isFalse();
        assertThat(sqlState(id)).isEqualTo("NEW");

        PurchaseRecord reloaded = repository.findById(id)
                .orElseThrow();
        assertThat(reloaded.getState()).isEqualTo("NEW");
    }

    @Test
    void flushThenClearCanReloadWrittenButUncommittedState() {
        PurchaseRecord managed = seeded("PO-105");
        Long id = managed.getId();

        managed.setState("PAID");
        repository.flush();
        entityManager.clear();

        PurchaseRecord reloaded = repository.findById(id)
                .orElseThrow();

        assertThat(reloaded).isNotSameAs(managed);
        assertThat(reloaded.getState()).isEqualTo("PAID");
        assertThat(sqlState(id)).isEqualTo("PAID");

        // PAID đã được ghi bằng SQL, nhưng @DataJpaTest vẫn rollback.
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
    }

    @Test
    void refreshOverwritesManagedStateFromDatabaseRow() {
        PurchaseRecord managed = seeded("PO-106");
        Long id = managed.getId();

        int changed = jdbcTemplate.update(
                "update purchase_records set state = ? where id = ?",
                "RETURNED",
                id);
        assertThat(changed).isEqualTo(1);

        assertThat(managed.getState()).isEqualTo("NEW");

        entityManager.refresh(managed);

        assertThat(entityManager.contains(managed)).isTrue();
        assertThat(managed.getState()).isEqualTo("RETURNED");
    }

    @Test
    void flushedInsertIsUndoneByExplicitTestRollback() {
        PurchaseRecord managed = seeded("PO-107");
        Long id = managed.getId();

        assertThat(sqlState(id)).isEqualTo("NEW");
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        // Kết thúc giao dịch hiện tại bằng ROLLBACK.
        TestTransaction.end();
        assertThat(TestTransaction.isActive()).isFalse();

        // Mở giao dịch khác để đọc dữ liệu sau rollback.
        TestTransaction.start();

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from purchase_records where id = ?",
                Integer.class,
                id);

        assertThat(count).isZero();
    }
}
```

**Kết quả mong đợi:** **7/7 test pass** trên dự án Spring Boot 3.x/H2/Hibernate tương thích như dependencies đã nêu. Không có dòng `System.out.println` nào trong sample; build tool có thể in log startup và summary, nhưng không có stdout ứng dụng cố định để sao chép.

**Cách đọc:** test `managedValueChangesBeforeDatabaseUpdateIsFlushed` chỉ ra sự khác biệt giữa managed object và hàng database; test `directJdbcUpdateDoesNotRefreshManagedEntity` chỉ ra tình huống ngược lại (database row đã đổi, managed object vẫn cũ). Hai tình huống này là hai chiều của cùng một vấn đề.

### 7.7. Lệnh chạy

Linux/macOS:

```bash
# Nếu dự án dùng Gradle:
./gradlew test --tests "com.example.jpaboundary.PersistenceBoundaryTest"

# Hoặc Maven:
./mvnw -Dtest=PersistenceBoundaryTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jpaboundary.PersistenceBoundaryTest"

# Hoặc Maven:
.\mvnw.cmd "-Dtest=PersistenceBoundaryTest" test
```

Dùng **một** build tool đúng với project. Nếu project multi-module, chọn đúng module chứa test. Nếu có Flyway/Liquibase hoặc custom datasource khác, sample cần tách thành module/dự án nhỏ hoặc cấu hình database test phù hợp; không kết nối database production để thử sự khác biệt flush/commit.

### 7.8. Vì sao helper `seeded(...)` dùng saveAndFlush?

`seeded(referenceCode)` tạo baseline state `NEW` và gọi `saveAndFlush(...)`. Điều này làm test bắt đầu từ một hàng đã được đưa vào database **trong test transaction**, tránh việc trộn hiệu ứng “INSERT cần sinh ID” vào phép đo về dirty UPDATE.

Nhưng **baseline chưa commit**. Khi `@DataJpaTest` rollback, cả baseline INSERT lẫn những UPDATE sau đó đều bị hoàn tác. Test thứ bảy dùng `TestTransaction.end()` để chứng minh điều đó trực tiếp.

### 7.9. Vì sao không dùng repository.findById để đo row?

Trong cùng persistence context, `findById` thường dựa trên `EntityManager.find`. Nếu entity đã managed, JPA có thể trả lại **cùng object instance**. Test thứ hai khẳng định `isSameAs(managed)`, đồng thời JDBC thấy row chưa đổi vì thiếu flush.

Khi kiểm tra “database row đã thay đổi hay chưa” **trước flush**, hãy dùng đường đọc không tự flush JPA, như JDBC trong cùng transaction. Khi kiểm tra “một EntityManager mới đọc được data không”, hãy `flush()` rồi `clear()` để ép JPA bỏ first-level cache và nạp lại. Hai dạng test trả lời những câu hỏi khác nhau.

### 7.10. Vì sao TestTransaction.end/start không phải thao tác mặc định?

Trong `@DataJpaTest`, test-managed transaction rollback tự động sau mỗi method, nên phần lớn test không cần gọi `TestTransaction.end()`.

Test cuối dùng:

1. `isFlaggedForRollback()` xác nhận transaction test đang theo policy rollback.
2. `end()` kết thúc transaction ngay, thực thi rollback vì flag.
3. `start()` mở **transaction test mới**.
4. JDBC `count(*)` xác nhận row cũ không còn sau rollback.

Đây là bài test có mục đích giáo dục về transaction boundary. Trong production code không gọi `TestTransaction`; class này thuộc **Spring TestContext**, chỉ nên dùng trong tests. Nếu test có nhiều transaction managers hoặc execution listeners bị tùy chỉnh, phải kiểm tra transaction manager được chọn.

## 8. Bảy tình huống trong test giải thích điều gì?

| Test | Nhìn từ JPA/Java | Nhìn từ database/transaction | Bài học |
|---|---|---|---|
| Managed đổi trước flush | `state = PAID` | JDBC trước flush vẫn `NEW`, sau flush `PAID` | Dirty state chưa chắc đã ghi SQL |
| `findById` dùng first-level cache | Trả đúng managed instance `PACKING` | JDBC vẫn `NEW` | Repository find không chứng minh SELECT/UPDATE vừa xảy ra |
| JDBC UPDATE ngoài JPA | Managed vẫn `NEW` | JDBC đã `SHIPPED` | Database thay đổi không làm object đang managed tự refresh |
| `clear()` không flush | Java object detached mang `CANCELLED` | DB vẫn `NEW` | Dirty state chưa flush có thể bị bỏ |
| `flush(); clear()` | Entity nạp lại mang `PAID` | Row đã `PAID` trong tx | Đã đồng bộ SQL nhưng chưa commit |
| `refresh(managed)` | Object managed đổi từ `NEW` sang `RETURNED` | JDBC row là `RETURNED` | Refresh đọc lại database, ghi đè managed state |
| Explicit rollback | Trước rollback thấy `NEW` | Transaction sau rollback đếm 0 | Flush không đồng nghĩa commit |

### 8.1. Không nhầm phép đo SQL với phép đo external visibility

Các JDBC assertions dùng **cùng Spring-managed transaction** với JPA. Chúng chứng minh SQL đã/chưa được đồng bộ vào database **trong giao dịch hiện tại**, không chứng minh một giao dịch ở process khác đã nhìn thấy row.

Để chứng minh external visibility, tạo **transaction/connection khác thực sự**, xác định isolation level và thời điểm commit/rollback. Tránh suy luận chỉ từ một JDBC query chạy trên cùng connection.

### 8.2. Khi database thật khác H2

Hibernate có thể tạo SQL khác theo dialect. RDBMS có thể trì hoãn constraint checking, áp isolation khác, tự động lock, tạo trigger, thay sequence/identity semantics hoặc có transaction snapshot behavior riêng. Bài test H2 đủ để học cơ chế persistence context; trước khi phát hành một hệ thống dùng PostgreSQL/MySQL/Oracle, nên có test integration trên database engine thực tế cho những quy tắc phụ thuộc database.

## 9. Hai chiều sai lệch: persistence context mới hơn hoặc cũ hơn DB

### 9.1. Case A: entity mới hơn database (dirty state chưa flush)

```text
Java managed entity: state = "PAID"
RDBMS row:          state = "NEW"
Reason:             Setter đã đổi RAM; chưa flush UPDATE
Fix/test:            em.flush(); JDBC SELECT cùng transaction
```

Đây là trường hợp đặc trưng của Hibernate write-behind. Các validation/mapping/constraint errors đôi khi chỉ xuất hiện tại flush chứ không phải ngay setter/save. Khi muốn test lỗi DB sớm, force flush ở thời điểm assertion có ý nghĩa.

### 9.2. Case B: database mới hơn entity (SQL ngoài persistence context)

```text
Java managed entity: state = "NEW"
RDBMS row:          state = "SHIPPED"
Reason:             JDBC/bulk SQL thay row, first-level cache chưa đồng bộ
Fix/test:            em.refresh(managed) hoặc em.clear(); em.find(...)
```

Những thay đổi đến từ `JdbcTemplate`, native SQL bulk updates, JPQL bulk `UPDATE/DELETE` hoặc một transaction khác **không tự sửa các Java object đang managed** trong persistence context hiện tại.

Khi dùng bulk DML của Spring Data JPA, annotation `@Modifying(clearAutomatically=true, flushAutomatically=true)` có thể hỗ trợ đồng bộ trước và clear sau query; cần hiểu rõ rằng clear có thể làm mất những dirty changes chưa flush nếu không thiết kế đúng. Không dùng clear tự động như một phép “đồng bộ database vào mọi object đang giữ”.

### 9.3. Vì sao có thể bị lost update?

Nếu database row bị JDBC UPDATE trực tiếp nhưng persistence context vẫn giữ state cũ, sau đó code tiếp tục đổi managed entity và flush, Hibernate có thể ghi UPDATE dựa trên snapshot cũ và đè lên thay đổi xảy ra ngoài JPA. Tùy mapping, SQL generation và concurrency, hậu quả có thể là **lost update** hoặc error khác.

Giảm rủi ro bằng:

- không trộn JDBC/JPQL bulk updates với managed entities mà thiếu chính sách clear/refresh;
- dùng `@Version`/optimistic locking khi domain yêu cầu;
- thực hiện thay đổi trong transaction boundaries phù hợp;
- kiểm tra concurrency và transaction isolation trên RDBMS thật;
- tránh giữ EntityManager dài quá mức, giữ persistence context nhỏ và rõ phạm vi.

**Lưu ý:** `@Version` không phải thuốc chữa mọi direct SQL: một câu JDBC UPDATE bỏ qua điều kiện/version increment có thể vô hiệu hóa phần mong đợi của optimistic locking. Nếu ngoài JPA cập nhật cùng table, phải có quy tắc về version/tính nhất quán.

## 10. Flush, clear và refresh: trình tự nào đúng?

### 10.1. Flush trước clear khi cần giữ dirty changes

Nếu muốn kiểm tra dữ liệu đã được viết ra database:

```java
managed.setState("PAID");

entityManager.flush();
entityManager.clear();

PurchaseRecord reloaded = entityManager.find(
        PurchaseRecord.class, managed.getId());

assertThat(reloaded.getState()).isEqualTo("PAID");
```

Đây là **snippet minh họa** trong test transaction có entity persisted baseline. Flush gửi pending SQL; clear detach managed objects; find sau clear có thể phát SELECT để tạo managed instance mới. Kết quả thể hiện state **trong transaction**, không commit.

Nếu đảo:

```java
managed.setState("PAID");

entityManager.clear();
entityManager.flush();
```

trong tình huống không có flush trước đó, dirty state của object đã bị detach và có thể **không còn pending update**; flush sau clear không tự tìm lại object để ghi. Bởi vậy `clear()` không phải phép “save trước rồi xóa cache”.

### 10.2. Refresh khi muốn lấy state từ DB

```java
entityManager.refresh(managed);
```

sẽ yêu cầu JPA tải lại database state cho một managed entity hợp lệ; có thể ghi đè giá trị mà object đang giữ, bao gồm những thay đổi chưa flush. Nếu entity đã detached (sau clear), refresh có thể không áp dụng được trực tiếp như với managed entity; cần `find`/`merge` thích hợp.

**Không gọi refresh chỉ để cho test pass** khi production vẫn không có logic refresh. Nếu bug do stale state, hãy cân nhắc transaction design hoặc đưa xử lý refresh/clear vào nơi có lý do nghiệp vụ.

### 10.3. Detach từng entity

`entityManager.detach(entity)` detach một object nhưng không flush. Nếu sau đó bạn giữ Java reference, object vẫn có field values cũ/mới trong RAM, nhưng JPA không còn dirty-check nó; thay đổi tiếp trên detached object không tự xuống DB. `merge(entity)` có thể đưa state từ detached object vào một managed copy, cần **dùng object được `merge` trả về** khi tiếp tục công việc.

Đừng nhầm việc thay đổi Java object sau detach với database row thay đổi.

## 11. Constraint, unique, FK và generated IDs: lỗi xuất hiện lúc nào?

### 11.1. Không hứa mọi INSERT bị hoãn

Với `@GeneratedValue(strategy=IDENTITY)`, provider thường phải chạy INSERT để biết generated key. Vì thế:

```java
PurchaseRecord p = repository.save(
        new PurchaseRecord("PO-201", "NEW"));

assertThat(p.getId()).isNotNull();
```

không tự chứng minh “database row chưa có”, và cũng không chứng minh commit. ID có giá trị và INSERT đã được thực hiện là hai việc cần phân tích theo generator/provider/transaction. Bài runnable không dựa vào timing INSERT.

Các chiến lược `SEQUENCE` hoặc `TABLE` thường có khả năng trì hoãn INSERT đến flush, nhưng sequence acquisition có thể vẫn gọi DB sớm; không suy diễn “không có SQL nào” chỉ vì INSERT bị hoãn.

### 11.2. Unique và NOT NULL thường phát hiện tại flush/INSERT

Giả sử entity có unique constraint, hai bản ghi cùng khóa có thể được Java code tạo mà chưa gặp lỗi; đến khi Hibernate flush/DB INSERT, RDBMS mới trả constraint violation. Với IDENTITY, INSERT sớm có thể khiến lỗi ném ở `persist/save`. Với constraints deferred (theo DB), lỗi có thể còn chờ đến commit.

Do đó test constraint đáng tin cần:

1. Dùng RDBMS phù hợp với constraint cần kiểm tra.
2. Cố định transaction và ID strategy.
3. Chủ động flush ở nơi hợp lý để ép SQL sớm **khi DB kiểm tra constraint tại statement**.
4. Bắt đúng root cause/exception translation của Spring/Hibernate; đừng đoán mọi DB trả cùng exception class/message.
5. Nếu có deferrable constraint kiểm tra lúc COMMIT, phải test commit boundary riêng.

### 11.3. Không giải quyết bằng “gọi saveAndFlush mọi nơi”

`saveAndFlush` có thể giúp bắt lỗi database sớm, nhưng gọi ở mỗi thao tác có thể giảm hiệu quả batching và tăng số SQL round-trip. Trong production, hãy chọn flush boundary phù hợp, thường giao cho transaction manager/provider. Dùng explicit flush khi cần immediate DB constraint evaluation, external synchronization hoặc đo trạng thái theo test contract.

## 12. @DataJpaTest, @Transactional và rollback mặc định

### 12.1. @DataJpaTest thực sự tạo môi trường gì?

Theo Spring Boot 3.5, `@DataJpaTest`:

- tập trung vào `@Entity`, JPA repositories và auto-configuration liên quan;
- có thể tự cấu hình embedded database nếu có H2/HSQLDB/Derby phù hợp trên classpath;
- **mặc định chạy từng test trong transaction và rollback sau test**;
- cung cấp `TestEntityManager` và `JdbcTemplate` khi hạ tầng tương ứng có sẵn;
- không tự nạp mọi `@Service`/controller thông thường.

Điều này làm test JPA nhanh, ít tác động bên ngoài. Nhưng khi bạn thấy `repository.saveAndFlush(...)` thành công rồi test kết thúc, **transaction bị rollback** theo mặc định — tức là row không được commit lâu dài.

### 12.2. TestEntityManager là công cụ gì?

Spring Boot cung cấp `TestEntityManager` bọc một số thao tác phổ biến trên JPA EntityManager trong tests, ví dụ `persist`, `persistAndFlush`, `flush`, `clear`, `find` và một số helper tùy version.

Trong ví dụ runnable, ta inject `jakarta.persistence.EntityManager` trực tiếp để học semantics JPA gốc. Nếu project dùng `TestEntityManager`, vẫn phải phân biệt:

- `persistAndFlush(entity)`: đưa entity vào context và flush, **không phải commit**.
- `flush()`: gửi pending SQL, không clear.
- `clear()`: detach, không tự flush.
- `find(...)`: có thể trả managed entity từ persistence context.

### 12.3. Test rollback khác production transaction

Một transactional test được Spring TestContext rollback sau method không chứng minh rằng production service sẽ rollback trong cùng tình huống. Production transaction có thể:

- commit khi method kết thúc;
- rollback theo exception rules của `@Transactional`;
- mở `REQUIRES_NEW` hoặc transaction ở thread khác;
- xử lý qua HTTP server thread thay vì test thread;
- có database timeout/isolation khác.

Trong `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP client và embedded server chạy ở các thread/transactions khác. `@Transactional` ở JUnit test **không tự rollback** dữ liệu mà server đã commit khi xử lý request. Nếu chuyển từ repository slice sang live HTTP test, phải thiết kế cleanup/schema test riêng.

### 12.4. TestTransaction hỗ trợ kiểm tra commit/rollback rõ ràng

Spring Test có `TestTransaction.isActive()`, `isFlaggedForRollback()`, `flagForRollback()`, `flagForCommit()`, `end()`, `start()`.

Lưu ý:

- `flagForRollback()` chỉ **đánh dấu**, chưa kết thúc transaction.
- `flagForCommit()` thay đổi kế hoạch kết thúc transaction; dùng thận trọng với fixtures, không tự động cleanup.
- `end()` kết thúc ngay theo flag hiện tại.
- `start()` mở test transaction mới sau end, không nên gọi khi transaction vẫn đang active.

Trong test cuối ở phần 7, default flag rollback được kiểm tra trước khi `end()`, và transaction mới được mở để đo row đã biến mất. Trình tự này an toàn với H2 test data riêng, **không dùng trên production database**.

## 13. Quan sát từ transaction/connection khác và isolation

### 13.1. Flush chỉ bảo đảm state trong transaction phù hợp

Giả sử transaction A thực hiện:

```text
TX-A: UPDATE purchase_records SET state='PAID' WHERE id=10
TX-A: chưa COMMIT
```

Khi TX-A đã flush, SQL UPDATE chạy. Nhưng TX-B đọc row ra sao phụ thuộc isolation, snapshot, lock, timing, DB engine. Dưới `READ_COMMITTED` thông thường, TX-B không thấy uncommitted version của TX-A; có thể thấy version cũ hoặc bị chặn khi xung đột, tùy query và engine.

Vì vậy:

- “JDBC cùng transaction đọc thấy PAID” **không** chứng minh đã commit.
- “Một connection khác không thấy PAID” không tự nói SQL chưa chạy; có thể do isolation.
- “Tôi bật READ_UNCOMMITTED và nhìn thấy PAID” cũng không có nghĩa transaction đã commit.

### 13.2. Muốn kiểm tra external committed state

Một phép kiểm tra commit/visibility cần:

1. Tạo fixture trong DB/schema thử nghiệm.
2. Kết thúc transaction với commit thật, theo đúng Spring transaction manager.
3. Mở transaction/connection mới và kiểm tra giá trị.
4. Cleanup bằng transaction khác, không dựa trên rollback của transaction cũ đã commit.
5. Khi kiểm tra concurrency, phối hợp threads/transaction boundaries deterministic để tránh race.

Nếu dùng H2 trong-memory single process, bạn đang đo behavior của H2. Nếu yêu cầu là PostgreSQL locking, write skew hoặc isolation anomalies, dùng PostgreSQL thực hoặc container trong CI.

### 13.3. Transaction-scoped EntityManager trong Spring

Với Spring Data JPA và transaction manager chuẩn, một `EntityManager` được inject bởi Spring có thể là proxy liên kết tới persistence context của transaction hiện tại. Điều này giải thích vì sao repository và `@PersistenceContext EntityManager` trong cùng transaction thường nhìn thấy cùng managed entity, nhưng **không cho phép** kết luận mọi repository khác transaction dùng cùng persistence context.

Nếu đổi thread, dùng transaction propagation khác hoặc mở EntityManager riêng, identity map và visibility boundaries thay đổi. Test nên ghi rõ phạm vi transaction.

## 14. Bulk JPQL updates/deletes là nguồn lệch cache phổ biến

### 14.1. Bulk UPDATE bỏ qua managed object synchronization

Ví dụ:

```java
@Modifying
@Query("update PurchaseRecord p "
        + "set p.state = :state where p.id = :id")
int updateStateDirectly(@Param("id") Long id,
                        @Param("state") String state);
```

Đây là **snippet khai báo repository method**, không phải file biên dịch độc lập. JPA bulk UPDATE chạy thẳng vào database, thường **không cập nhật từng managed Java entity** đã nằm trong persistence context.

Nếu cùng EntityManager đang giữ `PurchaseRecord(id, state="NEW")` rồi bulk UPDATE state sang `"PAID"`, object managed có thể vẫn là `NEW`. `repository.findById(id)` có thể tiếp tục trả instance cũ từ first-level cache.

### 14.2. flushAutomatically và clearAutomatically

Spring Data JPA hỗ trợ các option:

```java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true
)
```

khi dùng annotation này trên modifying query methods. Ý nghĩa chung:

- `flushAutomatically=true`: flush persistence context **trước** khi chạy query để tránh dirty state chưa được đồng bộ.
- `clearAutomatically=true`: clear persistence context **sau** query, để lần truy vấn JPA mới không dùng stale managed entities.

Nhưng **clear không flush** những thay đổi đã có nếu không cấu hình và thiết kế phù hợp; tự bật clear có thể làm mất dirty changes không được flush. Đừng dùng hai option vô điều kiện trên mọi repository method; test cần xác minh behavior và transaction policy.

### 14.3. Batch deletes cũng có thể lệch cache

Các phương thức như `deleteAllInBatch(...)` hoặc `deleteAllByIdInBatch(...)` thực hiện batch DML, không nhất thiết đồng bộ mọi managed entity state trong context và có thể bỏ qua entity lifecycle callbacks/cascade semantics mà xóa từng entity mang lại.

Khi sử dụng bulk deletes, hãy đọc Javadoc của Spring Data JPA version đang dùng, cân nhắc flush/clear và viết test về relationship/constraints. Không mặc định `findById` trong context cũ sẽ là nguồn chứng minh hàng đã bị xóa trên DB.

## 15. SQL logs: biết lúc nào Hibernate thực sự phát SQL

Để điều tra dirty changes và timing của flush, bật logging trong **môi trường test**:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Các cấu hình log này chủ yếu hướng đến Hibernate 6 / Spring Boot 3; chi tiết logger category phụ thuộc version. `spring.jpa.show-sql=true` có thể tạo output khác format/logging framework.

Quan sát khi test cập nhật managed entity:

```text
Bước Java                     SQL bạn có thể quan sát
---------------------------   -------------------------
saveAndFlush(new baseline)    INSERT (IDENTITY có thể INSERT sớm)
managed.setState("PAID")      chưa nhất thiết có UPDATE
JDBC SELECT trước flush       SELECT state -> "NEW"
entityManager.flush()         UPDATE ... SET state='PAID'
JDBC SELECT sau flush         SELECT state -> "PAID"
transaction rollback          ROLLBACK do Spring transaction manager
```

Đây là **bảng dòng sự kiện dự kiến**, không phải stdout chính xác của Hibernate/Gradle; số SQL, câu SQL cụ thể, binding order và log format có thể khác theo Hibernate version, dialect và batching.

**Không dùng “log thấy UPDATE” làm bằng chứng đã COMMIT.** SQL statements có thể chạy trong transaction bị rollback. Cũng không suy từ việc chưa thấy log là “không có SQL” nếu logging chưa bật/không đúng logger hoặc SQL chạy qua JDBC khác.

### 15.1. Không log dữ liệu nhạy cảm trong CI

TRACE binding có thể in parameter values bao gồm email, token hoặc thông tin khách hàng. Chỉ dùng fixture giả và logger này có thời hạn để debug; tránh bật rộng cho production hoặc upload CI artifacts chứa dữ liệu nhạy cảm.

## 16. Các lỗi phổ biến trong JPA testing

| Triệu chứng | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| `findById` thấy giá trị mới, SQL row chưa đổi | Entity đã managed, dirty state chưa flush | Dùng JDBC trước/sau explicit flush, hoặc flush+clear+find |
| `saveAndFlush` pass nhưng sau test không còn row | `@DataJpaTest` rollback mặc định | Phân biệt flush vs commit; dùng TestTransaction/transaction mới khi mục tiêu cần |
| JDBC UPDATE chạy nhưng JPA vẫn đọc state cũ | First-level cache đang giữ managed entity | `refresh()` hoặc `clear()+find`, thiết kế lại trộn JDBC/JPA |
| Clear làm mất thay đổi | Dirty state chưa flush | `flush()` trước `clear()` nếu mục tiêu phải ghi SQL |
| Test “trước flush” vẫn thấy DB row mới | JPQL/native query auto-flush hoặc IDENTITY INSERT sớm | Xác định query path và ID strategy, dùng JDBC cùng tx để đo |
| `save()` có ID nên nghĩ commit | ID có thể sinh trước commit | Đo bằng transaction boundary mới, không dùng ID như chỉ dấu commit |
| SQL UPDATE log có nhưng transaction rollback | Flush đã phát SQL, Spring test rollback | Kiểm tra rollback flag/test transaction |
| @Transactional test không rollback HTTP POST | Server xử lý trong transaction/thread riêng | Test DB cleanup/schema riêng, không tin rollback JUnit thread |
| Constraint lỗi xuất hiện ở `flush` | DB check sau INSERT/UPDATE thực | Ép flush khi appropriate, kiểm tra DB engine |
| Unique constraint fail chỉ ở commit | Deferred constraint hoặc transaction config | Test commit boundary trên DB thật |
| Query kết quả thay đổi khi thêm `findAll()` | AUTO flush của JPQL/Hibernate | Đặt explicit flush/check SQL và queries đúng mục tiêu |
| `EntityManager.refresh` ném lỗi | Entity đã detached/missing hoặc transaction không hợp lệ | Kiểm tra managed state, PK tồn tại, transaction |
| Second-level cache khiến clear vẫn chưa fresh | Cache L2 đã được bật và còn stale | Evict L2 theo chính sách hoặc test đúng cache boundary |
| H2 pass, PostgreSQL fail | Dialect, constraint, locking/isolation, migration khác | Dùng Testcontainers với production DB engine |
| Tests chạy song song fail ngẫu nhiên | Shared DB/schema/fixtures, fixed IDs hoặc tx isolation | Tạo unique fixtures và isolated test database |
| Repository test đột nhiên cần service/HTTP | Slice scan bị mở rộng/explicit ComponentScan | Kiểm tra @DataJpaTest và bootstrap configuration |
| Test không chạy trong transaction | @Transactional bị tắt, propagation NOT_SUPPORTED hoặc custom test listeners | Kiểm tra TestTransaction.isActive() và annotation |
| Bulk update xong findById vẫn cũ | Bulk SQL không sync managed entity | Flush/clear hoặc refresh, kiểm tra @Modifying |
| Test xanh vì chỉ assert object Java | Không đo row/flush/transaction | Assert qua JDBC hoặc nạp lại bằng context mới |

### 16.1. Quy trình debug theo từng lớp

1. **Xác nhận test có chạy không?** JUnit Jupiter, Gradle/Maven test task, report.
2. **Xác nhận transaction đang active không?** `TestTransaction.isActive()`.
3. **Xác nhận object managed không?** `entityManager.contains(object)`.
4. **Xác nhận DB row ban đầu có chưa?** `saveAndFlush` fixture và JDBC query cùng transaction.
5. **Xác nhận trước/sau flush có SQL gì?** Bật Hibernate SQL logs có kiểm soát.
6. **Xác nhận phương thức đọc có làm flush không?** JPQL/native JPA queries có thể làm thế.
7. **Xác nhận cache có ảnh hưởng không?** `findById` vs `clear()+find`.
8. **Xác nhận đã commit hay rollback?** TestTransaction/transaction manager.
9. **Nếu ngoại transaction nhìn khác:** kiểm tra isolation, snapshot và locking.
10. **Nếu production DB khác:** chạy integration test với production dialect/database.

Một lỗi ở bước 2 (không có transaction) không nên sửa bằng cách gọi `clear()`. Một lỗi ở bước 8 (rollback) không thể sửa chỉ bằng `saveAndFlush()`.

## 17. Best practices cho dự án Spring Boot

### 17.1. Không đặt mọi assertion vào cùng persistence context

Với các phép đo “ghi/đọc từ database”, dùng ít nhất một điểm rõ ràng:

- `entityManager.flush()` để gửi pending SQL;
- `entityManager.clear()` để bỏ identity map và nạp mới;
- JDBC query trong cùng transaction để quan sát SQL state;
- transaction mới khi phải đo committed state hoặc isolation.

Nếu chỉ assert managed object, hãy đặt tên test đúng như điều nó thực sự chứng minh, ví dụ `managedEntityIsUpdatedInMemory()`; đừng đặt `persistedToDatabase()` nếu chưa kiểm tra DB.

### 17.2. Cô lập test data, không phụ thuộc thứ tự

Dùng các reference codes cố định nhưng riêng mỗi test trong sample; transaction rollback giúp làm sạch. Trong hệ thống song song/có shared test DB, cần schema/DB riêng hoặc unique keys. Không dùng production database để chứng minh flush behavior, và tránh fixture có tên giống dữ liệu khách hàng thật.

### 17.3. Viết contract tests ở tầng phù hợp

- **Unit test:** business method thuần Java, không JPA.
- **`@DataJpaTest`:** mapping, queries, dirty checking, flush/clear, constraints ở JPA repository.
- **`@SpringBootTest`:** phối hợp service, transaction boundaries, persistence và các bean khác.
- **HTTP integration test:** request qua server, thread/transaction khác; cần cleanup DB.
- **Real database integration:** dùng cùng engine như production khi cần isolation/locking/SQL dialect.

Đừng đẩy toàn bộ business tests thành full Spring Boot context nếu chỉ cần một repository slice; cũng đừng kết luận repository slice đã kiểm tra network hoặc production transaction topology.

### 17.4. Không lạm dụng flush/clear trong production

Flush/clear rất hữu ích để **kiểm thử** và giải quyết các tình huống cụ thể trong production, nhưng:

- flush thường xuyên có thể giảm batching;
- clear detach mọi entity, khiến lazy access và thay đổi tiếp theo cần quản lý rõ;
- refresh có thể ghi đè thay đổi đang chờ;
- merge một detached object cũ có thể đưa lại state không mong muốn;
- explicit transaction commit/rollback nên thuộc transaction service boundary, không nằm rải rác trong controller/repository gọi tùy tiện.

Mục tiêu là hiểu SQL timing để thiết kế đúng, không phải gọi `flush()` ở mỗi setter.

## 18. Bài tập và lời giải

### Bài A. Khi findById trả giá trị mới

Bạn vừa gọi `managed.setState("PAID")` rồi `repository.findById(id)` trả `PAID`. Có thể kết luận database đã chạy SQL UPDATE không?

**Không.** Entity có thể được lấy trực tiếp từ first-level cache. Hãy đọc bằng JDBC cùng transaction **trước và sau** explicit `flush()`, hoặc flush+clear rồi find lại tùy mục tiêu.

### Bài B. saveAndFlush có phải commit?

Bạn gọi `repository.saveAndFlush(entity)` trong `@DataJpaTest`; JDBC cùng transaction đọc ra row mới. Sau test database không còn row. Có mâu thuẫn không?

**Không.** SaveAndFlush đồng bộ pending SQL, nhưng @DataJpaTest mặc định rollback test-managed transaction. Transaction chưa commit; rollback hoàn tác SQL đã flush.

### Bài C. clear trước flush

Entity baseline từ database có state `NEW`, test gọi `setState("SHIPPED")` rồi `entityManager.clear()`. Lần find kế tiếp trả `NEW`. Tại sao?

**Vì** dirty state chỉ nằm trong managed object đã bị detach trước khi flush; clear không tự ghi SQL. Khi muốn giữ update, flush trước clear.

### Bài D. JDBC mới hơn managed object

Sau khi JPA đọc state `NEW`, một JDBC UPDATE trong cùng transaction đổi state thành `PAID`. Repository.findById(id) vẫn trả NEW. Hãy nêu hai cách buộc đọc lại.

**Đáp án:** dùng `entityManager.refresh(managed)` nếu object vẫn managed, hoặc `entityManager.clear()` rồi `repository.findById(id)`. Chú ý cả hai có thể làm mất pending Java-only changes, nên chỉ dùng ở boundary có chủ đích.

### Bài E. JPQL select trước flush

Tại sao một `select p from PurchaseRecord p where p.state='PAID'` có thể làm JDBC sau đó thấy PAID dù bạn không gọi `flush()`?

**Vì** Hibernate AUTO flush có thể đồng bộ pending update trước truy vấn JPQL có query spaces liên quan. Đừng dùng truy vấn JPA đó để đo “trước flush”; hãy dùng JDBC cùng transaction mà không kích JPA flush.

### Bài F. IDENTITY và INSERT

Một entity được `save(...)`, ID đã có và thấy INSERT log trước explicit flush. Có phải ORM viết sai không?

**Không.** IDENTITY thường cần INSERT sớm để nhận generated ID. Cần phân biệt INSERT timing theo generator với UPDATE timing của managed entity đã tồn tại; cả hai đều có thể chưa commit.

### Bài G. Two transactions và visibility

TX-A đã flush state PAID nhưng chưa commit. TX-B ở READ_COMMITTED vẫn đọc NEW. Có thể suy ra flush không xảy ra không?

**Không.** TX-B không được đảm bảo thấy thay đổi chưa commit từ TX-A; đó là isolation behavior. Để kiểm tra flush, dùng same-transaction SQL read hoặc logs; để kiểm tra commit, kết thúc transaction rồi đọc từ transaction khác.

### Bài H. Vì sao TestTransaction.end() trong ví dụ không để lại dữ liệu?

Ở test cuối, `TestTransaction.isFlaggedForRollback()` là true. `end()` làm gì? `start()` tiếp theo để làm gì?

**Đáp án:** end kết thúc và rollback transaction theo flag; start mở một test-managed transaction mới. JDBC `count(*)` ở transaction mới trả 0 vì INSERT baseline đã rollback.

### Bài I. Bulk UPDATE rồi repository.findById

Một bulk JPQL update sửa state PAID nhưng managed entity vẫn NEW. Có nên gọi save(managed) ngay để “đồng bộ” không?

**Không.** Save/merge stale entity có nguy cơ ghi đè lại state cũ. Cần xác định đúng nguồn of truth, flush pending changes khi cần, clear/refresh theo giao dịch và dùng optimistic locking/version strategy nếu có concurrent updates.

## 19. Checklist QA cho test JPA persistence context

- [ ] Xác định rõ entity transient, managed, detached hay removed.
- [ ] Biết first-level cache thuộc EntityManager/persistence context nào.
- [ ] Tách state trong Java với SQL row trong transaction và committed database state.
- [ ] Không coi getter hoặc findById trên managed entity là bằng chứng SQL đã chạy.
- [ ] Kiểm tra `entityManager.contains(...)` khi cần xác định managed state.
- [ ] Dùng `flush()` khi muốn kiểm tra constraint/SQL effects tại boundary xác định.
- [ ] Hiểu `save` có thể persist/merge và `saveAndFlush` không commit.
- [ ] Không khẳng định INSERT luôn delayed nếu dùng IDENTITY generator.
- [ ] Không dùng JPQL/native EntityManager query làm phép đo trước flush nếu nó có thể AUTO flush.
- [ ] Khi dùng JDBC đo DB state, bảo đảm cùng transaction/connection và đúng table.
- [ ] Không nhầm JDBC cùng transaction với external transaction visibility.
- [ ] `clear()`/`detach()` không tự flush; tránh làm mất dirty changes.
- [ ] `refresh()` có thể ghi đè Java-only changes.
- [ ] Hiểu bulk JPQL/native updates không tự cập nhật managed entity.
- [ ] Có chiến lược kiểm soát lost update/optimistic locking khi trộn JPA với JDBC.
- [ ] `@DataJpaTest` transaction rollback đúng kỳ vọng.
- [ ] Dùng `TestTransaction` chỉ khi thực sự cần chứng minh transaction boundary.
- [ ] Không nhầm HTTP server transaction với test thread transaction.
- [ ] Với DB-dependent behavior, test thêm trên production database engine.
- [ ] Không dùng production dữ liệu/secrets trong test hay Hibernate SQL logs.
- [ ] Test chạy đúng class, JDK, Gradle/Maven Wrapper và kiểm tra test report.

## 20. Kết luận

**Dữ liệu trong persistence context, dữ liệu đã được flush xuống database và dữ liệu đã commit là ba lớp trạng thái khác nhau.** Một managed entity có thể mang giá trị mới trước khi SQL UPDATE chạy; một database row có thể đổi qua JDBC/bulk SQL trong khi managed entity vẫn giữ giá trị cũ; và SQL đã flush vẫn có thể bị rollback.

Trong Spring Data JPA, hãy chọn phép đo theo câu hỏi: **getter/contains** cho managed state, **JDBC + flush** cho SQL state trong transaction, **clear/refresh** để vượt first-level cache, và **transaction mới sau commit/rollback** để kiểm tra persistence thực sự theo isolation rules. Khi cần kiểm thử SQL dialect, unique constraints, transaction isolation hay locking giống production, dùng RDBMS tương ứng thay vì chỉ H2.

## Tài liệu tham khảo chính thức

- [Hibernate ORM — User Guide, Persistence Context](https://docs.hibernate.org/stable/orm/userguide/html_single/#pc): entity states, managed/detached, dirty checking, refresh/clear và identity map.
- [Hibernate ORM — User Guide, Flushing](https://docs.hibernate.org/stable/orm/userguide/html_single/#flushing): write-behind, AUTO/COMMIT flush, IDENTITY vs SEQUENCE, query-triggered flush và SQL.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @DataJpaTest, transaction rollback, TestEntityManager, JdbcTemplate và RANDOM_PORT caveat.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): save, persist/merge và entity-is-new determination.
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html): flush(), saveAndFlush() và batch operations.
- [Spring Data JPA — @Modifying API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html): flushAutomatically, clearAutomatically cho bulk queries.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed transaction và rollback.
- [Spring Framework — TestTransaction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): flagForRollback, flagForCommit, end/start.
- [Spring Boot 4 — Testing Data JPA](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): thay đổi package @DataJpaTest giữa Boot 3.x và 4.x; nguyên lý transaction/flush vẫn cần hiểu theo JPA/Hibernate version.
