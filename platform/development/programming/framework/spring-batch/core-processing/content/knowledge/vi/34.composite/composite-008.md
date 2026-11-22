# Writer composite chọn theo classifier

Trong Spring Batch, ClassifierCompositeItemWriter cho phép chọn writer đích dựa trên từng item. Thay vì gửi toàn bộ chunk tới mọi delegate, composite hỏi một Classifier để xác định writer phù hợp cho mỗi item rồi chuyển item đó tới delegate tương ứng.

Cách này hữu ích khi một Step đọc nhiều loại bản ghi nhưng cần xuất chúng tới các đích khác nhau: đơn hàng ưu tiên và thông thường, giao dịch theo loại, bản ghi hợp lệ và bản ghi cần cách ly, hoặc dữ liệu được phân tuyến theo tenant. Classifier quyết định tuyến; delegate writer chịu trách nhiệm ghi dữ liệu. Để cấu hình đúng, cần hiểu cách composite gom item theo delegate, lifecycle của writer con, transaction của chunk và hành vi khi một delegate gặp lỗi.

## 1. ClassifierCompositeItemWriter giải quyết vấn đề gì?

Giả sử một Step đọc tất cả Order từ một nguồn. Mỗi Order có thuộc tính priority. Đơn hàng ưu tiên cần ghi vào file riêng, các đơn hàng còn lại ghi vào file thông thường.

Có thể tạo hai writer độc lập:

- priorityOrderWriter: ghi đơn hàng ưu tiên.
- standardOrderWriter: ghi đơn hàng thông thường.

Classifier kiểm tra từng Order và trả về writer tương ứng. ClassifierCompositeItemWriter điều phối việc gọi các writer này trong cùng một Step.

~~~text
                 Chunk<Order>
          [A, B, C, D, E, F]
                    |
                    v
             Classifier<T>
             /           \
     priority = true    priority = false
           |                 |
           v                 v
   Priority writer     Standard writer
           |                 |
           v                 v
   priority.csv        standard.csv
~~~

Composite không cần biết chi tiết writer đang ghi file, database hay dịch vụ nào. Nó chỉ cần một classifier trả về ItemWriter phù hợp.

## 2. Phân biệt CompositeItemWriter và ClassifierCompositeItemWriter

Hai loại composite có mục đích khác nhau.

| Thành phần | Cách điều phối | Ví dụ |
|---|---|---|
| CompositeItemWriter | Gửi cùng chunk tới lần lượt các delegate | Ghi một bản vào database, đồng thời ghi audit file |
| ClassifierCompositeItemWriter | Phân loại từng item và gửi tới delegate được chọn | Order ưu tiên vào file A, Order thường vào file B |

Với CompositeItemWriter, mọi delegate thường nhận cùng tập item. Với ClassifierCompositeItemWriter, một item được phân loại để chọn writer đích; nó không tự động được gửi tới tất cả writer.

Ví dụ chunk có 5 item:
- 2 item có priority = true.
- 3 item có priority = false.

ClassifierCompositeItemWriter sẽ gửi hai item thuộc nhóm ưu tiên tới writer A và ba item còn lại tới writer B. CompositeItemWriter sẽ gửi cả 5 item cho writer A rồi cả 5 item cho writer B.

Nếu yêu cầu là ghi một item vào nhiều nơi, hãy xem xét CompositeItemWriter hoặc một writer điều phối riêng. Nếu yêu cầu là chọn một nơi ghi theo nội dung item, ClassifierCompositeItemWriter phù hợp hơn.

## 3. Classifier là chiến lược chọn writer

Classifier là một strategy nhận một đối tượng và trả về kết quả phân loại. Trong trường hợp này, kết quả là một ItemWriter có thể ghi kiểu item đang xử lý.

Về ý tưởng:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

Với Order, classifier nhận Order và trả về ItemWriter<? super Order>:

~~~java
Classifier<Order, ItemWriter<? super Order>> classifier =
        order -> order.isPriority()
                ? priorityWriter
                : standardWriter;
~~~

