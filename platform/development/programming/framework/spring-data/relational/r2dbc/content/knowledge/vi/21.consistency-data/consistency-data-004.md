# Xử lý xung đột phiên bản khi cập nhật hoặc xóa

## 1. Vì sao cập nhật đồng thời có thể làm mất dữ liệu?

Trong ứng dụng Spring Data Relational R2DBC, nhiều request có thể đọc và thay đổi cùng một bản ghi gần như đồng thời. Nếu không có cơ chế phát hiện xung đột, thao tác ghi sau có thể ghi đè kết quả của thao tác ghi trước, dù người thực hiện thao tác sau đang dựa trên dữ liệu cũ.

Giả sử một đơn hàng đang có trạng thái PENDING và hai người cùng mở màn hình quản trị:

1. Người A đọc đơn hàng với trạng thái PENDING.
2. Người B cũng đọc cùng đơn hàng với trạng thái PENDING.
3. A đổi trạng thái thành PAID và lưu thành công.
4. B, vẫn giữ bản dữ liệu cũ, đổi trạng thái thành CANCELLED và lưu sau đó.

Nếu database chỉ cập nhật theo ID, thao tác của B có thể ghi đè trạng thái PAID thành CANCELLED. Ứng dụng không biết rằng B đã chỉnh sửa một phiên bản cũ.

Hiện tượng này thường được gọi là **lost update** (cập nhật bị mất). Dữ liệu cuối cùng phản ánh thao tác ghi sau cùng, nhưng có thể làm mất quyết định vừa được một người khác lưu.

Spring Data Relational hỗ trợ **optimistic locking** (khóa lạc quan) bằng annotation @Version. Cơ chế này cho phép ứng dụng phát hiện một entity đã bị thay đổi kể từ lúc được đọc. Khi phát hiện xung đột, thao tác cập nhật hoặc xóa bị từ chối và phát sinh lỗi optimistic locking.

## 2. Optimistic locking hoạt động như thế nào?

Optimistic locking giả định rằng xung đột ghi không xảy ra thường xuyên. Ứng dụng không giữ khóa database trong suốt thời gian người dùng đọc và chỉnh sửa dữ liệu. Thay vào đó, mỗi bản ghi có một giá trị phiên bản (version). Khi ghi, database chỉ chấp nhận thao tác nếu version hiện tại vẫn bằng version mà ứng dụng đã đọc.

Có thể hình dung:

~~~text
A đọc đơn hàng: version = 5
B đọc đơn hàng: version = 5
          |
          v
A cập nhật với điều kiện version = 5
          |
          v
Database ghi thành công, version tăng thành 6
          |
          v
B cập nhật với điều kiện version = 5
          |
          v
Không có hàng nào khớp version = 5
          |
          v
B nhận lỗi xung đột phiên bản
~~~

Điểm quan trọng là kiểm tra version và cập nhật dữ liệu được thực hiện trong cùng một câu lệnh có điều kiện ở database. Vì vậy, hai request cạnh tranh không thể cùng cập nhật thành công dựa trên một version cũ.

Optimistic locking phù hợp với những trường hợp:

- Nhiều người có thể cùng xem và chỉnh sửa một bản ghi.
- Xung đột không xảy ra quá thường xuyên.
- Không muốn giữ database lock trong suốt thời gian người dùng thao tác.
- Cần phát hiện dữ liệu cũ trước khi ghi đè.
- Có thể yêu cầu người dùng tải lại hoặc kết hợp thay đổi khi xảy ra xung đột.

## 3. Khai báo thuộc tính @Version

