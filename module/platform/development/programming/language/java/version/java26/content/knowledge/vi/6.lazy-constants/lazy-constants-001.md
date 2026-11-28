# Lazy Constants preview lần 2 ở Java 26, lần 3 ở Java 27

Lazy Constants cung cấp cách giữ một giá trị được tính ở lần truy cập đầu tiên và không thay đổi sau khi đã khởi tạo. Ứng dụng có thể trì hoãn việc tạo một thành phần đắt đỏ cho đến khi thật sự cần, trong khi JVM vẫn có cơ hội xem giá trị đã khởi tạo như một hằng để tối ưu tương tự field `final`.

Đây là preview API, không phải API Java SE ổn định. Java 26 cung cấp lần preview thứ hai qua JEP 526. Java 27 tiếp tục qua JEP 531, bổ sung lazy set và điều chỉnh API cùng cách xử lý lỗi. Tại thời điểm hiện tại, JDK 27 đã phát hành chính thức nhưng Lazy Constants vẫn ở trạng thái preview; cần bật preview khi biên dịch và chạy.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa khởi tạo eager, lazy thông thường và lazy constant.
- Dùng `LazyConstant.of(...)` và `get()` để khởi tạo một giá trị đúng một lần khi được yêu cầu.
- Hiểu cơ chế thread safety, safe publication, xử lý lỗi và tối ưu constant folding.
- Dùng `List.ofLazy`, `Map.ofLazy` và `Set.ofLazy` để trì hoãn việc tính từng phần tử, giá trị hoặc trạng thái membership.
- Nhận biết thay đổi API từ Java 26 sang Java 27 và tránh phụ thuộc vào phương thức preview đã bị loại bỏ.
- Đánh giá trường hợp phù hợp để thử nghiệm, các giới hạn bộ nhớ và lý do chưa nên dùng trong production.

## 1. Lịch sử và trạng thái API

| Phiên bản | JEP | Trạng thái và thay đổi chính |
|---|---|---|
| Java 26 | JEP 526 | Preview lần 2; API chính là `LazyConstant.of(Supplier)` và `get()`, kèm `isInitialized()` và `orElse()`; có `List.ofLazy` và `Map.ofLazy` |
| Java 27 | JEP 531 | Preview lần 3; loại bỏ `isInitialized()` và `orElse()`, bổ sung `Set.ofLazy`; thay đổi cách xử lý lỗi khi tính giá trị thất bại |

Không nhầm trạng thái phát hành JDK với trạng thái của JEP. Java 27 đã GA từ ngày 15-09-2026, nhưng Lazy Constants vẫn được đánh dấu preview trong API Java SE 27. Preview có thể tiếp tục thay đổi hoặc bị loại bỏ ở release sau.

Các ví dụ chính trong bài sử dụng API Java 27 hiện hành. Phần so sánh Java 26 chỉ nêu khác biệt cần biết khi nâng cấp mã nguồn từng thử nghiệm với JDK 26.

## 2. Vì sao cần lazy constant?

Một field `final` thông thường được gán khi đối tượng được tạo hoặc khi class được khởi tạo:

```java
public final class ReportService {
    private final ReportParser parser = new ReportParser();

    public Report parse(String input) {
        return parser.parse(input);
    }
}
```

Nếu `ReportParser` tốn thời gian hoặc bộ nhớ để tạo nhưng ứng dụng không bao giờ gọi `parse`, chi phí đó vẫn phát sinh. Có thể trì hoãn việc tạo parser bằng lazy initialization tự quản lý:

```java
public final class ReportService {
    private ReportParser parser;

    public synchronized ReportParser parser() {
        if (parser == null) {
            parser = new ReportParser();
        }
        return parser;
    }

    public Report parse(String input) {
        return parser().parse(input);
    }
}
```

