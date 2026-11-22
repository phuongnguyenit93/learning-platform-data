# Giới hạn skip để không che lỗi hàng loạt

Spring Batch cho phép một Step bỏ qua một số item bị lỗi để tiếp tục xử lý phần dữ liệu còn lại. Cơ chế này hữu ích khi nguồn có một vài bản ghi sai định dạng hoặc một số item vi phạm quy tắc nghiệp vụ có thể được cách ly. Tuy nhiên, nếu cấu hình skip quá rộng hoặc giới hạn quá cao, một lỗi hệ thống hay lỗi dữ liệu trên diện rộng có thể bị hiểu nhầm thành nhiều lỗi riêng lẻ và Job vẫn chạy gần hết dữ liệu trong trạng thái không đáng tin cậy.

Giới hạn skip là một cơ chế bảo vệ để Step dừng khi số lỗi được phép bỏ qua vượt ngưỡng. Để tránh che giấu lỗi hàng loạt, cần phân loại exception rõ ràng, đặt ngưỡng dựa trên quy mô dữ liệu, theo dõi tỷ lệ lỗi và kiểm thử các tình huống mà một lỗi nhỏ ban đầu chuyển thành lỗi diện rộng.

## 1. Skip trong Spring Batch có ý nghĩa gì?

Trong chunk-oriented Step, một item có thể gặp lỗi khi đọc, xử lý hoặc ghi. Nếu Step được cấu hình fault-tolerant và exception thuộc loại được phép skip, Spring Batch có thể bỏ qua item đó rồi tiếp tục với item tiếp theo.

Ba giai đoạn có thể phát sinh skip:

- **Read skip:** reader gặp lỗi khi lấy item, ví dụ một dòng file không thể parse.
- **Process skip:** reader đọc được item nhưng processor ném exception do dữ liệu không hợp lệ.
- **Write skip:** writer không thể ghi một hoặc nhiều item trong chunk và framework xác định item lỗi để bỏ qua theo cấu hình.

Skip không có nghĩa là mọi exception đều có thể bỏ qua. Step phải được cấu hình rõ loại lỗi được phép skip và giới hạn số lượng. Lỗi không được phân loại là skippable hoặc lỗi vượt giới hạn sẽ làm Step thất bại.

## 2. skipLimit giới hạn tổng số lỗi bị bỏ qua

Với cấu hình skipLimit(n), Step được phép bỏ qua tối đa n lỗi theo skip policy. Khi một lỗi skippable tiếp theo làm số skip vượt giới hạn, Step thất bại thay vì tiếp tục bỏ qua.

Ví dụ skipLimit(10) cho phép tối đa 10 skip. Lỗi skippable thứ 11 làm Step thất bại. Giới hạn này áp dụng cho tổng skip của Step qua các giai đoạn read, process và write; nó không phải 10 lỗi cho mỗi giai đoạn hoặc mỗi chunk.

~~~text
skipLimit = 5

Read skips:     2
Process skips:  2
Write skips:    1
                -
Total skips:    5  -> vẫn trong giới hạn

Lỗi skippable tiếp theo
Total skips:    6  -> vượt giới hạn, Step FAILED
~~~

Đây là điểm quan trọng khi tính ngưỡng. Nếu đặt skipLimit(10), không có nghĩa reader được skip 10 item, processor thêm 10 item và writer thêm 10 item. Tất cả cùng tiêu thụ một ngân sách skip của Step.

Giới hạn tuyệt đối giúp ngăn một Job bỏ qua vô hạn lỗi. Tuy nhiên, cùng một con số có thể phù hợp với file 1.000 dòng nhưng quá thấp với file 10 triệu dòng, hoặc quá cao với một Job chỉ xử lý vài chục item. Cần chọn ngưỡng dựa trên quy mô và mức chấp nhận lỗi của nghiệp vụ.

## 3. Cấu hình skip có chọn lọc

Ví dụ Step nhập đơn hàng cho phép bỏ qua lỗi parse file và lỗi validation nghiệp vụ, nhưng không bỏ qua lỗi kết nối database:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        OrderSkipAuditListener skipAuditListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .noSkip(DataAccessResourceFailureException.class)
            .skipLimit(50)
            .listener(skipAuditListener)
            .build();
}
~~~

