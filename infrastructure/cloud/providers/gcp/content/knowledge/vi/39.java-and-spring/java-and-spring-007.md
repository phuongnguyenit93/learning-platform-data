# Đồng bộ, bất đồng bộ và streaming với Google Cloud Java clients

Ứng dụng Java trên Google Cloud thường gọi nhiều loại API: đọc một object, tạo một bản ghi, gửi message, truy vấn dữ liệu hoặc nhận luồng sự kiện liên tục. Các Java client libraries cung cấp nhiều cách thực hiện những thao tác này. Lựa chọn giữa gọi đồng bộ, bất đồng bộ và streaming ảnh hưởng trực tiếp đến số thread cần dùng, độ trễ, khả năng xử lý tải lớn, cách quản lý lỗi và vòng đời ứng dụng.

Gọi đồng bộ phù hợp khi cần một kết quả ngay trong luồng xử lý hiện tại và thời gian chờ có thể dự đoán. Gọi bất đồng bộ phù hợp khi muốn tiếp tục công việc khác trong lúc chờ API hoàn thành. Streaming phù hợp khi dữ liệu được truyền theo nhiều phần hoặc sự kiện đến liên tục. Ba cách này là những mô hình thực thi khác nhau; không nên chọn chỉ theo cảm giác rằng một cách luôn nhanh hơn cách còn lại.

Trong phạm vi Google Cloud, cần phân biệt client cấp cao của từng dịch vụ, chẳng hạn Publisher của Pub/Sub hoặc Storage, với các client sinh từ Google API Client Libraries (GAPIC) dựa trên GAX. Mỗi thư viện có API và khả năng đồng bộ, bất đồng bộ, streaming khác nhau. Hãy kiểm tra tài liệu của đúng dịch vụ và phiên bản thư viện trước khi thiết kế.

## 1. Ba mô hình gọi API

| Mô hình | Cách hoạt động | Khi nên dùng |
| --- | --- | --- |
| Synchronous | Gọi hàm và chờ kết quả hoặc exception trước khi tiếp tục | Thao tác đơn giản, cần kết quả ngay, lưu lượng và thời gian chờ có kiểm soát |
| Asynchronous | Gửi yêu cầu, nhận future hoặc callback và tiếp tục xử lý công việc khác | Nhiều yêu cầu độc lập, tác vụ I/O có thời gian chờ dài, gửi message hoặc xử lý nền |
| Streaming | Trao đổi nhiều phần dữ liệu trong một luồng thay vì một request/response đơn lẻ | Tập dữ liệu lớn, kết quả trả dần, sự kiện liên tục hoặc giao tiếp hai chiều |

Một API đồng bộ có thể vẫn được gọi từ thread pool để tránh chặn thread xử lý request. Tuy nhiên, việc đưa lời gọi blocking vào một executor chỉ chuyển nơi bị chặn; nó không biến API đó thành non-blocking. Tương tự, nhận một ApiFuture không có nghĩa dữ liệu đang được streaming.

## 2. Đồng bộ với Google Cloud Java clients

Với lời gọi đồng bộ, chương trình gọi phương thức và chờ kết quả. Ví dụ, client Cloud Storage có thể đọc metadata của object:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class ReadObjectMetadata {
  public static void main(String[] args) {
    Storage storage = StorageOptions.getDefaultInstance().getService();

    Blob blob = storage.get(BlobId.of("orders-data", "exports/orders.csv"));
    if (blob == null) {
      throw new IllegalStateException("Object không tồn tại");
    }

    System.out.println("Generation: " + blob.getGeneration());
    System.out.println("Size: " + blob.getSize());
  }
}
~~~

Phương thức get trả về khi đã nhận kết quả hoặc phát sinh lỗi. Cách gọi này dễ đọc, dễ kiểm tra và phù hợp với tác vụ cần metadata ngay. Trong một request HTTP, thời gian gọi Cloud Storage sẽ chiếm thời gian của thread xử lý request.

Lời gọi đồng bộ phù hợp khi:

- Luồng nghiệp vụ cần kết quả để quyết định bước tiếp theo.
- Số lời gọi đồng thời được giới hạn hợp lý.
- Thời gian chờ và timeout được cấu hình rõ ràng.
- Mã nguồn ưu tiên tính tuần tự, dễ đọc hơn việc điều phối nhiều tác vụ.

