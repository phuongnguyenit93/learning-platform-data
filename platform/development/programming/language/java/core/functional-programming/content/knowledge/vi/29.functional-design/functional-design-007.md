# Không thay mọi vòng lặp bằng Stream khi luồng điều khiển cần rõ ràng

## Mục tiêu

Java Stream API khuyến khích cách viết **khai báo điều muốn tính** thay vì mô tả từng bước duyệt dữ liệu. Ví dụ, `filter`, `map` và `collect` rất phù hợp với việc lọc, biến đổi rồi thu kết quả. Nhưng **không phải vòng lặp nào cũng nên đổi thành Stream**. Khi thuật toán có nhiều nhánh điều khiển, cần `break`, `continue`, `return`, xử lý ngoại lệ theo từng phần tử, cập nhật một máy trạng thái hoặc quản lý tài nguyên chặt chẽ, vòng lặp `for`/`while` có thể diễn đạt chủ ý chính xác và dễ kiểm thử hơn.

Điểm cốt lõi của bài là **chọn công cụ làm rõ ý nghĩa**, không đánh giá code theo số lượng dòng hoặc sự “hiện đại” của cú pháp. Một Stream có side effect phức tạp và state chia sẻ không tự nhiên trở thành thiết kế hàm tốt; một vòng lặp rõ ràng với biến cục bộ cũng không tự nhiên là thiết kế kém.

Sau bài này, bạn sẽ:

- Phân biệt thao tác khai báo trên dữ liệu với điều phối luồng điều khiển.
- Biết khi `filter/map/flatMap/collect` và các terminal operation của Stream giúp code sáng hơn.
- So sánh `break/continue/return` với `takeWhile/filter/findFirst/anyMatch`, hiểu sự khác nhau về hợp đồng.
- Nhận diện trường hợp xử lý lỗi, retry, nested loop, transaction hoặc finite-state machine nên ưu tiên cấu trúc điều khiển trực tiếp.
- Tránh cách dùng `forEach` như một phiên bản khó đọc hơn của `for`.
- Kiểm tra tính lazy, short-circuit, encounter order, xử lý song song, tác dụng phụ và tài nguyên.
- Chạy chương trình Java 17 có cả cách viết Stream và vòng lặp, với stdout đã kiểm chứng.

## 1. Stream và vòng lặp giải quyết những kiểu bài toán khác nhau

### 1.1. Vòng lặp: mô tả quá trình điều phối

Vòng lặp thường diễn đạt một quy trình: kiểm tra điều kiện, bỏ qua một bước, dừng cả quá trình, chuyển trạng thái hoặc thoát phương thức.

```java
int total = 0;

for (int value : values) {
    if (value < 0) break;
    if (value == 0) continue;
    total += value;
}
```

Đây là **đoạn minh họa**, cần khai báo `values` là tập các số phù hợp. Ý nghĩa rất trực tiếp:

1. Dừng khi gặp số âm đầu tiên.
2. Bỏ qua số 0.
3. Cộng các giá trị dương đã gặp trước điểm dừng.

`break` dừng **vòng lặp hiện tại**, `continue` bỏ phần còn lại của lượt hiện tại, và `return` có thể trả kết quả rồi thoát **phương thức bao quanh**. Ba công cụ này rất hữu ích khi thuật toán được mô tả như một chuỗi quyết định có thứ tự.

### 1.2. Stream: mô tả chuỗi biến đổi

Với tập dữ liệu đã có và mục tiêu rõ ràng, Stream cho phép mô tả các bước:

```java
int total = values.stream()
        .filter(value -> value > 0)
        .mapToInt(Integer::intValue)
        .sum();
```

Đoạn này chỉ tính **tổng mọi giá trị dương trong toàn bộ nguồn**; nó **không tương đương** vòng lặp ở trên nếu nguồn có một số âm báo dừng rồi các số dương phía sau. Đây là lỗi rất dễ gặp khi “dịch cú pháp” mà chưa xác định hợp đồng thuật toán.

Nếu yêu cầu thật sự là dừng ở số âm đầu tiên trên nguồn có encounter order, Java 9+ có `takeWhile`:

```java
int total = values.stream()
        .takeWhile(value -> value >= 0)
        .filter(value -> value != 0)
        .mapToInt(Integer::intValue)
        .sum();
```

Với nguồn `[4,0,8,-1,16,32]`, cả vòng lặp và pipeline `takeWhile` đều cho **12**. Nhưng việc dùng Stream chỉ nên được chọn nếu các bước khai báo này vẫn giúp người đọc hiểu quy tắc dừng ngay lập tức.

**Quan trọng:** với nguồn **unordered**, `takeWhile` có ngữ nghĩa khác khi điều kiện ban đầu không có thứ tự rõ: nó không nhất thiết biểu diễn “mọi phần tử trước dấu dừng” theo một thứ tự nghiệp vụ. Khi cần nghĩa “trước mốc đầu tiên”, cần nguồn có encounter order hoặc một cách điều phối rõ ràng.

