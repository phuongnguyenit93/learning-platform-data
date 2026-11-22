# Skip với output có thể gây thiếu dữ liệu

Trong Spring Batch, skip cho phép một step tiếp tục xử lý khi gặp một số lỗi được xác định là có thể bỏ qua. Cơ chế này hữu ích khi một vài item đầu vào bị lỗi nhưng phần dữ liệu còn lại vẫn có thể xử lý. Tuy nhiên, nếu output được kỳ vọng phải chứa đầy đủ mọi bản ghi nguồn, skip có thể làm kết quả thiếu dữ liệu trong khi job vẫn kết thúc với trạng thái thành công.

Ví dụ, một file có 10.000 đơn hàng nhưng 25 dòng bị lỗi validation. Nếu step được cấu hình skip các lỗi đó, writer có thể chỉ ghi 9.975 đơn hàng. Job vẫn có thể có BatchStatus COMPLETED vì các lỗi đều được xử lý theo chính sách. Người tiêu thụ output nếu chỉ nhìn trạng thái job có thể tưởng rằng đã nhập đủ 10.000 đơn hàng.

Vì vậy, quyết định dùng skip không chỉ là quyết định kỹ thuật. Cần xác định rõ dữ liệu nào được phép bỏ qua, ai nhận thông tin về item bị skip, output được xem là đầy đủ theo tiêu chí nào và job có được phép công bố kết quả khi có skip hay không.

## 1. Skip có ý nghĩa gì đối với output?

Trong chunk-oriented processing, reader đọc item, processor có thể chuyển đổi hoặc filter item, rồi writer ghi các item còn lại. Khi một exception được phân loại là skippable và skip limit chưa bị vượt, Spring Batch có thể bỏ qua item gây lỗi và tiếp tục xử lý.

Skip có thể xảy ra ở ba giai đoạn:

| Giai đoạn | Trường hợp | Tác động đến output |
|---|---|---|
| Read | Reader không thể đọc hoặc parse một record | Record không được tạo thành item để writer ghi |
| Process | Processor phát hiện item không hợp lệ và ném exception | Item không được chuyển tới writer |
| Write | Writer không thể ghi một item | Item bị bỏ qua theo skip policy; các item khác có thể tiếp tục được ghi |

Khi một item bị skip, item đó không xuất hiện trong output thành công thông thường của step. Nếu output là danh sách đơn hàng, file CSV, bảng database hoặc message được publish, kết quả có thể thiếu item tương ứng.

~~~mermaid
flowchart TD
    A[Input records] --> B[Reader]
    B --> C{Read được?}
    C -- Không, skippable --> S[Record bị skip]
    C -- Có --> D[Processor]
    D --> E{Process hợp lệ?}
    E -- Không, skippable --> S
    E -- Có --> F[Writer]
    F --> G{Write thành công?}
    G -- Không, skippable --> S
    G -- Có --> O[Output]
    S --> R[SkipListener / reject record]
    O --> V[Đối soát và quyết định công bố]
    R --> V
~~~

Skip không có nghĩa Spring Batch xóa dữ liệu nguồn. Nó có nghĩa item không được xử lý theo đường thành công của step. Nếu nghiệp vụ cần xử lý lại item đó, ứng dụng phải lưu đủ thông tin để sửa và chạy lại.

## 2. BatchStatus COMPLETED không bảo đảm output đầy đủ

Nếu step được cấu hình skip và số item bị skip không vượt giới hạn, step có thể hoàn thành bình thường. Khi đó:

- BatchStatus của step có thể là COMPLETED.
- Job có thể tiếp tục các step sau và cuối cùng có BatchStatus COMPLETED.
- Skip count vẫn lớn hơn 0.
- Output có thể ít item hơn input hoặc thiếu một phần dữ liệu nghiệp vụ.

Ví dụ:

| Chỉ số | Giá trị |
|---|---:|
| Số record nguồn | 10.000 |
| Record đọc được | 10.000 |
| Record bị skip khi process | 20 |
| Record bị skip khi write | 5 |
| Record được ghi thành công | 9.975 |
| BatchStatus | COMPLETED (nếu các điều kiện khác đều thành công) |

