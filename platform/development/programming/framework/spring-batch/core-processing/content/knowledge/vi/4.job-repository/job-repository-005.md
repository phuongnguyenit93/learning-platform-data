# Transaction khi cập nhật batch metadata

Trong Spring Batch, `JobRepository` lưu metadata mô tả trạng thái của job, job instance, job execution, step execution và execution context. Những dữ liệu này được cập nhật liên tục khi job bắt đầu, khi step chạy, sau mỗi chunk và khi job kết thúc. Vì metadata quyết định khả năng theo dõi và restart, các thao tác cập nhật phải được thực hiện trong transaction với ranh giới rõ ràng.

Transaction bảo đảm một nhóm thay đổi metadata được ghi nhận nhất quán. Nếu một chunk xử lý thất bại và transaction rollback, checkpoint tương ứng cũng cần được rollback để lần chạy sau không bỏ qua dữ liệu chưa được commit. Trong cấu hình JDBC thông dụng, `JobRepository` dùng `PlatformTransactionManager` để quản lý transaction khi đọc và ghi các bảng metadata `BATCH_*`.

## Vì sao cập nhật metadata cần transaction?

Metadata của Spring Batch không chỉ là log trạng thái. Framework dựa vào metadata để quyết định job nào đang chạy, step nào đã hoàn thành và vị trí nào cần tiếp tục khi restart. Nếu trạng thái bị ghi dở hoặc checkpoint không khớp với dữ liệu nghiệp vụ, lần restart có thể bỏ sót hoặc xử lý lặp dữ liệu.

Ví dụ một step đọc 100 đơn hàng, xử lý rồi ghi vào database. Sau khi writer hoàn tất, Spring Batch cập nhật số lượng item và `ExecutionContext` để ghi nhận vị trí đọc tiếp theo. Nếu dữ liệu đơn hàng đã commit nhưng checkpoint chưa được lưu, lần restart có thể đọc lại chunk vừa xử lý. Ngược lại, nếu checkpoint được lưu trước khi dữ liệu nghiệp vụ commit, lần restart có thể bỏ qua những đơn hàng chưa thực sự được ghi.

Transaction giúp phối hợp các thao tác liên quan trong một đơn vị commit. Khi metadata và dữ liệu nghiệp vụ cùng tham gia một transaction trên cùng database resource, chúng có thể cùng commit hoặc cùng rollback. Đây là nền tảng để Spring Batch duy trì checkpoint đáng tin cậy.

## JobRepository quản lý transaction như thế nào?

`JobRepository` là abstraction quản lý metadata. Với JDBC repository, các thao tác được thực hiện trên schema Spring Batch thông qua `DataSource` và `PlatformTransactionManager` đã cấu hình.

Các nhóm thao tác thường gặp:

| Thao tác | Metadata liên quan | Mục đích |
| --- | --- | --- |
| Tạo `JobExecution` | `BATCH_JOB_EXECUTION` và các bảng liên quan | Ghi nhận một lần chạy mới của `JobInstance` |
| Cập nhật `JobExecution` | Trạng thái, thời điểm bắt đầu/kết thúc, exit code | Theo dõi vòng đời của lần chạy |
| Tạo/cập nhật `StepExecution` | `BATCH_STEP_EXECUTION` | Theo dõi trạng thái và số liệu của step |
| Cập nhật execution context | `BATCH_JOB_EXECUTION_CONTEXT`, `BATCH_STEP_EXECUTION_CONTEXT` | Lưu checkpoint và trạng thái phục hồi |
| Lưu job parameters | `BATCH_JOB_EXECUTION_PARAMS` | Ghi lại tham số dùng trong lần chạy |

Các thao tác ghi metadata được repository thực hiện trong transaction theo cấu hình. Ứng dụng thường gọi API của Spring Batch như `JobLauncher`, `JobRepository` hoặc các thành phần step; framework chịu trách nhiệm gọi repository vào đúng thời điểm. Không nên tự cập nhật trực tiếp các bảng `BATCH_*` để thay đổi trạng thái execution.

Với JDBC `JobRepository`, các phương thức tạo instance hoặc execution cần bảo vệ trước các yêu cầu khởi chạy đồng thời. Spring Batch thường dùng isolation level nghiêm ngặt hơn cho nhóm thao tác `create*` (mặc định phổ biến là `SERIALIZABLE`) để tránh hai tiến trình cùng tạo metadata cho một logical job. Các thao tác repository còn lại cũng được thực hiện trong transaction, với isolation level theo cấu hình transaction manager/database. Có thể tùy chỉnh isolation cho thao tác tạo, nhưng chỉ nên làm sau khi hiểu rõ khả năng cạnh tranh và ràng buộc duy nhất của schema.

