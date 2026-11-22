# Giới hạn thời gian chờ, số lần thử lại và lượng công việc

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao một lời gọi chậm có thể làm cạn kết nối, luồng xử lý và bộ nhớ, từ đó gây lỗi dây chuyền.
2. Phân biệt **timeout cho từng thao tác**, **deadline cho toàn yêu cầu**, **retry** và **giới hạn công việc đồng thời**.
3. Chọn điều kiện thử lại, số lần thử, khoảng chờ tăng dần và jitter phù hợp với tính an toàn của thao tác.
4. Thiết kế hàng đợi có giới hạn, cơ chế từ chối sớm và backpressure để hệ thống không nhận thêm công việc vượt khả năng.
5. Áp dụng và kiểm tra các cơ chế này trong ứng dụng Java, đồng thời nhận diện những đánh đổi về độ trễ, tính đúng đắn và trải nghiệm người dùng.

Trong module **CODE_QUALITY_FUNDAMENTALS**, độ tin cậy là một trong các thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Một chương trình có logic nghiệp vụ đúng vẫn có thể thiếu tin cậy khi phụ thuộc bên ngoài treo quá lâu, thử lại vô hạn hoặc xếp công việc vào hàng đợi không giới hạn.

**Ý chính:** Mỗi yêu cầu cần có ngân sách hữu hạn về **thời gian**, **số lần thử** và **tài nguyên được sử dụng**. Ba giới hạn này phải được thiết kế cùng nhau, vì một cơ chế riêng lẻ không đủ bảo vệ hệ thống.

## 1. Sự cố bắt đầu từ một thao tác chậm

Xét một dịch vụ đặt hàng xử lý yêu cầu như sau:

~~~mermaid
flowchart LR
    C[Khách gửi yêu cầu] --> O[Order Service]
    O --> P[Payment Service]
    O --> I[Inventory Service]
    O --> D[Database]
~~~

Trong điều kiện bình thường, lời gọi kiểm tra tồn kho chỉ mất khoảng 100 ms. Một ngày, dịch vụ kho bị chậm, khiến lời gọi kéo dài 10 giây. Nếu **Order Service** vẫn đợi mà không có giới hạn thời gian:

1. Mỗi yêu cầu giữ lại một luồng xử lý hoặc một vị trí trong pool kết nối.
2. Yêu cầu mới tiếp tục đến, làm số tác vụ đang đợi tăng.
3. Hàng đợi đầy dần; độ trễ tăng ngay cả với những yêu cầu không có lỗi nghiệp vụ.
4. Nếu ứng dụng tự động thử lại mọi yêu cầu, số lời gọi tới dịch vụ kho tăng thêm và có thể làm dịch vụ đang quá tải chậm hơn.
5. Khi tài nguyên cạn, lỗi ở một phụ thuộc lan sang những phần còn lại của hệ thống.

Giả sử một hệ thống ổn định hoàn thành trung bình 100 yêu cầu/giây và mỗi yêu cầu mất 0,2 giây. Theo quan hệ gần đúng **L = λ × W** (định luật Little trong trạng thái ổn định), số yêu cầu đang xử lý trung bình vào khoảng **20**. Nếu thời gian xử lý tăng lên 2 giây trong khi vẫn duy trì được cùng thông lượng, số yêu cầu đồng thời có thể tăng lên khoảng **200**. Khi tốc độ yêu cầu đến vượt quá khả năng xử lý, giả định ổn định không còn đúng và hàng đợi có thể tiếp tục phình ra.

Thông điệp ở đây không phải “luôn giới hạn 20 hay 200 yêu cầu”, vì sức chứa thực tế cần đo. Điều quan trọng là **độ trễ tăng làm công việc đang chờ tích tụ**. Phần mềm phải biết dừng đợi, ngừng thử và từ chối công việc khi đã đạt giới hạn.

## 2. Timeout: giới hạn thời gian cho một thao tác

**Timeout** là khoảng thời gian tối đa mà một thành phần sẵn sàng chờ một thao tác nhất định trước khi coi thao tác đó không hoàn tất đúng hạn.

Trong một lời gọi mạng có thể có nhiều giai đoạn:

| Loại giới hạn | Bảo vệ điều gì? | Điều cần lưu ý |
| --- | --- | --- |
| **Connection timeout** | Thời gian thiết lập kết nối tới máy đích | Không nhất thiết bao gồm toàn bộ thời gian xử lý request |
| **Read/response timeout** | Thời gian chờ dữ liệu hoặc phản hồi, theo ngữ nghĩa của thư viện | Có thư viện giới hạn mỗi lần đọc, có thư viện giới hạn cả request; phải kiểm tra hợp đồng API |
| **Request/attempt timeout** | Thời gian cho một lần gọi tới phụ thuộc | Có thể bao gồm nhiều pha, nhưng thường không bao trùm mọi bước trước/sau lời gọi |
| **Queue wait timeout** | Thời gian công việc được phép chờ trong hàng đợi | Nếu không tính vào ngân sách tổng, yêu cầu có thể hết hạn trước khi bắt đầu xử lý |
| **Overall deadline** | Mốc thời gian cuối cùng cho toàn bộ yêu cầu nghiệp vụ | Phải trừ cả thời gian đã dùng cho xử lý, chờ retry và gọi các phụ thuộc |

Các tên gọi không đồng nghĩa tuyệt đối giữa các HTTP client, JDBC driver hoặc message broker. Khi cấu hình cần biết **giới hạn áp dụng từ lúc nào đến lúc nào**, ngoại lệ nào xuất hiện khi quá hạn và liệu thao tác phía xa có thực sự dừng hay không.

### Timeout không đồng nghĩa thao tác phía xa đã bị hủy

