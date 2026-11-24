# Biến đổi, lọc và làm giàu dữ liệu trong chuỗi xử lý

Một message đi vào ứng dụng thường chưa có hình dạng phù hợp để mọi consumer sử dụng ngay. Dữ liệu có thể mang tên trường từ hệ thống đối tác, chứa khoảng trắng, dùng mã trạng thái nội bộ hoặc thiếu thông tin tham chiếu. Một chuỗi xử lý tốt sẽ chuẩn hóa dữ liệu, loại bỏ hoặc cách ly bản ghi không đạt điều kiện, rồi bổ sung thông tin cần thiết trước khi phát event đầu ra.

Spring Cloud Stream kết hợp mô hình hàm của Spring Cloud Function để ghép các bước xử lý bằng tên bean. Mỗi Function đảm nhiệm một trách nhiệm rõ ràng; output của bước trước trở thành input của bước tiếp theo. Với luồng dữ liệu liên tục, có thể dùng reactive function nhận và trả về `Flux<T>` để biến đổi, lọc và gọi dịch vụ bổ sung dữ liệu mà vẫn giữ được cơ chế backpressure.

Trong mô hình imperative, `Function<T, R>` được gọi cho từng event. Với reactive function `Function<Flux<T>, Flux<R>>`, framework truyền tham chiếu tới luồng dữ liệu vào function để thiết lập pipeline; các toán tử Reactor sau đó xử lý từng phần tử khi luồng được tiêu thụ. Vì vậy, không viết reactive function như thể framework sẽ gọi lại phương thức một lần cho từng record.

## 1. Nhìn chuỗi xử lý như các bước có hợp đồng kiểu dữ liệu

Giả sử hệ thống nhận đơn hàng từ một đối tác. Payload đầu vào có thể dùng tên trường và định dạng riêng của đối tác. Ứng dụng cần:

1. Chuẩn hóa mã đơn hàng, mã khách hàng, tiền và currency.
2. Lọc các bản ghi không đủ điều kiện nghiệp vụ.
3. Tra cứu tên và phân nhóm khách hàng để làm giàu dữ liệu.
4. Phát event đã chuẩn hóa tới destination dành cho các consumer tiếp theo.

~~~text
orders.raw
    |
    v
+--------------------+
| normalizeOrder     |
| Chuẩn hóa dữ liệu  |
+--------------------+
    |
    v
+--------------------+
| filterValidOrder   |
| Lọc bản ghi hợp lệ |
+--------------------+
    |
    v
+--------------------+
| enrichOrder        |
| Bổ sung thông tin  |
+--------------------+
    |
    v
orders.enriched
~~~

Mỗi bước nên có kiểu đầu vào và đầu ra rõ ràng:

| Bước | Input | Output | Trách nhiệm |
|---|---|---|---|
| `normalizeOrder` | `RawOrder` | `NormalizedOrder` | Chuẩn hóa biểu diễn dữ liệu |
| `filterValidOrder` | `NormalizedOrder` | `NormalizedOrder` | Chỉ giữ bản ghi đạt điều kiện |
| `enrichOrder` | `NormalizedOrder` | `EnrichedOrder` | Bổ sung dữ liệu từ nguồn tham chiếu |

Hợp đồng kiểu dữ liệu giúp phát hiện lỗi ghép hàm ngay khi khởi động hoặc biên dịch. Nếu bước đầu trả `NormalizedOrder`, bước tiếp theo phải nhận đúng kiểu đó. Không nên để mỗi function tự đọc lại broker hoặc tự tìm destination; việc vận chuyển thuộc binding và binder, còn function tập trung vào xử lý dữ liệu.

## 2. Phân biệt biến đổi, lọc và làm giàu

Ba thao tác thường xuất hiện cùng nhau nhưng có mục đích khác nhau.

| Thao tác | Câu hỏi | Ví dụ |
|---|---|---|
| Biến đổi (transform) | Dữ liệu cần đổi biểu diễn như thế nào? | Trim mã đơn, chuẩn hóa currency thành chữ hoa |
| Lọc (filter) | Bản ghi có được phép đi tiếp không? | Loại đơn có tổng tiền không dương hoặc thiếu order ID |
| Làm giàu (enrich) | Cần thêm dữ liệu nào để consumer xử lý? | Tra cứu tên khách hàng hoặc nhóm khách hàng |

