# Phân biệt gán lại biến với thay đổi đối tượng được tham chiếu trong Java lambda

## 1. Mục tiêu và tình huống thực tế

Khi học **phạm vi và bắt giữ biến (scope and variable capture)** của lambda, có hai thao tác trông giống nhau nhưng chịu những quy tắc khác nhau:

1. **Gán lại một biến tham chiếu (reassignment):** khiến tên biến trỏ tới đối tượng khác, ví dụ `items = new ArrayList<>();`.
2. **Thay đổi trạng thái đối tượng mà biến đang trỏ tới (mutation):** giữ nguyên tham chiếu nhưng sửa đối tượng, ví dụ `items.add("Java");`.

Java yêu cầu biến **local** được lambda sử dụng từ phạm vi bao ngoài phải là `final` hoặc **effectively final**. Quy tắc này cấm gán lại biến local được bắt giữ, nhưng **không tự động cấm sửa trạng thái đối tượng mutable** mà biến ấy tham chiếu.

Hệ quả thực tế: một lambda có thể biên dịch hợp lệ và vẫn gây side effect, mất tính an toàn luồng, tạo kết quả phụ thuộc thứ tự hoặc khiến người học nhầm rằng có `final` tức là dữ liệu không thể thay đổi.

Sau bài học, bạn cần có thể:

- Giải thích sự khác nhau giữa **biến**, **giá trị tham chiếu**, **đối tượng trên heap** và **trạng thái đối tượng**.
- Phân biệt `final` với `effectively final` khi lambda capture biến local.
- Dự đoán chính xác trường hợp gán lại gây lỗi biên dịch và trường hợp mutate vẫn hợp lệ.
- Biết cách tránh shared mutable state, dùng immutable data, defensive copy hoặc reduction khi phù hợp.
- Nhận diện rủi ro khi lambda được lưu để gọi sau hoặc chạy trên nhiều thread.

Ví dụ đầy đủ sử dụng **Java 17 trở lên**.

## 2. Bốn khái niệm nền tảng

### 2.1. Biến local và tham chiếu

Với mã:

~~~java
List<String> names = new ArrayList<>();
~~~

`names` là **biến local chứa một giá trị tham chiếu** tới đối tượng `ArrayList`. Đối tượng có trạng thái nội bộ như danh sách phần tử. Hai biến có thể giữ cùng tham chiếu:

~~~java
List<String> alias = names;
~~~

Lúc này `names == alias` là `true`: chúng cùng trỏ tới một đối tượng. Sửa qua một biến thì quan sát qua biến còn lại cũng thấy, miễn cùng đối tượng và trong điều kiện truy cập phù hợp.

### 2.2. Gán lại biến là thay giá trị tham chiếu

~~~java
names = new ArrayList<>(List.of("new"));
~~~

Lệnh trên khiến `names` trỏ tới **đối tượng mới**. `alias` vẫn giữ tham chiếu cũ. Một phép gán mới cho biến local là một lần thay đổi **binding** của tên biến; đây là hành vi mà quy tắc effectively final hạn chế khi lambda capture biến đó.

### 2.3. Mutate là sửa nội dung của cùng một đối tượng

~~~java
names.add("Java");
names.set(0, "Core"); // Chỉ chạy nếu danh sách có phần tử ở vị trí 0.
~~~

Các lời gọi thay đổi trạng thái đối tượng `List`, không thực hiện phép gán `names = ...`. Nếu `names` đang trỏ tới `ArrayList` và danh sách có trạng thái thích hợp, chúng có thể hợp lệ ngay cả khi biến `names` được khai báo `final`.

### 2.4. Sơ đồ tham chiếu

~~~text
Trước mutation:
local names ─────┐
                 ├──► ArrayList #1 ["A"]
local alias ─────┘

Sau names.add("B"):
local names ─────┐
                 ├──► ArrayList #1 ["A", "B"]
local alias ─────┘

Sau names = new ArrayList<>():
local names ─────────► ArrayList #2 []
local alias ─────────► ArrayList #1 ["A", "B"]
~~~

Sơ đồ này mô tả ngữ nghĩa các tham chiếu, không mô tả chi tiết bố trí bộ nhớ vật lý của JVM. Nếu `names` là local được lambda bắt giữ, phép **gán lại** ở bước cuối sẽ khiến biến không còn effectively final và làm mã lambda sử dụng `names` **không biên dịch**, dù bản thân phép gán ấy có thể hợp lệ khi không capture.

## 3. Quy tắc `final` và `effectively final`

