# distinct và hợp đồng equals, hashCode trong Java Stream

## 1. Mục tiêu và vấn đề cần giải quyết

Trong Java Stream, `distinct()` là **intermediate operation** dùng để loại bỏ những phần tử được xem là **bằng nhau** theo `Object.equals(Object)`. Nhìn bề ngoài, đây là thao tác rất ngắn:

~~~java
List<String> result = List.of("A", "B", "A", "C", "B")
        .stream()
        .distinct()
        .toList();

// [A, B, C]
~~~

Nhưng kết quả thực tế với **đối tượng tự định nghĩa** phụ thuộc trực tiếp vào cách class đó triển khai **`equals(Object)` và `hashCode()`**, trạng thái có bị sửa khi Stream đang chạy hay không, và luồng dữ liệu có **encounter order** hay không. Những điểm này quyết định đúng/sai của nghiệp vụ khử trùng, chất lượng dữ liệu, chi phí bộ nhớ, khả năng xử lý song song và độ ổn định của chương trình.

Bài này thuộc nhóm **Biến đổi Stream** trong module Java 8. `distinct()` đã có từ Java 8, vẫn được hỗ trợ trong Java hiện đại; ví dụ chạy chính dùng Java 17+ để trình bày thêm `record` và `Stream.toList()` một cách ngắn gọn, rõ ràng.

Sau bài, bạn sẽ:

1. Giải thích chính xác `Stream.distinct()` xác định “trùng nhau” bằng cách nào.
2. Phân biệt **giá trị bằng nhau** (`equals`) với **cùng tham chiếu** (`==`), **hash collision**, **thứ tự sắp xếp** và **trùng theo khóa nghiệp vụ**.
3. Nêu đầy đủ hợp đồng của `equals` và `hashCode`, biết vì sao phải override hai phương thức **nhất quán**.
4. Áp dụng `distinct()` cho `String`, value object, `record`, arrays, `BigDecimal`, phần tử `null` và primitive streams.
5. Hiểu tính **stable** của `distinct()` trên ordered streams, và việc **unordered/parallel** thay đổi bảo đảm lựa chọn đại diện.
6. Tránh sửa những field tham gia `equals`/`hashCode` trong lúc pipeline đang xử lý.
7. Thiết kế cách **khử trùng theo khóa** khi đối tượng không nên định nghĩa equality theo khóa đó.
8. Chọn `distinct`, `Set`, `toMap`, `groupingBy` hoặc truy vấn dữ liệu phù hợp với yêu cầu thay vì dùng một mẫu code cho mọi trường hợp.
9. Kiểm thử kết quả và hợp đồng bằng một chương trình Java 17+ độc lập cùng stdout đáng tin cậy.

**Ý chính ngay từ đầu:** `distinct()` không có một tham số `Comparator` hay key extractor. Nếu muốn thay đổi quy tắc “hai đối tượng có bị coi là trùng không”, bạn phải sử dụng **equality semantics của chính phần tử** hoặc thiết kế một phép chuyển đổi/collector khác.

## 2. distinct() là thao tác gì?

Chữ ký API:

~~~java
Stream<T> distinct()
~~~

Theo Java Stream Javadoc, nó trả về Stream gồm các phần tử **khác nhau theo `Object.equals(Object)`**. Đây là một **stateful intermediate operation**.

- **Intermediate**: bản thân gọi `distinct()` chưa tạo ra List kết quả và chưa bảo đảm nguồn đã được duyệt. Cần một terminal operation như `toList()`, `count()` hoặc `forEach(...)`.
- **Stateful**: để biết một phần tử đã xuất hiện hay chưa, implementation cần duy trì thông tin về những giá trị đã gặp, hoặc sử dụng một chiến lược tương đương tuân thủ đặc tả.
- **Equality-based**: “trùng” phụ thuộc `equals` của phần tử, **không** tự động là cùng mã định danh nghiệp vụ, cùng tên hiển thị hay có hai chuỗi `toString()` giống nhau.
- **Ordered stream**: nếu nguồn có encounter order, thao tác loại trùng ổn định: **giữ phần tử đầu tiên theo encounter order** của mỗi nhóm bằng nhau.
- **Unordered stream**: không có bảo đảm giữ phần tử nào trong nhóm bằng nhau.

Ví dụ:

~~~java
List<String> source =
        List.of("java", "stream", "java", "Java", "stream");

List<String> unique = source.stream()
        .distinct()
        .toList();

System.out.println(unique);
~~~

Kết quả:

~~~text
[java, stream, Java]
~~~

`String.equals` phân biệt chữ hoa/thường. Do đó `"java"` và `"Java"` không bằng nhau; cả hai được giữ lại. Đừng suy luận “hai chuỗi nói cùng từ” là Java tự khử trùng không phân biệt hoa/thường.

## 3. Equals là quan hệ tương đương của đối tượng

`Object.equals(Object)` mô tả khi nào hai đối tượng được xem là bằng nhau về mặt ngữ nghĩa. Nó thường được override trong các **value objects** như `String`, `Integer`, `BigDecimal`, `LocalDate` hoặc các class của ứng dụng.

Hợp đồng `equals` trên các tham chiếu không-null gồm:

| Tính chất | Quy tắc |
| --- | --- |
| Reflexive | `x.equals(x)` phải là `true` |
| Symmetric | `x.equals(y)` và `y.equals(x)` phải có cùng kết quả |
| Transitive | Nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)` |
| Consistent | Cùng trạng thái liên quan, các lần gọi phải cho cùng kết quả |
| Null | `x.equals(null)` phải trả `false` khi `x` không-null |

Những yêu cầu này quan trọng bởi `distinct()` cần một khái niệm “các phần tử thuộc cùng nhóm tương đương”. Nếu `equals` không đối xứng hoặc không bắc cầu, logic khử trùng không còn nền tảng đáng tin cậy.

### == khác equals

~~~java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);      // false: hai object riêng
System.out.println(a.equals(b)); // true: cùng nội dung
~~~

Đối với kiểu tham chiếu, `==` so sánh **identity** (có phải cùng một object reference); `equals` so sánh **equality theo contract của class**. Nếu class không override `equals`, triển khai mặc định từ `Object` dùng identity, nên hai instance khác nhau dù có cùng fields thường **không** bị `distinct` loại như trùng.

Không dùng `System.identityHashCode` như khóa khử trùng về mặt giá trị. Nó có ngữ nghĩa khác với `hashCode` của một value object, và identity hash cũng không bảo đảm duy nhất cho mọi object.

## 4. HashCode là hợp đồng đi cùng equals

`hashCode()` trả một số nguyên `int` được thiết kế để hỗ trợ các cấu trúc hash-based, ví dụ `HashMap` và `HashSet`.

Hợp đồng then chốt:

> Nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` **phải** là `true`.

Chiều ngược lại **không đúng**: hai đối tượng có cùng hash code **không nhất thiết bằng nhau**.

Ngoài ra, `hashCode` phải có giá trị ổn định qua các lần gọi khi thông tin dùng cho `equals` không bị thay đổi trong thời gian ứng dụng đang chạy.

### Vì sao distinct liên quan hashCode nếu Javadoc nói equals?

Javadoc định nghĩa **kết quả đúng dựa trên `equals`**. Còn một triển khai có thể dùng những cấu trúc như bảng hash để tra cứu hiệu quả các phần tử đã xuất hiện. Nếu class phá vỡ hợp đồng `equals/hashCode`, kết quả thực tế của những thuật toán và collections phụ thuộc hashing có thể sai, dù các đối tượng lẽ ra phải được coi là trùng.

