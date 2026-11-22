# Lỗi phân loại và skip trong Spring Batch

Trong một batch job có nhiều loại item, writer có thể cần chọn đích ghi dựa trên thuộc tính của từng item. Ví dụ order nội địa được ghi vào bảng A, order quốc tế vào bảng B, còn record có loại không được hỗ trợ phải được cách ly hoặc xử lý lỗi. Spring Batch cung cấp ClassifierCompositeItemWriter để định tuyến item đến writer phù hợp.

Khi phân loại hoặc writer delegate gặp lỗi, step phải quyết định có retry, skip hay dừng job. Hai nhóm lỗi này cần được phân biệt: lỗi phân loại cho biết item không thể xác định đích ghi; lỗi delegate cho biết đã chọn được đích nhưng thao tác ghi thất bại. Cách phân loại exception đúng giúp batch bỏ qua dữ liệu lỗi có kiểm soát, đồng thời vẫn dừng khi hạ tầng hoặc cấu hình có vấn đề.

## 1. ClassifierCompositeItemWriter làm gì?

ClassifierCompositeItemWriter nhận một chunk và dùng một Classifier để chọn ItemWriter cho từng item. Mỗi item được chuyển tới một delegate dựa trên kết quả phân loại.

~~~text
Chunk<Order>
  |
  v
ClassifierCompositeItemWriter
  |
  +-- Order loại DOMESTIC ------> domesticWriter
  |
  +-- Order loại INTERNATIONAL -> internationalWriter
  |
  +-- Order loại PARTNER --------> partnerWriter
~~~

Đây là định tuyến: mỗi item đi tới một delegate được chọn. Khác với CompositeItemWriter, nơi mọi delegate đều nhận toàn bộ chunk, classifier writer chọn writer theo từng item.

| Writer | Hành vi |
| --- | --- |
| CompositeItemWriter | Gửi cùng chunk tới tất cả delegate theo thứ tự cấu hình |
| ClassifierCompositeItemWriter | Chọn một delegate cho từng item |
| Writer tùy chỉnh gom nhóm | Phân loại item, gom theo đích rồi gọi mỗi delegate một lần cho nhóm |

Ví dụ một chunk có 5 order, gồm 3 order nội địa và 2 order quốc tế. Classifier writer chuyển 3 item nội địa tới domesticWriter, 2 item quốc tế tới internationalWriter. Nó không tự sao chép mỗi order sang cả hai writer.

## 2. Phân biệt lỗi phân loại và lỗi ghi

Có hai thời điểm có thể phát sinh exception:

1. **Trong classifier:** hệ thống không tìm được route hợp lệ cho item, hoặc logic phân loại phát hiện dữ liệu không hợp lệ.
2. **Trong delegate writer:** route đã được chọn, nhưng thao tác ghi vào database, file, API hoặc đích khác thất bại.

Ví dụ:

~~~text
Order 101
  classifier -> DOMESTIC
  domesticWriter -> ghi thành công

Order 102
  classifier -> UNKNOWN
  -> UnroutableOrderException
  -> không delegate nào được gọi cho item này

Order 103
  classifier -> INTERNATIONAL
  internationalWriter -> database timeout
  -> TransientDataAccessException
~~~

Lỗi của order 102 có thể là lỗi dữ liệu của một record. Lỗi của order 103 có thể là lỗi hạ tầng tạm thời. Không nên áp dụng cùng một skip/retry policy cho cả hai nhóm.

## 3. Cấu hình ClassifierCompositeItemWriter

Trong Spring Batch 5, có thể tạo ClassifierCompositeItemWriter và gắn classifier qua setClassifier:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> internationalWriter) {

    ClassifierCompositeItemWriter<Order> writer =
        new ClassifierCompositeItemWriter<>();

    writer.setClassifier(order -> {
        return switch (order.market()) {
            case DOMESTIC -> domesticWriter;
            case INTERNATIONAL -> internationalWriter;
        };
    });

    return writer;
}
~~~

Ví dụ giả định market() là enum có hai giá trị. Nếu enum hoặc dữ liệu nguồn có thể chứa route khác, cần định nghĩa nhánh fallback hoặc exception rõ ràng thay vì để route không hợp lệ lọt vào writer.

Đăng ký writer vào step:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ClassifierCompositeItemWriter<Order> orderRoutingWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .writer(orderRoutingWriter)
        .build();
}
~~~

ClassifierCompositeItemWriter chịu trách nhiệm gọi classifier và writer được chọn. Step vẫn quản lý transaction chunk và fault tolerance.

