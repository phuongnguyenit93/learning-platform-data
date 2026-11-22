# `Collectors.toMap` và lỗi khóa trùng trong Java Stream

`Collectors.toMap` biến các phần tử trong `Stream<T>` thành những cặp **khóa → giá trị** rồi gom vào một `Map<K,V>`. Khác với `List`, một `Map` không thể chứa hai ánh xạ riêng biệt có cùng khóa theo quy tắc so sánh khóa của map. Vì vậy, trước khi dùng `toMap`, phải trả lời: **khóa có thực sự duy nhất không, và nếu trùng thì nghiệp vụ muốn làm gì?**

Đây là kiến thức nền tảng của **Collector cơ bản** trong Java 8, vẫn áp dụng với Stream API hiện nay. Những ví dụ hoàn chỉnh bên dưới tương thích Java 8 và chạy trên JDK 17+.

## 1. `toMap` hoạt động như thế nào?

Dạng cơ bản:

~~~java
Map<K, V> result = source.stream().collect(
    Collectors.toMap(
        item -> key,     // keyMapper: lấy khóa K từ phần tử T
        item -> value    // valueMapper: lấy giá trị V từ phần tử T
    )
);
~~~

- **`keyMapper`** chạy với từng phần tử đầu vào và tạo khóa `K`, chẳng hạn mã sản phẩm, mã người dùng hoặc mã đơn hàng.
- **`valueMapper`** tạo giá trị `V` cho khóa, chẳng hạn số lượng, tên hoặc chính đối tượng thông qua `Function.identity()`.
- Collector xây dựng map; nếu **hai phần tử tạo ra khóa trùng**, dạng hai tham số không có cách xử lý nên ném `IllegalStateException`.
- `toMap` là terminal collection thông qua `collect(...)`. Khác với khai báo `filter` hoặc `map` đơn thuần, gọi `collect` làm tiêu thụ stream.

Ví dụ có khóa duy nhất:

~~~java
Map<String, Integer> lengths = Stream.of("Java", "SQL")
    .collect(Collectors.toMap(
        Function.identity(),
        String::length
    ));
// Tra cứu: lengths.get("Java") == 4; lengths.get("SQL") == 3.
~~~

Đây là đoạn **minh họa**, cần import `java.util.Map`, `java.util.function.Function`, `java.util.stream.Collectors` và `java.util.stream.Stream` nếu dùng riêng. Không suy ra thứ tự duyệt map từ dạng `toMap` hai tham số: kiểu map cụ thể và thứ tự iteration **không được API bảo đảm**.

## 2. Lỗi khóa trùng: nguyên nhân và nhận diện

Ví dụ:

~~~java
List<String> names = Arrays.asList("An", "Bình", "An");

Map<String, Integer> lengths = names.stream()
    .collect(Collectors.toMap(
        Function.identity(),
        String::length
    )); // IllegalStateException do khóa "An" xuất hiện hai lần.
~~~

Hai khóa có thể trùng vì:

1. **Dữ liệu thật sự có bản ghi cùng mã**, ví dụ hai dòng cùng `productId` trong đơn hàng.
2. **Hàm tạo khóa làm mất thông tin**, ví dụ `String::length` đưa nhiều tên khác nhau về cùng độ dài.
3. **Chuẩn hóa khóa**, ví dụ `trim().toLowerCase(Locale.ROOT)` khiến `" Java "` và `"java"` trở thành một khóa `"java"`.
4. **Quy tắc so sánh của map**, ví dụ `TreeMap` với `String.CASE_INSENSITIVE_ORDER` xem `"a"` và `"A"` tương đương như khóa.

Với map dựa trên hash như `HashMap`, hai khóa hợp lệ được xem là một khi `equals` xác định chúng bằng nhau; `hashCode` phải nhất quán với `equals`. **Hash collision đơn thuần không làm hai khóa khác nhau thành cùng khóa**: nếu có cùng hash nhưng `equals` trả `false`, map vẫn giữ được cả hai.

