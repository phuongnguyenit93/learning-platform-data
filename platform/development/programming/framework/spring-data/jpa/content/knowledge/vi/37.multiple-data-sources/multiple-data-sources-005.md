# Giới hạn tính nguyên tử khi cập nhật nhiều nguồn dữ liệu

Một ứng dụng Spring Data JPA có thể kết nối tới nhiều database, mỗi database có một `DataSource`, `EntityManagerFactory` và transaction manager riêng. Cấu hình nhiều nguồn dữ liệu giúp tách miền nghiệp vụ, dữ liệu hoặc tải truy cập. Tuy nhiên, một transaction JPA cục bộ thường chỉ bảo vệ các thao tác trên nguồn dữ liệu mà transaction manager đó quản lý.

Nếu một nghiệp vụ cập nhật hai database, ví dụ trừ tồn kho ở database kho và tạo đơn hàng ở database bán hàng, việc đặt một annotation `@Transactional` không tự bảo đảm cả hai thay đổi cùng commit hoặc cùng rollback. Đây là giới hạn quan trọng về tính nguyên tử khi làm việc với nhiều nguồn dữ liệu.

## 1. Transaction cục bộ chỉ quản lý một nguồn tài nguyên

Trong cấu hình phổ biến, mỗi `JpaTransactionManager` được gắn với một `EntityManagerFactory`. Nó quản lý transaction cho persistence context và database tương ứng.

Ví dụ ứng dụng có hai database:

- `ordersDataSource`: lưu đơn hàng.
- `inventoryDataSource`: lưu số lượng tồn kho.

Có thể cấu hình hai bộ repository riêng, mỗi bộ dùng EntityManager và transaction manager phù hợp. Khi gọi một method:

```java
@Transactional("ordersTransactionManager")
public void createOrder() {
    // Các thao tác qua OrdersEntityManagerFactory
}
```

transaction manager được chọn chỉ quản lý transaction của database đơn hàng. Nó không tự động đưa các thao tác qua `inventoryEntityManagerFactory` vào cùng transaction.

Tương tự:

```java
@Transactional("inventoryTransactionManager")
public void reserveStock() {
    // Các thao tác qua InventoryEntityManagerFactory
}
```

Đây là một transaction cục bộ khác. Mỗi transaction có thể commit hoặc rollback độc lập.

**Điểm cần nhớ:** `@Transactional` xác định ranh giới transaction theo transaction manager được chọn. Nó không có nghĩa mọi database mà ứng dụng kết nối đều tham gia transaction đó.

## 2. Vì sao một nghiệp vụ có thể chỉ thành công một nửa?

Giả sử luồng đặt hàng gồm hai thao tác:

1. Ghi đơn hàng vào database Orders.
2. Trừ số lượng sản phẩm trong database Inventory.

Nếu hai thao tác chạy bằng hai transaction manager cục bộ, có thể xảy ra trình tự:

```text
Orders DB:     BEGIN -> INSERT order -> COMMIT
Inventory DB:  BEGIN -> UPDATE stock -> ERROR -> ROLLBACK
```

Kết quả là đơn hàng đã tồn tại nhưng kho chưa trừ hàng. Nếu đảo thứ tự, tình huống ngược lại cũng có thể xảy ra: tồn kho đã giảm nhưng đơn hàng không được tạo.

Một phương thức service có thể gọi hai service con, mỗi service có `@Transactional` với manager riêng. Điều đó vẫn không tạo ra một transaction phân tán. Transaction của database thứ nhất có thể commit trước khi transaction thứ hai kết thúc. Nếu transaction thứ hai thất bại, transaction thứ nhất không tự rollback theo.

Cũng không nên hiểu `Propagation.REQUIRES_NEW` là cách gộp nhiều database vào một transaction. `REQUIRES_NEW` tạo transaction độc lập đối với transaction manager đang được chọn; nó không cung cấp cơ chế commit nguyên tử giữa các manager.

## 3. Cấu hình nhiều transaction manager một cách tường minh

Khi có nhiều datasource, nên đặt tên rõ ràng cho từng transaction manager và chỉ định manager phù hợp ở service hoặc repository.

Ví dụ minh họa cách chọn transaction manager cho từng miền:

```java
@Service
public class OrderWriter {

    private final OrderRepository orderRepository;

    public OrderWriter(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional("ordersTransactionManager")
    public void createOrder(Order order) {
        orderRepository.save(order);
    }
}
```

