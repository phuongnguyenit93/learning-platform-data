# Chọn kiến trúc mở rộng Spring Batch theo yêu cầu restart

## 1. Đặt yêu cầu restart trước khi chọn mô hình scaling

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, hệ thống cần mở rộng Spring Batch cho workload dữ liệu lớn bằng **multi-threaded step**, **parallel steps**, **partitioning** hoặc các mô hình phân tán. Việc chọn mô hình chỉ theo throughput thường dẫn đến vấn đề khi production xảy ra lỗi: job chạy nhanh nhưng restart phải làm lại quá nhiều dữ liệu, tạo bản ghi trùng, bỏ sót item hoặc không thể khôi phục đúng checkpoint.

Vì vậy, ở chương **Ma trận lựa chọn**, câu hỏi **“Chọn theo yêu cầu restart”** phải được trả lời trước khi tăng số thread hay worker:

> Nếu một tiến trình chết giữa chừng, chúng ta cần khôi phục **từ đâu**, **trong bao lâu**, **có thể xử lý lại bao nhiêu**, và **làm sao chứng minh kết quả dữ liệu vẫn đúng**?

Một kiến trúc phù hợp phải cân bằng **khả năng restart, tính đúng đắn dữ liệu, thread safety, tài nguyên, chi phí vận hành và tốc độ xử lý**. Tăng concurrency nhưng không quản lý trạng thái phục hồi thường chỉ đẩy lỗi sang thời điểm khó khắc phục hơn.

**Mục tiêu học tập:**

- Phân biệt restart của Spring Batch với retry, relaunch và replay.
- Đánh giá mức độ restartable của từng mô hình scaling.
- Chọn checkpoint, partition boundary, transaction và idempotency theo mục tiêu khôi phục.
- Thiết kế phép thử sự cố và tiêu chí nghiệm thu để quyết định kiến trúc bằng bằng chứng.
- Biết khi nào nên ưu tiên giải pháp đơn giản hơn dù có nhiều tài nguyên chạy song song.

## 2. Nền tảng restart trong Spring Batch

### 2.1. Các đối tượng cần hiểu

| Thành phần | Ý nghĩa đối với restart |
|---|---|
| `JobInstance` | Nhận diện một lần chạy logic của job theo tên job và **identifying JobParameters**. |
| `JobExecution` | Một lần cố gắng thực thi `JobInstance`; restart hợp lệ tạo một `JobExecution` mới trong cùng `JobInstance`. |
| `StepExecution` | Một lần thực thi step; lưu trạng thái và counters như read/write/skip/commit/rollback. |
| `ExecutionContext` | Trạng thái checkpoint cần thiết để khôi phục `Job` hoặc `Step`, được framework persist vào `JobRepository` tại các mốc phù hợp. |
| `JobRepository` | Kho metadata bền vững quản lý execution, checkpoint, trạng thái và lịch sử restart. |
| `JobExplorer` / `JobOperator` | API truy cứu và điều khiển job; `JobOperator.restart(executionId)` cần được kiểm soát quyền, kiểm tra điều kiện và giám sát. |

**Điểm cần nhớ:** cùng tên job nhưng khác **identifying parameters** thường tạo `JobInstance` mới, không phải restart lần thực thi cũ. Khi operator tăng `run.id` hoặc thay ngày xử lý chỉ để “chạy lại”, hệ thống có thể xử lý lại toàn bộ dữ liệu dưới một instance khác, trong khi các biện pháp chống trùng dựa trên JobExecution ID không còn đủ.

Một `JobInstance` đã hoàn thành thường không được restart như một execution thất bại; `JobExecution` đang chạy hoặc đã bị `ABANDONED` cũng có quy tắc riêng. Không nên khởi tạo bản chạy mới để né điều kiện restart nếu nghiệp vụ yêu cầu khôi phục chính xác.

### 2.2. Retry, restart, replay, rerun không giống nhau

| Cơ chế | Phạm vi | Cách suy nghĩ đúng |
|---|---|---|
| **Retry** | Thử lại một thao tác/item/chunk khi job vẫn vận hành | Xử lý lỗi tạm thời, thường không thay `JobExecution`; phải đảm bảo side effect có thể lặp. |
| **Restart** | Khởi động một `JobExecution` mới của cùng `JobInstance` sau khi execution trước không hoàn thành hợp lệ | Spring Batch dùng metadata đã lưu để xác định step/chunk cần tiếp tục hoặc chạy lại. |
| **Replay message** | Broker/worker phát lại cùng đơn vị công việc | Cần idempotency tại consumer và correlation; ack không chứng minh business transaction đã commit. |
| **Rerun/new instance** | Tạo instance mới với tham số nhận diện khác hoặc sau quy trình reprocessing riêng | Có thể chạy lại toàn bộ input; phải định nghĩa nghiệp vụ và chống trùng bên ngoài metadata batch. |
| **Recovery thao tác thủ công** | Sửa dữ liệu, đối soát, bỏ qua hoặc khởi chạy lại theo runbook | Cần audit người vận hành và nguyên tắc không mất/nhân đôi dữ liệu. |

### 2.3. Checkpoint chỉ có ý nghĩa khi gắn với commit

Với chunk-oriented step, Spring Batch xử lý các item theo chunk và thường persist checkpoint ở các boundary transaction đã cấu hình. Khi một chunk thất bại **trước khi commit**, dữ liệu trong chunk đó có thể phải được đọc và xử lý lại sau retry hoặc restart. **Commit interval** ảnh hưởng đến lượng công việc có thể bị lặp nhưng không tự tạo ra bảo đảm end-to-end exactly-once.

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant DB as Transactional Store
    participant JR as JobRepository
    R->>P: Đọc và xử lý chunk N
    P->>W: Các item đã xử lý
    W->>DB: Ghi dữ liệu trong transaction
    DB-->>W: Transaction commit
    W-->>JR: Framework lưu checkpoint tại boundary
    Note over DB,JR: Phạm vi atomicity thực tế tùy transaction manager và tài nguyên liên quan
    R->>P: Bắt đầu chunk N+1
    Note over R,P: Nếu tiến trình chết, có thể phải xử lý lại phần chưa checkpoint
~~~

Sơ đồ biểu diễn ý tưởng; không nên suy diễn rằng **DB nghiệp vụ** và **JobRepository** luôn commit nguyên tử. Nếu dùng hai nguồn dữ liệu/transaction manager hoặc gọi API bên ngoài, có thể xảy ra “ghi nghiệp vụ đã thành công nhưng checkpoint chưa được ghi”, dẫn đến xử lý lại khi restart. Phải đánh giá transaction topology thực tế.