Không nên dùng riêng BatchStatus để khẳng định dữ liệu đã được nhập đầy đủ. Cần xem read/write/skip counts, reject records, đối soát theo khóa nghiệp vụ và quy tắc completeness của output.

Nếu nghiệp vụ yêu cầu mọi record phải được xử lý, một skip cũng có thể là lỗi nghiêm trọng. Nếu nghiệp vụ cho phép bỏ một số record, job vẫn cần công bố rõ số lượng và lý do bị bỏ qua.

## 3. Phân biệt skip với filter

Processor có thể trả về null để loại item khỏi luồng xử lý. Đây là filter, không phải skip:

~~~java
@Bean
ItemProcessor<OrderInput, Order> filterCancelledOrders() {
    return input -> {
        if (input.status().equals("CANCELLED")) {
            return null;
        }
        return mapToOrder(input);
    };
}
~~~

Trong trường hợp này, item bị filter vì quy tắc nghiệp vụ chủ động loại nó, không được chuyển tới writer và filter count được tăng. SkipListener không được gọi cho item bị filter.

Ngược lại, nếu processor ném exception được cấu hình skippable, item được tính là process skip. Hai trường hợp cùng làm output ít hơn input nhưng có ý nghĩa khác nhau:

| Hành vi | Ý nghĩa | Cần ghi nhận |
|---|---|---|
| Processor trả null | Item bị loại có chủ đích theo quy tắc filter | Lý do filter nếu cần audit |
| Exception bị skip | Item không thể xử lý theo đường thông thường | Item, exception và lý do skip |

Không dùng null để che giấu dữ liệu lỗi nếu nghiệp vụ cần điều tra. Ngược lại, không ném exception cho một điều kiện loại bỏ bình thường nếu đó chỉ là filter được định nghĩa rõ.

## 4. Cấu hình skip có kiểm soát

Trong Spring Batch 5, có thể cấu hình skip cho một số loại exception và đặt giới hạn tổng:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        ImportSkipListener skipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skip(FlatFileParseException.class)
            .noSkip(FatalConfigurationException.class)
            .skipLimit(25)
            .listener(skipListener)
            .build();
}
~~~

Trong ví dụ, InvalidOrderException và FlatFileParseException được phép skip; FatalConfigurationException không được skip; tổng skip count của step bị giới hạn ở 25; SkipListener nhận thông tin item/lỗi để ứng dụng ghi nhận.

Skip limit được tính chung cho các giai đoạn read, process và write, không phải một giới hạn riêng cho mỗi giai đoạn. Khi số lượng skip vượt giới hạn, step thất bại. Hãy kiểm tra API của phiên bản Spring Batch đang dùng khi cấu hình classifier hoặc SkipPolicy tùy chỉnh.

Chỉ khai báo exception có ý nghĩa rõ ràng. Không nên skip mọi Exception hoặc RuntimeException vì điều đó có thể biến lỗi lập trình, lỗi database hoặc lỗi cấu hình thành các bản ghi âm thầm bị bỏ qua.

## 5. Chọn lỗi nào được phép skip?

Một exception phù hợp để skip thường là lỗi riêng của item, có thể nhận diện và xử lý độc lập mà không làm mất tính toàn vẹn của các item khác.

Ví dụ thường có thể cân nhắc skip:

- Một dòng CSV có định dạng sai và có thể lưu nguyên dòng để sửa sau.
- Một bản ghi thiếu trường bắt buộc theo quy tắc nghiệp vụ.
- Một item tham chiếu tới mã danh mục không tồn tại và nghiệp vụ cho phép đưa vào danh sách từ chối.
- Một bản ghi vi phạm constraint riêng lẻ, nếu việc bỏ nó được nghiệp vụ cho phép và output được đối soát.

Các lỗi thường không nên skip:

- Database mất kết nối hoặc hết connection.
- API thanh toán không sẵn sàng.
- Lỗi cấu hình khiến toàn bộ job không thể xử lý đúng.
- Lỗi lập trình như NullPointerException không được dự kiến.
- Lỗi làm mất khả năng xác định item nào đã được ghi thành công.
- Lỗi cho thấy dữ liệu đầu vào bị sai phạm vi hoặc không đáng tin cậy trên diện rộng.

Một lỗi hạ tầng thường cần retry có giới hạn hoặc làm step thất bại, không phải bỏ item. Nếu database tạm thời không ghi được 100 đơn hàng, skip cả 100 đơn hàng sẽ tạo output thiếu nghiêm trọng nhưng có thể che giấu sự cố.

## 6. Ghi nhận item bị skip bằng SkipListener

Khi output có thể thiếu dữ liệu, ứng dụng cần biết chính xác item nào bị bỏ qua và vì sao. Spring Batch cung cấp SkipListener với callback riêng cho read, process và write.

~~~java
public class ImportSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedOrders;

    public ImportSkipListener(RejectedOrderRepository rejectedOrders) {
        this.rejectedOrders = rejectedOrders;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        rejectedOrders.saveReadFailure(
                extractSourceLocation(throwable),
                throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable throwable) {
        rejectedOrders.save(
                item.orderId(),
                item.customerId(),
                "PROCESS",
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable throwable) {
        rejectedOrders.save(
                item.orderId(),
                item.customerId(),
                "WRITE",
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }
}
~~~

Ví dụ này dùng repository minh họa. Trong ứng dụng thực tế:

- Callback read không có item vì reader chưa tạo được item; cần lấy số dòng, offset hoặc source location từ exception/reader context.
- Callback process nhận item đầu vào.
- Callback write nhận item đầu ra của processor.
- Nên lưu source ID, batch ID, giai đoạn lỗi, loại exception và thông tin đủ để sửa hoặc chạy lại.
- Không lưu toàn bộ stack trace hoặc payload nhạy cảm vào bảng reject nếu không có chính sách bảo mật và dung lượng phù hợp.

Spring Batch gọi SkipListener theo cơ chế giúp callback được thực hiện một lần cho item bị skip ngay trước khi chunk commit, tránh việc callback bị lặp đơn thuần do rollback/retry nội bộ. Tuy vậy, thao tác ghi reject vẫn cần tham gia transaction phù hợp và có khóa chống trùng nếu quy trình có thể được restart hoặc chạy lại.

## 7. Tạo reject table thay vì bỏ mất record

Với output database, một mô hình phổ biến là ghi các item hợp lệ vào bảng đích và ghi item bị skip vào bảng reject. Nhờ đó, output thành công có thể được sử dụng, còn record lỗi vẫn được giữ để điều tra.

Ví dụ schema:

~~~sql
CREATE TABLE import_reject (
    batch_id       VARCHAR(80) NOT NULL,
    source_id      VARCHAR(100) NOT NULL,
    stage          VARCHAR(20) NOT NULL,
    error_code     VARCHAR(100) NOT NULL,
    error_message  VARCHAR(1000),
    created_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (batch_id, source_id, stage)
);
~~~

Khóa duy nhất theo batch, source ID và stage giúp hạn chế tạo nhiều reject record cho cùng lỗi khi job restart hoặc xử lý lại. Nếu cùng một source ID có thể lỗi ở nhiều lần thử với nguyên nhân khác nhau, cần xác định rõ muốn lưu lịch sử từng lần thử hay chỉ lưu kết quả reject cuối cùng.

Không nên chỉ lưu số lượng skip. Khi cần xử lý lại, người vận hành cần biết record nào bị bỏ qua và có đủ thông tin để tìm lại dữ liệu nguồn. Nếu read skip xảy ra trước khi tạo item, cần lưu vị trí nguồn hoặc raw line để có thể truy vết.

## 8. Output file: ghi dữ liệu hợp lệ và file lỗi riêng

Với batch nhập/xuất file, có thể tạo hai output:

- File chính chứa các record được xử lý thành công.
- File reject chứa source ID, dòng nguồn, loại lỗi và lý do.

Ví dụ cấu trúc:

~~~text
output/
  orders-accepted.csv
  orders-rejected.csv
  orders-summary.json
~~~

File summary có thể ghi:

~~~json
{
  "batchId": "ORDERS-2026-11-14",
  "inputCount": 10000,
  "acceptedCount": 9975,
  "rejectedCount": 25,
  "status": "COMPLETED_WITH_REJECTS"
}
~~~

Đây là định dạng minh họa; ứng dụng cần định nghĩa schema summary ổn định. Với FlatFileItemWriter, file output thường được quản lý theo lifecycle của writer. Nếu job có thể restart, cần cấu hình state saving và dùng tên file ổn định theo batch. Không ghi file cuối cùng trực tiếp vào vị trí mà downstream đọc trước khi job hoàn tất và đối soát.

Một cách an toàn là ghi vào thư mục staging theo batch ID, hoàn tất cả file accepted/rejected/summary, kiểm tra số liệu rồi mới đổi tên hoặc publish manifest hoàn tất. Nếu job thất bại, downstream không coi output staging là kết quả chính thức.

## 9. Output message hoặc tích hợp hệ thống ngoài

Nếu writer publish message cho từng item, skip có thể khiến một số event không bao giờ được phát. Điều đó có thể làm hệ thống downstream thiếu dữ liệu mà không biết.

Các lựa chọn:

- Ghi item lỗi vào dead-letter topic hoặc reject store với event ID và nguyên nhân.
- Ghi outbox record trong cùng transaction với dữ liệu nghiệp vụ rồi publish sau commit.
- Dùng consumer inbox/deduplication để message giao lại không tạo side effect trùng.
- Công bố batch manifest cho biết số event dự kiến, số event đã phát và số event bị reject.
- Có quy trình replay item đã sửa sau khi lỗi được khắc phục.

Không nên bắt exception do broker mất kết nối rồi skip message. Đây thường là lỗi hạ tầng cần retry hoặc làm step thất bại. Skip chỉ nên áp dụng cho lỗi riêng của item mà nghiệp vụ cho phép bỏ qua và có cơ chế ghi nhận.

## 10. Đối soát để phát hiện output thiếu dữ liệu

Khi skip được cho phép, job cần có tiêu chí completeness rõ ràng. Không chỉ so sánh số dòng input và output vì một số item có thể bị filter hợp lệ, hoặc một item nguồn có thể tạo nhiều output.

Các phép đối soát hữu ích:

- Số record nguồn trong phạm vi batch.
- Số item được đọc thành công.
- Số item bị filter theo quy tắc nghiệp vụ.
- Số item bị skip khi read/process/write.
- Số item được writer ghi thành công.
- Số reject record đã lưu.
- Số khóa nghiệp vụ duy nhất trong output.
- Tổng tiền, số lượng hoặc checksum theo nhóm nghiệp vụ.

Ví dụ bảng đối soát:

| Chỉ số | Kết quả |
|---|---:|
| Input records | 10.000 |
| Filtered by business rule | 100 |
| Skipped | 25 |
| Expected accepted output | 9.875 |
| Actual accepted output | 9.875 |
| Reject records | 25 |
| Reconciliation | MATCH |

Phương trình đối soát phụ thuộc nghiệp vụ. Trong ví dụ đơn giản, mỗi record nguồn hoặc được filter, hoặc được skip, hoặc được chấp nhận. Khi có một-nhiều mapping, duplicate suppression hoặc aggregation, phải dùng khóa và tổng hợp phù hợp thay vì áp dụng một phép cộng đơn giản.

Nếu số liệu không khớp, job không nên công bố output là hoàn chỉnh. Có thể đánh dấu batch cần điều tra, chạy step đối soát thất bại hoặc giữ output trong staging.

## 11. Đặt ngưỡng skip theo mức độ quan trọng của dữ liệu

Skip limit giới hạn số item được phép bỏ qua trong một step, nhưng một giới hạn cố định không tự phản ánh mức độ nghiêm trọng nghiệp vụ. 25 lỗi có thể chấp nhận với file marketing nhưng không thể chấp nhận với bảng kê thanh toán.

| Chính sách | Khi phù hợp | Hành vi |
|---|---|---|
| Không cho phép skip | Dữ liệu bắt buộc đầy đủ, ví dụ sổ cái hoặc thanh toán | Không khai báo skip cho lỗi nghiệp vụ; step thất bại |
| Skip có giới hạn tuyệt đối | Có thể bỏ một số record lỗi riêng lẻ | Cấu hình skipLimit thấp và ghi reject |
| Skip theo tỷ lệ | Chất lượng dữ liệu biến động theo kích thước batch | Đối soát tỷ lệ reject ở step riêng trước khi publish |
| Skip nhưng cần phê duyệt | Kết quả được phép tạo nhưng cần người có trách nhiệm xác nhận | Tạo trạng thái pending review; chưa công bố |

SkipLimit là giới hạn số lượng trong fault-tolerant step. Nếu cần giới hạn theo tỷ lệ, ví dụ reject không vượt 0,1% input, hãy tính tỷ lệ trong bước đối soát sau khi step nhập hoàn tất. Không nên cố nhét quy tắc tỷ lệ vào một skip limit cố định nếu kích thước batch thay đổi lớn.

## 12. Đặt ExitStatus riêng khi có skip

Một step có thể hoàn thành với skip count lớn hơn 0. Nếu flow cần xử lý khác khi có reject, có thể đặt ExitStatus tùy chỉnh sau khi step kết thúc.

~~~java
public class SkipOutcomeListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Step completed with rejected items");
        }

        return null;
    }
}
~~~

