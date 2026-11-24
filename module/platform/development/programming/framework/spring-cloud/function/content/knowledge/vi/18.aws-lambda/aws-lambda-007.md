# Xử lý cấu trúc sự kiện API Gateway, S3 và SQS

Một bean **Function<T, R>** trong **SPRING_CLOUD_FUNCTION** có thể tái sử dụng qua HTTP, sự kiện hoặc serverless. Nhưng khi bean được gọi qua **AWS Lambda**, đầu vào không phải lúc nào cũng là JSON nghiệp vụ thuần. **API Gateway** gửi một *proxy event* chứa method, route, headers và body; **Amazon S3** gửi thông báo về một object trong bucket; **Amazon SQS** gửi một batch gồm nhiều message với body và metadata riêng. Muốn xử lý chính xác, cần hiểu **cấu trúc event envelope**, chọn kiểu Java thích hợp và xác định ranh giới chuyển đổi trước khi gọi logic nghiệp vụ.

Bài học thuộc chương **AWS Lambda**. Ta sẽ phân tích ba loại event, triển khai các bean Spring Cloud Function dùng **FunctionInvoker** và **FunctionCatalog**, xử lý API Gateway payload 1.0/2.0, giải mã S3 object key, xử lý SQS batch và partial failures, rồi cấu hình AWS SAM, kiểm thử và chẩn đoán lỗi. Các ví dụ dùng Java 17+ và hướng tiếp cận **Spring Boot 3.x/Jackson 2**; nếu dùng thế hệ thư viện khác, cần đối chiếu API/serializer với BOM tương thích của dự án.

## 1. Phân biệt payload nghiệp vụ với AWS event envelope

Hãy giả sử nghiệp vụ nhận lệnh báo giá:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 2
}
~~~

Đây là **payload nghiệp vụ**. Khi đi qua AWS, nó có thể nằm ở vị trí khác nhau:

| Nguồn kích hoạt | Đơn vị AWS đưa tới Lambda | Vị trí payload nghiệp vụ | Hành vi phản hồi |
| --- | --- | --- | --- |
| **API Gateway proxy** | Một HTTP request event | Thường là chuỗi **body** trong event | Lambda trả response cho HTTP client theo payload format |
| **S3 notification** | Một thông báo có **Records** | Không có nội dung file; chỉ bucket/key/metadata | Invocation bất đồng bộ; output không phải HTTP response |
| **SQS trigger** | Một event có **Records** batch | Mỗi **record.body** thường là một message string | Lambda/poller quyết định xóa hoặc giao lại message dựa trên kết quả xử lý |

~~~mermaid
flowchart TD
    A["Nguồn AWS"] --> B{"Loại event"}
    B --> C["API Gateway envelope"]
    B --> D["S3 notification"]
    B --> E["SQS batch"]
    C --> F["Trích/giải mã body"]
    D --> G["Đọc bucket + URL-decode key"]
    E --> H["Duyệt Records, parse từng body"]
    F --> I["DTO nghiệp vụ"]
    G --> J["Object reference / S3 client"]
    H --> K["DTO từng message"]
    I --> L["Function nghiệp vụ"]
    J --> L
    K --> L
~~~

**FunctionInvoker không đồng nghĩa một công cụ tự hiểu mọi loại envelope**. Adapter AWS nhận stream invocation và cố chuyển sang kiểu T đã khai báo, hoặc truyền nguyên **InputStream** nếu Function nhận kiểu đó. Để bóc một HTTP body, phân biệt S3 key với file bytes hay xử lý từng record SQS, đôi khi cần thêm **adapter nghiệp vụ** của chính ứng dụng.

## 2. Kiến trúc nên dùng với Spring Cloud Function

Giữ phần lõi nhận và trả các kiểu Java độc lập AWS:

~~~java
public record QuoteRequest(
    String requestId,
    String sku,
    Integer quantity
) {}

public record QuoteResult(
    String requestId,
    String sku,
    int quantity,
    long subtotal
) {}
~~~

Ví dụ dịch vụ nghiệp vụ:

~~~java
public final class QuoteService {

    public QuoteResult quote(QuoteRequest request) {
        if (request == null
                || request.requestId() == null
                || request.requestId().isBlank()
                || request.sku() == null
                || request.sku().isBlank()
                || request.quantity() == null
                || request.quantity() < 1
                || request.quantity() > 1000) {
            throw new IllegalArgumentException(
                "Invalid quote request");
        }

        String sku = request.sku()
            .trim().toUpperCase(java.util.Locale.ROOT);

        // Bảng giá minh họa: một SKU duy nhất.
        if (!"BOOK".equals(sku)) {
            throw new IllegalArgumentException("Unknown SKU");
        }

        long subtotal = Math.multiplyExact(
            85_000L, request.quantity());

        return new QuoteResult(
            request.requestId().trim(),
            sku,
            request.quantity(),
            subtotal);
    }
}
~~~

Từ đây, mỗi nguồn AWS có lớp điều hợp riêng:

~~~text
API Gateway event -> HTTP adapter -> QuoteRequest -> QuoteService
S3 event          -> S3 adapter   -> ObjectReference -> S3 processor
SQS batch         -> SQS adapter  -> từng Message DTO -> Message processor
~~~

**Không ép tất cả loại event vào một Function<Map<String, Object>, Object>** chỉ để giảm số bean. Làm vậy dễ đánh mất schema, khó kiểm thử hợp đồng và khiến logic nghiệp vụ phụ thuộc cấu trúc do AWS cung cấp. Khi cần hỗ trợ nhiều trigger, có thể tạo nhiều Lambda resources cùng dùng một shaded JAR, nhưng mỗi Lambda dùng **spring_cloud_function_definition** riêng.

## 3. Những dependency thường liên quan

Một ứng dụng Spring Cloud Function AWS cần adapter và các thư viện phù hợp với kiểu event:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-aws</artifactId>
    </dependency>

    <!-- Chỉ cần khai báo tường minh khi mã sử dụng lớp sự kiện AWS. -->
    <dependency>
        <groupId>com.amazonaws</groupId>
        <artifactId>aws-lambda-java-events</artifactId>
    </dependency>

    <!-- ObjectMapper dùng trong ví dụ Spring Boot 3 / Jackson 2. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây chỉ là **đoạn dependencies**, không phải POM hoàn chỉnh. Phiên bản Boot, Spring Cloud/Function, **aws-lambda-java-events** và Jackson cần được khóa/quản lý tương thích theo build. Không tự ghép những bản mới nhất không thuộc cùng tổ hợp đã được kiểm tra.

**aws-lambda-java-events** cung cấp những class như **S3Event**, **SQSEvent**, **SQSBatchResponse**. Nó khác với **AWS SDK for Java v2**: SDK được dùng khi bạn muốn gọi dịch vụ S3/SQS từ ứng dụng, còn classes sự kiện chỉ mô tả event mà Lambda nhận. Nếu không truy cập S3 object hoặc gọi AWS API, không cần thêm toàn bộ AWS SDK.

