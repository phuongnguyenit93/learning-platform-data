# Xử lý khởi tạo thất bại, phụ thuộc vòng và tác dụng phụ

Khởi tạo lười (lazy initialization) giúp ứng dụng chỉ tạo một giá trị khi thật sự cần. Cách làm này có thể giảm thời gian khởi động và tránh tạo những thành phần không bao giờ được sử dụng. Nhưng nó cũng chuyển một phần lỗi từ thời điểm khởi động sang thời điểm truy cập đầu tiên. Nếu hàm khởi tạo thất bại, có phụ thuộc vòng hoặc thực hiện tác dụng phụ, hành vi của holder sẽ ảnh hưởng trực tiếp đến độ tin cậy của ứng dụng.

Java 25 giới thiệu **Stable Values** qua **JEP 502** dưới dạng preview API `StableValue<T>`. Sau đó, thiết kế được đổi tên thành **Lazy Constants**: JDK 26 có JEP 526 (preview lần hai), và JDK 27 hiện hành có JEP 531 (preview lần ba), với API `LazyConstant<T>`. Vì vậy, cần phân biệt hai thế hệ API và đặc biệt chú ý rằng **quy tắc xử lý lỗi đã thay đổi giữa JDK 26 và JDK 27**.

Bài thuộc chương **Stable Values** của module **JAVA_VERSION_JAVA25**, theo đề bài **xử lý khởi tạo thất bại, phụ thuộc vòng và tác dụng phụ**. Bài giải thích Stable Values trong đúng ngữ cảnh Java 25, đồng thời lấy `LazyConstant` của JDK 27 làm mốc hiện hành để đánh giá cách thiết kế ứng dụng. `StableValue` của Java 25 là preview API theo phiên bản; không dùng tên hoặc ví dụ đó như API hiện hành trên JDK 26/27.

> **Điểm cần nhớ:** Java 25 `StableValue` để giá trị ở trạng thái chưa đặt nếu supplier thất bại, nên lần truy cập sau có thể thử lại. JDK 27 `LazyConstant` chuyển sang trạng thái lỗi vĩnh viễn sau lần khởi tạo thất bại. Với supplier có side effect, khác biệt này có thể quyết định việc một request tạo tài nguyên một lần hay lặp lại side effect.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích Stable Value/Lazy Constant là holder có nội dung được thiết lập tối đa một lần.
2. Phân biệt trạng thái chưa khởi tạo, đã khởi tạo và trạng thái lỗi.
3. Giải thích chính xác hành vi khi supplier ném unchecked exception ở Java 25, 26 và 27.
4. Nhận biết vì sao retry sau khởi tạo thất bại có thể lặp lại tác dụng phụ.
5. Hiểu cách JDK 27 ghi nhận trạng thái lỗi và vì sao `get()` tiếp theo không thử lại.
6. Nhận diện đệ quy trực tiếp, phụ thuộc vòng giữa các constant và vòng khởi tạo class.
7. Thiết kế dependency graph không có chu trình.
8. Biết vì sao `null` không phải kết quả hợp lệ của `LazyConstant` và khi nào dùng `Optional`.
9. Hiểu an toàn luồng, safe publication, blocking, interruption và giới hạn timeout.
10. Quyết định loại công việc nào phù hợp để khởi tạo lười.
11. Phân biệt API Java 25 `StableValue` với API JDK 27 `LazyConstant`.
12. Viết kiểm thử cho lỗi khởi tạo, retry, recursion, side effect và truy cập đồng thời.

## 2. Stable Value và Lazy Constant là gì?

Một stable value là holder có nội dung được đặt tối đa một lần. Khi nội dung đã được đặt, tham chiếu đó không thể đổi sang một nội dung khác. Tính chất này cho phép JVM xem nội dung đã khởi tạo như một giá trị ổn định, có tiềm năng áp dụng các tối ưu tương tự `final`.

Một lazy constant là biến thể khởi tạo lười: ứng dụng cung cấp hàm tính toán khi tạo holder; hàm chỉ chạy khi lần đầu có người yêu cầu nội dung. Nếu tính toán thành công, kết quả được giữ lại và các lần truy cập sau trả về cùng nội dung.

~~~mermaid
stateDiagram-v2
    [*] --> Uninitialized
    Uninitialized --> Computing: lần truy cập đầu tiên
    Computing --> Initialized: tính toán thành công
    Computing --> Failed: tính toán thất bại (JDK 27)
    Initialized --> Initialized: truy cập tiếp theo trả nội dung
    Failed --> Failed: truy cập tiếp theo báo lỗi, không tính lại
~~~

Sơ đồ trên mô tả trạng thái của `LazyConstant` trong JDK 27. Với `StableValue` Java 25, supplier thất bại không đặt nội dung; holder vẫn chưa được khởi tạo và lần gọi tiếp theo có thể chạy supplier lần nữa.

### 2.1. Shallow immutability

Nội dung của Lazy Constant là **shallowly immutable**: tham chiếu được giữ trong holder không thay đổi sau khi khởi tạo, nhưng object được tham chiếu vẫn có thể mutable.

Ví dụ:

~~~java
import java.lang.LazyConstant;
import java.util.ArrayList;
import java.util.List;

static final LazyConstant<List<String>> NAMES =
        LazyConstant.of(ArrayList::new);
~~~

Sau khi khởi tạo, tham chiếu `NAMES` luôn trỏ đến cùng một `ArrayList`, nhưng danh sách vẫn có thể bị thêm hoặc xóa phần tử. Stable holder không tự biến object bên trong thành immutable và không thay thế đồng bộ hóa cho các thao tác mutable.

Nếu muốn giá trị thật sự ổn định, hãy ưu tiên object immutable, defensive copy hoặc API chỉ đọc.

## 3. API thay đổi theo từng JDK

