# Gatherers.mapConcurrent và giới hạn số tác vụ đồng thời

## Mục tiêu

Một pipeline Stream thường xử lý từng phần tử qua các intermediate operation như `map`, `filter` hoặc `flatMap`. Khi mỗi phần tử cần gọi một dịch vụ từ xa, truy vấn cơ sở dữ liệu hoặc thực hiện một thao tác I/O có thời gian chờ, xử lý từng phần tử lần lượt có thể làm tổng thời gian chờ tăng lên đáng kể.

`Gatherers.mapConcurrent(maxConcurrency, mapper)` cho phép chạy hàm ánh xạ của nhiều phần tử cùng lúc, với giới hạn số tác vụ đang thực hiện. API sử dụng virtual thread và giữ thứ tự kết quả theo thứ tự của stream.

Điểm cần nhớ:

- `maxConcurrency` đặt giới hạn trên cho số lần gọi mapper đang chạy đồng thời.
- Mapper được thực thi đồng thời bằng virtual thread.
- Với stream có encounter order, kết quả vẫn được phát theo thứ tự đầu vào dù tác vụ hoàn thành không theo thứ tự đó.
- Khi downstream không cần thêm phần tử, các tác vụ đang chạy được yêu cầu hủy theo cơ chế best effort.
- Nếu mapper hoàn thành bất thường và kết quả của nó cần được phát xuống downstream, lỗi được ném lại dưới dạng `RuntimeException` và các tác vụ còn lại bị hủy.

`mapConcurrent` là API chính thức từ JDK 24. Trong JDK 22, Gatherers còn ở giai đoạn preview theo JEP 461; JDK 23 tiếp tục preview theo JEP 473. Ví dụ trong bài dùng API ổn định từ JDK 24 trở lên, không cần bật preview.

## Vì sao cần giới hạn số tác vụ đồng thời?

Giả sử ứng dụng cần tải thông tin của 100 khách hàng từ một dịch vụ HTTP. Nếu thực hiện tuần tự, ứng dụng gửi yêu cầu thứ hai sau khi yêu cầu thứ nhất hoàn tất. Nếu mỗi yêu cầu mất 200 ms, tổng thời gian chờ có thể xấp xỉ 20 giây, chưa tính các chi phí khác.

Chạy tất cả 100 yêu cầu cùng lúc có thể gây áp lực lớn lên dịch vụ đích, connection pool, bộ nhớ hoặc giới hạn tài khoản. Ta cần một mức đồng thời có kiểm soát, ví dụ tối đa 8 yêu cầu đang chạy.

`mapConcurrent` đáp ứng tình huống đó:

~~~java
List<Customer> customers =
    customerIds.stream()
        .gather(Gatherers.mapConcurrent(
            8,
            customerRepository::load
        ))
        .toList();
~~~

Trong ví dụ, mỗi mã khách hàng được truyền vào `customerRepository.load`. Nhiều lần tải có thể diễn ra cùng lúc, nhưng số lần mapper đang thực hiện không vượt quá 8. Khi một tác vụ hoàn tất, pipeline có thể tiếp tục xử lý phần tử tiếp theo.

## Cú pháp và hợp đồng API

Chữ ký phương thức:

~~~java
public static <T, R> Gatherer<T, ?, R> mapConcurrent(
    int maxConcurrency,
    Function<? super T, ? extends R> mapper
)
~~~

| Tham số | Ý nghĩa |
|---|---|
| `T` | Kiểu phần tử đầu vào |
| `R` | Kiểu phần tử đầu ra sau khi ánh xạ |
| `maxConcurrency` | Số tác vụ mapper tối đa được thực hiện đồng thời |
| `mapper` | Hàm nhận một phần tử đầu vào và tạo ra kết quả |

Điều kiện đầu vào:

- `maxConcurrency` phải lớn hơn hoặc bằng 1. Nếu nhỏ hơn 1, phương thức ném `IllegalArgumentException`.
- `mapper` không được là `null`. Nếu là `null`, phương thức ném `NullPointerException`.
- Phương thức trả về một `Gatherer`, vì vậy có thể đặt nó vào pipeline bằng `Stream.gather(...)`.

Ví dụ với dữ liệu số:

