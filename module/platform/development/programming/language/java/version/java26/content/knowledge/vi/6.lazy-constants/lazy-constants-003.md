# Bài toán khởi tạo sớm, khởi tạo lười và tham chiếu không đổi

Khởi tạo một đối tượng ngay khi tạo instance hoặc khi lớp được nạp là cách đơn giản và an toàn, nhưng đôi khi ứng dụng phải trả chi phí cho những thành phần có thể không bao giờ được sử dụng. Chuyển sang khởi tạo lười giúp trì hoãn chi phí đó, nhưng nếu dùng một field có thể thay đổi thì phải tự xử lý đồng bộ, công bố đối tượng an toàn và nguy cơ nhiều thread cùng khởi tạo.

Java 26 giới thiệu `LazyConstant<T>` dưới dạng preview trong JEP 526. Cơ chế này kết hợp hai đặc tính: nội dung chỉ được tạo khi có lần truy cập đầu tiên, sau đó được thiết lập tối đa một lần và không thể thay đổi. Nhờ vậy, JVM có thể xem nội dung đã khởi tạo như một hằng số trong những trường hợp phù hợp, mở ra các tối ưu hóa tương tự field `final`.

## 1. Khởi tạo sớm và chi phí phải trả

Field `final` phải được gán đúng một lần trong constructor, initializer hoặc static initializer. Ví dụ:

```java
public final class ReportService {
    private final ExpensiveCatalog catalog = ExpensiveCatalog.load();

    public Report createReport() {
        return Report.from(catalog);
    }
}
```

Mỗi `ReportService` đều tải catalog ngay cả khi instance đó không bao giờ gọi `createReport()`. Nếu catalog tốn thời gian đọc file, phân tích cấu hình hoặc dựng cấu trúc dữ liệu lớn, chi phí này làm tăng thời gian tạo đối tượng và có thể làm chậm startup.

Với static field, `static final` cũng được khởi tạo trong quá trình khởi tạo lớp:

```java
public final class ApplicationServices {
    private static final SearchIndex INDEX = SearchIndex.load();

    public static SearchIndex index() {
        return INDEX;
    }
}
```

Lần đầu lớp được khởi tạo, `INDEX` được tạo dù ứng dụng có thể không bao giờ dùng chức năng tìm kiếm. Bù lại, class initialization của Java có quy tắc đồng bộ và công bố an toàn: thread khác không quan sát lớp ở trạng thái khởi tạo dở dang.

Khởi tạo sớm phù hợp khi đối tượng chắc chắn được dùng, chi phí khởi tạo nhỏ, hoặc muốn phát hiện lỗi cấu hình ngay lúc startup. Không phải mọi field đều cần trì hoãn.

## 2. Khởi tạo lười bằng field có thể thay đổi

Một cách trực tiếp là để field ban đầu bằng `null`, rồi khởi tạo khi getter được gọi:

```java
public final class ReportService {
    private ExpensiveCatalog catalog;

    public synchronized ExpensiveCatalog catalog() {
        if (catalog == null) {
            catalog = ExpensiveCatalog.load();
        }
        return catalog;
    }
}
```

Cách này trì hoãn việc tải catalog đến lần đầu cần dùng. Tuy nhiên, field không còn `final`, nên compiler và JVM không thể dựa vào tính bất biến của field để áp dụng các tối ưu hóa dành cho hằng số. Mọi truy cập cần đi qua getter được đồng bộ; nếu đọc trực tiếp field ở nơi khác, code có thể thấy `null` hoặc không có bảo đảm visibility phù hợp.

Nếu bỏ `synchronized` mà không có cơ chế công bố an toàn khác, nhiều thread có thể đồng thời gọi `load()` hoặc thread khác có thể quan sát trạng thái không đúng. Các biến thể dùng `volatile`, khóa và double-checked locking có thể triển khai được, nhưng làm tăng độ phức tạp và vẫn phải quản lý một field có thể thay đổi.

Vấn đề cần giải quyết là giữ được lợi ích của khởi tạo lười mà vẫn có một giá trị chỉ được thiết lập một lần và an toàn khi chia sẻ giữa các thread.

## 3. Lazy Constants trong JDK 26

