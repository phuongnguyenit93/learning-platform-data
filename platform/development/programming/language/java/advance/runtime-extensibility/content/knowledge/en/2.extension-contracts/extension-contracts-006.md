# Quy định quyền sở hữu tài nguyên, trạng thái và khả năng gọi đồng thời trong hợp đồng mở rộng Java

Trong kiến trúc mở rộng ở runtime (SPI, plugin, adapter, hook hoặc handler được nạp động), host gọi mã của extension nhưng hai bên có thể có vòng đời, luồng thực thi và tài nguyên khác nhau. Một interface chỉ khai báo phương thức là chưa đủ. Hợp đồng mở rộng phải trả lời rõ: **ai sở hữu tài nguyên**, **trạng thái tồn tại ở phạm vi nào**, và **host được gọi extension đồng thời theo cách nào**.

Mục tiêu của bài là thiết kế hợp đồng đủ cụ thể để host có thể khởi tạo, dùng lại, dừng, nạp lại và kiểm thử extension mà không làm rò rỉ tài nguyên, mất dữ liệu hoặc phát sinh race condition.

## 1. Phân biệt các chủ thể và phạm vi trách nhiệm

- **Host (runtime/container):** ứng dụng điều phối việc tìm provider, tạo instance, cung cấp ngữ cảnh thực thi, phân phối request, áp dụng giới hạn tải và quyết định khi nào bắt đầu/dừng extension.
- **Provider/extension:** phần triển khai được đăng ký hoặc nạp vào host; xử lý nghiệp vụ theo interface đã thống nhất và giải phóng những tài nguyên mà chính nó sở hữu.
- **Caller:** mã yêu cầu host sử dụng extension. Caller có thể nằm ngoài host hoặc là một thành phần nội bộ; caller không nhất thiết nắm vòng đời instance của provider.

Ví dụ: host dùng `ServiceLoader<Transformer>` để tìm một provider. `ServiceLoader` cung cấp cơ chế khám phá/khởi tạo provider; **nó không tự quy định provider có thread-safe hay không, không tự dừng tác vụ nền và không tự gọi `close()` cho provider**. Các trách nhiệm đó phải thuộc về hợp đồng giữa host và provider. Bản thân đối tượng `ServiceLoader` cũng không được thiết kế để nhiều luồng thao tác đồng thời một cách tùy ý; việc duyệt/nạp nên được host quản lý riêng với việc gọi các instance provider.

Một đặc tả tốt phải ghi rõ phạm vi áp dụng cho **mỗi instance** và cho **mỗi phiên hoạt động**. Đăng ký một provider một lần không đồng nghĩa chỉ có một instance: host có thể tạo một instance dùng chung, một instance cho từng tenant, hoặc một instance cho mỗi request.

## 2. Quy định quyền sở hữu tài nguyên

**Quyền sở hữu** là trách nhiệm quản lý vòng đời của tài nguyên: tạo/cấp phát, sử dụng hợp lệ, ngừng sử dụng, đóng và xử lý lỗi khi đóng. Quyền được *mượn sử dụng* không tự động trao quyền *đóng hoặc thay cấu hình*.

| Tài nguyên | Chủ sở hữu điển hình | Trách nhiệm cần ghi trong hợp đồng |
| --- | --- | --- |
| `ExecutorService`/scheduler do host truyền vào | Host | Extension chỉ gửi tác vụ theo quota; không `shutdown()` executor được mượn |
| Connection pool, client HTTP dùng chung, registry metrics, cấu hình host | Host hoặc thành phần quản lý chung | Extension không đóng, không thay trạng thái toàn cục nếu API không cấp quyền |
| File/socket/luồng nền/cache do chính provider mở và giữ | Provider | Provider đóng/hủy đúng lúc; hủy listener, job và tham chiếu khi unload |
| Buffer, parser hoặc object tạo cho một lần gọi | Bên tạo hoặc bên nhận nếu có chuyển quyền rõ ràng | Đóng trong phạm vi lời gọi hoặc chuyển quyền bằng tài liệu/API tường minh |
| `InputStream`/`Stream`/cursor trả ra từ API | Phải được hợp đồng chỉ đích danh | Ai đóng, khi nào đóng, có được đọc sau khi phương thức trả về hay không |
| ClassLoader chuyên biệt dùng để nạp plugin | Bên tạo/quản lý loader, thường là host | Chỉ đóng loader sau khi extension ngừng hoạt động và các tham chiếu liên quan được giải phóng |

