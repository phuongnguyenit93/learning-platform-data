# Savepoint, giao dịch lồng nhau và kiểm tra khả năng hỗ trợ

Savepoint là một điểm đánh dấu bên trong transaction đang mở. Ứng dụng có thể quay lui các thao tác được thực hiện sau điểm đánh dấu mà vẫn giữ transaction bên ngoài hoạt động. Spring biểu diễn ý tưởng này qua propagation PROPAGATION_NESTED khi transaction manager và R2DBC driver hỗ trợ savepoint.

Giao dịch lồng nhau không giống transaction độc lập. Với NESTED, phần công việc bên trong thường dùng cùng transaction vật lý và một savepoint; nếu phần bên trong rollback về savepoint, phần bên ngoài vẫn có thể tiếp tục. Nhưng khi transaction bên ngoài rollback, mọi thay đổi đã thực hiện trong phần lồng nhau cũng rollback. Với REQUIRES_NEW, Spring tạm ngưng transaction bên ngoài và mở transaction vật lý khác; transaction mới có thể commit độc lập.

Trong Spring Data Relational R2DBC, khả năng này phụ thuộc cả Spring transaction manager, R2DBC driver và database. Không nên chỉ thấy annotation @Transactional(propagation = NESTED) biên dịch được rồi kết luận savepoint đã hoạt động. Cần xác minh bằng integration test trên đúng driver và phiên bản database triển khai.

## 1. Savepoint là gì?

Một transaction thông thường gom nhiều thao tác ghi thành một đơn vị nguyên tử: hoặc commit toàn bộ, hoặc rollback toàn bộ. Savepoint tạo ra một mốc bên trong đơn vị đó.

Ví dụ, xử lý một đơn hàng gồm ba bước:

1. Lưu đơn hàng.
2. Thử áp dụng một phần tùy chọn như voucher hoặc thông tin quà tặng.
3. Lưu các dòng hàng và hoàn tất đơn.

Nếu bước tùy chọn thất bại nhưng nghiệp vụ vẫn cho phép tạo đơn, có thể rollback riêng bước đó rồi tiếp tục các bước còn lại. Savepoint phù hợp với tình huống này khi tất cả thao tác vẫn phải thuộc cùng transaction ngoài.

Mô hình:

~~~mermaid
flowchart TD
    A[Begin outer transaction] --> B[Save order]
    B --> C[Create savepoint]
    C --> D[Run optional operation]
    D --> E{Operation succeeds?}
    E -->|Yes| F[Release savepoint]
    E -->|No| G[Rollback to savepoint]
    G --> H[Handle optional failure]
    F --> I[Continue outer work]
    H --> I
    I --> J{Outer transaction succeeds?}
    J -->|Yes| K[Commit all remaining changes]
    J -->|No| L[Rollback entire transaction]
~~~

Nếu rollback về savepoint thành công, các thay đổi sau savepoint bị hủy. Những thay đổi trước savepoint vẫn nằm trong transaction ngoài. Chúng chưa được commit; transaction ngoài vẫn quyết định kết quả cuối cùng.

## 2. Các thao tác savepoint ở mức database

R2DBC SPI cung cấp các thao tác savepoint trên Connection:

- createSavepoint(name): tạo điểm đánh dấu trong transaction hiện tại.
- rollbackTransactionToSavepoint(name): quay lui transaction về điểm đánh dấu.
- releaseSavepoint(name): giải phóng điểm đánh dấu khi không cần dùng nữa.

Ở mức SQL, nhiều database có cú pháp tương tự:

~~~sql
BEGIN;

INSERT INTO orders (id, status)
VALUES (1001, 'NEW');

SAVEPOINT optional_step;

INSERT INTO order_notes (order_id, note)
VALUES (1001, 'Optional note');

ROLLBACK TO SAVEPOINT optional_step;

INSERT INTO order_lines (order_id, product_id, quantity)
VALUES (1001, 501, 2);

COMMIT;
~~~

Kết quả mong đợi là đơn hàng và dòng hàng được giữ lại, còn ghi chú tùy chọn bị hủy. Tên câu lệnh, chi tiết release và một số giới hạn có thể khác giữa hệ quản trị. Đoạn SQL trên minh họa semantics, không phải script portable để chạy nguyên văn trên mọi database.

