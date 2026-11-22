# Transformer không tạo output

## 1. Vấn đề cần giải quyết

Trong module **SPRING_INTEGRATION_CORE**, transformer là endpoint chuyển một thông điệp sang dạng dữ liệu mà bước tiếp theo có thể sử dụng. Khi ứng dụng báo “transformer không tạo output”, cần xác định thông điệp dừng ở đâu: bên trong phép biến đổi, khi gửi qua `MessageChannel`, hay trên đường trả kết quả về gateway.

Ví dụ, một luồng nhận mã sản phẩm, chuẩn hóa rồi chuyển cho dịch vụ tra cứu:

```text
Message<String> → productsInput → transformer → normalizedProducts → consumer
                    " ab-123 "                   "AB-123"
```

Nếu consumer không nhận được gì, tăng thời gian chờ chưa đủ để xử lý. Có thể phép biến đổi trả về `null`, endpoint chưa được gọi, kết quả nằm trong một hàng đợi, hoặc một bước sau transformer đã kết thúc luồng.

Sau bài này, bạn có thể:

- Phân biệt kết quả `null`, payload rỗng, thông điệp bị loại và kết quả được gửi sang kênh khác.
- Chọn transformer, filter, router hoặc service activator theo hợp đồng nghiệp vụ.
- Tái hiện lỗi bằng Java DSL và kiểm tra cả nhánh thành công lẫn nhánh không có output.
- Lần theo `outputChannel`, `replyChannel`, lỗi đồng bộ và lỗi bất đồng bộ.

Các cấu hình và kiểm thử minh họa dùng **Java 17+ và Spring Integration 6.5.x**. Đây là mốc của ví dụ, không phải yêu cầu nâng cấp dự án. Khi dùng Spring Boot, để cơ chế quản lý dependency của Boot chọn bộ phiên bản tương thích; không tự trộn các phiên bản Spring chỉ để chạy ví dụ.

## 2. Hợp đồng của transformer

### 2.1. Chuyển đổi thành công phải có kết quả

Về thiết kế, transformer thực hiện quan hệ:

```text
một thông điệp đầu vào → một thông điệp đầu ra hợp lệ
```

