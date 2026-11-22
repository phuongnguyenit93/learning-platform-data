# Range, RoundRobin, Sticky và CooperativeSticky assignor

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này so sánh bốn partition assignor thường gặp: **RangeAssignor**, **RoundRobinAssignor**, **StickyAssignor** và **CooperativeStickyAssignor**.

Partition assignor quyết định các partition của topic được phân phối cho những consumer trong cùng group như thế nào. Chọn assignor ảnh hưởng đến độ cân bằng tải, số partition phải chuyển khi group thay đổi thành viên và thời gian consumer bị gián đoạn trong rebalance. Bốn assignor có mục tiêu khác nhau: Range chia các dải partition theo từng topic; RoundRobin luân phiên trên danh sách partition; Sticky ưu tiên giữ assignment cũ; CooperativeSticky kết hợp tính ổn định đó với rebalance tăng dần.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của partition assignor trong consumer group.
- Mô tả cách RangeAssignor chia partition thành các dải liên tiếp theo từng topic.
- Mô tả cách RoundRobinAssignor phân phối luân phiên partition qua các consumer có đăng ký topic tương ứng.
- Giải thích cách StickyAssignor cân bằng assignment và giảm số partition bị chuyển khi group thay đổi.
- Phân biệt StickyAssignor với CooperativeStickyAssignor về giao thức rebalance.
- Dự đoán tác động khi consumer tham gia, rời group hoặc thay đổi subscription.
- Cấu hình assignor bằng Java Kafka Consumer và Spring Kafka.
- Lập kế hoạch chuyển từ eager sang cooperative rebalance an toàn.
- Nhận biết giới hạn của assignor khi số partition, subscription hoặc tải nghiệp vụ không đồng đều.

## 2. Partition assignor làm nhiệm vụ gì?

Một topic được chia thành các partition. Trong một consumer group, Kafka phân phối các partition đó cho các consumer thành viên. Partition assignor là thuật toán xác định consumer nào nhận partition nào.

Ví dụ topic **orders** có sáu partition và consumer group có ba member:

~~~text
Topic orders:
  orders-0
  orders-1
  orders-2
  orders-3
  orders-4
  orders-5

Consumer group:
  Consumer A
  Consumer B
  Consumer C
~~~

Một assignment có thể là:

~~~text
Consumer A -> orders-0, orders-3
Consumer B -> orders-1, orders-4
Consumer C -> orders-2, orders-5
~~~

Assignor hoạt động trong phạm vi một consumer group. Hai group khác nhau có assignment và offset độc lập dù cùng đọc một topic.

### 2.1. Những yếu tố ảnh hưởng đến assignment

Assignor phải xét:

- Danh sách topic mỗi consumer đăng ký.
- Danh sách partition của các topic đó.
- Số lượng consumer đang là thành viên group.
- Metadata group và assignment trước đó, nếu thuật toán sử dụng tính ổn định.
- Giao thức rebalance mà các member hỗ trợ.

Không phải consumer nào cũng nhất thiết đăng ký cùng một tập topic. Khi subscription khác nhau, assignor chỉ có thể giao partition của một topic cho consumer đã đăng ký topic đó.

### 2.2. Assignment cân bằng không đồng nghĩa tải xử lý cân bằng

Một assignor có thể chia mỗi consumer hai partition, nhưng lượng record và chi phí xử lý trên mỗi partition có thể khác nhau rất lớn.

Ví dụ:

| Partition | Throughput giả định |
|---|---:|
| orders-0 | 1.000 record/s |
| orders-1 | 100 record/s |
| orders-2 | 900 record/s |
| orders-3 | 80 record/s |

Nếu Consumer A nhận orders-0 và orders-1, Consumer B nhận orders-2 và orders-3, mỗi consumer có hai partition nhưng throughput lần lượt là 1.100 và 980 record/s. Trong trường hợp khác, chênh lệch có thể lớn hơn nhiều.

Assignor chủ yếu cân bằng theo partition và subscription; nó không tự đo CPU hoặc thời gian xử lý nghiệp vụ để chia tải chính xác. Cần theo dõi consumer lag, throughput và thời gian xử lý theo partition.

## 3. Eager và cooperative rebalance

Trước khi so sánh bốn assignor, cần hiểu hai kiểu rebalance.

### 3.1. Eager rebalance

