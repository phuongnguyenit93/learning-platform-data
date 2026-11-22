# Chọn concurrency theo tốc độ xử lý

Khi một ứng dụng Spring Kafka cần tiêu thụ nhiều sự kiện hơn, tăng số consumer chạy song song có thể giúp nâng throughput. Spring Kafka cung cấp thuộc tính `concurrency` cho listener container để tạo nhiều consumer trong cùng một consumer group. Tuy nhiên, tăng concurrency chỉ có tác dụng khi topic có đủ partition và hệ thống phía sau còn khả năng xử lý thêm tải.

Chọn concurrency phù hợp cần dựa trên tốc độ xử lý đo được, số partition, độ trễ cho phép và năng lực của các dịch vụ phụ thuộc. Cấu hình quá thấp khiến partition không được khai thác hết; cấu hình quá cao tạo thêm consumer và luồng xử lý nhưng không tăng số partition có thể được tiêu thụ song song.

## 1. `concurrency` hoạt động như thế nào trong Spring Kafka?

Một `KafkaMessageListenerContainer` thông thường quản lý một Kafka consumer. Khi cấu hình concurrency lớn hơn một, `ConcurrentMessageListenerContainer` của Spring Kafka quản lý nhiều container con; mỗi container con có consumer và luồng thực thi riêng. Các consumer này tham gia consumer group của listener và nhận partition theo cơ chế assignment của Kafka.