Spring Data Relational nhận biết thuộc tính version thông qua annotation:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    public Long getId() {
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
~~~

Annotation @Version thuộc package org.springframework.data.annotation. Nó đánh dấu thuộc tính được Spring Data dùng để theo dõi phiên bản của entity.

Thông thường, version dùng kiểu số nguyên như Long hoặc Integer. Spring Data quản lý giá trị version trong quá trình insert, update và delete. Ứng dụng không nên tự tăng version bằng code nghiệp vụ trước mỗi lần gọi save.

### 3.1. Schema database phải có cột version

Ví dụ DDL:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Tên cột được suy ra từ thuộc tính Java theo naming strategy hoặc có thể chỉ định tường minh bằng @Column. Trong ví dụ, version ánh xạ tới cột version.

Nếu database hiện tại chưa có cột version, cần tạo migration trước khi triển khai code dùng @Version:

~~~sql
ALTER TABLE orders
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

Giá trị DEFAULT trong migration giúp các hàng hiện hữu có version ban đầu. Khi Spring Data quản lý version, framework sẽ áp dụng quy tắc khởi tạo và tăng version của nó. Hãy kiểm tra DDL, kiểu Java và phiên bản Spring Data đang dùng để bảo đảm chúng tương thích.

### 3.2. Không tự quản lý version trong code nghiệp vụ

Không nên viết:

~~~java
order.setVersion(order.getVersion() + 1);
return orderRepository.save(order);
~~~

Spring Data cần giá trị version cũ để kiểm tra điều kiện cập nhật và tự quản lý giá trị version mới. Nếu code tự tăng trước khi lưu, giá trị dùng để kiểm tra có thể không còn khớp với version đang có trong database, khiến thao tác bị từ chối hoặc phá vỡ quy ước quản lý version.

Hãy thay đổi các trường nghiệp vụ rồi gọi save:

~~~java
order.setStatus("PAID");
return orderRepository.save(order);
~~~

Publisher save phát ra entity sau khi lưu thành công. Hãy sử dụng entity được trả về, vì version của đối tượng kết quả đã được cập nhật theo thao tác lưu.

### 3.3. Version và nhận diện entity mới

Spring Data cần phân biệt entity mới với entity đã tồn tại. ID và version có thể tham gia vào cơ chế nhận diện trạng thái mới tùy kiểu dữ liệu và cấu hình entity.

Khi dùng @Version, hãy để Spring Data khởi tạo version theo quy ước của framework. Không tự gán một version tùy ý cho entity mới chỉ để ép insert hoặc update. Nếu entity dùng chiến lược xác định trạng thái mới tùy chỉnh, hãy tìm hiểu cơ chế Persistable và cách nó tương tác với ID/version trước khi áp dụng.

## 4. Spring Data tạo điều kiện cập nhật có version

Khi lưu một entity đã tồn tại và có @Version, Spring Data Relational tạo thao tác cập nhật có điều kiện dựa trên ID và version hiện tại.

Về mặt ý tưởng, câu SQL tương đương:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
~~~

Tên placeholder, cách tăng version và SQL cụ thể do Spring Data cùng dialect quyết định. Điều cần hiểu là câu UPDATE có hai điều kiện:

- ID phải khớp bản ghi cần cập nhật.
- Version trong database phải bằng version mà entity đang mang.

Nếu cập nhật thành công, version được tăng lên. Nếu không có hàng nào thỏa cả hai điều kiện, Spring Data không coi đó là một lần lưu thành công bình thường mà phát sinh lỗi optimistic locking.

### 4.1. Ví dụ với repository

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

Service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Mono<Order> markAsPaid(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                order.setStatus("PAID");
                return orderRepository.save(order);
            });
    }
}
~~~

Luồng đọc rồi ghi diễn ra trong reactive pipeline. Khi save được thực thi, Spring Data dùng version của entity vừa đọc làm điều kiện cập nhật. Nếu một request khác đã cập nhật entity sau bước đọc, save có thể thất bại do version không còn khớp.

Không cần khóa database trong suốt thời gian từ findById đến save. Câu UPDATE có điều kiện là điểm quyết định request nào ghi thành công.

### 4.2. Dùng entity được trả về sau save

Ví dụ:

~~~java
return orderRepository.findById(orderId)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
    .flatMap(order -> {
        order.setStatus("PAID");
        return orderRepository.save(order);
    })
    .map(savedOrder -> {
        // savedOrder mang version mới sau khi lưu thành công
        return toOrderResponse(savedOrder);
    });
~~~

Nếu tiếp tục dùng một bản entity cũ đã được giữ ở nơi khác, version trong bản đó có thể không còn mới. Hãy truyền đối tượng được save trả về qua các bước tiếp theo hoặc tải lại dữ liệu khi cần.

## 5. Điều gì xảy ra khi hai request cùng cập nhật?

Giả sử version trong database ban đầu là 3.

| Thời điểm | Request A | Request B | Database |
|---|---|---|---|
| 1 | Đọc entity | | version = 3 |
| 2 | | Đọc entity | version = 3 |
| 3 | Đổi status thành PAID | | version = 3 |
| 4 | Save thành công | | version = 4 |
| 5 | | Đổi status thành CANCELLED | version = 4 |
| 6 | | Save với version kỳ vọng 3 | Không có hàng khớp version 3 |
| 7 | | Nhận lỗi optimistic locking | version vẫn = 4 |

Request B không được phép ghi đè thay đổi của A một cách âm thầm. Tầng ứng dụng có thể chuyển lỗi này thành phản hồi xung đột, yêu cầu tải lại dữ liệu hoặc áp dụng quy tắc kết hợp thay đổi.

