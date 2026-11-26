# Cô lập fixture, làm sạch dữ liệu và kiểm chứng trạng thái sau commit

Một kiểm thử repository có thể vượt qua khi chạy riêng nhưng thất bại trong cả bộ test vì dữ liệu từ ca trước còn tồn tại. Nó cũng có thể báo thành công dù chưa từng commit: entity vẫn nằm trong persistence context, hoặc mọi assertion đều chạy bên trong transaction mà framework sẽ rollback sau khi phương thức test kết thúc.

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, bài học này trình bày cách quản lý fixture, chọn phạm vi làm sạch và quan sát dữ liệu sau commit. Các abstraction Repository, CRUD, truy vấn, phân trang và auditing đều chịu ảnh hưởng của trạng thái dữ liệu dùng chung. Cơ chế cô lập phải phù hợp với transaction manager, store và tài nguyên mà từng bài kiểm thử thực sự sử dụng.

## 1. Xác định thứ cần cô lập

**Fixture** là trạng thái đầu vào được chuẩn bị để một ca kiểm thử có thể thực hiện và quan sát hành vi mong muốn. Nó có thể bao gồm dữ liệu nền, entity nghiệp vụ, tài khoản, thời gian giả lập, cache hoặc thông điệp chờ xử lý.

Không phải mọi trạng thái đều được rollback cùng một transaction cơ sở dữ liệu.

| Loại trạng thái | Ví dụ | Cách quản lý thường cần xem xét |
| --- | --- | --- |
| Dữ liệu trong transaction test | Customer vừa lưu bằng repository cùng tài nguyên | Rollback nếu toàn bộ thao tác thực sự tham gia transaction đó |
| Dữ liệu đã commit | Đơn hàng được tạo để kiểm tra sau commit | Cleanup được commit hoặc hủy kho test riêng |
| Dữ liệu ở transaction độc lập | Lần ghi dùng `REQUIRES_NEW` | Dọn trong phạm vi riêng phù hợp |
| Dữ liệu nền | Danh mục hoặc cấu hình đọc chung | Chỉ đọc hoặc tạo lại có kiểm soát |
| Cache và trạng thái trong bộ nhớ | Cache ứng dụng, bộ đếm, event collector | Reset hoặc namespace riêng theo thiết kế |
| Hệ thống ngoài | Broker, object storage, dịch vụ HTTP giả lập | Vòng đời và cleanup riêng |

Mỗi ca kiểm thử cần biết mình sở hữu dữ liệu nào. Một bộ test chỉ nên xóa toàn bộ bảng khi nó thực sự có quyền sử dụng độc quyền phạm vi đó, ví dụ một database riêng của worker test.

## 2. Tách ba câu hỏi: đã lưu, đã flush hay đã commit?

Xét một ví dụ JPA:

```java
PurchaseOrder saved = orders.save(order);
PurchaseOrder loaded = orders.findById(saved.getId()).orElseThrow();
```

Nếu cùng persistence context, đối tượng `loaded` có thể được cung cấp từ trạng thái đang được quản lý. Đoạn này chưa tự chứng minh rằng transaction đã commit.

### 2.1. `save` thể hiện yêu cầu lưu qua repository

Implementation có thể tạo hoặc cập nhật entity theo chiến lược của store. ID có thể đã được cấp trước khi transaction hoàn tất. Không dùng sự tồn tại của ID làm bằng chứng duy nhất về commit.

### 2.2. `flush` đồng bộ thay đổi nhưng chưa kết thúc transaction

Trong JPA, flush có thể làm các câu lệnh cần thiết được gửi tới cơ sở dữ liệu và giúp phát hiện sớm một số lỗi mapping hoặc ràng buộc. Nếu transaction rollback sau đó, những thay đổi trong phạm vi đó vẫn bị hủy.

```text
save -> flush -> nhìn thấy trong cùng transaction -> rollback

Kết quả cuối: không có dữ liệu được commit từ lần ghi đó.
```

### 2.3. `clear` bỏ ảnh hưởng persistence context hiện tại

