# Projection động với tham số Class<T>

## 1. Projection động là gì?

Projection động (dynamic projection) cho phép chọn kiểu dữ liệu trả về của một repository method tại thời điểm gọi. Cùng một điều kiện truy vấn có thể trả về Entity đầy đủ, một interface projection hoặc một DTO class/record tùy theo `Class<T>` được truyền vào.

Điểm chính là repository chỉ cần khai báo một method tổng quát. Caller quyết định hình dạng dữ liệu cần nhận thay vì tạo một method riêng cho từng projection.

Dynamic projection thay đổi **hình dạng kết quả**. Nó không tự thay đổi điều kiện lọc, sort, join hay logic nghiệp vụ của query. Nếu cần thay đổi predicate theo tham số, hãy kết hợp với Specification, Querydsl hoặc custom query phù hợp.

## 2. Cấu trúc repository với Class<T>

Giả sử Entity `Customer` có các thuộc tính `id`, `firstName`, `lastName`, `email` và `status`. Repository có thể khai báo:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    <T> List<T> findByLastName(String lastName, Class<T> projectionType);
}
```

Spring Data nhận diện tham số `Class<T>` là projection selector vì generic type `T` của tham số Class khớp với generic type `T` trong kiểu trả về `List<T>`. Khi gọi method, framework dùng class được truyền để quyết định cách chiếu kết quả.

Ví dụ ba kiểu kết quả:

```java
List<Customer> entities =
    repository.findByLastName("Nguyen", Customer.class);

List<CustomerNameView> names =
    repository.findByLastName("Nguyen", CustomerNameView.class);

List<CustomerSummary> summaries =
    repository.findByLastName("Nguyen", CustomerSummary.class);
```

Cả ba lời gọi dùng cùng điều kiện `lastName = "Nguyen"`. Khác biệt nằm ở kiểu kết quả được yêu cầu.

## 3. Dùng interface projection

Closed interface projection chỉ khai báo các accessor cần thiết:

```java
public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
}
```

Gọi repository:

```java
List<CustomerNameView> result =
    repository.findByLastName("Nguyen", CustomerNameView.class);

for (CustomerNameView customer : result) {
    System.out.println(customer.getFirstName() + " " + customer.getLastName());
}
```

Spring Data tạo projection phù hợp với interface. Accessor phải khớp tên property Java của Entity: `getFirstName()` ánh xạ tới `firstName`, không phải tên cột vật lý `first_name`.

Với closed projection, framework biết tập property được yêu cầu và có thể tối ưu truy vấn để chỉ lấy dữ liệu cần thiết. Nested projection hoặc open projection có SpEL có thể làm giảm khả năng tối ưu này; hãy kiểm tra SQL thực tế.

## 4. Dùng DTO class hoặc record

Dynamic projection cũng có thể chọn một DTO class. DTO cần constructor phù hợp với dữ liệu được chọn; Java record là lựa chọn gọn vì có canonical constructor tự sinh:

```java
public record CustomerSummary(
    Long id,
    String firstName,
    String lastName
) {
}
```

Gọi repository:

```java
List<CustomerSummary> summaries =
    repository.findByLastName("Nguyen", CustomerSummary.class);
```

Với DTO class thông thường, Spring Data cần xác định constructor dùng để tạo kết quả. Nếu có nhiều constructor, đánh dấu constructor phù hợp bằng `@PersistenceCreator` theo yêu cầu của Spring Data. Các tham số constructor phải tương thích với property được chiếu về số lượng, thứ tự và kiểu.

Không nhầm dynamic projection với việc tự động map bất kỳ class nào. Kiểu được truyền phải là Entity hoặc projection hợp lệ cho query; DTO không có constructor tương thích sẽ gây lỗi khi tạo hoặc thực thi truy vấn.

## 5. Dùng Entity làm kiểu kết quả

Truyền `Customer.class` để nhận Entity đầy đủ:

```java
List<Customer> customers =
    repository.findByLastName("Nguyen", Customer.class);
