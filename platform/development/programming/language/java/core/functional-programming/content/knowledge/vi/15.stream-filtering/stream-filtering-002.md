# Stream.distinct() và ảnh hưởng của equals(), hashCode() trong Java

`distinct()` là **intermediate operation** của Java Stream API dùng để loại các phần tử **trùng nhau** và chỉ giữ các phần tử phân biệt theo quan hệ bằng nhau của đối tượng. Nó thường xuất hiện trong pipeline như `stream().distinct().toList()`, nhưng kết quả không đơn giản là “bỏ các object có cùng dữ liệu hiển thị”: Java dựa vào **`equals()`** để xác định bằng nhau theo hợp đồng của kiểu phần tử. Việc cài đặt đúng **`hashCode()`** là yếu tố thiết yếu để các cấu trúc dựa trên hash có thể phân nhóm và tìm kiếm đối tượng nhất quán, bao gồm cách triển khai phổ biến của `distinct()`.

Ví dụ, với `List.of("Java", "Java", "Kotlin")`, hai chuỗi `"Java"` bằng nhau theo `String.equals()`, nên `distinct()` chỉ giữ một. Ngược lại, hai instance của class thường **không tự trở nên bằng nhau chỉ vì mọi field có cùng giá trị**; nếu class không override `equals()`, nó thường kế thừa so sánh identity từ `Object`.

Bài học này giải thích cơ chế, tính ổn định thứ tự, hợp đồng `equals`/`hashCode`, so sánh với `record`, cách loại trùng theo một khóa nghiệp vụ, và các sai lầm cần tránh khi chạy Stream tuần tự hoặc song song. Ví dụ sử dụng Java 17+.

## 1. Cú pháp, vai trò và thời điểm thực thi

Với `Stream<T>`, cú pháp cơ bản là:

```java
Stream<T> uniqueStream = sourceStream.distinct();
```

Đây là **mẫu cú pháp**; `sourceStream` phải là một `Stream<T>` đã có trong ngữ cảnh. `distinct()` trả về **một Stream mới** và không tự sửa collection nguồn.

Trong pipeline đầy đủ:

```java
List<String> unique = List.of("A", "B", "A", "C", "B")
        .stream()
        .distinct()
        .toList();
// [A, B, C]
```

Đoạn trên là mảnh mã cần `import java.util.List;` và đặt trong phương thức. `distinct()` là **stateful intermediate operation**: để xác định phần tử đã thấy hay chưa, pipeline phải có trạng thái đủ để nhận biết các phần tử trước đó (chi tiết triển khai do JDK quyết định). Nó là **lazy**: việc tạo pipeline không đồng nghĩa toàn bộ danh sách đã được duyệt; terminal operation `toList()` kích hoạt xử lý.

Không nên kỳ vọng `distinct()` xóa hay cập nhật phần tử trong `List` gốc. Stream mới có thể chứa ít phần tử hơn, nhưng nguồn ban đầu không bị `distinct()` sửa đổi.

## 2. “Trùng nhau” nghĩa là gì?

Hợp đồng Stream API quy định phần tử phân biệt **theo `Object.equals(Object)`**. Trong các ví dụ thường gặp:

| Kiểu phần tử | Quy tắc so sánh mặc định hoặc phổ biến | Ảnh hưởng đến distinct |
| --- | --- | --- |
| `String` | So sánh nội dung, phân biệt hoa/thường | `"Java"` và `"Java"` trùng, `"Java"` và `"java"` khác |
| `Integer` | So sánh giá trị số được bọc | Hai `Integer` cùng giá trị được coi là trùng |
| `record` | `equals` và `hashCode` tự sinh dựa trên các component | Các record cùng kiểu có component bằng nhau được coi là trùng |
| Class thường không override `equals` | Kế thừa `Object.equals`, thường là cùng reference | Hai instance khác nhau không tự trùng, dù field bằng nhau |
| Class override `equals` đúng hợp đồng | Quan hệ bằng nhau do class định nghĩa | Có thể loại trùng theo ID, mã, hoặc quy tắc nghiệp vụ |
| Mảng, ví dụ `int[]` | `Object.equals` theo reference, không tự so sánh phần tử | Hai mảng khác nhau nhưng cùng nội dung vẫn là hai phần tử phân biệt |

