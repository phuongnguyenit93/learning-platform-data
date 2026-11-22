# Giao dịch, mức cô lập và truy cập đồng thời trong cơ sở dữ liệu quan hệ

Trong ứng dụng dùng Spring Data Relational R2DBC, nhiều thao tác ghi thường phải được thực hiện như một đơn vị: tạo đơn hàng và trừ tồn kho, ghi nợ và ghi có khi chuyển tiền, hoặc cập nhật dữ liệu cùng với trạng thái xử lý. Nếu một bước thành công nhưng bước tiếp theo thất bại, dữ liệu có thể rơi vào trạng thái không nhất quán. Đồng thời, nhiều request có thể đọc và sửa cùng một bản ghi trong cùng thời điểm.

Giao dịch (transaction) xác định ranh giới mà trong đó các câu lệnh SQL được xử lý cùng nhau. Mức cô lập (isolation level) quy định một giao dịch có thể quan sát những thay đổi đồng thời đến đâu. Cơ chế kiểm soát đồng thời (concurrency control) giúp bảo vệ các quy tắc nghiệp vụ khi nhiều giao dịch cùng thao tác trên dữ liệu.

Với R2DBC, các khái niệm cơ sở dữ liệu này vẫn giữ nguyên, nhưng cách Spring quản lý giao dịch gắn với luồng reactive và Reactor Context thay vì dựa chủ yếu vào ThreadLocal như cách làm imperative truyền thống.

## 1. Vì sao cần giao dịch?

Hãy xét thao tác chuyển 500.000 đồng từ tài khoản A sang tài khoản B. Về nghiệp vụ, thao tác gồm hai câu lệnh:

1. Trừ 500.000 đồng khỏi số dư tài khoản A.
2. Cộng 500.000 đồng vào số dư tài khoản B.

Nếu câu lệnh đầu thành công nhưng câu lệnh thứ hai lỗi, tiền sẽ bị trừ khỏi A mà không được cộng vào B. Giao dịch cho phép cơ sở dữ liệu commit cả hai thay đổi hoặc rollback cả hai thay đổi.

Một giao dịch quan hệ thường được mô tả bằng bốn thuộc tính ACID:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Atomicity – tính nguyên tử | Các thay đổi trong giao dịch cùng thành công hoặc cùng bị hủy | Không để thao tác chuyển tiền chỉ trừ tiền mà không ghi có |
| Consistency – tính nhất quán | Giao dịch đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ khác, theo các ràng buộc đã định nghĩa | Số dư không được âm nếu đó là quy tắc của hệ thống |
| Isolation – tính cô lập | Các giao dịch đồng thời không được quan sát lẫn nhau theo cách vi phạm mức cô lập đã chọn | Một giao dịch không đọc dữ liệu chưa commit của giao dịch khác |
| Durability – tính bền vững | Sau khi commit thành công, dữ liệu được lưu bền vững theo cam kết của hệ quản trị cơ sở dữ liệu | Kết quả đã commit vẫn còn sau khi tiến trình ứng dụng khởi động lại |

ACID không tự động bảo đảm mọi quy tắc nghiệp vụ. Ứng dụng vẫn phải thiết kế câu lệnh cập nhật, ràng buộc dữ liệu và mức cô lập phù hợp. Ví dụ, một giao dịch có thể hoàn toàn nguyên tử nhưng vẫn cho phép hai request cùng đặt món hàng cuối cùng nếu câu lệnh kiểm tra tồn kho và câu lệnh trừ kho được thiết kế không an toàn.

## 2. Mô hình giao dịch trong Spring Data R2DBC

R2DBC là API truy cập cơ sở dữ liệu quan hệ theo kiểu reactive. Ứng dụng thường làm việc với `ConnectionFactory`, các repository reactive, `DatabaseClient` hoặc `R2dbcEntityTemplate`. Spring quản lý giao dịch thông qua một `ReactiveTransactionManager`, thường là `R2dbcTransactionManager`.

Khi bắt đầu giao dịch, transaction manager lấy một connection từ `ConnectionFactory`, mở giao dịch trên connection đó và gắn tài nguyên giao dịch vào Reactor Context. Các thao tác R2DBC nằm trong cùng luồng reactive và dùng đúng `ConnectionFactory` sẽ tham gia giao dịch đang hoạt động. Khi publisher hoàn tất thành công, Spring commit; khi publisher kết thúc bằng lỗi, Spring rollback theo quy tắc rollback.

Điểm quan trọng là giao dịch reactive gắn với subscription và Reactor Context, không gắn cố định với một thread. Các toán tử như `publishOn` có thể chuyển việc thực thi giữa các thread mà vẫn truyền Reactor Context theo cơ chế của Reactor. Tuy nhiên, tự tạo một subscription độc lập bằng `subscribe()` sẽ tạo một luồng xử lý riêng và không tự động tham gia giao dịch của luồng gọi.

### 2.1. Cấu hình transaction manager

Nếu ứng dụng cần khai báo transaction manager tường minh, có thể tạo bean như sau:

~~~java
@Configuration
class R2dbcTransactionConfiguration {

