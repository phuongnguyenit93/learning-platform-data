# Khóa do ứng dụng gán và cách Spring Data nhận diện Entity mới

## Mục tiêu

Trong JPA, khóa chính của entity có thể do database/provider sinh hoặc do ứng dụng cung cấp. Khi ứng dụng tự gán ID, Spring Data JPA cần xác định object đang lưu là entity mới hay entity đã tồn tại để chọn cách gọi JPA phù hợp.

Bài này giải thích:

- Khác biệt giữa ID do database sinh và ID do ứng dụng gán.
- Cách Spring Data JPA xác định một entity là mới.
- Vì sao ID khác null có thể khiến entity mới bị xem là entity cũ.
- Cách dùng thuộc tính `@Version` hoặc interface `Persistable` để điều khiển nhận diện.
- Ảnh hưởng của `persist`, `merge`, transaction và optimistic locking.
- Cách kiểm thử, xử lý lỗi trùng khóa và lựa chọn chiến lược phù hợp.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Khóa chính và cách cấp ID

Mỗi entity JPA cần một định danh được đánh dấu bằng `@Id`. ID dùng để nhận diện duy nhất một bản ghi entity trong persistence context và database.

Có hai cách cấp ID thường gặp.

### 1.1. ID do database hoặc JPA provider sinh

Ứng dụng để provider/database sinh ID. Ví dụ với khóa số tự tăng:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }
}
```

Khi tạo object mới, `id` thường có giá trị null. Sau khi persist/flush, database cấp ID và JPA cập nhật giá trị vào entity.

Với kiểu này, Spring Data JPA có thể dùng trạng thái ID null để nhận diện entity mới khi entity không có chiến lược khác ưu tiên hơn.

JPA cũng hỗ trợ các chiến lược như `SEQUENCE` hoặc `TABLE`. Chiến lược cụ thể phụ thuộc database và provider. Annotation `@GeneratedValue` cho biết ID được tạo theo chiến lược provider/database; ứng dụng không tự gán giá trị ID trong luồng thông thường.

### 1.2. ID do ứng dụng gán

Có trường hợp ứng dụng đã có ID trước khi lưu:

- ID UUID được sinh trong ứng dụng.
- Mã đơn hàng hoặc mã khách hàng được cấp bởi hệ thống khác.
- ID đồng bộ từ dịch vụ bên ngoài.
- Khóa tự nhiên đã được xác định trước khi ghi database.

Ví dụ:

```java
@Entity
@Table(name = "external_orders")
public class ExternalOrder {

    @Id
    @Column(nullable = false, updatable = false)
    private UUID id;

    @Column(nullable = false)
    private String status;

    protected ExternalOrder() {
    }

    public ExternalOrder(UUID id, String status) {
        this.id = Objects.requireNonNull(id);
        this.status = status;
    }

    public UUID getId() {
        return id;
    }
}
```

ID đã khác null ngay từ khi tạo object. Đây là điểm khác biệt quan trọng: Spring Data không thể chỉ dựa vào việc ID có giá trị để kết luận object đã được lưu trước đó.

Nếu entity dùng ID do ứng dụng gán và không khai báo chiến lược nhận diện trạng thái new khác, Spring Data JPA mặc định có thể phân loại object là entity cũ. Phần tiếp theo giải thích hệ quả.

Không nên thêm `@GeneratedValue` cho một ID mà ứng dụng đang chủ động gán theo cách thông thường. Hãy chọn một nguồn cấp ID nhất quán và thể hiện đúng trong mapping.

## 2. Spring Data JPA xác định entity mới như thế nào?

Khi gọi `repository.save(entity)`, Spring Data JPA phải quyết định nên gọi `EntityManager.persist` hay `EntityManager.merge`. Quyết định này dựa trên thông tin entity, không phải phép kiểm tra trực tiếp rằng “database có hàng mang ID này hay chưa” ở mọi trường hợp.

Với chiến lược mặc định, Spring Data JPA dùng thứ tự nhận diện sau:

1. Nếu entity triển khai `Persistable`, Spring Data gọi `isNew()` trên entity và dùng kết quả đó.
2. Nếu entity không triển khai `Persistable` nhưng có thuộc tính `@Version` không phải kiểu primitive, Spring Data kiểm tra version. Version null có nghĩa entity mới; version khác null có nghĩa entity đã tồn tại.
3. Nếu không áp dụng được hai trường hợp trên, Spring Data kiểm tra ID. ID null nghĩa entity mới; ID khác null nghĩa entity đã tồn tại.

Có thể hình dung:

| Entity | Quy tắc nhận diện mặc định |
|---|---|
| ID null, không có version | New |
| ID khác null, không có version | Existing |
| Có @Version kiểu wrapper, version null | New |
| Có @Version kiểu wrapper, version khác null | Existing |
| Triển khai Persistable | Dùng kết quả isNew() |

Thứ tự này rất quan trọng. Nếu entity triển khai `Persistable`, kết quả `isNew()` được dùng thay cho cách suy luận từ version/ID. Nếu không triển khai `Persistable`, một thuộc tính version dạng wrapper có thể được kiểm tra trước ID.

### Vì sao ID được gán sẵn gây vấn đề?

Ví dụ:

```java
@Entity
public class ExternalOrder {

