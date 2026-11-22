# @NoRepositoryBean và interface repository cơ sở dùng chung

Bài này nằm trong nhóm **Công bố repository** của Spring Data REST. Khi nhiều repository có cùng một nhóm thao tác, ta có thể gom các khai báo đó vào một interface generic rồi để repository cụ thể kế thừa. **@NoRepositoryBean** đánh dấu interface trung gian này để Spring Data không cố tạo một repository proxy riêng cho nó.

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận ra khi nào nên tạo một repository interface cơ sở dùng chung.
- Giải thích vì sao interface generic trung gian cần **@NoRepositoryBean**.
- Viết interface cơ sở có kiểu entity và kiểu ID tổng quát, rồi ràng buộc chúng ở repository cụ thể.
- Phân biệt việc Spring Data tạo repository bean với việc Spring Data REST công bố endpoint.
- Chọn đúng cách mở rộng khi cần phương thức truy vấn, logic dùng chung hoặc tùy chỉnh hành vi repository.

## 1. Bài toán: nhiều repository có cùng hợp đồng

Một ứng dụng thường có nhiều repository theo từng entity:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatus(OrderStatus status);
}

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByStatus(CustomerStatus status);
}
~~~

Các repository này có thể cần một số phương thức dùng chung, chẳng hạn tìm dữ liệu theo tenant, lấy bản ghi đang hoạt động hoặc áp dụng một quy ước truy cập dữ liệu thống nhất. Nếu sao chép cùng một khai báo vào nhiều interface, các thay đổi sau này dễ bị lệch giữa các repository.

Ta có thể tạo một interface cơ sở generic:

~~~java
public interface BaseRepository<T, ID> extends JpaRepository<T, ID> {
    // Các khai báo dùng chung cho nhiều entity
}
~~~

Nhưng Spring Data quét các repository interface trong phạm vi cấu hình. Interface trên vẫn mang hai biến kiểu **T** và **ID**, nên khi xét riêng nó, Spring Data chưa biết entity và kiểu khóa chính cụ thể để tạo repository proxy. Đây là lý do cần **@NoRepositoryBean**.

## 2. @NoRepositoryBean có tác dụng gì?

Import annotation:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
~~~

Đặt annotation trên interface trung gian mà Spring Data không được tạo instance trực tiếp:

~~~java
@NoRepositoryBean
public interface BaseRepository<T, ID> extends JpaRepository<T, ID> {
}
~~~

Ý nghĩa của annotation:

1. Spring Data vẫn nhận diện interface này là một phần của cây kế thừa repository.
2. Spring Data không tạo repository proxy riêng cho chính interface trung gian đó.
3. Repository cụ thể kế thừa interface này vẫn được phát hiện và tạo proxy khi nó khai báo đầy đủ entity và ID.
4. Các phương thức hợp lệ được kế thừa tiếp tục tham gia vào repository cụ thể.

Có thể hình dung cây kế thừa như sau:

~~~text
BaseRepository<T, ID>
  |  @NoRepositoryBean: không tạo repository riêng ở đây
  |
  +-- OrderRepository extends BaseRepository<Order, Long>
  |     -> repository proxy quản lý Order
  |
  +-- CustomerRepository extends BaseRepository<Customer, Long>
        -> repository proxy quản lý Customer
~~~

**@NoRepositoryBean không phải annotation để tắt repository nói chung.** Nó chỉ loại interface được đánh dấu khỏi việc tạo repository instance trực tiếp. Những interface con đã xác định kiểu cụ thể vẫn có thể được tạo như bình thường.

## 3. Ví dụ đầy đủ với repository dùng chung theo tenant

Giả sử các entity cần hỗ trợ truy vấn theo tenant đều có thuộc tính **tenantId**. Ta mô tả hợp đồng chung:

~~~java
public interface TenantOwned {
    UUID getTenantId();
}
~~~

Một entity có thể triển khai hợp đồng đó:

~~~java
@Entity
public class PurchaseOrder implements TenantOwned {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private UUID tenantId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Override
    public UUID getTenantId() {
        return tenantId;
    }
}
~~~

Tạo repository interface cơ sở:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface TenantScopedRepository<T extends TenantOwned, ID>
        extends JpaRepository<T, ID> {

    List<T> findAllByTenantId(UUID tenantId);
}
~~~

