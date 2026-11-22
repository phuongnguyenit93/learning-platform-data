# Throughput và latency

Trong vận hành Spring Kafka, throughput và latency là hai chỉ số mô tả khả năng xử lý của hệ thống theo hai góc nhìn khác nhau. Throughput cho biết hệ thống xử lý được bao nhiêu dữ liệu trong một đơn vị thời gian. Latency cho biết một bản ghi phải chờ bao lâu từ lúc được gửi đến lúc đạt được mốc xử lý mà ứng dụng quan tâm. Một cụm Kafka có thể đạt throughput cao nhưng vẫn làm người dùng chờ lâu; ngược lại, latency thấp ở tải nhỏ không chứng minh hệ thống đủ sức xử lý lưu lượng giờ cao điểm.

Khi thiết kế hoặc tối ưu Spring Kafka, cần đo cả hai chỉ số trên cùng một luồng dữ liệu, xác định rõ điểm bắt đầu và kết thúc của phép đo, sau đó tìm giới hạn ở producer, broker, consumer hay phần xử lý nghiệp vụ. Mục tiêu vận hành là đáp ứng lưu lượng thực tế với latency phù hợp, duy trì khả năng phục hồi khi có biến động và còn đủ headroom cho tải tăng hoặc một broker gặp sự cố.

## 1. Hiểu đúng throughput

**Throughput** là lượng công việc hoàn thành trong một đơn vị thời gian. Với Kafka, thường cần theo dõi ít nhất hai cách biểu diễn:

- **Records per second (records/s):** số bản ghi được gửi, ghi nhận hoặc tiêu thụ mỗi giây.
- **Bytes per second (bytes/s, KiB/s, MiB/s):** lượng dữ liệu được truyền hoặc xử lý mỗi giây.

Hai đơn vị này bổ sung cho nhau. Một hệ thống xử lý 20.000 bản ghi nhỏ mỗi giây có thể tiêu thụ ít băng thông hơn hệ thống xử lý 2.000 bản ghi lớn mỗi giây. Vì vậy, báo cáo throughput chỉ bằng records/s có thể che khuất áp lực lên mạng và đĩa; báo cáo chỉ bằng bytes/s lại không cho biết số lần gọi logic mà ứng dụng phải xử lý.

Nên phân biệt throughput tại từng chặng:

| Phạm vi | Câu hỏi cần trả lời | Ví dụ phép đo |
|---|---|---|
| Producer | Ứng dụng tạo và gửi được bao nhiêu dữ liệu? | Records gửi thành công/giây, bytes gửi/giây |
| Broker | Cụm Kafka nhận, ghi và phục vụ được bao nhiêu dữ liệu? | Bytes in/out, request rate, replication traffic |
| Consumer | Nhóm consumer xử lý được bao nhiêu dữ liệu? | Records tiêu thụ/giây, bytes fetch/giây |
| Nghiệp vụ | Bao nhiêu sự kiện đã hoàn tất tác vụ cuối cùng? | Số đơn hàng, thanh toán hoặc cập nhật đã xử lý/giây |

Throughput đầu vào và đầu ra không nhất thiết bằng nhau trong từng khoảng thời gian. Consumer có thể xử lý chậm hơn producer và tạo lag; cũng có thể xử lý nhanh hơn producer trong một khoảng thời gian để bù backlog. Với luồng dữ liệu ổn định, nếu tốc độ sản xuất liên tục lớn hơn tốc độ tiêu thụ thì lag sẽ tăng theo thời gian, dù cả producer và consumer đều chưa phát sinh lỗi.

Ví dụ, producer gửi trung bình 8.000 records/s nhưng consumer chỉ hoàn tất 6.500 records/s. Backlog tăng khoảng 1.500 records mỗi giây. Tăng throughput của producer trong tình huống này chỉ làm vấn đề nghiêm trọng hơn; cần tìm giới hạn ở consumer hoặc tăng năng lực tiêu thụ.

## 2. Hiểu đúng latency

**Latency** là thời gian từ một mốc bắt đầu đến một mốc kết thúc được định nghĩa rõ. Trong hệ thống Kafka, cụm từ “latency” có thể chỉ nhiều khoảng thời gian khác nhau:

- **Producer send latency:** thời gian từ lúc ứng dụng gọi gửi bản ghi đến khi producer nhận kết quả gửi thành công hoặc thất bại.
- **Broker request latency:** thời gian broker xử lý một request Kafka. Chỉ số này không đại diện cho toàn bộ thời gian một sự kiện đi qua hệ thống.
- **Consumer processing latency:** thời gian consumer nhận bản ghi và hoàn thành xử lý nghiệp vụ.
- **End-to-end latency:** thời gian từ lúc sự kiện được tạo ở nguồn đến lúc tác vụ đích hoàn tất.

