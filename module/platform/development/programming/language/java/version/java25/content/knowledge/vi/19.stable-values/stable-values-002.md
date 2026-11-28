# Khởi tạo trì hoãn với giá trị ổn định và khác biệt với trường final

> **Chương:** Stable Values  
> **Nền tảng:** Ý tưởng Stable Values xuất hiện trong Java 25 qua JEP 502; API được đổi tên thành Lazy Constants từ Java 26 và tiếp tục preview trong Java 27.  
> **Mục tiêu:** Hiểu cách tạo một giá trị chỉ được tính khi cần, chỉ khởi tạo thành công một lần, sau đó không đổi; biết phân biệt cơ chế này với trường `final` và chọn đúng API theo JDK.

## 1. Bài toán: khởi tạo muộn nhưng vẫn giữ tính ổn định

Một ứng dụng Spring Boot có thể có nhiều thành phần chỉ được dùng trong một số luồng hiếm gặp: bộ phân tích định dạng báo cáo, metadata cho một giao thức, logger chuyên biệt hoặc cấu trúc tra cứu tốn thời gian xây dựng.

Nếu khởi tạo tất cả ngay khi tạo object hoặc khi class được nạp, startup có thể phải trả chi phí cho thành phần chưa chắc được dùng. Nhưng nếu chuyển sang một trường mutable và tự viết lazy initialization, code phải xử lý đồng thời, safe publication, lỗi khởi tạo và nguy cơ tạo nhiều object.

Ví dụ đơn giản nhưng không an toàn:

~~~java
final class ReportService {
    private Parser parser;

    Parser parser() {
        if (parser == null) {
            parser = new Parser();
        }
        return parser;
    }
}
~~~

Nếu nhiều thread gọi `parser()` cùng lúc, có thể có nhiều `Parser` được tạo. Một thread cũng có thể đọc trạng thái chưa được công bố an toàn. Thêm `synchronized` giải quyết một phần vấn đề nhưng mọi lần đọc đều phải đi qua monitor; double-checked locking lại đòi hỏi `volatile` và code khó kiểm tra hơn.

Một yêu cầu tốt hơn là:

- Chưa dùng thì chưa tạo giá trị.
- Khi nhiều thread cùng yêu cầu lần đầu, chỉ một phép tính được chọn để chạy.
- Sau khi khởi tạo thành công, giá trị không thể bị thay bằng giá trị khác.
- Những lần đọc sau có thể được JVM tối ưu như đọc một hằng số.
- Lập trình viên không phải tự quản lý cờ khởi tạo và khóa.

Ý tưởng này được gọi là **Stable Values** trong Java 25 và được phát triển tiếp dưới tên **Lazy Constants** ở các JDK mới hơn.

## 2. Stable Values và Lazy Constants là gì?

Một stable value/lazy constant là một holder có thể chưa chứa giá trị. Khi được truy cập lần đầu, nó tính giá trị từ một computing function; sau khi khởi tạo thành công, nội dung được cố định và không thể thay đổi.

Có hai đặc tính cần tách biệt:

1. **Khởi tạo trì hoãn (lazy initialization):** tính giá trị tại lần truy cập đầu tiên thay vì lúc tạo holder.
2. **Tính ổn định (constantness):** sau khi có giá trị, holder không cho thay nội dung. JVM có thể tận dụng đặc tính này để tối ưu các lần đọc.

~~~mermaid
stateDiagram-v2
    [*] --> Uninitialized
    Uninitialized --> Initializing: lần get đầu tiên
    Initializing --> Initialized: tính thành công
    Initializing --> Error: tính thất bại theo ngữ nghĩa JDK
    Initialized --> Initialized: get trả cùng nội dung
    Error --> Error: lần get sau theo JDK 27
~~~

Ở trạng thái đã khởi tạo, holder không có thao tác reset hoặc set giá trị mới. Đây là khác biệt quan trọng với cache thông thường: cache có thể hết hạn, bị xóa hoặc được cập nhật; lazy constant chỉ dành cho giá trị được xác định một lần trong vòng đời của holder.

**Tên gọi đã thay đổi theo release.** Java 25 giới thiệu API `StableValue`; Java 26 đổi tên thành `LazyConstant` và đơn giản hóa cách dùng; Java 27 tiếp tục preview API này. Bài học dùng thuật ngữ Stable Values để giải thích ý tưởng trong Java 25, đồng thời dùng Lazy Constants làm tên và API hiện hành trong ví dụ chính.