Savepoint chỉ có ý nghĩa bên trong transaction đang hoạt động. Không thể dùng savepoint để commit một phần transaction thành công độc lập. RELEASE SAVEPOINT cũng không commit dữ liệu; nó chỉ bỏ mốc savepoint.

### Phạm vi rollback

Giả sử transaction có các thao tác:

~~~text
A: insert order
SAVEPOINT S1
B: insert optional detail
SAVEPOINT S2
C: update inventory
ROLLBACK TO S2
D: insert order line
COMMIT
~~~

Sau ROLLBACK TO S2, thao tác C bị hủy; thao tác A và B vẫn thuộc transaction. Thao tác D được thực hiện sau khi rollback về S2. Khi commit transaction ngoài, A, B và D được commit.

Nếu sau đó transaction ngoài rollback, A, B và D đều bị hủy. Savepoint không tạo một transaction con có khả năng commit độc lập.

## 3. Phân biệt REQUIRED, NESTED và REQUIRES_NEW

Ba propagation này thường bị nhầm lẫn vì đều có thể được dùng khi một service gọi một service khác.

| Propagation | Khi đã có transaction | Khả năng rollback riêng | Có thể commit độc lập? |
| --- | --- | --- | --- |
| REQUIRED | Tham gia transaction hiện tại. | Không có savepoint riêng theo mặc định. | Không. |
| NESTED | Tạo savepoint trong transaction hiện tại nếu manager/driver hỗ trợ. | Có thể rollback về savepoint. | Không. |
| REQUIRES_NEW | Tạm ngưng transaction hiện tại và mở transaction mới. | Transaction mới rollback độc lập. | Có, nếu transaction mới commit thành công. |

### REQUIRED: cùng một transaction

Nếu phương thức ngoài và phương thức trong đều dùng REQUIRED, cả hai tham gia cùng transaction vật lý.

Nếu phương thức trong phát lỗi thuộc rollback rule, transaction có thể bị đánh dấu rollback-only. Nếu phương thức ngoài bắt lỗi rồi tiếp tục, đến lúc commit có thể nhận UnexpectedRollbackException vì transaction đã bị đánh dấu rollback-only.

Không có savepoint tự động để chỉ hủy phần công việc của phương thức trong.

### NESTED: cùng transaction, có savepoint

Nếu đã có transaction, NESTED yêu cầu transaction manager tạo savepoint. Khi scope lồng nhau rollback, manager quay lui về savepoint và transaction ngoài có thể tiếp tục nếu lỗi được xử lý phù hợp.

Nếu chưa có transaction hiện tại, lời gọi NESTED thường phải bắt đầu một transaction mới; không có transaction ngoài để tạo savepoint bên trong.

Thành công của scope lồng nhau chỉ có nghĩa phần công việc của nó được giữ trong transaction ngoài. Nó vẫn có thể bị hủy khi transaction ngoài rollback.

### REQUIRES_NEW: transaction vật lý riêng

REQUIRES_NEW tạm ngưng transaction hiện tại và bắt đầu transaction độc lập. Transaction mới có thể commit dù transaction ngoài sau đó rollback.

Cách này cần tài nguyên connection riêng trong lúc connection của transaction ngoài vẫn có thể đang được giữ. Connection pool phải đủ dung lượng cho số transaction lồng đồng thời. Nếu pool quá nhỏ, lời gọi có thể chờ connection và timeout.

### Ví dụ so sánh kết quả

Giả sử bước ngoài lưu đơn hàng A, bước trong lưu dữ liệu phụ B, sau đó bước ngoài phát lỗi:

| Cơ chế cho bước trong | Khi bước trong thành công, bước ngoài thất bại | Kết quả cuối |
| --- | --- | --- |
| REQUIRED | B cùng transaction với A. | A và B rollback. |
| NESTED | B nằm sau savepoint trong transaction ngoài. | A và B rollback cùng transaction ngoài. |
| REQUIRES_NEW | B được commit trong transaction riêng. | A rollback, B vẫn tồn tại. |

Nếu bước trong thất bại nhưng bước ngoài bắt lỗi và tiếp tục:

