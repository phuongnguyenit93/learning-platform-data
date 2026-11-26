# Thứ tự kết quả, ngoại lệ và chi phí khi ánh xạ đồng thời

Khi một pipeline Stream cần gọi nhiều dịch vụ, truy vấn cơ sở dữ liệu hoặc thực hiện các thao tác I/O độc lập, xử lý tuần tự có thể làm chương trình phải chờ từng tác vụ hoàn tất. `Gatherers.mapConcurrent(...)` cho phép thực thi mapper đồng thời với giới hạn số tác vụ đang chạy, đồng thời vẫn giữ thứ tự kết quả theo thứ tự gặp của stream.

Đây là một gatherer có sẵn trong Stream Gatherers API. Tính năng được preview lần đầu ở JDK 22 qua JEP 461, preview lần hai ở JDK 23 qua JEP 473 và trở thành API chính thức trong JDK 24 qua JEP 485. Khi dùng trong Java hiện đại, hãy sử dụng API final từ JDK 24 trở lên, không cần bật preview.

## 1. `mapConcurrent(...)` giải quyết vấn đề gì?

`Stream.map(...)` gọi mapper theo cách tuần tự trong một pipeline tuần tự. Nếu mapper phải chờ mạng hoặc đĩa, thời gian chờ của từng phần tử cộng dồn. Ví dụ, tải thông tin cho 20 tài khoản, mỗi lần gọi dịch vụ mất 200 ms, có thể mất khoảng 4 giây nếu tất cả lần gọi diễn ra tuần tự.

`Gatherers.mapConcurrent(...)` cho phép nhiều lời gọi mapper diễn ra cùng lúc. Ta chỉ định số tác vụ tối đa có thể chạy đồng thời bằng `maxConcurrency`:

```java
Stream<T> input = ...;

Stream<R> output = input.gather(
        Gatherers.mapConcurrent(8, value -> loadRemoteData(value))
);
```

API có chữ ký:

```java
static <T, R> Gatherer<T, ?, R> mapConcurrent(
        int maxConcurrency,
        Function<? super T, ? extends R> mapper
)
```

Các điểm quan trọng:

- Mỗi phần tử đầu vào được đưa qua mapper để tạo một phần tử đầu ra tương ứng.
- Các lần gọi mapper có thể chạy đồng thời, sử dụng virtual thread.
- `maxConcurrency` giới hạn số lần gọi mapper đang được thực hiện đồng thời.
- Gatherer bảo toàn thứ tự encounter order của stream.
- `maxConcurrency` phải lớn hơn hoặc bằng 1; nếu nhỏ hơn 1, API ném `IllegalArgumentException`.
- Nếu mapper là `null`, API ném `NullPointerException`.

`mapConcurrent` là intermediate operation được áp dụng bằng `Stream.gather(...)`. Nó không tự biến toàn bộ stream thành parallel stream và không yêu cầu gọi `.parallel()` để có concurrency.

## 2. Thứ tự hoàn thành và thứ tự kết quả

Khi các tác vụ chạy đồng thời, thời gian hoàn thành có thể khác thứ tự đầu vào. Một tác vụ được gửi sau có thể hoàn thành trước tác vụ gửi trước. Tuy nhiên, `Gatherers.mapConcurrent(...)` giữ thứ tự đầu ra theo encounter order của stream.

