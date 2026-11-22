# Retention và thời gian lưu trữ

Kafka được thiết kế để lưu các bản ghi trong một khoảng thời gian hoặc cho đến khi đạt giới hạn dung lượng đã cấu hình. Cơ chế quyết định dữ liệu cũ được giữ lại hay loại bỏ được gọi là **retention**. Đây là một phần quan trọng của mô hình Kafka: nó ảnh hưởng đến lượng dữ liệu consumer có thể đọc lại, thời gian một consumer được phép chậm, dung lượng đĩa cần chuẩn bị và cách thiết kế topic.

Trong ứng dụng Spring Kafka, producer gửi bản ghi bằng `KafkaTemplate` và consumer nhận bản ghi bằng `@KafkaListener`. Hai thành phần này không quyết định vòng đời lưu trữ của topic. Retention được quản lý ở phía Kafka broker thông qua cấu hình broker và cấu hình từng topic. Spring Kafka có thể khai báo cấu hình topic khi tạo topic, nhưng việc lưu giữ và xóa segment vẫn do Kafka thực hiện.

## 1. Retention là gì?

Kafka ghi bản ghi vào log của từng partition. Log được chia thành các **segment**; khi segment hiện tại đạt ngưỡng kích thước hoặc thời gian, broker đóng segment đó và bắt đầu segment mới. Các segment cũ có thể được dọn theo chính sách cleanup của topic.

Retention xác định dữ liệu trong log được giữ trong bao lâu hoặc tối đa đến dung lượng nào. Với topic dùng chính sách `delete`, Kafka có thể xóa các segment cũ khi chúng vượt giới hạn thời gian hoặc dung lượng. Với topic dùng `compact`, Kafka dọn các phiên bản cũ của cùng một key để giữ lại trạng thái mới nhất theo key.

Retention không có nghĩa là Kafka xóa bản ghi ngay khi consumer đọc xong. Nhiều consumer group có thể đọc cùng một bản ghi ở những thời điểm khác nhau; dữ liệu vẫn được giữ theo chính sách topic cho đến khi đủ điều kiện cleanup. Việc một consumer group đã commit offset cũng không làm bản ghi lập tức biến mất.

Ví dụ, topic `orders.events` được cấu hình lưu dữ liệu trong bảy ngày. Dịch vụ phân tích có thể tạm dừng hai ngày rồi đọc tiếp nếu các bản ghi cần thiết vẫn còn trong retention. Nếu dịch vụ ngừng hoạt động lâu hơn thời hạn lưu trữ và dữ liệu cũ đã bị xóa, consumer không thể khôi phục những bản ghi đó chỉ bằng cách reset offset.

## 2. Hai giới hạn chính: thời gian và dung lượng

### Lưu theo thời gian với `retention.ms`

`retention.ms` đặt thời gian lưu tối đa cho topic dùng `cleanup.policy=delete`, tính bằng mili giây. Khi không khai báo ở cấp topic, Kafka sử dụng giá trị mặc định của broker, thường được cấu hình qua `log.retention.ms` hoặc các thuộc tính tương đương theo đơn vị phút/giờ.

Ví dụ, bảy ngày được biểu diễn như sau:

```text
7 ngày = 7 x 24 x 60 x 60 x 1000
       = 604800000 ms
```

Một số giá trị thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| `retention.ms=86400000` | Giới hạn thời gian một ngày |
| `retention.ms=604800000` | Giới hạn thời gian bảy ngày |
| `retention.ms=2592000000` | Giới hạn thời gian xấp xỉ 30 ngày |
| `retention.ms=-1` | Không giới hạn thời gian bằng thuộc tính này |

`retention.ms=-1` không có nghĩa dữ liệu được bảo vệ vĩnh viễn trước mọi nguyên nhân mất dữ liệu. Nó chỉ tắt giới hạn retention theo thời gian; giới hạn dung lượng, chính sách compact, thao tác quản trị, lỗi hạ tầng và các cơ chế khác vẫn có thể tác động đến dữ liệu.

### Lưu theo dung lượng với `retention.bytes`

`retention.bytes` đặt giới hạn dung lượng log được giữ cho **mỗi partition**, không phải tổng dung lượng của toàn topic. Khi partition vượt ngưỡng, Kafka có thể xóa các segment cũ để đưa dung lượng về dưới giới hạn.

Ví dụ, topic có sáu partition và đặt `retention.bytes=10737418240` (10 GiB) thì giới hạn logic xấp xỉ là 60 GiB cho toàn topic. Nếu replication factor là ba, dung lượng vật lý trên các broker có thể xấp xỉ ba lần dung lượng logic, chưa tính overhead, index, chênh lệch phân bố và phần dung lượng tạm thời do cleanup theo segment.