**Phân biệt equality với identity:** biểu thức `a == b` kiểm tra cùng reference đối với object; `a.equals(b)` kiểm tra equality do class định nghĩa. `distinct()` theo **equality**, không phải phép `==` tự viết.

`distinct()` cũng không tự phân biệt “trùng theo mã sản phẩm” và “trùng theo tất cả thuộc tính”. Quy tắc đó phải được đưa vào `equals` của kiểu phần tử hoặc biểu diễn bằng một khóa rõ ràng trong pipeline.

## 3. Chương trình Java 17: String, null và chuẩn hóa dữ liệu

Lưu thành **`DistinctBasicsDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public class DistinctBasicsDemo {
    public static void main(String[] args) {
        List<String> languages =
                List.of("Java", "Kotlin", "Java", "java", "Kotlin");

        System.out.println("unique=" + languages.stream()
                .distinct()
                .toList());

        System.out.println("normalized=" + languages.stream()
                .map(s -> s.toLowerCase(Locale.ROOT))
                .distinct()
                .toList());

        // Stream.of có thể chứa null; List.of không chấp nhận null.
        List<String> withNulls =
                Stream.of("A", null, "A", null, "B")
                        .distinct()
                        .toList();

        System.out.println("withNulls=" + withNulls);
        System.out.println("sourceSize=" + languages.size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DistinctBasicsDemo.java
java DistinctBasicsDemo
```

**Stdout chính xác:**

```text
unique=[Java, Kotlin, java]
normalized=[java, kotlin]
withNulls=[A, null, B]
sourceSize=5
```

Giải thích:

1. `String.equals` phân biệt chữ hoa/thường, nên `"Java"` và `"java"` không bằng nhau. Lần xuất hiện thứ hai của `"Java"` và `"Kotlin"` bị loại.
2. `map(s -> s.toLowerCase(Locale.ROOT))` tạo chuỗi chuẩn hóa **trước** khi distinct, nên `"Java"` và `"java"` cùng trở thành `"java"`.
3. Stream này có nguồn có thứ tự; `distinct()` giữ **phần tử gặp đầu tiên** trong từng nhóm bằng nhau. `null` được giữ tối đa một lần; `Stream.toList()` hỗ trợ `null` trong danh sách kết quả, trong khi `List.of(..., null, ...)` ném `NullPointerException`.
4. `languages` vẫn có 5 phần tử. `distinct()` không sửa nguồn.

Đừng mặc định mọi pipeline xử lý `null` an toàn. Nếu đặt `.map(String::toLowerCase)` trước khi lọc `null`, phép gọi instance method có thể ném `NullPointerException`. Khi dữ liệu nullable và cần chuẩn hóa, hãy dùng `.filter(Objects::nonNull)` trước khi gọi phương thức trên chuỗi.

## 4. Quy tắc equals(): quyết định hai object có bằng nhau không

`Object.equals(Object other)` có hợp đồng cơ bản:

- **Reflexive:** nếu `x` không null thì `x.equals(x)` là true.
- **Symmetric:** `x.equals(y)` và `y.equals(x)` phải có cùng kết quả.
- **Transitive:** nếu `x.equals(y)` và `y.equals(z)` đều true, thì `x.equals(z)` phải true.
- **Consistent:** khi dữ liệu liên quan không đổi, kết quả so sánh cần nhất quán.
- **Non-null:** `x.equals(null)` phải false với `x` không null.

Đối với class thường, nếu không override, `Object.equals` về cơ bản so sánh **cùng object**. Nếu muốn nhận diện hai entity trùng nhau theo `id`, cần định nghĩa quy tắc equality tương ứng.

