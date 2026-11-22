# Nhận sự kiện Cloud Storage và Pub/Sub qua Eventarc

Trong chương **Serverless trên Google Cloud**, Eventarc giúp kết nối các sự kiện từ dịch vụ Google Cloud với ứng dụng chạy trên Cloud Run hoặc Cloud Run functions. Thay vì để mỗi function tự dò trạng thái của một dịch vụ, Eventarc nhận sự kiện từ nguồn, áp dụng bộ lọc và chuyển sự kiện đến đích theo định dạng CloudEvents. Hai nguồn phổ biến là Cloud Storage, nơi phát sự kiện khi object được tạo hoặc thay đổi, và Pub/Sub, nơi producer công bố message để các consumer xử lý bất đồng bộ.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function được kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Khi nhận sự kiện, người học cần xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định cách dùng FaaS phù hợp.

## 1. Eventarc giải quyết vấn đề gì?

Một dịch vụ nghiệp vụ thường cần phản ứng khi dữ liệu hoặc trạng thái ở một dịch vụ khác thay đổi. Ví dụ:

- Khi một file được tải lên Cloud Storage, function kiểm tra định dạng, tạo thumbnail hoặc trích xuất metadata.
- Khi một đơn hàng được công bố lên Pub/Sub, function cập nhật trạng thái hoặc bắt đầu quy trình xử lý.
- Khi object bị xóa, function dọn metadata hoặc đánh dấu tài nguyên không còn khả dụng.

Nếu mỗi ứng dụng tự gọi API của nguồn, tự quản lý webhook hoặc polling định kỳ, các thành phần sẽ phụ thuộc chặt vào nhau. Eventarc cung cấp lớp định tuyến sự kiện được quản lý:

1. Một dịch vụ Google Cloud phát sinh sự kiện.
2. Eventarc nhận sự kiện và áp dụng bộ lọc của trigger.
3. Eventarc chuyển sự kiện đến đích đã cấu hình.
4. Đích nhận HTTP request theo định dạng CloudEvents.
5. Function hoặc service xử lý payload rồi trả kết quả HTTP.

~~~mermaid
flowchart LR
    GCS["Cloud Storage"] -->|Object event| EA["Eventarc trigger"]
    PS["Pub/Sub topic"] -->|Message published| EA
    EA -->|CloudEvent over HTTP| RUN["Cloud Run / Cloud Run functions"]
    RUN --> JAVA["Java handler"]
    JAVA --> DB[("Database / downstream service")]
~~~

Eventarc tách nguồn phát sự kiện khỏi nơi xử lý. Producer không cần biết function nào đang nhận sự kiện, còn function không cần polling liên tục để kiểm tra nguồn.

Eventarc là bộ định tuyến và giao nhận sự kiện. Nó không thay thế logic nghiệp vụ, schema validation, idempotency hoặc việc lưu trạng thái xử lý. Những trách nhiệm đó vẫn thuộc về ứng dụng và dịch vụ nguồn.

## 2. Eventarc, Cloud Run và Cloud Run functions

Eventarc có thể chuyển sự kiện đến các đích được hỗ trợ, trong đó thường gặp:

- **Cloud Run service:** ứng dụng HTTP do nhóm phát triển triển khai, tự quản lý routing và handler.
- **Cloud Run functions / Cloud Functions thế hệ mới:** function được đóng gói và triển khai theo mô hình functions framework, có entry point rõ ràng.
- Các đích khác được Eventarc hỗ trợ theo loại trigger và cấu hình.

Với Java, handler có thể triển khai giao diện CloudEvents của Functions Framework hoặc nhận HTTP request rồi tự phân tích CloudEvent. Dùng Functions Framework giúp adapter xử lý giao thức và chuyển event vào method Java theo kiểu dữ liệu rõ ràng.

Cần phân biệt hai cách nhận message từ Pub/Sub:

| Cách nhận | Ai khởi tạo việc giao? | Khi phù hợp |
|---|---|---|
| Eventarc trigger | Eventarc chuyển event đến HTTP target | Muốn định tuyến event đến Cloud Run/function theo cùng mô hình CloudEvents |
| Pub/Sub pull subscription | Ứng dụng tự gọi API pull và ACK message | Cần tự điều khiển poll, batch, flow control và acknowledgement |

Khi dùng Eventarc, target không cần tự poll Pub/Sub subscription. Nếu ứng dụng cần điều khiển pull và ack ở mức message, có thể dùng Pub/Sub client trực tiếp; đó là một kiến trúc consumer khác với Eventarc.

## 3. CloudEvents là hợp đồng giữa Eventarc và handler

