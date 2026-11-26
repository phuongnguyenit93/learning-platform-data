# DataSource pool theo số worker

**Chương:** Resource pool  
**Module học:** SPRING_BATCH_SCALING_OPERATIONS

Khi mở rộng Spring Batch bằng **multi-threaded step**, **parallel steps**, **partitioning** hoặc các worker phân tán, số tác vụ có thể cùng truy cập cơ sở dữ liệu thường tăng. Tuy nhiên, tăng số worker không đồng nghĩa cơ sở dữ liệu có thể phục vụ số truy vấn đồng thời không giới hạn. Trong một hệ thống có **DataSource connection pool**, mỗi tác vụ cần lấy kết nối từ pool trước khi thực hiện thao tác JDBC; nếu thiếu kết nối, tác vụ có thể phải đợi, timeout hoặc kích hoạt retry không cần thiết.

Bài này giải thích cách **tính và kiểm chứng kích thước DataSource pool theo số worker**, nhận diện nút thắt giữa thread pool, connection pool và database, cũng như cấu hình và vận hành an toàn trong Spring Batch. Mục tiêu là đạt thông lượng phù hợp batch window mà vẫn giữ được **thread safety, retry/restart và tính đúng đắn của dữ liệu** trong giới hạn CPU, RAM, I/O và số kết nối thực tế.

## 1. Ba loại tài nguyên cần phân biệt

Trong một job xử lý dữ liệu lớn, cần phân biệt các tầng concurrency:

| Tầng tài nguyên | Chức năng | Giới hạn điển hình |
| --- | --- | --- |
| **Worker / thread pool** | Quy định bao nhiêu tác vụ Batch có thể thực thi đồng thời | Số thread trong JVM, số worker/replica trong cụm |
| **DataSource connection pool** | Cấp phát và tái sử dụng kết nối JDBC cho các tác vụ | Kích thước pool, số kết nối đang mượn, thời gian chờ |
| **Database server** | Thực thi SQL, commit transaction và duy trì connection/session | Cấu hình max connections, CPU, RAM, IOPS, lock, transaction log |

Một thread đang chạy **không nhất thiết** sử dụng kết nối JDBC trong toàn bộ vòng đời; nó có thể đang tính toán trên CPU, chờ API hoặc đang xử lý dữ liệu trong bộ nhớ. Ngược lại, một thread **có thể cần nhiều hơn một kết nối** trong một số thiết kế, ví dụ đọc và ghi qua hai DataSource, mở transaction độc lập bằng REQUIRES_NEW hoặc giữ cursor trong khi thao tác trên connection khác.

Vì vậy, hai kết luận đều sai nếu áp dụng máy móc:

- “Sáu worker thì pool luôn phải là sáu.”
- “Pool càng lớn thì job càng nhanh.”

Cấu hình đúng phụ thuộc vào **bao nhiêu connection được giữ cùng lúc**, thời gian giữ connection, số lần chạy song song và ngân sách kết nối của DB.

### Luồng cấp phát kết nối

~~~mermaid
flowchart LR
    A["Spring Batch: các chunk / partition / step"] --> B["Worker thread(s)"]
    B --> C["DataSource pool (ví dụ HikariCP)"]
    C --> D[("Database")]
    D --> C
    C --> B
~~~

Khi worker gọi một thao tác cần JDBC, nó yêu cầu kết nối từ pool. Nếu có connection sẵn, worker dùng connection đó theo vòng đời transaction và trả lại pool sau khi hoàn tất công việc tương ứng. Nếu toàn bộ connection trong pool đang được sử dụng, yêu cầu mới phải chờ tối đa đến ngưỡng được cấu hình, hoặc nhận lỗi timeout.

Cần nhớ **trả connection về pool không phải là đóng kết nối vật lý tới DB**. Pool giữ lại các connection còn hợp lệ để tái sử dụng cho những tác vụ tiếp theo.

## 2. Các cách Spring Batch làm tăng nhu cầu kết nối

### 2.1. Multi-threaded step

Khi một step cho phép nhiều thread xử lý chunk, nhiều transaction có thể cùng đọc/ghi DB. Ví dụ pool có tối đa 8 connection, nhưng executor cho phép 24 task hoạt động đồng thời và mỗi task đều cần một connection trong cùng khoảng thời gian; 16 task có thể phải chờ.

**Lưu ý về thread safety:** mở rộng step bằng nhiều thread không tự làm cho ItemReader/ItemWriter có trạng thái trở nên an toàn. Reader dựa trên cursor hoặc vị trí file có thể đòi hỏi đồng bộ hoặc thiết kế khác. Việc tăng pool chỉ giải quyết một phần nhu cầu JDBC, không giải quyết race condition của state.

### 2.2. Parallel steps

Hai step chạy song song có thể dùng chung một DataSource trong một JVM. Nếu step A có 5 tác vụ truy cập DB và step B có 4 tác vụ, áp lực kết nối cực đại có thể gần **9**, chưa kể job metadata hay các hoạt động khác. Không nên tính pool chỉ theo số worker của step lớn nhất khi các step có thể cùng chạy.

