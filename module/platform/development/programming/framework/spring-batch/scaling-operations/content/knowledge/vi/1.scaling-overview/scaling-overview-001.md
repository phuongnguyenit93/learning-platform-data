# Vì sao cần mở rộng Spring Batch

**Chương:** Tổng quan scaling  
**Phạm vi:** SPRING_BATCH_SCALING_OPERATIONS

Spring Batch phù hợp với những công việc xử lý dữ liệu theo lô như nhập dữ liệu, đối soát giao dịch, tính toán báo cáo, đồng bộ giữa hệ thống hay chuyển đổi dữ liệu. Ở quy mô nhỏ, một tiến trình chạy tuần tự thường dễ xây dựng, theo dõi và khôi phục. Tuy nhiên, khi lượng dữ liệu tăng, thời hạn hoàn thành ngắn lại hoặc hệ thống cần xử lý đồng thời nhiều nguồn dữ liệu, một step chạy tuần tự có thể không còn đáp ứng được.

Trong phạm vi **mở rộng Spring Batch cho workload dữ liệu lớn**, mục tiêu không chỉ là làm job chạy nhanh hơn. Ta còn phải đo đúng nút thắt, sử dụng tài nguyên hợp lý, bảo đảm an toàn khi nhiều luồng cùng chạy, và giữ được khả năng retry, restart cũng như vận hành ổn định. Các kỹ thuật thường gặp gồm **multi-threaded step**, **parallel steps**, **partitioning** và những mô hình xử lý phân tán phù hợp với hệ thống thực tế.

## 1. Hiểu đúng ý nghĩa của scaling

**Scaling** là tăng khả năng hệ thống hoàn thành khối lượng xử lý theo yêu cầu. Trong batch processing, hiệu quả thường được nhìn qua các đại lượng:

| Đại lượng | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Khối lượng (volume) | Số bản ghi, tập tin hoặc nghiệp vụ phải xử lý trong một lần chạy | Có bao nhiêu dữ liệu cần xử lý? |
| Thông lượng (throughput) | Số bản ghi được xử lý thành công trên một đơn vị thời gian, thường là bản ghi/giây | Hệ thống xử lý nhanh đến đâu? |
| Thời gian hoàn tất (elapsed time) | Khoảng thời gian từ lúc job bắt đầu đến khi hoàn thành | Job có kịp thời hạn không? |
| Cửa sổ batch (batch window) | Khoảng thời gian được phép dùng để chạy batch | Có chồng lấn sang lịch chạy hoặc nghiệp vụ tiếp theo không? |
| Độ tin cậy | Khả năng hoàn tất chính xác và khôi phục sau lỗi | Job có thể chạy lại an toàn không? |
| Hiệu quả tài nguyên | Mức CPU, RAM, kết nối DB, I/O, băng thông, quota dịch vụ | Tăng tốc có làm quá tải hệ thống khác không? |

Một job nhanh hơn nhưng ghi trùng giao dịch hoặc không thể restart sau lỗi **không phải** là thành công. Tính đúng đắn của dữ liệu và khả năng vận hành luôn là ràng buộc của bài toán scaling.

### Spring Batch xử lý tuần tự như thế nào?

Trong một **chunk-oriented step** đơn giản, một luồng đọc item bằng **ItemReader**, xử lý bằng **ItemProcessor** (nếu có), rồi ghi bằng **ItemWriter**. Các item được nhóm theo chunk để thực hiện giao dịch và checkpoint.

~~~mermaid
flowchart LR
    A[Input: file / database] --> B[ItemReader]
    B --> C[ItemProcessor]
    C --> D[ItemWriter]
    D --> E[Output: database / file / service]
    F[JobRepository] -. metadata chạy và trạng thái .-> B
    F -. metadata chạy và trạng thái .-> D
~~~

Mô hình này có ưu điểm: dễ hiểu, ít cạnh tranh tài nguyên, thứ tự xử lý thường dễ dự đoán và trạng thái đọc/ghi dễ quản lý. Điểm hạn chế là một luồng xử lý không tận dụng hết khả năng chạy đồng thời của máy hoặc cụm máy trong nhiều loại workload.

**Phân biệt hai mục tiêu:**

