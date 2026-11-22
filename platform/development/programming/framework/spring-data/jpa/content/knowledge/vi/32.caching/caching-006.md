# Query hints và `CacheRetrieveMode`, `CacheStoreMode` trong Spring Data JPA

Trong Spring Data JPA, **query hint** là một chỉ dẫn gửi kèm truy vấn cho JPA provider (ví dụ Hibernate). Hai hint chuẩn `CacheRetrieveMode` và `CacheStoreMode` điều khiển cách một thao tác đọc/ghi tương tác với **bộ nhớ đệm cấp hai (second-level cache, L2)**. Hiểu đúng chúng giúp bạn quyết định khi nào được tận dụng dữ liệu đã cache, khi nào bỏ qua dữ liệu L2 cũ và khi nào làm mới L2 sau khi đọc database.

Trọng tâm của bài là **Spring Data JPA repository**, các giá trị của Jakarta Persistence, sự phối hợp với `EntityManager` và các giới hạn thường bị bỏ qua. Ví dụ dùng **Java 17+, Spring Boot 3.x/Spring Data JPA 3.x và `jakarta.persistence`**; nếu dự án dùng Spring Boot 2/JPA 2, tên gói và khóa hint tương ứng là `javax.persistence.*`.

## 1. Đặt query hints đúng vị trí trong hệ thống cache

Trước khi áp dụng một hint, cần phân biệt ba cơ chế:

| Cơ chế | Phạm vi | Lưu gì? | Hai cache mode chuẩn tác động thế nào? |
|---|---|---|---|
| **First-level cache (L1)** | Một persistence context/`EntityManager` | Các entity đang được quản lý, theo định danh | **Không bị tắt** bằng `CacheRetrieveMode.BYPASS` hay `CacheStoreMode.BYPASS` |
| **Second-level cache (L2)** | Thường chia sẻ giữa các `EntityManager` thuộc cùng `EntityManagerFactory` | Trạng thái entity/collection đủ điều kiện cache theo provider | **Đây là đối tượng điều khiển** của retrieve/store mode |
| **Query result cache** | Bộ cache truy vấn riêng của provider, ví dụ Hibernate | Kết quả hoặc danh sách định danh của một truy vấn cùng tham số | Cần cấu hình/hint riêng; **không tự bật** bởi `CacheRetrieveMode.USE` |

Ví dụ: cùng một giao dịch, bạn gọi `findById(10L)` hai lần. Lần thứ hai có thể được đáp ứng từ L1 ngay cả khi L2 bị bypass, bởi persistence context đã giữ đối tượng managed với ID đó. Vì vậy, một hint BYPASS **không bảo đảm** trả về trạng thái mới nhất từ database trong mọi tình huống.

Một truy vấn JPQL `select p from Product p where p.category = :category` thông thường vẫn phải chạy SQL để xác định hàng thỏa điều kiện, kể cả khi L2 đã cache các entity. L2 entity cache và Hibernate query result cache giải quyết hai bài toán khác nhau; muốn tránh chạy lại một câu truy vấn lặp, phải nghiên cứu query result cache riêng.

Query hint cũng **không thay thế** chính sách nhất quán dữ liệu, transaction isolation, khóa hay cơ chế đồng bộ khi nhiều ứng dụng cập nhật cùng database.

## 2. `CacheRetrieveMode`: chọn cách đọc từ L2

`jakarta.persistence.CacheRetrieveMode` có đúng **hai** giá trị:

- **`USE` (mặc định):** cho phép provider đọc dữ liệu entity từ L2 khi có bản cache hợp lệ. Nếu không có hoặc không sử dụng được cache, provider có thể phải truy vấn database. `USE` không bảo đảm một cache hit.
- **`BYPASS`:** bỏ qua việc **đọc L2** khi thực hiện thao tác áp dụng hint; provider lấy dữ liệu từ database thay vì lấy từ L2. L1 vẫn có hiệu lực, và một entity đã managed trong cùng persistence context có thể được dùng lại.

