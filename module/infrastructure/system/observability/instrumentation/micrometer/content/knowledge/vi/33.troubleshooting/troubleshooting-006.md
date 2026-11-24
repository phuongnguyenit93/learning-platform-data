# Timer không ghi nhận do thiếu stop hoặc kết thúc sai nhánh

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `Timer` ghi nhận số lần hoàn tất và tổng thời lượng của một thao tác. Khi dùng `Timer.record(...)`, Micrometer quản lý việc đo và ghi nhận quanh khối code. Khi dùng `Timer.Sample`, ứng dụng tự quản lý hai mốc: bắt đầu sample và dừng sample bằng cách gắn nó với một `Timer` cụ thể.

Một lỗi phổ biến là tạo `Timer.Sample` nhưng chỉ gọi `sample.stop(timer)` ở nhánh thành công. Nếu method return sớm, ném exception, bị hủy hoặc đi qua một nhánh khác, sample không được dừng và Timer không nhận được mẫu. Một lỗi khác là dừng sample trước khi công việc thực sự hoàn tất, khiến duration ngắn hơn thực tế. Cần đặt điểm stop tại một ranh giới kết thúc duy nhất và bảo đảm mọi nhánh đều đi qua ranh giới đó.

## 1. Timer chỉ ghi nhận mẫu khi thao tác được record hoặc sample được stop

`Timer` lưu count và tổng thời lượng của các lần ghi nhận đã hoàn tất. Với cách dùng trực tiếp:

```java
Timer timer = registry.timer("orders.process");

timer.record(() -> orderService.process(command));
```

Micrometer đo thời gian chạy của lambda và ghi một mẫu khi lambda kết thúc, kể cả khi nó ném exception. Khi dùng `Timer.Sample`:

```java
Timer.Sample sample = Timer.start(registry);

orderService.process(command);

sample.stop(registry.timer("orders.process"));
```

`Timer.start(registry)` chỉ tạo mốc thời gian bắt đầu. Mẫu chỉ được ghi vào Timer khi gọi `sample.stop(timer)`. Nếu sample bị bỏ quên, Timer không tăng count và không cộng duration cho lần thực thi đó.

## 2. Nhận diện lỗi thiếu stop

Ví dụ dưới đây có lỗi: sample chỉ được dừng khi xử lý thành công.

```java
public Order create(CreateOrderCommand command) {
    Timer.Sample sample = Timer.start(registry);

    Order order = repository.save(Order.from(command));

    sample.stop(registry.timer("orders.create"));
    return order;
}
```

Nếu `repository.save(...)` ném exception, dòng `sample.stop(...)` không được thực thi. Lời gọi đã chạy nhưng Timer không ghi nhận lần đó. Khi lỗi xảy ra thường xuyên, count của Timer thấp hơn số lần gọi method thực tế và dashboard có thể cho thấy traffic thấp bất thường.

Các biến thể lỗi thường gặp:

- Có nhiều `return` sớm trước dòng `stop()`.
- `catch` ghi log rồi ném lại exception trước khi dừng sample.
- Một nhánh validation trả về kết quả từ chối mà quên stop.
- `finally` chỉ được thêm ở một nhánh hoặc bị return trước khi vào vùng `try`.
- Sample được tạo ở caller nhưng tác vụ async không bao giờ gọi callback kết thúc.

## 3. Đặt stop trong finally để bao phủ mọi nhánh

Nếu dùng `Timer.Sample`, hãy dừng sample trong `finally`:

```java
public Order create(CreateOrderCommand command) {
    Timer.Sample sample = Timer.start(registry);
    try {
        return repository.save(Order.from(command));
    }
    finally {
        sample.stop(registry.timer("orders.create"));
    }
}
```

`finally` được thực thi khi khối `try` kết thúc bình thường, return hoặc ném exception. Vì vậy, Timer nhận được một mẫu cho cả thành công và thất bại. Exception vẫn tiếp tục truyền ra caller; việc đo thời lượng không thay đổi hành vi nghiệp vụ.