**Nguyên tắc:** một reader lưu được cursor không đủ để chứng minh restart an toàn; writer, hệ thống đích và mọi side effect cũng phải chịu được phát lại.

## 3. Biến yêu cầu nghiệp vụ thành tiêu chí đo được

Trước khi chọn model, lập một **restart requirement profile** cho từng job:

| Tiêu chí | Câu hỏi cần trả lời | Ví dụ yêu cầu |
|---|---|---|
| **Recovery time / RTO** | Từ khi phát hiện lỗi đến khi job tiếp tục chạy hữu ích được phép mất bao lâu? | Worker lỗi cần phục hồi trong 10 phút. |
| **Data loss tolerance** | Có chấp nhận bỏ sót/đánh mất item đã nhận không? | Không chấp nhận mất giao dịch. |
| **Replay/reprocessing window** | Được phép đọc/ghi lại bao nhiêu item hoặc bao nhiêu phút công việc? | Tối đa 5.000 item phải xử lý lại sau một sự cố. |
| **Duplicate side effect tolerance** | Ghi lặp có gây sai tiền, gửi email trùng, xuất hóa đơn trùng không? | Mỗi khoản thanh toán phải có kết quả nghiệp vụ một lần. |
| **Ordering** | Có bắt buộc xử lý theo thứ tự giữa item hoặc giữa tenant? | Giao dịch trong cùng tài khoản phải theo thứ tự timestamp + ID. |
| **Failure isolation** | Khi một worker chết, cần chạy lại cả step hay chỉ partition bị lỗi? | Chỉ các partition chưa hoàn tất được làm lại. |
| **Infrastructure failure** | Phải chịu lỗi JVM, node, broker, database, mạng ở mức nào? | Chịu lỗi một worker và redelivery message. |
| **Version compatibility** | Có restart job được tạo ở release cũ sau khi deploy release mới không? | Cần hỗ trợ restart qua rolling deployment. |
| **Manual recovery** | Có thể chấp nhận đối soát thủ công hoặc batch compensating không? | Hệ thống đối soát ngân hàng bắt buộc bước xác nhận. |
| **SLA throughput** | Sau khi áp đặt các ràng buộc trên, phải hoàn thành bao nhiêu item/giờ? | 30 triệu bản ghi trước 06:00. |

**Không dùng RPO như một từ thay thế mơ hồ cho lượng công việc phải chạy lại.** Với batch tài chính, mục tiêu thường là **không mất dữ liệu đã nhận**; restart có thể replay một số item mà vẫn đạt zero logical data loss. Vì vậy, tách rõ *data-loss tolerance*, *reprocessing window* và *duplicate side effect tolerance*.

Ví dụ hai job cùng xử lý 10 triệu item:

- **Job A:** tổng hợp báo cáo đọc từ snapshot bất biến, ghi bảng staging và thay thế báo cáo theo phiên bản. Có thể chạy lại 100.000 item, thậm chí dựng lại cả partition, miễn không mất dữ liệu. Restart đơn giản, không cần hệ thống điều phối phân tán phức tạp.
- **Job B:** trích nợ hoặc gọi API phát lệnh thanh toán; không được phát lệnh trùng. Dù chunk size = 1, restart vẫn nguy hiểm nếu lệnh bên ngoài đã thành công nhưng checkpoint chưa được lưu. Cần idempotency key và quy trình đối soát với hệ thống đích.

## 4. Ma trận lựa chọn theo yêu cầu restart

Bảng sau mô tả **xu hướng** khi ứng dụng đã cấu hình state và transaction đúng. Không mô hình nào tự bảo đảm chính xác dữ liệu nếu reader/writer không restartable hoặc side effect không idempotent.

| Mô hình | Phạm vi checkpoint / khôi phục | Điểm mạnh | Rủi ro đối với restart | Đánh giá khi restart nghiêm ngặt |
|---|---|---|---|---|
| **Single-threaded chunk step** | `ExecutionContext` và commit theo một luồng xử lý | Dễ xác định thứ tự, cursor và vùng công việc chưa commit | I/O đích ngoài transaction vẫn có thể bị ghi trùng | **Ưu tiên làm baseline** nếu đạt SLA |
| **Multi-threaded step** | Nhiều chunk đang chạy; cùng step có state/concurrency phức tạp | Tăng throughput trong một JVM, thay đổi topology ít | Reader/processor/writer không thread-safe; completion khác thứ tự đọc; checkpoint khó chứng minh | **Cần thận trọng**, chỉ chọn nếu đã kiểm thử restart dưới concurrency |
| **Parallel steps** | Mỗi step có `StepExecution` riêng | Cô lập các luồng nghiệp vụ độc lập; step completed có thể được bỏ qua khi restart | Các step cùng đụng dữ liệu/đầu ra hoặc có dependency ẩn | **Rất phù hợp** khi step độc lập và ranh giới rõ |
| **Local partitioning** | Mỗi partition có `StepExecution`/`ExecutionContext` riêng, cùng tiến trình | Phân vùng rõ, theo dõi và khởi chạy lại partition chưa hoàn tất | Partition name/range thay đổi; nguồn dữ liệu biến động; metadata/transaction | **Thường phù hợp** cho dataset có thể chia ổn định |
| **Remote partitioning** | Partition `StepExecution` ở worker; metadata chia sẻ qua `JobRepository` | Cô lập lỗi worker, mở rộng theo node, khôi phục theo partition | Broker redelivery, worker mồ côi, phiên bản/schema, metadata chung | **Phù hợp** nếu cần multi-node và đã có quy trình đối soát |
| **Remote chunking** | Reader/checkpoint chủ yếu ở manager; worker xử lý các chunk qua message | Phân phối phần xử lý/ghi tốn tài nguyên | Mất response sau khi worker commit, duplicate delivery, trạng thái manager–broker–DB không nguyên tử | **Chọn có điều kiện**, đòi hỏi idempotency và kiểm thử failure window nghiêm ngặt |

Giải thích đánh giá:

- **Single-threaded không luôn là chậm:** Với I/O-bound workload, tăng thread có thể không cải thiện khi database/pool đã là điểm nghẽn. Nếu throughput đủ, đây thường là kiến trúc dễ chứng minh restart nhất.
- **Parallel steps không thay thế partitioning:** Khi dữ liệu là những luồng nghiệp vụ độc lập (ví dụ xử lý khách hàng và xử lý tồn kho), parallel steps là cách chia phù hợp; cùng một tập dữ liệu lớn cần cắt miền công việc thường hợp partitioning hơn.
- **Partitioning cần ranh giới ổn định:** Điểm mạnh khôi phục theo partition chỉ giữ được khi tên, phạm vi và điều kiện lọc không thay đổi tùy ý qua restart.
- **Remote chunking mang nhiều failure window:** Cùng một chunk có thể đã commit nghiệp vụ nhưng manager chưa nhận response; cần hợp đồng idempotent rõ ràng tại worker.

## 5. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Thu thập yêu cầu restart, dữ liệu và SLA] --> B{Một chunk step đơn luồng đạt SLA?}
    B -- Có --> C[Single-threaded chunk, checkpoint rõ]
    B -- Không --> D{Nhiệm vụ là các step độc lập?}
    D -- Có --> E[Parallel steps với trạng thái riêng]
    D -- Không --> F{Có thể chia dữ liệu thành vùng ổn định?}
    F -- Có --> G{Một JVM đủ tài nguyên?}
    G -- Có --> H[Local partitioning]
    G -- Không --> I[Remote partitioning]
    F -- Không --> J{Có thể xử lý chunk phân tán với side effect idempotent?}
    J -- Có --> K[Đánh giá remote chunking bằng failure tests]
    J -- Không --> L[Thiết kế lại input/transaction/restart, hoặc giữ thực thi tuần tự]
    C --> M[Failure-injection + kiểm chứng checkpoint]
    E --> M
    H --> M
    I --> M
    K --> M
    L --> M
    M --> N{Đạt correctness + RTO + throughput?}
    N -- Không --> A
    N -- Có --> O[Chấp nhận kiến trúc và tài liệu runbook]
~~~

Sơ đồ là **hướng dẫn chọn lựa**, không phải lệnh mặc định. Có trường hợp multi-threaded step thích hợp hơn partitioning, chẳng hạn các tác vụ không lưu state và chỉ tính toán trên item bất biến; tuy nhiên phải xác minh thực tế về thread safety, ordering và checkpoint trước khi chấp nhận. Khi yêu cầu restart nghiêm ngặt, hãy coi multi-threaded step là lựa chọn cần **thêm bằng chứng**, không mặc định là đường mở rộng đầu tiên.

## 6. Chọn checkpoint và commit interval theo phạm vi chạy lại

### 6.1. Tương quan chunk size và lượng công việc lặp

Giả sử một chunk có tối đa `C` item và commit thành công sau khi hoàn tất. Nếu tiến trình chết trong khi xử lý chunk, phần chưa commit thường phải được thực hiện lại. Với single-threaded chunk, **một phạm vi cần replay xấp xỉ tối đa một chunk** là cách ước lượng trực giác, với điều kiện transaction và trạng thái reader/writer tuân theo thiết kế; thực tế có thể khác do prefetch, retry, buffering, transactional topology và cách reader lưu state.

Khi có `K` chunk đang xử lý đồng thời, lượng công việc in-flight có thể tăng tương ứng. Chỉ dùng biểu thức sau làm **ước lượng sơ bộ** để lập kế hoạch, không xem là mức bảo đảm:

~~~text
Estimated in-flight work ≈ concurrent chunks × chunk size

Ví dụ minh họa:
K = 8, C = 500
=> khoảng 4.000 item đang trong những chunk có thể cần xét lại
~~~

Với external side effect ngoài transaction, lượng tác động cần đối soát **có thể lớn hơn** do retry/replay và sai lệch checkpoint. Do đó, số item in-flight không phải giới hạn an toàn tuyệt đối.

### 6.2. Trade-off của chunk size

| Chunk size | Ưu điểm | Rủi ro và chi phí |
|---|---|---|
| Nhỏ (ví dụ 10–100) | Lượng replay cục bộ nhỏ, checkpoint thường xuyên, giảm kích thước transaction | Nhiều transaction/metadata write, overhead cao, throughput có thể giảm |
| Trung bình (ví dụ 500–2.000) | Có thể cân bằng throughput và vùng replay | Cần thử nghiệm với kích thước item, network và DB |
| Lớn (ví dụ 5.000+) | Có thể giảm overhead commit | Transaction dài, lock lâu, retry/restart lặp nhiều, heap usage lớn |

Các giá trị chỉ là ví dụ **không phải khuyến nghị mặc định**. Chunk size phù hợp cần đo trên workload đại diện, với cùng mức concurrency, reader, writer và storage.

Khi dùng retry/skip, phải hiểu transaction rollback và retry state của `ItemProcessor`/`ItemWriter`; một item có thể qua processor nhiều lần. Không dựa vào số lần `process()` được gọi để quyết định “một lần ghi nghiệp vụ duy nhất”.

## 7. Trường hợp 1: Single-threaded chunk step khi ưu tiên restart dễ dự đoán

Đây là baseline tốt khi:

- Reader có thể lưu trạng thái và khôi phục theo checkpoint (ví dụ vị trí đọc ổn định hoặc keyset cursor).
- Item có thứ tự xác định từ nguồn dữ liệu; input snapshot không đổi tùy ý giữa các lần restart.
- Writer dùng cùng transaction manager với cơ chế lưu state khi có thể, hoặc có idempotency.
- Throughput đáp ứng SLA, hoặc bottleneck nằm ở hệ thống đích nên thêm thread không giúp.

Ví dụ pipeline:

~~~text
Read invoice snapshot theo id tăng dần
    -> validate/transform
    -> upsert bảng tổng hợp theo business key
    -> commit chunk và checkpoint
~~~

Khi restart, không tự xóa `ExecutionContext` để “bắt đầu ở dòng chưa biết”. Nếu schema dữ liệu thay đổi hoặc cursor không đáng tin, phải dừng và thực hiện đối soát thay vì ép Spring Batch tiếp tục từ trạng thái mơ hồ.

Lưu ý: các reader như `JdbcCursorItemReader`, `JdbcPagingItemReader`, `FlatFileItemReader` có cách lưu và khôi phục state khác nhau. Kiểm tra `saveState`, tên reader, query/order và cách chúng được sử dụng khi concurrency; **không giả định mọi reader mặc định an toàn khi dùng chung giữa nhiều thread**.

## 8. Trường hợp 2: Multi-threaded step cần chứng minh khả năng replay