Eventarc chuyển sự kiện theo đặc tả CloudEvents 1.0. CloudEvent có envelope chứa ngữ cảnh chung và phần data chứa payload riêng của nguồn.

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| specversion | Phiên bản CloudEvents, thường là 1.0 |
| id | Định danh sự kiện |
| source | Nguồn phát sự kiện |
| type | Loại sự kiện |
| subject | Đối tượng liên quan, nếu có |
| time | Thời điểm sự kiện |
| datacontenttype | Media type của payload, nếu có |
| data | Payload nghiệp vụ hoặc dữ liệu của dịch vụ nguồn |

Ví dụ envelope minh họa:

~~~json
{
  "specversion": "1.0",
  "id": "1234567890123456",
  "source": "//storage.googleapis.com/projects/_/buckets/incoming-files",
  "type": "google.cloud.storage.object.v1.finalized",
  "subject": "objects/invoice-1001.pdf",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "bucket": "incoming-files",
    "name": "invoice-1001.pdf",
    "generation": "1731840000000000",
    "contentType": "application/pdf",
    "size": "245760"
  }
}
~~~

Envelope cung cấp ID, source và type để định tuyến, chống xử lý trùng và truy vết. Data có schema riêng theo từng event type. Không nên dùng một DTO payload duy nhất cho cả Cloud Storage và Pub/Sub vì hai nguồn có cấu trúc khác nhau.

## 4. Nhận sự kiện Cloud Storage qua Eventarc

Cloud Storage có thể phát sự kiện khi object được tạo, cập nhật metadata, xóa hoặc được thay thế theo các event type mà Eventarc hỗ trợ.

Một số event type thường dùng:

| Event type | Ý nghĩa | Use case |
|---|---|---|
| google.cloud.storage.object.v1.finalized | Object mới được tạo hoặc một generation mới được ghi hoàn tất | Xử lý file upload, thumbnail, scan tài liệu |
| google.cloud.storage.object.v1.deleted | Một object generation bị xóa | Dọn metadata, cập nhật catalog |
| google.cloud.storage.object.v1.archived | Object generation cũ được archive/thay thế theo cơ chế versioning | Lưu lịch sử hoặc đồng bộ trạng thái |
| google.cloud.storage.object.v1.metadataUpdated | Metadata object được cập nhật | Đồng bộ nhãn, content type hoặc metadata nghiệp vụ |

Event type và khả năng phát sự kiện cụ thể phụ thuộc loại trigger và cấu hình bucket. Cần chọn đúng event type cho mục tiêu; không dùng finalized để thay thế cho mọi thay đổi metadata.

### 4.1. Payload Cloud Storage

Payload của object event thường chứa các trường như:

- bucket: tên bucket.
- name: tên object.
- generation: định danh phiên bản nội dung của object.
- metageneration: phiên bản metadata.
- contentType: loại nội dung.
- size: kích thước object.
- timeCreated: thời điểm tạo.
- updated: thời điểm cập nhật.

Ví dụ DTO Java:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record StorageObjectData(
        String bucket,
        String name,
        String generation,
        String metageneration,
        String contentType,
        String size,
        String timeCreated,
        String updated) {
}
~~~

Một số trường số lớn được biểu diễn dưới dạng chuỗi trong event payload. Dùng String cho generation và metageneration giúp tránh mất độ chính xác khi chuyển qua kiểu số có giới hạn. Khi cần so sánh, parse sang BigInteger hoặc giữ nguyên chuỗi theo hợp đồng.

### 4.2. Generation và metageneration

Cloud Storage dùng generation để nhận diện phiên bản nội dung của object. Khi object bị ghi đè, generation thay đổi. Metageneration tăng khi metadata của một generation thay đổi.

Hai giá trị này rất quan trọng khi function xử lý bất đồng bộ. Ví dụ, một event finalized của generation cũ có thể đến muộn sau khi object đã được ghi generation mới. Nếu function chỉ đọc theo bucket và object name, nó có thể vô tình xử lý nội dung mới trong khi event mô tả nội dung cũ.

Khi cần đọc đúng phiên bản đã phát event, dùng generation từ payload làm điều kiện truy cập object bằng Cloud Storage client. Khi cần phát hiện metadata đã thay đổi, xem xét metageneration. Không dùng riêng tên object làm khóa idempotency cho mọi lần upload.

### 4.3. Luồng xử lý file

Một quy trình thường gặp:

1. Người dùng tải file lên bucket incoming.
2. Cloud Storage phát sự kiện finalized.
3. Eventarc lọc event theo bucket và type rồi chuyển đến Java function.
4. Function kiểm tra bucket, object name, generation và content type.
5. Function đọc đúng object generation nếu cần.
6. Function quét nội dung, kiểm tra nghiệp vụ hoặc tạo bản xử lý.
7. Function lưu kết quả và ghi nhận event đã xử lý.
8. Function trả phản hồi thành công sau khi các thay đổi cần thiết đã được lưu bền vững.

Không nên giả định event finalized chỉ phát đúng một lần. Retry hoặc giao nhận lặp có thể khiến function nhận lại cùng sự kiện.

## 5. Nhận sự kiện Pub/Sub qua Eventarc

Pub/Sub là dịch vụ nhắn tin bất đồng bộ. Producer publish message lên topic; subscription quản lý việc phân phối message đến consumer. Khi tích hợp qua Eventarc, Eventarc tạo trigger cho loại sự kiện message được publish và chuyển CloudEvent đến target.

Event type thường dùng:

~~~text
google.cloud.pubsub.topic.v1.messagePublished
~~~

Payload event chứa thông tin subscription và message. Trường data của Pub/Sub message được mã hóa Base64; consumer cần decode trước khi parse nội dung nghiệp vụ.

Ví dụ phần data của CloudEvent:

~~~json
{
  "subscription": "projects/demo/subscriptions/orders-eventarc-sub",
  "message": {
    "data": "eyJvcmRlcklkIjoiT1JELTEwMDEiLCJjdXN0b21lcklkIjoiQ1VTLTIwMDEifQ==",
    "messageId": "2070443601311540",
    "publishTime": "2026-11-17T10:15:30.123Z",
    "attributes": {
      "schemaVersion": "1",
      "eventType": "OrderPlaced"
    },
    "orderingKey": "ORD-1001"
  }
}
~~~

DTO Java:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubPublishedData(
        String subscription,
        PubSubMessage message) {
}

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubMessage(
        String data,
        String messageId,
        String publishTime,
        Map<String, String> attributes,
        String orderingKey) {
}
~~~

Sau khi parse PubSubPublishedData, function decode trường message.data:

~~~java
import java.util.Base64;
import java.nio.charset.StandardCharsets;

byte[] payloadBytes =
        Base64.getDecoder().decode(published.message().data());

String payloadJson =
        new String(payloadBytes, StandardCharsets.UTF_8);

OrderPlacedPayload payload =
        objectMapper.readValue(payloadJson, OrderPlacedPayload.class);
~~~

Không parse trực tiếp chuỗi Base64 thành JSON. Nếu producer gửi dữ liệu nhị phân thay vì JSON UTF-8, consumer phải xử lý theo content type hoặc hợp đồng đã thống nhất.

### 5.1. Attributes và message data

Pub/Sub message có hai vùng dữ liệu:

- data: nội dung chính, được mã hóa Base64 trong event payload.
- attributes: các cặp key/value dạng chuỗi dùng cho metadata, lọc hoặc định tuyến.

Không nên đặt toàn bộ payload nghiệp vụ vào attributes. Attributes phù hợp với metadata nhỏ như schemaVersion, eventType, tenant hoặc correlationId. Nội dung nghiệp vụ có cấu trúc nên nằm trong data và có schema rõ ràng.

## 6. Tạo Eventarc trigger và cấu hình vùng

Để tạo trigger, cần xác định:

- Nguồn sự kiện: Cloud Storage bucket hoặc Pub/Sub topic.
- Event type cần nhận.
- Đích: Cloud Run service hoặc Cloud Run function.
- Region/location của trigger và đích.
- Service account mà Eventarc dùng để gọi đích.
- Bộ lọc bổ sung như bucket hoặc các thuộc tính nguồn hỗ trợ.

Với Cloud Storage, location của trigger cần tương thích với location của bucket và các giới hạn của Eventarc. Với Pub/Sub, cần chọn location phù hợp với trigger, topic và nơi triển khai target. Không chọn region chỉ dựa vào nơi người dùng cuối đang ở; hãy xét vị trí dữ liệu, yêu cầu độ trễ, khả năng hỗ trợ nguồn và chi phí truyền dữ liệu.

Quy trình tạo trigger ở mức khái niệm:

1. Bật các API cần thiết như Eventarc, Cloud Run, Cloud Storage hoặc Pub/Sub và dịch vụ build/deploy đang sử dụng.
2. Tạo service account riêng cho trigger.
3. Cấp quyền Eventarc nhận sự kiện và quyền invoke target cho service account.
4. Triển khai Cloud Run service hoặc Cloud Run function trước.
5. Tạo trigger với event type, source filter, location và destination.
6. Kiểm tra trigger ở trạng thái hoạt động và gửi một event thử.
7. Xác nhận target nhận CloudEvent và trả phản hồi thành công.

