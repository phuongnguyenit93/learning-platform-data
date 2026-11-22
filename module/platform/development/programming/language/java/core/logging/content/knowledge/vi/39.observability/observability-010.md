# SLO cho pipeline log trong Java: đo độ tin cậy từ sự kiện đến nơi lưu

## 1. SLO cho pipeline log là gì và tại sao cần?

**Service Level Objective (SLO)** là mục tiêu định lượng về chất lượng một dịch vụ trong một khoảng thời gian xác định. Với pipeline logging, SLO giúp trả lời một câu hỏi thực tế: **“Trong những sự kiện log mà hệ thống cam kết thu thập, bao nhiêu sự kiện đến được nơi cần thiết, đúng hạn và còn đủ thông tin để sử dụng?”**

Một câu lệnh Java như `logger.info("Order {}", orderId)` hoàn thành **không có nghĩa** log đã được ghi vào file, được agent gửi, được collector nhận, được index để truy vấn hoặc được lưu bền vững. Khi appender bất đồng bộ, còn một queue giữa thread ứng dụng và sink. Khi collector chậm hoặc mất kết nối, người vận hành có thể vẫn thấy ứng dụng trả request thành công nhưng thông tin cần để điều tra đã bị mất.

Ví dụ pipeline:

```text
Java service -> SLF4J/JUL -> logger level/filter -> appender
                                              |
                                              v
                                  async queue / stdout / file
                                              |
                                              v
                                      log agent / forwarder
                                              |
                                              v
                                     transport + retry
                                              |
                                              v
                                       collector/ingest
                                              |
                                              v
                                  durable storage + index
                                              |
                                              v
                                     dashboard / alert
```

Mỗi chặng có thể trở thành điểm mất hoặc chậm log:

- Sự kiện bị filter hoặc sampling ngay trong JVM.
- Async queue đầy rồi bỏ event theo chính sách.
- stdout/file không ghi được, hoặc volume/pipe bị nghẽn.
- Agent mất kết nối, backlog hoặc disk spool hết chỗ.
- Collector trả 429/5xx hoặc xác nhận nhận nhưng indexing chậm.
- Event đã lưu nhưng không truy vấn được do schema/parser, retention, quyền truy cập hoặc sai time range.

**SLO không phải là một dashboard CPU/heap của ứng dụng.** Nó đo một kết quả hữu ích của đường logging, với đối tượng, điểm bắt đầu, điểm kết thúc, deadline và cách đếm được định nghĩa trước.

Bài này phân biệt **SLI**, **SLO**, **SLA**, **error budget**, cách đo end-to-end và cách triển khai kiểm thử bằng Java 17. Các phần trăm và ngưỡng dưới đây là **giá trị minh họa để học và thiết kế**, không phải tiêu chuẩn mặc định bắt buộc cho mọi hệ thống.

## 2. SLI, SLO, SLA và error budget

| Thuật ngữ | Ý nghĩa | Ví dụ cho logging |
| --- | --- | --- |
| **SLI (Service Level Indicator)** | Tỷ số/đại lượng đo chất lượng thực tế | Tỷ lệ event có thể truy vấn trong 30 giây |
| **SLO (Service Level Objective)** | Mục tiêu đặt lên SLI trong cửa sổ đo | Ít nhất 99,95% event quan trọng đạt deadline trong 30 ngày |
| **SLA (Service Level Agreement)** | Cam kết/hợp đồng với hậu quả khi vi phạm | Cam kết pháp lý/thương mại nếu có, không đồng nghĩa SLO nội bộ |
| **Error budget** | Phần tỷ lệ/số sự kiện được phép không đạt SLO | Với 99,95%, ngân sách lỗi 0,05% của mẫu đủ điều kiện |
| **Burn rate** | Tốc độ tiêu thụ budget so với tốc độ cho phép | Burn 2x nghĩa lỗi đang đến gấp đôi tốc độ ngân sách theo định nghĩa đo |

SLO tốt không chỉ ghi `99.9% uptime` mà cần nói **cái gì được coi là một lần thành công**. Một agent “UP” nhưng không gửi được log vẫn có thể làm mất giá trị pipeline.

**Phân biệt availability của thành phần và outcome của pipeline:** Kafka broker, Logback appender, Fluent Bit/Vector, collector và dashboard đều có thể đang “healthy” riêng lẻ nhưng event đã bị discard giữa các chặng. End-to-end SLI phải có ít nhất một phương pháp quan sát kết quả phía sau cùng.

## 3. Chọn đối tượng đo: event nào thực sự “eligible”?

Không phải mọi `TRACE`/`DEBUG` đều nên được kỳ vọng lưu đủ 100%. Một số ứng dụng chủ động sampling hoặc drop log ít quan trọng để tiết kiệm tài nguyên. Vì vậy, định nghĩa **eligible event** trước khi tính SLI.

Ví dụ các lớp:

| Lớp | Chính sách điển hình | Gợi ý SLO |
| --- | --- | --- |
| **Audit bắt buộc** | Không chủ động discard; có hợp đồng lưu/đối soát | SLO riêng, rất nghiêm và có kiểm tra độ bền |
| **Security event quan trọng** | Cần điều tra, giữ event ID/actor/action an toàn | Độ đầy đủ và độ trễ riêng |
| **Operational log quan trọng** | `ERROR`, event trạng thái critical service | Mục tiêu end-to-end và freshness |
| **INFO thông thường** | Có thể có rate-limit theo thiết kế | SLO theo mẫu đã định nghĩa |
| **DEBUG/TRACE được sampling** | Chỉ một phần event đủ điều kiện đi tiếp | Không đo như “mất” mọi event bị sampling có chủ đích |

Ví dụ hợp đồng:

> Tất cả event ở lớp `critical` **đã được ứng dụng chấp nhận để gửi vào pipeline theo policy** phải có record hợp lệ và có thể truy vấn trong tối đa 30 giây, với tỷ lệ ít nhất 99,95% trên cửa sổ 30 ngày.

Nhưng ví dụ trên còn một rủi ro: nếu chính logger/filter bị vô hiệu hóa trước điểm đánh dấu “đã được chấp nhận”, denominator có thể **bỏ qua tất cả event đã mất ngay tại nguồn**. Với audit quan trọng, nên đếm **sự kiện nghiệp vụ phải phát log từ nguồn dữ liệu đáng tin cậy**, chẳng hạn event/outbox đã commit, không chỉ từ bộ đếm của appender.

### Một định nghĩa eligible có thể kiểm chứng

```text
Eligible(event) =
    thuộc nhóm cần giữ theo chính sách
    AND đã xảy ra mốc phát sinh nghiệp vụ được định nghĩa
    AND không thuộc trường hợp miễn trừ được phê duyệt
```

Mọi exemption như maintenance, sampling hoặc dữ liệu thử nghiệm phải được mô tả rõ, đo được và được duyệt trước. **Không loại sự kiện bị mất ra khỏi denominator chỉ vì “không thấy ở collector”**; làm vậy SLI sẽ trông đẹp giả tạo.

