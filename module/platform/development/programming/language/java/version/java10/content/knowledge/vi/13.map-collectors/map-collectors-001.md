# `Collectors.toUnmodifiableMap` với hàm tạo khóa và giá trị (Java 10+)

## 1. Mục tiêu bài học

Từ **Java 10**, `java.util.stream.Collectors` cung cấp phương thức `toUnmodifiableMap(keyMapper, valueMapper)` để thu thập các phần tử của một `Stream<T>` thành một **`Map<K,V>` không cho thay đổi các ánh xạ** (*unmodifiable map*).

Điểm cốt lõi là bạn phải chỉ định **hai hàm ánh xạ**:

- **`keyMapper`**: nhận mỗi phần tử đầu vào và tạo **khóa** `K` của map.
- **`valueMapper`**: nhận cùng phần tử đầu vào và tạo **giá trị** `V` của map.

Ví dụ, từ các sản phẩm có mã và tên, ta tạo một bản đồ tra tên theo mã:

~~~java
Map<Integer, String> namesById = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId,
                Product::getName
        ));
~~~

Đây là đoạn minh họa trong phương thức, giả sử `Product` có `getId()`, `getName()`, `products` là một `List<Product>`, và đã import `java.util.Map`, `java.util.stream.Collectors`. Một chương trình hoàn chỉnh nằm ở mục 9.

**Hợp đồng cần nắm:**
1. Mỗi phần tử của stream cung cấp một cặp `keyMapper(element)` → `valueMapper(element)`.
2. Nếu **hai phần tử tạo ra khóa bằng nhau** theo `equals()`, overload **hai tham số** ném `IllegalStateException`; nó không âm thầm ghi đè.
3. Nếu `keyMapper` hoặc `valueMapper` trả về `null`, collector ném `NullPointerException`.
4. Kết quả là `Map` **unmodifiable**, không hỗ trợ `put`, `remove`, `replace` hay sửa mapping qua entry.
5. **Thứ tự duyệt map kết quả không được cam kết**; đừng dùng nó làm một danh sách có thứ tự.

Đây là kiến thức vẫn còn áp dụng trong các JDK hiện đại. Bài học dùng cú pháp tương thích JDK 17+, đồng thời chỉ rõ API `toUnmodifiableMap` được giới thiệu ở **Java 10**.

## 2. Cú pháp và các kiểu được suy luận

Chữ ký rút gọn của overload cơ bản:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper)
~~~

Ý nghĩa các tham số kiểu:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu phần tử đầu vào của `Stream<T>` | `Product` |
| `K` | Kiểu khóa do `keyMapper` tạo | `Integer` |
| `U` | Kiểu value do `valueMapper` tạo | `String` |
| `Collector<T, ?, Map<K,U>>` | Collector tạo map từ stream | `Collector<Product, ?, Map<Integer,String>>` |

Ví dụ:

~~~java
var namesById = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId,       // T -> K: Product -> Integer
                Product::getName      // T -> U: Product -> String
        ));
~~~

Khi `getId()` trả `int`, giá trị được boxing thành `Integer`, còn `getName()` trả `String`. Vì thế biến `namesById` được suy ra kiểu tĩnh **`Map<Integer,String>`**. `var` chỉ giúp bỏ khai báo kiểu ở vế trái; nó **không** làm map trở thành kiểu động.

Nếu yêu cầu kiểu ở nơi khai báo phải thật rõ, có thể viết:

~~~java
Map<Integer, String> namesById = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId, Product::getName));
~~~

Cả hai cách đều hợp lệ và tạo ra cùng loại hợp đồng map unmodifiable.

## 3. Hai hàm mapper được áp dụng như thế nào?

Giả sử stream gồm ba sản phẩm:

| Mã `id` | Tên `name` | Giá `price` |
| --- | --- | --- |
| 101 | Paper | 20 |
| 102 | Pencil | 8 |
| 103 | Bag | 60 |