### 2.3. Local partitioning

Mỗi partition có một StepExecution với vùng dữ liệu riêng. Nếu cấu hình executor cho phép 6 partition chạy đồng thời, tối đa 6 partition có thể đang giữ connection, hoặc nhiều hơn tùy reader/transaction. Grid size 100 có thể tạo 100 partition nhưng **không có nghĩa 100 partition đang chạy cùng lúc**: nhu cầu pool phải dựa vào concurrency thực tế của executor và các job khác.

### 2.4. Remote partitioning

Mỗi worker JVM hoặc container thường có DataSource pool **riêng**. Nếu có 4 replica, mỗi replica cấu hình maximumPoolSize = 12, toàn bộ nhóm worker có khả năng mở tối đa **48 connection**, chưa kể manager và các dịch vụ khác.

Vì thế cần tính tổng ở cấp **cụm**, không chỉ nhìn file cấu hình của một pod. Ngoài ra, remote partitioning thường cần truy cập JobRepository được chia sẻ để quản lý StepExecution; nếu metadata và dữ liệu nghiệp vụ dùng chung một database, cả hai đều tiêu thụ ngân sách kết nối của database ấy.

### 2.5. Remote chunking

Trong remote chunking, manager thường đọc dữ liệu và gửi chunk, còn worker xử lý/ghi. Nhu cầu kết nối được phân bố theo vai trò:

- Manager có thể giữ connection để đọc nguồn, cập nhật metadata và quản lý trạng thái.
- Worker có thể cần connection để ghi đích và thực hiện những truy vấn nghiệp vụ bổ sung.
- Nếu manager và worker dùng **các database khác nhau**, phải tính ngân sách riêng cho từng database.

Tăng số worker xử lý chunk không nâng throughput nếu **manager đọc quá chậm**, database ghi đã bão hòa hoặc broker đang nghẽn.

## 3. Định nghĩa các biến trước khi tính pool

Hãy bắt đầu với một DataSource cụ thể trên **một instance ứng dụng**:

| Biến | Ý nghĩa |
| --- | --- |
| \(T\) | Số tác vụ có thể đồng thời cần truy cập DataSource này; xét tất cả job/step đang cùng chạy |
| \(c\) | Số connection lớn nhất mà một tác vụ có thể giữ đồng thời từ **chính DataSource này** |
| \(H\) | Khoảng dự phòng cho JobRepository, tác vụ quản trị, health check hoặc hoạt động JDBC ngoài những task đã tính |
| \(M\) | Giới hạn connection tối đa dự định cấu hình cho pool của instance |
| \(R\) | Số instance/replica có pool tương tự |
| \(B_{\mathrm{db}}\) | Ngân sách connection mà database dành được cho toàn bộ nhóm ứng dụng Batch |

Một **ước lượng cận trên theo concurrency** cho một pool là:

\[
M_{\text{ước lượng}} \approx T \times c + H
\]

Đây là **điểm bắt đầu để lập kế hoạch**, không phải công thức tối ưu tuyệt đối. Tài nguyên có thể được tái sử dụng theo thời gian, nên connection hoạt động thực tế có thể thấp hơn. Nhưng nếu đặt pool quá nhỏ so với lúc các transaction chồng lấn, các worker sẽ chờ lấy connection và thông lượng có thể giảm.

Một nguyên tắc bổ sung cho nhiều instance cùng dùng một DB:

\[
\sum_{i=1}^{N} M_i \le B_{\mathrm{db}}
\]

Trong đó \(M_i\) là giới hạn connection của **từng pool** kết nối đến database này, gồm manager, worker và các dịch vụ batch khác. Nếu các instance cùng dùng cấu hình \(M\), tổng giới hạn của chúng là \(R \times M\). Cần cộng **mọi pool đi tới cùng DB**, kể cả khi chúng nằm trong nhiều ứng dụng hoặc nhiều DataSource bean.

Ngân sách kết nối khả dụng cho Batch có thể ước lượng như sau:

\[
B_{\mathrm{db}} =
C_{\text{giới hạn DB}}
- C_{\text{dịch vụ khác}}
- C_{\text{dự phòng vận hành}}
\]

Không phải cứ database cho phép 100 connection là Batch được sử dụng cả 100. Những kết nối phục vụ giao dịch trực tuyến, quản trị, migration, tác vụ bảo trì hoặc dịch vụ dùng chung cần được dành chỗ.

> **Phân biệt giới hạn cấu hình và số đang dùng:** \(M\) là mức pool *có thể* mở tối đa; connection thực tế có thể thấp hơn. Tuy nhiên, khi thiết kế worst case và triển khai tăng replica, phải tính theo giới hạn để tránh trường hợp mọi pool cùng mở đến mức tối đa.

## 4. Ví dụ tính pool theo số worker

### 4.1. Một JVM chạy sáu worker

Giả sử một job xử lý độc lập từng nhóm giao dịch:

- Executor cho phép **6** tác vụ xử lý đồng thời.
- Mỗi tác vụ ở thời điểm đỉnh giữ **1 connection** đến database nghiệp vụ.
- Dự phòng **2 connection** cho thao tác Batch metadata và hoạt động DB khác trên cùng pool.