Vì vậy, **luôn override `hashCode` cùng `equals`** khi định nghĩa value equality. Không dựa vào việc một phiên bản JDK tình cờ hoạt động như mong muốn với class có hash contract sai.

### Hash collision là hợp lệ

Hai String `"Aa"` và `"BB"` có cùng `hashCode` trong Java, nhưng:

~~~java
"Aa".equals("BB") // false
~~~

Nên:

~~~java
long count = Stream.of("Aa", "BB")
        .distinct()
        .count();

// count == 2
~~~

Đây là minh họa quan trọng: `distinct()` không đơn giản là “chỉ giữ một object cho mỗi giá trị hash”. Nếu có collision, các giá trị **không bằng nhau** vẫn cần được giữ.

## 5. Đối tượng tự định nghĩa: lỗi khi chỉ override một phương thức

Giả sử có class:

~~~java
final class Customer {
    private final long id;
    private final String name;

    Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

Nếu bạn tạo:

~~~java
Customer a = new Customer(7, "Lan");
Customer b = new Customer(7, "Lan");
~~~

và `Customer` không override `equals`, hai instances thường không bằng nhau vì chỉ có identity equality mặc định. `Stream.of(a,b).distinct()` sẽ giữ cả hai, dù nghiệp vụ có thể coi cùng `id` là cùng khách hàng.

### Chỉ override equals nhưng quên hashCode

~~~java
@Override
public boolean equals(Object other) {
    return other instanceof Customer c && id == c.id;
}

// Thiếu hashCode()
~~~

Đây là **mã minh họa một thiết kế sai**: hai customers cùng `id` có `equals == true`, nhưng vẫn có thể nhận các hash codes khác nhau từ `Object.hashCode()`. Vi phạm hợp đồng có thể khiến hash-based algorithms không nhận ra dữ liệu trùng.

### Cách đúng khi identity nghiệp vụ là id

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof Customer c && id == c.id);
}

@Override
public int hashCode() {
    return Long.hashCode(id);
}
~~~

Khi đó:
- Hai customers có cùng `id` bằng nhau.
- Hai customers có cùng `id` có cùng hash code.
- `name` là thuộc tính hiển thị không tham gia identity theo **quyết định thiết kế đã chọn**.

**Cảnh báo:** Không có quy tắc tổng quát “mọi entity phải chỉ dùng id trong equals”. Điều đó còn tùy id có được gán trước khi lưu hay không, uniqueness, vòng đời, subtype/proxy, persistence framework và hợp đồng domain. Nếu nhiều instance có id mặc định `0`, việc coi chúng bằng nhau có thể là lỗi nghiệp vụ nghiêm trọng. Hãy xác định identity thật trước khi chọn các fields tham gia equality.

## 6. Chương trình Java 17+ minh họa Customer đúng hợp đồng

Ví dụ được biên dịch/chạy độc lập ở phần sau định nghĩa:

~~~java
static final class Customer {
    private final long id;
    private final String name;

    Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Customer c && id == c.id);
    }

    @Override
    public int hashCode() {
        return Long.hashCode(id);
    }

    @Override
    public String toString() {
        return name + "#" + id;
    }
}
~~~

Ở một ordered source:

~~~java
List<Customer> customers = List.of(
        new Customer(7, "Lan"),
        new Customer(2, "Minh"),
        new Customer(7, "Lan-new"),
        new Customer(3, "Hoa"),
        new Customer(2, "Minh-new"));

List<Customer> unique = customers.stream()
        .distinct()
        .toList();
~~~

Kết quả hiển thị:

~~~text
[Lan#7, Minh#2, Hoa#3]
~~~

Hai khách hàng `Lan` và `Lan-new` cùng `id == 7` nên được coi là trùng. Ordered `distinct` **giữ đối tượng xuất hiện đầu tiên**: `Lan#7`.

**Đây là một khác biệt quan trọng giữa equality và lựa chọn đại diện.** Nếu nghiệp vụ muốn “giữ bản cập nhật mới nhất”, `distinct()` trên một List xếp cũ trước sẽ **không** tự biết điều đó. Bạn phải sắp xếp theo timestamp có hợp đồng rõ, hoặc dùng collector chọn latest record qua merge function.

## 7. Class bất biến: lợi thế với distinct và hashing

Hợp đồng hashing yêu cầu giá trị liên quan equality giữ ổn định khi đối tượng được sử dụng trong cấu trúc hash-based. Nếu một object đổi `id` sau khi đã được hash, các collection/algorithms có thể không tìm thấy nó theo cách mong đợi.

**Nên ưu tiên các fields tham gia `equals/hashCode` là bất biến** nếu đó là value object dùng trong set, map, stream deduplication hay caching.

Ví dụ rủi ro:

~~~java
class MutableKey {
    int id;

    MutableKey(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof MutableKey k && id == k.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}
~~~

Nếu sửa `id` khi đối tượng đang nằm trong `HashSet`, `HashMap` hoặc pipeline `distinct` đang xử lý, hành vi có thể khác mong đợi. Điều này không cần race condition mới có vấn đề: ngay cả ở một thread, đổi key sau khi nó được đưa vào hash table cũng có thể làm lookup bị sai.

### Không mutate key trong map/peek khi distinct phía sau

~~~java
// Thiết kế không an toàn về ý nghĩa:
source.stream()
        .peek(item -> item.setId(computeNewId(item)))
        .distinct()
        .toList();
~~~

Dù code có thể chạy, nó đã trộn thay đổi trạng thái nguồn với việc xác định equality. Còn nếu code thực thi song song, nguy cơ data race và thiếu nhất quán càng lớn.

Cách an toàn hơn là **tạo một value object mới đã có identity ổn định**:

~~~java
List<KeySnapshot> keys = source.stream()
        .map(item -> new KeySnapshot(item.getId()))
        .distinct()
        .toList();
~~~

Với:

~~~java
record KeySnapshot(long id) {
}
~~~

Đây là các đoạn minh họa cần `source` và class tương ứng. Lưu ý `record` được chuẩn hóa từ Java 16. Nó hữu ích cho value semantics nhưng không biến một field tham chiếu mutable nằm bên trong record thành bất biến sâu.

## 8. Java record: equals/hashCode được sinh theo components

Với một record:

~~~java
record Point(int x, int y) {
}
~~~

Java tạo ra các phương thức `equals` và `hashCode` dựa trên **record components** theo hợp đồng của record. Vì vậy:

~~~java
List<Point> points = List.of(
        new Point(1, 2),
        new Point(1, 2),
        new Point(1, 3));

List<Point> unique = points.stream()
        .distinct()
        .toList();
~~~

Kết quả:

~~~text
[Point[x=1, y=2], Point[x=1, y=3]]
~~~

Hai `Point(1,2)` có cùng giá trị components nên một bản bị loại. `Point(1,3)` khác ở `y`, được giữ.

### Record không tự định nghĩa equality nghiệp vụ

Giả sử:

~~~java
record CustomerSnapshot(long id, String name) {
}
~~~

Hai snapshots có cùng `id` nhưng `name` khác nhau **không tự bằng nhau**, vì record equality mặc định xét **cả hai components**.

Vì vậy:
- Dùng record khi **giá trị của toàn bộ components** phù hợp với semantics equality bạn cần.
- Nếu nghiệp vụ chỉ cần khử trùng theo `id`, cân nhắc ánh xạ sang key hoặc collector theo khóa.
- Không thay đổi logic equals/hashCode của một record chỉ để khiến một pipeline bất kỳ cho kết quả mong muốn nếu điều đó làm sai ngữ nghĩa của value type ở các nơi khác.

### Record chứa mảng

Một record như `record Payload(byte[] data) {}` vẫn có component tham chiếu tới mảng. Mặc định, equality của component kiểu mảng dựa trên equality của mảng, mà mảng Java không override `Object.equals` theo nội dung.

Hai `byte[]` có cùng bytes nhưng là hai arrays khác nhau thường không bằng nhau theo `equals`, và hai record chứa chúng cũng không tự được coi bằng nhau theo nội dung. Nếu cần **deep/content equality**, thiết kế một wrapper bất biến với `Arrays.equals` và `Arrays.hashCode` tương ứng, hoặc tạo một canonical value representation.

## 9. Array và distinct: cùng nội dung chưa chắc bằng nhau

Xét:

~~~java
int[] first = {1, 2};
int[] second = {1, 2};
~~~

`Arrays.equals(first, second)` trả `true` vì các phần tử nguyên thủy tương ứng bằng nhau. Nhưng:

~~~java
first.equals(second) // false: hai mảng khác identity
~~~

Do đó:

~~~java
long count = Stream.of(first, second)
        .distinct()
        .count();

// count == 2
~~~

**`distinct()` không gọi `Arrays.equals` hộ bạn**; nó dùng equality semantics của các phần tử trong Stream. Nếu Stream chứa `int[]`, mỗi phần tử là **một array reference**, không phải từng số nguyên bên trong.

### Khi muốn loại trùng các giá trị trong mảng primitive

~~~java
int[] values = {1, 2, 1, 3, 2};

int[] unique = Arrays.stream(values)
        .distinct()
        .toArray();

// [1, 2, 3]
~~~

Ở đây `Arrays.stream(int[])` trả `IntStream` của **từng số nguyên**, nên semantics khác hoàn toàn với `Stream.of(intArray)`, là stream có **một phần tử** kiểu `int[]` trong trường hợp truyền một mảng kiểu primitive.

Đừng nhầm:
- `Stream.of(first, second)`: hai phần tử là hai đối tượng `int[]`.
- `Arrays.stream(first)`: các phần tử là `int` trong mảng.
- `IntStream.of(1,2,1)`: các phần tử là `int`.

Nếu cần dedup **mảng con** theo nội dung, hãy dùng một wrapper key có equality/hash code theo contents hoặc chuyển sang biểu diễn immutable có semantics phù hợp, không dựa vào identity của mảng.

## 10. BigDecimal: bằng nhau về số học khác bằng nhau theo equals

`java.math.BigDecimal` là một ví dụ kinh điển:

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));   // false
System.out.println(a.compareTo(b)); // 0
~~~

