# Nhận một kết quả bằng `retrieveMono`

## Mục tiêu

Khi gửi một yêu cầu RSocket và mong nhận đúng một phản hồi, dùng `RSocketRequester` để mô tả route, payload và kiểu dữ liệu trả về, sau đó gọi `retrieveMono`. Phương thức này thực hiện tương tác **Request-Response** và trả về một `Mono<T>` chứa phản hồi đã được giải mã.

## 1. `retrieveMono` hoạt động như thế nào?

RSocket hỗ trợ nhiều kiểu tương tác. Request-Response gửi một thông điệp và nhận lại một thông điệp. Đây là trường hợp phù hợp với `retrieveMono`.

Một yêu cầu thường có dạng:

```java
Mono<User> result = requester
    .route("users.find")
    .data(userId)
    .retrieveMono(User.class);
```

Từng bước trong chuỗi trên có ý nghĩa riêng:

1. `route("users.find")` đặt route trong metadata của thông điệp. Route phải khớp với route mà phía nhận đăng ký.
2. `data(userId)` cung cấp payload gửi đi. Giá trị này được encoder chuyển thành dạng dữ liệu truyền qua kết nối.
3. `retrieveMono(User.class)` khai báo kiểu phản hồi mong đợi và chọn tương tác Request-Response. Decoder chuyển payload phản hồi thành đối tượng `User`.
4. Kết quả là `Mono<User>`, tức một luồng reactive có tối đa một giá trị.

`retrieveMono` không trả về đối tượng ngay lập tức và cũng không tự biến lời gọi thành thao tác đồng bộ. Nó tạo một pipeline reactive. Khi pipeline được subscribe, yêu cầu mới được thực thi. Với kết nối được tạo bằng `RSocketRequester.Builder`, việc thiết lập kết nối cũng được thực hiện một cách minh bạch khi có request đầu tiên.

Payload là tùy chọn. Nếu route không cần dữ liệu đầu vào, có thể bỏ qua `data`:

```java
Mono<HealthStatus> status = requester
    .route("system.health")
    .retrieveMono(HealthStatus.class);
```

Route là metadata định tuyến; payload là dữ liệu nghiệp vụ. Không nhầm hai phần này với nhau.

## 2. Ví dụ chạy được với Spring Boot

Ví dụ dưới đây chạy một RSocket server và một client trong cùng ứng dụng để dễ quan sát Request-Response. Ứng dụng dùng TCP trên cổng 7000 và trao đổi một chuỗi ký tự.

### Dependency

Thêm starter sau vào phần `dependencies` của Maven project. Dùng parent hoặc BOM của Spring Boot để quản lý phiên bản:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
```

Starter cung cấp hạ tầng RSocket của Spring Boot và các codec cần thiết cho payload, bao gồm hỗ trợ JSON/CBOR khi có Jackson.

### Cấu hình server

Trong `src/main/resources/application.properties`:

```properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
```

### Responder: nhận request và tạo một response

Tạo `GreetingResponder.java`:

```java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingResponder {

    @MessageMapping("greeting")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Xin chào " + name);
    }
}
```

`@MessageMapping("greeting")` đăng ký handler cho route `greeting`. Handler nhận payload kiểu `String` và trả về `Mono<String>`. Spring Messaging dùng giá trị phát ra từ Mono làm response của request.

### Requester: gọi `retrieveMono`

Tạo `GreetingClient.java`:

```java
package example.rsocket;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingClient {

    private final RSocketRequester requester;

    public GreetingClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }

    public Mono<String> greet(String name) {
        return requester
                .route("greeting")
                .data(name)
                .retrieveMono(String.class);
    }
}
```

Spring Boot tự cấu hình bean `RSocketRequester.Builder`. Client dùng builder để tạo requester kết nối TCP tới server. Việc gọi `tcp` chuẩn bị requester; kết nối được sử dụng khi có request. Builder là prototype bean và có trạng thái cấu hình, vì vậy nên inject builder tại từng điểm cần tạo requester thay vì dùng chung một builder để tạo nhiều requester với các cấu hình khác nhau.

### Chạy thử

Tạo `RSocketDemoApplication.java`:

```java
package example.rsocket;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(GreetingClient client) {
        return args -> {
            String reply = client.greet("Lan").block(Duration.ofSeconds(5));
            System.out.println(reply);
        };
    }
}
```

Chạy ứng dụng bằng Maven:

```bash
./mvnw spring-boot:run
```

Trên Windows có thể dùng:

```powershell
.mvnw.cmd spring-boot:run
```

Kết quả mong đợi:

```text
Xin chào Lan
```

Trong ví dụ, `block(Duration)` chỉ được dùng ở ranh giới chạy thử kiểu command-line để chờ kết quả và giới hạn thời gian chờ. Trong ứng dụng reactive như WebFlux, nên trả trực tiếp `Mono<String>` cho framework hoặc ghép Mono vào pipeline hiện có, không block trên event-loop.

## 3. Chọn kiểu dữ liệu phản hồi

Đối số của `retrieveMono` là kiểu mà client muốn nhận sau khi giải mã:

```java
Mono<User> user = requester
    .route("users.find")
    .data(userId)
    .retrieveMono(User.class);
