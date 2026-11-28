# Tính giá trị theo chỉ số hoặc theo khóa khi được truy cập

## 1. Mục tiêu và bối cảnh phiên bản

Java cung cấp hai factory tạo tập hợp có giá trị được tính khi cần:

- `List.ofLazy(int size, IntFunction<? extends E> computingFunction)`: tính phần tử khi một chỉ số được truy cập lần đầu.
- `Map.ofLazy(Set<? extends K> keys, Function<? super K, ? extends V> computingFunction)`: tính giá trị khi một khóa đã khai báo được truy cập lần đầu.

Hai API này thuộc nhóm Lazy Constants:

| Phiên bản | JEP | Trạng thái |
|---|---|---|
| JDK 26 | JEP 526 — Lazy Constants | Preview lần thứ hai |
| JDK 27 | JEP 531 — Lazy Constants | Preview lần thứ ba |

Tính đến ngày 27/11/2026, JDK 27 là feature release mới hơn. `List.ofLazy` và `Map.ofLazy` vẫn là preview API trong JDK 27; chúng chưa phải hợp đồng ổn định của Java SE. JDK 26 cũng là feature release ngắn hạn và đã kết thúc vòng đời hỗ trợ theo lộ trình Oracle vào tháng 09/2026. Chính sách hỗ trợ thực tế phụ thuộc nhà cung cấp JDK.

Bài học dùng API Java 27 làm chuẩn hiện hành, đồng thời chỉ ra một khác biệt quan trọng về xử lý lỗi giữa JDK 26 và JDK 27. Không nên đưa hai preview API này vào thư viện hoặc dịch vụ cần tương thích dài hạn nếu tổ chức chưa chấp nhận rủi ro thay đổi preview.

## 2. Lazy List và Lazy Map hoạt động như thế nào?

Một tập hợp thông thường thường giữ sẵn các phần tử hoặc giá trị khi được tạo. Với lazy collection, lúc tạo chỉ xác định cấu trúc và cách tính. Phần tử hoặc giá trị cụ thể chỉ được tính khi chương trình truy cập đến vị trí hoặc khóa tương ứng.

Ví dụ:

~~~java
List<String> pages = List.ofLazy(
        100,
        index -> loadPage(index)
);
~~~

Lệnh trên tạo một danh sách có 100 vị trí. Nó chưa cần gọi `loadPage` cho cả 100 vị trí. Khi chương trình gọi `pages.get(42)`, hàm tính mới được gọi cho chỉ số 42. Lần đọc tiếp theo cùng chỉ số lấy lại giá trị đã khởi tạo.

Với map:

~~~java
Set<String> supportedLocales = Set.of("en", "vi", "ja");

Map<String, Bundle> bundles = Map.ofLazy(
        supportedLocales,
        locale -> loadBundle(locale)
);
~~~

Map biết trước ba khóa hợp lệ. Giá trị cho `"vi"` chỉ được tính khi có truy cập khóa đó. Truy cập `"en"` hoặc `"ja"` không cần khởi tạo giá trị `"vi"`.

Có thể hình dung cơ chế này như một tập hợp các ô giá trị độc lập. Mỗi ô giữ một hàm tính và trạng thái khởi tạo riêng. Khi một ô được truy cập, nó được tính một lần; các lần đọc sau dùng kết quả đã có.

Các phần tử lazy được xây dựng trên mô hình Lazy Constants. Sau khi một giá trị được khởi tạo, JVM có thể xem liên kết tới giá trị đó như một hằng số và giá trị có thể đủ điều kiện cho một số tối ưu hóa như constant folding. Đây là cơ hội tối ưu hóa của runtime, không phải cam kết mọi lần đọc đều được biên dịch thành hằng số hoặc ứng dụng chắc chắn nhanh hơn. Hãy đo trên workload thực tế.

## 3. Tạo danh sách tính theo chỉ số với List.ofLazy