### 2.1. Ba mô hình sở hữu phổ biến

**Host-owned, provider-borrowed:** host truyền `Executor`, `Clock`, cấu hình, logger hoặc client dùng chung cho provider. Provider có thể dùng trong thời hạn được cho phép; tuyệt đối không đóng tài nguyên đó. Nếu provider cần lưu tham chiếu để thực hiện bất đồng bộ, hợp đồng phải cho phép và giới hạn thời gian giữ tham chiếu.

**Provider-owned:** provider mở socket riêng, đăng ký listener hoặc tạo cache và thread riêng. Khi ngừng provider, nó phải ngắt nhận việc mới, xử lý hoặc hủy việc đang chạy, tháo đăng ký callback, đóng tài nguyên và xóa các tham chiếu lâu sống. Nếu khởi tạo thất bại giữa chừng, phần tài nguyên đã mở cũng phải được hoàn trả.

**Ownership transfer:** một phương thức trả về đối tượng có tài nguyên, ví dụ `InputStream`. Phải nói rõ bên nhận có trách nhiệm `close()`, thời hạn sử dụng và điều gì xảy ra nếu kết quả bị bỏ qua. Nếu không muốn truyền nghĩa vụ đóng cho caller, ưu tiên trả DTO hoặc giá trị đã được vật hóa.

Hai bên cùng gọi `close()` có thể gây đóng sớm hoặc double-close; cả hai bên cùng chờ bên kia đóng sẽ gây leak. `AutoCloseable` tạo ra một điểm đóng chuẩn trong Java, nhưng **không mặc nhiên bảo đảm `close()` idempotent hoặc thread-safe**. Nếu muốn cho phép gọi đóng lặp lại, phải ghi và triển khai điều đó trong hợp đồng riêng.

### 2.2. Bảng điều khoản tối thiểu

Với mỗi API mở rộng, nên công khai:

1. Bên nào tạo và sở hữu instance extension; một instance sống qua bao nhiêu request/tenant.
2. Tài nguyên nào được host cho mượn, trong bao lâu; provider có được giữ sau khi phương thức trả về hay không.
3. Tài nguyên nào provider phải tự đóng; thứ tự dừng task, hủy callback, đóng tài nguyên.
4. Kết quả trả về có chuyển quyền sở hữu cho caller hay không.
5. Hành vi khi khởi tạo thất bại, xử lý lỗi, timeout, hủy tác vụ và đóng lặp lại.
6. Thời điểm host được tháo provider khỏi registry và giải phóng class loader.

Không nên dựa vào tên phương thức như `getClient()` hoặc `open()` để suy đoán ownership: viết rõ trong Javadoc, tài liệu SPI và kiểm thử vòng đời.

## 3. Quy định trạng thái và phạm vi sống

**Trạng thái** gồm dữ liệu cấu hình, cache, bộ đếm, phiên làm việc, bảng ánh xạ và các object có thể thay đổi qua các lần gọi. Trước khi tuyên bố một provider là “thread-safe”, phải xác định trạng thái nào được chia sẻ.

| Phạm vi | Ví dụ | Cách quản lý |
| --- | --- | --- |
| Bất biến cho cả instance | Cấu hình đã kiểm tra, routing rules, `Clock` | Khởi tạo hoàn chỉnh rồi công bố an toàn; không sửa khi đang chạy |
| Riêng từng lần gọi | Request DTO, buffer tạm, trace ID | Tạo trong lời gọi, không giữ trong trường instance nếu không cần |
| Dùng chung trong một instance | Cache, bộ đếm, danh sách listener | Dùng cấu trúc đồng thời hoặc đồng bộ hóa và quy tắc đóng |
| Riêng tenant/session | Credential, cache theo tenant, session state | Phân vùng theo định danh, có giới hạn dung lượng và chính sách dọn dẹp |
| Toàn JVM/process | Registry `static`, thread, singleton toàn cục | Tránh mặc định; cần hợp đồng đa-tenant, classloader và cleanup cụ thể |