Flow có thể chuyển sang bước đối soát hoặc phê duyệt:

~~~java
return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("COMPLETED_WITH_SKIPS").to(reconcileRejectsStep)
        .from(importStep)
            .on("COMPLETED").to(publishStep)
        .from(importStep)
            .on("*").fail()
        .end()
        .build();
~~~

Trong ví dụ, step có skip không đi thẳng tới bước publish. Nó đi qua bước đối soát reject trước. Cần định nghĩa rõ reconcileRejectsStep sẽ kết thúc thành công, chờ phê duyệt hay làm job thất bại nếu vượt ngưỡng. Mã ExitStatus tùy chỉnh không thay thế BatchStatus; step vẫn có thể có BatchStatus COMPLETED trong khi exit code là COMPLETED_WITH_SKIPS.

## 13. Không công bố output chưa hoàn chỉnh

Nếu downstream đọc output ngay khi file hoặc bảng được tạo, nó có thể tiêu thụ dữ liệu trước khi job biết rằng một số item bị skip hoặc đối soát thất bại.

~~~mermaid
flowchart TD
    A[Import step] --> B[Accepted output in staging]
    A --> C[Reject records]
    B --> D[Reconciliation step]
    C --> D
    D --> E{Completeness rules pass?}
    E -- Có --> F[Publish output / mark batch ready]
    E -- Không --> G[Hold batch for review]
