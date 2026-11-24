# Nhiều đầu vào hoặc đầu ra với kiểu hàm được hỗ trợ

Một hàm Spring Cloud Stream thường có một đầu vào và một đầu ra: Function<T, R> nhận một message, xử lý rồi trả kết quả. Trong hệ thống sự kiện thực tế, một phép xử lý có thể cần dữ liệu từ nhiều luồng, hoặc cần phát kết quả đến nhiều luồng độc lập. Spring Cloud Stream hỗ trợ các dạng hàm phản ứng với nhiều đầu vào hoặc đầu ra bằng cách sử dụng tuple của Reactor chứa các Flux.

Điểm quan trọng là phân biệt số lượng cổng message với số tham số Java thông thường. Một hàm nhiều đầu vào được biểu diễn bằng một tuple chứa các luồng đầu vào; một hàm nhiều đầu ra trả về tuple chứa các luồng đầu ra. Spring Cloud Stream tạo binding riêng cho từng cổng theo hậu tố in-0, in-1, out-0, out-1... Từ đó, mỗi binding có thể kết nối đến destination và consumer group phù hợp.

## 1. Các kiểu hàm cơ bản

Spring Cloud Stream dùng mô hình hàm của Spring Cloud Function. Ba kiểu cơ bản là:

| Kiểu hàm | Chữ ký đơn giản | Binding mặc định |
|---|---|---|
| Supplier | Supplier<T> | functionName-out-0 |
| Function | Function<T, R> | functionName-in-0, functionName-out-0 |
| Consumer | Consumer<T> | functionName-in-0 |

Với dữ liệu xử lý từng message, các kiểu trên có thể dùng payload Java thông thường. Với luồng liên tục hoặc cần nhiều cổng, có thể dùng kiểu reactive:

- Supplier<Flux<T>> phát một luồng message.
- Function<Flux<T>, Flux<R>> biến đổi một luồng đầu vào thành một luồng đầu ra.
- Consumer<Flux<T>> nhận và xử lý một luồng.

Khi cần nhiều đầu vào hoặc đầu ra trong cùng một hàm reactive, dùng tuple của Reactor, chẳng hạn Tuple2 hoặc Tuple3. Mỗi phần tử tuple tương ứng một cổng binding. Các ví dụ dưới đây dùng Tuple2 để làm rõ cách ánh xạ. Đây là cách biểu diễn nhiều cổng của mô hình reactive; không khai báo một phương thức Java có nhiều tham số rời rồi kỳ vọng Spring Cloud Stream tự tạo binding cho từng tham số.

## 2. Nhiều đầu vào: kết hợp hai luồng

Giả sử dịch vụ tạo đơn hàng phát sự kiện OrderCreated, còn dịch vụ khách hàng phát dữ liệu hồ sơ CustomerProfile. Một bước xử lý cần kết hợp thông tin đơn hàng với hồ sơ khách hàng để tạo EnrichedOrder.

Định nghĩa các kiểu dữ liệu:

~~~java
record OrderCreated(String orderId, String customerId, long totalMinorUnits) {}

record CustomerProfile(String customerId, String displayName, String tier) {}

record EnrichedOrder(
        String orderId,
        String customerId,
        String customerName,
        String customerTier,
        long totalMinorUnits) {}
~~~

Khai báo Function có một tham số kiểu tuple, mỗi phần tử là một Flux:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

@Configuration
class OrderEnrichmentFunctions {

    @Bean
    Function<Tuple2<Flux<OrderCreated>, Flux<CustomerProfile>>,
             Flux<EnrichedOrder>> enrichOrders() {
        return inputs -> Flux.zip(
                inputs.getT1(),
                inputs.getT2(),
                (order, customer) -> new EnrichedOrder(
                        order.orderId(),
                        order.customerId(),
                        customer.displayName(),
                        customer.tier(),
                        order.totalMinorUnits()));
    }
}
~~~

Tuple2 chứa hai luồng đầu vào. getT1() truy cập luồng thứ nhất, getT2() truy cập luồng thứ hai. Flux.zip kết hợp một phần tử từ luồng thứ nhất với một phần tử từ luồng thứ hai để tạo kết quả. Hàm trả về một Flux<EnrichedOrder>, vì vậy chỉ có một binding đầu ra.