Đoạn mã trên cần đồng bộ hóa để tránh nhiều thread cùng tạo parser. Việc đọc field không phải `final` cũng không cung cấp cho JVM cùng cơ hội tối ưu như một giá trị bất biến. Nếu bỏ `synchronized` đơn giản, có thể có nhiều instance được tạo và các thread có thể quan sát trạng thái không mong muốn.

Lazy constant tách thời điểm khởi tạo khỏi tính bất biến sau khởi tạo:

```java
import java.lang.LazyConstant;

public final class ReportService {
    private static final LazyConstant<ReportParser> PARSER =
            LazyConstant.of(ReportParser::new);

    public Report parse(String input) {
        return PARSER.get().parse(input);
    }
}
```

Giả sử `ReportParser` là thành phần stateless có thể dùng chung, khi tạo `ReportService`, supplier chưa chạy. Lần đầu gọi `PARSER.get()`, `ReportParser` được tạo và gắn vào lazy constant. Các lần gọi sau nhận lại cùng giá trị đó.

## 3. `LazyConstant<T>` hoạt động thế nào?

`LazyConstant<T>` là một interface preview trong package `java.lang`, đồng thời là một `Supplier<T>`. Factory hiện hành là:

```java
static <T> LazyConstant<T> of(Supplier<? extends T> computingFunction)
```

Quá trình hoạt động:

1. Gọi `LazyConstant.of(...)` để tạo holder và cung cấp hàm tính giá trị. Hàm chưa được thực thi ở bước này.
2. Khi gọi `get()` lần đầu, thread thực hiện lời gọi sẽ chạy hàm tính giá trị.
3. Nếu tính thành công và trả về giá trị hợp lệ, lazy constant được khởi tạo.
4. Những lần `get()` tiếp theo trả về cùng giá trị đã lưu, không chạy lại supplier.

Ví dụ dùng `Pattern`, một đối tượng phù hợp để chia sẻ vì bản thân `Pattern` là immutable:

```java
import java.lang.LazyConstant;
import java.util.regex.Pattern;

public final class EmailValidator {
    private static final LazyConstant<Pattern> EMAIL_PATTERN =
            LazyConstant.of(() -> Pattern.compile(
                    "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$"));

    public static boolean isValid(String email) {
        return EMAIL_PATTERN.get().matcher(email).matches();
    }
}
```

`EMAIL_PATTERN` được khai báo `static final` để tham chiếu tới lazy constant ổn định. Nếu ứng dụng không gọi `isValid`, regex chưa cần được biên dịch. Khi được gọi, kết quả được tính một lần và tái sử dụng.

Lưu ý về tính bất biến: lazy constant bảo đảm liên kết giữa holder và giá trị chỉ được thiết lập một lần. Nó không tự biến toàn bộ object graph thành immutable. Ví dụ, nếu supplier trả về một `ArrayList`, danh sách đó vẫn có thể bị sửa thông qua reference được trả về từ `get()`. Nên lưu các giá trị immutable hoặc bảo đảm không sửa nội dung sau khi khởi tạo.

## 4. Thread safety và công bố giá trị

`LazyConstant.get()` bảo đảm việc khởi tạo nguyên tử và tối đa một lần. Nếu nhiều thread gọi `get()` đồng thời:

- Chỉ một thread được chọn để chạy supplier.
- Các thread còn lại chờ cho đến khi việc khởi tạo thành công hoặc thất bại.
- Khi thành công, mọi thread nhận cùng giá trị đã được khởi tạo.
- Việc tính giá trị và khởi tạo xảy ra trước khi thread đọc giá trị; các field `final` bên trong object mới tạo được safe publication theo quan hệ happens-before.

Supplier chạy trên thread đầu tiên thực hiện việc khởi tạo. Vì vậy, nếu supplier thực hiện thao tác chậm, các thread khác đang gọi cùng lazy constant có thể phải chờ. API không cung cấp timeout hoặc cơ chế hủy việc khởi tạo. Ngắt thread thực hiện supplier không làm `get()` tự hủy quá trình tính hoặc ném `InterruptedException`.

