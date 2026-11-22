# Điều tiết nhu cầu và giới hạn đồng thời để bảo vệ Redis

## 1. Vấn đề: API phản ứng không có nghĩa Redis chịu được vô hạn yêu cầu

Giả sử một API Spring WebFlux cần lấy trạng thái của 5.000 thiết bị từ Redis. Spring Data Redis cung cấp `ReactiveRedisTemplate` và `ReactiveStringRedisTemplate`, cho phép gọi Redis qua `Mono` hoặc `Flux` mà không cần chặn một luồng Java cho mỗi phản hồi.

Một đoạn mã có vẻ rất tự nhiên:

```java
return Flux.fromIterable(deviceIds)
        .flatMap(id ->
                reactiveRedisTemplate.opsForValue()
                        .get("device:status:" + id)
        );
```

Nhưng có một câu hỏi quan trọng: **tại một thời điểm ứng dụng đang gửi bao nhiêu lệnh tới Redis?**

Nếu hàng trăm HTTP request cùng chạy, mỗi request lại tạo hàng nghìn thao tác Redis, số lệnh đang chờ phản hồi có thể tăng nhanh. Redis có thể chưa hết CPU nhưng kết nối client, hàng đợi gửi lệnh, bộ nhớ đệm, băng thông, thời gian giải mã và độ trễ p99 đã tăng mạnh.

```text
Nhiều request HTTP
       |
       v
Spring WebFlux / Reactor
       |
       | Nếu phát Redis GET không giới hạn
       v
Rất nhiều lệnh đang chờ / hàng đợi client
       |
       v
       Redis
       |
       +-- Thời gian phản hồi tăng
       +-- Timeout, reconnect, retry
       +-- Heap và buffer tăng
       +-- Request khác bị ảnh hưởng
```

Một hệ thống phản ứng (*reactive*) cho phép tổ chức I/O bất đồng bộ và truyền tín hiệu **nhu cầu** (*demand*) giữa các thành phần. Điều đó **không tự cấp thêm CPU, băng thông hay bộ nhớ cho Redis**. Muốn bảo vệ Redis cần chủ động điều tiết:

- Một luồng công việc có bao nhiêu thao tác Redis **đồng thời**?
- Tất cả request trên một instance có bao nhiêu thao tác Redis đang thực hiện?
- Trong một giây có thể phát bao nhiêu lệnh?
- Nguồn dữ liệu có phát nhanh hơn phía xử lý không, và nếu có thì chuyện gì xảy ra?
- Khi tải vượt ngưỡng, hệ thống **chờ, từ chối, bỏ bớt hay lưu công việc bền vững**?

Bài học này thuộc chương **Redis phản ứng** của Spring Data Redis, tập trung vào cơ chế *backpressure* của Reactor, các giới hạn `flatMap`, giới hạn **in-flight** trên toàn ứng dụng, rate limiting, timeout, retry và cách đo để lựa chọn ngân sách tải phù hợp.

## 2. Backpressure trong Reactive Streams là gì?

### 2.1. Publisher, Subscriber và request(n)

Trong mô hình Reactive Streams, thành phần phát (`Publisher`) gửi dữ liệu cho thành phần nhận (`Subscriber`) thông qua một `Subscription`. Subscriber có thể báo nó sẵn sàng nhận bao nhiêu phần tử bằng tín hiệu:

```java
subscription.request(n);
```

Ví dụ về ý tưởng:

```text
Publisher                         Subscriber
    |                                 |
    | <------- request(5) ------------|
    | -------- onNext(item1) -------->|
    | -------- onNext(item2) -------->|
    | -------- onNext(item3) -------->|
    | -------- onNext(item4) -------->|
    | -------- onNext(item5) -------->|
    |                                 |
    | <------- request(5) ------------|
    | -------- các item tiếp theo --->|
```

Dòng dữ liệu tuân thủ backpressure không phát `onNext` vượt quá nhu cầu được yêu cầu. Trong Reactor, `Flux` và `Mono` là hai loại Publisher phổ biến.

**Demand** không giống với “đặt Redis xử lý tối đa 5 lệnh mỗi giây”. Nó biểu thị **số phần tử đầu ra đang được yêu cầu**, không trực tiếp định nghĩa ngân sách QPS, số kết nối hay giới hạn lệnh Redis.

### 2.2. Hai loại luồng đầu vào rất khác nhau

**Cold publisher** có thể phát theo nhu cầu:

```java
Flux.fromIterable(keys)
```

Danh sách khóa có sẵn và được duyệt khi có subscription. Những operator ở phía sau có thể điều chỉnh nhu cầu ở phía trước.

**Hot publisher** có thể tiếp tục phát bất kể một subscriber cụ thể đang xử lý chậm, ví dụ nguồn sự kiện sống, callback ngoại vi hoặc một `Sinks.Many` được cấp dữ liệu bởi luồng khác.

```text
Cold source:
  downstream yêu cầu -> upstream phát phù hợp

Hot source:
  sự kiện vẫn đến -> downstream chậm
                    |
                    +-- Cần chính sách buffer / drop / error / lưu bền vững
```

`flatMap(..., concurrency)` giúp giới hạn số tác vụ bên trong được đăng ký cùng lúc, nhưng **không biến một nguồn hot vô hạn thành hàng đợi bền vững**. Nếu sự kiện đến nhanh hơn Redis xử lý lâu dài, hệ thống phải có chính sách rõ ràng khi quá tải.

### 2.3. Backpressure không có nghĩa Redis server biết request(n)

Redis không nhận tín hiệu `request(n)` từ Reactor. Đây là tín hiệu giữa các Publisher và Subscriber trong ứng dụng.

Cách bảo vệ Redis là dùng demand và các operator để **giảm số lệnh được ứng dụng phát tới Redis**. Một khi lệnh đã được ghi ra socket, hủy một subscription cũng không bảo đảm Redis chưa thực thi lệnh đó.

Sự khác biệt này đặc biệt quan trọng với các thao tác ghi dữ liệu.

## 3. Phân biệt ba giới hạn: demand, concurrency và rate

| Khái niệm | Giới hạn cái gì? | Ví dụ | Có bảo đảm Redis QPS không? |
|---|---|---|---|
| **Demand/backpressure** | Số phần tử Publisher được downstream yêu cầu | `request(10)`, `limitRate(32)` | Không |
| **Concurrency** | Số thao tác đang xử lý đồng thời | `flatMap(fn, 8)` | Không |
| **Rate limit** | Số yêu cầu được chấp nhận trong một khoảng thời gian | Tối đa 500 Redis reads/giây | Có thể giới hạn tốc độ phát ở phạm vi áp dụng |
| **Queue/buffer limit** | Số việc được giữ chờ xử lý | Tối đa 1.000 công việc | Không trực tiếp |
| **Connection limit** | Số kết nối vật lý trong pool | 16 connections | Không tương đương với số lệnh đồng thời |

Một Redis client như Lettuce có thể **multiplex** nhiều lệnh trên một kết nối, nên “16 connection” không đồng nghĩa “16 lệnh đang thực thi”. Ngược lại, `flatMap` với 16 inner subscriptions không có nghĩa Redis chỉ thấy 16 lệnh nếu **mỗi inner publisher** tự gửi nhiều lệnh.