Cấu hình hai input binding và một output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrders-in-1:
          destination: customers.profile-snapshots
          group: order-enrichment
          content-type: application/json
        enrichOrders-out-0:
          destination: orders.enriched
          content-type: application/json
~~~

Trong cấu hình trên:

- enrichOrders-in-0 nhận message từ orders.created.
- enrichOrders-in-1 nhận message từ customers.profile-snapshots.
- enrichOrders-out-0 phát kết quả đến orders.enriched.

Tên binding được suy ra từ tên bean và chỉ số cổng. Destination là tên luồng trên broker. Mỗi input binding khai báo group; ví dụ này dùng cùng tên order-enrichment cho hai luồng đầu vào. Binder ánh xạ group đến consumer group, queue hoặc subscription tương ứng theo từng destination.

## 3. Chọn phép kết hợp phù hợp với ý nghĩa dữ liệu

Flux.zip ghép phần tử theo thứ tự phát: phần tử thứ nhất của luồng A đi với phần tử thứ nhất của luồng B, phần tử thứ hai đi với phần tử thứ hai, và tiếp tục như vậy. Nó phù hợp khi hai luồng có quan hệ một-một và được tạo ra theo cùng thứ tự.

Không nên dùng zip để giả lập phép join theo khóa nghiệp vụ nếu hai luồng phát độc lập. Ví dụ, một đơn hàng không nhất thiết tương ứng với message hồ sơ khách hàng tiếp theo trong luồng profile. Hai luồng có thể có tốc độ, thứ tự và số lượng phần tử khác nhau. Khi đó, zip có thể ghép nhầm dữ liệu hoặc chờ vô hạn nếu một phía không phát thêm phần tử.

Chọn cách xử lý theo yêu cầu:

| Nhu cầu | Cách tiếp cận |
|---|---|
| Hai luồng phát các phần tử tương ứng theo cùng thứ tự | Flux.zip |
| Mỗi message đơn hàng cần tra cứu hồ sơ mới nhất theo customerId | Gọi service/cache hoặc kho dữ liệu theo khóa |
| Cần ghép hai luồng sự kiện theo key và cửa sổ thời gian | Dùng processor có trạng thái, window/join phù hợp như Kafka Streams hoặc công cụ streaming chuyên dụng |
| Cần phát kết quả khi bất kỳ luồng nào thay đổi, dựa trên giá trị mới nhất của mỗi luồng | Xem xét combineLatest, sau khi xác định rõ ngữ nghĩa |

Ví dụ combineLatest phát kết quả khi một phía phát phần tử mới, sau khi cả hai phía đã có ít nhất một phần tử. Nó kết hợp phần tử mới nhất từ mỗi phía, không phải phép ghép từng cặp một-một. Chọn operator theo quy tắc nghiệp vụ và kiểm thử với các luồng có tốc độ khác nhau.

## 4. Nhiều đầu ra: phân nhánh một luồng

Một Function có thể nhận một luồng đầu vào và phát kết quả đến nhiều output binding. Ví dụ, đơn hàng có tổng tiền cao được chuyển đến luồng cần kiểm tra thủ công; các đơn còn lại đi đến luồng xử lý thông thường.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

record ManualReviewRequested(String orderId, long totalMinorUnits) {}

@Configuration
class OrderRoutingFunctions {

    @Bean
    Function<Flux<OrderCreated>,
             Tuple2<Flux<OrderCreated>, Flux<ManualReviewRequested>>> routeOrders() {
        return orders -> {
            Flux<OrderCreated> shared = orders.publish().autoConnect(2);

            Flux<OrderCreated> normalOrders =
                    shared.filter(order -> order.totalMinorUnits() < 100_000_000);

            Flux<ManualReviewRequested> reviewOrders =
                    shared.filter(order -> order.totalMinorUnits() >= 100_000_000)
                            .map(order -> new ManualReviewRequested(
                                    order.orderId(),
                                    order.totalMinorUnits()));

            return Tuples.of(normalOrders, reviewOrders);
        };
    }
}
~~~

Hàm trả về Tuple2, nên có hai output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrders
    stream:
      bindings:
        routeOrders-in-0:
          destination: orders.created
          group: order-router
        routeOrders-out-0:
          destination: orders.normal
        routeOrders-out-1:
          destination: orders.manual-review
