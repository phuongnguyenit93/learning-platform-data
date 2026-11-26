# Single-process và multi-process trong Spring Batch

## Mục tiêu bài học

Khi khối lượng dữ liệu tăng, quyết định quan trọng không chỉ là tăng số luồng xử lý mà còn là **một job sẽ thực thi trong một tiến trình hay được phối hợp qua nhiều tiến trình**. Hai cách triển khai này có giới hạn tài nguyên, cách chia việc, cơ chế phục hồi và chi phí vận hành rất khác nhau.

Sau bài học, bạn có thể:

- Phân biệt thread, process, JVM, máy chủ và worker trong ngữ cảnh Spring Batch.
- Nhận diện các phương án single-process: xử lý tuần tự, multi-threaded step, parallel steps và local partitioning.
- Giải thích cách remote chunking và remote partitioning phối hợp nhiều tiến trình.
- Chọn mô hình phù hợp dựa trên bottleneck thực tế, khả năng chia dữ liệu, tính an toàn luồng và yêu cầu restart.
- Thiết kế các phép đo, giới hạn tài nguyên và cơ chế tránh ghi trùng trước khi mở rộng quy mô.

## 1. Xác định ranh giới: thread, process và máy chủ

**Single-process** nghĩa là các thành phần thực thi của một workload batch chạy trong **một tiến trình hệ điều hành**, thường là một JVM chứa ứng dụng Spring Batch. JVM ấy có thể dùng một luồng hoặc nhiều luồng, nhưng chúng cùng chia sẻ heap, classloader và vòng đời của tiến trình.

**Multi-process** nghĩa là workload được phân phối hoặc điều phối qua **nhiều tiến trình độc lập**. Trong Java, mỗi tiến trình thường là một JVM với heap, thread pool và vòng đời riêng. Các tiến trình có thể chạy trên cùng máy, trên nhiều máy hoặc trong các container/pod khác nhau. Chúng cần cơ chế phối hợp công việc, trao đổi trạng thái và xử lý lỗi giữa các tiến trình.

Ba khái niệm thường bị nhầm lẫn:

| Trường hợp | Có nhiều thread? | Có nhiều process? | Ý nghĩa đối với Spring Batch |
| --- | --- | --- | --- |
| Một step tuần tự trong một JVM | Không nhất thiết | Không | Đường cơ sở đơn giản nhất |
| Một multi-threaded step với 8 thread trong một JVM | Có | Không | Vẫn là single-process |
| Hai flow chạy đồng thời trong cùng JVM | Có | Không | Parallel steps vẫn là single-process |
| Một manager JVM và bốn worker JVM | Có thể | Có | Multi-process có điều phối |
| Bốn JVM tự khởi chạy bốn job độc lập | Có thể | Có | Nhiều process, nhưng **chưa chắc** là một job được phân phối |

**Lưu ý về thuật ngữ:** “Nhiều instance ứng dụng” và “một job phân tán” không đồng nghĩa. Nếu bốn instance cùng khởi chạy một job với cùng bộ *identifying JobParameters*, chúng không tự động chia nhau 25% dữ liệu. Spring Batch dùng định danh JobInstance và metadata JobRepository để quản lý lần chạy; phân chia công việc phải do kiến trúc job thiết kế, chẳng hạn thông qua partitioning.

### Những thành phần liên quan

- **Job**: đơn vị nghiệp vụ batch, gồm một hoặc nhiều step.
- **Step**: đơn vị xử lý và checkpoint; với chunk-oriented step, công việc thường gồm read → process → write theo từng chunk.
- **JobRepository**: lưu metadata như JobInstance, JobExecution, StepExecution, ExecutionContext để theo dõi và hỗ trợ restart.
- **TaskExecutor**: thực thi công việc trên các thread; tự nó không biến hệ thống thành multi-process.
- **Manager**: thành phần chia việc hoặc gửi chunk/partition.
- **Worker**: thành phần thực thi phần việc được giao; tùy kiến trúc có thể là thread nội bộ hoặc một JVM riêng.

## 2. Single-process: khai thác tài nguyên trong một JVM

Một tiến trình có thể mở rộng từ xử lý tuần tự lên nhiều dạng song song mà không cần điều phối giữa các JVM.

### 2.1. Xử lý tuần tự

Với step chunk-oriented thông thường, một thread đọc, xử lý và ghi các item theo chunk. Cách này dễ hiểu, dễ xác định thứ tự xử lý và thường dễ chẩn đoán hơn. Đây là **baseline bắt buộc có số đo** trước khi tối ưu.

