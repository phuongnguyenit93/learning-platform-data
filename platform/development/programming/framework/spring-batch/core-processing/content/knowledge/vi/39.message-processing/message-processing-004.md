# Acknowledgement theo chunk

Trong Spring Batch, khi một Step đọc message từ broker như Kafka, RabbitMQ, JMS hoặc Amazon SQS, ứng dụng phải quyết định thời điểm xác nhận message đã được xử lý thành công. Hành động xác nhận này thường được gọi là acknowledgement (ack). Với batch processing, một cách tổ chức phổ biến là xử lý nhiều message trong một chunk rồi mới ack cả nhóm sau khi dữ liệu nghiệp vụ đã commit.

Điểm quan trọng là **chunk commit và broker acknowledgement là hai thao tác riêng**. Transaction của Spring Batch thường commit dữ liệu database ở ranh giới chunk. Broker lại có cơ chế ack, commit offset, delete message hoặc commit session riêng. Nếu ack trước khi database commit, message có thể bị mất khi chunk rollback. Nếu database commit trước nhưng ack thất bại, message có thể được gửi lại và tạo xử lý trùng.

Vì vậy, acknowledgement theo chunk cần được thiết kế cùng với transaction boundary, redelivery, idempotency, checkpoint, retry và cơ chế đối soát. Không có một cách ack duy nhất áp dụng giống nhau cho mọi broker.

## 1. Acknowledgement là gì?

Broker giữ message cho đến khi consumer xác nhận đã xử lý hoặc cho đến khi chính sách giao nhận quyết định message được loại bỏ. Tùy broker, acknowledgement có thể mang hình thức:

| Broker | Hành động xác nhận |
| --- | --- |
| JMS | Acknowledge message hoặc commit transacted session |
| RabbitMQ | Basic ACK cho delivery tag |
| Kafka | Commit consumer offset |
| Amazon SQS | Delete message bằng receipt handle |

Các thao tác này không hoàn toàn tương đương. JMS có acknowledgement mode/session transaction; RabbitMQ ack theo delivery tag; Kafka lưu offset tiếp theo cần đọc; SQS xóa message khỏi queue sau khi nhận receipt handle.

Ack thường có nghĩa consumer đã hoàn thành trách nhiệm xử lý message theo contract của hệ thống. Nó không nhất thiết chứng minh mọi side effect ở tất cả hệ thống ngoài đã hoàn tất atomic.

## 2. Vì sao ack theo chunk?

Giả sử một Step xử lý 100 message trong một chunk:

~~~text
Broker
  |
  v
ItemReader nhận 100 messages
  |
  v
Processor kiểm tra và chuyển đổi
  |
  v
Writer ghi dữ liệu nghiệp vụ
  |
  v
Database transaction COMMIT
  |
  v
ACK nhóm 100 messages
~~~

Ack từng message ngay sau khi đọc có thể làm tăng số lần giao tiếp với broker và làm message biến mất trước khi chunk commit. Ack theo chunk giúp giảm số lần xác nhận và gắn trách nhiệm ack với kết quả của một nhóm xử lý.

Ví dụ lợi ích:

- Giảm số lần commit offset hoặc gửi ack khi broker hỗ trợ xác nhận theo nhóm.
- Chỉ xác nhận message sau khi toàn bộ thao tác database của chunk đã commit.
- Dễ đối chiếu số message nhận, xử lý, skip và ack.
- Có thể điều chỉnh chunk size để cân bằng throughput, độ trễ và phạm vi redelivery.

Nhưng chunk lớn cũng có nghĩa nhiều message cùng chờ ack. Nếu chunk thất bại, toàn bộ nhóm có thể được giao lại. Điều này làm tăng chi phí retry và yêu cầu idempotency tốt hơn.

## 3. Chunk transaction và broker ack là hai ranh giới

Trong chunk-oriented Step, Spring Batch thực hiện một transaction cho mỗi chunk theo transaction manager được cấu hình:

~~~text
BEGIN CHUNK TRANSACTION
    |
    +--> read items
    |
    +--> process items
    |
    +--> write business data
    |
    +--> update Step metadata/checkpoint
    |
COMMIT CHUNK TRANSACTION
    |
    v
ACK broker messages
~~~

Đây là thứ tự mong muốn khi database là nơi lưu kết quả nghiệp vụ và broker không tham gia cùng transaction. Ack chỉ diễn ra sau khi chunk commit thành công.

Nếu ack trước commit:

~~~text
ACK message
    |
    v
Database write
    |
    v
Chunk rollback
~~~

Broker có thể không gửi lại message vì đã được xác nhận, trong khi dữ liệu nghiệp vụ không tồn tại. Đây là nguy cơ mất message.

Nếu commit trước ack:

~~~text
Database COMMIT
    |
    v
ACK message thất bại
    |
    v
Broker redeliver
    |
    v
Consumer xử lý lại message
~~~

Trường hợp này có thể tạo duplicate delivery nhưng dữ liệu đã commit. Đây là tình huống thường được chấp nhận trong hệ thống at-least-once nếu writer idempotent.

## 4. Spring Batch không tự định nghĩa ack cho mọi ItemReader

ItemReader có hợp đồng đọc item; bản thân interface ItemReader không định nghĩa một giao thức acknowledgement chung cho Kafka, RabbitMQ, JMS và SQS.

Reader tùy chỉnh hoặc integration module phải quyết định:

- Message được nhận từ broker bằng API nào?
- Broker có xóa message ngay khi receive hay giữ lại đến ack?
- Delivery token, delivery tag, offset hoặc receipt handle được lưu ở đâu?
- Ack được gọi tại thời điểm nào?
- Điều gì xảy ra khi chunk rollback?
- Làm thế nào để broker giao lại message?
- Ack có thể được gom theo chunk hay chỉ theo từng message?

Không nên viết một reader chỉ gọi receive() rồi giả định Spring Batch sẽ tự ack sau khi writer thành công. Cần xác định rõ semantics của thư viện broker và cấu hình transaction.

## 5. Gắn acknowledgement với ranh giới chunk

Khi broker không tham gia transaction database, một cách triển khai là giữ delivery metadata của các message đã đọc, rồi ack chúng trong callback sau khi chunk commit.

Spring Batch có ChunkListener:

- beforeChunk được gọi trước khi chunk được xử lý trong transaction.
- afterChunk được gọi sau khi chunk đã commit thành công.
- afterChunkError được gọi khi xử lý chunk gặp lỗi.

Một thiết kế khái quát:

~~~text
beforeChunk
    |
    v
Reader nhận message và ghi nhận delivery token
    |
    v
Processor / Writer
    |
    +--> thành công: transaction commit
    |                   |
    |                   v
    |              afterChunk
    |                   |
    |                   v
    |              ACK các token
    |
    +--> lỗi: rollback
                        |
                        v
                 afterChunkError
                        |
                        v
              Không ACK; để broker redeliver
~~~

Ví dụ listener minh họa:

~~~java
public class ChunkAcknowledgementListener
        implements ChunkListener {

    private final ChunkAckManager ackManager;

    public ChunkAcknowledgementListener(ChunkAckManager ackManager) {
        this.ackManager = ackManager;
    }

    @Override
    public void afterChunk(ChunkContext context) {
        ackManager.acknowledgeCommittedChunk();
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        ackManager.releaseForRedelivery();
    }
}
~~~

Đây là cấu trúc minh họa. ChunkAckManager phải biết chính xác delivery token nào thuộc chunk vừa commit, và cách release/requeue phụ thuộc broker. Không lưu token trong static collection hoặc một singleton list dùng chung cho các StepExecution/worker.

### Vì sao afterChunk phù hợp?

afterChunk chạy sau khi chunk đã commit. Nếu listener ack ở beforeChunk hoặc trong writer trước khi transaction commit, message có thể bị xác nhận dù database transaction sau đó rollback.

Tuy nhiên, afterChunk cũng tạo ra một khoảng thời gian giữa database commit và broker ack. Nếu process dừng trong khoảng đó, broker có thể redeliver message đã được database xử lý. Do đó, ack sau commit vẫn cần idempotency.

### afterChunkError không tự bảo đảm redelivery

Không ack chỉ có nghĩa consumer chưa xác nhận thành công. Việc message được giao lại ngay hay sau đó phụ thuộc broker:

- RabbitMQ có thể requeue khi nack/reject hoặc khi channel/connection đóng.
- Kafka cần consumer không commit offset và có thể phải seek/restart theo offset đã commit.
- SQS message thường trở nên visible sau visibility timeout hoặc khi visibility được đặt về 0.
- JMS phụ thuộc session transacted, acknowledgement mode và việc session recover/rollback.

Một listener không thể tự tạo redelivery nếu reader/broker adapter không có cơ chế phù hợp.

## 6. Quản lý delivery token theo chunk

Để ack theo chunk, ứng dụng cần liên kết item đã đọc với token của broker:

| Broker | Metadata cần giữ |
| --- | --- |
| RabbitMQ | Channel và delivery tag |
| Kafka | Topic, partition, offset và consumer/transaction context |
| SQS | Queue URL, message ID và receipt handle hiện tại |
| JMS | Message/session hoặc transaction context theo provider |

Không phải token nào cũng có thể lưu rồi sử dụng tùy ý sau này. Ví dụ delivery tag của RabbitMQ gắn với channel đã nhận message; dùng tag trên channel khác là sai. Receipt handle của SQS gắn với lần receive cụ thể; lần redelivery có thể có receipt handle mới. Kafka offset phải được commit đúng partition và theo thứ tự an toàn.

Một AckManager thường cần:

- Gắn token với StepExecution hoặc chunk hiện tại.
- Thu thập token khi reader nhận item.
- Xác định item nào thuộc chunk đang commit.
- Ack đúng token sau commit.
- Giữ trạng thái an toàn khi rollback.
- Xử lý lỗi ack và quan sát redelivery.
- Tránh dùng chung state giữa các thread hoặc partition.

Với reader có thể đọc trước (prefetch) nhiều hơn chunk size, phải phân biệt token đã được đưa vào chunk với token chỉ mới được buffer. Không ack các message chưa được writer xử lý hoặc chưa được policy xác nhận là hoàn tất.

## 7. Xử lý item bị filter hoặc skip

Không phải mọi message được reader nhận đều được ghi bởi writer:

- Processor trả null có nghĩa item bị filter.
- Skip policy có thể bỏ qua item sau lỗi đọc, xử lý hoặc ghi tùy cấu hình.
- Một item có thể được ghi sang reject/DLQ thay vì bảng nghiệp vụ chính.

Khi chunk commit thành công, các message đã được xử lý theo chính sách của Step có thể được ack, kể cả item bị filter, nhưng chỉ khi việc filter/skip là một kết quả nghiệp vụ được chấp nhận.

Ví dụ:

~~~text
Chunk nhận 5 messages:
  M1 -> ghi bảng chính
  M2 -> filter có chủ đích
  M3 -> ghi bảng chính
  M4 -> lỗi dữ liệu, lưu reject record
  M5 -> ghi bảng chính