`java.lang.LazyConstant<T>` là một holder giữ một nội dung được tính bằng `Supplier`. Tạo holder không gọi supplier. Lần đầu gọi `get()`, supplier được chạy và kết quả trở thành nội dung của lazy constant. Sau khi khởi tạo thành công, mọi lần gọi `get()` tiếp theo đều nhận lại cùng nội dung.

```java
import java.lang.LazyConstant;
import java.util.logging.Logger;

public final class OrderService {
    private static final LazyConstant<Logger> LOGGER =
            LazyConstant.of(() -> Logger.getLogger(OrderService.class.getName()));

    public void submit() {
        LOGGER.get().info("Submitting order");
        // Xử lý đơn hàng...
    }
}
```

Khi `OrderService` được khởi tạo, đối tượng `LazyConstant` được tạo nhưng `Logger` chưa được yêu cầu từ supplier. `Logger` chỉ được lấy khi `submit()` gọi `LOGGER.get()`. Nếu chức năng submit không bao giờ được dùng, supplier không chạy.

Điểm khác biệt quan trọng: field `LOGGER` là `static final`, còn nội dung bên trong `LazyConstant` được khởi tạo muộn. Sau khi có nội dung, nó không thể được thay bằng một logger khác. Đây là **khởi tạo lười kết hợp với tính bất biến sau khởi tạo**.

### 3.1. API chính

| API | Tác dụng | Có kích hoạt khởi tạo không? |
|---|---|---|
| `LazyConstant.of(supplier)` | Tạo holder với hàm tính nội dung | Không |
| `get()` | Lấy nội dung, tính và lưu nếu chưa có | Có |
| `isInitialized()` | Kiểm tra trạng thái đã khởi tạo | Không |
| `orElse(other)` | Lấy nội dung nếu đã có, nếu chưa thì trả `other` | Không |
| `toString()` | Biểu diễn trạng thái để debug | Không |

`isInitialized()` và `orElse()` hữu ích khi cần quan sát trạng thái mà không muốn vô tình kích hoạt công việc tốn kém. `orElse()` trả về giá trị dự phòng nếu nội dung chưa được khởi tạo; nó không chờ một thread khác đang tính nội dung. Đây là phép quan sát trạng thái tại thời điểm gọi, không phải cơ chế khóa hay thay thế `get()`.

### 3.2. Tạo chuỗi phụ thuộc lazy constants

Một lazy constant có thể phụ thuộc vào lazy constant khác. Khi yêu cầu thành phần phía ngoài, những thành phần phụ thuộc sẽ được khởi tạo theo thứ tự truy cập:

```java
import java.lang.LazyConstant;

public final class ApplicationComponents {
    private ApplicationComponents() {}

    static final LazyConstant<DatabaseConfig> DATABASE_CONFIG =
            LazyConstant.of(DatabaseConfig::load);

    static final LazyConstant<Repository> REPOSITORY =
            LazyConstant.of(() -> new Repository(DATABASE_CONFIG.get()));

    static Repository repository() {
        return REPOSITORY.get();
    }

    record DatabaseConfig(String url) {
        static DatabaseConfig load() {
            return new DatabaseConfig("jdbc:example:catalog");
        }
    }

    record Repository(DatabaseConfig config) {}
}
```

Gọi `repository()` sẽ tạo `Repository`; trong quá trình đó, `DATABASE_CONFIG.get()` tạo cấu hình nếu chưa có. Những lần truy cập sau dùng lại cùng hai nội dung đã khởi tạo. Cách tổ chức này cho phép mô hình hóa đồ thị phụ thuộc mà không cần khởi tạo mọi thành phần ngay khi lớp tiện ích được nạp.

Không tạo vòng phụ thuộc. Nếu supplier gọi trực tiếp hoặc gián tiếp lại chính lazy constant đang được tính, `get()` ném `IllegalStateException` và holder không được khởi tạo. Chuỗi phụ thuộc giữa các static initializer cũng cần được thiết kế cẩn thận để tránh chu trình khởi tạo lớp theo JLS.

## 4. An toàn khi nhiều thread cùng truy cập