Ước lượng ban đầu:

\[
M \approx 6 \times 1 + 2 = 8
\]

Vậy **maximumPoolSize = 8** là một cấu hình thí nghiệm hợp lý, **nếu** quan sát và kiểm thử cho thấy giả định \(c=1\) thực sự đúng. Nếu reader giữ connection dài hạn và writer phải mở connection thứ hai từ cùng pool, hoặc một nhánh nghiệp vụ sử dụng REQUIRES_NEW, \(c\) có thể lớn hơn 1 và cần tính lại.

### 4.2. Bốn replica worker cùng một database

Tiếp tục ví dụ trên, triển khai **4 worker instance**, mỗi instance có pool tối đa **8** connection. Manager có một pool riêng tối đa **4** connection, tất cả cùng kết nối tới một database:

| Thành phần | Số instance | Pool tối đa/instance | Connection tối đa tổng |
| --- | ---: | ---: | ---: |
| Worker | 4 | 8 | 32 |
| Manager | 1 | 4 | 4 |
| **Tổng Batch** | | | **36** |

Giả sử DB có ngưỡng tối đa 80 connection, hệ thống online có thể cần 22 connection và muốn giữ 14 connection làm dự phòng:

\[
B_{\mathrm{db}} = 80 - 22 - 14 = 44
\]

Tổng giới hạn Batch là **36**, còn dư 8 connection so với ngân sách 44. Đây mới là **đánh giá khả thi sơ bộ**. Để chốt, phải chạy workload đại diện và theo dõi connection đang sử dụng, thời gian đợi pool, độ trễ SQL và lock contention.

Nếu mở rộng từ 4 lên 8 worker instance mà vẫn giữ pool size 8, giới hạn kết nối sẽ thành:

\[
8 \times 8 + 4 = 68
\]

Mức 68 vượt quá ngân sách 44 dù chưa tính các pool khác, nên không thể tự động scale replica mà không kiểm tra lại DB. Có thể giảm worker, giảm concurrency/pool mỗi replica, chia thời gian chạy hoặc nâng năng lực database khi có bằng chứng.

### 4.3. Nếu một worker cần hai connection đồng thời

Giả sử mỗi worker có thể giữ hai connection từ cùng DataSource, ví dụ một transaction ngoài đã giữ connection, trong khi một thao tác **REQUIRES_NEW** cần connection độc lập. Với 6 worker hoạt động đồng thời:

\[
M_{\text{ước lượng}} \approx 6 \times 2 + 2 = 14
\]

Nếu giữ bốn replica và manager như trước, tổng mức tối đa thành \(4 \times 14 + 4 = 60\), vượt ngân sách 44. Lúc này phải thay đổi concurrency, cách mở transaction hoặc số replica; chỉ tăng pool mỗi worker sẽ chuyển nút thắt xuống DB.

**Đặc biệt với REQUIRES_NEW:** một transaction ngoài có thể giữ connection trong khi transaction trong xin connection khác. Nếu mọi thread cùng giữ connection ngoài và chờ connection trong, pool có nguy cơ bế tắc chờ tài nguyên. Cần thiết kế đủ dư địa hoặc xem xét lại ranh giới transaction; đừng khắc phục bằng retry vô hạn.

## 5. Số worker không phải lúc nào cũng bằng số connection đang bận

Hai workload có cùng sáu worker nhưng nhu cầu kết nối rất khác nhau:

- **Workload A:** mỗi item tốn 90 ms xử lý CPU, chỉ cần 10 ms để ghi DB. Connection được mượn gần thời điểm ghi; sáu worker có thể hiếm khi cùng giữ connection.
- **Workload B:** mỗi item cần 10 ms tính toán, nhưng transaction giữ kết nối 300 ms vì truy vấn/giao tiếp chậm. Sáu worker thường xuyên chồng lấn thời gian giữ connection.

Khả năng sử dụng pool phụ thuộc vào **thời gian connection bị giữ**. Một ước lượng hữu ích dựa trên định luật Little, khi workload ổn định, là:

\[
L \approx \lambda \times W
\]

Trong đó:

- \(L\): số connection đang được mượn **trung bình**.
- \(\lambda\): số hoạt động DB/transaction hoàn thành mỗi giây, tính theo cùng đơn vị với \(W\).
- \(W\): thời gian trung bình một hoạt động giữ connection, tính bằng giây.

Ví dụ một job đạt 2.400 item/giây, chunk size 100, và giả định mỗi chunk có một khoảng giữ connection trung bình 0,20 giây:

\[
\lambda = 2400 / 100 = 24\ \text{chunk/giây}
\]

\[
L \approx 24 \times 0{,}20 = 4{,}8\ \text{connection}
\]

Con số 4,8 là **mức bận trung bình**, không phải kích thước pool tối đa cần cấu hình. Đỉnh tải, variance của độ trễ, các truy vấn metadata, partition khác và connection giữ kéo dài đều có thể khiến nhu cầu tức thời cao hơn. Công thức cũng không đúng nếu quy đổi nhầm item/giây thành transaction/giây khi một item phát sinh nhiều transaction.