Ví dụ lệnh tạo trigger Cloud Storage đến Cloud Run service:

~~~bash
gcloud eventarc triggers create storage-finalized \
  --location=REGION \
  --destination-run-service=JAVA_SERVICE \
  --destination-run-region=REGION \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=BUCKET_NAME" \
  --service-account=EVENTARC_TRIGGER_SA
~~~

Ví dụ này minh họa trigger cho object finalized. Thay các placeholder bằng resource thực tế và kiểm tra các yêu cầu location, quyền, API cũng như cú pháp gcloud hiện hành trước khi chạy. Các loại nguồn và phiên bản gcloud khác nhau có thể yêu cầu tham số transport hoặc cấu hình bổ sung.

Với Pub/Sub, chọn event type messagePublished và topic làm nguồn theo cú pháp Eventarc được hỗ trợ cho loại trigger đang dùng. Đảm bảo producer publish vào đúng topic mà trigger theo dõi. Không nhầm topic nguồn với topic transport nội bộ mà một số loại trigger hoặc cấu hình Eventarc sử dụng.

## 7. Java handler dùng CloudEventsFunction

Với Java Functions Framework, có thể triển khai giao diện CloudEventsFunction. Framework chuyển HTTP CloudEvent thành đối tượng CloudEvent để handler đọc metadata và data.

Ví dụ sau minh họa một handler nhận cả hai event type. DTO StorageObjectData và PubSubPublishedData là các record đã trình bày ở trên.

~~~java
package com.example.events;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.util.Base64;

public class EventarcHandler implements CloudEventsFunction {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final String STORAGE_FINALIZED =
            "google.cloud.storage.object.v1.finalized";

    private static final String PUBSUB_PUBLISHED =
            "google.cloud.pubsub.topic.v1.messagePublished";

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (event.getData() == null) {
            throw new IllegalArgumentException("CloudEvent data is required");
        }

        byte[] eventData = event.getData().toBytes();

        switch (event.getType()) {
            case STORAGE_FINALIZED -> handleStorage(event, eventData);
            case PUBSUB_PUBLISHED -> handlePubSub(event, eventData);
            default -> throw new UnsupportedOperationException(
                    "Unsupported event type: " + event.getType());
        }
    }

    private void handleStorage(
            CloudEvent event,
            byte[] eventData) throws Exception {

        StorageObjectData object =
                MAPPER.readValue(eventData, StorageObjectData.class);

        storageProcessor().processOnce(
                event.getSource().toString(),
                event.getId(),
                object);
    }

    private void handlePubSub(
            CloudEvent event,
            byte[] eventData) throws Exception {

        PubSubPublishedData published =
                MAPPER.readValue(eventData, PubSubPublishedData.class);

        byte[] payload = Base64.getDecoder().decode(
                published.message().data());

        OrderPlacedPayload order =
                MAPPER.readValue(payload, OrderPlacedPayload.class);

        orderProcessor().processOnce(
                event.getSource().toString(),
                event.getId(),
                published.message().messageId(),
                order);
    }

    private StorageProcessor storageProcessor() {
        // Lấy dependency từ composition root hoặc dependency injection.
        throw new UnsupportedOperationException("Wire application service");
    }

    private OrderProcessor orderProcessor() {
        // Lấy dependency từ composition root hoặc dependency injection.
        throw new UnsupportedOperationException("Wire application service");
    }
}
~~~

Các kiểu nghiệp vụ mà handler gọi có thể được khai báo theo hợp đồng nội bộ:

~~~java
public record OrderPlacedPayload(
        String orderId,
        String customerId) {
}

public interface StorageProcessor {
    void processOnce(
            String source,
            String eventId,
            StorageObjectData object) throws Exception;
}

public interface OrderProcessor {
    void processOnce(
            String source,
            String eventId,
            String messageId,
            OrderPlacedPayload order) throws Exception;
}
~~~

Đây là skeleton minh họa ranh giới adapter; hai factory cuối cần được thay bằng dependency injection hoặc composition root thực tế. Trong production, không tạo service nghiệp vụ bằng cách để method ném UnsupportedOperationException như ví dụ placeholder.

Nhánh default trong switch cũng cần chính sách rõ ràng. Nếu event type không được hỗ trợ là lỗi hợp đồng vĩnh viễn, có thể ghi nhận vào vùng cách ly hoặc dead-letter có kiểm soát rồi trả thành công sau khi lưu bền vững; nếu chỉ ném exception mãi, Eventarc có thể retry cùng event cho đến khi hết chính sách retry.