    @Bean
    R2dbcTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

Trong một ứng dụng Spring Boot, cấu hình tự động có thể đã cung cấp transaction manager phù hợp. Trước khi khai báo thêm bean, hãy kiểm tra cấu hình thực tế để tránh tạo nhiều transaction manager không cần thiết.

Một `R2dbcTransactionManager` quản lý giao dịch cho một `ConnectionFactory`. Các repository và `DatabaseClient` muốn tham gia cùng giao dịch cần dùng connection factory tương ứng. Nếu một thao tác dùng connection factory khác hoặc tự mở connection ngoài transaction manager, thao tác đó có thể chạy ngoài giao dịch hiện tại.

### 2.2. Giữ mọi thao tác trong cùng reactive chain

Một phương thức nghiệp vụ nên trả về publisher chứa toàn bộ các thao tác cần giao dịch:

~~~java
@Transactional
public Mono<Void> processOrder(Long orderId) {
    return orderRepository.markAsProcessing(orderId)
            .then(inventoryRepository.decreaseForOrder(orderId))
            .then(orderRepository.markAsCompleted(orderId));
}
~~~

Đoạn mã trên chỉ minh họa ranh giới giao dịch; các phương thức repository phải trả về publisher và sử dụng cùng cấu hình R2DBC. Spring có thể quản lý giao dịch vì publisher được trả về cho interceptor `@Transactional`.

Không gọi `subscribe()` bên trong phương thức nghiệp vụ để chạy một thao tác cần giao dịch:

~~~java
@Transactional
public Mono<Void> processOrder(Long orderId) {
    inventoryRepository.decreaseForOrder(orderId).subscribe();
    return orderRepository.markAsCompleted(orderId);
}
~~~

Trong ví dụ sai này, lệnh giảm tồn kho tạo subscription riêng. Phương thức có thể hoàn tất và giao dịch có thể commit trước khi lệnh giảm tồn kho hoàn tất; lệnh đó cũng không được bảo đảm dùng connection của giao dịch hiện tại. Hãy nối các publisher bằng `then`, `flatMap`, `concatMap` hoặc toán tử phù hợp và trả về toàn bộ chuỗi cho Spring.

Tương tự, không dùng `block()` trong luồng reactive để chờ một thao tác R2DBC. Việc chặn thread làm mất lợi ích non-blocking và có thể gây deadlock hoặc cạn thread trong môi trường reactive.

### 2.3. Tránh chạy song song các câu lệnh trên cùng connection

`Mono.zip` hoặc `Mono.when` có thể khởi chạy nhiều publisher đồng thời. Trong một giao dịch R2DBC, các publisher này có thể dùng chung connection. Không phải driver hoặc connection nào cũng hỗ trợ nhiều câu lệnh SQL đang chạy đồng thời trên cùng connection.

Nếu các câu lệnh cần thực hiện tuần tự, hãy dùng `then` hoặc `concatMap`. Chỉ chạy song song khi đã xác nhận driver, connection và ngữ nghĩa giao dịch hỗ trợ cách thực hiện đó. Việc các publisher cùng thuộc một Reactor Context không có nghĩa cơ sở dữ liệu sẽ thực thi các câu lệnh trên cùng connection song song một cách an toàn.

## 3. Ranh giới giao dịch và rollback

### 3.1. Dùng `@Transactional`

Spring hỗ trợ giao dịch reactive cho các phương thức trả về kiểu reactive như `Mono` hoặc `Flux`, khi ứng dụng sử dụng `ReactiveTransactionManager`. Có thể đặt annotation ở phương thức hoặc lớp service:

~~~java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Không tìm thấy đơn hàng")))
            .flatMap(order -> {
                order.setStatus(OrderStatus.CONFIRMED);
                return orderRepository.save(order);
            });
}
~~~

Một số điều kiện cần nhớ:

- Lời gọi phải đi qua Spring proxy để interceptor giao dịch được áp dụng. Tự gọi một phương thức `@Transactional` khác trong cùng instance (self-invocation) thường bỏ qua proxy và không tạo ranh giới giao dịch như mong muốn.
- Phương thức phải trả về publisher reactive để Spring quản lý giao dịch reactive. Không trộn một transaction manager imperative với chuỗi R2DBC reactive.
- Các thao tác cần cùng giao dịch phải nằm trong publisher được trả về, hoặc được gọi trong ngữ cảnh reactive transaction tương ứng.
- Khi có nhiều transaction manager, có thể chỉ rõ manager bằng thuộc tính `transactionManager` hoặc `value` của `@Transactional`.

### 3.2. Rollback khi có lỗi

Với cấu hình mặc định của Spring, lỗi runtime thường làm giao dịch rollback; exception checked không mặc định kích hoạt rollback trong mọi trường hợp. Có thể khai báo rõ quy tắc bằng `rollbackFor` hoặc `noRollbackFor` khi nghiệp vụ cần.

Trong reactive flow, tín hiệu lỗi phải truyền tới ranh giới giao dịch để Spring nhận biết và rollback. Vị trí đặt toán tử xử lý lỗi có thể thay đổi kết quả:

~~~java
// Lỗi đi ra khỏi transaction operator trước khi được xử lý:
return performWrites()
        .as(transactionalOperator::transactional)
        .onErrorResume(error -> returnFallbackResult());
~~~

~~~java
// Lỗi đã bị chuyển thành kết quả thành công bên trong giao dịch:
return performWrites()
        .onErrorResume(error -> returnFallbackResult())
        .as(transactionalOperator::transactional);
~~~