    @Id
    private UUID id;

    private String status;

    protected ExternalOrder() {
    }

    public ExternalOrder(UUID id, String status) {
        this.id = id;
        this.status = status;
    }
}
```

Khi tạo object:

```java
ExternalOrder order = new ExternalOrder(
        UUID.randomUUID(),
        "NEW"
);

repository.save(order);
```

ID đã có giá trị. Nếu entity không có thuộc tính version phù hợp và không triển khai `Persistable`, chiến lược mặc định phân loại object là existing. Spring Data JPA chọn `merge` thay vì `persist`.

Điều này không có nghĩa `merge` luôn tạo ra câu UPDATE. Theo JPA, merge sao chép trạng thái của object đầu vào vào một instance managed; provider xác định trạng thái thực tế và có thể thực hiện INSERT nếu entity chưa tồn tại. Tuy nhiên, đường đi qua merge có thể cần kiểm tra trạng thái hoặc đọc dữ liệu bổ sung và không diễn đạt rõ ý định “đây chắc chắn là entity mới”.

Nếu ứng dụng cần phân biệt rõ entity mới với entity đã lưu, hãy cung cấp một tín hiệu newness phù hợp.

## 3. persist và merge khác nhau ra sao?

Đây là hai thao tác JPA quan trọng mà Spring Data JPA lựa chọn khi lưu entity.

### 3.1. EntityManager.persist

`persist(entity)` đưa một entity mới vào persistence context. Entity trở thành managed và được lên lịch INSERT khi flush/commit.

- Dùng cho entity mới.
- ID có thể đã được ứng dụng gán trước khi gọi persist.
- Nếu database đã có bản ghi trùng khóa chính, thao tác ghi sẽ thất bại do vi phạm tính duy nhất của primary key.
- Phương thức không trả về một entity khác; object truyền vào trở thành managed.

### 3.2. EntityManager.merge

`merge(entity)` sao chép trạng thái của object đầu vào vào một instance managed và trả về instance managed đó.

- Thường dùng cho entity detached hoặc entity mà Spring Data nhận diện là existing.
- Object đầu vào không nhất thiết trở thành managed.
- Phải sử dụng object được trả về từ `merge` hoặc `repository.save` nếu cần tiếp tục làm việc với instance managed.
- Provider có thể cần truy vấn database để xác định trạng thái entity và quyết định thao tác ghi.

Ví dụ:

```java
ExternalOrder detached = loadOrderOutsideCurrentContext();

ExternalOrder managed = entityManager.merge(detached);

