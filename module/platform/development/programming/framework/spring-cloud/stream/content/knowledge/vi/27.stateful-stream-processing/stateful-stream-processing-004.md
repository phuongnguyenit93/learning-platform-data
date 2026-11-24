# Phép nối KStream, KTable và GlobalKTable

Trong xử lý sự kiện, một luồng giao dịch thường cần được bổ sung thông tin từ dữ liệu tham chiếu như hồ sơ khách hàng, danh mục sản phẩm hoặc trạng thái tài khoản. Kafka Streams cung cấp ba abstraction quan trọng để biểu diễn dữ liệu và thực hiện phép nối: KStream, KTable và GlobalKTable. Chọn đúng kiểu đầu vào quyết định ý nghĩa của phép join, yêu cầu partition, cách lưu trạng thái và chi phí khi mở rộng ứng dụng.

KStream biểu diễn các sự kiện độc lập, mỗi record là một lần phát sinh. KTable biểu diễn trạng thái mới nhất theo key, được xây dựng từ changelog có thao tác insert, update và delete. GlobalKTable cũng biểu diễn trạng thái mới nhất nhưng mỗi instance Kafka Streams đọc toàn bộ partition của topic nguồn để giữ một bản sao cục bộ đầy đủ. Vì vậy, KStream-KStream join là phép nối theo cửa sổ thời gian; KStream-KTable là phép tra cứu bảng khi một sự kiện đến; KTable-KTable tạo một bảng kết quả liên tục được cập nhật; còn KStream-GlobalKTable phù hợp để bổ sung dữ liệu tham chiếu theo khóa ngoại mà không yêu cầu hai topic co-partition.

Spring Cloud Stream Kafka Streams binder cho phép khai báo các kiểu này ngay trong chữ ký hàm Supplier/Function/Consumer. Binder tạo input binding tương ứng với KStream, KTable hoặc GlobalKTable, sau đó ứng dụng dùng Kafka Streams DSL để xây dựng topology. Bài học này trình bày semantics của từng loại join, yêu cầu partitioning, cửa sổ/grace, Serde, state store, cách cấu hình binder, kiểm thử và vận hành.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt KStream, KTable và GlobalKTable theo ý nghĩa của record.
- Chọn đúng loại join cho sự kiện, bảng trạng thái và dữ liệu tham chiếu.
- Thực hiện KStream-KStream join với JoinWindows và grace period.
- Thực hiện KStream-KTable join để làm giàu sự kiện bằng trạng thái mới nhất.
- Thực hiện KTable-KTable join để tạo bảng kết quả liên tục được cập nhật.
- Dùng KStream-GlobalKTable join để tra cứu theo khóa ngoại.
- Giải thích co-partitioning, repartition và giới hạn của partition key.
- Cấu hình nhiều input binding trong Spring Cloud Stream Kafka Streams binder.
- Chọn Serde, materialize state store và hiểu tombstone.
- Kiểm thử join bằng TopologyTestDriver và kiểm tra hành vi thực tế với Kafka.

## 1. Ba cách nhìn dữ liệu trong Kafka Streams

Kafka lưu record dưới dạng key-value trong partition. Kafka Streams bổ sung ý nghĩa cho chuỗi record đó bằng cách diễn giải nó như một dòng sự kiện hoặc một changelog trạng thái.

### 1.1. KStream: dòng sự kiện

KStream là một luồng record không giới hạn. Mỗi record được xem là một sự kiện độc lập, tương tự một dòng mới được thêm vào sổ cái. Hai record có cùng key không có nghĩa record thứ hai thay thế record thứ nhất.

Ví dụ:

~~~text
Topic clicks:
  (user-17, 1)
  (user-17, 3)
~~~

Đây là hai lần click. Nếu cộng giá trị theo user, tổng là 4. Record thứ hai không xóa record đầu.

KStream phù hợp với:

- Sự kiện đơn hàng được tạo.
- Lần thanh toán được xác nhận.
- Lượt xem trang hoặc lượt click.
- Log hoạt động và sự kiện thiết bị.
- Các giao dịch cần được phân tích theo thời gian.

### 1.2. KTable: trạng thái mới nhất theo key

KTable được xây dựng từ changelog stream. Record có key đã tồn tại được xem là bản cập nhật giá trị hiện tại của key đó. Giá trị null là tombstone, biểu thị việc xóa key khỏi bảng.

Ví dụ:

~~~text
Topic customer-profile:
  (user-17, "Bronze")
  (user-17, "Gold")
  (user-22, "Silver")
  (user-22, null)
~~~

Trạng thái cuối:

~~~text
user-17 -> Gold
~~~

Record Gold thay thế Bronze. Tombstone xóa user-22 khỏi bảng. Đây là semantics upsert/delete, tương tự bảng quan hệ được cập nhật theo khóa chính.

KTable phù hợp với:

- Hồ sơ khách hàng hiện tại.
- Trạng thái đơn hàng mới nhất.
- Bảng giá hoặc cấu hình hiện hành.
- Dữ liệu CDC phản ánh insert/update/delete từ database.
- Dimension table được cập nhật liên tục.

### 1.3. GlobalKTable: bản sao đầy đủ trên mỗi instance

GlobalKTable cũng là changelog table nhưng mỗi instance Kafka Streams đọc toàn bộ partition của topic nguồn và duy trì bản sao đầy đủ trong local state store. KTable thông thường chỉ đọc phần partition được gán cho instance/task; GlobalKTable đọc toàn bộ dữ liệu của topic trên mỗi instance.

Giả sử topic products có sáu partition và ứng dụng chạy ba instance:

~~~text
KTable:
  Instance A đọc một tập partition được gán
  Instance B đọc một tập partition được gán
  Instance C đọc một tập partition được gán