Multi-threaded step có thể xử lý nhiều chunk song song bằng `TaskExecutor`. Nó tạo thêm tình huống:

1. Chunk A đọc trước nhưng chunk B có thể commit trước.
2. Reader có thể bị nhiều thread gọi, đặc biệt nếu dùng instance chia sẻ.
3. Writer nhận các chunk hoàn thành khác thời điểm, có thể cạnh tranh trên cùng bảng hoặc khóa nghiệp vụ.
4. Một thất bại có thể ảnh hưởng các chunk đang xử lý khác; replay cần xét đến thứ tự và checkpoint.
5. Sử dụng wrapper đồng bộ reader có thể bảo vệ race, nhưng **không tự giải quyết chính xác restart khi thứ tự commit khác thứ tự đọc**.

**Không dùng `SynchronizedItemStreamReader` như lời giải tổng quát cho restart.** Nó có thể giúp đồng bộ thao tác đọc, nhưng nếu việc đọc được phân phối sang nhiều chunk và chunk hoàn thành khác thứ tự, restart vẫn có thể phát sinh replay/skip tùy reader và logic nghiệp vụ. Mỗi cơ chế cần test cụ thể.

Chỉ cân nhắc khi:

- Từng item có business key độc lập, xử lý không đòi hỏi thứ tự.
- Reader/writer có thread safety và checkpoint đã được kiểm chứng, hoặc dùng thiết kế đọc/phân phối có kiểm soát.
- Side effect idempotent; rollback của chunk không tạo tác động không thể hoàn tác.
- Fault-injection test chứng minh không mất item khi thread crash, restart job, timeout và writer retry.

Nếu không chứng minh được các điều kiện này, **partitioning theo miền dữ liệu** thường tạo ranh giới khôi phục rõ ràng hơn vì mỗi partition có `StepExecution` riêng.

## 9. Trường hợp 3: Parallel steps phục hồi theo công việc độc lập

Với những bước không phụ thuộc hoặc có dependency được mô hình hóa rõ, `split()` cho phép chạy nhiều flow/step song song. Các step có execution metadata riêng; khi restart, step đã `COMPLETED` thường được bỏ qua, còn step chưa hoàn tất được đánh giá để chạy lại. Thuộc tính `allowStartIfComplete` có thể thay đổi hành vi mặc định; cần cấu hình có chủ đích.

Ví dụ:

~~~mermaid
flowchart LR
    A[Start job] --> B[Flow A: đọc dữ liệu kho]
    A --> C[Flow B: đọc dữ liệu bán hàng]
    B --> D[Step A đã COMPLETED]
    C --> E[Step B FAILED]
    D --> F[Restart: bỏ qua Step A nếu cấu hình mặc định]
    E --> G[Restart: thực hiện lại phần Step B]
    F --> H[Tiếp tục flow/join theo trạng thái]
    G --> H
~~~

**Cảnh báo phụ thuộc ẩn:** Nếu Flow B ghi vào cùng tập dữ liệu do Flow A đã cập nhật, restart chỉ một flow có thể tạo kết quả không nhất quán. Thiết kế nên phân định output, transaction và trạng thái “đã publish” cuối cùng. Khi các flow tạo ra dữ liệu trung gian, dùng staging/versioned output rồi publish sau khi mọi flow hoàn tất.

Parallel steps phù hợp hơn multi-threaded step nếu phần chia được thành **các bước độc lập**, mỗi bước có reader/writer và checkpoint riêng. Không chia một step phụ thuộc thứ tự thành nhiều step chỉ để lấy concurrency.

## 10. Trường hợp 4: Local partitioning cho ranh giới restart rõ ràng

Partitioning chia dataset thành các vùng không chồng lấn và tạo `StepExecution` cho từng partition. Với `TaskExecutorPartitionHandler`, worker step có thể chạy trong cùng JVM; manager vẫn tổng hợp metadata từng partition.

Ví dụ xử lý khoảng khóa định danh:

~~~text
Snapshot source: invoice ID từ 1 tới 12.000.000
rangeSize: 300.000

partition-00000: [1, 300.000]
partition-00001: [300.001, 600.000]
...
partition-00039: [11.700.001, 12.000.000]
~~~

Nếu partition-00007 lỗi khi 37 partition khác đã hoàn tất, restart có thể chỉ thực hiện lại những partition chưa hoàn thành theo metadata step và cấu hình. Điều này chỉ đúng khi **partition names, step identity và state vẫn đối chiếu đúng với lần chạy trước**.

### 10.1. Ví dụ Java: partition theo khoảng ID ổn định

Mẫu sau minh họa Spring Batch 5.x với `Partitioner`. Khoảng `minId`/`maxId` và `rangeSize` phải được chốt từ dữ liệu của `JobInstance` hoặc một snapshot bất biến đã lưu; không truy bảng để tính ngẫu nhiên vùng dữ liệu mỗi lần restart.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class StableRangePartitioner implements Partitioner {
    private final long minId;
    private final long maxId;
    private final long rangeSize;

    public StableRangePartitioner(long minId, long maxId, long rangeSize) {
        if (minId < 0 || maxId < minId || rangeSize <= 0) {
            throw new IllegalArgumentException("Invalid frozen ID range");
        }
        this.minId = minId;
        this.maxId = maxId;
        this.rangeSize = rangeSize;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        // Số khoảng được quyết định bởi rangeSize cố định;
        // gridSize được dùng để điều tiết concurrency ở cấu hình quản lý.
        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long start = minId;
        int index = 0;

        while (start <= maxId) {
            long end = maxId - start < rangeSize
                    ? maxId
                    : start + rangeSize - 1;

            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", start);
            context.putLong("maxIdInclusive", end);

            String partitionName =
                    String.format(Locale.ROOT, "range-%06d", index++);
            result.put(partitionName, context);

            if (end == maxId) {
                break;
            }
            start = end + 1;
        }
        return result;
    }
}
~~~

Worker step đọc dữ liệu theo điều kiện đã đóng băng:

~~~sql
SELECT invoice_id, customer_id, amount
FROM invoice_snapshot
WHERE snapshot_id = :snapshot_id
  AND invoice_id >= :min_id_inclusive
  AND invoice_id <= :max_id_inclusive
ORDER BY invoice_id;
~~~

Các biến `min_id_inclusive`/`max_id_inclusive` lấy từ `ExecutionContext` của partition; `snapshot_id` được gắn với `JobInstance` hoặc input snapshot ổn định. `ORDER BY invoice_id` cần khóa xác định duy nhất; nếu key không unique, thêm tie-breaker.