```java
@Service
public class InventoryWriter {

    private final InventoryRepository inventoryRepository;

    public InventoryWriter(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional("inventoryTransactionManager")
    public void reserve(Long productId, int quantity) {
        Inventory item = inventoryRepository.findById(productId)
                .orElseThrow();

        item.reserve(quantity);
    }
}
```

Các tên `ordersTransactionManager` và `inventoryTransactionManager` phải khớp với bean thực tế trong cấu hình ứng dụng. Mỗi repository cũng phải được gắn với đúng `EntityManagerFactory` và transaction manager của datasource tương ứng, thường qua các cấu hình `@EnableJpaRepositories` riêng.

Ví dụ trên minh họa hai ranh giới transaction độc lập. Nếu một service điều phối gọi cả hai writer, service điều phối không thể làm cho hai transaction cục bộ trở thành nguyên tử chỉ bằng cách thêm `@Transactional` vào chính nó.

Khi cấu hình nhiều nguồn dữ liệu, tránh dựa vào transaction manager mặc định nếu một method có thể thao tác trên nhiều miền. Chỉ định rõ manager giúp người đọc nhận biết database nào được bảo vệ bởi transaction đó.

## 4. Phương án 1: Dùng JTA/XA khi thực sự cần commit nguyên tử

Nếu nghiệp vụ bắt buộc hai database cùng commit hoặc cùng rollback, có thể cân nhắc distributed transaction bằng JTA kết hợp XA.

JTA transaction manager đóng vai trò điều phối một global transaction. Các resource tham gia phải hỗ trợ XA và được enlist vào global transaction. Với JPA, cấu hình phải dùng các resource/EntityManagerFactory và transaction integration tương thích với JTA. Chỉ có hai datasource hoặc hai JpaTransactionManager riêng là chưa đủ.

### Cách two-phase commit hoạt động

Two-phase commit (2PC) có hai giai đoạn chính:

1. **Prepare:** coordinator yêu cầu mỗi resource participant chuẩn bị commit. Database kiểm tra khả năng hoàn tất và ghi trạng thái prepared theo giao thức XA.
2. **Commit hoặc rollback:** nếu các participant đều prepare thành công, coordinator yêu cầu tất cả commit. Nếu có participant không thể prepare, coordinator yêu cầu rollback theo kết quả giao thức.

Sơ đồ khái niệm:

```text
Application
    |
    v
JTA Transaction Manager (Coordinator)
    |
    +---- prepare ----> Orders DB (XA)
    |
    +---- prepare ----> Inventory DB (XA)
    |
    +---- commit -----> Orders DB
    |
    +---- commit -----> Inventory DB
```

Khi dùng JTA, ứng dụng thường khai báo transaction theo global transaction manager đã được cấu hình:

```java
@Transactional
public void placeOrder(Order order, Long productId, int quantity) {
    orderRepository.save(order);
    inventoryRepository.reserve(productId, quantity);
}
```

Đoạn code chỉ có ý nghĩa là một global transaction khi cả hai repository thật sự tham gia cùng JTA transaction. Nếu chúng vẫn dùng hai `JpaTransactionManager` cục bộ, annotation này không tạo ra 2PC.

### Điều kiện và đánh đổi của XA

- Database và JDBC driver phải hỗ trợ XA cho resource được sử dụng.
- Connection pool và datasource phải được cấu hình theo XA; datasource JDBC thông thường không tự trở thành XA resource.
- Ứng dụng cần JTA coordinator, cấu hình enlist resource và cơ chế recovery sau khi process hoặc node gặp sự cố.
- Global transaction có thêm trao đổi mạng và bước prepare/commit, làm tăng độ trễ.
- Resource có thể giữ lock hoặc trạng thái prepared trong lúc coordinator chưa hoàn tất, ảnh hưởng throughput và khả năng phục vụ.
- Khi coordinator hoặc mạng gặp sự cố, việc khôi phục transaction cần log và quy trình recovery phù hợp. Một số tình huống hiếm có thể tạo heuristic outcome cần được vận hành xử lý.

XA phù hợp khi yêu cầu nguyên tử xuyên database là bắt buộc, các hệ thống đều hỗ trợ XA và tổ chức chấp nhận chi phí vận hành. Không nên chọn XA chỉ vì ứng dụng có nhiều datasource.

## 5. Phương án 2: Transactional Outbox và eventual consistency

Trong nhiều hệ thống, không cần tất cả database commit trong cùng một thời điểm. Điều quan trọng là thay đổi ở nguồn dữ liệu chính và ý định đồng bộ sang nguồn khác không bị mất. Transactional outbox là một lựa chọn phổ biến.