Không nên dùng lời gọi blocking dài trên event loop của Spring WebFlux hoặc thread phục vụ nhiều kết nối. Nếu thư viện chỉ cung cấp API đồng bộ, có thể chạy nó trên executor riêng có giới hạn thread và hàng đợi. Cần giới hạn concurrency để tránh việc hàng đợi tăng vô hạn khi dịch vụ Google Cloud chậm.

## 3. Bất đồng bộ với ApiFuture và callback

Nhiều Google Cloud Java clients dùng ApiFuture để biểu diễn kết quả sẽ có trong tương lai. Mã gọi có thể đăng ký callback để nhận kết quả hoặc lỗi khi thao tác hoàn tất, thay vì chặn thread bằng get().

Pub/Sub Publisher là một ví dụ phổ biến. Publisher nhận message để gửi và trả về ApiFuture chứa message ID khi việc publish hoàn thành:

~~~java
import com.google.api.core.ApiFuture;
import com.google.api.core.ApiFutureCallback;
import com.google.api.core.ApiFutures;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.common.util.concurrent.MoreExecutors;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

public class PublishAsync {
  public static void main(String[] args) throws IOException, InterruptedException {
    TopicName topic = TopicName.of("my-project", "orders");
    Publisher publisher = Publisher.newBuilder(topic).build();

    try {
      PubsubMessage message = PubsubMessage.newBuilder()
          .setData(ByteString.copyFromUtf8("{\"orderId\":\"A-1024\"}"))
          .putAttributes("source", "orders-api")
          .build();

      ApiFuture<String> messageId = publisher.publish(message);

      ApiFutures.addCallback(
          messageId,
          new ApiFutureCallback<String>() {
            @Override
            public void onSuccess(String id) {
              System.out.println("Published message: " + id);
            }

            @Override
            public void onFailure(Throwable error) {
              System.err.println("Publish failed: " + error.getMessage());
            }
          },
          MoreExecutors.directExecutor());
    } finally {
      publisher.shutdown();
      if (!publisher.awaitTermination(1, TimeUnit.MINUTES)) {
        System.err.println("Publisher chưa kết thúc trong thời hạn chờ");
      }
    }
  }
}
~~~

Đoạn mã minh họa việc đăng ký callback và đóng Publisher khi ứng dụng mẫu kết thúc. Trong ứng dụng server chạy lâu dài, Publisher nên là thành phần dùng chung được quản lý theo vòng đời ứng dụng; không tạo rồi shutdown Publisher cho từng HTTP request. Callback dùng direct executor phải ngắn và không thực hiện I/O blocking, vì callback có thể chạy ngay trên thread hoàn tất future. Nếu cần xử lý nặng, chuyển công việc sang executor riêng có giới hạn.

Có thể gọi get() trên ApiFuture, nhưng thao tác đó lại chặn thread cho đến khi có kết quả. Nếu mục tiêu là bất đồng bộ, hãy dùng callback hoặc compose future thay vì gọi get() ngay sau khi publish.

### Dùng callable của GAX

Các GAPIC clients thường cung cấp phương thức tiện ích đồng bộ và các callable cho những kiểu RPC tương ứng. Với unary callable, call() thực hiện đồng bộ; futureCall() trả về ApiFuture:

~~~java
ApiFuture<Response> future =
    client.someUnaryCallable().futureCall(request);

ApiFutures.addCallback(
    future,
    new ApiFutureCallback<Response>() {
      @Override
      public void onSuccess(Response response) {
        handleResponse(response);
      }

      @Override
      public void onFailure(Throwable error) {
        handleFailure(error);
      }
    },
    callbackExecutor);
~~~

Đây là mẫu tổng quát của GAX; thay Request, Response và tên callable bằng kiểu cùng phương thức được cung cấp bởi client cụ thể. Không phải mọi phương thức của mọi dịch vụ đều có cùng tập callable hoặc hỗ trợ bất đồng bộ.

## 4. Streaming là gì?