Ví dụ một class có hai object cùng `id` nhưng khác `name`: nếu `equals` định nghĩa bằng `id`, `distinct()` sẽ chỉ giữ một trong nhóm. Nếu nghiệp vụ cần coi hai version khác nhau là khác nhau, quy tắc equality có thể cần cả các field liên quan hoặc một khóa version cụ thể.

**Không sửa nghĩa của `equals` trên domain object chỉ để đạt một pipeline đặc biệt.** Equality là hợp đồng toàn class và ảnh hưởng đến `HashSet`, `HashMap`, `contains` và các phần khác của ứng dụng. Khi cần dedup theo một khóa cục bộ, cân nhắc pipeline khác sử dụng key rõ ràng.

## 5. Hợp đồng hashCode(): tại sao phải đi cùng equals()?

`hashCode()` trả một số nguyên đại diện cho đối tượng theo hợp đồng hash. Quy tắc quan trọng nhất:

> **Nếu `a.equals(b)` là true thì `a.hashCode() == b.hashCode()` phải là true.**

Chiều ngược lại **không bắt buộc**: hai object có cùng hash code vẫn có thể khác nhau và `equals` có thể trả false. Hash collision là bình thường; một cấu trúc hash đúng phải kiểm tra equality để phân biệt những giá trị va chạm.

Vì sao điều này quan trọng? Nhiều cấu trúc tổ chức đối tượng theo hash trước, rồi dùng equals để xác nhận một object đã tồn tại. Nếu hai object **bằng nhau theo equals nhưng hashCode khác nhau**, chúng có thể bị đưa vào các vị trí khác nhau và bị xem sai như hai giá trị tách biệt. Một triển khai `distinct()` dựa trên tập hợp hash có thể bộc lộ hành vi không đúng ý định nếu class vi phạm hợp đồng này.

**Không nên suy luận Stream API cam kết dùng đúng một HashSet nội bộ:** chuẩn mô tả tính phân biệt bằng `equals`; thuật toán cụ thể và tối ưu hóa có thể khác giữa các phiên bản JDK hoặc pipeline. Trách nhiệm của người viết class là cung cấp `equals` và `hashCode` đúng hợp đồng.

Ngoài ra, giá trị tham gia `equals`/`hashCode` nên **ổn định trong quá trình đối tượng nằm trong cấu trúc hash**. Nếu sửa field dùng để tính hash sau khi object đã được đưa vào tập hợp, thao tác tìm kiếm và nhận diện trùng có thể trở nên sai lệch hoặc khó dự đoán.

## 6. Chương trình Java 17: class tự định nghĩa equality và record

Lưu thành **`DistinctDomainDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class DistinctDomainDemo {
    static final class Product {
        private final int id;
        private final String name;

        Product(int id, String name) {
            this.id = id;
            this.name = name;
        }

        String name() {
            return name;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Product product)) {
                return false;
            }
            return this.id == product.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record Book(String code, String title) {}

    static final class Plain {
        private final String name;

        Plain(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product(1, "Sách Java"),
                new Product(1, "Sách Java bản cập nhật"),
                new Product(2, "Sách Kotlin"),
                new Product(2, "Sách Kotlin bản cập nhật")
        );

        System.out.println("productNames=" + products.stream()
                .distinct()
                .map(Product::name)
                .toList());

        List<Book> books = List.of(
                new Book("B1", "First"),
                new Book("B1", "Second"),
                new Book("B1", "First")
        );

        System.out.println("books=" + books.stream()
                .distinct()
                .map(Book::title)
                .toList());

        List<Plain> plain = List.of(
                new Plain("X"),
                new Plain("X")
        );
        System.out.println("plainCount=" + plain.stream().distinct().count());

        System.out.println("productEquality="
                + products.get(0).equals(products.get(1)));
        System.out.println("sameHash="
                + (products.get(0).hashCode() == products.get(1).hashCode()));
    }
}
```

