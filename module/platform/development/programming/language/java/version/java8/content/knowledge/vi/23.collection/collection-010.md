# Hợp đồng equals, hashCode và tác động lên tập hợp trong Java

> **Phạm vi:** Java 8 — Collection. Bài học giải thích hai phương thức của `Object`, cách Java Collections Framework nhận biết phần tử/khóa tương đương, hậu quả khi vi phạm hợp đồng và những cách thiết kế vẫn đúng trong các JDK hiện hành.

## 1. Vì sao hai phương thức này quan trọng?

Trong Java, một đối tượng có thể được so sánh theo **cùng tham chiếu** hoặc theo **ý nghĩa bằng nhau**. Hai khái niệm không đồng nhất:

- Toán tử `==` trên **hai biến kiểu tham chiếu** kiểm tra chúng trỏ đến **cùng một object** hay không. Với kiểu nguyên thủy, `==` so sánh giá trị nguyên thủy.
- Phương thức `equals(Object)` kiểm tra **quan hệ bằng nhau do lớp định nghĩa**. Mặc định của `Object.equals` là đồng nhất tham chiếu, nhưng nhiều lớp như `String`, các wrapper và các value object đã ghi đè để so sánh nội dung.
- Phương thức `hashCode()` trả một số `int` hỗ trợ tổ chức dữ liệu theo hash. Nó **không phải ID duy nhất** và không thể thay thế `equals`.

Ví dụ:

~~~java
String first = new String("JAVA");
String second = new String("JAVA");

System.out.println(first == second);       // false
System.out.println(first.equals(second));  // true
System.out.println(first.hashCode() == second.hashCode()); // true
~~~

Đây là **đoạn minh họa** trong một phương thức Java, không phải chương trình độc lập. Hai `new String(...)` tạo hai object khác nhau nhưng mang cùng nội dung; `String.equals` so sánh nội dung, vì thế chúng có cùng hash code theo hợp đồng.

Tác động trực tiếp: `HashSet` xem hai chuỗi trên là một giá trị logic; `HashMap` xem chúng là **cùng khóa logic**. Nếu dùng lớp tự viết mà không cài đặt `equals` và `hashCode` đúng, những phần tử nhìn như trùng nhau có thể vẫn được lưu thành nhiều mục.

### 1.1. "Bằng nhau" phải được định nghĩa theo nghiệp vụ

Ví dụ hai sản phẩm cùng mã SKU và thị trường:

~~~text
ProductKey("P-01", "VN")
ProductKey("P-01", "VN")
~~~

Nếu nghiệp vụ coi hai cặp dữ liệu này là cùng một khóa, `equals` phải trả `true`, bất kể chúng được tạo bởi hai lần `new`.

Nhưng nếu đối tượng là **thực thể có vòng đời** mà ID chưa được cấp khi tạo, định nghĩa equality dựa trên ID có thể cần chiến lược riêng. Không có một công thức áp dụng đúng cho mọi domain object: trước tiên chọn **thuộc tính định danh logic**, sau đó mới cài đặt các phương thức.

## 2. Hợp đồng của Object.equals(Object)

Các lớp cài đặt `equals` phải tuân thủ những tính chất cơ bản trong Javadoc:

| Tính chất | Quy tắc | Ví dụ |
| --- | --- | --- |
| **Reflexive — phản xạ** | Với đối tượng `x` không null, `x.equals(x)` là `true` | Một mã sản phẩm luôn bằng chính nó |
| **Symmetric — đối xứng** | `x.equals(y)` và `y.equals(x)` phải cùng kết quả | Không được một chiều đúng, chiều còn lại sai |
| **Transitive — bắc cầu** | Nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)` | Không được có chuỗi bằng nhau nhưng đầu và cuối khác |
| **Consistent — nhất quán** | Gọi lại nhiều lần cho kết quả giống nhau khi thông tin liên quan không thay đổi | Không dựa vào đồng hồ ngẫu nhiên |
| **Non-null** | Với `x` không null, `x.equals(null)` là `false` | Không ném lỗi chỉ vì so sánh với null |

Các quy tắc này phải đúng cho **mọi cặp/triple đối tượng hợp lệ**, không chỉ dữ liệu được dùng trong một test đơn lẻ.

### 2.1. Đối xứng là lỗi dễ mắc khi có kế thừa

Giả sử lớp `Animal` coi mọi object có cùng tên là bằng nhau, còn lớp con `Pet` thêm điều kiện về chủ sở hữu. Nếu `Animal.equals` chấp nhận `instanceof Animal` nhưng `Pet.equals` đòi cùng lớp, ta có thể gặp `a.equals(p) == true` và `p.equals(a) == false`.

Cách xử lý cần được thiết kế có hệ thống:

1. Ưu tiên **value object bất biến** và có thể đánh dấu `final` nếu muốn mỗi value type có định nghĩa equality riêng, không bị subclass làm thay đổi.
2. Khi cần kế thừa, xác định rõ liệu các subtype có thể bằng nhau hay không, chọn chiến lược `getClass()` hoặc một thiết kế khác phù hợp và **kiểm thử đối xứng/bắc cầu**.
3. Tránh tự động thêm trường mới vào `equals` của subclass khi lớp cha cho phép bằng nhau qua `instanceof` mà không xét hợp đồng chung.

`getClass() == other.getClass()` và `instanceof` không phải "một đúng, một sai" cho mọi hệ thống; lựa chọn phụ thuộc việc các subtype có cùng mô hình identity hay không. Ví dụ chạy được ở mục 6 dùng lớp `final` để tránh toàn bộ vấn đề kế thừa.

### 2.2. Phương thức đúng là override, không phải overload

Chữ ký cần ghi đè:

~~~java
@Override
public boolean equals(Object other)
~~~

Đây là **chữ ký phương thức minh họa**, không phải chương trình biên dịch riêng lẻ.

Sai thường gặp:

~~~java
// Chỉ tạo overload; KHÔNG override Object.equals(Object).
public boolean equals(ProductKey other) {
    // ...
    return false;
}
~~~

Khai báo `equals(ProductKey)` không thay thế `Object.equals(Object)`. Collection thường làm việc với tham chiếu kiểu `Object` hoặc API có tham số `Object`, vì thế overload này không đáp ứng hợp đồng.

**Thói quen tốt:** luôn viết `@Override` khi định nghĩa `equals` và `hashCode`. Trình biên dịch sẽ giúp phát hiện chữ ký không thực sự ghi đè một phương thức có sẵn.

## 3. Hợp đồng của Object.hashCode()

Quy tắc căn bản:

1. **Nhất quán trong cùng một lần chạy**, miễn là những thông tin được dùng bởi `equals` không bị thay đổi, thì các lần gọi `hashCode()` trên cùng một đối tượng phải trả cùng `int`.
2. **Hai đối tượng bằng nhau theo `equals` phải có cùng hash code**: nếu `a.equals(b) == true` thì bắt buộc `a.hashCode() == b.hashCode()`.
3. **Hai đối tượng khác nhau theo `equals` không bắt buộc có hash code khác nhau**. Va chạm hash (**collision**) được phép; phân biệt cuối cùng vẫn dựa vào equality.

Dạng kéo theo cần nhớ:

~~~text
a.equals(b) == true
    ==> a.hashCode() == b.hashCode()
~~~

**Chiều ngược lại là sai:**

~~~text
a.hashCode() == b.hashCode()
    KHÔNG suy ra a.equals(b) == true
~~~

Không cần hash code không trùng, không cần hash code luôn dương và không được xem `hashCode` là một khóa bền vững giữa các tiến trình/JVM. API Java không hứa hash code của một object sẽ như nhau khi chạy lại ứng dụng khác thời điểm.

### 3.1. Vì sao cần cả hai phương thức?

Một hash-based collection như `HashSet` hoặc `HashMap` dùng hash để xác định **vùng tra cứu/nhóm ứng viên**, rồi dùng `equals` khi cần phân biệt các khóa có hash liên quan. Đây là mô hình khái niệm; không phải cam kết về số bucket hay thuật toán nội bộ của mọi JDK.

| Tình huống | Kết quả hợp đồng |
| --- | --- |
| `equals == true` và `hashCode` giống nhau | Hợp lệ: hai khóa/giá trị tương đương |
| `equals == false` nhưng `hashCode` giống nhau | Hợp lệ: collision; hai khóa khác nhau vẫn có thể cùng tồn tại |
| `equals == true` nhưng `hashCode` khác nhau | **Vi phạm**; tìm kiếm và loại trùng theo hash có thể sai |
| `hashCode` thay đổi sau khi đưa object vào HashSet/HashMap | Có thể khiến `contains/get/remove` không tìm được object |

Tối ưu tốc độ tìm kiếm không cho phép phá quy tắc equality. Một hash code "phân tán tốt" giúp hạn chế collision nhưng **không thay thế được việc cài `equals` đúng**.

### 3.2. Không bắt buộc dùng Objects.hash

Từ Java 7 đã có:

~~~java
@Override
public int hashCode() {
    return Objects.hash(sku, region);
}
~~~

Đây là đoạn minh họa cho một lớp có hai trường `sku` và `region`, cần `import java.util.Objects;`. `Objects.hash` thuận tiện và nhất quán với việc so sánh các trường tương ứng.

Có thể viết `hashCode` bằng công thức thủ công chuẩn hoặc dùng code generation, miễn tuân thủ hợp đồng. Tránh viết hash từ một tập trường trong khi `equals` lại so sánh tập trường khác theo cách làm các object bằng nhau có thể cho hash khác nhau.

### 3.3. Hash collision không tạo equality

Ví dụ hai đối tượng có hash code cố ý giống nhau:

~~~java
@Override
public int hashCode() {
    return 7;
}
~~~

Đoạn này là **một phương thức minh họa**. Trả hằng `7` về mặt hình thức **không vi phạm** hợp đồng nếu `equals` đúng, nhưng thường có hiệu năng kém khi dữ liệu lớn vì nhiều đối tượng có cùng hash. Vì thế không nên dùng nó trong production; chỉ hữu ích khi học và kiểm thử xử lý collision.

## 4. Cài equals/hashCode cho value object Java 8

Với giá trị định danh bằng cặp `sku` và `region`, thiết kế một lớp:

- `final`: tránh subclass thay đổi cách so sánh.
- Trường `private final`: hạn chế thay đổi trạng thái sau khi thêm vào Set/Map.
- Constructor xác nhận đầu vào phù hợp; ở đây yêu cầu hai chuỗi khác null.
- `equals(Object)` so sánh đúng hai trường nghiệp vụ.
- `hashCode()` tính từ chính hai trường đó.
- `toString()` chỉ dùng để hiển thị, **không phải** cách định nghĩa equality.

~~~java
import java.util.Objects;

public final class ProductKey {
    private final String sku;
    private final String region;

    public ProductKey(String sku, String region) {
        this.sku = Objects.requireNonNull(sku, "sku");
        this.region = Objects.requireNonNull(region, "region");
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ProductKey)) {
            return false;
        }
        ProductKey that = (ProductKey) other;
        return sku.equals(that.sku) && region.equals(that.region);
    }

    @Override
    public int hashCode() {
        return Objects.hash(sku, region);
    }

    @Override
    public String toString() {
        return sku + "@" + region;
    }
}
~~~

Đây là **lớp độc lập có thể biên dịch** khi lưu thành `ProductKey.java`; phần ví dụ có `main` trong mục 10 sử dụng một lớp lồng `ProductKey` tương đương, để chạy trực tiếp bằng một tệp.

### 4.1. Vì sao thường chọn final fields?

Khi một `ProductKey` được dùng làm khóa `HashMap`, các trường mà `equals`/`hashCode` dựa vào **không được thay đổi trong thời gian nó làm khóa**. Trường `final` kiểu `String` vừa dễ bảo đảm tính này vừa làm đối tượng an toàn hơn khi chia sẻ giữa các thành phần.

Tuy nhiên, **`final` không làm mọi object bất biến sâu**. Nếu một trường `final List<String> codes` tham chiếu đến một List còn sửa được, nội dung List có thể đổi và làm thay đổi kết quả equality/hash. Cần cân nhắc defensive copy và immutable collection theo hợp đồng ứng dụng.

### 4.2. Null và so sánh trường

Nếu thuộc tính có thể null, dùng `Objects.equals(a, b)` để so sánh an toàn:

~~~java
return Objects.equals(this.code, other.code)
        && Objects.equals(this.description, other.description);
~~~

Đây là biểu thức minh họa trong `equals`. `Objects.equals(null, null)` trả `true`; `Objects.equals(null, "X")` trả `false`. Với code chính ở trên, constructor đã từ chối null nên có thể gọi `sku.equals` trực tiếp.

**Không gọi `x.equals(...)` khi `x` có thể null**: việc đó ném `NullPointerException` trước khi có kết quả so sánh.

### 4.3. Có nên đưa mọi trường vào equals?

Không nhất thiết. Một `ProductKey` định danh bằng `sku + region` không cần đưa các thuộc tính hiển thị như tên mô tả hay giá đang thay đổi vào equality. Chỉ chọn trường theo **ngữ nghĩa bằng nhau** của value type.

Nếu cần so sánh mọi thuộc tính như một snapshot, cũng có thể đưa tất cả trường cần thiết vào; lúc đó nên bảo đảm chúng ổn định. Quan trọng là quy tắc phải rõ, nhất quán và được kiểm thử.

## 5. Tác động lên HashSet và HashMap

### 5.1. HashSet loại phần tử trùng theo equality

Với `Set<E>`, một phần tử `e` được thêm mới khi không có phần tử đang lưu nào bằng `e` theo hợp đồng `equals`. `HashSet` dùng hash để tổ chức tra cứu nhưng phải tuân thủ quan hệ bằng nhau.

~~~java
Set<ProductKey> products = new HashSet<>();
boolean first = products.add(new ProductKey("P-01", "VN"));
boolean second = products.add(new ProductKey("P-01", "VN"));

// first == true, second == false, products.size() == 1
~~~

Đây là **đoạn minh họa** yêu cầu lớp `ProductKey` của mục 4 cùng import `Set`/`HashSet`. Việc gọi `new` hai lần không khiến chúng tự động trở thành hai phần tử khác nhau nếu `equals` xem chúng bằng nhau.

Nếu lớp không override `equals`, Object mặc định chỉ xét cùng tham chiếu; hai lần `new ProductKey(...)` lúc đó có thể bị xem là hai phần tử khác nhau. Do đó, lỗi trùng phần tử thường là lỗi **mô hình equality**, không phải lỗi `HashSet`.

### 5.2. HashMap thay thế value khi key đã có

~~~java
Map<ProductKey, String> inventory = new HashMap<>();
inventory.put(new ProductKey("P-01", "VN"), "old");
String previous =
        inventory.put(new ProductKey("P-01", "VN"), "new");

// previous == "old"
// inventory.size() == 1
// inventory.get(new ProductKey("P-01", "VN")) == "new"
~~~

Đây là **đoạn minh họa**. Khi một khóa mới được coi là bằng khóa có sẵn, `put` thay thế value gắn với khóa logic đó; nó không tạo entry thứ hai. `HashMap` vẫn phân biệt các khóa không bằng nhau ngay cả khi xảy ra hash collision.

**Giới hạn quan trọng:** Không dựa vào thứ tự duyệt của `HashMap`, `HashSet` hay một số lượng bucket cụ thể. Hợp đồng chính ở đây là **quan hệ bằng nhau và ánh xạ khóa → giá trị**.

### 5.3. Chỉ override equals mà quên hashCode

Giả sử hai `ProductKey` được định nghĩa bằng nhau qua `equals` nhưng vẫn giữ `Object.hashCode` gốc. Vì hash mặc định của hai object **không được ràng buộc phải bằng nhau khi ta tùy biến equals**, bộ sưu tập dựa trên hash có thể không phát hiện khóa bằng nhau; `contains`/`get`/`remove` có thể hoạt động không đúng kỳ vọng.

Quy tắc thực hành: **đã override equals thì phải override hashCode tương thích**. Điều ngược lại không bắt buộc về mặt ngôn ngữ, nhưng cần hiểu rõ lý do thay đổi hash mà không thay đổi equality; trong phần lớn value object, cả hai phương thức đi cùng nhau.

### 5.4. Hash collision vẫn xử lý được

Hai object không bằng nhau nhưng cùng `hashCode` có thể cùng lưu trong `HashSet`. Cơ chế tra cứu cần đối chiếu equality ở những ứng viên liên quan. Vì thế điều kiện:

~~~text
sameHashCode(a, b) == true
~~~

**không tương đương** với:

~~~text
a.equals(b) == true
~~~

Không dùng `hashCode` để thay mã khóa nghiệp vụ, mã định danh duy nhất toàn hệ thống hay fingerprint bảo mật; số `int` có miền hữu hạn nên collision là điều có thể xảy ra.

## 6. List, Set và Map có hợp đồng bằng nhau khác nhau

Bản thân giao diện Collection không quy định mọi implementation đều phải so sánh cấu trúc theo cùng một cách. Những giao diện chuyên biệt như `List`, `Set` và `Map` có hợp đồng riêng:

| Loại | Bằng nhau khi | Hệ quả |
| --- | --- | --- |
| `List` | Cùng số phần tử; từng phần tử ở cùng vị trí tương đương theo `equals` | **Thứ tự có ý nghĩa**, phần tử trùng lặp được phép |
| `Set` | Cùng số phần tử và chứa các phần tử tương đương | **Thứ tự không quyết định equality** |
| `Map` | Cùng tập các ánh xạ khóa → value tương đương | **Thứ tự entry không quyết định equality** |
| `HashSet` / `HashMap` | Tuân thủ hợp đồng của Set/Map và dùng hash trong triển khai | Cần khóa/phần tử có `hashCode` tương thích `equals` |
| `TreeSet` / `TreeMap` | Dùng thứ tự tự nhiên hoặc Comparator để tổ chức và nhận biết phần tử/khóa | Cần quan hệ `compare(...) == 0` **nhất quán với `equals`** nếu muốn thỏa hợp đồng Set/Map |

### 6.1. Danh sách giữ trùng lặp

~~~java
List<String> list = Arrays.asList("A", "B", "A");

System.out.println(list.size());        // 3
System.out.println(list.contains("A")); // true
~~~

Đây là **đoạn minh họa**. `List` có thể chứa nhiều phần tử bằng nhau; `contains` kiểm tra sự tồn tại theo equality chứ không buộc tập hợp phải duy nhất.

Hai List:

~~~java
Arrays.asList("A", "B").equals(Arrays.asList("B", "A"))
~~~

trả `false` vì vị trí phần tử khác nhau. Dù cùng chứa hai giá trị `A` và `B`, List có ordering là một phần của hợp đồng equality.

### 6.2. Set không phụ thuộc thứ tự phần tử

~~~java
Set<String> left = new HashSet<>(Arrays.asList("A", "B"));
Set<String> right = new HashSet<>(Arrays.asList("B", "A"));

System.out.println(left.equals(right)); // true
~~~

Đây là **đoạn minh họa**. Không được từ dòng trên suy ra `HashSet` sẽ in `[A, B]` theo một thứ tự cố định; điều được bảo đảm là tính bằng nhau theo tập phần tử.

### 6.3. Hash của chính tập hợp có ý nghĩa riêng

Hợp đồng `Set.hashCode()` được định nghĩa bằng tổng các hash code của phần tử, với hash của `null` được coi là `0`. `List.hashCode()` dùng cách kết hợp nhạy với thứ tự theo đặc tả. `Map.hashCode()` là tổng hash code của các entry.

Điều này giúp hai Set/Map/List **bằng nhau theo hợp đồng của giao diện** cũng có hash code tương thích. Nhưng nó **không** có nghĩa Set/Map có thể dùng một cách vô tư làm phần tử/khóa trong hash collection rồi tiếp tục bị sửa: nếu nội dung làm hash của chúng thay đổi, vấn đề mutable key vẫn xuất hiện.

## 7. TreeSet/TreeMap: comparator khác hashCode

`TreeSet` và `TreeMap` tổ chức phần tử theo **natural ordering** (`Comparable.compareTo`) hoặc `Comparator.compare`. Chúng **không dựa vào `hashCode` để nhận biết phần tử tương đương**. Đối với TreeSet, hai phần tử được coi trùng từ góc nhìn của cấu trúc khi phép so sánh thứ tự cho kết quả `0`.

Vì hợp đồng của `Set` nói theo `equals`, để TreeSet hoạt động nhất quán với Set, nên bảo đảm:

~~~text
compare(a, b) == 0
    tương đương a.equals(b) == true
~~~

Nếu so sánh thứ tự và `equals` không nhất quán, TreeSet/TreeMap vẫn có hành vi được xác định theo comparator, nhưng có thể **vi phạm hợp đồng tổng quát của Set/Map**. Không phải lỗi `hashCode`; đây là một quan hệ tương đương khác.

### 7.1. Ví dụ kinh điển: BigDecimal("2.0") và BigDecimal("2.00")

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));      // false
System.out.println(a.compareTo(b));   // 0
~~~

Đây là **đoạn minh họa**. `BigDecimal.equals` xét cả giá trị số **và scale**; `compareTo` so sánh giá trị số, nên hai biểu diễn trên bằng nhau về giá trị nhưng khác về `equals`.

~~~java
Set<BigDecimal> hashed = new HashSet<>();
hashed.add(new BigDecimal("2.0"));
hashed.add(new BigDecimal("2.00"));

Set<BigDecimal> sorted = new TreeSet<>();
sorted.add(new BigDecimal("2.0"));
sorted.add(new BigDecimal("2.00"));

// hashed.size() == 2
// sorted.size() == 1
~~~

Với `HashSet`, `equals` là `false` nên hai phần tử riêng biệt được giữ. Với `TreeSet`, `compareTo` trả `0` nên lần thêm thứ hai không tạo phần tử mới. Đây là tình huống minh họa sự không nhất quán nổi tiếng của natural ordering `BigDecimal` với `equals`.

**Không viết**: "TreeSet loại trùng bằng hashCode". `hashCode` không phải tiêu chí tương đương của TreeSet.

### 7.2. Comparator theo chiều dài có thể làm mất giá trị khác nhau

~~~java
Set<String> byLength = new TreeSet<>(
        Comparator.comparingInt(String::length));
byLength.add("ab");
byLength.add("cd");

// size == 1, vì compare("ab","cd") == 0.
~~~

Đây là **đoạn minh họa**. Theo `String.equals`, `"ab"` khác `"cd"`; comparator chỉ so sánh độ dài xem chúng là bằng nhau. Nếu mục đích là sắp xếp theo độ dài **nhưng vẫn giữ các chuỗi khác nhau**, phải có tie-breaker phù hợp:

~~~java
Comparator<String> lengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());

Set<String> fixed = new TreeSet<>(lengthThenText);
fixed.add("ab");
fixed.add("cd"); // size == 2.
~~~

Đoạn này là **minh họa Java 8**. Quan hệ `compare(a,b)==0` của comparator mới tương ứng với hai chuỗi bằng nhau theo `String.equals` (với đầu vào String không null).

## 8. Đừng thay đổi trạng thái tham gia equals/hashCode khi đang lưu trong Set/Map

### 8.1. Vấn đề mutable key

Ví dụ một object có trường `code` có thể đổi:

~~~java
final class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey
                && Objects.equals(code, ((MutableKey) other).code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
~~~

Đây là **lớp minh họa**, cần import `java.util.Objects` và nằm trong file thích hợp. Hai phương thức có vẻ tương thích ngay tại thời điểm đối tượng không bị sửa. Nhưng hãy xem:

~~~java
MutableKey key = new MutableKey("A");
Set<MutableKey> keys = new HashSet<>();
keys.add(key);

key.code = "B"; // THAY ĐỔI trường tham gia hash/equality.

boolean found = keys.contains(key);
~~~

Mã trên **không còn bảo đảm `found == true`**. Khi object đang nằm trong HashSet mà hash code của nó bị đổi, cấu trúc nội bộ không tự chuyển phần tử sang vị trí mới. `contains` hoặc `remove` có thể thất bại, thậm chí object cũ vẫn tồn tại khi duyệt tập hợp.

Tương tự, thay đổi trạng thái của **khóa HashMap** có thể làm `map.get(key)` trả `null` dù entry vẫn tồn tại. Không dựa vào việc một thử nghiệm nhỏ có vẻ chạy đúng: theo Javadoc của Set/Map, hậu quả thay đổi thông tin dùng để so sánh phần tử/khóa khi nó đang ở trong cấu trúc không được bảo đảm.

### 8.2. Giải pháp

- Ưu tiên khóa **immutable value object**, các trường dùng trong `equals`/`hashCode` không thay đổi.
- Nếu cần cập nhật một giá trị định danh logic, **remove bằng khóa cũ trước**, tạo khóa mới rồi add/put lại; chỉ thực hiện khi các điều kiện giao dịch và cạnh tranh được kiểm soát.
- Không đưa list/map/set mutable làm một phần của khóa trừ khi có thiết kế đóng băng dữ liệu hợp lệ.
- Với ORM/entity, cần cân nhắc ID do cơ sở dữ liệu cấp sau khi persist; tránh xây hash từ một ID thay đổi từ `null` sang có giá trị trong lúc entity đã được dùng làm khóa.
- Đừng dùng `System.identityHashCode` như một "cách sửa" khi domain mong muốn bằng nhau theo nội dung; nó có ý nghĩa khác.

### 8.3. HashMap với key bất biến nhưng value thay đổi

Thay đổi **value** của một entry HashMap là nghiệp vụ bình thường, bởi map tổ chức lookup theo **key**, không phải `value.hashCode()`. Ví dụ `map.put(existingKey, newValue)` là thao tác hợp lệ. Cần phân biệt nó với việc sửa các trường làm **key.hashCode()` thay đổi.