- REQUIRED: transaction ngoài có thể đã bị đánh dấu rollback-only; việc bắt lỗi không tự khôi phục transaction.
- NESTED: scope trong có thể rollback về savepoint, sau đó transaction ngoài tiếp tục.
- REQUIRES_NEW: transaction trong rollback độc lập; transaction ngoài vẫn có thể tiếp tục.

Đây là lý do NESTED hữu ích cho phần việc có thể thất bại độc lập về mặt thao tác nhưng vẫn phải commit cùng đơn vị nghiệp vụ ngoài.

## 4. Spring R2dbcTransactionManager và hỗ trợ savepoint

R2dbcTransactionManager là reactive transaction manager dành cho một ConnectionFactory. Spring Data R2DBC sử dụng transaction manager này để điều phối connection và transaction context cho repository, DatabaseClient và R2dbcEntityTemplate.

Spring Framework có hỗ trợ nested transaction dựa trên R2DBC savepoint, nhưng việc sử dụng thành công phụ thuộc phiên bản framework, transaction manager thực tế và khả năng của driver/database. Driver phải triển khai các thao tác savepoint cần thiết. Một số driver hoặc cấu hình có thể từ chối thao tác này.

Khi cấu hình, cần phân biệt:

- Có ReactiveTransactionManager chưa chắc đã có savepoint.
- Có R2DBC driver chưa chắc mọi thao tác savepoint đều được hỗ trợ.
- Database có cú pháp savepoint chưa chắc phiên bản driver đang dùng đã expose đầy đủ API đó.
- PROPAGATION_NESTED không phải cơ chế tạo một connection độc lập.
- Dùng nhiều ConnectionFactory không tạo thành một distributed transaction.

Ví dụ cấu hình manager:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

Không cần tạo transaction manager riêng chỉ để dùng savepoint nếu manager hiện tại đã được cấu hình và hỗ trợ nested transaction. Nếu ứng dụng có nhiều ConnectionFactory, hãy chọn manager tương ứng cho service và không giả định savepoint có thể trải qua nhiều database.

## 5. Dùng @Transactional(propagation = NESTED)

Cách khai báo đơn giản nhất là đặt NESTED trên một phương thức public của bean khác. Lời gọi từ service ngoài phải đi qua Spring proxy.

Ví dụ service thực hiện phần tùy chọn:

~~~java
@Service
public class OptionalOrderStepService {

    private final OrderNoteRepository notes;

    public OptionalOrderStepService(OrderNoteRepository notes) {
        this.notes = notes;
    }

    @Transactional(propagation = Propagation.NESTED)
    public Mono<Void> addOptionalNote(
            Long orderId,
            String note) {
        return notes.save(new OrderNote(orderId, note))
            .then();
    }
}
~~~

Service điều phối:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final OrderLineRepository lines;
    private final OptionalOrderStepService optionalStep;

    public OrderService(
            OrderRepository orders,
            OrderLineRepository lines,
            OptionalOrderStepService optionalStep) {
        this.orders = orders;
        this.lines = lines;
        this.optionalStep = optionalStep;
    }

    @Transactional
    public Mono<Order> createOrder(CheckoutCommand command) {
        return orders.save(Order.from(command))
            .flatMap(order ->
                optionalStep.addOptionalNote(
                    order.id(),
                    command.optionalNote()
                )
                .onErrorResume(OptionalStepException.class, error ->
                    Mono.empty()
                )
                .then(lines.saveAll(
                    OrderLine.from(order.id(), command.items())
                ).then(Mono.just(order)))
            );
    }
}
~~~

Khi optionalStep.addOptionalNote được gọi qua proxy, Spring áp dụng NESTED. Nếu thao tác ghi note phát lỗi thuộc rollback rule, nested scope được rollback về savepoint. Sau khi lỗi thoát khỏi nested transactional publisher, onErrorResume ở caller có thể xử lý lỗi và tiếp tục lưu dòng hàng trong transaction ngoài.

Ví dụ giả định exception được phân loại là lỗi tùy chọn và không phải lỗi nghiêm trọng khiến database transaction ngoài không còn sử dụng được. Nếu driver hoặc database đánh dấu toàn bộ transaction ở trạng thái failed sau lỗi, khả năng tiếp tục còn phụ thuộc semantics của hệ quản trị và việc rollback về savepoint có thành công hay không.