## 2. Đừng đổi từng câu lệnh trong for thành một lời gọi Stream

Một sai lầm phổ biến là nhìn thấy:

```java
for (Item item : items) {
    if (!item.isActive()) continue;
    send(item);
}
```

rồi lập tức thay bằng:

```java
items.stream()
        .filter(Item::isActive)
        .forEach(this::send);
```

Hai đoạn chỉ là **minh họa**: `Item` và `send` cần do ứng dụng định nghĩa. Pipeline có thể đọc tốt nếu `send` là thao tác độc lập, mỗi phần tử không ảnh hưởng tới phần tử khác, không cần thoát sớm, và chính sách lỗi của hành động bên ngoài đã rõ. Nhưng nếu `send` gọi API mạng, cần retry, rollback, dừng sau lỗi, kiểm soát thứ tự và lưu checkpoint, thì `for` thường cho phép thể hiện những bước đó một cách trực tiếp hơn.

Không có quy tắc “thấy for là thay bằng stream”. Hãy tự hỏi:

- Đây là **biến đổi dữ liệu** hay **điều phối quy trình**?
- Có cần dừng, bỏ qua, thử lại hoặc trả về từ phương thức ngay không?
- Có trạng thái thay đổi tùy phần tử trước đó không?
- Mọi callback có thể độc lập và không có side effect không?
- Kết quả cần là collection, thống kê hay tác vụ bắt buộc với hệ thống bên ngoài?

Câu trả lời quyết định lựa chọn.

## 3. break: dừng vòng lặp không giống filter

`filter(predicate)` quyết định **phần tử nào được giữ**, không có nghĩa “gặp phần tử sai điều kiện thì ngừng toàn bộ pipeline”. Với nguồn:

```java
List<Integer> values = List.of(4, 0, 8, -1, 16, 32);
```

Vòng lặp dừng tại `-1` cho tổng `12`; trong khi:

```java
int different = values.stream()
        .filter(n -> n >= 0)
        .mapToInt(Integer::intValue)
        .sum(); // 60
```

Giá trị `60` được tính từ `4+0+8+16+32`. Đây là **bài toán khác** vì `filter` bỏ số âm nhưng vẫn tiếp tục qua phần tử phía sau.

Với nguồn có thứ tự, `takeWhile(n -> n >= 0)` lấy tiền tố liên tiếp trong lúc predicate đúng rồi ngừng tại phần tử đầu tiên không thỏa. Do đó:

```java
int correct = values.stream()
        .takeWhile(n -> n >= 0)
        .mapToInt(Integer::intValue)
        .sum(); // 12
```

Ở ví dụ này, `filter(n -> n != 0)` không cần thiết để tính tổng vì cộng 0 không đổi giá trị; thêm filter chỉ khi muốn diễn tả rõ “bỏ qua những lần đo bằng 0” hoặc các bước sau cần loại chúng.

### Khi dùng takeWhile chưa chắc đơn giản hơn

Nếu dấu dừng phụ thuộc vào một trạng thái thay đổi qua nhiều bước, ví dụ “dừng khi đã gặp BEGIN rồi ACK rồi lỗi trong khoảng 30 giây”, viết một predicate đóng trên state mutable để ép `takeWhile` có thể làm code khó hiểu, khó kiểm thử, và không phù hợp với stream song song. Một vòng lặp với biến trạng thái, điều kiện `break` và comment mô tả bất biến thường tốt hơn.

Đừng dùng `filter`, `peek` hay `map` chỉ như một cách giấu `break` trong side effect hoặc exception.

## 4. continue: khi nào filter là tương đương?

Nếu hành vi duy nhất là **bỏ qua phần tử không cần xử lý** và các phần tử còn lại được xử lý độc lập, `continue` có thể được diễn đạt bằng `filter`:

```java
for (String name : names) {
    if (name.isBlank()) continue;
    result.add(name.strip());
}
```

Một pipeline tương ứng về dữ liệu, khi `names` có các String khác null:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::strip)
        .toList();
