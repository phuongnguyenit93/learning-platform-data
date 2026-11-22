# Timeout mặc định của client

Một gRPC client có thể gọi server thành công trong môi trường phát triển nhưng lại giữ request quá lâu khi server chậm, mạng gián đoạn hoặc một endpoint không còn phản hồi. Nguyên nhân thường gặp là lời gọi không có **deadline**. Trong gRPC Java, nếu client không đặt deadline và không có chính sách timeout từ cấu hình dịch vụ, lời gọi có thể tiếp tục chờ cho tới khi hoàn tất, bị hủy hoặc kết nối gặp lỗi.

Với ứng dụng Spring, ta thường muốn đặt một **timeout mặc định** để mọi RPC có giới hạn thời gian hợp lý, đồng thời cho phép từng nghiệp vụ đặt deadline riêng khi cần. Bài học này tập trung vào cách thiết lập chính sách mặc định, thứ tự ưu tiên với deadline tường minh, lựa chọn timeout theo loại RPC và kiểm chứng hành vi khi hết hạn. Nội dung thuộc phần Spring client của mô-đun **SPRING_GRPC**, nơi client được xây dựng từ hợp đồng Protocol Buffers và generated Java stub, đồng thời xử lý metadata, status, interceptor, TLS, streaming, kiểm thử và độ tin cậy.

## 1. Timeout của client thực chất là deadline của RPC

Trong gRPC, client giới hạn thời gian một RPC bằng **deadline**: một thời điểm tuyệt đối mà sau đó lời gọi được xem là hết hạn. API Java thường nhận một khoảng thời gian rồi chuyển nó thành deadline, ví dụ:

```java
HelloReply reply = greeterStub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .sayHello(request);
```

`withDeadlineAfter(2, SECONDS)` tạo một bản stub có deadline cho lần gọi đó. Nếu RPC chưa hoàn tất trong hai giây, client kết thúc lời gọi với status `DEADLINE_EXCEEDED`. Deadline là ngân sách cho toàn bộ RPC ở phía client, bao gồm thời gian chờ kết nối/sẵn sàng và trao đổi với server; nó không chỉ đo thời gian server chạy hàm nghiệp vụ.

Phân biệt các khái niệm sau:

| Khái niệm | Ý nghĩa | Có thay thế deadline RPC không? |
| --- | --- | --- |
| RPC deadline / timeout | Giới hạn thời gian một lời gọi được phép tồn tại. | Đây là cơ chế cần dùng để giới hạn RPC. |
| Connection timeout | Thời gian hoặc chính sách liên quan tới việc thiết lập kết nối transport. | Không. Channel có thể tái kết nối; RPC vẫn cần deadline riêng. |
| Keepalive | Cơ chế kiểm tra kết nối HTTP/2 còn hoạt động bằng ping. | Không. Keepalive không đặt thời gian tối đa cho một RPC. |
| Retry backoff | Khoảng chờ giữa các lần thử lại. | Không. Các lần thử vẫn tiêu thụ ngân sách deadline của RPC. |
| HTTP request timeout | Giới hạn thời gian request HTTP phía trước chờ ứng dụng. | Không. Cần truyền ngân sách còn lại xuống RPC để tránh RPC sống lâu hơn request gốc. |

Mặc định, gRPC Java không tự đặt một deadline hữu hạn cho mọi RPC. Vì vậy, nếu ứng dụng không áp dụng chính sách mặc định và người gọi cũng không dùng `withDeadlineAfter(...)`, một RPC có thể chờ rất lâu. Đây là lý do nên có timeout mặc định tại client.

## 2. Chọn một chính sách mặc định phù hợp

Timeout mặc định cần phản ánh thời gian mà ứng dụng có thể chờ dịch vụ từ xa, không nên lấy một con số tùy ý cho mọi trường hợp. Một truy vấn dữ liệu nhỏ thường có ngân sách ngắn; một RPC tổng hợp hoặc xử lý nhiều bước có thể cần dài hơn. Với streaming, timeout thường áp dụng cho **toàn bộ thời lượng stream**, nên một giá trị ngắn như hai giây có thể phù hợp với unary RPC nhưng không phù hợp với một subscription được thiết kế để mở lâu.

