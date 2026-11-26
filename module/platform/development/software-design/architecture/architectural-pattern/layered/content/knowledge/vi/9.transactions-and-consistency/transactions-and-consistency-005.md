# Kiểm soát ghi cạnh tranh bằng optimistic locking và pessimistic locking

Khi nhiều request cùng đọc rồi cập nhật một dữ liệu, thứ tự thực thi có thể làm mất thay đổi hoặc tạo ra trạng thái không hợp lệ. Ví dụ, hai nhân viên cùng sửa số lượng tồn kho của một sản phẩm; nếu cả hai đều đọc giá trị 10 rồi lần lượt ghi 8 và 7, kết quả cuối có thể là 7 dù cả hai thay đổi đều được tính từ cùng một trạng thái ban đầu. Đây là dạng lost update.

Trong kiến trúc phân tầng, tầng ứng dụng điều phối ca sử dụng và ranh giới giao dịch; tầng truy cập dữ liệu dùng cơ chế của JPA và cơ sở dữ liệu để phát hiện hoặc ngăn ghi cạnh tranh. Hai chiến lược phổ biến là **optimistic locking** (khóa lạc quan) và **pessimistic locking** (khóa bi quan). Chúng giải quyết cùng nhóm vấn đề nhưng có cách phối hợp khác nhau: optimistic locking phát hiện xung đột khi ghi, còn pessimistic locking yêu cầu khóa dữ liệu trước khi thực hiện thay đổi.

Bài học thuộc module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, với mục tiêu học tổ chức phần mềm theo kiến trúc phân tầng. Ví dụ dùng Java, Spring và JPA để minh họa. Việc chọn chiến lược nào phụ thuộc mức tranh chấp, thời gian giữ transaction, yêu cầu nhất quán và khả năng chịu retry của ca sử dụng; không có một lựa chọn phù hợp cho mọi hệ thống.

## 1. Vì sao cần kiểm soát ghi cạnh tranh?

Giả sử một sản phẩm có availableQuantity = 10. Hai request đồng thời muốn trừ số lượng:

~~~text
Thời điểm   Transaction T1                  Transaction T2
---------   ------------------------------   ------------------------------
t1          Đọc availableQuantity = 10
t2                                           Đọc availableQuantity = 10
t3          Tính 10 - 2 = 8
t4                                           Tính 10 - 3 = 7
t5          Ghi availableQuantity = 8
t6                                           Ghi availableQuantity = 7
~~~

Nếu cả hai lần ghi đều thành công mà không có kiểm soát phù hợp, lần ghi sau có thể ghi đè kết quả trước. Hệ thống chỉ còn 7, trong khi tổng số lượng đã xuất theo hai request là 5 và số lượng còn lại đúng phải là 5. Một transaction đã làm mất cập nhật của transaction kia.

Đây là vấn đề đồng thời (concurrency), không đơn thuần là lỗi validate đầu vào. Mỗi request có thể hợp lệ khi kiểm tra riêng lẻ nhưng kết hợp lại tạo ra kết quả sai. Transaction giúp gom các thao tác thành một đơn vị nguyên tử, nhưng chỉ dùng @Transactional không tự động giải quyết mọi kiểu ghi cạnh tranh. Cần chọn mức cô lập, khóa hoặc câu lệnh cập nhật phù hợp với bất biến cần bảo vệ.

## 2. Optimistic locking — phát hiện xung đột khi ghi

Optimistic locking giả định xung đột không xảy ra thường xuyên. Nhiều transaction có thể đọc cùng một bản ghi mà không giữ khóa độc quyền trong suốt thời gian xử lý. Khi ghi, hệ thống kiểm tra dữ liệu có còn ở phiên bản mà transaction đã đọc hay không. Nếu một transaction khác đã cập nhật trước, thao tác ghi cũ bị từ chối.

Trong JPA, cách phổ biến là thêm trường version với annotation @Version:

~~~java
@Entity
@Table(name = "products")
public class ProductEntity {
    @Id
    private UUID id;

    @Column(nullable = false)
    private int availableQuantity;

    @Version
    private long version;

    protected ProductEntity() {}
}
~~~

Ứng dụng không tự tăng hoặc gán giá trị version. JPA provider quản lý trường này. Khi đọc, persistence context ghi nhận version hiện tại. Khi cập nhật, provider phát sinh câu lệnh tương đương:

~~~sql
UPDATE products
SET available_quantity = ?, version = version + 1
WHERE id = ? AND version = ?
~~~

Nếu câu lệnh không cập nhật được hàng nào vì version đã đổi, provider nhận biết xung đột và ném lỗi optimistic locking, thường được biểu diễn qua OptimisticLockException của JPA hoặc exception đã được Spring dịch như OptimisticLockingFailureException.

### 2.1. Minh họa hai transaction cạnh tranh

Giả sử bản ghi ban đầu có version 12:

~~~text
T1 đọc quantity=10, version=12
T2 đọc quantity=10, version=12

T1 cập nhật quantity=8 với điều kiện version=12
   -> cập nhật thành công, version thành 13

T2 cập nhật quantity=7 với điều kiện version=12
   -> không có hàng nào khớp version=12
   -> phát sinh optimistic locking conflict
~~~

Nhờ kiểm tra version, T2 không thể âm thầm ghi đè thay đổi của T1. Ứng dụng có thể yêu cầu người dùng tải lại dữ liệu, hợp nhất thay đổi hoặc thử lại toàn bộ ca sử dụng theo một chính sách an toàn.

### 2.2. Cập nhật entity trong Spring Data JPA

Một repository có thể khai báo truy vấn tìm sản phẩm:

~~~java
public interface ProductJpaRepository
        extends JpaRepository<ProductEntity, UUID> {
}
~~~

Tầng ứng dụng thực hiện thay đổi trong transaction:

~~~java
@Service
public class ReduceStockService {
    private final ProductJpaRepository products;

    public ReduceStockService(ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional
    public void reduce(UUID productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        ProductEntity product = products.findById(productId)
            .orElseThrow(() -> new ProductNotFoundException(productId));

        if (product.getAvailableQuantity() < quantity) {
            throw new InsufficientStockException(productId);
        }

        product.setAvailableQuantity(
            product.getAvailableQuantity() - quantity
        );
        // Entity đang được quản lý; JPA dirty checking sẽ ghi thay đổi.
    }
}
~~~

Đoạn mã giả định entity có getter/setter phù hợp. Khi transaction flush hoặc commit, JPA kiểm tra version. Nếu một transaction khác đã cập nhật cùng entity, transaction hiện tại có thể thất bại với optimistic locking exception. Không nhất thiết phải gọi save() cho entity đang được quản lý trong persistence context; dirty checking sẽ phát hiện thay đổi. Việc gọi save() trong một số trường hợp có thể vẫn hợp lệ theo repository abstraction, nhưng không phải điều kiện để JPA ghi một managed entity.

### 2.3. Xử lý conflict và retry

Optimistic locking phát hiện xung đột chứ không tự giải quyết xung đột. Khi gặp lỗi, transaction hiện tại thường không thể tiếp tục như thể chưa có gì xảy ra. Nếu muốn thử lại, cần bắt lỗi ở ranh giới bên ngoài transaction, bắt đầu transaction mới, đọc lại trạng thái mới nhất rồi tính lại toàn bộ nghiệp vụ.

Không nên chỉ gọi lại câu lệnh save() với entity cũ vì entity đó có thể vẫn mang version cũ và quyết định nghiệp vụ đã dựa trên dữ liệu lỗi thời. Với ví dụ tồn kho, lần thử lại phải đọc số lượng mới, kiểm tra đủ hàng hay không, sau đó mới trừ số lượng.

Retry chỉ phù hợp nếu thao tác có thể thực hiện lại an toàn. Dùng số lần thử giới hạn, khoảng chờ tăng dần và jitter nếu có nhiều client cùng tranh chấp. Nếu sau khi đọc lại, số lượng không còn đủ, kết quả đúng là từ chối đặt hàng chứ không tiếp tục retry.

## 3. Pessimistic locking — khóa trước khi cập nhật

Pessimistic locking giả định xung đột có khả năng xảy ra đủ thường xuyên để cần khóa dữ liệu trước khi đọc hoặc ghi. Transaction yêu cầu cơ sở dữ liệu khóa hàng liên quan; transaction khác muốn lấy khóa xung đột thường phải chờ, hoặc nhận timeout nếu không thể chờ đủ lâu.

Trong JPA, các lock mode thường dùng gồm:

- PESSIMISTIC_READ: yêu cầu khóa để ngăn các transaction khác sửa dữ liệu được khóa trong khi transaction hiện tại đang đọc.
- PESSIMISTIC_WRITE: yêu cầu khóa ghi để ngăn các transaction khác lấy khóa xung đột và cập nhật hàng đó cho đến khi transaction kết thúc.
- PESSIMISTIC_FORCE_INCREMENT: yêu cầu khóa ghi và tăng version của entity versioned; có thể dùng khi cần thể hiện một lần thay đổi về mặt phiên bản ngay cả khi không có trường nghiệp vụ nào thay đổi.

Provider có thể ánh xạ các lock mode sang cơ chế cụ thể của database. Khóa đọc có thể được hiện thực khác nhau tùy hệ quản trị; không nên giả định mọi database đều dùng cùng một câu SQL hoặc cùng hành vi khóa. Khóa thực tế cũng có thể ảnh hưởng đến hàng liên quan tùy truy vấn, quan hệ và phạm vi khóa.

### 3.1. Khai báo khóa ghi trong Spring Data JPA

Ví dụ repository lấy sản phẩm với PESSIMISTIC_WRITE:

~~~java
public interface ProductJpaRepository
        extends JpaRepository<ProductEntity, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from ProductEntity p where p.id = :id")
    Optional<ProductEntity> findByIdForUpdate(@Param("id") UUID id);
}
~~~