~~~

routeOrders-out-0 nhận các đơn hàng thông thường; routeOrders-out-1 nhận yêu cầu kiểm tra thủ công. Chỉ số output tương ứng với thứ tự phần tử trong tuple: getT1() là output 0, getT2() là output 1.

Ví dụ dùng publish().autoConnect(2) để chia sẻ upstream cho hai nhánh thay vì tạo hai subscription độc lập lên nguồn. Số subscriber phải khớp số nhánh được tiêu thụ. Nếu thay đổi số output hoặc có nhánh tùy chọn, cần điều chỉnh chiến lược chia sẻ và kiểm thử vòng đời subscription để tránh luồng không được kết nối hoặc nguồn bị đăng ký nhiều lần.

## 5. Một hàm có nhiều đầu vào và nhiều đầu ra

Có thể kết hợp hai dạng tuple trong cùng một chữ ký: tuple đầu vào chứa nhiều Flux, tuple đầu ra chứa nhiều Flux. Ví dụ, hệ thống nhận đơn hàng và danh mục sản phẩm, sau đó phát đơn hàng đã bổ sung thông tin cùng một luồng cảnh báo dữ liệu không hợp lệ.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

record ProductInfo(String productId, String category) {}

record OrderLine(String orderId, String productId, int quantity) {}

record OrderWithCategory(
        String orderId,
        String productId,
        String category,
        int quantity) {}

record EnrichmentWarning(String orderId, String reason) {}

@Configuration
class MultiPortFunctions {

    @Bean
    Function<Tuple2<Flux<OrderLine>, Flux<ProductInfo>>,
             Tuple2<Flux<OrderWithCategory>, Flux<EnrichmentWarning>>>
    enrichAndReport() {
        return inputs -> {
            Flux<Tuple2<OrderLine, ProductInfo>> sharedPairs =
                    Flux.zip(inputs.getT1(), inputs.getT2())
                            .publish()
                            .autoConnect(2);

            Flux<OrderWithCategory> enriched = sharedPairs
                    .filter(pair -> pair.getT1().productId() != null)
                    .map(pair -> new OrderWithCategory(
                            pair.getT1().orderId(),
                            pair.getT1().productId(),
                            pair.getT2().category(),
                            pair.getT1().quantity()));

            Flux<EnrichmentWarning> warnings = sharedPairs
                    .filter(pair -> pair.getT1().productId() == null)
                    .map(pair -> new EnrichmentWarning(
                            pair.getT1().orderId(),
                            "Missing product identifier"));

            return Tuples.of(enriched, warnings);
        };
    }
}
~~~

Chữ ký có hai input và hai output, vì vậy Spring Cloud Stream tạo bốn binding:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichAndReport
    stream:
      bindings:
        enrichAndReport-in-0:
          destination: order-lines.created
          group: order-enrichment
        enrichAndReport-in-1:
          destination: products.catalog
          group: order-enrichment
        enrichAndReport-out-0:
          destination: orders.enriched
        enrichAndReport-out-1:
          destination: orders.enrichment-warnings
~~~

Ví dụ này chỉ minh họa ánh xạ nhiều cổng. Hai luồng được ghép bằng zip, do đó chỉ phù hợp nếu phần tử của chúng tương ứng theo thứ tự. Trong ví dụ, hai output dùng chung publisher đã chia sẻ để tránh đăng ký độc lập lên hai input. Không dùng zip cho dữ liệu danh mục và đơn hàng nếu chúng không phát theo cặp đồng bộ.

## 6. Supplier và Consumer với nhiều cổng

Các ví dụ trên dùng Function vì có đầu vào và đầu ra. Một Supplier reactive có thể phát nhiều output bằng cách trả về tuple các luồng:

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
class MultiOutputSupplier {

    @Bean
    Supplier<Tuple2<Flux<String>, Flux<Long>>> systemSignals() {
        return () -> Tuples.of(
                Flux.just("started", "ready"),
                Flux.just(10L, 20L, 30L));
    }
}
~~~

Supplier không có input binding; tuple trả về tạo hai output binding systemSignals-out-0 và systemSignals-out-1. Cần cấu hình poller và vòng đời phát phù hợp nếu supplier tạo luồng liên tục. Không dùng Flux.just trong ví dụ này như một nguồn sự kiện vô hạn; nó chỉ phát các giá trị mẫu rồi hoàn tất.