Biên dịch và chạy trên JDK 17:

```bash
javac -encoding UTF-8 DistinctDomainDemo.java
java DistinctDomainDemo
```

**Stdout chính xác:**

```text
productNames=[Sách Java, Sách Kotlin]
books=[First, Second]
plainCount=2
productEquality=true
sameHash=true
```

Giải thích:

1. `Product.equals` so sánh `id`, còn `hashCode` cũng dựa trên `id`. Hai sản phẩm cùng `id` được coi là bằng nhau dù `name` khác. Do nguồn là List có thứ tự, `distinct()` giữ bản ghi xuất hiện đầu tiên trong mỗi nhóm.
2. `Book` là `record`. Java tự sinh `equals` và `hashCode` dựa trên cả `code` và `title`; `Book("B1","First")` và `Book("B1","Second")` khác nhau, nhưng bản `"First"` lặp lại bị loại.
3. `Plain` không override `equals` nên hai `new Plain("X")` là hai object khác nhau; count sau distinct vẫn là 2.
4. Hai `Product` đầu tiên có cùng `id`; `equals` trả true và `hashCode` bằng nhau, đáp ứng hợp đồng bắt buộc.

Ví dụ trên lựa chọn equality theo ID **cho mục đích minh họa**. Một số domain object có yêu cầu về ID chưa được cấp, composite key hoặc vòng đời entity; hãy định nghĩa `equals`/`hashCode` theo hợp đồng nghiệp vụ thực tế.

## 7. Lỗi chỉ override equals mà quên hashCode

Mẫu class sau là **cảnh báo về thiết kế không đúng hợp đồng**, không dùng trong ứng dụng thực tế:

```java
class BrokenItem {
    private final int id;

    BrokenItem(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BrokenItem item && id == item.id;
    }

    // SAI: không override hashCode().
}
```

Hai instance `new BrokenItem(7)` có thể `equals` true nhưng thừa kế `Object.hashCode`, không được bảo đảm cùng mã hash. Đây là **vi phạm quy tắc bắt buộc**: object bằng nhau phải có hash bằng nhau.

Cách sửa tối thiểu:

```java
@Override
public int hashCode() {
    return Integer.hashCode(id);
}
```

Đây là **mảnh mã bổ sung bên trong class `BrokenItem`**, không phải phương thức top-level độc lập. Khi thiết kế equality theo nhiều field, có thể dùng `Objects.equals` và `Objects.hash` đúng tập field tương ứng. Trong trường hợp cần hiệu năng, có thể tính hash trực tiếp từ field; điều cốt lõi là **hai object bằng nhau phải có hash bằng nhau**.

**Không viết unit test trông chờ `distinct()` chắc chắn loại hoặc chắc chắn không loại một cặp object vi phạm hợp đồng.** Hành vi trong trường hợp broken equality/hash không phải cơ sở đúng để thiết kế API. Hãy sửa class trước, rồi kiểm thử `equals`, `hashCode`, `HashSet` và kết quả pipeline.

## 8. Encounter order: distinct có giữ phần tử nào?

Trên **ordered Stream**, `distinct()` là **stable**: nếu có nhiều phần tử bằng nhau, nó giữ phần tử **xuất hiện đầu tiên theo encounter order**. Ví dụ:

```java
List<String> values = List.of("B", "A", "B", "C", "A");
List<String> result = values.stream().distinct().toList();
// [B, A, C]
```

Đoạn minh họa cần `import java.util.List;`.

Với Stream song song nhưng vẫn **ordered**, tính ổn định này vẫn là yêu cầu về kết quả. Phần việc xử lý có thể diễn ra ngoài thứ tự trên các thread, nhưng kết quả của `distinct().toList()` vẫn giữ phần tử gặp đầu tiên và encounter order.