## 3. Trạng thái API theo từng phiên bản JDK

Đây là phần quan trọng khi học Java 25 nhưng làm việc với JDK mới hơn. API preview có thể đổi tên, thay method hoặc thay semantics giữa các release.

| JDK | JEP | Tên API | Trạng thái và điểm đáng chú ý |
|---|---|---|---|
| Java 25 | JEP 502 | `java.lang.StableValue` | Preview lần đầu; có `of()`, `trySet()`, `setOrThrow()`, `orElseSet()` và các factory cho supplier/function/list/map |
| Java 26 | JEP 526 | `java.lang.LazyConstant` | Preview lần hai; đổi mô hình sang `of(Supplier)` và `get()`, kế thừa `Supplier<T>` |
| Java 27 | JEP 531 | `java.lang.LazyConstant` | Preview lần ba; bỏ `orElse()` và `isInitialized()` từng có ở Java 26; bổ sung lazy set bên cạnh lazy list/map |

Tại ngày 27-11-2026, Lazy Constants vẫn là **preview API** trong JDK 27. Không xem nó là API permanent. Nếu sử dụng, cần bật preview khi compile và run, pin JDK release trong build và kiểm tra lại API khi nâng cấp.

### Vì sao bài không dùng StableValue làm API chính?

`StableValue` là tên và thiết kế API của Java 25. Từ Java 26, API được thay bằng `LazyConstant`. Mã nguồn Java 25 dùng `StableValue.of()` hoặc `orElseSet()` không thể chuyển nguyên trạng sang JDK 27.

Vì mục tiêu là kiến thức còn áp dụng khi làm việc hiện nay, ví dụ chính bên dưới dùng `LazyConstant` của JDK 27. Bảng phiên bản giúp bạn nhận diện mã Java 25 cũ khi đọc tài liệu hoặc dự án đang nâng cấp.

## 4. Khác biệt giữa final field và lazy constant

Trường `final` chỉ bảo đảm biến tham chiếu được gán một lần. Nó không tự làm object mà trường trỏ tới trở thành immutable.

~~~java
final class ReportService {
    private final Parser parser = new Parser();

    ReportService() {
        // Parser đã được tạo trong lúc khởi tạo ReportService.
    }

    String report(String input) {
        return parser.parse(input);
    }
}
~~~

Trong ví dụ này, `parser` được khởi tạo khi tạo `ReportService`. Nếu service được tạo lúc startup nhưng chức năng report chưa bao giờ được gọi, chi phí tạo `Parser` vẫn đã phát sinh.

Với lazy constant, holder có thể được tạo sớm nhưng nội dung chỉ được tính ở lần `get()` đầu tiên:

~~~java
import java.lang.LazyConstant;

final class ReportService {
    private final LazyConstant<Parser> parser =
            LazyConstant.of(Parser::new);

    String report(String input) {
        return parser.get().parse(input);
    }
}
~~~

So sánh:

| Tiêu chí | `final Parser parser` | `final LazyConstant<Parser> parser` |
|---|---|---|
| Thời điểm tạo Parser | Khi field/instance được khởi tạo | Lần đầu gọi `get()` |
| Thay tham chiếu sau khởi tạo | Không | Holder không cho thay content sau khi initialized |
| Giá trị có thể chưa được tính? | Không, nếu field phải được khởi tạo ngay | Có |
| Khởi tạo đồng thời | Do cơ chế constructor/class initialization | Lazy constant bảo đảm một computing function được chọn |
| JVM tối ưu như hằng số | Có thể với final field theo điều kiện tối ưu | Có thể sau khi initialized và có đường tham chiếu đáng tin cậy |
| Reset/refresh | Không qua field final | Không |
| Preview API | Không | Có trong JDK 27 |

Nếu object luôn cần thiết và rẻ để tạo, `final` vẫn là lựa chọn đơn giản nhất. Lazy constant hữu ích khi giá trị đắt để tạo, ít khi dùng và sau khi tạo không cần thay đổi.

### final không đồng nghĩa immutable sâu

~~~java
final List<String> names = new ArrayList<>();
names.add("Ada"); // Hợp lệ: tham chiếu names không đổi, nội dung list vẫn thay đổi.
~~~

