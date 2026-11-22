# Xây dựng Java function với Functions Framework

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Functions Framework trong việc viết Java function có thể chạy local và triển khai lên Google Cloud.
- Phân biệt HTTP function với function nhận sự kiện theo CloudEvents.
- Tạo handler Java bằng các interface của Functions Framework.
- Tổ chức Maven project, chọn entry point và chạy function trong môi trường phát triển.
- Triển khai function lên Cloud Run functions (trước đây thường được gọi là Cloud Functions thế hệ 2) bằng Google Cloud CLI.
- Kết nối function với HTTP, Cloud Storage, Pub/Sub và Eventarc theo đúng loại trigger.
- Thiết kế quyền truy cập, idempotency, retry, logging và kiểm thử cho function.

## 1. Functions Framework là gì?

Functions Framework là framework mã nguồn mở cung cấp hợp đồng lập trình để viết function theo cách độc lập với nền tảng triển khai. Với Java, framework định nghĩa các interface cho function HTTP và function nhận sự kiện. Ứng dụng triển khai một interface, còn Functions Framework đảm nhiệm việc khởi chạy và chuyển request hoặc event vào handler.

Một Java function có thể chạy bằng Functions Framework trong môi trường local hoặc được đóng gói và triển khai lên nền tảng hỗ trợ framework. Trên Google Cloud, framework được dùng bởi Cloud Run functions. Điều này giúp người phát triển tập trung vào logic xử lý mà không phải tự viết HTTP server hoặc vòng lặp nhận sự kiện.

Functions Framework không phải là một workflow engine, queue hoặc cơ sở dữ liệu. Nó cung cấp điểm vào (entry point) cho một invocation. Việc điều phối nhiều bước, lưu trạng thái bền vững, retry và quản lý event delivery phụ thuộc vào dịch vụ triển khai và trigger được chọn.

### 1.1. Vị trí của framework trong kiến trúc

~~~mermaid
flowchart TD
    A[HTTP request hoặc CloudEvent] --> B[Google Cloud trigger]
    B --> C[Cloud Run functions runtime]
    C --> D[Functions Framework]
    D --> E[Java function entry point]
    E --> F[Application service]
    F --> G[Database, Cloud Storage hoặc API]
~~~

Luồng xử lý khái quát:

1. Một client gọi HTTP endpoint hoặc một sự kiện được phát sinh từ dịch vụ Google Cloud.
2. Nền tảng nhận request/event và tạo invocation cho function.
3. Functions Framework chuyển request/event đến class Java được khai báo làm entry point.
4. Handler kiểm tra input, gọi application service và tạo kết quả hoặc tác động nghiệp vụ.
5. Runtime trả HTTP response hoặc ghi nhận việc xử lý event theo semantics của trigger.

### 1.2. Functions Framework và Cloud Run functions

Cloud Run functions là cách Google Cloud chạy source function theo mô hình serverless trên nền Cloud Run. Tên gọi và giao diện quản lý có thể thay đổi theo thế hệ sản phẩm; tài liệu và lệnh CLI cũ thường dùng tên Cloud Functions gen2. Khi triển khai, `gcloud functions deploy --gen2` vẫn là một cách phổ biến để tạo function thế hệ 2.

Functions Framework là hợp đồng handler mà source Java thực thi. Cloud Run functions cung cấp môi trường chạy, mở rộng, mạng, danh tính dịch vụ, logging và tích hợp trigger. Phân biệt hai lớp này giúp ứng dụng dễ chạy local và tránh phụ thuộc vào một API triển khai cụ thể trong business logic.

### 1.3. Hai loại function chính

| Loại | Interface Java | Đầu vào | Dùng khi |
|---|---|---|---|
| HTTP function | `HttpFunction` | HTTP request | REST endpoint, webhook, health/status endpoint |
| Event function | `CloudEventsFunction` | CloudEvent | Cloud Storage, Pub/Sub, Eventarc và sự kiện tương thích CloudEvents |

HTTP function nhận method, path, headers, query và body. Event function nhận một CloudEvent envelope có các thuộc tính chuẩn như `id`, `source`, `type`, `subject` và dữ liệu event. Hai loại handler có contract khác nhau; không nên cố xử lý CloudEvent như một HTTP request thông thường.

## 2. Tạo Maven project cho Java Functions Framework

Một project tối thiểu có thể tổ chức như sau:

~~~text
hello-functions/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    ├── HelloHttp.java
                    └── StorageCreatedFunction.java
~~~

`pom.xml` khai báo Functions Framework API để compiler biết các interface và kiểu request/response:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>hello-functions</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.1.0</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>
</project>
~~~

Phiên bản dependency ở đây là ví dụ minh họa. Hãy chọn phiên bản API tương thích với runtime và plugin mà project sử dụng, rồi pin version trong Maven để build có thể lặp lại. Không dùng version động như `LATEST` trong pipeline production.

Với Maven, source code nằm trong `src/main/java`; class entry point cần public và implement đúng interface. Build thường dùng `mvn package`. Artifact triển khai phải chứa code ứng dụng và dependency runtime theo định dạng mà buildpack hoặc quy trình đóng gói yêu cầu. Nếu dùng shaded JAR, kiểm tra kỹ service descriptor và resource để không làm mất metadata của thư viện.

### 2.1. Dependency API và dependency ứng dụng

Tách dependency thành hai nhóm:

- **Functions Framework API:** kiểu `HttpFunction`, `HttpRequest`, `HttpResponse`, `CloudEventsFunction` và CloudEvent contract.
- **Dependency ứng dụng:** JSON mapper, validation, database client, Google Cloud client library và thư viện nghiệp vụ.

