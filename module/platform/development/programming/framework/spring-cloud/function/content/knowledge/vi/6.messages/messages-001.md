# Cấu trúc `Message<T>`, `payload` và `MessageHeaders`

## 1. Bối cảnh: dữ liệu và thông tin đi kèm dữ liệu

Trong **SPRING_CLOUD_FUNCTION**, logic nghiệp vụ được biểu diễn bằng `Supplier`, `Function` và `Consumer`. Một hàm có thể được gọi trực tiếp qua `FunctionCatalog`, công bố qua HTTP, nối với luồng sự kiện hoặc chạy trong môi trường serverless. Để cùng một hàm xử lý thông tin từ nhiều giao thức mà không phụ thuộc vào API của từng giao thức, Spring sử dụng một kiểu dữ liệu chung: **`Message<T>`**.

Giả sử dịch vụ nhận sự kiện đặt hàng. Nội dung đơn hàng là dữ liệu nghiệp vụ; mã theo dõi yêu cầu (`correlationId`), loại nội dung (`contentType`) và nguồn phát sự kiện là thông tin hỗ trợ xử lý. Nếu chỉ truyền một đối tượng `Order`, hàm sẽ không nhìn thấy những thông tin đi kèm này. Nếu nhận `Message<Order>`, hàm có thể sử dụng cả hai nhóm thông tin theo cùng một mô hình.

Mục tiêu của bài học:

- Nhận diện đúng vai trò của `Message<T>`, `payload` và `MessageHeaders`.
- Tạo, đọc và biến đổi thông điệp bằng API Spring Messaging.
- Viết hàm Spring Cloud Function có thể xử lý metadata mà không ràng buộc vào HTTP hoặc message broker.
- Hiểu cách giữ/chọn lọc header, cách `contentType` liên quan đến chuyển đổi kiểu và những lỗi thường gặp khi composition.

> `Message<T>` và `MessageHeaders` thuộc **Spring Messaging** (`org.springframework.messaging`); Spring Cloud Function sử dụng lại các kiểu này. `Message<T>` là mô hình thông điệp **bên trong ứng dụng**, không phải khẳng định rằng dữ liệu truyền trên mạng luôn có JSON dạng `{ "payload": ..., "headers": ... }`.

## 2. Cấu trúc của `Message<T>`

Giao diện cốt lõi được rút gọn như sau:

```java
package org.springframework.messaging;

public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

| Thành phần | Kiểu | Vai trò | Ví dụ |
|---|---|---|---|
| `Message<T>` | Giao diện bao thông điệp | Gom nội dung và metadata thành một đơn vị xử lý | `Message<OrderCreated>` |
| `payload` | `T` | Dữ liệu nghiệp vụ chính mà hàm xử lý | `OrderCreated("O-42", 150000)` |
| `headers` | `MessageHeaders` | Tập khóa–giá trị mô tả ngữ cảnh, cách diễn giải hoặc định tuyến thông điệp | `correlationId`, `contentType` |

Trong khai báo `Message<OrderCreated>`, tham số kiểu `OrderCreated` mô tả **kiểu payload**, không phải kiểu của headers. Hai thông điệp có cùng kiểu payload vẫn có thể mang các header khác nhau.

```text
Message<OrderCreated>
├── payload: OrderCreated(orderId="O-42", amount=150000)
└── headers: MessageHeaders
    ├── id            -> UUID của thông điệp
    ├── timestamp     -> thời điểm tạo thông điệp (milliseconds)
    ├── correlationId -> "checkout-73"
    └── contentType   -> application/json
