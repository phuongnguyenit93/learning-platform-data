# UnexpectedRollbackException và xử lý rollback-only

Trong Spring Data JPA, `UnexpectedRollbackException` thường xuất hiện ở thời điểm kết thúc một transaction khi transaction đã bị đánh dấu `rollback-only`, nhưng luồng gọi bên ngoài vẫn đi đến bước commit. Spring không thể commit một transaction đã bị đánh dấu phải rollback, vì vậy nó thực hiện rollback và thông báo cho caller bằng exception này.

Điểm cần tìm thường nằm trước thời điểm exception xuất hiện: một lời gọi bên trong đã thất bại, transaction đã bị đánh dấu rollback-only, nhưng exception bị bắt lại nên phương thức bên ngoài vẫn chạy như thể mọi việc bình thường.

## 1. Hiểu rollback-only và UnexpectedRollbackException

### Transaction vật lý và các phạm vi giao dịch logic

Khi một phương thức được đánh dấu `@Transactional`, Spring thường dùng proxy để mở, tham gia, commit hoặc rollback transaction quanh lời gọi phương thức. Propagation mặc định là `Propagation.REQUIRED`:

- Nếu chưa có transaction, Spring tạo một transaction mới.
- Nếu đã có transaction, phương thức tham gia vào transaction đang tồn tại.
- Nhiều phương thức có thể có các phạm vi giao dịch logic riêng nhưng cùng sử dụng một transaction vật lý.

Khi một phương thức tham gia transaction bằng `REQUIRED` thất bại với `RuntimeException` hoặc `Error`, interceptor của Spring áp dụng rollback rule và đánh dấu transaction đang dùng là rollback-only. Việc đánh dấu này có hiệu lực với transaction vật lý được chia sẻ.

Nếu phương thức bên ngoài bắt exception rồi tiếp tục, việc bắt exception chỉ xử lý luồng điều khiển của Java. Nó không xóa cờ rollback-only. Khi phương thức ngoài cùng kết thúc và Spring thử commit, Spring phát hiện transaction đã bị đánh dấu rollback-only, thực hiện rollback và ném `UnexpectedRollbackException`.

### Ví dụ: bắt exception bên trong nhưng transaction vẫn rollback

Hai service dưới đây phải là hai Spring bean riêng biệt để lời gọi từ service cha đi qua proxy giao dịch của service con.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ChildService {

    @Transactional
    public void executeChild() {
        // Có thể đã thực hiện một số thao tác với cơ sở dữ liệu.
        throw new IllegalStateException("Thao tác bên trong thất bại");
    }
}
```

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ParentService {

    private final ChildService childService;

    public ParentService(ChildService childService) {
        this.childService = childService;
    }

    @Transactional
    public void execute() {
        try {
            childService.executeChild();
        } catch (IllegalStateException ex) {
            // Chỉ bắt exception; transaction dùng chung đã bị đánh dấu rollback-only.
            System.out.println("Đã ghi nhận lỗi: " + ex.getMessage());
        }

        // Các câu lệnh tiếp theo vẫn có thể chạy.
        // Tuy nhiên transaction không còn khả năng commit.
    }
}
```

Diễn biến:

1. Caller gọi `ParentService.execute()`; Spring mở transaction.
2. `ChildService.executeChild()` tham gia transaction đang tồn tại vì dùng `REQUIRED`.
3. Phương thức con ném `IllegalStateException`. Transaction interceptor của phương thức con xử lý rollback và đánh dấu transaction dùng chung là rollback-only.
4. Phương thức cha bắt exception nên tiếp tục chạy và có thể trả về bình thường.
5. Khi phương thức cha kết thúc, interceptor thử commit. Transaction đã rollback-only nên Spring rollback và ném `UnexpectedRollbackException`.

Trong trường hợp này, exception cuối cùng được nhìn thấy ở caller có thể là `UnexpectedRollbackException`, còn nguyên nhân ban đầu là exception đã bị bắt trong phương thức con. Hãy tìm exception đầu tiên trong log để hiểu lỗi gốc.

### Khi nào exception không tự động đánh dấu rollback-only?

Cần phân biệt exception đi qua transaction interceptor với exception được bắt hoàn toàn bên trong cùng một phương thức:

- Nếu một phương thức con có `@Transactional` được gọi qua proxy và exception thoát khỏi phương thức con, interceptor có thể đánh dấu transaction rollback-only theo rollback rule.
- Nếu code ném rồi bắt exception ngay trong cùng phương thức transactional, interceptor bên ngoài không nhìn thấy exception đó. Spring không tự động đánh dấu rollback chỉ vì exception từng được ném rồi bắt.
- Tuy nhiên, Hibernate/JPA hoặc transaction manager vẫn có thể đánh dấu transaction rollback-only sau một lỗi ở tầng persistence. Khi đó, dù code đã bắt exception, transaction vẫn không thể commit.
- Theo rollback rule mặc định phổ biến của Spring, `RuntimeException` và `Error` làm transaction rollback; checked exception không tự động rollback nếu không cấu hình thêm. Có thể khai báo `rollbackFor` hoặc `noRollbackFor` khi nghiệp vụ yêu cầu.

