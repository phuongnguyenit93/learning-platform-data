# Tạo Map không sửa đổi được bằng `toUnmodifiableMap`

Trong **Java Stream API**, ta có thể dùng pipeline lazy gồm `filter`, `map` và các phép toán trung gian khác để chuẩn bị dữ liệu, rồi dùng `collect` để tạo kết quả. Khi kết quả là bảng tra cứu theo khóa, `Collectors.toMap` là lựa chọn quen thuộc. Nhưng nếu bảng tra cứu đã hoàn thành và **không được phép thêm, xóa hay thay thế ánh xạ**, `Collectors.toUnmodifiableMap` (Java 10+) diễn đạt yêu cầu đó trực tiếp.

Bài này thuộc chương **Thu thập thành Map**: học cách xây `Map<K,V>` không sửa đổi được, xử lý khóa trùng, ngăn giá trị `null`, phân biệt tính không sửa đổi với tính bất biến sâu, và chọn giải pháp khi cần thứ tự hoặc muốn xử lý song song.

## 1. `toUnmodifiableMap` làm gì?

`Collectors.toUnmodifiableMap` là **factory tạo collector**, không phải một phép toán trung gian. Nó được truyền cho terminal operation `Stream.collect(...)`; thao tác thu thập kích hoạt việc duyệt stream và tạo một `Map` không cho phép chỉnh sửa cấu trúc ánh xạ qua API của map trả về.

Ví dụ đơn giản từ danh sách từ khóa:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> lengths = Stream.of("Java", "Stream", "API")
    .collect(Collectors.toUnmodifiableMap(
        word -> word,
        String::length
    ));

System.out.println(lengths.get("Java"));   // 4
System.out.println(lengths.get("Stream")); // 6
System.out.println(lengths.size());        // 3

// Không hợp lệ với map này:
// lengths.put("New", 3);  // UnsupportedOperationException
```

Ở đây, `word -> word` là hàm lấy **khóa**, `String::length` là hàm lấy **giá trị**. Các cặp khóa/giá trị được tạo khi stream được thu thập. Sau khi có kết quả, ta vẫn có thể gọi `get`, `containsKey`, `entrySet`, `size` và các thao tác đọc bình thường.

### Hai overload quan trọng

| Cách gọi | Ý nghĩa | Khi có khóa trùng |
| --- | --- | --- |
| `toUnmodifiableMap(keyMapper, valueMapper)` | Tạo map khi mỗi phần tử sinh khóa duy nhất | Ném `IllegalStateException` |
| `toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` | Tạo map và quy định cách gộp các giá trị có cùng khóa | Gọi `mergeFunction` để xử lý xung đột |

Hai overload đều có trong `java.util.stream.Collectors` từ **Java 10**. Các mapper thuộc họ `java.util.function.Function`; hàm gộp là `BinaryOperator<U>`, nhận hai giá trị kiểu `U` và trả một giá trị cùng kiểu.

Về mặt kiểu, có thể hình dung:

```java
<T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper
);

<T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
);
```

Đừng dựa vào một lớp triển khai cụ thể (như `HashMap` hoặc `LinkedHashMap`): hợp đồng trả về **`Map` không sửa đổi được**, không hứa cấu trúc lưu trữ hoặc thứ tự duyệt.

## 2. Khóa trùng: hiểu ngoại lệ trước khi triển khai

Khóa trong `Map` phải duy nhất theo quy tắc `equals`/`hashCode`. Một nguồn có phần tử khác nhau vẫn có thể tạo **cùng khóa** sau `keyMapper`.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Hai từ Java và JUnit đều có khóa "J".
Map<String, Integer> broken = Stream.of("Java", "JUnit")
    .collect(Collectors.toUnmodifiableMap(
        word -> word.substring(0, 1),
        String::length
    ));

// IllegalStateException vì khóa "J" xuất hiện hai lần.
```

