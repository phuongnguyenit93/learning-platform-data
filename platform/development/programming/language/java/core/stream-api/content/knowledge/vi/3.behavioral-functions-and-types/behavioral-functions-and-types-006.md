# Biến được capture và yêu cầu effectively final

> **Chương:** Hàm hành vi và kiểu dữ liệu  
> **Bối cảnh:** Trong Java Stream API, `filter`, `map`, `reduce`, `collect` và nhiều thao tác khác nhận hàm hành vi dưới dạng lambda hoặc method reference. Khi các hàm này sử dụng biến ở phạm vi bên ngoài, Java áp dụng quy tắc **capture** và **effectively final**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định biến nào được một lambda **capture** và phân biệt biến cục bộ với field của đối tượng.
2. Giải thích quy tắc **final hoặc effectively final** khi lambda truy cập biến cục bộ, tham số phương thức và biến trong phạm vi bao ngoài.
3. Dự đoán đoạn mã nào biên dịch được, đoạn nào báo lỗi và cách sửa mà vẫn giữ đúng ý nghĩa xử lý.
4. Phân biệt **không gán lại một tham chiếu** với **không thay đổi trạng thái của đối tượng** mà tham chiếu trỏ đến.
5. Thiết kế lambda không phụ thuộc trạng thái thay đổi để xử lý Stream tuần tự hoặc song song an toàn hơn.
6. Thay các mẫu cộng dồn bằng biến bên ngoài bằng `sum`, `reduce` hoặc `collect` khi phù hợp.

Các ví dụ sử dụng cú pháp Java 17 trở lên (một số cú pháp lambda và Stream có sẵn từ Java 8; `Stream.toList()` có từ Java 16). Những đoạn minh họa ngắn được viết để đặt trong một phương thức, với `import` cần thiết được ghi kèm hoặc nêu rõ trong ví dụ.

## 1. Lambda dùng biến ở đâu?

Lambda là một biểu thức đại diện cho một hàm hành vi. Trong Stream API, ta thường truyền lambda cho các functional interface như:

| Functional interface | Phương thức trừu tượng | Ví dụ trong Stream |
|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | `filter(n -> n > limit)` |
| `Function<T, R>` | `R apply(T value)` | `map(name -> name.trim())` |
| `Consumer<T>` | `void accept(T value)` | `forEach(value -> log(value))` |
| `Supplier<T>` | `T get()` | Nhà cung cấp container khi dùng collector |
| `BinaryOperator<T>` | `T apply(T left, T right)` | `reduce((a, b) -> a + b)` |

Xét ví dụ:

~~~java
import java.util.List;

List<Integer> prices = List.of(45, 120, 75, 200);
int minimum = 100;

List<Integer> expensive = prices.stream()
        .filter(price -> price >= minimum)
        .toList();

System.out.println(expensive); // [120, 200]
~~~

Có hai tên xuất hiện trong lambda `price -> price >= minimum` nhưng vai trò rất khác nhau:

- `price` là **tham số** của lambda; Stream đưa từng phần tử vào tham số này.
- `minimum` là biến cục bộ được khai báo **ngoài** lambda nhưng được sử dụng **bên trong** lambda.

Việc lambda sử dụng `minimum` được gọi là **capture biến từ phạm vi bao ngoài** (*capturing a local variable*). Lambda có thể tiếp tục sử dụng giá trị đó sau khi lời gọi phương thức chứa biến cục bộ đã kết thúc, vì giá trị được capture được giữ theo ngữ nghĩa của đối tượng hàm, chứ không phụ thuộc vào việc giữ nguyên một ô biến cục bộ trên stack.

**Không phải tên nào xuất hiện trong lambda cũng được capture.** Tham số `price` là đầu vào của lambda; chỉ những biến hoặc tham chiếu từ phạm vi bên ngoài mới liên quan đến capture.

## 2. Quy tắc effectively final là gì?

Biến cục bộ được lambda sử dụng phải được khai báo `final` **hoặc effectively final**. Theo nghĩa thực hành:

- **`final` tường minh:** biến được khai báo với từ khóa `final` và không thể gán lại sau khi được gán giá trị theo quy tắc ngôn ngữ Java.
- **Effectively final:** biến **không có từ khóa** `final`, nhưng chương trình không gán lại biến sau lần gán giá trị hợp lệ ban đầu. Java có thể coi biến như một biến `final` cho mục đích capture.
- Phép gán lại `=`, phép gán kết hợp `+=`, `-=` hoặc toán tử `++`, `--` có thể khiến một biến **không còn effectively final**.

Ví dụ hợp lệ:

~~~java
import java.util.List;

List<Integer> values = List.of(4, 9, 12);