Một phép đo chỉ hữu ích khi hai đầu của khoảng thời gian được xác định nhất quán. Chẳng hạn, đo thời gian producer nhận callback thành công không đồng nghĩa với đo thời gian đơn hàng đã được consumer ghi vào cơ sở dữ liệu. Nếu yêu cầu nghiệp vụ là “sự kiện phải xuất hiện ở hệ thống đích trong vòng hai giây”, cần đo đến lúc hệ thống đích xác nhận hoàn tất.

Latency thường được phân tích theo các phân vị thay vì chỉ dùng giá trị trung bình:

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Một nửa số phép đo có latency bằng hoặc thấp hơn giá trị này; thể hiện trải nghiệm điển hình |
| p95 | 95% số phép đo có latency bằng hoặc thấp hơn giá trị này; giúp thấy phần lớn các trường hợp chậm |
| p99 | 99% số phép đo có latency bằng hoặc thấp hơn giá trị này; nhạy với các đợt chậm kéo dài ở một phần nhỏ request |
| max | Giá trị lớn nhất quan sát được; hữu ích khi điều tra nhưng dễ bị chi phối bởi một ngoại lệ |

Ví dụ, p50 bằng 40 ms nhưng p99 bằng 2,5 giây cho thấy phần lớn sự kiện được xử lý nhanh, song vẫn có một nhóm nhỏ phải chờ rất lâu. Chỉ nhìn trung bình có thể bỏ qua vấn đề này. Khi đặt SLO, cần nêu rõ phân vị, khoảng thời gian đo và phạm vi sự kiện, ví dụ “p99 end-to-end dưới 1 giây trong cửa sổ 5 phút”.

## 3. Mối quan hệ giữa throughput và latency

Throughput và latency có liên hệ với nhau nhưng không thể thay thế cho nhau. Khi tải còn thấp, hệ thống có tài nguyên nhàn rỗi nên có thể xử lý bản ghi ngay. Khi tải tiến gần giới hạn, request phải chờ trong hàng đợi, producer phải chờ buffer, broker phải xếp lịch request và consumer phải chờ xử lý. Hàng đợi làm latency tăng nhanh khi năng lực phục vụ gần bão hòa.

Batching là ví dụ rõ về sự đánh đổi này. Producer gom nhiều bản ghi vào một batch giúp giảm số request và tăng hiệu quả truyền dữ liệu. Tuy nhiên, một bản ghi có thể phải đợi thêm để batch đủ lớn. Tăng `linger.ms` đôi khi cải thiện throughput và giảm chi phí request, nhưng cũng thêm thời gian chờ có chủ đích. Giảm `linger.ms` có thể giảm thời gian chờ khi tải thấp, song tạo nhiều batch nhỏ hơn khi tải cao.

Một quan hệ hữu ích khi phân tích hệ thống là định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số phần tử trung bình đang ở trong hệ thống hoặc đang chờ xử lý.
- `λ` là tốc độ hoàn thành trung bình, chẳng hạn records/s.
- `W` là thời gian trung bình một phần tử ở trong hệ thống, tính bằng giây.

Nếu một luồng xử lý hoàn tất 10.000 records/s và mỗi bản ghi ở trong hệ thống trung bình 0,1 giây, số bản ghi trung bình đang được xử lý hoặc chờ trong phạm vi đo xấp xỉ 1.000. Quan hệ này giúp ước lượng mức công việc đang tồn tại trong hệ thống; cần dùng cùng một ranh giới đo và trạng thái ổn định khi áp dụng.

Không nên tối ưu throughput bằng mọi giá. Nếu tăng batch hoặc số lượng request đồng thời làm p99 vượt SLO, thay đổi đó không phù hợp với yêu cầu nghiệp vụ. Ngược lại, nếu latency đang rất thấp nhưng CPU, mạng và broker còn nhiều dư địa, có thể tăng batching hoặc concurrency để tận dụng tài nguyên.

## 4. Latency hình thành ở đâu trong luồng Kafka?

Một sự kiện đi qua nhiều chặng trước khi hoàn tất. Sơ đồ dưới đây mô tả các khoảng thời gian thường cần tách riêng khi điều tra:

```text
Ứng dụng tạo sự kiện
        |
        v
Producer serialize và chờ batch/buffer
        |
        v
Gửi request qua mạng
        |
        v
Broker nhận, ghi log và xử lý replication
        |
        v
Consumer fetch bản ghi
        |
        v
Ứng dụng xử lý nghiệp vụ
        |
        v
Ghi kết quả / xác nhận offset
```