Nếu transaction và reject handling commit thành công:
  Có thể ACK M1, M2, M3, M4, M5
~~~

Nếu M4 bị skip nhưng raw message không được lưu ở đâu, ack M4 có thể làm mất dữ liệu cần điều tra. Hãy xác định rõ skip có nghĩa là bỏ qua hợp lệ hay phải chuyển sang reject/DLQ.

Nếu reject record được ghi cùng database transaction của chunk, ack sau commit có thể an toàn theo mô hình at-least-once. Nếu reject message được publish ra broker khác, đó lại là một side effect ngoài transaction và cần outbox hoặc idempotency.

## 8. JMS acknowledgement và chunk

JMS có các acknowledgement mode và transacted session. Hành vi cụ thể phụ thuộc cách tạo Session, connection factory, listener container hoặc reader adapter.

Các chế độ thường gặp:

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| AUTO_ACKNOWLEDGE | Provider tự acknowledge theo quy tắc của session sau khi message được receive/consumer xử lý theo API |
| CLIENT_ACKNOWLEDGE | Client gọi acknowledge trên message; semantics chuẩn JMS có thể acknowledge các message đã được session tiêu thụ |
| DUPS_OK_ACKNOWLEDGE | Provider có thể trì hoãn acknowledgement và cho phép duplicate delivery |
| SESSION_TRANSACTED | Receive và acknowledge được quản lý qua transaction của JMS Session; commit xác nhận, rollback phục hồi theo provider |

### AUTO_ACKNOWLEDGE có thể ack quá sớm

Nếu một ItemReader gọi receive() trên session AUTO_ACKNOWLEDGE, message có thể được acknowledge theo semantics của provider khi receive hoàn tất, trước khi processor và writer của chunk chạy xong.

Nếu chunk rollback sau đó, message có thể đã được broker xác nhận và không được giao lại. Vì vậy, không mặc định AUTO_ACKNOWLEDGE là ack sau chunk commit.

### CLIENT_ACKNOWLEDGE

CLIENT_ACKNOWLEDGE cho phép client chủ động acknowledge. Tuy nhiên, theo semantics JMS, acknowledge trên một message có thể xác nhận tất cả message đã được session tiêu thụ đến thời điểm đó. Cần kiểm soát session và thứ tự receive nếu muốn ack theo nhóm.

Nếu reader prefetch message cho chunk tiếp theo trên cùng session, một lần acknowledge có thể xác nhận nhiều message hơn số item đã commit. Điều này có thể gây mất message khi chunk sau chưa hoàn tất.

### SESSION_TRANSACTED

Một transacted JMS Session có thể phối hợp receive và acknowledge qua commit/rollback của session. Nhưng để database writer và JMS session cùng atomic, cần một transaction coordination strategy phù hợp, thường là JTA/XA nếu cả hai resource hỗ trợ.

Nếu JMS session commit riêng sau database commit, vẫn tồn tại cửa sổ duplicate delivery. Nếu JMS commit trước database commit, vẫn có nguy cơ mất message khi database rollback.

Không giả định Spring Batch chunk transaction tự động commit JMS Session chỉ vì reader dùng JMS. Kiểm tra transaction manager và connection/session được cấu hình thực tế.

## 9. RabbitMQ manual acknowledgement theo chunk

RabbitMQ manual ack sử dụng delivery tag gắn với channel. Consumer gửi basic.ack để xác nhận một delivery.

Với ack từng message:

~~~java
channel.basicAck(deliveryTag, false);
~~~

Tham số multiple=false xác nhận chỉ delivery tag được chỉ định.

Với ack nhiều delivery:

~~~java
channel.basicAck(lastDeliveryTag, true);
~~~

multiple=true xác nhận tất cả delivery tag chưa ack trên cùng channel đến và bao gồm tag được chỉ định.

Điều này hữu ích khi các message được xử lý tuần tự trên một channel và mọi delivery trước lastDeliveryTag đều đã hoàn tất.

### Điều kiện khi dùng multiple=true

- Delivery tag chỉ có ý nghĩa trong channel đã nhận message.
- Không ack delivery chưa được xử lý thành công.
- Không dùng last tag để ack nếu có delivery tag nhỏ hơn còn đang xử lý.
- Không chia sẻ channel không an toàn giữa nhiều thread.
- Phải xử lý channel đóng hoặc connection mất trước khi ack.

Nếu nhiều worker xử lý message song song, message có delivery tag thấp hơn có thể chưa hoàn tất trong khi tag cao hơn đã xong. Ack multiple=true ở tag cao sẽ xác nhận cả message thấp hơn, dù message đó chưa được xử lý. Trong trường hợp này, dùng ack từng message hoặc duy trì bộ theo dõi các delivery liên tục đã hoàn tất.

### Nack và requeue

Khi chunk rollback, có thể dùng basic.nack hoặc basic.reject với requeue=true để yêu cầu broker giao lại:

~~~java
channel.basicNack(deliveryTag, false, true);
~~~

Không requeue vô hạn message lỗi vĩnh viễn. Message có thể tạo vòng lặp giao lại, tiêu tốn tài nguyên và làm nghẽn queue. Dùng retry có giới hạn, dead-letter exchange hoặc parking queue theo chính sách.

## 10. Kafka offset commit theo chunk

Kafka không ack từng record bằng delivery tag. Consumer quản lý offset theo từng topic-partition. Khi commit offset N, consumer thông báo rằng các record có offset nhỏ hơn N đã được xử lý theo semantics của consumer group.