Với eager rebalance, các consumer trong group thu hồi toàn bộ partition đang sở hữu trước khi assignment mới được áp dụng. Sau đó assignor tính assignment mới và partition được giao lại.

~~~text
Trước rebalance:
  A -> P0, P1
  B -> P2, P3

Group có thay đổi thành viên.

Eager rebalance:
  A -> thu hồi P0, P1
  B -> thu hồi P2, P3
  Tất cả member tham gia rebalance

Sau rebalance:
  A -> P0, P2
  B -> P1, P3
~~~

Ngay cả partition vẫn được giao cho cùng consumer cũng có thể bị thu hồi rồi gán lại. Trong khoảng thời gian này, consumer có thể tạm dừng xử lý record.

RangeAssignor, RoundRobinAssignor và StickyAssignor sử dụng kiểu eager trong cấu hình classic consumer group protocol thông thường.

### 3.2. Cooperative (incremental) rebalance

Cooperative rebalance chỉ thu hồi các partition cần chuyển sang consumer khác. Consumer có thể tiếp tục xử lý các partition được giữ lại trong khi quá trình phân phối diễn ra.

~~~text
Trước rebalance:
  A -> P0, P1
  B -> P2, P3

Consumer C tham gia.

Cooperative rebalance:
  A giữ P0, P1
  B giữ P2
  B thu hồi P3
  C nhận P3 sau khi partition được giải phóng

Sau rebalance:
  A -> P0, P1
  B -> P2
  C -> P3
~~~

Trong một số thay đổi membership, quá trình cooperative có thể cần nhiều vòng rebalance: vòng đầu xác định partition cần chuyển và yêu cầu owner cũ thu hồi; vòng tiếp theo mới giao partition đã được giải phóng cho owner mới.

Cooperative rebalance giảm phạm vi gián đoạn, nhưng không loại bỏ hoàn toàn rebalance, duplicate hoặc yêu cầu commit offset an toàn. Ứng dụng vẫn phải xử lý revoke/assign callback và idempotency.

## 4. RangeAssignor

**RangeAssignor** chia partition thành các dải liên tiếp cho consumer. Thuật toán thực hiện riêng cho từng topic, dựa trên danh sách partition và consumer đã đăng ký topic đó.

Giả sử topic **orders** có 7 partition và group có 3 consumer đều đăng ký topic:

~~~text
Partition:
  orders-0, orders-1, orders-2, orders-3,
  orders-4, orders-5, orders-6

Consumer:
  A, B, C
~~~

Cách chia Range:

- Mỗi consumer nhận tối thiểu 2 partition.
- Còn dư 1 partition, consumer đầu tiên nhận thêm một partition.
- Các partition được giao thành từng dải liên tiếp.

Kết quả:

~~~text
Consumer A -> orders-0, orders-1, orders-2
Consumer B -> orders-3, orders-4
Consumer C -> orders-5, orders-6
~~~

### 4.1. Cách tính số partition

Với một topic có:

- P partition.
- C consumer đang đăng ký topic đó.
- q = floor(P / C).
- r = P mod C.

Mỗi consumer nhận q partition; r consumer đầu tiên nhận thêm một partition. Các partition được chia thành các đoạn liên tiếp theo thứ tự consumer.

Ví dụ P=10, C=3:

- q=3.
- r=1.
- Consumer A nhận 4 partition.
- Consumer B và C mỗi người nhận 3 partition.

### 4.2. Range trên nhiều topic có thể gây lệch tổng thể

Điểm quan trọng là RangeAssignor chia riêng theo từng topic. Mỗi topic lại bắt đầu phân phối từ consumer đầu tiên.

Giả sử có hai topic, mỗi topic có 3 partition và hai consumer đều đăng ký cả hai topic:

~~~text
Topic orders:
  A -> orders-0, orders-1
  B -> orders-2

Topic payments:
  A -> payments-0, payments-1
  B -> payments-2

Tổng:
  A -> 4 partition
  B -> 2 partition
~~~

Mỗi topic được chia gần cân bằng, nhưng tổng số partition của consumer A gấp đôi consumer B. Đây là một nhược điểm có thể gặp khi nhiều topic có số partition nhỏ và cùng subscription.

### 4.3. Khi nào dùng RangeAssignor?

RangeAssignor phù hợp khi:

- Muốn các consumer nhận những dải partition liên tiếp.
- Ứng dụng xử lý theo thứ tự partition và muốn assignment dễ quan sát.
- Group thường đọc một topic hoặc các topic có số partition và subscription tương đối đồng đều.
- Mức độ thay đổi assignment khi rebalance không phải vấn đề lớn nhất.

Cần cân nhắc khi group đọc nhiều topic có số partition nhỏ, vì việc chia riêng theo từng topic có thể tạo phân bố tổng thể không đều.

## 5. RoundRobinAssignor

**RoundRobinAssignor** sắp xếp các topic-partition theo thứ tự và phân phối luân phiên qua danh sách consumer. Consumer chỉ nhận partition của topic mà nó đã đăng ký.

Nếu tất cả consumer đăng ký cùng tập topic, RoundRobin thường tạo phân bố số partition đồng đều hơn Range trên nhiều topic.

Ví dụ hai topic, mỗi topic có ba partition và hai consumer đều đăng ký cả hai topic:

~~~text
Danh sách partition đã sắp xếp:
  orders-0
  orders-1
  orders-2
  payments-0
  payments-1
  payments-2

Phân phối luân phiên:
  A -> orders-0, orders-2, payments-1
  B -> orders-1, payments-0, payments-2
~~~

Mỗi consumer nhận ba partition.

### 5.1. Subscription khác nhau

Nếu consumer có subscription khác nhau, RoundRobin chỉ phân phối partition cho member có đăng ký topic tương ứng.

Ví dụ:

- Consumer A đăng ký orders và payments.
- Consumer B chỉ đăng ký orders.
- Consumer C đăng ký payments.

Các partition của orders chỉ được phân phối giữa A và B; partition payments chỉ được phân phối giữa A và C. Kết quả có thể không đều về tổng số partition vì các tập consumer đủ điều kiện khác nhau.

### 5.2. Ưu điểm và giới hạn

Ưu điểm:

- Dễ hiểu và dễ dự đoán khi các consumer có cùng subscription.
- Phân bố tổng thể qua nhiều topic thường đều hơn Range.
- Không gom toàn bộ dải partition của một topic vào một consumer.

Giới hạn:

- Không ưu tiên giữ assignment cũ khi membership thay đổi.
- Eager rebalance thu hồi toàn bộ partition trước khi gán lại.
- Khi consumer tham gia hoặc rời group, nhiều partition có thể chuyển owner hơn mức cần thiết.
- Với subscription không đồng nhất, số partition mỗi consumer có thể vẫn lệch.

### 5.3. Khi nào dùng RoundRobinAssignor?

RoundRobin phù hợp khi:

- Các consumer thường đăng ký cùng tập topic.
- Muốn phân bố partition đều trên nhiều topic.
- Muốn assignment luân phiên, dễ quan sát.
- Tính ổn định assignment và giảm partition movement không phải yêu cầu hàng đầu.

Nếu group thường xuyên thay đổi thành viên hoặc rebalance gây gián đoạn đáng kể, Sticky hoặc CooperativeSticky có thể phù hợp hơn.

## 6. StickyAssignor

**StickyAssignor** có hai mục tiêu:

1. Cân bằng partition giữa các consumer trong phạm vi subscription cho phép.
2. Giữ assignment cũ nhiều nhất có thể để giảm số partition phải chuyển khi group thay đổi.

Tính chất thứ hai gọi là **stickiness** (tính ổn định assignment).

Giả sử ban đầu topic có 6 partition và group có hai consumer:

~~~text
Ban đầu:
  A -> P0, P1, P2
  B -> P3, P4, P5
~~~

Consumer C tham gia. Group cần phân phối lại thành ba consumer, mỗi consumer lý tưởng nhận hai partition.

Một assignment minh họa có thể là:

~~~text
Sau khi C tham gia:
  A -> P0, P1
  B -> P3, P4
  C -> P2, P5
~~~

Chỉ hai partition P2 và P5 chuyển sang C; các partition còn lại được giữ nguyên owner. Assignment cụ thể phụ thuộc subscription, metadata và trạng thái group, nhưng mục tiêu của StickyAssignor là giảm movement trong khi vẫn giữ cân bằng hợp lệ.

### 6.1. Vì sao giảm partition movement quan trọng?

Mỗi lần partition chuyển owner, ứng dụng có thể phải:

- Dừng xử lý partition cũ.
- Commit offset và hoàn tất công việc đang chạy.
- Đóng hoặc chuyển state cục bộ.
- Khôi phục cache hoặc state store ở consumer mới.
- Khởi động lại các tác vụ gắn với partition.
- Chấp nhận khả năng đọc lại record chưa commit.