- **Tối ưu hóa (optimization):** làm cùng lượng việc với ít chi phí hơn, chẳng hạn giảm truy vấn N+1, đọc theo trang phù hợp, ghi batch hoặc loại bỏ thao tác thừa.
- **Mở rộng (scaling):** tăng năng lực xử lý bằng cách dùng thêm khả năng thực thi đồng thời hoặc phân phối công việc, chẳng hạn nhiều luồng, nhiều step hoặc nhiều worker.

Thông thường nên tìm cơ hội tối ưu rõ ràng trước khi tăng số luồng. Nếu một truy vấn đang bị thiếu index hoặc Writer ghi từng dòng quá chậm, nhân đôi số worker có thể chỉ khiến cơ sở dữ liệu chịu tải gấp đôi.

## 2. Khi nào xử lý tuần tự trở thành vấn đề?

### 2.1. Dữ liệu tăng nhưng thời hạn hoàn thành không đổi

Giả sử hệ thống đối soát cuối ngày phải xử lý **12 triệu giao dịch**, đạt thông lượng đo thực tế là **1.000 bản ghi/giây** với một step tuần tự:

~~~text
Thời gian gần đúng = 12.000.000 / 1.000 = 12.000 giây
                  = 3 giờ 20 phút
~~~

Nếu cửa sổ batch chỉ còn **1 giờ**, thông lượng tối thiểu trên lý thuyết phải đạt:

~~~text
Thông lượng tối thiểu = 12.000.000 / 3.600 ≈ 3.334 bản ghi/giây
~~~

Để có phần dự phòng cho biến động dữ liệu, tranh chấp tài nguyên và thời gian khởi động/kết thúc, nhóm vận hành có thể đặt mục tiêu cao hơn mức tối thiểu. Chẳng hạn, dành 20% năng lực làm dự phòng sẽ tương ứng với công suất thiết kế khoảng **4.167 bản ghi/giây** (3.334 / 0,8). Đây là ví dụ lập kế hoạch, không phải thông lượng mà cứ thêm bốn luồng là tự động đạt được.

### 2.2. Batch chồng lấn lịch chạy và ảnh hưởng nghiệp vụ

Job ban đêm chạy kéo dài đến giờ cao điểm có thể giữ kết nối DB, làm tăng I/O hoặc tranh chấp khóa với giao dịch trực tuyến. Các job phụ thuộc phía sau cũng bị trễ. Khi đó, mục tiêu mở rộng là **hoàn tất trong khung thời gian cam kết**, chứ không đơn thuần giảm vài phút trong môi trường kiểm thử.

### 2.3. Một luồng không dùng hết tài nguyên sẵn có

Ví dụ, một luồng dành nhiều thời gian chờ đọc dữ liệu từ mạng hoặc chờ phản hồi từ hệ thống bên ngoài, trong khi CPU còn rảnh. Nhiều tác vụ độc lập có thể tận dụng thời gian chờ ấy. Ngược lại, nếu CPU đã bão hòa hoặc DB đạt giới hạn I/O, tăng concurrency trên cùng tài nguyên thường ít lợi ích.

### 2.4. Nhiều công việc độc lập phải chạy trong cùng khoảng thời gian

Một job có thể gồm bước chuẩn hóa khách hàng, bước tổng hợp đơn hàng và bước đối chiếu kho. Nếu các bước thật sự **không phụ thuộc dữ liệu hoặc kết quả của nhau**, chạy chúng song song có thể rút ngắn thời gian tổng. Nếu bước B cần kết quả của bước A, không được song song hóa chỉ vì chúng nằm trong cùng job.

### 2.5. Nhu cầu tăng vượt giới hạn một máy

Khi CPU, RAM, số luồng hay băng thông của một JVM không đủ, việc chia dữ liệu thành các phần độc lập để xử lý trên nhiều tiến trình hoặc máy có thể phù hợp hơn việc tiếp tục đẩy concurrency vào một instance.

## 3. Đo nút thắt trước khi quyết định mở rộng

Điểm bắt đầu là **baseline**: đo một lần chạy đại diện với dữ liệu, kích thước batch, cấu hình hạ tầng và tải đồng thời gần thực tế.

Một phép ước lượng đơn giản:

~~~text
Thời gian job ≈ thời gian khởi tạo
              + số item / thông lượng hiệu dụng
              + thời gian kết thúc
~~~