Tương tự, một `LazyConstant<List<String>>` không cho thay list được holder giữ sau khi khởi tạo, nhưng bản thân list có thể mutable nếu computing function trả về `ArrayList`. Nếu muốn dữ liệu bất biến, trả về collection immutable như `List.copyOf(...)` hoặc một kiểu dữ liệu immutable phù hợp.

## 5. API hiện hành trong JDK 27: LazyConstant

Trong Java 27, `LazyConstant<T>` là preview interface trong module `java.base` và mở rộng `Supplier<T>`. API cốt lõi:

- `LazyConstant.of(Supplier<? extends T>)` tạo một lazy constant chưa được khởi tạo.
- `get()` trả về nội dung; nếu chưa có thì gọi computing function để tạo và lưu nội dung.
- Sau khi khởi tạo thành công, các lần `get()` tiếp theo trả cùng nội dung.
- Không có API để thay nội dung hoặc reset.

Ví dụ:

~~~java
import java.lang.LazyConstant;
import java.util.logging.Logger;

final class AuditService {
    private static final LazyConstant<Logger> LOGGER =
            LazyConstant.of(() ->
                    Logger.getLogger(AuditService.class.getName()));

    void record(String message) {
        LOGGER.get().info(message);
    }
}
~~~

`LOGGER` được tạo như một holder khi class được khởi tạo. Logger chỉ được lấy ở lần đầu gọi `record()`. Các lần gọi tiếp theo dùng cùng nội dung đã được khởi tạo.

### Compile và run trên JDK 27

Vì Lazy Constants là preview trong JDK 27, dùng đúng release:

~~~bash
javac --release 27 --enable-preview -d out LazyConstantDemo.java
java --enable-preview -cp out LazyConstantDemo
~~~

Không biên dịch với `--release 25` rồi chạy bằng JDK 27. Preview class file được gắn với release đã tạo nó; khi nâng JDK, cần biên dịch lại bằng preview flags của release đích.

Nếu cần tái hiện API StableValue ban đầu trong JDK 25, phải dùng JDK 25 và `--release 25 --enable-preview`. Đó là một nhánh API khác; không trộn import hoặc method của StableValue vào ví dụ LazyConstant hiện hành.

## 6. Ví dụ thực tế: tạo parser đắt tiền đúng một lần

Giả sử ứng dụng đọc schema báo cáo từ một file cấu hình cố định. Parser cần đọc metadata và xây dựng cấu trúc tra cứu; chỉ một số request mới sử dụng chức năng này.

~~~java
import java.lang.LazyConstant;
import java.util.Map;

final class ReportSchema {
    private final Map<String, String> columns;

    ReportSchema() {
        this.columns = Map.of(
                "order_id", "Order ID",
                "created_at", "Created time",
                "total", "Total amount");
    }

    String labelOf(String column) {
        return columns.getOrDefault(column, column);
    }
}

final class ReportService {
    private static final LazyConstant<ReportSchema> SCHEMA =
            LazyConstant.of(ReportSchema::new);

    String header(String column) {
        return SCHEMA.get().labelOf(column);
    }
}
~~~

Luồng hoạt động:

1. JVM tạo holder `SCHEMA` khi class `ReportService` được khởi tạo.
2. Chưa có `ReportSchema` nào được tạo tại thời điểm này.
3. Request đầu tiên gọi `header()` và đi tới `SCHEMA.get()`.
4. Computing function `ReportSchema::new` được gọi.
5. Nếu khởi tạo thành công, nội dung được gắn vào lazy constant.
6. Các request tiếp theo lấy cùng schema đã có.

Ví dụ dùng `Map.of(...)` cho dữ liệu minh họa nhỏ. Nếu schema được đọc từ file hoặc remote config, phải cân nhắc semantics lỗi ở mục 9: trong JDK 27, lỗi unchecked của computing function có thể đưa lazy constant vào error state vĩnh viễn. Không dùng lazy constant như cơ chế retry mạng.

## 7. Thread safety và safe publication

Lazy constant được thiết kế cho truy cập đồng thời:

- Nếu nhiều thread cùng gọi `get()` khi holder chưa được khởi tạo, chỉ một thread được chọn chạy computing function.
- Các thread còn lại chờ kết quả khởi tạo hoặc trạng thái lỗi.
- Khi khởi tạo thành công, nội dung được publish an toàn cho các thread đọc.
- Việc khởi tạo và publish có quan hệ happens-before với lần đọc nội dung đã khởi tạo.