`LazyConstant` bảo đảm nội dung được khởi tạo nguyên tử và tối đa một lần thành công. Nếu nhiều thread cùng gọi `get()` khi holder chưa có nội dung:

1. Một thread được chọn để chạy supplier.
2. Những thread còn lại chờ kết quả khởi tạo.
3. Khi supplier trả về thành công, nội dung được công bố an toàn.
4. Những thread đang chờ và các lần truy cập sau nhận cùng nội dung; supplier không chạy lại.

Việc chạy supplier và khởi tạo nội dung *happens-before* các lần đọc nội dung đã khởi tạo. Vì vậy các field `final` của đối tượng vừa tạo cũng được công bố an toàn cho thread khác.

Supplier chạy trên thread gọi `get()` đầu tiên, không tự chạy trên background thread. Do đó, nếu supplier tải cấu hình từ mạng hoặc mở kết nối chậm, request đầu tiên sẽ chịu thời gian chờ. Các thread khác cùng truy cập holder có thể bị chặn trong thời gian đó. Lazy constant không cung cấp timeout hay cơ chế hủy việc khởi tạo; nếu supplier bị block vô hạn, các thread chờ cũng có thể bị block vô hạn.

Interrupt cũng không hủy quá trình khởi tạo. Nếu thread đang tính hoặc đang chờ bị interrupt, `get()` không xóa trạng thái interrupt và không ném `InterruptedException` chỉ vì interrupt đó.

### 4.1. Lỗi trong supplier

Trên JDK 26, nếu supplier ném exception, throwable được chuyển cho caller và lazy constant vẫn chưa khởi tạo. Một lần gọi `get()` sau có thể chạy supplier lại. Vì `Supplier` không khai báo checked exception, hãy chuyển lỗi checked thành một unchecked exception phù hợp (ví dụ `UncheckedIOException`) tại supplier. Supplier nên xử lý dọn dẹp tài nguyên và an toàn khi thử lại; tránh tạo side effect không thể đảo ngược trước khi có thể thất bại.

Lazy constant không nhận `null` làm nội dung. Nếu supplier trả về `null`, `get()` ném `NullPointerException` và holder vẫn chưa được khởi tạo. Nếu cần biểu diễn giá trị có thể vắng mặt, hãy dùng `LazyConstant<Optional<T>>`:

```java
private static final LazyConstant<Optional<FeatureConfig>> FEATURE_CONFIG =
        LazyConstant.of(() -> Optional.ofNullable(loadFeatureConfig()));
```

Nếu supplier tự gọi lại cùng lazy constant, `get()` ném `IllegalStateException` do khởi tạo đệ quy. Hãy giải quyết vòng phụ thuộc ở thiết kế các thành phần thay vì bắt exception để tiếp tục.

### 4.2. Không đồng nghĩa với immutable object

Lazy constant bảo đảm **tham chiếu nội dung được thiết lập tối đa một lần**; nó không tự làm cho object được giữ bên trong trở thành immutable. Ví dụ, một `LazyConstant<ArrayList<String>>` vẫn có thể chứa một `ArrayList` mà code khác sửa được:

```java
private static final LazyConstant<List<String>> NAMES =
        LazyConstant.of(() -> new ArrayList<>(List.of("An", "Binh")));

static void changeNames() {
    NAMES.get().add("Chi"); // Holder không đổi, nhưng object bên trong đã đổi trạng thái.
}
```

Nếu cần dữ liệu bất biến, hãy dùng kiểu immutable hoặc tạo bản sao không thể sửa trước khi trả về, ví dụ `List.copyOf(...)`, `Map.copyOf(...)` hoặc record có các thành phần bất biến. Nếu nội dung phải thay đổi theo nghiệp vụ, hãy dùng một mô hình state riêng có đồng bộ phù hợp thay vì coi lazy constant là kho trạng thái.

## 5. Lazy lists và lazy maps

JEP 526 còn đưa vào các factory preview để tạo collection không thể sửa, trong đó từng phần tử được tính khi cần:

- `List.ofLazy(size, indexFunction)` tạo danh sách có kích thước cố định; phần tử tại một index được tính khi lần đầu truy cập index đó và được giữ lại cho các lần sau.
- `Map.ofLazy(keys, valueFunction)` tạo map với tập key xác định trước; value của một key được tính khi lần đầu truy cập key đó và được giữ lại.