~~~

Các kỹ thuật triển khai:

- Ghi dữ liệu vào bảng staging theo batch ID.
- Tạo file trong thư mục tạm theo batch ID.
- Lưu batch status riêng như PROCESSING, READY, REJECTED hoặc NEEDS_REVIEW.
- Chỉ đổi trạng thái READY sau khi đối soát thành công.
- Dùng unique key để publish cùng batch không tạo dữ liệu trùng.
- Downstream chỉ đọc batch có trạng thái READY.

Với database, việc chuyển từ staging sang bảng chính có thể là một transaction hoặc thao tác set-based sau khi đối soát. Với file, có thể dùng rename nguyên tử trong cùng filesystem và một manifest đánh dấu hoàn tất. Với message, cần outbox/manifest và quy tắc consumer rõ ràng.

## 14. Retry trước khi quyết định skip

Một lỗi tạm thời không nên bị biến thành skip chỉ vì writer thất bại lần đầu. Ví dụ database deadlock hoặc API timeout có thể phục hồi nếu thử lại. Nếu phân loại lỗi sai, job có thể hoàn thành với output thiếu dù item thực tế hoàn toàn có thể xử lý.

| Loại lỗi | Hành vi thường phù hợp |
|---|---|
| Dữ liệu item không hợp lệ, không thể tự sửa | Skip có ghi nhận hoặc fail theo yêu cầu completeness |
| Database deadlock | Retry có giới hạn và backoff |
| Connection timeout tạm thời | Retry có giới hạn; nếu hết thì fail |
| API rate limit | Retry theo chính sách dịch vụ, backoff/jitter |
| Thiếu cấu hình hoặc schema không tương thích | Fail sớm, không skip |
| Không xác định được side effect đã xảy ra hay chưa | Đối soát/idempotency; không skip mù quáng |

