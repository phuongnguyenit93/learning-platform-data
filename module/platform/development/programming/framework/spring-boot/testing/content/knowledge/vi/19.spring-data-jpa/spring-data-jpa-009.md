# Kiểm thử optimistic locking và xung đột cập nhật

## 1. Bài toán: hai người cùng sửa một bản ghi

Trong ứng dụng **Spring Boot + Spring Data JPA**, hai request có thể cùng đọc một bản ghi tồn kho, đơn hàng hoặc hồ sơ trước khi lưu thay đổi. Nếu không có cơ chế phát hiện xung đột, người ghi sau có thể **ghi đè thay đổi đã được người ghi trước lưu**, tạo ra hiện tượng *lost update*.

Giả sử hàng `SKU-7` có `quantity = 10`:

~~~text
Thời điểm       Người dùng A                 Người dùng B
    t0          đọc quantity=10, version=0  đọc quantity=10, version=0
    t1          sửa thành 8                 sửa thành 9
    t2          ghi quantity=8, version=1   vẫn giữ snapshot version=0
    t3          —                          cố ghi quantity=9 với version=0
                                               |
                         @Version -> từ chối cập nhật stale
    t4          DB vẫn quantity=8, version=1
~~~

Nếu thiếu kiểm tra phiên bản, lần ghi B có thể khiến DB thành 9 và che mất ý định của A. Với **optimistic locking**, DB chấp nhận thay đổi A rồi phát hiện B đang dựa trên **phiên bản cũ**. Phía B cần thông báo xung đột, đọc lại dữ liệu hoặc thực hiện một chiến lược retry được thiết kế rõ ràng.

**Optimistic** ở đây nghĩa là **không cố giữ khóa độc quyền trong suốt thời gian người dùng suy nghĩ**; ứng dụng để các bên đọc và thao tác, sau đó kiểm tra phiên bản khi ghi. Đây là lựa chọn thường phù hợp với hệ thống ít tranh chấp ghi so với tần suất đọc.

Mục tiêu của bài **“Kiểm thử optimistic locking và xung đột cập nhật”**, thuộc nhóm **Spring Data JPA**:

1. Hiểu `@Version`, phiên bản entity, persistence context và SQL điều kiện.
2. Viết test chứng minh **bản ghi cập nhật thành công tăng version**.
3. Tạo **hai snapshot độc lập** của cùng entity; ghi snapshot A, sau đó xác nhận snapshot B stale **bị từ chối**.
4. Kiểm tra DB giữ giá trị của lần ghi hợp lệ, không bị lần ghi stale ghi đè.
5. Phân biệt xung đột ORM trong một transaction với **xung đột phiên bản do client gửi qua HTTP**.
6. Biết cách kiểm tra HTTP `409 Conflict`, `412 Precondition Failed` khi sử dụng cơ chế tiền điều kiện và chính sách retry.
7. Tránh bẫy `@DataJpaTest` rollback, context cache, `flush` bị trì hoãn và H2 khác DB production.

Bài dùng **Java 17, Spring Boot 3.5.x, Spring Data JPA/Hibernate, H2 trong test và JUnit Jupiter**. Các đoạn chương trình đầy đủ được đặt ở đúng tệp. Những SQL/hướng mở rộng riêng sẽ được ghi là *minh họa* thay vì giả làm code test đã chạy.

## 2. @Version phát hiện xung đột ra sao?

JPA định nghĩa `jakarta.persistence.Version` cho một thuộc tính biểu diễn phiên bản của entity. Hibernate theo dõi giá trị phiên bản của từng bản ghi đã được tải, và khi flush một thay đổi nó có thể phát lệnh SQL có điều kiện theo **id và version cũ**.

~~~java
@Entity
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private int quantity;
}
~~~

**Đây là đoạn entity rút gọn để giải thích**; ví dụ runnable đầy đủ ở phần 5 có constructor, accessor, tên bảng và dữ liệu khác.

SQL dưới đây chỉ mô tả cơ chế, không phải cam kết Hibernate sẽ phát đúng thứ tự cột hoặc cú pháp cho mọi dialect:

~~~sql
-- A đã đọc version = 0 và cập nhật hợp lệ:
UPDATE inventory_items
SET quantity = 8, version = 1
WHERE id = 17 AND version = 0;
-- 1 row affected

-- B vẫn mang version = 0:
UPDATE inventory_items
SET quantity = 9, version = 1
WHERE id = 17 AND version = 0;
-- 0 rows affected => optimistic locking conflict
~~~

Khi câu `UPDATE` với version cũ không còn khớp bản ghi nào, Hibernate/JPA xử lý như dữ liệu stale và phát exception thay vì âm thầm ghi đè.

### Ba quy tắc không được nhầm

- **`@Version` thuộc về entity persistent**, không phải chỉ một field bất kỳ trong DTO hoặc request JSON. JPA provider quản lý và tăng phiên bản khi cập nhật versioned entity phù hợp.
- **Đừng tự đặt `entity.setVersion(entity.getVersion() + 1)`**. Việc tăng và kiểm tra version là trách nhiệm của provider; tự sửa field có thể phá điều kiện so sánh hoặc sinh lỗi mapping.
- **Có `@Version` chưa đủ bảo vệ một màn hình sửa lâu** nếu mỗi request HTTP luôn tải entity **mới nhất** rồi gán thay đổi mà **không mang expected version từ lúc người dùng đọc**. Trong tình huống đó, request B có thể ghi lên phiên bản hiện tại mà không bị coi là stale theo JPA.

Bởi vậy bài triển khai **hai lớp bảo vệ bổ sung**: JPA version check tại lúc flush/commit, và HTTP command mang `expectedVersion` để phát hiện người dùng gửi một lần sửa dựa trên dữ liệu đã cũ.

### Version được tăng khi nào?

Một entity mới với field `Long version` có thể bắt đầu bằng `null` trong Java trước khi persist; sau khi JPA persist/flush, Hibernate quản lý giá trị khởi tạo. **Đừng hard-code rằng version đầu tiên luôn là 0 trong mọi provider/mapping/database**. Trong test, giữ lại giá trị thực được trả về và assert rằng version **tăng** sau update.

Nếu chỉ đọc entity mà không sửa nó, version không tự động tăng chỉ vì `findById` được gọi. Trong Hibernate, một thay đổi managed entity có thể được ghi bằng dirty checking lúc flush, ngay cả khi không gọi `save`, nếu transaction đang hoạt động.

## 3. Các loại exception và thời điểm phát hiện