Tổng end-to-end latency có thể được phân tích thành thời gian ở các chặng trên, nhưng cần tránh cộng các chỉ số đo chồng lấn. Ví dụ, thời gian producer chờ callback có thể bao gồm thời gian mạng và broker xử lý; không được cộng thêm toàn bộ các khoảng đó lần nữa nếu chúng đã nằm trong phép đo producer.

Các nguồn gây chậm phổ biến gồm:

1. **Ứng dụng producer:** serialize JSON hoặc Avro tốn CPU, tạo payload lớn, thread gửi bị nghẽn, buffer cạn hoặc chờ metadata.
2. **Mạng:** độ trễ giữa ứng dụng và broker, băng thông bão hòa, retransmission hoặc kết nối không ổn định.
3. **Broker:** request queue tăng, CPU bận, xử lý TLS hoặc compression tốn tài nguyên, ghi đĩa chậm, replication bị chậm hoặc leader phân bố không đều.
4. **Consumer:** fetch chờ đủ dữ liệu, số consumer hoạt động thấp, xử lý nghiệp vụ chậm, gọi dịch vụ ngoài lâu hoặc commit offset không phù hợp.
5. **Hệ thống phụ trợ:** cơ sở dữ liệu, HTTP service, cache hoặc lock trong ứng dụng trở thành nút thắt sau khi consumer đã fetch dữ liệu.

## 5. Các yếu tố ảnh hưởng đến throughput và latency

### 5.1. Producer và batching

Kafka producer gửi bản ghi theo batch cho từng partition. Một batch lớn hơn thường giúp giảm số request trên mỗi bản ghi, tăng hiệu quả nén và tận dụng băng thông tốt hơn. Các cấu hình thường được xem xét gồm:

| Cấu hình | Tác động chính | Điều cần cân nhắc |
|---|---|---|
| `batch.size` | Giới hạn kích thước batch theo byte | Batch quá nhỏ làm tăng request; batch quá lớn có thể tăng bộ nhớ sử dụng và thời gian chờ gom dữ liệu |
| `linger.ms` | Thời gian producer có thể chờ thêm dữ liệu để gom batch | Giá trị lớn hơn có thể tăng hiệu quả batch nhưng thêm latency, nhất là khi tải thấp |
| `buffer.memory` | Dung lượng bộ nhớ producer dành cho bản ghi đang chờ gửi | Buffer nhỏ dễ gây chờ; tăng buffer không giải quyết được broker hoặc mạng đang thiếu năng lực |
| `compression.type` | Nén batch trước khi truyền | Giảm bytes qua mạng và dung lượng log; đổi lại tiêu thụ CPU và phụ thuộc đặc điểm dữ liệu |

Compression có lợi nhất khi payload có tính lặp hoặc cấu trúc dễ nén. Dữ liệu đã nén hoặc có entropy cao có thể không giảm nhiều kích thước. Hãy đo cả bytes truyền, CPU producer/broker và latency trước khi chọn codec. Codec cần được hỗ trợ bởi phiên bản client và broker đang dùng.

Producer gửi bất đồng bộ cho phép ứng dụng tiếp tục làm việc trong khi request đang được xử lý. Tuy nhiên, ứng dụng phải quan sát callback hoặc kết quả future để phát hiện lỗi gửi. Bỏ qua kết quả gửi có thể khiến throughput nhìn bề ngoài cao nhưng dữ liệu thực tế bị thất lạc hoặc lỗi không được xử lý.

Nếu producer hết buffer, các lời gọi gửi có thể phải chờ cho đến khi có chỗ trống hoặc hết `max.block.ms`. Hãy theo dõi buffer còn trống, thời gian chờ buffer và lỗi timeout. Tăng `buffer.memory` chỉ giúp hấp thụ burst ngắn; nếu tốc độ gửi dài hạn cao hơn tốc độ broker tiếp nhận, hàng đợi vẫn tiếp tục tăng.

### 5.2. Partition và phân bố key

Partition tạo khả năng xử lý song song. Producer có thể ghi vào nhiều partition và consumer group có thể phân công các partition cho nhiều consumer. Tuy nhiên, tổng số partition không tự động chuyển thành throughput cao nếu tài nguyên broker, mạng hoặc ứng dụng đã bão hòa.

Key quyết định cách bản ghi được phân phối theo partition khi dùng partitioner mặc định. Các bản ghi có cùng key thường đi vào cùng partition, giúp giữ thứ tự theo key trong phạm vi partition. Nếu một key xuất hiện quá thường xuyên, partition tương ứng có thể trở thành **hot partition**: một consumer phải xử lý phần lớn dữ liệu trong khi các consumer khác nhàn rỗi.

Khi xem xét tăng partition, cần cân nhắc:

- Số consumer tối đa có thể hoạt động song song trong một group bị giới hạn bởi số partition được gán cho group đó.
- Tăng partition có thể tăng khả năng phân tán tải, nhưng cũng tăng metadata, chi phí quản lý, số log segment và công việc replication.
- Thay đổi số partition của topic có thể làm thay đổi cách key được ánh xạ vào partition trong tương lai; cần xem xét yêu cầu ordering và cách ứng dụng dựa vào partition.
- Cần phân bố leader và replica hợp lý giữa các broker. Nhiều partition nhưng leader tập trung vào một broker vẫn tạo điểm nghẽn.

Hãy kiểm tra lưu lượng theo từng partition thay vì chỉ nhìn tổng topic. Chênh lệch lớn giữa partition có thể là dấu hiệu key skew hoặc phân bố leader không đều.

### 5.3. Broker, đĩa và replication

Broker nhận request, ghi dữ liệu vào log và phục vụ fetch request. Throughput bị giới hạn bởi nhiều tài nguyên phối hợp:

- **Network:** bytes vào/ra, tốc độ kết nối giữa broker và giữa client với broker.
- **Disk:** khả năng ghi, đọc và duy trì log segment; Kafka tận dụng page cache của hệ điều hành nên cần theo dõi cả áp lực bộ nhớ và hoạt động đĩa.
- **CPU:** xử lý request, TLS, compression/decompression, checksum và các tác vụ nền.
- **Replication:** leader truyền dữ liệu đến follower; replication traffic dùng chung tài nguyên mạng và có thể ảnh hưởng khả năng phục vụ client.
- **Phân bố tải:** leader, partition và replica cần được phân bố hợp lý giữa các broker.

`acks` ảnh hưởng đến thời điểm producer nhận xác nhận. Với `acks=0`, producer không chờ broker xác nhận; với `acks=1`, leader xác nhận sau khi ghi vào log cục bộ; với `acks=all`, leader chờ các replica đang thuộc ISR đáp ứng điều kiện xác nhận. Cấu hình `acks=all` thường được kết hợp với replication factor và `min.insync.replicas` phù hợp để tăng độ bền dữ liệu. Đổi lại, thời gian xác nhận có thể tăng và việc thiếu replica trong ISR có thể làm producer không gửi được khi yêu cầu ghi không còn thỏa mãn.

Không nên giảm mức xác nhận chỉ để cải thiện latency khi chưa đánh giá rủi ro mất dữ liệu. Chọn `acks`, replication factor và `min.insync.replicas` theo yêu cầu durability, sau đó đo hiệu năng với chính cấu hình vận hành đó.

### 5.4. Consumer fetch và xử lý song song

Consumer fetch dữ liệu theo request. Một số cấu hình quan trọng:

| Cấu hình | Tác động |
|---|---|
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch response; tăng có thể giảm số request nhưng làm consumer chờ lâu hơn khi lưu lượng thấp |
| `fetch.max.wait.ms` | Thời gian tối đa broker chờ để đáp ứng điều kiện fetch tối thiểu; cần cân bằng với latency mục tiêu |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition trong một request |
| `fetch.max.bytes` | Giới hạn tổng dữ liệu fetch trong một request, với các quy tắc xử lý batch lớn của Kafka |
| `max.poll.records` | Số bản ghi tối đa trả về trong một lần `poll`; ảnh hưởng khối lượng ứng dụng phải xử lý giữa các lần poll |

Tăng `fetch.min.bytes` có thể cải thiện hiệu quả khi lưu lượng cao và liên tục, nhưng với topic ít bản ghi, consumer có thể phải đợi đến `fetch.max.wait.ms`. Vì vậy, cấu hình phù hợp cho luồng telemetry lớn có thể không phù hợp với luồng thông báo cần phản hồi nhanh.

Trong Spring Kafka, `concurrency` của listener container tạo các consumer chạy song song. Một consumer group không thể có nhiều consumer đang được gán cùng một partition tại cùng thời điểm. Nếu topic có 8 partition và listener có concurrency 12, tối đa 8 consumer trong group có thể nhận partition của topic đó; các consumer dư không tạo thêm năng lực tiêu thụ cho topic này.

Concurrency chỉ có ích khi có đủ partition và phần xử lý phía sau chịu được tải tăng. Nếu consumer gọi chung một cơ sở dữ liệu đã bão hòa, tăng concurrency có thể làm connection pool cạn, tăng lock contention và khiến latency xấu hơn.

### 5.5. Xử lý nghiệp vụ và commit offset

Sau khi fetch, consumer còn phải deserialize, kiểm tra dữ liệu, gọi dịch vụ hoặc ghi cơ sở dữ liệu. Đây thường là phần chi phối end-to-end latency trong hệ thống nghiệp vụ.