Không đặt công việc mạng, truy vấn database có thể treo lâu hoặc thao tác cần hủy theo request vào supplier dùng chung nếu các thread khác không thể chờ vô hạn. Hãy đo thời gian khởi tạo và quyết định có nên trì hoãn nó hay cần một cơ chế bất đồng bộ hoặc timeout riêng.

## 5. Xử lý giá trị null, exception và phụ thuộc vòng

Lazy constant không thể chứa `null`. Nếu supplier trả về `null`, API coi đó là lỗi. Nếu ứng dụng cần biểu diễn trường hợp không có giá trị, hãy dùng `Optional<T>` làm nội dung:

```java
LazyConstant<Optional<ReportParser>> OPTIONAL_PARSER =
        LazyConstant.of(() -> Optional.ofNullable(createParserOrNull()));
```

Hành vi khi supplier thất bại khác nhau giữa Java 26 và Java 27:

| Tình huống | Java 26 — preview lần 2 | Java 27 — preview lần 3 |
|---|---|---|
| Supplier ném unchecked exception | Exception được truyền tới caller; lazy constant chưa khởi tạo và lần `get()` sau có thể thử tính lại | Lazy constant chuyển sang error state; `get()` ném `NoSuchElementException` có cause là exception gốc; lần sau tiếp tục ném `NoSuchElementException` mà không gọi supplier lại |
| Supplier trả về `null` | Ném `NullPointerException`; không có giá trị được lưu | Chuyển sang error state; `get()` ném `NoSuchElementException` với cause là `NullPointerException` |
| Supplier tự gọi lại `get()` trên chính lazy constant đang tính | Ném `IllegalStateException` và không khởi tạo được | Ném `NoSuchElementException` với cause là `IllegalStateException`, sau đó lazy constant ở error state |

Thay đổi ở Java 27 rất quan trọng khi nâng cấp. Không dùng `LazyConstant` cho phép tính có thể thất bại tạm thời và cần tự động retry, chẳng hạn gọi dịch vụ từ xa hoặc đọc file có thể chưa sẵn sàng. Một khi việc tính đã chuyển sang error state, supplier sẽ không được chạy lại. Hãy thực hiện retry ở tầng riêng trước khi tạo giá trị ổn định, hoặc dùng một abstraction có chính sách retry/cache phù hợp.

Nếu các lazy constant phụ thuộc lẫn nhau, hãy thiết kế đồ thị phụ thuộc theo một chiều. Ví dụ `B` có thể lấy `A.get()` khi tạo `B`; nhưng nếu constructor của `A` lại truy cập `B.get()`, hai lần khởi tạo sẽ đệ quy. Phụ thuộc vòng có thể dẫn tới lỗi khởi tạo. Việc đặt các lazy constant trong static initializer cũng cần chú ý thứ tự khởi tạo class.

## 6. Lazy collections: List, Map và Set

Java 26 có hai factory preview cho collection lazy; Java 27 bổ sung factory thứ ba:

| API | Có từ | Hàm tính | Khi nào tính? |
|---|---:|---|---|
| `List.ofLazy(int, IntFunction)` | Java 26 | Nhận index và trả về phần tử | Lần đầu truy cập từng index, ví dụ `get(index)` |
| `Map.ofLazy(Set, Function)` | Java 26 | Nhận key và trả về value | Lần đầu truy cập value của từng key, ví dụ `get(key)` |
| `Set.ofLazy(Set, Predicate)` | Java 27 | Nhận candidate và trả về boolean | Lần đầu kiểm tra membership của từng candidate, ví dụ `contains(candidate)` |

Các collection này không cho phép sửa cấu trúc. Chúng có tập index, key hoặc candidate được xác định từ lúc tạo; hàm tính chỉ được gọi tối đa một lần cho từng phần tử tương ứng, kể cả khi nhiều thread truy cập đồng thời.