Tên và semantics đã thay đổi trong các vòng preview. Đây là phần quan trọng khi đọc ví dụ trên Internet hoặc nâng cấp JDK.

| Release | JEP / tên API | Quy tắc khi supplier thất bại |
|---|---|---|
| Java 25 | JEP 502 — Stable Values, `StableValue<T>` | Exception được truyền cho caller; nội dung chưa được đặt; lần truy cập sau có thể thử lại |
| Java 26 | JEP 526 — Lazy Constants, `LazyConstant<T>` | Supplier thất bại thì holder vẫn chưa khởi tạo; lần `get()` sau có thể thử lại |
| Java 27 | JEP 531 — Lazy Constants, `LazyConstant<T>` | Holder chuyển sang trạng thái lỗi; các lần `get()` sau không chạy supplier lại |

JDK 27 đã phát hành GA ngày 15-09-2026. Lazy Constants vẫn là preview API ở JDK 27; cần bật preview khi biên dịch và chạy.

### 3.1. Khác biệt API cần nhớ

- Java 25 dùng `StableValue.of()`, `orElseSet()`, `trySet()`, `setOrThrow()` và các factory stable supplier/function/collection.
- JDK 26 đổi tên API thành `LazyConstant.of(Supplier)` và dùng `get()` để khởi tạo hoặc đọc nội dung.
- JDK 27 tiếp tục dùng `LazyConstant.of(Supplier)` và `get()`. Một số method quan sát/truy cập có trong preview JDK 26, chẳng hạn `isInitialized()` và `orElse()`, không còn trong API JDK 27.

Đừng chép ví dụ Java 25 hoặc JDK 26 rồi mặc định nó sẽ biên dịch trên JDK 27. Hãy kiểm tra Javadoc của đúng JDK mục tiêu.

## 4. Khởi tạo thất bại trong Java 25 StableValue

Trong Java 25, `StableValue.orElseSet(Supplier)` cố gắng tính toán và đặt nội dung nếu holder chưa có giá trị. Nếu supplier hoàn tất thành công, nội dung được đặt và không thể thay đổi. Nếu supplier ném unchecked exception, exception được truyền cho caller và không có nội dung nào được đặt.

Điều này có nghĩa lần truy cập tiếp theo có thể thử lại.

~~~java
import java.lang.StableValue;
import java.util.concurrent.atomic.AtomicInteger;

class StableValueRetryExample {

    private static final AtomicInteger ATTEMPTS = new AtomicInteger();

    private static final StableValue<String> CONFIG =
            StableValue.of();

    static String loadConfig() {
        int attempt = ATTEMPTS.incrementAndGet();

        if (attempt == 1) {
            throw new IllegalStateException("Temporary config error");
        }

        return "config-loaded";
    }

    static String config() {
        return CONFIG.orElseSet(StableValueRetryExample::loadConfig);
    }

    public static void main(String[] args) {
        try {
            config();
        } catch (IllegalStateException ex) {
            System.out.println("first attempt failed");
        }

        System.out.println(config());
        System.out.println("attempts=" + ATTEMPTS.get());
    }
}
~~~

Kết quả dự kiến:

~~~text
first attempt failed
config-loaded
attempts=2
~~~

Lần đầu supplier ném exception nên `CONFIG` vẫn chưa có nội dung. Lần thứ hai supplier chạy lại và thành công. Khi đã đặt giá trị, các lần gọi sau trả về nội dung đã lưu.

**Chú ý:** Javadoc bảo đảm supplier của `orElseSet` được gọi thành công tối đa một lần; nếu supplier ném exception thì nội dung không được đặt. Không diễn giải điều này thành “supplier chỉ được gọi đúng một lần trong mọi trường hợp”.

### 4.1. Tác dụng phụ có thể bị lặp lại

Giả sử supplier thực hiện các bước:

1. Tạo thư mục dữ liệu.
2. Đăng ký một resource với service quản lý.
3. Đọc file cấu hình.
4. Xây dựng object.
5. Trả object cho StableValue.

Nếu bước 4 thất bại, holder không được đặt. Lần gọi sau có thể thực hiện lại từ đầu. Thư mục hoặc đăng ký resource từ lần đầu có thể vẫn còn.

Đó là lý do supplier của StableValue Java 25 nên có tác dụng phụ tối thiểu, hoặc các tác dụng phụ phải idempotent và có cleanup rõ ràng.

## 5. Khởi tạo thất bại trong LazyConstant JDK 27

JDK 27 thay đổi semantics: nếu computing function ném unchecked exception, Lazy Constant chuyển sang trạng thái lỗi.

- Lần `get()` đầu tiên ném `NoSuchElementException`, có cause là exception gốc.
- Các lần `get()` sau tiếp tục ném `NoSuchElementException`.
- Supplier không được gọi lại.
- Các lần lỗi sau không giữ cause gốc; message cho biết loại exception xảy ra trong lần tính toán ban đầu.

Điều này khiến Lazy Constant phù hợp với giá trị có phép tính ổn định, xác định và không nên thử lại trong cùng vòng đời holder.

~~~java
import java.lang.LazyConstant;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

class LazyConstantFailureExample {

    private static final AtomicInteger ATTEMPTS = new AtomicInteger();

    private static final LazyConstant<String> CONFIG =
            LazyConstant.of(() -> {
                ATTEMPTS.incrementAndGet();
                throw new IllegalStateException("Invalid bundled config");
            });

    public static void main(String[] args) {
        for (int i = 1; i <= 3; i++) {
            try {
                CONFIG.get();
            } catch (NoSuchElementException ex) {
                System.out.println(
                        "get #" + i
                        + ", cause=" + ex.getCause()
                        + ", attempts=" + ATTEMPTS.get());
            }
        }
    }
}
~~~

