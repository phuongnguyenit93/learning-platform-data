# Kiểm kê tài nguyên và xác định thành phần chịu trách nhiệm quản lý

Khi chuẩn bị một ứng dụng Java cho CRaC (Coordinated Restore at Checkpoint), nhóm phát triển cần biết tiến trình đang giữ những tài nguyên nào và thành phần nào chịu trách nhiệm quản lý từng tài nguyên. Một ứng dụng có thể dùng hàng chục thư viện, framework và client bên ngoài. Mỗi thành phần có thể tạo socket, connection pool, thread nền, file handle, timer, cache hoặc trạng thái phụ thuộc môi trường. Nếu bỏ sót một tài nguyên, ứng dụng có thể restore thành công ở cấp tiến trình nhưng thất bại khi xử lý request đầu tiên.

**Kiểm kê tài nguyên** (*resource inventory*) là quá trình lập danh sách có cấu trúc về những tài nguyên và trạng thái có ảnh hưởng đến checkpoint/restore. **Xác định owner** là việc gắn từng mục trong danh sách với thành phần có đủ hiểu biết và quyền kiểm soát để chuẩn bị tài nguyên trước checkpoint, phục hồi nó sau restore và xác minh nó hoạt động.

Owner có thể là một bean của ứng dụng, một adapter do nhóm phát triển viết, một thư viện, một framework hoặc một thành phần nền tảng. Điều quan trọng là trách nhiệm phải rõ ràng: ai dừng việc sử dụng tài nguyên, ai đóng hoặc giải phóng nó, ai tạo lại, và ai ngăn ứng dụng nhận traffic khi phục hồi chưa hoàn tất.

## 1. Vì sao phải kiểm kê tài nguyên trước khi dùng CRaC?

Checkpoint lưu trạng thái của một tiến trình tại một thời điểm. Một số trạng thái trong heap có thể tiếp tục được sử dụng sau restore, nhưng nhiều tài nguyên gắn với hệ điều hành hoặc dịch vụ bên ngoài có thể đã hết hiệu lực, thay đổi hoặc không được phép dùng lại. Ví dụ, kết nối TCP có thể bị peer đóng, token có thể hết hạn, DNS có thể thay đổi, hoặc thread nền có thể đang giữ một giao dịch dở dang.

Khi chưa có danh sách tài nguyên, nhóm thường chỉ phát hiện vấn đề sau khi restore: request đầu tiên gặp lỗi database, worker không nhận message, cổng HTTP không bind được hoặc scheduler chạy trùng. Những lỗi này khó truy nguyên nếu không biết thành phần nào tạo và sở hữu tài nguyên.

Kiểm kê giúp nhóm:

- Biết ứng dụng đang mở hoặc giữ những tài nguyên nào, kể cả tài nguyên do thư viện tạo ra gián tiếp.
- Phân biệt trạng thái có thể giữ lại với trạng thái cần đóng, làm mới hoặc tạo lại.
- Giao trách nhiệm cho đúng component, tránh nhiều thành phần cùng đóng hoặc cùng khởi tạo một tài nguyên.
- Xác định thứ tự phối hợp giữa các thành phần phụ thuộc nhau.
- Thiết kế callback CRaC có thể kiểm soát, quan sát và kiểm thử.
- Tạo tiêu chí readiness sau restore dựa trên những tài nguyên thiết yếu.

Kiểm kê không chỉ là đếm socket hay thread. Một giá trị trong bộ nhớ cũng cần được xem xét nếu nó chứa thông tin phụ thuộc môi trường hoặc có thời hạn, chẳng hạn token, địa chỉ instance, timestamp, lease hoặc trạng thái bộ sinh số ngẫu nhiên.

## 2. Tài nguyên và trạng thái cần đưa vào phạm vi kiểm kê

Một cách hữu ích là chia đối tượng cần kiểm tra thành các nhóm. Cách phân loại này giúp tránh chỉ tập trung vào những tài nguyên nhìn thấy được ở cấp hệ điều hành.

| Nhóm | Ví dụ | Rủi ro khi restore |
|---|---|---|
| Kết nối mạng | Socket, HTTP client, TLS session, database connection, broker channel | Kết nối đã đóng, session hết hạn hoặc endpoint thay đổi |
| File và hệ điều hành | File descriptor, file handle, thư mục tạm, lock file, memory-mapped file | Đường dẫn, mount, quyền hoặc trạng thái handle không còn phù hợp |
| Thread và thực thi nền | Executor, worker, thread pool, event loop | Thread đang xử lý dở, giữ lock hoặc không tiếp tục đúng cách |
| Lịch và thời gian | Timer, scheduler, deadline, lease, tác vụ định kỳ | Lịch cũ bị chạy bù hoặc tác vụ được kích hoạt nhiều lần |
| Dữ liệu xác thực | Token, credential, secret, chứng thư | Hết hạn, bị thu hồi hoặc không còn đúng với instance |
| Cấu hình và danh tính | Hostname, IP, port, instance ID, node metadata | Nhiều instance dùng chung danh tính hoặc cấu hình cũ |
| Cache và metadata | DNS cache, cache nghiệp vụ, ORM metadata, serializer cache | Dữ liệu hết hạn, lỗi thời hoặc cần đồng bộ giữa replica |
| Trạng thái đồng bộ | Lock, semaphore, transaction, session, consumer offset | Trạng thái dở dang hoặc không còn tương ứng với dịch vụ ngoài |
| Nguồn ngẫu nhiên | PRNG state, seed, ID generator | Các tiến trình restore tạo chuỗi giống nhau hoặc ID trùng |
| Thư viện native | Native handle, context của thư viện C/C++, GPU/device handle | Tài nguyên native không có vòng đời tương thích với checkpoint |