## 4. Classifier nên đơn giản, xác định và không có side effect

Classifier nên dựa trên dữ liệu đã có trong item, chẳng hạn enum, loại khách hàng, region hoặc destination code. Cùng một item phải cho cùng kết quả trong một lần xử lý.

Không nên gọi database hoặc HTTP API từ classifier để quyết định route cho từng item. Điều đó có thể tạo N+1 query/network call, khiến route thay đổi giữa retry và làm khó kiểm soát lỗi. Nếu cần tra cứu thông tin để phân loại, hãy enrich item trước đó trong processor hoặc dùng một cache/reference service có lifecycle và concurrency rõ ràng.

Ví dụ classifier dễ kiểm thử:

~~~java
private ItemWriter<? super Order> classify(
        Order order,
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> internationalWriter) {

    return switch (order.market()) {
        case DOMESTIC -> domesticWriter;
        case INTERNATIONAL -> internationalWriter;
    };
}
~~~

Không lưu currentWriter hoặc currentOrder trong mutable field của classifier. Writer có thể được dùng bởi nhiều execution hoặc thread; route nên được tính từ tham số của lần gọi.

## 5. Xử lý route không được hỗ trợ

Có hai chiến lược chính khi item không có route hợp lệ:

- Chọn một writer cách ly (quarantine/reject writer) để lưu record cùng lý do không xử lý được.
- Ném exception có kiểu riêng để step áp dụng skip hoặc fail.

Ví dụ:

~~~java
public class UnroutableOrderException extends RuntimeException {

    public UnroutableOrderException(String message) {
        super(message);
    }
}
~~~

Classifier:

~~~java
writer.setClassifier(order -> {
    if (order.market() == null) {
        throw new UnroutableOrderException(
            "Order " + order.id() + " has no market"
        );
    }

    return switch (order.market()) {
        case DOMESTIC -> domesticWriter;
        case INTERNATIONAL -> internationalWriter;
    };
});
~~~

Nếu loại không hợp lệ là lỗi dữ liệu từng record và nghiệp vụ cho phép bỏ qua, có thể cấu hình skip cho UnroutableOrderException. Nếu route không hợp lệ cho thấy cả file đang dùng schema không tương thích hoặc cấu hình triển khai sai, nên fail job thay vì skip hàng loạt.

Không trả về null như một cách biểu diễn “không có writer”. Hãy trả một reject writer rõ ràng hoặc ném exception có ý nghĩa. Một delegate null thường dẫn tới lỗi runtime khó hiểu và không thể hiện được nguyên nhân nghiệp vụ.

## 6. Dùng reject writer khi cần lưu record lỗi

Skip làm item không đi tiếp qua writer chính. Nếu cần giữ record để sửa và xử lý lại, hãy dùng một reject/quarantine writer:

~~~java
@Bean
ItemWriter<Order> rejectedOrderWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (Order order : chunk) {
            jdbcTemplate.update("""
                insert into rejected_order
                    (source_order_id, reason, rejected_at)
                values (?, ?, current_timestamp)
                """,
                order.id(),
                "Unsupported market"
            );
        }
    };
}
~~~

Classifier có thể định tuyến rõ ràng:

~~~java
writer.setClassifier(order -> {
    if (order.market() == null) {
        return rejectedOrderWriter;
    }

    return switch (order.market()) {
        case DOMESTIC -> domesticWriter;
        case INTERNATIONAL -> internationalWriter;
    };
});
~~~

Reject writer cần lưu đủ thông tin để tìm lại nguồn, chẳng hạn source file/batch ID, business key, lỗi và thời điểm. Nếu payload nhạy cảm, lưu đúng phần dữ liệu được phép và áp dụng retention phù hợp.

Reject writer là một route nghiệp vụ. Nó khác SkipListener, vốn được gọi khi Spring Batch quyết định bỏ qua item do exception. Có thể dùng cả hai, nhưng tránh ghi cùng một record hai lần.

## 7. Lỗi trong classifier được xử lý ở write phase

Classifier được gọi bên trong ClassifierCompositeItemWriter.write(). Nếu classifier ném exception, exception truyền ra khỏi writer và step xem đó là lỗi ở write phase.

Ví dụ:

~~~java
writer.setClassifier(order -> {
    if (order.market() == null) {
        throw new UnroutableOrderException(
            "Missing market for order " + order.id()
        );
    }
    return writerFor(order.market());
});
~~~

