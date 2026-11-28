# Phân biệt tạo phần tử lười với pipeline Stream

Lazy collection và Stream đều có thể trì hoãn công việc cho đến khi dữ liệu được yêu cầu, nhưng chúng giải quyết hai vấn đề khác nhau. Lazy collection giữ một tập hợp có cấu trúc cố định và tính từng phần tử, value hoặc trạng thái membership khi truy cập lần đầu; kết quả thành công được lưu để dùng lại. Stream trì hoãn việc duyệt nguồn và thực hiện các bước biến đổi cho đến khi có terminal operation; pipeline không phải nơi lưu trữ hay cache kết quả đã biến đổi.

Trong Java 26, `List.ofLazy` và `Map.ofLazy` được giới thiệu dưới dạng preview. Java 27 tiếp tục Lazy Constants ở preview và bổ sung `Set.ofLazy`. Stream API đã là API chính thức từ Java 8. Hai cách làm này có thể kết hợp: một Stream có thể đọc từ lazy collection, nhờ đó việc duyệt và biến đổi được trì hoãn, còn các phần tử của collection vẫn được cache sau lần tính đầu tiên.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lazy initialization của phần tử collection với laziness của pipeline Stream.
- Giải thích thời điểm hàm tính chạy và kết quả có được lưu lại hay không.
- Chọn `List.ofLazy`, `Map.ofLazy`, `Set.ofLazy` hoặc Stream theo dạng dữ liệu và vòng đời tính toán.
- Kết hợp lazy collection với Stream mà không nhầm việc cache phần tử với cache kết quả pipeline.
- Nhận biết các thao tác có thể kích hoạt nhiều phép tính, giới hạn của short-circuit và cách xử lý lỗi.
- Bật preview đúng JDK cho lazy collections và tránh đưa API preview vào hợp đồng production.

## 1. Hai ý nghĩa khác nhau của từ “lazy”

**Lazy collection** trì hoãn việc tạo nội dung của một vị trí hoặc một khóa. Ví dụ, `List.ofLazy(100, factory)` tạo một list có kích thước 100 ngay lúc đầu, nhưng chưa cần tạo 100 object. Khi gọi `get(17)`, factory mới tính phần tử ở index 17. Kết quả đó được giữ lại; gọi `get(17)` lần nữa sẽ nhận lại giá trị đã tạo.

**Stream pipeline** trì hoãn việc thực hiện các thao tác như `filter`, `map` và `flatMap`. Khi gọi các intermediate operation, chương trình mới mô tả pipeline. Việc đọc phần tử nguồn và chạy các bước xử lý bắt đầu khi gọi terminal operation như `toList`, `count`, `reduce`, `findFirst` hoặc `forEach`. Stream không tự lưu các kết quả đã map để dùng lại ở lần chạy sau.

| Tiêu chí | Lazy collection | Stream pipeline |
|---|---|---|
| Vai trò | Cung cấp một collection có cấu trúc và nội dung được tính theo yêu cầu | Mô tả quá trình duyệt và biến đổi dữ liệu |
| Khi tính | Khi truy cập vị trí, key hoặc membership tương ứng | Khi pipeline được terminal operation kích hoạt và cần phần tử |
| Lưu kết quả | Cache kết quả thành công theo từng index/key/candidate | Không cache kết quả biến đổi của pipeline |
| Dùng lại | Có thể truy cập lại cùng phần tử đã tính | Một pipeline chỉ được tiêu thụ một lần; muốn chạy lại phải tạo Stream mới |
| Kích thước | Tập index, key hoặc candidate được xác định từ lúc tạo | Có thể hữu hạn hoặc vô hạn |
| Short-circuit | Chỉ phần tử được truy cập mới cần tính; thao tác duyệt có thể truy cập nhiều phần tử | `findFirst`, `anyMatch`, `limit` và các thao tác tương tự có thể dừng pipeline sớm |
| Trạng thái API trong bài | `ofLazy` vẫn là preview trong Java 27 | Stream là API chính thức |

Không nên chọn một trong hai chỉ vì cùng có tính chất trì hoãn. Hãy xác định mình cần lưu kết quả phần tử để tái sử dụng hay cần mô tả một lần xử lý dữ liệu.

## 2. Lazy List: tính từng index và giữ kết quả

