# Kết nối Storage với Spring Integration và thông báo thay đổi đối tượng

## 1. Từ lưu trữ file đến xử lý theo luồng

Một ứng dụng Spring Boot có thể upload file lên Google Cloud Storage (GCS), nhưng nhiều nghiệp vụ cần xử lý tiếp sau khi object xuất hiện: kiểm tra nội dung, tạo thumbnail, trích xuất metadata, quét virus, lập chỉ mục tìm kiếm, đồng bộ dữ liệu sang hệ thống khác hoặc cập nhật trạng thái hồ sơ.

Có hai cách phổ biến để đưa object vào một Spring Integration flow:

- **Polling Storage:** ứng dụng định kỳ liệt kê bucket hoặc prefix và nhận các file mới qua MessageChannel. Cách này phù hợp với batch nhỏ, đồng bộ file hoặc hệ thống không cần phản ứng ngay khi object thay đổi.
- **Event-driven qua Pub/Sub:** Cloud Storage phát notification khi object được tạo, xóa, chuyển thành noncurrent hoặc cập nhật metadata. Pub/Sub chuyển message đến subscription; PubSubInboundChannelAdapter đưa message vào Spring Integration flow. Cách này phù hợp khi cần phản ứng theo sự kiện và mở rộng nhiều consumer.

Spring Framework on Google Cloud còn cung cấp GCS inbound/outbound channel adapters để đọc, stream và ghi file qua MessageChannels. Những adapter này làm việc trực tiếp với Storage theo kiểu polling/file transfer. Chúng không thay thế Pub/Sub notifications khi nghiệp vụ cần biết chính xác event type, generation hoặc metadata update.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào Spring Integration channel adapters cho GCS và luồng thông báo object change qua Pub/Sub.

Sau bài học, bạn có thể:

- Phân biệt GCS polling adapters với Pub/Sub event notifications.
- Chọn GcsInboundFileSynchronizingMessageSource, GcsStreamingMessageSource hoặc GcsMessageHandler.
- Cấu hình Cloud Storage notification cho OBJECT_FINALIZE, OBJECT_DELETE, OBJECT_ARCHIVE và OBJECT_METADATA_UPDATE.
- Cấp đúng quyền cho Cloud Storage service agent, Pub/Sub subscriber và ứng dụng đọc object.
- Kết nối subscription với PubSubInboundChannelAdapter và MessageChannel.
- Đọc Pub/Sub attributes và JSON object metadata payload.
- Xử lý ack/nack, retry, duplicate delivery và event đến sai thứ tự.
- Dùng generation/metageneration để tránh xử lý nhầm phiên bản object.
- Thiết kế idempotency, dead-letter handling, quan sát và integration test.

> **Phạm vi phiên bản:** Ví dụ dùng Spring Framework on Google Cloud (Spring Cloud GCP) với package hiện hành com.google.cloud.spring..., Google Cloud Storage Java client và Spring Integration. Quản lý version bằng Spring Framework on Google Cloud BOM tương thích với Spring Boot của dự án. Không trộn package/API của Spring Cloud GCP đời cũ org.springframework.cloud.gcp... với major version hiện hành. Hãy kiểm tra Javadoc của đúng BOM đã resolve trước khi áp dụng.

## 2. Kiến trúc tích hợp

### 2.1. Polling file qua GCS channel adapter

~~~mermaid
flowchart LR
    GCS["Cloud Storage bucket"] --> POLL["GcsInboundFileSynchronizingMessageSource<br/>hoặc GcsStreamingMessageSource"]
    POLL --> CHANNEL["Spring Integration MessageChannel"]
    CHANNEL --> FILTER["Filter / Transformer"]
    FILTER --> SERVICE["ServiceActivator"]
    SERVICE --> DB["Database / downstream service"]
    OUT["Message<File>"] --> HANDLER["GcsMessageHandler"]
    HANDLER --> GCS
~~~

Polling adapter định kỳ truy vấn bucket/prefix, lấy file và phát message. Với synchronizing adapter, file được tải xuống thư mục local trước khi message được phát. Với streaming adapter, payload là InputStream và ứng dụng đọc trực tiếp từ remote object.

### 2.2. Event-driven qua Pub/Sub notifications

~~~mermaid
sequenceDiagram
    participant App as Spring Boot upload service
    participant GCS as Cloud Storage
    participant Topic as Pub/Sub topic
    participant Sub as Pub/Sub subscription
    participant Adapter as PubSubInboundChannelAdapter
    participant Flow as Spring Integration flow

    App->>GCS: Upload object
    GCS->>Topic: OBJECT_FINALIZE notification
    Topic->>Sub: Message delivery
    Sub->>Adapter: Streaming pull
    Adapter->>Flow: Spring Message + attributes + payload
    Flow->>Flow: Deduplicate / validate generation
    Flow->>GCS: Read đúng object generation
    Flow->>Flow: Process business data
    Flow->>Sub: ACK sau khi xử lý và commit
~~~

Trong kiến trúc này, GCS không gọi trực tiếp Spring Boot endpoint. GCS publish notification lên Pub/Sub topic; ứng dụng nhận message qua subscription. Pub/Sub tách rời storage producer và các consumer, cho phép nhiều dịch vụ cùng xử lý một sự kiện bằng các subscription riêng.

### 2.3. Chọn đúng cơ chế

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Định kỳ nhập file từ prefix | GcsInboundFileSynchronizingMessageSource | Polling và đồng bộ file xuống local directory |
| Xử lý file lớn mà không muốn tạo bản local | GcsStreamingMessageSource | Payload là InputStream |
| Ghi file từ Spring message lên bucket | GcsMessageHandler | Outbound file adapter |
| Phản ứng khi object finalize/delete/update metadata | GCS Pub/Sub notification + PubSubInboundChannelAdapter | Có event type, generation và metadata |
| Nhiều service cùng nhận event | Pub/Sub topic với nhiều subscriptions | Fan-out độc lập |
| Chỉ cần trigger một function nhỏ | Cloud Run functions hoặc Eventarc | Có thể giảm phần messaging do ứng dụng tự vận hành |

Không dùng polling như một event log. Polling có thể bỏ lỡ trạng thái trung gian nếu object bị thay đổi hoặc xóa giữa hai lần quét. Ngược lại, notification cung cấp thông tin về event nhưng không tự tải bytes; consumer cần dùng Storage API nếu muốn đọc nội dung object.

## 3. GCS channel adapters cho Spring Integration

### 3.1. Dependency

Các GCS channel adapters nằm trong module spring-cloud-gcp-storage. Cần thêm spring-integration-file vì dependency này không được kéo vào transitive.

Maven:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-storage</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

Nếu dùng starter theo cấu hình Spring Framework on Google Cloud:

~~~gradle
dependencies {
    implementation("com.google.cloud:spring-cloud-gcp-starter-storage")
    implementation("org.springframework.integration:spring-integration-file")
}
~~~

Dùng BOM của Spring Framework on Google Cloud để quản lý version. Nếu starter đã tự cấu hình Storage bean, inject bean đó thay vì tạo thêm một client cho mỗi adapter.

### 3.2. Đồng bộ file về local directory