Không phải mọi mục trong bảng đều cần đóng trước checkpoint. Một số chỉ cần xác minh, một số cần làm mới sau restore, một số có thể giữ nguyên. Mục tiêu của kiểm kê là xác định hành động cụ thể dựa trên bản chất tài nguyên và tài liệu của thành phần tạo ra nó.

## 3. Phân biệt tài nguyên, trạng thái bộ nhớ và dữ liệu nghiệp vụ

Ba khái niệm này thường đan xen nhưng cần được ghi nhận riêng.

**Tài nguyên runtime** là thứ mà tiến trình sử dụng để tương tác với môi trường hoặc thực hiện công việc: socket, file handle, connection pool, executor, timer hoặc native handle. Nó thường có quy trình tạo, sử dụng và giải phóng rõ ràng.

**Trạng thái bộ nhớ** là dữ liệu nằm trong heap hoặc cấu trúc runtime. Ví dụ, cache, cấu hình đã parse, bộ đếm, metadata và trạng thái của đối tượng. Một phần có thể tái sử dụng; một phần cần làm mới vì đã cũ hoặc gắn với instance.

**Dữ liệu nghiệp vụ** là thông tin có ý nghĩa đối với hệ thống và thường phải được lưu ở nguồn bền vững như database hoặc message broker. Không nên coi checkpoint của một tiến trình là cơ chế lưu trữ chính cho giao dịch hoặc công việc nghiệp vụ. Nếu một request đang cập nhật database dở dang khi checkpoint xảy ra, cần bảo đảm giao dịch được hoàn tất hoặc rollback theo thiết kế.

Ví dụ với một ứng dụng thương mại điện tử:

| Đối tượng | Phân loại | Câu hỏi cần trả lời |
|---|---|---|
| `HikariDataSource` | Tài nguyên runtime | Pool được đóng và tạo lại bởi component nào? |
| Danh sách mã sản phẩm trong cache | Trạng thái bộ nhớ | Dữ liệu có bất biến hoặc còn mới sau restore không? |
| `instanceId` | Trạng thái cấu hình/danh tính | Giá trị có cần khác nhau cho từng replica không? |
| Giao dịch tạo đơn hàng | Dữ liệu nghiệp vụ | Giao dịch đã commit hay rollback trước checkpoint chưa? |
| Scheduled executor | Tài nguyên runtime và lịch | Ai dừng scheduler, ai khởi động lại và có nguy cơ chạy trùng không? |

Phân loại đúng giúp tránh một sai lầm phổ biến: cố gắng giải quyết mọi vấn đề bằng cách đóng một đối tượng Java. Có những trường hợp cần làm mới dữ liệu, có trường hợp cần đồng bộ với hệ thống ngoài, và có trường hợp cần bảo đảm tính nhất quán nghiệp vụ.

## 4. Owner của tài nguyên là ai?

Owner là thành phần chịu trách nhiệm cho toàn bộ vòng đời của tài nguyên trong phạm vi mà nó kiểm soát. Owner cần hiểu tài nguyên được tạo thế nào, ai đang sử dụng nó, khi nào có thể dừng, cách giải phóng an toàn và điều kiện để tạo lại.

Owner không nhất thiết là nơi chứa biến tham chiếu đến tài nguyên. Ví dụ, một service có thể nhận `DataSource` qua dependency injection nhưng không phải owner của connection pool nếu pool được tạo và quản lý bởi cấu hình hạ tầng hoặc thư viện. Component sở hữu pool mới là nơi hiểu cách đóng và tạo lại nó.

Một số kiểu owner thường gặp:

| Kiểu owner | Ví dụ | Trách nhiệm điển hình |
|---|---|---|
| Application component | Service tự mở file hoặc tạo executor | Định nghĩa cách dừng, đóng và tạo lại tài nguyên |
| Infrastructure/configuration component | Bean tạo `DataSource`, HTTP client hoặc scheduler | Quản lý vòng đời đối tượng được inject cho nhiều service |
| Library/framework integration | Driver, framework hoặc thư viện có CRaC integration | Thực hiện quy trình được nhà cung cấp hỗ trợ |
| Platform/orchestrator | Container runtime, secret provider, service discovery | Cấp phát hoặc cung cấp lại tài nguyên ở cấp môi trường |
| External service | Database, broker, API server | Quản lý tài nguyên phía server; ứng dụng vẫn phải quản lý client và kết nối của mình |