Khi client hết thời gian chờ, client biết rằng **mình chưa nhận được kết quả đúng hạn**. Điều đó không chứng minh máy chủ chưa thực hiện tác vụ. Ví dụ, client gửi yêu cầu thanh toán, phía server ghi giao dịch thành công nhưng kết nối đứt trước khi trả phản hồi. Nếu client thử lại như một thanh toán mới, khách hàng có nguy cơ bị tính tiền hai lần.

Vì vậy:
- Với thao tác **đọc không làm thay đổi trạng thái**, thử lại thường dễ an toàn hơn, nhưng vẫn cần tôn trọng hợp đồng thật của dịch vụ.
- Với thao tác **ghi hoặc tạo tác dụng phụ**, cần tính tới **idempotency**: lặp lại cùng một yêu cầu không tạo thêm hiệu ứng ngoài ý muốn. Có thể dùng khóa idempotency được dịch vụ nhận và lưu kết quả theo cùng khóa, hoặc cơ chế kiểm tra trạng thái giao dịch.
- Hủy một request ở phía client không tự động hoàn tác công việc đã được thực hiện ở server.

### Đặt timeout như thế nào?

Không có con số chung đúng cho mọi hệ thống. Cần kết hợp thời gian đáp ứng thực tế, độ lệch theo tải, yêu cầu người dùng, kết nối mạng và ngân sách tổng.

Ví dụ minh họa: một API phải phản hồi trong tối đa **3 giây**. Nếu phần xử lý nội bộ cần khoảng 300 ms và lời gọi kho cần một hoặc hai lần thử, timeout cho một lần gọi có thể nằm trong giới hạn nhỏ hơn 3 giây. Không hợp lý khi đặt riêng lời gọi kho 5 giây, sau đó vẫn cho phép retry nhiều lần mà không xét thời gian tổng.

Timeout quá **ngắn** làm tăng tỷ lệ lỗi giả và lần thử lại không cần thiết. Timeout quá **dài** giữ tài nguyên quá lâu. Giá trị ban đầu nên dựa vào phân phối độ trễ đo được của phụ thuộc, sau đó điều chỉnh dựa trên tỷ lệ timeout và các tình huống tải thực tế.

## 3. Deadline: ngân sách thời gian chung từ đầu tới cuối

**Deadline** là thời điểm cuối cùng mà yêu cầu được phép tiếp tục. Nếu toàn bộ thao tác phải hoàn thành trước một mốc, từng thành phần chỉ được dùng **thời gian còn lại**, không tự khởi tạo một timeout đầy đủ mới.

Giả sử yêu cầu có ngân sách 2.000 ms:

~~~text
Bắt đầu yêu cầu                                      Deadline
|---------------------------------------------------------|
0 ms                                                   2000 ms

Xác thực     Gọi A        Chờ retry     Gọi A lần 2    Xử lý kết quả
|--100 ms--|---600 ms---|---200 ms---|----700 ms----|---?---|
                                                    Còn 400 ms
~~~

Trong ví dụ, sau 1.600 ms chỉ còn **400 ms** cho xử lý cuối và mọi bước khác. Không thể tiếp tục gọi một phụ thuộc với timeout mới 2.000 ms mà vẫn giữ cam kết deadline ban đầu.

Có thể mô hình hóa ngân sách đơn giản:

~~~text
Thời gian còn lại = deadline - thời điểm hiện tại
Timeout lần gọi = min(timeout tối đa mỗi lần, thời gian còn lại)
~~~

Khi tính khoảng thời gian đã trôi qua trong cùng một tiến trình Java, nên dùng đồng hồ đơn điệu **System.nanoTime()** để tránh việc điều chỉnh đồng hồ hệ thống làm sai phép đo khoảng thời gian. Khi truyền deadline giữa các tiến trình, cần chọn hợp đồng cụ thể (chẳng hạn mốc thời gian hoặc số mili giây còn lại) và tính tới trễ mạng, chênh lệch đồng hồ và phần ngân sách cần dành cho xử lý kết quả.

**Deadline phải tính cả thời gian chờ trong queue và backoff**. Nếu yêu cầu đã hết hạn trước khi được worker lấy ra, việc tiếp tục tính toán có thể chỉ tiêu tốn tài nguyên cho kết quả không còn được người dùng cần đến.

## 4. Retry: khắc phục lỗi tạm thời nhưng không làm lỗi trầm trọng hơn

**Retry** là thực hiện lại một thao tác sau khi lần trước thất bại hoặc không có phản hồi trong thời gian cho phép. Nó hữu ích khi lỗi là **tạm thời**, chẳng hạn sự cố kết nối ngắn hoặc phụ thuộc báo đang quá tải trong chốc lát.

Retry cũng tiêu tốn tài nguyên và có thể khuếch đại sự cố. Nếu 100 yêu cầu cùng lỗi và mỗi yêu cầu được phép thử tối đa ba lần, tổng số lượt gọi có thể lên tới **300** trong tình huống xấu. Nếu ba tầng dịch vụ đều tự thử ba lần, một yêu cầu gốc có thể dẫn đến **3 × 3 × 3 = 27** lần gọi xuống tầng cuối, tùy cấu trúc và điểm thất bại.

### Chỉ retry khi vừa cần thiết vừa an toàn

