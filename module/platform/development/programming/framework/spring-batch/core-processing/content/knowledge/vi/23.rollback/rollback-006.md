# Chính sách rollback cho step có classifier

Trong Spring Batch, một fault-tolerant chunk step có thể phân loại exception theo nhiều mục đích: exception nào được retry, exception nào được skip và exception nào làm transaction rollback. Những quyết định này có liên quan nhưng không giống nhau. Một exception được phép skip không tự động có nghĩa transaction không rollback; một exception không làm rollback cũng không tự động được retry hoặc skip.

Chính sách rollback quyết định transaction hiện tại có phải hoàn tác các thay đổi chưa commit khi exception xuất hiện hay không. Trong cấu hình fault-tolerant step, API builder thường dùng để khai báo ngoại lệ không cần rollback là noRollback. Spring Batch dùng quy tắc phân loại rollback trong quá trình xử lý chunk để xác định hành vi tương ứng.

Điều này đặc biệt quan trọng khi xử lý lỗi theo từng item. Nếu exception chỉ phản ánh một item không hợp lệ và xảy ra trước khi có thay đổi cần hoàn tác, việc không rollback có thể giúp tránh rollback cả chunk. Ngược lại, nếu writer đã ghi một phần dữ liệu hoặc tạo side effect trước khi ném exception, bỏ rollback có thể để lại trạng thái không nhất quán.

## 1. Rollback classifier làm nhiệm vụ gì?

Trong fault-tolerant chunk processing, rollback classifier phân loại exception theo câu hỏi: exception này có yêu cầu rollback transaction của chunk hay không?

Mặc định, lỗi trong quá trình xử lý chunk thường dẫn tới rollback để các thay đổi chưa commit được hoàn tác. Khi một exception được cấu hình là noRollback, Spring Batch có thể tiếp tục xử lý theo chính sách tương ứng mà không yêu cầu rollback chỉ vì exception đó.

Rollback classification là một trục quyết định riêng:

| Quyết định | Câu hỏi | API/cấu hình thường dùng |
|---|---|---|
| Rollback | Exception có làm transaction hiện tại rollback không? | noRollback(...) trong fault-tolerant step |
| Retry | Có thử lại thao tác khi exception xảy ra không? | retry(...), noRetry(...), retryLimit(...) |
| Skip | Có bỏ qua item gây lỗi và tiếp tục không? | skip(...), noSkip(...), skipLimit(...) |
| Backoff | Chờ bao lâu trước lần retry tiếp theo? | backOffPolicy(...) |

Không nên gộp các quyết định trên thành một khái niệm duy nhất. Một lỗi validation có thể không cần retry, được phép skip và được xem xét không rollback nếu xảy ra ở giai đoạn an toàn. Một lỗi deadlock thường cần rollback và retry. Một lỗi cấu hình nghiêm trọng thường cần rollback và làm step thất bại.

## 2. Phân biệt rollback classification với retry và skip classification

Ví dụ, processor phát hiện một đơn hàng thiếu mã khách hàng:

- Retry thường không có ích vì cùng dữ liệu sẽ tiếp tục thiếu mã.
- Skip có thể được cho phép nếu nghiệp vụ chấp nhận đưa đơn hàng vào reject store.
- Rollback phụ thuộc thời điểm exception xảy ra và các thay đổi đã thực hiện trong transaction.

Trong khi đó, nếu writer gặp deadlock:

- Exception có thể retryable.
- Transaction chunk thường cần rollback để giải phóng thay đổi chưa commit và bắt đầu lại thao tác an toàn.
- Không nên đánh dấu deadlock là noRollback chỉ để tránh rollback.

Ma trận minh họa:

| Tình huống | Retry? | Skip? | Rollback? | Hướng xử lý |
|---|---|---|---|---|
| Validation lỗi ở processor, chưa có write | Thường không | Có thể | Có thể không cần nếu transaction vẫn an toàn và policy phù hợp | Ghi reject, tiếp tục item khác |
| Deadlock khi writer ghi database | Thường có giới hạn | Thường không | Có | Rollback chunk rồi retry |
| Thiếu cấu hình bắt buộc | Không | Không | Có nếu transaction đã bắt đầu và cần hủy thay đổi | Fail step |
| Lỗi writer sau khi đã ghi một phần chunk | Tùy loại lỗi | Chỉ khi semantics cho phép | Thường cần | Rollback phần ghi dở dang trước khi recovery |
| Lỗi đọc một dòng không parse được | Thường không | Có thể | Tùy nguồn đọc và transaction | Ghi nhận vị trí dòng và reject |

Đây là hướng dẫn thiết kế, không phải bảng ánh xạ tự động cho mọi exception. Quyết định cuối cùng phụ thuộc giai đoạn phát sinh lỗi, transaction manager, side effect và yêu cầu nghiệp vụ.

## 3. Mặc định rollback trong chunk step

Một chunk step xử lý nhiều item trong một transaction. Ví dụ commit interval là 100:

1. Reader đọc các item.
2. Processor chuyển đổi hoặc filter item.
3. Writer ghi các item còn lại.
4. Spring Batch cập nhật checkpoint và metadata liên quan.
5. Transaction commit.

Nếu exception làm chunk rollback, các thay đổi chưa commit trong resource tham gia transaction bị hoàn tác. Những chunk đã commit trước đó vẫn tồn tại.

~~~mermaid
flowchart TD
    A[Bắt đầu chunk transaction] --> B[Read và process]
    B --> C[Writer ghi dữ liệu]
    C --> D{Có exception?}
    D -- Không --> E[Commit chunk]
    D -- Có --> F[Rollback classification]
    F --> G{Có yêu cầu rollback?}
    G -- Có --> H[Rollback transaction]
    G -- Không --> I[Không rollback chỉ vì exception này]
    H --> J[Retry / skip / fail theo policy]
    I --> J
    E --> K[Chunk tiếp theo]
~~~

Rollback classification không thay thế transaction manager. Nó chỉ tham gia quyết định hành vi đối với exception trong xử lý chunk; transaction manager vẫn là thành phần thực hiện commit hoặc rollback trên resource đã enlist.

Nếu writer dùng datasource hoặc connection không thuộc transaction của step, rollback classifier không thể khiến transaction manager hoàn tác resource đó. Vì vậy, phải xác nhận writer thực sự tham gia transaction mà step quản lý.

## 4. Khai báo exception không rollback bằng noRollback

Trong fault-tolerant chunk step, builder cung cấp noRollback để khai báo exception không yêu cầu rollback transaction của chunk theo rollback classifier.

Ví dụ:

~~~java
@Bean
Step validateAndImportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        ImportSkipListener skipListener) {

    return new StepBuilder("validateAndImportOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .noRollback(InvalidOrderException.class)
            .listener(skipListener)
            .build();
}
~~~

Trong ví dụ, InvalidOrderException được khai báo là skippable và noRollback. Cấu hình này chỉ phù hợp nếu exception biểu thị lỗi riêng của item, phát sinh trước khi có thay đổi nghiệp vụ cần hoàn tác, và việc tiếp tục transaction không làm dữ liệu dở dang.

noRollback không thay thế skip. Nếu exception không được cấu hình là skippable hoặc skip limit đã bị vượt, step vẫn có thể thất bại. Tương tự, skip không tự động thêm noRollback; hai quyết định phải được thiết kế riêng.

Không nên áp dụng noRollback cho toàn bộ RuntimeException hoặc Exception. Một rule quá rộng có thể khiến lỗi writer, lỗi hạ tầng hoặc lỗi lập trình không được rollback như mong muốn.

## 5. Exception classifier và quy tắc theo lớp exception

Rollback classifier thường dựa trên kiểu exception. Một rule cho một lớp exception có thể ảnh hưởng cả các lớp con tùy cách classifier được cấu hình. Vì vậy, cần hiểu cây kế thừa exception trong ứng dụng.

Ví dụ:

~~~java
class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String message) {
        super(message);
    }
}