Khi chọn giá trị, hãy xem xét:

- **SLO và latency thực tế:** dùng phân phối độ trễ ở percentile cao (ví dụ p95/p99), cộng phần ngân sách cần thiết cho mạng và xử lý phía client.
- **Request timeout ở tầng trên:** nếu HTTP request chỉ được phép tồn tại ba giây, gRPC call không nên có deadline năm giây.
- **Số RPC trong một luồng nghiệp vụ:** nếu một request gọi lần lượt nhiều dịch vụ, tổng ngân sách cần bao phủ các bước đó; không cấp lại toàn bộ timeout cho mỗi bước mà không tính thời gian đã tiêu thụ.
- **Loại RPC:** unary thường có thời hạn ngắn; server/client/bidirectional streaming cần chính sách phù hợp với tuổi thọ stream và khả năng cancellation.
- **Retry:** các lần thử lại dùng chung ngân sách thời gian của lời gọi; timeout quá ngắn có thể làm retry không có cơ hội hoàn tất.

Ví dụ, một ứng dụng có thể đặt mặc định 2 giây cho `SayHello`, 800 mili giây cho `GetStock`, và 30 giây cho một RPC tạo báo cáo. Giá trị cụ thể cần được xác nhận bằng đo đạc và SLO của hệ thống.

## 3. Đặt timeout mặc định bằng gRPC Service Config

gRPC hỗ trợ cấu hình theo service/method thông qua **Service Config**. Trong gRPC Java, `ManagedChannelBuilder.defaultServiceConfig(...)` nhận một map cấu hình. Mỗi `methodConfig` có thể áp dụng timeout cho một phương thức hoặc nhiều phương thức cùng service.

Ví dụ dưới đây đặt timeout mặc định hai giây cho mọi RPC thuộc service `greeting.v1.Greeter`, trừ khi một cấu hình method cụ thể hơn được khai báo:

```java
import java.util.List;
import java.util.Map;

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(
                Map.of(
                        "name", List.of(
                                Map.of("service", "greeting.v1.Greeter")
                        ),
                        "timeout", "2s"
                )
        )
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///greeter.internal:7443")
        .useTransportSecurity()
        .defaultServiceConfig(serviceConfig)
        .build();
```

Tên service trong `name` phải khớp với tên đầy đủ trong hợp đồng Protobuf: package `greeting.v1` cộng service `Greeter`. Nếu muốn áp dụng cho một method cụ thể, bổ sung `"method", "SayHello"` vào map `name`. `timeout` là chuỗi duration theo định dạng Service Config, ví dụ `"800ms"`, `"2s"` hoặc `"1m"`.

Có thể định nghĩa timeout khác nhau theo method:

```java
Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(
                Map.of(
                        "name", List.of(Map.of(
                                "service", "inventory.v1.Inventory",
                                "method", "GetStock")),
                        "timeout", "800ms"
                ),
                Map.of(
                        "name", List.of(Map.of(
                                "service", "inventory.v1.Inventory",
                                "method", "WatchStock")),
                        "timeout", "30s"
                )
        )
);
```

Trong ví dụ này, `GetStock` có ngân sách ngắn còn `WatchStock` được phép tồn tại lâu hơn. Đối với stream vô hạn, deadline 30 giây vẫn sẽ kết thúc stream sau 30 giây; nếu nghiệp vụ cần subscription lâu dài, phải cân nhắc cách quản lý tuổi thọ stream, heartbeat, cancellation và tái đăng ký thay vì coi timeout dài là stream vô hạn.