## Các ranh giới transaction trong vòng đời job

Một job có nhiều giai đoạn cập nhật metadata. Chúng không nhất thiết nằm trong cùng một transaction kéo dài từ lúc khởi chạy đến lúc hoàn thành.

```text
JobLauncher
    |
    | transaction tạo JobExecution
    v
JobExecution = STARTING / STARTED
    |
    v
Tạo và bắt đầu StepExecution
    |
    v
Chunk transaction 1
    |-- read / process / write
    |-- cập nhật ExecutionContext và StepExecution
    +-- COMMIT hoặc ROLLBACK
    |
    v
Chunk transaction 2
    |-- read / process / write
    |-- cập nhật checkpoint và số liệu step
    +-- COMMIT hoặc ROLLBACK
    |
    v
Cập nhật trạng thái StepExecution
    |
    v
Cập nhật trạng thái JobExecution
    |
    v
COMPLETED / FAILED / STOPPED
```

Sơ đồ biểu diễn các giai đoạn ở mức khái niệm. Spring Batch có thể mở các transaction riêng cho thao tác tạo execution, cập nhật trạng thái bắt đầu/kết thúc và các chunk. Một job thường có nhiều transaction ngắn trong suốt quá trình chạy, giúp dữ liệu được commit theo từng đơn vị xử lý thay vì giữ một transaction khổng lồ.

### Khi tạo JobExecution

Khi `JobLauncher` nhận yêu cầu chạy job, Spring Batch tra cứu hoặc tạo `JobInstance` dựa trên tên job và identifying parameters, sau đó tạo `JobExecution`. Repository ghi metadata ban đầu trong transaction. Nếu việc tạo execution không thành công, job không thể tiếp tục như một lần chạy hợp lệ.

Isolation level ở thao tác tạo có vai trò quan trọng khi nhiều request cùng khởi chạy một job với cùng identifying parameters. Nó giúp ngăn hai luồng đồng thời tạo hai instance hoặc execution xung đột cho cùng một danh tính.

### Khi bắt đầu và kết thúc step

Spring Batch tạo hoặc cập nhật `StepExecution` để lưu trạng thái step, thời điểm bắt đầu/kết thúc, số item đọc/ghi, skip, commit và rollback. Khi step chuyển sang trạng thái kết thúc, metadata được cập nhật thông qua repository trong transaction tương ứng.

### Trong mỗi chunk

Với chunk-oriented step, mỗi chunk thường là một đơn vị transaction. Framework đọc và xử lý một nhóm item, gọi writer, cập nhật trạng thái và execution context, sau đó commit transaction theo cấu hình. Nếu có lỗi làm transaction rollback, các thay đổi nằm trong transaction đó được rollback.

### Khi job kết thúc

Sau khi các step kết thúc, Spring Batch cập nhật trạng thái cuối cùng của `JobExecution`, chẳng hạn `COMPLETED`, `FAILED` hoặc `STOPPED`, cùng thời điểm và exit information. Những cập nhật này được repository quản lý trong transaction của nó.

## Transaction của chunk và checkpoint

Với chunk processing, `commit-interval` xác định số item được gom vào một chunk trước khi commit. Ví dụ `chunk(100, transactionManager)` có nghĩa mỗi chunk xử lý tối đa 100 item theo transaction manager được cung cấp cho step.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
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

Trong ví dụ, `transactionManager` quản lý transaction của chunk. `JobRepository` được truyền vào `StepBuilder` để step lưu metadata. Để dữ liệu nghiệp vụ và metadata checkpoint commit nhất quán, transaction manager của step và transaction manager của repository cần được cấu hình phù hợp với cùng database resource khi cả hai loại dữ liệu cùng nằm trong một database.

Trong quá trình commit chunk, Spring Batch cập nhật `StepExecution` và `ExecutionContext` theo vòng đời của step. Một reader có hỗ trợ state có thể lưu vị trí hiện tại để lần restart biết tiếp tục từ đâu. Checkpoint phải tương ứng với dữ liệu đã commit. Nếu transaction rollback, checkpoint được lưu trong cùng transaction cũng rollback; lần chạy sau có thể đọc lại chunk đó.

