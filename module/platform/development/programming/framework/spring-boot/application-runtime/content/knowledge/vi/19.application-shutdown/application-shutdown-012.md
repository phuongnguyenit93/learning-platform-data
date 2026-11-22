# Chẩn đoán hook bị kẹt, tác vụ không kết thúc và callback dừng bị bỏ quên

## 1. Vì sao ứng dụng Spring Boot “không chịu tắt”?

Khi một ứng dụng Spring Boot đang chạy được yêu cầu dừng, các bước tiếp theo không phải là một thao tác `kill` duy nhất. JVM, `ApplicationContext`, `LifecycleProcessor`, bean destroy callbacks, worker threads và tài nguyên bên ngoài có những hợp đồng dừng khác nhau.

Ba triệu chứng phổ biến trông giống nhau nhưng nguyên nhân khác nhau:

1. **Shutdown hook hoặc callback đóng context bị kẹt:** luồng chịu trách nhiệm đóng đang chờ một lock, network I/O, `Future.get()`, `CountDownLatch.await()`, `@PreDestroy` hoặc một hook khác. Lúc này **lời gọi đóng chưa hoàn thành**.
2. **Tác vụ nền không kết thúc:** Spring đã phát lệnh shutdown, thậm chí `ApplicationContext.close()` đã trở về, nhưng còn một **non-daemon thread** hoặc resource vẫn sống. JVM có thể vẫn chạy nếu việc đóng context không tự kết thúc tiến trình; với shutdown do `System.exit` kích hoạt, JVM sẽ chờ các shutdown hooks chứ không chờ mọi non-daemon thread theo cùng cách.
3. **`SmartLifecycle.stop(Runnable)` bỏ quên callback:** bean có thể đã ngừng hoạt động thật, nhưng `DefaultLifecycleProcessor` chưa nhận được tín hiệu hoàn thành nên chờ đến **timeout của phase** trước khi đi tiếp. Đây thường là **chờ có hạn**, không phải lúc nào cũng là treo vô hạn.

Bài này chỉ ra cách **phân loại triệu chứng**, lấy bằng chứng từ thread dump và log, tái hiện có kiểm soát, tìm nguyên nhân gốc, sau đó sửa code theo đúng hợp đồng của Spring Boot 3.3, Spring Framework 6.1 và Java 17+.

**Nguyên tắc đầu tiên:** đừng tăng timeout hoặc dùng `kill -9` ngay khi mới thấy shutdown chậm. Hãy xác định **giai đoạn nào chưa hoàn thành**, **luồng nào đang chờ ai**, và **tài nguyên nào chưa xác nhận đã dừng**. Nếu tác vụ liên quan dữ liệu quan trọng, một lần cưỡng bức dừng có thể để lại công việc chưa ack/commit và cần recovery.

## 2. Phân biệt JVM shutdown hook, lifecycle stop và bean destroy

Một đường dừng bình thường có thể được mô tả:

```text
SIGTERM / System.exit / yêu cầu đóng context
                     |
                     v
        JVM shutdown hook (khi JVM shutdown)
             hoặc context.close() trực tiếp
                     |
                     v
      Spring ApplicationContext bắt đầu close
                     |
             ContextClosedEvent
                     |
             LifecycleProcessor.onClose()
                     |
           SmartLifecycle.stop(callback)
              theo phase giảm dần
                     |
      đợi callback hoặc timeout từng phase
                     |
                     v
            Destroy singleton beans
         @PreDestroy / DisposableBean /
             @Bean destroy method
                     |
                     v
         ApplicationContext.close() hoàn tất
                     |
          JVM tiến tới kết thúc nếu đủ điều kiện
```

**Đây là luồng logic rút gọn**. `ContextClosedEvent` được phát ở đầu đường đóng context; nhận được sự kiện đó **không chứng minh** lifecycle stop, bean destruction và flush tài nguyên đã hoàn tất. Khi đóng qua `System.exit()` hoặc signal, Java VM thực thi các shutdown hooks của nó. Khi gọi `context.close()` trực tiếp, code đóng chạy trên luồng gọi; đó không nhất thiết là một JVM shutdown-hook thread.

### 2.1. JVM shutdown hook

Spring Boot `SpringApplication` mặc định đăng ký cơ chế shutdown hook để đóng `ApplicationContext` khi JVM kết thúc theo đường hỗ trợ. `SpringApplication.setRegisterShutdownHook(boolean)` có thể điều chỉnh hành vi này trước `run`. Không nên tắt hook chỉ để làm tiến trình thoát nhanh khi còn resource cần dọn.

Java `Runtime.addShutdownHook(Thread)` cho phép các thư viện hoặc ứng dụng đăng ký hook riêng. JVM khởi động các hook theo **thứ tự không được bảo đảm** và cho phép chúng chạy **đồng thời**. Vì vậy không thể dựa vào việc “đăng ký hook A trước hook B” để bảo đảm B chỉ chạy sau A. Nếu một hook tự chờ hook khác nhưng hai hook giữ những lock phụ thuộc lẫn nhau, cả shutdown có thể kẹt.

**Không** gọi `System.exit()` từ bên trong shutdown hook như một cơ chế dừng lại lần hai. Chỉ tạo những hook thật sự cần thiết; với tài nguyên đã thuộc Spring container, ưu tiên lifecycle/destroy của Spring thay vì đăng ký thêm một JVM hook trùng trách nhiệm.

### 2.2. SmartLifecycle và phase

`SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Với bean đang running, `DefaultLifecycleProcessor` gọi:

```java
void stop(Runnable callback);
```

Nó **không gọi `stop()` không tham số** cho `SmartLifecycle` nếu implementation đã có overload callback và không tự delegate. Để phối hợp dừng bất đồng bộ, callback **phải được thực thi sau khi bean thực sự dừng**.

Phase quyết định thứ tự:

```text
Start: phase thấp trước phase cao
Stop:  phase cao trước phase thấp
```

Ví dụ consumer phase 200 phụ thuộc writer phase 100: consumer được yêu cầu dừng trước writer. Khi consumer hoàn tất drain, gọi callback để processor có thể đi tới phase 100. Nếu callback mất, processor đợi hết timeout trước khi thử stop writer. Nếu callback **được gọi quá sớm**, writer có thể đóng trong khi consumer còn dùng nó.

Trong Spring Framework 6.1, `DefaultLifecycleProcessor` có timeout mặc định **30.000 ms cho mỗi shutdown phase** nếu không điều chỉnh; trong Spring Boot 3.3 có thể cấu hình:

```properties
spring.lifecycle.timeout-per-shutdown-phase=3s
```

Đây là thời gian chờ cho **một nhóm phase**, không phải timeout tổng cho toàn bộ quy trình đóng context.

### 2.3. @PreDestroy và destroy method

Sau phần dừng lifecycle, Spring hủy singleton beans và gọi những callbacks như:

- `@PreDestroy` của bean Spring (dùng `jakarta.annotation.PreDestroy` với Spring Boot 3.x).
- `DisposableBean.destroy()`.
- Destroy method tường minh của `@Bean(destroyMethod="close")` hoặc cơ chế suy luận phù hợp.

Các callback này có thể **chạy đồng bộ và chặn luồng đóng context**. Cấu hình `spring.lifecycle.timeout-per-shutdown-phase` **không tự đặt deadline** cho bất cứ method `@PreDestroy` nào đang mắc kẹt ở socket read, `Thread.join()` hoặc `CountDownLatch.await()` không giới hạn.

Đừng gắn `@PreDestroy` cho mọi component và cho rằng Spring đã đảm bảo dừng bất đồng bộ sạch. Mỗi resource cần timeout/cancellation của chính nó, hoặc cơ chế completion phù hợp.

## 3. Phân loại triệu chứng bằng ba câu hỏi

Khi thấy quy trình deploy/terminal đứng yên tại bước shutdown, hãy trả lời theo thứ tự:

**Câu 1 — `ApplicationContext.close()` đã trả về chưa?**

- Nếu **chưa**, nghi ngờ một `SmartLifecycle` phase còn chờ callback, một destroy method đang block, thread trong hook đang giữ lock, hoặc phần cleanup khác.
- Nếu **đã**, mà process vẫn sống trong đường đóng context trực tiếp, nghi ngờ một **non-daemon thread** còn chạy, một library-managed executor chưa tắt, timer hoặc background worker. Một số process vẫn sống do phần code khác tiếp tục thực thi; phải xác định từ thread dump.
- Nếu đang xử lý `System.exit()`, nhớ rằng JVM đợi **tất cả shutdown hooks kết thúc**. Không suy luận cùng hành vi từ một lượt đóng context trực tiếp.

**Câu 2 — log ngừng ở phase/callback nào?**

- Có `STOP begin` nhưng không có `STOP callback` rồi sau vài giây có thông báo timeout phase: nghi ngờ callback bị bỏ quên, callback nằm trên một worker bị lỗi, hoặc cleanup chưa xong.
- Có `DESTROY begin` mà không có `DESTROY end`: nghi ngờ destroy callback đồng bộ đang block.
- Có `CONTEXT close completed` nhưng process không ra: nghi ngờ luồng sống ngoài lifecycle; kiểm tra daemon status và stack của thread.

**Câu 3 — thread dump cho biết luồng chờ cái gì?**

- `CountDownLatch.await`, `Future.get`, `Thread.join`, `ConditionObject.await`: tìm **ai phải phát tín hiệu** và luồng đó đang làm gì.
- `ThreadPoolExecutor.awaitTermination`: tìm task chưa kết thúc và có phản ứng interruption không.
- `BLOCKED` trên monitor: tìm owner của monitor; nghi ngờ lock contention/deadlock.
- `SocketInputStream`, driver I/O, native read: tìm timeout cấp client/resource.
- `DefaultLifecycleProcessor` chờ latch trong phase: đọc log `stop(Runnable)` để biết bean nào chưa callback.

Đừng đánh đồng `TIMED_WAITING` với “đã mắc kẹt”: một thread pool idle có thể chờ queue bình thường. Cần kết hợp **vị trí stack**, **giai đoạn đóng**, **thời gian trôi** và **nhiều mẫu dump**.

## 4. Ma trận chẩn đoán nhanh

| Biểu hiện | Bằng chứng nên tìm | Nguyên nhân khả dĩ | Việc sửa |
|---|---|---|---|
| Dừng chậm gần đúng timeout của phase | Log `DefaultLifecycleProcessor`; callback chưa xuất hiện | `SmartLifecycle` quên callback | Gọi callback sau khi cleanup thực sự xong; test timeout |
| Dừng nhanh bất thường nhưng vẫn còn work | Callback đã đến ngay sau `shutdown()` | Callback quá sớm | Chờ `awaitTermination`/completion đúng semantics |
| Có `@PreDestroy begin` nhưng không có end | Thread dump trong method destroy | I/O/lock/Future không có deadline | Deadline cấp tài nguyên, force close có kiểm soát |
| Context đã đóng nhưng Java process chưa thoát | Dump còn non-daemon worker | Executor không shutdown/task phớt lờ interrupt | Thiết kế shutdown/rejection/cancellation |
| Hook thread đang chờ `CountDownLatch.await` | Dump có hook stack | Không có thread nào `countDown` hoặc bị deadlock | Sửa giao thức completion |
| Hook và worker cùng giữ/chờ lock | Dump có cycle `BLOCKED` | Deadlock | Thứ tự lock nhất quán; không chờ Future khi giữ lock |
| CPU cao lúc tắt | Dump nhiều lần thấy vòng lặp `RUNNABLE` | Spin loop không có cờ stop/visibility | Kiểm tra `volatile`/atomic/cancellation |
| Chỉ treo trong IDE | IDE dùng stop cưỡng bức, tín hiệu khác production | Không đi qua đường graceful shutdown | Tái hiện bằng signal/close hợp lệ |
| Chỉ treo ở container | Grace period quá ngắn, sidecar/network dependency đã dừng | Shutdown budget/order sai | Tương thích timeout nhiều lớp |
| `jcmd` không kết nối | PID/namespace/user/JDK khác, attach không khả dụng | Hạn chế môi trường | Dùng công cụ trong container hoặc thread-dump signal khi được hỗ trợ |
| `ContextClosedEvent` đã log nhưng vẫn chờ | Event xảy ra trước stop/destroy | Hiểu sai mốc lifecycle | Gắn log bắt đầu/kết thúc cho mỗi phase/callback |
| Một lần stop chạy hai lần | JVM hook và close trực tiếp, hoặc nhiều đường destroy | Resource close thiếu idempotency | Một owner, state OPEN/CLOSING/CLOSED, completion chung |

Mỗi hàng là **giả thuyết**, không phải kết luận tự động. Lấy stack trace và timeline để chứng minh nguyên nhân trước khi thay đổi kiến trúc.

## 5. Thu thập bằng chứng khi JVM còn sống

### 5.1. Ghi nhận timeline trước khi can thiệp

Từ log/telemetry, ghi lại:

1. Thời điểm nhận `SIGTERM`/yêu cầu stop.
2. Thời điểm bắt đầu `ApplicationContext.close()` hoặc shutdown hook.
3. Tên bean/phase khi gọi `stop(Runnable)`.
4. Thời điểm gửi lệnh ngừng intake, số in-flight tasks, queue length.
5. Thời điểm callback được gọi và phase chuyển tiếp.
6. Thời điểm `@PreDestroy` bắt đầu/kết thúc.
7. Thời điểm context đóng xong và thời điểm process thực sự kết thúc.

Ví dụ cách ghi log hữu ích (pseudocode):

```text
15:00:00.000 shutdown-requested pid=12345
15:00:00.008 lifecycle-stop-begin bean=consumer phase=200 inflight=3
15:00:00.180 consumer-drained inflight=0
15:00:00.181 lifecycle-stop-callback bean=consumer phase=200
15:00:00.185 lifecycle-stop-begin bean=writer phase=100
15:00:00.250 lifecycle-stop-callback bean=writer phase=100
15:00:00.260 bean-destroy-begin bean=dbClient
15:00:00.310 bean-destroy-end bean=dbClient
15:00:00.312 context-closed
```

Đây là **timeline minh họa**, không phải log mặc định được Spring Boot tự in. Trong production, nên cấu trúc log để có `bean`, `phase`, `thread`, `durationMs` và `outcome`; tránh log payload/secrets.

### 5.2. Tìm PID Java

Linux/macOS với JDK:

```bash
jcmd -l
```

hoặc:

```bash
jps -lv
```

Trong container, PID quan sát từ host có thể khác PID bên trong namespace. Chạy công cụ **trong cùng PID namespace, cùng quyền phù hợp và có JDK/tool attach**, không đoán PID từ log của một instance khác.

Windows PowerShell:

```powershell
jcmd -l
```

Nếu tool không có trên máy chứa JVM (ví dụ image chỉ có JRE), cần chuẩn bị quy trình capture phù hợp môi trường — không cài tooling trực tiếp vào pod production một cách tùy tiện.

### 5.3. Chụp nhiều thread dumps

Giả sử PID là `12345`:

```bash
jcmd 12345 Thread.print -l > dump-1.txt
sleep 2
jcmd 12345 Thread.print -l > dump-2.txt
```

Hoặc thử:

```bash
jstack -l 12345 > dump-jstack.txt
```

JDK/VM có thể hỗ trợ tùy chọn khác; dùng `jcmd 12345 help Thread.print` để kiểm tra. Một dump rất hữu ích, **hai hoặc ba dump cách nhau một khoảng ngắn** còn cho thấy stack đang tiến triển hay đứng yên. Chỉ chụp khi JVM vẫn còn sống; khi bị `SIGKILL`, không thể attach để lấy trạng thái cuối.

Windows PowerShell (khi đã biết PID):

```powershell
jcmd 12345 Thread.print -l | Out-File dump-1.txt
Start-Sleep -Seconds 2
jcmd 12345 Thread.print -l | Out-File dump-2.txt
```

Với HotSpot trên Linux, có thể yêu cầu in dump vào stdout/log của process bằng:

```bash
kill -QUIT 12345
```

Tín hiệu **`SIGQUIT`** dành cho thread dump trong nhiều triển khai HotSpot/Linux; nó khác với `SIGTERM` là tín hiệu yêu cầu dừng. Hãy kiểm tra VM, nền tảng và quyền trước khi gửi signal. Đừng nhầm `kill -9` (cưỡng bức kết thúc) với một công cụ thu thập stack.

### 5.4. Đọc stack của thread nào trước?

Ưu tiên:

- Thread liên quan `SpringApplicationShutdownHook` hoặc `SpringContextShutdownHook` nếu có tên tương tự, hoặc thread có stack `AbstractApplicationContext.doClose`, `DefaultLifecycleProcessor.stopBeans`.
- Thread đang chạy `DisposableBeanAdapter.destroy`, `@PreDestroy` hoặc custom `close()`.
- Worker có tên tương ứng executor/message consumer/queue đang không kết thúc.
- Thread chờ `CountDownLatch.await`, `FutureTask.get`, `ThreadPoolExecutor.awaitTermination`.
- Thread giữ monitor mà những thread khác đang chờ.

**Đừng suy luận chỉ từ thread name.** Tên phụ thuộc Spring Boot/JDK/library và cách chương trình đặt tên. Stack frame, monitor owner và dữ liệu runtime mới là bằng chứng mạnh.

### 5.5. Mẫu dump phân biệt chờ bình thường và lỗi

Một đoạn minh họa **không phải dump thật của Spring**:

```text
"SpringApplicationShutdownHook" ... TIMED_WAITING
  at java.util.concurrent.CountDownLatch.await(...)
  at org.springframework.context.support.DefaultLifecycleProcessor...