Một stale update có thể xuất hiện dưới nhiều lớp API:

| Nguồn | Ví dụ type | Ý nghĩa |
| --- | --- | --- |
| Jakarta Persistence | `jakarta.persistence.OptimisticLockException` | JPA phát hiện xung đột phiên bản |
| Hibernate | `StaleObjectStateException` và các lỗi stale liên quan | Provider cụ thể báo không thể cập nhật snapshot cũ |
| Spring ORM/DataAccess | `ObjectOptimisticLockingFailureException` hoặc subclass `OptimisticLockingFailureException` | Spring chuyển đổi lỗi persistence để tầng ứng dụng xử lý thống nhất |
| HTTP API | `409 Conflict` hoặc `412 Precondition Failed` theo contract | Client biết request không thể áp dụng theo trạng thái hiện tại |

Không cố assert **nguyên văn message** của exception ở mọi bản Spring/Hibernate. Message có thể chứa SQL, id hoặc tên entity khác theo phiên bản.

**Thời điểm xảy ra lỗi rất quan trọng:**

- `repository.save(entity)` có thể chưa phát SQL ngay, đặc biệt khi thao tác với entity managed. Lỗi có thể chỉ xuất hiện tại **flush hoặc commit**.
- `repository.saveAndFlush(entity)` yêu cầu flush trước khi method hoàn tất; khi không có transaction bao ngoài, Spring Data repository method tự quản lý transaction phù hợp.
- Nếu transaction của test bao quanh thao tác nhưng cuối test chỉ **rollback**, một số dirty updates chưa từng được flush và không chứng minh được version conflict.
- Với một transaction đã ném optimistic lock exception, đừng tiếp tục sửa/commit trong transaction lỗi. Hãy rollback và mở transaction **mới** cho lựa chọn xử lý tiếp.

Test nên assert **family exception** ở mức phù hợp và kiểm tra lại dữ liệu sau khi transaction thất bại, thay vì tin vào một log có chữ “stale”.

## 4. @DataJpaTest: cái bẫy transaction mặc định

`@DataJpaTest` tập trung JPA entities, repositories, `EntityManager` và datasource test. Nó đặc biệt phù hợp để kiểm tra optimistic locking ở persistence layer. Tuy nhiên, mặc định `@DataJpaTest` **mở transaction cho từng test và rollback sau test**.

Điều này có thể làm một bài test xung đột cho kết quả sai:

~~~java
@DataJpaTest
class MisleadingTest {
    // Cả hai lần findById trong cùng test-managed transaction
    // có thể lấy cùng một managed entity từ persistence context.
}
~~~

Nếu gọi hai lần `findById(id)` trong **cùng persistence context**, JPA identity map có thể trả lại **cùng một object managed**, không phải hai snapshot độc lập. Việc gán biến `a` và `b` khác nhau không chứng minh hai “người dùng” đã đọc hai phiên bản.

~~~java
InventoryItem a = repository.findById(id).orElseThrow();
InventoryItem b = repository.findById(id).orElseThrow();
// Trong cùng persistence context, a == b có thể là true.
~~~

Test như vậy **không mô phỏng stale version** đúng cách. Một lỗi khác là test mong `save(...)` ném exception ngay nhưng không flush, khiến assertion bỏ qua thời điểm SQL chạy.

### Chiến lược dùng trong bài

Với test JPA bên dưới, gắn:

~~~java
@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class InventoryOptimisticLockingTest {
    // Không có transaction test-managed bao ngoài.
}
~~~

Khi không có test transaction bao ngoài, mỗi lời gọi repository có transactional boundary riêng theo Spring Data JPA. Đối tượng do `findById` trả về được **detach sau khi transaction/persistence context của repository call hoàn tất**. Hai lần đọc liên tiếp tạo hai snapshot độc lập của bản ghi hiện tại. Lần save của A commit, còn bản B vẫn giữ version cũ và phải bị từ chối khi ghi.

**Lưu ý:** đây là một phép mô phỏng xung đột **tuần tự nhưng deterministic**, không phải hai request chạy cùng một nano-giây. Nó tạo đúng tình huống **hai bản sao được đọc trước lần ghi đầu tiên**, rồi kiểm tra lần ghi stale. Để xác thực deadlock, lock wait, transaction isolation và race thật, cần integration test concurrency với các transaction/connection tách biệt và DB cùng loại production.

## 5. Chuẩn bị dự án Spring Boot 3.5 + Java 17

Ta tạo một ứng dụng mẫu quản lý số lượng tồn kho. Chạy test JPA với DB H2 in-memory; dùng một HTTP API nhỏ để minh họa client gửi version và nhận `409`.

Cấu trúc:

~~~text
build.gradle
src/main/java/com/example/jpaoptimistic/
  LockingDemoApplication.java
  InventoryItem.java
  InventoryItemRepository.java
  InventoryView.java
  UpdateQuantityRequest.java
  InventoryService.java
  InventoryController.java
  InventoryApiAdvice.java
  ApiProblem.java
src/test/java/com/example/jpaoptimistic/
  InventoryOptimisticLockingTest.java
  InventoryHttpConflictTest.java
~~~