final int thresholdA = 8; // final tường minh
int thresholdB = 8;       // effectively final vì không bị gán lại

System.out.println(values.stream()
        .filter(n -> n > thresholdA)
        .toList()); // [9, 12]

System.out.println(values.stream()
        .filter(n -> n > thresholdB)
        .toList()); // [9, 12]
~~~

Ví dụ không hợp lệ:

~~~java
import java.util.List;

List<Integer> values = List.of(4, 9, 12);
int threshold = 8;
threshold = 10; // Biến threshold được gán lại

// Lỗi biên dịch: threshold không effectively final.
List<Integer> result = values.stream()
        .filter(n -> n > threshold)
        .toList();
~~~

Thông báo lỗi thường có dạng:

~~~text
Local variable threshold defined in an enclosing scope must be
final or effectively final
~~~

Lưu ý: **quy tắc xét cách biến được gán trong mã nguồn**, không xét liệu giá trị sau khi gán có vô tình bằng giá trị cũ hay không. Chẳng hạn `threshold = threshold;` vẫn là một phép gán lại và không làm biến trở thành effectively final.

### 2.1. “Chỉ gán một lần” không có nghĩa luôn phải gán tại dòng khai báo

Một biến có thể được gán ở những nhánh khác nhau miễn là trên **mỗi đường chạy hợp lệ**, biến được khởi tạo đúng và không bị gán lại.

~~~java
import java.util.function.IntPredicate;

boolean promotion = true;
int minimum;

if (promotion) {
    minimum = 50;
} else {
    minimum = 100;
}

IntPredicate passes = value -> value >= minimum;
System.out.println(passes.test(75)); // true
~~~

`minimum` là biến **effectively final** vì mọi đường chạy chỉ gán nó một lần, trước khi sử dụng trong lambda. Java còn yêu cầu biến được **definitely assigned** (đã được gán chắc chắn trước khi đọc); effectively final không thay thế yêu cầu khởi tạo này.

Trái lại:

~~~java
boolean promotion = true;
int minimum = 50;
if (promotion) {
    minimum = 100; // Gán lại biến đã được khởi tạo
}

// Predicate<Integer> p = x -> x >= minimum;
// Lỗi nếu lambda truy cập minimum.
~~~

Nếu mục tiêu là chọn giá trị cấu hình theo điều kiện, bạn có thể tính nó một lần:

~~~java
boolean promotion = true;
int minimum = promotion ? 50 : 100;

java.util.function.IntPredicate passes = value -> value >= minimum;
System.out.println(passes.test(75)); // true
~~~

Cú pháp `var` hay việc viết kiểu tường minh không thay đổi quy tắc effectively final; trong trường hợp này việc viết biểu thức điều kiện giúp rõ rằng `minimum` không được gán lại.

### 2.2. Tham số phương thức cũng chịu quy tắc này

~~~java
import java.util.function.IntPredicate;

class Filters {
    static IntPredicate greaterThan(int limit) {
        return value -> value > limit; // limit là tham số được capture
    }
}
~~~

`limit` không được gán lại trong phương thức nên effectively final. Nếu thêm `limit++` trong cùng phương thức, việc capture đó sẽ không biên dịch.

Biến cục bộ được khai báo trong phạm vi bao ngoài của **anonymous class** cũng phải đáp ứng quy tắc tương tự. Đây không phải giới hạn chỉ dành riêng cho cú pháp lambda.

## 3. Vì sao Java yêu cầu effectively final?

Hãy phân biệt hai việc:

1. **Giữ giá trị để hàm có thể dùng về sau.**
2. **Giữ một ô biến cục bộ dùng chung để hàm và phương thức bên ngoài liên tục sửa chung.**

Java lựa chọn ngữ nghĩa capture theo **giá trị** đối với biến cục bộ: giá trị nguyên thủy được giữ như giá trị, còn biến tham chiếu được giữ như một **tham chiếu** tới đối tượng. Không có cam kết rằng lambda đang nắm một ô biến cục bộ có thể gán lại trong phạm vi bên ngoài.

Ví dụ một lambda được trả về để dùng sau:

~~~java
import java.util.function.IntPredicate;

class PredicateFactory {
    static IntPredicate atLeast(int minimum) {
        return value -> value >= minimum;
    }

    public static void main(String[] args) {
        IntPredicate adultAge = atLeast(18);

        System.out.println(adultAge.test(16)); // false
        System.out.println(adultAge.test(20)); // true
    }
}
~~~

Khi `atLeast(18)` trả về, biến tham số `minimum` của lời gọi đó không còn ở phạm vi thực thi ban đầu; `adultAge` vẫn dùng được giá trị `18` đã capture.

