# Cấu hình concurrency và giới hạn theo số partition

Kafka có thể xử lý nhiều message song song bằng cách chia topic thành các partition và phân phối partition cho các consumer trong cùng một consumer group. Spring Cloud Stream cho phép cấu hình concurrency cho input binding để tạo nhiều consumer đồng thời trong mỗi instance ứng dụng. Tuy nhiên, số consumer thực sự có thể nhận dữ liệu trong một group bị giới hạn bởi số partition được subscribe.

Đây là giới hạn quan trọng khi scale ứng dụng. Tăng số replica hoặc tăng concurrency không tự động làm throughput tăng nếu topic không có đủ partition. Các consumer vượt quá số partition sẽ không được gán partition và ở trạng thái rảnh. Ngược lại, nếu số partition lớn hơn số consumer, mỗi consumer có thể nhận nhiều partition.

Bài học này giải thích quan hệ giữa partition, consumer group, concurrency và số instance; cách cấu hình concurrency trong Spring Cloud Stream Kafka binder; cách phân biệt concurrency với max.poll.records và max.poll.interval.ms; tác động đến thứ tự, rebalance, throughput và vận hành; cùng các cách kiểm thử để chọn cấu hình phù hợp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao số consumer hoạt động trong một group không thể vượt số partition được gán.
- Tính tổng số consumer dựa trên concurrency và số instance ứng dụng.
- Cấu hình consumer.concurrency cho input binding của Spring Cloud Stream.
- Phân biệt concurrency với max.poll.records và max.poll.interval.ms.
- Dự đoán consumer nào hoạt động hoặc rảnh khi thay đổi số partition và replica.
- Hiểu consumer group rebalance khi instance tham gia, rời đi hoặc mất kết nối.
- Giữ thứ tự xử lý theo key và nhận biết giới hạn của xử lý song song.
- Đo lag, độ lệch tải và hiệu quả scale để điều chỉnh cấu hình.

## 1. Partition và consumer trong Kafka

Một Kafka topic được chia thành một hoặc nhiều partition. Mỗi partition là một log có thứ tự riêng, chứa các record được ghi nối tiếp và đánh số bằng offset. Kafka phân phối các partition cho consumer thuộc cùng một consumer group.

Quy tắc quan trọng:

- Trong cùng một consumer group, tại một thời điểm, một partition chỉ được gán cho tối đa một consumer.
- Một consumer có thể nhận nhiều partition.
- Một consumer group có thể có consumer không được gán partition nếu số consumer lớn hơn số partition.
- Các consumer group khác nhau có thể đọc độc lập cùng một topic; mỗi group có tiến độ offset riêng.

Ví dụ topic orders có sáu partition:

~~~text
Topic orders
  P0  P1  P2  P3  P4  P5
~~~

Nếu group order-processor có ba consumer, Kafka có thể phân phối hai partition cho mỗi consumer. Nếu group có sáu consumer, mỗi consumer có thể nhận một partition. Nếu group có tám consumer, tối đa sáu consumer được gán partition; hai consumer còn lại không nhận record từ topic đó.

Giới hạn này áp dụng theo từng consumer group. Nếu một dịch vụ chạy hai group khác nhau, mỗi group có thể đọc toàn bộ sáu partition độc lập. Không nên tạo group ID khác nhau cho từng replica khi mục tiêu là chia tải, vì cách đó tạo nhiều bản tiêu thụ độc lập thay vì chia partition giữa các replica.

## 2. concurrency trong Spring Cloud Stream

Với Kafka binder, thuộc tính concurrency trên consumer binding xác định số consumer đồng thời mà một instance ứng dụng tạo cho binding đó. Mỗi consumer có Kafka client và vòng đời poll riêng do container quản lý.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 3
~~~

Trong ví dụ, mỗi instance của ứng dụng tạo ba consumer cho input binding processOrder-in-0. Khi triển khai nhiều replica, tổng số consumer trong cùng group là tổng concurrency của tất cả replica.

