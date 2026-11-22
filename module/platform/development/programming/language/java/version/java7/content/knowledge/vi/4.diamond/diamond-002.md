# Suy luận tham số khi khởi tạo bằng dấu `<>` (Diamond Operator)

> **Chủ đề: Java 7 / Diamond.** Dấu `<>` trong biểu thức `new GenericType<>()` cho phép trình biên dịch suy luận **đối số kiểu generic** khi tạo đối tượng, nhờ ngữ cảnh của biểu thức và ràng buộc constructor. Tính năng xuất hiện từ Java 7 và vẫn được dùng hằng ngày trong Java 17, 21 và các JDK hiện đại. Bài này chỉ tập trung vào cơ chế và cách dùng còn giá trị hiện nay, đồng thời chỉ rõ các cải tiến Java 8/9/10 khi kết hợp với diamond.

## 1. Diamond `<>` giải quyết vấn đề gì?

Trước khi có cú pháp này, lập trình viên phải lặp lại các đối số kiểu ở cả hai phía của phép gán. Kể từ Java 7, biểu thức tạo đối tượng có thể để trình biên dịch suy luận phần bên phải:

```java
// Cú pháp vẫn hợp lệ nhưng thường dài dòng không cần thiết:
List<String> names = new ArrayList<String>();

// Diamond operator: kiểu đối số trên vế phải được compiler suy luận.
List<String> names = new ArrayList<>();
```

Đây là **đoạn minh họa cú pháp**; hai khai báo cùng tên chỉ để đối chiếu, không đặt nguyên cả hai vào cùng một scope. Trong thực tế, khai báo duy nhất với diamond vừa gọn vừa vẫn giữ kiểm tra kiểu. Biến `names` có kiểu **`List<String>`** tại thời điểm biên dịch, còn đối tượng khởi tạo là một **`ArrayList<String>`**.

Một số ví dụ phổ biến khác:

```java
Map<String, Integer> scores = new HashMap<>();
Set<Long> ids = new HashSet<>();
Deque<String> queue = new ArrayDeque<>();
Map<String, List<Integer>> index = new LinkedHashMap<>();
```

Tất cả là *snippet* đặt trong method/class phù hợp và cần import từ `java.util`. Diamond đặc biệt hữu ích khi khai báo generic lồng nhau: `new LinkedHashMap<>()` không cần chép lại `String, List<Integer>`.

**Đọc đúng dấu `<>`:**

- Phía trái `List<String>` là một **kiểu tham số hóa**, trong đó `String` đã được nêu tường minh.
- Phía phải `new ArrayList<>()` là một **biểu thức gọi constructor** sử dụng diamond; compiler suy ra đối số kiểu cụ thể.
- `<>` **không phải kiểu Object**, không có nghĩa “bỏ qua generic”, cũng không tạo “generic động” lúc chạy.
- Diamond không thay thế tên lớp hoặc constructor: ta vẫn phải viết `new ArrayList<>()` hay `new HashMap<>()` và quyết định loại collection thích hợp.

## 2. Trình biên dịch suy luận kiểu như thế nào?

Khi gặp `new ArrayList<>()`, trình biên dịch dựa vào các thông tin có sẵn để xác định tham số kiểu, chẳng hạn:

1. **Kiểu đích (target type)** ở biểu thức khai báo/gán hoặc ngữ cảnh tương thích, ví dụ `List<String>`.
2. **Các đối số truyền vào constructor**, ví dụ một collection các `String`.
3. **Các ràng buộc của lớp/constructor** (generic bounds) và khả năng chuyển kiểu hợp lệ.

Trong trường hợp thông thường:

```java
List<String> result = new ArrayList<>();
```

Ta có thể hiểu compiler xác định `E = String` đối với `ArrayList<E>`, vì biểu thức khởi tạo phải tương thích với `List<String>`. Việc suy luận diễn ra **khi biên dịch**; chương trình không phải suy luận lại mỗi lần chạy. Nếu compiler không tìm được nghiệm thỏa ràng buộc, mã nguồn không biên dịch.