Với consumer có local state lớn hoặc cần warm-up, việc chuyển partition có thể tốn nhiều thời gian và tài nguyên. StickyAssignor giảm số partition di chuyển để hạn chế các chi phí đó.

### 6.2. StickyAssignor vẫn dùng eager rebalance

Một điểm dễ nhầm: StickyAssignor giữ assignment ổn định, nhưng bản thân nó vẫn dùng eager rebalance trong classic consumer group protocol.

Điều đó có nghĩa là:

- Thuật toán cố gắng giữ partition ở đúng consumer cũ.
- Tuy nhiên, khi rebalance bắt đầu, các member vẫn phải thu hồi toàn bộ partition theo cơ chế eager.
- Sau đó assignment mới được áp dụng.

Vì thế, stickiness giảm số partition chuyển owner nhưng không loại bỏ giai đoạn dừng và phân phối lại toàn group.

### 6.3. Khi nào dùng StickyAssignor?

StickyAssignor phù hợp khi:

- Muốn cân bằng partition nhưng giảm movement.
- Consumer duy trì local state hoặc cache tốn chi phí khởi tạo.
- Group có membership thay đổi nhưng muốn hạn chế partition chuyển owner.
- Có thể chấp nhận eager rebalance.

Nếu muốn vừa giữ assignment cũ vừa giảm phạm vi thu hồi partition trong rebalance, hãy xem CooperativeStickyAssignor.

## 7. CooperativeStickyAssignor

**CooperativeStickyAssignor** kết hợp hai đặc tính:

- Tính cân bằng và ổn định assignment của StickyAssignor.
- Cơ chế cooperative/incremental rebalance, chỉ thu hồi các partition cần chuyển.

Điều này giúp các consumer giữ tiếp những partition không cần di chuyển trong lúc group điều chỉnh assignment.

Ví dụ ban đầu:

~~~text
A -> P0, P1, P2
B -> P3, P4, P5
~~~

Consumer C tham gia. Assignment mục tiêu là mỗi consumer nhận hai partition:

~~~text
Mục tiêu:
  A -> P0, P1
  B -> P3, P4
  C -> P2, P5
~~~

Trong cooperative rebalance:

1. Assignor xác định P2 và P5 cần chuyển sang C.
2. A và B tiếp tục giữ các partition không cần di chuyển.
3. A thu hồi P2, B thu hồi P5.
4. Sau khi partition đã được giải phóng, một vòng rebalance tiếp theo giao P2 và P5 cho C.
5. Các partition P0, P1, P3 và P4 tiếp tục được xử lý bởi owner cũ.

Ví dụ này minh họa mục tiêu của cooperative assignment; số vòng và assignment thực tế phụ thuộc trạng thái group, subscription và phiên bản client.

### 7.1. Ưu điểm

- Không buộc toàn bộ member thu hồi mọi partition khi chỉ một số partition cần chuyển.
- Giảm thời gian gián đoạn khi group thay đổi thành viên.
- Kết hợp khả năng cân bằng với giảm partition movement.
- Phù hợp với hệ thống có nhiều partition hoặc consumer giữ state cục bộ.

### 7.2. Giới hạn và yêu cầu

CooperativeStickyAssignor không có nghĩa rebalance hoàn toàn không gây gián đoạn:

- Partition cần chuyển vẫn phải được owner cũ thu hồi trước khi giao cho owner mới.
- Quá trình có thể cần nhiều vòng rebalance.
- Ứng dụng vẫn phải xử lý onPartitionsRevoked, onPartitionsAssigned và các trường hợp partition lost.
- Công việc đang chạy trên partition bị thu hồi phải được dừng hoặc hoàn tất an toàn.
- Tất cả member trong group cần hỗ trợ assignor/protocol tương thích.

Cooperative rebalance không tự bảo đảm exactly-once hoặc ngăn duplicate. Nếu record đã tạo side effect nhưng offset chưa commit, consumer mới vẫn có thể đọc lại record đó. Idempotency vẫn cần thiết.

### 7.3. Khi nào dùng CooperativeStickyAssignor?

Phù hợp khi:

- Group có nhiều consumer hoặc nhiều partition.
- Consumer thường xuyên scale up/down hoặc rolling restart.
- Partition movement tốn chi phí do local state hoặc warm-up.
- Muốn giảm thời gian dừng toàn group khi rebalance.
- Có thể triển khai đồng bộ client version và chiến lược chuyển đổi assignor.

Đây thường là lựa chọn đáng cân nhắc cho workload production có yêu cầu hạn chế gián đoạn khi rebalance, nhưng cần kiểm thử với subscription và lifecycle thực tế của ứng dụng.

## 8. So sánh bốn assignor

| Tiêu chí | Range | RoundRobin | Sticky | CooperativeSticky |
|---|---|---|---|---|
| Cách phân phối | Dải liên tiếp theo từng topic | Luân phiên qua danh sách topic-partition | Cân bằng và giữ assignment cũ | Cân bằng, giữ assignment cũ và chuyển dần |
| Cân bằng nhiều topic cùng subscription | Có thể lệch tổng thể | Thường tốt hơn | Cố gắng cân bằng tổng thể | Cố gắng cân bằng tổng thể |
| Giảm partition movement | Không phải mục tiêu chính | Không phải mục tiêu chính | Có | Có |
| Rebalance protocol | Eager | Eager | Eager | Cooperative |
| Thu hồi toàn bộ partition khi rebalance | Có | Có | Có | Không; chỉ thu hồi partition cần chuyển |
| Có thể cần nhiều vòng rebalance | Theo eager flow | Theo eager flow | Theo eager flow | Có thể |
| Giữ local state | Không tối ưu riêng cho mục tiêu này | Không tối ưu riêng cho mục tiêu này | Tốt hơn nhờ stickiness | Tốt hơn và giảm gián đoạn |
| Phù hợp | Dải partition liên tiếp, subscription đơn giản | Nhiều topic, subscription đồng nhất | Cần giảm movement | Cần giảm movement và rebalance gián đoạn |

Không có assignor tốt nhất cho mọi hệ thống. Hãy chọn dựa trên subscription, số topic/partition, tần suất thay đổi membership, local state và thời gian xử lý khi revoke/assign.

## 9. Cấu hình assignor trong Java Kafka Consumer

Classic consumer group protocol sử dụng thuộc tính **partition.assignment.strategy** để cấu hình assignor. Giá trị có thể là một hoặc nhiều class name.

### 9.1. Cấu hình RangeAssignor

~~~java
Properties props = new Properties();

props.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    List.of(
        "org.apache.kafka.clients.consumer.RangeAssignor"
    )
);
~~~

### 9.2. Cấu hình RoundRobinAssignor

~~~java
props.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    List.of(
        "org.apache.kafka.clients.consumer.RoundRobinAssignor"
    )
);
~~~

### 9.3. Cấu hình StickyAssignor

~~~java
props.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    List.of(
        "org.apache.kafka.clients.consumer.StickyAssignor"
    )
);
~~~

### 9.4. Cấu hình CooperativeStickyAssignor

~~~java
props.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    List.of(
        "org.apache.kafka.clients.consumer.CooperativeStickyAssignor"
    )
);
~~~

Cần bảo đảm các consumer trong cùng group có cấu hình tương thích và class assignor tồn tại trong Kafka client đang chạy. Nếu các member không có assignor chung, group có thể không hoàn tất quá trình join.

### 9.5. Cấu hình nhiều assignor

Classic consumer group protocol cho phép cấu hình danh sách assignor. Group chọn chiến lược tương thích chung theo cơ chế protocol; thứ tự trong danh sách có ý nghĩa khi lựa chọn.

Ví dụ:

~~~java
props.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    List.of(
        "org.apache.kafka.clients.consumer.RangeAssignor",
        "org.apache.kafka.clients.consumer.CooperativeStickyAssignor"
    )
);
~~~

Danh sách trên hữu ích trong quá trình chuyển đổi vì client có thể hỗ trợ cả assignor cũ và mới. Nếu RangeAssignor đứng trước và tất cả member đều hỗ trợ nó, group tiếp tục dùng Range cho đến khi chiến lược chung thay đổi.

Không nên hiểu danh sách này là Kafka chạy đồng thời cả hai thuật toán trong cùng một lần assignment.

## 10. Chuyển từ eager sang CooperativeSticky an toàn

Một thay đổi assignor trên một member đơn lẻ có thể khiến group không tìm được chiến lược chung với các member còn lại. Hãy triển khai theo từng giai đoạn.

### Giai đoạn 1: Nâng cấp client

