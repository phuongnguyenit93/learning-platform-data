# Nguồn nóng và lạnh

## Phát lại dữ liệu, bộ nhớ đệm và giới hạn lưu giữ

Với một Publisher, subscriber đăng ký muộn có thể cần xem lại một phần dữ liệu đã phát trước đó. Ví dụ, bảng điều khiển vừa mở cần nhận vài cập nhật gần nhất để dựng trạng thái ban đầu; một dịch vụ khác cần đọc lại kết quả truy vấn đã thực hiện; hoặc một luồng sự kiện cần giữ một cửa sổ dữ liệu ngắn để consumer mới không bắt đầu từ trạng thái trống.

Phát lại (replay) cho phép publisher gửi lại những tín hiệu đã lưu cho subscriber đến sau. Bộ nhớ đệm (cache) kết hợp việc chia sẻ nguồn với việc lưu giữ tín hiệu để những lần đăng ký tiếp theo có thể dùng lại dữ liệu. Trong Project Reactor, các API như **replay**, **cache** và **share** có ngữ nghĩa khác nhau về thời điểm kết nối, lịch sử được giữ và vòng đời nguồn. Chọn đúng chính sách lưu giữ giúp cân bằng trải nghiệm consumer, độ mới của dữ liệu và giới hạn bộ nhớ.

### 1. Vì sao cần phát lại dữ liệu?

Một hot publisher có thể phát độc lập với từng subscriber. Nếu một subscriber đăng ký sau khi nguồn đã phát một số sự kiện, subscriber đó thường chỉ nhận các sự kiện mới từ thời điểm đăng ký. Điều này phù hợp với consumer chỉ quan tâm dữ liệu tương lai, nhưng không đủ cho consumer cần trạng thái gần nhất để khởi tạo.

Ví dụ, một luồng giá đã phát các cập nhật 100, 101 và 102. Subscriber thứ nhất đã nhận cả ba. Nếu subscriber thứ hai đăng ký sau khi giá 102 được phát, nó có thể chỉ nhận giá trị 103 tiếp theo. Nếu giao diện cần hiển thị ngay giá gần nhất, chờ đến lần cập nhật tiếp theo có thể tạo cảm giác dữ liệu bị thiếu.

Replay giải quyết vấn đề bằng cách lưu giữ một phần lịch sử. Subscriber đến muộn có thể nhận các phần tử được lưu trước khi tiếp tục nhận dữ liệu mới. Phạm vi lịch sử cần giữ phụ thuộc vào mục đích:

- Một hoặc vài giá trị gần nhất để dựng trạng thái ban đầu.
- Một số lượng sự kiện cố định để hỗ trợ consumer đến muộn.
- Các sự kiện trong một khoảng thời gian để giữ cửa sổ gần đây.
- Toàn bộ kết quả của một tác vụ hữu hạn để tránh thực hiện lại công việc tốn kém.

Không phải luồng nào cũng cần replay. Nếu dữ liệu cũ không còn ý nghĩa hoặc có thể được truy vấn từ nguồn lưu trữ chính, chỉ phát sự kiện mới có thể đơn giản và tiết kiệm tài nguyên hơn.

### 2. Replay trong Project Reactor

Toán tử **replay()** trên một Flux tạo ra **ConnectableFlux** có khả năng lưu và phát lại các tín hiệu đã phát. Có thể đăng ký các subscriber trước, sau đó chủ động gọi **connect()** để bắt đầu nguồn:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

ConnectableFlux<Integer> replayed =
    Flux.range(1, 5).replay(2);

replayed.subscribe(value -> System.out.println("A: " + value));

Disposable connection = replayed.connect();

// Nguồn đã phát xong; subscriber B nhận lại hai phần tử cuối.
replayed.subscribe(value -> System.out.println("B: " + value));
~~~

Với giới hạn lịch sử là hai phần tử, subscriber A nhận các giá trị từ 1 đến 5. Khi subscriber B đăng ký sau khi nguồn hoàn tất, nó nhận lại hai giá trị cuối là 4 và 5, sau đó nhận tín hiệu hoàn tất. Đối tượng trả về từ **connect()** cho phép quản lý kết nối nguồn.

