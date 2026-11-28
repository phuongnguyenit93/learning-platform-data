# Phần thực hành dùng API preview Java 27 hiện hành

*Tình trạng phiên bản được đối chiếu đến ngày 27/11/2026.*

Java 27 đã là bản JDK phát hành chính thức (GA), nhưng các factory tạo tập hợp khởi tạo trễ vẫn là API preview. Trong JDK 27, ba factory hiện có là `List.ofLazy(...)`, `Map.ofLazy(...)` và `Set.ofLazy(...)`. Hai factory đầu đã xuất hiện trong JDK 26; `Set.ofLazy(...)` được bổ sung từ JDK 27.

Các factory này tạo tập hợp có cấu trúc cố định và không cho sửa đổi. Phần tử của List, giá trị của Map hoặc trạng thái thành viên của Set chỉ được tính khi cần truy cập. Mỗi vị trí, khóa hoặc ứng viên được tính thành công tối đa một lần; nếu nhiều thread cùng yêu cầu một mục đang tính, các thread cạnh tranh sẽ chờ kết quả. Khi hàm tính thất bại, cách xử lý lần truy cập tiếp theo phụ thuộc phiên bản JDK.

Đây là API preview trong module chuẩn `java.base`. Khi biên dịch và chạy bằng JDK 27, cần bật `--enable-preview` ở cả hai bước; không cần thêm module incubator.

## 1. Phân biệt ba factory

| Factory | Tham số đầu vào | Phần được tính trễ | Lần truy cập kích hoạt |
|---|---|---|---|
| `List.ofLazy(size, function)` | Kích thước cố định và `IntFunction` nhận index | Giá trị tại từng index | `list.get(index)` |
| `Map.ofLazy(keys, function)` | Tập khóa cố định và `Function` nhận key | Giá trị gắn với từng key | `map.get(key)` |
| `Set.ofLazy(candidates, predicate)` | Tập ứng viên cố định và `Predicate` | Trạng thái có thuộc Set hay không của từng ứng viên | `set.contains(candidate)` |

Có thể nhớ sự khác nhau bằng ba câu:

- List biết trước **có bao nhiêu vị trí**, nhưng chưa biết giá trị tại mỗi vị trí.
- Map biết trước **những khóa nào tồn tại**, nhưng chưa tính giá trị tương ứng.
- Set biết trước **những phần tử nào có thể được xét**, nhưng chưa xác định ứng viên nào thực sự là thành viên.

Lazy collection không phải collection có thể tự tăng kích thước hoặc nhận khóa mới. Tập vị trí, khóa và ứng viên đã được xác định lúc tạo collection.

## 2. Thực hành List.ofLazy

Chữ ký API:

```java
static <E> List<E> ofLazy(
        int size,
        IntFunction<? extends E> computingFunction
)
```

List có kích thước cố định. Hàm cung cấp giá trị nhận index kiểu `int` và trả về phần tử tương ứng. Khi chương trình gọi `get(index)` lần đầu, hàm được gọi để tạo phần tử đó. Các index khác có trạng thái khởi tạo độc lập.

Ví dụ tạo danh sách báo cáo:

```java
import java.util.List;

record Report(int id, String title) {}

public class LazyListDemo {
    private static Report loadReport(int index) {
        System.out.println("Computing report " + index);
        return new Report(index, "Report-" + index);
    }

    public static void main(String[] args) {
        List<Report> reports =
                List.ofLazy(4, LazyListDemo::loadReport);

        System.out.println("List size: " + reports.size());

        Report first = reports.get(2);
        Report second = reports.get(2);

        System.out.println(first);
        System.out.println("Same object: " + (first == second));
        System.out.println(reports.get(0));
    }
}
```

Diễn tiến:

1. `List.ofLazy(4, ...)` tạo List có bốn vị trí. Chưa có báo cáo nào được tải.
2. `reports.size()` trả về `4` mà không cần tạo các báo cáo vì kích thước đã biết.
3. `reports.get(2)` kích hoạt hàm với index `2`.
4. Lần gọi `get(2)` tiếp theo trả lại giá trị đã lưu, không chạy hàm lần nữa.
5. `reports.get(0)` kích hoạt riêng phép tính tại index `0`.