```

`Message<T>` hỗ trợ việc truy cập payload theo kiểu tĩnh trong mã Java. Tuy nhiên, việc dữ liệu nhận từ HTTP hoặc broker có được giải mã thành `T` hay không còn phụ thuộc vào chữ ký hàm, converter, cấu hình và adapter đầu vào. Khai báo `Message<OrderCreated>` tự nó không bảo đảm rằng mọi chuỗi JSON sẽ được chuyển thành `OrderCreated`.

### `payload`: phần nội dung được xử lý

`payload` có thể là `String`, một DTO, `byte[]`, danh sách hoặc kiểu đối tượng mà ứng dụng hỗ trợ. Ví dụ, `Function<Message<String>, Message<Integer>>` nhận một thông điệp có payload chuỗi và tạo ra thông điệp có payload số nguyên.

Với các cách xây dựng thông điệp thông dụng của Spring Messaging như `MessageBuilder` hoặc `GenericMessage`, payload phải khác `null`. Nếu nghiệp vụ cần biểu diễn “không có dữ liệu”, hãy thiết kế hợp đồng hàm rõ ràng (chẳng hạn một kết quả/trạng thái riêng); đừng giả định `MessageBuilder.withPayload(null)` tạo được thông điệp hợp lệ.

### `MessageHeaders`: metadata có cấu trúc khóa–giá trị

`MessageHeaders` triển khai `Map<String, Object>` và cung cấp thêm các hằng số, phương thức truy cập một số header chuẩn. Giá trị header có kiểu `Object`, vì vậy không nên mặc định mọi header đều là `String`.

| Header | Ý nghĩa thường gặp | Lưu ý |
|---|---|---|
| `id` (`MessageHeaders.ID`) | Định danh của **thông điệp** | Thường là `UUID`; khác với mã đơn hàng hoặc `correlationId` |
| `timestamp` (`MessageHeaders.TIMESTAMP`) | Thời điểm tạo thông điệp | Thường là số mili giây từ Unix epoch (`Long`) |
| `contentType` (`MessageHeaders.CONTENT_TYPE`) | Gợi ý định dạng payload để chuyển đổi nội dung | Kiểu giá trị có thể khác nhau theo nơi tạo thông điệp/adapter |
| `replyChannel` | Kênh nhận phản hồi trong một số luồng Spring Messaging/Integration | Không mặc định xuất hiện trong mọi lời gọi HTTP hay broker |
| `errorChannel` | Kênh xử lý lỗi trong một số luồng tích hợp | Ý nghĩa cụ thể do hạ tầng tích hợp quyết định |
| `correlationId`, `source`, `tenantId` | Header do ứng dụng tự quy ước | Chỉ có ý nghĩa khi các thành phần thống nhất tên, kiểu và độ tin cậy |

Không nên dùng `id` của một thông điệp làm định danh nghiệp vụ lâu dài: một sự kiện có thể được đóng gói, chuyển đổi hoặc phát lại trong một thông điệp mới. `correlationId` do ứng dụng định nghĩa hữu ích hơn để liên kết nhiều bước xử lý cùng một yêu cầu.

## 3. Tạo và đọc thông điệp

`MessageBuilder` là cách tạo thông điệp phổ biến. Ví dụ bên dưới sử dụng trực tiếp Spring Messaging, chưa cần HTTP server hay message broker:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> message = MessageBuilder.withPayload("order.created")
        .setHeader("correlationId", "checkout-73")
        .setHeader("source", "checkout-service")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
        .build();

String eventName = message.getPayload();
String correlationId = message.getHeaders()
        .get("correlationId", String.class);
Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);

System.out.println(eventName);               // order.created
System.out.println(correlationId);           // checkout-73
System.out.println(contentType);             // text/plain
System.out.println(message.getHeaders().getId());
System.out.println(message.getHeaders().getTimestamp());
```

Trong ví dụ này:

1. `withPayload(...)` đặt nội dung nghiệp vụ.
2. `setHeader(...)` thêm metadata theo tên và giá trị xác định.
3. `build()` tạo một `Message<String>` để truyền qua các hàm.
4. `getPayload()` và `getHeaders()` đọc hai phần của thông điệp; `get("correlationId", String.class)` yêu cầu header có đúng kiểu `String` nếu tồn tại. Nếu tồn tại nhưng sai kiểu, API có thể ném ngoại lệ thay vì tự ép kiểu.

`MessageHeaders` không cho phép thay đổi trực tiếp sau khi tạo: các thao tác như `message.getHeaders().put(...)` sẽ không thành công. Muốn thay payload hoặc header, hãy **tạo thông điệp mới** bằng `MessageBuilder`:

```java
Message<String> updated = MessageBuilder.fromMessage(message)
        .setHeader("source", "order-processor")
        .build();

// message vẫn là thông điệp ban đầu; updated mang header đã thay đổi.
```

Đây là tính **chỉ đọc của map headers**, không bảo đảm tính bất biến sâu: nếu một giá trị header là đối tượng có thể thay đổi, bản thân đối tượng đó vẫn có thể bị sửa. Ưu tiên kiểu giá trị đơn giản, ổn định và có thể biểu diễn được qua ranh giới giao thức.

## 4. `Message<T>` trong `Supplier`, `Function`, `Consumer`

Spring Cloud Function cho phép khai báo hàm theo hai cách. Khi chỉ cần dữ liệu nghiệp vụ, sử dụng kiểu payload trực tiếp; khi cần đọc hoặc phát sinh metadata, đưa `Message<T>` vào chữ ký hàm.

