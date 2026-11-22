# Phối hợp JPA với JDBC cho thao tác đặc thù trong cùng giao dịch

Spring Data JPA phù hợp với các thao tác CRUD trên entity và quan hệ giữa chúng. Tuy nhiên, một số công việc như cập nhật hàng loạt, truy vấn SQL đặc thù của hệ quản trị cơ sở dữ liệu, gọi stored procedure hoặc ghi vào bảng phụ có thể được thực hiện gọn và hiệu quả hơn bằng JDBC.

Có thể dùng JPA và JDBC trong cùng một giao dịch Spring để các thay đổi cùng được commit hoặc rollback. Điều kiện quan trọng là cả hai phải tham gia cùng transaction đang quản lý cùng một cơ sở dữ liệu. Khi kết hợp, cần chủ động xử lý thời điểm JPA đẩy dữ liệu xuống database và trạng thái entity đang nằm trong persistence context.

## 1. Khi nào nên kết hợp JPA và JDBC?

Dùng JPA cho phần nghiệp vụ dựa trên entity:

- Tải entity và kiểm tra trạng thái nghiệp vụ.
- Thay đổi thuộc tính của entity đang được quản lý.
- Dùng cascade, quan hệ entity, dirty checking và optimistic locking.
- Lưu dữ liệu theo mô hình domain.

Dùng JDBC cho phần SQL cần kiểm soát trực tiếp:

- Cập nhật hoặc xóa số lượng lớn bản ghi bằng một câu lệnh SQL.
- Dùng CTE, window function, hint hoặc cú pháp riêng của database.
- Gọi stored procedure hoặc thao tác với cấu trúc dữ liệu cũ chưa được ánh xạ thành entity.
- Ghi log nghiệp vụ, bảng thống kê hoặc bảng phụ bằng SQL đơn giản.
- Thực hiện truy vấn báo cáo có cấu trúc kết quả không phù hợp với entity.

Ví dụ, một nghiệp vụ hoàn tất đơn hàng có thể tải và chuyển trạng thái `Order` bằng JPA, sau đó thêm một bản ghi vào bảng `order_audit` bằng JDBC. Cả hai thay đổi cần thành công cùng nhau.

Không nên trộn hai cách truy cập chỉ vì có thể làm được. Nếu thao tác cần đầy đủ cascade, entity listener, auditing hoặc kiểm soát phiên bản của JPA, hãy cân nhắc thực hiện bằng JPA. JDBC phù hợp khi lợi ích của SQL trực tiếp lớn hơn phần đồng bộ trạng thái mà ứng dụng phải tự đảm nhiệm.

## 2. Điều kiện để dùng chung một transaction

Trong ứng dụng Spring, hãy đặt ranh giới giao dịch tại tầng service bằng `@Transactional`. Phương thức service điều phối cả thao tác repository/JPA và JDBC.

Để hai công nghệ dùng chung transaction, cần bảo đảm:

1. JPA và `JdbcTemplate` dùng cùng một `DataSource` và cùng database.
2. Transaction được quản lý bởi `JpaTransactionManager` gắn với `EntityManagerFactory` tương ứng. Với cấu hình Spring Boot thông thường chỉ có một datasource và một JPA transaction manager, cơ chế tự cấu hình thường đã đáp ứng điều kiện này.
3. `JdbcTemplate` nhận chính `DataSource` đó. `JdbcTemplate` lấy connection qua cơ chế quản lý transaction của Spring (`DataSourceUtils`), vì vậy có thể sử dụng connection đã được gắn với transaction hiện tại.
4. Các thao tác diễn ra trong cùng luồng thực thi và cùng transaction context. Không tự mở một connection độc lập rồi gọi `commit()`.

Khi có nhiều datasource hoặc nhiều transaction manager, cần cấu hình rõ manager mà phương thức dùng, ví dụ `@Transactional(transactionManager = "jpaTransactionManager")`. Chỉ định đúng tên bean và bảo đảm datasource của JDBC thuộc cùng transaction manager đó.

Ví dụ về cấu trúc phụ thuộc:

```text
OrderCompletionService
  ├── OrderRepository ──> EntityManagerFactory ──┐
  └── JdbcTemplate ─────> DataSource ────────────┤
                                                 v
                                      Cùng transaction/database
```