Ở ví dụ thứ hai, nếu `onErrorResume` thay lỗi bằng một publisher hoàn tất bình thường, transaction manager có thể nhìn thấy giao dịch kết thúc thành công và commit các thay đổi trước đó. Nếu nghiệp vụ yêu cầu rollback, hãy để lỗi truyền qua ranh giới giao dịch hoặc chủ động đánh dấu rollback-only bằng API giao dịch phù hợp.

### 3.3. Giao dịch với `Flux`

Khi một phương thức `@Transactional` trả về `Flux`, giao dịch thường tồn tại trong suốt thời gian subscription xử lý publisher. Nếu downstream tiêu thụ dữ liệu chậm, giao dịch và connection có thể bị giữ lâu. Điều này làm tăng thời gian giữ lock, giảm số connection còn lại trong pool và ảnh hưởng đến các request khác.

Không nên giữ một giao dịch cơ sở dữ liệu mở trong một luồng vô hạn hoặc trong lúc chờ người dùng, gọi dịch vụ HTTP chậm hay thực hiện công việc không liên quan. Với xử lý dữ liệu lớn, hãy cân nhắc chia thành các batch có ranh giới giao dịch rõ ràng nếu quy tắc nghiệp vụ cho phép.

### 3.4. Propagation, timeout và read-only

Spring cung cấp các thuộc tính giao dịch thường dùng:

| Thuộc tính | Mục đích |
|---|---|
| `propagation` | Quy định hành vi khi phương thức được gọi trong lúc đã có giao dịch. `REQUIRED` là mặc định: tham gia giao dịch hiện tại hoặc tạo giao dịch mới |
| `isolation` | Chọn mức cô lập cho giao dịch mới |
| `timeout` | Giới hạn thời gian giao dịch theo khả năng hỗ trợ của transaction manager và driver |
| `readOnly` | Đưa ra gợi ý giao dịch chỉ đọc; việc cơ sở dữ liệu có thực thi hạn chế ghi hay không phụ thuộc nền tảng |
| `rollbackFor` / `noRollbackFor` | Tùy chỉnh loại exception làm rollback hoặc không rollback |

`REQUIRES_NEW` yêu cầu một giao dịch mới theo khả năng của transaction manager. Hỗ trợ savepoint hoặc `NESTED` phụ thuộc transaction manager, driver và cơ sở dữ liệu. Không nên giả định mọi kiểu propagation đều có cùng hành vi trên mọi hệ quản trị.

Mức cô lập khai báo trên một phương thức thường chỉ có hiệu lực khi phương thức thực sự bắt đầu giao dịch mới. Nếu phương thức tham gia giao dịch đã tồn tại, cấu hình isolation tại lời gọi bên trong không tự động thay đổi isolation của giao dịch bên ngoài.

## 4. Các hiện tượng khi giao dịch chạy đồng thời

Để chọn isolation level đúng, cần hiểu các bất thường mà giao dịch có thể quan sát.

### 4.1. Dirty read – đọc dữ liệu chưa commit

Giao dịch A cập nhật số dư từ 1.000.000 xuống 500.000 nhưng chưa commit. Giao dịch B đọc được số dư 500.000. Sau đó A rollback. B đã sử dụng một giá trị chưa bao giờ trở thành dữ liệu đã commit.

Dirty read có thể khiến ứng dụng đưa ra quyết định dựa trên dữ liệu tạm thời của giao dịch khác.

### 4.2. Non-repeatable read – đọc lại cùng hàng nhưng nhận giá trị khác

Giao dịch A đọc số dư tài khoản là 1.000.000. Giao dịch B cập nhật số dư thành 800.000 và commit. Khi A đọc lại cùng hàng, A nhận được 800.000.

Hai lần đọc cùng một hàng trong một giao dịch trả về kết quả khác nhau vì giao dịch khác đã commit thay đổi ở giữa.

### 4.3. Phantom read – tập hàng thỏa điều kiện thay đổi

Giao dịch A truy vấn tất cả đơn hàng có trạng thái `PENDING` và nhận được 5 hàng. Giao dịch B thêm một đơn hàng mới có trạng thái `PENDING` rồi commit. Khi A chạy lại cùng điều kiện, kết quả có thể có 6 hàng.

Khác với non-repeatable read, phantom read liên quan đến tập hàng thỏa một điều kiện truy vấn; hàng mới có thể xuất hiện hoặc hàng cũ có thể không còn thỏa điều kiện.

### 4.4. Lost update – cập nhật của một giao dịch bị ghi đè

Giả sử số dư ban đầu là 100:

1. A đọc số dư 100.
2. B cũng đọc số dư 100.
3. A tính 100 + 20 và ghi 120.
4. B tính 100 - 10 và ghi 90.

Kết quả cuối là 90; phần cộng 20 của A đã bị ghi đè. Cả hai giao dịch có thể đã commit thành công nhưng kết quả nghiệp vụ sai.

Lost update thường xuất hiện khi ứng dụng đọc giá trị, tính toán ở tầng ứng dụng rồi ghi lại toàn bộ giá trị cũ đã sửa. Cách khắc phục phù hợp thường là cập nhật nguyên tử trong SQL, optimistic locking hoặc khóa hàng; chỉ tăng isolation level mà không hiểu hành vi của database chưa chắc đã giải quyết đúng vấn đề.

### 4.5. Write skew – các giao dịch cùng giữ điều kiện riêng nhưng phá vỡ quy tắc chung