// Tiếp tục dùng managed trong persistence context hiện tại.
managed.setStatus("CONFIRMED");
```

Với Spring Data JPA:

```java
ExternalOrder saved = repository.save(order);
```

Hãy dùng `saved` nếu cần tiếp tục thay đổi entity sau `save`, vì trong trường hợp merge, instance trả về có thể khác instance đầu vào.

### 3.3. save không đồng nghĩa với upsert nguyên tử

`repository.save(entity)` là API lưu entity của Spring Data. Không nên hiểu nó là một lệnh database upsert nguyên tử, nghĩa là “nếu chưa có thì insert, nếu có thì update” được bảo đảm an toàn trước mọi truy cập đồng thời.

`save` chọn persist/merge theo chiến lược nhận diện entity. Còn tính nguyên tử, xung đột đồng thời và quy tắc ghi đè phụ thuộc transaction, provider và database.

Nếu cần thao tác upsert theo khóa nghiệp vụ dưới tải đồng thời, hãy thiết kế rõ:

- Unique constraint trên khóa nghiệp vụ.
- Cách xử lý xung đột khi hai transaction cùng tạo một khóa.
- Transaction và chính sách retry phù hợp.
- Native database upsert như PostgreSQL `INSERT ... ON CONFLICT` nếu nghiệp vụ thực sự cần hành vi đó và chấp nhận phụ thuộc database.

## 4. Cách 1: Dùng thuộc tính @Version để nhận diện entity mới

JPA hỗ trợ optimistic locking bằng `@Version`. Khi entity có thuộc tính version không phải kiểu primitive, Spring Data JPA có thể dùng giá trị null của version để nhận diện entity mới.

Đây thường là lựa chọn gọn nếu entity vốn cần optimistic locking.

Ví dụ entity dùng UUID do ứng dụng gán:

```java
package com.example.demo.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.util.UUID;

@Entity
@Table(name = "external_orders")
public class ExternalOrder {

    @Id
    @Column(nullable = false, updatable = false)
    private UUID id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String status;

    protected ExternalOrder() {
    }