Nếu UnroutableOrderException được khai báo là skip exception, Spring Batch có thể bỏ qua item theo skip policy. Nếu không được phép skip, exception làm step thất bại sau khi retry policy (nếu có) đã được áp dụng.

Đừng bắt exception trong classifier rồi trả về một writer mặc định chỉ để job tiếp tục. Cách đó có thể ghi item vào sai bảng hoặc sai hệ thống. Nếu có fallback route, đặt tên và mục đích của nó rõ ràng, ví dụ unknownMarketWriter.

## 8. Lỗi từ delegate writer

Sau khi classifier chọn writer, delegate có thể thất bại vì:

- Lỗi validation hoặc constraint cho một record.
- Duplicate key hoặc dữ liệu xung đột.
- Database connection timeout hoặc deadlock.
- File không thể mở/ghi hoặc hết dung lượng.
- HTTP service trả lỗi hoặc timeout.
- Cấu hình writer sai hoặc thiếu resource.

Phân loại lỗi theo nguyên nhân:

| Nhóm lỗi | Ví dụ | Xử lý thường phù hợp |
| --- | --- | --- |
| Dữ liệu record không hợp lệ | Field bắt buộc thiếu, route không hỗ trợ | Skip hoặc quarantine nếu được phép |
| Lỗi tạm thời | Deadlock, connection reset, service unavailable | Retry có giới hạn |
| Lỗi cấu hình | Thiếu writer, sai table, thiếu output path | Fail nhanh |
| Lỗi hệ thống lâu dài | Hết disk, schema không tương thích | Thường fail và xử lý nguyên nhân |
| Lỗi không xác định | Runtime exception không được phân loại | Fail và điều tra |

Không cấu hình skip cho một superclass quá rộng như Exception chỉ để job không dừng. Làm vậy có thể che giấu lỗi lập trình, lỗi cấu hình hoặc lỗi hạ tầng khiến nhiều item bị mất.

## 9. Cấu hình skip cho lỗi phân loại

Spring Batch cho phép cấu hình skip exception ở step:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .faultTolerant()
    .skip(UnroutableOrderException.class)
    .skipLimit(50)
    .build();
~~~

Trong ví dụ, tối đa 50 item gây UnroutableOrderException có thể bị skip. Nếu vượt giới hạn, step thất bại. skipLimit là giới hạn tổng cho các skip trong step, không phải một giới hạn riêng cho từng loại exception hoặc riêng write phase.

Spring Batch có thể áp dụng skip cho lỗi xảy ra ở read, process hoặc write. Hãy xác định exception thực tế phát sinh ở phase nào và test bằng job thật; không suy ra từ tên exception rằng nó chỉ xuất hiện ở một phase.

Nếu route sai là lỗi nghiêm trọng của cả file, không cấu hình skip cho exception đó. Để step fail giúp phát hiện producer/schema/configuration drift sớm.

## 10. Skip limit được tính như thế nào?

skipLimit(n) giới hạn tổng số item bị bỏ qua trong step. Khi đã đạt giới hạn và phát sinh thêm một lỗi thuộc nhóm được skip, step sẽ thất bại.

Ví dụ skipLimit(3):

~~~text
Item 10 -> skip count 1
Item 21 -> skip count 2
Item 35 -> skip count 3
Item 44 -> lỗi tiếp theo -> step FAILED
~~~

Các skip ở read, process và write cùng đóng góp vào skip count. Vì vậy, nếu step đã skip nhiều lỗi parse ở reader, số lỗi phân loại còn được phép skip sẽ ít hơn.

Đặt limit theo chất lượng dữ liệu và SLA. Limit quá lớn có thể làm job hoàn tất dù phần lớn dữ liệu sai; limit quá nhỏ có thể khiến một batch có vài record lỗi hợp lệ không thể hoàn thành.

## 11. Kết hợp retry và skip

Retry dành cho lỗi có khả năng tự hết. Skip dành cho item không thể xử lý theo quy tắc hiện tại nhưng nghiệp vụ cho phép bỏ qua.

Ví dụ:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(UnroutableOrderException.class)
    .skipLimit(50)
    .build();
~~~

Ở đây:

- UnroutableOrderException được skip theo chính sách dữ liệu.
- TransientDataAccessException được retry theo giới hạn.
- Các exception không nằm trong retry/skip policy làm step thất bại.

Khi một exception vừa được cấu hình retry vừa được cấu hình skip, Spring Batch thử retry trước; sau khi retry policy hết khả năng thử lại, skip policy mới quyết định có bỏ qua item hay không. Hãy tránh chồng lấn policy nếu không có lý do rõ ràng.

