# Tách biểu thức lồng nhau thành các bước trung gian với `var`

*Chủ đề Java 10 — Sử dụng `var` rõ ràng. Nội dung tập trung vào kỹ thuật đọc, hiểu, bảo trì và kiểm thử mã Java vẫn có giá trị trên Java 17+ và các phiên bản hiện đại.*

## 1. Mục tiêu và nguyên tắc

Khi nhiều lời gọi phương thức, phép lọc, điều kiện, truy cập dữ liệu và phép biến đổi được ghép trong một biểu thức dài, người đọc phải giữ nhiều trạng thái trong đầu để hiểu kết quả. **Tách biểu thức lồng nhau thành các bước trung gian có tên rõ ràng** giúp mỗi bước trả lời một câu hỏi: dữ liệu lấy từ đâu, đã được kiểm tra chưa, đang được lọc theo điều kiện gì và kết quả cuối cùng là gì.

Từ Java 10, `var` giúp khai báo **biến cục bộ** ở các bước đó mà không phải viết lại kiểu generic dài. Kiểu của biến vẫn được **suy luận tĩnh tại lúc biên dịch** từ biểu thức khởi tạo: `var` không phải kiểu động, không làm biến thay đổi kiểu lúc chạy và không thay đổi cách Java thực thi các biểu thức.

Ví dụ về ý tưởng (các tên `repository`, `formatter` và `request` là đối tượng giả định đã được khai báo trong chương trình thực tế):

~~~java
// Một biểu thức lồng nhiều trách nhiệm:
var output = formatter.format(repository.find(request.id())
        .stream().filter(item -> item.isActive()).toList());

// Tách theo ý nghĩa:
var requestId = request.id();
var foundItems = repository.find(requestId);
var activeItems = foundItems.stream()
        .filter(item -> item.isActive())
        .toList();
var output2 = formatter.format(activeItems);
~~~

Đoạn mã trên chỉ **minh họa cách refactor**, không phải tệp Java độc lập. Phần chương trình đầy đủ chạy được nằm ở mục 4. Khi mã gốc có thể phát sinh `null`, tác dụng phụ, luồng dữ liệu dùng một lần hoặc các bước tính toán đắt đỏ, việc tách phải giữ đúng ngữ nghĩa; bài này giải thích các giới hạn đó.

## 2. Khi nào một biểu thức nên được tách?

Một biểu thức bắt đầu khó đọc khi nó trộn **nhiều trách nhiệm**:

- Truy xuất dữ liệu: `ordersByCustomer.get(customerId)`.
- Xử lý trường hợp không có dữ liệu: `getOrDefault(..., List.of())` hoặc kiểm tra `null`.
- Lọc: `filter(task -> !task.done())`.
- Chuyển đổi: `map(Task::title)` hoặc `mapToInt(Task::minutes)`.
- Tổng hợp: `sum()`, `count()` hoặc `toList()`.
- Trình bày: `String.join(", ", titles)`.

Ví dụ biểu thức một dòng:

~~~java
var total = tasksByTeam.getOrDefault("backend", List.of())
        .stream().filter(task -> !task.done())
        .mapToInt(Task::minutes).sum();
~~~

Cách này **đúng** và đôi khi rất dễ đọc. Nhưng khi phải thêm kiểm tra dữ liệu, theo dõi lỗi, đặt breakpoint hay tái sử dụng danh sách đã lọc, có thể tách:

~~~java
var team = "backend";                                      // String
var tasks = tasksByTeam.getOrDefault(team, List.of());     // List<Task>
var pending = tasks.stream().filter(task -> !task.done())
        .toList();                                          // List<Task>
var totalMinutes = pending.stream().mapToInt(Task::minutes)
        .sum();                                             // int
~~~

Bốn tên này cho biết **ngữ nghĩa** tại từng bước; `var` giúp mã không cần lặp `List<Task>`. Kỹ thuật này phù hợp nhất khi dữ liệu trung gian có giá trị để hiểu, xác thực, ghi log có kiểm soát hoặc sử dụng nhiều hơn một lần.

Không có quy tắc “hễ thấy hai dấu chấm là phải tách”. Chọn ranh giới dựa trên **ý nghĩa nghiệp vụ** và sự dễ đọc.

