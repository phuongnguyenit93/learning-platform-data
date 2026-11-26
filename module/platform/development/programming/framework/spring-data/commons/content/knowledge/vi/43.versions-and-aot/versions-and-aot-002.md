# Chuyển giao diện CRUD/sorting cũ sang hệ phân cấp hiện hành

## Mục tiêu và phạm vi

Một thay đổi quan trọng khi chuyển từ Spring Data đời cũ sang hệ phân cấp từ Spring Data 3.0 là các giao diện sorting không còn mặc nhiên kế thừa CRUD như trước.

Hệ quả dễ thấy: một repository chỉ kế thừa PagingAndSortingRepository có thể vẫn có phương thức phân trang nhưng không còn công khai save hoặc findById qua hợp đồng đó.

Spring Data Commons cũng cung cấp các biến thể trả List cho nhóm phương thức phù hợp. Việc chuyển đổi cần xem cả superinterface, kiểu biến ở service, implementation tùy biến và các consumer đã biên dịch.

Sau bài học này, bạn có thể:

- Nhận diện giả định CRUD/sorting từ hệ phân cấp cũ.
- Ghép các interface đúng với năng lực cần dùng.
- Chọn Iterable hay List một cách có chủ đích.
- Chuyển repository cơ sở generic và các kiểu inject.
- Phân biệt lỗi biên dịch, lỗi liên kết thư viện và lỗi cấu hình repository.
- Hiểu phần cần kiểm tra thêm khi dự án có AOT hoặc native image.

Bài tập trung vào cấu trúc API và hợp đồng. Không đưa ra một số phiên bản mới nhất làm đích mặc định; dự án cần chọn bộ phiên bản Spring Data và module store tương thích theo nền tảng đang dùng.

## 1. Thay đổi cốt lõi của hệ phân cấp

Trong hệ phân cấp trước Spring Data 3.0, mô hình quen thuộc là:

```text
Repository<T, ID>
    |
CrudRepository<T, ID>
    |
PagingAndSortingRepository<T, ID>
```

Vì vậy, mã kế thừa PagingAndSortingRepository thường sử dụng được cả CRUD lẫn sorting/paging thông qua quan hệ kế thừa.

Trong hệ phân cấp từ Spring Data 3.0, hai nhóm được tách:

```text
Repository<T, ID>
    |
    +-- CrudRepository<T, ID>
    |
    +-- PagingAndSortingRepository<T, ID>
```

Muốn có cả hai nhóm năng lực, repository cụ thể hoặc repository cơ sở do ứng dụng định nghĩa cần kết hợp cả hai.

Thay đổi này không có nghĩa CRUD đã bị xóa khỏi Spring Data. Nó làm quan hệ kế thừa trở nên rõ ràng hơn: có sorting không tự đồng nghĩa có CRUD.

## 2. Bảng năng lực của các interface imperative

| Interface | CRUD thông thường | findAll(Sort) | findAll(Pageable) | Đặc điểm kiểu collection |
|---|---|---|---|---|
| CrudRepository | Có | Không từ interface này | Không từ interface này | Các method nhiều phần tử tương ứng trả Iterable |
| PagingAndSortingRepository | Không mặc nhiên có | Có | Có, trả Page | findAll(Sort) trả Iterable |
| ListCrudRepository | Có | Không từ interface này | Không từ interface này | Các method CRUD nhiều phần tử được đổi covariant sang List |
| ListPagingAndSortingRepository | Không mặc nhiên có | Có | Có, trả Page | findAll(Sort) trả List |

Những điểm cần lưu ý:

- ListCrudRepository kế thừa CrudRepository.
- ListPagingAndSortingRepository kế thừa PagingAndSortingRepository.
- ListPagingAndSortingRepository không tự cung cấp CRUD.
- ListCrudRepository không tự cung cấp sorting/paging.
- Kiểu Page của findAll(Pageable) không biến thành List chỉ vì dùng biến thể List.
- Một Page có thể có total, nhưng điều đó không có nghĩa interface sorting công khai method count() như CrudRepository.