### Theo dõi thay đổi chính sách

Khi triển khai thêm filter, chỉnh log level, đổi sampling hoặc thay retention, tập eligible có thể đổi. Cần ghi version chính sách và ngày có hiệu lực để so SLI qua các giai đoạn. Không so trực tiếp tháng này với tháng trước nếu mẫu đo đã đổi nhưng báo cáo không giải thích.

## 4. Định nghĩa điểm bắt đầu, điểm kết thúc và deadline

Tỷ lệ giao log đúng hạn chỉ có ý nghĩa khi **bắt đầu tính từ đâu, giao đến đâu** được xác định rõ.

Một ví dụ:

- **`t0`**: thời điểm sự kiện nguồn được tạo/commit theo hợp đồng.
- **`t1`**: thời điểm collector ghi event vào nơi lưu có thể truy vấn được và có xác nhận theo hợp đồng.
- **Deadline**: `t1 - t0 <= 30 giây`.
- **Good event**: đúng ID, đúng lớp, hợp lệ schema, có thể truy vấn trước deadline.
- **Bad event**: không có record tới deadline, record đến muộn, hoặc record không đạt điều kiện hợp lệ đã được thống nhất.

Nếu chỉ đo lúc agent gọi `send()`, event có thể chưa đến collector. Nếu chỉ đo lúc collector trả HTTP 200, việc indexing hoặc lưu bền vững có thể vẫn xảy ra sau đó. Nếu chỉ đo khi dashboard hiển thị, kết quả chịu ảnh hưởng hệ thống truy vấn. **Chọn một mốc cuối tương ứng đúng điều người dùng/đội vận hành cần.**

### Bảng các “điểm kết thúc” khác nhau

| Mốc đích | Có thể khẳng định | Chưa được bảo đảm |
| --- | --- | --- |
| Java logger call returned | Lời gọi API logging đã hoàn thành | Event không bị filter, tới file hoặc collector |
| Appender accepted | Appender nhận event | Có thể chỉ nằm trong RAM |
| Async queue enqueued | Worker có thể tiêu thụ sau | Không mất khi JVM crash |
| Agent sent bytes | Đã thử truyền dữ liệu | Collector đã lưu hoặc index |
| Collector ack | Đã đạt phạm vi xác nhận của protocol | Ack đó có bảo đảm durable hay queryable không |
| Durable/indexed/queryable | Event tồn tại theo hợp đồng lưu/truy vấn | Sẽ tồn tại mãi sau khi retention hết hạn |

Với event audit, nếu yêu cầu là “bằng chứng phải còn sau crash”, một ACK chấp nhận queue trong bộ nhớ là mốc quá yếu. Nếu requirement chỉ là “dashboard hiển thị trong 30 giây”, một metric `appender_writes_total` cũng chưa đủ.

### Chú ý thời gian

Để so thời gian trên hai host, cần cơ chế đồng bộ đồng hồ và hiểu clock skew. Một `t1 < t0` do lệch đồng hồ **không được tính thành độ trễ âm tức là siêu nhanh**. Có thể phân loại `INVALID_TIMESTAMP` và báo chất lượng đo; trong SLI chặt chẽ, xem như không đạt cho đến khi có dữ liệu xác minh khác. Trong cùng process, dùng clock monotonic để đo elapsed khi có thể; với end-to-end nhiều host, cần timestamp đáng tin cậy cùng định nghĩa.

## 5. Những SLI nên cân nhắc cho pipeline log

Không nên gom mọi nhu cầu vào một tỷ số “logging healthy” mơ hồ. Có thể bắt đầu bằng các SLI sau.

### 5.1. Completeness / delivery success

```text
delivery_success_rate =
    số eligible event có mặt hợp lệ tại mốc đích đúng yêu cầu
    ---------------------------------------------------------
                 tổng eligible event
```

Chọn **mốc kết quả**: đã lưu, đã index, hoặc có thể truy vấn. Nếu target không yêu cầu deadline, đây là tỷ lệ cuối cùng trong một giới hạn kết thúc/reconciliation có quy định. Khi event trễ chưa đến mốc kết thúc, không được vô thời hạn giữ chúng “pending” để làm đẹp mẫu số.

### 5.2. Timely delivery / freshness

```text
on_time_delivery_rate =
    số eligible event hợp lệ đến mốc đích trước deadline
    ------------------------------------------------------
                    tổng eligible event
```

Đây thường là SLI thực dụng nhất: vừa phạt **mất log**, vừa phạt **log đến quá muộn**. Nếu chỉ tính latency p99 trên các event đã giao, 20% event mất hoàn toàn vẫn không hiện trong percentile — vì những event mất không có latency quan sát được.

Có thể đặt một SLO riêng cho `p99 ingest latency` như tín hiệu chẩn đoán, nhưng **không thay SLO completeness/on-time** bằng percentile chỉ của event thành công.

### 5.3. Parseability / schema correctness

```text
parse_success_rate =
    số event tới sink và parse đúng schema bắt buộc
    ------------------------------------------------
             tổng event tới sink đã kiểm tra
```

Tỷ lệ này cho biết chất lượng format của các event đã đến; **không đo được sự kiện hoàn toàn không đến nơi**. Nếu mục tiêu sản phẩm là “99,95% event eligible có thể truy vấn theo `reasonCode`”, hãy đưa cả mất event và lỗi schema vào numerator/denominator end-to-end, không dùng `parse_success_rate` độc lập để tuyên bố đã đạt.

### 5.4. Duplicate rate / integrity

```text
duplicate_delivery_rate =
    số bản sao dư của event ID đã xác định
    ---------------------------------------
          tổng bản sao event đã nhận
```

Tỷ lệ trùng có thể được đo riêng. Retry với at-least-once có thể tạo bản sao hợp lệ theo cơ chế giao nhận; hệ thống cần dedup ở điểm truy vấn hoặc consumer, và hiểu một `eventId` có thể xuất hiện nhiều bản sao. **Đừng coi mỗi bản sao là một event nguồn mới** khi tính completeness. Nhưng cũng đừng bỏ qua duplicate nếu làm tăng chi phí hoặc khiến kết quả audit đếm hai lần.

### 5.5. End-to-end canary success

Phát một event **synthetic có ID duy nhất** từ điểm nguồn được chọn, rồi kiểm tra query/ack ở cuối pipeline. Ví dụ canary mỗi phút, timeout 30 giây:

```text
canary_success_rate =
    số canary có thể tìm thấy trong deadline
    ----------------------------------------
                 tổng canary đã phát
```

Canary rất hữu ích để phát hiện outage **ngay cả khi traffic thật thấp**, nhưng chỉ phản ánh đúng đường mà canary đi qua. Nếu canary xuất phát từ agent thay vì từ JVM, nó không phát hiện logger/filter/async queue của ứng dụng hỏng. Nếu canary được ưu tiên khác với event thật, nó có thể đẹp trong khi dữ liệu thực bị drop. **Canary là SLI bổ trợ, không phải bằng chứng duy nhất cho độ đầy đủ toàn bộ log.**