`List.ofLazy(int size, IntFunction<? extends E> computingFunction)` tạo một list không sửa đổi được với kích thước xác định. Hàm tính nhận index và chỉ được gọi khi phần tử ở index đó được truy cập lần đầu.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

record Rule(int id, boolean enabled) {}

public class LazyListDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final List<Rule> RULES = List.ofLazy(4, index -> {
        CREATED.incrementAndGet();
        return new Rule(index, index % 2 == 0);
    });

    public static void main(String[] args) {
        System.out.println("Created: " + CREATED.get()); // 0

        Rule third = RULES.get(2);
        System.out.println(third);                       // Rule[id=2, enabled=true]
        System.out.println("Created: " + CREATED.get()); // 1

        Rule sameThird = RULES.get(2);
        System.out.println(third == sameThird);          // true
        System.out.println("Created: " + CREATED.get()); // 1

        RULES.get(0);
        System.out.println("Created: " + CREATED.get()); // 2
    }
}
```

Mỗi index có trạng thái khởi tạo riêng. Đọc index 2 không buộc list tạo index 0, 1 hoặc 3. Sau khi index 2 được tạo thành công, các lần đọc tiếp theo dùng lại cùng object. `CREATED` chỉ là bộ đếm minh họa để quan sát factory; không cần đưa bộ đếm hoặc side effect tương tự vào logic tính phần tử thực tế.

Các đặc điểm cần nhớ:

- Kích thước list được biết ngay từ lúc tạo; `size()` không cần tạo các phần tử.
- List không cho thêm, xóa hoặc thay thế phần tử; nó là unmodifiable.
- Không cho phép phần tử `null`.
- Trong Java 27, computing function được gọi tối đa một lần cho mỗi index, kể cả khi nhiều thread cùng truy cập. Thread cạnh tranh với index đang được tính sẽ chờ kết quả.
- Trong Java 27, nếu factory ném unchecked exception hoặc trả về `null`, index chuyển sang error state; lần truy cập sau không gọi lại factory để retry.
- `subList()` và `reversed()` tiếp tục là các view lazy.

Các thao tác cần đọc nội dung như duyệt list, `contains`, `equals`, `hashCode` hoặc `toString` có thể làm khởi tạo một hoặc nhiều index. Vì vậy, việc log toàn bộ list hoặc đưa list vào phép so sánh có thể làm phát sinh chi phí mà trước đó chưa cần.

## 3. Lazy Map: key cố định, value được tính theo yêu cầu

`Map.ofLazy(Set<? extends K> keys, Function<? super K, ? extends V> computingFunction)` nhận trước tập key hợp lệ. Value của một key chỉ được tính khi truy cập lần đầu, chẳng hạn qua `get(key)`. Trong Java 27, computing function được gọi tối đa một lần cho mỗi key.

```java
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public class LazyMapDemo {
    private static final Map<String, Pattern> VALIDATORS = Map.ofLazy(
            Set.of("EMAIL", "ORDER_ID", "INVOICE_ID"),
            key -> switch (key) {
                case "EMAIL" -> Pattern.compile(
                        "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");
                case "ORDER_ID" -> Pattern.compile("ORD-[0-9]{6}");
                case "INVOICE_ID" -> Pattern.compile("INV-[0-9]{6}");
                default -> throw new IllegalArgumentException("Unknown key: " + key);
            });

    public static boolean validate(String type, String value) {
        Pattern validator = VALIDATORS.get(type);
        return validator != null && validator.matcher(value).matches();
    }
}
```

Tạo map chỉ xác định ba key; các `Pattern` chưa được biên dịch cho đến khi value tương ứng được lấy. `get("EMAIL")` lần đầu tính pattern email; những lần sau dùng lại pattern đã có. `get("UNKNOWN")` trả về `null` theo hợp đồng Map vì key không thuộc tập đã khai báo; computing function không được gọi cho key đó.

`keySet()` chỉ cần các key đã biết, trong khi các value của `values()` và `entrySet()` vẫn được tính lazy khi được truy cập. Duyệt toàn bộ `entrySet`, gọi `values`, hoặc dùng `equals`, `hashCode`, `toString` có thể làm khởi tạo nhiều hoặc tất cả value. Map không cho sửa cấu trúc và không cho key/value `null`.

Tập key đầu vào được dùng làm miền key khi tạo map. Nếu sau đó sửa tập key ban đầu, map lazy không tự cập nhật. Tập key phải có quy tắc tương đương nhất quán với `equals`; không dùng một `Set` có comparator hoặc equality semantics mâu thuẫn.

## 4. Lazy Set: tính trạng thái membership của từng candidate

`Set.ofLazy(Set<? extends E> elementCandidates, Predicate<? super E> computingFunction)` hoạt động khác một list và map. Nó nhận một tập candidate hữu hạn, rồi xác định candidate nào thực sự thuộc set bằng cách gọi predicate khi membership được hỏi lần đầu.

```java
import java.util.EnumSet;
import java.util.Set;