Không retry một lỗi route cố định. Cùng một item với cùng dữ liệu thường sẽ tiếp tục không có route ở lần thử tiếp theo.

## 12. Dùng SkipListener để ghi nhận item bị skip

SkipListener cho phép ứng dụng nhận thông tin về item bị bỏ qua ở từng phase:

- onSkipInRead(Throwable): không tạo được item từ nguồn.
- onSkipInProcess(item, Throwable): item lỗi khi processor xử lý.
- onSkipInWrite(item, Throwable): item lỗi khi writer ghi.

Ví dụ:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedOrders;

    public OrderSkipListener(RejectedOrderRepository rejectedOrders) {
        this.rejectedOrders = rejectedOrders;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Could not read an order", throwable);
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        rejectedOrders.record(item.id(), "PROCESS", throwable);
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        rejectedOrders.record(item.id(), "WRITE", throwable);
    }
}
~~~

Đăng ký listener bằng listener(orderSkipListener) trên step builder. Trong code thực tế, generic input/output của listener phải khớp với step. Nếu reader trả OrderInput và processor trả Order, onSkipInProcess nhận input, còn onSkipInWrite nhận output.

Skip listener phù hợp để audit và thống kê. Nếu cần lưu record lỗi bền vững, hãy ghi bằng resource tham gia transaction phù hợp hoặc dùng cơ chế quarantine riêng. Không chỉ log rồi giả định record có thể được khôi phục sau này.

## 13. SkipListener khác với ItemWriteListener

Hai listener này có mục đích khác nhau:

| Listener | Callback | Ý nghĩa |
| --- | --- | --- |
| ItemWriteListener | beforeWrite, afterWrite, onWriteError | Theo dõi một lần gọi writer/chunk |
| SkipListener | onSkipInWrite | Ghi nhận item cụ thể mà framework quyết định bỏ qua |

onWriteError thường chỉ biết exception và chunk được gửi vào writer; nó không tự cho biết item nào gây lỗi. onSkipInWrite nhận item đã được xác định là item bị skip.

Với ClassifierCompositeItemWriter, delegate được gọi theo từng item, nên exception có thể xuất hiện ngay tại item đang định tuyến. Dù vậy, transaction vẫn ở phạm vi chunk; việc xác định item không có nghĩa mỗi item có transaction riêng.

## 14. Write-phase skip và rollback của chunk

Trong chunk-oriented step, writer được gọi trong transaction chunk. Nếu một delegate thất bại, mặc định step rollback transaction theo exception policy. Các item trong chunk có thể phải được xử lý lại.

Với writer nhận cả chunk, framework không phải lúc nào cũng biết item nào gây lỗi. Trong fault-tolerant step, Spring Batch có thể rollback rồi kiểm tra lại item riêng lẻ để xác định item gây lỗi và áp dụng skip. Chi tiết đường thực thi phụ thuộc writer, rollback policy và phiên bản framework.

ClassifierCompositeItemWriter vốn gọi delegate cho từng item trong vòng lặp của nó, vì vậy exception từ một delegate xảy ra trong lúc xử lý một item cụ thể. Tuy nhiên, exception vẫn thoát khỏi lời gọi write(chunk) và làm chunk đi qua cơ chế rollback/retry/skip của step.

Không coi việc một delegate đã chạy thành công là bằng chứng side effect của nó đã commit. Nếu transaction rollback, database write có thể bị hoàn tác; file hoặc remote call có thể không được hoàn tác.

## 15. Delegate có thể được gọi lại khi retry hoặc write skip

Giả sử chunk có ba item:

~~~text
Chunk: A, B, C

Lần gọi đầu:
  A -> route writer thành công
  B -> route writer ném exception
  C -> chưa được xử lý

Chunk rollback
Retry/scan theo fault-tolerant policy:
  A có thể được gửi lại
  B được kiểm tra và có thể bị skip
  C được gửi khi framework tiếp tục xử lý
~~~

Số lần gọi thực tế phụ thuộc retry/skip configuration và cách writer được gọi trong quá trình scan. Điều cần thiết là thiết kế delegate an toàn khi được gọi lại.

Database writer nên dùng unique key hoặc upsert khi phù hợp. API writer nên gửi idempotency key. File writer cần có checkpoint/transactional buffer và đường restart phù hợp. Không tạo một external side effect không thể lặp an toàn bên trong delegate rồi giả định writer chỉ chạy một lần.