```

Trong trường hợp này, kết quả là Entity `Customer` được quản lý theo quy tắc persistence context của JPA. Caller có thể sử dụng các thuộc tính và quan hệ Entity, nhưng cần lưu ý lazy loading, dirty checking và việc serialize Entity trực tiếp ra API.

Khi chỉ đọc dữ liệu cho danh sách hoặc response, interface projection/DTO thường giúp giới hạn dữ liệu và tách hợp đồng API khỏi Entity.

## 6. Vì sao generic Class<T> được framework nhận diện?

Chữ ký quan trọng là:

```java
<T> List<T> findByLastName(String lastName, Class<T> projectionType);
```

Spring Data xem `Class<T>` là dynamic projection parameter khi generic `T` của tham số Class khớp với generic type của kết quả query method. Framework dùng giá trị này để chọn projection và không xem nó như bind parameter thông thường của query.

Do đó, trong một query có named parameter, không thể mặc định dùng chính projection selector `Class<T>` như `:type` trong JPQL hoặc như một giá trị trong SpEL. Nó được dành cho cơ chế projection.

## 7. Phân biệt Class<T> và Class<?>

Đôi khi repository thực sự cần nhận một đối tượng Class như tham số truy vấn. Khi đó cần tránh để Spring Data nhận diện nó như dynamic projection selector.

- `Class<T>` có generic `T` khớp với kiểu trả về `T`: Spring Data có thể nhận diện là projection parameter.
- `Class<?>` không gắn generic với kiểu trả về theo cách đó: framework không nhận diện nó là dynamic projection selector chỉ từ tham số này, nên có thể được xem như tham số query thông thường.

Ví dụ chữ ký tổng quát:

```java
<T> List<T> findByLastNameAndEntityType(
    String lastName,
    Class<?> entityType,
    Class<T> projectionType
);
```

Trong ví dụ này, `projectionType` chọn kiểu kết quả; `entityType` là tham số Class riêng. Nếu bind Class vào JPQL/native query, phải kiểm tra biểu thức, kiểu parameter và hỗ trợ của JPA provider/database. Không phải vị trí nào trong JPQL cũng chấp nhận Class như một giá trị.

Quy tắc thực tế: dùng `Class<T>` cho projection động; dùng `Class<?>` khi Class phải là một tham số dữ liệu bình thường và query/provider hỗ trợ kiểu đó.

## 8. Kết hợp với @Query

Dynamic projection chủ yếu được thể hiện rõ nhất với derived query. Có thể dùng projection với các repository query khai báo, nhưng phải bảo đảm câu query và kiểu kết quả tương thích. Với JPQL, query cần trả về Entity hoặc các expression mà projection có thể ánh xạ; với DTO constructor expression, số lượng, thứ tự và kiểu tham số phải khớp constructor.

Ví dụ query trả Entity root để framework áp dụng projection:

```java
@Query("select c from Customer c where c.lastName = :lastName")
<T> List<T> searchByLastName(
    @Param("lastName") String lastName,
    Class<T> projectionType
);
```

Khi dùng native query, alias cột, kiểu dữ liệu và cách provider chuyển kết quả thành interface/DTO cần được kiểm thử trên database thực tế. Native projection phức tạp có thể cần result-set mapping hoặc custom repository thay vì kỳ vọng framework tự suy luận mọi mapping.

Không khai báo constructor expression cố định cho một DTO rồi kỳ vọng cùng câu query tự chuyển thành interface hoặc Entity bất kỳ. Một constructor expression đã khóa hình dạng kết quả; hãy thiết kế query tương ứng với các kiểu projection thực sự hỗ trợ.

## 9. Dynamic projection không phải dynamic filtering

Hai nhu cầu thường bị nhầm:

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Cùng filter nhưng caller chọn Entity, interface hoặc DTO | Dynamic projection `Class<T>` |
| Filter có thể có hoặc không theo request | Specification hoặc Querydsl |
| Điều kiện query cố định, cần JPQL rõ | `@Query` |
| SQL đặc thù database | Native query/custom repository |

Ví dụ, `findByLastName("Nguyen", CustomerNameView.class)` vẫn lọc theo last name. Nó không cho phép caller truyền một tên cột tùy ý để thay đổi WHERE. Để thay đổi điều kiện, xây dựng predicate riêng theo input đã được kiểm tra.

## 10. Kết hợp với Page, Slice và các kiểu trả về

Dynamic projection có thể kết hợp với các kiểu kết quả repository phù hợp như `List<T>`, `Collection<T>`, `Page<T>` hoặc `Slice<T>`:

```java
<T> Page<T> findByStatus(
    CustomerStatus status,
    Class<T> projectionType,
    Pageable pageable
);
```

Caller có thể yêu cầu:

```java
Page<CustomerNameView> page = repository.findByStatus(
    CustomerStatus.ACTIVE,
    CustomerNameView.class,
    PageRequest.of(0, 20)
);
```

`Page<T>` cung cấp tổng số phần tử và có thể phát sinh count query; `Slice<T>` chỉ cần biết còn trang tiếp theo hay không. Nếu query có join, distinct hoặc group, cần kiểm tra count query và pagination. Dynamic projection không giải quyết các vấn đề phân trang collection fetch join.

Với `Stream<T>`, phải chú ý transaction và đóng stream đúng cách; không giữ stream repository mở ngoài vòng đời transaction.

## 11. Giới hạn và lưu ý hiệu năng

- Mỗi projection type phải tương thích với Entity/query. Không thể truyền một class bất kỳ và kỳ vọng Spring Data tự biết cách tạo.
- Interface projection phụ thuộc accessor/property name và alias khi query trả tuple/scalar.
- DTO class phụ thuộc constructor và kiểu tham số.
- Nested projection có thể tải thêm dữ liệu qua association join; kiểm tra SQL để xác nhận cột thực tế.
- Open projection dùng SpEL có thể hạn chế tối ưu chọn cột vì framework không biết chính xác property cần truy cập.
- Truy vấn trả Entity có thể kích hoạt lazy loading hoặc dirty checking; projection DTO/interface thường phù hợp hơn cho read-only use case.
- Chọn kiểu kết quả ở runtime không làm query tự nhanh hơn. Đo SQL, số cột, số hàng và execution plan.

## 12. Không để client chọn class tùy ý

Tham số `Class<T>` nên được chọn bởi code ứng dụng từ các projection đã được cho phép. Không nhận tên class tùy ý từ HTTP request rồi dùng reflection để nạp class và truyền thẳng vào repository.

Nếu API cần cho client lựa chọn định dạng response, dùng một giá trị enum/string allow-list và ánh xạ trong service:

```java
public enum CustomerViewType {
    NAME,
    SUMMARY
}
```

```java
public Object search(String lastName, CustomerViewType viewType) {
    return switch (viewType) {
        case NAME -> repository.findByLastName(
            lastName, CustomerNameView.class
        );
        case SUMMARY -> repository.findByLastName(
            lastName, CustomerSummary.class
        );
    };
}
```

Đây là đoạn minh họa service; trong ứng dụng thực tế có thể dùng kiểu trả về chung hoặc response wrapper rõ ràng thay cho `Object`. Allow-list giữ quyền lựa chọn projection trong phạm vi mà API hỗ trợ.

## 13. Kiểm thử dynamic projection

Integration test nên kiểm tra từng kiểu projection trên cùng một tập dữ liệu:

1. Gọi method với `Customer.class`, xác nhận Entity và các thuộc tính cần thiết.
2. Gọi với closed interface projection, xác nhận từng accessor trả đúng giá trị.
3. Gọi với DTO record/class, xác nhận constructor mapping đúng thứ tự và kiểu.
4. Kiểm tra không có bản ghi, nhiều bản ghi, giá trị null và dữ liệu trùng.
5. Nếu dùng `Page<T>`, kiểm tra nội dung, tổng số, sort và count query.
6. Xem SQL thực tế để xác nhận projection lấy lượng cột phù hợp.
7. Nếu dùng `@Query` hoặc native SQL, chạy test trên database/provider mục tiêu.

Test không chỉ xác nhận repository trả đúng số lượng phần tử; cần gọi các accessor hoặc đọc các component của DTO để phát hiện lỗi mapping.

## 14. Lỗi thường gặp và cách xử lý

**Class<T> không được nhận diện là dynamic projection.** Kiểm tra generic `T` trong tham số `Class<T>` có khớp với generic type của kết quả method hay không.

**Muốn bind projection Class vào query nhưng parameter không tồn tại.** Framework đã tiêu thụ `Class<T>` làm projection selector. Nếu cần Class như dữ liệu query, dùng `Class<?>` và bind theo biểu thức được provider hỗ trợ.

**Interface accessor trả null.** Kiểm tra accessor có khớp property Java hoặc alias projection hay không; không dùng tên cột vật lý thay cho property.

**DTO không tạo được.** Kiểm tra constructor, số lượng tham số, thứ tự và kiểu; với nhiều constructor, đánh dấu constructor được chọn bằng `@PersistenceCreator`.

**Native projection lỗi trên database khác.** Kiểm tra alias, case folding, kiểu dữ liệu và result-set mapping.

**Projection trả nhiều dữ liệu hơn mong đợi.** Xem có nested association hoặc open projection/SpEL không; kiểm tra SQL và cân nhắc DTO query tường minh.

**Page tổng số không chính xác.** Kiểm tra count query, join, distinct và group độc lập với projection type.

## 15. Checklist sử dụng Class<T>

- Khai báo method generic `<T> List<T> find...( ..., Class<T> projectionType)`.
- Chọn Entity, closed interface projection hoặc DTO class/record phù hợp.
- Bảo đảm accessor trùng property Java; alias query trùng tên projection.
- Với DTO, bảo đảm constructor tương thích; dùng `@PersistenceCreator` nếu cần chỉ rõ.
- Dùng `Class<?>` nếu Class phải là tham số query thông thường, không phải projection selector.
- Không nhầm chọn kiểu kết quả với thay đổi điều kiện lọc.
- Allow-list projection type khi lựa chọn xuất phát từ API.
- Kiểm thử từng projection và xem SQL thực tế.

Dynamic projection với `Class<T>` giúp một repository method phục vụ nhiều hình dạng kết quả mà vẫn giữ điều kiện truy vấn thống nhất. Dùng generic đúng cách, chọn projection có chủ đích và kiểm thử mapping giúp code gọi repository linh hoạt mà không làm mờ hợp đồng dữ liệu.