~~~java
List<Integer> doubled =
    Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.mapConcurrent(3, number -> number * 2))
        .toList();
~~~

Kết quả:

~~~text
[2, 4, 6, 8, 10]
~~~

Với mapper rất nhanh như phép nhân số nguyên, chạy đồng thời thường không đem lại lợi ích đáng kể. Tình huống phù hợp hơn là mapper có thời gian chờ I/O hoặc thao tác độc lập có độ trễ đáng kể.

## Virtual thread và cách hoạt động

`mapConcurrent` thực thi mapper bằng virtual thread. Virtual thread là thread do JVM quản lý, có chi phí tạo và chờ thấp hơn platform thread trong nhiều tình huống I/O blocking. Khi một virtual thread chờ một thao tác I/O hỗ trợ cơ chế này, JVM có thể giải phóng platform thread để thực hiện công việc khác.

Với `maxConcurrency = 8`, có tối đa 8 tác vụ mapper đang được xử lý tại một thời điểm. Đây là giới hạn concurrency của thao tác, không phải cam kết rằng ứng dụng chỉ tạo đúng 8 virtual thread trong toàn bộ vòng đời pipeline.

Quá trình có thể hình dung như sau:

~~~text
Phần tử đầu vào
      |
      v
  mapConcurrent(3, mapper)
      |
      +---- tác vụ A ---- virtual thread
      |
      +---- tác vụ B ---- virtual thread
      |
      +---- tác vụ C ---- virtual thread
      |
      | Khi một tác vụ hoàn tất, nhận phần tử tiếp theo
      v
Kết quả theo encounter order
~~~

Các tác vụ được phép hoàn thành theo thứ tự bất kỳ. Gatherer điều phối kết quả để giữ thứ tự stream.

### Không cần gọi parallel()

Không cần biến stream thành parallel stream để dùng `mapConcurrent`:

~~~java
List<Response> responses =
    requests.stream()
        .gather(Gatherers.mapConcurrent(8, this::sendRequest))
        .toList();
~~~

`mapConcurrent` tự tổ chức việc thực thi mapper đồng thời. Gọi thêm `parallel()` không phải điều kiện để API này hoạt động.

Virtual thread đặc biệt hữu ích cho các tác vụ chờ I/O. Với phép tính CPU-bound nặng, virtual thread không làm tăng năng lực tính toán của CPU. Trong trường hợp đó, hãy đo đạc và chọn chiến lược xử lý CPU phù hợp, chẳng hạn parallel stream hoặc một executor có mức song song gắn với số lõi xử lý.

## Thứ tự kết quả được giữ nguyên

Một đặc điểm quan trọng của `mapConcurrent` là giữ thứ tự stream. Thứ tự bắt đầu và kết thúc của mapper có thể khác nhau, nhưng kết quả được chuyển xuống downstream theo encounter order.

Ví dụ, stream có ba phần tử:

~~~text
Đầu vào:       A     B     C
Thời gian:    300ms  50ms  80ms
Hoàn tất:       C     B     A
Kết quả:       A     B     C
~~~

Khi mapper xử lý A lâu hơn B và C, các tác vụ B và C vẫn có thể hoàn tất trước. Tuy nhiên, pipeline phải chờ kết quả A trước khi phát B và C để bảo toàn thứ tự.

Điều này giúp giữ quan hệ giữa đầu vào và đầu ra. Ví dụ, danh sách mã khách hàng và danh sách hồ sơ sau ánh xạ vẫn tương ứng theo cùng vị trí.

Đổi lại, có thể xuất hiện hiện tượng chờ đầu hàng (*head-of-line blocking*): một tác vụ đầu vào chậm làm chậm việc phát các kết quả phía sau dù chúng đã hoàn tất. Nếu thứ tự không quan trọng, hãy đánh giá lại yêu cầu nghiệp vụ và các lựa chọn xử lý khác; không giả định rằng `mapConcurrent` tự bỏ thứ tự để tối đa thông lượng.

## Ví dụ thực tế: tải dữ liệu HTTP có giới hạn

Ví dụ dưới đây gửi các yêu cầu HTTP đồng bộ để minh họa một mapper có thời gian chờ I/O. `mapConcurrent(8, ...)` cho phép tối đa 8 lời gọi `HttpClient.send` được thực hiện đồng thời.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.concurrent.CompletionException;
import java.util.stream.Gatherers;