### Hiểu đúng về chunk size

Chunk size ảnh hưởng đến số lần commit, dữ liệu cần giữ trong bộ nhớ và có thể ảnh hưởng đến thời gian giữ connection. Nó **không** trực tiếp quy định số kết nối tối đa.

- Chunk quá nhỏ có thể làm tăng overhead commit và cập nhật metadata.
- Chunk quá lớn có thể làm transaction kéo dài, tăng áp lực lock, log, heap hoặc chi phí rollback.
- Cùng chunk size nhưng SQL nhanh/chậm khác nhau dẫn đến nhu cầu pool khác nhau.

Thay đổi chunk size cần được đo cùng throughput, thời gian transaction, memory và lock; không chỉ đo số chunk đã hoàn thành.

## 6. Cấu hình HikariCP trong ứng dụng Spring Batch

HikariCP là connection pool phổ biến trong ứng dụng Spring Boot. Với một ứng dụng worker dùng **một DataSource** được Spring Boot tự cấu hình, ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/batchdb
    username: batch_worker
    # Lấy mật khẩu từ hệ thống secret phù hợp, không ghi trực tiếp vào tài liệu.
    hikari:
      pool-name: batch-worker-pool
      maximum-pool-size: 8
      minimum-idle: 2
      connection-timeout: 30000
~~~

Ở đây:

| Thuộc tính | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| \`maximum-pool-size: 8\` | Số connection vật lý tối đa pool có thể duy trì, gồm đang bận và đang rảnh | Không phải giới hạn số worker hay toàn bộ DB |
| \`minimum-idle: 2\` | Mục tiêu giữ một số connection nhàn rỗi để sẵn phục vụ yêu cầu | Các instance nhiều replica vẫn có thể chiếm kết nối nhàn rỗi |
| \`connection-timeout: 30000\` | Thời gian tối đa chờ mượn connection trước khi báo lỗi, đơn vị ms với cấu hình Hikari này | Timeout không giải quyết nguyên nhân nghẽn pool |
| \`pool-name\` | Tên pool hỗ trợ đọc metrics/log | Nên đặt tên phân biệt vai trò hoặc DataSource |

Địa chỉ DB và tên đăng nhập trong ví dụ là giá trị minh họa. Trong triển khai thực tế, dùng cấu hình môi trường và secret manager tương ứng.

**Chú ý:** nếu tự cấu hình nhiều DataSource bean, các thuộc tính dưới \`spring.datasource.hikari\` không tự nhiên áp dụng cho mọi pool. Mỗi DataSource phải có cấu hình riêng theo cách binding của ứng dụng.

### Giới hạn executor và pool phải được cân nhắc cùng nhau

Ví dụ khai báo executor với tối đa sáu thread trong Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BatchWorkerExecutorConfig {

    @Bean
    public ThreadPoolTaskExecutor batchWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(6);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("batch-worker-");
        executor.initialize();
        return executor;
    }
}
~~~

Đây là cấu hình **executor độc lập**, chưa tự gắn nó vào Step. Ứng dụng còn phải cấu hình mô hình Spring Batch cụ thể (multi-threaded step, local partitioning hoặc flow) để sử dụng executor. Khi pool có 8 connection và executor có 6 thread, chỉ nên kết luận là **có dư địa 2 connection theo giả định mỗi task cần một connection**; không có bảo đảm mọi Reader/Writer hoặc các JobExecution khác đều dùng đúng một connection.

**Tránh nhầm lẫn:** việc khai báo một bean TaskExecutor không tự tăng thông lượng job. Nên kiểm tra nơi executor thực sự được nối vào step, số task đang hoạt động và trạng thái chờ kết nối.

## 7. Dữ liệu nghiệp vụ và JobRepository có thể dùng các pool khác nhau

Một ứng dụng Spring Batch có thể dùng:

1. **DataSource nghiệp vụ:** reader/writer truy cập nguồn và đích.
2. **DataSource metadata:** JobRepository ghi JobExecution, StepExecution và ExecutionContext.
3. **DataSource khác:** tra cứu tham chiếu, audit hoặc báo cáo.

Việc có **bao nhiêu pool** phụ thuộc cấu hình. Nếu tất cả cùng trỏ về một database vật lý, giới hạn kết nối của các pool vẫn cộng dồn tại DB đó. Nếu kết nối đến các database khác nhau, phải tính ngân sách cho từng server/cluster độc lập.

~~~mermaid
flowchart TB
    W["Worker JVM: 6 tác vụ chạy đồng thời"]
    W --> DP["Pool nghiệp vụ: max 8"]
    W --> JP["Pool JobRepository: max 3"]
    DP --> DB1[("DB nghiệp vụ")]
    JP --> DB2[("DB metadata")]
~~~

Sơ đồ minh họa hai database khác nhau. Nếu cả hai pool trỏ vào cùng một DB server, tổng giới hạn từ JVM này là 11 connection đến server đó. Khi nhân số replica, tổng giới hạn tương ứng cũng nhân theo.

### Hai điểm đặc biệt của JobRepository

- Khi số partition hoặc chunk và tần suất commit tăng, số thao tác metadata cũng tăng. Một pool dành cho metadata quá nhỏ có thể làm job chờ checkpoint/commit dù database nghiệp vụ vẫn còn dư năng lực.
- **Không được giả định** metadata luôn cần một connection riêng đang giữ đồng thời với connection nghiệp vụ. Điều này tùy cấu hình transaction manager, DataSource và cách các bước thực thi. Hãy đo acquisition thực tế và dùng mô hình cận trên khi đánh giá worst case.

Nếu thiết kế yêu cầu đồng bộ thay đổi trên hai DB riêng biệt, việc có hai pool không tự tạo transaction nguyên tử liên DB. Cần xác định ranh giới transaction, cơ chế đối soát và cách phục hồi phù hợp.

## 8. Đo pool để biết đang thiếu kết nối hay DB đã bão hòa

Trước khi đổi pool size, cần quan sát trong một lần chạy có dữ liệu đại diện.

| Chỉ số cần đo | Ý nghĩa | Khi nào đáng chú ý |
| --- | --- | --- |
| **Active / in-use connections** | Kết nối đang được ứng dụng mượn | Thường xuyên chạm giới hạn pool |
| **Idle connections** | Kết nối rảnh trong pool | Idle nhiều nhưng throughput thấp gợi ý nút thắt khác |
| **Pending / waiting threads** | Số yêu cầu đang đợi mượn kết nối | Liên tục lớn hơn 0, nhất là đi kèm timeout |
| **Connection acquire time** | Thời gian từ lúc xin đến lúc lấy được connection | Tăng mạnh khi pool hết kết nối |
| **Connection usage/hold time** | Thời gian một thao tác giữ connection | Dài do truy vấn/transaction nặng, network hoặc khóa DB |
| **Connection timeout count** | Số lần chờ mượn connection quá thời hạn | Có tác động trực tiếp tới retry, thất bại hoặc dừng step |
| **DB active sessions / lock waits** | DB đang bận thực thi và chờ khóa ra sao | DB có thể đã quá tải dù pool vẫn tăng được |
| **Job throughput, commit, rollback, retry** | Hiệu quả và tính ổn định của Batch | Tăng pool nhưng throughput giảm hoặc rollback tăng |

Nếu ứng dụng tích hợp Micrometer/Spring Boot Actuator và Hikari được bật metrics, có thể quan sát các metric Hikari cho connection active, idle, pending, max và timeout theo tên/cách export tương ứng. Mỗi worker instance cần có nhãn để phân biệt số liệu; sau đó tổng hợp theo job/step/pod để xác định điểm nghẽn ở cấp cụm.

### Nhận diện các kịch bản phổ biến

**Kịch bản A — pool cạn, DB còn dư:** active liên tục bằng maximumPoolSize, pending tăng, nhưng DB CPU và lock waits thấp. Có thể thử tăng pool một mức nhỏ **nếu còn ngân sách connection ở DB**; đồng thời kiểm tra connection có bị giữ quá lâu hay có leak không.

**Kịch bản B — pool tăng nhưng DB quá tải:** pending trong pool giảm nhưng CPU DB, lock wait, transaction latency tăng và throughput không cải thiện. Tăng pool đang chuyển hàng đợi từ ứng dụng xuống DB. Cần tối ưu SQL/index, giảm số tác vụ đồng thời hoặc điều chỉnh phạm vi partition.

**Kịch bản C — idle nhiều, job vẫn chậm:** pool không phải nút thắt chính; hãy đo CPU Processor, độ trễ API, tốc độ reader, phân bố partition và broker backlog.

**Kịch bản D — timeout sau nhiều phút dù chỉ vài worker:** kiểm tra transaction không kết thúc, reader streaming giữ connection dài, ngoại lệ khiến connection không được trả đúng cách, hoặc thao tác blocking diễn ra **bên trong transaction**.

**Kịch bản E — tất cả replica chậm sau autoscaling:** mỗi replica tự tạo pool, khiến tổng connection và truy vấn cùng tăng. Có thể DB hoặc metadata repository bị bão hòa dù metrics của từng JVM trông không bất thường.

### Quy trình phân tích một timeout khi xin connection

1. Ghi nhận thời điểm lỗi, pool nào bị timeout và thông lượng job khi đó.
2. So sánh active/idle/pending tại thời điểm lỗi; xác định có thật sự cạn pool không.
3. Xem DB sessions, transaction đang mở, câu SQL chậm và lock waits.
4. Kiểm tra số job/step/partition đồng thời, số replica mới và các workload khác đang dùng DB.
5. Điều tra transaction quá dài hoặc connection leak; không đổi timeout trước khi biết nguyên nhân.
6. Thử nghiệm thay đổi một biến mỗi lần, kiểm tra throughput, ổn định và đối soát dữ liệu.

## 9. Pool size, timeout và retry có quan hệ như thế nào?

Một worker đợi quá lâu để mượn connection có thể phát sinh lỗi từ DataSource và khiến chunk rollback hoặc step thất bại tùy nơi lỗi xuất hiện và cấu hình fault tolerance. Việc đặt **connectionTimeout** thật cao không làm tăng tài nguyên: nó chỉ khiến nhiều thread có thể đợi lâu hơn trước khi báo lỗi.

Ngược lại, đặt timeout quá ngắn có thể phát sinh lỗi ngay khi database bị tăng latency tạm thời. Cần chọn timeout dựa trên SLO thực tế và kết quả đo thời gian chờ.

### Vì sao retry có thể khuếch đại nghẽn?

~~~mermaid
flowchart TD
    A["Nhiều worker mượn connection"] --> B["Pool đầy / DB chậm"]
    B --> C["Connection timeout hoặc transaction lỗi"]
    C --> D["Retry nếu được cấu hình"]
    D --> E["Thêm yêu cầu truy cập DB"]
    E --> B
~~~

Khi lỗi có nguyên nhân là thiếu capacity, retry lập tức từ nhiều worker có thể làm tình trạng nặng hơn. Những biện pháp thường có ích gồm:

- Retry **có giới hạn** với backoff, phân biệt lỗi tạm thời và lỗi dữ liệu.
- Giới hạn concurrency hoặc tạm giảm số partition thực thi đồng thời khi DB căng tải.
- Thiết kế tác động ghi có tính **idempotent**, vì chunk có thể được xử lý lại sau rollback/restart.
- Kiểm tra thời điểm transaction bắt đầu để tránh giữ connection trong lúc gọi API chậm hoặc xử lý CPU dài không cần transaction.
- Điều chỉnh kích thước chunk và batch write trên cơ sở số liệu, không chỉ dựa trên cảm giác.

**Không nên mặc định** lỗi xin connection là một lỗi nghiệp vụ được phép skip. Bỏ qua một chunk do hết connection có thể làm thiếu dữ liệu cần xử lý; cần có chính sách lỗi và đối soát rõ ràng.

## 10. Những trường hợp cần đặc biệt lưu ý

### 10.1. Reader dùng cursor hoặc streaming

Một số reader đọc bằng cursor hoặc stream có thể giữ connection trong khoảng thời gian dài. Nếu writer hoặc truy vấn bổ sung cần connection độc lập, nhu cầu có thể cao hơn số worker. Cách cấp phát connection và transaction của reader phụ thuộc implementation; hãy kiểm tra tài liệu của reader cụ thể và đo trạng thái pool khi chạy.

Nếu một Reader có trạng thái được dùng chung giữa nhiều thread, vấn đề **thread safety** không được giải quyết bằng cách tăng pool. Partitioning với Reader theo từng StepExecution thường giúp phân định trạng thái rõ ràng hơn.

### 10.2. Transaction lồng nhau và REQUIRES_NEW

Với transaction ngoài giữ connection mà một nhánh nghiệp vụ mở transaction mới, nhiều task có thể đồng thời đòi thêm connection. Pool size bằng đúng số thread có thể làm chúng cùng chờ nhau. Khi thiết kế cần xét **số connection tối đa đang giữ cùng lúc**, hoặc tránh mở transaction mới ở vị trí gây cạnh tranh cao.

### 10.3. Nhiều job chồng lấn

Job A có 8 thread và job B có 6 thread không nhất thiết yêu cầu pool 14 nếu lịch chạy không bao giờ chồng lấn. Nhưng nếu hai job **có thể cùng hoạt động** khi retry, chạy bù hoặc restart, sizing phải dựa trên kịch bản đồng thời thực sự được phép. Chỉ dựa vào lịch bình thường của scheduler sẽ bỏ sót tình huống sự cố.

### 10.4. Số replica thay đổi tự động

Kubernetes HPA hoặc hệ thống autoscaling có thể tăng worker khi queue dài. Nếu mỗi replica có pool max 10, tăng từ 3 lên 12 replica có thể tăng giới hạn kết nối worker từ 30 lên 120. Trước khi bật autoscaling, cần có **ngân sách DB ở mức số replica cực đại**, concurrency limit và cơ chế bảo vệ downstream.

### 10.5. DB proxy và pool ở nhiều tầng

Nếu ứng dụng dùng proxy hoặc connection pool phía database, số client connection phía ứng dụng không luôn bằng số backend connection trên DB. Khả năng multiplex phụ thuộc transaction, session state, prepared statements và cấu hình proxy. Cần đo cả hai phía; không giả định proxy biến DB thành tài nguyên vô hạn.

### 10.6. Pool idle cũng tiêu thụ tài nguyên

Kết nối idle vẫn có thể chiếm slot connection, bộ nhớ và tài nguyên session ở database. Trong cụm có hàng chục replica, cấu hình minimumIdle cao gây áp lực dù job chưa chạy. Ngược lại, minimumIdle quá thấp có thể tăng thời gian khởi tạo connection khi burst; hãy đo và chọn mức cân bằng.

## 11. Quy trình sizing theo số liệu thực tế

Một quy trình phù hợp cho Spring Batch scaling operations:

1. **Xác định khối lượng và batch window:** ví dụ 12 triệu bản ghi trong 90 phút, có dự phòng cho restart hoặc một vài partition bị chậm.
2. **Liệt kê nguồn dùng connection:** reader, writer, JobRepository, lookup, audit, từng manager/worker và từng database đích.
3. **Đặt giới hạn concurrency ban đầu:** số step chạy song song, số thread của mỗi executor, số partition đang xử lý và số replica cực đại.
4. **Ước lượng pool trên từng instance:** dùng \(T \times c + H\), kiểm tra khả năng giữ nhiều connection đồng thời.
5. **Kiểm tra tổng quota DB:** tính \(\sum M_i\) trên mọi pool/replica, trừ lưu lượng online và dự phòng.
6. **Chạy baseline đại diện:** ghi throughput, elapsed time, active/idle/pending, acquire/hold time, DB waits và rollback.
7. **Tăng một yếu tố mỗi lần:** ví dụ giữ worker = 6 và thử pool = 6/8/10, hoặc giữ pool cố định rồi thay số worker trong giới hạn DB.
8. **Chọn cấu hình có lợi ích thực:** loại bỏ cấu hình chỉ giảm pending nhưng không cải thiện throughput hoặc làm DB quá tải.
9. **Kiểm tra fault tolerance:** thử worker restart, retry, mất DB tạm thời, chồng lấn job và đối soát sau chạy lại.
10. **Giám sát khi vận hành:** đặt cảnh báo theo thời gian chờ connection, pool timeout, DB saturation và batch window; đánh giá lại khi thay số replica hoặc khối lượng dữ liệu.

### Ví dụ bảng kết quả đo thử nghiệm

Giả sử cùng một nguồn DB, cùng workload và cùng cách chia partition; bảng dưới đây chỉ là **số liệu minh họa**, không phải benchmark của Spring Batch:

| Concurrency | Pool max/instance | Throughput (item/giây) | Pending ở đỉnh | Quan sát |
| ---: | ---: | ---: | ---: | --- |
| 4 | 4 | 900 | 3 | Chờ pool ở một số thời điểm |
| 4 | 6 | 1.020 | 0 | Cải thiện nhẹ, DB ổn |
| 6 | 8 | 1.480 | 0–1 | Cân bằng giữa concurrency và DB |
| 8 | 10 | 1.510 | 0 | Lợi ích nhỏ, DB bắt đầu căng |
| 12 | 14 | 1.420 | 0 | Lock waits/DB latency tăng |

Tăng pool từ 8 lên 14 không đảm bảo tăng throughput. Nếu database đã thành nút thắt, nhiều connection có thể khiến queue nằm bên trong DB và transaction giữ lock lâu hơn.

Khi so sánh các lần chạy, hãy giữ **dữ liệu thử, khối lượng tác vụ, phiên bản job, cấu hình transaction và tải nền** nhất quán nhất có thể. Đối soát số item thành công và kết quả nghiệp vụ ở mỗi lần chạy để tránh kết luận “nhanh hơn” chỉ vì đã bỏ sót bản ghi.

## 12. Tình huống thiết kế thực tế

Một hệ thống đối soát có các thành phần:

- **Manager** chia dữ liệu thành 48 partition theo dải ID.
- **6 worker pod**, mỗi pod tối đa **4 partition chạy đồng thời**.
- Các worker truy cập một PostgreSQL dùng chung để đọc/ghi và cập nhật metadata.
- DB cũng phục vụ API trực tuyến; nhóm vận hành chỉ cho phép Batch sử dụng tối đa **50 connection** tính cả manager.
- Manager có pool tối đa **4 connection**.

Với 6 pod, ngân sách worker là \(50 - 4 = 46\) connection. Nếu mỗi pod đặt pool 8 connection, toàn bộ worker có giới hạn \(6 \times 8 = 48\), cộng manager thành 52, **vượt ngân sách**.

Có thể thử pool **7 connection/pod** trước, cho tổng \(6 \times 7 + 4 = 46\), vẫn trong ngân sách 50. Tuy nhiên, cần kiểm tra trường hợp bốn partition đồng thời ở một pod có thể giữ hơn một connection/partition hay không. Nếu thực tế cần đến 2 connection/partition, mức 7 có nguy cơ nghẽn; lúc đó lựa chọn đúng có thể là **giảm số partition đồng thời hoặc số pod**, thay đổi transaction boundaries hay cấp thêm ngân sách DB, thay vì chỉ ép pool vào một giới hạn thiếu thực tế.

~~~mermaid
flowchart LR
    M["Manager pool: 4"]
    W1["Worker pod 1 pool: 7"]
    W2["Worker pod 2 pool: 7"]
    W3["Worker pod 3 pool: 7"]
    W4["Worker pod 4 pool: 7"]
    W5["Worker pod 5 pool: 7"]
    W6["Worker pod 6 pool: 7"]
    DB[("DB: ngân sách Batch 50 connections")]

    M --> DB
    W1 --> DB
    W2 --> DB
    W3 --> DB
    W4 --> DB
    W5 --> DB
    W6 --> DB
~~~

**Phép tính:** \(4 + 6 \times 7 = 46\) connection tối đa theo cấu hình, còn dư 4 connection trong ngân sách Batch. Mức dư này có thể cần tăng nếu workload khác sử dụng cùng DB hoặc retry/restart làm thay đổi concurrency; việc kiểm chứng bằng metrics vẫn bắt buộc.

### Một quyết định khác khi ngân sách DB không tăng được

Nếu chỉ có thể dành 32 connection cho Batch, manager cần 4, còn worker tối đa 28 connection. Hệ thống có thể cân nhắc:

- **4 pod, pool 7/pod:** 28 cho worker, 4 cho manager, tổng 32.
- **7 pod, pool 4/pod:** cũng tổng 32, nhưng nếu mỗi pod đang chạy 4 partition và cần connection cho metadata, pool 4 có thể gây chờ.
- **Giữ 6 pod nhưng giảm concurrency mỗi pod:** giảm áp lực DB; chỉ nên chọn kích thước pool sau khi đo số connection đang giữ.

Với cùng ngân sách, nhiều pod hơn **không tự động tạo thêm năng lực DB**. Lựa chọn phải dựa vào phần chi phí CPU/IO nào có thể song song hóa mà không tăng quá mức số transaction cạnh tranh.

## 13. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Worker = pool size là công thức cố định.” | Cần xem các worker giữ connection bao lâu, có mở nhiều connection cùng lúc không và có job khác chạy chung không. |
| “Pool 20 trên mỗi pod nghĩa là DB dùng tối đa 20 connection.” | Giới hạn mỗi pod nhân với số replica, cộng tất cả manager và pool khác cùng DB. |
| “Tăng maximumPoolSize luôn tăng throughput.” | Nếu database đã bão hòa, throughput có thể đứng yên hoặc giảm. |
| “Không có pending nghĩa là database không nghẽn.” | Pool có thể đủ rộng nhưng SQL/lock/IO tại DB vẫn quá tải. |
| “Tăng connectionTimeout sẽ xử lý được thiếu capacity.” | Timeout chỉ đổi thời gian chờ trước khi lỗi; cần tìm nút thắt thực tế. |
| “Chunk size bằng 100 thì pool phải có 100 connection.” | Chunk size quyết định số item/giao dịch, không phải số transaction chạy đồng thời. |
| “Partition grid size 100 nghĩa là 100 connection đang dùng.” | Số partition đang hoạt động phụ thuộc executor và worker; grid size không trực tiếp là concurrency. |
| “Retry khi hết connection luôn vô hại.” | Retry có thể làm nghẽn thêm và tạo replay của tác động nghiệp vụ. |
| “Pool dành cho JobRepository không đáng kể.” | Khi nhiều step/partition hoặc tần suất commit cao, metadata có thể trở thành điểm nghẽn riêng. |
| “Đã dùng remote worker thì không còn race condition.” | Cạnh tranh SQL, khóa nghiệp vụ và ghi trùng vẫn xảy ra qua tài nguyên dùng chung. |

## 14. Checklist trước khi chốt cấu hình

- [ ] Có thông lượng mục tiêu, batch window và dữ liệu thử đại diện.
- [ ] Đã liệt kê tất cả job, step và replica **có thể thực thi đồng thời**.
- [ ] Đã xác định DataSource nào truy cập DB nào, kể cả JobRepository.
- [ ] Đã phân tích số connection có thể giữ cùng lúc trong transaction, Reader/Writer và REQUIRES_NEW.
- [ ] Tổng giới hạn pool của toàn cụm nằm trong ngân sách DB có dự phòng.
- [ ] Đã đo active/idle/pending, acquire/hold time, DB waits và throughput.
- [ ] Đã thử tăng/giảm pool và worker riêng rẽ để xác định nút thắt thực.
- [ ] Đã kiểm tra thread safety, tính idempotent và kết quả khi retry/restart.
- [ ] Có cảnh báo pool timeout, transaction quá dài, DB saturation và batch window bị vượt.
- [ ] Đã kiểm tra giới hạn số replica tối đa và tài nguyên khi autoscaling.

## 15. Ghi nhớ

**DataSource pool theo số worker** là bài toán cân bằng giữa năng lực thực thi đồng thời của Spring Batch và khả năng phục vụ transaction của database. Worker/thread quyết định tiềm năng tạo tải; pool điều tiết số connection có thể được mượn; database và các hệ thống downstream mới quyết định mức thông lượng bền vững.

Hãy bắt đầu bằng mô hình **số tác vụ đồng thời × số connection giữ cùng lúc + dự phòng**, rồi cộng giới hạn của **tất cả replica và các pool** kết nối đến cùng DB. Sau đó dùng metrics để điều chỉnh: pool thiếu sẽ gây pending/timeout, còn pool dư có thể tăng tranh chấp và không cải thiện thời gian job.

Trong Spring Batch scaling operations, một cấu hình tốt phải đồng thời đáp ứng **batch window, thread safety, đúng dữ liệu, retry/restart có kiểm soát và ngân sách tài nguyên thực tế**. Đó mới là tiêu chí để quyết định có nên tăng worker hay pool, thay vì chạy theo một con số connection lớn nhất.