Không gọi `sample.stop()` trong `try` rồi gọi lại trong `finally`. Mỗi sample cần được dừng đúng một lần. Nếu cần chọn tag theo kết quả, lưu trạng thái vào biến cục bộ rồi chỉ gọi `stop()` tại một điểm trong `finally`.

## 4. Ghi nhận kết quả thành công và thất bại bằng tag có kiểm soát

Khi cần tách duration theo kết quả, xác định tag trong quá trình xử lý nhưng vẫn dừng sample ở một vị trí:

```java
public Order create(CreateOrderCommand command) {
    Timer.Sample sample = Timer.start(registry);
    String result = "failure";

    try {
        Order order = repository.save(Order.from(command));
        result = "success";
        return order;
    }
    finally {
        sample.stop(registry.timer(
            "orders.create",
            "result", result));
    }
}
```

Giá trị mặc định `failure` bảo đảm exception trước khi cập nhật kết quả vẫn được phân loại. Nếu nghiệp vụ có nhiều kết quả như `rejected`, `not_found` hoặc `retryable_error`, hãy chuẩn hóa về một tập hữu hạn. Không đưa exception message, request ID hoặc entity ID vào tag vì chúng làm tăng cardinality.

Nếu có nhiều loại exception cần phân biệt, có thể đặt `result` trong `catch` dựa trên loại lỗi đã chuẩn hóa rồi ném lại exception; vẫn để `finally` là nơi duy nhất dừng sample.

## 5. Dùng Timer.record khi không cần chọn Timer lúc kết thúc

Nếu tên và tag đã biết trước khi chạy, `Timer.record(...)` thường an toàn và ngắn gọn hơn `Timer.Sample`:

```java
Timer createTimer = registry.timer("orders.create");

public Order create(CreateOrderCommand command) {
    return createTimer.record(
        () -> repository.save(Order.from(command)));
}
```

`record(Supplier<T>)` đo thời gian của supplier và ghi nhận duration khi supplier kết thúc, kể cả khi nó ném exception. Các overload `record(Runnable)` và `recordCallable(Callable<T>)` cũng phù hợp với kiểu tác vụ tương ứng; `recordCallable` cho phép xử lý callable có checked exception.

Đăng ký Timer một lần và giữ tham chiếu trong field của bean. Không tạo builder mới trong mỗi request. Dùng `Timer.Sample` khi cần bắt đầu ở một nơi và chọn Timer/tag ở nơi khác, hoặc khi ranh giới bắt đầu/kết thúc không thể gói trong một lambda đơn giản.

## 6. Đừng dừng Timer quá sớm

Timer phải bao quanh đúng phần công việc muốn đo. Ví dụ sai khi đo tác vụ async:

```java
public CompletableFuture<Order> createAsync(CreateOrderCommand command) {
    Timer.Sample sample = Timer.start(registry);
    try {
        return CompletableFuture.supplyAsync(
            () -> repository.save(Order.from(command)), executor);
    }
    finally {
        sample.stop(registry.timer("orders.create"));
    }
}
```

`finally` chạy ngay khi `supplyAsync(...)` trả về Future, không đợi công việc hoàn tất. Timer trong ví dụ chỉ đo thời gian submit, không đo thời gian xử lý. Để đo processing duration, đặt sample bên trong worker:

```java
public CompletableFuture<Order> createAsync(CreateOrderCommand command) {
    return CompletableFuture.supplyAsync(() -> {
        Timer.Sample sample = Timer.start(registry);
        try {
            return repository.save(Order.from(command));
        }
        finally {
            sample.stop(registry.timer("orders.create.processing"));
        }
    }, executor);
}
```

Nếu mục tiêu là đo end-to-end từ lúc caller gửi tác vụ đến khi Future hoàn tất, gắn callback hoàn tất và dừng sample ở callback. Cần xác định rõ đang đo submit, queue wait, processing hay end-to-end; không dùng một tên metric chung cho các ranh giới khác nhau.

## 7. Xử lý CompletableFuture và cancellation

Đo end-to-end cho Future có thể dùng `whenComplete`:

```java
public CompletableFuture<Order> createAsync(CreateOrderCommand command) {
    Timer.Sample sample = Timer.start(registry);
    CompletableFuture<Order> future;

    try {
        future = CompletableFuture.supplyAsync(
            () -> repository.save(Order.from(command)), executor);
    }
    catch (RuntimeException exception) {
        sample.stop(registry.timer("orders.create.end.to.end", "result", "rejected"));
        throw exception;
    }

    return future.whenComplete((order, error) -> {
        String result = error == null ? "success" : "failure";
        sample.stop(registry.timer(
            "orders.create.end.to.end", "result", result));
    });
}
```

Callback chạy khi Future hoàn tất bình thường, exceptional hoặc bị cancel, vì vậy sample end-to-end được dừng ở callback. Trong thực tế, nên chuẩn hóa riêng kết quả `cancelled` nếu cần phân biệt. Nếu executor từ chối tác vụ đồng bộ ngay lúc submit, nhánh `catch` dừng sample với `result=rejected`.

Lưu ý: cancel Future không đảm bảo code worker đã dừng ngay lập tức. Callback có thể chạy khi Future được đánh dấu cancelled trong khi task bên dưới vẫn đang thực thi hoặc bỏ qua interrupt. Timer end-to-end của Future đo vòng đời Future; muốn đo thời gian worker thực sự chạy, đặt một Timer riêng trong worker và dừng trong `finally` ở worker.

## 8. Kiểm tra mọi nhánh return và exception

Khi review một method dùng `Timer.Sample`, lập bảng các đường kết thúc:

| Đường thực thi | Có đi qua `finally`? | Timer có ghi nhận? |
| --- | --- | --- |
| Trả về thành công từ `try` | Có | Có |
| Return sớm bên trong `try` | Có | Có |
| Ném unchecked exception trong `try` | Có | Có |
| Ném checked exception trong `try` | Có | Có |
| Exception bị catch rồi trả fallback | Có | Có; tag phản ánh kết quả fallback nếu code đặt đúng |
| Exception xảy ra trước khi sample được tạo | Không có sample | Không có mẫu; đây là khoảng ngoài ranh giới đo |
| Async task được submit nhưng chưa hoàn tất | Chưa chạy callback completion | Sample end-to-end vẫn active, chưa ghi mẫu |

Đặc biệt chú ý các `return` nằm trong `catch` và các callback bất đồng bộ. `finally` chỉ bao phủ luồng điều khiển của method hiện tại; nó không tự bao phủ công việc tiếp tục sau khi method trả Future.

## 9. Không để nhiều nhánh cùng dừng một sample

Một lỗi đối nghịch là gọi `stop()` ở nhiều nơi:

```java
Timer.Sample sample = Timer.start(registry);
try {
    return service.execute();
}
catch (RuntimeException exception) {
    sample.stop(errorTimer);
    throw exception;
}
finally {
    sample.stop(successTimer); // Sai: sample đã bị dừng ở catch.
}
```

Đoạn code trên có thể ghi nhận hai lần hoặc gây kết quả không mong đợi tùy implementation; không dựa vào việc `stop()` có được bảo vệ lặp hay không. Hãy chọn Timer đích trước khi dừng và chỉ có một điểm gọi `sample.stop(...)`.

```java
Timer.Sample sample = Timer.start(registry);
String result = "success";
try {
    return service.execute();
}
catch (RuntimeException exception) {
    result = "failure";
    throw exception;
}
finally {
    sample.stop(registry.timer("service.execute", "result", result));
}
```

## 10. Đảm bảo sample được sở hữu bởi đúng tác vụ

Không lưu một `Timer.Sample` vào field của singleton service rồi dùng lại cho nhiều request. Mỗi request cần sample riêng vì thời điểm bắt đầu và kết thúc khác nhau. Giữ sample trong biến cục bộ hoặc gắn nó với callback/tác vụ cụ thể.

```java
// Đúng: mỗi invocation tạo một sample riêng.
public void execute(Job job) {
    Timer.Sample sample = Timer.start(registry);
    try {
        job.run();
    }
    finally {
        sample.stop(jobTimer);
    }
}
```

