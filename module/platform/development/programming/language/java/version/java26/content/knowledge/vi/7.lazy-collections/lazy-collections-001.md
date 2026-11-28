# List.ofLazy và Map.ofLazy trong nhóm API lazy constant preview

Một số ứng dụng biết trước cấu trúc của một tập hợp nhưng không cần tạo ngay tất cả phần tử. Ví dụ, một màn hình có 200 ô dữ liệu nhưng người dùng chỉ mở vài ô; một ứng dụng hỗ trợ 12 locale nhưng mỗi lần chạy chỉ dùng một hoặc hai locale; hoặc một bảng tra cứu có tập khóa cố định nhưng giá trị được dựng từ cấu hình tốn thời gian.

Java 26 bổ sung `List.ofLazy()` và `Map.ofLazy()` để biểu diễn các tập hợp như vậy. Hai factory tạo collection không thể sửa, giữ trước cấu trúc hoặc tập khóa, rồi tính từng phần tử hoặc giá trị ở lần truy cập đầu tiên. Chúng thuộc nhóm API preview của JEP 526, cùng hướng thiết kế với `LazyConstant<T>`.

## 1. Hai factory giải quyết bài toán gì?

Collection thông thường thường tính các giá trị trước khi đưa chúng vào collection:

```java
List<Report> reports = new ArrayList<>();
for (int i = 0; i < 100; i++) {
    reports.add(loadReport(i));
}
```

Đoạn code trên gọi `loadReport()` đủ 100 lần ngay khi tạo danh sách, kể cả khi phần lớn report không được dùng. Nếu việc tạo mỗi report tốn I/O, bộ nhớ hoặc CPU, chi phí khởi tạo sẽ tăng theo toàn bộ số phần tử.

Với `List.ofLazy()`, ứng dụng khai báo kích thước và hàm tạo phần tử. Một phần tử chỉ được tính khi có thao tác cần giá trị tại index đó. Với `Map.ofLazy()`, ứng dụng khai báo tập khóa hợp lệ và hàm tạo value; value chỉ được tính khi được truy cập lần đầu theo key.

| API | Khai báo trước | Tính lười theo | Kiểu hàm tính |
|---|---|---|---|
| `List.ofLazy(size, computingFunction)` | Kích thước và vị trí index | Index | `IntFunction<? extends E>` |
| `Map.ofLazy(keys, computingFunction)` | Tập khóa | Key | `Function<? super K, ? extends V>` |

Hai collection đều không thể thêm, xóa hoặc thay thế phần tử/mapping. Chúng không phải cache có thể thay đổi tùy ý; mỗi vị trí hoặc key có một kết quả được tính và giữ lại sau khi khởi tạo thành công.

## 2. List.ofLazy: tính phần tử theo index

Chữ ký API trên JDK 26:

```java
static <E> List<E> ofLazy(
        int size,
        IntFunction<? extends E> computingFunction)
```

`size` là kích thước cố định của danh sách. `computingFunction` nhận index bắt đầu từ `0` và trả về phần tử tại index đó. Việc tạo danh sách không gọi hàm tính phần tử.

`computingFunction` phải khác `null`; nếu `size` âm, factory ném `IllegalArgumentException`. List rỗng với `size == 0` là hợp lệ và hàm tính không được gọi.

### 2.1. Ví dụ: tạo báo cáo khi người dùng mở

```java
import java.util.List;

record Report(int id, String content) {}

final class ReportStore {
    private static final int REPORT_COUNT = 100;

    private static final List<Report> REPORTS =
            List.ofLazy(REPORT_COUNT, index -> loadReport(index));

    static Report reportAt(int index) {
        return REPORTS.get(index);
    }

    private static Report loadReport(int index) {
        // Thay bằng truy vấn hoặc xử lý thực tế.
        return new Report(index, "Report " + index);
    }
}
```

Khi lớp `ReportStore` được khởi tạo, `REPORTS` có kích thước 100 nhưng chưa tạo report nào. Lần đầu `reportAt(7)` được gọi, hàm tính nhận `7` và tạo report tại index đó. Lần truy cập sau vào index `7` nhận lại cùng phần tử đã được tính; các index khác vẫn chưa cần tạo.

