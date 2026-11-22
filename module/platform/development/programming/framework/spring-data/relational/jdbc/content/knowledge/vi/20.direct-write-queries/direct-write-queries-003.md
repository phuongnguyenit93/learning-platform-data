# Đặt ranh giới giao dịch cho phương thức sửa dữ liệu

## 1. Vì sao phương thức sửa dữ liệu cần ranh giới giao dịch?

Một câu lệnh UPDATE có thể thay đổi dữ liệu thành công, nhưng nghiệp vụ thường gồm nhiều thao tác cần cùng thành công hoặc cùng thất bại. Ví dụ, khi chuyển tiền giữa hai tài khoản, hệ thống phải trừ tiền ở tài khoản nguồn và cộng tiền vào tài khoản đích. Nếu bước đầu đã ghi nhưng bước sau lỗi, dữ liệu sẽ mất cân bằng nếu hai thao tác không nằm trong cùng một transaction.

Spring Data JDBC cho phép viết SQL sửa dữ liệu trực tiếp bằng @Modifying kết hợp @Query. Cách này hữu ích cho những cập nhật có điều kiện, cập nhật số lượng lớn hoặc thao tác không cần tải toàn bộ aggregate. Tuy nhiên, câu SQL sửa dữ liệu không tự quyết định ranh giới nghiệp vụ của transaction. Ứng dụng cần xác định rõ:

- Transaction bắt đầu ở đâu và kết thúc ở đâu?
- Những lệnh ghi nào phải commit hoặc rollback cùng nhau?
- Điều gì xảy ra nếu một bước không cập nhật được hàng nào?
- Lỗi nào phải làm transaction rollback?
- Cập nhật trực tiếp có bỏ qua invariant, version hoặc hành vi của aggregate không?

Trong bài này, ta sẽ thiết kế ranh giới transaction cho phương thức sửa dữ liệu với Spring Data JDBC, tập trung vào @Transactional, @Modifying, @Query và application service.

## 2. Transaction bảo đảm điều gì?

Transaction cơ sở dữ liệu gom một hoặc nhiều thao tác thành một đơn vị commit/rollback. Các thuộc tính ACID thường được nhắc đến:

| Thuộc tính | Ý nghĩa trong thao tác sửa dữ liệu |
| --- | --- |
| Atomicity | Các thay đổi thuộc transaction được commit cùng nhau hoặc rollback cùng nhau. |
| Consistency | Các ràng buộc và quy tắc được bảo vệ để trạng thái dữ liệu hợp lệ sau transaction. |
| Isolation | Các transaction đồng thời không nhìn thấy hoặc can thiệp vào nhau ngoài mức isolation đã chọn. |
| Durability | Sau khi commit thành công, thay đổi được database bảo đảm lưu theo chính sách của nó. |

@Transactional của Spring xác định phạm vi transaction cho một lời gọi phương thức. Khi phương thức kết thúc bình thường, transaction interceptor commit; khi gặp lỗi thuộc chính sách rollback, interceptor rollback.

Điều quan trọng là transaction **không tự động bảo vệ mọi quy tắc nghiệp vụ**. Nó giúp các thao tác database trong phạm vi đó có tính nguyên tử và áp dụng isolation tương ứng. Ứng dụng vẫn phải xác định điều kiện cập nhật, kiểm tra số hàng bị ảnh hưởng, dùng constraint và xử lý cạnh tranh phù hợp.

## 3. @Modifying và @Query trong Spring Data JDBC

Một query method thông thường thường trả về dữ liệu:

~~~java
@Query("""
    SELECT id, name, available
    FROM inventory
    WHERE id = :id
    """)
Optional<Inventory> findInventory(@Param("id") Long id);
~~~

Khi câu SQL thay đổi dữ liệu, đánh dấu method bằng @Modifying:

~~~java
@Modifying
@Query("""
    UPDATE inventory
    SET available = available - :quantity
    WHERE id = :id
    """)
