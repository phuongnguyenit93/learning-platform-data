# Quan hệ static final, constant folding và tối ưu truy cập

`static final` và *constant folding* thường được nhắc cùng nhau, nhưng chúng không đồng nghĩa. Một trường `static final` có thể giữ tham chiếu ổn định đến một object mà không phải là hằng compile-time. Với **Lazy Constants** trong Java 26, ứng dụng có thể trì hoãn việc tạo nội dung đến lần truy cập đầu tiên, sau đó cho JVM biết nội dung ấy không thể thay đổi. Khi cấu trúc tham chiếu đáp ứng điều kiện của API, JVM có thể tối ưu các lần đọc tiếp theo như đọc một hằng.

Chủ đề này thuộc chương Hằng khởi tạo trễ và gắn với mục tiêu tối ưu khởi động, khởi tạo object theo nhu cầu, đồng thời giữ khả năng tối ưu truy cập sau khi giá trị đã được tạo. Cần phân biệt rõ tối ưu ở compile time với tối ưu của JIT tại runtime.

## 1. `static final` không phải lúc nào cũng là hằng compile-time

Trong Java, một *constant variable* theo JLS là biến `final` có kiểu primitive hoặc `String`, được khởi tạo bằng một constant expression. Trường `static final` là cách khai báo phổ biến, nhưng điều kiện kiểu và biểu thức khởi tạo mới quyết định nó có phải constant variable hay không.

```java
static final int MAX_RETRIES = 3;
static final String DEFAULT_SCHEME = "https";

static final Integer RETRIES = Integer.valueOf(3);
static final URI ENDPOINT = URI.create("https://api.example.com");
static final Logger LOGGER = Logger.getLogger("application");
```

| Khai báo | Constant variable theo JLS? | Ý nghĩa |
| --- | --- | --- |
| `static final int MAX_RETRIES = 3` | Có | Primitive `final`, khởi tạo bằng constant expression |
| `static final String DEFAULT_SCHEME = "https"` | Có | `String final`, khởi tạo bằng constant expression |
| `static final Integer RETRIES = Integer.valueOf(3)` | Không | Wrapper object, không phải primitive hoặc `String` |
| `static final URI ENDPOINT = URI.create(...)` | Không | Giá trị được tính bằng lời gọi method lúc khởi tạo lớp |
| `static final Logger LOGGER = ...` | Không | Object reference được gán khi lớp khởi tạo |

Với constant variable, compiler có thể dùng giá trị hằng ngay tại nơi tham chiếu; class file của bên sử dụng có thể chứa giá trị đã được inline. Vì vậy, thay đổi giá trị `public static final` dạng constant variable trong thư viện rồi chỉ thay JAR mà không biên dịch lại consumer có thể để consumer tiếp tục dùng giá trị cũ.

Một trường `static final` tham chiếu object có ý nghĩa khác: sau khi trường được gán, reference không thể trỏ sang object khác, nhưng object mà nó trỏ đến vẫn có thể mutable. Trường đó không trở thành constant expression chỉ vì có từ khóa `final`. JIT vẫn có thể tối ưu một số truy cập final field khi đủ điều kiện, nhưng đó là tối ưu runtime và không giống việc javac inline constant variable.

## 2. Constant folding có hai ngữ cảnh

**Compile-time constant evaluation** xảy ra khi compiler có thể tính một constant expression theo JLS. Ví dụ:

```java
static final int BUFFER_SIZE = 1024 * 8;
static final String API_PREFIX = "https" + "://api.example.com";
```

Các biểu thức này có thể được tính khi biên dịch vì chỉ dùng hằng hợp lệ. Chúng không cần đợi chương trình chạy.

**JIT constant folding** xảy ra khi JVM biên dịch mã nóng thành machine code. Nếu JVM chứng minh một giá trị không thay đổi, nó có thể thay các lần đọc lặp lại bằng giá trị đã biết, loại bỏ thao tác đọc qua bộ nhớ và mở đường cho các tối ưu tiếp theo. Đây là ngữ cảnh mà tài liệu `LazyConstant` dùng thuật ngữ *constant folding*.

