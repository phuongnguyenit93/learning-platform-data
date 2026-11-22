# Phân biệt `LockTimeoutException` và `PessimisticLockException` trong JPA

## 1. Vấn đề: yêu cầu khóa bi quan có thể thất bại theo hai cách

Trong ứng dụng dùng cơ sở dữ liệu quan hệ, hai giao dịch có thể cùng cần sửa một bản ghi. Nếu giao dịch thứ nhất đang nắm giữ khóa, giao dịch thứ hai có thể phải chờ. Với JPA (Jakarta Persistence), ứng dụng yêu cầu khóa bi quan bằng `LockModeType.PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` hoặc `PESSIMISTIC_FORCE_INCREMENT`, thường trong một transaction đang hoạt động.

Ví dụ: hai yêu cầu rút tiền đều muốn cập nhật cùng tài khoản. Yêu cầu A khóa tài khoản và chưa kết thúc transaction; yêu cầu B gọi `EntityManager.find(...)` với `PESSIMISTIC_WRITE` trên tài khoản đó. B có thể chờ, lấy được khóa khi A hoàn tất, hoặc thất bại vì giới hạn chờ/điều kiện khóa của database.

Khi thao tác lấy khóa bi quan thất bại, JPA phân biệt hai tình huống:

- **`LockTimeoutException`:** thao tác ở mức câu lệnh thất bại, nhưng theo hợp đồng JPA, provider **không đánh dấu toàn bộ transaction là rollback-only** chỉ vì lỗi khóa này.
- **`PessimisticLockException`:** lỗi khóa khiến **toàn bộ transaction phải rollback**; provider phải đánh dấu transaction để rollback.

Đây là điểm phân biệt chính. Tên `LockTimeoutException` gợi ý “hết thời gian chờ”, nhưng **không thể phân loại hai exception chỉ theo số giây đã chờ**. Phạm vi ảnh hưởng của lỗi lên transaction mới là căn cứ theo đặc tả JPA.

## 2. So sánh trực tiếp

| Tiêu chí | `LockTimeoutException` | `PessimisticLockException` |
|---|---|---|
| Ý nghĩa theo JPA | Không lấy được khóa bi quan; thất bại được xử lý ở **mức câu lệnh** | Không lấy được khóa bi quan; thất bại làm **transaction bị rollback** |
| Trạng thái transaction theo đặc tả | Provider không đánh dấu rollback-only chỉ vì exception này | Provider đánh dấu transaction rollback-only |
| Có thể tiếp tục cùng transaction? | **Có thể về mặt hợp đồng JPA**, nếu môi trường thực tế còn cho phép và logic nghiệp vụ an toàn | **Không** nên tiếp tục công việc rồi cố commit transaction đó |
| Cách xử lý thông thường | Thông báo tài nguyên bận, thử lại sau hoặc chủ động rollback để thử lại toàn bộ nghiệp vụ | Hủy transaction hiện tại; nếu có retry thì chạy lại trong **transaction mới** |
| Có luôn xảy ra đúng lúc hết thời gian chờ? | Không nên suy luận từ tên; phụ thuộc cách provider/database báo lỗi và phạm vi rollback | Không; deadlock hoặc lỗi tranh chấp khóa khác cũng có thể dẫn đến trường hợp này |
| Package Jakarta Persistence | `jakarta.persistence.LockTimeoutException` | `jakarta.persistence.PessimisticLockException` |
| Kiểu exception | Runtime exception, kế thừa `PersistenceException` | Runtime exception, kế thừa `PersistenceException` |

Cả hai đều là exception của tầng JPA. SQL error cụ thể, điều kiện deadlock, timeout cấu hình hay cách dịch exception có thể khác nhau giữa PostgreSQL, MySQL, Oracle, SQL Server và giữa các JPA provider. Vì vậy, **không có quy tắc phổ quát** rằng “lock wait timeout của database X luôn tạo exception A” hay “deadlock luôn tạo exception B”.

## 3. Hiểu đúng statement-level và transaction-level rollback

Giả sử cùng lúc có hai giao dịch:

~~~text
Transaction A                       Transaction B
BEGIN                               BEGIN
Đọc + giữ khóa bản ghi #42          Yêu cầu PESSIMISTIC_WRITE #42
Tiếp tục xử lý                       Chờ khóa...
(chưa COMMIT/ROLLBACK)               Không lấy được khóa
~~~

Từ điểm B không lấy được khóa, có hai khả năng theo ngữ nghĩa exception của JPA.

### 3.1. Lỗi chỉ ảnh hưởng câu lệnh: `LockTimeoutException`

~~~text
B: BEGIN
B: UPDATE/SELECT ... yêu cầu khóa
B:   ↳ yêu cầu khóa thất bại
B:   ↳ provider ném LockTimeoutException
B:   ↳ provider không tự đánh dấu transaction rollback-only
B: ứng dụng quyết định tiếp tục việc hợp lệ hoặc tự rollback
~~~

Nghĩa là **lỗi lấy khóa không mặc nhiên hủy tất cả thao tác trước đó trong transaction theo hợp đồng JPA**. Ví dụ, ứng dụng có thể quyết định bỏ qua một tác vụ tùy chọn khi không lấy được khóa, nếu transaction và trạng thái persistence context thực sự còn dùng được.

Tuy nhiên, đây **không phải bảo đảm mọi database đều cho phép chạy tiếp SQL** sau một lỗi câu lệnh. Một số database có thể đặt transaction ở trạng thái lỗi cho đến khi rollback. Ngoài ra, framework quản lý transaction có thể chủ động quyết định rollback khi exception thoát ra ngoài phương thức. Cần xét trạng thái thực tế thay vì mặc định cứ catch là tiếp tục được.

### 3.2. Lỗi làm hỏng toàn transaction: `PessimisticLockException`

~~~text
B: BEGIN
B: thực hiện vài thao tác hợp lệ
B: cố lấy khóa #42
B:   ↳ database/provider xác định thất bại ở mức transaction
B:   ↳ provider ném PessimisticLockException
B:   ↳ transaction bị đánh dấu rollback-only
B: mọi thay đổi trong transaction hiện tại phải được rollback
B: muốn thử lại → bắt đầu transaction khác
~~~

Giả sử B đã ghi trạng thái đơn hàng rồi mới lấy khóa tài khoản. Nếu ngoại lệ là `PessimisticLockException`, không được coi phần cập nhật đơn hàng là một kết quả có thể commit độc lập trong cùng transaction. Cần rollback và thiết kế lại lượt thực hiện nghiệp vụ trong một transaction mới nếu muốn thử lại.

**Điểm cần nhớ:** “Câu lệnh bị hủy” và “transaction bị hủy” là hai phạm vi khác nhau. Chúng không nhất thiết tương ứng một-một với “timeout” và “deadlock” trong lời mô tả ở tầng SQL.

## 4. Cách yêu cầu khóa bi quan trong JPA

Ví dụ dưới đây dùng Jakarta Persistence (các tên `jakarta.persistence.*`). Với dự án JPA 2.x còn dùng `javax.persistence.*`, tên package và khóa hint tương ứng có thể khác.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import java.util.Map;

Account account = entityManager.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of("jakarta.persistence.lock.timeout", 1_500)
);
~~~

Ở ví dụ này:

- `PESSIMISTIC_WRITE` yêu cầu khóa phù hợp cho thao tác cập nhật; SQL thực tế có thể giống `SELECT ... FOR UPDATE`, nhưng tùy database và provider.
- Hint `jakarta.persistence.lock.timeout` có giá trị **1.500 mili giây**: ứng dụng đề nghị giới hạn thời gian chờ khóa.
- Hint là yêu cầu gửi đến provider/database. Không được mặc định mọi tổ hợp JPA provider và database đều hỗ trợ, áp dụng chính xác tới mili giây hoặc sinh cùng một loại exception.
- Lệnh cần được chạy trong transaction phù hợp; khóa bi quan trên entity thường yêu cầu transaction đang hoạt động.

Có thể yêu cầu khóa khi entity đã được quản lý bằng `entityManager.lock(account, LockModeType.PESSIMISTIC_WRITE, hints)`; hoặc khóa kết quả truy vấn qua `query.setLockMode(LockModeType.PESSIMISTIC_WRITE)`.

### Phân biệt hint timeout của khóa và của truy vấn

