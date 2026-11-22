# Không tạo flow khó theo dõi từ quá nhiều nhánh

Job flow trong Spring Batch mô tả cách các step và các thành phần flow nối với nhau. Khi job có nhiều kết quả nghiệp vụ, việc khai báo transition giúp chọn đường đi phù hợp. Tuy nhiên, nếu mỗi điều kiện nhỏ đều tạo thêm một nhánh, flow nhanh chóng trở thành một đồ thị lớn, khó hiểu, khó kiểm thử và khó vận hành.

Thiết kế tốt cần giữ số đường đi ở mức cần thiết, đặt quyết định ở đúng nơi và gom những công đoạn có cùng trách nhiệm thành step hoặc subflow dễ đọc. Flow nên thể hiện cấu trúc điều phối chính; các quy tắc chi tiết về dữ liệu nên nằm trong processor, service, decider hoặc chính sách lỗi phù hợp.

## 1. Vì sao quá nhiều nhánh làm flow khó bảo trì?

Một job có thể rẽ nhánh theo kết quả kiểm tra, loại file, tenant, kênh nhập, chế độ xử lý, ngày nghiệp vụ hoặc trạng thái của hệ thống ngoài. Nếu mỗi giá trị đều được biểu diễn bằng một transition riêng, số cạnh và số đường đi tăng nhanh.

Ví dụ, một job nhập dữ liệu có thể phân nhánh theo ba loại file, hai chế độ xử lý và bốn nhóm khách hàng. Nếu kết hợp tất cả điều kiện trong flow, số trường hợp cần theo dõi có thể lên đến 3 × 2 × 4 = 24 tổ hợp. Khi thêm một điều kiện mới, đồ thị càng khó đọc.

```text
                 +--> CSV + normal + group A
                 +--> CSV + normal + group B
                 +--> CSV + special + group A
validateInput ---+--> XML + normal + group A
                 +--> XML + special + group C
                 +--> JSON + normal + group D
                 +--> ... nhiều đường đi khác
```

Những vấn đề thường xuất hiện:

- Khó nhìn ra đường đi chính của job vì transition cụ thể và wildcard đan xen.
- Cùng một nhóm step bị khai báo lặp lại ở nhiều nhánh.
- Một thay đổi nghiệp vụ nhỏ phải sửa nhiều transition.
- Dễ bỏ sót exit code hoặc tạo nhánh không có đường kết thúc.
- Khó viết test bao phủ mọi tổ hợp điều kiện.
- Người vận hành khó giải thích vì sao một execution đi vào một nhánh cụ thể.

## 2. Chỉ dùng nhánh khi đường đi thực sự khác nhau

Không phải mọi điều kiện nghiệp vụ đều cần trở thành một nhánh trong job flow. Trước khi thêm transition, hãy xác định điều kiện đó có làm thay đổi **công đoạn điều phối** hay chỉ làm thay đổi cách xử lý một item.

| Điều kiện | Cách xử lý thường phù hợp |
|---|---|
| Bản ghi không hợp lệ nhưng có thể bỏ qua | Validation, exception và skip policy trong step |
| Bản ghi không thuộc phạm vi cần xử lý | Processor filter bằng `null` hoặc reader chọn dữ liệu phù hợp |
| Chỉ khác cách chuyển đổi từng item | `ItemProcessor` hoặc strategy service |
| Lỗi kết nối tạm thời | Retry policy, timeout và backoff |
| Kết quả kiểm tra quyết định chạy một nhóm step khác | Conditional flow hoặc `JobExecutionDecider` |
| Sau một bước cần thực hiện một công đoạn chung | Nối các nhánh về step dùng chung |

Ví dụ, không cần tạo một nhánh flow cho từng loại đơn hàng nếu tất cả đều đi qua cùng bước ghi dữ liệu. Có thể để processor chọn chiến lược chuyển đổi theo loại đơn hàng, còn flow vẫn chỉ có một đường `validate -> process -> write`.

## 3. Giữ đường đi chính tuyến tính

