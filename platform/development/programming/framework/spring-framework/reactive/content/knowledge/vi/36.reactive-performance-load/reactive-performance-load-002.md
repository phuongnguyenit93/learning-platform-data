# Nhận diện lệnh chặn nằm sâu trong thư viện phụ thuộc của Spring WebFlux

## 1. Vấn đề: code reactive vẫn có thể gọi blocking

Một controller có thể trả §Mono§, service dùng các Reactor operator và repository dùng reactive API, nhưng dependency nằm sâu bên dưới vẫn có thể thực hiện I/O đồng bộ.

~~~java
@GetMapping("/prices/{sku}")
public Mono<PriceView> price(@PathVariable String sku) {
    return pricingService.find(sku);
}
~~~

Service có thể trông reactive:

~~~java
public Mono<PriceView> find(String sku) {
    return Mono.fromCallable(() -> vendorSdk.fetch(sku))
        .map(PriceView::from);
}
~~~

Nhìn vào chữ §Mono§ chưa đủ để kết luận hệ thống non-blocking. Nếu §vendorSdk.fetch§ gọi sâu xuống JDBC, §SocketInputStream.read§, §Thread.sleep§, §Future.get§ hoặc một hàm chờ đồng bộ, thread đang chạy pipeline vẫn bị giữ cho tới khi lời gọi đó trả về.

~~~text
WebFlux Controller
      |
      v
PricingService.find()
      |
      v
VendorPricingSdk.fetch()
      |
      v
VendorHttpFacade.read()
      |
      v
LegacyTransport.execute()
      |
      v
SocketInputStream.read()  <-- blocking call
~~~

Blocking nằm ở lớp cuối cùng dù controller và service không chứa lời gọi blocking trực tiếp. Vì thế, kiểm tra riêng source code của ứng dụng là chưa đủ; cần xem cả dependency tree, stack trace và hành vi runtime.

Mục tiêu bài học là nhận diện call blocking sâu trong thư viện, xác định đường gọi, tái hiện bằng test, rồi chọn cách sửa phù hợp với mô hình concurrency của WebFlux.

## 2. Vì sao phải tìm blocking ở cả dependency?

Với Reactor Netty, một nhóm event-loop thread nhỏ xử lý nhiều kết nối. Mỗi thread luân phiên xử lý request, callback và response:

~~~text
reactor-http-nio-1
   |-- request A: đọc header
   |-- request B: xử lý callback
   |-- request C: ghi response
   |-- request A: callback DB hoàn tất
   |-- request D: đọc body
~~~

Nếu request A gọi một SDK blocking và chờ 500 ms, event-loop thread không thể xử lý các công việc khác trong thời gian đó. Một vài lời gọi blocking có thể ảnh hưởng nhiều request không liên quan.

Dấu hiệu thường gặp khi tải tăng:

- P95/P99 latency tăng mạnh trong khi CPU chưa chắc đã cao.
- Timeout và retry tăng.
- Nhiều request cùng chậm dù chỉ một dependency có vấn đề.
- Thread dump cho thấy event-loop thread dừng trong cùng vendor method.
- Queue của event loop, scheduler hoặc connection pool tăng.
- Retry làm tăng tải lên dependency đang chậm và khiến sự cố lan rộng.

Reactive/non-blocking không mặc nhiên làm mọi request chạy nhanh hơn. Lợi ích chính là xử lý nhiều tác vụ I/O đồng thời bằng số thread tương đối nhỏ. Lợi ích đó suy giảm nếu event loop phải chờ I/O đồng bộ.

Tên thread là manh mối:

| Tên thread thường gặp | Vai trò |
| --- | --- |
| §reactor-http-nio-*§ | Event loop của Reactor Netty |
| §parallel-*§ | Scheduler non-blocking dành cho CPU-bound work |
| §boundedElastic-*§ | Worker pool có giới hạn dành cho blocking work |

Tên thread không đủ để kết luận; cần kiểm tra stack trace, thread marker và vị trí chuyển scheduler.

## 3. Những dạng blocking thường ẩn trong dependency

| Nhóm | API hoặc dấu hiệu | Rủi ro |
| --- | --- | --- |
| Thread sleep/chờ | §Thread.sleep§, §Object.wait§ | Giữ thread |
| Đồng bộ Future | §Future.get§, §CompletableFuture.join§ | Chờ tác vụ khác |
| Lock/coordination | §CountDownLatch.await§, §Semaphore.acquire§, §LockSupport.park§ | Chờ thread hoặc tín hiệu |
| File I/O | §FileInputStream.read§, §Files.readAllBytes§, §RandomAccessFile§ | Chờ filesystem |
| Network I/O | §Socket.connect/read§, §ServerSocket.accept§ | Chờ mạng đồng bộ |
| Database | JDBC §executeQuery§, §ResultSet.next§, JPA repository | Chờ database qua driver blocking |
| Process | §Process.waitFor§ | Chờ tiến trình bên ngoài |
| Logging | Synchronous file/socket appender | I/O log chặn event loop |
| Native/custom code | JNI hoặc hàm tự chờ | Có thể không được instrument |

Một dependency có thể gọi qua nhiều lớp:

~~~java
public Price fetch(String sku) {
    return client.getPrice(sku);
}