Trong ví dụ:

- FlatFileParseException có thể đại diện cho một dòng đầu vào sai định dạng.
- InvalidOrderException đại diện cho một lỗi validation được nghiệp vụ cho phép cách ly.
- DataAccessResourceFailureException đại diện cho sự cố truy cập database cần làm Step dừng.
- Tổng số skip được phép là 50 cho cả Step.

Các exception trong ví dụ chỉ mang tính minh họa; hãy dùng loại exception thực tế do reader, processor và writer phát ra. Đặt noSkip cho những lỗi phải dừng xử lý, chẳng hạn database unavailable, lỗi cấu hình, thiếu resource bắt buộc hoặc lỗi xác thực hệ thống.

Tránh dùng skip(Exception.class) hoặc skip(Throwable.class) cho một Job thông thường. Cách phân loại quá rộng có thể khiến lỗi lập trình, lỗi hạ tầng hoặc lỗi dữ liệu nghiêm trọng bị xem như một bản ghi xấu có thể bỏ qua.

## 4. Phân biệt lỗi dữ liệu với lỗi hệ thống

Một giới hạn skip chỉ hữu ích nếu phân loại exception đúng. Cần xác định lỗi nào thuộc về một item riêng lẻ và lỗi nào cho thấy toàn bộ quy trình không thể tiếp tục an toàn.

| Loại lỗi | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| Dữ liệu sai định dạng | Một dòng CSV thiếu cột bắt buộc | Có thể skip và ghi nhận dòng lỗi |
| Vi phạm quy tắc nghiệp vụ riêng lẻ | Đơn hàng có trạng thái không được hỗ trợ | Có thể skip nếu nghiệp vụ cho phép |
| Dữ liệu tham chiếu không tồn tại | Mã khách hàng của một đơn hàng không hợp lệ | Quyết định theo quy tắc nghiệp vụ |
| Database không kết nối được | Connection refused, database unavailable | Retry có giới hạn hoặc fail Step |
| Hết quyền truy cập hệ thống đích | Credential hết hạn hoặc permission bị thu hồi | Fail nhanh và xử lý cấu hình/quyền |
| Lỗi lập trình | NullPointerException do bug trong processor | Thông thường phải fail để sửa code |
| File đầu vào không tồn tại | Đường dẫn cấu hình sai hoặc file chưa được giao | Fail Step, không coi là một dòng bị lỗi |

Một file có một vài dòng sai format khác hoàn toàn với việc toàn bộ file dùng sai delimiter hoặc sai schema. Trường hợp thứ hai có thể làm hầu hết dòng đều parse lỗi; tăng skipLimit để Job tiếp tục chỉ che giấu việc nguồn dữ liệu không tương thích.

Tương tự, nếu writer không kết nối được database, từng item không phải là dữ liệu sai. Bỏ qua hàng loạt write error sẽ khiến đầu ra thiếu dữ liệu nghiêm trọng.

## 5. Không dùng skip để thay thế retry

Retry và skip giải quyết hai loại vấn đề khác nhau:

- **Retry** thử lại một thao tác có khả năng thành công sau đó, thường do lỗi tạm thời như timeout hoặc deadlock.
- **Skip** bỏ qua một item mà nghiệp vụ cho phép không xử lý, thường do dữ liệu không hợp lệ hoặc lỗi không thể sửa bằng cách thử lại.

Ví dụ cấu hình retry cho deadlock và skip cho lỗi validation:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Đây là cấu hình minh họa theo API của Spring Batch 5; exception cụ thể phụ thuộc phiên bản Spring và database. Nếu lỗi tạm thời vẫn tồn tại sau số lần retry, Step chỉ được skip nếu exception cuối cùng cũng được phân loại là skippable và ngân sách skip còn cho phép. Nếu không, Step thất bại.

Không nên skip timeout hoặc deadlock hàng loạt chỉ để Job có trạng thái hoàn thành. Nếu database đang quá tải, retry có giới hạn và dừng Job thường giúp bảo vệ dữ liệu tốt hơn.

