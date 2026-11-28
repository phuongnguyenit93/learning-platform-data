# Mục đích và trạng thái preview của Stable Values trong JDK 25

## 1. Mục tiêu và bối cảnh

Một ứng dụng Java thường có những đối tượng chỉ cần tạo khi tính năng tương ứng được sử dụng: logger, parser, bộ nạp cấu hình, metadata, bảng tra cứu hoặc một thành phần khởi tạo tốn thời gian. Khởi tạo tất cả ngay khi tạo object hoặc nạp class có thể làm chậm startup, kể cả khi một số giá trị không bao giờ được dùng.

Ta có thể trì hoãn khởi tạo bằng lazy initialization. Tuy nhiên, nếu muốn vừa khởi tạo trễ, vừa bảo đảm chỉ khởi tạo một lần trong môi trường nhiều thread, code thường phải dùng synchronized, double-checked locking, holder idiom hoặc tự xây một cache đồng bộ. Các cách này giải quyết những vấn đề khác nhau và không phải lúc nào cũng cho JVM biết giá trị đã trở nên bất biến sau khi được tính.

**Stable Values (JEP 502)** giới thiệu một API preview trong **Java 25** để biểu diễn một giá trị có thể chưa được thiết lập lúc tạo holder, nhưng sau khi được thiết lập thì nội dung không thể thay đổi. JVM có thể xem giá trị đã thiết lập như một hằng số để áp dụng những tối ưu hóa tương tự final field, trong khi ứng dụng vẫn được quyền quyết định thời điểm khởi tạo.

Bài **Mục đích và trạng thái preview của Stable Values trong JDK 25**, thuộc chương **Stable Values** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào:

1. Vấn đề mà Stable Values giải quyết và khác biệt với final field.
2. Vòng đời của StableValue: unset, set một lần và đọc lại.
3. Các API of, trySet, setOrThrow, orElseSet, orElse, orElseThrow và isSet.
4. Stable supplier, stable function, stable int function, stable list và stable map.
5. Tính an toàn đa luồng, happens-before và xử lý lỗi khi khởi tạo.
6. Cơ hội constant folding và những giới hạn thực tế.
7. Trạng thái preview trong JDK 25 và quá trình đổi tên thành Lazy Constants ở các JDK mới hơn.

**Phạm vi phiên bản:** ví dụ mã dùng đúng API **java.lang.StableValue của JDK 25, JEP 502**. Đây là preview API, không phải API Java SE ổn định. Từ JDK 26, tính năng được đổi tên thành **Lazy Constants** và API được thiết kế lại; mã Java 25 không thể chuyển nguyên trạng sang các release đó.

## 2. Stable Value là gì?

Một **StableValue<T>** là holder chứa một giá trị kiểu T có thể ở trạng thái chưa được thiết lập. Khi nội dung được thiết lập thành công, nó chỉ được thiết lập một lần; những lần đọc sau nhận cùng nội dung đó.

~~~mermaid
stateDiagram-v2
    [*] --> Unset: StableValue.of()
    Unset --> Set: trySet / setOrThrow / orElseSet thành công
    Set --> Set: đọc lại cùng nội dung
    Unset --> Unset: supplier ném unchecked exception
    Set --> [*]: holder được thu gom
~~~

Ví dụ:

~~~java
import java.lang.StableValue;
import java.util.logging.Logger;

public final class Orders {
    private final StableValue<Logger> logger = StableValue.of();

    private Logger logger() {
        return logger.orElseSet(
                () -> Logger.getLogger(Orders.class.getName()));
    }

    public void printOrders() {
        logger().info("Printing orders");
    }
}
~~~

Khi tạo Orders, holder logger được tạo nhưng Logger chưa được khởi tạo. Lần đầu gọi printOrders(), orElseSet tính Logger và lưu vào StableValue. Những lần gọi sau nhận lại đúng Logger đã lưu.

Điểm quan trọng là **holder trở nên ổn định sau khi nội dung được thiết lập**. StableValue không có nghĩa object được giữ bên trong tự động bất biến sâu. Nếu holder chứa một ArrayList, reference tới ArrayList không đổi nhưng các phần tử của list vẫn có thể bị thay đổi theo API của ArrayList.

## 3. Vì sao final field chưa giải quyết đủ bài toán?

Một final field có ưu điểm là được khởi tạo một lần và không thể gán lại sau khi constructor hoàn tất. JVM có thể tận dụng tính chất đó để tối ưu. Nhưng nếu khởi tạo một final field tốn kém, constructor phải trả chi phí ngay cả khi tính năng tương ứng không được dùng.

Ví dụ eager initialization:

~~~java
public final class ReportService {
    private final ReportParser parser = ReportParser.loadLargeRuleset();

    public Report parse(String input) {
        return parser.parse(input);
    }
}
~~~

Nếu ứng dụng tạo ReportService nhưng không bao giờ gọi parse(), chi phí load ruleset vẫn đã xảy ra.

Một cách lazy initialization truyền thống:

~~~java
public final class ReportService {
    private ReportParser parser;