Một ứng dụng thực tế nên:

- Cấu hình ObjectMapper một lần và đăng ký module cần thiết.
- Xác thực event source, type và schema.
- Kiểm tra payload null, rỗng, quá lớn hoặc sai định dạng.
- Chỉ gọi use case sau khi validation thành công.
- Ghi nhận idempotency bền vững.
- Không log toàn bộ data hoặc nội dung file.
- Trả lỗi có chủ đích để Eventarc retry khi lỗi tạm thời.

Nếu một trigger chỉ nhận một event type, có thể dùng handler chuyên biệt và bỏ phần switch. Tách handler theo loại sự kiện giúp giảm coupling và cấp quyền theo đúng nguồn dữ liệu.

## 8. Xử lý Cloud Storage object an toàn

Khi function nhận event finalized, object có thể đã bị ghi đè hoặc xóa trước lúc function đọc. Do đó, không nên chỉ dùng bucket và name rồi lấy phiên bản hiện tại nếu nghiệp vụ cần xử lý đúng nội dung đã phát event.

Một quy trình an toàn:

1. Đọc bucket, name và generation từ payload.
2. Kiểm tra object nằm trong bucket được phép.
3. Tạo request đọc object có điều kiện generation bằng giá trị event.
4. Giới hạn kích thước file và content type.
5. Xử lý stream thay vì tải toàn bộ file vào heap nếu file lớn.
6. Ghi kết quả gắn với generation đã xử lý.
7. Lưu khóa chống trùng để lần giao lại không tạo kết quả thứ hai.

Nếu object đã bị xóa hoặc generation không còn khả dụng, cần phân biệt đây là trường hợp hợp lệ theo nghiệp vụ hay lỗi tạm thời. Không retry vô hạn một object đã bị xóa vĩnh viễn.

Object name có thể chứa dấu cách, Unicode hoặc ký tự đặc biệt. Dùng Cloud Storage client library để truy cập object thay vì tự ghép URL mà không encode đúng. Cần xác thực bucket và prefix để function không đọc nhầm object ngoài phạm vi.

## 9. Retry và acknowledgement

Eventarc giao sự kiện theo mô hình có thể phát lại. Target cần trả HTTP response thành công sau khi đã xử lý và lưu kết quả cần thiết. Nếu target trả lỗi hoặc không phản hồi trong thời gian cho phép, Eventarc có thể thử giao lại theo retry policy của trigger và nguồn.

Các nguyên tắc:

- Trả 2xx khi event đã được xử lý hoặc đã được lưu bền vững vào một hàng đợi xử lý nội bộ.
- Trả lỗi khi có lỗi tạm thời và muốn Eventarc thử lại.
- Không trả thành công trước khi dữ liệu cần xử lý đã được lưu bền vững.
- Không retry vô hạn lỗi schema hoặc event type không hỗ trợ.
- Cấu hình retry, retention và dead-letter theo khả năng của nguồn/trigger.

Với Cloud Run target, phản hồi HTTP của service là tín hiệu giao nhận. Với Cloud Run functions, exception từ handler thường được framework chuyển thành phản hồi lỗi. Cần kiểm tra cách runtime/framework ánh xạ exception để bảo đảm retry hoạt động như mong muốn.

Eventarc và Pub/Sub có chính sách retry riêng theo loại nguồn và cấu hình. Không nên giả định một khoảng retry cố định cho mọi trigger; kiểm tra cấu hình thực tế và tài liệu dịch vụ đang dùng.

## 10. Idempotency và xử lý event trùng

Một sự kiện có thể được giao nhiều lần do retry, timeout hoặc mất response. Consumer cần bảo đảm xử lý lặp không tạo hiệu ứng nghiệp vụ trùng.

Với CloudEvent, có thể dùng cặp source và id làm khóa nhận diện sự kiện. Với Cloud Storage, bổ sung bucket, object name và generation để định danh nội dung cụ thể. Với Pub/Sub, messageId là metadata hữu ích; CloudEvent id cũng nhận diện lần phát sự kiện trong envelope.

Ví dụ bảng chống trùng:

~~~sql
CREATE TABLE processed_events (
    source VARCHAR(500) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source, event_id)
);
~~~

Consumer ghi khóa và thay đổi nghiệp vụ trong cùng transaction nếu cùng cơ sở dữ liệu hỗ trợ. Nếu khóa đã tồn tại, coi sự kiện là đã được xử lý và kết thúc an toàn.