`defaultServiceConfig(...)` là **cấu hình mặc định của channel**. Nếu NameResolver cung cấp Service Config riêng, cấu hình do resolver cung cấp có thể được ưu tiên theo hành vi của gRPC và cài đặt channel. Do đó, khi dùng DNS/service discovery, cần kiểm tra cấu hình thực tế mà client nhận được; không giả định map mặc định luôn thắng cấu hình do resolver phân phối. Nếu muốn kiểm soát tập trung bằng cấu hình tĩnh, cần thống nhất chính sách resolver/service config của môi trường.

## 4. Đưa timeout mặc định vào cấu hình Spring Boot

Để thay đổi timeout theo môi trường mà không sửa Java code, đặt nó trong `application.yml`:

```yaml
app:
  grpc:
    greeter:
      target: dns:///greeter.internal:7443
      default-timeout: 2s
```

Bind cấu hình vào `Duration`:

```java
package com.example.client;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.grpc.greeter")
public record GreeterClientProperties(
        String target,
        Duration defaultTimeout) {

    public GreeterClientProperties {
        if (target == null || target.isBlank()) {
            throw new IllegalArgumentException("gRPC target không được rỗng");
        }
        if (defaultTimeout == null || defaultTimeout.isZero()
                || defaultTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "default-timeout phải lớn hơn 0");
        }
    }
}
```

Spring Boot chuyển `2s` thành `Duration.ofSeconds(2)`. Trong sản phẩm thực tế nên giới hạn giá trị tối đa để một cấu hình sai không khiến RPC chờ quá lâu. Nếu dùng `toNanos()` hoặc `toMillis()` khi tạo deadline, cũng cần tránh duration quá lớn gây tràn số hoặc duration quá nhỏ bị làm tròn về 0.

## 5. Cách 1: áp dụng mặc định bằng Client Interceptor

Một client interceptor có thể áp dụng deadline khi lời gọi chưa có deadline tường minh. Cách này hữu ích khi muốn đặt **một fallback chung** cho mọi method đi qua channel, không phải thêm `withDeadlineAfter(...)` ở từng application service.

`DefaultDeadlineInterceptor.java`:

```java
package com.example.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Deadline;
import io.grpc.MethodDescriptor;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class DefaultDeadlineInterceptor implements ClientInterceptor {

    private final Duration defaultTimeout;

    public DefaultDeadlineInterceptor(Duration defaultTimeout) {
        if (defaultTimeout == null || defaultTimeout.isZero()
                || defaultTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "defaultTimeout phải lớn hơn 0");
        }
        this.defaultTimeout = defaultTimeout;
    }

    @Override
    public <RequestT, ResponseT> ClientCall<RequestT, ResponseT> interceptCall(
            MethodDescriptor<RequestT, ResponseT> method,
            CallOptions callOptions,
            Channel next) {

        CallOptions effectiveOptions = callOptions;
        if (callOptions.getDeadline() == null) {
            long timeoutNanos = defaultTimeout.toNanos();
            effectiveOptions = callOptions.withDeadline(
                    Deadline.after(timeoutNanos, TimeUnit.NANOSECONDS));
        }

        return next.newCall(method, effectiveOptions);
    }
}
```

Interceptor chỉ đặt deadline khi `CallOptions` chưa có deadline. Nếu application service đã gọi `stub.withDeadlineAfter(500, MILLISECONDS)`, interceptor giữ nguyên deadline 500 ms thay vì thay bằng mặc định 2 giây. Đây là ngữ nghĩa của **default**: lấp chỗ trống, không ghi đè chính sách cụ thể mà caller đã chọn.

Đăng ký interceptor trên channel:

```java
package com.example.client;

import com.example.contract.grpc.GreeterGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GreeterClientProperties.class)
public class GreeterClientConfiguration {

    @Bean(name = "greeterChannel", destroyMethod = "shutdown")
    ManagedChannel greeterChannel(GreeterClientProperties properties) {
        return ManagedChannelBuilder.forTarget(properties.target())
                .useTransportSecurity()
                .intercept(new DefaultDeadlineInterceptor(
                        properties.defaultTimeout()))
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(
            @org.springframework.beans.factory.annotation.Qualifier("greeterChannel")
            ManagedChannel channel) {
        return GreeterGrpc.newBlockingStub(channel);
    }
}
```