Lần đầu `get()` tạo trạng thái lỗi. Các lần tiếp theo không gọi supplier nữa; `ATTEMPTS` vẫn bằng 1. Cause của lỗi ban đầu chỉ có ở exception đầu tiên, vì vậy cần ghi log hoặc phát cảnh báo khi lần khởi tạo đầu tiên thất bại.

### 5.1. `null` cũng là lỗi khởi tạo

LazyConstant không cho phép nội dung là `null`. Nếu computing function trả về `null`, holder chuyển sang trạng thái lỗi và lần `get()` đầu tiên ném `NoSuchElementException` với cause là `NullPointerException`.

Nếu một giá trị hợp lệ có thể “không tồn tại”, hãy biểu diễn kết quả bằng `Optional<T>`:

~~~java
static final LazyConstant<Optional<FeatureConfig>> FEATURE =
        LazyConstant.of(() -> findFeatureConfig());
~~~

Supplier luôn trả về một `Optional` khác null, trong đó `Optional.empty()` biểu diễn trường hợp không có cấu hình. Không dùng `null` để biểu diễn trạng thái chưa khởi tạo hoặc trạng thái lỗi.

### 5.2. Không có thao tác reset

LazyConstant không cung cấp thao tác xóa nội dung hoặc khôi phục từ trạng thái lỗi. Sau khi khởi tạo thành công, nội dung không thể đổi; sau khi thất bại trên JDK 27, holder giữ trạng thái lỗi.

Nếu cấu hình cần reload, credential có thể rotate hoặc dependency có thể phục hồi sau lỗi mạng, hãy dùng một cơ chế quản lý trạng thái có thể thay thế/reload được. Không đặt một giá trị cần thay đổi trong suốt vòng đời process vào LazyConstant chỉ vì nó được khởi tạo lười.

## 6. So sánh semantics lỗi giữa Java 25 và JDK 27

| Tình huống | StableValue Java 25 | LazyConstant JDK 27 |
|---|---|---|
| Supplier thành công | Đặt nội dung; lần sau dùng lại | Đặt nội dung; lần sau dùng lại |
| Supplier ném unchecked exception | Truyền exception; holder vẫn chưa đặt | Chuyển sang trạng thái lỗi |
| Lần truy cập tiếp theo | Có thể chạy supplier lại | Không chạy supplier lại |
| Nhiều thread cùng truy cập | Các lần tính toán được phối hợp; chỉ có tối đa một lần thành công | Một thread chạy computing function; thread khác chờ kết quả hoặc trạng thái lỗi |
| Supplier trả `null` | Không nên dùng `null` làm trạng thái nghiệp vụ | Không hợp lệ; chuyển sang trạng thái lỗi |
| Đệ quy trực tiếp | `IllegalStateException` | `NoSuchElementException`, cause là `IllegalStateException` |
| Chu trình dependency | Có thể phát hiện và ném `IllegalStateException` | Recursive initialization tạo trạng thái lỗi; chu trình static class init còn chịu quy tắc JLS |

Điểm khác biệt lớn nhất là **retry**. Java 25 để caller quyết định thử lại bằng cách gọi lại supplier thông qua holder chưa được đặt. JDK 27 coi lần tính toán thất bại là kết quả cuối cùng của holder.

## 7. Phụ thuộc vòng: vì sao dependency graph phải có hướng rõ ràng?

Lazy initialization cho phép object chỉ được tạo khi cần, nhưng không tự giải quyết dependency cycle. Hãy hình dung:

- `A` cần `B` để khởi tạo.
- `B` lại cần `A` để khởi tạo.

Khi `A` bắt đầu tạo `B`, constructor của `B` truy cập lại `A` trong lúc `A` chưa hoàn tất. Đây là một chu trình trong dependency graph.

~~~mermaid
flowchart TD
    A["A cần B"] --> B["B cần C"]
    B --> C["C cần A"]
    C --> A
    D["Chu trình A → B → C → A"] -.-> E["Khởi tạo đệ quy / lỗi"]
~~~

Một dependency graph có thể được khởi tạo theo thứ tự an toàn khi nó là **directed acyclic graph (DAG)**: không có đường đi nào quay lại node ban đầu. Nếu graph có chu trình, việc truy cập các giá trị trong chu trình có thể kích hoạt recursive initialization.

### 7.1. Ví dụ chu trình A → B → A trên JDK 27

~~~java
import java.lang.LazyConstant;

class CircularLazyConstants {

    static final LazyConstant<A> A_VALUE =
            LazyConstant.of(A::new);

    static final LazyConstant<B> B_VALUE =
            LazyConstant.of(B::new);

    static final class A {
        A() {
            B_VALUE.get();
        }
    }

    static final class B {
        B() {
            A_VALUE.get();
        }
    }

    public static void main(String[] args) {
        A_VALUE.get();
    }
}
~~~

Diễn biến:

1. `A_VALUE.get()` bắt đầu tạo `A`.
2. Constructor `A` gọi `B_VALUE.get()`.
3. `B_VALUE.get()` bắt đầu tạo `B`.
4. Constructor `B` gọi lại `A_VALUE.get()`.
5. `A_VALUE` đang được tính toán trên cùng call path, nên recursive initialization bị phát hiện.
6. JDK 27 báo `NoSuchElementException` với cause `IllegalStateException`; các Lazy Constant tham gia chuỗi thất bại có thể chuyển sang trạng thái lỗi.

Không bắt `NoSuchElementException` rồi tiếp tục dùng object một phần. Hãy sửa dependency graph.

### 7.2. Tách chu trình bằng một abstraction thứ ba

Nếu `A` và `B` cần thông tin của nhau, hãy xác định phần dữ liệu chung và chuyển nó sang một thành phần độc lập:

~~~mermaid
flowchart TD
    C["Shared contract / configuration"] --> A["A"]
    C --> B["B"]
    A --> S["Application service"]
    B --> S