Tầng ứng dụng gọi phương thức trong một transaction:

~~~java
@Transactional
public void reduce(UUID productId, int quantity) {
    ProductEntity product = products.findByIdForUpdate(productId)
        .orElseThrow(() -> new ProductNotFoundException(productId));

    if (quantity <= 0 || product.getAvailableQuantity() < quantity) {
        throw new InsufficientStockException(productId);
    }

    product.setAvailableQuantity(
        product.getAvailableQuantity() - quantity
    );
}
~~~

Transaction giữ khóa cho đến khi commit hoặc rollback. Transaction khác cần khóa xung đột trên cùng hàng có thể phải đợi. Vì vậy, thao tác đọc, kiểm tra và cập nhật nằm trong cùng ranh giới transaction. Nếu đọc khóa xong rồi kết thúc transaction trước khi cập nhật, bảo vệ đồng thời sẽ mất tác dụng.

### 3.2. Timeout, deadlock và thời gian giữ khóa

Khóa bi quan có thể khiến transaction chờ. Nếu T1 khóa hàng A rồi chờ hàng B, trong khi T2 khóa hàng B rồi chờ hàng A, hai transaction có thể tạo deadlock. Database thường phát hiện và hủy một transaction để giải phóng vòng chờ.

Một số biện pháp giảm rủi ro:

- Giữ transaction ngắn; không gọi dịch vụ HTTP bên ngoài, gửi email hoặc chờ người dùng trong lúc đang giữ khóa.
- Nếu cần khóa nhiều hàng, lấy khóa theo thứ tự nhất quán ở mọi luồng xử lý.
- Chỉ khóa những hàng cần thiết, trong khoảng thời gian cần thiết.
- Cấu hình timeout phù hợp để request không chờ vô hạn.
- Theo dõi thời gian chờ khóa, deadlock và tỷ lệ rollback trong môi trường vận hành.

JPA hỗ trợ hint jakarta.persistence.lock.timeout tính theo mili giây trong các ngữ cảnh phù hợp. Provider hoặc database có thể có giới hạn về khả năng hỗ trợ hint này, vì vậy cần kiểm tra hành vi thực tế của hệ thống triển khai. Timeout không thay thế việc thiết kế transaction ngắn và thứ tự khóa nhất quán.

## 4. So sánh optimistic locking và pessimistic locking

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách hoạt động | Phát hiện dữ liệu đã đổi khi ghi | Khóa dữ liệu trước khi thao tác |
| Xung đột | Transaction có thể cùng đọc; một lần ghi có thể bị từ chối | Transaction lấy khóa xung đột thường phải chờ hoặc timeout |
| Chi phí chính | Kiểm tra version và xử lý retry/conflict | Thời gian giữ khóa, chờ khóa, deadlock |
| Phù hợp | Đọc nhiều, ghi ít, xung đột thấp hoặc chấp nhận conflict | Ghi cạnh tranh cao, cần tuần tự hóa thao tác trên một số hàng |
| Trải nghiệm người dùng | Có thể yêu cầu tải lại hoặc thử lại | Có thể tăng độ trễ do phải chờ khóa |
| Điều cần chú ý | Retry phải đọc lại và tính lại nghiệp vụ | Transaction cần ngắn và khóa theo thứ tự nhất quán |