Tên property chuẩn dùng trong Spring Boot 3+/Jakarta Persistence:

```text
jakarta.persistence.cache.retrieveMode
```

Tên enum trong Java: `CacheRetrieveMode.USE` và `CacheRetrieveMode.BYPASS`. Đừng nhầm `BYPASS` ở chế độ này với việc vô hiệu hóa mọi cache.

## 3. `CacheStoreMode`: chọn cách ghi hoặc làm mới L2

`jakarta.persistence.CacheStoreMode` có **ba** giá trị:

| Giá trị | Ý nghĩa với L2 | Trường hợp cần nhớ |
|---|---|---|
| `USE` (mặc định) | Cho phép đưa entity đã đọc từ database vào L2 và cập nhật cache khi ghi dữ liệu; không bắt buộc refresh mục đã cache sẵn mỗi lần đọc database | Chế độ thông thường |
| `BYPASS` | Không đưa hoặc cập nhật entity vào L2 cho thao tác; provider có thể **invalidate** mục cache khi ghi database | Muốn hạn chế ghi cache trong một luồng đặc biệt |
| `REFRESH` | Khi đọc dữ liệu từ database hoặc ghi dữ liệu, đưa/cập nhật trạng thái entity vào L2, kể cả khi L2 đã có dữ liệu | Muốn tái tạo mục cache từ dữ liệu đã đọc mới |

Tên property chuẩn:

```text
jakarta.persistence.cache.storeMode
```

Lưu ý quan trọng:

- `REFRESH` **không tự buộc** một đối tượng đang managed trong L1 phải tải lại dữ liệu. Nó mô tả cách xử lý **L2 khi dữ liệu được lấy từ database** hoặc được ghi.
- `REFRESH` là giá trị của **store mode**; `CacheRetrieveMode` **không** có giá trị `REFRESH`.
- `BYPASS` ở store mode không đồng nghĩa với xóa tất cả entry của L2. Với thao tác ghi, provider được phép vô hiệu hóa entry có liên quan để duy trì nhất quán.
- Nếu L2 chưa được bật hoặc entity không thuộc phạm vi cache, các cache mode **không mang lại tác dụng L2**.

## 4. Kết hợp hai mode: đọc ở đâu và xử lý cache ra sao?

| Retrieve mode | Store mode | Cách hiểu thực tế |
|---|---|---|
| `USE` | `USE` | Có thể đọc từ L2; khi đọc database, có thể nạp vào L2. Đây là mặc định. |
| `BYPASS` | `USE` | Không đọc L2; khi tải dữ liệu từ database, có thể nạp/cập nhật L2 theo chính sách `USE`. |
| `USE` | `BYPASS` | Có thể đọc L2; không nạp/cập nhật L2 trong thao tác được áp dụng. |
| `BYPASS` | `BYPASS` | Không đọc L2 và không nạp/cập nhật L2 trong thao tác; không có nghĩa là tắt L1. |
| `BYPASS` | `REFRESH` | Bỏ qua L2 khi đọc và làm mới L2 bằng dữ liệu lấy từ database. Hữu ích khi cần đọc lại và cập nhật cache. |
| `USE` | `REFRESH` | Cho phép đọc L2; nếu thực sự tải dữ liệu từ database thì làm mới L2. **Không đảm bảo** bắt buộc truy vấn lại database. |

Trên Hibernate, các cặp này tương ứng về ý tưởng với các `CacheMode` như `NORMAL`, `PUT`, `GET`, `IGNORE` và `REFRESH`; khi viết mã Spring Data JPA có thể dùng cặp enum chuẩn Jakarta Persistence để dễ chuyển đổi provider.

Một quy tắc vận dụng: muốn **bỏ qua dữ liệu L2 và cập nhật lại L2 từ lần đọc database đó**, hãy cân nhắc **`BYPASS + REFRESH`**. Muốn truy vấn **không đọc và không bổ sung L2**, dùng **`BYPASS + BYPASS`**. Cả hai vẫn phải xét L1 và ngữ cảnh transaction.

## 5. Gắn query hints trên phương thức Spring Data JPA repository