Các điểm cần chú ý:

- **T extends TenantOwned** giới hạn entity được dùng với repository này vào nhóm có hợp đồng tenant.
- **ID** vẫn tổng quát; mỗi repository cụ thể sẽ truyền kiểu khóa chính thực tế.
- **JpaRepository** cung cấp các thao tác JPA thông dụng như lưu, tìm, phân trang và xóa.
- **findAllByTenantId** là query method. Spring Data phân tích tên phương thức trong ngữ cảnh entity cụ thể của repository con.
- **@NoRepositoryBean** ngăn Spring Data tạo repository riêng cho interface còn chứa biến kiểu **T** và **ID**.

Repository cụ thể ràng buộc các kiểu tổng quát:

~~~java
import java.util.List;

import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface PurchaseOrderRepository
        extends TenantScopedRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Ở đây:

- **PurchaseOrder** là entity được quản lý.
- **Long** là kiểu ID.
- **PurchaseOrderRepository** là repository cụ thể mà Spring Data có thể tạo proxy.
- Repository con kế thừa cả thao tác JPA lẫn phương thức truy vấn theo tenant.
- **@RepositoryRestResource** đặt trên repository cụ thể để tùy chỉnh đường dẫn và tên liên kết khi Spring Data REST công bố repository.

Nếu Spring Data REST được cấu hình và repository đáp ứng chính sách phát hiện/công bố hiện hành, tài nguyên collection có thể được truy cập qua đường dẫn **/orders**. Phương thức truy vấn **findByStatus** có thể được công bố dưới tài nguyên tìm kiếm của repository theo quy tắc Spring Data REST.

> Ví dụ giả định mọi entity dùng **TenantScopedRepository** đều có thuộc tính persistent tên **tenantId**. Nếu một entity không có thuộc tính này, Spring Data có thể không tạo được query method cho repository tương ứng.

## 4. Chọn interface cơ sở nào để kế thừa?

Chọn interface theo tập thao tác mà repository cụ thể cần có:

| Interface | Khi nào dùng |
| --- | --- |
| **Repository<T, ID>** | Muốn chọn lọc những phương thức được đưa vào hợp đồng repository. Đây là marker interface tối thiểu của Spring Data. |
| **CrudRepository<T, ID>** | Cần các thao tác CRUD tổng quát. |
| **PagingAndSortingRepository<T, ID>** | Cần phân trang và sắp xếp. |
| **JpaRepository<T, ID>** | Repository dùng JPA và cần các tiện ích riêng của JPA. |
| **ReactiveCrudRepository<T, ID>** | Làm việc với repository theo mô hình reactive. |

Nếu interface cơ sở kế thừa **CrudRepository** hoặc **JpaRepository**, các phương thức CRUD tương ứng đã được kế thừa; không cần khai báo lại chỉ để có chúng.

Nếu muốn chỉ công bố một phần hợp đồng CRUD, có thể kế thừa **Repository<T, ID>** rồi khai báo những chữ ký cần thiết. Ví dụ:

~~~java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadWriteRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    <S extends T> S save(S entity);
}
~~~

Các chữ ký này khớp với những phương thức CRUD mà Spring Data hỗ trợ. Repository cụ thể kế thừa **ReadWriteRepository<Order, Long>** sẽ có hợp đồng đọc theo ID và lưu entity mà không cần kế thừa toàn bộ **CrudRepository**.

Cách này hữu ích khi muốn giới hạn bề mặt thao tác của repository. Cần kiểm tra chữ ký theo đúng phiên bản Spring Data và module lưu trữ đang dùng.

## 5. Nhiều tầng interface cơ sở

Một ứng dụng có thể chia hợp đồng thành nhiều tầng, ví dụ một tầng đọc chung và một tầng truy vấn theo tenant:

~~~java
@NoRepositoryBean
public interface ReadRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}

@NoRepositoryBean
public interface TenantRepository<T extends TenantOwned, ID>
        extends ReadRepository<T, ID> {

    List<T> findAllByTenantId(UUID tenantId);
}

public interface OrderRepository
        extends TenantRepository<Order, Long> {
}
~~~