enum Feature {
    AUDIT_LOG,
    BETA_REPORT,
    FAST_EXPORT
}

public class LazySetDemo {
    private static final Set<Feature> ENABLED = Set.ofLazy(
            EnumSet.allOf(Feature.class),
            LazySetDemo::isEnabled);

    private static boolean isEnabled(Feature feature) {
        // Ví dụ minh họa; ứng dụng có thể đọc cấu hình đã nạp.
        return switch (feature) {
            case AUDIT_LOG -> true;
            case BETA_REPORT -> false;
            case FAST_EXPORT -> true;
        };
    }

    public static void main(String[] args) {
        System.out.println(ENABLED.contains(Feature.AUDIT_LOG));  // true
        System.out.println(ENABLED.contains(Feature.BETA_REPORT)); // false
    }
}
```

Khi gọi `contains(AUDIT_LOG)`, predicate được gọi và kết quả `true` được lưu. Với `BETA_REPORT`, predicate chạy và kết quả `false` cũng được lưu. Một candidate đã được đánh giá không cần chạy predicate lần nữa. Candidate không có trong tập đầu vào luôn không thuộc lazy set và không kích hoạt predicate.

Set này không sửa đổi được. Tập candidate được cố định khi tạo; sửa tập nguồn sau đó không làm set lazy thay đổi. Các thao tác cần biết toàn bộ thành viên thực tế như duyệt set, xác định kích thước hoặc so sánh tập có thể phải đánh giá nhiều hay tất cả candidate. `equals`, `hashCode` và `toString` cũng có thể kích hoạt đánh giá membership.

Không nhầm `Set.ofLazy` với một predicate tổng quát trên toàn bộ miền giá trị. Ví dụ, nếu candidate đầu vào là các enum trong `EnumSet.allOf(Feature.class)`, predicate chỉ được hỏi cho các enum đó; một đối tượng khác ngoài miền candidate không được thêm vào set.

## 5. Stream pipeline: trì hoãn phép xử lý, không cache kết quả

Stream không phải collection. Nó không lưu một danh sách kết quả đã tính; nó chuyển các phần tử từ source qua một chuỗi phép xử lý. Các intermediate operation như `filter`, `map`, `flatMap`, `distinct` và `sorted` tạo pipeline mới nhưng chưa bắt đầu duyệt dữ liệu. Terminal operation mới kích hoạt quá trình xử lý.

```java
import java.util.List;

record Product(String name, int price, boolean available) {}

static List<String> availableProductNames(List<Product> products) {
    return products.stream()
            .filter(Product::available)
            .map(Product::name)
            .toList();
}
```

Khi gọi `products.stream().filter(...).map(...)`, chưa có phần tử nào nhất thiết được duyệt. `toList()` kích hoạt pipeline, lọc sản phẩm có sẵn, chuyển thành tên và tạo list kết quả. List kết quả này lưu các tên đã tạo; đó là collection đầu ra của terminal operation, không phải Stream pipeline tự cache.

Một Stream chỉ được tiêu thụ một lần:

```java
var pipeline = products.stream()
        .filter(Product::available)
        .map(Product::name);

var first = pipeline.findFirst();

// Không được gọi pipeline.toList() lần nữa: stream đã được tiêu thụ.
```

Muốn chạy lại phép xử lý, tạo Stream mới từ source:

```java
var firstRun = products.stream()
        .filter(Product::available)
        .map(Product::name)
        .toList();

var secondRun = products.stream()
        .filter(Product::available)
        .map(Product::name)
        .toList();