class MissingCustomerException extends InvalidOrderException {
    MissingCustomerException(String message) {
        super(message);
    }
}
~~~

Nếu noRollback được khai báo cho InvalidOrderException và classifier áp dụng rule cho các lớp con, MissingCustomerException cũng có thể nhận cùng quyết định. Điều này hữu ích khi cả nhóm lỗi validation có cùng semantics, nhưng nguy hiểm nếu một lớp con cần rollback vì đã thực hiện thay đổi trước khi ném lỗi.

Hãy giữ hệ thống exception có ý nghĩa rõ ràng:

- Nhóm lỗi validation riêng của item.
- Nhóm lỗi dependency tạm thời.
- Nhóm lỗi cấu hình hoặc lập trình nghiêm trọng.
- Nhóm lỗi writer có thể xảy ra sau khi đã ghi một phần dữ liệu.

Tránh dùng một exception tổng quát như BatchProcessingException cho nhiều loại lỗi có yêu cầu transaction khác nhau. Nếu cần phân biệt, dùng subtype cụ thể hoặc classifier có quy tắc được kiểm thử.

## 6. Chọn noRollback cho lỗi validation ở processor

Một trường hợp có thể cân nhắc noRollback là processor xác thực item trước khi writer thực hiện ghi dữ liệu:

~~~java
@Bean
ItemProcessor<OrderInput, Order> validateOrderProcessor(
        CustomerRepository customers) {

    return input -> {
        if (input.customerId() == null || input.customerId().isBlank()) {
            throw new InvalidOrderException("customerId is required");
        }

        if (!customers.existsById(input.customerId())) {
            throw new InvalidOrderException(
                    "Unknown customer: " + input.customerId());
        }

        return new Order(input.orderId(), input.customerId(), input.amount());
    };
}
~~~

Nếu lỗi chỉ xảy ra trong bước validation và chưa có write nghiệp vụ nào cho item, có thể thiết kế để skip item mà không rollback toàn bộ chunk. Điều này có thể giảm chi phí khi một chunk có nhiều item hợp lệ và chỉ một vài item không hợp lệ.

Tuy nhiên, processor không nên tạo side effect như cập nhật bảng, gửi email hoặc gọi API trước khi validation hoàn tất. Processor thường nên stateless và tập trung chuyển đổi/kiểm tra. Nếu processor đã thay đổi dữ liệu trong transaction, cần đánh giá xem không rollback có để lại thay đổi đó hay không.

Nếu mục tiêu chỉ là loại item theo một quy tắc bình thường, hãy cân nhắc trả về null để filter thay vì ném exception rồi skip. Filter thể hiện rõ rằng item bị loại có chủ đích; skip thể hiện một lỗi được chính sách cho phép bỏ qua.

## 7. Vì sao noRollback nguy hiểm trong writer?

Writer có thể thực hiện nhiều câu lệnh ghi trong cùng một chunk. Giả sử chunk chứa ba item A, B và C:

1. Writer insert A thành công.
2. Writer insert B thành công.
3. Writer ghi C thì ném exception.

Nếu các câu lệnh tham gia cùng transaction và chunk rollback, insert A và B được hoàn tác cùng C. Nếu exception được phân loại noRollback, không thể mặc định rằng phần ghi dở dang sẽ được tự động phục hồi hoặc writer sẽ chỉ ghi lại C.

Các rủi ro:

- A và B có thể đã được ghi trong khi C thất bại.
- Writer có thể bị gọi lại và insert A/B lần nữa.
- Một số side effect ngoài database có thể đã xảy ra và không rollback.
- Bộ đếm hoặc trạng thái ứng dụng có thể không còn phản ánh cùng một tập dữ liệu.