public class ConcurrentHttpFetch {

    private static String fetch(
            HttpClient client,
            URI uri
    ) {
        HttpRequest request = HttpRequest.newBuilder(uri)
            .GET()
            .build();

        try {
            return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
            ).body();
        } catch (InterruptedException e) {
            // Giữ lại trạng thái interrupt để tầng gọi có thể nhận biết.
            Thread.currentThread().interrupt();
            throw new CompletionException(e);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        List<URI> endpoints = List.of(
            URI.create("https://example.com/api/a"),
            URI.create("https://example.com/api/b"),
            URI.create("https://example.com/api/c"),
            URI.create("https://example.com/api/d"),
            URI.create("https://example.com/api/e"),
            URI.create("https://example.com/api/f")
        );

        List<String> bodies = endpoints.stream()
            .gather(Gatherers.mapConcurrent(
                8,
                uri -> fetch(client, uri)
            ))
            .toList();

        System.out.println("Đã nhận " + bodies.size() + " phản hồi");
    }
}
~~~

Trong ví dụ:

1. `HttpClient` được tạo một lần và dùng lại cho nhiều yêu cầu.
2. Mỗi URI là một phần tử đầu vào.
3. Mapper gọi `fetch` để gửi yêu cầu và đọc nội dung phản hồi.
4. Tối đa 8 lời gọi mapper được thực hiện đồng thời.
5. `toList()` là terminal operation kích hoạt việc thực thi pipeline.
6. Danh sách `bodies` giữ thứ tự tương ứng với danh sách `endpoints`.

Đây là ví dụ minh họa cơ chế đồng thời. Trong ứng dụng thật, cần cấu hình timeout, xác thực, xử lý mã trạng thái HTTP, giới hạn kết nối và chính sách retry phù hợp với dịch vụ đang gọi.

## Chọn maxConcurrency như thế nào?

Không có một con số phù hợp cho mọi ứng dụng. Giá trị hợp lý phụ thuộc vào thời gian chờ, tài nguyên cục bộ và giới hạn của dịch vụ đích.

| Yếu tố | Ảnh hưởng tới lựa chọn |
|---|---|
| Giới hạn kết nối của HTTP client hoặc connection pool | Không đặt concurrency cao hơn khả năng phục vụ thực tế của pool nếu không có lý do rõ ràng. |
| Giới hạn API từ xa | Cần tuân thủ quota và giới hạn số yêu cầu đồng thời của nhà cung cấp. |
| Cơ sở dữ liệu | Cân nhắc số connection khả dụng và giới hạn tải của database. |
| Thời gian chờ I/O | Tác vụ thường chờ lâu có thể tận dụng concurrency cao hơn, nhưng phải đo tải thực tế. |
| Bộ nhớ mỗi tác vụ | Mỗi tác vụ có thể giữ request, response hoặc buffer; tăng concurrency làm tăng lượng tài nguyên đang được giữ. |
| Tác vụ CPU-bound | Tăng concurrency không làm CPU xử lý nhanh hơn và có thể tăng tranh chấp tài nguyên. |

Một cách triển khai thực tế:

1. Bắt đầu bằng giới hạn nhỏ, chẳng hạn 4 hoặc 8.
2. Đo thông lượng, độ trễ, tỷ lệ lỗi và mức sử dụng tài nguyên.
3. Tăng dần nếu hệ thống còn khả năng xử lý.
4. Dừng tăng khi độ trễ hoặc tỷ lệ lỗi tăng, hoặc dịch vụ đích đạt giới hạn.
5. Ghi lại giá trị cấu hình để có thể điều chỉnh theo môi trường triển khai.

### Concurrency không phải rate limit

`maxConcurrency` giới hạn số tác vụ đang chạy cùng lúc. Nó không giới hạn số yêu cầu được gửi trong một giây hoặc một phút.

Ví dụ, nếu mỗi yêu cầu hoàn tất trong 10 ms và giới hạn đồng thời là 10, ứng dụng vẫn có thể gửi nhiều yêu cầu mỗi giây. Nếu API quy định tối đa 100 yêu cầu/phút, chỉ đặt `maxConcurrency(10)` không bảo đảm tuân thủ quota đó.