~~~mermaid
sequenceDiagram
    participant T1 as Thread A
    participant T2 as Thread B
    participant L as LazyConstant

    T1->>L: get()
    T2->>L: get()
    L->>T1: chọn làm computing thread
    L-->>T2: chờ kết quả
    T1->>T1: tạo Parser
    T1->>L: hoàn tất initialization
    L-->>T1: trả Parser
    L-->>T2: trả cùng Parser
~~~

Không cần tự thêm `synchronized` quanh mọi lần đọc `get()`. Việc khởi tạo nguyên tử và safe publication là trách nhiệm của API.

### Điều gì không được bảo đảm?

- Nếu computing function block vô thời hạn, các thread khác chờ holder đó cũng có thể block vô thời hạn.
- Thread interruption không hủy phép khởi tạo; `get()` không tự xóa interrupt status và không ném `InterruptedException` chỉ vì thread bị interrupt.
- Lazy constant không cung cấp timeout, cancellation hoặc retry policy cho computing function.
- Bảo đảm at-most-once chỉ nói về phép tính của holder; nó không biến các side effect bên ngoài thành transaction.

Vì vậy, computing function nên có thời gian thực thi dự đoán được, không giữ lock bên ngoài quá lâu và tránh gọi những dependency có thể block vô hạn.

## 8. Lazy constant có thể được JVM tối ưu như thế nào?

Sau khi initialized, nội dung không thể thay đổi. Vì vậy JVM có thể tối ưu bằng cách loại bỏ các lần đọc holder lặp lại và dùng giá trị đã quan sát trước đó. Đây là dạng constant folding.

Tuy nhiên, không nên hiểu rằng cứ tạo một `LazyConstant` là JVM chắc chắn biến nó thành hằng số. Tài liệu JDK 27 mô tả điều kiện để tối ưu: holder cần được truy cập qua một tham chiếu `static final` trực tiếp hoặc qua một chuỗi trusted fields, chẳng hạn trường static final, trường record hoặc final instance field trong hidden class.

Ví dụ có cấu trúc phù hợp:

~~~java
final class ApplicationConstants {
    private static final LazyConstant<Parser> PARSER =
            LazyConstant.of(Parser::new);

    static Parser parser() {
        return PARSER.get();
    }
}
~~~

`PARSER` được giữ trong `static final`. Sau khi khởi tạo, các lần truy cập có thể đủ điều kiện để JVM thực hiện tối ưu constant folding.

**Đây là khả năng tối ưu, không phải cam kết về thời gian chạy.** JIT có thể cần warm-up và profile; kết quả còn phụ thuộc đường truy cập, cấu trúc code và implementation JVM. Hãy benchmark ứng dụng nếu hiệu năng là lý do chính để áp dụng.

## 9. Xử lý exception, null và lỗi đệ quy trong JDK 27

Đây là thay đổi quan trọng giữa các phiên bản. Trong JDK 27, nếu computing function ném unchecked exception, lazy constant đi vào error state:

- Lần gọi `get()` đầu tiên ném `NoSuchElementException` có unchecked exception gốc làm `cause`.
- Holder không được initialized thành công.
- Các lần `get()` tiếp theo tiếp tục ném `NoSuchElementException` nhưng không còn `cause`; computing function không được gọi lại.
- Nếu computing function trả về `null`, holder cũng đi vào error state với `NullPointerException` là nguyên nhân.
- Nếu computing function gọi lại chính lazy constant đang được tính, sẽ xảy ra lỗi đệ quy và holder chuyển sang error state.

~~~java
import java.lang.LazyConstant;

final class BrokenConfiguration {
    private static final LazyConstant<String> CONFIG =
            LazyConstant.of(() -> {
                throw new IllegalStateException("configuration is invalid");
            });

    static String get() {
        return CONFIG.get();
    }
}
~~~

Ở JDK 27, không dùng lazy constant này với kỳ vọng lần sau sẽ tự retry sau một lỗi tạm thời. Trạng thái lỗi được giữ lại.

### Khác biệt semantics qua release