Giả sử Orders DB là nguồn dữ liệu chính khi đặt hàng. Trong cùng một transaction cục bộ, ứng dụng:

1. Lưu đơn hàng ở trạng thái `PENDING`.
2. Ghi một bản ghi vào bảng `outbox_event` mô tả yêu cầu giữ hàng.
3. Commit cả đơn hàng và outbox event cùng nhau.

Một publisher nền đọc các event chưa gửi và chuyển chúng tới message broker hoặc một worker xử lý Inventory DB. Worker cập nhật tồn kho trong transaction cục bộ của Inventory DB, rồi ghi nhận event đã xử lý. Sau khi giữ hàng thành công, một event phản hồi có thể được gửi về để cập nhật đơn hàng thành `CONFIRMED`. Nếu kho không đủ, đơn hàng có thể chuyển sang `REJECTED`.

Ví dụ luồng:

```text
Orders DB transaction
    |
    +-- INSERT order (PENDING)
    |
    +-- INSERT outbox event (ReserveStock)
    |
    +-- COMMIT
             |
             v
       Outbox publisher
             |
             v
        Message broker
             |
             v
Inventory DB transaction
    |
    +-- Reserve stock
    |
    +-- Record processed event
    |
    +-- COMMIT
             |
             v
       Reservation result
             |
             v
Orders DB: CONFIRMED / REJECTED
```

Outbox loại bỏ khoảng trống nguy hiểm giữa commit dữ liệu Orders và việc lưu ý định gửi thông điệp: nếu transaction Orders rollback, hàng outbox cũng rollback; nếu commit thành công, event vẫn còn để publisher gửi lại sau sự cố.

Đây là eventual consistency. Trong một khoảng thời gian ngắn, Orders DB có thể đang ở trạng thái `PENDING` trong khi Inventory DB chưa xử lý. Ứng dụng cần mô hình hóa trạng thái trung gian và chỉ báo hoàn tất nghiệp vụ sau khi nhận kết quả phù hợp.

## 6. Thiết kế consumer idempotent và xử lý gửi trùng

Transactional outbox không bảo đảm broker chỉ nhận một message đúng một lần. Ví dụ publisher gửi message thành công nhưng process chết trước khi đánh dấu outbox row đã gửi. Khi chạy lại, publisher có thể gửi message đó lần nữa.

Vì vậy consumer cần idempotent. Một cách thường dùng là cấp `eventId` duy nhất và lưu ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ ở database đích.

Ví dụ bảng nhận event:

```sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Luồng consumer:

1. Nhận message và lấy `eventId`.
2. Bắt đầu transaction ở database đích.
3. Thử ghi `eventId` vào `processed_event`.
4. Nếu ID đã tồn tại, coi đây là message trùng và không áp dụng thay đổi lần nữa.
5. Nếu ID mới, thực hiện cập nhật nghiệp vụ trong cùng transaction.
6. Commit rồi mới xác nhận message với broker.

Ràng buộc khóa chính giúp database xử lý cạnh tranh giữa hai consumer cùng nhận một event. Nếu ghi dấu đã xử lý và cập nhật tồn kho ở hai transaction khác nhau, hệ thống vẫn có thể đánh dấu event hoàn tất dù thay đổi tồn kho thất bại, hoặc ngược lại.

Consumer idempotent giúp xử lý an toàn khi message được gửi lại. Nó không tự tạo exactly-once delivery trên toàn hệ thống; mục tiêu thực tế là giao nhận ít nhất một lần kết hợp xử lý hiệu quả một lần theo event ID.

## 7. Dùng Saga và compensating action cho quy trình nhiều bước

Một nghiệp vụ có nhiều bước trên nhiều database hoặc service thường được mô hình hóa bằng Saga. Mỗi bước là một transaction cục bộ. Nếu bước sau thất bại, workflow chạy các compensating action để đưa hệ thống về một trạng thái nghiệp vụ chấp nhận được.

Ví dụ đặt hàng:

| Bước | Transaction cục bộ | Bù trừ khi cần |
|---|---|---|
| 1 | Tạo đơn ở trạng thái PENDING | Hủy đơn |
| 2 | Giữ hàng trong kho | Giải phóng lượng hàng đã giữ |
| 3 | Thu tiền | Hoàn tiền |
| 4 | Xác nhận đơn | Chuyển sang trạng thái cần xử lý thủ công nếu không thể hoàn tất |

Compensation không nhất thiết là rollback vật lý. Nếu một khoản thanh toán đã được gửi tới cổng thanh toán bên ngoài, không thể xóa sự kiện đó khỏi lịch sử; hệ thống cần tạo giao dịch hoàn tiền mới.

Một Saga cần lưu trạng thái workflow, định danh bước, kết quả, số lần retry và thông tin lỗi để có thể tiếp tục sau khi process khởi động lại. Các bước phải idempotent vì message hoặc command có thể được gửi lại. Cần có timeout, retry có giới hạn, dead-letter hoặc hàng chờ xử lý thủ công và cơ chế đối soát cho các trường hợp không thể tự phục hồi.

Saga phù hợp khi nghiệp vụ chấp nhận trạng thái trung gian và cần phối hợp nhiều bước lâu dài. Nó không cung cấp rollback nguyên tử tức thời như một local database transaction.

## 8. Chọn chiến lược theo yêu cầu nghiệp vụ

| Yêu cầu | Chiến lược phù hợp |
|---|---|
| Một thao tác chỉ cập nhật một database | Transaction cục bộ với JpaTransactionManager |
| Hai database phải commit/rollback cùng nhau và đều hỗ trợ XA | JTA/XA two-phase commit |
| Cần đồng bộ sang database khác, chấp nhận trạng thái trung gian | Transactional outbox và consumer idempotent |
| Quy trình có nhiều bước, cần hành động bù khi bước sau thất bại | Saga |
| Dữ liệu được sao chép hoặc tổng hợp định kỳ, độ trễ cho phép | Job đồng bộ, CDC hoặc quy trình đối soát phù hợp |

Trước khi chọn, hãy trả lời:

- Database nào là nguồn dữ liệu chính cho từng phần dữ liệu?
- Trạng thái trung gian có được nghiệp vụ chấp nhận không?
- Nếu một database thành công và database kia thất bại, cần làm gì?
- Message có thể được gửi lại không và consumer có idempotent không?
- Có bắt buộc commit đồng thời hay chỉ cần hội tụ về trạng thái đúng?
- Hệ thống có hỗ trợ XA và đội vận hành có thể xử lý recovery không?

Nếu hai database thuộc hai miền nghiệp vụ độc lập, thường nên để mỗi miền sở hữu transaction cục bộ của mình và trao đổi qua event/command. Chỉ dùng distributed transaction khi yêu cầu nguyên tử thực sự cần thiết và được hỗ trợ đầy đủ.

## 9. Lỗi thường gặp

- **Cho rằng một `@Transactional` bao phủ mọi datasource:** annotation chỉ dùng transaction manager được chọn. Xác định manager và resource thực tế của từng repository.
- **Gọi hai service có hai transaction manager rồi kỳ vọng rollback cùng nhau:** hai transaction cục bộ commit độc lập. Chọn XA hoặc thiết kế outbox/Saga theo yêu cầu.
- **Dùng `REQUIRES_NEW` để tạo transaction xuyên database:** propagation này chỉ tạo transaction mới cho manager hiện tại, không điều phối các resource.
- **Gửi message trước khi transaction nguồn commit:** consumer có thể xử lý một thay đổi mà database nguồn sau đó rollback. Ghi outbox cùng transaction rồi publish sau commit.
- **Đánh dấu outbox đã gửi trước khi broker xác nhận:** event có thể bị mất khi publisher gặp sự cố. Thiết kế trạng thái gửi và retry cẩn thận.
- **Không chống xử lý trùng:** publisher hoặc broker có thể gửi lại. Dùng event ID, unique constraint và consumer idempotent.
- **Coi compensation là rollback:** bù trừ là một thao tác nghiệp vụ mới, có thể thất bại và cần retry hoặc can thiệp thủ công.
- **Dùng XA mà thiếu recovery:** coordinator có thể để lại transaction ở trạng thái prepared khi hệ thống gián đoạn. Cấu hình durable log và kiểm thử quy trình phục hồi.

## 10. Ghi nhớ

Transaction cục bộ của Spring Data JPA thường chỉ quản lý một `EntityManagerFactory` và datasource. Nhiều `@Transactional` với các manager khác nhau không tự tạo tính nguyên tử xuyên database. Nếu bắt buộc commit đồng thời, dùng JTA/XA với các resource hỗ trợ và cấu hình recovery đầy đủ. Nếu chấp nhận nhất quán cuối cùng, transactional outbox, consumer idempotent và Saga thường giúp phối hợp nhiều nguồn dữ liệu theo cách dễ mở rộng và vận hành hơn.