### 3.1. Concurrency không đồng nghĩa QPS

Giả sử trung bình một lệnh Redis mất 20 ms từ lúc gửi đến khi ứng dụng nhận xong. Với tối đa 10 thao tác in-flight, thông lượng lý tưởng có thể gần:

```text
concurrency / latency = 10 / 0,020 = 500 thao tác/giây
```

Đây chỉ là một phép tính định hướng theo quan hệ giữa số việc đang chạy, tốc độ và thời gian phục vụ; throughput thực tế chịu ảnh hưởng của client, Redis, mạng và phân bố độ trễ.

Nếu cùng giới hạn 10 thao tác nhưng latency giảm còn 2 ms, ứng dụng có thể phát tải lớn hơn đáng kể. Vì vậy, **giới hạn đồng thời không thay thế giới hạn tốc độ phát lệnh** khi Redis có ngân sách QPS phải tuân thủ.

### 3.2. Rate limit cũng không thay thế concurrency limit

Giả sử chấp nhận 100 yêu cầu/giây nhưng mỗi thao tác mất 3 giây. Số thao tác đang chờ có thể tăng rất lớn dù tốc độ nhận mới đã bị giới hạn.

Một thiết kế vững hơn thường phối hợp:

```text
Incoming requests
      |
      v
Rate limit: không nhận quá nhiều yêu cầu/giây
      |
      v
Concurrency limit: không cho quá nhiều việc cùng gọi Redis
      |
      v
Timeout + bounded queue + overload policy
      |
      v
Redis
```

## 4. Giới hạn đồng thời trong Reactor bằng flatMap

### 4.1. flatMap có tham số concurrency

Với Spring Data Redis Reactive, mỗi lần `get(key)` thường trả một `Mono<String>` đại diện cho một thao tác đọc bất đồng bộ. Reactor `flatMap` có thể giới hạn số inner publishers được subscribe đồng thời:

```java
Flux.fromIterable(keys)
        .flatMap(
                key -> redis.opsForValue().get(key),
                8
        );
```

Ý nghĩa: tối đa khoảng **8 inner publishers đang được đăng ký tại một thời điểm** trong **một lần subscribe vào Flux này**. Với tình huống mỗi inner là một Redis `GET` đơn giản, đây là cách thực tế để hạn chế số GET cùng lúc phát từ luồng công việc đó.

Lưu ý:

- Đây là **giới hạn cho một pipeline**, không phải giới hạn chung của cả JVM.
- `flatMap` có thể trả kết quả **không theo thứ tự khóa đầu vào** vì lệnh hoàn thành ở những thời điểm khác nhau.
- Nếu inner publisher có nhiều thao tác Redis, giới hạn inner không phải giới hạn số lệnh tuyệt đối.
- Nếu nhiều HTTP request mỗi request tạo một pipeline riêng, các giới hạn cộng dồn theo số request.

Ví dụ 100 request, mỗi request `flatMap(..., 8)` có thể tạo tới khoảng **800 inner subscriptions in-flight** trên một instance nếu tất cả chạy cùng lúc và không có giới hạn khác.

### 4.2. flatMap(mapper, concurrency, prefetch)

Một overload quan trọng:

```java
.flatMap(
        key -> redis.opsForValue().get(key),
        8,  // concurrency
        1   // prefetch
)
```

- `concurrency` giới hạn số inner publishers cùng hoạt động.
- `prefetch` điều chỉnh lượng dữ liệu mà operator yêu cầu trước từ **mỗi inner publisher**, có thể ảnh hưởng bộ đệm.

Với inner là `Mono` trả nhiều nhất một kết quả, `prefetch = 1` thể hiện ý định không yêu cầu nhiều phần tử từ mỗi inner. Với inner là `Flux` trả hàng nghìn phần tử, prefetch lớn có thể tạo nhiều dữ liệu chờ xử lý hơn.

`prefetch` **không phải** ngưỡng tổng bộ nhớ hay Redis QPS. Giá trị này cần được đánh giá cùng hình dạng nguồn dữ liệu và chuỗi operator.

### 4.3. concatMap: lần lượt từng thao tác

Nếu muốn xử lý có thứ tự và gần như chỉ một tác vụ tại một thời điểm:

```java
Flux.fromIterable(keys)
        .concatMap(key -> redis.opsForValue().get(key));
```

`concatMap` đợi inner hiện tại hoàn thành trước khi chuyển sang inner kế tiếp. Nó phù hợp nếu thứ tự hoặc giới hạn tối thiểu quan trọng hơn throughput, nhưng với mạng có RTT lớn thì có thể chậm hơn đáng kể.

Nếu `get(key)` trả `Mono.empty()` cho khóa không tồn tại, phần tử tương ứng **không được phát** trừ khi ứng dụng chủ động biến miss thành một giá trị kết quả. Điều đó quan trọng khi muốn đối chiếu số khóa đầu vào với số kết quả đầu ra.

### 4.4. flatMapSequential: giới hạn đồng thời nhưng giữ thứ tự đầu ra

```java
Flux.fromIterable(keys)
        .flatMapSequential(
                key -> redis.opsForValue().get(key),
                8,
                1
        );
```

`flatMapSequential` có thể subscribe nhiều inner cùng lúc nhưng phát kết quả theo thứ tự nguồn. Nó hữu ích nếu API bắt buộc trả kết quả theo thứ tự khóa.

Đổi lại, nếu inner ở đầu chậm, những kết quả phía sau đã hoàn tất có thể phải được **giữ trong buffer**. Cấu hình này cần được đo về bộ nhớ và độ trễ, không mặc định tốt hơn `flatMap`.

### 4.5. limitRate không phải rate limiter

Ví dụ:

```java
Flux.fromIterable(keys)
        .limitRate(32)
        .flatMap(key -> redis.opsForValue().get(key), 8);
```

`limitRate(32)` điều chỉnh cách yêu cầu phần tử ở phía upstream theo những đợt nhỏ hơn. Nó **không** bảo đảm Redis sẽ nhận tối đa 32 lệnh/giây hoặc tối đa 32 lệnh cùng lúc.

Nếu Redis trả phản hồi rất nhanh, pipeline có thể phát hàng nghìn lệnh trong một giây. Nếu cần giới hạn QPS, phải có cơ chế rate limiting riêng.

## 5. Ví dụ Spring Data Redis: GET nhiều khóa với in-flight giới hạn

### 5.1. ReactiveStringRedisTemplate

Trong một ứng dụng Spring Boot có Spring Data Redis Reactive và kết nối Lettuce phù hợp, có thể tiêm `ReactiveStringRedisTemplate`:

```java
package com.example.redis.reactive;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DeviceRedisService {

    private final ReactiveStringRedisTemplate redis;

    public DeviceRedisService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

`ReactiveStringRedisTemplate` dùng serializer chuỗi cho khóa và giá trị. Nếu dữ liệu trong Redis là JSON hoặc Hash, phải dùng `ReactiveRedisTemplate`/operation và serializer đúng với dữ liệu thực. Không nên mặc định mọi Redis value đều là String.

### 5.2. Trả cả cache hit và cache miss

Khi muốn đọc danh sách nhiều khóa, một `GET` không tìm thấy thường trả `Mono.empty()`. Nếu dùng `flatMap` trực tiếp, khóa miss biến mất khỏi luồng đầu ra; việc đối chiếu theo ID trở nên khó khăn.

Định nghĩa kiểu kết quả:

```java
package com.example.redis.reactive;

