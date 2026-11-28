# Tạo bằng LazyConstant.of và truy cập bằng get

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao cần khởi tạo trễ một giá trị chỉ dùng trong một số luồng xử lý.
- Tạo `LazyConstant<T>` bằng `LazyConstant.of(Supplier)` và lấy nội dung bằng `get()`.
- Phân biệt thời điểm tạo holder với thời điểm tính toán nội dung.
- Hiểu bảo đảm khởi tạo một lần, an toàn luồng và công bố dữ liệu của LazyConstant.
- Sử dụng `isInitialized()` và `orElse()` mà không vô tình kích hoạt khởi tạo.
- Nhận diện giới hạn preview của JDK 26 và chọn phương án ổn định cho production khi cần.

## 1. Vấn đề: vừa muốn khởi tạo trễ, vừa muốn giá trị bất biến

Một ứng dụng thường có những đối tượng chỉ cần trong một số trường hợp: bộ phân tích biểu thức chính quy, metadata lớn, cấu hình được tính từ nhiều nguồn, bộ định tuyến hoặc thành phần hỗ trợ một tính năng tùy chọn.

Nếu tạo tất cả đối tượng ngay khi khởi tạo ứng dụng, startup phải trả chi phí cho cả những thành phần có thể không bao giờ được dùng. Nhưng nếu dùng một field có thể thay đổi từ `null` sang đối tượng thật, mã nguồn phải kiểm tra trạng thái mỗi lần truy cập và tự đảm bảo nhiều luồng không cùng tạo nhiều bản sao.

Ví dụ khởi tạo trễ thủ công:

~~~java
private Logger logger;

synchronized Logger logger() {
    if (logger == null) {
        logger = Logger.getLogger(MyService.class.getName());
    }
    return logger;
}
~~~

Cách này có thể hoạt động, nhưng field không còn là `final`; mọi nơi truy cập phải đi qua getter; việc đồng bộ có thể tạo tranh chấp; nếu bỏ `synchronized` mà không có cơ chế đồng bộ khác, nhiều luồng có thể cùng khởi tạo. Với những giá trị sau khi tạo không cần thay đổi, ta muốn giữ lợi ích của một giá trị bất biến mà vẫn trì hoãn được chi phí khởi tạo.

JDK 26 giới thiệu API `java.lang.LazyConstant<T>` trong JEP 526. Nó là một holder có nội dung được tính ở lần truy cập đầu tiên và không thể thay thế sau khi đã khởi tạo. JVM có thể xem nội dung đã khởi tạo như một hằng để áp dụng một số tối ưu hóa tương tự field `final`.

## 2. Tạo LazyConstant bằng LazyConstant.of

`LazyConstant.of` nhận một `Supplier<? extends T>` mô tả cách tạo giá trị:

~~~java
private static final LazyConstant<Pattern> EMAIL_PATTERN =
    LazyConstant.of(() -> Pattern.compile("[^@]+@[^@]+\\.[^@]+"));
~~~

Khi dòng khai báo trên được thực thi, JVM tạo holder và lưu computing function. Biểu thức `Pattern.compile(...)` chưa được gọi tại thời điểm đó. Giá trị chỉ được tạo khi ứng dụng yêu cầu nó bằng `get()`.

Một ví dụ hoàn chỉnh:

~~~java
import java.lang.LazyConstant;
import java.util.regex.Pattern;

public final class EmailValidator {
    private static final LazyConstant<Pattern> EMAIL_PATTERN =
        LazyConstant.of(() -> Pattern.compile("[^@]+@[^@]+\\.[^@]+"));

    private EmailValidator() {}

    public static boolean isValid(String value) {
        return value != null
            && EMAIL_PATTERN.get().matcher(value).matches();
    }

    public static void main(String[] args) {
        System.out.println(EMAIL_PATTERN.isInitialized()); // false

        System.out.println(isValid("dev@example.com"));

        System.out.println(EMAIL_PATTERN.isInitialized()); // true
    }
}
~~~

Lần gọi `isValid` đầu tiên cần dùng biểu thức chính quy, nên `EMAIL_PATTERN.get()` kích hoạt việc biên dịch pattern. Những lần gọi sau lấy lại cùng đối tượng `Pattern`. Nếu ứng dụng không bao giờ gọi `isValid`, chi phí tạo pattern sẽ không phát sinh.

Ở ví dụ này, `EMAIL_PATTERN` là field `static final`. Cấu trúc đó cũng phù hợp với điều kiện để JVM có thể áp dụng constant folding cho LazyConstant sau khi nó được khởi tạo.