Một listener xử lý tuần tự từng bản ghi có thể đạt throughput thấp nếu mỗi bản ghi phải chờ một lời gọi I/O chậm. Có thể cải thiện bằng cách gom thao tác phù hợp thành batch, dùng I/O bất đồng bộ có giới hạn hoặc tối ưu truy vấn đích. Cần giữ giới hạn concurrency và cơ chế backpressure để không làm quá tải hệ thống phụ trợ.

`max.poll.records` cần được chọn dựa trên thời gian xử lý thực tế. Nếu một lần poll trả về quá nhiều bản ghi và ứng dụng xử lý quá lâu trước lần poll tiếp theo, consumer có thể vượt `max.poll.interval.ms` và bị xem là không còn hoạt động trong group. Nếu giá trị quá thấp, ứng dụng có thể tạo nhiều vòng poll và tăng overhead. Hãy đo thời gian xử lý một poll và điều chỉnh cùng với timeout liên quan.

Commit offset cũng có chi phí và liên quan đến ngữ nghĩa giao nhận. Commit quá thường xuyên có thể tăng request và ảnh hưởng throughput; commit quá thưa có thể làm tăng lượng công việc phải xử lý lại sau sự cố. Chọn ack mode và thời điểm commit dựa trên yêu cầu at-least-once, xử lý idempotent và khả năng chấp nhận duplicate. Không được commit offset trước khi tác vụ nghiệp vụ cần bảo đảm đã hoàn tất nếu điều đó có thể khiến bản ghi bị bỏ qua sau sự cố.

## 6. Đo lường đúng trước khi tối ưu

Trước khi thay đổi cấu hình, hãy thiết lập baseline trong điều kiện tải có thể lặp lại. Một baseline tốt cần ghi nhận:

- Tốc độ producer theo records/s và bytes/s.
- Tốc độ consumer hoàn tất xử lý theo records/s và bytes/s.
- End-to-end latency ở p50, p95 và p99.
- Consumer lag theo partition và xu hướng tăng/giảm của lag.
- CPU, heap, garbage collection, network và disk trên ứng dụng lẫn broker.
- Tỷ lệ lỗi, retry, timeout, rebalance và số bản ghi xử lý lại.
- Cấu hình topic: partition count, replication factor, `min.insync.replicas`, retention và phân bố leader.

### 6.1. Đo end-to-end latency

Một cách phổ biến là ghi timestamp tạo sự kiện vào payload hoặc header, sau đó consumer ghi nhận thời điểm hoàn tất xử lý. Latency của bản ghi được tính bằng:

\[
\text{end-to-end latency} = t_{\text{completed}} - t_{\text{created}}
\]

Hai thời điểm cần dùng đồng hồ có độ đồng bộ phù hợp giữa các máy. Nếu clock lệch, phép trừ có thể cho kết quả âm hoặc sai lệch. Với phép đo nội bộ trong cùng một tiến trình, monotonic clock phù hợp để đo khoảng thời gian; với timestamp đi qua nhiều máy, cần đồng bộ thời gian và hiểu sai số đo.

Timestamp của Kafka record như `CreateTime` hoặc `LogAppendTime` có ý nghĩa riêng và không mặc nhiên là thời điểm nghiệp vụ hoàn tất. Hãy chọn nguồn timestamp đúng với SLO đang theo dõi.

### 6.2. Theo dõi producer

Các nhóm metric hữu ích của producer gồm:

- Tốc độ gửi bản ghi và byte.
- Số bản ghi trung bình trong mỗi request/batch.
- Request latency và thời gian chờ gửi.
- Buffer còn trống, thời gian chờ buffer và số lần cạn buffer.
- Tỷ lệ lỗi gửi, retry, timeout và record bị từ chối.

Nếu `records-per-request` thấp trong khi request rate cao, batching có thể chưa hiệu quả. Nếu buffer wait tăng, producer đang tạo dữ liệu nhanh hơn khả năng giải phóng buffer hoặc có vấn đề kết nối/request. Nếu retry và timeout tăng đồng thời với broker request latency, cần điều tra broker hoặc mạng trước khi tăng buffer.

### 6.3. Theo dõi broker

Theo dõi bytes in/out, request rate, thời gian chờ trong request queue, thời gian xử lý request, mức nhàn rỗi của network processor và request handler, CPU, disk I/O, network và tình trạng replication. Các metric JMX cụ thể có thể thay đổi tên hoặc cách biểu diễn theo phiên bản Kafka và hệ thống giám sát.

Những tín hiệu cần chú ý gồm:

- Request queue tăng trong khi request handler hoặc network processor ngày càng ít thời gian nhàn rỗi.
- Bytes in/out tiến sát giới hạn mạng của máy hoặc hạ tầng.
- Disk latency tăng hoặc page cache chịu áp lực lớn.
- Under-replicated partitions xuất hiện hoặc tăng kéo dài.
- Leader phân bố lệch khiến một broker chịu tải cao hơn rõ rệt các broker khác.

