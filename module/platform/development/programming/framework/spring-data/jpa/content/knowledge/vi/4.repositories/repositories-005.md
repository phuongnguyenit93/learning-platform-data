# Cơ chế tạo proxy và vai trò của SimpleJpaRepository

## 1. Mục tiêu và phạm vi

Trong Spring Data JPA, ta thường chỉ khai báo một interface repository, chẳng hạn `CustomerRepository`, rồi inject interface đó vào service. Ứng dụng vẫn có một bean thực thi được các phương thức dù ta không tự viết class `CustomerRepositoryImpl`.

Điều này hoạt động nhờ Spring Data tạo một repository proxy trong lúc khởi động ứng dụng. Proxy tiếp nhận lời gọi và chuyển tiếp đến đúng thành phần: implementation CRUD mặc định, bộ thực thi query method, hoặc custom repository fragment. `SimpleJpaRepository` là implementation nền mặc định cho các thao tác CRUD của `JpaRepository`.

Bài này giải thích vòng đời tạo repository, cách proxy định tuyến lời gọi và phần việc cụ thể của `SimpleJpaRepository` trong ứng dụng Spring Boot dùng Spring Data JPA.

## 2. Từ repository interface đến bean có thể inject

Ví dụ một repository thường gặp:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

`CustomerRepository` chỉ khai báo hợp đồng. Nó kế thừa các phương thức như `save`, `findById`, `findAll`, `deleteById` từ `JpaRepository`/các interface cha và bổ sung query method `findByEmail`. Không cần tự viết class triển khai toàn bộ các phương thức này.

Trong Spring Boot, repository thường được tự động quét từ package của class `@SpringBootApplication` trở xuống. Nếu repository nằm ngoài vùng quét mặc định, có thể cấu hình rõ bằng `@EnableJpaRepositories` và `basePackages` hoặc `basePackageClasses`.

## 3. Vòng đời tạo repository proxy

Quá trình diễn ra khi Spring xây dựng ApplicationContext, trước khi ứng dụng phục vụ request:

1. **Quét repository interface.** Cơ chế repository scanning tìm các interface kế thừa `Repository`, `CrudRepository`, `PagingAndSortingRepository` hoặc `JpaRepository` trong package được cấu hình. Interface generic dùng làm base chung thường được đánh dấu `@NoRepositoryBean` để không bị tạo bean riêng.
2. **Đăng ký FactoryBean.** Spring Data đăng ký một `JpaRepositoryFactoryBean` cho mỗi repository interface tìm được. FactoryBean là thành phần tạo ra bean repository mà ứng dụng sẽ inject.
3. **Tạo factory JPA.** `JpaRepositoryFactoryBean` nhận các phụ thuộc cần thiết, đặc biệt là `EntityManager`, rồi tạo `JpaRepositoryFactory`.
4. **Tạo implementation nền.** `JpaRepositoryFactory` xác định metadata của domain type và identifier type, sau đó tạo implementation nền mặc định là `SimpleJpaRepository` (trừ khi ứng dụng cấu hình repository base class khác).
5. **Tạo proxy và ghép các thành phần.** `RepositoryFactorySupport` dùng cơ chế proxy của Spring để ghép implementation nền, custom fragments, query method interceptors và các advice cần thiết như transaction advice.
6. **Đăng ký bean hoàn chỉnh.** Bean proxy được đăng ký dưới kiểu repository interface. Service có thể inject `CustomerRepository` và gọi phương thức như với một bean Spring thông thường.

Luồng khái quát:

```text
@EnableJpaRepositories / Spring Boot auto-configuration
                  |
                  v
       Repository interface được quét
                  |
                  v
          JpaRepositoryFactoryBean
                  |
                  v
           JpaRepositoryFactory
                  |
                  v
       RepositoryFactorySupport
                  |
                  v
       Proxy + implementation nền
       + query methods + fragments
                  |
                  v
          Repository bean được inject
```

Trong các class trên, `JpaRepositoryFactoryBean` và `JpaRepositoryFactory` thuộc phần tích hợp JPA; `RepositoryFactorySupport` là hạ tầng repository dùng chung của Spring Data Commons. Tên class giúp lần theo mã nguồn khi debug, còn chi tiết nội bộ có thể thay đổi giữa các phiên bản Spring Data.

## 4. Proxy làm nhiệm vụ gì?