Hãy gán một owner chính cho mỗi tài nguyên. Những component khác có thể là consumer hoặc dependency, nhưng không nên tự ý đóng tài nguyên mà chúng chỉ đang sử dụng.

## 5. Nguyên tắc xác định owner

### 5.1. Bắt đầu từ nơi tạo tài nguyên

Tìm nơi gọi API tạo hoặc mở tài nguyên, chẳng hạn `new`, `open`, `connect`, `build`, `start` hoặc factory method. Ghi lại component tạo nó và nơi tham chiếu được lưu giữ. Đây thường là manh mối đầu tiên để tìm owner.

Tuy nhiên, nơi tạo không phải lúc nào cũng là owner cuối cùng. Một factory có thể chuyển quyền quản lý cho container hoặc framework. Cần theo dõi việc chuyển giao đó và đọc hợp đồng vòng đời của thư viện.

### 5.2. Xác định ai có quyền dừng việc sử dụng

Đóng một socket khi nhiều thread vẫn đang ghi dữ liệu có thể làm request lỗi. Dừng một executor khi tác vụ đang giữ transaction có thể để lại trạng thái không nhất quán. Vì vậy, owner cần biết các consumer và có cách ngăn họ bắt đầu công việc mới trước khi giải phóng tài nguyên.

Nếu component tạo tài nguyên không kiểm soát được consumer, hãy xác định một coordinator chịu trách nhiệm quiesce các consumer trước. Coordinator điều phối thứ tự; owner tài nguyên vẫn thực hiện thao tác đóng và mở lại.

### 5.3. Ưu tiên tích hợp CRaC có sẵn

Một số framework, driver hoặc thư viện đã cung cấp CRaC integration. Khi đó, thư viện có thể tự đăng ký resource và quản lý chi tiết nội bộ mà ứng dụng không nên can thiệp. Hãy xác minh phiên bản và phạm vi hỗ trợ. Không đăng ký thêm một resource thứ hai để đóng cùng tài nguyên nếu tích hợp thư viện đã quản lý nó.

Nếu thư viện không có tích hợp, nhóm ứng dụng có thể viết adapter hoặc wrapper để phối hợp vòng đời. Adapter nên dùng API công khai của thư viện và giữ trách nhiệm trong một nơi.

### 5.4. Tách owner khỏi coordinator

Trong ứng dụng lớn, một thành phần trung tâm có thể cần điều phối nhiều resource. Coordinator chịu trách nhiệm bắt đầu quá trình chuẩn bị và xác định khi nào hệ thống đủ điều kiện checkpoint. Mỗi owner chịu trách nhiệm chi tiết với tài nguyên của mình.

Ví dụ: coordinator yêu cầu HTTP server ngừng nhận request, yêu cầu consumer dừng nhận message, chờ các giao dịch hoàn tất, rồi yêu cầu các owner đóng kết nối. Coordinator không nên tự đóng từng socket nội bộ mà không hiểu hợp đồng của các thư viện.

## 6. Xác định owner trong ứng dụng Java thực tế

Một cuộc kiểm kê tốt thường kết hợp nhiều cách tìm kiếm. Không nên chỉ đọc mã nguồn vì một số tài nguyên được tạo tự động bởi framework hoặc thư viện native.

### 6.1. Đọc cấu hình khởi tạo và dependency injection

Kiểm tra các cấu hình tạo bean, factory, client và pool. Với Spring, xem các lớp `@Configuration`, `@Bean`, component khởi tạo, lifecycle method và cấu hình auto-configuration. Xác định bean nào được tạo, scope của bean và ai đóng bean khi context shutdown.

Ví dụ:

```java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return ExternalClient.builder().build();
    }
}
```

Trong ví dụ, `ClientConfiguration` tạo và đăng ký bean; container quản lý lifecycle bean theo cấu hình. `ExternalClient` là đối tượng được tạo. Khi tích hợp CRaC, cần xác định component nào có thể đóng và tạo lại client, và cách những service đang dùng client được phối hợp trong giai đoạn checkpoint/restore.

### 6.2. Tìm API tạo và giải phóng tài nguyên

Tìm trong mã nguồn các thao tác như:

- `Socket`, `ServerSocket`, `SocketChannel`, `FileChannel`, `Files.new...`.
- `DataSource`, `Connection`, `HttpClient`, broker client và driver.
- `ExecutorService`, `ScheduledExecutorService`, `Thread`, timer và scheduler.
- API mở file, native library, device hoặc memory-mapped resource.
- `close()`, `shutdown()`, `stop()`, `disconnect()`, `dispose()` và các phương thức tương tự.

Đối chiếu nơi tạo với nơi giải phóng. Nếu không tìm thấy nơi đóng, đó là dấu hiệu cần điều tra. Nếu nhiều nơi cùng đóng, cần xác định nơi nào thực sự sở hữu vòng đời và loại bỏ việc quản lý chồng chéo.