**Ưu tiên thiết kế ít shared mutable state:** biến cấu hình không đổi, request/response không đổi, dữ liệu tạm nằm trong scope của lời gọi. `record` của Java giúp biểu diễn DTO, nhưng chỉ bất biến nông: một `record` chứa `List` có thể vẫn bị sửa nếu không sao chép hoặc đóng băng dữ liệu bên trong.

Nếu phải có trạng thái dùng chung, chọn primitive dựa trên thao tác cần bảo vệ:

- `AtomicInteger`/`LongAdder` cho bộ đếm thích hợp; `LongAdder` thuận lợi khi cập nhật đồng thời lớn, nhưng tổng quan sát tức thời không phải snapshot tuyến tính hoàn hảo giữa các lần cập nhật.
- `ConcurrentHashMap` cho truy cập map đồng thời theo hợp đồng của nó; thao tác ghép qua nhiều key vẫn có thể cần lock hoặc thiết kế transaction riêng.
- `synchronized`/`Lock` khi nhiều trường phải thay đổi cùng một bất biến; hạn chế gọi callback của provider khác trong khi giữ lock.
- `volatile` để công bố/đọc trạng thái đơn giản như cờ dừng, **không** biến `count++` thành thao tác nguyên tử. `count++` là đọc, cộng và ghi, nên có thể mất cập nhật dù `count` được khai báo `volatile`.

Trạng thái khởi tạo phải được **công bố an toàn**: không để `this` thoát khỏi constructor, dùng trường `final` phù hợp và chuyển instance vào registry sau khi khởi tạo xong. Không để task nền đọc cấu hình đang được xây dựng dở.

**Cảnh báo khi hot reload:** `static` cache, `ThreadLocal`, listener, timer, thread và lambda được giữ ở singleton của host có thể giữ tham chiếu đến class hoặc class loader cũ, khiến plugin không thể được thu gom. Hủy đăng ký, giải phóng object và gọi `ThreadLocal.remove()` ở đúng luồng khi có thể; không dùng `ThreadLocal` như kho trạng thái request xuyên qua executor/asynchronous boundary nếu không có cơ chế truyền ngữ cảnh rõ ràng.

## 4. Quy định khả năng gọi đồng thời

“Có thể gọi từ nhiều thread” có nhiều nghĩa. Hợp đồng cần chọn **một mô hình gọi cho từng instance** và tách biệt khả năng chạy đồng thời với reentrancy.

| Mô hình | Host được làm gì? | Provider phải bảo đảm gì? |
| --- | --- | --- |
| **Concurrent shared instance** | Gọi nhiều `execute()` đồng thời trên cùng instance | Mọi dữ liệu dùng chung và side effect tuân theo tính nhất quán đã công bố |
| **Serialized per instance** | Tối đa một lời gọi đang hoạt động trên mỗi instance | Provider có thể dùng trạng thái tuần tự; host chịu trách nhiệm xếp hàng/khóa theo instance |
| **Thread-confined** | Chỉ gọi từ một thread/dispatcher được định danh | Host duy trì affinity; không đổi thread tùy ý giữa các callback |
| **Per-call instance** | Tạo instance riêng cho mỗi request hoặc đơn vị công việc | Không chia sẻ mutable state giữa các instance, trừ khi có cấu trúc chung được thiết kế riêng |

**Không nhầm “serialized” với “luôn cùng một thread”:** host có thể lần lượt chạy các lời gọi trên những thread khác nhau. Provider lệ thuộc `ThreadLocal` hoặc thread affinity phải yêu cầu mô hình thread-confined một cách minh bạch.

**Không nhầm “thread-safe” với “reentrant”:** một provider có thể xử lý nhiều lời gọi độc lập đồng thời nhưng không chịu được việc một lời gọi gọi ngược vào chính provider trước khi lời gọi đầu kết thúc. Cần ghi rõ callback của host có thể xảy ra đồng bộ/bất đồng bộ, có thể lồng nhau hay không và có được giữ lock khi callback không. Khuyến nghị host tránh gọi mã extension khi đang giữ global lock để giảm nguy cơ deadlock và lock inversion.

Đối với API bất đồng bộ, hợp đồng phải ghi thêm:

- Kết quả là `CompletionStage`, `Future`, callback hay publisher; ai quyết định executor thực thi phần tiếp theo.
- Có bao nhiêu lời gọi đang chạy tối đa; chính sách queue/backpressure khi quá tải, tránh tạo thread và queue không giới hạn.
- Timeout tính cho phần nào; khi hủy, provider có phải hợp tác kiểm tra interrupt/cancellation token không.
- Request/result có thể bị sử dụng đồng thời và có được sửa sau khi gửi không.
- Retry có thể chạy lại một lời gọi đã gây side effect; có cần idempotency key hay cơ chế deduplication không.

Trong Java, `Thread.interrupt()` là tín hiệu hợp tác, không phải phương thức cưỡng bức dừng mọi I/O hoặc mọi tác vụ. Provider cần xử lý `InterruptedException` đúng nghĩa, tránh nuốt interrupt. Host không được đóng tài nguyên mà một task còn đang sử dụng chỉ vì đã yêu cầu hủy.

## 5. Vòng đời: khởi tạo, hoạt động, dừng và nạp lại

Một state machine đơn giản cho **mỗi instance**:

~~~text
CREATED -> STARTED -> QUIESCING -> CLOSED
             |
             +---- failure ----> QUIESCING -> CLOSED
~~~

- **CREATED:** host xây dựng provider và truyền cấu hình/ngữ cảnh hợp lệ; provider chưa nhận request. Nếu constructor hoặc bước start thất bại, dọn các tài nguyên đã tạo một phần.
- **STARTED:** instance đã sẵn sàng; host công bố instance vào registry và có thể gửi request đúng mô hình concurrency đã khai báo.
- **QUIESCING:** host ngừng chấp nhận công việc mới cho instance, chờ hoặc hủy công việc đang chạy theo chính sách đã công bố, sau đó mới gọi cleanup.
- **CLOSED:** tài nguyên thuộc provider đã giải phóng; host gỡ tham chiếu, listener, registry và cuối cùng xử lý class loader do host sở hữu nếu không còn dùng.

Trình tự dừng an toàn thường là:

1. **Ngừng phân phối request mới** và đóng cổng callback vào instance cũ; thay thế registry một cách nguyên tử nếu có hot swap.
2. **Theo dõi in-flight calls** và chờ hoàn tất, hoặc gửi cancellation rồi xác nhận chúng đã dừng. Nếu hết timeout nhưng task vẫn dùng tài nguyên, phải có chính sách giữ/quarantine instance hoặc cô lập process; không tùy tiện giải phóng tài nguyên đang dùng.
3. **Cho provider đóng tài nguyên của mình**, tốt nhất theo thứ tự ngược với thứ tự mở. Ghi nhận lỗi đóng mà không bỏ qua việc đóng các tài nguyên còn lại.
4. **Tháo đăng ký và xóa tham chiếu**, sau đó host mới giải phóng tài nguyên của mình khi không còn consumer.

Không gọi `close()` đồng thời với `execute()` trừ khi interface tuyên bố và triển khai rõ mô hình đó. Cờ `closed` chỉ giúp phát hiện yêu cầu sau khi đóng; **nó không thay thế cơ chế drain các lời gọi đang chạy**.

Nếu module nạp lại thường xuyên, phiên bản mới có thể được tạo và kiểm tra trước, sau đó host chuyển routing sang phiên bản mới và drain phiên bản cũ. Không dùng lại trạng thái provider cũ nếu định dạng, class loader hay phiên bản không tương thích; việc chuyển trạng thái phải là hợp đồng độc lập.

## 6. Ví dụ Java 17 chạy được: host sở hữu pool và vòng đời provider

Ví dụ sau minh họa một extension xử lý nhiều request đồng thời. Host sở hữu `ExecutorService`, tạo và đóng instance extension; extension sở hữu bộ đếm `AtomicInteger` cùng cờ vòng đời. Hợp đồng của `apply()` cho phép gọi đồng thời **khi instance đang hoạt động**; `close()` chỉ được gọi sau khi host đã ngừng và đợi mọi task hoàn tất. Hai kết quả được đọc theo thứ tự gửi nên stdout xác định.