## 6. Ví dụ SLO theo từng nhóm log

Giả sử một công ty định nghĩa các mục tiêu thử nghiệm như sau:

| Nhóm | SLI | Target minh họa | Cửa sổ |
| --- | --- | --- | --- |
| Critical operational logs | Event hợp lệ, queryable trong 30 giây | ≥ 99,95% | Rolling 30 ngày |
| Security events | Event đúng schema, có thể truy vấn trong 60 giây | ≥ 99,99% | Rolling 30 ngày |
| Log pipeline canary | Canary từ JVM queryable trong 30 giây | ≥ 99,90% | Rolling 7 ngày |
| General INFO | Event được giữ theo policy và tìm thấy trong 2 phút | ≥ 99,0% | Rolling 30 ngày |

**Đây không phải mục tiêu khuyến nghị mặc định.** Target phải dựa trên độ quan trọng, nhu cầu điều tra, nghĩa vụ lưu giữ, tải, lưu lượng, chi phí, thiết kế hạ tầng và khả năng đo. Sự kiện audit bắt buộc có thể cần **cam kết chức năng mạnh hơn SLO tỷ lệ**, ví dụ transaction/outbox, không cho phép mất dù xác suất nhỏ.

SLO có thể bao gồm **nhiều điều kiện đồng thời**:

- `eventId` không trùng sai ngữ nghĩa.
- Có thể truy vấn trong thời gian quy định.
- Không mất trường `service`, `action`, `outcome`, `reasonCode` quan trọng.
- Không có secret trong dữ liệu được phép truy cập rộng (yêu cầu bảo mật phải kiểm tra riêng, không quy mọi thứ về một tỷ lệ).

Cần tránh lấy trung bình chung nhiều lớp và che khuất lỗi của lớp nhỏ nhưng quan trọng. Ví dụ 1 triệu INFO giao tốt không bù được 10 event audit bị mất.

## 7. Error budget: tính đúng chứ không chỉ ghi mục tiêu

Giả sử SLO là **99,95% event đúng hạn** trong cửa sổ đã chọn.

```text
error_budget_fraction = 1 - 0,9995 = 0,0005 = 0,05%
```

Nếu cửa sổ có **10.000 eligible events** đã đủ thời gian để phân loại:

- Tối đa **5 event không đạt** tương ứng 0,05%.
- Nếu **9.990 event đúng hạn**, **7 event đến muộn** và **3 event không tìm thấy**, tổng không đạt là **10**.
- SLI đúng hạn là `9990 / 10000 = 99,90%`.
- Error budget cho phép là 5 event nhưng thực tế có 10 event không đạt → **đã dùng 200% budget**, tức vượt mục tiêu.
- Burn rate trên cửa sổ quan sát là `(10/10000) / (1-0,9995) = 2x`.

Với volume không chia hết hoặc mẫu quá nhỏ, “số lỗi cho phép” là khái niệm cần quản lý quy tắc làm tròn và cách đánh giá tỷ số. **Ưu tiên đánh giá trực tiếp tỷ lệ SLI với target**, không lấy một phép `floor` thiếu giải thích rồi đổi semantics của SLO. Cửa sổ có 0 eligible events phải được phân loại **no data**, không tự động báo 100% thành công.

### Burn rate không phải số giờ còn lại cố định

`burn_rate = observed_bad_fraction / allowed_bad_fraction`.

- `burn=1x`: ở mức tốc độ lỗi đúng bằng tỷ lệ budget cho phép trong cửa sổ đang đo.
- `burn=2x`: tốc độ lỗi cao gấp đôi mức cho phép.
- `burn≫1x`: lỗi đang tiêu thụ budget nhanh, có thể cần xử lý khẩn cấp nếu số mẫu đủ và tác động lớn.

Burn rate phụ thuộc **cửa sổ đo**. Một khoảng 5 phút có 1 lỗi trên 10 event tạo tỷ lệ cao nhưng mẫu nhỏ; cần đánh giá cùng cửa sổ dài hơn, volume và ý nghĩa nhóm log. Không tự suy ra “còn X giờ” nếu không biết lịch sử budget, traffic và thời gian cửa sổ.

## 8. Đo end-to-end không thể chỉ đếm ở collector

Một lỗi logic phổ biến:

```text
collector_received_total / collector_received_total = 100%
```

hoặc đếm mẫu số là “mọi log mà collector nhìn thấy”. Cách này **không thể phát hiện event mất trước collector**, vì cả numerator và denominator cùng không thấy chúng.

Một kiến trúc đo khả thi cần **nguồn dữ liệu độc lập**:

```text
Business source / outbox
     |
     +-- source event ID + expected timestamp --> SLI reconciler
     |
     v
Application logger / agent / collector
                                    |
                                    v
                         indexed event IDs
                                    |
                                    v
                    reconciliation + deadline
                                    |
                                    v
                  metrics / SLO / alert
```

Với event có ID và giữ toàn bộ, bộ đối soát kiểm tra mỗi ID đã commit ở source có tồn tại tại sink hợp lệ và đến đúng deadline không. Nếu một event bị mất trước appender, bộ đối soát vẫn biết nó phải xuất hiện.

**Giới hạn:** không phải mọi debug log đều có event nguồn bền vững. Với lớp log không thể đối soát từng event, có thể kết hợp canary end-to-end, bộ đếm ở điểm phát, bộ đếm trên agent và sink, sampling có kiểm soát và các chỉ báo vận hành. Khi đó phải ghi rõ **độ phủ của SLI**, không tuyên bố đo được mọi thất thoát tuyệt đối.

### Nguồn ID và tính độc lập

- `eventId` phải đủ ổn định và duy nhất để nối nguồn với sink; nếu retry gửi lại cùng event, giữ ID để dedup.
- `messageId` của business message không nhất thiết là `eventId` của từng bản ghi log; một message có thể phát nhiều log.
- Có thể lấy mốc nguồn từ audit outbox/transaction commit, không chỉ metric trong JVM vì JVM crash cũng có thể làm mất chính metric đó.
- SLI reconciler cần có trạng thái/timestamp đáng tin và phải báo chính nó khi bị hỏng.
- Nếu source event count được lấy từ chính logging pipeline đang đo, outage toàn pipeline có thể làm cả metric nguồn biến mất. Cần monitor bằng đường metrics/health tương đối độc lập.

## 9. Cohort, deadline và phân loại sự kiện chưa kết thúc

Đây là điểm dễ làm sai tỷ lệ khi tính trên cửa sổ thời gian.

Giả sử mốc deadline 30 giây. Nếu đo đúng lúc 10:00:05, một event tạo lúc 10:00:00 nhưng chưa thấy ở sink vẫn **chưa quá hạn**. Coi nó là mất ngay là sai; bỏ nó khỏi mẫu số vô thời hạn cũng sai.