Với Lazy Constant, supplier không được javac thực thi trước. Nội dung được tính lần đầu khi gọi `get()`. Sau khi nội dung đã được khởi tạo, JVM *có thể* tối ưu các lần đọc tương lai nếu reference đến Lazy Constant nằm trong cấu trúc được API cho phép. Việc tối ưu phụ thuộc implementation, JIT, profile và trạng thái biên dịch; API không bảo đảm mọi lần `get()` đều bị loại bỏ.

## 3. LazyConstant kết hợp khởi tạo trễ với tính ổn định

Từ JDK 26, Java cung cấp preview API `java.lang.LazyConstant<T>`. Đây là một holder có nội dung được gán tối đa một lần. `LazyConstant.of(Supplier)` tạo holder và lưu cách tính giá trị; lời gọi `get()` đầu tiên thực hiện phép tính, lưu kết quả và trả về. Các lần gọi sau nhận cùng nội dung đó.

```java
public class LazyConfigDemo {
    record Config(String endpoint) {
        static Config load() {
            System.out.println("Loading configuration...");
            return new Config("https://api.example.com");
        }
    }

    private static final LazyConstant<Config> CONFIG =
            LazyConstant.of(Config::load);

    static Config config() {
        return CONFIG.get();
    }

    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println(config().endpoint());
        System.out.println(config().endpoint());
    }
}
```

Kết quả minh họa:

```text
Application started
Loading configuration...
https://api.example.com
https://api.example.com
```

Trong ví dụ, khi lớp `LazyConfigDemo` được khởi tạo, JVM tạo LazyConstant và lưu supplier `Config::load`. `Config.load()` chưa chạy ở thời điểm đó. Nó chỉ chạy khi ứng dụng gọi `config()` lần đầu. Lần gọi tiếp theo nhận cùng `Config` đã được tạo.

Điểm quan trọng là **holder** và **nội dung** có thời điểm khởi tạo khác nhau:

1. Khởi tạo lớp: tạo trường `static final CONFIG` và LazyConstant chưa có nội dung.
2. Truy cập lần đầu: `CONFIG.get()` chạy supplier và lưu nội dung.
3. Truy cập tiếp theo: trả về nội dung đã lưu; supplier không chạy lại.
4. Sau khi nội dung ổn định: JVM có thể áp dụng constant folding nếu đường tham chiếu đáp ứng điều kiện tối ưu.

`static final` ở đây là một phần của cấu trúc tham chiếu mà JVM có thể tin cậy. Nó không có nghĩa `Config.load()` được tính tại compile time.

## 4. Vì sao static final là điểm neo cho constant folding?

JVM chỉ được phép coi nội dung LazyConstant là ổn định khi có thể chứng minh đường tham chiếu đến holder không bị thay đổi. Theo API Specification, constant folding có thể được áp dụng khi:

- Có tham chiếu trực tiếp từ một trường `static final` đến LazyConstant; hoặc
- Có một chuỗi tham chiếu bắt đầu từ trường `static final`, đi qua một hay nhiều trusted fields rồi đến LazyConstant.

Các trusted fields được API nêu rõ gồm:

- Trường `static final`.
- Các trường thành phần của `record` (record component fields).
- Trường instance `final` trong hidden class.

Ví dụ trực tiếp:

```java
static final LazyConstant<Config> CONFIG = LazyConstant.of(Config::load);

static String endpoint() {
    return CONFIG.get().endpoint();
}
```

Ví dụ có trusted chain qua record:

```java
record ConfigHolder(LazyConstant<Config> config) {}

static final ConfigHolder HOLDER =
        new ConfigHolder(LazyConstant.of(Config::load));

static String endpoint() {
    return HOLDER.config().get().endpoint();
}
```

Đường tham chiếu trong ví dụ thứ hai là `static final HOLDER` → record component `config` → `LazyConstant`. Record component là final field do record tạo ra, nên đây là một trusted chain được tài liệu API mô tả.

Không nên suy rộng rằng mọi trường instance `final` đều là trusted field. API nêu trường instance `final` của hidden class; trường instance `final` trong một class thông thường không tự động thuộc danh sách trusted fields cho điều kiện constant folding này.

Nếu reference LazyConstant được lưu trong trường có thể thay đổi, ví dụ:

```java
static LazyConstant<Config> currentConfig = LazyConstant.of(Config::load);
```