```

Có thể là lifecycle processor đang chờ callback của một phase. Nếu sau timeout nó tiếp tục và context đóng, có thể đang thiếu callback hoặc callback quá chậm.

Một dạng khác:

```text
"SpringApplicationShutdownHook" ... TIMED_WAITING
  at java.util.concurrent.ThreadPoolExecutor.awaitTermination(...)
  at com.example.Worker.close(...)
  at ... DisposableBeanAdapter.destroy(...)
```

Đây là chờ trong destroy callback. **Cấu hình `timeout-per-shutdown-phase` không nhất thiết ảnh hưởng tới đoạn await này.**

Một dạng nữa:

```text
"custom-worker-1" ... RUNNABLE/TIMED_WAITING
  at com.example.Worker.longRunningLoop(...)
```

Khi context đã close nhưng thread này vẫn sống và non-daemon, hãy kiểm tra vòng lặp có điểm dừng hoặc phản ứng interrupt không.

### 5.6. JFR và Actuator

JDK Flight Recorder có thể giúp phân tích blocking, lock contention, CPU và I/O trước khi bắt đầu shutdown. Ví dụ (nếu process còn attach được):

```bash
jcmd 12345 JFR.start name=shutdown-check settings=profile duration=30s filename=shutdown-check.jfr
```

Phải khởi động recording **trước hoặc trong giai đoạn có vấn đề**; một recording bắt đầu sau khi process đã chết không giúp gì. Với `duration`, cần đảm bảo JVM sống đủ lâu để xuất file, và chi phí profile phù hợp môi trường.

Nếu ứng dụng đã cấu hình Spring Boot Actuator, endpoint `/actuator/threaddump` có thể cung cấp thông tin khi HTTP server còn phục vụ. Trong shutdown, server có thể đã ngừng nhận request mới nên **không nên chỉ dựa vào endpoint này**. Bảo vệ endpoint khỏi truy cập công khai và tránh lộ stack, đường dẫn hoặc thông tin nhạy cảm.

## 6. Chẩn đoán callback SmartLifecycle bị bỏ quên

### 6.1. Hợp đồng của stop(Runnable)

Với `SmartLifecycle` của Spring Framework 6.1, `stop(Runnable callback)` có hai nhiệm vụ:

1. Yêu cầu/tiến hành dừng thành phần.
2. **Gọi đúng callback được Spring cung cấp sau khi việc dừng hoàn tất.**

`DefaultLifecycleProcessor` dùng callback này để biết bean đã xong. Dù bạn dùng thread mới hay `CompletableFuture`, callback không tự chạy nếu bạn quên nó.

Cách sai:

```java
@Override
public void stop(Runnable callback) {
    consumer.stopAsync();
    // Không gắn callback vào completion.
}
```

Đây là snippet lỗi cố ý; `consumer` là thư viện giả định. `stopAsync()` được gọi không có nghĩa cleanup đã xong, và Spring sẽ không biết khi nào dừng hoàn tất.

Cách khác cũng sai:

```java
@Override
public void stop(Runnable callback) {
    consumer.stopAsync();
    callback.run(); // Báo xong quá sớm.
}
```

Khi callback đến trước resource thật sự ngừng, Spring có thể stop bean phase thấp hơn (ví dụ writer/database) trong khi consumer vẫn sử dụng.

### 6.2. Làm thế nào xác định bean nào quên callback?

Gắn log **trước khi gọi stop**, **khi resource thực sự hoàn tất**, và **ngay trước callback**:

```java
@Override
public void stop(Runnable callback) {
    log.info("stop-begin bean={} phase={}", "consumer", getPhase());

    CompletionStage<Void> stage = consumer.stopAsync();

    stage.whenComplete((ignored, error) -> {
        try {
            if (error != null) {
                log.error("consumer-stop-failed", error);
                forceCloseIfNecessary();
            }
        } finally {
            log.info("stop-callback bean={}", "consumer");
            callback.run();
        }
    });
}
```

Đây là **pseudocode tích hợp**, không phải class tự chứa: `consumer`, `log` và `forceCloseIfNecessary()` phải được thiết kế thật. Nhánh lỗi phải bảo đảm đã kết thúc quy trình dừng/force-close theo chính sách trước khi báo completion; đừng mặc nhiên xem `finally` là bằng chứng mọi dữ liệu đã flush.

Nếu `stage` không bao giờ complete vì I/O treo, callback sẽ không chạy. Vì vậy cần **timeout ở resource/future**, không chỉ timeout của `LifecycleProcessor`.

### 6.3. Những nhánh dễ bỏ sót

- `stop(Runnable)` return sớm vì `!running` nhưng quên gọi callback.
- `executor.execute(cleanupTask)` ném `RejectedExecutionException` trước khi callback được lên lịch.
- Cleanup ném exception giữa chừng; callback đặt ở cuối happy path.
- `CompletableFuture.thenRun(...)` không chạy khi future hoàn tất exceptional; cần đường `whenComplete`/`handle` và chính sách lỗi.
- Một callback được đưa vào queue nhưng chính executor của queue đã bị shutdown.
- `stop()` không tham số chứa logic dừng, nhưng overload `stop(Runnable)` không delegate.
- Callback bị gọi **hai lần** từ `try` và `finally`; lần thứ hai không phải một retry hợp lệ.

Hãy kiểm tra **mỗi đường điều khiển**, không chỉ happy path. Trong một invocation của `stop(Runnable)`, nên phát callback chính xác một lần và sau khi resource đạt trạng thái dừng theo hợp đồng.

## 7. Chẩn đoán task không kết thúc sau shutdown()

### 7.1. ExecutorService shutdown API không giống nhau

| API | Điều nó đảm bảo | Điều nó không đảm bảo |
|---|---|---|
| `shutdown()` | Ngừng nhận task mới, để task đã nhận có cơ hội hoàn tất | Không chờ task xong |
| `isShutdown()` | Có yêu cầu shutdown | Không đồng nghĩa terminated |
| `awaitTermination(timeout, unit)` | Chờ tối đa một khoảng, trả `true` nếu executor terminated | Không tự giết task còn chạy |
| `shutdownNow()` | Cố ngắt task đang chạy và trả các task chưa bắt đầu | Không thể buộc task phớt lờ interrupt phải dừng |
| `isTerminated()` | Executor đã kết thúc sau shutdown | Không chứng minh mọi transaction nghiệp vụ đã commit |
| `Future.get(timeout, unit)` | Chờ một future trong khoảng cho phép | Timeout ở caller không tự hủy task |

Ví dụ dễ sai:

```java
executor.shutdown();
System.out.println("All tasks stopped"); // Chưa có cơ sở!
```

Giải pháp thường gồm `shutdown()`, `awaitTermination`, sau deadline thì `shutdownNow()`, tiếp tục đợi có giới hạn và **báo trạng thái không xác nhận** nếu vẫn chưa terminated.

### 7.2. Vì sao shutdownNow vẫn không giải quyết được?

Interruption là cơ chế **hợp tác**. Nếu task viết:

```java
while (true) {
    try {
        Thread.sleep(1000);
    } catch (InterruptedException ignored) {
        // Sai: nuốt interrupt và tiếp tục mãi.
    }
}
```

thì gọi `shutdownNow()` có thể không làm thread kết thúc. Đây là code lỗi cố ý; **không chạy trong một process production**.

Tương tự, một lệnh blocking I/O hoặc native code không có timeout phù hợp có thể không phản ứng với interrupt theo cách bạn mong đợi.

Cách sửa là thiết kế **cờ dừng**, cancellation, giới hạn thời gian ở thư viện I/O, đóng socket/channel để unblock nếu hỗ trợ, và đường recovery khi công việc chưa xác nhận hoàn tất.

### 7.3. Lỗi tự chờ chính mình

Một task chạy trên executor một worker gọi:

```java
executor.shutdown();
executor.awaitTermination(30, TimeUnit.SECONDS);
```

ngay **trong cùng worker đó**. Executor không thể terminated cho tới khi task hiện tại trả về, còn task đang chờ executor terminated. Đây là dạng self-wait/starvation. Chạy điều phối shutdown trên thread khác, hoặc dùng phương thức bất đồng bộ không chặn chính worker phải kết thúc.

Một trường hợp tương tự: task A trong pool một thread submit task B cũng vào pool đó rồi gọi `B.get()`. B không có worker để chạy. Thread dump có thể thấy `FutureTask.get()` và task trong queue, nhưng deadlock detector dựa vào Java monitor **không nhất thiết báo deadlock**. Vì thế “`jstack` không thấy deadlock” **không phải** bằng chứng mọi task đều có đường tiến.

### 7.4. Non-daemon worker còn sống

Thread `daemon=false` có thể giữ JVM chưa thoát sau khi code ứng dụng kết thúc theo đường bình thường. Trong khi `System.exit()` khởi tạo JVM shutdown sequence và chờ hooks, với việc chỉ đóng Spring context trực tiếp rồi `main` trả về, các non-daemon threads chưa dừng là nguyên nhân thường thấy khiến process còn sống.

Không được giải quyết bằng cách chuyển tùy tiện mọi worker thành daemon. Daemon có thể bị JVM bỏ lại khi kết thúc, làm công việc đang chạy không được flush. Hãy quản lý executor/worker bằng owner và shutdown phù hợp.

## 8. Chẩn đoán hook bị kẹt do lock, Future hoặc I/O

### 8.1. JVM hooks không có thứ tự đăng ký bảo đảm

Ví dụ nguy hiểm:

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    otherHookCompleted.await();
}));
```