Giả sử một ca trực phải luôn có ít nhất một bác sĩ đang trực. A và B cùng đọc thấy hai bác sĩ đang trực. A cho bác sĩ thứ nhất nghỉ; B cho bác sĩ thứ hai nghỉ. Mỗi giao dịch chỉ cập nhật một hàng khác nhau nên có thể không xung đột trực tiếp. Nếu cả hai commit, không còn ai trực.

Đây là ví dụ điển hình về write skew trong các hệ thống dùng snapshot isolation. Để bảo vệ quy tắc trên nhiều hàng, có thể cần `SERIALIZABLE`, khóa một hàng đại diện cho quy tắc, hoặc thiết kế lại dữ liệu và ràng buộc để cơ sở dữ liệu kiểm tra được bất biến đó.

## 5. Các mức cô lập phổ biến

SQL định nghĩa bốn mức isolation phổ biến. Mức càng cao thường giảm khả năng quan sát bất thường nhưng có thể làm giảm concurrency, tăng thời gian chờ lock hoặc khiến giao dịch phải thử lại.

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read theo định nghĩa SQL |
|---|---|---|---|
| `READ_UNCOMMITTED` | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra |
| `READ_COMMITTED` | Không | Có thể xảy ra | Có thể xảy ra |
| `REPEATABLE_READ` | Không | Không | Có thể xảy ra |
| `SERIALIZABLE` | Không | Không | Không |

Đây là mô tả theo mô hình SQL. Cách mỗi hệ quản trị hiện thực isolation có thể mạnh hơn hoặc khác về chi tiết. Đặc biệt, snapshot isolation không hoàn toàn đồng nghĩa với mức `SERIALIZABLE`: write skew vẫn có thể xảy ra trong một số hệ thống.

### 5.1. `READ_UNCOMMITTED`

Đây là mức cho phép giao dịch đọc dữ liệu mà giao dịch khác chưa commit. Nó có mức cô lập thấp và thường không phù hợp với nghiệp vụ cần dữ liệu đáng tin cậy.

Một số hệ quản trị không thực sự cung cấp dirty read. Ví dụ, PostgreSQL xử lý yêu cầu `READ UNCOMMITTED` như `READ COMMITTED`. Vì vậy, tên isolation level trong cấu hình không đủ để kết luận hành vi; cần xem tài liệu của database đang chạy.

### 5.2. `READ_COMMITTED`

Một câu lệnh chỉ đọc dữ liệu đã commit tại thời điểm câu lệnh đó bắt đầu. Mức này ngăn dirty read, nhưng hai câu lệnh trong cùng giao dịch vẫn có thể nhìn thấy hai trạng thái đã commit khác nhau.

Đây là lựa chọn mặc định của PostgreSQL. Nó thường phù hợp với nhiều thao tác CRUD thông thường, nhưng ứng dụng vẫn cần bảo vệ lost update và các quy tắc nghiệp vụ nhiều hàng bằng câu lệnh nguyên tử, lock hoặc version.

### 5.3. `REPEATABLE_READ`

Mức này bảo đảm các lần đọc cùng một hàng trong giao dịch có hành vi lặp lại theo định nghĩa của hệ quản trị. Theo bảng bất thường của SQL, phantom read vẫn có thể xảy ra.

Các database hiện thực mức này khác nhau. PostgreSQL sử dụng snapshot ổn định cho giao dịch `REPEATABLE READ` và ngăn phantom read theo cách hiện thực của PostgreSQL. InnoDB của MySQL thường dùng `REPEATABLE READ` làm mặc định và kết hợp consistent read với cơ chế khóa/gap lock cho một số loại truy vấn. Không nên suy rộng hành vi của một database sang database khác.

### 5.4. `SERIALIZABLE`

Đây là mức cô lập mạnh nhất trong bốn mức chuẩn. Kết quả của các giao dịch đã commit phải tương đương với một thứ tự thực thi tuần tự nào đó.

Để đạt điều đó, database có thể khóa nhiều hơn hoặc phát hiện xung đột và từ chối commit một giao dịch. Vì vậy, ứng dụng phải sẵn sàng xử lý lỗi serialization và thử lại toàn bộ giao dịch khi phù hợp. `SERIALIZABLE` hữu ích với các bất biến khó bảo vệ bằng một câu lệnh cập nhật đơn giản, nhưng không nên bật đại trà mà không đo tải và kiểm tra tỷ lệ retry.

### 5.5. Không dựa vào tên isolation level để suy đoán mặc định

Mức mặc định phụ thuộc hệ quản trị, cấu hình server, phiên kết nối và phiên bản. PostgreSQL thường mặc định `READ COMMITTED`; InnoDB của MySQL thường mặc định `REPEATABLE READ`. Cấu hình có thể thay đổi các giá trị này. Hãy kiểm tra database thực tế trong môi trường triển khai và kiểm tra lại sau khi đổi driver hoặc hệ quản trị.

## 6. Cấu hình isolation level trong Spring

### 6.1. Dùng `@Transactional`

Có thể chọn isolation level ngay trên phương thức nghiệp vụ:

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.REPEATABLE_READ)
public Mono<MonthlyReport> buildMonthlyReport() {
    return loadReportData();
}
~~~

Các giá trị của `Isolation` tương ứng với các mức SQL quen thuộc: `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE`.