```

Lần chạy thứ hai duyệt source và thực hiện lại các phép lọc, map. Nếu source là một collection thông thường, những phần tử đã có sẵn vẫn được đọc; nếu phép map tạo object hoặc thực hiện phép tính đắt đỏ, phép tính đó cũng chạy lại. Stream không giữ lại kết quả map của lần chạy đầu.

## 6. Kết hợp lazy collection với Stream

Hai cơ chế có thể hoạt động trong cùng một luồng xử lý. Lazy collection quyết định khi nào phần tử nguồn được tạo và giữ lại; Stream quyết định khi nào các phần tử được duyệt và những phép biến đổi nào được áp dụng.

```java
import java.util.List;

record Rule(int id, boolean enabled) {
    String normalizedName() {
        return "RULE-" + id;
    }
}

static final List<Rule> RULES = List.ofLazy(
        5,
        index -> loadRule(index));

static List<String> enabledRuleNames() {
    return RULES.stream()
            .filter(Rule::enabled)
            .map(Rule::normalizedName)
            .toList();
}

static Rule loadRule(int index) {
    // Thay bằng việc nạp cấu hình hoặc tạo rule từ dữ liệu cố định.
    return new Rule(index, index % 2 == 0);
}
```

Ở lần gọi `enabledRuleNames()` đầu tiên, Stream bắt đầu duyệt `RULES`. Khi iterator yêu cầu một index, lazy list mới gọi `loadRule(index)`. Mỗi rule đã tạo được giữ lại ở index tương ứng. Nếu gọi `enabledRuleNames()` lần nữa, Stream mới sẽ lọc và map lại; `loadRule` không cần chạy lại cho các index đã khởi tạo, nhưng `normalizedName()` vẫn được gọi lại trong pipeline mới.

Short-circuit cũng tác động tới số phần tử lazy được tạo:

```java
var firstEnabled = RULES.stream()
        .filter(Rule::enabled)
        .findFirst();
```

`findFirst()` dừng khi tìm được rule đầu tiên phù hợp. Lazy list chỉ cần tạo các index đã được duyệt tới thời điểm đó. Các index phía sau có thể vẫn chưa khởi tạo. Nếu lần sau dùng một pipeline cần duyệt toàn bộ list, những index còn lại mới được tạo.

Có thể hình dung hai tầng như sau:

```text
List.ofLazy / Map.ofLazy / Set.ofLazy
        │
        │ truy cập phần tử, key hoặc membership
        ▼
Giá trị hoặc trạng thái được tính và cache theo vị trí
        │
        │ Stream source đọc các phần tử khi terminal operation cần
        ▼
filter → map → flatMap → reduce / findFirst / toList
        │
        ▼
Kết quả terminal operation
```

Cache của lazy collection không phải cache cho pipeline. Nếu cần lưu kết quả biến đổi để dùng lại, hãy thu thập thành collection hoặc cache kết quả một cách tường minh sau khi đánh giá yêu cầu bộ nhớ và vòng đời.

## 7. Short-circuit không đồng nghĩa với cache

Stream có thể tránh xử lý phần tử không cần thiết. `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`, `limit` và `takeWhile` có thể dừng sớm tùy kết quả và đặc tính source. Đây là tối ưu về lượng công việc trong một lần duyệt.

Ví dụ:

```java
boolean hasExpensiveProduct = products.stream()
        .filter(Product::available)
        .anyMatch(product -> product.price() > 1_000_000);