Không dùng `ThreadLocal<Timer.Sample>` như giải pháp mặc định. Thread pool tái sử dụng thread; nếu không xóa trạng thái ở mọi nhánh, sample của request trước có thể bị nhầm với request sau. Truyền sample qua closure hoặc tham số của task giúp quan hệ sở hữu rõ ràng hơn.

## 11. Timer không tăng vì meter bị lọc hoặc sai định danh

Nếu `sample.stop(timer)` đã chạy nhưng dashboard vẫn không thấy số liệu, cần kiểm tra registry và meter identity:

- `MeterFilter` có thể deny meter theo tên hoặc tag.
- Tên metric thực tế có thể đã được đổi bởi filter hoặc quy tắc chuẩn hóa của exporter.
- Tag ở lúc stop có thể khác tag mà dashboard đang lọc.
- Code có thể đang ghi vào một `MeterRegistry` khác với registry được exporter scrape.
- Backend có thể chưa scrape mẫu mới hoặc dashboard đang dùng selector sai.

Kiểm tra trực tiếp trong ứng dụng:

```java
Timer timer = registry.find("orders.create")
    .tag("result", "success")
    .timer();

if (timer != null) {
    log.info("count={}, totalTimeMs={}",
        timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
}
```

`find(...)` giúp xác định meter có tồn tại với tập tag đó trong registry hay không. Nếu `timer` là `null`, xem lại tên, tag và filter. Nếu meter tồn tại nhưng count bằng 0, kiểm tra sample stop hoặc record path.

## 12. Kiểm thử Timer ghi nhận cả success và exception

Dùng `SimpleMeterRegistry` để kiểm tra hành vi mà không cần exporter:

```java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TimerRecordingTest {
    @Test
    void recordsDurationWhenOperationThrows() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Timer timer = registry.timer("orders.create");

        assertThrows(IllegalStateException.class, () ->
            timer.record((Runnable) () -> {
                throw new IllegalStateException("database unavailable");
            }));

        assertEquals(1, timer.count());
        registry.close();
    }
}
```

Test xác minh `Timer.record(...)` vẫn ghi một mẫu khi supplier ném exception. Với code dùng `Timer.Sample`, viết test riêng cho success, early return và exception rồi kiểm tra count của meter đích sau mỗi lần gọi.

Không nên assert một duration mili giây cố định trong test thông thường vì scheduler và máy chạy test làm thời gian dao động. Nếu cần kiểm tra chính xác duration, dùng `MockClock` và tiến clock chủ động.

## 13. Kiểm thử Timer.Sample với MockClock

`MockClock` cho phép kiểm tra rõ việc mẫu chỉ được ghi khi `stop()` được gọi:

```java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TimerSampleLifecycleTest {
    @Test
    void recordsOnlyAfterSampleIsStopped() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        Timer timer = registry.timer("orders.create");

        Timer.Sample sample = Timer.start(registry);
        assertEquals(0, timer.count());

        clock.add(Duration.ofSeconds(2));
        assertEquals(0, timer.count());

        sample.stop(timer);

        assertEquals(1, timer.count());
        assertEquals(2.0, timer.totalTime(TimeUnit.SECONDS), 0.001);
        registry.close();
    }
}
```

Test cho thấy count vẫn bằng 0 trước khi sample dừng, dù clock đã tiến 2 giây. Chỉ sau `sample.stop(timer)`, Timer mới tăng count và total time. Đây là cách xác minh trực tiếp nguyên nhân “đã start nhưng chưa record”.

## 14. Kiểm tra dữ liệu sau export

Với Spring Boot Actuator, endpoint `/actuator/metrics/orders.create` có thể giúp kiểm tra meter trong registry. Nếu dùng Prometheus, kiểm tra `/actuator/prometheus` và tìm series tương ứng, thường có dạng `_count` và `_sum` sau chuẩn hóa tên và đơn vị.

Khi không thấy dữ liệu:

1. Xác nhận code có gọi `record(...)` hoặc `sample.stop(...)` trên mọi nhánh cần đo.
2. Xác nhận count trong registry tăng ngay sau thao tác.
3. Kiểm tra tên meter và toàn bộ tag, kể cả common tags.
4. Kiểm tra `MeterFilter`, registry được inject và exporter đang scrape đúng instance.
5. Kiểm tra Prometheus target health, scrape interval và dashboard selector.

Nếu count trong registry tăng nhưng Prometheus không có series, lỗi nằm ở cấu hình/export/scrape hoặc truy vấn. Nếu count trong registry không tăng, lỗi nằm ở instrumentation, sample lifecycle, meter identity hoặc filter.

## 15. Các nguyên nhân và cách xử lý nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Count thấp hơn số lần gọi | Thiếu `sample.stop()` ở nhánh exception/return | Đưa stop vào `finally` |
| Count luôn bằng 0 | Sample được start nhưng không stop | Tìm mọi nơi tạo sample và kiểm tra callback kết thúc |
| Duration quá ngắn | Stop ngay sau khi submit Future | Đo trong worker hoặc callback completion theo mục tiêu |
| Duration không tính exception | Timer chỉ được record ở nhánh success | Dùng `Timer.record` hoặc stop trong `finally` |
| Count tăng hai lần | Stop ở cả catch và finally | Chỉ giữ một điểm stop |
| Meter không tìm thấy | Sai tên/tag, registry khác hoặc filter deny | Kiểm tra `registry.find(...)` và cấu hình filter |
| Future bị cancel nhưng sample còn active | Callback không chạy ở ranh giới dự kiến hoặc worker vẫn chạy | Xác định đo Future lifecycle hay worker lifecycle; dừng ở đúng nơi sở hữu sample |
| Dashboard không có series | Exporter chưa scrape hoặc selector sai | Kiểm tra endpoint exposition và target health |

## 16. Quy trình chẩn đoán

Khi Timer không ghi nhận, đi theo thứ tự sau:

1. **Xác định loại API:** code dùng `Timer.record(...)` hay `Timer.Sample`? Nếu dùng Sample, tìm cặp `Timer.start(...)` và `sample.stop(...)`.
2. **Liệt kê đường kết thúc:** success, return sớm, exception, fallback, rejection, cancellation và callback async.
3. **Xác minh điểm stop:** mọi đường kết thúc cần đi qua đúng một lần stop; dùng `finally` cho tác vụ đồng bộ.
4. **Kiểm tra ranh giới đo:** với Future, phân biệt submit duration, worker processing và end-to-end.
5. **Kiểm tra registry:** xác nhận meter đúng tên/tag tồn tại và count tăng trong process.
6. **Kiểm tra export:** xác nhận endpoint Actuator, Prometheus scrape và dashboard selector.

Đừng bắt đầu bằng việc tăng scrape interval hoặc sửa dashboard nếu count trong registry chưa tăng. Những thay đổi đó không thể sửa một sample chưa từng được ghi nhận.

## 17. Nguyên tắc áp dụng

Ưu tiên `Timer.record(...)` khi có thể bao quanh trọn thao tác bằng một khối code. Khi cần `Timer.Sample`, tạo sample riêng cho mỗi invocation và dừng nó tại một điểm kết thúc duy nhất. Với xử lý đồng bộ, `finally` là nơi phù hợp để bảo đảm mọi nhánh success/exception/early return đều được ghi nhận. Với xử lý bất đồng bộ, đặt điểm stop tại worker hoặc completion callback đúng với mục tiêu đo.

Nếu cần phân loại kết quả, chuẩn hóa tag về tập hữu hạn và chọn Timer đích trước khi stop. Không lưu sample dùng chung trong singleton hoặc dừng cùng sample nhiều lần. Kiểm thử cả success lẫn exception bằng `SimpleMeterRegistry`, dùng `MockClock` khi cần duration xác định và kiểm tra count trong registry trước khi điều tra exporter. Như vậy có thể phân biệt lỗi vòng đời instrumentation với lỗi scrape hoặc dashboard.