Hai output binding có thể được cấu hình độc lập:

~~~yaml
spring:
  cloud:
    function:
      definition: systemSignals
    stream:
      bindings:
        systemSignals-out-0:
          destination: system.status
        systemSignals-out-1:
          destination: system.metrics
~~~

Consumer<T> phù hợp khi một binding đầu vào cần thực hiện side effect và không phát kết quả qua output binding. Với xử lý nhiều luồng đầu vào, Function reactive nhận tuple thường dễ kiểm soát hơn: hàm kết hợp các Flux bằng operator rồi trả publisher kết quả để framework quản lý subscription và backpressure. Tránh tự gọi subscribe() bên trong Function nếu không có lý do cụ thể; việc tự subscribe có thể làm lỗi và vòng đời subscription nằm ngoài cơ chế quản lý của framework. Nếu cần xử lý side effect, đặt nó trong các operator phù hợp như doOnNext hoặc trong một Consumer riêng.

## 7. Tên binding và thứ tự cổng

Spring Cloud Stream đánh số cổng từ 0 theo thứ tự trong tuple:

| Vị trí | Tên binding | Ý nghĩa |
|---|---|---|
| Input thứ nhất | functionName-in-0 | Phần tử getT1() |
| Input thứ hai | functionName-in-1 | Phần tử getT2() |
| Input thứ ba | functionName-in-2 | Phần tử getT3() |
| Output thứ nhất | functionName-out-0 | Phần tử getT1() |
| Output thứ hai | functionName-out-1 | Phần tử getT2() |
| Output thứ ba | functionName-out-2 | Phần tử getT3() |

Tên bean trong ví dụ là enrichOrders, routeOrders hoặc enrichAndReport. spring.cloud.function.definition chọn bean cần kích hoạt. Các khóa trong spring.cloud.stream.bindings dùng tên binding; thuộc tính destination xác định luồng broker.

Khi đổi thứ tự phần tử trong tuple, ý nghĩa các binding theo chỉ số cũng đổi. Ví dụ, nếu hoán đổi Tuples.of(normalOrders, reviewOrders) thành Tuples.of(reviewOrders, normalOrders) mà không cập nhật cấu hình, dữ liệu có thể đi nhầm destination dù ứng dụng vẫn khởi động. Hãy coi thứ tự tuple là một phần của hợp đồng cấu hình và kiểm thử nó.

## 8. Backpressure, tốc độ và lỗi giữa các luồng

Với nhiều input, các luồng có thể phát với tốc độ khác nhau. zip phải đợi phần tử tương ứng ở cả hai phía và có thể giữ phần tử từ luồng nhanh trong khi chờ luồng chậm. Nếu một luồng hoàn tất, luồng kết quả của zip cũng có thể hoàn tất khi không còn cặp đầy đủ. combineLatest có ngữ nghĩa khác và thường phát kết quả sau khi cả hai nguồn đã phát ít nhất một giá trị.

Với nhiều output, mỗi binding có thể có tốc độ tiêu thụ và lỗi riêng. Một nhánh chậm có thể tạo backlog trong khi nhánh khác xử lý bình thường. Cần xem xét:

- Backpressure và khả năng điều tiết nguồn.
- Giới hạn bộ đệm khi ghép luồng có tốc độ không cân bằng.
- Retry và DLQ cho từng output binding.
- Hành vi khi một output không kết nối được hoặc consumer của nhánh đó dừng.
- Khả năng một nhánh được subscribe nhiều lần khi tái sử dụng cùng publisher.
- Tính idempotent nếu message có thể được phát lại sau lỗi.

Không giả định nhiều output binding tạo thành một giao dịch nguyên tử. Nếu gửi đến output 0 thành công nhưng output 1 thất bại, hệ thống có thể chỉ phát được một phần kết quả. Với yêu cầu nhất quán giữa nhiều luồng, cần thiết kế event ID, outbox, trạng thái phát từng nhánh hoặc quy trình bù trừ phù hợp.

## 9. Kiểm thử số lượng cổng và dữ liệu từng nhánh