Đối với phương thức POJO hoặc lambda được DSL thích nghi thành transformer, giá trị trả về thông thường trở thành payload của thông điệp mới. Nếu trả về một `Message<?>`, đối tượng đó là thông điệp kết quả. Không dùng `return null` để biểu thị “bỏ qua thông điệp”. Tài liệu chính thức dành hành vi loại thông điệp cho filter. [Tham khảo hợp đồng transformer](https://docs.spring.io/spring-integration/reference/transformer.html).

Ví dụ đúng:

```java
public String normalizeProductCode(String code) {
    return code.strip().toUpperCase(java.util.Locale.ROOT);
}
```

Ví dụ sai về thiết kế:

```java
public String normalizeProductCode(String code) {
    if (code.isBlank()) {
        return null; // Đang lồng quyết định loại bỏ vào phép chuyển đổi.
    }
    return code.strip().toUpperCase(java.util.Locale.ROOT);
}
```

Transformer có thể trả về một danh sách, nhưng danh sách đó vẫn là payload của **một** thông điệp. Muốn phát từng phần tử thành thông điệp riêng cần một splitter.

### 2.2. Không đồng nhất mọi giá trị “rỗng”

| Kết quả của phương thức | Ý nghĩa trong tình huống này | Hướng xử lý |
| --- | --- | --- |
| `null` | Không có kết quả để tạo output của transformer | Sửa logic chuyển đổi hoặc tách quyết định loại bỏ ra filter |
| `""` hoặc chuỗi chỉ có khoảng trắng | Có đối tượng payload kiểu `String` | Kiểm tra quy tắc nghiệp vụ; không suy ra rằng luồng đã dừng |
| `List.of()` | Có một payload danh sách rỗng | Consumer nhận danh sách rỗng nếu các bước còn lại cho phép |
| Một DTO có trường tùy chọn bằng `null` | DTO vẫn là đối tượng khác `null` | Kiểm tra schema và dữ liệu bắt buộc của DTO |
| `void` | Phương thức không có giá trị trả về | Dùng service activator cho tác vụ kết thúc luồng |

Không dùng `Optional.empty()` như một lệnh chung yêu cầu transformer bỏ thông điệp. `Optional` là kiểu dữ liệu; việc được giữ làm payload hay được một lớp thích nghi xử lý phụ thuộc API đang dùng. Nếu nghiệp vụ có trạng thái “không tìm thấy”, hãy mô hình hóa trạng thái đó hoặc chọn endpoint phù hợp.

### 2.3. Kiểu exception cần đọc theo đường thực thi

Trong Spring Integration 6.5.x, `MessageTransformingHandler` bật `requiresReply=true` khi được tạo. Nếu phần xử lý trả về `null`, lớp cha `AbstractReplyProducingMessageHandler` có thể ném `ReplyRequiredException`. Nếu bản thân phép chuyển đổi ném lỗi, bạn thường gặp `MessageTransformationException` trong chuỗi nguyên nhân. Xem [handler của transformer 6.5.x](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/transformer/MessageTransformingHandler.java) và [logic kiểm tra reply của lớp cha](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/handler/AbstractReplyProducingMessageHandler.java).

Vì vậy, không viết cơ chế giám sát dựa trên giả định “mọi trường hợp transformer trả về `null` đều có cùng một tên exception”. Hãy đọc endpoint gây lỗi, failed message và toàn bộ chuỗi nguyên nhân.

Không sửa lỗi bằng cách tìm cách tắt yêu cầu reply của transformer. Chọn endpoint có hợp đồng phù hợp. Riêng từ Spring Integration 7.1, `MessageTransformingHandler.setRequiresReply(...)` được ghi rõ là ném `UnsupportedOperationException`. [Javadoc của phương thức](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/MessageTransformingHandler.html#setRequiresReply(boolean)).

## 3. Phân loại hiện tượng trước khi sửa

| Quan sát | Giả thuyết cần kiểm tra | Bằng chứng nên thu thập |
| --- | --- | --- |
| Không có log khi vào transformer | Message chưa tới endpoint, endpoint chưa chạy hoặc có consumer khác nhận | Tên input channel, trạng thái endpoint, số subscriber, poller |
| Có log vào hàm rồi phát sinh lỗi | Nhánh trả về `null`, sai kiểu hoặc exception trong phép chuyển đổi | Giá trị trả về, stack trace, nguyên nhân gốc |
| Hàm đã trả dữ liệu nhưng gửi thất bại | Không xác định được kênh hoặc kênh không nhận được message | `outputChannel`, `replyChannel`, lỗi dispatch/send |
| Hàng đợi output có message nhưng consumer không chạy | Consumer chưa poll, bị dừng hoặc chưa được cấu hình | Loại channel, poller, lifecycle |
| Có output sau transformer nhưng gateway vẫn chờ | Một bước sau đó loại message, trả `null`, hoặc gửi sang nhánh không hồi đáp | Các kênh sau transformer và hợp đồng gateway |
| Chỉ một số request mất kết quả | Nhánh điều kiện, cạnh tranh consumer hoặc lỗi theo dữ liệu | Mã nghiệp vụ/correlation ID của từng request |

Một phép đo hữu ích là xác định **ranh giới cuối cùng đã thấy thông điệp**. Log “đã gửi vào input” chỉ chứng minh được một mốc; log “đã tạo DTO” cũng chưa chứng minh consumer cuối đã nhận DTO.

## 4. Tái hiện lỗi và sửa bằng filter kết hợp transformer

### 4.1. Cấu hình đầy đủ cho hai luồng

Ví dụ sau cố ý đặt luồng lỗi và luồng sửa trong cùng cấu hình để so sánh. Các queue đầu ra dành cho kiểm thử; không có consumer tự động lấy thông điệp khỏi chúng.

Dependency cần có là `spring-integration-core`. Phần kiểm thử ở mục sau dùng JUnit Jupiter và `spring-test`. Trong dự án Boot, starter Integration và starter Test tương ứng có thể cung cấp các thành phần này.

Lưu cấu hình dưới tên `TransformerNoOutputConfig.java` trong package phù hợp của dự án:

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class TransformerNoOutputConfig {

    @Bean
    public DirectChannel brokenInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel brokenOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow brokenFlow() {
        return IntegrationFlow.from(brokenInput())
                .<String, String>transform(text -> {
                    if (text.isBlank()) {
                        return null; // Cố ý gây lỗi để quan sát.
                    }
                    return text.strip().toUpperCase(Locale.ROOT);
                }, endpoint -> endpoint.id("brokenTransformerEndpoint"))
                .channel(brokenOutput())
                .get();
    }

    @Bean
    public DirectChannel cleanInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel acceptedOutput() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel rejectedOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow cleanFlow() {
        return IntegrationFlow.from(cleanInput())
                .<String>filter(text -> !text.isBlank(),
                        filter -> filter.discardChannel(rejectedOutput()))
                .<String, String>transform(
                        text -> text.strip().toUpperCase(Locale.ROOT),
                        endpoint -> endpoint.id("normalizeTransformerEndpoint"))
                .channel(acceptedOutput())
                .get();
    }
}
```

Cấu hình trên dùng các phương thức `@Bean` được proxy theo mặc định của `@Configuration`; những lần gọi như `brokenInput()` tham chiếu bean do container quản lý. Các toán tử `transform`, `filter` trong DSL tạo endpoint tương ứng và các kết nối của luồng. [Cơ sở Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

Đầu vào minh họa được giới hạn là payload kiểu `String`. Việc xử lý payload kiểu khác cần hợp đồng chuyển đổi kiểu riêng; không xem ví dụ này là bộ kiểm tra dữ liệu tổng quát.

### 4.2. Kết quả mong đợi

| Luồng | Input | Output thành công | Nhánh loại bỏ hoặc lỗi |
| --- | --- | --- | --- |
| `brokenFlow` | `" ab-123 "` | `brokenOutput` nhận `"AB-123"` | Không có |
| `brokenFlow` | `"   "` | Không có | Lỗi vì transformer không tạo reply |
| `cleanFlow` | `" ab-123 "` | `acceptedOutput` nhận `"AB-123"` | `rejectedOutput` không nhận |
| `cleanFlow` | `"   "` | `acceptedOutput` không nhận | `rejectedOutput` nhận thông điệp ban đầu |

Trong luồng sửa, filter xử lý quyết định chấp nhận trước khi transformer chuẩn hóa. Một thông điệp bị từ chối được chuyển đến `discardChannel`, không biến thành một output giả chứa chuỗi rỗng. Filter cũng có tùy chọn `throwExceptionOnRejection(true)` nếu từ chối phải là lỗi; cần quyết định rõ chính sách loại bỏ và tránh bật các tùy chọn theo thói quen. [Hành vi của filter](https://docs.spring.io/spring-integration/reference/filter.html).

Điểm cần giữ trong thiết kế là mỗi nhánh có kết quả quan sát được: đầu vào hợp lệ được chuẩn hóa, đầu vào không hợp lệ đi vào nhánh từ chối. Với hệ thống thật, nhánh từ chối có thể ghi nhận lý do, số lượng và mã nghiệp vụ để hỗ trợ vận hành.

## 5. Chọn endpoint theo ý nghĩa của “không cần output”

### 5.1. Chỉ thực hiện tác dụng phụ và kết thúc luồng

Nếu yêu cầu là ghi audit, gửi thông báo hoặc gọi một dịch vụ không cần kết quả tiếp theo, dùng service activator. Ví dụ độc lập dưới đây nhận thông điệp rồi in payload; trong ứng dụng, thay phần in bằng dịch vụ audit:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class AuditOnlyConfig {

    @Bean
    public IntegrationFlow auditOnlyFlow() {
        MessageHandler auditHandler = (Message<?> message) ->
                System.out.println("AUDIT: " + message.getPayload());

        return IntegrationFlow.from("auditInput")
                .handle(auditHandler)
                .get();
    }
}
```

Nếu phương thức nghiệp vụ được service activator gọi trả `null` hoặc `void`, endpoint có thể kết thúc mà không phát reply. Với service activator cần bắt buộc có kết quả, bật `requiresReply(true)` trên cấu hình endpoint phù hợp để lỗi xuất hiện ngay tại bước vi phạm. [Hợp đồng service activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

Nếu cần ghi audit **và tiếp tục**, phương thức phải trả lại dữ liệu hoặc dùng một nhánh quan sát riêng. Ví dụ đoạn DSL:

```java
.<String>handle((payload, headers) -> {
    System.out.println("AUDIT: " + payload);
    return payload;
})
```

Đừng đặt một handler kết thúc luồng trước bước vẫn cần chạy, rồi chờ bước đó nhận thông điệp.

### 5.2. Có kết quả nhưng chủ động bỏ kết quả

`nullChannel` là một channel nhận thông điệp rồi loại bỏ nó. Khái niệm này khác với giá trị Java `null`. Bạn có thể chuyển output hợp lệ vào channel này nếu hợp đồng thực sự cho phép kết thúc tại đó. [Special Channels](https://docs.spring.io/spring-integration/reference/channel/special-channels.html).

```java
@Bean
public IntegrationFlow normalizeAndDiscardFlow() {
    return IntegrationFlow.from("normalizeAndDiscardInput")
            .<String, String>transform(String::strip)
            .channel("nullChannel")
            .get();
}
```

Đoạn này là một bean trong cấu hình đã bật Integration. Transformer vẫn phải tạo kết quả trước khi channel cuối loại bỏ nó. Thay `String::strip` bằng lambda trả `null` vẫn là lỗi; `nullChannel` không sửa hợp đồng của transformer.

Không trỏ kết quả vào `nullChannel` chỉ để làm biến mất lỗi thiếu đích nhận nếu caller vẫn cần câu trả lời.

### 5.3. Có nhiều hướng xử lý nghiệp vụ

Nếu một mã sản phẩm phải được chuyển sang nhánh “hợp lệ”, “không tồn tại” hoặc “cần bổ sung dữ liệu”, router làm rõ các hướng đó. Một kết quả nghiệp vụ như `NOT_FOUND` cũng có thể được mô hình hóa bằng DTO khác `null`, rồi router chọn kênh theo trạng thái.

Quyết định thiết kế có thể đối chiếu như sau:

| Nhu cầu | Thành phần phù hợp |
| --- | --- |
| Chuyển dữ liệu từ dạng A sang B | Transformer |
| Quyết định có cho thông điệp đi tiếp hay không | Filter |
| Chọn một hay nhiều nhánh xử lý | Router |
| Gọi nghiệp vụ và cho phép không tạo reply | Service activator |
| Nhận rồi chủ động bỏ một output đã tồn tại | `nullChannel` |

## 6. Có kết quả nhưng không đến nơi mong đợi

### 6.1. Không cấu hình output channel chưa chắc là lỗi

Một endpoint tạo reply có thể gửi đến output channel được cấu hình rõ; nếu không có, framework có thể dùng `replyChannel` của request. Gateway thường cung cấp địa chỉ trả lời này. Bởi vậy, transformer cuối luồng request–reply không nhất thiết phải khai báo channel đầu ra riêng. [Cơ chế chọn kênh trả lời](https://docs.spring.io/spring-integration/reference/service-activator.html).

Ví dụ dưới đây dành cho caller dùng request–reply, nơi request đã có `replyChannel`:

```java
@Bean
public IntegrationFlow normalizeRequestFlow() {
    return IntegrationFlow.from("normalizeRequests")
            .<String, String>transform(
                    text -> text.strip().toUpperCase(java.util.Locale.ROOT))
            .get();
}
```

Nếu gửi trực tiếp bằng `input.send(message)` mà message không có `replyChannel`, đồng thời endpoint cũng không có output channel, kết quả có thể đã được tính nhưng không xác định được nơi gửi. Đây là lỗi định tuyến reply, cần phân biệt với việc phép chuyển đổi trả về `null`.

Ngược lại, nếu đã cấu hình output channel rõ ràng, đừng giả định kết quả sẽ đồng thời tự quay về gateway. Hãy lần theo endpoint cuối cùng trên nhánh output đó.

### 6.2. QueueChannel cần được lấy thông điệp ra

Với `QueueChannel`, output có thể đang nằm trong bộ đệm. Một consumer đọc từ channel dạng pollable cần poller; trong kiểm thử, có thể gọi `receive(timeout)` trực tiếp. Gắn consumer vào hàng đợi mà thiếu cơ chế polling là một vấn đề cấu hình độc lập với transformer. [Cấu hình channel](https://docs.spring.io/spring-integration/reference/6.5/channel/configuration.html).

Trong ví dụ ở mục 4, queue là điểm quan sát cuối. Không cần poller cho transformer vì input của nó là `DirectChannel`; test lấy kết quả từ các queue bằng `receive(...)`.

Nếu dùng `DirectChannel` làm output mà không có subscriber, hãy tìm lỗi dispatch. Một send thất bại không có nghĩa transformer chưa tạo dữ liệu. Nếu có nhiều consumer cạnh tranh trên cùng một kênh point-to-point, đừng mặc định tất cả consumer đều nhận bản sao.

### 6.3. Giữ metadata khi tự tạo Message

Khi phương thức trả về toàn bộ `Message<?>`, bạn đang quyết định cả payload lẫn headers của kết quả. Việc tạo message mới mà bỏ các header cần thiết có thể làm một endpoint phía sau mất thông tin hồi đáp hoặc tương quan.

Ví dụ phương thức dùng với transformer nhận cả message và bảo toàn các header đầu vào có thể sao chép:

```java
import java.util.Locale;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class ProductCodeTransformer {

    public Message<String> normalize(Message<String> input) {
        return MessageBuilder
                .withPayload(input.getPayload().strip().toUpperCase(Locale.ROOT))
                .copyHeaders(input.getHeaders())
                .setHeader("normalized", true)
                .build();
    }
}
```

Đây là ví dụ bảo toàn metadata trong luồng nội bộ; ở ranh giới hệ thống phải chọn tập header được phép truyền. `id` và `timestamp` có quy tắc do framework quản lý, không dùng chúng làm cam kết định danh nghiệp vụ xuyên toàn bộ phép biến đổi. Phép sao chép header cũng không cho phép payload trở thành `null`.

## 7. Gateway chờ reply dù transformer đã chạy

Giả sử caller gọi một gateway có phương thức trả `String`, nhưng sau transformer là một handler chỉ ghi log rồi kết thúc. Transformer đã hoạt động đúng; nhánh xử lý cuối không tạo câu trả lời mà gateway mong đợi.

Ba lựa chọn thiết kế thường gặp:

1. Giữ hợp đồng request–reply và trả kết quả thành công hoặc từ chối một cách rõ ràng.
2. Nếu không cần kết quả, dùng gateway có phương thức trả `void` và luồng một chiều phù hợp.
3. Nếu từ chối là lỗi, ném hoặc chuyển lỗi theo chính sách của gateway, thay vì làm request mất reply âm thầm.

Đặt thời gian chờ hữu hạn giúp tránh chờ vô hạn nhưng không tạo ra reply còn thiếu. `replyTimeout` cũng không ngắt một handler chạy lâu trên cùng caller thread qua `DirectChannel`; nó điều khiển giai đoạn đợi reply. Khi không có reply, gateway có thể trả `null` hoặc ném lỗi timeout theo cấu hình và kiểu lời gọi. [Gateway khi không nhận phản hồi](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

Ví dụ, chuyển dữ liệu bị từ chối sang một queue để vận hành kiểm tra là hợp lý đối với luồng một chiều. Với gateway đồng bộ, riêng hành động đưa request vào queue từ chối chưa đủ: vẫn cần một đường phản hồi hoặc chính sách báo lỗi cho caller.

## 8. Tìm lỗi theo ranh giới luồng thực thi

### 8.1. Luồng đồng bộ

Với `DirectChannel` mặc định, handler chạy trên thread gửi. Exception từ transformer có thể đi ngược về `send(...)` hoặc caller của gateway. Khi gửi trực tiếp qua `MessageChannel`, không giả định việc đặt header `errorChannel` sẽ tự chuyển mọi lỗi đồng bộ thành thông điệp lỗi.

### 8.2. Luồng bất đồng bộ

Khi có `ExecutorChannel` hoặc poller tiêu thụ một queue, lỗi xử lý xảy ra ở thread khác. Cơ chế xử lý lỗi của tác vụ Integration có thể phát `ErrorMessage` tới kênh được chỉ định qua header `errorChannel`, hoặc kênh lỗi mặc định. Caller có thể đã hoàn tất việc gửi trước lúc transformer thất bại. [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Thông tin phục vụ chẩn đoán nên gồm:

- Tên endpoint và channel sát vị trí lỗi.
- Mã nghiệp vụ hoặc correlation ID để nối các mốc xử lý.
- Kiểu payload, trạng thái chấp nhận/từ chối và loại exception.
- Failed message nếu có, với dữ liệu nhạy cảm được che phù hợp.

Tránh bắt toàn bộ exception trong hàm chuyển đổi rồi `return null`. Ví dụ sai:

```java
try {
    return convert(payload);
} catch (RuntimeException ex) {
    return null; // Che nguyên nhân chuyển đổi, rồi lại vi phạm hợp đồng reply.
}
```

Hãy để lỗi đi vào cơ chế xử lý đã thiết kế, hoặc bọc lỗi có giữ nguyên cause. Retry phù hợp với lỗi tạm thời; retry một nhánh luôn trả `null` chỉ lặp lại sai sót của logic.

## 9. Kiểm thử hành vi bằng các thông điệp cụ thể

Bộ kiểm thử sau đi cùng `TransformerNoOutputConfig` ở mục 4. Đặt hai lớp cùng package hoặc khai báo import phù hợp. Test dùng context riêng của cấu hình minh họa; không có consumer khác tranh lấy message khỏi output queue.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.ReplyRequiredException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(TransformerNoOutputConfig.class)
class TransformerNoOutputTest {

    @Autowired
    @Qualifier("brokenInput")
    DirectChannel brokenInput;

    @Autowired
    @Qualifier("brokenOutput")
    QueueChannel brokenOutput;

    @Autowired
    @Qualifier("cleanInput")
    DirectChannel cleanInput;

    @Autowired
    @Qualifier("acceptedOutput")
    QueueChannel acceptedOutput;

    @Autowired
    @Qualifier("rejectedOutput")
    QueueChannel rejectedOutput;

    @Test
    void nullResultFailsInsteadOfSilentlyDropping() {
        MessagingException failure = assertThrows(
                MessagingException.class,
                () -> brokenInput.send(
                        MessageBuilder.withPayload("   ").build()));

        assertTrue(hasCause(failure, ReplyRequiredException.class));
        assertNull(brokenOutput.receive(0));
    }

    @Test
    void acceptedInputProducesNormalizedOutput() {
        assertTrue(cleanInput.send(MessageBuilder
                .withPayload(" ab-123 ")
                .setHeader("businessKey", "request-001")
                .build()));

        Message<?> output = acceptedOutput.receive(1000);
        assertNotNull(output);
        assertEquals("AB-123", output.getPayload());
        assertEquals("request-001", output.getHeaders().get("businessKey"));
        assertNull(acceptedOutput.receive(0));
        assertNull(rejectedOutput.receive(0));
    }

    @Test
    void rejectedInputGoesToDiscardChannel() {
        assertTrue(cleanInput.send(MessageBuilder
                .withPayload("   ")
                .setHeader("businessKey", "request-002")
                .build()));

        Message<?> rejected = rejectedOutput.receive(1000);
        assertNotNull(rejected);
        assertEquals("   ", rejected.getPayload());
        assertEquals("request-002", rejected.getHeaders().get("businessKey"));
        assertNull(acceptedOutput.receive(0));
        assertNull(rejectedOutput.receive(0));
    }

    private static boolean hasCause(
            Throwable failure, Class<? extends Throwable> expectedType) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Các assertion phân biệt ba kết quả: lỗi hợp đồng, output hợp lệ và thông điệp đi vào nhánh từ chối. Assertion không chỉ dựa vào việc queue đầu ra rỗng, vì queue rỗng cũng có thể do message chưa tới endpoint hoặc đã bị consumer khác lấy.

Trong cấu hình này, việc xử lý qua input `DirectChannel` hoàn thành trước khi `send(...)` trả về. Vì thế `receive(0)` đủ để kiểm tra không có message thừa tại các queue không có consumer cạnh tranh. Với luồng bất đồng bộ, cần đồng bộ hóa việc hoàn thành tác vụ và quan sát kênh lỗi trước khi kết luận “không có output”; một lần receive ngắn chưa đủ.

Các đoạn kiểm thử là mã thực hành cho người học. Chúng cần được chạy trong môi trường dependency tương thích của dự án; bài viết không coi kết quả kỳ vọng là bằng chứng đã thực thi test.

## 10. Liên hệ với aggregator và quan sát vận hành

Một thông điệp không đến downstream có thể ảnh hưởng đến nhiều request trong cùng nhóm. Ví dụ splitter phát ba phần tử có cùng correlation ID và kích thước nhóm dự kiến là ba. Nếu một phần tử bị loại sau splitter, aggregator dùng điều kiện hoàn tất theo kích thước nhóm có thể chỉ nhận hai phần tử và tiếp tục chờ.

Khi thêm filter vào luồng như vậy, cần xác định lại hợp đồng của nhóm: lọc trước khi tạo tập phần tử nếu phù hợp, phát kết quả từ chối có cấu trúc để nhóm vẫn hoàn tất, hoặc thiết kế release/expiry policy cho trường hợp thiếu phần tử. Không giảm số lượng chờ một cách tùy ý vì có thể phát kết quả chưa đầy đủ.

Ở mức vận hành, nên phân biệt các số đếm theo từng nhánh:

```text
đã nhận → được chấp nhận → chuyển đổi thành công → gửi sang bước kế
       ↘ bị từ chối
                          ↘ chuyển đổi lỗi
```

Đây là mô hình quan sát cho ví dụ, không phải đẳng thức áp dụng nguyên xi cho mọi hệ thống. Retry, fan-out, splitter và xử lý lại có thể làm số lần xử lý khác số request nghiệp vụ. Dùng mã nghiệp vụ để đối chiếu cùng một request qua các mốc, thay vì so sánh tổng số một cách máy móc.

## 11. Trình tự chẩn đoán có thể áp dụng ngay

1. Xác nhận request đi vào đúng channel và endpoint transformer đang hoạt động.
2. Kiểm tra mọi nhánh `return`, khối `catch` và lời gọi thư viện trong phương thức chuyển đổi.
3. Tách rõ trường hợp trả `null`, có payload rỗng và ném exception.
4. Kiểm tra đích gửi kết quả: output channel cấu hình rõ, rồi đường reply của request.
5. Xem loại channel, subscriber, poller và các consumer cạnh tranh.
6. Lần theo các bước sau transformer, đặc biệt filter, router và handler có thể kết thúc luồng.
7. Đối chiếu hợp đồng gateway: caller cần reply, chấp nhận từ chối hay chỉ gửi một chiều.
8. Viết một kiểm thử với đầu vào gây lỗi và xác nhận đúng một kết cục đã thiết kế: output, từ chối hoặc lỗi.

Một transformer không tạo output cần được phân tích bằng cả hợp đồng chuyển đổi lẫn đường đi của thông điệp. Khi quyết định chuyển đổi, loại bỏ và kết thúc luồng được đặt đúng endpoint, nguyên nhân sẽ dễ tái hiện và kết quả của mỗi nhánh sẽ dễ kiểm chứng.