Optimistic locking không quyết định thay người dùng rằng trạng thái PAID hay CANCELLED đúng hơn. Nó chỉ phát hiện dữ liệu mà request B đang dựa vào đã cũ. Quyết định nghiệp vụ sau xung đột thuộc về ứng dụng.

## 6. Xử lý xung đột khi cập nhật

Khi save phát sinh lỗi optimistic locking, có một số chiến lược xử lý.

### 6.1. Thông báo xung đột và yêu cầu tải lại

Đây là lựa chọn phù hợp khi người dùng cần xem dữ liệu mới trước khi tiếp tục.

Ví dụ chuyển lỗi ở service:

~~~java
public Mono<Order> updateStatus(Long orderId, String status) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus(status);
            return orderRepository.save(order);
        })
        .onErrorMap(
            OptimisticLockingFailureException.class,
            error -> new OrderConflictException(orderId, error)
        );
}
~~~

Ứng dụng web có thể chuyển OrderConflictException thành HTTP 409 Conflict. Client hiển thị thông báo rằng dữ liệu đã được người khác thay đổi và đề nghị tải lại.

Trong một API, không nên trả thông tin nội bộ của database hoặc stack trace cho client. Hãy trả mã lỗi và thông điệp nghiệp vụ rõ ràng.

### 6.2. Tải lại rồi áp dụng lại thay đổi

Một số thay đổi có thể được áp dụng lại trên phiên bản mới nhất. Ví dụ, thao tác tăng số lượng thêm 1 có thể được thực hiện lại sau khi đọc giá trị mới, nếu nghiệp vụ cho phép.

Cách xử lý cần thể hiện rõ ý định:

1. Bắt lỗi optimistic locking.
2. Đọc lại entity mới nhất.
3. Kiểm tra trạng thái hiện tại và điều kiện nghiệp vụ.
4. Áp dụng lại thay đổi trên entity mới.
5. Thử lưu lại với version mới.
6. Giới hạn số lần thử và xử lý nếu tiếp tục xung đột.

Ví dụ minh họa thử lại một lần:

~~~java
public Mono<Inventory> increaseStock(Long productId, int amount) {
    return updateStockOnce(productId, amount)
        .onErrorResume(
            OptimisticLockingFailureException.class,
            error -> updateStockOnce(productId, amount)
        );
}

private Mono<Inventory> updateStockOnce(Long productId, int amount) {
    return inventoryRepository.findById(productId)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(productId)))
        .flatMap(inventory -> {
            inventory.setQuantity(inventory.getQuantity() + amount);
            return inventoryRepository.save(inventory);
        });
}
~~~

Đây là ví dụ minh họa việc tải lại entity ở lần thử tiếp theo. Trong triển khai thực tế, hãy giới hạn retry rõ ràng và phân biệt lỗi xung đột với các lỗi database khác. Không retry vô hạn khi nhiều request liên tục tranh chấp cùng một bản ghi.

### 6.3. Không retry mù quáng cùng một entity cũ

Đoạn sau không giải quyết được xung đột:

~~~java
Mono<Inventory> saved = inventoryRepository.save(staleInventory);

return saved.retry(3);
~~~

Nếu staleInventory vẫn mang version cũ, mỗi lần retry có thể gửi lại cùng điều kiện version đã lỗi. Retry không tự tải lại entity và không tự hòa giải dữ liệu.

Muốn retry, phải thực hiện lại cả quy trình đọc mới, kiểm tra nghiệp vụ và ghi. Nếu thao tác không thể được áp dụng lại một cách an toàn, hãy trả conflict để người dùng hoặc tầng nghiệp vụ quyết định.

### 6.4. Kiểm tra tính idempotent của thao tác

Không phải mọi lệnh đều có thể áp dụng lại an toàn.

Ví dụ:

- Đặt trạng thái thành PAID có thể là thao tác gán giá trị, nhưng cần kiểm tra trạng thái hiện tại và quy trình thanh toán.
- Tăng số lượng thêm 1 là thao tác cộng dồn; đọc lại rồi cộng lại có thể đúng nếu mỗi request đại diện cho một sự kiện độc lập.
- Trừ tồn kho cho một đơn hàng không thể retry tùy tiện nếu đã phát sinh tác động ở hệ thống khác.
- Gửi email hoặc gọi cổng thanh toán không nên được lặp lại chỉ vì database save bị conflict.

Khi một nghiệp vụ có side effect bên ngoài database, hãy thiết kế idempotency key, outbox hoặc quy trình phối hợp phù hợp. Không để retry optimistic locking vô tình gửi thanh toán hoặc thông báo nhiều lần.