int decreaseAvailable(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

@Query cung cấp câu SQL. @Modifying cho Spring Data JDBC biết đây là query sửa dữ liệu, không phải query đọc result set. Kiểu trả về số nguyên có thể dùng để nhận số hàng bị ảnh hưởng, giúp service biết câu lệnh đã cập nhật được bao nhiêu hàng.

Các điểm cần phân biệt:

- @Modifying **không phải** annotation mở transaction.
- @Query **không tự tạo** ranh giới nghiệp vụ gồm nhiều thao tác.
- Việc một repository method được gọi không có nghĩa mọi lệnh sửa liên quan tự động cùng transaction.
- Hãy cấu hình transaction tại nơi thể hiện use case, thường là application service.

Với query method khai báo trực tiếp, không nên mặc định chúng có cùng cấu hình transaction với các phương thức CRUD kế thừa. Cấu hình mặc định của repository CRUD và các query method khai báo là hai vấn đề riêng; hãy đặt @Transactional tường minh ở service hoặc method cần transaction.

## 4. Đặt transaction ở application service

Giả sử hệ thống có nghiệp vụ đặt chỗ tồn kho. Khi khách đặt một số lượng hàng, ứng dụng cần:

1. Giảm số lượng có thể bán nếu còn đủ hàng.
2. Tạo bản ghi reservation.
3. Nếu không tạo được reservation, hoàn tác việc giảm tồn kho.

Đây là một use case gồm nhiều thao tác ghi. Ranh giới phù hợp thường là phương thức service thực hiện toàn bộ nghiệp vụ.

### 4.1. Repository khai báo câu lệnh sửa trực tiếp

~~~java
package com.example.inventory;

import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available = available - :quantity
        WHERE id = :id
          AND available >= :quantity
        """)
    int reserveIfAvailable(
            @Param("id") Long id,
            @Param("quantity") int quantity
    );
}
~~~

Điều kiện available >= :quantity nằm ngay trong câu UPDATE. Database kiểm tra và cập nhật trong cùng một statement. Cách này tránh mẫu thao tác dễ gặp race condition:

~~~text
T1: SELECT available = 5
T2: SELECT available = 5
T1: kiểm tra 5 >= 4
T2: kiểm tra 5 >= 4
T1: UPDATE available = 1
T2: UPDATE available = 1
~~~

Nếu cả hai transaction đều đọc số lượng cũ rồi ghi một giá trị tính từ snapshot đó, kết quả có thể không phản ánh cả hai lượt đặt hàng. Cập nhật có điều kiện giúp database kiểm tra và thực hiện phép trừ trong một câu lệnh nguyên tử theo semantics của database.

### 4.2. Service điều phối nhiều thao tác trong cùng transaction

~~~java
package com.example.inventory;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {

    private final InventoryRepository inventory;
    private final ReservationRepository reservations;

    public ReservationService(
            InventoryRepository inventory,
            ReservationRepository reservations
    ) {
        this.inventory = inventory;
        this.reservations = reservations;
    }

    @Transactional
    public Long reserve(Long inventoryId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        int changed = inventory.reserveIfAvailable(
                inventoryId,
                quantity
        );

        if (changed != 1) {
            throw new IllegalStateException(
                    "Inventory not found or insufficient quantity");
        }

        Reservation reservation = new Reservation(
                inventoryId,
                quantity
        );

        Reservation saved = reservations.save(reservation);
        return saved.id();
    }
}
~~~

Trong ví dụ, ReservationRepository là repository CRUD cho bảng reservation và Reservation là aggregate tương ứng. Các lớp này được lược bớt để tập trung vào ranh giới transaction.

Luồng xử lý:

1. Spring mở transaction khi lời gọi đi qua proxy của ReservationService.
2. reserveIfAvailable chạy câu UPDATE có điều kiện.
3. Nếu số hàng bị ảnh hưởng không bằng 1, service ném exception.
4. Nếu cập nhật tồn kho thành công, service lưu reservation.
5. Khi phương thức kết thúc bình thường, transaction commit.
6. Nếu bước lưu reservation lỗi và exception kích hoạt rollback, cả thay đổi tồn kho cũng rollback.

Hai thao tác repository tham gia cùng transaction khi chúng sử dụng cùng transaction manager và cùng resource/database phù hợp. Không cần tự mở một transaction riêng cho từng lệnh.

## 5. Kiểm tra số hàng bị ảnh hưởng

Một phương thức sửa dữ liệu thường nên trả về số hàng bị ảnh hưởng:

~~~java
@Modifying
@Query("""
    UPDATE accounts
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

Service kiểm tra kết quả:

~~~java
@Transactional
public void blockAccount(Long id) {
    int updated = accounts.updateStatus(id, "BLOCKED");

    if (updated == 0) {
        throw new AccountNotFoundException(id);
    }
    if (updated > 1) {
        throw new IllegalStateException(
                "Expected one account to be updated");
    }
}
~~~

Với một khóa chính duy nhất, kết quả hợp lệ thường là 0 hoặc 1:

- 0: không có hàng thỏa điều kiện; có thể ID không tồn tại hoặc điều kiện bổ sung không đạt.
- 1: đúng một hàng được cập nhật.
- Lớn hơn 1: có thể điều kiện WHERE quá rộng hoặc schema không bảo đảm tính duy nhất như dự kiến.

Không nên mặc định số hàng bằng 0 luôn có nghĩa “không tồn tại”. Nếu WHERE có điều kiện trạng thái, tenant hoặc số dư, hàng có thể tồn tại nhưng không thỏa điều kiện. Hãy thiết kế exception và phản hồi theo semantics nghiệp vụ.

## 6. Khi nào đặt @Transactional ở repository, khi nào ở service?

Có thể đặt @Transactional ở nhiều lớp, nhưng mỗi vị trí thể hiện một ý nghĩa khác nhau.

### 6.1. Ở application service — lựa chọn thường nên ưu tiên

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final AuditRepository audit;

    @Transactional
    public void approve(Long orderId) {
        int changed = orders.markApproved(orderId);
        if (changed != 1) {
            throw new IllegalStateException("Order cannot be approved");
        }

        audit.save(new AuditEntry(orderId, "APPROVED"));
    }
}
~~~