```

Hai đoạn chỉ là **hai phương án minh họa** với biến `names`, `result` được khai báo trong ngữ cảnh riêng. Pipeline làm rõ chức năng: loại tên blank → loại khoảng trắng → tạo List. Đây là trường hợp Stream thường thắng về khả năng đọc.

Nhưng phải so sánh đúng thứ tự thao tác. Nếu yêu cầu coi `"   "` là blank, có thể chuẩn hóa trước rồi lọc:

```java
List<String> result = names.stream()
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .toList();
```

Nếu nguồn chứa `null`, `String::strip` và `isBlank` có thể gây `NullPointerException`. Phải quyết định có lọc, báo lỗi hay thay giá trị; đừng coi chuyển sang Stream là cơ chế tự xử lý null.

### continue không tương đương return trong lambda

Không thể đặt `continue` trong thân lambda rồi mong tiếp tục vòng lặp ngoài:

```java
// Không biên dịch: continue không có vòng lặp thích hợp ở đây.
items.forEach(item -> {
    if (skip(item)) continue;
});
```

Một `return;` trong lambda kiểu `Consumer<T>` chỉ kết thúc **lần gọi lambda hiện tại**, không thoát khỏi phương thức bao quanh hay làm `forEach` ngừng duyệt. Việc cố mô phỏng `continue` bằng `return` trong lambda có thể gây hiểu nhầm mạnh nếu code còn nhiều nhánh.

## 5. return: thoát phương thức với vòng lặp, trả Optional với Stream

Tình huống thường gặp là duyệt theo thứ tự để tìm tác vụ đầu tiên đủ điều kiện. Vòng lặp:

```java
static Optional<String> firstReadyLoop(List<Task> tasks) {
    for (Task task : tasks) {
        if (task.cancelled()) continue;
        if (task.priority() >= 8) return Optional.of(task.id());
    }
    return Optional.empty();
}
```

Đoạn này sử dụng record `Task` được định nghĩa đầy đủ trong chương trình chính.

Bản Stream tương đương khi nguồn có encounter order:

```java
static Optional<String> firstReadyStream(List<Task> tasks) {
    return tasks.stream()
            .filter(task -> !task.cancelled())
            .filter(task -> task.priority() >= 8)
            .map(Task::id)
            .findFirst();
}
```

Ở đây Stream khá rõ vì **chỉ lựa chọn một phần tử**, không có state phức tạp. `findFirst` là short-circuit terminal operation: trên ordered stream, nó trả bản ghi đầu tiên thỏa điều kiện. Nếu không có tác vụ phù hợp, trả `Optional.empty()`.

Cần lưu ý:

- `findAny` **không tương đương** `findFirst` nếu thứ tự ưu tiên là quan trọng.
- `findFirst` không tự thay thế một vòng lặp có nhiều lệnh ghi trạng thái và rollback trước khi trả về.
- Nếu `Task.id()` trả `null`, pipeline `map(Task::id).findFirst()` có thể ném NPE do Optional không thể chứa null. Cần hợp đồng dữ liệu rõ.
- Không gọi `stream().forEach(...)` rồi mong một `return` trong callback sẽ thoát phương thức.

## 6. Những luồng điều khiển có lợi từ vòng lặp

### 6.1. Xử lý dữ liệu lỗi theo từng dòng rồi tiếp tục

Giả sử ứng dụng nhận dữ liệu chuỗi theo thứ tự. Nó cần:

1. Gặp `STOP` thì dừng đọc.
2. Bỏ qua dòng trống.
3. Parse dòng số nguyên và cộng vào tổng.
4. Dòng không parse được được đưa vào danh sách lỗi với số dòng, nhưng **không dừng toàn bộ batch**.

Vòng lặp diễn đạt trực tiếp:

```java
int sum = 0;
boolean stopped = false;
List<String> errors = new ArrayList<>();