Khi phần lớn job luôn chạy theo cùng thứ tự, hãy thể hiện chuỗi chính bằng `start()` và `next()`. Chỉ tách nhánh tại những điểm thật sự cần chọn một quy trình khác.

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step classifyInputStep,
        Step processOrdersStep,
        Step publishResultStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
        .start(validateInputStep)
        .next(classifyInputStep)
        .next(processOrdersStep)
        .next(publishResultStep)
        .build();
}
```

Đây là flow tuần tự khi mọi step có cùng đường đi. Nếu một step thất bại, job dừng theo hành vi thông thường và có thể được restart khi metadata cho phép. Không cần tạo nhánh riêng chỉ để mô tả lỗi kỹ thuật nếu retry/skip ở cấp step đã xử lý được trường hợp đó.

## 4. Dùng exit code có ý nghĩa và giới hạn số kết quả

Conditional flow dựa trên `ExitStatus` của step. Step có thể trả về exit code chuẩn như `COMPLETED`, `FAILED` hoặc một mã tùy chỉnh như `EMPTY_INPUT` hay `INVALID_INPUT`.

Không nên tạo một exit code cho mọi giá trị dữ liệu chi tiết, ví dụ `CSV_TENANT_A`, `CSV_TENANT_B`, `XML_TENANT_A`, `XML_TENANT_B`. Hãy gom các kết quả thành một số trạng thái điều phối có ý nghĩa ổn định.

Ví dụ, step phân loại chỉ cần đưa ra ba kết quả:

- `READY`: có dữ liệu hợp lệ và có thể xử lý.
- `EMPTY`: nguồn hợp lệ nhưng không có dữ liệu cần nhập.
- `INVALID`: đầu vào không đáp ứng hợp đồng.

Flow sau đó xử lý ba kết quả này ở cấp quy trình. Các khác biệt như tenant, định dạng cột hoặc quy tắc mapping nên được giải quyết trong thành phần chuyên trách.

## 5. Dùng JobExecutionDecider cho quyết định runtime

Khi cần chọn nhánh dựa trên JobParameters, trạng thái nghiệp vụ hoặc thông tin runtime, `JobExecutionDecider` giúp gom logic quyết định vào một thành phần riêng. Flow chỉ cần ánh xạ kết quả decider sang các đường đi.

```java
@Bean
JobExecutionDecider inputDecider(InputPolicyService policyService) {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");
        InputDecision decision = policyService.decide(mode);

        return new FlowExecutionStatus(decision.name());
    };
}
```

Flow dùng decider:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step inspectInputStep,
        JobExecutionDecider inputDecider,
        Step processStandardStep,
        Step processPriorityStep,
        Step finishEmptyInputStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(inspectInputStep)
        .next(inputDecider)
            .on("STANDARD").to(processStandardStep)
        .from(inputDecider)
            .on("PRIORITY").to(processPriorityStep)
        .from(inputDecider)
            .on("EMPTY").to(finishEmptyInputStep)
        .from(inputDecider)
            .on("*").fail()
        .end()
        .build();
}
```

Decider giúp tách quyết định khỏi cấu hình flow, nhưng bản thân decider cũng cần đơn giản. Nên để service chuyên trách tính kết quả, còn decider chuyển kết quả đó thành `FlowExecutionStatus` nhỏ và dễ hiểu. Tránh biến decider thành một nơi chứa toàn bộ nghiệp vụ và nhiều truy vấn không liên quan.

## 6. Gom các nhánh về step dùng chung

Khi nhiều kết quả khác nhau cần tiếp tục bằng cùng một công đoạn, hãy nối các transition về một step chung thay vì sao chép các step phía sau cho từng nhánh.

```java
return new JobBuilder("importJob", jobRepository)
    .start(classifyInputStep)
        .on("STANDARD").to(processStandardStep)
    .from(classifyInputStep)
        .on("PRIORITY").to(processPriorityStep)
    .from(processStandardStep)
        .on("COMPLETED").to(publishResultStep)
    .from(processPriorityStep)
        .on("COMPLETED").to(publishResultStep)
    .from(publishResultStep)
        .on("COMPLETED").end()
    .from(publishResultStep)
        .on("*").fail()
    .end()
    .build();
```