    public synchronized ReportParser parser() {
        if (parser == null) {
            parser = ReportParser.loadLargeRuleset();
        }
        return parser;
    }
}
~~~

Cách này trì hoãn việc tạo parser và an toàn khi nhiều thread gọi đồng thời, nhưng mọi lần gọi parser() đều đi qua synchronized. Field parser cũng không phải final, nên JVM không thể xem nó như một giá trị bất biến theo cùng cách final field.

StableValue đưa hai đặc tính lại gần nhau: **khởi tạo trễ** và **không thay đổi sau khi đã khởi tạo**. Việc tối ưu hóa vẫn là quyền của JVM; API không cam kết mọi lần truy cập sẽ nhanh hơn hoặc luôn được constant-fold.

## 4. Stable Values trong JDK 25 là preview lần đầu

Stable Values được đưa vào Java 25 qua **JEP 502 – Stable Values (Preview)**. Đây là lần preview đầu tiên của tính năng, không phải tính năng final và không phải API đã được duy trì ổn định qua nhiều release.

| JDK | Tên JEP | Trạng thái | Thay đổi cần biết |
| --- | --- | --- | --- |
| **JDK 25** | **JEP 502 – Stable Values** | **Preview lần đầu** | API là java.lang.StableValue, có of, trySet, setOrThrow, orElseSet, supplier, function, intFunction, list và map. |
| **JDK 26** | **JEP 526 – Lazy Constants (Second Preview)** | Preview lần hai | Đổi tên khái niệm và API chính thành java.lang.LazyConstant; cách dùng chuyển sang of(Supplier) và get(). |
| **JDK 27** | **JEP 531 – Lazy Constants (Third Preview)** | Preview lần ba | Tiếp tục đơn giản hóa API; bổ sung Set.ofLazy cho lazy collection. |
| **JDK 28** | **JEP 547 – Lazy Constants (Fourth Preview)** | Preview lần bốn, đã được nhắm tới/tích hợp vào nhánh JDK 28 | Không phải API final; JDK 28 chưa GA tại ngày 27/11/2026. |

### Trạng thái hiện hành tính đến ngày 27/11/2026

- **JDK 25:** dùng tên Stable Values và kiểu StableValue. Cần bật preview khi biên dịch và chạy.
- **JDK 26:** tên được đổi thành Lazy Constants; kiểu chính là LazyConstant. Không dùng StableValue của JDK 25 trong source code JDK 26.
- **JDK 27:** Lazy Constants vẫn là preview. JEP 531 là preview lần thứ ba.
- **JDK 28 Early Access:** JEP 547 là preview lần thứ tư. JDK 28 chưa phát hành GA, và Lazy Constants vẫn chưa trở thành API final.

Vì vậy, Stable Values vẫn là kiến thức quan trọng để hiểu nguồn gốc và thiết kế của Lazy Constants, nhưng **không nên coi StableValue là tên API hiện hành trên JDK 26 trở lên**. Các ví dụ trong bài này được khóa theo JDK 25.

## 5. API nằm ở đâu và cần cờ preview nào?

Trong JDK 25, StableValue thuộc package **java.lang** và module **java.base**. Với ứng dụng Java thông thường, không cần thêm thư viện ngoài JDK hoặc khai báo requires cho module java.base.

Do đây là preview API, cần bật preview ở cả hai giai đoạn:

~~~bash
# Xác nhận compiler và runtime là JDK 25
javac --version
java --version

# Biên dịch source dùng StableValue
javac --enable-preview --release 25 StableValueDemo.java

# Chạy bằng JDK 25
java --enable-preview StableValueDemo
~~~

Nếu dùng Maven hoặc Gradle, cấu hình compiler phải truyền --enable-preview và --release 25; JVM chạy test hoặc ứng dụng cũng phải có --enable-preview. Chỉ bật preview ở compiler là chưa đủ.

Preview API gắn với release cụ thể. Class file được biên dịch với preview API Java 25 không phải artifact có thể mang nguyên sang JDK 26 hoặc JDK 27. Khi nâng JDK, cần chuyển source sang API của release mới và biên dịch lại.

## 6. Các thao tác cơ bản của StableValue

JDK 25 cung cấp hai cách tạo holder:

~~~java
StableValue<String> unset = StableValue.of();
StableValue<String> preset = StableValue.of("ready");
~~~

Holder unset chưa có nội dung. Holder preset đã được thiết lập ngay khi tạo.

| Phương thức | Hành vi |
| --- | --- |
| **of()** | Tạo StableValue chưa được thiết lập. |
| **of(contents)** | Tạo StableValue đã có nội dung. |
| **trySet(contents)** | Thử thiết lập; trả true nếu lần gọi này thắng, false nếu holder đã được thiết lập. |
| **setOrThrow(contents)** | Thiết lập nội dung; ném IllegalStateException nếu đã có nội dung. |
| **orElseSet(supplier)** | Nếu chưa có nội dung, tính và thiết lập bằng supplier; trả nội dung sau khi thiết lập thành công. |
| **isSet()** | Kiểm tra holder đã có nội dung hay chưa. |
| **orElse(other)** | Trả nội dung nếu đã set, nếu chưa thì trả other. |
| **orElseThrow()** | Trả nội dung hoặc ném NoSuchElementException nếu chưa set. |