Nếu viết:

~~~java
var names = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId,
                Product::getName
        ));
~~~

Đầu ra theo **quan hệ khóa–giá trị** là:

~~~text
101 -> Paper
102 -> Pencil
103 -> Bag
~~~

Đây là mô tả quan hệ, **không phải** cam kết rằng `names.toString()` hoặc `entrySet()` sẽ hiển thị theo thứ tự trên. Tra cứu bằng `names.get(101)` trả `"Paper"` và `names.get(103)` trả `"Bag"`.

`valueMapper` không nhất thiết chỉ là getter. Nó có thể tính ra giá trị mới:

~~~java
var doublePrices = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId,
                p -> p.getPrice() * 2
        ));

System.out.println(doublePrices.get(103)); // 120
~~~

`p -> p.getPrice() * 2` tạo một `Integer` từ giá nguyên thủy `int`, nên kiểu map là `Map<Integer,Integer>`.

`keyMapper` cũng có thể biến đổi dữ liệu, chẳng hạn chuẩn hóa email:

~~~java
var byEmail = users.stream()
        .collect(Collectors.toUnmodifiableMap(
                u -> u.getEmail().toLowerCase(Locale.ROOT),
                Function.identity()
        ));
~~~

Đây là **đoạn minh họa không độc lập**; `User` cần có `getEmail()`, cùng import `Locale` và `Function`. `Function.identity()` trả về chính đối tượng `User` làm value, còn email viết thường làm key. Việc chuẩn hóa key có thể **làm hai email khác cách viết trở thành một khóa trùng**; overload hai tham số sẽ phát hiện bằng ngoại lệ.

**Lời khuyên:** các mapper nên là hàm rõ ràng và không tạo tác dụng phụ không cần thiết; collector có thể làm việc với parallel stream, nên đừng phụ thuộc vào thứ tự gọi mapper để sửa trạng thái bên ngoài.

## 4. Khóa trùng: `IllegalStateException` ở overload hai tham số

Mỗi khóa trong một map phải là duy nhất theo quy tắc `equals()`. Nếu hai phần tử khác nhau sinh ra cùng một khóa:

~~~java
var records = List.of(
        new Product(101, "Paper", 20),
        new Product(101, "Notebook", 30)
);

var names = records.stream().collect(
        Collectors.toUnmodifiableMap(
                Product::getId, Product::getName
        )
);
// Khi chạy: IllegalStateException do cả hai phần tử có khóa 101.
~~~

Mã trên là ví dụ **cố ý ném ngoại lệ**; không phải phần nằm trong ví dụ runnable của mục 9 mà không có `try/catch`.

Không có quy tắc “phần tử cuối ghi đè phần tử đầu” ở overload này. Bạn phải chủ động giải quyết xung đột bằng một trong các cách:
- **Bảo đảm khóa duy nhất** theo ràng buộc dữ liệu; khi trùng là dữ liệu sai, giữ overload hai tham số để phát hiện lỗi sớm.
- **Dùng overload ba tham số** với `mergeFunction` nếu nhiều phần tử cùng khóa là tình huống nghiệp vụ hợp lệ.
- **Dùng `groupingBy`** nếu mỗi khóa cần gắn với **danh sách tất cả phần tử**, thay vì chỉ một value.
- **Lọc/chọn trước khi collect** nếu chính sách nghiệp vụ yêu cầu loại bản ghi không đạt điều kiện.

Phải kiểm tra độ duy nhất của **giá trị keyMapper trả về**, không chỉ giá trị của đối tượng nguồn. Ví dụ, nếu keyMapper luôn trả `"constant"` thì mọi phần tử cùng dùng một khóa dù mã sản phẩm khác nhau.

## 5. Overload ba tham số: xử lý khóa trùng có chủ đích

Java 10 cũng có overload:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction)
~~~

`mergeFunction` kết hợp **hai giá trị `U` có cùng khóa** thành một giá trị đại diện.