Một cách thiết kế:

1. Sự kiện đủ điều kiện có `eventId` và `t0`.
2. Đến `t0 + 30s`, reconciler kết luận **ON_TIME** nếu đã quan sát kết quả đích hợp lệ trước/hay đúng deadline.
3. Nếu chưa có, sau deadline được tính **BAD / DEADLINE_MISSED** theo SLO, dù event có thể đến muộn sau đó.
4. Sau đó có thể thêm thông tin `LATE` hoặc `MISSING` trong báo cáo eventual delivery; **không xóa vi phạm deadline** khi event đến muộn.
5. Khi reconciliation itself không hoạt động, đánh dấu **measurement unavailable**, không tự báo green.

Để tổng hợp, có thể dùng **cohort theo thời điểm phát sinh** (event `t0` nằm trong cùng cửa sổ nguồn, và cửa sổ đã “mature” đủ deadline) hoặc **cửa sổ theo thời điểm kết luận** (mọi event có trạng thái cuối được finalized trong window). Hai cách có thể khác ở ranh giới cửa sổ. Hãy chọn **một** và nhất quán trong SLO, dashboard và alert.

### Tránh trộn cohort khi chia hai counter độc lập

Không nên tùy tiện lấy:

```text
events_arrived_in_last_5m / events_created_in_last_5m
```

vì log tạo cuối cửa sổ có thể tới đầu cửa sổ sau, trong khi log tạo trước cửa sổ có thể vừa đến. Tỷ số có thể tạm thời vượt 100% hoặc thấp giả. Đúng hơn là đối chiếu cùng cohort/event ID, hoặc count một counter **finalized outcome** với cùng mốc kết luận.

## 10. Java 17 chạy độc lập: tính SLI, error budget và burn rate

Ví dụ sau dùng **Java 17 thuần, không phụ thuộc broker hay logger ngoài**. Nó tạo một tập gồm 10.000 event giả định đã đủ thời gian kết luận, trong đó:

- 9.990 event được lưu sau 10 giây (trong deadline 30 giây).
- 7 event được lưu sau 45 giây (đến muộn).
- 3 event không có bằng chứng được lưu (missing).
- Không có timestamp sai trật tự.

Mỗi record có ID, mốc nguồn và mốc persisted hoặc `null`. Logic phân loại **không tính latency của event missing như 0**, và không tính độ trễ âm là tốt.

### 10.1. Tệp `LogPipelineSloDemo.java`

```java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;

public class LogPipelineSloDemo {
    enum Result {
        ON_TIME, LATE, MISSING, INVALID_TIMESTAMP
    }

    record Event(
            String eventId,
            Instant createdAt,
            Instant persistedAt
    ) {}

    static Result classify(Event event, Duration deadline) {
        if (event.persistedAt() == null) {
            return Result.MISSING;
        }

        Duration elapsed = Duration.between(
                event.createdAt(), event.persistedAt());

        if (elapsed.isNegative()) {
            return Result.INVALID_TIMESTAMP;
        }

        if (elapsed.compareTo(deadline) <= 0) {
            return Result.ON_TIME;
        }

        return Result.LATE;
    }

    public static void main(String[] args) {
        int eligible = 10_000;
        int onTime = 0;
        int late = 0;
        int missing = 0;
        int invalid = 0;

        Instant produced =
                Instant.parse("2026-01-01T10:00:00Z");
        Duration deadline = Duration.ofSeconds(30);

        for (int i = 0; i < eligible; i++) {
            Instant persisted;

            if (i < 9_990) {
                persisted = produced.plusSeconds(10);
            } else if (i < 9_997) {
                persisted = produced.plusSeconds(45);
            } else {
                persisted = null;
            }

            Event event = new Event(
                    "event-" + i, produced, persisted);

            switch (classify(event, deadline)) {
                case ON_TIME -> onTime++;
                case LATE -> late++;
                case MISSING -> missing++;
                case INVALID_TIMESTAMP -> invalid++;
            }
        }

        int bad = eligible - onTime;
        BigDecimal target = new BigDecimal("0.9995");
        BigDecimal allowedFraction =
                BigDecimal.ONE.subtract(target);

        long allowedBad = BigDecimal.valueOf(eligible)
                .multiply(allowedFraction)
                .longValueExact();

        double achievedRate = 100.0 * onTime / eligible;
        double budgetUsed = 100.0 * bad / allowedBad;
        double burnRate =
                ((double) bad / eligible)
                    / allowedFraction.doubleValue();

        System.out.println("eligible=" + eligible);
        System.out.println("onTime=" + onTime);
        System.out.println("late=" + late);
        System.out.println("missing=" + missing);
        System.out.println("invalidTimestamp=" + invalid);
        System.out.printf(
                Locale.ROOT,
                "onTimeRate=%.3f%%%n", achievedRate);
        System.out.printf(
                Locale.ROOT,
                "target=%.3f%%%n", target.doubleValue() * 100.0);
        System.out.println("allowedBad=" + allowedBad);
        System.out.println("observedBad=" + bad);
        System.out.printf(
                Locale.ROOT,
                "budgetUsed=%.1f%%%n", budgetUsed);
        System.out.printf(
                Locale.ROOT,
                "burnRate=%.2fx%n", burnRate);
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac LogPipelineSloDemo.java
java LogPipelineSloDemo
```

**Stdout xác định của chương trình:**

```text
eligible=10000
onTime=9990
late=7
missing=3
invalidTimestamp=0
onTimeRate=99.900%
target=99.950%
allowedBad=5
observedBad=10
budgetUsed=200.0%
burnRate=2.00x
```

### 10.2. Diễn giải

- `ON_TIME` khi persisted timestamp không âm và **≤30 giây** sau nguồn.
- `LATE` dù event cuối cùng có tới: nó đã vi phạm SLO đúng hạn.
- `MISSING` chỉ vì mô hình giả định **cửa sổ đã đủ lâu để kết luận** và không thấy bằng chứng lưu; trong hệ thống thật cần reconciler/timeout có trách nhiệm.
- `INVALID_TIMESTAMP` được đếm riêng khi thời gian đích nhỏ hơn nguồn; nó không được cộng vào good. Cần điều tra clock skew hoặc dữ liệu bị hỏng.
- `allowedBad=5` được tính với `BigDecimal("0.9995")` để tránh sai số nhị phân ở phép tính số nguyên minh họa.
- `budgetUsed=200%` phản ánh 10 bad so với ngân sách cho phép 5; `burnRate=2x` phản ánh tỷ lệ lỗi cao gấp đôi tỷ lệ cho phép.

**Giới hạn của demo:** mọi event được tạo trong bộ nhớ, timestamp cố định, không có collector, không thực sự quan sát mạng, không xử lý duplicate, kết quả persisted do code tự dựng. Đây là bộ tính toán để hiểu công thức, **không phải hệ thống đo end-to-end production**. Với cửa sổ khác, target không chia hết ra số nguyên hoặc `allowedBad=0`, cần chính sách đánh giá trực tiếp SLI và phép chia an toàn; không copy `budgetUsed` của demo vào mọi trường hợp.