### 3.1. Cú pháp và ý nghĩa tham số

~~~java
List<E> values = List.ofLazy(
        int size,
        IntFunction<? extends E> computingFunction
);
~~~

- `size`: số phần tử của danh sách. Kích thước được cố định ngay khi tạo.
- `computingFunction`: nhận chỉ số `int` và trả về phần tử tương ứng.
- `get(index)`: kích hoạt việc tính phần tử tại chỉ số nếu phần tử đó chưa được khởi tạo.

Kích thước âm gây `IllegalArgumentException`; hàm tính `null` gây `NullPointerException`. Chỉ số truy cập vẫn phải nằm trong miền `0` đến `size - 1` như các `List` khác.

Ví dụ danh sách tên báo cáo theo số thứ tự:

~~~java
List<String> reports = List.ofLazy(
        5,
        index -> "report-" + (index + 1)
);

System.out.println(reports.size()); // 5
System.out.println(reports.get(2)); // report-3
System.out.println(reports.get(2)); // report-3, dùng lại kết quả
System.out.println(reports.get(4)); // report-5
~~~

Danh sách có kích thước 5 ngay khi được tạo. Việc gọi `size()` không cần tính nội dung các phần tử. Chỉ số bắt đầu từ 0, giống mọi `List` thông thường.

### 3.2. Ví dụ với phép tính tốn chi phí

Giả sử hệ thống có nhiều trang báo cáo, nhưng mỗi request chỉ xem một vài trang:

~~~java
private static Report loadReport(int pageIndex) {
    // Đọc dữ liệu, tổng hợp và tạo báo cáo cho một trang.
    return new Report("Page " + pageIndex);
}

private static final List<Report> REPORTS = List.ofLazy(
        1_000,
        LazyReportExample::loadReport
);
~~~

Khi người dùng mở trang 18:

~~~java
Report report = REPORTS.get(18);
~~~

Chỉ phần tử tại chỉ số 18 được yêu cầu tính. Nếu request khác truy cập lại chỉ số 18, danh sách trả về cùng giá trị đã khởi tạo thay vì gọi lại hàm tính.

Lazy list phù hợp khi:

- Số vị trí đã biết trước.
- Mỗi vị trí có thể được yêu cầu độc lập.
- Chi phí tính một phần tử đáng kể.
- Không phải mọi phần tử đều chắc chắn được truy cập.

Không dùng lazy list như một danh sách vô hạn. API yêu cầu một kích thước hữu hạn và cố định khi tạo.

### 3.3. Các view vẫn giữ tính lazy

Tài liệu Java SE 27 quy định các phần tử trong `subList()` và `reversed()` view của lazy list cũng được tính trễ.

~~~java
List<String> pages = List.ofLazy(
        10,
        index -> "page-" + index
);

List<String> middlePages = pages.subList(3, 7);
String page = middlePages.get(1); // tương ứng chỉ số 4 của pages

List<String> reversePages = pages.reversed();
String lastPage = reversePages.get(0); // tương ứng chỉ số 9 của pages
~~~

Việc tạo view không đồng nghĩa phải tính toàn bộ phần tử. Khi truy cập một vị trí trong view, phần tử tương ứng của danh sách gốc mới được yêu cầu.

Lazy list và các view của nó triển khai `RandomAccess`. Tuy vậy, không nên giả định mọi thao tác trên danh sách đều miễn phí: một số phương thức có thể phải đọc nhiều phần tử và vì thế kích hoạt nhiều phép tính.

## 4. Tạo map tính theo khóa với Map.ofLazy

### 4.1. Cú pháp và ý nghĩa tham số

~~~java
Map<K, V> values = Map.ofLazy(
        Set<? extends K> keys,
        Function<? super K, ? extends V> computingFunction
);
~~~