**Quan trọng:** ví dụ chỉ minh họa partitioner; reader, worker step, StepScope injection và repository phải được cấu hình nhất quán theo version Spring Batch thực tế. `gridSize` không nên được hiểu là “tự động số thread thực tế”: số worker đồng thời phụ thuộc executor, pool, queue, network và hạ tầng.

### 10.2. Không đổi danh tính partition khi restart

Một anti-pattern điển hình:

~~~text
Lần chạy đầu: 8 partition, chia theo index của danh sách ID hiện tại
Restart:       16 partition, tính lại ranh giới từ dữ liệu đã thay đổi
Kết quả:       tên partition cũ không còn khớp vùng dữ liệu mới
~~~

Khả năng restart theo partition phụ thuộc vào **tên partition ổn định**. Khi dùng `PartitionNameProvider` để tối ưu việc xác định tên trên restart, tập tên phải nhất quán với các partition đã phát hành; interface này không cứu được việc ranh giới dữ liệu đổi.

Chốt min/max/rangeSize/snapshot trước khi manager tạo partition, và giữ nguyên trong cùng JobInstance. Nếu dữ liệu được thêm/xóa trong quá trình chạy, phải chọn một trong các chiến lược: snapshot bất biến, high-water mark + filter cố định, hoặc thiết kế CDC/event offset có quy tắc riêng; không dựa vào “ID từ nhỏ đến lớn” khi các hàng có thể biến mất hoặc cập nhật điều kiện lọc.

### 10.3. Sự cố tại partition và độ mịn restart

Có hai mức tái xử lý:

- **Theo partition:** partition `FAILED`/`STOPPED` được chạy lại theo trạng thái lưu; partition `COMPLETED` thường không cần chạy lại.
- **Theo checkpoint bên trong partition:** worker step dùng chunk + reader có state bền vững thì có thể tiếp tục từ checkpoint trong vùng partition, không cần đọc lại toàn bộ vùng.

Một partition chứa 500.000 bản ghi nhưng không lưu checkpoint có thể buộc xử lý lại nhiều dữ liệu sau crash. Vì vậy, chọn partition size **và** chunk commit interval cùng lúc; partitioning chỉ định ranh giới lỗi, còn chunk/checkpoint quyết định khối lượng replay bên trong.

## 11. Trường hợp 5: Remote partitioning cho restart trên nhiều node

Remote partitioning mở rộng ý tưởng partition sang các worker process/node. Manager tạo partition `StepExecution` và truyền yêu cầu chạy step qua messaging; worker phải truy cập metadata execution cần thiết, thường từ **JobRepository chia sẻ**. Worker có thể chết sau khi nhận request nhưng trước khi cập nhật trạng thái; hoặc đã commit dữ liệu nhưng manager chưa nhận kết quả.

Các điều kiện tối thiểu để chọn remote partitioning khi restart quan trọng:

1. **JobRepository bền vững, cấu hình nhất quán**, với cơ chế khóa và transaction phù hợp các instance đồng thời.
2. **Partition identity ổn định** qua restart, ranh giới dữ liệu không thay đổi hoặc có version/snapshot.
3. **Worker step restartable**: reader lưu state đúng, writer chịu được retry/replay.
4. **At-least-once delivery được tính đến:** broker có thể redeliver; không giả định một request chỉ tới một worker đúng một lần.
5. **Liveness và timeout rõ ràng:** biết khi nào manager đánh dấu failed/stopped, khi nào worker cũ thật sự không còn thực thi, và cách ngăn hai worker cùng ghi cùng partition.
6. **Version compatibility:** manager mới, worker cũ và metadata `ExecutionContext` cũ phải tương thích trong giai đoạn rolling deployment.
7. **Runbook reconcile:** khi broker ack nhưng JobRepository chưa hoàn tất, hoặc worker mồ côi tiếp tục ghi, operator biết cách kiểm tra và phục hồi.

Trong môi trường có nguy cơ worker cũ sống lại sau network partition, cần xem xét **fencing token/lease có kiểm soát ở mức business operation**, ngoài việc kiểm tra trạng thái `StepExecution`. Chỉ nhìn vào message ID không đủ đảm bảo hai worker không đồng thời ghi cùng tài nguyên.

Bản chất lựa chọn: remote partitioning thường có ranh giới khôi phục **dễ giải thích** hơn remote chunking nếu dataset có thể partition ổn định. Đổi lại, hệ thống phải vận hành repository, worker fleet, broker, monitoring và xử lý lỗi mạng một cách có kỷ luật.

## 12. Trường hợp 6: Remote chunking khi restart đòi hỏi nhiều bảo đảm

Trong remote chunking, manager thường đọc/điều phối chunk và gửi dữ liệu hoặc tham chiếu qua message broker; worker xử lý/ghi và trả response. Cơ chế này hữu ích khi bước xử lý/ghi tốn CPU hoặc I/O ở đích, nhưng có một cửa sổ lỗi quan trọng:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker
    participant W as Worker
    participant D as Business DB
    M->>B: Chunk request (workUnitId=42)
    B->>W: Giao request
    W->>D: Ghi dữ liệu
    D-->>W: COMMIT thành công
    Note over W,M: Worker chết hoặc response bị mất
    B-->>M: Timeout / chưa có response
    M->>B: Retry hoặc replay workUnitId=42
    B->>W: Giao lại
    W->>D: Dữ liệu có thể bị ghi lại
~~~

Nếu writer gọi API gửi tiền hoặc gửi email không hỗ trợ idempotency, message replay có thể gây duplicate side effect. **Acknowledgement của broker, response của worker và commit nghiệp vụ là các thời điểm khác nhau**. Trong mạng phân tán, không nên tuyên bố “exactly once” end-to-end chỉ vì Spring Batch lưu checkpoint hoặc broker hỗ trợ transaction của riêng nó.

### 12.1. Thiết kế idempotency

Một cách là kết hợp:

- **Business idempotency key:** được suy từ hành động nghiệp vụ ổn định (ví dụ `settlementId + operationType`), không chỉ từ `jobExecutionId`, vì restart/new instance có thể phát lại cùng hành động.
- **Inbox/ledger:** phát hiện request xử lý lại, ghi trạng thái thực hiện và outcome.
- **Unique constraint hoặc upsert có điều kiện:** ngăn ghi hai lần vào cùng business key.
- **Transactional outbox:** khi phát thông điệp ra hệ thống khác, ghi intent/outbox cùng transaction DB chính rồi publish độc lập; consumer vẫn cần idempotent.
- **External idempotency API:** nếu gọi hệ thống ngoài, chuyển key ổn định qua API và xác minh thời gian lưu key/cách tra cứu trạng thái.
- **Reconciliation:** đối chiếu trạng thái business DB, message, batch metadata và hệ thống đích sau timeout.