### 10.3. Chuyển ví dụ sang ứng dụng thật

Thay generator giả bằng:
- nguồn `eventId`/`t0` của audit outbox, event emitter hoặc canary;
- sink lookup xác nhận ID tại nơi lưu/query;
- bộ phân loại khi deadline kết thúc;
- counter/metric chỉ phát sau khi kết luận và có thể replay/dedup kết quả.

Đừng để một failure của reconciler được hiểu là “không có event xấu”. Instrument cả **số event chưa phân loại, thời gian trễ reconciler và nguồn bị mất kết nối**.

## 11. Thiết kế metrics và cách dùng Prometheus/PromQL

Một bộ metrics có thể gồm:

| Metric minh họa | Vai trò | Chú ý |
| --- | --- | --- |
| `log_eligible_events_total` | Số event nguồn đủ điều kiện | Cần nguồn gần business event, không chỉ collector |
| `log_delivery_finalized_total{result}` | Số event đã được phân loại khi deadline mature | Các result **loại trừ nhau** và cùng denominator |
| `log_delivery_latency_seconds` | Latency các event đã nhận | Histogram phục vụ chẩn đoán; không thay loss SLI |
| `log_pipeline_dropped_total{stage}` | Drop được phát hiện tại JVM/agent/sink | Có thể không bao phủ silent loss |
| `log_pipeline_queue_depth` | Backlog async appender/agent | Gauge không phải tỷ lệ delivery |
| `log_pipeline_spool_bytes` | Disk spool đã sử dụng | Cảnh báo gần đầy |
| `log_pipeline_retry_total` | Retry của transport | Không bằng số event unique |
| `log_pipeline_last_delivery_timestamp_seconds` | Mốc thành công gần nhất | Phát hiện stalled pipeline nếu traffic bình thường |
| `log_pipeline_canary_total{result}` | Canary tốt/xấu theo probe ID | Cần kiểm tra từ nguồn tới nơi lưu |
| `log_sli_reconciler_lag_seconds` | Reconciler chậm kết luận | Phát hiện hệ thống đo bị hỏng |

Tên metric trên là **tên đề xuất**, không phải metric mặc định của JUL, Logback, agent hay collector. Kỹ thuật instrument phụ thuộc stack đang dùng.

**Quan trọng:** `log_delivery_finalized_total` chỉ được tăng **một lần cho mỗi eligible event** khi đã đến thời điểm kết luận. Các label `result="on_time"`, `result="late"`, `result="missing"`, `result="invalid_timestamp"` không được đếm trùng; nếu event đến muộn sau khi đã được đánh dấu missed, nên theo dõi late-arrival bằng metric khác hoặc trạng thái bổ sung không làm tăng denominator finalized lần hai.

### Ví dụ PromQL

Nếu counter đã được instrument chính xác theo những event **được finalized trong cửa sổ**:

```promql
sum(increase(log_delivery_finalized_total{
  class="critical",result="on_time"
}[1h]))
/
sum(increase(log_delivery_finalized_total{
  class="critical"
}[1h]))
```

Query minh họa tính tỷ lệ event **được kết luận trong một giờ**. Nó **không tương đương** SLI cho cohort “event được tạo trong một giờ” nếu deadline và phân loại trễ nằm ở cửa sổ khác; hãy thống nhất định nghĩa trong SLO. Nếu denominator bằng 0 hoặc metric không có data, phải báo trạng thái no-data/unknown, không vẽ 100%.

Burn rate tương ứng khi target là `0.9995`:

```promql
(
  1 -
  (
    sum(increase(log_delivery_finalized_total{
      class="critical",result="on_time"
    }[1h]))
    /
    sum(increase(log_delivery_finalized_total{
      class="critical"
    }[1h]))
  )
) / (1 - 0.9995)
```

**Cảnh báo về tính độc lập của phép đo:** query chỉ phản ánh đúng SLO khi reconciler đã phân loại cả **event mất trước collector**. Counter tự tăng dựa trên những event đã nhìn thấy tại collector sẽ đánh giá thiếu lỗi. Cần thêm kiểm tra volume, `reconciler lag` và trạng thái nguồn.

### Tránh cardinality cao

Metric labels nên dùng `service`, `environment`, `class`, `result`, `stage` theo tập có giới hạn. **Không dùng `eventId`, `requestId`, `userId`, `messageId` hoặc raw exception string làm label**. Các ID chi tiết nên nằm trong event store/reconciliation DB, không trở thành time series riêng.

## 12. Canary end-to-end và kiểm tra sự hiện diện trong sink

**Synthetic canary** là event thử chứa ID không nhạy cảm, gửi định kỳ qua đúng đường ứng dụng cần giám sát.

Quy trình khái niệm:

1. Scheduler phát canary qua cùng logger/appender/profile với event `critical` thực, hoặc từ một service đại diện phù hợp.
2. Ghi lại `canaryId`, mốc phát và lớp lưu.
3. Hệ thống giám sát độc lập truy vấn collector/index theo canaryId, hạn chót và quyền kiểm tra.
4. Chỉ đánh dấu `ON_TIME` nếu tìm đúng record có field/schema hợp lệ trước deadline.
5. Nếu không tìm thấy, báo lỗi đường logging; tiếp tục kiểm tra sự kiện đến muộn để phân biệt latency với loss.
6. Cảnh báo vẫn phải hoạt động khi collector/logging chính hỏng, ví dụ metrics/alerting nằm ở miền lỗi khác.

Ví dụ sự kiện thử:

```json
{
  "eventType": "LOG_PIPELINE_CANARY",
  "canaryId": "canary-test-0007",
  "service": "order-service",
  "class": "critical",
  "schemaVersion": 1
}
```

Không đưa secret thật, token hay dữ liệu người dùng vào canary. Nếu canary không có load/định dạng giống event thật, nó có thể đi qua pipeline khác. Nên bổ sung **kiểm tra trên traffic thực** khi có yêu cầu về completeness.

### Làm sao để canary không tạo kết quả giả?

- Không phát canary trực tiếp vào collector rồi tuyên bố ứng dụng Java đã được kiểm tra; điểm phát phải đúng phạm vi SLO.
- Không chỉ kiểm tra HTTP 200 khi gửi; cần kiểm tra mốc lưu/query theo contract.
- Không cho canary lọt qua filter riêng còn event thật bị discard mà dashboard vẫn xanh.
- Không dùng query dựa trên thời gian hiện tại quá hẹp khiến event có time skew bị ẩn; ưu tiên ID duy nhất.
- Khi collector hỏng, canary probe cũng có thể không đọc được; đó là failure/unknown của đường đo, không được coi là pass.
- Dữ liệu canary phải được nhận diện và giới hạn retention/khối lượng, tránh làm lệch report audit hoặc phí ingest.

