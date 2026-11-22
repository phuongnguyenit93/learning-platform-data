# setRollbackOnly trong callback của TransactionTemplate — Spring Framework transaction management

Trong Spring Framework, **TransactionTemplate** giúp mở và hoàn tất một transaction bằng chương trình Java mà không cần đặt @Transactional lên từng method. Mỗi lời gọi **execute(...)** hoặc **executeWithoutResult(...)** nhận một callback được chạy trong transaction và cung cấp một đối tượng **TransactionStatus**. Khi quy tắc nghiệp vụ phát hiện cần hủy toàn bộ thay đổi nhưng không muốn ném exception ra caller, callback có thể gọi **status.setRollbackOnly()**.

Cách làm này dễ đọc nhưng có một điểm cực kỳ quan trọng: **setRollbackOnly() đánh dấu yêu cầu rollback; nó không lập tức chạy JDBC ROLLBACK ngay tại dòng đó**. Callback vẫn có thể chạy tiếp, thậm chí return một giá trị bình thường. TransactionTemplate sẽ xem trạng thái rollback-only khi hoàn tất boundary; nếu template sở hữu physical transaction, nó sẽ yêu cầu manager rollback thay vì commit. Vì thế, **giá trị trả về của callback không phải bằng chứng dữ liệu đã commit**.

Bài học nằm trong phần **TransactionTemplate** của module Spring Framework – transaction management. Nội dung tập trung vào thời điểm gọi setRollbackOnly trong callback, khác biệt với ném exception, cách báo kết quả nghiệp vụ, propagation lồng nhau, JDBC/JPA, kiểm thử và những lỗi phổ biến. Có chương trình Java 17+ sử dụng Spring JDBC/H2 để người học quan sát dữ liệu sau từng transaction.

## 1. Khi nào cần gọi setRollbackOnly?

Một giao dịch ứng dụng có thể bị từ chối theo quy tắc nghiệp vụ **sau khi đã chạy một số câu SQL**:

- Hai bước cập nhật phải cùng thành công, nhưng bước thứ hai trả updateCount=0.
- Một thao tác ghi được chấp nhận về mặt kỹ thuật, nhưng kiểm tra điều kiện nghiệp vụ cuối cùng không đạt.
- Cần trả về một **BusinessResult** như REJECTED hoặc CANCELLED cho caller, thay vì dùng exception cho mọi tình huống.
- Một callback bắt lỗi đã được phân loại là có thể chuyển thành kết quả nghiệp vụ, nhưng mọi thay đổi DB trước đó phải rollback.

Giả sử service chuẩn bị một đơn hàng:

~~~text
BEGIN transaction T1
  INSERT order_header
  INSERT order_line
  kiểm tra business constraint cuối cùng
  => không hợp lệ
  status.setRollbackOnly()
  return Result.REJECTED
TransactionTemplate hoàn tất T1:
  ROLLBACK tất cả thay đổi trong T1
Caller nhận Result.REJECTED
~~~

Đây là **một cách có chủ đích để hủy transaction mà vẫn trả kết quả nghiệp vụ**. Không nên coi việc return Result.REJECTED là tự động rollback: **chính setRollbackOnly** (hoặc exception/rollback rule hoặc cơ chế hạ tầng khác) mới yêu cầu rollback. Nếu callback chỉ return "REJECTED" mà không gọi setRollbackOnly và không có lỗi/marker khác, manager có thể commit các SQL đã thực thi.

### Mục tiêu sau bài học

Người học cần làm được:

1. Giải thích vòng đời TransactionTemplate và vai trò của TransactionStatus.
2. Đánh dấu rollback trong **execute** và **executeWithoutResult** bằng Java lambda.
3. Phân biệt rollback-only với throw exception, return null, return false và catch exception.
4. Biết vì sao gọi setRollbackOnly rồi tiếp tục ghi SQL là một thiết kế rủi ro.
5. Dự đoán kết quả khi callback tham gia **REQUIRED**, **NESTED** hoặc **REQUIRES_NEW** bên trong transaction khác.
6. Phân biệt callback tự sở hữu physical transaction với callback tham gia transaction đã có.
7. Kiểm chứng bằng trạng thái DB sau khi execute(...) trả về, không chỉ xem status.isRollbackOnly().
8. Xử lý riêng callback imperative của TransactionTemplate và reactive transaction operator.

## 2. Vòng đời của TransactionTemplate

TransactionTemplate hoạt động trên **PlatformTransactionManager** được cấp qua constructor. Với Spring JDBC, manager thường là **JdbcTransactionManager** hoặc **DataSourceTransactionManager**; với JPA có thể là **JpaTransactionManager**. Tất cả thao tác dữ liệu cần dùng tài nguyên mà manager tương ứng quản lý.

Luồng điển hình:

~~~text
Caller gọi transactionTemplate.execute(callback)
  |
  v
TransactionTemplate hỏi PlatformTransactionManager
  |
  +-- REQUIRED: tham gia transaction hiện có hoặc bắt đầu mới
  +-- cấu hình propagation, isolation, timeout, readOnly, name...
  |
  v
callback.doInTransaction(status)
  |
  +-- SQL thao tác qua JdbcTemplate/repository/EntityManager
  +-- callback có thể:
  |     a) trả về bình thường
  |     b) status.setRollbackOnly() rồi trả về
  |     c) ném RuntimeException/Error
  |
  v
TransactionTemplate hoàn tất scope
  |
  +-- callback ném RuntimeException/Error: rollback theo đường exception
  +-- status đã rollback-only: manager quyết định rollback
  +-- không lỗi/không rollback-only: manager cố commit
  |
  +-- nếu chỉ tham gia REQUIRED bên ngoài: không tự commit physical transaction
  |
  v
cleanup transaction resources và trả kết quả/exception cho caller
~~~

Điểm mấu chốt là **TransactionTemplate điều khiển boundary**, còn **TransactionStatus truyền vào callback biểu diễn status của scope đó**. Caller không cần và không nên tự gọi transactionManager.commit(status) hoặc rollback(status) trên status do template cấp; làm như vậy có thể khiến template hoàn tất lần thứ hai hoặc sử dụng status đã completed.

### API cốt lõi

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| new TransactionTemplate(manager) | Tạo template với manager | Cần chọn đúng DataSource/JPA resource |
| template.execute(status -> result) | Chạy callback và trả kết quả kiểu T | result có thể được trả ngay cả khi transaction rollback có chủ đích |
| template.executeWithoutResult(status -> ...) | Dành cho callback không cần result | Vẫn nhận status để đánh dấu rollback |
| status.setRollbackOnly() | Yêu cầu rollback khi scope hoàn tất | Không ném exception; không thực hiện rollback ngay tại dòng gọi |
| status.isRollbackOnly() | Kiểm tra trạng thái rollback-only được báo cho status | Không phải bằng chứng DB đã rollback vật lý |
| status.isNewTransaction() | Cho biết scope đang sở hữu transaction mới | false khi tham gia outer REQUIRED |
| status.hasSavepoint() | Cho biết scope đang mang savepoint | Thường true trong inner NESTED JDBC |
| status.isCompleted() | Cho biết status đã được manager hoàn tất | Trong callback thông thường chưa completed |
| template.setPropagationBehavior(...) | Chọn REQUIRED/NESTED/REQUIRES_NEW... | Cài đặt trước khi sử dụng đa luồng |
| template.setIsolationLevel(...), setTimeout(...), setReadOnly(...) | Metadata cho transaction definition | Tính hiệu lực phụ thuộc manager, DBMS và scope mới/tham gia |

Một instance **TransactionTemplate** có thể tái sử dụng giữa nhiều lời gọi và thread sau khi đã cấu hình ổn định, vì nó không giữ trạng thái cuộc hội thoại của từng transaction. Nhưng các **thuộc tính cấu hình của template là mutable**: đừng đổi propagation/timeout giữa chừng khi nhiều threads đang dùng chung instance. Nếu cần policy khác nhau, tạo template riêng với cấu hình riêng.