- `keys`: tập hợp các khóa hợp lệ được xác định ngay khi tạo map.
- `computingFunction`: nhận khóa và tạo giá trị tương ứng.
- `get(key)`: nếu khóa thuộc tập khóa đã khai báo, giá trị được tính khi truy cập lần đầu.

Tập khóa và hàm tính phải khác `null`; tập khóa không được chứa khóa `null`. Hàm tính phải trả về giá trị khác `null`.

Ví dụ tính mã vùng theo mã quốc gia:

~~~java
Set<String> countryCodes = Set.of("VN", "JP", "US");

Map<String, String> callingCodes = Map.ofLazy(
        countryCodes,
        country -> switch (country) {
            case "VN" -> "+84";
            case "JP" -> "+81";
            case "US" -> "+1";
            default -> throw new IllegalArgumentException(country);
        }
);

System.out.println(callingCodes.get("VN")); // +84
System.out.println(callingCodes.get("VN")); // dùng lại giá trị đã tính
System.out.println(callingCodes.get("FR")); // null: khóa không tồn tại
~~~

Các khóa hợp lệ đã biết từ đầu. `"FR"` không thuộc tập khóa nên không được chuyển tới hàm tính; `get("FR")` trả về `null`.

### 4.2. Tập khóa là cố định

Map được tạo với một tập khóa đã xác định. Nếu tập `Set` ban đầu bị sửa đổi sau khi gọi `Map.ofLazy`, map đã tạo không phản ánh những thay đổi đó.

~~~java
Set<String> keys = new HashSet<>(Set.of("A", "B"));

Map<String, String> values = Map.ofLazy(
        keys,
        key -> "value-" + key
);

keys.add("C");

System.out.println(values.get("C")); // null
~~~

Đây là điểm khác với một `HashMap` có thể thêm khóa bằng `put`. `Map.ofLazy` không phải map cache có thể mở rộng tập khóa trong lúc chạy.

Tập khóa đầu vào không được là `null` và không được chứa khóa `null`. Quan hệ tương đương của `Set` phải nhất quán với `equals`; nếu dùng một `Set` có comparator không nhất quán với `equals`, hành vi được xem là không xác định theo hợp đồng API.

### 4.3. Các view của Map cũng có thể kích hoạt tính toán

Giá trị trong các view `values()` và `entrySet()` cũng được tính trễ. Ví dụ:

~~~java
Map<String, String> messages = Map.ofLazy(
        Set.of("en", "vi", "ja"),
        locale -> loadMessageBundle(locale)
);

String vietnamese = messages.get("vi"); // chỉ tính giá trị vi

messages.values().forEach(System.out::println);
// Khi duyệt values, các giá trị còn chưa khởi tạo cũng sẽ được truy cập.
~~~

Nếu mục tiêu là chỉ tải một vài giá trị, tránh gọi các thao tác duyệt toàn bộ map một cách vô tình. `equals()`, `hashCode()` và `toString()` của lazy map cũng có thể kích hoạt việc tính một hoặc nhiều giá trị.

## 5. Ví dụ hoàn chỉnh cho cả List và Map

