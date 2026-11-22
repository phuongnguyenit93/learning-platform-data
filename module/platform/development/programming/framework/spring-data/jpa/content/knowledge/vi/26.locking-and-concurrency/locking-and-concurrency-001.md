# Cập nhật mất dữ liệu và nhu cầu kiểm soát đồng thời

## Mục tiêu

Khi nhiều request cùng đọc và sửa một bản ghi, mỗi request có thể làm việc với một phiên bản dữ liệu đã cũ. Nếu ứng dụng ghi lại toàn bộ giá trị mà không phát hiện xung đột, lần ghi sau có thể ghi đè kết quả của lần ghi trước. Hiện tượng đó gọi là **cập nhật mất dữ liệu (lost update)**.

Sau bài này, bạn có thể:

- Mô tả cách lost update xảy ra trong một ứng dụng dùng Spring Data JPA.
- Giải thích vì sao chỉ đặt phương thức trong một transaction chưa đủ để ngăn mọi xung đột.
- Dùng **optimistic locking** với trường **@Version**.
- Dùng **pessimistic locking** với **@Lock** khi cần khóa bản ghi trong lúc xử lý.
- Chọn câu lệnh cập nhật nguyên tử cho các phép thay đổi số lượng hoặc bộ đếm.
- Xử lý xung đột, retry và kiểm thử các tình huống đồng thời.

## 1. Lost update xảy ra như thế nào?

Giả sử kho có 10 sản phẩm. Hai request cùng lúc muốn giảm số lượng: giao dịch T1 giảm 2, giao dịch T2 giảm 3. Cả hai cùng đọc giá trị ban đầu là 10:

| Thời điểm | Giao dịch T1 | Giao dịch T2 | Giá trị trong DB |
|---|---|---|---:|
| 1 | Đọc quantity = 10 | | 10 |
| 2 | | Đọc quantity = 10 | 10 |
| 3 | Tính 10 - 2 = 8 | | 10 |
| 4 | Ghi quantity = 8 | | 8 |
| 5 | | Tính 10 - 3 = 7 | 8 |
| 6 | | Ghi quantity = 7 | 7 |

Kết quả cuối cùng là 7. Tuy nhiên, nếu cả hai yêu cầu đều được áp dụng thì số lượng đúng phải là 5. T2 đã ghi một kết quả tính từ dữ liệu cũ và ghi đè thay đổi của T1.

Điểm nguy hiểm là mỗi giao dịch riêng lẻ vẫn có thể chạy thành công. Ứng dụng không nhất thiết nhận được lỗi SQL; dữ liệu chỉ âm thầm mất một cập nhật.

Lost update thường xuất hiện trong quy trình **đọc – tính toán – ghi (read–modify–write)**:

1. Đọc một entity từ cơ sở dữ liệu.
2. Tính giá trị mới trong bộ nhớ.
3. Ghi giá trị mới trở lại cơ sở dữ liệu.

Nếu hai giao dịch thực hiện quy trình này đồng thời trên cùng một bản ghi, chúng có thể cùng tính từ một giá trị cũ.

## 2. Vì sao @Transactional chưa tự giải quyết vấn đề?

Spring quản lý ranh giới transaction bằng **@Transactional**. JPA quản lý entity được tải trong persistence context; khi thuộc tính của entity thay đổi, cơ chế dirty checking ghi nhận thay đổi và gửi câu lệnh UPDATE khi flush.

Ví dụ:

~~~java
@Transactional
public void decrease(Long productId, int amount) {
    Product product = productRepository.findById(productId)
        .orElseThrow();
    product.setQuantity(product.getQuantity() - amount);
}
~~~

Phương thức trên có transaction, nhưng nếu entity không có cơ chế kiểm tra phiên bản thì câu lệnh UPDATE thường chỉ xác định bản ghi bằng khóa chính, tương tự:

~~~sql
UPDATE product
SET quantity = ?
WHERE id = ?;
~~~

Cơ sở dữ liệu biết bản ghi nào cần cập nhật, nhưng câu lệnh không thể hiện rằng giá trị mới được tính từ phiên bản nào. Một transaction khác có thể đã sửa bản ghi kể từ lúc entity được đọc.