## 3. Cách dùng đơn giản nhất: đánh dấu rollback rồi return

### 3.1. execute(...) khi có kết quả nghiệp vụ

Ví dụ cho một callback xử lý hai bước SQL:

~~~java
// Snippet minh họa, giả định tx là TransactionTemplate,
// jdbc là JdbcTemplate và hai method updateA/updateB đã tồn tại.
BusinessResult result = tx.execute(status -> {
    updateA(jdbc);

    int affected = updateB(jdbc);
    if (affected != 1) {
        status.setRollbackOnly();
        return BusinessResult.rejected("Step B failed");
    }

    return BusinessResult.accepted();
});
~~~

Nếu updateB không cập nhật được row, callback đã thực hiện updateA, nhưng đánh dấu rollback-only rồi return REJECTED. Khi template quản lý **một physical transaction mới**, updateA bị rollback. **result vẫn là REJECTED**, nên ứng dụng có thể trả HTTP 409 hoặc thông báo nghiệp vụ thích hợp thay vì báo “OK”. Ở nơi có outer REQUIRED, hậu quả đối với outer cần phân tích riêng (phần propagation bên dưới).

Đây là snippet, không phải Java file biên dịch độc lập: cần class BusinessResult, hàm updateA/updateB và bean transaction manager thực tế. Mã chạy đầy đủ ở phần 8.

### 3.2. executeWithoutResult(...) khi không cần trả giá trị

~~~java
// Snippet: Spring 6.2; callback dùng consumer không trả về value.
tx.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO demo_event(message) VALUES (?)", "attempt");
    if (!businessConditionSatisfied()) {
        status.setRollbackOnly();
        return; // return khỏi lambda, không return một business value.
    }
    jdbc.update("INSERT INTO demo_event(message) VALUES (?)", "accepted");
});
~~~

Phương thức **executeWithoutResult** phù hợp khi caller không cần một đối tượng kết quả. Câu return; chỉ thoát khỏi lambda; nếu đã setRollbackOnly, template vẫn phải hoàn tất transaction theo trạng thái đó.

Không nên viết:

~~~java
// Sai về ý định nghiệp vụ: setRollbackOnly không dừng callback.
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET balance = balance - 10 WHERE id = 1");
    status.setRollbackOnly();

    // Dòng này VẪN có thể chạy nếu không return/throw.
    jdbc.update("UPDATE account SET balance = balance + 10 WHERE id = 2");
});
~~~

Dù các SQL cuối cùng có thể bị rollback, việc tiếp tục sau khi biết chắc giao dịch sẽ thất bại có thể gây tốn lock, truy vấn thừa, gây exception phụ và phát side effects ngoài database. Hãy **return ngay, hoặc throw exception** nếu cần caller biết lỗi qua exception.

### 3.3. Một dòng quan trọng: setRollbackOnly không phải lệnh rollback ngay

Đối chiếu:

~~~text
Bên trong callback:
  status.setRollbackOnly()
  status.isRollbackOnly() -> true
  transaction có thể vẫn đang active
  JDBC Connection/EntityManager có thể chưa được cleanup

Sau khi callback kết thúc và template hoàn tất scope:
  nếu scope sở hữu physical transaction -> manager thực hiện ROLLBACK
  nếu scope tham gia outer REQUIRED -> đánh dấu global rollback-only,
                                   physical transaction xử lý ở outer boundary
~~~

Với một transaction mới, **đối tượng status nhận marker trong callback** là nguồn quyết định khi template hoàn tất, không cần caller gọi rollback thủ công. Sau khi template trả về, status không nên tiếp tục được giữ và dùng như một API giao dịch đang hoạt động.

## 4. setRollbackOnly so với throw exception, return và catch

Một bảng giúp tránh sự nhầm lẫn thường gặp:

| Hành động trong callback | Trạng thái thường gặp khi sở hữu transaction mới | Caller nhận gì? |
| --- | --- | --- |
| return "OK" sau SQL thành công | Template cố commit | Giá trị "OK" nếu commit thành công |
| return "REJECTED" **không setRollbackOnly** | Có thể commit SQL trước đó | "REJECTED" nhưng database có thể đã thay đổi |
| status.setRollbackOnly(); return "REJECTED" | Rollback | "REJECTED" (nếu rollback xử lý thành công) |
| status.setRollbackOnly(); return null | Rollback | null; không phải exception |
| throw new IllegalStateException(...) | Rollback theo đường RuntimeException | Exception được ném lại cho caller |
| catch RuntimeException rồi return "OK" | Có thể commit nếu không bị đánh dấu rollback-only bởi scope/hạ tầng khác | "OK" nhưng có thể che giấu lỗi |
| catch RuntimeException; status.setRollbackOnly(); return "REJECTED" | Rollback | "REJECTED" nếu đường hoàn tất thành công |
| status.setRollbackOnly(); throw RuntimeException | Rollback theo đường exception | Exception; marker có thể dư thừa |

**Chú ý về checked exceptions:** callback Java thường không thể ném checked Exception trực tiếp khỏi lambda nếu functional interface không khai báo throws; cần xử lý/biến đổi phù hợp. TransactionTemplate xử lý RuntimeException/Error theo đường rollback của template; không dùng quy tắc declarative @Transactional checked-vs-unchecked một cách máy móc để suy đoán mọi đường exception của callback. Nếu bạn bắt một checked business error và muốn trả kết quả, có thể setRollbackOnly rồi return rõ ràng.

### 4.1. Khi nào dùng setRollbackOnly là tốt?

Nó hữu ích khi:

- Lỗi là một **kết quả nghiệp vụ kỳ vọng**, ví dụ không đủ điều kiện tiếp tục sau khi đã ghi tạm.
- API ngoài muốn nhận **Result/Outcome** thay vì exception, nhưng DB phải rollback hoàn toàn.
- Callback kiểm tra số row bị ảnh hưởng và muốn hủy những bước trước.
- Có một workflow ngắn mà code chủ ý điều khiển cả data access và outcome bên trong callback.

### 4.2. Khi nào nên ném exception?

Nên cân nhắc ném exception khi:

- Lỗi là bất thường, không phải outcome nghiệp vụ thông thường.
- Caller cần stack trace/cause để chẩn đoán hoặc áp dụng retry.
- Việc nuốt exception có thể che giấu inconsistency, DB transaction đã ở trạng thái lỗi hoặc cơ sở dữ liệu không thể tiếp tục thực thi.
- Transaction chỉ đơn giản là @Transactional declarative và exception policy đã mô tả rõ.

**Không gọi setRollbackOnly để thay thế xử lý lỗi**. Nếu một SQLException do connection mất hoặc DBMS đã abort transaction, việc đánh dấu rollback không làm connection lành lại hay tự sửa dữ liệu. Hãy để lỗi được truyền ra và transaction manager cleanup phù hợp.

### 4.3. Return value không chứng minh commit

Ví dụ:

~~~java
// Trong callback trả String, status biểu diễn transaction hiện tại.
String outcome = tx.execute(status -> {
    jdbc.update("UPDATE task SET state='DONE' WHERE id=1");
    status.setRollbackOnly();
    return "DONE";
});
~~~

Sau execute, caller có thể nhận String **"DONE"** dù UPDATE không commit. Đây là một **API contract nguy hiểm**. Nếu application muốn trả result, hãy dùng giá trị phản ánh thực tế, ví dụ "CANCELLED" hoặc "REJECTED"; không trả SUCCESS khi đã yêu cầu rollback. Khi callback tham gia outer transaction, ngay cả return thành công từ inner cũng chưa xác nhận physical commit.

## 5. TransactionStatus: những gì cần hiểu và không nên làm

