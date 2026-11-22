# Giao dịch mặc định của CRUD và phương thức truy vấn tự khai báo

Spring Data JPA cung cấp sẵn các phương thức CRUD qua `CrudRepository`, `PagingAndSortingRepository` và `JpaRepository`. Những phương thức này có cấu hình giao dịch mặc định trong lớp triển khai `SimpleJpaRepository`. Ngược lại, các phương thức truy vấn do ứng dụng khai báo, chẳng hạn phương thức dẫn xuất từ tên hàm hoặc phương thức dùng `@Query`, không tự động có cấu hình giao dịch. Hiểu rõ khác biệt này giúp xác định đúng ranh giới giao dịch, tránh ghi dữ liệu không được commit, lỗi khi cập nhật hàng loạt và các vấn đề với lazy loading.

## 1. Giao dịch mặc định của các phương thức CRUD

Trong Spring Data JPA, `SimpleJpaRepository` được cấu hình ở cấp lớp với `@Transactional(readOnly = true)`. Các thao tác đọc kế thừa từ repository, chẳng hạn `findById()`, `findAll()`, `existsById()` và `count()`, vì vậy chạy trong giao dịch chỉ đọc.

Các thao tác thay đổi dữ liệu như `save()`, `saveAll()`, `deleteById()`, `delete()`, `deleteAll()` và các biến thể ghi khác được đánh dấu `@Transactional` mà không đặt `readOnly = true`. Chúng chạy trong giao dịch có thể ghi dữ liệu.

| Nhóm phương thức | Ví dụ | Cấu hình mặc định |
|---|---|---|
| Đọc | `findById`, `findAll`, `count`, `existsById` | `@Transactional(readOnly = true)` |
| Ghi | `save`, `saveAll`, `delete`, `deleteAll` | `@Transactional` |
| Truy vấn tự khai báo | `findByStatus`, `findRecentOrders` | Không có cấu hình giao dịch mặc định |

Ví dụ repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Khi gọi trực tiếp `repository.findById(id)`, Spring Data JPA mở hoặc tham gia một giao dịch chỉ đọc theo cấu hình của phương thức CRUD. Khi gọi `repository.save(order)`, phương thức chạy trong giao dịch ghi. Nếu không có giao dịch bên ngoài, giao dịch do phương thức repository tạo ra thường kết thúc khi lời gọi phương thức hoàn tất.

Lưu ý: `save()` không đồng nghĩa với việc câu lệnh SQL chắc chắn được gửi xuống cơ sở dữ liệu ngay tại dòng lệnh đó. JPA có thể trì hoãn thao tác ghi đến lúc flush hoặc commit. Nếu phương thức repository tham gia một giao dịch lớn hơn, commit chỉ diễn ra khi giao dịch bên ngoài kết thúc.

## 2. Phương thức truy vấn tự khai báo không tự mở giao dịch

Spring Data JPA không tự áp dụng cấu hình giao dịch của các phương thức CRUD kế thừa cho mọi phương thức mới được khai báo trong interface repository. Điều này áp dụng cho cả:

- Derived query: Spring phân tích tên phương thức, ví dụ `findByStatus()`, `findByCreatedAtAfter()`.
- JPQL hoặc native query khai báo bằng `@Query`.
- Named query được Spring Data JPA tìm thấy theo quy ước.