for (int i = 0; i < raw.size(); i++) {
    String value = raw.get(i).strip();

    if (value.equals("STOP")) {
        stopped = true;
        break;
    }
    if (value.isEmpty()) continue;

    try {
        sum += Integer.parseInt(value);
    } catch (NumberFormatException e) {
        errors.add("Line " + (i + 1) + ": " + value);
    }
}
```

Đoạn minh họa giả định `raw` là `List<String>` không chứa null; code hoàn chỉnh nằm ở mục chương trình. Vòng lặp cho thấy rõ: điểm dừng, số dòng, vùng bắt lỗi và chính sách tiếp tục sau lỗi.

Có thể thiết kế Stream tạo các `ParseResult` thành công/thất bại rồi `collect` cả hai loại; điều này cũng có thể đúng. Nhưng nếu để giữ một Stream ngắn mà phải capture biến `sum` và `errors` mutable, dùng `AtomicInteger` cho tổng, ném exception từ `map` để mô phỏng break và tra chỉ số bằng state bên ngoài, đó thường là **cải thiện cú pháp giả tạo**.

### 6.2. Quy trình có trạng thái

Một danh sách command:

```text
BEGIN
ADD 3
ADD 2
ROLLBACK
BEGIN
ADD 7
COMMIT
```

cần máy trạng thái:

- `BEGIN` mở giao dịch mới.
- `ADD n` tăng giá trị chưa commit.
- `ROLLBACK` hủy giá trị chưa commit.
- `COMMIT` chốt giá trị vào tổng.
- Mọi lệnh sai trạng thái phải bị từ chối.

Với loại logic này, `for` kết hợp `switch` và biến `active/pending/committed` diễn đạt **thứ tự chuyển trạng thái** minh bạch. Việc chuyển thành `map` với mutable state ẩn trong lambda không làm quy tắc chính xác hơn, và `parallelStream` có thể phá phụ thuộc thứ tự lệnh.

### 6.3. Nested loop và thoát nhiều cấp

Một thuật toán tìm cặp đầu tiên thỏa điều kiện trong hai tập:

```java
outer:
for (String left : lefts) {
    for (String right : rights) {
        if (matches(left, right)) {
            chosen = left + ":" + right;
            break outer;
        }
    }
}
```

Đây là đoạn **minh họa**, cần khai báo `lefts`, `rights`, `chosen` và `matches`. Label `outer` giúp thoát cả hai vòng khi đã tìm thấy một cặp. Dùng `flatMap` rồi `findFirst` có thể phù hợp nếu cặp được biểu diễn như giá trị thuần, nhưng nếu các vòng còn thay đổi trạng thái theo từng lần thử, có các điều kiện dừng khác nhau hoặc cần giải phóng tài nguyên tại điểm dừng, một vòng lặp dễ đọc hơn.

### 6.4. Retry, backoff và cleanup

Một lệnh xử lý API mạng có thể phải:

- Thử tối đa N lần.
- Dừng ngay khi thành công.
- Bắt các lỗi được phép thử lại.
- Ghi số lần thử và kết quả.
- Đóng tài nguyên trong `finally` hoặc `try-with-resources`.
- Dừng hẳn khi lỗi không thể phục hồi.

Đây là **điều phối quy trình**, không phải pipeline biến đổi phần tử độc lập. `for` hoặc `while` với `try/catch` rõ chính sách thường dễ đánh giá và debug. Stream không tự mang lại retry, transaction hoặc resource cleanup.

## 7. Chương trình Java 17 đầy đủ

Chương trình sau bao gồm cả các trường hợp **có thể thay vòng lặp bằng Stream rõ ràng** và các trường hợp **nên giữ vòng lặp**.

Tạo file **`LoopVsStreamDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class LoopVsStreamDemo {
    record Task(String id, int priority, boolean cancelled) {}
    record ParseResult(int total, List<String> errors, boolean stopped) {}

    static int sumBeforeStopLoop(List<Integer> values) {
        int sum = 0;
        for (int value : values) {
            if (value < 0) break;
            if (value == 0) continue;
            sum += value;
        }
        return sum;
    }

    static int sumBeforeStopStream(List<Integer> values) {
        return values.stream()
                .takeWhile(value -> value >= 0)
                .filter(value -> value != 0)
                .mapToInt(Integer::intValue)
                .sum();
    }

    static Optional<String> firstReadyLoop(List<Task> tasks) {
        for (Task task : tasks) {
            if (task.cancelled()) continue;
            if (task.priority() >= 8) return Optional.of(task.id());
        }
        return Optional.empty();
    }

    static Optional<String> firstReadyStream(List<Task> tasks) {
        return tasks.stream()
                .filter(task -> !task.cancelled())
                .filter(task -> task.priority() >= 8)
                .map(Task::id)
                .findFirst();
    }

    static ParseResult parseUntilStop(List<String> raw) {
        int sum = 0;
        boolean stopped = false;
        List<String> errors = new ArrayList<>();
        for (int i = 0; i < raw.size(); i++) {
            String value = raw.get(i).strip();
            if (value.equals("STOP")) {
                stopped = true;
                break;
            }
            if (value.isEmpty()) continue;
            try {
                sum += Integer.parseInt(value);
            } catch (NumberFormatException e) {
                errors.add("Line " + (i + 1) + ": " + value);
            }
        }
        return new ParseResult(sum, List.copyOf(errors), stopped);
    }

    static int applyTransactions(List<String> commands) {
        boolean active = false;
        int pending = 0;
        int committed = 0;

        for (String command : commands) {
            switch (command) {
                case "BEGIN" -> {
                    if (active)
                        throw new IllegalStateException("Already active");
                    active = true;
                    pending = 0;
                }
                case "COMMIT" -> {
                    if (!active)
                        throw new IllegalStateException("No transaction");
                    committed += pending;
                    pending = 0;
                    active = false;
                }
                case "ROLLBACK" -> {
                    if (!active)
                        throw new IllegalStateException("No transaction");
                    pending = 0;
                    active = false;
                }
                default -> {
                    if (!active || !command.startsWith("ADD "))
                        throw new IllegalArgumentException("Invalid command");
                    pending += Integer.parseInt(command.substring(4));
                }
            }
        }
        if (active)
            throw new IllegalStateException("Unclosed transaction");
        return committed;
    }

    public static void main(String[] args) {
        List<Integer> readings = List.of(4, 0, 8, -1, 16, 32);
        System.out.println("Loop sum: "
                + sumBeforeStopLoop(readings));
        System.out.println("Stream sum: "
                + sumBeforeStopStream(readings));

        List<Task> tasks = List.of(
                new Task("A", 7, true),
                new Task("B", 4, false),
                new Task("C", 9, false),
                new Task("D", 10, false)
        );
        System.out.println("First ready loop: "
                + firstReadyLoop(tasks));
        System.out.println("First ready stream: "
                + firstReadyStream(tasks));

        ParseResult parsed = parseUntilStop(
                List.of("10", " ", "oops", "20", "STOP", "30"));
        System.out.println("Parsed total: " + parsed.total());
        System.out.println("Errors: " + parsed.errors());
        System.out.println("Stopped: " + parsed.stopped());

        int committed = applyTransactions(List.of(
                "BEGIN", "ADD 3", "ADD 2", "ROLLBACK",
                "BEGIN", "ADD 7", "COMMIT"));
        System.out.println("Committed: " + committed);
    }
}
```

Biên dịch và chạy:

```bash
javac LoopVsStreamDemo.java
java LoopVsStreamDemo
```

**Stdout chính xác** với Java 17:

```text
Loop sum: 12
Stream sum: 12
First ready loop: Optional[C]
First ready stream: Optional[C]
Parsed total: 30
Errors: [Line 3: oops]
Stopped: true
Committed: 7
```

### 7.1. Giải thích đầu ra

**Loop sum và Stream sum đều bằng 12.** Nguồn `[4,0,8,-1,16,32]` có marker `-1`. Vòng lặp dùng `break`; Stream dùng `takeWhile(value >= 0)`. Các số 16 và 32 **không được cộng**, khác với phương án `filter(n >= 0)` đã chỉ ra trước đó.

**First ready đều là Optional[C].** Tác vụ A đã cancelled, B có priority 4 dưới ngưỡng 8, C có priority 9 và chưa cancelled. C là tác vụ hợp lệ đầu tiên theo encounter order nên cả hai phương án chọn cùng ID. Tác vụ D cũng đủ điều kiện nhưng xuất hiện sau C.

**Parsed total bằng 30.** Dòng 1 là 10; dòng 2 blank bị bỏ qua; dòng 3 `oops` không phải số nên đưa vào `errors`; dòng 4 là 20; dòng 5 là `STOP` khiến vòng lặp dừng; dòng 6 là 30 nhưng không được xử lý. Kết quả ghi đúng số dòng `Line 3` và cờ `stopped=true`.

**Committed bằng 7.** Giao dịch đầu cộng 3+2 vào `pending` nhưng `ROLLBACK` hủy nó. Giao dịch sau thêm 7 rồi `COMMIT`, nên kết quả cuối là 7. Đây là ví dụ mà vòng lặp và `switch` giữ logic trạng thái rõ hơn một pipeline Stream chứa biến mutable.

Ví dụ cố định, không cần thư viện ngoài Java 17, không phụ thuộc mạng hay thread. Các đoạn code minh họa ở phần trước không nhất thiết đứng độc lập; **chương trình này là chương trình đầy đủ** đã biên dịch và chạy kiểm chứng.

## 8. Khi nào Stream thực sự làm thiết kế tốt hơn?

Stream thường rất phù hợp với các phép biến đổi có **đầu vào và đầu ra rõ**, ít phụ thuộc trạng thái bên ngoài:

```java
List<String> emails = users.stream()
        .filter(User::active)
        .map(User::email)
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(email -> !email.isEmpty())
        .distinct()
        .toList();