Ví dụ:

~~~java
StableValue<String> state = StableValue.of();

System.out.println(state.isSet());          // false
System.out.println(state.orElse("pending")); // pending

boolean first = state.trySet("ready");
System.out.println(first);                  // true
System.out.println(state.isSet());          // true
System.out.println(state.orElseThrow());    // ready

boolean second = state.trySet("changed");
System.out.println(second);                 // false
System.out.println(state.orElseThrow());    // ready
~~~

Nội dung đã set không thể thay bằng giá trị khác. StableValue không có thao tác reset hoặc clear để quay về trạng thái unset.

## 7. Chọn trySet, setOrThrow hay orElseSet

Ba thao tác thiết lập có mục đích khác nhau:

### trySet: nhiều thread có thể tạo candidate

~~~java
StableValue<Configuration> configuration = StableValue.of();

Configuration candidate = loadConfiguration();
boolean won = configuration.trySet(candidate);
~~~

Nếu nhiều thread cùng gọi trySet(), chỉ một lần thiết lập thành công. Tuy nhiên, các thread có thể đã cùng chạy loadConfiguration() trước khi tranh quyền set. Cách này phù hợp khi tạo candidate rẻ hoặc việc tạo dư có thể chấp nhận được.

Nếu candidate mở file, tạo connection hoặc giữ tài nguyên native, cần xử lý candidate thua cuộc để không rò rỉ tài nguyên.

### setOrThrow: thiết lập ở một bước được kiểm soát

~~~java
StableValue<String> endpoint = StableValue.of();
endpoint.setOrThrow("https://api.example.test");
~~~

Dùng setOrThrow khi luồng khởi tạo được kiểm soát và việc thiết lập hai lần là lỗi lập trình cần phát hiện ngay.

### orElseSet: chỉ một supplier thành công

~~~java
StableValue<Configuration> configuration = StableValue.of();

Configuration value = configuration.orElseSet(
        Configuration::loadFromDisk);
~~~

orElseSet phù hợp khi giá trị cần được tính lazy và supplier có thể tốn kém. Khi nhiều thread gọi đồng thời, chỉ một supplier có thể hoàn tất thành công để thiết lập nội dung; các thread còn lại chờ và nhận cùng giá trị.

Nếu supplier ném unchecked exception, exception được truyền lại cho caller và holder vẫn chưa được thiết lập. Một lần gọi sau có thể thử tính lại. Đây là một điểm khác biệt quan trọng so với LazyConstant ở các JDK sau.

## 8. Tính an toàn đa luồng và happens-before

StableValue được thiết kế để nhiều thread có thể cùng đọc hoặc tranh quyền thiết lập mà không cần ứng dụng tự đồng bộ mọi lần truy cập.

Khi một lần ghi thành công bằng trySet(), setOrThrow() hoặc orElseSet(), thao tác ghi đó **happens-before** các thao tác đọc thành công theo hợp đồng API. Nhờ đó, object được tạo trong supplier được safely published: các thread đọc nội dung sau khi thiết lập nhìn thấy trạng thái đã khởi tạo và các final field của object được công bố an toàn.

~~~mermaid
sequenceDiagram
    participant T1 as Thread A
    participant S as StableValue
    participant T2 as Thread B
    T1->>S: orElseSet(supplier)
    T2->>S: orElseSet(otherSupplier)
    S->>T1: Chọn một supplier để tính
    T1->>T1: Tạo object
    T1->>S: Thiết lập nội dung thành công
    S-->>T1: Trả nội dung
    S-->>T2: Đánh thức và trả cùng nội dung
~~~

Một số điểm cần nhớ:

- Chỉ có một nội dung được thiết lập thành công.
- Với orElseSet, supplier hoàn tất thành công được thực thi tối đa một lần, kể cả khi nhiều thread gọi đồng thời.
- Với trySet, nhiều thread có thể tạo candidate, nhưng chỉ một candidate được lưu.
- Thread đọc nội dung sau khi thiết lập thành công nhận được quan hệ happens-before.
- StableValue không làm object được chứa trở thành thread-safe nếu object đó có trạng thái mutable.

Ví dụ, nếu StableValue chứa một HashMap mutable và nhiều thread cùng sửa HashMap, ứng dụng vẫn phải đồng bộ các thao tác sửa map theo quy tắc của HashMap.

## 9. StableValue.supplier(): lazy supplier an toàn

Nếu không cần giữ StableValue trực tiếp, JDK 25 cung cấp factory **StableValue.supplier(...)** để tạo một Supplier có kết quả được tính khi gọi get() lần đầu:

~~~java
import java.util.function.Supplier;
import java.lang.StableValue;
import java.util.logging.Logger;

public final class AuditLog {
    private static final Supplier<Logger> LOGGER =
            StableValue.supplier(
                    () -> Logger.getLogger(AuditLog.class.getName()));