Đây là lỗi theo **hợp đồng collector**, không phải hiện tượng chỉ xảy ra khi chạy song song. Ngay cả khi hai phần tử tạo ra cùng một khóa **và cùng một giá trị**, overload hai tham số vẫn từ chối khóa trùng.

Nếu khóa trùng là điều hợp lệ của bài toán, phải mô tả chính sách gộp một cách rõ ràng:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> totalLengthByInitial =
    Stream.of("Java", "JUnit", "Stream")
        .collect(Collectors.toUnmodifiableMap(
            word -> word.substring(0, 1),
            String::length,
            Integer::sum
        ));

System.out.println(totalLengthByInitial.get("J")); // 9 = 4 + 5
System.out.println(totalLengthByInitial.get("S")); // 6
```

`Integer::sum` là một `BinaryOperator<Integer>`: hai độ dài gặp cùng khóa được cộng thành một giá trị. Chính sách “cộng” không phù hợp với mọi dữ liệu; tùy mục đích, ta có thể chọn giá trị lớn nhất, giá trị nhỏ nhất hoặc gộp nội dung theo một quy tắc khác.

### Ví dụ chọn giá trị lớn nhất theo khóa

```java
import java.util.Comparator;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Character, String> longestByInitial =
    Stream.of("An", "Anh", "Binh", "Bao")
        .collect(Collectors.toUnmodifiableMap(
            word -> word.charAt(0),
            word -> word,
            BinaryOperator.maxBy(
                Comparator.comparingInt(String::length)
            )
        ));

System.out.println(longestByInitial.get('A')); // Anh
System.out.println(longestByInitial.get('B')); // Binh
```

Trong ví dụ này, `maxBy` chỉ so sánh độ dài; nếu hai tên có độ dài bằng nhau, comparator xem chúng là ngang nhau. Khi **cần kết quả duy nhất, ổn định** cho cả trường hợp hòa, hãy bổ sung tiêu chí phụ, ví dụ so sánh chuỗi theo thứ tự chữ cái.

### Khi muốn giữ *tất cả* giá trị theo khóa

Nếu yêu cầu là lưu danh sách sản phẩm cho từng nhóm, `toUnmodifiableMap` với một phép gộp chọn **một** giá trị không phản ánh đúng nghiệp vụ. Khi đó thường dùng `groupingBy`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Character, List<String>> byInitial = Stream.of(
        "An", "Anh", "Binh", "Bao"
    )
    .collect(Collectors.groupingBy(word -> word.charAt(0)));

System.out.println(byInitial.get('A')); // [An, Anh]
```

`groupingBy` ở đây chỉ minh họa sự khác biệt về ý nghĩa: **kết quả mặc định không được bảo đảm là map hay danh sách không sửa đổi được**. Nếu vẫn cần kết quả không sửa đổi được ở cả các cấp, phải thiết kế bước kết thúc phù hợp, tránh nhầm “không thay được map bên ngoài” với “không thay được list bên trong”.

## 3. Null bị từ chối

`toUnmodifiableMap` **không cho phép khóa hoặc giá trị `null`**. Nếu `keyMapper` hoặc `valueMapper` trả về `null`, thao tác thu thập sẽ ném `NullPointerException`.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Ví dụ SAI: valueMapper trả null.
Map<String, String> invalid = Stream.of("A", "B")
    .collect(Collectors.toUnmodifiableMap(
        key -> key,
        key -> key.equals("B") ? null : "active"
    ));

// NullPointerException
```

Nếu dữ liệu nguồn có phần tử `null`, nó cũng có thể làm mapper ném `NullPointerException` trước khi collector xây map. Cách xử lý phải theo yêu cầu nghiệp vụ: **lọc**, **thay bằng giá trị có nghĩa**, hoặc **báo lỗi**.

```java
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

Map<String, Integer> lengths = Arrays.asList("Java", null, "API")
    .stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toUnmodifiableMap(
        word -> word,
        String::length
    ));