Streaming truyền dữ liệu thành nhiều phần trong một phiên trao đổi. Thay vì đợi toàn bộ kết quả rồi mới xử lý, ứng dụng có thể xử lý từng phần khi nhận được. Điều này giảm nhu cầu giữ toàn bộ dữ liệu trong bộ nhớ và phù hợp với luồng dữ liệu lớn hoặc liên tục.

Có bốn kiểu giao tiếp streaming thường gặp trong API RPC:

| Kiểu | Hướng dữ liệu | Ví dụ sử dụng |
| --- | --- | --- |
| Unary | Một request, một response | Đọc metadata hoặc tạo tài nguyên |
| Server streaming | Một request, nhiều response | Đọc tập dữ liệu theo từng block |
| Client streaming | Nhiều request, một response | Gửi nhiều phần dữ liệu rồi nhận kết quả tổng hợp |
| Bidirectional streaming | Nhiều request và nhiều response trong cùng phiên | Gửi sự kiện và nhận kết quả tương ứng liên tục |

Tên kiểu streaming mô tả giao thức trao đổi. Một phương thức server streaming có thể được tiêu thụ đồng bộ qua iterator, dù server gửi nhiều response. Một API bất đồng bộ có thể trả future nhưng vẫn chỉ có một response. Vì vậy, hãy đánh giá riêng hai câu hỏi: lời gọi có chặn thread không, và API trao đổi bao nhiêu message trong một phiên?

Không phải dịch vụ Google Cloud nào cũng hỗ trợ đủ bốn kiểu. Cloud Storage có các channel đọc/ghi theo phần dữ liệu; Pub/Sub có Publisher và Subscriber xử lý message liên tục; BigQuery Storage Read API cung cấp kết quả dạng server stream; các GAPIC clients có thể cung cấp callable streaming nếu API của dịch vụ định nghĩa RPC tương ứng.

## 5. Đọc object lớn bằng ReadChannel của Cloud Storage

Khi đọc một object lớn, không nhất thiết phải tải toàn bộ nội dung vào byte array. Storage ReadChannel cho phép đọc từng phần qua ByteBuffer:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.Storage;

import java.io.IOException;
import java.nio.ByteBuffer;

public class StreamObject {
  public static void copyToProcessor(Storage storage, String bucket, String objectName)
      throws IOException {
    try (ReadChannel channel = storage.reader(BlobId.of(bucket, objectName))) {
      ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);
      int bytesRead;

      while ((bytesRead = channel.read(buffer)) != -1) {
        buffer.flip();
        if (buffer.hasRemaining()) {
          processChunk(buffer);
        }
        buffer.clear();
      }
    }
  }

  private static void processChunk(ByteBuffer chunk) {
    // Xử lý dữ liệu hiện có trong buffer trước khi đọc phần tiếp theo.
  }
}
~~~

Buffer 64 KiB là giá trị minh họa, không phải kích thước tối ưu cho mọi workload. Kích thước cần cân bằng giữa số lần đọc, bộ nhớ mỗi request và độ trễ xử lý. Hàm processChunk phải tiêu thụ dữ liệu trước khi buffer được clear để tái sử dụng.

Với upload, WriteChannel cho phép ghi từng phần vào object. Cần đóng channel đúng cách để hoàn tất thao tác ghi và giải phóng tài nguyên. Với file lớn, hãy cân nhắc retry, resumable upload, checksum và xử lý trường hợp ứng dụng dừng giữa chừng.

## 6. Server streaming với BigQuery Storage Read API

BigQuery Storage Read API trả dữ liệu theo các response block. Một read session có thể cung cấp nhiều read stream; mỗi stream được đọc độc lập. Ví dụ dưới đây minh họa cách đọc một stream:

~~~java
import com.google.api.gax.rpc.ServerStream;
import com.google.cloud.bigquery.storage.v1.BigQueryReadClient;
import com.google.cloud.bigquery.storage.v1.ReadRowsRequest;
import com.google.cloud.bigquery.storage.v1.ReadRowsResponse;

public class ReadBigQueryStream {
  public static void read(String readStreamName) throws Exception {
    try (BigQueryReadClient client = BigQueryReadClient.create()) {
      ReadRowsRequest request = ReadRowsRequest.newBuilder()
          .setReadStream(readStreamName)
          .build();

      ServerStream<ReadRowsResponse> responses =
          client.readRowsCallable().call(request);

      for (ReadRowsResponse response : responses) {
        processResponseBlock(response);
      }
    }
  }