Annotation chỉ là yêu cầu gửi tới transaction manager. Database và R2DBC driver phải hỗ trợ mức được yêu cầu. Hãy kiểm tra hành vi thật trên hệ quản trị đang dùng, nhất là khi triển khai trên nhiều loại database hoặc khi chạy test bằng database khác production.

### 6.2. Dùng `TransactionalOperator`

Với xử lý cần tạo ranh giới giao dịch ngay trong reactive pipeline, có thể dùng `TransactionalOperator`:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_SERIALIZABLE);
definition.setTimeout(5);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);

return performBusinessOperation()
        .as(operator::transactional);
~~~

`transactionManager` ở đây là một `ReactiveTransactionManager`, chẳng hạn `R2dbcTransactionManager`. `performBusinessOperation()` trả về `Mono` hoặc `Flux`; toán tử bọc publisher đó trong ranh giới giao dịch.

`TransactionalOperator` hữu ích khi một phương thức chỉ có một đoạn cần giao dịch, khi muốn cấu hình giao dịch tại thời điểm xây dựng pipeline, hoặc khi không muốn dựa vào proxy annotation. Vẫn phải bảo đảm mọi thao tác cần giao dịch nằm trong publisher được bọc.

### 6.3. Isolation của giao dịch hiện tại

Giả sử phương thức A mở giao dịch `READ_COMMITTED` rồi gọi phương thức B được khai báo `SERIALIZABLE`. Nếu B tham gia giao dịch hiện tại theo propagation `REQUIRED`, giao dịch không tự đổi thành `SERIALIZABLE`. Isolation level thường được quyết định khi giao dịch vật lý được bắt đầu.

Nếu một đoạn công việc thực sự cần giao dịch riêng, hãy cân nhắc propagation tạo giao dịch mới và hiểu rõ chi phí của nó. Không nên dùng `REQUIRES_NEW` chỉ để ép isolation nếu việc tách commit có thể làm sai tính nguyên tử của nghiệp vụ tổng thể.

## 7. Các cách bảo vệ dữ liệu khi có truy cập đồng thời

Isolation level là một phần của giải pháp. Ứng dụng thường kết hợp nhiều cơ chế dưới đây.

### 7.1. Dùng câu lệnh SQL cập nhật nguyên tử

Thay vì đọc số dư về ứng dụng, trừ một khoản tiền trong Java rồi ghi lại giá trị mới, hãy để database thực hiện phép tính trên giá trị hiện tại:

~~~sql
UPDATE bank_account
SET balance = balance - :amount
WHERE id = :accountId
  AND balance >= :amount;
~~~

Điều kiện `balance >= :amount` được kiểm tra cùng câu lệnh cập nhật. Nếu hai request cùng trừ tiền, database điều phối các cập nhật cạnh tranh trên hàng đó; câu lệnh sau sẽ kiểm tra điều kiện trên trạng thái phù hợp với quy tắc thực thi của database. Nếu số hàng bị ảnh hưởng bằng 0, tài khoản không tồn tại hoặc không đủ số dư.

Cách này thường đơn giản và hiệu quả hơn quy trình đọc-sửa-ghi ở tầng ứng dụng. Có thể bổ sung ràng buộc `CHECK (balance >= 0)` ở database để bảo vệ bất biến số dư ngay cả khi có một đường ghi khác trong ứng dụng.

### 7.2. Dùng optimistic locking với `@Version`

Optimistic locking phù hợp khi xung đột không thường xuyên. Mỗi hàng có một cột version. Khi đọc, ứng dụng lấy cả dữ liệu và version; khi cập nhật, câu lệnh chỉ thành công nếu version trong database vẫn bằng version đã đọc.

Ví dụ entity Spring Data Relational:

~~~java
@Table("inventory")
public class Inventory {

    @Id
    private Long id;

    private Integer quantity;

    @Version
    private Long version;

    // Constructors, getters và setters
}
~~~

Khi lưu một entity có `@Version`, Spring Data R2DBC sử dụng version để phát hiện bản ghi đã bị thay đổi kể từ lúc đọc. Nếu một giao dịch khác đã cập nhật trước, thao tác lưu có thể phát sinh `OptimisticLockingFailureException` thay vì âm thầm ghi đè dữ liệu mới.

Optimistic locking phù hợp với màn hình chỉnh sửa, hồ sơ, cấu hình hoặc dữ liệu có tần suất xung đột thấp. Ứng dụng cần quyết định cách xử lý xung đột: tải lại dữ liệu, yêu cầu người dùng xác nhận, hợp nhất thay đổi hoặc thử lại một thao tác có thể tính toán lại an toàn.

Với câu lệnh SQL tùy chỉnh qua `@Query`, không nên giả định Spring tự thêm điều kiện version như khi lưu entity được quản lý. Nếu dùng custom update, hãy tự đưa version vào điều kiện và tăng version trong câu lệnh:

~~~sql
UPDATE inventory
SET quantity = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu số hàng bị ảnh hưởng bằng 0, version đã thay đổi hoặc bản ghi không còn tồn tại.

### 7.3. Dùng pessimistic locking với `SELECT ... FOR UPDATE`

Pessimistic locking khóa hàng cần xử lý để giao dịch khác phải chờ hoặc nhận lỗi khi cố lấy khóa xung đột. Ví dụ:

~~~sql
SELECT id, balance
FROM bank_account
WHERE id = :accountId
FOR UPDATE;
~~~