## 6. Skip không giống filter

Processor có thể trả null để loại item khỏi luồng ghi mà không phát sinh exception. Đây là filter, không phải skip.

~~~java
@Bean
ItemProcessor<Order, Order> activeOrderProcessor() {
    return order -> {
        if (order.isCancelled()) {
            return null;
        }

        return order;
    };
}
~~~

Trong ví dụ, đơn hàng đã hủy được lọc theo quy tắc nghiệp vụ. Item không đi tới writer và được phản ánh trong filter count của Step. Nó không tiêu thụ skipLimit.

Ngược lại, nếu processor ném InvalidOrderException và exception đó được cấu hình skip, item được tính vào skip count.

| Hành vi | Có exception? | Tăng skip count? | Ý nghĩa |
|---|---|---|---|
| Processor trả null | Không | Không | Filter có chủ đích |
| Processor ném exception skippable | Có | Có | Bỏ qua item lỗi |
| Reader trả null | Không | Không | Hết dữ liệu |
| Exception không skippable | Có | Không được bỏ qua | Step thất bại |

Không dùng exception để biểu diễn một điều kiện filter bình thường. Ngược lại, cũng không trả null khi có lỗi parse hoặc lỗi hệ thống, vì framework sẽ hiểu đó là filter hoặc EOF tùy vị trí và có thể kết thúc mà không báo lỗi.

## 7. SkipLimitExceededException và kết quả của Step

Khi skip count vượt giới hạn, Spring Batch ném SkipLimitExceededException trong quá trình kiểm tra skip policy. Step không tiếp tục bỏ qua item vượt ngưỡng và thường kết thúc với trạng thái FAILED.

Ví dụ với giới hạn 20:

~~~text
Item 1..100:
  8 read skips
  5 process skips
  7 write skips
  ----------------
  20 skips: còn trong giới hạn

Item tiếp theo gặp lỗi skippable:
  skip count sẽ vượt 20
  -> SkipLimitExceededException
  -> Step FAILED
~~~

Không nên bắt SkipLimitExceededException trong reader, processor hoặc writer rồi tiếp tục xử lý. Đây là tín hiệu bảo vệ của Step; nuốt exception sẽ làm mất ý nghĩa giới hạn.

Nếu cần cung cấp lý do thất bại rõ hơn cho vận hành, có thể bổ sung ExitStatus hoặc audit ở listener theo cách giữ nguyên BatchStatus FAILED. Không chuyển trạng thái sang COMPLETED chỉ vì đã ghi nhận được danh sách lỗi.

## 8. Theo dõi skip count theo từng giai đoạn

StepExecution lưu counters riêng cho read, process và write skip. Sau khi Step kết thúc, có thể truy vấn các giá trị này để biết lỗi tập trung ở giai đoạn nào.

~~~java
long readSkips = stepExecution.getReadSkipCount();
long processSkips = stepExecution.getProcessSkipCount();
long writeSkips = stepExecution.getWriteSkipCount();

long totalSkips = readSkips + processSkips + writeSkips;
~~~

Các counters giúp chẩn đoán:

- Read skips tăng mạnh: kiểm tra file format, encoding, delimiter hoặc nguồn đầu vào.
- Process skips tăng mạnh: kiểm tra dữ liệu nghiệp vụ, mapping và validation.
- Write skips tăng mạnh: kiểm tra constraint, schema, quyền ghi và tính duy nhất của dữ liệu đích.

Có thể ghi các counters vào metric và audit để cảnh báo khi một giai đoạn vượt mức bình thường. Đừng chỉ theo dõi tổng skip vì tổng số không cho biết lỗi xuất hiện ở đâu.

## 9. Ghi nhận item bị skip bằng SkipListener

SkipListener cho phép ghi lại sự kiện skip theo giai đoạn:

- onSkipInRead(Throwable): lỗi đọc bị skip; thường không có item hợp lệ để cung cấp.
- onSkipInProcess(item, Throwable): item đã đọc được nhưng lỗi xử lý.
- onSkipInWrite(item, Throwable): item bị lỗi trong lúc ghi.