Với `TreeMap`, thứ tự và nhận diện khóa tương đương dựa vào comparator (`compare(a,b) == 0`), nên có thể khác `equals` nếu comparator không nhất quán với `equals`. Hãy chọn cơ chế khóa phù hợp nghiệp vụ thay vì dựa vào chi tiết triển khai.

Lưu ý: không nên kiểm tra nội dung **thông báo lỗi** của `IllegalStateException` để viết logic, vì wording có thể khác giữa các phiên bản JDK. Kiểm tra kiểu ngoại lệ và sửa chính sách xử lý khóa trùng.

## 3. Ba overload `Collectors.toMap` cần biết

### 3.1. Hai tham số: yêu cầu khóa duy nhất

~~~java
Collectors.toMap(keyMapper, valueMapper)
~~~

Dùng khi khóa **phải duy nhất** và gặp trùng là dữ liệu lỗi. `IllegalStateException` giúp phát hiện vi phạm giả định thay vì âm thầm làm mất một dòng dữ liệu.

Các trường hợp phù hợp: chuyển danh sách người dùng được bảo đảm có `userId` duy nhất thành `Map<Id, User>`; tạo index từ các mã được validate; đưa danh sách cấu hình có khóa không được trùng vào map.

Nếu dữ liệu có thể trùng theo thiết kế, cần chọn một trong các chính sách ở phần tiếp theo.

### 3.2. Ba tham số: định nghĩa cách hợp nhất giá trị

~~~java
Collectors.toMap(keyMapper, valueMapper, mergeFunction)
~~~

`mergeFunction` có kiểu `BinaryOperator<V>`, nhận **hai giá trị V cùng khóa**, không nhận trực tiếp khóa `K`. Chẳng hạn muốn cộng số lượng các dòng cùng mã:

~~~java
Map<String, Integer> quantityBySku = orderLines.stream()
    .collect(Collectors.toMap(
        OrderLine::getSku,
        OrderLine::getQuantity,
        Integer::sum
    ));
~~~

Với `SKU1` có số lượng lần lượt `2` và `3`, map sẽ giữ `SKU1 → 5`. Đó là **tổng hợp nghiệp vụ**, không phải “bỏ dòng trùng”.

Các chính sách thường gặp:

~~~java
(first, later) -> first   // giữ giá trị đã có trong thứ tự gặp ở stream tuần tự
(first, later) -> later   // lấy giá trị mới gặp ở stream tuần tự
Integer::sum             // cộng các giá trị số lượng
Integer::max             // giữ số lớn hơn
~~~

Chọn `first` hoặc `later` chỉ khi nghiệp vụ thực sự cho phép bỏ bớt dữ liệu. Nếu “mới nhất” nghĩa là thời điểm cập nhật lớn nhất, dùng comparator theo thời gian (ví dụ `BinaryOperator.maxBy(...)` với tiêu chí rõ ràng), **không đồng nhất “phần tử đến sau” với “được cập nhật mới hơn”**.

Hàm merge nên không có side effect, không sửa nguồn và có tính kết hợp (*associative*) để kết quả không phụ thuộc cách các phần được gộp trong parallel stream. Với `(a,b)->a` hoặc `(a,b)->b`, ngữ nghĩa “đầu/cuối” chỉ có ý nghĩa rõ khi nguồn có encounter order xác định; không nên giả định thứ tự của nguồn unordered như `HashSet`.

### 3.3. Bốn tham số: chỉ định kiểu map đích

~~~java
Collectors.toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

`mapFactory` cung cấp kiểu map cụ thể:

~~~java
Map<String, Integer> totals = orderLines.stream()
    .collect(Collectors.toMap(
        OrderLine::getSku,
        OrderLine::getQuantity,
        Integer::sum,
        LinkedHashMap::new
    ));
~~~