GcsInboundFileSynchronizingMessageSource là inbound message source cho file. Nó sử dụng GcsInboundFileSynchronizer để truy cập bucket, tải file về local directory và phát message có payload kiểu File.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.spring.storage.integration.inbound.GcsInboundFileSynchronizer;
import com.google.cloud.spring.storage.integration.inbound.GcsInboundFileSynchronizingMessageSource;
import com.google.cloud.spring.storage.integration.filters.GcsRegexPatternFileListFilter;
import java.io.File;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.MessageChannel;
import org.springframework.integration.channel.DirectChannel;

@Configuration(proxyBeanMethods = false)
public class GcsPollingConfiguration {

    @Bean
    MessageChannel newGcsFiles() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            channel = "newGcsFiles",
            poller = @Poller(fixedDelay = "5000"))
    MessageSource<File> gcsFileSource(Storage storage) {

        GcsInboundFileSynchronizer synchronizer =
                new GcsInboundFileSynchronizer(storage);

        synchronizer.setRemoteDirectory("training-documents");
        synchronizer.setFilter(
                new GcsRegexPatternFileListFilter("^incoming/.*"));

        GcsInboundFileSynchronizingMessageSource source =
                new GcsInboundFileSynchronizingMessageSource(synchronizer);

        source.setLocalDirectory(new File("./work/gcs-incoming"));
        source.setAutoCreateLocalDirectory(true);

        return source;
    }
}
~~~

Poller trên chạy mỗi 5 giây. Đây là cấu hình minh họa; chu kỳ thực tế cần dựa trên latency, số object và chi phí list/read metadata.

Xử lý file trong channel:

~~~java
import java.io.File;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class GcsFileProcessor {

    @ServiceActivator(inputChannel = "newGcsFiles")
    public void process(File file) {
        // Validate file, scan content, extract metadata, then persist result.
        // Chỉ xóa file local sau khi nghiệp vụ đã hoàn tất và có thể retry an toàn.
    }
}
~~~

Lưu ý vận hành:

- Thư mục local phải tồn tại hoặc cho phép adapter tự tạo.
- Container cần volume/disk phù hợp nếu file lớn.
- Dùng file filter để bỏ qua file tạm, file không đúng pattern hoặc file đã xử lý.
- Nếu cần tránh xử lý lại sau khi restart, dùng persistent metadata store/filter thay vì chỉ dựa trên bộ nhớ.
- Không xóa file local trước khi công việc downstream hoàn tất.
- Với GCS adapter, remote directory là tên bucket; lọc object prefix bằng FileListFilter như GcsRegexPatternFileListFilter. GCS object name có thể chứa dấu gạch chéo nhưng đó không phải thư mục vật lý.
- Polling list bucket có thể tạo nhiều request khi bucket lớn; thu hẹp phạm vi bằng filter và tách bucket khi cần.

### 3.3. Streaming inbound adapter

GcsStreamingMessageSource gửi payload InputStream, không cần tải file về thư mục tạm trước. Adapter sử dụng GcsRemoteFileTemplate và GcsSessionFactory.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.spring.storage.integration.GcsRemoteFileTemplate;
import com.google.cloud.spring.storage.integration.GcsSessionFactory;
import com.google.cloud.spring.storage.integration.filters.GcsRegexPatternFileListFilter;
import com.google.cloud.spring.storage.integration.inbound.GcsStreamingMessageSource;
import java.io.InputStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;

@Configuration(proxyBeanMethods = false)
public class GcsStreamingConfiguration {

    @Bean
    @InboundChannelAdapter(
            channel = "gcsStreamingFiles",
            poller = @Poller(fixedDelay = "10000"))
    MessageSource<InputStream> gcsStreamingSource(Storage storage) {

        GcsStreamingMessageSource source =
                new GcsStreamingMessageSource(
                        new GcsRemoteFileTemplate(
                                new GcsSessionFactory(storage)));

        source.setRemoteDirectory("training-documents");
        source.setFilter(
                new GcsRegexPatternFileListFilter("^large-files/.*"));
        return source;
    }
}
~~~

Streaming giúp tránh tạo file local trung gian, nhưng consumer phải đọc và đóng stream đúng cách:

~~~java
import java.io.InputStream;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class GcsStreamingProcessor {

    @ServiceActivator(inputChannel = "gcsStreamingFiles")
    public void process(InputStream input) throws Exception {
        try (InputStream stream = input) {
            // Stream bytes to a parser or downstream service.
            // Không đọc toàn bộ file vào byte[] nếu kích thước lớn.
        }
    }
}
~~~

Không chuyển InputStream sang thread khác rồi đóng stream trước khi consumer hoàn tất. Nếu cần xử lý bất đồng bộ, hãy thiết kế ownership và vòng đời stream rõ ràng hoặc lưu file vào vùng staging có kiểm soát.

GcsStreamingMessageSource có thể nhận Comparator<BlobInfo> để sắp xếp file được xử lý. Thứ tự này chỉ áp dụng cho lần polling của adapter; nó không tạo bảo đảm thứ tự toàn cục giữa các lần poll hoặc giữa nhiều instance.

### 3.4. Outbound adapter ghi file lên GCS

GcsMessageHandler nhận Spring message có payload File và ghi file vào bucket/prefix được cấu hình.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.spring.storage.integration.GcsSessionFactory;
import com.google.cloud.spring.storage.integration.outbound.GcsMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration(proxyBeanMethods = false)
public class GcsOutboundConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "writeFilesToGcs")
    MessageHandler gcsOutboundHandler(Storage storage) {

        GcsMessageHandler handler =
                new GcsMessageHandler(new GcsSessionFactory(storage));

        handler.setRemoteDirectoryExpression(
                new LiteralExpression("training-documents"));
        handler.setFileNameGenerator(message ->
                "processed/" + ((java.io.File) message.getPayload()).getName());

        return handler;
    }
}
~~~

Có thể nối một MessagingGateway hoặc service gửi Message<File> vào channel writeFilesToGcs. Hãy kiểm soát file name, remote directory và chế độ xử lý khi object cùng tên đã tồn tại. Nếu cần create-only hoặc generation precondition cho nghiệp vụ quan trọng, dùng Storage client trực tiếp hoặc một adapter tùy chỉnh có truyền precondition; không giả định mọi tùy chọn của Storage.create đều được expose bởi GcsMessageHandler.

### 3.5. Polling filters và trạng thái đã nhận

Polling có thể nhìn thấy cùng object ở nhiều lần quét nếu filter không lưu trạng thái hoặc object bị cập nhật. Một số filter GCS có sẵn trong module:

- GcsSimplePatternFileListFilter: lọc theo pattern tên file.
- GcsRegexPatternFileListFilter: lọc theo regular expression.
- GcsPersistentAcceptOnceFileListFilter: lưu trạng thái đã nhận qua ConcurrentMetadataStore.

Một filter accept-once giúp giảm xử lý lặp khi polling, nhưng không thay thế idempotency của nghiệp vụ. Object có thể được upload lại với cùng tên nhưng generation mới; filter chỉ dựa trên tên có thể không phân biệt được phiên bản. Khi cần xử lý theo từng generation, hãy đưa generation vào khóa xử lý hoặc dùng notification payload.