Ví dụ gộp số lượng sản phẩm theo mã SKU:

~~~java
var lines = List.of(
        new LineItem("A", 2),
        new LineItem("A", 3),
        new LineItem("B", 4)
);

Map<String, Integer> quantities = lines.stream()
        .collect(Collectors.toUnmodifiableMap(
                LineItem::getSku,
                LineItem::getQuantity,
                Integer::sum
        ));

System.out.println(quantities.get("A")); // 5
System.out.println(quantities.get("B")); // 4
~~~

`LineItem` là kiểu minh họa với `getSku()` trả `String` và `getQuantity()` trả `int`; chương trình hoàn chỉnh ở mục 9 định nghĩa lớp này.

Giải thích từng hàm:
1. `keyMapper = LineItem::getSku` biến các dòng thành khóa `"A"`, `"A"`, `"B"`.
2. `valueMapper = LineItem::getQuantity` biến từng dòng thành `2`, `3`, `4`.
3. `mergeFunction = Integer::sum` gộp hai value của khóa `"A"` thành `5`.
4. Map cuối vẫn **unmodifiable**. Hàm merge chỉ xử lý xung đột **trong quá trình tạo map**, không mở quyền sửa map sau đó.

Trong pipeline song song, hàm merge nên có tính kết hợp (*associative*) phù hợp với phép gom kết quả; nếu kết quả cần độc lập với thứ tự xử lý, nên ưu tiên các phép gộp không phụ thuộc thứ tự như cộng số nguyên trong phạm vi không tràn. `Integer::sum` giúp trình bày ý tưởng rõ ràng; hãy cân nhắc khả năng tràn `int` đối với số lượng rất lớn.

### Khi nào không nên tự “chọn bản đầu hoặc cuối”?

Cách viết:

~~~java
(a, b) -> a
~~~

cho phép giữ một value khi trùng khóa. Nhưng nếu bạn cần “bản đầu theo thứ tự dữ liệu nghiệp vụ”, phải định nghĩa rõ trình tự và cách dữ liệu được xử lý. Tránh dùng chính sách giữ bản đầu/đến sau một cách tùy tiện với parallel/unordered stream. Cách chắc chắn hơn có thể là **sắp xếp hoặc chọn bản ghi mong muốn trước khi collect** bằng một tiêu chí xác định.

**Lưu ý:** overload `toUnmodifiableMap` chỉ có dạng hai và ba tham số. Không có overload bốn tham số nhận `mapFactory` để chọn `LinkedHashMap`. Nếu cần map có thứ tự hoặc một implementation cụ thể, hãy dùng collector phù hợp như `toMap(..., mergeFunction, mapFactory)` và sau đó quyết định cách công bố unmodifiable map; bản thân `Map.copyOf` không cam kết giữ thứ tự duyệt nguồn.

## 6. `null` ở keyMapper và valueMapper bị từ chối

Cả hai overload của `toUnmodifiableMap` **không cho khóa hoặc value là `null`**.

Nếu một mapper trả `null`, thao tác `collect` ném `NullPointerException`. Điều này khác với việc một số implementation mutable như `HashMap` có thể cho phép key/value `null`.

Ví dụ:

~~~java
var products = List.of(new Product(201, null, 5));

products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId,
                Product::getName
        ));
// Ném NullPointerException vì valueMapper trả null.
~~~

Đây là ví dụ **cố ý gây lỗi**, không phải code chạy thành công khi bỏ vào `main` mà không có `try/catch`.