Classifier nên có một quy tắc rõ ràng, dễ kiểm thử và ổn định trong suốt lần chạy. Không nên để classifier tự thực hiện side effect như ghi file, cập nhật database hoặc gửi HTTP; những hành động đó thuộc delegate writer.

Classifier có thể dựa trên:
- Một field như loại giao dịch hoặc trạng thái.
- Enum hoặc mã nghiệp vụ.
- Tenant hoặc khu vực.
- Ngưỡng số tiền hoặc mức ưu tiên.
- Loại class khi chunk chứa nhiều subtype.
- Kết quả đã được chuẩn hóa bởi ItemProcessor.

## 4. Cấu hình ClassifierCompositeItemWriter bằng Java

Một cách cấu hình phổ biến là tạo các delegate trước, sau đó đặt classifier vào ClassifierCompositeItemWriter.

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        @Qualifier("priorityOrderWriter")
        ItemWriter<Order> priorityWriter,
        @Qualifier("standardOrderWriter")
        ItemWriter<Order> standardWriter) {

    ClassifierCompositeItemWriter<Order> writer =
            new ClassifierCompositeItemWriter<>();

    writer.setClassifier(order ->
            order.isPriority()
                    ? priorityWriter
                    : standardWriter);

    return writer;
}
~~~

Trong ví dụ:
- Order là kiểu item đầu vào.
- setClassifier(...) nhận chiến lược chọn writer.
- Classifier trả về delegate dựa trên thuộc tính priority.
- Composite chịu trách nhiệm nhóm và gọi các delegate.

Dùng @Qualifier khi có nhiều bean cùng implement ItemWriter. Nếu inject theo type mà có nhiều ứng viên, Spring có thể báo NoUniqueBeanDefinitionException.

Các package và chữ ký method cụ thể cần khớp với phiên bản Spring Batch đang dùng. Trong Spring Batch 5, ItemWriter nhận Chunk; ở các phiên bản cũ, chữ ký write có thể nhận List.

## 5. Khai báo delegate writer

Delegate là writer thực sự thực hiện việc ghi. Chúng có thể dùng cùng kiểu item nhưng khác resource hoặc cách lưu trữ.

Ví dụ hai file writer:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> priorityOrderWriter(
        @Value("#{jobParameters['priorityOutput']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("priorityOrderWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount", "priority")
            .saveState(true)
            .build();
}

@Bean
@StepScope
FlatFileItemWriter<Order> standardOrderWriter(
        @Value("#{jobParameters['standardOutput']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("standardOrderWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount", "priority")
            .saveState(true)
            .build();
}
~~~

Hai writer có state riêng, tên riêng và output path riêng. @StepScope cho phép nhận JobParameters khi Step thực sự chạy. Nếu resource cố định và writer không cần late binding, có thể khai báo theo scope phù hợp khác.

Không dùng chung một instance writer cho nhiều route nếu writer giữ state hoặc resource riêng. Mỗi delegate nên có lifecycle và output resource rõ ràng.

## 6. Gắn composite writer vào Step

Step sử dụng ClassifierCompositeItemWriter như writer chính:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ClassifierCompositeItemWriter<Order> orderRoutingWriter,
        FlatFileItemWriter<Order> priorityOrderWriter,
        FlatFileItemWriter<Order> standardOrderWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderRoutingWriter)
            .stream(priorityOrderWriter)
            .stream(standardOrderWriter)
            .build();
}
~~~

Trong ví dụ này, các delegate là FlatFileItemWriter nên chúng có ItemStream lifecycle. Cần đăng ký chúng với Step qua .stream(...) để Spring Batch gọi open, update và close.

Điểm này rất quan trọng: ClassifierCompositeItemWriter chỉ chịu trách nhiệm dispatch write theo classifier; bản thân composite không thay thế lifecycle của các delegate stream. Nếu bỏ đăng ký delegate ItemStream, file writer có thể không được mở/đóng và checkpoint của chúng không được lưu như mong đợi.

Nếu delegate chỉ là writer stateless không triển khai ItemStream thì không cần đăng ký nó như stream. Hãy xem interface thực tế mà delegate implement.

