# Phân biệt ghép trong tiến trình với nối ứng dụng qua broker

Trong Spring Cloud Stream, nhiều bước xử lý sự kiện có thể được tổ chức theo hai cách. Các hàm có thể được ghép trực tiếp trong cùng tiến trình bằng Spring Cloud Function, hoặc mỗi ứng dụng có thể thực hiện một phần công việc rồi trao đổi thông điệp qua Kafka, RabbitMQ hay Pulsar. Cả hai cách đều tạo thành một luồng nghiệp vụ nhiều bước, nhưng khác nhau về ranh giới thực thi, giao nhận, triển khai, khả năng mở rộng và cách xử lý lỗi.

Ghép hàm trong tiến trình phù hợp khi các bước thuộc cùng một ứng dụng, cần gọi trực tiếp và có thể triển khai cùng nhau. Nối ứng dụng qua broker phù hợp khi các năng lực cần độc lập về vòng đời, quy mô, công nghệ hoặc quyền sở hữu. Việc lựa chọn cần xuất phát từ yêu cầu vận hành và hợp đồng dữ liệu, không chỉ từ số lượng bước trong sơ đồ.

## 1. Hai cách tổ chức một luồng xử lý

Giả sử một sự kiện **OrderCreated** cần được bổ sung thông tin khách hàng, kiểm tra điều kiện và ghi nhận kết quả.

Với ghép trong tiến trình, một ứng dụng có thể gọi lần lượt các Function:

~~~mermaid
flowchart LR
    A[Input binding] --> B[enrichOrder]
    B --> C[validateOrder]
    C --> D[Output binding]
~~~

Thông điệp được chuyển từ hàm này sang hàm kế tiếp trong cùng tiến trình. Broker chỉ tham gia ở đầu vào hoặc đầu ra của toàn chuỗi nếu ứng dụng có binding tương ứng.

Với các ứng dụng độc lập nối qua broker, mỗi bước có thể chạy ở một tiến trình riêng:

~~~mermaid
flowchart LR
    A[Order API] --> B[Topic orders]
    B --> C[Order enrichment service]
    C --> D[Topic enriched-orders]
    D --> E[Validation service]
    E --> F[Topic validated-orders]
    F --> G[Order persistence service]
~~~

Ở đây broker nằm giữa các ứng dụng. Mỗi ứng dụng nhận thông điệp từ destination của mình, xử lý rồi phát sự kiện mới tới destination tiếp theo. Broker tạo ranh giới truyền tin và lưu trữ theo chính sách của nó.

## 2. Ghép hàm trong cùng tiến trình

Spring Cloud Function cho phép ghép các bean Function bằng ký hiệu **|** trong thuộc tính **spring.cloud.function.definition**. Đầu ra của hàm trước trở thành đầu vào của hàm kế tiếp. Kiểu dữ liệu ở hai đầu phải tương thích.

Ví dụ, một ứng dụng có hai bước:

~~~java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderCreated, OrderEnriched> enrichOrder(
            CustomerDirectory customers) {
        return order -> {
            Customer customer = customers.find(order.customerId());
            return new OrderEnriched(
                    order.orderId(),
                    order.customerId(),
                    customer.segment(),
                    order.total()
            );
        };
    }

    @Bean
    public Function<OrderEnriched, OrderValidated> validateOrder(
            OrderRules rules) {
        return order -> {
            rules.validate(order);
            return new OrderValidated(
                    order.orderId(),
                    order.customerId(),
                    order.segment(),
                    order.total(),
                    true
            );
        };
    }
}
~~~

Khai báo chuỗi hàm:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder
~~~

Spring Cloud Function tạo một Function tổng hợp. Khi Function này được gọi với **OrderCreated**, nó gọi **enrichOrder**, lấy **OrderEnriched** rồi chuyển kết quả sang **validateOrder** để nhận **OrderValidated**.

Đừng nhầm dấu **|** với dấu chấm phẩy trong danh sách function definition. Dấu **|** ghép các hàm thành một chuỗi gọi liên tiếp. Dấu chấm phẩy dùng để chọn nhiều hàm độc lập; nó không tự chuyển đầu ra của hàm này sang đầu vào của hàm khác và cũng không tạo ranh giới broker.