Bảo đảm tất cả consumer instance sử dụng Kafka client có hỗ trợ CooperativeStickyAssignor. Nếu phiên bản client cũ chưa có class này, nâng cấp thư viện trước khi cấu hình assignor.

### Giai đoạn 2: Cho tất cả member hỗ trợ cả hai assignor

Triển khai cấu hình tương thích:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.RangeAssignor,org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Khi tất cả member đã hỗ trợ CooperativeSticky nhưng Range vẫn đứng trước trong danh sách chung, group có thể tiếp tục dùng Range. Giai đoạn này giúp rollout cấu hình mà không tạo ra member không có protocol chung.

### Giai đoạn 3: Chuyển sang CooperativeSticky

Sau khi toàn bộ member hỗ trợ CooperativeSticky, cập nhật cấu hình để chỉ còn:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Khi các member lần lượt nhận cấu hình mới, chiến lược chung có thể chuyển sang CooperativeSticky vì các member còn lại vẫn hỗ trợ nó qua danh sách hai assignor.

### Giai đoạn 4: Xác minh

- Kiểm tra group đã dùng đúng assignor.
- Theo dõi rebalance count và thời gian rebalance.
- Quan sát partition revoke/assign callback.
- Kiểm tra consumer lag và duplicate.
- Kiểm tra ứng dụng không tiếp tục xử lý partition sau khi đã revoke.
- Xác nhận tất cả member đã chạy cấu hình cuối.

Trong quá trình rollout, cần bảo đảm không có instance cũ không hỗ trợ CooperativeSticky tham gia lại group. Hãy thực hiện trong staging trước và có kế hoạch rollback phù hợp.

## 11. Lưu ý về classic và consumer group protocol mới

Các cấu hình assignor ở trên mô tả **classic consumer group protocol**, trong đó client tham gia group và sử dụng thuộc tính **partition.assignment.strategy** để thương lượng assignor.

Các phiên bản Kafka mới có thêm consumer group protocol mới, được chọn bằng cấu hình **group.protocol=consumer**. Trong protocol này, một số trách nhiệm điều phối và assignment được chuyển sang broker; cấu hình lựa chọn remote assignor và các assignor broker hỗ trợ có thể khác classic protocol.

Vì vậy:

- Nếu dùng classic protocol, kiểm tra partition.assignment.strategy trên từng consumer.
- Nếu dùng consumer protocol mới, kiểm tra group.protocol, group.remote.assignor và cấu hình assignor được broker hỗ trợ theo phiên bản.
- Không giả định cấu hình class Range/Sticky phía client sẽ có cùng tác dụng khi group chuyển sang protocol mới.
- Kiểm tra tài liệu đúng phiên bản Kafka broker và client trước khi chuyển protocol.

Protocol mới có cơ chế rebalance cooperative theo thiết kế. Cách chọn thuật toán phân phối partition vẫn cần được cấu hình và kiểm chứng theo phiên bản triển khai.

## 12. Quan sát assignment và rebalance

### 12.1. Dùng Kafka CLI

Liệt kê consumer group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Xem thành viên và assignment của group (tùy chọn CLI có thể khác theo phiên bản):

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
~~~

Windows PowerShell dùng script tương ứng trong **bin\windows**.

Kết quả giúp quan sát member, client ID, host và partition assignment. Để xác định assignor đang được dùng, có thể xem mô tả group qua AdminClient hoặc log/metric của consumer và đối chiếu cấu hình thực tế.

### 12.2. Dùng AdminClient

Java AdminClient có thể mô tả consumer group và lấy thông tin partition assignor cùng member assignment:

~~~java
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;

ConsumerGroupDescription description =
    admin.describeConsumerGroups(
        List.of("orders-service")
    ).all().get().get("orders-service");

System.out.println(
    "assignor=" + description.partitionAssignor()
);

description.members().forEach(member -> {
    System.out.println(
        "member=" + member.consumerId()
        + ", clientId=" + member.clientId()
        + ", host=" + member.host()
        + ", assignment=" + member.assignment().topicPartitions()
    );
});
~~~

Tên assignor được trả về phụ thuộc protocol và client/broker version. Với protocol mới, có thể có remote assignor hoặc thông tin assignment được quản lý theo cách khác.

### 12.3. Theo dõi metric và log

Các tín hiệu nên theo dõi:

- Số lần rebalance trong một khoảng thời gian.
- Thời gian rebalance.
- Số partition bị revoke và assign.
- Consumer lag theo partition.
- Thời gian xử lý record và batch.
- Số member trong group.
- Số partition mỗi consumer.
- Lỗi commit, heartbeat hoặc group coordination.
- Thời gian khôi phục local state sau khi nhận partition.

Sticky hoặc CooperativeSticky có thể giảm partition movement, nhưng nếu rebalance vẫn xảy ra liên tục, cần điều tra nguyên nhân membership thay đổi, poll interval, crash, network và rollout.

## 13. Chọn assignor theo tình huống

| Tình huống | Assignor nên thử trước | Lý do |
|---|---|---|
| Một topic, muốn các consumer nhận dải partition liên tiếp | RangeAssignor | Cách chia theo range dễ quan sát. |
| Nhiều topic, tất cả consumer có cùng subscription | RoundRobinAssignor | Phân phối luân phiên trên tổng danh sách partition. |
| Consumer có local state và cần hạn chế partition chuyển owner | StickyAssignor | Giữ assignment cũ nhiều nhất có thể trong eager rebalance. |
| Group scale up/down thường xuyên, cần giảm thời gian gián đoạn | CooperativeStickyAssignor | Giảm phạm vi partition bị revoke và chuyển dần. |
| Subscription khác nhau giữa các consumer | Đo thử Range, RoundRobin và Sticky | Kết quả phụ thuộc tập member đủ điều kiện cho từng topic. |
| Partition có throughput rất lệch | Kết hợp assignor với phân tích tải | Assignor không tự cân bằng theo CPU hoặc record rate. |

Đừng chọn assignor chỉ dựa trên số partition. Hãy xem tần suất rebalance, local state, subscription, throughput và yêu cầu ordering của nghiệp vụ.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Group không join được sau khi đổi assignor | Các member không có assignor chung hoặc client cũ không hỗ trợ class mới. | Đồng bộ Kafka client và triển khai migration theo giai đoạn. |
| CooperativeSticky không được chọn | Danh sách assignor chung vẫn ưu tiên một assignor eager đứng trước. | Kiểm tra partition.assignment.strategy trên mọi member. |
| Rebalance vẫn thu hồi toàn bộ partition | Group vẫn dùng eager assignor hoặc còn member chưa hỗ trợ cooperative. | Xác minh assignor/protocol thực tế và rollout đầy đủ. |
| Phân bố Range không đều giữa nhiều topic | Range chia riêng theo từng topic. | Thử RoundRobin hoặc Sticky với subscription tương ứng. |
| RoundRobin vẫn lệch số partition | Consumer có subscription khác nhau. | Xem topic nào từng member đăng ký và partition đủ điều kiện. |
| Sticky giữ partition nhưng consumer vẫn dừng khi rebalance | StickyAssignor vẫn dùng eager protocol. | Dùng CooperativeSticky nếu cần incremental rebalance. |
| Partition chuyển nhiều sau rolling restart | Member ID thay đổi hoặc group membership không ổn định. | Xem xét static membership, group.instance.id và CooperativeSticky. |
| Consumer xử lý duplicate sau revoke | Side effect hoàn tất nhưng offset chưa commit. | Dùng idempotency và commit an toàn trong revoke callback. |

## 15. Bài tập thực hành

### Bài 1: So sánh Range và RoundRobin

Tạo hai topic:

- orders: 6 partition.
- payments: 6 partition.

Chạy hai consumer trong cùng group, cả hai đăng ký cả hai topic.

1. Cấu hình RangeAssignor.
2. Ghi lại assignment từng consumer.
3. Đổi sang RoundRobinAssignor.
4. Ghi lại assignment.
5. So sánh tổng số partition mỗi consumer nhận.
6. Giải thích vì sao Range có thể chia đều theo từng topic nhưng lệch tổng thể.

### Bài 2: Quan sát Sticky khi consumer tham gia

1. Tạo topic có 6 partition.
2. Chạy hai consumer cùng group với StickyAssignor.
3. Ghi lại assignment ban đầu.
4. Khởi động consumer thứ ba.
5. Ghi lại partition chuyển owner.
6. So sánh số partition bị chuyển với một lần thử dùng Range hoặc RoundRobin.

Kết quả cụ thể có thể khác theo member ID và metadata; hãy tập trung đo số partition được giữ lại và số partition phải chuyển.