| Loại hàm | Chỉ xử lý payload | Xử lý cả thông điệp |
|---|---|---|
| `Supplier` | `Supplier<OrderCreated>` | `Supplier<Message<OrderCreated>>` |
| `Function` | `Function<OrderCreated, OrderResult>` | `Function<Message<OrderCreated>, Message<OrderResult>>` |
| `Consumer` | `Consumer<OrderCreated>` | `Consumer<Message<OrderCreated>>` |

Ví dụ `Function<String, String>` chỉ thể hiện phép biến đổi chuỗi ở cấp chữ ký Java:

```java
@Bean
public Function<String, String> uppercase() {
    return text -> text.toUpperCase(Locale.ROOT);
}
```

Khi mã xử lý cần kiểm tra `correlationId` hoặc tạo header đầu ra, khai báo rõ `Message` làm đầu vào/đầu ra. Điều này giúp logic metadata trở thành một phần có thể đọc hiểu và kiểm thử của hợp đồng hàm.

### Ví dụ hoàn chỉnh: chuẩn hóa chuỗi và giữ mã liên kết

```java
package com.example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class MessageFunctions {

    @Bean
    public Function<Message<String>, Message<String>> normalize() {
        return incoming -> {
            String result = incoming.getPayload()
                    .strip()
                    .toUpperCase(Locale.ROOT);

            String correlationId = incoming.getHeaders()
                    .get("correlationId", String.class);

            MessageBuilder<String> output = MessageBuilder
                    .withPayload(result)
                    .setHeader("processedBy", "normalize");

            if (correlationId != null) {
                output.setHeader("correlationId", correlationId);
            }

            return output.build();
        };
    }
}
```

Đầu vào minh họa:

```text
payload = "  spring cloud function  "
headers = { correlationId: "req-42", source: "api-gateway", ... }
```

Đầu ra logic của hàm:

```text
payload = "SPRING CLOUD FUNCTION"
headers = { processedBy: "normalize", correlationId: "req-42", ... }
```

Dấu `...` ở đầu ra biểu thị các header hệ thống được tạo khi xây dựng thông điệp, **không** hàm ý rằng header `source` từ đầu vào đã được tự động chuyển tiếp. Hàm trên chủ động giữ `correlationId` vì nghiệp vụ cần nó; các header khác không được sao chép.

Với `Supplier<Message<T>>`, hàm tự tạo cả payload và header trước khi cung cấp thông điệp. Với `Consumer<Message<T>>`, hàm đọc được headers nhưng không có giá trị trả về; việc xác nhận đã nhận sự kiện hoặc báo lỗi cho hệ thống vận chuyển phụ thuộc adapter/binder đang dùng, không chỉ phụ thuộc chữ ký `Consumer`.

## 5. Sao chép header: chọn lọc hay giữ toàn bộ?

Khi biến đổi payload, có hai cách tạo thông điệp đầu ra thường gặp:

```java
// A. Chỉ mang những header cần thiết cho nghiệp vụ
Message<String> selective = MessageBuilder
        .withPayload("PROCESSED")
        .setHeader("correlationId", "req-42")
        .build();

// B. Sao chép headers rồi thay hoặc bổ sung theo yêu cầu
Message<String> copied = MessageBuilder
        .withPayload("PROCESSED")
        .copyHeaders(incoming.getHeaders())
        .setHeader("processedBy", "processor")
        .build();
```

Phương án A phù hợp khi chỉ một vài metadata thực sự cần đi tiếp. Phương án B hữu ích khi hợp đồng xử lý yêu cầu chuyển tiếp nhiều header, nhưng cần rà soát chúng trước khi sử dụng:

- `contentType` của đầu vào có thể không phù hợp sau khi payload đổi từ DTO sang `String` hoặc `byte[]`.
- `replyChannel`, `errorChannel` hoặc metadata riêng của broker có thể chỉ có ý nghĩa tại chặng hiện tại.
- Header nhạy cảm, do client tự khai báo hoặc thuộc ngữ cảnh bảo mật không nên được phát tán mặc định qua nhiều hệ thống.
- Các header hệ thống như `id`/`timestamp` có quy tắc xử lý riêng khi xây dựng thông điệp; đừng dựa vào việc sao chép để suy ra một định danh nghiệp vụ bất biến.

Vì vậy, hãy định nghĩa rõ **header nào cần tồn tại ở đầu ra**. Nếu sử dụng `copyHeaders(...)`, xem xét loại bỏ hoặc thay thế những khóa không còn phù hợp bằng builder trước `build()`.

## 6. `contentType`, kiểu `T` và chuyển đổi dữ liệu

Một thông điệp có ba khía cạnh dễ bị nhầm lẫn:

| Khía cạnh | Câu hỏi cần trả lời |
|---|---|
| Kiểu Java `T` | Bên trong hàm, `getPayload()` được kỳ vọng có kiểu nào? |
| Header `contentType` | Payload được biểu diễn theo định dạng nào khi cần chuyển đổi? |
| Adapter và converter | Ai chuyển bytes/JSON từ bên ngoài thành đối tượng Java và ngược lại? |

Ví dụ: HTTP client gửi JSON của đơn hàng, adapter web nhận nội dung thô rồi dùng cơ chế chuyển đổi phù hợp với cấu hình và chữ ký `Function<Message<OrderCreated>, ...>`. Khi hàm đang thực thi, `incoming.getPayload()` có thể là `OrderCreated` **nếu** quá trình chuyển đổi thành công. Bản thân `Message<T>` không phải bộ giải mã JSON.

```java
// DTO minh họa trên Java 17+
public record OrderCreated(String orderId, long amount) {}

@Bean
public Function<Message<OrderCreated>, Message<String>> orderSummary() {
    return incoming -> {
        OrderCreated order = incoming.getPayload();
        String summary = order.orderId() + ": " + order.amount();

        return MessageBuilder.withPayload(summary)
                .setHeader("correlationId",
                        incoming.getHeaders().get("correlationId"))
                .build();
    };
}
```

Ở đây kiểu payload **thay đổi từ `OrderCreated` sang `String`**. Một `contentType: application/json` gắn với nội dung đầu vào không nhất thiết phù hợp với định dạng muốn xuất ra. Định dạng đầu ra thực tế phải được xác định theo hợp đồng giao tiếp và cấu hình converter/adapter tương ứng. Ví dụ trên không sao chép nguyên xi `contentType` từ đầu vào.

Đừng nhầm `contentType` của `MessageHeaders` với header HTTP `Content-Type` trong mọi hoàn cảnh: adapter có thể ánh xạ giữa chúng, nhưng quy tắc ánh xạ, giá trị và cách mã hóa payload phụ thuộc tích hợp đang sử dụng.

## 7. Message khi gọi `FunctionCatalog`, composition và các adapter

`FunctionCatalog` đăng ký, tìm kiếm và kết hợp các hàm. Với bean `normalize` ở trên, mã Java khác có thể tra cứu hàm bằng tên:

```java
// catalog được inject từ Spring context
Function<Message<String>, Message<String>> fn =
        catalog.lookup("normalize");

Message<String> request = MessageBuilder
        .withPayload("  hello  ")
        .setHeader("correlationId", "req-42")
        .build();

Message<String> response = fn.apply(request);
// response.getPayload() -> "HELLO"
// response.getHeaders().get("correlationId") -> "req-42"
```

Ở đây `catalog` có kiểu `org.springframework.cloud.function.context.FunctionCatalog`. Khi công bố hàm qua **Spring Cloud Function Web**, lời gọi HTTP được adapter chuyển thành đầu vào thích hợp cho hàm. Khi dùng **Spring Cloud Stream**, binder và cơ chế chuyển đổi thông điệp đảm nhận bước liên kết với broker. Với **serverless adapter**, runtime sự kiện đảm nhận điểm vào. Code nghiệp vụ của `normalize` có thể được dùng lại, nhưng **không phải mọi header từ mỗi giao thức đều tự động có mặt hoặc giữ nguyên tên/kiểu**. Cần xác minh mapping header tại từng adapter thực tế.

Sơ đồ luồng tư duy:

```text
HTTP / Broker / Serverless event
               |
        [adapter + converter]
               |
      Message<T> + MessageHeaders
               |
       Function<Message<T>, Message<R>>
               |
      Message<R> + MessageHeaders
               |
        [adapter + converter]
               |
      HTTP response / Event / Result
```

Composition cho phép nối nhiều bước, ví dụ cấu hình `spring.cloud.function.definition=normalize|decorate` khi cả hai bean đã được định nghĩa và tương thích kiểu. Khi một bước cần `correlationId` từ bước trước, hãy kiểm tra hợp đồng của từng bước: nếu hàm đầu trả về thông điệp mới nhưng bỏ `correlationId`, hàm sau không thể tự khôi phục mã đó. Ngoài ra, composition của các chữ ký chỉ có payload và có `Message` có thể chịu ảnh hưởng từ cơ chế đóng gói/chuyển đổi của framework; nên kiểm thử kết quả thực tế thông qua `FunctionCatalog`.

## 8. Kiểm thử payload và header cùng nhau

