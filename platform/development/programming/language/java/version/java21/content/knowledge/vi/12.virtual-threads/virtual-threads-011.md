# Tiêu chí chọn virtual thread cho một đường xử lý cụ thể

Virtual thread phù hợp nhất với đường xử lý có nhiều tác vụ đồng thời nhưng mỗi tác vụ thường dành phần lớn thời gian để chờ I/O hoặc chờ một thao tác có thể park thread. Chúng giúp ứng dụng duy trì mô hình lập trình đồng bộ, theo từng tác vụ, mà không cần giữ một platform thread riêng trong suốt thời gian chờ.

Virtual thread không làm CPU chạy nhanh hơn và không loại bỏ giới hạn của database, dịch vụ từ xa, connection pool hay bộ nhớ. Vì vậy, quyết định sử dụng phải dựa trên đặc điểm thực tế của đường xử lý, cách thư viện hoạt động và tài nguyên mà đường xử lý tiêu thụ.

## 1. Hiểu đúng lợi ích của virtual thread

Virtual thread là đối tượng Thread được JVM lập lịch trên một số lượng nhỏ hơn các platform thread, còn gọi là carrier thread. Khi virtual thread thực hiện một thao tác blocking được JDK hỗ trợ và có thể unmount, carrier thread được giải phóng để chạy virtual thread khác.

Điều này hữu ích cho mô hình một tác vụ trên một thread:

- Mỗi request hoặc công việc có thể chạy trong một virtual thread riêng.
- Mã có thể dùng lời gọi tuần tự, try/catch và stack trace thông thường.
- Khi tác vụ chờ I/O, JVM có thể cho carrier thread xử lý tác vụ khác.
- Ứng dụng có thể hỗ trợ nhiều tác vụ chờ đồng thời mà không cần tạo số lượng platform thread tương ứng.

Virtual thread vẫn là thread thực thi mã Java. Khi nó chạy mã CPU-bound, nó vẫn cần thời gian CPU như mọi thread khác. Việc tạo thêm virtual thread không làm tăng số core hoặc năng lực tính toán của máy.

## 2. Đánh giá đường xử lý theo loại công việc

Trước khi chuyển đổi, hãy phân tích từng giai đoạn trong đường xử lý: tính toán, I/O, chờ khóa, gọi thư viện và truy cập tài nguyên dùng chung.

| Đặc điểm đường xử lý | Virtual thread có phù hợp? | Lý do |
|---|---|---|
| Nhiều request đồng thời, mỗi request chờ HTTP hoặc socket I/O | Rất phù hợp | Thời gian chờ có thể giải phóng carrier thread |
| Nhiều tác vụ gọi JDBC hoặc dịch vụ từ xa bằng API blocking | Thường phù hợp | Có thể giữ cách viết đồng bộ, nhưng phải kiểm tra driver và giới hạn kết nối |
| Tác vụ chủ yếu tính toán CPU-bound | Ít lợi ích | Số lượng công việc chạy đồng thời vẫn bị giới hạn bởi CPU |
| Tác vụ chờ semaphore, queue hoặc thao tác park được hỗ trợ | Có thể phù hợp | Virtual thread có thể nhường carrier trong thời gian chờ |
| Tác vụ giữ khóa lâu trong khi thực hiện blocking | Cần kiểm tra | Trên Java 21, một số vùng mã có thể pin carrier thread |
| Tác vụ phụ thuộc native library hoặc mã có thread affinity | Cần kiểm tra kỹ | Native call có thể giữ virtual thread gắn với carrier trong thời gian gọi |
| Tác vụ dùng tài nguyên giới hạn như connection hoặc API quota | Phù hợp nếu có giới hạn tài nguyên | Virtual thread không tự giới hạn số request tới tài nguyên đó |

Một đường xử lý có thể vừa CPU-bound vừa I/O-bound. Hãy phân tích giai đoạn chiếm thời gian lớn và điểm nghẽn thực tế thay vì gắn nhãn toàn bộ ứng dụng là I/O-bound hoặc CPU-bound.

## 3. Trường hợp điển hình: nhiều tác vụ blocking I/O

