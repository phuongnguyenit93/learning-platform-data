# Nhận diện Entity mới qua `@Version`, `@Id` và `Persistable` trong Spring Data JPA

Khi gọi `JpaRepository.save(entity)`, Spring Data JPA phải quyết định entity được xem là **mới** hay **đã tồn tại** để chọn thao tác với JPA `EntityManager`. Quyết định này dựa trên trạng thái entity mà repository suy ra từ metadata và giá trị thuộc tính; nó **không phải** một truy vấn bảo đảm bản ghi đã có hay chưa trong cơ sở dữ liệu.

Sau bài này, bạn có thể giải thích thứ tự ưu tiên `Persistable` → version dạng đối tượng → ID, dự đoán nhánh `persist`/`merge` trong các trường hợp phổ biến và xử lý đúng entity dùng ID tự gán.

## 1. `save()` dùng kết quả nhận diện mới như thế nào?

Ý tưởng cốt lõi của `SimpleJpaRepository.save(...)` có thể viết gọn như sau (mã mô tả cơ chế bên trong Spring Data JPA, không phải một chương trình chạy độc lập):

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}
return entityManager.merge(entity);
```

- **`isNew(entity) == true`**: repository gọi `persist`. Đối tượng được đưa vào persistence context để INSERT theo quy tắc JPA; thời điểm phát SQL có thể phụ thuộc chiến lược sinh ID và `flush`.
- **`isNew(entity) == false`**: repository gọi `merge`. JPA sao chép trạng thái sang một đối tượng managed và trả về đối tượng managed đó (có thể khác instance đầu vào). Vì vậy, hãy sử dụng giá trị `save(...)` trả về.
- `saveAndFlush(...)` vẫn dùng cách nhận diện như `save(...)`, sau đó yêu cầu `flush`. `saveAll(...)` lần lượt áp dụng `save` cho từng entity.

`isNew` là tín hiệu để chọn API JPA, không đồng nghĩa với `entityManager.contains(entity)` và không phải phép kiểm tra tồn tại trong database. Entity có ID nhưng chưa được INSERT vẫn có thể bị suy ra là “đã tồn tại”; ngược lại, một ID được đánh dấu “mới” vẫn có thể trùng khóa chính của hàng đang có.

## 2. Quy tắc chọn chiến lược nhận diện

Trong **Spring Data JPA**, thứ tự áp dụng thực tế là:

1. **Entity triển khai `org.springframework.data.domain.Persistable<ID>`**: sử dụng chính kết quả `entity.isNew()`. Lập trình viên chịu trách nhiệm duy trì trạng thái mới/cũ.
2. **Không triển khai `Persistable` và có thuộc tính `@jakarta.persistence.Version` thuộc kiểu tham chiếu** như `Long`, `Integer`: `version == null` → mới; `version != null` → không mới. **Kết quả này được ưu tiên hơn giá trị ID.**
3. **Không có version kiểu tham chiếu thích hợp**: xét `@Id`. ID `null` → mới, ID khác `null` → không mới. Với ID kiểu số nguyên thủy (primitive), giá trị `0` được coi là mới theo cơ chế kiểm tra ID cơ bản.

Điểm dễ nhầm: **`@Version long` hoặc `@Version int` (kiểu primitive) không được Spring Data JPA dùng để nhận diện mới.** JPA cho phép phiên bản đầu tiên có giá trị `0`; vì thế `version == 0` chưa đủ để kết luận entity mới. Khi version là primitive, Spring Data JPA quay về xét ID. Tài liệu chung của Spring Data Commons mô tả nhận diện version primitive ở một số module khác; với bài toán `JpaRepository`, hãy theo quy tắc riêng của **Spring Data JPA**.

Bảng quyết định (giả sử entity không triển khai `Persistable`, trừ dòng cuối):

| Tình huống | ID | `@Version` | `isNew` | Nhánh `save` |
|---|---|---|---|---|
| ID sinh tự động, chưa lưu, không có version | `null` | Không có | `true` | `persist` |
| ID tự gán, chưa lưu, không có version | `"BK-01"` | Không có | `false` | `merge` |
| ID tự gán, version kiểu `Long` chưa được thiết lập | `"BK-01"` | `null` | `true` | `persist` |
| Entity đã có version kiểu `Long` | `"BK-01"` | `0L` hoặc `1L` | `false` | `merge` |
| ID tự gán, version kiểu `long` bằng 0 | `"BK-01"` | `0` (primitive) | `false` | `merge` (xét ID) |
| ID kiểu `Long` được đặt thành `0L`, không có version | `0L` | Không có | `false` | `merge` (vẫn khác `null`) |
| Có `Persistable.isNew()` trả về `true` | `"BK-01"` | Bất kỳ | `true` | `persist` |

Ở đây, “không mới” chỉ là **kết luận của Spring Data JPA**, không khẳng định hàng tương ứng thực sự tồn tại. Provider JPA có thể cần SELECT, phát UPDATE/INSERT hoặc ném lỗi tùy trạng thái dữ liệu, version và ngữ cảnh giao dịch.

## 3. Nhận diện qua ID: đơn giản khi ID được sinh tự động

Ví dụ JPA với ID do cơ sở dữ liệu sinh (đoạn dưới thuộc một dự án Spring Boot 3+/Java 17+ có Spring Data JPA, không chạy riêng bằng lệnh `javac` thiếu dependency):

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {} // JPA cần constructor không tham số

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

`new Customer("An")` có `id == null` nên mặc định được nhận diện là mới và `save` gọi `persist`. Sau khi ID được cấp, nếu không có version kiểu tham chiếu, entity có ID khác `null` được nhận diện là không mới. ID kiểu wrapper (`Long`) biểu diễn trạng thái chưa gán rõ ràng hơn `long`, vốn mặc định bằng `0`.

**Ca đặc biệt – ID tự gán:** với `@Id private String code;` và giá trị `code = "BK-01"` được đặt ngay khi tạo object, kiểm tra ID mặc định cho `isNew == false` dù bản ghi chưa được lưu lần nào. Vì thế `save` đi vào `merge`. Đừng đồng nhất “đã có ID” với “đã có hàng trong database”.

## 4. Nhận diện qua `@Version` dạng wrapper

`@Version` là metadata JPA dùng cho **optimistic locking**: provider duy trì số phiên bản để phát hiện cập nhật xung đột. Trong Spring Data JPA, version dạng đối tượng còn giúp phân biệt entity mới khi ID đã được gán từ trước.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {
    @Id
    private String sku; // ID do ứng dụng tự gán

    @Version
    private Long version; // null khi tạo mới

    private String name;

    protected Product() {}

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public String getSku() {
        return sku;
    }

    public Long getVersion() {
        return version;
    }
}
```