Test binder của Spring Cloud Stream có thể kiểm tra từng binding riêng. Với function nhiều input, gửi message vào đúng tên binding đầu vào. Với function nhiều output, đọc message từ từng output binding để xác nhận thứ tự tuple và nội dung.

Ví dụ kiểm thử function hai đầu vào, một đầu ra:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "spring.cloud.function.definition=enrichOrders",
        "spring.cloud.stream.bindings.enrichOrders-in-0.destination=orders.in",
        "spring.cloud.stream.bindings.enrichOrders-in-1.destination=customers.in",
        "spring.cloud.stream.bindings.enrichOrders-out-0.destination=orders.out"
})
class EnrichOrdersBindingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void combinesMessagesFromBothInputs() {
        input.send(
                MessageBuilder.withPayload(
                        new OrderCreated("ORD-1", "CUS-1", 12500)).build(),
                "enrichOrders-in-0");

        input.send(
                MessageBuilder.withPayload(
                        new CustomerProfile("CUS-1", "Lan", "GOLD")).build(),
                "enrichOrders-in-1");

        assertNotNull(output.receive(1000, "enrichOrders-out-0"));
    }
}
~~~

Với zip, test phải cung cấp đủ một phần tử ở mỗi input để tạo ra một cặp. Trong kiểm thử thực tế, xác nhận thêm orderId và customerId của kết quả để chắc chắn hàm không ghép nhầm dữ liệu. Với nhiều output, đọc cả routeOrders-out-0 và routeOrders-out-1, kiểm tra mỗi message đi đúng nhánh.

Test binder xác nhận wiring ở cấp ứng dụng nhưng không chứng minh broker thật có cùng hành vi. Kiểm thử tích hợp với Kafka, RabbitMQ hoặc Pulsar cần xác nhận group, partition, queue/subscription, backpressure, retry và tình huống một output bị lỗi.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Cấu hình thiếu in-1 hoặc out-1 | Một cổng không được nối đúng destination | Đối chiếu số phần tử tuple với số binding |
| Đảo thứ tự phần tử tuple | Message đi nhầm luồng | Kiểm thử từng output và ghi rõ thứ tự cổng |
| Dùng zip cho hai luồng không tương ứng theo thứ tự | Ghép sai thực thể hoặc chờ không kết thúc | Join theo key/state hoặc tra cứu dữ liệu phù hợp |
| Một publisher bị subscribe nhiều lần | Lặp xử lý hoặc phát lại nguồn | Chia sẻ upstream có chủ đích và kiểm thử subscription |
| Một output lỗi nhưng output khác đã gửi thành công | Kết quả chỉ phát được một phần | Dùng event ID, outbox và quy trình phục hồi |
| Tự subscribe trong reactive function | Mất kiểm soát backpressure và lỗi | Trả về publisher và để framework quản lý subscription khi có thể |

## 11. Checklist trước khi triển khai

- Chọn kiểu Supplier, Function hoặc Consumer phù hợp với số cổng và mục đích xử lý.
- Dùng tuple Reactor cho các hàm reactive có nhiều input hoặc output.
- Khai báo đủ binding theo chỉ số in-0...in-n và out-0...out-n.
- Xác nhận thứ tự tuple khớp với destination được cấu hình.
- Chọn operator ghép luồng theo đúng quan hệ dữ liệu; không nhầm zip với join theo khóa.
- Đánh giá tốc độ input, backpressure, buffer và khả năng một nhánh bị chậm.
- Xử lý lỗi riêng cho từng output và không giả định phát nhiều output là nguyên tử.
- Dùng event ID và consumer idempotent để xử lý khả năng giao lại.
- Kiểm thử từng input, từng output và tích hợp với binder/broker thật.

Spring Cloud Stream hỗ trợ nhiều đầu vào hoặc đầu ra bằng các kiểu hàm reactive chứa tuple của Reactor. Mỗi phần tử tuple tương ứng một binding có chỉ số riêng; cấu hình binding nối từng cổng với destination và group phù hợp. Khi chọn đúng phép kết hợp luồng, quản lý subscription và kiểm thử từng nhánh, ứng dụng có thể ghép dữ liệu từ nhiều nguồn hoặc phân phối kết quả đến nhiều dịch vụ mà vẫn giữ được ranh giới rõ ràng giữa logic hàm và hạ tầng messaging.