Yêu cầu effectively final làm ngữ nghĩa này rõ ràng: lập trình viên không thể viết tiếp `minimum = 21` ở một đoạn mã bao ngoài rồi mặc nhiên kỳ vọng lambda giữ một liên kết trực tiếp đến ô biến cục bộ ấy.

Với Stream API, quy tắc này đặc biệt hữu ích vì thao tác trung gian thường **lazy**: lambda được khai báo trước nhưng có thể được gọi sau, khi một thao tác kết thúc chạy.

## 4. Capture giá trị nguyên thủy và capture tham chiếu là hai chuyện khác nhau

### 4.1. Với kiểu nguyên thủy: giá trị được giữ

~~~java
import java.util.function.IntPredicate;

int threshold = 10;
IntPredicate greaterThan = value -> value > threshold;

System.out.println(greaterThan.test(12)); // true

// threshold = 20; // Nếu bỏ comment, lỗi biên dịch.
~~~

Ở đây, lambda dùng giá trị `10`. Đó không phải một biến độc lập trong lambda để mã bên ngoài có thể gán lại.

### 4.2. Với đối tượng: tham chiếu không đổi nhưng nội dung có thể đổi

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

List<String> acceptedNames =
        new ArrayList<>(List.of("An", "Bình"));

Predicate<String> accepted =
        name -> acceptedNames.contains(name);

System.out.println(accepted.test("Chi")); // false

acceptedNames.add("Chi"); // Thay đổi nội dung List, không gán lại biến
System.out.println(accepted.test("Chi")); // true
~~~

Biến cục bộ `acceptedNames` **vẫn effectively final**: nó chưa từng nhận một tham chiếu mới. Tuy nhiên, đối tượng `ArrayList` mà biến này tham chiếu đã thay đổi.

Đây là điểm dễ nhầm nhất:

| Điều gì thay đổi? | Có làm biến cục bộ mất effectively final không? | Có thể thay đổi hành vi lambda không? |
|---|---|---|
| `threshold = 20` sau khi đã khởi tạo `threshold` | **Có** | Không biên dịch nếu lambda capture biến đó |
| `names = new ArrayList<>()` sau khi đã khởi tạo `names` | **Có** | Không biên dịch nếu lambda capture biến đó |
| `names.add("Chi")` | **Không** | **Có**, nếu lambda đọc nội dung `names` |
| `array[0]++` | **Không** | **Có**, nếu lambda đọc `array[0]` |
| `object.setStatus("DONE")` | **Không** | **Có**, nếu lambda đọc trạng thái của đối tượng |

Từ khóa `final` cũng **không làm đối tượng bất biến**:

~~~java
import java.util.ArrayList;
import java.util.List;

final List<Integer> numbers = new ArrayList<>();
numbers.add(10); // Hợp lệ: đổi nội dung đối tượng

// numbers = new ArrayList<>(); // Lỗi: không thể gán lại biến final
~~~

Nếu muốn dữ liệu thật sự ổn định cho quá trình lọc, cần thiết kế cấu trúc dữ liệu bất biến, tạo bản chụp dữ liệu phù hợp, hoặc tránh thay đổi trạng thái mà lambda phụ thuộc. Một tham chiếu effectively final **không đồng nghĩa** với thread-safe.

### 4.3. Stream lazy có thể quan sát trạng thái đối tượng tại thời điểm chạy

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<Integer> allowed = new ArrayList<>(List.of(2, 4));
Stream<Integer> pipeline = List.of(1, 2, 3, 4).stream()
        .filter(allowed::contains);

allowed.add(3); // Thay đổi danh sách dùng để kiểm tra, trước terminal operation.

System.out.println(pipeline.toList()); // [2, 3, 4]
~~~

Stream được khai báo trước nhưng `filter` thực thi khi gọi `toList()`. Lambda/method reference giữ tham chiếu tới `allowed`; nó **không chụp toàn bộ nội dung** của `ArrayList` tại thời điểm tạo pipeline.

Ví dụ trên chỉ minh họa một thay đổi **tuần tự trước khi tiêu thụ** trên danh sách phụ dùng để kiểm tra, không thay đổi trực tiếp nguồn `List.of(1, 2, 3, 4)`. Việc thay đổi trạng thái mà predicate đọc **trong khi pipeline đang chạy** có thể tạo kết quả thiếu ổn định, đặc biệt ở Stream song song.

Khi cần kết quả cố định theo cấu hình ban đầu, chụp giá trị hoặc dữ liệu một cách có chủ đích:

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

Set<Integer> allowedSnapshot = Set.copyOf(List.of(2, 4));
Predicate<Integer> isAllowed = allowedSnapshot::contains;

System.out.println(
        List.of(1, 2, 3, 4).stream().filter(isAllowed).toList()
); // [2, 4]
~~~