### Vì sao phải bắt lỗi bên ngoài nested boundary?

Hãy đặt error recovery sau lời gọi đã được bọc transaction:

~~~java
optionalStep.addOptionalNote(orderId, note)
    .onErrorResume(OptionalStepException.class, error -> Mono.empty());
~~~

onErrorResume ở downstream nhận lỗi sau khi transactional interceptor của phương thức nested đã xử lý rollback/cleanup. Nếu nuốt lỗi bên trong phương thức trước khi transaction boundary nhìn thấy nó, transaction manager có thể nhận completion bình thường và không rollback nested scope như mong muốn.

Nếu lỗi không thuộc loại có thể bỏ qua, hãy để lỗi tiếp tục truyền ra ngoài để transaction ngoài rollback theo chính sách.

### Không tự gọi phương thức NESTED trong cùng bean

Ví dụ sau không tạo savepoint qua proxy:

~~~java
@Service
public class OrderService {

    @Transactional
    public Mono<Order> createOrder(CheckoutCommand command) {
        return saveOptionalPart(command)
            .then(orders.save(Order.from(command)));
    }

    @Transactional(propagation = Propagation.NESTED)
    public Mono<Void> saveOptionalPart(CheckoutCommand command) {
        return notes.save(OrderNote.from(command)).then();
    }
}
~~~

Lời gọi saveOptionalPart là self-invocation. Annotation NESTED không được proxy áp dụng, do đó không có savepoint mới được tạo bởi lời gọi đó. Hãy tách bước nested sang bean khác hoặc dùng TransactionalOperator với propagation NESTED.

## 6. Dùng TransactionalOperator với propagation NESTED

Nếu muốn biểu diễn ranh giới lồng nhau ngay trong reactive chain, có thể tạo một TransactionalOperator dùng transaction definition với propagation NESTED.

~~~java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

DefaultTransactionDefinition nestedDefinition =
    new DefaultTransactionDefinition();

nestedDefinition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_NESTED
);

TransactionalOperator nestedOperator =
    TransactionalOperator.create(
        transactionManager,
        nestedDefinition
    );
~~~

Sau đó bọc riêng publisher cần savepoint:

~~~java
Mono<Void> optionalStep =
    nestedOperator.transactional(
        notes.save(OrderNote.from(orderId, note)).then()
    );

return outerOperator.transactional(
    orders.save(order)
        .flatMap(saved ->
            optionalStep
                .onErrorResume(OptionalStepException.class, error ->
                    Mono.empty()
                )
                .then(lines.saveAll(
                    OrderLine.from(saved.id(), items)
                ).thenReturn(saved))
        )
);
~~~

Ở đây:

- outerOperator dùng transaction definition mặc định hoặc REQUIRED.
- nestedOperator dùng PROPAGATION_NESTED.
- optionalStep được subscribe trong transaction context của publisher ngoài.
- Nếu có transaction ngoài, nested operator yêu cầu savepoint.
- Nếu nested step lỗi, transactional operator xử lý rollback về savepoint trước khi downstream recovery tiếp tục.

Đừng subscribe riêng optionalStep trước khi bọc transaction ngoài. Cần giữ publisher trong cùng composition để nested operator nhìn thấy transaction context đang tồn tại.

Nếu nestedOperator được gọi khi không có transaction ngoài, manager có thể mở transaction mới cho publisher đó. Khi đó đây không phải savepoint lồng trong một transaction khác. Nếu nghiệp vụ yêu cầu savepoint cụ thể, hãy bảo đảm outer transaction đã bắt đầu trước khi nested publisher được thực thi.

## 7. Điều gì xảy ra khi nested scope thất bại?

Kết quả phụ thuộc vào nơi xử lý lỗi và loại lỗi.

### Nested scope lỗi, caller xử lý và tiếp tục

Luồng mong muốn:

1. Transaction ngoài bắt đầu.
2. Ghi dữ liệu chính.
3. Tạo savepoint.
4. Nested scope thực hiện ghi dữ liệu phụ.
5. Nested scope phát lỗi.
6. Transaction manager rollback về savepoint.
7. Caller nhận lỗi và xử lý bằng onErrorResume.
8. Transaction ngoài tiếp tục thực hiện phần còn lại.
9. Transaction ngoài commit.