System.out.println(lengths.size()); // 2
```

Đừng tự động đổi mọi giá trị thiếu thành chuỗi rỗng hoặc số 0 nếu những giá trị đó có ý nghĩa thật trong hệ thống. Với dữ liệu tài chính, lỗi nhập liệu hoặc khóa định danh bị thiếu thường cần được ghi nhận và xử lý minh bạch.

## 4. Không sửa đổi được khác với bất biến sâu

“Unmodifiable Map” có nghĩa là người dùng **không thể sửa các ánh xạ qua đối tượng `Map` nhận về**. Nó không có nghĩa toàn bộ đồ thị đối tượng được sao chép sâu hay những đối tượng dùng làm khóa/giá trị đều trở thành immutable.

### Những thao tác nào bị chặn?

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Integer, String> names = Stream.of("An", "Binh")
    .collect(Collectors.toUnmodifiableMap(
        String::length, word -> word
    ));

// Không hợp lệ:
// names.put(3, "New");
// names.remove(2);
// names.clear();
// names.replace(2, "Other");
```

Các thao tác sửa cấu trúc map bị chặn theo hợp đồng; phương thức sửa đổi có thể ném `UnsupportedOperationException`. Với các phương thức mặc định như `compute`, `merge` hoặc `replaceAll`, đừng dùng chúng để cập nhật map này. Không cần dựa vào việc một thao tác có hoặc không làm thay đổi dữ liệu mới ném lỗi: API cam kết kết quả **không sửa đổi được**.

### Giá trị mutable bên trong vẫn có thể thay đổi

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> roles = new ArrayList<>(Arrays.asList("READ"));

Map<String, List<String>> permissions = Stream.of("user")
    .collect(Collectors.toUnmodifiableMap(
        key -> key,
        key -> roles
    ));

// permissions.put("admin", roles); // Không được
permissions.get("user").add("WRITE"); // Được: sửa chính List mutable

System.out.println(permissions.get("user")); // [READ, WRITE]
```

Vì vậy, bản thân `Map` không thể thêm hoặc thay thế cặp khóa/giá trị, nhưng **trạng thái bên trong đối tượng `roles`** vẫn thay đổi được. Đây là một map không sửa đổi được ở cấp ánh xạ, **không** là một snapshot bất biến sâu.

Nếu muốn danh sách giá trị cũng không thể sửa qua API của nó, có thể tạo bản sao:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> roles = new ArrayList<>(Arrays.asList("READ"));
Map<String, List<String>> permissions = Stream.of("user")
    .collect(Collectors.toUnmodifiableMap(
        key -> key,
        key -> List.copyOf(roles)
    ));

roles.add("WRITE");
System.out.println(permissions.get("user")); // [READ]
```

`List.copyOf` có từ Java 10, từ chối phần tử `null`, và tạo danh sách không sửa đổi được chứa các phần tử tại thời điểm sao chép. **Các phần tử trong danh sách vẫn là tham chiếu**; nếu bản thân chúng mutable, cần chiến lược sao chép sâu hoặc thiết kế kiểu giá trị bất biến.

### Khóa mutable còn nguy hiểm hơn

Các key của `Map` phải giữ `equals`/`hashCode` ổn định khi nằm trong map. Nếu dùng đối tượng có trường tham gia `hashCode` rồi thay đổi trường đó sau khi thu thập, việc tra cứu có thể không hoạt động như mong đợi. `toUnmodifiableMap` **không tự làm khóa trở thành immutable**. Hãy ưu tiên `String`, `Integer`, enum hoặc kiểu khóa bất biến với cách định nghĩa bằng nhau rõ ràng.

## 5. Khác nhau giữa `toMap`, `toUnmodifiableMap`, `Map.copyOf` và unmodifiable view

Một số API tạo map trông giống nhau nhưng có hợp đồng khác nhau:

| API | Mục đích | Đầu ra có cho phép sửa qua Map trả về? | Tình huống |
| --- | --- | --- | --- |
| `Collectors.toMap(k, v)` | Thu thập thành map; không hứa lớp triển khai cụ thể | Không có cam kết không sửa đổi | Cần map có thể tiếp tục xử lý; kết quả phụ thuộc hợp đồng `toMap`. |
| `Collectors.toMap(k, v, merge)` | Xử lý khóa trùng khi thu thập | Không có cam kết không sửa đổi | Cần chính sách gộp và tiếp tục thao tác với kết quả. |
| `Collectors.toUnmodifiableMap(k, v)` | Thu thập trực tiếp thành map không sửa đổi được | **Không** | Các khóa dự kiến duy nhất. |
| `Collectors.toUnmodifiableMap(k, v, merge)` | Thu thập thành map không sửa đổi được có gộp khóa trùng | **Không** | Cần gộp giá trị trước khi chốt kết quả. |
| `Map.copyOf(existing)` | Tạo map không sửa đổi được từ một map hiện hữu | **Không** | Đã có map, muốn bản chụp các ánh xạ ở thời điểm tạo. |
| `Collections.unmodifiableMap(existing)` | Tạo **view** không sửa đổi được của map hiện hữu | **Không qua view** | Cần bảo vệ bề mặt API, nhưng map gốc có thể vẫn thay đổi. |

Ví dụ phân biệt **view** với **snapshot của ánh xạ**:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> source = new HashMap<>();
source.put("A", 1);

Map<String, Integer> view = Collections.unmodifiableMap(source);
Map<String, Integer> snapshot = Map.copyOf(source);

source.put("B", 2);

System.out.println(view.containsKey("B"));     // true
System.out.println(snapshot.containsKey("B")); // false
```

`Collections.unmodifiableMap(source)` phản ánh thay đổi trên **map nền** nếu có tham chiếu khác vẫn sửa nó. `Map.copyOf(source)` không phản ánh những sửa đổi ánh xạ sau thời điểm tạo, dù vẫn là **bản chụp nông** đối với các đối tượng khóa/giá trị. `toUnmodifiableMap` tạo kết quả từ chính pipeline mà không yêu cầu người gọi phải tạo map mutable rồi bọc nó trong một bước riêng.

Lưu ý: `Collectors.toMap` không hứa kiểu triển khai hoặc tính mutable của map trả về; do đó không dùng nó như một cách bảo đảm `HashMap` hay bảo đảm cho phép sửa trong mọi triển khai. Nếu cần xác định kiểu bộ chứa, `toMap` có overload nhận `mapFactory`.

## 6. Thứ tự duyệt: không suy ra từ thứ tự nguồn

`toUnmodifiableMap` **không bảo đảm thứ tự duyệt các entry**. Ngay cả khi nguồn là `List` có encounter order hoặc pipeline đã gọi `sorted()`, thứ tự in `keySet()`, `values()` hay `entrySet()` của map kết quả cũng không phải hợp đồng được phép dựa vào.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> result = Stream.of("A", "B", "C")
    .collect(Collectors.toUnmodifiableMap(
        s -> s,
        String::length
    ));

// Chỉ kiểm tra ánh xạ, không kiểm tra thứ tự in entrySet().
System.out.println(result.get("B")); // 1
```

Nếu yêu cầu là *Map có thứ tự chèn* và không muốn người dùng kết quả sửa nó, có thể dùng `LinkedHashMap` với overload bốn tham số của `toMap`, sau đó tạo một view không sửa đổi được **trên một map mới riêng tư**:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> orderedView = Stream.of("A", "B", "C")
    .collect(Collectors.collectingAndThen(
        Collectors.toMap(
            Function.identity(),
            String::length,
            (left, right) -> left,
            LinkedHashMap::new
        ),
        Collections::unmodifiableMap
    ));