Không đưa credential cố định vào Maven resource hoặc source code. Khi function chạy trên Google Cloud, hãy dùng service account gắn với function và Application Default Credentials để client library lấy danh tính thực thi.

## 3. Xây dựng HTTP function

HTTP function implement `com.google.cloud.functions.HttpFunction`. Functions Framework gọi phương thức `service` cho mỗi request. Handler đọc request, kiểm tra điều kiện và ghi status, header, body vào response.

### 3.1. HTTP function tối thiểu

~~~java
package com.example;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;

public final class HelloHttp implements HttpFunction {

    @Override
    public void service(
            HttpRequest request,
            HttpResponse response) throws Exception {

        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            response.getWriter().write("Method Not Allowed");
            return;
        }

        response.setStatusCode(200);
        response.appendHeader("Content-Type", "text/plain; charset=utf-8");
        response.getWriter().write("Hello from Java Functions Framework");
    }
}
~~~

Một số điểm cần chú ý:

- Method HTTP phải được kiểm tra theo contract của endpoint.
- Status code phải phản ánh kết quả xử lý, ví dụ `400` cho input không hợp lệ, `401`/`403` cho vấn đề xác thực/quyền, `404` khi không tìm thấy tài nguyên và `500` cho lỗi ngoài dự kiến.
- Chỉ ghi header/body phù hợp với response. Không trả stack trace hoặc thông tin nội bộ cho client.
- Handler nên kết thúc sau khi ghi response; không giữ request/response object để dùng trong invocation khác.

### 3.2. Đọc query parameter, header và body

`HttpRequest` cung cấp các phương thức đọc method, URI, query parameter, header và input stream. Ví dụ:

~~~java
package com.example;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;

import java.util.List;

public final class SearchHttp implements HttpFunction {

    @Override
    public void service(
            HttpRequest request,
            HttpResponse response) throws Exception {

        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            return;
        }

        String query = request.getFirstQueryParameter("q").orElse("");
        List<String> tags = request.getQueryParameters().get("tag");

        if (query.isBlank()) {
            response.setStatusCode(400);
            response.getWriter().write("Missing query parameter: q");
            return;
        }

        response.setStatusCode(200);
        response.appendHeader("Content-Type", "text/plain; charset=utf-8");
        response.getWriter().write(
                "q=" + query + ", tags=" + (tags == null ? List.of() : tags));
    }
}
~~~

API cụ thể có thể cung cấp `getFirstQueryParameter`, `getQueryParameters`, `getFirstHeader`, `getInputStream` và `getReader`. Hãy dùng đúng method của phiên bản Functions Framework API mà project pin. Không giả định query parameter luôn có mặt hoặc chỉ xuất hiện một lần.

Với request body, giới hạn kích thước trước khi đọc toàn bộ vào memory. Dùng JSON mapper như Jackson/Gson để deserialize sang DTO, kiểm tra schema và validate các field bắt buộc. Với payload lớn, cân nhắc stream thay vì đọc toàn bộ body vào một `String` hoặc `byte[]`.

### 3.3. HTTP response và error mapping

Nên thống nhất error contract để client biết cách xử lý:

~~~json
{
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "The field 'email' is required",
    "requestId": "req-8f31"
  }
}
~~~

Một số nguyên tắc:

- Dùng `400 Bad Request` cho input không hợp lệ.
- Dùng `401 Unauthorized` khi thiếu hoặc sai thông tin xác thực; `403 Forbidden` khi danh tính hợp lệ nhưng không có quyền.
- Dùng `404 Not Found` khi tài nguyên không tồn tại hoặc chính sách bảo mật yêu cầu không tiết lộ sự tồn tại.
- Dùng `409 Conflict` cho xung đột trạng thái nghiệp vụ.
- Dùng `429 Too Many Requests` khi áp dụng rate limit.
- Dùng `5xx` cho lỗi phía server hoặc dependency mà client có thể thử lại theo chính sách.

Không ánh xạ mọi exception thành `200 OK`. Đồng thời, không trả nguyên văn exception, SQL, token, secret hoặc stack trace ra ngoài. Ghi lỗi chi tiết ở log có kiểm soát và trả thông báo an toàn cho client.

### 3.4. Không lưu trạng thái request trong field của handler

Một class function có thể được tái sử dụng trong execution environment và nhiều request có thể được xử lý đồng thời tùy cấu hình nền tảng. Vì vậy, không đặt dữ liệu request vào field mutable dùng chung:

~~~java
// Không nên: request A có thể ghi đè dữ liệu của request B.
public final class UnsafeHandler implements HttpFunction {
    private String currentUser;

    @Override
    public void service(HttpRequest request, HttpResponse response) {
        currentUser = request.getFirstHeader("X-User").orElse("");
        // ...
    }
}
~~~

Hãy giữ dữ liệu request trong biến local của `service`. Client dùng chung như HTTP client hoặc database pool có thể được tái sử dụng nếu thread-safe và được khởi tạo an toàn. Không lưu dữ liệu cá nhân, authorization context hoặc trạng thái nghiệp vụ của một request vào biến static.

## 4. Xây dựng event function với CloudEvents

Các sự kiện từ Google Cloud thường được chuyển đến function dưới dạng CloudEvent. CloudEvents là một chuẩn mở mô tả event bằng envelope thống nhất, giúp handler không phải phụ thuộc vào định dạng transport riêng của từng dịch vụ.

Java event function implement `com.google.cloud.functions.CloudEventsFunction` và xử lý một đối tượng `io.cloudevents.CloudEvent`.

### 4.1. CloudEvent envelope