| Hint | Phạm vi mục đích |
|---|---|
| `jakarta.persistence.lock.timeout` | Đề nghị thời gian tối đa để chờ **lấy khóa** |
| `jakarta.persistence.query.timeout` | Đề nghị thời gian tối đa để thực thi **truy vấn** |

Timeout ở tầng truy vấn có thể gắn với `QueryTimeoutException`, nên không nên gom tất cả các lỗi “timeout” thành `LockTimeoutException`. Kiểm tra đúng thao tác phát sinh lỗi và exception chain.

## 5. Ví dụ transaction và cách xử lý hai exception

Giả sử `Account` là entity có `getBalance()` / `setBalance(...)`, và ứng dụng dùng JPA với transaction kiểu `RESOURCE_LOCAL`. Đoạn sau minh họa xử lý một lần rút tiền; phần kiểm tra số dư chỉ nhằm tạo ngữ cảnh cho khóa.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.LockModeType;
import jakarta.persistence.LockTimeoutException;
import jakarta.persistence.PessimisticLockException;

import java.math.BigDecimal;
import java.util.Map;

public void withdraw(EntityManagerFactory emf, Long accountId, BigDecimal amount) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Account account = em.find(
            Account.class,
            accountId,
            LockModeType.PESSIMISTIC_WRITE,
            Map.of("jakarta.persistence.lock.timeout", 1_500)
        );

        if (account == null) {
            throw new IllegalArgumentException("Account not found");
        }
        if (account.getBalance().compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient balance");
        }

        account.setBalance(account.getBalance().subtract(amount));
        tx.commit();

    } catch (LockTimeoutException ex) {
        // JPA: lỗi khóa ở mức câu lệnh, provider không tự mark rollback-only.
        // Chính sách của nghiệp vụ rút tiền: chủ động hủy lượt này.
        rollbackIfActive(tx);
        throw ex;

    } catch (PessimisticLockException ex) {
        // JPA: transaction hiện tại phải rollback.
        rollbackIfActive(tx);
        throw ex;

    } catch (RuntimeException ex) {
        rollbackIfActive(tx);
        throw ex;

    } finally {
        em.close();
    }
}

private void rollbackIfActive(EntityTransaction tx) {
    if (tx.isActive()) {
        tx.rollback();
    }
}
~~~

**Vì sao cả hai nhánh đều gọi rollback trong ví dụ?** Vì đây là **quyết định nghiệp vụ**: một lần rút tiền chỉ thành công khi toàn bộ kiểm tra và cập nhật hoàn thành. Việc chủ động rollback khi gặp `LockTimeoutException` **không làm mất đi khác biệt** trong đặc tả: bản thân exception này không bắt buộc provider đánh dấu transaction rollback-only, trong khi `PessimisticLockException` có yêu cầu đó.

Nếu đang dùng JTA hay Spring quản lý transaction, không lấy `EntityTransaction` như ví dụ `RESOURCE_LOCAL`. Hãy để transaction manager xử lý rollback và đặt retry bên ngoài ranh giới transaction. Không nên sao chép cơ chế quản lý transaction thủ công vào một phương thức đã dùng `@Transactional`.

### Trường hợp muốn thử lại

Một lần thử lại chỉ nên được tính là một **lượt transaction độc lập**. Luồng tham khảo:

~~~text
Nhận yêu cầu nghiệp vụ
  └─ Bắt đầu transaction mới
       ├─ Lấy khóa bi quan
       ├─ Kiểm tra điều kiện nghiệp vụ
       ├─ Cập nhật dữ liệu
       └─ Commit
  └─ Nếu gặp lỗi tranh chấp khóa:
       ├─ Rollback lượt hiện tại
       ├─ Nếu thao tác an toàn để retry và còn trong giới hạn:
       │    chờ ngắn rồi chạy lại toàn bộ nghiệp vụ ở transaction mới
       └─ Nếu không:
            trả lỗi rõ ràng cho caller
~~~

Thực tế nên giới hạn số lần retry, thêm khoảng chờ tăng dần kèm jitter khi tải cao, và thiết kế nghiệp vụ **idempotent** nếu cùng yêu cầu có thể được gửi lại. Riêng `PessimisticLockException`, không tiếp tục dùng transaction đã rollback-only. Với `LockTimeoutException`, rollback cả lượt là lựa chọn thận trọng khi kết quả nghiệp vụ cần tính nguyên tử.

