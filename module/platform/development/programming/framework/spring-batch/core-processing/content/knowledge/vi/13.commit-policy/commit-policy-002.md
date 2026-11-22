# CompletionPolicy

Trong Spring Batch, `CompletionPolicy` là cơ chế xác định khi nào một chu kỳ lặp hoặc một chunk được xem là hoàn tất. Với chunk-oriented Step, policy quyết định khi nào Spring Batch dừng gom item cho chunk hiện tại để chuyển sang giai đoạn ghi và commit transaction.

Khi cấu hình `.chunk(500, transactionManager)`, ứng dụng đang dùng quy tắc hoàn tất theo số lượng item cố định. `CompletionPolicy` cho phép mô tả quy tắc linh hoạt hơn, chẳng hạn kết thúc chunk khi đã xử lý đủ số item, khi đã đạt một khoảng thời gian hoặc khi một điều kiện tùy chỉnh được thỏa mãn.

Điều quan trọng là `CompletionPolicy` điều khiển ranh giới của một lần lặp/chunk. Nó không quyết định Job đã thành công hay Step có `BatchStatus.COMPLETED` hay không. Kết quả thực thi Job và Step vẫn được quản lý bởi trạng thái, exit status và các cơ chế khác của Spring Batch.

## 1. CompletionPolicy nằm ở đâu trong chunk processing?

Chunk-oriented processing gom nhiều item thành một nhóm. Spring Batch đọc item, chuyển qua processor nếu có, đưa kết quả phù hợp đến writer rồi commit transaction của chunk. `CompletionPolicy` xác định khi nào nhóm hiện tại đã đủ điều kiện kết thúc.

```text
Job
 |
 v
Chunk-oriented Step
 |
 v
CompletionPolicy bắt đầu chu kỳ
 |
 +--> ItemReader đọc item
 |       |
 |       v
 |    ItemProcessor xử lý item
 |       |
 |       v
 |    Thêm kết quả vào chunk
 |       |
 |       v
 |    CompletionPolicy kiểm tra điều kiện
 |       |
 |       +-- Chưa hoàn tất --> Đọc item tiếp theo
 |       |
 |       +-- Hoàn tất ------> ItemWriter ghi chunk
 |                              |
 |                              v
 |                         Commit transaction
 |
 +--> Bắt đầu chunk tiếp theo
```

Nếu policy báo chunk chưa hoàn tất, Step tiếp tục thu thập item. Khi policy báo hoàn tất, chunk được chuyển sang writer và transaction được commit theo cơ chế của Step. Nếu reader báo hết dữ liệu trước khi đạt điều kiện, Spring Batch vẫn phải kết thúc phần dữ liệu còn lại và hoàn tất Step.

## 2. Vì sao cần CompletionPolicy?

Không phải mọi nguồn dữ liệu hoặc workload đều phù hợp với một commit interval cố định. Ví dụ:

- Một hệ thống có thể muốn commit sau mỗi 500 item để đạt throughput ổn định.
- Một nguồn dữ liệu có tốc độ không đều có thể cần giới hạn thời gian gom item trong một chunk.
- Một ứng dụng có thể muốn dừng chunk khi số item hoặc thời gian xử lý chạm ngưỡng.
- Một quy tắc nghiệp vụ hoặc kỹ thuật đặc thù có thể yêu cầu chunk kết thúc theo điều kiện riêng.

`CompletionPolicy` tách quy tắc “khi nào chunk kết thúc” khỏi reader, processor và writer. Reader tập trung đọc dữ liệu, processor tập trung xử lý từng item, writer tập trung ghi kết quả, còn policy quyết định ranh giới chunk.

Với nhiều Job đơn giản, chunk size cố định đã đủ. Chỉ nên dùng policy tùy chỉnh khi có yêu cầu cụ thể mà commit interval cố định không diễn đạt tốt.

## 3. Commit interval cố định và SimpleCompletionPolicy

Khi khai báo chunk bằng số nguyên:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

Spring Batch sử dụng quy tắc hoàn tất theo số item cố định. Đây là lựa chọn phổ biến vì dễ hiểu và dễ dự đoán: mỗi chunk gom tối đa 500 item trước khi writer ghi và transaction commit. Chunk cuối có thể ít hơn 500 item nếu nguồn dữ liệu đã hết.