### 6.3. Đọc tài liệu thư viện và framework

Một framework có thể tạo tài nguyên bên trong mà mã ứng dụng không gọi trực tiếp. Ví dụ, web server tạo listening socket và event loop; ORM tạo connection pool hoặc cache metadata; thư viện messaging tạo heartbeat thread và network channel.

Đọc tài liệu của đúng phiên bản dependency để xác định:

- Tài nguyên nào được tạo tự động.
- Framework quản lý lifecycle theo cách nào.
- Có CRaC integration chính thức hay không.
- Phiên bản nào hỗ trợ và có giới hạn gì.
- Cách bật/tắt integration hoặc đăng ký callback theo khuyến nghị.

Không suy luận khả năng CRaC từ việc một thư viện có phương thức `close()`. Đóng được tài nguyên khi shutdown không đồng nghĩa với việc thư viện đã hỗ trợ đầy đủ checkpoint/restore.

### 6.4. Quan sát tài nguyên ở runtime

Khi có thể, chạy ứng dụng trong môi trường kiểm thử và quan sát những gì tiến trình đang giữ. Dùng công cụ hệ điều hành và công cụ JVM để xem thread, socket, file descriptor, stack trace, log khởi tạo và hoạt động của thư viện.

Các nguồn quan sát có thể gồm:

- Thread dump để tìm worker, scheduler, event loop và thread đang chờ.
- JFR hoặc profiler để hiểu hoạt động thread, I/O và allocation.
- Công cụ hệ điều hành để liệt kê socket, file handle, PID và giới hạn tài nguyên.
- Log startup/shutdown của framework và driver.
- Metric của connection pool, broker client, executor và HTTP server.

Ảnh chụp runtime chỉ phản ánh trạng thái ở thời điểm quan sát. Hãy quan sát ở startup, sau warm-up, khi có tải và trước checkpoint để phát hiện tài nguyên chỉ xuất hiện khi một đường đi nghiệp vụ được gọi.

## 7. Mẫu resource inventory

Một bảng kiểm kê cần đủ thông tin để một người khác có thể hiểu tài nguyên, owner và hành động cần thực hiện. Mẫu dưới đây có thể được dùng làm điểm bắt đầu:

| Trường | Nội dung cần ghi |
|---|---|
| Resource ID | Tên định danh duy nhất trong tài liệu kiểm kê |
| Resource/type | Loại tài nguyên hoặc trạng thái cần quản lý |
| Creator | Component hoặc thư viện tạo tài nguyên |
| Owner | Thành phần chịu trách nhiệm lifecycle |
| Consumers | Những thành phần đang sử dụng tài nguyên |
| Scope | Toàn tiến trình, theo instance, theo request hay theo tác vụ |
| Lifetime | Khi nào tạo, khi nào hết hiệu lực và khi nào đóng |
| External dependency | Dịch vụ, file, endpoint hoặc thiết bị liên quan |
| Before checkpoint | Dừng, drain, flush, đóng, giữ nguyên hay không áp dụng |
| After restore | Tạo lại, làm mới, xác minh hay không áp dụng |
| Ordering/dependency | Những resource hoặc component cần sẵn sàng trước/sau |
| Failure behavior | Hành vi khi đóng/mở lại thất bại |
| Verification | Log, metric, health check hoặc phép thử xác nhận |

Ví dụ một phần inventory cho dịch vụ Java:

| Resource ID | Creator / Owner | Before checkpoint | After restore | Xác minh |
|---|---|---|---|---|
| `db-pool` | Database configuration / `DataSource` owner | Ngừng cấp connection mới, chờ tác vụ xong, đóng pool theo integration | Tạo pool mới và kiểm tra database | Pool active, query kiểm tra thành công |
| `http-server` | Web framework / server lifecycle owner | Ngừng nhận request, drain request đang chạy, xử lý listening socket theo integration | Khôi phục server/listener theo cơ chế được hỗ trợ | Readiness endpoint và request thử thành công |
| `broker-consumer` | Messaging configuration / consumer owner | Pause, xử lý hoặc hoàn tác message dở dang, đóng client nếu cần | Tạo client mới, subscribe hoặc join group | Consumer hoạt động và offset hợp lệ |
| `scheduler` | Scheduling configuration / scheduler owner | Ngừng trigger mới, chờ tác vụ hoàn tất, dừng scheduler | Tạo lịch theo chính sách instance/leader | Metric số job đang chạy và trạng thái leader |
| `instance-config` | Runtime configuration component | Không lưu danh tính riêng của tiến trình chuẩn bị | Đọc instance ID, địa chỉ và secret mới | Log identity và cấu hình đã xác minh |
| `local-cache` | Cache component | Giữ cache nền hoặc flush theo chính sách | Làm mới phần có TTL hoặc dữ liệu theo instance | Hit/miss, timestamp và tính hợp lệ dữ liệu |

Đây chỉ là ví dụ minh họa. Owner thật phải được xác định từ cấu trúc ứng dụng và hợp đồng thư viện đang dùng. Không sao chép tên component trong bảng vào hệ thống mà chưa xác nhận chúng tồn tại.