Câu lệnh thường phải chạy bên trong giao dịch. Khóa được giữ đến khi giao dịch commit hoặc rollback. Cú pháp chi tiết, các tùy chọn như `NOWAIT` hoặc `SKIP LOCKED`, và loại hàng được khóa phụ thuộc database.

Pessimistic locking hữu ích khi dữ liệu có tranh chấp cao hoặc nghiệp vụ bắt buộc tuần tự hóa thao tác trên một số hàng. Đổi lại, giao dịch khác có thể phải chờ; giao dịch giữ lock càng lâu thì nguy cơ nghẽn và deadlock càng lớn.

Nếu một nghiệp vụ khóa nhiều hàng, hãy lấy khóa theo cùng một thứ tự ổn định, chẳng hạn tăng dần theo ID. Điều này giảm nguy cơ hai giao dịch khóa các hàng theo thứ tự ngược nhau.

### 7.4. Dùng ràng buộc ở database

Các quy tắc có thể diễn đạt bằng constraint nên được bảo vệ ở database:

- `PRIMARY KEY` bảo đảm định danh duy nhất.
- `UNIQUE` bảo đảm giá trị hoặc tổ hợp giá trị không bị trùng.
- `FOREIGN KEY` bảo đảm quan hệ tham chiếu hợp lệ.
- `CHECK` bảo đảm điều kiện trên giá trị của hàng, ví dụ số lượng không âm.
- `NOT NULL` ngăn dữ liệu thiếu ở cột bắt buộc.

Kiểm tra ở tầng Java giúp trả lỗi sớm và tạo thông báo dễ hiểu, nhưng không thay thế constraint. Hai request có thể cùng vượt qua một lần kiểm tra ở ứng dụng; constraint là lớp bảo vệ cuối cùng khi cả hai cùng ghi.

### 7.5. Chọn `SERIALIZABLE` cho bất biến liên quan nhiều hàng

Khi quy tắc nghiệp vụ phụ thuộc vào tập dữ liệu hoặc nhiều hàng mà các cách khóa và cập nhật nguyên tử không đủ rõ ràng, `SERIALIZABLE` có thể là lựa chọn phù hợp. Database sẽ bảo đảm các giao dịch commit có kết quả tương đương một thứ tự tuần tự.

Ứng dụng cần xử lý trường hợp database từ chối một giao dịch do xung đột serialization. Hãy thử lại toàn bộ nghiệp vụ trong một giao dịch mới, không chỉ chạy lại câu lệnh cuối cùng.

## 8. Ví dụ: chuyển tiền bằng Spring Data R2DBC

Ví dụ dưới đây minh họa cách kết hợp transaction boundary với cập nhật nguyên tử. Giả sử bảng `bank_account` có các cột `id` và `balance`.

Repository khai báo các câu lệnh cập nhật:

~~~java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("""
        UPDATE bank_account
        SET balance = balance - :amount
        WHERE id = :id
          AND balance >= :amount
        """)
    Mono<Integer> debit(
            @Param("id") Long id,
            @Param("amount") BigDecimal amount);

    @Modifying
    @Query("""
        UPDATE bank_account
        SET balance = balance + :amount
        WHERE id = :id
        """)
    Mono<Integer> credit(
            @Param("id") Long id,
            @Param("amount") BigDecimal amount);
}
~~~

Service thực hiện hai cập nhật trong cùng giao dịch:

~~~java
@Service
public class TransferService {

    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        if (amount == null || amount.signum() <= 0) {
            return Mono.error(
                    new IllegalArgumentException(
                            "Số tiền phải lớn hơn 0"));
        }

        if (fromId.equals(toId)) {
            return Mono.error(
                    new IllegalArgumentException(
                            "Tài khoản nguồn và đích phải khác nhau"));
        }

        return requireOne(
                    accounts.debit(fromId, amount),
                    "Không thể ghi nợ: tài khoản không tồn tại hoặc không đủ số dư")
                .then(requireOne(
                    accounts.credit(toId, amount),
                    "Không thể ghi có: tài khoản đích không tồn tại"));
    }

    private Mono<Void> requireOne(
            Mono<Integer> update,
            String errorMessage) {
        return update.flatMap(rows -> {
            if (rows == 1) {
                return Mono.<Void>empty();
            }
            return Mono.error(
                    new IllegalStateException(errorMessage));
        });
    }
}
~~~

Luồng xử lý có các đặc điểm:

1. Câu lệnh ghi nợ kiểm tra số dư và cập nhật trong một thao tác SQL.
2. Chỉ khi ghi nợ ảnh hưởng đúng một hàng, publisher mới chạy câu lệnh ghi có.
3. Nếu tài khoản đích không tồn tại, phương thức phát sinh lỗi. Lỗi đi ra khỏi phương thức `@Transactional`, vì vậy thay đổi ghi nợ được rollback cùng giao dịch.
4. Publisher trả về cho Spring, do đó transaction interceptor có thể quản lý toàn bộ chuỗi reactive.

Đây là ví dụ minh họa, cần bổ sung xác thực quyền sở hữu tài khoản, kiểm tra giới hạn giao dịch, tiền tệ, ghi nhận lịch sử và xử lý lỗi theo quy tắc của sản phẩm. Với các chuyển khoản ngược chiều diễn ra đồng thời, database vẫn có thể phát hiện deadlock tùy thứ tự khóa. Có thể khóa hai tài khoản theo thứ tự ID cố định trước khi cập nhật, hoặc xử lý retry có giới hạn cho lỗi deadlock.