`BigDecimal.equals` xét cả giá trị và **scale**, còn `compareTo` so sánh theo thứ tự số học có thể trả `0` dù scale khác nhau. Vì vậy:

~~~java
long count = Stream.of(a, b)
        .distinct()
        .count();

// 2
~~~

**`distinct()` theo equals, không theo compareTo hay Comparator.**

### Khi nghiệp vụ muốn gộp BigDecimal có giá trị số học bằng nhau

Có thể chuẩn hóa bằng `stripTrailingZeros()` trong những ngữ cảnh phù hợp:

~~~java
List<BigDecimal> normalized = Stream.of(
        new BigDecimal("1.0"),
        new BigDecimal("1.00"),
        new BigDecimal("2.0"))
        .map(BigDecimal::stripTrailingZeros)
        .distinct()
        .toList();
~~~

Trong kết quả này, các giá trị `1.0` và `1.00` có thể trở thành cùng một dạng chuẩn để equals nhận ra. Nhưng:

- `stripTrailingZeros()` **có thể thay đổi scale và cách biểu diễn dạng scientific notation** của một số giá trị.
- Khi dữ liệu tiền tệ cần bảo toàn số chữ số thập phân cho hiển thị, accounting hoặc dữ liệu gốc, normalization phải dựa trên yêu cầu nghiệp vụ.
- Đừng tự động chuẩn hóa mọi BigDecimal rồi nghĩ đó là thao tác “không làm mất ý nghĩa”; scale có thể là dữ liệu quan trọng.

Một `TreeSet<BigDecimal>` dùng ordering theo `compareTo` sẽ có semantics membership khác `HashSet<BigDecimal>` dựa theo `equals/hashCode`. Đó là lý do một collection/sorted structure không tự là phiên bản thay thế tương đương cho `Stream.distinct()`.

## 11. Null trong Stream và distinct

`Stream` có thể chứa phần tử `null` nếu nguồn tạo ra như vậy (không phải mọi factory đều cho phép null).

~~~java
List<String> result = Stream.of(
        "A", null, "A", null, "B")
        .distinct()
        .toList();

// [A, null, B]
~~~

Hai occurrences `null` được xem là cùng một giá trị khi khử trùng, nên chỉ giữ một `null`. Đây là một hành vi hợp lệ với Stream của các reference elements có null.

**Đừng dùng `List.of("A", null)` để tạo nguồn**, vì `List.of(...)` không cho phép null và sẽ ném `NullPointerException`. `Stream.toList()` có semantics khác `List.of()`: nó tạo List unmodifiable nhưng **có thể chứa null** khi nguồn chứa null.

Nếu nghiệp vụ muốn bỏ null:

~~~java
List<String> result = Stream.of(
        "A", null, "A", null, "B")
        .filter(Objects::nonNull)
        .distinct()
        .toList();

// [A, B]
~~~

Nên xác định rõ liệu null là “một giá trị cần giữ”, “dữ liệu không hợp lệ” hay “placeholder cần bỏ”. `distinct()` không phải validation, nên không tự loại bỏ null.

## 12. Các primitive streams và distinct

Ba primitive Stream interfaces có phương thức `distinct()`:

- `IntStream.distinct()`: khử trùng các `int`.
- `LongStream.distinct()`: khử trùng các `long`.
- `DoubleStream.distinct()`: khử trùng các `double` theo các quy tắc equality của `Double.compare`/`Double` được đặc tả.

Ví dụ:

~~~java
int[] indexes = IntStream.of(4, 2, 4, 1, 2)
        .distinct()
        .toArray();

// [4, 2, 1]
~~~

Primitive streams tránh phải boxing thành `Integer`/`Long`/`Double` chỉ để thực hiện một số phép tính trên dữ liệu số. Khi cần `List<Integer>`, có thể `boxed().toList()` ở Java 16+.

### DoubleStream: NaN và signed zero

Đây là tình huống cần kiểm tra Javadoc thay vì dùng trực giác toán học:

- Các giá trị `NaN` được coi là bằng nhau cho mục đích `DoubleStream.distinct()`.
- `+0.0` và `-0.0` được xem là **khác nhau** theo `Double.compare`, nên có thể cùng tồn tại trong kết quả distinct.
- Cùng một bài toán số học, phép `==` trên primitive double có semantics khác với `Double.equals` hoặc `Double.compare` tại NaN và signed zero.

Ví dụ:

~~~java
double[] result = DoubleStream.of(
        Double.NaN, Double.NaN, +0.0, -0.0)
        .distinct()
        .toArray();
~~~