GlobalKTable:
  Instance A giữ bản sao của cả sáu partition
  Instance B giữ bản sao của cả sáu partition
  Instance C giữ bản sao của cả sáu partition
~~~

GlobalKTable hữu ích khi luồng sự kiện lớn cần tra cứu một bảng tham chiếu nhỏ hoặc vừa, ví dụ ánh xạ productId sang tên sản phẩm, customerId sang phân khúc hoặc mã vùng sang thông tin địa lý.

Đổi lại, mỗi instance phải lưu toàn bộ bảng và đọc toàn bộ changelog. Điều này làm tăng disk, memory, network và tải broker. GlobalKTable không có khái niệm thời gian sự kiện; phép join không phải temporal join.

### 1.4. Bảng so sánh

| Đặc điểm | KStream | KTable | GlobalKTable |
|---|---|---|---|
| Ý nghĩa record | Sự kiện độc lập | Cập nhật trạng thái theo key | Cập nhật trạng thái theo key |
| Record trùng key | Giữ lại như sự kiện mới | Thay giá trị hiện tại | Thay giá trị hiện tại |
| Giá trị null | Thường bị bỏ qua trong join | Tombstone xóa key | Tombstone xóa key |
| Dữ liệu mỗi instance | Một phần partition được gán | Một phần partition được gán | Toàn bộ partition |
| Join thường dùng | Stream-stream, stream-table | Table-table, stream-table | Stream-global-table |
| Co-partition | Cần với equi-join stream/table | Cần với equi-join | Không cần khi join với KStream |
| Chi phí local state | Theo topology/window | Theo partition được gán | Toàn bộ bảng trên mỗi instance |

## 2. Chọn join theo ý nghĩa nghiệp vụ

Trước khi viết code, hãy xác định dữ liệu ở hai phía có ý nghĩa gì:

- Hai phía đều là sự kiện phát sinh theo thời gian: KStream-KStream.
- Một phía là sự kiện, phía kia là trạng thái mới nhất: KStream-KTable.
- Cả hai phía là trạng thái mới nhất và kết quả cũng phải cập nhật theo thay đổi: KTable-KTable.
- Sự kiện cần tra cứu một bảng tham chiếu đầy đủ, có thể dùng khóa ngoại: KStream-GlobalKTable.

| Phép nối | Có cửa sổ? | Join key | Điều kiện partition | Khi nào phát kết quả? |
|---|---|---|---|---|
| KStream-KStream | Có | Key bằng nhau và timestamp nằm trong cửa sổ | Co-partition | Khi record mới khớp record phía kia |
| KStream-KTable | Không mặc định | Key bằng nhau | Co-partition | Khi record KStream đến |
| KTable-KTable equi-join | Không | Key bằng nhau | Co-partition | Khi một trong hai bảng thay đổi |
| KTable-KTable foreign-key join | Không | Giá trị khóa ngoại của bảng trái bằng key bảng phải | Kafka Streams xử lý co-partition nội bộ | Khi một phía liên quan thay đổi |
| KStream-GlobalKTable | Không | Key được mapper tra cứu trong global table | Không cần co-partition | Khi record KStream đến |

Kafka Streams hỗ trợ inner/left/outer cho KStream-KStream; inner/left cho KStream-KTable và KStream-GlobalKTable; inner/left/outer cho KTable-KTable equi-join. Foreign-key KTable-KTable hỗ trợ inner và left join, không hỗ trợ outer join. KTable-GlobalKTable join không được hỗ trợ.

## 3. KStream-KStream join: nối hai luồng sự kiện theo thời gian

KStream-KStream join luôn là windowed join. Nếu không giới hạn thời gian, state store phải giữ các record chờ khớp vô hạn và có thể tăng mãi. JoinWindows xác định khoảng thời gian mà hai record cùng key được xem là có liên quan.

Ví dụ dịch vụ thương mại điện tử có hai topic:

- orders: sự kiện OrderCreated.
- payments: sự kiện PaymentAuthorized.

Ứng dụng cần ghép đơn hàng với thanh toán nếu hai sự kiện có cùng orderId và đến trong khoảng thời gian năm phút.

~~~text
orders stream                     payments stream
  order-81 @ 10:00:00               order-81 @ 10:02:10
          \                         /
           \                       /
            +-- same key + window -+
                       |
                       v
             OrderWithPayment
~~~

### 3.1. Inner join

Inner join chỉ phát kết quả khi tìm thấy record khớp ở cả hai phía. Nếu OrderCreated không có PaymentAuthorized trong cửa sổ, inner join không phát kết quả cho order đó.

### 3.2. Left join

Left join giữ record phía trái. Nếu không có record phía phải phù hợp trong cửa sổ, kết quả phía trái có thể được phát với giá trị phải là null sau khi cửa sổ và grace period kết thúc theo semantics của API đang dùng.

### 3.3. Outer join

Outer join giữ record không khớp từ cả hai phía. Record chỉ xuất hiện ở orders hoặc chỉ ở payments có thể tạo kết quả với một phía null sau khi cửa sổ được đóng.

Với API JoinWindows mới, left/outer join phát kết quả không khớp sau khi cửa sổ đóng và grace period đã qua. Các overload cũ đã deprecated có thể có semantics eager-emit khác; hãy dùng API tương ứng với phiên bản Kafka Streams của dự án và khai báo grace rõ ràng.

### 3.4. Code ví dụ