Nếu **khóa** trả `null`, kết quả cũng là `NullPointerException`. Điều kiện này nên được xử lý trong thiết kế dữ liệu:
- Nếu bản ghi thiếu key/value là **không hợp lệ**, kiểm tra hoặc từ chối rõ trước khi tạo map.
- Nếu muốn loại bản ghi thiếu dữ liệu, dùng `filter` **trước** `collect`, chỉ khi nghiệp vụ cho phép bỏ chúng.
- Nếu cần thay giá trị `null` bằng một giá trị mặc định có nghĩa, dùng mapper với default **không null**, ví dụ `p -> Objects.requireNonNullElse(p.getName(), "Unknown")`. Phương thức `Objects.requireNonNullElse` được hỗ trợ từ Java 9.
- Không thay `null` bằng chuỗi rỗng hay sentinel một cách âm thầm nếu điều đó làm sai hợp đồng dữ liệu.

Để lọc đúng:

~~~java
var safeNames = products.stream()
        .filter(p -> p.getName() != null)
        .collect(Collectors.toUnmodifiableMap(
                Product::getId, Product::getName));
~~~

Khi lọc, hãy nhớ còn có thể tồn tại **khóa trùng** giữa các phần tử đã lọc; `filter` phần tử null không tự giải quyết mọi xung đột.

## 7. Unmodifiable map khác với immutable object bên trong

Map trả về không hỗ trợ sửa **các ánh xạ**:

~~~java
var names = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::getId, Product::getName));

// names.put(104, "Ruler"); // Ném UnsupportedOperationException.
// names.remove(101);       // Ném UnsupportedOperationException.
// names.replace(101,"Other"); // Ném UnsupportedOperationException.
~~~

Cú pháp lời gọi vẫn hợp lệ theo interface `Map`; implementation trả về không hỗ trợ thay đổi. Các entry qua `names.entrySet()` cũng không thể dùng `setValue` để phá vỡ hợp đồng unmodifiable.

Tuy nhiên, map unmodifiable **không có nghĩa object key/value được deep-copy hoặc đóng băng**.

Ví dụ:

~~~java
var box = new MutableBox(5);

Map<Integer, MutableBox> byId = Stream.of(box)
        .collect(Collectors.toUnmodifiableMap(
                value -> 7,
                Function.identity()
        ));

box.add(2);
System.out.println(byId.get(7).get()); // 7
~~~

Đây là đoạn minh họa; `MutableBox` có phương thức `add(int)`, `get()`, và chương trình đầy đủ ở mục 9 định nghĩa nó. Map không thay mapping `7 -> box`; chỉ có **trạng thái bên trong `box` thay đổi**, nên cách đọc qua map thấy giá trị mới.

**Hệ quả thiết kế:**
- Nếu muốn snapshot độc lập, dùng immutable value objects hoặc sao chép phần trạng thái mutable trước khi collect.
- Nếu dùng object mutable làm **key**, việc đổi field tham gia `equals()` hoặc `hashCode()` sau khi tạo map có thể làm kết quả tra cứu không còn đáng tin. Nên dùng key bất biến.
- Unmodifiable map không tự tạo thread safety cho toàn bộ object graph; dữ liệu mutable được chia sẻ vẫn cần cơ chế phối hợp phù hợp.

Với giá trị `String`, `Integer` bất biến như ví dụ sản phẩm, việc chia sẻ tham chiếu value thường an toàn vì không thể đổi trạng thái của chính object đó.

## 8. So sánh `toUnmodifiableMap`, `toMap`, `Map.copyOf` và `groupingBy`

| Nhu cầu | Công cụ phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| Thu thập một stream thành map **không cho sửa**, key/value không null | `Collectors.toUnmodifiableMap(keyMapper, valueMapper)` | Khóa trùng ném `IllegalStateException` |
| Thu thập thành unmodifiable map nhưng có khóa trùng hợp lệ | `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` | Gộp value theo chính sách đã định |
| Cần kiểm soát implementation map mutable, chẳng hạn `LinkedHashMap` | `Collectors.toMap(keyMapper, valueMapper, merge, LinkedHashMap::new)` | Có thể xác định mapFactory; không dùng `toUnmodifiableMap` 4 tham số vì không có |
| Đã có `Map<K,V>` và muốn bản chụp không cho sửa mappings | `Map.copyOf(existingMap)` | Java 10+; không tự deep-copy value |
| Một khóa phải có **danh sách nhiều giá trị** | `Collectors.groupingBy(keyMapper, ...)` | Không ép dữ liệu 1–n thành map 1–1 bằng cách làm mất giá trị |
| Muốn view không cho sửa nhưng luôn phản ánh map nguồn | `Collections.unmodifiableMap(source)` | Là view, khác snapshot |