Mỗi interface trung gian mà Spring Data không được tạo instance trực tiếp đều cần **@NoRepositoryBean**. Đánh dấu ở một tầng không thay thế cho việc đánh dấu các interface trung gian khác trong cây kế thừa.

Interface lá như **OrderRepository** không được đánh dấu **@NoRepositoryBean** nếu ta muốn Spring Data tạo repository bean cho nó.

## 6. @NoRepositoryBean và việc công bố REST là hai việc khác nhau

Đây là điểm quan trọng khi làm việc với Spring Data REST.

| Cơ chế | Trách nhiệm |
| --- | --- |
| **@NoRepositoryBean** | Ngăn Spring Data tạo repository instance trực tiếp cho interface trung gian generic. |
| **@RepositoryRestResource** | Tùy chỉnh cách một repository được công bố thành REST resource; cũng có thuộc tính **exported** để bật/tắt công bố. |
| **@RestResource** | Tùy chỉnh hoặc tắt công bố một phương thức hay quan hệ cụ thể. |
| **RepositoryDetectionStrategy** | Quy định repository nào đủ điều kiện được Spring Data REST phát hiện và công bố. |
| Spring Security | Kiểm soát người gọi nào được phép truy cập thao tác và dữ liệu. |

Ví dụ muốn repository cụ thể không xuất hiện như REST resource:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalOrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Ví dụ muốn giữ repository nhưng không công bố một query method:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @RestResource(exported = false)
    List<Order> findByInternalFlag(boolean internalFlag);
}
~~~

Không dùng **@NoRepositoryBean** để ẩn endpoint của repository con. Nếu một repository cụ thể vẫn được Spring Data tạo bean, Spring Data REST có thể công bố nó tùy theo dependency, cấu hình và detection strategy.

Cũng không xem việc tắt công bố REST là cơ chế phân quyền. Endpoint được công bố vẫn cần chính sách xác thực và phân quyền phù hợp; dữ liệu nhạy cảm cần được kiểm soát bằng security, projection và cấu hình export tương ứng.

## 7. Interface cơ sở không tự cung cấp implementation

**@NoRepositoryBean** chỉ điều khiển việc tạo repository instance. Annotation không viết code thực thi cho phương thức mới.

Spring Data có thể xử lý các nhóm phương thức khác nhau:

- **Phương thức CRUD chuẩn:** nếu chữ ký khớp với hợp đồng CRUD mà module hỗ trợ, Spring Data định tuyến tới implementation mặc định của module, chẳng hạn **SimpleJpaRepository** trong JPA.
- **Derived query method:** Spring Data phân tích tên phương thức và thuộc tính entity cụ thể, ví dụ **findAllByTenantId**.
- **Phương thức cần logic tùy chỉnh:** phải cung cấp implementation thông qua repository fragment, default method phù hợp hoặc custom repository base class.

Nếu cần thêm một thao tác dùng chung có logic riêng cho tất cả repository JPA, có thể cân nhắc custom base class kế thừa **SimpleJpaRepository** và cấu hình **repositoryBaseClass** trong **@EnableJpaRepositories**. Interface cơ sở chỉ định hợp đồng; custom base class mới cung cấp implementation dùng chung.

Nếu logic chỉ dùng ở một vài repository, repository fragment thường rõ ràng hơn việc đưa tất cả phương thức vào một base interface lớn.

## 8. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Ứng dụng lỗi khi khởi động vì Spring không xác định được entity hoặc ID cho interface generic | Interface trung gian chưa có **@NoRepositoryBean** | Đánh dấu tất cả interface trung gian cần loại khỏi việc tạo repository instance. |
| Repository cụ thể không được tạo bean | Interface lá bị đánh dấu **@NoRepositoryBean**, nằm ngoài phạm vi scan hoặc kế thừa sai loại repository | Bỏ annotation khỏi interface lá nếu cần bean; kiểm tra package scan và module repository. |
| Lỗi không tìm thấy thuộc tính khi tạo query | Query method ở base interface yêu cầu một thuộc tính không có trên entity cụ thể | Chỉ đặt derived query dùng chung khi mọi entity con đều có thuộc tính tương ứng; nếu không, chuyển phương thức xuống repository cụ thể hoặc dùng fragment. |
| Có interface cơ sở nhưng gọi phương thức mới bị lỗi | Chỉ khai báo chữ ký mà chưa có query phù hợp hoặc implementation tùy chỉnh | Dùng derived query hợp lệ, fragment, default method hoặc custom base class. |
| Repository con vẫn xuất hiện trong API | Nhầm **@NoRepositoryBean** với cơ chế tắt REST export | Dùng **@RepositoryRestResource(exported = false)**, **@RestResource(exported = false)** hoặc detection strategy phù hợp. |
| Repository không được bind đúng store khi ứng dụng dùng nhiều Spring Data module | Cây kế thừa chỉ dùng các interface generic chung, không đủ thông tin để phân biệt module | Dùng interface module-specific như **JpaRepository** hoặc cấu hình/kiểu domain đủ rõ để Spring Data chọn đúng module. |