## 3. Phương pháp tách theo từng bước

### Bước 1: Xác định đầu vào và kết quả cuối

Trước khi refactor, viết rõ biểu thức dùng dữ liệu nào, kết quả mong muốn có kiểu gì và điều gì có thể thất bại. Với ví dụ nhóm công việc:

- Đầu vào: map chứa `List<Task>` theo tên nhóm.
- Điều kiện: chỉ lấy `Task` chưa hoàn tất.
- Kết quả: tổng số phút `int`.
- Tình huống biên: tên nhóm không tồn tại.

Nắm điều này giúp không tùy tiện sửa logic khi chỉ định cải thiện khả năng đọc.

### Bước 2: Chọn các ranh giới có tên cụ thể

~~~java
var allTasks = tasksByTeam.getOrDefault(team, List.of());
var pendingTasks = allTasks.stream()
        .filter(task -> !task.done())
        .toList();
var estimatedMinutes = pendingTasks.stream()
        .mapToInt(Task::minutes)
        .sum();
~~~

`allTasks`, `pendingTasks` và `estimatedMinutes` dễ hiểu hơn `x`, `tmp`, `data2`. Biến trung gian nên có một vai trò rõ ràng; đừng tách mọi lời gọi `get`, `size` hay phép cộng thành hàng chục biến vô nghĩa.

### Bước 3: Kiểm tra kiểu compiler đã suy luận

Ở ví dụ trên:

| Biến trung gian | Kiểu tĩnh có thể suy luận | Ý nghĩa |
| --- | --- | --- |
| `team` | `String` | Khóa tra cứu |
| `tasksByTeam` | `Map<String, List<Task>>` trong ví dụ đầy đủ | Bảng tra dữ liệu |
| `allTasks` | `List<Task>` | Các công việc theo nhóm |
| `pendingTasks` | `List<Task>` | Danh sách công việc chưa hoàn tất |
| `estimatedMinutes` | `int` | Tổng phút dự kiến |

Sự suy luận xuất phát từ kiểu phương thức ở vế phải, ví dụ `Map.getOrDefault`, `Stream.toList` và `IntStream.sum`. `var` không che giấu kiểu với trình biên dịch; nó chỉ khiến người đọc phải nhìn vào biểu thức bên phải để hiểu kiểu đó.

Nếu kiểu từ vế phải **khó nhận ra hoặc không đúng ý định**, viết kiểu tường minh là lựa chọn tốt hơn:

~~~java
List<Task> pendingTasks = allTasks.stream()
        .filter(task -> !task.done())
        .toList();
~~~

### Bước 4: Đặt kiểm tra lỗi ở đúng vị trí

Khi một bước có thể trả về `null`, kiểm tra tại chính bước đó thay vì truy cập tiếp rồi nhận `NullPointerException` không rõ nguyên nhân:

~~~java
var tasks = tasksByTeam.get(team);  // Có thể null
if (tasks == null) {
    throw new IllegalArgumentException("Unknown team: " + team);
}
var pending = tasks.stream().filter(task -> !task.done()).toList();
~~~

Lưu ý: kiểm tra rồi ném `IllegalArgumentException` là **thay đổi hành vi xử lý lỗi có chủ ý** so với một chuỗi gọi trực tiếp gây `NullPointerException`. Khi chỉ refactor mà cần giữ hành vi tuyệt đối, phải quyết định và kiểm thử đường lỗi tương ứng. Nếu bài toán cho phép coi “không có nhóm” là tập rỗng, `getOrDefault(team, List.of())` là một lựa chọn khác.

### Bước 5: So sánh với hành vi cũ

Sau khi tách, dùng cùng dữ liệu thử nghiệm để xác nhận giá trị, thứ tự và ngoại lệ dự kiến. Nếu chuỗi ban đầu chỉ duyệt một lần mà phiên bản tách lại materialize `toList()`, xem thêm ảnh hưởng về bộ nhớ/độ trễ (mục 5).

## 4. Chương trình hoàn chỉnh Java 17+: trước và sau khi tách