## 4. Cloud Storage Pub/Sub notifications

### 4.1. Notification configuration

Pub/Sub notification là cấu hình gắn với bucket. Cấu hình xác định:

- Pub/Sub topic nhận thông báo.
- Những event type cần phát.
- Payload metadata có được đính kèm hay không.
- Object name prefix dùng để lọc event.
- Custom attributes tùy chọn.

Cloud Storage publish message lên topic. Mỗi message có hai phần:

1. **Attributes:** các cặp key/value mô tả event.
2. **Payload:** chuỗi JSON metadata của object nếu cấu hình JSON_API_V1; có thể chọn NONE nếu không cần payload.

Không thể quản lý Pub/Sub notification của GCS bằng Google Cloud Console; dùng gcloud CLI, Terraform hoặc client library phù hợp.

### 4.2. Các event type

| Event type | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| OBJECT_FINALIZE | Object mới hoặc generation mới đã được tạo thành công | Quét file, tạo thumbnail, indexing |
| OBJECT_METADATA_UPDATE | Metadata của object hiện có thay đổi | Đồng bộ Content-Type, custom metadata, cache policy |
| OBJECT_DELETE | Object bị xóa vĩnh viễn | Dọn index, cập nhật trạng thái xóa |
| OBJECT_ARCHIVE | Live version trở thành noncurrent version khi Object Versioning bật | Theo dõi lịch sử hoặc xử lý version cũ |
| OBJECT_INITIALIZE | Bắt đầu tạo object trong zonal bucket | Theo dõi tiến trình tạo object của zonal bucket |

OBJECT_FINALIZE chỉ phát khi upload/copy/rewrite/restore hoàn tất thành công; upload thất bại không phát event này.

OBJECT_DELETE là xóa vĩnh viễn theo semantics của notification. Nó bao gồm object bị thay thế hoặc bị lifecycle xóa. Nếu Object Versioning bật, khi live object chỉ chuyển thành noncurrent version thì event tương ứng là OBJECT_ARCHIVE, không phải OBJECT_DELETE.

Khi thay thế object cùng tên, thường có hai event:

- OBJECT_FINALIZE cho generation mới; message có attribute overwroteGeneration.
- OBJECT_ARCHIVE hoặc OBJECT_DELETE cho generation cũ; message có attribute overwrittenByGeneration.

Không gộp hai event thành một thao tác “file updated” nếu nghiệp vụ cần biết generation cũ và generation mới.

### 4.3. Notification attributes

Các attribute chuẩn gồm:

| Attribute | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| notificationConfig | projects/_/buckets/docs/notificationConfigs/3 | Notification configuration đã tạo event |
| eventType | OBJECT_FINALIZE | Loại sự kiện |
| payloadFormat | JSON_API_V1 | Định dạng payload |
| bucketId | training-documents | Bucket chứa object |
| objectId | incoming/invoice-01.pdf | Object name |
| objectGeneration | 1730000000000000 | Generation của object |
| eventTime | 2026-11-24T03:15:00Z | Thời điểm event theo RFC 3339 |

Một số event có thêm overwrittenByGeneration hoặc overwroteGeneration. Notification configuration cũng có thể gắn tối đa 10 custom attributes.

Với payload JSON_API_V1, nội dung là JSON object metadata theo JSON API. Payload của OBJECT_DELETE mô tả metadata trước khi xóa và có thêm timeDeleted; payload của các event khác mô tả metadata sau thay đổi.

### 4.4. Delivery guarantee

Cloud Storage notifications có các đặc tính quan trọng:

- Delivery từ Cloud Storage sang Pub/Sub là at-least-once.
- Pub/Sub cũng có thể giao một event nhiều lần cho subscriber.
- Một event có thể được giao lặp với các Pub/Sub message ID khác nhau.
- Event không được đảm bảo phát đến Pub/Sub theo thứ tự xảy ra.
- Notification thường đến trong vài giây nhưng không có SLA thời gian; có thể trễ đáng kể.
- Sau khi tạo notification configuration, có thể mất tối đa khoảng 30 giây trước khi bắt đầu gửi event.
- Nếu notification liên tục không thể publish, Cloud Storage có thể xóa notification sau 7 ngày.
- Bật notifications làm thao tác phát sinh event chậm hơn một chút, thường ở mức khoảng 0,1 giây.

Vì vậy, consumer phải chịu được duplicate, delay, out-of-order và trạng thái object đã thay đổi trước khi event được xử lý.

## 5. Cấu hình topic, IAM và notification

### 5.1. Bật API và tạo topic

Ví dụ dùng project training-platform-dev:

~~~bash
gcloud services enable pubsub.googleapis.com \
  --project=training-platform-dev

gcloud pubsub topics create gcs-object-events \
  --project=training-platform-dev
~~~

Tạo subscription cho Spring Boot consumer:

~~~bash
gcloud pubsub subscriptions create gcs-object-events-sub \
  --topic=gcs-object-events \
  --project=training-platform-dev
~~~

Subscription là nơi consumer nhận message. Topic không lưu trữ message theo kiểu application queue độc lập nếu chưa có subscription phù hợp.

### 5.2. Cấp quyền cho Cloud Storage service agent

Cloud Storage service agent của project chứa bucket có dạng:

service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com

Lấy service agent:

~~~bash
gcloud storage service-agent \
  --project=training-platform-dev
~~~

Cấp quyền Pub/Sub Publisher trên topic:

~~~bash
gcloud pubsub topics add-iam-policy-binding gcs-object-events \
  --project=training-platform-dev \
  --member="serviceAccount:service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
~~~

Thay PROJECT_NUMBER bằng project number thực tế. Cấp role trên đúng topic, không cấp rộng ở project nếu không cần. Nếu topic nằm trong project khác bucket, service agent của project chứa bucket vẫn cần quyền Publisher trên topic đích.

Sau khi cấp role bằng API/automation, có thể cần chờ khoảng 30 giây để IAM binding có hiệu lực trước khi tạo notification configuration.

### 5.3. Cấp quyền cho Spring Boot consumer

Runtime service account của ứng dụng cần:

- roles/pubsub.subscriber trên subscription để pull/ack message.
- storage.objects.get trên bucket nếu ứng dụng đọc bytes hoặc metadata của object.
- storage.objects.list chỉ khi nghiệp vụ cần list object.
- Các quyền khác như create/delete chỉ khi service thực sự thực hiện thao tác đó.

Không cấp roles/storage.admin chỉ để đọc object theo event. Cloud Storage service agent publish event; Spring Boot consumer subscribe message; đây là hai principal khác nhau.

Principal cấu hình notification cần quyền cập nhật bucket metadata và xem Pub/Sub topic. Các role phổ biến trong tài liệu là Storage Admin trên bucket và Pub/Sub Admin trong project chứa topic; có thể dùng predefined/custom roles hẹp hơn nếu đã xác định đủ permission.

### 5.4. Tạo notification cho prefix và event cụ thể