### 6.4. Theo dõi consumer

Theo dõi records consumed/s, fetch rate, fetch latency, lag theo partition, thời gian xử lý listener, thời gian commit và số lần rebalance. Consumer lag là chênh lệch giữa vị trí log hiện tại và vị trí consumer group đã commit/đọc, tùy metric và cách công cụ biểu diễn.

Lag là chỉ báo backlog, không phải phép đo trực tiếp end-to-end latency. Một consumer có thể có lag bằng 0 ở thời điểm kiểm tra nhưng từng bản ghi vẫn mất nhiều thời gian xử lý. Ngược lại, lag có thể tăng tạm thời trong một burst nhưng consumer nhanh chóng bắt kịp. Hãy xem cả giá trị lag, tốc độ thay đổi lag và thời gian thực tế của bản ghi.

## 7. Quy trình tối ưu có kiểm soát

Tối ưu throughput và latency nên tiến hành theo từng bước để biết thay đổi nào tạo ra kết quả. Một quy trình thực tế:

1. **Xác định mục tiêu.** Ghi rõ throughput cần đạt, p95/p99 latency tối đa, tỷ lệ lỗi cho phép và yêu cầu durability. Nêu rõ phép đo kết thúc ở producer acknowledgement, consumer completion hay hệ thống đích.
2. **Tạo tải đại diện.** Dùng payload có kích thước và phân bố key gần với production; giữ đúng replication, `acks`, TLS, compression và số producer/consumer dự kiến.
3. **Đo baseline.** Chạy đủ lâu để quan sát trạng thái ổn định, tách thời gian warm-up và ghi lại metric ở tất cả các chặng.
4. **Tìm nút thắt.** Xác định chặng có hàng đợi tăng, tài nguyên bão hòa hoặc latency bất thường. Kiểm tra theo partition để phát hiện hot partition.
5. **Thay đổi một nhóm nhỏ.** Ví dụ điều chỉnh batching producer, sau đó mới thay đổi fetch hoặc concurrency consumer. Không thay nhiều cấu hình cùng lúc vì khó xác định nguyên nhân kết quả.
6. **Chạy lại cùng kịch bản.** So sánh throughput, p95/p99, lag, lỗi và tài nguyên với baseline. Một thay đổi chỉ có lợi nếu cải thiện mục tiêu mà không vi phạm SLO hoặc yêu cầu độ bền.
7. **Kiểm tra khi có sự cố giả lập phù hợp.** Đánh giá hành vi khi một consumer dừng, một broker không khả dụng hoặc lưu lượng tăng đột biến trong môi trường kiểm thử.
8. **Triển khai theo dõi được.** Áp dụng thay đổi có kiểm soát, quan sát metric và chuẩn bị khả năng quay lại cấu hình trước nếu kết quả production khác thử nghiệm.

Tránh benchmark chỉ đo producer gửi được nhanh đến đâu trong khi không xác nhận dữ liệu đã được consumer xử lý. Bài đo cần có cùng ranh giới hoàn tất với yêu cầu thực tế.

## 8. Cấu hình tham khảo trong Spring Boot

Ví dụ sau minh họa một cấu hình khởi điểm để thử nghiệm batching producer và fetch consumer. Các con số chỉ là giá trị mẫu; cần hiệu chỉnh theo kích thước record, tải, phiên bản Kafka, số partition và SLO của hệ thống.

```yaml
spring:
  kafka:
    producer:
      acks: all
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        linger.ms: 5
    consumer:
      enable-auto-commit: false
      fetch-min-size: 65536
      fetch-max-wait: 50
      max-poll-records: 500
    listener:
      concurrency: 6
```

Ý nghĩa các lựa chọn trong ví dụ:

- `acks: all` yêu cầu xác nhận theo ISR hiện tại; cần cấu hình replication và `min.insync.replicas` phù hợp với yêu cầu durability.
- `batch-size` là kích thước batch theo byte. `linger.ms` cho producer thêm thời gian gom dữ liệu; 5 ms không phải giá trị tối ưu cho mọi luồng.
- `buffer-memory` là dung lượng buffer producer. Cần theo dõi buffer wait để biết có thực sự thiếu buffer hay không.
- `compression-type: lz4` là lựa chọn minh họa. Hãy benchmark codec trên dữ liệu thật và xác nhận tương thích phiên bản.
- `fetch-min-size` và `fetch-max-wait` điều khiển việc gom dữ liệu khi fetch. Tăng chúng có thể tăng hiệu quả truyền nhưng cũng tăng thời gian chờ.
- `max-poll-records` giới hạn số bản ghi trả về trong một lần poll; cần bảo đảm thời gian xử lý không khiến consumer vượt `max.poll.interval.ms`.
- `concurrency: 6` tạo tối đa sáu consumer trong listener container. Cần đủ partition được gán và đủ năng lực ở cơ sở dữ liệu/dịch vụ phía sau.