**Không nên khẳng định `Collectors.toMap` luôn trả một `HashMap` mutable** như một lời hứa API: tài liệu overload phổ thông không bảo đảm implementation hoặc mutability cụ thể. Nếu cần biết chắc map là mutable `LinkedHashMap`, hãy dùng overload có **supplier** như trong bảng.

`Map.copyOf(existingMap)` tạo map unmodifiable từ một map đã tồn tại; `toUnmodifiableMap` làm việc **trực tiếp trong quá trình thu thập Stream**. Chúng là hai đường đi tới map không cho sửa, nhưng điểm lấy dữ liệu đầu vào khác nhau.

## 9. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **ToUnmodifiableMapDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ToUnmodifiableMapDemo {
    static final class Product {
        private final int id;
        private final String name;
        private final int price;

        Product(int id, String name, int price) {
            this.id = id;
            this.name = name;
            this.price = price;
        }

        int getId() {
            return id;
        }

        String getName() {
            return name;
        }

        int getPrice() {
            return price;
        }
    }

    static final class LineItem {
        private final String sku;
        private final int quantity;

        LineItem(String sku, int quantity) {
            this.sku = sku;
            this.quantity = quantity;
        }

        String getSku() {
            return sku;
        }

        int getQuantity() {
            return quantity;
        }
    }

    static final class MutableBox {
        private int count;

        MutableBox(int count) {
            this.count = count;
        }

        void add(int extra) {
            count += extra;
        }

        int get() {
            return count;
        }
    }

    public static void main(String[] args) {
        var products = List.of(
                new Product(101, "Paper", 20),
                new Product(102, "Pencil", 8),
                new Product(103, "Bag", 60)
        );

        // Mỗi Product tạo một cặp ID -> name.
        Map<Integer, String> names = products.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Product::getId, Product::getName));
        System.out.println("names size = " + names.size());
        System.out.println("name 101 = " + names.get(101));

        // valueMapper tính ra giá mới.
        var doubledPrices = products.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Product::getId,
                        p -> p.getPrice() * 2));
        System.out.println("price 103 x2 = " + doubledPrices.get(103));

        // Không thể cập nhật mapping của map kết quả.
        try {
            names.put(104, "Ruler");
        } catch (UnsupportedOperationException ex) {
            System.out.println("map update = blocked");
        }

        // Cũng không thể cập nhật value qua Map.Entry.
        var entry = names.entrySet().iterator().next();
        try {
            entry.setValue("Changed");
        } catch (UnsupportedOperationException ex) {
            System.out.println("entry update = blocked");
        }

        // Hai Product có cùng id -> lỗi với overload hai tham số.
        var duplicates = List.of(
                new Product(101, "Paper", 20),
                new Product(101, "Notebook", 30)
        );
        try {
            duplicates.stream().collect(
                    Collectors.toUnmodifiableMap(
                            Product::getId, Product::getName));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate key = rejected");
        }

        // Overload ba tham số gộp value khi khóa trùng.
        var merged = duplicates.stream().collect(
                Collectors.toUnmodifiableMap(
                        Product::getId,
                        Product::getName,
                        (left, right) -> left + " / " + right));
        System.out.println("merged 101 = " + merged.get(101));

        var lines = List.of(
                new LineItem("A", 2),
                new LineItem("A", 3),
                new LineItem("B", 4)
        );
        var quantities = lines.stream().collect(
                Collectors.toUnmodifiableMap(
                        LineItem::getSku,
                        LineItem::getQuantity,
                        Integer::sum));
        System.out.println("quantity A = " + quantities.get("A"));
        System.out.println("quantity B = " + quantities.get("B"));

        // null value bị từ chối.
        var missingName = List.of(new Product(201, null, 5));
        try {
            missingName.stream().collect(
                    Collectors.toUnmodifiableMap(
                            Product::getId, Product::getName));
        } catch (NullPointerException ex) {
            System.out.println("null value = rejected");
        }

        // null key cũng bị từ chối.
        try {
            Stream.of("item").collect(
                    Collectors.toUnmodifiableMap(
                            value -> (String) null,
                            Function.identity()));
        } catch (NullPointerException ex) {
            System.out.println("null key = rejected");
        }

        // Stream được thu thập một lần; thêm nguồn sau đó
        // không làm thay đổi map kết quả.
        var mutableSource = new ArrayList<>(products);
        var snapshot = mutableSource.stream().collect(
                Collectors.toUnmodifiableMap(
                        Product::getId, Product::getName));
        mutableSource.add(new Product(104, "Ruler", 5));
        System.out.println("source size after add = " + mutableSource.size());
        System.out.println("snapshot size after add = " + snapshot.size());

        // Unmodifiable mappings không làm value mutable bất biến.
        var box = new MutableBox(5);
        var boxes = Stream.of(box).collect(
                Collectors.toUnmodifiableMap(
                        value -> 7,
                        Function.identity()));
        box.add(2);
        System.out.println("mutable value via map = " + boxes.get(7).get());
    }
}
~~~