| Phiên bản | API | Khi computing function ném unchecked exception |
|---|---|---|
| Java 25 / JEP 502 | `StableValue.orElseSet(...)` | Không ghi content; lần gọi sau có thể thử lại |
| Java 26 / JEP 526 | `LazyConstant.get()` | Vẫn chưa initialized; lần gọi sau có thể thử lại |
| Java 27 / JEP 531 | `LazyConstant.get()` | Chuyển sang error state; lần đầu ném `NoSuchElementException` có cause, lần sau ném `NoSuchElementException` không cause và không gọi lại supplier |

Đây là lý do không được mang assumptions về retry từ Java 25/26 sang Java 27. Đọc Javadoc của đúng JDK trước khi dùng exception handling trong production.

### Nếu giá trị có thể null

Lazy constant không lưu `null` như một content hợp lệ. Nếu domain cho phép "không tìm thấy", hãy biểu diễn kết quả bằng `Optional<T>`:

~~~java
private static final LazyConstant<Optional<Profile>> PROFILE =
        LazyConstant.of(() -> loadProfile().map(Optional::of)
                .orElseGet(Optional::empty));
~~~

Như vậy lazy constant giữ một object `Optional` không null; trạng thái rỗng được biểu diễn bên trong Optional.

## 10. Tổ chức dependency và tránh vòng khởi tạo

Có thể xây dựng một dependency graph từ các lazy constants. Ví dụ `ReportRenderer` cần `ReportSchema`; schema lại phụ thuộc một registry cố định.

~~~java
import java.lang.LazyConstant;

final class ReportComponents {
    private static final LazyConstant<ReportSchema> SCHEMA =
            LazyConstant.of(ReportSchema::new);

    private static final LazyConstant<ReportRenderer> RENDERER =
            LazyConstant.of(() -> new ReportRenderer(SCHEMA.get()));

    static ReportRenderer renderer() {
        return RENDERER.get();
    }
}
~~~

Khi `renderer()` được gọi, `RENDERER` được khởi tạo; trong lúc đó `SCHEMA.get()` được gọi và schema được khởi tạo trước. Đây là dependency một chiều và có thể hiểu được.

Tránh vòng phụ thuộc:

~~~text
A.get() -> tạo A -> cần B.get()
B.get() -> tạo B -> cần A.get()
~~~

Nếu computing function quay lại chính lazy constant đang trong quá trình tính, API phát hiện recursive initialization và báo lỗi. Vòng phụ thuộc giữa các class static initializer cũng có thể tạo vấn đề class initialization. Hãy thiết kế graph theo hướng một chiều hoặc dùng dependency injection container quản lý lifecycle.

### Không đồng bộ trên chính holder

Implementation được phép synchronize trên chính lazy constant. Tránh dùng holder làm monitor:

~~~java
synchronized (CONFIG) {
    // Không dùng LazyConstant làm monitor.
}
~~~

Việc này có thể gây deadlock nếu implementation cũng cần monitor đó trong quá trình khởi tạo. Dùng một lock riêng nếu ứng dụng thực sự cần đồng bộ thao tác khác.

## 11. Lazy collections trong JDK 27

JDK 27 mở rộng ý tưởng lazy constants sang các collection preview. Các collection này không cho thêm/xóa phần tử; nội dung hoặc trạng thái membership được tính theo nhu cầu.

| API | Cách tính trì hoãn | Trường hợp sử dụng |
|---|---|---|
| `List.ofLazy(size, mapper)` | Tính phần tử khi gọi `get(index)` lần đầu | Danh sách có index cố định, mỗi phần tử tốn chi phí tạo |
| `Map.ofLazy(keys, mapper)` | Tính value khi truy cập key lần đầu | Cache hữu hạn với tập key đã biết |
| `Set.ofLazy(candidates, predicate)` | Tính membership khi gọi `contains(candidate)` | Tập ứng viên cố định, điều kiện membership tốn chi phí |

Ví dụ lazy list:

~~~java
import java.util.List;

final class PowerTables {
    private static final List<Long> POWERS =
            List.ofLazy(10, index -> 1L << index);

    static long powerOfTwo(int exponent) {
        return POWERS.get(exponent);
    }
}
~~~

Chỉ số hợp lệ là `0` đến `9`. Mỗi index được tính khi truy cập lần đầu; danh sách không cho sửa nội dung bằng `add()` hoặc `set()`.

Ví dụ lazy map:

~~~java
import java.util.Map;
import java.util.Set;

final class Pricing {
    private static final Map<String, Integer> PRICE =
            Map.ofLazy(
                    Set.of("basic", "plus", "enterprise"),
                    Pricing::loadPrice);