## 7. Xử lý xung đột khi xóa

Optimistic locking có thể áp dụng cho thao tác xóa entity có version. Về mặt ý tưởng, câu lệnh xóa có điều kiện như sau:

~~~sql
DELETE FROM orders
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu bản ghi đã được người khác cập nhật sau khi entity được đọc, version trong database không còn khớp. Lệnh xóa không tác động hàng nào và Spring Data phát hiện xung đột.

### 7.1. Xóa entity đã đọc

Ví dụ:

~~~java
public Mono<Void> deleteOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> orderRepository.delete(order));
}
~~~

Entity truyền vào delete mang theo ID và version mà ứng dụng đã đọc. Nếu một request khác cập nhật đơn hàng trước khi lệnh xóa được thực thi, thao tác xóa có thể thất bại vì version đã thay đổi.

### 7.2. Phân biệt xóa theo entity và xóa chỉ theo ID

Một lệnh xóa chỉ nhận ID không mang theo version mà client đã đọc. Vì thế, nếu yêu cầu nghiệp vụ là "chỉ xóa khi bản ghi vẫn ở đúng phiên bản mà người dùng đã xác nhận", cần truyền expected version vào quy trình xóa và bảo đảm câu DELETE có điều kiện version.

Có thể đọc entity, so sánh version với expectedVersion từ client rồi xóa chính entity đó:

~~~java
public Mono<Void> deleteIfVersionMatches(
        Long orderId,
        Long expectedVersion) {

    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            if (!Objects.equals(order.getVersion(), expectedVersion)) {
                return Mono.error(new OrderConflictException(orderId));
            }

            return orderRepository.delete(order);
        });
}
~~~

Có hai lớp bảo vệ trong ví dụ:

- So sánh version với giá trị mà client đã gửi để phát hiện dữ liệu đã cũ trước khi xóa.
- Thao tác delete trên entity có version để database kiểm tra lại trong lúc ghi, phòng trường hợp có request khác cập nhật sau bước so sánh.

Không nên thay delete(entity) bằng deleteById(id) nếu yêu cầu cần kiểm tra expected version của client. API chỉ nhận ID không thể tự thể hiện phiên bản mà client đã nhìn thấy. Hãy kiểm tra semantics của method trong phiên bản Spring Data R2DBC đang dùng và dùng câu lệnh có điều kiện nếu cần kiểm soát rõ ràng.

### 7.3. Xóa và dữ liệu phụ thuộc

Nếu xóa một aggregate có dữ liệu con, hãy xem xét cách Spring Data Relational xử lý aggregate và các foreign key trong database. Optimistic locking trên aggregate root giúp phát hiện phiên bản root đã thay đổi theo cơ chế mapping được hỗ trợ. Constraint và hành vi ON DELETE của foreign key vẫn là lớp bảo vệ toàn vẹn tham chiếu riêng.

Nếu database từ chối xóa vì foreign key hoặc constraint, đó là lỗi toàn vẹn dữ liệu, không phải optimistic locking conflict. Không chuyển mọi lỗi delete thành HTTP 409 cùng một thông điệp mà không phân biệt nguyên nhân.

## 8. Trả version cho client qua API

Trong ứng dụng web, client thường đọc một resource, chỉnh sửa rồi gửi yêu cầu cập nhật. Để server biết client đang dựa trên phiên bản nào, có thể trả version trong response DTO.

Ví dụ:

~~~java
public record OrderResponse(
    Long id,
    String status,
    Long version
) {}
~~~

Khi client cập nhật, request có thể gửi lại expectedVersion:

~~~java
public record UpdateOrderRequest(
    String status,
    Long version
) {}
~~~

Service so sánh version client với entity mới nhất và dùng optimistic locking ở lúc save. Việc kiểm tra version trong service giúp trả thông báo sớm; điều kiện @Version ở database vẫn cần thiết để bảo vệ khoảng thời gian giữa lần đọc và lần ghi.

### 8.1. Dùng HTTP ETag và If-Match

Một cách khác là biểu diễn version qua HTTP ETag:

- GET resource trả ETag chứa version.
- Client gửi If-Match khi cập nhật hoặc xóa.
- Server chỉ chấp nhận thay đổi nếu version hiện tại khớp ETag.
- Nếu không khớp, server trả HTTP 412 Precondition Failed hoặc 409 Conflict theo hợp đồng API.

ETag có thể được tạo từ version:

~~~text
ETag: "order-42-v7"
~~~

Request cập nhật:

~~~http
PUT /orders/42
If-Match: "order-42-v7"
Content-Type: application/json
~~~