Chạy trong thư mục chứa tệp với **JDK 17 trở lên**:

~~~bash
javac ToUnmodifiableMapDemo.java
java ToUnmodifiableMapDemo
~~~

**Đầu ra chính xác:**

~~~text
names size = 3
name 101 = Paper
price 103 x2 = 120
map update = blocked
entry update = blocked
duplicate key = rejected
merged 101 = Paper / Notebook
quantity A = 5
quantity B = 4
null value = rejected
null key = rejected
source size after add = 4
snapshot size after add = 3
mutable value via map = 7
~~~

### Giải thích đầu ra

1. `names` có ba cặp vì mỗi `Product` tạo một khóa `id` riêng.
2. `doubledPrices` sử dụng lambda trong `valueMapper` để tính giá `120` cho sản phẩm có mã `103`.
3. `names.put` và `entry.setValue` đều bị từ chối bằng `UnsupportedOperationException`. Đây là **hành vi lúc chạy**, không phải lỗi cú pháp Java.
4. Hai sản phẩm cùng mã `101` làm overload hai tham số ném `IllegalStateException`.
5. Overload ba tham số gộp hai tên thành `"Paper / Notebook"` trong **sequential stream có thứ tự**; ví dụ chỉ tra khóa `101`, không dựa vào thứ tự duyệt map.
6. `Integer::sum` gộp hai số lượng của SKU `"A"` thành `5`.
7. `null` từ keyMapper hoặc valueMapper đều bị từ chối.
8. Việc thêm phần tử mới vào `mutableSource` sau khi `collect` hoàn tất không tự cập nhật snapshot đã tạo.
9. `MutableBox` là object mutable; map giữ tham chiếu đến nó, nên đọc qua map thấy giá trị `7` sau khi `box.add(2)`.

Chương trình không có logic phụ thuộc vào thứ tự `entrySet()`: entry lấy đầu tiên chỉ được dùng để kiểm tra rằng **mọi entry của map không cho sửa** đều từ chối `setValue`. Tên sản phẩm và SKU được lấy theo **khóa xác định**, nên stdout có thể kiểm chứng ổn định.

## 10. Các lỗi thường gặp khi sử dụng trong dự án

### Lỗi 1 — Nhầm `keyMapper` với `valueMapper`