Không nên dùng một function lớn để vừa đổi định dạng, vừa kiểm tra quy tắc, vừa gọi nhiều API. Khi tách thành các bước, có thể kiểm thử từng trách nhiệm, thay đổi một bước mà ít ảnh hưởng bước khác và xác định chính xác nơi phát sinh lỗi.

Lọc cũng cần có chính sách rõ ràng. Bỏ qua một bản ghi không hợp lệ có thể phù hợp với dữ liệu telemetry hoặc dữ liệu tùy chọn. Với đơn hàng, thanh toán hoặc dữ liệu tài chính, bản ghi bị loại thường cần được ghi nhận hoặc đưa vào quarantine để điều tra. Không âm thầm loại bỏ dữ liệu quan trọng chỉ vì dùng toán tử `filter`.

## 3. Định nghĩa kiểu dữ liệu cho từng giai đoạn

Không nên dùng một DTO duy nhất cho mọi giai đoạn nếu ý nghĩa của dữ liệu đã thay đổi. Tạo kiểu riêng giúp phân biệt dữ liệu thô từ đối tác với dữ liệu đã chuẩn hóa và event cuối cùng.

~~~java
import java.math.BigDecimal;

public record RawOrder(
    String externalOrderNumber,
    String customerCode,
    BigDecimal amount,
    String currencyCode
) {}

public record NormalizedOrder(
    String orderId,
    String customerId,
    BigDecimal total,
    String currency
) {}

public record CustomerInfo(
    String customerId,
    String displayName,
    String segment
) {}

public record EnrichedOrder(
    String orderId,
    String customerId,
    String customerName,
    String customerSegment,
    BigDecimal total,
    String currency
) {}
~~~

`RawOrder` phản ánh cấu trúc nhận từ nguồn. `NormalizedOrder` có tên trường và định dạng thống nhất trong nội bộ pipeline. `EnrichedOrder` chứa các thuộc tính cần cho consumer, bao gồm thông tin khách hàng được tra cứu.

Trong ứng dụng thật, các record có thể nằm trong package riêng. Hãy coi kiểu dữ liệu giữa các function là hợp đồng nội bộ của pipeline; event phát ra broker vẫn cần được thiết kế theo contract công khai của service.

## 4. Biến đổi dữ liệu bằng Function

Bước chuẩn hóa nên thực hiện những phép biến đổi xác định, không phụ thuộc vào trạng thái bên ngoài. Ví dụ, bỏ khoảng trắng ở hai đầu, chuẩn hóa currency và giữ nguyên giá trị tiền chính xác bằng `BigDecimal`.

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
public class OrderPipelineFunctions {