| Tình huống | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Mất kết nối thoáng qua, connect timeout | Có thể thử lại có giới hạn | Sự cố có thể hết nhanh; cần biết thao tác có tạo tác dụng phụ hay không |
| HTTP 429 Too Many Requests | Chỉ thử lại khi có ngân sách, tôn trọng chỉ dẫn chờ của server | Client có thể đang gửi quá nhanh |
| HTTP 503 Service Unavailable | Có thể thử lại có giới hạn, ưu tiên chỉ dẫn **Retry-After** nếu có | Dịch vụ có thể đang quá tải hoặc bảo trì |
| HTTP 502/504 tại gateway | Có thể thử lại với thao tác an toàn và ngân sách đủ | Lỗi có thể do một phụ thuộc tạm thời |
| HTTP 400 do dữ liệu sai | Thường không retry cùng dữ liệu | Gửi lại không sửa được đầu vào |
| HTTP 401/403 | Không retry mù quáng | Cần giải quyết xác thực/phân quyền, không phải lặp request |
| HTTP 404 | Thông thường không retry trừ khi hợp đồng nói dữ liệu sẽ sớm xuất hiện | Có thể là trạng thái nghiệp vụ hợp lệ |
| Lỗi xác thực chứng chỉ hoặc cấu hình | Cần sửa cấu hình hoặc hạ tầng | Retry chỉ lặp lại một lỗi khó tự phục hồi |
| Timeout khi tạo giao dịch hoặc thanh toán | Chỉ retry nếu có cơ chế chống lặp và xác nhận trạng thái | Phía server có thể đã thực hiện tác vụ |

Danh sách là gợi ý; quyết định cuối cùng cần dựa trên **hợp đồng của API và loại lỗi cụ thể**. Đặc biệt, một request dùng phương thức HTTP POST không tự nhiên trở nên an toàn khi retry. Có những POST được thiết kế idempotent nhờ khóa idempotency, nhưng phải được phía nhận bảo đảm.

### Giới hạn số lần thử

Một retry policy cần trả lời rõ:
1. **Điều kiện nào được thử lại?** Chỉ lỗi tạm thời có thể khắc phục; không retry mọi exception.
2. **Thử tối đa bao nhiêu lần?** Phân biệt số **attempt** (bao gồm lần đầu) với số **retry** (những lần sau thất bại).
3. **Chờ bao lâu giữa các lần?** Có cần tuân thủ Retry-After từ server không?
4. **Dừng khi nào?** Hết attempt, hết deadline, request bị hủy hoặc cơ chế bảo vệ đã mở.
5. **Ai chịu trách nhiệm retry?** Tránh nhiều tầng tự thử lại lồng nhau mà không quản lý chung ngân sách.

Chỉ đặt **maxAttempts = 3** không bảo đảm yêu cầu có giới hạn thời gian. Nếu mỗi lần chờ rất lâu và giữa các lần có backoff dài, tổng thời gian vẫn vượt quá mong đợi.

### Exponential backoff và jitter

Nếu retry ngay lập tức, nhiều client có thể đồng loạt gây một làn sóng tải mới. **Exponential backoff** tăng khoảng chờ giữa các lần thử, nhưng cần có giới hạn trên để thời gian không tăng vô hạn.

Một công thức phổ biến:

~~~text
trần_chờ_n = min(trần_tối_đa, chờ_cơ_sở × 2^(n - 1))
chờ_thực_tế_n = random(0, trần_chờ_n)    // full jitter
~~~

Với chờ cơ sở 100 ms và trần 800 ms, ba khoảng trần đầu tiên sẽ là 100, 200 và 400 ms. Full jitter chọn ngẫu nhiên trong khoảng từ 0 tới trần tương ứng, giúp các client không thức dậy cùng một lúc. Đây là **một lựa chọn chính sách**, không phải bảo đảm chống quá tải; cần xem xét phân bố tải và đặc tính nghiệp vụ.

Một số response 429 hoặc 503 cung cấp **Retry-After** (số giây hoặc thời điểm HTTP). Khi có, client nên tuân thủ chỉ dẫn hợp lệ trong phạm vi deadline. Nếu server yêu cầu chờ 5 giây nhưng người dùng chỉ còn 300 ms ngân sách, đáp án hợp lý là **dừng sớm** thay vì phá deadline hoặc gọi lại trước thời gian server yêu cầu.

## 5. Ví dụ Java: GET có timeout, deadline và retry hữu hạn

Ví dụ sau minh họa một truy vấn **GET được phía cung cấp bảo đảm không tạo tác dụng phụ**. Chính sách giả định:

- Deadline toàn lời gọi: 3 giây.
- Timeout kết nối: 250 ms.
- Timeout mỗi attempt: tối đa 700 ms hoặc phần ngân sách còn lại.
- Tối đa 3 attempt (tức là tối đa 2 lần thử lại).
- Chỉ retry khi connect timeout, kết nối bị từ chối, hoặc HTTP 408/429/502/503/504.
- Với Retry-After dạng **số giây**, không retry sớm hơn chỉ dẫn của server; ví dụ giản lược này chưa xử lý dạng **HTTP-date**.
- Giữa các lần dùng exponential backoff với full jitter, dừng nếu không đủ deadline.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public final class BoundedGetClient {
    private static final int MAX_ATTEMPTS = 3;
    private static final Duration TOTAL_BUDGET = Duration.ofSeconds(3);
    private static final Duration PER_ATTEMPT = Duration.ofMillis(700);

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(250))
            .build();

    public String get(URI uri) throws IOException, InterruptedException {
        long deadline = System.nanoTime() + TOTAL_BUDGET.toNanos();
        IOException lastFailure = null;

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            long remainingNanos = deadline - System.nanoTime();
            if (remainingNanos <= 0) {
                break;
            }

            Duration requestTimeout = Duration.ofNanos(
                    Math.min(PER_ATTEMPT.toNanos(), remainingNanos));
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(requestTimeout)
                    .GET()
                    .build();

            HttpResponse<String> response = null;
            long serverWaitMillis = 0L;
            try {
                response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
            } catch (HttpTimeoutException | ConnectException transientError) {
                lastFailure = transientError;
            }
            // InterruptedException được truyền ra cho phía gọi xử lý hủy.

            if (response != null) {
                int status = response.statusCode();
                if (status >= 200 && status < 300) {
                    return response.body();
                }
                if (!isRetryable(status)) {
                    throw new IOException("HTTP non-retryable: " + status);
                }

                lastFailure = new IOException("HTTP retryable: " + status);
                if (status == 429 || status == 503) {
                    // Demo hỗ trợ Retry-After dạng số giây.
                    // Sản phẩm thật cần hỗ trợ cả HTTP-date và chính sách rõ.
                    String hint = response.headers()
                            .firstValue("Retry-After")
                            .orElse(null);
                    if (hint != null) {
                        try {
                            long seconds = Long.parseLong(hint.trim());
                            if (seconds >= 0) {
                                serverWaitMillis =
                                        TimeUnit.SECONDS.toMillis(seconds);
                            }
                        } catch (NumberFormatException ignored) {
                            // Dạng HTTP-date chưa được xử lý trong demo.
                        }
                    }
                }
            }

            if (attempt == MAX_ATTEMPTS) {
                break;
            }

            long backoffCap = Math.min(800L, 100L << (attempt - 1));
            long jitterMillis = ThreadLocalRandom.current()
                    .nextLong(backoffCap + 1);
            long delayMillis = Math.max(jitterMillis, serverWaitMillis);
            long remainingMillis = TimeUnit.NANOSECONDS.toMillis(
                    Math.max(0L, deadline - System.nanoTime()));

            if (remainingMillis <= delayMillis) {
                break; // Không đủ thời gian để thử lại hợp lệ.
            }
            Thread.sleep(delayMillis);
        }
        throw new IOException(
                "GET failed within attempt/deadline limits", lastFailure);
    }

    private static boolean isRetryable(int status) {
        return status == 408 || status == 429
                || status == 502 || status == 503 || status == 504;
    }
}
~~~

**Phạm vi ví dụ:** Mã dùng API của Java 17, không cần thư viện HTTP bên ngoài. Nó tập trung vào cách phối hợp ba giới hạn, **không phải HTTP client sẵn sàng đưa vào production**. Trong sản phẩm thật cần đánh giá thêm phân loại IOException theo thư viện, lỗi proxy/TLS, Retry-After dạng ngày, connection pool, telemetry, hủy request và nguồn cấu hình; kiểm thử với server giả lập. Nên cấu hình các ngưỡng theo dịch vụ, lưu ý **Thread.sleep** chiếm một thread trong thời gian chờ nên không thích hợp khi có rất nhiều request đồng thời. Có thể dùng cách thực thi bất đồng bộ và scheduler khi cần mở rộng.

Đoạn mã không cố retry mọi **IOException**: lỗi chứng chỉ hoặc cấu hình có thể không phải sự cố tạm thời. Nếu request đã bị ngắt (**InterruptedException**), phương thức truyền lỗi ra thay vì nuốt rồi thử tiếp; phía gọi chịu trách nhiệm xử lý hủy đúng cách.

### Vì sao phải kiểm tra cả số lần và deadline?

Giả sử attempt thứ nhất hết 700 ms, sau đó chờ 100 ms; attempt thứ hai mất 700 ms và chờ 200 ms. Dù còn một attempt, chương trình phải kiểm tra **ngân sách còn lại** trước khi bắt đầu. Khi ngân sách quá ít, không có ích khi xếp thêm một lần thử chỉ để nó lập tức hết hạn.

Với workflow dài hơn gồm nhiều dịch vụ, đoạn minh họa còn cần được đặt trong **deadline chung của request gốc**. Một lời gọi client tự cấp 3 giây sẽ không đủ nếu phía gọi chỉ còn 500 ms; khi đó phải truyền phần ngân sách còn lại vào client.

## 6. Giới hạn lượng công việc: tránh hệ thống bị ngập khi đến quá nhiều yêu cầu

Timeout và retry kiểm soát lời gọi bên ngoài; chúng **không tự ngăn** một ứng dụng nhận nhiều việc hơn khả năng xử lý.

Một hệ thống thường có các giới hạn tài nguyên:
- Số thread và connection đang sử dụng.
- Số lời gọi đồng thời tới dịch vụ phụ thuộc.
- Số phần tử đang đợi trong queue.
- Bộ nhớ dành cho yêu cầu và dữ liệu đệm.
- Tốc độ ghi cơ sở dữ liệu hoặc gọi API có quota.

Khi số việc được nhận vượt quá tốc độ xử lý trong một thời gian dài, **hàng đợi không giới hạn** có thể che giấu quá tải trong ngắn hạn nhưng dẫn đến độ trễ cao, sử dụng bộ nhớ lớn hoặc OOM.

### Ba cơ chế khác nhau

| Cơ chế | Giới hạn điều gì? | Dùng khi nào? |
| --- | --- | --- |
| **Concurrency limit / bulkhead** | Số việc đang thực thi đồng thời | Bảo vệ thread, connection pool và phụ thuộc có sức chứa hữu hạn |
| **Bounded queue** | Số việc được phép đợi | Không để backlog tăng vô hạn; tạo điểm từ chối rõ ràng |
| **Rate limit** | Số yêu cầu được nhận trong một khoảng thời gian | Bảo vệ quota và điều tiết tốc độ đầu vào |
| **Backpressure** | Tín hiệu để phía tạo việc giảm tốc hoặc dừng | Các pipeline, stream hoặc producer-consumer có khả năng phối hợp |
| **Load shedding / rejection** | Từ chối việc vượt mức khi không thể chờ thêm | Giữ dịch vụ hoạt động trong khả năng thay vì sụp đổ toàn bộ |

Rate limit và concurrency limit **không tương đương**. 50 request/giây có thể dễ xử lý nếu mỗi request mất 10 ms nhưng gây quá tải nếu mỗi request giữ tài nguyên 20 giây. Ngược lại, giới hạn 10 yêu cầu đồng thời không trực tiếp ràng buộc tổng số yêu cầu/giây khi mỗi việc chạy cực nhanh.