Kết quả là dữ liệu chính và phần còn lại được commit, phần nested bị rollback.

### Nested scope lỗi và caller không xử lý

Nếu lỗi tiếp tục thoát khỏi transaction ngoài, transaction ngoài rollback. Khi đó cả dữ liệu trước savepoint và sau savepoint đều bị hủy.

### Rollback về savepoint thất bại

Nếu driver/database không hỗ trợ savepoint hoặc thao tác rollback-to-savepoint thất bại, transaction manager không thể bảo đảm phần công việc bên ngoài tiếp tục an toàn. Lỗi rollback có thể thay thế hoặc bổ sung lỗi ban đầu. Cần để transaction ngoài kết thúc theo đường lỗi và kiểm tra trạng thái database.

Không nên bắt mọi exception rồi tiếp tục. Chỉ phục hồi những lỗi mà nghiệp vụ xác định là có thể bỏ qua và transaction manager đã hoàn thành rollback nested scope thành công.

## 8. Savepoint không thay thế transaction boundary

Savepoint chỉ tạo điểm quay lui bên trong transaction. Nó không:

- Commit một phần dữ liệu.
- Tạo connection mới.
- Tách biệt lock hoặc isolation như một transaction độc lập.
- Bảo đảm dữ liệu nested tồn tại nếu transaction ngoài rollback.
- Tự khôi phục transaction nếu database đã đánh dấu transaction ngoài không thể tiếp tục.
- Thay thế cơ chế bù trừ giữa các dịch vụ hoặc database.

Nếu cần một thao tác commit độc lập, hãy cân nhắc REQUIRES_NEW. Nếu cần hai database commit nguyên tử cùng nhau, một R2dbcTransactionManager thông thường không cung cấp distributed transaction. Hãy xem xét outbox, saga hoặc quy trình bù trừ theo kiến trúc.

## 9. Khả năng hỗ trợ của database và driver

Hỗ trợ savepoint là thuộc tính của cả stack:

~~~text
Spring Framework / Spring Data R2DBC
            |
ReactiveTransactionManager
            |
R2DBC SPI
            |
R2DBC driver
            |
Database server and version
~~~

Một mắt xích không hỗ trợ sẽ khiến nested transaction không hoạt động như mong đợi.

### Các câu hỏi cần xác minh

| Thành phần | Cần kiểm tra |
| --- | --- |
| Spring Framework | Phiên bản có hỗ trợ nested transaction cho reactive manager đang dùng không? |
| Transaction manager | Đúng là R2dbcTransactionManager hay custom manager? Có cho phép nested transaction không? |
| R2DBC SPI | Driver triển khai createSavepoint, rollbackTransactionToSavepoint và releaseSavepoint như thế nào? |
| Driver | Phiên bản cụ thể có bug hoặc giới hạn savepoint nào đã biết? |
| Database | Phiên bản server hỗ trợ savepoint trong transaction loại đang dùng không? |
| Transaction state | Sau lỗi statement, rollback về savepoint có đưa transaction về trạng thái tiếp tục được không? |
| Connection pool | Có đủ connection cho các luồng REQUIRES_NEW riêng biệt không? |

Không nên kiểm tra hỗ trợ bằng cách chỉ đọc tên database. Các phiên bản driver khác nhau có thể expose khả năng khác nhau dù cùng kết nối một loại server.

### Kiểm tra bằng tài liệu và runtime

Thực hiện theo các bước:

1. Xác định phiên bản Spring Framework và Spring Data R2DBC trong dependency tree.
2. Xác định chính xác R2DBC driver và phiên bản đang chạy.
3. Đọc tài liệu driver về savepoint và các giới hạn.
4. Đối chiếu database server version và semantics savepoint.
5. Viết integration test thực hiện create, rollback-to và release savepoint trong transaction thật.
6. Kiểm tra nested rollback rồi tiếp tục thao tác và commit transaction ngoài.
7. Kiểm tra outer rollback sau khi nested scope thành công.
8. Kiểm tra hành vi khi nested scope bị cancel hoặc lỗi trong lúc rollback.

Nếu driver không hỗ trợ, đừng giả định Spring có thể tự mô phỏng savepoint bằng nhiều connection. Hãy chọn cách xử lý nghiệp vụ khác hoặc giới hạn database/driver được hỗ trợ.