`commit-interval` là một quyết định ảnh hưởng cả hiệu năng lẫn phạm vi rollback:

| Chunk size | Tác động thường gặp |
| --- | --- |
| Nhỏ | Transaction ngắn, rollback ít item hơn, nhưng số lần commit và cập nhật metadata tăng |
| Lớn | Ít lần commit hơn, có thể tăng throughput, nhưng transaction lâu hơn và rollback có thể phải xử lý lại nhiều item hơn |

Không có một giá trị tối ưu cho mọi job. Hãy cân nhắc thời gian xử lý từng item, tải database, lock, dung lượng bộ nhớ, yêu cầu restart và tần suất cập nhật metadata.

## Dùng chung hay tách transaction manager?

Một ứng dụng có thể có transaction manager cho dữ liệu nghiệp vụ và transaction manager cho batch metadata. Cách cấu hình phù hợp phụ thuộc vào việc hai loại dữ liệu nằm ở cùng database hay ở các resource độc lập.

### Metadata và dữ liệu nghiệp vụ dùng chung database

Đây là trường hợp đơn giản nhất để phối hợp transaction. Nếu `JobRepository` và writer cùng dùng một `DataSource` và cùng một `PlatformTransactionManager`, các thao tác repository được gọi trong transaction đang hoạt động có thể tham gia cùng transaction theo propagation phù hợp (thông thường là `REQUIRED`).

```text
Chunk transaction
       |
       +---- Writer ghi bảng ORDER
       |
       +---- JobRepository cập nhật BATCH_STEP_EXECUTION
       |
       +---- JobRepository lưu STEP_EXECUTION_CONTEXT
       |
       +---- COMMIT / ROLLBACK cùng transaction
```

Nếu writer hoặc repository gặp lỗi trước commit, transaction có thể rollback cả dữ liệu nghiệp vụ lẫn metadata checkpoint được enlist trong cùng transaction. Điều này giúp giảm nguy cơ checkpoint đi trước dữ liệu.

Điều kiện quan trọng là các thao tác thực sự dùng cùng transaction resource và transaction manager. Chỉ có cùng URL database hoặc cùng máy chủ database chưa đủ để bảo đảm hai kết nối riêng biệt tham gia cùng một transaction.

### Metadata và dữ liệu nghiệp vụ dùng database khác nhau

Một số hệ thống tách database batch metadata khỏi database nghiệp vụ để phân quyền, cô lập tải hoặc đáp ứng yêu cầu vận hành. Khi đó, repository và writer có thể dùng hai `DataSource` cùng hai transaction manager khác nhau.

Hai local transaction manager không tự phối hợp để commit hoặc rollback nguyên tử. Ví dụ writer commit đơn hàng vào database nghiệp vụ, sau đó transaction ghi checkpoint vào database metadata thất bại. Khi restart, Spring Batch có thể đọc lại item đã được ghi vào database nghiệp vụ. Tình huống ngược lại cũng có thể xảy ra nếu checkpoint commit trong khi dữ liệu nghiệp vụ chưa được lưu.

```text
Transaction nghiệp vụ             Transaction metadata
        |                                  |
        v                                  v
  Ghi ORDER rows                    Ghi checkpoint
        |                                  |
     COMMIT                              lỗi
        |                                  |
        +---------- restart ---------------+
                   |
                   v
          Item có thể được đọc lại
```

Khi tách resource, cần thiết kế khả năng phục hồi:

- Làm cho writer idempotent: ghi cùng một business key nhiều lần vẫn cho kết quả đúng.
- Dùng unique constraint hoặc upsert có quy tắc nghiệp vụ rõ ràng để tránh bản ghi trùng.
- Có thể ghi nhận trạng thái xử lý ở hệ thống nghiệp vụ để đối soát khi metadata và dữ liệu lệch nhau.
- Xác định hành vi khi một phía commit còn phía kia rollback hoặc mất kết nối.
- Nếu yêu cầu thực sự cần atomic commit qua nhiều resource, đánh giá giải pháp distributed transaction/XA và chi phí vận hành của nó.

Trong nhiều hệ thống, idempotency và khả năng đối soát là cách thực tế để xử lý lỗi giữa hai database. Không nên giả định rằng việc cấu hình hai transaction manager sẽ tự tạo ra một transaction phân tán.

## Propagation và transaction lồng nhau