Ví dụ: đọc 2 triệu giao dịch từ bảng nguồn, chuẩn hóa dữ liệu rồi ghi kết quả. Hãy ghi lại tổng thời gian, item/giây, thời gian query và thời gian ghi theo chunk trước khi thêm song song.

Một job chậm không nhất thiết thiếu CPU. Nguyên nhân có thể là query không có index phù hợp, commit quá thường xuyên, gọi API bị giới hạn tốc độ hoặc một bảng đích bị tranh chấp khóa.

### 2.2. Multi-threaded step

Với multi-threaded step, nhiều thread trong cùng JVM xử lý các chunk của **một step**. Mục tiêu là tăng số chunk đang được thực thi đồng thời, thích hợp khi công việc có khả năng chạy song song và các thành phần truy cập dữ liệu hỗ trợ concurrency.

~~~mermaid
flowchart TB
    J[Spring Batch Job - một JVM] --> S[Multi-threaded Step]
    S --> C1[Thread 1: chunk A]
    S --> C2[Thread 2: chunk B]
    S --> C3[Thread 3: chunk C]
    C1 --> D[(Nguồn / đích dữ liệu)]
    C2 --> D
    C3 --> D
~~~

Ví dụ cấu hình minh họa theo kiểu API thông dụng của Spring Batch 5.x:

~~~java
@Bean
public TaskExecutor importExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("import-");
    executor.initialize();
    return executor;
}

@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> safeReader,
        ItemProcessor<InputRow, OutputRow> statelessProcessor,
        ItemWriter<OutputRow> safeWriter,
        @Qualifier("importExecutor") TaskExecutor importExecutor) {

    return new StepBuilder("importStep", jobRepository)
            .<InputRow, OutputRow>chunk(200, transactionManager)
            .reader(safeReader)
            .processor(statelessProcessor)
            .writer(safeWriter)
            .taskExecutor(importExecutor)
            .build();
}
~~~

**Giả định quan trọng:** InputRow/OutputRow là các DTO của ứng dụng; các bean có tên safeReader/safeWriter **phải thực sự được kiểm chứng thread-safe**. Tên bean không tạo ra thread safety. Ví dụ chỉ minh họa cách gắn TaskExecutor vào step; cách cấu hình và giới hạn concurrency cần đối chiếu với phiên bản Spring Batch đang sử dụng.

Các rủi ro cần xử lý:

1. **Reader có state chia sẻ:** con trỏ file, cursor, số dòng hoặc biến đếm mutable có thể khiến nhiều thread đọc sai hoặc bỏ sót item. Nhiều reader không mặc định thread-safe.
2. **Processor/Writer có state chia sẻ:** cache mutable, bộ đếm, buffer và object không an toàn luồng có thể làm dữ liệu ghi sai. Processor thuần hàm và writer kiểm soát concurrency thường dễ mở rộng hơn.
3. **Thứ tự hoàn tất chunk:** các chunk có thể commit không theo thứ tự đọc; không dựa vào thứ tự ghi nếu nghiệp vụ yêu cầu thứ tự tuyệt đối.
4. **Restart:** đồng bộ hóa thao tác read không tự động bảo đảm checkpoint/restart chính xác khi các chunk hoàn tất lệch thứ tự. Phải thử tình huống dừng giữa chừng và chạy lại.
5. **Transaction và connection:** mỗi chunk đang thực thi cần tài nguyên giao dịch phù hợp. Thread pool lớn nhưng connection pool nhỏ chỉ tạo hàng chờ; quá nhiều kết nối còn có thể làm DB chậm hơn.

Có thể dùng các wrapper đồng bộ hóa reader trong những trường hợp phù hợp, nhưng điều này có thể làm bước đọc trở thành nút thắt và không giải quyết mọi vấn đề về restart. Nếu cần bảo đảm ranh giới dữ liệu rõ ràng, **partitioning theo khoảng khóa** thường dễ suy luận hơn việc chia sẻ một reader có state.

### 2.3. Parallel steps

Nếu job có các nhánh **độc lập về dữ liệu và thứ tự phụ thuộc**, có thể chạy nhiều flow/step song song trong cùng JVM. Ví dụ: một nhánh tổng hợp dữ liệu bán hàng, một nhánh tổng hợp tồn kho; bước kết quả chỉ chạy khi cả hai nhánh bắt buộc đã hoàn tất.