Đây là bảng về API được kế thừa. Khả năng tạo implementation và hỗ trợ truy vấn vẫn thuộc module store cùng cấu hình thực tế.

## 3. Chuyển repository cũ sang hợp đồng CRUD và sorting rõ ràng

Khai báo cũ thường gặp:

```java
import org.springframework.data.repository.PagingAndSortingRepository;

public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {
}
```

Nếu ứng dụng cần cả save, findById, delete và phân trang, có thể chuyển thành:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {
}
```

Sau thay đổi, hợp đồng thể hiện rõ cả hai nhóm phương thức:

```java
Product saved = products.save(draft);

var found = products.findById(saved.getId());

var sorted = products.findAll(
        Sort.by(Sort.Order.asc("id")));

var page = products.findAll(
        PageRequest.of(
                0,
                20,
                Sort.by(Sort.Order.asc("id"))));
```

Các import Sort và PageRequest thuộc org.springframework.data.domain.

Ghép hai superinterface trên một repository cụ thể không có nghĩa tạo hai repository bean riêng. Nó mô tả một hợp đồng repository bao gồm hai nhóm năng lực, để factory của module thực hiện theo cấu hình tương ứng.

Không tạo thêm hai repository cho cùng domain chỉ để lấy lại CRUD và sorting nếu ứng dụng chỉ cần một hợp đồng kết hợp.

## 4. Khi nào chọn các biến thể List?

Nếu ứng dụng muốn các phương thức collection tương ứng trả List:

```java
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.ListPagingAndSortingRepository;

public interface ProductRepository
        extends ListCrudRepository<Product, Long>,
                ListPagingAndSortingRepository<Product, Long> {
}
```

Khi đó có thể viết:

```java
List<Product> all = products.findAll();

List<Product> selected = products.findAllById(
        List.of(1L, 2L, 3L));

List<Product> sorted = products.findAll(
        Sort.by(Sort.Order.asc("id")));

Page<Product> page = products.findAll(
        PageRequest.of(0, 20));
```

Các dòng trên minh họa kiểu trả về. Với một query không có sort, không tự suy ra thứ tự của List. findAllById cũng không nên được coi là cam kết giữ thứ tự ID đầu vào nếu hợp đồng cụ thể không bảo đảm.

### List không có nghĩa là truy vấn đã được giới hạn

findAll() trả List vẫn có thể tải toàn bộ tập kết quả. Đổi từ Iterable sang List không tạo paging, backpressure hoặc giới hạn bộ nhớ.

Nếu nhu cầu là chỉ đọc một phần dữ liệu, hãy chọn phương thức phân trang, giới hạn hoặc scrolling mà store hỗ trợ.

### Không dùng cast để đổi hợp đồng

Cách dễ sai:

```java
List<Product> result =
        (List<Product>) products.findAll();
```

Nếu kiểu tĩnh chỉ cam kết Iterable, implementation không bắt buộc trả một List có thể cast theo cách đó.

Có thể chọn ListCrudRepository khi phù hợp hoặc chuyển đổi có chủ đích:

```java
List<Product> result = new ArrayList<>();

products.findAll().forEach(result::add);
```

Cách chuyển đổi này materialize dữ liệu vào bộ nhớ, không phải giải pháp cho một tập quá lớn.

## 5. Sửa cả kiểu phụ thuộc ở service

Chỉ thêm CrudRepository vào ProductRepository chưa đủ nếu service vẫn khai báo biến theo interface sorting.

Ví dụ:

```java
private final PagingAndSortingRepository<Product, Long> products;
```

Qua kiểu tĩnh đó, mã không có quyền gọi save theo quan hệ kế thừa đã tách, dù bean cụ thể có thể thực hiện nhiều interface hơn.

Cách thường phù hợp là phụ thuộc vào repository cụ thể:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Product create(Product draft) {
        return products.save(draft);
    }
}
```

Nếu có service generic dùng chung, hãy định nghĩa một hợp đồng generic bao gồm đúng năng lực cần thiết.

Không cast một PagingAndSortingRepository thành CrudRepository ở từng điểm sử dụng để tránh sửa kiểu. Cast che mất yêu cầu thật của service và có thể tạo lỗi runtime với implementation khác.