Đừng test bằng cách chỉ dùng `==` để so NaN hoặc hai signed zeros. Khi cần khử trùng theo một **ngưỡng sai số** epsilon, đó là một quy tắc domain-specific: `distinct()` không nhận epsilon. Hãy xây dựng chiến lược phân nhóm/canonicalization rõ ràng, tính đến rounding, overflow, NaN, infinity và biên bucket.

## 13. Encounter order: phần tử nào được giữ lại?

Với một **ordered stream**, Javadoc quy định stable distinct: nếu nhiều phần tử bằng nhau, **phần tử xuất hiện đầu tiên theo encounter order được giữ**.

Ví dụ:

~~~java
List<Customer> customers = List.of(
        new Customer(7, "Lan"),
        new Customer(7, "Lan-new"));

List<Customer> unique = customers.stream()
        .distinct()
        .toList();
~~~

Kết quả có một `Customer` với `name == "Lan"` theo equality `id`. Vì input là `List` có encounter order và pipeline không bỏ ordering constraint, first representative được giữ.

### Phân biệt encounter order với thứ tự chạy callbacks

Ngay cả khi một ordered parallel stream cho kết quả giữ order, những thao tác upstream có thể được thực thi trên nhiều threads và không theo thứ tự vật lý bạn nhìn thấy trong logs. Không dùng `peek(System.out::println)` để khẳng định phần tử “được xử lý đầu tiên” theo thời gian chính là phần tử có encounter order đầu tiên.

**Bảo đảm của `distinct` là lựa chọn đại diện/kết quả**, không phải lịch thực thi của từng lambda.

### Nguồn unordered

Với `HashSet` hoặc một stream đã gọi `unordered()`, không có encounter order được bảo đảm tương đương với List. Vì vậy nếu bạn dùng `distinct`, không được yêu cầu một đại diện đầu tiên cụ thể cho mỗi nhóm bằng nhau.

Một số nguồn `Set` vốn đã không có phần tử trùng theo equality contract của set, nên `distinct()` trên chúng thường không mang nhiều giá trị semantic. Nhưng vẫn cần hiểu set implementation, thứ tự và kiểu equality trước khi suy ra kết quả.

## 14. Parallel distinct và chi phí của sự ổn định

`distinct()` là stateful. Javadoc ghi rõ việc **giữ stability trên ordered parallel streams** có thể khá tốn kém, vì cần barrier/buffering đáng kể.

~~~java
List<Customer> result = customers.parallelStream()
        .distinct()
        .toList();
~~~

Trong trường hợp source là `List` có encounter order và equality contract hợp lệ, kết quả vẫn phải tôn trọng ordered stable distinct. Nhưng đánh đổi có thể là:
- Tăng bộ nhớ trung gian.
- Tăng chi phí phối hợp/synchronization.
- Tăng latency với dữ liệu lớn hoặc nhiều phần tử khác nhau.
- Không nhanh hơn sequential dù bạn đã gọi `parallelStream()`.

### Khi nào unordered có thể giúp?

Nếu nghiệp vụ **không cần đại diện đầu tiên hoặc thứ tự kết quả**, bạn có thể cân nhắc:

~~~java
List<Customer> result = customers.parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

Điều này giải phóng ràng buộc encounter order, có thể cho phép implementation tối ưu hơn. Tuy nhiên:
- Kết quả **không bảo đảm giữ bản `Customer` đầu tiên** trong một nhóm bằng nhau.
- Thứ tự đầu ra không được bảo đảm theo List source.
- Bạn phải thật sự chấp nhận semantics đó.
- Không có bảo đảm `unordered()` luôn nhanh hơn; hãy benchmark workload thực tế.

Khi cần ổn định, Javadoc còn gợi ý cân nhắc `sequential()` nếu ordered parallel distinct gây vấn đề hiệu năng/bộ nhớ. Đừng thêm `parallel()` chỉ vì nhìn thấy số lượng phần tử lớn; hãy cân nhắc chi phí stage và đặc tính nguồn.

## 15. distinct không sắp xếp dữ liệu

`distinct()` và `sorted()` khác nhau:

~~~java
List<Integer> values = List.of(5, 1, 5, 3, 1);

List<Integer> unique = values.stream()
        .distinct()
        .toList();

// [5, 1, 3]
~~~

Nếu muốn kết quả được sắp xếp:

~~~java
List<Integer> sortedUnique = values.stream()
        .distinct()
        .sorted()
        .toList();

// [1, 3, 5]
~~~

`distinct` chỉ loại trùng. `sorted` thay đổi/áp đặt thứ tự. Với ordered stream:
- `distinct` ổn định về lựa chọn đại diện.
- `sorted()` theo natural order (hoặc `sorted(comparator)` khi cần).
- Không có một quá trình “sort theo comparator rồi distinct dùng comparator” tự động chỉ vì hai operations đặt cạnh nhau.

Nếu dùng `sorted(comparator).distinct()`, **comparator equality không thay thế Object.equals**. Hai phần tử mà comparator trả `0` nhưng `equals` là `false` vẫn có thể cùng xuất hiện sau `distinct`.

## 16. distinct theo khóa nghiệp vụ: vì sao không có distinctByKey chuẩn?

Ví dụ hai sự kiện:

~~~java
record Event(String eventId, String type, long timestamp) {
}
~~~

Giả sử bạn muốn chỉ giữ **một event cho mỗi `eventId`**, bất kể `type` và `timestamp`. Nhưng record equality mặc định dùng mọi components, nên:

~~~java
new Event("e1", "created", 100)
new Event("e1", "updated", 200)
~~~

là hai record **không bằng nhau** và `distinct()` không loại một bản.

**Java Stream API không có overload chuẩn `distinct(keyExtractor)` hoặc `distinct(comparator)`.** Bạn phải chỉ rõ loại trùng theo khóa là một yêu cầu khác với equality toàn đối tượng.

### Cách 1: chỉ cần danh sách khóa duy nhất

~~~java
List<String> ids = events.stream()
        .map(Event::eventId)
        .distinct()
        .toList();
~~~

Cách này đưa các phần tử thành String keys, nên `String.equals/hashCode` được dùng. Nhược điểm: **mất object Event đầy đủ**, chỉ còn key.

### Cách 2: giữ một object cho mỗi key với toMap

Nếu muốn giữ event đầy đủ và **bản đầu tiên theo encounter order** trên sequential ordered stream:

~~~java
Map<String, Event> firstById = events.stream()
        .collect(Collectors.toMap(
                Event::eventId,
                Function.identity(),
                (first, ignored) -> first,
                LinkedHashMap::new));

List<Event> firstEvents =
        new ArrayList<>(firstById.values());
~~~

Các phần tử được thu thập trong `LinkedHashMap` theo thứ tự insert của unique keys trong quá trình tuần tự, còn merge function giữ giá trị đầu cho mỗi key. Đây là cách rõ ràng khi source **ordered**, collector được dùng **sequential**, key non-null và semantics “first per key” là mong muốn.

**Đừng tự động suy điều đó cho mọi parallel collector** nếu yêu cầu là lựa chọn đại diện deterministic theo encounter order: cần xác định rõ collector semantics, ordering và kiểm thử trên workload; nếu bảo đảm first representative là thiết yếu, xử lý tuần tự hoặc một thuật toán selection có ordering rõ ràng thường dễ lý giải hơn.

### Cách 3: chọn bản cập nhật mới nhất

Có thể dùng merge function so sánh timestamp:

~~~java
Map<String, Event> latestById = events.stream()
        .collect(Collectors.toMap(
                Event::eventId,
                Function.identity(),
                (a, b) -> a.timestamp() >= b.timestamp() ? a : b));