~~~java
import java.time.Duration;
import java.util.function.BiFunction;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.JoinWindows;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.StreamJoined;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderJoinConfiguration {

    @Bean
    BiFunction<KStream<String, OrderCreated>,
            KStream<String, PaymentAuthorized>,
            KStream<String, OrderWithPayment>> joinOrders() {

        return (orders, payments) -> orders.join(
                payments,
                OrderWithPayment::new,
                JoinWindows.ofTimeDifferenceAndGrace(
                        Duration.ofMinutes(5),
                        Duration.ofSeconds(30)),
                StreamJoined.with(
                        Serdes.String(),
                        orderCreatedSerde(),
                        paymentAuthorizedSerde()));
    }
}
~~~

OrderCreated, PaymentAuthorized, OrderWithPayment và hai Serde nghiệp vụ là các kiểu minh họa. Trong dự án thực tế, hãy cung cấp Serde tương ứng với schema đang dùng. Nếu phiên bản Kafka Streams chưa có factory ofTimeDifferenceAndGrace, dùng API tương thích của phiên bản đó và xác định rõ grace period; không sao chép máy móc ví dụ từ version khác.

Trong ví dụ, hai stream được join theo key String. OrderCreated và PaymentAuthorized phải dùng cùng orderId làm Kafka record key, cùng partitioning strategy và cùng số partition để record cùng orderId tới cùng stream task.

### 3.5. Cửa sổ và grace period

Join window xác định độ chênh timestamp tối đa giữa hai record được phép ghép. Grace period xác định khoảng trễ mà hệ thống vẫn chấp nhận record đến muộn sau khi cửa sổ kết thúc.

Ví dụ:

- Join window: 5 phút.
- Grace period: 30 giây.
- OrderCreated có timestamp 10:00.
- PaymentAuthorized có timestamp 10:04:30: vẫn nằm trong cửa sổ.
- PaymentAuthorized đến muộn sau khi cửa sổ và grace đã đóng: không còn được ghép vào kết quả đó.

Grace period là một trade-off:

- Grace dài hơn cho phép dữ liệu đến trễ được xử lý, nhưng giữ state lâu hơn và có thể làm kết quả left/outer xuất hiện muộn hơn.
- Grace ngắn giảm thời gian chờ và dung lượng state, nhưng loại bỏ nhiều record đến trễ hơn.

Hãy chọn dựa trên độ trễ thực tế của producer, event-time semantics và SLA nghiệp vụ. Timestamp cần được tạo nhất quán; không dùng thời gian xử lý ở consumer thay cho event time nếu nghiệp vụ cần ghép theo thời điểm phát sinh.

### 3.6. Một record có thể khớp nhiều record

KStream-KStream join không phải luôn là quan hệ một-một. Nếu có nhiều record cùng key trong cùng cửa sổ ở hai phía, một record mới có thể tạo nhiều output với các record đã lưu của phía kia.

Ví dụ một order có nhiều lần payment attempt. Hãy xác định nghiệp vụ muốn ghép tất cả attempt, chỉ attempt thành công hay một giao dịch duy nhất. Có thể cần filter/deduplicate trước join hoặc dùng key riêng cho payment attempt.

## 4. KStream-KTable join: làm giàu sự kiện bằng trạng thái hiện tại

KStream-KTable join là phép tra cứu bảng không cửa sổ. Mỗi khi record KStream đến, Kafka Streams tìm giá trị hiện tại trong KTable theo key và đưa hai giá trị cho ValueJoiner.

Ví dụ:

- KStream clicks: (userId, ClickEvent).
- KTable user-regions: (userId, region).
- Kết quả: (userId, ClickWithRegion).

~~~text
KStream clicks                    KTable user-regions
  user-17 -> click                  user-17 -> Hanoi
            \                       /
             +---- lookup by key --+
                        |
                        v
             ClickWithRegion(Hanoi)
~~~

### 4.1. Semantics cần nhớ

- Chỉ record KStream kích hoạt phép join.
- Record KTable cập nhật state store, nhưng tự nó không phát lại các record KStream cũ.
- Inner join bỏ qua record stream nếu chưa có key tương ứng trong table.
- Left join phát record stream ngay cả khi không có giá trị table; ValueJoiner nhận null ở phía table.
- Tombstone của KTable xóa key khỏi trạng thái; tombstone không tự kích hoạt join.
- Join thông thường dùng giá trị mới nhất mà task đang biết tại thời điểm record stream được xử lý.

Điều này có nghĩa KStream-KTable không phải phép nối theo event time. Nếu sự kiện đến muộn và cần tra cứu phiên bản dimension có hiệu lực tại thời điểm sự kiện xảy ra, hãy đánh giá versioned KTable cùng grace period trong các phiên bản hỗ trợ.

### 4.2. Code ví dụ

~~~java
@Bean
BiFunction<KStream<String, Long>,
        KTable<String, String>,
        KStream<String, RegionWithClicks>> enrichClicks() {

    return (clicks, regions) -> clicks.leftJoin(
            regions,
            (count, region) -> new RegionWithClicks(
                    region == null ? "UNKNOWN" : region,
                    count),
            Joined.with(
                    Serdes.String(),
                    Serdes.Long(),
                    Serdes.String()));
}
~~~

Trong ví dụ, click stream và region table dùng userId làm key. Left join bảo đảm click vẫn xuất hiện khi hồ sơ vùng chưa được nạp hoặc đã bị xóa. Nếu dùng join thay vì leftJoin, click không tìm được region sẽ không tạo output.

### 4.3. Khi nào KStream-KTable không đủ?

Giả sử sự kiện click được phát lúc 09:00 nhưng đến Kafka Streams lúc 09:10. Trong thời gian đó, user đã chuyển vùng từ Hanoi sang Da Nang. Join thông thường có thể lấy trạng thái Da Nang hiện tại, dù sự kiện xảy ra khi user còn ở Hanoi.

Nếu nghiệp vụ yêu cầu thông tin có hiệu lực tại event time:

- Dùng versioned KTable nếu phiên bản Kafka Streams và API join hỗ trợ temporal lookup.
- Đặt timestamp extractor nhất quán.
- Cấu hình grace period để chờ update table đến muộn.
- Xác định retention lịch sử của versioned store.
- Kiểm thử trường hợp stream event đến trước update table có timestamp cũ hơn.

Nếu chỉ cần trạng thái mới nhất tại lúc xử lý, KStream-KTable thông thường đơn giản và phù hợp hơn.

## 5. KTable-KTable join: tạo bảng kết quả liên tục

KTable-KTable join nối hai bảng trạng thái theo key và trả về một KTable mới. Đây là phép join không cửa sổ, gần với join giữa hai bảng quan hệ. Kafka Streams materialize state của hai bảng để duy trì snapshot hiện tại.

Ví dụ:

- KTable customers: customerId -> Customer.
- KTable loyalty: customerId -> LoyaltyTier.
- KTable kết quả: customerId -> CustomerProfile.

~~~text
KTable customers                 KTable loyalty
  c-10 -> Customer                 c-10 -> GOLD
             \                     /
              +---- join by key --+
                         |
                         v
             KTable CustomerProfile
~~~

### 5.1. Kết quả được cập nhật từ cả hai phía

Khác với KStream-KTable, thay đổi ở một trong hai KTable có thể làm thay đổi kết quả join:

1. Customer c-10 được cập nhật địa chỉ: output profile được cập nhật.
2. Loyalty của c-10 đổi từ GOLD sang PLATINUM: output profile được cập nhật.
3. Customer bị xóa bằng tombstone: kết quả tương ứng được cập nhật/xóa theo semantics join.

KTable kết quả là changelog table. Khi chuyển nó sang KStream bằng toStream(), mỗi thay đổi của bảng kết quả được phát như một record changelog.

### 5.2. Code ví dụ

~~~java
@Bean
BiFunction<KTable<String, Customer>,
        KTable<String, LoyaltyTier>,
        KTable<String, CustomerProfile>> buildCustomerProfile() {

    return (customers, loyalty) -> customers.leftJoin(
            loyalty,
            (customer, tier) -> new CustomerProfile(
                    customer,
                    tier == null ? LoyaltyTier.NONE : tier));
}
~~~

Đây là left equi-join theo customerId. Khi không có loyalty record, profile vẫn tồn tại với tier mặc định. Nếu dùng inner join, customer chưa có loyalty sẽ không có trong bảng kết quả.

### 5.3. Foreign-key join

Không phải lúc nào hai bảng cũng dùng cùng key. Ví dụ:

- KTable orders có key orderId và value chứa customerId.
- KTable customers có key customerId.

KTable-KTable foreign-key join dùng extractor lấy customerId từ value của bảng trái rồi tra cứu key ở bảng phải:

~~~java
KTable<String, OrderWithCustomer> ordersWithCustomer =
        orders.leftJoin(
                customers,
                Order::customerId,
                (order, customer) -> new OrderWithCustomer(order, customer));
~~~

Foreign-key join không yêu cầu hai topic co-partition theo cách equi-join thông thường; Kafka Streams quản lý việc phối hợp nội bộ. Một cập nhật ở bảng phải có thể làm cập nhật mọi record bên trái tham chiếu tới key đó. Đây là chi phí cần tính khi một customer được tham chiếu bởi rất nhiều order hoặc entity.

Foreign-key join chỉ có trong các phiên bản Kafka Streams hỗ trợ API này. Kiểm tra dependency trước khi dùng và nhớ rằng foreign-key join không hỗ trợ outer join.

## 6. KStream-GlobalKTable join: tra cứu theo khóa ngoại

GlobalKTable cho phép một record KStream tra cứu bảng theo key được tính từ nội dung record, không bắt buộc stream key và table key giống nhau.

Ví dụ:

- KStream orders: key là orderId, value chứa customerId.
- GlobalKTable customers: key là customerId.
- Join mapper lấy customerId từ Order rồi tra cứu trong GlobalKTable.

~~~java
@Bean
BiFunction<KStream<Long, Order>,
        GlobalKTable<Long, Customer>,
        KStream<Long, EnrichedOrder>> enrichOrder() {

    return (orders, customers) -> orders.join(
            customers,
            (orderId, order) -> order.customerId(),
            (order, customer) -> new EnrichedOrder(order, customer));
}
~~~

KeyValueMapper trong tham số thứ hai chuyển record KStream thành key tra cứu của GlobalKTable. Vì vậy, orderId có thể khác customerId.

### 6.1. Không cần co-partition

GlobalKTable đọc toàn bộ partition của topic tham chiếu trên từng instance. Mỗi instance có bản sao cục bộ của toàn bảng, nên stream record có thể tra cứu key ngoại mà không cần record cùng key nằm trên cùng partition giữa hai topic.

### 6.2. Không phải temporal join

GlobalKTable không có notion of time và không đồng bộ event time giữa cập nhật bảng với record stream. Khi record stream được xử lý, phép join dùng giá trị hiện có trong bản sao GlobalKTable ở instance đó. Không dùng GlobalKTable nếu cần truy vấn chính xác phiên bản dimension tại timestamp của sự kiện.

### 6.3. Chi phí bootstrap và bản sao

Khi Kafka Streams instance khởi động lại hoặc được tạo mới, nó phải bootstrap toàn bộ dữ liệu hiện có trong topic nguồn trước khi bắt đầu xử lý stream theo topology. Topic lớn có thể làm tăng startup time và network load.

Mỗi instance lưu toàn bộ bảng. Nếu bảng có dung lượng 8 GB và chạy 5 instance, tổng dung lượng local state có thể xấp xỉ 40 GB trước khi tính overhead, changelog và các state store khác. Hãy đo dữ liệu thực tế và tính chi phí nhân bản.

