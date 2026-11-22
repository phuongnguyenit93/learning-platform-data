# Truyền hành vi như một tham số (Java 8 Lambda)

## 1. Ý tưởng cốt lõi

Một phương thức thường nhận **dữ liệu**: một số, một chuỗi, một danh sách hoặc đối tượng. Nhưng nhiều bài toán có quy trình xử lý giống nhau, chỉ khác **quy tắc xử lý**. Chẳng hạn, cùng duyệt một danh sách sản phẩm nhưng có lần lọc theo giá, lần khác lọc theo tên; cùng sắp xếp danh sách tên nhưng khi cần theo độ dài, khi cần theo chữ cái.

**Truyền hành vi như một tham số (behavior parameterization)** nghĩa là thiết kế phương thức nhận một đối tượng đại diện cho hành vi mà người gọi chọn. Phương thức giữ quy trình chung, còn người gọi cung cấp cách xử lý thay đổi theo ngữ cảnh.

~~~text
Phương thức chung: select(products, condition)
                                  |
                                  +-- price >= 80
                                  +-- price < 80
                                  +-- name.length() > 2
~~~

Từ Java 8, lambda expression và method reference cho phép biểu diễn hành vi ngắn gọn. Các API này vẫn là một phần của Java hiện đại.

Điểm cần phân biệt: **truyền lambda không tự thực thi lambda**. Phương thức nhận callback phải gọi nó; phương thức nhận có quyền quyết định gọi lúc nào, bao nhiêu lần và trên luồng nào. Lambda tự thân không tạo luồng hoặc làm mã chạy bất đồng bộ.

## 2. Vì sao functional interface làm được việc này?

Java sử dụng **functional interface** làm kiểu đích của lambda. Đó là interface có đúng một phương thức trừu tượng cần cài đặt (Single Abstract Method — SAM). Interface vẫn có thể có phương thức `default`, `static`, hoặc khai báo lại các phương thức của `Object`. Annotation `@FunctionalInterface` giúp trình biên dịch kiểm tra ràng buộc SAM và nên dùng cho interface tự định nghĩa.

~~~java
@FunctionalInterface
interface PriceRule {
    int apply(int originalPrice);
}
~~~

Một phương thức nhận quy tắc:

~~~java
static int calculate(int originalPrice, PriceRule rule) {
    return rule.apply(originalPrice);
}
~~~

Các lời gọi minh họa:

~~~java
int discounted = calculate(200, p -> p - p / 10); // 180
int withFee = calculate(200, p -> p + 30);        // 230
~~~

`calculate` không phải biết trước “giảm giá” hay “thêm phí”. Đối số `p -> ...` cung cấp thân của `PriceRule.apply(int)`; `rule.apply(originalPrice)` là chỗ hành vi thật sự được thực thi.

Lambda được **target typing**: kiểu của các tham số, kết quả và ngoại lệ phải tương thích chữ ký SAM tại vị trí sử dụng. Vì vậy, `PriceRule rule = p -> p * 2;` hợp lệ, còn `var rule = p -> p * 2;` không hợp lệ do thiếu kiểu đích. Java không khai báo tham số lambda bằng một “kiểu hàm” độc lập; functional interface chính là hợp đồng kiểu của hành vi.

Các dạng viết phổ biến:

~~~java
p -> p * 2
(p) -> { return p * 2; }
() -> System.out.println("Hello")
(a, b) -> Integer.compare(a, b)
~~~

Đây là **các biểu thức minh họa tùy target type**, không phải những dòng khai báo độc lập có thể đặt trực tiếp trong lớp. Thân lambda dạng biểu thức có giá trị trả về phù hợp với SAM; thân dạng khối cần `return` nếu SAM đòi một giá trị.

## 3. Ví dụ chạy được: truyền điều kiện lọc và quy tắc biến đổi

Thay vì viết riêng `selectExpensive`, `selectCheap`, `selectLongName`, hãy viết một phương thức `select` nhận `Predicate<T>` để hỏi phần tử có đạt điều kiện không. Một phương thức `transform` nhận `Function<T,R>` để quyết định cách chuyển đổi từng phần tử.

Tạo tệp **BehaviorParameterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Predicate;

public class BehaviorParameterDemo {
    static final class Product {
        private final String name;
        private final int price;

        Product(String name, int price) {
            this.name = name;
            this.price = price;
        }

        String getName() {
            return name;
        }

        int getPrice() {
            return price;
        }
    }

    static <T> List<T> select(
            List<T> items, Predicate<? super T> condition) {
        Objects.requireNonNull(items);
        Objects.requireNonNull(condition);

        List<T> result = new ArrayList<>();
        for (T item : items) {
            if (condition.test(item)) {
                result.add(item);
            }
        }
        return result;
    }