Trong ví dụ, target dùng TLS; khi chạy local không TLS, hãy cấu hình `usePlaintext()` theo profile phát triển. Channel được Spring quản lý và `destroyMethod` yêu cầu đóng khi context dừng. Interceptor áp dụng cho mọi RPC đi qua channel này, vì vậy nếu một channel dùng cho cả unary và streaming, timeout mặc định phải hợp lý cho tất cả các method hoặc nên chuyển sang chính sách theo method ở Service Config.

**Lưu ý khi dùng cả Service Config và interceptor:** hai cơ chế đều có thể ảnh hưởng đến deadline của RPC. Tránh cấu hình hai giá trị mâu thuẫn mà không xác định chính sách hiệu lực. Hãy chọn một nguồn mặc định chính, sau đó dùng deadline tường minh ở caller cho trường hợp đặc biệt. Nếu hệ thống nhận Service Config từ resolver, kiểm tra precedence và deadline hiệu lực bằng integration test.

## 6. Cách 2: mặc định theo method bằng Service Config trong Spring

Khi timeout cần khác nhau theo method, Service Config thường thể hiện ý định rõ hơn một interceptor chung. Tạo map cấu hình trong một lớp cấu hình riêng:

```java
package com.example.client;

import com.example.contract.grpc.GreeterGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GreeterClientProperties.class)
public class GreeterServiceConfigClientConfiguration {

    @Bean(name = "greeterChannel", destroyMethod = "shutdown")
    ManagedChannel greeterChannel(GreeterClientProperties properties) {
        Map<String, ?> serviceConfig = Map.of(
                "methodConfig", List.of(
                        Map.of(
                                "name", List.of(Map.of(
                                        "service", "greeting.v1.Greeter",
                                        "method", "SayHello")),
                                "timeout", properties.defaultTimeout().toMillis() + "ms"
                        )
                )
        );

        return ManagedChannelBuilder.forTarget(properties.target())
                .useTransportSecurity()
                .defaultServiceConfig(serviceConfig)
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(ManagedChannel greeterChannel) {
        return GreeterGrpc.newBlockingStub(greeterChannel);
    }
}
```

Đây là **phương án thay thế** cho cấu hình interceptor ở phần 5. Không đặt hai lớp `@Configuration` có cùng bean name `greeterChannel` và `greeterBlockingStub` trong cùng context. Service Config áp dụng timeout cho method đã khai báo; nếu cần một default chung cho mọi method, có thể bỏ trường `method` và chỉ giữ tên service trong `name`.

Khi cấu hình theo method, cần đảm bảo chuỗi service/method khớp chính xác tên trong `.proto`, kể cả package. Sai tên có thể khiến method không khớp cấu hình mong muốn và RPC không nhận timeout đó. Kiểm thử cần gọi method thật, chờ server chậm và xác minh status `DEADLINE_EXCEEDED`, không chỉ kiểm tra map đã được tạo.

## 7. Caller có thể đặt timeout riêng như thế nào?

Default timeout không nên loại bỏ quyền kiểm soát deadline theo nghiệp vụ. Một truy vấn tồn kho nhanh có thể yêu cầu 300 ms; một báo cáo tổng hợp có thể cần 5 giây. Caller tạo bản stub riêng cho từng RPC:

```java
import com.example.contract.grpc.HelloRequest;
import com.example.contract.grpc.HelloReply;
import java.util.concurrent.TimeUnit;

HelloRequest request = HelloRequest.newBuilder()
        .setName("Lan")
        .build();

// Dùng deadline cụ thể 500 ms cho thao tác nhạy về độ trễ.
HelloReply quickReply = greeterStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .sayHello(request);

// Không đặt deadline tại caller: dùng chính sách mặc định của client.
HelloReply normalReply = greeterStub.sayHello(request);
```