Transaction thể hiện rõ use case approve: cập nhật đơn hàng và ghi audit phải cùng thành công. Service có cái nhìn đầy đủ về các bước và quy tắc nghiệp vụ.

### 6.2. Ở repository method — khi một thao tác riêng cần transaction

Một method repository có thể được đánh dấu @Transactional nếu chính method đó được thiết kế như một thao tác hoàn chỉnh và cần transaction khi được gọi độc lập:

~~~java
@Transactional
@Modifying
@Query("""
    UPDATE customers
    SET active = false
    WHERE id = :id
    """)
int deactivate(@Param("id") Long id);
~~~

Tuy nhiên, nếu service gọi nhiều repository method và chúng phải cùng commit/rollback, transaction ở service vẫn quan trọng. Một transaction do service mở sẽ là ranh giới bao ngoài; các thao tác bên trong thường tham gia transaction hiện có với propagation mặc định REQUIRED.

### 6.3. Không đặt transaction tùy tiện ở cả hai nơi

Gắn @Transactional lên mọi repository method và mọi service method mà không hiểu propagation có thể làm ranh giới khó đọc. Hãy chọn nơi sở hữu use case:

- Service: transaction bao phủ nghiệp vụ gồm nhiều bước.
- Repository: transaction cho một thao tác độc lập khi có lý do cụ thể.
- Không dùng annotation chỉ để “cho chắc” nếu chưa biết method có được gọi qua proxy hay các thao tác có dùng chung transaction manager không.

## 7. Propagation: các phương thức tham gia transaction thế nào?

@Transactional mặc định dùng propagation REQUIRED. Nếu chưa có transaction, Spring bắt đầu một transaction mới; nếu đã có transaction, lời gọi tham gia transaction hiện tại.