Có thể diễn đạt rõ quy tắc đếm bằng `SimpleCompletionPolicy`:

```java
CompletionPolicy completionPolicy = new SimpleCompletionPolicy(500);

return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(completionPolicy, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

`SimpleCompletionPolicy` kết thúc chunk sau số lần lặp/item đã cấu hình. Trong ví dụ, policy dùng ngưỡng 500. Về ý nghĩa, cách này tương đương với việc chọn commit interval cố định bằng 500.

Nên dùng commit interval cố định khi:

- Kích thước item tương đối đồng đều.
- Chi phí đọc và ghi trên mỗi item tương đối ổn định.
- Hệ thống cần throughput dễ dự đoán.
- Yêu cầu transaction có thể được biểu diễn bằng số item trong mỗi chunk.

## 4. Cấu hình CompletionPolicy trực tiếp cho Step

Trong Spring Batch 5, `StepBuilder` hỗ trợ nhận một `CompletionPolicy` cùng transaction manager. Có thể khai báo policy thành bean để tái sử dụng hoặc kiểm soát cấu hình tập trung:

```java
@Bean
CompletionPolicy orderChunkPolicy() {
    return new SimpleCompletionPolicy(300);
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy orderChunkPolicy,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(orderChunkPolicy, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Policy được cung cấp cho Step khi xây dựng cấu hình. Trong ví dụ, mỗi chunk được kết thúc theo ngưỡng 300 lần lặp/item. Nếu dùng policy bean chung cho nhiều Step, cần bảo đảm policy không giữ state mutable dùng chung giữa các execution. Policy thường được tạo hoặc quản lý trong phạm vi phù hợp để mỗi chunk có context riêng.

## 5. CompletionPolicy hoạt động qua RepeatContext

`CompletionPolicy` thuộc cơ chế lặp của Spring Batch. Nó làm việc với `RepeatContext`, là ngữ cảnh lưu trạng thái của một lần lặp. Hợp đồng chính có các thao tác:

- `start(parent)`: khởi tạo context cho một chu kỳ lặp mới.
- `update(context)`: cập nhật trạng thái sau một lần thực thi.
- `isComplete(context)`: kiểm tra điều kiện hoàn tất dựa trên context.
- `isComplete(context, result)`: kiểm tra hoàn tất có xét đến kết quả của lần lặp.

Spring Batch gọi các phương thức này trong vòng đời điều phối lặp. Policy có thể lưu bộ đếm hoặc mốc thời gian trong context để quyết định khi nào dừng.

`RepeatContext` không phải `ExecutionContext`. Hai đối tượng có mục đích khác nhau:

| Đối tượng | Vai trò |
|---|---|
| `RepeatContext` | Giữ trạng thái của một vòng lặp đang diễn ra để CompletionPolicy quyết định khi nào kết thúc. |
| `ExecutionContext` | Lưu trạng thái thực thi bền vững của Job hoặc Step, thường dùng cho checkpoint và restart. |

Không nên dùng `RepeatContext` như kho checkpoint lâu dài. Khi cần tiếp tục công việc sau khi tiến trình dừng, hãy sử dụng `ExecutionContext` và các cơ chế `ItemStream` phù hợp.

## 6. TimeoutTerminationPolicy: kết thúc theo thời gian

Một số workload cần giới hạn thời gian gom item trong một chunk. `TimeoutTerminationPolicy` là một policy có sẵn để kết thúc vòng lặp khi khoảng thời gian cấu hình đã trôi qua.

Ví dụ, muốn kết thúc chunk sau khoảng 30 giây:

```java
@Bean
CompletionPolicy timeBasedChunkPolicy() {
    return new TimeoutTerminationPolicy(30_000L);
}

@Bean
Step processEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy timeBasedChunkPolicy,
        ItemReader<EventInput> eventReader,
        ItemProcessor<EventInput, Event> eventProcessor,
        ItemWriter<Event> eventWriter) {

    return new StepBuilder("processEventsStep", jobRepository)
            .<EventInput, Event>chunk(timeBasedChunkPolicy, transactionManager)
            .reader(eventReader)
            .processor(eventProcessor)
            .writer(eventWriter)
            .build();
}
```

Tham số thời gian của `TimeoutTerminationPolicy` được tính bằng millisecond. Policy kết thúc chu kỳ khi ngưỡng thời gian đã đạt. Đây là điều kiện kết thúc chunk dựa trên thời gian, không phải timeout cứng để hủy một lời gọi reader, processor hoặc writer đang chạy.

Ví dụ, nếu một lần gọi processor mất 45 giây, policy không thể tự ngắt giữa chừng chỉ vì ngưỡng 30 giây đã trôi qua. Điều kiện hoàn tất được kiểm tra tại các điểm điều phối lặp phù hợp; thao tác đang chạy cần timeout riêng nếu có nguy cơ bị treo.

Time-based policy có thể hữu ích khi tốc độ item biến động và ứng dụng muốn giới hạn thời gian gom chunk. Tuy nhiên, nó không đảm bảo mỗi chunk có cùng số item. Khi item xử lý nhanh, chunk có thể chứa nhiều item; khi item xử lý chậm, chunk có thể chứa ít item.

## 7. Kết hợp giới hạn số lượng và thời gian

Trong một số hệ thống, chỉ giới hạn số item hoặc chỉ giới hạn thời gian đều chưa đủ. Ví dụ, ứng dụng muốn chunk không vượt quá 500 item và cũng không gom dữ liệu lâu hơn 30 giây.

Có thể triển khai một `CompletionPolicy` tùy chỉnh hoặc một policy tổng hợp để diễn đạt nhiều điều kiện. Khi thiết kế, cần xác định rõ ngữ nghĩa kết hợp:

- Kết thúc khi bất kỳ điều kiện nào đạt (ví dụ đủ 500 item **hoặc** quá 30 giây).
- Chỉ kết thúc khi tất cả điều kiện đạt (thường ít phù hợp với giới hạn tối đa).
- Có thêm điều kiện theo kích thước payload hoặc trạng thái nguồn dữ liệu.

Với giới hạn tối đa, cách kết hợp thường là kết thúc khi điều kiện đầu tiên đạt. Cần dùng đúng policy tổng hợp hoặc tự triển khai semantics tương ứng; không nên giả định mọi composite policy mặc định đều dùng phép OR.

Ví dụ minh họa về yêu cầu:

```text
Chunk bắt đầu
   |
   +--> Đếm item
   |
   +--> Theo dõi thời gian
   |
   +--> Đạt 500 item? ------ Có ----+
   |                                |
   +--> Quá 30 giây? ------- Có ----+--> Kết thúc chunk
   |                                |
   +--> Chưa đạt cả hai ------------+--> Tiếp tục đọc
```

Không phải mọi ứng dụng đều cần kết hợp nhiều điều kiện. Một commit interval cố định thường đơn giản hơn, dễ kiểm thử và dễ dự đoán. Chỉ tăng độ phức tạp khi có số liệu hoặc yêu cầu vận hành chứng minh cần thiết.

## 8. Viết CompletionPolicy tùy chỉnh

Khi các policy có sẵn không đáp ứng yêu cầu, có thể triển khai interface `CompletionPolicy`. Ví dụ, một ứng dụng có thể muốn kết thúc chunk khi đã gom đủ số item hoặc khi một ngưỡng tùy chỉnh được lưu trong `RepeatContext`.

Một policy tùy chỉnh cần:

1. Khởi tạo trạng thái cho mỗi lần lặp trong `start`.
2. Cập nhật trạng thái trong `update`.
3. Kiểm tra điều kiện kết thúc trong `isComplete`.
4. Xử lý trường hợp repeat result báo kết thúc hoặc nguồn không còn item.
5. Không phụ thuộc vào state mutable toàn cục có thể bị chia sẻ giữa nhiều StepExecution.

Khung hợp đồng:

```java
public interface CompletionPolicy {
    RepeatContext start(RepeatContext parent);

    void update(RepeatContext context);

    boolean isComplete(RepeatContext context);

    boolean isComplete(RepeatContext context, RepeatStatus result);
}
```

Đây là interface của Spring Batch; khi triển khai, cần dùng đúng package và API của phiên bản dependency trong dự án. Policy nên có logic nhỏ, xác định và dễ kiểm thử. Không nên thực hiện database query, gọi API hoặc thực hiện tác dụng phụ trong `isComplete`, vì phương thức có thể được gọi nhiều lần trong quá trình điều phối.

Nếu điều kiện phụ thuộc dữ liệu của item hiện tại, hãy cân nhắc nơi đặt logic. `CompletionPolicy` điều khiển ranh giới vòng lặp; nó không thay thế `ItemProcessor` và không tự nhận item như tham số trực tiếp. Có thể cập nhật thông tin cần thiết qua context theo thiết kế phù hợp, nhưng không nên biến policy thành nơi chứa toàn bộ nghiệp vụ xử lý bản ghi.

## 9. CompletionPolicy và dữ liệu cuối nguồn

Chunk không nhất thiết luôn đạt đúng kích thước hoặc thời gian mục tiêu. Nếu reader trả về `null` vì hết dữ liệu, Spring Batch kết thúc việc đọc và xử lý chunk cuối cùng với số item còn lại.

Ví dụ, chunk size là 100 nhưng nguồn chỉ còn 35 item, writer vẫn có thể nhận chunk cuối gồm 35 item. Không cần chờ đủ 100 item mới kết thúc Step.

Tương tự, với policy dựa trên thời gian, nguồn có thể hết trước khi timeout. Khi đó Step kết thúc theo tín hiệu hết dữ liệu của reader. `CompletionPolicy` xác định điều kiện hoàn tất vòng lặp, còn reader xác định khi nào không còn item để đọc.

Điều này đặc biệt quan trọng khi xử lý nguồn dữ liệu hữu hạn như tệp CSV hoặc một truy vấn database. Với nguồn liên tục hoặc polling, cần xác định thêm điều kiện dừng của reader/Step; policy thời gian không tự biến một nguồn vô hạn thành một Job có ý nghĩa nghiệp vụ nếu không có quy tắc kết thúc rõ ràng.

## 10. CompletionPolicy và filter, skip, retry

`CompletionPolicy` quyết định khi nào chunk kết thúc; filter, skip và retry quyết định cách xử lý từng item hoặc exception. Đây là các cơ chế khác nhau nhưng cùng ảnh hưởng đến kích thước và thời gian thực tế của chunk.

- **Filter:** processor trả về `null`; item không được gửi đến writer. Việc filter không đồng nghĩa policy đã hoàn tất.
- **Skip:** exception được cho phép bỏ qua; item bị loại theo fault-tolerance policy và được ghi nhận trong skip counters.
- **Retry:** framework thử lại thao tác gặp lỗi tạm thời; thời gian hoàn tất chunk có thể tăng.
- **CompletionPolicy:** kiểm tra điều kiện kết thúc chunk theo quy tắc đã cấu hình.

Ví dụ, với `SimpleCompletionPolicy(100)`, một số item có thể bị filter hoặc skip nhưng chunk vẫn được điều khiển theo policy đếm. Số item writer thực nhận có thể ít hơn số item reader đã đọc.

Nếu retry kéo dài, time-based policy có thể đạt ngưỡng thời gian trong khi Step đang xử lý. Tuy nhiên, policy không hủy một thao tác retry đang chạy; việc retry có timeout/backoff riêng và cần được cấu hình phù hợp.

## 11. CompletionPolicy và transaction commit

Khi policy báo chunk hoàn tất, Spring Batch chuyển chunk sang giai đoạn ghi và commit transaction theo cấu trúc của Step. Vì vậy, policy gián tiếp ảnh hưởng đến:

- Số item được gom trong một transaction.
- Tần suất commit.
- Thời gian giữ transaction và khóa database.
- Lượng dữ liệu có thể phải rollback khi một chunk thất bại.
- Throughput và chi phí giao tiếp với database.

Chunk lớn có thể giảm số lần commit và tận dụng batch write tốt hơn, nhưng cũng có thể tăng bộ nhớ, thời gian transaction và lượng công việc phải xử lý lại khi lỗi. Chunk nhỏ commit thường xuyên hơn nhưng có thể tăng overhead.

Với policy theo thời gian, kích thước chunk thay đổi theo tốc độ xử lý. Cần đo thời gian transaction và số item mỗi chunk thực tế để biết policy có đạt mục tiêu vận hành hay không.

## 12. CompletionPolicy không phải BatchStatus hoặc ExitStatus

Một số khái niệm có tên gần giống nhưng phục vụ mục đích khác nhau:

| Khái niệm | Câu hỏi được trả lời |
|---|---|
| `CompletionPolicy` | Khi nào một vòng lặp hoặc chunk hiện tại kết thúc? |
| `RepeatStatus` | Tasklet hoặc repeat callback có cần tiếp tục được gọi không? |
| `BatchStatus` | JobExecution hoặc StepExecution đang chạy, hoàn tất, thất bại hay dừng? |
| `ExitStatus` | Mã kết quả nào được dùng để mô tả kết quả và điều khiển flow? |
| `ExecutionContext` | Trạng thái nào cần lưu để chia sẻ hoặc khôi phục khi restart? |

Ví dụ, một chunk kết thúc và commit không có nghĩa Step đã hoàn tất. Step có thể tiếp tục xử lý nhiều chunk nữa. Khi reader hết dữ liệu, Step mới có thể kết thúc. Sau đó BatchStatus và ExitStatus phản ánh kết quả cuối cùng của Step.

## 13. Chọn policy nào cho từng workload?

| Workload | Policy thường phù hợp | Lý do |
|---|---|---|
| Import CSV với dòng có kích thước tương đối đồng đều | `SimpleCompletionPolicy` hoặc `chunk(int)` | Commit interval cố định dễ dự đoán. |
| Batch insert database theo nhóm 500 item | `SimpleCompletionPolicy(500)` | Tận dụng ghi batch và kiểm soát transaction. |
| Item đến chậm, muốn giới hạn thời gian gom chunk | `TimeoutTerminationPolicy` | Chunk kết thúc theo ngưỡng thời gian. |
| Muốn giới hạn cả số item và thời gian | Policy tổng hợp hoặc custom policy | Kết thúc khi điều kiện giới hạn phù hợp đạt. |
| Quy tắc kết thúc phụ thuộc tiêu chí riêng của ứng dụng | Custom `CompletionPolicy` | Diễn đạt logic kết thúc đặc thù. |
| Job nhỏ, dữ liệu ít và tốc độ ổn định | `chunk(int)` | Không cần tăng độ phức tạp. |

Trước khi dùng timeout hoặc policy tùy chỉnh, hãy xác định mục tiêu cụ thể. Nếu mục tiêu là timeout một truy vấn database hoặc HTTP request, cần cấu hình timeout ở reader/service/driver; CompletionPolicy chỉ điều khiển ranh giới chunk.

## 14. Đo lường và điều chỉnh CompletionPolicy

Không nên chọn ngưỡng policy chỉ theo cảm tính. Hãy quan sát dữ liệu chạy thực tế:

- Số item mỗi chunk.
- Thời gian từ lúc bắt đầu đến lúc kết thúc chunk.
- Thời gian writer và commit.
- Throughput tổng thể.
- Mức sử dụng heap và áp lực garbage collection.
- Số lần rollback, retry và skip.
- Thời gian giữ khóa và tải database.

Với policy cố định theo số lượng, có thể bắt đầu từ một chunk size vừa phải rồi đo throughput và transaction time. Với policy theo thời gian, kiểm tra phân bố số item mỗi chunk và xác nhận thời gian commit có nằm trong mục tiêu mong muốn.

Nếu writer là nút thắt, tăng chunk size có thể giúp batch write nhưng cũng có thể kéo dài transaction. Nếu processor chậm, timeout policy không thể cắt ngang một item đang xử lý. Hãy tối ưu chính thành phần chậm, dùng timeout riêng cho I/O và điều chỉnh policy dựa trên số liệu.

## 15. Kiểm thử CompletionPolicy

Policy nên được kiểm thử độc lập để xác nhận điều kiện kết thúc đúng như mong đợi.

Với `SimpleCompletionPolicy`, kiểm tra các trường hợp:

- Chunk chưa đủ số item thì policy chưa hoàn tất.
- Khi đạt số item cấu hình, policy báo hoàn tất.
- Một context mới bắt đầu bộ đếm mới.

Với `TimeoutTerminationPolicy`, kiểm tra:

- Policy chưa hoàn tất trước khi timeout.
- Policy hoàn tất sau khi ngưỡng thời gian đã trôi qua.
- Một thao tác đang chạy lâu không bị hiểu nhầm là đã bị hủy giữa chừng.

Với custom policy, cần kiểm tra:

- Context được khởi tạo riêng cho từng lần lặp.
- `update` thay đổi đúng state cần theo dõi.
- Các điều kiện kết thúc có ngữ nghĩa rõ ràng.
- EOF và repeat result kết thúc được xử lý đúng.
- Nhiều StepExecution đồng thời không chia sẻ state mutable ngoài ý muốn.

Integration test ở cấp Step có thể kiểm tra thêm số lần writer được gọi, số item mỗi chunk, commit/rollback và hành vi khi nguồn hết dữ liệu.

## 16. Những lỗi thường gặp

### Nhầm CompletionPolicy với điều kiện kết thúc Job

Policy chỉ quyết định vòng lặp/chunk hiện tại kết thúc. Job có thể còn nhiều chunk hoặc Step tiếp theo.

### Nghĩ timeout policy sẽ ngắt một item đang chạy

Timeout policy kiểm tra điều kiện hoàn tất tại các điểm điều phối. Nó không tự interrupt một lời gọi reader, processor hoặc writer đang bị block. Hãy cấu hình timeout riêng cho I/O.

### Dùng time-based policy để thay thế timeout của database

Nếu truy vấn SQL bị treo, policy không thể thay thế query timeout hoặc socket timeout. Cần đặt timeout ở driver, JDBC statement hoặc service tương ứng.

### Cho rằng chunk luôn chứa đúng số item cấu hình

Chunk cuối có thể nhỏ hơn do reader hết dữ liệu. Filter và skip cũng khiến số item writer nhận thấp hơn số item đã đọc.

### Viết custom policy giữ state trong field dùng chung

Nếu policy bean được chia sẻ giữa các execution, state mutable có thể bị trộn giữa các Job. Dùng `RepeatContext` để giữ state theo vòng lặp và kiểm soát scope của policy.

### Kết hợp nhiều điều kiện mà không xác định AND/OR

Một policy kết hợp có thể kết thúc khi một điều kiện đạt hoặc chỉ khi mọi điều kiện đạt. Hãy xác định rõ semantics và kiểm thử, nhất là với các giới hạn tối đa như số item và thời gian.

### Chọn chunk size lớn mà không đo transaction

Chunk lớn có thể làm tăng thời gian giữ khóa, bộ nhớ và lượng công việc rollback. Điều chỉnh theo throughput, transaction time và tải database.

## 17. Quy trình chọn và cấu hình CompletionPolicy

Khi thiết kế chunk Step, có thể thực hiện theo trình tự:

1. Xác định đơn vị commit mà nghiệp vụ và database có thể chấp nhận.
2. Nếu số item cố định là đủ, dùng `.chunk(n, transactionManager)`.
3. Nếu muốn mô tả rõ policy đếm, dùng `SimpleCompletionPolicy`.
4. Nếu cần kết thúc theo thời gian gom chunk, cân nhắc `TimeoutTerminationPolicy`.
5. Nếu cần nhiều điều kiện, xác định semantics OR/AND rồi chọn policy tổng hợp hoặc triển khai custom policy.
6. Giữ logic policy nhỏ, xác định và không có tác dụng phụ.
7. Cấu hình timeout riêng cho reader, processor, writer hoặc I/O nếu cần giới hạn thời gian thao tác.
8. Đo số item mỗi chunk, thời gian transaction, throughput và rollback để điều chỉnh ngưỡng.
9. Kiểm thử EOF, filter, skip, retry và execution đồng thời.

## Kết luận

`CompletionPolicy` xác định khi nào một vòng lặp hoặc chunk trong Spring Batch được xem là hoàn tất. `SimpleCompletionPolicy` phù hợp với commit interval cố định theo số item; `TimeoutTerminationPolicy` kết thúc chunk theo khoảng thời gian; policy tùy chỉnh hoặc tổng hợp có thể diễn đạt điều kiện phức tạp hơn. Policy ảnh hưởng đến kích thước chunk, tần suất commit, thời gian transaction và lượng công việc có thể phải rollback. Hãy phân biệt nó với timeout I/O, `RepeatStatus`, `BatchStatus` và `ExitStatus`, đồng thời chọn ngưỡng dựa trên số liệu vận hành thực tế.