Propagation xác định một thao tác transaction tham gia transaction hiện có hay tạo transaction riêng. Trong xử lý batch, lựa chọn này có ảnh hưởng trực tiếp đến tính nhất quán của dữ liệu nghiệp vụ và checkpoint.

`REQUIRED` thường là propagation phù hợp khi một thao tác writer hoặc repository cần tham gia transaction chunk đang hoạt động. Nếu đã có transaction, thao tác tham gia transaction đó; nếu chưa có, nó tạo transaction mới.

`REQUIRES_NEW` tạm treo transaction hiện tại và mở một transaction riêng. Nếu writer dùng `REQUIRES_NEW` để commit dữ liệu nghiệp vụ trong khi transaction chunk còn có thể rollback, dữ liệu đã commit riêng có thể tồn tại dù checkpoint chunk rollback. Khi restart, item có thể được xử lý lại. Cách làm này chỉ phù hợp khi ứng dụng đã thiết kế idempotency và thực sự cần transaction độc lập.

`NESTED` dựa trên khả năng savepoint của transaction manager và database. Không phải mọi transaction manager hoặc resource đều hỗ trợ giống nhau. Không nên chọn propagation chỉ để né lỗi transaction; cần xác định rõ trạng thái nào phải commit cùng nhau và trạng thái nào có thể độc lập.

Một service được gọi từ `ItemWriter` thường tham gia transaction chunk nếu cấu hình transaction của service cho phép. Hãy kiểm tra annotation `@Transactional`, propagation, datasource và transaction manager được inject; một method tưởng như nằm trong chunk có thể mở transaction riêng nếu được cấu hình khác.

## Cấu hình JobRepository và transaction attributes

Với Spring Boot, ứng dụng thường khai báo `DataSource` và để auto-configuration thiết lập JDBC `JobRepository` cùng các thành phần batch. Repository cần có transaction manager phù hợp để ghi metadata. Step cũng cần transaction manager cho chunk.

Trong cấu hình tự quản lý, cần xác định rõ:

1. `DataSource` nào chứa schema `BATCH_*`.
2. `PlatformTransactionManager` nào quản lý các thao tác `JobRepository`.
3. `PlatformTransactionManager` nào quản lý transaction của step/chunk.
4. Hai transaction manager có cùng quản lý một resource hay không.
5. Isolation level và timeout nào phù hợp với database và tải thực tế.

Ở các phiên bản Spring Batch hỗ trợ cấu hình repository JDBC tường minh, repository được tạo với datasource, transaction manager và các transaction attributes cho thao tác tạo/cập nhật. API cấu hình cụ thể khác nhau giữa các phiên bản Spring Batch và Spring Boot, vì vậy hãy dùng cách cấu hình đúng phiên bản của dự án. Không trộn ví dụ cấu hình cũ với API builder mới mà không kiểm tra tương thích.

Một số thuộc tính cần cân nhắc:

| Thuộc tính | Ý nghĩa vận hành |
| --- | --- |
| Isolation level cho thao tác tạo | Giảm race condition khi nhiều request cùng tạo instance/execution |
| Transaction propagation | Quy định thao tác repository tham gia transaction hiện có hay mở transaction mới |
| Transaction timeout | Giới hạn thời gian chờ của transaction, cần tương thích với thời gian chunk và tải database |
| Table prefix | Cho phép repository dùng tên bảng metadata có tiền tố khác nếu schema được cấu hình tương ứng |

Không nên hạ isolation level của thao tác tạo chỉ để giảm lock khi chưa kiểm tra các lỗi cạnh tranh có thể xuất hiện. Nếu có nhiều node cùng khởi chạy một job, cần giữ cơ chế bảo vệ danh tính instance và kiểm tra unique constraint của schema.

## Xử lý lỗi và rollback

Khi một exception xuất hiện trong chunk, kết quả phụ thuộc loại exception, cấu hình retry/skip và transaction boundary. Nếu lỗi khiến chunk rollback, các thao tác database tham gia transaction đó sẽ được rollback. Spring Batch có thể retry item hoặc chunk theo cấu hình fault tolerance, hoặc kết thúc step ở trạng thái lỗi.

Các trường hợp thường gặp:

| Tình huống | Kết quả transaction thường thấy | Điều cần kiểm tra |
| --- | --- | --- |
| Writer ném exception trước commit | Chunk transaction rollback | Writer có ghi ra hệ thống ngoài transaction không? |
| Lỗi database khi cập nhật metadata trong chunk | Transaction chunk có thể rollback | Metadata và business data có cùng transaction resource không? |
| Ứng dụng dừng sau commit chunk | Dữ liệu và checkpoint của chunk đã commit vẫn còn | Reader có khôi phục đúng state không? |
| Ứng dụng dừng trước commit | Transaction chưa commit bị rollback khi connection được giải phóng | Writer có side effect bên ngoài database không? |
| Hai database dùng hai transaction manager | Một phía có thể commit trong khi phía kia thất bại | Có idempotency và quy trình đối soát không? |

Không phải mọi side effect đều được database rollback. Gửi email, gọi HTTP, publish message hoặc ghi file có thể đã xảy ra trước khi transaction chunk rollback. Với những side effect này, nên dùng outbox pattern, giao tiếp có idempotency key, hoặc cơ chế xác nhận/đối soát để tránh gửi hoặc xử lý trùng khi retry.

## Isolation, lock và chạy đồng thời

Transaction metadata cũng chịu ảnh hưởng của concurrency. Khi nhiều scheduler, node hoặc operator cùng khởi chạy job, repository phải bảo vệ việc tạo `JobInstance` và `JobExecution`. Isolation level cao hơn giúp ngăn một số race condition, nhưng có thể tăng lock contention tùy database.

Các nguyên tắc vận hành:

- Dùng chung một `JobRepository` bền vững cho các node cùng tham gia một hệ thống batch.
- Dùng identifying parameters ổn định để các node nhận diện cùng một logical job.
- Giữ schema và phiên bản Spring Batch tương thích trên tất cả node.
- Đặt transaction timeout phù hợp với thời gian xử lý chunk và giới hạn của database.
- Theo dõi deadlock, lock wait, connection pool và thời gian commit.
- Không tự ý giảm isolation hoặc bỏ constraint để xử lý lỗi cạnh tranh.

Nếu transaction thường xuyên bị timeout hoặc deadlock, hãy kiểm tra truy vấn writer, thứ tự cập nhật bản ghi, kích thước chunk, index và thời gian giữ lock. Tăng timeout đơn thuần có thể chỉ làm lỗi xuất hiện muộn hơn.

## Ví dụ tình huống: metadata và business data cùng transaction

Giả sử `importOrdersStep` đọc dữ liệu từ tệp và ghi đơn hàng vào bảng `ORDERS`. Cả bảng `ORDERS` và các bảng `BATCH_*` đều nằm trong cùng PostgreSQL database, và writer cùng `JobRepository` sử dụng cùng transaction manager.

Một chunk gồm 100 đơn hàng được xử lý như sau:

1. Reader lấy 100 item và processor chuyển đổi chúng.
2. Writer ghi 100 đơn hàng.
3. Spring Batch cập nhật số liệu `StepExecution` và checkpoint trong `ExecutionContext`.
4. Transaction commit.

Nếu bước 3 gặp lỗi trước khi commit, writer và metadata checkpoint tham gia cùng transaction nên các thay đổi trong chunk rollback. Khi restart, reader có thể đọc lại 100 item đó. Nếu commit thành công rồi ứng dụng dừng, dữ liệu đơn hàng và checkpoint đã được lưu cùng transaction; reader có thể tiếp tục từ chunk tiếp theo.

Thiết kế này vẫn cần bảo đảm reader lưu state đúng và writer không tạo side effect ngoài transaction. Nhưng nó cung cấp ranh giới commit rõ ràng giữa dữ liệu nghiệp vụ và metadata.

## Ví dụ tình huống: metadata và business data ở hai database

Giả sử `BATCH_*` nằm trong database `batch_meta`, còn đơn hàng nằm trong database `orders_db`. Step dùng transaction manager của `orders_db` để ghi dữ liệu; repository dùng transaction manager của `batch_meta` để lưu checkpoint.

Nếu writer commit vào `orders_db` thành công nhưng cập nhật context trong `batch_meta` thất bại, lần chạy sau có thể xử lý lại các đơn hàng đó. Khi writer có unique business key và xử lý upsert đúng cách, việc xử lý lại có thể an toàn. Nếu writer luôn insert một dòng mới mà không kiểm soát trùng lặp, dữ liệu sẽ bị nhân đôi.

Do đó, tách database cần đi kèm chiến lược idempotency, kiểm tra trạng thái xử lý và quy trình khôi phục. Nếu yêu cầu nghiệp vụ không chấp nhận bất kỳ khoảng thời gian không nhất quán nào giữa hai database, cần đánh giá distributed transaction hoặc thiết kế lại luồng dữ liệu để có thể phục hồi.

