# Đánh giá mức độ rõ kiểu từ biểu thức khởi tạo khi dùng `var` trong Java

## Mục tiêu bài học

Từ Java 10, `var` cho phép trình biên dịch suy luận kiểu của **biến cục bộ** từ biểu thức khởi tạo. Tuy nhiên, một khai báo hợp lệ về mặt cú pháp vẫn có thể khiến người đọc khó hiểu biến có kiểu gì. Bài này hướng dẫn cách **đánh giá mức độ rõ kiểu ngay tại nơi khai báo**, lựa chọn giữa `var` và kiểu tường minh, và cải thiện tên biến hoặc biểu thức khởi tạo khi cần.

Sau bài học, bạn sẽ có thể:

- Phân biệt **kiểu tĩnh được trình biên dịch suy luận** với **mức độ rõ kiểu đối với người đọc**.
- Nhận ra những biểu thức khởi tạo bộc lộ kiểu tốt: literal, constructor, lời gọi factory có đối số và kiểu rõ ràng.
- Phát hiện các biểu thức dễ gây hiểu lầm: generic rỗng, phương thức trả về không hiển nhiên, chuỗi lời gọi dài, số học hoặc biểu thức điều kiện phức tạp.
- Chọn cách viết giúp code dễ đọc và dễ bảo trì mà vẫn giữ kiểm tra kiểu tĩnh của Java.

> `var` vẫn là tính năng hiện hành của Java; các ví dụ sử dụng cú pháp và API còn áp dụng với Java 17 trở lên.

## 1. "Rõ kiểu" có nghĩa là gì?

Xem hai khai báo:

~~~java
var names = new ArrayList<String>();
var value = calculate();
~~~

Ở dòng đầu, biểu thức `new ArrayList<String>()` trực tiếp cho thấy **kiểu tĩnh của biến** là `ArrayList<String>`. Ở dòng thứ hai, muốn biết kiểu của `value`, người đọc phải tìm đến khai báo của `calculate()` (và có thể còn phải đọc thêm API xung quanh). Cả hai đều có thể biên dịch, nhưng mức độ rõ kiểu khác nhau.

Với `var`, **trình biên dịch luôn cần suy luận được kiểu**; điều đó không bảo đảm **người đọc nhận ra kiểu nhanh và chính xác**. Khi đánh giá, hãy đặt mình vào vị trí người đang đọc đoạn mã ở nơi khai báo, không chỉ dựa vào việc IDE có thể hiển thị kiểu khi rê chuột.

Ba câu hỏi cốt lõi:

1. **Nhìn biểu thức bên phải có nhận ra kiểu tĩnh không?** Ví dụ `new HashMap<String, Integer>()` cho thấy rõ, còn `fetch()` không nói rõ.
2. **Nhận ra kiểu rồi, có hiểu được ý nghĩa của biến không?** Tên `status`, `userIds`, `timeoutMillis` có thể bổ sung ý nghĩa mà tên `x` hoặc `result` không có.
3. **Kiểu tĩnh có quan trọng đối với phần mã phía sau không?** Nếu cần người đọc biết `Optional<User>`, `List<String>` hay một interface, khai báo tường minh đôi khi giúp tránh hiểu sai.

Sự rõ ràng không phải một điểm số cố định: nó phụ thuộc vào độ quen thuộc của API, tên biến, phạm vi sử dụng và mục đích của đoạn mã.

## 2. Trình biên dịch thực sự làm gì với `var`?

Trong khai báo `var identifier = initializer;`, trình biên dịch xác định kiểu của biểu thức khởi tạo ở **thời điểm biên dịch** rồi gán kiểu đó cho biến cục bộ. Biến vẫn được kiểm tra kiểu tĩnh và **không đổi kiểu sau khi khai báo**.

~~~java
var quantity = 10;               // int
var caption = "Java";             // String
var maxWaitMillis = 2_000L;      // long
var ratio = 0.5;                 // double

// quantity = "mười";           // Lỗi: String không gán được cho int
~~~