**TransactionStatus** là interface chứa trạng thái của execution hiện tại; status được cấp cho một callback cụ thể.

### 5.1. setRollbackOnly là một chiều

Sau khi đã đặt rollback-only, không có API an toàn để “unset” marker và tiếp tục commit transaction đó. Nếu business logic thay đổi ý định sau khi đánh dấu rollback, cách đúng thường là kết thúc/rollback transaction rồi thực hiện **một transaction mới**, không lách vào internals để xóa flag.

~~~java
// Snippet: không có status.unsetRollbackOnly() để phục hồi.
tx.executeWithoutResult(status -> {
    if (mustAbort()) {
        status.setRollbackOnly();
        return;
    }
    doDatabaseWork();
});
~~~

Các phương thức mustAbort và doDatabaseWork là minh họa. Trong một scope đang tham gia transaction có sẵn, marker có thể khiến **outer transaction không còn khả năng commit**; điều này đặc biệt quan trọng với REQUIRED.

### 5.2. isRollbackOnly là tín hiệu, không phải trạng thái DB cuối

Trong callback:

~~~java
tx.executeWithoutResult(status -> {
    System.out.println("initial rollback-only=" + status.isRollbackOnly());
    status.setRollbackOnly();
    System.out.println("after marking=" + status.isRollbackOnly());
});
~~~

Thường in false, true trong một transaction mới, không có rollback-only marker từ trước. Nhưng **true không đồng nghĩa JDBC ROLLBACK vừa được gửi đến DBMS**; template mới quyết định kết thúc scope sau callback. Đừng dựa vào log “rollback only=true” để tuyên bố toàn bộ data đã được hoàn tác; phải đọc lại DB sau boundary.

### 5.3. isNewTransaction phân biệt owner với participant

Khi TransactionTemplate REQUIRED chạy không có transaction hiện hành, status.isNewTransaction() thường true. Khi template REQUIRED được gọi trong một outer REQUIRED transaction, inner status thường **không sở hữu physical transaction mới**.

~~~text
Không có outer:
  template(REQUIRED) -> status.isNewTransaction() = true
  marker -> rollback physical transaction của chính scope

Có outer T1:
  outer template(REQUIRED) -> owner của T1
  inner template(REQUIRED) -> status.isNewTransaction() = false
  inner marker -> T1 bị ảnh hưởng, không có commit riêng ở inner
~~~

Status mang theo thông tin tiết lộ trạng thái context; nó **không phải một JDBC Connection** và không nên được truyền sang thread khác để đổi trạng thái của transaction imperative trong thread hiện tại.

### 5.4. hasSavepoint trong NESTED

Nếu một template PROPAGATION_NESTED chạy bên trong JDBC transaction hỗ trợ savepoint, status.hasSavepoint() thường true. Marker setRollbackOnly() trên nested status làm manager **rollback về savepoint**, cho phép outer tiếp tục nếu điều kiện DBMS cho phép. Không phải mọi manager/JPA provider đều hỗ trợ nested savepoint semantics.

## 6. Gắn vào API nghiệp vụ: Result thay vì nuốt lỗi

Có thể mô hình hóa outcome:

~~~java
// Ví dụ Java 17: record để mô tả dữ liệu, không tự quản lý transaction.
public record TransferResult(boolean accepted, String reason) {
    public static TransferResult ok() {
        return new TransferResult(true, "accepted");
    }
    public static TransferResult rejected(String reason) {
        return new TransferResult(false, reason);
    }
}
~~~

Trong service có TransactionTemplate:

~~~java
// Trích đoạn, cần class có field TransactionTemplate tx và JdbcTemplate jdbc.
public TransferResult transfer(long from, long to, long amount) {
    return tx.execute(status -> {
        int debit = jdbc.update(
            "UPDATE wallet SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount);
        if (debit != 1) {
            status.setRollbackOnly();
            return TransferResult.rejected("source missing or insufficient funds");
        }

        int credit = jdbc.update(
            "UPDATE wallet SET balance = balance + ? WHERE id = ?",
            amount, to);
        if (credit != 1) {
            status.setRollbackOnly();
            return TransferResult.rejected("destination missing");
        }

        return TransferResult.ok();
    });
}
~~~

**Đây là snippet**, không phải một chương trình biên dịch độc lập vì chưa có class/config/imports. Nó minh họa hợp đồng hợp lý:

- Một callback bao cả debit và credit.
- Mỗi nhánh không hợp lệ **đánh dấu rollback-only và return ngay**.
- Caller nhận result mô tả outcome đúng với commit/rollback mong muốn.
- Nếu debit cập nhật thành công nhưng credit ảnh hưởng 0 row, thay đổi debit bị rollback.
- Khi result accepted=true, template cố commit nhưng **commit vẫn có thể ném lỗi**, do đó caller chỉ được coi accepted là thành công khi execute thực sự return mà không có exception từ manager.

Trong ứng dụng tài chính còn cần xử lý số âm, overflow, tài khoản nguồn/đích trùng nhau, optimistic locking hoặc row locking, isolation và idempotency. Một local JDBC transaction không tự làm HTTP/email/DB khác tham gia rollback.

### 6.1. “Tôi không muốn exception” khác “Tôi không muốn rollback”

Không ít service viết:

~~~java
// KHÔNG an toàn nếu SQL đầu tiên đã làm thay đổi DB.
return tx.execute(status -> {
    jdbc.update("UPDATE wallet SET balance = balance - 10 WHERE id=1");
    if (!canComplete()) {
        return "REJECTED";  // Thiếu status.setRollbackOnly()
    }
    jdbc.update("UPDATE wallet SET balance = balance + 10 WHERE id=2");
    return "OK";
});
~~~

Nếu canComplete() là false, callback **return bình thường** và transaction thường commit debit trước đó. Điều này dễ tạo “đã trừ nhưng chưa cộng”. Hãy xác định mọi nhánh từ chối: đã có SQL side effect trước đó chưa? Nếu có, rollback marker/exception phải rõ ràng.

Tốt hơn nữa là **kiểm tra các điều kiện không biến đổi** trước khi mở transaction nếu an toàn; nhưng bất biến có thể thay đổi bởi request đồng thời, nên các điều kiện quan trọng phải được **kiểm tra lại trong transaction** hoặc bảo vệ bằng constraint/locking.

## 7. Hai cách gọi hiện đại: execute và executeWithoutResult

### 7.1. execute(callback) trả dữ liệu

TransactionTemplate triển khai TransactionOperations, với execute nhận **TransactionCallback<T>**. Lambda nhận status và trả T:

~~~java
String result = tx.execute(status -> {
    performStepOne();
    if (!allowed()) {
        status.setRollbackOnly();
        return "CANCELLED";
    }
    performStepTwo();
    return "COMPLETED";
});
~~~

Đây là snippet với các phương thức nghiệp vụ minh họa. Java suy ra T là String; caller có thể nhận null nếu callback trả null. Không giả định null đồng nghĩa rollback. Muốn dùng checked errors hoặc Result object, thiết kế loại trả về rõ ràng.

### 7.2. executeWithoutResult(callback) trả void

Trên Spring Framework hiện đại như 6.2, có thể gọi:

~~~java
tx.executeWithoutResult(status -> {
    insertAuditDraft();
    if (mustCancel()) {
        status.setRollbackOnly();
        return;
    }
    finishAudit();
});
~~~

Nếu đọc ví dụ cũ, bạn có thể thấy **TransactionCallbackWithoutResult** với doInTransactionWithoutResult(status) hoặc lambda execute trả null. Các dạng đó đều dùng một transaction callback và cho phép setRollbackOnly; ví dụ bài này ưu tiên executeWithoutResult cho trường hợp không cần giá trị.

### 7.3. Cấu hình transaction definition

~~~java
// Snippet khởi tạo trong constructor Spring service hoặc @Bean.
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(15);
tx.setReadOnly(false);
~~~

- REQUIRED: nếu không có transaction, tạo mới; nếu có outer transaction phù hợp, tham gia outer.
- Isolation: khi transaction mới bắt đầu, manager áp policy ở resource; khi tham gia transaction đã có, isolation inner có thể không đổi.
- Timeout: thời gian yêu cầu cho transaction; mức enforce còn tùy manager/driver và query.
- Read-only: hint về mục đích read, không phải quyền DB bắt buộc cấm write.
- Template nên được cấu hình xong **trước khi đưa vào dùng đồng thời**.

Mặc định TransactionTemplate dùng settings tương đương DefaultTransactionDefinition thông thường. Không cần gọi setPropagationBehavior(REQUIRED) nếu chỉ muốn default, nhưng đặt tường minh trong bài thực hành giúp dễ đọc.

## 8. Chương trình Java 17+ kiểm chứng trực tiếp trên H2

Ví dụ sau chạy Spring Framework 6.2.12 với Spring JDBC, H2 in-memory và Java 17+. Không dùng Spring Boot để có thể nhìn rõ PlatformTransactionManager. Bảng demo_balance có hai row A và B, amount=0. Mỗi thao tác thay đổi amount bằng UPDATE. Chương trình reset dữ liệu trước mỗi scenario, vì vậy kết quả sau từng callback dễ so sánh.

**Các ca kiểm thử:**

1. Callback return OK, không đánh dấu rollback → commit.
2. Callback setRollbackOnly rồi return CANCELLED → rollback nhưng caller vẫn nhận CANCELLED.
3. Bước đầu UPDATE thành công, bước sau UPDATE row không tồn tại → setRollbackOnly và return REJECTED → rollback bước đầu.
4. executeWithoutResult với setRollbackOnly → rollback dù không có return value.
5. Callback ném RuntimeException → rollback và exception truyền ra.
6. Inner template REQUIRED setRollbackOnly khi tham gia outer REQUIRED → physical transaction ngoài không commit, caller outer có thể nhận UnexpectedRollbackException.
7. Inner template NESTED setRollbackOnly → rollback về savepoint; outer vẫn commit phần thay đổi của nó.

### 8.1. Cấu trúc

~~~text
transaction-template-rollback-only/
├── pom.xml
└── src/main/java/demo/RollbackOnlyDemo.java
~~~

### 8.2. Maven dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-template-rollback-only</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.RollbackOnlyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong ứng dụng Spring Boot thật, nên dùng Spring Boot dependency management/BOM đúng với version Boot thay vì ép riêng Spring version mà không kiểm tra tương thích. DriverManagerDataSource chỉ phù hợp demo/test; production thường dùng một connection pool được cấu hình phù hợp.

### 8.3. Java main đầy đủ

**src/main/java/demo/RollbackOnlyDemo.java**

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionTemplate;

public final class RollbackOnlyDemo {
    private RollbackOnlyDemo() {}

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE demo_balance SET amount = 0");
    }

    private static void add(JdbcTemplate jdbc, int id) {
        int rows = jdbc.update(
                "UPDATE demo_balance SET amount = amount + 1 WHERE id = ?",
                id);
        if (rows != 1) {
            throw new IllegalStateException("Missing row: " + id);
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT amount FROM demo_balance WHERE id = ?",
                Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT amount FROM demo_balance WHERE id = ?",
                Integer.class, 2);
        return "A=" + a + ", B=" + b;
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("CREATE TABLE demo_balance (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update(
                    "INSERT INTO demo_balance(id, amount) VALUES (?, ?)", 1, 0);
            jdbc.update(
                    "INSERT INTO demo_balance(id, amount) VALUES (?, ?)", 2, 0);

            TransactionTemplate tx = new TransactionTemplate(manager);
            tx.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);

            TransactionTemplate participating = new TransactionTemplate(manager);
            participating.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);

            TransactionTemplate nested = new TransactionTemplate(manager);
            nested.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_NESTED);

            System.out.println("initial: " + balances(jdbc));

            // 1. Không set rollback-only: commit cả hai UPDATE.
            reset(jdbc);
            String accepted = tx.execute(status -> {
                add(jdbc, 1);
                add(jdbc, 2);
                return "OK";
            });
            System.out.println("1 commit: result=" + accepted +
                    ", " + balances(jdbc));

            // 2. Đánh dấu rollback; vẫn return kết quả nghiệp vụ.
            reset(jdbc);
            String cancelled = tx.execute(status -> {
                add(jdbc, 1);
                add(jdbc, 2);
                status.setRollbackOnly();
                return "CANCELLED";
            });
            System.out.println("2 mark rollback: result=" + cancelled +
                    ", " + balances(jdbc));

            // 3. UPDATE bước 2 không thành công; rollback bước 1.
            reset(jdbc);
            String rejected = tx.execute(status -> {
                add(jdbc, 1);
                int rows = jdbc.update(
                        "UPDATE demo_balance " +
                        "SET amount = amount + 1 WHERE id = ?", 999);
                if (rows != 1) {
                    status.setRollbackOnly();
                    return "REJECTED";
                }
                add(jdbc, 2);
                return "OK";
            });
            System.out.println("3 reject: result=" + rejected +
                    ", " + balances(jdbc));

            // 4. Không có return value, vẫn có thể rollback.
            reset(jdbc);
            tx.executeWithoutResult(status -> {
                add(jdbc, 1);
                status.setRollbackOnly();
            });
            System.out.println("4 without result: " + balances(jdbc));

            // 5. Throw RuntimeException: template rollback và ném lại.
            reset(jdbc);
            boolean caught = false;
            try {
                tx.executeWithoutResult(status -> {
                    add(jdbc, 1);
                    throw new IllegalStateException("test exception");
                });
            } catch (IllegalStateException expected) {
                caught = true;
            }
            System.out.println("5 exception: caught=" + caught +
                    ", " + balances(jdbc));

            // 6. Inner REQUIRED tham gia outer; inner marker chặn commit T1.
            reset(jdbc);
            boolean unexpected = false;
            try {
                tx.executeWithoutResult(outer -> {
                    add(jdbc, 1);
                    participating.executeWithoutResult(inner -> {
                        add(jdbc, 2);
                        inner.setRollbackOnly();
                    });
                });
            } catch (UnexpectedRollbackException expected) {
                unexpected = true;
            }
            System.out.println("6 joined REQUIRED: unexpected=" + unexpected +
                    ", " + balances(jdbc));

            // 7. Inner NESTED có savepoint: hủy B nhưng outer commit A.
            reset(jdbc);
            Boolean savepoint = tx.execute(outer -> {
                add(jdbc, 1);
                return nested.execute(inner -> {
                    add(jdbc, 2);
                    boolean found = inner.hasSavepoint();
                    inner.setRollbackOnly();
                    return found;
                });
            });
            System.out.println("7 NESTED: savepoint=" + savepoint +
                    ", " + balances(jdbc));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:rollback_only_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            JdbcTransactionManager manager = new JdbcTransactionManager(ds);
            manager.setNestedTransactionAllowed(true);
            return manager;
        }
    }
}
~~~

**Tại sao mã chạy được với một Java file?** Config và các hàm tiện ích đều nằm trong class RollbackOnlyDemo; transaction manager, DataSource và JdbcTemplate được Spring khởi tạo, còn TransactionTemplate được tạo trong main. Không cần @EnableTransactionManagement vì ví dụ **không sử dụng @Transactional advice**: TransactionTemplate tự gọi manager. Với Spring JDBC, JdbcTemplate dùng đúng transaction-bound Connection của JdbcTransactionManager.

### 8.4. Chạy và stdout dự kiến

Từ thư mục transaction-template-rollback-only:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến của Java main** (không tính log riêng của Maven/Spring):