Với một pipeline có thể hoạt động đồng thời, thông lượng bị giới hạn bởi tài nguyên hoặc công đoạn chậm nhất. Với step xử lý hoàn toàn tuần tự, thời gian đọc, xử lý và ghi không chồng lấn có thể **cộng dồn** trên mỗi item. Vì vậy phải đo thông lượng đầu-cuối thực tế; không nên lấy thông lượng của riêng Processor làm thông lượng của toàn job.

### 3.1. Các chỉ số nên ghi nhận

- **Ở mức job/step:** thời gian bắt đầu/kết thúc, elapsed time, item/giây, read count, write count, filter count, skip count, commit count, rollback count và trạng thái hoàn thành. Khi phân tích số liệu, phân biệt item đã đọc, item bị lọc, item bị skip và item đã ghi.
- **Ở JVM:** CPU, heap, garbage collection, số thread đang hoạt động, mức sử dụng bộ nhớ và thời gian chờ.
- **Ở nguồn/đích:** tốc độ đọc file, đĩa và network I/O, độ trễ SQL, database locks, connection pool, hàng đợi, số lần timeout hoặc lỗi giới hạn tốc độ (rate limit).
- **Ở dữ liệu:** phân bố số item theo loại, kích thước payload, tỷ lệ bản ghi khó xử lý, độ lệch giữa các nhóm và số lần retry.
- **Ở vận hành:** thời gian phục hồi sau lỗi, số lần restart, số bản ghi trùng hoặc thiếu khi đối soát và ảnh hưởng tới các hệ thống dùng chung.

### 3.2. Nhận diện triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm chứng |
| --- | --- | --- |
| CPU thấp, nhiều thời gian chờ I/O | Đọc/ghi DB, mạng hoặc dịch vụ ngoài chậm | Đo độ trễ I/O, SQL, pool và thời gian chờ theo công đoạn |
| CPU gần bão hòa trên một core, các core khác rảnh | Công việc CPU-bound đang chạy tuần tự | Profile Processor, thử mức concurrency nhỏ |
| Tăng thread nhưng throughput không tăng | DB/đích đã bão hòa, lock contention, pool quá nhỏ hoặc chia việc kém | So sánh throughput với CPU, DB waits, pool usage và locks |
| Một vài partition hoàn tất rất muộn | Chia dữ liệu mất cân đối hoặc bản ghi có chi phí xử lý khác nhau | Thống kê số item và thời gian của từng partition |
| Tăng tốc nhưng có bản ghi trùng hoặc mất | Reader/Writer không an toàn khi dùng đồng thời; ranh giới dữ liệu sai; retry không idempotent | Đối soát bằng khóa nghiệp vụ và thử restart khi lỗi |
| Thời gian job biến động mạnh | Cạnh tranh tài nguyên, tốc độ mạng, batch kế cận hoặc dữ liệu không đồng đều | Đo nhiều lần trên dữ liệu và lịch tải tương đương |

**Ví dụ:** CPU của ứng dụng mới dùng 25%, nhưng DB ở mức I/O và lock wait cao. Tăng bốn lần số luồng tại ứng dụng có thể làm DB chậm hơn, gây timeout và làm tổng thời gian job tăng. Trong trường hợp này cần xử lý nút thắt SQL, phân trang, index, khối lượng ghi hoặc lịch truy cập DB trước.

## 4. Spring Batch có những hướng mở rộng nào?

Không có một cấu hình concurrency phù hợp cho mọi job. Cách chọn phụ thuộc vào **đơn vị công việc có thể chạy độc lập**, mối quan hệ giữa các step, giới hạn nguồn/đích và mức phức tạp có thể vận hành.

| Mô hình | Đơn vị chạy đồng thời | Khi nào có ích | Điều kiện/rủi ro đáng chú ý |
| --- | --- | --- | --- |
| **Multi-threaded step** | Nhiều chunk/tác vụ trong cùng một step | Item độc lập, một step đang chậm và tài nguyên còn dư | Reader/Writer, state và thứ tự xử lý phải an toàn khi nhiều thread truy cập |
| **Parallel steps** | Các step/flow độc lập trong một job | Nhiều nhánh nghiệp vụ không phụ thuộc nhau | Không rút ngắn được một step dài đơn lẻ; phải quản lý phụ thuộc đúng |
| **Local partitioning** | Nhiều StepExecution xử lý các phần dữ liệu trên một máy | Dữ liệu chia rõ theo ID, ngày, file hoặc vùng | Chia partition không chồng lấn, cân bằng tải, định danh ổn định khi restart |
| **Remote partitioning** | Nhiều worker xử lý partition trên nhiều tiến trình/máy | Cần mở rộng vượt giới hạn một JVM | Điều phối, kết nối, trạng thái worker, lỗi mạng, lưu trạng thái và restart |
| **Remote chunking** | Manager đọc và gửi chunk để worker xử lý/ghi | Muốn phân tán phần xử lý/ghi nhưng có thể tập trung khâu đọc | Nút thắt ở manager, messaging, xử lý lại thông điệp, idempotency |