```

Đây là đoạn minh họa: cần `users`, kiểu `User` và import `Objects`. Ý nghĩa là chọn user active, lấy email, lọc thiếu, chuẩn hóa, bỏ trùng và thu danh sách. Các bước là **biến đổi dữ liệu** và đọc như một mô tả nghiệp vụ.

Các trường hợp phù hợp khác:

- `mapToInt(...).sum()` tính tổng thuộc tính số.
- `groupingBy(...)` nhóm theo khóa ổn định.
- `anyMatch(...)` hỏi có phần tử thỏa predicate hay không.
- `allMatch(...)` kiểm tra toàn bộ phần tử thỏa điều kiện.
- `findFirst()` chọn phần tử đầu trên nguồn ordered.
- `flatMap(...)` biến một phần tử thành nhiều phần tử rồi làm phẳng, khi kết quả có mô hình rõ.
- `Collectors.toMap(...)` hoặc `groupingBy(...)` tạo cấu trúc kết quả theo khóa.

Stream khiến code tốt hơn khi pipeline giải thích được bằng một câu **“lấy dữ liệu → lọc → biến đổi → thu kết quả”**. Nếu để đọc hiểu một pipeline phải lần theo 4 biến mutable bên ngoài và 3 nhánh exception trong lambda, vòng lặp có thể là lựa chọn dễ bảo trì hơn.

### Stream không buộc toàn bộ ứng dụng phải thuần hàm

Java là ngôn ngữ hỗ trợ nhiều phong cách. Có thể dùng vòng lặp ở tầng **điều phối** và dùng Stream bên trong những phép biến đổi dữ liệu độc lập. Đây thường là cách phối hợp hợp lý:

```java
for (Batch batch : batches) {
    if (batch.cancelled()) break;

    long amount = batch.items().stream()
            .filter(Item::valid)
            .mapToLong(Item::amount)
            .sum();

    persistBatchTotal(batch.id(), amount);
}
```

Đoạn này minh họa, cần khai báo `Batch`, `Item`, `batches` và `persistBatchTotal`. Vòng lặp thể hiện quy tắc dừng và ghi một batch; Stream mô tả một phép tổng độc lập bên trong batch. Chỉ dùng nếu contract của `persistBatchTotal` và việc xử lý lỗi đã được thiết kế.

## 9. Chú ý lazy evaluation, short-circuit và side effect

Các thao tác trung gian như `map` và `filter` thường **lazy**: chúng xây pipeline, chưa thực thi mapper cho từng phần tử cho tới khi terminal operation cần dữ liệu.

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> n * 2);
List<Integer> result = pipeline.toList(); // [2, 4, 6]
```