`var` không tự chọn kiểu số có dung lượng nhỏ nhất, không làm biến trở thành kiểu động và không mặc định biến là `Object`. Kiểu phụ thuộc vào **kiểu thực tế của biểu thức bên phải**.

Trong Java hiện đại, `var` chủ yếu được dùng với biến cục bộ, kể cả biến trong vòng lặp enhanced `for` và một số khai báo `for`. Không thể dùng `var` để khai báo field hoặc kiểu trả về của phương thức; biểu thức khởi tạo ở khai báo biến cục bộ thông thường là điều kiện thiết yếu.

Ví dụ mã minh họa không hợp lệ:

~~~java
// var missing;       // Không có initializer nên không suy luận được kiểu
// var nothing = null; // Chỉ null không đủ để suy luận kiểu
~~~

Nói cách khác: **khả năng suy luận của compiler** là điều kiện để mã hợp lệ; **khả năng người đọc hiểu kiểu** là tiêu chí lựa chọn phong cách viết.

## 3. Phân loại mức độ rõ kiểu từ biểu thức khởi tạo

Bảng sau dùng ba mức để hỗ trợ review; đây là **hướng dẫn đọc mã**, không phải quy tắc bắt buộc của ngôn ngữ.

| Dạng khởi tạo | Ví dụ | Đánh giá và lưu ý |
| --- | --- | --- |
| Literal có kiểu dễ nhận ra | `var attempts = 3;` | **Rõ:** `int`. |
| Literal có hậu tố | `var timeoutMillis = 500L;` | **Rõ:** `long`; hậu tố `L` cho biết kiểu. |
| Constructor nêu kiểu đầy đủ | `var names = new ArrayList<String>();` | **Rõ:** `ArrayList<String>`, gồm cả generic. |
| Constructor có tên lớp cụ thể | `var date = LocalDate.of(2026, 1, 1);` | **Khá rõ:** `LocalDate` nếu biết factory của lớp. |
| Factory có phần tử | `var tags = List.of("java", "core");` | **Khá rõ:** `List<String>` với API quen thuộc. |
| Factory generic rỗng | `var tags = List.of();` | **Dễ hiểu nhầm:** `List<Object>`; chưa thấy kiểu phần tử mong muốn. |
| Diamond không có kiểu đích | `var tags = new ArrayList<>();` | **Dễ hiểu nhầm:** `ArrayList<Object>` khi constructor không có đối số hữu ích để suy luận. |
| Lời gọi nghiệp vụ | `var data = loadTasks();` | **Cần ngữ cảnh:** phải biết chữ ký `loadTasks()`. |
| Chuỗi xử lý dài | `var data = source.stream().map(...).toList();` | **Cần ngữ cảnh:** kiểu phụ thuộc phần tử sau `map`. |
| Biểu thức số học | `var avg = 7 / 2;` | **Dễ hiểu nhầm:** `int`, giá trị là 3, không phải 3,5. |

Các ví dụ trong bảng là **đoạn mã minh họa**, không phải chương trình độc lập; khi dùng cần import các lớp liên quan và có biến/phương thức được khai báo tương ứng.

Không nên chỉ nhìn số ký tự ở vế phải: biểu thức ngắn `find()` có thể mờ kiểu hơn `new LinkedHashMap<String, Integer>()`, còn biểu thức dài nhưng các bước đặt tên rõ ràng vẫn có thể dễ đọc.

## 4. Những trường hợp `var` giúp mã rõ và gọn

### 4.1. Constructor nêu chính xác kiểu

~~~java
var scores = new HashMap<String, Integer>();
var names = new ArrayList<String>();
~~~

Không cần viết lại cùng tên lớp ở hai phía của phép gán. Người đọc vẫn thấy cả lớp cụ thể lẫn tham số kiểu. So sánh với:

~~~java
HashMap<String, Integer> scores = new HashMap<>();
ArrayList<String> names = new ArrayList<>();
~~~

Hai phong cách đều hợp lệ. Với `var`, kiểu tĩnh của biến là chính lớp constructor (`HashMap`, `ArrayList`), không phải tự động là interface `Map` hoặc `List`.

Nếu mục tiêu là thiết kế theo một abstraction nhất định, hãy cân nhắc:

~~~java
Map<String, Integer> scores = new HashMap<>();
List<String> names = new ArrayList<>();
~~~

Các dòng này thể hiện rõ kiểu tĩnh mong muốn là **interface**, điều hữu ích nếu không muốn mã sử dụng các phương thức chỉ có ở một implementation cụ thể.

### 4.2. Biểu thức khởi tạo vốn đã thể hiện kiểu

~~~java
var active = true;               // boolean
var greeting = "Xin chào";       // String
var key = 'A';                   // char
var elapsedMillis = 1_500L;      // long
var labels = List.of("A", "B");   // List<String>
~~~

`var` phù hợp khi một người đọc Java có thể nhận biết kiểu mà không phải đi tìm chữ ký trả về. Tên biến vẫn phải nói rõ **vai trò hoặc đơn vị**: `elapsedMillis` tốt hơn `n` ngay cả khi cả hai đều có kiểu `long`.

### 4.3. Phạm vi biến ngắn và cách dùng nhất quán

~~~java
for (var name : List.of("An", "Binh")) {
    System.out.println(name.toUpperCase());
}
~~~

Ở đây nguồn lặp cho biết phần tử là `String`, và biến chỉ dùng trong vài dòng. Mức độ rõ kiểu đủ tốt để dùng `var`. Với phương thức dài hoặc biến đi qua nhiều nhánh điều kiện, người đọc có thể cần thêm tín hiệu kiểu ngay tại khai báo.

## 5. Những trường hợp nên viết kiểu tường minh hoặc cải thiện initializer

### 5.1. Phương thức không làm lộ kiểu trả về

~~~java
var result = loadTasks();
var value = findTask("A");
~~~

Giả sử `loadTasks()` trả về `List<Task>` và `findTask(...)` trả về `Optional<Task>`. Người đọc sẽ không tự suy ra những kiểu đó chỉ từ tên biến `result`, `value`. Đặc biệt, `findTask` không cho biết nó trả `Task` trực tiếp hay một wrapper `Optional<Task>`.

Khi kiểu ảnh hưởng đến cách xử lý tiếp theo, viết:

~~~java
List<Task> tasks = loadTasks();
Optional<Task> maybeTask = findTask("A");
~~~

Hoặc giữ `var` với tên gợi ý cấu trúc dữ liệu, nếu API đã quen thuộc và kiểu không phải điều cần nhấn mạnh:

~~~java
var tasks = loadTasks();
var maybeTask = findTask("A");
~~~

Cách thứ hai dễ đọc hơn `var value`, nhưng **tên biến không thay thế việc biết chính xác kiểu**. Trong code review phức tạp, kiểu khai báo tường minh có thể là lựa chọn rõ hơn.

### 5.2. Factory generic rỗng thiếu thông tin suy luận

~~~java
var names = List.of();            // List<Object>
var maybeName = Optional.empty(); // Optional<Object>
var items = new ArrayList<>();    // ArrayList<Object>
~~~

Các khai báo này hợp lệ nhưng thường **không diễn đạt đúng kiểu phần tử mà người viết mong muốn**. Khi không có đối số và không có kiểu đích, generic có thể suy luận `Object`.

Các cách diễn đạt rõ hơn:

~~~java
List<String> names = List.of();
Optional<String> maybeName = Optional.empty();
var writableNames = new ArrayList<String>();

// Type witness dành cho generic factory method:
var namedEmpty = List.<String>of();
var optionalName = Optional.<String>empty();
~~~

`List<Object>` và `List<String>` không thể dùng thay nhau tùy ý: Java generics là invariant. Đây là **khác biệt thật trong kiểu tĩnh**, không chỉ là vấn đề thẩm mỹ.

### 5.3. Biểu thức số học che mất kiểu và giá trị

~~~java
var quotient = 7 / 2;       // int, giá trị 3
var exact = 7.0 / 2;        // double, giá trị 3.5
var amount = 100;           // int
var longAmount = 100L;      // long
~~~