Có thể cấu hình replay theo thời gian:

~~~java
import java.time.Duration;

import reactor.core.publisher.ConnectableFlux;

ConnectableFlux<PriceUpdate> recentPrices =
    priceFeed.liveUpdates()
        .replay(100, Duration.ofMinutes(2));
~~~

Ví dụ này giữ tối đa 100 cập nhật trong cửa sổ hai phút. Subscriber mới chỉ nhận những phần tử còn trong phạm vi lưu giữ, sau đó tiếp tục nhận dữ liệu mới nếu nguồn vẫn đang hoạt động. Giới hạn số lượng và thời gian bổ sung cho nhau: giới hạn số lượng ngăn cửa sổ tăng quá lớn khi nguồn phát dày; giới hạn thời gian ngăn dữ liệu cũ tồn tại lâu khi nguồn phát thưa.

Các overload của **replay** có thể dùng giới hạn số phần tử, khoảng thời gian hoặc cả hai. Vì đây là **ConnectableFlux**, cần quyết định cách kết nối: gọi **connect()** thủ công, dùng **autoConnect(n)** để kết nối sau khi đủ subscriber, hoặc dùng **refCount(n)** để quản lý kết nối theo số subscriber đang tham gia.

### 3. Cache: chia sẻ nguồn và lưu lại tín hiệu

**cache()** biến một Flux thành nguồn nóng có lưu giữ lịch sử. Subscriber đầu tiên kích hoạt nguồn; những subscriber sau có thể nhận lại các tín hiệu đã được cache. Khác với **replay()**, cách dùng cơ bản của **cache()** không yêu cầu gọi **connect()** thủ công.

~~~java
Flux<Product> products =
    productRepository.findFeaturedProducts()
        .cache();

products.subscribe(this::renderCatalog);
products.subscribe(this::updateRecommendationPanel);
~~~

Nếu publisher nguồn là cold, subscription đầu tiên kích hoạt việc đọc dữ liệu. Các subscriber sau dùng lại những tín hiệu đã được cache thay vì tạo một lần đọc upstream mới. Điều này hữu ích khi dữ liệu hữu hạn, ít thay đổi và nhiều thành phần cần cùng kết quả.

Mặc định, **cache()** giữ lịch sử không giới hạn trong vòng đời của publisher và phát lại cả tín hiệu kết thúc. Với một luồng hữu hạn, điều đó có thể phù hợp. Với luồng sự kiện vô hạn, mỗi phần tử mới có thể tiếp tục được giữ lại, khiến bộ nhớ tăng theo thời gian. Vì vậy, không nên dùng cache không giới hạn cho nguồn dài hạn hoặc tốc độ cao nếu không có chính sách lưu giữ rõ ràng.

### 4. Giới hạn cache theo số phần tử

Overload **cache(history)** giới hạn số phần tử được giữ để phát lại:

~~~java
Flux<OrderEvent> recentOrderEvents =
    orderEventSource.events()
        .cache(200);
~~~

Publisher chỉ giữ tối đa 200 phần tử lịch sử gần nhất cho subscriber đến sau. Đây là lựa chọn phù hợp khi cần cửa sổ theo số lượng, chẳng hạn hiển thị 200 sự kiện gần nhất trong màn hình theo dõi.

Giới hạn theo số phần tử không đảm bảo giới hạn bộ nhớ tuyệt đối. Một phần tử có thể chứa payload rất nhỏ hoặc một đối tượng lớn với nhiều dữ liệu lồng nhau. Nếu kích thước phần tử biến động mạnh, 200 phần tử vẫn có thể chiếm nhiều bộ nhớ. Khi đó cần cân nhắc giới hạn kích thước payload, chuyển sang lưu trữ ngoài hoặc chỉ cache dữ liệu đã được rút gọn.

### 5. Giới hạn cache theo thời gian sống