~~~

Ví dụ, thay vì để `A` gọi `B` trong constructor và `B` gọi ngược `A`, có thể:

- Tạo `SharedConfiguration` độc lập.
- Đưa interface cần thiết vào constructor.
- Chuyển thao tác phối hợp sang service điều phối.
- Chỉ truy cập Lazy Constant sau khi các dependency cần thiết đã sẵn sàng.

Constructor nên nhận dependency đã được tạo, không nên kích hoạt cả một chuỗi khởi tạo ngược qua global singleton.

### 7.3. Chu trình lazy và chu trình khởi tạo class là hai vấn đề liên quan nhưng khác nhau

Java có quy tắc khởi tạo class/interface trong JLS `12.4`. Việc dùng lazy holder trong static field không xóa bỏ các quy tắc đó.

Một chu trình truy cập Lazy Constant có thể dẫn tới recursive initialization và trạng thái lỗi của holder. Một chu trình giữa static initializers của class có thể gây lỗi khởi tạo class như `ExceptionInInitializerError`; các lần truy cập sau có thể gặp `NoClassDefFoundError`.

Vì vậy:

- Không gọi `LazyConstant.get()` trong static initializer nếu dependency graph chưa rõ.
- Không để constructor của component kích hoạt ngược static singleton khác.
- Tránh thực hiện I/O, gọi framework container hoặc truy cập service toàn cục trong static initializer.
- Kiểm thử thứ tự khởi tạo bằng một process/JVM mới; class đã khởi tạo hoặc holder đã lỗi không thể được reset trong cùng classloader theo cách thông thường.

## 8. Tác dụng phụ trong computing function

Một computing function có thể tạo file, mở connection, đăng ký listener, đọc secret, gọi HTTP hoặc ghi database. Những hành động này có thể xảy ra ngay trong lần truy cập đầu tiên, trên thread gọi `get()`.

Lazy Constant chỉ quản lý kết quả và trạng thái khởi tạo. Nó không cung cấp transaction, rollback, retry policy hoặc cleanup cho các side effect.

### 8.1. Tác dụng phụ thất bại một phần

Ví dụ supplier thực hiện:

1. Tạo thư mục cache.
2. Ghi file tạm.
3. Đăng ký resource với hệ thống bên ngoài.
4. Parse file và xây dựng object.
5. Trả object.

Nếu bước 4 ném exception:

- Với StableValue Java 25, lần gọi tiếp theo có thể chạy lại supplier, nên các bước 1–3 có nguy cơ lặp.
- Với LazyConstant JDK 27, holder chuyển sang trạng thái lỗi và không thử lại, nhưng các side effect từ bước 1–3 vẫn có thể đã xảy ra.

Không phiên bản nào tự động xóa file, hủy registration hoặc rollback database.

### 8.2. Thiết kế supplier ít side effect

Ưu tiên computing function có các đặc tính:

- Đầu vào ổn định và có thể xác định trước.
- Kết quả được tạo từ dữ liệu local/immutable.
- Không gửi email, thanh toán, tạo đơn hàng hoặc publish message.
- Không ghi database chỉ để tạo một object dùng chung.
- Có thể cleanup tài nguyên tạm nếu khởi tạo thất bại.
- Không giữ một transaction mở trong lúc chờ các thread khác truy cập holder.

Ví dụ phù hợp là biên dịch một regular expression, parse một schema nằm trong artifact hoặc xây dựng lookup table từ hằng số.

~~~java
import java.lang.LazyConstant;
import java.util.regex.Pattern;

final class EmailPatterns {

    private static final LazyConstant<Pattern> EMAIL =
            LazyConstant.of(() ->
                    Pattern.compile(
                            "^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+$"));

    static Pattern email() {
        return EMAIL.get();
    }
}
~~~

Đây là phép tính xác định, không gọi hệ thống bên ngoài và không thực hiện side effect nghiệp vụ. Nếu pattern sai, holder chuyển sang trạng thái lỗi; lỗi này nên được phát hiện trong test hoặc startup validation nếu ứng dụng không thể hoạt động thiếu pattern.

### 8.3. Khi supplier cần mở tài nguyên

Nếu thật sự cần tạo một resource như client hoặc pool:

1. Chỉ mở resource khi lần đầu cần.
2. Nếu bước khởi tạo tiếp theo thất bại, đóng resource đã mở.
3. Chỉ trả resource sau khi nó ở trạng thái sử dụng được.
4. Xác định ai sở hữu và đóng resource khi ứng dụng shutdown.
5. Không để LazyConstant giữ một resource có lifecycle cần reload hoặc rotate.
6. Đảm bảo cleanup an toàn khi có exception.

LazyConstant giữ tham chiếu mạnh đến nội dung sau khi thành công. Một connection pool hoặc client lớn có thể sống suốt vòng đời classloader. Hãy cân nhắc memory retention và lifecycle rõ ràng trước khi lưu resource dài hạn.

## 9. Side effect và idempotency

Một operation idempotent có thể được thực hiện nhiều lần mà kết quả nghiệp vụ vẫn như một lần thực hiện. Đây là thuộc tính hữu ích khi supplier có khả năng được thử lại.

Ví dụ:

- Tạo thư mục với thao tác chấp nhận thư mục đã tồn tại.
- Ghi file cấu hình theo tên/version xác định và thay thế nguyên tử.
- Đăng ký resource bằng một key duy nhất có thể kiểm tra trạng thái trước.
- Dùng idempotency key khi gọi API bên ngoài.

Nhưng idempotency không thay thế cleanup. Một thao tác có thể idempotent về dữ liệu cuối cùng nhưng vẫn tạo thêm log, metrics, audit records hoặc chi phí request.

### 9.1. Không dùng lazy holder để đảm bảo exactly once cho nghiệp vụ

