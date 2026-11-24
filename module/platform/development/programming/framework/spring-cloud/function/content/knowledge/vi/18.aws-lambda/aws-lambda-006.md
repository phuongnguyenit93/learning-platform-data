# Chuyển đổi sự kiện thành POJO và truy cập InputStream nguyên bản

Khi triển khai **SPRING_CLOUD_FUNCTION** trên **AWS Lambda**, một sự kiện đến Lambda ban đầu là dữ liệu do runtime nhận từ nguồn gọi: direct invoke, API Gateway, SQS, S3 hoặc một trigger khác. **spring-cloud-function-adapter-aws** cung cấp **FunctionInvoker**, có thể đọc payload của invocation và **chuyển sang kiểu Java khai báo trong Function**. Vì vậy, bean **Function<OrderRequest, OrderResult>** có thể nhận một POJO có cấu trúc rõ ràng mà không phải tự đọc JSON. Ngược lại, khi cần xem hoặc xử lý các byte của event trước chuyển đổi, có thể khai báo **Function<InputStream, R>** để nhận **InputStream nguyên bản**.

Bài thuộc chương **AWS Lambda**, phân tích hai đường xử lý **typed POJO** và **raw InputStream**, cách phân biệt event envelope với payload nghiệp vụ, ví dụ Java 17+ hoàn chỉnh, giới hạn kiểu dữ liệu, xử lý lỗi, bảo mật, cấu hình FunctionInvoker, kiểm thử và những tình huống cần tự parse JSON. Mục tiêu là giữ logic **Supplier/Function/Consumer** tái sử dụng được qua HTTP, sự kiện hoặc serverless, đồng thời đặt trách nhiệm chuyển đổi ở ranh giới phù hợp.

## 1. Hai đường xử lý đầu vào trong FunctionInvoker

**FunctionInvoker** là handler chung của Spring Cloud Function trên AWS. Nó triển khai giao diện AWS **RequestStreamHandler**: runtime đưa vào một stream chứa payload invocation, một output stream và đối tượng context. Adapter khởi tạo Spring context, lấy bean từ **FunctionCatalog**, rồi chuẩn bị input theo kiểu đã khai báo.

~~~mermaid
flowchart TD
    A["AWS Lambda event bytes"] --> B["FunctionInvoker"]
    B --> C{"Kiểu input của bean?"}
    C -- "OrderRequest / POJO" --> D["Chuyển đổi JSON sang POJO"]
    C -- "InputStream" --> E["Chuyển stream gốc vào hàm"]
    D --> F["Function<OrderRequest, R>"]
    E --> G["Function<InputStream, R>"]
    F --> H["Output R"]
    G --> H
    H --> I["Adapter serialize response"]
~~~

Hai chữ ký tiêu biểu:

~~~java
Function<OrderRequest, OrderResult> validateOrder;
Function<InputStream, RawEventDigest> rawEventDigest;
~~~

| Tiêu chí | **Function<POJO, R>** | **Function<InputStream, R>** |
| --- | --- | --- |
| Đầu vào ứng dụng thấy | Một object Java đã được dựng | Stream byte của Lambda invocation |
| Ai thực hiện parse ban đầu? | Adapter/converter | Mã của bạn nếu cần |
| Hợp đồng nghiệp vụ | Rõ ràng qua kiểu T và các field | Cần quy định cách hiểu byte/format |
| Lỗi parse JSON | Thường xảy ra trước khi logic nghiệp vụ chạy | Xảy ra trong code nếu tự parse |
| Tác vụ phù hợp | Business DTO, sự kiện có schema ổn định | Kiểm tra raw envelope, chữ ký, định dạng đặc biệt, parse tùy chỉnh |
| Rủi ro chính | Type conversion, schema và nullability | Đọc stream một lần, bộ nhớ, encoding, bảo mật raw data |

Theo tài liệu Spring Cloud Function AWS, khi input là **InputStream**, adapter **không thực hiện bước chuyển đổi kiểu đầu vào** mà truyền stream cho function. Khi đầu vào khai báo là kiểu cụ thể như **OrderRequest**, adapter **cố gắng** chuyển event thành kiểu đó. Từ “cố gắng” quan trọng: conversion phụ thuộc schema, converter, kiểu Java và phiên bản thư viện.

## 2. Ba khái niệm không được đánh đồng

Cần phân biệt:

1. **Lambda invocation payload:** toàn bộ JSON document (hoặc dữ liệu do runtime đưa vào stream) của một lần gọi Lambda.
2. **Event envelope:** cấu trúc mà nguồn AWS tạo ra, ví dụ trường **body** của API Gateway, **Records** của SQS hoặc **detail** của EventBridge.
3. **Payload nghiệp vụ:** các trường thực sự cần cho Function, ví dụ **requestId**, **sku**, **quantity**.

Ví dụ khi gọi Lambda trực tiếp:

~~~json
{
  "requestId": "REQ-101",
  "sku": "book",
  "quantity": 2
}
~~~

Ở đây toàn bộ JSON document có thể chính là payload nghiệp vụ, nên **Function<OrderRequest, OrderResult>** là lựa chọn tự nhiên.

Nhưng API Gateway HTTP API có thể gửi một event rút gọn như sau:

~~~json
{
  "version": "2.0",
  "routeKey": "POST /orders",
  "rawPath": "/orders",
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"requestId\":\"REQ-101\",\"sku\":\"book\",\"quantity\":2}",
  "isBase64Encoded": false
}
~~~

Lúc này **body là chuỗi JSON nằm bên trong một JSON object khác**. Raw InputStream nhận **event envelope**, không tự biến thành byte của trường body. Còn một Function nhận **OrderRequest** cần converter/adapter phù hợp để chọn và parse đúng nội dung. Không mặc định mọi event source và mọi phiên bản adapter đều tự unwrap envelope giống nhau.

~~~mermaid
flowchart LR
    A["API Gateway event"] --> B["Envelope gồm body, headers, metadata"]
    B --> C["Adapter đọc/giải mã body"]
    C --> D["OrderRequest"]
    D --> E["Hàm nghiệp vụ"]
