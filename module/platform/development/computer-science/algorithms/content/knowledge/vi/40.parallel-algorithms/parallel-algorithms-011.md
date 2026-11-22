# Phân biệt mô hình bộ nhớ chung với mô hình phân tán

## 1. Câu hỏi cốt lõi của lập trình song song

Khi muốn giải một bài toán nhanh hơn bằng nhiều đơn vị tính toán, điều đầu tiên phải xác định không chỉ là “có bao nhiêu CPU” mà còn là **dữ liệu nằm ở đâu và các đơn vị tính toán trao đổi thông tin như thế nào**.

Có hai mô hình nền tảng:

1. **Bộ nhớ chung (shared-memory):** nhiều luồng hoặc đơn vị xử lý truy cập **cùng một không gian địa chỉ có thể chia sẻ**. Chúng có thể đọc cùng mảng và, nếu được phép, ghi vào cùng các vị trí. Trao đổi thông tin thông qua bộ nhớ cần các quy tắc đồng bộ.
2. **Bộ nhớ phân tán (distributed-memory):** mỗi tiến trình/worker có **không gian bộ nhớ riêng**. Dữ liệu của worker khác không tự xuất hiện qua một phép đọc con trỏ thông thường; các worker trao đổi bằng **thông điệp, giao thức truyền dữ liệu hoặc các primitive giao tiếp tập thể**.

Tên gọi mô tả **mô hình truy cập bộ nhớ và giao tiếp**, không mặc định rằng shared-memory chỉ chạy trên một CPU hoặc distributed-memory nhất thiết phải chạy ở hai trung tâm dữ liệu khác nhau.

Một ứng dụng có thể dùng **cả hai**: mỗi máy trong cluster có nhiều thread chung RAM, còn giữa các máy dùng mạng để trao đổi dữ liệu. Đây là thiết kế **hybrid parallelism**.

### Hai câu hỏi để nhận diện nhanh

- **Một worker có thể đọc trực tiếp dữ liệu ở vùng nhớ của worker khác bằng cùng object reference không?** Nếu có, nó thuộc mô hình shared-memory ở mức đó; nếu không, thường cần truyền dữ liệu hay một dịch vụ trung gian.
- **Một phép cập nhật của worker A có tự trở thành giá trị mà worker B có thể đọc qua cùng object không?** Với shared-memory, cần xét memory visibility và đồng bộ. Với distributed-memory, cần xét nội dung thông điệp, thứ tự nhận, replication và consistency.

**Mục tiêu bài học:** hiểu sự khác biệt về không gian địa chỉ, truyền thông, đồng bộ, hiệu năng, chịu lỗi, nhất quán, khả năng mở rộng; biết chọn mô hình và viết được ví dụ Java 17 minh họa cả hai cách tổ chức phép tính song song.

## 2. Shared-memory: cùng địa chỉ, nhiều đơn vị thực thi

Trong ứng dụng Java truyền thống, nhiều `Thread` bên trong **cùng một JVM** có thể giữ tham chiếu tới **cùng một `int[]`, `List` hoặc object**.

~~~text
                      ONE JVM / ONE ADDRESS SPACE
                 +----------------------------------+
Thread A --------|                                  |
                 |     shared int[] data            |
Thread B --------|     shared objects               |
                 |     locks / atomics / queues     |
Thread C --------|                                  |
                 +----------------------------------+
~~~

Ví dụ, ba thread cùng đọc mảng bất biến để tính tổng ba đoạn khác nhau. Không cần sao chép cả mảng cho mỗi thread. Nhưng nếu nhiều thread cùng sửa `counter`, ta phải xử lý **race conditions**.

### Các khái niệm cần phân biệt

- **Thread:** đơn vị thực thi; thread trong cùng process thường dùng chung không gian địa chỉ của process.
- **Process:** một không gian địa chỉ riêng do hệ điều hành quản lý; hai process không tự chia sẻ mọi object trong heap.
- **Core:** lõi xử lý vật lý hoặc logic, không đồng nghĩa với thread trong chương trình.
- **Cache:** dữ liệu có thể nằm trong cache của từng core; vẫn phải tuân theo quy tắc coherence và memory model tương ứng.
- **NUMA:** trên một máy nhiều socket, các core có thể nhìn thấy một không gian địa chỉ chung nhưng truy cập RAM cục bộ/xa có độ trễ khác nhau.

### Các mô hình quen thuộc

- Java threads và `ExecutorService` với object dùng chung.
- OpenMP cho các vòng lặp song song trong C/C++/Fortran.
- Các tác vụ cùng truy cập một bộ dữ liệu trong RAM của máy.
- Thuật toán dùng `AtomicLong`, `synchronized`, lock hay concurrent collections để điều phối cập nhật.

Việc có chung bộ nhớ là **khả năng**, không phải nghĩa vụ: cách thiết kế an toàn thường là giữ dữ liệu input **read-only** và để mỗi thread sinh kết quả cục bộ rồi hợp nhất.

## 3. Distributed-memory: không có object chung tự động

Trong mô hình phân tán, mỗi worker/process có vùng nhớ riêng:

~~~text
+------------------+        messages        +------------------+
| Process/Node A   | <--------------------> | Process/Node B   |
| private heap A   |      network / IPC     | private heap B   |
| local data A     |                        | local data B     |
+------------------+                        +------------------+
         ^                                            ^
         |                                            |
         +---------------- coordinator ---------------+
~~~

Nếu worker A có một `int[]`, worker B không thể lấy tham chiếu Java tới object ấy rồi tự đọc qua mạng. A phải **gửi một biểu diễn dữ liệu** hoặc B phải có một bản sao/partition tại nơi lưu trữ mà B truy cập được.

### Có thể cùng một máy vật lý không?

Có. Hai **process có address space riêng** trên cùng một máy vẫn có thể dùng IPC/message passing. Điều khác biệt trọng tâm là **không có một heap object tự động chung** như nhiều thread cùng JVM. Khi chạy trên nhiều máy, thông điệp thường đi qua mạng.

Các kỹ thuật như **shared memory segment, memory-mapped files, distributed shared memory** có thể cung cấp những giao diện chia sẻ đặc biệt. Chúng không xóa bỏ mọi khác biệt về đồng bộ, truyền thông và chịu lỗi; phải biết tầng abstraction đang sử dụng.

### Công cụ thường gặp

- MPI với `send`, `receive`, `broadcast`, `scatter`, `gather`, `reduce`.
- Cluster batch processing, map/shuffle/reduce.
- Microservices trao đổi thông điệp/RPC.
- Actor systems, queues, event streams.
- Dataflow engines chạy các worker trên nhiều process/máy.

**Không phải mọi message-passing program đều là distributed deployment.** Một hệ thống actor toàn bộ trong một JVM có thể giao tiếp bằng messages nhưng vẫn chia sẻ address space vật lý; phải phân biệt **kiểu lập trình** với **kiểu triển khai và fault domain**.

## 4. So sánh có hệ thống