| Propagation | Hành vi khái quát | Trường hợp sử dụng |
| --- | --- | --- |
| REQUIRED | Tham gia transaction hiện có hoặc tạo mới | Mặc định phù hợp cho phần lớn use case |
| REQUIRES_NEW | Tạm treo transaction hiện tại và mở transaction độc lập | Một thao tác cần commit riêng, độc lập với kết quả transaction ngoài |
| SUPPORTS | Tham gia nếu có; nếu không thì chạy không có transaction | Một thao tác có thể chạy cả trong và ngoài transaction |
| MANDATORY | Yêu cầu caller đã có transaction | Buộc một service chỉ được gọi trong transaction do caller quản lý |
| NOT_SUPPORTED | Tạm treo transaction hiện có và chạy không transaction | Một thao tác không nên chạy trong transaction |
| NEVER | Báo lỗi nếu đã có transaction | Buộc caller không được mở transaction |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ | Một phần công việc có thể rollback về savepoint |

### 7.1. Vì sao không nên dùng REQUIRES_NEW tùy tiện?

Giả sử service ngoài cập nhật đơn hàng, rồi gọi service audit có REQUIRES_NEW. Audit có thể commit ngay cả khi transaction ngoài sau đó rollback. Điều này có thể đúng nếu audit cần ghi nhận một lần thử bất kể nghiệp vụ chính thất bại; nhưng nếu audit được hiểu là “đơn đã được duyệt”, dữ liệu sẽ mâu thuẫn.

Hãy chọn REQUIRES_NEW chỉ khi transaction độc lập là yêu cầu nghiệp vụ rõ ràng. Với phần lớn các bước ghi phải cùng thành công hoặc thất bại, REQUIRED là lựa chọn tự nhiên.

### 7.2. Transaction manager và database resource

Một transaction chỉ bao phủ các thao tác tham gia cùng transaction manager/resource phù hợp. Nếu hai repository kết nối hai database độc lập hoặc một bước gọi HTTP service, @Transactional trên một datasource không tự làm các thao tác đó nguyên tử cùng nhau.

Với nhiều hệ thống, cần thiết kế saga, outbox, giao dịch phân tán hoặc cơ chế bù trừ tùy yêu cầu. Không giả định một annotation có thể commit/rollback đồng thời database, message broker và dịch vụ HTTP.

## 8. Rollback: exception nào làm transaction bị hủy?

Theo quy tắc mặc định phổ biến của Spring transaction:

- RuntimeException và Error làm transaction rollback.
- Checked exception không tự động kích hoạt rollback nếu không cấu hình chính sách tương ứng.

Ví dụ:

~~~java
@Transactional
public void updateAndValidate(Long id) {
    repository.updateStatus(id, "ACTIVE");
    throw new IllegalStateException("Validation failed");
}
~~~

Vì IllegalStateException là unchecked exception, transaction mặc định rollback.

Nếu nghiệp vụ ném checked exception và muốn rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importAndSave() throws IOException {
    // Ghi dữ liệu...
    throw new IOException("Import failed");
}
~~~

Có thể cấu hình rollbackFor cho kiểu exception phù hợp. Không nên bắt exception rồi bỏ qua mà vẫn để method kết thúc bình thường:

~~~java
@Transactional
public void updateAccount(Long id) {
    repository.updateStatus(id, "ACTIVE");
    try {
        performAnotherWrite();
    } catch (RuntimeException ex) {
        log.error("Write failed", ex);
        // Nếu nuốt exception, transaction có thể vẫn commit.
    }
}
~~~

Nếu lỗi phải làm hủy toàn bộ nghiệp vụ, hãy ném exception ra khỏi ranh giới transactional method hoặc đánh dấu transaction rollback-only bằng cơ chế phù hợp. Ghi log rồi tiếp tục commit có thể tạo trạng thái một phần ngoài ý muốn.

## 9. Transactional proxy và self-invocation

Trong cấu hình Spring thông thường, @Transactional được áp dụng thông qua proxy. Lời gọi từ bean khác đi qua proxy sẽ kích hoạt transaction interceptor.

Một lỗi phổ biến là tự gọi phương thức transactional trong cùng object:

~~~java
@Service
public class ImportService {

    public void importAll() {
        saveOne(); // Gọi trực tiếp trên this, không qua proxy.
    }

    @Transactional
    public void saveOne() {
        // Không nên giả định transaction được mở bởi self-invocation.
    }
}
~~~