~~~

**Quy tắc:** chọn kiểu đầu vào dựa vào **đơn vị dữ liệu do Lambda thực sự nhận**, không chỉ dựa vào JSON body mà bạn mong đợi từ frontend.

## 3. POJO là gì trong bài toán event conversion?

**POJO (Plain Old Java Object)** là object Java thông thường, không buộc phải kế thừa lớp AWS hay Spring. Với các mapper JSON dựa trên Jackson, một JavaBean có constructor không tham số cùng getter/setter là hình thức dễ hiểu để minh họa conversion.

Ví dụ:

~~~java
public static final class OrderRequest {
    private String requestId;
    private String sku;
    private Integer quantity;

    public OrderRequest() {
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

**Java record** cũng là một kiểu DTO phù hợp khi phiên bản serializer hỗ trợ record. Nhưng không nhất thiết mọi POJO phải là record, và không phải mọi phiên bản mapper đều xử lý constructor/record/immutable classes theo cùng cách.

Tại sao dùng **Integer quantity** thay vì **int**? Vì một trường JSON bị thiếu có thể để lại **null**, giúp hàm phân biệt rõ **thiếu trường** với **quantity = 0**. Đây là một quyết định về hợp đồng; không thay thế việc kiểm tra điều kiện nghiệp vụ.

### Các ràng buộc thuộc hợp đồng, không thuộc parser

| Trường | Kiểu Java | Kiểm tra cần có |
| --- | --- | --- |
| **requestId** | String | Có giá trị, không blank, giới hạn độ dài |
| **sku** | String | Không blank, chuẩn hóa nhất quán, định dạng cho phép |
| **quantity** | Integer | Không null, nằm trong khoảng nghiệp vụ |
| **result.status** | String/enum | Ý nghĩa trạng thái rõ, không nhập nhằng với AWS invocation status |

Converter giúp tạo object Java; **nó không tự xác minh tất cả bất biến nghiệp vụ**. Thêm validation annotation cũng không bảo đảm mọi adapter tự kích hoạt validator trước khi gọi **apply(...)**. Với bất biến bắt buộc, validation phải được bảo đảm ở tầng nghiệp vụ hoặc một lớp validation được dùng nhất quán.

## 4. Ứng dụng Java 17+: hai bean, hai cách nhận event

Ví dụ sau dùng Spring Boot để tạo hai Function:

- **validateOrder** nhận một **OrderRequest** POJO đã được chuyển đổi từ event.
- **rawEventDigest** nhận **InputStream** nguyên bản và trả về số byte cùng SHA-256 digest của payload invocation.

Hai bean có cùng chức năng minh họa đường đi AWS, nhưng **khác hợp đồng đầu vào**. Ví dụ không thực sự ghi đơn hàng vào database.

Tệp **src/main/java/example/lambda/LambdaEventApplication.java**:

~~~java
package example.lambda;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LambdaEventApplication {

    private static final int MAX_EVENT_BYTES = 1_048_576;

    public static void main(String[] args) {
        SpringApplication.run(LambdaEventApplication.class, args);
    }

    // JavaBean POJO dùng cho JSON input.
    public static final class OrderRequest {
        private String requestId;
        private String sku;
        private Integer quantity;

        public OrderRequest() {
        }

        public String getRequestId() {
            return requestId;
        }

        public void setRequestId(String requestId) {
            this.requestId = requestId;
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    // Kết quả validation, không phải xác nhận đã lưu order.
    public record OrderValidation(
        String requestId,
        String sku,
        int quantity,
        String status
    ) {}

    // Kết quả không chứa raw event để tránh lộ payload.
    public record RawEventDigest(
        int byteCount,
        String sha256
    ) {}

    @Bean("validateOrder")
    Function<OrderRequest, OrderValidation> validateOrder() {
        return request -> {
            if (request == null
                    || request.getRequestId() == null
                    || request.getRequestId().isBlank()
                    || request.getSku() == null
                    || request.getSku().isBlank()
                    || request.getQuantity() == null
                    || request.getQuantity() < 1
                    || request.getQuantity() > 1000) {
                throw new IllegalArgumentException(
                    "Invalid order request");
            }

            String requestId = request.getRequestId().trim();
            String sku = request.getSku()
                .trim().toUpperCase(Locale.ROOT);

            return new OrderValidation(
                requestId, sku, request.getQuantity(), "VALID");
        };
    }

    @Bean("rawEventDigest")
    Function<InputStream, RawEventDigest> rawEventDigest() {
        return input -> {
            // Bounded read: tránh đọc vô hạn vào bộ nhớ.
            byte[] bytes;
            try {
                bytes = input.readNBytes(MAX_EVENT_BYTES + 1);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                    "Unable to read invocation input", ex);
            }

            if (bytes.length > MAX_EVENT_BYTES) {
                throw new IllegalArgumentException(
                    "Invocation payload exceeds demo limit");
            }

            try {
                MessageDigest sha256 =
                    MessageDigest.getInstance("SHA-256");

                String hex = HexFormat.of().formatHex(
                    sha256.digest(bytes));

                return new RawEventDigest(bytes.length, hex);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(
                    "SHA-256 provider unavailable", ex);
            }
        };
    }
}
~~~

**Các điều cần chú ý khi sao chép:**

- **InputStream** thuộc **java.io**, không phải một interface do Spring Cloud Function định nghĩa.
- **readNBytes(MAX + 1)** chỉ lấy tối đa **1 MiB + 1 byte**, sau đó từ chối nếu quá giới hạn minh họa. Điều này tránh việc dùng **readAllBytes()** không giới hạn với payload không tin cậy.
- SHA-256 digest ở đây dùng để nhận diện byte trong **demo**, không phải chữ ký xác thực hoặc cơ chế bảo vệ tính toàn vẹn trước đối thủ. Một hash đơn thuần không chứng minh ai đã gửi event.
- Mã **rawEventDigest** không lưu stream vào field, không giữ stream cho invocation sau, không in raw bytes ra log và không tự đóng stream thuộc runtime adapter.
- Ví dụ **validateOrder** trả **VALID**, không phải **ORDER_CREATED**: nó mới chỉ kiểm tra dữ liệu, chưa ghi database hay tạo tác dụng phụ.
- Những kiểu output record cần serializer hỗ trợ và phải được kiểm thử trên phiên bản Spring/Jackson thực tế.

Nếu cần chặn payload sớm hơn để giảm chi phí, nên kết hợp cấu hình giới hạn từ nguồn gọi, API Gateway hoặc tầng tiếp nhận phù hợp. Giới hạn trong Function là **hàng phòng vệ bổ sung**, không thay thế giới hạn hạ tầng.

## 5. Lời gọi POJO: JSON được đưa vào OrderRequest thế nào?

Trong ví dụ, bean **validateOrder** khai báo:

~~~java
@Bean("validateOrder")
Function<OrderRequest, OrderValidation> validateOrder() { ... }
~~~

Khi AWS Lambda dùng **FunctionInvoker** và định nghĩa được chọn là **validateOrder**, adapter dựa trên kiểu input **OrderRequest** để cố gắng chuyển payload JSON của invocation thành object.

~~~text
Lambda invocation JSON
  -> FunctionInvoker InputStream
  -> message/conversion layer
  -> OrderRequest POJO
  -> validateOrder.apply(request)
  -> OrderValidation
  -> serialized Lambda output
~~~

Với direct invocation:

~~~json
{
  "requestId": "REQ-101",
  "sku": "book",
  "quantity": 2
}
~~~

Đầu ra nghiệp vụ dự kiến:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 2,
  "status": "VALID"
}
~~~

**Không cần gọi ObjectMapper thủ công trong validateOrder** nếu adapter đã tạo đúng OrderRequest. Điều này giúp code nghiệp vụ dễ unit test và dễ sử dụng lại qua một adapter khác cũng cung cấp OrderRequest.

Tuy nhiên, nếu event không phải JSON object đúng schema, parser có thể thất bại **trước khi** Function chạy. Ví dụ gửi một JSON array hoặc trường quantity là một object:

~~~json
{
  "requestId": "REQ-102",
  "sku": "BOOK",
  "quantity": { "value": 2 }
}
~~~

Đây là vấn đề **deserialization/type conversion**, khác với JSON có **quantity = 0** (đúng kiểu Integer nhưng vi phạm điều kiện nghiệp vụ).

## 6. Lời gọi InputStream: nhận byte nguyên bản

Bean **rawEventDigest** khai báo:

~~~java
@Bean("rawEventDigest")
Function<InputStream, RawEventDigest> rawEventDigest() { ... }
~~~

Trong đường AWS Lambda mà tài liệu mô tả, Spring Cloud Function **bỏ qua bước convert input** và truyền stream trực tiếp vào hàm.

~~~text
Lambda event JSON bytes
  -> RequestStreamHandler của FunctionInvoker
  -> InputStream ban đầu
  -> rawEventDigest.apply(stream)
  -> bounded read + SHA-256
  -> RawEventDigest
  -> output serialization
~~~

**Ví dụ quan sát:** caller gửi đúng chuỗi byte UTF-8 của document:

~~~json
{"requestId":"REQ-101","sku":"book","quantity":2}
~~~

Hàm có thể tính số byte và SHA-256 trên chính document đó, bao gồm các ký tự **{**, **}**, dấu ngoặc kép, dấu hai chấm và khoảng trắng **nếu có trong payload thực tế**.

Nếu caller thêm xuống dòng ở cuối, đổi thứ tự field JSON hoặc thêm khoảng trắng không ảnh hưởng giá trị nghiệp vụ, **SHA-256 trên raw bytes vẫn thay đổi**. Đây là điểm khác biệt quan trọng giữa **raw-byte equivalence** và **semantic JSON equivalence**.

### Raw InputStream không phải những thứ sau

- **Không phải** nội dung file S3 mà event đang tham chiếu. S3 event thường cung cấp bucket/key; muốn đọc file cần S3 API và IAM.
- **Không mặc nhiên** là HTTP body được người dùng gửi qua API Gateway. Nó thường là cả Lambda event envelope có field **body**.
- **Không phải** stream vô hạn của một TCP connection; đó là stream của **một Lambda invocation**.
- **Không tự động** bỏ Base64 nếu event API Gateway chứa body với **isBase64Encoded=true**; việc hiểu event envelope và giải mã là trách nhiệm adapter/lớp xử lý.
- **Không phải** output stream của runtime. Hàm **Function<InputStream, R>** trả **R**; **FunctionInvoker** vẫn chịu trách nhiệm serialize R và ghi ra AWS **OutputStream**.

Nếu cần trực tiếp điều khiển output bytes, đó là một quyết định kiến trúc khác: tự triển khai handler **RequestStreamHandler** hoặc dùng cơ chế adapter đặc thù. Đừng nhầm việc nhận raw InputStream trong Function với việc tự sở hữu cả input/output streams của AWS handler.

## 7. Khi nào nên dùng InputStream thay vì POJO?

Một số nhu cầu hợp lý:

| Nhu cầu | Lựa chọn phù hợp | Giải thích |
| --- | --- | --- |
| Event JSON có schema cố định | **Function<POJO, R>** | Framework chuyển đổi, code nghiệp vụ typed |
| Cần kiểm tra raw payload bytes | **Function<InputStream, R>** | Bảo toàn cách biểu diễn byte ở đầu vào |
| Nguồn event có schema khác nhau | InputStream/Map hoặc adapter envelope | Tự xác định version/source, rồi map sang DTO |
| Cần xác minh HMAC/chữ ký trên raw payload | InputStream ở tầng điều hợp | Byte raw có thể quan trọng; còn cần khóa và so sánh an toàn |
| Nội dung nhập có định dạng không phải JSON thông thường | InputStream với parser phù hợp | Code tự chịu trách nhiệm format, giới hạn, lỗi |
| Event SQS/S3 có kiểu Java AWS chuẩn | **SQSEvent / S3Event** | Dùng các type từ thư viện AWS events |
| Chỉ cần đọc HTTP body trong API Gateway | Event adapter trích body | Không cần biến mọi business Function thành InputStream |

**Đừng chọn InputStream chỉ vì nghĩ nó luôn nhanh hơn POJO.** Bỏ converter ở adapter đồng nghĩa bạn phải tự parse, xử lý encoding, giới hạn và lỗi. Hiệu năng phải được đo trên workload thật; tính rõ ràng của hợp đồng thường có giá trị hơn việc tối ưu chưa có số liệu.

## 8. Tự deserialize InputStream thành POJO khi cần

Có những trường hợp cần đọc hoặc xác thực raw bytes trước rồi mới chuyển sang POJO. Lúc đó nên tách code thành hai bước:

~~~mermaid
flowchart LR
    A["InputStream"] --> B["Adapter giới hạn/kiểm tra raw bytes"]
    B --> C["JSON parser"]
    C --> D["OrderRequest POJO"]
    D --> E["Validation nghiệp vụ"]
    E --> F["OrderValidation"]
~~~

Ví dụ dùng **Jackson 2 API** (phù hợp những dự án Spring Boot 3.x sử dụng **com.fasterxml.jackson.databind.ObjectMapper**). Khi dùng Spring Boot/Jackson thế hệ khác, cần đối chiếu package và API theo dependency được khóa:

~~~java
package example.lambda;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.function.Function;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManualParsingConfiguration {

    @Bean("parseRawOrder")
    Function<InputStream, LambdaEventApplication.OrderValidation>
            parseRawOrder(
                ObjectMapper mapper,
                @Qualifier("validateOrder")
                Function<LambdaEventApplication.OrderRequest,
                         LambdaEventApplication.OrderValidation>
                    validator) {

        return input -> {
            try {
                LambdaEventApplication.OrderRequest request =
                    mapper.readValue(
                        input,
                        LambdaEventApplication.OrderRequest.class);

                return validator.apply(request);
            } catch (JsonProcessingException ex) {
                throw new IllegalArgumentException(
                    "Invalid JSON for OrderRequest", ex);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                    "Unable to read invocation input", ex);
            }
        };
    }
}
~~~

Ví dụ này giả định Spring đã đăng ký **ObjectMapper** phù hợp, dependency Jackson tương ứng có mặt và **ManualParsingConfiguration** nằm trong component scan. **parseRawOrder** là **bean bổ sung tùy chọn**, không phải bean có sẵn nếu bạn chỉ sao chép LambdaEventApplication ở phần 4.

Ở đây raw stream được Jackson đọc **một lần**, rồi validator nghiệp vụ xử lý POJO. Nếu cần tính hash và parse JSON **cùng một input**, không đọc toàn bộ stream hai lần: có thể đọc có giới hạn vào một byte array rồi dùng cùng array để tính hash và parse. Không giả định **InputStream.reset()** luôn được hỗ trợ.

**Giới hạn của snippet:** bản minh họa này chưa đặt giới hạn kích thước trước Jackson; trong hệ thống thực cần áp dụng bounded read, parser constraints và giới hạn của nguồn event. Nếu định dạng không phải JSON, thay Jackson bằng parser đúng loại nội dung, nhưng vẫn giữ nguyên nguyên tắc tách điều hợp với nghiệp vụ.

## 9. Sở hữu stream, đọc một lần và kiểm soát bộ nhớ

InputStream thường có tính chất **one-way**: đọc tiến tới cuối stream. Không nên dùng nó như một String bất biến có thể xử lý lại vô số lần.

### Những lỗi dễ gặp

~~~java
@Bean("brokenRawReader")
Function<InputStream, String> brokenRawReader() {
    return stream -> {
        // Lần đầu tiêu thụ hết input.
        String first;
        try {
            first = new String(
                stream.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);
        } catch (java.io.IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }

        // Lần đọc tiếp theo thường không còn byte.
        // Không có nghĩa event ban đầu rỗng!
        try {
            return first + " / remaining=" + stream.readAllBytes().length;
        } catch (java.io.IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }
    };
}
~~~

Vấn đề không chỉ là hiệu suất: khi input đã bị đọc hết, một parser phía sau có thể nhận stream rỗng và ném lỗi khó hiểu. Để inspect và parse trong cùng lời gọi, cần dùng **một lần đọc có kiểm soát**, hoặc stream tee/đánh dấu theo hợp đồng được hỗ trợ.

### Giới hạn dung lượng

Tránh dùng **readAllBytes()** khi payload không được giới hạn:

~~~java
byte[] event = stream.readAllBytes();
~~~

Đoạn này có thể cấp phát bộ nhớ lớn nếu dữ liệu nhiều hoặc không đáng tin cậy. Giải pháp minh họa:

~~~java
int limit = 1_048_576;
byte[] payload = stream.readNBytes(limit + 1);

if (payload.length > limit) {
    throw new IllegalArgumentException("Event too large");
}
~~~

Ví dụ này cần được đặt trong ngữ cảnh **try/catch IOException** hoặc method khai báo **throws IOException**. Giới hạn 1 MiB là **chính sách minh họa do ứng dụng chọn**, không phải giới hạn tối đa của AWS Lambda. Với dữ liệu lớn, cân nhắc streaming parser hoặc lưu dữ liệu ngoài Lambda payload (chẳng hạn S3), rồi truyền con trỏ đến dữ liệu.

### Ai đóng stream?

**RequestStreamHandler** thuộc runtime/adapter quản lý stream của invocation. Function nghiệp vụ nên đọc trong phạm vi lời gọi, không giữ stream vào field hoặc xử lý bất đồng bộ sau khi invocation kết thúc. Việc tự gọi **close()** trong một hàm nhận stream do adapter cấp phải được cân nhắc theo hợp đồng sở hữu; ví dụ ở phần 4 không chủ động đóng input.

Nếu bạn tự tạo **FileInputStream** trong code nghiệp vụ, quy tắc sở hữu khác: code mở file thường có trách nhiệm đóng file.

## 10. Character encoding và nội dung nhị phân

Để biến raw bytes thành text khi **biết chắc** định dạng là UTF-8:

~~~java
byte[] bytes = input.readNBytes(limit + 1);
String text = new String(
    bytes,
    java.nio.charset.StandardCharsets.UTF_8);
~~~

Đây là **giải mã text từ bytes**, không phải một JSON parser. Nếu chuỗi là:

~~~json
{"name":"Lan"}
~~~

thì biến **text** vẫn chứa dấu ngoặc, dấu ngoặc kép và ký tự escape của JSON; nó không tự biến thành Java object có field **name**.

Với dữ liệu nhị phân, không nên ép thành String theo UTF-8 rồi encode ngược và cho rằng bytes được bảo toàn. Dùng **byte[]**, **InputStream**, checksum hoặc parser nhị phân đúng định dạng.

API Gateway proxy event có **isBase64Encoded**; nếu body được base64-encode, adapter cần:

1. Đọc **body** string từ event envelope.
2. Kiểm tra **isBase64Encoded** và giải mã đúng khi true.
3. Kiểm tra content type/định dạng thật.
4. Parse các bytes đó thành dữ liệu nghiệp vụ.

Một Function nhận raw InputStream **không mặc nhiên thực hiện bốn bước** trên. Dựa vào mô hình event proxy và phiên bản adapter đang dùng, nên kiểm thử cả đường binary payload.

## 11. Không xác định được generic input type sẽ thế nào?

Spring Cloud Function dựa vào thông tin kiểu của Function để lựa chọn conversion. Tài liệu AWS nêu rằng nếu kiểu không biết rõ hoặc không xác định được, ví dụ **Function<?, ?>**, adapter có thể cố chuyển event thành một **Map** chung.

So sánh:

~~~java
Function<OrderRequest, OrderValidation>
Function<java.util.Map<String, Object>, String>
Function<Object, Object>
Function<InputStream, RawEventDigest>
~~~

| Kiểu input | Mức độ cụ thể | Hệ quả |
| --- | --- | --- |
| **OrderRequest** | Rõ schema | Conversion hướng tới POJO |
| **Map<String,Object>** | Linh hoạt | Người viết tự kiểm tra kiểu field |
| **Object / raw Function** | Thiếu schema | Converter có thể tạo Map hoặc biểu diễn chung |
| **InputStream** | Rõ ý định nhận bytes | Adapter bỏ convert input và truyền raw stream |

**Map không phải phương án tự động an toàn**. Ví dụ JSON number có thể thành Integer, Long hoặc loại số khác tùy mapper, JSON array thành List, nested object thành Map. Code ép kiểu trực tiếp như **(Integer) map.get("quantity")** có thể lỗi khi client hoặc mapper thay đổi.

Nếu schema ổn định, **POJO typed** giúp phát hiện sai hợp đồng sớm hơn, dễ viết test và dễ version API. Nếu event đa dạng, cân nhắc adapter envelope có trường **type/version** rồi chuyển về các DTO typed riêng thay vì đẩy một Map tùy ý xuyên toàn bộ hệ thống.

## 12. Những nguồn AWS có event envelope riêng

### 12.1. API Gateway

Event proxy thường có **body**, headers, request context và thông tin route. Raw InputStream đưa cho bạn toàn bộ JSON event. Nếu logic chỉ muốn **OrderRequest**, cần bóc và parse **body** thích hợp, đồng thời tạo output đúng contract API Gateway.

Với API Gateway proxy integration kiểu 1.0, response thường cần cấu trúc như:

~~~json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json"
  },
  "isBase64Encoded": false,
  "body": "{\"status\":\"VALID\"}"
}
~~~