    private static int loadPrice(String tier) {
        return switch (tier) {
            case "basic" -> 100;
            case "plus" -> 250;
            case "enterprise" -> 800;
            default -> throw new IllegalArgumentException(tier);
        };
    }

    static int priceOf(String tier) {
        return PRICE.get(tier);
    }
}
~~~

Tập key được cố định lúc tạo map. Key không có trong tập không trở thành một mapping mới. Các lazy collections cũng là preview APIs trong JDK 27 và có thể thay đổi ở release sau.

### Lưu ý khi duyệt collection

Các thao tác như duyệt toàn bộ list/map hoặc gọi các method cần đọc nhiều phần tử có thể kích hoạt nhiều computing functions. Đừng giả định chỉ gọi factory là đã tính hết hoặc một lần truy cập một phần tử sẽ không kích hoạt các phần tử khác trong một thao tác duyệt.

## 12. Khi nào nên dùng và khi nào không nên dùng?

| Tình huống | Có phù hợp? | Lý do |
|---|---|---|
| Parser hoặc schema cố định, chỉ dùng ở một số request | Có thể | Chi phí tạo được trì hoãn và giá trị không cần refresh |
| Metadata giao thức cố định theo phiên bản ứng dụng | Có thể | Nội dung chỉ cần tạo một lần |
| Logger hoặc formatter dùng chung | Có thể | Tạo khi cần, sau đó tái sử dụng |
| Cấu hình có thể reload khi vận hành | Không phù hợp | Lazy constant không hỗ trợ reset/refresh |
| Cache kết quả theo user có TTL | Không phù hợp | Cần eviction, expiration và giới hạn dung lượng |
| Kết quả truy vấn remote có thể lỗi tạm thời | Thường không phù hợp | JDK 27 giữ error state, không retry supplier |
| Request context hoặc dữ liệu theo từng người dùng | Không phù hợp | Không phải storage theo request/thread |
| Object cần mutate sau khởi tạo | Không phù hợp | Nội dung holder không thể thay; object mutable vẫn có thể bị thay đổi bên trong nhưng làm mất lợi ích constantness |

Một lazy constant giữ mạnh nội dung của nó. Nếu holder tồn tại lâu, nội dung cũng có thể tồn tại lâu. Đừng dùng nó để giữ các object lớn có vòng đời ngắn hoặc chứa reference đến request/session.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng StableValue import trên JDK 27 | Không tìm thấy type vì API đã đổi tên | Dùng `java.lang.LazyConstant` |
| Copy code Java 26 gọi `orElse()` hoặc `isInitialized()` sang JDK 27 | Compile error vì hai method đã bị loại bỏ | Dùng `get()` cho API JDK 27; thiết kế flow không dựa vào trạng thái chưa khởi tạo |
| Quên preview flags | Compiler/runtime từ chối preview API | Dùng `--release 27 --enable-preview` khi compile và `--enable-preview` khi run |
| Nghĩ holder final làm object bất biến sâu | Vẫn có thể sửa List/Map/field bên trong object | Dùng kiểu dữ liệu immutable nếu cần |
| Dùng cho cấu hình cần reload | Không thể thay content sau khởi tạo | Dùng AtomicReference, cache có TTL hoặc lifecycle config riêng |
| Mong retry khi supplier lỗi trên JDK 27 | Holder đã chuyển error state | Validate trước; dùng cơ chế retry bên ngoài nếu nghiệp vụ cần |
| Trả null từ supplier | Lazy constant không thể giữ null | Dùng Optional hoặc kiểu kết quả không null |
| Supplier block vô hạn | Các thread khác chờ cùng holder | Giới hạn timeout ở dependency và tránh khởi tạo blocking không kiểm soát |
| Supplier gọi lại chính nó | Recursive initialization error | Loại bỏ vòng dependency |
| Synchronize trực tiếp trên holder | Có nguy cơ deadlock | Dùng lock riêng hoặc thiết kế lại |
| Dùng lazy constant như cache không giới hạn | Nội dung được giữ mạnh trong suốt vòng đời holder | Đánh giá footprint và chọn cache có eviction |
| Kỳ vọng chắc chắn có constant folding | Benchmark không đạt như kỳ vọng | Coi tối ưu là khả năng; đo trên JDK và workload mục tiêu |