### Ví dụ Java: ThreadPoolExecutor với queue hữu hạn

~~~java
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class BoundedJobRunner implements AutoCloseable {
    private final ThreadPoolExecutor executor =
            new ThreadPoolExecutor(
                    4, 4,
                    0L, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(32),
                    new ThreadPoolExecutor.AbortPolicy());

    public boolean trySubmit(Runnable job) {
        Objects.requireNonNull(job, "job");
        try {
            executor.execute(job);
            return true;
        } catch (RejectedExecutionException rejected) {
            return false;
        }
    }

    @Override
    public void close() {
        executor.shutdown();
    }
}
~~~

Với cấu hình minh họa, tối đa **4 tác vụ đang thực thi** và **32 tác vụ chờ** tại một thời điểm; khi cả worker và queue đều bận, tác vụ mới bị từ chối bằng chính sách **AbortPolicy** và được chuyển thành giá trị **false** ở API này. Nếu executor đã đóng, việc nộp mới cũng bị từ chối.

Ứng dụng phía trên cần xác định phản hồi thích hợp khi nhận **false**: trả trạng thái quá tải có thể hiểu được, yêu cầu client giảm tốc, hoặc chuyển sang kênh lưu trữ công việc bền vững nếu nghiệp vụ cho phép. **Không nên âm thầm bỏ việc** mà đã hứa sẽ hoàn thành.

**Các giá trị 4 và 32 chỉ để minh họa**, không phải khuyến nghị chung. Kích thước pool và queue phải dựa trên tải, thời gian thực thi, giới hạn kết nối và ngân sách độ trễ. Queue lớn không làm hệ thống có thêm năng lực xử lý; nó chỉ cho phép nhiều yêu cầu đợi hơn.

**Lưu ý Java:** Các tiện ích tạo thread pool có thể dùng queue không giới hạn tùy cấu hình. Với thành phần cần chống quá tải, phải kiểm tra cụ thể loại queue, sức chứa và chính sách từ chối của executor đang dùng.

### Queue cũng phải tôn trọng deadline

Một yêu cầu có ngân sách 1 giây mà nằm trong queue 2 giây đã hết hạn trước khi worker xử lý. Nếu tiếp tục, hệ thống dành tài nguyên cho kết quả mà client có thể không còn nhận.

Thiết kế thực tế cần:
- Ghi nhận **thời điểm đến** hoặc deadline của từng công việc.
- Kiểm tra thời gian chờ khi lấy việc ra khỏi queue và trước khi gây tác dụng phụ.
- Không giữ chỗ hoặc khóa tài nguyên cho những việc đã bị hủy.
- Quy định rõ cách xử lý việc bị từ chối/hết hạn và cách người dùng biết kết quả.
- Với công việc nền quan trọng, có thể cần queue bền vững, cơ chế xác nhận, retry và dead-letter queue thay vì chỉ dùng queue trong RAM.

## 7. Backpressure và load shedding: phản hồi khi không đủ năng lực

**Backpressure** là khả năng bên xử lý chậm phát tín hiệu hoặc áp đặt giới hạn để bên tạo việc giảm tốc. Trong một pipeline có producer và consumer, nó giúp tránh tích lũy công việc không giới hạn. Nếu producer không có khả năng giảm tốc, phía nhận phải quyết định từ chối, gộp hoặc bỏ một số việc theo hợp đồng.

**Load shedding** là chủ động không nhận công việc vượt quá mức chịu tải, thường ưu tiên giữ các luồng quan trọng vẫn hoạt động. Ví dụ:
- API có thể trả **429 Too Many Requests** khi một client vượt quota.
- Dịch vụ đang quá tải có thể trả **503 Service Unavailable** và hướng dẫn thử lại hợp lý.
- Một màn hình gợi ý sản phẩm có thể bỏ qua đề xuất phụ khi dịch vụ gợi ý chậm, nếu sản phẩm cho phép.
- Hệ thống thanh toán không nên tùy tiện trả “thành công” bằng dữ liệu fallback hoặc bỏ qua kiểm tra bắt buộc.

Giới hạn cần gắn với ưu tiên nghiệp vụ: tác vụ thiết yếu có thể dành một phần năng lực riêng, còn tác vụ nền ít quan trọng được điều tiết hoặc trì hoãn. Điều này liên quan đến **bulkhead**: cô lập tài nguyên để lỗi ở một nhóm không chiếm toàn bộ thread/connection của nhóm khác.

~~~mermaid
flowchart TD
    A[Yêu cầu đến] --> B{Còn deadline?}
    B -- Không --> C[Trả kết quả hết hạn]
    B -- Có --> D{Còn năng lực nhận?}
    D -- Không --> E[Từ chối có kiểm soát hoặc backpressure]
    D -- Có --> F[Thực thi trong giới hạn]
    F --> G{Lỗi tạm thời và an toàn retry?}
    G -- Không --> H[Trả kết quả hoặc lỗi rõ ràng]
    G -- Có --> I{Còn attempt và deadline?}
    I -- Có --> J[Chờ backoff có jitter]
    J --> F
    I -- Không --> H
~~~

Sơ đồ mô tả cách ra quyết định; triển khai thực tế có thể yêu cầu kiểm tra năng lực **trước mỗi attempt**, kể cả các lần retry. Một lần thử lại không có quyền vượt qua quota hay pool đang đầy.

## 8. Tránh một hệ thống tự làm sự cố tồi tệ hơn

### 8.1. Retry storm