Chương trình mẫu sau mô tả nhóm công việc. Nó dùng `record` và `Stream.toList()` (đều có trong Java 17); cú pháp suy luận kiểu cục bộ `var` được đưa vào từ Java 10. Cấu trúc ví dụ giúp người học hiện nay có thể biên dịch bằng JDK 17+.

~~~java
// File: BreakDownVarDemo.java
import java.util.List;
import java.util.Map;

public class BreakDownVarDemo {
    record Task(String title, int minutes, boolean done) { }

    public static void main(String[] args) {
        var tasksByTeam = Map.of(
            "backend", List.of(
                new Task("Review", 30, false),
                new Task("Build", 45, true),
                new Task("Test", 20, false)),
            "frontend", List.of(new Task("Design", 15, false)));

        var team = "backend";
        var tasks = tasksByTeam.getOrDefault(team, List.of());
        var pending = tasks.stream()
                .filter(task -> !task.done())
                .toList();
        var titles = pending.stream()
                .map(Task::title)
                .toList();
        var totalMinutes = pending.stream()
                .mapToInt(Task::minutes)
                .sum();
        var summary = String.join(", ", titles);

        var inlineMinutes = tasksByTeam.getOrDefault(team, List.of())
                .stream()
                .filter(task -> !task.done())
                .mapToInt(Task::minutes)
                .sum();

        System.out.println("team = " + team);
        System.out.println("pending = " + summary);
        System.out.println("count = " + pending.size());
        System.out.println("minutes = " + totalMinutes);
        System.out.println("same as inline = " + (totalMinutes == inlineMinutes));

        var missing = tasksByTeam.getOrDefault("unknown", List.of());
        System.out.println("unknown = " + missing.size());
    }
}
~~~

Lưu trong `BreakDownVarDemo.java`, mở terminal tại thư mục chứa tệp:

~~~bash
javac --release 17 BreakDownVarDemo.java
java BreakDownVarDemo
~~~

Stdout đã được kiểm chứng bằng chương trình biên dịch và chạy:

~~~text
team = backend
pending = Review, Test
count = 2
minutes = 50
same as inline = true
unknown = 0
~~~

**Vì sao ví dụ đáng học:**

1. `tasksByTeam` có kiểu `Map<String, List<Task>>` nhờ `Map.of` nhận các danh sách `Task`. `var` không bỏ mất kiểu generic.
2. `tasks` là `List<Task>` từ `getOrDefault`; nhóm vắng mặt nhận danh sách rỗng ở ví dụ này.
3. `pending` là `List<Task>` sau khi lọc bằng `filter` và gom thành `toList()`. Các phần tử đã hoàn tất bị bỏ qua.
4. `titles` là `List<String>` vì `Task::title` trả về `String`. `summary` là `String` do `String.join`.
5. `totalMinutes` là `int` vì `mapToInt` tạo `IntStream` và `sum` trả về `int`.
6. `inlineMinutes` tính lại cùng biểu thức ở dạng chuỗi; kết quả bằng 50 giống phiên bản tách bước. Đây là một phép đối chiếu **chỉ dành cho ví dụ dữ liệu không đổi và phép toán không có tác dụng phụ**. Không nên tính hai lần ở môi trường thực tế chỉ để so sánh.
7. `pending` chứa hai công việc “Review” và “Test” theo thứ tự nguồn; trong ví dụ dữ liệu ban đầu là `List` nên thứ tự đó được giữ qua các thao tác stream có thứ tự.

## 5. Lưu ý lớn: tách `Stream` không phải lúc nào cũng miễn phí

### 5.1. `Stream` được dùng cho một lượt terminal operation

~~~java
var stream = tasks.stream().filter(task -> !task.done());
var count = stream.count(); 
// var titles = stream.map(Task::title).toList(); // Sai lúc chạy: stream đã dùng
~~~

Sau `count()`, `stream` đã được tiêu thụ; không thể dùng lại cùng đối tượng stream cho một terminal operation khác. `var` không thay đổi vòng đời đó.

Nếu cần nhiều kết quả từ cùng tập dữ liệu, có thể **materialize một lần**:

~~~java
var pending = tasks.stream()
        .filter(task -> !task.done())
        .toList();

var count = pending.size();
var titles = pending.stream().map(Task::title).toList();
var total = pending.stream().mapToInt(Task::minutes).sum();
~~~

