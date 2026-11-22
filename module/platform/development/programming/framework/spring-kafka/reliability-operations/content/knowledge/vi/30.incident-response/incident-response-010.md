# Pause trước khi sửa dữ liệu

Trong một sự cố production, sửa một bản ghi sai trong database có thể trông như một thao tác đơn giản: tìm đúng hàng, chạy `UPDATE`, kiểm tra lại kết quả. Nhưng nếu Spring Kafka consumer vẫn đang xử lý message liên quan, dữ liệu có thể bị ghi đè ngay sau khi sửa. Một message đang nằm trong retry topic có thể quay lại, một consumer khác có thể cập nhật cùng aggregate, hoặc một scheduled job có thể phát sinh thêm thay đổi trong lúc người vận hành đang khắc phục.

Vì vậy, trước khi sửa dữ liệu trong một hệ thống đang chạy, cần kiểm soát những luồng có thể tiếp tục ghi vào vùng dữ liệu bị ảnh hưởng. **Pause trước khi sửa dữ liệu** là bước tạo ra một khoảng dừng có kiểm soát để người vận hành xác định trạng thái hiện tại, bảo toàn bằng chứng, thực hiện thay đổi có giới hạn và khôi phục xử lý theo thứ tự an toàn.

Pause không tự sửa được dữ liệu sai, không hủy một side effect đã xảy ra và cũng không bảo đảm mọi writer trong hệ thống đều dừng. Nó chỉ có tác dụng khi xác định đúng phạm vi và kiểm tra rằng tất cả đường ghi liên quan đã được kiểm soát.

## 1. Vì sao phải pause trước khi sửa?

Hãy xét một consumer nhận event `OrderPaid` và cập nhật trạng thái đơn hàng. Người vận hành phát hiện một nhóm đơn có trạng thái sai và chuẩn bị chạy SQL để sửa. Nếu consumer vẫn hoạt động, các tình huống sau có thể xảy ra:

- Consumer đang xử lý đúng một đơn mà người vận hành sắp sửa. SQL chạy trước, sau đó consumer ghi trạng thái cũ trở lại.
- Hai event của cùng aggregate được xử lý ở hai luồng khác nhau. Một lần sửa thủ công có thể bị lần cập nhật còn lại ghi đè.
- Consumer đã gọi payment provider hoặc tạo vận đơn nhưng chưa ghi kết quả vào DB. Việc sửa trạng thái DB có thể khiến lần retry tiếp theo gọi provider lần nữa.
- Event cũ đang chờ trong retry topic hoặc DLT được replay trong lúc dữ liệu đang được sửa.
- Một ứng dụng khác, batch job hoặc API quản trị vẫn có quyền ghi vào cùng bảng, dù Kafka listener đã pause.

Khi đó, dữ liệu có thể thay đổi ngay trong lúc người vận hành đang xác minh. Bản sửa có thể đúng tại thời điểm chạy SQL nhưng sai vài giây sau đó. Tệ hơn, nếu sửa một bảng trạng thái mà không hiểu các bản ghi inbox, outbox hoặc effect ledger liên quan, hệ thống có thể mất dấu một side effect đã thực hiện hoặc thực hiện side effect thêm lần nữa.

Pause tạo ra một ranh giới vận hành rõ ràng: những luồng nào được phép tiếp tục, những luồng nào đang dừng, công việc nào còn đang chạy và dữ liệu nào được phép thay đổi trong thời gian bảo trì.

## 2. Khi nào cần pause?

Pause phù hợp khi cần một khoảng thời gian để điều tra hoặc sửa chữa một vùng dữ liệu mà consumer có thể tiếp tục tác động tới. Những tình huống thường gặp gồm:

| Tình huống | Vì sao nên pause |
|---|---|
| Sửa trạng thái nghiệp vụ sai do một event trước đó | Ngăn event mới hoặc event retry ghi đè bản sửa |
| Điều tra duplicate processing hoặc side effect trùng | Giữ ổn định dữ liệu để đối chiếu event, offset và lịch sử provider |
| Sửa dữ liệu tham chiếu mà consumer đang đọc | Tránh consumer đọc dữ liệu ở trạng thái nửa sửa đổi |
| Chạy backfill hoặc repair script có phạm vi ghi trùng với consumer | Tránh hai luồng ghi cạnh tranh |
| Xử lý sự cố gây ra chuỗi retry liên tục | Tạo thời gian xác định nguyên nhân và chính sách retry |
| Chuẩn bị replay một nhóm event | Kiểm soát thứ tự, phạm vi và điều kiện idempotency trước khi phát lại |

Không phải mọi lỗi đều cần pause toàn bộ hệ thống. Nếu một consumer độc lập xử lý một topic không liên quan và không ghi vào vùng dữ liệu bị ảnh hưởng, có thể giữ nó hoạt động. Phạm vi pause nên nhỏ nhất có thể nhưng phải bao phủ mọi writer có khả năng làm thay đổi dữ liệu đang sửa.