## 10. Integration test xác nhận savepoint

Một kiểm thử thực tế cần chứng minh rollback về savepoint chỉ hủy phần nested, trong khi transaction ngoài vẫn commit được.

Giả sử có bảng orders và order_notes, với repository tương ứng. Test service thực hiện:

~~~java
@Transactional
public Mono<Long> saveOrderWithOptionalNote() {
    return orders.save(new Order(null, "NEW"))
        .flatMap(order ->
            optionalNoteService.addNote(order.id())
                .onErrorResume(OptionalStepException.class, error ->
                    Mono.empty()
                )
                .thenReturn(order.id())
        );
}
~~~

Nested service:

~~~java
@Transactional(propagation = Propagation.NESTED)
public Mono<Void> addNote(Long orderId) {
    return notes.save(new OrderNote(orderId, "optional"))
        .then(Mono.error(new OptionalStepException()));
}
~~~

Test:

~~~java
@Test
void rollsBackNestedWorkAndCommitsOuterTransaction() {
    StepVerifier.create(orderService.saveOrderWithOptionalNote())
        .assertNext(orderId -> {
            StepVerifier.create(orders.findById(orderId))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(notes.findByOrderId(orderId))
                .verifyComplete();
        })
        .verifyComplete();
}
~~~

Ví dụ phác thảo ý tưởng kiểm thử; không nên subscribe lồng bên trong assertNext trong test thực tế. Hãy viết test theo chuỗi reactive tuần tự để mọi assertion hoàn tất trước khi test kết thúc:

~~~java
@Test
void nestedRollbackKeepsOuterOrder() {
    StepVerifier.create(
        orderService.saveOrderWithOptionalNote()
            .flatMap(orderId ->
                orders.findById(orderId)
                    .switchIfEmpty(Mono.error(
                        new AssertionError("Outer order was not committed")
                    ))
                    .flatMap(order ->
                        notes.findByOrderId(orderId)
                            .hasElements()
                            .flatMap(hasNote -> {
                                assertFalse(hasNote);
                                return Mono.just(order.id());
                            })
                    )
            )
    )
    .expectNextMatches(Objects::nonNull)
    .verifyComplete();
}
~~~

Test phải gọi service qua bean Spring được inject để proxy transaction hoạt động. Không tự tạo instance bằng new OrderService(...) rồi kỳ vọng annotation được áp dụng.

### Kiểm thử outer rollback

Một test bổ sung xác nhận nested success vẫn phụ thuộc transaction ngoài:

1. Outer transaction lưu order.
2. Nested scope lưu note và hoàn tất.
3. Outer publisher phát lỗi sau nested scope.
4. Sau khi kết thúc, kiểm tra cả order và note đều không tồn tại.

Điều này chứng minh savepoint không commit độc lập.

### Kiểm thử REQUIRES_NEW để đối chiếu

Nếu muốn chứng minh khác biệt với transaction độc lập:

1. Outer transaction bắt đầu.
2. Một bean khác được gọi qua proxy với REQUIRES_NEW.
3. Transaction mới ghi dữ liệu và commit.
4. Outer transaction phát lỗi và rollback.
5. Dữ liệu của transaction mới vẫn tồn tại.

Test này cần connection pool đủ để cấp connection cho transaction mới trong khi transaction ngoài đang bị suspend.

## 11. Kiểm thử trực tiếp R2DBC driver

Ngoài test qua Spring transaction manager, có thể viết một integration test ở mức driver để xác minh API savepoint. Ý tưởng:

~~~java
Mono.usingWhen(
    connectionFactory.create(),
    connection ->
        connection.beginTransaction()
            .then(connection.createSavepoint("sp_optional"))
            .then(runOptionalStatement(connection))
            .then(connection.rollbackTransactionToSavepoint("sp_optional"))
            .then(connection.releaseSavepoint("sp_optional"))
            .then(connection.commitTransaction()),
    connection -> connection.close()
);
~~~

Đây chỉ là phác thảo thứ tự thao tác. Test thực tế cần xử lý rollback khi lỗi, đóng connection an toàn và dùng đúng kiểu Publisher mà driver trả về. Không chạy đoạn này song song với thao tác khác trên cùng connection.