thì đường tham chiếu không còn có điểm neo `static final` như yêu cầu. LazyConstant vẫn giữ tính chất nội dung chỉ khởi tạo một lần và `get()` vẫn hoạt động, nhưng không thể dựa vào điều kiện constant folding nêu trên.

## 5. LazyConstant và static final eager initialization khác nhau thế nào?

| Cách lưu giá trị | Thời điểm tính nội dung | Có thể thay đổi nội dung sau khi tạo? | Cơ hội tối ưu |
| --- | --- | --- | --- |
| `static final` primitive/String constant variable | Compile time nếu là constant expression | Không | Compiler có thể inline giá trị; JIT có thể tối ưu tiếp |
| `static final` object reference | Khi lớp khởi tạo và initializer chạy | Reference không đổi; object có thể mutable | JIT có thể tối ưu final field khi đủ điều kiện |
| `static final LazyConstant<T>` | Khi `get()` đầu tiên | Holder không cho thay nội dung sau khi khởi tạo | JVM có thể constant-fold nội dung qua đường tham chiếu tin cậy |
| Trường mutable chứa LazyConstant | Khi `get()` đầu tiên | Nội dung LazyConstant vẫn chỉ khởi tạo một lần | Không đáp ứng điểm neo `static final` cho tối ưu được mô tả |

Ví dụ eager initialization:

```java
static final RoutingTable ROUTING_TABLE = RoutingTable.load();
```

`RoutingTable.load()` chạy khi lớp khai báo trường được khởi tạo. Nếu ứng dụng chỉ dùng routing table ở một luồng xử lý hiếm gặp, thời gian khởi tạo này có thể làm tăng startup hoặc làm công việc không cần thiết.

Ví dụ lazy initialization:

```java
static final LazyConstant<RoutingTable> ROUTING_TABLE =
        LazyConstant.of(RoutingTable::load);
```

Lớp chỉ tạo holder ban đầu; `RoutingTable.load()` chờ đến lần `get()` đầu tiên. Sau khi nội dung được tạo, holder vẫn giữ một giá trị ổn định và có thể đủ điều kiện để JIT tối ưu các lần truy cập sau.

## 6. Thread safety và an toàn công bố

LazyConstant đảm bảo khởi tạo nguyên tử và tối đa một lần. Nếu nhiều thread cùng gọi `get()` khi holder chưa được khởi tạo:

- Chỉ một thread được chọn để chạy computing function.
- Các thread còn lại chờ cho đến khi quá trình khởi tạo hoàn tất hoặc thất bại.
- Sau khi khởi tạo thành công, mọi thread nhận cùng nội dung.
- Việc chạy computing function và khởi tạo nội dung có quan hệ *happens-before* với lần đọc nội dung đã khởi tạo, nên object được safe publication, bao gồm các `final` fields của object mới tạo.

Supplier chạy trên thread được chọn để thực hiện lần khởi tạo, không phải một background executor do LazyConstant tự tạo. Nếu supplier chặn vô thời hạn, các thread đang chờ cùng holder cũng có thể chờ vô thời hạn. API không cung cấp timeout hoặc cancellation cho việc khởi tạo. Interrupt của computing thread không hủy quá trình khởi tạo và `get()` không ném `InterruptedException`.

Vì vậy, supplier nên có thời gian thực thi có thể dự đoán, tránh phụ thuộc vòng và không nên thực hiện công việc có thể treo vô thời hạn. Nếu nội dung cần I/O hoặc kết nối mạng, hãy cân nhắc rõ tác động khi thread đầu tiên truy cập phải chờ công việc đó.

## 7. Nội dung không đổi không đồng nghĩa object bất biến sâu

LazyConstant bảo đảm **nội dung được giữ trong holder không thể thay bằng nội dung khác** sau khi đã khởi tạo. Điều đó không tự làm object được giữ trở thành immutable.

Ví dụ:

```java
static final LazyConstant<List<String>> NAMES =
        LazyConstant.of(ArrayList::new);

static void addName(String name) {
    NAMES.get().add(name);
}
```