concurrency là thuộc tính theo binding. Nếu một ứng dụng có nhiều input binding, mỗi binding có thể có cấu hình concurrency riêng. Cần tính tổng số consumer cho từng topic/group thay vì chỉ nhìn một giá trị concurrency ở cấp ứng dụng.

### 2.1. Công thức tính số consumer

Với một input binding subscribe một topic:

\[
C = I \times K
\]

Trong đó:

- I: số instance/replica ứng dụng đang chạy.
- K: concurrency trên mỗi instance cho binding đó.
- C: tổng số consumer trong cùng consumer group.

Nếu topic có P partition, số consumer tối đa được gán partition tại một thời điểm là:

\[
A = \min(P, C)
\]

Số consumer không được gán partition trong mô hình một topic là:

\[
U = \max(0, C-P)
\]

Các công thức này mô tả giới hạn về số lượng. Cách chia partition cụ thể còn phụ thuộc assignor, số topic được subscribe và trạng thái group.

### 2.2. Ví dụ tính concurrency

Giả sử dịch vụ có ba replica và concurrency bằng hai:

\[
C = 3 \times 2 = 6
\]

Nếu topic có sáu partition, cả sáu consumer đều có thể hoạt động:

~~~text
6 partitions / 6 consumers

Replica A: Consumer A1 <- P0
           Consumer A2 <- P1
Replica B: Consumer B1 <- P2
           Consumer B2 <- P3
Replica C: Consumer C1 <- P4
           Consumer C2 <- P5
~~~

Nếu topic chỉ có bốn partition, tối đa bốn consumer được gán:

~~~text
4 partitions / 6 consumers

Consumer A1 <- P0
Consumer A2 <- P1
Consumer B1 <- P2
Consumer B2 <- P3
Consumer C1 <- idle
Consumer C2 <- idle
~~~

Sơ đồ minh họa một cách phân phối có thể xảy ra; vị trí consumer nhận partition cụ thể do Kafka assignor quyết định.

### 2.3. Bảng so sánh nhanh

Giả sử một topic có sáu partition và tất cả replica dùng cùng group:

| Replica | Concurrency mỗi replica | Tổng consumer | Consumer tối đa hoạt động | Consumer dư |
|---:|---:|---:|---:|---:|
| 1 | 2 | 2 | 2 | 0 |
| 2 | 2 | 4 | 4 | 0 |
| 3 | 2 | 6 | 6 | 0 |
| 4 | 2 | 8 | 6 | 2 |
| 3 | 3 | 9 | 6 | 3 |
| 6 | 1 | 6 | 6 | 0 |

Tăng replica và tăng concurrency đều làm tăng tổng consumer. Hãy chọn cách scale dựa trên tài nguyên CPU/bộ nhớ, giới hạn triển khai và nhu cầu cô lập tác vụ.

## 3. Cấu hình concurrency trong Spring Cloud Stream

Concurrency được khai báo trên consumer binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 4
~~~

Trong ví dụ, mỗi replica tạo bốn consumer cho binding. Nếu chạy hai replica, group có tổng cộng tám consumer. Để cả tám consumer đều có thể nhận partition từ một topic, topic cần ít nhất tám partition.

Hãy dùng một group ID ổn định cho các replica cùng chia tải. Nếu không khai báo group, binder có thể dùng nhóm ẩn danh theo quy tắc của framework; điều này thường không phù hợp với consumer cần duy trì tiến độ sau khi khởi động lại.

### 3.1. Kiểm tra số partition thực tế

Không dựa vào giá trị concurrency để suy ra topic đã có đủ partition. Hãy kiểm tra metadata của topic trên broker hoặc bằng công cụ quản trị Kafka.

Ví dụ lệnh CLI:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Kết quả mô tả topic cho biết số partition và leader của từng partition. Nếu topic đã được tạo trước với số partition thấp hơn nhu cầu scale, cần lập kế hoạch tăng partition hoặc tạo topic mới theo quy trình vận hành. Tăng concurrency không tự tạo thêm partition.

### 3.2. Nhiều instance cùng group

Khi triển khai nhiều replica, tất cả replica của cùng một dịch vụ cần dùng cùng group ID để Kafka phân phối partition giữa chúng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 2
~~~