| Tiêu chí | Shared-memory | Distributed-memory |
| --- | --- | --- |
| Không gian địa chỉ | Các thread có thể truy cập cùng object | Mỗi worker/process có vùng nhớ riêng |
| Trao đổi dữ liệu | Đọc/ghi bộ nhớ, lock, atomics | Message, RPC, network, collectives |
| Chia dữ liệu | Chia đoạn của một mảng chung | Partition/copy/shard tại từng worker |
| Chi phí giao tiếp | Cache miss, coherence, contention | Serialization, copying, network/IPC latency |
| Đồng bộ | Lock, barrier, atomic, happens-before | Protocol, messages, acknowledgments, barrier phân tán |
| Lỗi cạnh tranh thường gặp | Data race, lost update, deadlock | Lost/duplicated/late messages, retries, network partition |
| Đơn vị hỏng hóc | Thread lỗi có thể ảnh hưởng cả process | Worker/node/network có thể hỏng độc lập; cần recovery |
| Khả năng mở rộng | Giới hạn bởi RAM/cache/coherence của một domain | Có thể trải nhiều node, nhưng trả giá giao tiếp |
| Dữ liệu nhất quán | Governed by language/hardware memory model | Governed by replication, order, protocol/consistency |
| Debug | Interleaving, thread dumps, races | Distributed tracing, message IDs, clock/order, partial failure |
| Sử dụng điển hình | Vòng lặp trên mảng lớn vừa RAM, parallel reduction | Dữ liệu quá RAM một máy, cluster shuffle, distributed join |

### Không có mô hình nào luôn nhanh hơn

Một mảng 100.000 số nguyên trên một máy có thể xử lý rất nhanh bằng một thread. Mở nhiều thread hay chạy cluster cho bài quá nhỏ làm overhead tăng. Ngược lại, nếu dữ liệu quá lớn để chứa trên một máy hoặc cần chịu lỗi/đàn hồi theo node, distributed-memory có thể là lựa chọn phù hợp dù chi phí truyền thông lớn hơn.

### Hybrid thường gặp trong thực tế

~~~text
Node 1: 8 threads shared RAM   <--- network --->   Node 2: 8 threads shared RAM
Node 3: 8 threads shared RAM   <--- network --->   Node 4: 8 threads shared RAM
~~~

Mỗi node xử lý partition bằng multithreading; các node trao đổi partial results bằng messages. Không cần ép một bài toán lớn vào đúng một trong hai nhãn.

## 5. Chia việc: cùng mảng hay chuyển partition?

Xét bài toán **tính tổng n số nguyên**:

~~~text
sum = a[0] + a[1] + ... + a[n-1]
~~~

Đây là ví dụ **data parallelism**: các phần tử có thể được xử lý độc lập trước khi gộp partial sums.

### Shared-memory

Một thread tạo `int[] a`, chia thành p khoảng không giao nhau:

~~~text
Worker 0 reads a[0 ... k0-1]
Worker 1 reads a[k0 ... k1-1]
Worker 2 reads a[k1 ... k2-1]
...
~~~

Mỗi worker chỉ đọc mảng chung và trả một `long partialSum`. Coordinator cộng các partials khi worker đã hoàn thành.

~~~text
               shared int[] a
                  /   |   \
             task0  task1  task2
                \     |     /
                partial sums
                     |
                   reduce
~~~

**Không cần lock trên a** nếu mọi worker chỉ đọc và không ai sửa nó trong lúc chạy. Cần bảo đảm object được công bố cho thread đúng cách và coordinator chờ hoàn tất trước khi dùng kết quả.

### Distributed-memory

Coordinator phải **đưa partition đến worker** hoặc worker tự đọc partition tại kho dữ liệu:

~~~text
coordinator:
  chunk0 -> serialize -> message0 -> worker0
  chunk1 -> serialize -> message1 -> worker1
  chunk2 -> serialize -> message2 -> worker2

worker:
  decode local chunk -> local sum -> result message

coordinator:
  collect result messages by id -> reduce
~~~

Worker không cần biết toàn bộ mảng. Bù lại có phí encode/copy/transfer và cần quản lý message IDs, faults và retry.

### Phải so cùng phép tính

Hai phương pháp chỉ được xem là tương đương nếu dùng cùng dữ liệu, cùng phép toán tổng, không mất/nhân đôi partition và cùng quy định xử lý overflow. Chương trình minh họa dùng `int` làm phần tử và `long` cho tổng.

## 6. Race condition, data race và lost update ở bộ nhớ chung

Nếu nhiều thread **ghi cùng vị trí** mà không có cơ chế đồng bộ phù hợp, có thể xảy ra **data race** trong Java Memory Model. Kết quả phụ thuộc interleaving và không thể suy luận như một chương trình tuần tự đơn giản.

Ví dụ nguy hiểm:

~~~java
long counter = 0;

// Nhiều thread cùng chạy:
counter++;
~~~

`counter++` không phải một thao tác atomic duy nhất; nó gồm đọc giá trị, cộng và ghi lại. Hai thread có thể đọc cùng số cũ rồi cùng ghi một số mới, làm mất một lần tăng.

### Phân biệt hai thuật ngữ

- **Race condition:** kết quả hoặc hành vi phụ thuộc thứ tự/timing tương tác giữa các tác vụ; không phải race condition nào cũng đúng định nghĩa data race.
- **Data race:** có các truy cập bộ nhớ xung đột không được sắp thứ tự bởi quan hệ happens-before theo memory model liên quan; ít nhất một truy cập là ghi.

### Cách tránh

- Phân vùng output, mỗi thread sở hữu ô/đoạn riêng.
- Tính partial result cục bộ, gộp sau khi hoàn thành.
- Dùng `synchronized`/lock cho critical section.
- Dùng `AtomicLong`, `AtomicInteger` hoặc `LongAdder` khi phù hợp.
- Sử dụng cấu trúc concurrent có hợp đồng rõ.
- Hạn chế shared mutable state.

### Vì sao volatile chưa đủ?

~~~java
volatile int count;

// Van sai neu nhieu thread cung:
count++;
~~~

`volatile` cung cấp những bảo đảm visibility/order cho truy cập volatile, nhưng **không biến read–modify–write thành nguyên tử**. Khi muốn cộng đồng thời, cần một primitive atomic hoặc khóa.

### Deadlock khác race

Nếu thread A giữ khóa X chờ Y còn thread B giữ Y chờ X, cả hai có thể chờ vô hạn. Đây là **deadlock**, không đơn giản là lost update. Giảm số khóa, chốt thứ tự lock nhất quán, tránh giữ khóa trong I/O chậm là các cách thiết kế quan trọng.

## 7. Visibility, happens-before và bộ nhớ Java

Java Memory Model (JMM) mô tả khi nào một luồng được bảo đảm quan sát các hành động của luồng khác, không chỉ việc hai luồng “đã chạy đến đâu”.

Các cơ chế thường tạo quan hệ **happens-before**:

- Chương trình thực hiện theo thứ tự trong cùng thread.
- Các cặp lock/unlock được sử dụng đúng.
- Các thao tác volatile theo quy tắc JMM.
- Thread được start sau khi các giá trị đầu vào đã chuẩn bị phù hợp.
- Tương tác qua các concurrency utilities có các bảo đảm memory-consistency được tài liệu hóa.

Ví dụ với `ExecutorService` và `Future`:

~~~java
int[] data = createInput();

Future<Long> f = pool.submit(() -> {
    return sumRange(data, 0, data.length);
});

long answer = f.get();
~~~

Các hành động chuẩn bị input trước khi submit và những hành động của task trước khi hoàn thành được quan sát đúng qua hợp đồng concurrency tương ứng. `Future.get()` còn là bước **đợi kết quả**, nên coordinator không dùng partial sum quá sớm.