**Không cần spring-cloud-starter-function-web chỉ để xử lý API Gateway Lambda event.** Web starter điều hợp HTTP server Spring Cloud Function; API Gateway Lambda proxy và Spring Cloud Function AWS adapter là con đường triển khai khác. Với một ứng dụng Spring MVC cần giữ nhiều controller, có thể cân nhắc Serverless Java Container, nhưng đó không phải mô hình của bài này.

## 4. API Gateway: event không chỉ là HTTP body

API Gateway proxy integration ánh xạ HTTP request vào một Lambda invocation event. Hai kiểu phổ biến:

- **REST API proxy / payload 1.0**: thường có **httpMethod**, **path**, **headers**, **multiValueHeaders**, **queryStringParameters**, **multiValueQueryStringParameters**, **requestContext**, **body**, **isBase64Encoded**.
- **HTTP API / payload 2.0**: có **version=2.0**, **routeKey**, **rawPath**, **rawQueryString**, **requestContext.http.method**, **headers**, có thể có **cookies**, **body**, **isBase64Encoded**. Không dùng **multiValueHeaders** và **multiValueQueryStringParameters** giống v1.

| Yếu tố | API Gateway 1.0 | API Gateway 2.0 |
| --- | --- | --- |
| HTTP method | **httpMethod** | **requestContext.http.method** |
| URL path | **path** | **rawPath** |
| Query string | **queryStringParameters** và có thể **multiValueQueryStringParameters** | **rawQueryString** + **queryStringParameters** |
| Repeated headers | Có thể dùng **multiValueHeaders** | Duplicate values có thể được kết hợp bằng dấu phẩy |
| Cookie | Thường nằm trong headers | Có trường **cookies** riêng |
| HTTP body | **body** (String) | **body** (String) |
| Binary payload | **isBase64Encoded** | **isBase64Encoded** |
| Response | Proxy response có statusCode/body | Có thể trả proxy response tường minh hoặc một số output JSON được API Gateway suy diễn |

**Cùng một đường HTTP không đồng nghĩa cùng event schema.** Phải biết đang dùng REST API hay HTTP API và **payloadFormatVersion** nào. Không suy ra version chỉ từ tên API hoặc vị trí route.

### 4.1. Event REST API 1.0 rút gọn

~~~json
{
  "resource": "/quotes",
  "path": "/quotes",
  "httpMethod": "POST",
  "headers": {
    "content-type": "application/json"
  },
  "multiValueHeaders": {
    "x-request-tag": ["one", "two"]
  },
  "queryStringParameters": null,
  "requestContext": {
    "requestId": "api-req-001",
    "stage": "prod"
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2}",
  "isBase64Encoded": false
}
~~~

**body là chuỗi JSON lồng trong JSON event**. Nếu Java code deserialize toàn bộ object trên thành **QuoteRequest**, các field requestId/sku/quantity không nằm ở root tương ứng; việc conversion có thể thất bại hoặc tạo object rỗng, tùy mapper.

### 4.2. Event HTTP API 2.0 rút gọn

~~~json
{
  "version": "2.0",
  "routeKey": "POST /quotes",
  "rawPath": "/quotes",
  "rawQueryString": "",
  "headers": {
    "content-type": "application/json"
  },
  "requestContext": {
    "requestId": "api-req-002",
    "http": {
      "method": "POST",
      "path": "/quotes",
      "protocol": "HTTP/1.1"
    }
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2}",
  "isBase64Encoded": false
}
~~~

Trong thực tế có thể có nhiều trường bổ sung. Đừng viết parser chỉ chấp nhận đúng từng field của một ví dụ; dùng DTO ghi rõ những field cần thiết và quy tắc xử lý trường mới.

### 4.3. Đọc body và isBase64Encoded

Quy trình cho một HTTP API v2 adapter:

1. Kiểm tra **version**, route/method theo contract đã đăng ký.
2. Nhận **body**, xem **isBase64Encoded**.
3. Nếu true, Base64-decode body; nếu false, diễn giải chuỗi theo encoding được hỗ trợ (thường UTF-8 cho JSON).
4. Áp dụng giới hạn kích thước/content type và parse JSON sang DTO.
5. Validate DTO rồi gọi phần lõi nghiệp vụ.
6. Tạo **response envelope** có HTTP status và body đúng định dạng.

~~~mermaid
flowchart LR
    A["HTTP API v2 event"] --> B["body + isBase64Encoded"]
    B --> C["Decode bytes"]
    C --> D["QuoteRequest"]
    D --> E["QuoteService.quote"]
    E --> F["QuoteResult"]
    F --> G["Proxy HTTP response"]
~~~

**Không lấy HTTP status từ exception Java một cách tự động.** Khi dùng Lambda proxy, tầng adapter cần tạo response theo đúng payload format mà API Gateway mong đợi. Nếu chỉ trả DTO **QuoteResult**, HTTP API v2 có thể suy diễn response ở một số trường hợp; với REST API proxy v1, response không đúng schema có thể khiến API Gateway trả **502**.

## 5. Ví dụ Java: adapter HTTP API 2.0

Tệp **src/main/java/example/lambda/HttpApiApplication.java**. Đây là ví dụ Java 17+ theo **Jackson 2**; nếu dự án dùng Jackson 3, đổi package/API theo phiên bản hiện hành.