Ví dụ một partition:

~~~text
Partition 0:
  offset 10
  offset 11
  offset 12
  offset 13

Chunk xử lý 10, 11, 12
DB commit thành công
Commit offset 13
~~~

Offset được commit là vị trí tiếp theo cần đọc, không phải offset cuối cùng đã xử lý. Nếu chunk chứa offset 10, 11, 12 thì committed offset thường là 13.

### Tắt auto commit khi cần phối hợp với chunk

Nếu consumer tự động commit offset theo thời gian, offset có thể được commit trước khi writer database hoàn tất. Khi chunk rollback, Kafka có thể không gửi lại các record đã commit.

Với mô hình chunk processing, thường cần kiểm soát auto commit và chỉ commit offset sau khi chunk đã commit dữ liệu nghiệp vụ.

### Commit theo partition

Một poll có thể trả record từ nhiều partition:

~~~text
Topic orders:
  partition 0: offsets 20, 21
  partition 1: offsets 7, 8, 9
~~~

Sau khi chunk hoàn tất, cần commit offset riêng cho từng partition:

- partition 0: next offset 22.
- partition 1: next offset 10.

Không dùng một offset chung cho tất cả partition.

### Chỉ commit offset liên tục đã hoàn tất

Nếu xử lý song song:

~~~text
partition 0:
  offset 20 -> đang xử lý
  offset 21 -> hoàn tất
  offset 22 -> hoàn tất
~~~

Không được commit offset 23 vì offset 20 chưa hoàn tất. Commit offset 23 sẽ khiến consumer group bỏ qua offset 20 sau restart.

Chỉ commit offset tiếp theo sau dãy offset liên tục đã xử lý thành công. Nếu xử lý song song, cần theo dõi completion theo partition và không vượt qua gap.

### Chunk commit và consumer rebalance

Kafka consumer có thể bị rebalance khi mất heartbeat, vượt thời gian poll hoặc group membership thay đổi. Nếu partition bị thu hồi trong khi chunk đang chạy, commit offset có thể thất bại hoặc consumer không còn quyền commit partition đó.

Thiết kế cần:

- Giới hạn thời gian xử lý chunk phù hợp với max.poll.interval.ms.
- Quản lý pause/resume hoặc poll loop khi xử lý dài.
- Xử lý commit failure và partition revocation.
- Không commit offset của partition không còn sở hữu.
- Dùng idempotent writer để xử lý redelivery sau rebalance.

Không giữ một KafkaConsumer và gọi nó đồng thời từ nhiều thread; KafkaConsumer không thread-safe. Nếu cần parallel processing, tổ chức consumer thread và worker handoff theo mô hình được hỗ trợ, đồng thời quản lý offset liên tục.

## 11. Spring Kafka và acknowledgement mode

Spring Kafka cung cấp listener container và các acknowledgement mode. Một số mode phổ biến:

| Ack mode | Ý nghĩa khái quát |
| --- | --- |
| RECORD | Commit offset sau khi từng record listener xử lý xong |
| BATCH | Commit offset sau khi các record từ một poll batch được xử lý xong |
| MANUAL | Listener gọi acknowledge() |
| MANUAL_IMMEDIATE | Acknowledge có thể commit ngay tùy thread và cấu hình |

Các mode này thuộc Spring Kafka listener container. Chúng không tự động đồng nhất với chunk boundary của một Spring Batch Step.

Nếu một Spring Batch ItemReader tự dùng KafkaConsumer, reader/adapter phải tự phối hợp offset và chunk commit. Nếu dùng Spring Kafka listener để đẩy message vào Job hoặc queue trung gian, cần xác định listener ack chỉ sau khi message đã được chuyển giao bền vững cho batch workflow.

Không giả định AckMode.BATCH có nghĩa là ack theo chunk Spring Batch. Một poll batch của Kafka và một chunk của Spring Batch có thể có kích thước, thời điểm và ranh giới khác nhau.

## 12. Amazon SQS và delete theo chunk

SQS không dùng ack API giống RabbitMQ. Khi consumer nhận message, message trở nên invisible trong khoảng visibility timeout. Để xác nhận xử lý, consumer gọi DeleteMessage với receipt handle của lần receive hiện tại.

Luồng phù hợp với chunk:

~~~text
ReceiveMessage
    |
    v
Giữ message ID + receipt handle
    |
    v
Spring Batch xử lý chunk
    |
    v
Database COMMIT
    |
    v
DeleteMessageBatch cho các receipt handle
~~~

SQS hỗ trợ batch delete với giới hạn số entry cho mỗi request; ứng dụng cần chia nhóm theo giới hạn API và kiểm tra kết quả từng entry. HTTP request thành công không đồng nghĩa mọi entry đều được xóa thành công.

### Visibility timeout

Nếu chunk xử lý lâu hơn visibility timeout, message có thể trở lại visible và được consumer khác nhận trước khi chunk hiện tại hoàn tất.

Giải pháp:

- Đặt visibility timeout phù hợp với thời gian xử lý dự kiến.
- Dùng ChangeMessageVisibility để gia hạn khi cần.
- Theo dõi heartbeat/lease nếu xử lý dài.
- Dùng idempotency vì message vẫn có thể được giao nhiều lần.

Receipt handle có thể thay đổi qua mỗi lần receive. Phải xóa bằng receipt handle hiện tại, không dùng lại handle cũ từ lần nhận trước.

### Batch delete có partial failure