Reference đến `ArrayList` không đổi, nhưng các phần tử bên trong vẫn thay đổi. Vì thế không nên xem `LazyConstant<List<String>>` là immutable collection chỉ vì holder là lazy constant. LazyConstant cũng không tự đồng bộ hóa những lần sửa object sau khi công bố; nếu nhiều thread cùng thay đổi nội dung, object đó vẫn cần cơ chế thread safety riêng. Nếu cần dữ liệu bất biến, hãy tạo collection không sửa được hoặc dùng kiểu dữ liệu immutable phù hợp.

Đặt một array trong LazyConstant cũng chỉ làm ổn định reference đến array; nó không biến từng phần tử thành hằng và không tự tăng tốc việc đọc phần tử. Khi cần khởi tạo từng phần tử theo nhu cầu, hãy xem các lazy collection như `List.ofLazy(...)` thay vì kỳ vọng một `LazyConstant<T[]>` tối ưu nội dung array.

Khi nội dung đã được khởi tạo, LazyConstant giữ tham chiếu mạnh đến nó và không có thao tác reset hoặc clear. Nếu holder sống suốt vòng đời class loader, object được giữ cũng có thể sống suốt khoảng thời gian đó. Đưa cache lớn, object gắn với request hoặc tài nguyên cần đóng vào một static LazyConstant có thể gây giữ bộ nhớ ngoài dự kiến.

Một LazyConstant không phải `Serializable`. Sử dụng trong static initializer cũng cần chú ý thứ tự khởi tạo lớp; dependency vòng có thể gây lỗi khởi tạo. Ví dụ `A` tạo lazy `B`, trong constructor `B` lại gọi lazy `A`, sẽ tạo vòng tính toán đệ quy.

## 8. Hành vi lỗi và thay đổi API giữa JDK 26 và JDK 27

Lazy Constants vẫn là preview trong cả JDK 26 lẫn JDK 27, nhưng API đã có thay đổi. Không nên sao chép ví dụ của JDK 26 rồi giả định chúng compile nguyên trạng trên JDK 27.

| Nội dung | JDK 26 — JEP 526, Second Preview | JDK 27 — JEP 531, Third Preview |
| --- | --- | --- |
| Khởi tạo | `LazyConstant.of(Supplier)`; nội dung tính ở `get()` | Giữ mô hình `of` và `get` |
| Kiểm tra trạng thái | Có `isInitialized()` | Đã bỏ `isInitialized()` |
| Đọc nếu đã có nội dung | Có `orElse(other)` | Đã bỏ `orElse(other)` |
| Supplier ném unchecked exception | Exception được truyền cho caller; holder vẫn chưa khởi tạo và lần `get()` sau có thể thử lại | Holder chuyển sang error state; lần đầu ném `NoSuchElementException` có cause, các lần sau tiếp tục ném `NoSuchElementException` và không chạy supplier lại |
| Supplier trả `null` | Ném `NullPointerException`; holder không có nội dung | Chuyển sang error state và ném `NoSuchElementException` với `NullPointerException` làm cause |
| Factory nhận một LazyConstant làm Supplier | Implementation được phép trả lại LazyConstant đó | `of` luôn tạo LazyConstant mới |

Trong JDK 27, hãy thiết kế computing function sao cho lỗi là tình huống cần xử lý rõ ràng. Đừng dựa vào việc gọi `get()` lần nữa để thử lại sau một lỗi khởi tạo. Nếu cần retry, hãy đặt chính sách retry ở một tầng khác và tạo một lần thử/holder mới theo thiết kế của ứng dụng.

JDK 27 cũng bổ sung `Set.ofLazy(...)` trong nhóm lazy collections; `List.ofLazy(...)` và `Map.ofLazy(...)` đã có từ JDK 26. Đây là các API preview liên quan, không phải cách thay thế cho một `LazyConstant` đơn lẻ trong mọi trường hợp.

## 9. Bật preview trên JDK 26 và JDK 27

`LazyConstant` là preview API, không phải API permanent. Phải bật preview khi biên dịch và khi chạy, đồng thời dùng cùng phiên bản JDK cho hai bước.

Với JDK 26:

```bash
javac --enable-preview --release 26 -d out src/LazyConfigDemo.java
java --enable-preview -cp out LazyConfigDemo
```

Với JDK 27:

```bash
javac --enable-preview --release 27 -d out src/LazyConfigDemo.java
java --enable-preview -cp out LazyConfigDemo
```