Giả sử supplier gọi payment API rồi tạo object receipt. Nếu API đã nhận payment nhưng kết nối bị ngắt trước khi client nhận response, supplier có thể thất bại dù side effect đã hoàn tất.

- StableValue Java 25 có thể thử lại, dẫn tới thanh toán trùng nếu API không idempotent.
- LazyConstant JDK 27 không thử lại, nhưng vẫn có thể giữ trạng thái lỗi dù payment đã thành công.

Để đảm bảo tính đúng đắn, cần idempotency key, trạng thái giao dịch được lưu bền, kiểm tra kết quả qua API nghiệp vụ và reconciliation. Lazy holder không thay thế transaction hoặc distributed workflow.

## 10. Tính toán thất bại tạm thời: có nên dùng LazyConstant?

Không nên đặt một dependency dễ thất bại tạm thời vào LazyConstant nếu ứng dụng cần tự thử lại sau đó.

Ví dụ không phù hợp:

~~~java
static final LazyConstant<RemoteConfig> CONFIG =
        LazyConstant.of(() -> httpClient.fetchConfig());
~~~

Nếu lần gọi đầu tiên gặp timeout hoặc service chưa sẵn sàng, LazyConstant trên JDK 27 chuyển sang trạng thái lỗi. Các request sau không tự gọi HTTP lại.

Các trường hợp thường cần retry:

- Database tạm thời không sẵn sàng.
- Secret manager chưa phản hồi.
- Remote configuration service đang khởi động.
- DNS/network có sự cố.
- Credential hoặc certificate đang được rotate.
- Resource phụ thuộc vào trạng thái hệ thống bên ngoài.

Dùng service method hoặc cache có chính sách retry, backoff, timeout, circuit breaker và refresh phù hợp. Nếu vẫn dùng LazyConstant, có thể đặt một retry policy hữu hạn bên trong computing function; nếu mọi lần thử đều thất bại, holder vẫn chuyển sang trạng thái lỗi trên JDK 27.

### 10.1. Không cố reset bằng cách gọi get() lại

Trên JDK 27, `get()` tiếp theo không chạy computing function lần nữa. Bắt `NoSuchElementException` rồi gọi `get()` lại chỉ nhận lỗi trạng thái.

Nếu cần thay đổi giá trị sau lỗi, hãy dùng một thành phần quản lý lifecycle có khả năng thay thế generation/holder, chẳng hạn một reference có thể cập nhật hoặc cơ chế reload của framework. Khi đó phải thiết kế đồng bộ hóa, cleanup và việc các request đang dùng giá trị cũ.

## 11. Truy cập đồng thời và an toàn luồng

Lazy Constant được thiết kế để khởi tạo an toàn khi nhiều thread cùng truy cập lần đầu:

- Một thread được chọn để chạy computing function.
- Các thread khác chờ kết quả khởi tạo hoặc trạng thái lỗi.
- Khi thành công, các thread quan sát cùng nội dung.
- Việc khởi tạo thành công happens-before các lần đọc nội dung thành công, giúp object được safe publication.

Điều này loại bỏ nhu cầu tự viết double-checked locking cho trường hợp phù hợp.

### 11.1. Supplier chạy trên thread của caller

Computing function chạy trên thread đầu tiên gọi `get()`, không tự động được đưa vào một background executor. Vì vậy, nếu supplier đọc file lớn hoặc gọi remote service, request đầu tiên có thể phải chờ.

Các thread khác truy cập cùng holder trong lúc đó cũng có thể bị block. Nếu computing function block vô thời hạn, các caller khác có thể block vô thời hạn.

### 11.2. Interruption không hủy initialization

Interruption không được LazyConstant dùng làm cơ chế cancellation cho computing function. Nếu thread computing bị interrupt, `get()` không tự xóa interrupt status và không ném `InterruptedException` chỉ vì interruption đó.

Nếu supplier gọi API blocking, hành vi interruption phụ thuộc API bên trong supplier. Không thiết kế request cancellation bằng cách kỳ vọng LazyConstant tự dừng phép khởi tạo.

### 11.3. Không có timeout tích hợp

LazyConstant không có API timeout hoặc cancellation cho lần khởi tạo. Nếu công việc có thể block, hãy đặt timeout tại API thực hiện công việc, hoặc không đặt công việc đó trong LazyConstant.

### 11.4. Không đồng bộ hóa trực tiếp trên holder

Implementation được phép đồng bộ hóa trên chính LazyConstant. Tránh dùng holder làm monitor:

~~~java
synchronized (CONFIG) {
    // Không dùng LazyConstant làm monitor
}
~~~

Nếu code khác cũng khóa tài nguyên theo thứ tự khác nhau, việc khóa trực tiếp hoặc gián tiếp trên holder có thể gây deadlock. Dùng lock riêng có ownership và thứ tự rõ ràng khi thật sự cần đồng bộ hóa.

## 12. Lazy Constant có phải immutable object không?

Không. Lazy Constant bảo đảm **nội dung của holder không đổi sau khi khởi tạo**; nó không đảm bảo object được lưu là immutable.

| Nội dung | Holder ổn định? | Object bên trong có thể mutable? |
|---|---|---|
| `String` | Có | Không |
| `Pattern` | Có | Không |
| `List.copyOf(...)` | Có | Danh sách không sửa được; phần tử tùy kiểu |
| `ArrayList` | Có | Có |
| `HashMap` | Có | Có |
| Connection pool | Có | Có, có lifecycle riêng |
| Mutable configuration bean | Có | Có |

Nếu lưu mutable object, mọi thread có thể đọc cùng một instance. Các thao tác thay đổi nội dung cần cơ chế thread safety riêng. Không dựa vào safe publication của LazyConstant để suy ra mọi thao tác về sau trên object đã an toàn.