```

Nếu kiểu phản hồi có generic type, ví dụ `ApiResponse<List<User>>`, chỉ truyền `ApiResponse.class` sẽ làm mất thông tin kiểu phần tử do Java type erasure. Dùng `ParameterizedTypeReference` để giữ đầy đủ kiểu:

```java
import org.springframework.core.ParameterizedTypeReference;

Mono<ApiResponse<List<User>>> users = requester
    .route("users.search")
    .data(criteria)
    .retrieveMono(
        new ParameterizedTypeReference<ApiResponse<List<User>>>() {}
    );
```

Nếu chỉ cần chờ thao tác hoàn tất mà không cần dữ liệu phản hồi, có thể dùng kiểu `Void`:

```java
Mono<Void> completed = requester
    .route("cache.refresh")
    .data("product-cache")
    .retrieveMono(Void.class);
```

Với phản hồi `Mono<Void>`, pipeline hoàn tất sau khi dữ liệu được tiêu thụ; nó không phát ra một đối tượng nghiệp vụ để xử lý trong `doOnNext`.

Kiểu dữ liệu client khai báo phải tương thích với payload mà responder gửi về. Hai phía cũng phải có encoder/decoder phù hợp. Khi dùng Spring Framework trực tiếp, các codec cơ bản mặc định hỗ trợ `String`, `byte[]` và `ByteBuffer`; muốn trao đổi DTO JSON, CBOR hoặc định dạng khác thì cấu hình `RSocketStrategies` với encoder và decoder tương ứng. Spring Boot có thể tự cấu hình các codec phổ biến thông qua starter RSocket.

## 4. Xử lý kết quả theo cách reactive

Vì `retrieveMono` trả về `Mono<T>`, có thể kết hợp nó với các toán tử Reactor trước khi subscribe:

```java
import java.time.Duration;

Mono<String> response = requester
    .route("greeting")
    .data("Lan")
    .retrieveMono(String.class)
    .timeout(Duration.ofSeconds(3))
    .doOnNext(value -> System.out.println("Response: " + value))
    .doOnError(error ->
        System.err.println("RSocket request failed: " + error.getMessage())
    );