Với interceptor ở phần 5, lời gọi thứ nhất giữ 500 ms, lời gọi thứ hai nhận default timeout. `withDeadlineAfter(...)` trả về stub mới; bean stub dùng chung không bị thay đổi sau một request. Nếu caller đặt deadline dài hơn default, interceptor minh họa vẫn giữ deadline caller vì nó chỉ lấp trường hợp chưa có deadline. Nếu chính sách của tổ chức là **giới hạn tối đa** thay vì default, cần viết interceptor so sánh hai deadline và chọn deadline sớm hơn; đó là một policy khác và cần được đặt tên, kiểm thử rõ ràng.

Nếu request chạy bên trong một gRPC `Context` đã có deadline, gRPC Java có thể sử dụng deadline còn lại ngắn hơn của context khi tạo RPC. Khi ứng dụng chuyển ngân sách từ HTTP request sang gRPC, hãy truyền **thời gian còn lại**, không cấp lại nguyên timeout ban đầu ở mỗi service hop.

## 8. Deadline ảnh hưởng đến server và retry ra sao?

Khi client đặt deadline, gRPC truyền thông tin timeout còn lại trong giao thức. Server có thể nhận biết RPC hết hạn hoặc bị hủy và dừng công việc nếu implementation kiểm tra cancellation/context. Điều này giúp giảm việc server tiếp tục xử lý một yêu cầu mà client không còn chờ.

Tuy nhiên, deadline **không phải rollback giao dịch**. Nếu server đã ghi dữ liệu trước khi hết hạn, client nhận `DEADLINE_EXCEEDED` không có nghĩa thao tác chưa xảy ra. Với RPC tạo đơn, thanh toán hoặc cập nhật tồn kho, cần idempotency key, kiểm tra trạng thái và hợp đồng retry phù hợp.

Khi bật retry bằng Service Config, các lần thử tiêu thụ ngân sách deadline của RPC; không nên coi mỗi attempt có một timeout mặc định mới. Ví dụ một RPC có deadline hai giây, lần đầu đã mất 1,5 giây thì lần thử sau chỉ còn phần ngân sách còn lại. Backoff và retry policy phải nằm trong ngân sách tổng.

Phân biệt các status khi chẩn đoán:

| Status | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `DEADLINE_EXCEEDED` | RPC không hoàn tất trước deadline. | Xem latency, tải server, deadline caller và timeout mặc định. |
| `UNAVAILABLE` | Dịch vụ/transport tạm thời không sẵn sàng. | Kiểm tra DNS, mạng, TLS, server và policy retry. |
| `CANCELLED` | Lời gọi bị caller, context hoặc hệ thống hủy. | Xác định request gốc bị hủy hay ứng dụng đang shutdown. |
| `RESOURCE_EXHAUSTED` | Server hoặc transport từ chối do vượt giới hạn tài nguyên/chính sách. | Kiểm tra tải, quota, giới hạn message và retry-after nếu có. |
| `INVALID_ARGUMENT` | Request không hợp lệ theo hợp đồng/nghiệp vụ. | Sửa dữ liệu; tăng timeout thường không giải quyết được. |

Không chuyển mọi `DEADLINE_EXCEEDED` thành `UNAVAILABLE` trong tầng ứng dụng. Giữ được phân biệt giúp metrics và quyết định retry chính xác hơn.

## 9. Timeout mặc định với streaming RPC

Deadline của streaming RPC áp dụng cho **toàn bộ RPC**, không phải thời gian tối đa giữa hai message. Nếu một server-streaming RPC được thiết kế gửi dữ liệu liên tục trong 10 phút nhưng channel có default timeout 2 giây, stream sẽ bị kết thúc sớm dù server vẫn hoạt động.

Có ba hướng thiết kế thường gặp:

1. **Timeout theo method:** dùng Service Config để đặt thời hạn dài hơn cho streaming method, trong khi unary method vẫn ngắn.
2. **Deadline do caller quyết định:** dùng stub `withDeadlineAfter(...)` theo tuổi thọ công việc cụ thể; nếu stream cần tồn tại lâu, chọn một giới hạn có chủ đích.
3. **Stream sống lâu có tái đăng ký:** không đặt một RPC vô hạn nếu hệ thống cần quản lý kết nối; dùng cancellation, heartbeat, resume token/offset và reconnect theo chính sách ứng dụng.

Đừng nhầm deadline với idle timeout. Nếu yêu cầu là “hủy stream khi không có message trong 30 giây”, cần cơ chế theo dõi thời gian không hoạt động hoặc heartbeat; một deadline 30 giây sẽ hủy stream sau 30 giây kể từ lúc bắt đầu dù stream có gửi message đều đặn.

Với client-streaming và bidirectional-streaming, client cũng cần xử lý callback `onError`/`onCompleted`, đóng request observer và cancellation khi hết deadline. Đối với async stub, status hết hạn thường đến trong `onError(Throwable)`; có thể dùng `Status.fromThrowable(error)` để đọc `DEADLINE_EXCEEDED`.

## 10. Kiểm thử timeout mặc định

Kiểm thử nên chứng minh ba hành vi riêng:

- RPC không đặt deadline tường minh nhận được timeout mặc định.
- RPC đặt deadline ngắn hơn vẫn dùng deadline ngắn đó.
- RPC chậm vượt giới hạn kết thúc với `DEADLINE_EXCEEDED`, callback hoặc blocking call được hoàn tất theo đúng cách.

Có thể dùng gRPC in-process server với một implementation cố ý trì hoãn response. Test nên chạy trên executor phù hợp để tác vụ server chậm không chặn chính luồng kiểm thử; dùng `CountDownLatch` hoặc scheduler để kiểm soát thời điểm trả response thay vì `Thread.sleep()` dài và không ổn định. Khi kiểm tra deadline, đặt thời gian test đủ chênh lệch để tránh phụ thuộc lịch chạy của CI.

Ví dụ ý tưởng test với blocking stub:

```java
// Greeter server thử nghiệm chưa gửi response trong khoảng thời gian timeout.
// Channel được cấu hình DefaultDeadlineInterceptor(Duration.ofMillis(100)).
assertThrows(StatusRuntimeException.class, () ->
        greeterBlockingStub.sayHello(request));
```

Sau assertion, kiểm tra `Status.fromThrowable(exception).getCode()` là `DEADLINE_EXCEEDED`. Đoạn mã giả định server test giữ RPC đủ lâu để deadline hết trước khi trả response; cần giải phóng latch và shutdown server/channel trong `finally` để test không rò tài nguyên.

Với async stub, dùng observer hoặc `CompletableFuture` để chờ kết quả test có giới hạn, rồi xác minh lỗi được chuyển về nhánh `onError`. Nếu dùng `CompletableFuture.get(...)`, chỉ dùng trong test và luôn đặt thời hạn cho chính thao tác chờ của test; không biến production async call thành blocking bằng cách gọi `.get()` ngay sau RPC.

In-process test xác minh logic deadline và status ở client/server gRPC nhưng không kiểm tra TLS, DNS, proxy hoặc HTTP/2 trên mạng. Cần integration test qua TCP/TLS khi muốn xác minh timeout trong môi trường triển khai. Cũng nên test server có phản ứng với cancellation, để tránh chỉ xác minh client ngừng chờ trong khi server vẫn tiếp tục công việc tốn tài nguyên.

## 11. Quan sát timeout trong production

Một default timeout chỉ hữu ích khi đội vận hành biết nó đang có hiệu lực và có thể điều chỉnh theo dữ liệu thực tế. Nên theo dõi theo **service/method**:

- Tổng số RPC và tỷ lệ `DEADLINE_EXCEEDED`.
- Latency ở p50/p95/p99 so với timeout được cấu hình.
- Số lần retry, số attempt và thời gian backoff nếu bật retry.
- Tỷ lệ RPC bị `CANCELLED`, phân biệt client disconnect với application shutdown.
- Các method streaming kết thúc do deadline và thời lượng stream thực tế.