**Body là một string** chứa JSON response. Với HTTP API payload 2.0, quy tắc inference response có thể khác và một số dạng output JSON thuần được hỗ trợ. Vì vậy không được khẳng định mọi API Gateway event đều cần cùng một wrapper; phải xem **integration type/payload version**.

### 12.2. SQS

SQS gửi một event có nhiều **Records**. Mỗi record thường chứa **body** string, messageId và attributes. Raw InputStream nhận JSON của **cả batch event**, không phải chỉ một message body.

Nếu muốn tận dụng lớp event AWS chuẩn, có thể dùng:

~~~java
Function<
    com.amazonaws.services.lambda.runtime.events.SQSEvent,
    com.amazonaws.services.lambda.runtime.events.SQSBatchResponse>
        processSqs;
~~~

Đây là **chữ ký thiết kế**, không phải bean được đăng ký chỉ bằng khai báo biến. Dự án cần dependency **aws-lambda-java-events** tương ứng, triển khai xử lý từng record và cấu hình SQS event source mapping.

**Partial batch failure** không tự phát huy nếu chỉ trả một DTO tùy ý: trigger SQS phải bật **ReportBatchItemFailures**, và output phải khớp schema mà AWS yêu cầu. Nếu Function ném exception ra ngoài, cả batch có thể bị xem là thất bại. Cần thiết kế idempotency, retry và DLQ cho message.