Nếu dùng chuỗi hàm đó làm điểm xử lý của Spring Cloud Stream, composite function được binding như một endpoint. Có thể cấu hình destination cho binding đầu vào và đầu ra của composite function. Tên binding mặc định được hình thành từ định nghĩa hàm tổng hợp; nếu muốn tên dễ quản lý hơn, có thể dùng cơ chế ánh xạ binding của Spring Cloud Stream. Hãy xác minh tên binding được tạo trong phiên bản dự án và dùng đúng tên đó trong cấu hình.

Có thể đặt alias ngắn cho hai binding của composite function để phần cấu hình destination dễ đọc hơn:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder
    stream:
      function:
        bindings:
          "enrichOrder|validateOrder-in-0": orders-in
          "enrichOrder|validateOrder-out-0": validated-out
      bindings:
        orders-in:
          destination: orders
          group: order-processing-v1
        validated-out:
          destination: validated-orders
~~~

Hai khóa trong **spring.cloud.stream.function.bindings** là tên binding mặc định của composite function; các giá trị **orders-in** và **validated-out** là alias dùng trong phần cấu hình **spring.cloud.stream.bindings**. Cách ánh xạ này giúp destination và group được khai báo bằng tên ngắn, đồng thời vẫn giữ rõ ranh giới giữa binding của chuỗi hàm và tên binding alias. Không dùng tên bean đơn lẻ **enrichOrder-in-0** để mặc định suy ra rằng nó là input của cả chuỗi.

### Dữ liệu được chuyển tiếp như thế nào?

Khi ghép hàm trong cùng tiến trình, kết quả Java của hàm trước được truyền trực tiếp cho hàm sau theo hợp đồng kiểu dữ liệu. Không có lần publish/consume broker giữa hai bước, trừ khi chính logic ứng dụng chủ động gửi thêm thông điệp.

Điều này đem lại một số đặc điểm:

- Không cần serialize rồi deserialize dữ liệu giữa từng hàm.
- Không phát sinh network hop hoặc broker round trip giữa các bước.
- Các bước dùng chung tiến trình, cấu hình, classpath và tài nguyên runtime.
- Một lỗi không được xử lý trong hàm có thể truyền lên chuỗi gọi và làm lần xử lý hiện tại thất bại.
- Các bước thường được triển khai, scale và rollback cùng một đơn vị ứng dụng.

Ghép hàm không tự tạo transaction phân tán hay điểm lưu trạng thái trung gian. Nếu bước đầu đã gọi một dịch vụ bên ngoài rồi bước sau thất bại, tác động bên ngoài đó không tự động được hoàn tác. Hãy thiết kế idempotency, transaction cục bộ hoặc cơ chế bù trừ khi nghiệp vụ cần.

## 3. Nối các ứng dụng độc lập qua broker

Khi các bước cần độc lập, mỗi ứng dụng có thể sở hữu một phần của luồng sự kiện. Ứng dụng phát sự kiện lên destination; ứng dụng tiếp theo đăng ký input binding để nhận sự kiện.

Ví dụ, ứng dụng API phát sự kiện đơn hàng bằng StreamBridge:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersOut
      bindings:
        ordersOut:
          destination: orders
          content-type: application/json
~~~

~~~java
@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("ordersOut", event);
    }
}
~~~

Ứng dụng bổ sung thông tin khách hàng chạy độc lập và nhận từ cùng destination:

~~~java
@Bean
public Function<OrderCreated, OrderEnriched> enrichOrder(
        CustomerDirectory customers) {
    return event -> {
        Customer customer = customers.find(event.customerId());
        return new OrderEnriched(
                event.orderId(),
                event.customerId(),
                customer.segment(),
                event.total()
        );
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders
          group: order-enrichment-v1
          content-type: application/json
        enrichOrder-out-0:
          destination: enriched-orders
          content-type: application/json
~~~

Một ứng dụng xác thực đơn hàng khác có thể nhận từ **enriched-orders**, dùng group riêng, rồi phát **OrderValidated** sang destination **validated-orders**. Mỗi ứng dụng có thể được đóng gói, triển khai, cấu hình và scale riêng.

Trong mô hình này, broker là ranh giới giữa các tiến trình. Dữ liệu phải có định dạng wire ổn định; producer và consumer cần thống nhất schema, content type, version và quy tắc xử lý thông điệp không hợp lệ.

## 4. So sánh trực tiếp

| Tiêu chí | Ghép trong tiến trình | Nối ứng dụng qua broker |
|---|---|---|
| Ranh giới | Các hàm trong cùng tiến trình. | Các ứng dụng hoặc tiến trình độc lập. |
| Cách chuyển dữ liệu | Gọi hàm và truyền đối tượng Java. | Serialize, publish, broker lưu/chuyển, consumer deserialize. |
| Độ trễ | Thường thấp hơn do không có network hop giữa các bước. | Có thêm chi phí gửi, lưu và nhận thông điệp. |
| Ghép lỏng | Các bước phụ thuộc cùng runtime và cấu hình ứng dụng. | Các ứng dụng giao tiếp qua hợp đồng thông điệp. |
| Triển khai | Thường phát hành cùng một artifact. | Có thể phát hành từng ứng dụng riêng. |
| Mở rộng | Scale toàn ứng dụng hoặc theo giới hạn của runtime. | Có thể scale riêng từng consumer group/service. |
| Cô lập lỗi | Lỗi có thể làm thất bại cả lần gọi composite. | Broker có thể giữ thông điệp trong khi consumer tạm ngừng; lỗi vẫn cần retry/DLQ. |
| Lưu trạng thái trung gian | Không có điểm lưu tự động giữa các hàm. | Broker có thể lưu thông điệp ở từng ranh giới theo retention/queue policy. |
| Schema | Các bước có thể dùng kiểu Java chung trong cùng codebase. | Cần hợp đồng wire tương thích giữa các phiên bản ứng dụng. |
| Quan sát | Theo dõi trace và log trong một tiến trình. | Cần correlation/trace context xuyên qua broker và nhiều dịch vụ. |
| Giao nhận | Phụ thuộc lần xử lý của binding ngoài cùng và logic nội bộ. | Phụ thuộc xác nhận, offset/cursor, retry và cấu hình từng broker. |

Không có lựa chọn luôn tốt hơn. Ghép hàm làm chuỗi xử lý gọn và hiệu quả trong một ứng dụng. Broker phù hợp khi cần ranh giới vận hành và khả năng phục hồi giữa các năng lực độc lập.

## 5. Khác biệt về lỗi và giao nhận

Trong ghép hàm, nếu **enrichOrder** ném exception, **validateOrder** không nhận kết quả của lần gọi đó. Lỗi được truyền theo cơ chế gọi trong tiến trình. Nếu chuỗi đang được kích hoạt bởi input binding, cách binder xử lý thông điệp lỗi, retry và dead-letter vẫn áp dụng ở ranh giới binding đó theo cấu hình. Không có một thông điệp trung gian được broker xác nhận riêng giữa **enrichOrder** và **validateOrder**.

Trong chuỗi ứng dụng qua broker, mỗi ranh giới có thể có trạng thái giao nhận riêng:

1. Producer gửi sự kiện đến broker.
2. Broker xác nhận nhận theo cơ chế của binder và broker.
3. Consumer nhận và xử lý sự kiện.
4. Consumer xác nhận hoặc commit tiến độ theo ngữ nghĩa broker.
5. Nếu xử lý lỗi, thông điệp có thể được retry hoặc chuyển sang DLQ theo cấu hình.
6. Ứng dụng tiếp theo chỉ nhận sự kiện đầu ra khi bước trước phát thành công.

Điều này tạo ra khả năng lưu đệm và tiếp tục sau khi một ứng dụng ngừng hoạt động. Tuy nhiên, không nên diễn giải broker là bảo đảm exactly-once cho toàn bộ nghiệp vụ. Producer có thể gửi lại sau timeout, consumer có thể xử lý lại sau khi mất ACK hoặc commit chưa hoàn tất, và tác động tới cơ sở dữ liệu ngoài broker cần được bảo vệ riêng.

### Idempotency và tác động nghiệp vụ

Giả sử consumer đã ghi đơn hàng vào cơ sở dữ liệu nhưng bị dừng trước khi offset được commit. Khi khởi động lại, broker có thể giao lại cùng sự kiện. Consumer nên dùng **eventId** hoặc khóa nghiệp vụ để phát hiện lần xử lý lặp.

~~~java
@Transactional
public void apply(OrderValidated event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderRepository.markValidated(event.orderId());
    processedEventRepository.save(event.eventId());
}
~~~

Đoạn mã minh họa ý tưởng; việc bảo đảm duy nhất cần có ràng buộc unique và transaction phù hợp trong cơ sở dữ liệu. Nếu cập nhật cơ sở dữ liệu và publish sự kiện tiếp theo cần nhất quán, hãy cân nhắc transactional outbox hoặc cơ chế tích hợp tương đương. Gọi StreamBridge trong cùng một phương thức **@Transactional** không tự động tạo transaction nguyên tử bao trùm cả cơ sở dữ liệu và broker.

## 6. Khác biệt về thứ tự và partition

Trong cùng tiến trình, thứ tự gọi các Function trong composition được xác định bởi chuỗi **|**. Tuy nhiên, nếu một hàm xử lý bất đồng bộ hoặc trả về kiểu reactive, thứ tự hoàn tất của các phần tử có thể phụ thuộc vào toán tử reactive và concurrency được chọn.

Với broker, thứ tự phụ thuộc vào broker, partition, queue, subscription và cách consumer xử lý song song. Kafka bảo đảm thứ tự trong một partition; các partition khác nhau không có thứ tự tổng thể. RabbitMQ và Pulsar cũng có các quy tắc phân phối và thứ tự riêng theo queue hoặc loại subscription.

Nếu cần giữ thứ tự theo **orderId**, hãy chọn key hoặc partition key nhất quán và bảo đảm các sự kiện liên quan đi qua cùng phân vùng theo khả năng của binder. Đồng thời, không để consumer xử lý song song cùng một khóa theo cách làm đảo thứ tự nghiệp vụ.

Ghép hàm trong tiến trình không cần partition để chuyển dữ liệu giữa các bước. Tuy nhiên, nếu toàn chuỗi nhận nhiều thông điệp đồng thời từ input binding, các lần gọi khác nhau vẫn có thể chạy song song. Cần phân biệt thứ tự giữa các bước trong một lần xử lý với thứ tự giữa nhiều sự kiện.

## 7. Khác biệt về triển khai và mở rộng

Một composite function thường được triển khai như một ứng dụng. Khi cần thêm năng lực xử lý, nhóm phát triển thay đổi code và phát hành lại ứng dụng đó. Việc scale thường tăng số instance của toàn ứng dụng, kể cả khi chỉ một bước đang là nút thắt.

Với broker, từng ứng dụng có thể có số replica khác nhau:

| Ứng dụng | Công việc | Ví dụ cách scale |
|---|---|---|
| Order enrichment | Tra cứu thông tin khách hàng. | Tăng replica khi thời gian gọi hệ thống khách hàng tăng. |
| Order validation | Kiểm tra quy tắc nghiệp vụ. | Tăng consumer khi backlog validation tăng. |
| Order persistence | Ghi kết quả vào cơ sở dữ liệu. | Giới hạn concurrency theo năng lực database. |

Đổi lại, mô hình nhiều ứng dụng cần quản lý thêm deployment, cấu hình, quyền truy cập broker, dashboard, cảnh báo, schema và tương thích phiên bản. Một dịch vụ có thể nâng cấp nhanh hơn dịch vụ khác; vì vậy hợp đồng sự kiện cần hỗ trợ khoảng thời gian các phiên bản cùng tồn tại.

## 8. Chọn ranh giới giữa các bước xử lý

Không nên tạo một ứng dụng mới cho mỗi phép biến đổi nhỏ. Ranh giới ứng dụng có chi phí vận hành và chi phí hợp đồng dữ liệu. Hãy cân nhắc tách khi có một hoặc nhiều lý do rõ ràng:

- Bước xử lý có nhu cầu scale khác đáng kể so với phần còn lại.
- Bước có vòng đời phát hành hoặc đội sở hữu độc lập.
- Bước cần công nghệ, quyền truy cập hoặc môi trường bảo mật riêng.
- Bước cần tiếp tục xử lý khi ứng dụng khác tạm ngừng hoạt động.
- Cần lưu sự kiện trung gian để phát lại, kiểm toán hoặc xây dựng nhiều consumer độc lập.
- Bước xử lý có thể được tái sử dụng bởi nhiều hệ thống thông qua hợp đồng sự kiện.

Nên giữ các bước trong cùng tiến trình khi chúng là các phép biến đổi nhỏ, cần độ trễ thấp, thay đổi cùng nhau và không có yêu cầu lưu trạng thái trung gian. Ví dụ chuẩn hóa chuỗi, kiểm tra định dạng, tính trường dẫn xuất và áp dụng một số quy tắc nội bộ thường có thể ghép trong một Function.

Một cách tiếp cận thực tế là bắt đầu với ranh giới đơn giản, đo độ trễ, backlog, chi phí triển khai và nhu cầu sở hữu. Khi có bằng chứng về nút thắt hoặc yêu cầu độc lập, mới tách một bước thành ứng dụng riêng. Nếu đã có ranh giới broker, hãy giữ event contract ổn định và không để consumer phụ thuộc vào cấu trúc lớp Java nội bộ của producer.

## 9. Kết hợp ghép hàm và broker trong cùng kiến trúc

Hai cách tổ chức không loại trừ nhau. Một ứng dụng có thể nhận thông điệp từ broker, ghép nhiều Function trong tiến trình để xử lý, rồi phát kết quả tới destination khác. Các ứng dụng ở hai phía vẫn độc lập.

Ví dụ:

~~~mermaid
flowchart LR
    A[Producer service] --> B[(Topic orders)]
    B --> C[Input binding]
    C --> D[enrichOrder]
    D --> E[validateOrder]
    E --> F[Output binding]
    F --> G[(Topic validated-orders)]
    G --> H[Persistence service]
~~~

Trong sơ đồ, **enrichOrder** và **validateOrder** được ghép trong cùng ứng dụng xử lý đơn hàng. Producer service và persistence service là các ứng dụng độc lập, trao đổi qua broker. Cách này giữ chi phí thấp cho các bước nội bộ nhưng vẫn tạo ranh giới rõ ràng giữa các năng lực cần độc lập.

Khi kết hợp, hãy đặt tên destination theo ý nghĩa sự kiện, ví dụ **orders** và **validated-orders**; dùng group ổn định cho consumer; version hóa payload khi hợp đồng thay đổi; và gắn event ID/correlation ID xuyên suốt luồng. Tránh để tên Function nội bộ trở thành hợp đồng công khai giữa các dịch vụ.

## 10. Kiểm thử hai mô hình

Kiểm thử ghép hàm tập trung vào thứ tự gọi, kiểu dữ liệu và hành vi lỗi giữa các bước. Có thể kiểm thử composite function trực tiếp hoặc dùng test binder để xác nhận input/output binding của toàn chuỗi.

Kiểm thử nối ứng dụng qua broker cần xác minh cả hợp đồng giữa hai ứng dụng và hành vi broker:

| Kiểm thử | Ghép trong tiến trình | Nối ứng dụng qua broker |
|---|---|---|
| Kiểu dữ liệu | Xác nhận output của hàm trước phù hợp input hàm sau. | Xác nhận serializer và deserializer tương thích qua wire format. |
| Thứ tự bước | Xác nhận Function được gọi theo composition. | Xác nhận destination và topology nối đúng các ứng dụng. |
| Lỗi ở bước giữa | Xác nhận exception truyền theo chuỗi và xử lý tại binding ngoài cùng. | Xác nhận retry, ACK/commit và DLQ tại ranh giới consumer tương ứng. |
| Khởi động lại | Kiểm tra hành vi của toàn ứng dụng và input binding. | Dừng một service, kiểm tra broker giữ backlog rồi khởi động lại consumer. |
| Phiên bản schema | Kiểm tra DTO và mapper trong cùng ứng dụng. | Kiểm tra producer mới với consumer cũ và ngược lại theo yêu cầu tương thích. |
| Tải | Đo throughput và concurrency của toàn composite. | Đo backlog, lag và khả năng scale riêng từng consumer group. |
| Xử lý lặp | Kiểm tra idempotency khi input binding giao lại. | Kiểm tra idempotency qua timeout, redelivery và replay. |

Với test binder, có thể kiểm tra logic Spring Cloud Stream mà không cần broker thật. Nhưng test binder không mô phỏng đầy đủ retention, partition rebalance, queue durability, subscription cursor hay xác nhận của broker. Các thuộc tính đó cần integration test với Kafka, RabbitMQ hoặc Pulsar tương ứng.

### Ma trận tình huống nên thử

1. Gửi một sự kiện hợp lệ và xác nhận kết quả cuối cùng.
2. Làm bước đầu ném exception và kiểm tra bước sau không xử lý dữ liệu thiếu.
3. Làm bước sau thất bại và kiểm tra retry hoặc luồng lỗi của binding.
4. Dừng consumer trong mô hình broker, gửi thêm sự kiện, rồi khởi động lại để xác nhận backlog được xử lý.
5. Gửi cùng event ID hai lần và xác nhận tác động nghiệp vụ chỉ được áp dụng một lần khi yêu cầu idempotency.
6. Thay đổi schema sự kiện và chạy consumer với fixture của phiên bản cũ.
7. Tăng tải ở một bước và quan sát liệu scale toàn ứng dụng hay scale riêng service có phù hợp hơn.

## 11. Lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Tách mỗi Function thành một service dù chỉ làm biến đổi nhỏ | Chưa tính chi phí vận hành, network hop và schema. | Ghép các bước nội bộ có vòng đời chung. |
| Ghép quá nhiều bước vào một ứng dụng | Các bước cần scale, phát hành hoặc phục hồi độc lập. | Tạo ranh giới broker tại năng lực có yêu cầu vận hành riêng. |
| Nghĩ ghép Function tạo checkpoint giữa các bước | Nhầm gọi hàm trực tiếp với publish/consume. | Dùng broker nếu cần lưu thông điệp trung gian và phát lại độc lập. |
| Cho rằng broker bảo đảm exactly-once toàn nghiệp vụ | Bỏ qua lỗi giữa commit, ACK và cập nhật hệ thống ngoài. | Dùng idempotency, transaction cục bộ hoặc outbox theo yêu cầu. |
| Consumer mới không đọc được sự kiện cũ | Hợp đồng schema thay đổi không tương thích. | Duy trì backward compatibility và kiểm thử payload lịch sử. |
| Các service xử lý sai thứ tự theo khóa | Không có partition key hoặc consumer xử lý song song thiếu kiểm soát. | Thiết kế key/partition và concurrency theo yêu cầu thứ tự. |
| Không truy vết được luồng qua nhiều service | Thiếu event ID, correlation ID hoặc trace context. | Truyền metadata tương quan và cấu hình tracing qua broker. |
| Scale một bước nhưng phải tăng toàn bộ ứng dụng | Các bước bị ghép trong cùng đơn vị triển khai. | Cân nhắc tách bước có tải khác biệt rõ rệt. |

## 12. Quy trình lựa chọn và triển khai

Trước khi quyết định, hãy ghi lại các bước nghiệp vụ và trả lời:

1. Các bước có cùng đội sở hữu và cùng chu kỳ phát hành không?
2. Chúng có cần scale độc lập hoặc dùng tài nguyên khác nhau không?
3. Có cần lưu sự kiện trung gian để tiếp tục sau sự cố hoặc phát lại không?
4. Có consumer độc lập nào khác cần nhận cùng sự kiện không?
5. Hợp đồng dữ liệu có thể được duy trì ổn định giữa các phiên bản không?
6. Chi phí vận hành thêm một service có tương xứng với lợi ích không?

Sau khi chọn mô hình:

- Nếu ghép trong tiến trình, khai báo **spring.cloud.function.definition**, kiểm tra kiểu đầu vào/đầu ra của từng hàm và cấu hình binding cho composite function.
- Nếu nối qua broker, xác định destination, group, content type, schema, retry/DLQ, quyền truy cập và chính sách lưu giữ.
- Nếu kết hợp, đặt ranh giới broker ở những điểm có yêu cầu độc lập và giữ các phép biến đổi nội bộ trong composite function.
- Với cả hai mô hình, kiểm thử lỗi, tải, giao nhận lặp và khả năng tương thích schema trước khi triển khai.

Ghép hàm trong tiến trình và nối ứng dụng qua broker là hai cách tổ chức có đặc tính khác nhau. Ghép hàm truyền kết quả trực tiếp giữa các Function trong một runtime, giúp giảm độ trễ và đơn giản hóa luồng nội bộ. Broker tạo ranh giới bất đồng bộ giữa các ứng dụng, cho phép lưu đệm, triển khai và mở rộng độc lập nhưng đòi hỏi quản lý hợp đồng dữ liệu, giao nhận và quan sát xuyên dịch vụ. Spring Cloud Stream hỗ trợ kết hợp cả hai để cân bằng giữa hiệu quả xử lý và tính độc lập vận hành.