## 7. Composite nhóm item theo delegate

ClassifierCompositeItemWriter không nhất thiết gọi delegate một lần cho từng item. Nó phân loại các item trong chunk, nhóm chúng theo writer được chọn rồi gọi từng writer với nhóm item tương ứng.

Ví dụ:

~~~text
Chunk đầu vào:
  A(priority)
  B(standard)
  C(priority)
  D(standard)
  E(priority)

Sau phân loại:
  Priority writer: [A, C, E]
  Standard writer: [B, D]

Các delegate nhận:
  priorityWriter.write([A, C, E])
  standardWriter.write([B, D])
~~~

Cách gom nhóm này cho phép delegate tiếp tục xử lý theo chunk, tận dụng batch insert hoặc ghi tuần tự hiệu quả hơn so với gọi write cho từng item.

Thứ tự item bên trong nhóm của mỗi delegate được giữ theo thứ tự xuất hiện trong chunk. Tuy nhiên, không nên dựa vào thứ tự gọi giữa các delegate như một hợp đồng nghiệp vụ. Nếu cần thứ tự toàn cục giữa các route, cần thiết kế riêng hoặc sắp xếp/điều phối trước khi ghi.

## 8. Một item được gửi tới bao nhiêu delegate?

Với một classifier thông thường, mỗi item được gửi tới writer mà classifier trả về. Nếu classifier luôn trả về đúng một delegate, mỗi item có một route.

Ví dụ:
- Order A -> priority writer.
- Order B -> standard writer.
- Order C -> priority writer.

Nếu muốn một item được ghi vào nhiều đích, classifier composite không phải cơ chế broadcast. Có thể:
- Trả về một writer adapter gọi nhiều writer con.
- Dùng CompositeItemWriter bên trong một route.
- Tạo writer điều phối chuyên biệt cho quy tắc đó.

Ví dụ adapter cho route ưu tiên vừa ghi database vừa ghi audit:

~~~java
@Bean
CompositeItemWriter<Order> priorityAuditWriter(
        ItemWriter<Order> databaseWriter,
        ItemWriter<Order> auditWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, auditWriter)
            .build();
}
~~~

Classifier có thể chọn priorityAuditWriter cho Order ưu tiên và standardWriter cho các Order khác. Cần bảo đảm các delegate con có lifecycle ItemStream được đăng ký đúng với Step nếu chúng cần open/update/close.

## 9. Phân loại theo enum hoặc loại nghiệp vụ

Một quy tắc dễ quản lý là dùng enum thay vì nhiều điều kiện boolean rải rác.

~~~java
public enum OrderChannel {
    PRIORITY,
    STANDARD,
    INTERNATIONAL
}
~~~

Classifier:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        ItemWriter<Order> priorityWriter,
        ItemWriter<Order> standardWriter,
        ItemWriter<Order> internationalWriter) {

    Map<OrderChannel, ItemWriter<? super Order>> writers =
            Map.of(
                    OrderChannel.PRIORITY, priorityWriter,
                    OrderChannel.STANDARD, standardWriter,
                    OrderChannel.INTERNATIONAL, internationalWriter);

    ClassifierCompositeItemWriter<Order> composite =
            new ClassifierCompositeItemWriter<>();

    composite.setClassifier(order -> {
        ItemWriter<? super Order> writer =
                writers.get(order.getChannel());

        if (writer == null) {
            throw new IllegalArgumentException(
                    "Unsupported order channel: " + order.getChannel());
        }

        return writer;
    });

    return composite;
}
~~~

Cách dùng map phù hợp khi số route cố định và được cấu hình lúc khởi tạo application. Nếu classifier có nhiều nhánh hoặc cần test độc lập, hãy tách thành class riêng thay vì để lambda quá dài trong bean configuration.

Không trả null khi không có route. Hãy định nghĩa rõ default writer, reject writer hoặc ném exception để Step thất bại. Một route bị bỏ quên có thể khiến item không được ghi.

## 10. Phân loại theo nhiều điều kiện

Classifier có thể kết hợp nhiều thuộc tính. Ví dụ phân loại theo tenant trước, sau đó theo loại giao dịch:

~~~java
classifier.setClassifier(item -> {
    if (item.isRejected()) {
        return rejectedWriter;
    }

    if (item.getAmount().compareTo(bigAmountLimit) >= 0) {
        return highValueWriter;
    }

    if (item.isInternational()) {
        return internationalWriter;
    }

    return standardWriter;
});
~~~

Thứ tự điều kiện là một phần của business rule. Nếu một item thỏa nhiều điều kiện, nhánh đầu tiên được chọn. Hãy viết rõ precedence và kiểm thử các trường hợp giao nhau.

Nếu logic phân loại phụ thuộc dữ liệu bên ngoài, chẳng hạn tra bảng cấu hình hoặc gọi service, tránh thực hiện truy vấn mạng/database riêng cho từng item nếu có thể. Nên tải rule hoặc mapping một lần, cache an toàn theo Job/Step, hoặc chuẩn hóa route trong processor.

Classifier nên nhanh và có kết quả xác định cho cùng một item trong cùng lần chạy. Nếu rule thay đổi giữa lúc Job chạy, item có thể bị phân vào route khác khi retry hoặc restart.

## 11. Phân loại theo subtype

Một số Job xử lý nhiều subtype trong cùng một luồng. Có thể dùng classifier dựa trên kiểu runtime:

~~~java
Classifier<BaseEvent, ItemWriter<? super BaseEvent>> eventClassifier =
        event -> {
            if (event instanceof OrderCreatedEvent) {
                return orderEventWriter;
            }
            if (event instanceof PaymentReceivedEvent) {
                return paymentEventWriter;
            }
            throw new IllegalArgumentException(
                    "Unsupported event type: " + event.getClass().getName());
        };
~~~

Các writer được trả về phải có khả năng nhận kiểu BaseEvent hoặc được bọc bằng adapter có kiểm tra và chuyển kiểu rõ ràng. Một ItemWriter<OrderCreatedEvent> không thể tự động nhận Chunk<BaseEvent> chỉ vì mọi OrderCreatedEvent đều là BaseEvent. Không dùng unchecked cast để né generic type safety.

Nếu các route có schema khác nhau, có thể dùng processor chuyển mỗi input thành một envelope chung có chứa route và payload đã chuẩn hóa, rồi các delegate đọc envelope đó. Chỉ dùng thiết kế này khi cần; không làm phức tạp model nếu các delegate có thể nhận cùng kiểu item.

## 12. Dùng ItemProcessor để chuẩn hóa route

Classifier có thể phân loại trực tiếp domain object, nhưng trong nhiều hệ thống, ItemProcessor là nơi thích hợp để tính toán route và xác thực dữ liệu.

Ví dụ:

~~~java
public record RoutedOrder(
        Order order,
        OrderChannel channel) {
}

@Bean
ItemProcessor<Order, RoutedOrder> routeOrderProcessor() {
    return order -> {
        OrderChannel channel =
                order.isPriority()
                        ? OrderChannel.PRIORITY
                        : OrderChannel.STANDARD;

        return new RoutedOrder(order, channel);
    };
}
~~~

Khi đó writer composite phân loại RoutedOrder theo channel. Delegate có thể nhận RoutedOrder hoặc adapter trích xuất Order trước khi ghi.

Ưu điểm:
- Quy tắc nghiệp vụ được kiểm thử độc lập.
- Có thể ghi log route đã chọn.
- Có thể reject item không hợp lệ trước writer.
- Retry không phải tính lại từ một nguồn cấu hình thay đổi nếu route đã được xác định trong item.

Nếu processor trả null để filter item, item đó không tới writer và classifier không được gọi cho nó. Hãy phân biệt filtering có chủ đích với route bị thiếu.

## 13. Classifier phải ổn định qua retry và restart

Một Job có thể retry chunk hoặc restart sau khi process thất bại. Nếu classifier chọn route khác nhau giữa các lần xử lý cùng item, dữ liệu có thể được ghi vào nhiều nơi hoặc thiếu ở nơi mong đợi.