public record DeviceLookup(
        String deviceId,
        String status,
        boolean found
) {
}
```

Một service đầy đủ:

```java
package com.example.redis.reactive;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DeviceStatusReader {

    private static final int MAX_CONCURRENCY = 8;

    private final ReactiveStringRedisTemplate redis;

    public DeviceStatusReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Flux<DeviceLookup> findMany(List<String> deviceIds) {

        return Flux.fromIterable(deviceIds)
                .flatMap(
                        this::findOne,
                        MAX_CONCURRENCY,
                        1
                );
    }

    private Mono<DeviceLookup> findOne(String deviceId) {

        String key = "device:status:" + deviceId;

        return redis.opsForValue()
                .get(key)
                .map(value -> new DeviceLookup(
                        deviceId, value, true
                ))
                .switchIfEmpty(Mono.fromSupplier(
                        () -> new DeviceLookup(
                                deviceId, null, false
                        )
                ))
                .timeout(Duration.ofMillis(800));
    }
}
```

Giải thích:

1. `Flux.fromIterable(deviceIds)` tạo luồng khóa **khi được subscribe**.
2. `flatMap(..., 8, 1)` giới hạn số lời gọi `findOne` được đăng ký cùng lúc **trong một lượt đọc**.
3. `get(key)` trả `Mono<String>`, không chặn một thread trong lúc đợi Redis.
4. `map(...)` biến một Redis hit thành kết quả có `found=true`.
5. `switchIfEmpty(...)` biến Redis miss thành kết quả có `found=false`; không bỏ mất ID đầu vào.
6. `timeout(800 ms)` xác định ngân sách chờ cho mỗi inner operation trong ví dụ; khi vượt quá sẽ tạo lỗi và theo mặc định làm luồng `findMany` kết thúc nếu không có chính sách xử lý lỗi riêng.
7. Không gọi `.block()` hoặc `.subscribe()` bên trong service. Service **trả Flux** để WebFlux/consumer điều khiển subscription.

**Đây là ngân sách ví dụ, không phải giá trị mặc định tối ưu.** Thời gian timeout và mức concurrency phải đến từ SLO và đo đạc của hệ thống.

### 5.3. flatMap không bảo đảm thứ tự kết quả

Giả sử đầu vào:

```text
A, B, C, D
```

Nếu Redis trả giá trị C nhanh hơn A, kết quả có thể đến:

```text
C, A, D, B
```

Vì vậy, API đọc nhiều khóa cần giữ liên kết bằng `deviceId`. Nếu đầu ra bắt buộc đúng thứ tự, cân nhắc `flatMapSequential` và đánh giá chi phí buffer.

### 5.4. Không tự subscribe bên trong vòng lặp

Một lỗi rất dễ gặp:

```java
for (String key : keys) {
    redis.opsForValue().get(key)
            .subscribe(value -> handle(value));
}
```

Mỗi vòng lặp tự tạo subscription, khiến ứng dụng khó kiểm soát tổng số lệnh đồng thời, thứ tự hoàn tất, lỗi và cancellation. Nếu không lưu `Disposable` và xử lý lifecycle, tác vụ có thể tiếp tục chạy sau khi request kết thúc.

Thay vào đó:

```java
return Flux.fromIterable(keys)
        .flatMap(
                key -> redis.opsForValue().get(key),
                8
        );
```

Đưa các thao tác vào **một reactive chain** và để phần gọi ở ranh giới ứng dụng subscribe.

## 6. Giới hạn đồng thời cho toàn bộ một instance

`flatMap(..., 8)` bảo vệ **một pipeline**, nhưng không bảo vệ toàn bộ ứng dụng nếu có hàng trăm pipeline chạy đồng thời.

Giả sử:

```text
100 request HTTP cùng lúc
Mỗi request: maxConcurrency = 8
=> Tối đa khoảng 800 thao tác GET inner đang hoạt động
```

Nếu Redis và driver chỉ phù hợp với một lượng nhỏ hơn, cần thêm ngân sách **in-flight chung** cho các request qua cùng service.

### 6.1. Semaphore không chặn event loop

Có thể dùng `java.util.concurrent.Semaphore` với `tryAcquire()` để **từ chối ngay** khi hết lượt, thay vì gọi `acquire()` khiến event-loop thread bị chặn.

Ví dụ:

```java
package com.example.redis.reactive;

public class RedisOverloadedException extends RuntimeException {

    public RedisOverloadedException() {
        super("Ngân sách thao tác Redis đang bận");
    }
}
```

Service giới hạn in-flight:

```java
package com.example.redis.reactive;

import java.util.concurrent.Semaphore;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProtectedRedisReader {

    // Một ngân sách chung cho instance của service này.
    private final Semaphore permits = new Semaphore(40);
    private final ReactiveStringRedisTemplate redis;

    public ProtectedRedisReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> get(String key) {

        return Mono.defer(() -> {

            if (!permits.tryAcquire()) {
                return Mono.error(new RedisOverloadedException());
            }

            // Defer thứ hai bảo vệ cả việc tạo publisher:
            // nếu tạo/get phát lỗi, doFinally vẫn release.
            return Mono.defer(() ->
                    redis.opsForValue().get(key)
            ).doFinally(signal -> permits.release());
        });
    }
}
```

Cơ chế:

- Chỉ thử lấy permit **khi subscription bắt đầu**, không lấy từ lúc tạo `Mono`.
- Nếu hết 40 permit, trả lỗi `RedisOverloadedException` để tầng gọi quyết định trả HTTP 429/503 hoặc cơ chế giảm tải phù hợp.
- `doFinally` trả permit khi `Mono` hoàn thành, lỗi hoặc bị hủy.
- `tryAcquire` không chặn Reactor event loop.
- Giới hạn 40 là **trên instance ứng dụng này**, không phải toàn Redis Cluster.
- Với mỗi inner chỉ thực hiện một `GET`, số permit gần với số thao tác in-flight trên đường đi qua service này.

Cần đặc biệt lưu ý: **tất cả đường truy cập Redis cần được bảo vệ phải thực sự đi qua cơ chế chung này**. Nếu một vài endpoint gọi `ReactiveStringRedisTemplate` trực tiếp, chúng không bị tính vào semaphore.

### 6.2. Kết hợp mức giới hạn của request và instance

```java
public Flux<DeviceLookup> findManyProtected(List<String> deviceIds) {

    return Flux.fromIterable(deviceIds)
            .flatMap(
                    id -> protectedRedisReader
                            .get("device:status:" + id)
                            .map(status ->
                                    new DeviceLookup(id, status, true))
                            .switchIfEmpty(
                                    Mono.just(
                                            new DeviceLookup(id, null, false)
                                    )
                            ),
                    8,
                    1
            );
}
```

Có hai tầng:

```text
Một HTTP request
      |
      | flatMap concurrency=8
      v