Server cần phân tích ETag, xác định expected version và thực hiện thao tác có version. ETag là hợp đồng HTTP; @Version là cơ chế persistence. Hai phần phối hợp với nhau nhưng không thay thế nhau.

### 8.2. Không tin version do client gửi một cách mù quáng

Version từ client là dữ liệu đầu vào. Hãy xác thực định dạng, xác nhận resource và quyền truy cập, rồi dùng giá trị đó làm điều kiện cạnh tranh. Không cho phép client tự chọn version mới tùy ý để ghi đè trạng thái.

Nếu client không gửi version trong một API cần bảo vệ cập nhật đồng thời, hãy quyết định rõ: bắt buộc If-Match, trả lỗi precondition, hay áp dụng chính sách cập nhật khác. Không âm thầm bỏ qua kiểm soát phiên bản.

## 9. Cập nhật bằng SQL trực tiếp phải tự kiểm tra version

Khi dùng repository save(entity), Spring Data có thể áp dụng optimistic locking dựa trên @Version. Nhưng một câu SQL tùy chỉnh qua DatabaseClient hoặc @Query không tự động có đầy đủ semantics đó chỉ vì entity có trường @Version.

Nếu tự viết UPDATE, hãy đưa expected version vào WHERE và tăng version trong cùng câu lệnh:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Trong DatabaseClient:

~~~java
public Mono<Void> updateStatus(
        Long orderId,
        Long expectedVersion,
        String status) {

    return databaseClient.sql("""
            UPDATE orders
            SET status = :status,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """)
        .bind("status", status)
        .bind("id", orderId)
        .bind("expectedVersion", expectedVersion)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.empty();
            }

            return Mono.error(new OrderConflictException(orderId));
        });
}
~~~

Với câu UPDATE tác động đúng một hàng, rowsUpdated bằng 1 nghĩa là cập nhật thành công. Nếu bằng 0, ID không tồn tại hoặc version không khớp. Có thể đọc lại để phân biệt bản ghi không tồn tại với xung đột phiên bản nếu API cần hai phản hồi khác nhau.

Khi dùng SQL tùy chỉnh:

- Tự thêm điều kiện version.
- Tự tăng version.
- Kiểm tra số hàng bị ảnh hưởng.
- Đồng bộ version của entity đang nằm trong bộ nhớ bằng cách tải lại hoặc cập nhật kết quả.
- Không giả định @Version tự can thiệp vào mọi câu SQL viết tay.

Nếu query tùy chỉnh bỏ qua version, nó có thể ghi đè dữ liệu mà không phát hiện stale entity. Đây là một trong những nguyên nhân khiến optimistic locking có vẻ hoạt động với repository save nhưng không hoạt động ở một số luồng cập nhật khác.

## 10. Kết hợp optimistic locking với reactive transaction

Optimistic locking và transaction giải quyết hai vấn đề liên quan nhưng khác nhau:

- Optimistic locking phát hiện một entity đã thay đổi kể từ version được đọc.
- Transaction bảo đảm một nhóm thao tác database được commit hoặc rollback như một đơn vị theo cấu hình transaction.

Ví dụ, một nghiệp vụ xác nhận đơn hàng có thể cập nhật order và ghi audit log:

~~~java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus("CONFIRMED");
            return orderRepository.save(order);
        })
        .flatMap(savedOrder ->
            auditRepository.save(
                new OrderAudit(savedOrder.getId(), "CONFIRMED")
            ).thenReturn(savedOrder)
        );
}
~~~

Nếu save order gặp version conflict, publisher phát lỗi và transaction có thể rollback. Nếu ghi audit thất bại, transaction cũng có thể rollback thay đổi order nếu cả hai repository tham gia cùng transaction reactive.

Để transaction hoạt động đúng:

1. Dùng R2DBC reactive transaction manager.
2. Repository và transaction manager dùng cùng ConnectionFactory.
3. Phương thức trả về Mono/Flux để Reactor Context được truyền xuyên suốt.
4. Không tự gọi subscribe() hoặc block() giữa các bước.
5. Để Spring quản lý commit/rollback.

Một transaction không loại bỏ nhu cầu optimistic locking. Hai transaction vẫn có thể cùng đọc version cũ; điều kiện version ở lệnh UPDATE/DELETE quyết định thao tác nào thành công.

### 10.1. Khi nào nên retry transaction?

Nếu một transaction có nhiều bước và gặp optimistic lock conflict, thường cần kết thúc transaction lỗi rồi mới bắt đầu một lần thử mới với dữ liệu được tải lại. Không tiếp tục sử dụng entity cũ hoặc trạng thái transaction đã lỗi.