### 3.1. `final`: chỉ được gán theo quy tắc khởi tạo

~~~java
final int limit = 10;
final List<String> list = new ArrayList<>();
~~~

`limit` không được gán giá trị khác; `list` không được gán tham chiếu khác sau khi khởi tạo. Tuy nhiên, `list.add(...)` vẫn được phép vì nó sửa **đối tượng**.

~~~java
list.add("A");      // Hợp lệ: đổi trạng thái đối tượng mutable.
// list = new ArrayList<>(); // Lỗi: không được gán lại biến final.
~~~

Từ khóa `final` bảo vệ **biến** ở cấp này, không bảo đảm cấu trúc đối tượng được tham chiếu là immutable. Đối với đối tượng thực sự không cho mutate, tính bất biến được xác định bởi API/thiết kế của đối tượng, không phải chỉ bởi từ khóa `final` ở biến tham chiếu.

### 3.2. `effectively final`: không ghi `final` nhưng vẫn không gán lại

~~~java
int threshold = 10;
Runnable show = () -> System.out.println(threshold);
show.run(); // In 10
~~~

`threshold` là local được gán một lần và không thay đổi về sau, nên compiler coi là **effectively final**. Viết thêm `final` không thay đổi ý nghĩa trong trường hợp này.

Nếu ta sửa mã thành:

~~~java
int threshold = 10;
Runnable show = () -> System.out.println(threshold);
threshold = 20; // Lỗi biên dịch do threshold đã được lambda capture.
~~~

Compiler xét **phạm vi và phép gán trong mã**, không đợi chương trình chạy. Cho dù câu lệnh gán nằm sau lúc tạo lambda hoặc trên một nhánh hiếm được chạy, một phép gán làm biến không effectively final vẫn có thể khiến lambda bị từ chối tại compile time. Đừng hiểu rằng giá trị được copy vào lambda khiến phép gán lại cho biến local tự động hợp lệ.

### 3.3. Local chưa khởi tạo và các nhánh gán

Quy tắc effectively final không đơn giản chỉ là "phải có đúng một dấu `=` trong toàn bộ mã". Một biến local chưa có initializer có thể được **gán đúng một lần trên mỗi đường đi hợp lệ** trước khi sử dụng và vẫn được bắt giữ, miễn thỏa các quy tắc definite assignment/effectively final.

Ví dụ hợp lệ đặt trong phương thức:

~~~java
final int score;
if (condition) {
    score = 100;
} else {
    score = 0;
}
Runnable printScore = () -> System.out.println(score);
~~~

Đây là **mảnh mã** cần có biến `condition` kiểu `boolean` được xác định trong phạm vi. Mỗi nhánh khởi tạo `score` một lần trước khi lambda dùng nó. Với local không khai báo `final`, Java cũng có quy tắc tương đương về việc gán trên đường đi và không thay đổi sau đó; nên dựa vào compiler/JLS khi trường hợp phức tạp, không suy diễn từ số dòng mã chứa dấu `=`.

### 3.4. Bảng so sánh thao tác

| Thao tác | Có gán lại biến local? | Có sửa đối tượng đang được tham chiếu? | Nếu local đã được lambda capture |
| --- | --- | --- | --- |
| `count = 2` | Có | Không áp dụng với primitive | Không hợp lệ nếu làm mất effectively final |
| `list = anotherList` | Có | Không trực tiếp | Không hợp lệ nếu làm mất effectively final |
| `list.add("X")` | Không | Có, nếu list mutable | Có thể biên dịch; xét thêm hợp đồng List |
| `list.clear()` | Không | Có, nếu mutable | Có thể biên dịch; vẫn có side effect |
| `builder.append("X")` | Không | Có | Có thể biên dịch; builder bị thay đổi |
| `atomic.incrementAndGet()` | Không | Có, qua AtomicInteger | Có thể biên dịch; phép tăng riêng lẻ atomic |
| `list.size()` | Không | Thông thường không | Có thể biên dịch; chỉ đọc trạng thái |

**Lưu ý:** "có thể biên dịch" không đồng nghĩa "luôn chạy thành công". Gọi `add` trên `List.of(...)` sẽ ném `UnsupportedOperationException`; gọi phương thức trên tham chiếu `null` có thể ném `NullPointerException`; chia sẻ `ArrayList` giữa thread có thể sai về đồng bộ.

## 4. Lambda bắt giữ điều gì?