~~~text
initial: A=0, B=0
1 commit: result=OK, A=1, B=1
2 mark rollback: result=CANCELLED, A=0, B=0
3 reject: result=REJECTED, A=0, B=0
4 without result: A=0, B=0
5 exception: caught=true, A=0, B=0
6 joined REQUIRED: unexpected=true, A=0, B=0
7 NESTED: savepoint=true, A=1, B=0
~~~

Diễn giải:

1. **1 commit**: callback trả OK, không có rollback-only marker; cả hai UPDATE được commit.
2. **2 mark rollback**: cả A và B được UPDATE nhưng status.setRollbackOnly() khiến physical transaction rollback; caller vẫn nhận CANCELLED.
3. **3 reject**: bước A đã UPDATE, nhưng bước B không tìm thấy row 999; callback đánh dấu rollback-only rồi return REJECTED. A=0 xác nhận cập nhật trước đó cũng bị hủy.
4. **4 without result**: executeWithoutResult không trả business value nhưng status vẫn có thể yêu cầu rollback.
5. **5 exception**: callback ném IllegalStateException; template rollback rồi ném lại. Caller bắt được exception, DB không đổi.
6. **6 joined REQUIRED**: inner TransactionTemplate với propagation REQUIRED không mở physical transaction riêng, mà tham gia outer T1. Inner đánh dấu rollback-only; outer cố hoàn tất bình thường nhưng T1 không thể commit, do đó Spring phát sinh UnexpectedRollbackException ở outer boundary. Cả A và B được rollback.
7. **7 NESTED**: outer cập nhật A; inner NESTED cập nhật B, hasSavepoint=true rồi setRollbackOnly làm rollback về savepoint. Outer vẫn commit A. Kết quả A=1,B=0 cho thấy marker có phạm vi khác khi scope là savepoint NESTED.

Các giá trị được đọc **sau khi TransactionTemplate đã hoàn tất**; đó là bằng chứng về dữ liệu cuối cùng. Trên database/manager khác, đặc biệt manager không hỗ trợ savepoint, kịch bản NESTED có thể bị từ chối thay vì chạy thành công. Không dùng stdout H2 để suy rộng tất cả behavior của JPA hoặc DBMS production.

### 8.5. Vì sao không dùng try/catch để tự commit/rollback trong callback?

TransactionTemplate đã quản lý begin/commit/rollback/cleanup. Trong callback, ứng dụng nên sử dụng callback status để đánh dấu rollback hoặc ném exception, **không tự lấy một TransactionStatus khác rồi gọi commit/rollback lên status do template quản lý**.

Nếu cần toàn quyền gọi PlatformTransactionManager trực tiếp, đó là một workflow programmatic thấp hơn: getTransaction(definition), commit(status) hoặc rollback(status) trong finally/catch. Không trộn workflow đó với status của một TransactionTemplate.execute call.

## 9. Điểm khó: callback REQUIRED tham gia transaction ngoài

Với REQUIRED, **setRollbackOnly trong callback nội bộ có thể tác động lên toàn physical transaction**, ngay cả khi callback nội bộ không ném exception.

Giả sử:

~~~text
T1 outer @Transactional(REQUIRED) hoặc TransactionTemplate(REQUIRED)
   |
   +-- UPDATE A
   |
   +-- inner TransactionTemplate(REQUIRED):
   |     UPDATE B
   |     innerStatus.setRollbackOnly()
   |     return bình thường
   |
   +-- outer tiếp tục và muốn COMMIT
   |
   +-- physical transaction T1 đã bị đánh dấu rollback-only
   +-- manager ROLLBACK T1
   +-- caller outer có thể nhận UnexpectedRollbackException
~~~

**Lý do của UnexpectedRollbackException:** caller outer không tự yêu cầu rollback và có thể tưởng rằng đã commit khi method outer trả thành công. Spring phát exception để không báo nhầm thành công khi transaction bị rollback do một participating scope. Nếu **outer owner tự gọi outerStatus.setRollbackOnly()**, rollback có chủ ý của owner thường hoàn tất mà không cần UnexpectedRollbackException trong trường hợp mới/độc lập.

### 9.1. Không nên chỉ nhìn inner callback return

~~~java
// Snippet, outerTx và innerTx đều REQUIRED trên cùng manager/DB.
outerTx.executeWithoutResult(outer -> {
    jdbc.update("UPDATE demo_balance SET amount=amount+1 WHERE id=1");
    innerTx.executeWithoutResult(inner -> {
        jdbc.update("UPDATE demo_balance SET amount=amount+1 WHERE id=2");
        inner.setRollbackOnly();
    });
    // Inner đã return, nhưng physical transaction chung không thể commit.
});
~~~

Nếu outer có đường gọi khác vẫn ghi sau inner, SQL có thể tiếp tục trước khi outer boundary phát hiện final rollback; điều đó không biến transaction thành có thể commit. Nên trả kết quả lỗi sớm tới outer hoặc thiết kế lại để outer quyết định abort. Đừng nuốt marker rồi return success.

### 9.2. Phân biệt isRollbackOnly trên status của các scope

Một inner status có **local rollback-only** sau setRollbackOnly. Khi inner REQUIRED hoàn tất, manager có thể chuyển yêu cầu này thành **global rollback-only trên physical transaction**. Vì outer status là logical scope khác, không nên suy luận từ local flag của một status khác mà thiếu thông tin global marker/manager. API có các cơ chế kiểm tra trạng thái nhưng chi tiết phụ thuộc manager và transaction implementation.

Thiết kế tốt hơn là trả về một **typed Result** cho outer để outer tự quyết định setRollbackOnly khi điều kiện bắt buộc hủy toàn bộ. Nếu cần một đoạn có thể rollback riêng, cân nhắc NESTED khi JDBC savepoint được hỗ trợ hoặc REQUIRES_NEW khi thực sự cần physical transaction độc lập.

## 10. Cùng một dòng setRollbackOnly nhưng NESTED khác REQUIRES_NEW

TransactionTemplate cũng cho phép cấu hình propagation khác.

| Propagation của inner khi đã có outer | Phạm vi xử lý | Tác động của inner setRollbackOnly |
| --- | --- | --- |
| REQUIRED | Tham gia cùng physical transaction T1 | Khi inner kết thúc, transaction chung có thể bị đánh dấu rollback-only; outer không thể commit |
| NESTED | Cùng T1 nhưng có savepoint S1, nếu manager hỗ trợ | Rollback các thay đổi từ S1, outer có thể tiếp tục/commit phần còn lại |
| REQUIRES_NEW | Suspend outer T1, mở physical transaction T2 độc lập | Rollback T2; outer T1 có thể tiếp tục nếu không bị lỗi/marker riêng |
| SUPPORTS | Tham gia nếu có T1; nếu không thì không có actual transaction | Không thể suy luận luôn có physical rollback khi không có transaction |
| NOT_SUPPORTED | Chạy ngoài transaction, suspend outer nếu cần | Không có local DB transaction để rollback bằng marker thông thường |

### 10.1. NESTED dựa trên savepoint

Trong demo, nested template NESTED sử dụng JdbcTransactionManager và H2 có savepoint. Khi inner setRollbackOnly, manager rollback về savepoint. **Outer không phải rollback cả T1**. Đây là cơ chế partial rollback, không phải NESTED có commit độc lập.

~~~text
T1 begin
  UPDATE A
  SAVEPOINT S1
     UPDATE B
     nestedStatus.setRollbackOnly()
  ROLLBACK TO S1
  UPDATE C
T1 commit
=> A và C có thể được commit; B bị rollback
~~~

NESTED với JPA EntityManager không có ý nghĩa giống hệt JDBC savepoint: savepoint trên JDBC Connection không tự làm sạch toàn bộ state cache/dirty entities trong persistence context. JpaTransactionManager thường không bật nestedTransactionAllowed mặc định. Phải kiểm chứng provider/manager/DBMS, không dùng NESTED như một mẹo để xóa bất kỳ lỗi ORM nào.

