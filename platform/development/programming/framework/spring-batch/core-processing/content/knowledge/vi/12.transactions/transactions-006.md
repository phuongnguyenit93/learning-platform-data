# Transaction metadata và business data

Trong Spring Batch, mỗi lần chạy job tạo và cập nhật hai nhóm dữ liệu có mục đích khác nhau: **batch metadata** và **business data**. Batch metadata mô tả quá trình thực thi, còn business data là dữ liệu nghiệp vụ mà job đọc, biến đổi hoặc ghi ra hệ thống đích.

Hai nhóm dữ liệu này thường được cập nhật trong cùng một luồng xử lý. Vì vậy, thiết kế transaction phải trả lời được câu hỏi: khi một chunk hoặc một tasklet thất bại, dữ liệu nghiệp vụ và metadata checkpoint có cùng commit hoặc rollback hay không? Nếu chúng không nhất quán, lần restart có thể ghi trùng dữ liệu hoặc bỏ qua phần việc chưa hoàn tất.

Spring Batch cung cấp `JobRepository` để quản lý metadata và dùng transaction manager của step để điều phối transaction xử lý. Khi metadata và business data dùng chung transaction resource cùng transaction manager phù hợp, các thay đổi liên quan có thể commit hoặc rollback cùng nhau. Khi chúng nằm ở các resource độc lập, không có atomic commit mặc định; ứng dụng phải thiết kế idempotency, outbox hoặc cơ chế phục hồi tương ứng.

## Phân biệt batch metadata và business data

### Batch metadata

Batch metadata ghi lại danh tính và lịch sử chạy của job. Với JDBC `JobRepository`, dữ liệu thường được lưu trong các bảng Spring Batch có tiền tố `BATCH_`.

| Nhóm metadata | Ví dụ nội dung | Mục đích |
| --- | --- | --- |
| `JobInstance` | Tên job và identifying parameters | Nhận diện một logical job |
| `JobExecution` | Trạng thái, thời điểm bắt đầu/kết thúc, exit code, lỗi | Theo dõi một lần thực thi |
| `StepExecution` | Trạng thái step, số item đọc/ghi/skip/filter, commit và rollback count | Theo dõi tiến trình của step |
| `JobParameters` | Ngày nghiệp vụ, tên tệp, phạm vi dữ liệu và cờ identifying | Xác định đầu vào và danh tính lần chạy |
| `ExecutionContext` | Vị trí đọc tiếp theo, page number, khóa cuối đã xử lý | Lưu checkpoint để restart |

Các bảng metadata thường gặp gồm `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`. Tên cột, kiểu dữ liệu và schema cụ thể phụ thuộc phiên bản Spring Batch và hệ quản trị cơ sở dữ liệu.

### Business data

Business data là dữ liệu của domain mà job xử lý, ví dụ:

- Đơn hàng, giao dịch, hóa đơn hoặc thông tin khách hàng.
- Bản ghi staging được nạp từ file nguồn.
- Kết quả tính toán, số dư, báo cáo hoặc dữ liệu tổng hợp.
- Trạng thái xử lý nghiệp vụ, audit record hoặc outbox event.

Các bảng này do ứng dụng/domain thiết kế. Spring Batch không tự quyết định schema nghiệp vụ và cũng không dùng các bảng `BATCH_*` làm nơi lưu toàn bộ dữ liệu đầu vào hoặc kết quả.

Ví dụ một job nhập đơn hàng có thể sử dụng:

```text
Batch metadata database/schema          Business database/schema
-------------------------------         ------------------------
BATCH_JOB_INSTANCE                      orders
BATCH_JOB_EXECUTION                     order_items
BATCH_STEP_EXECUTION                    import_audit
BATCH_STEP_EXECUTION_CONTEXT            outbox_events
```

Hai nhóm có thể nằm trong cùng một database hoặc ở hai database riêng. Việc tách schema giúp tổ chức và phân quyền; nhưng chỉ riêng việc cùng máy chủ database hoặc cùng database name chưa đủ để bảo đảm chúng tham gia cùng một transaction.

## Vì sao transaction giữa hai nhóm dữ liệu quan trọng?