Không chỉ dùng biến trong bộ nhớ hoặc cache cục bộ để chống trùng. Các instance Cloud Run có thể chạy song song, khởi động lại hoặc chuyển sang máy khác. Trạng thái idempotency cần được lưu ở nơi bền vững và có ràng buộc duy nhất để xử lý đồng thời.

Đối với Cloud Storage, cùng một object name có thể có nhiều generation. Nếu khóa chỉ gồm bucket và name, lần upload mới có thể bị nhầm là event cũ. Đưa generation vào khóa khi nghiệp vụ xử lý từng phiên bản nội dung.

## 11. Thứ tự sự kiện và trạng thái nghiệp vụ

Eventarc không nên được xem là cơ chế bảo đảm thứ tự toàn cục. Các event có thể đến trễ hoặc được xử lý đồng thời. Với Pub/Sub, ordering key có thể hỗ trợ thứ tự trong phạm vi cấu hình phù hợp, nhưng consumer vẫn phải chịu được retry và xử lý lặp.

Nếu nghiệp vụ cần thứ tự:

- Dùng ordering key theo aggregate ID, ví dụ orderId.
- Lưu version hoặc sequence number trong payload.
- Chỉ áp dụng event nếu version phù hợp với trạng thái hiện tại.
- Lưu event đến sớm để xử lý sau nếu cần.
- Xác định hành động bù trừ khi event đến sai thứ tự.

Với Cloud Storage, generation cho biết phiên bản object; với Pub/Sub, producer có thể đưa aggregateVersion vào payload. Không dùng timestamp đơn lẻ để suy ra thứ tự tuyệt đối giữa các producer vì đồng hồ có thể lệch.

## 12. IAM và bảo mật cho Eventarc

Eventarc gọi target bằng danh tính dịch vụ được cấu hình. Target nên yêu cầu xác thực thay vì cho phép truy cập công khai nếu không có lý do rõ ràng.

Các vai trò thường gặp trong cấu hình:

- Service account của trigger cần quyền nhận sự kiện theo yêu cầu Eventarc, thường là roles/eventarc.eventReceiver.
- Service account của trigger cần quyền invoke Cloud Run target, thường là roles/run.invoker trên đúng service.
- Producer cần quyền ghi object vào bucket hoặc publish message lên Pub/Sub topic.
- Java service account cần quyền đọc object hoặc gọi dịch vụ downstream nếu nghiệp vụ cần.
- Service agent của Google Cloud cần các quyền dịch vụ được quản lý để vận hành tích hợp.

Không cấp roles/editor hoặc quyền project-wide rộng cho trigger service account chỉ để làm trigger hoạt động. Gắn quyền ở phạm vi resource nếu có thể.

Với Cloud Storage, quyền ghi bucket nên được tách khỏi quyền đọc object của function. Với Pub/Sub, quyền publish của producer nên tách khỏi quyền subscribe/pull nếu ứng dụng dùng consumer trực tiếp. Khi dùng Eventarc, không tự cấp Pub/Sub Subscriber cho function nếu function không trực tiếp gọi pull API.

Không tin payload chỉ vì nó đến qua Eventarc. Kiểm tra source, type, bucket/topic dự kiến và dữ liệu nghiệp vụ. Tránh log token, thông tin cá nhân hoặc nội dung file.

## 13. Vùng, độ trễ và giới hạn tích hợp

Eventarc trigger có location. Cloud Storage bucket, Pub/Sub topic và target cũng có vị trí hoặc phạm vi triển khai riêng. Một số nguồn trực tiếp yêu cầu trigger ở cùng location với tài nguyên nguồn hoặc chỉ hỗ trợ các tổ hợp region nhất định.

Trước khi triển khai, xác nhận:

- Location của bucket hoặc topic.
- Region của Eventarc trigger.
- Region của Cloud Run service hoặc function.
- Loại event provider và event type được hỗ trợ tại location đó.
- Yêu cầu cùng project hoặc quyền cross-project.
- Chi phí truyền dữ liệu và độ trễ giữa nguồn với target.

Đặt function gần nguồn dữ liệu thường giúp giảm độ trễ và chi phí truyền dữ liệu, nhưng không được vi phạm yêu cầu location của dịch vụ. Với bucket multi-region hoặc dual-region, kiểm tra quy tắc location cụ thể của Eventarc trước khi chọn trigger region.

## 14. Mở rộng và kiểm soát concurrency

Cloud Run có thể mở rộng số instance khi lưu lượng event tăng. Điều đó giúp xử lý backlog nhanh hơn nhưng cũng có thể làm database hoặc API phụ thuộc quá tải.