    public static void record(String message) {
        LOGGER.get().info(message);
    }
}
~~~

Supplier trả về giữ lại kết quả đã tính. Trong môi trường nhiều thread, computing supplier chỉ được gọi thành công tối đa một lần; các thread khác chờ kết quả được thiết lập.

Nếu supplier ném exception, exception được truyền lại cho caller đầu tiên và không có nội dung nào được lưu. Lần get() sau có thể thử tính lại. Nếu supplier gọi đệ quy chính supplier đó, API ném IllegalStateException.

StableValue.supplier thích hợp cho một giá trị lazy đơn lẻ như logger, parser hoặc component. Nếu cần truy vấn trạng thái set/unset hoặc thiết lập từ nhiều nơi, giữ StableValue trực tiếp sẽ linh hoạt hơn.

## 10. StableValue.intFunction(): cache theo chỉ số

StableValue.intFunction(size, underlying) tạo một IntFunction lưu kết quả riêng cho từng input trong khoảng [0, size):

~~~java
import java.util.function.IntFunction;
import java.lang.StableValue;

public final class Powers {
    private static final IntFunction<Integer> POWER_OF_TWO =
            StableValue.intFunction(6, index -> 1 << index);

    public static int powerOfTwo(int exponent) {
        return POWER_OF_TWO.apply(exponent);
    }
}
~~~

Trong ví dụ, các giá trị 2^0 đến 2^5 được tính khi cần và giữ lại theo từng index. Mỗi input hợp lệ chỉ được tính thành công tối đa một lần, kể cả khi nhiều thread cùng gọi.

Input ngoài phạm vi [0, size) gây IllegalArgumentException. Nếu underlying function ném exception, exception được truyền lại và giá trị cho input đó chưa được lưu; lần gọi sau có thể thử lại.

Dạng này phù hợp với bảng tra cứu có miền input nguyên nhỏ và xác định trước, chẳng hạn bảng cấu hình theo level, mã trạng thái hoặc tham số thuật toán.

## 11. StableValue.function(): cache theo tập khóa cho trước

Khi input không phải số nguyên liên tiếp, dùng StableValue.function(inputs, underlying):

~~~java
import java.util.Set;
import java.util.function.Function;
import java.lang.StableValue;

public final class LogTable {
    private static final Set<Integer> KEYS =
            Set.of(1, 2, 4, 8, 16, 32);

    private static final Function<Integer, Integer> LOG2 =
            StableValue.function(
                    KEYS,
                    value -> 31 - Integer.numberOfLeadingZeros(value));

    public static int log2(int value) {
        return LOG2.apply(value);
    }
}
~~~

Function chỉ chấp nhận các input nằm trong tập KEYS. Input không thuộc tập sẽ gây IllegalArgumentException. Kết quả cho mỗi input được tính lazy và lưu sau lần tính thành công đầu tiên.

Dạng này hữu ích khi số khóa có thể biết trước, chẳng hạn mã sản phẩm hỗ trợ, loại định dạng, enum được ánh xạ sang metadata hoặc tập tham số cấu hình cố định.

StableValue.function không phải cache tổng quát cho mọi input tùy ý. Nếu tập khóa không giới hạn hoặc thay đổi liên tục, cần dùng cache có eviction hoặc cơ chế lưu trữ phù hợp hơn.

## 12. StableValue.list(): danh sách bất biến có phần tử lazy

StableValue.list(size, mapper) tạo một List không sửa được, trong đó từng phần tử chỉ được tính khi truy cập lần đầu:

~~~java
import java.util.List;
import java.lang.StableValue;

public final class RuleCatalog {
    private static final int RULE_COUNT = 100;

    private static final List<Rule> RULES =
            StableValue.list(RULE_COUNT, RuleCatalog::loadRule);

    public static Rule rule(int index) {
        return RULES.get(index);
    }

    private static Rule loadRule(int index) {
        return Rule.load(index);
    }
}
~~~

Danh sách có kích thước cố định và không hỗ trợ các thao tác sửa đổi. Mapper được gọi tối đa một lần thành công cho mỗi index. Những thread cùng truy cập một phần tử đang được tính sẽ chờ kết quả đó.

Các view subList và reversed của stable list cũng giữ đặc tính lazy. List này phù hợp khi danh sách vị trí đã biết trước nhưng chi phí tạo từng phần tử có thể trì hoãn.

Mapper của StableValue.list có thể trả về null theo API Java 25. Tuy vậy, với dữ liệu nghiệp vụ, nên cân nhắc dùng Optional hoặc một kiểu biểu diễn trạng thái rõ ràng để tránh null làm khó việc xử lý.

## 13. StableValue.map(): map có khóa cố định, value lazy

StableValue.map(keys, mapper) tạo một Map không sửa được. Tập khóa được xác định ngay khi tạo map, còn giá trị cho từng khóa được tính khi gọi get() lần đầu:

~~~java
import java.util.Map;
import java.util.Set;
import java.lang.StableValue;

public final class FormatCatalog {
    private static final Set<String> FORMATS =
            Set.of("json", "xml", "csv");