## 3. get() khởi tạo ở lần truy cập đầu tiên

`get()` vừa yêu cầu nội dung, vừa bảo đảm holder đã được khởi tạo thành công trước khi trả về:

~~~java
LazyConstant<String> greeting =
    LazyConstant.of(() -> {
        System.out.println("Đang tạo giá trị");
        return "Xin chào";
    });

System.out.println("Holder đã tạo");
System.out.println(greeting.get());
System.out.println(greeting.get());
~~~

Kết quả:

~~~text
Holder đã tạo
Đang tạo giá trị
Xin chào
Xin chào
~~~

Thông điệp “Đang tạo giá trị” chỉ xuất hiện một lần. Lần `get()` đầu tiên chạy computing function và lưu kết quả. Các lần tiếp theo trả về cùng nội dung đã lưu mà không gọi lại function.

Cần phân biệt:

| Thao tác | Có tạo holder? | Có tính nội dung? |
|---|---:|---:|
| Gọi `LazyConstant.of(supplier)` | Có | Không |
| Gọi `get()` khi chưa khởi tạo | Holder đã tồn tại | Có |
| Gọi `get()` sau khi khởi tạo | Holder đã tồn tại | Không, lấy nội dung cũ |
| Gọi `isInitialized()` | Không tạo thêm | Không |
| Gọi `orElse(other)` | Không tạo thêm | Không |

Không nên gọi `get()` trong static initializer hoặc constructor nếu mục tiêu là trì hoãn chi phí đến lúc thật sự cần. Nếu gọi ngay khi khởi tạo lớp hoặc đối tượng, phần tính toán cũng diễn ra ngay tại thời điểm đó.

## 4. Kiểm tra trạng thái bằng isInitialized và orElse

`isInitialized()` cho biết nội dung đã được tạo thành công hay chưa. Phương thức này không kích hoạt việc khởi tạo:

~~~java
if (!EMAIL_PATTERN.isInitialized()) {
    System.out.println("Pattern chưa được tạo");
}
~~~

`orElse(other)` trả về nội dung nếu nó đã sẵn sàng; nếu chưa, trả về giá trị thay thế. Phương thức này cũng không gọi computing function:

~~~java
Pattern current = EMAIL_PATTERN.orElse(null);

if (current == null) {
    System.out.println("Chưa có pattern; không khởi tạo chỉ để kiểm tra");
}
~~~

Tham số `other` có thể là `null`, nhưng bản thân LazyConstant không thể giữ nội dung `null`. Nếu computing function trả về `null`, `get()` ném `NullPointerException` và holder vẫn chưa được khởi tạo. Nếu nghiệp vụ cần biểu diễn “không có giá trị”, hãy bọc kết quả trong `Optional`:

~~~java
private static final LazyConstant<Optional<FeatureConfig>> CONFIG =
    LazyConstant.of(() -> loadConfig());
~~~

Trong đó `loadConfig()` luôn trả về một `Optional` khác null, có thể là `Optional.empty()`.

Không dùng mẫu `if (!isInitialized()) get()` để cố đảm bảo một lần khởi tạo. Giữa hai lời gọi, luồng khác có thể đã khởi tạo holder. Nếu cần nội dung, chỉ cần gọi `get()`; API tự xử lý tranh chấp giữa các luồng.

## 5. Khởi tạo an toàn khi nhiều luồng cùng gọi get

`LazyConstant` bảo đảm khởi tạo nguyên tử và tối đa một lần thành công. Nếu nhiều luồng đồng thời gọi `get()` trên cùng holder khi nó chưa được khởi tạo:

1. Một luồng được chọn để chạy computing function. Function chạy trên chính luồng gọi `get()` đó.
2. Những luồng còn lại chờ cho đến khi quá trình khởi tạo hoàn tất.
3. Sau khi có kết quả, các luồng nhận cùng nội dung đã khởi tạo.
4. Computing function không được gọi đồng thời nhiều lần cho cùng một lần khởi tạo thành công.

Ví dụ:

~~~java
private static final AtomicInteger CREATED = new AtomicInteger();

private static final LazyConstant<ServiceConfig> CONFIG =
    LazyConstant.of(() -> {
        CREATED.incrementAndGet();
        return ServiceConfig.load();
    });
~~~