Cũng không thêm method save rải rác vào mọi service adapter chỉ để giữ một kiểu phụ thuộc đã không còn phù hợp.

## 6. Chuyển repository cơ sở generic

Repository cơ sở kiểu cũ:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends PagingAndSortingRepository<T, ID> {
}
```

Nếu các consumer từng dựa vào CRUD được kế thừa gián tiếp, cần bổ sung rõ:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.PagingAndSortingRepository;

@NoRepositoryBean
public interface CrudSortingRepository<T, ID>
        extends CrudRepository<T, ID>,
                PagingAndSortingRepository<T, ID> {
}
```

Repository cụ thể:

```java
public interface ProductRepository
        extends CrudSortingRepository<Product, Long> {
}
```

Nếu muốn List cho toàn bộ hợp đồng tương ứng:

```java
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.ListPagingAndSortingRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ListCrudSortingRepository<T, ID>
        extends ListCrudRepository<T, ID>,
                ListPagingAndSortingRepository<T, ID> {
}
```

Hai base interface trên là hai phương án hợp đồng. Không bắt buộc một dự án phải có cả hai.

NoRepositoryBean biểu đạt rằng interface generic cơ sở không phải đích tạo bean độc lập. Không gắn nó lên repository cụ thể cần inject chỉ để tránh lỗi scan.

Mọi tầng generic cũng phải giữ T và ID đúng. Chuyển sang raw type để vượt lỗi biên dịch làm mất thông tin metadata mà framework cần.

## 7. Không thêm năng lực ghi khi ứng dụng chỉ cần đọc

Tách CRUD và sorting tạo cơ hội kiểm tra lại hợp đồng thay vì luôn ghép mọi thứ.

Nếu một thành phần chỉ cần:

- Đọc một trang.
- Đọc danh sách đã sort.

thì một interface chỉ công khai sorting/paging có thể là lựa chọn hợp lệ.

Nếu cần chọn lọc một số phương thức khác, có thể định nghĩa hợp đồng đọc phù hợp với khả năng routing của store:

```java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.PagingAndSortingRepository;

@NoRepositoryBean
public interface ReadRepository<T, ID>
        extends PagingAndSortingRepository<T, ID> {

    Optional<T> findById(ID id);
}
```

Đoạn mã thể hiện ý định không công khai toàn bộ CRUD ghi. Module store cần hỗ trợ việc thực hiện chữ ký đã khai báo.

Tên ReadRepository không tự cấu hình database chỉ đọc, transaction readOnly hay authorization. Đây là kiểm soát API ở mức Java.

Khi chuyển đổi, hãy quyết định consumer nào thật sự cần save/delete và consumer nào chỉ cần đọc, thay vì thêm CrudRepository theo quán tính ở mọi nơi.

## 8. Interface riêng của store có thể đã kết hợp sẵn

Một module store có thể cung cấp repository interface bao gồm nhiều năng lực.

Ví dụ trong hệ phân cấp phù hợp của Spring Data JPA, JpaRepository kết hợp các hợp đồng CRUD và sorting dạng List, cùng khả năng khác của JPA.

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Nếu dự án đã dùng JpaRepository, không mặc định mọi repository đều bị mất CRUD khi nâng hệ phân cấp Commons.

Tuy nhiên, không đổi một repository MongoDB, JDBC hoặc reactive sang JpaRepository chỉ để làm phương thức save xuất hiện. Đó là thay đổi phụ thuộc store và hạ tầng thực thi, không phải cách sửa trung lập.

Khi chọn interface riêng của module, cần xem:

- Domain được store nào quản lý.
- Ứng dụng có chủ đích phụ thuộc API riêng của store không.
- Có nhiều nhóm repository cùng classpath không.
- Package scan và factory đang tạo bean nào.
- Những năng lực bổ sung có thật sự cần được công khai không.

Một abstraction Commons vẫn hữu ích nếu ứng dụng muốn hạn chế phụ thuộc store. Nhưng nó không tự làm mọi đặc tính của các store trở nên tương đương.