~~~java
public class OrderSkipAuditListener
        implements SkipListener<Order, Order> {

    private final SkipAuditService auditService;

    public OrderSkipAuditListener(SkipAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        auditService.recordReadFailure(
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            Order item,
            Throwable exception) {
        auditService.recordItemFailure(
                item.getId(),
                "PROCESS",
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        auditService.recordItemFailure(
                item.getId(),
                "WRITE",
                exception.getClass().getSimpleName());
    }
}
~~~

Audit nên lưu JobExecution ID, StepExecution ID, business key, giai đoạn lỗi và loại exception đã chuẩn hóa. Tránh lưu toàn bộ item hoặc exception message nếu chúng có thể chứa dữ liệu cá nhân, SQL parameter hay secret.

SkipListener giúp biết item nào bị bỏ qua, nhưng không thay thế skipLimit. Listener ghi nhận sự kiện; skip policy mới quyết định lỗi có được phép bỏ qua và giới hạn đã bị vượt hay chưa.

## 10. Dùng SkipPolicy khi quy tắc phức tạp

Khi skip, noSkip và skipLimit không đủ diễn đạt quy tắc, có thể dùng SkipPolicy tùy chỉnh.

Policy nhận exception và số lượng skip hiện tại, rồi quyết định có cho phép bỏ qua hay không. Nếu không cho phép, policy trả false hoặc ném SkipLimitExceededException theo thiết kế. Cần chú ý hợp đồng của phiên bản Spring Batch đang dùng: framework có thể gọi policy với giá trị skipCount đặc biệt khi chỉ kiểm tra một exception có skippable hay không.

Ví dụ minh họa một policy chỉ cho phép lỗi parse và validation trong giới hạn tuyệt đối:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private final long maxSkips;

    public OrderSkipPolicy(long maxSkips) {
        this.maxSkips = maxSkips;
    }

    @Override
    public boolean shouldSkip(Throwable exception, long skipCount)
            throws SkipLimitExceededException {

        boolean skippable =
                exception instanceof FlatFileParseException
                || exception instanceof InvalidOrderException;

        if (!skippable) {
            return false;
        }

        // Một số luồng kiểm tra khả năng skip truyền skipCount = -1.
        if (skipCount < 0) {
            return true;
        }

        if (skipCount >= maxSkips) {
            throw new SkipLimitExceededException(
                    "Order skip limit exceeded", exception);
        }

        return true;
    }
}
~~~

Đăng ký policy:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy(50))
        .build();
~~~

Ví dụ policy cần được điều chỉnh và kiểm thử theo API của phiên bản Spring Batch. Không kết hợp skip, noSkip, skipLimit và skipPolicy một cách tùy tiện; khi dùng custom policy, hãy để policy thể hiện đầy đủ việc phân loại và giới hạn để tránh các quy tắc chồng chéo.

## 11. skipLimit là ngưỡng tuyệt đối, không phải tỷ lệ

skipLimit(50) giới hạn số skip tuyệt đối. Nó không có nghĩa chỉ được bỏ qua 50 phần trăm, 5 phần trăm hoặc một tỷ lệ khác của dữ liệu.

Ví dụ:

| Tổng item | Số skip | Tỷ lệ lỗi |
|---:|---:|---:|
| 100 | 10 | 10% |
| 10.000 | 10 | 0,1% |
| 10.000 | 100 | 1% |
| 1.000.000 | 100 | 0,01% |

Cùng 100 skip có thể là mức lỗi rất nghiêm trọng với Job nhỏ nhưng không đáng kể với Job lớn. Vì vậy, chọn ngưỡng tuyệt đối cần dựa vào volume điển hình và mức lỗi nghiệp vụ cho phép.

Nếu cần ngưỡng theo tỷ lệ, hãy xác định rõ mẫu số là số item đã đọc, số item đã xử lý hay tổng số item dự kiến. Những số này có thể khác nhau do EOF, filter, retry và skip ở từng giai đoạn.