### 2.1. Suy luận từ kiểu đích

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
Map<String, List<Long>> lookup = new HashMap<>();
```

Cùng một cú pháp `new ArrayList<>()` nhưng đối số kiểu khác nhau do **ngữ cảnh khai báo**. Dấu diamond không mặc định mọi collection thành `List<Object>` khi đã có kiểu đích rõ ràng.

### 2.2. Suy luận từ đối số constructor

```java
List<String> original = List.of("A", "B");
List<String> copied = new ArrayList<>(original);
```

Constructor `ArrayList(Collection<? extends E>)` cung cấp thêm thông tin về `E`. Đối tượng mới là danh sách có thể sửa, chứa các phần tử được sao chép từ `original`. `List.of(...)` được thêm ở **Java 9**; diamond vẫn là cơ chế ra đời ở Java 7. Không nên đồng nhất việc **sao chép dữ liệu** với việc **suy luận tham số kiểu**: đó là hai vai trò khác nhau của cùng biểu thức.

### 2.3. Suy luận có giới hạn

Diamond không “đoán” kiểu nghiệp vụ từ ý nghĩa biến. Ví dụ:

```java
var values = new ArrayList<>();
```

Từ **Java 10**, `var` yêu cầu trình biên dịch suy luận *kiểu biến cục bộ* từ biểu thức khởi tạo. Vì ở đây không có đối số constructor hay kiểu `List<String>` ở vế trái để ràng buộc `E`, kiểu nhận được là **`ArrayList<Object>`**. Đây là hai cơ chế suy luận khác nhau: **diamond cho đối số kiểu constructor** và **`var` cho kiểu biến cục bộ**. Phần 6 sẽ kiểm tra hệ quả này bằng chương trình chạy được.

## 3. Ví dụ hoàn chỉnh: collection generic với diamond

Lưu thành `DiamondBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DiamondBasicsDemo {
    public static void main(String[] args) {
        List<String> languages = new ArrayList<>();
        languages.add("Java");
        languages.add("Kotlin");

        Map<String, List<Integer>> versions = new LinkedHashMap<>();
        versions.put("Java", new ArrayList<>());
        versions.get("Java").add(7);
        versions.get("Java").add(17);

        System.out.println("languages=" + languages);
        System.out.println("versions=" + versions);
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac -encoding UTF-8 --release 17 DiamondBasicsDemo.java
java DiamondBasicsDemo
```

Stdout:

```text
languages=[Java, Kotlin]
versions={Java=[7, 17]}
```

**Vì sao hoạt động?**

- `languages` yêu cầu `List<String>` nên `new ArrayList<>()` nhận kiểu đối số `String`.
- `versions` có kiểu `Map<String, List<Integer>>` nên `new LinkedHashMap<>()` suy luận hai đối số kiểu `String` và `List<Integer>`.
- `versions.put("Java", new ArrayList<>())` đặt biểu thức diamond vào ngữ cảnh tham số `List<Integer>` của lời gọi `put`, giúp suy luận `Integer`.
- `languages.add(123)` sẽ **không biên dịch** do `123` không phải `String`. Diamond không làm mất cơ chế kiểm tra kiểu.
- `LinkedHashMap` được dùng để thứ tự in ở ví dụ có thể dự đoán theo thứ tự chèn; chọn cấu trúc dữ liệu là quyết định riêng, không liên quan đến diamond.

## 4. Diamond với generic class tự định nghĩa

Diamond dùng được với **lớp generic do chính bạn định nghĩa**, miễn biểu thức tạo đối tượng và các ràng buộc kiểu phù hợp. Không chỉ dành cho collection của JDK.

Lưu thành `DiamondPairDemo.java`:

```java
public class DiamondPairDemo {
    static final class Pair<K, V> {
        private final K first;
        private final V second;

        Pair(K first, V second) {
            this.first = first;
            this.second = second;
        }

        K first() {
            return first;
        }

        V second() {
            return second;
        }
    }

    static final class NumericBox<T extends Number> {
        private final T value;

        NumericBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> setting = new Pair<>("port", 8080);
        NumericBox<Long> counter = new NumericBox<>(42L);

        System.out.println(setting.first() + "=" + setting.second());
        System.out.println("counter=" + counter.get());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DiamondPairDemo.java
java DiamondPairDemo
```

```text
port=8080
counter=42
```

**Những điều cần phân biệt:**

- `Pair<K, V>` khai báo **hai tham số kiểu**. `Pair<String, Integer>` ở vế trái xác định đối số kiểu là `String` và `Integer`; constructor nhận giá trị tương ứng.
- `NumericBox<T extends Number>` chỉ nhận các kiểu tham số thỏa ràng buộc `extends Number`. `NumericBox<Long>` hợp lệ; `NumericBox<String>` bị compiler từ chối.
- Literal `42L` mang kiểu nguyên thủy `long`, được boxing thành `Long` khi truyền vào constructor có `T = Long`.
- Cú pháp diamond không làm mất tính generic của phương thức `first()` / `second()`; compiler vẫn biết chúng trả về `String` / `Integer` khi sử dụng `setting`.
- Việc constructor có các tham số `K`, `V` giúp kiểm tra tương thích giữa **giá trị đầu vào** và **kiểu đích**. Nếu hai nguồn thông tin mâu thuẫn, compiler báo lỗi, không ép kiểu tùy tiện.

## 5. Diamond trong các ngữ cảnh biểu thức hiện đại

Diamond vẫn giữ nguyên hình thức `new Type<>()` khi được dùng trong khai báo, đối số method, giá trị trả về hoặc lambda.

Lưu thành `DiamondContextsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class DiamondContextsDemo {
    static void printCount(List<String> values) {
        System.out.println("count=" + values.size());
    }

    static List<String> emptyNames() {
        return new ArrayList<>();
    }

    public static void main(String[] args) {
        List<String> copied = new ArrayList<>(List.of("An", "Bình"));
        printCount(new ArrayList<>());
        System.out.println("copy=" + copied);
        System.out.println("empty=" + emptyNames());

        Supplier<List<String>> factory = () -> new ArrayList<>();
        List<String> created = factory.get();
        created.add("Java");
        System.out.println("factory=" + created);
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DiamondContextsDemo.java
java DiamondContextsDemo
```

```text
count=0
copy=[An, Bình]
empty=[]
factory=[Java]
```

Ở đây, compiler kiểm tra kiểu đích khi dùng `new ArrayList<>()` trong lời gọi `printCount`, trong `return` và trong lambda. **Lambda/functional interface là tính năng Java 8**; `List.of` thuộc Java 9. Trong hệ thống chạy JDK hiện đại, các cơ chế này phối hợp tự nhiên với diamond từ Java 7.

**Gợi ý thiết kế:** khai báo theo interface khi hợp lý, ví dụ `List<String>` thay cho `ArrayList<String>` ở API/biến cục bộ, vì điều đó giúp thay implementation mà không đổi phần code tiêu thụ. Dùng `ArrayList`, `LinkedHashMap` hay implementation khác tùy yêu cầu như thứ tự, hiệu năng, khóa, tính thay đổi được; compiler suy luận generic **không tự chọn** implementation.

## 6. Kết hợp diamond với `var`: khi nào suy luận thành `Object`?

Đây là lỗi dễ gặp khi nâng cấp code lên Java 10+:

```java
var items = new ArrayList<>();
items.add("Java");
items.add(7);   // Hợp lệ: items là ArrayList<Object>
```

Ở đây, `var` tự lấy kiểu từ vế phải, nhưng `new ArrayList<>()` không có đủ ràng buộc để suy luận kiểu phần tử cụ thể. Kiểu kết quả là `ArrayList<Object>`; thêm `String` và `Integer` đều hợp lệ. Nếu mục tiêu là danh sách chỉ chứa `String`, dùng một trong các cách rõ ràng:

```java
List<String> items = new ArrayList<>(); // Kiểu đích rõ, vẫn dùng diamond
var items2 = new ArrayList<String>();   // Kiểu khởi tạo rõ, var suy ra chính xác
var items3 = new ArrayList<>(List.of("Java")); // Đối số constructor định hướng String
```

Các snippet trên là **các khai báo minh họa riêng biệt** (không đưa trùng tên vào cùng method). `var` không làm code mất kiểm tra kiểu, nhưng nếu suy luận ra kiểu quá rộng như `Object`, compiler sẽ cho phép những giá trị mà nghiệp vụ không mong muốn.

Lưu thành `DiamondVarDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondVarDemo {
    public static void main(String[] args) {
        var mixed = new ArrayList<>();
        mixed.add("Java");
        mixed.add(7);

        var typed = new ArrayList<String>();
        typed.add("Java");

        var inferredFromValues = new ArrayList<>(List.of("A", "B"));
        inferredFromValues.add("C");

        System.out.println("mixed=" + mixed);
        System.out.println("typed=" + typed);
        System.out.println("copied=" + inferredFromValues);
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DiamondVarDemo.java
java DiamondVarDemo
```

```text
mixed=[Java, 7]
typed=[Java]
copied=[A, B, C]
```

Cần nhớ: `var` chỉ dùng ở những vị trí ngôn ngữ hỗ trợ suy luận kiểu biến cục bộ (và một số cú pháp được bổ sung sau đó), **không biến Java thành ngôn ngữ dynamically typed**. Đối với collection rỗng, khai báo `List<DomainType> list = new ArrayList<>()` thường truyền tải ý định tốt hơn `var list = new ArrayList<>()`.

## 7. Diamond vẫn tuân thủ invariance và wildcard

Suy luận generic không làm Java tự đổi luật tương thích kiểu. `ArrayList<Integer>` **không phải** subtype của `List<Number>`, dù `Integer` là subtype của `Number`. Đây là đặc tính **invariance** của generic, quan trọng khi compiler quyết định có chấp nhận kiểu được suy luận hay không.

Đoạn mã không hợp lệ:

```java
List<Number> numbers = new ArrayList<Integer>();
// Compile error: ArrayList<Integer> không tương thích với List<Number>
```

Nếu cần một collection có thể lưu nhiều subtype khác nhau của `Number`:

```java
List<Number> numbers = new ArrayList<>();
numbers.add(10);
numbers.add(2.5);
```

Ở đây compiler suy luận `ArrayList<Number>` nhờ vế trái. Nếu chỉ cần **đọc** từ danh sách một loại con của `Number` thì có thể dùng `List<? extends Number>`. Nếu cần **ghi** các giá trị `Integer` vào một collection phù hợp thì có thể dùng `List<? super Integer>`. Hai kiểu wildcard này mang các giới hạn riêng:

```java
List<? extends Number> source = new ArrayList<Integer>();
List<? super Integer> sink = new ArrayList<Number>();
sink.add(10);          // Hợp lệ: Integer
Number n = source.isEmpty() ? 0 : source.get(0);
```

Đây là snippet minh họa kiểu generic, không phải chương trình độc lập. Với `source`, không thể tùy ý `source.add(10)` vì compiler không biết chính xác subtype nào đang được giữ. Với `sink`, kết quả `sink.get(0)` có kiểu tối thiểu an toàn là `Object`. Diamond có thể được dùng trong khởi tạo nếu các ràng buộc cung cấp đủ thông tin, nhưng **không vượt qua** các giới hạn wildcard.

**Nguyên tắc:** dùng diamond để giảm lặp; khi gặp compile error liên quan `List<X>` / `List<Y>`, hãy xem lại kiểu generic, variance và hợp đồng API, thay vì sửa bằng raw type hoặc ép kiểu thiếu căn cứ.

## 8. Diamond khác raw type và ép kiểu unchecked

Hãy đối chiếu:

| Cú pháp | Kiểm tra generic tại compile-time | Khuyến nghị |
| --- | --- | --- |
| `List<String> a = new ArrayList<>();` | Có; compiler suy luận `String` | Phổ biến, rõ ràng |
| `List<String> a = new ArrayList<String>();` | Có; viết tường minh `String` | Hợp lệ khi giúp diễn đạt ý định |
| `List a = new ArrayList();` | Raw type, bỏ nhiều kiểm tra generic | Tránh trong code mới |
| `List<String> a = new ArrayList();` | Gán unchecked từ raw type, thường có cảnh báo | Sửa nguồn kiểu hoặc API, không che cảnh báo |
| `var a = new ArrayList<>();` | Có generic nhưng `E` là `Object` ở đây | Cần xem kiểu kết quả có đúng ý định không |

Dùng diamond **không** tạo raw type. Raw type là cú pháp dùng tên lớp generic nhưng **bỏ toàn bộ tham số kiểu**, ví dụ `new ArrayList()`; điều này làm mất thông tin cần thiết để kiểm tra phần tử khi biên dịch.

Ví dụ mã **có vấn đề** chỉ để hiểu cảnh báo:

```java
List raw = new ArrayList();
raw.add(42);
List<String> names = raw;     // unchecked conversion warning
String first = names.get(0);  // ClassCastException tại runtime
```

Khi biên dịch với `javac -Xlint:rawtypes -Xlint:unchecked`, compiler giúp tìm chỗ dùng raw/unchecked. Một số dự án tích hợp thư viện cũ phải xử lý các biên API chưa generic; giải pháp là cô lập việc chuyển đổi và kiểm tra dữ liệu tại ranh giới, không lan raw type vào nội bộ ứng dụng.

**Type erasure vẫn tồn tại:** JVM thông thường không giữ đối số kiểu của `new ArrayList<String>()` dưới dạng một loại đối tượng runtime riêng. Hai đối tượng `new ArrayList<String>()` và `new ArrayList<Integer>()` có cùng runtime class `ArrayList`. Kiểm tra generic chủ yếu là lợi ích **compile-time**; diamond không thay đổi nguyên tắc này.

## 9. Có dùng diamond với anonymous class được không?

**Có, trên Java 9 trở lên**, khi suy luận thỏa các điều kiện ngôn ngữ. Giới hạn của Java 7/8 đối với `new GenericType<>() { ... }` đã được nới từ Java 9. Trong dự án JDK 17+, trường hợp dưới đây hợp lệ:

Lưu thành `DiamondAnonymousDemo.java`:

```java
import java.util.concurrent.Callable;

public class DiamondAnonymousDemo {
    public static void main(String[] args) throws Exception {
        Callable<String> task = new Callable<>() {
            @Override
            public String call() {
                return "Hoàn tất";
            }
        };

        System.out.println(task.call());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DiamondAnonymousDemo.java
java DiamondAnonymousDemo
```

```text
Hoàn tất
```

Ví dụ dùng Java 17 nên không có xung đột phiên bản. Nếu bảo trì mã cần biên dịch `--release 8`, không sử dụng cú pháp diamond với anonymous class vì **Java 8 không hỗ trợ** trường hợp đó. Với một tác vụ đơn giản dùng functional interface, lambda từ Java 8 thường ngắn gọn hơn; anonymous class vẫn có ích khi cần diễn đạt phần cài đặt cụ thể của class/interface.

**Phân biệt:** `new Runnable<>()` không hợp lệ vì `Runnable` **không phải generic interface**. Diamond chỉ áp dụng khi kiểu đang khởi tạo có tham số generic.

## 10. Những vị trí không được viết `<>`

Diamond có phạm vi cú pháp cụ thể: thuộc **biểu thức tạo instance của lớp generic**. Nó không phải ký hiệu thay cho mọi khai báo kiểu.

| Viết sai | Lý do | Cách đúng |
| --- | --- | --- |
| `List<> items = new ArrayList<>();` | Khai báo kiểu generic không được bỏ trống đối số kiểu như vậy | `List<String> items = new ArrayList<>();` |
| `new String<>()` | `String` không phải lớp generic | `new String(...)` nếu constructor phù hợp |
| `new ArrayList<?>();` | Wildcard không được sử dụng trực tiếp làm đối số kiểu tường minh khi tạo instance kiểu này | `new ArrayList<>()` với kiểu đích thích hợp |
| `new HashMap<>()` rồi giả định mọi khóa/giá trị là `String` | Không có ràng buộc kiểu đó khi đứng độc lập | Khai báo `Map<String, String> map = new HashMap<>();` |
| `List<Number> n = new ArrayList<Integer>();` | Generic invariant; không phải lỗi thiếu diamond | `List<Number> n = new ArrayList<>();` nếu cần thêm nhiều kiểu Number |
| `var words = new ArrayList<>();` rồi kỳ vọng `words` là `ArrayList<String>` | Không có kiểu đích `String` để suy luận | `var words = new ArrayList<String>();` hoặc khai báo vế trái |

Cũng đừng nhầm `<>` của diamond với toán tử so sánh `<` và `>` trong biểu thức, hoặc với ký hiệu `<T>` khi **khai báo phương thức generic**. Ví dụ `static <T> T identity(T value)` định nghĩa **tham số kiểu của method**; đó là cơ chế khác, dù hai cơ chế cùng dựa trên hệ thống generic.

## 11. Khi nào viết rõ kiểu thay vì dùng diamond?

Diamond là lựa chọn mặc định tốt khi đã có ngữ cảnh kiểu rõ. Tuy nhiên có tình huống việc ghi tường minh một kiểu ở constructor giúp code dễ đọc hoặc tránh suy luận quá rộng:

- `var result = new ArrayList<String>();`: đối số kiểu phải hiển thị ở vế phải vì `var` không cung cấp `String`.
- `new ArrayList<String>()` trong đoạn biểu thức phức tạp: có thể thể hiện ý định rõ hơn nếu ngữ cảnh bị che khuất, nhưng không cần lặp máy móc khi vế trái đã đủ rõ.
- Khi compiler báo lỗi ràng buộc kiểu, khai báo trung gian có kiểu tường minh giúp thấy giới hạn type inference; kiểm tra API thực tế thay vì ép sang `Object` cho qua.
- Với API công khai, ưu tiên kiểu tham số/trả về cụ thể như `List<Order>`; việc rút gọn constructor bằng diamond không nên làm mất hợp đồng kiểu bên ngoài.

**Không nên viết raw type để “sửa nhanh” lỗi suy luận.** Nếu kiểu mong muốn không tương thích với constructor hoặc đối số, đó thường là thông tin hữu ích để sửa mô hình dữ liệu.

### 11.1. Diamond không quyết định mutability

`new ArrayList<>()` tạo một danh sách có thể sửa vì **`ArrayList`** có hành vi đó, không phải vì `<>`. `List.of("a", "b")` (Java 9) trả danh sách không hỗ trợ thao tác sửa phần tử/ cấu trúc, còn `new ArrayList<>(List.of("a", "b"))` là một bản sao dạng `ArrayList` có thể sửa. Trình biên dịch suy luận **kiểu tham số**, không lựa chọn tính bất biến hay đồng bộ hóa giúp ta.

### 11.2. Diamond không làm sâu kiểm tra phần tử ở runtime

`List<String> names = new ArrayList<>();` ngăn `names.add(123)` ngay khi biên dịch, nhưng dữ liệu từ deserialization, reflection hoặc raw API vẫn cần được xác thực khi đi qua ranh giới không an toàn. Đối số kiểu `String` không biến việc kiểm tra dữ liệu đầu vào từ bên ngoài thành không cần thiết.

## 12. Thực hành: chọn cú pháp hợp lý

**Tình huống A — mã xử lý danh sách người dùng**

```java
List<String> usernames = new ArrayList<>();
```

Kiểu phần tử đã rõ ở vế trái, nên diamond dễ đọc và duy trì kiểm tra kiểu.

**Tình huống B — bản sao thay đổi được từ danh sách nguồn**

```java
List<String> editable = new ArrayList<>(List.of("An", "Bình"));
editable.add("Chi");
```

Dùng diamond và constructor sao chép. Nếu dữ liệu nguồn có hợp đồng không cho sửa, đừng nhầm bản sao `ArrayList` với danh sách không thể thay đổi.

**Tình huống C — khai báo bằng `var` trong JDK hiện đại**

```java
var users = new ArrayList<User>();
```

Đoạn này là snippet giả định đã có lớp `User`. Nhờ `new ArrayList<User>()`, compiler suy luận `users` là `ArrayList<User>`, tránh kiểu phần tử `Object`. Nếu muốn bộc lộ interface trên vế trái, viết `List<User> users = new ArrayList<>();`.

**Tình huống D — generic lồng nhau**

```java
Map<String, List<Integer>> results = new HashMap<>();
results.put("passed", new ArrayList<>());
```

Không phải lặp `String, List<Integer>` trên constructor. Khi dữ liệu hoặc logic trở nên phức tạp, vẫn nên chọn tên biến, API và cấu trúc rõ ràng.

## 13. Câu hỏi tự kiểm tra

1. **`<>` trong `new ArrayList<>()` là generic raw type hay generic có suy luận?**  
   **Đáp án:** Generic có suy luận. Compiler tìm đối số kiểu theo ngữ cảnh và ràng buộc.

2. **Vì sao `List<String> a = new ArrayList<>();` có thể thêm `"Java"` nhưng `a.add(1)` bị từ chối?**  
   **Đáp án:** Compiler suy luận kiểu phần tử `String`; lời gọi `add(Integer)` không thỏa hợp đồng `List<String>`.

3. **`var a = new ArrayList<>();` và `List<String> a = new ArrayList<>();` có giống kiểu phần tử không?**  
   **Đáp án:** Không. Trường hợp đầu trong ngữ cảnh này suy luận `Object`; trường hợp sau suy luận `String`.

4. **`Map<String, List<Integer>> m = new HashMap<>();` có phải chỉ suy luận một đối số kiểu?**  
   **Đáp án:** Không, `HashMap<K,V>` có hai đối số: `K=String` và `V=List<Integer>`.

5. **Có thể thay `List<Number> x = new ArrayList<Integer>();` bằng `List<Number> x = new ArrayList<>();` không?**  
   **Đáp án:** Có, nếu mục tiêu thật sự là một `List<Number>` mới. Diamond suy luận `Number`; nó không làm `ArrayList<Integer>` trở thành subtype của `List<Number>`.

6. **Đã dùng diamond có cần quan tâm type erasure không?**  
   **Đáp án:** Có. Diamond là đường viết ngắn ở compile-time; generic Java vẫn có erasure như bình thường.

7. **Diamond với anonymous class có hợp lệ khi biên dịch Java 8 không?**  
   **Đáp án:** Không. Hỗ trợ cú pháp này được bổ sung từ Java 9; trên Java 17+ có thể dùng khi thỏa ràng buộc suy luận.

8. **Bài thực hành:** Tạo `Map<String, List<String>>` và hàm thêm một dòng mới cho một khóa, dùng `computeIfAbsent` (Java 8+) với `new ArrayList<>()`, sau đó in kết quả. Giải thích kiểu suy luận của collection mới.

9. **Bài thực hành:** Thử `var values = new ArrayList<>();` rồi thêm một chuỗi và một số; đổi thành `var values = new ArrayList<String>();` và quan sát lỗi compile-time cho phần tử số.

10. **Bài thực hành:** Viết `Pair<A, B>` có constructor và hai getter; tạo `Pair<String, Long>` bằng diamond; thử truyền đối số thứ hai là `"42"` và giải thích vì sao compiler từ chối.

## 14. Tài liệu chuẩn

- [Java Language Specification — Class Instance Creation Expressions (`15.9)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): cú pháp `new`, diamond và quy tắc suy luận trong tạo đối tượng.
- [Java Language Specification — Type Inference (`18)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): cơ chế ràng buộc và suy luận kiểu.
- [Java Language Specification — Type Erasure (`4.6)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): vì sao đối số generic không tạo loại runtime riêng.
- [Java Language Specification — Local Variable Type Inference (`14.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): quy tắc của `var`.
- [Java SE 17 API — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): constructors và `Collection<? extends E>`.

**Ghi nhớ:** Dùng `new GenericType<>()` khi ngữ cảnh đủ rõ để compiler suy luận đối số kiểu. Suy luận này **chỉ xảy ra khi biên dịch**, giữ nguyên cơ chế kiểm tra generic và type erasure. Khi kết hợp với `var`, chú ý rằng `new ArrayList<>()` độc lập thường suy luận `Object`. Cách viết tốt nhất là cách vừa ngắn gọn vừa biểu đạt chính xác kiểu phần tử, constructor và hợp đồng API.