### Chú ý dữ liệu bị sửa trong lúc chạy

Nếu main thread cập nhật `data[i]` trong khi worker đang đọc, việc đã submit task **không tự làm toàn bộ dãy giá trị thành snapshot bất biến**. Muốn kết quả từ một phiên bản nhất quán, cần đóng băng input, copy/snapshot hoặc một cơ chế versioning/locking thích hợp.

### Cache coherence không thay thế synchronization

Phần cứng có thể bảo đảm coherence của từng cache line theo quy tắc của kiến trúc, nhưng chương trình vẫn phải tuân theo JMM. Không được nói rằng “các core chung RAM thì lúc nào cũng thấy mọi ghi ngay lập tức”.

### False sharing

Hai thread cập nhật **hai biến khác nhau** nhưng cùng cache line có thể làm line di chuyển liên tục giữa core, giảm performance dù không có data race trên cùng biến. Padding/alignment và partition theo vùng có thể hữu ích, nhưng cần benchmark, tránh tối ưu mù quáng.

## 8. Truyền thông phân tán: message là một phần của thuật toán

Trong distributed-memory, trao đổi dữ liệu phải **được biểu diễn rõ ràng**:

~~~text
send(destination, message)
receive(source, message)
~~~

Một message thường cần:

- Loại thao tác (command/type).
- Task/request ID để đối chiếu kết quả.
- Phiên bản schema.
- Partition key hoặc phạm vi dữ liệu.
- Payload hoặc đường dẫn/vị trí của dữ liệu.
- Thông tin kiểm tra toàn vẹn khi cần.
- Retry/idempotency token hoặc sequence number nếu giao thức yêu cầu.

### Serialization và bản sao dữ liệu

Một object Java không thể được “gửi nguyên con trỏ RAM” sang máy khác. Phải có biểu diễn truyền được: bytes, Protobuf, Avro, JSON, Arrow, v.v. Phía nhận phải hiểu **cùng schema, encoding và thứ tự byte**.

Ví dụ bài này dùng:

~~~text
int32 count (4 bytes, big-endian)
int32 value[0]
int32 value[1]
...
int32 value[count-1]
~~~

Với c phần tử, application payload có:

~~~text
4 + 4*c bytes
~~~

Đây chưa phải tổng byte trên dây mạng; transport framing, headers, TLS, retries và response messages có overhead khác.

### Không chỉ băng thông

Ngay cả khi message nhỏ, một round trip có thể mất một độ trễ đáng kể. Nhiều message nhỏ phát sinh chi phí latency và scheduling; message lớn làm tăng copy, memory peak và thời gian truyền.

Bài toán cần chọn **granularity** phù hợp: không phải cứ phân nhỏ thành một message cho mỗi số nguyên là tốt.

## 9. Ordering, lỗi một phần và retry

Trong shared-memory, worker cùng process thường có chung fate của JVM: một lỗi nghiêm trọng có thể ảnh hưởng cả process. Trong distributed-memory, một worker/máy/đường truyền có thể gặp sự cố **trong khi các worker khác vẫn chạy**.

### Các tình huống phải xử lý

- Worker bị crash trước khi gửi kết quả.
- Message đến trễ, mất, trùng hoặc bị từ chối.
- Coordinator timeout nhưng worker đã xử lý thành công.
- Worker thực thi lại task sau retry.
- Hai phiên bản worker hiểu schema khác nhau.
- Network partition khiến một số node không liên lạc được.
- Một node chậm hơn các node còn lại (straggler).

### Vì sao timeout không chứng minh thất bại?

Nếu không nhận được phản hồi trong một khoảng, có thể worker chưa nhận request, đang xử lý, đã hoàn thành nhưng response thất lạc, hoặc network bị phân vùng. Chỉ nhìn timeout **không xác định** công việc đã được áp dụng hay chưa.

Nếu tự động retry một tác vụ **có side effect** (ví dụ trừ tiền, gửi email), có nguy cơ thực hiện hai lần. Cần thiết kế idempotency, deduplication hoặc transaction/consensus tương ứng.

### Với phép tính tổng thuần túy

Một task chỉ đọc partition và trả partial sum là **pure computation** nếu input snapshot cố định. Nó có thể được thực thi lại an toàn, nhưng coordinator phải **chỉ tính một kết quả đúng cho mỗi task ID**. Nếu cộng cả response cũ và response retry, tổng sẽ bị nhân đôi.

### “Exactly once” không miễn phí

Một hệ thống có thể cung cấp hiệu ứng exactly-once theo hợp đồng nhất định bằng log, checkpoint, transaction, idempotency và recovery. Không được giả định nó tự có chỉ vì dùng message queue hoặc RPC.

## 10. Dữ liệu phân mảnh, replication và nhất quán

### Partitioning / sharding

Chia input thành các phần:

~~~text
partition0 -> worker0
partition1 -> worker1
partition2 -> worker2
...
~~~

Mỗi partition cần được xử lý đúng một lần theo ngữ nghĩa kết quả. Với phép tổng, chỉ cần các đoạn **không chồng nhau và phủ đủ đầu vào**. Với join, group-by hoặc graph algorithms, có thể phải di chuyển theo key hoặc trao đổi thông tin biên partition.

### Data locality

Một worker gần dữ liệu của nó có thể giảm network traffic. Nếu mỗi worker phải kéo nguyên tập dữ liệu từ một node trung tâm, node đó có thể thành bottleneck dù có nhiều máy tính toán.

### Replication

Giữ bản sao dữ liệu ở nhiều node có thể tăng khả năng đọc và phục hồi. Nhưng nếu có update, cần xác định:

- Bản sao nào được cập nhật trước?
- Khi nào các replica cùng thấy một phiên bản?
- Có bắt buộc đọc giá trị mới nhất hay chấp nhận eventual consistency?
- Ai quyết định kết quả khi node mất kết nối?
- Một task đang chạy nhìn thấy snapshot nào?

Replication không đồng nghĩa tự động nhất quán mạnh.

### Snapshot và kết quả chính xác

Nếu nhiều worker tính tổng trên những phiên bản dữ liệu khác nhau trong khi dữ liệu được cập nhật, kết quả có thể không đại diện cho **bất kỳ snapshot nhất quán nào**. Cần định nghĩa snapshot/version/epoch trước khi gửi các partition.

## 11. Đồng bộ: barrier, reduce và giao tiếp tập thể

Một thuật toán song song thường có pha:

~~~text
partition -> local compute -> synchronization -> combine
~~~

Trong shared-memory, ta có thể dùng `CountDownLatch`, `CyclicBarrier`, `Phaser`, `Future.get()` hoặc `join()` tùy tính chất cần thiết.

Trong distributed-memory, những primitive tương ứng có thể là:

- **Barrier:** các process đợi đến một mốc đồng bộ.
- **Broadcast:** phát cùng dữ liệu đến nhiều worker.
- **Scatter:** gửi các partition khác nhau.
- **Gather:** thu kết quả về một nơi.
- **Reduce / all-reduce:** kết hợp các partial results theo phép gộp, đôi khi trả kết quả cho mọi worker.

### Chọn phép gộp phù hợp

Với tổng số nguyên không overflow:

~~~text
combine(a,b) = a+b
identity = 0
~~~