Với **unordered Stream**, API **không bảo đảm giữ bản xuất hiện đầu tiên** hoặc thứ tự kết quả, vì không có encounter order cần bảo toàn. `unordered()` chỉ loại bỏ ràng buộc thứ tự, không có nghĩa phần tử sẽ bị tráo một cách ngẫu nhiên trong mỗi lần chạy.

**Đặc biệt với các object cùng key nhưng dữ liệu khác:** nếu `Product.equals` dựa trên ID, việc giữ bản nào trong nhóm duplicate có thể mang ý nghĩa nghiệp vụ. Khi cần một “bản mới nhất” hoặc bản được ưu tiên, hãy định nghĩa quy tắc lựa chọn rõ ràng thay vì dựa vào thứ tự không được bảo đảm của unordered/parallel processing.

## 9. Chương trình Java 17: ordered, parallel và unordered

Lưu thành **`DistinctOrderDemo.java`**:

```java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class DistinctOrderDemo {
    public static void main(String[] args) {
        List<String> names = List.of("B", "A", "B", "C", "A", "D");

        List<String> sequential = names.stream()
                .distinct()
                .toList();

        List<String> parallel = names.parallelStream()
                .distinct()
                .toList();

        TreeSet<String> sortedDistinct = names.parallelStream()
                .unordered()
                .distinct()
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("unorderedAsSortedSet=" + sortedDistinct);
        System.out.println("uniqueCount=" + names.parallelStream()
                .distinct()
                .count());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DistinctOrderDemo.java
java DistinctOrderDemo
```

**Stdout chính xác:**

```text
sequential=[B, A, C, D]
parallel=[B, A, C, D]
unorderedAsSortedSet=[A, B, C, D]
uniqueCount=4
```

`sequential` và `parallel` đều bắt đầu từ List có encounter order nên giữ thứ tự lần xuất hiện đầu tiên. Với pipeline `unordered()`, chương trình **không giả định thứ tự do distinct trả về**; thay vào đó, `TreeSet` sắp xếp các chuỗi theo natural order để có đầu ra dự đoán được. Kết quả chỉ minh họa tập các giá trị khác nhau; không chứng minh unordered pipeline đã xử lý phần tử theo thứ tự nào.

Khi nguồn chứa object có equality phức tạp hoặc không có encounter order, không được lấy đầu ra của một lần chạy làm bảo đảm thứ tự cho lần chạy khác.

## 10. distinct() trên parallel Stream: đúng nhưng có thể tốn chi phí

`distinct()` là **stateful intermediate operation**. Trong parallel Stream **có thứ tự**, việc giữ bản đầu tiên của từng giá trị thường đòi hỏi phối hợp, lưu trạng thái hoặc buffering; các bước này có thể tạo overhead đáng kể so với pipeline không cần loại trùng.

Những điểm cần cân nhắc:

- **Nguồn dữ liệu:** List thường chia được theo index; nguồn khó chia có thể khiến parallel kém hiệu quả.
- **Số phần tử và tỷ lệ trùng:** dữ liệu lớn, phép xử lý nặng có thể có lợi, nhưng quản lý tập giá trị đã gặp cũng có chi phí.
- **Chi phí hashCode/equals:** việc tính hash hoặc so sánh phức tạp làm tăng chi phí.
- **Ràng buộc thứ tự:** ordered `distinct()` cần ổn định; nếu business không cần phần tử đầu tiên, `unordered()` có thể cho phép tối ưu.
- **Tính đúng đắn:** object mutable hoặc `equals`/`hashCode` không nhất quán gây nguy cơ kết quả sai; parallel không khắc phục được.
- **Tài nguyên:** tạo thêm task, lưu trạng thái, cấp phát và contention đều có thể ảnh hưởng.

Hãy **đo bằng benchmark phù hợp như JMH** trên dữ liệu thật trước khi tuyên bố parallel nhanh hơn. `parallelStream()` không tự bảo đảm dùng bao nhiêu thread, không bảo đảm tăng tốc và không phải giải pháp cho một thuật toán equality sai.

