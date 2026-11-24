# Phân biệt kết thúc Observation với đóng Scope

Trong Micrometer Observation, Observation và Scope có hai vòng đời khác nhau. Observation đại diện cho một hoạt động cần quan sát, chẳng hạn xử lý một request hoặc một use case. Scope đưa Observation đó thành ngữ cảnh hiện hành trong luồng thực thi để code bên trong có thể tìm thấy observation đang hoạt động và liên kết các hoạt động con.

Vì vậy, gọi Observation.stop() và gọi Scope.close() không thay thế cho nhau. stop() kết thúc hoạt động được quan sát và thông báo cho các ObservationHandler. close() kết thúc việc gắn observation vào execution context hiện tại, đồng thời khôi phục context trước đó. Một thao tác thường cần cả hai, theo đúng thứ tự.

## 1. Observation và Scope giải quyết hai vấn đề khác nhau

| Thành phần | Vai trò | Bắt đầu | Kết thúc |
| --- | --- | --- | --- |
| Observation | Vòng đời của một operation được quan sát; chứa tên, context, key-values và trạng thái lỗi | start() | stop() |
| Observation.Scope | Đưa Observation thành context hiện hành trong đoạn code đang chạy | openScope() | close() |

Observation là đối tượng đo lường. Nó có thể được xử lý bởi các handler để tạo Timer, cập nhật metrics hoặc tạo span tracing. Scope quản lý việc observation nào đang hiện hành trong execution context, thường dựa trên ThreadLocal ở imperative code.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Observation được tạo"] --> B["observation.start()"]
    B --> C["observation.openScope()"]
    C --> D["Code chạy trong context của Observation"]
    D --> E["scope.close()"]
    E --> F["Khôi phục context trước đó"]
    F --> G["observation.stop()"]
    G --> H["Handlers hoàn tất Observation"]
~~~

Scope có thể đóng trong khi Observation vẫn đang chạy. Điều này hữu ích khi một operation bất đồng bộ tạm rời execution thread hiện tại nhưng chưa hoàn tất. Ngược lại, một Observation có thể được start và stop mà không cần mở Scope nếu không cần đặt nó làm current observation cho code lồng bên trong.

## 2. Observation.start() và Observation.stop()

Observation quản lý vòng đời của một lần quan sát:

- start() đánh dấu operation bắt đầu và gọi các handler tương ứng.
- error(Throwable) ghi nhận lỗi của operation để handler có thể xử lý.
- stop() kết thúc operation và gọi giai đoạn hoàn tất của handler.

Các handler có thể dùng vòng đời này để ghi nhận thời lượng, số lần thực hiện, trạng thái lỗi hoặc span tracing. Với metrics, timer thường được hoàn tất ở giai đoạn stop. Với tracing, span được kết thúc khi Observation dừng.

Ví dụ tạo Observation:

~~~java
Observation observation = Observation.createNotStarted(
    "business.checkout",
    observationRegistry
);

observation
    .lowCardinalityKeyValue("channel", "web")
    .start();
~~~

Tên observation và low-cardinality key-values mô tả operation. Không dùng order ID, request ID hoặc dữ liệu định danh riêng làm low-cardinality tag. Nếu cần thêm dữ liệu chỉ dành cho tracing, hãy chọn high-cardinality key-value theo chính sách của hệ thống và backend.

Observation phải được stop khi operation kết thúc, kể cả khi có exception. Không để một Observation đã start bị bỏ quên vì timer hoặc span tương ứng có thể không được hoàn tất.

## 3. Scope.openScope() và Scope.close()

openScope() đưa Observation thành current observation trong execution context hiện tại. Các thành phần chạy bên trong scope có thể lấy ngữ cảnh hiện hành để tạo observation con, liên kết tracing hoặc đọc metadata.

close() kết thúc phạm vi context đó và khôi phục observation trước đó. Nếu đang có parent scope, đóng child scope sẽ khôi phục parent làm current observation.

Scope không kết thúc operation. Nó chỉ kết thúc việc kích hoạt context trong đoạn thực thi hiện tại.

Ví dụ:

~~~java
observation.start();

try (Observation.Scope scope = observation.openScope()) {
    // Các lời gọi bên trong có thể thấy observation hiện hành.
    checkoutService.execute(command);
}