### 10.2. REQUIRES_NEW dùng transaction độc lập

~~~text
T1 outer begin, UPDATE A
  suspend T1
  T2 inner begin, UPDATE B
  innerStatus.setRollbackOnly()
  ROLLBACK T2
  resume T1
T1 commit
=> A được giữ, B mất
~~~

Nếu inner T2 setRollbackOnly rồi return bình thường, outer vẫn có thể commit T1 (nếu không có lỗi/marker khác). Nhưng REQUIRES_NEW thường cần thêm JDBC Connection khi outer đang giữ resource; có thể tăng áp lực connection pool, lock wait hoặc deadlock khi inner cần tài nguyên outer đang khóa. Không dùng chỉ vì muốn outer thoát UnexpectedRollbackException mà không cân nhắc nghiệp vụ.

### 10.3. Khi nào nên đặt marker ở outer?

Nếu business rule nói “không được commit bất kỳ bước nào của ca sử dụng”, owner transaction ngoài có thể gọi outerStatus.setRollbackOnly() sau khi nhận kết quả inner. Nếu một bước con được phép thất bại riêng nhưng các bước trước/sau vẫn phải commit, cần ranh giới savepoint hoặc physical transaction độc lập có chủ đích, không cố biến REQUIRED thành partial rollback.

## 11. Tương tác với @Transactional trong Spring service

Có thể dùng TransactionTemplate bên trong một service đã có @Transactional, nhưng cần hiểu **ai sở hữu physical transaction**.

~~~java
// Snippet: outerMethod phải được gọi qua Spring proxy.
@Transactional
public void outerMethod() {
    innerTransactionTemplate.executeWithoutResult(status -> {
        repository.write();
        status.setRollbackOnly();
    });
    // TransactionTemplate default REQUIRED thường tham gia outer transaction.
}
~~~

Nếu inner template dùng REQUIRED và cùng transaction manager, marker có thể khiến **outer rollback** và báo UnexpectedRollbackException. Không giả định inner template sẽ tự tạo một transaction độc lập chỉ vì bạn dùng new TransactionTemplate(...). Propagation default là REQUIRED.

### 11.1. So với TransactionAspectSupport

Trong declarative transaction, có thể truy cập current status bằng:

~~~java
// Chỉ hợp lệ trong Spring AOP transactional invocation tương ứng.
org.springframework.transaction.interceptor.TransactionAspectSupport
        .currentTransactionStatus()
        .setRollbackOnly();
~~~

Cách này làm mã nghiệp vụ phụ thuộc Spring transaction infrastructure. Với TransactionTemplate, **status đã được cấp trực tiếp vào callback**; đó là API đúng và đơn giản nhất trong ngữ cảnh này. Không cần gọi TransactionAspectSupport.currentTransactionStatus() bên trong callback.

Nếu muốn code domain thuần không phụ thuộc framework, nên để application service quyết định transaction policy ở ngoài domain và để domain trả lỗi/exception/result; không ép domain object gọi setRollbackOnly trực tiếp.

### 11.2. Self-invocation không giống vấn đề của callback

Một method @Transactional gọi this.otherTransactionalMethod() trong cùng bean có thể bỏ qua Spring AOP proxy. TransactionTemplate là API programmatic gọi trực tiếp; **nếu thực sự chạy tx.execute(...)**, nó có thể tạo transaction theo manager mà không cần AOP interception. Tuy nhiên, nếu bạn kết hợp cả hai, **outer @Transactional có thể không được kích hoạt** do self-invocation; template bên trong sẽ chạy theo context thực sự đang có. Phải kiểm tra entrypoint, không chỉ đọc annotation.

## 12. TransactionManager và DataSource phải khớp

Ví dụ callback:

~~~java
tx.executeWithoutResult(status -> {
    jdbcTemplate.update("UPDATE demo_balance SET amount=amount+1 WHERE id=1");
    status.setRollbackOnly();
});
~~~

Để UPDATE bị rollback, JdbcTemplate phải dùng **DataSource thuộc transaction manager đang điều phối** và transaction context của lời gọi:

- JdbcTransactionManager/DataSourceTransactionManager quản lý connection của DataSource tương ứng.
- JdbcTemplate dùng DataSourceUtils để tham gia connection gắn với Spring transaction trong thread.
- Nếu code tự mở một JDBC Connection khác bằng DriverManager hoặc dùng một DataSource khác, UPDATE có thể autocommit ngoài transaction.
- Nếu repository ghi DB khác trong callback, marker trên local manager không tự rollback DB khác.
- Nếu bật JPA, transaction manager và EntityManagerFactory/persistence context phải tương thích.

**Không có transaction manager nào khiến email, HTTP calls, file writes hoặc message đã gửi tự hoàn tác** chỉ bằng status.setRollbackOnly(). Nếu nghiệp vụ cần phát event sau commit, cân nhắc transactional outbox hoặc callback after-commit phù hợp. Nếu một request có thể retry, side effects phải idempotent.

## 13. Khi DBMS đã abort transaction, setRollbackOnly không “chữa” được

Một số DBMS, điển hình PostgreSQL, có thể đưa transaction vào trạng thái **failed/aborted** sau lỗi SQL. Các SQL tiếp theo trong cùng physical transaction có thể báo trạng thái “current transaction is aborted”. Đánh dấu rollback-only không reset transaction đó để chạy tiếp.

Ví dụ nguy hiểm:

~~~java
// Snippet mô tả lối xử lý KHÔNG an toàn cho PostgreSQL sau SQL error.
tx.executeWithoutResult(status -> {
    try {
        jdbc.update("INSERT INTO demo(id) VALUES (1)");
        jdbc.update("INSERT INTO demo(id) VALUES (1)"); // unique violation
    } catch (org.springframework.dao.DataAccessException ex) {
        status.setRollbackOnly();
        // Không tiếp tục nhiều câu SQL mới trong transaction đã failed.
        return;
    }
});
~~~

Cách an toàn khi gặp lỗi dữ liệu không dự đoán trước là để transaction kết thúc/rollback, sau đó bắt đầu transaction mới nếu nghiệp vụ retry được. Nếu muốn retry lỗi transient như deadlock/serialization failure, phải đảm bảo **mỗi attempt có transaction mới** và đọc lại điều kiện nghiệp vụ. Không viết retry loop bên trong một callback sau khi transaction đã bị abort.

Trong JPA, lỗi flush hoặc persistence exception cũng có thể khiến EntityManager/transaction không còn an toàn để tiếp tục; không dùng setRollbackOnly như công tắc phục hồi persistence context.

### Những thứ cần giữ ngoài transaction có thể rollback

- Gửi email/SMS.
- Publish Kafka/RabbitMQ message trực tiếp mà không có consistency protocol.
- Gọi API thanh toán hoặc bên thứ ba.
- Upload file hoặc ghi hệ thống ngoài database.
- Chờ một Future/remote call dài, sleep/backoff retry.
- Ghi các logs nghiệp vụ bắt buộc còn sau rollback nếu chúng nằm cùng DB transaction.

Nếu cần audit **mọi lần thử** kể cả giao dịch chính rollback, có thể thiết kế transaction độc lập có chủ đích hoặc hệ thống logging ngoài DB transaction, nhưng phải xác định đúng ý nghĩa và tác dụng phụ.

## 14. TransactionTemplate, TransactionalOperator và asynchronous code

Bài này dùng **PlatformTransactionManager** và TransactionTemplate cho imperative JDBC/JPA. Trong reactive stack, Spring sử dụng **ReactiveTransactionManager** và **TransactionalOperator**, với **ReactiveTransaction** và signal-based lifecycle.