## 9. Stream.distinct, Collectors.toSet và groupingBy liên quan thế nào?

### 9.1. distinct() định nghĩa duy nhất qua equals

`Stream.distinct()` là thao tác loại phần tử trùng theo `Object.equals(Object)`. Với stream **ordered**, nếu có nhiều phần tử bằng nhau, kết quả ổn định giữ **phần tử xuất hiện đầu tiên trong encounter order**. Với stream unordered, không có bảo đảm phải giữ đại diện nào nếu nhiều object khác nhau nhưng equals bằng nhau.

~~~java
List<String> values = Arrays.asList("x", "y", "x", "z");
List<String> unique = values.stream()
        .distinct()
        .collect(Collectors.toList());

// unique = [x, y, z]
~~~

Đây là đoạn minh họa. Việc loại trùng là **ngữ nghĩa của equals**; không được coi hashCode có thể dùng thay cho equals trong phép phân biệt.

### 9.2. Collectors.toSet()

~~~java
Set<ProductKey> uniqueProducts = products.stream()
        .collect(Collectors.toSet());
~~~

Đây là đoạn minh họa, giả định `products` là một collection các `ProductKey`. Collector trả Set với hợp đồng loại trùng theo equality. **Không** dựa vào kiểu Set cụ thể, độ sửa được, serialization hoặc thứ tự duyệt của kết quả; `Collectors.toSet()` là **unordered collector**.