Khi transaction manager của Spring đang quản lý connection, tránh tự lấy connection mới hoặc tự commit/rollback thủ công. Hãy để manager sở hữu vòng đời transaction. Test ở mức SPI nên tách riêng khỏi test qua @Transactional để không xung đột quyền sở hữu connection.

## 12. Các giới hạn và khác biệt theo hệ quản trị

Savepoint được hỗ trợ rộng rãi ở nhiều hệ quản trị quan hệ, nhưng vẫn có các giới hạn cần lưu ý:

- Một số lệnh DDL có thể implicit commit hoặc có semantics savepoint riêng.
- Một số loại thao tác không thể rollback theo cách người dùng kỳ vọng.
- Khi statement lỗi, database có thể đánh dấu transaction cần rollback đến savepoint trước khi tiếp tục.
- Tên savepoint và cách lồng savepoint có thể có giới hạn.
- Release savepoint có thể không bắt buộc về mặt semantics ở một số hệ, nhưng API/driver vẫn cần xử lý theo hợp đồng.
- Một số database không hỗ trợ savepoint trong mọi loại transaction hoặc storage engine.
- Lock được lấy sau savepoint có thể được giải phóng khi rollback về savepoint tùy hệ quản trị.

Vì vậy, không suy rộng hành vi từ một database sang database khác. Đọc tài liệu của đúng server version và kiểm thử trên cấu hình triển khai.

### Savepoint và DDL

Không nên dùng nested transaction như một cách bảo đảm DDL có thể rollback trên mọi database. Migration thường được quản lý bởi công cụ chuyên dụng và có semantics transaction riêng. Một số hệ quản trị tự commit trước/sau một số câu lệnh DDL hoặc giới hạn lệnh được phép trong transaction.

Nếu phần việc nested có thay đổi schema, hãy kiểm tra riêng hành vi DDL. Với nghiệp vụ ứng dụng, savepoint thường phù hợp hơn cho các thao tác DML như INSERT, UPDATE và DELETE.

## 13. Connection pool và nested transaction

NESTED dùng savepoint trên transaction hiện tại, nên thường không cần một connection vật lý mới. REQUIRES_NEW cần transaction riêng và có thể cần connection khác trong khi transaction ngoài bị suspend.

Sự khác biệt này ảnh hưởng đến pool:

| Cơ chế | Connection | Tác động pool |
| --- | --- | --- |
| REQUIRED | Dùng connection transaction hiện tại. | Không cần connection bổ sung cho scope tham gia. |
| NESTED | Dùng connection hiện tại và savepoint. | Thường không cần connection bổ sung. |
| REQUIRES_NEW | Mở transaction riêng trong khi transaction ngoài bị suspend. | Cần khả năng cấp thêm connection. |

Nếu nhiều request đồng thời đều giữ connection ngoài rồi chờ connection cho REQUIRES_NEW, pool có thể cạn. Hãy đo concurrency và cấu hình pool phù hợp; tránh lồng nhiều tầng transaction mới mà không có giới hạn.

Không chạy nhiều câu SQL song song trên cùng transaction connection trừ khi driver/database hỗ trợ rõ ràng. Với reactive chain, dùng concatMap, then hoặc flatMap với concurrency phù hợp khi các lệnh phải tuần tự. Savepoint là trạng thái của một transaction connection; việc đan xen nhiều luồng command trên cùng connection có thể làm thứ tự thao tác khó dự đoán.

## 14. Hủy subscription và lỗi trong reactive transaction

Reactive transaction phụ thuộc vòng đời subscription. Nếu subscriber cancel trước khi publisher hoàn tất, transaction manager cần thực hiện cleanup và rollback theo cơ chế reactive transaction của Spring.

Với savepoint, cancellation trong lúc nested scope đang chạy là tình huống cần kiểm tra: nested scope có được rollback đúng không, transaction ngoài có còn sử dụng được không, và connection có được trả về pool sau cleanup không.

Các tình huống nên kiểm tra:

- Cancel trước khi nested publisher bắt đầu.
- Cancel sau khi savepoint được tạo nhưng trước khi statement hoàn tất.
- Statement phát lỗi và rollback-to-savepoint thành công.
- Rollback-to-savepoint tự phát lỗi.
- Outer publisher bị cancel sau khi nested scope thành công.
- Driver timeout hoặc connection bị đóng giữa thao tác savepoint.

