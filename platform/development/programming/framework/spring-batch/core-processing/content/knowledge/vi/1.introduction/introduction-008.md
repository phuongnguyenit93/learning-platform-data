# Khi dùng chunk processing và khi dùng tasklet

Trong Spring Batch, một `Step` là đơn vị thực thi chính của một Job. Mỗi Step cần một cách tổ chức công việc: có thể xử lý dữ liệu theo từng nhóm bản ghi bằng **chunk-oriented processing**, hoặc thực hiện một tác vụ bằng **Tasklet**. Hai cách này đều có thể chạy trong một Job, dùng transaction và được Spring Batch quản lý trạng thái thực thi, nhưng chúng phù hợp với hai kiểu công việc khác nhau.

Quyết định quan trọng nhất là nhìn vào bản chất của công việc:

- Nếu công việc là đọc nhiều bản ghi, kiểm tra hoặc chuyển đổi từng bản ghi rồi ghi kết quả theo từng lô, hãy ưu tiên chunk processing.
- Nếu công việc là một thao tác có ý nghĩa độc lập như chuẩn bị dữ liệu, gọi một thủ tục cơ sở dữ liệu, dọn dẹp bảng hoặc di chuyển một tệp, hãy ưu tiên Tasklet.

Không nên chọn chỉ dựa vào số dòng code hoặc tên thao tác. Hãy xem xét đơn vị công việc, ranh giới transaction, cách xử lý lỗi và yêu cầu chạy lại khi Job bị gián đoạn.

## 1. Hai mô hình xử lý trong Spring Batch

### Chunk-oriented processing

Chunk processing chia dữ liệu đầu vào thành các nhóm có kích thước xác định. Với mỗi nhóm, Spring Batch thực hiện chu trình đọc, xử lý và ghi:

1. `ItemReader` đọc từng item từ nguồn dữ liệu.
2. `ItemProcessor` xử lý một item, chẳng hạn kiểm tra hợp lệ, chuẩn hóa hoặc chuyển đổi kiểu dữ liệu.
3. `ItemWriter` ghi các item đã xử lý thành một nhóm.
4. Khi nhóm hoàn tất, transaction của chunk được commit. Nếu có lỗi khiến transaction rollback, các thay đổi thuộc transaction đó được hoàn tác.
5. Step tiếp tục với nhóm tiếp theo cho đến khi reader báo hết dữ liệu.

Kích thước chunk thường được cấu hình bằng `chunk(n, transactionManager)`. Giá trị `n` là commit interval: số item được gom cho một lần xử lý và commit. Ví dụ, `chunk(500, transactionManager)` yêu cầu Spring Batch xử lý dữ liệu theo các nhóm khoảng 500 item trước mỗi lần commit. Nhóm cuối cùng có thể nhỏ hơn nếu nguồn dữ liệu đã hết.

```text
Nguồn dữ liệu
     |
     v
  ItemReader -- đọc item
     |
     v
 ItemProcessor -- xử lý từng item
     |
     v
  ItemWriter -- ghi cả chunk
     |
     v
 Commit transaction
     |
     +------> Chunk tiếp theo
```

Nếu processor trả về `null`, item đó được lọc và không được chuyển đến writer. Đây là cách loại bỏ bản ghi có chủ đích; nó khác với việc ném exception để báo lỗi. Khi reader không còn item, nó trả về `null` để kết thúc phần đọc.

Điểm mạnh của chunk processing là Spring Batch đã cung cấp sẵn cấu trúc cho việc xử lý theo item, commit theo lô, lưu trạng thái và cấu hình skip/retry. Người phát triển tập trung vào logic đọc, xử lý và ghi thay vì tự viết vòng lặp điều phối toàn bộ bản ghi.

### Tasklet

Tasklet phù hợp với một tác vụ được mô tả như một đơn vị công việc. Spring Batch gọi phương thức `execute` của Tasklet và nhận về `RepeatStatus` để biết có cần gọi tiếp hay không:

- `RepeatStatus.FINISHED`: tác vụ đã hoàn tất; Step có thể kết thúc bình thường.
- `RepeatStatus.CONTINUABLE`: Tasklet còn việc cần làm; Spring Batch sẽ gọi lại Tasklet.

Mỗi lần gọi Tasklet được thực hiện trong transaction do Step cấu hình. Nếu Tasklet chỉ thực hiện một thao tác, nó thường trả về `FINISHED`. Nếu cần chia một tác vụ thành nhiều lượt, Tasklet có thể trả về `CONTINUABLE` và lưu tiến độ để có thể tiếp tục sau đó.

Ví dụ, một Step có thể gọi dịch vụ dọn các bản ghi hết hạn:

```java
@Bean
Step cleanupExpiredDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupService cleanupService) {

    return new StepBuilder("cleanupExpiredDataStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                cleanupService.deleteExpiredRecords();
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Tasklet không yêu cầu phải có `ItemReader`, `ItemProcessor` hay `ItemWriter`. Logic của tác vụ nằm trong `execute` hoặc được ủy quyền cho một service. Điều này khiến Tasklet phù hợp với công việc không tự nhiên biểu diễn thành một luồng item.

## 2. Khi nào nên dùng chunk processing?

Chọn chunk processing khi dữ liệu có thể được xem như một tập hợp các item và mỗi item cần đi qua một quy trình tương đối nhất quán.

### Xử lý nhiều bản ghi theo cùng một quy tắc

Các ví dụ điển hình gồm:

- Đọc đơn hàng từ CSV, kiểm tra dữ liệu và lưu vào cơ sở dữ liệu.
- Đọc giao dịch từ một bảng staging, tính phí và ghi kết quả sang bảng nghiệp vụ.
- Đồng bộ danh sách khách hàng từ một hệ thống nguồn sang hệ thống đích.
- Đọc dữ liệu nhân sự, chuẩn hóa mã phòng ban rồi cập nhật hệ thống.
- Tính toán số dư hoặc tổng hợp dữ liệu cho từng tài khoản.

Trong các trường hợp này, từng bản ghi có thể được đọc, xử lý và ghi riêng về mặt logic, trong khi nhiều bản ghi được commit cùng nhau để giảm chi phí transaction và thao tác I/O.

### Cần kiểm soát transaction theo nhóm

Chunk là lựa chọn phù hợp khi muốn một nhóm bản ghi thành công hoặc rollback cùng nhau trong transaction của chunk. Ví dụ, với commit interval là 100, nếu lỗi ghi xảy ra trước khi commit, các thay đổi thuộc transaction hiện tại có thể được rollback. Các chunk đã commit trước đó vẫn được giữ lại.

Ranh giới này có ý nghĩa trực tiếp với yêu cầu nghiệp vụ. Nếu hệ thống chấp nhận rằng 100 bản ghi được xử lý như một đơn vị commit, chunk processing diễn đạt yêu cầu đó rõ ràng.

### Cần skip hoặc retry theo item

Chunk processing cung cấp cơ chế fault tolerance ở cấp item. Tùy loại lỗi và cấu hình, Step có thể bỏ qua một số item không hợp lệ hoặc thử lại thao tác gặp lỗi tạm thời.

Ví dụ cấu hình minh họa:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Trong ví dụ này, lỗi dữ liệu thuộc `InvalidOrderException` có thể được skip trong giới hạn đã đặt; lỗi truy cập dữ liệu tạm thời có thể được retry. Cần chọn loại exception, giới hạn và chính sách rollback theo hành vi thật của ứng dụng. Không nên skip một lỗi hệ thống hoặc lỗi dữ liệu quan trọng chỉ để Job có trạng thái thành công.

### Cần khả năng restart trên một tập dữ liệu lớn

Các reader và writer triển khai `ItemStream` có thể lưu và khôi phục trạng thái thông qua `ExecutionContext`. Khi được cấu hình đúng và có trạng thái có thể khôi phục, Spring Batch có thể tiếp tục xử lý từ vị trí phù hợp sau khi Job bị gián đoạn, thay vì phải tự xây dựng toàn bộ cơ chế đánh dấu từng bản ghi.

Khả năng restart không tự động giải quyết mọi trường hợp. Reader phải hỗ trợ lưu trạng thái; dữ liệu nguồn cần có cách xác định vị trí đọc ổn định; thao tác ghi cần được thiết kế để tránh tạo dữ liệu trùng khi chạy lại. Ví dụ, đọc theo thứ tự ổn định với khóa hoặc cursor rõ ràng thường an toàn hơn đọc một tập dữ liệu không có thứ tự xác định.

### Ví dụ Step xử lý đơn hàng theo chunk

Đoạn code dưới đây thể hiện cấu trúc một Step trong Spring Batch 5.x. Các bean reader, processor và writer được cấu hình riêng theo nguồn dữ liệu và mô hình của ứng dụng:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Luồng dữ liệu có thể được hiểu như sau:

| Thành phần | Trách nhiệm trong ví dụ |
|---|---|
| `ItemReader<OrderInput>` | Đọc dữ liệu đơn hàng đầu vào, chẳng hạn từ CSV hoặc bảng staging. |
| `ItemProcessor<OrderInput, Order>` | Kiểm tra và chuyển `OrderInput` thành đối tượng `Order` phù hợp với nghiệp vụ. |
| `ItemWriter<Order>` | Ghi một nhóm `Order` đã xử lý vào cơ sở dữ liệu hoặc đích dữ liệu khác. |
| `chunk(500, transactionManager)` | Đặt commit interval là 500 item và dùng transaction manager đã chỉ định. |

Đây là mô hình phù hợp nếu mỗi đơn hàng cần được xử lý độc lập, có thể phát sinh lỗi dữ liệu riêng và cần được ghi theo từng nhóm.

## 3. Khi nào nên dùng Tasklet?

Chọn Tasklet khi công việc được mô tả tự nhiên bằng một hành động hoặc một quy trình ngắn, không cần pipeline đọc-xử lý-ghi cho từng item.

### Chuẩn bị hoặc hoàn tất dữ liệu

Ví dụ:

- Xóa dữ liệu tạm trước khi bắt đầu import.
- Tạo bảng staging hoặc chuẩn bị cấu trúc dữ liệu cho một lần chạy.
- Cập nhật trạng thái của một đợt xử lý.
- Đóng tệp, chuyển tệp đã xử lý sang thư mục lưu trữ hoặc tạo tệp báo cáo cuối cùng.
- Dọn tài nguyên sau khi các Step xử lý dữ liệu đã hoàn tất.

Các thao tác này thường có đầu vào và đầu ra ở cấp tác vụ, thay vì hàng nghìn item cần được xử lý riêng lẻ.

### Gọi một thao tác ở cấp hệ thống hoặc cơ sở dữ liệu

Tasklet thường phù hợp để:

- Gọi stored procedure thực hiện một nghiệp vụ đã được đóng gói trong cơ sở dữ liệu.
- Thực hiện một câu SQL dạng set-based để cập nhật hoặc xóa một tập bản ghi.
- Gọi một service để khởi tạo hoặc chốt một đợt nghiệp vụ.
- Kiểm tra điều kiện tiền xử lý trước khi cho phép Step tiếp theo chạy.

Ví dụ, nếu một stored procedure xử lý toàn bộ tập dữ liệu và ứng dụng chỉ cần gọi nó một lần, Tasklet biểu đạt công việc rõ ràng hơn việc tạo reader và writer giả chỉ để bọc một lời gọi.

Tuy nhiên, một câu SQL tác động đến hàng triệu dòng vẫn có thể tạo transaction dài, khóa nhiều dữ liệu hoặc gây áp lực lên cơ sở dữ liệu. Việc dùng Tasklet không tự làm thao tác đó nhẹ hơn. Nếu cần chia nhỏ dữ liệu, kiểm soát lỗi theo bản ghi hoặc checkpoint theo lô, hãy cân nhắc chunk processing hoặc cơ chế phân vùng phù hợp.

### Chạy một lệnh hoặc thao tác trên tệp

Tasklet cũng phù hợp với các công việc như kiểm tra sự tồn tại của tệp, giải nén, đổi tên, di chuyển hoặc tạo tệp đánh dấu hoàn tất. Những thao tác này không nhất thiết có cấu trúc item để đưa qua `ItemProcessor` và `ItemWriter`.

Khi làm việc với hệ thống tệp, cần tính đến trường hợp thao tác đã hoàn thành nhưng Job bị dừng trước khi trạng thái Step được lưu. Có thể thiết kế tên tệp đích ổn định, kiểm tra điều kiện tồn tại và làm cho thao tác chạy lại an toàn.

### Ví dụ Tasklet gọi stored procedure

```java
@Bean
Step refreshSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("refreshSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("call refresh_daily_summary()");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Đây là ví dụ minh họa cho một thao tác cơ sở dữ liệu được gọi một lần. Cú pháp gọi stored procedure phụ thuộc vào hệ quản trị cơ sở dữ liệu và cách ứng dụng cấu hình JDBC. Nếu stored procedure tự quản lý transaction hoặc thực hiện thao tác ngoài transaction hiện tại, cần hiểu rõ ranh giới transaction thực tế.

## 4. So sánh chunk processing và Tasklet

| Tiêu chí | Chunk processing | Tasklet |
|---|---|---|
| Đơn vị công việc | Một nhóm item được đọc, xử lý và ghi. | Một tác vụ do phương thức `execute` thực hiện. |
| Cấu trúc chính | `ItemReader`, `ItemProcessor`, `ItemWriter`. | `Tasklet.execute`. |
| Cách lặp | Spring Batch lặp qua các item và các chunk cho đến khi hết dữ liệu. | Spring Batch gọi lại Tasklet khi kết quả là `CONTINUABLE`. |
| Ranh giới transaction | Thông thường một transaction cho mỗi chunk. | Một transaction cho mỗi lần gọi Tasklet. |
| Lỗi theo bản ghi | Có cơ chế skip/retry tích hợp ở cấp item trong chunk step. | Ứng dụng tự thiết kế xử lý lỗi bên trong tác vụ. |
| Trạng thái khi restart | Reader/Writer hỗ trợ `ItemStream` có thể lưu trạng thái trong `ExecutionContext`. | Tác vụ tự lưu checkpoint cần thiết vào `ExecutionContext` hoặc cơ chế bền vững khác. |
| Trường hợp điển hình | Import, export, đồng bộ, chuyển đổi và xử lý hàng loạt bản ghi. | Dọn dữ liệu, gọi stored procedure, chuẩn bị tài nguyên, thao tác tệp hoặc gọi một service. |

Điểm khác biệt cốt lõi là chunk processing đã cung cấp mô hình xử lý item cùng các cơ chế liên quan. Với Tasklet, ứng dụng chịu trách nhiệm tổ chức logic bên trong tác vụ. Tasklet vẫn có thể lặp nhiều lần, nhưng việc lặp đó không tự cung cấp đầy đủ các tính năng đọc, xử lý, ghi và fault tolerance theo item như chunk step.

## 5. Cách chọn trong các tình huống dễ nhầm lẫn

### Một câu SQL cập nhật nhiều dòng

Nếu yêu cầu chỉ là gọi một câu SQL set-based hoặc một stored procedure đã được thiết kế để xử lý tập dữ liệu, Tasklet thường là lựa chọn hợp lý. Cơ sở dữ liệu tự thực hiện phép cập nhật theo tập hợp và Step quản lý lời gọi đó như một tác vụ.

Nếu cần đọc từng dòng, áp dụng quy tắc Java khác nhau cho từng dòng, ghi kết quả và xử lý lỗi riêng cho từng bản ghi, chunk processing phù hợp hơn.

### Xử lý tệp lớn

Nếu cần đọc từng dòng của tệp, kiểm tra nội dung và ghi từng bản ghi sang cơ sở dữ liệu, dùng chunk processing. Nếu chỉ cần di chuyển hoặc đổi tên tệp sau khi một Step khác hoàn tất, dùng Tasklet.

Nếu cần giải nén một tệp rất lớn, hãy xác định thao tác giải nén có thể hoàn tất như một tác vụ độc lập hay cần chia thành các đơn vị có thể tiếp tục. Tasklet phù hợp cho một lần giải nén có thể chạy lại an toàn; nếu cần theo dõi và khôi phục từng phần, cần thiết kế checkpoint riêng hoặc một mô hình xử lý theo item.

### Gọi API cho từng bản ghi

Nếu mỗi item cần gọi API, biến đổi phản hồi và lưu kết quả, chunk processing thường giúp tổ chức luồng item, giới hạn số lần xử lý mỗi chunk và kết hợp chính sách retry. Cần chú ý giới hạn tốc độ, timeout và tính lặp an toàn của API.

Nếu chỉ gọi một API để bắt đầu hoặc chốt một đợt xử lý, Tasklet thường phù hợp. Vì HTTP call không nằm trong transaction cơ sở dữ liệu thông thường, rollback database không thể tự hoàn tác một yêu cầu đã được hệ thống bên ngoài tiếp nhận. Hãy dùng idempotency key, trạng thái nghiệp vụ hoặc cơ chế đối soát khi cần bảo đảm chạy lại an toàn.

### Một Step cần nhiều giai đoạn

Không cần ép mọi giai đoạn vào cùng một kiểu Step. Một Job có thể kết hợp Tasklet và chunk processing theo đúng trình tự nghiệp vụ:

```text
Job: import-orders
  |
  v
Tasklet Step: kiểm tra và chuẩn bị nguồn dữ liệu
  |
  v
Chunk Step: đọc, kiểm tra, chuyển đổi và lưu từng đơn hàng
  |
  v
Tasklet Step: lưu báo cáo, lưu trữ tệp đầu vào và dọn tài nguyên
```

Ví dụ, Tasklet đầu tiên có thể kiểm tra tệp đầu vào và tạo bảng staging; chunk Step xử lý từng đơn hàng; Tasklet cuối cùng di chuyển tệp đã xử lý sang thư mục archive. Cách kết hợp này giúp mỗi Step có trách nhiệm rõ ràng và phù hợp với bản chất công việc.

## 6. Chọn commit interval cho chunk processing

Khi đã chọn chunk processing, cần chọn kích thước chunk phù hợp. Không có một con số tối ưu cho mọi ứng dụng. Chunk quá nhỏ có thể làm tăng số lần commit và chi phí giao tiếp với cơ sở dữ liệu. Chunk quá lớn có thể làm tăng bộ nhớ sử dụng, thời gian giữ transaction và lượng công việc phải thực hiện lại khi rollback.

Các yếu tố nên xem xét:

- **Kích thước item:** item lớn hoặc chứa nhiều dữ liệu có thể khiến chunk lớn tiêu thụ nhiều bộ nhớ.
- **Chi phí đọc và ghi:** writer hỗ trợ batch insert/update có thể hoạt động hiệu quả với nhóm item lớn hơn ghi từng dòng.
- **Thời gian transaction:** transaction dài có thể giữ khóa lâu, làm tăng cạnh tranh tài nguyên và ảnh hưởng các giao dịch khác.
- **Chi phí rollback và retry:** chunk lớn làm tăng số item có thể phải xử lý lại khi transaction thất bại.
- **Giới hạn của hệ thống đích:** database, API hoặc dịch vụ ghi có thể có giới hạn về kích thước batch và tốc độ tiếp nhận.
- **Yêu cầu nghiệp vụ:** nếu cần commit thường xuyên để giảm lượng công việc có thể mất khi lỗi, hãy chọn commit interval nhỏ hơn.

Có thể bắt đầu bằng một giá trị vừa phải, đo thời gian chạy, bộ nhớ, thời gian transaction và tải của hệ thống đích, sau đó điều chỉnh bằng dữ liệu thực tế. Đừng tăng chunk size chỉ vì muốn giảm số lần commit nếu điều đó làm transaction quá dài hoặc tăng rủi ro khi chạy lại.

## 7. Transaction và tác dụng phụ bên ngoài

Cả chunk step và Tasklet step đều có thể chạy trong transaction được cấu hình với `PlatformTransactionManager`. Tuy nhiên, transaction chỉ bảo đảm rollback cho các tài nguyên tham gia transaction đó. Ví dụ, một transaction JDBC có thể rollback thay đổi trong cơ sở dữ liệu được quản lý bởi transaction manager tương ứng; nó không tự khôi phục một tệp đã đổi tên hoặc một email đã gửi.

Vì vậy, khi Step kết hợp nhiều loại tác dụng phụ, cần thiết kế thứ tự và khả năng chạy lại cẩn thận. Một số nguyên tắc hữu ích:

- Ưu tiên thao tác idempotent: chạy lại cùng một yêu cầu không tạo ra kết quả sai hoặc dữ liệu trùng.
- Dùng khóa nghiệp vụ hoặc khóa duy nhất để ngăn ghi trùng khi Job được restart.
- Ghi nhận trạng thái xử lý rõ ràng để có thể đối soát sau lỗi.
- Với sự kiện cần phát ra cùng thay đổi database, cân nhắc transactional outbox hoặc một cơ chế phối hợp phù hợp.
- Không giả định rằng transaction rollback sẽ hoàn tác được mọi thao tác đã gọi đến hệ thống bên ngoài.

Trong chunk processing, nếu writer vừa ghi database vừa gọi API ngoài, transaction database không thể rollback API call. Nếu chunk rollback và Spring Batch retry, API có thể bị gọi nhiều lần. Có thể cần tách việc phát sự kiện thành Step riêng, dùng outbox hoặc bảo đảm API nhận yêu cầu có tính idempotent.

## 8. Tasklet lặp nhiều lần và checkpoint

Tasklet có thể trả về `CONTINUABLE` để Spring Batch gọi lại `execute`. Cách này hữu ích khi tác vụ gồm một số lượt công việc có giới hạn, ví dụ xử lý từng trang dữ liệu hoặc gọi một thao tác theo từng phân đoạn. Tuy nhiên, Tasklet không tự biết đã xử lý đến item nào. Nếu cần restart chính xác, ứng dụng phải lưu checkpoint và thiết kế mỗi lượt xử lý có thể chạy lại an toàn.

Ví dụ khung ý tưởng cho một Tasklet xử lý từng trang:

```java
.tasklet((contribution, chunkContext) -> {
    ExecutionContext executionContext = contribution
            .getStepExecution()
            .getExecutionContext();

    int page = executionContext.getInt("currentPage", 0);
    boolean hasMore = migrationService.processPage(page);

    if (hasMore) {
        executionContext.putInt("currentPage", page + 1);
        return RepeatStatus.CONTINUABLE;
    }

    return RepeatStatus.FINISHED;
}, transactionManager)
```

Đây là khung minh họa, cần bổ sung xử lý lỗi, điều kiện kết thúc và cơ chế phân trang ổn định theo dữ liệu thực tế. Checkpoint phải được cập nhật nhất quán với phần công việc đã hoàn tất. Nếu tác vụ thay đổi dữ liệu ngoài transaction hiện tại, cần thêm cơ chế chống thực hiện trùng khi một lượt bị chạy lại.

Nếu công việc thực chất là xử lý một luồng item lớn với yêu cầu skip/retry theo item, reader/writer có trạng thái và commit interval, hãy dùng chunk processing thay vì tự xây lại các cơ chế này trong một Tasklet.

## 9. Những lỗi thiết kế thường gặp

### Dùng Tasklet cho một vòng lặp hàng triệu bản ghi

Một Tasklet có thể chứa vòng lặp đọc và ghi dữ liệu, nhưng khi đó ứng dụng phải tự quản lý phân trang, checkpoint, transaction, retry, skip, logging và khôi phục sau lỗi. Nếu nghiệp vụ là xử lý từng item, chunk processing thường đơn giản và dễ vận hành hơn.

### Dùng chunk chỉ để gọi một thao tác duy nhất

Nếu một Step chỉ gọi một stored procedure hoặc thực hiện một thao tác chuẩn bị, việc tạo reader trả về đúng một item và writer gọi service có thể làm cấu trúc khó hiểu. Tasklet diễn đạt trực tiếp ý nghĩa của tác vụ hơn.

### Nghĩ rằng chunk size là số bản ghi chắc chắn được ghi

Commit interval mô tả số item trong chu trình chunk. Processor có thể lọc item bằng cách trả về `null`, và chính sách skip cũng có thể làm số item được ghi ít hơn số item đã đọc. Vì vậy, số item được writer nhận có thể khác commit interval.

### Cho rằng mọi lỗi đều được retry an toàn

Retry chỉ phù hợp với lỗi có khả năng tạm thời và thao tác có thể thực hiện lại an toàn. Retry một thao tác không idempotent có thể tạo bản ghi trùng hoặc lặp tác dụng phụ. Cần xác định loại exception, giới hạn retry và hành vi transaction trước khi bật retry.

### Cho rằng Tasklet luôn chỉ chạy một lần

Tasklet có thể được gọi nhiều lần nếu trả về `CONTINUABLE`. Khi đó cần quản lý tiến độ và trạng thái. `FINISHED` mới là tín hiệu kết thúc vòng lặp Tasklet.

### Bỏ qua trạng thái và khả năng chạy lại

Job có thể thất bại sau khi một phần công việc đã được thực hiện. Dù dùng chunk hay Tasklet, cần xác định điều gì xảy ra khi chạy lại: dữ liệu nào đã commit, thao tác nào có thể lặp, checkpoint nằm ở đâu và có thể đối soát bằng cách nào.

## 10. Quy trình ra quyết định

Có thể dùng các câu hỏi sau khi thiết kế một Step:

1. **Công việc có phải xử lý nhiều item theo cùng một pipeline không?** Nếu có, chunk processing thường là điểm bắt đầu phù hợp.
2. **Mỗi item có cần đọc, kiểm tra/chuyển đổi và ghi riêng không?** Nếu có, dùng `ItemReader`, `ItemProcessor` và `ItemWriter`.
3. **Cần commit theo nhóm và xử lý skip/retry ở cấp item không?** Nếu có, chunk processing cung cấp các cơ chế phù hợp.
4. **Công việc chỉ là một thao tác độc lập hoặc một lời gọi cấp hệ thống không có pipeline item?** Nếu có, dùng Tasklet.
5. **Tác vụ có thể bị chạy lại sau khi đã tạo tác dụng phụ không?** Nếu có, thiết kế idempotency, checkpoint hoặc đối soát trước khi triển khai.
6. **Một Step đang làm nhiều việc có bản chất khác nhau không?** Nếu có, tách thành nhiều Step và kết hợp Tasklet với chunk processing trong cùng Job.

| Nhu cầu chính | Lựa chọn thường phù hợp |
|---|---|
| Import hàng nghìn dòng CSV, validate từng dòng và ghi database | Chunk processing |
| Đọc bảng staging, chuyển đổi từng bản ghi và cập nhật bảng đích | Chunk processing |
| Skip bản ghi sai định dạng và retry lỗi ghi tạm thời | Chunk processing |
| Gọi một stored procedure để làm mới bảng tổng hợp | Tasklet |
| Xóa dữ liệu tạm trước khi import | Tasklet |
| Di chuyển tệp đầu vào sau khi import thành công | Tasklet |
| Gọi API một lần để bắt đầu một đợt xử lý | Tasklet |
| Gọi API cho từng bản ghi và lưu phản hồi | Chunk processing, kèm thiết kế retry/idempotency phù hợp |

## Kết luận

Chunk processing phù hợp với luồng dữ liệu gồm nhiều item cần đọc, xử lý và ghi theo nhóm, đặc biệt khi cần commit interval, restart và fault tolerance ở cấp item. Tasklet phù hợp với một tác vụ độc lập như chuẩn bị dữ liệu, gọi stored procedure, dọn dẹp hoặc thao tác tệp. Một Job có thể kết hợp cả hai: dùng Tasklet cho các bước điều phối hoặc thao tác cấp hệ thống, và dùng chunk processing cho phần xử lý dữ liệu theo bản ghi.