System.out.println(orderedView.keySet()); // [A, B, C]
```

Trong ví dụ này, `LinkedHashMap` duyệt theo thứ tự chèn và stream có encounter order. Vì map nền được tạo mới bên trong collector và không bị lộ ra ngoài, người dùng chỉ nhận view không sửa đổi được. Nếu sau này chương trình làm lộ tham chiếu map nền hoặc giá trị mutable bên trong, cần xem lại hợp đồng bất biến mong muốn.

Không dùng `Map.copyOf(orderedMap)` nếu cần **bảo toàn iteration order**: `Map.copyOf` không hứa giữ thứ tự chèn.

## 7. Chạy song song và hàm gộp

`toUnmodifiableMap` dùng được trên stream song song. Framework có thể thu thập kết quả từng phần rồi gộp chúng thành map cuối; không nên giả định thứ tự thực thi của mapper hoặc số lần gọi merge function là cố định.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Integer, Integer> sumByRemainder = IntStream.rangeClosed(1, 1000)
    .parallel()
    .boxed()
    .collect(Collectors.toUnmodifiableMap(
        n -> n % 10,
        n -> n,
        Integer::sum
    ));

System.out.println(sumByRemainder.size()); // 10
System.out.println(
    sumByRemainder.values().stream().mapToInt(Integer::intValue).sum()
); // 500500
```

Mỗi phần tử được đưa vào nhóm dựa trên phần dư; `Integer::sum` kết hợp các giá trị cùng khóa. Tổng trong ví dụ nằm trong phạm vi `int`, nên phép cộng không tràn.

Các nguyên tắc nên giữ khi dùng overload có merge function:

1. **Chọn quy tắc gộp theo nghiệp vụ**, ví dụ cộng số lượng, chọn bản ghi có mốc thời gian lớn hơn, hay phát hiện xung đột. Không chọn `(a, b) -> a` chỉ để tránh ngoại lệ nếu nghiệp vụ không xác định bên nào cần giữ.
2. **Ưu tiên phép gộp kết hợp được** (*associative*): các nhánh song song được phép gộp theo nhóm khác nhau. Phép cộng số nguyên khi không tràn có tính kết hợp; phép trừ không phù hợp.
3. **Hạn chế trạng thái dùng chung và hiệu ứng phụ** trong mapper và merger. Không ghi vào một `HashMap` bên ngoài từ nhiều thread rồi mong collector giải quyết an toàn luồng cho map đó.
4. **Không giả định thứ tự duyệt của map kết quả**. Nếu cần thứ tự, chọn thiết kế khác theo mục 6.
5. **Đánh giá hiệu năng bằng đo đạc**. Việc gộp map ở nhiều nhánh và tạo map cuối có chi phí; `parallel()` không bảo đảm nhanh hơn tuần tự.

Đặc biệt, nếu dùng một merger không có tính kết hợp hoặc quyết định dựa vào trạng thái bên ngoài, kết quả có thể phụ thuộc cách stream được phân chia và gộp. Hãy dùng hàm thuần và xác định rõ quy tắc xử lý khi hai bản ghi có cùng khóa.

## 8. Ví dụ thực tế: lập bảng giá tra cứu chỉ đọc