Kích thước và index hợp lệ được xác định ngay từ lúc tạo list. Nếu `size` âm, `List.ofLazy()` ném `IllegalArgumentException`. Truy cập index ngoài phạm vi vẫn ném `IndexOutOfBoundsException` theo hợp đồng của `List`.

### 2.2. Tạo đối tượng theo vị trí

Một trường hợp phù hợp khác là tập đối tượng có vị trí xác định, ví dụ bộ xử lý theo shard hoặc cấu hình cho các tab:

```java
private static final int SHARD_COUNT = 16;

private static final List<ShardReader> READERS =
        List.ofLazy(SHARD_COUNT, shardId -> new ShardReader(shardId));

static ShardReader readerFor(int shardId) {
    return READERS.get(shardId);
}
```

Mỗi index có một `ShardReader` riêng, được tạo khi shard đó lần đầu được dùng. Nếu `ShardReader` mở file hoặc tạo cấu trúc dữ liệu lớn, việc trì hoãn này có thể giảm chi phí startup.

Không dùng mẫu này để tạo pool có số lượng phần tử thay đổi liên tục. Kích thước của lazy list là cố định; nếu số shard thay đổi theo cấu hình, hãy xác định kích thước trước khi tạo list hoặc dùng một cấu trúc khác phù hợp với vòng đời dữ liệu.

## 3. Map.ofLazy: tính value theo key

Chữ ký API trên JDK 26:

```java
static <K, V> Map<K, V> ofLazy(
        Set<? extends K> keys,
        Function<? super K, ? extends V> computingFunction)
```

Tập khóa được xác định ngay lúc tạo map; hàm tính nhận key và trả về value. Các khóa này tồn tại trong map ngay từ đầu, nhưng value tương ứng chỉ được tính khi cần.

Đối số `keys` và `computingFunction` phải khác `null`; tập khóa không được chứa `null`. Nếu cần một tập map rỗng, truyền `Set.of()`; khi đó hàm tính không được gọi.

### 3.1. Ví dụ: tải cấu hình theo locale

```java
import java.util.Locale;
import java.util.Map;
import java.util.Set;

record Messages(String welcome, String goodbye) {}

final class MessageCatalog {
    private static final Set<Locale> SUPPORTED = Set.of(
            Locale.US,
            Locale.UK,
            Locale.FRANCE,
            Locale.JAPAN);

    private static final Map<Locale, Messages> CATALOG =
            Map.ofLazy(SUPPORTED, locale -> loadMessages(locale));

    static Messages forLocale(Locale locale) {
        return CATALOG.get(locale);
    }

    private static Messages loadMessages(Locale locale) {
        // Có thể thay bằng đọc resource bundle hoặc cấu hình.
        return new Messages("Welcome (" + locale + ")", "Goodbye");
    }
}
```

Khi `MessageCatalog` được khởi tạo, map đã biết bốn locale hợp lệ nhưng chưa tải bộ thông điệp nào. Lần đầu gọi `forLocale(Locale.FRANCE)`, `loadMessages()` chỉ chạy cho key đó. Truy cập cùng key về sau nhận lại value đã lưu. Những locale chưa được dùng vẫn chưa phải tải.

`Map.ofLazy()` chỉ tạo mapping cho những key nằm trong `keys`. Gọi `get()` với key không có trong tập này trả về `null`, giống hợp đồng thông thường của `Map` khi không có mapping. Nếu ứng dụng cần báo lỗi khi locale không được hỗ trợ, hãy kiểm tra rõ kết quả hoặc tập key ở tầng nghiệp vụ.

### 3.2. Dùng key enum cho bảng xử lý

Khi tập key là enum, `Map.ofLazy()` giúp mô tả tập tác vụ được hỗ trợ:

```java
import java.util.Map;
import java.util.Set;

enum DocumentKind {
    PDF, CSV, XML
}

final class ParserRegistry {
    private static final Map<DocumentKind, DocumentParser> PARSERS =
            Map.ofLazy(
                    Set.of(DocumentKind.PDF, DocumentKind.CSV, DocumentKind.XML),
                    ParserRegistry::createParser);

    static DocumentParser parserFor(DocumentKind kind) {
        return PARSERS.get(kind);
    }

    private static DocumentParser createParser(DocumentKind kind) {
        return switch (kind) {
            case PDF -> new PdfParser();
            case CSV -> new CsvParser();
            case XML -> new XmlParser();
        };
    }
}
```

Mỗi parser chỉ được tạo khi loại tài liệu tương ứng lần đầu được yêu cầu. Tập key cố định giúp registry thể hiện rõ những loại tài liệu được hỗ trợ. Nếu thêm loại tài liệu mới, cập nhật tập key và hàm tạo cùng nhau.

## 4. Bảo đảm đồng thời và cách xử lý lỗi

Hai factory được thiết kế để dùng an toàn giữa nhiều thread. Với cùng một index của list hoặc cùng một key của map, hàm tính được gọi thành công tối đa một lần. Nếu nhiều thread cùng yêu cầu một phần tử đang được tính, các thread cạnh tranh sẽ chờ cho đến khi phần tử được tạo xong hoặc hàm tính kết thúc bất thường.

Điều này giúp tránh việc hai request đồng thời tạo hai bản sao thành công của cùng một phần tử. Tuy nhiên, việc tính phần tử vẫn chạy trên thread thực hiện truy cập đầu tiên; các thread khác có thể bị block trong lúc chờ. Đây không phải API xử lý bất đồng bộ và không tự cung cấp timeout.

### 4.1. Hàm tính ném exception

Trên JDK 26, nếu hàm tính ném exception, exception được truyền lại cho thread gọi đầu tiên và không có value nào được ghi nhận cho index/key đó. Một lần truy cập sau có thể gọi lại hàm tính. Vì vậy, hàm tính cần an toàn khi thử lại và nên dọn dẹp tài nguyên nếu thất bại giữa chừng.

```java
List<Configuration> CONFIGS = List.ofLazy(4, index -> {
    try {
        return readConfiguration(index);
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
});
```

`IntFunction` và `Function` không khai báo checked exception, nên cần chuyển lỗi checked thành unchecked exception phù hợp hoặc xử lý ngay trong hàm tính. Không tạo side effect không thể đảo ngược trước khi hàm có thể thất bại, vì lần truy cập sau có thể thử lại.

### 4.2. Không cho phép null

Giống các collection được tạo bằng `List.of()` và `Map.of()`, lazy list không cho phép phần tử `null`; lazy map không cho phép key hoặc value `null`. Nếu hàm tính trả về `null`, thao tác truy cập ném `NullPointerException` và giá trị đó không được ghi nhận.

Nếu cần biểu diễn kết quả có thể vắng mặt, dùng `Optional` làm phần tử/value:

```java
List<Optional<User>> USERS = List.ofLazy(
        20,
        index -> Optional.ofNullable(findUser(index)));

Map<String, Optional<Feature>> FEATURES = Map.ofLazy(
        Set.of("search", "export", "billing"),
        name -> Optional.ofNullable(loadFeature(name)));
```

`Optional.empty()` là một object hợp lệ, khác với việc trả `null`.

### 4.3. Tránh khởi tạo đệ quy cùng vị trí

Nếu hàm tính của list truy cập lại chính list tại cùng index đang được tính, hoặc hàm tính của map gọi lại cùng key đang tính, API ném `IllegalStateException`. Đây là dấu hiệu có vòng phụ thuộc trong đồ thị khởi tạo.

Ví dụ thiết kế không an toàn:

```java
// Minh họa lỗi phụ thuộc vòng, không dùng trong ứng dụng.
final class CircularValues {
    private static List<String> values;

    static {
        values = List.ofLazy(1, index -> values.get(index));
    }
}
```

Hàm tính phải tạo value từ dữ liệu độc lập hoặc từ các dependency khác không dẫn ngược về chính vị trí/key đang tính. Hãy thiết kế đồ thị phụ thuộc theo một chiều để tránh vòng lặp.

## 5. Các thao tác có thể kích hoạt tính lười