  private static void processResponseBlock(ReadRowsResponse response) {
    // Giải mã Arrow hoặc Avro theo định dạng được chọn trong read session.
  }
}
~~~

readStreamName phải lấy từ ReadSession được tạo trước đó bằng BigQuery Storage Read API. Định dạng dữ liệu trong response phụ thuộc định dạng được chọn khi tạo session, thường là Avro hoặc Arrow; ứng dụng phải giải mã theo đúng định dạng đó. Mỗi response là một block dữ liệu, không nhất thiết là một hàng đơn lẻ.

ServerStream cho phép duyệt tuần tự các response. Nếu xử lý mỗi block mất nhiều thời gian, cần cân nhắc cách điều phối song song mà vẫn giới hạn số block đang giữ trong bộ nhớ. Không gom toàn bộ response thành một List lớn nếu mục tiêu là xử lý tập dữ liệu lớn.

## 7. Client streaming và bidirectional streaming

Một số API gRPC cho phép client gửi nhiều request trong cùng một phiên. Client streaming phù hợp khi client cần gửi nhiều phần dữ liệu rồi nhận một kết quả cuối cùng. Bidirectional streaming cho phép cả client và server gửi message độc lập trong cùng phiên; hai phía có thể tiến triển đồng thời.

GAX biểu diễn các kiểu callable này bằng các abstraction như ClientStreamingCallable và BidiStreamingCallable. Với bidirectional streaming, callable có thể tạo một BidiStream để gửi request và đọc response. Tên callable, kiểu message và cách kết thúc stream phụ thuộc API cụ thể.

Mẫu khái niệm:

~~~java
BidiStream<Request, Response> stream = streamingCallable.call();

try {
  stream.send(firstRequest);
  stream.send(secondRequest);
} finally {
  stream.closeSend();
}

for (Response response : stream) {
  handle(response);
}
~~~

Đây là minh họa cho một phiên gửi hữu hạn, không phải đoạn mã có thể thay thế trực tiếp cho một client cụ thể. Hãy kiểm tra API của dịch vụ để biết cách đóng nửa gửi, cách nhận lỗi cuối stream, giới hạn kích thước message và yêu cầu flow control. Với bidirectional stream kéo dài, phía gửi và phía nhận thường cần chạy đồng thời; chỉ đóng luồng gửi khi giao thức hoặc nghiệp vụ cho phép. Với client streaming, ứng dụng thường gửi nhiều request rồi đóng luồng gửi để server hoàn tất response tổng hợp.

Khi stream bị lỗi giữa chừng, cần xác định có thể tiếp tục từ checkpoint hay phải tạo phiên mới. Không giả định rằng gửi lại toàn bộ request sẽ an toàn: thao tác có thể đã được server xử lý trước khi kết nối đứt. Dùng request ID, sequence number hoặc cơ chế idempotency của dịch vụ nếu cần tránh xử lý trùng.

## 8. Pub/Sub: bất đồng bộ khi publish và xử lý message liên tục

Pub/Sub thể hiện rõ sự khác nhau giữa publish bất đồng bộ và nhận message liên tục. Publisher có thể gom batch và gửi message nền; Subscriber nhận message qua callback khi có dữ liệu.

Ví dụ receiver xử lý message:

~~~java
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.cloud.pubsub.v1.AckReplyConsumer;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import com.google.cloud.pubsub.v1.MessageReceiver;

public class SubscribeOrders {
  public static void start() {
    ProjectSubscriptionName subscription =
        ProjectSubscriptionName.of("my-project", "orders-worker-sub");

    MessageReceiver receiver = (PubsubMessage message, AckReplyConsumer consumer) -> {
      try {
        processOrder(message.getData().toStringUtf8());
        consumer.ack();
      } catch (Exception error) {
        consumer.nack();
      }
    };

    Subscriber subscriber = Subscriber.newBuilder(subscription, receiver).build();
    subscriber.startAsync().awaitRunning();
  }

  private static void processOrder(String payload) {
    // Xác thực và xử lý nghiệp vụ; nên có tính idempotent.
  }
}
~~~