Ví dụ sau mô phỏng ba yêu cầu có thời gian chờ khác nhau:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class OrderedConcurrentMapping {
    static String fetch(String id) {
        long delay = switch (id) {
            case "A" -> 300;
            case "B" -> 50;
            default -> 100;
        };

        try {
            Thread.sleep(delay);
            return "result-" + id;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Request interrupted: " + id, exception);
        }
    }

    public static void main(String[] args) {
        List<String> results = Stream.of("A", "B", "C")
                .gather(Gatherers.mapConcurrent(3,
                        OrderedConcurrentMapping::fetch))
                .toList();

        System.out.println(results);
    }
}
```

Kết quả:

```text
[result-A, result-B, result-C]
```

Trong ví dụ, `B` và `C` có thể hoàn thành trước `A`, nhưng danh sách kết quả vẫn giữ thứ tự `A`, `B`, `C`. Thời gian chờ chỉ nhằm minh họa sự khác nhau giữa thứ tự hoàn thành và thứ tự đầu ra; trong ứng dụng thật, mapper thường gọi HTTP client, truy vấn database hoặc một thao tác I/O có thời gian chờ.

### Encounter order là gì?

Encounter order là thứ tự mà stream quy định các phần tử được gặp. Với `List.stream()` hoặc `Stream.of(...)`, thứ tự thường được xác định theo thứ tự phần tử ban đầu. `mapConcurrent` giữ thứ tự đó khi phát kết quả.

Nếu nguồn stream không có encounter order hoặc pipeline đã loại bỏ ràng buộc thứ tự bằng `unordered()`, không nên kỳ vọng có một thứ tự nghiệp vụ cố định để bảo toàn.

Thứ tự được bảo toàn ở đầu ra của gatherer. Nếu sau đó chuyển pipeline sang parallel mode và dùng terminal operation `forEach`, chính `forEach` vẫn không cam kết thứ tự gọi action. Khi cần quan sát thứ tự trong terminal operation của parallel stream, dùng `forEachOrdered` hoặc thu kết quả bằng một collector/list có thứ tự.

### Thứ tự kết quả không đồng nghĩa thứ tự side effect

Mapper chạy đồng thời, nên các thao tác phụ bên trong mapper như ghi log, cập nhật hệ thống ngoài hoặc ghi vào database có thể xảy ra theo thứ tự khác với đầu vào. Chỉ thứ tự phần tử được phát xuống downstream mới được gatherer bảo toàn.

Ví dụ, log `finished B` có thể xuất hiện trước `finished A`, dù danh sách kết quả cuối cùng vẫn đặt kết quả A trước B. Nếu nghiệp vụ yêu cầu các side effect phải tuần tự, hãy thực hiện chúng ở bước downstream tuần tự hoặc thiết kế cơ chế đồng bộ riêng.

## 3. Giới hạn số tác vụ đồng thời

Tham số `maxConcurrency` là giới hạn số mapper invocation đang chạy cùng lúc. Nó hữu ích khi muốn khai thác I/O đồng thời mà vẫn kiểm soát áp lực lên dịch vụ bên ngoài.

Ví dụ, hệ thống có thể chỉ cho phép tối đa 10 yêu cầu cùng lúc tới một dịch vụ:

```java
List<CustomerProfile> profiles = customerIds.stream()
        .gather(Gatherers.mapConcurrent(10, customerClient::loadProfile))
        .toList();
```

Nếu có 1.000 customer ID, gatherer không khởi chạy 1.000 mapper invocation đồng thời. Số lời gọi đang thực hiện được giới hạn ở mức 10; khi một tác vụ hoàn tất, một phần tử tiếp theo có thể được xử lý.

Không nên chọn `maxConcurrency` tùy tiện. Giá trị phù hợp phụ thuộc vào:

- Giới hạn kết nối của HTTP client hoặc connection pool.
- Khả năng chịu tải và quota của dịch vụ đích.
- Số truy vấn đồng thời mà database cho phép.
- Dung lượng bộ nhớ và kích thước dữ liệu mỗi kết quả.
- Độ trễ trung bình và độ biến động của thao tác I/O.

Giới hạn concurrency không đồng nghĩa với giới hạn số yêu cầu mỗi giây. Ví dụ, 10 yêu cầu đồng thời có thể tạo ra hàng trăm yêu cầu mỗi giây nếu mỗi yêu cầu hoàn tất rất nhanh. Nếu dịch vụ quy định quota theo thời gian, cần kết hợp thêm rate limiter hoặc cơ chế điều tiết tốc độ phù hợp.

## 4. Xử lý ngoại lệ từ mapper

Mapper của `mapConcurrent` có kiểu `Function`, vì vậy không thể khai báo ném checked exception trực tiếp. Nếu thao tác bên trong có thể ném checked exception, cần xử lý nó trong mapper, thường bằng cách chuyển thành unchecked exception.

Ví dụ, HTTP client có thể ném `IOException`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.stream.Gatherers;

public class ConcurrentFetch {
    @FunctionalInterface
    interface TextClient {
        String get(String url) throws IOException;
    }

    static List<String> loadBodies(List<String> urls, TextClient httpClient) {
        try {
            return urls.stream()
                    .gather(Gatherers.mapConcurrent(8, url -> {
                        try {
                            return httpClient.get(url);
                        } catch (IOException exception) {
                            throw new UncheckedIOException(
                                    "Cannot fetch " + url, exception);
                        }
                    }))
                    .toList();
        } catch (RuntimeException exception) {
            throw new IllegalStateException(
                    "One or more requests failed", exception);
        }
    }
}
```