## 13. Cách xây một bộ đối soát completeness

Với những event quan trọng có `eventId` bền vững, đối soát là cách đáng tin hơn kiểm tra mỗi component health.

Một bảng khái niệm:

| `eventId` | `t0` | `tPersisted` | Kết luận tại deadline | Eventual outcome |
| --- | --- | --- | --- | --- |
| ev-1 | 10:00:00 | 10:00:05 | ON_TIME | DELIVERED |
| ev-2 | 10:00:00 | 10:00:42 | MISSED_DEADLINE | LATE |
| ev-3 | 10:00:00 | Chưa có | MISSED_DEADLINE | MISSING |
| ev-4 | 10:00:00 | 09:59:59 | INVALID_TIMESTAMP | CLOCK_SKEW/INVESTIGATE |

Một pipeline đối soát có thể:

- Đọc source outbox/event table theo checkpoint đáng tin, ghi lại watermark và event IDs.
- Query sink theo batch ID hoặc truy vấn cơ sở dữ liệu event, không query mỗi ID bằng một yêu cầu mạng nếu volume lớn.
- Khóa/đánh dấu trạng thái một lần khi deadline kết thúc; tránh hai worker finalized cùng event.
- Lưu `state` và `finalizedAt` để có thể restart/replay mà không nhân đôi `log_delivery_finalized_total`.
- Ghi lại event đến muộn sau khi đã vi phạm deadline nhưng **không sửa lịch sử vi phạm** trong báo cáo SLO.
- Theo dõi khoảng mất dữ liệu, clock skew và tình trạng backlog của chính reconciler.

**Phải chống sai lệch do dữ liệu đo:** Nếu source database bị thiếu event, không thể xem mọi hành động nghiệp vụ đã diễn ra. Nếu sink index bị retention xóa trước lúc reconciliation, kết luận cần xét contract retention. Nếu event IDs có collision, join có thể báo false success.

### Khi nào không thể có số đo tuyệt đối?

Với log text ad hoc không có event ID từ source, không có outbox và logger có thể disable, rất khó đo chính xác “tỷ lệ mọi dòng log từng lẽ ra phải có”. Khi đó **đừng đặt một SLO completeness giả có độ chính xác hai chữ số thập phân**. Hãy chọn SLI đo được (canary, rate-limit/drop metrics, queue health, sampling coverage) hoặc bổ sung instrumentation để tiến tới end-to-end đo thật.

## 14. Alerting theo error budget và multi-window burn rate

SLO giúp phân biệt alert cần phản ứng ngay và cảnh báo xu hướng.

Ví dụ triển khai:

- **Fast burn:** lỗi tăng mạnh trong cửa sổ ngắn và dài tương ứng; cần đánh giá incident ngay.
- **Slow burn:** tỷ lệ vi phạm nhẹ nhưng kéo dài; tạo ticket/ưu tiên cải thiện trước khi budget cạn.
- **No data:** traffic source biến mất hoặc reconciler hỏng, không coi là healthy.
- **Silent loss:** canary không đến, nhưng queue/CPU của ứng dụng vẫn bình thường; cần kiểm tra mốc end-to-end.

### Vì sao dùng nhiều cửa sổ?

Một cửa sổ 5 phút phản ứng nhanh nhưng dễ nhiễu khi volume ít. Một cửa sổ 1 giờ ổn định hơn nhưng phát hiện chậm. Có thể yêu cầu điều kiện trên **cả 5 phút và 1 giờ** cho fast burn, cộng một cặp **6 giờ và 24 giờ** cho slow burn. Ngưỡng burn cụ thể phải căn theo target, thời gian budget, volume và alert fatigue; **không có một con số áp dụng chung cho mọi hệ thống**.

Một chính sách triển khai có thể nói:

```text
PAGE: 5m và 1h đều vượt ngưỡng fast-burn đã hiệu chỉnh,
      với tối thiểu số eligible events để có tín hiệu đáng tin.

TICKET: 6h và 24h vượt ngưỡng slow-burn đã hiệu chỉnh.

PAGE/DASHBOARD UNAVAILABLE:
      nguồn/reconciler/canary no-data quá ngưỡng
      hoặc thành phần đo báo lỗi độc lập.
```

Không nhất thiết mọi trường hợp budget burn đều cần page. Nếu event class là audit bắt buộc, một event mất đã có thể cần phản ứng theo policy; nếu traffic nhỏ và có một số log đến muộn vì maintenance hợp lệ, cần xử lý theo phạm vi miễn trừ đã phê duyệt, không tùy tiện làm xanh metric sau sự cố.

## 15. Tác động của AsyncAppender, buffer và backpressure lên SLO

Với Logback `AsyncAppender`, producer enqueue event rồi worker thread mới gửi tới appender đích. Tùy cấu hình và tải:

- `queueSize` giới hạn queue trong RAM.
- `discardingThreshold` có thể khiến những mức log ít ưu tiên bị bỏ gần ngưỡng đầy, trừ khi đã thay đổi chính sách.
- `neverBlock=true` tránh chặn producer khi enqueue thất bại nhưng có thể bỏ event.
- `neverBlock=false` có thể chặn producer khi queue đầy, làm tăng latency nghiệp vụ.
- `maxFlushTime` ảnh hưởng thời gian chờ khi dừng, không tự bảo đảm event đã đến collector cuối.

Đây là các tùy chọn đặc thù của **Logback AsyncAppender**; không copy tên này sang mọi backend. Với Log4j2 AsyncLogger, JUL async bridge hoặc collector agent, hành vi phải đọc từ implementation/version thực.

**SLO phải đo từ điểm nguồn đủ điều kiện**, không từ “số event đã vượt qua AsyncAppender queue”. Nếu event bị drop trong async queue và nguồn vẫn phải cam kết lưu, đó là SLO violation. Nếu sampling/drop là policy đã công bố cho lớp DEBUG, những event đó có thể nằm ngoài eligible set; không được lặng lẽ đổi policy của lớp critical khi quá tải.

### Buffer hữu hạn luôn phải có kế hoạch khi đầy

| Cách xử lý | Đổi lại | Tác động cần đo |
| --- | --- | --- |
| Block producer | Có thể tránh drop ngắn hạn, tăng latency | p95/p99 request latency, thời gian block |
| Drop log ưu tiên thấp | Giữ business throughput | Drop count theo class, risk mất tín hiệu |
| Disk spool | Tăng thời gian chịu outage | Spool size, replay delay, quota |
| Retry với backoff | Có thể phục hồi transport | Backlog tuổi lớn nhất, retry success |
| Secondary sink | Giảm phụ thuộc một đích | Duplicates, miền lỗi chung, quyền truy cập |

Queue trong RAM **không durable khi process crash**. Disk spool có thể chịu outage dài hơn nhưng vẫn có rủi ro quota đầy, mất disk hoặc crash trước fsync. SLO không nên dựa vào việc “queue hiện đang rỗng” như bằng chứng record đã nằm trong nơi lưu cần thiết.