Nếu nhiều client cùng thất bại rồi đồng loạt retry, dịch vụ vừa phục hồi có thể bị quá tải lần nữa. Giải pháp phối hợp gồm giới hạn attempt, backoff có jitter, tôn trọng Retry-After, hạn mức retry toàn cục hoặc **retry budget**. Retry budget giới hạn tỷ lệ/tổng số lần retry so với lưu lượng phục vụ, để retry không thống trị công suất.

Cần chú ý retry ở nhiều tầng. Nếu Gateway, Order Service và SDK phía dưới đều retry, một lỗi ở tầng sâu có thể bị nhân lên nhiều lần. Nên xác định rõ tầng chịu trách nhiệm chính, tránh retry chồng nhau thiếu kiểm soát.

### 8.2. Circuit breaker

**Circuit breaker** có thể tạm ngừng gửi yêu cầu tới phụ thuộc đang lỗi liên tục. Sau một thời gian, nó cho phép một số yêu cầu kiểm tra xem phụ thuộc đã phục hồi chưa.

- **Closed:** tiếp tục gọi bình thường và theo dõi lỗi.
- **Open:** từ chối nhanh các lời gọi mới tới phụ thuộc bị lỗi.
- **Half-open:** cho một số lời gọi thử nghiệm, quyết định phục hồi hay mở lại.

Circuit breaker không thay timeout hay giới hạn tải. Ngưỡng mở, thời gian chờ và loại lỗi cần dựa trên telemetry; mở breaker quá nhạy có thể làm từ chối cả khi phụ thuộc còn khả năng phục vụ. Với nhiều instance, cơ chế cũng cần tránh chúng đồng loạt kiểm tra ngay khi half-open.

### 8.3. Bulkhead và cô lập tài nguyên

Nếu mọi thao tác đều dùng chung một pool 100 thread, một dịch vụ phụ thuộc chậm có thể giữ hết thread và làm cả health check hay tác vụ thiết yếu bị chậm. Tách hạn mức theo nhóm công việc hoặc phụ thuộc giúp khoanh vùng sự cố. Đổi lại, quá nhiều pool nhỏ có thể làm giảm khả năng tận dụng công suất. Cần chọn ranh giới cô lập theo mức rủi ro và tải thực tế.

### 8.4. Fallback có ý nghĩa nghiệp vụ

Fallback chỉ đáng dùng khi kết quả thay thế vẫn đáp ứng hợp đồng chấp nhận được. Ví dụ, một danh sách gợi ý có thể tạm bỏ phần cá nhân hóa nhưng vẫn hiện các sản phẩm phổ biến. Nhưng khi không xác minh được quyền truy cập hoặc kết quả thanh toán, trả dữ liệu giả hoặc coi thành công là sai và nguy hiểm. Cần nói rõ phần nào đã bị giảm chất lượng dịch vụ.

## 9. Chọn cấu hình dựa trên số liệu và rủi ro

Không có một bộ thông số timeout, retry và queue có thể sao chép cho mọi dịch vụ. Hãy trả lời:

| Cần quyết định | Dữ liệu và câu hỏi nên xem |
| --- | --- |
| **Timeout cho mỗi attempt** | Độ trễ p50/p95/p99 của phụ thuộc dưới tải bình thường và khi tăng tải; số request bị timeout giả |
| **Deadline toàn yêu cầu** | SLO người dùng, thời gian xử lý nội bộ, các bước gọi liên tiếp/song song |
| **Max attempts** | Xác suất thành công ở lần tiếp theo, mức nguy cơ tác dụng phụ, số lượt gọi phụ trội khi lỗi |
| **Backoff và jitter** | Thời gian phục hồi phụ thuộc, chỉ dẫn Retry-After, nguy cơ đồng bộ client và ngân sách tổng |
| **Concurrency limit** | CPU, bộ nhớ, connection pool, độ trễ và năng lực xử lý thực khi tăng concurrent requests |
| **Queue capacity** | Thời gian đợi chấp nhận được, kích thước mỗi tác vụ, khả năng chịu backlog và deadline |
| **Rate limit** | Quota phía dưới, tính công bằng giữa client, mô hình tải đột biến và ưu tiên nghiệp vụ |
| **Fallback / từ chối** | Tác vụ có thể trì hoãn hay bỏ qua không, người dùng có cần biết kết quả chính xác ngay không? |

Ví dụ, nếu giới hạn phản hồi người dùng là **2 giây**, không nên dành toàn bộ 2 giây cho mỗi attempt, cho phép 3 retry rồi còn một queue dài. Một ngân sách phải bao trùm mọi giai đoạn. Khi có nhiều phụ thuộc độc lập chạy song song, cần tính thời gian chờ tổng theo nhánh chậm nhất và chi phí kết hợp kết quả, thay vì đơn giản cộng tất cả timeout.

### Các chỉ số cần quan sát

- **Độ trễ:** phân phối p50/p95/p99 cho request gốc và từng phụ thuộc, bao gồm thời gian queue.
- **Kết quả:** tỷ lệ thành công, timeout, từ chối, trả lỗi do phụ thuộc, hủy request.
- **Retry:** số attempt cho mỗi request, tỷ lệ retry thành công, số retry bị dừng vì deadline; tránh chỉ đo “retry thành công” mà bỏ chi phí và độ trễ.
- **Sức chứa:** số tác vụ đang chạy, độ dài queue, thời gian chờ, thread/connection đang dùng, CPU và bộ nhớ.
- **Độ ổn định:** tỷ lệ breaker open, số yêu cầu bị load shedding, tỷ lệ lỗi thay đổi khi lưu lượng tăng.

Khi log và xuất metrics, không gắn các trường có cardinality quá cao (như requestId duy nhất) vào nhãn metric theo cách gây nổ số chuỗi thời gian. Dùng trace hoặc log có kiểm soát cho từng yêu cầu và bảo vệ dữ liệu nhạy cảm.