## 6. Lưu ý khi dùng Spring

Trong ứng dụng Spring sử dụng `@Transactional`, có **hai lớp quyết định rollback** cần phân biệt:

1. **JPA provider** quyết định transaction bị đánh dấu rollback-only theo ngữ nghĩa của exception JPA.
2. **Spring transaction interceptor** có quy tắc rollback riêng. Mặc định, một `RuntimeException` thoát ra ngoài phương thức `@Transactional` khiến Spring thực hiện rollback, **bao gồm cả `LockTimeoutException`** nếu không có cấu hình xử lý khác.

Vì vậy, phát biểu “`LockTimeoutException` không đánh dấu rollback-only” **không có nghĩa** “Spring chắc chắn sẽ commit transaction sau khi phương thức ném exception này”. Ngược lại, nếu provider đã đánh dấu rollback-only do `PessimisticLockException`, việc catch exception trong phương thức cũng không biến transaction đó trở lại trạng thái có thể commit.

Nếu ứng dụng bật chuyển đổi ngoại lệ của Spring Data/JPA, exception mà lớp service nhận được có thể là các lớp trong hệ thống `DataAccessException`, chẳng hạn một biến thể của `PessimisticLockingFailureException` hoặc `CannotAcquireLockException` tùy tình huống. **Không giả định mọi provider đều luôn chuyển thành một lớp Spring cố định.** Khi chẩn đoán, kiểm tra cả exception gốc và chuỗi `cause`.

Đặt cơ chế retry ở một lớp gọi **ngoài** phương thức `@Transactional`, để mỗi lần gọi tạo transaction mới; tự gọi lại cùng phương thức trong cùng bean có thể không đi qua transaction proxy như mong muốn.

## 7. Hai tình huống cần biết để tránh nhầm

### Tình huống A: Chờ khóa quá lâu

Transaction A đang cập nhật dòng `account_id = 42`. Transaction B gọi `find(..., PESSIMISTIC_WRITE, timeoutHint)` và không lấy được khóa trong giới hạn chờ.

- Nếu provider xác định chỉ câu lệnh yêu cầu khóa thất bại, kết quả phù hợp là **`LockTimeoutException`**.
- Nếu lỗi từ database khiến toàn transaction B phải rollback, kết quả phù hợp là **`PessimisticLockException`**.

Không thể nhìn riêng câu “đã chờ 1.500 ms” để kết luận exception nào chắc chắn xảy ra.

### Tình huống B: Deadlock giữa hai giao dịch

Transaction A giữ khóa dòng X rồi muốn khóa Y; transaction B giữ khóa Y rồi muốn khóa X. Database phát hiện vòng chờ và thường hủy một giao dịch để phá deadlock.

Nếu giao dịch bị hủy ở mức transaction, đó là tình huống tương ứng với **`PessimisticLockException`** trong ngữ cảnh khóa bi quan. Tuy nhiên, class cụ thể mà ứng dụng thấy có thể phụ thuộc SQL dialect, JPA provider và lớp chuyển đổi ngoại lệ. Không viết logic dựa trên giả định “cứ deadlock thì chắc chắn ném class này”.

Giải pháp phòng ngừa hữu ích là giữ **thứ tự lấy khóa nhất quán** (ví dụ, luôn khóa tài khoản có ID nhỏ hơn trước), rút ngắn transaction, tránh chờ I/O ngoài database khi giữ khóa, và sử dụng truy vấn có index phù hợp để giảm phạm vi khóa.

## 8. Cách chẩn đoán khi chạy thực tế

Khi production báo lỗi khóa bi quan, nên trả lời lần lượt những câu hỏi sau:

1. **Thao tác nào đang lấy khóa?** `find`, `lock`, `refresh`, hay truy vấn có `setLockMode`? Mode khóa và hint cụ thể là gì?
2. **Exception chính xác nằm ở lớp nào?** Kiểm tra lớp JPA, exception sau khi Spring dịch, và các `cause` bên trong. Thu thập thông tin SQLState/vendor error code nếu driver cung cấp.
3. **Transaction còn hợp lệ không?** Đã bị đánh dấu rollback-only, database đã hủy transaction, hay chỉ câu lệnh thất bại? Không suy từ tên exception khi môi trường có nhiều tầng dịch lỗi.
4. **Ai đang giữ khóa và trong bao lâu?** Kiểm tra transaction lâu, truy vấn gây khóa, trình tự truy cập nhiều bảng/bản ghi, deadlock log và chỉ số chờ khóa của database.
5. **Chính sách nghiệp vụ là gì?** Trả về “tài nguyên đang bận”, thử lại có giới hạn trong transaction mới, hay chuyển sang xử lý bất đồng bộ? Với thanh toán/chuyển tiền, phải kiểm soát idempotency trước khi retry.

Trong log, nên lưu mã nghiệp vụ/correlation ID, thao tác và thời điểm bắt đầu transaction, loại exception và nguyên nhân gốc. Tránh ghi dữ liệu nhạy cảm của tài khoản hoặc tham số SQL nhạy cảm vào log chỉ để điều tra lock.

## 9. Những phát biểu đúng và sai thường gặp

| Phát biểu | Đánh giá | Giải thích |
|---|---|---|
| “`LockTimeoutException` luôn có nghĩa cả transaction bị rollback.” | **Sai** | JPA định nghĩa trường hợp này là lỗi mức statement, không tự mark transaction rollback-only. |
| “`PessimisticLockException` cho phép catch rồi tiếp tục commit như thường.” | **Sai** | Transaction đã hoặc phải bị đánh dấu rollback-only. |
| “Hai exception chỉ khác nhau ở thời gian chờ.” | **Sai** | Điểm khác biệt thuộc **phạm vi rollback**. |
| “Cùng một tranh chấp khóa có thể cho kết quả khác nhau giữa các database/provider.” | **Đúng** | Tính chất rollback, tính năng khóa và cách chuyển lỗi khác nhau. |
| “Dùng `@Transactional` thì ném `LockTimeoutException` ra ngoài vẫn chắc chắn commit.” | **Sai** | Spring mặc định rollback khi RuntimeException thoát khỏi phương thức. |
| “Retry nên bắt đầu transaction mới và chạy lại toàn bộ thao tác cần tính nguyên tử.” | **Đúng** | Tránh tận dụng transaction không còn hợp lệ hoặc để lại kết quả nửa chừng. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một giao dịch chưa bị provider đánh dấu rollback-only sau khi yêu cầu khóa thất bại. Trong hai exception, tên nào thể hiện ngữ nghĩa này?

**Trả lời:** `LockTimeoutException`. Nhưng ứng dụng vẫn phải xem transaction manager và database có thực sự cho phép tiếp tục không.

**Câu 2.** Một transaction bị hủy vì không lấy được khóa bi quan. Có thể catch `PessimisticLockException` rồi thử `commit()` ngay trên transaction đó không?

**Trả lời:** Không. Rollback transaction cũ; nếu chính sách cho phép retry thì bắt đầu transaction mới.

**Câu 3.** Vì sao hai nhánh catch ở ví dụ rút tiền đều rollback, mặc dù định nghĩa của hai exception khác nhau?

**Trả lời:** Vì việc rút tiền phải là một thao tác nguyên tử. `LockTimeoutException` để ngỏ khả năng tiếp tục ở mức JPA, nhưng nghiệp vụ chọn hủy lượt thất bại để đảm bảo tính nhất quán.

**Câu 4.** Cấu hình `jakarta.persistence.lock.timeout = 1500` có đảm bảo mọi database đợi đúng 1.500 ms và luôn ném `LockTimeoutException` không?

**Trả lời:** Không. Hỗ trợ hint, độ chính xác timeout và cách báo lỗi còn phụ thuộc provider/database; kết quả cần được kiểm chứng trên stack đang dùng.

**Quy tắc cốt lõi:** Khi phân biệt hai ngoại lệ khóa bi quan của JPA, trước hết hãy hỏi **“thất bại này chỉ hủy câu lệnh hay đã buộc cả transaction rollback?”**. Câu trả lời quyết định cách xử lý an toàn ở tầng nghiệp vụ.