Giả sử một dịch vụ cần gọi nhiều endpoint HTTP độc lập. Mỗi lần gọi có thể chờ mạng trong khi không thực hiện nhiều tính toán. Có thể tạo một virtual thread cho mỗi request bằng executor chuyên dụng:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ParallelHttpCalls {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        List<URI> endpoints = List.of(
                URI.create("https://service-a.example"),
                URI.create("https://service-b.example"),
                URI.create("https://service-c.example")
        );

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Integer>> results = endpoints.stream()
                    .map(uri -> executor.submit(() -> {
                        HttpRequest request = HttpRequest.newBuilder(uri)
                                .GET()
                                .build();
                        return client.send(
                                request,
                                HttpResponse.BodyHandlers.ofString()
                        ).statusCode();
                    }))
                    .toList();

            for (Future<Integer> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
~~~

Ví dụ dùng send(), là API blocking của HttpClient. Các lời gọi có thể chờ mạng trong những virtual thread riêng, trong khi executor tạo một virtual thread cho mỗi tác vụ được submit. Executor được đóng bằng try-with-resources; thao tác close chờ các tác vụ đã submit hoàn tất.

Đây là ví dụ về cấu trúc thực thi. Trong ứng dụng thực tế, cần thêm timeout, xử lý lỗi từng request, giới hạn số request đồng thời theo năng lực dịch vụ đích và chính sách retry phù hợp.

## 4. Không chọn virtual thread để tăng tốc công việc CPU-bound

Nếu mỗi tác vụ chủ yếu thực hiện tính toán như mã hóa, nén, xử lý ảnh hoặc tính toán số học, tác vụ không dành nhiều thời gian chờ để giải phóng carrier. Tạo rất nhiều virtual thread cho công việc này không làm tăng thông lượng CPU; nó có thể tăng chi phí lập lịch, bộ nhớ và chuyển đổi trạng thái.

Với công việc CPU-bound, một executor platform thread có kích thước giới hạn thường phù hợp hơn:

~~~java
int parallelism = Runtime.getRuntime().availableProcessors();

try (var executor = Executors.newFixedThreadPool(parallelism)) {
    // Submit các tác vụ tính toán CPU-bound vào executor giới hạn này.
}
~~~

Kích thước thực tế cần đo và điều chỉnh theo đặc tính tác vụ, CPU quota của container, các công việc khác trong tiến trình và yêu cầu latency. availableProcessors() là điểm bắt đầu để đánh giá, không phải công thức bắt buộc cho mọi ứng dụng.

## 5. Virtual thread không thay thế giới hạn tài nguyên

Executors.newVirtualThreadPerTaskExecutor() tạo virtual thread mới cho mỗi tác vụ. Executor này không phải một pool có kích thước cố định để giới hạn số tác vụ đang chạy. Nếu ứng dụng nhận request nhanh hơn khả năng xử lý của database hoặc dịch vụ đích, số tác vụ chờ có thể tăng cao và tiêu thụ bộ nhớ.

Hãy giới hạn tài nguyên khan hiếm tại đúng ranh giới của chúng. Ví dụ, nếu một database chỉ nên nhận tối đa 20 truy vấn đồng thời từ đường xử lý này, có thể dùng Semaphore:

~~~java
import java.util.concurrent.Semaphore;

final class DatabaseGate {
    private final Semaphore permits = new Semaphore(20);
    private final Repository repository;

    DatabaseGate(Repository repository) {
        this.repository = repository;
    }

    Result query() throws InterruptedException {
        permits.acquire();
        try {
            return repository.query();
        } finally {
            permits.release();
        }
    }
}
~~~

Repository và Result trong ví dụ đại diện cho kiểu của ứng dụng. Semaphore giới hạn số truy vấn đang đi qua vùng được bảo vệ. Nếu tác vụ phải chờ permit, virtual thread có thể park thay vì chiếm một carrier thread trong suốt thời gian chờ.

Ngoài Semaphore, có thể cần:

- Giới hạn số request được nhận hoặc số tác vụ được phép chờ.
- Dùng connection pool có kích thước phù hợp với database.
- Áp dụng timeout và deadline cho lời gọi ra ngoài.
- Dùng rate limiter khi dịch vụ đích quy định quota theo thời gian.
- Thiết kế backpressure để hệ thống từ chối hoặc làm chậm đầu vào khi quá tải.

Không tạo một virtual thread cho mọi phần tử trong một hàng đợi không giới hạn mà không có chính sách admission control. Virtual thread rẻ hơn platform thread nhưng không miễn phí về stack, object, context, bộ nhớ và tài nguyên ứng dụng.

## 6. Kiểm tra thư viện và mã blocking

Virtual thread chỉ giúp giải phóng carrier khi thao tác blocking có thể unmount virtual thread. Trước khi chuyển một đường xử lý sang virtual thread, hãy kiểm tra các thành phần bên trong:

- **HTTP và socket client:** xác nhận API đang dùng có hỗ trợ blocking theo cách tương thích với virtual thread; kiểm tra timeout, retry và giới hạn kết nối.
- **JDBC driver:** xác nhận phiên bản driver, pool và các lời gọi native hoặc vùng khóa bên trong. Số virtual thread không thể vượt qua giới hạn connection của database.
- **Thư viện bên thứ ba:** tìm các thao tác native, khóa được giữ qua thời gian chờ, thread-local cache lớn hoặc giả định một tác vụ luôn chạy trên cùng platform thread.
- **Đồng bộ hóa:** xác định các vùng synchronized có thể thực hiện I/O hoặc chờ lâu trên Java 21.
- **Tài nguyên theo thread:** tránh tạo một tài nguyên nặng trong ThreadLocal cho mọi virtual thread nếu số tác vụ đồng thời có thể rất lớn.

Virtual thread vẫn hỗ trợ ThreadLocal. Tuy nhiên, mô hình một thread cho mỗi tác vụ làm số thread có thể tăng đáng kể; một cache hoặc connection được giữ trong ThreadLocal có thể nhân lên theo số virtual thread. Hãy đặt giới hạn ở pool tài nguyên hoặc quản lý vòng đời tài nguyên rõ ràng thay vì dựa vào việc tái sử dụng thread.

## 7. Pinning trên Java 21

Trên Java 21, virtual thread có thể bị pin vào carrier thread trong một số trường hợp. Khi virtual thread bị pin và thực hiện blocking, carrier thread cũng bị giữ lại, làm giảm khả năng tận dụng scheduler.

Hai trường hợp cần chú ý trên Java 21:

1. Virtual thread thực hiện thao tác blocking trong khi đang ở trong một synchronized block hoặc synchronized method.
2. Virtual thread đang thực thi native method; virtual thread không thể unmount khỏi carrier trong thời gian chạy native method đó.

Ví dụ cần xem xét khi mục tiêu runtime là Java 21:

~~~java
synchronized (lock) {
    // Tránh giữ intrinsic monitor trong lúc chờ I/O lâu.
    remoteClient.callBlockingService();
}
~~~

Nếu vùng synchronized bao quanh lời gọi blocking kéo dài, carrier thread có thể bị pin. Hãy rút ngắn vùng giữ monitor, thực hiện I/O bên ngoài vùng khóa nếu bảo đảm được tính đúng đắn, hoặc đánh giá ReentrantLock cho trường hợp phù hợp. Không thay thế synchronized một cách máy móc: khóa vẫn cần bảo vệ invariant và tính nguyên tử của dữ liệu dùng chung.

Lưu ý theo phiên bản: JDK 24 đã thay đổi cơ chế để virtual thread không còn bị pin chỉ vì blocking trong synchronized block hoặc method (JEP 491). Vì bài này nhắm đến Java 21, hành vi pinning của Java 21 vẫn cần được xét khi runtime triển khai là JDK 21; không nên áp dụng cảnh báo về monitor pinning như một quy tắc chung cho các JDK mới hơn. Native method vẫn là trường hợp cần kiểm tra riêng.

Trên Java 21, có thể điều tra pinning bằng Java Flight Recorder với sự kiện jdk.VirtualThreadPinned hoặc bật tùy chọn chẩn đoán:

~~~shell
java -Djdk.tracePinnedThreads=full -jar application.jar
~~~

Chỉ dùng trace khi điều tra hoặc trong môi trường kiểm thử vì log có thể nhiều. Kết hợp quan sát với tải thực tế để xác định pinning có phải điểm nghẽn hay không.

## 8. Chia sẻ trạng thái và ThreadLocal

Khi chuyển từ pool platform thread có kích thước nhỏ sang nhiều virtual thread, nhiều đoạn mã trước đây ít chạy đồng thời có thể bắt đầu truy cập trạng thái dùng chung song song. Cần rà soát:

- Mutable singleton, cache và collection dùng chung có được đồng bộ hóa đúng cách không?
- Một tác vụ có vô tình giữ monitor trong thời gian gọi dịch vụ bên ngoài không?
- ThreadLocal có giữ object lớn, buffer hoặc tài nguyên cần đóng không?
- Có giả định mã luôn chạy trên một thread cụ thể hoặc thread ID cụ thể không?
- Có dùng ThreadLocal như một cách giới hạn số kết nối hoặc số phiên đồng thời không?

Virtual thread không tự làm cho mã an toàn luồng. Mỗi tác vụ cần có quy tắc sở hữu dữ liệu rõ ràng, dùng immutable object khi thích hợp và bảo vệ trạng thái dùng chung bằng cơ chế đồng bộ hóa đúng.

## 9. Quy trình quyết định cho một đường xử lý

Có thể đánh giá theo thứ tự sau:

1. **Đo thời gian chờ và thời gian CPU.** Nếu tác vụ chủ yếu tính toán, virtual thread thường không mang lại lợi ích thông lượng.
2. **Xác định loại blocking.** Kiểm tra I/O, lock, semaphore, native call và thư viện có thể unmount virtual thread hay không.
3. **Liệt kê tài nguyên giới hạn.** Xác định số connection, quota, worker bên ngoài và dung lượng hàng đợi.
4. **Kiểm tra pinning và trạng thái dùng chung.** Đặc biệt với synchronized và native code nếu runtime là Java 21.
5. **Chạy thử với executor phù hợp.** Dùng một virtual thread cho mỗi tác vụ blocking; giữ executor giới hạn cho công việc CPU-bound.
6. **So sánh bằng tải đại diện.** Đo latency, throughput, CPU, heap, số tác vụ đang chờ, thời gian chờ connection và lỗi downstream.

Không quyết định chỉ dựa trên benchmark tạo thread rỗng. Bài đo phải đại diện cho đường xử lý thật, gồm thư viện, network, database, giới hạn tài nguyên và mức tải dự kiến.

## 10. Bảng lựa chọn nhanh

| Câu hỏi | Nếu câu trả lời là có | Hướng xử lý |
|---|---|---|
| Tác vụ đồng thời cao và phần lớn thời gian chờ I/O? | Có | Thử virtual thread |
| Mỗi tác vụ có thể dùng mô hình blocking đơn giản? | Có | Executor tạo virtual thread cho từng tác vụ là lựa chọn phù hợp |
| Tác vụ chủ yếu dùng CPU liên tục? | Có | Ưu tiên executor platform thread có giới hạn |
| Database hoặc dịch vụ đích có quota/connection giới hạn? | Có | Bổ sung Semaphore, connection pool, rate limit hoặc backpressure |
| Thư viện giữ khóa khi blocking hoặc gọi native code? | Có | Đo pinning và xác minh tương thích trên JDK triển khai |
| ThreadLocal giữ tài nguyên nặng? | Có | Thay đổi vòng đời hoặc chuyển sang pool tài nguyên có giới hạn |
| Chưa có số liệu tải thực tế? | Có | Đo baseline trước khi chuyển đổi diện rộng |

Virtual thread là lựa chọn tốt khi đường xử lý có nhiều tác vụ chờ và có thể giải phóng carrier trong lúc chờ. Lợi ích chỉ bền vững khi ứng dụng đồng thời quản lý giới hạn tài nguyên, kiểm tra thư viện, xử lý trạng thái dùng chung và đo hiệu quả trên runtime triển khai thực tế.