Một CloudEvent có các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `id` | Định danh event trong phạm vi source |
| `source` | Nguồn phát sinh event |
| `type` | Loại sự kiện, mô tả việc gì đã xảy ra |
| `subject` | Đối tượng cụ thể trong source nếu có |
| `time` | Thời điểm event được phát sinh nếu có |
| `datacontenttype` | Content type của event data |
| `data` | Payload đặc thù của sự kiện |

Ví dụ minh họa một CloudEvent cho object được tạo trong Cloud Storage:

~~~json
{
  "specversion": "1.0",
  "id": "1234567890",
  "source": "//storage.googleapis.com/projects/_/buckets/product-images",
  "type": "google.cloud.storage.object.v1.finalized",
  "subject": "objects/catalog/item-01.jpg",
  "time": "2026-11-17T08:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "bucket": "product-images",
    "name": "catalog/item-01.jpg",
    "generation": "1731832200000000",
    "contentType": "image/jpeg",
    "size": "524288"
  }
}
~~~

CloudEvent envelope là lớp metadata chung; cấu trúc `data` phụ thuộc loại event. Handler nên kiểm tra `type` trước khi parse data theo schema cụ thể. Không giả định mọi CloudEvent đều có cùng field trong payload.

### 4.2. Java handler cho Cloud Storage event

Ví dụ dưới đây dùng Jackson để đọc payload JSON. Project cần thêm Jackson Databind vào Maven dependencies:

~~~java
package com.example;

import com.google.cloud.functions.CloudEventsFunction;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.cloudevents.CloudEvent;

public final class StorageCreatedFunction implements CloudEventsFunction {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"google.cloud.storage.object.v1.finalized".equals(event.getType())) {
            System.out.println("Ignoring event type: " + event.getType());
            return;
        }

        if (event.getData() == null) {
            throw new IllegalArgumentException("CloudEvent data is missing");
        }

        JsonNode data = MAPPER.readTree(event.getData().toBytes());

        String bucket = data.path("bucket").asText();
        String objectName = data.path("name").asText();
        String generation = data.path("generation").asText();

        if (bucket.isBlank() || objectName.isBlank() || generation.isBlank()) {
            throw new IllegalArgumentException(
                    "Required Cloud Storage event fields are missing");
        }

        System.out.printf(
                "Object finalized: bucket=%s name=%s generation=%s eventId=%s%n",
                bucket, objectName, generation, event.getId());

        // Gọi application service để xử lý object.
    }
}
~~~

`ObjectMapper` được tạo một lần và tái sử dụng vì nó có thể dùng chung an toàn sau khi cấu hình xong. Không giữ dữ liệu của từng event trong field mutable. Trong ứng dụng thực tế, nên đưa logic xử lý object vào service riêng, còn handler chỉ xác thực envelope, chuyển đổi DTO và gọi service.

Nếu xử lý file, hãy dùng `bucket`, `name` và `generation` để xác định đúng object version. Object có thể bị ghi đè sau khi event phát sinh; nếu cần xử lý đúng phiên bản đã tạo event, hãy đọc object theo generation hoặc áp dụng cơ chế kiểm tra version tương ứng.

### 4.3. Phân biệt event type và event data

Một event handler nên kiểm tra tối thiểu:

- `event.getType()` có đúng loại event mong muốn không.
- `event.getId()` và `event.getSource()` có hiện diện để định danh không.
- `event.getData()` có tồn tại và đúng content type không.
- Các field nghiệp vụ bắt buộc trong payload có hợp lệ không.
- Event có thuộc tenant, bucket, topic hoặc đối tượng mà function được phép xử lý không.

Không dùng mỗi `subject` làm định danh duy nhất vì cùng một object có thể phát sinh nhiều event ở các thời điểm hoặc generation khác nhau. Kết hợp `source`, `id` và khóa nghiệp vụ như object generation giúp truy vết và chống xử lý trùng.

## 5. CloudEvents, Pub/Sub và Eventarc

Eventarc định tuyến sự kiện từ các nguồn Google Cloud đến đích hỗ trợ như Cloud Run functions. Pub/Sub có thể kích hoạt function thông qua trigger tương ứng; Cloud Storage có thể phát sự kiện object finalized, deleted hoặc metadata updated tùy cấu hình nguồn.

### 5.1. Luồng event qua Eventarc

~~~mermaid
flowchart LR
    A[Cloud Storage hoặc Pub/Sub] --> B[Eventarc trigger]
    B --> C[Cloud Run functions endpoint]
    C --> D[Functions Framework]
    D --> E[CloudEventsFunction]
    E --> F[Validate event]
    F --> G[Idempotent application service]
    G --> H[Database hoặc Cloud Storage]
~~~

Eventarc chịu trách nhiệm lọc/định tuyến sự kiện theo trigger đã cấu hình. Functions Framework nhận CloudEvent ở entry point. Application service xử lý nghiệp vụ. Mỗi lớp nên có trách nhiệm rõ ràng để có thể kiểm thử handler và logic nghiệp vụ độc lập.

### 5.2. Ví dụ triển khai Cloud Storage trigger

Một function có thể được deploy bằng Google Cloud CLI:

~~~bash
gcloud functions deploy storageCreated \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.StorageCreatedFunction \
  --trigger-bucket=product-images \
  --memory=512Mi \
  --timeout=120s
~~~

Ví dụ này minh họa function nhận event khi object trong bucket được tạo/finalize. Tài khoản triển khai cần quyền cần thiết để tạo function, build source, cấu hình Eventarc và gắn service account. Bucket và trigger phải đáp ứng yêu cầu location/region của dịch vụ.

### 5.3. Ví dụ triển khai Pub/Sub trigger

Với topic Pub/Sub:

~~~bash
gcloud functions deploy messageProcessor \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.PubSubFunction \
  --trigger-topic=orders \
  --memory=512Mi \
  --timeout=60s