`Set.copyOf` tạo tập hợp không thể thay đổi cấu trúc; ở đây các phần tử `Integer` cũng bất biến. Với tập chứa đối tượng mutable, việc sao chép collection như vậy chỉ sao chép các tham chiếu phần tử, không tự động biến từng đối tượng thành bất biến.

## 5. Capture biến cục bộ khác truy cập field

Yêu cầu effectively final áp dụng cho **biến cục bộ được capture**, bao gồm tham số phương thức, chứ không cấm mọi dạng thay đổi trạng thái trong lambda.

~~~java
import java.util.List;

class ThresholdFilter {
    private int threshold = 10; // Field của đối tượng

    List<Integer> filter(List<Integer> source) {
        return source.stream()
                .filter(n -> n > threshold) // Đọc field qua this
                .toList();
    }

    void setThreshold(int newValue) {
        threshold = newValue; // Hợp lệ về mặt biên dịch
    }
}
~~~

Ở đây lambda truy cập `this.threshold`; `this` trong lambda chỉ **đối tượng bao ngoài**, không phải một đối tượng `this` mới như trong anonymous class. Field có thể được gán lại nên không bị ràng buộc bởi quy tắc effectively final của biến cục bộ.

Tuy nhiên, **hợp lệ khi biên dịch không có nghĩa an toàn khi chạy đồng thời**. Nếu thread khác thay đổi `threshold` trong lúc Stream xử lý, ứng dụng cần quyết định rõ cách đồng bộ, khả năng nhìn thấy thay đổi (*visibility*) và tính nhất quán. Chỉ thêm `volatile` vào field có thể hỗ trợ visibility trong một số trường hợp, nhưng không làm toàn bộ phép tính phức hợp trở nên nguyên tử hay tạo snapshot nhất quán.

Một lựa chọn dễ dự đoán hơn là cố định cấu hình tại đầu phương thức:

~~~java
import java.util.List;

class ThresholdFilter {
    private int threshold = 10;

    List<Integer> filter(List<Integer> source) {
        int currentThreshold = threshold; // Snapshot giá trị primitive
        return source.stream()
                .filter(n -> n > currentThreshold)
                .toList();
    }
}
~~~

`currentThreshold` effectively final nên mọi lần gọi predicate trong pipeline của lần gọi `filter` này dùng cùng giá trị. Nếu có nhiều thread cùng truy cập field, việc đọc snapshot vẫn phải tuân theo thiết kế đồng bộ/visibility của ứng dụng.

### 5.1. Method reference cũng có thể giữ receiver

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

Set<String> allowed = Set.of("java", "stream");
Predicate<String> predicate = allowed::contains;

System.out.println(
        List.of("java", "sql", "stream").stream()
                .filter(predicate)
                .toList()
); // [java, stream]
~~~

`allowed::contains` là **bound method reference**: nó giữ receiver `allowed`. Quy tắc về capture tham chiếu và trạng thái mutable cũng cần được cân nhắc khi thay receiver bằng một đối tượng mutable. Method reference không tự làm cho mã thuần khiết (*pure*) hoặc an toàn song song.

## 6. Vì sao cộng dồn vào biến ngoài lambda gây lỗi?

Một mẫu rất thường gặp khi chuyển từ vòng lặp sang Stream:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int total = 0;

// LỖI BIÊN DỊCH:
// values.stream().forEach(value -> total += value);
~~~

`total += value` là phép gán lại biến cục bộ `total`. Vì bị capture trong lambda, `total` phải effectively final và phép gán lại này bị cấm.

Vòng lặp truyền thống không có ràng buộc capture:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int total = 0;

for (int value : values) {
    total += value;
}

System.out.println(total); // 10
~~~

Đây là trường hợp **vòng lặp thường hoàn toàn hợp lý**. Nếu chọn Stream, hãy diễn đạt việc tổng hợp bằng API thay vì tìm cách lách hạn chế của lambda.

### 6.1. Dùng tổng hợp chuyên biệt: sum, count, average

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

int total = values.stream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 10
~~~

`mapToInt` biến `Stream<Integer>` thành `IntStream`, sau đó `sum()` thực hiện phép cộng. Với dữ liệu có thể vượt giới hạn `int`, cần cân nhắc `mapToLong` / `LongStream.sum` hoặc `BigInteger` / `BigDecimal` tùy yêu cầu chính xác. Phép cộng `int` trong Java có thể tràn số.

### 6.2. Dùng reduce cho phép tổng hợp có tính kết hợp

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

int total = values.stream()
        .reduce(0, Integer::sum);

System.out.println(total); // 10
~~~