Đây là pseudocode lỗi, chưa xử lý checked exception. Nếu hook “khác” chưa bao giờ phát tín hiệu hoặc đang đợi lại lock do hook này giữ, JVM có thể chờ mãi. Không nên thiết kế phụ thuộc giữa các JVM shutdown hooks dựa vào thứ tự chạy.

Khi tài nguyên thuộc Spring context, hãy dùng **một đường điều phối trong context** để có thứ tự phase, thay vì tạo nhiều hooks JVM tự chờ lẫn nhau.

### 8.2. Chờ Future khi đang giữ khóa

Một anti-pattern:

```java
synchronized (sharedLock) {
    Future<?> result = executor.submit(() -> {
        synchronized (sharedLock) {
            flush();
        }
    });

    result.get(); // Caller giữ sharedLock và chờ worker cần sharedLock.
}
```

Đây là **pseudocode lỗi**: giả định có `sharedLock`, `executor` và `flush()` thật, checked exceptions phải xử lý. Hook hoặc destroy callback có thể kẹt ở `Future.get`, worker kẹt `BLOCKED` chờ lock; đây là vòng phụ thuộc.

Sửa bằng cách **không chờ Future khi giữ lock mà task cần**, chuyển trạng thái dưới lock rồi thả lock trước khi drain; hoặc thiết kế event/completion không re-enter vào cùng monitor.

### 8.3. I/O không có timeout

Một shutdown callback gọi `client.close()`, nhưng bên dưới nó flush network và chờ server xác nhận vô hạn. Spring có thể không chặn được việc này bằng `spring.lifecycle.timeout-per-shutdown-phase` nếu hoạt động đang chạy **đồng bộ trong destroy method**. Hãy đặt timeout ở client/driver hoặc thiết kế dừng bất đồng bộ có giới hạn và chính sách force-close.

Chỉ bọc `client.close()` trong `CompletableFuture` rồi `get(2,SECONDS)` **không tự ngắt** lời gọi close ở thread nguồn. Nếu thread nguồn không dừng, vấn đề có thể chỉ được chuyển sang một worker khác và vẫn giữ process sống.

### 8.4. Hook bị kẹt vì shutdown thứ tự sai

Ví dụ consumer cần DB client để flush nhưng DB client đã bị đóng trước. Consumer retry vô hạn hoặc kẹt ở Future chờ kết quả không đến. Cần kiểm tra quan hệ:

```text
Start: database client -> writer -> consumer
Stop:  consumer -> writer -> database client
```

`SmartLifecycle.getPhase()` và dependency graph giúp định thứ tự; phase cao được yêu cầu stop trước. Nhưng chỉ đổi phase **không giúp** nếu callback đến quá sớm hoặc task không có deadline.

## 9. Ví dụ chạy được: bốn chế độ chẩn đoán shutdown

Dự án sau hướng tới **Spring Boot 3.3.x + Java 17**, Gradle Groovy DSL, **không cần Web server**. Chúng ta tạo hai thành phần tách biệt:

- `DemoLifecycle`: một `SmartLifecycle` có thể cố ý bỏ quên callback ở chế độ `missing-callback`.
- `DemoBlockingResource`: một bean dùng `@PreDestroy`; có thể tạo worker phớt lờ interrupt trong **thời hạn hữu hạn 25 giây** (`stuck-task`) hoặc chờ trong destroy **12 giây** (`stuck-destroy`).

Hai chế độ lỗi chỉ dành cho môi trường học/test, **không sử dụng trong production**. Thời gian được giới hạn để dễ quan sát; kết quả runtime có thể dao động do scheduler.

### 9.1. Cấu trúc project

```text
shutdown-diagnostics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/shutdowndiag/
    │   ├── ShutdownDiagnosticsApplication.java
    │   ├── DemoLifecycle.java
    │   └── DemoBlockingResource.java
    └── resources/
        └── application.properties
```

**`settings.gradle`:**

```groovy
rootProject.name = 'shutdown-diagnostics-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

**`src/main/resources/application.properties`:**

```properties
spring.application.name=shutdown-diagnostics-demo
spring.lifecycle.timeout-per-shutdown-phase=2s
logging.level.org.springframework.context.support.DefaultLifecycleProcessor=DEBUG
demo.mode=normal
demo.via-hook=false
```

`demo.mode` và `demo.via-hook` là **thuộc tính tự định nghĩa của ví dụ**, không phải Spring Boot built-in properties. `spring.lifecycle.timeout-per-shutdown-phase=2s` chỉ rút thời gian chờ trong phần dừng lifecycle để minh họa callback bị bỏ quên; nó **không** đặt giới hạn cho `@PreDestroy`.

### 9.2. DemoLifecycle: callback đầy đủ hoặc cố ý bị quên

**`src/main/java/com/example/shutdowndiag/DemoLifecycle.java`:**

```java
package com.example.shutdowndiag;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class DemoLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();
    private final String mode;

    public DemoLifecycle(@Value("${demo.mode:normal}") String mode) {
        this.mode = mode;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("LIFECYCLE: started phase=100");
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.getAndSet(false)) {
            callback.run();
            return;
        }

        System.out.println("LIFECYCLE: stop begin");

        if ("missing-callback".equals(mode)) {
            System.out.println("LIFECYCLE: callback intentionally missing");
            // SAI CỐ Ý: chỉ dùng trong demo để quan sát phase timeout.
            return;
        }

        System.out.println("LIFECYCLE: callback delivered");
        callback.run();
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

Trong `normal`, callback chạy sau công việc dừng giả lập, không có việc bất đồng bộ còn dở. Trong `missing-callback`, bean đánh dấu `running=false` nhưng **cố ý không gọi callback**. `DefaultLifecycleProcessor` sẽ chờ đến deadline của phase dù bean không còn running theo cờ. Đây là bằng chứng callback và cờ trạng thái **không thể thay thế nhau**.

`stop()` riêng có mặt để đáp ứng `Lifecycle` nhưng **Spring dùng `stop(Runnable)`** đối với `SmartLifecycle`. Ví dụ không dùng method `stop()` để xử lý cleanup nhằm làm đường callback dễ quan sát.