Sự khác nhau với `distinct().collect(toList())`: trường hợp sau trả **List** vẫn giữ thứ tự xuất hiện của các phần tử đầu tiên nếu nguồn ordered, còn `toSet` không hứa thứ tự duyệt.

### 9.3. groupingBy dùng Map key

~~~java
Map<String, List<ProductKey>> byRegion = products.stream()
        .collect(Collectors.groupingBy(ProductKey::getRegion));
~~~

Đây là **đoạn minh họa** yêu cầu `ProductKey` có getter `getRegion()` (ví dụ lớp ở mục 4 chưa khai báo getter) và import `Collectors`/`Map`/`List`. `groupingBy` dùng kết quả classifier làm khóa Map; equality/hashCode của loại khóa quyết định phần tử nào được gom về cùng nhóm, theo Map được tạo.

Một classifier tạo **key object mới cho mỗi phần tử** vẫn nhóm đúng nếu các key object có `equals/hashCode` đúng. Nếu không, cùng giá trị logic có thể bị chia thành những khóa khác nhau. Với `groupingByConcurrent`, nguyên lý tương đương khóa vẫn áp dụng trong một ConcurrentMap nhưng có thêm những quy tắc về đồng thời/ordering.

## 10. Chương trình Java 8 đầy đủ và stdout có thể kiểm chứng