### 12.1. Rủi ro giữ tài nguyên lâu dài

LazyConstant giữ tham chiếu mạnh đến nội dung. Nếu holder nằm trong static final field, nội dung có thể sống suốt vòng đời classloader.

Không dùng nó cho:

- Cache theo user/request có thể tăng vô hạn.
- Session hoặc authentication context.
- Dữ liệu tenant có thể thay đổi.
- Credential cần rotate.
- Connection cần đóng/reopen theo lifecycle.
- Object chứa file handle hoặc native memory mà không có cleanup.
- Cấu hình cần refresh nóng.

## 13. Áp dụng trong ứng dụng Spring Boot

Trong ứng dụng Spring Boot, dependency graph thường đã được quản lý bởi IoC container. Hãy dùng constructor injection để thể hiện dependency rõ ràng và để Spring quản lý lifecycle của bean.

Không dùng LazyConstant để che giấu vòng phụ thuộc giữa hai Spring beans. Việc trì hoãn truy cập có thể khiến lỗi chỉ xuất hiện ở request đầu tiên, xa thời điểm application context được khởi tạo và kiểm tra.

Một số trường hợp có thể phù hợp:

- Parse một schema bất biến được đóng gói trong application artifact.
- Biên dịch một regular expression dùng chung.
- Xây lookup table xác định từ hằng số.
- Tạo object tính toán thuần, không phụ thuộc request hoặc môi trường thay đổi.

Các trường hợp cần cân nhắc kỹ:

- Tạo DataSource, HTTP client hoặc connection pool có lifecycle.
- Load secret/configuration từ hệ thống bên ngoài.
- Gọi API từ bean constructor hoặc lần truy cập đầu tiên.
- Tạo cache mutable có eviction/refresh.
- Gọi database hoặc phát message trong computing function.

Nếu bean phải được quản lý bởi Spring, hãy ưu tiên lifecycle của Spring (`@Lazy`, bean scopes, lifecycle callbacks, configuration properties) thay vì tạo một singleton song song nằm ngoài container.

### 13.1. Kiểm tra lỗi sớm khi ứng dụng cần giá trị bắt buộc

Nếu cấu hình là bắt buộc để service hoạt động, lazy initialization có thể đẩy lỗi từ startup sang request đầu tiên. Hãy chủ động gọi `get()` trong startup validation hoặc dùng khởi tạo eager. Điều này làm lỗi xuất hiện gần thời điểm triển khai và tránh request đầu tiên chịu chi phí khởi tạo.

## 14. Quan sát và ghi log lỗi khởi tạo

Với JDK 27, exception đầu tiên của LazyConstant có cause gốc; các lần `get()` tiếp theo không giữ cause đó. Vì vậy, cần ghi nhận lỗi ở lần truy cập đầu tiên.

Nên log:

- Tên thành phần hoặc constant có vấn đề.
- Operation đang kích hoạt khởi tạo.
- Exception/cause của lần đầu.
- JDK version và build.
- Correlation ID nếu khởi tạo xảy ra trong request.
- Thời gian khởi tạo và loại dependency.
- Trạng thái cleanup nếu có resource được mở trước khi thất bại.

Không log token, password, private key hoặc raw configuration secret. Không dùng nội dung nhạy cảm làm tên Lazy Constant.

### 14.1. Phân biệt lỗi supplier với lỗi nghiệp vụ sau khởi tạo

Nếu `get()` thành công và trả về object, nhưng một method của object thất bại sau đó, LazyConstant vẫn ở trạng thái initialized. Nó không quan sát hoặc ghi nhớ lỗi của những method được gọi trên object.

Ví dụ `CONFIG.get()` tạo thành công một client; request tiếp theo gọi `client.fetch()` bị timeout. Đây là lỗi hoạt động của client, không phải lỗi khởi tạo LazyConstant. Cần xử lý bằng timeout/retry/circuit breaker của client.

## 15. Kiểm thử failure, cycle và side effects

Không chỉ kiểm tra trường hợp supplier thành công. Hãy viết test cho các trạng thái và các đường lỗi.

| Kiểm thử | Câu hỏi cần xác minh |
|---|---|
| Supplier thành công | Lần truy cập đầu tạo nội dung; lần sau trả cùng nội dung? |
| Hai thread cùng truy cập | Computing function có chỉ chạy một lần? |
| Supplier ném exception | Holder có chuyển sang trạng thái lỗi theo JDK đích? |
| Gọi lại sau lỗi | JDK 27 có tránh chạy supplier lần nữa? |
| Supplier trả null | Có báo lỗi đúng và không giữ null? |
| Supplier gọi lại chính holder | Có phát hiện recursion? |
| Hai holder phụ thuộc vòng | Có phát hiện chu trình trong dependency graph? |
| Supplier tạo resource rồi thất bại | Resource một phần có được cleanup? |
| Supplier block lâu | Các caller khác chờ ra sao? |
| Thread bị interrupt khi chờ | Interrupt status và kết quả được xử lý thế nào? |
| Object mutable | Các thao tác sau khởi tạo có thread-safe? |
| Holder static | Giá trị có bị giữ lâu hơn dự kiến? |

### 15.1. Kiểm thử số lần supplier chạy trên JDK 27

~~~java
import java.lang.LazyConstant;
import java.util.concurrent.atomic.AtomicInteger;

class LazyConstantCallsTest {

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        LazyConstant<String> value = LazyConstant.of(() -> {
            calls.incrementAndGet();
            return "ready";
        });

        String first = value.get();
        String second = value.get();

        if (!first.equals(second) || calls.get() != 1) {
            throw new AssertionError("Unexpected initialization count");
        }
    }
}
~~~

Bài test này xác nhận supplier thành công chỉ chạy một lần trong trường hợp truy cập tuần tự. Cần thêm test đồng thời để xác minh nhiều thread cùng truy cập lần đầu.