Lời gọi saveOne() từ importAll() là self-invocation; trong proxy mode mặc định, nó không đi qua proxy và annotation trên saveOne() có thể không được áp dụng như kỳ vọng.

Cách tổ chức rõ hơn là đặt transaction trên phương thức public được gọi từ bên ngoài:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importAll() {
        saveOne();
        saveAnother();
    }

    private void saveOne() {
        // Các thao tác ghi tham gia transaction của importAll.
    }

    private void saveAnother() {
        // Các thao tác ghi tham gia transaction của importAll.
    }
}
~~~

Hoặc tách use case/transactional operation sang một bean khác nếu cần ranh giới riêng. Cần lưu ý thêm các giới hạn proxy như method không thể được proxy theo cách cấu hình, method final/private và kiểu proxy đang sử dụng.

## 10. readOnly không phải cơ chế khóa ghi

Một method đọc thường được đánh dấu:

~~~java
@Transactional(readOnly = true)
public Customer findCustomer(Long id) {
    return customers.findById(id).orElseThrow();
}
~~~

readOnly = true biểu đạt ý định chỉ đọc và có thể giúp transaction manager/provider tối ưu phù hợp. Nhưng không nên coi nó là một cơ chế bảo mật hoặc bảo đảm tuyệt đối rằng mọi lệnh ghi sẽ bị chặn. Hành vi cụ thể phụ thuộc transaction manager, database và driver.

Với phương thức sửa dữ liệu, dùng transaction ghi thông thường:

~~~java
@Transactional
public void changeStatus(Long id, String status) {
    int changed = customers.updateStatus(id, status);
    if (changed != 1) {
        throw new IllegalStateException("Customer was not updated");
    }
}
~~~

Không đánh dấu một use case ghi là read-only chỉ vì nó có một bước đọc trước khi cập nhật.

## 11. Isolation và cập nhật đồng thời

@Transactional mặc định sử dụng isolation DEFAULT, tức là dùng mức mặc định do database/transaction manager quy định. Một transaction bảo đảm nguyên tử không có nghĩa là mọi race condition đều tự biến mất.

### 11.1. Cập nhật có điều kiện

Với thao tác giảm tồn kho, câu SQL:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE id = :id
  AND available >= :quantity;
~~~

giúp database kiểm tra điều kiện tại thời điểm cập nhật. Service cần kiểm tra số hàng bị ảnh hưởng để biết thao tác có thành công hay không.

### 11.2. Optimistic locking

Nếu dùng @Version trên aggregate root và gọi repository.save(aggregate), Spring Data JDBC có thể dùng version để phát hiện cập nhật cạnh tranh. Nhưng câu SQL @Modifying tự viết không tự động đi qua cơ chế lưu aggregate có version.

Nếu muốn cập nhật trực tiếp có optimistic locking, phải đưa version vào điều kiện và tăng version trong cùng câu lệnh:

~~~sql
UPDATE accounts
SET balance = :newBalance,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Sau đó kiểm tra số hàng bị ảnh hưởng:

- 1: cập nhật thành công theo version đã đọc.
- 0: ID không tồn tại hoặc version đã thay đổi; cần phân biệt theo nhu cầu nghiệp vụ.

Đây là ví dụ SQL khái niệm. Kiểu version, cách tăng version và mapping phải nhất quán với model. Không để câu @Modifying bỏ qua version trong khi các luồng khác dựa vào optimistic locking.

### 11.3. Pessimistic locking và isolation

Một số nghiệp vụ cần khóa hàng hoặc isolation cao hơn, nhưng việc chọn SELECT ... FOR UPDATE, mức isolation hoặc lock timeout phụ thuộc database và driver. Hãy chỉ dùng khi có lý do rõ ràng, kiểm tra execution plan/lock behavior và thiết kế thứ tự khóa nhất quán để giảm nguy cơ deadlock.

Không tăng isolation lên mức cao nhất cho mọi method. Isolation cao hơn có thể giảm một số bất thường nhưng cũng làm giảm concurrency hoặc tăng chi phí lock/retry.