### 4.1. Multi-threaded step: tăng concurrency trong một bước

Trong mô hình này, một step cho phép nhiều thread xử lý các chunk. Điều này có thể cải thiện throughput nếu item độc lập và các thành phần chịu được truy cập đồng thời.

Tuy nhiên, **ItemReader có trạng thái** (ví dụ giữ cursor, offset hoặc vị trí trong file) thường không mặc nhiên thread-safe; **ItemWriter** có thể giữ buffer hay tài nguyên dùng chung. Chỉ cấu hình TaskExecutor là chưa đủ. Một bean có **step scope** cũng không tự động trở nên an toàn khi nhiều thread cùng dùng **một StepExecution**. Cần kiểm tra từng implementation, đồng bộ nơi thích hợp hoặc chọn thiết kế partition với reader riêng.

Thứ tự item được xử lý và ghi có thể khác thứ tự đọc. Nếu nghiệp vụ yêu cầu thứ tự toàn cục, cần thiết kế đặc biệt hoặc cân nhắc giữ xử lý tuần tự.

### 4.2. Parallel steps: chạy song song các nhánh độc lập

Giả sử ba nhánh A, B, C mất lần lượt 30, 20 và 15 phút, không chia sẻ đầu ra và không phụ thuộc nhau:

- Chạy tuần tự: xấp xỉ **65 phút**.
- Chạy song song với đủ tài nguyên: thời gian lý tưởng gần **30 phút**, cộng chi phí điều phối.

Nếu B phải đọc dữ liệu do A tạo, B **không** độc lập và không nên được đặt song song với A. Chia flow phải tuân thủ thứ tự nghiệp vụ và trạng thái thất bại của từng nhánh.

### 4.3. Partitioning: chia một khối lượng dữ liệu thành nhiều phần

Thay vì một reader xử lý toàn bộ dữ liệu, manager chia input thành các partition và giao cho các StepExecution riêng. Ví dụ:

~~~text
Tập giao dịch theo ID
├── P1: [1, 2.000.000]
├── P2: [2.000.001, 4.000.000]
├── P3: [4.000.001, 6.000.000]
└── P4: [6.000.001, 8.000.000]
~~~

Mỗi partition có thể có reader, processor và writer riêng, với context chỉ ra vùng dữ liệu cần xử lý. Partition có thể chạy cục bộ hoặc phân phối đến worker ở máy khác.

Phải bảo đảm **không chồng lấn** và **không bỏ sót** vùng dữ liệu; tránh phân hoạch bằng offset trên tập dữ liệu đang thay đổi nếu offset có thể dịch chuyển. Chia theo ID ổn định, mốc thời gian đã chốt hoặc danh sách file cố định thường dễ lập luận hơn. Đừng giả định bốn partition sẽ chạy nhanh gấp bốn: partition có thể lệch kích thước, gặp điểm nóng DB hoặc tranh chấp tài nguyên.

### 4.4. Remote partitioning và remote chunking: phân tán theo hai cách khác nhau

~~~mermaid
flowchart TB
    subgraph RP[Remote partitioning]
      PM[Manager chia partition] --> PW1[Worker 1: read-process-write]
      PM --> PW2[Worker 2: read-process-write]
      PM --> PW3[Worker 3: read-process-write]
    end
    subgraph RC[Remote chunking]
      CM[Manager: read và gửi chunk] --> Q[Hệ thống messaging]
      Q --> CW1[Worker 1: process-write]
      Q --> CW2[Worker 2: process-write]
    end
~~~

Ở **remote partitioning**, mỗi worker phụ trách một phần input và có thể tự đọc, xử lý, ghi. Ở **remote chunking**, manager thường đảm nhiệm đọc và chuyển item/chunk cho worker qua messaging, nên throughput đọc và mạng của manager có thể trở thành nút thắt. Cả hai đều cần thiết kế xử lý khi worker mất kết nối, khi thông điệp được gửi lại và khi job restart.