**Transaction bảo đảm một nhóm thao tác tuân theo ranh giới commit hoặc rollback; khả năng ngăn lost update còn phụ thuộc vào cơ chế đồng thời và mức cô lập (isolation level).** Với READ COMMITTED, hai giao dịch vẫn có thể đọc cùng một giá trị trước khi một giao dịch ghi. Không nên xem @Transactional là khóa tự động cho mọi entity.

Một số hệ quản trị cơ sở dữ liệu và mức cô lập cao hơn có thể phát hiện hoặc ngăn một số lịch thực thi xung đột. Tuy nhiên, hành vi cụ thể phụ thuộc hệ quản trị và cấu hình. Ứng dụng nên chọn cơ chế kiểm soát rõ ràng phù hợp với nghiệp vụ.

## 3. Optimistic locking với @Version

Optimistic locking giả định xung đột không xảy ra thường xuyên. Thay vì khóa bản ghi ngay từ đầu, JPA kiểm tra phiên bản tại thời điểm cập nhật. Nếu bản ghi đã bị giao dịch khác sửa, giao dịch hiện tại bị từ chối và ứng dụng nhận được lỗi xung đột.

### 3.1. Khai báo trường phiên bản

Thêm một thuộc tính có chú thích **@Version** vào entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    protected Product() {
    }

    public void decrease(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (quantity < amount) {
            throw new IllegalStateException("Insufficient quantity");
        }
        quantity -= amount;
    }
}
~~~

JPA provider quản lý giá trị của trường version. Ứng dụng không nên tự gán hoặc tăng trường này trong luồng cập nhật entity thông thường. Kiểu thường dùng là **long**, **Long**, **int**, **Integer**, **short** hoặc **Short**; kiểu timestamp cũng được hỗ trợ theo đặc tả JPA và provider.

Cột version cần tồn tại trong bảng tương ứng. Khi tạo schema bằng migration, hãy bảo đảm cột này được thêm với kiểu phù hợp và giá trị ban đầu hợp lệ. Với entity đã có dữ liệu, migration phải thiết lập giá trị khởi tạo cho các hàng hiện tại.

### 3.2. JPA kiểm tra phiên bản khi ghi

Giả sử hai giao dịch cùng tải entity có version = 4.

- T1 cập nhật thành công. Provider ghi giá trị mới và tăng version lên 5.
- T2 vẫn giữ entity với version = 4. Khi T2 flush, điều kiện version = 4 không còn khớp.
- UPDATE của T2 tác động đến 0 hàng. Provider nhận ra xung đột và phát sinh lỗi optimistic locking.

Câu lệnh SQL minh họa có dạng:

~~~sql
UPDATE product
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Cú pháp SQL thực tế và cách tăng version do JPA provider quyết định. Điều quan trọng là điều kiện WHERE có cả khóa chính và version cũ. Chỉ một giao dịch có thể cập nhật thành công từ cùng một version.

### 3.3. Dùng với Spring Data JPA

Repository có thể giữ nguyên khai báo cơ bản:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Trong service, tải entity rồi thay đổi trạng thái bên trong transaction:

~~~java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final ProductRepository productRepository;

    public InventoryService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public void decrease(Long productId, int amount) {
        Product product = productRepository.findById(productId)
            .orElseThrow(() ->
                new EntityNotFoundException("Product not found"));

        product.decrease(amount);
    }
}
~~~

Entity được tải trong transaction là entity đang được quản lý. Khi thay đổi quantity, dirty checking ghi nhận thay đổi; không cần gọi save chỉ để JPA nhận ra thay đổi đó. Khi flush hoặc commit, provider thực hiện UPDATE kèm điều kiện version.

Lỗi có thể xuất hiện ở thời điểm flush hoặc commit, vì vậy việc phương thức service chạy đến dòng cuối không có nghĩa là transaction chắc chắn đã commit thành công. Gọi save hoặc saveAndFlush cũng không loại bỏ khả năng lỗi xuất hiện ở commit.

### 3.4. Xử lý xung đột