Retry cần được đặt quanh toàn bộ đơn vị công việc có thể chạy lại an toàn, không chỉ quanh câu save cuối cùng. Hãy bảo đảm các side effect bên ngoài database không bị lặp lại.

## 11. Optimistic locking khác gì pessimistic locking?

Optimistic locking không giữ khóa ghi trong lúc người dùng xem và chỉnh sửa dữ liệu. Nó phát hiện xung đột tại thời điểm ghi.

Pessimistic locking yêu cầu database khóa tài nguyên để ngăn hoặc giới hạn transaction khác thay đổi dữ liệu trong phạm vi khóa. Cách khóa cụ thể phụ thuộc hệ quản trị và transaction.

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách hoạt động | So sánh version khi ghi | Lấy khóa database trước hoặc trong khi đọc/cập nhật |
| Giữ khóa khi người dùng suy nghĩ | Không | Không nên giữ transaction/lock lâu qua tương tác người dùng |
| Khi có xung đột | Một thao tác ghi thất bại do version không khớp | Transaction khác có thể phải chờ hoặc bị từ chối |
| Phù hợp | Xung đột tương đối hiếm, đọc nhiều ghi ít | Tranh chấp cao hoặc cần khóa theo quy tắc database |
| Chi phí | Cần cột version và xử lý conflict | Có thể tăng thời gian chờ, deadlock và giữ connection |
| Tính di động | Cơ chế @Version do Spring Data hỗ trợ | Cú pháp và semantics khóa phụ thuộc database/driver |

Với R2DBC, các câu lệnh như SELECT ... FOR UPDATE phụ thuộc dialect và cần được chạy trong transaction phù hợp. Không nên mở transaction rồi giữ lock trong khi chờ người dùng gửi form. Hãy chọn chiến lược theo mẫu truy cập dữ liệu và mức độ tranh chấp thực tế.

## 12. Những giới hạn và trường hợp cần cân nhắc

### 12.1. Tất cả luồng ghi phải tôn trọng version

@Version bảo vệ các thao tác được thực hiện qua cơ chế mapping có áp dụng optimistic locking. Nếu một tác vụ khác cập nhật trực tiếp SQL mà không tăng version, entity trong ứng dụng có thể không phát hiện được thay đổi đó.

Ví dụ, một script chạy:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE id = 42;
~~~

mà không tăng version. Entity đang giữ version cũ có thể vẫn khớp version trong database và ghi đè thay đổi của script. Nếu có nhiều writer, tất cả luồng cập nhật cần tuân theo quy ước version hoặc một cơ chế đồng bộ thống nhất.

### 12.2. Version không thay thế constraint nghiệp vụ

@Version không ngăn email bị trùng, số lượng âm hoặc foreign key không hợp lệ. Những quy tắc đó cần được bảo vệ bằng UNIQUE, CHECK, NOT NULL, FOREIGN KEY và validation nghiệp vụ thích hợp.

Optimistic locking chỉ phát hiện một entity đã bị thay đổi theo version. Nó không kiểm tra mọi bất biến trên nhiều hàng hoặc nhiều bảng.

### 12.3. Version của aggregate và dữ liệu con

Spring Data Relational tổ chức mapping quanh aggregate root. Khi thiết kế version, hãy xác định aggregate root nào đại diện cho đơn vị nhất quán nghiệp vụ. Đừng mặc định rằng mỗi bảng con hoặc mọi object lồng nhau đều có một version độc lập chỉ vì aggregate root có @Version.

Nếu dữ liệu con được cập nhật bằng SQL riêng hoặc một repository khác ngoài cơ chế lưu aggregate, hãy xác định rõ liệu thao tác đó có cần tăng version của root hay không. Các writer cần phối hợp theo cùng quy tắc để tránh thay đổi không được phát hiện.

### 12.4. Xóa cascade và thao tác ngoài aggregate

Foreign key ON DELETE CASCADE có thể xóa hàng con ở database khi hàng cha bị xóa. Đây là cơ chế toàn vẹn tham chiếu của database, không tự động có nghĩa mọi hàng con đều được kiểm tra version riêng.

Nếu nghiệp vụ cần kiểm tra phiên bản của nhiều bản ghi hoặc lưu lịch sử, hãy thiết kế quy trình xóa rõ ràng thay vì dựa hoàn toàn vào cascade.