## 9. Deadlock và retry

Deadlock xảy ra khi các giao dịch chờ khóa lẫn nhau. Ví dụ:

- Giao dịch A khóa hàng tài khoản 10 rồi chờ hàng tài khoản 20.
- Giao dịch B khóa hàng tài khoản 20 rồi chờ hàng tài khoản 10.

Không giao dịch nào tiếp tục được. Database thường phát hiện deadlock và hủy một giao dịch để giải phóng hệ thống. Ứng dụng cần xem đây là lỗi có thể phục hồi trong một số trường hợp, nhưng không nên retry mọi loại exception.

Các cách giảm deadlock:

- Lấy khóa theo cùng thứ tự ở mọi luồng nghiệp vụ.
- Giữ giao dịch ngắn; không gọi HTTP, gửi email hoặc chờ thao tác người dùng trong khi đang giữ lock.
- Tạo index phù hợp để câu lệnh tìm hàng nhanh và khóa ít hàng hơn.
- Cập nhật đúng phạm vi dữ liệu cần thiết.
- Chỉ retry các lỗi transient đã xác định như deadlock hoặc serialization failure, với số lần giới hạn và backoff.

Ví dụ đặt retry bên ngoài ranh giới giao dịch để mỗi lần thử tạo một giao dịch mới:

~~~java
Mono.defer(() -> performTransfer()
        .as(transactionalOperator::transactional))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(100))
        .filter(this::isRetryableConcurrencyFailure));
~~~

`performTransfer()` phải tạo lại công việc khi được subscribe. Bộ lọc chỉ nên chấp nhận những lỗi có thể thử lại; lỗi dữ liệu đầu vào, thiếu tài khoản hoặc vi phạm quy tắc nghiệp vụ không nên retry.

Retry có thể chạy lại toàn bộ phần thân giao dịch. Vì vậy, không đặt tác động bên ngoài không thể rollback (ví dụ gửi email hoặc gọi cổng thanh toán) vào giữa giao dịch rồi kỳ vọng database rollback sẽ hoàn tác chúng. Với tác động cần phát đi sau commit, có thể dùng transactional outbox: ghi sự kiện vào bảng outbox trong cùng giao dịch, sau đó một tiến trình riêng phát sự kiện và xử lý lặp an toàn.

Đối với API có thể được client gửi lại sau timeout mạng, hãy cân nhắc idempotency key hoặc mã giao dịch duy nhất. Một giao dịch database đã commit nhưng response bị mất có thể khiến client gửi lại yêu cầu; idempotency giúp tránh thực hiện nghiệp vụ hai lần.

## 10. Hiệu năng và vận hành

Isolation cao hơn có thể làm tăng lock contention, số lần giao dịch bị hủy và retry. Hãy chọn mức thấp nhất vẫn bảo vệ được bất biến nghiệp vụ, sau đó đo trên database và tải gần với production.

Một số điểm cần theo dõi:

- Thời gian giao dịch và thời gian giữ connection.
- Số lượng connection đang dùng, đang chờ trong pool và lỗi lấy connection.
- Lock wait, deadlock, serialization failure và optimistic locking failure.
- Tỷ lệ retry, số lần retry trung bình và tỷ lệ nghiệp vụ cuối cùng thất bại.
- Các truy vấn chậm hoặc thiếu index khiến giao dịch giữ khóa lâu.

Không nên giữ giao dịch mở trong lúc thực hiện công việc không thuộc database. Hãy đọc dữ liệu cần thiết, xử lý ngoài transaction nếu an toàn, rồi mở một giao dịch ngắn để xác nhận và ghi các thay đổi cần thiết. Nếu cần bảo đảm dữ liệu chưa đổi kể từ lúc đọc, kết hợp version, điều kiện cập nhật hoặc lock phù hợp.

Khi dùng connection pool, transaction manager quản lý connection được mượn cho giao dịch và trả lại khi giao dịch kết thúc. Giao dịch dài có thể chiếm connection và làm request khác phải chờ dù database vẫn còn khả năng xử lý. Đặt timeout hợp lý và điều chỉnh pool theo tải thực tế; tăng kích thước pool không thay thế việc rút ngắn giao dịch và tối ưu truy vấn.

## 11. Kiểm thử giao dịch và concurrency

Kiểm thử đơn vị với repository giả có thể xác nhận thứ tự gọi publisher, nhưng không chứng minh isolation level, row lock, deadlock hay cách driver thực thi transaction. Các hành vi đó cần integration test trên database thật hoặc môi trường tương thích với database production.

Một bộ kiểm thử hữu ích nên bao gồm:

1. **Rollback:** cho bước thứ hai thất bại và xác nhận thay đổi ở bước thứ nhất không còn trong database.
2. **Atomic update:** gửi nhiều yêu cầu trừ tồn kho hoặc số dư cùng lúc, sau đó xác nhận dữ liệu không vi phạm giới hạn.
3. **Optimistic locking:** hai luồng cùng đọc một version; chỉ một cập nhật được chấp nhận, luồng còn lại nhận lỗi xung đột.
4. **Isolation:** điều phối hai giao dịch để kiểm tra dirty read, non-repeatable read hoặc phantom read theo mức cô lập đang dùng.
5. **Deadlock và retry:** kiểm tra lỗi được nhận diện đúng và lần thử lại dùng giao dịch mới.
6. **Hủy subscription hoặc timeout:** xác nhận connection và transaction được giải phóng theo hành vi của transaction manager và driver.