    private static final Map<String, Formatter> FORMATTERS =
            StableValue.map(FORMATS, FormatCatalog::loadFormatter);

    public static Formatter formatter(String name) {
        return FORMATTERS.get(name);
    }

    private static Formatter loadFormatter(String name) {
        return Formatter.create(name);
    }
}
~~~

Map không cho thêm hoặc xóa khóa. Mapper chỉ được gọi tối đa một lần thành công cho mỗi khóa. Các view values() và entrySet() cũng giữ tính chất stable theo API.

Dạng này phù hợp với registry có tập khóa xác định nhưng value khởi tạo tốn kém, ví dụ formatter, strategy, adapter hoặc metadata theo loại giao thức.

## 14. Ghép nhiều StableValue thành đồ thị phụ thuộc

Một stable value có thể phụ thuộc vào stable value khác. Điều này giúp chia nhỏ việc khởi tạo component theo dependency:

~~~java
import java.lang.StableValue;

public final class Components {
    private static final StableValue<DatabaseConfig> CONFIG =
            StableValue.of();

    private static final StableValue<DatabaseClient> DATABASE =
            StableValue.of();

    public static DatabaseClient database() {
        return DATABASE.orElseSet(() ->
                new DatabaseClient(
                        CONFIG.orElseSet(DatabaseConfig::load)));
    }
}
~~~

Khi database() được gọi, cấu hình database được tạo trước nếu chưa có, sau đó DatabaseClient được tạo và lưu lại. Những lần gọi sau dùng lại cả hai giá trị.

~~~mermaid
flowchart TD
    A["database()"] --> B["DATABASE.orElseSet"]
    B --> C["CONFIG.orElseSet"]
    C --> D["DatabaseConfig"]
    D --> E["DatabaseClient"]
    E --> F["DATABASE đã được thiết lập"]
~~~

Đồ thị phụ thuộc cần có hướng rõ ràng và không có chu trình. Nếu quá trình khởi tạo quay lại cùng stable value đang được tính, API có thể ném IllegalStateException. Hãy kiểm tra vòng phụ thuộc giữa component trước khi dùng lazy holder cho dependency graph phức tạp.

## 15. Stable Values và constant folding

Lợi ích hiệu năng quan trọng của Stable Values là khả năng cho JVM biết nội dung sau khi set sẽ không đổi. Nếu holder được tham chiếu qua một đường dẫn ổn định, chẳng hạn static final field, JVM có thể:

- Ghi nhớ nội dung đã quan sát.
- Loại bỏ các lần đọc holder không cần thiết.
- Constant-fold một số biểu thức phụ thuộc vào stable value.
- Tối ưu tiếp các phép tính hoặc nhánh điều kiện dựa trên kết quả đó.

Ví dụ:

~~~java
private static final StableValue<Integer> LIMIT =
        StableValue.of();

static int limit() {
    return LIMIT.orElseSet(() -> loadLimit());
}
~~~

Sau khi LIMIT được thiết lập, JVM **có thể** tối ưu các lần đọc về sau. Đây là cơ hội tối ưu hóa, không phải lời hứa rằng compiler sẽ luôn thay mọi lần đọc bằng một hằng số trong mọi bản build hoặc mọi workload.

StableValue cũng không phải compile-time constant theo nghĩa hằng số primitive/String được khai báo bằng static final và constant expression. Giá trị chỉ được xác định ở runtime; JIT có thể tối ưu sau khi quan sát được trạng thái đã set.

Để đánh giá hiệu năng, cần đo:

- Thời gian khởi động trước khi dùng component.
- Độ trễ lần truy cập đầu tiên, khi supplier thực sự chạy.
- Độ trễ các lần truy cập tiếp theo.
- Throughput dưới nhiều thread.
- Allocation và memory footprint của object được giữ lại.

Đừng chỉ đo lần truy cập thứ hai rồi kết luận toàn bộ ứng dụng nhanh hơn. Chi phí khởi tạo vẫn tồn tại, chỉ được chuyển sang thời điểm sử dụng đầu tiên.

## 16. StableValue khác các cách lazy initialization truyền thống

| Cách triển khai | Khởi tạo trễ | Thread-safe | Giá trị không đổi sau khi set | JVM có thể tối ưu như stable constant |
| --- | --- | --- | --- | --- |
| Eager final field | Không | Có sau constructor | Có | Có thể |
| synchronized getter | Có | Có nếu mọi truy cập đi qua getter | Theo thiết kế ứng dụng | Không có bảo đảm stable-value semantics |
| Double-checked locking | Có | Có nếu dùng volatile đúng cách | Theo thiết kế ứng dụng | Không có bảo đảm stable-value semantics |
| Initialization-on-demand holder idiom | Có, cho static state | Có nhờ class initialization | Có nếu field final | Có thể tối ưu final field |
| JDK 25 StableValue | Có | Có theo hợp đồng API | Có với nội dung holder | JVM có thể constant-fold sau khi set |

### Khi nào vẫn nên dùng holder idiom?