## 11. Loại trùng theo khóa nghiệp vụ mà không thay equals của class

Có lúc bạn muốn loại trùng theo `email` hoặc `productId`, trong khi equality tự nhiên của class dựa trên nhiều thuộc tính. Tránh sửa `equals` toàn class chỉ vì một phép lọc cục bộ.

### 11.1. Nếu chỉ cần danh sách khóa duy nhất

Giải pháp đơn giản, rõ nghĩa:

```java
List<String> uniqueCodes = products.stream()
        .map(Product::code)
        .distinct()
        .toList();
```

Đây là **mảnh mã minh họa**: `products` là nguồn có kiểu phù hợp và `Product::code` là accessor tồn tại trong ứng dụng. Nó trả về **khóa duy nhất**, không giữ toàn bộ object sản phẩm.

### 11.2. Nếu cần giữ object đầu tiên theo key

Với nguồn `List` có thứ tự, có thể dùng phép thu thập vào `LinkedHashMap` với quy tắc giữ giá trị đầu tiên:

```java
record Item(String code, String label) {}

List<Item> items = List.of(
        new Item("A", "First"),
        new Item("A", "Second"),
        new Item("B", "Third")
);

List<Item> uniqueByCode = new java.util.ArrayList<>(
        items.stream()
                .collect(java.util.stream.Collectors.toMap(
                        Item::code,
                        item -> item,
                        (first, later) -> first,
                        java.util.LinkedHashMap::new))
                .values()
);
// [Item[code=A, label=First], Item[code=B, label=Third]]
```

Đây là **mảnh mã đặt trong phương thức**, ngoại trừ khai báo `record Item` thuộc cấp top-level hoặc nested context của class. Cần `import java.util.List;`. `toMap` với merge function `(first, later) -> first` giải quyết các key trùng, còn `LinkedHashMap` duy trì thứ tự chèn của các key. Ở ví dụ Stream tuần tự có encounter order, kết quả giữ object đầu tiên của mỗi key.

**Không áp dụng nguyên xi kỳ vọng “first” về thứ tự cho một pipeline unordered/parallel** mà chưa phân tích hợp đồng collector và ordering. Nếu muốn bản ưu tiên theo timestamp, version hoặc một comparator, hãy đưa quy tắc chọn bản ghi vào merge function hoặc chọn thuật toán minh bạch.

### 11.3. Dùng record như khóa tổng hợp

Nếu “trùng” có nghĩa là cùng hai thuộc tính, tạo khóa tổng hợp bất biến:

```java
record Key(String category, String code) {}
```

Record tự cung cấp `equals` và `hashCode` cho các component. Trong pipeline, có thể `map(item -> new Key(item.category(), item.code()))` rồi `distinct()` nếu mục tiêu là danh sách **khóa** duy nhất. Muốn giữ object, dùng map/collector với khóa đó. Cách này bảo vệ equality của domain class khỏi bị thay đổi chỉ để phục vụ một báo cáo.

## 12. Những trường hợp tinh tế

### 12.1. BigDecimal và equals khác compareTo

`BigDecimal.equals` xem xét **giá trị và scale**, còn `BigDecimal.compareTo` so sánh giá trị số theo quy tắc khác. Vì thế:

```java
List<java.math.BigDecimal> values = List.of(
        new java.math.BigDecimal("1.0"),
        new java.math.BigDecimal("1.00")
);

System.out.println(values.stream().distinct().toList());
// [1.0, 1.00]
```

Đây là mảnh mã cần `import java.util.List;`. Hai giá trị so sánh số học có thể `compareTo(...) == 0`, nhưng `equals` false do scale khác, nên `distinct()` giữ cả hai. Nếu nghiệp vụ muốn quy về cùng giá trị số, có thể cân nhắc `stripTrailingZeros()` hoặc một chính sách normalization trước khi gọi `distinct`, đồng thời kiểm tra yêu cầu nghiệp vụ với scale.