### 15.2. Kiểm thử lỗi không retry trên JDK 27

~~~java
import java.lang.LazyConstant;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

class LazyConstantNoRetryTest {

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        LazyConstant<String> value = LazyConstant.of(() -> {
            calls.incrementAndGet();
            throw new IllegalStateException("broken");
        });

        for (int i = 0; i < 2; i++) {
            try {
                value.get();
                throw new AssertionError("Expected failure");
            } catch (NoSuchElementException expected) {
                // First call has the original cause.
                // Later calls report the already failed constant.
            }
        }

        if (calls.get() != 1) {
            throw new AssertionError("Supplier must not be retried");
        }
    }
}
~~~

Không kiểm tra chỉ bằng message của exception vì message có thể thay đổi. Hãy kiểm tra kiểu exception, cause ở lần đầu và số lần supplier được gọi.

## 16. Quyết định có nên dùng LazyConstant không

| Loại giá trị | Có phù hợp? | Lý do |
|---|---|---|
| Regex hoặc parser được xây từ hằng số | Phù hợp | Tính toán thuần, ổn định |
| Schema đóng gói trong artifact | Có thể phù hợp | Đầu vào bất biến, cần phát hiện lỗi sớm |
| Lookup table được tính từ dữ liệu bất biến | Phù hợp | Kết quả ổn định sau khi tạo |
| Remote config có thể tạm thời không truy cập được | Không phù hợp | JDK 27 ghi nhận lỗi vĩnh viễn |
| Token hoặc credential có thể rotate | Không phù hợp | Nội dung cần thay thế |
| Cache cần eviction/refresh | Không phù hợp | Nội dung holder không thể reset |
| Tạo đơn hàng hoặc thanh toán | Không phù hợp | Side effect không có rollback/idempotency tự động |
| Connection pool có lifecycle phức tạp | Cần cân nhắc | Cleanup, shutdown và reload phải rõ |
| Request-scoped data | Không phù hợp | Dữ liệu không phải constant dùng chung |
| Component Spring do container quản lý | Thường không cần | Spring đã có cơ chế lifecycle và dependency graph |

Một câu hỏi hữu ích trước khi chọn LazyConstant: **nếu phép tính thất bại ở lần đầu, ứng dụng có thể chấp nhận holder này lỗi đến hết vòng đời hay không?** Nếu câu trả lời là không, hãy chọn một cơ chế khác.

## 17. Biên dịch và chạy theo đúng JDK

### 17.1. Java 25 — Stable Values (JEP 502)

StableValue là preview API trong Java 25. Biên dịch và chạy với đúng JDK 25, bật preview ở cả hai bước:

~~~bash
javac --release 25 --enable-preview -d out StableValueExample.java
java --enable-preview -cp out StableValueExample
~~~

Ví dụ dùng `StableValue`, `orElseSet`, `trySet` hoặc `setOrThrow` chỉ dành cho API Java 25. Không giả định các tên này còn tồn tại trong JDK 26/27.

### 17.2. JDK 27 — Lazy Constants (JEP 531)

Với API hiện hành trong JDK 27:

~~~bash
javac --release 27 --enable-preview -d out LazyConstantExample.java
java --enable-preview -cp out LazyConstantExample
~~~

JDK 27 là bản phát hành GA, nhưng Lazy Constants vẫn là preview API. Vì vậy vẫn phải bật `--enable-preview` ở compiler và JVM. Preview API có thể thay đổi hoặc bị loại bỏ ở release sau.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `StableValue` không tìm thấy trên JDK 27 | Tên API Java 25 đã được thay đổi | Dùng `LazyConstant` theo JDK 27 |
| `LazyConstant` không biên dịch | Thiếu preview flag hoặc JDK không đúng | Dùng JDK 27 và bật preview khi compile/run |
| Lần `get()` đầu ném `NoSuchElementException` | Computing function thất bại hoặc trả null | Xem cause của exception đầu tiên |
| Lần `get()` tiếp tục lỗi nhưng không có cause | Holder đã ở trạng thái lỗi | Điều tra log của lần khởi tạo đầu |
| Supplier không chạy lại | JDK 27 ghi nhận trạng thái lỗi | Không dựa vào `get()` để retry |
| Side effect xuất hiện dù khởi tạo thất bại | Supplier đã thực hiện một phần operation | Thêm cleanup, idempotency và transaction ở tầng nghiệp vụ |
| `IllegalStateException`/`NoSuchElementException` do recursion | Supplier truy cập lại chính holder | Phá chu trình dependency |
| `ExceptionInInitializerError` | Chu trình hoặc lỗi trong static initializer | Kiểm tra thứ tự khởi tạo class và loại bỏ side effect khỏi static initializer |
| Request đầu tiên bị treo | Supplier block trên thread gọi `get()` | Đặt timeout ở API bên trong hoặc bỏ lazy initialization |
| Các thread khác chờ lâu | Một thread đang tính toán holder | Đo thời gian supplier và tránh I/O không giới hạn |
| Không thể reload giá trị | LazyConstant không có reset | Dùng holder có thể thay thế hoặc cơ chế refresh |
| Heap giữ object quá lâu | Holder giữ tham chiếu mạnh đến nội dung | Tránh lưu request/session/resource ngắn hạn |
| Code dựa vào `isInitialized()` không chạy trên JDK 27 | API đã thay đổi giữa các preview | Kiểm tra Javadoc của đúng release |

## 19. Bài tập thực hành

**Bài 1 — Retry Java 25:** dùng StableValue.orElseSet với supplier ném exception ở lần đầu và thành công ở lần sau. Ghi số lần supplier được gọi và giải thích vì sao holder vẫn chưa được đặt sau lỗi.