Nếu cần khởi tạo một static singleton và không cần khởi tạo theo instance hoặc theo một nhánh logic phức tạp, initialization-on-demand holder idiom vẫn là một cách đơn giản, ổn định và không cần preview:

~~~java
public final class GlobalParser {
    private GlobalParser() {}

    private static class Holder {
        static final Parser INSTANCE = Parser.load();
    }

    public static Parser instance() {
        return Holder.INSTANCE;
    }
}
~~~

StableValue hữu ích khi muốn biểu diễn rõ một giá trị chưa được set nhưng sẽ bất biến sau khi set, đặc biệt khi giá trị nằm trong một object instance hoặc trong một dependency graph. Vì API JDK 25 còn preview, lựa chọn thay thế ổn định vẫn có giá trị với thư viện hoặc hệ thống cần tương thích lâu dài.

## 17. Xử lý lỗi, thử lại và phụ thuộc vòng

Trong JDK 25, nếu supplier của orElseSet ném unchecked exception:

1. Exception được truyền lại cho caller đang thực hiện tính.
2. StableValue vẫn ở trạng thái unset.
3. Lần gọi sau có thể thử chạy supplier lại.

Điều này khác với LazyConstant trong JDK 26 trở lên: nếu computing function ném unchecked exception, lazy constant chuyển sang error state; những lần get() sau ném NoSuchElementException và không gọi computing function lại.

| Tình huống | StableValue JDK 25 | LazyConstant JDK 26+ |
| --- | --- | --- |
| Tính thành công | Lưu giá trị và dùng lại. | Lưu giá trị và dùng lại. |
| Hai thread cùng khởi tạo | Chỉ một supplier hoàn tất thành công để set; thread khác chờ. | Chỉ một computing function được chọn; thread khác chờ. |
| Supplier ném unchecked exception | Exception được truyền lại; holder chưa set, lần gọi sau có thể thử lại. | Chuyển sang error state; lần get sau ném NoSuchElementException. |
| Kết quả null | StableValue API JDK 25 có thể biểu diễn nội dung null; dùng isSet() để phân biệt trạng thái. | LazyConstant không cho phép null; get() thất bại nếu computing function trả null. |

Vì semantics lỗi đã thay đổi, khi chuyển source từ JDK 25 sang JDK 26+, hãy kiểm tra lại cách ứng dụng xử lý lỗi khởi tạo. Nếu supplier có thể thất bại tạm thời do mạng hoặc cấu hình chưa sẵn sàng, hành vi retry của JDK 25 và error state của LazyConstant có thể dẫn tới kết quả vận hành khác nhau.

### Tránh khởi tạo đệ quy

Ví dụ không nên dùng:

~~~java
private static final StableValue<String> VALUE = StableValue.of();

static String value() {
    return VALUE.orElseSet(() -> value());
}
~~~

Supplier gọi lại chính accessor đang khởi tạo cùng holder. Trường hợp này có thể ném IllegalStateException. Tương tự, hai stable values phụ thuộc vòng tròn vào nhau cũng có thể thất bại khi khởi tạo.

## 18. Các giới hạn cần biết trước khi áp dụng

### Nội dung không thể bị gỡ bỏ

StableValue không có thao tác unset hoặc clear. Khi holder đã được thiết lập, nó giữ tham chiếu mạnh tới nội dung. Nếu holder còn reachable trong thời gian dài, nội dung cũng còn reachable. Dùng StableValue cho cache vô hạn hoặc object gắn với request có thể giữ bộ nhớ lâu hơn dự kiến.

### Holder ổn định không làm object mutable thành immutable

Nếu StableValue giữ một object mutable, reference không thay đổi nhưng trạng thái bên trong object vẫn có thể đổi. Muốn dữ liệu bất biến, hãy dùng immutable object hoặc bảo vệ trạng thái mutable theo quy tắc đồng bộ riêng.

### Array reference không đồng nghĩa từng phần tử là stable

Nếu StableValue giữ một array, JVM chỉ có thể xem reference tới array là stable; không suy ra từng phần tử trong array cũng bất biến. Nếu cần các phần tử được tính và giữ ổn định riêng theo index, cân nhắc StableValue.list hoặc StableValue.intFunction.

### Không Serializable

StableValue, stable functions và stable collections của JDK 25 không triển khai Serializable. Không dùng chúng làm dữ liệu trực tiếp cần serialize hoặc truyền qua cơ chế persistence Java serialization.

### Tránh synchronized trực tiếp trên StableValue

Implementation của StableValue được phép đồng bộ trên chính đối tượng holder. Vì vậy không nên dùng holder làm monitor:

~~~java
synchronized (stableValue) {
    // Không nên khóa trực tiếp trên StableValue
}
~~~

Việc khóa cùng monitor có thể dẫn đến deadlock nếu implementation cũng cần monitor đó trong quá trình set/get.

## 19. Ví dụ tổng hợp: lazy component và bảng tra cứu

Ví dụ dưới đây kết hợp StableValue, stable supplier và stable list:

~~~java
import java.lang.StableValue;
import java.util.List;
import java.util.function.Supplier;
import java.util.logging.Logger;