observation.stop();
~~~

Try-with-resources bảo đảm scope được đóng khi code thoát bình thường hoặc ném exception. Sau khi scope đóng, observation vẫn chưa tự động stop; lệnh stop() vẫn cần được gọi.

## 4. Thứ tự đúng: đóng Scope trước, stop Observation sau

Trong một operation đồng bộ, thứ tự thường dùng là:

1. Tạo Observation.
2. Gọi start().
3. Mở Scope.
4. Thực hiện code thuộc operation.
5. Ghi nhận lỗi nếu có trong khi Scope còn mở.
6. Đóng Scope.
7. Gọi stop().

Ví dụ đầy đủ:

~~~java
public CheckoutResult checkout(CheckoutCommand command) {
    Observation observation = Observation.createNotStarted(
        "business.checkout",
        observationRegistry
    ).lowCardinalityKeyValue("channel", command.channel());

    observation.start();

    try (Observation.Scope scope = observation.openScope()) {
        try {
            return checkoutService.execute(command);
        } catch (RuntimeException error) {
            observation.error(error);
            throw error;
        }
    } finally {
        observation.stop();
    }
}
~~~

Khối catch bên trong chạy khi Scope vẫn đang mở, vì vậy error() được ghi nhận trong context của operation. Khi khối try-with-resources kết thúc, Java đóng Scope; sau đó finally gọi stop() để hoàn tất Observation.

Không dựa vào stop() để tự đóng Scope. Nếu Scope vẫn mở sau khi operation kết thúc, context hiện hành có thể tiếp tục trỏ đến một Observation đã stop và ảnh hưởng code chạy tiếp trên cùng thread.

## 5. Điều gì xảy ra nếu chỉ đóng Scope?

Ví dụ:

~~~java
observation.start();

try (Observation.Scope scope = observation.openScope()) {
    doWork();
}
// Quên observation.stop()
~~~

Scope đã được đóng, vì vậy context hiện hành được khôi phục. Tuy nhiên, Observation vẫn chưa hoàn tất. Các handler chờ sự kiện stop có thể không ghi nhận đầy đủ thời lượng hoặc không kết thúc span tracing.

Đây là lỗi rò rỉ vòng đời Observation. Nó có thể làm số lượng operation đang mở tăng lên, span không hoàn tất hoặc metrics không được cập nhật như mong đợi.

Hãy luôn có một nơi sở hữu việc stop(), thường là finally hoặc callback terminal của operation.

## 6. Điều gì xảy ra nếu chỉ stop Observation?

Ví dụ sai:

~~~java
observation.start();
Observation.Scope scope = observation.openScope();

try {
    doWork();
} finally {
    observation.stop();
    // Quên scope.close()
}
~~~

Observation đã được kết thúc nhưng Scope vẫn đang mở. Current context chưa được khôi phục. Những lời gọi tiếp theo trên thread có thể nhìn thấy context cũ, tạo quan hệ parent-child sai hoặc làm rò rỉ metadata của operation trước.

Cách sửa:

~~~java
observation.start();

try (Observation.Scope scope = observation.openScope()) {
    doWork();
} finally {
    observation.stop();
}
~~~

Scope đóng trước khi stop() được gọi. Hai thao tác có owner và mục đích riêng, nên cần bảo đảm cả hai đều được thực hiện.

## 7. Scope lồng nhau và thứ tự LIFO

Trong một request, có thể có Observation cha và nhiều Observation con. Khi mở scope lồng nhau, phải đóng theo thứ tự ngược với lúc mở: scope mở sau được đóng trước.

~~~java
Observation parent = Observation.createNotStarted(
    "business.checkout",
    observationRegistry
).start();

try (Observation.Scope parentScope = parent.openScope()) {
    Observation child = Observation.createNotStarted(
        "inventory.reserve",
        observationRegistry
    ).start();

    try (Observation.Scope childScope = child.openScope()) {
        inventoryService.reserve(command.items());
    } finally {
        child.stop();
    }
} finally {
    parent.stop();
}
~~~

Trình tự:

1. Parent start và mở parent scope.
2. Child start và mở child scope.
3. Child scope đóng, current context trở lại parent.
4. Child stop.
5. Parent scope đóng, current context trở về context trước parent.
6. Parent stop.