Giả sử ứng dụng nhận danh sách sản phẩm, mỗi sản phẩm có mã `sku` và giá theo đơn vị nguyên nhỏ nhất của tiền. Sau khi xác thực dữ liệu, ứng dụng cần một map `sku -> price` để tra cứu, và không muốn các đoạn mã khác chỉnh sửa bảng giá.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class PriceCatalog {
    static final class Product {
        final String sku;
        final long priceInMinorUnits;

        Product(String sku, long priceInMinorUnits) {
            this.sku = sku;
            this.priceInMinorUnits = priceInMinorUnits;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
            new Product("BOOK-01", 25000L),
            new Product("PEN-02", 8000L),
            new Product("BAG-03", 90000L)
        );

        Map<String, Long> priceBySku = products.stream()
            .collect(Collectors.toUnmodifiableMap(
                product -> product.sku,
                product -> product.priceInMinorUnits
            ));

        System.out.println(priceBySku.get("PEN-02")); // 8000
        // priceBySku.put("PEN-02", 0L); // UnsupportedOperationException
    }
}
```

Trong thiết kế này, `String` và `Long` là các kiểu giá trị bất biến, nên cả **bề mặt map** lẫn các giá trị dùng để tra cứu đều tránh được bẫy object mutable ở mục 4. Nếu hai sản phẩm trùng `sku`, pipeline báo lỗi thay vì âm thầm chọn một giá: điều này có thể phù hợp khi SKU được kỳ vọng là duy nhất.

Nếu ứng dụng cho phép nhiều bản cập nhật cùng SKU, phải xác định chính sách trước khi đổi sang overload có merger. Ví dụ: lấy bản cập nhật mới nhất **theo timestamp thực**, thay vì tùy tiện chọn bản ghi xuất hiện cuối trong một pipeline có thể chạy song song.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Có khóa trùng nhưng gọi overload hai tham số | Ném `IllegalStateException`. | Bảo đảm khóa duy nhất hoặc dùng overload ba tham số với merger đúng nghiệp vụ. |
| `keyMapper` hoặc `valueMapper` trả `null` | Ném `NullPointerException`. | Xác thực, lọc hoặc chọn chính sách thay thế rõ ràng. |
| Gọi `put`, `remove`, `clear` trên map kết quả | Bị từ chối sửa đổi. | Chọn `toMap`/map mutable khi thật sự cần cập nhật. |
| Nghĩ `toUnmodifiableMap` sao chép sâu đối tượng | `List` hoặc bean mutable nằm trong value vẫn đổi trạng thái. | Dùng kiểu bất biến hoặc sao chép dữ liệu ở cấp phần tử. |
| Viết test dựa trên thứ tự `entrySet()` | Thứ tự map kết quả không được bảo đảm. | So sánh ánh xạ; dùng `LinkedHashMap` nếu cần thứ tự chèn. |
| Merger trả kết quả phụ thuộc thứ tự thread hoặc biến dùng chung | Kết quả song song khó dự đoán. | Dùng hàm thuần, kết hợp được và chính sách gộp xác định. |
| Dùng khóa mutable có `hashCode` thay đổi | Tra cứu có thể sai hoặc không còn tìm được key. | Chọn kiểu khóa bất biến. |
| Thu toàn bộ stream vô hạn vào map | Không hoàn thành; có thể cạn tài nguyên. | Giới hạn nguồn hoặc dùng phép tổng hợp hữu hạn. |

## 10. Dữ liệu rỗng, stream vô hạn và vòng đời pipeline

Với stream rỗng, `toUnmodifiableMap` tạo **map rỗng không sửa đổi được**:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> empty = Stream.<String>empty()
    .collect(Collectors.toUnmodifiableMap(
        text -> text,
        String::length
    ));

System.out.println(empty.isEmpty()); // true
```

Ngược lại, với nguồn không giới hạn như `Stream.generate`, terminal operation `collect` thường không thể hoàn tất nếu không giới hạn số phần tử:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Integer, Integer> firstHundred = IntStream.range(0, 100)
    .boxed()
    .collect(Collectors.toUnmodifiableMap(
        n -> n,
        n -> n * n
    ));