public final class StableValueDemo {
    private static final Supplier<Logger> LOGGER =
            StableValue.supplier(
                    () -> Logger.getLogger(StableValueDemo.class.getName()));

    private static final StableValue<Settings> SETTINGS =
            StableValue.of();

    private static final List<String> LABELS =
            StableValue.list(4, index -> "label-" + index);

    private static Settings settings() {
        return SETTINGS.orElseSet(Settings::load);
    }

    public static void main(String[] args) {
        LOGGER.get().info("Application starting");

        Settings settings = settings();
        LOGGER.get().info("Mode: " + settings.mode());

        System.out.println(LABELS.get(2));
        System.out.println(LABELS.get(2));
    }

    record Settings(String mode) {
        static Settings load() {
            return new Settings("production");
        }
    }
}
~~~

Biên dịch và chạy trên JDK 25:

~~~bash
javac --enable-preview --release 25 StableValueDemo.java
java --enable-preview StableValueDemo
~~~

Quan sát:

- LOGGER chỉ tạo Logger khi lần đầu gọi get().
- SETTINGS chỉ load Settings khi gọi settings().
- LABELS chỉ tính phần tử tại index 2 khi get(2) được gọi lần đầu.
- Lần get(2) tiếp theo nhận giá trị đã lưu.

Ví dụ nhằm minh họa API và cần được chạy bằng JDK 25. Trong ứng dụng thực tế, thay Settings.load() bằng nguồn cấu hình có xử lý lỗi, timeout và chính sách retry rõ ràng.

## 20. Kiểm thử tính an toàn và hiệu năng

Không nên chỉ kiểm tra rằng supplier được gọi một lần trong một thread. Hãy kiểm tra cả cạnh tranh đa luồng và trường hợp supplier thất bại.

### Kiểm thử khởi tạo đồng thời

1. Tạo một StableValue chưa set.
2. Khởi chạy nhiều thread cùng gọi orElseSet với supplier tăng AtomicInteger.
3. Đợi tất cả thread hoàn tất.
4. Xác nhận mọi thread nhận cùng object reference.
5. Xác nhận supplier hoàn tất thành công đúng một lần.

### Kiểm thử supplier thất bại

1. Cho supplier ném exception trong lần gọi đầu.
2. Xác nhận exception được truyền lại và isSet() vẫn false.
3. Gọi lại orElseSet bằng supplier có thể thành công.
4. Xác nhận holder được set sau lần thành công.
5. So sánh hành vi này với LazyConstant trên JDK mới hơn.

### Kiểm thử hiệu năng

So sánh ba cách triển khai: eager final, synchronized lazy getter và StableValue. Dùng cùng workload và cùng JDK build; đo startup, lần truy cập đầu tiên, các lần đọc tiếp theo, throughput nhiều thread và allocation. Nếu cần benchmark microbenchmark, dùng JMH với warm-up và fork phù hợp.

Stable Values được thiết kế để mở ra cơ hội constant folding, nhưng kết quả phụ thuộc JIT, vị trí holder, workload và mức độ ổn định của dữ liệu. Không khẳng định nhanh hơn chỉ dựa trên một lần chạy hoặc một con số latency.

## 21. Hướng dẫn chuyển từ StableValue sang LazyConstant

Từ JDK 26, API được đổi tên từ StableValue thành LazyConstant và cách sử dụng holder đơn lẻ chuyển sang mô hình Supplier:

~~~java
// JDK 25 — JEP 502
private final StableValue<Logger> logger = StableValue.of();

Logger logger() {
    return logger.orElseSet(() -> createLogger());
}
~~~

~~~java
// JDK 26+ — Lazy Constants preview
private final LazyConstant<Logger> logger =
        LazyConstant.of(() -> createLogger());

Logger logger() {
    return logger.get();
}
~~~

Các stable collection của JDK 25 như StableValue.list/map/function/intFunction cũng được tái tổ chức trong các release sau thành các factory lazy tương ứng trên collection APIs, chẳng hạn List.ofLazy và Map.ofLazy; JDK 27 bổ sung Set.ofLazy. Không giả định các static factory cũ còn tồn tại trong java.lang.StableValue sau khi nâng JDK.

Checklist chuyển đổi:

1. Xác định source đang dùng JDK 25 StableValue hay LazyConstant ở release mới.
2. Đổi type và factory theo API đích; không chỉ thay tên import.
3. Rà soát hành vi supplier exception: JDK 25 cho phép thử lại sau khi supplier ném exception, còn LazyConstant chuyển sang error state.
4. Rà soát null: LazyConstant không nhận nội dung null; dùng Optional nếu cần biểu diễn thiếu giá trị.
5. Chuyển stable list/map/function sang các lazy collection/function API tương ứng của release đích.
6. Biên dịch và chạy lại test concurrency, retry, memory retention và hiệu năng trên JDK mục tiêu.

## 22. Bài tập thực hành

### Bài A — Lazy Logger

Tạo class có StableValue<Logger>. Khởi tạo Logger trong orElseSet và gọi accessor từ nhiều thread.