Trong `reduce(identity, accumulator)`, thao tác gộp cần đáp ứng hợp đồng về **phần tử đơn vị** (*identity*) và **tính kết hợp** (*associativity*) để đặc biệt phù hợp khi chia và gộp trong Stream song song. Ví dụ phép cộng số nguyên ở trên có identity là `0` và kết hợp theo quy tắc số học modulo 32-bit của `int` trong Java.

Đừng biến `reduce` thành thao tác sửa một container mutable được chia sẻ giữa các thread. Với việc gom vào danh sách, map hay nhóm, `collect` và collector thích hợp thường đúng hơn.

### 6.3. Dùng collect để thu thập và nhóm dữ liệu

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = List.of("java", "jdk", "stream", "sql");

Map<Integer, List<String>> byLength = words.stream()
        .collect(Collectors.groupingBy(String::length));

System.out.println(byLength.get(3)); // [jdk, sql]
~~~

Thư viện quản lý container của collector và quá trình gộp kết quả. Bạn không cần một biến `Map` bên ngoài rồi gọi `computeIfAbsent` trong `forEach`. Với Stream song song, framework có thể cung cấp từng container cục bộ cho các phần xử lý và gộp bằng combiner theo hợp đồng collector; việc đó khác với mọi lambda cùng sửa một `ArrayList` hoặc `HashMap` chia sẻ.

## 7. Cách “lách” effectively final bằng đối tượng mutable: hợp lệ nhưng dễ sai

Một cách để làm đoạn cộng dồn biên dịch là bọc số trong mảng:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int[] total = {0};

values.stream().forEach(value -> total[0] += value);

System.out.println(total[0]); // 10 với pipeline tuần tự này
~~~

Biến cục bộ `total` vẫn giữ **cùng tham chiếu tới mảng**, nên effectively final. Nhưng phần tử `total[0]` có thể thay đổi.

Điều này **không phải cách viết được khuyến khích** cho tổng hợp dữ liệu: lambda đang có side effect lên trạng thái bên ngoài. Đổi thành parallel stream sẽ tạo ra race condition:

~~~java
import java.util.stream.IntStream;

int[] total = {0};

IntStream.rangeClosed(1, 100_000)
        .parallel()
        .forEach(n -> total[0] += n); // Data race, có thể mất lượt cộng

System.out.println(total[0]); // Kết quả không đáng tin cậy
~~~

Phép `total[0] += n` là đọc–cộng–ghi, không phải một thao tác cập nhật nguyên tử. Nhiều thread có thể đọc cùng giá trị cũ rồi ghi đè nhau. Đừng dựa vào kết quả tình cờ đúng trong một vài lần chạy.

Thay bằng:

~~~java
import java.util.stream.IntStream;

long total = IntStream.rangeClosed(1, 100_000)
        .parallel()
        .asLongStream()
        .sum();

System.out.println(total); // 5_000_050_000
~~~

Dùng `long` vì tổng vượt giới hạn của `int`. Không có trạng thái cộng dồn ở phạm vi ngoài; phép tổng hợp do Stream quản lý.

### 7.1. AtomicInteger có giải quyết vấn đề không?

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger total = new AtomicInteger();

IntStream.rangeClosed(1, 1_000)
        .parallel()
        .forEach(total::addAndGet);

System.out.println(total.get()); // 500500
~~~

Trong ví dụ **đọc toàn bộ stream** này, `AtomicInteger` cho phép cập nhật nguyên tử và tổng đúng trong phạm vi `int`. Nhưng nó vẫn tạo trạng thái chia sẻ, cạnh tranh cập nhật, phụ thuộc vào side effect và có thể làm mất lợi ích xử lý song song.

Nghiêm trọng hơn, một pipeline có **thao tác dừng sớm** như `findAny`, `anyMatch` hoặc `limit` không đảm bảo mọi phần tử đều được xử lý; đếm side effect trong `filter`/`map` có thể không khớp với số phần tử mong đợi. Thư viện Stream có thể bỏ qua một số thao tác trung gian khi việc tối ưu không ảnh hưởng kết quả được định nghĩa.

**Kết luận thiết kế:** `AtomicInteger` hữu ích cho mục đích đồng bộ phù hợp, nhưng không nên dùng như mặc định để thay `sum`, `count`, `reduce` hoặc `collect`.

## 8. Capture trong vòng lặp: lỗi đặc trưng của chỉ số for

Xét đoạn mã muốn lưu ba tác vụ để chạy sau:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

// LỖI BIÊN DỊCH: i++ khiến i không effectively final.
// for (int i = 0; i < 3; i++) {
//     tasks.add(() -> System.out.println(i));
// }
~~~

`i` thay đổi sau mỗi vòng lặp, nên không được capture trực tiếp. Giải pháp là tạo một biến riêng cho **mỗi lần lặp**:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