Proxy là điểm vào của repository bean. Nó nhận lời gọi phương thức và chọn cơ chế xử lý tương ứng. Một repository có thể kết hợp nhiều loại phương thức:

| Loại phương thức | Thành phần thường xử lý | Ví dụ |
| --- | --- | --- |
| CRUD kế thừa từ `JpaRepository` | Implementation nền `SimpleJpaRepository` | `save`, `findById`, `deleteAll` |
| Query method suy ra từ tên | Query lookup và query execution infrastructure | `findByEmail`, `countByStatus` |
| Query khai báo bằng `@Query` | Query execution infrastructure | `findActiveCustomers` |
| Phương thức custom fragment | Class implementation của fragment | `anonymizeOlderThan` |
| Default method trong interface | Cơ chế gọi default method của proxy | `findContactEmail` |

Với query method, Spring Data phân tích tên phương thức hoặc đọc khai báo `@Query`, tạo truy vấn phù hợp rồi thực thi qua JPA. Ví dụ `findByEmail` được hiểu dựa trên thuộc tính `email` của domain type; phương thức này không cần được triển khai trong `SimpleJpaRepository`.

Với custom fragment, proxy ghép implementation do ứng dụng cung cấp vào repository composition. Fragment có thể bổ sung hành vi riêng hoặc cung cấp implementation ưu tiên cho một phương thức trùng với implementation nền. Vì vậy, không nên giả định mọi lời gọi repository đều đi thẳng đến `SimpleJpaRepository`.

## 5. Vai trò của SimpleJpaRepository

`SimpleJpaRepository` là repository base class mặc định cho Spring Data JPA. Nó triển khai các hợp đồng CRUD và paging/sorting bằng cách sử dụng `EntityManager` cùng metadata của entity. Nó là implementation nền trong composition của proxy, không phải class được tạo riêng cho từng interface repository.

Các trách nhiệm chính gồm:

- **Lưu entity:** `save` chọn `EntityManager.persist` hoặc `EntityManager.merge` dựa trên việc entity được xem là mới hay đã tồn tại.
- **Đọc entity:** `findById` dùng thao tác tìm theo khóa chính; `findAll` và các biến thể có `Sort`/`Pageable` tạo và thực thi truy vấn phù hợp.
- **Xóa entity:** các phương thức `delete`, `deleteById`, `deleteAll` xử lý entity theo trạng thái quản lý và metadata khóa chính.
- **Đồng bộ persistence context:** `flush` yêu cầu `EntityManager` đồng bộ thay đổi đang được quản lý xuống database; `saveAndFlush` lưu rồi flush.
- **Làm việc với tham chiếu:** `getReferenceById` dùng `EntityManager.getReference`, có thể trả về tham chiếu tải dữ liệu trì hoãn.
- **Phân trang và sắp xếp:** các overload nhận `Pageable` hoặc `Sort` xây dựng truy vấn dữ liệu và, với `Page`, thường cần thêm truy vấn đếm tổng số bản ghi.

Class này thường được khởi tạo với `JpaEntityInformation` và `EntityManager`. `JpaEntityInformation` cung cấp thông tin về entity, identifier và cách xác định trạng thái mới; `EntityManager` thực hiện thao tác JPA.

## 6. Hiểu đúng phương thức save