Ví dụ:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    @Query("""
        select p
        from PurchaseOrder p
        where p.status = :status
        order by p.createdAt desc
        """)
    List<PurchaseOrder> findRecentByStatus(
            @Param("status") OrderStatus status);
}
```

Hai phương thức trên không có ranh giới giao dịch riêng chỉ vì chúng nằm trong repository interface. Chúng vẫn có thể chạy bên trong giao dịch do service hoặc thành phần gọi bên ngoài mở. Nếu được gọi độc lập, ứng dụng không nên dựa vào giả định rằng Spring Data JPA sẽ tự tạo giao dịch cho chúng.

Một truy vấn đọc đơn giản đôi khi vẫn trả kết quả khi không có giao dịch tường minh. Tuy nhiên, việc thiếu ranh giới giao dịch có thể gây vấn đề khi cần đọc dữ liệu nhất quán qua nhiều thao tác, truy cập quan hệ lazy sau khi persistence context đóng, hoặc dùng API yêu cầu giao dịch đang hoạt động. Vì vậy, hãy khai báo rõ ý định giao dịch tại service hoặc tại phương thức repository.

Có thể đặt cấu hình trực tiếp trên phương thức truy vấn:

```java
@Transactional(readOnly = true)
List<PurchaseOrder> findByStatus(OrderStatus status);
```

Hoặc đặt `@Transactional(readOnly = true)` ở cấp interface repository để áp dụng cho các phương thức truy vấn được khai báo tại đó. Với phương thức ghi cần cấu hình khác, đặt `@Transactional` trực tiếp trên phương thức để thể hiện rõ ý định.

## 3. Đặt ranh giới giao dịch ở tầng service

Trong ứng dụng thực tế, một nghiệp vụ thường gọi nhiều phương thức repository. Nếu mỗi lần gọi repository tự mở và kết thúc một giao dịch riêng, các bước có thể commit độc lập. Khi bước sau thất bại, dữ liệu do bước trước ghi có thể đã được commit và không thể rollback cùng nhau.

Cách phổ biến là đặt `@Transactional` trên phương thức service đại diện cho một nghiệp vụ. Mặc định, propagation là `REQUIRED`: nếu đã có giao dịch phù hợp thì tham gia giao dịch đó; nếu chưa có thì tạo giao dịch mới.

Ví dụ dưới đây minh họa các phần khai báo trong một project Spring Boot và Spring Data JPA. Các đoạn code không phải một file Java độc lập.

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

```java
@Service
@RequiredArgsConstructor
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    @Transactional
    public void markAsPaid(Long orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found: " + orderId));

        order.markPaid();

        // Entity đang được quản lý trong persistence context.
        // Dirty checking có thể ghi thay đổi khi flush/commit.
        // Gọi save() vẫn hợp lệ nếu muốn thể hiện rõ thao tác lưu.
        orders.save(order);
    }

    @Transactional(readOnly = true)
    public List<PurchaseOrder> findNewOrders() {
        return orders.findByStatus(OrderStatus.NEW);
    }
}
```

Trong `markAsPaid()`, lời gọi `findById()` và `save()` tham gia cùng giao dịch service nhờ propagation mặc định `REQUIRED`. Nếu có lỗi làm giao dịch rollback trước khi commit, thay đổi trạng thái đơn hàng cũng được rollback. Entity được tải trong giao dịch đang hoạt động được quản lý bởi persistence context; khi thay đổi thuộc tính, JPA có thể phát hiện thay đổi bằng dirty checking, vì vậy lời gọi `save()` sau khi tải entity thường không bắt buộc về mặt kỹ thuật. Tuy nhiên, dùng `save()` có thể giúp ý định lưu dữ liệu dễ đọc hơn.

Nếu chỉ gọi `save()` rồi gọi một phương thức truy vấn ở hai lời gọi độc lập mà không có service transaction bao quanh, hai thao tác có thể thuộc hai giao dịch khác nhau. Khi nghiệp vụ cần tính nguyên tử, hãy bao cả chuỗi thao tác trong một phương thức service có `@Transactional`.

## 4. Ý nghĩa của readOnly

`@Transactional(readOnly = true)` đánh dấu giao dịch là chỉ đọc. Đây là một gợi ý tối ưu cho transaction manager, JDBC driver và JPA provider; nó không phải cơ chế phân quyền bảo đảm mọi lệnh ghi đều bị chặn.

Với Hibernate, giao dịch chỉ đọc có thể giúp giảm chi phí theo dõi thay đổi, chẳng hạn bỏ qua một số bước dirty checking. Chi tiết tối ưu phụ thuộc vào provider và cấu hình.

Nên dùng `readOnly = true` cho các nghiệp vụ chỉ truy vấn:

```java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return orders.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException("Order not found: " + id));
}
```

Không nên sửa entity rồi trông đợi thay đổi được lưu trong một giao dịch chỉ đọc. Một số cấu hình provider có thể không flush các thay đổi như mong đợi. Hãy dùng giao dịch ghi cho nghiệp vụ thay đổi dữ liệu.

Khi một phương thức service có `@Transactional(readOnly = true)` gọi một phương thức CRUD ghi, phương thức repository thường tham gia giao dịch đang có do propagation `REQUIRED`. Cấu hình của giao dịch bên ngoài quyết định thuộc tính thực tế của giao dịch đang chạy. Vì vậy, không nên gọi thao tác ghi bên trong một service transaction chỉ đọc.

## 5. Giao dịch cho phương thức @Query cập nhật hoặc xóa

`@Query` thường dùng để khai báo câu truy vấn. Với JPQL `UPDATE` hoặc `DELETE`, cần thêm `@Modifying` để Spring Data JPA thực thi truy vấn như một thao tác thay đổi dữ liệu.

`@Modifying` không tự tạo giao dịch. Phương thức vẫn phải chạy trong một giao dịch đang hoạt động, thường được cung cấp bởi service hoặc bởi `@Transactional` đặt trực tiếp trên phương thức repository.

Ví dụ:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") OrderStatus status);
}
```