~~~java
package example.lambda;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import java.util.function.Function;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HttpApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpApiApplication.class, args);
    }

    // Chỉ chọn các field cần thiết của HTTP API v2 envelope.
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record HttpApiV2Event(
        String version,
        String routeKey,
        String rawPath,
        String body,
        Boolean isBase64Encoded
    ) {}

    public record QuoteRequest(
        String requestId,
        String sku,
        Integer quantity
    ) {}

    public record QuoteResult(
        String requestId,
        String sku,
        int quantity,
        long subtotal
    ) {}

    public record ApiError(
        String code,
        String message
    ) {}

    // Response envelope cho API Gateway proxy.
    public record ProxyResponse(
        int statusCode,
        Map<String, String> headers,
        String body,
        boolean isBase64Encoded
    ) {}

    public static final class QuoteService {

        public QuoteResult quote(QuoteRequest request) {
            if (request == null
                    || request.requestId() == null
                    || request.requestId().isBlank()
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() == null
                    || request.quantity() < 1
                    || request.quantity() > 1000) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            String sku = request.sku()
                .trim().toUpperCase(java.util.Locale.ROOT);

            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException(
                    "Unknown SKU");
            }

            return new QuoteResult(
                request.requestId().trim(),
                sku,
                request.quantity(),
                Math.multiplyExact(
                    85_000L,
                    request.quantity()));
        }
    }

    @Bean
    QuoteService quoteService() {
        return new QuoteService();
    }

    @Bean("httpQuoteV2")
    Function<HttpApiV2Event, ProxyResponse> httpQuoteV2(
            QuoteService service, ObjectMapper mapper) {

        return event -> {
            if (event == null
                    || !"2.0".equals(event.version())
                    || !"POST /quotes".equals(event.routeKey())
                    || event.body() == null) {
                return jsonResponse(mapper, 400,
                    new ApiError(
                        "BAD_ENVELOPE", "Invalid API event"));
            }

            try {
                byte[] body = Boolean.TRUE.equals(
                        event.isBase64Encoded())
                    ? Base64.getDecoder().decode(event.body())
                    : event.body().getBytes(StandardCharsets.UTF_8);

                // Giới hạn ứng dụng minh họa, không phải AWS limit.
                if (body.length > 64 * 1024) {
                    return jsonResponse(mapper, 413,
                        new ApiError(
                            "PAYLOAD_TOO_LARGE", "Body too large"));
                }

                QuoteRequest request =
                    mapper.readValue(body, QuoteRequest.class);

                QuoteResult result = service.quote(request);
                return jsonResponse(mapper, 200, result);

            } catch (java.io.IOException
                     | IllegalArgumentException ex) {
                return jsonResponse(mapper, 400,
                    new ApiError(
                        "INVALID_REQUEST",
                        "Quote request is invalid"));
            }
        };
    }

    private static ProxyResponse jsonResponse(
            ObjectMapper mapper, int status, Object payload) {
        try {
            return new ProxyResponse(
                status,
                Map.of("content-type", "application/json"),
                mapper.writeValueAsString(payload),
                false
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Could not serialize API response", ex);
        }
    }
}
~~~

Ví dụ này chỉ phục vụ **POST /quotes** với HTTP API payload **2.0**. Không khẳng định lớp record này deserialize được event REST API 1.0 hoặc một integration có mapping tùy biến.

### Vì sao output có body là String?

Một phản hồi proxy đúng dạng:

~~~json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2,\"subtotal\":170000}",
  "isBase64Encoded": false
}
~~~

Trường **body** là **JSON string** chứa kết quả nghiệp vụ đã được serialize. Trả trực tiếp một object con dưới field body có thể vi phạm hợp đồng proxy v1 và không nhất quán giữa các integration.

### Giới hạn của ví dụ

- Không có authentication/authorization. Production cần authorizer/IAM ở API Gateway hoặc cơ chế tương ứng và kiểm tra quyền nghiệp vụ.
- Không dùng HTTP headers làm bằng chứng bảo mật khi chưa được ranh giới tin cậy xác nhận.
- Lỗi parse/validation được ánh xạ về 400; chính sách 404/422 cho business rejection tùy API contract.
- Không bắt và biến mọi exception hạ tầng thành 400: lỗi bất ngờ nên đi qua cơ chế lỗi/quan sát có kiểm soát hoặc mapping 5xx phù hợp.
- Nếu cần nhiều route hay REST API 1.0, xây lớp điều hợp riêng hoặc dùng framework hỗ trợ proxy integration thích hợp.

## 6. API Gateway v1/v2: response và các bẫy thường gặp

| Tình huống | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Lấy field **httpMethod** từ event v2 | Field không tồn tại ở vị trí đó | Dùng **requestContext.http.method** hoặc routeKey |
| Xử lý repeated headers giống nhau ở v1/v2 | Mất thông tin đa giá trị | Đối chiếu multiValueHeaders/cookies/combined values |
| Parse toàn bộ envelope thành QuoteRequest | DTO thiếu field nghiệp vụ | Đọc **body** trước khi parse |
| Bỏ qua isBase64Encoded | Dữ liệu body bị hiểu sai | Decode theo flag, kiểm tra content type |
| Trả **QuoteResult** như response v1 | API Gateway có thể trả 502 | Tạo **statusCode/body** proxy response đúng |
| Tin field auth do client tự gửi | Bypass quyền | Dùng kết quả authorizer hoặc IAM đã được xác thực |
| Ghi log mọi headers/body | Lộ token, thông tin cá nhân | Chỉ log metadata tối thiểu có kiểm soát |

Với **HTTP API 2.0**, nếu Lambda trả JSON hợp lệ nhưng **không có statusCode**, API Gateway có thể suy diễn response 200 và content-type JSON. Đây là khả năng của **payload format 2.0**, không nên áp dụng máy móc cho REST API proxy 1.0. Nếu API cần status 400/404/422/500, nên trả proxy response rõ ràng và kiểm thử qua HTTP integration thực tế.

## 7. S3: hiểu Records và object reference

Khi object được tạo/xóa hoặc có sự kiện thuộc loại đã cấu hình, Amazon S3 có thể gửi **event notification** đến Lambda. Event chứa thông tin **sự kiện về object**, không chứa toàn bộ bytes của file trong bucket.

Một notification rút gọn:

~~~json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-southeast-1",
      "eventTime": "2026-01-15T08:00:00.000Z",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "sample-input-bucket"
        },
        "object": {
          "key": "incoming%2Freport+nov%2Bfinal.csv",
          "size": 256,
          "eTag": "sample-etag",
          "sequencer": "0066AABBCCDDEEFF"
        }
      }
    }
  ]
}
~~~

Từ event trên, các thông tin quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| **Records** | Danh sách record được gửi trong notification |
| **eventSource** | Phân biệt nguồn, ví dụ **aws:s3** |
| **eventVersion** | Version schema của S3 notification |
| **eventName** | Loại thao tác, ví dụ **ObjectCreated:Put** |
| **awsRegion** | Region của sự kiện/bucket |
| **s3.bucket.name** | Bucket chứa object |
| **s3.object.key** | Object key **được URL-encode** |
| **s3.object.size** | Kích thước object khi có field này |
| **s3.object.versionId** | Có thể có với bucket bật versioning |
| **s3.object.sequencer** | Phục vụ so sánh thứ tự một số sự kiện của **cùng một object key** |

### 7.1. Object key phải được giải mã đúng

S3 notification ghi object key theo kiểu **application/x-www-form-urlencoded**:

~~~text
Event key:
  incoming%2Freport+nov%2Bfinal.csv

Decoded key:
  incoming/report nov+final.csv
~~~

Trong Java:

~~~java
String decoded = java.net.URLDecoder.decode(
    encodedKey,
    java.nio.charset.StandardCharsets.UTF_8);
~~~

**URLDecoder** chuyển **+** thành khoảng trắng và **%2B** thành dấu cộng thật. Không giải mã hai lần vì có thể làm đổi key không mong muốn. Không dùng một bộ decode URI path thông thường nếu nó xử lý dấu **+** khác với form encoding mà S3 notification sử dụng.