Không sử dụng status từ TransactionTemplate trên thread khác để rollback một physical JDBC transaction đã hoàn tất. Nếu callback chỉ lên lịch một async task rồi return, TransactionTemplate có thể commit/rollback ngay lúc callback return, **không đợi CompletableFuture hoàn tất**. Transaction context của PlatformTransactionManager thường gắn với thread hiện tại.

~~~java
// Snippet minh họa lỗ hổng ranh giới thời gian.
tx.execute(status -> {
    CompletableFuture<Void> future = CompletableFuture.runAsync(
            () -> performDatabaseWorkInAnotherThread());
    return future; // Callback return trước khi worker nhất thiết hoàn tất.
});
~~~

Đoạn này thiếu imports/method và không độc lập. TransactionTemplate imperative không tự kéo dài transaction tới lúc worker Future hoàn tất. Nếu worker SQL cần transactional atomicity, hãy tạo boundary trong worker hoặc thiết kế workflow độc lập. Nếu async task hoàn tất thất bại **sau khi transaction của template đã kết thúc**, không thể gọi setRollbackOnly để rollback hồi tố.

Spring reactive transaction operator có API setRollbackOnly riêng qua callback reactive, nhưng phải theo Reactor Context và lifecycle của publisher. Không chuyển code imperative sang reactive chỉ bằng đổi kiểu trả về.

## 15. Logging và kiểm tra rollback thật

Trong ứng dụng có Spring Boot logging, có thể bật tạm:

~~~properties
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
logging.level.org.springframework.transaction.support=TRACE
~~~

Có thể thấy log manager chứa nội dung tương tự:

~~~text
Creating new transaction ...
Acquired Connection ...
Switching JDBC Connection to manual commit ...
Initiating transaction rollback ...
Rolling back JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

Với callback tự đánh dấu rollback-only, không bắt buộc xuất hiện stack trace ứng dụng vì **không có exception được ném ra**. Không dựa vào log câu chữ cố định: logger, manager, version và mức log có thể thay đổi.

Nếu dùng connection pool, “releasing JDBC Connection” có thể có nghĩa **trả connection về pool**, không phải đóng socket vật lý. TransactionTemplate cleanup quản lý resource binding; không nên tự đóng connection do Spring đang quản lý trong callback.

### Ba cấp xác minh

1. **Trong callback:** status.isRollbackOnly() sau khi đánh dấu cho biết rollback requested.
2. **Ngay sau execute:** template đã hoàn tất scope nó quản lý; nếu tạo transaction mới, commit/rollback đã được manager xử lý (hoặc exception được ném).
3. **Đọc từ transaction/connection độc lập:** trạng thái cuối DB cho biết thay đổi đã commit hay không, tránh nhầm với dữ liệu chưa commit nhìn thấy trong cùng transaction.

Với một template REQUIRED **tham gia outer transaction**, execute kết thúc **chưa đồng nghĩa physical commit/rollback đã xong**. Kết quả cuối cần đọc sau outer boundary.

## 16. Kiểm thử: tránh “xanh giả” do @Transactional test

Trong Spring TestContext, test method có @Transactional có thể tự mở outer transaction và mặc định rollback khi test kết thúc. Khi gọi TransactionTemplate REQUIRED bên trong test đó, nó **tham gia outer test transaction**, nên:

- status.isNewTransaction() có thể false.
- Nếu inner gọi setRollbackOnly, nó có thể làm rollback-only toàn test transaction.
- Các assertions đọc trong cùng connection/context chưa xác nhận physical commit.
- Test framework rollback cuối test có thể làm mọi case trông như đều rollback, ngay cả khi logic production quên setRollbackOnly.

Để kiểm tra đúng semantics cần:

- Chạy transaction theo ranh giới production, không bị outer test transaction vô tình bao.
- Khởi tạo dữ liệu trước, gọi service/template rồi để boundary hoàn tất.
- Đọc kết quả từ connection/transaction mới.
- Test cả nhánh accepted, rejected, exception và propagation.
- Khi kiểm tra outer REQUIRED joined, assert UnexpectedRollbackException ở owner boundary nếu đó là behavior đang dùng.
- Khi dùng NESTED, kiểm tra manager/driver/savepoint thực sự hỗ trợ.
- Khi dùng JPA, flush/clear EntityManager hoặc dùng persistence context mới để tránh đọc cache.
- Test side effects ngoài DB một cách tách biệt; chỉ rollback DB không đủ chứng minh mọi event không bị phát.

### Test matrix đề xuất

| Ca | SQL đã chạy trong callback? | setRollbackOnly? | Expected result khi sở hữu transaction mới |
| --- | --- | --- | --- |
| Hoàn tất bình thường | Có | Không | Commit; return accepted |
| Từ chối sau bước 1 | Có | Có | Rollback; return rejected |
| executeWithoutResult hủy | Có | Có | Rollback; không có result |
| RuntimeException thoát ra | Có | Không nhất thiết | Rollback; exception tới caller |
| Catch exception, return bình thường | Có | Không | Có thể commit — case cần cảnh báo |
| Catch exception, mark, return | Có | Có | Rollback; typed result |
| Inner REQUIRED mark khi outer active | Có | Có ở inner | Global rollback, outer có thể UnexpectedRollbackException |
| Inner NESTED mark khi outer active | Có | Có ở nested | Rollback về savepoint, outer có thể commit |
| Inner REQUIRES_NEW mark khi outer active | Có | Có ở inner | Rollback transaction inner; outer độc lập |

### Unit test và integration test bổ sung

Unit test với mock JdbcTemplate có thể kiểm tra rằng code **gọi setRollbackOnly đúng nhánh**, nhưng không thể chứng minh DB transaction rollback thật khi không có DBMS/resource. Integration test nên dùng H2 cho bước học cơ bản và database production (PostgreSQL/MySQL/Oracle...) nếu logic phụ thuộc isolation, savepoint, constraint hoặc DB error behavior.

Trong ứng dụng có nhiều transaction managers, mỗi test cần biết manager nào đang được template sử dụng, không suy diễn chỉ từ annotation @Transactional trên service khác.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| return "FAILED" nhưng quên setRollbackOnly | Template có thể commit SQL đã chạy | Đặt marker hoặc throw khi cần rollback |
| setRollbackOnly rồi trả "SUCCESS" | Caller tưởng commit dù DB rollback | Dùng typed Result thể hiện CANCELLED/REJECTED |
| setRollbackOnly nhưng không return/throw | Callback tiếp tục SQL/side effects không cần thiết | Dừng callback ngay khi quyết định rollback |
| Gọi transactionManager.rollback(status) ngay trong template callback | Template còn phải hoàn tất status, gây double handling | Chỉ dùng status.setRollbackOnly() hoặc ném exception |
| Nghĩ status.setRollbackOnly() rollback ngay | Transaction vẫn active tới khi template xử lý | Xem rollback marker là yêu cầu tại boundary |
| Đọc status.isRollbackOnly=true rồi coi DB đã rollback | Marker không phải physical outcome | Query sau khi outer boundary kết thúc |
| Inner REQUIRED mark nhưng outer return success | Physical transaction bị rollback, có thể UnexpectedRollbackException | Thiết kế outer biết kết quả lỗi và xử lý đúng |
| Dùng NESTED cho JPA mà chưa kiểm tra provider | Savepoint không đồng nghĩa quay ngược persistence context | Xác minh transaction manager/DBMS hoặc tránh |
| Nghĩ new TransactionTemplate luôn tạo transaction riêng | Default REQUIRED có thể tham gia outer | Chọn propagation có chủ đích |
| Dùng REQUIRES_NEW tùy tiện để né rollback chung | Inner commit/rollback độc lập, pool/locks khác | Chọn theo bất biến nghiệp vụ |
| Bắt SQLException rồi tiếp tục SQL sau marker | DB transaction có thể đã aborted | Kết thúc/rollback, retry trong transaction mới |
| Gửi email trước khi callback quyết định rollback | Email không bị rollback | Outbox/after-commit/idempotency |
| Truyền TransactionStatus sang thread khác | Transaction imperative theo execution context | Boundary riêng trong worker |
| Dùng TransactionTemplate nhưng gọi JDBC Connection tự mở | SQL có thể autocommit ngoài managed transaction | Dùng JdbcTemplate/DataSource đúng manager |
| Đổi template config giữa các threads | Shared mutable configuration gây race | Cấu hình trước, dùng template riêng cho policy khác |
| Test method @Transactional làm mọi dữ liệu biến mất cuối test | Che dấu thiếu rollback-only trong business code | Test qua boundary độc lập, đọc lại DB |
| Kiểm tra exception string thay vì class/cause | Mất stack/cause và error classification | Giữ nguyên cause, phân loại rõ trước retry |