Spring Batch dùng metadata để xác định step đã xử lý đến đâu. Nếu checkpoint cho biết một nhóm item đã hoàn tất nhưng business data chưa được lưu, restart có thể bỏ qua item đó. Nếu business data đã được lưu nhưng checkpoint chưa được cập nhật, restart có thể xử lý lại item và tạo dữ liệu trùng.

Ví dụ, một chunk gồm 100 đơn hàng:

1. Reader đọc 100 đơn hàng.
2. Processor chuẩn hóa và kiểm tra dữ liệu.
3. Writer ghi 100 đơn hàng vào bảng `orders`.
4. Spring Batch cập nhật số liệu `StepExecution` và checkpoint trong `ExecutionContext`.
5. Transaction commit.

Khi business rows và checkpoint cùng tham gia một transaction, chúng có thể được commit hoặc rollback như một đơn vị. Nếu hai thay đổi commit độc lập, có thể xuất hiện khoảng thời gian một bên đã lưu còn bên kia chưa lưu.

```text
Một chunk
   |
   +----> Ghi business rows
   |
   +----> Cập nhật StepExecution / ExecutionContext
   |
   v
Transaction commit
   |
   +----> Business data đã lưu
   +----> Checkpoint đã lưu
```

Mục tiêu là checkpoint phải phản ánh đúng phần business data đã được commit. Transaction boundary là cơ chế quan trọng để giữ mối quan hệ này.

## Khi metadata và business data dùng chung transaction

Đây là trường hợp dễ phối hợp nhất. Ví dụ cả bảng `orders` và các bảng `BATCH_*` đều nằm trong cùng PostgreSQL database, và step cùng `JobRepository` sử dụng cùng `DataSource` và `PlatformTransactionManager`.

Trong chunk-oriented step, transaction manager của step mở transaction cho chunk. Writer ghi business data trong transaction đó. Các thao tác repository cập nhật `StepExecution` và execution context có thể tham gia cùng transaction nếu `JobRepository` được cấu hình để dùng cùng resource và propagation phù hợp.

```text
                  Một JDBC transaction
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
       INSERT orders   UPDATE audit   UPDATE BATCH_*
             |             |             |
             +-------------+-------------+
                           |
                      COMMIT / ROLLBACK
```

Nếu writer ném exception trước khi commit, các thay đổi business data trong transaction được rollback. Checkpoint được cập nhật trong cùng transaction cũng rollback. Khi restart, Spring Batch có thể đọc lại chunk chưa commit.

Nếu transaction commit thành công, business data và checkpoint liên quan cùng được lưu. Job có thể tiếp tục từ phần dữ liệu kế tiếp theo state của reader.

### Cấu hình step dùng chung transaction manager