```

Các điểm cần nhớ:

- `doOnNext` quan sát giá trị phản hồi; nó không thay đổi giá trị đó.
- `doOnError` quan sát lỗi như lỗi kết nối, lỗi từ responder hoặc lỗi encode/decode. Lỗi vẫn được truyền tiếp trong pipeline.
- `timeout` giới hạn thời gian chờ ở phía ứng dụng. Hãy chọn thời hạn phù hợp với độ trễ và yêu cầu của nghiệp vụ.
- Dùng `onErrorResume` khi có phương án dự phòng hợp lệ; dùng `onErrorMap` khi cần chuyển đổi loại lỗi. Tránh biến mọi lỗi thành giá trị thành công vì điều đó có thể che giấu sự cố.

Một Mono chỉ chạy khi có subscriber. Trong service, cách thường dùng là trả Mono cho tầng gọi để tầng đó quyết định cách ghép và tiêu thụ kết quả:

```java
public Mono<String> greet(String name) {
    return requester.route("greeting")
            .data(name)
            .retrieveMono(String.class);
}
```

Không nên gọi `subscribe()` bên trong mọi phương thức service chỉ để “kích hoạt” request. Làm như vậy tách request khỏi pipeline của caller, khiến caller khó phối hợp kết quả, xử lý lỗi và quản lý vòng đời. Chỉ subscribe trực tiếp ở ranh giới imperative khi ứng dụng thực sự cần tự khởi chạy một tác vụ độc lập.

## 5. Phân biệt `retrieveMono`, `retrieveFlux` và `send`

| Phương thức | Tương tác RSocket | Kiểu trả về | Khi nào dùng |
|---|---|---|---|
| `retrieveMono(Type.class)` | Request-Response | `Mono<T>` | Một request, một response |
| `retrieveFlux(Type.class)` | Request-Stream hoặc Request-Channel tùy cardinality của input | `Flux<T>` | Cần nhận nhiều response hoặc trao đổi stream |
| `send()` | Fire-and-Forget | `Mono<Void>` | Chỉ cần gửi thông điệp một chiều |

Không dùng `retrieveMono` cho request payload là một Publisher phát nhiều phần tử. RSocket không có kiểu tương tác “many-to-one”; trường hợp này sẽ phát sinh lỗi. Nếu cần gửi hoặc nhận nhiều phần tử, hãy chọn tương tác streaming phù hợp và dùng `retrieveFlux`.

Cũng cần phân biệt `send()` với Request-Response: Mono do `send()` trả về chỉ cho biết việc gửi payload có hoàn tất thành công hay không. Nó không xác nhận responder đã xử lý nghiệp vụ hoặc đã tạo kết quả.

## 6. Lỗi thường gặp

1. **Route không khớp:** client gọi `route("greeting")` nhưng responder đăng ký route khác. Kiểm tra chính tả và cấu hình route ở cả hai phía.
2. **Không có subscriber:** tạo Mono rồi bỏ đó khiến request chưa được thực thi. Hãy trả Mono cho framework/caller hoặc subscribe tại ranh giới imperative phù hợp.
3. **Dùng sai kiểu phản hồi:** client khai báo `User.class` nhưng server trả kiểu dữ liệu khác, hoặc thiếu decoder cho định dạng payload. Đồng bộ contract và cấu hình codec.
4. **Dùng Publisher nhiều phần tử với `retrieveMono`:** đây là tổ hợp không hợp lệ. Chọn `retrieveFlux` và mô hình streaming phù hợp.
5. **Block trong luồng reactive:** `block()` có thể làm nghẽn event-loop. Chỉ dùng trong ví dụ command-line, kiểm thử hoặc ranh giới imperative có chủ đích.
6. **Bỏ qua lỗi bất đồng bộ:** lỗi không nhất thiết xuất hiện tại dòng tạo Mono. Đặt xử lý lỗi trong pipeline và cấu hình timeout phù hợp.

## 7. Checklist khi triển khai

- Route phía requester trùng với route của responder.
- Payload gửi đi đúng kiểu và đúng định dạng mà responder mong đợi.
- Kiểu trong `retrieveMono` khớp với response thực tế.
- Encoder/decoder cho data và metadata đã được đăng ký ở cả hai phía.
- Có subscriber tiêu thụ Mono; lỗi và timeout được xử lý ở tầng phù hợp.
- Chọn `retrieveMono` khi cần một response; chọn `retrieveFlux` khi cần stream; chọn `send` khi chỉ cần gửi một chiều.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.RetrieveSpec — API Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