### 7.2. S3 test event có hình dạng khác

Khi cấu hình event notification, Amazon S3 có thể gửi một test message dạng:

~~~json
{
  "Service": "Amazon S3",
  "Event": "s3:TestEvent",
  "Time": "2026-01-15T08:00:00.000Z",
  "Bucket": "sample-input-bucket",
  "RequestId": "sample-request-id"
}
~~~

**s3:TestEvent không có Records** như object-created notification. Nếu một Function chỉ khai báo **Function<S3Event, R>** và lập tức duyệt Records, test event có thể không map đúng hoặc bị từ chối. Nếu ứng dụng cần chấp nhận cả hai dạng, hãy thêm xử lý test event ở adapter InputStream/JsonNode hoặc kiểm tra schema trước khi dùng lớp S3Event.

### 7.3. Schema version và thứ tự thông báo

S3 notification schema đã có các version **2.x** khác nhau, và có thể bổ sung trường/loại event mới. Tài liệu AWS hướng dẫn kiểm tra major version phù hợp và chấp nhận minor version mới tương thích; không khóa parser vào việc phải đúng chuỗi **2.1**.

**S3 không bảo đảm mọi notification đến đúng thứ tự và không bị trùng**. Với các event create/delete có **sequencer**, chỉ so sánh sequencer khi chúng cùng chỉ tới **một object key**; không so sánh giữa các key khác nhau. VersionId hoặc sequencer có thể hỗ trợ idempotency/thứ tự theo yêu cầu nghiệp vụ, nhưng phải thiết kế kho trạng thái bền vững.

## 8. Ví dụ Spring Cloud Function với S3Event

**aws-lambda-java-events** cung cấp lớp **com.amazonaws.services.lambda.runtime.events.S3Event**. Function có thể nhận trực tiếp kiểu này khi adapter chuyển đổi thành công.

Tệp **src/main/java/example/lambda/S3EventFunctions.java**, đặt trong package được Spring Boot quét:

~~~java
package example.lambda;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.events.S3Event;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class S3EventFunctions {

    public record S3ObjectReference(
        String bucket,
        String key,
        String eventName,
        String versionId
    ) {}

    @Bean("inspectS3Notifications")
    Function<S3Event, List<S3ObjectReference>>
            inspectS3Notifications() {

        return event -> {
            if (event == null || event.getRecords() == null) {
                throw new IllegalArgumentException(
                    "S3 notification Records are required");
            }

            return event.getRecords().stream()
                .map(record -> {
                    if (record.getS3() == null
                            || record.getS3().getBucket() == null
                            || record.getS3().getObject() == null) {
                        throw new IllegalArgumentException(
                            "S3 bucket/object is missing");
                    }

                    String bucket =
                        record.getS3().getBucket().getName();

                    String key = decodeS3Key(
                        record.getS3().getObject().getKey());

                    return new S3ObjectReference(
                        bucket,
                        key,
                        record.getEventName(),
                        record.getS3().getObject().getVersionId()
                    );
                })
                .toList();
        };
    }

    public static String decodeS3Key(String encodedKey) {
        if (encodedKey == null || encodedKey.isBlank()) {
            throw new IllegalArgumentException("S3 key is missing");
        }

        return URLDecoder.decode(
            encodedKey, StandardCharsets.UTF_8);
    }
}
~~~

Function này **chỉ đọc metadata**, không tải file và không tạo side effect. Với event gồm nhiều Records, output là **List<S3ObjectReference>**; tuy nhiên phản hồi của Lambda được S3 kích hoạt bất đồng bộ thường không được dùng như response cho một HTTP client.

### Muốn đọc nội dung object thì sao?

Tách một lớp chuyên truy cập S3:

~~~java
public interface ObjectContentReader {
    java.io.InputStream open(String bucket, String key);
}
~~~

Implementation có thể dùng **AWS SDK for Java v2 S3Client** hoặc async client phù hợp, kèm quyền **s3:GetObject** cho đúng bucket/prefix. Khi dùng stream nội dung từ SDK, cần quản lý đóng stream và kích thước file. **InputStream của FunctionInvoker là stream của event**, không phải stream nội dung S3 object.

### Ngăn Lambda kích hoạt lặp vô hạn