**Lưu ý:** Spring Batch không tự biến một đoạn xử lý phụ thuộc vào dữ liệu tuần tự thành xử lý song song an toàn. Mô hình phân tán cũng không loại bỏ giới hạn của database, API hoặc hạ tầng lưu trữ chung.

## 5. Vì sao tăng số worker không làm tốc độ tăng tuyến tính?

Hãy xem xét giới hạn của phần việc không thể song song hóa bằng **định luật Amdahl**. Nếu tỷ lệ phần việc song song hóa được là **p** và có **k** đơn vị xử lý, tốc độ tăng lý tưởng tối đa xấp xỉ:

~~~text
Speedup = 1 / ((1 - p) + p / k)

Ví dụ: p = 0,9; k = 4
Speedup = 1 / (0,1 + 0,9/4) ≈ 3,08 lần
~~~

Ngay cả khi 90% công việc có thể chạy song song, bốn worker cũng chỉ đạt khoảng 3,08 lần trong mô hình lý tưởng này. Ngoài thực tế, tốc độ thường còn bị giảm bởi việc tạo task, chia partition, mở transaction, tranh chấp lock, truyền dữ liệu, GC, tải không cân bằng và retry.

Một giới hạn quan trọng khác là **năng lực của nguồn và đích dùng chung**. Giả sử bốn worker có thể xử lý tổng cộng 4.000 item/giây, nhưng DB chỉ ghi bền vững được 2.500 item/giây. Thông lượng đầu-cuối không thể duy trì ở 4.000 item/giây nếu không thay đổi thiết kế ghi hoặc nâng năng lực của DB. Tăng thêm worker sẽ tạo backlog, chiếm connection và có thể tăng rollback.

### Các giới hạn phải xác định trước

- **CPU:** chi phí xử lý trên mỗi item; số core và cạnh tranh với ứng dụng khác.
- **Bộ nhớ:** số chunk và buffer cùng tồn tại, heap, GC, dữ liệu nạp sẵn.
- **Connection pool:** tổng số kết nối đồng thời từ reader/writer/metadata, bao gồm các workload khác.
- **Database:** tốc độ query/commit, index, log, lock, IOPS và mức chịu tải ghi.
- **I/O và network:** giới hạn đọc file, băng thông, độ trễ hoặc số request song song.
- **Dịch vụ downstream:** quota, rate limit, timeout và khả năng chịu retry.
- **Bản chất dữ liệu:** độ lệch phân bố, điều kiện phụ thuộc, thứ tự xử lý và tác động chéo.

Nếu mục tiêu là xử lý 12 triệu item trong một giờ nhưng đích chỉ ghi được 2.500 item/giây, thì ngay cả pipeline hoàn toàn song song cũng cần ít nhất **80 phút** để ghi đủ dữ liệu (12.000.000 / 2.500 / 60). Phải tối ưu hoặc nâng năng lực đích, thay đổi cách ghi, hoặc điều chỉnh cửa sổ batch thay vì chỉ thêm thread.

## 6. An toàn dữ liệu và khả năng restart là một phần của scaling

Khi thêm concurrency, mức độ khó không nằm ở việc tạo thread mà nằm ở việc **mỗi item được xử lý đúng theo quy tắc nghiệp vụ**, kể cả khi một bước bị lỗi.

### 6.1. Thread safety và trạng thái dùng chung

Các biến đếm, collection, cursor, cache, buffer hoặc kết nối bị nhiều thread cùng sửa có thể gây race condition. Trước khi chạy multi-threaded step, cần xác định rõ:

1. Reader/Writer cụ thể có được tài liệu xác nhận thread-safe hay không.
2. Các thành phần có giữ trạng thái thay đổi qua từng lần gọi hay không.
3. Trạng thái checkpoint được lưu và khôi phục có tương thích với cách chạy đồng thời hay không.
4. Output có cần giữ thứ tự tuyệt đối hay chỉ cần kết quả đúng theo khóa nghiệp vụ.

Khóa đồng bộ có thể giúp bảo vệ một đoạn truy cập, nhưng cũng tuần tự hóa phần việc đó và làm giảm lợi ích scaling. **Partitioning với tài nguyên riêng cho từng partition** thường dễ kiểm soát hơn khi một reader vốn không phù hợp dùng chung.