Cần cấu hình và theo dõi:

- Maximum instances để giới hạn số instance.
- Concurrency trên mỗi instance.
- CPU và memory phù hợp với kích thước payload.
- Timeout request.
- Giới hạn kết nối database.
- Tốc độ xử lý event so với tốc độ publish.
- Backlog, retry và tuổi event.

Nếu một instance xử lý nhiều request đồng thời, Java code và dependency dùng chung phải thread-safe. ObjectMapper sau khi cấu hình xong có thể dùng chung; mutable state nghiệp vụ trong static field thì không nên dùng để phối hợp invocation.

Với file lớn, tránh tải toàn bộ nội dung vào heap khi có thể stream. Với Pub/Sub batch hoặc message lớn, giới hạn kích thước payload và thời gian xử lý. Nếu downstream không chịu được tải tăng nhanh, dùng concurrency cap hoặc queue trung gian để tạo backpressure.

## 15. Quan sát và chẩn đoán

Một luồng Eventarc cần quan sát cả nguồn, trigger và target.

Các tín hiệu nên ghi nhận:

- CloudEvent id, source, type và subject.
- Bucket/object/generation hoặc Pub/Sub messageId.
- Correlation ID và trace context nếu có.
- Thời gian nhận và thời gian xử lý.
- Kết quả xử lý, retry và lỗi.
- Số event đã xử lý, bị bỏ qua hoặc chuyển luồng lỗi.

Dùng Cloud Logging để tìm log theo event ID hoặc correlation ID. Dùng Cloud Monitoring để theo dõi request count, error rate, latency, instance count và metric liên quan đến Eventarc, Cloud Run, Pub/Sub hoặc Cloud Storage. Dùng Cloud Trace hoặc OpenTelemetry nếu cần nối thời gian xử lý qua nhiều dịch vụ.

Không tạo metric label có cardinality cao như object name, orderId hoặc messageId. Đưa các định danh đó vào log hoặc trace. Đặt cảnh báo cho error rate, latency, backlog, retry và dead-letter theo mục tiêu dịch vụ.

## 16. Chi phí và lựa chọn kiến trúc

Chi phí có thể đến từ:

- Eventarc trigger và số event được giao theo mô hình tính phí hiện hành.
- Cloud Run/Cloud Run functions theo request, CPU, memory và thời gian.
- Pub/Sub theo dung lượng message, throughput và retention.
- Cloud Storage theo dung lượng, thao tác và network.
- Logging, Monitoring và Trace.
- Database hoặc downstream service được function gọi.

Eventarc giảm nhu cầu tự vận hành webhook hoặc polling, nhưng mỗi event vẫn có chi phí giao nhận và xử lý. Nếu một bucket phát hàng triệu event nhỏ hoặc producer publish message quá thường xuyên, cần xem xét lọc event, batch xử lý, kích thước payload và retention.

Chọn Eventarc khi muốn định tuyến sự kiện dịch vụ theo CloudEvents đến HTTP target. Chọn Pub/Sub pull consumer khi cần tự kiểm soát poll, flow control, ack deadline và batch ở cấp client. Với workload xử lý file, Cloud Storage event kết hợp Eventarc thường tự nhiên hơn polling bucket liên tục.

## 17. Quy trình triển khai Java function nhận Eventarc

1. **Xác định nguồn:** Cloud Storage hay Pub/Sub, event type nào và điều kiện lọc nào.
2. **Thiết kế hợp đồng:** CloudEvent envelope, payload schema, event ID và version.
3. **Chọn target:** Cloud Run service hoặc Cloud Run function theo cách triển khai Java.
4. **Viết handler:** Dùng CloudEventsFunction hoặc HTTP adapter; tách logic nghiệp vụ khỏi wrapper.
5. **Validate:** Kiểm tra source, type, schema, kích thước và quyền truy cập dữ liệu.
6. **Thiết kế idempotency:** Lưu source + event ID và khóa nghiệp vụ trong kho bền vững.
7. **Cấu hình IAM:** Trigger service account, event receiver, run invoker và quyền đọc/ghi nguồn.
8. **Chọn location:** Kiểm tra tương thích giữa nguồn, trigger và target.
9. **Tạo trigger:** Cấu hình event type, filter, destination và retry.
10. **Kiểm thử:** Upload file hoặc publish message thử; xác nhận payload Java parse đúng.
11. **Thử lỗi:** Mô phỏng timeout, duplicate, malformed event và downstream unavailable.
12. **Quan sát:** Tạo log, metric, alert và dashboard.
13. **Triển khai an toàn:** Giới hạn concurrency, timeout, memory và kiểm tra chi phí.