Ví dụ lazy list cho pool các worker:

```java
import java.util.List;

private static final int POOL_SIZE = 8;

private static final List<Worker> WORKERS =
        List.ofLazy(POOL_SIZE, index -> new Worker(index));

static Worker worker(int index) {
    return WORKERS.get(index);
}
```

Khi tạo list, chưa worker nào được tạo. Lần đầu `get(3)` gọi factory với index `3`; các lần đọc tiếp theo tại index đó dùng lại cùng worker. Các index khác được khởi tạo độc lập khi cần. Danh sách không cho phép thay thế hoặc thêm phần tử, nhưng mỗi `Worker` vẫn có thể mutable nếu lớp `Worker` được thiết kế như vậy.

Ví dụ lazy map cho bộ chuyển đổi theo locale:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Set;

private static final Set<Locale> SUPPORTED_LOCALES =
        Set.of(Locale.US, Locale.UK, Locale.FRANCE);

private static final Map<Locale, Formatter> FORMATTERS =
        Map.ofLazy(SUPPORTED_LOCALES, Formatter::new);

static Formatter formatter(Locale locale) {
    return FORMATTERS.get(locale);
}
```

Map chỉ có các key đã khai báo trong `SUPPORTED_LOCALES`; value của từng key được tạo khi cần. Cách này phù hợp khi có tập key hữu hạn nhưng không phải giá trị nào cũng được sử dụng. Hãy xác định rõ cách xử lý key không được hỗ trợ ở tầng gọi.

`List.ofLazy` và `Map.ofLazy` cũng là preview trên JDK 26. Không nhầm chúng với `List.of(...)` và `Map.of(...)` thông thường, vốn tạo collection không thể sửa nhưng nhận sẵn các giá trị đã được tính.

## 6. JVM có thể tối ưu nội dung như hằng số

Field `final` cho phép JVM suy luận rằng tham chiếu field không bị gán lại sau khi khởi tạo. Lazy constant mở rộng ý tưởng này: nội dung ban đầu chưa tồn tại, nhưng sau khi được khởi tạo thì không thể đổi. Vì thế JVM có thể áp dụng *constant folding* hoặc loại bỏ một số lần đọc nội dung trong mã máy đã biên dịch.

Tối ưu này có điều kiện. Theo API Java 26, JVM có thể tối ưu khi có tham chiếu trực tiếp từ một field `static final` đến lazy constant, hoặc có một chuỗi tham chiếu đáng tin cậy từ `static final` qua các field phù hợp (như field của record hoặc final instance field trong hidden class) đến lazy constant. Không nên giả định mọi field `LazyConstant` ở bất kỳ vị trí nào đều được constant-fold.

Đây là khả năng tối ưu của JVM, không phải cam kết rằng mọi lần gọi `get()` sẽ có chi phí bằng đọc một field `final`. Kết quả còn phụ thuộc vào cách sử dụng, trạng thái đã khởi tạo và quyết định tối ưu của JVM. Hãy đo bằng workload thực tế trước khi kết luận lazy constant cải thiện hiệu năng.

## 7. Khi nào nên dùng từng cách?

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Giá trị luôn cần ngay khi tạo object | `final` và khởi tạo trong constructor | Đơn giản, bất biến từ đầu, không có chi phí kiểm tra lazy |
| Singleton static chỉ cần khi lần đầu gọi | Initialization-on-demand holder idiom | API Java ổn định, class initialization bảo đảm đồng bộ |
| Giá trị cần tạo muộn, sau đó cố định, có nhiều thread truy cập | `LazyConstant<T>` | Khởi tạo tối đa một lần, công bố an toàn, có khả năng tối ưu như constant |
| Tập phần tử lớn nhưng chỉ truy cập một phần | `List.ofLazy` hoặc `Map.ofLazy` | Tính riêng từng phần tử hoặc value khi được yêu cầu |
| Giá trị phải thay đổi hoặc cần hết hạn/evict | Cache hoặc state manager phù hợp | Lazy constant không có thao tác thay thế hoặc xóa nội dung |

Ví dụ holder idiom cho singleton static là một lựa chọn ổn định, không cần preview:

```java
public final class GlobalCatalog {
    private GlobalCatalog() {}