Overload **cache(ttl)** đặt thời gian sống cho các tín hiệu được lưu:

~~~java
Flux<PriceUpdate> priceWindow =
    priceFeed.liveUpdates()
        .cache(Duration.ofMinutes(3));
~~~

Các cập nhật chỉ được giữ trong cửa sổ thời gian cấu hình. Subscriber đến muộn không nhận những tín hiệu đã hết hạn lưu giữ. Cách này hữu ích khi dữ liệu cũ mất giá trị sau một khoảng thời gian, chẳng hạn trạng thái theo dõi gần đây hoặc kết quả tạm thời.

Chỉ giới hạn TTL vẫn có thể giữ nhiều phần tử nếu nguồn phát hàng nghìn sự kiện trong khoảng thời gian đó. Khi tốc độ phát không ổn định, nên cân nhắc giới hạn đồng thời cả số lượng và thời gian:

~~~java
Flux<OrderEvent> boundedRecentEvents =
    orderEventSource.events()
        .cache(500, Duration.ofMinutes(10));
~~~

Ví dụ đặt hai giới hạn: tối đa 500 phần tử lịch sử và thời gian lưu tối đa mười phút. Hãy kiểm tra overload phù hợp với phiên bản Reactor của dự án và xác định chính sách cho cả tín hiệu kết thúc. Cache có TTL cũng có quy tắc hết hạn và tải lại nguồn; cần hiểu rõ hành vi của overload đang dùng trước khi dựa vào nó cho dữ liệu nghiệp vụ.

### 6. Cache tín hiệu kết thúc và lỗi

Cache trong Reactor lưu cả tín hiệu kết thúc của nguồn, không chỉ các phần tử dữ liệu. Vì vậy, nếu nguồn hoàn tất, subscriber đến sau có thể nhận lại các phần tử còn được lưu cùng tín hiệu hoàn tất. Nếu nguồn kết thúc bằng lỗi, lỗi đó cũng có thể được phát lại cho subscriber tiếp theo.

Ví dụ:

~~~java
Mono<Configuration> configuration =
    configurationClient.fetch()
        .cache();
~~~

Với **Mono**, cache có thể giữ một giá trị, trạng thái rỗng hoặc lỗi. Nếu lần gọi đầu tiên thất bại và lỗi được cache, những subscriber tiếp theo có thể nhận lại lỗi đã lưu thay vì tự động gọi dịch vụ lại. Đây là lý do cần quyết định rõ có muốn cache lỗi hay không, và trong bao lâu.

Vị trí đặt toán tử phục hồi và cache làm thay đổi hành vi:

~~~java
Mono<Configuration> recoveredThenCached =
    configurationClient.fetch()
        .onErrorResume(error -> loadFallbackConfiguration())
        .cache();

Mono<Configuration> cachedThenRetried =
    configurationClient.fetch()
        .cache()
        .retry(2);
~~~

Ở pipeline thứ nhất, lỗi được chuyển sang nguồn dự phòng trước khi tín hiệu được cache. Các subscriber có thể nhận cấu hình dự phòng đã được lưu. Ở pipeline thứ hai, lỗi upstream có thể đã được cache; retry ở downstream đăng ký lại vào cache và có thể nhận lại chính lỗi đã lưu thay vì thực hiện lại yêu cầu gốc. Nếu mục tiêu là thử lại thao tác nguồn trước khi lưu kết quả cuối cùng, hãy đặt **retry** trước **cache**:

~~~java
Mono<Configuration> retriedThenCached =
    configurationClient.fetch()
        .retry(2)
        .cache();
~~~

Retry vẫn cần giới hạn và bảo đảm thao tác an toàn để lặp. Cache không thay thế chiến lược retry, fallback hay xử lý lỗi nghiệp vụ.

### 7. Phân biệt share, replay và cache

Ba toán tử thường được dùng để chia sẻ publisher, nhưng chính sách lịch sử khác nhau:

| Cơ chế | Kết nối nguồn | Subscriber đến muộn | Lịch sử lưu giữ |
| --- | --- | --- | --- |
| **share()** | Tự kết nối khi có subscriber | Nhận dữ liệu mới trong thời gian chia sẻ còn hoạt động | Không replay các phần tử đã phát |
| **replay(n)** | Kết nối qua **connect()**, **autoConnect** hoặc **refCount** | Nhận lại tối đa n phần tử gần nhất còn lưu | Có thể giới hạn theo số lượng và/hoặc thời gian |
| **cache(n)** | Subscriber đầu tiên kích hoạt nguồn | Nhận lại lịch sử đã cache | Giới hạn theo số lượng |
| **cache(ttl)** | Subscriber đầu tiên kích hoạt nguồn | Nhận lại tín hiệu còn trong TTL | Giới hạn theo thời gian |
| **cache(n, ttl)** | Subscriber đầu tiên kích hoạt nguồn | Nhận lại phần tử còn trong cả hai giới hạn | Giới hạn theo số lượng và thời gian |

**share()** phù hợp khi các subscriber đang hoạt động cần dùng chung nguồn và không cần lịch sử. **replay()** phù hợp khi muốn điều khiển thời điểm kết nối và chính sách phát lại. **cache()** phù hợp khi muốn tự động khởi động nguồn ở subscriber đầu tiên và lưu kết quả cho những lần đăng ký tiếp theo.

Không nên chọn cache chỉ để tránh gọi nguồn nhiều lần mà không xem xét độ mới của dữ liệu. Nếu dữ liệu thay đổi thường xuyên, cache không có TTL có thể trả kết quả cũ vô thời hạn. Ngược lại, TTL quá ngắn có thể làm nguồn bị gọi lại thường xuyên và tăng tải hệ thống.

### 8. Tính toán giới hạn lưu giữ và ngân sách bộ nhớ

Giới hạn số phần tử là một cách kiểm soát đơn giản, nhưng cần ước lượng bộ nhớ dựa trên kích thước dữ liệu thực tế. Một ước lượng sơ bộ:

\[
\text{Bộ nhớ cache}
\approx
\text{Số phần tử được giữ}
\times
\text{Kích thước trung bình mỗi phần tử}
\]

Nếu giữ 500 phần tử, mỗi phần tử trung bình 8 KB, payload đã vào khoảng 4 MB, chưa tính overhead của đối tượng, cấu trúc lưu trữ, tham chiếu và các vùng đệm khác trong pipeline. Nếu mỗi phần tử giữ tham chiếu đến một đồ thị đối tượng lớn, chi phí thực tế có thể cao hơn đáng kể.

Với cache theo TTL, cần ước lượng tốc độ phát:

\[
\text{Số phần tử trong cửa sổ}
\approx
\text{Tốc độ phát mỗi giây}
\times
\text{TTL tính bằng giây}
\]

Nếu nguồn phát trung bình 300 sự kiện mỗi giây và TTL là 120 giây, cửa sổ có thể chứa khoảng 36.000 sự kiện. Một TTL nghe có vẻ ngắn vẫn có thể tạo cache lớn khi nguồn phát dày. Kết hợp giới hạn số lượng giúp kiểm soát trường hợp tải tăng đột biến.

### 9. Cache trong bộ nhớ không phải kho lưu trữ bền vững

Cache của Reactor tồn tại trong bộ nhớ tiến trình. Khi ứng dụng khởi động lại, dữ liệu cache mất đi. Nó không thay thế database, event store, message broker có retention hoặc kho lưu trữ dùng để khôi phục sau sự cố.

Với dữ liệu cần phát lại qua nhiều lần triển khai, nhiều instance hoặc sau khi tiến trình dừng, hãy dùng cơ chế lưu trữ bền vững và offset/sequence number phù hợp. Cache cục bộ có thể bổ sung để giảm truy vấn lặp, nhưng mỗi instance có thể có cache riêng và thời điểm hết hạn khác nhau. Nếu nhiều instance cùng phục vụ một dữ liệu, cần cân nhắc tính nhất quán và chiến lược invalidation.