Ví dụ Spring Batch 5 với JDBC writer:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("batchTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Trong cấu hình minh họa, `batchTransactionManager` phải quản lý đúng datasource mà writer và repository sử dụng nếu mục tiêu là một transaction chung. Tên bean chỉ là ví dụ; ứng dụng có thể dùng một tên khác. Nếu có nhiều transaction manager, cần dùng qualifier rõ ràng để tránh inject nhầm bean.

Không cần tự mở transaction thủ công trong writer thông thường. Writer nên tham gia transaction chunk do step quản lý. Nếu writer gọi service có `@Transactional`, mặc định `Propagation.REQUIRED` thường cho phép service tham gia transaction hiện tại khi cùng transaction manager và resource.

### Tasklet dùng chung transaction

Với `TaskletStep`, transaction boundary thông thường là một transaction cho mỗi lần gọi `Tasklet.execute`. Nếu tasklet cập nhật business data bằng `JdbcTemplate` dùng cùng datasource và transaction manager của step, các câu SQL đó có thể commit hoặc rollback cùng metadata được repository cập nhật trong transaction.

Nếu tasklet trả `RepeatStatus.CONTINUABLE`, mỗi lần gọi tiếp theo có transaction riêng. Vì vậy, một đơn vị business work và checkpoint tương ứng nên được cập nhật trong cùng invocation/transaction.

## Khi metadata và business data dùng transaction manager khác nhau

Một ứng dụng có thể tách database metadata khỏi database nghiệp vụ để phân quyền, cô lập tải, backup hoặc vận hành độc lập. Ví dụ:

- `batch_meta_db` lưu các bảng `BATCH_*`.
- `orders_db` lưu đơn hàng và dữ liệu liên quan.

Khi repository và writer dùng hai datasource hoặc hai local transaction manager khác nhau, hai transaction không tự động commit hoặc rollback nguyên tử.

```text
Transaction của orders_db          Transaction của batch_meta_db
          |                                  |
          v                                  v
      Ghi orders                       Ghi checkpoint
          |                                  |
      COMMIT                              ROLLBACK
          |                                  |
          +------------ restart -------------+
                         |
                         v
                Item có thể được xử lý lại
```

Hai tình huống rủi ro chính:

| Trạng thái sau lỗi | Hệ quả có thể xảy ra |
| --- | --- |
| Business data đã commit, metadata checkpoint chưa commit | Restart có thể đọc lại item và writer ghi trùng |
| Metadata checkpoint đã commit, business data chưa commit | Restart có thể bỏ qua item dù kết quả nghiệp vụ chưa được lưu |

Thứ tự thao tác và transaction cụ thể phụ thuộc cấu hình repository, transaction manager và resource. Không nên giả định thứ tự commit giữa hai local transaction manager tạo ra atomicity.

### Cùng database server vẫn có thể là hai transaction

Ví dụ hai datasource trỏ tới cùng một PostgreSQL server nhưng dùng connection pool riêng. Nếu mỗi datasource mở connection riêng và được quản lý bởi transaction manager riêng, các thao tác có thể thuộc hai transaction độc lập. Tương tự, dùng hai schema trên cùng database nhưng cấu hình hai transaction manager riêng không tự động làm chúng thành một transaction.

Để có transaction chung, cần bảo đảm cả hai nhóm dữ liệu tham gia cùng transaction resource và transaction manager phù hợp, hoặc dùng cơ chế distributed transaction được cấu hình rõ ràng.

## Các chiến lược duy trì nhất quán

Không phải ứng dụng nào cũng cần cùng một cách triển khai. Lựa chọn phụ thuộc vào số resource, mức độ nhất quán yêu cầu và khả năng phục hồi nghiệp vụ.

### Dùng chung transaction resource

Nếu business data và metadata có thể nằm trong cùng database/resource, đây thường là giải pháp đơn giản nhất. Dùng cùng `DataSource`, transaction manager phù hợp và cấu hình repository/step rõ ràng để cập nhật business rows và checkpoint trong cùng transaction.

Ưu điểm:

- Business data và checkpoint có thể commit/rollback cùng nhau.
- Restart dễ dự đoán hơn vì checkpoint gắn với dữ liệu đã commit.
- Không cần điều phối transaction phân tán.

Hạn chế:

- Batch metadata và workload nghiệp vụ cùng phụ thuộc một database.
- Tải ghi metadata và business data cạnh tranh tài nguyên.
- Có thể không đáp ứng yêu cầu phân quyền, cô lập hoặc kiến trúc nhiều hệ thống.

### Idempotent writer

Khi không thể bảo đảm atomic commit giữa các resource, writer nên xử lý an toàn khi nhận lại cùng một item. Một số cách:

- Tạo unique constraint trên business key.
- Dùng upsert có quy tắc rõ ràng.
- Lưu processing key để nhận biết item đã được áp dụng.
- Dùng idempotency key khi gọi API hoặc publish message.
- Kiểm tra trạng thái hiện tại trước khi thực hiện thao tác có thể lặp.

Ví dụ PostgreSQL upsert:

```sql
INSERT INTO orders (order_id, customer_id, amount, status)
VALUES (:orderId, :customerId, :amount, :status)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount = EXCLUDED.amount,
    status = EXCLUDED.status;
```

Upsert giúp tránh duplicate theo `order_id`, nhưng cần xác định liệu cập nhật lại có hợp lệ hay không. Nếu bản ghi đích có thể đã được một quy trình khác cập nhật mới hơn, việc ghi đè vô điều kiện có thể làm mất dữ liệu.

### Business processing ledger

Với job xử lý lượng lớn dữ liệu, có thể lưu một ledger nghiệp vụ ghi nhận từng item hoặc từng nhóm đã được áp dụng. Ví dụ bảng `batch_processed_item` lưu `job_business_key`, `item_key`, `processed_at` và kết quả.

Ledger nên nằm cùng transaction với business changes mà nó đại diện. Khi writer nhận lại item, nó kiểm tra ledger hoặc dùng unique key để tránh áp dụng thay đổi hai lần. Cách này hữu ích khi metadata Spring Batch nằm ở resource riêng nhưng hệ thống nghiệp vụ vẫn cần tự bảo vệ trước replay.

Không nên xem ledger nghiệp vụ là bản thay thế cho `JobRepository`. Ledger trả lời câu hỏi item nghiệp vụ đã được áp dụng chưa; repository trả lời câu hỏi job/step execution đang ở trạng thái nào và restart từ đâu.

### Transactional outbox cho message

Nếu batch job cập nhật business data và cần phát message, không nên dựa vào giả định database transaction có thể rollback message đã được broker nhận.

Một mẫu phổ biến là transactional outbox:

```text
Một business DB transaction
          |
          +---- Ghi business rows
          |
          +---- Ghi outbox event
          |
          +---- COMMIT
                    |
                    v
             Outbox publisher
                    |
                    v
              Message broker
                    |
                    v
             Idempotent consumer
```

Business row và outbox event được ghi cùng transaction trong database nghiệp vụ. Một publisher riêng đọc event chưa gửi và phát tới broker. Nếu publisher gửi thành công nhưng chưa đánh dấu event đã gửi, nó có thể gửi lại; do đó event cần ID ổn định và consumer cần idempotent.

Outbox bảo đảm sự kiện được lưu cùng thay đổi nghiệp vụ; nó không tạo atomic transaction giữa database và broker. Nó biến vấn đề gửi message thành một luồng có thể retry và đối soát.

### Distributed transaction hoặc XA

Nếu yêu cầu nghiệp vụ bắt buộc business data và metadata ở nhiều resource phải commit nguyên tử, có thể đánh giá distributed transaction/XA với transaction coordinator và các resource hỗ trợ XA.

Distributed transaction có chi phí về cấu hình, hiệu năng, vận hành, recovery log và phụ thuộc hệ thống. Không phải mọi database, driver hoặc broker đều hỗ trợ cùng mức. Chỉ nên chọn khi yêu cầu atomicity thực sự cần thiết và đội vận hành có khả năng quản lý coordinator cùng các trạng thái in-doubt.

Trong nhiều hệ thống batch, idempotency và khả năng đối soát đơn giản hơn và dễ mở rộng hơn so với đưa mọi resource vào XA.

## JobRepository và transaction của step

`JobRepository` quản lý metadata nhưng không có nghĩa mọi cập nhật metadata trong toàn bộ vòng đời job đều nằm trong cùng transaction với business data.

Các thao tác như tạo `JobExecution`, đánh dấu bắt đầu/kết thúc step, cập nhật `StepExecution` hoặc lưu execution context diễn ra ở các thời điểm khác nhau trong lifecycle. Trong chunk processing, các cập nhật metadata liên quan đến checkpoint có thể tham gia transaction chunk khi repository và step được cấu hình tương thích. Các chuyển trạng thái ở đầu/cuối job hoặc step có thể thuộc transaction riêng.

Điều này có nghĩa:

- Có thể business chunk đã commit nhưng bước cập nhật trạng thái cuối của job gặp lỗi.
- `JobExecution` có thể được đánh dấu `FAILED` dù một số business chunks trước đó đã commit thành công.
- Metadata `COMPLETED` không tự thay thế kiểm tra kết quả nghiệp vụ nếu job ghi ra nhiều resource độc lập.
- Khi restart, Spring Batch dựa trên trạng thái repository và checkpoint; writer vẫn cần an toàn trước việc item chưa được xác nhận hoặc bị gửi lại.

Vì vậy, hãy phân biệt transaction của từng chunk/tasklet invocation với transaction quản lý các chuyển trạng thái lifecycle của job và step.

## Ví dụ: chunk ghi database cùng metadata

Giả sử job `importOrdersJob` nhập file CSV vào bảng `orders`. `businessDate` là identifying parameter. `FlatFileItemReader` đọc theo dòng, processor chuẩn hóa dữ liệu, `JdbcBatchItemWriter` insert các đơn hàng.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        JdbcBatchItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Giả sử `JobRepository` và writer dùng cùng datasource/transaction manager. Mỗi chunk tối đa 200 item có thể ghi business rows và cập nhật checkpoint trong cùng transaction. Nếu chunk thứ ba lỗi trước commit, các thay đổi của chunk đó rollback; hai chunk trước đã commit vẫn tồn tại. Khi restart cùng identifying parameters, reader khôi phục checkpoint để tiếp tục từ chunk chưa hoàn tất.

Nếu `orders` nằm trong database riêng và writer dùng transaction manager khác repository, checkpoint và business rows có thể lệch khi một transaction commit còn transaction kia thất bại. Khi đó, unique business key hoặc upsert giúp writer chịu được replay.

## Ví dụ: tasklet cập nhật business data và metadata

Một tasklet có thể thực hiện một thao tác nghiệp vụ ngắn như cập nhật trạng thái kỳ kế toán và ghi checkpoint.

```java
public class CloseAccountingPeriodTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public CloseAccountingPeriodTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String period = chunkContext.getStepContext()
                .getJobParameters().get("period").toString();

        jdbcTemplate.update(
                "UPDATE accounting_period SET status = 'CLOSED' WHERE period_code = ?",
                period);

        contribution.getStepExecution()
                .getExecutionContext()
                .putString("closedPeriod", period);

        return RepeatStatus.FINISHED;
    }
}
```

Nếu tasklet dùng cùng transaction resource và transaction manager với repository, thay đổi trạng thái nghiệp vụ và execution context liên quan có thể được commit cùng transaction của tasklet invocation. Nếu business database khác metadata database, cần thêm cơ chế nghiệp vụ để bảo đảm việc đóng kỳ có thể thực hiện lại an toàn.

Trong code production, nên kiểm tra parameter bắt buộc, dùng API lấy parameter có kiểu phù hợp và xử lý trường hợp kỳ kế toán đã đóng. Một thao tác `UPDATE` nên có điều kiện hoặc business key để gọi lại không tạo tác động sai.

## Xử lý restart và trạng thái không nhất quán

Khi job thất bại, trước khi restart cần xác định:

1. Chunk hoặc tasklet invocation cuối cùng đã commit business data chưa?
2. Checkpoint tương ứng đã được lưu trong `ExecutionContext` chưa?
3. Metadata và business data dùng chung transaction resource hay không?
4. Writer có thể được gọi lại với cùng item hay không?
5. Có ledger, unique key, idempotency key hoặc outbox để phát hiện thao tác đã áp dụng không?

Không nên chỉ nhìn `JobExecution` ở trạng thái `FAILED` rồi kết luận mọi business changes đã rollback. Những chunk trước đó có thể đã commit. Ngược lại, cũng không nên nhìn thấy checkpoint tiến lên rồi mặc định tất cả side effect bên ngoài đã hoàn tất.

Một quy trình phục hồi có thể gồm:

- Đọc metadata execution và step để xác định lần chạy, checkpoint và lỗi.
- Đối chiếu business records hoặc ledger theo business key.
- Kiểm tra message/outbox hoặc trạng thái hệ thống đích nếu job có side effect ngoài database.
- Xác định restart cùng `JobInstance` hay tạo một logical job mới theo nghiệp vụ.
- Bảo đảm writer idempotent trước khi restart hoặc replay.
- Ghi nhận quyết định phục hồi để có thể kiểm toán.

Nếu cần sửa dữ liệu nghiệp vụ, hãy dùng quy trình nghiệp vụ hoặc migration có kiểm soát. Không cập nhật trực tiếp `STATUS`, `VERSION` hoặc execution context trong bảng `BATCH_*` để ép job chạy tiếp; thao tác như vậy có thể làm hỏng quan hệ metadata và checkpoint.

## Transaction propagation trong service được gọi từ batch

Tasklet hoặc writer thường gọi service có annotation `@Transactional`. Propagation quyết định service tham gia transaction của step hay mở transaction riêng.

| Propagation | Hành vi | Tác động tới tính nhất quán |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction hiện tại hoặc tạo transaction nếu chưa có | Thường phù hợp khi business update cần commit cùng chunk/tasklet invocation và cùng transaction manager |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại và mở transaction mới | Service có thể commit dù transaction step sau đó rollback |
| `NESTED` | Dùng savepoint trong transaction hiện tại nếu resource hỗ trợ | Có thể rollback một phần trong transaction; khả năng hỗ trợ tùy manager/database |

Ví dụ service dùng `REQUIRES_NEW` ghi audit có thể commit audit record dù chunk thất bại. Điều đó có thể đúng nếu audit cần lưu cả sự kiện thất bại, nhưng phải được thiết kế có chủ đích. Nếu audit là checkpoint hoặc business change phải nhất quán với chunk, transaction riêng có thể gây sai lệch.

Khi ứng dụng có nhiều datasource, hãy chỉ định transaction manager phù hợp bằng qualifier trên service. Cùng một annotation `@Transactional` nhưng chọn nhầm manager có thể khiến thao tác không tham gia transaction mà step đang quản lý.

## Đồng thời và nhiều node

Trong triển khai nhiều node, các node thường dùng chung `JobRepository` để nhận diện instance và trạng thái execution. Business database cũng cần quy tắc concurrency rõ ràng.

Nếu hai job instance khác nhau cùng cập nhật một tập business records, database có thể gặp lock contention hoặc lost update nếu writer không dùng khóa/điều kiện phù hợp. Nếu cùng một logical job bị yêu cầu chạy từ nhiều node, repository giúp điều phối execution của instance nhưng không thay thế constraint nghiệp vụ ở database đích.

Các biện pháp thường dùng:

- Chọn identifying parameters phản ánh phạm vi dữ liệu mà job sở hữu.
- Dùng unique business key và điều kiện update phù hợp.
- Chia partition theo phạm vi không chồng lấn nếu cần chạy song song.
- Dùng optimistic/pessimistic locking theo đặc điểm dữ liệu.
- Theo dõi deadlock, lock wait, connection pool và số execution đồng thời.
- Bảo đảm các node dùng schema metadata tương thích và cùng repository khi thuộc một hệ thống batch.

## Backup, retention và quyền truy cập

Batch metadata và business data có vòng đời khác nhau, nhưng khi điều tra hoặc phục hồi job cần xem xét chúng cùng nhau.

- Backup business data theo yêu cầu nghiệp vụ và chính sách khôi phục của hệ thống.
- Backup metadata để giữ lịch sử, checkpoint và khả năng restart.
- Khi cần khôi phục một thời điểm, bảo đảm metadata và business data tương thích về trạng thái commit; khôi phục hai database về hai thời điểm khác nhau có thể tạo lệch trạng thái.
- Thiết lập retention cho execution đã hoàn tất nhưng không xóa metadata của job đang chạy hoặc cần restart.
- Giới hạn quyền đọc/ghi bảng `BATCH_*` và bảng nghiệp vụ theo vai trò ứng dụng.
- Không lưu bí mật hoặc payload nghiệp vụ lớn trong `ExecutionContext`; chỉ lưu checkpoint và tham chiếu cần thiết.

Nếu metadata và business data ở hai database, kế hoạch backup/restore cần xác định cách đồng bộ thời điểm phục hồi hoặc cách đối soát sau restore.

## Kiểm thử tính nhất quán transaction

Kiểm thử thành công thông thường chưa đủ để chứng minh metadata và business data nhất quán. Cần mô phỏng lỗi tại các thời điểm khác nhau.

### Cùng resource

- Chạy chunk thành công và xác nhận business rows cùng checkpoint được commit.
- Cố ý ném exception trước commit và xác nhận business rows cùng checkpoint của chunk rollback.
- Cho chunk trước commit thành công, chunk sau thất bại; xác nhận dữ liệu chunk trước vẫn còn.
- Restart cùng identifying parameters và xác nhận reader tiếp tục từ checkpoint đã commit.

### Khác resource

- Mô phỏng business DB commit thành công nhưng cập nhật metadata thất bại.
- Mô phỏng metadata được cập nhật nhưng business DB transaction rollback.
- Restart/replay và xác nhận unique key, upsert hoặc ledger ngăn duplicate.
- Mô phỏng broker nhận message nhưng database rollback; xác nhận consumer xử lý event ID lặp an toàn.

### Kiểm thử phục hồi

- Xác nhận job `FAILED` không đồng nghĩa toàn bộ business data của job bị rollback.
- Đối chiếu `readCount`, `writeCount`, skip/filter count và checkpoint với dữ liệu thực tế.
- Kiểm tra trạng thái outbox và khả năng publisher gửi lại event chưa được xác nhận.
- Kiểm tra quy trình restore metadata/business data có thể phục hồi cùng một trạng thái nhất quán.

Fault injection nên được thực hiện trong môi trường test với dữ liệu có thể reset. Không nên kiểm tra bằng cách sửa thủ công metadata production.

## Các lỗi thiết kế thường gặp

### Cho rằng cùng database server đồng nghĩa cùng transaction

Hai datasource hoặc hai transaction manager có thể mở transaction độc lập dù trỏ tới cùng server. Xác nhận resource và transaction manager thực tế thay vì chỉ so sánh JDBC URL.

### Nghĩ job FAILED thì mọi business data đã rollback

Các chunk đã commit trước khi lỗi vẫn tồn tại. Job status mô tả lần thực thi; nó không phải một transaction bao trùm toàn bộ job.

### Checkpoint và business update được commit riêng

Điều này có thể dẫn tới replay hoặc bỏ sót. Dùng chung transaction khi có thể; nếu không, dùng idempotency, ledger hoặc quy trình đối soát.

### Dùng REQUIRES_NEW mà không đánh giá hậu quả

Transaction độc lập có thể commit dữ liệu dù chunk/tasklet rollback. Chỉ dùng khi nghiệp vụ cần tính độc lập và có kế hoạch xử lý trạng thái đó.

### Giả định message hoặc file rollback cùng JDBC

Side effect ngoài database không tự động tham gia JDBC transaction. Dùng outbox, file tạm, idempotency key hoặc cơ chế phục hồi theo giao thức đích.

### Dùng ExecutionContext làm kho business data

Execution context dành cho checkpoint và trạng thái nhỏ phục vụ restart. Dữ liệu nghiệp vụ, payload lớn hoặc lịch sử xử lý nên nằm trong schema/domain store phù hợp.

## Nguyên tắc thiết kế

Khi thiết kế một job production, hãy thống nhất các điểm sau:

1. Xác định rõ bảng nào là batch metadata và bảng nào là business data.
2. Chọn nơi lưu `JobRepository` và transaction manager cho step.
3. Nếu cần commit nguyên tử, cấu hình metadata và business writer dùng cùng transaction resource phù hợp.
4. Nếu tách resource, xác định rõ các cửa sổ lỗi khi một bên commit còn bên kia rollback.
5. Thiết kế writer idempotent theo business key hoặc idempotency key.
6. Dùng ledger hoặc outbox khi cần truy vết việc áp dụng item và phát message.
7. Lưu checkpoint nhỏ, ổn định trong `ExecutionContext`.
8. Kiểm tra propagation của các service được gọi từ tasklet/processor/writer.
9. Theo dõi metadata cùng business records khi điều tra job thất bại.
10. Kiểm thử rollback, restart, partial failure và restore trước khi triển khai.

## Ghi nhớ

Batch metadata mô tả `JobInstance`, `JobExecution`, `StepExecution` và checkpoint; business data là dữ liệu nghiệp vụ mà job xử lý. Trong chunk hoặc tasklet, các thay đổi của hai nhóm có thể commit/rollback cùng nhau khi chúng tham gia cùng transaction resource và transaction manager phù hợp. Nếu metadata và business data dùng hai database hoặc hai transaction manager độc lập, không có atomic commit mặc định: business data có thể đã lưu nhưng checkpoint chưa lưu, hoặc ngược lại. Khi không thể dùng chung transaction, hãy thiết kế writer idempotent, business ledger, transactional outbox và quy trình đối soát để restart an toàn. Trạng thái `FAILED` của job không có nghĩa mọi business changes đã rollback; cần đọc metadata cùng dữ liệu nghiệp vụ để hiểu trạng thái thực tế.