### 12.3. S3

Một S3 event thường mô tả bucket, key và action. Nó **không chứa bytes của toàn bộ file được upload**. Nếu muốn xử lý nội dung file, code phải gọi S3 **GetObject** bằng SDK/client phù hợp và IAM permission. InputStream từ FunctionInvoker vẫn chỉ chứa **event notification payload**.

### 12.4. EventBridge và các nguồn khác

EventBridge thường gửi metadata như **source**, **detail-type**, **detail**, **id**. Nên quyết định Function cần nhận toàn bộ envelope hay chỉ **detail** đã được adapter trích xuất. Dù chọn cách nào, hãy ghi rõ schema, validation, version và error contract.

## 13. Chọn đúng bean trên Lambda

Vì ví dụ Java có **hai bean Function**, cần đặt function definition tường minh để tránh mơ hồ:

~~~text
spring_cloud_function_definition=validateOrder
~~~

hoặc:

~~~text
spring_cloud_function_definition=rawEventDigest
~~~

Handler AWS vẫn là:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Lớp ứng dụng:

~~~text
MAIN_CLASS=example.lambda.LambdaEventApplication
~~~

~~~mermaid
flowchart TD
    A["Một shaded JAR chứa cả hai bean"] --> B["Lambda validate-order"]
    A --> C["Lambda inspect-raw"]
    B --> D["definition = validateOrder"]
    C --> E["definition = rawEventDigest"]
    D --> F["FunctionInvoker + FunctionCatalog"]
    E --> F