## 18. Thực hành suy luận trước khi chạy code

**Câu 1.** Trong một TransactionTemplate tạo physical transaction mới, callback UPDATE A rồi setRollbackOnly rồi return "OK". Sau execute, điều gì xảy ra?  
**Đáp án:** Manager rollback A, nhưng caller vẫn có thể nhận "OK" nếu không có lỗi khi rollback. Return value không chứng minh commit; code nên trả CANCELLED/REJECTED.

**Câu 2.** Callback UPDATE A, catch BusinessException rồi return "REJECTED" mà không mark/throw. Có rollback không?  
**Đáp án:** Không mặc nhiên. Nếu không có rollback-only marker từ nơi khác, TransactionTemplate có thể commit A vì callback return bình thường.

**Câu 3.** status.setRollbackOnly() có ném exception ngay tại dòng gọi không?  
**Đáp án:** Không; nó đánh dấu rollback. Callback cần tự return/throw để không chạy thêm SQL ngoài ý định.

**Câu 4.** Khi executeWithoutResult(status -> ...) dùng return;, return đó mang dữ liệu gì?  
**Đáp án:** Không mang business value; return chỉ thoát lambda. Manager vẫn xử lý rollback marker lúc hoàn tất.

**Câu 5.** Inner template REQUIRED join outer T1 rồi setRollbackOnly, outer cố commit. Vì sao có thể có UnexpectedRollbackException?  
**Đáp án:** Inner đã làm physical transaction chung không thể commit. Outer có thể không biết, nên Spring phát exception để không báo nhầm đã commit.

**Câu 6.** Nếu inner NESTED dùng savepoint và setRollbackOnly, outer có bắt buộc rollback không?  
**Đáp án:** Không nếu manager/DBMS hỗ trợ savepoint và outer không có lỗi khác. Inner rollback phần sau savepoint; outer vẫn có thể commit các bước còn lại.

**Câu 7.** Nếu một callback trực tiếp dùng REQUIRES_NEW và mark rollback-only, outer có bị rollback theo không?  
**Đáp án:** Không tự động. Inner là physical transaction riêng, outer có thể tiếp tục; quyết định nghiệp vụ ở caller có thể yêu cầu outer cũng rollback.

**Câu 8.** status.isRollbackOnly=true có nghĩa một email đã gửi sẽ bị thu hồi không?  
**Đáp án:** Không. Nó chỉ tác động đến resource transaction được manager điều phối; email là side effect ngoài DB.

**Câu 9.** Có cần @EnableTransactionManagement để dùng TransactionTemplate trong demo không?  
**Đáp án:** Không. TransactionTemplate gọi PlatformTransactionManager trực tiếp; @EnableTransactionManagement cần cho xử lý @Transactional bằng proxy trong Spring config thông thường.

**Câu 10.** Nếu một INSERT gây unique violation trên PostgreSQL rồi callback catch lỗi và mark, có nên tiếp tục INSERT khác trong transaction không?  
**Đáp án:** Không mặc nhiên. Transaction có thể đã failed; cần kết thúc/rollback, rồi retry ở transaction mới khi business policy cho phép.

**Câu 11.** Tại sao unit test mock repository không chứng minh được rollback?  
**Đáp án:** Mock không có physical transaction và commit/rollback database thật; cần integration test kiểm tra trạng thái DB sau boundary.

**Câu 12.** Đặt status.setRollbackOnly() trong callback và gọi transactionManager.rollback(status) thủ công có tốt hơn không?  
**Đáp án:** Không. TransactionTemplate đã sở hữu lifecycle. Chỉ dùng status marker hoặc exception để template làm việc; tránh double completion.

## 19. Checklist áp dụng trong dự án

1. **Xác định đơn vị atomic:** Những SQL nào phải cùng commit hoặc cùng rollback?
2. **Chọn đúng manager:** JdbcTransactionManager/JpaTransactionManager và DataSource/EntityManagerFactory tương ứng.
3. **Chọn boundary:** TransactionTemplate trong application service; không mở transaction tùy tiện quanh mọi method nhỏ.
4. **Định nghĩa outcome:** accepted/rejected/cancelled/error; đừng dùng "SUCCESS" cho rollback có chủ đích.
5. **Kiểm tra mọi nhánh return:** Có SQL nào đã chạy mà nhánh return báo lỗi thiếu setRollbackOnly không?
6. **Gọi marker rồi dừng sớm:** status.setRollbackOnly(); return outcome hoặc throw khi cần.
7. **Không tự gọi commit/rollback thủ công** trên status template đã cấp.
8. **Phân tích outer transaction:** REQUIRED join, NESTED savepoint hay REQUIRES_NEW independent transaction?
9. **Tách transient DB exceptions:** rollback rồi retry toàn use case trong transaction mới, có giới hạn và idempotency.
10. **Không phát side effects thiếu bảo vệ** trước khi commit.
11. **Integration test dữ liệu sau boundary:** H2 cho demo, DBMS production khi behavior khác biệt.
12. **Quan sát log/metrics:** commit, rollback, rollback-only, UnexpectedRollbackException và connection pool duration.

## 20. Kết luận

**setRollbackOnly trong TransactionTemplate callback là cách rõ ràng để yêu cầu hủy các thay đổi thuộc transaction scope mà không bắt buộc ném exception.** Đặc điểm then chốt:

- Callback có thể return bình thường nhưng transaction cuối cùng **rollback**.
- Marker không làm callback tự dừng; nên return ngay sau khi quyết định hủy.
- **Giá trị trả về không xác nhận physical commit**. Đặt tên Outcome phản ánh rollback thật sự.
- Một callback **tạo transaction mới** thường có thể rollback có chủ đích mà không gây exception cho caller.
- Một callback **REQUIRED tham gia outer** có thể khiến outer cuối cùng nhận UnexpectedRollbackException.
- Một callback **NESTED** có thể rollback savepoint mà không hủy outer; **REQUIRES_NEW** rollback transaction riêng.
- Xác minh DataSource/manager, proxy context nếu kết hợp @Transactional, và kết quả đọc lại từ DB sau boundary.

Đây là công cụ hữu ích khi cần biểu diễn **business rejection có rollback** bằng Result object. Khi chỉ cần rollback theo exception một cách thông thường, @Transactional declarative có thể đơn giản và ít phụ thuộc infrastructure hơn. Chọn cách nào cũng phải bảo đảm business invariant, không tự gửi side effects rồi mong rollback DB sẽ hoàn tác được.

## Tài liệu tham khảo

- [Spring Framework — Programmatic Transaction Management / TransactionTemplate](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction Propagation và UnexpectedRollbackException](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — TransactionStatus API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Spring JDBC Connection Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)

**Ghi nhớ cuối bài:** Trong callback của TransactionTemplate, nếu một nhánh business cần trả về từ chối sau khi đã ghi dữ liệu, hãy đánh dấu rollback-only trước khi return; sau đó kiểm tra trạng thái DB sau khi boundary hoàn tất. Việc chọn đúng phạm vi transaction quan trọng không kém việc gọi đúng một API.