Spring Data JPA cung cấp `org.springframework.data.jpa.repository.QueryHints` để đặt nhiều `jakarta.persistence.QueryHint` trên một phương thức repository. Áp dụng được cho query viết bằng `@Query` và nhiều phương thức query suy ra từ tên method.

Ví dụ dưới đây thể hiện một **entity đủ điều kiện xét cache**. File `Product.java` (trong package entity của ứng dụng):

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Cacheable
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false)
    private String name;

    protected Product() { }

    public Product(String category, String name) {
        this.category = category;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getCategory() {
        return category;
    }

    public String getName() {
        return name;
    }
}
```

`@Cacheable` trong đoạn này là **`jakarta.persistence.Cacheable`**, khác với **`org.springframework.cache.annotation.Cacheable`** của Spring Cache. Nó mô tả khả năng cache entity theo JPA; **chỉ annotation này chưa đủ để bảo đảm hệ thống có một L2 cache hoạt động**. Bạn còn cần cấu hình cache provider, các vùng cache và shared-cache mode phù hợp.

File `ProductRepository.java`:

```java
import jakarta.persistence.QueryHint;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {

    @Query("""
           select p
           from Product p
           where p.category = :category
           """)
    @QueryHints(
        value = {
            @QueryHint(
                name = "jakarta.persistence.cache.retrieveMode",
                value = "BYPASS"
            ),
            @QueryHint(
                name = "jakarta.persistence.cache.storeMode",
                value = "REFRESH"
            )
        },
        forCounting = false
    )
    Page<Product> findFreshByCategory(
            @Param("category") String category,
            Pageable pageable);
}
```

**Cách đọc đoạn mã:**

1. `@Query` xác định câu JPQL. Spring Data JPA tạo truy vấn danh sách `Product` theo `category`, áp dụng phân trang.
2. `@QueryHints` gắn hai hint chuẩn: không đọc entity từ L2 khi thực hiện truy vấn và đề nghị cập nhật lại L2 bằng entity đã được đọc từ database.
3. `@QueryHint.value` là **String**, vì vậy annotation nhận `"BYPASS"` và `"REFRESH"`. Các tên hint và giá trị phải chính xác; nếu tích hợp provider cụ thể, kiểm tra nó diễn giải những chuỗi này đúng enum mong muốn.
4. `forCounting = false` yêu cầu Spring Data JPA **không chuyển hai hint sang count query** phục vụ `Page`. Truy vấn đếm không tải entity nên cache retrieve/store mode của entity thường không giúp ích. Một count query có thể được bỏ qua bởi chiến lược phân trang tối ưu nếu đã đủ dữ liệu, nhưng khi nó được tạo thì hai hint không áp dụng.
5. Hint gắn với **phương thức truy vấn này**; `findById`, `findAll` hoặc một query khác không tự động kế thừa annotation ấy.

Đây là các lớp mã nguồn hợp lệ trong một dự án Spring Boot 3.x có `spring-boot-starter-data-jpa`, driver database và cấu hình datasource. Chúng **không phải** chương trình Java thuần có thể chạy một mình bằng `javac Product.java` vì cần Jakarta Persistence và Spring Data trên classpath.

### Một method derived query cũng có thể dùng `@QueryHints`

Nếu không cần JPQL tự viết, cú pháp còn ngắn hơn:

```java
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.QueryHints;

import java.util.List;

public interface ProductLookupRepository
        extends JpaRepository<Product, Long> {

    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.cache.retrieveMode",
            value = "BYPASS"
        ),
        @QueryHint(
            name = "jakarta.persistence.cache.storeMode",
            value = "BYPASS"
        )
    })
    List<Product> findByCategory(String category);
}
```

Spring Data JPA suy diễn query từ `findByCategory`, còn hai hint chỉ ảnh hưởng tương tác L2 của truy vấn đó.

## 6. Áp dụng hint khi dùng `EntityManager` trực tiếp

Với một thao tác `find` đơn lẻ, có thể dùng `Map<String, Object>` để truyền các enum thật. Cách này tránh việc phải biểu diễn enum bằng chuỗi annotation:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

@Service
public class ProductReadService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public Product findByIdBypassingL2(Long id) {
        Map<String, Object> hints = Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.REFRESH
        );
        return entityManager.find(Product.class, id, hints);
    }
}
```