Các factory không cho phép phần tử hoặc key/value `null`. Nếu hàm tính trả về `null`, phần tử lazy không thể được khởi tạo thành công. Các collection là unmodifiable: không thể thêm, xóa hoặc thay thế phần tử sau khi tạo. Tính unmodifiable của collection không làm object được chứa bên trong tự động immutable.

Trong JDK 27, nếu hàm tính của một index, key hoặc candidate ném unchecked exception, trạng thái lazy tương ứng chuyển sang error state. Lần truy cập đầu tiên nhận `NoSuchElementException` có cause là lỗi gốc; lần truy cập sau tiếp tục nhận `NoSuchElementException` và hàm tính không được gọi lại. Quy tắc này áp dụng cho lazy list, lazy map và lazy set.

### Lazy List

`List.ofLazy(size, computingFunction)` tạo danh sách có kích thước cố định. Mỗi index được tính riêng khi lần đầu truy cập:

```java
import java.util.List;
import java.util.regex.Pattern;

static final List<Pattern> ORDER_PATTERNS = List.ofLazy(
        3,
        index -> switch (index) {
            case 0 -> Pattern.compile("ORD-[0-9]{6}");
            case 1 -> Pattern.compile("INV-[0-9]{6}");
            case 2 -> Pattern.compile("RET-[0-9]{6}");
            default -> throw new IndexOutOfBoundsException(index);
        });

static boolean isOrderId(String value) {
    return ORDER_PATTERNS.get(0).matcher(value).matches();
}
```

Trong ví dụ này, chỉ pattern ở index `0` được tạo khi `isOrderId` được gọi. Các index còn lại chưa cần khởi tạo. Nếu duyệt toàn bộ list bằng vòng lặp, stream hoặc `forEach`, các phần tử tương ứng sẽ được truy cập và tính khi cần.

### Lazy Map

`Map.ofLazy(keys, computingFunction)` nhận tập key cố định và tính value theo key khi được truy cập:

```java
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

static final Map<String, Pattern> VALIDATORS = Map.ofLazy(
        Set.of("EMAIL", "ORDER_ID"),
        key -> switch (key) {
            case "EMAIL" -> Pattern.compile(
                    "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");
            case "ORDER_ID" -> Pattern.compile("ORD-[0-9]{6}");
            default -> throw new IllegalArgumentException("Unknown key: " + key);
        });

static boolean validate(String type, String value) {
    Pattern pattern = VALIDATORS.get(type);
    return pattern != null && pattern.matcher(value).matches();
}
```

Các key phải được xác định khi tạo map. Một key không có trong tập ban đầu không làm supplier chạy; `get(key)` trả về `null` theo hợp đồng Map khi không có mapping. Map không cho thêm, xóa hoặc thay đổi key/value. Các thao tác duyệt entry có thể kích hoạt việc tính value cho tất cả key.

### Lazy Set — bổ sung trong Java 27

`Set.ofLazy(candidates, computingFunction)` tạo tập không sửa đổi được, trong đó hàm `Predicate` xác định một candidate có thuộc tập hay không. Kết quả `true` hoặc `false` được ghi nhận tối đa một lần cho mỗi candidate:

```java
import java.util.EnumSet;
import java.util.Set;

enum Feature {
    AUDIT_LOG,
    BETA_REPORT,
    FAST_EXPORT
}

static final Set<Feature> ENABLED_FEATURES = Set.ofLazy(
        EnumSet.allOf(Feature.class),
        LazyConstantsDemo::isEnabled);

static boolean isEnabled(Feature feature) {
    // Thay bằng việc đọc cấu hình đã nạp và kiểm tra được.
    return switch (feature) {
        case AUDIT_LOG -> true;
        case BETA_REPORT -> false;
        case FAST_EXPORT -> true;
    };
}

static boolean auditEnabled() {
    return ENABLED_FEATURES.contains(Feature.AUDIT_LOG);
}
```