## 12. Cập nhật trực tiếp có thể bỏ qua hành vi aggregate

Một method @Modifying chạy SQL trực tiếp. Nó không tải aggregate rồi gọi hành vi miền. Vì vậy, nó có thể bỏ qua:

- Invariant được kiểm tra trong aggregate root.
- Quy tắc chuyển trạng thái.
- Logic tính toán hoặc chuẩn hóa trong domain model.
- Cơ chế optimistic locking được áp dụng trong đường save.
- Callback hoặc quy trình do ứng dụng gắn với việc lưu aggregate.
- Việc đồng bộ các entity con thuộc aggregate.

Ví dụ, nếu một đơn hàng chỉ được hủy khi còn ở trạng thái DRAFT, câu SQL:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id;
~~~

có thể hủy cả đơn đã gửi. Câu lệnh an toàn hơn phải thể hiện điều kiện:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id
  AND status = 'DRAFT';
~~~

Sau đó service kiểm tra row count. Tuy vậy, nếu hành vi hủy còn phải ghi audit, giải phóng reservation hoặc phát sự kiện, cần một application service điều phối toàn bộ bước đó trong transaction phù hợp.

Hãy chọn SQL sửa trực tiếp khi thao tác phù hợp với chính sách nghiệp vụ và có thể bảo vệ các invariant cần thiết bằng điều kiện SQL/constraint. Nếu nghiệp vụ có hành vi phong phú, tải aggregate, gọi hành vi root và save thường diễn đạt rõ hơn.

## 13. Không giữ transaction database trong lúc gọi dịch vụ bên ngoài

Ví dụ cần tránh:

~~~java
@Transactional
public void approve(Long orderId) {
    orders.markApproved(orderId);
    emailClient.sendApprovalEmail(orderId);
    remoteBilling.capture(orderId);
}
~~~

Lời gọi HTTP/email có thể chậm hoặc thất bại, khiến transaction database giữ connection và lock trong thời gian dài. Ngoài ra, transaction database không thể rollback email đã gửi hoặc một khoản thanh toán đã được hệ thống khác chấp nhận.

Một cách thiết kế thường gặp:

~~~text
Application service
  -> cập nhật dữ liệu nghiệp vụ
  -> ghi outbox event trong cùng transaction
  -> commit

Outbox publisher
  -> đọc event đã commit
  -> gửi tới broker/dịch vụ ngoài
  -> retry và đánh dấu đã gửi
~~~

Transactional outbox giúp ghi thay đổi nghiệp vụ và thông điệp cần phát trong cùng database transaction. Việc gửi tới hệ thống ngoài diễn ra sau commit và cần idempotency/retry phù hợp.

Với nghiệp vụ nhiều bước qua nhiều dịch vụ, cân nhắc saga và hành động bù trừ. Không giả định @Transactional cục bộ có thể rollback tài nguyên bên ngoài.

## 14. Batch update và kích thước transaction

Một transaction chứa hàng chục nghìn hoặc hàng triệu cập nhật có thể giữ connection lâu, tạo nhiều log/undo data và làm tăng áp lực lên database. Không phải lúc nào gom toàn bộ batch vào một transaction lớn cũng tốt.

Có hai cách tiếp cận:

### Một transaction cho toàn bộ batch

Phù hợp khi nghiệp vụ yêu cầu tất cả hàng được cập nhật cùng nhau và kích thước batch có giới hạn.

Ưu điểm: đơn giản về atomicity. Nhược điểm: transaction dài, rollback tốn kém và có thể giữ lock lâu.

### Chia batch thành các transaction nhỏ

Phù hợp khi có thể chấp nhận tiến độ từng phần và cần resume:

~~~java
for (List<Long> ids : batches) {
    batchWriter.updateBatch(ids);
}
~~~

Trong ví dụ, batchWriter là bean khác có phương thức @Transactional được gọi qua proxy:

~~~java
@Service
public class BatchWriter {

    private final CustomerRepository customers;