Parallel steps hữu ích khi các nhánh thực sự độc lập. Không nên chạy song song hai step cùng cập nhật một tập bản ghi nếu chưa có chiến lược khóa và nhất quán dữ liệu. Mỗi step vẫn cần metadata và quy tắc restart của riêng nó.

### 2.4. Local partitioning

Trong **local partitioning**, manager chia một step thành các partition có ExecutionContext riêng, rồi giao cho các worker step chạy trên những thread **trong cùng một JVM**. Mỗi partition có thể dùng reader và writer riêng, ví dụ một partition đọc các đơn hàng có ID trong khoảng [1, 250000), partition khác đọc [250000, 500000).

So với multi-threaded step chia sẻ reader, cách chia bằng partition thường tạo **ranh giới sở hữu dữ liệu** rõ hơn. Tuy vậy, tất cả partition vẫn dùng chung CPU, RAM, tiến trình và giới hạn tài nguyên máy chủ.

## 3. Multi-process: phân phối công việc qua nhiều JVM

Multi-process phù hợp khi một JVM không còn đủ tài nguyên hoặc muốn tách các worker để scale, cô lập lỗi và triển khai độc lập. Chi phí đổi lại là mạng, serialization, messaging, metadata và vận hành nhiều tiến trình.

Có hai mô hình phân tán thường gặp trong hệ sinh thái Spring Batch: **remote chunking** và **remote partitioning**. Chúng khác nhau ở chỗ dữ liệu được chia **sau khi đọc** hay các worker **tự đọc phần dữ liệu của mình**.

### 3.1. Remote chunking: manager đọc, worker xử lý và ghi

Trong remote chunking, tiến trình manager thực hiện việc đọc và hình thành chunk, rồi gửi các item/chunk qua middleware nhắn tin đến worker. Worker nhận chunk, thực hiện xử lý và ghi, sau đó phản hồi kết quả để manager theo dõi tiến độ.

~~~mermaid
flowchart LR
    D[(Nguồn)] --> M[Manager JVM<br/>read + tạo chunk]
    M --> Q[[Message broker]]
    Q --> W1[Worker JVM 1<br/>process + write]
    Q --> W2[Worker JVM 2<br/>process + write]
    Q --> W3[Worker JVM 3<br/>process + write]
    W1 --> T[(Đích)]
    W2 --> T
    W3 --> T
    W1 -. phản hồi .-> M
    W2 -. phản hồi .-> M
    W3 -. phản hồi .-> M
~~~

Đặc điểm chính:

- **Ưu điểm:** tách phần xử lý/ghi nặng khỏi manager; có thể tăng số worker khi phần process/write là nút thắt.
- **Giới hạn:** manager vẫn phải đọc toàn bộ item; tốc độ đọc và khả năng gửi message của manager có thể trở thành trần throughput.
- **Chi phí truyền dữ liệu:** dữ liệu item đi qua broker, cần serialization, quản lý kích thước message, dung lượng hàng đợi, độ trễ và phản hồi.
- **Độ tin cậy:** phải xử lý message gửi lại, worker chết sau khi ghi nhưng trước khi phản hồi, message hết hạn hoặc broker bị gián đoạn. Không mặc nhiên coi giao nhận message là “exactly once”.

Ví dụ phù hợp: đọc hóa đơn từ một nguồn đã tối ưu, mỗi hóa đơn cần tính toán CPU nặng và ghi kết quả độc lập; số lượng item vừa phải về kích thước nên chuyển qua broker không quá tốn kém.

Ví dụ kém phù hợp: đọc hàng trăm triệu item lớn trong khi chính bước đọc DB mới là bottleneck. Thêm worker sẽ khó cải thiện vì manager vẫn phải quét và gửi toàn bộ dữ liệu.

### 3.2. Remote partitioning: manager chia phạm vi, worker tự đọc

Trong remote partitioning, manager lập các partition và gửi **thông tin mô tả phần việc** (như khoảng ID, mã vùng, ngày dữ liệu) tới worker JVM. Mỗi worker thực thi step với reader/processor/writer và transaction **của chính nó** trên phần dữ liệu được giao.

~~~mermaid
flowchart TB
    M[Manager JVM<br/>Partitioner] --> Q[[Điều phối partition]]
    Q --> W1[Worker JVM 1<br/>ID 1..250k]
    Q --> W2[Worker JVM 2<br/>ID 250k..500k]
    Q --> W3[Worker JVM 3<br/>ID 500k..750k]
    W1 --> D[(Nguồn / đích dữ liệu)]
    W2 --> D
    W3 --> D
    R[(JobRepository chung<br/>metadata chạy)] --- M
    R --- W1
    R --- W2
    R --- W3