Vì vậy, không dùng noRollback cho exception writer sau khi đã có thao tác ghi một phần, trừ khi writer được thiết kế đặc biệt để tiếp tục an toàn và có bằng chứng về tính nguyên tử/idempotency. Với lỗi ghi database thông thường, rollback mặc định thường là lựa chọn đúng.

## 8. Kết hợp noRollback với retry

Retry và noRollback không nên được kết hợp tùy tiện. Retry thường nhằm thử lại một thao tác có thể thành công sau khi lỗi tạm thời biến mất. Nếu transaction không rollback, thay đổi dở dang của lần thử trước có thể còn trong transaction hoặc resource.

Ví dụ deadlock:

- Database báo deadlock khi writer ghi.
- Transaction cần rollback để giải phóng trạng thái và cho phép thử lại sạch sẽ.
- Retry policy thử lại sau backoff.

Đánh dấu deadlock là noRollback có thể làm sai semantics phục hồi. Hãy để rollback xảy ra và retry với giới hạn/backoff.

Ví dụ validation:

- Processor phát hiện item sai trước khi writer ghi.
- Lỗi không có ích khi retry.
- Nếu nghiệp vụ cho phép bỏ item và transaction vẫn an toàn, có thể dùng skip cùng noRollback.

Không nên cấu hình retry cho lỗi validation chỉ để chờ dữ liệu tự thay đổi. Nếu dữ liệu có thể được bổ sung từ hệ thống ngoài, cần một bước đồng bộ hoặc quy trình retry ở cấp batch phù hợp hơn.

## 9. Kết hợp noRollback với skip

Một exception được skip vẫn có thể làm rollback chunk theo rollback classifier mặc định. Điều này có thể cần thiết, đặc biệt khi lỗi xảy ra trong writer hoặc sau khi có thay đổi cần hoàn tác.

Nếu exception là lỗi riêng của item ở processor và không có side effect, cấu hình noRollback có thể giảm rollback không cần thiết. Nhưng cần xem xét các yếu tố:

- Exception phát sinh ở read, process hay write?
- Reader có phải nguồn transactional queue không?
- Processor hoặc writer đã thay đổi dữ liệu chưa?
- SkipListener ghi reject record vào cùng transaction hay resource khác?
- Các item khác trong chunk có thể tiếp tục an toàn không?

Một skip policy tốt phải ghi nhận item bị loại. Không chỉ tăng skip count; cần lưu source ID, vị trí nguồn, giai đoạn lỗi và lý do để điều tra/replay. Nếu listener ghi reject record vào cùng transaction, xác nhận việc ghi đó được commit theo cách mong muốn.

## 10. noRollback và transaction attribute

Có hai lớp cấu hình cần phân biệt:

1. Quy tắc rollback của transaction attribute/transaction manager, quyết định transaction xử lý exception như thế nào ở ranh giới transaction.
2. Rollback classification trong fault-tolerant chunk processing, quyết định exception trong xử lý item/chunk có yêu cầu rollback theo chính sách chunk hay không.

Trong cấu hình Spring Batch, transaction attribute cũng có thể điều chỉnh các thuộc tính như isolation, propagation, timeout và rollback rules tùy builder/API của step. Những cấu hình này không nên bị nhầm với retry classifier hoặc skip classifier.

Ví dụ tạo transaction attribute với timeout:

~~~java
@Bean
DefaultTransactionAttribute chunkTransactionAttribute() {
    DefaultTransactionAttribute attribute =
            new DefaultTransactionAttribute();
    attribute.setTimeout(60);
    return attribute;
}
~~~

Sau đó, tùy loại step builder và phiên bản Spring Batch, transaction attribute có thể được gắn vào step qua API transactionAttribute tương ứng. Cần kiểm tra API có trong phiên bản đang dùng trước khi áp dụng.