Nếu dữ liệu đang bị ghi sai liên tục hoặc có nguy cơ gây hậu quả tài chính, bảo mật hay vận hành, ưu tiên kiểm soát luồng ghi trước khi tiếp tục điều tra sâu. Trong trường hợp cần ngăn cả producer tạo thêm message, có thể phải tạm dừng ingress hoặc chức năng nghiệp vụ ở upstream. Pause consumer một mình không ngăn producer gửi record mới vào Kafka.

## 3. Xác định đầy đủ phạm vi ảnh hưởng

Trước khi nhấn pause, cần biết chính xác điều gì đang ghi dữ liệu và điều gì sẽ bị ảnh hưởng khi dừng. Một consumer group không phải lúc nào cũng tương ứng với một luồng nghiệp vụ duy nhất; một topic có thể có nhiều group độc lập, và một ứng dụng có thể chứa nhiều `@KafkaListener`.

Lập danh sách tối thiểu các thành phần sau:

| Thành phần | Cần xác định |
|---|---|
| Topic nguồn | Tên topic, partition, key và khoảng thời gian có record liên quan |
| Consumer group | Group ID, các instance đang tham gia, listener ID và concurrency |
| Retry topic | Topic retry theo cấp độ, lịch retry và consumer xử lý retry |
| Dead-letter topic | DLT, quy trình điều tra và replay đang tồn tại |
| Database | Bảng, aggregate, khóa chính, quan hệ và transaction có thể cập nhật dữ liệu |
| Side effect bên ngoài | Payment, email, SMS, vận chuyển, cấp quyền hoặc API khác |
| Luồng ghi khác | REST API, scheduler, batch, CDC consumer, admin tool hoặc ứng dụng khác |
| Outbox/inbox/effect ledger | Bản ghi đang chờ publish, event đã nhận và side effect chưa xác định |

Đặc biệt, hãy phân biệt **consumer group** với **listener container**. Một group có thể có nhiều instance chạy ở nhiều pod hoặc máy khác nhau. Pause một listener trong một pod chỉ kiểm soát container đó. Các instance khác trong cùng group vẫn có thể xử lý những partition được giao cho chúng. Các group khác đọc cùng topic cũng tiếp tục hoạt động độc lập.

Một bảng phạm vi incident nên ghi rõ:

```text
Incident: INC-2026-0042
Affected service: billing-service
Listener ID: billing-order-listener
Consumer group: billing-orders-v2
Source topic: order-paid
Affected partitions: 2, 5
Affected order IDs: ORD-1001, ORD-1008, ORD-1012
Database tables: orders, payment_attempts, external_effect
Other writers: refund scheduler, manual operations API
Retry/DLT paths: order-paid-retry-*, order-paid-dlt
```

Đây là ví dụ về cách ghi phạm vi, không phải cấu hình mặc định. Dùng tên thực tế của hệ thống và xác minh từng thành phần trước khi thao tác.

## 4. Pause trong Spring Kafka hoạt động như thế nào?

Spring Kafka cung cấp API pause/resume ở cấp listener container. Đây thường là cách phù hợp để điều khiển consumer được quản lý bởi `@KafkaListener`.

Khi gọi `pause()` trên listener container:

- Container yêu cầu consumer tạm dừng lấy thêm record từ các partition đang được gán.
- Việc pause được áp dụng tại chu kỳ poll phù hợp của consumer; lời gọi `pause()` không hủy callback đang xử lý.
- Consumer vẫn tiếp tục poll theo cơ chế của container để duy trì membership và heartbeat trong consumer group.
- Partition đang được pause vẫn thuộc assignment của consumer đó. Consumer khác không tự động nhận partition chỉ vì partition đang pause.
- Khi gọi `resume()`, consumer tiếp tục nhận record từ vị trí hiện tại theo offset và trạng thái đã được xác nhận.

Do đó, pause không giống với việc kill process hoặc xóa consumer group. Nó tạo một khoảng dừng trong việc nhận record mới, đồng thời giữ consumer trong group. Các record đã được poll hoặc listener đang xử lý vẫn cần được xử lý và xác minh theo đúng cơ chế ack/commit của ứng dụng.

### 4.1. Điều khiển listener container qua registry

Đặt `id` rõ ràng cho listener để có thể tìm đúng container qua `KafkaListenerEndpointRegistry`:

```java
@KafkaListener(
    id = "billing-order-listener",
    topics = "order-paid",
    groupId = "billing-orders-v2",
    concurrency = "3"
)
public void onOrderPaid(OrderPaid event) {
    billingService.handle(event);
}
```

Một service điều khiển có thể yêu cầu pause hoặc resume:

```java
@Component
public class KafkaListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener id: " + listenerId);
        }

        container.pause();
    }

    public void resume(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener id: " + listenerId);
        }

        container.resume();
    }
}
```

Đây là ví dụ tối giản về API điều khiển. Trong ứng dụng production, cần bổ sung phân quyền, audit log, xác nhận incident ID, trạng thái pause hiện tại và cơ chế tránh thao tác nhầm listener. Không nên cung cấp endpoint pause/resume công khai mà không có authentication và authorization phù hợp.

