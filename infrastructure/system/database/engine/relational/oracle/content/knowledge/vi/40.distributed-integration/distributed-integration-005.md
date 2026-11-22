# Advanced Queuing: queue table, enqueue, dequeue và tính giao dịch

Oracle Advanced Queuing (AQ) là cơ chế messaging tích hợp trong Oracle Database. Ứng dụng có thể gửi một message vào queue, để một tiến trình khác nhận và xử lý message sau đó. Vì message được lưu và quản lý trong database, AQ có thể phối hợp việc gửi/nhận message với transaction SQL của ứng dụng.

AQ thường được dùng để tách các bước xử lý trong hệ thống: ứng dụng giao dịch ghi nhận đơn hàng rồi phát một sự kiện; worker nhận sự kiện để gửi thông báo, cập nhật hệ thống phụ hoặc thực hiện công việc nền. Producer và consumer không cần hoạt động cùng thời điểm, nhưng vẫn có thể phối hợp qua message được lưu trong queue.

Các khái niệm trọng tâm:

- **Queue table** là bảng lưu trữ nội bộ các message và metadata do AQ quản lý.
- **Queue** là luồng message logic được tạo trên queue table, có cấu hình enqueue/dequeue và chính sách xử lý.
- **Enqueue** là thao tác đưa message vào queue.
- **Dequeue** là thao tác đọc, khóa hoặc lấy message khỏi queue.
- **Payload** là nội dung nghiệp vụ của message, có thể là kiểu object, RAW hoặc kiểu được AQ hỗ trợ.
- **Transaction visibility** xác định thao tác enqueue/dequeue tham gia transaction hiện tại hay được thực hiện độc lập.

Điểm quan trọng nhất khi thiết kế AQ là bảo đảm message và thay đổi dữ liệu nghiệp vụ có cùng ranh giới transaction khi cần tính nguyên tử. Nếu cập nhật đơn hàng và enqueue sự kiện được commit cùng nhau, hệ thống tránh được tình huống đơn hàng đã commit nhưng message thông báo lại bị mất.

## 1. Kiến trúc và vòng đời message

Một queue table có thể lưu message cho một hoặc nhiều queue. Queue xác định cách ứng dụng tương tác với message, còn queue table là nơi AQ lưu payload và metadata cần thiết để theo dõi trạng thái.

Một luồng xử lý cơ bản:

1. Producer tạo payload chứa thông tin sự kiện.
2. Producer gọi **DBMS_AQ.ENQUEUE** để đưa message vào queue.
3. Transaction của producer commit; message trở nên khả dụng cho consumer nếu enqueue dùng chế độ ON_COMMIT.
4. Consumer gọi **DBMS_AQ.DEQUEUE** để lấy message.
5. Consumer xử lý payload và cập nhật dữ liệu nghiệp vụ.
6. Consumer commit; message được xác nhận đã xử lý và bị loại khỏi tập message sẵn sàng.
7. Nếu consumer rollback, thao tác dequeue bị hoàn tác và message có thể được xử lý lại.

Sơ đồ:

~~~text
        Ứng dụng Producer
               |
        Tạo payload/message
               |
               v
       DBMS_AQ.ENQUEUE
               |
       Transaction COMMIT
               |
               v
       +------------------+
       |    Queue         |
       |  Queue table     |
       +------------------+
               |
       DBMS_AQ.DEQUEUE
               |
               v
        Ứng dụng Consumer
               |
       Xử lý nghiệp vụ
               |
         COMMIT / ROLLBACK
               |
       +-------+--------+
       |                |
     COMMIT           ROLLBACK
       |                |
       v                v
 Message được       Message trở lại
 xác nhận xử lý     trạng thái có thể
                    được xử lý lại
~~~

AQ lưu và quản lý message trong database. Ứng dụng không nên thao tác trực tiếp bằng INSERT, UPDATE hoặc DELETE trên queue table nội bộ. Hãy dùng DBMS_AQ và DBMS_AQADM để tạo queue, enqueue, dequeue, quản lý subscriber và vận hành queue.

## 2. Queue table và queue

### Queue table

Queue table là cấu trúc lưu trữ được tạo bằng **DBMS_AQADM.CREATE_QUEUE_TABLE**. Khi tạo queue table, DBA khai báo kiểu payload và queue table có hỗ trợ nhiều consumer hay không.

Payload có thể là:

- **ADT (Abstract Data Type)**: SQL object type do ứng dụng định nghĩa. Đây là cách thuận tiện khi message có cấu trúc rõ ràng gồm nhiều trường.
- **RAW**: dữ liệu nhị phân do ứng dụng tự định nghĩa cách mã hóa/giải mã.
- **ANYDATA** hoặc các payload type khác được hỗ trợ: dùng khi cần biểu diễn nhiều kiểu dữ liệu hoặc tích hợp theo API tương ứng.

Với payload ADT, cả producer và consumer cần sử dụng đúng kiểu object tương thích. Khi thay đổi cấu trúc type, phải xem xét tác động đến các ứng dụng đang enqueue/dequeue và message đã tồn tại trong queue.

### Queue

Queue được tạo bằng **DBMS_AQADM.CREATE_QUEUE** trên queue table đã có. Một queue có thể được bật/tắt enqueue và dequeue độc lập thông qua **START_QUEUE** và **STOP_QUEUE**.

Queue có thể được cấu hình với các thuộc tính như:

- Số lần retry khi consumer rollback hoặc xử lý message thất bại.
- Khoảng chờ trước lần retry tiếp theo.
- Thời gian lưu message sau khi dequeue.
- Exception queue nhận message hết hạn hoặc vượt số lần retry.
- Quy tắc phân phối và subscriber trong mô hình multi-consumer.

Queue table và queue không phải cùng một khái niệm. Queue table là nơi lưu trữ; queue là đối tượng logic mà producer/consumer sử dụng.

### Single-consumer và multi-consumer queue

**Single-consumer queue** phù hợp khi mỗi message chỉ cần một consumer nhận và xử lý. Nhiều consumer process có thể cùng cạnh tranh lấy message, nhưng một message chỉ được một consumer dequeue thành công theo cơ chế locking của AQ.

**Multi-consumer queue** phù hợp khi một message cần được phân phối đến nhiều subscriber. Ví dụ một sự kiện thanh toán có thể cần được gửi cho dịch vụ kế toán, kho hàng và hệ thống thông báo. Mỗi subscriber có trạng thái nhận message riêng.

| Đặc điểm | Single-consumer | Multi-consumer |
|---|---|---|
| Mục đích | Một message được một consumer xử lý | Một message có thể được nhiều subscriber nhận |
| Queue table | Tạo với multiple_consumers = FALSE | Tạo với multiple_consumers = TRUE |
| Định danh consumer | Không cần consumer name cho mô hình đơn giản | Dequeue thường chỉ rõ consumer_name |
| Phân phối | Nhiều worker cạnh tranh lấy message | Mỗi subscriber có bản giao message logic riêng |
| Ví dụ | Queue xử lý đơn hàng | Queue phát sự kiện cho nhiều hệ thống |

Việc chọn single hay multi-consumer được quyết định khi tạo queue table. Hãy xác định mô hình phân phối trước khi tạo queue table vì không nên xem đây là tùy chọn có thể đổi tùy ý sau khi hệ thống đã có message.

## 3. Chuẩn bị quyền và kiểu payload

Để minh họa, giả sử ứng dụng có schema APP và cần queue sự kiện đơn hàng. Payload gồm mã đơn, loại sự kiện, thời điểm và phần mô tả.

Tạo SQL object type:

~~~sql
CREATE TYPE app.order_event_t AS OBJECT (
  order_id   NUMBER,
  event_type VARCHAR2(30),
  event_time TIMESTAMP WITH TIME ZONE,
  detail     VARCHAR2(2000)
);
/
~~~

Tài khoản quản trị cần quyền tạo queue table và queue, thường thông qua quyền quản trị AQ phù hợp. Tài khoản producer/consumer cần quyền sử dụng package AQ, quyền truy cập kiểu payload và quyền enqueue/dequeue trên queue tương ứng.

Sau khi queue đã được tạo, DBA có thể cấp quyền queue bằng **DBMS_AQADM.GRANT_QUEUE_PRIVILEGE**. Ví dụ cụ thể được đặt ngay sau phần tạo queue để bảo đảm đối tượng đã tồn tại. Nếu producer và consumer dùng cùng một schema, có thể cấp cả hai quyền cho schema đó. Quyền thực tế còn phụ thuộc cách triển khai và phiên bản Oracle; DBA cần bảo đảm user có quyền thực thi package, truy cập type và quyền queue cần thiết. Không cấp quyền quản trị AQ rộng cho tài khoản ứng dụng nếu chỉ cần enqueue hoặc dequeue.

## 4. Tạo queue table và queue bằng DBMS_AQADM

Tạo queue table đơn consumer:

~~~sql
BEGIN
  DBMS_AQADM.CREATE_QUEUE_TABLE(
    queue_table        => 'APP.ORDER_QTAB',
    queue_payload_type => 'APP.ORDER_EVENT_T',
    multiple_consumers => FALSE
  );
END;
/
~~~

Tạo queue trên queue table:

~~~sql
BEGIN
  DBMS_AQADM.CREATE_QUEUE(
    queue_name  => 'APP.ORDER_Q',
    queue_table => 'APP.ORDER_QTAB',
    max_retries => 5,
    retry_delay => 60
  );
END;
/
~~~

Bật enqueue và dequeue:

~~~sql
BEGIN
  DBMS_AQADM.START_QUEUE(
    queue_name => 'APP.ORDER_Q',
    enqueue    => TRUE,
    dequeue    => TRUE
  );
END;
/
~~~

Sau khi start, queue có thể nhận và cung cấp message theo các quyền đã cấp. Nếu queue chưa được bật enqueue hoặc dequeue, thao tác tương ứng có thể thất bại dù queue table và queue đã được tạo.

Cấp quyền cho producer và worker sau khi queue đã tồn tại:

~~~sql
BEGIN
  DBMS_AQADM.GRANT_QUEUE_PRIVILEGE(
    privilege  => 'ENQUEUE',
    queue_name => 'APP.ORDER_Q',
    grantee    => 'APP_PRODUCER'
  );

  DBMS_AQADM.GRANT_QUEUE_PRIVILEGE(
    privilege  => 'DEQUEUE',
    queue_name => 'APP.ORDER_Q',
    grantee    => 'APP_WORKER'
  );
END;
/
~~~

### Cấu hình retry và exception queue

Khi consumer lấy message nhưng transaction rollback, AQ có thể thử giao message lại. Queue có thuộc tính retry count và retry delay. Khi vượt quá số lần retry, message có thể được chuyển sang exception queue theo chính sách và trạng thái của queue.