## 9. Quy trình triển khai và kiểm tra

1. Xác định những phương thức thực sự giống nhau giữa các repository.
2. Chọn hợp đồng gốc: **Repository**, **CrudRepository**, **PagingAndSortingRepository** hay interface theo store.
3. Khai báo tham số kiểu **T** và **ID**; thêm ràng buộc kiểu nếu phương thức dùng chung yêu cầu thuộc tính hoặc hợp đồng của entity.
4. Đặt **@NoRepositoryBean** trên từng interface trung gian.
5. Tạo repository cụ thể và truyền entity cùng kiểu ID rõ ràng, ví dụ **OrderRepository extends TenantRepository<Order, Long>**.
6. Khởi động application context và xác nhận repository cụ thể được inject thành công.
7. Chạy kiểm thử persistence cho các phương thức kế thừa, đặc biệt là derived query dùng thuộc tính chung.
8. Nếu dùng Spring Data REST, kiểm thử đường dẫn và các query resource của repository cụ thể; kiểm tra riêng những repository hoặc phương thức được đặt **exported = false**.
9. Kiểm tra phân quyền độc lập với việc repository có được công bố hay không.

Khi viết test, lưu ý repository cụ thể kế thừa interface cơ sở nên bean cụ thể cũng có thể được gán cho kiểu interface cơ sở. Vì vậy, không nên kết luận rằng base interface đã được tạo thành một repository riêng chỉ bằng cách tìm bean theo kiểu cha; hãy kiểm tra repository metadata hoặc hành vi của repository cụ thể.

## 10. Checklist nhanh

- [ ] Base interface thực sự đại diện cho hợp đồng dùng chung.
- [ ] Entity và ID của repository cụ thể được ràng buộc rõ ràng.
- [ ] Mọi interface trung gian cần loại khỏi việc tạo instance đều có **@NoRepositoryBean**.
- [ ] Interface repository cụ thể không bị đánh dấu nhầm **@NoRepositoryBean**.
- [ ] Derived query chỉ dùng các thuộc tính tồn tại trên mọi entity áp dụng.
- [ ] Phương thức có logic riêng đã có fragment hoặc implementation tương ứng.
- [ ] Việc công bố REST được điều khiển bằng cấu hình Spring Data REST phù hợp.
- [ ] Security được cấu hình riêng, không dựa vào annotation loại repository.

## 11. Ghi nhớ

**@NoRepositoryBean** cho phép dùng một interface generic làm tầng hợp đồng chung trong cây repository mà không yêu cầu Spring Data tạo repository proxy cho chính tầng đó. Khi interface con cung cấp entity và ID cụ thể, Spring Data vẫn có thể tạo repository tương ứng.

Trong bài toán Spring Data REST, hãy tách rõ hai câu hỏi:

- Spring Data có tạo repository bean cho interface này không?
- Spring Data REST có công bố repository bean đó thành REST resource không?

Câu hỏi thứ nhất liên quan đến **@NoRepositoryBean** và cấu hình repository. Câu hỏi thứ hai liên quan đến **@RepositoryRestResource**, **@RestResource** và repository detection strategy.

## Tài liệu tham khảo

- Spring Data JPA — Defining Repository Interfaces: https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html
- Spring Data REST — Getting Started và Repository Detection Strategy: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
- Spring Data REST — RepositoryRestResource API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html
- Spring Data Commons — Repository API: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/Repository.html
- Spring Data Commons — NoRepositoryBean API: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/NoRepositoryBean.html