Đây là một trong những hành vi quan trọng nhất của `SimpleJpaRepository`. Về ý tưởng, `save` hoạt động như sau:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}
return entityManager.merge(entity);
```

Đây là đoạn mã minh họa cơ chế, không phải bản sao đầy đủ của implementation trong framework.

`isNew` thường dựa trên metadata của entity. Nếu entity triển khai `Persistable`, Spring Data có thể dùng `isNew()` của entity. Với cơ chế mặc định, Spring Data thường xem xét thuộc tính `@Version` nullable trước, sau đó dùng identifier để xác định entity mới. Vì vậy, không phải lúc nào `id == null` cũng là quy tắc duy nhất.

Hai nhánh có ý nghĩa khác nhau:

- `persist` đưa entity mới vào persistence context. Entity được quản lý sau lời gọi này; câu lệnh `INSERT` có thể được gửi ngay hoặc ở thời điểm flush tùy chiến lược sinh khóa và trạng thái transaction.
- `merge` sao chép trạng thái của entity đầu vào vào một instance được quản lý và trả về instance đó. Đối với entity detached, không nên giả định object đầu vào chính là object managed sau `merge`; hãy dùng giá trị mà `save` trả về.

Ví dụ sử dụng đúng giá trị trả về:

```java
Customer customer = new Customer("dev@example.com");
Customer managedCustomer = customerRepository.save(customer);
```

Nếu cần tiếp tục thay đổi entity sau khi lưu, dùng `managedCustomer` để tránh nhầm lẫn giữa object đầu vào và object được quản lý.

`saveAll` về cơ bản áp dụng thao tác lưu cho từng entity. Gọi `saveAll` không tự đảm bảo database chỉ nhận một câu SQL hoặc JDBC batch được bật; batching phụ thuộc cấu hình Hibernate, driver, thứ tự thao tác và chiến lược sinh khóa.

## 7. Theo dấu hai lời gọi điển hình

Giả sử service gọi:

```java
customerRepository.save(customer);
customerRepository.findByEmail("dev@example.com");
```

**Với `save`:**

1. Service gọi method trên repository proxy.
2. Transaction advice áp dụng theo cấu hình transaction của method và context hiện tại.
3. Proxy định tuyến method CRUD đến implementation nền `SimpleJpaRepository`.
4. `SimpleJpaRepository.save` kiểm tra trạng thái mới qua `JpaEntityInformation`.
5. Nó gọi `EntityManager.persist` hoặc `EntityManager.merge`.
6. Hibernate quản lý entity trong persistence context và gửi SQL khi cần flush/commit hoặc theo yêu cầu của provider.

**Với `findByEmail`:**

1. Proxy nhận lời gọi query method.
2. Query infrastructure dùng tên `findByEmail` để xác định thuộc tính `email` và tạo truy vấn.
3. Truy vấn được thực thi qua JPA `EntityManager`.
4. Kết quả được chuyển về kiểu trả về khai báo, ở đây là `Optional<Customer>`.

Điểm cần nhớ: `findByEmail` là query method do hạ tầng query xử lý; nó không phải phương thức CRUD được viết sẵn trong `SimpleJpaRepository`.

## 8. Custom repository fragment

Khi nghiệp vụ cần thao tác đặc thù, hãy tách phần đó thành fragment thay vì cố nhồi mọi hành vi vào service hoặc kế thừa trực tiếp implementation nội bộ.

Interface fragment:

```java
public interface CustomerMaintenance {
    int deactivateBefore(Instant cutoff);
}
```

Implementation fragment (ví dụ minh họa, giả sử entity có thuộc tính `active` và `lastSeenAt`):

```java
public class CustomerMaintenanceImpl implements CustomerMaintenance {
    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public int deactivateBefore(Instant cutoff) {
        return entityManager.createQuery(
                "update Customer c set c.active = false where c.lastSeenAt < :cutoff")
            .setParameter("cutoff", cutoff)
            .executeUpdate();
    }
}
```

Repository kết hợp fragment:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerMaintenance {
    Optional<Customer> findByEmail(String email);
}
```

Spring Data tìm implementation fragment theo quy ước tên hoặc cấu hình repository implementation postfix. Với postfix mặc định `Impl`, class `CustomerMaintenanceImpl` là tên thường dùng. Cần đặt interface và implementation trong phạm vi package mà cấu hình repository có thể phát hiện, hoặc cấu hình rõ nếu dự án tổ chức package khác.

Fragment dùng được `EntityManager`, repository khác hoặc các dependency Spring phù hợp. Nếu fragment thực hiện cập nhật dữ liệu, hãy xác định transaction boundary rõ ràng; có thể đặt `@Transactional` trên method/implementation hoặc gọi từ service đang có transaction.

## 9. Transaction và thời điểm SQL thực sự chạy

`SimpleJpaRepository` cung cấp transaction metadata cho các phương thức CRUD kế thừa: các thao tác đọc thường chạy với `readOnly = true`, còn thao tác ghi có transaction. Tuy nhiên, các query method do ứng dụng tự khai báo không mặc nhiên nhận transaction configuration chỉ vì chúng nằm trong repository interface.

Trong ứng dụng thực tế, nên đặt transaction boundary ở service cho một use case nghiệp vụ có nhiều thao tác:

```java
@Service
public class CustomerService {
    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void register(Customer customer) {
        customerRepository.save(customer);
        // Các thao tác nghiệp vụ khác cùng tham gia transaction này.
    }
}
```

Ví dụ trên giả định đã có entity và import cần thiết. Transaction ở service giúp nhiều lời gọi repository tham gia cùng một transaction và giữ ranh giới nghiệp vụ dễ hiểu.