`EntityManager.clear()` tách các entity đang được quản lý, giúp một lần đọc sau không chỉ lấy lại cùng đối tượng từ persistence context cấp một. Nó không commit và cũng không tự giải quyết cache cấp hai hoặc query cache.

### 2.4. Commit cần được quan sát qua ranh giới thích hợp

Một cách tổ chức kiểm thử sau commit:

```text
Transaction ghi
    chuẩn bị dữ liệu cần ghi
    thực hiện thao tác
    kết thúc và commit thành công
                |
                v
Transaction đọc mới
    đọc bằng định danh hoặc request key
    tạo snapshot dữ liệu cần kiểm tra
    kết thúc transaction đọc
                |
                v
Assertion trên snapshot
                |
                v
Transaction cleanup riêng, commit việc xóa
```

“Transaction mới” là một ranh giới giao dịch mới; không bắt buộc pool phải cấp một connection vật lý chưa từng được sử dụng. Điều quan trọng là không tiếp tục đọc bằng chính trạng thái chưa commit của lần ghi.

## 3. Hiểu rollback mặc định của kiểm thử Spring

Trong Spring TestContext với transaction imperative được cấu hình, `@Transactional` trên lớp hoặc phương thức test thường tạo test-managed transaction và mặc định rollback sau khi test kết thúc. Các lifecycle method như `@BeforeEach` và `@AfterEach` thường chạy bên trong transaction đó. Xem [transaction management trong Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html).

Điều này hữu ích để giữ nhiều ca kiểm thử repository độc lập, nhưng phải phân biệt:

- Test-managed transaction do hạ tầng kiểm thử quản lý.
- Transaction do service của ứng dụng mở hoặc tham gia.
- Transaction do code kiểm thử chủ động quản lý bằng API theo chương trình.

Nếu service dùng propagation thông thường và cùng manager, nó có thể tham gia test transaction. Nếu service mở transaction độc lập, thay đổi đã commit ở transaction đó không tự bị rollback theo transaction test bên ngoài.

### 3.1. Cleanup bên trong transaction rollback có thể không dọn gì bền vững

Giả sử ca trước để lại một bản ghi đã commit. Ca sau xóa nó trong `@BeforeEach`, nhưng transaction của ca sau cuối cùng rollback:

```text
Trước test: bản ghi cũ tồn tại
Trong test: DELETE bản ghi cũ
Cuối test: ROLLBACK cả DELETE
Sau test: bản ghi cũ lại tồn tại
```

Vì vậy, không mặc định `deleteAll()` trong một lifecycle method đã làm sạch bền vững dữ liệu từ các lần chạy trước.

### 3.2. Gọi HTTP thật có thể tạo ranh giới khác

Nếu test gọi một server đang chạy qua HTTP, phần ghi của server thường diễn ra ở luồng và transaction riêng. Transaction bao quanh phương thức test phía client không tự bao được phần xử lý server.

Tương tự, một tác vụ chạy ở luồng khác không tự mang test-managed transaction imperative sang đó. Cần thiết kế dữ liệu test và cleanup theo phạm vi thực tế.

### 3.3. Timeout kiểu preemptive có thể làm thay đổi phạm vi

Công cụ timeout chạy thân test trên một luồng khác có thể khiến thao tác không tham gia transaction đang gắn với luồng test ban đầu. Đây là trường hợp được Spring nêu rõ với các cơ chế như `assertTimeoutPreemptively`.

Không kết luận “framework sẽ rollback mọi thứ” nếu đã thay đổi mô hình thực thi bằng luồng riêng, HTTP hoặc tác vụ bất đồng bộ.

## 4. Chọn chiến lược cô lập theo mục tiêu kiểm thử