Một Stream chỉ dùng cho một terminal operation; sau `toList` không gọi `count` lần nữa trên cùng object Stream.

### Không cho rằng callback chạy đúng một lần với mọi phần tử

`findFirst`, `findAny`, `anyMatch` và `takeWhile` có thể **short-circuit**. Nếu đưa audit nghiệp vụ bắt buộc vào `map` hoặc `peek`, những phần tử không cần cho kết quả có thể không được xử lý. Một số terminal operation còn có thể tối ưu hóa pipeline khiến mapper không cần chạy như bạn kỳ vọng.

Ví dụ:

```java
boolean found = Stream.of(1, 2, 3, 4)
        .anyMatch(n -> n == 1); // true
```

Không cần gọi predicate với mọi phần tử để biết kết quả. Do đó, nếu mục tiêu là “kiểm tra dữ liệu và ghi log mọi dòng”, một pipeline short-circuit không thể thay thế quy trình bắt buộc xử lý đủ mọi dòng.

### Parallel và biến mutable

Đừng chuyển Stream thành `parallelStream()` khi callback còn cập nhật biến mutable không đồng bộ:

```java
int[] total = {0};
values.parallelStream().forEach(n -> total[0] += n);
```

Đoạn này minh họa một **data race** có thể làm mất cập nhật; không dùng làm cách tính tổng. Thay bằng `mapToInt(...).sum()` khi phép cộng phù hợp hoặc một Collector được thiết kế đúng. Với quy trình phụ thuộc thứ tự từng bước, song song hóa tùy tiện có thể sai dù không xuất hiện exception.

## 10. Ngoại lệ và tài nguyên: ưu tiên ranh giới rõ ràng

### Checked exception trong lambda

Các functional interface thông dụng như `Function.apply`, `Predicate.test` và `Consumer.accept` không khai báo checked exception. Nếu mỗi phần tử cần gọi API ném `IOException`, không thể chỉ viết lambda ném checked exception ra ngoài mà không xử lý.

Vòng lặp có thể diễn đạt rõ `try/catch` theo mỗi phần tử và quyết định tiếp tục hay dừng. Cũng có thể chuyển kết quả lỗi thành object có kiểu và xử lý bằng Stream; lựa chọn tùy mức độ phức tạp, không có luật bắt buộc phải dùng Stream.

### Quản lý tài nguyên

`Stream` từ `Files.lines(path)` có thể giữ file mở. Terminal operation `collect` hoặc `forEach` **không tự đóng** Stream. Dùng `try-with-resources` ở ranh giới sở hữu:

```java
// Minh họa: cần Path path và xử lý IOException ở phương thức bao quanh.
try (Stream<String> lines = Files.lines(path)) {
    lines.filter(s -> !s.isBlank())
         .forEach(System.out::println);
}
```

Nếu cần giữ số dòng và ghi lỗi parse theo từng dòng, vòng lặp đọc từ `BufferedReader` với `try-with-resources` có thể diễn đạt rõ việc đọc từng dòng, dừng sớm, ghi số dòng và dọn tài nguyên. Đừng ép `Files.lines(...).forEach(...)` thành một vòng lặp trá hình kèm nhiều biến captured.

### Lỗi và rollback

Một pipeline không tự tạo transaction. Nếu action đã gửi request hoặc ghi database rồi một callback khác ném exception, những side effect trước đó không tự được undo. Vòng lặp rõ ràng làm vị trí `try`, `catch`, `finally` và ranh giới commit/rollback dễ nhìn hơn; nhưng chính ứng dụng vẫn phải cung cấp cơ chế transaction và chính sách lỗi thực sự.