Giá trị `retention.bytes=-1` nghĩa là không đặt giới hạn dung lượng bằng thuộc tính này. Khi không giới hạn theo dung lượng, vẫn cần kiểm soát thời gian lưu hoặc dung lượng đĩa bằng các biện pháp vận hành khác.

Nếu cấu hình cả `retention.ms` và `retention.bytes` cho topic dùng `delete`, cả hai giới hạn đều có hiệu lực. Dữ liệu cũ có thể bị dọn khi chạm giới hạn thời gian hoặc khi partition cần giải phóng dung lượng. Do đó, retention thực tế có thể ngắn hơn kỳ vọng nếu giới hạn dung lượng quá thấp so với tốc độ phát sinh dữ liệu.

## 3. Kafka xóa dữ liệu theo segment

Kafka không thường xuyên mở từng bản ghi để xóa riêng lẻ khi hết hạn. Dữ liệu được quản lý theo segment. Hai cấu hình ảnh hưởng đến việc chia segment là:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `segment.bytes` | Kích thước tối đa của một segment trước khi log roll sang segment mới |
| `segment.ms` | Thời gian tối đa trước khi segment hiện tại được roll, kể cả khi chưa đạt giới hạn kích thước |
| `log.retention.check.interval.ms` | Khoảng thời gian broker kiểm tra các segment đủ điều kiện bị xóa |

Vì cleanup diễn ra theo segment và theo chu kỳ kiểm tra, bản ghi không nhất thiết biến mất đúng tại mili giây `retention.ms` chạm ngưỡng. Segment có thể còn được giữ thêm một khoảng thời gian cho đến khi segment được roll và lần kiểm tra cleanup tiếp theo diễn ra. Ở topic ít dữ liệu, `segment.ms` có thể ảnh hưởng rõ đến thời điểm segment được đóng.

Điều này cũng giải thích vì sao không nên dùng retention như một bộ hẹn giờ chính xác cho từng bản ghi. Nếu nghiệp vụ cần xóa một bản ghi theo thời điểm chính xác, cần thiết kế thêm cơ chế lưu trữ hoặc xóa ở tầng ứng dụng phù hợp với yêu cầu đó.

## 4. `cleanup.policy`: delete và compact

Retention thời gian/dung lượng thường được hiểu cùng với `cleanup.policy`. Topic có thể dùng `delete`, `compact`, hoặc kết hợp cả hai.

### Chính sách `delete`

Với `cleanup.policy=delete`, Kafka xóa các segment cũ theo giới hạn retention. Đây là lựa chọn phổ biến cho event log, log ứng dụng, dữ liệu đo lường hoặc sự kiện cần lưu trong một khoảng thời gian hữu hạn.

Ví dụ, topic `orders.events` có thể lưu toàn bộ sự kiện đơn hàng trong bảy ngày để dịch vụ phân tích hoặc hệ thống hỗ trợ có thời gian đọc lại dữ liệu khi gặp sự cố.

### Chính sách `compact`

Với `cleanup.policy=compact`, Kafka thực hiện log compaction theo key. Trong một partition, nhiều bản ghi có cùng key có thể được ghi theo thời gian; compaction giữ lại giá trị mới nhất của key và dọn các phiên bản cũ sau khi đủ điều kiện. Đây là cách phù hợp để duy trì changelog hoặc topic biểu diễn trạng thái mới nhất, ví dụ `customer-state` với key là `customerId`.

Compaction không biến topic thành một bảng chỉ có một bản ghi cho mỗi key ngay lập tức. Các bản ghi cũ có thể vẫn còn trong log trước khi cleaner xử lý; consumer đọc từ đầu có thể nhìn thấy nhiều phiên bản của một key. Consumer cần hiểu rằng dữ liệu compact là luồng thay đổi trạng thái và phải áp dụng các bản ghi theo thứ tự trong partition.

Để xóa một key khỏi trạng thái được compact, producer gửi một **tombstone**: bản ghi có key cần xóa và value là `null`. Tombstone được giữ trong khoảng thời gian `delete.retention.ms` để consumer có cơ hội nhìn thấy chỉ thị xóa trước khi tombstone bị dọn. Giá trị mặc định thường là 24 giờ. Nếu consumer đọc lại quá chậm và tombstone đã bị xóa, nó có thể không nhận ra rằng key đó từng bị xóa.

### Kết hợp `compact,delete`

`cleanup.policy=compact,delete` cho phép Kafka vừa compact dữ liệu theo key, vừa xóa các segment cũ theo giới hạn retention. Cách kết hợp này hữu ích khi topic cần giữ trạng thái mới nhất theo key nhưng vẫn giới hạn tuổi của dữ liệu.

Không nên mặc định dùng `compact` cho mọi topic. Nếu yêu cầu là giữ toàn bộ lịch sử sự kiện trong một khoảng thời gian, `delete` thường phù hợp hơn. Nếu yêu cầu là khôi phục trạng thái mới nhất theo key, `compact` có thể phù hợp hơn. Việc chọn chính sách cần dựa trên cách consumer sử dụng dữ liệu.