~~~

Trong CloudEvent data của Pub/Sub, payload thường là JSON mô tả message và subscription. Trường `message.data` được mã hóa Base64. Handler cần decode Base64 trước khi parse nội dung nghiệp vụ; không parse trực tiếp toàn bộ CloudEvent data như thể đó là JSON đơn hàng.

### 5.4. Xử lý lỗi và retry của event

Event-driven function có thể nhận lại cùng một event nếu delivery hoặc xử lý thất bại. Hành vi retry, thời gian giữ event và khả năng dead-letter phụ thuộc nguồn phát, Eventarc, Pub/Sub và cấu hình trigger. Không giả định mọi trigger đều có cùng chính sách retry.

Một số nguyên tắc:

- Chỉ coi event được xử lý thành công sau khi tác động nghiệp vụ đã được ghi bền vững.
- Với lỗi tạm thời, để invocation thất bại theo contract của trigger nếu retry được cấu hình.
- Với lỗi dữ liệu vĩnh viễn, ghi nhận lỗi có thể điều tra và áp dụng chính sách bỏ qua/quarantine phù hợp.
- Không bắt exception rồi trả về bình thường nếu muốn nền tảng retry; return bình thường thường được xem là handler đã xử lý xong.
- Theo dõi event retry, event quá hạn và dead-letter path nếu dịch vụ nguồn hỗ trợ.
- Không retry vô hạn một event có payload không hợp lệ; điều đó có thể tạo vòng lặp và chi phí.

Với Pub/Sub, cần xem xét ack deadline, retry policy, subscription và dead-letter topic. Với Eventarc, kiểm tra chính sách retry và giới hạn lưu giữ event của trigger cụ thể. Khi một handler ném exception, hành vi cuối cùng còn phụ thuộc loại trigger và cấu hình đã deploy.

## 6. Idempotency và xử lý event trùng lặp

Serverless event delivery thường ưu tiên khả năng giao lại khi không chắc chắn một event đã được xử lý hay chưa. Vì vậy, handler cần an toàn khi cùng event được nhận nhiều lần.

### 6.1. Chọn idempotency key

Một khóa có thể được tạo từ `source` và `id` của CloudEvent:

~~~java
String eventKey = event.getSource().toString()
        + ":"
        + event.getId();
~~~

Lưu event key vào database với unique constraint. Nếu key đã tồn tại và trạng thái đã hoàn tất, handler có thể bỏ qua tác động lặp. Nếu event đang xử lý, hệ thống cần lease/lock hoặc trạng thái có thời hạn để xử lý trường hợp invocation trước bị dừng giữa chừng.

Đối với Cloud Storage, nếu nghiệp vụ cần phân biệt các phiên bản object, có thể đưa `bucket`, `name` và `generation` vào khóa nghiệp vụ. Đừng chỉ dùng tên object nếu object cùng tên có thể được ghi đè nhiều lần.

### 6.2. Ghi trạng thái và tác động trong cùng transaction

Một quy trình idempotent nên:

1. Tạo hoặc claim event key bằng thao tác nguyên tử.
2. Kiểm tra event đã hoàn tất hay đang được worker khác xử lý.
3. Thực hiện tác động nghiệp vụ.
4. Ghi kết quả và đánh dấu event hoàn tất theo transaction hoặc giao thức nhất quán.
5. Chỉ trả thành công sau khi trạng thái bền vững đã được ghi.

Nếu tác động diễn ra ở một hệ thống bên ngoài, database transaction cục bộ không thể bảo đảm tính nguyên tử giữa hai hệ thống. Khi đó cần idempotency key ở dịch vụ đích, outbox/inbox pattern hoặc bước đối soát để xử lý trạng thái không xác định.

### 6.3. Không dùng bộ nhớ instance làm nơi chống trùng

Không dùng `static Set<String>` hoặc cache trong RAM để ghi nhận event đã xử lý. Function có thể chạy trên nhiều instance, instance có thể bị thu hồi và nhiều invocation có thể xử lý cùng event đồng thời. Dùng kho lưu trữ bền vững có unique constraint hoặc cơ chế claim nguyên tử.

## 7. Chạy function local và quy trình phát triển

Functions Framework giúp chạy function trong môi trường local để kiểm tra handler trước khi deploy. Maven project có thể cấu hình Functions Framework Maven plugin với phiên bản tương thích; plugin cung cấp goal chạy server local.

Ví dụ chạy HTTP function:

~~~bash
mvn function:run -Drun.functionTarget=com.example.HelloHttp
~~~

Server local thường lắng nghe trên port được cấu hình, mặc định phổ biến là `8080`. Có thể thử bằng curl:

~~~bash
curl -i http://localhost:8080/
~~~

Với event function, cần gửi một CloudEvent có envelope và data hợp lệ đến server local theo giao thức CloudEvents. Payload thử nghiệm phải có `specversion`, `id`, `source`, `type` và `data` tương ứng với handler. Không gửi một JSON nghiệp vụ thuần rồi mong framework tự suy ra đó là CloudEvent.

### 7.1. Cấu hình Maven plugin

Plugin local run phải được khai báo trong `pom.xml` với version được pin. Chọn phiên bản plugin đã xác minh tương thích với Functions Framework API và Maven project; không dùng version động trong CI/CD. Nếu project có nhiều function class, truyền `run.functionTarget` để chỉ định class đang chạy.

### 7.2. Tách handler khỏi business logic

Handler nên mỏng:

- Chuyển đổi request/event thành command hoặc DTO.
- Kiểm tra contract, field bắt buộc và giới hạn payload.
- Gọi application service.
- Chuyển kết quả hoặc exception thành HTTP response hoặc event outcome.