Có thể dùng listener/metric để tính tỷ lệ sau Step và cảnh báo hoặc đánh dấu kết quả cần xem xét. Nếu cần dừng sớm khi tỷ lệ lỗi vượt ngưỡng, phải thiết kế một policy có state theo StepExecution hoặc một bước kiểm soát chuyên biệt; không giả định skipLimit tự hiểu tỷ lệ. State theo tỷ lệ cần được xử lý cẩn thận với rollback, retry, partitioning và restart để không tính sai số item.

## 12. Cách phát hiện lỗi hàng loạt sớm

Một skipLimit tuyệt đối là lớp bảo vệ đầu tiên. Để nhận ra lỗi hàng loạt, nên kết hợp nhiều tín hiệu:

- Số skip tuyệt đối trong toàn Step.
- Tỷ lệ skip trên số item đã đọc hoặc đã xử lý.
- Số skip liên tiếp trong một khoảng dữ liệu.
- Tỷ lệ lỗi theo nguồn, tenant hoặc loại bản ghi.
- Sự thay đổi đột ngột so với lịch sử các lần chạy.
- Tập trung lỗi ở một giai đoạn read, process hay write.
- Các lỗi hệ thống như database timeout, authentication failure hoặc thiếu resource.

Ví dụ, nếu 20 dòng đầu có 2 lỗi parse thì có thể vẫn nằm trong ngưỡng. Nếu 500 dòng liên tiếp đều lỗi parse, nhiều khả năng cấu hình file hoặc schema nguồn đã thay đổi. Tỷ lệ và chuỗi lỗi liên tiếp giúp phát hiện tình huống này sớm hơn chỉ nhìn vào một giới hạn tuyệt đối lớn.

Có thể thêm bước pre-validation để kiểm tra header, encoding, schema hoặc checksum trước khi import toàn bộ file. Nếu cấu trúc nguồn không phù hợp, Job nên dừng trước khi tạo nhiều skip record.

## 13. Thiết kế ngưỡng theo quy mô và mức độ rủi ro

Không có một skipLimit phù hợp cho mọi Job. Hãy chọn dựa trên dữ liệu thực tế và hậu quả nếu bỏ qua item.

Ví dụ một chính sách minh họa:

| Job | Quy mô dự kiến | Skip limit gợi ý để bắt đầu thử nghiệm |
|---|---:|---:|
| Import file nhỏ | 1.000 dòng | 5 |
| Import dữ liệu hằng ngày | 100.000 dòng | 100 |
| Xử lý log không quan trọng | 5.000.000 dòng | Theo tỷ lệ và mức mất dữ liệu chấp nhận được |
| Thanh toán hoặc đối soát tài chính | Tùy batch | Rất thấp hoặc không cho skip ở lỗi trọng yếu |

Các con số chỉ là điểm bắt đầu minh họa, không phải mặc định Spring Batch hay khuyến nghị chung. Với dữ liệu tài chính, y tế hoặc dữ liệu cần đối soát, một item bị bỏ qua có thể tạo sai lệch lớn; chính sách có thể yêu cầu fail ngay với bất kỳ lỗi nào thuộc loại quan trọng.

Khi volume thay đổi theo ngày, nên theo dõi cả số tuyệt đối và tỷ lệ. Một ngưỡng lớn được đặt cho ngày cao điểm có thể che giấu lỗi nghiêm trọng trong ngày có ít dữ liệu.

## 14. Xử lý lỗi write và nguy cơ skip quá rộng

Skip trong giai đoạn write cần đặc biệt thận trọng. Writer nhận cả chunk; một lỗi ghi có thể khiến transaction chunk rollback. Spring Batch có thể phải xác định item nào gây lỗi thông qua cơ chế xử lý fault-tolerant, vì vậy writer có thể được gọi lại trong quá trình phân loại lỗi.

Nếu database đang lỗi kết nối, mọi item trong chunk có thể thất bại. Cấu hình skip cho một exception quá tổng quát có thể làm Step lần lượt bỏ qua nhiều item thay vì dừng ngay.

Nên:

- Phân biệt lỗi constraint của một bản ghi với lỗi connection/resource của database.
- Chỉ skip lỗi ghi có thể quy về một item cụ thể và được nghiệp vụ cho phép.
- Retry lỗi tạm thời như deadlock hoặc timeout khi thao tác có thể thử lại an toàn.
- Fail nhanh khi database unavailable, credential sai hoặc schema không tương thích.
- Dùng unique key hoặc upsert để writer an toàn khi retry/restart.
- Ghi audit cho từng item write bị skip và đối soát số liệu sau Job.

Không bắt exception trong writer rồi bỏ qua im lặng. Khi framework không nhận được exception, skip policy, counters và SkipListener không thể phản ánh đúng lỗi.

## 15. Skip trong partitioned Step

Trong partitioning, mỗi worker StepExecution có counters và lifecycle riêng. Cần hiểu giới hạn skip được áp dụng ở phạm vi StepExecution của worker, không nên mặc định một con số duy nhất tự động giới hạn tổng lỗi của toàn bộ manager Step theo cách nghiệp vụ mong muốn.

Ví dụ nếu có 8 worker và mỗi worker được phép skip tối đa 20 item, tổng số skip trên toàn Job có thể cao hơn 20. Nếu yêu cầu nghiệp vụ là giới hạn tổng toàn batch, cần có cơ chế kiểm soát tổng hợp giữa các partition hoặc kiểm tra kết quả manager sau khi worker hoàn tất.

Các nguyên tắc:

- Đặt skipLimit cho từng worker dựa trên quy mô partition.
- Tổng hợp skip count của tất cả worker.
- Kiểm tra tỷ lệ lỗi theo từng partition để phát hiện một vùng dữ liệu bất thường.
- Nếu cần global limit, dùng một cơ chế phối hợp an toàn thay vì các biến static hoặc Job context mutable được nhiều worker ghi đồng thời.
- Bảo đảm retry/restart không làm đếm trùng audit hoặc metric.

Một partition có tỷ lệ lỗi cao có thể bị che khuất nếu chỉ nhìn tổng Job. Dashboard nên hiển thị cả tổng và số liệu theo partition.

## 16. Quan sát và cảnh báo khi skip tăng bất thường

Có thể dùng StepExecution counters hoặc listener để phát metric:

~~~java
public class SkipMetricsListener implements StepExecutionListener {

    private final MeterRegistry registry;

    public SkipMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        String job = execution.getJobExecution()
                .getJobInstance().getJobName();
        String step = execution.getStepName();

        registry.counter(
                "batch.step.skip.read",
                "job", job,
                "step", step)
                .increment(execution.getReadSkipCount());

        registry.counter(
                "batch.step.skip.process",
                "job", job,
                "step", step)
                .increment(execution.getProcessSkipCount());

        registry.counter(
                "batch.step.skip.write",
                "job", job,
                "step", step)
                .increment(execution.getWriteSkipCount());

        return execution.getExitStatus();
    }
}
~~~

Có thể đặt alert khi tổng skip vượt ngưỡng vận hành, tỷ lệ skip tăng bất thường hoặc write skip xuất hiện trong một Job vốn không chấp nhận lỗi ghi.

Không đưa Order ID, Customer ID, JobExecution ID hoặc file path vào metric tag vì cardinality có thể tăng rất cao. Đưa các định danh chi tiết vào audit/log với quyền truy cập phù hợp.

Nếu dùng metric listener sau Step, alert sẽ xuất hiện sau khi Step kết thúc. Muốn phát hiện sớm trong lúc xử lý, cần cập nhật metric ở listener item/skip hoặc dùng cơ chế theo dõi tiến độ theo chunk; vẫn cần tránh overhead quá lớn.

## 17. Kiểm thử giới hạn skip