## 8. Đánh giá hành động cho từng tài nguyên

Sau khi xác định owner, hãy chọn hành động cụ thể. Một cách phân loại đơn giản gồm bốn nhóm:

| Chiến lược | Khi nào phù hợp | Ví dụ |
|---|---|---|
| Giữ nguyên và xác minh | Trạng thái hợp lệ qua checkpoint, không gắn với môi trường thay đổi | Metadata bất biến đã parse |
| Đóng trước, tạo lại sau | Tài nguyên phụ thuộc socket, peer hoặc môi trường hiện tại | Database connection, HTTP client có kết nối mạng |
| Giữ lại nhưng làm mới dữ liệu | Đối tượng còn dùng được nhưng chứa dữ liệu có thời hạn | Cache DNS, token, cấu hình động |
| Dừng và khởi động lại | Thành phần thực thi nền cần bắt đầu lại ở trạng thái sạch | Scheduler, consumer, worker pool |

Một số tài nguyên cần nhiều hành động. Ví dụ, consumer phải pause, chờ message đang xử lý, commit offset, đóng client, rồi tạo client mới và subscribe sau restore. Ghi rõ từng bước giúp tránh cách mô tả mơ hồ như “reset consumer”.

Đừng đóng tài nguyên chỉ vì nó xuất hiện trong inventory. Đóng không đúng thời điểm có thể làm mất request, transaction hoặc dữ liệu chưa flush. Owner cần có quy trình quiesce trước khi gọi thao tác đóng.

## 9. Xác định quan hệ phụ thuộc và thứ tự phối hợp

Tài nguyên thường có quan hệ phụ thuộc. Một request handler dùng service; service dùng repository; repository dùng connection pool. Một scheduler có thể gọi service và ghi database. Nếu đóng database pool trước khi scheduler ngừng chạy, scheduler có thể tiếp tục gọi vào pool đã đóng.

Vì vậy, inventory nên ghi cả quan hệ phụ thuộc:

```text
HTTP Server
    |
    v
Request Handler
    |
    v
Application Service
    |
    v
Repository ---------> Database Pool ---------> Database

Scheduler ----------> Application Service
Broker Consumer ----> Application Service
```

Khi chuẩn bị checkpoint, hệ thống thường ngừng nguồn tạo công việc trước (HTTP server, consumer, scheduler), chờ các công việc đang chạy kết thúc, rồi mới đóng những dependency mà chúng sử dụng (pool, client, file handle). Khi restore, các dependency cần sẵn sàng trước khi nguồn công việc được mở lại.

Thứ tự thực tế phụ thuộc framework, resource registration và cơ chế callback của bản CRaC đang sử dụng. Không nên tự giả định thứ tự callback giữa các resource nếu chưa kiểm tra tài liệu API. Nếu thứ tự có ý nghĩa, hãy dùng coordinator hoặc cấu trúc context được hỗ trợ để biểu diễn quan hệ, đồng thời kiểm thử thứ tự thực tế.

## 10. Đăng ký resource CRaC và giao trách nhiệm

CRaC API cung cấp `org.crac.Resource` để thành phần quản lý tài nguyên triển khai callback trước checkpoint và sau restore. `Core.getGlobalContext().register(...)` là một cách đăng ký resource với global context trong các môi trường hỗ trợ API tương ứng.