### 6.2. Chunk transaction không đồng nghĩa toàn job là một transaction

Trong chunk-oriented processing, các chunk có thể commit theo từng giao dịch. Nếu job lỗi giữa chừng, một số chunk đã commit, chunk hiện tại có thể rollback; khi restart, một phần công việc có thể được thực hiện lại tùy cách lưu checkpoint và thiết kế nguồn dữ liệu. Tác động phụ bên ngoài transaction (gọi API, gửi email, gửi message) càng cần cơ chế xử lý trùng.

Một số cách giữ tính đúng đắn:

- Dùng **khóa nghiệp vụ ổn định**, unique constraint, upsert hoặc kiểm tra trạng thái xử lý phù hợp.
- Thiết kế thao tác ghi **idempotent**: thực hiện lại cùng một item không tạo tác động sai hoặc trùng dữ liệu.
- Chia partition có biên rõ ràng và không trùng; bảo đảm dataset đầu vào nhất quán trong thời gian chạy.
- Thiết lập retry có giới hạn, backoff hợp lý; phân biệt lỗi tạm thời với lỗi dữ liệu không thể tự phục hồi.
- Kiểm soát chính sách skip, và đối soát tổng số item thành công/bị lọc/bị lỗi thay vì chỉ nhìn trạng thái COMPLETED.

Không nên mặc định rằng bật retry hay dùng message broker sẽ tạo ra bảo đảm **exactly-once** cho mọi hệ thống. Cần đánh giá giao dịch, checkpoint, khả năng gửi lại thông điệp và side effect của từng thành phần.

### 6.3. Restart và vận hành phân tán

**JobRepository** lưu metadata thực thi của job/step, nhưng không thể thay thế thiết kế lưu trạng thái đúng của từng reader, writer và partition. Khi mở rộng, cần kiểm thử các tình huống: JVM bị dừng sau khi chunk commit, worker mất kết nối, lỗi DB lúc ghi, retry quá giới hạn và restart cùng tham số job.

Partition cần có tên/định danh và cách chia dữ liệu đủ ổn định để xác định phần đã hoàn thành, phần cần chạy lại. Chạy song song cũng đòi hỏi quan sát được trạng thái từng StepExecution, thời gian của các partition và lý do lỗi để hỗ trợ điều tra sự cố.

## 7. Cách lựa chọn hướng mở rộng theo tình huống

~~~mermaid
flowchart TD
    A[Đo baseline và xác định batch window] --> B{Nút thắt chính?}
    B -->|Query / write / downstream| C[Tối ưu nguồn hoặc đích và đo lại]
    B -->|Nhiều step độc lập| D[Xem xét parallel steps]
    B -->|Một step nặng, item độc lập| E{Có thể chia input ổn định?}
    E -->|Có| F[Xem xét partitioning]
    E -->|Khó chia nhưng thành phần an toàn| G[Xem xét multi-threaded step]
    E -->|Không an toàn / có thứ tự| H[Giữ tuần tự và tối ưu thuật toán]
    F --> I{Một máy đủ tài nguyên?}
    I -->|Có| J[Local partitioning]
    I -->|Không| K[Remote partitioning]
    B -->|Cần phân phối xử lý chunk| L[Đánh giá remote chunking và nút thắt manager]
~~~

Sơ đồ là định hướng ban đầu; quyết định cuối cùng phải dựa trên số liệu, điều kiện thread safety và kết quả thử nghiệm.

### Tình huống A: tổng hợp nhiều nguồn độc lập

Job sinh ba bộ báo cáo từ ba miền dữ liệu độc lập. Mỗi bước 20–40 phút và không sử dụng kết quả của nhau. **Parallel steps** là lựa chọn tự nhiên vì ranh giới độc lập đã nằm ở cấp step. Phải kiểm tra ba nhánh có tranh chấp DB và tài nguyên ghi hay không.

### Tình huống B: tính toán độc lập trên tập dữ liệu lớn

Một step tính phí theo từng tài khoản; dữ liệu có ID ổn định và mỗi tài khoản được xử lý độc lập. Chia thành các partition theo khoảng ID hoặc nhóm tài khoản giúp mỗi StepExecution giữ input riêng và có checkpoint riêng. Nếu một JVM đủ tài nguyên, thử **local partitioning** trước. Khi giới hạn máy thực sự đạt tới, mới cân nhắc **remote partitioning** với chi phí điều phối cao hơn.

