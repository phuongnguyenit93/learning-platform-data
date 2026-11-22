# Vai trò của ObservationRegistry, Observation.Context và ObservationHandler

## 1. Vì sao cần ba thành phần riêng?

Giả sử ta muốn quan sát thao tác xác nhận đơn hàng. Ta cần biết khi nào thao tác bắt đầu, kết thúc, thất bại và có những thuộc tính gì. Sau đó, cùng một thao tác có thể phục vụ nhiều nhu cầu: đo thời gian, tạo span để lần theo lời gọi, hoặc ghi log chọn lọc.

Nếu mã xử lý đơn hàng tự làm cả ba việc, nó sẽ bị gắn chặt với từng công cụ quan sát. Khi đổi công cụ hoặc thêm một đầu ra, ta lại sửa mã nghiệp vụ.

Micrometer Observation tách bài toán thành các vai trò:

| Thành phần | Câu hỏi mà nó trả lời |
| --- | --- |
| `Observation` | Lần thực hiện công việc này bắt đầu, kết thúc, phát sinh lỗi hoặc sự kiện lúc nào? |
| `ObservationRegistry` | Lần quan sát sử dụng cấu hình và những bộ xử lý nào? Đâu là observation hiện hành trong phạm vi thực thi? |
| `Observation.Context` | Những dữ liệu và trạng thái nào thuộc về chính lần quan sát này? |
| `ObservationHandler` | Khi nhận một mốc vòng đời, cần thực hiện hành động quan sát nào? |

Ba kiểu trong đề bài không thay thế `Observation`. Chúng phối hợp để `Observation` vận hành: registry cung cấp cấu hình, context mang dữ liệu, handler phản ứng với vòng đời.

```text
Mã nghiệp vụ được gắn Observation
              |
              v
        ObservationRegistry
        chọn cấu hình/handler
              |
              v
         Observation  ------ dùng ------> Context của lần thực hiện
              |
        start / error / event / stop
              |
              v
       Handler hỗ trợ context
              |
       đo thời gian / tracing / log
```

Đây là cách phân chia trách nhiệm được dùng trong [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html). Phần thực hành bên dưới dùng Micrometer 1.13.0 để kiểm chứng trực tiếp callback; khi dùng trong Spring Boot 3.3, để dependency management của Boot quản lý phiên bản thư viện.

## 2. ObservationRegistry: nơi cấu hình quan sát được dùng chung

### 2.1. Registry quản lý cấu hình, không phải kết quả của một yêu cầu

Trong một chương trình Java độc lập, có thể tạo registry rồi đăng ký handler:

```java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig().observationHandler(new CheckoutHandler());
```

Đây là đoạn trích; `CheckoutHandler` được định nghĩa đầy đủ ở ví dụ chạy được phía dưới.

Registry cho biết những bộ xử lý nào tham gia, cùng các tùy biến liên quan như điều kiện cho phép quan sát, quy ước tên/nhãn và bộ lọc context. Đối với bài này, điểm quan trọng nhất là **handler phải được đăng ký vào đúng registry mà observation đang dùng**.

Nếu đăng ký handler vào registry A nhưng tạo observation bằng registry B, observation đó không tự tìm handler của A. Tên observation giống nhau cũng không nối hai cấu hình lại với nhau.

Registry thường được chia sẻ trong ứng dụng. Nó không phải đối tượng chứa mã đơn hàng hay kết quả riêng của một lần gọi. Những giá trị ấy thuộc context tương ứng.

### 2.2. Registry mới không có sẵn mọi tích hợp

`ObservationRegistry.create()` chỉ tạo registry của chương trình độc lập. Nó không tự:

- Tạo một backend Prometheus hoặc một hệ thống tracing.
- Gắn mọi handler đang có trong Spring.
- Gửi dữ liệu ra mạng.
- Lưu lịch sử mọi observation đã hoàn tất để truy vấn.

Trong Micrometer 1.13.0 ở ví dụ thực hành, registry mới không có handler dẫn đến observation không thực hiện công việc quan sát; phần mã được truyền vào `observe(...)` vẫn chạy.

Vì vậy, nếu chạy chương trình nghiệp vụ thấy đúng kết quả nhưng không thấy timer/span, phải kiểm tra cấu hình registry và handler trước khi kết luận rằng lambda không được gọi.

### 2.3. Observation hiện hành là một khái niệm về scope

Registry có thể trả về observation hiện hành:

```java
Observation current = registry.getCurrentObservation();
```

`start()` và “trở thành observation hiện hành” là hai việc khác nhau. Việc mở `Observation.Scope` mới đặt observation vào phạm vi hiện hành của luồng trong cách thực thi đồng bộ thông thường.

Điều này giúp mã ở sâu bên trong chuỗi gọi tìm được observation đang bao quanh nó mà không phải truyền tham số qua mọi phương thức. Nhưng nó không có nghĩa registry là một biến toàn cục chứa “yêu cầu gần nhất” của tất cả người dùng.

Khi không có scope hiện hành, kết quả có thể là `null`. Luôn xét trường hợp này nếu đọc current observation từ mã dùng chung.

## 3. Observation.Context: dữ liệu và trạng thái của một lần quan sát

### 3.1. Context đi cùng một observation cụ thể

Giả sử đồng thời có hai đơn hàng:

```text
Registry dùng chung
   |
   +-- Observation A -- Context A: channel=web, result=success
   |
   +-- Observation B -- Context B: channel=store, result=failed
```

Hai lần thực hiện có thể dùng chung một handler, nhưng không nên dùng chung context có thể thay đổi.

Context có các dữ liệu tiêu chuẩn như tên, tên theo ngữ cảnh, lỗi và các cặp khóa–giá trị. Ta cũng có thể đặt dữ liệu phụ vào vùng lưu trữ dạng map hoặc tạo lớp con có thuộc tính rõ nghĩa.

Ví dụ từ chương trình thực hành:

```java
static final class CheckoutContext extends Observation.Context {
    final String channel;
    String result = "pending";

    CheckoutContext(String channel) {
        this.channel = channel;
    }
}
```

`channel` và `result` phục vụ việc quan sát thao tác thanh toán trong ví dụ. Mỗi lần gọi sẽ tạo một `CheckoutContext` mới. Handler đọc context đó để biết kết quả của đúng lần gọi, không cần giữ kết quả trong một biến instance dùng chung.

### 3.2. Dữ liệu phụ giúp nối các callback

Một handler có thể cần thông tin từ `onStart` để hoàn tất công việc trong `onStop`. Ví dụ điển hình là trạng thái của một phép đo thời gian.

Trong ví dụ, để stdout dễ kiểm chứng, ta lưu một dấu đánh dấu:

```java
context.put(START_MARKER, "ready");
```

Rồi đọc lại trong `onStop`:

```java
String marker = context.get(START_MARKER);
```

`START_MARKER` là một đối tượng khóa dùng chung; **giá trị** của nó nằm trong từng context. Dùng khóa riêng giúp tránh vô tình ghi đè dữ liệu của handler khác.

Nếu đặt dữ liệu vào context bằng một khóa có kiểu giá trị không nhất quán, việc lấy ra có thể lỗi ép kiểu. Với dữ liệu quan trọng hoặc phức tạp, lớp context chuyên biệt giúp diễn đạt hợp đồng rõ hơn.

### 3.3. Đặt vào context không đồng nghĩa đã xuất thành nhãn

Phải phân biệt ba dạng dữ liệu:

| Dạng dữ liệu | Ví dụ | Điều không được tự suy ra |
| --- | --- | --- |
| Thuộc tính của lớp context | `context.result = "success"` | Không tự trở thành nhãn của mọi timer |
| Dữ liệu map nội bộ | `context.put(START_MARKER, "ready")` | Không tự xuất toàn bộ map đến backend |
| Metadata được khai báo | `lowCardinalityKeyValue("channel", "web")` | Đầu ra còn phụ thuộc handler và tích hợp đang dùng |

Trong ví dụ, handler tự đọc `result` và `marker` để in. Nếu bỏ logic đó, hai giá trị không tự xuất hiện trong stdout.

Metadata có số giá trị hữu hạn, chẳng hạn kênh `web/store`, thường phù hợp để phân nhóm metrics. Mã đơn hàng có số giá trị rất lớn cần được xem xét cho dữ liệu chi tiết như trace, tránh đưa vào nhãn metrics. Dù thuộc nhóm nào, chỉ đưa dữ liệu thật sự cần thiết vào quan sát; nhãn “high cardinality” không tự làm dữ liệu nhạy cảm trở nên phù hợp để xuất.

### 3.4. Context có thể thay đổi, nên thời điểm đọc có ý nghĩa

Ở đầu thao tác, `result` có thể là `pending`; sau khi chạy nghiệp vụ, nó đổi thành `success` hoặc `failed`. `onStart` không thể giả định biết kết quả cuối cùng.