~~~

Một JAR có thể dùng cho **hai Lambda resources khác nhau**, mỗi Lambda chọn một bean và có quyền IAM, memory/timeout hoặc trigger riêng. Không cần tự viết hai lớp **RequestStreamHandler** nếu **FunctionInvoker** đáp ứng yêu cầu.

**Đừng trộn FunctionCatalog lookup với handler.** Handler là entrypoint của AWS; **FunctionCatalog** giải quyết tên function trong Spring context. Bean có tên **validateOrder** không phải Java handler mà AWS tải trực tiếp.

## 14. AWS SAM minh họa cho POJO và raw stream

Ví dụ **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ValidateOrderLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/lambda-event-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.LambdaEventApplication
          spring_cloud_function_definition: validateOrder

  RawEventLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/lambda-event-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.LambdaEventApplication
          spring_cloud_function_definition: rawEventDigest
~~~

**CodeUri** là tên artifact minh họa: phải thay bằng **shaded JAR thực sự có sau build**. **java21** chỉ là runtime ví dụ; các lớp sử dụng API Java 17 và có thể được compile cho Java 17 nếu Spring Boot/Cloud Function version và Lambda runtime tương thích. Memory/Timeout không phải giá trị tối ưu cố định.

Theo tài liệu AWS adapter, ví dụ SAM có thể dùng handler là tên lớp **FunctionInvoker**; AWS Console cũng cho phép cú pháp **FunctionInvoker::handleRequest**. Giữ nhất quán với cấu hình và phiên bản runtime đã thử nghiệm.