Ví dụ trên là API Java 27; `Set.ofLazy` chưa có trong Java 26. Hàm kiểm tra membership chỉ chạy khi một candidate được hỏi lần đầu. Khi duyệt toàn bộ tập, các candidate còn lại cũng sẽ được kiểm tra. Tập candidate đầu vào được chụp tại thời điểm tạo; sửa tập nguồn sau đó không làm tập lazy thay đổi.

## 7. Lazy không có nghĩa là mọi thao tác đều không tính trước

Lazy collection trì hoãn tính từng phần tử, nhưng các thao tác duyệt toàn bộ có thể kích hoạt nhiều hoặc tất cả phép tính:

| Thao tác | Hệ quả thường gặp |
|---|---|
| `list.get(2)` | Tính phần tử index `2` nếu chưa có |
| Duyệt toàn bộ list | Tính mọi index được duyệt |
| `map.get(key)` | Tính value của key đó nếu chưa có |
| Duyệt `map.entrySet()` | Truy cập value của các key, do đó có thể tính tất cả value |
| `set.contains(candidate)` | Tính trạng thái membership của candidate nếu chưa có |
| Duyệt toàn bộ set | Tính trạng thái membership của các candidate |

Các factory lazy collection tạo collection không sửa đổi được, nhưng object bên trong vẫn có thể mutable. `List.ofLazy`, `Map.ofLazy` và `Set.ofLazy` cũng không phải cache có eviction, refresh hoặc khả năng thêm key/candidate mới. Hãy dùng chúng khi miền dữ liệu đã biết và kết quả cần được tính tối đa một lần.

## 8. JVM có thể tối ưu như thế nào?

Sau khi lazy constant được khởi tạo, giá trị của nó không đổi. JVM có thể áp dụng constant folding: thay các lần đọc sau bằng giá trị đã quan sát được, tránh một số lần tải giá trị từ bộ nhớ. Đây là tối ưu mà JVM có thể thực hiện, không phải cam kết mọi lần truy cập sẽ được thay thế bằng hằng số.

Điều kiện quan trọng để JVM nhận diện đường dẫn đáng tin cậy tới lazy constant là:

- Một field `static final` tham chiếu trực tiếp tới lazy constant; hoặc
- Một chuỗi field đáng tin cậy từ `static final` tới lazy constant, chẳng hạn field của record hoặc final instance field trong hidden class.

Vì vậy, ví dụ thường khai báo holder dưới dạng `private static final LazyConstant<T>`. Nếu giữ holder trong field thay đổi được hoặc đường dẫn tham chiếu không thuộc dạng JVM có thể tin cậy, không nên giả định constant folding sẽ xảy ra.

Lợi ích khởi động đến từ việc các giá trị không được truy cập sẽ không phải tạo ngay khi ứng dụng khởi động. Đổi lại, chi phí được chuyển sang lần truy cập đầu tiên. Hãy đo thời gian khởi động, độ trễ lần đầu, mức sử dụng bộ nhớ và hiệu năng ổn định bằng workload thật; đừng mặc định rằng lazy luôn nhanh hơn.

## 9. Những giới hạn cần tính đến

- **Không có eviction:** sau khi khởi tạo, lazy constant giữ reference mạnh tới nội dung cho đến khi holder không còn reachable. Dùng nó cho object lớn có thể giữ bộ nhớ lâu hơn dự kiến.
- **Không serialize:** `LazyConstant` không triển khai `Serializable`.
- **Không chứa null:** dùng `Optional` nếu cần biểu diễn kết quả vắng mặt.
- **Không tự retry ở Java 27:** supplier thất bại sẽ làm holder chuyển sang error state.
- **Có thể chờ vô hạn:** thread khác chờ khi supplier đang chạy; API không cung cấp timeout hoặc cancellation.
- **Không đảm bảo object nội dung immutable:** chỉ bảo đảm giá trị holder không bị thay sau khi khởi tạo.
- **Cẩn thận với khóa:** implementation được phép đồng bộ hóa trên chính lazy constant; không dùng holder làm monitor cho `synchronized`.
- **Cẩn thận với phụ thuộc vòng:** tránh để supplier khởi tạo lại chính nó trực tiếp hoặc gián tiếp.