## 18. Các lỗi thường gặp

**Nhầm Eventarc với Pub/Sub pull:** Function dùng Eventarc không cần tự poll subscription. Chỉ dùng Pub/Sub client pull khi chọn mô hình consumer pull riêng.

**Parse sai payload Pub/Sub:** Trường message.data là Base64. Decode trước khi parse JSON hoặc xử lý byte.

**Dùng cùng DTO cho Storage và Pub/Sub:** Hai event type có schema khác nhau. Parse theo type rồi chuyển sang command nội bộ.

**Dùng object name làm khóa chống trùng:** Một object có thể có nhiều generation. Dùng event identity và generation.

**Đọc phiên bản object hiện tại:** Event cũ có thể đến sau khi object đã bị ghi đè. Đọc theo generation nếu nghiệp vụ cần đúng nội dung của event.

**Trả 2xx quá sớm:** Eventarc xem giao nhận thành công dù xử lý chưa được lưu bền vững. Chỉ xác nhận sau khi commit hoặc ghi nhận công việc an toàn.

**Retry lỗi vĩnh viễn:** Payload sai schema hoặc type không hỗ trợ bị giao lại nhiều lần. Cách ly, cảnh báo hoặc xử lý theo chính sách lỗi vĩnh viễn.

**Không chống duplicate:** Retry tạo xử lý file, đơn hàng hoặc thanh toán trùng. Dùng idempotency bền vững.

**Tin rằng event luôn đúng thứ tự:** Consumer có thể nhận event trễ hoặc đồng thời. Dùng generation, aggregate version hoặc ordering key khi cần.

**Cấp IAM quá rộng:** Trigger hoặc function có quyền toàn project. Cấp quyền ở resource và theo đúng vai trò.

**Không giới hạn concurrency:** Event tăng đột biến làm database quá tải. Đặt max instances/concurrency và theo dõi backlog.

**Không quan sát nguồn và đích:** Chỉ xem log function mà không thấy trigger hoặc queue bị nghẽn. Theo dõi toàn bộ đường đi sự kiện.

## 19. Checklist trước khi đưa Eventarc vào production

- [ ] Đã xác định đúng nguồn Cloud Storage hoặc Pub/Sub.
- [ ] Event type và filter chỉ nhận sự kiện cần thiết.
- [ ] Location của nguồn, trigger và target tương thích.
- [ ] Target nhận CloudEvents và kiểm tra specversion, source, type, id.
- [ ] Payload Storage và Pub/Sub được ánh xạ bằng DTO riêng.
- [ ] Pub/Sub message.data được decode Base64 trước khi parse.
- [ ] Cloud Storage generation được dùng khi cần đọc đúng phiên bản object.
- [ ] Có idempotency dựa trên định danh sự kiện bền vững.
- [ ] Retry và lỗi vĩnh viễn có chính sách riêng.
- [ ] Target chỉ trả thành công sau khi xử lý hoặc lưu bền vững.
- [ ] Service account của trigger có quyền tối thiểu.
- [ ] Function chỉ có quyền đọc/ghi dữ liệu cần thiết.
- [ ] Concurrency, timeout, memory và payload size được giới hạn.
- [ ] Có log event ID, source, type và correlation ID mà không lộ payload nhạy cảm.
- [ ] Có metric latency, errors, retry, backlog và dead-letter.
- [ ] Đã thử duplicate, out-of-order, malformed event và downstream failure.
- [ ] Chi phí Eventarc, Cloud Run, Pub/Sub, Storage và observability được ước lượng.

## Kết luận

Eventarc kết nối sự kiện từ Cloud Storage và Pub/Sub đến Cloud Run hoặc Cloud Run functions bằng hợp đồng CloudEvents. Với Cloud Storage, payload mô tả object và generation; với Pub/Sub, payload chứa message metadata và trường data mã hóa Base64. Java handler cần kiểm tra event type, parse đúng DTO, xác thực nguồn, xử lý nghiệp vụ idempotent và chỉ trả thành công sau khi kết quả được lưu bền vững.

Để vận hành production, hãy chọn location phù hợp, cấp IAM tối thiểu, cấu hình retry, giới hạn concurrency và theo dõi toàn bộ đường đi từ nguồn đến target. Eventarc giúp giảm coupling và loại bỏ polling ở phía ứng dụng trong mô hình push event, nhưng tính đúng đắn vẫn phụ thuộc vào schema, trạng thái, xử lý trùng và khả năng phục hồi của Java function.