    static <T, R> List<R> transform(
            List<T> items, Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(items);
        Objects.requireNonNull(mapper);

        List<R> result = new ArrayList<>();
        for (T item : items) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
                new Product("Sach", 120),
                new Product("But", 30),
                new Product("Vo", 80)
        );

        List<Product> expensive =
                select(products, p -> p.getPrice() >= 80);
        List<Product> cheap =
                select(products, p -> p.getPrice() < 80);

        System.out.println(transform(expensive, Product::getName));
        System.out.println(transform(cheap, Product::getName));
    }
}
~~~

Chạy bằng JDK 17+ (mã chỉ dùng tính năng đã có từ Java 8):

~~~bash
javac BehaviorParameterDemo.java
java BehaviorParameterDemo
~~~

Đầu ra:

~~~text
[Sach, Vo]
[But]
~~~

Diễn giải:

1. `select` chỉ phụ trách duyệt, kiểm tra và thu thập kết quả; không chứa điều kiện giá được mã hóa cứng.
2. `condition.test(item)` gọi hành vi mà người dùng truyền ở lần gọi đó; `p -> p.getPrice() >= 80` và `p -> p.getPrice() < 80` là hai hành vi khác nhau.
3. `transform` gọi `mapper.apply(item)`; `Product::getName` là method reference tương ứng với `p -> p.getName()` trong ngữ cảnh này.
4. Generic `<T, R>` giúp hai phương thức dùng được cho nhiều kiểu dữ liệu. `? super T` cho phép hàm nhận kiểu cha của T; `? extends R` cho phép kết quả là kiểu con của R. Khi mới học có thể bắt đầu với `Predicate<T>` và `Function<T,R>` rồi bổ sung wildcard khi thiết kế API tái sử dụng.

Ví dụ cố ý sử dụng vòng lặp để chỉ rõ nơi thực thi callback. Trong chương trình thực tế, nhiều bài toán lọc/biến đổi có thể dùng Stream API có sẵn.

## 4. Những functional interface hiện vẫn dùng thường xuyên

| Kiểu | Phương thức SAM | Ý nghĩa hành vi |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | Đánh giá điều kiện; hợp với lọc |
| `Function<T,R>` | `R apply(T value)` | Chuyển đổi từ T sang R |
| `Consumer<T>` | `void accept(T value)` | Xử lý giá trị, không trả kết quả |
| `Supplier<T>` | `T get()` | Cung cấp hoặc tạo giá trị khi được gọi |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi giá trị nhưng giữ cùng kiểu |
| `BiFunction<T,U,R>` | `R apply(T left, U right)` | Kết hợp hai đối số thành một kết quả |
| `Comparator<T>` | `int compare(T a, T b)` | Quy định thứ tự sắp xếp |
| `Runnable` | `void run()` | Một tác vụ không trả kết quả |
| `Callable<V>` | `V call()` | Tác vụ trả kết quả và cho phép checked exception |

Đối với dữ liệu nguyên thủy, có thêm các biến thể chuyên dụng như `IntPredicate`, `IntUnaryOperator`, `LongConsumer`, `ToIntFunction<T>`. Chúng giúp tránh boxing/unboxing không cần thiết khi có nhiều giá trị nguyên thủy. Không cần tạo functional interface mới nếu một interface chuẩn thể hiện đúng hợp đồng.

### 4.1. Sắp xếp: đưa quy tắc vào `Comparator`

Tạo tệp **SortBehaviorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class SortBehaviorDemo {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(Arrays.asList("Lan", "An", "Binh", "Hoa"));

        Comparator<String> byLengthThenAlphabet =
                Comparator.comparingInt(String::length)
                          .thenComparing(Comparator.naturalOrder());

        names.sort(byLengthThenAlphabet);
        System.out.println(names);
    }
}
~~~

~~~bash
javac SortBehaviorDemo.java
java SortBehaviorDemo
~~~

~~~text
[An, Hoa, Lan, Binh]
~~~

`List.sort` thực hiện thao tác sắp xếp; `Comparator` là hành vi quyết định thứ tự. `String::length` đưa ra khóa thứ nhất, `thenComparing` giải quyết trường hợp bằng độ dài theo thứ tự từ điển. Thay comparator sẽ thay quy tắc mà không phải sửa thuật toán.

### 4.2. Stream: truyền nhiều hành vi vào cùng pipeline

Dựa trên biến `products` và lớp `Product` trong phần 3, đoạn **minh họa đặt trong `main`** này tương đương kết quả lọc và lấy tên:

~~~java
List<String> names = products.stream()
        .filter(p -> p.getPrice() >= 80)
        .map(Product::getName)
        .collect(java.util.stream.Collectors.toList());