Không nên kết luận optimistic luôn nhanh hơn hoặc pessimistic luôn an toàn hơn. Với workload ít xung đột, optimistic thường tránh chi phí chờ khóa. Với một tài nguyên rất nóng, optimistic có thể tạo nhiều lần thất bại và retry; pessimistic có thể giúp tuần tự hóa nhưng lại làm tăng thời gian chờ và nguy cơ deadlock. Cần đo trên workload thực tế.

## 5. Chọn cơ chế theo bất biến nghiệp vụ

Hãy bắt đầu từ điều hệ thống cần bảo vệ, không bắt đầu từ annotation:

- **Hồ sơ người dùng ít được cập nhật đồng thời:** optimistic locking với @Version thường đủ. Nếu hai người sửa cùng hồ sơ, người cập nhật sau nhận conflict và có thể tải lại.
- **Sản phẩm có nhiều request trừ tồn kho:** nếu lượng tranh chấp vừa phải, optimistic locking có thể phát hiện và retry; nếu một số SKU rất nóng, có thể cân nhắc pessimistic write hoặc cập nhật nguyên tử có điều kiện.
- **Chuyển số dư giữa hai tài khoản:** cần transaction bao phủ cả hai thay đổi, kiểm soát thứ tự khóa và bảo đảm không tạo số dư âm. Chỉ thêm version cho một hàng không đủ bảo vệ toàn bộ nghiệp vụ nhiều hàng.
- **Tài nguyên được đặt chỗ trong khoảng thời gian ngắn:** pessimistic locking có thể phù hợp nếu cần giữ quyền thao tác trong một transaction ngắn; với quy trình kéo dài qua nhiều phút, giữ database lock trong suốt quy trình thường không phù hợp.

Với bài toán tồn kho, một lựa chọn khác là câu lệnh cập nhật nguyên tử có điều kiện:

~~~sql
UPDATE products
SET available_quantity = available_quantity - :quantity
WHERE id = :productId
  AND available_quantity >= :quantity
~~~

Sau câu lệnh, kiểm tra số hàng được cập nhật. Nếu bằng 1, thao tác trừ tồn kho thành công; nếu bằng 0, sản phẩm không tồn tại hoặc không đủ hàng (cần truy vấn bổ sung nếu nghiệp vụ phải phân biệt hai trường hợp). Câu lệnh này để database kiểm tra và cập nhật trong một thao tác nguyên tử, tránh khoảng trống giữa đọc rồi ghi. Tuy nhiên, nó không tự bảo vệ các bất biến khác nằm ở nhiều bảng hoặc cần logic phức tạp.

## 6. Phạm vi bảo vệ và những giới hạn cần biết

Optimistic locking qua @Version bảo vệ entity/version được cập nhật theo cơ chế của JPA. Nó không tự động bảo vệ mọi bất biến liên quan đến nhiều hàng. Ví dụ, hai transaction có thể cùng kiểm tra tổng số đặt chỗ của một sự kiện bằng 99 với giới hạn 100, rồi mỗi transaction thêm một hàng đặt chỗ riêng. Nếu không có một hàng tổng hợp được khóa/version, constraint hoặc cập nhật nguyên tử, cả hai có thể cùng vượt giới hạn.

Pessimistic locking cũng chỉ bảo vệ tài nguyên và phạm vi khóa thực tế mà database/provider áp dụng. Khóa một hàng sản phẩm không tự động khóa mọi hàng đặt chỗ hoặc mọi sản phẩm liên quan. Cần xác định chính xác dữ liệu nào tạo nên bất biến và khóa đủ phạm vi để giữ bất biến đó.

Một số điểm cần lưu ý:

- **Bulk update:** JPQL bulk update hoặc native SQL thường bỏ qua cơ chế dirty checking của entity và có thể không tự áp dụng kiểm tra/tăng @Version như cập nhật entity thông thường. Nếu dùng bulk operation, cần quản lý version và persistence context một cách tường minh.
- **Detached entity:** cập nhật một entity đã tách khỏi persistence context vẫn cần xử lý version đúng. Không được tự gán version để “làm cho update thành công”.
- **Isolation level:** mức cô lập của transaction database và cơ chế khóa entity có liên quan nhưng không đồng nhất. Một isolation level cao hơn có thể ngăn một số anomaly nhưng không thay thế việc xác định bất biến nghiệp vụ.
- **Nhiều hệ thống lưu trữ:** JPA lock chỉ có hiệu lực trong phạm vi database/transaction mà provider quản lý; nó không tự khóa một cache, message broker hay dịch vụ từ xa.
- **Distributed workflow:** không giữ database row lock trong lúc chờ một quy trình kéo dài qua nhiều dịch vụ. Các quy trình như đặt vé, thanh toán hoặc giữ hàng lâu có thể cần reservation, expiry, idempotency hoặc saga thay vì một transaction khóa dài.