## Chẩn đoán lỗi transaction metadata

Khi job gặp lỗi liên quan đến transaction hoặc metadata, nên bắt đầu từ trạng thái execution và log của đúng thời điểm xảy ra lỗi.

### Deadlock hoặc lock timeout trên bảng BATCH_*

Kiểm tra nhiều job có cùng tạo instance/execution hoặc cập nhật metadata đồng thời hay không. Xem isolation level, truy vấn đang giữ lock, database index và số lượng worker. Không sửa trực tiếp trạng thái trong bảng để giải phóng lock.

### JobExecution được tạo nhưng step không bắt đầu

Có thể transaction tạo execution đã commit nhưng bước tiếp theo thất bại khi tạo hoặc cập nhật `StepExecution`, hoặc ứng dụng bị dừng giữa hai giai đoạn. Kiểm tra `BATCH_JOB_EXECUTION`, trạng thái execution và log tại thời điểm chuyển sang step.

### Step bị rollback nhưng dữ liệu vẫn tồn tại

Xác định writer có dùng transaction manager khác, propagation `REQUIRES_NEW`, kết nối khác hoặc hệ thống ngoài database hay không. Kiểm tra transaction thực tế được mở trên datasource nào và side effect nào đã commit độc lập.

### Restart đọc lại dữ liệu đã ghi

Kiểm tra checkpoint trong `ExecutionContext`, reader state, thời điểm commit và việc metadata/business data có cùng transaction không. Nếu dùng hai database, kiểm tra khả năng một phía commit còn phía kia thất bại; sau đó đánh giá idempotency của writer.

### Metadata không được cập nhật do lỗi kết nối

Kiểm tra connection pool, timeout, quyền ghi schema, trạng thái database và transaction manager được cấu hình cho repository. Khi database metadata không khả dụng, job có thể không thể tạo execution hoặc cập nhật trạng thái một cách an toàn.

Không nên khắc phục bằng cách update thủ công `STATUS`, `VERSION` hoặc execution context trong các bảng `BATCH_*`. Sửa trực tiếp có thể phá vỡ quan hệ giữa instance, execution, step và checkpoint. Hãy khôi phục database hoặc dùng API vận hành của Spring Batch sau khi xác định trạng thái hợp lệ.

## Nguyên tắc thiết kế transaction cho batch metadata

Khi xây dựng một job production, hãy xác định rõ các câu hỏi sau:

1. Metadata và dữ liệu nghiệp vụ nằm trong cùng database hay khác database?
2. Transaction manager nào được dùng cho `JobRepository` và transaction manager nào được dùng cho step?
3. Nếu cùng database, các thao tác repository có thực sự tham gia transaction chunk hay không?
4. Nếu khác database, ứng dụng xử lý thế nào khi một phía commit còn phía kia rollback?
5. `ExecutionContext` lưu checkpoint nào và checkpoint đó có khớp với dữ liệu đã commit không?
6. Writer có idempotent khi chunk bị retry hoặc restart không?
7. Isolation, timeout và kích thước chunk có phù hợp với tải và concurrency không?
8. Có log, metric và quy trình đối soát đủ để điều tra trạng thái lệch hay không?

Với hệ thống dùng một database quan hệ cho cả batch metadata và dữ liệu nghiệp vụ, cấu hình chung `DataSource` và transaction manager thường là cách đơn giản để đồng bộ commit của chunk với checkpoint. Với hệ thống tách database, cần thiết kế khả năng phục hồi rõ ràng; nếu không dùng distributed transaction, idempotency và đối soát là những cơ chế quan trọng để xử lý các trường hợp commit lệch.

## Ghi nhớ

`JobRepository` cập nhật batch metadata thông qua transaction manager đã cấu hình. Các giai đoạn tạo execution, cập nhật trạng thái step/job và commit từng chunk có những transaction boundary riêng. Trong chunk processing, dữ liệu nghiệp vụ và checkpoint nên cùng commit hoặc rollback khi chúng dùng chung transaction resource. Nếu metadata và business data nằm ở hai database hoặc dùng hai transaction manager độc lập, không có bảo đảm atomic commit mặc định; writer cần idempotent và hệ thống cần có cơ chế phục hồi, đối soát phù hợp. Isolation, propagation, timeout và chunk size đều ảnh hưởng đến tính nhất quán và hiệu năng của batch job.