Ở đây mỗi lời gọi `pending.stream()` tạo **một stream mới** từ danh sách đã có. Dữ liệu được lọc một lần rồi có thể đọc lại. Tuy nhiên, việc tạo danh sách `pending` tốn bộ nhớ và thường duyệt qua toàn bộ nguồn trước các phép xử lý tiếp theo.

### 5.2. Phân biệt pipeline lazy và việc materialize

~~~java
var filteredStream = tasks.stream()
        .filter(task -> !task.done());  // Chưa chạy terminal operation
var minutes = filteredStream
        .mapToInt(Task::minutes)
        .sum();                         // Chạy pipeline tại đây
~~~

Các intermediate operation như `filter`, `map` về cơ bản **lazy**; dữ liệu được xử lý khi có terminal operation. Nhưng:

~~~java
var pending = tasks.stream()
        .filter(task -> !task.done())
        .toList(); // Terminal operation: duyệt và tạo danh sách
~~~

`toList()` (Java 16+) thu thập các phần tử thành danh sách không thể sửa. Không gọi `pending.add(...)`; thao tác thay đổi cấu trúc sẽ ném `UnsupportedOperationException`. Nếu cần danh sách có thể sửa, có thể chọn `new ArrayList<>(pending)` và import `java.util.ArrayList`.

Tách một stream thành `var filteredStream = ...` thường chỉ tạo **tên cho pipeline**, trong khi tách qua `toList()` là **chuyển pipeline thành dữ liệu lưu trữ**. Hai cách phục vụ mục tiêu khác nhau về đọc mã, chi phí và khả năng dùng lại.

### 5.3. Không nhân đôi phép tính đắt đỏ khi tách

Trước:

~~~java
var formatted = format(calculate(load(requestId)));
~~~

Tách có ý nghĩa:

~~~java
var loaded = load(requestId);
var calculated = calculate(loaded);
var formatted = format(calculated);
~~~

Các lời gọi `load`, `calculate` và `format` vẫn xảy ra một lần theo thứ tự cũ. Đây là pseudocode, giả định ba phương thức có sẵn và các lời gọi không bị dời sang điều kiện khác.

Ngược lại, không tạo biến trung gian bằng cách gọi lại `load(requestId)` ở nhiều chỗ: kết quả có thể khác nếu dữ liệu thay đổi; đồng thời tốn tài nguyên hoặc phát sinh tác dụng phụ nhiều lần.

## 6. Tách biểu thức lồng nhau có kiểm tra `null`

### 6.1. Không biến lỗi thiếu dữ liệu thành NPE khó hiểu

Biểu thức trực tiếp sau không an toàn nếu map không có khóa:

~~~java
// Có thể ném NullPointerException khi key không tồn tại:
var count = tasksByTeam.get(team).stream().count();
~~~

Tách ra giúp nhìn rõ điểm cần kiểm tra:

~~~java
var tasks = tasksByTeam.get(team);
if (tasks == null) {
    throw new IllegalArgumentException("Unknown team: " + team);
}
var count = tasks.size();
~~~

Việc lựa chọn ném ngoại lệ hay dùng mặc định là quyết định nghiệp vụ. Với map có thể lưu khóa và giá trị `null`, `getOrDefault` không tự thay thế giá trị `null` nếu khóa thực sự tồn tại và được map tới `null`. Đừng coi mọi `Map.getOrDefault` là một phép kiểm tra null hoàn chỉnh.

### 6.2. Bảo toàn kiểm tra short-circuit

Ví dụ mã có bảo vệ null:

~~~java
if (user != null && user.active()) {
    process(user);
}
~~~

**Không** tách thành `var active = user.active();` trước điều kiện: nếu `user` là `null`, chương trình mới sẽ ném ngoại lệ ngay.

Có thể dùng biểu thức ngắn mạch giống cũ:

~~~java
var active = user != null && user.active();
if (active) {
    process(user);
}
~~~

Với code thực tế có khả năng `user` thay đổi giữa hai điểm đọc hoặc có cơ chế đồng thời, hãy xem xét đồng bộ và trạng thái ở thời điểm dùng. `var` không cung cấp cơ chế an toàn đa luồng.