~~~

Với dữ liệu dạng khóa số, một partition có thể nhận ngữ cảnh:

~~~yaml
partitionId: orders-01
minIdInclusive: 1
maxIdExclusive: 250001
~~~

Reader của partition đó sử dụng điều kiện minh họa:

~~~sql
SELECT id, amount, customer_id
FROM orders
WHERE id >= :minIdInclusive
  AND id < :maxIdExclusive
ORDER BY id;
~~~

Khoảng **bao gồm đầu, loại trừ cuối** giúp tránh chồng lấn tại ranh giới. Các partition phải bao phủ đúng tập dữ liệu cần xử lý; chọn ranh giới theo ID, ngày, tenant hoặc shard key tùy tính chất dữ liệu. Với ID có nhiều khoảng trống, số dòng mỗi partition có thể rất lệch nhau.

Đặc điểm chính:

- **Ưu điểm:** worker tự đọc từ nguồn, nên manager không phải chuyển toàn bộ item qua mạng; phù hợp dữ liệu lớn, chia được theo khóa ổn định.
- **Đổi lại:** mỗi worker mở kết nối tới nguồn/đích; tổng tải DB có thể tăng mạnh. Phải kiểm soát tổng kết nối, scan, lock và băng thông.
- **Restart và metadata:** partition/StepExecution cần định danh ổn định và metadata dùng chung, thường thông qua JobRepository bền vững mà manager và worker liên quan có thể truy cập. Cần cấu hình đúng giao thức điều phối, timeout và xử lý worker mất kết nối.
- **Cân bằng tải:** số partition có thể lớn hơn số worker để giảm hiện tượng một worker nhận phần dữ liệu quá nặng. Tuy nhiên quá nhiều partition nhỏ làm tăng overhead quản lý.

Ví dụ phù hợp: bảng có 40 triệu giao dịch với khóa ID và index phù hợp, có thể chia thành các khoảng độc lập để các worker đọc, tính toán và ghi. Mỗi worker cam kết chỉ xử lý phần khóa được giao.

**Điểm cần phân biệt:** remote partitioning phân phối **phần việc và ranh giới đọc dữ liệu**; remote chunking phân phối **các item/chunk đã đọc**. Đây là khác biệt quyết định khi đánh giá tải trên manager và băng thông messaging.

### 3.3. Nhiều tiến trình chạy job độc lập

Một lựa chọn khác là nhiều scheduler hoặc instance ứng dụng chạy **các JobInstance khác nhau**, chẳng hạn mỗi tenant hoặc mỗi ngày nghiệp vụ dùng JobParameters riêng. Cách này hữu ích khi các workload độc lập và không cần manager partition.

Tuy nhiên phải thiết kế chống chạy trùng: cùng JobParameters không phải là cơ chế chia việc, còn JobParameters khác nhau không tự đảm bảo các truy vấn nguồn không chồng lấn. Khi nhiều job cùng ghi một đích, cần ràng buộc khóa và idempotency ở tầng dữ liệu.

## 4. So sánh single-process và multi-process

| Tiêu chí | Single-process | Multi-process |
| --- | --- | --- |
| Đơn vị triển khai | Một JVM thực thi workload | Nhiều JVM, có thể trên nhiều máy/pod |
| Chia sẻ bộ nhớ | Các thread dùng chung heap | Heap tách biệt, trao đổi qua DB/messaging |
| Mở rộng tài nguyên | Giới hạn CPU/RAM của một tiến trình và host | Có thể tăng worker trên các host khác nhau |
| Chi phí điều phối | Thấp hơn; chủ yếu thread pool và step/partition nội bộ | Cao hơn; mạng, message, worker lifecycle, metadata |
| Rủi ro dữ liệu | State dùng chung và thread safety | Trùng lặp giao việc, chuyển message, phân vùng chồng lấn |
| Sự cố worker | Một lỗi nghiêm trọng của JVM có thể dừng toàn job | Worker có thể chết riêng; cần timeout/retry/reassign |
| Quan sát hệ thống | Log và metric tập trung hơn | Cần correlation ID và metric giữa các JVM |
| Restart | Cần checkpoint đúng trong một tiến trình | Cần thêm định danh partition/message và trạng thái đồng bộ |
| Trường hợp khởi đầu | Dữ liệu vừa, tài nguyên máy còn dư, nghiệp vụ đơn giản | Khối lượng lớn, chia việc rõ, một JVM thực sự là giới hạn |