Ngoài ra, dữ liệu nhạy cảm cần được lưu giữ đúng phạm vi và thời gian cho phép. Không nên cache thông tin cá nhân hoặc dữ liệu xác thực lâu hơn nhu cầu thực tế. Việc giới hạn TTL, số lượng và payload giúp giảm cả chi phí bộ nhớ lẫn phạm vi dữ liệu tồn tại trong tiến trình.

### 10. Kiểm thử replay và giới hạn lịch sử

Có thể dùng **StepVerifier** để xác nhận subscriber đến muộn nhận lại đúng số phần tử gần nhất:

~~~java
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

ConnectableFlux<Integer> replayed =
    Flux.range(1, 5).replay(2);

replayed.connect();

StepVerifier.create(replayed)
    .expectNext(4, 5)
    .verifyComplete();
~~~

Nguồn đã phát và hoàn tất trước khi StepVerifier đăng ký. Replay giữ hai phần tử cuối, vì vậy subscriber mới nhận 4 và 5 rồi nhận tín hiệu hoàn tất.

Với cache, có thể xác nhận nguồn cold chỉ được đăng ký một lần trong các subscriber cùng dùng cache:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

AtomicInteger subscriptions = new AtomicInteger();

Flux<Integer> cached =
    Flux.defer(() -> {
        subscriptions.incrementAndGet();
        return Flux.range(1, 3);
    }).cache(2);

StepVerifier.create(cached)
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(cached)
    .expectNext(2, 3)
    .verifyComplete();

assertEquals(1, subscriptions.get());
~~~

Subscriber đầu tiên nhận toàn bộ ba phần tử. Subscriber thứ hai nhận lại hai phần tử cuối theo giới hạn lịch sử. Bộ đếm xác nhận nguồn chỉ được đăng ký một lần trong vòng đời cache này. Trong kiểm thử thực tế, cần đặt các import và assertion phù hợp với JUnit đang dùng.

Với TTL, nên dùng công cụ thời gian ảo của Reactor để kiểm thử hết hạn mà không phải chờ thật. Bài kiểm thử cần xác minh cả phần tử được phát lại, tín hiệu kết thúc, thời điểm cache hết hạn và việc nguồn có được đăng ký lại theo overload đã chọn hay không.

### 11. Chọn chính sách replay và cache

Trước khi thêm replay hoặc cache, hãy trả lời:

- Subscriber đến muộn cần nhận bao nhiêu phần tử lịch sử?
- Dữ liệu cũ còn hữu ích trong bao lâu?
- Nguồn có hữu hạn hay phát liên tục?
- Có cần phát lại tín hiệu hoàn tất hoặc lỗi không?
- Khi cache hết hạn, nguồn cần được tải lại theo cách nào?
- Tốc độ phát và kích thước phần tử tạo ra ngân sách bộ nhớ bao nhiêu?
- Nhiều instance có cần dùng chung lịch sử và trạng thái cache không?
- Có dữ liệu nhạy cảm cần giới hạn thời gian lưu giữ không?

Với một kết quả tra cứu hữu hạn, **Mono.cache(Duration)** có thể giảm các lần gọi lặp trong một khoảng ngắn. Với một luồng sự kiện dài hạn, **replay(history, ttl)** hoặc **cache(history, ttl)** giúp giữ một cửa sổ có giới hạn. Với consumer chỉ cần nhận dữ liệu mới, **share()** có thể đủ. Khi cần khôi phục lịch sử sau khi tiến trình dừng, hãy dùng kho lưu trữ bền vững thay vì cache trong bộ nhớ.

Trong module REACTIVE_PROGRAMMING, hiểu replay và giới hạn lưu giữ giúp phân biệt vòng đời hot/cold publisher, kiểm soát số lần subscription và quản lý tài nguyên. Chính sách lưu giữ cần được xem là một phần của hợp đồng dữ liệu: nó quyết định subscriber đến muộn nhìn thấy điều gì, dữ liệu tồn tại bao lâu và nguồn được thực thi lại vào thời điểm nào.