Nếu exception vừa được cấu hình retry vừa được phép skip, cần hiểu hành vi sau khi retry hết giới hạn. Kiểm thử chính sách cụ thể của phiên bản Spring Batch đang dùng để bảo đảm lỗi hạ tầng không bị bỏ qua ngoài ý muốn.

## 15. Restart và skip: item bị bỏ qua có tự xuất hiện lại không?

Skip thường là quyết định của step execution hiện tại. Khi item bị skip và step hoàn tất, checkpoint có thể tiến qua item đó. Restart job sau này không tự động đưa item đã skip trở lại luồng xử lý thành công.

Muốn xử lý lại item bị skip, ứng dụng cần có nguồn dữ liệu reject đủ chi tiết và một quy trình replay riêng, ví dụ:

1. Người vận hành sửa dữ liệu nguồn hoặc bổ sung dữ liệu tham chiếu.
2. Tạo batch replay với danh sách source ID bị reject.
3. Dùng identifying JobParameters riêng cho lần replay nhưng vẫn tham chiếu batch gốc.
4. Ghi kết quả replay theo business key để không tạo duplicate.
5. Đối soát lại số lượng accepted/rejected của batch gốc và replay.

Không nên sửa checkpoint trong ExecutionContext bằng SQL để ép reader quay lại các item đã skip. Metadata checkpoint thuộc quyền quản lý của Spring Batch; replay theo danh sách reject thường rõ ràng và an toàn hơn.

## 16. Skip trong writer có thể làm mất một phần output như thế nào?

Writer nhận một chunk gồm nhiều item. Nếu writer ném exception cho một item, transaction chunk có thể rollback. Trong fault-tolerant step, Spring Batch có thể phân lập item gây lỗi để áp dụng skip policy và tiếp tục ghi những item còn lại.

Điều này có nghĩa output của chunk có thể chỉ chứa các item ghi thành công, còn item gây lỗi được skip. Nếu writer đã thực hiện side effect ngoài transaction trước khi ném exception, việc rollback database không hoàn tác side effect đó. Khi framework thử lại hoặc phân lập item, cùng item hoặc các item khác trong chunk có thể được gửi lại tùy cơ chế xử lý.

Ví dụ writer ghi vào database và gửi message:

1. Ghi đơn hàng A vào database.
2. Gửi event cho A.
3. Ghi đơn hàng B thất bại.
4. Transaction chunk rollback các thay đổi database.
5. Message cho A có thể đã được broker nhận.

Nếu không dùng outbox hoặc idempotency, downstream có thể nhận event A dù database không còn thay đổi tương ứng, hoặc event có thể bị gửi lại khi retry. Đây là lý do writer có side effect ngoài transaction cần được thiết kế riêng, kể cả khi step cho phép skip.

## 17. SkipListener và transaction của reject record

SkipListener thường được gọi ngay trước khi chunk commit để callback không bị lặp chỉ vì một lần rollback nội bộ. Nếu listener ghi reject record bằng cùng datasource và transaction manager của step, reject record có thể commit cùng transaction của chunk đã xử lý skip.

Điều này có ưu điểm là trạng thái accepted/rejected của chunk được lưu cùng nhau. Tuy nhiên, cần cân nhắc:

- Nếu ghi reject record thất bại, chunk có thể không commit và step có thể retry hoặc fail.
- Nếu listener ghi sang datasource khác, transaction của step có thể không rollback reject record đó.
- Nếu replay hoặc chạy lại batch tạo cùng reject record, unique key cần ngăn duplicate hoặc lưu lịch sử theo mô hình đã chọn.
- Callback read skip không có item; phải trích xuất source location từ exception hoặc reader state.
- Không gọi API ngoài trực tiếp trong SkipListener nếu không có cơ chế idempotency và phục hồi.

Nếu reject store phải độc lập với transaction chính để vẫn giữ lỗi khi chunk rollback, cần thiết kế rõ transaction riêng, outbox hoặc cơ chế audit bền vững. Không dùng REQUIRES_NEW một cách tùy tiện vì nó có thể commit reject record ngay cả khi chunk nghiệp vụ rollback; điều đó có thể đúng hoặc sai tùy ý nghĩa dữ liệu.

## 18. Kiểm thử output có skip

Kiểm thử cần chứng minh cả việc skip xảy ra đúng và output không bị coi nhầm là đầy đủ.

Các trường hợp nên có:

1. Không có lỗi: tất cả item hợp lệ được ghi, skip count bằng 0.
2. Process skip: item lỗi không đến writer, reject record chứa đúng source ID và lý do.
3. Read skip: dòng không parse được được ghi nhận bằng line number/raw source reference nếu có thể.
4. Write skip: item writer không ghi được bị đưa vào reject store, các item còn lại có kết quả đúng.
5. Skip limit: số skip trong giới hạn thì step có thể hoàn thành; vượt giới hạn thì step thất bại.
6. Không skip lỗi hạ tầng: lỗi database/API tạm thời được retry hoặc làm step thất bại, không âm thầm bỏ item.
7. Đối soát: số accepted, filtered và rejected khớp với phạm vi input theo quy tắc nghiệp vụ.
8. Output staging: batch chưa được publish khi đối soát không đạt.
9. Restart: các chunk đã commit không tạo duplicate; item đã skip được lưu để replay riêng.
10. Idempotency: chạy lại listener/replay không tạo reject record hoặc side effect trùng ngoài ý muốn.

Ví dụ test tích hợp:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchJob(jobParameters);

StepExecution importStep = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
assertEquals(2, importStep.getSkipCount());
assertEquals(98, importStep.getWriteCount());
assertEquals(2, rejectedOrderRepository.countByBatchId(batchId));
assertEquals(98, acceptedOrderRepository.countByBatchId(batchId));
~~~

Ví dụ giả định input có đúng 100 item, hai item bị skip trong processor, không có filter và writer ghi thành công 98 item. Nếu có read skip, write skip hoặc filter, các con số cần được điều chỉnh theo pipeline thực tế.

Test cần dùng repository/database phù hợp và kiểm tra cả dữ liệu accepted lẫn reject. Chỉ assert BatchStatus COMPLETED là chưa đủ để chứng minh kết quả đúng.

## 19. Các chỉ số nên theo dõi trong production

Khi output có thể thiếu dữ liệu, dashboard và alert nên thể hiện:

- Input count theo batch.
- Read count, write count, filter count.
- Read skip, process skip và write skip.
- Tổng skip count và skip rate.
- Số reject record đã lưu.
- Số item được replay và số item còn reject.
- Kết quả reconciliation.
- Batch publication status.
- Top exception type và nguồn phát sinh lỗi.

Có thể đặt cảnh báo khi skip count lớn hơn 0 đối với batch yêu cầu đầy đủ tuyệt đối, skip rate vượt ngưỡng nghiệp vụ, có skip nhưng không có reject record tương ứng, accepted + filtered + rejected không khớp phạm vi input theo quy tắc đã định, hoặc batch được đánh dấu READY dù reconciliation chưa thành công.

Log nên chứa batch ID, source ID, stage và error code để truy vết. Không log toàn bộ payload nhạy cảm. Metric nên dùng nhãn có cardinality kiểm soát; không đưa từng order ID vào metric label.