Ở đây, hai nhánh xử lý khác nhau nhưng cùng đi tới `publishResultStep`. Step công bố kết quả chỉ được khai báo một lần. Cách hội tụ này giảm code lặp và giúp thay đổi bước chung dễ dàng hơn.

Khi hội tụ, cần bảo đảm step chung nhận được dữ liệu cần thiết từ cả hai nhánh. Có thể lưu kết quả phân loại hoặc metadata cần thiết trong `JobExecution` context, hoặc dùng một định dạng đầu ra thống nhất.

## 7. Đóng gói nhóm step thành Flow con

Khi một nhánh gồm nhiều step có ý nghĩa riêng, có thể gom chúng thành `Flow` con. Job cấp cao khi đó chỉ thể hiện các giai đoạn lớn, còn chi tiết nội bộ nằm trong flow con.

```java
@Bean
Flow standardImportFlow(
        Step parseStandardFileStep,
        Step validateStandardRowsStep,
        Step writeStandardRowsStep) {

    return new FlowBuilder<SimpleFlow>("standardImportFlow")
        .start(parseStandardFileStep)
        .next(validateStandardRowsStep)
        .next(writeStandardRowsStep)
        .build();
}
```

Flow cấp job có thể sử dụng flow con này cùng các flow khác. Cách tổ chức này phù hợp khi mỗi nhóm có trách nhiệm rõ ràng và đủ phức tạp để được đọc, kiểm thử hoặc tái sử dụng độc lập.

Không nên tạo flow con cho mọi step đơn lẻ. Quá nhiều lớp lồng nhau cũng khiến người đọc phải nhảy qua nhiều file mới hiểu được đường đi. Chỉ tách khi tên flow con thể hiện được một giai đoạn nghiệp vụ có ý nghĩa.

## 8. Phân biệt flow điều phối với xử lý lỗi

Một nguyên nhân làm flow phình to là dùng transition cho mọi lỗi có thể xảy ra. Nhiều lỗi nên được giải quyết ở cấp step:

- Lỗi tạm thời: retry có giới hạn.
- Item không hợp lệ nhưng có thể loại bỏ: skip policy và `SkipListener`.
- Item hợp lệ nhưng không thuộc phạm vi: filter hoặc query điều kiện.
- Lỗi nghiêm trọng: để step thất bại và xử lý restart sau khi sửa nguyên nhân.

Flow chỉ cần nhánh khi kết quả làm thay đổi giai đoạn tiếp theo của quy trình. Ví dụ, `INVALID_INPUT` có thể dẫn tới flow lưu file reject, trong khi `TransientDataAccessException` thường nên được retry ngay trong step thay vì tạo một nhánh flow riêng.

## 9. Đặt wildcard và transition rõ ràng

Với conditional flow, dùng các pattern cụ thể cho kết quả dự kiến và một nhánh dự phòng cho kết quả còn lại. Khai báo các transition cụ thể trước wildcard để người đọc dễ nhận ra những trường hợp được xử lý chủ động.

```java
.start(validateInputStep)
    .on("INVALID_INPUT").to(rejectInputStep)
.from(validateInputStep)
    .on("COMPLETED").to(processInputStep)
.from(validateInputStep)
    .on("*").fail()
```

`on("*")` là nhánh tổng quát. Nó hữu ích để bảo đảm kết quả ngoài dự kiến có hành vi rõ ràng, nhưng không nên dùng wildcard để gom cả lỗi nghiêm trọng vào một nhánh hoàn tất thành công.

Đối với mỗi step có conditional transition, hãy xác định các exit code có thể phát sinh và đảm bảo mỗi code có đường đi phù hợp. Nếu một step tạo ra quá nhiều exit code, xem xét gom kết quả hoặc chuyển quyết định sang decider.

## 10. Đừng biến từng parameter thành một nhánh