Không dùng lazy constant cho dữ liệu người dùng thay đổi liên tục, session, token có thời hạn, cache cần refresh, tài nguyên phải đóng/mở theo vòng đời request hoặc thao tác cần retry. Những trường hợp đó cần một abstraction quản lý vòng đời và trạng thái phù hợp.

## 10. Biên dịch và chạy preview trên đúng JDK

Preview API phải được bật ở cả lúc biên dịch và chạy. Dùng compiler và runtime cùng phiên bản JDK:

**Java 26 — JEP 526, preview lần 2:**

```bash
javac --release 26 --enable-preview -Xlint:preview LazyConstantsDemo.java
java --enable-preview LazyConstantsDemo
```

**Java 27 — JEP 531, preview lần 3:**

```bash
javac --release 27 --enable-preview -Xlint:preview LazyConstantsDemo.java
java --enable-preview LazyConstantsDemo
```

Ví dụ dùng `Set.ofLazy` chỉ biên dịch trên JDK 27 trở lên. `List.ofLazy` và `Map.ofLazy` có từ JDK 26 nhưng vẫn là preview trong JDK 27. Không thể dùng JDK 27 để bật preview của Java 26 chỉ bằng cách đặt `--release 26`; `--enable-preview` áp dụng cho preview của JDK đang chạy compiler.

Nếu dùng Maven hoặc Gradle, cấu hình cờ preview cho cả compiler và JVM chạy test/ứng dụng. Giới hạn cấu hình vào module hoặc source set dùng API này để các phần còn lại không phải bật preview. Kiểm tra JDK của toolchain, JVM của build tool và JVM thực thi test; chúng có thể là các cấu hình riêng.

## 11. Nâng cấp mã thử nghiệm từ Java 26 lên Java 27

Khi chuyển thử nghiệm từ JDK 26 sang JDK 27, kiểm tra các điểm sau:

| Mã Java 26 preview lần 2 | Java 27 preview lần 3 |
|---|---|
| `LazyConstant.of(supplier)` và `get()` | Tiếp tục dùng |
| `isInitialized()` | Đã bị loại bỏ; không gọi trong mã mới |
| `orElse(value)` | Đã bị loại bỏ; không gọi trong mã mới |
| `List.ofLazy(...)` | Tiếp tục có, vẫn preview |
| `Map.ofLazy(...)` | Tiếp tục có, vẫn preview |
| Chưa có `Set.ofLazy(...)` | Có `Set.ofLazy(...)`, vẫn preview |
| Supplier ném unchecked exception có thể được thử lại ở lần `get()` sau | Lazy constant chuyển sang error state; không thử lại supplier |

Mã nguồn từng gọi `isInitialized()` hoặc `orElse()` sẽ không biên dịch với API Java 27. Thiết kế mới nên dùng `get()` theo mục tiêu của lazy constant: yêu cầu giá trị khi thật sự cần, không thăm dò trạng thái khởi tạo để thay đổi hành vi. Nếu ứng dụng cần biết trạng thái, retry hoặc fallback theo trạng thái, hãy quản lý điều đó bằng abstraction khác.

## 12. Khi nào nên thử nghiệm và khi nào nên tránh?

Trường hợp đáng thử nghiệm:

- Thành phần dùng chung có chi phí tạo đáng kể nhưng chỉ một phần luồng chạy cần tới.
- Bảng quy tắc, parser hoặc cấu hình có tập phần tử biết trước và phần lớn không được truy cập trong một lần chạy.
- Các giá trị có thể tính đúng một lần, không cần refresh và có vòng đời gần với vòng đời ứng dụng.