Group ID phải ổn định giữa các replica. Nếu mỗi replica sử dụng group ID khác nhau, mỗi group sẽ đọc toàn bộ topic và xử lý lại cùng các sự kiện. Đây là fan-out giữa các group, không phải scale-out trong một group.

### 3.3. Cơ chế rebalance mặc định

Kafka binder mặc định sử dụng cơ chế consumer group để Kafka quản lý partition assignment. Khi consumer mới tham gia, consumer cũ rời group hoặc mất heartbeat, Kafka có thể rebalance để phân phối lại partition.

Với chế độ tự động này, thường không cần tự gán partition cho từng replica bằng instance-index. Nếu tắt autoRebalanceEnabled, binder có thể sử dụng instanceCount và instanceIndex để gán partition theo cấu hình tĩnh. Khi đó, số instance và index phải được quản lý đồng bộ với deployment; không trộn cấu hình tĩnh và mong đợi Kafka tự cân bằng như chế độ mặc định.

## 4. Giới hạn concurrency theo partition count

### 4.1. Consumer dư sẽ rảnh

Giả sử topic có ba partition nhưng mỗi replica tạo hai consumer và hệ thống chạy hai replica:

\[
C = 2 \times 2 = 4,\quad P = 3
\]

Chỉ tối đa ba consumer được gán partition. Consumer còn lại không thể xử lý record của topic trong group đó cho đến khi có thay đổi assignment.

Điều này không nhất thiết là lỗi. Consumer dư có thể hữu ích nếu số partition tăng trong tương lai hoặc deployment thay đổi. Tuy nhiên, chúng vẫn tiêu thụ tài nguyên như thread, Kafka client, connection và bộ nhớ; không nên tạo concurrency quá cao mà không có lý do.

### 4.2. Một consumer có thể nhận nhiều partition

Nếu topic có mười hai partition và group có ba consumer, mỗi consumer có thể được gán khoảng bốn partition. Consumer đó đọc record từ các partition được gán thông qua poll.

Số partition lớn hơn số consumer không có nghĩa dữ liệu bị xử lý tuần tự trên toàn topic. Các consumer vẫn hoạt động song song; một consumer chỉ quản lý nhiều partition.

### 4.3. Tăng concurrency có giới hạn

Nếu số partition là sáu, tăng concurrency mỗi replica từ ba lên sáu khi chỉ có một replica có thể tăng số consumer từ ba lên sáu. Nhưng tăng lên mười hai sẽ không làm số consumer hoạt động vượt sáu.

Khi đã đạt giới hạn partition, muốn tăng song song ở cấp consumer group cần tăng số partition hoặc thay đổi mô hình xử lý. Tăng partition có tác động đến key mapping, thứ tự và tài nguyên broker nên cần đánh giá trước.

### 4.4. Nhiều topic trong cùng binding

Nếu binding subscribe nhiều topic, tổng số partition có thể được gán là tổng partition của các topic được subscribe, nhưng assignment và độ cân bằng phụ thuộc assignor. Không áp dụng công thức đơn giản của một topic mà bỏ qua số topic và pattern subscription.

## 5. Phân biệt concurrency với max.poll.records

Hai thuộc tính này điều khiển hai khía cạnh khác nhau:

| Thuộc tính | Điều khiển | Đơn vị |
|---|---|---|
| consumer.concurrency | Số consumer đồng thời trên mỗi instance/binding | Consumer |
| max.poll.records | Số record tối đa Kafka trả về trong một lần poll của một consumer | Record trên mỗi poll |

Ví dụ, một instance có concurrency bằng ba và max.poll.records bằng 100. Ứng dụng có ba Kafka consumer; mỗi consumer có thể nhận tối đa 100 record từ một lần poll, tùy số record đang có và partition được gán.

max.poll.records không tạo thêm consumer và không tăng số partition. Nó điều chỉnh kích thước lô record mà mỗi consumer lấy trong một lần poll.

### 5.1. Cấu hình max.poll.records

Kafka binder cho phép truyền native consumer properties qua cấu hình binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                max.poll.records: 100
~~~