### Bài 3: Quan sát CooperativeSticky

1. Bảo đảm tất cả consumer dùng client hỗ trợ CooperativeStickyAssignor.
2. Triển khai cấu hình tương thích cho toàn group.
3. Chuyển group sang chỉ dùng CooperativeStickyAssignor.
4. Bật log cho ConsumerRebalanceListener.
5. Khởi động thêm hoặc dừng một consumer.
6. Ghi lại partition bị revoke và partition được giữ.
7. Quan sát liệu quá trình cần nhiều vòng rebalance hay không.
8. So sánh thời gian gián đoạn với eager assignor.

### Bài 4: Subscription không đồng nhất

1. Consumer A đăng ký orders và payments.
2. Consumer B chỉ đăng ký orders.
3. Consumer C chỉ đăng ký payments.
4. Thử Range và RoundRobin.
5. Ghi lại assignment và số partition mỗi member nhận.
6. Giải thích vì sao không thể chỉ chia tổng partition cho tổng consumer để dự đoán assignment.

## 16. Câu hỏi tự kiểm tra

1. Partition assignor quyết định điều gì trong consumer group?
2. RangeAssignor chia partition theo phạm vi nào?
3. Vì sao Range có thể tạo tổng assignment lệch khi group đọc nhiều topic?
4. RoundRobinAssignor phân phối partition theo cách nào?
5. Subscription không đồng nhất ảnh hưởng RoundRobin ra sao?
6. StickyAssignor tối ưu hai mục tiêu nào?
7. StickyAssignor có dùng cooperative rebalance không?
8. CooperativeStickyAssignor khác StickyAssignor ở điểm nào?
9. Vì sao cooperative rebalance có thể cần nhiều vòng?
10. Vì sao partition movement có thể tốn chi phí với consumer có local state?
11. Làm sao chuyển từ eager sang CooperativeSticky mà tránh group không có assignor chung?
12. partition.assignment.strategy áp dụng cho protocol nào?
13. Khi dùng consumer group protocol mới, cần kiểm tra cấu hình nào?
14. Vì sao số partition bằng nhau không bảo đảm throughput bằng nhau?
15. Khi consumer bị revoke partition, ứng dụng cần bảo vệ offset và side effect như thế nào?

## Kết luận

RangeAssignor chia partition thành các dải liên tiếp theo từng topic. RoundRobinAssignor phân phối luân phiên qua danh sách topic-partition và thường cân bằng tốt hơn khi consumer có cùng subscription. StickyAssignor cân bằng đồng thời giữ assignment cũ để giảm partition movement, nhưng vẫn dùng eager rebalance. CooperativeStickyAssignor giữ các partition không cần chuyển và chỉ revoke phần cần thiết, giúp giảm phạm vi gián đoạn.

Việc chọn assignor cần dựa trên số topic/partition, subscription, tần suất thay đổi membership, local state và yêu cầu thời gian phục hồi. Với workload production thường xuyên scale hoặc rolling restart, CooperativeSticky là lựa chọn đáng thử sau khi đồng bộ client và kiểm thử migration. Dù dùng assignor nào, ứng dụng vẫn phải xử lý rebalance callback, commit offset an toàn, idempotency và ordering nghiệp vụ.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Partition assignor | Thuật toán phân phối partition cho consumer trong một group. |
| RangeAssignor | Chia các partition thành dải liên tiếp theo từng topic. |
| RoundRobinAssignor | Phân phối luân phiên các topic-partition qua consumer đủ điều kiện. |
| StickyAssignor | Cân bằng assignment và hạn chế partition movement, dùng eager rebalance. |
| CooperativeStickyAssignor | Sticky assignment kết hợp cooperative/incremental rebalance. |
| Eager rebalance | Rebalance thu hồi toàn bộ partition hiện có trước khi áp dụng assignment mới. |
| Cooperative rebalance | Rebalance chỉ thu hồi partition cần chuyển owner. |
| Partition movement | Việc partition chuyển từ consumer này sang consumer khác. |
| Subscription | Tập topic mà consumer đăng ký đọc. |
| ConsumerRebalanceListener | Callback xử lý partition revoke, assign và lifecycle liên quan. |
| partition.assignment.strategy | Cấu hình assignor của classic consumer group protocol. |
| group.remote.assignor | Cấu hình chọn remote assignor trong consumer group protocol mới, tùy phiên bản Kafka. |