**Đạt:** giải thích được vì sao chỉ một supplier hoàn tất thành công và các thread nhận cùng Logger.

### Bài B — So sánh trySet và orElseSet

Cho nhiều thread tạo các Configuration candidate rồi gọi trySet. Đếm số candidate được tạo và số candidate được lưu. Sau đó lặp lại bằng orElseSet.

**Đạt:** phân biệt số lần tạo candidate với số lần thiết lập thành công.

### Bài C — Stable int function

Tạo bảng bình phương hoặc lũy thừa cho một miền index cố định bằng StableValue.intFunction. Thử input trong và ngoài phạm vi.

**Đạt:** giải thích được cache theo input và IllegalArgumentException khi input vượt miền.

### Bài D — Stable map

Tạo map formatter cho một tập key cố định. Chỉ load formatter khi gọi get(key); xác nhận lần gọi tiếp theo dùng lại value.

**Đạt:** hiểu map không sửa được, tập key cố định và mapper chạy tối đa một lần thành công trên mỗi key.

### Bài E — Supplier thất bại rồi thử lại

Viết supplier thất bại lần đầu và thành công lần hai. Kiểm tra isSet() và số lần gọi supplier trong JDK 25.

**Đạt:** giải thích được exception không làm StableValue chuyển sang error state cố định trong API JDK 25.

### Bài F — Nâng cấp JDK

Chuyển ví dụ StableValue sang LazyConstant của JDK 26/27. Thử lại trường hợp supplier ném exception và so sánh kết quả.

**Đạt:** chỉ ra được thay đổi tên API, package/type và failure semantics giữa các release.

## 23. Câu hỏi tự kiểm tra

1. StableValue khác final field ở thời điểm khởi tạo như thế nào?
2. JEP nào giới thiệu Stable Values trong Java 25?
3. Vì sao Stable Values là preview API trong JDK 25?
4. trySet khác orElseSet ở số lần supplier có thể chạy như thế nào?
5. happens-before của StableValue giúp bảo đảm điều gì?
6. StableValue.supplier khác một Supplier thông thường như thế nào?
7. StableValue.intFunction giới hạn miền input ra sao?
8. StableValue.list và StableValue.map lưu kết quả theo đơn vị nào?
9. Vì sao StableValue không tự làm object mutable trở thành immutable?
10. Constant folding có phải bảo đảm hiệu năng của API không?
11. Vì sao không nên synchronize trực tiếp trên StableValue?
12. Điều gì xảy ra nếu supplier ném unchecked exception trong JDK 25?
13. StableValue khác LazyConstant ở JDK 26+ như thế nào?
14. Tại sao không thể dùng class file preview Java 25 nguyên trạng trên JDK 26?

## 24. Tài liệu tham khảo chính thức

- [JEP 502 — Stable Values (Preview)](https://openjdk.org/jeps/502): mục tiêu và thiết kế Stable Values trong Java 25.
- [StableValue — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StableValue.html): toàn bộ API, stable supplier/function/collection, thread safety và performance notes.
- [Stable Values — Java 25 Core Libraries Guide](https://docs.oracle.com/en/java/javase/25/core/lazy-constants.html): bài toán lazy initialization, ví dụ StableValue và constant folding.
- [Preview Features — Java SE 25](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): cách biên dịch và chạy preview API.
- [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): đổi tên và API tiếp nối trong JDK 26.
- [LazyConstant — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API LazyConstant và semantics khởi tạo/lỗi.
- [Lazy Constants — Java 27 Core Libraries Guide](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): cách dùng LazyConstant, lazy collections và constant folding.
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): thay đổi ở JDK 27.
- [JEP 547 — Lazy Constants (Fourth Preview)](https://openjdk.org/jeps/547): trạng thái preview tiếp theo được nhắm tới JDK 28.
- [Inside Java — JEP targeted to JDK 28: 547 Lazy Constants](https://inside.java/2026/11/20/jep547-target-jdk28/): thông báo JEP 547 được nhắm tới JDK 28.

**Ghi chú tính hiện hành:** Stable Values trong JDK 25 là preview lần đầu, được cung cấp qua java.lang.StableValue và yêu cầu --enable-preview. Từ JDK 26, tên tính năng chuyển thành Lazy Constants và API thay đổi; JDK 27 tiếp tục preview lần ba, còn JDK 28 được nhắm tới preview lần bốn. Tại ngày 27/11/2026, chưa có bản GA nào biến API này thành tính năng final. Hãy dùng tài liệu và chữ ký API đúng release thay vì trộn StableValue của JDK 25 với LazyConstant của JDK mới hơn.

**Kết quả cần nộp:** chương trình Java 25 minh họa StableValue, stable supplier, ít nhất một stable function hoặc collection, bài kiểm thử đa luồng, bài kiểm thử supplier thất bại/thử lại, lệnh biên dịch/chạy preview và bảng đối chiếu JDK 25/26/27/28. Kết quả cần cho thấy bạn hiểu mục đích, giới hạn và trạng thái preview của Stable Values trong Java 25.