## 5. Cấu hình retention ở broker và topic

Kafka có cấu hình mặc định ở broker. Ví dụ, `log.retention.hours` thường có giá trị mặc định bảy ngày và được dùng khi topic không ghi đè chính sách tương ứng. Một topic có thể đặt `retention.ms` hoặc `retention.bytes` riêng để có thời hạn lưu trữ khác với mặc định chung.

Nên dùng cấu hình cấp topic khi các loại dữ liệu có yêu cầu lưu giữ khác nhau. Ví dụ, sự kiện kỹ thuật có thể chỉ cần giữ ba ngày, trong khi sự kiện nghiệp vụ cần giữ 30 ngày để hỗ trợ đối soát. Không nên tăng retention toàn broker chỉ để đáp ứng một topic riêng lẻ nếu việc đó làm dung lượng các topic khác tăng ngoài dự kiến.

Ví dụ cấu hình topic qua Spring Kafka:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("orders.events")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_DELETE)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .config(TopicConfig.RETENTION_BYTES_CONFIG, "10737418240")
                .build();
    }
}
```

Khi ứng dụng Spring Boot khởi động, `KafkaAdmin` có thể sử dụng bean `NewTopic` để tạo topic nếu topic chưa tồn tại. Ví dụ trên đặt sáu partition, replication factor ba, retention bảy ngày và giới hạn 10 GiB cho mỗi partition. Cluster phải có đủ broker để đáp ứng replication factor đã khai báo.

Bean `NewTopic` chủ yếu mô tả topic cần tạo. Nếu topic đã tồn tại, việc thay đổi các giá trị trong mã không nên được xem là bằng chứng rằng cấu hình hiện tại trên broker đã được cập nhật. Với topic đang chạy, cần dùng Kafka Admin API hoặc công cụ quản trị Kafka để thay đổi cấu hình và xác minh kết quả thực tế.

Các thuộc tính kết nối như `spring.kafka.bootstrap-servers` có thể nằm trong `application.yml`, nhưng retention là cấu hình của topic/broker, không phải thuộc tính điều khiển thời gian lưu của một lệnh `KafkaTemplate.send` hay một phương thức `@KafkaListener`.

## 6. Retention ảnh hưởng thế nào đến consumer?

Consumer group lưu offset để ghi nhận vị trí đọc của từng partition. Offset cho biết consumer đã tiến đến đâu; nó không giữ bản ghi tồn tại lâu hơn retention của topic.

Giả sử consumer group `billing-service` ngừng hoạt động trong mười ngày, trong khi topic chỉ giữ dữ liệu bảy ngày. Khi consumer hoạt động lại, một phần dữ liệu mà group chưa đọc có thể đã bị xóa. Consumer có thể gặp tình huống offset nằm ngoài phạm vi log hiện tại (`OffsetOutOfRange`). Cách xử lý tiếp theo phụ thuộc cấu hình và error handling, nhưng dữ liệu đã bị retention xóa không thể được Kafka trả lại chỉ bằng cách đặt offset về đầu.

`auto.offset.reset` thường bị hiểu nhầm trong tình huống này:

- `earliest`: khi không có offset hợp lệ, bắt đầu từ bản ghi sớm nhất hiện còn trong partition.
- `latest`: khi không có offset hợp lệ, bắt đầu từ cuối log và chỉ nhận dữ liệu mới.
- `none`: phát sinh lỗi nếu không tìm thấy offset hợp lệ.

`earliest` không khôi phục dữ liệu đã bị xóa. Nó chỉ đưa consumer về đầu phần dữ liệu còn được lưu. Vì vậy, retention cần được chọn dựa trên thời gian gián đoạn tối đa mà consumer có thể chịu được, cộng thêm thời gian xử lý backlog sau khi khôi phục.

Retention của topic cũng khác với thời gian Kafka lưu offset của consumer group. Offset được lưu trong topic nội bộ `__consumer_offsets` và có chính sách hết hạn riêng ở broker. Xóa offset của một group không đồng nghĩa xóa event trong topic; ngược lại, event bị xóa do retention cũng không có nghĩa offset của group lập tức bị xóa.

## 7. Ước lượng dung lượng và chọn thời hạn lưu

Một cách ước lượng ban đầu là lấy tốc độ dữ liệu trung bình nhân với thời gian cần lưu:

```text
Dung lượng logic xấp xỉ = tốc độ ghi mỗi giây x số giây retention
Dung lượng vật lý xấp xỉ = dung lượng logic x replication factor
```

Ví dụ, một topic nhận trung bình 2 MiB/s và cần lưu bảy ngày:

```text
2 MiB/s x 604800 s = 1,209,600 MiB
                   ≈ 1,181 GiB
                   ≈ 1.15 TiB dung lượng logic