System.out.println(names); // [Sach, Vo]
~~~

`filter` nhận `Predicate<Product>`, `map` nhận `Function<Product,String>`, `collect` tiêu thụ stream và trả kết quả. Stream có **lazy evaluation** đối với các phép toán trung gian: hành vi được lưu trong pipeline và thực thi khi có terminal operation như `collect`. Đừng suy diễn rằng tất cả API nhận lambda đều lazy; điều đó tùy hợp đồng phương thức nhận hành vi.

Với Stream, nên ưu tiên các lambda không tạo side effect bên ngoài, không sửa source collection và không dựa vào thứ tự tác động phụ, nhất là khi có xử lý song song.

### 4.3. Truyền tác vụ để thực hiện sau

~~~java
Runnable task = () -> System.out.println("Xu ly don hang");
// Tạo đối tượng hành vi: chưa in.
task.run(); // In: Xu ly don hang
~~~

`Runnable` cũng có thể được đưa vào executor; executor quyết định cơ chế thực thi. Việc truyền lambda không tự tạo thread, không bảo đảm callback chạy một lần và không bảo đảm callback chạy ngay. API quản lý tác vụ phải định nghĩa các điều này.

## 5. Lựa chọn cách biểu diễn hành vi

- **Lambda** phù hợp khi hành vi ngắn và diễn đạt rõ ở nơi gọi: `p -> p.getPrice() >= 80`.
- **Method reference** phù hợp khi chỉ gọi phương thức đã tồn tại: `Product::getName`, `System.out::println`, `String::length`.
- **Lớp triển khai interface** phù hợp khi hành vi cần tên riêng, nhiều trạng thái, cấu hình hoặc được tái sử dụng có hệ thống. Functional interface vẫn có thể được cài bằng lớp hoặc anonymous class, không bắt buộc dùng lambda.
- **Phương thức thông thường** phù hợp cho quy tắc cố định, không có nhu cầu caller thay đổi. Không cần biến mọi phương thức thành hàm nhận callback.

Một callback nên đại diện cho **một trách nhiệm có thể diễn đạt bằng SAM**. Nếu một quy trình yêu cầu nhiều phương thức liên quan hoặc hợp đồng phức tạp, có thể cần một interface thông thường nhiều phương thức hoặc một đối tượng chiến lược có tên thay vì ép vào một lambda dài.

## 6. Thiết kế phương thức nhận hành vi có hợp đồng rõ ràng

Khi tạo API, lần lượt xác định:

1. **Phần cố định**: phương thức duyệt, sắp xếp, lặp, chạy lại hay quản lý tài nguyên?
2. **Phần biến đổi**: điều kiện (`Predicate`), phép chuyển (`Function`), hành động (`Consumer`), nhà cung cấp giá trị (`Supplier`) hay hợp đồng riêng?
3. **Lúc gọi**: callback được gọi ngay, trì hoãn, gọi một lần hay nhiều lần?
4. **Ngữ cảnh**: có thể chạy trên luồng khác hoặc thực hiện song song không? Có thứ tự ổn định không?
5. **Lỗi**: nếu callback ném exception, phương thức nhận sẽ truyền tiếp, chuyển đổi hay xử lý thế nào?
6. **Tiền điều kiện**: callback có được `null` không? Nếu không, kiểm tra bằng `Objects.requireNonNull` và báo lỗi sớm.

Ví dụ API `retry(operation)` có thể gọi `operation` nhiều lần; người gọi phải biết để tránh gửi lại thanh toán hoặc tạo tác dụng phụ trùng lặp. API `processAsync(callback)` cần nêu rõ callback có thể chạy trên luồng khác. Tên hàm và chữ ký SAM đơn thuần chưa đủ để suy ra số lần gọi hoặc luồng thực thi.

## 7. Capture biến, phạm vi và side effect

Lambda có thể dùng biến local bên ngoài nhưng biến local được capture phải là `final` hoặc **effectively final** (được gán một lần và không gán lại):

~~~java
int threshold = 80;
java.util.function.IntPredicate expensive =
        price -> price >= threshold;

System.out.println(expensive.test(100)); // true
~~~

Đoạn minh họa sau **không thể biên dịch**:

~~~java
int threshold = 80;
java.util.function.IntPredicate rule = p -> p >= threshold;
threshold = 100; // Không còn effectively final
~~~

Điều kiện effectively final áp dụng cho **biến local**, không làm đối tượng mà nó trỏ tới trở thành immutable. Lambda có thể sửa nội dung một collection được capture hoặc sửa field của object. Nếu callback được dùng ở nhiều luồng, phải xét đồng bộ hóa và chia sẻ trạng thái; effectively final không đảm bảo thread safety.