~~~java
Collectors.toUnmodifiableMap(
        Product::getName,
        Product::getId
)
~~~

Cách này tạo **`Map<String,Integer>`** (tên → mã), không phải **`Map<Integer,String>`** (mã → tên). Cú pháp có thể hợp lệ nhưng thiết kế tra cứu sai hướng.

**Cách khắc phục:** xác định trước câu hỏi “tra cứu bằng khóa gì?” rồi mới quyết định `keyMapper`. Đặt tên biến theo ý nghĩa, ví dụ `nameById` hoặc `idByName`.

### Lỗi 2 — Cho rằng key trùng sẽ tự ghi đè

Overload hai tham số **ném `IllegalStateException`** khi có hai khóa bằng nhau theo `equals`. Nếu muốn gộp, dùng overload có `mergeFunction`; nếu muốn một value cho nhiều bản ghi, cân nhắc `groupingBy`.

### Lỗi 3 — Cho rằng map không cho sửa thì các object bên trong cũng bất biến

Map unmodifiable ngăn thay **mapping**. Nếu value là một object mutable, code vẫn có thể sửa object đó qua tham chiếu. Khi công bố dữ liệu ra ngoài, cân nhắc immutable DTO hoặc defensive copy.

### Lỗi 4 — Cho rằng phép `collect` không bao giờ ném lỗi vì nguồn là `List`

Nguồn có thể chứa object hợp lệ nhưng mapper lại trả **`null`**; hoặc các object khác nhau có cùng key sau chuẩn hóa. Hai trường hợp này gây ngoại lệ ngay tại terminal operation `collect`.

### Lỗi 5 — In trực tiếp map và giả định thứ tự

`toUnmodifiableMap` không cam kết thứ tự duyệt. Khi cần output deterministic, hãy **sắp xếp khóa** để hiển thị, hoặc dùng một cấu trúc dữ liệu có hợp đồng thứ tự phù hợp.

### Lỗi 6 — Dùng `toUnmodifiableMap(...)` rồi gọi `put` ở bước kế tiếp

Nếu quy trình cần tiếp tục chỉnh sửa mappings, hãy thu thập vào một map mutable được kiểm soát trước, sau đó mới tạo snapshot unmodifiable ở ranh giới công bố.

Ví dụ dùng map mutable có implementation xác định:

~~~java
var editable = products.stream().collect(
        Collectors.toMap(
                Product::getId,
                Product::getName,
                (existing, incoming) -> incoming,
                LinkedHashMap::new
        ));

editable.put(104, "Ruler");
var published = Map.copyOf(editable);
~~~

Đoạn minh họa này cần import `LinkedHashMap` và `Map`. `editable` có thể chỉnh sửa vì supplier tạo `LinkedHashMap`. `published` là map unmodifiable theo API Java 10; đừng dựa vào việc nó giữ thứ tự của `LinkedHashMap`.

### Lỗi 7 — Cố sử dụng API Java 10 trên môi trường Java 8

`Collectors.toUnmodifiableMap` **không tồn tại ở Java 8**, dù Stream và `Collectors.toMap` đã có. Khi project đặt `--release 8`, mã này không biên dịch. Nếu dùng Java 10+, API được hỗ trợ; ví dụ bài dùng JDK 17+.

### Lỗi 8 — Hiểu nhầm `Function.identity()`

`Function.identity()` trả về **chính phần tử đầu vào**, không sao chép phần tử. Nếu dùng:

~~~java
var productsById = products.stream().collect(
        Collectors.toUnmodifiableMap(
                Product::getId,
                Function.identity()
        ));
~~~

Value là object `Product`, kiểu kết quả là **`Map<Integer, Product>`**. Nếu `Product` mutable thì map có thể chia sẻ object mutable với nguồn; bản thân `Function.identity()` không thực hiện defensive copy.

## 11. Câu hỏi tự kiểm tra