~~~

Ở đây `>=` tạo tie policy “giữ a khi bằng timestamp”, nhưng cần cân nhắc **associativity/determinism** khi input chứa timestamp trùng và chạy parallel. Với các bản ghi bằng timestamp nhưng khác nội dung, lựa chọn tie break không được mô tả rõ có thể không ổn định khi merge thứ tự khác nhau. Nếu business rule cần chính xác, thêm một key phụ để xác định tổng thứ tự.

Bài học: **dedup theo key là một phép aggregate/selection có contract riêng**, không chỉ một lựa chọn cú pháp thay cho `distinct()`.

## 17. Case-insensitive distinct mà vẫn giữ cách viết gốc

Vì `String.equals` phân biệt hoa/thường:

~~~java
List<String> values =
        List.of("Java", "java", "Stream", "STREAM", "Map");
~~~

`values.stream().distinct()` không coi `"Java"` và `"java"` là trùng. Nếu bạn **chấp nhận mất chữ hoa gốc**, cách dễ nhất:

~~~java
List<String> normalized = values.stream()
        .map(s -> s.toLowerCase(Locale.ROOT))
        .distinct()
        .toList();

// [java, stream, map]
~~~

Nếu muốn **giữ cách viết xuất hiện đầu tiên** theo chuỗi sau chuẩn hóa lowercase (trên sequential ordered input):

~~~java
Map<String, String> byKey = values.stream()
        .collect(Collectors.toMap(
                s -> s.toLowerCase(Locale.ROOT),
                Function.identity(),
                (first, ignored) -> first,
                LinkedHashMap::new));

List<String> originalCase =
        new ArrayList<>(byKey.values());

// [Java, Stream, Map]
~~~

Ở đây:
- `toLowerCase(Locale.ROOT)` tạo key nhằm tránh phụ thuộc locale mặc định của máy cho một policy normalization đơn giản.
- `Function.identity()` giữ original value làm value của Map.
- `(first, ignored) -> first` giữ value đã có.
- `LinkedHashMap` giữ thứ tự insert của các unique keys khi collector xử lý sequential.

**Case-insensitive không hoàn toàn đồng nghĩa Unicode canonical equivalence hoặc mọi quy tắc so sánh ngôn ngữ.** Nếu hệ thống cần so sánh Unicode phức tạp, normalization như NFC/NFKC, case folding chuẩn hoặc locale-sensitive collation, hãy thiết kế và test riêng. `Locale.ROOT` chỉ là một lựa chọn cụ thể, không phải thuật toán nhận diện “cùng một tên người” toàn cầu.

### Tránh thủ thuật distinctByKey dùng shared mutable Set

Một đoạn thường được chia sẻ:

~~~java
Set<Object> seen = ConcurrentHashMap.newKeySet();

stream.filter(value -> seen.add(keyExtractor.apply(value)));
~~~

Kỹ thuật này có **side effect/stateful predicate**. Ngay cả khi Set thread-safe, thứ tự phần tử nào được chọn trong parallel pipeline không được bảo đảm theo nhu cầu nghiệp vụ. Nó cũng trộn business selection với state bên ngoài pipeline.

**Ưu tiên collector hoặc thuật toán được thiết kế rõ cho chọn đại diện theo key.** Nếu bắt buộc dùng một cơ chế stateful cụ thể, cần định nghĩa concurrency, ordering, lifetime và error semantics riêng; không gọi đó là `Stream.distinct()` chuẩn.

## 18. Hash collisions, hiệu năng và memory

`distinct()` phải nhớ điều gì đã gặp hoặc một cấu trúc tương đương để không trả lại duplicate. Vì là stateful operation, nó có thể tốn bộ nhớ theo **số giá trị khác nhau** đang được xử lý.

Điều này đặc biệt cần cân nhắc khi:

- Nguồn rất lớn, hầu hết phần tử đều khác nhau.
- Object nặng hoặc có tham chiếu tới đồ thị dữ liệu lớn.
- `equals`/`hashCode` tốn chi phí tính toán.
- Hash codes phân bố kém làm tăng collisions.
- Pipeline ordered parallel cần giữ stability.
- Nguồn vô hạn hoặc rất dài và không có biện pháp dừng/bound.

### Không tối ưu bằng cách phá hợp đồng equality

Một `hashCode()` đơn giản như:

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

có thể vẫn **đúng về mặt hợp đồng** nếu các đối tượng bằng nhau cùng hash, nhưng gần như không phân tán key nào, có thể làm hiệu năng hashing kém.

Ngược lại, một `hashCode` phân tán rất tốt nhưng **không nhất quán với equals** sẽ gây lỗi logic. **Độ đúng của contract luôn quan trọng hơn việc giảm collisions**, sau đó mới cải thiện phân bố hash.

### Không dựa vào một thuật toán triển khai duy nhất

Javadoc `Stream.distinct()` mô tả **ngữ nghĩa**, không bắt buộc mọi JDK sử dụng chính xác cùng một kiểu Set, số lần gọi equals/hashCode hoặc cùng profile bộ nhớ. Vì vậy:
- Không test số lần `equals()` hay `hashCode()` đã được gọi như một yêu cầu của `distinct`.
- Không log side effects trong `equals` rồi suy ra thứ tự duyệt.
- Không giả định implementation luôn có độ phức tạp một con số cố định trong mọi trường hợp.
- Đánh giá profile/benchmark khi dữ liệu thật đủ lớn và có ràng buộc thời gian/bộ nhớ.

## 19. Bài toán Stream vô hạn và distinct

Với nguồn vô hạn, `distinct()` có thể duy trì trạng thái ngày càng lớn nếu có vô số giá trị khác nhau. Ngay cả khi kết hợp `limit(n)`, thứ tự operations cũng rất quan trọng.

~~~java
Stream.iterate(0, n -> n + 1)
        .distinct()
        .limit(10)
        .toList();
~~~

Nguồn tạo nhiều giá trị khác nhau, nên pipeline có thể lấy mười giá trị đầu rồi dừng nhờ `limit`.

Nhưng:

~~~java
Stream.generate(() -> 1)
        .distinct()
        .limit(2)
        .toList();
~~~

Nguồn chỉ tạo một giá trị độc nhất là `1`, nên `distinct()` không bao giờ cung cấp đủ **hai phần tử khác nhau** cho downstream `limit(2)`. Với nguồn vô hạn này, terminal có thể không kết thúc.

**Không dùng đoạn thứ hai trong chương trình demo chạy chính**, vì nó không có điều kiện dừng hữu hạn. Nó là ví dụ phân tích tính kết thúc.

Nếu nguồn có thể vô hạn, cần chứng minh pipeline có thể tạo đủ unique values theo yêu cầu, hoặc đặt giới hạn/timing ở tầng nguồn/thuật toán. `distinct` không tự bảo đảm một stream vô hạn sẽ trở nên hữu hạn.

## 20. Lỗi thường gặp khi thiết kế equals/hashCode