### Dependency và packaging

Ứng dụng cần:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Cùng Spring Boot và bộ Spring Cloud/Function version tương thích, và build setup để tạo shaded JAR có **FunctionInvoker.class**, application class và metadata Spring.

**Đừng upload Boot executable JAR theo cấu trúc BOOT-INF mà không xác minh runtime classpath**. Với Java Lambda JAR thông thường, Spring Cloud Function AWS mẫu dùng shaded JAR. Dependency đủ chưa đồng nghĩa artifact đã đóng gói đúng.

## 15. Gọi thử hai Lambda bằng AWS CLI

Giả sử artifact đã deploy, credentials và IAM được cấu hình, lệnh direct invoke qua AWS CLI v2:

### 15.1. POJO conversion

~~~bash
aws lambda invoke --function-name validate-order --cli-binary-format raw-in-base64-out --payload '{"requestId":"REQ-101","sku":"book","quantity":2}' validation.json

cat validation.json
~~~

Kết quả nghiệp vụ mong đợi là **OrderValidation** với **status=VALID**. Kiểm tra JSON output, metadata CLI như **FunctionError** và CloudWatch logs.

### 15.2. Raw InputStream

~~~bash
aws lambda invoke --function-name inspect-raw --cli-binary-format raw-in-base64-out --payload '{"requestId":"REQ-101","sku":"book","quantity":2}' digest.json

cat digest.json
~~~

Kết quả nghiệp vụ là **RawEventDigest**:

~~~json
{
  "byteCount": 49,
  "sha256": "64 ký tự hex do SHA-256 tạo ra"
}
~~~

**Lưu ý:** với đúng chuỗi JSON ASCII ở lệnh direct invoke, không thêm khoảng trắng hoặc xuống dòng, payload dài **49 byte UTF-8**. Trường **sha256** trong JSON trên chỉ là chuỗi mô tả vị trí giá trị hash, **không phải SHA-256 thực**. Khi thực hành, phải đọc số byte và hash do Lambda thật tính; khác biệt whitespace/encoding sẽ thay đổi hash. Không sao chép chuỗi mô tả SHA-256 vào test assertion.

Các lệnh trên là hướng dẫn dành cho môi trường AWS thật, không phải thao tác được chạy trong bước viết tài liệu.

## 16. Unit test cho Function nhận POJO

Unit test POJO không yêu cầu Spring context, Lambda runtime hoặc JSON converter:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class LambdaEventPojoTest {

    private final LambdaEventApplication app =
        new LambdaEventApplication();

    @Test
    void acceptsValidOrder() {
        var input = new LambdaEventApplication.OrderRequest();
        input.setRequestId("REQ-101");
        input.setSku(" book ");
        input.setQuantity(2);

        var result = app.validateOrder().apply(input);

        assertEquals("REQ-101", result.requestId());
        assertEquals("BOOK", result.sku());
        assertEquals(2, result.quantity());
        assertEquals("VALID", result.status());
    }

    @Test
    void rejectsMissingQuantity() {
        var input = new LambdaEventApplication.OrderRequest();
        input.setRequestId("REQ-102");
        input.setSku("BOOK");

        assertThrows(IllegalArgumentException.class,
            () -> app.validateOrder().apply(input));
    }

    @Test
    void rejectsNullRequest() {
        assertThrows(IllegalArgumentException.class,
            () -> app.validateOrder().apply(null));
    }
}
~~~

Test này xác minh **logic validation và kết quả**. Nó **chưa chứng minh** JSON Lambda event được chuyển thành OrderRequest đúng vì test tự tạo POJO. Để kiểm tra converter, cần integration test ở adapter hoặc direct invocation với event JSON thật.

## 17. Unit test cho Function<InputStream, R>

Có thể tạo **ByteArrayInputStream** trong test để giả lập payload byte của một invocation:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class RawEventDigestTest {

    private final LambdaEventApplication app =
        new LambdaEventApplication();

    @Test
    void rawFunctionReadsBytesWithoutJsonConversion() {
        byte[] payload =
            "{\"requestId\":\"REQ-101\",\"sku\":\"BOOK\",\"quantity\":2}"
                .getBytes(StandardCharsets.UTF_8);

        var result = app.rawEventDigest().apply(
            new ByteArrayInputStream(payload));

        assertEquals(payload.length, result.byteCount());
        assertTrue(result.sha256().matches("[0-9a-f]{64}"));
    }

    @Test
    void rejectsPayloadLargerThanDemoLimit() {
        byte[] oversized = new byte[1_048_577];

        assertThrows(IllegalArgumentException.class,
            () -> app.rawEventDigest().apply(
                new ByteArrayInputStream(oversized)));
    }
}
~~~