### 9.3. DemoBlockingResource: một worker không hợp tác và một destroy chờ lâu

**`src/main/java/com/example/shutdowndiag/DemoBlockingResource.java`:**

```java
package com.example.shutdowndiag;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class DemoBlockingResource {

    private final String mode;
    private ExecutorService executor;

    public DemoBlockingResource(
            @Value("${demo.mode:normal}") String mode) {
        this.mode = mode;
    }

    @PostConstruct
    void init() {
        if (!"stuck-task".equals(mode)) {
            return;
        }

        executor = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "demo-uncooperative-worker");
            thread.setDaemon(false);
            return thread;
        });

        executor.submit(() -> {
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(25);

            // SAI CỐ Ý: bỏ qua tín hiệu interruption trong demo.
            while (System.nanoTime() - deadline < 0) {
                LockSupport.parkNanos(
                        TimeUnit.MILLISECONDS.toNanos(200));
                Thread.interrupted(); // đọc và XÓA cờ interrupt
            }

            System.out.println("TASK: finite demo worker finally ended");
        });

        System.out.println("TASK: demo worker started");
    }

    @PreDestroy
    void destroy() {
        System.out.println("DESTROY: begin");

        if ("stuck-destroy".equals(mode)) {
            System.out.println("DESTROY: blocking for at most 12s");

            try {
                new CountDownLatch(1).await(
                        12, TimeUnit.SECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("DESTROY: interrupted");
            }
        }

        if (executor != null) {
            executor.shutdown();

            try {
                if (!executor.awaitTermination(
                        1, TimeUnit.SECONDS)) {
                    System.out.println(
                            "DESTROY: executor grace period expired");
                    executor.shutdownNow();

                    if (!executor.awaitTermination(
                            1, TimeUnit.SECONDS)) {
                        System.out.println(
                                "DESTROY: worker still alive!");
                    }
                }
            } catch (InterruptedException ex) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
                System.out.println(
                        "DESTROY: termination wait interrupted");
            }
        }

        System.out.println("DESTROY: end");
    }
}
```

**Vì sao đây chỉ là kịch bản lỗi mô phỏng?**

- `stuck-task` cố tình dùng `Thread.interrupted()` để xóa cờ interrupt, không xử lý dừng như code production. Worker vẫn tự kết thúc sau khoảng 25 giây theo đồng hồ đơn điệu, tránh vòng lặp vô hạn trong ví dụ.
- `ExecutorService.shutdown()` rồi `shutdownNow()` không thể buộc task đó kết thúc sớm, nên destroy có thể log `worker still alive!` và trả về.
- Vì worker là **non-daemon**, tiến trình chạy theo đường đóng context trực tiếp có thể còn sống **sau** `MAIN: context closed` cho đến khi thread tự kết thúc.
- `stuck-destroy` mô phỏng một callback hủy bean chờ quá lâu. Nó có giới hạn 12 giây nhờ `CountDownLatch.await(timeout, unit)` để không treo vĩnh viễn.
- Không nên sao chép `Thread.interrupted()` trong vòng lặp để “xử lý” interrupt ở ứng dụng thật; đó là chủ ý minh họa lỗi.

### 9.4. Lớp main: đóng context trực tiếp hoặc qua JVM shutdown hook

**`src/main/java/com/example/shutdowndiag/ShutdownDiagnosticsApplication.java`:**

```java
package com.example.shutdowndiag;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ShutdownDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShutdownDiagnosticsApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context =
                application.run(args);

        boolean viaHook = context.getEnvironment()
                .getProperty("demo.via-hook", Boolean.class, false);

        if (viaHook) {
            System.out.println("MAIN: System.exit invokes JVM shutdown");
            System.exit(0);
            return; // Không trở lại trong đường bình thường.
        }

        System.out.println("MAIN: closing context directly");
        context.close();
        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner printReadyMarker() {
        return arguments ->
                System.out.println("RUNNER: completed");
    }
}
```

Mặc định, code gọi `context.close()` **từ luồng main**. Khi `--demo.via-hook=true`, code thay bằng `System.exit(0)` để kích hoạt chuỗi JVM shutdown hook. Spring Boot 3.3 mặc định đăng ký hook để đóng context; tên thread trong dump/log có thể khác tùy phiên bản. Không cần thêm `Runtime.addShutdownHook(...)` thủ công.

**Đừng đưa lựa chọn `System.exit(0)` vào library hoặc service production tùy tiện.** Đây là nhánh thử nghiệm cố ý để quan sát **khác biệt giữa close context trực tiếp và đóng do JVM khởi động shutdown**.

### 9.5. Chạy chế độ bình thường

Nếu project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu tự viết files, cần tạo Gradle Wrapper bằng một Gradle tương thích hoặc khởi tạo project qua Spring Initializr; `build.gradle` không tự sinh `gradlew`/`gradlew.bat`.

Các dòng **do mã ví dụ tự in**, bỏ qua banner/log Spring Boot:

```text
LIFECYCLE: started phase=100
RUNNER: completed
MAIN: closing context directly
LIFECYCLE: stop begin
LIFECYCLE: callback delivered
DESTROY: begin
DESTROY: end
MAIN: context closed
```

Phần lớn trạng thái hiển thị theo đúng thứ tự vì context khởi động `SmartLifecycle` trước runner, dừng lifecycle trước destroy singleton và main chỉ in `context closed` khi `close()` đã trả về.

### 9.6. Tái hiện callback bị quên

```bash
./gradlew bootRun --args='--demo.mode=missing-callback'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.mode=missing-callback"
```

Những dòng đáng quan sát:

```text
LIFECYCLE: stop begin
LIFECYCLE: callback intentionally missing
... [khoảng chờ gần timeout phase 2s, có thể có log Spring] ...
DESTROY: begin
DESTROY: end
MAIN: context closed
```

**Dòng có dấu ba chấm chỉ là chú thích thời gian**, không phải stdout nguyên văn bắt buộc. Sự kiện xác định là callback không được gọi, và processor có thể chờ hết time budget của phase rồi tiếp tục đóng. Một cấu hình/phiên bản có thể log warning hoặc debug với nội dung khác nhau; không viết test phụ thuộc nguyên văn thông báo lỗi.

Để sửa, bỏ nhánh `missing-callback` và bảo đảm mọi đường kết thúc `stop(Runnable)` gọi callback sau cleanup. **Không sửa bằng cách đặt timeout bằng 0**: đó chỉ là che triệu chứng.

### 9.7. Tái hiện worker không kết thúc

```bash
./gradlew bootRun --args='--demo.mode=stuck-task'
```

Những dòng then chốt:

```text
TASK: demo worker started
...
MAIN: closing context directly
LIFECYCLE: stop begin
LIFECYCLE: callback delivered
DESTROY: begin
DESTROY: executor grace period expired
DESTROY: worker still alive!
DESTROY: end
MAIN: context closed
... [process có thể vẫn còn do non-daemon worker] ...
TASK: finite demo worker finally ended
```

Thứ tự `TASK: demo worker started` với mốc Spring tạo component khác có thể thay đổi; không ràng buộc nó là stdout duy nhất của ứng dụng. **Khác với thiếu callback**, ở đây lifecycle đã hoàn thành và context có thể đã đóng, nhưng worker vẫn chạy vì cố tình phớt lờ interruption.

Ngay sau log `worker still alive!`, thử `jcmd` từ terminal khác để thấy thread `demo-uncooperative-worker`. Nếu bạn thao tác quá chậm, task demo 25 giây có thể đã kết thúc; khởi chạy lại để quan sát. Không dùng `kill -9` cho tình huống bài tập khi task đã được giới hạn thời gian.

### 9.8. Tái hiện destroy callback chờ lâu

```bash
./gradlew bootRun --args='--demo.mode=stuck-destroy'
```

Bạn sẽ thấy:

```text
MAIN: closing context directly
LIFECYCLE: stop begin
LIFECYCLE: callback delivered
DESTROY: begin
DESTROY: blocking for at most 12s
... [chờ trong @PreDestroy, không phải chờ lifecycle callback] ...
DESTROY: end
MAIN: context closed
```

Trong lúc chờ, chụp thread dump. Luồng `main` có thể đang ở `CountDownLatch.await` bên trong `DemoBlockingResource.destroy()` qua Spring bean destruction. **Đổi `spring.lifecycle.timeout-per-shutdown-phase=1s` không rút ngắn 12 giây này**, vì nó xảy ra **sau khi phase stop đã hoàn thành**.