### 6.3. Tách chuỗi `Optional` khi từng bước có ý nghĩa

Ví dụ mã sau là **đoạn minh họa trong một phương thức** khi đã có biến kiểu `Optional<Customer>` và các accessor `Customer::profile`, `Profile::city`:

~~~java
var profile = customerOptional.map(Customer::profile);
var city = profile.map(Profile::city).orElse("unknown");
~~~

Ý nghĩa: bước đầu lấy profile nếu có customer; bước tiếp theo lấy thành phố nếu profile tồn tại, sau đó cung cấp giá trị mặc định. Khai báo `var` giữ kiểu `Optional<Profile>` của `profile` và `String` của `city`.

Nếu hai bước này luôn đi cùng nhau và vẫn rõ ý, viết liền đôi khi ngắn gọn hơn:

~~~java
var city = customerOptional.map(Customer::profile)
        .map(Profile::city)
        .orElse("unknown");
~~~

Quan trọng là **không tự chuyển một chuỗi có khả năng thiếu dữ liệu thành nhiều phép truy cập trực tiếp có nguy cơ `NullPointerException`**.

## 7. `var` và việc giữ kiểu của biểu thức trung gian

### 7.1. Suy luận từ chữ ký phương thức

~~~java
var pending = tasks.stream()
        .filter(task -> !task.done())
        .toList(); // List<Task>

var titles = pending.stream()
        .map(Task::title)
        .toList(); // List<String>

var minutes = pending.stream()
        .mapToInt(Task::minutes)
        .sum(); // int
~~~

`var` xác định kiểu của **từng biến tại khai báo**, không điều chỉnh kiểu theo cách bạn sử dụng ở dòng sau. `minutes` là kiểu primitive `int`; `titles` là `List<String>`.

### 7.2. Cẩn trọng với diamond khi tách bước

~~~java
var names = new ArrayList<>();     // ArrayList<Object> khi không có kiểu đích
names.add("Lan");
~~~

Nếu mục tiêu là danh sách chuỗi, nên ghi:

~~~java
var names = new ArrayList<String>();  // ArrayList<String>
~~~

hoặc:

~~~java
List<String> names = new ArrayList<>();
~~~

Đoạn này cần import `java.util.ArrayList` và `java.util.List` khi đặt trong tệp. `var` không cung cấp kiểu đích cho diamond `<>` trống; các dòng `add("Lan")` về sau **không suy luận lại** type argument thành `String`.

### 7.3. `var` không làm kiểu trở thành dynamic

~~~java
var label = "backend"; // String
// label = 123;         // Sai compile-time: Integer không thể gán cho String
~~~

Biến trung gian không tự thay đổi kiểu vì biểu thức khác xuất hiện sau. Nếu bước tiếp theo cần chuyển đổi kiểu, tạo **biến mới có tên thích hợp** và biểu thức chuyển đổi rõ ràng.

### 7.4. Khi cần kiểu tường minh

~~~java
var result = service.execute(input);
~~~

Nếu người đọc không biết `execute` trả gì và kiểu kết quả quan trọng cho bước sau, tên `result` cùng `var` dễ gây mơ hồ. Có thể thay bằng:

~~~java
List<Invoice> approvedInvoices = service.execute(input);
~~~

Đây là pseudocode khi có `service` và kiểu `Invoice`; nêu ý tưởng rằng **tên và kiểu quan trọng hơn việc cố dùng `var` ở mọi nơi**. Trong API công khai, kiểu trả về của phương thức và field vẫn phải được khai báo rõ.

## 8. Tách bước để quan sát và kiểm thử

Đặt breakpoint tại `pending` hoặc `totalMinutes` giúp quan sát dữ liệu trung gian mà không cần đọc một chuỗi lệnh dài trong debugger. Trong môi trường production, khi log cần thiết, nên log giá trị tóm tắt, ví dụ số phần tử hoặc thời gian tính, thay vì ghi toàn bộ đối tượng có thể chứa dữ liệu nhạy cảm.

Bài kiểm thử có thể kiểm tra từng hành vi quan trọng: danh sách đã lọc chỉ còn công việc chưa hoàn tất; số công việc đúng; tổng phút đúng; nhóm không tồn tại có kết quả mặc định mong muốn. Nhưng không nên gắn test với tên `var` hay chi tiết biến cục bộ; điều cần bảo đảm là **hành vi chức năng**.