for (int i = 0; i < 3; i++) {
    int snapshot = i;
    tasks.add(() -> System.out.println(snapshot));
}

tasks.forEach(Runnable::run);
// 0
// 1
// 2
~~~

Mỗi lần vào thân vòng lặp tạo một biến `snapshot` khác nhau, được gán một lần. Không phải “bỏ quy tắc effectively final” mà là tạo dữ liệu capture hợp lệ.

Vòng lặp enhanced for thường đơn giản hơn:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

for (String name : List.of("An", "Bình", "Chi")) {
    tasks.add(() -> System.out.println(name));
}

tasks.forEach(Runnable::run);
// An
// Bình
// Chi
~~~

Biến duyệt `name` trong enhanced for tương ứng với một biến riêng cho mỗi lượt lặp nên có thể effectively final khi không bị gán lại trong thân vòng lặp. Đừng nhầm với một chỉ số `i` được tăng qua nhiều lượt bằng `i++`.

## 9. Effectively final trong pipeline lazy

Một biến cục bộ được capture phải effectively final ngay từ góc nhìn trình biên dịch, bất kể bạn gọi terminal operation ngay hay sau đó:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = List.of(2, 5, 8, 11);
int threshold = 6;

Stream<Integer> pipeline = values.stream()
        .filter(value -> value > threshold); // Chưa duyệt giá trị

System.out.println("Pipeline đã được tạo");
System.out.println(pipeline.toList());        // [8, 11]
~~~

Nếu thêm `threshold = 9;` ở sau khi tạo pipeline, chương trình sẽ **không biên dịch**, dù thao tác gán đó nằm trước `toList()`. Java không thiết lập một liên kết sống để lambda tự đọc giá trị mới của biến cục bộ.

Một cách xử lý hợp lệ khi yêu cầu nghiệp vụ muốn đổi ngưỡng là **tạo pipeline mới theo cấu hình mới**:

~~~java
import java.util.List;

List<Integer> values = List.of(2, 5, 8, 11);

int firstThreshold = 6;
List<Integer> first = values.stream()
        .filter(n -> n > firstThreshold)
        .toList();

int secondThreshold = 9;
List<Integer> second = values.stream()
        .filter(n -> n > secondThreshold)
        .toList();

System.out.println(first);  // [8, 11]
System.out.println(second); // [11]
~~~

Đây cũng là cách biểu đạt rõ ý định hơn khi mỗi lần xử lý cần một cấu hình cố định. Một đối tượng Stream đã có terminal operation không thể tái sử dụng; tạo Stream mới từ collection có thể duyệt lại là hợp lý.

## 10. Stateless và non-interfering: hai yêu cầu liên quan nhưng khác nhau

Với Stream, đặc biệt là parallel stream, các hàm hành vi thường phải:

- **Stateless (không phụ thuộc trạng thái thay đổi):** kết quả xử lý một phần tử không phụ thuộc vào trạng thái có thể thay đổi trong khi pipeline đang chạy, chẳng hạn biến đếm ngoài hay field liên tục được cập nhật.
- **Non-interfering (không can thiệp):** không sửa nguồn dữ liệu không hỗ trợ sửa đổi đồng thời trong khi Stream đang duyệt.

Effectively final chỉ nói về **khả năng gán lại một biến cục bộ**. Nó **không đảm bảo** lambda stateless hoặc non-interfering.

Ví dụ không nên làm:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Tránh: tác dụng phụ sửa chính nguồn trong lúc đang duyệt.
// numbers.stream().forEach(n -> numbers.add(n * 2));
~~~

Ví dụ trên có thể ném ngoại lệ hoặc dẫn tới kết quả không xác định theo cách triển khai. Dù biến `numbers` effectively final, lambda đang sửa chính collection nguồn.

Một cách thuần túy hơn:

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4);

List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8]
System.out.println(numbers); // [1, 2, 3, 4]
~~~

Lambda `n -> n * 2` là phép biến đổi độc lập từng phần tử. Stream có nhiều tự do hơn trong việc chọn thứ tự thực thi, dừng sớm hoặc chạy song song mà không làm thay đổi giá trị được mô tả.

### 10.1. Side effect trong thao tác trung gian có thể gây hiểu nhầm

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3);

long count = numbers.stream()
        .map(n -> {
            System.out.println("map: " + n);
            return n * 2;
        })
        .count();

System.out.println("count = " + count);
~~~

Với nguồn `List` đã biết kích thước, một triển khai Stream hợp lệ có thể suy ra `count()` mà **không cần chạy `map`**. Vì thế đừng sử dụng `map` hoặc `peek` để thực hiện một hiệu ứng bắt buộc (ghi log nghiệp vụ, cập nhật dữ liệu, trừ tiền, tăng bộ đếm).