Business service nên không phụ thuộc trực tiếp vào `HttpRequest`, `HttpResponse` hoặc `CloudEvent`. Điều này giúp kiểm thử logic nghiệp vụ bằng unit test mà không cần khởi động Functions Framework.

~~~mermaid
flowchart TD
    A[HttpFunction hoặc CloudEventsFunction] --> B[Adapter / DTO mapping]
    B --> C[Application service]
    C --> D[Domain logic]
    C --> E[Repository interface]
    E --> F[Cloud SQL, Firestore hoặc API]
~~~

## 8. Triển khai HTTP function và bảo vệ endpoint

Ví dụ deploy HTTP function trên Cloud Run functions:

~~~bash
gcloud functions deploy helloHttp \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.HelloHttp \
  --trigger-http \
  --memory=512Mi \
  --timeout=30s \
  --max-instances=10
~~~

Để endpoint công khai cho demo, có thể cấu hình cho phép unauthenticated invocation theo chính sách của project. Với API thật, nên yêu cầu IAM authentication hoặc đặt API Gateway/đầu vào có xác thực phù hợp. Không bật public access chỉ để curl thử nghiệm nếu endpoint có thể thay đổi dữ liệu hoặc truy cập tài nguyên nội bộ.

### 8.1. IAM và service account

Có hai vai trò danh tính cần phân biệt:

- **Invoker identity:** danh tính được phép gọi function/endpoint.
- **Runtime service account:** danh tính mà function sử dụng khi gọi Cloud Storage, Pub/Sub, Secret Manager, database hoặc dịch vụ khác.

Không cấp quyền Owner/Editor cho runtime service account chỉ để function chạy được. Cấp quyền tối thiểu trên đúng tài nguyên cần thiết. Nếu function đọc một bucket, chỉ cấp quyền đọc bucket đó; nếu function publish lên một topic, cấp quyền publish trên topic tương ứng.

Đối với HTTP endpoint nội bộ, client cần token hoặc cơ chế xác thực phù hợp. Đối với event trigger, Eventarc/Pub/Sub cần danh tính và quyền để gửi event đến đích. Việc cấp quyền cho trigger và quyền runtime service account là hai việc riêng.

### 8.2. Secret và cấu hình môi trường

Không hardcode API key, password hoặc private key trong source code, Maven resource hay image layer. Dùng Secret Manager và cấp quyền truy cập secret cho runtime service account. Tham số không nhạy cảm có thể truyền qua environment variable hoặc cấu hình triển khai.

Log không được chứa secret, bearer token, dữ liệu cá nhân hoặc toàn bộ request body nhạy cảm. Khi log lỗi, ưu tiên mã lỗi, request ID, event ID và correlation ID.

## 9. Ví dụ đọc Pub/Sub message trong CloudEvent

CloudEvent data của Pub/Sub thường chứa một object `message`; trường `data` của message là chuỗi Base64. Handler cần decode trước khi chuyển thành JSON hoặc DTO nghiệp vụ.

~~~java
package com.example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class PubSubFunction implements CloudEventsFunction {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"google.cloud.pubsub.topic.v1.messagePublished"
                .equals(event.getType())) {
            return;
        }

        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing Pub/Sub event data");
        }

        JsonNode envelope = MAPPER.readTree(event.getData().toBytes());
        String encoded = envelope.path("message").path("data").asText();

        if (encoded.isBlank()) {
            throw new IllegalArgumentException("Pub/Sub message data is empty");
        }

        byte[] decoded = Base64.getDecoder().decode(encoded);
        String payload = new String(decoded, StandardCharsets.UTF_8);

        System.out.printf(
                "Received Pub/Sub event id=%s source=%s payloadBytes=%d%n",
                event.getId(), event.getSource(), decoded.length);

        // Parse payload và gọi application service.
    }
}
~~~

Payload thực tế có thể là JSON, text hoặc binary. Chỉ chuyển thành UTF-8 string khi producer đã định nghĩa message data là văn bản UTF-8. Nếu payload là binary, truyền byte array cho service phù hợp. Validate kích thước trước khi deserialize để tránh tiêu thụ memory không giới hạn.

## 10. Cấu hình và triển khai function

Cloud Run functions hỗ trợ build source, chọn runtime, entry point, trigger và một số giới hạn tài nguyên. Cấu hình cần được quản lý cùng source code hoặc template triển khai để có thể review và tái tạo.

### 10.1. Triển khai HTTP function

Ví dụ:

~~~bash
gcloud functions deploy helloHttp \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.HelloHttp \
  --trigger-http \
  --memory=512Mi \
  --timeout=30s \
  --max-instances=10
~~~

Các tham số chính:

- `--gen2`: triển khai function thế hệ 2 trên nền Cloud Run.
- `--runtime=java21`: chọn runtime Java 21 được hỗ trợ trong ví dụ.
- `--region`: chọn region phù hợp với người dùng, dữ liệu và dịch vụ phụ thuộc.
- `--source`: thư mục chứa source và `pom.xml`.
- `--entry-point`: tên đầy đủ của class Java implement interface function.
- `--trigger-http`: tạo HTTP trigger.
- `--memory` và `--timeout`: đặt giới hạn tài nguyên và thời gian invocation.
- `--max-instances`: giới hạn số instance tối đa để kiểm soát khả năng mở rộng và tải lên dependency.

Ví dụ này không bật public access. Nếu endpoint cần công khai cho demo, hãy cấu hình quyền unauthenticated một cách có chủ đích và chỉ dùng với handler không phơi bày dữ liệu hoặc thao tác nhạy cảm. Với endpoint nội bộ, giữ yêu cầu IAM authentication và cấp quyền invoker cho đúng principal.