Với `ConcurrentMessageListenerContainer`, thao tác pause trên container cấp cao được áp dụng cho các consumer container con thuộc listener đó. Tuy nhiên, registry của một ứng dụng chỉ điều khiển những listener mà ứng dụng đó quản lý. Nếu service có nhiều replica, cần điều khiển và xác nhận trạng thái trên mọi replica liên quan. Một pod đã pause không có nghĩa toàn bộ consumer group đã pause.

### 4.2. Không gọi KafkaConsumer trực tiếp từ thread quản trị

Kafka consumer không phải đối tượng thread-safe để tùy ý gọi từ bất kỳ thread nào. Khi Spring Kafka quản lý consumer, hãy dùng API của listener container để yêu cầu pause/resume. Không lấy một `KafkaConsumer` nội bộ rồi gọi `pause()` trực tiếp từ HTTP controller hoặc thread scheduler.

Nếu ứng dụng tự quản lý Kafka consumer mà không dùng listener container, việc pause/resume phải được thực hiện trên thread sở hữu consumer hoặc thông qua một cơ chế điều khiển an toàn do ứng dụng xây dựng. Không dùng chung một consumer instance giữa thread xử lý và thread quản trị.

### 4.3. Pause container và pause partition

Pause toàn bộ listener phù hợp khi tất cả partition của listener cùng nằm trong phạm vi incident. Nếu chỉ một số partition bị ảnh hưởng và phiên bản Spring Kafka đang dùng hỗ trợ điều khiển partition, có thể cân nhắc pause partition cụ thể.

Pause theo partition đòi hỏi hiểu rõ key distribution, assignment, concurrency và dữ liệu nghiệp vụ. Một order có thể được xử lý ở partition khác nếu producer không bảo đảm cùng key; một luồng retry có thể đưa record sang topic và partition khác. Không nên chỉ pause partition chứa record đang thấy lỗi mà bỏ qua các đường đi liên quan.

Khi cần sửa một aggregate cụ thể, phạm vi dữ liệu có thể nhỏ hơn phạm vi partition. Nhưng nếu không chứng minh được rằng mọi event của aggregate đó luôn đi qua cùng một partition và mọi side effect đều do cùng listener thực hiện, hãy mở rộng phạm vi kiểm soát cho tới khi có bằng chứng rõ ràng.

## 5. Pause không có nghĩa là mọi xử lý đã dừng

Đây là điểm dễ bị hiểu nhầm nhất trong incident response. Lệnh pause là một yêu cầu điều khiển; nó không phải một hàng rào đồng bộ bao quanh toàn bộ ứng dụng.

Sau khi gọi `pause()`, vẫn có thể tồn tại:

- Một callback listener đang xử lý record đã nhận từ poll trước đó.
- Một batch listener đang xử lý các record đã nằm trong batch.
- Một tác vụ bất đồng bộ đã được listener đẩy sang executor riêng.
- Một HTTP request tới provider đang chờ phản hồi.
- Một transaction DB đã bắt đầu nhưng chưa commit hoặc rollback.
- Một scheduled job hoặc listener khác đang ghi cùng bảng.
- Một instance khác trong cùng group hoặc một consumer group khác vẫn đang hoạt động.

Vì vậy, cần có bước **drain** (để công việc đang chạy hoàn tất hoặc được phân loại) sau khi yêu cầu pause. Không chạy SQL sửa dữ liệu ngay sau khi API trả về.

### 5.1. Xác nhận listener đã pause

Tùy phiên bản Spring Kafka, có thể theo dõi trạng thái container và các sự kiện như `ConsumerPausedEvent` hoặc `ConsumerResumedEvent`. Kết hợp log có listener ID, client ID, group ID, pod/instance và partition để xác nhận từng consumer đã pause.

Các tín hiệu cần kiểm tra:

1. Đã gửi yêu cầu pause tới đúng listener ID trên tất cả instance trong phạm vi.
2. Container phát tín hiệu hoặc trạng thái xác nhận pause đã có hiệu lực.
3. Không còn record mới được chuyển vào callback của listener đó.
4. Số callback đang chạy và số tác vụ bất đồng bộ liên quan đã về 0 hoặc đã được phân loại.
5. Không còn DB transaction hoặc request bên ngoài chưa rõ kết quả có thể tác động tới dữ liệu đang sửa.

Không chỉ dựa vào việc log có dòng “pause requested”. Cần phân biệt yêu cầu pause đã được gửi với trạng thái consumer thực sự đã pause. Cách đọc trạng thái và event cụ thể phụ thuộc phiên bản Spring Kafka và cách ứng dụng cấu hình container.

### 5.2. Xử lý công việc đang chạy

Với callback đang chạy, ưu tiên để nó hoàn thành trong thời gian chờ đã định. Sau đó kiểm tra transaction DB và offset. Nếu callback bị treo ở một HTTP request, xác định provider có thể đã thực hiện side effect hay chưa. Timeout hoặc hủy future không chứng minh rằng request bên ngoài chưa xảy ra.

Nếu cần dừng một tác vụ đang chạy, phải biết trạng thái commit và side effect của nó. Không kill pod chỉ để làm số callback đang chạy về 0 khi chưa biết request đã tới provider hay transaction đã commit. Kill process có thể khiến message được giao lại trong khi hành động bên ngoài đã hoàn tất.