## 2. Nhận diện và tìm nguyên nhân

Một số dấu hiệu thường gặp:

- Exception xuất hiện khi phương thức transactional ngoài cùng kết thúc, dù phần thân phương thức dường như đã chạy xong.
- Log có một exception trước đó đã bị catch, chẳng hạn lỗi nghiệp vụ, `DataIntegrityViolationException`, lỗi optimistic locking hoặc lỗi từ thao tác persistence.
- Có nhiều phương thức `@Transactional` dùng propagation `REQUIRED`; một phương thức bên trong thất bại nhưng caller vẫn tiếp tục.
- Code gọi `setRollbackOnly()` hoặc một lỗi ở JPA provider đã đánh dấu transaction rollback-only.

Cách điều tra:

1. Tìm exception đầu tiên xảy ra trước `UnexpectedRollbackException`. Xác định chính xác câu lệnh persistence hoặc quy tắc nghiệp vụ gây lỗi.
2. Lần theo transaction boundary: phương thức nào mở transaction, phương thức nào tham gia transaction, exception có đi qua proxy hay bị bắt ở đâu.
3. Kiểm tra các khối `catch` có ghi log rồi tiếp tục hay không. Việc chỉ ghi log không làm transaction trở lại trạng thái có thể commit.
4. Kiểm tra rollback rule trên `@Transactional`, các lệnh `setRollbackOnly()` và propagation được cấu hình.
5. Nếu cần biết lỗi SQL xảy ra ở thao tác nào, có thể gọi `EntityManager.flush()` hoặc dùng `saveAndFlush()` ở vị trí phù hợp để buộc persistence context đồng bộ sớm. Flush giúp xác định thời điểm lỗi; nó không xóa cờ rollback-only và không sửa được transaction đã hỏng.

Có thể bật log để quan sát transaction boundary và câu lệnh SQL:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.orm.jpa: DEBUG
    org.hibernate.SQL: DEBUG
```

Không nên chỉ dựa vào exception cuối cùng. Hãy đối chiếu log transaction với exception gốc và vị trí catch.

## 3. Chọn cách xử lý theo mục tiêu nghiệp vụ

### Cách 1: Để lỗi truyền ra ngoài khi toàn bộ thao tác phải nguyên tử

Nếu thao tác con thất bại thì toàn bộ nghiệp vụ phải thất bại, hãy để exception truyền ra ngoài. Spring sẽ rollback transaction và caller nhận được exception gốc.

```java
@Service
public class ParentService {

    private final ChildService childService;

    public ParentService(ChildService childService) {
        this.childService = childService;
    }

    @Transactional
    public void execute() {
        childService.executeChild();
        // Chỉ chạy khi thao tác con thành công.
        // Nếu thao tác con thất bại, exception truyền ra và transaction rollback.
    }
}
```

Đây thường là lựa chọn phù hợp cho nghiệp vụ cần tính nguyên tử, ví dụ tạo đơn hàng và trừ tồn kho trong cùng một transaction. Không nên bắt exception rồi tiếp tục ghi dữ liệu nếu trạng thái nghiệp vụ không còn nhất quán.

Nếu cần đổi exception kỹ thuật thành exception nghiệp vụ, hãy bọc exception gốc rồi ném tiếp:

```java
try {
    childService.executeChild();
} catch (IllegalStateException ex) {
    throw new OrderProcessingException("Không thể xử lý đơn hàng", ex);
}
```

Exception nghiệp vụ nên là unchecked exception nếu muốn tuân theo rollback rule mặc định. Nếu dùng checked exception, cấu hình `rollbackFor` phù hợp.

### Cách 2: Muốn trả kết quả thất bại nhưng vẫn rollback transaction

Có trường hợp phương thức cần trả về một kết quả nghiệp vụ thay vì ném exception. Nếu lỗi được xử lý trong chính phạm vi transaction hiện tại và transaction chưa bị một phạm vi con đánh dấu rollback-only, có thể chủ động đánh dấu rollback:

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result execute() {
    try {
        // Thực hiện các thao tác cần transaction.
        performWork();
        return Result.success();
    } catch (RecoverableBusinessException ex) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        return Result.failure(ex.getMessage());
    }
}
```