### 6.4. Khi nào nên dùng?

GlobalKTable phù hợp khi:

- Bảng tham chiếu nhỏ hoặc vừa.
- Nhiều stream partition cần tra cứu các dimension key tùy ý.
- Dữ liệu tham chiếu được cập nhật tương đối thường xuyên nhưng không cần temporal join.
- Cần star join với nhiều bảng dimension.
- Phân bố key của stream bị lệch và muốn tránh hot partition ở bảng tham chiếu.

Nếu bảng rất lớn hoặc chỉ cần tra cứu theo cùng key đã partition, KTable thường tiết kiệm tài nguyên hơn.

## 7. Co-partitioning: điều kiện quan trọng của equi-join

KStream-KStream, KStream-KTable và KTable-KTable equi-join cần dữ liệu được co-partition. Điều này bảo đảm record cùng key từ hai phía được đưa tới cùng stream task.

Hai điều kiện:

1. Các topic đầu vào có cùng số partition.
2. Producer ở hai phía dùng cùng partitioning strategy để cùng key luôn được đưa tới cùng partition number.

Ví dụ:

~~~text
orders:       P0  P1  P2  P3
payments:     P0  P1  P2  P3

orderId 81 -> partition 2 ở cả hai topic
orderId 95 -> partition 0 ở cả hai topic
~~~

Nếu orders có 6 partition nhưng payments có 3 partition, Kafka Streams có thể báo lỗi khi topology được gán partition. Nếu số partition bằng nhau nhưng producer dùng partitioner khác nhau, Kafka Streams không thể tự xác minh rằng cùng key đã đi vào cùng partition.

### 7.1. Key là một phần của hợp đồng dữ liệu

Hãy thống nhất:

- Key type và cách serialize.
- Quy tắc chuẩn hóa key (ví dụ chữ hoa/thường, tiền tố tenant).
- Partition count của các topic join.
- Partitioner hoặc hash strategy.
- Cách thay đổi partition count khi topic đã có dữ liệu.

Nếu producer dùng orderId làm key ở topic orders nhưng paymentId làm key ở topic payments, equi-join theo key sẽ không ghép đúng dù hai payload cùng chứa orderId.

### 7.2. Repartition khi đổi key

Các thao tác như selectKey hoặc map thay đổi key có thể đánh dấu stream cần repartition trước khi thực hiện grouping/join. Kafka Streams có thể tạo internal repartition topic khi topology cần.

Ví dụ:

~~~java
KStream<String, Order> byCustomer =
        orders.selectKey((orderId, order) -> order.customerId());

KStream<String, EnrichedOrder> result =
        byCustomer.join(customers, this::enrich);
~~~

Khi đổi key sang customerId, cần bảo đảm stream được repartition theo key mới trước join. Với topology phức tạp, có thể gọi repartition(Repartitioned...) để kiểm soát số partition, tên và Serde của internal topic.

Nếu chỉ thay đổi value mà giữ nguyên key, ưu tiên mapValues hoặc flatMapValues khi phù hợp. Các thao tác này giữ key và thường tránh repartition không cần thiết.

### 7.3. Ngoại lệ của co-partitioning

Hai trường hợp không cần co-partitioning theo cách equi-join:

- KStream-GlobalKTable: mọi instance có toàn bộ GlobalKTable.
- KTable-KTable foreign-key join: Kafka Streams quản lý việc phối hợp nội bộ.

Không áp dụng ngoại lệ này cho KStream-KTable hoặc KTable-KTable equi-join.

## 8. Cấu hình nhiều input binding trong Spring Cloud Stream

Kafka Streams binder suy ra kiểu binding từ chữ ký hàm. Một function nhận KStream và KTable sẽ có hai input binding; một function nhận KStream và GlobalKTable cũng có hai input binding.

Ví dụ:

~~~java
@Bean
BiFunction<KStream<String, Long>,
        KTable<String, String>,
        KStream<String, RegionWithClicks>> enrichClicks() {
    return (clicks, regions) -> clicks.leftJoin(
            regions,
            (count, region) -> new RegionWithClicks(
                    region == null ? "UNKNOWN" : region,
                    count),
            Joined.with(
                    Serdes.String(),
                    Serdes.Long(),
                    Serdes.String()));
}
~~~

Với function tên enrichClicks, binder mặc định tạo:

- enrichClicks-in-0: KStream đầu vào.
- enrichClicks-in-1: KTable đầu vào.
- enrichClicks-out-0: KStream đầu ra.

Cấu hình destination:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichClicks
    stream:
      bindings:
        enrichClicks-in-0:
          destination: clicks
        enrichClicks-in-1:
          destination: user-regions
        enrichClicks-out-0:
          destination: enriched-clicks
~~~

Binder dựa vào kiểu generic trong chữ ký hàm để tạo KStream hoặc KTable. Nếu input thứ hai khai báo KTable, binder đọc destination như changelog table; nếu khai báo GlobalKTable, binder đọc toàn bộ partition vào global table.

### 8.1. Từ ba input trở lên

Với hai input, có thể dùng BiFunction. Với ba input trở lên, Kafka Streams binder hỗ trợ curried Function:

~~~java
record OrderWithCustomer(Order order, Customer customer) {
    Long productId() {
        return order.productId();
    }
}

record EnrichedOrder(OrderWithCustomer order, Product product) {}

@Bean
Function<KStream<Long, Order>,
        Function<GlobalKTable<Long, Customer>,
                Function<GlobalKTable<Long, Product>,
                        KStream<Long, EnrichedOrder>>>> enrichOrder() {

    return orders -> customers -> products ->
            orders.join(
                    customers,
                    (orderId, order) -> order.customerId(),
                    (order, customer) -> new OrderWithCustomer(order, customer))
            .join(
                    products,
                    (orderId, order) -> order.productId(),
                    (order, product) -> new EnrichedOrder(order, product));
}
~~~