Đối với xử lý bất đồng bộ, listener có thể trả về trước khi công việc nền kết thúc. Trong trường hợp đó, trạng thái pause của container không phản ánh trạng thái executor. Ứng dụng cần theo dõi riêng số tác vụ đang chạy, queue nội bộ và khả năng dừng có kiểm soát của executor.

## 6. Kiểm tra offset và trạng thái consumer group

Trước khi sửa dữ liệu, ghi lại trạng thái offset của các partition liên quan. Offset giúp trả lời consumer đã xác nhận tới đâu, còn record nào đang chờ và lag đang tăng hay giảm.

Có thể dùng Kafka consumer groups CLI để xem trạng thái group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-servers> \
  --group <consumer-group-id> \
  --describe
```

Lệnh trên dùng để quan sát. Lưu output cùng thời điểm, group ID, topic và partition vào incident record. Một số môi trường có thể cần đường dẫn script hoặc cú pháp khác tùy bản phân phối Kafka.

Khi đọc kết quả, chú ý:

- `CURRENT-OFFSET` là vị trí consumer group đã commit, thường đại diện cho offset tiếp theo sẽ được đọc.
- `LOG-END-OFFSET` là vị trí cuối của log theo cách hiển thị của công cụ.
- `LAG` cho biết khoảng cách giữa log end và committed offset theo cách tính của công cụ.
- `CONSUMER-ID`, `HOST` và `CLIENT-ID` giúp xác định thành viên đang giữ partition.

Committed offset không nhất thiết bằng record cuối cùng đã được xử lý thành công trong mọi cấu hình. Với manual ack, async processing hoặc transaction, cần đối chiếu offset với log xử lý, DB và trạng thái side effect. Nếu listener đã lấy record nhưng chưa commit offset, record có thể được giao lại sau sự cố hoặc restart.

**Không reset offset chỉ để làm lag về 0 hoặc để “đồng bộ” với dữ liệu đã sửa.** Offset reset là một quyết định replay hoặc bỏ qua record, có thể thay đổi toàn bộ lịch sử xử lý của group. Nó phải có phạm vi, mốc bắt đầu/kết thúc, kế hoạch idempotency và phê duyệt vận hành riêng.

## 7. Bảo toàn bằng chứng trước khi chạy repair

Khi consumer và các writer liên quan đã được kiểm soát, lưu trạng thái trước sửa. Đây là cơ sở để xác định bản sửa có tác dụng gì, có ảnh hưởng ngoài dự kiến không và có thể khôi phục như thế nào.

Thông tin nên ghi lại gồm:

| Nhóm | Dữ liệu cần lưu |
|---|---|
| Incident | ID sự cố, người xử lý, thời điểm bắt đầu, lý do pause và phạm vi đã duyệt |
| Kafka | Topic, partition, offset, key, event ID, group ID và committed offset |
| Application | Service version, pod/instance, listener ID, concurrency và trạng thái pause |
| Database | Primary key, giá trị trước sửa, version, timestamp, quan hệ và số lượng bản ghi ảnh hưởng |
| Side effect | Effect key, provider reference, trạng thái, attempt count và kết quả đối soát |
| Retry/DLT | Record liên quan, header, exception, retry count và lịch sử replay |
| Vận hành | Log, trace ID, dashboard snapshot và lệnh đã chạy |

Với dữ liệu quan trọng, tạo backup hoặc snapshot có thể truy xuất được trước khi sửa. Nếu chỉ cần một nhóm bản ghi nhỏ, có thể xuất giá trị trước sửa vào một bảng audit hoặc file được lưu ở nơi có kiểm soát. Bản sao phải đủ thông tin để khôi phục đúng các cột đã thay đổi và phải được bảo vệ như dữ liệu production.

Lưu cả số lượng và phạm vi. Ví dụ, nếu dự kiến sửa 12 đơn hàng, hãy ghi danh sách 12 ID và xác nhận câu `SELECT` trả về đúng 12 hàng trước khi chạy `UPDATE`. Một câu SQL thiếu điều kiện có thể biến repair nhỏ thành thay đổi trên toàn bảng.

## 8. Thực hiện sửa dữ liệu có kiểm soát

Một repair tốt có mục tiêu nghiệp vụ rõ ràng, phạm vi giới hạn, có thể kiểm tra trước và có lịch sử sau khi chạy.

### 8.1. Xác định invariant cần khôi phục

Trước khi viết SQL, diễn đạt trạng thái đúng bằng một quy tắc có thể kiểm chứng. Ví dụ:

- Một `payment_attempt` ở trạng thái `SUCCEEDED` phải có provider reference hợp lệ.
- Một đơn hàng đã thanh toán không thể quay về `PENDING_PAYMENT` chỉ vì một event cũ được replay.
- Một effect đã được provider xác nhận thành công không được chuyển về `PENDING`.
- Một event đã ghi inbox và đã tạo effect intent phải có quan hệ tham chiếu nhất quán.

Không sửa theo suy đoán dựa trên một cột trạng thái. Cần hiểu aggregate, quan hệ, version, lịch sử event và side effect liên quan.

### 8.2. Chạy SELECT trước UPDATE

Luôn chạy truy vấn đọc với cùng điều kiện dự kiến dùng cho câu lệnh sửa:

```sql
SELECT order_id, status, version, updated_at
FROM orders
WHERE order_id IN ('ORD-1001', 'ORD-1008', 'ORD-1012')
ORDER BY order_id;
```

Đối chiếu từng hàng với danh sách đã được duyệt. Nếu số lượng, trạng thái hoặc version không đúng như dự kiến, dừng và điều tra trước khi chạy lệnh ghi.

### 8.3. Dùng transaction và giới hạn phạm vi

Ví dụ dưới đây minh họa cách sửa có kiểm tra trên PostgreSQL. Điều kiện `status` và `version` chỉ là ví dụ; phải thay bằng invariant thật của nghiệp vụ.

```sql
BEGIN;