`setRollbackOnly()` yêu cầu Spring rollback khi phạm vi giao dịch hiện tại kết thúc. Cách này không khôi phục transaction đã bị đánh dấu rollback-only từ một phạm vi con. Nếu một phương thức con tham gia bằng `REQUIRED` đã đánh dấu transaction dùng chung rollback-only, việc bắt exception ở ngoài và trả kết quả bình thường vẫn có thể dẫn đến `UnexpectedRollbackException` tại commit của transaction ngoài cùng.

Vì vậy, chỉ dùng cách này khi chủ đích rollback đã rõ ràng và caller hiểu rằng transaction có thể kết thúc bằng rollback. Với thiết kế mới, ưu tiên mô hình trả kết quả nghiệp vụ tách biệt với transaction boundary hoặc để exception truyền ra ngoài.

### Cách 3: Tách thao tác cần transaction độc lập bằng REQUIRES_NEW

Nếu thao tác bên trong cần commit hoặc rollback độc lập với transaction bên ngoài, dùng `Propagation.REQUIRES_NEW`. Spring tạm treo transaction hiện tại và mở transaction vật lý mới cho lời gọi đó.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String message) {
        // Lưu bản ghi audit trong transaction riêng.
    }
}
```

Phương thức ngoài có thể bắt lỗi từ thao tác độc lập rồi tiếp tục transaction của nó:

```java
@Transactional
public void execute() {
    try {
        auditService.recordFailure("Một thao tác phụ thất bại");
    } catch (RuntimeException ex) {
        // Transaction riêng của audit đã rollback.
        // Transaction bên ngoài vẫn có thể tiếp tục nếu chưa có lỗi khác.
    }

    // Các thao tác của transaction bên ngoài.
}
```

Cần dùng `REQUIRES_NEW` khi tính độc lập là yêu cầu nghiệp vụ thật sự, chẳng hạn lưu một bản ghi audit cần tồn tại dù transaction chính rollback. Lưu ý:

- Phương thức `REQUIRES_NEW` phải được gọi qua Spring proxy; tự gọi phương thức trong cùng class không kích hoạt proxy transaction theo cơ chế proxy mặc định.
- Transaction mới dùng tài nguyên kết nối riêng trong khi transaction ngoài bị treo, vì vậy cần cân nhắc connection pool và thời gian giữ lock.
- Nếu exception từ transaction mới tiếp tục truyền ra ngoài, transaction ngoài cũng có thể rollback theo rollback rule của nó. Muốn transaction ngoài tiếp tục thì phải xử lý exception có chủ đích.
- Không dùng `REQUIRES_NEW` chỉ để che giấu lỗi dữ liệu hoặc tách tùy tiện các thao tác vốn phải nguyên tử.

### Cách 4: Dùng noRollbackFor chỉ với lỗi thực sự có thể tiếp tục

Có thể cấu hình một loại exception không làm Spring rollback:

```java
@Transactional(noRollbackFor = InventoryWarningException.class)
public void reserveInventory() {
    // Một cảnh báo nghiệp vụ được xác định là không làm hỏng transaction.
}
```

Cách này chỉ phù hợp khi exception biểu thị một tình huống có thể tiếp tục và transaction manager/JPA provider chưa đánh dấu transaction rollback-only. `noRollbackFor` chỉ thay đổi rollback rule của Spring; nó không thể xóa cờ rollback-only mà Hibernate, JPA hoặc transaction manager đã đặt. Không dùng cách này để tiếp tục một transaction sau lỗi SQL, lỗi constraint hoặc lỗi persistence khiến transaction không còn hợp lệ.

### Cẩn trọng với NESTED

`Propagation.NESTED` thường dựa trên savepoint của transaction vật lý và chỉ hoạt động khi transaction manager hỗ trợ. Khả năng hỗ trợ phụ thuộc loại transaction manager và cấu hình. Với Spring Data JPA, không nên mặc định rằng `NESTED` tạo được một transaction JPA lồng nhau độc lập; JPA không cung cấp cơ chế nested transaction portable. Nếu cần transaction độc lập rõ ràng, hãy đánh giá `REQUIRES_NEW`.

## 4. So sánh propagation thường gặp

| Propagation | Hành vi | Ảnh hưởng khi phạm vi con thất bại |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có | Nếu phạm vi tham gia đánh dấu rollback-only, transaction vật lý dùng chung không thể commit; caller có thể nhận `UnexpectedRollbackException` |
| `REQUIRES_NEW` | Treo transaction hiện tại và tạo transaction vật lý mới | Transaction con rollback độc lập; transaction ngoài có thể tiếp tục nếu exception được xử lý và bản thân nó chưa rollback-only |
| `NESTED` | Tạo savepoint trong transaction hiện tại nếu transaction manager hỗ trợ | Có thể rollback về savepoint; không phải giải pháp nested JPA portable |

Mặc định `@Transactional` dùng `REQUIRED`. Hãy chỉ thay propagation khi ranh giới nhất quán dữ liệu của nghiệp vụ yêu cầu.

## 5. Kiểm thử để phát hiện lỗi tại đúng ranh giới commit

Một integration test nên gọi service qua Spring bean và để transaction của service tự kết thúc. Không đặt `@Transactional` lên chính test này, vì transaction của test có thể làm thay đổi thời điểm commit và khiến exception chỉ xuất hiện khi test framework kết thúc.

Ví dụ với JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootTest
class ParentServiceIntegrationTest {

    @Autowired
    private ParentService parentService;

    @Test
    void shouldExposeUnexpectedRollbackWhenInnerRequiredTransactionFails() {
        assertThrows(
            UnexpectedRollbackException.class,
            () -> parentService.execute()
        );
    }
}
```