DeleteMessageBatch có thể trả thành công cho một số entry và thất bại cho entry khác. Ack manager phải đánh dấu chính xác entry đã xóa và entry cần xử lý lại. Không retry toàn bộ batch một cách mù quáng nếu việc xóa lại có thể dùng receipt handle cũ hoặc response trước đó đã thành công.

Nếu database đã commit nhưng một số delete thất bại, các message đó có thể được giao lại. Writer phải idempotent theo message/business ID.

## 13. Transactional acknowledgement và XA

Một số hệ thống có thể phối hợp transaction của database và broker bằng transaction manager phân tán hoặc resource transaction phù hợp.

Ví dụ với hai resource:

~~~text
Global transaction
    |
    +--> Database resource
    |
    +--> JMS resource
    |
    v
Coordinator quyết định commit/rollback
~~~

Với XA/JTA, coordinator có thể điều phối prepare và commit giữa các resource nếu database, broker, driver và transaction manager hỗ trợ. Cách này giảm cửa sổ lệch giữa DB commit và message acknowledgement.

Nhưng XA làm tăng độ phức tạp:

- Cần cấu hình XA datasource/connection factory.
- Cần transaction coordinator và recovery log.
- Có thể giữ lock/resource lâu hơn.
- Cần vận hành recovery khi coordinator hoặc node dừng.
- Không phải mọi broker/API hỗ trợ XA.

Không dùng XA chỉ để tránh viết idempotency. Nhiều hệ thống chọn at-least-once cùng outbox/inbox vì dễ vận hành và có thể mở rộng hơn.

## 14. Transaction synchronization sau commit

Trong một số ứng dụng, có thể đăng ký callback sau commit của transaction hiện tại để thực hiện ack:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                ackManager.acknowledgeCommittedChunk();
            }
        });
~~~

Callback afterCommit chỉ chạy khi transaction commit thành công. Nó phù hợp khi muốn ràng buộc thao tác ack với transaction hiện tại.

Tuy nhiên:

- Phải bảo đảm callback được đăng ký trong transaction của đúng chunk.
- Không đăng ký lặp nhiều callback cho cùng token.
- Phải phân biệt callback của chunk này với chunk khác.
- Ack failure xảy ra sau DB commit nên không thể rollback DB.
- Callback không thay thế cơ chế redelivery khi transaction rollback.

ChunkListener.afterChunk thường dễ hiểu hơn khi acknowledgement là một hành động theo chunk. Transaction synchronization hữu ích khi cần gắn hành động vào transaction cụ thể, nhưng cần quản lý state và exception cẩn thận.

Không ném exception từ callback sau commit rồi kỳ vọng database transaction được rollback. Transaction đã commit trước khi afterCommit chạy.

## 15. Idempotency khi message được giao lại

Với at-least-once delivery, duplicate là tình huống bình thường. Consumer phải chịu được việc cùng message được xử lý nhiều lần.

Ví dụ bảng inbox:

~~~sql
create table processed_message (
    message_id varchar(200) primary key,
    processed_at timestamp not null
);
~~~

Trong cùng database transaction của chunk:

1. Kiểm tra hoặc insert message_id vào processed_message.
2. Nếu ID đã tồn tại, xem message là duplicate đã xử lý.
3. Nếu insert mới thành công, thực hiện thay đổi nghiệp vụ.
4. Commit cả marker và dữ liệu nghiệp vụ cùng nhau.
5. Sau commit mới ack broker.

Pseudocode:

~~~java
@Transactional
public void processOnce(MessageRecord message) {
    boolean firstDelivery =
            inboxRepository.insertIfAbsent(message.messageId());

    if (!firstDelivery) {
        return;
    }

    orderService.apply(message);
}
~~~

Implementation insert-if-absent phụ thuộc database, ví dụ unique constraint, insert on conflict hoặc câu lệnh tương đương. Không thực hiện check rồi insert trong hai transaction tách biệt mà không có unique constraint, vì hai worker có thể cùng vượt qua bước check.

Nếu marker inbox commit cùng dữ liệu nghiệp vụ, redelivery sau ack failure sẽ được nhận diện và không tạo side effect nghiệp vụ lần hai.

### Business key và message ID

Message ID nên ổn định qua redelivery. Nếu producer tạo ID mới cho cùng một sự kiện khi retry publish, consumer không thể nhận ra duplicate bằng ID đó. Khi cần, dùng event ID hoặc business operation key do producer tạo một lần và giữ ổn định.

Không dùng offset đơn lẻ làm idempotency key toàn cục vì offset chỉ duy nhất trong một partition. Nếu dùng Kafka identity, key nên bao gồm cluster/topic/partition/offset hoặc event ID ổn định.

## 16. Transactional outbox khi cần phát message tiếp

Nếu batch vừa cập nhật database vừa phát một event sang broker khác, không nên dựa vào composite writer để thực hiện hai thao tác atomic.

Outbox pattern:

~~~text
Spring Batch chunk transaction
    |
    +--> update business tables
    |
    +--> insert outbox event
    |
    v
COMMIT
    |
    v
Outbox publisher
    |
    v
Broker
~~~

Outbox event và dữ liệu nghiệp vụ được commit cùng database transaction. Publisher riêng gửi event đến broker rồi đánh dấu đã gửi. Nếu publisher dừng sau khi gửi nhưng trước khi đánh dấu, event có thể được gửi lại; consumer cần idempotency.

Outbox giải quyết việc không mất event giữa DB commit và publish, nhưng không tạo exactly-once delivery end-to-end tự động.

## 17. Retry, nack, redelivery và dead-letter

Không phải lỗi nào cũng nên xử lý giống nhau:

| Loại lỗi | Hành vi thường phù hợp |
| --- | --- |
| Lỗi tạm thời của database hoặc API | Retry có giới hạn, không ack trước khi thành công |
| Message sai schema hoặc vi phạm nghiệp vụ | Reject/DLQ hoặc lưu reject record |
| Lỗi cấu hình hoặc thiếu credential | Dừng xử lý và cảnh báo |
| Ack thất bại sau DB commit | Cho phép redelivery và xử lý idempotently |
| Consumer chết giữa chunk | Broker redeliver hoặc message hết visibility/lease |

### Tránh poison message loop

Một message lỗi vĩnh viễn nếu luôn requeue có thể được giao đi giao lại liên tục:

~~~text
Receive
  |
  v
Processing fails
  |
  v
Requeue
  |
  v
Receive again
  |
  v
Processing fails ...
~~~

Dùng retry limit, delivery count, backoff và dead-letter queue. DLQ cần có quy trình điều tra, sửa dữ liệu và replay có kiểm soát.

Không ack message lỗi rồi chỉ log payload nếu dữ liệu cần được xử lý lại. Nếu chủ ý loại bỏ, phải ghi nhận reject reason và giữ raw message theo chính sách lưu trữ/bảo mật.

## 18. Chunk size và batch acknowledgement

Chunk size quyết định số item được xử lý trong một transaction chunk. Nếu một message tương ứng một item và mỗi message được ack theo chunk, chunk size cũng ảnh hưởng số message được ack cùng lúc.

| Chunk size | Đặc điểm |
| --- | --- |
| Nhỏ | Commit thường xuyên, ít message redelivery mỗi lần lỗi, nhiều lần ack hơn |
| Lớn | Ít lần commit/ack hơn, throughput có thể cao hơn, nhưng rollback/redelivery có phạm vi lớn hơn |

Không phải lúc nào chunk size cũng bằng số message broker nhận trong một poll. Reader có thể prefetch, buffer hoặc trả item từ nhiều partition. Cần theo dõi số token thực sự thuộc chunk.

Các yếu tố để chọn chunk size:

- Thời gian xử lý trung bình và p99.
- Transaction timeout.
- Visibility timeout hoặc broker lease.
- Kafka max.poll.interval và heartbeat.
- Số lượng message có thể redeliver sau rollback.
- Giới hạn batch ack/delete của broker.
- Bộ nhớ do prefetch và buffer.
- Mức độ idempotency của writer.

Đo throughput và thời gian ack thực tế. Chunk lớn hơn không luôn nhanh hơn nếu transaction giữ lock lâu hoặc message bị timeout trước khi xử lý xong.

## 19. Ack batch có giới hạn API

Một số broker chỉ cho phép xác nhận một số lượng message nhất định trong một request:

- SQS DeleteMessageBatch có giới hạn số entry mỗi request.
- Một số client/API có giới hạn kích thước batch hoặc số record.
- RabbitMQ basic.ack với multiple=true có thể ack dãy delivery tag trên cùng channel.
- Kafka commit offset là map offset theo partition, không phải danh sách ack từng record.

Nếu chunk lớn hơn giới hạn API, AckManager cần chia thành các nhóm nhỏ. Sau mỗi request, kiểm tra kết quả thành công/thất bại từng phần.

Không chia chunk database thành nhiều transaction chỉ để khớp giới hạn ack nếu điều đó làm thay đổi semantics nghiệp vụ. Có thể commit chunk một lần rồi gửi nhiều request ack/delete theo nhóm. Nếu một nhóm ack lỗi, phần còn lại có thể đã thành công; cần lưu kết quả và dựa vào idempotency cho phần bị redeliver.

## 20. Prefetch và buffer

Broker client có thể prefetch nhiều message trước khi Spring Batch yêu cầu read tiếp. Vì vậy:

~~~text
Broker prefetch: M1 ... M500
Spring Batch chunk size: 100

Chunk 1: M1-M100
Chunk 2: M101-M200
Chunk 3: M201-M300
...
~~~

Không ack toàn bộ 500 message sau khi chunk 1 commit. Chỉ ack các delivery thực sự thuộc chunk đã hoàn tất.

Nếu reader giữ buffer qua nhiều chunk, phải có cấu trúc tách token theo chunk. Khi chunk rollback, token của chunk thất bại phải được giữ để redelivery hoặc reprocess; token của chunk đã commit không được ack lại theo cách gây lỗi.

Prefetch quá lớn có thể:

- Tăng bộ nhớ.
- Tăng số message đang invisible hoặc unacked.
- Tăng redelivery sau consumer crash.
- Làm message chờ lâu hơn trước khi xử lý.
- Gây mất cân bằng giữa consumer.

Đặt prefetch dựa trên chunk size, concurrency và khả năng xử lý. Không dùng một giá trị lớn tùy tiện để tối đa hóa throughput.

## 21. Concurrency và ack theo chunk

Khi nhiều chunk chạy đồng thời, mỗi chunk phải có tập token độc lập. Không dùng một list ack chung trong singleton listener nếu nhiều thread có thể ghi vào cùng lúc.

Ví dụ sai về mặt thiết kế:

~~~java
private final List<DeliveryToken> allTokens = new ArrayList<>();
~~~

Nhiều thread có thể thêm/xóa token đồng thời; listener của chunk này có thể ack token của chunk khác.

Các lựa chọn quản lý:

- Một AckManager instance theo StepExecution/partition.
- Chunk-scoped context nếu framework và thiết kế cho phép.
- Thread-bound accumulator được dọn đúng ở commit/rollback.
- Token batch được truyền rõ qua wrapper item, rồi writer/ack coordinator phân nhóm theo chunk.