Lưu thành `ExtensionOwnershipDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ExtensionOwnershipDemo {
    record Request(String text) {
        Request {
            Objects.requireNonNull(text, "text");
        }
    }

    interface TextExtension extends AutoCloseable {
        // May run concurrently with other apply calls on this instance.
        // close() is called only after the host has drained all calls.
        String apply(Request request);

        int calls();
        boolean isClosed();

        @Override
        void close();
    }

    static final class UppercaseExtension implements TextExtension {
        private final AtomicInteger calls = new AtomicInteger();
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public String apply(Request request) {
            Objects.requireNonNull(request, "request");
            if (closed.get()) {
                throw new IllegalStateException("Extension already closed");
            }
            calls.incrementAndGet();
            return request.text().toUpperCase(Locale.ROOT);
        }

        @Override
        public int calls() {
            return calls.get();
        }

        @Override
        public boolean isClosed() {
            return closed.get();
        }

        @Override
        public void close() {
            closed.set(true); // Idempotent by this implementation's contract.
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        UppercaseExtension extension = new UppercaseExtension();

        try {
            List<Future<String>> results = List.of(
                pool.submit(() -> extension.apply(new Request("java"))),
                pool.submit(() -> extension.apply(new Request("spi")))
            );

            // Await each task; printing in submission order is deterministic.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } finally {
            // The host stops its own executor before closing the provider.
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Tasks still running: provider cannot close safely"
                    );
                }
            }

            extension.close();
            System.out.println("calls=" + extension.calls());
            System.out.println("closed=" + extension.isClosed());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~text
javac ExtensionOwnershipDemo.java
java ExtensionOwnershipDemo
~~~

Stdout của lệnh `java`:

~~~text
JAVA
SPI
calls=2
closed=true
~~~

**Điểm cần đọc từ ví dụ:**

- `Request` chỉ chứa `String` bất biến; hai request độc lập nên không có tranh chấp bộ nhớ input.
- `AtomicInteger` bảo vệ số lượt gọi khi `apply()` được thực thi từ nhiều thread; dùng `int calls` với `calls++` sẽ không bảo đảm kết quả đúng khi tăng đồng thời.
- `AtomicBoolean` thể hiện trạng thái đã đóng và cho phép `close()` lặp lại trong **triển khai cụ thể này**. Nó không ngăn race giữa `apply()` và `close()` nếu host vi phạm thứ tự vòng đời.
- Host giữ `Future`, ngừng executor, đợi termination rồi mới gọi `close()` của provider. Provider không tự `shutdown()` pool do host sở hữu.
- Khi task không chịu dừng sau timeout, ví dụ **không đóng provider** vì còn nguy cơ task đang dùng nó; hệ thống thật cần bổ sung logging, quarantine hoặc cô lập tiến trình. Nếu thread gọi `main` bị interrupt khi đang chờ, ví dụ cũng cần một chính sách hủy/phục hồi interrupt thích hợp trước khi giải phóng tài nguyên; đó là nhánh phục hồi được lược khỏi tình huống chạy bình thường này.

Đây là ví dụ đồng bộ hóa vòng đời đơn giản, không phải một plugin framework hoàn chỉnh. Khi thêm `start()`, callback hoặc hot reload, phải mở rộng state machine và cơ chế theo dõi in-flight tương ứng.

## 7. Các lỗi thiết kế thường gặp

| Dấu hiệu | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Provider gọi `shutdown()` trên executor mà host truyền vào | Làm hỏng công việc của extension khác | Quy định borrowed resource: provider không có quyền đóng |
| Provider lưu request vào field `currentRequest` của singleton | Lời gọi sau có thể ghi đè request trước | Dùng biến cục bộ hoặc state phân vùng theo request |
| Dùng `volatile int count` rồi `count++` | Có visibility nhưng không có atomicity | Dùng `AtomicInteger` hoặc lock |
| Gọi `close()` ngay khi thay registry, bỏ qua lời gọi đang chạy | Resource bị đóng khi task còn dùng | Chuyển sang QUIESCING, drain rồi close |
| Dựa vào `ThreadLocal` để truyền context giữa các executor | Luồng mới không tự nhận context; thread pool giữ dữ liệu cũ | Truyền context tường minh và cleanup ở đúng luồng |
| Đăng ký listener/scheduler ở `start()` nhưng không unregister | Leak instance/class loader sau reload | Cleanup đối xứng với đăng ký |
| Mô tả “thread-safe” nhưng không nói về `close()` | Host có thể đóng khi đang xử lý | Ghi rõ quan hệ giữa execute, callback, cancel và close |
| Retry mọi lỗi mà không xét side effect | Có thể tạo trùng ghi dữ liệu/thanh toán/gửi thông báo | Thiết kế idempotency hoặc phân loại thao tác không retry |
| Provider giữ lock rồi gọi ngược host; host giữ lock khác rồi gọi provider | Dễ tạo deadlock do thứ tự lock không thống nhất | Giảm phạm vi lock, gọi callback ngoài critical section |
| Gộp state nhiều tenant trong một `static HashMap` | Vừa có race vừa gây lẫn dữ liệu tenant/phiên | Phân vùng, bảo vệ truy cập và cleanup theo tenant |

## 8. Mẫu câu cần có trong tài liệu SPI

Với một extension point cụ thể, có thể ghi quy định theo mẫu sau, rồi thay các giá trị cho đúng thiết kế thực tế:

| Thuộc tính | Ví dụ hợp đồng rõ ràng |
| --- | --- |
| Instance scope | Host tạo **một instance cho mỗi tenant** và dùng lại cho nhiều request tenant đó |
| Tài nguyên host cung cấp | `Executor` và `Clock` là borrowed; provider không đóng, không lưu sau `close()` |
| Tài nguyên provider sở hữu | Cache cục bộ và listener; đăng ký khi `start()`, tháo đăng ký ở `close()` |
| State | Cấu hình bất biến; cache concurrent và có giới hạn; request state chỉ ở biến cục bộ |
| Concurrency | `execute()` có thể đồng thời trên cùng instance; callback có thể chạy trên thread khác |
| Reentrancy | Không cho phép callback đồng bộ gọi lại `execute()` trên cùng instance, hoặc yêu cầu công bố hỗ trợ rõ ràng |
| Blocking | `execute()` không giữ thread host quá thời hạn đã công bố; tác vụ lâu chuyển sang API async |
| Cancel/timeout | Host đưa tín hiệu hủy; provider hợp tác ngừng, trả lỗi/cancellation theo quy ước |
| Shutdown | Host chặn request mới, chờ hết in-flight, sau đó mới gọi `close()` đúng một lần |
| Failure | Exception được phân loại; resource đã mở khi start thất bại phải được đóng |
| Hot reload | Instance cũ drain và hủy callback trước khi host nhả class loader |
| Kiểm thử | Concurrency, close khi có request, start thất bại, retry, timeout, tenant isolation và unload |

Mẫu này là **ví dụ để viết hợp đồng**, không phải quy định ngầm của mọi SPI trong Java. Mỗi extension point phải chọn mô hình phù hợp với mục đích và ghi rõ những điểm khác biệt.

## 9. Kiểm thử hợp đồng trước khi cho phép plugin chạy

Một bộ kiểm thử tích hợp cần chứng minh được cả ba nhóm nghĩa vụ:

1. **Ownership:** provider không đóng tài nguyên host-owned; mọi file/connection/listener/thread của provider được cleanup khi bình thường và khi khởi tạo lỗi; kiểm tra lặp nhiều vòng start/stop/reload không tăng số thread hoặc tài nguyên còn sống.
2. **State:** cùng input cho kết quả đúng; state mỗi request/tenant không lẫn nhau; bộ đếm/cache có kết quả hợp lệ dưới tải; không có mutable state được công bố khi đang khởi tạo dở.
3. **Concurrency:** gọi hàng trăm hoặc hàng nghìn request đồng thời theo mô hình đã khai báo; thử callback lồng nhau nếu được phép; thử timeout, interrupt, cancel, retry, drain và lỗi lúc close. Chạy lặp để phát hiện race; không coi một lần thành công là bằng chứng thread safety.
4. **Lifecycle:** dừng tiếp nhận request mới trước khi close; không task nào truy cập resource sau close; reload không giữ class loader cũ qua listener, thread, cache hoặc `ThreadLocal`. Nếu dùng thread dump, heap dump hoặc metrics để xác minh, so sánh sau nhiều chu kỳ.
5. **Compatibility:** thay provider bằng một triển khai khác cùng interface mà host vẫn tuân thủ scope, ownership và concurrency contract; không phụ thuộc ngẫu nhiên vào chi tiết triển khai của provider cũ.

Khi thiết kế extension point mới, hãy viết mô tả ownership, state scope, concurrency/reentrancy và shutdown **trước khi triển khai interface**. Một chữ ký Java hợp lệ chỉ bảo đảm tương thích kiểu; các quy tắc trên mới giúp extension vận hành an toàn trong runtime thực tế.