~~~bash
gcloud storage buckets notifications create \
  gs://training-documents \
  --topic=projects/training-platform-dev/topics/gcs-object-events \
  --event-types=OBJECT_FINALIZE,OBJECT_METADATA_UPDATE,OBJECT_DELETE,OBJECT_ARCHIVE \
  --payload-format=json \
  --object-prefix=incoming/
~~~

Cấu hình trên chỉ phát các event thuộc prefix incoming/ và đính kèm JSON object metadata. Nếu cần theo dõi tất cả prefix, bỏ --object-prefix.

Liệt kê notification configuration:

~~~bash
gcloud storage buckets notifications list \
  gs://training-documents
~~~

Xem một notification configuration:

~~~bash
gcloud storage buckets notifications describe \
  projects/_/buckets/training-documents/notificationConfigs/NOTIFICATION_ID
~~~

Xóa notification configuration:

~~~bash
gcloud storage buckets notifications delete \
  projects/_/buckets/training-documents/notificationConfigs/NOTIFICATION_ID
~~~

Mỗi bucket có thể có tối đa 100 notification configurations và tối đa 10 configurations cho cùng một event type. Tạo hoặc xóa notification configuration làm tăng bucket metageneration. Không tạo một configuration mới cho từng object hoặc từng request.

## 6. Kết nối Pub/Sub với Spring Integration

### 6.1. Dependency

Để dùng Pub/Sub channel adapters, thêm starter Pub/Sub và Spring Integration core:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
~~~

Starter cấu hình PubSubTemplate và các subscriber operations dựa trên ADC/workload identity. Dùng BOM để đồng bộ version.

### 6.2. Tạo inbound channel adapter

PubSubInboundChannelAdapter dùng Streaming Pull để nhận message từ subscription và chuyển thành Spring Message. Mặc định payload là byte[]; message attributes được ánh xạ vào Spring headers.

~~~java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class GcsPubSubConfiguration {

    @Bean
    MessageChannel gcsObjectEvents() {
        return new DirectChannel();
    }

    @Bean
    PubSubInboundChannelAdapter gcsObjectEventAdapter(
            @Qualifier("gcsObjectEvents") MessageChannel output,
            PubSubTemplate pubSubTemplate) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(
                        pubSubTemplate,
                        "gcs-object-events-sub");

        adapter.setOutputChannel(output);
        adapter.setPayloadType(byte[].class);
        adapter.setAckMode(AckMode.MANUAL);

        return adapter;
    }
}
~~~

Tên subscription có thể là short name trong project hiện tại hoặc resource name đầy đủ projects/PROJECT_ID/subscriptions/SUBSCRIPTION_ID.

Chọn DirectChannel nếu muốn xử lý đồng bộ trên luồng nhận. Dùng ExecutorChannel hoặc queue/channel khác nếu cần tách thread, nhưng phải kiểm soát thời gian ack deadline và cách truyền acknowledgment handle đến nơi hoàn tất xử lý.

### 6.3. Attributes và JSON payload

Với adapter mặc định:

- message.getPayload() là byte[] chứa JSON metadata payload.
- Header eventType, bucketId, objectId, objectGeneration, eventTime, payloadFormat lấy từ Pub/Sub message attributes.
- GcpPubSubHeaders.ORIGINAL_MESSAGE chứa đối tượng acknowledgment gốc để ack/nack thủ công.

Có thể đặt payload type thành String.class nếu Pub/Sub message converter được cấu hình hỗ trợ chuyển byte payload sang String. Bài này giữ byte[] để parse UTF-8 rõ ràng bằng Jackson.

### 6.4. Xử lý event và ack/nack thủ công

Ví dụ dưới đây chỉ ack sau khi processor hoàn thành. Nếu có lỗi, message bị nack để Pub/Sub có thể giao lại theo subscription policy.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

@Component
public class GcsObjectEventHandler {

    private final ObjectMapper objectMapper;
    private final GcsObjectEventProcessor processor;

    public GcsObjectEventHandler(
            ObjectMapper objectMapper,
            GcsObjectEventProcessor processor) {
        this.objectMapper = objectMapper;
        this.processor = processor;
    }

    @ServiceActivator(inputChannel = "gcsObjectEvents")
    public void handle(Message<byte[]> message) {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        try {
            String eventType =
                    String.valueOf(message.getHeaders().get("eventType"));
            String bucket =
                    String.valueOf(message.getHeaders().get("bucketId"));
            String objectName =
                    String.valueOf(message.getHeaders().get("objectId"));
            String generation =
                    String.valueOf(message.getHeaders().get("objectGeneration"));
            String eventTime =
                    String.valueOf(message.getHeaders().get("eventTime"));

            JsonNode objectMetadata =
                    objectMapper.readTree(message.getPayload());

            processor.process(
                    eventType,
                    bucket,
                    objectName,
                    Long.parseLong(generation),
                    eventTime,
                    objectMetadata);

            original.ack();
        }
        catch (Exception ex) {
            original.nack();
            throw new MessagingException(message, ex);
        }
    }
}
~~~

GcsObjectEventProcessor là service nghiệp vụ của ứng dụng. Không log toàn bộ message nếu payload chứa metadata nhạy cảm hoặc custom attributes không nên xuất hiện trong log.

Trong flow thực tế, nên phân loại event trước khi xử lý:

- OBJECT_FINALIZE: đọc generation mới và bắt đầu pipeline xử lý file.
- OBJECT_METADATA_UPDATE: đồng bộ metadata hoặc đánh giá lại policy.
- OBJECT_DELETE: cập nhật index/trạng thái; không cố tải object đã bị xóa.
- OBJECT_ARCHIVE: cập nhật trạng thái phiên bản cũ khi versioning bật.

### 6.5. Ack mode và error channel

PubSubInboundChannelAdapter có ba chế độ:

| Ack mode | Xử lý thành công | Xử lý lỗi |
| --- | --- | --- |
| AUTO | Adapter ack | Adapter nack nếu lỗi được truyền ngược tới adapter |
| AUTO_ACK | Adapter ack | Không tự ack/nack khi lỗi không được xử lý thành công |
| MANUAL | Không tự ack | Không tự ack/nack; ứng dụng tự quyết định |

Trong MANUAL, ứng dụng phải gọi ack() hoặc nack() trên original message. Nếu quên cả hai, message sẽ được giao lại khi ack deadline hết hạn.

Khi dùng error channel, một error handler kết thúc bình thường được xem là xử lý thành công; ở AUTO/AUTO_ACK, message có thể được ack. Nếu muốn adapter áp dụng hành vi lỗi mặc định, error handler phải ném exception trở lại. Hãy kiểm tra behavior của error flow trước khi chọn ack mode.

nack() đặt ack deadline về 0 và có thể khiến message được giao lại ngay. Nếu lỗi là dữ liệu không hợp lệ vĩnh viễn, nack liên tục có thể tạo vòng lặp. Dùng retry policy, dead-letter topic hoặc ghi nhận trạng thái rejected theo nghiệp vụ.

### 6.6. Ack deadline và thời gian xử lý

Pub/Sub subscription có ack deadline. Streaming subscriber có thể gia hạn deadline trong khi xử lý, nhưng vẫn có giới hạn maximum extension period.

Nếu file cần xử lý lâu:

- Không tải file hàng GB và xử lý đồng bộ trong một handler mà không tính deadline.
- Tách bước nhận event và bước xử lý dài bằng queue nội bộ/job table.
- Chỉ ack sau khi đã lưu bền vững công việc tiếp theo vào database hoặc queue khác.
- Dùng spring.cloud.gcp.pubsub.subscriber.max-ack-extension-period khi cần điều chỉnh thời gian gia hạn.
- Cấu hình dead-letter topic và maximum delivery attempts để cô lập message thất bại kéo dài.

Khi ack sau khi ghi job vào database, job worker cần có idempotency riêng. Việc ack event không có nghĩa là xử lý file cuối cùng đã hoàn tất; nó có nghĩa công việc đã được tiếp nhận bền vững.

## 7. Đọc đúng object từ event

### 7.1. Dùng generation, không chỉ object name

Event có thể đến trễ. Ví dụ:

1. Object incoming/a.pdf được upload thành generation 100.
2. Event OBJECT_FINALIZE của generation 100 được publish.
3. Object bị upload lại thành generation 101.
4. Consumer mới nhận event generation 100.

Nếu consumer gọi storage.get(BlobId.of(bucket, objectName)), nó sẽ đọc live object 101, không phải bytes đã tạo event 100.

Hãy dùng generation từ notification:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob loadExactGeneration(
        Storage storage,
        String bucket,
        String objectName,
        long generation) {

    return storage.get(
            BlobId.of(bucket, objectName, generation));
}
~~~

Nếu object generation cũ không còn tồn tại do bucket không bật versioning hoặc lifecycle đã xóa, kết quả có thể là null. Hãy coi đó là trạng thái stale/missing và xử lý theo nghiệp vụ; không tự động thay bằng live generation mới.

### 7.2. Dùng metageneration cho metadata event

Với OBJECT_METADATA_UPDATE, generation có thể giữ nguyên trong khi metageneration tăng. Payload JSON_API_V1 có metadata field metageneration.

Khi cần thực hiện một update dựa trên metadata snapshot, dùng cả generation và metageneration làm precondition:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public Blob updateMetadataFromEvent(
        Storage storage,
        String bucket,
        String objectName,
        long generation,
        long metageneration,
        String newCacheControl) {

    Blob current = storage.get(
            BlobId.of(bucket, objectName, generation));

    if (current == null) {
        return null;
    }

    BlobInfo updated = current.toBuilder()
            .setCacheControl(newCacheControl)
            .build();

    return storage.update(
            updated,
            Storage.BlobTargetOption.generationMatch(generation),
            Storage.BlobTargetOption.metagenerationMatch(metageneration));
}
~~~

Nếu object hoặc metadata đã đổi kể từ event, Cloud Storage từ chối precondition thay vì ghi đè trạng thái mới. Xử lý conflict bằng cách đọc lại metadata và đánh giá lại nghiệp vụ.

### 7.3. Event DELETE và ARCHIVE

Với OBJECT_DELETE, payload mô tả object trước khi xóa và có timeDeleted. Consumer nên dùng payload để cập nhật index hoặc trạng thái nghiệp vụ. Không giả định object vẫn có thể đọc bằng Storage API.

Với OBJECT_ARCHIVE, live version đã trở thành noncurrent version. Nếu bucket bật Object Versioning, có thể đọc generation cũ nếu version đó còn được giữ. Nếu chỉ cần cập nhật trạng thái version, notification đã cung cấp object name và generation.

### 7.4. Xử lý event đến sai thứ tự

Không dựa vào thứ tự nhận message để suy ra trạng thái hiện tại. Ví dụ event metadata update metageneration 5 có thể đến trước event metageneration 4.

Quy tắc:

- So sánh generation trước; generation khác nhau là các phiên bản bytes khác nhau.
- Với cùng generation, so sánh metageneration để nhận biết metadata snapshot mới hơn.
- Không ghi trạng thái database lùi về generation/metageneration cũ.
- Nếu update object, dùng precondition tương ứng.
- Nếu cần dữ liệu live hiện tại, đọc metadata mới nhất từ Storage API và so sánh với event.
- Nếu event cũ không còn ý nghĩa nghiệp vụ, đánh dấu stale và ack sau khi ghi nhận kết quả.

Pub/Sub ordering key không tự sửa được thứ tự event gốc của Cloud Storage vì notifications không được đảm bảo publish theo thứ tự xảy ra. Generation và metageneration là cơ chế bảo vệ chính.

## 8. Idempotency và chống xử lý trùng

### 8.1. Không dùng Pub/Sub message ID làm khóa duy nhất của event

Cloud Storage và Pub/Sub giao message theo at-least-once. Cùng một Cloud Storage event có thể được gửi nhiều lần với Pub/Sub message ID khác nhau. Do đó, chỉ lưu Pub/Sub message ID không đủ để loại duplicate event.

Có thể xây dựng event fingerprint từ:

- bucketId
- objectId
- objectGeneration
- eventType
- metageneration khi event liên quan metadata
- notificationConfig nếu nghiệp vụ muốn phân biệt cùng event phát từ nhiều notification configurations

Ví dụ:

~~~java
public String eventKey(
        String bucket,
        String objectName,
        long generation,
        long metageneration,
        String eventType) {

    return bucket + "|" + objectName + "|" + generation
            + "|" + metageneration + "|" + eventType;
}
~~~

Đây là khóa idempotency minh họa. Nếu cùng object change được phát từ nhiều notification configurations nhưng chỉ muốn xử lý nghiệp vụ một lần, không đưa notificationConfig vào fingerprint.

### 8.2. Inbox table trong database

Có thể lưu trạng thái event bằng unique key:

~~~sql
CREATE TABLE gcs_event_inbox (
    event_key        VARCHAR(512) PRIMARY KEY,
    bucket_name      VARCHAR(255) NOT NULL,
    object_name      VARCHAR(1024) NOT NULL,
    generation       NUMERIC(20, 0) NOT NULL,
    metageneration   NUMERIC(20, 0),
    event_type       VARCHAR(64) NOT NULL,
    event_time       TIMESTAMP WITH TIME ZONE,
    status           VARCHAR(32) NOT NULL,
    processed_at     TIMESTAMP WITH TIME ZONE,
    error_message    VARCHAR(2000)
);
~~~

Luồng xử lý:

1. Tạo event key.
2. Insert inbox record với unique constraint.
3. Nếu record đã tồn tại ở trạng thái COMPLETED, ack message và bỏ qua side effect.
4. Nếu record mới, xử lý nghiệp vụ và cập nhật COMPLETED trong transaction phù hợp.
5. Ack sau khi trạng thái bền vững.
6. Nếu lỗi tạm thời, ghi trạng thái lỗi/retry và nack hoặc chuyển sang retry workflow.

Nếu side effect gọi một hệ thống ngoài database, dùng outbox hoặc idempotency key của downstream service. Không giả định một transaction database có thể rollback thao tác GCS hoặc HTTP call đã hoàn tất.

### 8.3. Thứ tự commit và ack