Với Kafka, commit offset phải giữ tính liên tục theo partition. Với RabbitMQ, multiple ack phải giữ thứ tự delivery trên cùng channel. Với SQS, mỗi receipt handle được xử lý độc lập và batch delete có thể trả partial failure.

Không giả định mọi broker đều cho phép ack message hoàn tất không theo thứ tự.

## 22. Restart và broker offset/checkpoint

Spring Batch ExecutionContext lưu checkpoint của reader/writer. Broker lại lưu acknowledgement state riêng. Hai hệ thống checkpoint này không tự động đồng bộ nếu không có integration transaction chung.

Ví dụ:

~~~text
Database/Batch:
  Chunk 1 commit
  Chunk 2 commit

Broker:
  Ack chunk 1 thành công
  Ack chunk 2 chưa thành công
~~~

Sau process restart, broker có thể giao lại message của chunk 2. Spring Batch có thể restart cùng JobInstance từ checkpoint sau chunk 2 hoặc từ checkpoint reader đã lưu. Nếu reader và broker offset không được phối hợp, cần tránh bỏ qua hoặc xử lý trùng message.

### Chọn một nguồn sự thật cho tiến độ

Các mô hình thường gặp:

1. **Broker offset là checkpoint chính:** reader khôi phục từ committed offset; DB writer idempotent để chịu duplicate khi DB commit trước offset commit.
2. **Spring Batch ExecutionContext là checkpoint chính:** reader lưu vị trí/ID trong context và khôi phục theo checkpoint; broker ack chỉ sau commit.
3. **Inbox table là checkpoint nghiệp vụ:** message ID được ghi cùng dữ liệu nghiệp vụ; broker có thể redeliver và consumer nhận diện duplicate.

Không để hai checkpoint độc lập có thể tiến lên theo hai hướng mà không có cơ chế đối soát.

### Job restart không đồng nghĩa consumer offset tự reset

Restart JobInstance có thể không reset Kafka consumer group offset hoặc trạng thái queue. Nếu muốn replay từ đầu, phải có chính sách replay riêng, chẳng hạn consumer group mới, offset seek có kiểm soát hoặc batch ID mới.

Không tự commit offset về phía trước để bỏ qua message chỉ vì Spring Batch Step đã fail.

## 23. Monitoring acknowledgement theo chunk

Để vận hành batch message đáng tin cậy, theo dõi ít nhất:

- Số message nhận từ broker.
- Số item được processor xử lý.
- Số item bị filter.
- Số item skip/reject.
- Số item ghi thành công.
- Số message được ack/commit/delete.
- Số ack thất bại và retry.
- Số redelivery/duplicate.
- Số message đang unacked hoặc invisible.
- Consumer lag và committed offset theo partition.
- Thời gian từ receive đến ack.
- Chunk rollback và retry count.
- DLQ depth và tuổi message lâu nhất.

Các count phải được định nghĩa rõ. Ví dụ số item được đọc không nhất thiết bằng số record được ghi vì filter/skip. Số ack thành công có thể khác số message đọc do ack batch partial failure.

Dùng correlation key như batchId, JobExecution ID, message ID và partition/offset để đối soát. Tránh log toàn bộ payload nhạy cảm.

## 24. Kiểm thử acknowledgement theo chunk

Unit test cần kiểm tra AckManager và listener:

- Ack chỉ được gọi sau callback commit thành công.
- Không ack trong beforeChunk.
- Chunk lỗi không ack token.
- Mỗi token chỉ được xác nhận theo đúng chính sách.
- Token của chunk khác không bị ack nhầm.
- Ack failure được ghi nhận và không bị che giấu.
- Batch ack chia đúng giới hạn API.
- Partial success chỉ retry các entry cần thiết.

Ví dụ test listener:

~~~java
@Test
void acknowledgesOnlyAfterChunkCommit() {
    ChunkAckManager manager = mock(ChunkAckManager.class);
    ChunkAcknowledgementListener listener =
            new ChunkAcknowledgementListener(manager);

    listener.afterChunk(mock(ChunkContext.class));

    verify(manager).acknowledgeCommittedChunk();
}

@Test
void doesNotAcknowledgeFailedChunk() {
    ChunkAckManager manager = mock(ChunkAckManager.class);
    ChunkAcknowledgementListener listener =
            new ChunkAcknowledgementListener(manager);

    listener.afterChunkError(mock(ChunkContext.class));

    verify(manager).releaseForRedelivery();
    verify(manager, never()).acknowledgeCommittedChunk();
}
~~~

Đây là unit test của callback, không chứng minh callback thật sự chạy sau database commit hoặc broker redelivery hoạt động. Các hành vi đó cần integration test.

### Integration test với database

1. Dùng database test và transaction manager thật.
2. Writer ghi một số row trong chunk.
3. AckManager fake ghi nhận ack.
4. Gây lỗi để chunk rollback.
5. Xác nhận database không có row của chunk.
6. Xác nhận không có ack thành công.
7. Chạy lại chunk và xác nhận sau commit mới có ack.

### Integration test với broker

Với broker thật hoặc test container phù hợp:

- Gửi một nhóm message.
- Chạy Step xử lý chunk.
- Xác nhận database commit và message được ack.
- Gây lỗi trước commit và xác nhận message được giao lại.
- Gây ack failure sau commit và xác nhận redelivery không tạo duplicate nghiệp vụ.
- Kiểm tra visibility timeout, requeue, offset commit hoặc DLQ theo broker.