### 12.2. Mảng không so sánh sâu phần tử

```java
int[] a = {1, 2};
int[] b = {1, 2};
long count = java.util.stream.Stream.of(a, b).distinct().count();
// 2: hai mảng riêng biệt, Object.equals so sánh reference.
```

Đây là mảnh mã đúng khi `Stream.of(a, b)` được hiểu là Stream hai phần tử có kiểu `int[]`. Nếu muốn loại trùng theo **nội dung mảng**, hãy tạo wrapper có equality dựa trên `Arrays.equals`/`Arrays.hashCode` hoặc chuyển thành dạng khóa bất biến phù hợp.

### 12.3. Null khác object có giá trị rỗng

`null`, chuỗi `""`, số `0` và một object có field rỗng không đồng nghĩa. `distinct()` không tự gộp tất cả chúng. Nếu muốn coi một số trạng thái là giống nhau, chuẩn hóa trước rồi mới distinct, ví dụ `trim`/lowercase hoặc chuyển dữ liệu không hợp lệ thành một mã đại diện rõ ràng.

### 12.4. distinct() không thể thay mọi phép chọn phần tử

Nếu mục đích là lấy **một phần tử theo điều kiện**, có thể dùng `filter` và `findFirst`/ `findAny`. Nếu mục đích là **sắp xếp**, dùng `sorted`. Nếu mục đích là **nhóm theo key**, dùng `groupingBy` hoặc `toMap` phù hợp. `distinct()` chỉ xử lý **trùng nhau theo equality** của phần tử đi qua pipeline tại vị trí đó.

Ví dụ, `map(Product::id).distinct()` trả danh sách ID, không trả danh sách Product; vị trí của `map` so với `distinct` có thể thay đổi ý nghĩa “trùng” đang được kiểm tra.

## 13. Side effect, mutation và độ tin cậy

Predicate và mapper trong Stream nên có tính **non-interfering** và **stateless** khi có thể. Đối với `distinct`, đặc biệt tránh sửa field tham gia `equals` hoặc `hashCode` trong khi pipeline đang xử lý object đó.

Ví dụ rủi ro:

```java
// Không làm thế này trong một Stream đang xử lý Set/hash-based uniqueness:
// product.setId(newId); // id được dùng trong equals/hashCode
```

Đây là dòng **minh họa sai lầm cần tránh**, không phải lời gọi runnable độc lập. Khi sửa thuộc tính tham gia hashing trong quá trình đối tượng đang nằm trong cấu trúc hash, membership có thể bị phá. Với parallel Stream, việc nhiều thread đồng thời sửa object chỉ làm nguy cơ race condition tăng lên.

Tránh dùng `peek` hoặc một `map` có side effect để “vừa đổi ID vừa distinct”. Hãy xử lý chuẩn hóa dữ liệu trước pipeline và dùng các đối tượng/khóa không đổi trong thời gian tính kết quả.

## 14. Lỗi phổ biến