Test này minh họa trường hợp service cha bắt exception của service con nhưng transaction dùng chung đã rollback-only. Trong bài kiểm thử nghiệp vụ thực tế, bổ sung assertion trên repository để xác nhận các thay đổi thuộc transaction đã rollback và không để lại dữ liệu một phần.

Khi kiểm thử cách khắc phục:

- Với cách truyền exception ra ngoài, xác nhận caller nhận exception phù hợp và dữ liệu được rollback.
- Với `REQUIRES_NEW`, xác nhận dữ liệu của transaction độc lập được commit/rollback theo kết quả riêng, còn transaction ngoài có kết quả đúng như yêu cầu.
- Với `setRollbackOnly()`, xác nhận phương thức trả kết quả dự kiến và dữ liệu của transaction đã rollback.
- Không chỉ kiểm tra việc phương thức Java chạy hết; phải kiểm tra kết quả sau khi transaction thực sự kết thúc.

## 6. Lỗi thường gặp và cách tránh

- **Bắt exception rồi bỏ qua:** caller tưởng nghiệp vụ thành công nhưng transaction đã rollback-only. Hãy quyết định rõ là truyền lỗi, trả kết quả thất bại kèm rollback có chủ đích, hay tách transaction độc lập.
- **Cho rằng catch sẽ xóa rollback-only:** catch chỉ bắt exception, không reset trạng thái transaction. Không có cách an toàn để biến một transaction đã bị persistence provider đánh dấu rollback-only trở lại trạng thái commit được.
- **Tiếp tục dùng persistence context sau lỗi JPA:** sau khi transaction rollback, các entity đang quản lý có thể không còn phản ánh trạng thái cơ sở dữ liệu. Hãy kết thúc transaction và tải lại dữ liệu trong transaction mới khi cần.
- **Dùng `noRollbackFor` để bỏ qua lỗi cơ sở dữ liệu:** rollback rule của Spring không thể đảo ngược trạng thái rollback-only do provider hoặc transaction manager đặt.
- **Gọi phương thức transactional bằng self-invocation:** lời gọi nội bộ cùng object thường bỏ qua proxy trong chế độ proxy mặc định, nên annotation của phương thức được gọi có thể không được áp dụng. Tách service hoặc thiết kế lại ranh giới bean.
- **Dùng `REQUIRES_NEW` ở mọi nơi:** tách transaction có thể làm mất tính nguyên tử của nghiệp vụ và tăng nhu cầu kết nối. Chỉ dùng khi dữ liệu cần vòng đời commit/rollback độc lập.
- **Chỉ nhìn exception cuối cùng:** `UnexpectedRollbackException` thường là hệ quả. Hãy tìm exception đầu tiên hoặc vị trí đánh dấu rollback-only trong log.

## 7. Quy trình xử lý nhanh

1. Tìm exception gốc xảy ra trước `UnexpectedRollbackException`.
2. Xác định transaction ngoài cùng và các phương thức con tham gia bằng `REQUIRED`.
3. Kiểm tra exception có đi qua proxy, bị catch ở đâu, và có rollback rule hoặc `setRollbackOnly()` hay không.
4. Xác định nghiệp vụ cần rollback toàn bộ, rollback một phần độc lập, hay trả kết quả thất bại có chủ đích.
5. Chọn cách phù hợp: truyền exception ra ngoài, đánh dấu rollback-only trong đúng phạm vi, hoặc tách transaction bằng `REQUIRES_NEW`.
6. Viết integration test kiểm tra cả exception tại commit và trạng thái dữ liệu sau transaction.

Điều quan trọng nhất là xem rollback-only như trạng thái kết thúc của transaction: một khi transaction vật lý đã bị đánh dấu rollback-only, việc tiếp tục chạy code Java không làm transaction có thể commit trở lại. Hãy sửa ranh giới giao dịch và cách xử lý lỗi theo đúng yêu cầu nhất quán dữ liệu của nghiệp vụ.