## 10. Kiểm thử độ tin cậy thay vì chỉ thử đường thành công

Các giới hạn này cần được kiểm tra bằng các tình huống có thể tái hiện:

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Phụ thuộc trả ngay kết quả thành công | Không retry; trả kết quả và giải phóng tài nguyên |
| Phụ thuộc chậm vượt timeout từng lần | Attempt kết thúc theo giới hạn và hệ thống quyết định retry/dừng theo chính sách |
| Phụ thuộc luôn trả HTTP 503 | Số attempt hữu hạn; backoff; cuối cùng lỗi rõ ràng |
| HTTP 429 với Retry-After dài hơn deadline | Không retry sớm hơn chỉ dẫn; dừng khi ngân sách không đủ |
| Trả HTTP 400 vì dữ liệu đầu vào sai | Không thử lại cùng request |
| Thanh toán đã hoàn tất nhưng response bị mất | Không tạo giao dịch thứ hai; kiểm tra cơ chế idempotency hoặc truy vấn trạng thái |
| Queue đầy và tất cả worker bận | Từ chối nhanh; không tăng bộ nhớ vô hạn; phản hồi theo hợp đồng |
| Công việc hết deadline khi còn ở queue | Không tiếp tục công việc đã hết hạn khi không còn phù hợp |
| Thread bị ngắt hoặc request bị hủy | Dừng chờ và truyền tín hiệu hủy; không nuốt ngắt |
| Nhiều client cùng gặp lỗi | Retry được phân tán bởi jitter và không vượt ngân sách được thiết kế |
| Phụ thuộc phục hồi sau sự cố | Hệ thống tăng lưu lượng trở lại có kiểm soát; không có đợt retry dồn bất thường |

Nên dùng **fake HTTP server**, stub phụ thuộc, đồng hồ và bộ lập lịch có thể điều khiển để kiểm tra thời gian, số lần gọi và kết quả một cách ổn định. Test thời gian sử dụng **Thread.sleep** dài có thể chậm và không ổn định vì phụ thuộc khả năng lập lịch của hệ điều hành. Với kiểm thử hiệu năng và quá tải, dùng môi trường đại diện để quan sát queue, độ trễ và tỷ lệ lỗi ở nhiều mức tải.

### Một ví dụ test chính sách retry ở mức logic

Để kiểm tra quyết định retry mà không cần gọi mạng thật, có thể tách quy tắc thành một hàm đơn giản:

~~~java
final class RetryDecisions {
    private RetryDecisions() {}