```

Nếu replication factor là ba, dung lượng lưu trên toàn cluster có thể vào khoảng 3.45 TiB trước khi tính overhead và dự phòng. Đây là ước lượng sơ bộ; khi lập kế hoạch thực tế cần tính đến peak throughput, kích thước record, compression, phân bố partition, tốc độ tăng trưởng, segment/index và dung lượng trống cần thiết để broker hoạt động an toàn.

Khi chọn retention, hãy trả lời các câu hỏi sau:

1. Consumer có thể ngừng hoạt động tối đa bao lâu?
2. Sau khi hoạt động lại, cần bao lâu để xử lý hết backlog?
3. Có yêu cầu nghiệp vụ, kiểm toán hoặc đối soát về thời gian lưu dữ liệu không?
4. Tốc độ ghi trung bình và cao điểm của topic là bao nhiêu?
5. Topic có bao nhiêu partition và replication factor là bao nhiêu?
6. Có cần lưu toàn bộ lịch sử hay chỉ cần trạng thái mới nhất theo key?

Nếu retention quá ngắn, consumer chậm có thể mất cơ hội đọc dữ liệu. Nếu retention quá dài, chi phí đĩa và thời gian phục hồi có thể tăng. Giới hạn dung lượng cũng cần đủ lớn để không xóa dữ liệu sớm hơn thời hạn nghiệp vụ mong muốn.

## 8. Giám sát và kiểm thử retention

Trong môi trường vận hành, cần theo dõi dung lượng log trên broker, dung lượng từng partition, mức sử dụng đĩa, tốc độ ghi và consumer lag. Consumer lag tăng liên tục có thể là dấu hiệu tốc độ xử lý không theo kịp tốc độ ghi; nếu lag tiến gần thời hạn retention, cần xử lý trước khi dữ liệu chưa đọc bị dọn.

Khi điều tra một topic, nên kiểm tra cấu hình thực tế trên broker thay vì chỉ đọc file cấu hình trong ứng dụng. Các giá trị cần xem gồm `cleanup.policy`, `retention.ms`, `retention.bytes`, `segment.ms`, `segment.bytes` và cấu hình broker liên quan đến retention. Cấu hình topic đang tồn tại có thể khác với giá trị mà một bản triển khai ứng dụng mới khai báo.

Kiểm thử tích hợp có thể dùng Kafka Testcontainers hoặc broker kiểm thử để xác minh topic được tạo với đúng cấu hình. Có thể dùng AdminClient để đọc cấu hình topic và so sánh với giá trị mong đợi. Kiểm thử việc xóa segment do retention cần tính đến thời gian roll segment và chu kỳ cleanup; không nên giả định bản ghi sẽ bị xóa chính xác tại thời điểm `retention.ms` hết hạn.

Đối với topic compact, cần kiểm thử riêng hành vi cập nhật cùng key và tombstone. Consumer khôi phục trạng thái cần đọc được các bản ghi cần thiết và hiểu rằng compaction có thể loại bỏ các phiên bản trung gian.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Consumer đọc xong thì Kafka xóa bản ghi | Bản ghi được giữ theo cleanup policy và retention của topic |
| `retention.bytes` là giới hạn toàn topic | Đây là giới hạn theo từng partition |
| `retention.ms` xóa từng record đúng thời điểm hết hạn | Kafka dọn theo segment và chu kỳ cleanup |
| `auto.offset.reset=earliest` khôi phục mọi dữ liệu cũ | Nó chỉ đọc từ dữ liệu sớm nhất còn tồn tại |
| Topic compact giữ toàn bộ lịch sử | Compaction giữ trạng thái mới nhất theo key sau khi cleaner xử lý |
| Tăng retention của topic sẽ kéo dài thời gian lưu offset consumer group | Event và offset group có chính sách lưu trữ riêng |

## 10. Kết luận

Retention quyết định Kafka giữ dữ liệu trong bao lâu hoặc đến giới hạn dung lượng nào. Với `cleanup.policy=delete`, hai cấu hình quan trọng là `retention.ms` và `retention.bytes`; với `compact`, Kafka dọn các phiên bản cũ theo key và sử dụng tombstone để biểu diễn việc xóa key.

Kafka thực hiện cleanup theo segment, vì vậy thời điểm dữ liệu thực sự bị dọn có thể trễ hơn mốc cấu hình. Retention cũng đặt giới hạn thời gian mà consumer có thể chậm trước khi dữ liệu chưa đọc bị loại bỏ. Khi xây dựng ứng dụng Spring Kafka, cần cấu hình retention ở broker hoặc topic, khai báo topic phù hợp qua `NewTopic` khi cần, xác minh cấu hình trên broker và giám sát consumer lag cùng dung lượng lưu trữ.