Trong ví dụ, concurrency bằng ba consumer trên mỗi instance; mỗi consumer có giới hạn 100 record trong một lần poll. Với kiểu consumer xử lý từng record, container có thể chuyển các record cho handler lần lượt. Với batch listener hoặc cấu hình xử lý khác, cách ứng dụng nhận batch có thể khác.

Không nên tăng max.poll.records chỉ để tăng throughput. Nếu xử lý một record mất nhiều thời gian, batch lớn có thể khiến thời gian xử lý giữa hai lần poll vượt giới hạn và gây rebalance.

## 6. max.poll.interval.ms và thời gian xử lý

Kafka yêu cầu consumer tiếp tục gọi poll trong khoảng thời gian quy định. max.poll.interval.ms đặt giới hạn tối đa giữa các lần gọi poll trước khi consumer được xem là không còn tiến triển và có thể rời group, dẫn đến partition được gán lại.

Giá trị này cần đủ lớn cho thời gian xử lý thực tế của một batch, nhưng không nên tăng tùy tiện vì nó ảnh hưởng thời gian phát hiện consumer bị kẹt.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                max.poll.records: 50
                max.poll.interval.ms: 300000
~~~

Trong ví dụ, mỗi consumer lấy tối đa 50 record mỗi lần poll và có khoảng thời gian tối đa giữa hai lần poll theo cấu hình Kafka. Đây là giá trị minh họa; hãy đo thời gian xử lý batch ở phân vị cao, tính thêm thời gian retry nội bộ và chọn giới hạn phù hợp.

### 6.1. Quan hệ giữa batch size và thời gian xử lý

Nếu một consumer xử lý từng record tuần tự và thời gian trung bình mỗi record là t, batch có B record có thể mất xấp xỉ:

\[
T_{\text{batch}} \approx B \times t
\]

Đây chỉ là ước lượng đơn giản. Thời gian thực tế còn phụ thuộc I/O, database, retry, GC, network và độ phân bố dữ liệu. Cần kiểm tra thời gian xử lý ở trường hợp xấu, không chỉ dùng trung bình.

Nếu T_batch tiến gần hoặc vượt max.poll.interval.ms, hãy xem xét:

- Giảm max.poll.records.
- Tăng hiệu quả xử lý từng record.
- Tăng max.poll.interval.ms trong giới hạn vận hành chấp nhận được.
- Tách tác vụ dài sang một mô hình xử lý bất đồng bộ có cơ chế pause/resume và commit phù hợp.
- Giảm retry blocking trong luồng consumer.

Không chuyển việc xử lý sang thread khác rồi commit offset ngay lập tức nếu chưa có cơ chế bảo đảm rằng tác vụ bất đồng bộ hoàn tất trước khi offset được commit. Điều đó có thể làm mất message khi ứng dụng dừng.

## 7. Concurrency, thứ tự và partition key

Concurrency tăng khả năng xử lý nhiều partition song song. Kafka vẫn giữ thứ tự record trong một partition, nhưng không có thứ tự tổng thể giữa các partition.

Nếu các sự kiện của cùng một đơn hàng cần xử lý theo thứ tự, producer phải dùng key ổn định như orderId để những sự kiện đó đi vào cùng partition. Trong Spring Cloud Stream có thể cấu hình partition key:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

Kafka binder tính partition theo cấu hình partitioning của binding. Nếu ứng dụng hoặc consumer Kafka khác cần đọc Kafka record key thực tế cho compaction hoặc định tuyến riêng, hãy kiểm tra cấu hình message key của binder và xác minh record key trên broker; partition selection và record key là hai khía cạnh cần được hiểu rõ.

### 7.1. Một partition chỉ có một consumer trong group

Kafka không gán cùng một partition cho hai consumer trong cùng group tại cùng thời điểm. Vì vậy, hai consumer thread có thể xử lý hai partition khác nhau đồng thời, còn các record trong một partition vẫn thuộc cùng consumer.

Tuy nhiên, ứng dụng có thể tự offload message sang executor hoặc reactive pipeline. Nếu làm vậy, nhiều record cùng partition có thể hoàn tất không theo thứ tự đọc. Khi thứ tự nghiệp vụ quan trọng, cần xử lý tuần tự theo partition hoặc key và chỉ commit offset khi các record trước đó đã hoàn tất.