Phép cộng kết hợp, nên có thể gộp partial sums theo các thứ tự khác nhau mà vẫn ra cùng kết quả toán học.

Nếu dùng floating-point, `(a+b)+c` có thể khác `a+(b+c)` do làm tròn. Các worker hoàn thành theo thứ tự khác nhau có thể làm kết quả số thực chênh nhẹ. Muốn reproducibility bit-for-bit cần chiến lược reduction xác định hoặc số học phù hợp.

### Barrier không có nghĩa failover

Một barrier đơn giản có thể chờ vô hạn nếu worker bị crash. Distributed barrier cần timeout/cancellation/membership hoặc recovery theo hợp đồng hệ thống; không có primitive giao tiếp tập thể nào tự giải quyết mọi lỗi node.

## 12. Cost model: work, span và chi phí giao tiếp

Cho một thuật toán song song:

- **W (work):** tổng lượng công việc, gần thời gian chạy tuần tự theo mô hình lý tưởng.
- **S (span/critical path):** độ dài chuỗi phụ thuộc dài nhất, không thể song song hóa.
- **p:** số đơn vị xử lý.

Một cận dưới lý tưởng:

~~~text
T_p >= max(W/p, S)
~~~

Vì không thể thực hiện nhiều hơn p đơn vị công việc đồng thời, cũng không thể rút ngắn đường phụ thuộc dài nhất.

### Amdahl's law

Nếu phần công việc bắt buộc tuần tự là tỷ lệ s, phần còn lại tăng tốc lý tưởng với p worker:

~~~text
Speedup(p) <= 1 / (s + (1-s)/p)
~~~

Ví dụ s=0,1 và p=8:

~~~text
1 / (0.1 + 0.9/8)
= 1 / 0.2125
≈ 4.706
~~~

Không phải 8 lần, ngay cả khi bỏ qua overhead.

### Shared-memory có overhead gì?

- Tạo/scheduling thread.
- Cache miss và tranh chấp memory bandwidth.
- Lock/atomic contention.
- False sharing và NUMA remote accesses.
- Barrier hoặc reduce partial sums.

### Distributed-memory có overhead gì?

Có thêm:

~~~text
T ≈ TlocalCompute
   + messageCount * latency
   + transferredBytes / bandwidth
   + serialization/deserialization
   + coordination/retry/checkpoint overhead
~~~

Đây chỉ là mô hình ước lượng; các pha có thể overlap, mạng có congestion và thuật toán có nhiều vòng giao tiếp. Không được tự suy ra công thức là một phép đo chính xác cho mọi cluster.

### Mỗi worker nhanh hơn không bảo đảm toàn hệ thống nhanh hơn

Một `shuffle` lớn có thể chuyển rất nhiều byte; node chậm nhất có thể giữ cả pipeline; một coordinator duy nhất cũng có thể trở thành bottleneck.

## 13. Ví dụ so sánh trên một phép toán: tổng mảng

Cho dữ liệu xác định:

~~~text
n = 100003

value(i) = ((i * 37) mod 103) - 51
i = 0..100002
~~~

Do 37 và 103 nguyên tố cùng nhau, 103 chỉ số liên tiếp modulo 103 đi qua toàn bộ 103 giá trị, nên mỗi chu kỳ chứa lần lượt một hoán vị các số từ −51 đến 51, tổng bằng 0.

~~~text
n = 103 * 970 + 93

full periods sum = 0
remaining 93 entries sum = -30

expected total = -30
~~~

Đây là một **oracle theo chu kỳ**, độc lập với cách chia tác vụ.

### Mô hình shared-memory

Bốn tác vụ đọc trực tiếp mảng `int[]` chung và mỗi tác vụ trả một `long`.

| Task | Đoạn 0-based nửa mở | Số phần tử | Partial sum |
| ---: | --- | ---: | ---: |
| 0 | [0,25000) | 25.000 | −39 |
| 1 | [25000,50001) | 25.001 | −62 |
| 2 | [50001,75002) | 25.001 | 3 |
| 3 | [75002,100003) | 25.001 | 68 |
| Tổng | Toàn bộ mảng | 100.003 | **−30** |

Những đoạn không chồng nhau và phủ đúng toàn bộ `[0,n)`. Input không bị sửa trong lúc chạy; worker chỉ **đọc** và trả partial result.

### Mô phỏng message-passing

Chia dữ liệu thành chunk tối đa **8.192 phần tử**:

~~~text
12 chunks of 8192 elements
1 last chunk of 1699 elements

13 messages in total
~~~

Mỗi message mã hóa 4 byte `count` và 4 byte cho mỗi phần tử:

~~~text
application payload bytes
= 13 * 4 + 100003 * 4
= 400064 bytes
~~~

Giá trị này **chỉ là tổng kích thước payload request** trong ví dụ; chưa bao gồm kết quả trả về, transport/network headers, queue objects, buffer copies và retries.

### Kết quả đúng không phụ thuộc thứ tự hoàn thành

Task 7 có thể hoàn thành trước task 1. Vì phép cộng long ở ví dụ không overflow và các partition độc lập, coordinator có thể dùng task ID để đặt partial vào đúng vị trí rồi gộp kết quả cuối. Điều quan trọng là **mỗi ID được tính một lần** và không thiếu partition.

## 14. Java 17: chương trình chạy được minh họa hai kiểu

Ví dụ dưới đây dùng **một JVM duy nhất** để chạy cả hai cách tổ chức:

- **Shared-memory thực sự:** nhiều thread truy cập cùng mảng đầu vào chỉ đọc.
- **Message-passing được mô phỏng:** main thread **serialize từng partition sang byte[]**; task phía worker chỉ nhận byte[] và decode/sum, **không trực tiếp đọc mảng gốc**.
- Mỗi task trả result có ID và count; coordinator đặt kết quả theo ID bất kể completion order.
- `ExecutorCompletionService` cho phép nhận kết quả theo thứ tự hoàn thành.
- Có kiểm tra số phần tử, task IDs, dữ liệu đầu vào, lỗi message và đối chiếu với oracle.

**Điều cực kỳ quan trọng:** các “worker” nhận byte[] ở đây vẫn là thread trong **cùng một JVM**, không phải process/máy độc lập. Code này minh họa **ranh giới giao tiếp bằng thông điệp**, nhưng **không mô phỏng được network latency, partial failure, distributed consensus, container isolation hay process crash**. Muốn có hệ thống phân tán thật, phải thay bộ gửi công việc bằng transport/worker process thực sự và bổ sung giao thức vận hành.

Lưu thành **`SharedVsDistributedMemoryDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.Objects;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SharedVsDistributedMemoryDemo {

    private record Piece(int taskId, int count, long sum) {}

    private record Result(
            long sum, int tasks, long requestPayloadBytes) {}

    private static int valueAt(int index) {
        return (int) (((long) index * 37L) % 103L) - 51;
    }

    private static long serialSum(int[] data) {
        long total = 0L;
        for (int x : data) {
            total += x;
        }
        return total;
    }

    // Independent oracle from the exact period of valueAt().
    private static long expectedByPeriod(int n) {
        long cycleSum = 0L;
        for (int i = 0; i < 103; i++) {
            cycleSum += valueAt(i);
        }
        if (cycleSum != 0L) {
            throw new AssertionError("period does not sum to zero");
        }

        long remainder = 0L;
        for (int i = 0; i < n % 103; i++) {
            remainder += valueAt(i);
        }
        return (n / 103L) * cycleSum + remainder;
    }

    private static void checkWorkers(int workers) {
        if (workers < 1) {
            throw new IllegalArgumentException(
                    "workers must be >= 1");
        }
    }

    // SHARED MEMORY: each task reads the SAME int[] object.
    private static Result sharedMemorySum(
            int[] data, int workers) throws Exception {
        Objects.requireNonNull(data, "data");
        checkWorkers(workers);
        int count = data.length;
        if (count == 0) {
            return new Result(0L, 0, 0L);
        }

        int tasks = Math.min(workers, count);
        ExecutorService pool =
                Executors.newFixedThreadPool(tasks);
        try {
            CompletionService<Piece> finished =
                    new ExecutorCompletionService<>(pool);

            for (int id = 0; id < tasks; id++) {
                int from = (int) (((long) id * count) / tasks);
                int to = (int) (
                        ((long) (id + 1) * count) / tasks);
                final int taskId = id;

                finished.submit(() -> {
                    long local = 0L;
                    for (int i = from; i < to; i++) {
                        local += data[i];
                    }
                    return new Piece(taskId, to - from, local);
                });
            }

            long[] partial = new long[tasks];
            boolean[] seen = new boolean[tasks];
            int returned = 0;

            for (int i = 0; i < tasks; i++) {
                Piece piece = finished.take().get();
                int id = piece.taskId();
                if (id < 0 || id >= tasks || seen[id]) {
                    throw new AssertionError(
                            "duplicate/invalid task ID");
                }
                seen[id] = true;
                partial[id] = piece.sum();
                returned += piece.count();
            }

            if (returned != count) {
                throw new AssertionError(
                        "missing elements");
            }
            long total = 0L;
            for (long part : partial) {
                total += part;
            }
            return new Result(total, tasks, 0L);
        } finally {
            pool.shutdownNow();
        }
    }

    // One application message: int32 count, then count int32.
    private static byte[] encodeChunk(
            int[] data, int from, int to)
            throws IOException {
        ByteArrayOutputStream raw =
                new ByteArrayOutputStream();
        try (DataOutputStream output =
                     new DataOutputStream(raw)) {
            output.writeInt(to - from);
            for (int i = from; i < to; i++) {
                output.writeInt(data[i]);
            }
        }
        return raw.toByteArray();
    }

    // A worker-side handler: no access to the source int[].
    private static Piece handleMessage(
            int taskId, byte[] bytes) throws IOException {
        Objects.requireNonNull(bytes, "bytes");
        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(bytes))) {
            int count = input.readInt();
            if (count < 0
                    || bytes.length != 4L + 4L * count) {
                throw new IllegalArgumentException(
                        "invalid message length");
            }

            long local = 0L;
            for (int i = 0; i < count; i++) {
                local += input.readInt();
            }
            return new Piece(taskId, count, local);
        }
    }

    // MESSAGE-PASSING SIMULATION, still ONE JVM.
    // All workers consume serialized byte[] only.
    private static Result messagePassingSimulation(
            int[] data, int workers, int chunkSize)
            throws Exception {
        Objects.requireNonNull(data, "data");
        checkWorkers(workers);
        if (chunkSize < 1) {
            throw new IllegalArgumentException(
                    "chunk size must be >= 1");
        }
        if (data.length == 0) {
            return new Result(0L, 0, 0L);
        }

        int tasks = (int) (
                ((long) data.length - 1L) / chunkSize + 1L);
        ExecutorService pool = Executors.newFixedThreadPool(
                Math.min(workers, tasks));

        try {
            CompletionService<Piece> finished =
                    new ExecutorCompletionService<>(pool);

            long payloadBytes = 0L;
            int taskId = 0;
            for (int from = 0; from < data.length;) {
                int to = (int) Math.min(
                        (long) data.length,
                        (long) from + chunkSize);

                // The producer has access to data.
                // The worker callback receives only bytes.
                final byte[] wire = encodeChunk(data, from, to);
                final int id = taskId;
                payloadBytes += wire.length;

                finished.submit(() -> handleMessage(id, wire));
                taskId++;
                from = to;
            }
            if (taskId != tasks) {
                throw new AssertionError(
                        "wrong task count");
            }

            long[] partial = new long[tasks];
            boolean[] seen = new boolean[tasks];
            int returned = 0;

            for (int i = 0; i < tasks; i++) {
                Piece piece = finished.take().get();
                int id = piece.taskId();
                if (id < 0 || id >= tasks || seen[id]) {
                    throw new AssertionError(
                            "duplicate/invalid task ID");
                }
                seen[id] = true;
                partial[id] = piece.sum();
                returned += piece.count();
            }

            if (returned != data.length) {
                throw new AssertionError(
                        "message coverage mismatch");
            }
            long total = 0L;
            for (long part : partial) {
                total += part;
            }
            return new Result(total, tasks, payloadBytes);
        } finally {
            pool.shutdownNow();
        }
    }

    // Exhaustive codec/partition oracle on short arrays.
    // It does not create thousands of thread pools.
    private static int[] verifyCodecExhaustive()
            throws IOException {
        int arrays = 0;
        int configurations = 0;
        int[] alphabet = {-2, 0, 3};

        for (int n = 0; n <= 6; n++) {
            int cases = 1;
            for (int i = 0; i < n; i++) {
                cases *= alphabet.length;
            }

            for (int code = 0; code < cases; code++) {
                int[] data = new int[n];
                int number = code;
                for (int i = 0; i < n; i++) {
                    data[i] = alphabet[
                            number % alphabet.length];
                    number /= alphabet.length;
                }

                long oracle = serialSum(data);
                for (int chunkSize = 1;
                        chunkSize <= 4; chunkSize++) {
                    long total = 0L;
                    int covered = 0;

                    for (int from = 0; from < n;) {
                        int to = Math.min(
                                n, from + chunkSize);
                        byte[] bytes = encodeChunk(
                                data, from, to);
                        Piece piece = handleMessage(
                                covered, bytes);

                        if (piece.count() != to - from
                                || bytes.length
                                   != 4 + 4 * (to - from)) {
                            throw new AssertionError(
                                    "codec framing mismatch");
                        }

                        total += piece.sum();
                        covered += piece.count();
                        from = to;
                    }

                    if (total != oracle || covered != n) {
                        throw new AssertionError(
                                "codec/partition mismatch");
                    }
                    configurations++;
                }
                arrays++;
            }
        }

        if (arrays != 1093 || configurations != 4372) {
            throw new AssertionError(
                    "wrong exhaustive counts");
        }
        return new int[] {arrays, configurations};
    }

    private static int verifyThreadedEdgeCases()
            throws Exception {
        int[][] cases = {
                {},
                {7},
                {1, -1},
                {-5, 0, 5, 10},
                {Integer.MIN_VALUE, Integer.MAX_VALUE,
                        -1, 1}
        };

        for (int[] data : cases) {
            int[] before = data.clone();
            long oracle = serialSum(data);
            Result shared = sharedMemorySum(data, 4);
            Result messages = messagePassingSimulation(
                    data, 4, 2);

            if (shared.sum() != oracle
                    || messages.sum() != oracle
                    || !Arrays.equals(before, data)) {
                throw new AssertionError(
                        "threaded edge case differs");
            }
        }
        return cases.length;
    }

    public static void main(String[] args)
            throws Exception {
        int n = 100003;
        int[] input = new int[n];
        for (int i = 0; i < n; i++) {
            input[i] = valueAt(i);
        }

        int[] before = input.clone();
        long serial = serialSum(input);
        long oracle = expectedByPeriod(n);
        Result shared = sharedMemorySum(input, 4);
        Result message = messagePassingSimulation(
                input, 4, 8192);

        System.out.println("n = " + n);
        System.out.println("serial = " + serial);
        System.out.println("period oracle = " + oracle);
        System.out.println(
                "shared sum = " + shared.sum());
        System.out.println(
                "shared tasks = " + shared.tasks());
        System.out.println(
                "message simulation sum = " + message.sum());
        System.out.println(
                "serialized tasks = " + message.tasks());
        System.out.println(
                "application payload bytes = "
                + message.requestPayloadBytes());

        boolean match = serial == oracle
                && shared.sum() == oracle
                && message.sum() == oracle;
        System.out.println("all sums equal = " + match);
        System.out.println(
                "input unchanged = "
                + Arrays.equals(before, input));

        Result emptyShared = sharedMemorySum(
                new int[0], 4);
        Result emptyMessage = messagePassingSimulation(
                new int[0], 4, 8);
        System.out.println(
                "empty both models = "
                + (emptyShared.sum() == 0L
                   && emptyMessage.sum() == 0L
                   && emptyShared.tasks() == 0
                   && emptyMessage.tasks() == 0));

        try {
            handleMessage(0, new byte[] {
                    0, 0, 0, 2,
                    0, 0, 0, 1
            });
            throw new AssertionError(
                    "invalid message was accepted");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid message: " + error.getMessage());
        }

        try {
            sharedMemorySum(input, 0);
            throw new AssertionError(
                    "invalid worker count was accepted");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid workers: " + error.getMessage());
        }

        int[] codec = verifyCodecExhaustive();
        System.out.println(
                "codec arrays checked = " + codec[0]);
        System.out.println(
                "codec chunk configurations = " + codec[1]);
        System.out.println(
                "threaded edge cases checked = "
                + verifyThreadedEdgeCases());
        System.out.println("all checks passed = true");
    }
}
~~~

### Biên dịch và thực thi

~~~bash
javac SharedVsDistributedMemoryDemo.java
java SharedVsDistributedMemoryDemo
~~~

**Stdout dự kiến chính xác**, độc lập với thứ tự thread hoàn thành:

~~~text
n = 100003
serial = -30
period oracle = -30
shared sum = -30
shared tasks = 4
message simulation sum = -30
serialized tasks = 13
application payload bytes = 400064
all sums equal = true
input unchanged = true
empty both models = true
invalid message: invalid message length
invalid workers: workers must be >= 1
codec arrays checked = 1093
codec chunk configurations = 4372
threaded edge cases checked = 5
all checks passed = true
~~~

Khi demo hoàn tất, kết quả tổng là xác định. Thời gian thread chạy, thứ tự completion và thời gian được scheduler cấp CPU **không xác định**, nhưng output không in những thứ đó. Không suy ra rằng mỗi thread luôn chiếm một core vật lý hay luôn tạo được speedup.

## 15. Giải thích mã: điều gì thật sự được chia sẻ?

### Shared path

Trong `sharedMemorySum`:

~~~java
finished.submit(() -> {
    long local = 0L;
    for (int i = from; i < to; i++) {
        local += data[i];
    }
    return new Piece(taskId, to - from, local);
});
~~~

Mọi worker có reference tới cùng `int[] data`. Chúng chỉ đọc các đoạn **không giao nhau**, không ghi vào shared array. Việc chia các đoạn theo phép chia nguyên long tránh overflow khi tính `taskId * count` với các mảng lớn.

Kết quả `Piece` chứa id và count; coordinator dùng `finished.take().get()` để đợi từng kết quả. Các thread có thể hoàn thành khác thứ tự submit, nhưng partial sums được đặt vào `partial[id]`, rồi cộng theo ID.

### Message path

Trong `messagePassingSimulation`, producer làm:

~~~java
byte[] wire = encodeChunk(data, from, to);
finished.submit(() -> handleMessage(id, wire));
~~~

Handler chỉ dùng **`wire`** được truyền qua callback; không truy cập `data`. Nó kiểm `count` và tổng số byte trước khi decode, sau đó trả một partial sum.

Sự khác biệt thể hiện ở API và ownership của dữ liệu, không phải ở cơ chế cách ly bộ nhớ: `wire` vẫn là một byte array trong cùng JVM. Một chương trình phân tán thật cần thay callback bằng **gửi request qua IPC/network tới process khác**, phải có framing, timeouts, retries, resource limits và authentication theo môi trường.

### Không có backpressure trong demo

Producer tạo các payload rồi submit hết **13 task** trước khi nhận kết quả. Với tập dữ liệu lớn và hàng triệu task, thiết kế giữ quá nhiều byte[]/futures có thể gây memory pressure.

Muốn sản xuất, dùng **bounded in-flight tasks**, bounded queue theo byte, streaming partition hoặc một dispatcher có backpressure. Một message queue hữu hạn không thể tự bảo đảm cluster không OOM nếu producer vẫn tạo vô hạn request ở một tầng khác.

### Vì sao dùng `long` cho tổng?

Một phần tử được đọc bằng `int` nhưng tổng n phần tử có thể vượt `int`. Với `int[]` có số phần tử trong giới hạn chỉ số Java và các giá trị int, `long` có không gian rộng hơn đáng kể; trong dữ liệu ví dụ tất cả kết quả nằm an toàn trong long.

Nếu làm phép nhân, tổng tích hoặc dùng `long[]` với giá trị cực trị, có thể vẫn overflow; cần nêu/kiểm các bound riêng.

## 16. Kiểm thử độc lập và các bất biến

### Oracle tổng tuần tự

`serialSum` cộng trực tiếp toàn bộ dữ liệu mà không chia partition. Đây là đối chứng với cả hai phương pháp song song.

### Oracle chu kỳ toán học

Vì phép nhân 37 sinh hoán vị modulo 103:

~~~text
sum of one full 103-element cycle = 0
100003 = 970*103 + 93
sum of first 93 elements of cycle = -30
~~~

Đối chiếu `serial = shared = message = periodOracle = −30` phát hiện một nhóm lỗi đếm thiếu/dư dữ liệu.

### Kiểm mỗi partition đúng một lần

Với shared-memory:

~~~text
ranges cover [0,n)
ranges do not overlap
sum of range lengths = n
~~~

Với message-passing simulation:

~~~text
each sent payload has count
decoded bytes = 4 + 4*count
one result per task ID
sum of returned counts = n
~~~

Chương trình từ chối task ID trùng/ngoài phạm vi và kiểm tổng count sau khi thu kết quả.

### Kiểm codec theo liệt kê mảng nhỏ

Sinh mọi mảng có độ dài 0..6, giá trị thuộc `{−2,0,3}`:

~~~text
3^0+3^1+...+3^6 = 1093 arrays
~~~

Với **4 chunk sizes** từ 1 đến 4, tổng cấu hình:

~~~text
1093 * 4 = 4372
~~~

Mỗi cấu hình được serialize/decode theo từng chunk, gộp partial sum và so với tổng tuần tự. Cách kiểm này độc lập với scheduler, không cần tạo 4.372 thread pools.

### Kiểm concurrency trên case biên

Chương trình còn chạy cả hai đường **thực sự bằng ExecutorService** trên năm dãy:

~~~text
[]
[7]
[1,-1]
[-5,0,5,10]
[Integer.MIN_VALUE,Integer.MAX_VALUE,-1,1]
~~~

Nó kiểm tổng và mảng input không bị mutate. Những case này có input rỗng, một phần tử, số âm, số dương, và cực trị int.

### Điều chưa được kiểm

- Network delivery, partial node failure hoặc timeout.
- Bảo mật giao thức và versioning schema qua máy.
- Đồng bộ và nhất quán của dữ liệu có update song song.
- Áp lực memory khi có hàng triệu message đang chờ.
- Tăng tốc thực tế; chương trình không đo speedup.

Những trường hợp đó cần hạ tầng và bộ test riêng của một deployment phân tán thật.

## 17. Từ mô phỏng sang hệ thống phân tán thật

Muốn biến ví dụ message-passing thành một cluster application:

1. **Chia partition theo key hoặc range.** Lưu location/version của từng partition.
2. **Định nghĩa protocol có version:** task ID, partition/version, encoding, checksum, result schema.
3. **Transport:** gửi request tới worker process qua TCP/RPC/message broker hoặc worker tự lấy task từ queue.
4. **Receiver process:** decode vào bộ nhớ **riêng** của nó, tính partial result, trả kết quả.
5. **Coordinator:** theo dõi pending/in-progress/completed, chỉ chấp nhận **một kết quả hợp lệ cho mỗi task ID**.
6. **Timeout và retry:** có deadline, exponential backoff theo điều kiện và idempotency nếu có side effect.
7. **Failure recovery:** tái phân công partition khi worker chết, quản lý checkpoint/offset.
8. **Observability:** metrics latency, bytes sent, retries, queue depth, straggler time và distributed traces.
9. **Security:** authentication, authorization, encryption và giới hạn payload.
10. **Scale test:** thử tình huống mạng chậm, packet loss, node restart, partition, skew và dữ liệu lớn.

### Quá trình gộp cũng cần bảo toàn ngữ nghĩa

Nếu một worker timeout nhưng đã tính xong, việc retry có thể tạo hai partial results cùng task ID. Coordinator phải biết **task ID đã hoàn thành hay chưa**, chứ không cộng cả hai.

Nếu input có cập nhật giữa các lần retry, phải pin phiên bản snapshot; nếu không, hai lần xử lý cùng ID có thể ra hai partial sums khác nhau. Không được xem retry như một cơ chế miễn phí.

### Kiến trúc hybrid

Một worker process trên mỗi node có thể tiếp tục dùng nhiều Java threads để xử lý phần local. Khi ấy cần cả:

- Chống data race trong shared-memory nội bộ process.
- Message protocol/fault tolerance giữa các process.
- Memory budget cho mỗi node và network budget của cả cluster.

Đây là trường hợp thực tế phổ biến hơn sự lựa chọn tuyệt đối một mô hình.

## 18. Chọn mô hình theo workload, bottleneck và mục tiêu

| Tình huống | Hướng cân nhắc | Vì sao |
| --- | --- | --- |
| Mảng vừa RAM một máy, chia được thành đoạn độc lập | Shared-memory threads | Ít di chuyển dữ liệu, đơn giản |
| Input lớn hơn RAM một máy, lưu trên nhiều node | Distributed-memory | Partition và xử lý gần dữ liệu |
| Cần độ trễ cực thấp trong một process | Shared-memory hoặc tuần tự tối ưu | Tránh network serialization |
| Cần scale-out nhiều máy | Distributed-memory | Mở rộng capacity nhưng tốn communication |
| Bài có shared counter cập nhật liên tục | Partition/partial reduction trong shared | Giảm lock/atomic contention |
| Bài có shuffle lớn giữa partition | Phân tán nhưng cần tối ưu locality | Network có thể thành bottleneck |
| Nhiều node, mỗi node nhiều cores | Hybrid | Threads local + messages inter-node |
| Cần xử lý partial failures | Distributed framework có recovery | Worker có thể chết độc lập |
| Phép tính rất nhỏ | Tuần tự có thể tốt nhất | Parallel overhead lấn át work |
| Bài graph có nhiều cạnh cắt partition | Cân nhắc kỹ | Communication và synchronization dày đặc |
| Pipeline nhiều microservices | Message/RPC | Ranh giới process và governance |
| Bài iterative có nhiều barrier | Ưu tiên tối ưu đồng bộ | Chậm nhất/latency chi phối |

### Cách đánh giá thực nghiệm

- Dùng **cùng input và tiêu chí đúng** cho serial/shared/distributed.
- Ghi wall time, CPU time, memory peak, network bytes và số message.
- Kiểm dữ liệu có được partition cân bằng không.
- Đo work và critical path khi có thể.
- Thử một worker, rồi tăng dần p; nhìn vào **speedup và efficiency**.
- Phân tích latency, bandwidth, serialization, cache misses, lock contention và skew.
- Lưu seed/config/version cho khả năng tái lập.
- Không dùng một lần benchmark để kết luận mô hình luôn tốt hơn.

### Một cảnh báo về từ “shared”

Một database có **shared storage** không có nghĩa ứng dụng Java trên hai máy đọc được cùng heap object. “Shared-memory model”, “shared disk/storage” và “shared cache” là những tầng khái niệm khác nhau.

## 19. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách hiểu/sửa |
| --- | --- | --- |
| Gọi nhiều threads là nhiều máy | Nhầm deployment | Cùng JVM là shared address space |
| Gọi queue trong một JVM là distributed memory thật | Quá khẳng định | Phân biệt simulation và process isolation |
| Truyền object reference qua mạng như con trỏ | Không hợp lệ | Serialize/IPC/remote ID |
| Dùng biến global cho mọi node | Node khác không cùng heap | Dùng protocol/replication |
| Shared counter++ không đồng bộ | Lost updates | Atomic/lock/partial sums |
| Dùng volatile để biến increment thành atomic | Vẫn race | AtomicLong hoặc synchronized |
| Giữ input mutable khi tasks đọc | Snapshot không nhất quán | Freeze/copy/version |
| Không đợi Future hoặc barrier | Dùng kết quả trước khi xong | Join/get/collective |
| Chỉ tính CPU work và bỏ communication | Speedup ảo | Tính latency/bandwidth |
| Chia một phần tử thành một network message | Overhead rất lớn | Batch/chunk hợp lý |
| Chia dữ liệu không cân bằng | Straggler | Dynamic scheduling, rebalance |
| Gửi trùng kết quả mà không có task ID | Cộng nhầm | ID, dedupe, idempotency |
| Timeout rồi giả định worker chưa làm gì | Retry side effect hai lần | Protocol và outcome tracking |
| Nghĩ replication luôn strong consistent | Đọc phiên bản sai | Nêu consistency contract |
| Chạy reduce float theo completion order rồi đòi bit-identical | Sai số làm tròn | Deterministic reduction |
| Nhầm cache coherence với JMM happens-before | Thiếu memory visibility | Dùng synchronization đúng |
| Coi false sharing là data race | Chẩn đoán sai | Phân biệt hiệu năng và tính đúng |
| Dùng chung array trong “distributed” demo mà không nói | Không thể hiện data ownership | Chuyển payload rõ |
| Mở hàng triệu futures không bounded | OOM in-process | Backpressure, giới hạn in-flight |
| Xem network partition là lỗi thread thường | Thiếu partial failure model | Retry/membership/quorum |
| Cho rằng shared luôn nhanh hơn | Bỏ scale-out | So workload và constraint |
| Cho rằng distributed luôn mở rộng tuyến tính | Quên network/skew | Đo speedup, efficiency |
| Không phân biệt process isolation và hardware node | Chọn sai mô hình | Định nghĩa ranh giới |
| Gộp partial theo ID thiếu kiểm số lượng | Có thể mất dữ liệu | Check coverage/count |
| Không kiểm kiểu số khi sum lớn | Overflow | Dùng long/BigInteger nếu cần |
| Chỉ test tổng một lần | Dễ bỏ lỗi partition | Oracle, edge cases, exhaustive nhỏ |
| Tăng thread count vô hạn | Contention/overhead | Bound concurrency theo tài nguyên |

### Checklist debug nhanh

Nếu output sai, hãy kiểm **coverage và duplication** của partition trước; sau đó kiểm concurrent writes/visibility ở shared-memory, hoặc message IDs/schema/version ở distributed-memory.

Nếu output đúng nhưng chậm, kiểm overhead task creation, memory bandwidth/cache coherence hoặc chi phí serialization/network. Đừng vội tăng số thread/node trước khi biết bottleneck.

## 20. Bài tập và tổng kết

### Bài tập theo mức độ

1. Định nghĩa shared-memory model bằng quyền truy cập object.
2. Định nghĩa distributed-memory model bằng address space và message passing.
3. Nêu hai ví dụ thực tế cho mỗi mô hình.
4. Vì sao nhiều thread Java trong cùng JVM là shared-memory?
5. Vì sao hai process trên cùng máy có thể thuộc distributed-memory model?
6. Vẽ mô hình hybrid có ba node, mỗi node bốn thread.
7. Phân biệt process, thread, core và cache.
8. Nêu một workload mảng vừa RAM phù hợp shared-memory.
9. Nêu một workload scale-out cần distributed-memory.
10. Chia mảng 13 phần tử cho bốn worker thành đoạn không giao nhau.
11. Chứng minh tổng độ dài các đoạn bằng n.
12. Giải thích tại sao input read-only tránh data race.
13. Nêu ví dụ lost update với `counter++`.
14. Giải thích `volatile` không làm `counter++` atomic.
15. So synchronized, AtomicLong và local reduction.
16. Mô tả deadlock do hai lock được lấy ngược thứ tự.
17. Định nghĩa happens-before trong ví dụ task/Future.
18. Vì sao đọc một array bị sửa đồng thời có thể sai snapshot?
19. Giải thích false sharing và memory bandwidth contention.
20. Giải thích NUMA dù vẫn có một không gian địa chỉ.
21. Mô tả payload cần có của một message tính tổng partition.
22. Tại sao Java object reference không phải wire format?
23. Đếm byte cho packet gồm int32 count và c int32 values.
24. Tính payload của 100.003 số nguyên chia thành 13 message.
25. Phân biệt application payload bytes và physical network bytes.
26. Giải thích local task vs message-passing task ownership.
27. Cài Java `ExecutorCompletionService` thu partial theo ID.
28. Thử để task trả kết quả theo thứ tự completion khác submit.
29. Cài encode/decode int32 big-endian.
30. Tạo packet khai báo hai int nhưng chỉ chứa một int, phải reject.
31. Chứng minh một task ID chỉ nên đóng góp một lần.
32. Nêu hậu quả retry task có side effect mà không idempotency.
33. Phân biệt timeout với thất bại đã được chứng minh.
34. Phân tích response duplicate sau khi coordinator retry.
35. Giải thích vì sao retry phải pin phiên bản input.
36. Nêu khác biệt giữa strong consistency và eventual consistency.
37. Cho ví dụ dữ liệu cập nhật làm partial sums không cùng snapshot.
38. Phân biệt scatter, gather và reduce.
39. Vì sao barrier có thể kẹt khi một worker crash?
40. Chứng minh cận T_p≥max(W/p,S).
41. Tính speedup Amdahl khi s=0,1 và p=8.
42. Giải thích vì sao m*latency ảnh hưởng ứng dụng nhiều message nhỏ.
43. Nêu cách đo bytes/s, latency và throughput riêng.
44. Tạo input 100.003 phần tử theo generator của bài.
45. Chứng minh chu kỳ 103 phần tử có tổng 0.
46. Tính tổng remainder 93 phần tử thành −30.
47. Cộng bốn shared partial sums −39,−62,3,68.
48. Tính 12 chunk đủ 8192 và chunk cuối 1699.
49. Kiểm 4.372 cấu hình codec của các mảng ngắn.
50. Thử cả array rỗng, một phần tử, số âm và `Integer.MIN_VALUE`.
51. Mở rộng mô phỏng bằng bounded in-flight tasks.
52. Đề xuất protocol có task ID, version, checksum và deadline.
53. Thiết kế worker process TCP thật, nêu khác biệt so với demo.
54. Thiết kế test worker crash rồi retry, không cộng kết quả hai lần.
55. Tính hiệu quả p-processor bằng speedup/p.
56. So một vòng lặp song song có ít công việc với serial.
57. Xác định một tác vụ có data skew và cách phân vùng lại.
58. Phân tích chi phí network shuffle khi group-by theo key.
59. Nêu khi nào nên dùng hybrid per-node shared memory + inter-node messages.
60. Viết bảng quyết định giữa shared, distributed và hybrid cho workload cụ thể.

### Checklist cuối cùng

- Có xác định **đơn vị thực thi và address space** của từng worker?
- Dữ liệu được chia sẻ trực tiếp hay chuyển bằng message?
- Input có được giữ **read-only/snapshot/versioned** trong lúc tính?
- Có data race, deadlock, visibility hoặc false-sharing risk?
- Có kiểm **coverage, duplication và đúng task ID**?
- Với distributed, đã tính schema, serialization, network latency/bandwidth?
- Có partial-failure model, retry/idempotency và timeout hợp lệ?
- Có chọn cách reduce phù hợp với integer/floating-point?
- Có đo work/span, load balance và overhead thực tế?
- Có giới hạn concurrency, in-flight messages và memory budget?
- Có tách rõ **mô phỏng message trong một JVM** với hệ thống phân tán thật?
- Có đối chiếu serial oracle và kiểm các trường hợp biên?

**Kết luận:** sự khác biệt nền tảng không phải “một máy hay nhiều máy” mà là **có hay không một không gian bộ nhớ trực tiếp dùng chung và cách worker giao tiếp**. Shared-memory dễ chia một mảng lớn cho các thread và gộp partials, nhưng cần đồng bộ chính xác khi có trạng thái mutable chung. Distributed-memory bắt buộc làm rõ ownership/partition, message protocol và các rủi ro mạng, phiên bản dữ liệu, retry và lỗi một phần. Hai mô hình có thể kết hợp trong hệ thống hybrid; lựa chọn đúng dựa trên **dung lượng dữ liệu, độ hạt của tác vụ, chi phí truyền thông, consistency/fault requirements và bằng chứng benchmark**.