**1. `Collectors.toUnmodifiableMap(Product::getId, Product::getName)` tạo khóa và value từ đâu?**  
`getId()` là **keyMapper**, `getName()` là **valueMapper**. Mỗi sản phẩm tạo một cặp mã → tên.

**2. Nếu `getId()` của hai sản phẩm trả cùng `101`, overload hai tham số sẽ làm gì?**  
Ném `IllegalStateException` trong quá trình `collect` vì khóa trùng theo `equals`.

**3. Nếu muốn cộng số lượng nhiều dòng có cùng SKU thì dùng overload nào?**  
Dùng `Collectors.toUnmodifiableMap(LineItem::getSku, LineItem::getQuantity, Integer::sum)` — overload **ba tham số**.

**4. Nếu `getName()` trả `null`, map kết quả có chứa `101 -> null` không?**  
Không. `toUnmodifiableMap` không chấp nhận `null` key hoặc value và sẽ ném `NullPointerException`.

**5. Có thể gọi `put`, `replace`, hoặc `entry.setValue` để sửa map kết quả không?**  
Không. Map kết quả là unmodifiable; thao tác sửa mapping bị từ chối bằng `UnsupportedOperationException`.

**6. Dùng `Function.identity()` làm valueMapper thì value là gì?**  
Chính phần tử của stream, ví dụ `Product`; nó không tự tạo bản sao.

**7. Lời gọi này có bảo đảm map duyệt theo thứ tự `products` không?**

~~~java
products.stream().collect(
        Collectors.toUnmodifiableMap(
                Product::getId, Product::getName))
~~~

Không. Thứ tự duyệt map không được `toUnmodifiableMap` cam kết.

**8. `Collectors.toMap` và `Collectors.toUnmodifiableMap` khác nhau cơ bản ở đâu?**  
`toUnmodifiableMap` cam kết map trả về không cho sửa. Các overload `toMap` phổ thông không cam kết loại map hoặc mutability cụ thể; có overload `toMap` với `mapFactory` nếu cần điều khiển implementation.

**9. `List<Product>` nguồn thêm sản phẩm sau khi `collect` hoàn tất thì map kết quả có tự cập nhật không?**  
Không. Collector đã hoàn thành phép thu thập. Nhưng nếu value là một object mutable được chia sẻ, sửa state object ấy có thể quan sát qua map.

**10. Khi nào nên dùng `groupingBy` thay `toUnmodifiableMap`?**  
Khi một khóa cần giữ **nhiều phần tử**, thay vì một value duy nhất hoặc value đã gộp. `groupingBy` thể hiện quan hệ một–nhiều rõ hơn.

## 12. Ghi nhớ cuối bài

- `toUnmodifiableMap(keyMapper, valueMapper)` là **Collector Java 10+** biến `Stream<T>` thành `Map<K,U>` không cho sửa mapping.
- `keyMapper` tạo **khóa**, `valueMapper` tạo **value**; kiểu map được suy luận từ kiểu trả về của hai hàm.
- Overload **hai tham số** không cho khóa trùng: `IllegalStateException`. Overload **ba tham số** dùng `mergeFunction` để giải quyết.
- Cả khóa và value **không được là `null`**; mapper trả `null` sẽ gây `NullPointerException`.
- Map kết quả **unmodifiable, không cam kết thứ tự duyệt, không deep-copy object key/value**.
- Chọn `toUnmodifiableMap` khi cần công bố một map một–một đã hoàn tất; dùng `groupingBy`, overload merge hoặc map mutable khi yêu cầu dữ liệu khác.

**Tài liệu Oracle chính thức:**
- [Java SE 10 — `Collectors.toUnmodifiableMap`](https://docs.oracle.com/javase/10/docs/api/java/util/stream/Collectors.html#toUnmodifiableMap-java.util.function.Function-java.util.function.Function-).
- [Java SE 17 — `Collectors`, cả hai overload `toUnmodifiableMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — Unmodifiable Maps và `Map.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