Khi cần rate limit, phải kết hợp một cơ chế giới hạn tốc độ theo thời gian, token bucket, bộ điều phối yêu cầu hoặc giới hạn được cung cấp bởi client/thư viện mạng.

## Hủy tác vụ khi downstream không cần thêm dữ liệu

Một số terminal operation có thể dừng sớm, ví dụ `findFirst`, `anyMatch` hoặc `limit`. Khi downstream không muốn nhận thêm phần tử, `mapConcurrent` sẽ cố gắng hủy các tác vụ đang chạy theo cơ chế best effort.

Ví dụ:

~~~java
Optional<String> firstAvailable =
    endpoints.stream()
        .gather(Gatherers.mapConcurrent(8, this::fetchStatus))
        .filter(this::isHealthy)
        .findFirst();
~~~

Khi downstream đã tìm thấy phần tử phù hợp và không cần đọc thêm, các tác vụ còn lại được yêu cầu hủy.

Cần hiểu rõ giới hạn:

- Hủy là best effort; không bảo đảm mọi thao tác đang chạy dừng ngay lập tức.
- Mapper có thể đã gửi request hoặc tạo tác dụng phụ trước khi nhận tín hiệu hủy.
- Một lời gọi native, thư viện hoặc thao tác I/O không phản hồi interruption có thể tiếp tục chạy.
- Với thao tác có thể bị hủy, nên dùng API hỗ trợ interruption hoặc cơ chế timeout/cancel riêng.

Vì vậy, mapper nên ưu tiên tạo ra kết quả và hạn chế tác dụng phụ không thể đảo ngược. Nếu mapper gửi lệnh thanh toán, ghi dữ liệu hoặc tạo tài nguyên từ xa, cần có cơ chế idempotency và xử lý trạng thái độc lập.

## Xử lý ngoại lệ trong mapper

Mapper nhận một `Function`, nên không thể khai báo ném checked exception trong chữ ký. Nếu thao tác bên trong phát sinh checked exception, hãy chuyển nó thành unchecked exception phù hợp, như `UncheckedIOException` hoặc `CompletionException`.

Theo hợp đồng API, nếu tác vụ của mapper hoàn thành bất thường và kết quả của nó cần được phát xuống downstream, ngoại lệ tương ứng được ném lại dưới dạng `RuntimeException`. Sau đó, các tác vụ còn lại bị hủy.

Ví dụ:

~~~java
List<String> contents =
    paths.stream()
        .gather(Gatherers.mapConcurrent(4, path -> {
            try {
                return Files.readString(path);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }))
        .toList();
~~~

Nếu một file không thể đọc, pipeline sẽ thất bại thay vì tự bỏ qua file đó. Nếu nghiệp vụ muốn bỏ qua lỗi, hãy xử lý rõ ràng bên trong mapper và trả về kiểu kết quả biểu diễn thành công/thất bại, ví dụ một record `LoadResult`.

Không nên nuốt mọi exception rồi trả về `null`; cách đó khiến lỗi khó phân biệt với dữ liệu vắng mặt và có thể gây lỗi ở bước xử lý sau.

## Mapper chạy đồng thời nên cần an toàn luồng

Vì mapper có thể được gọi đồng thời trên nhiều virtual thread, hãy coi nó là hàm có thể được nhiều luồng gọi cùng lúc.

Nên:

- Dùng biến cục bộ cho dữ liệu tạm thời của mỗi lần gọi.
- Dùng client hoặc repository dùng chung nếu API của chúng được tài liệu xác nhận là thread-safe.
- Tránh ghi vào collection hoặc biến mutable dùng chung mà không có đồng bộ phù hợp.
- Không dựa vào thứ tự thực thi mapper để cập nhật trạng thái nghiệp vụ.
- Giữ thao tác độc lập giữa các phần tử khi có thể.

Ví dụ không an toàn:

~~~java
List<String> results = new ArrayList<>();

List<String> values =
    inputs.stream()
        .gather(Gatherers.mapConcurrent(8, input -> {
            String result = process(input);
            results.add(result); // Nhiều mapper có thể ghi đồng thời.
            return result;
        }))
        .toList();
~~~

Không cần collection phụ trong ví dụ này vì `toList()` đã thu thập kết quả từ pipeline theo encounter order:

~~~java
List<String> values =
    inputs.stream()
        .gather(Gatherers.mapConcurrent(8, this::process))
        .toList();
~~~

Nếu thật sự cần trạng thái dùng chung, hãy chọn cấu trúc dữ liệu thread-safe hoặc đồng bộ hóa phù hợp và đánh giá chi phí tranh chấp. Tốt nhất là để kết quả đi qua pipeline thay vì tạo thêm side effect.

## So sánh map, parallel và mapConcurrent

| Cách xử lý | Đặc điểm | Khi nên cân nhắc |
|---|---|---|
| `stream.map(mapper)` | Ánh xạ tuần tự trên stream tuần tự | Mapper nhanh, dữ liệu nhỏ hoặc cần thứ tự thực thi đơn giản |
| `stream.parallel().map(mapper)` | Xử lý song song theo cơ chế parallel stream | Công việc CPU-bound có thể chia nhỏ và kết hợp hiệu quả |
| `stream.gather(Gatherers.mapConcurrent(n, mapper))` | Mapper chạy đồng thời bằng virtual thread với giới hạn n; giữ thứ tự kết quả | Nhiều tác vụ độc lập, thường có thời gian chờ I/O |

`mapConcurrent` không phải phiên bản thay thế cho mọi trường hợp của `parallel().map()`. Hãy chọn theo bản chất công việc: chờ I/O, tính toán CPU, yêu cầu thứ tự, giới hạn dịch vụ và cách quản lý lỗi.

## Những lỗi thường gặp

| Lỗi hoặc giả định | Cách xử lý |
|---|---|
| Đặt `maxConcurrency` bằng 0 hoặc số âm | Dùng số nguyên dương; API ném `IllegalArgumentException` nếu nhỏ hơn 1. |
| Nghĩ rằng kết quả sẽ theo thứ tự hoàn thành | Kết quả giữ encounter order của stream. |
| Nghĩ concurrency là số request mỗi giây | Dùng thêm rate limiter nếu cần giới hạn tốc độ. |
| Tăng concurrency tối đa để luôn nhanh hơn | Đo tải dịch vụ, connection pool, bộ nhớ và độ trễ trước khi tăng. |
| Dùng mapper có trạng thái mutable không an toàn | Tách trạng thái theo lần gọi hoặc dùng cơ chế thread-safe. |
| Cho rằng `findFirst()` hủy ngay mọi tác vụ còn lại | API chỉ cố gắng hủy theo best effort; mapper phải có khả năng phản hồi hủy. |
| Dùng cho phép tính CPU-bound nặng mà không đo đạc | Đánh giá parallel stream hoặc executor phù hợp với số lõi CPU. |
| Nuốt exception rồi trả về null | Biểu diễn lỗi rõ ràng hoặc ném unchecked exception phù hợp. |

## Checklist khi áp dụng

- [ ] Mapper xử lý độc lập từng phần tử và có thể chạy đồng thời.
- [ ] `maxConcurrency` là số dương và phù hợp với giới hạn tài nguyên.
- [ ] Đã xác định kết quả cần giữ encounter order hay không.
- [ ] Đã có timeout và cách xử lý lỗi cho thao tác I/O.
- [ ] Mapper không ghi vào trạng thái mutable dùng chung một cách thiếu an toàn.
- [ ] Tác vụ có thể hủy đã phản hồi interruption hoặc có cơ chế cancel riêng.
- [ ] Đã phân biệt giới hạn concurrency với giới hạn tốc độ yêu cầu.
- [ ] Dự án dùng JDK 24 trở lên để sử dụng API chính thức mà không cần preview.

## Tài liệu tham khảo

- [JEP 461 – Stream Gatherers (Preview trong JDK 22)](https://openjdk.org/jeps/461)
- [JEP 473 – Stream Gatherers (Second Preview trong JDK 23)](https://openjdk.org/jeps/473)
- [JEP 485 – Stream Gatherers (Final trong JDK 24)](https://openjdk.org/jeps/485)
- [Gatherers.mapConcurrent – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html)
- [Gatherer – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html)
- [Virtual Threads – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html)