Nếu người đọc dễ tưởng `quotient` là số thực, hãy đổi biểu thức để bộc lộ phép toán mong muốn, ví dụ `7.0 / 2`, hoặc khai báo kiểu khi kiểu là một phần quan trọng của nghiệp vụ.

Lưu ý viết `double quotient = 7 / 2;` **không sửa phép chia số nguyên**: phép chia vẫn cho 3 trước khi chuyển sang `double` thành 3.0. Cần sửa chính biểu thức khởi tạo.

### 5.4. Biểu thức điều kiện hoặc chuỗi gọi dài

~~~java
// Minh họa: preferLinked có kiểu boolean.
List<String> names =
        preferLinked ? new LinkedList<>() : new ArrayList<>();
~~~

Hai nhánh khởi tạo hai implementation khác nhau; khai báo `List<String>` cho người đọc biết abstraction được sử dụng. Nếu viết `var names = preferLinked ? new LinkedList<String>() : new ArrayList<String>();`, kiểu tĩnh suy luận có thể khó nhận ra chỉ qua một lượt đọc, vì trình biên dịch cần tìm kiểu chung của biểu thức điều kiện.

Tương tự, chuỗi `stream().filter(...).map(...).toList()` có thể cần đọc hết lambda và generic ở nhiều bước mới biết kiểu phần tử cuối cùng. Trong các trường hợp này, khai báo kiểu tường minh hoặc tách biểu thức thành các biến trung gian có tên tốt sẽ giúp việc đọc và debug.

## 6. Chương trình Java 17+ chạy độc lập

Ví dụ này minh họa lựa chọn có chủ đích: dùng `var` khi initializer làm lộ kiểu, viết kiểu tường minh khi trả về từ một API nội bộ không tự giải thích rõ cấu trúc dữ liệu.