### Tình huống C: đồng bộ qua API giới hạn tốc độ

Writer gọi một API chỉ chấp nhận 200 request/giây. Tám thread tạo ra 1.000 request/giây có thể khiến server trả 429, retry nhiều và job chậm hơn. Cần giới hạn tốc độ, gom request nếu API hỗ trợ, dùng backoff và đo throughput thực. **Thêm worker không giúp vượt qua quota của bên nhận.**

## 8. Quy trình triển khai scaling có thể kiểm chứng

Một quá trình mở rộng đáng tin cậy thường theo vòng lặp:

1. **Chốt mục tiêu đo được:** khối lượng dữ liệu, batch window, throughput đích, giới hạn lỗi và yêu cầu đối soát.
2. **Lấy baseline:** chạy trên dataset đại diện, lưu metrics của job/step, DB, JVM và downstream.
3. **Xác định nút thắt:** phân biệt công việc CPU-bound, I/O-bound, cạnh tranh DB, phụ thuộc thứ tự hoặc mất cân bằng dữ liệu.
4. **Sửa điểm bất hợp lý trước:** ví dụ tối ưu SQL, batch write, fetch/chunk size, thuật toán, index hoặc giảm gọi API thừa.
5. **Chọn mô hình concurrency:** step song song, chunk song song, partition cục bộ hoặc phân tán theo đúng ranh giới độc lập.
6. **Tăng tải có kiểm soát:** thử lần lượt các mức concurrency, đo thông lượng đầu-cuối, thời gian và tài nguyên; dừng khi lợi ích giảm hoặc lỗi tăng.
7. **Kiểm tra tính đúng đắn:** đối soát count và tổng nghiệp vụ, thử retry/restart, dừng bất ngờ và xử lý lặp.
8. **Vận hành và giám sát:** cảnh báo job quá batch window, partition treo, pool cạn, lỗi downstream, rollback bất thường; lưu cấu hình có thể quay lại mức concurrency an toàn.

Ví dụ bảng ghi kết quả thử nghiệm cần có các cột **số worker**, **thời gian job**, **item/giây**, **CPU**, **độ trễ DB**, **rollback/retry** và **sai lệch đối soát**. Chỉ tăng số worker nếu mức tăng throughput và độ ổn định thực tế đủ thuyết phục.

## 9. Những nhầm lẫn phổ biến

| Nhận định dễ mắc | Điều cần nhớ |
| --- | --- |
| “Cứ tăng số thread là nhanh gấp tương ứng.” | Phần việc tuần tự, overhead và tài nguyên chung giới hạn speedup. |
| “CPU còn thấp nghĩa là có thể tăng thread.” | DB, network, lock hoặc quota downstream có thể đã là nút thắt. |
| “Dùng step scope là mọi reader đều thread-safe.” | Trong multi-threaded step, nhiều thread vẫn có thể cùng truy cập một instance thuộc cùng StepExecution. |
| “Có JobRepository là không thể ghi trùng khi restart.” | Checkpoint, transaction, side effect và thiết kế idempotent vẫn phải được kiểm tra. |
| “Nhiều partition thì chắc chắn cân bằng tải.” | Chi phí mỗi item và phân bố dữ liệu có thể rất lệch. |
| “Remote processing luôn tốt hơn local.” | Messaging, networking, giám sát, lỗi phân tán và vận hành có chi phí riêng. |

## 10. Ghi nhớ khi bắt đầu học scaling operations

Hãy trả lời bốn câu hỏi trước khi triển khai: **(1)** Job đang trễ so với yêu cầu nào? **(2)** Số liệu cho thấy công đoạn hay tài nguyên nào là nút thắt? **(3)** Phần việc nào thực sự độc lập và có thể chạy đồng thời? **(4)** Khi một phần xử lý lỗi hoặc chạy lại, dữ liệu có còn chính xác không?

Khi trả lời được bốn câu hỏi đó, việc chọn **multi-threaded step**, **parallel steps**, **partitioning** hay một mô hình **phân tán** trở thành quyết định kiến trúc dựa trên bằng chứng. Scaling tốt làm tăng năng lực xử lý trong giới hạn tài nguyên thực tế, đồng thời vẫn đáp ứng yêu cầu thread safety, retry/restart, đối soát và vận hành job lâu dài.