### 7.2. Retry và thứ tự

Retry blocking trong consumer có thể làm chậm partition đang xử lý. Nếu chuyển lỗi sang retry topic hoặc DLQ, record sau có thể tiếp tục được xử lý trong khi record trước đang chờ retry. Khi cần thứ tự nghiêm ngặt, phải xác định liệu retry có được phép làm gián đoạn thứ tự hay cần giữ partition tạm dừng.

Không thể đồng thời tối đa hóa song song và giữ thứ tự toàn cục. Hãy xác định phạm vi thứ tự thật sự cần bảo vệ, thường là theo aggregate hoặc key.

## 8. Chọn concurrency và partition count

Không có công thức duy nhất cho mọi workload. Hãy bắt đầu từ throughput mục tiêu, thời gian xử lý và tài nguyên:

1. Đo thời gian xử lý một record và throughput của một consumer.
2. Xác định throughput mục tiêu của dịch vụ.
3. Ước lượng số consumer cần thiết.
4. Nhân concurrency mỗi replica với số replica dự kiến.
5. Bảo đảm topic có đủ partition để hỗ trợ số consumer cần hoạt động.
6. Kiểm thử với dữ liệu và tải thực tế.
7. Theo dõi lag và mức phân bố tải để điều chỉnh.

Ví dụ nếu một consumer xử lý ổn định 200 record/giây và dịch vụ cần 900 record/giây, ước lượng ban đầu cần ít nhất năm consumer hoạt động. Có thể triển khai hai replica với concurrency ba, tổng sáu consumer, và topic có ít nhất sáu partition. Con số thực tế phải đo lại vì broker, database, key skew và chi phí xử lý ảnh hưởng throughput.

### 8.1. Không tạo partition quá nhiều

Partition nhiều giúp tăng khả năng song song và tạo dư địa scale, nhưng cũng làm tăng:

- Metadata và chi phí quản lý partition trên broker.
- File handle, log segment và chi phí replication.
- Số lượng tác vụ rebalance và thời gian khôi phục.
- Độ phức tạp theo dõi lag và phân bố key.

Chọn partition count dựa trên nhu cầu hiện tại và kế hoạch tăng trưởng hợp lý. Không tạo số lượng rất lớn chỉ để phòng trường hợp có thể cần đến.

### 8.2. Tăng partition có thể thay đổi key mapping

Với partition selector dựa trên hash và số partition, tăng partition count có thể khiến một key được ánh xạ sang partition khác. Record cũ vẫn ở partition cũ; record mới có thể đi vào partition mới. Điều này có thể làm các sự kiện cùng aggregate được xử lý song song trong giai đoạn chuyển tiếp.

Nếu thứ tự theo key là bắt buộc, hãy lập kế hoạch migration: dừng hoặc điều tiết producer, xử lý hết backlog cũ, thay đổi topology theo giai đoạn hoặc tạo topic phiên bản mới. Không tăng partition trong production mà không đánh giá tác động.

## 9. Rebalance và triển khai nhiều instance

Khi một instance mới tham gia consumer group, Kafka phân phối lại partition theo assignor. Khi instance dừng hoặc mất kết nối, group cũng có thể rebalance. Trong thời gian rebalance, việc tiêu thụ có thể tạm gián đoạn.

### 9.1. Những nguyên nhân gây rebalance

- Replica mới khởi động và tham gia group.
- Replica bị dừng hoặc restart.
- Consumer không gọi poll trong thời gian cho phép.
- Session timeout hoặc heartbeat không được duy trì.
- Thay đổi subscription hoặc số consumer.
- Một số thay đổi cấu hình group/assignor.

### 9.2. Giảm tác động rebalance

- Dùng graceful shutdown để consumer rời group có kiểm soát.
- Đặt max.poll.records phù hợp với thời gian xử lý.
- Tránh handler blocking quá lâu.
- Theo dõi thời gian rebalance và consumer lag.
- Chọn partition count đủ cho số consumer mục tiêu.
- Cân nhắc cooperative assignor nếu phiên bản Kafka và binder hỗ trợ, sau khi kiểm thử tương thích.