Có thể kiểm tra logic thuần Java mà chưa cần khởi động HTTP server hoặc broker. Ví dụ dùng JUnit 5 cho bean `normalize` đã viết ở mục 4:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageFunctionsTest {

    @Test
    void normalizeChangesPayloadAndKeepsCorrelationId() {
        Function<Message<String>, Message<String>> fn =
                new MessageFunctions().normalize();

        Message<String> input = MessageBuilder
                .withPayload("  xin chào  ")
                .setHeader("correlationId", "req-42")
                .build();

        Message<String> output = fn.apply(input);

        assertEquals("XIN CHÀO", output.getPayload());
        assertEquals("req-42", output.getHeaders().get("correlationId"));
        assertEquals("normalize", output.getHeaders().get("processedBy"));
        assertEquals("  xin chào  ", input.getPayload());
    }
}
```

Kiểm thử này cho thấy payload được biến đổi, `correlationId` được giữ, header mới được bổ sung và thông điệp đầu vào không bị thay đổi. Khi tích hợp với HTTP/broker, nên thêm kiểm thử riêng qua adapter để xác nhận mapping `contentType`, tên header và chuyển đổi DTO như kỳ vọng.

## 9. Các lỗi dễ gặp và cách tránh

| Hiện tượng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| `getPayload()` không phải DTO mong muốn | Thiếu/sai `contentType`, converter không phù hợp hoặc chữ ký kiểu không đúng | Kiểm tra dữ liệu nhận thực tế, cấu hình adapter và kiểu hàm |
| Hàm sau composition mất `correlationId` | Hàm trước tạo thông điệp mới nhưng không chuyển header cần thiết | Định nghĩa hợp đồng metadata giữa các bước và kiểm thử từng chặng |
| Không sửa được `message.getHeaders()` | `MessageHeaders` là map chỉ đọc | Dùng `MessageBuilder` xây thông điệp mới |
| Lỗi kiểu dữ liệu khi đọc header | Header chứa kiểu khác với kiểu yêu cầu | Thống nhất kiểu; kiểm tra và chuyển đổi rõ ràng tại biên hệ thống |
| Response hoặc event có định dạng không đúng | Header `contentType` cũ được mang theo khi payload đổi kiểu | Xác định lại định dạng đầu ra theo hợp đồng và converter |
| Dùng header client gửi để quyết định quyền truy cập | Metadata không phải bằng chứng xác thực | Xác thực/ủy quyền tại ranh giới tin cậy, không tin `tenantId` hoặc quyền tự khai báo |

Một nguyên tắc thiết kế hữu ích: **payload mô tả nghiệp vụ đang được xử lý; headers mô tả ngữ cảnh cần thiết để xử lý hoặc chuyển tiếp payload đó**. Chỉ đưa vào headers dữ liệu gọn, có tên/kiểu được quy ước, và chỉ truyền tiếp những gì bên nhận thực sự cần.

## 10. Thực hành áp dụng

Giả sử luồng `order.created` gửi payload kiểu `OrderCreated` cùng hai header `correlationId` và `source`. Hãy tự triển khai `Function<Message<OrderCreated>, Message<OrderResult>>` theo yêu cầu:

1. Đọc mã đơn hàng và số tiền từ `getPayload()`; từ chối giá trị số tiền không hợp lệ theo quy tắc nghiệp vụ bạn chọn.
2. Tạo `OrderResult` biểu diễn kết quả xử lý, không thay đổi payload đầu vào.
3. Chỉ đưa `correlationId` sang thông điệp đầu ra nếu nó có mặt và đúng kiểu; đặt thêm `processedBy=orderValidator`.
4. Viết kiểm thử cho trường hợp có và không có `correlationId`. Kiểm tra cả payload lẫn headers của kết quả.
5. Thử nối hàm này với một hàm thứ hai qua `FunctionCatalog`; xác minh `correlationId` vẫn tồn tại sau hai bước. Nếu đưa hàm ra HTTP hay broker, kiểm tra thêm việc ánh xạ header qua adapter đó.

**Ghi nhớ:** `Message<T>` gom payload và metadata trong một hợp đồng thống nhất. `MessageHeaders` cung cấp ngữ cảnh nhưng là cấu trúc chỉ đọc sau khi xây dựng. Trong Spring Cloud Function, lựa chọn giữa `Function<T, R>` và `Function<Message<T>, Message<R>>` tùy vào việc logic nghiệp vụ có cần tham gia xử lý metadata hay không; tính độc lập với HTTP, sự kiện và serverless đạt được nhờ adapter, chữ ký hàm phù hợp và hợp đồng chuyển đổi thông điệp rõ ràng.