## 14. Kiểm thử tính khởi tạo một lần

Một kiểm thử phù hợp nên chứng minh supplier chỉ chạy một lần khi nhiều thread cùng gọi. Ví dụ JDK 27:

~~~java
import java.lang.LazyConstant;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyConstantDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger computations = new AtomicInteger();

        LazyConstant<String> token = LazyConstant.of(() -> {
            computations.incrementAndGet();
            return "initialized";
        });

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var first = executor.submit(token::get);
            var second = executor.submit(token::get);
            var third = executor.submit(token::get);

            System.out.println(first.get());
            System.out.println(second.get());
            System.out.println(third.get());
        }

        if (computations.get() != 1) {
            throw new AssertionError(
                    "Expected one computation, got " + computations.get());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 27:

~~~bash
javac --release 27 --enable-preview -d out LazyConstantDemo.java
java --enable-preview -cp out LazyConstantDemo
~~~

Kết quả:

~~~text
initialized
initialized
initialized
~~~

Assertion xác nhận computing function chỉ được thực thi một lần trong lần chạy này. Để kiểm tra cạnh tranh tốt hơn, hãy lặp test nhiều lần, dùng barrier để đồng thời gọi `get()` và thêm test cho supplier chậm.

### Bộ test cần có

- Gọi `get()` nhiều lần và xác nhận cùng object identity.
- Nhiều thread gọi lần đầu đồng thời; supplier chỉ chạy một lần.
- Supplier trả `null` và kiểm tra error behavior.
- Supplier ném unchecked exception; kiểm tra lần đầu và các lần `get()` tiếp theo đúng semantics JDK 27.
- Supplier đệ quy gọi chính holder và xác nhận lỗi.
- Dependency graph lồng nhau được khởi tạo theo thứ tự mong đợi.
- Kiểm tra memory retention nếu holder giữ object lớn.

## 15. Quy trình chọn API khi nâng cấp JDK

Trước khi nâng JDK, tìm các import và method của API preview:

~~~text
java.lang.StableValue
StableValue.of
orElseSet
trySet
setOrThrow
java.lang.LazyConstant
LazyConstant.of
isInitialized
orElse
~~~

Sau đó đối chiếu phiên bản:

| Nguồn code | Đích | Việc cần làm |
|---|---|---|
| Java 25 `StableValue` | Java 26/27 | Chuyển sang `LazyConstant.of(Supplier)` và `get()`; không chỉ đổi tên import |
| Java 26 `LazyConstant` | Java 27 | Bỏ cách dùng `orElse()` và `isInitialized()`; rà lại semantics exception |
| Java 27 `LazyConstant` | JDK tiếp theo | Kiểm tra JEP/API preview mới; recompile bằng preview flags của release đích |

Vì preview API không có cam kết tương thích source/binary giữa các release, hãy pin JDK trong toolchain, compile test trong CI và tránh phát hành library công khai phụ thuộc preview API nếu chưa chấp nhận rủi ro nâng cấp.

### Bản đồ chuyển đổi khái niệm

| Ý định trong Java 25 | Cách tiếp cận LazyConstant từ Java 26/27 |
|---|---|
| Tạo holder rỗng bằng `StableValue.of()` | Tạo lazy computation bằng `LazyConstant.of(supplier)` |
| Lấy hoặc tính bằng `orElseSet(supplier)` | Gọi `get()` |
| Gán một lần bằng `trySet()` hoặc `setOrThrow()` | Cung cấp computing function khi tạo holder; không có thao tác set tùy ý |
| Kiểm tra `isSet()` | Thiết kế code không phụ thuộc trạng thái chưa khởi tạo; JDK 27 không có `isInitialized()` |
| Stable supplier/function/list/map factories | Dùng `LazyConstant` hoặc các lazy collection factory tương ứng theo JDK mục tiêu |

Đây là bản đồ ý tưởng, không phải phép thay thế cơ học. Ví dụ, việc chuyển từ `orElseSet()` sang `get()` còn làm thay đổi cách xử lý lỗi giữa các release.

## 16. Checklist và bài tập thực hành

### Checklist

- [ ] Phân biệt khởi tạo eager của `final` field với lazy initialization.
- [ ] Hiểu Stable Values trong Java 25 là preview API, không phải API permanent.
- [ ] Biết `StableValue` được đổi thành `LazyConstant` từ Java 26.
- [ ] Với JDK 27, dùng `LazyConstant.of(Supplier)` và `get()`.
- [ ] Biết Lazy Constants trong JDK 27 vẫn là preview và cần preview flags.
- [ ] Không dùng `orElse()` hoặc `isInitialized()` trong code nhắm JDK 27.
- [ ] Hiểu at-most-once initialization và safe publication.
- [ ] Kiểm tra semantics lỗi, null và recursive initialization theo đúng JDK.
- [ ] Không dùng cho dữ liệu cần refresh, TTL hoặc retry.
- [ ] Kiểm tra memory retention, supplier blocking và dependency cycles.
- [ ] Đo hiệu năng trước khi kết luận constant folding mang lại lợi ích.

### Bài tập A — Lazy logger

Tạo `LazyConstant<Logger>` trong một service. Chỉ gọi `get()` khi ghi log lần đầu. Dùng counter trong supplier để xác nhận nhiều request không tạo nhiều logger.

### Bài tập B — Parser theo schema

Một ứng dụng hỗ trợ ba định dạng báo cáo, nhưng mỗi instance chỉ dùng một định dạng. Tạo lazy constant cho parser tương ứng. Đo thời gian startup và thời điểm parser đầu tiên được tạo. Giải thích trade-off giữa startup và latency của request đầu tiên.

### Bài tập C — Dependency graph

Tạo hai lazy constants `SCHEMA` và `RENDERER`; renderer cần schema. Gọi `RENDERER.get()` trước và xác nhận schema chỉ được khởi tạo khi dependency được truy cập. Sau đó tạo một vòng dependency có kiểm soát trong test và quan sát lỗi recursive initialization.

### Bài tập D — Nâng cấp từ Java 25 lên Java 27

Một module dùng `StableValue.of()` và `orElseSet()`. Lập kế hoạch chuyển sang `LazyConstant.of(Supplier)` và `get()`. Thêm test chứng minh cách xử lý supplier exception thay đổi giữa Java 25 và Java 27; giải thích tại sao code retry không thể giữ nguyên.

### Câu hỏi tự đánh giá

1. Vì sao `final` field thường khởi tạo eager?
2. Lazy constant khác một mutable cache ở điểm nào?
3. Vì sao JVM có thể tối ưu nội dung sau khi lazy constant đã initialized?
4. Tại sao constant folding là khả năng tối ưu chứ không phải cam kết?
5. Điều gì xảy ra khi nhiều thread cùng gọi `get()` lần đầu?
6. Trong JDK 27, điều gì xảy ra sau khi computing function ném unchecked exception?
7. Vì sao không nên dùng lazy constant cho dữ liệu cấu hình cần reload?
8. API `StableValue` của Java 25 đã thay đổi ra sao trong Java 26 và 27?

## 17. Tài liệu chính thức

- [JEP 502 — Stable Values (Preview)](https://openjdk.org/jeps/502): thiết kế ban đầu và API StableValue trong Java 25.
- [Java SE 25 — StableValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StableValue.html): API preview ban đầu, các factory và semantics của StableValue.
- [Oracle JDK 25 — Stable Values](https://docs.oracle.com/en/java/javase/25/core/lazy-constants.html): khái niệm Stable Values, lazy initialization và khác biệt với final field.
- [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): đổi tên và sửa API trong Java 26.
- [Oracle JDK 26 — Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận Lazy Constants là preview lần thứ hai.
- [Java SE 27 — LazyConstant API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API hiện hành trong JDK 27, thread safety, failure state và constant folding.
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): thay đổi ở Java 27, bao gồm điều chỉnh API và lazy set.
- [Oracle JDK 27 — Lazy Constants](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): hướng dẫn thực hành LazyConstant và lazy collections.
- [Java SE 27 — List.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): danh sách lazy theo index.
- [Java SE 27 — Map.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): map lazy theo tập key cố định.
- [Java SE 27 — Set.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): set lazy theo tập ứng viên.

> **Ghi nhớ:** Stable Values bắt đầu trong Java 25 nhưng API đã tiến hóa thành Lazy Constants từ Java 26. Trong JDK 27, dùng `LazyConstant.of(supplier)` và `get()`; tính năng vẫn là preview. Giá trị chỉ được khởi tạo một lần, sau đó không đổi, nhưng không phù hợp với cache cần refresh hoặc retry.