Nếu tác dụng phụ là mục tiêu thực sự, nên diễn đạt rõ nó bằng thao tác kết thúc có chủ đích hoặc một vòng lặp thích hợp, đồng thời cân nhắc thứ tự và đồng thời. `forEach` trên parallel stream **không đảm bảo thứ tự encounter order**; `forEachOrdered` giữ thứ tự với nguồn có thứ tự nhưng có thể hạn chế hiệu năng.

### 10.2. Đọc field mutable trong parallel stream có an toàn không?

Ví dụ một lambda `n -> n > configuration.minimum()` có thể được capture hợp lệ thông qua biến tham chiếu `configuration` effectively final, nhưng nếu thread khác đồng thời sửa trạng thái của `configuration` thì các lượt xử lý có thể thấy những giá trị khác nhau hoặc gặp vấn đề visibility.

Thường nên tạo cấu hình bất biến cho một đợt xử lý:

~~~java
import java.util.List;

int minimumForRun = 10;

List<Integer> result = List.of(5, 12, 20, 8)
        .parallelStream()
        .filter(n -> n >= minimumForRun)
        .toList();

System.out.println(result); // [12, 20]
~~~

Các phép lọc độc lập và dữ liệu cấu hình cố định trong ví dụ giúp dễ phân tích hơn. Tuy vậy, effectively final **không phải** kiểm chứng an toàn song song cho toàn bộ thuật toán: collector, đối tượng phần tử, nguồn, thứ tự và các phép tổng hợp vẫn cần được xét theo hợp đồng của Stream API.

## 11. Capture trong callback, method reference và tài nguyên

Các điểm cần nhớ khi kết hợp với những nguồn Stream khác:

**Callback giữ dữ liệu từ phạm vi bao ngoài:** ví dụ `fileName` trong `line -> line.contains(fileName)` phải effectively final nếu là biến cục bộ. Chỉ vì callback được gọi ở mã thư viện, quy tắc capture vẫn áp dụng.

**Không được coi capture là cơ chế quản lý tài nguyên:** một lambda có thể giữ tham chiếu tới đối tượng `Reader` hoặc cấu hình I/O, nhưng điều đó không tự đóng tài nguyên, không kéo dài vòng đời tài nguyên một cách có kiểm soát, và không cho phép sử dụng an toàn sau khi đóng.

**Stream có nguồn I/O phải được đóng khi cần:**

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("application.log");
String marker = "ERROR"; // Effectively final

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines
            .filter(line -> line.contains(marker))
            .count();

    System.out.println("Số dòng lỗi: " + errors);
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Không thể đọc log: " + ex.getMessage());
}
~~~

`marker` được capture; `Files.lines` cung cấp nguồn dữ liệu lazy từ tệp. `try-with-resources` đóng Stream và giải phóng tài nguyên liên quan. Quy tắc effectively final và quy tắc đóng tài nguyên giải quyết **hai vấn đề độc lập**, cả hai đều quan trọng trong pipeline thực tế.

Về các chủ đề nâng cao của module — collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers — bài học này cung cấp một nguyên tắc nền: **hàm xử lý nên giao tiếp qua tham số và giá trị trả về, tránh phụ thuộc vào trạng thái chia sẻ có thể thay đổi**. Nếu một thao tác thật sự cần trạng thái, hãy dùng cơ chế quản lý trạng thái và hợp đồng đồng thời của API tương ứng, thay vì tự tạo biến chung bên ngoài lambda.

## 12. Quy trình sửa lỗi capture mà vẫn đúng thiết kế

Khi thấy thông báo *must be final or effectively final*, hãy kiểm tra lần lượt:

1. **Biến nào đang được capture?** Phân biệt tham số của lambda với biến địa phương ngoài lambda.
2. **Biến bị gán lại ở đâu?** Tìm phép gán `=`, `+=`, `++` hoặc `--` trên biến trong phạm vi bao ngoài, kể cả phép gán nằm sau biểu thức lambda.
3. **Giá trị thực sự cần thay đổi hay chỉ cần chọn một lần?** Nếu chỉ là cấu hình cho mỗi đợt xử lý, tính một giá trị cuối cùng bằng điều kiện hoặc tạo biến snapshot.
4. **Có đang tích lũy kết quả?** Dùng `sum`, `count`, `reduce`, `collect`; hoặc vòng lặp thường nếu nó rõ ràng và phù hợp.
5. **Có đang thay đổi đối tượng được capture?** Đảm bảo không sửa chính nguồn Stream và không đưa trạng thái chia sẻ thiếu đồng bộ vào tác vụ song song.
6. **Có dùng tài nguyên ngoài không?** Đảm bảo vòng đời I/O đúng, độc lập với capture.