Lưu toàn bộ chương trình sau thành **EqualityCollectionsDemo.java**. Mã dùng API có từ Java 8, không in thứ tự duyệt của HashSet/HashMap và không dựa vào một số hash code cụ thể của JVM.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public final class EqualityCollectionsDemo {

    static final class ProductKey {
        private final String sku;
        private final String region;

        ProductKey(String sku, String region) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.region = Objects.requireNonNull(region, "region");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ProductKey)) {
                return false;
            }
            ProductKey that = (ProductKey) other;
            return sku.equals(that.sku)
                    && region.equals(that.region);
        }

        @Override
        public int hashCode() {
            return Objects.hash(sku, region);
        }

        @Override
        public String toString() {
            return sku + "@" + region;
        }
    }

    static final class CollidingKey {
        private final int id;

        CollidingKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof CollidingKey
                    && this.id == ((CollidingKey) other).id;
        }

        @Override
        public int hashCode() {
            return 7; // Cố ý tạo collision để minh họa.
        }
    }

    public static void main(String[] args) {
        ProductKey a = new ProductKey("P1", "VN");
        ProductKey b = new ProductKey("P1", "VN");
        ProductKey c = new ProductKey("P1", "SG");

        System.out.println("same reference = " + (a == b));
        System.out.println("equals = " + a.equals(b));
        System.out.println("same hash = "
                + (a.hashCode() == b.hashCode()));
        System.out.println("equals null = " + a.equals(null));

        List<ProductKey> list = Arrays.asList(a, b, c);
        System.out.println("list size = " + list.size());
        System.out.println("list contains equal = "
                + list.contains(new ProductKey("P1", "VN")));

        Set<ProductKey> set = new HashSet<>(list);
        System.out.println("hash set size = " + set.size());
        System.out.println("hash set contains equal = "
                + set.contains(new ProductKey("P1", "VN")));

        Map<ProductKey, String> map = new HashMap<>();
        System.out.println("first put previous = "
                + map.put(a, "old"));
        System.out.println("second put previous = "
                + map.put(b, "new"));
        System.out.println("map size = " + map.size());
        System.out.println("map lookup = "
                + map.get(new ProductKey("P1", "VN")));

        Set<CollidingKey> collisions = new HashSet<>();
        collisions.add(new CollidingKey(1));
        collisions.add(new CollidingKey(2));
        collisions.add(new CollidingKey(1));
        System.out.println("collision set size = " + collisions.size());

        BigDecimal one = new BigDecimal("2.0");
        BigDecimal two = new BigDecimal("2.00");
        Set<BigDecimal> hashedDecimals = new HashSet<>();
        hashedDecimals.add(one);
        hashedDecimals.add(two);
        Set<BigDecimal> sortedDecimals = new TreeSet<>();
        sortedDecimals.add(one);
        sortedDecimals.add(two);

        System.out.println("big decimal equals = " + one.equals(two));
        System.out.println("big decimal compareTo = " + one.compareTo(two));
        System.out.println("decimal hash set size = "
                + hashedDecimals.size());
        System.out.println("decimal tree set size = "
                + sortedDecimals.size());

        List<ProductKey> withDuplicates = Arrays.asList(a, b, c, b);
        List<ProductKey> distinct = withDuplicates.stream()
                .distinct()
                .collect(Collectors.toList());
        System.out.println("distinct = " + distinct);

        Set<String> s1 = new HashSet<>(Arrays.asList("A", "B"));
        Set<String> s2 = new HashSet<>(Arrays.asList("B", "A"));
        System.out.println("set equality = " + s1.equals(s2));
        System.out.println("list equality = "
                + Arrays.asList("A", "B")
                        .equals(Arrays.asList("B", "A")));
    }
}
~~~

