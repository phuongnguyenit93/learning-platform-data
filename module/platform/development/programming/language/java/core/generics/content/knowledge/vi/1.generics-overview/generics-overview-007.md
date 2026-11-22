# Lợi ích, giới hạn và trường hợp không cần generics trong Java

Generics giúp diễn đạt **mối quan hệ về kiểu dữ liệu** ngay trong chữ ký lớp, interface và phương thức. Chúng thường giúp phát hiện sai kiểu khi biên dịch, tái sử dụng thuật toán và làm cho API rõ nghĩa hơn. Tuy nhiên, không phải mọi lớp hay phương thức đều nên khai báo `<T>`: việc tổng quát hóa chỉ hữu ích khi có một quan hệ kiểu thực sự cần duy trì.

Mục tiêu của bài học là đánh giá được **lợi ích**, hiểu **ranh giới bảo đảm** của generics trong Java và quyết định **khi nào dùng kiểu tổng quát, kiểu cụ thể, `Object` hoặc wildcard**. Các ví dụ dùng Java 17 trở lên.

## 1. Câu hỏi đầu tiên: có mối quan hệ kiểu cần biểu diễn không?

Xét hai API:

```java
// A: kiểu đầu vào quyết định kiểu kết quả.
static <T> T first(java.util.List<T> items) {
    return items.get(0);
}

// B: phép tính luôn phục vụ một loại dữ liệu nghiệp vụ cụ thể.
static int totalStock(java.util.List<Product> products) {
    return products.stream().mapToInt(Product::stock).sum();
}
```

Ở A, `T` xuất hiện ở cả đối số `List<T>` và kiểu trả về `T`. Nó biểu diễn quy tắc: **lấy phần tử từ danh sách kiểu nào thì nhận về phần tử kiểu đó**. Một phương thức làm việc với `String`, `Product` hoặc nhiều kiểu tham chiếu khác mà vẫn kiểm tra kiểu.

Ở B, quy tắc nghiệp vụ là tính tổng tồn kho của `Product`. Không có nhu cầu bảo toàn hay trả về một kiểu tham số tùy ý. `List<Product>` làm rõ yêu cầu hơn `List<T>`: tổng quát hóa B sẽ không tạo thêm lợi ích chỉ vì cú pháp ngắn gọn hay có vẻ linh hoạt.

`Product` trong đoạn B là một kiểu miền nghiệp vụ minh họa, được khai báo đầy đủ ở chương trình chạy bên dưới. Các đoạn code ngắn trong bài chỉ mô tả từng ý; ví dụ `Main.java` ở phần 3 là chương trình hoàn chỉnh.

## 2. Các lợi ích quan trọng

### 2.1. Phát hiện sai kiểu ngay khi biên dịch

Hãy xem hợp đồng `List<String>`:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Lan");
// names.add(123); // Lỗi biên dịch: add yêu cầu String.