| Chiến lược | Phù hợp khi | Giới hạn cần xử lý |
| --- | --- | --- |
| Rollback mỗi test | Kiểm tra thao tác trong cùng transaction, không cần commit thật | Không kiểm chứng after-commit; không bao tài nguyên hoặc transaction ngoài phạm vi |
| Database hoặc schema riêng cho mỗi worker | Test song song, cần dữ liệu độc lập | Chi phí khởi tạo, cấu hình và hủy tài nguyên |
| Dữ liệu có request key hoặc namespace riêng | Cần chạy nhiều ca trên hạ tầng dùng chung có kiểm soát | Mọi truy vấn và cleanup phải lọc đúng phạm vi |
| Reset toàn bộ dữ liệu test | Môi trường được dùng độc quyền | Không chạy đồng thời với các ca cần giữ dữ liệu trong cùng phạm vi |
| Tạo rồi commit, đọc mới, cleanup commit | Kiểm chứng dữ liệu sau commit | Phải cleanup cả khi assertion thất bại |

Một bộ test có thể phối hợp nhiều chiến lược. Ví dụ, dữ liệu danh mục bất biến được nạp một lần, còn dữ liệu đơn hàng của mỗi test mang request key riêng.

### 4.1. Đặt tên giúp nhận diện quyền sở hữu

Ví dụ request key:

```java
String requestKey = "commit-test-" + UUID.randomUUID();
```

Nếu request key là thuộc tính nghiệp vụ có sẵn, có thể dùng nó để liên kết và dọn dữ liệu của một ca. Không nhất thiết phải thêm một cột chỉ phục vụ test vào mọi entity.

Key duy nhất giảm xung đột giữa các ca, nhưng không tự cô lập những truy vấn toàn bảng, thao tác `deleteAll`, tài nguyên ngoài hoặc dữ liệu nền vẫn được sửa chung.

### 4.2. Dữ liệu cố định chỉ nên cố định những gì cần kiểm tra

Có thể cố định trạng thái, số lượng và thời điểm nghiệp vụ, nhưng tránh ép generated ID đầu tiên phải bằng 1 hoặc sequence phải liên tục. Rollback không bảo đảm mọi bộ sinh ID sẽ quay lại giá trị trước đó.

Với auditing, nên dùng nguồn thời gian và người dùng kiểm thử có thể điều khiển, thay vì assertion dựa vào thời điểm thực đang thay đổi giữa các môi trường.

## 5. Ví dụ kiểm chứng sau commit bằng TransactionTemplate

### 5.1. Giả định và hợp đồng ví dụ

Ví dụ chọn Spring Data JPA với một cơ sở dữ liệu quan hệ và `PlatformTransactionManager` tên `orderTransactionManager`. Repository và manager dùng đúng cùng tài nguyên.

Entity `PurchaseOrder` có:

- Generated ID kiểu `Long`.
- `requestKey` duy nhất.
- `status` và `quantity`.
- Factory `pending(requestKey, quantity)` tạo đơn mới có trạng thái `PENDING`.

Repository:

```java
import org.springframework.data.repository.CrudRepository;

import java.util.Optional;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByRequestKey(String requestKey);

    long countByRequestKey(String requestKey);
}
```

Các derived query ở đây được giả định hỗ trợ bởi module JPA và mapping trong ví dụ. Bài không triển khai đầy đủ entity hoặc cấu hình kết nối.

Mục tiêu ca kiểm thử: sau khi transaction ghi kết thúc thành công, một transaction mới nhìn thấy đúng một đơn có request key và thuộc tính đã lưu. Cấu hình test không dùng cache cấp hai hoặc query cache để che mất việc đọc trạng thái lưu trữ, và đọc từ nguồn dữ liệu chính phù hợp, không phải replica có độ trễ.

### 5.2. Lớp test với cleanup trong transaction riêng

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(OrderCommitTestConfiguration.class)
class PurchaseOrderCommitTest {

    @Autowired
    private PurchaseOrderRepository orders;

    @Autowired
    @Qualifier("orderTransactionManager")
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate independentTransaction;
    private String requestKey;

    @BeforeEach
    void prepareScope() {
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());