Không nên suy luận rằng gọi `save` luôn đồng nghĩa SQL đã chạy ngay tại dòng đó. Hibernate có thể trì hoãn ghi xuống database đến flush hoặc commit. Khi cần kiểm tra constraint hoặc SQL trong lúc debug/test, có thể dùng `flush()` có chủ đích; không nên flush sau mọi thao tác một cách máy móc vì điều đó có thể ảnh hưởng hiệu năng.

## 10. Cách debug repository proxy

Khi một method không chạy như mong đợi, hãy xác định nó thuộc nhóm CRUD, query method, default method hay custom fragment trước khi đọc sâu vào framework.

- Kiểm tra repository interface có nằm trong package được quét không; nếu không, cấu hình `@EnableJpaRepositories`.
- Kiểm tra domain type có phải JPA entity hợp lệ và identifier type có đúng không.
- Đặt breakpoint ở method service, sau đó lần theo method của repository proxy và implementation tương ứng.
- Với CRUD, đặt breakpoint trong `SimpleJpaRepository` như `save`, `findById` hoặc `deleteById`.
- Với query method, kiểm tra query lookup, tên thuộc tính trong method, `@Query`, parameter binding và kiểu trả về.
- Với custom fragment, xác nhận implementation được phát hiện, tên postfix đúng và method signature khớp.
- Khi quan sát class runtime, có thể thấy tên proxy do JVM/Spring tạo ra thay vì tên interface. Đây là điều bình thường; code ứng dụng nên phụ thuộc vào repository interface.

Trong test tích hợp JPA, `@DataJpaTest` có thể tạo application context thu gọn, cấu hình repository và cung cấp database test theo cấu hình dự án. Test nên kiểm tra hành vi quan sát được như lưu, đọc, cập nhật và query, thay vì phụ thuộc vào tên class proxy nội bộ.

## 11. Lỗi thường gặp và cách xử lý

**Không inject được repository.** Kiểm tra package scanning, `@EnableJpaRepositories`, cấu hình datasource, JPA provider và `EntityManagerFactory`. Repository interface nằm ngoài vùng quét là nguyên nhân phổ biến.

**Ứng dụng báo không tìm thấy implementation cho custom method.** Kiểm tra fragment interface đã được repository kế thừa chưa, tên class implementation/postfix có đúng không và package có được phát hiện không.

**Query method không được phân tích.** Kiểm tra tên thuộc tính trong method có khớp entity không, kiểu tham số và kiểu trả về có hợp lệ không. Với truy vấn phức tạp, cân nhắc dùng `@Query` để thể hiện rõ JPQL/SQL.

**Gọi save nhưng chưa thấy INSERT/UPDATE trong log.** Kiểm tra transaction, thời điểm flush/commit, persistence context và logger SQL. `save` có thể chỉ thay đổi trạng thái được quản lý trước khi SQL được gửi.

**Sau merge, object ban đầu không phản ánh trạng thái managed.** Dùng object được trả về từ `save`, vì `EntityManager.merge` trả về instance managed.

**saveAll không tạo batch như kỳ vọng.** Kiểm tra Hibernate JDBC batching, driver, chiến lược sinh ID và cách transaction được sử dụng. `saveAll` tự nó không phải cam kết batching.

**Một method trùng tên chạy implementation khác dự kiến.** Kiểm tra method có thuộc CRUD base, query method, default method hay custom fragment. Custom fragment có thể có độ ưu tiên cao hơn base implementation; các method CRUD được định nghĩa sẵn cũng có semantics dành riêng.

## 12. Tổng kết

Spring Data JPA tạo repository proxy trong quá trình khởi động từ interface mà ứng dụng khai báo. `JpaRepositoryFactoryBean` và `JpaRepositoryFactory` phối hợp với hạ tầng `RepositoryFactorySupport` để ghép implementation nền, query method, custom fragment và advice thành bean có thể inject.

`SimpleJpaRepository` đảm nhiệm CRUD mặc định bằng `EntityManager` và metadata entity. Proxy định tuyến từng lời gọi đến đúng cơ chế, nên query method và custom fragment không nhất thiết đi qua `SimpleJpaRepository`. Hiểu ranh giới này giúp debug chính xác, mở rộng repository đúng cách và tránh phụ thuộc vào chi tiết proxy nội bộ.