    @Bean
    Function<Flux<RawOrder>, Flux<NormalizedOrder>> normalizeOrder() {
        return rawOrders -> rawOrders.map(raw -> new NormalizedOrder(
                trimToNull(raw.externalOrderNumber()),
                trimToNull(raw.customerCode()),
                raw.amount(),
                normalizeCurrency(raw.currencyCode())
            ));
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private static String normalizeCurrency(String value) {
        if (value == null) {
            return null;
        }

        return value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Function trên chỉ đổi biểu diễn. Nó không tự quyết định rằng đơn hàng có hợp lệ hay không. Việc tách validation/lọc ra bước sau giúp quy tắc nghiệp vụ có tên và có thể kiểm thử độc lập.

Không nên tự ý thay đổi ý nghĩa dữ liệu trong bước normalize. Ví dụ, nếu đối tác gửi tiền theo đơn vị cent, cần chuyển đổi theo contract đã thỏa thuận; không thể mặc định nhân hoặc chia 100 chỉ dựa vào tên trường. Với currency, hãy xác định đơn vị và số chữ số thập phân theo quy tắc tiền tệ.

## 5. Lọc bản ghi không đạt điều kiện

Với luồng reactive, có thể dùng `Flux.filter` để chỉ phát các phần tử đạt predicate. Thêm bean method sau vào bên trong lớp `OrderPipelineFunctions` đã khai báo ở phần trước:

~~~java
// Method đặt bên trong OrderPipelineFunctions
@Bean
Function<Flux<NormalizedOrder>, Flux<NormalizedOrder>> filterValidOrder() {
    return orders -> orders.filter(order ->
        order.orderId() != null
            && !order.orderId().isBlank()
            && order.customerId() != null
            && !order.customerId().isBlank()
            && order.total() != null
            && order.total().signum() > 0
            && order.currency() != null
            && order.currency().matches("[A-Z]{3}")
    );
}
~~~

Predicate trên minh họa điều kiện tối thiểu: có mã đơn, mã khách hàng, tổng tiền dương và currency dạng ba chữ cái viết hoa. Quy tắc thực tế phải theo nghiệp vụ và schema của hệ thống.

`filter` loại phần tử không đạt điều kiện khỏi luồng. Nó không tự tạo DLQ, không lưu bản ghi lỗi và không phát cảnh báo. Nếu cần điều tra dữ liệu bị loại, hãy ghi metric hoặc chuyển bản ghi lỗi sang một luồng quarantine được thiết kế riêng. Không nên log toàn bộ payload nếu có dữ liệu nhạy cảm.

Cũng cần phân biệt validation với lọc nghiệp vụ:

- Validation xác định payload có đúng cấu trúc và kiểu dữ liệu hay không.
- Lọc nghiệp vụ xác định bản ghi có được tiếp tục trong pipeline hay không.
- Lỗi kỹ thuật như timeout khi tra cứu không phải là điều kiện filter; nó cần đi theo error handling.

Không dùng `filter` để che giấu exception. Nếu một phép kiểm tra không thể hoàn thành vì dịch vụ phụ thuộc bị lỗi, pipeline phải thể hiện lỗi đó để có thể retry hoặc phục hồi.

## 6. Làm giàu dữ liệu bằng nguồn tham chiếu

Bước làm giàu thường cần gọi một service hoặc kho dữ liệu khác. Ví dụ, lấy tên và phân khúc khách hàng từ Customer Directory.

Với reactive pipeline, định nghĩa adapter trả về `Mono<CustomerInfo>`:

~~~java
import reactor.core.publisher.Mono;

public interface CustomerDirectory {
    Mono<CustomerInfo> findById(String customerId);
}
~~~

Function làm giàu nhận luồng đơn hàng đã chuẩn hóa, tra cứu khách hàng và tạo kiểu dữ liệu đầu ra:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class EnrichmentFunctions {

    @Bean
    Function<Flux<NormalizedOrder>, Flux<EnrichedOrder>> enrichOrder(
            CustomerDirectory directory) {

        return orders -> orders.concatMap(order ->
            directory.findById(order.customerId())
                .map(customer -> new EnrichedOrder(
                    order.orderId(),
                    order.customerId(),
                    customer.displayName(),
                    customer.segment(),
                    order.total(),
                    order.currency()
                ))
        );
    }
}
~~~

Ví dụ giả định `findById` trả về `Mono.empty()` nếu không tìm thấy khách hàng. Khi đó phần tử tương ứng không tạo ra output trong `concatMap`. Nếu nghiệp vụ yêu cầu giữ đơn hàng dù chưa tra được khách hàng, hãy biểu diễn trạng thái chưa làm giàu trong một kiểu output rõ ràng thay vì âm thầm bỏ phần tử.

Không gọi `.block()` trong reactive function để chờ API trả kết quả. `block()` có thể chiếm thread xử lý và làm mất lợi ích của reactive pipeline. Hãy dùng client reactive và kết hợp kết quả bằng `map`, `flatMap`, `concatMap` hoặc toán tử phù hợp.

### Chọn toán tử theo yêu cầu thứ tự và concurrency

| Toán tử | Hành vi | Khi dùng |
|---|---|---|
| `map` | Biến đổi đồng bộ một phần tử thành một phần tử | Chuẩn hóa dữ liệu thuần |
| `filter` | Giữ phần tử thỏa predicate | Lọc điều kiện đơn giản |
| `concatMap` | Chuyển mỗi phần tử thành publisher, xử lý tuần tự và giữ thứ tự | Tra cứu cần giữ thứ tự đầu vào |
| `flatMap` | Xử lý các publisher con đồng thời; thứ tự đầu ra có thể thay đổi | Ưu tiên throughput khi không cần thứ tự |
| `flatMapSequential` | Cho phép xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn | Cần concurrency mà vẫn giữ thứ tự đầu ra |

`concatMap` dễ hiểu và giữ thứ tự nhưng có thể giới hạn throughput nếu mỗi lần tra cứu chậm. Khi cần xử lý đồng thời có giới hạn và vẫn giữ thứ tự đầu ra, có thể dùng `flatMapSequential(mapper, concurrency)`. Chỉ tăng concurrency sau khi đã kiểm tra giới hạn của dịch vụ tra cứu và khả năng chịu tải của hệ thống.

## 7. Ghép các Function thành một pipeline

Ba function có kiểu tương thích:

- `normalizeOrder`: `Flux<RawOrder>` thành `Flux<NormalizedOrder>`.
- `filterValidOrder`: `Flux<NormalizedOrder>` thành `Flux<NormalizedOrder>`.
- `enrichOrder`: `Flux<NormalizedOrder>` thành `Flux<EnrichedOrder>`.

Khai báo composition trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|filterValidOrder|enrichOrder"

    stream:
      bindings:
        "normalizeOrder|filterValidOrder|enrichOrder-in-0":
          destination: orders.raw
          group: order-enrichment
          content-type: application/json

        "normalizeOrder|filterValidOrder|enrichOrder-out-0":
          destination: orders.enriched
          content-type: application/json
~~~

Dấu `|` yêu cầu Spring Cloud Function ghép các bean theo thứ tự. Message đầu vào đi qua `normalizeOrder`, kết quả đã chuẩn hóa đi qua `filterValidOrder`, sau đó các phần tử còn lại được làm giàu bởi `enrichOrder`.

Tên binding mặc định của function tổng hợp dựa trên biểu thức composition:

- `normalizeOrder|filterValidOrder|enrichOrder-in-0` là input binding.
- `normalizeOrder|filterValidOrder|enrichOrder-out-0` là output binding.

Vì tên binding chứa ký tự `|`, đặt key trong dấu nháy kép để YAML thể hiện chính xác tên. Nếu muốn tên binding ngắn và ổn định hơn, có thể dùng thuộc tính `spring.cloud.stream.function.bindings` để ánh xạ tên binding được tạo sang tên tùy chỉnh; khi đó phải dùng tên đã ánh xạ trong phần `bindings`.

Composition chỉ hoạt động đúng khi kiểu output của mỗi bước tương thích với kiểu input của bước tiếp theo. Nếu thay `filterValidOrder` bằng function trả về một kiểu khác, cần điều chỉnh bước sau hoặc thêm mapper tương ứng.

## 8. Luồng dữ liệu đi qua pipeline như thế nào?

Giả sử broker gửi ba bản ghi:

~~~json
[
  {
    "externalOrderNumber": " ord-100 ",
    "customerCode": " cus-10 ",
    "amount": 150000,
    "currencyCode": "vnd"
  },
  {
    "externalOrderNumber": " ",
    "customerCode": "cus-11",
    "amount": 200000,
    "currencyCode": "VND"
  },
  {
    "externalOrderNumber": "ord-102",
    "customerCode": "cus-12",
    "amount": 85000,
    "currencyCode": "VND"
  }
]
~~~

Sau bước normalize, dữ liệu có dạng:

| orderId | customerId | total | currency |
|---|---|---:|---|
| ord-100 | cus-10 | 150000 | VND |
| null | cus-11 | 200000 | VND |
| ord-102 | cus-12 | 85000 | VND |

Bước filter loại bản ghi thứ hai vì orderId không hợp lệ. Hai bản ghi còn lại được chuyển tới bước enrich. Nếu Customer Directory trả về thông tin cho cả hai khách hàng, output có thể là:

~~~json
{
  "orderId": "ord-100",
  "customerId": "cus-10",
  "customerName": "Nguyen An",
  "customerSegment": "STANDARD",
  "total": 150000,
  "currency": "VND"
}
~~~

~~~json
{
  "orderId": "ord-102",
  "customerId": "cus-12",
  "customerName": "Tran Binh",
  "customerSegment": "PREMIUM",
  "total": 85000,
  "currency": "VND"
}
~~~

Nếu Customer Directory không tìm thấy một khách hàng, hành vi phụ thuộc chính sách đã chọn: bỏ phần tử, phát event có trạng thái enrichment thiếu hoặc chuyển sang luồng cần xử lý. Không để hành vi này phụ thuộc ngẫu nhiên vào việc adapter trả `null`, `Mono.empty()` hay exception.

## 9. Xử lý lỗi trong từng bước

Lỗi có thể xảy ra ở bất kỳ bước nào:

| Bước | Ví dụ | Hướng xử lý |
|---|---|---|
| Normalize | Payload thiếu cấu trúc, kiểu không chuyển đổi được | Validation và quarantine |
| Filter | Điều kiện nghiệp vụ không đạt | Bỏ qua có chủ đích hoặc phát bản ghi rejected |
| Enrich | API timeout, rate limit, khách hàng không tồn tại | Phân biệt lỗi tạm thời với không tìm thấy |
| Publish | Broker từ chối hoặc mất kết nối | Retry theo binder, giữ khả năng phát lại |

Trong reactive pipeline, exception phát sinh trong toán tử thường trở thành tín hiệu lỗi của publisher. Nếu không xử lý, tín hiệu lỗi truyền tới framework và error handling của binding. Có thể dùng `onErrorResume` khi đã xác định được phương án thay thế, nhưng không nên đổi mọi lỗi thành `Mono.empty()` vì như vậy sự cố kỹ thuật sẽ bị hiểu thành không có dữ liệu.

Ví dụ phân biệt không tìm thấy với lỗi dịch vụ:

~~~java
import reactor.core.publisher.Mono;

return directory.findById(order.customerId())
    .map(customer -> new EnrichedOrder(
        order.orderId(),
        order.customerId(),
        customer.displayName(),
        customer.segment(),
        order.total(),
        order.currency()
    ))
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(order.customerId())
    ));
~~~

Ở đây, `Mono.empty()` được chuyển thành lỗi nghiệp vụ có tên rõ ràng. Ứng dụng có thể bắt riêng `CustomerNotFoundException` để quarantine hoặc phát event rejected, trong khi timeout vẫn đi theo chính sách retry lỗi tạm thời.

Retry cần có giới hạn, backoff và phân loại exception. Với pipeline reactive, retry ở một publisher con có thể tránh chạy lại các phần tử trước đó; retry toàn bộ Flux có thể khiến một số phần tử được xử lý lại. Vì vậy, cần đặt retry ở đúng ranh giới và bảo đảm các bước có side effect là idempotent.

## 10. Bảo đảm thứ tự, backpressure và giới hạn tài nguyên

Một pipeline có thể nhận message nhanh hơn tốc độ tra cứu khách hàng hoặc tốc độ ghi broker. Reactive Streams dùng backpressure để truyền tín hiệu nhu cầu giữa các publisher/subscriber, nhưng backpressure chỉ có tác dụng khi các thành phần tham gia không tự tạo hàng đợi không giới hạn hoặc chặn thread.

Một số nguyên tắc:

- Giữ thao tác biến đổi thuần trong `map`; không gọi API blocking bên trong.
- Chọn `concatMap` nếu cần giữ thứ tự và chấp nhận xử lý tuần tự.
- Dùng concurrency có giới hạn khi tra cứu độc lập và dịch vụ phụ thuộc cho phép.
- Giới hạn timeout và số request đồng thời tới API bên ngoài.
- Theo dõi queue, lag, processing latency và số lỗi theo từng bước.
- Không tăng concurrency chỉ để giảm lag nếu downstream đang quá tải.
- Đảm bảo consumer idempotent khi retry hoặc redelivery có thể phát lại dữ liệu.

Thứ tự trong một pipeline reactive thường là thứ tự xử lý trong subscription đó. Khi broker có nhiều partition hoặc nhiều instance, không có thứ tự toàn cục giữa tất cả message. Nếu các event của cùng một đơn hàng cần giữ thứ tự, producer và binder phải dùng key/partition phù hợp, đồng thời pipeline không được làm đảo thứ tự các event đó.

## 11. Giữ metadata khi tạo payload mới

Khi Function nhận `Message<T>` và tạo payload mới, cần quyết định header nào phải được giữ lại. Nếu chỉ nhận payload `T`, function không truy cập trực tiếp metadata của message.

Ví dụ với function đồng bộ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public interface CustomerDirectorySync {
    CustomerInfo findRequired(String customerId);
}

@Configuration
public class SyncEnrichmentFunctions {