        independentTransaction = new TransactionTemplate(transactionManager);
        independentTransaction.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        requestKey = "commit-test-" + UUID.randomUUID();
    }

    @Test
    void committedOrderIsVisibleInAnotherTransaction() {
        Long savedId = independentTransaction.execute(status -> {
            PurchaseOrder saved = orders.save(
                    PurchaseOrder.pending(requestKey, 2));
            assertNotNull(saved.getId());
            return saved.getId();
        });

        assertNotNull(savedId);

        OrderSnapshot snapshot = independentTransaction.execute(status -> {
            PurchaseOrder loaded = orders.findByRequestKey(requestKey)
                    .orElseThrow();
            return new OrderSnapshot(
                    loaded.getId(),
                    loaded.getRequestKey(),
                    loaded.getStatus(),
                    loaded.getQuantity());
        });

        assertNotNull(snapshot);
        assertEquals(savedId, snapshot.id());
        assertEquals(requestKey, snapshot.requestKey());
        assertEquals("PENDING", snapshot.status());
        assertEquals(2, snapshot.quantity());

        Long count = independentTransaction.execute(status ->
                orders.countByRequestKey(requestKey));
        assertNotNull(count);
        assertEquals(1L, count.longValue());
    }

    @AfterEach
    void cleanCommittedData() {
        if (independentTransaction == null || requestKey == null) {
            return;
        }

        independentTransaction.executeWithoutResult(status ->
                orders.findByRequestKey(requestKey).ifPresent(orders::delete));

        Long remaining = independentTransaction.execute(status ->
                orders.countByRequestKey(requestKey));
        assertNotNull(remaining);
        assertEquals(0L, remaining.longValue());
    }

    record OrderSnapshot(
            Long id,
            String requestKey,
            String status,
            int quantity) {
    }
}
```

`OrderCommitTestConfiguration` là cấu hình do dự án cung cấp để tạo repository, entity manager và transaction manager thích hợp. Lớp test này không có `@Transactional` bao ngoài; assertion đầu xác nhận điều đó tại thời điểm chuẩn bị.

Mỗi lần `execute` tạo một ranh giới transaction mới theo cấu hình. Khi callback ghi trả về và bước commit của template hoàn tất bình thường, test mới chuyển sang transaction đọc. Snapshot được tạo bên trong transaction đọc để không phải mang một đồ thị entity lazy ra ngoài rồi vô tình phát sinh truy vấn khác.

`@AfterEach` không nằm trong test-managed transaction ở thiết kế này, nên transaction cleanup do template quản lý được kết thúc và commit riêng. Nó vẫn được thực thi khi phần assertion của test thông thường thất bại. Nếu tiến trình bị dừng đột ngột, lifecycle method không phải bảo đảm tuyệt đối; môi trường test cần cơ chế hủy hoặc reset phạm vi chạy tương ứng.

### 5.3. Điều ví dụ chưa chứng minh

Đây là kiểm thử persistence sau commit của thao tác được template bao quanh. Nó chưa chứng minh một service nhiều bước tự đặt đúng transaction boundary: template trong test có thể đang tạo một ranh giới mà service thực tế không có.

Muốn kiểm tra service, hãy gọi bean service thật qua proxy trong bối cảnh không có transaction test bao ngoài, gây lỗi ở vị trí nghiệp vụ cần kiểm tra, rồi đọc kết quả bằng transaction quan sát riêng. Không vô tình dùng transaction của test để che việc service thiếu ranh giới nguyên tử.

Một lỗi xuất hiện sau khi commit, chẳng hạn lỗi callback, cũng không tự chứng minh dữ liệu đã rollback. Khi yêu cầu liên quan tới trạng thái cuối, cần quan sát trạng thái lưu trữ theo hợp đồng thay vì chỉ dựa vào việc bên gọi nhận exception.

## 6. Khi đã có test-managed transaction: kết thúc nó một cách rõ ràng

Spring cung cấp `TestTransaction` để tương tác với test-managed transaction. Sau khi chuẩn bị và thao tác trong transaction hiện tại, có thể yêu cầu commit rồi kết thúc:

```java
import org.springframework.test.context.transaction.TestTransaction;