### 9.9. Quan sát JVM shutdown hook thật

Build JAR:

```bash
./gradlew bootJar
```

Sau đó khởi chạy phiên bản hook của chế độ destroy chờ lâu:

```bash
java -jar build/libs/shutdown-diagnostics-demo-0.0.1-SNAPSHOT.jar --demo.mode=stuck-destroy --demo.via-hook=true
```

Windows PowerShell:

```powershell
java -jar build/libs/shutdown-diagnostics-demo-0.0.1-SNAPSHOT.jar --demo.mode=stuck-destroy --demo.via-hook=true
```

Lần này main gọi `System.exit(0)`. Khi Spring shutdown hook thực hiện close context, callback `@PreDestroy` lại chờ khoảng 12 giây; có thể nhìn thấy stack của **shutdown-hook thread** trong `jcmd Thread.print` nếu attach kịp và VM còn nhận yêu cầu. Nếu không attach được trong JVM shutdown, dùng log/timeline đã gắn hoặc tái hiện qua `context.close()` để xác định callback nào đang block. Khả năng attach trong lúc VM thoát phụ thuộc JVM và môi trường.

**Quan trọng:** JVM chạy shutdown hooks đồng thời và chờ các hook kết thúc; một hook khác vẫn có thể đang chạy trong khi Spring hook bị kẹt. Đừng khẳng định thứ tự hook giữa Spring và thư viện thứ ba.

## 10. Viết stop(Runnable) đúng: callback sau khi thật sự dừng

Một mẫu cho resource có API bất đồng bộ trả `CompletionStage`:

```java
@Override
public void stop(Runnable callback) {
    if (!running.get()) {
        callback.run();
        return;
    }

    CompletionStage<Void> completion;

    try {
        completion = client.stopAsync();
    } catch (RuntimeException error) {
        recordFailure(error);
        finishStopUsingFallback();
        callback.run();
        return;
    }

    completion.whenComplete((ignored, error) -> {
        try {
            if (error != null) {
                recordFailure(error);
                finishStopUsingFallback();
            }
            running.set(false);
        } finally {
            callback.run();
        }
    });
}
```

Đây là **khung minh họa tích hợp, không phải lớp biên dịch độc lập**: `running`, `client`, `recordFailure` và `finishStopUsingFallback` là thành phần do dự án triển khai. Fallback phải có semantics thật và hạn chế thời gian; callback chỉ được phát sau khi bước stop/force-close đã đạt trạng thái kết thúc theo chính sách. Đừng dùng `finally` để tuyên bố đã dừng nếu fallback còn mắc kẹt hoặc chỉ gửi yêu cầu ngắt.

Đối với callback có thể đến qua nhiều nhánh hoặc nhiều stop calls đồng thời, cần state machine:

```text
RUNNING
   |
   | stop requested (một owner)
   v
STOPPING
   |
   +-- success -> STOPPED
   |
   +-- timeout/error -> FAILED_TO_STOP / FORCE_STOPPED
```

Nếu hai caller gọi `stop(Runnable)`, thiết kế nên chỉ có **một quá trình cleanup** nhưng bảo đảm **mỗi callback được Spring/caller cung cấp** đều được thông báo kết quả đúng một lần. Một `AtomicBoolean` chọn owner có ích, nhưng **không thay thế completion object** cho caller sau. Nếu bean không chạy, callback nên được gọi ngay.

### Test callback bằng CountDownLatch

```java
CountDownLatch completed = new CountDownLatch(1);
AtomicInteger calls = new AtomicInteger();

component.stop(() -> {
    calls.incrementAndGet();
    completed.countDown();
});

if (!completed.await(3, TimeUnit.SECONDS)) {
    throw new AssertionError("stop callback missing");
}

if (calls.get() != 1) {
    throw new AssertionError("callback count=" + calls.get());
}
```

Đây là **snippet kiểm thử tích hợp**: `component` là instance đã khởi động, cần import `CountDownLatch`, `AtomicInteger` và `TimeUnit`, method test cần xử lý `InterruptedException`. Một assertion duy nhất ngay khi latch mở chỉ đo count **tại thời điểm đó**; nếu nghi ngờ callback lặp muộn, cần test concurrency và quan sát toàn bộ trạng thái.

## 11. Viết executor shutdown có deadline

### 11.1. Một chính sách hai bước