Có thể dùng Testcontainers để chạy đúng hệ quản trị mục tiêu trong integration test. Nếu production dùng PostgreSQL, kiểm thử concurrency trên H2 không đủ để kết luận hành vi lock và isolation của PostgreSQL. Dùng `StepVerifier` để kiểm tra kết quả publisher, đồng thời truy vấn lại database sau khi các giao dịch hoàn tất để xác nhận trạng thái cuối.

Khi viết test đồng thời, cần điều phối thời điểm đọc và ghi bằng latch, barrier hoặc cơ chế đồng bộ phù hợp. Chỉ khởi chạy hai publisher gần nhau không bảo đảm test đã tạo ra đúng lịch thực thi cần kiểm tra.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `subscribe()` bên trong phương thức `@Transactional` | Tạo subscription độc lập, thao tác có thể chạy ngoài giao dịch | Nối publisher và trả về chuỗi reactive |
| Dùng `block()` trong luồng R2DBC | Chặn thread, có thể làm nghẽn hoặc deadlock | Giữ xử lý non-blocking bằng `flatMap`, `then`, `zip` khi phù hợp |
| Dùng transaction manager hoặc `ConnectionFactory` khác | Một số câu lệnh không tham gia cùng giao dịch | Đồng bộ cấu hình connection factory và transaction manager |
| Bắt lỗi rồi biến thành kết quả thành công bên trong transaction | Giao dịch có thể commit dù một bước nghiệp vụ đã thất bại | Đặt recovery ngoài ranh giới giao dịch hoặc đánh dấu rollback-only |
| Gọi nội bộ một phương thức `@Transactional` qua `this` | Spring proxy có thể không áp dụng annotation | Đặt ranh giới giao dịch ở phương thức được gọi qua bean proxy hoặc dùng `TransactionalOperator` |
| Chạy nhiều câu SQL đồng thời trên một connection | Driver có thể từ chối hoặc không hỗ trợ thực thi đồng thời | Tuần tự hóa thao tác nếu driver không hỗ trợ |
| Dùng isolation cao cho toàn bộ ứng dụng | Tăng chờ khóa và retry không cần thiết | Chọn mức theo bất biến nghiệp vụ và đo tải |
| Chỉ kiểm tra dữ liệu ở Java | Hai request có thể cùng vượt qua kiểm tra trước khi ghi | Dùng atomic SQL và constraint ở database |
| Retry toàn bộ exception | Lặp lại lỗi không thể phục hồi hoặc tác động ngoài database | Chỉ retry lỗi transient đã xác định; bảo đảm thao tác idempotent |
| Kiểm thử trên database khác production | Bỏ sót khác biệt về isolation, lock và SQL | Dùng integration test trên cùng hệ quản trị |

## 13. Quy trình chọn chiến lược giao dịch

Khi thiết kế một thao tác ghi, có thể đi theo trình tự sau:

1. Xác định bất biến nghiệp vụ: số dư không âm, tồn kho không âm, mã đơn hàng duy nhất, hoặc luôn có ít nhất một người trực.
2. Xác định các hàng và bảng mà thao tác đọc hoặc ghi; phân biệt quy tắc trên một hàng với quy tắc trên nhiều hàng.
3. Dùng constraint và câu lệnh cập nhật nguyên tử nếu có thể diễn đạt quy tắc trực tiếp trong database.
4. Dùng optimistic locking khi xung đột ít và có thể xử lý khi version thay đổi.
5. Dùng pessimistic lock khi cần tuần tự hóa thao tác trên hàng cụ thể và có thể giữ giao dịch ngắn.
6. Cân nhắc `SERIALIZABLE` khi bất biến phụ thuộc vào nhiều hàng hoặc tập kết quả và không có cách bảo vệ đơn giản hơn.
7. Kiểm tra hành vi của database/driver, đo thời gian giữ lock và bổ sung retry có giới hạn nếu database có thể từ chối giao dịch do xung đột.
8. Kiểm thử rollback và các tình huống cạnh tranh trên đúng hệ quản trị sẽ triển khai.

## 14. Ghi nhớ

- Transaction xác định ranh giới commit hoặc rollback cho một nhóm thao tác.
- Isolation level quyết định các giao dịch đồng thời có thể quan sát dữ liệu của nhau như thế nào; hành vi thực tế còn phụ thuộc database.
- Trong R2DBC, Spring quản lý giao dịch reactive qua `ReactiveTransactionManager` và Reactor Context.
- Mọi thao tác cần cùng giao dịch phải nằm trong reactive chain được trả về; tránh `subscribe()` và `block()` bên trong luồng nghiệp vụ.
- `READ_COMMITTED` thường đủ cho CRUD thông thường, nhưng lost update và các bất biến nghiệp vụ vẫn cần atomic SQL, constraint, version hoặc lock.
- `@Version`, `SELECT ... FOR UPDATE` và `SERIALIZABLE` giải quyết các dạng xung đột khác nhau; hãy chọn theo đặc điểm dữ liệu và tải.
- Giao dịch ngắn, thứ tự khóa nhất quán, retry có giới hạn và integration test trên database thật giúp hệ thống xử lý concurrency đáng tin cậy hơn.