Nếu handler cần dữ liệu ngay khi bắt đầu, phải điền dữ liệu ấy trước `start()` hoặc trước khi gọi `observe(...)`. Không thêm thông tin quan trọng quá muộn rồi trông chờ mọi callback trước đó đã thấy nó.

Context cũng không phải vùng bộ nhớ đồng bộ hóa cho mọi luồng. Không chia sẻ một context đang được sửa cho nhiều tác vụ song song mà không có thiết kế quản lý truy cập và vòng đời phù hợp.

## 4. ObservationHandler: nơi phản ứng với vòng đời

### 4.1. Handler nhận đúng loại context mình hỗ trợ

Một handler có kiểu:

```java
ObservationHandler<CheckoutContext>
```

cần triển khai phép kiểm tra:

```java
@Override
public boolean supportsContext(Observation.Context context) {
    return context instanceof CheckoutContext;
}
```

Khai báo generic cho biết kiểu mà các callback muốn nhận; `supportsContext` là điều kiện chọn ở thời điểm chạy. Không trả `true` cho mọi context rồi ép sang một lớp con bất kỳ.

Nếu handler chỉ hỗ trợ `CheckoutContext`, một observation được tạo với `Observation.Context` mặc định không tự được biến thành `CheckoutContext`. Có cùng tên `checkout` cũng không làm phép kiểm tra `instanceof` đổi kết quả.

### 4.2. Các callback có nhiệm vụ khác nhau

| Callback | Tín hiệu tương ứng | Việc handler có thể làm |
| --- | --- | --- |
| `onStart(context)` | Observation được bắt đầu | Chuẩn bị trạng thái đo, bắt đầu công việc quan sát |
| `onScopeOpened(context)` | Observation được đưa vào scope | Thiết lập trạng thái gắn với phạm vi thực thi |
| `onEvent(event, context)` | Có sự kiện được báo tường minh | Ghi một mốc chi tiết của thao tác |
| `onError(context)` | Có lời gọi báo lỗi cho observation | Đọc lỗi đã được ghi vào context |
| `onScopeClosed(context)` | Scope được đóng | Dọn trạng thái gắn với scope |
| `onStop(context)` | Observation kết thúc | Hoàn tất phép đo hoặc đầu ra tương ứng |