Lưu toàn bộ nội dung vào file **VarReadabilityDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class VarReadabilityDemo {
    private record Task(String name, int points) {}

    private static List<Task> loadTasks() {
        return List.of(new Task("A", 2), new Task("B", 3));
    }

    private static Optional<Task> findTask(String name) {
        return loadTasks().stream()
                .filter(task -> task.name().equals(name))
                .findFirst();
    }

    private static int sumPoints(List<Task> tasks) {
        return tasks.stream().mapToInt(Task::points).sum();
    }

    public static void main(String[] args) {
        var retries = 3;                       // int: literal rõ kiểu
        var waitMillis = 2_000L;               // long: hậu tố L rõ kiểu

        var names = new ArrayList<String>();   // ArrayList<String>
        names.add("An");
        names.add("Binh");

        var tags = List.of("core", "java");     // List<String>

        // API nghiệp vụ: viết rõ hợp đồng trả về.
        List<Task> tasks = loadTasks();
        Optional<Task> maybeTask = findTask("A");

        var total = sumPoints(tasks);          // int: tên hàm gợi ý, kiểu từ API
        var emptyNames = List.<String>of();    // List<String>, có type witness

        System.out.println("Retries: " + retries);
        System.out.println("Wait ms: " + waitMillis);
        System.out.println("Names: " + names);
        System.out.println("Tags: " + tags);
        System.out.println("Total points: " + total);
        System.out.println("Found: " + maybeTask.map(Task::name).orElse("none"));
        System.out.println("Typed empty: " + emptyNames.size());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac VarReadabilityDemo.java
java VarReadabilityDemo
~~~

Kết quả chính xác:

~~~text
Retries: 3
Wait ms: 2000
Names: [An, Binh]
Tags: [core, java]
Total points: 5
Found: A
Typed empty: 0
~~~

Giải thích:

- `retries` là `int`; `waitMillis` là `long`, bộc lộ trực tiếp từ literal.
- `names` là `ArrayList<String>`, vì constructor chỉ rõ lớp và tham số kiểu; `tags` là `List<String>`, nhờ các đối số chuỗi của `List.of`.
- `loadTasks()` trả về `List<Task>`, còn `findTask(...)` trả về `Optional<Task>`. Khai báo tường minh giúp người đọc thấy ngay hai hợp đồng đó.
- `total` là `int`, suy luận từ kiểu trả về của `sumPoints`. Đây là ví dụ mà `var` vẫn biên dịch chính xác nhưng việc **hiểu kiểu phụ thuộc vào API**. Nếu người đọc chưa quen `sumPoints`, khai báo `int total = sumPoints(tasks);` có thể rõ hơn.
- `List.<String>of()` khắc phục trường hợp `List.of()` trống suy luận `List<Object>`; vì thế `emptyNames` có kiểu tĩnh `List<String>`.

Đoạn mã dùng `record` (hỗ trợ trong Java 17) để biểu diễn `Task` ngắn gọn và rõ ràng. Chương trình không phụ thuộc thư viện ngoài và không có dữ liệu ngẫu nhiên, nên đầu ra xác định.

## 7. Một số lỗi tư duy phổ biến khi đánh giá độ rõ kiểu

**Nhầm 1: "Compiler suy luận được thì người đọc sẽ hiểu ngay."** Java kiểm tra kiểu bằng toàn bộ thông tin có tại thời điểm biên dịch; người đọc có thể chỉ nhìn vài dòng. Vì thế những tên phương thức ngắn, các factory rỗng hoặc các chuỗi xử lý dài vẫn có thể gây khó hiểu.

**Nhầm 2: "Tên biến đủ nói lên kiểu."** Tên `items` không cho biết đây là `List<String>`, `Set<String>`, `Stream<String>` hay `Iterable<String>`. Tên tốt hỗ trợ hiểu ý nghĩa, nhưng cần kiểu tường minh khi loại cấu trúc dữ liệu là điều quan trọng.

**Nhầm 3: "`var` lúc nào cũng suy ra interface."** `var map = new HashMap<String, Integer>();` có kiểu tĩnh `HashMap<String, Integer>`, không tự trở thành `Map<String, Integer>`. Nếu cần đặt ra hợp đồng thao tác qua interface, hãy cân nhắc khai báo `Map<String, Integer> map = new HashMap<>();`.

**Nhầm 4: "Giá trị nhỏ thì biến có kiểu nhỏ."** `var n = 1;` suy luận `int`, không phải `byte`. `var n = 1L;` suy luận `long`. Kiểm tra kiểu của biểu thức và các hậu tố literal trước khi kết luận.

**Nhầm 5: "Dùng `var` để khỏi cần hiểu generic."** `var values = new ArrayList<>();` không tự biết bạn muốn `String`; với constructor rỗng, nó suy luận `ArrayList<Object>`. Hãy nêu kiểu ở constructor, cung cấp ngữ cảnh hợp lệ hoặc khai báo biến tường minh.

**Nhầm 6: "Phải dùng `var` ở mọi chỗ để code nhất quán."** Java không yêu cầu như vậy. Trong cùng một phương thức, có thể dùng `var` cho biểu thức rõ kiểu và kiểu tường minh cho những biến mang hợp đồng hoặc có initializer khó hiểu.

## 8. Cách tự review một khai báo `var`

Khi quyết định giữ hay thay `var`, hãy kiểm tra theo thứ tự:

1. **Nhận biết kiểu:** Chỉ nhìn vế phải, bạn có thể nói chính xác kiểu tĩnh không, kể cả generic?
2. **Ngữ cảnh gần:** Có cần mở một phương thức khác hoặc dò nhiều lớp mới biết kiểu không?
3. **Ý nghĩa của biến:** Tên biến cho biết đối tượng/vai trò/đơn vị hay chỉ là `data`, `value`, `result`?
4. **Phần mã sau:** Cách sử dụng có đòi hỏi biết interface, Optional, kiểu số hoặc khả năng sửa collection không?
5. **Độ dài phạm vi:** Biến được dùng trong vài dòng hay truyền qua nhiều nhánh logic?
6. **Cách cải thiện:** Viết kiểu tường minh có tăng rõ ràng không? Có thể đặt tên tốt hơn, thêm type witness, hoặc tách biểu thức dài không?

Một hướng dẫn thực dụng:

| Mức độ | Dấu hiệu | Gợi ý |
| --- | --- | --- |
| Rõ | Literal có kiểu rõ; constructor cho thấy generic; factory quen thuộc với đối số cụ thể | Thường giữ `var` |
| Cần chút ngữ cảnh | Factory hoặc phương thức có tên tốt nhưng kiểu trả về không hiện ra ngay | Dựa vào phạm vi và người đọc; cân nhắc tên biến hoặc kiểu tường minh |
| Khó nhận biết | Generic rỗng, lời gọi mơ hồ, chuỗi xử lý dài, kiểu số dễ nhầm, nhiều implementation | Viết kiểu tường minh hoặc làm rõ initializer |

Đây là tiêu chí để trao đổi trong code review, **không phải lệnh cấm hay yêu cầu đổi mọi khai báo `var`**.

## 9. Bài tập tự kiểm tra

Đánh giá độ rõ kiểu và nêu kiểu tĩnh (nếu đủ thông tin):

~~~java
var a = 42;
var b = 42L;
var c = "Java";
var d = List.of("a", "b");
var e = List.of();
var f = new ArrayList<>();
var g = new ArrayList<String>();
var h = LocalDate.of(2026, 1, 1);
var i = 5 / 2;
var j = loadTasks();
~~~

**Đáp án:**

| Biến | Kiểu tĩnh | Đánh giá |
| --- | --- | --- |
| `a` | `int` | Rõ |
| `b` | `long` | Rõ nhờ `L` |
| `c` | `String` | Rõ |
| `d` | `List<String>` | Khá rõ với API `List.of` |
| `e` | `List<Object>` | Dễ hiểu nhầm nếu muốn `List<String>` |
| `f` | `ArrayList<Object>` | Dễ hiểu nhầm vì diamond thiếu kiểu đích |
| `g` | `ArrayList<String>` | Rõ |
| `h` | `LocalDate` | Khá rõ khi biết API `LocalDate.of` |
| `i` | `int`, giá trị 2 | Dễ hiểu nhầm nếu tưởng là số thực |
| `j` | `List<Task>` **trong chương trình ở mục 6** | Cần xem chữ ký `loadTasks`; đứng riêng thì chưa đủ thông tin |

Các ví dụ ở mục 9 là mã minh họa và giả định đã import các lớp cần thiết. Với `j`, kiểu chỉ xác định được sau khi biết chữ ký phương thức tương ứng; một hàm cùng tên ở mã khác có thể trả kiểu khác.

## 10. Ghi nhớ

- **Suy luận kiểu** là hoạt động của trình biên dịch; **độ rõ kiểu** là chất lượng mã đối với người đọc.
- Dùng `var` khi biểu thức khởi tạo và tên biến khiến kiểu tĩnh dễ nhận ra, nhất là với literal hoặc constructor có generic rõ ràng.
- Đặc biệt chú ý API trả về mơ hồ, `List.of()` và `new ArrayList<>()` rỗng, phép toán số, biểu thức điều kiện và chuỗi xử lý dài.
- Viết kiểu tường minh khi bạn cần thể hiện interface, kiểu generic, wrapper như `Optional`, hoặc một hợp đồng quan trọng.
- `var` không tự làm mất kiểm tra kiểu, cũng không đảm bảo mã dễ đọc hơn; lựa chọn hợp lý nhất tùy vào vị trí sử dụng và ngữ cảnh.

Tài liệu tham khảo hiện hành:

- [Java Language Specification §14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4.1) — quy tắc suy luận kiểu của biến cục bộ.
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide) — nguyên tắc đánh giá tính dễ đọc và sự rõ ràng khi dùng `var`.
- [Java Language Specification §5.1 — Kinds of Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1) — cơ sở về chuyển đổi và kiểu tĩnh trong Java.

**Kết luận:** Câu hỏi quan trọng khi dùng `var` không dừng ở việc "compiler có suy luận được kiểu hay không", mà là "một người đọc có hiểu nhanh kiểu và vai trò của biến tại nơi nó được khai báo hay không?". Hãy dùng `var` khi biểu thức khởi tạo làm rõ điều đó và viết kiểu tường minh khi nó giúp truyền đạt ý định tốt hơn.