Kiểm thử này chứng minh **Function xử lý stream**. Nó chưa tự chứng minh adapter AWS thực sự truyền stream không conversion trong một runtime Lambda. Phần đó cần kiểm thử trên FunctionInvoker hoặc Lambda staging.

### Tính hash thay đổi theo bytes, không theo ý nghĩa JSON

Có thể bổ sung một test với hai byte arrays biểu diễn:

~~~json
{"x":1}
~~~

và:

~~~json
{ "x": 1 }
~~~

Hai JSON object có cùng giá trị **x** nhưng bytes khác nhau, nên SHA-256 raw cũng khác. Đây là thuộc tính cần nhớ nếu dùng raw bytes cho chữ ký hoặc checksum.

## 18. Integration test của FunctionCatalog

Kiểm thử Spring context xác minh cả hai bean được đăng ký đúng tên:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import java.util.function.Function;

@SpringBootTest(classes = LambdaEventApplication.class)
class LambdaEventCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void bothFunctionsAreRegistered() {
        assertNotNull(catalog.lookup("validateOrder"));
        assertNotNull(catalog.lookup("rawEventDigest"));
    }

    @Test
    void typedFunctionAcceptsPojo() {
        Function<
            LambdaEventApplication.OrderRequest,
            LambdaEventApplication.OrderValidation> fn =
                catalog.lookup("validateOrder");

        assertNotNull(fn);

        var request = new LambdaEventApplication.OrderRequest();
        request.setRequestId("REQ-101");
        request.setSku("book");
        request.setQuantity(2);

        var result = fn.apply(request);

        assertEquals("BOOK", result.sku());
    }
}
~~~

**Không dùng assertSame giữa FunctionCatalog wrapper và bean gốc** để khẳng định singleton. Catalog có thể cung cấp wrapper cho conversion và composition. Cũng không dùng test này làm bằng chứng rằng AWS API Gateway hoặc SQS event envelope đã được unwrap đúng.

Nếu chạy test khi đã thêm **ManualParsingConfiguration**, application context phải có ObjectMapper bean và các dependencies Jackson phù hợp. Nếu chỉ dùng hai bean gốc của **LambdaEventApplication**, không cần thêm cấu hình đó.

## 19. Phân loại lỗi của đường POJO và InputStream

| Triệu chứng | Vùng lỗi | Nguyên nhân và cách xử lý |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Lambda packaging | Thiếu adapter trong shaded JAR hoặc handler sai |
| Không tìm được main class | Spring bootstrap | Kiểm tra **MAIN_CLASS/Start-Class** và lớp trong JAR |
| Không tìm được bean | FunctionCatalog | Sai **spring_cloud_function_definition** hoặc bean không đăng ký |
| JSON không parse thành POJO | Conversion | Sai schema, root type, field type, mapper |
| POJO được tạo nhưng bị từ chối | Validation | Field null, blank hoặc ngoài miền hợp lệ |
| **ClassCastException** với Map | Generic type | Input type chưa rõ, code ép kiểu không an toàn |
| Raw stream trả 0 bytes | Stream lifecycle | Đã đọc ở bước trước hoặc payload thực sự rỗng |
| OutOfMemoryError khi đọc raw | Bộ nhớ | **readAllBytes()** trên payload không giới hạn |
| UTF-8 text bị sai | Encoding | Dùng encoding không khớp hoặc coi binary là text |
| Signature/hash không khớp | Raw-byte contract | Thứ tự key, whitespace, newline, encoding đã đổi |
| API Gateway event không thành OrderRequest | Event envelope | Body nested/base64 hoặc version mapping khác |
| SQS xử lý nhầm chỉ một message | Batch semantics | Event chứa Records; cần xử lý từng record |
| S3 raw stream không phải file | Sai giả định nguồn | Stream là notification; dùng S3 GetObject để lấy nội dung |
| InputStream không đọc lại được | Ownership | Stream đã tiêu thụ; dùng buffer có giới hạn nếu cần |
| Handler trả lỗi nhưng CLI invoke thành công | AWS invocation | Xem **FunctionError**, response body và logs |

Thứ tự xử lý sự cố nên là: **handler có nạp không → Spring context có khởi tạo không → catalog có chọn đúng function không → input đã chuyển/đọc đúng không → business validation có thành công không**.

## 20. Đổi giao thức mà không đổi logic nghiệp vụ

Spring Cloud Function muốn các bean nghiệp vụ không phụ thuộc nơi gọi. Với **OrderRequest**, một đường thiết kế tốt là:

~~~mermaid
flowchart TB
    A["HTTP / API Gateway adapter"] --> D["OrderRequest"]
    B["SQS adapter"] --> D
    C["Serverless direct invoke"] --> D
    D --> E["validateOrder"]
    E --> F["OrderValidation"]
~~~

Nếu event từ các nguồn có envelope khác nhau, hãy tạo **adapter** trích xuất dữ liệu và gọi **validateOrder**. Đừng đưa việc đọc **APIGatewayProxyRequestEvent**, **SQSEvent** và **InputStream** vào cùng một hàm nghiệp vụ nếu không thật sự cần.

Khi cần raw bytes để kiểm tra chữ ký, giải mã hoặc parse đặc biệt, nên xử lý ở **adapter layer** rồi truyền DTO typed vào service. Nếu yêu cầu sản phẩm là lưu/kiểm tra chính raw invocation, một **Function<InputStream, R>** có thể là lựa chọn trực tiếp, nhưng cần tài liệu rõ format, kích thước tối đa và điều kiện an toàn.

### Chia sẻ POJO giữa nhiều adapter

Một kiểu **OrderRequest** có thể dùng được từ HTTP controller, Spring Cloud Stream mapper hoặc Lambda wrapper. Nhưng những chi tiết như **HTTP status**, **API Gateway response envelope**, **SQS partial batch failures** hoặc **IAM** không thuộc DTO nghiệp vụ.