Log nên ghi method, logical client name, status và correlation/trace ID. Không ghi token xác thực hoặc metadata bí mật. Tránh dùng request ID làm metric label vì cardinality cao. Khi tỷ lệ timeout tăng, kiểm tra tải server, độ trễ mạng, resolver, pool/executor và deadline upstream trước khi chỉ tăng timeout. Tăng timeout có thể làm request chờ lâu hơn và tích tụ nhiều công việc đồng thời, khiến sự cố quá tải nặng hơn.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| RPC chờ rất lâu dù channel đã kết nối | Không có deadline ở caller hoặc default policy. | Đặt timeout mặc định bằng Service Config/interceptor hoặc deadline tường minh. |
| Tăng timeout kết nối nhưng RPC vẫn treo | Nhầm connect/keepalive với RPC deadline. | Giới hạn thời gian từng RPC. |
| Interceptor ghi đè deadline 300 ms thành 2 giây | Logic interceptor luôn đặt deadline mới. | Chỉ áp dụng default khi caller chưa có deadline; nếu cần max cap, chọn deadline sớm hơn. |
| Unary chạy tốt nhưng stream bị ngắt sớm | Dùng default ngắn cho mọi method. | Đặt timeout theo method hoặc chính sách stream riêng. |
| Timeout ở service thứ hai vượt request HTTP | Cấp lại toàn bộ default thay vì thời gian còn lại. | Truyền deadline/budget còn lại qua các tầng. |
| Retry khiến RPC vượt ngân sách nghiệp vụ | Coi mỗi attempt có timeout riêng không giới hạn. | Giữ deadline tổng, giới hạn retry và backoff. |
| Client nhận `DEADLINE_EXCEEDED` nhưng dữ liệu đã được ghi | Server commit trước khi nhận cancellation. | Dùng idempotency key và kiểm tra trạng thái nghiệp vụ. |
| Service Config không có hiệu lực như mong đợi | Method/service name sai hoặc resolver cung cấp config khác. | Kiểm tra full method name và Service Config thực tế. |
| Timeout cấu hình bằng 0 hoặc quá lớn | Giá trị properties không được validate. | Validate `Duration` khi Spring bind/khởi tạo bean. |

## 13. Bài tập thực hành

1. Tạo Spring gRPC client có `default-timeout: 2s`, cấu hình default deadline bằng interceptor và gọi unary RPC mà caller không đặt timeout.
2. Đặt deadline 300 ms tại một application service; xác minh interceptor giữ nguyên deadline cụ thể đó.
3. Chuyển sang Service Config và đặt timeout riêng cho hai method `GetStock` và `WatchStock`; kiểm tra đúng tên service/method trong `.proto`.
4. Làm server trì hoãn response quá deadline; xác minh blocking stub ném `StatusRuntimeException` với status `DEADLINE_EXCEEDED` và async stub đi vào `onError`.
5. Thử một server-streaming RPC gửi message liên tục lâu hơn default timeout. Phân biệt deadline toàn stream với idle timeout và điều chỉnh policy phù hợp.
6. Đặt timeout HTTP ngắn hơn gRPC default, truyền thời gian còn lại xuống client; quan sát việc request gốc kết thúc trước RPC nếu không truyền budget đúng.
7. Bật retry cho một RPC đọc idempotent, đo tổng thời gian của các attempt và xác minh tất cả vẫn nằm trong deadline tổng.

Sau bài này, bạn cần giải thích được vì sao gRPC Java không tự cấp một deadline hữu hạn cho mọi lời gọi, cách thiết lập timeout mặc định bằng Service Config hoặc interceptor, cách giữ deadline tường minh của caller, và vì sao timeout phải được chọn theo method cũng như tuổi thọ streaming RPC. Đó là nền tảng để Spring gRPC client giới hạn thời gian chờ, giảm tích tụ request và vận hành đáng tin cậy hơn khi dịch vụ từ xa chậm hoặc mất kết nối.