Lambda có thể truy cập tham số, biến local và thành viên đang trong phạm vi hợp lệ. Với **biến local được capture**, Java yêu cầu `final`/`effectively final`. Giới hạn này giúp tránh hiểu nhầm về một local thay đổi trên stack trong khi hành vi lambda có thể sống lâu hơn khối tạo nó.

Ví dụ:

~~~java
int minimum = 3;
Predicate<String> accepted =
        name -> name != null && name.length() >= minimum;
~~~

Ở đây `minimum` không được gán lại; mỗi lần lambda chạy, nó dùng giá trị local đã được bắt giữ. Nếu `minimum` là primitive `int`, giá trị mà lambda dùng không thay đổi qua các phép gán lại biến local vì những phép gán đó không được phép trong trường hợp capture.

Với tham chiếu:

~~~java
List<String> audit = new ArrayList<>();
Consumer<String> record = name -> audit.add(name);
~~~

Lambda dùng **tham chiếu** tới đối tượng mà biến `audit` chỉ tới lúc capture. Nó có thể sửa đối tượng qua tham chiếu đó. **Không có bản sao tự động của cả ArrayList** khi tạo lambda.

### Capture không đồng nghĩa snapshot của trạng thái

~~~java
List<String> shared = new ArrayList<>(List.of("A"));
Supplier<Integer> size = () -> shared.size();

System.out.println(size.get()); // 1
shared.add("B");
System.out.println(size.get()); // 2
~~~

Mã minh họa cần import `java.util.List`, `java.util.ArrayList` và `java.util.function.Supplier`, đặt trong phương thức. Biến `shared` vẫn giữ cùng tham chiếu và vẫn effectively final; trạng thái đối tượng thay đổi giữa hai lần gọi `size.get()`, nên kết quả khác nhau.

Ngược lại, nếu cần cố định kết quả tại thời điểm tạo lambda, có thể tính trước một giá trị immutable:

~~~java
int fixedSize = shared.size();
Supplier<Integer> snapshotSize = () -> fixedSize;
~~~

Sau này `shared` thêm phần tử thì `snapshotSize.get()` vẫn trả `fixedSize` đã xác định. Đây là khác biệt giữa bắt giữ một **giá trị đã tính** và bắt giữ một **tham chiếu để đọc trạng thái về sau**.

### Field và local không bị ràng buộc giống nhau

Quy tắc effectively final áp dụng cho **local variables, parameters và exception parameters** được lambda tham chiếu. Các **instance field** và **static field** không phải local capture kiểu đó; field có thể được gán lại nếu khai báo và quy tắc truy cập cho phép.

~~~java
class CounterHolder {
    private int total;

    Runnable incrementer() {
        return () -> total++; // Biên dịch: total là field, không phải local.
    }
}
~~~

Đây là class minh họa, không phải chương trình độc lập có `main`. Nếu nhiều thread gọi `incrementer()` trên cùng instance, `total++` không phải thao tác nguyên tử, có thể race. Quy tắc capture chỉ kiểm tra khả năng gán lại **biến local**; nó không bảo đảm field có visibility hay atomicity khi chạy đa luồng.

## 5. Ví dụ Java 17 hoàn chỉnh: gán lại, alias và mutation