`Gatherers.mapConcurrent(...)` có quy tắc riêng khi mapper hoàn tất bất thường: nếu kết quả của mapper cần được phát xuống downstream nhưng mapper đó đã hoàn tất với exception, gatherer ném exception tương ứng dưới dạng một `RuntimeException`; sau đó các tác vụ còn lại bị hủy.

Vì vậy:

- Không giả định rằng lỗi sẽ được xử lý giống hệt một lời gọi `map(...)` tuần tự.
- Không dựa vào thứ tự chính xác mà nhiều mapper lỗi sẽ được quan sát; mapper chạy đồng thời và kết quả được phát theo encounter order.
- Đặt ranh giới xử lý lỗi ở nơi phù hợp, thường quanh thao tác terminal như `toList()`.
- Nếu cần giữ nguyên ngữ cảnh của lỗi, hãy gắn thông tin đầu vào vào exception khi chuyển checked exception thành unchecked exception.
- Không nuốt lỗi trong mapper bằng cách trả về `null` hoặc giá trị mặc định nếu nghiệp vụ cần phân biệt thất bại với kết quả hợp lệ.

### Có thể dừng các tác vụ còn lại không?

Khi một mapper hoàn tất exceptionally và lỗi cần được phát downstream, gatherer hủy các tác vụ còn lại. Khi downstream không còn muốn nhận thêm phần tử, các tác vụ đang chạy cũng được cố gắng hủy theo cơ chế best effort.

Best effort có nghĩa là yêu cầu hủy không bảo đảm mọi thao tác dừng ngay lập tức. Mapper nên tôn trọng interrupt khi phù hợp và dùng client có cơ chế timeout/cancellation. Một yêu cầu HTTP đã gửi tới server hoặc một side effect đã hoàn tất không tự động được rollback chỉ vì tác vụ Java bị hủy.

## 5. Xử lý `InterruptedException` đúng cách

Virtual thread có thể bị interrupt trong quá trình hủy tác vụ. Nếu mapper gọi API blocking như `Thread.sleep`, hoặc một API ném `InterruptedException`, không nên bỏ qua tín hiệu này.

Một cách xử lý thường dùng là khôi phục trạng thái interrupt rồi chuyển lỗi thành unchecked exception:

```java
static Result load(Request request) {
    try {
        return blockingClient.load(request);
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
                "Loading was interrupted", exception);
    }
}
```

Trong ứng dụng thực tế, hãy ưu tiên API client hỗ trợ timeout và cancellation. Việc chỉ khôi phục interrupt nhưng tiếp tục thực hiện các thao tác blocking khác có thể làm chậm quá trình dừng tác vụ.

## 6. Chi phí và giới hạn hiệu năng

`mapConcurrent` dùng virtual thread để chạy mapper đồng thời. Virtual thread có chi phí thấp hơn nhiều so với việc tạo một platform thread cho mỗi tác vụ blocking, nhưng concurrency vẫn có chi phí và giới hạn.

### Chi phí điều phối và lưu kết quả

Mỗi mapper invocation cần được lập lịch, theo dõi trạng thái và chuyển kết quả về pipeline. Khi tác vụ hoàn thành không đúng thứ tự đầu vào, kết quả hoàn tất sớm có thể phải chờ tác vụ trước nó để giữ encounter order. Điều này tạo ra hiện tượng *head-of-line blocking*:

```text
Thứ tự đầu vào:       A -------- B ---- C ---
Thời điểm hoàn thành:             B     C        A
Thứ tự phát kết quả:  A -------- B     C
```

Nếu A rất chậm, B và C dù đã hoàn tất vẫn chưa thể được phát ra trước A. Các kết quả chờ có thể chiếm bộ nhớ, đặc biệt khi mỗi kết quả lớn hoặc `maxConcurrency` cao.

### Mapper I/O-bound và CPU-bound

`mapConcurrent` thường phù hợp khi mapper dành nhiều thời gian chờ I/O:

- Gọi REST API hoặc RPC.
- Đọc dữ liệu từ dịch vụ từ xa.
- Truy vấn database độc lập.
- Gọi thư viện blocking có thể hoạt động an toàn trên virtual thread.

Với mapper chủ yếu thực hiện tính toán CPU, virtual thread không tạo thêm năng lực xử lý CPU. Số lõi xử lý vẫn giới hạn throughput; việc tăng `maxConcurrency` quá cao có thể làm tăng chi phí lập lịch, cạnh tranh CPU và bộ nhớ mà không tăng tốc đáng kể. Khi cần xử lý CPU song song, hãy cân nhắc parallel stream hoặc executor có số worker phù hợp với tài nguyên máy.