## 16. Phân biệt lỗi dữ liệu với lỗi hạ tầng

Một lỗi có thể xảy ra trong delegate nhưng không nên skip:

- DataAccessResourceFailureException: datasource không truy cập được.
- Timeout tới hệ thống ngoài.
- File system hết dung lượng.
- Connection pool cạn.
- Lỗi authentication/authorization do cấu hình sai.

Nếu skip những lỗi này, step có thể đánh dấu item là đã xử lý dù dữ liệu chưa được ghi ở đích. Điều đó gây mất dữ liệu âm thầm.

Ngược lại, một lỗi như UnroutableOrderException có thể skip nếu:

- Lỗi chỉ ảnh hưởng item hiện tại.
- Các item khác vẫn có thể xử lý độc lập.
- Record bị skip được audit hoặc quarantine theo yêu cầu.
- Chủ sở hữu dữ liệu chấp nhận xử lý lại sau.

Đặt exception type theo nguyên nhân nghiệp vụ, không chỉ theo nơi exception phát sinh. Một lỗi từ writer không tự động là lỗi có thể skip.

## 17. Fallback writer hay exception?

Khi classifier không tìm được route, lựa chọn giữa fallback và exception phụ thuộc hợp đồng:

| Tình huống | Cách xử lý |
| --- | --- |
| Có nhóm OTHER được hỗ trợ chính thức | Route tới otherWriter |
| Record không hợp lệ nhưng cần giữ lại | Route tới reject/quarantine writer |
| Record không hợp lệ và được phép loại bỏ | Ném exception riêng, cấu hình skip và audit |
| Route lạ cho thấy producer đã phá schema | Fail job |
| Route lạ do cấu hình thiếu writer | Fail nhanh, không skip |

Fallback phải có ý nghĩa nghiệp vụ. Không dùng writer mặc định để ghi mọi route không biết vào một bảng bình thường, vì như vậy dữ liệu sai có thể bị coi là hợp lệ.

## 18. ClassifierCompositeItemWriter và hiệu năng

ClassifierCompositeItemWriter định tuyến từng item bằng cách gọi delegate cho từng item. Điều này làm code đơn giản và giúp lỗi từ một delegate gắn với item đang xử lý, nhưng có thể giảm hiệu quả batch nếu delegate vốn được thiết kế để ghi theo chunk lớn.

Ví dụ một JdbcBatchItemWriter nhận chunk singleton cho mỗi order sẽ không gom được toàn bộ 100 order thành một batch JDBC duy nhất như khi nhận cả chunk:

~~~text
Chunk có 100 item
  |
  +-- writer A.write(chunk gồm 1 item)
  +-- writer B.write(chunk gồm 1 item)
  +-- writer A.write(chunk gồm 1 item)
  +-- ...
~~~

Nếu throughput quan trọng, có thể viết routing writer tùy chỉnh để gom item theo route, rồi gọi mỗi delegate một lần với chunk của nhóm đó. Cần lưu ý cách gom nhóm có thể thay đổi thứ tự ghi giữa các route.

## 19. Gom item theo route trước khi gọi delegate

Ví dụ ý tưởng cho một writer gom nhóm:

~~~java
public class GroupingOrderWriter implements ItemWriter<Order> {

    private final Function<Order, Market> classifier;
    private final Map<Market, ItemWriter<Order>> delegates;

    public GroupingOrderWriter(
            Function<Order, Market> classifier,
            Map<Market, ItemWriter<Order>> delegates) {
        this.classifier = classifier;
        this.delegates = delegates;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        Map<Market, List<Order>> groups = new LinkedHashMap<>();

        for (Order order : chunk) {
            Market market = classifier.apply(order);
            if (market == null || !delegates.containsKey(market)) {
                throw new UnroutableOrderException(
                    "No writer for order " + order.id()
                );
            }
            groups.computeIfAbsent(market, key -> new ArrayList<>())
                .add(order);
        }

        for (Map.Entry<Market, List<Order>> entry : groups.entrySet()) {
            delegates.get(entry.getKey())
                .write(new Chunk<>(entry.getValue()));
        }
    }
}
~~~

Đây là cấu trúc minh họa; implementation production cần quản lý generic types, exception attribution và ItemStream lifecycle. LinkedHashMap giữ thứ tự route xuất hiện lần đầu trong chunk, còn thứ tự item bên trong mỗi nhóm được giữ.