Tạo collection, đọc kích thước hoặc kiểm tra tập key không nhất thiết phải tạo tất cả value. Tuy nhiên, các thao tác cần nội dung có thể kích hoạt hàm tính.

Với list, `get(index)` tạo phần tử ở index đó. Các view như `subList()` và `reversed()` vẫn giữ hành vi lazy. Những thao tác phải duyệt hoặc so sánh phần tử có thể làm khởi tạo nhiều index; riêng `equals()`, `hashCode()` và `toString()` được API nêu rõ là có thể kích hoạt một hoặc nhiều phần tử.

Với map, `get(key)` tạo value của key đó. Các view `values()` và `entrySet()` cũng giữ hành vi lazy khi đọc value. Những thao tác cần duyệt value hoặc so sánh toàn map có thể làm nhiều value được tính; `equals()`, `hashCode()` và `toString()` được API nêu rõ là có thể kích hoạt khởi tạo.

Ví dụ, log trực tiếp toàn bộ collection có thể vô tình xóa bỏ lợi ích trì hoãn:

```java
System.out.println(REPORTS); // toString() có thể yêu cầu nhiều report.
System.out.println(CATALOG); // toString() có thể yêu cầu nhiều value.
```

Khi chỉ muốn quan sát trạng thái, log kích thước, tập key hoặc các thông tin metadata thay vì gọi `toString()` trên toàn bộ collection. Không nên giả định một thao tác debug luôn không gây side effect.

## 6. Collection không thể sửa không có nghĩa phần tử bất biến

`List.ofLazy()` trả về list không thể thêm, xóa hoặc thay thế phần tử. `Map.ofLazy()` trả về map không thể thêm, xóa key hoặc cập nhật mapping. Nhưng tính bất biến này chỉ áp dụng cấu trúc collection.

Nếu phần tử hoặc value là object mutable, code vẫn có thể thay đổi trạng thái của object đó:

```java
List<StringBuilder> buffers = List.ofLazy(
        2,
        index -> new StringBuilder("buffer-" + index));

buffers.get(0).append("-updated"); // Collection không đổi, object bên trong đổi.
```

Nếu cần dữ liệu bất biến, hãy trả về kiểu immutable, record với thành phần bất biến hoặc bản sao không thể sửa. Nếu phần tử cần thay đổi, hãy xác định rõ ai sở hữu trạng thái và cách đồng bộ khi nhiều thread dùng chung object.

Các list và map được tạo bởi factory này cũng là *value-based*: không dùng identity của instance làm hợp đồng, không so sánh bằng `==` để suy ra chúng là cùng collection, và không dùng chính collection làm monitor cho `synchronized`. Hãy dùng `equals()` khi cần so sánh giá trị; tuy nhiên cần nhớ `equals()` có thể kích hoạt việc tính các phần tử/value.

## 7. Vòng đời, bộ nhớ và giới hạn

- **Hàm tính được giữ lại khi còn phần tử chưa khởi tạo.** Collection cần giữ function để tạo các giá trị còn thiếu. Lambda capture một object lớn có thể giữ cả object graph đó sống lâu hơn dự kiến. Sau khi mọi phần tử/value được khởi tạo thành công, implementation của JDK có thể bỏ tham chiếu mạnh đến function.
- **Không hỗ trợ serialization.** Lazy list và lazy map được tạo bởi hai factory này không triển khai `Serializable`. Nếu cần lưu trữ hoặc truyền dữ liệu, hãy materialize thành collection thông thường sau khi đã quyết định cần những phần tử nào.
- **Map không cam kết thứ tự lặp.** `Map.ofLazy()` trả về `Map`; thứ tự duyệt mapping không được bảo đảm. Không dùng nó nếu thuật toán phụ thuộc thứ tự insertion hoặc thứ tự sắp xếp.
- **Tập hợp có kích thước hữu hạn.** List cần biết size và map cần biết toàn bộ keys lúc tạo. Đây không phải cấu trúc phù hợp cho key phát sinh vô hạn hoặc cache có eviction.
- **Không thay thế cache mutable.** Không có API để xóa một phần tử đã tính, thay value, đặt TTL hoặc giới hạn số phần tử đã tạo.
- **Không phải async loading.** Thread gọi lần đầu thực hiện computation; thread khác cần cùng phần tử có thể chờ. Nếu cần tải nền, cancellation hoặc timeout, dùng cơ chế tác vụ/cache bất đồng bộ phù hợp.
- **Không bảo đảm tiết kiệm nếu cuối cùng dùng hết.** Nếu mọi phần tử đều được truy cập, tất cả vẫn được tính và collection còn có chi phí giữ function trong giai đoạn chưa hoàn tất.