Thứ tự truy cập không bắt buộc theo thứ tự index. Nếu ứng dụng chỉ cần một vài phần tử trong một danh sách lớn, các phần tử còn lại có thể chưa bao giờ được tính.

Một số đặc điểm cần nhớ:

- Kích thước âm làm `List.ofLazy()` ném `IllegalArgumentException`.
- Hàm tính là `null` làm factory ném `NullPointerException`.
- Phần tử được tính không được là `null`.
- List không cho thêm, xóa hoặc thay thế phần tử; thao tác sửa đổi ném `UnsupportedOperationException`.
- `subList()` và `reversed()` vẫn giữ hành vi tính trễ.
- List và các view này hỗ trợ `RandomAccess`.
- List lazy không triển khai `Serializable`.

Các phương thức `equals()`, `hashCode()` và `toString()` có thể làm khởi tạo một hoặc nhiều phần tử. Vì thế, việc log cả List hoặc so sánh hai List có thể kích hoạt nhiều phép tính mà chương trình chưa chủ động gọi `get()`.

## 3. Thực hành Map.ofLazy

Chữ ký API:

```java
static <K, V> Map<K, V> ofLazy(
        Set<? extends K> keys,
        Function<? super K, ? extends V> computingFunction
)
```

Khác với List, Map nhận một Set khóa có sẵn. Những khóa này được biết ngay lúc tạo Map; chỉ giá trị của từng khóa được tính trễ. Hàm cung cấp giá trị nhận khóa và trả về giá trị tương ứng.

Ví dụ tải thông tin quốc gia theo mã:

```java
import java.util.Map;
import java.util.Set;

record Country(String code, String name) {}

public class LazyMapDemo {
    private static Country loadCountry(String code) {
        System.out.println("Loading " + code);
        return switch (code) {
            case "VN" -> new Country(code, "Vietnam");
            case "JP" -> new Country(code, "Japan");
            case "US" -> new Country(code, "United States");
            default -> throw new IllegalArgumentException(code);
        };
    }

    public static void main(String[] args) {
        Map<String, Country> countries = Map.ofLazy(
                Set.of("VN", "JP", "US"),
                LazyMapDemo::loadCountry
        );

        System.out.println(countries.containsKey("JP"));

        Country first = countries.get("JP");
        Country second = countries.get("JP");

        System.out.println(first);
        System.out.println("Same value: " + (first == second));

        System.out.println(countries.get("FR"));
    }
}
```

Diễn tiến:

1. `Map.ofLazy(...)` nhận ba khóa `VN`, `JP` và `US`. Chưa tên quốc gia nào được tải.
2. `containsKey("JP")` kiểm tra khóa đã biết, không cần gọi hàm tạo giá trị.
3. `get("JP")` lần đầu gọi hàm với key `JP` và lưu kết quả.
4. `get("JP")` tiếp theo trả lại giá trị đã lưu.
5. `get("FR")` trả về `null` vì `FR` không thuộc tập khóa đã cung cấp; hàm tính không được gọi cho khóa này.

Các giới hạn của Map lazy:

- Tập khóa đầu vào và hàm tính không được là `null`; khóa null không được phép.
- Khóa phải có quan hệ tương đương nhất quán với `equals()`.
- Nếu Set khóa đầu vào bị sửa sau khi tạo Map, Map đã tạo không phản ánh thay đổi đó.
- Map không cho thêm, xóa hoặc cập nhật mapping.
- Giá trị trả về không được là `null`. Nếu nghiệp vụ có thể không tìm thấy giá trị, hãy trả `Optional<V>`.
- `values()` và `entrySet()` cũng giữ hành vi tính trễ.
- `equals()`, `hashCode()` và `toString()` có thể kích hoạt khởi tạo một hoặc nhiều giá trị.
- Map lazy không triển khai `Serializable`.

Map lazy hữu ích khi miền khóa đã xác định, nhưng việc tạo từng giá trị tốn chi phí. Ví dụ: bảng cấu hình theo mã quốc gia, metadata theo loại tài liệu, bảng tính kết quả cho tập tham số đã biết hoặc các thành phần dịch vụ được chọn bằng key.