Skip policy phải được kiểm thử ở cả giới hạn và loại exception.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Không có lỗi | Step hoàn thành, skip count bằng 0 |
| Có ít lỗi skippable hơn giới hạn | Step tiếp tục, item lỗi được ghi nhận |
| Số skip đúng bằng giới hạn | Step vẫn có thể hoàn thành |
| Có thêm một lỗi skippable sau giới hạn | Step thất bại do vượt skip limit |
| Exception không skippable | Step thất bại ngay theo chính sách |
| Lỗi tạm thời có retry | Thử lại trong giới hạn trước khi quyết định kết quả cuối |
| Processor trả null | Tăng filter count, không tăng skip count |
| Lỗi read | Tăng read skip count nếu được phép skip |
| Lỗi process | Tăng process skip count nếu được phép skip |
| Lỗi write | Tăng write skip count nếu được phép skip |
| Partitioning | Giới hạn và tổng skip được đánh giá ở đúng phạm vi |
| Restart | Counters và audit phản ánh đúng execution, không nhân đôi side effect |

Một integration test hữu ích là tạo file với một số dòng hợp lệ, một số dòng lỗi và một đoạn dữ liệu sai schema hàng loạt. Xác nhận Job dừng khi vượt ngưỡng, các item đã commit trước đó vẫn đúng, các item lỗi được ghi vào audit và không có phần dữ liệu còn lại bị âm thầm coi là đã xử lý.

## 18. Những lỗi cấu hình thường gặp

**Đặt skipLimit quá cao.** Job có thể hoàn thành dù phần lớn dữ liệu không được xử lý. Chọn ngưỡng theo volume và hậu quả nghiệp vụ.

**Skip Exception.class.** Có thể che giấu lỗi lập trình hoặc hạ tầng. Chỉ skip exception cụ thể.

**Dùng skip thay retry.** Timeout hoặc deadlock tạm thời thường cần retry có giới hạn; bỏ qua sẽ làm thiếu dữ liệu.

**Chỉ xem tổng skip count.** Không biết lỗi xảy ra ở read, process hay write. Theo dõi từng counter.

**Nhầm filter với skip.** Processor trả null không tiêu thụ skipLimit.

**Không audit item bị skip.** Job có thể hoàn thành nhưng không có danh sách bản ghi cần sửa hoặc xử lý lại.

**Coi skipLimit là tỷ lệ.** Đây là giới hạn số lượng tuyệt đối của Step. Tỷ lệ cần được tính riêng.

**Không tính partition scope.** Nhiều worker có thể cộng dồn skip vượt mức nghiệp vụ mong muốn nếu chỉ đặt limit riêng cho từng worker.

**Bắt và nuốt exception.** Framework không thể áp dụng skip policy và cập nhật counters đúng.

## 19. Quy trình đặt giới hạn skip an toàn

Khi thiết kế Step có skip, hãy thực hiện theo thứ tự:

1. Xác định lỗi dữ liệu nào thực sự có thể bỏ qua theo nghiệp vụ.
2. Phân loại riêng lỗi hệ thống, lỗi cấu hình và lỗi lập trình phải làm Step dừng.
3. Cấu hình skip cho exception cụ thể; dùng noSkip khi cần loại trừ lỗi quan trọng.
4. Đặt skipLimit tuyệt đối dựa trên quy mô và mức rủi ro của batch.
5. Nếu volume biến động, theo dõi cả skip count và skip ratio.
6. Dùng retry cho lỗi tạm thời có thể phục hồi, với giới hạn thử lại rõ ràng.
7. Ghi audit item bị skip bằng SkipListener và bảo vệ side effect khỏi duplicate.
8. Theo dõi read/process/write skip riêng biệt.
9. Với partitioning, xác định rõ giới hạn từng worker và giới hạn toàn batch.
10. Kiểm thử trường hợp lỗi hàng loạt, vượt ngưỡng, retry, restart và dữ liệu đã commit.

Skip giúp Job tiếp tục khi một số item lỗi riêng lẻ có thể được bỏ qua an toàn. skipLimit đặt hàng rào để lỗi không tăng vô hạn; phân loại exception ngăn lỗi hạ tầng bị coi là lỗi dữ liệu; metric và audit giúp phát hiện xu hướng bất thường. Khi kết hợp các lớp này, Job có thể xử lý dữ liệu không hoàn hảo mà vẫn dừng kịp thời khi nguồn hoặc hệ thống gặp lỗi trên diện rộng.