System.out.println(firstHundred.size()); // 100
```

Khi phải sinh dãy vô hạn, có thể giới hạn bằng `limit(n)` trước `collect`, hoặc dùng ngay nguồn hữu hạn như `IntStream.range` trong ví dụ. Không nên dựa vào số lượng key nhỏ để kết luận một pipeline từ nguồn vô hạn sẽ dừng: dù các phần tử tiếp theo chỉ cập nhật những key cũ, collector vẫn phải đọc hết nguồn để biết kết quả cuối.

Sau `collect`, **đối tượng stream đã bị tiêu thụ**, không thể tiếp tục gọi terminal operation trên cùng stream. Nếu nguồn gắn với tài nguyên như `Files.lines`, dùng `try-with-resources` để đóng stream; việc `collect` trả map không tự đóng mọi tài nguyên bên ngoài.

## 11. Quy trình lựa chọn collector

Khi chuyển dữ liệu thành map, nên tự kiểm tra:

1. **Map có cần sửa sau khi tạo không?** Nếu không, ưu tiên `toUnmodifiableMap` để diễn đạt hợp đồng dữ liệu đầu ra. Nếu phải thêm, xóa hoặc cập nhật, chọn map mutable với collector phù hợp.
2. **Khóa có duy nhất không?** Nếu chắc chắn duy nhất, dùng overload hai tham số. Nếu có thể trùng, xác định merger hoặc chuyển sang `groupingBy` khi cần giữ mọi phần tử trong nhóm.
3. **Có trường nào `null` không?** `toUnmodifiableMap` từ chối null key/value; cần chính sách làm sạch hoặc báo lỗi.
4. **Giá trị và khóa có mutable không?** Map không sửa đổi được ở cấp ánh xạ; muốn bất biến sâu phải kiểm soát đối tượng lồng bên trong.
5. **Có cần thứ tự duyệt không?** `toUnmodifiableMap` không hứa thứ tự; chọn `LinkedHashMap` và tạo view phù hợp nếu thứ tự là yêu cầu.
6. **Có chạy song song không?** Merger nên kết hợp được, không phụ thuộc trạng thái chia sẻ, và không dựa vào thứ tự thread.
7. **Nguồn có hữu hạn và có tài nguyên không?** Giới hạn dữ liệu trước khi thu thập và đóng nguồn I/O đúng vòng đời.

### Bài tập thực hành

**Bài 1 — Khóa duy nhất.** Từ `Stream.of("Java", "Stream", "API")`, xây `Map<String, Integer>` bằng `toUnmodifiableMap`. Thử gọi `put` và giải thích ngoại lệ. Xác nhận `get("Stream") == 6`.

**Bài 2 — Khóa trùng.** Từ `Stream.of("Java", "JUnit", "Stream")`, ánh xạ khóa là chữ cái đầu. Dự đoán lỗi ở overload hai tham số. Viết lại bằng overload ba tham số và `Integer::sum`, rồi giải thích vì sao `get("J") == 9`.

**Bài 3 — Bất biến sâu.** Dùng `List<String>` mutable làm value của map không sửa đổi được, thử `map.get(key).add(...)`. Thay value bằng `List.copyOf` và giải thích mức độ bảo vệ mới đạt được.

**Bài 4 — So sánh view và snapshot.** Tạo `HashMap` gốc, sinh `Collections.unmodifiableMap` và `Map.copyOf`, rồi thêm phần tử vào map gốc. Map nào nhìn thấy ánh xạ mới? Vì sao?

**Bài 5 — Kết quả có thứ tự.** Từ nguồn có encounter order, tạo `LinkedHashMap` bằng overload bốn tham số của `toMap` và bọc bằng `Collections.unmodifiableMap`. So sánh iteration order với `toUnmodifiableMap` và giải thích hợp đồng thứ tự của từng loại.

**Ghi nhớ:** `Collectors.toUnmodifiableMap` giúp chốt một bảng tra cứu không thể chỉnh sửa **qua API Map**, hỗ trợ chính sách gộp khóa trùng bằng overload ba tham số và từ chối key/value `null`. Tính không sửa đổi không đồng nghĩa sao chép sâu hay bảo toàn thứ tự chèn. Chọn collector theo yêu cầu về khóa, giá trị, tính mutable, thứ tự và cách xử lý song song, rồi kiểm tra đầu vào trước khi thu thập.