JobParameters thường xác định dữ liệu hoặc phạm vi công việc, không nhất thiết phải làm thay đổi cấu trúc flow.

Ví dụ, một job chạy cho nhiều tenant có thể dùng cùng flow và truyền `tenantId` trong JobParameters. Các reader, processor và writer được cấu hình để xử lý dữ liệu theo tenant đó. Không cần tạo một nhánh cho từng tenant.

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("tenantId", tenantId, true)
    .addString("businessDate", businessDate.toString(), true)
    .toJobParameters();
```

Chỉ tạo nhánh khi tenant hoặc parameter thực sự chọn một quy trình khác, chẳng hạn tenant loại A phải qua một hệ thống đối soát riêng. Nếu chỉ khác giá trị dữ liệu, giữ flow chung sẽ dễ mở rộng hơn.

## 11. Khi nào nên dùng Split và chạy song song?

`split()` dùng khi có các flow độc lập có thể chạy song song. Đây là một cấu trúc điều phối khác với việc tạo nhiều nhánh tuần tự.

Ví dụ, sau khi chuẩn bị dữ liệu, job có thể tạo báo cáo và cập nhật chỉ mục tìm kiếm độc lập:

```java
Flow reportFlow = new FlowBuilder<SimpleFlow>("reportFlow")
    .start(generateReportStep)
    .build();

Flow indexFlow = new FlowBuilder<SimpleFlow>("indexFlow")
    .start(updateSearchIndexStep)
    .build();

Flow parallelFlow = new FlowBuilder<SimpleFlow>("parallelFlow")
    .split(taskExecutor)
    .add(reportFlow, indexFlow)
    .build();
```

Chỉ dùng song song khi hai flow thực sự độc lập về dữ liệu, transaction và tài nguyên. Cần xác định rõ cách xử lý khi một flow thất bại, khi flow còn lại đã hoàn thành và cách tổng hợp kết quả. Không dùng `split()` chỉ để làm sơ đồ trông ngắn hơn.

## 12. Giữ logic quyết định ở một nơi có thể kiểm thử

Khi điều kiện nghiệp vụ phức tạp, hãy đưa phần tính toán vào service thuần hoặc policy component có thể kiểm thử độc lập. Decider chỉ nên gọi service và trả về một kết quả hữu hạn.

```java
public enum ImportRoute {
    STANDARD,
    PRIORITY,
    EMPTY,
    REJECT
}

@Service
public class ImportRoutingPolicy {