Ví dụ rủi ro:
- Route dựa trên tỷ giá hoặc trạng thái cấu hình thay đổi theo thời gian.
- Route dựa trên service bên ngoài nhưng service trả kết quả khác khi retry.
- Route dựa trên thời điểm hiện tại.
- Route dựa trên field mutable bị processor hoặc delegate thay đổi.

Để giữ tính nhất quán:
- Dựa trên dữ liệu đầu vào ổn định hoặc business key đã chốt.
- Nếu route phụ thuộc cấu hình, lưu version/configuration ID cho Job.
- Không sửa field phân loại sau khi item đã được route.
- Giữ cùng JobParameters và nguồn dữ liệu khi restart.
- Nếu route có thể thay đổi theo nghiệp vụ, ghi nhận route đã chọn vào dữ liệu bền vững hoặc staging.

Classifier không tự lưu lịch sử route vào JobRepository. Nếu cần audit từng item đã đi đâu, hãy ghi route vào audit table/file hoặc metadata của domain.

## 14. Transaction của chunk khi nhiều delegate được gọi

ClassifierCompositeItemWriter được gọi trong write phase của chunk. Các delegate được gọi trong phạm vi cùng lần xử lý chunk, và các writer JDBC dùng cùng transaction manager/DataSource có thể tham gia transaction chunk đó.

Ví dụ hai delegate ghi hai bảng trong cùng database:

~~~text
Chunk transaction begins
    |
    +--> priorityWriter.write(priorityItems)
    |
    +--> standardWriter.write(standardItems)
    |
    v
Chunk transaction commits
~~~

Nếu một delegate ném exception, Step xử lý chunk theo rollback/retry/skip policy. Các thay đổi database tham gia cùng transaction có thể được rollback.

Tuy nhiên:
- Hai delegate dùng hai DataSource khác nhau không tự động có transaction nguyên tử chung.
- File system, HTTP service và message broker không tự tham gia transaction JDBC.
- Một delegate có thể đã tạo side effect bên ngoài trước khi delegate sau lỗi.

Do đó, composite writer không phải distributed transaction coordinator. Nếu cần consistency giữa nhiều hệ thống, cân nhắc outbox, staging, idempotent consumer, publish sau commit hoặc cơ chế transaction phân tán được hỗ trợ rõ ràng.

## 15. Lỗi giữa các delegate và partial write

Giả sử một chunk có item cho writer A và writer B. Composite gọi A thành công rồi B ném exception.

Kết quả phụ thuộc loại resource:
- Nếu A và B cùng ghi database trên cùng transaction, rollback có thể hoàn tác cả hai.
- Nếu A ghi file rồi B ghi database thất bại, file có thể đã chứa dữ liệu dù chunk rollback.
- Nếu A gọi HTTP thành công rồi B lỗi, remote side effect không tự bị thu hồi.
- Nếu A và B dùng hai database transaction độc lập, một bên có thể commit trong khi bên kia rollback.

Không giả định composite sẽ tự undo delegate đã chạy trước. Với external side effect, thiết kế:
- Idempotency key theo JobInstance/item ID.
- Ghi staging rồi publish sau khi Job hoàn tất.
- Outbox table trong transaction database.
- Reconciliation hoặc compensation có kiểm soát.
- Retry an toàn cho từng delegate.

Nếu một route là không thể ghi được, thường nên để chunk fail hoặc đưa item vào reject/quarantine theo quy tắc nghiệp vụ. Không âm thầm bỏ qua exception vì có thể tạo dữ liệu thiếu mà Job vẫn COMPLETED.

## 16. Skip và retry khi delegate writer lỗi

ClassifierCompositeItemWriter không tự định nghĩa chính sách retry hoặc skip. Những chính sách đó được cấu hình trên Step.

Ví dụ:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderRoutingWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

Đây là ví dụ khái quát; API cấu hình fault tolerance có thể khác theo phiên bản Spring Batch. Chỉ retry lỗi có khả năng tự phục hồi, chẳng hạn lỗi kết nối tạm thời hoặc deadlock theo chính sách ứng dụng. Chỉ skip lỗi nghiệp vụ được phép bỏ qua và cần ghi nhận item bị loại.