Các điểm cần nhớ:

- Trong lambda, `this` tham chiếu đối tượng bao quanh; lambda không tạo một `this` riêng như anonymous inner class.
- `return` bên trong thân lambda dạng khối chỉ kết thúc lambda, không kết thúc phương thức chứa nó.
- Side effect có thể hợp lý trong `Consumer`, nhưng phải rõ tác động và thứ tự thực thi; hạn chế dùng side effect trong các bước `Stream.map` hoặc `Stream.filter`.
- Nếu callback capture object lớn hoặc tài nguyên có vòng đời ngắn và được lưu giữ lâu, cần xét thời gian sống của những tham chiếu đó.

## 8. Những giới hạn và lỗi phổ biến

### 8.1. Phân biệt truyền giá trị với truyền hành vi

Giả sử có API `execute(Runnable action)`. Lời gọi `execute(doWork())` sẽ **thực thi `doWork()` trước** rồi truyền kết quả; nó còn có thể không biên dịch nếu `doWork` trả `void`. Khi muốn trì hoãn lời gọi, dùng `execute(() -> doWork())` hoặc một method reference phù hợp. Cần xác định nơi nào thực sự gọi `action.run()`.

### 8.2. Chọn đúng SAM

`Predicate.test` trả `boolean`; `Function.apply` trả một giá trị; `Consumer.accept` không trả kết quả; `Supplier.get` không nhận đầu vào. Tránh ép một loại hành vi vào interface mang ý nghĩa khác chỉ để mã biên dịch.

### 8.3. Checked exception

`Function.apply`, `Predicate.test`, `Consumer.accept` không khai báo checked exception như `IOException`. Lambda triển khai chúng phải tự xử lý checked exception hoặc dùng một functional interface tùy biến có chữ ký `throws`. Không nuốt lỗi rồi bỏ qua; hãy quy định cách xử lý ngoại lệ tại ranh giới callback. `Callable.call` có `throws Exception` nhưng phù hợp tác vụ có kết quả, không phải giải pháp thay thế chung cho tất cả API.

### 8.4. Target type và overload mơ hồ

Lambda không thể gán trực tiếp cho `Object` hay khai báo bằng `var` mà không có target type. Khi một tên phương thức bị overload bởi hai functional interface có chữ ký tương tự, lời gọi bằng lambda có thể mơ hồ. Nên ưu tiên tên phương thức dễ hiểu hoặc khai báo/ép kiểu đích một cách có chủ đích.

### 8.5. Hành vi phụ và hiệu năng

Callback có thể bị gọi nhiều lần, vì vậy tránh tác vụ nặng hoặc I/O ngoài ý muốn trong một predicate sẽ chạy với mọi phần tử. Với `Function<Integer,Integer>` trong vòng lặp lớn, boxing có thể phát sinh; cân nhắc `IntUnaryOperator` khi phù hợp và đo hiệu năng trước khi tối ưu. Không giả định mọi lambda “nhanh hơn” đối tượng thông thường; trình biên dịch/JVM quyết định triển khai và tối ưu thực tế.

## 9. Bài tập thực hành

**Bài 1 — Đổi quy tắc, không đổi thuật toán:** dùng `select` ở phần 3 để chọn sản phẩm có tên dài hơn hai ký tự; in tên của kết quả. Với dữ liệu mẫu, kết quả là `[Sach, But]`. Hãy chỉ ra phương thức `select` vẫn giữ nguyên.

**Bài 2 — Đổi phép biến đổi:** dùng `transform(products, Product::getPrice)` để lấy giá tất cả sản phẩm. Kết quả là `List<Integer>` chứa `[120, 30, 80]`. Giải thích vì sao getter trả `int` mà danh sách generic chứa `Integer` (boxing).

**Bài 3 — Người nhận kiểm soát số lần chạy:** tự viết `repeat(int times, Runnable action)`, gọi `action.run()` đúng số lần yêu cầu. Quy định `times < 0` và `action == null` phải được xử lý như thế nào; thử `times = 0`, `1`, `3` với một lambda in dòng văn bản.

## 10. Ghi nhớ

**Truyền hành vi như một tham số** tách cách xử lý có thể thay đổi khỏi quy trình chung. Java biểu diễn hành vi bằng đối tượng có kiểu functional interface; lambda và method reference giúp viết ngắn và rõ. Điều quan trọng hơn cú pháp là **hợp đồng thực thi callback**: loại đầu vào/đầu ra, thời điểm và số lần chạy, side effect, exception, capture biến và bối cảnh luồng. Các nguyên tắc này vẫn áp dụng rộng rãi trong Java hiện đại, từ Collection và Stream đến executor và nhiều API callback.