| Trình tự | Rủi ro |
| --- | --- |
| Ack trước, rồi mới ghi database | Process crash sau ack làm mất event khỏi luồng retry |
| Ghi database xong, rồi ack | Nếu crash trước ack, Pub/Sub giao lại; inbox dedupe ngăn side effect lặp |
| Ghi database và ack cùng transaction | Không có distributed transaction chung giữa Pub/Sub và database |

Mẫu an toàn thường là persist event/job và commit trước, sau đó ack. Nếu ack thất bại, message có thể được giao lại; unique key trong inbox khiến lần giao lại trở thành no-op.

## 9. Retry, dead-letter và xử lý lỗi

### 9.1. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Transient | Timeout Storage, 429, 5xx, database unavailable | Retry với backoff/jitter |
| Permission/configuration | 403 do thiếu storage.objects.get, topic IAM sai | Sửa IAM/config; tránh nack vô hạn |
| Stale event | Generation đã bị xóa hoặc không còn tồn tại | Ghi nhận stale, ack nếu nghiệp vụ cho phép |
| Invalid payload | Thiếu bucket/object/generation hoặc JSON sai | Đưa vào dead-letter/quarantine |
| Business rejection | File sai định dạng, tenant không hợp lệ | Ghi trạng thái rejected; ack sau khi lưu kết quả |
| Duplicate | Event fingerprint đã COMPLETED | Bỏ qua side effect và ack |

### 9.2. Dead-letter topic

Cấu hình dead-letter topic cho subscription để chuyển message không xử lý được sau số lần delivery tối đa. Runtime service account cần quyền phù hợp trên topic/subscription; service agent của Pub/Sub cũng cần quyền publish vào dead-letter topic theo cấu hình.

Không dùng dead-letter như nơi thay thế xử lý lỗi. Cần có quy trình:

- Quan sát số message chuyển dead-letter.
- Phân loại lỗi permission, payload, schema và business.
- Sửa nguyên nhân.
- Replay có kiểm soát sau khi xác nhận idempotency.
- Ghi lại ai replay, thời điểm và số lần.

### 9.3. Backoff và retry policy

Pub/Sub subscription có retry policy để redelivery theo exponential backoff. Nack thủ công có thể làm message được giao lại ngay; nếu muốn backoff, cấu hình retry policy và cân nhắc không nack liên tục khi hệ thống downstream đang lỗi.

Với AUTO, exception cần được truyền ngược về adapter để kích hoạt nack. Nếu error channel bắt exception rồi kết thúc bình thường, adapter có thể xem flow là thành công và ack. Với MANUAL, ứng dụng phải chủ động quyết định ack/nack trong cả happy path lẫn error path.

### 9.4. Exactly-once và thực tế của Spring adapter

Cloud Storage notifications là at-least-once và có thể đến sai thứ tự. Spring Framework on Google Cloud Pub/Sub integration không cung cấp AckReplyConsumerWithResponse, vốn cần để triển khai exactly-once feature của Pub/Sub Java client trong trường hợp tương ứng.

Vì vậy, hãy thiết kế consumer idempotent. Không dựa vào exactly-once delivery để bảo đảm một side effect chỉ xảy ra một lần. Inbox/outbox, generation token và unique constraints mới là phần bảo vệ ở tầng ứng dụng.

## 10. Luồng xử lý hoàn chỉnh: tạo thumbnail sau upload

### 10.1. Mô hình nghiệp vụ

Một hệ thống tài liệu có bucket training-documents, prefix incoming/ và processed/:

1. Client upload file vào incoming/.
2. GCS phát OBJECT_FINALIZE.
3. Pub/Sub chuyển event tới subscription.
4. Spring Integration nhận event và kiểm tra event key.
5. Processor đọc đúng object generation.
6. Kiểm tra file type, size và malware.
7. Tạo thumbnail/metadata.
8. Ghi kết quả vào database và upload output.
9. Ack event sau khi công việc được tiếp nhận bền vững.

~~~mermaid
flowchart TD
    A["Upload incoming/file.pdf"] --> B["OBJECT_FINALIZE"]
    B --> C["Pub/Sub topic"]
    C --> D["Subscription"]
    D --> E["PubSubInboundChannelAdapter"]
    E --> F["Validate attributes + JSON payload"]
    F --> G["Insert idempotency key"]
    G --> H{"Event đã hoàn tất?"}
    H -->|Có| ACK["ACK"]
    H -->|Không| I["Read exact generation"]
    I --> J["Scan / validate file"]
    J --> K["Generate thumbnail"]
    K --> L["Persist result / outbox"]
    L --> M["Mark completed"]
    M --> ACK
~~~

### 10.2. Processor đọc generation cụ thể

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class GcsObjectEventProcessor {

    private final Storage storage;
    private final DocumentJobService jobs;

    public GcsObjectEventProcessor(
            Storage storage,
            DocumentJobService jobs) {
        this.storage = storage;
        this.jobs = jobs;
    }

    public void process(
            String eventType,
            String bucket,
            String objectName,
            long generation,
            String eventTime,
            com.fasterxml.jackson.databind.JsonNode metadata) {

        if (!"OBJECT_FINALIZE".equals(eventType)) {
            return;
        }

        String eventKey = bucket + "|" + objectName + "|"
                + generation + "|" + eventType;

        if (!jobs.tryStart(eventKey)) {
            return;
        }

        Blob object = storage.get(
                BlobId.of(bucket, objectName, generation));

        if (object == null) {
            jobs.markStale(eventKey);
            return;
        }

        jobs.processExactGeneration(
                eventKey,
                object,
                eventTime,
                metadata);
    }
}
~~~

DocumentJobService minh họa một service lưu inbox/job state. tryStart cần được bảo vệ bằng unique constraint/transaction để hai delivery song song không khởi chạy cùng side effect.

### 10.3. Tránh event loop

Nếu processor upload thumbnail vào cùng bucket và notification theo dõi toàn bucket, upload thumbnail lại tạo OBJECT_FINALIZE, kích hoạt processor lần nữa.

Cách xử lý:

- Chỉ subscribe prefix incoming/.
- Ghi output vào prefix processed/ không nằm trong notification filter.
- Hoặc filter event trong handler dựa trên object name.
- Dùng metadata marker để phân biệt output do processor tạo nếu phù hợp.

Prefix filtering ở notification configuration giảm số message không cần thiết; filter trong code là lớp bảo vệ bổ sung.

## 11. Kiểm thử tích hợp

### 11.1. Unit test

Kiểm tra các nhánh logic:

- OBJECT_FINALIZE kích hoạt xử lý file.
- OBJECT_METADATA_UPDATE không chạy lại thumbnail nếu không cần.
- OBJECT_DELETE cập nhật trạng thái và không gọi download.
- Event duplicate không chạy side effect lần hai.
- Event generation cũ không thay thế trạng thái generation mới.
- Metadata update dùng generation/metageneration đúng.
- Invalid payload được quarantine/dead-letter.
- Processor lỗi thì không ack.
- Upload output không tạo event loop.

Mock Storage, ObjectMapper, DocumentJobService và acknowledgment object. Unit test không chứng minh notification GCS thực sự được publish.

### 11.2. Integration test với Pub/Sub emulator