Đóng sai thứ tự có thể khôi phục nhầm context hoặc phá vỡ quan hệ lồng nhau. Hãy dùng try-with-resources cho từng Scope và không lưu scope để đóng ở một vị trí không rõ owner.

## 8. Có cần Scope cho mọi Observation không?

Không. Nếu chỉ cần đo một operation độc lập và không cần đặt nó làm current context cho code bên trong, có thể start rồi stop:

~~~java
Observation observation = Observation.createNotStarted(
    "batch.reconcile",
    observationRegistry
).start();

try {
    reconciler.run();
} catch (RuntimeException error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
~~~

Không mở Scope không có nghĩa Observation không hoạt động. Các handler vẫn nhận lifecycle start/error/stop. Scope chỉ cần khi muốn propagate hoặc truy cập current observation trong đoạn code đang chạy.

Ngược lại, chỉ mở Scope mà không có Observation đã được start không phải cách thay thế lifecycle. Hãy tạo và start Observation trước, sau đó mới mở Scope.

## 9. Scope và ObservationHandler

ObservationHandler nhận các callback ở các mốc lifecycle khác nhau. Các callback thường được quan tâm gồm:

| Callback | Ý nghĩa |
| --- | --- |
| onStart | Observation bắt đầu |
| onError | Observation ghi nhận lỗi |
| onScopeOpened | Scope của Observation được mở |
| onScopeClosed | Scope được đóng |
| onStop | Observation kết thúc |

onScopeOpened/onScopeClosed phản ánh việc context được kích hoạt và khôi phục. onStart/onStop phản ánh vòng đời của operation. Không đồng nhất hai cặp callback này.

Một handler có thể tạo span khi Observation bắt đầu và kết thúc span khi Observation stop. Scope có thể kích hoạt span đó thành current span trong code chạy bên trong. Khi Scope đóng, current span trước đó được khôi phục; span vẫn tồn tại cho đến khi Observation được stop.

Với metrics handler, thời lượng operation thường gắn với start/stop. Đóng Scope sớm không có nghĩa Timer đã hoàn tất. Với tracing handler, đóng Scope không có nghĩa span đã kết thúc.

## 10. Observation context và ThreadLocal

Trong imperative execution, Scope thường gắn current observation vào context theo thread. Điều này cho phép code lồng nhau tạo child observation mà không cần truyền parent thủ công qua mọi phương thức.

Ví dụ về quan hệ:

~~~text
Thread A
  parent Observation
    open parent Scope
      child Observation
        open child Scope
        close child Scope
      stop child
    close parent Scope
  stop parent
~~~

Scope phải được đóng trong đúng execution context nơi nó được mở. Với cơ chế ThreadLocal thông thường, không chuyển một đối tượng Scope sang thread khác để đóng. Làm vậy có thể khôi phục sai ThreadLocal của thread hiện tại và để lại context cũ trên thread đã mở scope.

Khi dùng executor, callback hoặc thread pool, không giả định current observation tự động đi theo tác vụ. Cần dùng cơ chế context propagation phù hợp với Micrometer và framework đang dùng, hoặc mở Scope mới trên thread đích khi tiếp tục cùng một Observation và đóng nó ngay trên thread đó.

## 11. Observation trong xử lý bất đồng bộ

Vòng đời Observation có thể dài hơn Scope trên thread gửi tác vụ. Ví dụ, một request gửi công việc bất đồng bộ rồi chờ future hoàn tất. Scope chỉ cần mở quanh đoạn code submit; Observation có thể tiếp tục chạy đến khi future kết thúc.

~~~java
public CompletableFuture<Report> generate(ReportCommand command) {
    Observation observation = Observation.createNotStarted(
        "business.report.generate",
        observationRegistry
    ).start();

    CompletableFuture<Report> future;
    try (Observation.Scope scope = observation.openScope()) {
        future = reportClient.generateAsync(command);
    } catch (RuntimeException error) {
        observation.error(error);
        observation.stop();
        throw error;
    }

    return future.whenComplete((report, error) -> {
        if (error != null) {
            observation.error(error);
        }
        observation.stop();
    });
}
~~~

Trong ví dụ:

- Observation start trước khi submit công việc.
- Scope được mở trên thread gọi và đóng ngay sau khi submit.
- Observation vẫn tồn tại trong lúc future đang chạy.
- Khi future hoàn tất, error được ghi nhận nếu có và Observation được stop.

Nếu callback hoàn tất cần current observation để tạo observation con hoặc ghi log/tracing context, có thể mở một Scope mới bên trong callback và đóng tại chính callback đó. Không giữ Scope của thread submit để đóng từ thread hoàn tất.

### Mở Scope trên thread callback

~~~java
return future.whenComplete((report, error) -> {
    try (Observation.Scope callbackScope = observation.openScope()) {
        if (error != null) {
            observation.error(error);
        }
        auditCompletion(report, error);
    } catch (RuntimeException callbackError) {
        observation.error(callbackError);
        throw callbackError;
    } finally {
        observation.stop();
    }
});
~~~

Scope callback được tạo và đóng trên cùng thread chạy callback. Sau khi scope đóng, finally stop Observation. Nếu callback chạy trên executor khác, context propagation và tính an toàn khi chia sẻ context của Observation phải được xem xét theo integration cụ thể.

## 12. Reactive pipeline và context propagation

Trong Reactor, execution có thể chuyển thread và không gắn cố định với một ThreadLocal. Việc mở Scope thủ công ở thread tạo publisher không bảo đảm observation context có mặt ở thread thực thi signal sau đó.

Với reactive pipeline:

- Dùng integration Observation/Reactor do framework cung cấp khi phù hợp.
- Bảo đảm context được truyền qua Reactor Context hoặc cơ chế Micrometer Context Propagation được cấu hình.
- Không giữ Scope imperative mở xuyên suốt thời gian publisher chưa hoàn tất.
- Để terminal signal hoàn tất Observation đúng một lần.
- Xử lý cancel và error như các đường kết thúc riêng.

Ví dụ minh họa nguyên tắc: Observation được tạo theo subscription, còn lifecycle được kết thúc ở terminal signal:

~~~java
return Mono.defer(() -> {
    Observation observation = Observation.createNotStarted(
        "business.search",
        observationRegistry
    ).start();

    return Mono.defer(() -> searchService.search(command))
        .doOnError(observation::error)
        .doFinally(signal -> observation.stop());
});
~~~

Mono.defer tạo Observation mới cho mỗi subscription. doFinally được gọi khi publisher hoàn tất, lỗi hoặc bị cancel. Ví dụ này chỉ minh họa vòng đời; nếu các operator bên trong cần current observation, phải cấu hình context propagation hoặc dùng Observation instrumentation dành cho Reactor thay vì giả định ThreadLocal tự đi theo signal.

## 13. Dùng Scope để tạo quan hệ parent-child

Khi parent scope đang mở, Observation con được tạo trong đoạn code đó có thể nhận biết context hiện hành và liên kết với parent thông qua observation convention/handler phù hợp.

~~~java
Observation parent = Observation.createNotStarted(
    "business.checkout",
    observationRegistry
).start();

try (Observation.Scope parentScope = parent.openScope()) {
    inventoryService.reserve(command.items());
    paymentService.authorize(command.payment());
} finally {
    parent.stop();
}
~~~

Nếu inventory hoặc payment service tạo Observation riêng, scope của parent cung cấp context hiện hành để tracing integration xây dựng quan hệ lồng nhau. Nếu parent scope bị đóng quá sớm, child observation được tạo sau đó có thể không còn nhìn thấy parent context.

Scope không thay thế việc truyền dữ liệu nghiệp vụ. Nó chỉ cung cấp observation context cho instrumentation. Các tham số như order ID, command hoặc transaction vẫn phải được truyền qua API nghiệp vụ theo thiết kế bình thường.

## 14. Lỗi lifecycle thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ close Scope mà quên stop Observation | Handler không nhận giai đoạn kết thúc; Timer/span có thể chưa hoàn tất | Gọi stop trong finally hoặc terminal callback |
| Chỉ stop Observation mà quên close Scope | Current context có thể bị rò rỉ trên thread | Dùng try-with-resources cho Scope |
| Gọi stop trước khi Scope đóng | Context của Observation đã stop vẫn có thể còn hiện hành trong đoạn code còn lại | Đóng Scope trước, stop sau |
| Đóng scope không theo LIFO | Khôi phục sai parent/current context | Đóng scope lồng nhau theo thứ tự ngược |
| Đóng Scope trên thread khác | Có thể làm hỏng context gắn với thread | Đóng trên thread mở scope hoặc tạo scope mới ở thread đích |
| Giữ Scope mở qua thời gian chờ async | Giữ context trên thread submit và gây nhiễm context thread pool | Đóng scope sau submit, giữ Observation đến terminal event |
| Mở Scope nhưng chưa start Observation | Lifecycle không đúng và handler không nhận start như mong đợi | Start trước rồi mới openScope |
| Gọi stop nhiều lần từ nhiều callback | Handler có thể nhận lifecycle kết thúc lặp hoặc phát sinh lỗi | Chọn một owner/terminal path duy nhất |
| Bắt lỗi sau khi đã stop | Handler không nhận được trạng thái lỗi trước khi hoàn tất | Gọi error trước stop |

## 15. Kiểm thử sự khác nhau giữa Scope và Observation

Có thể gắn một ObservationHandler thử nghiệm để ghi lại thứ tự callback. Ví dụ dưới đây tập trung vào sự kiện lifecycle:

~~~java
List<String> events = new ArrayList<>();

ObservationHandler<Observation.Context> handler =
    new ObservationHandler<>() {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            events.add("start");
        }

        @Override
        public void onScopeOpened(Observation.Context context) {
            events.add("scope-open");
        }

        @Override
        public void onScopeClosed(Observation.Context context) {
            events.add("scope-close");
        }

        @Override
        public void onStop(Observation.Context context) {
            events.add("stop");
        }
    };

ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig().observationHandler(handler);