Diễn tiến:

1. `new Product("SKU-01", "Bàn phím")` có `sku != null` nhưng `version == null`. Spring Data JPA **ưu tiên version**, nhận diện **mới** và gọi `persist`.
2. Khi entity được lưu thành công, JPA provider quản lý version. Sau khi có giá trị version khác `null`, lần nhận diện tiếp theo cho kết quả **không mới**.
3. Entity được tải từ database thông thường có version đã được khởi tạo và được xem là **không mới**.

Hãy dùng `Long` (hoặc wrapper phù hợp), tránh thay bằng `long` nếu bạn cần chiến lược này. **Không tự đặt `version = 0L` cho object mới**: `0L` khác `null`, do đó có thể khiến repository chọn `merge`. Version nên do JPA quản lý; version cũ khi cập nhật cũng có thể gây lỗi optimistic locking lúc flush/commit.

Nếu entity không có version kiểu tham chiếu, hoặc version là primitive, Spring Data JPA dùng quy tắc ID ở mục 3.

## 5. `Persistable<ID>`: tự định nghĩa entity có mới hay không

`Persistable` đặc biệt hữu ích cho **ID tự gán, không có `@Version`**. Ta lưu một cờ **không ánh xạ xuống database**, khởi tạo `true` cho entity mới và chuyển thành `false` sau khi insert hoặc sau khi JPA tải entity lên.