### Không phải lúc nào cũng nhanh hơn `map(...)`

Nếu mapper chỉ đổi kiểu, chuẩn hóa chuỗi hoặc thực hiện một phép tính rất nhỏ, overhead tạo và điều phối tác vụ đồng thời có thể lớn hơn thời gian xử lý. Trong trường hợp đó, `map(...)` tuần tự thường đơn giản và hiệu quả hơn.

Nên đo thời gian thực tế, mức sử dụng bộ nhớ, số yêu cầu đồng thời và độ trễ p95/p99 trước khi chọn `maxConcurrency` cho production.

## 7. Chọn `maxConcurrency` theo giới hạn hệ thống

Một cách bắt đầu thực tế:

| Loại mapper | Cách chọn ban đầu |
| --- | --- |
| Gọi API có quota nhỏ | Bắt đầu thấp, không vượt quota đồng thời của dịch vụ. |
| Truy vấn database qua connection pool | Không vượt số connection có thể dành cho tác vụ này. |
| I/O blocking có độ trễ cao | Thử tăng dần và theo dõi throughput, timeout, lỗi và bộ nhớ. |
| Tính toán CPU nặng | Thường không phù hợp; cân nhắc parallel stream hoặc executor giới hạn worker. |
| Mapper rất nhẹ | Dùng `map(...)` nếu không có lý do cần concurrency. |

Không có một con số tối ưu cho mọi ứng dụng. Nếu dịch vụ đích chỉ cho phép 5 request đồng thời, đặt `maxConcurrency` là 100 không làm hệ thống nhanh hơn một cách hữu ích; nó có thể chỉ tạo thêm tranh chấp connection, timeout hoặc lỗi throttling.

## 8. So sánh `map`, `parallel()` và `mapConcurrent`

| Cách tiếp cận | Cách thực thi | Phù hợp với |
| --- | --- | --- |
| `stream.map(mapper)` | Gọi mapper theo pipeline tuần tự. | Phép biến đổi nhẹ hoặc cần tuần tự hóa. |
| `stream.parallel().map(mapper)` | Chia việc xử lý stream theo cơ chế parallel stream, thường dùng ForkJoinPool chung. | Tính toán CPU độc lập có thể chia nhỏ. |
| `stream.gather(Gatherers.mapConcurrent(n, mapper))` | Chạy mapper trên virtual thread, giới hạn tối đa `n` lời gọi đồng thời và giữ encounter order. | Blocking I/O hoặc thao tác độc lập cần giới hạn concurrency. |

`mapConcurrent` hữu ích khi muốn tăng số thao tác I/O đang chờ mà không biến toàn bộ pipeline thành parallel stream. Ngược lại, parallel stream phù hợp hơn với phép tính CPU có thể chia nhỏ và kết hợp kết quả.

Không nên dùng hai cơ chế đồng thời chỉ vì muốn “nhiều thread hơn”. Kết hợp `.parallel()` với `mapConcurrent(...)` có thể làm cách thực thi khó dự đoán hơn và không tự động cải thiện throughput. Hãy chọn một mô hình concurrency phù hợp với loại công việc và đo kiểm trong môi trường gần production.

## 9. Ví dụ thực tế: tải nhiều hồ sơ khách hàng

Giả sử hệ thống có một danh sách customer ID và cần gọi dịch vụ hồ sơ cho từng ID. Dịch vụ cho phép tối đa 12 yêu cầu đang xử lý cùng lúc.

```java
import java.util.List;
import java.util.stream.Gatherers;

public class CustomerProfileService {
    private final CustomerClient customerClient;

    public CustomerProfileService(CustomerClient customerClient) {
        this.customerClient = customerClient;
    }

    public List<CustomerProfile> loadProfiles(List<String> customerIds) {
        return customerIds.stream()
                .filter(id -> id != null && !id.isBlank())
                .gather(Gatherers.mapConcurrent(
                        12, customerClient::loadProfile))
                .toList();
    }
}
```

Với pipeline này:

- Bộ lọc chạy trước gatherer để loại ID không hợp lệ.
- `mapConcurrent` gọi `loadProfile` đồng thời, tối đa 12 lần.
- Danh sách kết quả vẫn theo thứ tự customer ID sau bộ lọc.
- Nếu một mapper thất bại theo cách cần phát exception, pipeline báo lỗi và các tác vụ còn lại bị hủy theo hợp đồng của gatherer.
- `CustomerClient` phải hỗ trợ việc được gọi đồng thời; nếu client không thread-safe, cần cấu hình hoặc bảo vệ phù hợp.