Observation observation = Observation.createNotStarted(
    "demo.operation",
    registry
).start();

try (Observation.Scope scope = observation.openScope()) {
    // Thực hiện công việc.
}
observation.stop();
~~~

Với implementation handler tương ứng, thứ tự mong đợi là:

~~~text
start
scope-open
scope-close
stop
~~~

Kiểm thử nên bổ sung các tình huống:

- Không mở Scope nhưng vẫn start và stop Observation.
- Ném exception trong Scope, xác nhận error được ghi trước stop.
- Lồng parent/child và xác nhận scope-close theo LIFO.
- Scope được đóng khi callback async hoàn tất trên thread đích.
- Cancel reactive publisher và xác nhận Observation vẫn được stop.
- Không có callback terminal thứ hai làm stop lại cùng Observation.

Các callback Scope và callback Observation phải được kiểm tra riêng. Nếu chỉ assert rằng Timer đã được ghi, test chưa chứng minh Scope đã được đóng và current context đã được khôi phục.

## 16. Quy trình chọn lifecycle phù hợp

Khi instrument một operation:

1. Tạo Observation từ ObservationRegistry.
2. Gắn tên và key-values có cardinality phù hợp.
3. Gọi start() đúng một lần.
4. Chỉ mở Scope nếu code bên trong cần current observation hoặc context propagation.
5. Đóng mỗi Scope đúng một lần, trên đúng execution context và theo thứ tự LIFO.
6. Gọi error(Throwable) trước stop() khi operation thất bại.
7. Gọi stop() đúng một lần khi logical operation thực sự kết thúc.
8. Với async, không giữ Scope mở trên thread submit trong khi chờ; giữ Observation đến completion và mở scope riêng trên thread callback nếu cần.
9. Với Reactor, dựa vào Reactor Context/context propagation và terminal signal, không dựa vào ThreadLocal thuần.
10. Kiểm thử riêng lifecycle start/stop và scope open/close.

Observation.stop() kết thúc operation được quan sát và kích hoạt các handler hoàn tất. Scope.close() chỉ kết thúc việc gắn Observation vào execution context hiện hành và khôi phục context trước đó. Đóng Scope mà không stop sẽ để Observation chưa hoàn tất; stop mà không đóng Scope có thể làm rò rỉ context. Quản lý hai vòng đời riêng biệt, theo đúng thứ tự, giúp metrics, tracing và các observation lồng nhau phản ánh chính xác luồng thực thi.