### 10.2. Triển khai event function

Một function nhận Cloud Storage event có thể dùng lệnh:

~~~bash
gcloud functions deploy storageCreated \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.StorageCreatedFunction \
  --trigger-bucket=product-images \
  --memory=512Mi \
  --timeout=120s
~~~

Với Pub/Sub, thay trigger bucket bằng topic:

~~~bash
gcloud functions deploy messageProcessor \
  --gen2 \
  --runtime=java21 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=com.example.PubSubFunction \
  --trigger-topic=orders \
  --memory=512Mi \
  --timeout=60s
~~~

Các lệnh là ví dụ; cần xác minh runtime, flag và yêu cầu region của trigger trong phiên bản Google Cloud CLI đang sử dụng. Eventarc có thể yêu cầu API được bật, service agent và quyền IAM phù hợp. Với Cloud Storage, bucket và trigger phải đáp ứng yêu cầu location. Với Pub/Sub, topic và function cần được cấu hình ở region/đường truyền đáp ứng yêu cầu dịch vụ.

### 10.3. Build, deploy và xác minh

Một quy trình triển khai cơ bản:

1. Build project và kiểm tra artifact.
2. Xác minh class entry point implement đúng interface.
3. Kiểm tra dependency và Java runtime tương thích.
4. Đảm bảo API liên quan đã bật và tài khoản deploy có quyền.
5. Deploy function vào region đã chọn.
6. Kiểm tra trạng thái build/deploy và trigger.
7. Gửi HTTP request hoặc phát event thử nghiệm.
8. Kiểm tra log, status, kết quả nghiệp vụ và quyền truy cập.
9. Chạy thử duplicate/retry và kiểm tra idempotency trước khi đưa traffic thật.

Nếu build thất bại, đọc Cloud Build log để xác định lỗi Maven, dependency hoặc runtime. Nếu build thành công nhưng invocation thất bại, kiểm tra entry point, function signature, runtime log, service account và quyền truy cập dịch vụ phụ thuộc.

### 10.4. Region và vị trí dữ liệu

Chọn region dựa trên nơi người dùng và dữ liệu được phục vụ, độ trễ đến database, yêu cầu residency và khả năng hỗ trợ trigger. Function ở một region nhưng database hoặc bucket ở region xa có thể tăng latency, chi phí truyền dữ liệu và rủi ro vận hành.

Không chỉ chọn region gần người dùng nếu dữ liệu bắt buộc ở một location khác. Với Cloud Storage/Eventarc, kiểm tra ràng buộc location của bucket, trigger và function trước khi deploy.

## 11. Concurrency, autoscaling và cold start

Cloud Run functions có thể tạo thêm instance khi tải tăng và thu hẹp khi tải giảm. Số instance và số request đồng thời trên mỗi instance phụ thuộc cấu hình, runtime và giới hạn nền tảng.

### 11.1. Thiết kế handler an toàn khi có concurrency

Không giả định mỗi instance chỉ xử lý một request tại một thời điểm. Một instance có thể nhận nhiều request đồng thời theo concurrency setting. Vì vậy:

- Biến local trong method phù hợp để giữ dữ liệu riêng cho request.
- Field immutable và client thread-safe có thể được chia sẻ nếu thư viện hỗ trợ.
- Không lưu user ID, tenant ID, request body hoặc trạng thái giao dịch trong mutable static field.
- Database pool cần có giới hạn và kích thước phù hợp với số request đồng thời.
- File tạm phải có tên duy nhất; không dùng một tên cố định cho mọi request.
- Dùng khóa hoặc transaction ở kho lưu trữ bền vững khi nhiều request có thể cập nhật cùng một tài nguyên.

### 11.2. Giới hạn concurrency và số instance

Concurrency cao có thể tăng throughput nhưng cũng làm database, API ngoài hoặc bộ nhớ bị quá tải. Giới hạn max instances giúp đặt trần số instance, nhưng không thay thế rate limit hoặc giới hạn kết nối ở downstream.

Ví dụ, nếu mỗi instance mở pool tối đa 10 connection và function có thể chạy 20 instance, database có thể phải chịu tới khoảng 200 connection từ function. Hãy tính theo concurrency, pool size và số service khác cùng truy cập database.

Với workload có tải đột biến, dùng queue để hấp thụ tải và worker xử lý theo capacity. Đặt max instances hoặc concurrency phù hợp với quota và SLA của dependency.

### 11.3. Cold start và khởi tạo Java

Cold start xảy ra khi nền tảng cần tạo execution environment mới, khởi chạy JVM, nạp class và khởi tạo dependency trước khi xử lý request đầu tiên. Framework lớn, classpath lớn, khởi tạo database client hoặc đọc cấu hình đồng bộ có thể làm thời gian khởi động tăng.

Một số cách giảm thời gian khởi tạo:

- Giảm dependency không cần thiết và kích thước artifact.
- Khởi tạo client dùng chung một lần khi phù hợp, tránh tạo lại trong mỗi request.
- Không thực hiện truy vấn database hoặc gọi API ngoài trong static initializer.
- Tải cấu hình cần thiết một cách có kiểm soát; không khởi tạo toàn bộ ứng dụng nếu function chỉ dùng một phần nhỏ.
- Đo cold start riêng với warm duration.
- Cân nhắc minimum instances khi yêu cầu latency nghiêm ngặt và chấp nhận chi phí duy trì instance.

Không đặt mọi thao tác khởi tạo vào static block nếu chúng có thể thất bại do network hoặc credential tạm thời. Một lỗi khởi tạo có thể khiến instance không sẵn sàng và gây lỗi cho nhiều request. Phân biệt dependency khởi tạo an toàn, có thể tái sử dụng với thao tác phụ thuộc request hoặc trạng thái người dùng.