Pub/Sub emulator có thể kiểm tra subscriber, payload conversion và ack/nack. Có thể publish synthetic Cloud Storage notification message vào emulator topic rồi xác minh Spring Integration flow.

Emulator không thay thế Cloud Storage notification service thực tế; việc upload object vào một GCS emulator không mặc nhiên tạo notification thật tới Pub/Sub emulator. Hãy tách test adapter/message consumer khỏi test cấu hình GCS notification trên cloud project.

### 11.3. Integration test trên project GCP riêng

1. Tạo bucket, topic và subscription dành riêng cho test.
2. Bật Pub/Sub API và cấp roles/pubsub.publisher cho Cloud Storage service agent.
3. Tạo notification configuration chỉ theo prefix test-incoming/.
4. Chạy Spring Boot consumer bằng service account có roles/pubsub.subscriber.
5. Upload object test và chờ OBJECT_FINALIZE.
6. Xác minh payload attributes, generation và JSON metadata.
7. Upload lại cùng object name; xác minh generation mới và event archive/delete tương ứng.
8. Cập nhật metadata; xác minh OBJECT_METADATA_UPDATE.
9. Xóa object; xác minh event delete/archive theo versioning policy.
10. Gửi cùng event hai lần; xác minh idempotency.
11. Tạo event sai thứ tự; xác minh generation guard.
12. Thu hồi tạm thời quyền đọc object; xác minh retry/dead-letter.
13. Xóa notification configuration, subscription, topic và object test sau khi kiểm tra.

Notification có thể trễ và không có SLA delivery time. Test nên đợi theo deadline hợp lý và kiểm tra trạng thái cuối, không phụ thuộc message đến trong một số mili giây cố định.

### 11.4. Test failure và recovery

| Tình huống | Kỳ vọng |
| --- | --- |
| Pub/Sub giao duplicate | Chỉ một business side effect |
| Consumer crash sau DB commit, trước ack | Event được giao lại nhưng inbox dedupe |
| Object bị replace trước khi consumer đọc | Consumer đọc generation từ event hoặc đánh dấu stale |
| Event metadata cũ đến sau event mới | Không ghi lùi metageneration |
| Service agent mất Publisher role | Notification delivery lỗi; alert cấu hình/IAM |
| Consumer mất Subscriber role | Subscription health/error thể hiện lỗi permission |
| Downstream service timeout | Retry có backoff hoặc chuyển dead-letter |
| File invalid | Ghi rejected/quarantine, không retry vô hạn |
| Notification config bị xóa | Dừng nhận event; cần kiểm tra provisioning drift |

## 12. Quan sát và vận hành

### 12.1. Metrics

Theo dõi tối thiểu:

- Số Pub/Sub messages nhận theo event type.
- Số ack, nack, redelivery và dead-letter.
- Thời gian từ eventTime tới thời điểm consumer bắt đầu xử lý.
- Thời gian xử lý object và số byte đọc.
- Tỷ lệ duplicate theo event fingerprint.
- Tỷ lệ stale generation.
- Số lỗi Storage 403/404/429/5xx.
- Số message đang outstanding và ack deadline extension.
- Số event xử lý thành công/thất bại theo bucket/prefix.

### 12.2. Logging và tracing

Log event type, bucket, object name đã được bảo vệ theo chính sách, generation, metageneration, eventTime, Pub/Sub message ID và event fingerprint. Không log nội dung file, signed URL, secret hoặc metadata nhạy cảm.

Dùng trace/correlation ID từ request upload hoặc document ID nội bộ để liên kết upload, notification, xử lý file và cập nhật database.

### 12.3. Health check

PubSubInboundChannelAdapter có thể tích hợp Pub/Sub subscriber health indicator. Nếu cần theo dõi trạng thái subscriber trong Spring Boot Actuator, cấu hình health tracker registry cho adapter theo tài liệu phiên bản đang dùng.

Health check nên phân biệt:

- Ứng dụng đã khởi động.
- Subscriber kết nối được.
- Subscription có message backlog.
- Processor còn khả năng đọc object.
- Downstream dependencies còn hoạt động.

Một subscriber healthy không có nghĩa business processing đang theo kịp backlog.

## 13. IAM và bảo mật

| Principal | Quyền | Phạm vi |
| --- | --- | --- |
| Cloud Storage service agent | roles/pubsub.publisher | Topic nhận notification |
| Spring Boot event consumer | roles/pubsub.subscriber | Subscription cụ thể |
| Spring Boot object processor | storage.objects.get | Bucket/prefix cần đọc |
| Spring Boot polling source | storage.objects.list, storage.objects.get | Bucket/prefix cần đồng bộ |
| Spring Boot outbound writer | storage.objects.create và quyền cần thiết khi overwrite | Bucket output |
| Provisioning identity | Cập nhật bucket notification, topic, subscription | Tài nguyên được quản trị |

Các nguyên tắc:

- Dùng workload identity/ADC thay vì lưu service account JSON key trong container.
- Tách principal cấu hình notification khỏi principal runtime.
- Chỉ cấp Publisher cho service agent trên topic đích.
- Chỉ cấp Subscriber cho app trên subscription cần đọc.
- Giới hạn Storage object permissions ở bucket cần dùng.
- Không để event payload tự quyết định bucket tùy ý; allowlist bucket/prefix được ứng dụng chấp nhận.
- Kiểm tra event attributes và payload trước khi gọi Storage API.
- Không tin objectId như đường dẫn file local; sanitize khi ghi xuống filesystem.
- Không cho event tự kích hoạt URL tùy ý hoặc command tùy ý.

## 14. Giới hạn, quota và chi phí

- Bucket có tối đa 100 notification configurations và tối đa 10 configurations cho mỗi event type.
- Tạo/xóa notification configuration làm tăng bucket metageneration.
- Notifications có độ trễ, không có SLA thời gian giao và có thể bị trễ đáng kể.
- GCS notification và Pub/Sub đều at-least-once; consumer phải dedupe.
- Polling tạo request list/metadata định kỳ; bucket lớn hoặc poller quá ngắn làm tăng tải và chi phí.
- Pub/Sub có chi phí publish/delivery/storage theo cấu hình và mức sử dụng.
- GCS event có thể kích hoạt nhiều downstream service; fan-out nhiều subscription sẽ tăng lượng message được xử lý.
- GCS notifications chỉ báo object events được hỗ trợ. Bucket operations, object reads và các hoạt động khác cần Cloud Audit Logs hoặc cơ chế khác.
- GCS notifications không đảm bảo thứ tự event; không dùng timestamp nhận message làm thứ tự dữ liệu.

Đối với bucket có nhiều triệu object, ưu tiên prefix filter và event-driven processing thay vì quét toàn bucket mỗi vài giây. Nếu dùng polling, thiết kế partition prefix, fetch limit và filter state.

## 15. So sánh Pub/Sub notifications, Eventarc và Cloud Audit Logs