public Price getPrice(String sku) {
    return transport.readPrice(sku);
}

public Price readPrice(String sku) {
    return jdbcTemplate.queryForObject(
        "select price from prices where sku = ?",
        Price.class,
        sku
    );
}
~~~

Controller chỉ thấy §fetch§, nhưng blocking xảy ra ở JDBC. Stack trace của BlockHound hoặc thread dump giúp lần theo call chain.

### Phân biệt slow I/O, blocking và CPU-bound

- **Slow non-blocking I/O:** request downstream mất nhiều thời gian nhưng thread được giải phóng trong lúc chờ.
- **Blocking call:** thread đang chạy bị giữ cho tới khi lời gọi đồng bộ trả về.
- **CPU-bound work:** thread bận tính toán; không phải blocking I/O nhưng vẫn có thể làm nghẽn event loop.
- **Lock contention:** thread chờ lock; có thể gây nghẽn dù không gọi API I/O quen thuộc.

BlockHound chủ yếu phát hiện blocking API đã được instrument. Nó không thay thế profiler để tìm mọi CPU hotspot hoặc mọi dạng lock contention.

## 4. BlockHound hoạt động thế nào?

§BlockHound§ là Java agent của Project Reactor. Nó instrument một số phương thức blocking trong JVM và kiểm tra khi chúng chạy trên thread được đánh dấu chỉ dành cho non-blocking work.

Các Reactor thread như thread được tạo bởi §Schedulers.parallel()§ triển khai marker §NonBlocking§. Nếu một phương thức blocking đã được instrument chạy trên thread đó, BlockHound mặc định ném §BlockingOperationError§.

~~~java
BlockHound.install();