Không dùng `Map.ofLazy()` như một cache không giới hạn. Nó không nhận khóa tùy ý, không có eviction và không có thao tác refresh.

## 4. Thực hành Set.ofLazy

`Set.ofLazy()` được bổ sung từ JDK 27. Chữ ký API:

```java
static <E> Set<E> ofLazy(
        Set<? extends E> elementCandidates,
        Predicate<? super E> computingFunction
)
```

Thay vì tính một giá trị, factory này tính trạng thái thành viên cho từng ứng viên. Hàm `Predicate` trả về:

- `true`: ứng viên là phần tử của Set.
- `false`: ứng viên không phải phần tử của Set.

Ví dụ kiểm tra các quyền được bật:

```java
import java.util.EnumSet;
import java.util.Set;

enum Permission {
    READ, WRITE, ADMIN
}

public class LazySetDemo {
    private static boolean isEnabled(Permission permission) {
        System.out.println("Checking " + permission);

        return switch (permission) {
            case READ, WRITE -> true;
            case ADMIN -> false;
        };
    }

    public static void main(String[] args) {
        Set<Permission> enabled = Set.ofLazy(
                EnumSet.allOf(Permission.class),
                LazySetDemo::isEnabled
        );

        System.out.println(enabled.contains(Permission.READ));
        System.out.println(enabled.contains(Permission.READ));
        System.out.println(enabled.contains(Permission.ADMIN));
    }
}
```

Diễn tiến:

1. `EnumSet.allOf(Permission.class)` cung cấp tập ứng viên gồm `READ`, `WRITE` và `ADMIN`.
2. Tạo lazy Set chưa gọi `isEnabled()`.
3. `contains(READ)` lần đầu gọi predicate cho `READ` và lưu kết quả `true`.
4. Lần `contains(READ)` thứ hai dùng kết quả đã lưu.
5. `contains(ADMIN)` mới gọi predicate cho `ADMIN` và lưu kết quả `false`.

Set lazy chỉ xét các ứng viên trong tập đầu vào. Nếu gọi `contains()` với phần tử không thuộc tập ứng viên, kết quả là `false` và predicate không được gọi cho phần tử đó.

Những điểm cần chú ý:

- Tập ứng viên, các phần tử trong tập và predicate không được là `null`.
- Tập ứng viên phải dùng `equals()` làm quan hệ tương đương, hoặc comparator phải nhất quán với `equals()`.
- Nếu tập ứng viên đầu vào bị sửa sau khi tạo Set lazy, Set kết quả không phản ánh các thay đổi đó.
- Set kết quả không cho thêm hoặc xóa phần tử.
- Predicate chỉ được gọi tối đa một lần cho mỗi ứng viên, kể cả khi nhiều thread cùng gọi `contains()`.
- Set lazy không triển khai `Serializable`.

Những thao tác cần duyệt hoặc so sánh toàn bộ Set có thể làm nhiều ứng viên được đánh giá. Tương tự List và Map, `equals()`, `hashCode()` và `toString()` có thể kích hoạt khởi tạo trạng thái thành viên của một hoặc nhiều ứng viên.

## 5. Đảm bảo khi nhiều thread cùng truy cập

Cả ba factory đều bảo đảm hàm tính được gọi thành công tối đa một lần cho mỗi đơn vị:

| Collection | Đơn vị khởi tạo độc lập |
|---|---|
| Lazy List | Mỗi index |
| Lazy Map | Mỗi key |
| Lazy Set | Mỗi ứng viên |

Nếu một thread đang tính phần tử tại index 2, thread khác gọi `get(2)` phải đợi kết quả. Điều này cũng áp dụng với cùng key của Map và cùng ứng viên của Set. Những phần tử khác nhau có trạng thái khởi tạo riêng.

Các factory không biến việc tính toán thành tác vụ bất đồng bộ. Hàm tính được gọi khi truy cập cần kết quả; thread kích hoạt lần truy cập đầu tiên có thể phải chờ hàm hoàn tất. Vì vậy:

- Không đặt thao tác I/O có thể chờ vô hạn vào hàm tính nếu nhiều thread có thể cùng truy cập.
- Không gọi đệ quy chính collection với cùng index, key hoặc ứng viên đang được tính.
- Không dùng lazy collection thay cho executor, future hoặc cơ chế timeout/cancellation.
- Nếu hàm tính phụ thuộc vào trạng thái mutable bên ngoài, hãy xác định rõ snapshot và đồng bộ của trạng thái đó.

Tính an toàn khi nhiều thread truy cập collection không làm cho object được lưu tự động thread-safe. Nếu phần tử là một object mutable, các thread vẫn phải đồng bộ khi sửa trạng thái bên trong object đó.

## 6. Xử lý lỗi và khác biệt giữa Java 26 với Java 27

Đây là khác biệt cần kiểm tra khi nâng cấp. Trong JDK 26, `List.ofLazy()` và `Map.ofLazy()` mới có; nếu hàm tính ném exception, exception được truyền lại cho lần truy cập ban đầu và giá trị chưa được ghi nhận. Một lần truy cập sau có thể gọi lại hàm tính.

Trong JDK 27, lazy collections dùng trạng thái lỗi được lưu cho từng index, key hoặc ứng viên:

| Tình huống | Java 26 – List/Map | Java 27 – List/Map/Set |
|---|---|---|
| Hàm tính thành công | Lưu kết quả và tái sử dụng | Lưu kết quả và tái sử dụng |
| Hàm tính ném unchecked exception | Truyền exception cho caller; lần truy cập sau có thể thử lại | Chuyển đơn vị đó sang error state; lần đầu ném `NoSuchElementException` với exception gốc làm cause |
| Truy cập lại đơn vị đang lỗi | Có thể gọi lại hàm tính | Ném `NoSuchElementException` lần nữa, không gọi lại hàm tính |
| Hàm List/Map trả về `null` | Ném `NullPointerException`; không lưu giá trị | Chuyển sang error state và ném `NoSuchElementException` với `NullPointerException` làm cause |
| Hàm tính đệ quy cùng index/key/candidate | Ném `IllegalStateException` | Ném `NoSuchElementException` với `IllegalStateException` làm cause |

Set không có trường hợp predicate trả về null vì `Predicate.test()` trả về boolean nguyên thủy.

Ví dụ kiểm tra lỗi của List trên Java 27:

```java
import java.util.List;
import java.util.NoSuchElementException;

public class LazyFailureDemo {
    public static void main(String[] args) {
        List<String> values = List.ofLazy(2, index -> {
            if (index == 1) {
                throw new IllegalStateException("Cannot load item");
            }
            return "item-" + index;
        });

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(values.get(1));
            } catch (NoSuchElementException e) {
                System.out.println("Attempt " + attempt);
                System.out.println("Cause: " + e.getCause());
            }
        }
    }
}
```

Lần truy cập đầu tiên vào index 1 làm hàm tính ném `IllegalStateException`. Java 27 chuyển index này sang error state và ném `NoSuchElementException` có cause. Lần truy cập tiếp theo không chạy lại hàm tính; nó tiếp tục ném `NoSuchElementException` nhưng không còn cause.

Vì vậy, hàm tính nên có hành vi xác định và có thể hoàn thành ổn định. Nếu ứng dụng cần retry khi dịch vụ ngoài tạm thời lỗi, hãy thiết kế retry bên trong hàm tính hoặc ở tầng dịch vụ trước khi kết quả đi vào lazy collection. Không giả định lần gọi collection tiếp theo sẽ tự retry như cách hoạt động của List/Map trong JDK 26.

## 7. Những thao tác có thể kích hoạt khởi tạo ngoài dự kiến

Không chỉ `get()` và `contains()` mới làm tính toán xảy ra. Các thao tác có nhu cầu đọc phần tử cũng có thể kích hoạt hàm tính:

| Collection | Truy cập trực tiếp | Thao tác khác có thể kích hoạt tính |
|---|---|---|
| List | `get(index)` | `subList()` view khi đọc, `reversed()` view khi đọc, `equals()`, `hashCode()`, `toString()` |
| Map | `get(key)` | Duyệt `values()` hoặc `entrySet()`, `equals()`, `hashCode()`, `toString()` |
| Set | `contains(candidate)` | Duyệt, so sánh, `equals()`, `hashCode()`, `toString()` |