## 7. Kiểm thử ghi cạnh tranh

Một unit test chạy tuần tự không đủ chứng minh optimistic hoặc pessimistic locking hoạt động đúng. Cần kiểm thử tích hợp với database tương thích và hai transaction thực sự chạy cạnh tranh.

| Kiểm thử | Cách tổ chức | Kết quả cần xác nhận |
|---|---|---|
| Optimistic conflict | Hai transaction đọc cùng entity/version; transaction thứ nhất commit trước, transaction thứ hai cố ghi | Transaction thứ hai nhận optimistic locking conflict; dữ liệu của transaction đầu không bị ghi đè |
| Pessimistic wait | T1 lấy PESSIMISTIC_WRITE; T2 yêu cầu khóa cùng hàng | T2 chờ cho đến khi T1 kết thúc hoặc timeout theo cấu hình |
| Deadlock handling | Hai transaction lấy nhiều khóa theo thứ tự ngược nhau | Database phát hiện một transaction thất bại; ứng dụng ghi nhận và xử lý phù hợp |
| Inventory invariant | Nhiều request đồng thời trừ số lượng | Số lượng không âm và tổng số lượng trừ không vượt tồn kho |
| Retry | Cố ý tạo optimistic conflict rồi thực hiện retry ở transaction mới | Lần thử lại đọc dữ liệu mới và tính lại kết quả |

Để tạo cạnh tranh thật, có thể dùng hai thread và barrier/latch để đồng bộ thời điểm đọc hoặc lấy khóa. Tránh dùng một transaction test bao ngoài khiến tất cả thao tác trong cùng test vô tình tham gia một transaction. Cần xác nhận transaction độc lập và commit/rollback thực sự xảy ra.

Database trong bộ test nên tương thích với database triển khai về hành vi khóa, isolation và constraint. H2 hoặc database giả lập có thể hữu ích cho test nhanh, nhưng không bảo đảm tái hiện chính xác hành vi SELECT FOR UPDATE, timeout hay deadlock của hệ quản trị production.

## 8. Quy tắc thực hành khi xử lý ghi cạnh tranh

Trước khi chọn locking strategy, hãy trả lời:

1. Bất biến nào cần bảo vệ? Một hàng, nhiều hàng hay một giới hạn tổng hợp?
2. Có bao nhiêu request đồng thời ghi cùng tài nguyên và mức tranh chấp thực tế ra sao?
3. Nếu phát hiện conflict, có thể yêu cầu người dùng tải lại hay hệ thống cần retry tự động?
4. Toàn bộ thao tác có thể chạy trong một transaction ngắn không?
5. Database/provider đang dùng hỗ trợ lock mode, timeout và isolation như thế nào?
6. Có integration test chứng minh hai transaction cạnh tranh không thể tạo trạng thái sai không?

Optimistic locking phù hợp khi xung đột không thường xuyên và ứng dụng có cách xử lý conflict rõ ràng. Pessimistic locking phù hợp khi cần tuần tự hóa thao tác trên dữ liệu nóng và có thể giữ transaction ngắn. Với một số nghiệp vụ, cập nhật nguyên tử có điều kiện hoặc constraint ở database là lựa chọn đơn giản và mạnh hơn. Có thể kết hợp nhiều cơ chế, miễn là mỗi cơ chế bảo vệ một bất biến được xác định rõ.

Điều quan trọng là giữ trách nhiệm đúng tầng: tầng ứng dụng xác định ca sử dụng, transaction boundary và phản ứng khi conflict; tầng truy cập dữ liệu khai báo version/lock hoặc câu lệnh cập nhật phù hợp; database thực thi tính nguyên tử và cơ chế khóa. Khi ba phần này phối hợp đúng, các request đồng thời có thể được xử lý mà không làm mất cập nhật hoặc phá vỡ dữ liệu nghiệp vụ.