**Không có quy tắc “multi-process luôn nhanh hơn”.** Nếu DB hoặc API đích đã bão hòa, nhân số worker có thể tăng lock, timeout, retry và làm throughput giảm. Ngay cả khi multi-process giúp tách failure domain, một JobExecution phân tán vẫn có thể bị ảnh hưởng nếu manager hoặc metadata store gặp sự cố.

## 5. Chọn kiến trúc từ nút thắt đo được

Trước khi chọn mô hình, hãy ghi lại bốn nhóm số liệu của baseline:

1. **Throughput và thời gian:** item/giây, thời gian xử lý tổng, thời gian từng step, p95/p99 thời gian chunk (nếu đo được).
2. **Tài nguyên ứng dụng:** CPU, heap, GC pause, số thread hoạt động, số chunk đang chạy, thời gian chờ connection.
3. **Nguồn/đích:** thời gian query, số hàng scan, tốc độ I/O, lock wait, connection pool, giới hạn rate của dịch vụ ngoài.
4. **Điều phối (nếu phân tán):** broker lag, độ trễ chuyển message, số worker bận/rảnh, số partition tồn đọng, retry và lỗi timeout.

~~~mermaid
flowchart TD
    A[Đo baseline đơn luồng] --> B{Bottleneck chính ở đâu?}
    B -->|CPU của một JVM| C{Có chia việc độc lập?}
    C -->|Có, tài nguyên host còn| D[Thử parallel steps / local partitioning]
    C -->|Có, host đã giới hạn| E[Thử remote partitioning hoặc remote chunking]
    C -->|Không| F[Thiết kế lại logic / ranh giới dữ liệu]
    B -->|Reader hoặc query DB| G[Tối ưu query, index, phân vùng đọc]
    G --> H{Nguồn chịu được nhiều reader?}
    H -->|Có| I[Thử partitioning]
    H -->|Không| J[Giữ concurrency thấp, giảm tải nguồn]
    B -->|Writer / API / DB đích| K[Tối ưu batch write, khóa, quota, backpressure]
    D --> L[Đo lại throughput + error + restart]
    E --> L
    I --> L
    K --> L
~~~

Một lộ trình thực tế:

- **Bước 1:** chạy single-process tuần tự với dữ liệu đại diện, thu metric và kiểm tra kết quả.
- **Bước 2:** tối ưu thuật toán, query, batch write, chunk size và index trước khi tăng concurrency.
- **Bước 3:** nếu các phần việc độc lập, thử số thread/partition nhỏ (ví dụ 2 rồi 4), quan sát throughput cùng tải DB.
- **Bước 4:** nếu host/JVM là giới hạn và các phần việc phân chia tốt, chuyển sang remote chunking hoặc remote partitioning tùy nơi đọc dữ liệu.
- **Bước 5:** tăng worker từng nấc, đo tốc độ tăng thật, kiểm tra tính đúng khi kill worker, mất kết nối và restart.

Ví dụ phép đo giả định với **2 triệu item**, chỉ để minh họa cách ra quyết định:

| Cấu hình | Throughput đo được | Thời gian xấp xỉ | Diễn giải |
| --- | ---: | ---: | --- |
| Một JVM, một luồng | 5.000 item/s | 400 giây | Baseline |
| Một JVM, 4 thread | 11.000 item/s | 182 giây | Có lợi, nhưng không tăng 4 lần |
| Bốn worker JVM | 12.000 item/s | 167 giây | Cải thiện nhỏ so với 4 thread |
| Tám worker JVM | 10.500 item/s | 190 giây | Có thể đã tạo tranh chấp DB |

Dữ liệu trên là **giả định**, không phải benchmark của Spring Batch. Từ bảng này, tăng từ 4 lên 8 worker không đáng làm nếu không xử lý bottleneck DB. Có thể tính speedup = throughput mới / throughput baseline, và hiệu suất mở rộng xấp xỉ = speedup / số đơn vị xử lý song song; đây là thước đo tham khảo, không phải mục tiêu duy nhất.

## 6. Tính đúng dữ liệu và restart khi chạy song song

Scaling không chỉ là xử lý nhanh hơn. Với batch dữ liệu lớn, một lỗi ghi trùng hoặc bỏ sót có thể nghiêm trọng hơn vài phút thời gian chạy.

### 6.1. Phân hoạch đủ và không trùng