Không biên dịch bằng JDK 26 rồi chạy class file preview đó trên JDK 27. Preview class file gắn với phiên bản phát hành đã biên dịch; khi nâng JDK, hãy đọc API Specification của bản đích và biên dịch lại. Mã dùng `isInitialized()` hoặc `orElse()` trong JDK 26 cần được sửa trước khi chuyển sang JDK 27.

## 10. Khi nào nên dùng và khi nào nên chọn cách ổn định?

Lazy Constants phù hợp để thử nghiệm khi ứng dụng có object dùng chung, chi phí tạo đáng kể, chỉ một phần luồng thực thi cần đến object và muốn giữ một nội dung ổn định sau lần tạo đầu tiên. Ví dụ gồm bảng định tuyến, parser/configuration dùng chung, metadata được tính từ môi trường và thành phần service chỉ một số endpoint mới sử dụng.

Tuy nhiên, LazyConstant vẫn preview ở JDK 27. Nếu production cần API đã final, có thể dùng initialization-on-demand holder idiom:

```java
public final class RoutingTables {
    private RoutingTables() {}

    private static class Holder {
        static final RoutingTable INSTANCE = RoutingTable.load();
    }

    public static RoutingTable get() {
        return Holder.INSTANCE;
    }
}
```

Class `Holder` chỉ được khởi tạo khi `get()` được gọi lần đầu. Cơ chế khởi tạo lớp của JVM bảo đảm an toàn luồng và `INSTANCE` là `static final`. Đây là kỹ thuật Java hiện hành, không cần preview flag; đổi lại, nó tạo singleton theo class initialization và không có mô hình API LazyConstant để kết hợp các holder theo dependency graph.

Không nên thay mọi `static final` bằng LazyConstant. Hãy giữ constant variable cho giá trị compile-time đơn giản, dùng `static final` eager khi object luôn cần ngay lúc lớp được khởi tạo, và chỉ dùng LazyConstant khi việc trì hoãn nội dung có lợi ích rõ ràng, có thể chấp nhận preview API và hiểu chính sách lỗi/giữ bộ nhớ của nó.

## Ghi nhớ

- `static final` không tự động là constant variable; JLS chỉ coi biến `final` primitive hoặc `String` được khởi tạo bằng constant expression là constant variable.
- `static final` object reference không phải hằng compile-time; object có thể mutable dù reference không đổi.
- LazyConstant tạo holder trước, tính nội dung ở lần `get()` đầu tiên và chỉ khởi tạo nội dung tối đa một lần.
- JIT constant folding của LazyConstant là tối ưu runtime, không phải javac thực thi supplier lúc biên dịch.
- Để đủ điều kiện folding, cần đường tham chiếu từ `static final` trực tiếp hoặc qua trusted fields như `static final`, record fields hay final instance fields trong hidden classes.
- JVM có thể tối ưu các lần đọc sau, nhưng không có bảo đảm mọi lần `get()` đều được loại bỏ.
- LazyConstant thread-safe và safe publication, nhưng supplier có thể làm các thread chờ; không có timeout/cancellation.
- JDK 26 dùng JEP 526 Second Preview; JDK 27 dùng JEP 531 Third Preview. API JDK 27 đã bỏ `isInitialized()` và `orElse()` và thay đổi cách xử lý lỗi.
- Khi production yêu cầu API ổn định, initialization-on-demand holder idiom vẫn là lựa chọn hợp lệ không cần preview.

## Tài liệu tham khảo

- [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526) — mục tiêu và thiết kế trong JDK 26.
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531) — các thay đổi của preview trong JDK 27.
- [LazyConstant, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html) — `of`, `get`, thread safety, failure behavior và điều kiện constant folding.
- [LazyConstant, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html) — API hiện tại, trusted fields và error state.
- [Lazy Constants, Java SE 26 Core Libraries](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html) — so sánh eager/lazy initialization, constant folding và lazy collections.
- [Lazy Constants, Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html) — API preview hiện hành và các lazy collection.
- [JLS 26 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.12.4) và [JLS 26 §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.29) — định nghĩa constant variable và constant expression.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) và [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — xác nhận trạng thái preview của Lazy Constants trong từng bản JDK.