Hành vi dự định: thao tác `find` không lấy entity từ L2 và nếu tải từ database, provider làm mới entry cache thích hợp. Tuy nhiên, **nếu entity cùng ID đã được quản lý trong chính `EntityManager`**, L1 có thể trả về instance có sẵn. Không nên đặt tên method là “luôn lấy dữ liệu mới nhất” chỉ nhờ cặp hint này.

Cũng có thể truyền mode cho một `TypedQuery`:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.TypedQuery;

TypedQuery<Product> query = entityManager.createQuery(
    "select p from Product p where p.category = :category",
    Product.class
);
query.setParameter("category", "Laptop");
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);
var products = query.getResultList();
```

Đây là **đoạn mã nằm trong một method đã có biến `entityManager`**, không phải một file chạy độc lập. Một hint đặt trên `TypedQuery` chỉ áp dụng khi thực thi query đó; nó được ưu tiên hơn giá trị mode chung của `EntityManager` tại thao tác tương ứng.

Nếu đang giữ entity managed và cần nạp lại trạng thái từ database, xem xét **`entityManager.refresh(managedEntity)`** trong ngữ cảnh transaction thích hợp. `refresh` đọc database thay vì lấy dữ liệu L2; cache retrieve mode không phải yếu tố quyết định ở thao tác `refresh`. Việc `clear()` hoặc mở persistence context mới có thể giúp tách ảnh hưởng của L1 trong phép kiểm thử, nhưng **`clear()` sẽ detach mọi entity đang managed** và có thể làm mất các thay đổi chưa flush nếu dùng bất cẩn.

## 7. Query hints chuẩn khác query result cache của Hibernate

`@QueryHints` là **cơ chế gắn metadata**; không có nghĩa tất cả hint đều điều khiển cache. Một số hint ảnh hưởng timeout, cách fetch, chế độ chỉ đọc hoặc đặc tính thực thi, tùy chuẩn JPA và provider. Với các khóa cache chuẩn ở bài này, đối tượng điều khiển là **L2 entity cache**.

Hibernate có một tính năng **query result cache** riêng. Ví dụ hint đặc thù Hibernate:

```java
@QueryHints({
    @QueryHint(
        name = "org.hibernate.cacheable",
        value = "true"
    )
})
```

Đây chỉ là **đoạn annotation minh họa**, phải đặt trên method repository tương ứng. Nó không tự kích hoạt toàn bộ hạ tầng cache: cần bật tính năng query cache của Hibernate (`hibernate.cache.use_query_cache=true`), có cache region/provider phù hợp và thiết lập entity/collection cache khi cần. Query result cache có thể cache tập định danh/kết quả truy vấn, còn việc nạp trạng thái entity vẫn liên quan đến L1/L2 và database.

**Đừng suy luận** “đặt `CacheRetrieveMode.USE` ⇒ truy vấn JPQL sẽ không chạy SQL”. Hint L2 không phải lệnh bật Hibernate query cache, và đặc tính count query, phân trang, dữ liệu bị cập nhật cũng ảnh hưởng số SQL được phát.

Khi dùng API đặc thù Hibernate, nên ưu tiên các hằng hint chính thức của phiên bản Hibernate đang dùng (ví dụ `HibernateHints.HINT_CACHEABLE`) thay vì rải chuỗi magic trong nhiều repository. Dùng hint do provider khác định nghĩa sẽ giảm tính portable; JPA có thể bỏ qua hint nó không nhận biết.

## 8. Điều kiện để hai cache mode có hiệu quả

Một dự án thực tế cần đồng thời xác nhận:

1. **Shared cache được cho phép** đối với persistence unit. JPA hỗ trợ các chế độ như `NONE`, `ALL`, `ENABLE_SELECTIVE` và `DISABLE_SELECTIVE`. Với `ENABLE_SELECTIVE`, chỉ những entity đủ điều kiện như entity có `@jakarta.persistence.Cacheable` được tham gia.
2. **Provider L2 cache đã được cài đặt và bật thực sự.** Ví dụ khi dùng Hibernate phải có cache region factory/cache implementation tương thích; bật flag mà thiếu provider không làm phép đo cache có giá trị.
3. **Entity/các association cụ thể đủ điều kiện cache.** Đừng mặc định mọi kết quả từ DTO projection, native scalar query hoặc collection đều có L2 entry.
4. **Đo lường trong bối cảnh tách L1.** Đọc lại trong cùng `EntityManager` dễ tạo kết quả giả vì identity map L1. Phép đo nên dùng các persistence context khác nhau và dữ liệu kiểm thử có trạng thái rõ ràng.
5. **Xác nhận hành vi bằng công cụ của provider.** Với Hibernate, có thể bật thống kê (`hibernate.generate_statistics=true`), xem second-level cache hit/miss/put, SQL thực tế và số lần query result cache hit/miss nếu đang dùng query cache.

Điều quan trọng là không kết luận dựa vào **SQL log đơn độc**: một JPQL query có thể vẫn chạy SELECT nhưng các entity lấy từ L2; ngược lại, không thấy SELECT không chứng minh L2 hoạt động nếu entity đã nằm trong L1.

## 9. Kịch bản trước–sau để chọn mode

### Kịch bản A: dữ liệu tham chiếu ít thay đổi

Danh mục `Product` được nhiều request đọc, ít sửa. Cấu hình L2 hợp lý và chế độ `USE/USE` thường cho phép tận dụng cache. Không cần gắn hint BYPASS vào mọi query chỉ vì muốn “an toàn”; sẽ đánh mất khả năng tái sử dụng cache.

### Kịch bản B: người quản trị vừa sửa dữ liệu ngoài ứng dụng

Một hệ thống ngoài Hibernate cập nhật trực tiếp database, khiến mục L2 của `Product` có thể cũ. Với lần **đọc lại trong persistence context mới**, `CacheRetrieveMode.BYPASS` kết hợp `CacheStoreMode.REFRESH` là lựa chọn có thể giúp đọc database và tái tạo entry L2. Tuy nhiên, giải pháp bền vững cần xem lại **quy trình đồng bộ/invalidation** vì một query đơn lẻ không thể xử lý hết stale cache trên các node hoặc transaction đồng thời.

Nếu chỉ muốn bỏ qua L2 cho đúng một lần mà không tái tạo entry, dùng `BYPASS/BYPASS`. Nhưng entry cũ có thể vẫn tồn tại trong L2 để các luồng khác dùng; vì thế bỏ qua cache ở một chỗ **không tự chữa lỗi nhất quán dữ liệu**.

### Kịch bản C: cần đọc lại entity đang managed

`Product` đã được load trong cùng `EntityManager`, rồi dữ liệu bị thay đổi bên ngoài. `BYPASS/REFRESH` không bảo đảm ghi đè state trong L1. Nếu đúng nghiệp vụ yêu cầu đọc mới, đánh giá `entityManager.refresh(entity)`; luôn xem xét flush/transaction, isolation và khả năng ghi đè thay đổi đang chờ trong bộ nhớ.

### Kịch bản D: truy vấn phân trang có count

`Page<Product>` có thể sinh truy vấn data và truy vấn count. Cache retrieve/store hint cho data query có ý nghĩa với entity, nhưng không giúp SELECT COUNT. Vì thế `@QueryHints(..., forCounting = false)` giữ hint khỏi count query; đừng nhầm `forCounting = false` với “không chạy count query”.

## 10. Lỗi thường gặp và cách kiểm tra

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `CacheRetrieveMode.REFRESH` | Giá trị **không tồn tại**; nhầm enum | Dùng `CacheStoreMode.REFRESH` |
| Nghĩ `retrieveMode=BYPASS` tắt cả L1 | Entity managed có thể vẫn được trả về | Tách persistence context khi thử nghiệm, hoặc dùng `refresh` nếu phù hợp |
| Nghĩ `storeMode=BYPASS` làm sạch L2 | Không có yêu cầu xóa toàn bộ cache | Dùng eviction/invalidation có chủ đích nếu cần |
| Nghĩ `@Cacheable` là đủ để cache chạy | L2 provider/cấu hình có thể chưa bật | Kiểm tra shared-cache mode, region factory, cache backend |
| Nghĩ `USE` luôn tạo cache hit | Query có thể đọc database; entity có thể không eligible | Đo cache hit/miss và điều kiện cache |
| Nghĩ `BYPASS/REFRESH` luôn đọc giá trị mới nhất | L1, transaction isolation và external writers vẫn tác động | Kiểm tra ngữ cảnh persistence, transaction và freshness requirement |
| Bật query result cache chỉ bằng hai mode chuẩn | Truy vấn JPQL vẫn có thể chạy SQL | Bật/đo query result cache riêng nếu thực sự cần |
| Áp dụng hint lên cả count query | Không cần thiết cho entity cache | Đặt `forCounting = false` khi dùng `Page` |
| Dùng nhầm `javax.persistence.*` trong Boot 3+ | Sai tên property/package; hint có thể bị bỏ qua | Dùng `jakarta.persistence.*` đúng phiên bản |
| Đặt hint không được provider nhận biết | Hint có thể bị bỏ qua; kết quả không như kỳ vọng | Dùng hint chuẩn, kiểm tra docs của provider và integration test |

### Checklist thực hành

- Xác nhận bạn cần điều khiển **L2 entity cache** hay thực sự muốn **cache kết quả câu truy vấn**.
- Xác nhận L2 đang được bật và entity đủ điều kiện.
- Chọn retrieve mode theo câu hỏi “có được đọc bản cache L2 hay không?”.
- Chọn store mode theo câu hỏi “có cho phép ghi hoặc refresh L2 hay không?”.
- Áp dụng hint đúng query/repository method, tránh thay đổi global settings khi yêu cầu chỉ ở một luồng.
- Với phân trang, quyết định `forCounting` có nên là `false`.
- Kiểm thử trong các persistence context tách biệt, đo SQL và thống kê L2/query cache. Đồng thời kiểm thử luồng dữ liệu thay đổi bên ngoài ứng dụng nếu đó là nguyên nhân cần bypass.

## 11. Ghi nhớ nhanh

- `CacheRetrieveMode` chỉ gồm **`USE`** và **`BYPASS`**: *đọc từ L2 hay bỏ qua L2*.
- `CacheStoreMode` gồm **`USE`**, **`BYPASS`**, **`REFRESH`**: *được ghi vào L2, không ghi, hay cập nhật lại L2*.
- `BYPASS/REFRESH` hữu ích để đọc lại database và làm mới L2 khi context phù hợp; **không vô hiệu hóa L1**.
- `@QueryHints` + `@QueryHint` gắn các chế độ này lên một phương thức Spring Data JPA; `forCounting = false` loại hint khỏi count query khi phân trang.
- Query result cache của Hibernate là chức năng khác với entity L2 cache; cache mode chuẩn không thay thế cấu hình query cache.

## Tài liệu tham khảo chính thức

1. Spring Data JPA, *Applying Query Hints*: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
2. Spring Data JPA, `@QueryHints` API (`forCounting`): https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/QueryHints.html
3. Jakarta Persistence, `CacheRetrieveMode`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CacheRetrieveMode.html
4. Jakarta Persistence, `CacheStoreMode`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CacheStoreMode.html
5. Jakarta EE Tutorial, *Using a Second-Level Cache*: https://jakarta.ee/learn/docs/jakartaee-tutorial/current/persist/persistence-cache/persistence-cache.html
6. Hibernate ORM User Guide, *Managing the cached data* và query result caching: https://docs.hibernate.org/orm/current/userguide/html_single/