    public ExternalOrder(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Repository:

```java
package com.example.demo.order;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExternalOrderRepository
        extends JpaRepository<ExternalOrder, UUID> {
}
```

Service tạo entity mới:

```java
@Service
public class ExternalOrderService {

    private final ExternalOrderRepository repository;

    public ExternalOrderService(ExternalOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ExternalOrder create(UUID externalId) {
        ExternalOrder order =
                new ExternalOrder(externalId, "NEW");

        return repository.save(order);
    }
}
```

Khi object mới được tạo:

- ID đã có giá trị UUID.
- Version ban đầu là null.
- Spring Data JPA thấy thuộc tính version kiểu `Long` đang null.
- Entity được nhận diện là new và Spring Data chọn persist.
- JPA/provider quản lý version khi lưu và cập nhật version theo cơ chế optimistic locking.

Khi entity được nạp từ database, version đã có giá trị. Spring Data nhận diện entity là existing và chọn merge nếu gọi `save` trên instance đó.

### Tại sao phải dùng Long thay vì long?

`Long` là kiểu wrapper và có thể mang giá trị null. `long` là kiểu primitive, luôn có giá trị số mặc định là 0.

Spring Data JPA chỉ dùng version làm tín hiệu newness khi thuộc tính version không phải kiểu primitive. Nếu dùng:

```java
@Version
private long version;
```

thì không thể dùng null để biểu thị entity mới. Khi đó chiến lược mặc định sẽ quay về kiểm tra ID. Với ID ứng dụng gán và khác null, entity có thể lại bị nhận diện là existing.

Hãy để JPA provider quản lý version. Không tự đặt version tùy tiện trong service hoặc request. Version phục vụ optimistic locking, giúp phát hiện hai transaction cùng cập nhật một phiên bản dữ liệu.

### Khi nào nên chọn @Version?

Dùng thuộc tính version nếu entity cần optimistic locking hoặc ứng dụng muốn dùng tín hiệu version null/non-null theo cơ chế mặc định của Spring Data JPA.

Không nên thêm `@Version` chỉ như một cờ giả nếu ứng dụng không hiểu và không muốn sử dụng optimistic locking. Version là một phần của mapping persistence và ảnh hưởng tới câu lệnh UPDATE/DELETE cũng như phát hiện xung đột cập nhật.

## 5. Cách 2: Triển khai Persistable

Nếu entity không cần optimistic locking nhưng ID được ứng dụng gán, có thể triển khai `org.springframework.data.domain.Persistable<ID>`.

Interface này cung cấp hai phương thức:

```java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
```

Spring Data JPA kiểm tra `isNew()` để quyết định entity có phải mới hay không. Ta có thể duy trì một cờ trạng thái transient trong entity.

Ví dụ:

```java
package com.example.demo.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import org.springframework.data.domain.Persistable;

import java.util.UUID;

@Entity
@Table(name = "external_orders")
public class ExternalOrder implements Persistable<UUID> {

    @Id
    @Column(nullable = false, updatable = false)
    private UUID id;

    @Column(nullable = false)
    private String status;

    @Transient
    private boolean newEntity = true;

    protected ExternalOrder() {
    }

    public ExternalOrder(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
```

Ý nghĩa của từng thành phần:

- `implements Persistable<UUID>`: entity tự cung cấp định danh và trạng thái new.
- `@Transient`: cờ `newEntity` không được lưu thành cột database.
- `newEntity = true`: object vừa được tạo trong ứng dụng được xem là entity mới.
- `@PostPersist`: sau khi entity được persist, callback đặt cờ về false.
- `@PostLoad`: khi entity được tải từ database, callback đặt cờ về false.
- `isNew()`: trả trạng thái mà Spring Data dùng để chọn persist hoặc merge.

Khi gọi:

```java
ExternalOrder order =
        new ExternalOrder(UUID.randomUUID(), "NEW");

ExternalOrder saved = repository.save(order);
```

Spring Data gọi `isNew()`. Giá trị true khiến nó chọn `persist`. Sau khi JPA persist entity, callback `@PostPersist` đánh dấu object là không còn mới.

Khi repository tải entity từ database, `@PostLoad` cũng đánh dấu object là existing. Nếu gọi `save` trên entity đã tải, `isNew()` trả false và Spring Data chọn merge.

### Cẩn thận với object được dựng lại từ request

Chiến lược cờ transient giả định object mới được tạo bởi luồng tạo entity và object existing được tải từ database. Nếu nhận một ID đã tồn tại từ request rồi tạo object mới với constructor đặt cờ `newEntity = true`, `save` sẽ chọn persist. Database có thể từ chối do trùng primary key.

Với thao tác cập nhật, nên:

1. Tải entity hiện có bằng repository.
2. Kiểm tra quyền và điều kiện nghiệp vụ.
3. Thay đổi các thuộc tính cho phép.
4. Để transaction commit đồng bộ thay đổi.

Không nhận trực tiếp entity JPA do client gửi lên rồi tin vào cờ trạng thái của object.

### Cẩn thận khi transaction rollback

Callback `@PostPersist` có thể chạy khi persistence context flush, trước khi transaction thực sự commit. Nếu transaction sau đó rollback, object trong bộ nhớ vẫn có thể đã đổi cờ `newEntity` thành false mặc dù hàng chưa được commit vào database.

Vì vậy, không nên tái sử dụng instance đó như một entity mới sau rollback. Hãy tạo object mới hoặc tải lại trạng thái từ database trong transaction mới. Cờ transient chỉ là tín hiệu cho chiến lược nhận diện của repository, không thay thế trạng thái transaction của database.

### Khi nào nên chọn Persistable?

Dùng `Persistable` khi ID do ứng dụng gán và không có thuộc tính version phù hợp, hoặc khi quy tắc nhận diện new/existing cần được kiểm soát rõ ràng. Đây là cách linh hoạt, nhưng trách nhiệm duy trì cờ trạng thái thuộc về entity và cần được kiểm thử.

## 6. So sánh các chiến lược nhận diện

| Chiến lược | Điều kiện entity mới | Ưu điểm | Lưu ý |
|---|---|---|---|
| ID null | ID chưa có giá trị | Đơn giản, hợp với ID được sinh khi persist | Không phù hợp với ID ứng dụng gán sẵn |
| Wrapper @Version | Version null | Tận dụng cơ chế optimistic locking | Version phải do provider quản lý |
| Persistable.isNew() | Theo cờ/logic do entity cung cấp | Kiểm soát chính xác với ID gán sẵn | Phải duy trì trạng thái đúng qua lifecycle |
| Custom EntityInformation | Theo implementation tùy chỉnh | Linh hoạt cho quy tắc đặc biệt | Phức tạp, thường không cần thiết |

### Cách chọn thực tế

- ID database/provider sinh và để null trước khi lưu: dùng chiến lược mặc định.
- ID UUID hoặc ID ngoài được ứng dụng gán, đồng thời entity cần optimistic locking: dùng thuộc tính `@Version` dạng wrapper như `Long`.
- ID được ứng dụng gán, không cần optimistic locking và muốn kiểm soát trạng thái rõ ràng: triển khai `Persistable`.
- Quy tắc nhận diện rất đặc thù trên toàn bộ repository factory: chỉ cân nhắc custom `EntityInformation` khi các cách trên không đáp ứng.

Đừng chọn `Persistable` và `@Version` cùng lúc chỉ để “chắc chắn”. Khi entity triển khai `Persistable`, `isNew()` là tín hiệu được dùng. Hãy có một chiến lược rõ ràng và một nguồn sự thật cho trạng thái new.

## 7. Ví dụ kiểm thử với ID ứng dụng gán

Ví dụ sau dùng entity triển khai `Persistable<UUID>` ở mục 5. Test kiểm tra object có ID sẵn được lưu và đọc lại thành công.

```java
package com.example.demo.order;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ExternalOrderRepositoryTest {

    @Autowired
    private ExternalOrderRepository repository;

    @Test
    void savesAndLoadsOrderWithApplicationAssignedId() {
        UUID id = UUID.fromString(
                "d9428888-122b-11e1-b85c-61cd3cbb3210"
        );

        ExternalOrder order = new ExternalOrder(id, "NEW");

        ExternalOrder saved = repository.save(order);

        assertThat(saved.getId()).isEqualTo(id);
        assertThat(saved.isNew()).isFalse();

        repository.flush();

        ExternalOrder loaded = repository.findById(id).orElseThrow();

        assertThat(loaded.getId()).isEqualTo(id);
        assertThat(loaded.getStatus()).isEqualTo("NEW");
        assertThat(loaded.isNew()).isFalse();
    }
}
```

Test cần các import AssertJ/JUnit/Spring Boot test và cấu hình JPA phù hợp. `@DataJpaTest` thường chạy test trong transaction và rollback sau khi test kết thúc. Đối với entity triển khai `Persistable`, callback lifecycle phải hoạt động như dự kiến trên provider đang dùng.

Nếu dùng chiến lược `@Version`, hãy kiểm thử thêm:

- Entity mới có ID đã gán và version null được insert.
- Entity được load có version khác null.
- Hai transaction cập nhật cùng một version sẽ phát hiện xung đột optimistic locking.
- Client không thể tự ghi đè version để né kiểm tra concurrency.

Để xác nhận SQL thực tế hoặc hành vi riêng của PostgreSQL, hãy chạy integration test với đúng database đích. Embedded database có thể khác về kiểu dữ liệu, constraint và cú pháp SQL.

## 8. Những lỗi thường gặp

### Entity mới có ID khác null bị xử lý như existing

Nguyên nhân: entity không có version wrapper null và không triển khai `Persistable`. Spring Data mặc định kiểm tra ID, thấy ID khác null nên chọn merge.

Cách xử lý: thêm `@Version` kiểu wrapper nếu phù hợp, hoặc triển khai `Persistable` với cờ trạng thái được quản lý bằng lifecycle callback.

### Entity mới bị insert trùng ID

Nguyên nhân: `Persistable.isNew()` trả true cho một object có ID đã tồn tại trong database. Spring Data chọn persist và database từ chối primary key trùng.

Cách xử lý: không tạo object mới với ID existing để cập nhật. Hãy tải entity rồi sửa; nếu có chiến lược `Persistable`, đảm bảo cờ newness phản ánh đúng vòng đời.

### Entity existing bị merge như entity mới

Nguyên nhân: `isNew()` trả true cho object đã tồn tại, hoặc cờ transient không được cập nhật khi load.

Cách xử lý: kiểm tra `@PostLoad`, `@PostPersist` và mọi constructor/factory. Đảm bảo object existing được tải từ JPA hoặc được đánh dấu trạng thái phù hợp.

### @Version không giúp nhận diện

Nguyên nhân thường gặp:

- Dùng kiểu primitive `long` thay vì wrapper `Long`.
- Version được gán giá trị khác null trước lần lưu đầu tiên.
- Entity triển khai `Persistable` và `isNew()` đang được ưu tiên.
- Mapping version không được JPA nhận diện đúng.

Cách xử lý: kiểm tra mapping, để provider quản lý version và xác nhận chiến lược nhận diện thực tế.

### save không trả về cùng instance đầu vào

Nguyên nhân: `save` có thể gọi merge; merge trả về instance managed.

Cách xử lý: luôn dùng object trả về từ `save` nếu tiếp tục thao tác trên entity.

### Nghĩ rằng save là upsert an toàn

Nguyên nhân: nhầm chiến lược persist/merge với lệnh upsert nguyên tử của database.

Cách xử lý: thiết kế unique constraint, transaction và xử lý xung đột đồng thời. Nếu cần upsert theo semantics riêng của database, dùng câu lệnh phù hợp và kiểm thử concurrency.

### Cờ Persistable sai sau rollback

Nguyên nhân: `@PostPersist` đã chạy khi flush nhưng transaction bị rollback sau đó.

Cách xử lý: không tái sử dụng instance sau rollback; tạo object mới hoặc đọc lại từ database trong transaction mới.

## 9. Lưu ý về UUID và khóa nghiệp vụ

UUID là lựa chọn phổ biến cho ID do ứng dụng gán vì có thể tạo trước khi ghi database và thuận tiện khi nhiều hệ thống tạo dữ liệu độc lập. Ví dụ:

```java
UUID orderId = UUID.randomUUID();
ExternalOrder order = new ExternalOrder(orderId, "NEW");
```

Không có `@GeneratedValue` trong mapping trên vì ứng dụng chịu trách nhiệm cung cấp UUID.

JPA 3.1 cũng có `GenerationType.UUID` để provider tạo UUID. Đó là ID do persistence provider sinh, khác với việc ứng dụng tự gọi `UUID.randomUUID()` và gán vào entity trước khi lưu.

Nếu dùng khóa nghiệp vụ làm primary key, hãy cân nhắc tính ổn định và khả năng thay đổi. Khóa chính nên bất biến trong suốt vòng đời entity. Nếu giá trị nghiệp vụ có thể thay đổi, thường nên dùng surrogate key làm primary key và đặt unique constraint trên khóa nghiệp vụ.

## 10. Checklist trước khi đưa vào production

- [ ] Xác định rõ ID được sinh bởi database/provider hay do ứng dụng gán.
- [ ] Không kết hợp tùy tiện ID ứng dụng gán với `@GeneratedValue`.
- [ ] Hiểu chiến lược `isNew` của Spring Data JPA.
- [ ] Với ID gán sẵn, chọn version wrapper hoặc `Persistable` khi cần.
- [ ] Không tự gán version để điều khiển insert/update.
- [ ] Không nhận entity từ client rồi tin cờ trạng thái newness.
- [ ] Dùng instance trả về từ `save`.
- [ ] Dùng unique constraint để bảo vệ ID/khóa nghiệp vụ.
- [ ] Kiểm thử insert lần đầu, load lại, update và xung đột khóa.
- [ ] Kiểm thử optimistic locking nếu entity có `@Version`.
- [ ] Không tái sử dụng entity instance sau khi transaction rollback nếu lifecycle flag đã thay đổi.

## Kết luận

Với ID do ứng dụng gán, ID thường đã khác null ngay khi tạo entity. Spring Data JPA mặc định có thể xem entity là existing và chọn `merge`. Cơ chế nhận diện newness cần được hiểu rõ để tránh đường đi lưu dữ liệu không mong muốn.

Có hai giải pháp phổ biến: dùng thuộc tính `@Version` kiểu wrapper nếu entity cần optimistic locking, hoặc triển khai `Persistable` để tự cung cấp `isNew()`. Chọn một chiến lược nhất quán, kiểm thử lifecycle và để database bảo vệ tính duy nhất. Nhờ vậy, thao tác lưu entity có ID ứng dụng gán sẽ rõ ràng, an toàn và dễ bảo trì.