## 13. Các lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Quên khai báo @Version | Update có thể ghi đè dữ liệu cũ | Thêm thuộc tính version và migration |
| Database thiếu cột version | SQL được sinh không khớp schema | Tạo migration trước khi triển khai code |
| Tự tăng version trước save | Điều kiện kiểm tra version có thể sai | Để Spring Data quản lý version |
| Dùng lại entity cũ sau khi save | Tiếp tục mang version đã lỗi thời | Dùng entity được save trả về |
| Retry cùng entity stale | Lặp lại cùng xung đột | Tải lại, kiểm tra và áp dụng lại ý định |
| Bắt mọi exception rồi retry | Lặp lỗi constraint, timeout hoặc lỗi kết nối | Chỉ xử lý OptimisticLockingFailureException theo chính sách |
| Dùng deleteById khi cần expected version | Không truyền được version mà client đã đọc | Dùng entity có version hoặc SQL có điều kiện |
| SQL tùy chỉnh không tăng version | Luồng khác có thể không phát hiện thay đổi | Thêm điều kiện và tăng version thủ công |
| Coi conflict là lỗi database bất thường | Trải nghiệm người dùng không rõ ràng | Chuyển thành 409/412 hoặc quy trình tải lại |
| Mở transaction quá lâu | Giữ connection và tăng tranh chấp | Giới hạn transaction trong thao tác database |
| Nghĩ transaction tự ngăn lost update | Hai transaction vẫn có thể cùng đọc version cũ | Dùng @Version hoặc chiến lược khóa phù hợp |
| Không kiểm tra mọi writer | Script hoặc service khác bỏ qua version | Thống nhất quy ước cập nhật trên mọi luồng |

## 14. Quy trình triển khai optimistic locking

Khi bổ sung kiểm soát version cho một entity, hãy thực hiện theo trình tự:

1. Xác định entity hoặc aggregate root có nguy cơ bị cập nhật/xóa đồng thời.
2. Thêm thuộc tính version với kiểu số nguyên phù hợp và annotation @Version.
3. Tạo migration bổ sung cột version cho schema hiện tại, khởi tạo giá trị cho các hàng cũ.
4. Kiểm tra cách Spring Data nhận diện entity mới và quản lý version theo phiên bản framework.
5. Cập nhật service để dùng entity được repository đọc và truyền entity đó vào save/delete.
6. Xử lý OptimisticLockingFailureException thành lỗi xung đột nghiệp vụ.
7. Nếu API cần kiểm soát phiên bản từ client, đưa version vào DTO hoặc dùng ETag/If-Match.
8. Với SQL tùy chỉnh, thêm expected version vào WHERE, tăng version và kiểm tra rowsUpdated.
9. Xem xét transaction reactive khi nghiệp vụ cập nhật nhiều bảng.
10. Xác định retry có an toàn không; nếu retry, phải tải lại dữ liệu và áp dụng lại ý định.
11. Kiểm tra mọi luồng ghi khác như batch job, script hoặc service tích hợp.
12. Viết integration test với hai bản đọc cùng version và hai thao tác ghi cạnh tranh.

## 15. Kiểm thử xung đột phiên bản

Một integration test quan trọng là mô phỏng hai request cùng đọc một entity trước khi một trong hai lưu.

Ví dụ cấu trúc:

~~~java
@Test
void shouldRejectUpdateFromStaleVersion() {
    Mono<Order> result = orderRepository.findById(42L)
        .flatMap(firstRead ->
            orderRepository.findById(42L)
                .flatMap(secondRead -> {
                    firstRead.setStatus("PAID");
                    secondRead.setStatus("CANCELLED");

                    return orderRepository.save(firstRead)
                        .then(orderRepository.save(secondRead));
                })
        );

    StepVerifier.create(result)
        .expectError(OptimisticLockingFailureException.class)
        .verify();
}
~~~

Ví dụ này minh họa hai bản entity được đọc trước khi lưu. Thao tác lưu đầu tiên tăng version; thao tác lưu thứ hai dùng version cũ nên phải thất bại. Tùy cách tổ chức transaction và test fixture, hãy bảo đảm hai lần đọc thật sự xảy ra trước lần save đầu tiên như ví dụ.

Các test nên xác nhận thêm:

- Sau lần save thành công, version tăng theo quy ước framework.
- Entity trả về từ save mang version mới.
- Lưu entity stale phát sinh lỗi optimistic locking.
- Xóa entity stale phát sinh conflict nếu thao tác xóa có version.
- Câu SQL tùy chỉnh với expectedVersion không cập nhật hàng khi version sai.
- Lỗi conflict được chuyển thành phản hồi API phù hợp.
- Retry tải lại entity và không lặp side effect ngoài database.

Hãy dùng integration test với R2DBC driver và database thực tế của dự án. Test giả lập repository có thể không thể hiện chính xác câu SQL có điều kiện version và hành vi concurrency của driver.

## 16. Bài tập tự kiểm tra