## 12. Logging, monitoring và tracing

Một function cần được quan sát qua cả request và event. Log chỉ có dòng “function started” và “function finished” không đủ để điều tra khi có retry hoặc event trùng.

### 12.1. Các trường log nên có

- `requestId` hoặc trace ID cho HTTP request.
- `eventId`, `source` và `type` cho CloudEvent.
- `functionName`, `revision` hoặc version khi cần phân biệt deployment.
- `operation` và mã kết quả nghiệp vụ.
- `durationMs`, số lần retry nếu có và mã lỗi.
- `tenantId` đã được phép log hoặc một định danh đã được làm mờ.

Không log secret, bearer token, session cookie, dữ liệu cá nhân hoặc nội dung file nhạy cảm. Dùng structured logging để lọc theo field và liên kết với trace. Nếu log JSON, giữ schema ổn định để Cloud Logging parse chính xác.

### 12.2. Metric quan trọng

| Metric | Câu hỏi cần trả lời |
|---|---|
| Request count | Function đang nhận bao nhiêu request/event? |
| Request latency p50/p95/p99 | Độ trễ thay đổi thế nào theo tải? |
| Error rate | Có bao nhiêu invocation thất bại? |
| Instance count/concurrency | Autoscaling có đáp ứng tải không? |
| Cold start/initialization duration | Khởi tạo Java có ảnh hưởng latency không? |
| Memory utilization | Có nguy cơ OOM hoặc memory pressure không? |
| Event retry/dead-letter count | Event nào bị xử lý lặp hoặc thất bại kéo dài? |
| Downstream latency | Database hoặc API nào đang là bottleneck? |

Cloud Monitoring/Cloud Logging cung cấp metric nền tảng và log runtime. Có thể thêm custom metric cho kết quả nghiệp vụ như số đơn hàng xử lý thành công, số object bị bỏ qua hoặc số event trùng. Tránh tạo metric label có cardinality cao như request ID hoặc object name.

### 12.3. Tracing qua nhiều dịch vụ

Nếu function gọi Cloud SQL, Firestore, Pub/Sub hoặc HTTP API, tracing giúp xác định thời gian nằm ở handler hay dependency. Truyền trace/correlation ID qua các lời gọi nội bộ khi có thể. Với event bất đồng bộ, gắn event ID và source vào log để nối các bước producer-consumer.

## 13. Kiểm thử Java function

Có thể kiểm thử ở nhiều tầng:

- **Unit test:** kiểm tra application service, validation và mapping với input/output thông thường.
- **Handler test:** tạo request/event giả lập hoặc dùng test utility phù hợp để kiểm tra handler.
- **Local integration:** chạy Functions Framework local và gửi HTTP request hoặc CloudEvent.
- **Cloud integration:** deploy vào project thử nghiệm và kích hoạt bằng HTTP, Cloud Storage hoặc Pub/Sub.
- **Resilience test:** gửi event trùng, event sai schema, dependency timeout và request đồng thời.

Ví dụ unit test cho business service nên không cần Google Cloud credentials hoặc deploy function. Có thể mock repository và kiểm tra kết quả nghiệp vụ. Handler test tập trung vào status code, response body hoặc cách handler phản ứng với event không hợp lệ.

Khi test event, cần bao gồm:

- Event type không được hỗ trợ.
- Thiếu `id`, `source` hoặc data bắt buộc.
- Payload sai JSON hoặc sai encoding.
- Event được gửi lại nhiều lần.
- Hai invocation xử lý cùng một event gần như đồng thời.
- Dependency tạm thời lỗi và sau đó phục hồi.
- Event có object generation hoặc tenant không hợp lệ.

Khi test HTTP, cần bao gồm method không hỗ trợ, query parameter lặp/thiếu, body quá lớn, JSON sai schema, caller không có quyền và dependency timeout.

## 14. Bảo mật và quyền truy cập

Một function là ranh giới thực thi có thể được gọi từ Internet hoặc từ dịch vụ nội bộ. Bảo mật cần được áp dụng cả ở tầng invocation và tầng truy cập tài nguyên.

- Chỉ bật public invocation khi endpoint được thiết kế để công khai.
- Dùng IAM invoker hoặc lớp xác thực phía trước cho endpoint nội bộ.
- Runtime service account chỉ có quyền tối thiểu cần thiết.
- Không tin dữ liệu tenant/user do client gửi nếu chưa xác thực và kiểm tra quyền.
- Validate bucket, object, topic và resource ID trước khi truy cập.
- Dùng Secret Manager cho secret; không log credential.
- Giới hạn kích thước request, thời gian xử lý và concurrency để giảm nguy cơ lạm dụng.
- Dùng network/VPC configuration phù hợp nếu cần truy cập tài nguyên private.
- Kiểm tra nguồn event và loại event; không xử lý mọi CloudEvent như dữ liệu đáng tin cậy.

Một event hợp lệ về mặt CloudEvents vẫn có thể chứa payload không hợp lệ về nghiệp vụ. Kiểm tra chữ ký/nguồn gốc ở tầng trigger nếu hệ thống nhận event từ bên ngoài, sau đó vẫn validate dữ liệu trong handler.

## 15. Những lỗi thường gặp khi xây dựng Java function