Lệnh trên **JDK 17+** với mức ngôn ngữ và API **Java 8**:

~~~bash
javac --release 8 EqualityCollectionsDemo.java
java EqualityCollectionsDemo
~~~

**Stdout chính xác:**

~~~text
same reference = false
equals = true
same hash = true
equals null = false
list size = 3
list contains equal = true
hash set size = 2
hash set contains equal = true
first put previous = null
second put previous = old
map size = 1
map lookup = new
collision set size = 2
big decimal equals = false
big decimal compareTo = 0
decimal hash set size = 2
decimal tree set size = 1
distinct = [P1@VN, P1@SG]
set equality = true
list equality = false
~~~

### 10.1. Kiểm tra từng nhóm kết quả

1. `a` và `b` là hai object khác nhau (`== false`), nhưng cùng `sku`/`region` nên `equals true` và có hash code bằng nhau.
2. `List` vẫn giữ ba phần tử, gồm cả hai object bằng nhau; `contains` nhận diện một object mới có giá trị logic tương đương.
3. `HashSet` chỉ giữ hai khóa logic `P1@VN` và `P1@SG`, không quan tâm chúng được tạo mấy lần.
4. `HashMap.put(a, "old")` trả `null` vì chưa có key; `put(b, "new")` trả `"old"` và thay value của cùng key logic. Kích thước Map vẫn bằng `1`.
5. Ba object `CollidingKey` có hash code cùng bằng `7` nhưng ID `1` và `2` khác nhau; Set giữ **hai** phần tử logic. Lần thêm ID `1` thứ hai là trùng.
6. `BigDecimal("2.0")` và `BigDecimal("2.00")` không bằng nhau theo `equals` nhưng `compareTo == 0`; vì vậy `HashSet` có hai phần tử còn `TreeSet` chỉ có một.
7. `Stream.distinct()` giữ đại diện xuất hiện đầu tiên của nhóm bằng nhau trong ordered stream, rồi trả List có hai giá trị `[P1@VN, P1@SG]`.
8. Hai Set cùng nội dung thì bằng nhau dù thứ tự tạo khác; hai List đảo vị trí phần tử thì không bằng nhau.

## 11. Các trường hợp nâng cao vẫn quan trọng

### 11.1. Trường array: cần Arrays.equals/hashCode

Mảng trong Java **không override `Object.equals` để so sánh nội dung**. Hai mảng có các phần tử giống hệt nhau vẫn có thể `arrayA.equals(arrayB) == false` nếu là hai instance.

~~~java
byte[] a = {1, 2, 3};
byte[] b = {1, 2, 3};

System.out.println(a.equals(b));          // false
System.out.println(Arrays.equals(a, b));  // true
~~~

Đây là **đoạn minh họa** với import `java.util.Arrays`.