Gom nhóm làm thay đổi thứ tự toàn cục. Ví dụ chunk A1, B1, A2 sẽ được ghi thành A1, A2 rồi B1. Nếu thứ tự giữa các route có ý nghĩa, không gom nhóm hoặc dùng một thiết kế writer khác bảo toàn thứ tự.

## 20. Đăng ký ItemStream của delegate

ClassifierCompositeItemWriter là writer định tuyến; step không thể tự suy ra mọi writer delegate có thể được chọn từ classifier để quản lý lifecycle của chúng. Nếu delegate triển khai ItemStream, hãy đăng ký các delegate với step:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .stream(domesticWriter)
    .stream(internationalWriter)
    .build();
~~~

Điều này đặc biệt quan trọng với FlatFileItemWriter, reader/writer giữ cursor hoặc custom writer mở resource trong open(). Nếu không được mở, cập nhật state hoặc đóng đúng lifecycle, job có thể lỗi khi ghi, không flush dữ liệu hoặc rò rỉ resource.

Nếu dùng wrapper quanh delegate, wrapper cần forward open, update, close hoặc đăng ký delegate stream trực tiếp. Chọn một owner rõ ràng để callback không bị gọi trùng.

## 21. Step scope và nhiều route

Nếu mỗi route cần tham số riêng từ job/step execution, có thể khai báo writer delegate StepScope. Ví dụ mỗi writer nhận một output path khác nhau hoặc một tenant parameter.

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> domesticWriter(
        @Value("#{jobParameters['domesticOutput']}") Resource output) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("domesticOrderWriter")
        .resource(output)
        .lineAggregator(OrderLineAggregator::toLine)
        .build();
}
~~~

Classifier nên được xây dựng với các proxy/dependency tương ứng và chỉ truy cập target khi step scope đã hoạt động. Không khởi tạo hoặc gọi target step-scoped trong lúc application context chưa có StepExecution.

Mỗi delegate cần tên stream duy nhất trong step nếu nó lưu execution context. Hai writer stateful dùng cùng tên có thể gây xung đột key checkpoint.

## 22. Retry policy cho delegate lỗi tạm thời

Ví dụ một route ghi database có thể gặp deadlock hoặc lỗi kết nối tạm thời. Có thể retry các exception được xác định là transient:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(UnroutableOrderException.class)
    .skipLimit(50)
    .build();
~~~

Danh sách exception cụ thể phải phù hợp với database/driver và Spring version đang dùng. Một số exception transient có thể nằm trong hierarchy của exception khác; tránh cấu hình lặp hoặc quá rộng mà không có chủ đích.

Nếu lỗi hạ tầng vẫn tồn tại sau retry limit, step nên thất bại để scheduler hoặc operator xử lý. Skip một lỗi kết nối không giúp dữ liệu được ghi.

## 23. Custom SkipPolicy khi quy tắc phức tạp

Khi skip phụ thuộc số lượng lỗi, loại route hoặc context, có thể dùng SkipPolicy tùy chỉnh:

~~~java
public class RoutingSkipPolicy implements SkipPolicy {

    private final long maxUnroutable;

    public RoutingSkipPolicy(long maxUnroutable) {
        this.maxUnroutable = maxUnroutable;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof UnroutableOrderException) {
            if (skipCount < maxUnroutable) {
                return true;
            }
            throw new SkipLimitExceededException(
                maxUnroutable,
                throwable
            );
        }

        return false;
    }
}
~~~

Sau đó gắn policy vào step bằng skipPolicy. Custom policy cần xử lý đúng mọi exception và giới hạn; trả false có nghĩa exception không được skip. Không trả true cho mọi RuntimeException.

Nếu quy tắc chỉ là skip một exception type với một giới hạn cố định, DSL skip và skipLimit dễ đọc và ít lỗi hơn.

## 24. Kiểm thử classifier độc lập

Classifier là logic thuần nên có thể unit test mà không cần Spring Batch context:

~~~java
@Test
void routesDomesticOrderToDomesticWriter() {
    ItemWriter<Order> domestic = mock(ItemWriter.class);
    ItemWriter<Order> international = mock(ItemWriter.class);

    Classifier<Order, ItemWriter<? super Order>> classifier =
        order -> order.market() == Market.DOMESTIC
            ? domestic
            : international;

    assertThat(classifier.classify(domesticOrder))
        .isSameAs(domestic);
    assertThat(classifier.classify(internationalOrder))
        .isSameAs(international);
}
~~~

Test thêm cho:

- Mọi enum/route được hỗ trợ đều có writer.
- Giá trị null hoặc unknown được xử lý theo policy.
- Route không phụ thuộc vào mutable state của classifier.
- Cùng item luôn cho cùng route.
- Không có route nào trả null.