OrderWithCustomer giữ cả Order và Customer sau phép nối đầu tiên, đồng thời cung cấp productId để phép nối tiếp theo tra cứu Product. Đoạn code minh họa cách binder bind nhiều input bằng curried function. Nếu có quá nhiều input, hãy cân nhắc tách topology thành các processor nhỏ để dễ đọc và vận hành.

## 9. Serde và schema của dữ liệu join

Join phải serialize/deserialize key và value đúng kiểu. Serde không khớp có thể gây lỗi deserialization, lỗi state store hoặc output không đọc được.

Các lựa chọn:

- Dùng Serde mặc định của Kafka Streams khi tất cả binding cùng kiểu cơ bản.
- Khai báo Serde theo từng input binding khi mỗi topic có kiểu value khác nhau.
- Cung cấp Serde bean để binder suy ra từ kiểu generic.
- Truyền Serde trực tiếp vào Joined.with, StreamJoined.with hoặc Materialized.

Ví dụ cấu hình Serde cho hai input:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichClicks
    stream:
      bindings:
        enrichClicks-in-0:
          destination: clicks
        enrichClicks-in-1:
          destination: user-regions
        enrichClicks-out-0:
          destination: enriched-clicks
      kafka:
        streams:
          bindings:
            enrichClicks-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            enrichClicks-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Prefix đầy đủ cho các thuộc tính Kafka Streams là spring.cloud.stream.kafka.streams.bindings.<binding-name>.consumer. Trong ví dụ, key của cả hai input là String; value của clicks là Long và value của user-regions là String.

Default Serde ở cấp binder có thể cấu hình bằng:

~~~properties
spring.cloud.stream.kafka.streams.binder.configuration.default.key.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
spring.cloud.stream.kafka.streams.binder.configuration.default.value.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Đây là mặc định toàn ứng dụng. Khi nhiều input có kiểu value khác nhau, ưu tiên Serde theo binding hoặc khai báo Serde rõ trong join để tránh dùng một default không phù hợp.

### 9.1. Schema compatibility

Nếu producer thay đổi schema, Serde của consumer phải hiểu được payload mới và cũ trong giai đoạn triển khai chuyển tiếp. Với Avro/Protobuf/JSON Schema, cần kiểm tra schema registry, compatibility mode, default field và version.

Join thường yêu cầu hai phía có key tương thích. Nếu một topic dùng customerId dạng String còn topic kia dùng Long hoặc có cách chuẩn hóa khác, phép join không tìm được record tương ứng dù giá trị nghiệp vụ biểu diễn cùng một định danh.

## 10. State store và vòng đời dữ liệu join

Join là stateful operation. Kafka Streams giữ state để có thể tìm record đối ứng và duy trì bảng kết quả.

### 10.1. State của KStream-KStream

Stream-stream join lưu record trong window store cho đến khi không còn cần thiết cho cửa sổ join. Window size, grace period và retention ảnh hưởng dung lượng state.

Window quá dài làm tăng storage và restore time. Window quá ngắn bỏ lỡ các record đến trễ nhưng hợp lệ theo nghiệp vụ.

### 10.2. State của KTable-KTable

Hai KTable được materialize thành local state store để giữ snapshot mới nhất. Kết quả join cũng là changelog table và có thể được materialize nếu cần query hoặc dùng cho các bước tiếp theo.

Với incoming KTable binding, binder có thuộc tính materializedAs để đặt tên state store:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichClicks
    stream:
      kafka:
        streams:
          bindings:
            enrichClicks-in-1:
              consumer:
                materializedAs: user-regions-store
~~~

Tên store ổn định giúp quan sát topology và có thể hỗ trợ interactive query khi ứng dụng cấu hình queryable store phù hợp.

### 10.3. State của GlobalKTable

Mỗi instance lưu toàn bộ GlobalKTable. Khi instance mới khởi động, nó phải đọc và khôi phục toàn bộ dữ liệu global table trước khi xử lý stream theo topology. Nếu bảng lớn, thời gian bootstrap có thể làm chậm quá trình scale hoặc phục hồi sau sự cố.

### 10.4. Changelog và phục hồi

Kafka Streams có thể ghi changelog cho state store để khôi phục state sau khi task chuyển instance hoặc ứng dụng restart. Không xóa changelog topic hoặc internal repartition topic tùy tiện. Thay đổi tên store hoặc topology có thể tạo internal topic mới và ảnh hưởng khả năng khôi phục state.

## 11. Tombstone và xử lý xóa

Trong KTable, record có value null là tombstone, biểu thị xóa key. Đây không phải một giá trị nghiệp vụ null thông thường.

Ví dụ:

~~~text
customer-profile:
  (c-10, Customer("Lan"))
  (c-10, Customer("Lan Nguyen"))
  (c-10, null)  -> xóa c-10 khỏi KTable
~~~

KStream-KTable join:

- Nếu table nhận tombstone, state của key bị xóa.
- Tombstone không tự phát một output join.
- Stream event tiếp theo với key đó sẽ không tìm thấy giá trị table.

KTable-KTable join:

- Xóa ở một phía có thể làm thay đổi hoặc xóa kết quả join tương ứng.
- Cần kiểm tra inner/left/outer semantics và tombstone ở cả hai phía.

GlobalKTable cũng diễn giải null value là tombstone. Nếu dimension bị xóa, bản sao global ở mỗi instance sẽ cập nhật theo changelog. Không dùng một object có trường null làm tombstone nếu Serde không serialize thành Kafka record có null value đúng nghĩa.