## 11. Hiệu năng: đo thay vì đoán

Không có bảo đảm rằng vòng lặp luôn nhanh hơn Stream, hoặc Stream luôn tối ưu hơn for. Khác biệt hiệu năng phụ thuộc:

- Kích thước dữ liệu, độ phức tạp của mapper, filter và điều kiện dừng.
- Cấu trúc nguồn, tính liên tục bộ nhớ, boxing/unboxing và loại Stream primitive.
- JIT, tối ưu hóa JVM, chi phí allocation và khả năng inlining.
- Khả năng phân chia nguồn và chi phí phối hợp trong parallel pipeline.
- I/O, network hoặc database, vốn có thể lớn hơn rất nhiều so với overhead của chính vòng lặp.

Ví dụ tính tổng `int` có thể dùng `IntStream` để hạn chế boxing:

```java
int total = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Nhưng nếu xử lý chỉ vài phần tử và có state machine, tối ưu từng phép gọi Stream không giúp code dễ đọc hơn. Khi hiệu năng là yêu cầu, đo bằng benchmark phù hợp (ví dụ JMH cho microbenchmark), không suy luận từ độ dài cú pháp hoặc một lần chạy đo bằng `System.nanoTime` mà không có warm-up.

## 12. Bảng quyết định khi review code

| Câu hỏi | Stream thường phù hợp | Vòng lặp thường rõ hơn |
| --- | --- | --- |
| Có pipeline lọc/biến đổi/thu kết quả thuần? | Có | Không bắt buộc |
| Chỉ cần count, sum, grouping, matching? | Có | Có thể nhưng dài hơn |
| Cần dừng ở tiền tố có predicate đơn giản? | `takeWhile` trên ordered source | `break` nếu quy tắc dừng phức tạp |
| Cần bỏ qua một số bản ghi độc lập? | `filter` | `continue` khi còn nhánh xử lý |
| Cần trả phần tử đầu thỏa điều kiện? | `findFirst` | `return` khi có xử lý phụ |
| Cần retry, rollback, nhiều loại lỗi theo từng lượt? | Có thể nhưng dễ rối | Thường có |
| Cần máy trạng thái phụ thuộc thứ tự command? | Thường không | Có |
| Cần nested loop với thoát nhiều cấp? | `flatMap/findFirst` nếu thuần | Thường có nếu control flow phức tạp |
| Cần thay đổi biến mutable chia sẻ? | Không nên dùng side effect | Dùng biến cục bộ, kiểm soát phạm vi |
| Cần gọi dịch vụ ngoài từng phần tử? | Chỉ khi error semantics rõ | Thường dễ điều phối |
| Muốn chạy song song? | Chỉ khi callback/state phù hợp | Không đổi thuật toán phụ thuộc thứ tự thành parallel |
| Muốn giảm dòng code bằng mọi giá? | Không phải tiêu chí | Không phải tiêu chí |

**Quy tắc thực tế:** nếu tên các bước Stream kể rõ công việc và các callback có ý nghĩa độc lập, Stream thường dễ đọc. Nếu người đọc phải mô phỏng state và exception xuyên qua nhiều lambda để hiểu kết quả, hãy cân nhắc vòng lặp hoặc tách thuật toán thành các phương thức nhỏ.

## 13. Lỗi phổ biến

1. **Đổi `break` thành `filter`:** filter không dừng, khiến dữ liệu sau mốc dừng vẫn được xử lý.
2. **Giả định `continue` dùng được trong lambda:** `continue` không hợp lệ nếu không có vòng lặp thích hợp.
3. **Tưởng `return` trong lambda thoát phương thức bên ngoài:** nó chỉ trả về từ lambda.
4. **Dùng `forEach` để xây danh sách bằng ArrayList chia sẻ:** đặc biệt nguy hiểm với parallel.
5. **Biến một máy trạng thái thành Stream dùng captured mutable fields:** làm phụ thuộc thứ tự khó nhận ra.
6. **Tách logic dừng khỏi thông tin lỗi:** mất khả năng báo đúng dòng, đúng lý do.
7. **Dùng `findAny` thay `findFirst` khi phải chọn phần tử đầu:** không giữ hợp đồng encounter order.
8. **Đặt side effect bắt buộc trong pipeline short-circuit:** không phải mọi phần tử đều được duyệt.
9. **Tái sử dụng một Stream sau terminal operation:** Stream là single-use.
10. **Dùng `parallelStream` với state phụ thuộc phần tử trước:** dễ race hoặc sai thứ tự.
11. **Chọn `takeWhile` trên unordered source để diễn tả “trước dòng STOP”:** thiếu encounter order rõ.
12. **Ẩn checked exception trong lambda bằng catch trả null vô điều kiện:** che lỗi và làm sai kết quả.
13. **Quên đóng Stream có I/O:** terminal operation không tự đóng tài nguyên.
14. **Cho rằng code Stream ít dòng sẽ nhanh hơn:** không có cơ sở nếu chưa đo.
15. **Ép tất cả hoạt động vào một pipeline:** có thể giảm độ rõ của ranh giới transaction và xử lý lỗi.
16. **Không kiểm tra sự tương đương khi refactor:** cùng ví dụ đã cho thấy filter khác takeWhile.

## 14. Bài tập

**Bài 1.** Với `[4,0,8,-1,16,32]`, so sánh tổng từ vòng lặp có `break` và Stream dùng `filter(n>=0)`. Vì sao khác nhau?

**Bài 2.** Viết Stream dùng `takeWhile` để tương đương với vòng lặp dừng ở số âm đầu tiên. Điều kiện nào về thứ tự nguồn là quan trọng?

**Bài 3.** Với danh sách tên có chuỗi blank, hãy đổi vòng lặp `continue` sang pipeline `map(String::strip).filter(...)`. Vì sao đây là refactor hợp lý?

**Bài 4.** Một lambda trong `forEach` chứa `return;`. Nó thoát lambda, terminal operation hay phương thức bao quanh?

**Bài 5.** Dùng `findFirst` chọn Task đầu tiên không cancelled và có priority tối thiểu 8. Nêu kết quả từ chương trình.

**Bài 6.** Với batch chuỗi `["10"," ","oops","20","STOP","30"]`, hãy chỉ ra tổng, lỗi và cờ dừng mong đợi.

**Bài 7.** Một hệ thống đọc command BEGIN, ADD, ROLLBACK, COMMIT. Vì sao vòng lặp và switch có thể dễ bảo trì hơn `map` trên state mutable?

**Bài 8.** Dùng `anyMatch` tìm một phần tử thỏa điều kiện. Có được trông đợi predicate chạy trên tất cả phần tử không?

**Bài 9.** Thay cách dùng `parallelStream().forEach(n -> total[0] += n)` bằng một phép tổng hợp đúng.

**Bài 10.** Nếu xử lý file line-by-line, việc gọi `lines.collect(...)` có tự đóng file không? Nên đặt vùng đóng ở đâu?

**Bài 11.** Nêu hai tình huống mà Stream cải thiện khả năng đọc và hai tình huống vòng lặp rõ hơn.

**Bài 12.** Khi tối ưu hiệu năng của một pipeline nhỏ, vì sao chỉ nhìn số dòng code hoặc một lần chạy thử là chưa đủ?

### Gợi ý đáp án

1. Vòng lặp có break trả 12, `filter(n>=0)` trả 60 vì bỏ số âm nhưng tiếp tục cộng phía sau.
2. `values.stream().takeWhile(n -> n>=0).mapToInt(Integer::intValue).sum()`; cần encounter order nếu “trước mốc” có nghĩa.
3. Các phần tử độc lập, mục tiêu là biến đổi và tạo danh sách.
4. Chỉ thoát lần gọi lambda hiện tại; không thoát phương thức bao quanh.
5. `Optional[C]` trên nguồn Task đã cho.
6. Tổng 30, lỗi `Line 3: oops`, `stopped=true`; số 30 sau STOP không được đọc.
7. State phụ thuộc lệnh trước và rollback phải theo thứ tự; vòng lặp thể hiện transition trực tiếp.
8. Không; `anyMatch` short-circuit.
9. `values.parallelStream().mapToInt(Integer::intValue).sum()` nếu miền int phù hợp.
10. Không; dùng `try-with-resources` với Stream/reader đang sở hữu resource.
11. Stream: lọc/biến đổi/thu List và nhóm/thống kê. Vòng lặp: retry có lỗi, máy trạng thái hoặc dừng phức tạp.
12. JIT, warm-up, input và overhead làm kết quả phụ thuộc môi trường; dùng benchmark đúng nếu cần.

## Kết luận

**Thiết kế theo hàm không có nghĩa loại bỏ toàn bộ vòng lặp.** Stream mạnh khi bài toán là biến đổi dữ liệu và gom kết quả với các phép toán độc lập, khai báo được. Vòng lặp mạnh khi điều quan trọng là **diễn đạt luồng điều khiển**: dừng, bỏ qua, trả về, xử lý lỗi, chuyển trạng thái hoặc điều phối tài nguyên.

Hãy giữ thứ giúp người đọc thấy **điều kiện dừng, chính sách lỗi, ranh giới state và hợp đồng kết quả** dễ nhất. Có thể dùng vòng lặp để điều phối toàn bộ quy trình và Stream bên trong những phép tính thuần. Khi refactor, kiểm tra tương đương ngữ nghĩa bằng dữ liệu có marker dừng, nguồn rỗng, lỗi parse và trạng thái giao dịch; đừng chỉ so số dòng code.