- **Chọn sai entry point:** class không implement interface phù hợp hoặc tên class trong deploy command không đầy đủ.
- **Nhầm HTTP function với event function:** HTTP request và CloudEvent có contract khác nhau; handler cần implement đúng interface.
- **Đưa business logic vào handler:** làm logic khó kiểm thử và gắn chặt với framework.
- **Đọc body không giới hạn:** payload lớn có thể gây memory pressure hoặc timeout.
- **Không kiểm tra event type:** parse data theo schema sai và tạo lỗi runtime.
- **Không decode Pub/Sub Base64:** handler nhận chuỗi encoded thay vì payload nghiệp vụ.
- **Không có idempotency:** event delivery lại tạo tác động trùng.
- **Bắt exception rồi return bình thường:** trigger có thể coi event đã xử lý thành công và không retry.
- **Lưu trạng thái request trong static field:** request đồng thời có thể ghi đè dữ liệu của nhau.
- **Cấp quyền quá rộng cho service account:** một lỗi trong function có thể ảnh hưởng nhiều tài nguyên.
- **Không kiểm tra region/location:** trigger không tạo được hoặc dữ liệu phải truyền xa.
- **Không kiểm tra log sau deploy:** build thành công không có nghĩa invocation và quyền truy cập đều đúng.

## 16. Checklist triển khai

- [ ] Class entry point implement đúng `HttpFunction` hoặc `CloudEventsFunction`.
- [ ] Functions Framework API và Java runtime version được pin, tương thích.
- [ ] Maven build tạo artifact đúng và dependency runtime đầy đủ.
- [ ] Local HTTP/Event test chạy với payload đại diện.
- [ ] HTTP method, status code, header và body theo contract.
- [ ] CloudEvent handler kiểm tra type, source, id và data.
- [ ] Pub/Sub payload được decode đúng nếu có Base64.
- [ ] Event handler có idempotency key và xử lý duplicate.
- [ ] Retry policy phù hợp với loại trigger và lỗi nghiệp vụ.
- [ ] Entry point, trigger, region, memory và timeout đã được xác minh.
- [ ] Runtime service account có quyền tối thiểu cần thiết.
- [ ] Endpoint chỉ public khi có chủ đích; IAM invoker được cấu hình đúng.
- [ ] Secret lấy từ Secret Manager hoặc cơ chế quản lý secret phù hợp.
- [ ] Log có request/event ID và không chứa dữ liệu nhạy cảm.
- [ ] Đã kiểm tra concurrency, cold start và tải lên dependency.
- [ ] Có dashboard/cảnh báo cho error rate, latency, retry và dead-letter.

## 17. Tự kiểm tra

**Câu 1.** Functions Framework giải quyết vấn đề gì trong Java serverless?

**Gợi ý trả lời:** Nó cung cấp contract và runtime adapter cho HTTP function hoặc CloudEvents function, giúp handler chạy local và triển khai lên nền tảng hỗ trợ framework mà không phải tự viết HTTP server hoặc event loop.

**Câu 2.** HTTP function và CloudEvents function khác nhau ở điểm nào?

**Gợi ý trả lời:** HTTP function implement `HttpFunction` và nhận `HttpRequest`/`HttpResponse`. Event function implement `CloudEventsFunction` và nhận CloudEvent envelope có source, id, type và data.

**Câu 3.** Vì sao event handler phải idempotent?

**Gợi ý trả lời:** Event có thể được giao lại khi delivery hoặc xử lý không chắc chắn. Idempotency giúp cùng event không tạo tác động nghiệp vụ lặp, kể cả khi invocation chạy lại trên instance khác.

**Câu 4.** Vì sao không nên lưu user ID hoặc request state trong static field?

**Gợi ý trả lời:** Instance có thể được tái sử dụng và xử lý nhiều request đồng thời. Mutable shared state có thể bị request khác ghi đè và làm rò dữ liệu giữa người dùng.

**Câu 5.** Vì sao một function build thành công vẫn có thể lỗi khi deploy?

**Gợi ý trả lời:** Có thể chọn sai entry point, thiếu quyền IAM, sai trigger/region, dependency runtime thiếu, service account không được cấp quyền hoặc payload thực tế không đúng schema.

**Bài tập tình huống:** Xây dựng function xử lý ảnh khi người dùng upload object lên Cloud Storage. Function cần đọc metadata, tạo thumbnail và lưu kết quả vào bucket khác. Hãy thiết kế class entry point, CloudEvent fields cần kiểm tra, service account permissions, idempotency key, cách xử lý event retry và log cần có. Sau đó đề xuất cách chạy local, deploy lên Cloud Run functions và xác minh bằng một object thử nghiệm.

**Gợi ý:** Dùng class implement `CloudEventsFunction`; chỉ nhận event type finalized; đọc `bucket`, `name` và `generation`; xác thực bucket nằm trong allowlist. Idempotency key có thể kết hợp CloudEvent `source/id` hoặc bucket/object/generation tùy nghiệp vụ. Runtime service account chỉ cần quyền đọc object nguồn và ghi object thumbnail đích. Dùng object key xác định theo generation để retry không tạo nhiều file không kiểm soát. Chạy local với CloudEvent mẫu, deploy gen2 ở region phù hợp và tạo object thử nghiệm; xác minh log, object output, quyền truy cập và hành vi khi phát lại event.

## Kết luận

Functions Framework cung cấp hợp đồng Java cho HTTP function và event function theo CloudEvents. Handler nên tập trung vào adapter, kiểm tra input và gọi application service; logic nghiệp vụ, trạng thái và idempotency cần được quản lý độc lập. Khi triển khai Cloud Run functions, phải chọn đúng entry point, runtime, trigger, region và service account. HTTP endpoint cần IAM hoặc xác thực phù hợp; event handler cần kiểm tra event type, chống xử lý trùng và hiểu retry semantics của trigger. Chạy local, kiểm thử payload thực tế, quan sát log/metric và xác minh quyền sau deploy giúp Java function vận hành an toàn trong môi trường serverless.