ProtectedRedisReader
      |
      | Semaphore 40 cho cả JVM
      v
Redis
```

Khi 40 permit đã được dùng, request mới sẽ bị **từ chối nhanh**. Đây là **bulkhead/fail-fast policy**, không phải hàng chờ.

Nếu muốn chờ permit thay vì trả lỗi, phải thiết kế **hàng đợi có dung lượng và thời gian chờ giới hạn**, tránh dùng semaphore blocking trực tiếp trên event loop. Chờ vô hạn chỉ chuyển nguy cơ quá tải từ Redis sang RAM và latency của ứng dụng.

### 6.3. Permit chỉ phản ánh subscription, không bảo đảm lệnh đã bị hủy

`doFinally` chạy khi reactive chain kết thúc hoặc cancellation được phát. Trong trường hợp timeout/cancel, permit được giải phóng ở mức ứng dụng. Nhưng nếu Redis command đã được gửi qua socket, nó **vẫn có thể đang được thực thi hoặc hoàn thành tại Redis**.

Vì vậy, với mục tiêu **giới hạn chính xác số lệnh vật lý đang tồn tại ở Redis**, cần hiểu cơ chế hủy của client, queue và timeout. Semaphore ở tầng `Mono` là một biện pháp quản lý tải hữu ích, nhưng không phải hợp đồng bảo đảm tuyệt đối với phía server khi có nhiều timeout và cancellation.

## 7. Nhiều instance làm ngân sách tổng cộng lớn hơn

Một service có 10 pod, mỗi pod cấp 40 permit:

```text
Pod 1:  40 thao tác in-flight
Pod 2:  40 thao tác in-flight
...
Pod 10: 40 thao tác in-flight
----------------------------
Tổng lý thuyết: tới 400 thao tác
```

Vì vậy, giới hạn local không tự bảo vệ một Redis server chung khỏi tổng tải của mọi bản sao ứng dụng.

Để có ngân sách tổng:

- Phân bổ hạn mức theo số instance dự kiến và lưu lượng thực.
- Đặt giới hạn tại API gateway hoặc một tầng điều phối dùng chung.
- Dùng rate limiter phân tán nếu yêu cầu thật sự cần đồng bộ hạn mức.
- Có cơ chế phản ứng khi autoscaling tăng số instance.
- Theo dõi số Redis commands thực tế ở mức cụm, không chỉ metric từng pod.

Nếu dùng **Redis chính đang cần bảo vệ** làm nơi tính rate limiter phân tán cho mọi request, bản thân các lệnh rate limit có thể tạo thêm tải lên Redis. Cần tính chi phí này vào thiết kế và cân nhắc giới hạn tại tầng trước Redis khi phù hợp.

### 7.1. Redis Cluster có nhiều shard nhưng không đồng nghĩa mọi tài nguyên đều chia đều

Một `GET` được định tuyến tới node sở hữu hash slot của khóa. Nếu phần lớn request truy cập một vài khóa nóng, một shard có thể chịu nhiều tải hơn shard khác.

Cần quan sát:

- Lệnh/giây trên từng node.
- CPU, network và memory từng shard.
- Độ trễ theo nhóm khóa hoặc chức năng.
- Số command chờ gửi/nhận phản hồi trong client.
- Phân bố hot keys.

Một giới hạn concurrency chung bảo vệ tổng mức tải nhưng chưa chắc bảo vệ shard nóng nếu phân bố khóa rất lệch. Khi cần, có thể bổ sung giới hạn theo loại tác vụ, nhóm khóa hoặc shard, với chi phí phức tạp tương ứng.

## 8. Giới hạn tốc độ gửi lệnh: rate limiting

`flatMap(concurrency=8)` giúp không có quá nhiều thao tác **cùng lúc** trong một pipeline. Nhưng khi Redis trả lời rất nhanh, các inner kết thúc rồi được thay bằng inner mới liên tục; thông lượng vẫn có thể rất cao.

**Rate limiting** giới hạn số công việc được nhận trong một khoảng thời gian, ví dụ:

```text
Ngân sách: 200 thao tác GET/giây
Burst cho phép: tối đa 50 thao tác trong khoảng ngắn
```

Một thuật toán phổ biến là **token bucket**:

```text
Token bucket (capacity 50)
        |
   +1 token theo tốc độ refill cho trước
        |
Request cần 1 token
        |
  +-----+--------+
  |              |
Có token      Không còn token
  |              |
Cho phép       Từ chối hoặc
               đưa vào hàng chờ có giới hạn
```

Với Spring WebFlux có thể dùng một rate limiter tích hợp cùng reactive chain, hoặc đặt hạn mức ở gateway. Điều quan trọng không phải tên thư viện mà là:

1. Có xác định đơn vị đang giới hạn: request HTTP, thao tác Redis hay batch?
2. Có định nghĩa burst và số lượng request tối đa chờ không?
3. Có phân biệt ưu tiên giữa read cache và write quan trọng không?
4. Có giới hạn chung giữa nhiều pod không?
5. Khi vượt giới hạn, có trả tín hiệu quá tải rõ ràng cho caller không?

### 8.1. delayElements không phải giải pháp tổng quát

Một cách thử thường thấy:

```java
Flux.fromIterable(keys)
        .delayElements(Duration.ofMillis(10))
        .flatMap(
                key -> redis.opsForValue().get(key),
                8
        );
```

Trong một pipeline đơn lẻ, `delayElements` làm giãn khoảng phát các phần tử. Nhưng nếu có 100 HTTP request, **mỗi request có đồng hồ riêng** và tổng tốc độ phát lệnh có thể vượt xa dự tính.

`delayElements` cũng không có những tính năng thường cần của rate limiter production, như quota chung, burst policy, fairness và trả lỗi khi quá tải. Dùng nó như công cụ thử nghiệm hoặc khi chủ đích thật sự là giãn phần tử trong một stream, không coi đó là một cơ chế bảo vệ Redis toàn hệ thống.

## 9. Hàng đợi và backpressure: đặt giới hạn thay vì tích lũy vô hạn

### 9.1. Bộ đệm vô hạn là rủi ro

Giả sử sự kiện đến 10.000/giây nhưng Redis chỉ xử lý được 2.000/giây. Nếu ứng dụng đưa mọi sự kiện vào một hàng đợi RAM không giới hạn, số phần tử tồn đọng sẽ tăng:

```text
10.000 sự kiện/giây vào
 2.000 sự kiện/giây xử lý
--------------------------------
 8.000 sự kiện/giây tích lũy
```

Sau một phút, về mặt số lượng có thể tích thêm hàng trăm nghìn công việc. Payload lớn sẽ làm heap tăng nhanh và gây GC hoặc OutOfMemoryError.

Backpressure chỉ phát huy đầy đủ nếu **nguồn phát có khả năng giảm tốc** theo nhu cầu downstream. Với nguồn đẩy sự kiện bất kể nhu cầu, phải có chính sách giới hạn tồn đọng.

### 9.2. onBackpressureBuffer có giới hạn

Ví dụ đối với một Flux hot có thể phát nhanh:

```java
Flux<Event> guarded = incomingEvents
        .onBackpressureBuffer(1000);