Không dùng mock broker để kết luận semantics delivery tag, session transaction, consumer rebalance hoặc SQS receipt handle.

## 25. Những lỗi thường gặp

### Ack ngay khi reader nhận message

Chunk có thể rollback sau đó và message đã bị xác nhận. Chỉ ack sau khi xử lý thành công hoặc dùng transaction broker/database được phối hợp.

### Ack trước database commit

Có thể mất message nếu database rollback. Đặt ack sau commit trong mô hình at-least-once.

### Nghĩ ack sau commit không thể duplicate

Process có thể dừng giữa DB commit và ack. Broker redeliver; writer cần idempotency.

### Dùng AUTO_ACKNOWLEDGE rồi nghĩ ack theo chunk

JMS auto acknowledgement có thể xảy ra ở receive boundary. Kiểm tra session mode và reader adapter.

### Acknowledge JMS CLIENT_ACKNOWLEDGE trên session có prefetch

Một acknowledge có thể xác nhận nhiều message đã được session tiêu thụ. Không ack khi message của chunk sau vẫn chưa xử lý.

### RabbitMQ multiple ack vượt qua delivery chưa hoàn tất

Ack tag cao với multiple=true có thể xác nhận tag thấp chưa xử lý. Chỉ ack dãy liên tục đã hoàn tất trên cùng channel.

### Commit Kafka offset không theo partition

Offset là per partition. Commit offset cao hơn khi còn gap có thể làm mất record chưa xử lý.

### Nhầm Kafka poll batch với Spring Batch chunk

Hai ranh giới có thể khác nhau. Ack/commit phải gắn với chunk đã commit, không chỉ poll đã trả về.

### Dùng SQS receipt handle cũ

Receipt handle thay đổi qua lần receive. Xóa bằng handle của lần nhận hiện tại.

### Không xử lý partial failure của batch delete

Một số entry có thể xóa thành công trong khi entry khác thất bại. Theo dõi kết quả từng entry.

### Không quản lý visibility timeout

Message có thể được giao cho consumer khác khi chunk còn đang xử lý. Gia hạn visibility và dùng idempotency.

### Dùng chung token list giữa các thread

Chunk này có thể ack token của chunk khác. Cô lập state theo execution/partition/chunk.

### Ack message bị skip mà không lưu reject

Dữ liệu lỗi có thể biến mất. Lưu reject/DLQ bền vững trước khi ack.

### Cho rằng Spring Batch tự ack mọi broker

ItemReader không có acknowledgement contract chung. Phải thiết kế adapter và transaction integration theo broker.

## 26. Quy trình thiết kế acknowledgement theo chunk

Trước khi triển khai, hãy trả lời:

1. Broker nào cung cấp message và API ack tương ứng là gì?
2. Receive có tự acknowledge hoặc xóa message không?
3. Chunk size và broker batch/poll size có khác nhau không?
4. Delivery token nào phải được giữ cho từng item?
5. Ack được thực hiện sau transaction commit bằng callback nào?
6. Khi chunk rollback, broker sẽ requeue, redeliver, recover session hay hết visibility timeout?
7. Ack failure sau DB commit có tạo redelivery không?
8. Writer có idempotent theo message ID/business key không?
9. Message bị filter/skip được coi là hoàn tất hay phải chuyển reject/DLQ?
10. Với Kafka, offset được quản lý riêng theo partition và chỉ commit qua dãy liên tục chưa?
11. Với RabbitMQ, channel và delivery tag có được dùng đúng phạm vi không?
12. Với JMS, acknowledgement mode/session transaction có phù hợp không?
13. Với SQS, receipt handle và visibility timeout được quản lý thế nào?
14. Prefetch/buffer có chứa message của chunk kế tiếp không?
15. State ack có được cô lập theo thread/partition không?
16. Restart dùng broker offset, Batch ExecutionContext hay inbox table làm nguồn tiến độ?
17. Có outbox/inbox hoặc XA nếu cần phối hợp nhiều resource không?
18. Monitoring có đối chiếu receive, process, commit, ack và redelivery không?

Một mô hình at-least-once thường dễ vận hành là: nhận message, xử lý và ghi dữ liệu cùng inbox marker trong chunk transaction, commit database, sau đó ack broker. Nếu ack thất bại, message được giao lại nhưng inbox marker ngăn side effect nghiệp vụ lặp. Với hệ thống yêu cầu atomic giữa broker và database, đánh giá XA hoặc transaction integration chuyên biệt của broker; không giả định chunk transaction tự cung cấp điều đó.

## Kết luận

Acknowledgement theo chunk gắn việc xác nhận message với kết quả commit của nhóm item trong Spring Batch. Trong mô hình at-least-once, hãy commit dữ liệu nghiệp vụ trước rồi mới ack; nếu ack thất bại, chấp nhận redelivery và dùng inbox/unique key để xử lý idempotently. Khi chunk rollback, không ack và phải bảo đảm broker có thể giao lại message bằng requeue, session rollback, offset chưa commit hoặc visibility timeout. Semantics khác nhau giữa JMS, RabbitMQ, Kafka và SQS: đặc biệt chú ý JMS acknowledgement mode, Rabbit delivery tag/channel, Kafka offset liên tục theo partition và SQS receipt handle/visibility timeout. Tách poll/prefetch khỏi chunk boundary, cô lập token theo chunk/partition, xử lý filter/skip/DLQ rõ ràng và kiểm thử cả callback lẫn broker/database integration. Chunk commit và broker ack chỉ atomic khi có transaction coordination thực sự được cấu hình; còn lại phải thiết kế cho duplicate và restart.