Một phép đối chiếu giữa biểu thức trước/sau phù hợp khi dữ liệu **không đổi**, phép tính **deterministic** và **không có side effect**. Nếu phương thức truy cập mạng, đọc đồng hồ, lấy sự kiện từ queue hoặc tạo id mới, gọi biểu thức hai lần không tương đương với việc dùng lại kết quả trung gian.

## 9. Các quy tắc giúp mã sau refactor vẫn dễ bảo trì

| Nên làm | Vì sao |
| --- | --- |
| Đặt tên biến theo ý nghĩa (`allTasks`, `pendingTasks`, `estimatedMinutes`) | Bước trung gian trở thành tài liệu cho dữ liệu |
| Tách tại ranh giới truy xuất/lọc/chuyển đổi/tổng hợp | Mỗi bước có trách nhiệm dễ kiểm tra |
| Dùng `var` nếu kiểu rõ ngay ở initializer | Tránh lặp generic dài nhưng vẫn giữ kiểu tĩnh |
| Viết kiểu tường minh khi initializer mơ hồ | Giảm nhu cầu đoán `service.execute(...)` trả gì |
| Giữ số lần gọi hàm có side effect | Tránh vô tình thay đổi hành vi |
| Kiểm tra null tại nơi truy xuất dữ liệu | Thất bại rõ vị trí và có chiến lược xử lý |
| Giữ short-circuit và thứ tự đánh giá | Tránh thay đổi điều kiện và ngoại lệ |
| Nhớ `Stream` chỉ chạy một terminal operation mỗi instance | Không dùng lại stream đã tiêu thụ |
| Phân biệt pipeline lazy với `toList()` | Tính đúng, chi phí bộ nhớ và mutability khác nhau |
| Không chia một biểu thức ngắn thành quá nhiều biến | Tránh tăng độ dài mã vô ích |

Lưu ý riêng với thứ tự đánh giá: Java đánh giá toán hạng theo quy tắc ngôn ngữ. Một phép refactor chỉ an toàn nếu nó bảo toàn thứ tự đó đối với những lời gọi có tác dụng phụ hoặc khả năng ném ngoại lệ. Đặc biệt với toán tử `&&`, `||`, `?:` và lời gọi có xử lý lỗi, không kéo các biểu thức có điều kiện ra thực thi vô điều kiện.

## 10. Ví dụ nên tách và không cần tách

**Nên tách** khi ba tầng nghiệp vụ bị giấu trong một lời gọi:

~~~java
var report = render(summarize(filterActive(loadItems(userId))));
~~~

Nếu các phương thức trên đã được định nghĩa, có thể viết (pseudocode):

~~~java
var items = loadItems(userId);
var activeItems = filterActive(items);
var summary = summarize(activeItems);
var report = render(summary);
~~~

Mỗi biến đại diện cho một trạng thái có ý nghĩa và có thể kiểm tra.

**Không cần tách chỉ vì muốn dùng nhiều `var`:**

~~~java
var length = name.trim().length();
~~~

Viết thành `var trimmed = name.trim(); var length = trimmed.length();` chỉ tốt hơn nếu `trimmed` được dùng lại, cần kiểm tra riêng hoặc thật sự làm rõ mục tiêu. Mã ngắn và rõ có thể giữ nguyên.

**Khi biểu thức có điều kiện:**

~~~java
var label = isAdmin ? "Admin" : "Member";
~~~

Đây là ternary dễ hiểu; tách `isAdmin` hoặc từng nhánh thành biến trung gian không tạo giá trị rõ ràng. Nếu các nhánh là lời gọi đắt đỏ, đừng tính trước cả hai nhánh vì `?:` chỉ đánh giá nhánh được chọn.

## 11. Bài tập tự kiểm tra

### Câu 1 — Chia đúng ranh giới

Cho biểu thức:

~~~java
var total = tasksByTeam.getOrDefault("backend", List.of())
        .stream().filter(task -> !task.done())
        .mapToInt(Task::minutes).sum();
~~~

Tách thành ba bước có tên ý nghĩa, vẫn dùng `var`.