Tạo file `LazyCollectionsDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyCollectionsDemo {
    private static final AtomicInteger PAGE_COMPUTATIONS =
            new AtomicInteger();

    private static final List<String> PAGES = List.ofLazy(
            5,
            index -> {
                PAGE_COMPUTATIONS.incrementAndGet();
                System.out.println("Computing page index " + index);
                return "Page " + (index + 1);
            }
    );

    private static final AtomicInteger BUNDLE_COMPUTATIONS =
            new AtomicInteger();

    private static final Set<String> LOCALES =
            Set.of("en", "vi", "ja");

    private static final Map<String, String> BUNDLES = Map.ofLazy(
            LOCALES,
            locale -> {
                BUNDLE_COMPUTATIONS.incrementAndGet();
                System.out.println("Computing locale " + locale);

                return switch (locale) {
                    case "en" -> "English bundle";
                    case "vi" -> "Vietnamese bundle";
                    case "ja" -> "Japanese bundle";
                    default -> throw new IllegalArgumentException(locale);
                };
            }
    );

    public static void main(String[] args) {
        System.out.println("List size: " + PAGES.size());
        System.out.println("Page computations: "
                + PAGE_COMPUTATIONS.get());

        System.out.println(PAGES.get(2));
        System.out.println(PAGES.get(2));

        System.out.println("Page computations: "
                + PAGE_COMPUTATIONS.get());

        System.out.println(BUNDLES.get("vi"));
        System.out.println(BUNDLES.get("vi"));
        System.out.println(BUNDLES.get("fr"));

        System.out.println("Bundle computations: "
                + BUNDLE_COMPUTATIONS.get());
    }
}
~~~

Kết quả minh họa:

~~~text
List size: 5
Page computations: 0
Computing page index 2
Page 3
Page 3
Page computations: 1
Computing locale vi
Vietnamese bundle
Vietnamese bundle
null
Bundle computations: 1
~~~

Điều cần quan sát:

1. Tạo danh sách và gọi `size()` chưa tính phần tử nào.
2. Lần đầu `get(2)` gọi hàm tính cho chỉ số 2.
3. Lần thứ hai `get(2)` không gọi lại hàm tính.
4. Lần đầu `get("vi")` tính bundle tiếng Việt; lần đọc sau dùng lại kết quả.
5. Khóa `"fr"` không có trong tập khóa nên trả về `null`, không gọi hàm tính.

## 6. An toàn khi nhiều thread truy cập

Cả `List.ofLazy` và `Map.ofLazy` bảo đảm hàm tính được gọi nhiều nhất một lần cho mỗi chỉ số hoặc mỗi khóa, kể cả khi nhiều thread truy cập cùng một phần tử đồng thời.

Nếu một thread đang tính phần tử tại chỉ số 3 và thread khác cũng gọi `get(3)`, thread thứ hai chờ kết quả của phép tính đang chạy. Nó không tạo một phép tính thứ hai cho cùng chỉ số.

Ví dụ kiểm tra cùng một chỉ số từ nhiều thread:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger computations = new AtomicInteger();

List<Integer> values = List.ofLazy(1, index -> {
    computations.incrementAndGet();
    return 42;
});

IntStream.range(0, 1_000)
        .parallel()
        .forEach(ignored -> values.get(0));

if (computations.get() != 1) {
    throw new AssertionError("Expected one computation");
}
~~~

Khi nhiều thread cùng truy cập chỉ số 0, hàm tính chỉ được gọi một lần. Các lần đọc đồng thời còn lại chờ phần tử đó được tính xong.

Tuy nhiên, các chỉ số hoặc khóa khác nhau có thể được tính đồng thời. Vì vậy:

- Hàm tính phải an toàn khi nhiều thread chạy cho các chỉ số/khóa khác nhau.
- Không dựa vào thứ tự các phần tử được khởi tạo.
- Hạn chế tác dụng phụ dùng chung như ghi vào một collection không thread-safe.
- Không dùng khóa của chính lazy collection để tự đồng bộ hóa logic nghiệp vụ.
- Tránh gọi đệ quy để tính lại chính chỉ số hoặc khóa đang được khởi tạo.

Cơ chế bảo đảm at-most-once cho từng ô giá trị; nó không biến mọi trạng thái dùng chung bên trong hàm tính thành thread-safe.

## 7. Xử lý lỗi và giá trị null trên JDK 27

Đây là phần cần đặc biệt lưu ý khi chuyển từ JDK 26 sang JDK 27.

### 7.1. Hàm tính trả về null

Lazy List và Lazy Map không chứa phần tử hoặc giá trị `null`. Nếu hàm tính trả về `null`, lần truy cập sẽ thất bại bằng `NoSuchElementException` với `NullPointerException` làm nguyên nhân.

Nếu nghiệp vụ cần biểu diễn “không có kết quả”, hãy dùng một kiểu giá trị không null, chẳng hạn `Optional`:

~~~java
List<Optional<String>> results = List.ofLazy(
        3,
        index -> findValue(index)
                ? Optional.of(loadValue(index))
                : Optional.empty()
);
~~~

### 7.2. Hàm tính ném unchecked exception

Theo hợp đồng API JDK 27, khi hàm tính ném unchecked exception cho một chỉ số hoặc khóa:

1. Phần tử chuyển sang trạng thái lỗi.
2. Lần truy cập đang kích hoạt phép tính nhận `NoSuchElementException` với exception gốc làm cause.
3. Những lần truy cập sau cùng chỉ số/khóa tiếp tục nhận `NoSuchElementException`, không gọi lại hàm tính.

Vì vậy, lỗi tính toán được ghi nhớ cho ô giá trị đó trong vòng đời của lazy collection. Không xem lần truy cập sau là cơ hội tự động retry.

Nếu cần retry khi dịch vụ bên ngoài tạm thời lỗi, hãy thiết kế retry/cache riêng hoặc dùng một cấu trúc mutable phù hợp. Lazy collection không phải bộ nhớ đệm tự phục hồi cho thao tác I/O không ổn định.

### 7.3. Đệ quy vào cùng chỉ số hoặc khóa

Nếu hàm tính trực tiếp hoặc gián tiếp gọi lại chính lazy list/map để tính cùng chỉ số hoặc khóa đang chạy, API phát hiện tình huống đệ quy và ném `NoSuchElementException` với `IllegalStateException` làm cause.

Hãy tách phần tính toán thành hàm độc lập hoặc sắp xếp phụ thuộc theo hướng không quay lại chính ô giá trị đang khởi tạo.

### 7.4. Khác biệt lỗi giữa JDK 26 và JDK 27

Tài liệu API JDK 26 mô tả rằng nếu hàm tính ném exception thì exception được truyền lại cho caller đầu tiên và không ghi nhận giá trị; lần truy cập sau có thể gọi lại hàm tính.

JDK 27 thay đổi quy tắc: ô giá trị chuyển sang trạng thái lỗi và những lần truy cập sau không gọi lại hàm tính. Vì vậy, khi nâng từ JDK 26 lên JDK 27, hãy kiểm tra các đoạn code đang dựa vào việc đọc lại để thử tính lần nữa.

Dùng hành vi JDK 27 làm cơ sở cho thiết kế mới. Không viết logic phụ thuộc vào việc preview API có thể đổi lại ở bản sau.

## 8. Giới hạn và các thao tác có thể kích hoạt tính toán

| Đặc điểm | Lazy List | Lazy Map |
|---|---|---|
| Kích thước/cấu trúc | Kích thước cố định | Tập khóa cố định |
| Điểm kích hoạt | Truy cập chỉ số, ví dụ `get(index)` | Truy cập giá trị của khóa, ví dụ `get(key)` |
| Tính lại | Tối đa một lần cho mỗi chỉ số | Tối đa một lần cho mỗi khóa |
| Đồng thời | Nhiều thread cùng chỉ số chờ một phép tính | Nhiều thread cùng khóa chờ một phép tính |
| Thay đổi collection | Không thêm, xóa hoặc thay thế phần tử | Không thêm, xóa hoặc thay giá trị |
| Giá trị null | Không cho phép | Không cho phép |
| Serialization | Không Serializable | Không Serializable |

Một số thao tác có thể khiến nhiều phần tử được khởi tạo:

- Duyệt toàn bộ danh sách hoặc map.
- Gọi `toString()`, `hashCode()` hoặc `equals()`.
- Duyệt `values()` hoặc `entrySet()` của lazy map.
- Chuyển lazy collection thành collection khác bằng cách sao chép hoặc thu thập toàn bộ dữ liệu.

Do đó, một đoạn log như:

~~~java
logger.debug("pages={}", pages);
~~~

có thể gọi `toString()` và làm nhiều phần tử được khởi tạo. Nếu việc tính dữ liệu tốn kém, tránh log trực tiếp toàn bộ lazy collection khi chỉ cần kích thước hoặc một phần tử.

Lazy collection là unmodifiable, nhưng không phải immutable sâu. Nếu một phần tử là đối tượng có thể thay đổi, trạng thái bên trong đối tượng đó vẫn có thể đổi sau khi được trả về. Hãy dùng kiểu giá trị bất biến hoặc kiểm soát quyền sửa đổi nếu cần dữ liệu ổn định.

## 9. So sánh với các API collection thông thường

| API | Cách hoạt động | Khi nên dùng |
|---|---|---|
| `List.of(...)` / `Map.of(...)` | Giá trị được cung cấp ngay khi tạo | Tập hợp nhỏ, dữ liệu đã sẵn sàng |
| `List.copyOf(...)` / `Map.copyOf(...)` | Sao chép các giá trị hiện có thành collection unmodifiable | Cần snapshot không sửa đổi |
| `List.ofLazy(...)` | Tính theo chỉ số khi truy cập lần đầu | Danh sách có kích thước biết trước, phần tử tính độc lập |
| `Map.ofLazy(...)` | Tính theo khóa đã khai báo khi truy cập lần đầu | Tập khóa cố định, giá trị đắt để tính |
| `ConcurrentHashMap.computeIfAbsent(...)` | Tính và đưa giá trị vào map mutable khi khóa chưa có | Cache động, có nhu cầu thêm khóa và chính sách retry phù hợp |

Không nhầm `Map.ofLazy` với `Map.computeIfAbsent`:

- `Map.ofLazy` không thay đổi tập khóa hoặc giá trị đã khởi tạo; map unmodifiable.
- `ConcurrentHashMap.computeIfAbsent` thêm giá trị vào một map mutable và phù hợp hơn cho cache có khóa phát sinh trong lúc chạy.
- `computeIfAbsent` không có mô hình giá trị hằng lazy giống Lazy Constants; không nên kỳ vọng cùng cơ chế tối ưu hóa của JVM.
- Nếu hàm tính có thể lỗi tạm thời và cần retry ở lần truy cập tiếp theo, cache mutable với chính sách lỗi được thiết kế rõ ràng thường phù hợp hơn.

Không cần tự viết một `AbstractList` hoặc `AbstractMap` chỉ để trì hoãn việc tính theo index/key khi có thể dùng các factory chuẩn này. Tuy nhiên, vì các factory vẫn là preview, hãy chọn giải pháp stable nếu ứng dụng không thể chấp nhận preview API.

## 10. Khi nào nên và không nên dùng?

### Nên cân nhắc

- Danh sách có số vị trí cố định nhưng phần lớn phần tử ít khi được truy cập.
- Pool gồm một số lượng cố định các thành phần đắt để khởi tạo; mỗi vị trí chỉ cần tạo khi có người dùng đầu tiên.
- Map có một tập khóa hữu hạn đã biết và mỗi giá trị cần tính độc lập.
- Giá trị sau khi tính có thể được giữ lại trong suốt vòng đời collection.
- Hàm tính không phụ thuộc vào thứ tự truy cập và an toàn khi nhiều khóa/chỉ số khác nhau được tính song song.

### Không nên dùng

- Tập khóa thay đổi thường xuyên hoặc danh sách cần thêm/xóa phần tử.
- Nguồn dữ liệu có thể vô hạn hoặc không biết kích thước trước.
- Hàm tính phụ thuộc vào side effect phải chạy đúng một lần theo thứ tự nghiệp vụ.
- Hàm tính thực hiện network call hoặc truy vấn có thể lỗi tạm thời và cần retry tự động.
- Giá trị có thể là `null` mà không được bọc trong một kiểu holder.
- Ứng dụng cần API ổn định cho thư viện công khai hoặc runtime cũ không hỗ trợ preview.

Lazy collection trì hoãn công việc và ghi nhớ kết quả. Nó không thay thế cache phân tán, không quản lý thời hạn hết hạn, không tự làm mới dữ liệu và không bảo đảm kết quả giữa các instance của ứng dụng giống nhau.

## 11. Biên dịch và chạy với preview API

Các factory `List.ofLazy` và `Map.ofLazy` là preview API. Phải bật preview ở cả bước biên dịch và chạy, bằng cùng feature release.

JDK 27:

~~~bash
javac --release 27 --enable-preview -d out LazyCollectionsDemo.java
java --enable-preview -cp out LazyCollectionsDemo
~~~

JDK 26:

~~~bash
javac --release 26 --enable-preview -d out LazyCollectionsDemo.java
java --enable-preview -cp out LazyCollectionsDemo
~~~

Không cần thêm module incubator vì các API nằm trong `java.util`. Không dùng `--enable-preview` với một JDK khác phiên bản đã dùng để biên dịch preview bytecode.

Nếu compiler không nhận ra `List.ofLazy` hoặc `Map.ofLazy`, kiểm tra:

1. JDK compiler có từ phiên bản 26 trở lên không.
2. `--release` có đang đặt thấp hơn 26 không.
3. `--enable-preview` đã được bật khi biên dịch chưa.
4. IDE, CI và runtime có cùng feature release không.

### Mở rộng liên quan trong JDK 27

JDK 27 bổ sung `Set.ofLazy(Set, Predicate)` trong cùng nhóm preview Lazy Constants. Lazy set tính việc một ứng viên có thuộc tập hợp hay không khi có truy vấn membership. Đây là mở rộng cho trường hợp kiểm tra điều kiện theo phần tử; bài học này tập trung vào hai API truy xuất giá trị theo chỉ số và khóa.

## 12. Kết luận

`List.ofLazy` và `Map.ofLazy` cung cấp cách chuẩn để tính giá trị theo nhu cầu mà không phải tự xây dựng collection memoization:

- List xác định trước kích thước và tính mỗi phần tử khi chỉ số được truy cập.
- Map xác định trước tập khóa và tính mỗi giá trị khi khóa được truy cập.
- Mỗi chỉ số hoặc khóa được tính tối đa một lần, kể cả khi có nhiều thread cùng truy cập.
- Collection không cho phép sửa đổi và không chứa giá trị null.
- Trên JDK 27, lỗi tính toán được ghi nhớ thành trạng thái lỗi; lần đọc sau không tự thử lại.
- Cả hai API vẫn là preview trong JDK 27. Chỉ dùng khi dự án chấp nhận yêu cầu bật preview và rủi ro thay đổi API.

Khi cần cache động, retry hoặc hợp đồng ổn định, hãy chọn collection mutable và cơ chế đồng bộ/cache phù hợp. Khi dùng lazy collection, hãy giữ tập vị trí hoặc khóa ổn định, làm hàm tính an toàn với nhiều thread và tránh các thao tác vô tình duyệt toàn bộ dữ liệu.

## Tài liệu tham khảo chính thức

- [JEP 526 — Lazy Constants (Second Preview, JDK 26)](https://openjdk.org/jeps/526)
- [JEP 531 — Lazy Constants (Third Preview, JDK 27)](https://openjdk.org/jeps/531)
- [List — Java SE 26 API, ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [Map — Java SE 26 API, ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html)
- [List — Java SE 27 API, ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html)
- [Map — Java SE 27 API, ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html)
- [Set — Java SE 27 API, ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html)
- [Lazy Constants — Java SE 26 Core Libraries Guide](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Java Release Support Timeline](https://ops.java/releases/?lang=en)
- [Performance Improvements in JDK 27 — Inside Java](https://inside.java/2026/09/28/performance-update-jdk27/)