Nếu bean **sở hữu** executor:

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        List<Runnable> notStarted = executor.shutdownNow();
        recordNotStarted(notStarted);

        if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
            reportUnconfirmedTermination();
        }
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
    reportInterruptedShutdown(ex);
}
```

Đây là **snippet tích hợp**, cần biến `executor` thuộc `ExecutorService` và các functions `recordNotStarted`, `reportUnconfirmedTermination`, `reportInterruptedShutdown`, cùng import. Các timeout `5s` và `2s` chỉ là ví dụ; cần chọn từ SLA và budget của tiến trình.

**Cần tách các kết quả:** `shutdownNow()` là *yêu cầu cưỡng bức*, `isTerminated()` mới là *đã xác nhận executor kết thúc*. Nếu task bỏ qua interrupt, dù hết 2 giây chờ thứ hai vẫn có thể còn thread. Đừng log “graceful complete” ở nhánh đó.

### 11.2. Tại sao chờ phải ở đúng thread?

Nếu `@PreDestroy` thực hiện `awaitTermination` đồng bộ thì nó chặn thread đóng context. Điều này có thể phù hợp nếu deadline nhỏ và work quan trọng. Nhưng nếu muốn phối hợp stop theo phase bằng `SmartLifecycle`, cần làm work bất đồng bộ và gọi callback sau khi hoàn tất, thay vì làm việc lâu **ngay trên luồng `LifecycleProcessor`** khiến processor khó theo dõi timeout.

Một implementation `stop(Runnable)` vẫn có thể làm một ít cleanup đồng bộ rất nhanh trước khi phát work async; nhưng việc gửi work phải có đường xử lý `RejectedExecutionException` nếu executor cleanup đã bị đóng.

### 11.3. Tại sao chỉ đặt pool-size không đủ?

Một executor có queue lớn có thể còn hàng trăm task khi stop; gọi `shutdown()` nghĩa là chờ tất cả task đã nhận, có thể vượt budget. Cần:

- Ngừng intake trước.
- Đếm `inFlight` và queue depth.
- Ưu tiên hoàn thành tác vụ thật sự quan trọng.
- Có deadline cho I/O và task.
- Quy định task nào được retry sau restart.
- Có chính sách với task chưa bắt đầu bị trả về bởi `shutdownNow()`.

**Lifecycle đúng không đồng nghĩa không mất message.** Nếu xử lý thông điệp với broker, ack/offset/transaction và idempotency phải có thiết kế riêng.

## 12. Bằng chứng nào là “shutdown xong”?

Đừng chỉ dựa vào log:

```text
shutdown requested
```

Hãy định nghĩa các dấu hiệu hoàn thành rõ hơn:

| Dấu hiệu | Có thể chứng minh | Không thể chứng minh |
|---|---|---|
| `ContextClosedEvent` đã phát | Context bắt đầu close | Bean destroy xong |
| `SmartLifecycle.stop(Runnable)` đã được gọi | Đã có yêu cầu stop bean | Resource đã dừng |
| Callback đã được gọi | Bean **đã báo** completion với processor | Chất lượng cleanup thực tế, nếu code gọi sai |
| `DefaultLifecycleProcessor` hết timeout | Đã dùng hết budget chờ phase | Bean đã hoàn tất |
| `ExecutorService.isShutdown()` | Đã gửi yêu cầu đóng executor | Task đã kết thúc |
| `ExecutorService.isTerminated()` | Executor terminated | Mọi side effect nghiệp vụ đã commit |
| `@PreDestroy` đã return | Method hủy đã trả về | External service đã nhận flush/ack nếu method không kiểm chứng |
| `ApplicationContext.close()` đã return | Đường đóng context đồng bộ đã kết thúc | JVM không còn non-daemon threads |
| JVM process biến mất | OS không còn process đó | Không mất dữ liệu hoặc không xử lý trùng sau restart |

Một shutdown điều hành tốt nên có các trạng thái **GRACEFUL_TERMINATED**, **FORCED_TERMINATED**, **TIMED_OUT_UNCONFIRMED**, **INTERRUPTED**, **FAILED** tùy chuẩn của hệ thống. Đây là các tên minh họa của ứng dụng, **không phải enum mặc định của Spring Boot**.

## 13. Chẩn đoán từ log đến code: quy trình điều tra có thể áp dụng

### Bước 1 — Phân biệt đường dừng

Hỏi: người vận hành dùng `SIGTERM`, `System.exit()`, `context.close()`, IDE Stop hay `kill -9`? Thời gian chờ và khả năng chạy hook **khác nhau**.

Nếu hệ thống dùng Kubernetes, còn phải biết container termination grace period, preStop hooks, readiness và điều kiện nhận traffic. Một IDE có thể gửi stop theo cách khác signal ở server.

### Bước 2 — Đánh dấu mốc bằng log nhỏ, an toàn

Thêm log ở bốn vị trí:

- Bắt đầu/kết thúc `stop(Runnable)`.
- Trước/sau `callback.run()`.
- Bắt đầu/kết thúc `@PreDestroy`/destroy method.
- Trước/sau `ApplicationContext.close()` nếu ứng dụng sở hữu lời gọi này.

Đừng thay đổi logic shutdown quá nhiều ngay trước khi điều tra; log có thể làm race thay đổi. Nếu có tracing/metrics sẵn, dùng dữ liệu đó trước.

### Bước 3 — Lấy 2–3 thread dumps khi còn sống

So sánh tên thread, state, stack và locks. Nếu thread đứng ở cùng `Future.get()` trong nhiều mẫu, tìm future nào chưa complete; nếu ở `ThreadPoolExecutor.awaitTermination()`, tìm worker nào không kết thúc. Nếu `DefaultLifecycleProcessor` đang chờ phase, tìm callback chưa đến.

### Bước 4 — So sánh với ngân sách chờ

Lập bảng:

```text
SIGTERM grace budget:                 30s (ví dụ)
SmartLifecycle phase consumer:         8s
SmartLifecycle phase web server:       8s
Destroy executor/database:             6s
Khoảng dự phòng:                       8s
```

Các số trên **chỉ minh họa**, không phải mặc định Spring Boot. Nhiều phase có thể cộng dồn; `@PreDestroy` và I/O ngoài lifecycle cần budget riêng. Nếu tổng kịch bản xấu vượt grace period, hệ điều hành có thể cưỡng bức kết thúc trước khi cleanup xong.

### Bước 5 — Tái hiện bằng một mode nhỏ trước khi sửa

Phân loại theo demo:

- `missing-callback`: log stop xuất hiện nhưng callback mất, thời gian chờ gần timeout phase.
- `stuck-task`: context close xong, non-daemon task còn sống.
- `stuck-destroy`: close bị chặn trong destroy method lâu hơn timeout phase.
- `via-hook=true`: cùng vấn đề destroy nhưng chạy trong JVM shutdown hook thay vì caller main.

Không dùng lại đoạn lỗi trong sản phẩm sau khi tái hiện thành công.

### Bước 6 — Sửa tại đúng layer

- **Callback thiếu:** sửa `stop(Runnable)`; bảo đảm callback trên mọi nhánh completion.
- **Task không dừng:** sửa vòng lặp, interruption, I/O timeout và ownership của executor.
- **Destroy bị chặn:** thêm deadline/cancel/force-close ở resource, sửa lock/Future dependency.
- **Hook chờ lẫn nhau:** giảm số JVM hooks, dùng lifecycle phase/owner trong Spring.
- **Grace budget ngắn:** đo và phân bổ thời gian phù hợp, nhưng không chỉ tăng timeout để giấu lỗi.

### Bước 7 — Xác minh lại bằng kịch bản thất bại

Một fix shutdown tốt nên chịu được: close gọi hai lần, đang dừng thì nhận job mới, worker bị interrupt, task I/O timeout, một bean stop bị lỗi, SIGTERM khi có in-flight tasks, và thời gian chờ không vượt budget có thể kiểm soát.

## 14. Vì sao phase timeout không sửa được hook bị kẹt?

`spring.lifecycle.timeout-per-shutdown-phase` hữu ích khi `DefaultLifecycleProcessor` đang chờ **các callback trong một phase**. Nhưng:

- Một `@PreDestroy` tự gọi `Thread.sleep(60000)` không nằm dưới đồng hồ chờ callback phase theo cách đó.
- Một `DisposableBean.destroy()` chờ socket không có timeout có thể block lâu dù mọi SmartLifecycle bean đã stop đúng.
- Một JVM shutdown hook không thuộc Spring context có thể bị kẹt độc lập với cấu hình Spring.
- Một non-daemon worker chưa terminate có thể giữ process sống sau khi đóng context trực tiếp.
- Một task không hợp tác với interrupt không tự chết khi phase timeout.

Tăng `timeout-per-shutdown-phase` chỉ thay đổi thời gian Spring **sẵn sàng chờ** những callback liên quan. Nó không phải lệnh hủy thread. Khi xác định nguyên nhân bằng thread dump, phải sửa **đúng operation đang chặn**.

## 15. Tránh deadlock trong shutdown

Các quy tắc review thường giúp loại nhiều lỗi:

1. Không chờ future trong lúc giữ lock mà future cần.
2. Không đóng executor từ chính task trong executor rồi đợi executor terminate.
3. Không gọi lại `System.exit` từ shutdown hook.
4. Không dựa vào thứ tự đăng ký JVM hooks.
5. Không đóng dependency (writer/database) trước khi consumer còn cần flush.
6. Không dùng executor đã shutdown để submit cleanup task cho chính executor ấy.
7. Không để exception khiến callback bị quên.
8. Không gọi callback ngay khi gửi yêu cầu dừng nếu resource còn hoạt động.
9. Không giữ `synchronized` lock khi gọi network I/O hoặc code tùy biến có thể re-enter vào cùng monitor.
10. Không coi `@Async`, `@Scheduled` hay `@PreDestroy` là một cơ chế tự động “đợi mọi việc xong”.

Một thiết kế tốt phải tránh vòng chờ không tiến triển. Nếu shutdown cần hoàn thành công việc của worker, **chính worker phải có đường nhận stop signal và thoát khỏi blocking calls**.

## 16. Checklist quan sát và telemetry

Một dashboard/log tối thiểu cho quy trình dừng có thể có:

- `shutdown_requested_timestamp`.
- `application_context_close_started` và `completed`.
- `lifecycle_stop_started{bean,phase}`.
- `lifecycle_callback_seen{bean,phase}`.
- `lifecycle_phase_timeout{phase}`.
- `executor_active_threads`, `executor_queue_size`, `executor_unfinished_tasks`.
- `executor_shutdown_requested` và `executor_terminated`.
- `destroy_started{bean}`, `destroy_completed{bean}`.
- `shutdown_duration_ms`.
- `shutdown_outcome` với giá trị graceful, forced, timeout hoặc unconfirmed.

Đây là **tên telemetry đề xuất**, không phải các metric tự có đầy đủ trong Spring Boot. Khi có Actuator/Micrometer, bạn vẫn phải tạo những measurement tùy biến cho worker của mình.

Tránh một series metric có label **job ID hoặc user ID không giới hạn cardinality**. Nếu cần chẩn đoán một job cụ thể, ưu tiên structured logs/traces có kiểm soát; không tăng vô hạn lượng time series.

## 17. Những kết luận sai thường gặp

| Kết luận vội | Vì sao không đúng? | Cách kiểm chứng |
|---|---|---|
| “Đã thấy ContextClosedEvent nên shutdown xong.” | Event xảy ra trước lifecycle stop/destroy | Log completion thật |
| “Không có deadlock report nên code không bị kẹt.” | Future wait/IO/starvation không nhất thiết được detector nhận diện | Đọc thread stack và queue |
| “Thread TIMED_WAITING chắc chắn là deadlock.” | Có thể là idle wait hoặc deadline hợp lệ | So sánh nhiều dump và timeline |
| “Gọi shutdownNow() thì task phải chết.” | Interruption là cooperative | Kiểm tra isTerminated và code task |
| “isShutdown=true nên mọi task đã xong.” | isShutdown chỉ xác nhận request | Kiểm tra isTerminated |
| “SmartLifecycle đã đặt running=false, không cần callback.” | Processor đợi callback | Gọi callback sau stop |
| “Đặt timeout 2s cho Spring thì @PreDestroy chỉ chạy 2s.” | Phase timeout không quản lý destroy callback | Deadline cấp resource |
| “Process vẫn sống nghĩa là context chưa close.” | Non-daemon worker có thể sống tiếp | Phân biệt close-complete với process-exit |
| “Tăng grace period là fix.” | Có thể chỉ giấu lỗi chờ vô hạn | Chứng minh bounded cleanup |
| “Hook chạy sau hook đăng ký trước.” | JVM hook order không được bảo đảm | Dùng lifecycle/dependency quản lý thứ tự |
| “Callback đến nghĩa là mọi dữ liệu đã commit.” | Callback có thể bị gọi quá sớm hoặc code sai | Kiểm chứng flush/ack/termination |
| “Hook bị kẹt phải kill -9 ngay.” | Có thể mất cơ hội lấy thread dump và recovery | Capture evidence, theo runbook an toàn |
| “JFR chụp sau khi process chết vẫn thấy nguyên nhân.” | Recording phải có dữ liệu trước khi chết | Ghi sớm, dump khi còn sống |

## 18. Bài thực hành từng bước

Thực hiện trong môi trường thử nghiệm, dùng dự án phần 9. Mỗi bài chỉ thay một yếu tố để dễ xác định nguyên nhân.

**Bài A — baseline sạch.** Chạy `./gradlew bootRun`. Ghi các mốc lifecycle stop, callback, destroy và context close. Xác nhận không có task tồn đọng.

**Bài B — thiếu callback.** Chạy `--demo.mode=missing-callback`. Đo thời gian từ `LIFECYCLE: stop begin` đến `DESTROY: begin`. Thay timeout phase từ 2s lên 4s và quan sát thời gian chờ thay đổi; sau đó khôi phục.

**Bài C — bỏ quên callback ở nhánh lỗi.** Trong một class `SmartLifecycle` thử nghiệm, làm cleanup ném exception trước callback. Dùng unit test `CountDownLatch` để xác định callback không đến. Thiết kế đường xử lý lỗi/force-close rồi mới báo completion.

**Bài D — callback đến sớm.** Gửi yêu cầu `executor.shutdown()` rồi gọi callback ngay, nhưng task còn chạy. Thêm một bean phase thấp hơn làm writer và quan sát rủi ro writer bị stop trước khi task flush. Chỉ làm trong môi trường thử nghiệm không có dữ liệu thật.

**Bài E — task không dừng.** Chạy `--demo.mode=stuck-task`; chụp thread dump khi `demo-uncooperative-worker` còn sống. Giải thích vì sao `Context.close()` đã hoàn thành mà process vẫn còn chờ non-daemon worker tự kết thúc.

**Bài F — sửa task để tôn trọng interrupt.** Thay vòng lặp dùng `Thread.interrupted()` xóa cờ bằng một loop theo cờ dừng/`isInterrupted()` hợp lệ, kết hợp xử lý interruption và cleanup. Kiểm tra `shutdownNow()` làm task kết thúc trước deadline test.

**Bài G — destroy bị block.** Chạy `--demo.mode=stuck-destroy`, chụp dump khi đang ở `CountDownLatch.await`. Đổi `spring.lifecycle.timeout-per-shutdown-phase` và chứng minh timeout này **không** áp đặt giới hạn cho destroy method.

**Bài H — shutdown hook.** Chạy JAR với `--demo.mode=stuck-destroy --demo.via-hook=true`. Quan sát phương thức destroy được gọi từ đường JVM shutdown. So sánh stack với trường hợp `context.close()` từ main.

**Bài I — Future/get deadlock.** Tạo một test nhỏ với executor một worker: task A submit B vào cùng executor rồi chờ B. Quan sát dump cho thấy `Future.get` đang chặn một worker duy nhất; sau đó sửa bằng cách không chờ vòng hoặc tăng khả năng thực thi theo một thiết kế không tự chặn.

**Bài J — shutdown budget.** Xác định thời hạn SIGTERM ở môi trường thử nghiệm, liệt kê timeout cho lifecycle phases, destroy, network và executor. Thiết kế deadline đủ ngắn để còn dự phòng trước khi JVM bị kết thúc cưỡng bức.

**Bài K — test idempotency.** Gọi shutdown hai lần gần đồng thời và kiểm tra cleanup chỉ thực hiện một lần; các caller về sau vẫn biết đã dừng hay chưa. Không lấy một cờ `closing=true` làm bằng chứng completion.

**Bài L — kịch bản production.** Viết runbook xử lý lần deploy kẹt: PID, pod/container, signal đã gửi, log thời gian, 2–3 thread dumps, phase/bean đang chờ, owner của executor, số in-flight jobs, giải pháp tạm thời và fix code lâu dài.

### Câu hỏi tự kiểm tra

1. Vì sao nhận được `ContextClosedEvent` không chứng minh shutdown đã xong?
2. `DefaultLifecycleProcessor` chờ tín hiệu gì khi gọi `SmartLifecycle.stop(Runnable)`?
3. Nếu thiếu callback, timeout phase giúp điều gì? Nó có giết resource bị kẹt không?
4. Nếu `@PreDestroy` chờ vô hạn, việc giảm `spring.lifecycle.timeout-per-shutdown-phase` có chữa được không?
5. Vì sao `shutdownNow()` không thể bảo đảm một task tùy ý kết thúc?
6. Khác nhau giữa `isShutdown()` và `isTerminated()` là gì?
7. Khi process còn sống sau `context.close()`, phải kiểm tra loại thread nào?
8. Trong thread dump, `WAITING` và `BLOCKED` có đủ để khẳng định deadlock không?
9. Vì sao đăng ký hai JVM shutdown hooks có thứ tự trước/sau không được đảm bảo?
10. Khi nào nên dùng `jcmd Thread.print -l` thay vì chỉ tăng log level?
11. Có thể chờ `Future.get()` trong lúc giữ lock mà task cần để hoàn tất không?
12. Làm sao xác định một quy trình stop có deadline và không làm mất dữ liệu ngoài ý muốn?

## 19. Tóm tắt ra quyết định

| Bạn đang thấy gì? | Việc kiểm tra tiếp theo |
|---|---|
| Chờ gần đúng timeout shutdown phase | Tìm `SmartLifecycle.stop(Runnable)` thiếu callback hoặc cleanup quá chậm |
| Đã đóng context mà JVM vẫn sống | Thread dump: non-daemon threads, executor và vòng lặp không thoát |
| Có `@PreDestroy begin` rồi đứng yên | Dump thread destroy; lock, Future, I/O timeout cấp resource |
| Hook thread giữ lock và worker bị BLOCKED | Tìm vòng chờ; sửa lock ordering, thả lock trước await |
| Gọi `shutdownNow()` mà worker không dừng | Kiểm tra interrupt handling và I/O cancellation |
| JVM bị cưỡng bức trước khi cleanup | So sánh các budget với grace period, chuẩn bị recovery |
| Callback được gọi nhưng flush chưa xong | Chuyển callback đến sau completion thực, kiểm tra dependency phases |

**Kết luận:** chẩn đoán shutdown bắt đầu từ việc xác định đang chờ **JVM shutdown hook**, **Spring lifecycle callback**, **destroy method**, hay **một worker còn sống**. Sau đó dùng timeline và thread dumps để tìm đúng điểm chặn. `SmartLifecycle.stop(Runnable)` cần callback sau khi dừng; `ExecutorService` cần termination thật; `@PreDestroy` cần thời hạn riêng; và JVM hooks không được giả định chạy tuần tự. Timeout là giới hạn đợi, **không phải bằng chứng việc dừng hoặc ghi dữ liệu đã thành công**.

## 20. Tài liệu chính thức

- Spring Boot 3.3 — `SpringApplication`: đăng ký shutdown hook và các mốc lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Graceful Shutdown và `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — `SpringApplication.setRegisterShutdownHook` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `SmartLifecycle` Javadoc và yêu cầu callback: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` và timeout phase mặc định: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Java SE 17 — `Runtime.addShutdownHook`, thứ tự JVM shutdown hooks: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Java SE 17 — `ExecutorService`: `shutdown`, `shutdownNow`, `awaitTermination`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — Công cụ chẩn đoán `jcmd`, `jstack` và thread dump: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Java SE 17 — Troubleshoot Process Hangs and Loops: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-process-hangs-and-loops.html