## 12. Chọn KTable hay GlobalKTable?

| Câu hỏi | KTable | GlobalKTable |
|---|---|---|
| Bảng có lớn không? | Phù hợp bảng lớn được chia partition | Nên nhỏ/vừa vì mỗi instance giữ toàn bộ |
| Join theo cùng key? | Phù hợp equi-join với co-partition | Có thể lookup theo khóa ngoại |
| Cần event-time/versioned lookup? | Có thể dùng versioned KTable và grace nếu version hỗ trợ | Không có temporal semantics |
| Số instance tăng | Mỗi instance giữ phần partition được gán | Mỗi instance đọc và giữ toàn bộ bảng |
| Key skew/hot partition | Có thể chịu ảnh hưởng phân bố key | Có thể tránh một số hot partition khi lookup local |
| Bootstrap | Khôi phục phần state được gán | Phải bootstrap toàn bộ bảng trên mỗi instance |

Không chọn GlobalKTable chỉ để tránh sửa partitioning của topic lớn. Nếu bảng tham chiếu rất lớn, chi phí nhân bản có thể lớn hơn chi phí repartition hoặc duy trì một KTable được co-partition đúng.

## 13. Cách chẩn đoán join không tạo kết quả

Khi topology chạy nhưng output rỗng hoặc thiếu record, kiểm tra theo thứ tự:

1. Kiểu binding: input có thực sự được bind thành KStream, KTable hoặc GlobalKTable như chữ ký hàm không?
2. Destination: binding có đọc đúng topic không? Có record trong topic không?
3. Key: hai phía có cùng key type, giá trị và quy tắc chuẩn hóa không?
4. Partition: equi-join có cùng số partition và cùng partitioning strategy không?
5. Serde: key/value có deserialize đúng không? Có lỗi schema bị log không?
6. Join type: inner join có đang loại bỏ record chưa có match không? Có cần left join?
7. Window: stream-stream record có cùng key và timestamp nằm trong JoinWindows không?
8. Grace: record có đến sau grace period không?
9. Tombstone: KTable key có bị xóa trước khi stream event đến không?
10. Global bootstrap: GlobalKTable đã nạp xong trước khi stream processing bắt đầu chưa?
11. State restore: state store có đang restore hoặc bị lỗi disk/permission không?
12. Topology: repartition topic và internal topic có được tạo đúng không?

Kafka Streams có thể kiểm tra số partition của các input trong một số join và báo lỗi khi không bằng nhau. Nó không thể xác minh producer ở hai topic có dùng cùng partitioning strategy hay không; phần đó thuộc trách nhiệm của thiết kế producer.

## 14. Kiểm thử phép nối

Kafka Streams cung cấp TopologyTestDriver trong artifact kafka-streams-test-utils. Test driver chạy topology đồng bộ mà không cần broker thật, cho phép gửi record vào topic giả lập, đọc output và kiểm tra state store.

### 14.1. Kiểm thử KStream-KTable join

Tạo topology với stream clicks, table regions và output enriched-clicks. Trong test:

1. Gửi record user-17 -> Hanoi vào topic regions để nạp KTable.
2. Gửi record user-17 -> 5 vào topic clicks.
3. Đọc output và xác minh kết quả chứa region Hanoi cùng số click 5.
4. Gửi tombstone cho user-17 vào regions.
5. Gửi click tiếp theo và xác minh left join trả region mặc định/null theo logic ứng dụng.

### 14.2. Kiểm thử KStream-KStream windowed join

Dùng TestInputTopic để gửi hai record cùng key với timestamp cụ thể:

- OrderCreated lúc 10:00.
- PaymentAuthorized lúc 10:03.

Xác minh có output nếu timestamp nằm trong JoinWindows. Sau đó gửi record ngoài cửa sổ và xác minh không có kết quả. Với left/outer join, advance event time qua window và grace để kiểm tra kết quả không khớp được phát đúng thời điểm.

### 14.3. Kiểm thử KTable-KTable join

Gửi lần lượt:

1. Customer c-10.
2. Loyalty c-10 = GOLD.
3. Loyalty c-10 = PLATINUM.
4. Tombstone customer hoặc loyalty.

Xác minh output changelog phản ánh các lần cập nhật và xóa. Không chỉ kiểm tra output đầu tiên; KTable là kết quả liên tục thay đổi.

### 14.4. Kiểm thử GlobalKTable

Gửi dữ liệu vào topic dimension và xác minh GlobalKTable được nạp. Sau đó gửi stream event dùng foreign key để lookup. Kiểm tra:

- Key mapper trả đúng dimension key.
- Không cần co-partition giữa stream và global table.
- Update dimension được phản ánh trên bản sao local.
- Join không được xem là temporal lookup.

### 14.5. Giới hạn của TopologyTestDriver

TopologyTestDriver không thay thế integration test với broker. Nó không kiểm tra đầy đủ:

- Consumer group và partition assignment.
- Rebalance giữa nhiều instance.
- Co-partitioning thực tế của hai topic.
- ACL, network và broker failure.
- State restore từ changelog topic trong cluster.
- Serialization với cấu hình broker/schema registry thật.

Dùng Testcontainers hoặc Kafka test cluster cho các kiểm thử topology deployment, partition count, Serde và phục hồi state.

## 15. Quan sát và vận hành

Theo dõi các chỉ số sau:

| Chỉ số | Ý nghĩa |
|---|---|
| Consumer lag theo input topic/partition | Dữ liệu đầu vào đang tích lũy |
| Join output rate | Tỷ lệ output được tạo từ phép join |
| Join match/miss rate | Bao nhiêu record có hoặc không tìm thấy đối tác |
| Window store size | State đang giữ cho stream-stream join |
| KTable state size | Dung lượng bảng trạng thái local |
| GlobalKTable bootstrap duration | Thời gian nạp toàn bộ bảng trên mỗi instance |
| State restore duration | Thời gian phục hồi state sau restart/rebalance |
| Repartition topic throughput | Chi phí do đổi key hoặc repartition |
| Serde/deserialization errors | Lỗi schema, key hoặc value |
| Late record/drop count | Record đến sau window/grace |
| RocksDB/disk usage | Tài nguyên local state store |

### 15.1. Cảnh báo

Cân nhắc cảnh báo khi:

- Join output rate giảm về 0 trong khi input vẫn có dữ liệu.
- Join miss rate tăng đột biến.
- Consumer lag tăng liên tục.
- GlobalKTable bootstrap kéo dài bất thường.
- State store gần đầy hoặc restore thất bại.
- Late record bị loại bỏ vượt ngưỡng.
- Repartition topic có lưu lượng hoặc lag bất thường.

Join miss không phải lúc nào cũng là lỗi. Inner join có thể bỏ qua record chưa có match; hãy so sánh với kỳ vọng nghiệp vụ và dùng left join/metrics nếu cần quan sát record thiếu đối tác.

## 16. Những lỗi thường gặp

1. **Dùng KStream cho dữ liệu trạng thái**: update cùng key bị xem là sự kiện mới. Hãy dùng KTable khi topic là changelog.
2. **Dùng KTable cho event log**: các update cùng key ghi đè trạng thái trước. Hãy dùng KStream khi cần giữ mọi sự kiện.
3. **Dùng GlobalKTable cho bảng quá lớn**: mỗi instance đọc và lưu toàn bộ bảng. Hãy dùng KTable nếu có thể co-partition.
4. **Nhầm KStream-KTable join là temporal join**: join thông thường tra cứu trạng thái hiện tại khi stream record được xử lý. Hãy dùng versioned KTable khi cần event-time lookup.
5. **Cho rằng table update tự phát lại stream record cũ**: chỉ KStream mới kích hoạt KStream-KTable join. Hãy thiết kế KTable-KTable nếu cả hai phía đều cần cập nhật output.
6. **Thiếu co-partitioning**: cùng key có thể nằm ở task khác nhau. Hãy thống nhất partition count và partitioner.
7. **Chỉ kiểm tra số partition**: Kafka không xác minh partitioning strategy của producer. Hãy kiểm tra producer key/partitioner.
8. **Không đặt window/grace rõ ràng**: record đến muộn bị bỏ hoặc output left/outer xuất hiện không đúng kỳ vọng. Hãy cấu hình cửa sổ theo SLA.
9. **Không xử lý tombstone**: bảng tham chiếu có thể giữ dữ liệu đã bị xóa. Hãy xác định semantics xóa và test null value.
10. **Dùng Serde sai**: key/value không deserialize được hoặc join không tìm thấy key. Hãy khai báo Serde theo binding.
11. **Đổi key mà không repartition**: record cùng key có thể nằm ở task khác nhau. Hãy dùng repartition phù hợp.
12. **Không tính chi phí GlobalKTable**: mỗi instance bootstrap và giữ toàn bộ bảng. Hãy đo storage, network và startup time.
13. **Chỉ test output đầu tiên của KTable join**: bỏ sót các update/tombstone sau đó. Hãy test toàn bộ changelog.
14. **Chỉ dùng TopologyTestDriver để xác nhận deployment**: test driver không kiểm tra group assignment và broker. Hãy thêm integration test.

## 17. Quy trình thiết kế join

Khi xây dựng topology join trong Spring Cloud Stream:

1. Xác định mỗi topic là event log hay changelog trạng thái.
2. Chọn KStream, KTable hoặc GlobalKTable theo semantics.
3. Xác định join key và có cần foreign-key mapper hay không.
4. Với stream-stream join, đặt JoinWindows và grace period rõ ràng.
5. Với equi-join, xác minh số partition và partitioning strategy của các topic.
6. Repartition nếu key thay đổi hoặc input chưa co-partition.
7. Cấu hình input binding và Serde theo đúng generic type.
8. Đặt tên materialized state store nếu cần query/quan sát.
9. Xác định semantics inner, left hoặc outer và xử lý null/tombstone.
10. Kiểm thử update, delete, record đến muộn, duplicate và dữ liệu thiếu match.
11. Integration test trên Kafka thật cho partition, Serde và state restore.
12. Theo dõi lag, join miss, state size, bootstrap và late records sau triển khai.

## Kết luận

KStream biểu diễn sự kiện; KTable biểu diễn trạng thái mới nhất theo key; GlobalKTable là bản sao đầy đủ của changelog trên mỗi Kafka Streams instance. KStream-KStream join ghép sự kiện theo key và cửa sổ thời gian. KStream-KTable join tra cứu trạng thái khi sự kiện đến. KTable-KTable join tạo bảng kết quả liên tục được cập nhật. KStream-GlobalKTable join cho phép tra cứu theo khóa ngoại mà không cần co-partition, đổi lại mỗi instance phải nạp và lưu toàn bộ bảng.

Trong Spring Cloud Stream Kafka Streams binder, chữ ký Function/BiFunction xác định kiểu input binding và binder tạo KStream, KTable hoặc GlobalKTable tương ứng. Độ chính xác của join phụ thuộc key, partitioning, Serde, window/grace và state store. Hãy kiểm thử cả trường hợp khớp, không khớp, update, tombstone và record đến muộn; đồng thời kiểm tra co-partition và chi phí GlobalKTable trên broker thật.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream — Kafka Streams Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream — State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html)
- [Apache Kafka — Streams DSL and Joins](https://kafka.apache.org/44/streams/developer-guide/dsl-api/)
- [Apache Kafka — Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/)