Nếu API cần trả về kết quả thành công và lỗi riêng cho từng ID thay vì dừng toàn bộ pipeline, mapper có thể chuyển exception thành một kiểu kết quả nghiệp vụ như `LoadResult`. Cách đó phải phân biệt rõ trạng thái thành công, lỗi tạm thời và lỗi không thể phục hồi; không nên biến mọi exception thành một giá trị rỗng chung chung.

## 10. Những trường hợp cần cân nhắc trước khi dùng

Không nên dùng `mapConcurrent` nếu:

- Mapper phụ thuộc vào kết quả của phần tử trước đó.
- Thứ tự side effect bắt buộc phải đúng theo thứ tự đầu vào.
- Mapper dùng một tài nguyên không an toàn khi truy cập đồng thời.
- Dịch vụ đích không cho phép nhiều yêu cầu song song.
- Công việc quá nhẹ khiến chi phí điều phối lớn hơn lợi ích.
- Mapper CPU-bound và đã có chiến lược song song CPU phù hợp.

Nếu mapper có side effect, hãy kiểm tra xem các thao tác có thể chạy đồng thời và có thể bị hủy giữa chừng hay không. Nếu cần đảm bảo giao dịch hoặc thứ tự ghi, hãy đặt phần ghi ở bước tuần tự sau khi đã thu thập kết quả hoặc dùng cơ chế giao dịch thích hợp.

## 11. Phiên bản Java và cách sử dụng hiện nay

Stream Gatherers trải qua ba mốc:

| Phiên bản | JEP | Trạng thái |
| --- | --- | --- |
| JDK 22 | [JEP 461](https://openjdk.org/jeps/461) | Preview lần đầu. |
| JDK 23 | [JEP 473](https://openjdk.org/jeps/473) | Preview lần thứ hai. |
| JDK 24 | [JEP 485](https://openjdk.org/jeps/485) | API chính thức. |

Trong dự án hiện đại, dùng `java.util.stream.Gatherers` và `Stream.gather(...)` từ JDK 24 trở lên. Không cần `--enable-preview` khi biên dịch hoặc chạy bằng API final.

Ví dụ biên dịch:

```bash
javac --release 24 -d out src/OrderedConcurrentMapping.java
java -cp out OrderedConcurrentMapping
```

Nếu dự án phải chạy trên JDK 22 hoặc 23, API Gatherers ở các phiên bản đó còn là preview và chữ ký có thể thay đổi giữa các preview. Hãy chọn một baseline Java đã hỗ trợ API final khi phát triển tính năng mới; không trộn mã preview cũ với mã final.

## 12. Kiến thức cần nhớ

- `Gatherers.mapConcurrent(maxConcurrency, mapper)` thực hiện ánh xạ đồng thời bằng virtual thread.
- `maxConcurrency` giới hạn số mapper invocation đang chạy cùng lúc; nó không phải quota số request mỗi giây.
- Gatherer bảo toàn encounter order của stream dù các mapper có thể hoàn thành theo thứ tự khác nhau.
- Side effect bên trong mapper vẫn xảy ra đồng thời và có thể không theo thứ tự đầu vào.
- Khi mapper hoàn tất exceptionally, exception tương ứng được ném lại dưới dạng `RuntimeException` và các tác vụ còn lại bị hủy.
- Khi downstream không cần thêm phần tử, việc hủy tác vụ đang chạy chỉ được thực hiện theo best effort.
- Virtual thread phù hợp với I/O blocking; chúng không làm phép tính CPU tự nhiên chạy nhanh hơn số lõi máy.
- Kết quả hoàn thành sớm có thể phải chờ phần tử trước đó để giữ thứ tự, gây head-of-line blocking và tiêu tốn bộ nhớ.
- Dùng API final từ JDK 24 qua JEP 485, không dùng preview JDK 22/23 trong mã mới.

## Tài liệu tham khảo

- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — chuẩn hóa Stream Gatherers trong JDK 24.
- [JEP 461: Stream Gatherers (Preview)](https://openjdk.org/jeps/461) — mốc preview đầu tiên trong JDK 22.
- [JEP 473: Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473) — mốc preview thứ hai trong JDK 23.
- [Class `Gatherers` — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) — chữ ký, thứ tự kết quả, virtual threads, xử lý ngoại lệ và hủy tác vụ của `mapConcurrent`.
- [Stream Gatherers — Java SE 24 Developer Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html) — cách dùng Gatherers, concurrency limit và ví dụ.
- [Class `Stream` — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html) — intermediate operation `gather(...)`.