    static boolean shouldRetryStatus(
            int status, int attempt, int maxAttempts, boolean safeToReplay) {
        if (!safeToReplay || attempt >= maxAttempts) {
            return false;
        }
        return status == 408 || status == 429
                || status == 502 || status == 503 || status == 504;
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class RetryDecisionsTest {
    @Test
    void retriesTransientStatusOnlyWhenBudgetAllows() {
        assertTrue(RetryDecisions.shouldRetryStatus(503, 1, 3, true));
        assertFalse(RetryDecisions.shouldRetryStatus(503, 3, 3, true));
        assertFalse(RetryDecisions.shouldRetryStatus(400, 1, 3, true));
        assertFalse(RetryDecisions.shouldRetryStatus(503, 1, 3, false));
    }
}
~~~

Hàm này **chỉ mô tả một phần chính sách**: mã trạng thái, số lần thử và khả năng phát lại. Deadline, Retry-After, loại lỗi, bảo vệ quá tải và hủy tác vụ vẫn phải được phối hợp ở lớp thực thi. Một unit test xanh cho hàm này không chứng minh client HTTP hoàn chỉnh sẽ hoạt động an toàn.

## 11. Tình huống thực hành: đặt hàng lúc hệ thống kho chậm

Một ứng dụng nhận khoảng 150 yêu cầu đặt hàng/giây. Khi hệ thống kho bị chậm từ 100 ms lên 5 giây, nhóm ghi nhận:

- Timeout mặc định là 30 giây.
- Mỗi lỗi gọi kho được retry ngay 5 lần.
- Có một hàng đợi nhận việc không giới hạn.
- API vẫn nhận request mới vì chưa đạt giới hạn CPU, nhưng số thread/connection dần cạn.
- Client đôi khi tự gửi lại yêu cầu đặt hàng khi không thấy phản hồi.

Đây là tình huống giả định, nhưng phản ánh kiểu sự cố thường gặp khi nhiều giới hạn không phối hợp.

### Câu hỏi

1. Vì sao CPU chưa cao vẫn có thể làm API ngừng phục vụ?
2. Retry ngay 5 lần có thể gây điều gì cho hệ thống kho?
3. Nếu khách gửi lại yêu cầu tạo đơn khi lần trước đã lưu đơn nhưng chưa trả response, hệ thống cần cơ chế gì?
4. Bạn sẽ thiết kế những giới hạn nào ở Order Service, worker pool và lời gọi Inventory Service?
5. Làm sao chứng minh cấu hình mới tốt hơn chỉ tăng kích thước thread pool?

### Hướng phân tích

**Thứ nhất,** cạn thread và connection có thể xảy ra khi nhiều tác vụ chủ yếu đang chờ I/O, ngay cả khi CPU thấp. Các yêu cầu mới tiếp tục tăng backlog, làm thời gian chờ kéo dài.

**Thứ hai,** retry liên tục nhân lưu lượng tới dịch vụ đang chậm. Cần phân loại lỗi, chọn số attempt ít và phù hợp, dùng backoff có jitter, kiểm soát tổng ngân sách và xem hướng dẫn từ dịch vụ kho.

**Thứ ba,** tạo đơn cần xử lý chống lặp ở mức nghiệp vụ: khóa idempotency cho lệnh tạo đơn, khóa duy nhất hoặc truy vấn trạng thái theo mã yêu cầu, tùy hợp đồng. Chỉ dựa vào việc client “không gửi lại” sẽ không đủ an toàn.

**Thứ tư,** có thể giới hạn số lời gọi kho đồng thời, dùng queue hữu hạn, đặt deadline cho yêu cầu, timeout từng attempt thấp hơn deadline và trả từ chối rõ ràng khi hết sức chứa. Nếu việc tạo đơn phải được bảo đảm tiếp nhận bất đồng bộ, cần thiết kế lưu trữ bền vững và thông báo trạng thái, không chỉ để job trong bộ nhớ.

**Thứ năm,** so sánh trước/sau bằng các thước đo: p95/p99, tỷ lệ timeout, số request bị từ chối có kiểm soát, số retry trung bình, độ dài queue, thread/connection sử dụng và số đơn bị tạo trùng. Tăng pool đơn thuần có thể hoãn sự cố nhưng cũng có thể dồn thêm tải vào dịch vụ kho.

## 12. Những sai lầm thường gặp

1. **Đặt timeout nhưng không giới hạn retry.** Tổng thời gian và tổng tải vẫn có thể vượt kiểm soát.
2. **Giới hạn retry nhưng không có deadline.** Mỗi attempt và mỗi lần ngủ vẫn có thể rất lâu.
3. **Retry tất cả exception.** Lỗi cấu hình, dữ liệu không hợp lệ hoặc thao tác có tác dụng phụ không được xử lý đúng.
4. **Retry đồng thời ở nhiều tầng.** Số lời gọi tới phụ thuộc tăng theo cấp số nhân trong tình huống xấu.
5. **Chờ cố định không có jitter.** Các client cùng lỗi dễ tạo làn sóng gọi lại.
6. **Dùng queue không giới hạn.** Tăng độ trễ và bộ nhớ trong khi năng lực xử lý thực tế không tăng.
7. **Từ chối công việc mà không báo người gửi.** Người dùng tin việc đã được nhận, dễ mất dữ liệu nghiệp vụ.
8. **Không tính thời gian queue vào deadline.** Worker làm việc trên yêu cầu đã hết hạn.
9. **Coi timeout là bằng chứng server chưa xử lý.** Tạo tác dụng phụ trùng khi phát lại lệnh ghi.
10. **Thiết lập một con số cho mọi phụ thuộc.** Bỏ qua đặc điểm kết nối, SLO và rủi ro của từng luồng.
11. **Chỉ đo trung bình.** Không nhìn thấy độ trễ đuôi và dấu hiệu cạn tài nguyên.
12. **Bỏ qua quy trình hủy.** Tiếp tục giữ tài nguyên sau khi client hoặc upstream đã ngừng chờ.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Một request có deadline 1.000 ms, đã mất 850 ms. Có nên bắt đầu một lời gọi với timeout 800 ms?

*Gợi ý:* Không thể cấp tiếp 800 ms mà vẫn đáp ứng deadline. Phải dùng tối đa phần ngân sách còn lại, đồng thời dành đủ thời gian cho hoàn tất hoặc trả lỗi. Nếu phần còn lại không đủ để thực hiện có ích, nên dừng.

**Câu 2.** Một API thanh toán timeout sau khi gửi request. Có thể retry ngay vì timeout được coi là lỗi mạng?

*Gợi ý:* Không tự động. Cần xác minh thao tác idempotent hoặc có cơ chế chống lặp, vì server có thể đã ghi giao dịch thành công.

**Câu 3.** Tại sao cấu hình pool 8 thread và queue 100.000 phần tử không chắc giúp hệ thống đáng tin cậy hơn pool 8 thread và queue 100 phần tử?

*Gợi ý:* Queue lớn có thể tăng thời gian chờ và bộ nhớ mà không tăng tốc độ phục vụ. Cần tính deadline, kích thước công việc và cách báo quá tải.

**Câu 4.** HTTP 429 kèm Retry-After 10 giây, nhưng yêu cầu còn 2 giây. Nên làm gì?

*Gợi ý:* Không thử lại trước thời gian server yêu cầu. Nếu deadline không đủ thì dừng, báo lỗi phù hợp và để phía gọi quyết định bước tiếp theo.

**Câu 5.** Vì sao phải kiểm tra cả tỷ lệ retry thành công và tổng số retry được thực hiện?

*Gợi ý:* Retry có thể tăng thành công nhưng tạo tải phụ lớn, làm phụ thuộc phục hồi chậm và tăng độ trễ cho mọi người dùng.

**Câu 6.** Giới hạn 50 request/giây có thay cho giới hạn 10 yêu cầu đồng thời được không?

*Gợi ý:* Không. Một giới hạn kiểm soát tốc độ đầu vào, giới hạn còn lại kiểm soát số việc đang chiếm tài nguyên; thời gian phục vụ quyết định mức công việc tích lũy.

## Ghi nhớ

**Giới hạn thời gian chờ, số lần thử lại và lượng công việc** là ba cơ chế bảo vệ lẫn nhau. Timeout và deadline giúp yêu cầu ngừng đợi đúng lúc; retry có chọn lọc, hữu hạn và có jitter tăng cơ hội vượt qua lỗi tạm thời mà không khuếch đại quá tải; concurrency limit, queue hữu hạn, backpressure và load shedding giữ cho công việc nằm trong năng lực xử lý. Một thiết kế đáng tin cậy còn phải tôn trọng hợp đồng nghiệp vụ, idempotency, khả năng hủy và quan sát hệ thống. Những con số cấu hình cần được xác nhận bằng **độ trễ, tải thực tế, tỷ lệ lỗi và kiểm thử tình huống thất bại**, thay vì sao chép một giá trị mặc định cho mọi dịch vụ.