Đặt ranh giới giao dịch tại service:

```java
@Transactional
public int changeOrderStatus(Long id, OrderStatus status) {
    return orders.updateStatus(id, status);
}
```

Nếu muốn phương thức repository tự xác định ranh giới giao dịch khi được gọi độc lập, có thể đặt `@Transactional` ngay trên phương thức:

```java
@Modifying
@Transactional
@Query("""
    delete from PurchaseOrder p
    where p.status = :status
    """)
int deleteByStatus(@Param("status") OrderStatus status);
```

Chọn một vị trí phù hợp với ranh giới nghiệp vụ. Khi service đã có giao dịch, phương thức repository dùng propagation mặc định sẽ tham gia giao dịch đó.

Các tùy chọn trong ví dụ:

- `flushAutomatically = true`: yêu cầu flush persistence context trước khi chạy truy vấn cập nhật hàng loạt, giúp đẩy các thay đổi đang chờ xuống cơ sở dữ liệu trước truy vấn.
- `clearAutomatically = true`: xóa persistence context sau khi truy vấn chạy để tránh tiếp tục dùng entity đang giữ dữ liệu cũ. Các entity đã tải có thể trở thành detached sau thao tác này.

Truy vấn cập nhật/xóa hàng loạt tác động trực tiếp lên cơ sở dữ liệu và không đồng bộ từng entity đang được quản lý như thao tác thay đổi entity thông thường. Vì thế, persistence context có thể chứa dữ liệu cũ. Ngoài ra, bulk update không thực hiện đầy đủ vòng đời entity như khi sửa từng entity; cần cân nhắc callback, optimistic locking và trường `@Version` nếu nghiệp vụ phụ thuộc vào chúng.

## 6. Propagation và thứ tự ưu tiên cấu hình

Propagation mặc định của `@Transactional` là `Propagation.REQUIRED`. Khi service gọi repository, giao dịch repository thường tham gia giao dịch service đang hoạt động thay vì mở một giao dịch độc lập.

Ví dụ:

```java
@Transactional
public void completeOrder(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.markPaid();
    orders.save(order);

    auditRepository.save(
            new OrderAudit(id, "PAID")
    );
}
```

Nếu hai repository tham gia cùng transaction manager và cùng giao dịch, thay đổi đơn hàng và bản ghi audit được commit hoặc rollback cùng nhau.

Khi một phương thức có giao dịch bên ngoài gọi phương thức bên trong dùng `REQUIRED`, cấu hình của giao dịch bên ngoài chi phối giao dịch đang chạy. Ví dụ, `@Transactional(readOnly = true)` ở service không tự biến thành giao dịch ghi chỉ vì một repository method bên trong có `@Transactional` thông thường. Hãy thiết kế ranh giới service nhất quán với loại thao tác cần thực hiện.

Các thuộc tính khác như isolation, timeout và rollback rule cũng có thể khai báo trong `@Transactional`. Nếu không chỉ định, Spring dùng giá trị mặc định của transaction manager và hệ quản trị cơ sở dữ liệu. Không nên tự giả định mức isolation cụ thể giống nhau ở mọi môi trường.

## 7. Quy tắc rollback mặc định

Theo mặc định của Spring, giao dịch rollback khi phương thức giao dịch kết thúc bằng `RuntimeException` hoặc `Error`. Checked exception không tự động làm rollback theo quy tắc mặc định.

Ví dụ:

```java
@Transactional
public void createOrder() throws IOException {
    orders.save(new PurchaseOrder());

    throw new IOException("Cannot write audit file");
}
```

Với cấu hình rollback mặc định, `IOException` là checked exception nên giao dịch không tự động rollback chỉ vì ngoại lệ này. Nếu nghiệp vụ yêu cầu rollback, khai báo rõ:

```java
@Transactional(rollbackFor = IOException.class)
public void createOrder() throws IOException {
    orders.save(new PurchaseOrder());

    throw new IOException("Cannot write audit file");
}
```

Có thể dùng `noRollbackFor` khi một loại ngoại lệ được phép kết thúc phương thức mà không rollback. Hãy chọn rule theo yêu cầu nhất quán dữ liệu của nghiệp vụ.

## 8. Những lỗi thường gặp

**Cho rằng mọi phương thức trong repository đều có transaction mặc định.** Các CRUD method kế thừa có cấu hình từ `SimpleJpaRepository`, nhưng derived query và phương thức `@Query` tự khai báo không tự có cấu hình đó. Hãy đặt `@Transactional` tại service hoặc trên phương thức truy vấn.