UPDATE orders
SET status = 'PAID',
    version = version + 1,
    updated_at = now()
WHERE order_id IN ('ORD-1001', 'ORD-1008', 'ORD-1012')
  AND status = 'PAYMENT_PENDING'
  AND version = 7;

-- Kiểm tra số hàng đã thay đổi và đọc lại trạng thái trong transaction.
SELECT order_id, status, version, updated_at
FROM orders
WHERE order_id IN ('ORD-1001', 'ORD-1008', 'ORD-1012')
ORDER BY order_id;

-- Chỉ COMMIT sau khi kết quả khớp với phạm vi và invariant đã duyệt.
-- Nếu không khớp, chạy ROLLBACK.
```

Trong thực tế, người vận hành phải kiểm tra số hàng được cập nhật trước khi commit. Nếu DB client hỗ trợ script có điều kiện hoặc stored procedure để so sánh row count, hãy dùng cơ chế đó nhằm tự động rollback khi số lượng không đúng. Không copy nguyên ví dụ này vào production khi chưa điều chỉnh điều kiện và trạng thái nghiệp vụ.

### 8.4. Giữ audit trail

Ghi nhận repair ID, incident ID, người thực hiện, thời điểm, script version, danh sách ID bị ảnh hưởng và giá trị trước/sau. Nếu hệ thống có audit table, sử dụng nó theo chuẩn hiện hành. Tránh ghi đè hoặc xóa lịch sử nghiệp vụ để làm cho trạng thái mới trông như chưa từng có lỗi.

Nếu cần chạy repair nhiều lần, thiết kế script idempotent: chạy lại không tạo thêm thay đổi hoặc side effect. Có thể dùng một `repair_id` duy nhất để ghi nhận thao tác đã áp dụng, nhưng vẫn phải kiểm tra payload và phạm vi khi repair ID đã tồn tại.

### 8.5. Không xóa dấu vết idempotency để ép xử lý lại

Một lỗi thường gặp là xóa bản ghi inbox hoặc effect ledger rồi replay event với hy vọng consumer xử lý lại. Thao tác đó có thể làm hệ thống quên rằng payment đã thành công, email đã gửi hoặc vận đơn đã được tạo.

Trước khi thay đổi inbox, outbox, deduplication record hoặc external effect, phải xác định vai trò của từng bản ghi và đối chiếu với provider. Nếu cần thực hiện lại nghiệp vụ, hãy tạo một lần thực hiện mới với định danh nghiệp vụ mới theo quy tắc domain, hoặc dùng một quy trình replay đã được thiết kế. Không xóa khóa idempotency cũ chỉ để vượt qua unique constraint.

## 9. Các luồng phải kiểm soát ngoài listener chính

Pause một listener chính vẫn chưa đủ nếu dữ liệu bị ảnh hưởng có thể được ghi qua một đường khác.

### 9.1. Retry topic và DLT

Spring Kafka có thể sử dụng retry topic hoặc DLT để chuyển record lỗi sang một luồng khác. Hãy xác định listener nào tiêu thụ các topic đó. Nếu repair đang xử lý một event có thể xuất hiện ở retry topic, phải kiểm soát cả listener retry.

Không replay DLT trong lúc sửa dữ liệu. Record trong DLT có thể cũ hơn trạng thái hiện tại của aggregate; phát lại nó mà không kiểm tra version hoặc business state có thể đảo ngược một quyết định mới hơn.

### 9.2. Scheduled job và batch process

Một job đối soát, batch import hoặc scheduler có thể tiếp tục ghi DB dù Kafka listener đã pause. Tạm dừng job liên quan theo cơ chế quản trị của ứng dụng và ghi nhận trạng thái. Nếu job đã chạy, chờ nó hoàn thành hoặc phân loại transaction đang thực hiện trước khi sửa.

### 9.3. API và thao tác quản trị

Nếu REST API hoặc màn hình admin có thể cập nhật cùng aggregate, hãy bật maintenance mode hoặc chặn chức năng ghi trong phạm vi cần thiết. Chỉ thông báo cho người vận hành là “đang bảo trì” không tạo ra một rào chắn kỹ thuật; cần xác nhận request ghi mới thực sự bị từ chối hoặc được đưa vào hàng đợi an toàn.

### 9.4. Outbox publisher và CDC

Nếu DB repair tạo hoặc thay đổi bản ghi outbox, publisher có thể phát event mới sau khi consumer resume. CDC connector cũng có thể phát thay đổi dữ liệu sang Kafka hoặc hệ thống khác. Hãy hiểu liệu repair có được xem là thay đổi nghiệp vụ cần publish hay chỉ là điều chỉnh dữ liệu vận hành.

Không tự ý tắt outbox publisher hoặc CDC nếu chưa biết ảnh hưởng tới các luồng khác. Nếu cần tạm dừng, ghi lại checkpoint và kế hoạch xử lý các bản ghi chờ sau khi khôi phục.

### 9.5. Producer upstream

Pause consumer không ngăn producer ghi record mới. Kafka tiếp tục lưu record và lag có thể tăng trong thời gian bảo trì. Nếu lượng record tăng nhanh hoặc upstream tiếp tục phát dữ liệu sai, cần phối hợp tạm dừng chức năng phát sinh event, áp dụng rate limit hoặc chuyển upstream sang trạng thái bảo trì.

Không xóa record Kafka chỉ để giảm lag. Record có thể là bằng chứng cần thiết cho điều tra và phục hồi.

## 10. Phân biệt pause, stop và reset offset

Ba thao tác này có tác động khác nhau và không nên dùng thay thế cho nhau.

| Thao tác | Tác động chính | Khi nào dùng |
|---|---|---|
| Pause container | Tạm dừng nhận record mới, giữ consumer tham gia group và tiếp tục poll theo cơ chế container | Điều tra hoặc sửa dữ liệu trong một khoảng dừng có kiểm soát |
| Stop container | Dừng listener; consumer rời group và partition có thể được rebalance cho member khác | Bảo trì tiến trình hoặc chuẩn bị thao tác yêu cầu group không còn member hoạt động |
| Reset offset | Thay đổi vị trí group sẽ đọc tiếp trong log | Replay hoặc bỏ qua một phạm vi record theo kế hoạch rõ ràng |

Nếu pause một consumer nhưng các member khác vẫn hoạt động, các member khác có thể tiếp tục xử lý partition của chúng. Nếu stop một member, partition của nó có thể được giao cho member còn lại. Vì vậy, stop một pod không đồng nghĩa dừng toàn bộ group.

Một số thao tác reset offset yêu cầu consumer group không có member hoạt động. Consumer đang pause vẫn có thể là member đang hoạt động. Nếu cần reset offset, phải dừng toàn bộ consumer thuộc group theo kế hoạch, xác nhận group inactive, ghi lại offset hiện tại và thực hiện quy trình replay riêng.

Lệnh reset offset có thể làm record được xử lý lại hoặc bị bỏ qua. Nó không sửa dữ liệu DB và không tự kiểm tra side effect. Trước khi replay, cần chứng minh consumer idempotent, effect key được giữ nguyên và provider có thể trả lại kết quả của lần thực hiện trước. Với provider không hỗ trợ idempotency, cần reconciliation trước khi phát lại các event có kết quả chưa xác định.

## 11. Resume theo từng bước

Sau khi repair hoàn tất, không nên bật tất cả luồng cùng lúc mà chưa kiểm tra trạng thái. Resume là một phần của incident response và cần có điều kiện bắt đầu, tín hiệu giám sát và tiêu chí dừng.

### 11.1. Xác minh dữ liệu sau sửa

Trước tiên, chạy lại các truy vấn đọc đã dùng để xác định phạm vi. So sánh số hàng, trạng thái, version, quan hệ và invariant. Kiểm tra các bản ghi inbox, outbox, effect ledger và provider reference có còn nhất quán không.

Nếu repair đã tạo ra thay đổi cần phát event, xác nhận outbox record và payload đúng. Nếu repair chỉ là sửa dữ liệu nội bộ, xác nhận nó không vô tình kích hoạt một luồng publish hoặc CDC ngoài dự kiến.

### 11.2. Kiểm tra điều kiện resume

Chỉ resume khi:

- Script repair đã hoàn tất và số hàng thay đổi đúng với phạm vi đã duyệt.
- Không còn transaction hoặc tác vụ nền chưa rõ trạng thái có thể ghi đè dữ liệu.
- Các side effect có kết quả không xác định đã được ghi nhận và có kế hoạch reconciliation.
- Retry/DLT không còn một replay ngoài kế hoạch đang chờ chạy.
- Các writer khác được phép hoạt động trở lại theo đúng thứ tự.
- Dashboard, log và người trực incident sẵn sàng theo dõi giai đoạn khôi phục.

Nếu còn một side effect `UNKNOWN`, không nên tự động đổi nó thành `FAILED` để cho phép consumer tiếp tục. Giữ trạng thái chưa xác định và dùng quy trình đối soát đã định nghĩa.

### 11.3. Resume listener có kiểm soát

Với listener container đã pause, gọi `resume()` qua cùng cơ chế điều khiển. Nếu có nhiều replica, xác nhận mọi instance được resume đúng phạm vi. Không dựa vào một lệnh chạy ở một pod để kết luận toàn bộ group đã hoạt động trở lại.

Nếu hệ thống hỗ trợ pause theo partition, có thể resume một partition hoặc một nhóm nhỏ trước, sau đó quan sát kết quả rồi mở rộng. Với listener concurrency cao, cân nhắc khôi phục ở mức tải thấp theo cấu hình vận hành được phê duyệt.

### 11.4. Theo dõi sau resume

Theo dõi trong một khoảng thời gian đủ để bao phủ chu kỳ xử lý bình thường và lịch retry liên quan. Các tín hiệu cần quan sát gồm:

| Tín hiệu | Điều cần xác nhận |
|---|---|
| Consumer lag | Tăng hoặc giảm theo tốc độ dự kiến; không tăng bất thường kéo dài |
| Listener error rate | Không xuất hiện lại lỗi đã gây incident |
| Retry và DLT volume | Không tạo vòng lặp retry hoặc tăng đột biến |
| Duplicate detection | Không tăng số event trùng hoặc xung đột idempotency key |
| DB constraint và lock | Không có lỗi constraint, deadlock hoặc lock wait bất thường |
| Business state | Aggregate tiếp tục chuyển trạng thái theo quy tắc domain |
| External effects | Không phát sinh charge, email, shipment hoặc request trùng |
| `UNKNOWN` effects | Số lượng và tuổi bản ghi giảm theo kế hoạch reconciliation |

Nếu phát hiện dữ liệu sai xuất hiện lại, side effect trùng hoặc retry loop, pause lại phạm vi liên quan và giữ nguyên bằng chứng. Không tiếp tục sửa liên tiếp khi chưa hiểu vì sao lỗi tái diễn.

## 12. Ví dụ incident: sửa trạng thái đơn hàng sau khi consumer ghi sai

Giả sử `billing-service` nhận event `OrderPaid` và cập nhật `orders.status`. Một lỗi mapping khiến một số đơn đã thanh toán bị ghi thành `PAYMENT_PENDING`. Người vận hành xác định có 12 đơn bị ảnh hưởng.

**Bước 1 — Mở incident và xác định phạm vi.** Ghi 12 `orderId`, event ID, topic, partition, offset và thời điểm xử lý. Xác định listener `billing-order-listener`, group `billing-orders-v2`, tất cả pod đang chạy, retry listener, DLT listener và các job có thể cập nhật `orders`.

**Bước 2 — Ngăn phát sinh thêm dữ liệu sai.** Nếu lỗi mapping vẫn đang chạy, tạm dừng upstream phát event sai hoặc bật biện pháp ngăn luồng ghi theo incident procedure. Pause listener liên quan trên mọi replica. Pause retry listener có thể phát lại cùng event. Kiểm soát admin API hoặc scheduler nếu chúng có thể ghi vào các đơn này.

**Bước 3 — Drain và ghi nhận offset.** Chờ callback đang chạy hoàn tất trong giới hạn đã định. Kiểm tra request thanh toán chưa có kết quả rõ ràng. Ghi committed offset và log end offset của các partition liên quan; không reset offset.

**Bước 4 — Đối chiếu dữ liệu.** Với từng đơn, kiểm tra payment attempt, provider reference, effect ledger, event inbox và lịch sử chuyển trạng thái. Xác nhận cả 12 đơn thực sự đã thanh toán. Nếu có đơn chưa xác nhận được kết quả provider, đưa nó vào danh sách reconciliation riêng.

**Bước 5 — Repair có giới hạn.** Lưu snapshot giá trị trước sửa. Chạy `SELECT` với đúng 12 ID, kiểm tra số lượng và version. Thực hiện `UPDATE` có điều kiện để chỉ sửa những hàng đang ở trạng thái sai và có version dự kiến. Đọc lại trong transaction, xác nhận kết quả rồi commit. Ghi repair ID và giá trị trước/sau.

**Bước 6 — Kiểm tra điều kiện khôi phục.** Xác nhận 12 đơn có trạng thái đúng, payment attempt và provider reference không thay đổi ngoài dự kiến, effect ledger không bị xóa hoặc tạo lại. Xác nhận lỗi mapping đã được xử lý hoặc có biện pháp ngăn lỗi tái diễn trước khi mở consumer.

**Bước 7 — Resume và giám sát.** Resume listener và retry path theo thứ tự đã định. Theo dõi các đơn bị ảnh hưởng, duplicate detection, lag, lỗi DB và side effect. Nếu một event cũ làm trạng thái đơn quay lại `PAYMENT_PENDING`, pause lại và điều tra điều kiện cập nhật hoặc version check trong consumer.

Ví dụ này cho thấy pause chỉ là một bước trong quy trình. Sửa đúng 12 hàng vẫn chưa đủ nếu một event cũ có thể ghi đè trạng thái sau khi listener hoạt động trở lại.

## 13. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Pause một pod và cho rằng toàn bộ group đã dừng | Các pod khác vẫn xử lý partition được giao | Kiểm tra mọi instance và listener liên quan |
| Chạy SQL ngay sau khi gửi lệnh pause | Callback hoặc transaction cũ vẫn đang chạy | Chờ xác nhận pause và drain công việc đang xử lý |
| Chỉ pause listener chính | Retry, DLT, scheduler hoặc API vẫn ghi dữ liệu | Lập bản đồ tất cả writer và đường replay |
| Kill pod để dừng nhanh | Message có thể được giao lại; side effect có thể đã thành công | Phân loại in-flight work và unknown outcome trước khi dừng |
| Reset offset để consumer bỏ qua lỗi | Có thể mất record hoặc replay ngoài dự kiến | Tách offset reset thành kế hoạch replay có kiểm soát |
| Xóa inbox/effect record để xử lý lại | Mất dấu side effect đã thực hiện và tạo duplicate | Đối soát provider, giữ idempotency history |
| Sửa trạng thái DB mà không sửa nguyên nhân | Consumer ghi sai trở lại sau resume | Khắc phục code/config hoặc chặn điều kiện lỗi trước khi resume |
| Resume tất cả writer cùng lúc | Tải tăng đột ngột và khó xác định nguồn lỗi tái diễn | Mở lại theo thứ tự, quan sát và tăng tải từng bước |
| Không lưu giá trị trước sửa | Khó audit hoặc phục hồi khi repair sai | Snapshot, audit trail và repair ID trước khi ghi |

## 14. Mẫu ghi nhận thao tác pause và repair

Trong incident, dùng một mẫu ghi nhận ngắn và cập nhật theo từng bước giúp người trực sau hiểu chính xác trạng thái hệ thống:

```text
Incident ID:
Người điều phối:
Lý do pause:

Affected service:
Listener IDs:
Consumer group IDs:
Pods / instances:
Topics / partitions:
Retry topics / DLT:
Other writers paused or blocked:

Pause requested at:
Pause confirmed at:
In-flight callbacks remaining:
Async tasks remaining:
Unknown external requests:

Committed offsets captured at:
Database snapshot / backup reference:
Affected entity IDs:
Expected row count:
Actual row count before repair:
Repair script version:
Repair ID:
Rows changed:
Post-repair invariants checked:

Resume approved by:
Resume time:
Post-resume observations:
Remaining reconciliation items:
Incident status:
```

Mẫu này nên được lưu trong hệ thống incident hoặc audit log được tổ chức sử dụng. Không đưa credential, access token, dữ liệu thẻ hoặc thông tin cá nhân không cần thiết vào ghi chú vận hành.

## 15. Checklist trước khi sửa dữ liệu

Trước khi chạy bất kỳ repair script nào, xác nhận các điểm sau:

- Đã xác định invariant nghiệp vụ cần khôi phục và danh sách entity bị ảnh hưởng.
- Đã xác định mọi listener, consumer group, replica, retry topic và DLT có thể ghi dữ liệu liên quan.
- Đã kiểm soát các writer ngoài Kafka như API, scheduler, batch, admin tool và CDC.
- Đã gửi pause tới đúng container và xác nhận pause có hiệu lực trên mọi instance liên quan.
- Đã drain hoặc phân loại callback, async task, DB transaction và request bên ngoài đang chạy.
- Đã ghi lại topic, partition, offset, group ID và trạng thái consumer trước sửa.
- Đã snapshot dữ liệu trước sửa và lưu log, event ID, effect key cùng provider reference cần thiết.
- Đã chạy SELECT với cùng điều kiện dự kiến dùng cho UPDATE và xác nhận số hàng chính xác.
- Repair script có điều kiện giới hạn, audit trail, kiểm tra row count và cách rollback hoặc compensation.
- Không xóa inbox, outbox, deduplication record hoặc effect ledger chỉ để ép replay.
- Có tiêu chí rõ ràng để resume, theo dõi sau resume và pause lại nếu lỗi tái diễn.

## Kết luận

Trong incident response, pause trước khi sửa dữ liệu tạo ra khoảng dừng cần thiết để hiểu và kiểm soát các luồng ghi. Với Spring Kafka, cần điều khiển đúng listener container, xác nhận mọi replica đã pause, drain công việc đang chạy và ghi lại trạng thái offset. Sau đó mới snapshot dữ liệu, xác định invariant và chạy repair có giới hạn.

Pause một listener không dừng producer, retry path, DLT, scheduler, API hoặc consumer group khác. Nó cũng không hủy side effect đã gửi tới hệ thống bên ngoài. Vì vậy, phạm vi pause phải dựa trên toàn bộ đường ghi thực tế của dữ liệu bị ảnh hưởng.

Sau repair, xác minh lại dữ liệu và side effect, khôi phục listener theo thứ tự có kiểm soát, rồi theo dõi lag, retry, duplicate và trạng thái nghiệp vụ. Nếu dữ liệu sai xuất hiện trở lại, pause phạm vi liên quan và điều tra nguyên nhân trước khi sửa tiếp. Cách làm này giúp bảo toàn bằng chứng, giảm race condition và tránh biến một thao tác sửa dữ liệu thành sự cố thứ hai.