Nếu delegate writer đã tạo side effect ngoài transaction rồi ném exception, retry có thể gọi lại writer và tạo side effect trùng. Cần idempotency hoặc cơ chế phát hiện item đã được ghi.

## 17. Delegate ItemStream phải được đăng ký riêng

ClassifierCompositeItemWriter tập trung vào phân loại và gọi writer. Nếu delegate là ItemStreamWriter hoặc ItemStream, cần bảo đảm Step quản lý lifecycle của từng delegate.

Ví dụ:
- FlatFileItemWriter cần open file, update checkpoint và close file.
- Custom writer có state cần khôi phục trong open.
- Writer dùng resource cần đóng đúng lúc.

Đăng ký từng delegate trong Step:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderRoutingWriter)
        .stream(priorityOrderWriter)
        .stream(standardOrderWriter)
        .build();
~~~

Nếu delegate là một CompositeItemWriter chứa các stream con, hãy kiểm tra lifecycle propagation của composite đó và đăng ký stream theo contract của phiên bản framework. Không giả định chỉ vì writer được gọi qua một wrapper mà mọi delegate đều tự động nhận open/update/close.

Giữ tên stream và key state ổn định. Khi restart, mỗi writer cần khôi phục đúng resource và checkpoint của chính nó.

## 18. Writer step-scoped và late binding

Delegate writer có thể cần JobParameters hoặc Step ExecutionContext, chẳng hạn output path theo ngày, tenant hoặc JobInstance. Khi đó, khai báo delegate bằng @StepScope.