Ví dụ trên đặt MAX_RETRIES bằng 5 và RETRY_DELAY bằng 60 giây ngay khi tạo queue. Nếu queue đã tồn tại và cần thay đổi chính sách, dùng thủ tục quản trị thay đổi queue phù hợp với phiên bản, sau đó kiểm tra lại cấu hình bằng các view AQ. Không chạy lại CREATE_QUEUE cho một queue đã tồn tại.

Exception queue là nơi lưu message không thể tiếp tục giao theo chính sách retry/expiration. Cần có quy trình theo dõi, điều tra payload lỗi và quyết định phát lại hoặc loại bỏ message. Không nên xóa message khỏi exception queue mà chưa xác định nguyên nhân.

## 5. Enqueue: đưa message vào queue

Producer dùng **DBMS_AQ.ENQUEUE**. Các thành phần chính:

- **queue_name**: tên queue nhận message.
- **enqueue_options**: tùy chọn enqueue, gồm transaction visibility và một số hành vi giao message.
- **message_properties**: metadata như priority, delay, expiration, correlation và recipient list.
- **payload**: nội dung message theo kiểu đã khai báo cho queue table.
- **msgid**: mã message do AQ tạo và trả về.

Ví dụ enqueue một sự kiện đơn hàng:

~~~sql
DECLARE
  l_enqueue_options    DBMS_AQ.ENQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  l_enqueue_options.visibility := DBMS_AQ.ON_COMMIT;

  l_payload := APP.ORDER_EVENT_T(
    1001,
    'ORDER_PAID',
    SYSTIMESTAMP,
    'Payment completed'
  );

  DBMS_AQ.ENQUEUE(
    queue_name         => 'APP.ORDER_Q',
    enqueue_options    => l_enqueue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  DBMS_OUTPUT.PUT_LINE('Message ID: ' || RAWTOHEX(l_msgid));

  COMMIT;
END;
/
~~~

Message được enqueue với visibility ON_COMMIT. Vì vậy, message trở nên khả dụng cho consumer sau khi transaction commit. Nếu transaction rollback trước commit, message enqueue cũng bị rollback.

### Enqueue cùng transaction với DML nghiệp vụ

Một ứng dụng thường cần cập nhật dữ liệu nghiệp vụ và gửi sự kiện tương ứng trong cùng transaction.

~~~sql
DECLARE
  l_enqueue_options    DBMS_AQ.ENQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  UPDATE app.orders
  SET    status = 'PAID',
         paid_at = SYSTIMESTAMP
  WHERE  order_id = 1001;

  IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(-20001, 'Order not found');
  END IF;

  l_enqueue_options.visibility := DBMS_AQ.ON_COMMIT;

  l_payload := APP.ORDER_EVENT_T(
    1001,
    'ORDER_PAID',
    SYSTIMESTAMP,
    'Order payment committed'
  );

  DBMS_AQ.ENQUEUE(
    queue_name         => 'APP.ORDER_Q',
    enqueue_options    => l_enqueue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/
~~~

Nếu UPDATE thành công nhưng ENQUEUE thất bại, exception handler rollback cả transaction. Nếu ENQUEUE thành công nhưng commit thất bại, cả thay đổi đơn hàng và message đều không được commit. Đây là lợi ích quan trọng của AQ khi dùng ON_COMMIT: dữ liệu nghiệp vụ và message có cùng kết quả commit trong một Oracle transaction.

Không nên đặt COMMIT bên trong một procedure enqueue dùng chung nếu caller cần kiểm soát transaction. Commit ở tầng sở hữu transaction để tránh vô tình commit các thay đổi khác của caller.

## 6. Message properties và thứ tự xử lý

Payload chứa nội dung nghiệp vụ. Message properties chứa metadata điều khiển giao nhận và lọc message.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| PRIORITY | Độ ưu tiên của message |
| DELAY | Thời gian trì hoãn trước khi message được phép dequeue |
| EXPIRATION | Thời gian message còn hiệu lực trước khi hết hạn |
| CORRELATION | Giá trị ứng dụng dùng để nhóm hoặc lọc message liên quan |
| EXCEPTION_QUEUE | Queue nhận message hết hạn hoặc không thể giao theo chính sách |
| RECIPIENT_LIST | Danh sách recipient trong multi-consumer queue |
| SENDER_ID | Thông tin agent gửi message trong những mô hình hỗ trợ |

Thứ tự message phụ thuộc cấu hình sort order của queue table. Nếu queue table được cấu hình sắp xếp theo thời điểm enqueue, message thường được xử lý theo thứ tự thời gian. Nếu sort order có priority, AQ có thể ưu tiên message theo priority trước thời gian enqueue. Vì vậy, không nên giả định rằng gán PRIORITY sẽ thay đổi thứ tự nếu queue table không được cấu hình sort order tương ứng.

### Delay và expiration

- DELAY cho phép producer enqueue message ngay nhưng trì hoãn thời điểm consumer có thể nhận message.
- EXPIRATION xác định message có thể tồn tại bao lâu trong queue trước khi hết hạn.
- Message hết hạn có thể được chuyển đến exception queue theo cấu hình.
- Message đang bị trì hoãn chưa phải message sẵn sàng để consumer xử lý.

Delay hữu ích khi cần retry theo thời gian hoặc lên lịch xử lý. Expiration hữu ích với message chỉ còn ý nghĩa trong một khoảng thời gian, chẳng hạn yêu cầu xác thực tạm thời. Cần đặt thời gian phù hợp với nghiệp vụ và có quy trình theo dõi message hết hạn.

### Correlation

Correlation là metadata do ứng dụng đặt để nhận diện nhóm message liên quan. Ví dụ các message cùng đơn hàng có thể dùng mã đơn làm correlation. Consumer có thể chỉ dequeue message có correlation phù hợp.

Correlation không phải khóa chính của queue và không thay thế msgid. **MSGID** do AQ tạo để định danh message; **CORRELATION** là giá trị ứng dụng dùng để tìm hoặc phân nhóm message.

## 7. Dequeue: nhận và xử lý message

Consumer dùng **DBMS_AQ.DEQUEUE** để nhận message. Các tham số quan trọng:

- **queue_name**: queue nguồn.
- **dequeue_options**: chế độ lấy message, thời gian chờ, navigation, consumer name và điều kiện lọc.
- **message_properties**: metadata của message được nhận.
- **payload**: nội dung message trả về.
- **msgid**: mã định danh message.

Ví dụ consumer lấy một message và xử lý:

~~~sql
DECLARE
  l_dequeue_options    DBMS_AQ.DEQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  l_dequeue_options.wait         := DBMS_AQ.NO_WAIT;
  l_dequeue_options.navigation   := DBMS_AQ.FIRST_MESSAGE;
  l_dequeue_options.dequeue_mode := DBMS_AQ.REMOVE;
  l_dequeue_options.visibility   := DBMS_AQ.ON_COMMIT;

  DBMS_AQ.DEQUEUE(
    queue_name         => 'APP.ORDER_Q',
    dequeue_options    => l_dequeue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  DBMS_OUTPUT.PUT_LINE(
    'Order=' || l_payload.order_id ||
    ', event=' || l_payload.event_type
  );

  -- Thực hiện các thay đổi nghiệp vụ của consumer tại đây.

  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/
~~~

Với NO_WAIT, nếu không có message sẵn sàng phù hợp, dequeue có thể kết thúc bằng lỗi timeout/end-of-fetch của AQ, thường gặp là ORA-25228. Trong ứng dụng chạy nền, cần xử lý trường hợp queue tạm thời rỗng như một trạng thái bình thường, thay vì ghi nhận mọi lần queue rỗng là lỗi hệ thống.

### Chế độ dequeue

| Chế độ | Hành vi |
|---|---|
| REMOVE | Lấy message và đánh dấu loại khỏi queue; việc loại được commit theo transaction |
| BROWSE | Đọc message mà không loại message khỏi queue |
| LOCKED | Khóa message để kiểm tra/xử lý trong transaction nhưng chưa loại message |

REMOVE là chế độ thường dùng cho consumer xử lý message. BROWSE hữu ích khi kiểm tra nội dung mà không tiêu thụ message. LOCKED có thể dùng khi cần khóa message trong transaction để kiểm tra trước khi quyết định thao tác tiếp theo.

Với REMOVE và ON_COMMIT, message được lấy trong transaction hiện tại. Nếu consumer rollback, thao tác loại message bị hoàn tác và message có thể được giao lại. Nếu commit, việc dequeue được xác nhận.

### Wait và navigation

Thuộc tính WAIT điều khiển thời gian consumer chờ message:

- **NO_WAIT**: không chờ nếu hiện tại không có message phù hợp.
- **FOREVER**: chờ cho đến khi có message hoặc có điều kiện kết thúc khác.
- Một giá trị số: chờ trong khoảng thời gian tính bằng giây theo API.

Thuộc tính NAVIGATION điều khiển vị trí bắt đầu/tìm message trong queue, ví dụ FIRST_MESSAGE hoặc NEXT_MESSAGE. Khi xử lý một message đơn lẻ, FIRST_MESSAGE thường là lựa chọn dễ hiểu. Khi đọc nhiều message liên tiếp trong cùng session, hãy chọn navigation phù hợp với yêu cầu nhất quán và cách AQ định vị message.

### Lọc message khi dequeue

Dequeue có thể dùng các tiêu chí như:

- **consumer_name** trong multi-consumer queue.
- **correlation** để lấy message thuộc nhóm cần xử lý.
- **msgid** khi cần lấy một message cụ thể.
- **condition** để lọc dựa trên message properties hoặc thuộc tính payload theo cú pháp AQ hỗ trợ.

Không nên tạo điều kiện lọc phức tạp mà chưa kiểm tra cú pháp và hiệu năng trên phiên bản Oracle. Nếu nhiều consumer cùng dùng một queue, hãy xác định rõ mỗi consumer nhận message nào và cách xử lý message không phù hợp.

## 8. Tính giao dịch của ENQUEUE và DEQUEUE

Transaction visibility là thuộc tính quan trọng nhất khi phối hợp AQ với DML nghiệp vụ.

Hai chế độ phổ biến:

- **ON_COMMIT**: thao tác enqueue/dequeue tham gia transaction hiện tại của session.
- **IMMEDIATE**: thao tác được thực hiện trong transaction độc lập theo cơ chế autonomous của AQ.

### ON_COMMIT khi enqueue

Khi enqueue với ON_COMMIT:

1. Message được tạo trong transaction hiện tại.
2. Session khác chưa thấy message như một message đã commit.
3. Nếu producer COMMIT, message trở nên khả dụng.
4. Nếu producer ROLLBACK, message bị hủy cùng transaction.

Điều này bảo đảm ứng dụng có thể cập nhật bảng nghiệp vụ và enqueue message trong cùng một transaction.

Ví dụ:

~~~text
BEGIN TRANSACTION
    UPDATE ORDERS
    ENQUEUE ORDER_PAID
COMMIT
    -> ORDERS thay đổi và message cùng có hiệu lực

Nếu ROLLBACK
    -> UPDATE bị hoàn tác
    -> Message cũng không tồn tại trong queue
~~~

### ON_COMMIT khi dequeue

Khi dequeue với REMOVE và ON_COMMIT:

1. Consumer lấy và khóa message trong transaction.
2. Consumer xử lý nghiệp vụ, ví dụ ghi bảng invoice hoặc cập nhật trạng thái.
3. Nếu COMMIT, thay đổi nghiệp vụ và thao tác dequeue cùng được xác nhận.
4. Nếu ROLLBACK, thay đổi nghiệp vụ bị hoàn tác và message được đưa trở lại trạng thái có thể giao.

Ví dụ:

~~~text
BEGIN TRANSACTION
    DEQUEUE ORDER_PAID
    INSERT INVOICE
COMMIT
    -> Message được xác nhận đã xử lý
    -> Invoice được ghi nhận

Nếu ROLLBACK
    -> Invoice bị hoàn tác
    -> Message có thể được xử lý lại
~~~

Cơ chế này giúp tránh hai tình huống nguy hiểm:

- Message đã bị loại khỏi queue nhưng dữ liệu nghiệp vụ của consumer chưa được commit.
- Dữ liệu nghiệp vụ đã được commit nhưng message vẫn bị coi là chưa xử lý trong queue.

### IMMEDIATE và transaction độc lập

Với IMMEDIATE, AQ thực hiện thao tác trong transaction độc lập. Kết quả enqueue/dequeue có thể được commit riêng, không phụ thuộc việc transaction nghiệp vụ bên ngoài commit hay rollback.

Ví dụ producer cập nhật đơn hàng nhưng enqueue dùng IMMEDIATE:

~~~text
BEGIN TRANSACTION
    UPDATE ORDERS
    ENQUEUE MESSAGE (IMMEDIATE COMMIT)
ROLLBACK
    -> UPDATE ORDERS bị hoàn tác
    -> Message vẫn tồn tại trong queue
~~~

Đây có thể là hành vi mong muốn trong một số thiết kế, nhưng thường không phù hợp nếu message mô tả một thay đổi nghiệp vụ chưa chắc đã commit. Tương tự, dequeue IMMEDIATE có thể xác nhận việc lấy message độc lập; nếu xử lý nghiệp vụ sau đó rollback, message có thể đã bị loại trong transaction độc lập.

Vì vậy:

| Nhu cầu | Visibility thường phù hợp |
|---|---|
| Cập nhật bảng và gửi message phải cùng thành công/thất bại | ON_COMMIT |
| Lấy message và cập nhật dữ liệu consumer phải cùng thành công/thất bại | ON_COMMIT |
| Chủ động muốn thao tác AQ độc lập với transaction caller | IMMEDIATE, sau khi đánh giá hệ quả |
| Không muốn mất message khi xử lý nghiệp vụ thất bại | DEQUEUE REMOVE + ON_COMMIT |

IMMEDIATE không phải cách “commit nhanh hơn” cho một transaction nghiệp vụ. Nó thay đổi ranh giới nguyên tử. Chỉ sử dụng khi đã xác định rõ message phải tồn tại hoặc bị loại độc lập với transaction bên ngoài.

## 9. Retry, rollback và xử lý lỗi

Trong hệ thống bất đồng bộ, consumer có thể gặp lỗi tạm thời như deadlock, lỗi kết nối, dịch vụ phụ thuộc không sẵn sàng hoặc dữ liệu chưa đủ điều kiện xử lý. Với dequeue ON_COMMIT, consumer rollback sẽ hoàn tác việc remove message. Message có thể được thử lại theo chính sách retry của queue.

Các thuộc tính vận hành cần quan tâm:

- **MAX_RETRIES**: số lần AQ thử giao lại message sau các lần dequeue thất bại theo cơ chế queue.
- **RETRY_DELAY**: thời gian chờ trước khi thử lại.
- **EXPIRATION**: thời gian message còn hiệu lực.
- **EXCEPTION_QUEUE**: nơi nhận message không còn được giao bình thường do retry/expiration hoặc chính sách tương ứng.

Retry giúp hệ thống tự phục hồi với lỗi tạm thời. Tuy nhiên, nếu message luôn gây lỗi do payload sai hoặc dữ liệu nghiệp vụ không hợp lệ, retry liên tục chỉ làm tăng tải. Cần có ngưỡng retry, exception queue và quy trình điều tra.

### Consumer cần idempotent

Ngay cả khi AQ quản lý message transactionally, ứng dụng vẫn cần thiết kế consumer có khả năng xử lý lặp an toàn trong những tình huống tích hợp ngoài database, lỗi client hoặc quy trình retry.

Ví dụ một message ORDER_PAID có thể được giao lại nếu consumer rollback. Consumer nên kiểm tra xem invoice đã được tạo cho order đó chưa, hoặc dùng một business key/unique constraint để ngăn ghi nhận trùng.

Mẫu xử lý:

~~~sql
BEGIN
  -- Dequeue message với ON_COMMIT và REMOVE.

  INSERT INTO app.processed_events(event_id, processed_at)
  VALUES (:event_id, SYSTIMESTAMP);

  -- Thực hiện cập nhật nghiệp vụ trong cùng transaction.

  COMMIT;
EXCEPTION
  WHEN DUP_VAL_ON_INDEX THEN
    -- Event đã được xử lý trước đó; áp dụng chính sách xác nhận phù hợp.
    ROLLBACK;
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/
~~~

Ví dụ trên minh họa ý tưởng deduplication; cần quyết định rõ xử lý duplicate có được coi là thành công hay cần log và đối soát. Không nên nuốt mọi exception vì có thể che giấu lỗi nghiệp vụ.

Nếu consumer gọi hệ thống bên ngoài như email, HTTP API hoặc dịch vụ thanh toán, transaction Oracle không thể rollback side effect đã xảy ra ở hệ thống bên ngoài. Hãy dùng idempotency key, outbox/inbox, retry có kiểm soát hoặc cơ chế xác nhận riêng của dịch vụ ngoài.

## 10. Multi-consumer queue và subscriber

Khi một message cần được nhiều thành phần nhận độc lập, tạo queue table với multiple_consumers = TRUE.

Ví dụ tạo queue table sự kiện:

~~~sql
BEGIN
  DBMS_AQADM.CREATE_QUEUE_TABLE(
    queue_table        => 'APP.EVENT_QTAB',
    queue_payload_type => 'APP.ORDER_EVENT_T',
    multiple_consumers => TRUE
  );

  DBMS_AQADM.CREATE_QUEUE(
    queue_name  => 'APP.EVENT_Q',
    queue_table => 'APP.EVENT_QTAB'
  );
END;
/
~~~

Tạo subscriber cho queue:

~~~sql
DECLARE
  l_subscriber SYS.AQ$_AGENT;
BEGIN
  l_subscriber := SYS.AQ$_AGENT('BILLING', NULL, NULL);

  DBMS_AQADM.ADD_SUBSCRIBER(
    queue_name => 'APP.EVENT_Q',
    subscriber => l_subscriber
  );

  DBMS_AQADM.START_QUEUE(
    queue_name => 'APP.EVENT_Q',
    enqueue    => TRUE,
    dequeue    => TRUE
  );
END;
/
~~~

Có thể thêm subscriber khác như INVENTORY hoặc NOTIFICATION. Nếu message được gửi đến tất cả subscriber, mỗi subscriber có thể nhận bản giao message của riêng mình. Nếu cần giới hạn recipient, producer có thể dùng recipient list theo API AQ.

Khi dequeue, consumer chỉ rõ tên subscriber:

~~~sql
DECLARE
  l_dequeue_options    DBMS_AQ.DEQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  l_dequeue_options.consumer_name := 'BILLING';
  l_dequeue_options.wait := DBMS_AQ.NO_WAIT;
  l_dequeue_options.dequeue_mode := DBMS_AQ.REMOVE;
  l_dequeue_options.visibility := DBMS_AQ.ON_COMMIT;

  DBMS_AQ.DEQUEUE(
    queue_name         => 'APP.EVENT_Q',
    dequeue_options    => l_dequeue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  -- Xử lý riêng cho subscriber BILLING.

  COMMIT;
END;
/
~~~

Multi-consumer queue hữu ích khi các hệ thống cần nhận cùng một sự kiện nhưng xử lý độc lập. Nếu subscriber BILLING đã dequeue và commit, message vẫn có thể còn chờ subscriber INVENTORY. Vì vậy, trạng thái xử lý cần được hiểu theo từng subscriber, không phải chỉ một trạng thái chung cho cả message.

## 11. Queue lifecycle: start, stop và quản lý message

Queue phải được bật cho enqueue và/hoặc dequeue trước khi ứng dụng sử dụng.

Start queue:

~~~sql
BEGIN
  DBMS_AQADM.START_QUEUE(
    queue_name => 'APP.ORDER_Q',
    enqueue    => TRUE,
    dequeue    => TRUE
  );
END;
/
~~~

Tạm dừng enqueue nhưng vẫn cho consumer lấy message:

~~~sql
BEGIN
  DBMS_AQADM.STOP_QUEUE(
    queue_name => 'APP.ORDER_Q',
    enqueue    => TRUE,
    dequeue    => FALSE,
    wait       => TRUE
  );
END;
/
~~~

Tham số STOP_QUEUE cho phép điều khiển dừng enqueue/dequeue và chờ các thao tác đang hoạt động theo chính sách. Hãy kiểm tra ý nghĩa các tham số theo phiên bản Oracle đang dùng. Khi bảo trì queue, cần phối hợp producer/consumer để không tạo ra lỗi ngoài dự kiến.

Xem cấu hình queue:

~~~sql
SELECT name,
       queue_table,
       enqueue_enabled,
       dequeue_enabled
FROM   user_queues
ORDER BY name;
~~~

Xem queue table:

~~~sql
SELECT queue_table,
       object_type,
       sort_order,
       recipients
FROM   user_queue_tables
ORDER BY queue_table;
~~~

Các view USER_QUEUES, ALL_QUEUES, DBA_QUEUES và các view queue table tương ứng giúp kiểm tra trạng thái, kiểu payload, sort order và thuộc tính queue. Tên/cột view có thể khác theo phiên bản và quyền truy cập.

### Message retention và cleanup

Queue có thể được cấu hình giữ message sau khi dequeue trong một khoảng thời gian để phục vụ audit hoặc theo dõi. Retention khác với việc message còn sẵn sàng để dequeue: message đã được xác nhận xử lý không nhất thiết còn được giao cho consumer, nhưng metadata/message có thể được giữ lại theo retention policy.

Khi cần dọn dữ liệu cũ, dùng cơ chế AQ quản lý như **DBMS_AQADM.PURGE_QUEUE_TABLE** theo chính sách đã thiết kế. Không xóa trực tiếp các dòng trong queue table hoặc các bảng nội bộ AQ bằng SQL thông thường. Việc purge cần được lập kế hoạch vì có thể loại bỏ thông tin phục vụ điều tra và đối soát.

Khi không còn sử dụng queue, quy trình gỡ bỏ thường gồm dừng queue, drop queue, sau đó drop queue table nếu không còn queue nào sử dụng table đó. Không xóa queue table đang chứa message cần giữ hoặc queue còn được ứng dụng sử dụng.

## 12. Kiểm tra và giám sát AQ

Giám sát AQ nên theo dõi cả số lượng message và tiến độ xử lý, không chỉ kiểm tra queue có đang enabled hay không.

Các chỉ số hữu ích:

- Số message đang chờ xử lý.
- Thời gian message nằm trong queue.
- Tốc độ enqueue và dequeue.
- Số lần retry và số message trong exception queue.
- Tỷ lệ lỗi consumer.
- Độ trễ từ thời điểm tạo message đến thời điểm xử lý xong.
- Queue hoặc subscriber có bị backlog tăng liên tục hay không.

Có thể bắt đầu bằng các view queue:

~~~sql
SELECT name,
       queue_table,
       enqueue_enabled,
       dequeue_enabled,
       retention
FROM   user_queues
ORDER BY name;
~~~

AQ cung cấp các view theo dõi queue table, queue và message. View sinh theo queue table thường có tên dạng AQ$<queue_table>; có thể dùng để kiểm tra trạng thái message theo quyền và phiên bản. Nên ưu tiên view quản trị được Oracle công bố thay vì truy cập trực tiếp bảng lưu trữ nội bộ.

Kiểm tra message queue thường cần quyền thích hợp. Với môi trường nhiều schema, dùng các view DBA_ hoặc GV$ tương ứng nếu phiên bản hỗ trợ và tài khoản được cấp quyền.

### Kiểm tra message bị kẹt

Nếu backlog tăng:

1. Xác nhận queue đang bật dequeue.
2. Kiểm tra consumer process có chạy và có quyền dequeue.
3. Xem message có bị delay hoặc hết hạn không.
4. Kiểm tra retry count và exception queue.
5. Kiểm tra consumer có đang giữ transaction lâu hoặc khóa message.
6. Đo thời gian xử lý payload và lỗi nghiệp vụ.
7. Xem queue table có tăng dung lượng hoặc cleanup bị chậm không.

Không nên tăng số consumer ngay lập tức nếu nguyên nhân là message lỗi lặp, một subscriber không hoạt động hoặc consumer đang bị khóa bởi transaction dài. Tăng worker có thể làm tải database tăng mà không giải quyết backlog.

## 13. AQ và transaction trong ứng dụng thực tế

### Producer transaction

Producer nên thực hiện DML nghiệp vụ và enqueue trong cùng transaction khi message phản ánh kết quả của DML đó.

Ví dụ: tạo đơn hàng và enqueue ORDER_CREATED. Nếu tạo đơn hàng thất bại, message không được phát ra. Nếu enqueue thất bại, đơn hàng cũng rollback để tránh dữ liệu và message lệch nhau.

### Consumer transaction

Consumer nên dequeue REMOVE và thực hiện cập nhật database trong cùng transaction. Nếu xử lý thất bại, rollback để message được thử lại. Nếu xử lý thành công, commit để xác nhận cả thay đổi nghiệp vụ lẫn dequeue.

### Không giữ transaction quá lâu

Consumer nên giới hạn thời gian giữ message lock. Một transaction kéo dài có thể làm message bị giữ lâu, giảm throughput và khiến worker khác không xử lý được message đó. Hãy thiết kế công việc thành các bước có ranh giới transaction rõ ràng.

Nếu một message yêu cầu xử lý rất lâu, có thể dequeue rồi ghi nhận trạng thái công việc vào bảng nghiệp vụ trong cùng transaction; một worker khác thực hiện phần xử lý dài theo workflow riêng. Cần thiết kế trạng thái và retry rõ ràng để không mất công việc khi process bị dừng.

### AQ không thay thế distributed transaction cho hệ thống bên ngoài

Nếu producer cần vừa commit Oracle vừa gọi REST API, email hoặc message broker ngoài database, một transaction Oracle không thể tự động commit/rollback đồng bộ với hệ thống ngoài. AQ giúp lưu message nguyên tử với transaction Oracle, sau đó một consumer chuyển tiếp message ra ngoài. Consumer cần retry, idempotency và theo dõi kết quả giao tiếp.

Đây là một cách triển khai transactional outbox: business transaction ghi dữ liệu và enqueue event; worker đọc event và chuyển sang hệ thống ngoài. AQ cung cấp queue trong database, còn logic retry/đối soát và idempotency vẫn thuộc thiết kế ứng dụng.

## 14. Các lỗi thường gặp

### Queue chưa được start

Queue table và queue đã tạo nhưng enqueue/dequeue chưa được bật. Kiểm tra USER_QUEUES hoặc DBA_QUEUES và dùng START_QUEUE với đúng cờ enqueue/dequeue.

### Không đủ quyền enqueue/dequeue

User có thể nhìn thấy queue nhưng không được cấp quyền thực hiện thao tác. Kiểm tra quyền queue qua DBMS_AQADM và quyền sử dụng package/type. Cấp đúng quyền tối thiểu cho producer và consumer.

### Payload không tương thích

Kiểu payload của biến PL/SQL phải tương thích với queue table. Với ADT, kiểm tra schema, tên type, cấu trúc thuộc tính và quyền EXECUTE trên type. Không truyền payload khác kiểu với queue đã tạo.

### Queue rỗng hoặc dequeue timeout

Với NO_WAIT, không có message phù hợp có thể dẫn đến ORA-25228. Xử lý đây như trạng thái queue rỗng hoặc hết thời gian chờ theo logic worker. Nếu dùng WAIT hữu hạn, điều chỉnh polling để không tạo tải truy vấn liên tục.

### Message liên tục được retry

Consumer có thể rollback vì lỗi nghiệp vụ hoặc lỗi kỹ thuật. Kiểm tra log consumer, retry count, retry delay và exception queue. Xác định lỗi tạm thời hay lỗi dữ liệu trước khi phát lại message.

### Message bị xử lý trùng

Có thể do retry, consumer rollback sau side effect ngoài database hoặc ứng dụng enqueue cùng sự kiện nhiều lần. Dùng business key, unique constraint, inbox/processed-events table và idempotent handler.

### Message không xuất hiện dù producer đã chạy ENQUEUE

Kiểm tra visibility. Nếu enqueue dùng ON_COMMIT, producer phải commit. Nếu transaction rollback, message không được lưu. Kiểm tra exception path, queue đã bật enqueue, quyền của producer và các lỗi ORA/AQ trong session; đồng thời xác nhận transaction thực sự đã commit.

### Consumer đã dequeue nhưng nghiệp vụ không được ghi nhận

Nếu dequeue REMOVE dùng IMMEDIATE hoặc transaction bị commit trước khi xử lý nghiệp vụ hoàn tất, message có thể đã bị xác nhận riêng. Dùng ON_COMMIT và commit cùng các thay đổi nghiệp vụ. Kiểm tra transaction boundaries trong code gọi.

## 15. Quy trình triển khai AQ

1. **Xác định mô hình message.** Chọn payload ADT hay RAW; xác định trường dữ liệu, versioning và kích thước.
2. **Chọn single hay multi-consumer.** Xác định một worker cạnh tranh xử lý hay nhiều subscriber nhận cùng sự kiện.
3. **Tạo payload type.** Định nghĩa SQL object type và quyền sử dụng type.
4. **Tạo queue table.** Dùng DBMS_AQADM.CREATE_QUEUE_TABLE với payload type và multiple_consumers phù hợp.
5. **Tạo queue.** Cấu hình retry, delay, retention và exception queue theo yêu cầu.
6. **Tạo subscriber nếu cần.** Với multi-consumer, đăng ký consumer và xác định recipient.
7. **Start queue.** Bật enqueue/dequeue theo đúng vai trò.
8. **Cấp quyền tối thiểu.** Cấp ENQUEUE cho producer, DEQUEUE cho consumer và quyền cần thiết trên package/type.
9. **Triển khai producer.** Enqueue trong cùng transaction với DML nghiệp vụ khi cần atomicity.
10. **Triển khai consumer.** Dequeue REMOVE với ON_COMMIT, xử lý idempotent và commit/rollback rõ ràng.
11. **Kiểm thử lỗi.** Thử rollback producer, rollback consumer, queue rỗng, retry, expiration và exception queue.
12. **Giám sát production.** Theo dõi backlog, latency, retry, exception queue và dung lượng queue table.

## 16. Nguyên tắc thiết kế quan trọng

- Queue table là nơi lưu message; queue là luồng logic mà producer/consumer thao tác.
- Dùng DBMS_AQADM để tạo/quản lý queue và DBMS_AQ để enqueue/dequeue.
- Chọn payload type và single/multi-consumer trước khi tạo queue table.
- Enqueue ON_COMMIT cùng DML để message phản ánh đúng trạng thái đã commit của nghiệp vụ.
- Dequeue REMOVE với ON_COMMIT cùng xử lý database để rollback có thể trả message về queue.
- IMMEDIATE tạo ranh giới transaction độc lập; chỉ dùng khi hành vi đó được chủ động yêu cầu.
- Thiết kế consumer idempotent vì message có thể được giao lại hoặc producer có thể phát sự kiện trùng.
- Cấu hình retry, retry delay, expiration và exception queue theo loại lỗi có thể xảy ra.
- Không thao tác trực tiếp trên bảng AQ nội bộ; dùng API và view được Oracle hỗ trợ.
- Theo dõi backlog, thời gian chờ, retry và exception message; diễn tập xử lý message lỗi.
- Không giả định transaction Oracle bao trùm side effect của REST API, email hoặc hệ thống ngoài.
- Giữ transaction ngắn và xác định rõ nơi commit/rollback để tránh khóa message quá lâu.

Advanced Queuing cung cấp cơ chế trao đổi message bền vững ngay trong Oracle Database. Khi queue table, payload, enqueue/dequeue và transaction visibility được cấu hình phù hợp, producer và consumer có thể hoạt động độc lập mà vẫn giữ được tính nhất quán giữa message và dữ liệu nghiệp vụ.