**`build.gradle` (Gradle Groovy DSL, Java 17):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-data-jpa` cung cấp Spring Data JPA và Hibernate; `starter-web` dùng cho API, `starter-validation` hỗ trợ `@Valid`/Jakarta constraints, `starter-test` có JUnit Jupiter/AssertJ/TestRestTemplate, H2 chỉ có trong **test runtime**.

Tệp build này phục vụ **test demo**. Do H2 chỉ ở `testRuntimeOnly`, để khởi chạy `bootRun` độc lập cần cấu hình một datasource/runtime DB phù hợp; đừng đưa H2 hay mật khẩu thử nghiệm vào cấu hình production như giải pháp mặc định.

Các ví dụ dùng package `com.example.jpaoptimistic` để Spring Boot scan entity, repository, service, controller và exception advice theo cấu trúc chuẩn.

### Entry point

**`src/main/java/com/example/jpaoptimistic/LockingDemoApplication.java`:**

~~~java
package com.example.jpaoptimistic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LockingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LockingDemoApplication.class, args);
    }
}
~~~

## 6. Entity @Version và repository thực

### 6.1. Entity có id, version và dữ liệu cập nhật

**`src/main/java/com/example/jpaoptimistic/InventoryItem.java`:**

~~~java
package com.example.jpaoptimistic;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku");
        setQuantity(quantity);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "Quantity must not be negative"
            );
        }
        this.quantity = quantity;
    }
}
~~~

Điểm cần chú ý:

- `@Version` từ **`jakarta.persistence.Version`**, không phải annotation cùng tên của một thư viện khác.
- `Long version` được JPA tự cập nhật; class **không có setter version**.
- Constructor `protected` không tham số để JPA tạo entity.
- Entity là class mutable theo yêu cầu của JPA persistence lifecycle, **không** phải Java record.
- `quantity` được sửa trong entity, còn version đi theo mỗi lần update thực sự.
- `@Column(unique=true)` hỗ trợ tính duy nhất của SKU ở schema do Hibernate tạo cho demo. Với DB thật, quản lý unique constraint bằng migration.

Đừng tạo bản sao entity bằng cách `new InventoryItem("SKU-7", ...)` rồi tự gán id/version qua reflection trong test: đó là mô phỏng quá sâu và có thể bỏ qua lifecycle JPA cần kiểm tra.

### 6.2. Repository

**`src/main/java/com/example/jpaoptimistic/InventoryItemRepository.java`:**

~~~java
package com.example.jpaoptimistic;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}
~~~

`JpaRepository` cung cấp `save`, `saveAndFlush`, `findById`, `deleteAll` và những method cơ bản. Cơ chế `@Version` ở entity được Hibernate/JPA thực hiện khi repository lưu entity; **không cần thêm `@Lock` vào `findById`** chỉ để có optimistic locking cho một lần update thông thường.

## 7. Bộ test JPA: tái hiện stale update mà không ngủ/chạy thread

**`src/test/java/com/example/jpaoptimistic/InventoryOptimisticLockingTest.java`:**

~~~java
package com.example.jpaoptimistic;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class InventoryOptimisticLockingTest {

    @Autowired
    InventoryItemRepository repository;

    private InventoryItem seeded;

    @BeforeEach
    void seedIndependentState() {
        // No test-managed transaction; repository methods commit themselves.
        repository.deleteAll();
        seeded = repository.saveAndFlush(
                new InventoryItem("SKU-7", 10)
        );
    }

    @Test
    void newEntity_hasManagedNonNullVersion() {
        assertThat(seeded.getId()).isNotNull();
        assertThat(seeded.getVersion()).isNotNull();

        InventoryItem stored = repository.findById(seeded.getId())
                .orElseThrow();

        assertThat(stored.getQuantity()).isEqualTo(10);
        assertThat(stored.getVersion()).isEqualTo(seeded.getVersion());
    }

    @Test
    void successfulUpdate_incrementsVersion() {
        Long before = seeded.getVersion();

        InventoryItem current = repository.findById(seeded.getId())
                .orElseThrow();
        current.setQuantity(8);

        InventoryItem saved = repository.saveAndFlush(current);

        assertThat(saved.getVersion()).isGreaterThan(before);
        assertThat(repository.findById(seeded.getId()).orElseThrow()
                .getQuantity()).isEqualTo(8);
    }

    @Test
    void staleDetachedCopy_failsAndDoesNotOverwriteCommittedData() {
        Long id = seeded.getId();

        // Each repository read is a separate transaction/context.
        InventoryItem snapshotA = repository.findById(id).orElseThrow();
        InventoryItem snapshotB = repository.findById(id).orElseThrow();

        assertThat(snapshotA).isNotSameAs(snapshotB);
        assertThat(snapshotA.getVersion())
                .isEqualTo(snapshotB.getVersion());

        Long versionBefore = snapshotA.getVersion();

        snapshotA.setQuantity(8);
        InventoryItem firstWrite = repository.saveAndFlush(snapshotA);
        assertThat(firstWrite.getVersion())
                .isGreaterThan(versionBefore);

        snapshotB.setQuantity(9);

        assertThatThrownBy(
                () -> repository.saveAndFlush(snapshotB)
        ).isInstanceOf(OptimisticLockingFailureException.class);

        InventoryItem afterConflict = repository.findById(id)
                .orElseThrow();

        assertThat(afterConflict.getQuantity()).isEqualTo(8);
        assertThat(afterConflict.getVersion())
                .isEqualTo(firstWrite.getVersion());
    }

    @Test
    void freshReadAfterFirstCommit_canUpdateAgain() {
        Long id = seeded.getId();

        InventoryItem first = repository.findById(id).orElseThrow();
        first.setQuantity(8);
        InventoryItem updatedA = repository.saveAndFlush(first);

        InventoryItem fresh = repository.findById(id).orElseThrow();
        assertThat(fresh.getVersion()).isEqualTo(updatedA.getVersion());

        fresh.setQuantity(6);
        InventoryItem updatedB = repository.saveAndFlush(fresh);

        assertThat(updatedB.getQuantity()).isEqualTo(6);
        assertThat(updatedB.getVersion())
                .isGreaterThan(updatedA.getVersion());
    }

    @Test
    void independentRows_doNotConflict() {
        InventoryItem second = repository.saveAndFlush(
                new InventoryItem("SKU-8", 20)
        );

        InventoryItem itemA = repository.findById(seeded.getId())
                .orElseThrow();
        InventoryItem itemB = repository.findById(second.getId())
                .orElseThrow();

        itemA.setQuantity(7);
        itemB.setQuantity(19);

        repository.saveAndFlush(itemA);
        repository.saveAndFlush(itemB);

        assertThat(repository.findById(itemA.getId())
                .orElseThrow().getQuantity()).isEqualTo(7);
        assertThat(repository.findById(itemB.getId())
                .orElseThrow().getQuantity()).isEqualTo(19);
    }
}
~~~

### 7.1. Vì sao bài test stale là quan trọng nhất?

Test tạo **hai bản sao được tải trước khi có cập nhật**. Nó chứng minh:

1. Cả hai snapshot có version ban đầu bằng nhau.
2. Chúng **không phải cùng Java object**, do không có test-managed transaction dài bao ngoài.
3. Snapshot A ghi thành công và version trong DB tăng.
4. Snapshot B vẫn có version cũ, `saveAndFlush` bị Spring báo lỗi thuộc `OptimisticLockingFailureException`.
5. DB vẫn giữ `quantity = 8` và version của A, không bị stale snapshot B ghi đè.

Không cần `Thread.sleep` hoặc tạo hai Java thread để kiểm tra chính sách **stale write rejection**. Cách test tuần tự này nhanh, có thể lặp lại và thường giúp phân biệt lỗi version mapping tốt hơn so với race test may rủi.

### 7.2. Khi nào exception chưa xuất hiện?

Nếu bỏ `saveAndFlush`, sử dụng `save` rồi giữ nguyên một transaction bao ngoài, Hibernate có thể chỉ phát hiện stale ở commit/flush sau đó. Hãy đặt assertion vào đúng chỗ buộc DB update xảy ra. Nếu kiểm tra lỗi tại `flush()` trong một transaction do test quản lý, cần bảo đảm transaction đó không bị rollback trước khi SQL mong muốn chạy.

### 7.3. Vấn đề dữ liệu test bị chia sẻ

Vì test dùng `Propagation.NOT_SUPPORTED`, cập nhật thành công **thực sự commit vào DB test**. `@BeforeEach` gọi `repository.deleteAll()` rồi tạo lại một hàng `SKU-7`, giúp mỗi test bắt đầu với dữ liệu mong đợi. Đừng bỏ setup này rồi cho rằng `@DataJpaTest` vẫn rollback mọi thứ theo mặc định: annotation propagation đã chủ động thay đổi hành vi.

Khi test chạy song song trên **cùng datasource**, setup `deleteAll` toàn bảng có thể va chạm. Demo giả định JUnit chạy tuần tự; production suite nên dùng mỗi test một DB/schema/tenant riêng hoặc ID riêng và cleanup được cô lập.

## 8. @Version không thay thế “expected version” của client HTTP

Một người mở form ở thời điểm T0:

~~~text
GET /api/inventory/42

{
  "id": 42,
  "sku": "SKU-7",
  "quantity": 10,
  "version": 0
}
~~~

Năm phút sau, người đó nhấn Save. Trong thời gian đó, người khác đã cập nhật entity thành version 1. Nếu API thực hiện:

~~~java
InventoryItem current = repository.findById(id).orElseThrow();
current.setQuantity(request.quantity());
repository.saveAndFlush(current);
~~~

thì nó vừa tải version **mới nhất**, có thể ghi hợp lệ theo JPA nhưng vẫn **ghi đè quyết định của người dùng khác**. Không có dấu hiệu nào cho biết request được xây trên version cũ.

Với API hỗ trợ chỉnh sửa có kiểm soát, request nên mang **expectedVersion**, hoặc dùng tiêu chuẩn HTTP **`If-Match` + ETag**:

~~~http
PUT /api/inventory/42/quantity
Content-Type: application/json

{"expectedVersion":0,"quantity":8}
~~~

Service so sánh version hiện tại với version client đã đọc. Nếu khác, trả lỗi xung đột có chủ đích. Nhưng **so sánh version thủ công ở đầu transaction chưa đủ trong race đồng thời**: hai transaction có thể cùng đọc version 0, cùng pass điều kiện và cùng muốn ghi. `@Version` của JPA vẫn là lớp bảo vệ ở flush/commit.

Hai mức cần test riêng:

| Mức | Dữ liệu stale đến từ đâu? | Chứng minh |
| --- | --- | --- |
| ORM optimistic locking | Hai entity snapshots cũ trong các persistence contexts độc lập | Hibernate từ chối stale `UPDATE` |
| HTTP business conflict | Hai client giữ cùng `expectedVersion` khi gửi yêu cầu | Server không âm thầm chấp nhận request dựa trên version cũ |

## 9. DTO và service @Transactional cho HTTP API

### 9.1. DTO trả dữ liệu và version

**`src/main/java/com/example/jpaoptimistic/InventoryView.java`:**

~~~java
package com.example.jpaoptimistic;

public record InventoryView(
        Long id,
        String sku,
        int quantity,
        Long version
) {
    public static InventoryView from(InventoryItem item) {
        return new InventoryView(
                item.getId(),
                item.getSku(),
                item.getQuantity(),
                item.getVersion()
        );
    }
}
~~~

Version được trả cho client để client gửi lại khi ghi. Trong ứng dụng có dữ liệu nhạy cảm, xem xét những field nào được công bố; không trả JPA entity trực tiếp nếu dễ gây lộ quan hệ/lazy proxies.

### 9.2. Payload cập nhật

**`src/main/java/com/example/jpaoptimistic/UpdateQuantityRequest.java`:**

~~~java
package com.example.jpaoptimistic;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record UpdateQuantityRequest(
        @NotNull Long expectedVersion,
        @NotNull @Min(0) Integer quantity
) {
}
~~~

Dùng `Integer quantity` thay vì `int` để phân biệt **thiếu field** và số 0 hợp lệ. `@Valid` trong controller cùng Jakarta validator từ starter validation sẽ từ chối payload null hoặc âm.

### 9.3. Service thật với transaction boundary

**`src/main/java/com/example/jpaoptimistic/InventoryService.java`:**

~~~java
package com.example.jpaoptimistic;

import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryItemRepository repository;

    public InventoryService(InventoryItemRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    @Transactional(readOnly = true)
    public InventoryView get(Long id) {
        InventoryItem item = repository.findById(id)
                .orElseThrow(ItemNotFound::new);
        return InventoryView.from(item);
    }

    @Transactional
    public InventoryView changeQuantity(
            Long id,
            UpdateQuantityRequest request
    ) {
        Objects.requireNonNull(request, "request");

        InventoryItem current = repository.findById(id)
                .orElseThrow(ItemNotFound::new);

        if (!Objects.equals(
                current.getVersion(), request.expectedVersion()
        )) {
            throw new StaleVersion();
        }

        current.setQuantity(request.quantity());

        // Force detection before returning from the service method.
        InventoryItem saved = repository.saveAndFlush(current);
        return InventoryView.from(saved);
    }

    public static class ItemNotFound extends RuntimeException {
    }

    public static class StaleVersion extends RuntimeException {
    }
}
~~~

Ở đây Spring AOP `@Transactional` tạo transaction quanh `changeQuantity`. Service kiểm tra expected version của client, thay đổi entity **managed** và `saveAndFlush` để đẩy update xuống DB trước khi trả DTO.

Nếu hai request đồng thời đã đọc cùng version và cùng pass `Objects.equals`, optimistic lock check của Hibernate tại flush/commit vẫn ngăn việc ghi stale. Lỗi có thể nảy sinh trong repository call hoặc khi transaction hoàn tất ở proxy; tầng web phải xử lý cả **`StaleVersion`** và **`OptimisticLockingFailureException`**.

Không retry bằng cách gọi lại `saveAndFlush(current)` trong **cùng transaction đã thất bại**. Transaction có thể rollback-only và entity state không còn an toàn để tái sử dụng.

## 10. Controller và HTTP 409 Conflict

**`src/main/java/com/example/jpaoptimistic/InventoryController.java`:**

~~~java
package com.example.jpaoptimistic;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {
    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public InventoryView get(@PathVariable Long id) {
        return service.get(id);
    }

    @PutMapping(
            value = "/{id}/quantity",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public InventoryView update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateQuantityRequest request
    ) {
        return service.changeQuantity(id, request);
    }
}
~~~

**`src/main/java/com/example/jpaoptimistic/ApiProblem.java`:**

~~~java
package com.example.jpaoptimistic;

public record ApiProblem(String code) {
}
~~~

**`src/main/java/com/example/jpaoptimistic/InventoryApiAdvice.java`:**

~~~java
package com.example.jpaoptimistic;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InventoryApiAdvice {

    @ExceptionHandler({
            InventoryService.StaleVersion.class,
            OptimisticLockingFailureException.class
    })
    public ResponseEntity<ApiProblem> conflict(Exception ignored) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiProblem("VERSION_CONFLICT"));
    }

    @ExceptionHandler(InventoryService.ItemNotFound.class)
    public ResponseEntity<ApiProblem> notFound(Exception ignored) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiProblem("ITEM_NOT_FOUND"));
    }
}
~~~

Đây là một **HTTP contract tự thiết kế**:

- GET thành công → **200** với `InventoryView` (bao gồm `version`).
- PUT với expected version hiện tại → **200** và version mới sau update.
- PUT với version cũ → **409 Conflict** và JSON `{"code":"VERSION_CONFLICT"}`.
- ID không tồn tại → **404 Not Found**.
- Request thiếu expected version hoặc quantity âm → **400 Bad Request** do Bean Validation.

**409 không phải là mã duy nhất có thể dùng cho mọi conflict.** Nếu API triển khai HTTP conditional requests với `ETag` và `If-Match`, khi tiền điều kiện không khớp, **412 Precondition Failed** là cách biểu đạt HTTP thích hợp; API có thể yêu cầu `428 Precondition Required` nếu client thiếu precondition. Ví dụ hiện tại dùng JSON `expectedVersion` nên chủ động chọn 409.

Một `@ExceptionHandler(OptimisticLockingFailureException.class)` giúp chuyển exception persistence thành phản hồi ổn định, nhưng trong một kiến trúc phức tạp có exception bọc bên ngoài, cần bảo đảm tầng dịch lỗi/transaction thực sự chuyển được nguyên nhân như mong muốn; không tự trả stack trace/SQL ra client.

## 11. HTTP integration test: người dùng gửi version cũ

Test này dùng **server thật** trong `@SpringBootTest(RANDOM_PORT)` và `TestRestTemplate`. Nó không chỉ gọi Java method mà đi qua HTTP serialization, controller, service, repository và H2 DB. Không cần trình duyệt để chứng minh API conflict contract.

**`src/test/java/com/example/jpaoptimistic/InventoryHttpConflictTest.java`:**

~~~java
package com.example.jpaoptimistic;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class InventoryHttpConflictTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    InventoryItemRepository repository;

    private Long id;

    @BeforeEach
    void seed() {
        repository.deleteAll();
        id = repository.saveAndFlush(
                new InventoryItem("SKU-7", 10)
        ).getId();
    }

    private HttpEntity<UpdateQuantityRequest> json(
            Long expectedVersion,
            Integer quantity
    ) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return new HttpEntity<>(
                new UpdateQuantityRequest(expectedVersion, quantity),
                headers
        );
    }

    private InventoryView getCurrent() {
        ResponseEntity<InventoryView> response = http.getForEntity(
                "/api/inventory/{id}",
                InventoryView.class,
                id
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        return response.getBody();
    }

    @Test
    void staleClientVersion_returns409AndPreservesFirstWrite() {
        InventoryView before = getCurrent();

        ResponseEntity<InventoryView> first = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(before.version(), 8),
                InventoryView.class,
                id
        );

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(first.getBody()).isNotNull();
        assertThat(first.getBody().quantity()).isEqualTo(8);
        assertThat(first.getBody().version())
                .isGreaterThan(before.version());

        ResponseEntity<ApiProblem> stale = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(before.version(), 9),
                ApiProblem.class,
                id
        );

        assertThat(stale.getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT);
        assertThat(stale.getBody())
                .isEqualTo(new ApiProblem("VERSION_CONFLICT"));

        InventoryView after = getCurrent();
        assertThat(after.quantity()).isEqualTo(8);
        assertThat(after.version())
                .isEqualTo(first.getBody().version());
    }

    @Test
    void newVersionAfterRefresh_allowsAnotherUpdate() {
        InventoryView before = getCurrent();

        ResponseEntity<InventoryView> first = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(before.version(), 8),
                InventoryView.class,
                id
        );

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(first.getBody()).isNotNull();

        ResponseEntity<InventoryView> second = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(first.getBody().version(), 6),
                InventoryView.class,
                id
        );

        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(second.getBody()).isNotNull();
        assertThat(second.getBody().quantity()).isEqualTo(6);
        assertThat(second.getBody().version())
                .isGreaterThan(first.getBody().version());

        assertThat(getCurrent().quantity()).isEqualTo(6);
    }

    @Test
    void missingExpectedVersion_returns400WithoutChangingRow() {
        InventoryView before = getCurrent();

        ResponseEntity<String> invalid = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(null, 8),
                String.class,
                id
        );

        assertThat(invalid.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        InventoryView after = getCurrent();
        assertThat(after.quantity()).isEqualTo(before.quantity());
        assertThat(after.version()).isEqualTo(before.version());
    }

    @Test
    void unknownId_returns404() {
        ResponseEntity<ApiProblem> response = http.getForEntity(
                "/api/inventory/{id}",
                ApiProblem.class,
                Long.MAX_VALUE
        );

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody())
                .isEqualTo(new ApiProblem("ITEM_NOT_FOUND"));
    }
}
~~~

### 11.1. Điều gì được kiểm tra?

- **Phản hồi hiện tại có version:** client phải biết revision hiện tại trước khi sửa.
- **Lần ghi A thành công:** HTTP 200, quantity 8 và version tăng.
- **Lần ghi B với version cũ thất bại:** HTTP 409 và error code cụ thể.
- **DB không bị ghi đè:** GET tiếp theo vẫn quantity 8 và version của A.
- **Client refresh có thể ghi lại:** dùng version mới làm expected version.
- **Payload thiếu expected version:** HTTP 400 trước khi đổi dữ liệu.
- **ID không tồn tại:** HTTP 404, không trộn với lỗi version.

HTTP test này kiểm tra **xung đột cấp request** theo expected version một cách tuần tự. Còn test `InventoryOptimisticLockingTest` ở phần 7 kiểm tra **chính cơ chế version enforcement của ORM**. Cả hai cùng cần thiết: manual version comparison ở service không thay thế optimistic lock của JPA khi request thật sự đồng thời.

### 11.2. Vì sao không thêm @Transactional vào HTTP test?

Trong `@SpringBootTest(RANDOM_PORT)`, test method dùng HTTP client, còn server xử lý request trong thread/transaction riêng. `@Transactional` trên phía test client **không tự rollback** các thay đổi đã commit trong HTTP server transaction. Ví dụ dùng `@BeforeEach` seed/reset data và chỉ thao tác một row test. Trong bộ test thật, nếu nhiều test chạy song song, cần fixture isolation thay cho `deleteAll` toàn bảng.

**Không hard-code port 8080:** `TestRestTemplate` do Boot cấu hình tự gửi URL tương đối đến server test. Dữ liệu JSON và expected version có thể kiểm soát được, vì vậy không cần `Thread.sleep` hay đoán thứ tự chạy request.

## 12. Phân biệt xung đột JPA và xung đột business rule

Cùng một `409 Conflict` có thể mang nhiều ý nghĩa:

| Xung đột | Cách phát hiện | Ví dụ |
| --- | --- | --- |
| Optimistic lock stale entity | `@Version` và SQL affected rows | Hai snapshot cùng version ghi nối tiếp |
| Client expected version cũ | Service so sánh với version hiện tại | Form được mở trước khi người khác sửa |
| Business invariant | Kiểm tra domain ở transaction phù hợp | Không thể giảm tồn kho dưới 0 |
| Unique constraint | Database unique index | Hai request tạo trùng SKU |
| Pessimistic lock/timeout | DB lock hoặc transaction timeout | Tài nguyên bị transaction khác khóa |

Không nên catch **mọi `RuntimeException`** rồi trả 409; lỗi lập trình, datasource mất kết nối hay HTTP client sai payload không phải version conflict.

Tương tự, **optimistic locking không tự giải quyết overselling** nếu nghiệp vụ đọc nhiều hàng hoặc cần bảo đảm tổng tồn kho xuyên nhiều aggregate. Nếu chỉ có version trên từng item, các bất biến liên quan nhiều row vẫn cần transaction isolation, khóa/constraint hoặc mô hình coordination phù hợp.

### Nếu API dùng ETag và If-Match

Một API chuẩn HTTP có thể gửi:

~~~http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/json

{"id":42,"sku":"SKU-7","quantity":10}
~~~

Client ghi:

~~~http
PUT /api/inventory/42/quantity
If-Match: "7"
Content-Type: application/json

{"quantity":8}
~~~

Nếu ETag không khớp resource version hiện tại, **412 Precondition Failed** diễn đạt rõ tiền điều kiện bị vi phạm. Tuy nhiên phải phân biệt **strong/weak ETag semantics** và cách generate ETag theo representation; đừng đơn giản đặt string version rồi cho rằng đã thực hiện chuẩn If-Match đầy đủ. Ví dụ runnable trong bài **không triển khai ETag**, mà dùng expected version trong JSON với 409.

## 13. Bulk update/delete và những đường có thể bypass @Version

`@Version` bảo vệ các thao tác ORM entity thông thường. Nhưng **JPQL bulk update/delete**, native SQL và các job ghi thẳng database có thể **bỏ qua kiểm tra và việc tăng version tự động** của từng entity.

Ví dụ truy vấn dễ gây nguy hiểm nếu dùng để cập nhật quantity một cách thiếu kiểm soát:

~~~java
@Modifying
@Query("""
       update InventoryItem i
       set i.quantity = :quantity
       where i.id = :id
       """)
int replaceQuantityWithoutVersionCheck(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

Đây là **đoạn method repository minh họa**, không có trong `InventoryItemRepository` runnable của phần 6. Nó **không** tự so sánh version cũ và thường **không** tăng version. Nếu một job dùng đường này trong khi request bình thường dùng ORM, bảo vệ optimistic locking có thể mất tác dụng.

Một cách tiếp cận có kiểm soát là đưa version vào điều kiện và kiểm tra số hàng:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
       update InventoryItem i
       set i.quantity = :quantity,
           i.version = i.version + 1
       where i.id = :id
         and i.version = :expectedVersion
       """)
int updateIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") Long expectedVersion,
        @Param("quantity") int quantity
);
~~~

Đây cũng là **đoạn mở rộng minh họa** cho numeric version `Long`, cần `@Transactional` ở tầng service/caller, import `@Modifying`/`@Query`/`@Param` và một chiến lược handle kết quả trả về:

- `rows == 1`: đã cập nhật đúng một hàng theo version.
- `rows == 0`: version không khớp **hoặc id không tồn tại**; cần phân biệt nếu API có hai mã lỗi khác nhau.
- Query bulk **bỏ qua persistence context managed state**. Nếu đã có entity được load trong cùng transaction, cần flush/clear theo cách phù hợp hoặc tránh trộn bulk update với dirty managed entity; tùy tình huống có nguy cơ đọc stale data.

Cách này không phải thay thế tự động cho tất cả thao tác JPA versioned entity. Nó yêu cầu test riêng về affected rows, transaction boundary, id không tồn tại, xử lý lỗi và hỗ trợ DB dialect. **Không dùng query bulk không có version predicate** khi yêu cầu là không để stale writer ghi đè.

## 14. Optimistic vs pessimistic locking; @Lock không phải @Version

| Thuộc tính | Optimistic `@Version` | Pessimistic `PESSIMISTIC_WRITE` |
| --- | --- | --- |
| Cách tiếp cận | Phát hiện conflict lúc ghi/kiểm tra version | Giữ lock DB trên row trong transaction |
| Khi phù hợp | Đọc nhiều, ghi ít; client có thời gian suy nghĩ | Cạnh tranh ghi cao hoặc bắt buộc tuần tự hóa ở DB |
| Rủi ro chính | Writer phải xử lý conflict/retry | Lock wait, timeout, deadlock, throughput giảm |
| Thời gian giữ | Không khóa suốt thời gian chờ user | Lock tồn tại trong phạm vi transaction |
| Test cần có | Stale snapshot, version tăng, no lost update | Hai transaction thật, lock wait/timeout/isolation |

Ví dụ repository có thể yêu cầu lock khi đọc:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> findForUpdate(@Param("id") Long id);
~~~

Đây là **đoạn method mở rộng**, cần imports `jakarta.persistence.LockModeType`, Spring Data `@Lock`, `@Query`, `@Param` và transaction thực. Nó **khác** với `@Version`: một phiên gọi `findForUpdate` ngoài transaction phù hợp không thể thay thế khóa DB được giữ trong transaction.

JPA còn `LockModeType.OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT` để xác nhận version/ép tăng version trong một số tình huống đọc hoặc phối hợp aggregate. Đừng sử dụng chúng như một “thuốc chữa” cho bất biến giữa nhiều bảng mà chưa có thiết kế transaction/coordinator rõ.

## 15. Kiểm thử concurrency thực sự với database production-like

Test tuần tự hai snapshot trong phần 7 xác nhận **cơ chế stale version**. Để kiểm tra behavior gần production khi có hai transaction đồng thời, nên viết một bộ integration tests khác với **PostgreSQL/MySQL cùng loại production qua Testcontainers**, hoặc một DB test tương đương.

### Kịch bản kiểm thử hai transaction

~~~text
Tạo item version V
         |
      chia 2 transaction thật
         |
   Tx A read version V         Tx B read version V
         |                            |
   chờ cả hai đọc xong          chờ cả hai đọc xong
         |                            |
   A cập nhật / commit             B cố cập nhật / commit
         |                            |
   A thành công                     B conflict hoặc bị DB chặn
         |                            |
   kiểm tra cuối: dữ liệu A, version V+1
~~~

Đây là **sơ đồ kịch bản**, không phải mã lập lịch thread đã chạy. Trong test thực tế:

1. Dùng hai transaction tách biệt, tránh để cả hai luồng chia sẻ một `EntityManager` vì `EntityManager` không thread-safe.
2. Dùng barrier/latch để chắc chắn **cả hai đã đọc cùng version** trước khi cho phép update.
3. Kiểm soát thứ tự commit nếu cần test quyết định A thắng; không dựa vào `Thread.sleep(200)`.
4. Xem DB isolation: một số DB có thể báo serialization failure/deadlock/lock timeout ở một bước khác thay vì exception JPA “đẹp” mà bạn dự kiến.
5. Không assert cứng tên exception của một DB khi chưa xác định behavior của dialect/isolation.
6. Sau transaction lỗi, rollback, query lại bằng persistence context **mới** rồi assert dữ liệu cuối.
7. Không tạo transaction dùng chung giữa test method và server thread nếu test là HTTP integration.
8. Tránh chạy nhiều bài concurrency dùng chung SKU/DB khi parallel test nếu không có isolation.

**H2 không thay thế PostgreSQL/MySQL** về transaction isolation, lock semantics, collation, generated SQL và deadlock. H2 tốt cho test nhanh về version mapping; những thuộc tính transaction quan trọng của production cần được test trên DB cùng loại.

### Kiểm thử “exactly one succeeds”

Trong một race test nơi hai writer sửa cùng row từ version V, mục tiêu thường là:

- **Không có lost update:** không phải cả hai writer đều ghi thành công từ cùng version V.
- **Một kết quả hợp lệ được lưu:** đối chiếu final row và version.
- **Writer thua có tín hiệu lỗi dễ xử lý:** classify theo optimistic/serialization/timeout tùy thiết kế.
- **Không có trạng thái transaction bị kẹt** sau khi test kết thúc.

Nếu có yêu cầu thực sự “chính xác một writer thành công và một writer nhận optimistic exception”, phải kiểm soát isolation/commit order và môi trường DB thích hợp. Đừng yêu cầu mọi DB phát **cùng một exception class** cho race khi driver/provider khác nhau.

## 16. Retry: không phải xung đột nào cũng được tự động làm lại

Sau stale version, ứng dụng có thể:

1. **Trả 409 cho client:** người dùng xem khác biệt và quyết định cập nhật lại dựa trên dữ liệu mới.
2. **Đọc lại trong transaction mới, áp lại thao tác:** chỉ hợp lệ khi nghiệp vụ cho phép xử lý lại theo trạng thái mới.
3. **Merge có chủ đích:** kết hợp thay đổi trên các field độc lập, có domain rules để phát hiện cùng field bị sửa.
4. **Không tự retry:** khi hành động có side effect không idempotent như gửi tiền, đặt vé, xác nhận thanh toán hoặc phát thông báo không có khóa chống trùng.

Ví dụ “tăng thêm 1” khác hẳn “đặt quantity = 9”:

- Với **increment +1**, có thể đọc mới rồi áp một increment khác, nếu invariant và idempotency được bảo đảm.
- Với **set = 9**, retry mù quáng có thể đè lên cập nhật hợp lệ của người khác. API nên thông báo conflict để client làm mới hoặc xác nhận ghi đè.

Khi retry xảy ra **sau optimistic lock exception**, transaction bị lỗi phải được rollback. Mỗi lần retry phải có **transaction mới**, dữ liệu mới và giới hạn số lần thử. Đặt `@Retryable` trên method tự gọi nội bộ có thể không chạy qua proxy Spring; đảm bảo thiết kế AOP/transaction ordering thực sự đúng và test bằng một tình huống conflict có kiểm soát.

**Đừng coi việc tăng số lần retry là sửa được toàn bộ lỗi cạnh tranh.** Nếu domain yêu cầu serialize update hoặc không thể chịu xung đột ở khối thời gian cao, xem xét pessimistic lock, command queue, database atomic update, idempotency key hoặc thiết kế aggregate phù hợp.

## 17. Những sai lầm thường gặp

1. **Chỉ tạo hai biến Java trong một persistence context.** `a` và `b` có thể cùng tham chiếu một managed entity. **Sửa:** hai transaction/persistence contexts độc lập hoặc detached snapshots thực.
2. **Dựa vào rollback mặc định của `@DataJpaTest` để kiểm tra commit.** Rollback có thể che thời điểm flush/commit và dữ liệu liên transaction. **Sửa:** chọn transaction boundary rõ ràng.
3. **Gọi `save` rồi assert exception quá sớm.** SQL chưa chạy. **Sửa:** dùng `saveAndFlush`/`flush` hoặc assert sau commit.
4. **Tự tăng `version` trong Java.** Phá provider-managed semantics. **Sửa:** để JPA quản lý version.
5. **Assert version ban đầu bắt buộc là số 0.** Phụ thuộc provider/mapping. **Sửa:** lưu phiên bản thực rồi assert tăng.
6. **Chỉ assert exception mà không đọc lại DB.** Lỗi có thể xảy ra nhưng dữ liệu đã bị sửa sai ở một path khác. **Sửa:** kiểm tra final state sau rollback.
7. **Bắt mọi exception thành 409.** Che lỗi hạ tầng/lập trình. **Sửa:** bắt riêng version conflict và lỗi nghiệp vụ định nghĩa.
8. **Có `@Version` nhưng request không gửi expectedVersion.** Dữ liệu sửa từ UI cũ có thể được ghi lên version mới nếu service luôn load fresh. **Sửa:** mang version/ETag từ GET sang PUT.
9. **Chỉ so sánh expectedVersion thủ công mà bỏ `@Version`.** Hai transaction đồng thời có thể cùng pass comparison. **Sửa:** dùng JPA check hoặc SQL compare-and-update nguyên tử.
10. **Dùng JPQL bulk update không increment version.** Bỏ qua bảo vệ entity. **Sửa:** version predicate + update count hoặc dùng entity versioned path.
11. **Chạy race test với `Thread.sleep`.** Không bảo đảm thứ tự transaction. **Sửa:** barrier/latch, transaction riêng, timeout có kiểm soát.
12. **Dùng H2 để kết luận Postgres lock/isolation đã đúng.** DB semantics khác. **Sửa:** Testcontainers DB cùng loại nếu cần.
13. **Cố retry trong transaction đã thất bại.** Transaction có thể rollback-only. **Sửa:** rollback, đọc mới, transaction mới.
14. **Auto retry absolute write làm lost update theo ý định người dùng.** Thao tác không giao hoán. **Sửa:** 409 và cơ chế merge xác nhận.
15. **Không test stale delete.** `@Version` có thể bảo vệ xóa entity theo provider, nhưng các đường bulk delete có thể bỏ qua. **Sửa:** thêm test riêng nếu ứng dụng xóa bản ghi có phiên bản.
16. **Không phân biệt version conflict và unique constraint.** Hai lỗi có remediation khác. **Sửa:** map error code/HTTP theo nguồn lỗi.
17. **Để test HTTP chạy `@Transactional` phía client rồi nghĩ server tự rollback.** Sai transaction boundary. **Sửa:** seed/cleanup ngoài server request một cách chủ động.
18. **Đặt version vào response nhưng bỏ khỏi update request.** UI không có cách chứng minh mình sửa từ revision nào. **Sửa:** gửi expected version hoặc `If-Match`.
19. **Không kiểm tra cập nhật một entity không liên quan.** Dễ tưởng mọi update đang conflict toàn DB. **Sửa:** test independent rows.
20. **Không có migration cho cột version trong production.** Test schema auto-create xanh nhưng deploy thất bại. **Sửa:** Flyway/Liquibase và migration test riêng.

## 18. Checklist QA cho optimistic locking

Khi review một test hoặc pull request Spring Data JPA:

- [ ] Entity có `@Version` đúng kiểu được JPA provider hỗ trợ?
- [ ] Chưa có code tự gán/tăng version bằng tay?
- [ ] DB schema/migration có version column phù hợp?
- [ ] Test dương chứng minh update hợp lệ và version tăng?
- [ ] Hai snapshots trong test stale **thực sự độc lập**, không cùng identity map?
- [ ] Có flush/commit thật để phát hiện stale update đúng lúc?
- [ ] Test assert stale writer bị từ chối bằng exception family phù hợp?
- [ ] Test đọc lại DB bằng context mới và chứng minh dữ liệu của writer thắng được giữ?
- [ ] Test không phụ thuộc thứ tự method, cổng hoặc timing ngẫu nhiên?
- [ ] Nếu dùng `@DataJpaTest`, đã cân nhắc rollback mặc định và chủ động thiết kế transaction boundaries?
- [ ] Các HTTP edit command mang `expectedVersion` hoặc ETag/precondition khi cần chống overwrite do think time?
- [ ] Có test HTTP stale version → 409 hoặc 412 theo đúng hợp đồng?
- [ ] Có test client làm mới version → ghi tiếp thành công?
- [ ] Có test request thiếu version hoặc quantity không hợp lệ → 400?
- [ ] Các exception JPA, business và DB constraint không bị gom thành một lỗi mơ hồ?
- [ ] Các JPQL/native/batch writers có version predicate hoặc chiến lược đồng bộ riêng?
- [ ] Retry có giới hạn, transaction mới và bảo toàn idempotency/invariants?
- [ ] Test concurrency thật dùng DB production-like nếu nghiệp vụ phụ thuộc isolation/lock wait?
- [ ] Không dùng `@Transactional` ở test client để giả định rollback request HTTP server?
- [ ] Không kết luận optimistic locking đã bảo vệ toàn bộ aggregate hay nhiều bảng nếu chưa có protocol phối hợp?

### Lệnh chạy bộ test

Từ thư mục có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.jpaoptimistic.InventoryOptimisticLockingTest"
./gradlew test --tests "com.example.jpaoptimistic.InventoryHttpConflictTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.jpaoptimistic.InventoryOptimisticLockingTest"
.\gradlew.bat test --tests "com.example.jpaoptimistic.InventoryHttpConflictTest"
~~~

Bài có **5 `@DataJpaTest` methods và 4 `@SpringBootTest` HTTP methods**, tổng **9 ca JUnit**. Khi cấu hình Spring Boot 3.5, H2, transaction boundaries và dependencies đúng như mô tả, expected là các assertion PASS. **Đây là kết quả kỳ vọng sau khi đọc code, không phải một log test đã chạy trong lúc biên soạn**. Không có `System.out.println`, nên mã không có stdout xác định để chép lại; output Gradle/JUnit thay đổi theo môi trường.

**Tóm tắt cốt lõi:** `@Version` làm Hibernate phát hiện stale update ở **persistence boundary**, còn `expectedVersion`/`If-Match` giúp HTTP API biết client đang sửa từ **bản dữ liệu nào**. Test phải giữ hai snapshot độc lập, buộc flush/commit, assert conflict và **kiểm tra dữ liệu cuối**, rồi nâng lên real-DB concurrency test khi transaction race trong production là yêu cầu nghiệp vụ.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — @DataJpaTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Hibernate ORM — Locking và optimistic versioning](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#locking-optimistic)
- [Jakarta Persistence — @Version](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version)
- [Spring Framework — Transaction Management và Test Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Framework — OptimisticLockingFailureException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/OptimisticLockingFailureException.html)
- [HTTP Semantics — 409 Conflict và 412 Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.10)