**Dùng @Modifying mà quên transaction.** `@Modifying` chỉ thay đổi cách Spring Data thực thi truy vấn. Nếu không có giao dịch đang hoạt động, câu lệnh cập nhật/xóa có thể thất bại với lỗi yêu cầu transaction.

**Chia một nghiệp vụ thành nhiều transaction ngoài ý muốn.** Nếu mỗi lần gọi repository tự mở transaction, một bước có thể đã commit trước khi bước tiếp theo lỗi. Hãy bao các bước cần nguyên tử trong một service method.

**Đặt readOnly cho nghiệp vụ có ghi dữ liệu.** Đây là tín hiệu tối ưu chứ không phải hàng rào an toàn. Provider có thể bỏ qua flush hoặc tối ưu theo hướng chỉ đọc. Dùng giao dịch ghi khi cần thay đổi dữ liệu.

**Đọc entity rồi truy cập quan hệ lazy sau khi transaction kết thúc.** Khi persistence context không còn hoạt động, việc khởi tạo quan hệ lazy có thể gây `LazyInitializationException`. Hãy tải dữ liệu cần thiết trong transaction, dùng fetch join/entity graph hoặc chuyển kết quả sang DTO phù hợp.

**Cho rằng save() luôn gửi SQL ngay lập tức.** JPA có thể trì hoãn ghi đến flush/commit. Nếu cần phát hiện lỗi ràng buộc sớm trong luồng xử lý, có thể dùng `saveAndFlush()` hoặc `flush()` khi phù hợp; thao tác flush vẫn không thay thế commit.

**Gọi phương thức transactional qua self-invocation.** Trong cấu hình proxy phổ biến, lời gọi `this.otherMethod()` bên trong cùng bean không đi qua Spring proxy, nên annotation trên phương thức được gọi có thể không được áp dụng như mong đợi. Đặt ranh giới giao dịch tại phương thức được gọi từ bean khác hoặc thiết kế lại cấu trúc service.

**Dựa vào transaction trong kiểm thử repository.** Các bài kiểm thử dùng `@DataJpaTest` thường chạy trong transaction và rollback sau test. Điều đó không chứng minh rằng một derived query được gọi ngoài test sẽ tự có transaction.

## 9. Cách lựa chọn cấu hình

| Tình huống | Cách cấu hình phù hợp |
|---|---|
| Gọi CRUD đơn lẻ | Dùng transaction mặc định của phương thức CRUD |
| Một nghiệp vụ gọi nhiều repository | Đặt `@Transactional` ở service method |
| Service chỉ truy vấn | Dùng `@Transactional(readOnly = true)` |
| Derived query hoặc `@Query` cần transaction riêng | Đặt `@Transactional` ở phương thức hoặc interface repository |
| JPQL/native UPDATE hoặc DELETE | Dùng `@Modifying` và bảo đảm có transaction |
| Checked exception phải rollback | Khai báo `rollbackFor` |
| Bulk update có entity đã tải trong persistence context | Cân nhắc flush trước và clear sau truy vấn |

## 10. Quy trình kiểm tra khi giao dịch hoạt động sai

1. Xác định phương thức được gọi là CRUD kế thừa hay query method tự khai báo.
2. Kiểm tra lời gọi có đi qua Spring bean/proxy hay không.
3. Xác định service nào đang mở transaction và propagation có tham gia giao dịch đó không.
4. Kiểm tra giao dịch có bị đánh dấu chỉ đọc trong khi nghiệp vụ cần ghi hay không.
5. Với UPDATE/DELETE dùng `@Query`, xác nhận có `@Modifying` và có transaction đang hoạt động.
6. Kiểm tra loại exception và rollback rule.
7. Với dữ liệu cũ sau bulk update, kiểm tra persistence context và cân nhắc `clearAutomatically`.
8. Kiểm tra thời điểm flush/commit thay vì kết luận rằng `save()` đã ghi ngay xuống cơ sở dữ liệu.

## Kết luận

Spring Data JPA đã cấu hình giao dịch cho CRUD method kế thừa: thao tác đọc mặc định là chỉ đọc, thao tác ghi dùng giao dịch có thể ghi. Phương thức truy vấn tự khai báo cần được cấu hình rõ khi cần transaction. Với nghiệp vụ gồm nhiều bước, service là nơi thích hợp để xác định một ranh giới giao dịch thống nhất; `@Modifying` chỉ định cách thực thi truy vấn cập nhật/xóa và vẫn cần một giao dịch đang hoạt động.