Ở tầng JPA, lỗi thường liên quan đến **OptimisticLockException**. Khi đi qua lớp tích hợp Spring, lỗi có thể được chuyển thành các ngoại lệ thuộc **OptimisticLockingFailureException**, ví dụ **ObjectOptimisticLockingFailureException**.

Ứng dụng cần chọn hành vi phù hợp với nghiệp vụ:

- Thông báo cho người dùng rằng dữ liệu đã thay đổi và yêu cầu tải lại trước khi sửa tiếp.
- Trả HTTP 409 Conflict ở API khi request dựa trên dữ liệu cũ và người gọi cần giải quyết xung đột.
- Retry khi thao tác có thể tính lại an toàn trên dữ liệu mới và số lần xung đột thấp.

Nếu retry, hãy bắt đầu một transaction mới, tải lại entity rồi tính lại thao tác từ trạng thái mới. Không nên bắt lỗi optimistic locking rồi tiếp tục sử dụng entity cũ trong transaction đã rollback hoặc đã bị đánh dấu rollback-only. Cũng không retry mù quáng các thao tác có side effect bên ngoài như gửi email, trừ khi side effect đã được thiết kế idempotent hoặc được điều phối sau commit.

Optimistic locking phù hợp khi số lần đọc nhiều, xung đột ghi tương đối ít và ứng dụng chấp nhận xử lý lỗi xung đột ở phía gọi.

## 4. Pessimistic locking với @Lock

Pessimistic locking yêu cầu cơ sở dữ liệu khóa bản ghi trong lúc transaction xử lý. Giao dịch khác muốn lấy khóa xung đột trên cùng bản ghi thường phải chờ, hoặc có thể thất bại nếu hết thời gian chờ hay phát sinh deadlock.

Spring Data JPA hỗ trợ khai báo chế độ khóa bằng **@Lock** trên phương thức truy vấn repository:

~~~java
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findForUpdate(@Param("id") Long id);
}
~~~

Gọi phương thức này trong transaction:

~~~java
@Transactional
public void decreaseWithLock(Long productId, int amount) {
    Product product = productRepository.findForUpdate(productId)
        .orElseThrow(() ->
            new EntityNotFoundException("Product not found"));

    product.decrease(amount);
}
~~~

**PESSIMISTIC_WRITE** yêu cầu khóa phù hợp cho thao tác ghi. Khóa được giữ đến khi transaction commit hoặc rollback. Tùy hệ quản trị cơ sở dữ liệu, giao dịch khác có thể phải chờ, nhận lỗi timeout hoặc gặp deadlock.

Các lưu ý khi dùng:

- Phương thức lấy khóa phải chạy trong transaction để khóa được giữ trong toàn bộ khoảng xử lý cần bảo vệ.
- Giữ transaction ngắn; tránh gọi dịch vụ mạng, chờ người dùng hoặc thực hiện công việc lâu trong lúc đang giữ khóa.
- Nếu một luồng khóa nhiều bản ghi, nên thống nhất thứ tự lấy khóa để giảm nguy cơ deadlock.
- Cân nhắc cấu hình timeout và xử lý lỗi khóa theo khả năng của hệ quản trị cơ sở dữ liệu.
- Khóa chỉ bảo vệ tài nguyên và phạm vi mà câu truy vấn thực sự khóa; không tự giải quyết mọi bất biến trải trên nhiều bảng.

Pessimistic locking hữu ích khi xung đột thường xuyên, thao tác cần được tuần tự hóa và chi phí chờ khóa có thể chấp nhận được. Đổi lại, nó làm giảm khả năng xử lý song song và có thể gây nghẽn khi transaction kéo dài.

## 5. Cập nhật nguyên tử cho bộ đếm và số lượng

Một số nghiệp vụ không cần tải toàn bộ entity, tính toán trong Java rồi ghi lại. Với phép cộng, trừ hoặc tăng giảm một giá trị, có thể để cơ sở dữ liệu thực hiện phép tính trong một câu lệnh UPDATE.

Ví dụ repository giảm tồn kho có điều kiện:

~~~java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Product p
           set p.quantity = p.quantity - :amount
         where p.id = :id
           and p.quantity >= :amount
        """)
    int decreaseIfEnough(
        @Param("id") Long id,
        @Param("amount") int amount
    );
}
~~~

Gọi trong transaction và kiểm tra số hàng được cập nhật:

~~~java
@Transactional
public void decreaseAtomically(Long productId, int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    int updated = productRepository.decreaseIfEnough(productId, amount);

    if (updated == 0) {
        throw new IllegalStateException(
            "Product not found or insufficient quantity");
    }
}
~~~

Câu lệnh UPDATE thực hiện phép trừ ngay trên giá trị tại cơ sở dữ liệu. Điều kiện quantity >= amount được kiểm tra cùng câu lệnh ghi, giúp ngăn tồn kho âm trong tình huống nhiều giao dịch cùng giảm số lượng. Giá trị trả về là số hàng được cập nhật: 1 nghĩa là cập nhật thành công; 0 nghĩa là không tìm thấy hàng phù hợp hoặc không đủ số lượng.

Đây là bulk update của JPQL. Nó tác động trực tiếp lên cơ sở dữ liệu và **bỏ qua dirty checking, callback vòng đời entity và đồng bộ tự động với các entity đang được quản lý**. Sau bulk update, entity đã tải trước đó có thể chứa dữ liệu cũ. Ví dụ trên dùng clearAutomatically để xóa persistence context sau thao tác; một lựa chọn khác là chủ động refresh hoặc tải lại entity.

Bulk update cũng không tự thực hiện optimistic locking như cập nhật entity thông thường. Nếu nghiệp vụ cần kiểm tra version, phải thiết kế điều kiện version và cách tăng version một cách tường minh, phù hợp với provider và câu lệnh được sử dụng. Không nên giả định rằng chỉ vì entity có @Version thì mọi JPQL bulk update đều được bảo vệ.

Cập nhật nguyên tử phù hợp với bộ đếm, số dư hoặc tồn kho khi nghiệp vụ có thể biểu diễn bằng một câu lệnh có điều kiện. Nếu nghiệp vụ cần kiểm tra và thay đổi nhiều thuộc tính hoặc nhiều bản ghi theo một quy tắc phức tạp, hãy cân nhắc optimistic locking, pessimistic locking hoặc ràng buộc ở cơ sở dữ liệu.

## 6. Chọn cơ chế nào?

| Cơ chế | Phù hợp khi | Chi phí và lưu ý |
|---|---|---|
| Optimistic locking với @Version | Xung đột hiếm; muốn phát hiện bản ghi đã bị sửa | Giao dịch xung đột thất bại; cần thông báo hoặc retry có kiểm soát |
| Pessimistic locking với @Lock | Xung đột thường xuyên; cần tuần tự hóa thao tác trên bản ghi | Có thể phải chờ khóa, timeout hoặc deadlock; cần transaction ngắn |
| Cập nhật nguyên tử | Phép tính đơn giản trên một giá trị, như tăng giảm bộ đếm hoặc tồn kho | Bulk update bỏ qua persistence context và kiểm tra version mặc định |
| Ràng buộc cơ sở dữ liệu | Bất biến cần được bảo vệ ở cấp dữ liệu, như giá trị duy nhất hoặc giới hạn hợp lệ | Cần thiết kế constraint và xử lý lỗi vi phạm |

Không có một lựa chọn phù hợp cho mọi trường hợp. Hãy bắt đầu từ bất biến nghiệp vụ:

- Nếu chỉ cần phát hiện người khác đã sửa entity, dùng @Version.
- Nếu cần giữ khóa trong khi thực hiện một đoạn xử lý ngắn trên bản ghi, cân nhắc PESSIMISTIC_WRITE.
- Nếu thao tác là phép biến đổi số học đơn giản, ưu tiên một UPDATE có điều kiện.
- Nếu quy tắc liên quan nhiều hàng hoặc nhiều giao dịch, đánh giá thêm constraint, mức cô lập và phạm vi khóa. @Version trên một entity không tự bảo vệ bất biến trải qua nhiều entity.

## 7. Lỗi thường gặp

1. **Cho rằng @Transactional đồng nghĩa với khóa.** Transaction xác định phạm vi commit/rollback; hãy chọn cơ chế concurrency phù hợp.
2. **Quên @Version trên entity cần optimistic locking.** Nếu không có trường version, JPA không thể thực hiện kiểm tra phiên bản theo cách này.
3. **Tự sửa giá trị version.** Hãy để JPA provider quản lý trường được đánh dấu @Version.
4. **Bắt lỗi rồi tiếp tục với entity cũ.** Sau xung đột, tải lại dữ liệu trong transaction mới và tính lại nghiệp vụ.
5. **Dùng bulk update rồi đọc entity cũ trong persistence context.** Hãy clear, refresh hoặc tải lại để tránh dữ liệu trong bộ nhớ không khớp cơ sở dữ liệu.
6. **Giữ pessimistic lock quá lâu.** Transaction dài làm tăng thời gian chờ và nguy cơ deadlock.
7. **Chỉ khóa một hàng trong khi quy tắc liên quan nhiều hàng.** Hãy xác định đầy đủ phạm vi bất biến và bảo vệ nó ở đúng cấp.
8. **Retry cả side effect bên ngoài.** Gửi thông báo hoặc gọi hệ thống khác có thể bị lặp nếu transaction được thử lại; cần thiết kế idempotency hoặc xử lý sau commit.

## 8. Kiểm thử hành vi đồng thời

Một bài test chỉ gọi service tuần tự hai lần thường không tái hiện được lost update. Để kiểm thử đúng, cần hai transaction độc lập cùng tải một version trước khi một transaction ghi.

Một kịch bản kiểm thử optimistic locking:

1. Tạo một Product với quantity = 10 và version ban đầu.
2. Khởi chạy hai luồng, mỗi luồng mở transaction riêng và tải cùng Product.
3. Dùng CountDownLatch hoặc cơ chế đồng bộ tương đương để bảo đảm cả hai luồng đã đọc xong trước khi cho phép cập nhật.
4. Cho cả hai luồng thay đổi quantity rồi flush hoặc commit.
5. Xác nhận một giao dịch commit thành công và giao dịch còn lại nhận lỗi optimistic locking.
6. Đọc lại dữ liệu bằng transaction mới và xác nhận giá trị là kết quả của giao dịch thành công, không phải một lần ghi đè âm thầm.

Khi kiểm thử pessimistic locking, xác nhận giao dịch thứ hai phải chờ hoặc nhận lỗi theo cấu hình timeout của cơ sở dữ liệu. Khi kiểm thử cập nhật nguyên tử, chạy nhiều request giảm số lượng đồng thời và xác nhận quantity không âm, tổng số lần cập nhật thành công đúng với điều kiện nghiệp vụ.

Nên chạy integration test với cùng loại hệ quản trị cơ sở dữ liệu mà ứng dụng sử dụng trong môi trường thực tế. Cơ sở dữ liệu giả lập trong test có thể có hành vi khóa và isolation khác với hệ quản trị triển khai.

## 9. Checklist khi đưa vào ứng dụng

- Xác định rõ bất biến cần bảo vệ: không ghi đè dữ liệu mới, không âm tồn kho, không vượt hạn mức hay quy tắc nào khác.
- Xác định entity và phạm vi dữ liệu liên quan đến bất biến đó.
- Chọn @Version, @Lock, câu lệnh UPDATE nguyên tử hoặc constraint phù hợp.
- Đặt ranh giới @Transactional đúng với thao tác cần bảo vệ.
- Xử lý lỗi optimistic locking, lock timeout, deadlock và constraint violation theo nghiệp vụ.
- Nếu retry, tải lại dữ liệu trong transaction mới và bảo đảm side effect không bị lặp.
- Kiểm thử với nhiều transaction độc lập và xác nhận kết quả cuối cùng ở cơ sở dữ liệu.

Kiểm soát đồng thời là một phần của thiết kế nghiệp vụ. Spring Data JPA cung cấp các công cụ để phát hiện hoặc điều phối xung đột; ứng dụng cần chọn đúng công cụ theo dữ liệu, mức độ tranh chấp và hậu quả khi một cập nhật bị từ chối.