## 16. SLO khi logging qua file, stdout và collector

Ứng dụng Java chạy container thường ghi stdout/stderr rồi platform log agent thu thập. Điều này đơn giản hóa code nhưng không có nghĩa delivery end-to-end được bảo đảm.

**Đường stdout:**
- `println` hoặc ConsoleAppender trả về không chứng minh hệ thống trung tâm đã index.
- Runtime logging driver/agent có thể bị chậm, giới hạn dung lượng hoặc cấu hình discard.
- Nếu stdout bị redirect, sink thực tế có thể khác môi trường local.

**Đường file:**
- FileAppender mở/ghi file có thể lỗi vì permission, volume đầy, rotation hoặc read-only mount.
- Ghi vào OS buffer không tự bảo đảm fsync/durable sau host crash.
- Nếu agent tail file, cần hiểu rotation, inode/offset checkpoint và retention.

**Đường remote collector:**
- Batch có thể được nhận một phần; HTTP 200/202 và transport ACK có semantics riêng.
- Retry có thể tạo duplicate; phải giữ event ID và dedup nếu SLI đếm unique events.
- Indexer có thể chậm khi ingest vẫn hoạt động; freshness SLO cần đo đúng mốc queryable.
- Auth/TLS lỗi hoặc schema thay đổi có thể khiến một số event bị từ chối.

Với nhiều sink song song, cần nói SLO là **đến ít nhất một sink**, **đến đúng sink chính**, hay **đến cả hai sink**. Không cộng số event của hai sink rồi gọi đó là completeness: một event có thể được đếm hai lần và che event khác bị mất.

## 17. Audit logging có nên dùng cùng SLO với operational logs?

Thường **không nên**, nếu audit có ý nghĩa tuân thủ, truy vết hoặc bằng chứng nghiệp vụ bắt buộc. Các nguyên tắc cần tách:

- **Best-effort observability logs** phục vụ vận hành có thể cho phép một mức discard/sampling.
- **Audit events** có thể cần hợp đồng không được tự ý bỏ, truy cập hạn chế, retention, immutable storage, bảo toàn bằng chứng.
- Nếu audit phải lưu trước khi nghiệp vụ hoàn thành, cần boundary commit/ack rõ, không chỉ `logger.info("AUDIT ...")`.
- Transactional outbox có thể gắn mutation và event chờ gửi trong cùng transaction database; dispatcher retry/dedup sau commit. Nó giúp giảm khoảng trống mất event, **không tự tạo exactly-once trên toàn pipeline**.
- Event `DENIED/REJECTED` không có mutation cũng có thể cần lưu; không đưa vào transaction nghiệp vụ sẽ rollback rồi tưởng audit vẫn tồn tại.
- Nếu audit sink hỏng, chính sách có thể yêu cầu fail closed cho hành động cụ thể, hoặc dùng buffer bền vững được phê duyệt. Phải thống nhất với nghiệp vụ/pháp chế/an ninh.

Một SLO “99,95% audit đến trong 30 giây” **không thay thế** quy định bắt buộc phải có mọi bằng chứng. Nó có thể là chỉ báo phục vụ cảnh báo, nhưng độ bền, tính toàn vẹn và quyền truy cập là yêu cầu khác cần kiểm chứng.

### Phân biệt SLO “đến đúng hạn” với “còn được giữ”

Một event đã đến đúng hạn nhưng bị xóa sau 1 giờ, trong khi policy yêu cầu 90 ngày, vẫn vi phạm **retention/durability requirement**. Cần SLI hoặc kiểm tra compliance riêng cho tồn tại sau restart/crash, dữ liệu không bị sửa, retention và audit access.

## 18. Kiểm thử SLO: unit, integration và fault injection

### 18.1. Unit test hàm phân loại

Ví dụ phần 10 có hàm `classify(Event, Duration)`. Trong dự án JUnit 5 cùng package, có thể kiểm thử:

```java
// Test snippet: cần JUnit Jupiter trên classpath.
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class LogPipelineSloTest {
    @Test
    void deadlineBoundaryCountsAsOnTime() {
        Instant start = Instant.parse("2026-01-01T10:00:00Z");
        var event = new LogPipelineSloDemo.Event(
                "e-1", start, start.plusSeconds(30));

        assertEquals(
                LogPipelineSloDemo.Result.ON_TIME,
                LogPipelineSloDemo.classify(
                        event, Duration.ofSeconds(30)));
    }

    @Test
    void lateAndMissingAreNotGood() {
        Instant start = Instant.parse("2026-01-01T10:00:00Z");

        assertEquals(
                LogPipelineSloDemo.Result.LATE,
                LogPipelineSloDemo.classify(
                    new LogPipelineSloDemo.Event(
                        "e-2", start, start.plusSeconds(31)),
                    Duration.ofSeconds(30)));

        assertEquals(
                LogPipelineSloDemo.Result.MISSING,
                LogPipelineSloDemo.classify(
                    new LogPipelineSloDemo.Event(
                        "e-3", start, null),
                    Duration.ofSeconds(30)));
    }
}
```

Đây là **mẫu test có thể dùng sau khi thêm dependency JUnit 5 và đặt đúng package**, không phải file tự chạy bằng `javac` thuần. Nó kiểm tra ngưỡng, không chứng minh SLI end-to-end. Phải test thêm `persistedAt` trước `createdAt`, deadline âm/không hợp lệ, sự kiện trùng và xử lý counter khi mốc kết luận được replay.

### 18.2. Integration test pipeline

- Khởi động logging backend với profile đúng và sink test (collector/proxy, file hoặc agent cô lập).
- Phát các event có `eventId` duy nhất từ đúng entry point theo SLO.
- Dùng timestamp được kiểm soát/có hợp đồng, đo latency ở mốc sink được chọn.
- Chờ sink bằng acknowledgment hoặc polling có timeout, không dùng `Thread.sleep(500)` rồi coi là xác nhận.
- Đếm unique IDs tại source và sink, phân biệt event mất, trễ, duplicate và sai schema.
- Cleanup appender, agent, queue, files và test collector sau test; không can thiệp production.

### 18.3. Fault injection có chủ đích

| Tình huống | Điều cần quan sát |
| --- | --- |
| Logger level/filter chặn event critical | SLI phát hiện event thiếu nếu source truth độc lập |
| Async queue đầy và discard | Drop metric, tăng bad events, không tự báo green |
| Sink file hết quyền/đĩa đầy | Backend status, backlog, fallback, tỷ lệ mất |
| Agent restart | Spool/offset, duplicate hoặc gap, eventual delivery |
| Collector trả 429/503 | Retry với backoff, deadline misses, queue growth |
| Collector nhận nhưng index chậm | Ingest ACK tốt nhưng queryable freshness xấu |
| Network timeout sau collector nhận | Retry duplicate, dedup theo event ID |
| JVM/process crash khi queue còn event | Kiểm tra RAM queue không durable |
| Reconciler dừng hoặc metric source mất | No-data/measurement alert, không giả đạt SLO |
| Nhiều service/partition | Ordering, class-level degradation và SLI phân nhóm |