### 9.3. Rolling deployment

Trong rolling deployment, replica cũ rời group và replica mới tham gia theo từng đợt. Kafka có thể rebalance nhiều lần. Cần tránh triển khai đồng loạt gây mất toàn bộ consumer trong thời gian ngắn, và đặt readiness/liveness probe phù hợp để không đưa instance vào nhận traffic khi binder chưa sẵn sàng.

Nếu số consumer thay đổi liên tục do autoscaling, có thể phát sinh rebalance thường xuyên. Hãy cân nhắc thời gian scale cooldown, giới hạn replica tối thiểu/tối đa và chi phí rebalance.

## 10. Quan sát hiệu quả concurrency

Chỉ nhìn CPU hoặc số replica không đủ để đánh giá concurrency. Cần theo dõi:

| Chỉ số | Điều cần quan sát |
|---|---|
| Consumer count theo group | Số consumer thực tế so với số partition |
| Partition assignment | Partition nào được gán cho consumer nào |
| Consumer lag theo partition | Partition nào đang tích lũy backlog |
| Records consumed per second | Throughput thực tế |
| Processing duration | Thời gian xử lý từng record/batch |
| Poll duration và poll interval | Consumer có gọi poll đúng hạn không |
| Rebalance count/duration | Group có thay đổi assignment quá thường xuyên không |
| CPU, memory, GC | Concurrency có vượt tài nguyên instance không |
| Partition skew | Một partition có tải cao bất thường không |
| Error/retry rate | Lỗi có làm consumer chậm hoặc gây lặp không |

Nếu consumer lag không giảm khi tăng concurrency, kiểm tra xem số partition đã đạt giới hạn chưa, key có bị lệch không, consumer có bị nghẽn database hoặc dịch vụ phụ thuộc không, và thời gian xử lý có đang quá dài không.

## 11. Kiểm thử concurrency và giới hạn partition

Test binder của Spring Cloud Stream hữu ích cho kiểm tra binding và logic message, nhưng không mô phỏng đầy đủ Kafka group coordinator, partition assignment và rebalance. Các hành vi này cần integration test với Kafka thật, ví dụ dùng Testcontainers.

### 11.1. Kiểm thử số consumer và assignment

Một integration test có thể:

1. Khởi chạy Kafka test broker.
2. Tạo topic orders với số partition đã biết, ví dụ bốn.
3. Khởi động ứng dụng consumer với concurrency bằng hai và group ID cố định.
4. Chờ group assignment hoàn tất.
5. Đọc trạng thái group để xác minh có tối đa hai consumer được gán partition và mỗi partition chỉ thuộc một consumer.
6. Khởi động thêm replica thứ hai và xác minh assignment được rebalance.

Không nên chỉ kiểm tra property concurrency đã được bind. Cần xác minh consumer thực sự tham gia group và partition được phân phối như mong muốn.

### 11.2. Kiểm thử giới hạn consumer

Với một topic có ba partition và bốn consumer trong group, xác minh tối đa ba consumer có assignment. Consumer dư có thể tồn tại nhưng không được nhận partition từ topic đó.

Với một topic có sáu partition và ba consumer, xác minh mỗi consumer có thể nhận nhiều partition. Không khẳng định assignor luôn phân phối chính xác hai partition cho từng consumer trong mọi cấu hình nhiều topic.

### 11.3. Kiểm thử key affinity và thứ tự

Gửi nhiều record với cùng orderId và xác minh chúng đi vào cùng partition. Gửi record của nhiều orderId và kiểm tra phân phối qua các partition. Sau đó xác minh consumer xử lý các record cùng partition theo yêu cầu thứ tự của ứng dụng.

### 11.4. Kiểm thử max.poll.records và max.poll.interval.ms

Tạo workload có thời gian xử lý được kiểm soát để xác minh:

- max.poll.records giới hạn số record trả về trong một poll.
- Batch lớn làm tăng thời gian xử lý giữa các lần poll.
- Consumer có thể rời group nếu vượt max.poll.interval.ms.
- Giảm batch size hoặc tối ưu handler giúp tránh rebalance do xử lý quá lâu.

Không nên cố tình tạo timeout trong môi trường production. Dùng test broker và dữ liệu kiểm soát để kiểm tra tình huống này.

## 12. Những lỗi thường gặp

1. **Tăng concurrency mà không tăng partition**: consumer dư không được gán partition. Hãy tính tổng consumer theo replica nhân concurrency.
2. **Mỗi replica dùng group ID khác nhau**: mỗi group đọc toàn bộ topic, gây xử lý lặp ngoài ý muốn. Hãy dùng chung group cho các replica cần chia tải.
3. **Nhầm concurrency với số record mỗi poll**: concurrency tạo consumer; max.poll.records giới hạn record mỗi lần poll. Hãy điều chỉnh đúng thuộc tính.
4. **Nhầm partition count với replica count**: partition là đơn vị phân phối dữ liệu, replica là tiến trình ứng dụng. Hai số này cần được thiết kế cùng nhau.
5. **Tăng max.poll.records quá cao**: thời gian xử lý batch có thể vượt max.poll.interval.ms. Hãy đo thời gian xử lý và điều chỉnh batch.
6. **Xử lý bất đồng bộ nhưng commit offset quá sớm**: ứng dụng có thể mất tác vụ chưa hoàn tất khi crash. Hãy phối hợp ack/commit với completion.
7. **Giả định concurrency cao luôn tăng throughput**: broker, database, hot key hoặc CPU có thể là nút thắt. Hãy đo lag và throughput.
8. **Bỏ qua rebalance khi autoscaling**: scale liên tục có thể làm consumer tạm ngừng nhận dữ liệu. Hãy dùng cooldown và graceful shutdown.
9. **Tăng partition tùy tiện**: key có thể chuyển partition và làm gián đoạn thứ tự theo aggregate. Hãy có kế hoạch migration.
10. **Không kiểm tra partition assignment thực tế**: property đúng không chứng minh consumer được gán như dự kiến. Hãy integration test với Kafka.
11. **Không theo dõi partition skew**: một partition nóng có thể giữ lag cao dù consumer khác rảnh. Hãy chọn key và kiểm tra phân phối dữ liệu.

## 13. Quy trình cấu hình concurrency

Khi tối ưu một Kafka consumer trong Spring Cloud Stream:

1. Xác định topic và số partition thực tế.
2. Xác định group ID dùng chung cho các replica cần chia tải.
3. Đo throughput và thời gian xử lý của một consumer.
4. Ước lượng tổng consumer cần thiết.
5. Chọn số replica và concurrency mỗi replica sao cho tổng consumer không vượt xa partition count.
6. Cấu hình consumer.concurrency trên input binding.
7. Điều chỉnh max.poll.records theo kích thước batch và thời gian xử lý.
8. Điều chỉnh max.poll.interval.ms theo worst-case processing duration.
9. Kiểm thử assignment, rebalance, key affinity và thứ tự.
10. Theo dõi consumer lag, partition skew, throughput và tài nguyên sau triển khai.
11. Chỉ thay đổi partition count khi đã đánh giá key remapping và kế hoạch migration.

## Kết luận

Concurrency trong Spring Cloud Stream Kafka binder xác định số consumer đồng thời trên mỗi instance cho một input binding. Khi có nhiều replica dùng chung group, tổng số consumer bằng số replica nhân concurrency. Với một topic có P partition và C consumer, tối đa min(P,C) consumer có thể được gán partition; phần còn lại rảnh nếu C lớn hơn P.

Concurrency, max.poll.records và max.poll.interval.ms giải quyết ba vấn đề khác nhau: số consumer, số record mỗi lần poll và thời gian tối đa giữa các lần poll. Chọn cấu hình tốt cần cân bằng partition count, replica, batch size, thời gian xử lý, key distribution và tài nguyên. Hãy xác minh bằng consumer assignment và lag thực tế thay vì chỉ tăng concurrency theo cảm tính.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