### Bài 1: Phát hiện lost update

Hai người cùng đọc một sản phẩm với quantity = 10 và version = 2. Người A cập nhật quantity = 9 thành công. Người B sau đó lưu quantity = 8 từ entity cũ. Nếu dùng @Version, điều gì xảy ra?

Gợi ý: A tăng version. B vẫn gửi version 2, trong khi database đã có version mới, nên thao tác của B thất bại với lỗi optimistic locking.

### Bài 2: Khai báo version

Hãy thêm version cho entity Customer có ID kiểu Long.

Gợi ý:

~~~java
@Id
private Long id;

@Version
private Long version;
~~~

Đồng thời tạo cột version tương ứng trong schema và migration cho dữ liệu hiện có.

### Bài 3: Xử lý conflict

Khi save phát sinh OptimisticLockingFailureException, có nên retry lại đúng entity cũ không?

Gợi ý: Không. Entity cũ vẫn mang version không khớp. Cần tải lại, kiểm tra nghiệp vụ và áp dụng lại thay đổi nếu việc đó an toàn.

### Bài 4: Xóa theo expected version

Client đọc đơn hàng với version 7 rồi gửi yêu cầu xóa. Trong lúc đó, một người khác cập nhật đơn hàng lên version 8. Server nên làm gì?

Gợi ý: So sánh expected version 7 với dữ liệu mới nhất và từ chối yêu cầu nếu đã khác. Nếu dùng entity-based delete, giữ version đọc được và để thao tác delete kiểm tra lại ở database nhằm bảo vệ race condition sau bước so sánh.

### Bài 5: SQL tùy chỉnh

Viết câu UPDATE chỉ thay đổi status nếu version hiện tại bằng expectedVersion.

Gợi ý:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Kiểm tra số hàng bị ảnh hưởng để xác định thành công hay conflict.

### Bài 6: Phân biệt lỗi

Một thao tác save bị từ chối vì email vi phạm UNIQUE. Có nên chuyển lỗi này thành optimistic lock conflict không?

Gợi ý: Không. Unique constraint violation là lỗi toàn vẹn dữ liệu khác với OptimisticLockingFailureException. Cần ánh xạ lỗi theo nguyên nhân thực tế.

### Bài 7: Transaction có thay thế @Version không?

Hai transaction cùng đọc một bản ghi rồi lần lượt cập nhật. Chỉ dùng @Transactional có chắc chắn ngăn lost update không?

Gợi ý: Không. Transaction bảo vệ nhóm thao tác theo isolation level, nhưng không tự động so sánh version của entity. @Version cung cấp kiểm tra phiên bản ở thao tác ghi.

## 17. Ghi nhớ

- Optimistic locking phát hiện dữ liệu đã thay đổi kể từ lúc entity được đọc.
- Spring Data Relational dùng @Version để quản lý phiên bản của entity.
- Schema cần có cột version tương thích với kiểu Java.
- Khi update, version hiện tại được đưa vào điều kiện ghi và tăng sau khi lưu thành công.
- Nếu không có hàng khớp ID và version, thao tác có thể phát sinh OptimisticLockingFailureException.
- Dùng entity được save trả về vì nó mang version mới.
- Xóa entity có version có thể kiểm tra version; nếu cần bảo vệ theo version client đã đọc, hãy truyền expected version qua quy trình xóa.
- Không retry mù quáng entity stale; phải tải lại và áp dụng lại thay đổi theo quy tắc nghiệp vụ.
- Retry chỉ an toàn khi thao tác và side effect có tính idempotent hoặc được bảo vệ riêng.
- SQL tùy chỉnh phải tự thêm điều kiện version, tăng version và kiểm tra số hàng bị ảnh hưởng.
- Transaction và optimistic locking bổ sung cho nhau: transaction quản lý tính nguyên tử, @Version phát hiện cập nhật cạnh tranh.
- Mọi writer cần tuân theo quy ước version; constraint SQL vẫn cần để bảo vệ các bất biến dữ liệu khác.
- Với API, có thể đưa version vào DTO hoặc dùng ETag/If-Match để client thể hiện phiên bản mà họ đã đọc.

Khi thiết kế cập nhật hoặc xóa dữ liệu có khả năng xảy ra cạnh tranh, hãy dùng @Version ở entity phù hợp, để Spring Data kiểm tra version tại database và xử lý conflict như một kết quả nghiệp vụ có thể dự đoán. Cơ chế này giúp ngăn ghi đè âm thầm, đồng thời cho phép ứng dụng quyết định tải lại, kết hợp thay đổi hoặc yêu cầu người dùng xác nhận lại.