Trường hợp nên chọn giải pháp khác:

- Giá trị phụ thuộc trạng thái bên ngoài và có thể thay đổi sau khi tạo.
- Supplier có thể lỗi tạm thời, cần retry, timeout hoặc hủy.
- Object cần giải phóng tài nguyên, eviction hoặc quản lý vòng đời theo request.
- Giá trị có thể bị truy cập rất ít nhưng giữ reference lớn làm tăng footprint bộ nhớ.

Vì Lazy Constants vẫn là preview trong Java 27, không đưa API này vào hợp đồng thư viện production hoặc sản phẩm cần tương thích Java SE ổn định. Hãy dùng để thử nghiệm trên đúng JDK, theo dõi các JEP tiếp theo và chỉ cân nhắc chuyển sang production sau khi API được final trong một release được hệ thống hỗ trợ.

## 13. Bài tập thực hành

Tạo một chương trình Java 27 mô phỏng hệ thống báo cáo có nhiều bộ kiểm tra đầu vào, nhưng mỗi lần chạy chỉ dùng một số bộ kiểm tra.

**Yêu cầu:**

1. Tạo `LazyConstant<Pattern>` cho bộ kiểm tra email và chỉ gọi `get()` khi người dùng yêu cầu kiểm tra email.
2. Tạo `List<Pattern>` bằng `List.ofLazy(3, ...)` cho ba định dạng mã đơn hàng; chứng minh chỉ index được truy cập mới được tính.
3. Tạo `Map<String, Pattern>` bằng `Map.ofLazy(...)` với tập key cố định.
4. Tạo `Set<Feature>` bằng `Set.ofLazy(...)` để xác định feature flag được bật; kiểm tra cùng một candidate nhiều lần.
5. Dùng hai thread cùng gọi `get()` trên một lazy constant có supplier ghi nhận số lần chạy; xác minh supplier chỉ được gọi tối đa một lần.
6. Tạo một supplier ném unchecked exception và quan sát khác biệt giữa Java 26 preview lần 2 với Java 27 preview lần 3.
7. Biên dịch và chạy bằng đúng JDK với `--enable-preview`; giải thích vì sao không nên triển khai API này trong production hiện tại.

**Kết quả mong đợi:**

- Giá trị đơn được tính ở lần `get()` đầu tiên và giữ nguyên ở những lần tiếp theo.
- Các thread cạnh tranh cùng khởi tạo chỉ có một thread chạy supplier; thread còn lại chờ kết quả.
- Lazy list, map và set chỉ tính phần tử/key/candidate khi cần; duyệt toàn bộ có thể kích hoạt nhiều phép tính.
- Mã Java 27 không dùng `isInitialized()` hoặc `orElse()`; có thể dùng `Set.ofLazy`.
- Lỗi supplier trên Java 27 đưa lazy constant vào error state và không được thử lại tự động.
- Người học phân biệt rõ preview API với API ổn định và biết điều kiện bật preview trên đúng JDK.

## Tài liệu tham khảo

- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): thiết kế Lazy Constants trong Java 26.
- [LazyConstant — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html): API preview lần 2, gồm các phương thức có trong JDK 26.
- [Lazy Constants — Java SE 26 Core Libraries](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html): ví dụ khởi tạo trễ, kết hợp lazy constants, lazy list và lazy map.
- [JEP 531: Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): cập nhật preview trong Java 27.
- [LazyConstant — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API hiện hành, thread safety, exception handling và điều kiện constant folding.
- [Lazy Constants — Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): lazy list, lazy map, lazy set và ví dụ sử dụng.
- [List — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html), [Map — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html) và [Set — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): hợp đồng các factory lazy trong Collections Framework.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Lazy Constants là preview API lần thứ ba trong JDK 27.