| Cơ chế | Payload | Dùng khi | Lưu ý |
| --- | --- | --- | --- |
| GCS Pub/Sub notifications | Pub/Sub attributes + JSON_API_V1 object metadata | Muốn topic/subscription, nhiều consumer, tự kiểm soát ack/retry | At-least-once, không bảo đảm thứ tự |
| Eventarc Cloud Storage trigger | CloudEvents | Muốn định tuyến event tới Cloud Run/function hoặc service đích | Event envelope khác Pub/Sub notification payload |
| Cloud Audit Logs routed to Pub/Sub | Audit log entry | Theo dõi bucket operations, object reads hoặc hành động không có GCS notification event | Phải cấu hình audit log và log sink/filter |

Không parse CloudEvents như JSON_API_V1 notification. Nếu chọn Eventarc, handler cần đọc CloudEvent envelope và data schema tương ứng. Nếu chọn Pub/Sub notification, consumer đọc message attributes và payload metadata như các phần trước.

## 16. So sánh với AWS S3 và Azure Blob Storage

| Khía cạnh | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Object change event | Pub/Sub notifications | S3 Event Notifications | Event Grid events |
| Message transport | Pub/Sub topic/subscription | SNS, SQS, Lambda hoặc EventBridge | Event Grid, Queue Storage hoặc Service Bus |
| Spring consumer | PubSubInboundChannelAdapter | Spring Cloud AWS SQS listener/adapter | Azure Spring integration hoặc Service Bus/Event Grid integration |
| Payload identity | bucket, object, generation, event type | bucket, key, version ID, event name | account/container/blob, ETag/version ID, event type |
| Delivery | At-least-once, không đảm bảo thứ tự | At-least-once với nhiều notification destinations | At-least-once và retry theo Event Grid |
| Duplicate handling | Event fingerprint + inbox | Event key/version ID + inbox | Event ID + inbox |
| Object version guard | Generation/metageneration | Version ID/ETag | Version ID/ETag |

Các provider đều tách object storage khỏi event transport. Tuy nhiên, event envelope, identity token và retry semantics khác nhau. Trong adapter đa cloud, chuẩn hóa event nội bộ như ObjectCreated, ObjectDeleted, ObjectMetadataChanged, ObjectVersionArchived; giữ nguyên provider event ID, version token và payload gốc để truy vết.

## 17. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây ứng dụng Spring Boot document-api nhận file upload vào prefix incoming/, kiểm tra file, tạo thumbnail và cập nhật database. Khi người dùng thay metadata hoặc xóa file, hệ thống cần đồng bộ lại trạng thái.

### Nhiệm vụ A — GCS polling adapter

1. Thêm spring-cloud-gcp-storage và spring-integration-file.
2. Tạo Storage bean bằng ADC/workload identity.
3. Cấu hình GcsInboundFileSynchronizingMessageSource để poll prefix test.
4. Cấu hình GcsStreamingMessageSource và xử lý InputStream.
5. Dùng filter để tránh đọc lại file không cần thiết.
6. Tạo GcsMessageHandler để ghi file vào prefix output.

### Nhiệm vụ B — Pub/Sub notification

1. Bật Pub/Sub API và tạo topic/subscription.
2. Cấp roles/pubsub.publisher cho Cloud Storage service agent.
3. Tạo notification configuration cho OBJECT_FINALIZE, OBJECT_METADATA_UPDATE, OBJECT_DELETE.
4. Giới hạn prefix incoming/.
5. Cấu hình PubSubInboundChannelAdapter và MessageChannel.
6. Parse event attributes và JSON metadata payload.

### Nhiệm vụ C — Xử lý an toàn

1. Đọc object bằng generation từ event.
2. Dùng generation/metageneration precondition khi cập nhật object.
3. Tạo inbox table với unique event key.
4. Ack sau khi commit event/job vào database.
5. Nack lỗi transient và cấu hình dead-letter topic.
6. Xử lý duplicate và event đến sai thứ tự.
7. Ngăn event loop khi processor ghi output.

### Nhiệm vụ D — Kiểm thử và quan sát

- Test duplicate event và ack failure.
- Test object bị overwrite trước khi event được xử lý.
- Test metadata update và delete.
- Test missing IAM permissions.
- Test Pub/Sub emulator với synthetic notification.
- Test GCS notification thật trên project riêng.
- Theo dõi backlog, processing latency, dead-letter và stale generations.
- So sánh với S3 Event Notifications và Azure Event Grid.

**Tiêu chí đạt:** Ứng dụng phân biệt polling và event-driven flow; cấu hình đúng GCS notification và Pub/Sub IAM; nhận event qua Spring Integration; đọc đúng object generation; xử lý duplicate/out-of-order; ack/nack đúng thời điểm; và có integration test chứng minh event flow thực tế.

## 18. Ghi nhớ

- GCS channel adapters đọc/ghi file qua Spring MessageChannel; inbound adapters là polling, không phải event stream.
- GcsInboundFileSynchronizingMessageSource tải file về local directory; GcsStreamingMessageSource phát InputStream; GcsMessageHandler ghi file lên GCS.
- Object change notifications đi theo luồng Cloud Storage → Pub/Sub topic → subscription → PubSubInboundChannelAdapter → Spring Integration flow.
- Cloud Storage service agent cần roles/pubsub.publisher trên topic; Spring Boot consumer cần roles/pubsub.subscriber trên subscription và storage.objects.get nếu đọc file.
- OBJECT_FINALIZE, OBJECT_METADATA_UPDATE, OBJECT_DELETE, OBJECT_ARCHIVE có semantics khác nhau; thay thế object có thể phát hai event.
- Pub/Sub message chứa attributes và payload metadata; JSON_API_V1 mô tả metadata sau thay đổi, riêng delete payload mô tả trạng thái trước xóa và có timeDeleted.
- Notifications at-least-once, có thể duplicate, trễ và không theo thứ tự; không dựa vào Pub/Sub message ID hoặc thời điểm nhận để dedupe/order.
- Dùng bucket/object/generation/eventType và metageneration khi cần để tạo idempotency key và đọc đúng object version.
- Ack sau khi side effect hoặc job đã được persist bền vững; xử lý duplicate bằng inbox/unique constraint.
- Dùng retry policy, dead-letter topic, metrics và Cloud Audit Logs để vận hành ổn định.

### Tài liệu tham khảo

- [Pub/Sub notifications for Cloud Storage](https://docs.cloud.google.com/storage/docs/pubsub-notifications)
- [Configure Pub/Sub notifications for Cloud Storage](https://docs.cloud.google.com/storage/docs/reporting-changes)
- [gcloud storage buckets notifications create](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/create)
- [Spring Integration — Spring Framework on Google Cloud](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html)
- [Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring)
- [Spring Cloud GCP PubSubInboundChannelAdapter API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/pubsub/integration/inbound/PubSubInboundChannelAdapter.html)
- [GcsInboundFileSynchronizingMessageSource API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/integration/inbound/GcsInboundFileSynchronizingMessageSource.html)
- [GcsStreamingMessageSource API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/integration/inbound/GcsStreamingMessageSource.html)
- [GcsMessageHandler API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/integration/outbound/GcsMessageHandler.html)
- [Cloud Storage data consistency](https://docs.cloud.google.com/storage/docs/consistency)
- [Pub/Sub subscription retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Eventarc Cloud Storage events](https://docs.cloud.google.com/eventarc/docs/cloudevents)