Không nên cấu hình rollback rule ở nhiều tầng mà không kiểm tra kết quả kết hợp. Một exception có thể được xem là noRollback ở classifier của chunk nhưng vẫn chịu hành vi transaction attribute khác, hoặc ngược lại. Hãy test bằng transaction thật để xác nhận thay đổi database được commit hay rollback như mong muốn.

## 11. noRollback không làm side effect bên ngoài trở nên an toàn

Transaction database không tự quản lý HTTP request, email, file system hoặc message broker. Dù exception được đánh dấu noRollback hay rollback, side effect bên ngoài vẫn có thể đã xảy ra.

Ví dụ processor gọi API kiểm tra hạn mức và API ghi nhận một lượt sử dụng. Sau đó processor ném InvalidOrderException. noRollback không thể hoàn tác request API đó. Nếu retry hoặc skip khiến item được xử lý lại, API có thể nhận cùng tác động lần nữa.

Các cách xử lý:

- Giữ processor thuần chuyển đổi/validation, tránh side effect.
- Đưa side effect vào writer hoặc bước riêng với transaction/idempotency phù hợp.
- Dùng idempotency key ổn định cho API ngoài.
- Dùng transactional outbox để ghi ý định phát message cùng transaction database.
- Dùng inbox/deduplication ở consumer.
- Dùng đối soát nếu kết quả request ngoài không rõ ràng.

Rollback classifier chỉ điều khiển hành vi transaction trong phạm vi Spring Batch; nó không phải distributed transaction coordinator.

## 12. Kiểm tra transaction manager và propagation

Chính sách rollback chỉ có ý nghĩa nếu writer và repository tham gia transaction dự kiến. Cần xác nhận:

- JdbcTemplate dùng DataSource được quản lý bởi transaction manager của step.
- JPA repository tham gia transaction tương ứng và không mở resource độc lập.
- Không chia sẻ JDBC Connection hoặc EntityManager giữa các thread.
- Service được gọi không dùng REQUIRES_NEW ngoài ý muốn.
- Không chạy tác vụ async rồi giả định transaction của chunk bao phủ tác vụ đó.
- Writer không tự commit hoặc mở transaction riêng ngoài kiểm soát.

Nếu service dùng REQUIRES_NEW, transaction mới có thể commit độc lập. Rollback của chunk bên ngoài không hoàn tác dữ liệu đã commit trong transaction mới. Đây có thể là lựa chọn có chủ đích cho audit record, nhưng không phù hợp nếu dữ liệu phải được rollback cùng chunk.

Với nhiều datasource, cần có thiết kế transaction rõ ràng. Một transaction manager JDBC thông thường không tự tạo atomic commit cho hai database độc lập. Nếu cần đồng bộ nhiều resource, cân nhắc outbox/saga hoặc giải pháp distributed transaction phù hợp với hạ tầng.

## 13. Tình huống reader và buffering

Rollback cũng ảnh hưởng tới reader. Một file reader không thể yêu cầu filesystem hoàn tác thao tác đọc như một transactional queue. Spring Batch có thể buffer item trong fault-tolerant chunk processing để dùng lại khi rollback, tùy loại reader và cấu hình.

Với nguồn transactional queue, việc nhận message có thể được rollback để message trở lại queue. Trong trường hợp đó, cấu hình readerIsTransactionalQueue() có thể cần thiết để framework xử lý đúng semantics của nguồn. Chỉ bật tùy chọn này khi reader thực sự dùng một queue có giao dịch nhận message.

Không nên giả định noRollback sẽ làm reader state tự động chính xác. Reader có state cần triển khai ItemStream, lưu checkpoint và có thể khôi phục sau restart. Nếu reader tiến vị trí trong bộ nhớ qua item chưa commit, cần bảo đảm framework hoặc reader có thể phát lại item đúng.

## 14. Kiểm thử rollback classifier

Kiểm thử cần chứng minh quyết định classifier bằng trạng thái dữ liệu, không chỉ bằng số lần gọi phương thức.

Các tình huống quan trọng:

1. **Exception rollback mặc định:** writer ghi dữ liệu rồi ném exception; xác nhận dữ liệu chunk không còn sau rollback.
2. **Exception noRollback ở processor:** item bị skip theo cấu hình; xác nhận item hợp lệ còn lại được xử lý và transaction không để lại thay đổi dở dang.
3. **noRollback nhưng không skippable:** xác nhận step không tự động thành công chỉ vì exception không rollback.
4. **Retryable exception:** deadlock giả lập làm rollback rồi retry; xác nhận lần thử sau thành công và dữ liệu không trùng.
5. **Writer partial failure:** writer ghi một phần rồi ném lỗi; xác nhận rollback bảo vệ tính nguyên tử của chunk.
6. **Exception inheritance:** kiểm tra rule có ảnh hưởng tới lớp con như dự định.
7. **SkipListener:** xác nhận reject record được ghi đúng và không duplicate ngoài ý muốn.
8. **Transaction propagation:** kiểm tra thay đổi trong REQUIRES_NEW có tồn tại sau rollback của transaction ngoài hay không.
9. **External side effect:** mô phỏng API đã nhận request trước khi exception xảy ra; xác nhận idempotency/outbox.
10. **Restart:** sau khi step thất bại, restart cùng identifying JobParameters và xác nhận checkpoint cùng output đúng.

Ví dụ writer test có thể gây lỗi sau khi insert:

~~~java
@Bean
ItemWriter<ImportedOrder> failingWriter(
        JdbcTemplate jdbcTemplate,
        FailureSwitch failureSwitch) {

    return chunk -> {
        for (ImportedOrder item : chunk.getItems()) {
            jdbcTemplate.update(
                    "insert into imported_order(order_id) values (?)",
                    item.orderId());
        }

        if (failureSwitch.shouldFail()) {
            throw new IllegalStateException("Simulated writer failure");
        }
    };
}
~~~

Khi chạy step không cấu hình noRollback cho IllegalStateException, test kiểm tra các insert của chunk bị rollback. Nếu thay đổi classifier để noRollback exception này, test cần xác nhận rõ dữ liệu cuối và chứng minh cấu hình đó thực sự an toàn; không chỉ đổi assertion để chấp nhận dữ liệu partial.

Nên dùng database integration test có transaction manager thật. Mock JdbcTemplate không chứng minh rollback. Tránh bọc toàn bộ test method trong transaction bên ngoài nếu mục tiêu là quan sát commit/rollback thực tế của từng chunk.

## 15. Đọc metadata sau khi rollback

StepExecution cung cấp các trường giúp điều tra:

| Thuộc tính | Ý nghĩa |
|---|---|
| BatchStatus | Trạng thái thực thi của step |
| ExitStatus | Mã kết thúc và mô tả kết quả |
| readCount | Số item reader đã đọc theo metadata |
| writeCount | Số item writer ghi theo metadata |
| skipCount | Tổng số item bị skip |
| commitCount | Số lần commit được ghi nhận |
| rollbackCount | Số lần rollback được ghi nhận |
| readSkipCount | Số item bị skip ở reader |
| processSkipCount | Số item bị skip ở processor |
| writeSkipCount | Số item bị skip ở writer |

Các bộ đếm hữu ích để điều tra nhưng không thay thế việc kiểm tra dữ liệu. Ví dụ, writeCount không chứng minh side effect HTTP đã được xác nhận hoặc dữ liệu không bị ghi trùng. Hãy đối chiếu metadata với bảng nghiệp vụ, reject store và log có correlation ID.

Khi dùng noRollback, cần quan sát cả số lần rollback và kết quả dữ liệu. Nếu rollback count giảm nhưng xuất hiện bản ghi partial hoặc duplicate, chính sách đang làm sai tính toàn vẹn.

## 16. Những lỗi thường gặp

**Nhầm noRollback với noSkip.** noRollback điều khiển rollback classification; noSkip cấm skip exception. Hai API giải quyết hai quyết định khác nhau.