`LinkedHashMap` mặc định giữ **thứ tự chèn khóa**. Nếu nguồn là `List` và stream tuần tự có thứ tự, thứ tự iteration các khóa trong kết quả tương ứng lần đầu khóa xuất hiện. Merge giá trị của khóa đã có không làm khóa thành một mục mới trong `LinkedHashMap` chế độ insertion-order.

Muốn sắp xếp khóa theo thứ tự tự nhiên, có thể truyền `TreeMap::new` nếu khóa có khả năng so sánh; hoặc dùng supplier `() -> new TreeMap<>(comparator)` khi cần comparator riêng. Với `TreeMap`, nhớ rằng comparator còn quyết định khi nào hai khóa được coi là tương đương.

Dạng ba/bốn tham số vẫn cần chính sách merge đúng; `mapFactory` **không tự giải quyết khóa trùng**.

## 4. Chọn đúng chính sách xử lý khóa trùng

| Yêu cầu nghiệp vụ | Cách dùng | Kết quả |
| --- | --- | --- |
| Mã bắt buộc duy nhất | `toMap(keyMapper, valueMapper)` | Phát hiện khóa trùng bằng ngoại lệ. |
| Nhiều dòng cùng mã cần **cộng số lượng** | `toMap(key, quantity, Integer::sum)` | Một khóa, tổng số lượng. |
| Chỉ giữ bản ghi đầu tiên theo thứ tự đầu vào | `toMap(key, value, (a,b)->a)` | Một khóa, giá trị đầu. |
| Chỉ giữ bản ghi cuối theo thứ tự đầu vào | `toMap(key, value, (a,b)->b)` | Một khóa, giá trị cuối. |
| Cần giữ **mọi bản ghi** cùng khóa | `groupingBy(key)` / `mapping(...)` | Một khóa, danh sách các giá trị. |
| Cần duyệt khóa theo thứ tự xuất hiện | `toMap(..., LinkedHashMap::new)` | Map có thứ tự chèn khóa. |
| Cần duyệt khóa theo thứ tự so sánh | `toMap(..., TreeMap::new)` | Map có thứ tự khóa, theo comparator/natural order. |

**Đừng dùng merge “lấy cái đầu” chỉ để cho hết lỗi** nếu thông tin trùng là dữ liệu cần lưu, điều tra hoặc cảnh báo. Đó là nguy cơ làm mất dữ liệu im lặng.

### Trường hợp cần giữ tất cả giá trị: `groupingBy`

~~~java
Map<String, List<OrderLine>> linesBySku = orderLines.stream()
    .collect(Collectors.groupingBy(OrderLine::getSku));
~~~

Mỗi khóa `sku` ánh xạ đến toàn bộ các dòng có mã đó. Nếu chỉ cần danh sách số lượng:

~~~java
Map<String, List<Integer>> quantitiesBySku = orderLines.stream()
    .collect(Collectors.groupingBy(
        OrderLine::getSku,
        Collectors.mapping(
            OrderLine::getQuantity,
            Collectors.toList()
        )
    ));
~~~

Điểm khác cốt lõi: `toMap` tạo **mỗi khóa một giá trị V**; `groupingBy` có thể tạo **mỗi khóa một nhóm các phần tử/giá trị**. Khi muốn tổng mỗi nhóm, cả `groupingBy(..., summingInt(...))` và `toMap(..., Integer::sum)` đều có thể phù hợp; chọn biểu đạt rõ nhất ý định.

## 5. Ví dụ hoàn chỉnh: phát hiện trùng, gộp, giữ dòng, gom nhóm

Lưu mã sau thành tệp **`ToMapDuplicateKeyDemo.java`**. Dùng Java 8 Stream API, biên dịch/chạy được với JDK 17+.