String name = names.get(0); // Không phải tự ép từ Object.
```

Trình biên dịch biết kiểu phần tử của `names` là `String` nên từ chối việc thêm `Integer` bằng lời gọi thông thường. Nhờ đó, nhiều lỗi vốn chỉ lộ ra khi người dùng chạy đúng nhánh nghiệp vụ được phát hiện trước khi chương trình chạy.

Điều này **giảm nguy cơ** `ClassCastException` và các lỗi dùng sai kiểu, chứ **không triệt tiêu tuyệt đối** chúng. `raw type`, phép ép kiểu không kiểm chứng, reflection, deserialization hoặc tương tác với thư viện cũ vẫn có thể đưa dữ liệu sai kiểu vào bộ sưu tập.

### 2.2. Giảm ép kiểu tường minh, làm rõ hợp đồng API

Một API chỉ trả `Object` đặt trách nhiệm xác định kiểu thực lên bên gọi:

```java
Object result = getLegacyValue();
String text = (String) result; // Chỉ an toàn nếu dữ liệu thật là String.
```

Nếu hợp đồng có thể thể hiện bằng kiểu tổng quát, API có thể trả đúng kiểu liên quan tới lời gọi, chẳng hạn `Optional<Product>`, `Result<String>` hay `List<Order>`. Code gọi ngắn và dễ đọc hơn, còn IDE có thể hỗ trợ kiểm tra kiểu và gợi ý thành viên chính xác hơn.

Tuy nhiên, **không được đổi một API trả `Object` thành `<T> T` nếu thực tế không có cơ chế bảo đảm kiểu được yêu cầu**. Ví dụ một phương thức đọc dữ liệu không rõ schema mà tự ép `(T)` bên trong chỉ chuyển cảnh báo và nguy cơ lỗi sang chỗ khác, không tạo ra bảo đảm an toàn mới.

### 2.3. Tái sử dụng cấu trúc và thuật toán

`List<E>`, `Map<K, V>`, `Optional<T>` và `Comparator<T>` đều khai thác mối quan hệ kiểu. Ví dụ `Map<K,V>` buộc kiểu khóa và kiểu giá trị theo hai tham số độc lập; `Optional<T>` gói việc có hoặc không có giá trị mà vẫn giữ kiểu của giá trị đó.

Các thành phần dùng lại có thể nhận các kiểu miền nghiệp vụ khác nhau mà không phải viết `ProductResult`, `UserResult`, `InvoiceResult` có phần lưu dữ liệu giống nhau. Trong khi đó, phương thức generic có thể tái sử dụng phép tìm kiếm, chọn phần tử hoặc biến đổi dữ liệu theo kiểu được truyền vào.

Tính tái sử dụng nên đi kèm một **hợp đồng ổn định và có ý nghĩa**; tránh tạo lớp tổng quát chỉ để giảm vài dòng code nếu hành vi giữa các kiểu thực chất khác nhau.

### 2.4. Dễ bảo trì và đổi kiểu khi sửa API

Nếu tham số kiểu của một biến, field hoặc phương thức thay đổi, trình biên dịch chỉ ra nhiều vị trí sử dụng không tương thích. Các kiểu như `List<Product>` cũng là một dạng tài liệu được máy kiểm tra, giúp người đọc nhận biết đúng dữ liệu API chấp nhận.

Generics không thay thế tài liệu về ý nghĩa nghiệp vụ: `List<Integer>` vẫn không nói được số phải không âm, là mã định danh hay đại lượng đo lường. Những ràng buộc này cần kiểu miền nghiệp vụ hoặc validation riêng.

## 3. Ví dụ Java 17+ hoàn chỉnh: chọn generics ở đúng chỗ

Chương trình kết hợp ba quyết định thiết kế:

- `Result<T>` là lớp generic vì kiểu dữ liệu trả về thay đổi nhưng cấu trúc kết quả giữ nguyên.
- `findFirst` là phương thức generic vì kiểu đầu vào và phần tử tìm được phải đồng nhất.
- `totalStock` nhận đúng `List<Product>` và `describe` nhận `Object` vì cả hai không cần mối quan hệ kiểu tổng quát.

Lưu toàn bộ đoạn sau vào **`Main.java`**:

```java
import java.util.List;
import java.util.Optional;
import java.util.function.Predicate;

public class Main {
    record Product(String code, int stock) {
    }

    static final class Result<T> {
        private final String status;
        private final T value;

        private Result(String status, T value) {
            this.status = status;
            this.value = value;
        }

        static <T> Result<T> ok(T value) {
            return new Result<>("OK", value);
        }

        String status() {
            return status;
        }

        T value() {
            return value;
        }
    }

    static <T> Optional<T> findFirst(
            List<T> items,
            Predicate<? super T> condition) {
        for (T item : items) {
            if (condition.test(item)) {
                return Optional.ofNullable(item);
            }
        }
        return Optional.empty();
    }

    static int totalStock(List<Product> products) {
        int sum = 0;
        for (Product product : products) {
            sum += product.stock();
        }
        return sum;
    }

    static String describe(Object value) {
        return String.valueOf(value);
    }