Bảng tập trung vào các callback dùng trong bài; API còn có khả năng khác. Mô hình context và handler được trình bày trong [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Handler không phải phương thức nghiệp vụ. `onError` không tự thử thanh toán lại hoặc rollback giao dịch. `onStop` cũng không nên là nơi quyết định nghiệp vụ đã thành công hay thất bại.

Một handler có thể được gọi bởi nhiều observation đồng thời. Trạng thái riêng của từng lần thực hiện nên nằm trong context, không đặt vào trường như `this.currentOrder` hay `this.startedAt` của handler singleton.

### 4.3. Một observation có thể phục vụ nhiều đầu ra

Có thể đăng ký nhiều handler phù hợp, chẳng hạn một handler phục vụ đo lường và một handler phục vụ tracing. Mã nghiệp vụ vẫn mô tả cùng một lần thực hiện qua Observation.

Điều này không có nghĩa luôn phải tự viết tất cả handler. Khi dùng framework, nhiều handler đã được tích hợp. Chỉ thêm handler riêng khi có hành vi quan sát cần bổ sung.

Khi có composite handler chọn phần tử đầu tiên phù hợp, quy tắc lựa chọn bên trong composite khác với danh sách handler độc lập. Không dựa vào giả định rằng mọi handler đã khai báo đều chắc chắn chạy trong mọi cấu hình; kiểm tra cách đăng ký và điều kiện hỗ trợ của chúng.

## 5. Phân biệt vòng đời Observation với vòng đời Scope

### 5.1. Start/stop đo một công việc; open/close scope xác định phạm vi hiện hành

Có thể hình dung hai trục:

```text
Vòng đời công việc:   tạo → start --------------------→ stop
Scope đồng bộ:                 open → chạy mã → close
```

Mở scope không thay cho bắt đầu observation. Đóng scope không thay cho dừng observation.

Ví dụ, nếu chỉ đóng scope mà quên `stop()`, handler có thể chưa hoàn tất phép đo. Nếu chỉ gọi `start()` mà không mở scope, đoạn mã bên trong không nên trông chờ `getCurrentObservation()` trả về chính observation đó.

Với công việc đồng bộ đơn giản, `observe(...)` là cách thuận tiện để quản lý các thao tác này cùng việc báo ngoại lệ.

### 5.2. Scope lồng nhau cần khôi phục phạm vi bên ngoài

Khi có observation cha đang ở trong scope, rồi mở scope cho observation con:

```text
scope cha mở     → current = cha
scope con mở    → current = con
scope con đóng  → current được khôi phục về cha
scope cha đóng  → trở lại phạm vi trước cha
```

Sơ đồ mô tả việc dùng scope đúng thứ tự trên cùng luồng. Cần đóng theo thứ tự ngược với mở và không để scope tồn tại vượt phần công việc mà nó bao quanh.

Quan hệ cha–con không phải hệ quả của việc tái sử dụng cùng context. Context cha và con có dữ liệu riêng; việc lấy current observation và thiết lập quan hệ phụ thuộc cách instrumentation tạo observation.

### 5.3. Đổi luồng không tự mang theo mọi trạng thái

`Observation.Context`, Spring `ApplicationContext`, Reactor `Context` và cơ chế truyền ngữ cảnh qua luồng là các khái niệm khác nhau.

Đưa một lambda vào executor không đảm bảo observation hiện hành ở luồng gửi sẽ tự trở thành hiện hành ở luồng nhận. Tương tự, không mở scope quanh việc dựng một reactive publisher rồi mặc định rằng scope ấy vẫn tồn tại khi publisher thực sự chạy.

Với tác vụ bất đồng bộ/reactive, dùng cơ chế context propagation và instrumentation phù hợp của framework. Phần thực hành ở bài này cố ý dùng một luồng đồng bộ để quan sát rõ vai trò của ba thành phần.

## 6. Ví dụ Java chạy được: nhìn thấy cả ba vai trò

Ví dụ dưới đây thực hiện hai lần checkout: một lần thành công và một lần ném ngoại lệ. Handler chỉ in callback để phục vụ học tập; chương trình không cần Spring server, endpoint HTTP, hệ thống metrics hoặc tracing backend.

### 6.1. Chuẩn bị

Cần JDK 17 trở lên và hai thư viện cùng phiên bản:

```text
io.micrometer:micrometer-observation:1.13.0
io.micrometer:micrometer-commons:1.13.0
```

Đặt hai JAR tương ứng vào thư mục `lib/` cạnh file Java. Có thể lấy chúng từ Maven Central hoặc cache của công cụ build. Đây là phiên bản cố định của ví dụ độc lập, không phải yêu cầu ghi đè phiên bản do Spring Boot quản lý trong ứng dụng thật.

Cấu trúc thư mục:

```text
observation-demo/
├── ObservationRolesDemo.java
└── lib/
    ├── micrometer-observation-1.13.0.jar
    └── micrometer-commons-1.13.0.jar
```

### 6.2. Mã nguồn đầy đủ

Lưu đúng tên `ObservationRolesDemo.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationRolesDemo {
    private static final Object START_MARKER = new Object();

    static final class CheckoutContext extends Observation.Context {
        final String channel;
        String result = "pending";

        CheckoutContext(String channel) {
            this.channel = channel;
        }
    }

    static final class CheckoutHandler
            implements ObservationHandler<CheckoutContext> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof CheckoutContext;
        }

        @Override
        public void onStart(CheckoutContext context) {
            context.put(START_MARKER, "ready");
            System.out.println("START " + context.getName()
                    + " channel=" + context.channel);
        }

        @Override
        public void onScopeOpened(CheckoutContext context) {
            System.out.println("SCOPE_OPEN " + context.getName());
        }

        @Override
        public void onEvent(Observation.Event event, CheckoutContext context) {
            System.out.println("EVENT " + event.getName());
        }

        @Override
        public void onError(CheckoutContext context) {
            System.out.println("ERROR "
                    + context.getError().getClass().getSimpleName());
        }

        @Override
        public void onScopeClosed(CheckoutContext context) {
            System.out.println("SCOPE_CLOSE " + context.getName());
        }

        @Override
        public void onStop(CheckoutContext context) {
            String error = context.getError() == null
                    ? "none" : context.getError().getClass().getSimpleName();
            String marker = context.get(START_MARKER);
            System.out.println("STOP " + context.getName()
                    + " result=" + context.result
                    + " error=" + error + " marker=" + marker);
        }
    }

    static void checkout(ObservationRegistry registry,
                         String channel, boolean fail) {
        CheckoutContext context = new CheckoutContext(channel);
        Observation observation = Observation.createNotStarted(
                "checkout", () -> context, registry)
                .lowCardinalityKeyValue("channel", channel);
        try {
            observation.observe(() -> {
                Observation current = registry.getCurrentObservation();
                System.out.println("BODY current="
                        + (current == observation ? "checkout" : "unexpected"));
                observation.event(Observation.Event.of("inventory.checked"));
                if (fail) {
                    context.result = "failed";
                    throw new IllegalStateException("payment unavailable");
                }
                context.result = "success";
            });
        }
        catch (IllegalStateException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
                .observationHandler(new CheckoutHandler());

        checkout(registry, "web", false);
        System.out.println("---");
        checkout(registry, "store", true);
        System.out.println("AFTER current="
                + (registry.getCurrentObservation() == null ? "none" : "leaked"));

        Observation.createNotStarted(
                "without.handler", ObservationRegistry.create())
                .observe(() -> System.out.println("NO_HANDLER business=executed"));
    }
}
```

### 6.3. Biên dịch và chạy

Trong PowerShell tại thư mục chứa file:

```powershell
javac --release 17 -cp "lib/*" ObservationRolesDemo.java
java -cp ".;lib/*" ObservationRolesDemo
```

Trên Linux/macOS, dấu phân cách các mục classpath khi chạy là `:`:

```bash
javac --release 17 -cp "lib/*" ObservationRolesDemo.java
java -cp ".:lib/*" ObservationRolesDemo
```

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm chứng trên OpenJDK 24.0.2, dùng hai JAR Micrometer 1.13.0. Stdout thu được:

```text
START checkout channel=web
SCOPE_OPEN checkout
BODY current=checkout
EVENT inventory.checked
SCOPE_CLOSE checkout
STOP checkout result=success error=none marker=ready
---
START checkout channel=store
SCOPE_OPEN checkout
BODY current=checkout
EVENT inventory.checked
SCOPE_CLOSE checkout
ERROR IllegalStateException
STOP checkout result=failed error=IllegalStateException marker=ready
CAUGHT payment unavailable
AFTER current=none
NO_HANDLER business=executed
```

### 6.4. Đọc output theo đúng trách nhiệm

**Registry:** cùng một registry được truyền vào cả hai lần `checkout`. Handler được đăng ký một lần trước khi chạy, không phải đăng ký thêm theo từng đơn.

**Context:** mỗi lần `checkout` tạo một `CheckoutContext` mới. Lần đầu mang `channel=web`, lần sau mang `channel=store`. Thuộc tính `result` đổi theo lần gọi tương ứng; dấu `marker=ready` được handler ghi ở `onStart` và đọc lại ở `onStop`.

**Handler:** các dòng `START`, `SCOPE_OPEN`, `EVENT`, `SCOPE_CLOSE`, `ERROR`, `STOP` được in bởi callback. Dòng `BODY` được in bởi mã nằm trong `observe`, giúp phân biệt công việc đang được quan sát với bộ xử lý quan sát.

**Scope:** `BODY current=checkout` xác nhận observation này đang hiện hành khi lambda chạy. `AFTER current=none` xác nhận scope của hai lần thực hiện không còn bị giữ lại ở cuối chương trình.

**Lỗi:** `CAUGHT payment unavailable` chỉ xuất hiện sau khi ngoại lệ đi ra khỏi `observe(...)` và được phần demo bắt lại. Observation không biến lỗi thanh toán thành kết quả thành công.

**Registry không có handler:** dòng cuối cho thấy mã bên trong `observe` vẫn thực thi khi dùng một registry mới chưa có handler. Không có thêm các dòng callback cho `without.handler`.

### 6.5. Thứ tự callback phải dựa trên đường thực thi đang dùng

Ở đường lỗi của `observe(Runnable)` trong phép chạy Micrometer 1.13.0 này:

```text
lambda ném lỗi
    → đóng scope
    → báo lỗi cho observation
    → dừng observation
    → ngoại lệ đi ra ngoài observe
```

Vì vậy output là `SCOPE_CLOSE` trước `ERROR`. Không nên học thuộc một sơ đồ rằng lỗi luôn được báo trước khi scope đóng.

Nếu tự điều khiển vòng đời và gọi `observation.error(ex)` ngay bên trong scope, ta có thể tạo thứ tự khác. Handler cần dựa vào mốc nó được thông báo và dữ liệu context có ở mốc đó, không dựa vào giả định rằng mọi callback luôn chạy khi observation còn hiện hành.

Một hệ quả dễ bỏ sót: trong `onStop`, dùng tham số `context` mà callback nhận để đọc dữ liệu của observation đang kết thúc. Không lấy `registry.getCurrentObservation()` rồi mặc định đó vẫn là observation ấy; scope của nó có thể đã đóng hoặc current đã trở về observation bên ngoài.

## 7. Khi cần tự điều khiển vòng đời

`observe(...)` phù hợp với công việc đồng bộ được bao trọn trong một lambda. Nếu quản lý tường minh, phải chịu trách nhiệm cho cả báo lỗi, đóng scope và dừng observation.

Đoạn sau minh họa cấu trúc sử dụng trong một phương thức đã có registry. `performCheckout()` là lời gọi nghiệp vụ của ứng dụng, không phải một hàm có sẵn trong Micrometer; đây là đoạn trích, không phải chương trình độc lập:

```java
Observation observation = Observation.createNotStarted(
        "checkout", registry)
        .lowCardinalityKeyValue("channel", "web");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    performCheckout();
}
catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
}
finally {
    observation.stop();
}
```

Các điểm phải hiểu:

- Try-with-resources đóng scope của đường thực thi này.
- `finally` dừng observation kể cả khi nghiệp vụ ném ngoại lệ.
- `observation.error(ex)` báo lỗi cho cơ chế quan sát; `throw ex` mới tiếp tục đưa ngoại lệ cho bên gọi.
- Nếu nghiệp vụ có checked exception, phải xử lý/khai báo và báo lỗi tương ứng với hợp đồng của phương thức; không chỉ sao chép phần catch rồi bỏ sót loại lỗi của ứng dụng.

Trong đoạn trích, catch nằm ngoài try-with-resources nên scope được đóng trước khi catch báo lỗi. Việc đóng scope và việc báo lỗi vẫn là hai thao tác riêng.

Ngược lại, nếu lambda tự bắt ngoại lệ rồi trả về bình thường, `observe` không thể tự biết rằng lỗi đã bị xử lý bên trong. Nếu đó là một thất bại cần quan sát, mã xử lý phải chủ động báo qua `observation.error(ex)` theo ý nghĩa nghiệp vụ đã chọn. Không gắn lỗi cho một nhánh bình thường chỉ để tạo thêm tín hiệu.

Tránh gọi `start/stop` thủ công rồi lại dùng `observe` cho cùng observation. Chọn một cách sở hữu vòng đời rõ ràng thay vì để nhiều lớp cùng cố kết thúc nó.

## 8. Đặt ba thành phần vào Spring Boot Actuator

### 8.1. Dùng registry do Spring quản lý

Trong ứng dụng có Actuator và auto-configuration phù hợp, inject `ObservationRegistry` thay vì tự tạo một registry riêng trong service.

Ví dụ cấu trúc constructor:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ObservationRegistry observationRegistry;

    public CheckoutService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }
}
```

Lớp này chỉ minh họa việc nhận registry, chưa triển khai nghiệp vụ. Khi bổ sung phương thức, tạo observation và context mới cho từng lần thực hiện bằng registry đã được inject.

Một trường `final ObservationRegistry` trong service singleton là hợp lý. Một trường `CheckoutContext currentContext` dùng để giữ dữ liệu của mọi yêu cầu là thiết kế dễ trộn dữ liệu giữa các lần gọi.

### 8.2. Để Spring đăng ký handler bean

Spring Boot có thể tự đăng ký các bean `ObservationHandler` vào registry được quản lý. Ví dụ, khi giữ lớp demo cùng package và muốn đăng ký handler của nó, thêm phương thức sau trong một lớp `@Configuration`:

```java
@Bean
ObservationRolesDemo.CheckoutHandler checkoutObservationHandler() {
    return new ObservationRolesDemo.CheckoutHandler();
}
```

Đây là đoạn khai báo bean; cần import `org.springframework.context.annotation.Bean` trong lớp cấu hình. Không đồng thời đăng ký chính handler đó thủ công vào registry lần nữa.

Handler trong demo chỉ hỗ trợ `CheckoutContext`. Nếu mã Spring tạo observation bằng overload không cung cấp context riêng, context mặc định sẽ không khớp điều kiện đó. Có hai cách thiết kế rõ ràng:

1. Tiếp tục tạo `CheckoutContext` khi quan sát checkout và dùng handler chuyên biệt.
2. Viết handler dành cho `Observation.Context` chung, với điều kiện hỗ trợ phù hợp, chẳng hạn kiểm tra loại ngữ cảnh hoặc tên operation theo hợp đồng.

Không bỏ kiểm tra kiểu chỉ để ép handler chạy trên mọi loại HTTP, database hoặc messaging observation của framework.

Các quy tắc inject registry, đăng ký bean và phân loại nhãn của Spring Boot được mô tả trong [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 8.3. ObservationRegistry và MeterRegistry không phải cùng một nơi

`ObservationRegistry` điều phối vòng đời quan sát. `MeterRegistry` quản lý meter và các phép đo của Micrometer Metrics.

Handler phục vụ metrics nối hai cơ chế: nó nghe observation rồi ghi số liệu vào meter registry. Handler phục vụ tracing thực hiện một vai trò khác, như tạo/quản lý span qua tích hợp tracing.

Vì vậy:

- Thấy một observation chạy không chứng minh đã có span được gửi đến backend.
- Có một handler in console không tự tạo timer.
- Có metrics cục bộ không chứng minh mạng xuất metrics đã hoạt động.
- Muốn truy vấn `/actuator/metrics`, còn cần một ứng dụng HTTP, endpoint được expose và phép đo thực sự được ghi; chương trình Java độc lập ở trên không tạo endpoint này.

Trong tích hợp chuẩn của Boot, nhãn low cardinality được dùng cho metrics và traces, còn nhãn high cardinality dành cho traces. Custom handler vẫn phải tự tuân theo thiết kế dữ liệu của nó. Không dùng cơ chế phân loại này như lời hứa rằng mọi thuộc tính map nội bộ của context sẽ được tự động xuất.

### 8.4. Đặt ranh giới quan sát có ý nghĩa

Nếu framework đã quan sát yêu cầu HTTP, một observation nghiệp vụ như `checkout` có thể là một công việc bên trong yêu cầu ấy. Điều này có ý nghĩa khi cần tách thời gian/kết quả của nghiệp vụ khỏi toàn bộ HTTP request.

Ngược lại, tạo thêm observation có cùng ý nghĩa chỉ vì muốn “chắc chắn có dữ liệu” có thể gây đo trùng. Trước khi thêm handler hoặc instrumentation, xác định công việc nào đang được đo và ai sở hữu vòng đời của nó.

## 9. Lỗi thường gặp và cách tìm nguyên nhân

| Hiện tượng | Nguyên nhân cần xét | Cách kiểm tra |
| --- | --- | --- |
| Lambda chạy nhưng handler không in gì | Dùng sai registry hoặc chưa đăng ký handler | Đối chiếu nơi tạo observation với registry được cấu hình |
| Handler có đăng ký nhưng không nhận observation mong muốn | `supportsContext` không khớp | Kiểm tra lớp context thật, không chỉ tên operation |
| Lỗi ép kiểu khi callback chạy | Handler chuyên biệt nhận context không phù hợp | Sửa điều kiện hỗ trợ thay vì ép kiểu mù |
| `onStart` đọc thấy dữ liệu chưa có | Dữ liệu được thêm sau khi bắt đầu | Đặt thông tin đầu vào trước start; kết quả đọc ở mốc thích hợp |
| Nhiều yêu cầu ghi đè trạng thái nhau | Lưu trạng thái của từng lần gọi trong handler singleton hoặc dùng chung context | Chuyển trạng thái riêng về từng context |
| Mã bên trong không thấy current observation | Chỉ start, chưa mở scope hoặc đã đổi luồng | Đối chiếu phạm vi thực thi và cơ chế propagation |
| Sau khi kết thúc vẫn còn observation hiện hành | Scope không được đóng đúng cách | Dùng cấu trúc quản lý scope rõ ràng và kiểm tra khôi phục |
| Có lỗi nghiệp vụ nhưng handler không thấy lỗi | Ngoại lệ bị bắt trong lambda và không được báo | Kiểm tra nơi xử lý lỗi và lời gọi `observation.error(ex)` |
| Có thuộc tính trong context nhưng backend không thấy | Thuộc tính nội bộ chưa được ánh xạ thành dữ liệu đầu ra | Kiểm tra handler/convention và metadata đã khai báo |
| Có callback nhưng không có timer/span | Handler hiện tại chỉ làm một hành động khác, như in console | Kiểm tra tích hợp metrics/tracing cụ thể |
| Có đầu ra bị trùng | Đăng ký handler hai lần hoặc instrument trùng ranh giới | Kiểm kê nơi đăng ký và nơi tạo observation |

Callback là mã Java được chạy trong đường thực thi gọi vòng đời observation, không phải một hàng đợi bất đồng bộ mặc định. Một custom handler làm I/O chậm hoặc ném lỗi có thể ảnh hưởng đến lời gọi đang được quan sát. Ví dụ in console ở bài này phục vụ học tập; trong ứng dụng thật, giữ handler nhẹ, kiểm soát lỗi và tránh đưa lại nghiệp vụ vào callback.

Không coi handler là cơ chế lưu trữ đáng tin cậy cho kiểm toán tài chính hay xử lý giao dịch. Việc bật/tắt observation hoặc thay bộ xử lý quan sát không nên quyết định đơn hàng có được tạo hay không.

## 10. Thực hành để kiểm tra hiểu biết

Thực hiện từng thay đổi riêng trên bản sao chương trình ví dụ, rồi so với output ban đầu.

### Bài 1: bỏ đăng ký CheckoutHandler

Xóa lời gọi `observationHandler(new CheckoutHandler())`, giữ phần nghiệp vụ.

Kỳ vọng: không còn các dòng do handler in. Phần mã nghiệp vụ vẫn được thực thi; không nên kết luận “checkout không chạy” từ việc không thấy `START/STOP`. Dòng `BODY current` có thể thay đổi vì observation không còn tham gia quan sát như cấu hình ban đầu; đừng dùng nó làm bằng chứng nghiệp vụ đã bị bỏ qua.

### Bài 2: chỉ cho phép context kiểu khác

Thay điều kiện của `supportsContext` bằng một điều kiện luôn sai để quan sát tác dụng, không sửa nghiệp vụ.

Kỳ vọng: handler này không nhận callback cho checkout. Đây là sự khác biệt giữa “handler tồn tại trong cấu hình” và “handler hỗ trợ context của observation đang xét”.

Không giữ điều kiện giả đó trong thiết kế thật; mục đích bài thực hành là kiểm tra điểm lựa chọn.

### Bài 3: chuyển dữ liệu riêng sang trường của handler

Hình dung handler singleton có trường `String lastResult` được sửa bởi mọi `onStop`. Khi có hai yêu cầu chạy song song, vì sao đây không thay thế được `context.result`?

Đáp án: trường đó thuộc một handler dùng chung, nên không đại diện ổn định cho một lần quan sát. Context riêng gắn dữ liệu với từng observation; nếu thêm concurrency vào ví dụ, còn phải quản lý các đối tượng và scope đúng theo luồng thực thi.

### Bài 4: bắt lỗi ở bên trong lambda

Thay nhánh ném lỗi bằng một đoạn bắt và xử lý lỗi ngay trong lambda, không gọi `observation.error(ex)`.

Kỳ vọng: bên ngoài `observe` không còn nhận ngoại lệ từ nhánh đã xử lý; callback báo lỗi không tự xuất hiện chỉ vì từng có một exception object được tạo. Nếu thất bại đó cần ghi nhận, phải báo tường minh theo hợp đồng quan sát.

### Bài 5: thêm handler thứ hai

Đăng ký một handler nhẹ khác chỉ đếm số lần kết thúc và hỗ trợ cùng `CheckoutContext`.

Kỳ vọng với các handler độc lập phù hợp: cùng hai lần checkout có thể phục vụ cả handler in callback lẫn handler đếm. Không cần chép lại nghiệp vụ một lần cho mỗi công cụ quan sát.

Khi cần kiểm thử tự động instrumentation thực tế, Micrometer có `micrometer-observation-test` và `TestObservationRegistry` để kiểm tra tên, nhãn, việc bắt đầu/kết thúc và scope còn sót. Xem [Micrometer Observation — Testing](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html). Bài thực hành hiện tại dùng stdout có thứ tự xác định để nhìn trực tiếp các vai trò, không cần đoán thời gian xử lý.

Sau bài này, người học cần giải thích được một lần checkout đi qua registry nào, mang context nào, được handler nào hỗ trợ và ai chịu trách nhiệm đóng scope/dừng observation. Bốn câu trả lời đó giúp chẩn đoán phần lớn trường hợp “mã chạy nhưng không thấy dữ liệu quan sát”.