## 9. Reactive và coroutine cũng phải ghép đúng họ interface

Việc tách sorting khỏi CRUD không chỉ liên quan PagingAndSortingRepository imperative.

Trong các họ tương ứng, cần xem các interface như:

- ReactiveCrudRepository và ReactiveSortingRepository.
- RxJava3CrudRepository và RxJava3SortingRepository.
- CoroutineCrudRepository và CoroutineSortingRepository.

Ví dụ reactive:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.data.repository.reactive.ReactiveSortingRepository;

public interface ReactiveProductRepository
        extends ReactiveCrudRepository<Product, String>,
                ReactiveSortingRepository<Product, String> {
}
```

Ví dụ coroutine:

```kotlin
import org.springframework.data.repository.kotlin.CoroutineCrudRepository
import org.springframework.data.repository.kotlin.CoroutineSortingRepository

interface CoroutineProductRepository :
    CoroutineCrudRepository<Product, String>,
    CoroutineSortingRepository<Product, String>
```

Các ví dụ giả định module store hỗ trợ mô hình repository đã chọn.

Không ghép CrudRepository imperative với ReactiveCrudRepository chỉ để có thêm phương thức. Các chữ ký có thể xung đột, và việc ghép interface không biến I/O đồng bộ thành non-blocking.

Cũng không suy rằng một interface reactive sorting tự cung cấp findAll(Pageable) hoặc Page giống interface imperative. Cần dùng đúng API và khả năng phân trang của module.

Nếu client cần total với một pipeline reactive, đó còn là thiết kế truy vấn và hợp đồng tổng số riêng; thêm một superinterface không tự tạo toàn bộ hành vi đó.

## 10. Kiểm tra chữ ký trả về khi có implementation tùy biến

Một interface trả List là một hợp đồng mạnh hơn so với Iterable.

Nếu có class trực tiếp implement interface, việc đổi superinterface có thể yêu cầu sửa chữ ký.

Ví dụ một chữ ký cũ:

```java
public Iterable<Product> findAll() {
    // implementation tùy biến
}
```

không tự thỏa một hợp đồng mới yêu cầu:

```java
public List<Product> findAll() {
    // implementation phù hợp
}
```

Tương tự, saveAll có generic riêng:

```java
<S extends Product> List<S> saveAll(
        Iterable<S> entities)