TestTransaction.flagForCommit();
TestTransaction.end();
```

`flagForCommit()` chỉ đặt ý định; `end()` mới kết thúc transaction hiện tại và thực hiện bước commit hoặc rollback tương ứng.

Sau đó có thể đọc trong một transaction mới được quản lý rõ ràng, hoặc dùng `TestTransaction.start()` nếu phù hợp cấu trúc test. Phải xử lý đầy đủ vòng đời: không gọi start khi transaction cũ vẫn còn active, không coi dữ liệu đã commit sẽ tự bị xóa bởi một transaction đọc được rollback sau đó.

Dữ liệu commit trong cách này vẫn cần cleanup riêng. Có thể sử dụng một template cleanup được cấu hình phù hợp như ví dụ trước, với `try/finally` hoặc lifecycle method chạy ngoài transaction đã kết thúc.

### 6.1. Vì sao chỉ thêm `@Commit` chưa đủ cho assertion sau commit?

`@Commit` cấu hình việc kết thúc test-managed transaction theo hướng commit. Assertion nằm trong thân phương thức test thường vẫn chạy trước thời điểm framework kết thúc transaction đó.

Do đó:

```text
Thân test chạy assertion
        |
        v
Phương thức test kết thúc
        |
        v
Hạ tầng test mới xử lý commit
```

Đừng đặt tên ca là “quan sát sau commit” chỉ vì có annotation `@Commit` trong khi toàn bộ lần đọc vẫn ở trong transaction chưa kết thúc.

### 6.2. Lifecycle bên ngoài transaction

`@BeforeTransaction` và `@AfterTransaction` của Spring hỗ trợ chạy logic trước và sau test-managed transaction. Chúng phù hợp với một số thiết kế chuẩn bị hoặc kiểm chứng trạng thái bên ngoài transaction test.

Cần chọn thiết kế dễ đọc nhất giữa template chủ động, `TestTransaction` và các callback lifecycle, thay vì trộn mọi cơ chế trong cùng một ca mà không còn biết transaction nào đang hoạt động.

## 7. Làm sạch dữ liệu theo đồ thị quan hệ

Dữ liệu thực thường không chỉ có một bảng đơn hàng. Có thể tồn tại order line, bản ghi giữ hàng, outbox và metadata liên quan.

Khi không có cascade phù hợp, cleanup thường phải xóa bản ghi phụ thuộc trước bản ghi cha. Ví dụ SQL theo phạm vi request key:

```sql
DELETE FROM order_line
WHERE order_id IN (
    SELECT id FROM purchase_order WHERE request_key = ?
);

DELETE FROM outbox_event
WHERE aggregate_key = ?;