Nếu value object có trường mảng, dùng `Arrays.equals` với mảng một chiều phù hợp và `Arrays.hashCode` cho chính trường đó. Với mảng chứa mảng, cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode`. `Objects.equals(arrayA, arrayB)` **không thay thế** `Arrays.equals` trong tình huống cần so nội dung mảng.

Cần defensive copy khi nhận/trả mảng nếu muốn value object thực sự bất biến; nếu không, caller có thể thay dữ liệu byte sau khi object đã được đưa vào Set/Map.

### 11.2. BigDecimal: chuẩn hóa theo nhu cầu domain

Nếu nghiệp vụ cần coi `2.0` và `2.00` là cùng giá trị số, phải quyết định cách chuẩn hóa hoặc định nghĩa key phù hợp (ví dụ dùng quy tắc scale cố định). Không tùy tiện sửa `BigDecimal.equals` vì đây là lớp thư viện không thể ghi đè. Cần nhớ `BigDecimal.stripTrailingZeros` có thể thay scale và cách biểu diễn; kiểm tra kỹ nếu quy tắc equality có ý nghĩa kế toán hoặc hiển thị.

### 11.3. Enum và kiểu bất biến

Enum có danh tính instance được Java kiểm soát; `EnumSet` và `EnumMap` là các cấu trúc chuyên dụng hiệu quả khi phần tử/khóa là enum. Chúng không yêu cầu tự viết equals/hashCode cho từng enum constant.

Với các value type bất biến như `String`, `Integer`, `UUID` hoặc một lớp định danh được thiết kế đúng, dùng làm khóa Set/Map thường dễ bảo trì hơn so với một entity có nhiều trường biến đổi.

### 11.4. Record từ Java 16 (không thuộc cú pháp Java 8)

Ở Java 16+, `record` đã là tính năng chính thức, có cách tạo `equals`, `hashCode` và `toString` dựa trên các thành phần record. Ví dụ **chỉ dành cho Java 16+**:

~~~java
record ProductKey(String sku, String region) {}
~~~

Record thích hợp cho nhiều value object, nhưng **không tự bất biến sâu** nếu một thành phần tham chiếu đến object mutable. Ngoài ra, equality của record có ngữ nghĩa do các record component quyết định; không phải mọi domain entity đều nên chuyển thành record.

**Mã runnable trong mục 10 không dùng record**, vì module đặt mục tiêu tương thích API/cú pháp Java 8.

### 11.5. IdentityHashMap là trường hợp chuyên biệt

`IdentityHashMap` so sánh key bằng `==` thay vì `equals` và dùng ngữ nghĩa identity thay cho hợp đồng thông thường của `Map`. Nó phục vụ một số bài toán chuyên biệt như theo dõi object identity trong thuật toán đồ thị/serialization hoặc quản lý đối tượng đã đi qua.

**Không dùng IdentityHashMap chỉ để né việc viết equals/hashCode** nếu ý định nghiệp vụ là tra cứu theo giá trị. Đó sẽ là một thay đổi ngữ nghĩa, không phải sửa lỗi.

## 12. Các lỗi phổ biến và cách phòng tránh

### Lỗi 1 — Override equals nhưng quên hashCode

Hai object bằng nhau trả hash khác nhau, khiến HashSet/HashMap có thể không nhận diện cùng khóa. **Sửa:** cài cả hai, sử dụng trường nhất quán và test.

### Lỗi 2 — So sánh bằng == khi muốn so nội dung String

`a == b` kiểm tra identity, không kiểm tra nội dung. **Sửa:** `Objects.equals(a,b)` hoặc `a.equals(b)` khi biết `a` không null.

### Lỗi 3 — Thay equals bằng hashCode

Hash collision được phép. **Sửa:** định nghĩa equality và không kết luận chỉ từ cùng hash.

### Lỗi 4 — Cài equals(ProductKey) thay vì equals(Object)

Đó là overload, không phải override. **Sửa:** dùng `@Override public boolean equals(Object other)`.

### Lỗi 5 — Vi phạm đối xứng/bắc cầu khi có kế thừa

Lớp cha và lớp con dùng tập trường khác nhau hoặc điều kiện so kiểu mâu thuẫn. **Sửa:** thiết kế equality tổng thể, ưu tiên final value type khi phù hợp, test các cặp/triple subtype.

### Lỗi 6 — Sửa khóa sau khi put hoặc phần tử sau khi add

Thay trường tạo hash/equality sau khi đưa vào HashMap/HashSet phá giả định cấu trúc. **Sửa:** key bất biến hoặc remove/reinsert có kiểm soát.

### Lỗi 7 — Dùng Comparator không nhất quán với equals

`TreeSet` có thể coi hai object không bằng nhau là một phần tử hoặc ngược lại. **Sửa:** thêm tie-breaker phù hợp nếu muốn comparator biểu diễn cùng quan hệ bằng nhau.

### Lỗi 8 — Mong List tự loại trùng

`List` cho phép trùng lặp. **Sửa:** dùng `Set` nếu cần tính duy nhất hoặc `distinct` nếu vẫn cần List của các phần tử riêng biệt theo thứ tự.

### Lỗi 9 — Mong HashSet/HashMap có thứ tự cố định

Hash-based collection không hứa thứ tự duyệt. **Sửa:** nếu cần trật tự đưa vào, xét `LinkedHashSet`/`LinkedHashMap` theo hợp đồng; nếu cần sắp xếp theo khóa, xét `TreeSet`/`TreeMap` với comparator phù hợp.

### Lỗi 10 — So sánh mảng bằng Object.equals

Hai mảng có cùng nội dung có thể bị coi khác. **Sửa:** `Arrays.equals/hashCode` hoặc deep variants khi phù hợp.

### Lỗi 11 — Dùng thuộc tính luôn thay đổi để tính hash của entity

Ví dụ status, nhãn hiển thị hoặc thời gian cập nhật thay đổi có thể làm lookup sai. **Sửa:** chọn identity logic ổn định hoặc tách value key khỏi entity.

### Lỗi 12 — Cho rằng final field bảo đảm bất biến sâu

`final List<String>` vẫn trỏ đến List mutable. **Sửa:** sao chép phòng vệ, immutable types hoặc tách dữ liệu mutable khỏi equality.

### Lỗi 13 — HashCode dùng cho security hay ID bền vững

`hashCode()` là số `int` phục vụ cấu trúc dữ liệu, không phải cryptographic hash hay ID duy nhất. **Sửa:** dùng UUID/ID domain hoặc thuật toán băm chuyên dụng phù hợp mục đích.

### Lỗi 14 — Dùng test thiếu tình huống biên

Test chỉ `a.equals(a)` mà không test null, cùng giá trị khác instance, collision, kế thừa, mutation và container. **Sửa:** xem checklist mục 13.

## 13. Checklist và cách kiểm thử

Với một value object `Key` bất biến, có thể xây test theo các nhóm:

1. **Reflexive:** `a.equals(a)` đúng.
2. **Symmetric:** `a.equals(b) == b.equals(a)`.
3. **Transitive:** nếu `a` bằng `b` và `b` bằng `c` thì `a` bằng `c`.
4. **Consistent:** kết quả như nhau khi dữ liệu liên quan không thay đổi.
5. **Null:** `!a.equals(null)`.
6. **Hash agreement:** nếu `a.equals(b)` thì hai hash code bằng nhau.
7. **Collision tolerance:** object khác nhau nhưng cùng hash vẫn được Set/Map phân biệt.
8. **HashSet:** add hai instance bằng nhau chỉ tăng size một lần; `contains(new Key(...))` đúng.
9. **HashMap:** put key bằng nhau thay value; `get` với instance tương đương trả đúng.
10. **Ordering:** TreeSet comparator phải nhất quán equality nếu ứng dụng yêu cầu hợp đồng Set; test ít nhất một cặp cùng trọng số sort nhưng khác identity.
11. **Stability:** key không bị sửa phần tham gia hash/equality sau khi được đưa vào collection.
12. **Array/null fields:** so sánh đúng kiểu dữ liệu, tránh NPE, dùng `Arrays.equals` hoặc `Objects.equals` khi cần.
13. **Stream:** `distinct()`/`Collectors.toSet()` cho số phần tử logic hợp lý; không phụ thuộc thứ tự Set.
14. **Hiệu năng:** nếu nhiều hash collision, vẫn đúng kết quả nhưng có thể chậm; tối ưu hash sau khi xác nhận correctness.

Ví dụ các kiểm tra cơ bản (minh họa, sử dụng lớp `ProductKey` ở mục 4):

~~~java
ProductKey a = new ProductKey("A", "VN");
ProductKey b = new ProductKey("A", "VN");
ProductKey c = new ProductKey("A", "VN");

assert a.equals(a);
assert a.equals(b) && b.equals(a);
assert !(a.equals(b) && b.equals(c)) || a.equals(c);
assert !a.equals(null);
assert !a.equals(b) || a.hashCode() == b.hashCode();
~~~

**Lưu ý:** Java `assert` chỉ chạy khi bật assertion, ví dụ `java -ea ClassName`; trong kiểm thử tự động thực tế, dùng framework test hiện hành và assertions có thông báo rõ ràng. Không dựa vào `assert` bị tắt mặc định để kiểm tra input nghiệp vụ ở production.

## 14. Cách chọn collection theo equality và ordering

| Yêu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Giữ mọi phần tử, kể cả trùng, và bảo toàn vị trí | `List` |
| Chỉ lưu phần tử khác nhau theo `equals`; không cần thứ tự | `HashSet` |
| Loại trùng theo `equals` và duyệt theo thứ tự thêm | `LinkedHashSet` |
| Set sắp xếp theo natural order/comparator | `TreeSet`; bảo đảm comparator consistent with equals |
| Ánh xạ theo khóa logic, không yêu cầu thứ tự | `HashMap` với key ổn định |
| Ánh xạ theo thứ tự chèn | `LinkedHashMap` |
| Map theo thứ tự khóa | `TreeMap` với comparator nhất quán với equals |
| Khóa/phần tử thuộc enum | `EnumMap` / `EnumSet` nếu phù hợp |
| List loại trùng nhưng giữ phần tử đầu tiên của ordered stream | `stream.distinct().collect(toList())` |

Không có collection nào sửa được một chiến lược equality sai. **Chọn đúng cách định nghĩa bằng nhau trước, chọn cấu trúc lưu trữ sau.**

## 15. Tổng kết

- `equals(Object)` định nghĩa **bằng nhau logic**, phải phản xạ, đối xứng, bắc cầu, nhất quán và trả false với null.
- `hashCode()` phải **giống nhau cho hai object bằng nhau**; collision giữa object không bằng nhau là hợp lệ.
- `HashSet` và `HashMap` phụ thuộc hợp đồng này để nhận biết phần tử/khóa trùng; **đã override equals, phải override hashCode tương thích**.
- `List` cho phép trùng lặp và so equality theo **vị trí**; `Set` so equality theo thành viên, không dựa vào thứ tự.
- `TreeSet`/`TreeMap` phân biệt khóa/giá trị qua `compareTo` hoặc `Comparator`, nên cần ordering consistent with equals để thỏa hợp đồng Set/Map.
- **Không sửa trường tham gia equals/hashCode khi object là phần tử của hash Set hoặc key của hash Map**.
- `Stream.distinct` và `Collectors.toSet` cũng chịu ảnh hưởng định nghĩa equality của object.
- Ưu tiên value object ổn định, test hợp đồng và sử dụng `Objects.equals`/`Objects.hash`, `Arrays.equals`/`Arrays.hashCode` phù hợp.
- Những quy tắc trên vẫn áp dụng cho Java 8 và các JDK hiện nay; record là một tùy chọn Java 16+ khi mô hình value object phù hợp, không phải thay thế cho việc hiểu hợp đồng.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Object: equals và hashCode](https://docs.oracle.com/javase/8/docs/api/java/lang/Object.html)
- [Oracle Java SE 25 — Object](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html)
- [Oracle Java SE 25 — Set và HashSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html)
- [Oracle Java SE 25 — Map và HashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html)
- [Oracle Java SE 25 — TreeSet: yêu cầu ordering nhất quán với equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html)
- [Oracle Java SE 25 — Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 25 — BigDecimal: equals khác compareTo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html)
- [Oracle Java SE 25 — Stream.distinct](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