```

Không thay bằng một method mất generic như `List<Product> saveAll(Iterable<Product>)` rồi cho rằng mọi quan hệ override vẫn đúng. Có thể phát sinh name clash hoặc không thỏa hợp đồng.

Cần kiểm tra:

- Custom repository base class.
- Repository fragment.
- Test fake hoặc adapter tự viết.
- Interface do một thư viện nội bộ công khai.
- Method tham chiếu từ code generic.
- Các phương thức default gọi method được kế thừa.

Nếu implementation đã có List ở kiểu trả về thì thay đổi có thể nhỏ hơn, nhưng vẫn cần kiểm tra routing và kiểu của mọi consumer.

Một phương thức mới được khai báo lại cũng phải được framework nhận diện đúng là thao tác cơ sở hoặc phương thức tùy biến có implementation, không vô tình bị xử lý như một derived query.

## 11. Phân biệt lỗi biên dịch với lỗi liên kết runtime

### Lỗi biên dịch

Ví dụ:

```text
Không tìm thấy phương thức save trên kiểu
PagingAndSortingRepository<Product, Long>
```

Điều cần kiểm tra đầu tiên là hợp đồng của kiểu tĩnh và quan hệ kế thừa.

Không cần sửa entity mapping để giải quyết việc compiler không thấy method.

### Lỗi liên kết runtime

Các triệu chứng như NoSuchMethodError hoặc AbstractMethodError có thể cho thấy:

- Consumer được biên dịch với một hệ phân cấp hoặc chữ ký khác.
- Runtime đang nạp phiên bản thư viện không tương thích.
- Một implementation tự viết chưa đáp ứng hợp đồng mới.
- Có artifact cũ hoặc dependency chồng chéo trong ứng dụng.

Không sửa bằng cách thêm một bản Spring Data Commons bất kỳ vào classpath.

Cần đồng bộ bộ phiên bản của Commons, module store, Spring Framework và nền tảng quản lý dependency tương ứng. Sau khi thay API, các module consumer và artifact liên quan cần được biên dịch lại theo quy trình của dự án.

### Lỗi tạo repository

Nếu compiler đã thấy method nhưng context thất bại, cần đọc cause theo nhóm khác:

- Không xác định được domain type.
- Base repository bị tạo độc lập.
- Domain chưa được store quản lý.
- Query method không có đường thực thi phù hợp.
- Fragment hoặc cấu hình factory không đúng.

Thêm cả CRUD và sorting không tự sửa các lỗi cấu hình đó.

## 12. Những gì thay đổi interface không tự thay đổi

| Khía cạnh | Không thể suy ra chỉ từ superinterface |
|---|---|
| Transaction | save, delete và nhiều repository có cùng transaction hay không |
| Mapping | Domain có thuộc persistence unit hoặc collection đúng không |
| Query support | Store có hỗ trợ mọi return type và query method mong muốn không |
| Hiệu năng | List, Page hoặc Slice có phù hợp workload không |
| Thứ tự | List có thứ tự đúng khi query chưa yêu cầu sort không |
| Auditing | Hạ tầng auditing đã được bật và đường ghi có đi qua nó không |
| Metadata | Generic, projection và ID type có được mô tả đúng không |
| Nhiều store | Repository được gán đúng factory và tài nguyên chưa |

Đặc biệt, ListCrudRepository không làm saveAll trở thành một bulk command duy nhất hoặc bảo đảm một transaction xuyên mọi store.

Tương tự, thêm PagingAndSortingRepository không tự làm count rẻ hơn hay tránh offset sâu.

Khi nâng phiên bản, các thay đổi về namespace, JDK baseline, driver hoặc cấu hình framework là những đầu việc liên quan nhưng riêng biệt. Không kết luận rằng sửa superinterface đã hoàn tất toàn bộ quá trình nâng nền tảng.

## 13. Kiểm thử hồi quy theo năng lực đang công khai

Một bộ kiểm thử phù hợp cần xác nhận các thao tác mà consumer thực sự sử dụng:

- CRUD được thừa kế đúng.
- findAll(Sort) áp dụng đúng thứ tự.
- findAll(Pageable) trả nội dung và metadata đúng.
- Các method dạng List có đúng chữ ký.
- Custom method và fragment vẫn được route đúng.
- Context tạo repository thực thành công.

Ví dụ sau dùng phương án ProductRepository kế thừa ListCrudRepository và ListPagingAndSortingRepository.

Entity tối thiểu:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product_record")
public class Product {

    @Id
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Test minh họa với JPA:

```java
import java.util.List;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("repository-test")
@Transactional
class ProductRepositoryMigrationTest {

    @Autowired
    ProductRepository products;

    @Autowired
    EntityManager entityManager;