    public static void main(String[] args) {
        Result<String> message = Result.ok("ready");
        Result<Product> saved = Result.ok(new Product("P-01", 7));

        List<Product> inventory = List.of(
                new Product("P-01", 7),
                new Product("P-02", 2));

        Optional<Product> lowStock =
                findFirst(inventory, product -> product.stock() < 3);

        System.out.println("status: " + message.status());
        System.out.println("message: " + message.value());
        System.out.println("saved SKU: " + saved.value().code());
        System.out.println("low stock: "
                + lowStock.map(Product::code).orElse("none"));
        System.out.println("total stock: " + totalStock(inventory));
        System.out.println("describe: " + describe(42));

        // message = Result.ok(42); // Không biên dịch: Result<Integer>
        // không thể gán cho biến Result<String>.
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Kết quả trên stdout:

```text
status: OK
message: ready
saved SKU: P-01
low stock: P-02
total stock: 9
describe: 42
```

Giải thích thiết kế:

1. `Result.ok("ready")` suy luận `T` là `String`; `Result.ok(new Product(...))` suy luận `T` là `Product`. Người đọc `message.value()` được `String`, còn `saved.value()` được `Product`, không cần ép kiểu thủ công.
2. `findFirst` khai báo `<T>` trước kiểu trả về. `Predicate<? super T>` cho phép cung cấp một điều kiện có thể xử lý `T` hoặc kiểu cha của `T`; kết quả `Optional<T>` giữ kiểu phần tử của danh sách.
3. `totalStock(List<Product>)` cố ý không generic: logic `stock()` chỉ có ý nghĩa với `Product` trong ví dụ này.
4. `describe(Object)` cũng không cần `<T>`: nó nhận một giá trị bất kỳ, chuyển thành chuỗi và không trả lại giá trị cùng kiểu với đầu vào. Khai báo `static <T> String describe(T value)` sẽ thêm tham số kiểu không tạo ích lợi cho hợp đồng.

Các quy tắc thông báo lỗi ở ví dụ được để dưới dạng chú thích để chương trình vẫn biên dịch và chạy được. Việc thêm một tham số kiểu chỉ vì phương thức có đầu vào tùy ý thường là dấu hiệu cần xem lại thiết kế.

## 4. Ranh giới an toàn kiểu: Java generics không bảo đảm điều gì?

### 4.1. Type erasure: hầu hết đối số kiểu không còn ở runtime

Java generics chủ yếu hoạt động qua **type erasure**: trình biên dịch kiểm tra tính tương thích theo khai báo, sau đó chuyển phần lớn thông tin tham số kiểu thành kiểu bị xóa (với bound phù hợp), đồng thời chèn các phép ép kiểu cần thiết.

```java
java.util.List<String> texts = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

System.out.println(texts.getClass() == numbers.getClass()); // true
```

Hai đối tượng trên đều thuộc lớp runtime `java.util.ArrayList`. Kết quả `true` **không chứng minh** hai danh sách có cùng kiểu phần tử; nó chỉ chứng minh hai đối tượng có cùng lớp triển khai khi chạy.

Bạn có thể hỏi `value instanceof List<?>`, nhưng không thể kiểm tra chính xác `value instanceof List<String>` bằng cú pháp ấy: kiểu đối số `String` không được *reified* ở runtime. Tương tự, `List<String>.class` không phải một class literal hợp lệ.

Nếu cần kiểm tra kiểu runtime của một đối tượng riêng lẻ, có thể truyền **type token** `Class<T>`:

```java
static <T> T checkedCast(Object value, Class<T> expectedType) {
    return expectedType.cast(value);
}

// checkedCast("abc", String.class) -> String.
// checkedCast(123, String.class) -> ClassCastException khi chạy.
```

Đây là đoạn minh họa phương thức, không phải chương trình độc lập. `Class<T>` kiểm tra lớp của đối tượng được cast; nó **không kiểm tra sâu** danh sách thực sự chỉ chứa `String` qua `List<String>` vì không có `List<String>.class`.

### 4.2. Raw type và unchecked cast có thể làm hỏng bảo đảm kiểu

Raw type là việc bỏ đối số kiểu, ví dụ `List` thay vì `List<String>`, chủ yếu để tương thích ngược với Java trước generics:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(99); // Cảnh báo unchecked khi biên dịch.
```

Đoạn này vẫn có thể biên dịch cùng cảnh báo; danh sách gốc giờ chứa `Integer`. Nếu đoạn code khác lấy phần tử ấy với giả định `String`, có thể xảy ra `ClassCastException`. Phân biệt rõ: lỗi **không bắt buộc xảy ra ngay khi thêm**, mà thường lộ ra lúc lấy giá trị và trình biên dịch đã chèn cast tương ứng.

Cảnh báo `unchecked` phải được xem xét về nguồn gốc dữ liệu và hợp đồng kiểu; không nên xóa cảnh báo bằng `@SuppressWarnings("unchecked")` tùy tiện. Giữ thao tác ép kiểu không kiểm chứng tại ranh giới nhỏ nhất và kiểm tra giá trị khi cần.

### 4.3. Generics thường bất biến (invariant)

Dù `Integer` là subtype của `Number`, `List<Integer>` không phải subtype của `List<Number>`:

```java
java.util.List<Integer> integers = java.util.List.of(1, 2);
// java.util.List<Number> nums = integers; // Không biên dịch.
```

Nếu phép gán này hợp lệ, một phương thức nhận `List<Number>` có thể thêm `Double` vào danh sách vốn chỉ được thiết kế cho `Integer`.

Khi chỉ cần đọc các giá trị là số, wildcard có thể phù hợp:

```java
static double sum(java.util.List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

`sum` chấp nhận `List<Integer>`, `List<Double>` và nhiều danh sách số khác. Nhưng qua tham chiếu `List<? extends Number>`, bạn **không thể thêm một đối tượng `Number` tùy ý**; chỉ có thể thêm `null` trong những trường hợp phép thêm được hỗ trợ. Đây là đánh đổi để bảo vệ kiểu phần tử thực tế. `? super T` thường thích hợp khi API cần **nhận giá trị để ghi**; sự lựa chọn wildcard phải xuất phát từ hành vi đọc/ghi thực tế.

### 4.4. Không phải mọi cú pháp Java đều hỗ trợ tham số kiểu

Các ví dụ dưới đây **cố ý không hợp lệ**, dùng để nhận diện giới hạn; không ghép chúng vào `Main.java` để chạy:

```java
// List<int> values;               // Sai: đối số kiểu không là primitive.
// T x = new T();                   // Sai: không thể new T trực tiếp.
// T[] a = new T[10];               // Sai: không thể tạo mảng generic trực tiếp.
// new List<String>[10];            // Sai: không tạo mảng kiểu tham số hóa.
// if (obj instanceof List<String>) // Sai: không kiểm tra loại phần tử ấy.
// ...
```

Đối số kiểu như `List<Integer>` phải là **kiểu tham chiếu**, không phải primitive (`List<int>`). Java tự boxing/unboxing cho nhiều thao tác với `Integer`, nhưng vẫn có chi phí cấp phát hoặc chuyển đổi trong một số tình huống; không nên giả định dùng generics có hiệu năng giống `int[]`.

Trong một lớp `class Store<T>`, field `static T value` cũng không hợp lệ vì field static thuộc lớp dùng chung, còn `T` thuộc từng cách tham số hóa. Phương thức `static <T> T convert(...)` có thể tự khai báo `<T>` riêng; đây là hai trường hợp khác nhau.

Hai overload chỉ khác đối số kiểu như `void use(List<String> x)` và `void use(List<Integer> x)` sẽ xung đột do **cùng chữ ký sau erasure**. Java cũng không cho tạo một lớp generic kế thừa trực tiếp `Throwable`, nên kiểu ngoại lệ không thể được tham số hóa như `class MyException<T> extends Exception`.

### 4.5. Generics không thay thế validation hoặc xác thực dữ liệu

`List<String>` không bảo đảm phần tử khác `null`, không rỗng hay đúng định dạng email. `Result<Product>` không bảo đảm tồn kho không âm, bản ghi tồn tại trong cơ sở dữ liệu hay người dùng có quyền truy cập.

Kiểu tổng quát cho biết **hình dạng và mối quan hệ kiểu**. Các quy tắc như “số lượng lớn hơn hoặc bằng 0”, “mã sản phẩm duy nhất” và “được phép xem sản phẩm” phải được kiểm tra bởi constructor, domain model, tầng nghiệp vụ hoặc cơ chế bảo mật thích hợp.

Generics cũng không tự động làm API thread-safe, bất biến, nhanh hơn hay dùng ít bộ nhớ hơn. Các thuộc tính này phụ thuộc cấu trúc dữ liệu, cách đồng bộ hóa, thuật toán và cách lưu trữ thực tế.

## 5. Các trường hợp không cần tự khai báo generics

### 5.1. Thành phần chỉ có một kiểu miền nghiệp vụ cố định

Nếu nghiệp vụ xử lý đúng `Product`, dùng `Product` trực tiếp:

```java
static int quantityToReorder(Product product, int minimum) {
    return Math.max(0, minimum - product.stock());
}
```

Phương thức này không cần `<T>` vì nó đòi hỏi thuộc tính `stock()` của `Product`. Tổng quát hóa thành `<T>` buộc phải thêm ràng buộc hoặc ép kiểu, trong khi không có tình huống dùng lại có ý nghĩa. Bài học ở đây là: **kiểu cụ thể có thể là hợp đồng rõ nhất**.

### 5.2. Kiểu dữ liệu đầu vào không cần được giữ lại

Một phương thức ghi log hoặc hiển thị mô tả có thể nhận một đối tượng bất kỳ và luôn trả về chuỗi:

```java
static String describe(Object value) {
    return String.valueOf(value);
}
```

Tham số kiểu `<T>` không giúp liên kết đầu vào với đầu ra vì đầu ra luôn là `String`. Dùng `Object` là lựa chọn đơn giản, có chủ đích trong trường hợp này.

Cần phân biệt với API nhận danh sách *không rõ kiểu phần tử*. Khi chỉ duyệt và đọc một danh sách bất kỳ, `List<?>` thường phù hợp hơn `List<Object>`:

```java
static int count(java.util.List<?> items) {
    return items.size();
}
```

`count(List<?>)` nhận được `List<String>` và `List<Integer>`, trong khi `count(List<Object>)` **không** nhận trực tiếp `List<String>`. Đây vẫn là việc **sử dụng** cú pháp generic của thư viện, nhưng phương thức không phải tự khai báo tên kiểu `<T>`.

### 5.3. Tổng quát hóa làm mất ý nghĩa nghiệp vụ

`Payment`, `Invoice` và `UserAccount` có thể đều có một trường `id`, nhưng không vì thế mà mọi nghiệp vụ của chúng nên gom vào `Manager<T>`. Nếu validation, vòng đời và quyền truy cập khác nhau, những service cụ thể hoặc interface có trách nhiệm rõ ràng thường dễ đọc và an toàn hơn.

Tham số kiểu chỉ nên xuất hiện khi có **hành vi chung thực sự và quy tắc ràng buộc kiểu cần giữ**. Tránh khai báo nhiều tham số `<T,U,V>` mà phần lớn không xuất hiện ở đầu vào hoặc kết quả, khiến người gọi phải suy đoán ý nghĩa chúng.

### 5.4. Dữ liệu đa hình có tập kiểu và hành vi xác định

Nếu chương trình xử lý nhiều loại thông điệp với hành vi khác nhau, một interface hoặc sealed interface có thể diễn đạt miền dữ liệu tốt hơn một `Box<Object>` chứa mọi thứ. Với Java 17, ví dụ:

```java
sealed interface Event permits OrderCreated, PaymentFailed {
}

record OrderCreated(String orderId) implements Event {
}

record PaymentFailed(String reason) implements Event {
}
```

Đây là các khai báo minh họa, không phải chương trình độc lập. Chúng làm rõ các biến thể `Event` hợp lệ. Bạn vẫn có thể dùng `List<Event>` để chứa nhiều biến thể; việc lựa chọn đa hình theo hành vi và việc tham số hóa cấu trúc dữ liệu là **hai quyết định có thể phối hợp**.

Đối với dữ liệu JSON hoặc bản ghi động không xác định schema, không nên giả định `T` làm dữ liệu tự trở nên hợp lệ. Hãy parse, validate và chuyển đổi ở biên; chỉ dùng kiểu tổng quát nếu có cơ chế đáng tin để gắn đầu vào với kiểu kết quả.

### 5.5. Thuật toán sử dụng primitive trong đường xử lý hiệu năng cao

`List<Integer>` có thể phù hợp với logic nghiệp vụ thông thường. Nhưng khi xử lý một lượng lớn giá trị nguyên, `int[]`, `IntStream` hoặc cấu trúc chuyên dụng cho primitive có thể tránh một phần boxing và overhead đối tượng. Cần đo đạc trước khi tối ưu: generics không mặc định chậm và mảng primitive cũng không mặc định tốt nhất cho mọi bài toán.

### Bảng quyết định nhanh

| Nhu cầu thực tế | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Cùng cấu trúc lưu một giá trị với nhiều kiểu | `Box<T>` hoặc `Result<T>` | Bảo toàn kiểu payload qua các thao tác |
| Thuật toán trả về phần tử cùng kiểu với đầu vào | Phương thức `static <T> T ...` | Liên kết đầu vào và kết quả |
| Bảng ánh xạ khóa và giá trị có kiểu cụ thể | `Map<K,V>` khi khai báo API tổng quát; `Map<String,Integer>` khi sử dụng | Mô tả đúng hai loại dữ liệu |
| Chỉ tính tồn kho sản phẩm | `List<Product>` / `Product` | Đúng logic và kiểu miền nghiệp vụ |
| Chỉ đếm phần tử của danh sách bất kỳ | `List<?>` | Không cần biết hay truyền trả kiểu phần tử |
| Nhận đối tượng bất kỳ để ghi log/chuyển thành chuỗi | `Object` | Không cần quan hệ kiểu |
| Cần phân biệt nhiều trường hợp nghiệp vụ có hành vi riêng | Interface, sealed interface, class/record cụ thể | Diễn đạt tập biến thể và hành vi |
| Dữ liệu động chưa được kiểm chứng | Parse, validate, type token hoặc schema phù hợp | Generics không tự kiểm tra kiểu runtime sâu |
| Khối lượng lớn primitive, nhạy hiệu năng | `int[]`, `IntStream` hoặc cấu trúc primitive đã đo đạc | Tránh chi phí boxing ở nơi cần |

## 6. Dấu hiệu thiết kế generics đang bị lạm dụng

- **Tham số kiểu chỉ xuất hiện một lần, không có ràng buộc hữu ích:** ví dụ `static <T> void print(T value)` thường nên là `print(Object value)` nếu chỉ in bằng `String.valueOf`. Tuy nhiên, một bound cụ thể vẫn có thể diễn đạt yêu cầu kiểu; không dùng số lần xuất hiện như luật tuyệt đối.
- **Ép kiểu `(T)` bên trong mà không có căn cứ:** khiến API trông an toàn nhưng thực tế chỉ đẩy nguy cơ `ClassCastException` tới người gọi.
- **Mọi lớp đều có `<T>` dù logic chỉ dành cho một entity:** làm khó đọc và có thể làm lu mờ quy tắc nghiệp vụ.
- **Dùng raw type để tránh xử lý wildcard/bounds:** thường đánh mất kiểm tra kiểu và tạo cảnh báo `unchecked`.
- **Thử giải quyết bất biến hoặc phân quyền bằng generics:** kiểu tham số không thay thế constructor validation, kiểm tra quyền hay đồng bộ hóa.
- **Dùng wildcard quá rộng trong API cho phép ghi:** chẳng hạn trả `List<? extends Number>` rồi mong thêm số bất kỳ vào; khả năng đọc và ghi cần thiết phải được xác định trước khi chọn bound.
- **Tổng quát hóa vì dự đoán sẽ dùng lại nhưng chưa có trường hợp thật:** làm tăng chi phí học và bảo trì. Hãy thiết kế hợp đồng cụ thể đúng trước; trích xuất generic khi đã thấy quan hệ chung.

Một số API tổng quát phức tạp hoàn toàn có lý do chính đáng, nhất là thư viện, collection và framework. Điểm đánh giá không phải số lượng dấu `<...>`, mà là **tham số kiểu có làm rõ và kiểm tra được một ràng buộc thực sự hay không**.

## 7. Checklist khi quyết định dùng generics

Trước khi khai báo `<T>`, tự trả lời:

1. **Mối quan hệ kiểu nào cần giữ?** Kiểu của đối số, trạng thái, callback hoặc kết quả có cần phụ thuộc lẫn nhau không?
2. **Có hành vi chung thực sự?** Nhiều kiểu có thể chia sẻ cùng thuật toán mà không phải dùng `instanceof` và cast liên tục không?
3. **Người dùng API được lợi gì?** Có giảm ép kiểu, bắt lỗi sớm hoặc thể hiện hợp đồng rõ hơn không?
4. **Có cần kiểm tra kiểu runtime không?** Nếu có, cần type token/schema và validation ở đâu?
5. **Bound hoặc wildcard có phù hợp với hướng dữ liệu?** API chỉ đọc, chỉ ghi hay vừa đọc vừa ghi?
6. **Có đang che giấu logic nghiệp vụ?** Kiểu cụ thể, interface hoặc model miền có diễn đạt rõ hơn không?
7. **Có yếu tố primitive hoặc hiệu năng đặc biệt?** Khi đáng kể, nên benchmark giải pháp phù hợp.

Nếu câu hỏi 1–3 đều không cho thấy ích lợi, thường **không cần tự khai báo thêm generics**.

## 8. Tự kiểm tra kiến thức

**Câu 1.** Phương thức sau có cần khai báo `<T>` không?

```java
static <T> int lengthOfText(T value) {
    return String.valueOf(value).length();
}
```

**Đáp án:** Không bắt buộc. `T` không tham gia ràng buộc đầu ra hoặc thao tác phụ thuộc kiểu. `static int lengthOfText(Object value)` đơn giản và diễn đạt đúng hành vi hơn.

**Câu 2.** Có thể dùng `List<Number>` làm tham số để nhận trực tiếp mọi `List<Integer>` và `List<Double>` không?

**Đáp án:** Không, vì các tham số hóa này bất biến. Nếu chỉ đọc số và tính toán, `List<? extends Number>` có thể phù hợp.

**Câu 3.** `List<String>` có bảo đảm dữ liệu từ một raw `List` hoặc phản hồi JSON bên ngoài đều thật sự là `String` ở runtime không?

**Đáp án:** Không. Type erasure, raw type, unchecked operation và dữ liệu ngoài ranh giới kiểu khiến kiểm chứng runtime cần giải pháp riêng. Generics chủ yếu bảo vệ tại các điểm gọi được trình biên dịch kiểm tra.

**Câu 4.** Tại sao `totalStock(List<Product>)` lại là lựa chọn tốt hơn `static <T> int totalStock(List<T>)` trong ví dụ?

**Đáp án:** Vì phép tính cần phương thức `stock()` của `Product`, nên khai báo cụ thể mô tả trực tiếp điều kiện nghiệp vụ. Chữ `T` tự nó không cho phép gọi `stock()` nếu không có bound phù hợp, trong khi tính tổng tồn kho ở đây không phải hành vi tổng quát cho mọi loại đối tượng.

**Câu 5.** `Result<String>` có tự khiến chuỗi kết quả khác `null` hoặc khác rỗng không?

**Đáp án:** Không. `String` xác định loại dữ liệu, còn ràng buộc null/chuỗi rỗng phải có kiểm tra giá trị riêng trong API hoặc domain model.

## Kết luận

Generics có giá trị cao nhất khi chúng **bảo toàn quan hệ kiểu qua các thao tác**, giúp tái sử dụng logic và chuyển nhiều lỗi sang giai đoạn biên dịch. Chúng có giới hạn bởi type erasure, bất biến kiểu, quy tắc cú pháp Java, raw/unchecked code và sự tách biệt giữa kiểu dữ liệu với validation nghiệp vụ. Khi hành vi gắn chặt với một entity, đầu vào không cần liên kết với đầu ra hoặc một interface chuyên biệt diễn đạt miền dữ liệu tốt hơn, chọn **kiểu cụ thể hoặc abstraction phù hợp** sẽ làm API sáng sủa hơn.