| Tình huống | Cách sửa phù hợp | Tránh |
|---|---|---|
| `int limit = 5; limit = 10; filter(n -> n > limit)` | Tính `limit` một lần hoặc tạo `finalLimit` dùng cho pipeline | Dùng mảng một phần tử chỉ để né lỗi |
| `int total = 0; forEach(n -> total += n)` | `mapToInt(...).sum()` hoặc `reduce` | Tạo biến mutable chia sẻ |
| `for (int i = 0; i < n; i++)` và lambda dùng `i` | `int index = i` trong mỗi lượt | Mong lambda tự giữ giá trị `i` từng lượt |
| Lambda đọc cấu hình đối tượng hay thay đổi | Snapshot bất biến cho lần xử lý, đồng bộ khi cần | Cho thread khác sửa cấu hình trong lúc chạy |
| Lambda thêm phần tử vào chính nguồn Stream | Tạo collection kết quả bằng `map`/`filter`/`collect` | Sửa nguồn trong `forEach` |
| Đọc tệp qua `Files.lines` | `try-with-resources` và pipeline rõ ràng | Giả định terminal operation tự đóng Stream |

## 13. Bài tập tự kiểm tra

### Bài 1. Biên dịch được không?

~~~java
import java.util.List;

int a = 10;
int b = a + 5;

List<Integer> numbers = List.of(1, 10, 20);
List<Integer> filtered = numbers.stream()
        .filter(n -> n > b)
        .toList();
~~~

**Đáp án:** Có. `a` và `b` đều được gán đúng một lần. `b` được capture hợp lệ; kết quả `filtered` là `[20]`.

### Bài 2. Có thể đổi giá trị phía ngoài khi đã tạo lambda không?

~~~java
import java.util.function.IntPredicate;

int minimum = 10;
IntPredicate predicate = value -> value >= minimum;
// minimum = 20;
~~~

**Đáp án:** Không thể bỏ comment dòng cuối mà vẫn biên dịch: biến cục bộ `minimum` không còn effectively final. Nếu muốn hai ngưỡng, tạo hai predicate hoặc truyền ngưỡng thành tham số một hàm tạo predicate.

### Bài 3. Tại sao vẫn quan sát được giá trị thay đổi?

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

List<String> names = new ArrayList<>();
Supplier<Integer> size = names::size;

names.add("An");
names.add("Bình");

System.out.println(size.get());
~~~

**Đáp án:** In `2`. Tham chiếu `names` không bị gán lại nhưng nội dung `ArrayList` thay đổi; bound method reference `names::size` đọc kích thước hiện thời.

### Bài 4. Có nên dùng `int[] total` với parallel stream?

**Đáp án:** Không nên: `total[0] += n` là phép cập nhật không nguyên tử và có thể xảy ra data race. Dùng `mapToLong(...).sum()`, `reduce` hoặc collector phù hợp để tổng hợp.

### Bài 5. Sửa lỗi capture trong vòng lặp

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

// Sai:
// for (int i = 1; i <= 3; i++) {
//     tasks.add(() -> System.out.println(i));
// }
~~~

**Đáp án tham khảo:**

~~~java
for (int i = 1; i <= 3; i++) {
    int itemNumber = i;
    tasks.add(() -> System.out.println(itemNumber));
}

tasks.forEach(Runnable::run); // 1, 2, 3 theo thứ tự thêm
~~~

### Bài 6. Effectively final có đảm bảo hàm thuần khiết không?

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntUnaryOperator;

AtomicInteger counter = new AtomicInteger();
IntUnaryOperator op = x -> x + counter.incrementAndGet();
~~~

**Đáp án:** Không. `counter` là biến cục bộ effectively final nhưng lambda sửa trạng thái của đối tượng `AtomicInteger` ở mỗi lần gọi. Kết quả `op.applyAsInt(10)` phụ thuộc vào số lần gọi và thứ tự gọi trước đó. Atomic giúp cập nhật bộ đếm an toàn về tính nguyên tử; nó không làm lambda stateless.

---

**Ghi nhớ:** Khi lambda hoặc method reference cần dùng biến cục bộ từ phạm vi bên ngoài, biến đó phải **final hoặc effectively final**. Quy tắc áp dụng cho **việc gán lại biến**, không bảo đảm đối tượng được tham chiếu là bất biến. Với Java Stream API, giải pháp bền vững nhất thường là dùng **giá trị cấu hình cố định**, viết các hàm hành vi **không can thiệp nguồn**, và để `reduce`/`collect`/các phép tổng hợp chuyên biệt quản lý kết quả, nhất là khi xử lý song song.