| Vấn đề | Hệ quả | Gợi ý |
| --- | --- | --- |
| Chưa override equals cho value object | Khác instances vẫn không được loại trùng | Định nghĩa value equality khi phù hợp |
| Override equals nhưng quên hashCode | Phá hợp đồng hashing, có thể không khử trùng đúng | Override cả hai nhất quán |
| HashCode dùng field không có trong equals, gây khác hash với object bằng nhau | Vi phạm hợp đồng | Tính hash trên các thành phần bảo đảm equality |
| Đổi field identity sau khi đưa object vào hash-based structure | Lookup/khử trùng không đáng tin | Dùng immutable keys |
| equals không đối xứng vì so sánh superclass/subclass sai | Quan hệ equality hỏng | Thiết kế type policy nhất quán |
| equals phụ thuộc thời gian, external state hoặc random | Không consistent | Chỉ dùng state ổn định |
| Dùng `toString()` như key khử trùng | Format hiển thị không phải equality contract | Dùng id/key/value semantics rõ |
| Dùng `==` để mong distinct nhận biết cùng nội dung | Identity khác equality | Tìm hiểu equals của type |
| Dùng hashCode như id duy nhất | Hash collision tồn tại | Xét equals sau hashing |
| Dùng Lombok/code generator không kiểm tra những field tham gia | Có thể chọn sai business identity | Review generated equals/hashCode |
| Entity chưa có id mà equals chỉ dùng id mặc định | Có thể gộp các entities mới | Quyết định identity lifecycle |
| Record chứa mutable array và mong deep equals | Default equality có thể dựa identity của array | Wrapper hoặc explicit content equality |

### Vấn đề inheritance

Khi thiết kế `equals` cho những class có kế thừa, việc sử dụng `instanceof` hoặc `getClass()` có thể tạo semantics khác nhau. Không có một đáp án phù hợp cho mọi domain, nhưng phải giữ được symmetry/transitivity và không khiến subclass “mở rộng” equality theo cách phá hợp đồng superclass.

Một cách giảm phức tạp là dùng **final value classes** hoặc `record` khi phù hợp, để tránh các tình huống subtype equality khó dự đoán. Khi dùng proxy của ORM, cần đọc hợp đồng của framework thay vì áp một mẫu `equals` chung mà không xét proxy/lifecycle.

## 21. Chương trình Java 17+ đầy đủ và có đầu ra xác định