Ví dụ, việc ghi log:

```java
System.out.println(lazyList);
System.out.println(lazyMap);
System.out.println(lazySet);
```

có thể kích hoạt nhiều hàm tính vì `toString()` cần biểu diễn nội dung. Tương tự, debugger hoặc công cụ giám sát gọi `toString()` để hiển thị collection có thể vô tình kích hoạt công việc tốn chi phí.

Khi cần kiểm tra trạng thái, hãy log các thông tin không buộc collection duyệt phần tử, ví dụ kích thước List đã biết hoặc khóa Map đã biết. Tránh log toàn bộ collection lazy trong đường xử lý nhạy cảm về độ trễ.

## 8. Phân biệt lazy collection với Stream và collection thông thường

| Đặc điểm | Lazy collection | Stream |
|---|---|---|
| Miền dữ liệu | Kích thước, khóa hoặc ứng viên được cố định khi tạo | Dữ liệu nguồn và pipeline được mô tả; số phần tử có thể phụ thuộc nguồn |
| Thời điểm tính | Khi truy cập từng index, key hoặc ứng viên | Khi có terminal operation |
| Lưu kết quả | Kết quả mỗi đơn vị được ghi nhớ và dùng lại | Stream thông thường không lưu kết quả đã xử lý để dùng lại |
| Truy cập lặp | Có thể lấy lại phần tử đã tính | Stream là one-shot; không tái sử dụng sau terminal operation |
| Sửa đổi collection | Không cho sửa đổi cấu trúc | Stream không phải collection để sửa đổi |
| Mục đích | Giữ tập dữ liệu cố định và khởi tạo từng phần theo nhu cầu | Biến đổi, lọc và xử lý chuỗi dữ liệu |

Ví dụ Stream:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Report> reports = IntStream.range(0, 100)
        .mapToObj(LazyListDemo::loadReport)
        .toList();