1. **Nghĩ distinct dùng `==`:** nó dùng equality theo `equals`, không phải phép tham chiếu identity tùy tiện.
2. **Override `equals` nhưng không override `hashCode`:** vi phạm hợp đồng với cấu trúc hash.
3. **Tin rằng hash giống nhau có nghĩa object bằng nhau:** hash collision vẫn có thể xảy ra; cần `equals`.
4. **Nhầm hai object cùng field là trùng:** class thường kế thừa `Object.equals` nếu không override.
5. **Mong record so sánh chỉ một field:** record mặc định dùng các component trong equality.
6. **Trông đợi distinct tự bỏ chuỗi trống hoặc null:** nó chỉ loại bản trùng nhau; phải lọc theo quy tắc khác nếu cần.
7. **Mong distinct bỏ qua khác biệt hoa/thường:** `String.equals` phân biệt case; chuẩn hóa trước khi distinct.
8. **Trông đợi parallel unordered luôn giữ “bản đầu tiên”:** chỉ ordered Stream mới có hợp đồng ổn định theo encounter order.
9. **Cho rằng distinct làm thay đổi List nguồn:** nó trả một Stream mới, không sửa collection.
10. **Giả định distinct chạy ngay khi gọi:** đây là stateful intermediate operation, terminal mới kích hoạt pipeline.
11. **Dùng equals/hashCode dựa trên field mutable:** sửa field sau khi đưa object vào cấu trúc hash có thể làm hỏng membership.
12. **Dùng distinct thay groupingBy hoặc chọn object mới nhất:** cần thiết kế phép chọn theo key cụ thể.
13. **Cho rằng parallel distinct luôn nhanh hơn:** giữ thứ tự và quản lý state có thể gây overhead.
14. **Cho rằng `toList()` luôn trả ArrayList sửa được:** `Stream.toList()` trả danh sách không sửa được qua API.
15. **Giả định mọi terminal phải gọi mapper đúng một lần cho mọi phần tử:** Stream có thể short-circuit hoặc tối ưu; không đặt logic bắt buộc vào side effect.

## 15. Bài tập tự kiểm tra

**Câu 1.** Kết quả của `List.of("A", "a", "A").stream().distinct().toList()`?

**Đáp án:** `[A, a]`, vì `String.equals` phân biệt chữ hoa/thường.

**Câu 2.** Muốn loại trùng không phân biệt hoa/thường thì viết thế nào (chấp nhận kết quả đã lowercase)?

```java
List<String> unique = values.stream()
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .distinct()
        .toList();
```

Đây là mảnh mã cần `values` kiểu `List<String>` không chứa null.

**Câu 3.** Vì sao hai `new Plain("X")` trong ví dụ lại không bị coi là trùng?

Vì `Plain` không override `equals`, nên hai instance riêng biệt so sánh theo identity của `Object`.

**Câu 4.** Nếu `equals` trả true giữa hai object, `hashCode` bắt buộc phải như thế nào?

**Đáp án:** Hai object phải có **cùng giá trị hashCode**. Chiều ngược lại không bắt buộc.

**Câu 5.** Với nguồn List có thứ tự, `parallelStream().distinct().toList()` có giữ thứ tự encounter và bản xuất hiện đầu tiên không?

**Có**, vì ordered Stream yêu cầu distinct ổn định, và `toList` giữ encounter order của kết quả. Thứ tự thực thi nội bộ trên thread vẫn có thể khác.

**Câu 6.** Nếu class `Product` có `equals` dựa trên `id`, `distinct()` phân biệt hai sản phẩm cùng `id` khác `name` không?

**Không**; chúng được xem bằng nhau theo hợp đồng của class. Nếu chỉ muốn quy tắc này cho một pipeline, có thể dùng `toMap`/collector theo key thay vì đổi equality toàn class.

**Câu 7.** Vì sao `BigDecimal("1.0")` và `BigDecimal("1.00")` không bị loại thành một bởi distinct?

Vì `BigDecimal.equals` còn xét scale, dù `compareTo` có thể trả 0.

**Câu 8.** Tại sao một pipeline với `distinct()` không nên dựa trên các object bị sửa `id` liên tục trong khi đang xử lý?

Vì equality và hash phải nhất quán khi xử lý, đặc biệt với cấu trúc hash và nhiều thread; sửa dữ liệu tham gia equality/hash làm kết quả khó đoán.

**Ghi nhớ:** **`distinct()` loại trùng theo `equals()`; một class override `equals()` phải duy trì `hashCode()` nhất quán.** Ordered Stream giữ phần tử gặp đầu tiên; unordered Stream không cam kết điều đó. Khi cần loại trùng theo một trường riêng, hãy biểu diễn khóa nghiệp vụ rõ ràng thay vì mặc định sửa `equals` của toàn bộ class.