Ví dụ hoàn chỉnh về lớp entity (file `CatalogEntry.java`, đặt trong package ứng dụng của bạn):

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import org.springframework.data.domain.Persistable;

import java.util.Objects;

@Entity
@Table(name = "catalog_entries")
public class CatalogEntry implements Persistable<String> {
    @Id
    private String code;

    private String displayName;

    @Transient
    private boolean newEntity = true;

    protected CatalogEntry() {} // Dành cho JPA

    public CatalogEntry(String code, String displayName) {
        this.code = Objects.requireNonNull(code, "code");
        this.displayName = Objects.requireNonNull(displayName, "displayName");
    }

    @Override
    public String getId() {
        return code;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
```

Repository (file `CatalogEntryRepository.java`, cùng package):

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogEntryRepository
        extends JpaRepository<CatalogEntry, String> {
}
```

Ý nghĩa của từng phần:

- `getId()` cung cấp identifier cho `Persistable<String>`; `isNew()` là tín hiệu Spring Data JPA tin tưởng, **ưu tiên hơn cả ID lẫn version**.
- `newEntity = true` áp dụng cho object do mã ứng dụng vừa tạo; vì vậy `new CatalogEntry("BK-01", "Java")` có ID khác `null` vẫn đi vào `persist`.
- `@jakarta.persistence.Transient` ngăn cờ `newEntity` trở thành cột lưu trữ. Với JPA property access, cũng cần bảo đảm `isNew` không vô tình bị ánh xạ thành thuộc tính persistent.
- `@PostPersist` đặt cờ thành `false` **sau khi được persist thực sự**; `@PostLoad` đặt cờ thành `false` khi JPA tạo entity từ dữ liệu đã lưu. Nếu gọi `save` mà INSERT chưa flush, callback `@PostPersist` có thể chưa xảy ra ngay.
- `Persistable` không tự kiểm tra database. Nếu đặt `isNew() == true` cho một khóa đã tồn tại, `persist` có thể dẫn tới xung đột khóa chính hoặc lỗi trạng thái entity.

Mẫu này dựa trên các lifecycle callback JPA chính thức; có thể đưa cờ và callback vào một `@MappedSuperclass` dùng chung nếu nhiều entity có ID tự gán.

### Một integration test cho cờ trạng thái

Test sau giả sử có `spring-boot-starter-data-jpa`, `spring-boot-starter-test`, database kiểm thử (ví dụ H2) và các lớp đặt đúng package được Spring Boot quét. Đây là test trong dự án, không phải Java thuần chạy bằng `java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class CatalogEntryRepositoryTest {
    @Autowired
    CatalogEntryRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void assignedIdIsNewUntilPersisted() {
        CatalogEntry candidate =
                new CatalogEntry("BK-01", "Java thực hành");

        assertTrue(candidate.isNew());

        CatalogEntry saved = repository.saveAndFlush(candidate);
        assertFalse(saved.isNew()); // @PostPersist đã chạy

        entityManager.clear(); // Bắt buộc tải lại từ database
        CatalogEntry loaded =
                repository.findById("BK-01").orElseThrow();

        assertFalse(loaded.isNew()); // @PostLoad đã chạy
    }
}
```

Kết quả mong đợi: cả ba assertion đều thành công. `clear()` buộc lần `findById` sau đi qua quá trình load, nhờ đó kiểm tra cả callback `@PostLoad`.

## 6. So sánh lựa chọn trong dự án thực tế

| Kiểu định danh/entity | Cách nhận diện khuyến nghị | Vì sao |
|---|---|---|
| ID sinh tự động (`@GeneratedValue`), không cần version | Kiểm tra `@Id` mặc định với kiểu wrapper | Object mới thường có ID `null` |
| Entity có optimistic locking | `@Version Long`/wrapper | `null` biểu diễn mới và JPA quản lý phiên bản |
| ID tự gán, không có version | `Persistable<ID>` với cờ transient và callback | ID khác `null` trước khi INSERT |
| ID tự gán, có version wrapper | Thường dùng `@Version` mặc định | Version `null` đủ báo entity mới |
| Quy tắc không phù hợp ba cách trên | Tùy biến `EntityInformation`/`JpaRepositoryFactory` | Tình huống nâng cao, ít cần và phải kiểm thử kỹ |

Không triển khai `Persistable` chỉ để ép mọi lời gọi `save` thành INSERT. Hãy dùng nó khi **vòng đời entity cho phép bạn xác định đúng trạng thái mới**, và nhớ đồng bộ cờ khi đọc entity.

## 7. Những lỗi phổ biến và cách tự kiểm tra

1. **Tưởng `save` luôn có nghĩa INSERT hoặc UPDATE dựa trên việc database đã có khóa.** Thực tế, Spring Data JPA chọn `persist`/`merge` từ `isNew` trước; hãy lần theo chiến lược nhận diện thay vì suy ra từ tên method.
2. **Gán ID thủ công rồi ngạc nhiên vì `merge` hoặc SELECT phát sinh.** Với ID khác `null` mà không có version wrapper/Persistable, đó là hành vi mặc định. Cân nhắc `@Version Long` hoặc mẫu `Persistable` nếu semantics phù hợp.
3. **Dùng `@Version long` rồi coi `0` là “mới”.** Trong Spring Data **JPA**, primitive version không được dùng để nhận diện mới; hãy chuyển sang `Long` nếu cần dấu hiệu `null`.
4. **Gán trước version cho entity mới.** Version wrapper khác `null` làm Spring Data JPA phân loại là không mới, có thể đi vào `merge` ngoài ý muốn.
5. **Quên `@Transient` hoặc callback cho cờ `isNew`.** Cờ có thể bị lưu thành cột không mong muốn hoặc entity load từ database vẫn báo mới, dẫn tới `persist` sai ở lần lưu sau.
6. **Bỏ qua đối tượng trả về từ `merge`.** Hãy tiếp tục thao tác trên `saved = repository.save(entity)` vì JPA có thể trả về instance managed khác object truyền vào.
7. **Trông đợi `@PostPersist` chạy ngay sau một `save` chưa flush.** Thời điểm INSERT và callback phụ thuộc flush/transaction; dùng `saveAndFlush` trong kiểm thử cần quan sát ngay và kiểm tra trạng thái giao dịch.
8. **Xem `isNew` là phương án chống trùng bản ghi.** Nó không thay thế ràng buộc khóa chính/unique, kiểm soát cạnh tranh, optimistic locking hoặc một quy trình upsert rõ ràng.

Khi chẩn đoán, hãy hỏi theo thứ tự: entity có `Persistable` không và `isNew()` trả gì? Nếu không, có `@Version` dạng wrapper không và nó có `null` không? Nếu không, ID hiện là `null` hay giá trị khác? Sau đó kiểm tra phiên bản JPA/provider, thời điểm `flush` và SQL thực tế bằng integration test nếu cần. Những câu hỏi này giải thích chính xác hơn một phỏng đoán “có ID là đã lưu”.

## 8. Tóm tắt quyết định

- **`Persistable`:** dùng `isNew()` của entity.
- **Mặc định có `@Version` kiểu tham chiếu:** `null` → `persist`; khác `null` → `merge`.
- **Còn lại:** ID `null` (hoặc số primitive bằng `0`) → `persist`; ID đã có giá trị → `merge`.
- **Riêng Spring Data JPA:** `@Version` primitive không quyết định newness.
- **Bản chất:** quyết định của repository điều hướng thao tác JPA; tính tồn tại thực tế trong database và thời điểm SQL do JPA/provider, giao dịch và ràng buộc dữ liệu chi phối.

## Tài liệu tham khảo

- Spring Data JPA – Persisting Entities, Entity State-detection Strategies: https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html
- Mã nguồn `SimpleJpaRepository.save` (dòng nhận diện `isNew` và gọi `persist`/`merge`): https://github.com/spring-projects/spring-data-jpa/blob/main/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/support/SimpleJpaRepository.java
- Spring Data Commons – Entity State Detection Strategies (để đối chiếu sự khác biệt giữa mô-đun): https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html