Khi partition theo khóa, bảo đảm:

- Mỗi item thuộc **đúng một** partition trong phạm vi dữ liệu của lần chạy.
- Không có khoảng trống hoặc ranh giới trùng lặp.
- Tập dữ liệu đọc được xác định rõ: dữ liệu có thể thay đổi khi job đang chạy hay dùng một mốc snapshot/high-watermark?
- Partition key ổn định trong suốt vòng đời xử lý; nếu record đổi partition giữa hai lần chạy, cần chính sách rõ ràng.

Với bảng đang phát sinh đơn hàng liên tục, có thể chốt một mốc thời gian hoặc ID lớn nhất khi job bắt đầu, rồi chỉ đọc dữ liệu trong phạm vi đó. Mốc này phải được lưu cùng ngữ cảnh JobExecution/ExecutionContext thích hợp để restart không âm thầm thay đổi tập đầu vào.

### 6.2. Thread safety là trách nhiệm ở cấp component

Không mặc định rằng mọi ItemReader, ItemProcessor hay ItemWriter đều thread-safe. Hãy kiểm tra trạng thái mutable, connection/cursor, buffer, cache, ItemStream và tính tương thích restart. Với local partitioning, tạo reader theo partition và truyền ngữ cảnh riêng giúp giảm chia sẻ state; với multi-threaded step, mọi component dùng chung cần được xem xét cẩn thận.

### 6.3. Transaction, retry và idempotency

**Chunk commit** thường là ranh giới giao dịch ghi dữ liệu. Nếu worker chết sau khi commit DB nhưng trước khi gửi xác nhận qua broker, manager có thể giao lại phần việc tùy cơ chế retry/ack. Vì vậy, “message được xử lý một lần” không đồng nghĩa “tác dụng nghiệp vụ xảy ra đúng một lần”.

Các biện pháp quan trọng:

- Dùng **business key duy nhất** ở đích, với upsert hoặc kiểm tra trùng được DB thực thi atomically.
- Với side effect qua API, truyền idempotency key nếu dịch vụ hỗ trợ.
- Phân loại lỗi có thể retry (mạng tạm thời, timeout) và lỗi dữ liệu không nên retry vô hạn.
- Đảm bảo logic writer có thể chạy lại an toàn sau partial failure.
- Lưu metadata/checkpoint bền vững, theo dõi retry, skip và trạng thái partition bị kẹt.

Ví dụ PostgreSQL, ghi cùng một transaction_id nhiều lần vẫn cho một bản ghi logic:

~~~sql
INSERT INTO payment_summary (transaction_id, total_amount)
VALUES (:transactionId, :totalAmount)
ON CONFLICT (transaction_id)
DO UPDATE SET total_amount = EXCLUDED.total_amount;
~~~

Ví dụ này giả định transaction_id có ràng buộc UNIQUE/PRIMARY KEY và nghiệp vụ cho phép cập nhật theo cùng khóa. Với nghiệp vụ cộng dồn, gửi email hoặc gọi hệ thống thanh toán, cần thiết kế idempotency riêng; phép UPDATE không tự động đủ an toàn.

### 6.4. Metadata JobRepository và cạnh tranh tài nguyên

Khi nhiều JVM cùng tham gia một job, cơ chế metadata và giao dịch cần được cấu hình cho kiến trúc triển khai thực tế. Remote partitioning thường cần các tiến trình liên quan truy cập JobRepository dùng chung để thống nhất trạng thái StepExecution. Không dùng metadata chỉ lưu trong bộ nhớ để kỳ vọng restart tin cậy qua nhiều tiến trình.

Tổng số kết nối tiềm năng cần kiểm soát trên **toàn bộ** worker. Ví dụ 6 worker, mỗi worker có pool tối đa 10 kết nối, có thể tạo đến 60 kết nối từ ứng dụng, chưa kể manager và ứng dụng khác. Kích thước pool và số luồng thực tế phải được chọn theo giới hạn DB, tải query và số transaction đồng thời.

### 6.5. Cô lập lỗi và khởi động lại

Hãy kiểm thử ít nhất các tình huống:

| Sự cố | Cần quan sát | Điều kiện kết quả đúng |
| --- | --- | --- |
| Kill một worker khi đang xử lý | Chunk/partition nào được đánh dấu lỗi và được thử lại | Không mất item, không tạo side effect trùng |
| Manager bị dừng | Metadata có đủ để tiếp tục hay cần chạy lại | Resume theo chiến lược thiết kế |
| Broker mất kết nối | Message tồn đọng, retry, phản hồi quá hạn | Không mất dấu công việc đã nhận |
| DB đích chậm hoặc bị khóa | Connection wait, timeout, retry storm | Có backpressure và không làm quá tải DB |
| Dữ liệu nguồn thay đổi | Partition key, snapshot, high-watermark | Ranh giới dữ liệu không thay đổi ngoài ý muốn |