    public BatchWriter(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public void updateBatch(List<Long> ids) {
        customers.markInactive(ids);
    }
}
~~~

Mỗi batch có thể commit độc lập. Khi lỗi ở batch sau, những batch trước đã commit vẫn tồn tại; job cần checkpoint và có khả năng chạy lại an toàn. Nếu yêu cầu tất cả hoặc không có gì, chia transaction như vậy không phù hợp.

## 15. Kiểm thử ranh giới transaction

Kiểm thử không chỉ xác nhận method repository chạy được. Cần xác nhận các thao tác có cùng commit/rollback như thiết kế.

### 15.1. Kiểm thử rollback khi bước sau thất bại

Một integration test có thể:

1. Tạo inventory với số lượng 10.
2. Gọi service reserve 3 nhưng ép thao tác tạo reservation thất bại.
3. Xác nhận transaction rollback và inventory vẫn là 10.
4. Gọi lại use case thành công.
5. Xác nhận inventory còn 7 và có reservation tương ứng.

Ví dụ khung kiểm thử:

~~~java
@SpringBootTest
class ReservationServiceIntegrationTest {

    @Autowired
    ReservationService service;

    @Autowired
    InventoryRepository inventory;

    @Test
    void rollsBackInventoryWhenReservationCannotBeSaved() {
        // Arrange dữ liệu và kích hoạt lỗi ở bước lưu reservation.
        // Gọi service trong transaction riêng của service.
        // Đọc lại inventory trong transaction/test context phù hợp.
        // Assert số lượng được khôi phục.
    }
}
~~~

Đây là skeleton minh họa; cách ép lỗi có thể dùng một constraint thật hoặc test double ở đúng ranh giới. Cẩn thận với @Transactional trên chính test: test transaction bao ngoài có thể che khuất thời điểm commit thực tế. Khi kiểm thử transaction service, phải hiểu transaction của test và cách đọc lại dữ liệu.

### 15.2. Kiểm thử row count

Kiểm tra các trường hợp:

- ID tồn tại và điều kiện đạt: row count bằng 1.
- ID không tồn tại: row count bằng 0.
- Hàng tồn tại nhưng không đủ số lượng: row count bằng 0.
- Input quantity bằng 0 hoặc âm: service từ chối trước khi chạy SQL.

### 15.3. Kiểm thử concurrency

Với nghiệp vụ cập nhật đồng thời, dùng integration test chạy nhiều transaction thật trên database mục tiêu. H2 không chứng minh đầy đủ lock/isolation semantics của PostgreSQL, MySQL hoặc database production. Kiểm tra kết quả cuối, row count, exception và version theo database thực tế.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @Modifying update chạy nhưng lỗi khi có thao tác ghi thứ hai | Các bước không nằm trong cùng transaction | Đặt @Transactional ở application service bao trùm toàn use case. |
| Bước đầu đã commit dù bước sau lỗi | Hai thao tác dùng transaction riêng hoặc propagation REQUIRES_NEW | Dùng chung transaction manager và REQUIRED khi cần atomicity. |
| Lỗi xảy ra nhưng dữ liệu vẫn commit | Exception bị bắt rồi nuốt, hoặc là checked exception không nằm trong rollback rule | Ném lỗi ra ngoài hoặc cấu hình rollbackFor/rollback-only phù hợp. |
| @Transactional không có hiệu lực | Self-invocation hoặc method không đi qua proxy | Đặt annotation ở entry point được gọi qua proxy hoặc tách bean. |
| Update không đổi hàng nào | ID không tồn tại hoặc điều kiện WHERE không đạt | Kiểm tra row count và ánh xạ thành kết quả nghiệp vụ rõ ràng. |
| Cập nhật trực tiếp ghi đè dữ liệu mới | Không có điều kiện version hoặc điều kiện nghiệp vụ trong WHERE | Dùng optimistic locking/conditional update và kiểm tra row count. |
| Transaction giữ connection quá lâu | Gọi API bên ngoài hoặc xử lý batch dài trong transaction | Rút ngắn transaction, dùng outbox/chunk/checkpoint phù hợp. |
| Nghĩ readOnly chặn được mọi lệnh ghi | Hiểu nhầm readOnly là cơ chế bảo mật | Dùng transaction ghi cho use case sửa và constraint/permission cho bảo vệ dữ liệu. |
| Cập nhật SQL bỏ qua quy tắc domain | DML trực tiếp không gọi hành vi aggregate | Đưa invariant vào điều kiện SQL/constraint hoặc dùng aggregate behavior và save. |

## 17. Quy trình thiết kế ranh giới transaction

Khi thêm một phương thức sửa dữ liệu, hãy đi theo các bước:

1. **Mô tả use case:** người dùng muốn thay đổi điều gì và điều kiện thành công là gì?
2. **Liệt kê thao tác database:** có bao nhiêu lệnh insert/update/delete cần phối hợp?
3. **Xác định atomicity:** những bước nào bắt buộc cùng commit hoặc rollback?
4. **Chọn entry point:** đặt @Transactional ở application service đại diện use case.
5. **Chọn SQL sửa trực tiếp hay aggregate save:** cân nhắc invariant, entity con, version và chi phí.
6. **Kiểm tra row count:** xác định trường hợp không có hàng nào được cập nhật.
7. **Thiết kế rollback:** exception nào làm hủy transaction, có exception checked hay bị bắt lại không?
8. **Kiểm tra concurrency:** dùng conditional update, version, constraint hoặc lock phù hợp.
9. **Tách side effect:** không giữ transaction database trong lúc chờ dịch vụ ngoài; cân nhắc outbox.
10. **Kiểm thử commit/rollback:** xác nhận trạng thái database sau thành công và thất bại.

## 18. Bài tập tự thực hành

**Bài tập 1 — Cập nhật có điều kiện.** Viết repository method dùng @Modifying để giảm số lượng tồn kho khi còn đủ. Trả về row count và xử lý trường hợp không đủ hàng trong service.

**Bài tập 2 — Hai bước ghi.** Sau khi giảm tồn kho, tạo reservation. Cố tình làm bước tạo reservation thất bại và xác nhận transaction rollback cả thay đổi tồn kho.

**Bài tập 3 — Self-invocation.** Tạo hai method trong cùng service, chỉ một method có @Transactional, rồi gọi nội bộ. Quan sát transaction có được áp dụng như kỳ vọng không. Chuyển annotation lên entry point hoặc tách bean để so sánh.

**Bài tập 4 — Rollback rule.** Ném một runtime exception và một checked exception từ phương thức transactional. So sánh kết quả commit/rollback, sau đó cấu hình rollbackFor.

**Bài tập 5 — Optimistic update.** Thêm cột version và viết câu update có điều kiện WHERE id = :id AND version = :expectedVersion. Tăng version trong cùng statement và xử lý row count bằng 0.

**Bài tập 6 — REQUIRES_NEW.** Ghi một audit entry bằng service REQUIRES_NEW, sau đó làm transaction ngoài rollback. Quan sát audit có còn không và giải thích liệu đó có đúng ý nghĩa nghiệp vụ không.

**Bài tập 7 — Batch.** Viết job cập nhật nhiều khách hàng theo batch. So sánh một transaction lớn với transaction cho từng batch; xác định cách checkpoint và retry nếu batch thứ ba thất bại.

## 19. Ghi nhớ

@Modifying đánh dấu query method thực hiện lệnh sửa dữ liệu; nó không thay thế @Transactional. Với một use case có nhiều thao tác ghi, hãy đặt ranh giới transaction ở application service để các repository method cùng tham gia một transaction và commit/rollback theo kết quả nghiệp vụ.

Kiểm tra row count, chọn rollback rule rõ ràng, hiểu propagation và proxy, đồng thời bảo vệ cập nhật cạnh tranh bằng điều kiện SQL, version hoặc constraint. SQL sửa trực tiếp có thể bỏ qua hành vi aggregate và optimistic locking của đường save, vì vậy phải chủ động bảo đảm các invariant cần thiết. Transaction database cũng không bao trùm lời gọi HTTP, email hoặc broker; dùng outbox/saga khi cần phối hợp các hệ thống.

### Tài liệu tham khảo

- [Spring Data Relational – Modifying Queries](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework – @Transactional Annotation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