**Cho rằng noRollback làm exception được bỏ qua.** Exception vẫn có thể làm step thất bại nếu không có retry/recovery/skip phù hợp.

**Đánh dấu mọi lỗi validation là noRollback mà không xem side effect.** Processor hoặc listener có thể đã thay đổi dữ liệu. Kiểm tra toàn bộ transaction trước khi bỏ rollback.

**Dùng noRollback cho lỗi writer sau partial write.** Điều này có thể giữ lại một phần chunk. Với lỗi ghi database, rollback thường cần thiết.

**Kết hợp noRollback với retry cho deadlock.** Deadlock thường cần rollback trước khi thử lại. Dùng retry cùng rollback và backoff.

**Dùng exception cha quá rộng.** Rule có thể áp dụng cho nhiều lớp con có semantics khác nhau. Tách exception hoặc kiểm thử inheritance.

**Cho rằng rollback classifier điều khiển mọi resource.** File, HTTP và message ngoài transaction không tự rollback. Dùng idempotency/outbox/reconciliation.

**Bỏ qua transaction propagation.** REQUIRES_NEW có thể commit độc lập. Xác định transaction manager và propagation của service được gọi.

**Chỉ kiểm tra BatchStatus.** Job có thể COMPLETED nhưng dữ liệu partial. Kiểm tra database, reject store, counters và side effect.

## 17. Quy trình chọn chính sách rollback

Trước khi cấu hình classifier cho một step, hãy làm rõ:

1. Exception phát sinh ở reader, processor, writer hay listener?
2. Tại thời điểm đó, transaction đã có thay đổi nghiệp vụ nào chưa?
3. Những thay đổi đó có thể được hoàn tác bằng transaction manager của step không?
4. Exception có thể tự hết và có nên retry không?
5. Item có được phép bỏ qua theo nghiệp vụ không?
6. Nếu không rollback, transaction có thể tiếp tục và commit an toàn không?
7. Writer có side effect ngoài database hoặc partial write không?
8. Rule có ảnh hưởng tới các exception subclass không?
9. SkipListener và reject store có tham gia transaction phù hợp không?
10. Đã có integration test chứng minh dữ liệu sau commit/rollback chưa?

Quy tắc thực hành:

- Giữ rollback mặc định cho lỗi writer và lỗi hạ tầng nếu chưa có lý do rõ ràng để thay đổi.
- Dùng retry có giới hạn và backoff cho lỗi tạm thời cần rollback rồi thử lại.
- Dùng skip cho lỗi riêng của item khi nghiệp vụ cho phép, đồng thời ghi reject.
- Chỉ dùng noRollback khi đã chứng minh exception không để lại thay đổi cần hoàn tác và việc tiếp tục transaction là an toàn.
- Không dùng rollback classifier để xử lý side effect ngoài transaction; thiết kế idempotency hoặc outbox riêng.

## Kết luận

Chính sách rollback cho step có classifier là quyết định độc lập với retry và skip. Rollback classifier xác định exception có yêu cầu hoàn tác transaction chunk hay không; retry classifier xác định có thử lại; skip policy xác định có bỏ item để tiếp tục hay không. Trong fault-tolerant step, noRollback là cách khai báo các exception không cần rollback theo chính sách chunk.

Hãy dùng noRollback có chọn lọc, thường chỉ cho lỗi riêng của item xảy ra trước khi có thay đổi nghiệp vụ cần hoàn tác và khi transaction vẫn an toàn để tiếp tục. Tránh áp dụng cho lỗi writer sau partial write hoặc lỗi hạ tầng như deadlock. Xác nhận transaction manager, propagation, reader state và side effect ngoài database; sau đó kiểm thử bằng database thật để chứng minh kết quả commit/rollback. Một classifier chỉ đúng khi dữ liệu cuối cùng vẫn nhất quán theo yêu cầu nghiệp vụ.