Ví dụ lược giản về ràng buộc dữ liệu:

~~~sql
CREATE TABLE settlement_result (
    settlement_id    VARCHAR(100) PRIMARY KEY,
    source_version   BIGINT NOT NULL,
    computed_amount  DECIMAL(19, 4) NOT NULL,
    updated_at       TIMESTAMP NOT NULL
);

-- Mẫu PostgreSQL: cùng settlement + version thì ghi lặp có cùng kết quả;
-- nguồn cũ không được ghi đè kết quả được tính từ version mới hơn.
INSERT INTO settlement_result (
    settlement_id, source_version, computed_amount, updated_at
)
VALUES (:settlement_id, :source_version, :computed_amount, CURRENT_TIMESTAMP)
ON CONFLICT (settlement_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    computed_amount = EXCLUDED.computed_amount,
    updated_at = EXCLUDED.updated_at
WHERE settlement_result.source_version <= EXCLUDED.source_version;
~~~

Mẫu này giúp một thao tác cập nhật **deterministic** trên cùng business key, nhưng không xử lý tất cả vấn đề “exactly once”: phép cộng dồn không thể thay trực tiếp bằng upsert; external API side effect cần thiết kế riêng; cùng source version mà computed_amount không xác định cũng nguy hiểm. Khi thao tác nhiều bảng, ledger và dữ liệu nghiệp vụ cần đồng nhất transaction nếu có thể.

### 12.2. Khi nào tránh remote chunking vì yêu cầu restart?

Nên hoãn hoặc thiết kế lại nếu:

- Một chunk gửi lệnh không thể lặp, không thể tra trạng thái, không có idempotency key.
- Hệ thống chưa phân biệt response timeout và business transaction failure.
- Reader/manager không duy trì checkpoint, outstanding chunk và correlation tin cậy.
- Không có DLQ/replay policy hoặc runbook đối soát chunk bị mất phản hồi.
- Không thử được các failure window: worker commit rồi chết; manager crash trước nhận response; broker giao trùng; deployment lệch version.

Trong trường hợp workload có thể phân theo tenant, range hoặc snapshot ID, remote partitioning với worker chunk step độc lập thường là phương án dễ lập luận về restart hơn. Quyết định cuối cùng vẫn cần đo throughput và kiểm chứng source/target transaction.

## 13. Khung chấm điểm chọn mô hình

Sau khi vượt qua các ràng buộc bắt buộc (đúng dữ liệu, không mất, ngưỡng replay, khả năng đối soát), có thể dùng bảng trọng số để thảo luận. **Không dùng tổng điểm để hợp thức hóa một mô hình thất bại ở tiêu chí correctness bắt buộc.**

Ví dụ thang điểm `1 = bất lợi` đến `5 = thuận lợi` cho một workload có dữ liệu phân khoảng ổn định, database transactional, cần phục hồi từng phần và đang có một cụm worker; điểm là **minh họa**, phải hiệu chỉnh theo PoC:

| Tiêu chí | Trọng số | Single-thread | Multi-thread | Parallel steps | Local partition | Remote partition | Remote chunk |
|---|---:|---:|---:|---:|---:|---:|---:|
| Độ dễ chứng minh restart | 30% | 5 | 2 | 4 | 4 | 4 | 2 |
| Khả năng cô lập lỗi | 20% | 2 | 2 | 4 | 4 | 5 | 3 |
| Độ phức tạp vận hành thấp | 15% | 5 | 3 | 4 | 4 | 2 | 2 |
| Khả năng tăng throughput | 20% | 2 | 3 | 3 | 4 | 5 | 5 |
| Khả năng mở rộng theo node | 15% | 1 | 1 | 1 | 1 | 5 | 5 |

Đối với dữ liệu không partition được, điểm của partitioning phải giảm; với batch chỉ xử lý một JVM và SLA nhỏ, trọng số vận hành có thể cao hơn. Với payment side effect không idempotent, remote chunking bị loại ngay dù điểm throughput cao.

Để có kết quả có thể kiểm toán:

1. Xác định **hard constraints** và minh chứng của từng mô hình.
2. Đo workload baseline, latency, bottleneck và failure behavior.
3. Dùng trọng số cho các phương án đã qua ngưỡng correctness.
4. Ghi quyết định, trade-off, ngưỡng mở rộng và trigger cần đánh giá lại sau này.

## 14. Case study: xử lý 24 triệu bản ghi với yêu cầu restart nghiêm ngặt

**Bối cảnh:** job tổng hợp giao dịch mỗi đêm, có 24 triệu dòng trong snapshot bất biến. Đầu ra nằm trong database hỗ trợ transaction và unique business key. SLA hoàn thành trước 06:00; nếu một worker chết, chỉ chấp nhận tối đa 15 phút gián đoạn và không cho phép mất/trùng kết quả.

### 14.1. Xác nhận yêu cầu

~~~text
Input:          24.000.000 bản ghi; snapshotId cố định cho JobInstance
Output:         Bảng aggregate với business key + source_version
Correctness:    Không mất item, không nhân đôi kết quả cuối
Recovery time:  Mục tiêu <= 15 phút sau khi phát hiện sự cố
Partitioning:   Theo dải ID, ranh giới ổn định
Durability:     JobRepository trên database bền vững
Dependencies:   Không có thứ tự nghiệp vụ giữa các dải ID
~~~

Dữ liệu ID có thể bị thưa; điều quan trọng là mỗi bản ghi hợp lệ thuộc **đúng một khoảng**, không phải khoảng nào cũng chứa số item bằng nhau. Để cân tải tốt, nên đo độ phân bố và có thể chọn ranh giới theo histogram, nhưng các ranh giới đó vẫn phải được chốt trước khi chạy và tái sử dụng khi restart.

### 14.2. Ma trận rút gọn

| Phương án | Kết luận sơ bộ |
|---|---|
| Single-threaded | Baseline đo để biết throughput và chi phí checkpoint; giữ nếu đáp ứng SLA |
| Multi-threaded step | Loại khỏi shortlist nếu không chứng minh được restart dưới concurrency với reader hiện hữu |
| Parallel steps | Không tự nhiên vì tập dữ liệu là một pipeline chia theo vùng, thay vì các flow độc lập |
| Local partitioning | Phương án ưu tiên nếu một node đủ CPU, RAM, connection pool |
| Remote partitioning | Phương án khi đo xác nhận một node không đủ; cần JobRepository chung và failure tests |
| Remote chunking | Không phải lựa chọn đầu vì workload đã có khóa phân vùng ổn định; tăng complexity messaging/dedup không cần thiết |

### 14.3. Phác thảo thiết kế

- Dùng `snapshotId` và ranh giới ID được lưu bền vững trong metadata/đầu vào của JobInstance.
- Chia **48 partition**, mỗi partition dùng chunk size **500** làm điểm bắt đầu thử nghiệm; số lượng này là giả định PoC, không phải sizing production cố định.
- Worker đọc theo `snapshotId + idRange` với thứ tự khóa xác định, ghi idempotent vào bảng aggregate.
- Tăng `gridSize`/concurrency sau khi kiểm tra connection pool, lock contention, I/O và JobRepository throughput.
- Khi lỗi partition, restart cùng JobInstance; `COMPLETED` partitions được nhận diện theo tên, những phần chưa hoàn thành được xử lý lại theo checkpoint.
- Có dashboard theo JobExecution/StepExecution, missing partition và độ trễ phục hồi; có cảnh báo orphan worker và mismatched output counts.

### 14.4. Chứng minh restart bằng phép thử sự cố

Giả sử `partition-00017` đã ghi 67.500 trong 100.000 item dự kiến và tiến trình worker chết trước commit chunk kế tiếp. Khi restart, cần kiểm chứng:

1. Metadata phân biệt được partition đã hoàn tất và partition chưa hoàn tất.
2. `partition-00017` không bắt đầu từ vị trí ngẫu nhiên hoặc tính ra ranh giới khác.
3. Số item đã commit được lưu đúng; item chưa commit có thể đọc/ghi lại theo checkpoint.
4. Việc reprocess không làm tăng tổng business key hoặc làm mất dữ liệu.
5. Mọi partition đã `COMPLETED` không tự nhiên chạy lại khi dùng cấu hình mặc định.
6. Thời gian khởi động lại worker và hoàn thành phần còn lại đáp ứng mục tiêu 15 phút trong môi trường đo.

Không khẳng định kết quả chỉ dựa trên `readCount == writeCount` vì skip/filter, rollback và duplicate có thể làm counters khó diễn giải. Cần đối soát **tập business key, tổng số và tổng giá trị** theo snapshot nguồn, cộng thêm kiểm tra riêng những item bị skip theo quy tắc nghiệp vụ.

## 15. Bộ thử nghiệm failure injection bắt buộc

Chọn kiến trúc theo restart không thể dừng ở sơ đồ và cấu hình. Tối thiểu cần tạo lỗi có chủ đích trong môi trường thử nghiệm tương đương:

| Điểm gây lỗi | Điều cần chứng minh |
|---|---|
| JVM chết trong `ItemProcessor` trước commit | Chunk chưa commit được xử lý lại, không mất item |
| Writer ghi xong nhưng transaction rollback | Side effect được rollback hoặc idempotency ngăn ghi trùng |
| DB nghiệp vụ commit nhưng checkpoint chưa rõ | Reconcile xử lý được trạng thái mơ hồ, không tự phát lại thao tác nguy hiểm |
| Restart với cùng JobInstance và identifying parameters | Framework tạo execution mới phù hợp; không vô tình rerun toàn bộ |
| Restart sau thay đổi `chunkSize`/`gridSize` | Ranh giới item/partition vẫn đúng; thay đổi nếu có phải được chứng minh an toàn |
| Crash một worker trong local/remote partitioning | Partition lỗi được chạy lại đúng; partition thành công không bị nhân đôi kết quả |
| Hai worker có thể cùng nhận một partition | Fencing/idempotency ngăn side effect chồng lấn |
| Broker redeliver remote chunk sau commit | Consumer xử lý trùng có thể nhận biết và trả lại outcome đúng |
| Manager chết sau khi gửi chunk | Outstanding requests được đối soát; không mất chunk hoặc phát trùng không kiểm soát |
| Rolling deployment khác serializer/schema | Worker mới đọc được message và `ExecutionContext` còn phải hỗ trợ |
| Input thay đổi giữa lần chạy và restart | Snapshot/high-water mark đảm bảo không bỏ sót hoặc xử lý vượt phạm vi |
| Operator stop/restart đồng thời | Không tạo hai execution chạy cùng business scope trái quy định |

**Các phép thử phải đo cả correctness lẫn recovery time.** Một job restart “thành công” ở trạng thái `COMPLETED` nhưng ghi trùng tiền không đạt yêu cầu.

Nên xây dựng một tập golden dataset có business key duy nhất và các bản ghi được đánh dấu phiên bản nguồn. Sau mỗi lần tiêm lỗi, so sánh đầu ra thực với kết quả tham chiếu độc lập:

~~~text
expectedKeys == actualKeys
expectedAmounts == actualAmounts
unexpectedDuplicates == 0
unprocessedRecords == 0 (hoặc đúng danh mục skip có lý do)
recoveryDuration <= recoverySLA
~~~

## 16. Observability và runbook restart

### 16.1. Metrics và log tối thiểu

- `job_execution_status`, `step_execution_status`, số partition `COMPLETED`/`FAILED`/`STARTED`.
- Read/write/skip/rollback/retry counts theo job/step và thời gian; lưu ý quan hệ giữa attempt và committed work.
- Thời gian checkpoint, chunk duration, connection pool saturation và JobRepository latency.
- Số message redelivery/timeout/DLQ đối với remote chunking/partitioning.
- Số work unit cần reconciliation và số lỗi idempotency/fencing.
- Recovery time thực tế từ phát hiện sự cố đến khi job xử lý lại hữu ích, và đến khi job hoàn tất.

Không đưa `jobExecutionId`, `stepExecutionId`, `partitionId` biến thiên cao vào Prometheus labels nếu gây nổ cardinality. Dùng log cấu trúc, traces và JobExplorer để tra cứu execution cụ thể.

### 16.2. Quy trình operator khi job thất bại

1. **Xác nhận trạng thái thực:** tra `JobExplorer`/`JobRepository`, step errors, transaction và message backlog; phân biệt đang chạy, failed, stopped hay trạng thái stale.
2. **Đánh giá side effect:** kiểm tra output/external API; nếu có transaction không rõ kết quả thì đối soát trước.
3. **Kiểm tra phiên bản và nguồn:** bảo đảm code mới tương thích `ExecutionContext` cũ, snapshot/partition boundary không đổi.
4. **Khóa chạy đồng thời khi cần:** tránh hai job instance/execution xử lý cùng business scope; xử lý orphan worker theo runbook.
5. **Restart có audit:** dùng `JobOperator.restart` hoặc cơ chế vận hành chuẩn, ghi actor/reason/correlation, không tự đổi identifying params để né guard.
6. **Theo dõi:** số partition cần chạy lại, throughput, retry, duplicate rejection, error và ETA theo dữ liệu thực.
7. **Đối soát đầu ra:** kiểm chứng business key và invariant trước khi publish hoặc thông báo hoàn thành.

Nếu một step được thiết kế không restartable, không ép chạy lại bằng cách sửa tay metadata trong `JobRepository`. Phải có recovery/compensation procedure cụ thể và được thử nghiệm.

## 17. Anti-pattern cần tránh khi ưu tiên restart

| Anti-pattern | Hậu quả | Cách làm đúng |
|---|---|---|
| Chọn mô hình có throughput cao nhất mà chưa thử restart | Dữ liệu sai chỉ lộ khi có sự cố | Hard constraints về correctness, sau đó mới tối ưu tốc độ |
| Tăng identifying `run.id` để “restart” | Tạo JobInstance mới, có thể chạy lại toàn bộ input | Restart đúng instance hoặc định nghĩa rerun có idempotency |
| Dùng reader có state không thread-safe trong multi-threaded step | Race, mất thứ tự, checkpoint không đáng tin | Kiểm tra concurrency hoặc tách partition với reader riêng |
| Partition theo `OFFSET/LIMIT` trên dữ liệu đang thay đổi | Bỏ sót/trùng khi hàng được chèn, xóa | Snapshot/keyset với ranh giới bất biến |
| Đổi tên/range partition qua mỗi restart | Không ánh xạ đúng `StepExecution` cũ | Persist partition identity và boundary |
| Tin vào broker “exactly once” cho side effect ngoài broker | Có thể commit 2 lần hoặc mất response | Idempotency, outbox/inbox, reconciliation |
| Coi ack của worker là commit nghiệp vụ | Dữ liệu có thể chưa commit hoặc response bị mất | Quan sát transaction/outcome thực |
| Ghi trạng thái checkpoint sau khi gọi external API rồi tin rằng luôn đồng bộ | Có cửa sổ lỗi trước checkpoint | Idempotency key ổn định, tra trạng thái và compensation |
| Bật `allowStartIfComplete` bừa bãi | Step đã hoàn tất chạy lại gây trùng output | Chỉ dùng khi nghiệp vụ thật sự yêu cầu và đã test |
| Chỉnh tay bảng `BATCH_*` khi job kẹt | Phá tính nhất quán metadata | Dùng API/quy trình quản trị có audit |
| Dùng số dòng log làm nguồn đối soát | Log có thể mất hoặc lặp khi retry | Dựa vào JobRepository và invariant dữ liệu |
| Cho worker cũ chạy khi schema `ExecutionContext` không tương thích | Restart lỗi hoặc âm thầm xử lý sai | Version gate, compatibility test, migration/adapter |

## 18. Checklist quyết định cuối cùng

### Thiết kế

- [ ] Ghi rõ **data-loss tolerance**, **replay window**, **duplicate tolerance**, **recovery time** và throughput SLA.
- [ ] Phân biệt retry, restart, rerun và replay message trong runbook.
- [ ] Reader và writer có hợp đồng restart và idempotency rõ ràng.
- [ ] Chọn snapshot/ordering/partition key ổn định, không đổi ngữ nghĩa khi restart.
- [ ] Định nghĩa transaction boundary giữa JobRepository, business DB, broker và external API.
- [ ] Chọn chunk size, concurrency và partition size dựa trên đo throughput và lượng công việc cần replay.
- [ ] Tránh dùng multi-threaded step nếu chưa chứng minh thread safety và checkpoint dưới concurrency.
- [ ] Với partitioning, tên partition và boundary giữ nguyên trong JobInstance, mỗi worker có state riêng.
- [ ] Với remote chunking, có idempotency, correlation, timeout/replay policy và reconciliation.

### Kiểm thử, triển khai và vận hành

- [ ] Có baseline single-threaded để chứng minh nhu cầu scaling.
- [ ] Chạy test crash trước/sau commit, duplicate delivery, stale worker, restart và rolling upgrade.
- [ ] Kiểm tra kết quả nghiệp vụ theo business key và snapshot nguồn, không chỉ kiểm tra status `COMPLETED`.
- [ ] Đo recovery time thực tế và số item cần làm lại ở tải đại diện.
- [ ] Có dashboard JobRepository/partition/worker, metrics retry, timeout và reconciliation backlog.
- [ ] Có runbook stop/restart/abandon/compensation, phân quyền operator và audit đầy đủ.
- [ ] Có phương án rollback tương thích persisted state và message đang tồn đọng.
- [ ] Ghi quyết định kiến trúc và điều kiện cần đánh giá lại nếu workload thay đổi.

**Kết luận kỹ thuật:** Với yêu cầu restart nghiêm ngặt, cách chọn thường bắt đầu bằng **single-threaded chunk step** làm chuẩn correctness. Nếu cần tăng tốc, ưu tiên **parallel steps** cho những flow độc lập hoặc **partitioning** cho dataset có thể chia ổn định; mở rộng từ local partitioning sang remote partitioning khi một node không đủ tài nguyên. **Multi-threaded step** và **remote chunking** vẫn có chỗ đứng, nhưng cần chứng minh thêm về thứ tự, trạng thái, idempotency và các failure window. Không có lựa chọn đúng cho mọi workload: kiến trúc được chọn phải vượt qua phép thử **không mất dữ liệu, không tạo side effect trùng, khôi phục trong SLA và vận hành được khi sự cố thật xảy ra**.

### Tài liệu tham khảo

- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): JobInstance, JobExecution, parameters và điều khiển thực thi.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk, transaction và checkpoint.
- [Spring Batch Reference — Restarting a Job](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): trạng thái và cơ chế restart.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning, remote chunking.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata và transaction của job execution.