    @Bean
    Function<Message<NormalizedOrder>, Message<EnrichedOrder>> enrichWithHeaders(
            CustomerDirectorySync directory) {

        return input -> {
            NormalizedOrder order = input.getPayload();
            CustomerInfo customer = directory.findRequired(order.customerId());

            EnrichedOrder result = new EnrichedOrder(
                order.orderId(),
                order.customerId(),
                customer.displayName(),
                customer.segment(),
                order.total(),
                order.currency()
            );

            return MessageBuilder.withPayload(result)
                .copyHeaders(input.getHeaders())
                .setHeader("eventType", "OrderEnriched")
                .build();
        };
    }
}
~~~

Đặt interface `CustomerDirectorySync` và lớp `SyncEnrichmentFunctions` trong hai file Java riêng vì cả hai đều là kiểu top-level `public`. Ví dụ đồng bộ này minh họa việc giữ header; trong pipeline reactive ở trên, ưu tiên adapter trả về `Mono<CustomerInfo>` để không chặn thread xử lý.

Đây là một ví dụ imperative riêng, không phải function reactive `Flux` ở pipeline trước. `copyHeaders` giữ metadata đầu vào; sau đó có thể ghi đè header có ý nghĩa mới. Chỉ sao chép header được phép truyền qua ranh giới service, tránh đưa credential hoặc metadata nội bộ sang consumer khác.

Nếu event đầu ra là một sự kiện nghiệp vụ mới, hãy tạo event ID mới, giữ correlation ID theo quy trình và gán causation ID theo message trực tiếp gây ra event. Không dùng message ID nội bộ của Spring thay cho event ID nghiệp vụ.

## 12. Kiểm thử từng bước và toàn bộ composition

Tách function giúp kiểm thử từng bước bằng unit test. Với pipeline ví dụ, các trường hợp chính gồm:

| Kiểm thử | Kết quả cần xác nhận |
|---|---|
| Normalize mã có khoảng trắng | Mã đầu ra đã trim |
| Normalize currency viết thường | Currency đầu ra viết hoa theo Locale.ROOT |
| Filter thiếu order ID | Bản ghi không đi tiếp |
| Filter total bằng 0 hoặc âm | Bản ghi bị loại theo chính sách |
| Enrich tìm thấy khách hàng | Output có tên và segment |
| Enrich không tìm thấy khách hàng | Xử lý theo chính sách missing customer |
| Enrich gặp timeout | Lỗi được phân loại, không bị biến thành empty |
| Composition end-to-end | Output đúng thứ tự bước và đúng binding |

Ví dụ unit test cho function normalize và filter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

class OrderPipelineFunctionsTest {