    public ImportRoute determine(InputSummary summary) {
        if (!summary.isValid()) {
            return ImportRoute.REJECT;
        }
        if (summary.recordCount() == 0) {
            return ImportRoute.EMPTY;
        }
        return summary.isPriority()
            ? ImportRoute.PRIORITY
            : ImportRoute.STANDARD;
    }
}
```

Enum làm rõ tập kết quả có thể xảy ra và tránh các chuỗi rải rác trong code. Có thể kiểm thử policy với các trường hợp biên mà không cần khởi chạy cả job. Khi policy thay đổi, flow chỉ cần điều chỉnh nếu tập đường đi thực sự thay đổi.

## 13. Thiết kế flow có thể quan sát và kiểm thử

Mỗi nhánh nên có tên, điều kiện và kết thúc rõ ràng. Người vận hành cần xem được vì sao một execution đi vào nhánh đó, còn người phát triển cần viết test cho các kết quả quan trọng.

Các thực hành hữu ích:

1. Đặt tên exit code theo trạng thái nghiệp vụ ngắn gọn, không gắn dữ liệu cá nhân hoặc giá trị động.
2. Ghi nhận kết quả quyết định cùng JobExecution ID để có thể truy vết.
3. Kiểm thử từng giá trị mà decider có thể trả về.
4. Kiểm thử nhánh wildcard hoặc kết quả không hợp lệ.
5. Kiểm thử các đường hội tụ và xác nhận dữ liệu cần thiết có sẵn cho step chung.
6. Kiểm thử restart ở các điểm có thể thất bại trong từng nhánh.
7. Tránh log toàn bộ JobParameters nếu chúng có dữ liệu nhạy cảm.

Khi số nhánh tăng, một bảng quyết định thường dễ đọc hơn sơ đồ flow quá dày:

| Kết quả phân loại | Đường đi |
|---|---|
| `STANDARD` | `processStandardStep` rồi `publishResultStep` |
| `PRIORITY` | `processPriorityStep` rồi `publishResultStep` |
| `EMPTY` | `finishEmptyInputStep` rồi kết thúc |
| `REJECT` | `rejectInputStep` rồi kết thúc theo chính sách |
| Kết quả không biết | Kết thúc thất bại để điều tra |

## 14. Lập kế hoạch khi phải thêm nhánh mới

Khi một yêu cầu mới đề xuất thêm nhánh, hãy làm rõ:

1. Điều kiện mới có làm thay đổi chuỗi công đoạn hay chỉ thay đổi cách xử lý item?
2. Có thể dùng cùng step với strategy hoặc parameter khác không?
3. Có thể hội tụ về step chung sau phần khác biệt không?
4. Quyết định có nên được gom vào `JobExecutionDecider` hay policy service không?
5. Nhánh mới có tạo thêm một tổ hợp với các điều kiện hiện tại không?
6. Mỗi nhánh có đường kết thúc và restart rõ ràng không?
7. Có thể kiểm thử riêng kết quả quyết định và kiểm thử tích hợp các đường đi không?

Nếu một thay đổi nhỏ đòi hỏi sửa nhiều transition, đó là tín hiệu cấu trúc flow đang gánh quá nhiều nghiệp vụ. Hãy xem xét gom điều kiện, tách subflow hoặc chuyển xử lý về service/processor.

## 15. Các lỗi thiết kế thường gặp

| Cách thiết kế | Hệ quả | Hướng cải thiện |
|---|---|---|
| Tạo một nhánh cho mỗi tenant hoặc mã khách hàng | Flow phình theo dữ liệu runtime | Truyền phạm vi qua JobParameters và dùng flow chung |
| Tạo exit code cho mọi biến thể đầu vào | Có quá nhiều transition tương tự | Gom thành các trạng thái điều phối có ý nghĩa |
| Sao chép step chung trong từng nhánh | Lặp cấu hình và dễ lệch khi sửa | Hội tụ các nhánh về step dùng chung |
| Đưa toàn bộ logic nghiệp vụ vào decider | Decider khó kiểm thử và khó đọc | Tách policy/service, decider chỉ chọn route |
| Dùng flow cho lỗi có thể retry/skip | Flow có nhiều nhánh kỹ thuật không cần thiết | Dùng fault tolerance ở cấp step |
| Dùng wildcard để mọi kết quả đều hoàn tất | Lỗi ngoài dự kiến bị che giấu | Dùng nhánh dự phòng có hành vi an toàn, thường là fail |
| Tạo quá nhiều subflow nhỏ | Cấu hình bị lồng nhiều tầng | Chỉ tách nhóm step có trách nhiệm rõ ràng |
| Dùng split cho các step phụ thuộc dữ liệu | Race condition hoặc kết quả không nhất quán | Chỉ chạy song song các flow độc lập |

## Kết luận

Không nên biến mọi điều kiện nghiệp vụ thành một nhánh trong Spring Batch job flow. Hãy giữ đường đi chính tuyến tính, dùng số exit code nhỏ và có ý nghĩa, chuyển quyết định runtime phức tạp vào policy service hoặc `JobExecutionDecider`, và hội tụ các nhánh về step dùng chung khi có thể.

Flow con giúp đóng gói một nhóm step đủ lớn để tái sử dụng; `split()` chỉ phù hợp với các luồng độc lập có thể chạy song song. Retry, skip và filter nên xử lý ở cấp step hoặc item khi chúng không làm thay đổi quy trình. Một flow tốt cho thấy rõ các giai đoạn chính, có đường đi và kết thúc xác định, đồng thời vẫn dễ kiểm thử và restart khi có lỗi.