Nếu một Lambda nhận **ObjectCreated** trên prefix **incoming/** rồi lại ghi output vào cùng prefix, output mới có thể tiếp tục kích hoạt Lambda. Giải pháp: dùng bucket khác hoặc cấu hình notification filter riêng cho input và output prefix, đồng thời quản lý idempotency.

## 9. SQS: một invocation chứa nhiều Records

Lambda dùng **event source mapping** để poll SQS queue. Khi có message, AWS gom một hoặc nhiều message thành **một invocation event**.

Ví dụ rút gọn:

~~~json
{
  "Records": [
    {
      "messageId": "msg-001",
      "receiptHandle": "sample-receipt-handle-1",
      "body": "{\"eventId\":\"EVT-001\",\"orderId\":\"ORD-101\"}",
      "attributes": {
        "ApproximateReceiveCount": "1"
      },
      "messageAttributes": {},
      "md5OfBody": "sample-md5",
      "eventSource": "aws:sqs",
      "eventSourceARN": "arn:aws:sqs:ap-southeast-1:123456789012:order-events",
      "awsRegion": "ap-southeast-1"
    },
    {
      "messageId": "msg-002",
      "receiptHandle": "sample-receipt-handle-2",
      "body": "{\"eventId\":\"EVT-002\",\"orderId\":\"ORD-102\"}",
      "attributes": {
        "ApproximateReceiveCount": "1"
      },
      "messageAttributes": {},
      "md5OfBody": "sample-md5",
      "eventSource": "aws:sqs",
      "eventSourceARN": "arn:aws:sqs:ap-southeast-1:123456789012:order-events",
      "awsRegion": "ap-southeast-1"
    }
  ]
}
~~~

Một số field được rút gọn hoặc mang giá trị mẫu; event thực có metadata tùy loại queue và cấu hình.

| Trường | Điều cần nhớ |
| --- | --- |
| **Records** | Một batch; không được coi là một message duy nhất |
| **messageId** | ID của SQS message; dùng để báo partial batch failure |
| **body** | String chứa nội dung ứng dụng, có thể là JSON hoặc dữ liệu khác |
| **attributes** | Metadata hệ thống, ví dụ receive count; FIFO có thông tin nhóm |
| **messageAttributes** | Attribute do producer đưa vào, khác JSON trong body |
| **eventSourceARN** | ARN của queue nguồn |
| **receiptHandle** | Dùng bởi API nhận/xóa message, không thay cho messageId trong batch failure response |

**Nếu producer gửi JSON OrderEvent vào SQS, nó nằm trong mỗi record.body dưới dạng String**. Đừng deserialize toàn bộ SQS event thành một OrderEvent duy nhất.

### 9.1. Batch và visibility timeout

Khi poller giao batch cho Lambda, các message trong batch bị ẩn trong khoảng **visibility timeout**. Nếu batch thành công, Lambda thường xóa các message được xử lý. Nếu invocation thất bại, các message có thể xuất hiện lại sau timeout và được gửi lại.

Kết quả là hệ thống phải chịu được **at-least-once processing**, không giả định mỗi message chỉ được xử lý một lần.

### 9.2. Standard và FIFO queue khác nhau

- **Standard SQS**: có thể có nhiều message đồng thời, thứ tự không được bảo đảm tuyệt đối; nên xử lý các record độc lập khi phù hợp.
- **FIFO SQS**: hỗ trợ thứ tự theo **MessageGroupId**; khi xử lý partial failures, AWS khuyến nghị dừng sau lỗi đầu tiên và báo thất bại cho cả những message chưa xử lý, nhằm giữ thứ tự.
- **BatchSize** và batching window có giới hạn khác nhau theo Standard/FIFO. Không sao chép một cấu hình batch lớn sang FIFO mà không kiểm tra giới hạn.

## 10. SQS partial batch response: cấu trúc chính xác

Giả sử một batch có ba message: **msg-001** hợp lệ, **msg-002** lỗi, **msg-003** hợp lệ. Nếu Function **ném exception** lên Lambda runtime, theo cơ chế mặc định **cả batch** có thể bị xem là thất bại và những message đã xử lý thành công cũng có thể được gửi lại.

Nếu bật tính năng **ReportBatchItemFailures**, Function có thể trả:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "msg-002"
    }
  ]
}
~~~

**itemIdentifier phải là SQS messageId**, không phải business eventId, orderId, receiptHandle hay S3 sequencer. Cần trả danh sách lỗi đúng với messageId thực có trong batch.

~~~mermaid
flowchart TD
    A["SQS batch: 001, 002, 003"] --> B["Xử lý từng record"]
    B --> C["001 thành công"]
    B --> D["002 thất bại"]
    B --> E["003 thành công"]
    C --> F["Partial batch response"]
    D --> F
    E --> F
    F --> G["batchItemFailures = [002]"]
    G --> H["AWS có thể retry 002"]
~~~

**Ba điều kiện để partial response có tác dụng:**

1. Event source mapping được cấu hình **FunctionResponseTypes: ReportBatchItemFailures**.
2. Function trả schema **batchItemFailures** chính xác và không ném exception ra ngoài cho toàn invocation.
3. Các record thành công thật sự đã xử lý xong theo business contract; nếu chỉ “nuốt” exception mà không báo lỗi, AWS có thể coi message đã xong.

Với FIFO, khi gặp lỗi, nên dừng xử lý tiếp và đưa **message thất bại cùng các message chưa xử lý** vào danh sách **batchItemFailures**. Nếu không bảo toàn quy tắc này, ứng dụng có thể phá vỡ kỳ vọng ordering của nhóm message.

## 11. Ví dụ Spring Cloud Function với SQSEvent và SQSBatchResponse

Tệp **src/main/java/example/lambda/SqsEventFunctions.java**:

~~~java
package example.lambda;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SqsEventFunctions {

    public record OrderEvent(
        String eventId,
        String orderId
    ) {}

    @Bean("validateSqsBatch")
    Function<SQSEvent, SQSBatchResponse> validateSqsBatch(
            ObjectMapper mapper) {

        return event -> {
            if (event == null || event.getRecords() == null) {
                throw new IllegalArgumentException(
                    "SQS Records are required");
            }

            List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

            // Ví dụ: chỉ validate JSON/schema của từng record.
            // Production cần gọi xử lý nghiệp vụ bền vững tại đây.
            for (SQSEvent.SQSMessage message : event.getRecords()) {
                try {
                    OrderEvent input = mapper.readValue(
                        message.getBody(),
                        OrderEvent.class);

                    validateOrderEvent(input);

                } catch (JsonProcessingException
                         | IllegalArgumentException ex) {
                    failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                            message.getMessageId()));
                }
            }

            return new SQSBatchResponse(failures);
        };
    }

    private static void validateOrderEvent(OrderEvent input) {
        if (input == null
                || input.eventId() == null
                || input.eventId().isBlank()
                || input.orderId() == null
                || input.orderId().isBlank()) {
            throw new IllegalArgumentException(
                "Invalid order event");
        }
    }
}
~~~

Ở ví dụ này, **xử lý thành công** chỉ có nghĩa **message JSON có cấu trúc hợp lệ**. Đây là **Lambda kiểm tra hợp đồng dữ liệu**, không phải consumer hoàn chỉnh để thanh toán hoặc cập nhật đơn hàng. Nếu áp dụng cho xử lý nghiệp vụ thực, phải gọi repository/service và hoàn tất tác dụng phụ **trước khi coi record thành công**.

### Nơi đặt xử lý nghiệp vụ trong production

~~~java
OrderEvent input = mapper.readValue(
    message.getBody(), OrderEvent.class);
validateOrderEvent(input);

// Cần triển khai service giao dịch/idempotent thật:
orderEventProcessor.applyOnce(input.eventId(), input.orderId());
~~~

Dòng **orderEventProcessor.applyOnce(...)** ở đây là **mẫu thiết kế**, chưa được định nghĩa trong ví dụ Java ở trên. Nó cần implementation với storage/giao dịch phù hợp; không thay bằng một HashSet singleton nếu cần chống trùng xuyên restart và nhiều Lambda execution environments.

Không bắt mọi **Throwable** để đánh dấu lỗi một record: các lỗi hệ thống nghiêm trọng hoặc lỗi hạ tầng có thể cần làm invocation thất bại để được xử lý theo chính sách sự cố. Khi triển khai production, phân loại rõ lỗi parse vĩnh viễn, từ chối nghiệp vụ và lỗi dịch vụ tạm thời; với record có thể recover, báo failure để retry đúng.

## 12. SQS FIFO: dừng khi gặp lỗi đầu tiên

Ví dụ **validateSqsBatch** ở trên phù hợp khi xử lý các record độc lập của **Standard queue** và muốn liệt kê mọi record sai. Khi dùng FIFO, thay đổi vòng lặp để giữ thứ tự:

~~~java
// Đoạn thay thế vòng lặp trong Function xử lý FIFO.
List<SQSBatchResponse.BatchItemFailure> failures =
    new java.util.ArrayList<>();

List<SQSEvent.SQSMessage> records = event.getRecords();

for (int i = 0; i < records.size(); i++) {
    SQSEvent.SQSMessage message = records.get(i);

    try {
        SqsEventFunctions.OrderEvent input =
            mapper.readValue(
                message.getBody(),
                SqsEventFunctions.OrderEvent.class);

        // Validation/business processing phải có contract rõ.
        if (input == null
                || input.eventId() == null
                || input.eventId().isBlank()
                || input.orderId() == null
                || input.orderId().isBlank()) {
            throw new IllegalArgumentException("Invalid event");
        }

    } catch (com.fasterxml.jackson.core.JsonProcessingException
             | IllegalArgumentException ex) {

        // Report record lỗi và tất cả record CHƯA xử lý.
        for (int j = i; j < records.size(); j++) {
            failures.add(
                new SQSBatchResponse.BatchItemFailure(
                    records.get(j).getMessageId()));
        }
        break;
    }
}

return new SQSBatchResponse(failures);
~~~

Đây là **đoạn thay thế trong ngữ cảnh đã có biến event, mapper và Function**, không phải một file Java độc lập. Điều quan trọng là **không xử lý các record phía sau khi đã có lỗi đầu tiên**; các ID chưa xử lý được trả về để Lambda không xóa chúng.

Nếu queue FIFO có nhiều message group, người triển khai vẫn phải kiểm tra chính sách ordering/parallelism theo **MessageGroupId**, event source mapping và yêu cầu nghiệp vụ. Cấu hình partial response **không thay idempotency**.

## 13. Đặc biệt: S3 event được chuyển qua SQS

Có hệ thống gửi S3 notifications tới SQS thay vì gọi Lambda trực tiếp. Khi đó Lambda nhận **SQS event**, không nhận **S3Event** ở lớp ngoài cùng:

~~~mermaid
flowchart LR
    A["S3 ObjectCreated"] --> B["SQS message body = S3 notification JSON"]
    B --> C["Lambda SQSEvent"]
    C --> D["record.body"]
    D --> E["Parse S3 notification"]
    E --> F["S3 object reference"]
~~~

Bản chất là **hai lớp envelope**:

~~~text
SQS batch Records
  -> SQSMessage.body (String)
      -> S3 notification JSON
          -> S3 Records
              -> bucket/key/eventName
~~~

Vì thế:

- Chữ ký Function bên ngoài thường là **Function<SQSEvent, SQSBatchResponse>**.
- Khi xử lý mỗi record, parse **message.getBody()** thành S3 notification JSON hoặc kiểu sự kiện tương ứng.
- Nếu một S3 notification chứa nhiều Records, phải tiếp tục duyệt các S3 Records.
- **Partial failure ID vẫn là SQS messageId**, không phải S3 event ID hoặc object sequencer.
- S3 test event không có Records, nên adapter cần phân biệt nếu queue có thể nhận nó.

Nếu sử dụng SNS giữa S3 và SQS, body có thể còn chứa **SNS envelope** (khi raw message delivery chưa bật). Cần xác định rõ topology nguồn event thay vì parse nhầm một lớp JSON vào lớp khác.

## 14. AWS SAM: ba Lambda với ba trigger riêng

Một cấu hình thực tế thường dễ quản trị khi API Gateway, S3 và SQS sử dụng **ba Lambda resources** với **function definition riêng**, dù có thể cùng dùng một shaded JAR.

Ví dụ **template.yaml** minh họa:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  InputBucket:
    Type: AWS::S3::Bucket

  OrderQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 180

  QuoteApiLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/event-app-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.HttpApiApplication
          spring_cloud_function_definition: httpQuoteV2
      Events:
        QuotesHttp:
          Type: HttpApi
          Properties:
            Path: /quotes
            Method: POST
            PayloadFormatVersion: "2.0"

  S3NotificationLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/event-app-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.HttpApiApplication
          spring_cloud_function_definition: inspectS3Notifications
      Events:
        ObjectCreated:
          Type: S3
          Properties:
            Bucket: !Ref InputBucket
            Events: s3:ObjectCreated:*
            Filter:
              S3Key:
                Rules:
                  - Name: prefix
                    Value: incoming/

  SqsBatchLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/event-app-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.HttpApiApplication
          spring_cloud_function_definition: validateSqsBatch
      Policies:
        - SQSPollerPolicy:
            QueueName: !GetAtt OrderQueue.QueueName
      Events:
        QueueEvents:
          Type: SQS
          Properties:
            Queue: !GetAtt OrderQueue.Arn
            BatchSize: 10
            FunctionResponseTypes:
              - ReportBatchItemFailures
~~~

**Cấu hình có tính minh họa** và giả định **S3EventFunctions** cùng **SqsEventFunctions** được Spring quét từ package của **HttpApiApplication**. **CodeUri phải trỏ tới shaded JAR thực có**, còn Runtime Java, Boot/Cloud version, artifact resource transformers và IAM policy phải được kiểm chứng theo dự án.

Những điểm cần chú ý:

1. **SAM S3 event** ở ví dụ này dùng bucket được định nghĩa **cùng template**; khi dùng bucket đã có từ trước, cách cấu hình notification/permission có thể khác.
2. **SQS event mapping** cần quyền poll queue cho Lambda execution role; ví dụ dùng **SQSPollerPolicy**. Nếu xử lý message rồi gọi AWS service khác, cần cấp quyền thêm theo nguyên tắc tối thiểu.
3. **FunctionResponseTypes** là cấu hình bắt buộc nếu muốn AWS diễn giải danh sách **batchItemFailures**.
4. **VisibilityTimeout=180** chỉ là minh họa để lớn hơn thời gian chạy tối đa của Lambda; khi sản xuất cần áp dụng hướng dẫn AWS về timeout, batching window, retry và DLQ.
5. S3 notification là invocation bất đồng bộ và có resource-based permission riêng; SAM có thể tạo phần tích hợp tương ứng, nhưng vẫn cần xác minh cấu hình sau deploy.
6. Không nên bật công khai API Gateway mà thiếu cơ chế authorization nếu business API cần bảo vệ.
7. Với sample, ba Lambda cùng có lớp Spring main **HttpApiApplication**, vì hai lớp cấu hình S3/SQS nằm trong cùng package quét. Nếu tách chúng sang application khác, cập nhật **MAIN_CLASS** theo code thật.

## 15. Kiểm thử FunctionCatalog và tên bean

FunctionCatalog giúp Spring Cloud Function tìm bean theo tên. Các Lambda trên cùng JAR có thể dùng:

~~~text
spring_cloud_function_definition=httpQuoteV2
spring_cloud_function_definition=inspectS3Notifications
spring_cloud_function_definition=validateSqsBatch
~~~

Khi dùng **FunctionInvoker** làm handler, **MAIN_CLASS/Start-Class** tìm Spring application, còn **definition** chọn một bean hoặc composition. Đừng nhầm tên bean với Lambda handler hoặc tên AWS resource.

Ví dụ test context:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = HttpApiApplication.class)
class AwsEventCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsAllThreeAdapters() {
        assertNotNull(catalog.lookup("httpQuoteV2"));
        assertNotNull(catalog.lookup("inspectS3Notifications"));
        assertNotNull(catalog.lookup("validateSqsBatch"));
    }
}
~~~

Test này cần tất cả classes cấu hình nằm trong component scan. Nó xác minh **bean registration**, không chứng minh event từ API Gateway/S3/SQS được deserialize chính xác bởi FunctionInvoker trong một runtime thật.

## 16. Unit test API Gateway adapter

Vì **httpQuoteV2** là Java Function, có thể kiểm tra JSON request/response mà không chạy AWS:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

class HttpApiAdapterTest {

    private final HttpApiApplication app =
        new HttpApiApplication();

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void handlesValidHttpApiV2Body() throws Exception {
        String body = """
            {"requestId":"REQ-101","sku":"BOOK","quantity":2}
            """;

        var event = new HttpApiApplication.HttpApiV2Event(
            "2.0", "POST /quotes", "/quotes",
            body, false);

        var reply = app.httpQuoteV2(
            app.quoteService(), mapper).apply(event);

        assertEquals(200, reply.statusCode());
        assertEquals(
            "application/json",
            reply.headers().get("content-type"));
        assertTrue(reply.body().contains("170000"));
    }

    @Test
    void rejectsWrongRoute() {
        var event = new HttpApiApplication.HttpApiV2Event(
            "2.0", "GET /quotes", "/quotes",
            "{}", false);

        var reply = app.httpQuoteV2(
            app.quoteService(), mapper).apply(event);

        assertEquals(400, reply.statusCode());
    }
}
~~~

Test này xác minh logic **sau khi HttpApiV2Event đã được tạo**. Cần thêm integration test deserialize **JSON event đầy đủ** (bao gồm requestContext, headers) sang record, kiểm thử base64 body, JSON lỗi và status/headers ngoài API Gateway.

## 17. Unit test S3 key decoding

Dù chưa kết nối S3 thật, vẫn cần kiểm tra giải mã key:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class S3KeyDecodingTest {

    @Test
    void decodesFormEncodedObjectKey() {
        String key = S3EventFunctions.decodeS3Key(
            "incoming%2Freport+nov%2Bfinal.csv");

        assertEquals(
            "incoming/report nov+final.csv",
            key);
    }
}
~~~

Một integration test dùng event S3 thực cần kiểm tra **S3Event.getRecords()**, eventVersion, eventName và versionId khi có. Với event **s3:TestEvent**, phải có test riêng vì schema khác.

Nếu bổ sung AWS SDK **GetObject**, hãy mock client trong unit test và chỉ chạy integration test với bucket/role được cấu hình cho test, không dùng bucket production.

## 18. Unit test SQS partial failures

Có thể tạo **SQSEvent** và các **SQSMessage** ngay trong unit test của Function:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SqsBatchTest {

    @Test
    void returnsOnlyInvalidMessageIds() {
        var valid = new SQSEvent.SQSMessage();
        valid.setMessageId("msg-001");
        valid.setBody("""
            {"eventId":"EVT-001","orderId":"ORD-101"}
            """);

        var invalid = new SQSEvent.SQSMessage();
        invalid.setMessageId("msg-002");
        invalid.setBody("""
            {"eventId":"","orderId":"ORD-102"}
            """);

        var batch = new SQSEvent();
        batch.setRecords(List.of(valid, invalid));

        var fn = new SqsEventFunctions()
            .validateSqsBatch(new ObjectMapper());

        var response = fn.apply(batch);

        assertEquals(1, response.getBatchItemFailures().size());
        assertEquals(
            "msg-002",
            response.getBatchItemFailures()
                .get(0).getItemIdentifier());
    }
}
~~~

Test này xác minh mã Java tạo **batchItemFailures** theo message ID. Nhưng **không chứng minh AWS sẽ retry đúng record** nếu event source mapping chưa bật **ReportBatchItemFailures**. Cần thêm integration test hoặc kiểm tra cấu hình SAM/CloudFormation của Lambda thực tế.

## 19. Ba dạng lỗi: không xử lý giống nhau

| Dạng lỗi | Ví dụ | Chính sách phù hợp |
| --- | --- | --- |
| **Conversion / schema** | API Gateway body JSON hỏng; SQS body thiếu trường | Từ chối theo error contract, quarantine/DLQ khi cần |
| **Business rejection** | SKU không tồn tại; event đã xử lý; object không phù hợp | Quyết định idempotent/no-op hay result từ chối rõ ràng |
| **Transient infrastructure** | S3 GetObject timeout; database mất kết nối | Retry có giới hạn, backoff, observability |

### API Gateway

Một payload sai nên thường dẫn tới HTTP **400**; lỗi hệ thống có thể map **5xx**. Nếu dùng proxy integration, Lambda phải tạo response có đúng **statusCode/body** thay vì chỉ ném exception rồi hy vọng client nhận lỗi đã chuẩn hóa.

### S3

S3 thường gọi Lambda **bất đồng bộ**. Nếu xử lý thất bại, retry/destination/DLQ và số lần thử lại tùy cơ chế AWS asynchronous invocation đang cấu hình. S3 notification có thể trùng hoặc không đúng thứ tự; processor cần idempotency và chiến lược chống vòng lặp.

### SQS

SQS trigger dùng event source mapping poll queue; message có thể được giao lại. Khi sử dụng partial batch response, mỗi failure phải được báo bằng **messageId**. Với FIFO phải xét ordering; với dữ liệu sai vĩnh viễn cần chính sách DLQ/quarantine để tránh retry mãi.

## 20. Bảo mật và quan sát

- **Đừng tin requestContext/headers từ JSON gửi qua direct invoke** như bằng chứng đã xác thực. Chỉ tin metadata sau khi xác minh nguồn và ranh giới quyền.
- **Không log toàn bộ API headers hoặc body**; có thể chứa Authorization, cookie, PII.
- **Không giải mã S3 key hai lần**; key là định danh object, không phải URL path mà bạn tự ghép tùy ý.
- **Không cấp quyền s3:GetObject cho mọi Lambda** khi chỉ có Lambda xử lý S3 thực sự cần.
- **Không dùng receiptHandle làm idempotency key nghiệp vụ**; chọn eventId/business key ổn định ở storage.
- **Không ghi payload SQS lỗi vô hạn vào log**; dùng error code, messageId và correlation ID phục vụ truy vết.
- **Giới hạn JSON size và parser nesting**, đặc biệt khi unwrapping API Gateway body hoặc SQS body.
- **Không coi S3 eTag luôn là MD5 của nội dung**; multipart upload/encryption làm giả định này không luôn đúng.
- **Không coi Function bean singleton là kho lưu trạng thái liên Lambda**; mỗi execution environment có bộ nhớ riêng.

Một bộ log/metrics hữu ích nên phân biệt **eventSource**, **Lambda function/version**, **record/message ID**, **outcome**, **duration** và mã lỗi mà không lộ thông tin nhạy cảm.

## 21. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **FunctionInvoker ClassNotFound** | JAR sai layout hoặc thiếu adapter | Kiểm tra shaded JAR, handler |
| FunctionCatalog không tìm thấy bean | Sai definition hoặc package scan | Kiểm tra @Bean, MAIN_CLASS, catalog |
| API v2 báo field **httpMethod** null | Đọc kiểu v1 trên event v2 | Dùng requestContext.http.method/routeKey |
| API trả **502 Bad Gateway** | Response không đúng proxy format | Kiểm tra statusCode/body, payload version |
| JSON body không parse | Chưa bóc/giải mã body hoặc schema sai | Đọc isBase64Encoded, parse đúng lớp |
| S3 key có dấu **+** lạ | Chưa form URL-decode | URLDecoder UTF-8 một lần |
| S3 notification không có Records | Nhận **s3:TestEvent** | Phân nhánh theo schema |
| Lambda tưởng S3 event chứa file bytes | Nhầm notification với object | Dùng S3 GetObject và IAM |
| S3 ghi output tự kích hoạt vô hạn | Bucket/prefix notification trùng đầu ra | Dùng prefix/bucket khác |
| S3 event tới sai thứ tự | Notification at-least-once/out-of-order | Idempotency và sequencer per object |
| SQS chỉ xử lý một message | Không duyệt Records | Duyệt toàn bộ batch |
| SQS body thành raw string | Chưa parse JSON bên trong body | Deserialize từng message.body |
| Partial failure không có tác dụng | Chưa bật ReportBatchItemFailures | Kiểm tra event source mapping |
| Partial response bị coi batch thất bại | itemIdentifier rỗng/sai ID hoặc output sai | Dùng messageId có trong batch |
| FIFO bị xử lý sai thứ tự | Sau record lỗi vẫn xử lý tiếp | Dừng và báo cả các record chưa xử lý |
| Giao lại gây ghi dữ liệu trùng | Thiếu idempotency | Unique key, transaction/outbox |
| SQS có body là S3 event nhưng code mong OrderEvent | Event envelope lồng nhiều lớp | Parse SQS body thành S3 notification trước |

## 22. Bài tập thực hành

**Bài tập 1 — So sánh envelope.** Cho ba payload API Gateway 2.0, S3 ObjectCreated và SQS batch. Với mỗi payload, chỉ ra điểm nào là metadata AWS, điểm nào là payload nghiệp vụ và bean Function nên nhận kiểu gì.

**Bài tập 2 — API Gateway v1/v2.** Viết bảng ánh xạ method/path/headers/body giữa REST API proxy v1 và HTTP API v2. Thiết kế hai DTO adapter hoặc một chiến lược phân nhánh có kiểm thử version.

**Bài tập 3 — HTTP error response.** Mở rộng **httpQuoteV2** để xử lý body thiếu, Base64 sai, quantity 0, SKU lạ và lỗi hạ tầng. Mỗi trường hợp phải có status/error code theo contract.

**Bài tập 4 — S3 URL encoding.** Tính kết quả giải mã key **a+b%2Bc%2Fd.csv**. Viết unit test cho dấu cộng, khoảng trắng, Unicode và ký tự percent; giải thích vì sao chỉ decode một lần.

**Bài tập 5 — S3 test event.** Thiết kế một adapter có thể phân biệt **s3:TestEvent** với notification **Records**. Với test event, hãy quyết định có log rồi bỏ qua hay báo lỗi, và giải thích ảnh hưởng tới retry.

**Bài tập 6 — S3 version và idempotency.** Khi cùng object key có hai event create/delete đến ngược thứ tự, đề xuất kho trạng thái và cách dùng **sequencer** theo object key. Không so sánh sequencer giữa các key khác nhau.

**Bài tập 7 — SQS partial failures.** Một batch có messageId **a**, **b**, **c**; **b** không hợp lệ. Viết JSON response của Standard queue khi chỉ b lỗi, rồi response của FIFO queue khi dừng từ b trở đi.

**Bài tập 8 — S3 → SQS.** Vẽ cấu trúc hai lớp **SQS Records → SQS body → S3 Records**. Chỉ ra ID nào đặt trong **batchItemFailures** khi parse S3 body lỗi.

**Bài tập 9 — SAM deployment.** Tạo ba Lambda với cùng shaded JAR nhưng definition khác nhau; thêm HTTP API v2, S3 ObjectCreated prefix và SQS trigger có ReportBatchItemFailures. Giải thích IAM riêng của từng resource.

**Bài tập 10 — Kiểm thử ranh giới.** Tách unit tests cho QuoteService, S3 key decoder và SQS batch processor khỏi integration tests của FunctionInvoker, API Gateway, S3 event conversion và SQS event source mapping.

### Ghi nhớ

- **API Gateway, S3, SQS gửi những event envelope khác nhau**. Không coi event đầu vào luôn là DTO nghiệp vụ.
- **API Gateway v1/v2** khác vị trí method/path, headers và quy tắc response; body có thể là JSON string hoặc Base64.
- **S3 notification chỉ chứa metadata về object**. URL-decode key đúng một lần; không coi stream invocation là nội dung file; chú ý test event, trùng lặp và thứ tự.
- **SQS trigger gửi batch Records**. Parse **mỗi body**, thiết kế idempotency và dùng **messageId** cho **batchItemFailures** sau khi bật ReportBatchItemFailures.
- **FIFO cần giữ ordering**: khi có lỗi, dừng xử lý và báo lại các message chưa xử lý theo hướng dẫn AWS.
- **FunctionInvoker + FunctionCatalog** giữ logic nghiệp vụ độc lập giao thức; adapter chịu trách nhiệm trích xuất dữ liệu, conversion và phản hồi đúng contract của từng nguồn.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, S3Event, SQSEvent, SQSBatchResponse và conversion.
- [API Gateway — HTTP API Lambda proxy integrations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html): payload format 1.0/2.0 và response mapping.
- [API Gateway — REST API Lambda proxy integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html): request envelope và proxy response format.
- [Amazon S3 — Event notification message structure](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html): Records, key encoding, version, sequencer và test event.
- [AWS Lambda — S3 trigger](https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html): S3 event delivery, IAM và vòng lặp khi ghi cùng bucket.
- [AWS Lambda — SQS integration](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html): batch, visibility timeout, retry và idempotency.
- [AWS Lambda — SQS partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html): ReportBatchItemFailures, FIFO và itemIdentifier.
- [AWS SAM — SQS event](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-sqs.html): BatchSize và FunctionResponseTypes.