    private final OrderPipelineFunctions functions =
        new OrderPipelineFunctions();

    @Test
    void normalizesCurrencyAndIdentifiers() {
        RawOrder raw = new RawOrder(
            " ord-100 ",
            " cus-10 ",
            new BigDecimal("150000"),
            "vnd"
        );

        NormalizedOrder result =
            functions.normalizeOrder().apply(Flux.just(raw)).blockFirst();

        assertEquals("ord-100", result.orderId());
        assertEquals("cus-10", result.customerId());
        assertEquals("VND", result.currency());
    }

    @Test
    void filtersOrdersWithoutAnIdentifier() {
        NormalizedOrder valid = new NormalizedOrder(
            "ord-100", "cus-10", new BigDecimal("100"), "VND"
        );
        NormalizedOrder invalid = new NormalizedOrder(
            null, "cus-11", new BigDecimal("200"), "VND"
        );

        List<NormalizedOrder> result = functions.filterValidOrder()
            .apply(Flux.just(valid, invalid))
            .collectList()
            .block();

        assertEquals(List.of(valid), result);
    }
}
~~~

Ví dụ kiểm thử dùng `.block()` ở test để chờ kết quả; không dùng cách này trong function chạy production. Với function `enrichOrder`, dùng một CustomerDirectory giả trả `Mono.just(...)`, `Mono.empty()` hoặc `Mono.error(...)` để kiểm tra ba trường hợp tìm thấy, không tìm thấy và lỗi kỹ thuật.

Test binder của Spring Cloud Stream giúp xác nhận input binding, output binding và payload qua composition mà không cần broker thật. Integration test với Kafka, RabbitMQ hoặc Pulsar vẫn cần thiết để kiểm tra serialization, partition, header mapping, retry, redelivery và hành vi broker thực tế.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Function làm quá nhiều việc | Khó kiểm thử và thay đổi | Tách normalize, filter và enrich |
| Kiểu output/input không tương thích | Composition không tạo được pipeline đúng | Định nghĩa DTO cho từng giai đoạn |
| Gọi API blocking trong Flux | Chiếm thread, giảm throughput | Dùng reactive client hoặc cô lập blocking work |
| Filter bỏ dữ liệu quan trọng mà không ghi nhận | Mất khả năng điều tra | Metric, quarantine hoặc rejected event |
| Dùng empty để che lỗi timeout | Pipeline có thể âm thầm mất dữ liệu | Giữ error signal và phân loại exception |
| flatMap không giới hạn concurrency | Quá tải dịch vụ phụ thuộc | Đặt concurrency và timeout rõ ràng |
| Không giữ thứ tự khi nghiệp vụ yêu cầu | Trạng thái downstream có thể sai | Dùng concatMap hoặc flatMapSequential phù hợp |
| Retry toàn pipeline có side effect | Bước đã chạy có thể bị lặp | Đặt retry đúng ranh giới và thiết kế idempotent |

## 14. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện bài tập với luồng đơn hàng:

1. Tạo `RawOrder`, `NormalizedOrder` và `EnrichedOrder`.
2. Viết `normalizeOrder` để chuẩn hóa mã đơn, mã khách hàng và currency.
3. Viết `filterValidOrder` để loại bản ghi không đạt điều kiện.
4. Viết `enrichOrder` để tra cứu Customer Directory bằng reactive client.
5. Ghép ba function bằng `spring.cloud.function.definition`.
6. Ánh xạ binding tổng hợp tới `orders.raw` và `orders.enriched`.
7. Gửi dữ liệu hợp lệ, dữ liệu sai và dữ liệu có khách hàng không tồn tại.
8. Quan sát output, metric và error handling.
9. Thử concurrency khác nhau và xác nhận thứ tự đầu ra.
10. Viết unit test, test binder và integration test với broker.

Hoàn thành bài khi có thể giải thích kiểu dữ liệu tại từng bước, cấu hình tên binding của composition, cách lọc bản ghi, cách làm giàu bằng dịch vụ ngoài và cách xử lý lỗi mà không nhầm lỗi kỹ thuật với dữ liệu rỗng.

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — mô hình Supplier, Function, Consumer và reactive function.
- [Spring Cloud Function — Function composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-composition) — ghép nhiều function theo thứ tự.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — tên binding mặc định và ánh xạ binding tùy chỉnh.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — tích hợp function với binding và binder.
- [Project Reactor — Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html) — xử lý luồng nhiều phần tử.
- [Project Reactor — Error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — tín hiệu lỗi và chiến lược phục hồi.
- [Reactive Streams](https://www.reactive-streams.org/) — backpressure và giao thức xử lý luồng bất đồng bộ.