```

Nếu tìm thấy sản phẩm đầu tiên thỏa điều kiện, `anyMatch` có thể kết thúc mà không duyệt hết source. Nếu chạy một Stream mới với cùng source, pipeline được thực hiện lại; Stream không nhớ sản phẩm đã xét ở lần trước.

Với lazy list, những phần tử đã được tạo trong lần duyệt đầu vẫn nằm trong list và được dùng lại ở lần sau. Các phần tử chưa được truy cập vẫn chưa được tạo. Đây là khác biệt quan trọng giữa short-circuit của Stream và memoization theo index của lazy collection.

## 8. Không dùng side effect trong Stream để đo số lần tính

Không nên dựa vào side effect trong `map`, `filter` hoặc `peek` để kết luận một pipeline đã chạy bao nhiêu lần. Stream implementation được phép tối ưu và loại bỏ một số stage nếu điều đó không làm thay đổi kết quả của terminal operation. Ví dụ, một phép đếm trên source có kích thước đã biết có thể không cần chạy mapper chỉ để xác định số phần tử.

Nếu cần quan sát việc tạo phần tử lazy, hãy đo ở computing function của lazy collection trong một ví dụ kiểm thử riêng. Nếu cần đo chi phí pipeline, dùng benchmark hoặc instrumentation phù hợp; không biến lambda xử lý dữ liệu thành nơi cập nhật trạng thái dùng chung. Với parallel stream, behavioral parameter cần không can thiệp vào source và thường phải stateless; chia sẻ mutable state có thể gây race condition hoặc contention.

## 9. So sánh cách dùng theo bài toán

| Nhu cầu | Nên cân nhắc | Lý do |
|---|---|---|
| Danh sách có số index cố định, mỗi object đắt để tạo và có thể được truy cập lại | `List.ofLazy` | Tạo theo index và cache kết quả thành công |
| Tập key biết trước, mỗi value cần tính khi được đọc | `Map.ofLazy` | Key có sẵn, value được tính tối đa một lần mỗi key |
| Tập candidate hữu hạn, trạng thái thuộc/không thuộc cần đánh giá khi hỏi | `Set.ofLazy` | Cache cả kết quả membership `true` lẫn `false` |
| Lọc, biến đổi, tổng hợp hoặc tìm phần tử đầu tiên | Stream | Pipeline mô tả phép xử lý và có thể short-circuit |
| Nguồn dữ liệu vô hạn hoặc được sinh liên tục | Stream | Stream có thể biểu diễn nguồn vô hạn; lazy collection có miền index/key/candidate hữu hạn đã xác định |
| Cần tái sử dụng kết quả biến đổi nhiều lần | Thu thập kết quả Stream thành collection hoặc cache riêng | Stream pipeline không tự lưu kết quả map/filter |
| Dữ liệu phụ thuộc trạng thái ngoài có thể thay đổi theo từng lần truy vấn | Stream hoặc cơ chế cache có refresh | Lazy collection giữ kết quả đã tính và không tự làm mới |

Không chọn lazy collection chỉ vì factory có chữ `Lazy`. Nếu mọi phần tử đều sẽ được truy cập ngay, chi phí lưu trạng thái lazy có thể không đem lại lợi ích. Tương tự, không tạo một Stream chỉ để thay thế một collection cần random access và dùng lại nhiều lần.

## 10. Lỗi và giới hạn của lazy collections trong Java 27

`List.ofLazy`, `Map.ofLazy` và `Set.ofLazy` đều có thể đưa vị trí/key/candidate vào error state khi computing function thất bại:

- Nếu computing function ném unchecked exception, lần truy cập đầu tiên nhận `NoSuchElementException` với exception gốc làm cause.
- Những lần truy cập tiếp theo tới cùng index/key/candidate tiếp tục nhận `NoSuchElementException`; computing function không được gọi lại.
- Nếu function trả về `null` trong lazy list hoặc lazy map, API không lưu `null`; lần truy cập nhận lỗi có `NullPointerException` làm cause.
- Lazy collection không phải cache có retry, expiration, eviction hoặc refresh.

Các giới hạn khác:

- Collection là unmodifiable, nhưng object chứa bên trong có thể mutable.
- List và map không cho phần tử/value `null`; set không nhận candidate `null`.
- Lazy collection giữ computing function ít nhất khi vẫn còn phần tử chưa được tính; cân nhắc reference mà lambda capture giữ lại.
- Các lazy collections trong API preview này không hỗ trợ serialization.
- Những thao tác như `toString`, `hashCode`, `equals` và duyệt collection có thể kích hoạt việc tính phần tử hoặc value chưa cần ở luồng xử lý chính.
- Với `Set.ofLazy`, tập candidate đầu vào phải có equality semantics nhất quán với `equals`.

Stream cũng có giới hạn riêng: pipeline dùng một lần, không lưu phần tử, và một số stage stateful như `sorted` hoặc `distinct` có thể cần buffer hoặc xử lý phần lớn nguồn trước khi tạo kết quả. Vì vậy, Stream không tự động ít tốn bộ nhớ trong mọi pipeline.

## 11. Trạng thái preview và cấu hình JDK

Các factory lazy collections trong bài là preview API:

| API | JDK đầu tiên | JEP | Trạng thái trong Java 27 |
|---|---:|---|---|
| `List.ofLazy(int, IntFunction)` | 26 | JEP 526 — Lazy Constants, preview lần 2 | Preview |
| `Map.ofLazy(Set, Function)` | 26 | JEP 526 — Lazy Constants, preview lần 2 | Preview |
| `Set.ofLazy(Set, Predicate)` | 27 | JEP 531 — Lazy Constants, preview lần 3 | Preview |

Stream API là API chính thức; không cần `--enable-preview` để dùng `stream()`, `filter`, `map`, `findFirst` hoặc `toList`. Chỉ các factory lazy collections nói trên cần bật preview.

Với JDK 26, ví dụ dùng `List.ofLazy` và `Map.ofLazy` cần compiler và runtime Java 26:

```bash
javac --release 26 --enable-preview -Xlint:preview LazyCollectionDemo.java
java --enable-preview LazyCollectionDemo
```

Với JDK 27, ví dụ có thêm `Set.ofLazy` cần compiler và runtime Java 27:

```bash
javac --release 27 --enable-preview -Xlint:preview LazyCollectionDemo.java
java --enable-preview LazyCollectionDemo
```

Không thể dùng JDK 27 để bật preview của JDK 26 bằng cách chỉ đặt `--release 26`; `--enable-preview` chỉ bật preview của phiên bản JDK đang chạy compiler. Preview có thể thay đổi hoặc bị loại bỏ ở release sau. Không phụ thuộc các factory này trong API production cần tương thích Java SE ổn định cho đến khi chúng trở thành final.

Quy tắc error state mô tả ở phần trước là hành vi của preview Java 27. Trong preview Java 26, nếu computing function ném exception, exception được truyền tới caller và giá trị chưa được ghi; lần truy cập sau có thể thử tính lại. Khi so sánh hành vi giữa hai JDK, hãy đối chiếu đúng tài liệu API của release đang chạy.

## 12. Bài tập thực hành

Một dịch vụ có 5 bộ quy tắc kiểm tra đơn hàng. Việc tạo mỗi bộ quy tắc tốn chi phí, nhưng trong một request chỉ cần dùng một số bộ. Sau đó dịch vụ lọc các quy tắc đã bật và lấy tên chuẩn hóa của chúng.

**Yêu cầu:**

1. Tạo `List<Rule>` bằng `List.ofLazy(5, ...)`, mỗi index tạo một rule.
2. Gọi `get(3)` hai lần và giải thích vì sao factory chỉ chạy một lần cho index 3.
3. Tạo Stream từ list, lọc rule được bật, map sang tên và thu thập bằng `toList()`.
4. Gọi phương thức tạo kết quả hai lần; phân biệt số lần tạo Rule với số lần pipeline filter/map được thực hiện.
5. Dùng `findFirst()` để tìm rule đầu tiên phù hợp và xác định những index nào có thể vẫn chưa được khởi tạo.
6. Tạo `Map.ofLazy` cho tập key loại quy tắc và `Set.ofLazy` cho tập candidate feature; so sánh cách tính value với cách tính membership.
7. Thử một computing function ném unchecked exception và giải thích vì sao lần truy cập sau không tự retry.
8. Biên dịch bằng JDK 27 với `--enable-preview`; xác định phần Stream nào không cần cờ preview.

**Kết quả mong đợi:**

- Mỗi index của lazy list chỉ tạo Rule một lần sau khi được truy cập thành công.
- Mỗi lần gọi phương thức tạo kết quả dùng một Stream pipeline mới; các phép lọc/map được thực hiện lại khi terminal operation cần chúng.
- `findFirst()` có thể dừng trước khi chạm tới các index phía sau.
- Lazy map cache value theo key; lazy set cache trạng thái membership theo candidate.
- Người học chỉ ra được lazy collection lưu kết quả phần tử, còn Stream trì hoãn phép duyệt và biến đổi.
- Người học phân biệt được API preview của Lazy Constants với Stream API chính thức.

## Tài liệu tham khảo

- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): bổ sung `List.ofLazy` và `Map.ofLazy` trong Java 26.
- [JEP 531: Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): tiếp tục preview trong Java 27 và bổ sung `Set.ofLazy`.
- [List — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): hợp đồng `List.ofLazy`, cache theo index, xử lý lỗi và các view lazy.
- [Map — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): hợp đồng `Map.ofLazy`, key cố định và value được tính khi truy cập.
- [Set — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): hợp đồng `Set.ofLazy` và cache trạng thái membership.
- [Package java.util.stream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html): source, intermediate/terminal operations, laziness, short-circuit và khả năng tiêu thụ Stream một lần.
- [Stream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): hợp đồng các phép xử lý trên pipeline Stream.