Không tự động giả định job nào cũng có thể restart từ điểm dừng chỉ nhờ bật một cấu hình. Khả năng restart phụ thuộc reader, writer, ExecutionContext, transaction, định danh partition và nghiệp vụ idempotent.

## 7. Thiết kế vận hành cho multi-process

Mở rộng qua nhiều JVM cần thêm quy ước vận hành rõ ràng:

**Định danh và truy vết.** Mỗi log/metric nên có job name, JobExecution ID, StepExecution ID và partition ID hoặc chunk correlation ID. Điều này giúp nối sự kiện giữa manager, broker và worker mà không phụ thuộc vào hostname.

**Backpressure.** Không để manager gửi nhanh vô hạn khi worker hoặc DB đích chậm. Giới hạn inflight work, queue depth, số transaction đồng thời và cơ chế xử lý retry. Nếu hàng đợi tăng liên tục, tăng worker chỉ hữu ích khi phần tài nguyên phía sau còn dung lượng.

**Triển khai tương thích.** Manager và worker phải thống nhất format message, phiên bản DTO, logic partition và schema dữ liệu. Triển khai lệch phiên bản có thể làm worker không deserialize được message hoặc xử lý sai điều kiện phân vùng.

**Giám sát tồn đọng.** Theo dõi partition chờ quá lâu, worker không phản hồi, chunk retry nhiều lần, số item read/process/write/skip, dead-letter queue nếu kiến trúc messaging sử dụng và thời gian không có tiến độ.

**Chính sách retry và giới hạn lỗi.** Retry có giới hạn, exponential backoff khi thích hợp, phân biệt poison message với lỗi hạ tầng. Có cách chuyển việc lỗi sang trạng thái cần xử lý mà không tạo vòng lặp vô hạn.

**Cấp phát tài nguyên.** Ngoài CPU/RAM, tính tổng connection pool, disk throughput, network egress, quota broker và tải JobRepository. Scale out chỉ hiệu quả khi tài nguyên chia sẻ vẫn chịu được.

## 8. Tình huống thực tế: tổng hợp 40 triệu giao dịch

Một hệ thống cần đọc 40 triệu giao dịch, tính chỉ số gian lận và ghi kết quả vào bảng phân tích. Các bước ra quyết định có thể như sau.

**Giai đoạn A — Baseline:** chạy một JVM tuần tự, đo CPU chỉ 35% nhưng query nguồn chiếm 70% thời gian. Lúc này tăng số worker tính toán chưa giải quyết vấn đề cốt lõi. Ưu tiên tối ưu index và chiến lược đọc theo khóa.

**Giai đoạn B — Chia dữ liệu:** sau tối ưu, nguồn hỗ trợ nhiều truy vấn phạm vi ID độc lập. Chốt high-watermark, chia thành 32 partition, kiểm tra phân phối số record để tránh một partition quá lớn.

**Giai đoạn C — Thử local partitioning:** chạy 4 partition đồng thời trên một host. Nếu CPU đạt gần giới hạn và DB vẫn còn dung lượng, cân nhắc phân phối partition sang nhiều JVM.

**Giai đoạn D — Remote partitioning:** triển khai manager và 4 worker JVM, mỗi worker tự đọc một số khoảng ID, ghi đích bằng khóa nghiệp vụ duy nhất. Khởi chạy tải nhỏ rồi tăng dần theo metric DB/CPU.

**Giai đoạn E — Kiểm tra phục hồi:** chủ động dừng một worker ở giữa chunk, restart phần việc lỗi và so sánh tổng số khóa đầu vào với số khóa đầu ra hợp lệ. Chỉ mở rộng tiếp khi kết quả ổn định.

Nếu ở giai đoạn A, nguồn đọc vốn nhanh nhưng tính toán chỉ số gian lận tốn nhiều CPU và kích thước item nhỏ, **remote chunking** có thể phù hợp hơn vì manager đọc đủ nhanh rồi gửi item tới các worker xử lý.

Từ tình huống này, lựa chọn kiến trúc phụ thuộc vào nơi tiêu thụ thời gian, khả năng chia dữ liệu và tải mà hệ thống nguồn/đích chấp nhận được.