Không bắt cancellation rồi biến nó thành completion bình thường chỉ để giữ transaction. Hãy để transaction infrastructure hoàn tất cleanup và xác nhận hành vi bằng integration test với driver thực tế.

## 15. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| PROPAGATION_NESTED báo không hỗ trợ | Transaction manager/driver không hỗ trợ savepoint hoặc cấu hình không cho phép nested. | Kiểm tra Spring version, manager và driver; chạy integration test. |
| Nested annotation không tạo savepoint | Phương thức bị self-invocation nên proxy không intercept. | Tách bean hoặc dùng TransactionalOperator với NESTED. |
| Nghĩ nested commit độc lập | Nhầm savepoint với transaction mới. | Nhớ outer rollback vẫn hủy thay đổi nested. |
| Bắt lỗi nhưng outer transaction vẫn rollback | Transaction đã bị đánh dấu rollback-only hoặc database không phục hồi sau lỗi. | Kiểm tra lỗi, savepoint rollback và transaction state trước khi tiếp tục. |
| Dùng REQUIRES_NEW khi muốn rollback một phần | Chọn transaction vật lý độc lập thay vì savepoint. | Dùng NESTED nếu semantics savepoint phù hợp và được hỗ trợ. |
| Pool cạn khi dùng REQUIRES_NEW | Outer transaction giữ connection trong lúc inner cần connection khác. | Tính pool theo concurrency và tránh lồng không cần thiết. |
| Tự phát SQL SAVEPOINT trong transaction do Spring quản lý | Can thiệp thủ công vào connection state do manager sở hữu. | Dùng propagation NESTED hoặc API savepoint được quản lý phù hợp. |
| Kiểm thử chỉ bằng mock | Không xác nhận được driver và database hỗ trợ savepoint. | Dùng integration test trên đúng R2DBC driver/database. |
| Cho rằng DDL luôn rollback về savepoint | Semantics DDL khác nhau giữa database. | Kiểm tra riêng tài liệu và test DDL; dùng migration tool. |

## 16. Quy trình quyết định có nên dùng savepoint

Khi thiết kế một bước có thể thất bại trong transaction lớn, hãy trả lời lần lượt:

1. Phần việc bên trong có cần commit độc lập không?
2. Nếu outer transaction rollback, dữ liệu bên trong có phải rollback theo không?
3. Nếu phần bên trong lỗi, phần ngoài có được phép tiếp tục không?
4. REQUIRED có đủ không, hay cần rollback riêng một phần?
5. Driver và database mục tiêu có hỗ trợ savepoint không?
6. Spring transaction manager đang dùng có hỗ trợ PROPAGATION_NESTED ở phiên bản hiện tại không?
7. Lỗi nested có thể được phục hồi sau rollback-to-savepoint không?
8. Có cần một bean riêng để lời gọi đi qua proxy không?
9. Có rủi ro connection pool hoặc transaction concurrency không?
10. Integration test đã xác nhận cả nested rollback và outer rollback chưa?

Chọn theo semantics:

- Dùng REQUIRED nếu mọi thao tác phải cùng thành công hoặc cùng rollback.
- Dùng NESTED nếu phần bên trong có thể rollback về savepoint, còn transaction ngoài tiếp tục; toàn bộ vẫn commit/rollback cùng nhau.
- Dùng REQUIRES_NEW nếu phần bên trong phải có kết quả commit độc lập.
- Dùng outbox/saga hoặc quy trình bù trừ nếu công việc trải qua nhiều database hoặc dịch vụ.

Savepoint giúp transaction có thể phục hồi từ một bước thất bại mà không hủy ngay toàn bộ công việc. Trong Spring Data Relational R2DBC, hãy dùng PROPAGATION_NESTED hoặc TransactionalOperator với transaction definition tương ứng khi transaction manager và driver hỗ trợ. Luôn phân biệt savepoint với transaction độc lập, giữ lỗi trong đúng ranh giới reactive, và xác nhận hành vi bằng integration test trên đúng database/driver trước khi phụ thuộc vào nó trong nghiệp vụ.