Dù nhiều request cùng gọi `CONFIG.get()`, bộ đếm chỉ tăng một lần nếu việc khởi tạo thành công. `ServiceConfig` là kiểu minh họa do ứng dụng định nghĩa.

Việc gọi computing function và khởi tạo nội dung có quan hệ happens-before với những lần đọc nội dung sau đó. Các field `final` bên trong đối tượng mới tạo được công bố an toàn cho các luồng khác. Do đó, không cần tự thêm `volatile` hoặc `synchronized` chỉ để bảo vệ cùng một LazyConstant.

Tuy nhiên, bảo đảm an toàn luồng chỉ áp dụng cho việc khởi tạo và công bố tham chiếu. Nếu đối tượng được giữ bên trong có trạng thái mutable, LazyConstant không tự làm cho các thao tác thay đổi trạng thái của đối tượng đó trở nên thread-safe.

## 6. Kết hợp các LazyConstant có phụ thuộc

Một giá trị có thể được tạo từ một hoặc nhiều lazy constant khác. Điều này tạo thành đồ thị phụ thuộc và chỉ khởi tạo những thành phần cần cho luồng đang được gọi.

~~~java
final class ApplicationComponents {
    private static final LazyConstant<DatabaseSettings> SETTINGS =
        LazyConstant.of(DatabaseSettings::load);

    private static final LazyConstant<DataSource> DATA_SOURCE =
        LazyConstant.of(() -> createDataSource(SETTINGS.get()));

    static DataSource dataSource() {
        return DATA_SOURCE.get();
    }

    private static DataSource createDataSource(DatabaseSettings settings) {
        return DataSourceFactory.create(settings);
    }
}
~~~

Các kiểu `DatabaseSettings`, `DataSource` và `DataSourceFactory` là thành phần minh họa. Khi gọi `dataSource()`, LazyConstant `DATA_SOURCE` bắt đầu khởi tạo; trong quá trình đó, `SETTINGS.get()` được gọi trước để tạo cấu hình nếu cần. Nếu `SETTINGS` đã có nội dung, nó được dùng lại.

Tránh phụ thuộc vòng. Nếu computing function của A gọi B, rồi quá trình tạo B lại gọi A.get(), LazyConstant phát hiện việc gọi đệ quy và ném `IllegalStateException`. Holder không được khởi tạo thành công. Hãy thiết kế dependency graph theo một chiều hoặc tách phần cấu hình dùng chung thành thành phần độc lập.

## 7. Lỗi trong computing function và khả năng thử lại

Nếu computing function ném exception hoặc error, `get()` chuyển lỗi đó cho caller và LazyConstant vẫn chưa được khởi tạo. Lần gọi `get()` sau có thể chạy computing function lại:

~~~java
private static final AtomicInteger ATTEMPTS = new AtomicInteger();

private static final LazyConstant<ClientConfig> CLIENT_CONFIG =
    LazyConstant.of(() -> {
        if (ATTEMPTS.incrementAndGet() == 1) {
            throw new IllegalStateException("Nguồn cấu hình tạm thời chưa sẵn sàng");
        }
        return ClientConfig.load();
    });
~~~

Trong ví dụ này, lần gọi đầu tiên thất bại; lần gọi tiếp theo có thể thử lại và thành công. Khi thành công, giá trị được giữ lại cho các lần truy cập sau.

Điều này có ý nghĩa khi computing function có side effect. Không giả định function chỉ chạy đúng một lần trong toàn bộ vòng đời nếu nó có thể thất bại. Hãy thiết kế việc tạo giá trị sao cho an toàn khi thử lại: kiểm tra và đóng tài nguyên tạm, tránh tạo giao dịch trùng lặp, tránh ghi dữ liệu nghiệp vụ không thể đảo ngược hoặc dùng một khóa idempotency phù hợp.

`Supplier.get()` không khai báo checked exception. Nếu thao tác khởi tạo gọi API ném checked exception, hãy chuyển đổi lỗi theo quy ước của ứng dụng, ví dụ bọc `IOException` thành `UncheckedIOException`:

~~~java
private static final LazyConstant<byte[]> TEMPLATE =
    LazyConstant.of(() -> {
        try {
            return Files.readAllBytes(Path.of("template.bin"));
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    });
~~~

Không nên bắt rồi bỏ qua exception và trả về giá trị giả chỉ để holder được khởi tạo. Khi dữ liệu không hợp lệ hoặc không thể tải, hãy để lỗi được xử lý rõ ràng.

## 8. LazyConstant giúp JVM tối ưu như thế nào?

Sau khi khởi tạo, nội dung LazyConstant không thể bị thay thế. Vì vậy, JVM có thể áp dụng constant folding: loại bỏ một số lần đọc holder và dùng giá trị đã quan sát trong mã máy đã tối ưu.

Điều kiện quan trọng trong JDK 26 là phải có đường tham chiếu từ một field `static final` tới LazyConstant, trực tiếp hoặc qua các trusted field được đặc tả cho phép (ví dụ field record hoặc final instance field trong hidden class). Vì vậy, nếu muốn JVM có cơ hội tối ưu theo cách này, hãy đặt holder ở một field `static final` rõ ràng:

~~~java
private static final LazyConstant<Pattern> ROUTE_PATTERN =
    LazyConstant.of(() -> Pattern.compile("/orders/[0-9]+"));
~~~

Đây là khả năng tối ưu của JVM, không phải cam kết rằng mọi lần gọi `get()` sẽ luôn được thay bằng hằng số ở mọi JVM hoặc mọi đường chạy. Mức tối ưu phụ thuộc implementation, trạng thái khởi tạo và mã được JIT biên dịch.

LazyConstant cũng không tự làm cho object được giữ bên trong trở thành immutable sâu. Ví dụ, nếu holder chứa `ArrayList`, tham chiếu tới list không đổi nhưng các phần tử của list vẫn có thể thay đổi. Hãy ưu tiên giá trị thực sự bất biến hoặc không để lộ khả năng sửa đổi nếu muốn tận dụng mô hình hằng.

Lazy initialization có thể giảm thời gian startup nếu thành phần không được dùng trong lần chạy đó. Nếu thành phần được dùng ngay ở request đầu tiên, chi phí khởi tạo sẽ chuyển sang đường xử lý request đó. Hãy đo cả startup, độ trễ lần truy cập đầu và hiệu năng sau khi đã khởi tạo; không mặc định dùng LazyConstant là ứng dụng sẽ nhanh hơn trong mọi tình huống.

## 9. Những giới hạn cần tính đến

- **Không thể đặt lại hoặc xóa nội dung:** một khi đã khởi tạo, LazyConstant giữ giá trị cho đến khi holder không còn reachable.
- **Giữ tham chiếu mạnh:** holder giữ nội dung; một field static sống lâu có thể khiến object lớn tiếp tục chiếm bộ nhớ trong toàn bộ vòng đời class loader.
- **Không hỗ trợ null:** supplier trả null làm `get()` ném `NullPointerException`; dùng `Optional` nếu cần biểu diễn thiếu dữ liệu.
- **Không có timeout hoặc cancellation:** nếu computing function bị chặn vô hạn, các luồng khác gọi `get()` cũng có thể chờ vô hạn. Ngắt luồng không hủy quá trình khởi tạo.
- **Có thể thất bại và thử lại:** nếu supplier ném lỗi, holder chưa được khởi tạo; lần gọi sau có thể chạy lại supplier.
- **Không tự bảo vệ trạng thái mutable:** holder không đổi nội dung tham chiếu, nhưng object được giữ có thể vẫn mutable.
- **Không Serializable:** không dùng LazyConstant như một phần dữ liệu cần serialize trực tiếp.
- **Cẩn thận với khóa và khởi tạo lớp:** implementation được phép đồng bộ trên chính LazyConstant; tránh đồng bộ trực tiếp hoặc gián tiếp trên holder. Chu trình phụ thuộc trong static initializer có thể gây lỗi khởi tạo lớp.
- **Không dùng cho giá trị cần refresh:** cấu hình động, dữ liệu có thời hạn, cache cần invalidation hoặc kết quả thay đổi theo user/request không phù hợp với hằng chỉ khởi tạo một lần.

## 10. Bật preview và chạy trên JDK 26

`LazyConstant` là **preview API** trong JDK 26 theo JEP 526 (Second Preview). Nó nằm trong `java.lang` thuộc module `java.base`, nhưng vẫn cần bật preview ở cả bước biên dịch và chạy. Không cần thêm module incubator.

Với file `EmailValidator.java`, dùng đúng JDK 26:

~~~bash
javac --release 26 --enable-preview -d out EmailValidator.java
java --enable-preview -cp out EmailValidator
~~~

Nếu chạy bằng IDE hoặc build tool, cấu hình cả compiler và JVM test/run với `--enable-preview`, đồng thời đặt source/release là 26. Chỉ bật preview ở compiler mà quên runtime sẽ khiến chương trình không tải được class phụ thuộc preview. Class file dùng preview của Java SE 26 cũng gắn với release đó, không thể mặc định chuyển sang JDK khác.

Preview feature có thể thay đổi hoặc bị loại bỏ trong một release sau. Vì vậy, không nên đưa `LazyConstant` vào public API, thư viện dùng chung nhiều phiên bản JDK hoặc hệ thống production yêu cầu tương thích dài hạn nếu chưa chấp nhận rủi ro phụ thuộc preview.

## 11. Phương án ổn định khi không thể dùng preview

Nếu chỉ cần lazy singleton static, Java đã có initialization-on-demand holder idiom:

~~~java
final class SharedConfig {
    private SharedConfig() {}

    private static class Holder {
        static final Config INSTANCE = Config.load();
    }

    static Config get() {
        return Holder.INSTANCE;
    }
}
~~~

Class lồng `Holder` chỉ được khởi tạo khi `get()` lần đầu tham chiếu tới `Holder.INSTANCE`. Cơ chế khởi tạo class của Java bảo đảm an toàn luồng. Đây là cách ổn định cho một static singleton khi chấp nhận ngữ nghĩa khởi tạo lớp.

Với một field lazy theo từng instance, có thể dùng getter đồng bộ hoặc mẫu `volatile` kết hợp double-checked locking được triển khai đúng. Chọn phương án theo vòng đời đối tượng và yêu cầu đồng thời; đừng tự viết một cache dùng `null` sentinel nếu chưa xử lý an toàn luồng và lỗi khởi tạo.

`Supplier<T>` đơn thuần cũng không tương đương LazyConstant: mỗi lần gọi `supplier.get()` có thể thực hiện lại phép tính. Nếu muốn memoize một supplier, cần một abstraction memoization ổn định được kiểm thử và có ngữ nghĩa rõ ràng về concurrency, lỗi và null.

## 12. Khi nào nên dùng LazyConstant?

| Tình huống | Mức độ phù hợp | Lý do |
|---|---|---|
| Pattern, parser hoặc metadata đắt đỏ và chỉ dùng ở một số luồng | Phù hợp | Trì hoãn chi phí đến lần dùng đầu và tái sử dụng kết quả. |
| Cấu hình bất biến được tính một lần | Phù hợp nếu vòng đời dài hạn phù hợp | Nội dung ổn định sau khi tạo. |
| Component có dependency rõ ràng, không có chu trình | Phù hợp | Có thể tạo dependency graph theo nhu cầu. |
| Cấu hình cần reload hoặc cache cần expire | Không phù hợp | Nội dung không thể thay thế hoặc xóa sau khi init. |
| Kết nối/socket/file handle cần đóng | Thường không phù hợp | LazyConstant không quản lý vòng đời đóng tài nguyên. |
| Khởi tạo có thể chờ mạng rất lâu | Cần cân nhắc | Luồng đầu tiên thực hiện việc tạo; các luồng khác có thể phải chờ. |
| API công khai cần chạy trên nhiều JDK | Không nên phụ thuộc preview | Preview không bảo đảm tương thích giữa release. |

Trước khi chọn LazyConstant, hãy xác định giá trị có thật sự bất biến, có được dùng đủ thường xuyên để đáng giữ trong bộ nhớ, có thể được khởi tạo an toàn một lần và có chấp nhận được độ trễ ở lần truy cập đầu hay không.

## Kết luận

`LazyConstant.of(Supplier)` tạo một holder chưa có nội dung; `get()` tính giá trị ở lần truy cập đầu tiên và trả lại cùng giá trị ở các lần sau. JDK 26 bảo đảm việc khởi tạo tối đa một lần thành công và công bố nội dung an toàn giữa các luồng. `isInitialized()` và `orElse()` cho phép quan sát trạng thái mà không kích hoạt việc tạo giá trị. Tuy nhiên, LazyConstant trong JDK 26 vẫn là preview theo JEP 526; hãy dùng để thử nghiệm trên đúng JDK 26 và cân nhắc các mẫu khởi tạo trễ ổn định khi cần tương thích production lâu dài.

## Tài liệu tham khảo

- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526)
- [Java 26 API – LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [Java 26 Core Libraries Guide – Lazy Constants](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html)
- [Java 26 Preview API List](https://docs.oracle.com/en/java/javase/26/docs/api/preview-list.html)
- [Java 26 javac Command – --enable-preview](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Java 26 JVM Specification – Preview Features](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html)