```

Khi downstream không theo kịp, operator có thể giữ tối đa khoảng 1.000 phần tử trong buffer. Nếu vượt giới hạn, luồng có thể phát lỗi tràn bộ đệm theo cấu hình.

**Không dùng `onBackpressureBuffer()` vô hạn** cho luồng tải cao mà chưa có ngân sách bộ nhớ. Buffer chỉ giúp hấp thụ burst ngắn; nó không giải quyết tình trạng nguồn vào nhanh hơn khả năng xử lý **trong thời gian dài**.

Các lựa chọn khác gồm:

- `onBackpressureDrop`: bỏ bớt sự kiện khi không theo kịp; chỉ phù hợp với dữ liệu chấp nhận mất.
- `onBackpressureLatest`: giữ giá trị mới nhất theo nhu cầu downstream; phù hợp với trạng thái hiển thị có thể bỏ trạng thái trung gian.
- Báo lỗi hoặc từ chối đầu vào để upstream giảm tốc.
- Ghi yêu cầu vào một queue/stream bền vững khi **không được phép mất công việc**.

### 9.3. Không dùng drop cho tác vụ bắt buộc

Sự kiện “nhiệt độ màn hình mới nhất” có thể cho phép bỏ mẫu cũ, nhưng “ghi nhận thanh toán đơn hàng” không thể âm thầm drop vì Redis đang bận.

Chọn chính sách theo tính chất dữ liệu:

| Loại công việc | Chính sách thường phù hợp |
|---|---|
| Chỉ cập nhật trạng thái hiển thị mới nhất | Có thể giữ latest khi chấp nhận mất trạng thái trung gian |
| Cache pre-warming | Có thể bỏ qua khi hệ thống quá tải, vì lần đọc sau nạp lại |
| Đọc cache phục vụ API | Trả lỗi giảm tải/timeout hoặc fallback có giới hạn |
| Event nghiệp vụ bắt buộc | Hàng đợi bền vững, retry có kiểm soát, idempotency |
| Ghi dữ liệu tài chính | Giao dịch có thẩm quyền, chống lặp và không dùng drop |

## 10. Timeout, retry và cancellation phải được thiết kế cùng nhau

### 10.1. Timeout hạn chế thời gian chờ của ứng dụng

Ví dụ:

```java
redis.opsForValue()
        .get(key)
        .timeout(Duration.ofMillis(500));
```

Khi vượt thời gian, Reactor phát lỗi timeout và hủy subscription upstream theo ngữ nghĩa của operator. Nhưng **không được kết luận Redis đã hủy lệnh vật lý**. Nếu command đã được gửi, server có thể vẫn xử lý.

Với đọc `GET`, một lượt đọc lại thường ít rủi ro về tác dụng phụ hơn lệnh ghi. Nhưng khi nhiều timeout xảy ra liên tiếp, retry không có giới hạn sẽ làm áp lực Redis tăng đúng lúc hệ thống đang chậm.

### 10.2. Retry có giới hạn, điều kiện và jitter

Một ví dụ có retry ở mức ứng dụng:

```java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<String> getWithRetry(String key) {

    return redis.opsForValue()
            .get(key)
            .timeout(Duration.ofMillis(500))
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                            .maxBackoff(Duration.ofSeconds(1))
                            .jitter(0.5)
                            .filter(this::isTransientRedisFailure)
            );
}
```

`isTransientRedisFailure(Throwable)` là hàm nghiệp vụ do ứng dụng định nghĩa để phân biệt lỗi tạm thời với lỗi không nên retry; ví dụ không retry lỗi dữ liệu sai định dạng hoặc lỗi code.

Nguyên tắc:

- Giới hạn số lần retry.
- Có khoảng chờ và jitter để tránh retry đồng loạt.
- Có timeout tổng cho toàn request, không chỉ cho từng lần thử.
- Không retry mọi lỗi.
- Tính cả retry vào ngân sách rate và concurrency.
- Khi Redis đang quá tải, đôi khi **từ chối nhanh** tốt hơn phát thêm retry.

### 10.3. Lệnh ghi có rủi ro retry lặp tác dụng

Ví dụ:

```java
redis.opsForValue().increment("views:page:42");
```

Nếu request timeout sau khi Redis đã `INCR`, ứng dụng có thể không nhận được phản hồi dù Redis đã tăng bộ đếm. Retry mù quáng có thể làm tăng thêm lần nữa.

Tương tự, `LPUSH`, `XADD` và các thao tác ghi khác có thể tạo tác dụng lặp. Khi cần bảo đảm nghiệp vụ không chạy hai lần, phải có idempotency key hoặc cơ chế ghi có điều kiện phù hợp.

`retryWhen` không tự tạo **exactly-once semantics**. Nó chỉ điều khiển việc subscribe lại và thử thực hiện nguồn tác vụ lần nữa.

### 10.4. Cancellation không giống transaction rollback

Khi client HTTP đóng kết nối, subscription có thể bị hủy. Điều đó giúp ứng dụng không tiếp tục một số công việc không cần thiết, nhưng không đảm bảo lệnh Redis đã gửi bị hoàn tác.

Vì vậy:

```text
Cancel một Mono
      |
      +-- Có thể ngừng theo dõi phản hồi
      +-- Có thể giải phóng tài nguyên Reactor
      +-- Không mặc nhiên rollback Redis command
```

Đây là lý do không nên dùng cancellation làm cơ chế duy nhất để ngăn tác dụng phụ của các lệnh ghi nhạy cảm.

## 11. Scheduler và event loop: đừng đưa thao tác blocking vào luồng phản ứng

Spring Data Redis Reactive dùng API không chặn để chờ I/O. Nhưng nếu mã ứng dụng gọi:

```java
String value = reactiveRedis.opsForValue()
        .get(key)
        .block();