Trong test lỗi dài, giới hạn tốc độ, dung lượng spool và thời gian thử để không làm đầy máy CI. Với audit bắt buộc, test cả hành vi fail closed hoặc phục hồi outbox chứ không chỉ SLO dashboard.

## 19. Runbook khi SLO logging không đạt

Khi SLO hoặc canary cảnh báo, một quy trình phản ứng hữu ích:

1. **Xác thực tín hiệu:** SLI nào fail? Completeness, freshness, schema, canary hay measurement unavailable? Cửa sổ nào và lớp log nào?
2. **Kiểm tra nguồn:** event eligible có được tạo/commit? Có đổi log level, filter, sampling hoặc schema không? Source IDs có còn được phát không?
3. **Khoanh vùng chặng:** logger → async queue → stdout/file → agent → transport → collector → index/query. Đối chiếu số lượng và event IDs ở từng mốc có thể tin cậy.
4. **Xem tài nguyên:** queue depth, drop, spool bytes, disk quota, memory, CPU, retry, 429/5xx, rate limit và index lag.
5. **Phân loại mất hay đến muộn:** event đến sau deadline vẫn là violation của timely SLO; việc nó đến sau giúp định vị lỗi, không xóa vi phạm.
6. **Giảm tác động:** khôi phục sink, cấu hình lại quota/transport, kích hoạt đường dự phòng theo runbook; tránh tăng retry nóng gây overload.
7. **Bảo vệ chứng cứ:** với security/audit events, giữ source outbox, spool, bản ghi độc lập và metadata truy cập; không vội xóa log gốc.
8. **Phục hồi:** drain backlog, replay event chưa ACK, dedup bản nhận lại; đo queue age và xác nhận mốc sink.
9. **Tính lại ảnh hưởng:** khoảng thời gian, event classes, số bad đã kết luận, event chưa đối soát và mức dùng error budget.
10. **Ngăn tái diễn:** test lại failure scenario, bổ sung cảnh báo độc lập và theo dõi cửa sổ sau triển khai.

Báo cáo sự cố phải phân biệt **“xác nhận mất”**, **“quá deadline nhưng đến muộn”**, **“không có đủ dữ liệu để biết”** và **“không thuộc nhóm eligible theo policy”**. Không báo một con số “0 log mất” nếu chỉ có số liệu từ collector mà source không có independent truth.

## 20. Sai lầm thường gặp khi xây SLO cho pipeline log

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Lấy availability của collector làm SLO end-to-end | Collector up nhưng event có thể mất trước đó | Đo theo event IDs từ nguồn đến sink |
| Mẫu số chỉ là log đã nhận | Silent loss không vào denominator | Dùng source eligible count/reconciliation |
| Lấy p99 latency của event đã đến | Event mất không có latency | On-time success / total eligible |
| Tính event chưa đủ deadline là missing ngay | Tạo false failures | Cohort matured và deadline rõ |
| Bỏ event trễ khỏi bad khi cuối cùng đã tới | Xóa vi phạm freshness | Giữ deadline-miss, theo dõi late riêng |
| Đếm bản retry trùng như message nguồn mới | Completeness có thể vượt 100% | Dedup theo stable event ID |
| Gộp audit và debug vào một tỷ lệ | INFO volume che mất audit nhỏ nhưng quan trọng | SLO theo event class và nghĩa vụ |
| Coi canary từ collector là end-to-end | Không đi qua JVM/appender | Canary từ đúng điểm bắt đầu |
| Coi queue rỗng là durable | Worker có thể đã lấy rồi thất bại ghi | Kiểm tra ACK/index/query ở mốc đích |
| Chỉ query histogram latency | Không đo silent drop | Loss/completeness SLI + drop metrics |
| Không monitor SLI reconciler | Instrumentation chết khiến dashboard xanh giả | No-data, lag, independent health |
| Không phân biệt event emit và ingest window | Tỷ lệ lệch, có thể >100% | Cohort hoặc finalized window nhất quán |
| Dùng eventId làm metric label | Cardinality bùng nổ, có thể lộ dữ liệu | Giữ ID trong event store, label giới hạn |
| Chỉ alert trên lỗi transport | Parse/index lỗi vẫn làm event vô dụng | Schema/queryability SLI |
| Mặc định 99,95% là chuẩn cho mọi hệ thống | Không xét policy/chi phí/rủi ro | Thỏa thuận target theo class và nhu cầu |
| Tăng retry vô hạn khi outage | Gây overload, kéo dài sự cố | Backoff, budget, spool/buffer hữu hạn |

## 21. Checklist triển khai SLO pipeline log

- [ ] Xác định lớp event nào cần SLO, điểm nguồn `t0` và lý do event eligible.
- [ ] Xác định điểm đích: accepted, durable, indexed hay queryable, không gọi chung là “delivered”.
- [ ] Định nghĩa deadline, cửa sổ SLO, target và cách xử lý event chưa trưởng thành.
- [ ] Chọn on-time/completeness SLI có mẫu số từ nguồn phù hợp và nhận diện silent loss.
- [ ] Có stable `eventId`, dedup và đối soát khi retry hoặc collector mất ACK.
- [ ] Phân loại đúng event tốt, đến muộn, không tìm thấy, timestamp sai, sai schema.
- [ ] Đồng bộ đồng hồ hoặc có cách đo latency đáng tin, không coi thời gian âm là good.
- [ ] Theo dõi p95/p99 latency, queue depth, drop/retry, spool, collector/index lag để chẩn đoán.
- [ ] Canary đi qua đường thật, có ID riêng và hệ thống kiểm tra kết quả độc lập.
- [ ] Reconciler có watermark, no-data alert, restart/replay an toàn và không double-count.
- [ ] Dùng error budget/burn rate với cửa sổ, volume và alert phù hợp.
- [ ] SLO theo class; audit bắt buộc có hợp đồng durability/security riêng nếu cần.
- [ ] Có test fault injection ở logger, queue, agent, collector, indexing và measurement.
- [ ] Giữ dữ liệu nhạy cảm ra khỏi metric labels, canary và dashboard rộng quyền.
- [ ] Có runbook tính ảnh hưởng, phục hồi backlog, replay và công bố sai số quan sát.
- [ ] Review SLO sau thay đổi log level, filter, appender, sampling, retention hoặc backend.

**Ghi nhớ:** SLO logging có giá trị khi nó đo **sự kiện đáng lẽ phải đến có thật sự tới đúng nơi, đúng hạn và dùng được hay không**. Muốn như vậy cần định nghĩa đủ điều kiện từ nguồn, deadline/mốc đích rõ ràng, đối soát ID và hệ thống đo độc lập. Queue, collector health, canary và latency histogram là những tín hiệu hữu ích, nhưng không thể tự thay thế phép đo mất sự kiện end-to-end.