```

Terminal operation `toList()` phải tiêu thụ pipeline để tạo List, vì vậy các báo cáo được tạo trong lần thực thi đó. Nếu muốn truy cập index 2 nhiều lần mà chỉ tính báo cáo một lần, `List.ofLazy()` phù hợp hơn.

Không phải mọi pipeline Stream đều eager ngay khi tạo; Stream trì hoãn thực thi đến terminal operation. Điểm khác biệt là sau terminal operation, Stream không phải một container memoize từng kết quả để truy cập lại.

## 9. Giới hạn thiết kế và khi nào nên dùng

Lazy collections được thiết kế cho tập hợp có cấu trúc ổn định, phần tử có thể tính độc lập và không nhất thiết cần tất cả ngay từ đầu.

Nên cân nhắc:

- List có số vị trí cố định nhưng mỗi phần tử cần tải hoặc tạo tốn chi phí.
- Map có tập khóa biết trước nhưng giá trị chỉ cần cho một phần khóa.
- Set có tập ứng viên hữu hạn nhưng việc xác định thành viên tốn chi phí.
- Các giá trị sau khi tính có thể giữ lại trong suốt vòng đời collection.
- Hàm tính không cần timeout, cancellation hoặc refresh riêng.

Không phù hợp:

- Danh sách cần thêm/xóa phần tử thường xuyên.
- Map phải chấp nhận khóa mới theo request.
- Set phải thêm ứng viên sau khi khởi tạo.
- Giá trị cần hết hạn, refresh hoặc eviction.
- Hàm tính có side effect phải chạy lại theo mỗi lần đọc.
- Dữ liệu cần nullable trực tiếp thay vì wrapper.
- Object có vòng đời tài nguyên cần đóng/mở hoặc giải phóng theo chu kỳ.

Cả ba collection là unmodifiable, nhưng điều đó chỉ bảo vệ cấu trúc collection. Nếu giá trị là object mutable, trạng thái bên trong object vẫn có thể thay đổi. Muốn dữ liệu ổn định và dễ chia sẻ giữa thread, nên trả về record hoặc object immutable.

Các phần tử đã khởi tạo có thể đủ điều kiện cho một số tối ưu của JVM như constant folding, tương tự Lazy Constants. Đây là khả năng tối ưu, không phải cam kết rằng mọi truy cập sẽ được constant-fold hoặc mọi workload sẽ nhanh hơn. Đo hiệu năng bằng workload đại diện, tính cả chi phí khởi tạo, số phần tử thật sự được truy cập, bộ nhớ giữ lại và thời gian chờ giữa các thread.

## 10. Biên dịch và chạy với JDK 27

Các factory lazy collections nằm trong `java.util` của module `java.base` và là API preview. Dùng JDK 27 ở cả bước biên dịch và chạy:

```bash
javac --enable-preview --release 27 -d out LazyCollectionsDemo.java
java --enable-preview -cp out LazyCollectionsDemo
```

Không cần `--add-modules` vì đây không phải incubator module. Nếu bỏ `--enable-preview`, compiler hoặc runtime sẽ từ chối sử dụng API preview.

Class file được biên dịch với preview của Java 27 phải chạy trên JDK 27 với preview được bật. Không dùng class file preview của Java 27 như thể nó tương thích với runtime Java 26. Trước khi điều tra lỗi, xác nhận toolchain:

```bash
javac -version
java -version
```

Nếu cần giữ khả năng chạy trên Java 26, chỉ sử dụng `List.ofLazy()` và `Map.ofLazy()`, biên dịch và chạy bằng JDK 26 với preview được bật. `Set.ofLazy()` không tồn tại trong API Java 26. Ngoài ra, cần kiểm tra lại cách xử lý exception vì JDK 26 và JDK 27 có ngữ nghĩa lỗi khác nhau.

## 11. Bài tập thực hành

1. Tạo List 10.000 phần tử bằng `List.ofLazy()`. Ghi log index trong hàm tính, chỉ đọc index 10 và 9000. Xác nhận những index khác chưa được tính.
2. Tạo Map từ tập mã sản phẩm cố định. Hàm tính tải mô tả sản phẩm. Gọi lặp lại cùng key, gọi một key không tồn tại và quan sát số lần hàm được thực thi.
3. Tạo Set từ `EnumSet.allOf()` cho các tính năng hệ thống. Predicate đọc cấu hình bật/tắt. Gọi lặp lại cùng ứng viên và so sánh số lần kiểm tra.
4. Cho hàm tính ném unchecked exception ở một index. Trên Java 27, truy cập index đó hai lần và quan sát `NoSuchElementException` cùng cause ở lần đầu, rồi trạng thái lỗi được ghi nhớ ở lần sau.
5. Gọi `toString()` trên List lazy trước và sau khi đọc một phần tử. Quan sát những phần tử nào được khởi tạo.
6. So sánh chi phí của List eager, Stream terminal operation và `List.ofLazy()` trong trường hợp chỉ truy cập 1%, 50% và 100% phần tử.

Khi hoàn thành, cần giải thích được: tập ứng viên được cố định lúc nào, thao tác nào kích hoạt tính toán, mỗi đơn vị được tính bao nhiêu lần, lỗi được ghi nhớ ra sao và phiên bản JDK nào được phép chạy ví dụ.

## Tài liệu tham chiếu

1. [Oracle Java SE 27 API – List.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#ofLazy(int,java.util.function.IntFunction))
2. [Oracle Java SE 27 API – Map.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html#ofLazy(java.util.Set,java.util.function.Function))
3. [Oracle Java SE 27 API – Set.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html#ofLazy(java.util.Set,java.util.function.Predicate))
4. [Oracle Java SE 26 API – List.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#ofLazy(int,java.util.function.IntFunction))
5. [Oracle Java SE 26 API – Map.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#ofLazy(java.util.Set,java.util.function.Function))
6. [Oracle – JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
7. [JEP 531 – Lazy Constants (Third Preview)](https://openjdk.org/jeps/531)
8. [Inside.java – Performance Improvements in JDK 27](https://inside.java/2026/09/28/performance-update-jdk27/)