    private static class Holder {
        static final Catalog INSTANCE = Catalog.load();
    }

    public static Catalog instance() {
        return Holder.INSTANCE;
    }
}
```

Class `Holder` chỉ được khởi tạo khi `instance()` lần đầu tham chiếu đến `Holder.INSTANCE`. JVM bảo đảm class initialization được đồng bộ, và `INSTANCE` là `static final`. Đây là cách gọn cho một static singleton; `LazyConstant` hữu ích hơn khi cần biểu diễn rõ một giá trị trì hoãn trong object graph, nhiều giá trị độc lập hoặc lazy list/map.

## 8. Giới hạn và lưu ý vận hành

- **Preview:** `LazyConstant`, `List.ofLazy` và `Map.ofLazy` là preview trong JDK 26 theo JEP 526. API có thể đổi hoặc bị loại bỏ ở bản JDK sau.
- **Không phải asynchronous:** supplier chạy đồng bộ trên thread gọi `get()` đầu tiên. Tách công việc nền nếu kiến trúc yêu cầu, nhưng phải quản lý kết quả và lỗi riêng.
- **Không có timeout hoặc cancel:** supplier bị treo có thể khiến những thread khác chờ vô hạn.
- **Không lưu `null`:** dùng `Optional` nếu cần thể hiện giá trị vắng mặt.
- **Thử lại khi lỗi:** trên JDK 26, supplier ném exception thì holder chưa khởi tạo; lần `get()` tiếp theo có thể chạy lại supplier.
- **Giữ tham chiếu mạnh:** sau khi khởi tạo, lazy constant giữ nội dung cho đến khi holder không còn reachable. Không dùng nó thay cho cache có eviction hoặc cho tài nguyên cần giải phóng sớm.
- **Không đảm bảo immutable sâu:** nội dung mutable vẫn có thể bị thay đổi từ nơi khác.
- **Tránh vòng phụ thuộc:** truy cập đệ quy cùng holder gây `IllegalStateException`; chu trình khởi tạo lớp còn có thể gây lỗi theo quy tắc class initialization.
- **Cẩn thận với khóa:** implementation được phép đồng bộ trên chính lazy constant; tránh tự khóa trực tiếp hoặc gián tiếp trên object holder.

## 9. Bật preview trên JDK 26

JEP 526 là **Lazy Constants (Second Preview)** trong JDK 26. Tên và thiết kế API đã thay đổi so với preview đầu tiên của JDK 25 mang tên *Stable Values*. Khi viết code cho JDK 26, dùng API `LazyConstant`, `List.ofLazy` và `Map.ofLazy` trong tài liệu Java SE 26; không sao chép ví dụ theo API preview cũ của JDK 25.

Biên dịch và chạy bằng đúng JDK 26, bật preview ở cả hai bước:

```bash
javac --release 26 --enable-preview LazyConfigDemo.java
java --enable-preview LazyConfigDemo
```

Nếu chạy qua test task hoặc build tool, thêm `--enable-preview` cho compiler và JVM chạy test/app. Chỉ bật cờ ở compile là chưa đủ. Bytecode dùng preview của JDK 26 không phải cam kết tương thích với JDK 25 hoặc JDK 27; khi nâng JDK, hãy kiểm tra JEP và API Specification của phiên bản đích rồi biên dịch lại.

Nếu không thể chấp nhận preview trong môi trường production, tiếp tục dùng `final` với khởi tạo sớm, initialization-on-demand holder cho static singleton, hoặc một triển khai lazy có đồng bộ được kiểm tra kỹ. Chỉ chọn `LazyConstant` khi dự án chấp nhận ràng buộc preview của đúng JDK.

## Tài liệu tham khảo

- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526)
- [Java SE 26 API: LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [Java SE 26 API: List](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [Java SE 26 API: Map](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html)
- [Java SE 26 Core Libraries Guide: Lazy Constants](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html)
- [JEP 502: Stable Values (First Preview in JDK 25)](https://openjdk.org/jeps/502)