Mono.delay(Duration.ofMillis(10))
    .doOnNext(ignored -> {
        try {
            Thread.sleep(5);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    })
    .subscribeOn(Schedulers.parallel())
    .block();
~~~

Lời gọi §Thread.sleep§ ở đây diễn ra trên non-blocking thread. BlockHound có thể báo:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep

at java.base/java.lang.Thread.sleep(...)
at com.example.Demo.lambda$main$0(Demo.java:...)
~~~

Stack trace chỉ ra blocking API và frame gọi nó, giúp phát hiện cả những call nằm trong thư viện ngoài.

### Giới hạn cần hiểu

1. BlockHound tập trung vào các phương thức đã được instrument hoặc đánh dấu blocking.
2. Nó chỉ báo khi lời gọi đó chạy trên thread được nhận diện là non-blocking.
3. Một lời gọi blocking trên thread bình thường hoặc §boundedElastic§ có thể không bị báo.
4. Native code, custom spin loop, monitor contention hoặc cơ chế chờ riêng có thể không được nhận diện đầy đủ.
5. Một phương thức CPU-bound mất 300 ms không nhất thiết bị phát hiện.
6. Không có lỗi BlockHound không chứng minh toàn bộ dependency stack đều non-blocking.

Kết hợp BlockHound với source/bytecode inspection, thread dump, JFR, profiler và load test.

## 5. Cài BlockHound trong project Java 17

Tại thời điểm biên soạn, BlockHound có release §1.0.18.RELEASE§ trên Maven Central. Khi nâng cấp, kiểm tra release và yêu cầu tương ứng với JDK đang dùng.

Dependency test:

~~~xml
<dependency>
    <groupId>io.projectreactor.tools</groupId>
    <artifactId>blockhound</artifactId>
    <version>1.0.18.RELEASE</version>
    <scope>test</scope>
</dependency>
~~~

Cài đặt agent một lần, trước khi các test cần kiểm tra chạy:

~~~java
class BlockingDependencyTest {

    static {
        BlockHound.install();
    }

    // tests...
}
~~~

§BlockHound.install()§ tải các integration đã đăng ký qua ServiceLoader và thực hiện instrumentation. Đây là thao tác toàn cục; không cần cài lại cho mỗi test.

Có thể cài ở test listener hoặc test bootstrap để bảo đảm agent chạy trước các test khác. Nếu framework đã tự cài BlockHound, dùng SPI §BlockHoundIntegration§ để cấu hình bổ sung.

Luôn có một smoke test với blocking call quen thuộc trên §Schedulers.parallel()§ để xác nhận instrumentation thực sự hoạt động.

Nếu cài đặt thất bại do self-attach, Byte Buddy hoặc giới hạn JVM instrumentation, kiểm tra thông báo lỗi và hướng dẫn của phiên bản đang dùng. Có thể cấu hình agent qua §-javaagent§ trong JVM test/runtime. Một số cấu hình JDK 13+ có hướng dẫn thêm §-XX:+AllowRedefinitionToAddDeleteMethods§; chỉ thêm flag khi môi trường cụ thể báo cần, không copy mù quáng vào mọi JDK.

## 6. Đọc stack trace và tìm đúng dependency sâu

Giả sử BlockHound báo:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep

at java.lang.Thread.sleep(...)
at com.vendor.internal.RetryGate.waitBeforeRetry(RetryGate.java:84)
at com.vendor.http.LegacyTransport.execute(LegacyTransport.java:133)
at com.vendor.pricing.PricingClient.fetch(PricingClient.java:51)
at com.example.pricing.PricingService.lambda$find$0(PricingService.java:27)
~~~

Đọc từ trên xuống:

1. §Thread.sleep§ là API blocking thực tế.
2. §RetryGate.waitBeforeRetry§ là lớp nội bộ vendor đang chờ retry.
3. §LegacyTransport.execute§ là tầng transport gọi hàm chờ.
4. §PricingClient.fetch§ là API công khai mà ứng dụng gọi.
5. §PricingService.lambda...§ là điểm ứng dụng đưa dependency vào reactive pipeline.

Đừng chỉ sửa dòng service nếu vấn đề thật sự nằm trong SDK. Hãy đánh giá có phiên bản SDK non-blocking, API async thật hoặc cấu hình bỏ retry/sleep đồng bộ hay không.

### Khi không có source code dependency

1. Xác định artifact và version bằng §mvn dependency:tree -Dverbose§.
2. Xem dependency bắc cầu nào đưa SDK vào classpath.
3. Tìm source JAR nếu nhà cung cấp phát hành.
4. Dùng IDE decompiler để xem implementation.
5. Dùng §jar tf dependency.jar§ để tìm class liên quan.
6. Dùng §javap -c -p§ với classpath phù hợp để xem bytecode.
7. Đối chiếu stack trace với release notes và issue tracker của vendor.
8. Tạo test nhỏ chỉ gọi đúng method gây nghi ngờ để tái hiện.

Ví dụ:

~~~bash
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=com.vendor:pricing-sdk
~~~

Nếu chỉ thấy method bề mặt §fetch§, tiếp tục lần theo call stack hoặc bytecode để tìm nơi gọi Socket, JDBC, file API hoặc cơ chế chờ.

Tìm §Thread.sleep§ trong source ứng dụng không phát hiện được blocking nằm trong dependency JAR, generated code hoặc method được gọi gián tiếp. Kết quả tìm kiếm rỗng không chứng minh hệ thống sạch.

## 7. Kiểm thử blocking nằm sâu bằng StepVerifier

Một test tốt cần chạy dependency trên non-blocking thread và xác nhận lỗi xuất hiện trong Publisher:

~~~java
BlockHound.install();

Mono<String> result = Mono.fromCallable(
        () -> vendorClient.fetchPrice("BOOK-1")
    )
    .subscribeOn(Schedulers.parallel());

StepVerifier.create(result)
    .expectError(BlockingOperationError.class)
    .verify(Duration.ofSeconds(3));
~~~

§fromCallable§ bắt lỗi trong quá trình gọi hàm; lỗi BlockHound được truyền thành §onError§ của Mono. §StepVerifier§ xác nhận loại lỗi và có timeout để tránh test treo.

Không gọi thẳng method trên JUnit thread để kiểm tra:

~~~java
vendorClient.fetchPrice("BOOK-1");
~~~

JUnit thread thông thường không được đánh dấu §NonBlocking§, nên BlockHound có thể không báo dù lời gọi đó blocking. Test cần thực thi call trên một thread thuộc nhóm non-blocking.

Có thể xác nhận stack trace chứa class dependency:

~~~java
StepVerifier.create(result)
    .expectErrorSatisfies(error -> {
        assertInstanceOf(BlockingOperationError.class, error);

        boolean vendorFrameFound = Arrays.stream(error.getStackTrace())
            .anyMatch(frame ->
                frame.getClassName().contains("LegacyPricingSdk")
            );

        assertTrue(
            vendorFrameFound,
            "Stack trace should identify the dependency call path"
        );
    })
    .verify(Duration.ofSeconds(3));
~~~

## 8. Đưa blocking dependency ra khỏi event loop

Nếu chưa thay được thư viện đồng bộ, cô lập lời gọi trên §Schedulers.boundedElastic()§:

~~~java
Mono<String> price(String sku) {
    return Mono.fromCallable(() -> vendorClient.fetchPrice(sku))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

§boundedElastic§ được thiết kế cho tác vụ blocking có giới hạn tài nguyên. Nó không biến SDK thành reactive, nhưng giúp event loop không phải chờ lời gọi đồng bộ.

Controller vẫn có thể return Publisher:

~~~java
@GetMapping("/prices/{sku}")
public Mono<PriceView> price(@PathVariable String sku) {
    return pricingService.price(sku)
        .map(value -> new PriceView(sku, value));
}
~~~

### subscribeOn và publishOn

Với blocking source, dùng §subscribeOn§ để chuyển việc subscribe/đánh giá source sang scheduler khác:

~~~java
Mono.fromCallable(vendorClient::fetchPrice)
    .subscribeOn(Schedulers.boundedElastic());
~~~

§publishOn§ thay đổi scheduler cho các operator phía downstream kể từ vị trí đặt nó. Đặt §publishOn§ sau source callable không tự động chuyển lần gọi callable ban đầu:

~~~java
// Không phải cách cô lập source callable được khuyến nghị.
Mono.fromCallable(vendorClient::fetchPrice)
    .publishOn(Schedulers.boundedElastic());
~~~

Nếu blocking xảy ra trong operator downstream, §publishOn§ đặt trước operator đó có thể chuyển stage xử lý. Với lời gọi đồng bộ tại source, §subscribeOn§ thường rõ ràng hơn.

### Method trả Mono nhưng đã block trước khi trả về

Một method có thể trả Mono nhưng thực hiện blocking eager trong lúc được gọi:

~~~java
Mono<Price> fetch() {
    return vendorClient.fetchReactive();
}
~~~

Nếu §fetchReactive()§ chặn ngay lúc gọi rồi mới trả Mono, thêm §subscribeOn§ sau khi method đã được gọi có thể quá muộn.

Dùng §Mono.defer§ để trì hoãn cả lời gọi method tới lúc subscription:

~~~java
Mono<Price> fetch() {
    return Mono.defer(() -> vendorClient.fetchReactive())
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Nếu SDK thật sự non-blocking và chỉ thực hiện I/O khi Publisher được subscribe, không cần bọc nó vào boundedElastic. Nếu method đồng bộ hoặc chặn ngay khi được gọi, dùng §fromCallable§ hoặc §defer§ để lời gọi diễn ra trên scheduler phù hợp.

### boundedElastic không phải giải pháp cuối cùng

- Pool có giới hạn thread và queue; tải vượt mức vẫn có thể gây chờ.
- Nhiều request cùng gọi SDK chậm có thể làm queue và latency tăng.
- Timeout của Publisher không bảo đảm thư viện blocking ngắt được lệnh I/O bên dưới.
- Cancellation có thể không interrupt được lời gọi đồng bộ đang chạy.
- Nên giới hạn concurrency, đặt timeout ở client/driver và dùng bulkhead khi cần.
- Ưu tiên thay SDK bằng API reactive hoặc non-blocking chính thức nếu có.

## 9. Đánh dấu method custom và xử lý ngoại lệ

Một dependency có thể dùng JNI hoặc hàm native/custom để chờ, khiến BlockHound không nhận ra phương thức đó theo mặc định.

§BlockHound.Builder§ cho phép đánh dấu thêm method là blocking:

~~~java
BlockHound.install(builder -> builder
    .markAsBlocking(
        "com.vendor.nativebridge.LegacyTransport",
        "readPrice",
        "(Ljava/lang/String;)Ljava/lang/String;"
    )
);
~~~

Tham số cuối là method descriptor theo JVM notation. Trong ví dụ, method nhận một §String§ và trả một §String§.

Dùng cách này khi đã xác minh method thực sự chặn. Không đánh dấu một method chỉ vì tên chứa §read§ hoặc §fetch§; hãy xác minh implementation trước.

### Custom thread pool

Nếu ứng dụng dùng thread pool riêng và muốn BlockHound coi các thread đó là non-blocking, có thể tùy chỉnh predicate. Cần giữ nguyên predicate tích hợp sẵn:

~~~java
BlockHound.install(builder -> builder
    .nonBlockingThreadPredicate(current ->
        current.or(thread -> thread.getName().startsWith("my-event-loop-"))
    )
);
~~~

Không thay thế hoàn toàn predicate mặc định nếu chưa hiểu các integration khác. Đánh dấu sai thread pool có thể khiến blocking call vốn được phép chạy trên đó bị báo lỗi ngoài ý muốn.

### allowBlockingCallsInside

Có thể khai báo một method được phép chứa blocking call:

~~~java
BlockHound.install(builder -> builder
    .allowBlockingCallsInside(
        "com.vendor.logging.LegacyAppender",
        "append"
    )
);
~~~

Đây là ngoại lệ có phạm vi hẹp. Allow một method có thể cho phép cả blocking call nằm sâu bên dưới method đó. Nếu có method con cụ thể vẫn cần bị chặn, dùng §disallowBlockingCallsInside§ để ghi đè theo cách có chủ đích.

Không allow toàn bộ package vendor, mọi method §execute/read/write§ hoặc mọi thread. Allowlist không làm thư viện trở thành non-blocking.

## 10. False positive và logging

BlockHound có thể phát hiện blocking call trong thư viện mà nhóm không trực tiếp gọi. Đó không tự động là lỗi giả: nếu call xảy ra trên event loop, nó thực sự chặn thread.

Ví dụ logging:

~~~text
reactor-http-nio-2
  -> application log
  -> synchronous file appender
  -> file write
~~~

Nếu logger ghi file đồng bộ trên event loop, BlockHound có thể phát hiện. Cách sửa thường là dùng asynchronous appender hoặc chuyển logging I/O khỏi event loop, không phải tắt toàn bộ kiểm tra.

Nếu cần allow một method do thư viện bên thứ ba, ghi rõ lý do, phạm vi, version và test bảo đảm các đường call khác vẫn bị kiểm tra. Sau khi nâng cấp dependency, đánh giá lại ngoại lệ.

## 11. Reactor debugging bổ trợ cho BlockHound

Hai công cụ trả lời hai câu hỏi khác nhau:

- **BlockHound:** phương thức blocking nào chạy trên thread không được phép block?
- **Reactor debugging:** reactive operator được tạo ở đâu và lỗi đi qua những đoạn pipeline nào?

### checkpoint

~~~java
return pricingService.find(sku)
    .checkpoint("pricing-controller -> vendor-pricing");
~~~

Checkpoint có nhãn giúp xác định chuỗi liên quan khi lỗi Reactor xuất hiện. Nó không tự phát hiện blocking call.

### Global operator debug

~~~java
Hooks.onOperatorDebug();
~~~

Hook này thu thập assembly stack trace cho các operator được tạo sau khi hook bật. Tài liệu Reactor cảnh báo cách này tốn chi phí hơn vì phải capture stack trace trên nhiều operator; dùng có chọn lọc trong môi trường chẩn đoán.

### ReactorDebugAgent

§ReactorDebugAgent§ từ artifact §reactor-tools§ có thể instrument class để cung cấp assembly trace với chi phí phù hợp hơn global stacktrace capture. Khởi tạo trước khi ứng dụng tạo các reactive chain:

~~~java
public static void main(String[] args) {
    ReactorDebugAgent.init();
    SpringApplication.run(Application.class, args);
}
~~~

Đây là công cụ gỡ lỗi assembly, không phải bộ phát hiện blocking. Không thay thế BlockHound.

### log operator

~~~java
return pricingService.find(sku)
    .log("pricing-pipeline");
~~~

§log()§ quan sát subscribe, request, onNext, onError, onComplete và cancel tại vị trí operator. Nó hữu ích để thấy pipeline có subscribe/cancel đúng hay không, nhưng log tín hiệu không tự chứng minh thread không bị block.

Khi log trong production, cấu hình logging backend theo cách không chặn thread xử lý request.

## 12. Thread dump, JFR và profiler dưới tải

BlockHound tốt cho kiểm thử có chủ đích. Khi sự cố chỉ xuất hiện dưới tải production-like, kết hợp các công cụ runtime.

### Thread dump

~~~bash
jcmd <pid> Thread.print
~~~

Tìm các thread §reactor-http-nio-*§ và đọc stack. Nếu nhiều thread cùng dừng ở một method vendor, đó là tín hiệu mạnh cho thấy dependency đang chặn event loop.

Các frame thường đáng chú ý:

~~~text
java.lang.Thread.sleep
java.io.FileInputStream.read
java.net.SocketInputStream.socketRead0
java.util.concurrent.CountDownLatch.await
java.util.concurrent.FutureTask.get
java.util.concurrent.locks.LockSupport.park
com.vendor.internal.LegacyTransport.execute
~~~

Một frame đơn lẻ chưa đủ kết luận. Cần xem trạng thái thread, thời gian lặp lại, request latency và thread dump ở nhiều thời điểm.

### Java Flight Recorder

~~~bash
jcmd <pid> JFR.start name=webflux-blocking duration=60s filename=webflux-blocking.jfr
~~~

Sau đó mở file bằng Java Mission Control để xem thread activity, monitor contention, socket/file I/O và event liên quan. JFR không thay thế BlockHound, nhưng giúp phát hiện vấn đề chỉ xuất hiện khi chạy thật.

### Theo dõi chỉ số

Kết hợp:

- P50/P95/P99 latency theo endpoint.
- Request rate, active requests và timeout count.
- Event-loop pending tasks/queue nếu connector cung cấp metric.
- Scheduler queue và thread usage.
- BoundedElastic active/queued task count.
- Database connection pool active/pending/timeout.
- Downstream client latency và connection pool.
- CPU usage, allocation và GC pause.

Nếu CPU thấp nhưng latency cao, event-loop threads thường xuyên WAITING/TIMED_WAITING trong cùng dependency, ưu tiên điều tra blocking I/O hoặc lock contention. Nếu CPU cao và stack nằm trong vòng lặp tính toán, điều tra CPU-bound work thay vì chỉ dùng BlockHound.

## 13. Ví dụ hoàn chỉnh: Spring Boot 3.5, Java 17 và BlockHound

Project này mô phỏng SDK bên thứ ba có nhiều lớp gọi lồng nhau. Lớp cuối cùng dùng §Thread.sleep§ để biểu diễn thao tác đồng bộ. BlockHound bắt call sâu bên trong SDK khi chạy trên §Schedulers.parallel()§; adapter dùng boundedElastic sẽ hoàn tất.

### 13.1. Cấu trúc

~~~text
webflux-blocking-diagnostics/
├── pom.xml
└── src/
    ├── main/java/com/example/blocking/
    │   ├── BlockingDiagnosticsApplication.java
    │   ├── LegacyPricingSdk.java
    │   ├── PricingService.java
    │   └── PricingController.java
    └── test/java/com/example/blocking/
        └── BlockingDependencyTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-blocking-diagnostics</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor.tools</groupId>
            <artifactId>blockhound</artifactId>
            <version>1.0.18.RELEASE</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <argLine>-XX:+AllowRedefinitionToAddDeleteMethods</argLine>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

BlockHound chỉ nằm ở test scope. JVM flag trong Surefire là cấu hình tương thích instrumentation được BlockHound quick start ghi nhận cho một số JDK 13+; kiểm tra yêu cầu của đúng JDK và BlockHound release đang dùng. Nếu môi trường đã hỗ trợ self-attach/instrumentation mà không cần flag, có thể bỏ cấu hình sau khi xác minh test vẫn cài agent thành công.

### 13.3. BlockingDiagnosticsApplication.java

~~~java
package com.example.blocking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BlockingDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingDiagnosticsApplication.class, args);
    }
}
~~~