```

trong một handler WebFlux, bạn đã biến lời gọi không chặn thành một điểm chờ blocking. Điều này có thể chiếm event-loop thread và làm giảm khả năng phục vụ các request khác.

Cũng không nên tạo `subscribe()` tùy tiện rồi trả response trước khi tác vụ hoàn tất.

Một handler WebFlux nên trả `Mono` hoặc `Flux`:

```java
@GetMapping("/devices/{id}/status")
public Mono<ResponseEntity<String>> status(
        @PathVariable String id) {

    return redis.opsForValue()
            .get("device:status:" + id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Nếu trong chuỗi có phần xử lý blocking thật sự (ví dụ gọi thư viện JDBC đồng bộ), phải tách phần đó và sử dụng scheduler phù hợp với giới hạn tài nguyên, chẳng hạn bounded elastic cho tác vụ blocking. **Không chuyển mọi Redis call sang `Schedulers.boundedElastic()` chỉ vì đang dùng Reactive**: điều đó thường tạo thêm scheduler hop mà không giải quyết vấn đề Redis bị quá tải.

`publishOn`, `subscribeOn` và `parallel()` điều khiển ngữ cảnh thực thi, không tự giới hạn số Redis command đang chạy. Dùng chúng mà không hiểu queue/prefetch có thể làm khó quan sát tải hơn.

## 12. Batching và pipeline trong Reactive Redis

Nếu phải đọc nhiều khóa, ngoài giới hạn đồng thời còn có lựa chọn **gom lệnh** để giảm round trips.

Ví dụ Redis hỗ trợ `MGET` đối với nhiều Redis String:

```redis
MGET device:status:A device:status:B device:status:C
```

Trong Spring Data Redis Reactive, có các API nhiều khóa như `multiGet(...)` cho các kiểu thao tác phù hợp, nhưng khi dùng phải xét:

- Kết quả có thể được giữ trong bộ nhớ dưới dạng một danh sách.
- Số byte phản hồi có thể lớn dù chỉ có một lệnh.
- Redis Cluster có yêu cầu hash slot cho các lệnh đa khóa.
- Một `MGET` rất lớn có thể ảnh hưởng độ trễ của các request khác.
- Batching không thay thế việc giới hạn số công việc lớn chạy đồng thời.

Ví dụ về cách phân lô ở mức ý tưởng:

```text
5.000 keys
   |
   +--> 100 keys/batch
   |        |
   |        +--> MGET hoặc nhóm thao tác phù hợp
   |        +--> Xử lý và giải phóng kết quả
   |
   +--> tối đa 4 batch hoạt động cùng lúc
```

Không nên mặc định `buffer(1000)` là cách bảo vệ Redis; nó có thể tạo một danh sách lớn ở RAM và phát một thao tác nặng hơn. Cần đo lượng byte, latency và áp lực bộ nhớ.

Khi dùng Redis Cluster, nếu các khóa nằm ở các slot khác nhau, không phải mọi lệnh đa khóa đều có thể gửi trực tiếp. Cần chọn phương án phù hợp topology và tránh tạo bottleneck trên một shard nóng.

## 13. Thiết kế các tầng bảo vệ Redis trong một dịch vụ thực

Một sơ đồ triển khai có thể gồm:

```text
Client / Gateway
      |
      | Tầng 1: Giới hạn tốc độ request
      v
WebFlux controller
      |
      | Tầng 2: Validate, từ chối yêu cầu quá lớn
      v
Service
      |
      | Tầng 3: flatMap concurrency cho mỗi tác vụ
      v
Shared Redis Access Layer
      |
      | Tầng 4: In-flight budget cho toàn instance
      v
Reactive Redis client
      |
      | Tầng 5: Connection/pending-command limits
      v
Redis / Redis Cluster
      |
      +--> Metrics và cảnh báo
```

### 13.1. Validate và giới hạn số phần tử đầu vào

Không nên nhận vô điều kiện một danh sách 1.000.000 khóa từ một HTTP request, kể cả khi `flatMap(..., 8)` kiểm soát số lệnh in-flight. Request vẫn có thể chiếm CPU, bộ nhớ và connection quá lâu.

Một API có thể đặt:

- Số khóa tối đa mỗi request.
- Dung lượng payload đầu vào.
- Số request đồng thời mỗi user/client.
- Ngân sách thời gian tổng cho request.
- Giới hạn số batch và kết quả trả về.

Với danh sách rất lớn, cân nhắc phân trang, xử lý nền có giới hạn hoặc streaming có khả năng dừng.

### 13.2. Đặt ngân sách theo loại tác vụ

Không phải mọi Redis operation đều có chi phí giống nhau:

```text
GET một key nhỏ          -> thường tương đối nhẹ
HGETALL một Hash lớn     -> có thể trả rất nhiều dữ liệu
LRANGE một đoạn dài      -> tải phụ thuộc số phần tử trả về
SCAN toàn bộ keyspace    -> tốn nhiều lượt và tài nguyên
Lua script phức tạp      -> có thể giữ Redis bận lâu
```

Một semaphore đếm “mỗi thao tác bằng một permit” là bước khởi đầu dễ hiểu nhưng không phản ánh toàn bộ chi phí. Với những lệnh lớn, có thể cần:

- Giới hạn số phần tử trả về.
- Cho phép số lượng lệnh lớn hoạt động đồng thời ít hơn.
- Phân chia budget theo chức năng đọc/ghi hoặc theo class tải.
- Không cho những tác vụ nền áp đảo request latency-sensitive.

### 13.3. Chọn chính sách quá tải rõ ràng

Khi hết ngân sách, có một số phương án:

1. **Fail fast:** trả HTTP 429/503 hoặc lỗi ứng dụng có thể thử lại sau.
2. **Chờ có giới hạn:** xếp công việc vào queue nhỏ với timeout rõ ràng.
3. **Fallback:** đọc nguồn khác khi được phép và nguồn đó có đủ năng lực.
4. **Drop/Latest:** chỉ với dữ liệu cho phép mất hoặc hợp nhất các cập nhật.
5. **Bền vững hóa:** ghi vào queue/Stream thích hợp nếu công việc bắt buộc không được mất.

Không dùng một hành vi duy nhất cho mọi loại công việc. Ví dụ, cache pre-warming có thể bị bỏ khi Redis bận, còn việc ghi giao dịch phải có cơ chế xác nhận/lưu bền vững phù hợp.

## 14. Quan sát Redis và Reactor trước khi đặt ngưỡng

Nếu chỉ đo một con số `ops/s`, rất khó biết Redis đang được bảo vệ hay chỉ bị chuyển tải sang hàng đợi của client.

Nên đo cả **ứng dụng** lẫn **Redis server**.

| Chỉ số | Vì sao cần |
|---|---|
| Redis commands/giây | Đánh giá lượng tải thực |
| Redis command latency p50/p95/p99 | Phát hiện đuôi độ trễ tăng |
| In-flight operations ở ứng dụng | Xác định có chạm ngưỡng concurrency không |
| Rejected requests do bulkhead/rate limit | Nhận biết lượng nhu cầu vượt ngân sách |
| Pending commands / client buffers | Phát hiện hàng đợi bên trong driver |
| Timeout và retry attempts | Biết retry có làm tải tăng không |
| JVM heap, GC pauses | Phát hiện buffer/queue trong ứng dụng |
| CPU, memory, network của Redis | Xác định bottleneck phía server |
| Pool pending/acquire time | Phát hiện tranh chấp kết nối |
| Per-shard load trong Cluster | Phát hiện shard nóng |

Các lệnh Redis phục vụ quan sát:

```redis
INFO stats
INFO commandstats
INFO cpu
INFO memory
INFO clients
SLOWLOG GET 10
LATENCY LATEST
```

`SLOWLOG` chủ yếu ghi thời gian thực thi lệnh ở Redis, không bao gồm thời gian chờ mạng và giải mã phía ứng dụng. Vì vậy, có thể server thực thi nhanh nhưng p99 HTTP cao do pending command queue hoặc buffer client.

`LATENCY LATEST` hiển thị các sự kiện latency theo cơ chế giám sát của Redis nếu được cấu hình phù hợp. Phải hiểu các metric không cùng định nghĩa để tránh so trực tiếp hai con số không tương đương.

### 14.1. Instrument điểm in-flight

Với một `Mono` Redis, có thể đo thời gian theo subscription:

```java
public Mono<String> timedGet(
        String key,
        io.micrometer.core.instrument.Timer timer) {

    return Mono.defer(() -> {

        long started = System.nanoTime();

        return redis.opsForValue()
                .get(key)
                .doFinally(signal -> {
                    long elapsed = System.nanoTime() - started;
                    timer.record(
                            elapsed,
                            java.util.concurrent.TimeUnit.NANOSECONDS
                    );
                });
    });
}
```

Thời gian đo bao gồm thời gian reactive operation hoạt động từ subscription đến kết thúc/cancellation, không chỉ thời gian Redis thực thi lệnh. Khi báo metric, nên đặt tên thể hiện phạm vi đó, ví dụ `redis.client.operation.duration`.

Với số lượng khóa lớn, **không gắn tên khóa hoặc userId làm tag metric** vì tạo cardinality rất cao. Nên tag theo loại lệnh, endpoint hoặc nhóm công việc ở mức hữu hạn.

### 14.2. Những gì cần đo khi thử tăng tải

Khi tăng request rate từ mức thấp:

```text
Tải thấp
   |
   v
Throughput tăng gần tuyến tính
   |
   v
Một tài nguyên bắt đầu đạt ngưỡng
   |
   v
Latency p95/p99 tăng
   |
   v
Timeout/retry tăng, heap/queue tăng
   |
   v
Hệ thống có thể suy giảm nghiêm trọng
```

Mục tiêu của giới hạn đồng thời là **ngăn ứng dụng bước quá sâu vào vùng suy giảm**, không phải cố giữ mọi request bằng mọi giá.

## 15. Thí nghiệm xác định maxConcurrency phù hợp

### 15.1. Chuẩn bị workload

Giả sử API đọc 1.000 trạng thái thiết bị, mỗi giá trị trung bình 1 KiB. Tạo dữ liệu thử nghiệm dưới namespace riêng:

```text
device:status:test:1
device:status:test:2
...
device:status:test:1000
```

Dữ liệu nên có TTL/chiến lược dọn và không dùng thông tin người dùng thật. Dùng cùng serializer với ứng dụng production.

### 15.2. Thử các mức concurrency

| Cấu hình | Per-request concurrency | Instance cap | Số request đồng thời |
|---|---:|---:|---:|
| A | 1 | 40 | 1, 10, 50 |
| B | 4 | 40 | 1, 10, 50 |
| C | 8 | 40 | 1, 10, 50 |
| D | 16 | 40 | 1, 10, 50 |
| E | 32 | 40 | 1, 10, 50 |

Đây là **ma trận thử nghiệm**, không phải kết luận rằng 8 hoặc 40 luôn tối ưu.

Ở mỗi kịch bản, ghi:

- Thông lượng request/giây và Redis commands/giây.
- p50, p95, p99 của request.
- Số permit bị từ chối.
- Timeout và retry.
- Pending commands ở driver, nếu có metric phù hợp.
- CPU Redis, network, heap JVM và GC.

### 15.3. Đọc kết quả theo ngân sách độ trễ

Một kết quả **giả định**:

```text
Concurrency 1:  tải thấp, throughput chưa đạt nhu cầu
Concurrency 4:  throughput cải thiện, latency ổn định
Concurrency 8:  throughput tăng thêm, p99 vẫn trong SLO
Concurrency 16: throughput gần như không tăng, p99 cao hơn
Concurrency 32: retry/timeout tăng mạnh
```

Trong kịch bản giả định này, concurrency 8 có thể là điểm thử nghiệm tốt hơn 32. Nhưng phải kiểm tra ở nhiều mức đồng thời của HTTP request và trên Redis topology gần production.

Điểm quan trọng là tìm **vùng hiệu năng ổn định**, không phải chỉ đo số lệnh/giây lớn nhất.

### 15.4. Thử quá tải có kiểm soát

Sau khi chọn ngưỡng, nên thử:

1. Tăng tốc độ vào cao hơn ngân sách một cách có kiểm soát.
2. Xác nhận request bị từ chối/giảm tải thay vì tích lũy queue vô hạn.
3. Xác nhận số thao tác in-flight không vượt ngân sách dự kiến ở tầng ứng dụng.
4. Theo dõi p99 của request được chấp nhận.
5. Giảm tải và xác nhận hệ thống phục hồi, không bị retry storm kéo dài.
6. Thử Redis phản hồi chậm hoặc mất kết nối trong môi trường kiểm soát.

Nếu một timeout khiến mọi request lập tức retry nhiều lần, hệ thống vẫn có thể vượt khả năng chịu tải dù có concurrency limit đơn lẻ.

## 16. Những lỗi phổ biến khi triển khai

### Lỗi 1: Cho rằng reactive đồng nghĩa tự động chống quá tải

`Mono` và `Flux` hỗ trợ truyền demand và I/O không chặn, nhưng nhiều pipeline độc lập vẫn có thể phát lượng lệnh lớn. Phải đặt ngân sách tải cụ thể.

### Lỗi 2: Dùng flatMap mà không cân nhắc concurrency

Nếu dùng overload mặc định hoặc đồng thời quá lớn, số inner subscriptions có thể cao hơn dự định. Nên đặt `concurrency` rõ ràng với workload nhiều khóa.

### Lỗi 3: Coi limitRate(100) là 100 Redis GET/giây

`limitRate` điều chỉnh yêu cầu phần tử upstream, không giới hạn QPS. Dùng rate limiter phù hợp nếu cần giới hạn theo thời gian.

### Lỗi 4: Chỉ giới hạn từng request

`flatMap(..., 8)` cho một request không ngăn 100 request tạo khoảng 800 thao tác cùng lúc. Cần cân nhắc ngân sách chung ở service hoặc gateway.

### Lỗi 5: Dùng Semaphore.acquire() trong reactive pipeline

`acquire()` có thể chặn luồng đang chạy, kể cả event loop. Dùng `tryAcquire` để fail fast hoặc một cơ chế chờ không chặn với queue giới hạn.

### Lỗi 6: Giữ queue vô hạn khi Redis chậm

Buffer lớn chỉ chuyển áp lực từ Redis sang heap. Phải quyết định mức trần, thời gian chờ và hành vi khi tràn.

### Lỗi 7: Dùng onBackpressureDrop cho sự kiện không được mất

Drop chỉ phù hợp với dữ liệu được phép mất hoặc hợp nhất. Với công việc bắt buộc, dùng cơ chế lưu bền vững và xử lý lại.

### Lỗi 8: Retry tất cả lỗi ngay lập tức

Khi Redis đang chậm, retry liên tục tạo thêm tải và gây hiệu ứng dây chuyền. Cần retry có giới hạn, backoff, jitter và phân loại lỗi.

### Lỗi 9: Timeout nghĩa là Redis chắc chắn chưa thực thi

Đặc biệt nguy hiểm với lệnh ghi như `INCR`, `XADD` và `LPUSH`. Timeout ở client không bảo đảm rollback; phải xử lý idempotency khi retry.

### Lỗi 10: Dùng publishOn/parallel để “tăng sức Redis”

Đổi scheduler không làm Redis có thêm tài nguyên. Scheduler không thay thế limit in-flight, pending command hoặc rate limiting.

### Lỗi 11: Quên serializer và kích thước payload

Một `GET` chứa JSON vài MiB không có cùng chi phí với một `GET` trả vài byte. Giới hạn theo số lệnh cần đi cùng giới hạn byte và thời gian.

### Lỗi 12: Không xét số pod

Một giới hạn 40 in-flight trên mỗi pod có thể trở thành 400 trên 10 pod. Cần xem tổng tải và cách scale.

### Lỗi 13: Chỉ nhìn Redis CPU

Redis CPU chưa cao nhưng client buffer, event loop, mạng hoặc pool có thể là bottleneck. Đo cả hai phía.

### Lỗi 14: Đọc cache và ghi nghiệp vụ dùng chung ngân sách không công bằng

Một tác vụ quét hoặc cache warming có thể lấy hết permit, khiến ghi quan trọng bị từ chối. Nên có phân lớp ưu tiên và ngân sách theo nhóm tải nếu ứng dụng yêu cầu.

### Lỗi 15: Không phân biệt kết quả hoàn thành với subscription bị hủy

Một `Mono` bị cancel có thể giải phóng permit ở ứng dụng nhưng command đã gửi vẫn tiếp tục tại Redis. Cần tính tới timeout/cancellation trong việc phân tích tải.

## 17. Thực hành theo từng bước

### Bài tập A: Quan sát flatMap concurrency

Tạo 100 khóa test và một `Flux` giả lập công việc chậm:

```java
Flux.range(1, 100)
        .flatMap(
                n -> Mono.delay(Duration.ofMillis(100))
                        .map(ignore -> n),
                4
        );
```

Quan sát tổng thời gian với concurrency 1, 4, 8. Đây là ví dụ dùng `Mono.delay`, không phải lệnh Redis; mục tiêu là hiểu số inner đang hoạt động.

### Bài tập B: Thay bằng GET Redis

Với 100 khóa Redis phát triển:

```java
Flux.range(1, 100)
        .flatMap(
                n -> redis.opsForValue()
                        .get("test:device:" + n),
                4
        );
```

Thử concurrency 1, 4, 8, 16 và đo thời gian, số lệnh/giây, p95/p99 của request trong ứng dụng. Không kết luận từ một lần chạy.

### Bài tập C: Nhiều request đồng thời

Gửi nhiều request HTTP đọc cùng 100 khóa. So sánh:

- Chỉ `flatMap(..., 8)` trong từng request.
- Có thêm shared semaphore 40 permit.

Quan sát độ trễ, timeout, pending commands và số lần fail fast khi tải vượt ngưỡng.

### Bài tập D: Giới hạn tốc độ

Đặt một rate limiter ở API hoặc service trước khi gọi Redis; giữ concurrency cố định. Tăng tốc độ đầu vào và xem số lệnh Redis thực tế có vượt quota không. Thử với nhiều instance nếu kiến trúc có nhiều pod.

### Bài tập E: Redis chậm hoặc mất kết nối

Trong môi trường thử nghiệm an toàn, tạo sự cố hoặc giả lập timeout. Xác minh rằng:

- Có giới hạn số lần retry.
- Không tích lũy buffer vô hạn.
- Request có kết quả quá tải hoặc timeout rõ ràng.
- Sau khi Redis phục hồi, không có retry storm kéo dài.
- Những lệnh ghi có tác dụng phụ không bị retry thiếu kiểm soát.

## 18. Câu hỏi tự kiểm tra

**1. Backpressure trong Reactive Streams có trực tiếp gửi tín hiệu request(n) tới Redis server không?**

Không. `request(n)` là tín hiệu giữa Publisher và Subscriber. Ứng dụng phải dùng operator và giới hạn tải để giảm số lệnh thực sự gửi tới Redis.

**2. `flatMap(fn, 8)` giới hạn gì?**

Giới hạn số inner publishers đang được subscribe đồng thời trong một pipeline. Nó không phải ngân sách QPS hay số lệnh toàn JVM.

**3. Có 100 HTTP request, mỗi request dùng flatMap concurrency 8. Redis có thể chịu bao nhiêu thao tác từ instance đó?**

Có thể lên tới khoảng 800 inner Redis operations đang hoạt động nếu mỗi inner thực hiện một GET và không có giới hạn chung khác.

**4. `limitRate(32)` có bảo đảm không quá 32 lệnh/giây?**

Không. Nó điều tiết demand upstream, không phải rate limit theo thời gian.

**5. Vì sao concurrency và rate limit phải được xem xét riêng?**

Concurrency giới hạn số việc đang chạy cùng lúc, còn rate limit giới hạn số việc đến trong một khoảng thời gian. Khi latency thay đổi, cùng concurrency có thể tạo QPS khác nhau.

**6. Vì sao không nên dùng `Semaphore.acquire()` trong WebFlux?**

Vì nó có thể chặn event-loop thread. `tryAcquire` với fail-fast hoặc hàng chờ không chặn có giới hạn phù hợp hơn.

**7. `timeout` có bảo đảm Redis chưa thực thi một lệnh INCR không?**

Không. Lệnh có thể đã được gửi và hoàn tất ở Redis dù client không nhận được phản hồi.

**8. Khi nào có thể dùng onBackpressureDrop?**

Khi dữ liệu được phép mất hoặc chỉ cần giá trị mới nhất. Không dùng âm thầm cho công việc nghiệp vụ phải hoàn tất.

**9. Vì sao shared semaphore trên một pod không bảo đảm an toàn cho cả Redis Cluster?**

Vì nhiều pod có ngân sách riêng và những shard khác nhau có thể nhận tải không đồng đều. Cần quan sát tổng tải và có cơ chế phối hợp khi cần.

**10. Khi tối ưu concurrency cần xem metric nào ngoài throughput?**

Cần quan sát p95/p99, in-flight, rate rejection, timeout/retry, pending command, Redis CPU/network và JVM heap/GC.

## 19. Ghi nhớ

- **Reactive Redis không có nghĩa là tải vô hạn**: I/O không chặn giúp dùng luồng hiệu quả hơn, không làm Redis có thêm năng lực.
- **Backpressure/demand, concurrency và rate limit là ba khái niệm khác nhau**. Không dùng một operator để thay thế mọi giới hạn.
- **`flatMap(mapper, concurrency, prefetch)`** là công cụ cốt lõi để hạn chế số inner operations của một pipeline; `flatMapSequential` giữ thứ tự nhưng có thể tạo buffer, còn `concatMap` xử lý tuần tự.
- Với nhiều HTTP request, cần thêm **in-flight limit dùng chung** và có thể cần rate limit toàn instance hoặc toàn hệ thống.
- **Buffer phải có giới hạn**, retry phải có backoff/jitter và timeout không tự rollback lệnh đã gửi.
- **Đo cả Redis lẫn ứng dụng**, đặc biệt p95/p99, pending commands, heap và lỗi khi quá tải, rồi chọn giới hạn trên workload và topology thực tế.

### Tài liệu tham khảo

- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html).
- [Spring Data Redis — ReactiveRedisTemplate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ReactiveRedisTemplate.html).
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Reactive Streams — Specification](https://www.reactive-streams.org/).
- [Redis — Latency monitoring](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency-monitor/).
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