Tạo file **`DistinctEqualityDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class DistinctEqualityDemo {

    record Point(int x, int y) {
    }

    static final class Customer {
        private final long id;
        private final String name;

        Customer(long id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Customer c && id == c.id);
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }

        @Override
        public String toString() {
            return name + "#" + id;
        }
    }

    public static void main(String[] args) {
        List<String> words =
                List.of("java", "java", "stream", "Java", "stream");

        System.out.println("strings=" +
                words.stream().distinct().toList());

        List<Customer> customers = List.of(
                new Customer(7, "Lan"),
                new Customer(2, "Minh"),
                new Customer(7, "Lan-new"),
                new Customer(3, "Hoa"),
                new Customer(2, "Minh-new"));

        System.out.println("customers=" +
                customers.stream().distinct().toList());

        List<Point> points = List.of(
                new Point(1, 2),
                new Point(1, 2),
                new Point(1, 3));

        System.out.println("records=" +
                points.stream().distinct().toList());

        System.out.println("ints=" +
                IntStream.of(4, 2, 4, 1, 2)
                        .distinct()
                        .boxed()
                        .toList());

        System.out.println("with-null=" +
                Stream.of("A", null, "A", null, "B")
                        .distinct()
                        .toList());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("decimal.equals=" + a.equals(b));
        System.out.println("decimal.compareTo=" + a.compareTo(b));
        System.out.println("decimal.distinct=" +
                Stream.of(a, b).distinct().count());

        int[] x = {1, 2};
        int[] y = {1, 2};

        System.out.println("arrays.equals=" +
                Arrays.equals(x, y));

        System.out.println("arrays.distinct=" +
                Stream.of(x, y).distinct().count());

        List<String> input =
                List.of("Java", "java", "Stream", "STREAM", "Map");

        Map<String, String> byKey = input.stream()
                .collect(Collectors.toMap(
                        s -> s.toLowerCase(Locale.ROOT),
                        Function.identity(),
                        (first, ignored) -> first,
                        LinkedHashMap::new));

        List<String> byNormalizedKey =
                new ArrayList<>(byKey.values());

        System.out.println("by-key=" + byNormalizedKey);

        String collisionA = "Aa";
        String collisionB = "BB";

        System.out.println("same-hash=" +
                (collisionA.hashCode() == collisionB.hashCode()));

        System.out.println("collision-distinct=" +
                Stream.of(collisionA, collisionB).distinct().count());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 DistinctEqualityDemo.java
java DistinctEqualityDemo
~~~

**Stdout chính xác đã kiểm chứng bằng biên dịch và chạy:**

~~~text
strings=[java, stream, Java]
customers=[Lan#7, Minh#2, Hoa#3]
records=[Point[x=1, y=2], Point[x=1, y=3]]
ints=[4, 2, 1]
with-null=[A, null, B]
decimal.equals=false
decimal.compareTo=0
decimal.distinct=2
arrays.equals=true
arrays.distinct=2
by-key=[Java, Stream, Map]
same-hash=true
collision-distinct=2
~~~

### Phân tích từng phần

1. **strings**: `"java"` trùng chính xác nên bỏ bản thứ hai; `"Java"` khác chữ hoa vẫn được giữ.
2. **customers**: class định nghĩa equality theo `id` và hash code theo `id`; với ordered List giữ first representative cho mỗi id.
3. **records**: `Point` có equality được tạo theo `x` và `y`; hai điểm `(1,2)` thành một.
4. **ints**: `IntStream.distinct()` làm việc trực tiếp với các `int`; thứ tự nguồn được giữ.
5. **with-null**: `null` không tự bị lọc; hai occurrences trở thành một `null` trong kết quả.
6. **decimal.equals** và **decimal.compareTo**: `BigDecimal` scale tạo sự khác nhau giữa structural/value equality theo `equals` và numeric comparison.
7. **decimal.distinct**: vì `a.equals(b)` là false, `distinct` giữ cả hai.
8. **arrays.equals**: hai mảng chứa cùng values thì content equality qua `Arrays.equals` là true.
9. **arrays.distinct**: stream chứa **hai array objects**; array `equals` mặc định dùng identity nên giữ cả hai.
10. **by-key**: collector dùng lowercase key và `LinkedHashMap`, giữ giá trị đầu khi key trùng ở sequential ordered stream.
11. **same-hash**: hai String khác nội dung có cùng `hashCode`; đây là hash collision hợp lệ.
12. **collision-distinct**: hai String không bằng nhau nên cả hai phải được giữ.

Đoạn code sử dụng `record` (Java 16+) và `Stream.toList()` (Java 16+), nên yêu cầu Java 17+ rõ ràng. Những nguyên tắc `distinct`, `equals`, `hashCode`, `IntStream` và collectors cốt lõi đã tồn tại từ Java 8.

## 22. Phân biệt distinct, Set, toMap và groupingBy

Không nên xem bốn cơ chế sau là các cách viết hoàn toàn tương đương:

| Công cụ | Khử trùng theo đâu? | Kết quả và khác biệt |
| --- | --- | --- |
| `stream.distinct()` | `equals` của phần tử | Stream các đại diện; stable cho ordered source |
| `new HashSet<>(items)` | `equals/hashCode` | Set không cam kết encounter order |
| `new LinkedHashSet<>(items)` | `equals/hashCode` | Set giữ insertion order trong trường hợp tương ứng |
| `Collectors.toMap(key, value, merge, supplier)` | Equality của **key** | Có thể chọn first/last/aggregate object theo key |
| `Collectors.groupingBy(keyFn)` | Equality của key | Nhóm nhiều objects thành List/collection thay vì bỏ dữ liệu |

Ví dụ hai lựa chọn khác nhau:

~~~java
List<String> source = List.of("B", "A", "B");

// Đối với ordered List:
List<String> unique = source.stream().distinct().toList();

// Muốn một Set giữ insertion order:
Set<String> set = new LinkedHashSet<>(source);
~~~

Cả hai đều có thể biểu diễn `B` rồi `A`, nhưng API types, mutability và mục đích sử dụng khác nhau. Đừng chọn Set nếu API consumer cần một List cụ thể mà không có conversion hợp lệ.

### Khi cần giữ mọi bản ghi nhưng tổ chức theo key

~~~java
Map<String, List<Event>> groups = events.stream()
        .collect(Collectors.groupingBy(Event::eventId));
~~~

Cách này **không loại bỏ các event**; nó nhóm chúng theo eventId. Nếu nghiệp vụ cần điều tra lịch sử/các phiên bản, grouping có thể tốt hơn distinct vì không làm mất những record bị coi trùng.

### Khi cần phân tích dữ liệu đầu vào trước khử trùng

Có thể tính:
- Tổng số records.
- Số unique keys.
- Số duplicate records và các nhóm duplicate.
- Chính sách giữ first/last/latest/priority.
- Audit dữ liệu bị loại.

Làm rõ những đầu ra cần thiết trước khi chọn collector. `distinct()` không cung cấp trực tiếp danh sách “phần tử bị loại và lý do bị loại” cho nghiệp vụ cần audit.

## 23. equals/hashCode trong value object và dữ liệu nghiệp vụ

Thiết kế equality không chỉ để `distinct` hoạt động; nó ảnh hưởng:
- `HashSet.contains` / `HashMap.get`.
- Cache keys.
- Entity identity và ORM.
- Deduplication ở nhiều tầng.
- Tests dùng `assertEquals` hoặc so sánh collection.
- Không ít API khác trên JVM dùng equality contract.

### Equality theo business key vs toàn bộ state

**Value object** (ví dụ một tọa độ `Point(x,y)`) thường có equality theo toàn bộ những thành phần định nghĩa giá trị.

**Entity** (ví dụ `Customer(id,name,...)`) có thể có equality theo identity key `id`, nhưng phải giải quyết:
- ID được cấp khi nào?
- Có nhiều objects chưa được lưu dùng cùng placeholder ID không?
- ID có thay đổi không?
- Proxy/subclass có ảnh hưởng equality không?
- Một entity từ database shard khác có thể trùng ID không?
- Đối tượng có được serialize/deserialized qua nhiều service không?

Không viết `equals` theo `id` một cách máy móc nếu điều đó vi phạm domain identity.

### Đừng sửa equals chỉ để dedup một báo cáo

Nếu `Customer` đang có equality đúng về business semantics nhưng một báo cáo muốn gom “cùng email không phân biệt hoa thường”, hãy tạo **canonical key** ở lớp báo cáo. Sửa `Customer.equals` có thể làm thay đổi semantics của Set/Map/cache khắp ứng dụng và tạo lỗi ngoài phạm vi báo cáo.

Một phương án an toàn là dùng collector theo `normalizeEmail(customer.email())` với rules normalization được đặc tả và test đầy đủ. Tuy nhiên, email address normalization thực tế có các quy tắc miền/local-part phức tạp; không nên khẳng định toàn bộ email có thể chuẩn hóa chính xác chỉ bằng `toLowerCase`.

## 24. Kiểm thử hợp đồng và test cases nên có

### Test equals và hashCode trước

Nếu bạn tự viết một value class, test tối thiểu:

~~~java
Customer a = new Customer(7, "Lan");
Customer b = new Customer(7, "Another display");
Customer c = new Customer(8, "Lan");

if (!a.equals(b)) {
    throw new AssertionError("Equal id must be equal");
}
if (a.hashCode() != b.hashCode()) {
    throw new AssertionError("Equal objects need same hash");
}
if (a.equals(c)) {
    throw new AssertionError("Different id should differ");
}
~~~

Đây là mã minh họa với `Customer` như chương trình đầy đủ. Nếu có hierarchy, thêm symmetry/transitivity tests. Nếu có mutable fields, thêm tests chứng minh semantics an toàn hoặc refactor thành immutable keys.

### Test kết quả distinct theo ordered input

~~~java
List<Customer> unique = customers.stream()
        .distinct()
        .toList();
~~~

Nên assert:
- Số lượng unique đúng.
- Mỗi identity key chỉ có một đại diện.
- Trong **ordered stream**, first representative được giữ.
- Kết quả không làm thay đổi source.
- Các trường hợp duplicate ở đầu/giữa/cuối được xử lý.
- `null` nếu nguồn cho phép và nghiệp vụ cần, được xử lý theo chính sách.

### Test case-insensitive theo key

Tạo các case:
- `"Java"` và `"java"`.
- Khoảng trắng đầu/cuối có được trim hay không?
- Các ký tự Unicode và locale liên quan.
- Key rỗng hoặc `null`.
- Input có thứ tự khác nhau.
- Bản ghi trùng key nhưng khác metadata, kiểm tra policy giữ first/latest.

Không assert một thứ tự output cụ thể cho **unordered parallel** stream nếu contract không bảo đảm thứ tự.

### Test hiệu năng và memory

Nếu gọi `distinct()` trên hàng triệu phần tử:
- Profile heap usage và thời gian.
- Thử sequential so với ordered parallel trên workload thật.
- Cân nhắc đổi sang unordered chỉ khi semantics cho phép.
- Kiểm tra độ phân tán hash của key.
- Kiểm tra whether DB query `SELECT DISTINCT` hoặc unique constraint đã thực hiện logic tốt hơn trước khi kéo toàn bộ dữ liệu về JVM. Lưu ý SQL `DISTINCT` có semantics khác Java object equality; không thay thế nhau một cách mù quáng.

## 25. Câu hỏi thường gặp

**Hỏi:** `distinct()` dùng `equals` hay `hashCode`?

**Đáp:** Javadoc định nghĩa uniqueness theo **`Object.equals`**. `hashCode` là hợp đồng tương thích thiết yếu cho hash-based lookup; khi override equals, phải override hashCode đúng. Không được đồng nhất “hash giống” với “object bằng nhau”.

**Hỏi:** Nếu hai đối tượng khác tham chiếu nhưng cùng field, chúng bị gộp chứ?

**Đáp:** Chỉ nếu `equals` của class đánh giá chúng bằng nhau. `Object.equals` mặc định dùng identity, còn `record` và các value classes thường có value semantics riêng.

**Hỏi:** Có `distinct(Comparator)` không?

**Đáp:** Không có overload đó trong `java.util.stream.Stream`. Dùng canonicalization hoặc collector phù hợp nếu muốn equality/key rules khác.

**Hỏi:** `distinct()` có tự sắp xếp không?

**Đáp:** Không. Với ordered input, nó giữ first representative theo encounter order. Cần `sorted()` khi muốn sắp xếp.

**Hỏi:** `parallel().distinct()` có giữ bản đầu không?

**Đáp:** Nếu stream vẫn có encounter order, distinct stable theo Javadoc. Nhưng giữ ổn định có thể tốn buffering/barrier. Nếu gọi `unordered()`, không còn bảo đảm lựa chọn đại diện đầu tiên.

**Hỏi:** Có thể dùng `peek` để đếm số duplicate bị loại không?

**Đáp:** Không nên dựa vào side effects của intermediate stages để xác định một hợp đồng audit. Hãy dùng một thuật toán/collector thiết kế để trả metrics và dữ liệu cần thiết. Pipeline có thể tối ưu hóa/short-circuit, đặc biệt khi terminal thay đổi.

**Hỏi:** Có phải record luôn giải quyết được mọi vấn đề equality?

**Đáp:** Không. Record equality mặc định dựa trên components; domain có thể muốn identity theo subset/key hoặc content equality cho mutable arrays.

**Hỏi:** BigDecimal `1.0` và `1.00` có trùng trong distinct không?

**Đáp:** Không theo mặc định: `BigDecimal.equals` phân biệt scale, dù `compareTo` có thể trả 0. Chỉ normalize nếu business semantics cho phép.

**Hỏi:** Arrays có cùng phần tử được distinct loại không?

**Đáp:** Không nếu stream chứa **array objects** riêng và dùng array default equality. Muốn dedup phần tử của một `int[]`, dùng `Arrays.stream(intArray).distinct()`.

**Hỏi:** Có thể lọc `null` bằng distinct không?

**Đáp:** `distinct` chỉ giữ tối đa một `null` nếu nguồn chứa null. Muốn loại hết, thêm `filter(Objects::nonNull)`.

## 26. Bài tập thực hành

**Bài 1 — String:** Tính kết quả của `Stream.of("a","b","a","A","b").distinct().toList()`. Giải thích vai trò của `String.equals` và encounter order.

**Bài 2 — Customer:** Viết class `Customer(id,name)` với equality theo `id` bất biến. Override cả `equals` và `hashCode`. Tạo ba customers có hai ID trùng và kiểm tra số unique.

**Bài 3 — Sai hash contract:** Tạo class override equals theo `id` nhưng để `hashCode` kế thừa từ `Object`. Viết test phát hiện vi phạm hợp đồng, không cần dựa vào một output Stream cụ thể không được bảo đảm.

**Bài 4 — Hash collision:** Dùng `"Aa"` và `"BB"`. In hash codes, equals và distinct count. Vì sao collision không làm hai Strings bằng nhau?

**Bài 5 — BigDecimal:** Với `new BigDecimal("2.0")` và `new BigDecimal("2.00")`, so sánh `equals`, `compareTo` và `distinct()`. Nêu tình huống nghiệp vụ phải giữ scale.

**Bài 6 — Mảng:** So sánh `Stream.of(new int[]{1,2},new int[]{1,2}).distinct().count()` với `Arrays.stream(new int[]{1,2,1}).distinct().toArray()`.

**Bài 7 — Record:** Tạo `record OrderKey(long id, String region)`. Vì sao hai instances cùng id nhưng region khác sẽ không bị distinct loại?

**Bài 8 — Null:** Tạo `Stream.of("x",null,"x",null)`. So sánh `distinct` và `filter(Objects::nonNull).distinct`.

**Bài 9 — Theo key:** Có các events trùng `eventId` nhưng khác timestamp. Viết collector giữ first event trên sequential ordered source và collector chọn event có timestamp lớn nhất; định nghĩa tie policy rõ.

**Bài 10 — Case-insensitive:** Với `["Java","java","JAVA","Stream"]`, dùng key lowercase và `LinkedHashMap` để giữ original string xuất hiện đầu.

**Bài 11 — Parallel:** So sánh semantics của `list.parallelStream().distinct().toList()` và `list.parallelStream().unordered().distinct().toList()`. Khi nào được phép bỏ encounter order?

**Bài 12 — Mutable equality:** Thiết kế một bug do thay đổi `id` sau khi thêm object vào `HashSet`. Giải thích cách sửa bằng immutable identifier.

**Bài 13 — DoubleStream:** Kiểm thử `Double.NaN`, `+0.0` và `-0.0` với `DoubleStream.distinct()`. Vì sao dùng `==` để diễn giải kết quả có thể gây hiểu nhầm?

**Bài 14 — Bài toán performance:** Khi khử trùng một triệu records hầu hết đều khác nhau, đo heap/time của sequential vs ordered parallel. Lựa chọn tối ưu phải dựa trên workload và correctness requirements gì?

## 27. Tổng kết

- **`Stream.distinct()` dùng equality của phần tử**, được Javadoc định nghĩa theo `Object.equals(Object)`.
- **`equals` là quan hệ tương đương**; `hashCode` phải tương thích: đối tượng bằng nhau bắt buộc cùng hash, nhưng cùng hash chưa đủ kết luận bằng nhau.
- **Class không override equals** thường dùng identity equality, nên hai objects có cùng fields vẫn có thể không bị dedup.
- **Record** có value equality mặc định theo components; **arrays** dùng identity equality cho chính array object; **BigDecimal** phân biệt scale trong equals.
- **`null`** không tự bị loại; `distinct` giữ tối đa một null trong Stream có null.
- **Primitive `distinct()`** hoạt động trên `int`, `long`, `double`, với các quy tắc riêng cho NaN/signed zero của double.
- **Ordered distinct là stable**, giữ phần tử đầu mỗi nhóm theo encounter order; unordered không có bảo đảm đại diện đầu.
- **Parallel ordered distinct có thể tốn memory/buffering**, do phải bảo toàn stability.
- **Không mutate các fields tham gia equality/hashCode trong lúc dedup**; ưu tiên immutable keys và stateless transformations.
- **Khử trùng theo business key khác với Object.equals**. Dùng normalization, `toMap`, grouping hoặc một thuật toán selection có policy rõ, không sửa toàn cục `equals` chỉ cho một báo cáo.
- **Kiểm thử equality contracts trước**, rồi kiểm tra kết quả Stream; không lấy số lần gọi `equals/hashCode` hoặc thứ tự log làm API contract.
- Kiến thức trên vẫn áp dụng cho Java hiện đại; ví dụ chính sử dụng Java 17+ với `record` và `Stream.toList()`.

## 28. Tài liệu chuẩn còn áp dụng

1. Java SE 26 — `Stream.distinct()`, ordering và API note về ordered parallel buffering: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#distinct()
2. Java SE 26 — `Object.equals(Object)` và `Object.hashCode()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html
3. Java SE 26 — `java.util.stream` package summary (stateful operations, ordering, non-interference): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
4. Java SE 17 — `Stream.distinct()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#distinct()
5. Java SE 17 — `IntStream.distinct()`, `LongStream.distinct()`, `DoubleStream.distinct()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html
6. Java SE 17 — `BigDecimal.equals`, `compareTo`, `stripTrailingZeros`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
7. Java SE 17 — `Arrays.equals` và `Arrays.hashCode`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html
8. Java SE 17 — `Record` và quy tắc equality của record classes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html
9. Java SE 17 — `Collectors.toMap`, `groupingBy`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html
10. Java SE 17 — `HashSet` và `LinkedHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html
11. Java SE 17 — `Double.compare` và signed zero/NaN: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html
12. Java Language Specification Java SE 17 — `8.10 Record Classes`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10

Khi sử dụng `distinct` trong code thực, hãy đặt ba câu hỏi trước khi viết pipeline: **“Trùng theo quan hệ nào?”, “Bản đại diện nào phải được giữ?” và “Thứ tự/kích thước nguồn có ảnh hưởng hiệu năng không?”**. Chỉ khi cả ba câu trả lời rõ ràng, việc gọi `distinct()` mới chắc chắn đúng semantics của hệ thống.