### 13.4. LegacyPricingSdk.java

~~~java
package com.example.blocking;

import org.springframework.stereotype.Component;

@Component
public class LegacyPricingSdk {

    public String fetchPrice(String sku) {
        return LegacyTransport.readPrice(sku);
    }

    private static class LegacyTransport {

        private static String readPrice(String sku) {
            try {
                Thread.sleep(25);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Legacy pricing call interrupted", ex
                );
            }

            return "42.00";
        }
    }
}
~~~

§fetchPrice§ chỉ là facade. Blocking thật nằm trong §LegacyTransport.readPrice§, mô phỏng tầng transport nội bộ của dependency.

Trong hệ thống thật, lớp sâu này có thể thuộc JAR của vendor, không có source code và chỉ xuất hiện trong stack trace hoặc bytecode decompile.

### 13.5. PricingService.java

~~~java
package com.example.blocking;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class PricingService {

    private final LegacyPricingSdk sdk;

    public PricingService(LegacyPricingSdk sdk) {
        this.sdk = sdk;
    }

    public Mono<String> findUnsafe(String sku) {
        return Mono.fromCallable(() -> sdk.fetchPrice(sku))
            .subscribeOn(Schedulers.parallel());
    }

    public Mono<String> findSafely(String sku) {
        return Mono.fromCallable(() -> sdk.fetchPrice(sku))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

§findUnsafe§ chỉ phục vụ bài kiểm thử phát hiện lỗi; không dùng cách này trong endpoint production. §findSafely§ thể hiện adapter tạm thời khi SDK đồng bộ chưa thể thay thế.

### 13.6. PricingController.java

~~~java
package com.example.blocking;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/prices")
public class PricingController {

    public record PriceView(String sku, String amount) {}

    private final PricingService service;

    public PricingController(PricingService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public Mono<PriceView> price(@PathVariable String sku) {
        return service.findSafely(sku)
            .map(amount -> new PriceView(sku, amount));
    }
}
~~~

### 13.7. BlockingDependencyTest.java

~~~java
package com.example.blocking;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Arrays;

import org.junit.jupiter.api.Test;

import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDependencyTest {

    static {
        BlockHound.install();
    }

    private final LegacyPricingSdk sdk = new LegacyPricingSdk();

    @Test
    void detectsBlockingCallDeepInsideDependency() {
        Mono<String> result = Mono.fromCallable(
                () -> sdk.fetchPrice("BOOK-1")
            )
            .subscribeOn(Schedulers.parallel());

        StepVerifier.create(result)
            .expectErrorSatisfies(error -> {
                assertInstanceOf(
                    BlockingOperationError.class,
                    error
                );

                boolean vendorFrameFound = Arrays.stream(error.getStackTrace())
                    .anyMatch(frame ->
                        frame.getClassName().contains("LegacyPricingSdk")
                    );

                assertTrue(
                    vendorFrameFound,
                    "Stack trace should identify the dependency call path"
                );
            })
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void blockingDependencyWorksWhenIsolatedOnBoundedElastic() {
        Mono<String> result = Mono.fromCallable(
                () -> sdk.fetchPrice("BOOK-1")
            )
            .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(result)
            .expectNext("42.00")
            .verifyComplete();
    }
}
~~~

Test đầu chạy SDK trên §Schedulers.parallel()§. BlockHound phát hiện §Thread.sleep§ ở lớp sâu và StepVerifier xác nhận stack trace chứa §LegacyPricingSdk§.

Test thứ hai chạy cùng SDK trên boundedElastic. BlockHound không báo vì đây là scheduler cho phép tác vụ blocking; Publisher trả §42.00§ rồi hoàn tất.

Hai test không chứng minh SDK đã trở thành non-blocking. Chúng chứng minh cách phát hiện vấn đề và cách cô lập call đồng bộ khỏi non-blocking thread.

### 13.8. Chạy project

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn test
~~~

Có hai test trong ví dụ. Khi BlockHound được cài thành công và môi trường JVM đáp ứng yêu cầu instrumentation, cả hai test pass; Maven kết thúc với §BUILD SUCCESS§.

Khởi động ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/prices/BOOK-1
~~~

Response dự kiến:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{"sku":"BOOK-1","amount":"42.00"}
~~~

Đây là demo dùng SDK giả lập để tái hiện blocking. Trong ứng dụng thật, thay §LegacyPricingSdk§ bằng dependency thực và thêm test ở đường gọi thực tế.

## 14. Khi dependency cung cấp API blocking và reactive song song

Một số thư viện có cả hai method:

~~~java
Price fetch(String sku);                 // synchronous
Mono<Price> fetchReactive(String sku);   // non-blocking
~~~

Nếu API reactive thực sự dùng non-blocking I/O, ưu tiên method đó:

~~~java
return vendorClient.fetchReactive(sku)
    .map(PriceView::from);
~~~

Không bọc reactive method trong boundedElastic chỉ vì nó là dependency ngoài. Hãy kiểm tra implementation, documentation và test để xác nhận không có blocking ở assembly/subscription.

Nếu SDK không có API reactive:

~~~java
return Mono.fromCallable(() -> vendorClient.fetch(sku))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Nếu SDK trả Mono nhưng method tạo Mono có thể block eager:

~~~java
return Mono.defer(() -> vendorClient.fetchReactive(sku))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Nếu dependency là JDBC/JPA, đổi tên method hoặc wrap trong Mono không biến nó thành reactive. Cân nhắc R2DBC/driver async chính thức nếu hệ thống cần non-blocking end-to-end.

## 15. Chiến lược rollout và bảo vệ hiệu năng

Đưa việc phát hiện blocking vào quy trình phát triển:

1. Thêm BlockHound vào một test profile có kiểm soát.
2. Viết test cho các adapter/service có dùng SDK, file, database hoặc thư viện legacy.
3. Cài BlockHound một lần trước khi test chạy.
4. Chạy các test trên Reactor non-blocking scheduler để làm lộ blocking call.
5. Kiểm tra stack trace và dependency version.
6. Thay bằng API non-blocking nếu có.
7. Nếu chưa thay được, cô lập call bằng boundedElastic.
8. Đặt timeout ở SDK/driver, giới hạn concurrency và theo dõi queue.
9. Load test endpoint sau khi sửa để xác nhận p95/p99 latency và throughput.
10. Theo dõi thread dump/JFR khi sự cố chỉ xuất hiện dưới tải.

Không bật mọi instrumentation/debug hook trên production mà không đánh giá overhead. BlockHound hữu ích trong test/diagnostic environment; Reactor assembly tracing, metrics và profiling có vai trò bổ sung.

### Một thay đổi được coi là hoàn tất khi nào?

- Test tái hiện lỗi cũ thực sự fail với BlockingOperationError.
- Adapter hoặc dependency mới không còn gọi blocking API trên non-blocking thread.
- Test hồi quy pass trên cùng đường code.
- Test có timeout, không phụ thuộc sleep ngẫu nhiên hoặc network bên ngoài.
- Load test không còn biểu hiện event-loop starvation.
- BoundedElastic không bị queue/thread saturation do dồn quá nhiều blocking task.
- Có log/metric để phát hiện tái phát sau nâng cấp dependency.

## 16. Những lỗi thường gặp

1. **Chỉ tìm từ khóa block trong controller:** blocking có thể nằm sâu trong JAR phụ thuộc.
2. **Thấy method trả Mono rồi kết luận non-blocking:** method có thể block trước khi trả Publisher hoặc khi subscribe.
3. **Gọi dependency trên JUnit thread rồi chờ BlockHound báo:** thread test thông thường không được đánh dấu non-blocking.
4. **Cài BlockHound sau khi test đã chạy scheduler:** agent phải được cài trước pipeline cần kiểm tra.
5. **Không có smoke test instrumentation:** test pass không chứng minh BlockHound thực sự hoạt động nếu agent không được cài.
6. **Chỉ nhìn tên thread:** phải xác minh stack trace và thread marker.
7. **Cho rằng BlockHound phát hiện mọi CPU hotspot:** nó tập trung vào blocking API đã instrument.
8. **Cho rằng không có lỗi nghĩa là không có blocking:** custom/native wait hoặc API chưa instrument có thể lọt.
9. **Dùng publishOn sau Mono.fromCallable để cô lập source:** callable có thể vẫn chạy trên thread subscribe ban đầu; dùng subscribeOn.
10. **Bọc một method trả Mono bằng subscribeOn nhưng bỏ qua eager blocking:** dùng defer nếu lời gọi method chặn trước khi trả Publisher.
11. **Chuyển toàn bộ pipeline sang boundedElastic:** làm mất lợi ích event-loop và có thể tạo queue/thread quá lớn.
12. **Dùng parallel cho blocking I/O:** scheduler này dành cho CPU-bound, non-blocking work.
13. **Allow cả package vendor:** che khuất nhiều call thực sự nguy hiểm.
14. **Tắt BlockHound vì logger bị báo:** xem xét async appender hoặc allowlist thật hẹp sau khi đánh giá.
15. **Chỉ sửa dependency version mà không có regression test:** lỗi có thể tái xuất khi nâng cấp tiếp.
16. **Retry vô hạn với SDK blocking:** tăng queue và thời gian chờ khi downstream đang quá tải.
17. **Tin timeout reactive luôn ngắt được I/O đồng bộ:** nhiều thư viện blocking không hỗ trợ interruption/cancellation.
18. **Chỉ chạy unit test, không load test:** chưa chứng minh event-loop không bị starvation khi có tải thực.
19. **Không xem dependency tree:** không biết JAR/version nào đưa thư viện legacy vào classpath.
20. **Nhầm Reactor checkpoint với BlockHound:** checkpoint truy vết assembly; BlockHound phát hiện blocking call.
21. **Dùng ThreadLocal hoặc log context để suy ra scheduler:** context propagation và thread identity là hai khái niệm khác nhau.
22. **Không kiểm tra custom thread pool:** BlockHound chỉ nhận diện thread theo predicate đã cấu hình.
23. **Bỏ qua monitor contention:** synchronized lock hoặc custom wait có thể cần thread dump/profiler bổ sung.
24. **Cho rằng boundedElastic làm dependency reactive:** nó chỉ cô lập blocking trên worker pool có giới hạn.

## 17. Checklist điều tra blocking trong dependency

- [ ] Có biết endpoint/service nào tăng latency dưới tải không?
- [ ] Có thread dump của thời điểm sự cố không?
- [ ] Event-loop threads có cùng stack trace hoặc cùng vendor method không?
- [ ] Dependency tree đã xác định artifact và version chưa?
- [ ] Có source JAR hoặc bytecode để kiểm tra method sâu không?
- [ ] Đã cài BlockHound trước khi chạy test chưa?
- [ ] Test có thực thi lời gọi trên non-blocking thread không?
- [ ] Stack trace có chỉ ra blocking API và class dependency không?
- [ ] Blocking call là known JDK API hay custom/native method?
- [ ] Có cần markAsBlocking cho method custom đã xác minh không?
- [ ] Có false positive do logging hoặc instrumentation không?
- [ ] Có thể chuyển sang API reactive chính thức không?
- [ ] Nếu phải dùng blocking, đã dùng fromCallable/defer + subscribeOn(boundedElastic) đúng vị trí chưa?
- [ ] Có giới hạn concurrency, timeout và bulkhead không?
- [ ] Có tránh retry vô hạn và queue không giới hạn không?
- [ ] Đã test cancellation và behavior khi SDK chậm chưa?
- [ ] Có JFR/profiler/metrics để kiểm tra ngoài BlockHound không?
- [ ] Load test sau thay đổi đã xác nhận latency và throughput chưa?

## 18. Câu hỏi tự kiểm tra

**1.** Vì sao WebFlux có thể bị chậm dù controller chỉ return Mono? Vì dependency sâu bên dưới có thể thực hiện blocking call trên event-loop.

**2.** BlockHound là gì? Java agent instrument blocking APIs và báo khi chúng được gọi trên thread được đánh dấu non-blocking.

**3.** BlockHound mặc định ném loại lỗi nào? BlockingOperationError.

**4.** Vì sao phải chạy test trên Schedulers.parallel()? Thread của scheduler này được đánh dấu non-blocking, giúp kiểm tra đúng điều kiện BlockHound.

**5.** BlockHound có phát hiện mọi CPU hotspot không? Không; dùng profiler/JFR để tìm CPU-bound work.

**6.** BlockHound có phát hiện mọi custom native wait không? Không nhất thiết; có thể đánh dấu method custom bằng markAsBlocking nếu đã xác minh.

**7.** Tại sao không block trực tiếp trên JUnit thread để kiểm tra? JUnit thread thông thường không phải non-blocking thread.

**8.** Khi cần bọc một method synchronous, nên dùng gì? Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()).

**9.** Nếu method trả Mono nhưng chặn ngay lúc được gọi, dùng gì? Mono.defer(() -> dependency.method()).subscribeOn(boundedElastic()) để trì hoãn lời gọi.

**10.** subscribeOn khác publishOn thế nào? subscribeOn chuyển quá trình subscribe/source; publishOn chuyển xử lý downstream sau vị trí đặt operator.

**11.** Có nên dùng Schedulers.parallel() cho JDBC blocking không? Không; parallel dành cho CPU-bound non-blocking work.

**12.** boundedElastic có biến JDBC thành non-blocking không? Không, chỉ chuyển blocking sang worker pool có giới hạn.

**13.** Tại sao cần đọc stack trace BlockHound? Để tìm chính xác blocking API, class và method sâu trong dependency.

**14.** Khi nào dùng markAsBlocking? Khi một method custom/native đã xác minh blocking nhưng chưa được BlockHound nhận diện.

**15.** allowBlockingCallsInside có rủi ro gì? Nó có thể cho phép cả các blocking call nằm sâu bên dưới method được allow.

**16.** Reactor checkpoint có thay BlockHound không? Không; checkpoint bổ sung thông tin assembly của reactive chain.

**17.** Khi nào dùng thread dump? Khi cần xem event-loop thread đang chờ ở đâu tại thời điểm hệ thống chậm.

**18.** JFR giúp gì? Quan sát thread activity, I/O, lock contention và runtime behavior dưới tải.

**19.** Không có BlockingOperationError có chứng minh không có blocking? Không; có thể call chưa được instrument hoặc không chạy trên thread non-blocking.

**20.** Cách xác nhận sửa lỗi hoàn tất? Regression test, stack trace sạch, boundedElastic không quá tải và load test xác nhận latency/throughput.

**Ghi nhớ:** Blocking có thể nằm sâu trong dependency dù controller và service đều dùng Mono/Flux. Dùng BlockHound để phát hiện blocking API trên non-blocking thread, đọc stack trace tới class/method thực tế, kiểm tra dependency tree và bytecode khi thiếu source. Ưu tiên API reactive thật; nếu phải giữ thư viện đồng bộ, cô lập lời gọi bằng fromCallable/defer và subscribeOn(boundedElastic), có timeout/concurrency limit. Kết hợp Reactor debugging, thread dump, JFR và load test vì BlockHound không phát hiện mọi dạng công việc chậm.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebFlux concurrency model và blocking APIs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html)
- [BlockHound — GitHub README và cách cài agent](https://github.com/reactor/BlockHound)
- [BlockHound — Quick Start](https://github.com/reactor/BlockHound/blob/master/docs/quick_start.md)
- [BlockHound — Customization: markAsBlocking, allow/disallow](https://github.com/reactor/BlockHound/blob/master/docs/customization.md)
- [Maven Central — BlockHound 1.0.18.RELEASE](https://central.sonatype.com/artifact/io.projectreactor.tools/blockhound)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).