Ví dụ tập trung vào callback; ứng dụng production cần giữ tham chiếu Subscriber và dừng nó trong lifecycle hook khi shutdown. Cần import AckReplyConsumer từ package Pub/Sub client tương ứng. Không khởi động một Subscriber mới cho mỗi request HTTP.

Khi xử lý thành công, gọi ack để xác nhận message. Khi xử lý thất bại và muốn Pub/Sub phân phối lại theo chính sách subscription, gọi nack. Message có thể được giao lại, vì vậy handler nên idempotent hoặc lưu trạng thái xử lý theo message ID/business key. Không ack trước khi nghiệp vụ quan trọng đã được lưu bền vững nếu việc mất message là không chấp nhận được.

Subscriber có thể nhận nhiều message đồng thời. Dùng FlowControlSettings để giới hạn số lượng message và tổng byte chưa được xử lý. Giới hạn này tạo backpressure ở phía consumer: khi ứng dụng bận, client giảm lượng message đang giữ thay vì tăng bộ nhớ không giới hạn. Giá trị cần chọn theo kích thước message, thời gian xử lý và năng lực database phía sau.

## 9. Backpressure và giới hạn tài nguyên

Streaming và bất đồng bộ không tự động giải quyết vấn đề quá tải. Nếu producer gửi dữ liệu nhanh hơn consumer xử lý, hàng đợi và bộ nhớ có thể tăng liên tục. Backpressure là cơ chế điều chỉnh tốc độ hoặc lượng dữ liệu đang chờ để hệ thống không nhận nhiều công việc hơn khả năng xử lý.

Các cách kiểm soát thường dùng:

- Đặt giới hạn số request đang bay (in-flight) và số message chưa được xác nhận.
- Giới hạn kích thước buffer, batch và queue.
- Dùng executor có số thread và queue capacity hữu hạn.
- Tạm dừng đọc hoặc giảm demand khi consumer chậm, nếu API hỗ trợ.
- Chia stream thành partition hoặc nhiều stream độc lập khi dịch vụ hỗ trợ.
- Theo dõi latency xử lý, queue depth, outstanding bytes và tỷ lệ lỗi.

Với Pub/Sub, flow control giới hạn outstanding message và byte. Với Storage ReadChannel, ứng dụng kiểm soát tốc độ đọc bằng vòng lặp xử lý từng buffer. Với server streaming, xử lý tuần tự từng response giúp giữ bộ nhớ ổn định; nếu xử lý song song, cần dùng hàng đợi giới hạn và quy định rõ thứ tự khi nghiệp vụ yêu cầu.

Không nên tạo một thread mới cho mỗi message hoặc mỗi callback. Thread pool không giới hạn có thể làm cạn bộ nhớ và tăng context switching khi tải tăng. Hãy chọn concurrency theo số CPU, thời gian I/O, quota của dịch vụ và khả năng downstream.

## 10. Timeout, deadline, retry và cancellation

Mọi lời gọi từ ứng dụng đến Google Cloud đều cần có giới hạn thời gian. Timeout ở tầng HTTP của ứng dụng không nhất thiết thay thế deadline của RPC. Nếu client tiếp tục chờ sau khi request của người dùng đã hết hạn, công việc có thể chiếm tài nguyên dù không còn ai cần kết quả.

| Cơ chế | Mục đích | Lưu ý |
| --- | --- | --- |
| Timeout | Giới hạn thời gian chờ của một thao tác hoặc lớp kết nối | Phân biệt timeout kết nối, timeout đọc và timeout toàn thao tác |
| Deadline | Thời điểm cuối cùng RPC còn được phép hoàn thành | Nên phù hợp với ngân sách thời gian còn lại của request |
| Retry | Thử lại khi lỗi tạm thời có thể phục hồi | Chỉ retry lỗi phù hợp và thao tác an toàn khi lặp |
| Cancellation | Dừng công việc không còn cần thiết | Kiểm tra API có truyền cancellation xuống transport hay không |