DELETE FROM purchase_order
WHERE request_key = ?;
```

Đây là minh họa thứ tự và phạm vi, giả định schema tương ứng. Giá trị tham số phải được bind theo API truy cập dữ liệu sử dụng; không ghép trực tiếp request key vào chuỗi SQL.

### 7.1. Phân biệt cleanup kỹ thuật với hành vi xóa nghiệp vụ

Gọi repository để cleanup có thể kích hoạt callback, cascade hoặc cơ chế auditing theo module. Bulk delete hoặc SQL trực tiếp có thể bỏ qua một phần vòng đời entity và để persistence context đang mở chứa dữ liệu cũ.

Nếu mục tiêu là dọn hạ tầng test, hãy chọn cơ chế rõ ràng và phù hợp phạm vi. Nếu mục tiêu là kiểm thử xóa nghiệp vụ, phải đi qua đúng API nghiệp vụ cần xác nhận, không dùng cleanup SQL rồi kết luận hành vi xóa của repository đúng.

### 7.2. `TRUNCATE` và reset sequence không phải công cụ chung cho mọi store

Hành vi khóa, foreign key, transaction và bộ sinh ID khi truncate phụ thuộc cơ sở dữ liệu. Không áp dụng một script reset cho mọi môi trường mà không xét các khác biệt đó.

Ngay cả khi test cần khôi phục bảng rỗng, không phải lúc nào cũng cần reset sequence. Thường chỉ cần lấy ID trả về từ lần lưu và dùng nó trong assertion.

### 7.3. Không che lỗi cleanup

Nếu cleanup lỗi, bộ test phải thể hiện rằng môi trường có thể còn dữ liệu. Không bắt exception rồi chỉ ghi log thành công hoặc bỏ qua toàn bộ.

Thông tin chẩn đoán hữu ích gồm request key, nhóm tài nguyên được dọn và bước thất bại. Phải giữ được lỗi nghiệp vụ ban đầu cùng thông tin cleanup để tránh trường hợp lỗi phụ làm người đọc mất dấu nguyên nhân chính.

## 8. SQL fixture cần có transaction và thời điểm thực thi rõ ràng

Spring TestContext hỗ trợ `@Sql` để chạy câu lệnh hoặc script trước và sau test. Có thể cấu hình transaction mode và chọn manager phù hợp; xem [thực thi SQL script trong kiểm thử](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html).

Tuy nhiên, nhãn “sau test” chưa đủ để biết script có dọn dữ liệu bền vững không. Cần xác định:

1. Script chạy khi transaction nào đang active?
2. Nó tham gia transaction test hay transaction riêng?
3. Transaction đó cuối cùng commit hay rollback?
4. Nó có bị tranh chấp khóa với transaction test chưa kết thúc không?
5. Nó có chọn đúng datasource và transaction manager khi ứng dụng có nhiều store không?

Script cleanup ở transaction riêng có thể cần đợi hoặc bị khóa bởi transaction khác chưa kết thúc. Vì vậy, không chỉ bật một tùy chọn isolated rồi bỏ qua thứ tự lifecycle.

Không trộn việc tạo schema, nạp dữ liệu nền và xóa dữ liệu của từng ca vào một cơ chế khó suy luận. Chọn phạm vi phù hợp: schema theo môi trường, dữ liệu nền theo bộ test, dữ liệu biến đổi theo ca hoặc namespace.

## 9. Chạy song song: dữ liệu riêng và thao tác riêng

Hai test dùng request key khác nhau vẫn có thể tác động nhau nếu một test gọi `deleteAll()` hoặc đếm toàn bộ bảng.

```text
Test A tạo đơn request-A
Test B tạo đơn request-B
Test A xóa toàn bộ bảng
Test B đọc lại request-B -> không còn dữ liệu
```

Một thiết kế chạy song song cần xét đồng thời:

- Phạm vi dữ liệu ghi và đọc của mỗi test.
- Phạm vi thao tác cleanup.
- Dữ liệu nền dùng chung có bị sửa không.
- Những job nền nào có thể xử lý fixture.
- Tài nguyên ngoài và các key cache có cùng namespace không.

Có thể cấp database hoặc schema riêng cho từng worker, hoặc lọc dữ liệu theo key thuộc quyền sở hữu. Không dùng thứ tự chạy test như cách sửa sự phụ thuộc dữ liệu.

`@DirtiesContext` đánh dấu việc phải xây dựng lại Spring ApplicationContext, nhưng không tự xóa dữ liệu đã commit trong database bên ngoài. Reset object trong bộ nhớ và reset tài nguyên lưu trữ là hai công việc khác nhau.

## 10. After-commit, bất đồng bộ và store ngoài phạm vi

### 10.1. Listener sau commit cần một commit thật

`@TransactionalEventListener` có thể gắn xử lý với các pha của transaction; pha mặc định là `AFTER_COMMIT`. Một test chỉ rollback sẽ không kích hoạt hành vi sau commit theo cùng ý nghĩa. Xem [transaction-bound events của Spring](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Nếu listener ghi dữ liệu mới sau commit, cần xác định transaction thích hợp cho lần ghi đó; không mặc định transaction đã hoàn tất sẽ commit thêm một lần nữa cho mọi thay đổi mới.

### 10.2. Commit không đồng nghĩa mọi tác vụ nền đã hoàn tất

Commit thành công có thể mới chỉ tạo bản ghi outbox. Consumer gửi thông điệp hoặc cập nhật hệ thống khác có thể chạy sau đó.

Đối với tác vụ bất đồng bộ, nên chờ một điều kiện quan sát được với thời hạn rõ ràng, chẳng hạn trạng thái outbox hoặc sự kiện được collector kiểm thử ghi nhận. Không dùng một khoảng ngủ cố định rồi giả định mọi môi trường đều đủ nhanh.

Cleanup cũng cần phối hợp với tác vụ đang chạy. Nếu xóa fixture khi worker nền vẫn đang xử lý nó, worker có thể tạo lại dữ liệu sau cleanup và làm các ca sau thất bại.

### 10.3. Đọc từ replica hoặc search index là hợp đồng khác

Một lần đọc từ transaction mới trên nguồn dữ liệu chính khác với một lần đọc từ replica hoặc search index cập nhật bất đồng bộ. Nếu mục tiêu là kiểm tra khả năng quan sát cuối cùng, phải chỉ rõ điều kiện và giới hạn thời gian mong muốn, không nhầm độ trễ đồng bộ với việc transaction gốc chưa commit.

### 10.4. Reactive cần quản lý vòng đời publisher

Với store reactive, transaction dựa vào ngữ cảnh reactive và pipeline thực thi. Không tự áp rollback của test imperative lên một subscription riêng rồi kết luận dữ liệu sẽ được dọn.

Cần chờ publisher ghi transactional hoàn tất theo hạ tầng tương ứng, sau đó nối bước đọc trong phạm vi quan sát thích hợp và phối hợp cleanup cũng bằng công việc được subscribe, chờ và kiểm tra lỗi. Gọi `.subscribe()` để cleanup rồi kết thúc test ngay có thể để cleanup chưa chạy xong.

Khả năng transaction và cleanup còn tùy store: không giả định mọi kho đều có flush, foreign key, isolation và commit nhiều bản ghi như ví dụ JPA.

## 11. Các ca kiểm thử giúp đánh giá chính fixture lifecycle

| Tình huống | Kỳ vọng cần quan sát |
| --- | --- |
| Chạy một test hai lần liên tiếp | Lần sau không phụ thuộc dữ liệu còn lại từ lần trước |
| Assertion thất bại sau khi đã commit | Lifecycle cleanup vẫn được thực thi trong tiến trình test bình thường |
| Một bước ghi rollback | Transaction đọc riêng không thấy thay đổi bị hủy |
| Ghi thành công và commit | Transaction đọc mới thấy đúng snapshot theo key |
| Dữ liệu có bản ghi con | Cleanup xử lý đủ các quan hệ và không để dữ liệu mồ côi |
| Hai test chạy đồng thời | Cleanup của test này không xóa dữ liệu test kia |
| Tác vụ after-commit được kích hoạt | Quan sát được bằng cơ chế đồng bộ và điều kiện kết thúc rõ ràng |
| Môi trường có cache | Assertion không chỉ quan sát object cũ trong bộ nhớ |
| Có nhiều transaction manager | Ghi, đọc và cleanup dùng đúng tài nguyên cần kiểm chứng |

Nếu test chỉ xanh khi chạy đúng một thứ tự, hãy kiểm tra lại quyền sở hữu fixture và ranh giới cleanup trước khi thêm retry. Nếu test chỉ xanh khi bỏ commit thật, hãy kiểm tra thời điểm phát sinh ràng buộc, callback và lỗi ở giai đoạn kết thúc transaction.

Một ca kiểm thử đáng tin cậy phải giải thích được dữ liệu đến từ đâu, ai được phép thay đổi nó, khi nào commit hoàn tất, cách một bên quan sát mới đọc được kết quả và cách toàn bộ trạng thái thuộc ca được thu hồi. Khi các ranh giới này rõ ràng, kiểm thử repository, derived query, phân trang, projection và auditing sẽ ít phụ thuộc vào thứ tự chạy và phản ánh hành vi lưu trữ chính xác hơn.