Nếu classifier dùng bảng mapping, test tính đầy đủ của mapping để phát hiện một loại mới được thêm vào enum nhưng chưa có writer.

## 25. Kiểm thử fan-out định tuyến của writer

Unit test cho ClassifierCompositeItemWriter nên xác nhận từng item được chuyển tới đúng delegate:

~~~java
@Test
void sendsEachItemOnlyToItsClassifiedWriter() throws Exception {
    ItemWriter<Order> domestic = mock(ItemWriter.class);
    ItemWriter<Order> international = mock(ItemWriter.class);

    ClassifierCompositeItemWriter<Order> writer =
        new ClassifierCompositeItemWriter<>();
    writer.setClassifier(order ->
        order.market() == Market.DOMESTIC
            ? domestic
            : international
    );

    writer.write(new Chunk<>(List.of(
        domesticOrder,
        internationalOrder,
        secondDomesticOrder
    )));

    verify(domestic, times(2)).write(any());
    verify(international, times(1)).write(any());
}
~~~

Do writer định tuyến theo từng item, mỗi delegate có thể được gọi nhiều lần trong một lần write(chunk). Nếu cần xác nhận đúng item, dùng ArgumentCaptor hoặc verify chunk singleton chứa business key mong đợi.

Thêm test khi classifier ném UnroutableOrderException: không delegate nào được gọi cho item lỗi và exception được truyền ra ngoài.

## 26. Kiểm thử skip trong write phase

Để kiểm thử skip thực tế, hãy chạy một step với reader cung cấp một số order hợp lệ và một order không có route. Cấu hình skip cho UnroutableOrderException, đồng thời gắn SkipListener.

Các assertion:

- Step hoàn tất nếu số lỗi nằm trong skip limit.
- Các order hợp lệ được ghi tới đúng delegate.
- Order không route không bị ghi vào writer nghiệp vụ.
- SkipListener.onSkipInWrite nhận đúng business key và exception.
- Skip count trong StepExecution bằng số item bị bỏ qua.
- Khi vượt skip limit, step kết thúc FAILED.

Ví dụ dữ liệu:

~~~text
Order 1 -> DOMESTIC
Order 2 -> UNKNOWN
Order 3 -> INTERNATIONAL
~~~

Kết quả mong đợi: order 1 đến domestic writer, order 3 đến international writer, order 2 được skip/audit theo policy. Không kiểm tra chỉ bằng job status; xác nhận dữ liệu thực ở từng đích.

## 27. Kiểm thử lỗi delegate và rollback

Tạo một delegate writer cố ý thất bại với một business key cụ thể:

~~~java
public class FailingDomesticWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        if (chunk.getItems().stream()
                .anyMatch(order -> order.id() == 102L)) {
            throw new InvalidDomesticOrderException(
                "Order 102 is invalid"
            );
        }
    }
}
~~~

Integration test cần xác nhận:

1. Writer delegate được chọn đúng.
2. Exception xuất hiện ở write phase.
3. Chunk rollback theo transaction policy.
4. Nếu exception được skip, chỉ item hợp lệ được ghi cuối cùng.
5. Nếu exception không được skip, step thất bại và dữ liệu của chunk chưa commit không còn trong bảng transactional.

Với external delegate, không thể chỉ assert database rollback. Cần mock service hoặc broker để xác nhận idempotency và side effect sau retry.

## 28. Kiểm thử retry và idempotency của route

Một writer có thể thất bại tạm thời ở lần đầu rồi thành công ở lần retry. Test nên mô phỏng:

~~~text
Order 201 -> route INTERNATIONAL
Attempt 1 -> internationalWriter timeout
Attempt 2 -> internationalWriter thành công
~~~

Xác nhận:

- Classifier chọn cùng route ở mọi lần thử.
- Business key/idempotency key không thay đổi.
- Không có duplicate row/event sau retry.
- Retry count được ghi nhận đúng.
- Khi retry limit hết, step fail hoặc skip đúng policy.

Nếu classifier phụ thuộc trạng thái mutable như attemptNumber hoặc kết quả API, route có thể thay đổi giữa lần thử. Hãy tính route từ dữ liệu ổn định hoặc lưu quyết định route bền vững nếu nghiệp vụ yêu cầu.

## 29. Theo dõi lỗi và skip trong production

Một batch có routing nên theo dõi số item theo route và số lỗi:

- Số item được phân loại theo từng route.
- Số item không có route.
- Số lỗi của từng delegate.
- Số retry và số skip theo phase.
- Thời gian xử lý của từng delegate.
- Số record trong quarantine/reject store.
- Tỷ lệ item lỗi trên tổng item.

Log nên có job execution ID, step execution ID, route, business key và exception type. Không log toàn bộ payload nếu chứa thông tin nhạy cảm.

Nếu tỷ lệ unroutable tăng đột ngột, có thể producer đã thêm loại mới hoặc contract bị thay đổi. Alert theo ngưỡng giúp phát hiện sớm. Đừng tự động tăng skip limit khi job fail; trước hết xác định lỗi là dữ liệu hợp lệ mới, schema drift hay cấu hình thiếu delegate.

## 30. Những lỗi thường gặp khi phân loại và skip

**Trả về null khi không có route:** lỗi runtime khó hiểu và không có ngữ nghĩa nghiệp vụ. Ném exception riêng hoặc route tới reject writer.

**Skip mọi RuntimeException:** có thể che lỗi cấu hình, database hoặc lập trình. Chỉ skip lỗi record được xác định rõ.

**Retry lỗi phân loại cố định:** cùng dữ liệu sẽ tiếp tục không có route. Dùng skip/quarantine hoặc fail.

**Skip lỗi kết nối:** item có thể bị đánh dấu bỏ qua dù chưa ghi vào đích. Retry hoặc fail lỗi hạ tầng.

**Classifier gọi API/database cho từng item:** tạo N+1 calls và route không ổn định khi retry. Enrich trước hoặc dùng lookup có kiểm soát.

**Cho rằng mỗi delegate nhận một phần chunk:** ClassifierCompositeItemWriter định tuyến theo từng item và gọi writer theo item. Cân nhắc writer gom nhóm nếu cần batch efficiency.

**Quên đăng ký ItemStream delegate:** file/cursor writer có thể không được open/update/close. Đăng ký delegate stream với step.

**Nhầm SkipListener với ItemWriteListener:** write error listener theo dõi lần gọi writer; SkipListener ghi nhận item thực sự bị bỏ qua.

**Không kiểm tra skip limit:** job có thể bỏ qua quá nhiều record. Đặt limit theo chất lượng dữ liệu và kiểm thử trường hợp vượt ngưỡng.

**Không audit record bị skip:** dữ liệu lỗi không thể truy vết hoặc xử lý lại. Lưu business key, source và lý do.

**Không idempotent khi retry:** một delegate có thể đã tạo side effect trước khi lỗi được phát hiện. Dùng unique key, upsert, idempotency key hoặc outbox.

**Dùng một writer chung không thread-safe:** nhiều partition có thể gọi delegate đồng thời. Thiết kế writer theo concurrency model của step.

## 31. Quy trình thiết kế lỗi phân loại và skip trong production

Trước tiên, xác định route hợp lệ và nguồn dữ liệu dùng để phân loại. Dùng enum hoặc value object thay cho chuỗi tùy ý; classifier nên thuần, xác định và không gọi dịch vụ bên ngoài. Với route không được hỗ trợ, chọn rõ fallback, quarantine, skip hoặc fail theo hợp đồng dữ liệu.

Tiếp theo, tạo exception riêng cho lỗi phân loại và phân loại exception từ delegate theo nguyên nhân. Cấu hình skip cho lỗi record được phép loại bỏ, retry cho lỗi hạ tầng tạm thời và để lỗi cấu hình/lỗi nghiêm trọng làm step thất bại. Đặt skip limit tổng cho step và gắn SkipListener để audit item bị bỏ qua. Đảm bảo các delegate ItemStream được đăng ký lifecycle với step.

Cuối cùng, test classifier độc lập, test mỗi route, test unknown route, test write exception, rollback, retry, skip limit và ItemStream lifecycle. Kiểm tra dữ liệu thực ở từng đích và idempotency khi delegate được gọi lại. Theo dõi route count, retry, skip và quarantine trong production để phát hiện schema drift hoặc lỗi đích ghi.

Lỗi phân loại và skip là một phần của thiết kế routing, không chỉ là cấu hình exception. ClassifierCompositeItemWriter chọn một delegate cho mỗi item; classifier error và delegate error phải có chính sách riêng. Khi route ổn định, exception được phân loại đúng, skip được giới hạn và item lỗi được audit, job có thể tiếp tục với record hợp lệ mà vẫn làm lộ những lỗi hạ tầng hoặc cấu hình cần xử lý.