GAX hỗ trợ cấu hình retry và timeout cho nhiều GAPIC clients thông qua settings của client hoặc callable context. Cấu hình mặc định khác nhau theo API method; không nên giả định mọi method đều retry giống nhau. Khi điều chỉnh, hãy đặt tổng thời gian retry nhỏ hơn deadline nghiệp vụ và dùng exponential backoff cùng jitter khi phù hợp.

Các lỗi như UNAVAILABLE hoặc một số trường hợp DEADLINE_EXCEEDED có thể là tạm thời, nhưng cần xem semantics của method. INVALID_ARGUMENT thường không thể khắc phục bằng retry. RESOURCE_EXHAUSTED có thể liên quan quota hoặc giới hạn tải; retry dồn dập có thể làm tình trạng xấu hơn.

Đặc biệt, nếu client mất kết nối sau khi server đã thực hiện thao tác nhưng trước khi response đến, ứng dụng không biết chắc thao tác đã thành công hay chưa. Với thao tác ghi hoặc tạo tài nguyên, dùng idempotency key, request ID hoặc kiểm tra trạng thái trước khi retry để tránh tạo bản ghi trùng.

Với ApiFuture, có thể đăng ký xử lý lỗi và hủy future khi công việc không còn cần thiết. Tuy nhiên, cancellation ở client không bảo đảm server đã dừng xử lý; hãy dựa vào hợp đồng của API và thiết kế thao tác có thể phục hồi.

## 11. Quản lý client và vòng đời trong ứng dụng Spring

Các Google Cloud clients thường tạo transport, channel, executor hoặc connection pool bên trong. Tạo client mới cho từng request làm tăng chi phí khởi tạo, số kết nối và số thread. Với những client thread-safe, nên tạo một instance dùng chung cho ứng dụng và đóng nó khi ứng dụng dừng.

Ví dụ cấu hình một GAPIC client dùng chung trong Spring:

~~~java
import com.google.cloud.bigquery.storage.v1.BigQueryReadClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.IOException;

@Configuration
public class GcpClientConfiguration {
  @Bean(destroyMethod = "close")
  BigQueryReadClient bigQueryReadClient() throws IOException {
    return BigQueryReadClient.create();
  }
}
~~~

Spring sẽ đóng client khi context dừng. Với Publisher và Subscriber của Pub/Sub, cần quản lý các lifecycle method riêng như shutdown/awaitTermination hoặc startAsync/stopAsync/awaitTerminated theo đúng loại client. Nếu dùng Spring Cloud GCP, các abstraction như PubSubTemplate có thể giảm mã quản lý transport và tích hợp với dependency injection; hãy chọn một lớp quản lý rõ ràng, tránh tạo nhiều Publisher hoặc Subscriber trùng lặp.

Trong Spring MVC, lời gọi đồng bộ có thể phù hợp nếu thời gian chờ và số thread được kiểm soát. Trong Spring WebFlux, không gọi API blocking trực tiếp trên event loop. Hãy dùng API bất đồng bộ nếu thư viện hỗ trợ, hoặc chuyển blocking call sang scheduler dành riêng cho I/O blocking với concurrency hữu hạn.

Annotation @Async chỉ đưa phương thức sang executor khác; nó không thay đổi semantics của Google client bên trong. Nếu phương thức vẫn gọi API blocking, thread của executor vẫn bị giữ trong lúc chờ. Hãy chọn giữa future, stream hoặc blocking executor dựa trên API thật và mô hình tải.

## 12. Chọn mô hình theo dịch vụ và tình huống

| Dịch vụ hoặc tác vụ | Mô hình thường phù hợp | Lý do |
| --- | --- | --- |
| Cloud Storage đọc metadata object | Đồng bộ | Một response nhỏ, cần kết quả ngay |
| Cloud Storage đọc hoặc ghi object lớn | Channel/streaming | Xử lý từng phần, giảm bộ nhớ đỉnh |
| Pub/Sub publish message | Bất đồng bộ | Publisher có thể gom batch và trả future |
| Pub/Sub consume subscription | Callback liên tục và flow control | Message đến theo thời gian, consumer xác nhận từng message |
| BigQuery Storage Read API | Server streaming | Dữ liệu trả về theo block và có thể đọc nhiều stream |
| GAPIC unary RPC | Đồng bộ hoặc ApiFuture | Chọn theo khả năng chặn thread và nhu cầu điều phối |
| gRPC client/bidirectional stream | Streaming | Trao đổi nhiều message trong một phiên |