Tạo tệp **`CaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.IntConsumer;

public class CaptureDemo {
    public static void main(String[] args) {
        // threshold là local effectively final.
        int threshold = 10;
        List<String> messages = new ArrayList<>();

        // messages không bị gán lại; đối tượng List có thể bị sửa.
        Consumer<Integer> classify = number ->
                messages.add(number >= threshold
                        ? "high:" + number : "low:" + number);

        classify.accept(7);
        classify.accept(12);
        System.out.println(messages);

        List<String> original = new ArrayList<>(List.of("A"));
        List<String> alias = original;

        // Method reference cũng gọi thao tác trên cùng object.
        Consumer<String> append = original::add;
        append.accept("B");

        System.out.println(original);
        System.out.println(original == alias);

        // Chụp lại cấu trúc danh sách hiện tại.
        List<String> snapshot = List.copyOf(original);
        append.accept("C");
        System.out.println(snapshot);
        System.out.println(original);

        final StringBuilder builder = new StringBuilder("start");
        Runnable update = () -> builder.append("-done");
        update.run();
        System.out.println(builder);

        AtomicInteger counter = new AtomicInteger();
        IntConsumer count = number -> counter.incrementAndGet();
        count.accept(1);
        count.accept(2);
        System.out.println(counter.get());
    }
}
~~~

Biên dịch, chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 CaptureDemo.java
java CaptureDemo
~~~

**Stdout chính xác:**

~~~text
[low:7, high:12]
[A, B]
true
[A, B]
[A, B, C]
start-done
2
~~~

Phân tích:

1. `threshold` không bị gán lại, nên lambda `classify` được phép bắt giữ nó. `messages.add(...)` thay đổi **đối tượng List**, không gán lại biến local `messages`.
2. `original` và `alias` trỏ tới cùng `ArrayList`; `append.accept("B")` thay đổi đối tượng ấy, vì vậy danh sách trở thành `[A, B]` và phép `original == alias` in `true`.
3. `List.copyOf(original)` tạo danh sách **không thể thêm/xóa/sửa cấu trúc qua API List**, ghi nhận phần tử tại thời điểm gọi; khi `original` thêm `"C"`, `snapshot` vẫn là `[A, B]`. Trong ví dụ này phần tử là `String` immutable.
4. `builder` được khai báo `final` nhưng `StringBuilder` là mutable, nên `append` vẫn thực hiện được và in `start-done`.
5. `AtomicInteger` là một object mutable có thao tác cập nhật giá trị nguyên tử. `counter` không bị gán lại; `incrementAndGet` sửa **trạng thái bên trong** object, hai lần gọi làm giá trị thành `2`. Tham số `number` không được dùng trong lambda ví dụ này vì mục tiêu là minh họa phép tăng; có thể đặt tên `ignored` nếu muốn làm rõ.

**Điểm học được:** các lambda và method reference biên dịch được vì không có phép gán lại local đã capture. Chúng vẫn có thể làm trạng thái bên ngoài thay đổi. Tính an toàn không được suy ra từ việc compiler chấp nhận lambda.

## 6. Trường hợp lỗi: gán lại biến local đã được lambda dùng

Các đoạn sau là **ví dụ lỗi cố ý, không ghép vào chương trình chạy**.

### 6.1. Gán lại biến tham chiếu

~~~java
List<String> items = new ArrayList<>();
Runnable task = () -> System.out.println(items.size());
items = new ArrayList<>(); // Compiler error: items không effectively final.
~~~

Lỗi xảy ra dù lambda chỉ gọi `size()` và không mutate. Điều kiện của compiler là `items` không được gán lại khi được lambda capture, không phải chỉ cấm mutation trong lambda.

### 6.2. Gán lại primitive

~~~java
int number = 1;
Runnable task = () -> System.out.println(number);
number++; // Cũng là cập nhật biến local, vi phạm effectively final.
~~~

`number++` làm thay đổi giá trị biến local. Biến không còn effectively final, kể cả khi câu lệnh tăng nằm ngoài thân lambda.

### 6.3. Gán lại ngay trong lambda

~~~java
List<String> items = new ArrayList<>();
Runnable task = () -> {
    items = new ArrayList<>(); // Lỗi biên dịch.
};
~~~

Lambda không thể dùng phép gán để thay binding của biến local được capture. Nếu muốn tạo collection mới cho riêng việc xử lý, khai báo **biến local mới bên trong lambda**:

~~~java
Runnable task = () -> {
    List<String> temporary = new ArrayList<>();
    temporary.add("Java");
    System.out.println(temporary);
};
~~~

Mỗi lần gọi `run()` trong ví dụ này sẽ tạo một `ArrayList` mới, nên không cần chia sẻ cùng object mutable với lần gọi trước. Nếu yêu cầu thật sự là lưu lại kết quả, hãy thiết kế giá trị trả về bằng `Supplier<List<String>>`, `Function` hoặc chuyển qua một API quản lý trạng thái thích hợp, thay vì tìm cách vượt qua compiler.

### 6.4. Gán một tham chiếu mới cho biến khác không phải "sửa object"

~~~java
List<String> first = new ArrayList<>(List.of("A"));
List<String> second = first;
second = new ArrayList<>(List.of("B"));
~~~

Sau dòng cuối, `first` vẫn trỏ tới danh sách `["A"]`, còn `second` trỏ tới `["B"]`. Phép gán thay đổi **biến second**, không mutate đối tượng của `first`. Nếu một lambda capture `second` trong cùng phạm vi, phép gán lại đó sẽ gây lỗi compile; nếu lambda chỉ capture `first` thì việc gán lại biến **second** không làm `first` mất effectively final.

## 7. `final` không đồng nghĩa immutable hoặc thread-safe

### 7.1. Có nhiều cấp độ không thay đổi

| Cách khai báo / tạo dữ liệu | Điều được bảo vệ | Điều không tự bảo đảm |
| --- | --- | --- |
| `final List<String> list = new ArrayList<>();` | Không thể gán lại biến `list` | Vẫn `add`/`remove` được; không tự thread-safe |
| `List<String> list = new ArrayList<>();` và never reassign | Biến local effectively final để lambda capture | Vẫn có thể sửa object; không tự immutable |
| `List.of("A", "B")` | Không sửa cấu trúc danh sách qua `List` | Không mặc định deep immutable nếu phần tử là object mutable |
| `List.copyOf(source)` | Danh sách mới unmodifiable, chụp cấu trúc tại thời điểm copy | Không deep-copy phần tử mutable |
| `Collections.unmodifiableList(source)` | Không sửa qua wrapper | Nếu vẫn giữ `source` thì sửa source có thể hiện qua wrapper |
| `AtomicInteger` | Một số thao tác như `incrementAndGet` có bảo đảm nguyên tử | Không làm toàn bộ workflow nhiều bước thành transaction |

Ví dụ `List.copyOf` chỉ sao chép tham chiếu tới các phần tử và tạo cấu trúc không sửa được; nếu phần tử là một `StringBuilder` mutable, thay đổi nội dung của chính `StringBuilder` đó vẫn có thể quan sát từ cả source và copy.

### 7.2. `final` field cũng không mặc nhiên deep immutable

~~~java
class Store {
    final List<String> entries = new ArrayList<>();

    void add(String entry) {
        entries.add(entry); // Vẫn hợp lệ.
    }
}
~~~

Class này chỉ minh họa. `final` ngăn thay tham chiếu của field `entries` sau khi được khởi tạo; nó không biến `ArrayList` thành immutable. Để thiết kế một đối tượng bất biến hơn, hãy phòng ngừa việc lộ tham chiếu mutable, sao chép phòng vệ khi nhận/trả dữ liệu và bảo đảm các thành phần bên trong cũng đáp ứng bất biến mong muốn.

### 7.3. Immutable data giảm khó khăn khi dùng lambda

Với dữ liệu không thay đổi, việc chia sẻ cho nhiều hàm thường dễ dự đoán hơn. Một cách tổ chức:

~~~java
List<String> source = List.of("An", "Binh");
List<String> upper = source.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Đây là mã minh họa trong phương thức. `source` không bị mutate; pipeline tạo danh sách kết quả và `Stream.toList()` trả danh sách unmodifiable. Tính toán có đầu vào và đầu ra tường minh, dễ kiểm thử và giảm nguy cơ phụ thuộc vào trạng thái bên ngoài.

## 8. Vấn đề với shared mutable state và xử lý song song

### 8.1. Lambda hợp lệ chưa chắc an toàn đa luồng

~~~java
List<Integer> results = new ArrayList<>();
IntConsumer save = value -> results.add(value);
~~~

Đoạn trên **biên dịch được**: `results` là effectively final và phương thức `add` không gán lại biến đó. Nhưng nếu nhiều thread cùng gọi `save.accept(...)`, `ArrayList` không cung cấp thread safety cho các thay đổi đồng thời như vậy. Kết quả có thể mất phần tử, sai trạng thái hoặc có các hành vi không mong muốn.

Dùng `parallelStream().forEach(results::add)` để gom kết quả là một lỗi phổ biến. Hãy dùng phép tổng hợp được thiết kế cho Stream:

~~~java
List<Integer> squares = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * n)
        .toList();
~~~

Đây là đoạn mã minh họa với đầu vào có thứ tự; `toList()` tạo kết quả theo encounter order của pipeline khi có thứ tự. Nó tránh phải tự cập nhật một `ArrayList` chung trong `forEach`. Trong thực tế, **không tự động dùng parallelStream vì nghĩ sẽ nhanh hơn**; cần cân nhắc chi phí và yêu cầu nghiệp vụ.

### 8.2. Dùng phép reduction khi mục tiêu là tính toán

Cách có side effect:

~~~java
AtomicInteger total = new AtomicInteger();
List.of(1, 2, 3).forEach(total::addAndGet);
System.out.println(total.get()); // 6
~~~

Cách trực tiếp thể hiện kết quả:

~~~java
int total = List.of(1, 2, 3).stream()
        .mapToInt(Integer::intValue)
        .sum();
System.out.println(total); // 6
~~~

Hai đoạn độc lập cho cùng tổng trong ví dụ nhỏ. Cách thứ hai dễ thể hiện rằng mục đích là tính một giá trị, không cập nhật trạng thái chia sẻ. `AtomicInteger` hữu ích khi thật sự cần bộ đếm được cập nhật nguyên tử, nhưng không nên dùng nó chỉ để né quy tắc effectively final.

### 8.3. Vấn đề visibility và atomicity

Ngay cả khi mọi phép cập nhật đều hợp lệ về cú pháp, Java Memory Model vẫn quan trọng khi dữ liệu được chia sẻ giữa thread. Các thao tác như `counter++` trên một field thông thường không phải atomic; một field `volatile` hỗ trợ quy tắc visibility/ordering nhất định nhưng **không biến `++` thành nguyên tử**. `AtomicInteger.incrementAndGet()` có bảo đảm atomic cho thao tác cập nhật giá trị đó, nhưng hai bước cập nhật hai object khác nhau vẫn không tự thành transaction.

Vì vậy, quy tắc an toàn cần tách thành hai câu hỏi: *biến local có được bắt giữ theo luật compiler không?* và *trạng thái chia sẻ có đồng bộ và đúng nghĩa nghiệp vụ không?*. Trả lời "có" cho câu đầu không thể thay thế câu thứ hai.

## 9. Khi lambda được gọi ở thời điểm khác

### 9.1. Không nhầm thời điểm tạo với thời điểm chạy

~~~java
List<String> items = new ArrayList<>();
Runnable printSize = () -> System.out.println(items.size());

items.add("A");
printSize.run(); // In 1.
items.add("B");
printSize.run(); // In 2.
~~~

Ở đây lambda không chạy khi được gán vào `printSize`. Khi gọi `run`, nó đọc trạng thái hiện tại của object mà tham chiếu capture trỏ tới. Vì vậy hai lần gọi có thể cho kết quả khác nhau mà không có phép gán lại biến `items`.

### 9.2. Vòng lặp và capture

Trong vòng `for` cổ điển, biến đếm thay đổi theo mỗi lần lặp nên không effectively final:

~~~java
List<Runnable> tasks = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    // Lỗi: i thay đổi bởi i++.
    tasks.add(() -> System.out.println(i));
}
~~~

Giải pháp là tạo một biến local cho **mỗi lượt lặp**, không bị gán lại:

~~~java
List<Runnable> tasks = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    int index = i;
    tasks.add(() -> System.out.println(index));
}
tasks.forEach(Runnable::run); // In 0, rồi 1, rồi 2 trên ba dòng.
~~~

Một biến local mới `index` được tạo cho từng lượt lặp. Từng lambda capture một giá trị `index` khác nhau. Với vòng `for-each`, biến phần tử được khai báo ở vòng lặp cũng có phạm vi theo lượt lặp, nên có thể capture khi không bị gán lại trong lượt đó.

### 9.3. Lambda có thể sống lâu hơn khối tạo nó

Nếu phương thức trả về lambda, lambda có thể được gọi sau khi phương thức tạo nó kết thúc. Các biến local được capture không cần còn tồn tại dưới dạng frame stack ban đầu để lambda sử dụng; ngữ nghĩa Java đảm bảo dữ liệu cần thiết cho lambda còn truy cập được theo cơ chế runtime thích hợp. Không nên dựa trên một giả định cụ thể về cách compiler/JVM biểu diễn capture trong bộ nhớ.

Ví dụ minh họa:

~~~java
static Supplier<Integer> sizeLater(List<String> input) {
    List<String> view = input;
    return () -> view.size();
}
~~~

Đây là method minh họa trong class, cần import `Supplier`/`List`. `view` không được gán lại nên effectively final; khi lambda được gọi sau này, kết quả có thể phản ánh những thay đổi của **List instance** ở bên ngoài. Muốn snapshot cấu trúc, có thể dùng `List.copyOf(input)` trước khi tạo lambda, lưu ý yêu cầu không có phần tử `null` và đây chỉ là shallow copy.

## 10. Mẫu thiết kế giúp tránh nhầm lẫn

### 10.1. Truyền tham số, trả kết quả

Ưu tiên cách viết có input/output rõ:

~~~java
static List<String> appendCopy(List<String> source, String value) {
    List<String> result = new ArrayList<>(source);
    result.add(value);
    return result;
}
~~~

Đây là method minh họa trong class, cần import `List` và `ArrayList`. `source` không bị thay đổi cấu trúc bởi phương thức; người gọi nhận danh sách mới để quản lý tiếp. Nếu API yêu cầu kết quả không sửa được, trả `List.copyOf(result)` hoặc giải pháp phù hợp với hợp đồng về null và kiểu phần tử.

### 10.2. Tách mutation có chủ đích khỏi pipeline biến đổi

Giả sử cần ghi log khi thực hiện một hành động nghiệp vụ. Không nhất thiết phải đặt lời gọi log vào `map`/`filter` để tạo side effect ẩn. Có thể biến đổi dữ liệu bằng hàm thuần rồi thực hiện thao tác lưu/in ở ranh giới rõ ràng:

~~~java
List<String> output = input.stream()
        .filter(value -> value != null && !value.isBlank())
        .map(String::trim)
        .toList();

output.forEach(System.out::println);
~~~

Đây là đoạn minh họa trong phương thức, với `input` là `List<String>` hợp lệ. `output` là kết quả của pipeline; `forEach` ở sau thể hiện rõ ý định in dữ liệu. Cần xác định hợp đồng xử lý `null`, ngoại lệ và logging thực tế theo bài toán.

### 10.3. Dùng defensive copy khi xuất dữ liệu mutable

Nếu một API trả trực tiếp một `ArrayList` nội bộ, người gọi có thể mutate trạng thái của object sở hữu. Một cách bảo vệ cấu trúc là trả bản sao không sửa được:

~~~java
List<String> getEntries() {
    return List.copyOf(entries);
}
~~~

Đây là method minh họa nằm trong class sở hữu field `entries`; `List.copyOf` yêu cầu collection đầu vào không chứa phần tử `null`. Nếu phần tử có trạng thái mutable, cần đánh giá thêm yêu cầu deep-copy hoặc thiết kế phần tử immutable. Một `Collections.unmodifiableList(entries)` chỉ tạo **view** không sửa được qua wrapper, có thể phản ánh thay đổi cấu trúc của `entries` sau này; nó không có cùng ý nghĩa snapshot như `List.copyOf`.

## 11. Bài tập tự luyện

### Bài 1 — Dự đoán biên dịch

~~~java
int base = 2;
Function<Integer, Integer> add = n -> n + base;
base = 3;
~~~

**Câu hỏi:** vì sao lỗi? **Đáp án:** `base` là local được lambda capture nhưng bị gán lại, nên không effectively final. Nếu muốn một phép cộng phụ thuộc tham số thay đổi, hãy truyền giá trị `base` vào hàm hoặc tạo lambda mới dựa trên một biến local khác có giá trị ổn định.

### Bài 2 — Phân biệt tham chiếu và nội dung

~~~java
List<String> entries = new ArrayList<>();
Consumer<String> collect = entries::add;
collect.accept("A");
collect.accept("B");
System.out.println(entries);
~~~

Kết quả là `[A, B]`. Biến `entries` không bị gán lại; đối tượng List được mutate. Giải thích vì sao việc thêm `final` vào khai báo `entries` không làm dòng `add` thành lỗi.

### Bài 3 — Alias

Viết hai biến `a` và `b` cùng trỏ tới `ArrayList`, thêm phần tử qua `a` và đọc qua `b`. Sau đó gán `b` sang một `ArrayList` mới khi không có lambda capture `b`. Nêu rõ thời điểm hai biến còn trỏ cùng object và thời điểm tham chiếu đã tách.

### Bài 4 — Snapshot

Cho `List<String> mutable = new ArrayList<>(List.of("A"));`, tạo `List<String> snapshot = List.copyOf(mutable);`, rồi gọi `mutable.add("B")`. So sánh hai danh sách. Tiếp tục thử với danh sách chứa một object mutable để giải thích vì sao `List.copyOf` không phải deep copy.

### Bài 5 — Vòng lặp và capture

Tạo ba `Runnable`, mỗi cái in chỉ số tương ứng `0`, `1`, `2`. Phân biệt vì sao capture trực tiếp biến đếm của vòng for cổ điển bị lỗi và capture biến `index` được khai báo trong từng lượt hợp lệ.

### Bài 6 — Stream và shared state

Cho `List<Integer> nums = List.of(1,2,3,4,5);`. Viết cách tính tổng bình phương dùng `mapToInt(n -> n*n).sum()`. So sánh với cách dùng `AtomicInteger` cập nhật trong `forEach`; giải thích vì sao cách reduction thể hiện mục tiêu tính toán rõ hơn và ít phụ thuộc mutable state ngoài hơn. Thử danh sách rỗng và ghi nhận tổng bằng `0`.

### Bài 7 — Câu hỏi thiết kế

Một callback nhận `List<Order> orders`, giữ tham chiếu và có thể được gọi sau khi danh sách đã thay đổi. Nếu yêu cầu xử lý **đúng dữ liệu tại thời điểm đăng ký callback**, bạn sẽ làm gì? Gợi ý: tạo snapshot thích hợp và cân nhắc phần tử mutable; không dựa vào việc biến local là `final` để suy ra object bất biến.

## 12. Những sai lầm thường gặp

| Nhận định sai | Thực tế | Hướng xử lý |
| --- | --- | --- |
| "Lambda capture biến `final` nên object không thay đổi" | `final` bảo vệ phép gán lại biến, không khóa object mutable | Kiểm tra API/thiết kế immutable |
| "Không sửa list trong lambda thì không có side effect" | Callback có thể gọi phương thức mutate trên object ở nơi khác | Xem toàn bộ chuỗi lời gọi và quyền truy cập |
| "Sau khi tạo lambda có thể gán lại local đã capture" | Compiler xét quy tắc effectively final cả phạm vi | Truyền tham số hoặc tạo biến mới |
| "Copy List luôn copy sâu đối tượng" | `List.copyOf` tạo cấu trúc mới, có thể chia sẻ phần tử mutable | Deep-copy khi yêu cầu |
| "`AtomicInteger` biến cả quy trình thành thread-safe" | Chỉ các thao tác mà nó bảo đảm mới atomic | Đánh giá shared state và transaction tổng thể |
| "Biên dịch qua nghĩa là song song an toàn" | Kiểm tra capture khác với đồng bộ bộ nhớ | Tránh shared mutable state hoặc dùng cơ chế đúng |
| "Lambda giữ snapshot tự động của List" | Lambda capture tham chiếu, không tự nhân bản trạng thái object | Copy phòng vệ có chủ đích |
| "`Collections.unmodifiableList` là snapshot" | Nó thường là wrapper view lên source | Chọn `List.copyOf` nếu muốn snapshot cấu trúc |
| "Gán tham chiếu khác cũng sửa object cũ" | Gán lại biến chỉ đổi binding, object cũ không trực tiếp đổi | Vẽ sơ đồ alias để kiểm tra |

## 13. Checklist đánh giá code lambda

Trước khi dùng một lambda có capture biến ngoài, hãy xác định:

1. Biến được truy cập là **local**, **tham số**, **field** hay **static field**?
2. Nếu là local/parameter được capture: có `final` hoặc effectively final không? Có phép gán lại, `++` hoặc `--` nào tác động lên biến không?
3. Giá trị được capture là **primitive/immutable value** hay **tham chiếu tới object mutable**?
4. Lambda có gọi phương thức thay đổi object được tham chiếu hoặc field bên ngoài không?
5. Có **alias** nào khác cùng trỏ tới object có thể mutate? Lambda có thể được gọi sau khi object đổi trạng thái không?
6. Nếu lambda chạy trên nhiều thread, ai đảm bảo **visibility**, **atomicity** và thứ tự cập nhật? Có thể tránh chia sẻ trạng thái không?
7. Nếu cần snapshot, đó là snapshot **giá trị**, **cấu trúc collection**, hay **deep snapshot phần tử**?
8. Nếu mục tiêu là tính toán, có thể trả kết quả bằng `Function`/`Supplier` hoặc dùng `map`/`reduce`/`collect` để giảm side effect không?

## 14. Kết luận và tài liệu tra cứu

**Gán lại biến** thay giá trị lưu trong biến (ví dụ thay tham chiếu sang object mới). **Thay đổi object được tham chiếu** sửa trạng thái của object mà không gán lại biến. Với biến local được lambda capture, Java yêu cầu `final` hoặc **effectively final** nên phép gán lại bị hạn chế; mutation của object mutable vẫn có thể biên dịch và chạy.

Quy tắc này giúp hiểu cú pháp và phạm vi, **không phải lời hứa về immutability hoặc thread safety**. Để có code dễ kiểm thử và an toàn hơn, hãy làm rõ ranh giới side effect, ưu tiên dữ liệu bất biến khi phù hợp, tránh chia sẻ mutable state không được đồng bộ và dùng reduction thay cho cập nhật biến ngoài khi cần kết quả tổng hợp.

Tài liệu chính thức: *Java Language Specification* về **`4.12.4 final Variables`**, **`15.27 Lambda Expressions`** và phạm vi biến trong Java; Javadoc **`java.util.List`**, **`java.util.concurrent.atomic.AtomicInteger`**, **`java.util.function`**, **`java.util.stream.Stream`**.