~~~java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ToMapDuplicateKeyDemo {

    static final class OrderLine {
        private final String sku;
        private final String product;
        private final int quantity;

        OrderLine(String sku, String product, int quantity) {
            this.sku = sku;
            this.product = product;
            this.quantity = quantity;
        }

        String getSku() {
            return sku;
        }

        String getProduct() {
            return product;
        }

        int getQuantity() {
            return quantity;
        }
    }

    public static void main(String[] args) {
        List<OrderLine> lines = Arrays.asList(
                new OrderLine("SKU1", "Bút", 2),
                new OrderLine("SKU2", "Vở", 1),
                new OrderLine("SKU1", "Bút xanh", 3)
        );

        try {
            lines.stream().collect(Collectors.toMap(
                    OrderLine::getSku,
                    OrderLine::getQuantity
            ));
            System.out.println("unexpected success");
        } catch (IllegalStateException ex) {
            // Không phụ thuộc thông điệp ngoại lệ của từng JDK.
            System.out.println("duplicate = IllegalStateException");
        }

        Map<String, Integer> totals = lines.stream()
                .collect(Collectors.toMap(
                        OrderLine::getSku,
                        OrderLine::getQuantity,
                        Integer::sum,
                        LinkedHashMap::new
                ));

        Map<String, String> firstProducts = lines.stream()
                .collect(Collectors.toMap(
                        OrderLine::getSku,
                        OrderLine::getProduct,
                        (first, later) -> first,
                        LinkedHashMap::new
                ));

        Map<String, String> lastProducts = lines.stream()
                .collect(Collectors.toMap(
                        OrderLine::getSku,
                        OrderLine::getProduct,
                        (first, later) -> later,
                        LinkedHashMap::new
                ));

        Map<String, List<String>> allProducts = lines.stream()
                .collect(Collectors.groupingBy(
                        OrderLine::getSku,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                OrderLine::getProduct,
                                Collectors.toList()
                        )
                ));

        List<String> rawTags = Arrays.asList(" Java ", "java", "SQL");
        Map<String, Integer> normalizedLengths = rawTags.stream()
                .collect(Collectors.toMap(
                        tag -> tag.trim().toLowerCase(Locale.ROOT),
                        tag -> tag.trim().length(),
                        Integer::sum,
                        LinkedHashMap::new
                ));

        Map<String, Integer> unique = Stream.of("a", "bb")
                .collect(Collectors.toMap(
                        Function.identity(),
                        String::length
                ));

        System.out.println("totals = " + totals);
        System.out.println("firstProducts = " + firstProducts);
        System.out.println("lastProducts = " + lastProducts);
        System.out.println("allProducts = " + allProducts);
        System.out.println("normalizedLengths = " + normalizedLengths);
        System.out.println("unique[a] = " + unique.get("a"));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ToMapDuplicateKeyDemo.java
java ToMapDuplicateKeyDemo
~~~

**Đầu ra đúng:**

~~~text
duplicate = IllegalStateException
totals = {SKU1=5, SKU2=1}
firstProducts = {SKU1=Bút, SKU2=Vở}
lastProducts = {SKU1=Bút xanh, SKU2=Vở}
allProducts = {SKU1=[Bút, Bút xanh], SKU2=[Vở]}
normalizedLengths = {java=8, sql=3}
unique[a] = 1
~~~

Phân tích:

1. **Không truyền merge**: `SKU1` xuất hiện hai lần nên `toMap` ném `IllegalStateException`. Ví dụ chỉ in kiểu lỗi, tránh phụ thuộc thông báo của JDK.
2. **Tổng hợp**: `Integer::sum` biến hai số lượng `2` và `3` thành `5`.
3. **Giữ đầu/giữ cuối**: `firstProducts` có `"Bút"`, `lastProducts` có `"Bút xanh"`. Cả hai **bỏ một giá trị**; chỉ phù hợp nếu nghiệp vụ cho phép.
4. **Giữ đầy đủ**: `groupingBy` kết hợp `mapping` tạo danh sách hai tên sản phẩm của `SKU1`.
5. **Khóa chuẩn hóa**: `" Java "` và `"java"` đều thành `"java"`; `4 + 4 = 8`. `Locale.ROOT` giúp quy tắc đổi chữ hoa/thường không phụ thuộc locale mặc định của máy.
6. **Không dựa vào thứ tự map mặc định**: `unique.get("a")` tra theo khóa, không phụ thuộc việc collector trả về loại map nào.
7. **Thứ tự in ổn định**: Các map được in nguyên vẹn đều dùng `LinkedHashMap::new` và được tạo từ stream tuần tự có encounter order của `List`.

## 6. Vì sao không phải cứ trùng khóa là lỗi dữ liệu?

Hãy phân biệt **khóa của thực thể** và **khóa của phép tổng hợp**:

- Nếu `userId` phải duy nhất trong danh sách người dùng, bản ghi trùng `userId` có thể là lỗi cần phát hiện. Dạng `toMap` hai tham số là lựa chọn hợp lý.
- Nếu cùng `sku` xuất hiện trên nhiều dòng đơn hàng, trùng khóa là điều **bình thường**. Gộp bằng tổng số lượng hoặc nhóm các dòng mới đúng.
- Nếu dùng tên người làm khóa, hai người trùng tên không phải cùng một người. Hãy đổi sang định danh phù hợp (ví dụ mã người dùng) thay vì chọn bừa một người.
- Nếu email/username được chuẩn hóa trước khi dùng làm khóa, kiểm tra tiêu chuẩn chuẩn hóa theo chính sách hệ thống; không tự giả định mọi trường hợp khác chữ hoa, khoảng trắng hay Unicode đều là một định danh.

Trong ứng dụng thực tế, **chọn khóa đúng** thường quan trọng hơn chọn overload. Giải quyết lỗi bằng cách thay đổi `keyMapper` cho phù hợp miền dữ liệu có thể tốt hơn thêm merge để che lỗi.

## 7. Các góc cạnh cần xử lý cẩn thận

### 7.1. Giá trị `null`

`toMap` thông thường **không phải một cách đáng tin cậy để thu thập giá trị `null`**: trong các JDK hiện hành, `valueMapper` trả `null` có thể gây `NullPointerException`. Đừng biến `null` thành đối tượng `Map` một cách ngầm định.

~~~java
// Chỉ là minh họa rủi ro, không dùng cho dữ liệu có thể null:
Map<String, String> map = items.stream()
    .collect(Collectors.toMap(Item::getId, Item::getOptionalLabel));
~~~

Đoạn trên **không độc lập**: `Item` và `items` là các định nghĩa thuộc chương trình riêng. Nếu `getOptionalLabel()` có thể trả `null`, hãy quyết định nghiệp vụ: lọc bỏ các bản ghi đó; chuyển sang một giá trị mặc định có ý nghĩa; hoặc thiết kế kiểu kết quả biểu diễn sự vắng mặt, chẳng hạn `Optional` trong value mapper khi phù hợp.

Với **khóa `null`**, khả năng chấp nhận phụ thuộc loại map và implementation, không nên viết logic dựa vào việc một overload tình cờ chấp nhận null. Nên kiểm tra/chuẩn hóa khóa; với `groupingBy`, khóa `null` cũng thường bị từ chối. `Collectors.toUnmodifiableMap` (Java 10+) **cấm cả khóa và giá trị null**; nó cũng ném lỗi khi trùng khóa nếu không cung cấp merge.

### 7.2. `mergeFunction` trả `null`

Trong collector có merge, cơ chế hợp nhất dựa trên hành vi tương đương `Map.merge`: trả `null` từ hàm remapping có thể **xóa ánh xạ hiện có**. Đây không phải cách biểu diễn “lấy giá trị null cho khóa trùng”. Tránh trả null trừ khi đó là hành vi xóa đã được chủ động thiết kế và kiểm chứng.

### 7.3. Thứ tự và kiểu map trả về

Dạng `toMap(key, value)` và `toMap(key, value, merge)` không hứa trả `HashMap` hay giữ thứ tự xuất hiện. Dùng `mapFactory` khi hợp đồng đầu ra cần `LinkedHashMap`, `TreeMap` hoặc một kiểu map cụ thể. Nhớ rằng thứ tự của map và thứ tự của stream là hai vấn đề khác nhau.

### 7.4. `parallelStream()` và merge

`toMap` là collector **không concurrent**; khi parallel, các bản đồ con có thể cần hợp nhất bằng combiner, gây chi phí. Không nên đổi sang `parallelStream` chỉ vì số lượng lớn mà không đo đạc. Nếu thật sự cần collector concurrent và không cần thứ tự encounter, xem xét `Collectors.toConcurrentMap` với chính sách merge thích hợp, đồng thời chấp nhận đặc tính của `ConcurrentMap` và kiểm thử kỹ.

Một `mergeFunction` phụ thuộc trạng thái ngoài, thứ tự luồng hay mutable object có thể cho kết quả không ổn định. Đặc biệt, khái niệm “bản ghi cuối cùng” cần được định nghĩa bằng một **thuộc tính dữ liệu**, ví dụ `updatedAt`, chứ không phụ thuộc thread nào chạy sau.

### 7.5. Chi phí và tràn số

`toMap` thường tích lũy một phần tử mỗi lần; với hash map và hash tốt, thêm/tra cứu kỳ vọng gần `O(1)` mỗi phần tử, nhưng còn phụ thuộc hash, số khóa và chi phí merge. Thời gian gần `O(n)` là ước lượng thông thường, không phải cam kết tuyệt đối. `TreeMap` thường có chi phí `O(log k)` mỗi thao tác trên `k` khóa.

Nếu cộng số lượng, `Integer::sum` có thể tràn `int`. Khi tổng lớn, chọn `long`, `BigInteger` hoặc phép kiểm tra tràn phù hợp với miền dữ liệu. Việc merge trùng đúng cú pháp không tự bảo đảm tính đúng đắn nghiệp vụ.

## 8. Checklist trước khi dùng `toMap`

1. **Chọn khóa**: `keyMapper` có nhận diện duy nhất đúng thực thể, hay cố ý gom nhiều dòng vào cùng nhóm?
2. **Xác định xử lý trùng**: báo lỗi, cộng/ghép giá trị, giữ giá trị có ưu tiên, hay lưu tất cả?
3. **Chọn collector**: `toMap` cho một giá trị mỗi khóa; `groupingBy` khi cần nhóm nhiều giá trị.
4. **Kiểm tra khóa chuẩn hóa**: các phép `trim`/`lowercase`/làm tròn/ghép trường có thể gây collision mới.
5. **Kiểm tra `null`**: quyết định rõ dữ liệu thiếu khóa/giá trị phải được xử lý thế nào.
6. **Kiểm tra thứ tự**: nếu cần thứ tự chèn khóa, dùng nguồn ordered và `LinkedHashMap::new`; nếu cần thứ tự theo khóa, dùng `TreeMap` với comparator phù hợp.
7. **Kiểm tra merge**: stateless, có tính kết hợp khi cần chạy song song, không làm mất dữ liệu ngoài ý muốn.
8. **Thử dữ liệu biên**: stream rỗng, khóa trùng với giá trị bằng/khác nhau, case khác nhau, khóa null, giá trị null, tràn số, và nguồn không có thứ tự.
9. **Đừng kiểm tra text exception**: chỉ dựa vào kiểu lỗi hoặc validation nghiệp vụ rõ ràng.

**Nhớ trọng tâm:** `Collectors.toMap` hai tham số **từ chối khóa trùng** bằng `IllegalStateException`. Có khóa trùng không mặc nhiên là lỗi: giải pháp đúng là chính sách nghiệp vụ rõ ràng — **fail fast, merge đúng phép toán, chọn bản ghi theo quy tắc, hoặc `groupingBy` để giữ đủ dữ liệu**.

## Tài liệu chuẩn

- [Oracle Java API — `Collectors`: ba overload `toMap`, `groupingBy` và `toConcurrentMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java API — `Map.merge`, quy tắc null và hợp nhất](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html)
- [Oracle Java API — `LinkedHashMap` và thứ tự chèn khóa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html)