Đây là gợi ý theo dạng công việc, không phải cam kết rằng mọi phiên bản thư viện đều có cùng phương thức. Kiểm tra API reference và mẫu mã của đúng dịch vụ trước khi chọn.

## 13. Quan sát và vận hành

Để vận hành ổn định, cần quan sát cả lời gọi API và cách ứng dụng tiêu thụ kết quả:

- Ghi nhận latency theo dịch vụ, method và loại thao tác.
- Đếm request thành công, lỗi, retry và cancellation.
- Theo dõi số future đang chờ và thời gian hoàn tất.
- Theo dõi số stream đang mở, thời lượng stream, số response và lỗi kết thúc.
- Đo outstanding message, queue depth, buffer size và thời gian xử lý callback.
- Gắn correlation ID hoặc trace context để liên kết request của ứng dụng với log.
- Không ghi payload, access token hoặc secret vào log nếu dữ liệu đó nhạy cảm.

Khi lỗi tăng, phân biệt lỗi do mạng, quota, IAM, deadline, dữ liệu đầu vào và downstream. Một callback thất bại không nên chỉ ghi thông báo chung chung; log cần có service, operation, resource định danh an toàn, status code và correlation ID để điều tra.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi get() ngay sau khi nhận ApiFuture | Thread vẫn bị chặn, không còn lợi ích bất đồng bộ | Dùng callback hoặc compose future |
| Tạo client cho từng request | Tốn kết nối, thread và thời gian khởi tạo | Dùng client dùng chung và đóng khi ứng dụng dừng |
| Tải toàn bộ dữ liệu lớn vào bộ nhớ | Tăng heap và nguy cơ OutOfMemoryError | Đọc/ghi theo channel hoặc stream |
| Không giới hạn message đang xử lý | Queue và bộ nhớ tăng khi consumer chậm | Dùng flow control và queue hữu hạn |
| Retry mọi lỗi | Tăng tải, lặp side effect và kéo dài sự cố | Retry có chọn lọc, backoff và idempotency |
| Không đóng Publisher, Subscriber hoặc client | Rò rỉ thread, channel và kết nối | Quản lý lifecycle rõ ràng trong Spring |
| Chạy blocking call trên WebFlux event loop | Giảm khả năng phục vụ nhiều request | Dùng API non-blocking hoặc scheduler riêng |
| Xem mọi streaming API là giống nhau | Đóng stream, xử lý lỗi hoặc flow control sai | Theo hợp đồng của từng API và loại RPC |

## 15. Checklist trước khi đưa vào production

Trước khi triển khai tích hợp Java client, hãy xác nhận:

- Đã chọn mô hình đồng bộ, bất đồng bộ hoặc streaming theo đặc điểm dữ liệu và latency.
- Đã kiểm tra API reference của đúng dịch vụ và phiên bản thư viện.
- Client được tái sử dụng an toàn và đóng đúng lifecycle.
- Timeout/deadline phù hợp với ngân sách thời gian của request.
- Retry chỉ áp dụng cho lỗi phù hợp và thao tác an toàn khi lặp.
- Future callback chạy trên executor phù hợp và không chặn thread hoàn tất.
- Stream được xử lý theo từng phần, có giới hạn buffer và concurrency.
- Pub/Sub consumer có flow control, ack/nack và xử lý idempotent.
- Cancellation, lỗi giữa stream và quá trình khởi động lại đã có cách xử lý.
- Spring WebFlux không bị chặn bởi lời gọi blocking.
- Log, metric và trace đủ để quan sát latency, lỗi, queue và stream.
- Không ghi secret hoặc payload nhạy cảm vào log.

Khi sử dụng đúng mô hình, Java clients giúp ứng dụng tích hợp Google Cloud hiệu quả và dễ vận hành hơn. Gọi đồng bộ giữ luồng nghiệp vụ đơn giản, future giúp tận dụng thời gian chờ I/O, còn streaming hỗ trợ dữ liệu lớn và sự kiện liên tục. Quyết định quan trọng là quản lý thread, deadline, retry, backpressure và lifecycle cùng với API được chọn.