**Gợi ý đáp án:**

~~~java
var allTasks = tasksByTeam.getOrDefault("backend", List.of());
var pendingTasks = allTasks.stream()
        .filter(task -> !task.done())
        .toList();
var total = pendingTasks.stream().mapToInt(Task::minutes).sum();
~~~

Kiểm tra lại số lượng và giá trị đầu ra; lưu ý `toList()` tạo thêm danh sách, nên có thể chọn pipeline chỉ dùng một lần nếu cần tối ưu.

### Câu 2 — Tìm lỗi stream

~~~java
var filtered = tasks.stream().filter(task -> !task.done());
var count = filtered.count();
var names = filtered.map(Task::title).toList();
~~~

**Đáp án:** `filtered` đã bị tiêu thụ bởi `count()`; gọi terminal operation khác trên cùng stream sẽ ném `IllegalStateException`. Có thể materialize thành `var pending = ...toList();` rồi tạo stream mới cho từng phép xử lý.

### Câu 3 — Kiểu suy luận

~~~java
var pending = tasks.stream().filter(task -> !task.done()).toList();
var titles = pending.stream().map(Task::title).toList();
var total = pending.stream().mapToInt(Task::minutes).sum();
~~~

**Đáp án:** `pending` là `List<Task>`, `titles` là `List<String>`, `total` là `int`.

### Câu 4 — Refactor nào sai?

~~~java
if (user != null && user.active()) {
    process(user);
}
~~~

Có người đổi thành:

~~~java
var active = user.active();
if (user != null && active) {
    process(user);
}
~~~

**Đáp án:** Không an toàn. `user.active()` được gọi trước kiểm tra `user != null`, nên có thể ném `NullPointerException`. Giữ toán tử short-circuit bằng `var active = user != null && user.active();` hoặc điều kiện gốc.

### Câu 5 — Thao tác với danh sách trung gian

~~~java
var pending = tasks.stream().filter(task -> !task.done()).toList();
pending.add(new Task("Extra", 5, false));
~~~

**Đáp án:** Mã có thể biên dịch nếu `Task` phù hợp, nhưng `toList()` trả danh sách không thể sửa nên `add` sẽ ném `UnsupportedOperationException`. Nếu cần chỉnh sửa, tạo danh sách mutable có chủ đích như `new ArrayList<>(pending)`.

### Câu 6 — Khi nào không nên dùng `var`?

~~~java
var response = client.fetch(input);
~~~

**Đáp án:** Nếu chữ ký `fetch` khó xác định và kiểu phản hồi quan trọng cho việc đọc code, dùng một tên có nghĩa và/hoặc kiểu tường minh. `var` hợp lý nhất khi kiểu và ý nghĩa được biểu thức khởi tạo thể hiện rõ; không bắt buộc dùng ở mọi biến cục bộ.

## 12. Tài liệu chính thức còn phù hợp

- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): mục tiêu đưa `var` vào Java 10 và giới hạn suy luận kiểu biến cục bộ.
- [dev.java — Using the Var Type Identifier](https://dev.java/learn/language-basics/using-var/): hướng dẫn cách dùng `var` có ý nghĩa trong Java hiện đại.
- [Java Language Specification, `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): vị trí và ngữ nghĩa khai báo local variable.
- [Java SE API — `Map.getOrDefault`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#getOrDefault(java.lang.Object,V)): hành vi tra cứu và giá trị mặc định.
- [Java SE API — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): pipeline, intermediate/terminal operation, một stream một lượt sử dụng và `toList()`.
- [Java SE API — `List`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): hành vi danh sách và các factory.
- [Java Language Specification, `15.7 — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.7): thứ tự đánh giá cần được bảo toàn khi refactor.

**Ghi nhớ:** Hãy tách biểu thức lồng nhau tại các **điểm chuyển đổi có ý nghĩa**, đặt tên mô tả dữ liệu rồi dùng `var` khi kiểu đã rõ từ vế phải. Với stream, null, điều kiện ngắn mạch và tác dụng phụ, hãy kiểm tra cả **ngữ nghĩa, thứ tự thực thi và chi phí** để phiên bản dễ đọc hơn vẫn chạy đúng.