**Bài 2 — Terminal failure JDK 27:** dùng LazyConstant với supplier luôn ném IllegalStateException. Gọi get() ba lần; ghi kiểu exception, cause và số lần supplier chạy.

**Bài 3 — Null result:** trả null từ computing function. Quan sát NoSuchElementException và cause; thay bằng Optional.empty() để biểu diễn trường hợp không có dữ liệu.

**Bài 4 — Recursion:** tạo LazyConstant mà supplier gọi lại get() trên chính holder. Quan sát trạng thái lỗi và cause.

**Bài 5 — Dependency cycle:** tạo hai class A/B có LazyConstant phụ thuộc lẫn nhau. Xác định chu trình và sửa thành dependency graph một chiều.

**Bài 6 — Side effect:** viết supplier tạo file tạm rồi ném exception. Chạy theo semantics Java 25 và JDK 27; quan sát số lần tạo file và thiết kế cleanup/idempotency.

**Bài 7 — Concurrency:** cho nhiều virtual threads gọi get() cùng lúc. Dùng AtomicInteger để xác nhận computing function thành công chỉ chạy một lần.

**Bài 8 — Blocking:** tạo computing function chờ một latch. Quan sát thread đầu tiên thực hiện computation và các caller còn lại chờ. Đánh giá ảnh hưởng khi một request gọi get() lần đầu.

**Bài 9 — Interruption:** interrupt thread đang chờ LazyConstant được khởi tạo. Kiểm tra interrupt status và giải thích vì sao holder không cung cấp cancellation.

**Bài 10 — Spring Boot:** tạo một component có dependency graph rõ ràng. So sánh Spring lazy bean với LazyConstant và quyết định cơ chế nào phù hợp với lifecycle của component.

**Bài 11 — Failure logging:** thiết kế cách ghi lại cause của lần khởi tạo đầu tiên và cảnh báo cho các request tiếp theo khi holder đã ở trạng thái lỗi.

**Bài 12 — Nâng cấp JDK:** chạy cùng bài tập failure trên Java 25, JDK 26 và JDK 27. Ghi lại sự khác nhau giữa retry và terminal error state.

## 20. Checklist hoàn thành

- [ ] Hiểu StableValue là preview API Java 25, không phải API hiện hành của JDK 27.
- [ ] Biết LazyConstant là tên API được giới thiệu từ JDK 26.
- [ ] Biết JDK 27 dùng JEP 531 — Lazy Constants (Third Preview).
- [ ] Phân biệt khởi tạo chưa đặt, đã đặt và trạng thái lỗi.
- [ ] Hiểu Java 25 có thể thử lại sau supplier failure.
- [ ] Hiểu JDK 27 chuyển LazyConstant sang trạng thái lỗi sau lần tính toán thất bại.
- [ ] Biết exception đầu tiên có cause, các lần truy cập sau không giữ cause gốc.
- [ ] Biết null không phải nội dung hợp lệ của LazyConstant.
- [ ] Nhận diện recursion và dependency cycle.
- [ ] Phân biệt chu trình LazyConstant với lỗi static class initialization.
- [ ] Không đặt side effect không idempotent trong supplier.
- [ ] Biết cleanup resource khi computing function thất bại.
- [ ] Không dùng LazyConstant cho dependency có lỗi tạm thời cần retry.
- [ ] Hiểu get() chạy computing function trên thread của caller.
- [ ] Hiểu interruption không hủy initialization và không có timeout tích hợp.
- [ ] Hiểu safe publication và giới hạn shallow immutability.
- [ ] Tránh giữ request/session/resource có lifecycle ngắn trong holder dài hạn.
- [ ] Dùng đúng preview flags của JDK 25 hoặc JDK 27.
- [ ] Có test cho failure, retry, cycle, side effect và concurrent access.

## Tài liệu tham khảo chính thức

- [JEP 502 — Stable Values (Preview)](https://openjdk.org/jeps/502): API StableValue được giới thiệu trong JDK 25.
- [Java SE 25 — StableValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StableValue.html): semantics orElseSet, supplier failure, dependency cycle, thread safety và stable collections.
- [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): đổi tên và điều chỉnh API trong JDK 26.
- [Java SE 26 — LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html): semantics retry khi computation thất bại ở JDK 26.
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): trạng thái và thay đổi Lazy Constants trong JDK 27.
- [Java SE 27 — LazyConstant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API of, get, terminal error state, recursion và thread safety.
- [Oracle JDK 27 — Lazy Constants](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): hướng dẫn lazy initialization, composition và circular dependency.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Lazy Constants là preview API trong JDK 27.
- [Java Language Specification — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se27/html/jls-12.html#jls-12.4): quy tắc khởi tạo class và các tình huống lỗi do thứ tự khởi tạo.

## Kết luận

**Xử lý lỗi khởi tạo cần dựa trên semantics của đúng JDK, vì retry và ghi nhận trạng thái lỗi có thể làm thay đổi tác dụng phụ của ứng dụng.** Java 25 StableValue để holder chưa được đặt khi supplier thất bại, nên lần truy cập sau có thể thử lại. JDK 27 LazyConstant chuyển sang trạng thái lỗi sau lần tính toán thất bại; `get()` tiếp theo không chạy supplier lần nữa.

Phụ thuộc vòng cần được loại bỏ bằng dependency graph có hướng rõ ràng. Supplier nên tránh side effect nghiệp vụ, phải cleanup tài nguyên khi thất bại và không được giả định holder sẽ rollback hoặc retry thay cho ứng dụng. LazyConstant phù hợp với phép tính ổn định, xác định và có thể giữ suốt vòng đời holder; dependency cần timeout, retry, reload hoặc transaction nên dùng cơ chế quản lý lifecycle riêng. **Hãy kiểm thử cả đường thành công lẫn thất bại trên đúng JDK trước khi bật preview API trong môi trường vận hành.**