## 9. Các nhầm lẫn phổ biến

| Nhận định hoặc triệu chứng | Phân tích đúng |
| --- | --- |
| “Đã đặt TaskExecutor nên job là multi-process.” | TaskExecutor dùng thread; nếu vẫn trong một JVM thì là single-process. |
| “Tăng từ 4 lên 16 worker chắc chắn nhanh gấp bốn.” | Throughput bị giới hạn bởi DB, API, broker, network và phần công việc không song song. |
| “Bốn ứng dụng cùng chạy JobParameters giống nhau sẽ tự chia dữ liệu.” | Không có cơ chế chia tự động như vậy; cần partitioning hoặc các phạm vi job độc lập được xác định rõ. |
| “Dùng reader có khóa synchronized là đủ an toàn.” | Có thể hết data race khi read nhưng thứ tự commit, checkpoint và restart vẫn cần kiểm thử. |
| “Remote partitioning chỉ cần tăng số replica.” | Cần manager/worker, partition strategy, metadata, điều phối và định danh phần việc. |
| “Broker đã ack nên dữ liệu chắc chắn được ghi đúng một lần.” | Ack và commit DB có thể không atomic; thiết kế idempotency ở đích vẫn cần thiết. |
| “Số partition phải bằng số worker.” | Có thể có nhiều partition hơn worker để phân phối tải tốt hơn, nhưng phải cân bằng overhead. |
| “Multi-process giải quyết được nghẽn DB.” | Nhiều worker có thể làm nghẽn DB trầm trọng hơn nếu không tối ưu truy vấn và giới hạn cạnh tranh. |

## 10. Checklist chọn mô hình

Trước khi triển khai production, xác nhận rằng:

- [ ] Có baseline và bottleneck được đo bằng dữ liệu có kích thước đại diện.
- [ ] Đã xác định phần việc có thể chạy độc lập và cách tránh trùng/bỏ sót item.
- [ ] Reader, processor, writer và mọi state chia sẻ đã được đánh giá thread safety.
- [ ] Chunk size, concurrency và connection pool phù hợp với nguồn/đích.
- [ ] Đã chọn rõ remote chunking hay remote partitioning theo **ranh giới đọc dữ liệu**.
- [ ] JobRepository, ExecutionContext, transaction, retry/restart và idempotency được thiết kế cùng nhau.
- [ ] Có log/metric theo job, step, partition/chunk và worker.
- [ ] Đã thử kill worker, mất kết nối, retry, restart và đối soát dữ liệu đầu ra.
- [ ] Scale được kiểm chứng bằng throughput, độ đúng dữ liệu và chi phí vận hành, không chỉ số worker.

## 11. Câu hỏi tự kiểm tra

**1. Một Spring Batch step chạy 12 thread trong cùng một pod có phải multi-process không?**

Không. Nếu 12 thread thuộc một JVM thì đó là single-process có concurrency. Pod/container không thay đổi định nghĩa ranh giới tiến trình.

**2. Vì sao remote partitioning thường hợp với bảng rất lớn có thể chia theo ID?**

Manager chỉ chuyển thông tin về phạm vi xử lý; mỗi worker tự đọc những hàng thuộc phạm vi của mình. Không cần chuyển toàn bộ item qua broker như remote chunking. Đổi lại, DB phải đủ khả năng phục vụ nhiều reader.

**3. Khi tăng số worker từ 4 lên 8 mà throughput giảm, nên làm gì?**

Đo lại CPU, DB query/lock/connection, broker và thời gian chờ. Nếu DB bão hòa, hạ concurrency hoặc tối ưu nguồn/đích; thêm worker không xử lý được giới hạn tài nguyên chia sẻ.

**4. Vì sao cơ chế restart của Spring Batch chưa đủ để bảo đảm không ghi trùng?**

Restart giúp theo dõi và tiếp tục phần việc, nhưng các sự cố giữa commit dữ liệu và xác nhận điều phối có thể khiến một chunk/partition được xử lý lại. Writer cần idempotency và ràng buộc nghiệp vụ phù hợp.

**Ghi nhớ:** *Single-process* mở rộng bằng cách sử dụng tốt hơn tài nguyên trong một JVM; *multi-process* chia công việc và vận hành qua nhiều JVM. Trong Spring Batch, quyết định thực tế nên bắt đầu từ bottleneck, cách sở hữu dữ liệu của từng worker và khả năng retry/restart an toàn.