Nếu JPA và JDBC dùng hai datasource khác nhau, hai transaction manager độc lập hoặc hai connection được mở ngoài cơ chế Spring, `@Transactional` thông thường không tự tạo ra một giao dịch phân tán. Khi đó, một thao tác có thể commit trong khi thao tác còn lại rollback. Muốn bảo đảm tính nguyên tử giữa nhiều resource cần một giải pháp transaction phù hợp như JTA/XA, hoặc thiết kế nghiệp vụ theo hướng outbox/saga tùy yêu cầu.

## 3. Ví dụ: cập nhật entity bằng JPA và ghi audit bằng JDBC

Giả sử `Order` là entity đã được ánh xạ và `OrderRepository` kế thừa `JpaRepository<Order, Long>`. Entity có phương thức nghiệp vụ `complete()` để chuyển đơn hàng sang trạng thái hoàn tất.

Service có thể phối hợp hai công nghệ như sau:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityNotFoundException;
import jakarta.persistence.PersistenceContext;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCompletionService {

    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    public OrderCompletionService(
            OrderRepository orderRepository,
            JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void complete(Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() ->
                        new EntityNotFoundException("Order " + orderId));

        // Entity đang được quản lý bởi persistence context.
        order.complete();

        // Đẩy thay đổi JPA xuống database trước khi chạy SQL phụ thuộc vào nó.
        entityManager.flush();

        int inserted = jdbcTemplate.update(
                """
                INSERT INTO order_audit (order_id, action, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                orderId,
                "COMPLETED"
        );

        if (inserted != 1) {
            throw new IllegalStateException(
                    "Không ghi được audit cho order " + orderId);
        }
    }
}
```

Trong ví dụ:

- `findById()` tải entity trong transaction hiện tại. Entity được quản lý bởi persistence context.
- `order.complete()` thay đổi trạng thái trong bộ nhớ. Dirty checking của JPA ghi nhận thay đổi này; không cần gọi `save()` lại cho entity đang được quản lý.
- `entityManager.flush()` yêu cầu JPA đồng bộ các thay đổi đang chờ xuống database. Lệnh này không commit transaction.
- `jdbcTemplate.update()` thực hiện câu lệnh INSERT bằng connection tham gia transaction hiện tại.
- Nếu câu lệnh JDBC phát sinh lỗi và exception thoát khỏi phương thức, transaction sẽ rollback cả thay đổi trạng thái đơn hàng do JPA thực hiện lẫn bản ghi audit.

Các dấu `?` là tham số của prepared statement. Hãy truyền giá trị qua đối số của `update()`, không ghép chuỗi đầu vào vào SQL. Với câu truy vấn có nhiều tham số, có thể dùng `NamedParameterJdbcTemplate` để câu lệnh dễ đọc hơn.

Đoạn code giả định bảng `order_audit` đã tồn tại, các cột phù hợp với câu lệnh INSERT và `Order.complete()` hợp lệ theo mô hình nghiệp vụ của ứng dụng. Đây là phần minh họa cách phối hợp transaction, không phải một dự án độc lập có thể chạy nếu thiếu entity, repository và schema tương ứng.

## 4. Vì sao cần chú ý đến flush?

JPA thường trì hoãn việc gửi SQL xuống database cho đến thời điểm flush. Việc thay đổi entity trong Java không có nghĩa câu UPDATE đã được thực thi ngay.

Điều này tạo ra tình huống dễ nhầm lẫn:

```java
Order order = orderRepository.findById(orderId).orElseThrow();
order.complete();

// JDBC chạy trước khi thay đổi đang chờ của JPA được flush.
Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE status = ?",
        Integer.class,
        "COMPLETED"
);
```

Nếu JPA chưa flush, truy vấn JDBC có thể chưa nhìn thấy trạng thái mới. Khi câu SQL JDBC phụ thuộc vào thay đổi JPA vừa thực hiện, hãy gọi `entityManager.flush()` trước câu SQL đó.

Một số điểm cần nhớ:

- Flush gửi các câu SQL đang chờ xuống database trong transaction hiện tại.
- Flush không kết thúc transaction và không làm dữ liệu hiển thị cho transaction khác như một lần commit.
- Với flush mode mặc định `AUTO`, JPA có thể tự flush trước một số truy vấn JPA. Không nên dựa vào hành vi tự động đó để suy luận thứ tự giữa một truy vấn JDBC và thay đổi JPA.
- Flush có thể phát hiện lỗi constraint hoặc lỗi SQL sớm hơn thời điểm commit.
- Flush có thể đẩy nhiều thay đổi đang chờ trong persistence context, không chỉ entity vừa sửa.

Vì vậy, chỉ flush tại điểm cần bảo đảm thứ tự hoặc cần database nhìn thấy các thay đổi JPA trước khi chạy JDBC.

## 5. Khi JDBC sửa dữ liệu mà JPA đã tải

JDBC làm việc trực tiếp với database, không cập nhật các object entity đang nằm trong persistence context. Nếu một entity đã được tải bằng JPA rồi bị JDBC sửa, object trong bộ nhớ có thể giữ giá trị cũ.

Ví dụ:

1. JPA tải `Order` với trạng thái `PROCESSING`.
2. JDBC chạy `UPDATE orders SET status = 'COMPLETED' WHERE id = ?`.
3. Object `Order` trong persistence context vẫn có thể chứa `PROCESSING`.
4. Nếu tiếp tục sử dụng object này, ứng dụng có thể đọc dữ liệu cũ. Một lần flush sau đó còn có nguy cơ ghi đè thay đổi JDBC nếu entity có thay đổi đang chờ.

Cách xử lý tùy phạm vi:

- Dùng `entityManager.refresh(order)` để nạp lại một entity cụ thể từ database. Hãy bảo đảm không có thay đổi JPA chưa flush mà bạn muốn giữ, vì refresh sẽ nạp lại trạng thái từ database.
- Dùng `entityManager.clear()` để detach toàn bộ entity đang được quản lý, sau đó tải lại entity cần dùng. Trước khi clear, phải flush các thay đổi JPA cần giữ; clear có thể làm mất các thay đổi chưa flush.
- Nếu không cần tiếp tục dùng entity đó trong cùng transaction, có thể thiết kế luồng xử lý để tránh đọc lại object cũ.

Không gọi `refresh()` hoặc `clear()` một cách máy móc. Hãy xác định thay đổi nào đang chờ trong persistence context và dữ liệu nào cần được đọc lại.

## 6. Những cơ chế JPA mà JDBC không tự thực hiện

SQL chạy qua JDBC đi thẳng tới database. Nó không đi qua đầy đủ vòng đời entity của JPA. Vì vậy, các cơ chế sau không tự chạy cho câu lệnh JDBC:

| Cơ chế | Khi cập nhật bằng JDBC |
|---|---|
| Dirty checking | Không áp dụng; SQL phải mô tả thay đổi cần thực hiện. |
| Cascade và quan hệ entity | Không tự lan truyền thao tác sang entity liên quan. |
| Entity listener và callback như `@PreUpdate` | Không được gọi chỉ vì JDBC cập nhật hàng. |
| Bean Validation ở vòng đời entity | Không tự chạy; constraint tại database vẫn có thể được thực thi. |
| Spring Data JPA auditing | Không tự điền `@LastModifiedDate` hoặc `@LastModifiedBy`. |
| Optimistic locking với `@Version` | SQL JDBC phải tự bảo đảm điều kiện phiên bản và cập nhật cột version nếu cần. |
| Persistence context | Không tự đồng bộ object entity đã tải. |

Đặc biệt, nếu bảng có cột `@Version`, câu lệnh JDBC cập nhật dữ liệu nên kiểm tra version hiện tại và tăng version theo quy tắc của ứng dụng. Nếu bỏ qua, các entity JPA đang giữ version cũ có thể không phát hiện được một số cập nhật trực tiếp; hoặc lần flush tiếp theo có thể phát sinh lỗi optimistic locking.

Ví dụ về nguyên tắc cập nhật có kiểm tra version:

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
```

Sau khi chạy, kiểm tra số hàng bị ảnh hưởng. Nếu bằng 0, bản ghi không tồn tại hoặc version đã thay đổi; xử lý tình huống này theo quy tắc cạnh tranh cập nhật của nghiệp vụ.

Nếu ứng dụng dùng second-level cache hoặc query cache của JPA/Hibernate, cập nhật bằng JDBC cũng có thể khiến cache giữ dữ liệu cũ. Cần chủ động vô hiệu hóa vùng cache liên quan hoặc tránh cache những dữ liệu được sửa trực tiếp bằng JDBC.

## 7. Rollback và các lỗi cấu hình thường gặp

Mặc định, Spring rollback transaction khi phương thức transactional kết thúc bằng unchecked exception (`RuntimeException`) hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định; nếu cần, khai báo rõ:

```java
@Transactional(rollbackFor = Exception.class)
public void performOperation() throws Exception {
    // Thao tác JPA và JDBC trong cùng transaction.
}
```

Không nên bắt exception từ JDBC rồi bỏ qua nếu nghiệp vụ yêu cầu rollback. Hãy ném lại exception hoặc đánh dấu transaction rollback-only khi cần xử lý lỗi tại chỗ nhưng vẫn phải hủy toàn bộ giao dịch.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| JPA rollback nhưng INSERT JDBC vẫn còn | JDBC dùng datasource/transaction manager khác hoặc connection tự mở | Kiểm tra cả hai dùng cùng datasource và JDBC đi qua `JdbcTemplate`/cơ chế Spring. |
| JDBC không đọc thấy thay đổi vừa sửa bằng JPA | JPA chưa flush | Gọi `entityManager.flush()` trước truy vấn JDBC phụ thuộc vào thay đổi đó. |
| Entity vẫn có giá trị cũ sau UPDATE JDBC | Persistence context chưa được đồng bộ | Dùng `refresh()` hoặc `clear()` đúng thời điểm rồi tải lại. |
| Entity bị lỗi optimistic locking | SQL JDBC không cập nhật cột version theo quy ước | Kiểm tra và tăng version trong SQL; kiểm tra số hàng bị ảnh hưởng. |
| Callback hoặc auditing không chạy | JDBC bỏ qua vòng đời entity | Tự xử lý dữ liệu audit hoặc chuyển thao tác về JPA nếu cần lifecycle. |
| `@Transactional` không có tác dụng như mong đợi | Gọi nội bộ cùng object (self-invocation), dùng sai manager hoặc chạy sang thread khác | Gọi qua Spring bean proxy, chỉ định đúng transaction manager và kiểm tra luồng thực thi. |
| Checked exception không rollback | Quy tắc rollback mặc định không áp dụng cho checked exception | Dùng `rollbackFor` phù hợp. |

Transaction Spring thường gắn với thread hiện tại. Công việc được chuyển sang thread khác bằng `@Async`, executor hoặc tạo thread thủ công không tự tham gia transaction đang chạy. Nếu cần xử lý bất đồng bộ, hãy thiết kế ranh giới transaction riêng và truyền dữ liệu cần thiết một cách rõ ràng.

## 8. Cách kiểm thử tính nguyên tử

Một bài kiểm thử tích hợp hữu ích cần chứng minh cả hai loại thao tác cùng rollback:

1. Chuẩn bị một đơn hàng ở trạng thái ban đầu và dữ liệu audit tương ứng.
2. Gọi service transactional: JPA cập nhật đơn hàng, sau đó JDBC ghi audit.
3. Cố ý làm thao tác JDBC thất bại, chẳng hạn vi phạm một constraint đã được thiết lập trong môi trường kiểm thử.
4. Sau khi transaction kết thúc, đọc lại dữ liệu bằng một transaction mới.
5. Xác nhận trạng thái đơn hàng vẫn là trạng thái ban đầu và không có bản ghi audit được tạo.

Cũng nên có kiểm thử thành công để xác nhận cả trạng thái đơn hàng và bản ghi audit đều được lưu. Khi kiểm thử, chú ý transaction bao ngoài của framework test: nếu toàn bộ test chạy trong một transaction tự rollback, cần chủ động kiểm tra dữ liệu sau khi transaction nghiệp vụ kết thúc hoặc dùng cách kiểm thử phù hợp để không nhầm rollback của test với rollback của service.

## 9. Checklist khi triển khai

Trước khi đưa luồng JPA + JDBC vào sử dụng, hãy xác nhận:

- [ ] Service có một ranh giới `@Transactional` bao trọn các thao tác liên quan.
- [ ] JPA và `JdbcTemplate` dùng cùng `DataSource`, cùng database và transaction manager phù hợp.
- [ ] JDBC dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`, không tự commit connection riêng.
- [ ] Có `flush()` trước câu SQL JDBC cần nhìn thấy thay đổi JPA đang chờ.
- [ ] Entity được tải trước khi JDBC cập nhật đã được refresh, detach hoặc xử lý để tránh dữ liệu cũ.
- [ ] SQL JDBC tự xử lý version, audit và các quy tắc vốn do JPA đảm nhiệm nếu nghiệp vụ yêu cầu.
- [ ] Exception được truyền ra ngoài hoặc transaction được đánh dấu rollback-only khi cần rollback.
- [ ] Có kiểm thử tích hợp chứng minh cả thay đổi JPA và JDBC cùng commit hoặc cùng rollback.

Kết hợp JPA với JDBC giúp tận dụng mô hình entity cho nghiệp vụ và SQL trực tiếp cho thao tác đặc thù. Tính nhất quán phụ thuộc vào việc chia sẻ đúng transaction, kiểm soát thứ tự flush và chủ động đồng bộ persistence context sau các cập nhật JDBC.