    @BeforeEach
    void prepare() {
        products.deleteAll();

        products.saveAll(List.of(
                new Product(3L, "Mouse"),
                new Product(1L, "Cable"),
                new Product(2L, "Hub")));

        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void crudMethodsRemainAvailable() {
        Product saved = products.save(
                new Product(99L, "Temporary"));

        entityManager.flush();
        entityManager.clear();

        assertThat(products.findById(saved.getId()))
                .hasValueSatisfying(product ->
                        assertThat(product.getName())
                                .isEqualTo("Temporary"));

        products.deleteById(saved.getId());
        entityManager.flush();
        entityManager.clear();

        assertThat(products.findById(saved.getId())).isEmpty();
    }

    @Test
    void sortedReadHasTheListContract() {
        List<Product> sorted = products.findAll(
                Sort.by(Sort.Order.asc("id")));

        assertThat(sorted)
                .extracting(Product::getId)
                .containsExactly(1L, 2L, 3L);
    }

    @Test
    void pageableReadKeepsItsPageContract() {
        Page<Product> page = products.findAll(
                PageRequest.of(
                        1,
                        2,
                        Sort.by(Sort.Order.asc("id"))));

        assertThat(page.getContent())
                .extracting(Product::getId)
                .containsExactly(3L);

        assertThat(page.getNumber()).isEqualTo(1);
        assertThat(page.getSize()).isEqualTo(2);
        assertThat(page.getNumberOfElements()).isEqualTo(1);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void unsortedReadDoesNotInventAnOrder() {
        List<Product> all = products.findAll();

        assertThat(all)
                .extracting(Product::getId)
                .containsExactlyInAnyOrder(1L, 2L, 3L);
    }
}
```

Các ví dụ giả định profile repository-test dùng database kiểm thử riêng, entity và repository scan đúng, schema phù hợp và dữ liệu được cô lập.

Không chạy phần xóa fixture trên dữ liệu ứng dụng thật. Với store khác, dùng cách chuẩn bị và kiểm tra tương ứng thay vì EntityManager.

Mock repository không kiểm tra được toàn bộ việc tạo proxy, routing phương thức và thực thi query của module. Nó vẫn hữu ích cho service test, nhưng không thay thế nhóm kiểm thử tích hợp này.

## 14. Tác động với thư viện nội bộ và mã đã biên dịch

Repository interface có thể được công khai từ một module dùng chung. Khi đổi superinterface hoặc kiểu trả về, cần xem cả consumer ngoài module đó.

Ví dụ:

```text
Module persistence:
    ProductRepository

Module application:
    ProductService gọi save và findAll

Module integration:
    adapter hoặc fake implement một phần hợp đồng
```

Nếu chỉ cập nhật persistence nhưng giữ application hoặc adapter từ artifact cũ, ứng dụng có thể biên dịch hoặc liên kết không nhất quán.

Những câu hỏi cần giải quyết:

- Hợp đồng nào được công khai ra ngoài module?
- Consumer nào phụ thuộc vào CrudRepository qua quan hệ kế thừa cũ?
- Có method reference hoặc generic bound cũ không?
- Có implementation trả Iterable cần chuyển sang List không?
- Mọi artifact liên quan đã được dựng từ cùng bộ dependency chưa?

Nếu cần giữ tương thích trong một thời gian, có thể dùng một hợp đồng ứng dụng trung gian ổn định hoặc adapter có chủ đích. Không trộn tùy tiện hai thế hệ Commons để giữ cả hai hình dạng API.

## 15. AOT và native image cần metadata đúng ngay từ cấu hình

Thay đổi hierarchy ảnh hưởng tập phương thức, generic metadata và kiểu proxy mà hạ tầng repository xử lý.

Trong dự án có AOT:

- Repository cụ thể cần generic rõ ràng.
- Base interface cần vai trò đúng, thường có NoRepositoryBean nếu không được tạo độc lập.
- Các method tùy biến phải có đường thực thi phù hợp.
- Store và dependency phải tương thích.
- Artifact sinh từ cấu hình cũ cần được tái tạo theo quy trình build của dự án.

Không sửa trực tiếp generated source hoặc thêm runtime hint như cách vá một interface thiếu CrudRepository. Hints không bổ sung một phương thức không tồn tại trong hợp đồng Java.

Cũng không giả định một JVM integration test đã xác minh đầy đủ native image. Nếu native là mục tiêu triển khai, cần kiểm tra artifact native theo phạm vi chức năng quan trọng của dự án.

Việc ghép interface đúng là nền tảng cho metadata chính xác; nó không tự bảo đảm mọi feature động hoặc mọi custom implementation đều được AOT hỗ trợ.

## 16. Quy trình chuyển đổi có thể kiểm soát

Có thể thực hiện theo thứ tự:

1. Chọn bộ phiên bản mục tiêu tương thích cho toàn bộ nền tảng.
2. Liệt kê repository đang chỉ kế thừa sorting interface.
3. Xác định nơi consumer đang dùng CRUD nhờ quan hệ cũ.
4. Chọn giữ Iterable hay dùng các biến thể List.
5. Cập nhật base interface và repository cụ thể.
6. Cập nhật kiểu inject, generic bound và adapter liên quan.
7. Kiểm tra custom base class, fragment và fake.
8. Biên dịch lại các consumer cùng bộ dependency.
9. Khởi tạo context thật và kiểm tra CRUD, sort, paging.
10. Nếu có AOT/native, tái tạo và kiểm tra artifact tương ứng.

Không cần đổi mọi repository sang một superinterface lớn nhất. Mục tiêu là mỗi repository công khai đúng năng lực mà ứng dụng cần và store hỗ trợ.

Nếu gặp lỗi mới, phân loại nó theo compile, linkage, bootstrap hoặc thực thi query trước khi sửa. Một thông báo ở giai đoạn khác thường đòi hỏi giả thuyết khác.

## 17. Các lỗi chuyển đổi thường gặp

| Lỗi | Hướng xử lý |
|---|---|
| Chỉ giữ PagingAndSortingRepository nhưng vẫn gọi save | Ghép CRUD nếu hợp đồng cần, đồng thời sửa kiểu consumer |
| Dùng ListPagingAndSortingRepository để mong có CRUD | Ghép ListCrudRepository hoặc hợp đồng phù hợp |
| Dùng ListCrudRepository để mong có findAll(Pageable) | Ghép sorting/paging interface nếu cần |
| ProductRepository đã sửa nhưng service vẫn khai báo kiểu sorting | Cập nhật kiểu phụ thuộc |
| Cast Iterable thành List | Chọn hợp đồng List hoặc chuyển đổi có chủ đích |
| Custom implementation giữ return type quá rộng | Sửa chữ ký đáp ứng hợp đồng mới |
| Gắn NoRepositoryBean lên repository cụ thể | Giữ annotation ở tầng cơ sở không được tạo độc lập |
| Đổi mọi store sang JpaRepository | Chọn đúng họ interface theo store |
| Trộn Commons và module store khác thế hệ | Đồng bộ dependency theo nền tảng tương thích |
| Sửa generated AOT source để thêm method | Sửa hợp đồng nguồn rồi sinh lại theo quy trình |
| Dùng raw type để compiler bớt báo lỗi | Giữ generic đầy đủ và sửa nguyên nhân |
| Cho rằng List tự có thứ tự ổn định | Yêu cầu Sort khi thứ tự là hợp đồng |

## 18. Bài thực hành

Với một repository cũ đang dựa vào quan hệ sorting kế thừa CRUD:

1. Ghi lại các phương thức service đang gọi.
2. Vẽ hierarchy trước và sau khi tách CRUD/sorting.
3. Chuyển repository sang hợp đồng kết hợp đúng.
4. Tìm một consumer khai báo kiểu PagingAndSortingRepository và sửa yêu cầu phụ thuộc của nó.
5. Chọn các biến thể List nếu ứng dụng cần kiểu List.
6. Kiểm tra một method tùy biến hoặc fake có chịu ảnh hưởng chữ ký không.
7. Viết integration test xác nhận save, findById, sort và paging.
8. Kiểm tra một query không sort mà không áp đặt thứ tự ngầm.
9. Với dự án reactive hoặc coroutine, chọn đúng hai interface trong cùng họ.
10. Mô tả việc cần làm thêm khi repository được công khai qua thư viện hoặc được xử lý bằng AOT.

Mục tiêu là giải thích năng lực của từng interface và điểm mà consumer đang dựa vào, không chỉ sửa cho một dòng code hết báo lỗi.

## 19. Những điều cần nắm vững

Trong hệ phân cấp từ Spring Data 3.0, sorting và CRUD là các hợp đồng được tách riêng. Muốn có cả hai, hãy kết hợp rõ ràng hoặc dùng interface của module đã cung cấp đúng tổ hợp cần thiết.

Các biến thể List thay đổi kiểu collection của những method tương ứng, nhưng không tự thêm CRUD cho sorting, thêm paging cho CRUD hoặc giới hạn số dữ liệu được tải.

Một chuyển đổi đầy đủ cần cập nhật cả base repository, kiểu consumer, implementation tùy biến, bộ dependency và các artifact được biên dịch hoặc sinh từ metadata. Kiểm thử với store thật giúp xác nhận hợp đồng mới được thực hiện đúng.