**Độc lập giao thức không đồng nghĩa bỏ qua khác biệt giao nhận.** Side-effect có thể lặp do retry; với Consumer ghi database cần idempotency key và transaction thích hợp. Một Function validation không ghi dữ liệu như trong ví dụ đơn giản hơn nhưng vẫn phải kiểm soát lỗi dữ liệu.

## 21. Bảo mật và quan sát khi đọc raw events

Raw stream có thể chứa dữ liệu nhạy cảm, authorization tokens, thông tin nhận dạng hoặc nội dung nghiệp vụ mà log không được lưu trữ.

Những nguyên tắc cần áp dụng:

- **Không log toàn bộ raw payload** trong production chỉ để debug conversion.
- **Không tin tuyệt đối content type hoặc header do caller cung cấp**. Xác thực quyền ở ranh giới tin cậy.
- **Giới hạn kích thước** trước khi cấp phát buffer và parsing; áp dụng parser constraints khi xử lý cấu trúc lồng sâu.
- **Không xử lý dữ liệu binary như UTF-8 text** nếu chưa xác nhận định dạng.
- **Không coi SHA-256 hash là authentication**: nếu cần xác minh chữ ký, phải có secret/key phù hợp, thuật toán ký và so sánh an toàn.
- **Không lưu InputStream hoặc request data ở field singleton**; Lambda execution environment có thể được dùng lại cho nhiều invocation.
- **Phân loại lỗi vĩnh viễn và tạm thời**, cấu hình retry/dead-letter theo từng trigger.
- **Chỉ ghi metadata tối thiểu** phục vụ quan sát (request ID, type, kích thước, outcome); không dùng correlation ID do client tự gửi làm căn cứ phân quyền.

Nếu làm việc với event SQS, message có thể bị giao lại ngay cả khi code đã ghi dữ liệu nhưng response/ack lỗi. POJO conversion đúng không tự mang lại exactly-once delivery; cần idempotency ở tầng lưu trữ/hạ tầng.

## 22. Bài tập thực hành

**Bài tập 1 — POJO.** Viết **Function<PaymentRequest, PaymentValidation>** với JavaBean POJO có **requestId**, **currency**, **amount**. Dùng kiểu nullable ở input để phát hiện trường thiếu, nêu quy tắc tiền tệ/độ chính xác và test validation.

**Bài tập 2 — Raw hash.** Thay đổi rawEventDigest để từ chối payload lớn hơn 64 KiB. Viết unit test cho đúng biên 64 KiB và vượt một byte, kiểm tra SHA-256 thay đổi khi thêm whitespace cuối JSON.

**Bài tập 3 — Manual parse.** Viết **Function<InputStream, OrderValidation>** dùng ObjectMapper phù hợp với phiên bản dự án. Đọc có giới hạn, parse JSON sang OrderRequest và gọi validator. Giải thích vì sao không đọc InputStream hai lần.

**Bài tập 4 — Đối chiếu hai Lambda.** Deploy hai bean **validateOrder** và **rawEventDigest** bằng cùng shaded JAR, khác **spring_cloud_function_definition**. Dùng một direct invoke JSON object, so sánh output typed validation và digest của bytes.

**Bài tập 5 — API Gateway.** Một API Gateway HTTP API gửi event có **body** là chuỗi JSON và **isBase64Encoded**. Thiết kế adapter chuyển envelope thành OrderRequest, xử lý body đã encode và trả response phù hợp payload version.

**Bài tập 6 — SQS.** Một Lambda nhận SQS batch với ba Records. Giải thích tại sao **Function<OrderRequest,R>** không tự đại diện cho cả batch, đề xuất kiểu sự kiện hoặc adapter xử lý từng record và chính sách partial batch failures.

**Bài tập 7 — S3.** Một S3 notification chỉ có bucket/key. Chỉ ra vì sao InputStream của FunctionInvoker không chứa bytes của object, và lớp nào cần quyền IAM để lấy nội dung từ S3.

**Bài tập 8 — Generic type.** So sánh **Function<OrderRequest,R>**, **Function<Map<String,Object>,R>** và **Function<InputStream,R>** về conversion, type safety, versioning và khả năng test. Nêu lỗi có thể xảy ra với quantity trong Map.

**Bài tập 9 — Truy tìm lỗi.** Direct invoke JSON có quantity là string hoặc nested object; catalog đã chọn đúng bean nhưng không có log từ apply(). Xác định nguyên nhân ở conversion, cách kiểm tra payload thật và test nào cần bổ sung.

### Ghi nhớ

- **FunctionInvoker** nhận payload invocation ở dạng stream. Với **Function<POJO,R>**, adapter cố gắng chuyển dữ liệu thành kiểu POJO; với **Function<InputStream,R>**, nó **truyền stream thẳng vào hàm** mà không convert input.
- **InputStream nguyên bản là stream của Lambda event**, không mặc nhiên là HTTP body, SQS message body hay file S3.
- **POJO typed** làm rõ schema và giúp tái sử dụng nghiệp vụ; validation vẫn cần được thực hiện, không được dựa chỉ vào converter.
- Khi tự đọc stream, **đọc một lần**, có giới hạn dung lượng, xác định encoding, phân loại lỗi I/O/parsing và không giữ raw input sau invocation.
- **spring_cloud_function_definition** chọn đúng bean; handler **FunctionInvoker** và **MAIN_CLASS** thuộc tầng khởi tạo Lambda/Spring.
- Kiểm thử cần tách **logic Java**, **FunctionCatalog**, **conversion/event envelope** và **invocation trên AWS**. Lỗi của từng tầng phải được xử lý tại đúng ranh giới.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, Type Conversion, Raw Input, AWS request handlers và events.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): FunctionCatalog, types, message handling và composition.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): RequestHandler, RequestStreamHandler, InputStream và kiểu sự kiện.
- [AWS API Gateway — Lambda proxy integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html): event/response envelope cho proxy.
- [AWS Lambda — SQS error handling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html): retry và partial batch responses.