Nếu cần quan sát riêng một listener, có thể khai báo concurrency ngay trên `@KafkaListener`:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    concurrency = "6"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

Ví dụ này giả định `orderService.process` hoàn tất công việc cần thiết trước khi listener xác nhận xử lý theo ack mode đang dùng. Nếu phương thức thực hiện I/O chậm, hãy đo thời gian xử lý và kiểm tra connection pool, truy vấn cơ sở dữ liệu, lock và giới hạn dịch vụ. Tăng concurrency mà không kiểm tra các thành phần đó có thể chỉ chuyển điểm nghẽn sang hệ thống đích.

Khi dùng batch listener, ứng dụng có thể xử lý một nhóm bản ghi trong một lần gọi để giảm overhead hoặc tận dụng batch API của cơ sở dữ liệu. Cần thiết kế xử lý lỗi theo từng bản ghi hoặc theo batch một cách rõ ràng; một lỗi ở giữa batch có thể ảnh hưởng cách retry và commit offset.

## 9. Capacity planning và headroom

Capacity planning cần dựa trên tải bình thường, burst, tăng trưởng dự kiến và hành vi khi một thành phần mất khả năng phục vụ. Không nên lấy throughput cao nhất từng đo được làm công suất vận hành an toàn.

Giả sử hệ thống nhận trung bình 4.000 records/s, nhưng trong giờ cao điểm tăng lên 9.000 records/s. Consumer group cần duy trì tốc độ xử lý lớn hơn tốc độ đầu vào trong giai đoạn bình thường nếu muốn có khả năng bù backlog sau burst. Cần đo năng lực khi replication, TLS, compression và xử lý nghiệp vụ đều bật như production.

Khi consumer bị chậm, thời gian bắt kịp backlog phụ thuộc vào **tốc độ tiêu thụ vượt quá tốc độ sản xuất**, không chỉ vào tốc độ tiêu thụ tuyệt đối:

\[
\text{catch-up time} \approx \frac{\text{backlog}}{\text{consume rate} - \text{produce rate}}
\]

Công thức chỉ áp dụng khi tốc độ hai phía tương đối ổn định và consume rate lớn hơn produce rate. Ví dụ backlog là 1.500.000 records, consumer xử lý 12.000 records/s và producer vẫn gửi 4.000 records/s. Năng lực giảm backlog ròng là 8.000 records/s, do đó cần khoảng 187,5 giây để bắt kịp nếu các điều kiện giữ nguyên.

Khi lập kế hoạch, hãy đánh giá:

- Tải trung bình, đỉnh ngắn hạn và thời lượng burst.
- Kích thước record trung bình và phân bố kích thước lớn nhất.
- Tỷ lệ key và khả năng xuất hiện hot partition.
- Throughput cần thiết khi một broker hoặc consumer instance không hoạt động.
- Dung lượng mạng và đĩa dành cho replication, retention và lưu lượng client.
- Thời gian cho phép để xử lý backlog sau sự cố.
- Headroom cho tăng trưởng, rolling restart, rebalance và tác vụ bảo trì.

Headroom cần được xác định bằng thử nghiệm và mô hình tải của hệ thống. Nếu thiết kế chạy sát giới hạn đo được, một đợt burst hoặc một broker bị mất có thể khiến latency tăng mạnh và lag kéo dài.

## 10. Chẩn đoán triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Producer throughput thấp, buffer wait tăng | Broker nhận chậm, mạng nghẽn, buffer không đủ cho burst hoặc producer tạo request quá nhiều | Kiểm tra request latency, buffer metrics, broker/network; xem batch size và linger |
| Throughput tăng nhưng p99 tăng mạnh | Hàng đợi bắt đầu tích tụ, một partition bị nóng, broker hoặc dịch vụ đích gần bão hòa | Phân tích latency theo chặng, lag và metric theo partition; kiểm tra tài nguyên ở thời điểm p99 tăng |
| Consumer lag tăng liên tục | Consumer throughput thấp hơn producer throughput | So sánh records in/out, số partition, concurrency, thời gian listener và năng lực hệ thống phụ trợ |
| Một consumer bận, các consumer khác nhàn rỗi | Key skew hoặc phân bố partition không đều | Đo records/s từng partition và kiểm tra key; đánh giá lại chiến lược partitioning |
| Broker CPU cao nhưng disk còn rảnh | TLS, compression, request processing hoặc nhiều request nhỏ | Kiểm tra CPU theo tiến trình, request rate, batch efficiency và cấu hình compression |
| Network bão hòa | Record lớn, replication traffic cao hoặc bytes/request lớn | Kiểm tra bytes in/out, kích thước payload, compression và phân bố replica |
| Under-replicated partitions kéo dài | Follower không theo kịp leader, broker/mạng/đĩa có vấn đề | Kiểm tra replica fetch, broker health, disk và network; đánh giá ảnh hưởng đến `acks=all` |
| Consumer rebalance thường xuyên | Consumer mất heartbeat, xử lý một poll quá lâu, instance khởi động lại hoặc cấu hình timeout không phù hợp | Kiểm tra log rebalance, thời gian xử lý poll, `max.poll.interval.ms`, session và heartbeat |
| Lag thấp nhưng end-to-end latency cao | Phần xử lý nghiệp vụ chậm hoặc phép đo lag không phản ánh thời gian chờ thực | Đo timestamp từ lúc tạo sự kiện đến lúc hoàn tất, phân tách thời gian DB/API và commit |