## 20. Những lỗi thiết kế thường gặp

**Cho rằng job COMPLETED nghĩa là mọi record đã được ghi.** Step có thể hoàn thành với skip. Kiểm tra skip counts và reconciliation.

**Skip lỗi database hoặc API.** Lỗi hạ tầng có thể làm mất hàng loạt output. Retry có giới hạn hoặc fail step khi dependency không sẵn sàng.

**Không lưu item bị skip.** Chỉ tăng counter không đủ để sửa hoặc replay record. Ghi source ID, vị trí nguồn và nguyên nhân.

**Nhầm filter với skip.** Filter là loại bỏ có chủ đích bằng null; skip là bỏ qua do exception theo policy. Theo dõi hai trường hợp riêng.

**Đặt skipLimit quá cao.** Job có thể bỏ qua tỷ lệ dữ liệu lớn mà vẫn hoàn tất. Đặt giới hạn theo mức độ quan trọng và thêm kiểm tra tỷ lệ.

**Công bố output ngay sau import.** Downstream có thể tiêu thụ dữ liệu thiếu trước khi đối soát. Dùng staging và bước publish sau khi kiểm tra.

**Không có quy trình replay.** Record đã skip thường không tự xuất hiện lại khi restart. Lưu reject store và thiết kế batch replay riêng.

**Ghi side effect ngoài transaction trong writer.** Rollback không hoàn tác API/message/file. Dùng outbox, idempotency và đối soát.

**Chỉ kiểm tra BatchStatus trong test.** Cần kiểm tra output, reject store, skip counters và completeness.

## 21. Quy trình quyết định có cho phép skip hay không

Trước khi cấu hình skip, hãy trả lời:

1. Item lỗi có thể được xử lý độc lập mà không ảnh hưởng tính đúng đắn của các item khác không?
2. Nghiệp vụ có cho phép output thiếu item đó không?
3. Nếu cho phép, ai cần biết và dữ liệu reject phải được lưu ở đâu?
4. Có thể xác định lại item từ source ID, line number hoặc event ID không?
5. Skip limit và skip rate tối đa là bao nhiêu?
6. Có cần phê duyệt trước khi công bố output không?
7. Retry có phù hợp hơn skip vì lỗi có thể tạm thời không?
8. Writer có side effect ngoài transaction cần idempotency không?
9. Có thể đối soát accepted, filtered và rejected trước khi đánh dấu batch hoàn tất không?
10. Có quy trình replay sau khi dữ liệu được sửa không?

Nếu output phải đầy đủ tuyệt đối, không cho phép skip các lỗi làm mất record bắt buộc; hãy để step thất bại và xử lý dữ liệu trước khi chạy lại. Nếu nghiệp vụ cho phép partial success, skip phải đi cùng reject tracking, reconciliation và trạng thái output thể hiện rõ tính chưa đầy đủ.

## Kết luận

Skip giúp Spring Batch tiếp tục xử lý khi một số item gặp lỗi được cho phép bỏ qua, nhưng chính item đó sẽ không xuất hiện trong output thành công của step. Vì vậy, job có thể kết thúc với BatchStatus COMPLETED trong khi output vẫn thiếu dữ liệu. Đây là rủi ro nghiệp vụ cần được kiểm soát bằng phân loại exception, skip limit và quy tắc completeness rõ ràng.

Khi cho phép skip, hãy ghi nhận từng item qua SkipListener hoặc reject store, phân biệt read/process/write skip với filter, đối soát accepted/filtered/rejected và chỉ publish output sau khi các điều kiện hoàn tất được thỏa mãn. Với dữ liệu bắt buộc đầy đủ, nên fail fast thay vì bỏ qua record. Với partial success được chấp nhận, cần có báo cáo reject và quy trình replay. Kiểm thử phải xác nhận dữ liệu thực tế, không chỉ trạng thái job, để tránh một batch thành công nhưng âm thầm làm thiếu kết quả.