## 8. So sánh với các collection và cache thông thường

| Nhu cầu | API/cấu trúc phù hợp | Điểm khác biệt |
|---|---|---|
| Danh sách nhỏ, giá trị đã có sẵn | `List.of(...)` | Tính giá trị trước khi gọi factory; list không thể sửa |
| Sao chép dữ liệu hiện có thành list không thể sửa | `List.copyOf(...)` | Copy cấu trúc và các tham chiếu phần tử tại thời điểm gọi |
| Danh sách có thể thêm, xóa, thay thế | `ArrayList` | Mutable, phù hợp khi kích thước hoặc nội dung thay đổi |
| Tập key cố định, value đắt và chỉ một phần được dùng | `Map.ofLazy(...)` | Key biết trước, value được tính theo lần truy cập |
| Map thay đổi theo request hoặc cần xóa/evict | `HashMap` hoặc cache chuyên dụng | Hỗ trợ cập nhật, xóa và chính sách vòng đời phù hợp |
| Tính một giá trị lazy độc lập | `LazyConstant<T>` | Một nội dung được thiết lập tối đa một lần |

Chọn `List.ofLazy()` khi có một dãy index cố định và mỗi vị trí có thể được yêu cầu độc lập. Chọn `Map.ofLazy()` khi miền key đã biết và chỉ cần tính value cho những key thực sự được dùng. Nếu dữ liệu thay đổi theo thời gian, số lượng không cố định hoặc cần eviction, dùng collection/cache có khả năng cập nhật.

## 9. Trạng thái preview và cách bật trên JDK 26

`List.ofLazy()` và `Map.ofLazy()` được bổ sung từ JDK 26 và là preview API trong JEP 526 (*Lazy Constants, Second Preview*). Chúng không phải API Java SE final. JEP 526 cũng thay đổi đáng kể thiết kế so với JEP 502 (*Stable Values*, preview đầu tiên ở JDK 25); khi viết code cho JDK 26, phải dùng đúng chữ ký `List.ofLazy(int, IntFunction)` và `Map.ofLazy(Set, Function)` trong Java SE 26 API Specification.

Biên dịch và chạy với JDK 26, bật preview ở cả hai bước:

```bash
javac --release 26 --enable-preview LazyCollectionsDemo.java
java --enable-preview LazyCollectionsDemo
```

Nếu dùng Maven hoặc Gradle, bật preview cho compiler và JVM chạy test/app. Chỉ bật ở bước biên dịch là chưa đủ. Preview của JDK 26 gắn với chính release 26; bytecode dùng preview không phải cam kết chạy được trên JDK 25 hoặc JDK 27. Khi nâng JDK, đọc lại JEP và API Specification của phiên bản đích, rồi biên dịch và kiểm tra lại mã nguồn.

Nếu dự án yêu cầu API ổn định không preview, có thể tạo collection thông thường bằng `List.of()`, `List.copyOf()`, `Map.of()` hoặc `Map.copyOf()` sau khi tính dữ liệu; nếu cần trì hoãn việc tính thì triển khai lazy holder/cache bằng API ổn định phù hợp với chính sách vòng đời và đồng thời của ứng dụng. Không đưa `ofLazy()` vào hợp đồng thư viện công khai nếu người dùng thư viện không thể chấp nhận ràng buộc preview của JDK 26.

## Tài liệu tham khảo

- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526)
- [Java SE 26 API: List.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#ofLazy(int,java.util.function.IntFunction))
- [Java SE 26 API: Map.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#ofLazy(java.util.Set,java.util.function.Function))
- [Java SE 26 API: LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [JEP 502: Stable Values (First Preview in JDK 25)](https://openjdk.org/jeps/502)