Khi điều tra, hãy đối chiếu metric cùng mốc thời gian. Một biểu đồ CPU trung bình của cả ngày không giải thích được p99 tăng trong một phút; cần xem dữ liệu có độ phân giải đủ nhỏ quanh thời điểm sự cố.

## 11. Những sai lầm cần tránh

- **Chỉ đo records/s:** bỏ qua kích thước record, bytes/s, latency và tỷ lệ lỗi.
- **Chỉ nhìn latency trung bình:** che khuất các request chậm ở p95 hoặc p99.
- **Coi consumer lag là end-to-end latency:** lag mô tả backlog theo offset, không cho biết đầy đủ thời gian xử lý từng sự kiện.
- **Tăng partition theo cảm tính:** có thể làm tăng overhead mà không giải quyết được giới hạn CPU, mạng hoặc hệ thống đích.
- **Tăng concurrency không giới hạn:** có thể gây quá tải cơ sở dữ liệu, connection pool và dịch vụ downstream.
- **Tăng buffer để chữa nghẽn dài hạn:** buffer lớn chỉ trì hoãn thời điểm producer phải chờ nếu broker liên tục xử lý chậm hơn tốc độ gửi.
- **Giảm `acks` chỉ để giảm latency:** có thể làm suy giảm durability mà không giải quyết nguyên nhân chính.
- **Benchmark khác production:** tải thử không có replication, TLS, compression, key skew hoặc xử lý nghiệp vụ sẽ cho kết quả lạc quan sai lệch.
- **Thay nhiều cấu hình cùng lúc:** làm mất khả năng xác định thay đổi nào tạo ra cải thiện hoặc hồi quy.
- **Bỏ qua lỗi gửi và retry:** throughput đo ở phía ứng dụng có thể không phản ánh số bản ghi được xử lý thành công.

## 12. Checklist vận hành

Khi đánh giá một thay đổi liên quan đến throughput hoặc latency, hãy xác nhận các điểm sau:

- [ ] Đã định nghĩa rõ throughput ở producer, broker, consumer hay nghiệp vụ.
- [ ] Đã định nghĩa điểm bắt đầu và kết thúc của latency; có p50, p95 và p99.
- [ ] Đã đo records/s và bytes/s với kích thước record gần production.
- [ ] Đã kiểm tra lag và tốc độ thay đổi lag theo từng partition.
- [ ] Đã theo dõi CPU, memory/GC, network, disk và replication.
- [ ] Đã kiểm tra phân bố key, partition và leader để phát hiện tải lệch.
- [ ] Đã kiểm tra thời gian xử lý listener, commit và các dịch vụ downstream.
- [ ] Đã thử nghiệm với cấu hình durability thực tế, bao gồm `acks`, replication factor và `min.insync.replicas`.
- [ ] Đã thay đổi từng nhóm cấu hình và chạy lại cùng kịch bản để so sánh.
- [ ] Đã xác nhận throughput đạt mục tiêu mà p95/p99, lỗi và yêu cầu độ bền vẫn trong giới hạn.
- [ ] Đã tính thời gian catch-up khi có backlog và xác định headroom cho burst hoặc sự cố.

Throughput cho biết hệ thống có thể xử lý bao nhiêu dữ liệu; latency cho biết dữ liệu phải chờ bao lâu. Trong Spring Kafka, cả hai chịu ảnh hưởng đồng thời từ batching, partitioning, broker, replication, fetch, concurrency và xử lý nghiệp vụ. Đo theo từng chặng, quan sát phân vị latency và thử nghiệm với tải đại diện giúp xác định đúng nút thắt, từ đó điều chỉnh cấu hình mà vẫn giữ được độ bền dữ liệu và khả năng vận hành ổn định.