Ví dụ:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> priorityOrderWriter(
        @Value("#{jobParameters['priorityOutput']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("priorityOrderWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

Composite có thể được tạo trong ApplicationContext với proxy delegate. Target writer thực tế chỉ được khởi tạo khi Step scope hoạt động và các JobParameters đã có.

Không gọi trực tiếp method của target writer trước khi Step chạy. Hãy để Spring quản lý proxy và resource lifecycle.

## 19. Routing tới reject writer

Một pattern phổ biến là tách bản ghi hợp lệ và không hợp lệ:

~~~java
composite.setClassifier(item ->
        item.isValid()
                ? acceptedWriter
                : rejectedWriter);
~~~

Reject writer có thể ghi bản ghi lỗi cùng lý do vào file cách ly hoặc bảng kiểm tra. Cách này hữu ích khi business muốn xử lý phần dữ liệu hợp lệ và vẫn lưu lại phần bị từ chối.

Cần phân biệt:
- Invalid item theo nghiệp vụ: có thể route tới reject writer nếu Job được phép tiếp tục.
- Writer infrastructure failure: ví dụ disk full hoặc database unavailable; thường phải làm chunk fail.
- Unexpected classifier failure: lỗi code hoặc thiếu route; cần fail rõ ràng.

Không biến mọi exception thành reject item. Nếu writer không ghi được reject file, Job cũng cần phản ánh thất bại để không làm mất dữ liệu lỗi.

## 20. Routing theo tenant hoặc partition

Classifier có thể chọn writer theo tenant, nhưng cần cẩn thận với số lượng route. Nếu mỗi tenant có writer riêng, map writer có thể lớn và resource count tăng theo tenant.

Với số route nhỏ, cố định, map tenant -> writer có thể hợp lý. Với hàng nghìn tenant hoặc route tạo động, nên cân nhắc:
- Ghi vào một bảng có tenant_id.
- Ghi vào một resource chung có partition key.
- Dùng partitioned Step để mỗi worker xử lý một tenant hoặc nhóm tenant.
- Dùng writer adapter quản lý resource theo một lifecycle được thiết kế rõ.

ClassifierCompositeItemWriter không tự tạo StepExecution riêng cho từng route. Nó chỉ chọn delegate trong Step hiện tại. Nếu mỗi tenant cần transaction, restart, concurrency hoặc resource isolation riêng, partitioning có thể phù hợp hơn routing trong một writer.

## 21. Thứ tự ghi và tính ổn định

Vì composite nhóm item theo delegate trước khi gọi writer, thứ tự xử lý tổng thể có thể khác thứ tự ban đầu giữa các route.

Ví dụ input:

~~~text
A -> writer 1
B -> writer 2
C -> writer 1
D -> writer 2
~~~

Writer 1 nhận [A, C]; writer 2 nhận [B, D]. Không nên giả định output side effect sẽ xen kẽ theo thứ tự A, B, C, D.

Nếu thứ tự toàn cục là yêu cầu nghiệp vụ:
- Dùng một writer duy nhất xử lý từng item theo thứ tự.
- Tạo một adapter ghi tuần tự tới đúng đích cho mỗi item.
- Tách dữ liệu thành luồng riêng và điều phối bằng bước downstream.
- Lưu sequence number để consumer có thể tái lập thứ tự.

Trong mỗi delegate, thứ tự item theo chunk có thể được giữ, nhưng thứ tự giữa các chunk cũng phụ thuộc cách Step đọc và commit. Không dùng routing để bảo đảm thứ tự liên hệ thống nếu chưa có thiết kế cụ thể.

## 22. Thread safety và concurrency

Trong một Step chạy đa luồng, cùng một ClassifierCompositeItemWriter hoặc delegate có thể được gọi đồng thời tùy mô hình thực thi. Classifier nên thread-safe và không giữ state mutable không được đồng bộ.

Các điểm cần kiểm tra:
- Delegate writer có thread-safe không?
- Writer có giữ một file stream dùng chung không?
- Hai thread có thể ghi cùng resource đồng thời không?
- Classifier có dùng mutable map hoặc counter không?
- Route có được xác định độc lập cho từng item không?
- Checkpoint của delegate có được cập nhật an toàn không?

@StepScope tạo target theo StepExecution, không tự tạo một writer riêng cho mỗi thread trong cùng StepExecution. Nếu delegate không thread-safe, dùng partitioning với resource riêng hoặc một cơ chế tuần tự hóa được thiết kế rõ ràng.

Trong partitioning, mỗi worker StepExecution nên nhận delegate/resource riêng theo partition key. Không để nhiều worker ghi cùng một file hoặc dùng chung mutable writer state nếu không có coordination.

## 23. Logging và đo lường theo route

Khi cần quan sát dữ liệu được phân tuyến, có thể ghi metrics theo delegate:
- Số item được gửi tới mỗi writer.
- Số lần delegate write.
- Thời gian ghi của từng route.
- Số lỗi và số lần retry.
- Số item bị reject.
- JobExecution ID và Step name.

Có thể bọc delegate bằng writer adapter để đếm item trước/sau khi ghi. Đảm bảo counter không làm sai transaction semantics hoặc tạo race condition trong multi-threaded Step.

Không ghi toàn bộ payload vào log. Dùng business key hoặc ID đã được phép để truy vết item. Metrics tag nên có số lượng route hữu hạn; tránh dùng item ID hoặc tenant ID có cardinality rất lớn làm tag.

## 24. Kiểm thử ClassifierCompositeItemWriter

Nên kiểm thử classifier riêng và kiểm thử tích hợp với Step.

### Unit test cho classifier

Xác nhận:
- Item priority chọn đúng priority writer.
- Item standard chọn đúng standard writer.
- Các enum hoặc loại item khác chọn đúng route.
- Giá trị null hoặc route không hỗ trợ được xử lý rõ ràng.
- Quy tắc ưu tiên giữa nhiều điều kiện đúng như business rule.

### Unit test cho composite

Dùng writer giả/mock để xác nhận:
- Mỗi item được phân loại đúng.
- Delegate chỉ nhận item thuộc route của nó.
- Item trong từng nhóm giữ thứ tự mong muốn.
- Chunk rỗng không tạo side effect.
- Lỗi từ delegate được truyền lên Step.
- Không có item nào bị âm thầm bỏ khi classifier không tìm thấy route.

### Integration test cho Step

| Kịch bản | Điều cần xác nhận |
|---|---|
| Chunk chỉ có một route | Chỉ delegate tương ứng nhận item |
| Chunk có nhiều route | Các delegate nhận đúng nhóm item |
| Một delegate lỗi | Chunk/Step phản ánh lỗi theo policy |
| Hai delegate ghi cùng database transaction | Rollback đúng khi một delegate lỗi |
| Delegate là ItemStream | open/update/close được gọi |
| Restart | Từng delegate khôi phục checkpoint đúng |
| Output file | Không ghi trùng hoặc mất item sau restart |
| Multi-threaded Step | Delegate và classifier an toàn khi concurrent |
| Route không hợp lệ | Job fail hoặc reject theo quy tắc đã định |

Không chỉ kiểm tra số lần gọi write. Hãy xác nhận dữ liệu thực tế của từng delegate và kết quả cuối của JobRepository.

## 25. Lỗi thường gặp

**Dùng CompositeItemWriter khi chỉ muốn chọn một đích.** Mọi delegate có thể nhận cùng chunk và dữ liệu bị ghi lặp.

**Classifier trả về null.** Không có writer hợp lệ cho item; hãy định nghĩa default/reject hoặc fail rõ.

**Inject nhiều ItemWriter mà không có Qualifier.** Spring có thể không xác định được bean phù hợp.

**Cho rằng mỗi delegate nhận toàn bộ chunk.** Mỗi delegate chỉ nhận nhóm item đã được phân loại cho nó.

**Cho rằng thứ tự giữa các route được giữ nguyên.** Composite gom nhóm theo writer nên không đảm bảo thứ tự side effect toàn cục.

**Không đăng ký delegate ItemStream.** File writer hoặc stateful writer không nhận đủ lifecycle callback.

**Nhiều delegate ghi ra cùng file.** Có thể gây xung đột resource hoặc hỏng output.

**Classifier dùng rule thay đổi giữa retry.** Cùng item có thể đi vào route khác sau khi xử lý lại.

**Retry external side effect mà không idempotent.** Item có thể được ghi/gửi trùng.

**Dùng chung writer không thread-safe.** Multi-threaded Step có thể gây race condition.

**Dùng route theo tenant để thay partitioning khi cần isolation.** Các route vẫn ở cùng StepExecution và không tự có lifecycle độc lập.

**Cho rằng nhiều delegate là một distributed transaction.** Composite chỉ điều phối lời gọi; không làm các hệ thống ngoài cùng commit nguyên tử.

## 26. Quy trình triển khai writer composite chọn theo classifier

Khi cần route item tới các writer khác nhau, hãy thực hiện theo trình tự:

1. Xác định rule route và số lượng đích cần hỗ trợ.
2. Chọn ClassifierCompositeItemWriter nếu mỗi item cần chọn một delegate.
3. Dùng CompositeItemWriter nếu cùng item phải được gửi tới nhiều delegate.
4. Tạo delegate writer cùng nhận kiểu item phù hợp hoặc viết adapter có kiểm tra kiểu rõ ràng.
5. Tạo classifier thuần, ổn định và có nhánh xử lý route không hợp lệ.
6. Cấu hình ClassifierCompositeItemWriter bằng setClassifier.
7. Gắn composite vào writer(...) của Step.
8. Đăng ký riêng các delegate ItemStream bằng stream(...) khi cần.
9. Xác định transaction và idempotency cho các delegate ghi vào nhiều resource.
10. Giữ rule, output path và checkpoint ổn định qua retry/restart.
11. Kiểm tra thread safety nếu Step chạy song song; cân nhắc partitioning khi cần isolation theo route.
12. Kiểm thử routing, nhóm item, exception, rollback, restart và dữ liệu output thực tế.

ClassifierCompositeItemWriter tách quyết định route khỏi thao tác ghi. Classifier chọn writer theo từng item; composite gom item theo delegate và gọi các writer; delegate quản lý resource và cách lưu dữ liệu. Khi quy tắc phân loại ổn định, lifecycle của delegate được đăng ký đầy đủ và transaction/side effect được thiết kế đúng, một Step có thể điều phối nhiều đích ghi mà vẫn giữ được khả năng theo dõi và restart của Spring Batch.