Ví dụ một owner quản lý file cần đóng và mở lại:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileResource implements Resource {
    private final Path path;
    private java.io.BufferedReader reader;

    public FileResource(Path path) throws IOException {
        this.path = path;
        this.reader = Files.newBufferedReader(path);
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        if (reader != null) {
            reader.close();
            reader = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        reader = Files.newBufferedReader(path);
    }
}
```

Ví dụ chỉ minh họa một file reader đơn giản. Trong ứng dụng thật, owner cần quyết định vị trí đọc tiếp, xử lý dữ liệu chưa tiêu thụ, quyền truy cập file sau restore và trường hợp file đã thay đổi hoặc không còn tồn tại. Nếu file là dữ liệu chỉ đọc, có thể mở lại từ đầu; nếu là stream có offset, cần lưu offset bền vững và xác minh tính nhất quán.

Mỗi resource nên được đăng ký đúng một lần cho mỗi tiến trình. Nếu bean được tạo nhiều lần hoặc context khởi tạo lặp, cần tránh đăng ký trùng. Nếu thư viện đã tự đăng ký resource, ứng dụng không nên tạo wrapper thứ hai đóng cùng tài nguyên mà không có thiết kế phối hợp rõ ràng.

## 11. Xử lý tài nguyên được chia sẻ giữa nhiều component

Một tài nguyên có thể được nhiều component sử dụng. Ví dụ, nhiều service cùng dùng một `DataSource`, nhiều handler dùng chung một HTTP client hoặc nhiều tác vụ dùng một executor.

Trong trường hợp này, owner thường là component tạo và quản lý tài nguyên dùng chung. Các consumer chỉ mượn tài nguyên theo hợp đồng. Khi checkpoint, owner không thể đóng tài nguyên ngay nếu consumer vẫn đang sử dụng.

Một cách tổ chức trách nhiệm:

| Vai trò | Trách nhiệm |
|---|---|
| Consumer | Ngừng bắt đầu công việc mới và hoàn tất công việc đang chạy |
| Coordinator | Yêu cầu các consumer quiesce, theo dõi trạng thái và điều phối giai đoạn checkpoint |
| Resource owner | Xác nhận không còn consumer hoạt động, đóng hoặc chuẩn bị tài nguyên |
| Restore coordinator | Khởi tạo dependency theo thứ tự và chỉ mở lại traffic khi đủ điều kiện |

Không để mỗi consumer tự đóng cùng một `DataSource`. Điều đó dễ dẫn đến đóng lặp, race condition hoặc consumer này làm hỏng hoạt động của consumer khác. Cần có một chủ thể duy nhất quản lý lifecycle tài nguyên dùng chung.

Nếu tài nguyên có thể được tái tạo nhanh và độc lập, có thể chọn thiết kế mỗi component sở hữu client riêng. Nhưng lựa chọn đó cần cân nhắc chi phí kết nối, giới hạn dịch vụ và yêu cầu pooling.

## 12. Xử lý tài nguyên do thư viện hoặc framework tạo tự động

Một phần lớn tài nguyên trong ứng dụng Java không xuất hiện trực tiếp trong mã nguồn nghiệp vụ. Framework có thể tạo server socket, event loop, thread pool, cache reflection, connection pool hoặc client nội bộ.

Với mỗi thư viện quan trọng, hãy ghi nhận:

1. Phiên bản đang dùng và tính năng CRaC integration được hỗ trợ.
2. Tài nguyên nào thư viện tạo tự động và phạm vi của chúng.
3. Component nào sở hữu lifecycle theo thiết kế thư viện.
4. Cách thư viện yêu cầu xử lý trước checkpoint và sau restore.
5. Các giới hạn đã biết, ví dụ không hỗ trợ một loại native handle hoặc yêu cầu cấu hình bổ sung.

Nếu có integration chính thức, dùng đúng phiên bản và cấu hình được khuyến nghị. Nếu không có, tìm API lifecycle công khai hoặc hỏi tài liệu của nhà cung cấp trước khi viết adapter. Tránh truy cập field private, reflection vào nội bộ hoặc gọi phương thức không được hỗ trợ chỉ để ép đóng tài nguyên.

Framework cũng có thể quản lý bean theo lifecycle riêng. Nếu CRaC integration được tích hợp với container, hãy để container quản lý đúng bean và thứ tự phụ thuộc. Nếu tự đăng ký callback bên ngoài container, cần bảo đảm các bean vẫn tồn tại và sẵn sàng khi callback chạy.

## 13. Những câu hỏi cần trả lời khi kiểm kê từng mục

Để tránh inventory chỉ là một danh sách tên, hãy trả lời một bộ câu hỏi nhất quán cho mỗi tài nguyên:

**Tạo và sở hữu:** Ai tạo tài nguyên? Owner chính là ai? Quyền sở hữu có được chuyển cho framework hoặc container không? Những component nào đang sử dụng nó?

**Phạm vi và vòng đời:** Tài nguyên thuộc toàn tiến trình, instance, request hay tác vụ? Nó được tạo khi startup, lần sử dụng đầu hay theo lịch? Điều gì làm nó hết hiệu lực?

**Checkpoint:** Tài nguyên có thể tồn tại qua checkpoint không? Cần dừng consumer, drain, flush, commit, đóng hoặc giải phóng điều gì? Có công việc dở dang hay lock đang được giữ không?

**Restore:** Ai tạo lại tài nguyên? Cần cấu hình hoặc danh tính riêng nào? Tài nguyên có thể được tạo lặp an toàn không? Có giới hạn rate hoặc quota ở dịch vụ bên ngoài không?

**Lỗi và readiness:** Nếu đóng hoặc mở lại thất bại thì ứng dụng xử lý thế nào? Có retry và timeout không? Metric hoặc health check nào chứng minh tài nguyên đã sẵn sàng? Ứng dụng có bị chặn nhận traffic khi resource thiết yếu chưa hoạt động không?

**Kiểm thử:** Có thể mô phỏng mất kết nối, hết hạn token, file biến mất, cổng bị chiếm hoặc callback lỗi không? Làm thế nào chứng minh không có side effect trùng?

## 14. Quy trình thực hiện resource inventory

Một quy trình thực tế có thể chia thành các bước sau.

### Bước 1: Xác định phạm vi ứng dụng

Liệt kê các module, framework, thư viện client, dịch vụ ngoài và thành phần nền. Bắt đầu với các luồng quan trọng như HTTP request, database, messaging, scheduled job và xử lý file. Ghi nhận cả những tính năng chỉ chạy khi có tải.

### Bước 2: Thu thập bằng chứng

Đọc cấu hình, factory, lifecycle method, dependency documentation và mã tạo tài nguyên. Kết hợp quan sát thread, socket, file descriptor và metric khi ứng dụng chạy. Ghi rõ nguồn bằng chứng cho mỗi mục để người khác có thể xác minh.

### Bước 3: Xác định owner và consumer

Với từng tài nguyên, truy ngược nơi tạo và nơi đóng. Liệt kê consumer, xác định ai có thể dừng việc sử dụng, và ai có đủ hiểu biết để tạo lại. Nếu có nhiều ứng viên owner, làm rõ ranh giới trách nhiệm trước khi viết callback.

### Bước 4: Phân loại hành động checkpoint/restore

Chọn giữ nguyên, đóng rồi tạo lại, làm mới dữ liệu hoặc dừng rồi khởi động lại. Ghi rõ điều kiện trước khi thực hiện và hành vi khi lỗi. Đánh dấu các mục cần kiểm tra với nhà cung cấp thư viện.

### Bước 5: Vẽ dependency và xác định coordinator

Biểu diễn component tạo công việc, component tiêu thụ tài nguyên và dependency. Xác định thứ tự quiesce, đóng, tạo lại và mở traffic. Chọn coordinator nếu nhiều component cần phối hợp.

### Bước 6: Triển khai integration và kiểm thử

Đăng ký resource theo API và framework được hỗ trợ. Kiểm thử callback, lỗi callback, restore nhiều lần và tình huống dịch vụ ngoài thay đổi. Kiểm tra cả log lẫn metric để xác nhận hành vi.

### Bước 7: Duy trì inventory

Resource inventory cần được cập nhật khi thêm dependency, nâng cấp framework, thay connection pool, thêm worker hoặc thay cách triển khai. Có thể đưa việc cập nhật inventory vào quy trình review các thay đổi ảnh hưởng lifecycle.

## 15. Ví dụ inventory cho một ứng dụng Spring Boot

Giả sử một dịch vụ Spring Boot có HTTP server, database, Redis cache, Kafka consumer và scheduled job. Inventory ban đầu có thể được tổ chức như sau:

| Tài nguyên | Nơi thường tạo | Owner cần xác minh | Hành động dự kiến |
|---|---|---|---|
| HTTP server và listening socket | Embedded server do Spring Boot khởi tạo | Web server lifecycle integration | Drain request và xử lý socket theo tích hợp CRaC |
| JDBC connection pool | Auto-configuration hoặc bean cấu hình datasource | Datasource/pool bean | Đóng pool trước checkpoint, tạo pool mới sau restore |
| Redis client | Bean cấu hình cache/client | Redis client bean hoặc thư viện có CRaC integration | Đóng kết nối cũ, tạo client/kết nối mới nếu cần |
| Kafka consumer | Listener container | Messaging framework/container | Pause, hoàn tất message, phục hồi subscription |
| Scheduled job | Spring scheduling hoặc scheduler riêng | Scheduling component | Ngừng trigger, khởi động theo chính sách leader/instance |
| Thread pool ứng dụng | Bean executor | Executor bean | Drain, shutdown có kiểm soát, tạo executor mới |
| Secret/token | Secret provider hoặc client xác thực | Configuration/credential component | Lấy hoặc làm mới credential sau restore |
| Cache metadata | Cache manager và ứng dụng | Cache component | Giữ phần bất biến, làm mới phần có TTL hoặc theo instance |

Không thể kết luận owner chỉ từ tên bean hoặc framework. Một số phiên bản có integration CRaC chính thức; phiên bản khác có thể cần cấu hình hoặc adapter. Hãy kiểm tra đúng phiên bản Spring Boot, driver và thư viện được dùng trong ứng dụng.

Một cách tổ chức là tạo một bảng trách nhiệm cho các nhóm:

| Nhóm | Người chịu trách nhiệm kỹ thuật | Bằng chứng cần bàn giao |
|---|---|---|
| Web và request lifecycle | Nhóm sở hữu web layer | Cách drain request, trạng thái server sau restore |
| Database và cache client | Nhóm sở hữu persistence/infrastructure | Cách đóng/mở pool và kiểm tra kết nối |
| Messaging | Nhóm sở hữu consumer/producer | Quy trình pause, offset và subscribe lại |
| Background jobs | Nhóm sở hữu scheduler/worker | Quy tắc leader, idempotency và restart |
| Runtime configuration | Nhóm sở hữu cấu hình và secret | Cách cấp identity, token và endpoint mới |

Việc gán người phụ trách trong nhóm giúp inventory có người duy trì. Trong mã nguồn, owner vẫn nên được thể hiện bằng component và ranh giới lifecycle cụ thể, không chỉ là tên cá nhân trong tài liệu.

## 16. Tiêu chí hoàn thành inventory

Một inventory có thể được xem là đủ dùng cho giai đoạn tích hợp khi:

- Các module và dependency quan trọng đã được xem xét, kể cả tài nguyên tạo tự động.
- Mỗi tài nguyên có creator, owner và consumer rõ ràng.
- Phạm vi, vòng đời và phụ thuộc môi trường được ghi nhận.
- Hành động trước checkpoint và sau restore được xác định.
- Các tài nguyên dùng chung có một owner lifecycle rõ ràng.
- Các dependency và thứ tự quiesce/restore được biểu diễn.
- Có cách xử lý khi callback thất bại và tiêu chí readiness.
- Có phép kiểm chứng cụ thể bằng log, metric, health check hoặc integration test.
- Các mục chưa rõ được ghi thành câu hỏi cần xác nhận với nhà cung cấp hoặc chủ sở hữu thư viện.

Không cần chờ mọi mục đều hoàn hảo mới bắt đầu thử nghiệm. Có thể đánh dấu mức độ tin cậy của từng mục: đã xác minh bằng tài liệu, đã xác minh bằng thử nghiệm, giả định cần kiểm tra hoặc chưa xác định. Cách này giúp nhóm ưu tiên những rủi ro lớn trước.

## 17. Những sai lầm thường gặp

**Chỉ kiểm kê tài nguyên do mã ứng dụng trực tiếp tạo.** Framework và thư viện có thể tạo socket, thread, cache và native handle. Hãy đọc tài liệu dependency và quan sát runtime.

**Cho rằng nơi giữ reference là owner.** Một service có thể chỉ dùng `DataSource` do configuration bean quản lý. Hãy tìm nơi tạo, hợp đồng lifecycle và nơi có quyền đóng/mở.

**Để nhiều component cùng đóng một tài nguyên.** Việc đóng lặp có thể gây race condition và lỗi khó đoán. Gán một owner chính, các consumer chỉ phối hợp dừng sử dụng.

**Bỏ qua consumer đang hoạt động.** Đóng pool hoặc client trong khi request còn chạy có thể làm mất giao dịch. Cần quiesce và drain trước khi giải phóng.

**Đăng ký CRaC Resource trùng với integration của thư viện.** Hai callback cùng đóng/mở một tài nguyên có thể tạo lỗi. Kiểm tra thư viện đã tự quản lý chưa trước khi viết adapter.

**Chỉ kiểm thử callback thành công.** Tài nguyên có thể thất bại khi mở lại do mạng, quota hoặc secret. Cần kiểm thử timeout, retry, lỗi một phần và readiness.

**Không cập nhật inventory sau khi nâng cấp dependency.** Phiên bản mới có thể thay đổi lifecycle hoặc bổ sung integration. Xem thay đổi dependency là lý do để rà soát inventory liên quan.

**Ghi owner quá chung chung.** “Ứng dụng” hoặc “JVM” không giúp người vận hành biết phải sửa component nào. Ghi tên bean, module, thư viện và trách nhiệm cụ thể.

## 18. Checklist kiểm kê tài nguyên cho CRaC

- [ ] Đã liệt kê socket, file handle, pool, client, thread, executor, timer và native resource chưa?
- [ ] Đã rà soát các trạng thái trong heap có thời hạn hoặc gắn với instance chưa?
- [ ] Đã xem tài nguyên do framework và dependency tạo tự động chưa?
- [ ] Mỗi mục đã có creator, owner và danh sách consumer chưa?
- [ ] Owner có quyền dừng consumer và kiểm soát vòng đời tài nguyên không?
- [ ] Đã xác định hành động trước checkpoint và sau restore cho từng mục chưa?
- [ ] Đã kiểm tra thư viện có CRaC integration chính thức chưa?
- [ ] Đã tránh đăng ký callback trùng cho cùng một tài nguyên chưa?
- [ ] Đã vẽ quan hệ phụ thuộc và thứ tự quiesce/restore chưa?
- [ ] Đã có xử lý lỗi, timeout, retry và readiness cho tài nguyên thiết yếu chưa?
- [ ] Đã có log, metric hoặc test chứng minh tài nguyên hoạt động sau restore chưa?
- [ ] Inventory có nguồn bằng chứng, người phụ trách và ngày cập nhật chưa?

## Kết luận

Kiểm kê tài nguyên là bước nền tảng để ứng dụng Java có thể checkpoint và restore một cách có kiểm soát. Danh sách cần bao gồm cả tài nguyên hệ điều hành, kết nối dịch vụ, thread nền, trạng thái cấu hình, cache, credential và dữ liệu có thời hạn. Với mỗi mục, nhóm cần biết ai tạo, ai sử dụng, ai sở hữu vòng đời và điều gì phải xảy ra trước checkpoint cũng như sau restore.

Khi owner được xác định rõ, callback CRaC có thể được đặt tại đúng ranh giới quản lý. Coordinator điều phối các component dừng công việc và phục hồi theo quan hệ phụ thuộc; owner thực hiện thao tác cụ thể với tài nguyên của mình. Inventory có bằng chứng, hành động và phép kiểm chứng rõ ràng sẽ giúp giảm lỗi restore, tránh quản lý chồng chéo và làm cho vòng đời tài nguyên dễ vận hành hơn.