Ví dụ, cấu hình concurrency bằng 3 tạo tối đa ba consumer cho listener container trên mỗi instance ứng dụng:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, Order> orderListenerFactory(
            ConsumerFactory<String, Order> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, Order> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Listener dùng factory trên:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerFactory")
public void handleOrder(Order order) {
    orderService.process(order);
}
```

Nếu dùng factory mặc định do Spring Boot tự cấu hình, có thể đặt concurrency mặc định bằng thuộc tính:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
    listener:
      concurrency: 3
```

Khi tự tạo factory như ví dụ Java, đặt `factory.setConcurrency(...)` ngay trên factory đó. `concurrency` là số consumer của một listener container trên một instance ứng dụng; nếu chạy nhiều instance, tổng số consumer trong group còn phụ thuộc số instance và concurrency của từng instance.

Spring Kafka tạo consumer riêng cho từng container con. Không dùng chung một đối tượng `KafkaConsumer` cho nhiều thread vì Kafka consumer không thread-safe. Tuy nhiên, các container con có thể gọi cùng một phương thức listener trên cùng bean Spring; nếu bean giữ trạng thái mutable, cần thiết kế thread-safe hoặc chuyển trạng thái riêng cho từng lần xử lý.

## 2. Số partition giới hạn mức song song

Trong một consumer group, tại một thời điểm, mỗi partition được gán cho tối đa một consumer. Vì vậy, với một subscription có tổng cộng `P` partition, số consumer thực sự nhận dữ liệu đồng thời không thể vượt quá `P`:

\[
C_{active} \leq \min(C_{total}, P)
\]

Trong đó:

- `C_total` là tổng số consumer thuộc group và đăng ký nhận subscription đó, tính trên tất cả instance và listener container dùng cùng group.
- `P` là tổng số partition của các topic mà group đăng ký nhận.
- `C_active` là số consumer được gán ít nhất một partition.

Ví dụ, topic `orders` có 6 partition:

| Tổng consumer trong group | Consumer có thể nhận partition | Kết quả |
|---:|---:|---|
| 2 | 2 | Mỗi consumer có thể nhận nhiều partition. |
| 4 | 4 | Cả bốn consumer đều có thể hoạt động. |
| 6 | 6 | Có thể khai thác song song trên cả sáu partition. |
| 8 | Tối đa 6 | Ít nhất hai consumer không được gán partition và không tăng throughput. |

Giới hạn trên áp dụng cho tổng consumer của group, không chỉ một tiến trình. Chẳng hạn, ba instance ứng dụng, mỗi instance đặt concurrency bằng 2, tạo tổng cộng tối đa 6 consumer trong group. Nếu group có 4 partition, chỉ tối đa 4 consumer có thể nhận dữ liệu tại một thời điểm.

Nếu listener subscribe nhiều topic, cần tính tổng số partition của subscription. Nếu các listener khác nhau dùng cùng `group.id` và cùng subscription, consumer của chúng cũng tham gia việc phân phối partition trong group đó. Vì vậy, khi tính toán phải xét toàn bộ thành viên của group, không chỉ một annotation `@KafkaListener`.

Kafka bảo đảm thứ tự trong phạm vi một partition. Các record có cùng key thường được định tuyến tới cùng partition, nhờ đó có thể giữ thứ tự xử lý theo key khi listener xử lý tuần tự. Tăng số partition có thể làm thay đổi cách key được ánh xạ tới partition cho các record mới; nếu nghiệp vụ phụ thuộc chặt vào thứ tự theo key, hãy đánh giá tác động này trước khi mở rộng partition.

## 3. Ước lượng concurrency từ tốc độ xử lý

Hãy đo năng lực xử lý bền vững của một consumer bằng dữ liệu gần với môi trường thật. Nếu một consumer xử lý tuần tự trung bình một record trong `T_record` giây, năng lực lý thuyết gần đúng là:

\[
R_{consumer} \approx \frac{1}{T_{record}}
\]

Với mục tiêu throughput `R_target`, số consumer ước lượng ban đầu là:

\[
C_{required} = \left\lceil \frac{R_{target}}{R_{consumer}} \right\rceil
\]

Đây là ước lượng để bắt đầu thử tải. Năng lực thực tế còn phụ thuộc thời gian poll, batch, phân phối record giữa các partition, commit offset, CPU, bộ nhớ và các dịch vụ downstream.

**Ví dụ:** một listener xử lý tuần tự mỗi đơn hàng trong khoảng 20 ms. Một consumer có năng lực gần đúng 50 record/giây. Nếu hệ thống cần xử lý 200 record/giây, ước lượng ban đầu là:

\[
C_{required} = \left\lceil \frac{200}{50} \right\rceil = 4
\]

Nếu topic có ít nhất 4 partition và cơ sở dữ liệu có thể phục vụ 4 luồng xử lý đồng thời, có thể bắt đầu thử nghiệm với concurrency bằng 4. Nếu topic chỉ có 2 partition, tăng concurrency lên 4 không tạo ra 4 consumer hoạt động; cần xem xét số partition và yêu cầu thứ tự trước khi thay đổi cấu trúc topic.

Với xử lý batch, không nên lấy thời gian xử lý một record rồi áp dụng trực tiếp công thức trên mà bỏ qua kích thước batch. Hãy đo số record hoàn thành mỗi giây trên một consumer trong điều kiện batch và commit tương tự môi trường chạy thật. Dùng p95/p99 của thời gian xử lý để đánh giá độ ổn định, bởi giá trị trung bình có thể che khuất những batch kéo dài.

## 4. Những yếu tố làm giới hạn khả năng scale

Số partition chỉ là giới hạn song song ở phía Kafka. Concurrency có thể tăng mà throughput vẫn đứng yên nếu một thành phần khác đã bão hòa.

**Tài nguyên ứng dụng.** Mỗi consumer cần thread và tài nguyên xử lý. Tăng số consumer có thể làm tăng mức sử dụng CPU, heap, số kết nối và hoạt động GC. Nếu công việc chủ yếu dùng CPU, số luồng xử lý quá lớn có thể gây tranh chấp CPU thay vì tăng năng lực.

**Cơ sở dữ liệu và dịch vụ phụ thuộc.** Nếu mỗi record gọi cơ sở dữ liệu, số kết nối trong connection pool và khả năng ghi của database có thể là giới hạn thực tế. Concurrency cao hơn giới hạn của pool có thể làm nhiều luồng chờ kết nối, kéo dài thời gian xử lý và tăng consumer lag. Dịch vụ HTTP, giới hạn rate limit hoặc một hệ thống ghi dùng chung cũng có thể tạo nút thắt tương tự.

**Phân phối partition và tải theo key.** Sáu partition không đảm bảo sáu luồng luôn có lượng việc bằng nhau. Một key có tần suất cao có thể tạo partition nóng trong khi partition khác ít dữ liệu. Consumer nhận partition nóng vẫn có lag cao dù các consumer khác gần như rảnh. Khi đó cần xem lại cách chọn key, phân phối dữ liệu và logic xử lý theo key.

**Thời gian xử lý và poll.** Mỗi consumer phải tiếp tục gọi `poll()` theo giới hạn `max.poll.interval.ms`. Tăng concurrency không làm một batch riêng lẻ xử lý nhanh hơn. Nếu listener xử lý batch quá lâu, consumer đó vẫn có thể vượt khoảng poll và khiến group rebalance. Hãy đo thời gian xử lý của từng consumer và cấu hình batch phù hợp.

**Chi phí rebalance.** Thêm hoặc bớt instance, thay đổi concurrency hay mất kết nối consumer có thể làm group rebalance. Trong lúc phân phối lại partition, quá trình tiêu thụ có thể bị gián đoạn hoặc giảm tốc độ tạm thời. Tránh thay đổi concurrency liên tục khi tải dao động nhẹ; hãy dùng số liệu đủ ổn định để quyết định.

## 5. Quy trình chọn và điều chỉnh concurrency

1. **Đo baseline.** Chạy với concurrency ban đầu và ghi nhận records consumed rate, consumer lag, thời gian xử lý p95/p99, CPU, heap, GC, connection pool và lỗi downstream. Dùng lưu lượng và kích thước message đại diện cho thực tế.
2. **Tính số partition và consumer toàn group.** Xác định tổng partition được subscription sử dụng, số instance ứng dụng, số listener container và concurrency hiện tại. Không tính riêng một tiến trình nếu group có nhiều instance.
3. **Ước lượng concurrency cần thiết.** Dựa vào throughput mục tiêu và năng lực bền vững đã đo trên một consumer. Xem kết quả là điểm bắt đầu, đồng thời kiểm tra giới hạn partition và tài nguyên downstream.
4. **Tăng từng bước.** Thử lần lượt các mức như 1, 2, 4 rồi đo lại sau khi group ổn định. Chỉ tăng tiếp nếu throughput cải thiện và độ trễ, lỗi, CPU, bộ nhớ cùng các dịch vụ phụ thuộc vẫn trong giới hạn.
5. **Tìm điểm bão hòa.** Nếu tăng consumer nhưng throughput không tăng, hãy kiểm tra partition nóng, CPU, database, connection pool, broker và thời gian xử lý. Tăng concurrency thêm khi một nút thắt đã bão hòa thường chỉ làm tăng hàng đợi và tranh chấp tài nguyên.
6. **Mở rộng partition khi cần thiết.** Nếu mọi partition đều đã có consumer hoạt động và lag vẫn tăng, có thể cần tăng partition hoặc tối ưu tốc độ xử lý mỗi partition. Trước khi tăng, đánh giá thứ tự theo key, cách phân phối key, dung lượng broker và khả năng vận hành lâu dài.
7. **Kiểm tra sau triển khai.** Quan sát group rebalance, partition assignment, consumer lag và throughput sau khi thay đổi. Đảm bảo hệ thống vẫn hoạt động ổn định khi có instance khởi động lại hoặc một consumer tạm thời rời group.

## 6. Đọc dấu hiệu vận hành để quyết định scale

| Quan sát | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Consumer lag tăng, một số partition chưa có consumer riêng và tài nguyên còn dư | Group có ít consumer hoạt động hơn số partition | Tăng concurrency hoặc số instance theo từng bước. |
| Consumer lag tăng, mọi partition đã được gán và CPU ứng dụng còn dư | Năng lực xử lý mỗi partition hoặc downstream có thể là giới hạn | Kiểm tra thời gian listener, partition nóng và dịch vụ phụ thuộc trước khi tăng partition. |
| Throughput không tăng khi concurrency tăng, CPU gần bão hòa | Ứng dụng bị giới hạn CPU hoặc có tranh chấp thread | Tối ưu xử lý CPU, đo số thread hữu ích và thử mức concurrency thấp hơn. |
| Throughput không tăng, thời gian chờ database hoặc connection pool tăng | Database hoặc pool kết nối là nút thắt | Kiểm tra truy vấn, batch ghi và giới hạn kết nối trước khi tăng consumer. |
| Một partition lag cao trong khi các partition khác ít lag | Phân phối key không đều hoặc có partition nóng | Kiểm tra key, kích thước công việc và khả năng xử lý riêng của partition đó. |
| Rebalance thường xuyên, xử lý bị gián đoạn | Consumer khởi động/dừng liên tục, poll quá hạn hoặc hạ tầng không ổn định | Kiểm tra log container, thời gian xử lý, `max.poll.interval.ms` và lịch triển khai. |

Các chỉ số nên được xem cùng nhau. Consumer lag tăng không tự động có nghĩa là cần thêm consumer; nếu database đã quá tải, tăng concurrency có thể khiến lag và thời gian xử lý cùng tăng. Ngược lại, CPU còn thấp nhưng một số partition chưa được khai thác có thể cho thấy group chưa có đủ consumer hoạt động.

## 7. Nguyên tắc cần ghi nhớ

- `concurrency` điều khiển số consumer do một listener container quản lý trên mỗi instance; tổng consumer của group còn phụ thuộc số instance và các container khác cùng group.
- Một partition chỉ được gán cho tối đa một consumer trong cùng group tại một thời điểm. Consumer vượt quá số partition không làm tăng mức song song của subscription.
- Muốn tăng throughput bền vững, cần đồng thời có đủ partition, đủ năng lực xử lý ở listener và đủ tài nguyên cho các dịch vụ phía sau.
- Giữ thứ tự trong partition bằng cách thiết kế key phù hợp; scale partition có thể ảnh hưởng cách phân phối key cho record mới.
- Chọn concurrency bằng số liệu throughput và độ trễ đo được, sau đó tăng từng bước và kiểm tra điểm bão hòa.

Concurrency phù hợp là mức thấp nhất đáp ứng throughput mục tiêu với consumer lag, độ trễ và tài nguyên trong giới hạn vận hành. Khi đã dùng hết khả năng song song của partition, bước tiếp theo phải dựa vào nút thắt đo được và yêu cầu thứ tự của nghiệp vụ, thay vì chỉ tiếp tục tăng số thread.
