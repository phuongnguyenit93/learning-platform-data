# Chuỗi bất biến không làm mọi biến hoặc cấu trúc chứa nó an toàn đa luồng

## 1. Vấn đề cần hiểu

`String` trong Java là **immutable** (bất biến): sau khi một đối tượng `String` được tạo, nội dung của chính đối tượng đó không thể thay đổi thông qua API công khai. Nhiều luồng có thể cùng đọc một đối tượng `String` đã được chia sẻ đúng cách mà không làm hỏng nội dung chuỗi.

Tuy nhiên, **`String` bất biến không đồng nghĩa mọi biến tham chiếu đến `String`, mọi thao tác trên biến đó hoặc mọi cấu trúc lưu `String` đều an toàn đa luồng**.

Ví dụ:

```java
String name = "Java";
name = name + " 17";
```

Biểu thức trên tạo giá trị chuỗi mới rồi **gán lại biến `name`**; nó không chỉnh sửa đối tượng `"Java"`. Nếu nhiều luồng cùng đọc và gán lại **một biến dùng chung**, vấn đề tranh chấp (race condition), mất cập nhật (lost update) và khả năng nhìn thấy dữ liệu (visibility) vẫn tồn tại.

Mục tiêu bài học:
- Phân biệt **đối tượng bất biến**, **biến tham chiếu có thể gán lại** và **cấu trúc chứa chuỗi có thể thay đổi**.
- Giải thích vì sao `shared = shared + text` không phải một phép cập nhật nguyên tử.
- Hiểu vai trò của `volatile`, `synchronized` và `AtomicReference<String>` theo Java Memory Model.
- Chọn giải pháp phù hợp khi chia sẻ trạng thái chuỗi giữa các luồng.

## 2. Đối tượng `String` và biến tham chiếu là hai thứ khác nhau

Xét:

```java
String a = "hello";
String b = a;
a = a.toUpperCase();

System.out.println(a); // HELLO
System.out.println(b); // hello
```

`a` và `b` ban đầu trỏ đến cùng nội dung `"hello"`. `toUpperCase()` trả một giá trị `String` mới trong ví dụ này, sau đó `a` được gán lại; `b` vẫn trỏ đến chuỗi ban đầu.

Cần tách ba mức độ:

| Thành phần | Bất biến không? | Điều gì có thể xảy ra khi đa luồng? |
| --- | --- | --- |
| Một **đối tượng `String`** | Có; nội dung không thay đổi. | Các luồng đọc chung không tranh chấp vì thao tác sửa nội dung. |
| Một **biến/field `String` dùng chung**, ví dụ `current` | Không nhất thiết; tham chiếu có thể được gán lại. | Đọc/ghi đồng thời có thể thiếu bảo đảm visibility và xảy ra lost update. |
| Một **container** như `ArrayList<String>`, `HashMap<String,String>` hoặc `StringBuilder` | Thường là mutable. | Các phép sửa container có thể race hoặc vi phạm hợp đồng thread safety. |

Một biến `final String greeting = "hello";` ngăn **gán lại biến đó** sau khi khởi tạo, nhưng `final` không tự biến một cấu trúc chứa biến thành đối tượng immutable, cũng không làm tất cả các field khác của đối tượng chứa trở nên thread-safe.

## 3. Vì sao ghép chuỗi vào biến chung có thể mất cập nhật?

Xét trạng thái dùng chung:

```java
class State {
    String text = "X";
}
```

Nếu hai luồng cùng thực hiện:

```java
state.text = state.text + "A"; // Luồng 1
state.text = state.text + "B"; // Luồng 2
```

Một phép `+=` hay phép gán kết hợp này phải thực hiện nhiều bước:

1. **Đọc** tham chiếu hiện tại từ `state.text`.
2. **Tính** một giá trị `String` mới bằng cách ghép hậu tố.
3. **Ghi** tham chiếu `String` mới trở lại `state.text`.

Trong một lịch thực thi có thể xảy ra:

| Thời điểm | Luồng 1 | Luồng 2 | Giá trị trong `state.text` |
| --- | --- | --- | --- |
| Ban đầu | — | — | `"X"` |
| 1 | Đọc `"X"` | — | `"X"` |
| 2 | — | Đọc `"X"` | `"X"` |
| 3 | Tạo và gán `"XA"` | — | `"XA"` |
| 4 | — | Tạo và gán `"XB"` từ bản đọc cũ | `"XB"` |

Kết quả cuối trong lịch trên là `"XB"`: cập nhật của luồng 1 **bị ghi đè**. Nếu thứ tự ghi đảo ngược, kết quả có thể là `"XA"`. Không có đối tượng `String` nào bị sửa đổi hoặc hỏng; lỗi nằm ở **quá trình cập nhật tham chiếu dùng chung**.

Ở đây có **data race** khi các luồng truy cập field không được đồng bộ và có ít nhất một truy cập ghi. Không nên dựa vào việc “chạy vài lần vẫn đúng” để kết luận chương trình an toàn: trình biên dịch, JVM và bộ xử lý được phép tối ưu trong phạm vi Java Memory Model khi thiếu quan hệ *happens-before* cần thiết.

## 4. Java 17+: ví dụ chạy độc lập, có kết quả xác định

Ví dụ cố ý buộc hai luồng cùng đọc giá trị cũ trước khi ghi, để lỗi lost update được tái hiện rõ ràng thay vì phụ thuộc may rủi vào lịch chạy.

Lưu thành file `ImmutableStringConcurrencyDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableStringConcurrencyDemo {
    static final class Holder {
        String value = "X";
    }

    static void appendUnsafely(
            Holder shared, CountDownLatch bothRead, String suffix) {
        // Cả hai luồng đều đọc "X" trước bất kỳ phép ghi nào.
        String snapshot = shared.value;
        bothRead.countDown();

        try {
            bothRead.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }

        // Ghi đè bằng giá trị suy ra từ snapshot riêng.
        shared.value = snapshot + suffix;
    }

    public static void main(String[] args) throws InterruptedException {
        String original = "Hi";
        String updated = original.concat("!");
        System.out.println("original = " + original);
        System.out.println("updated = " + updated);

        Holder unsafe = new Holder();
        CountDownLatch bothRead = new CountDownLatch(2);

        Thread first = new Thread(
                () -> appendUnsafely(unsafe, bothRead, "A"));
        Thread second = new Thread(
                () -> appendUnsafely(unsafe, bothRead, "B"));

        first.start();
        second.start();
        first.join();
        second.join();

        // Giá trị là "XA" hoặc "XB", không chứa đủ hai cập nhật.
        System.out.println("unsafe length = " + unsafe.value.length());

        AtomicReference<String> safe = new AtomicReference<>("X");
        Thread third = new Thread(
                () -> safe.updateAndGet(s -> s + "A"));
        Thread fourth = new Thread(
                () -> safe.updateAndGet(s -> s + "B"));

        third.start();
        fourth.start();
        third.join();
        fourth.join();

        String result = safe.get();
        // "XAB" hoặc "XBA", luôn giữ được cả hai cập nhật.
        System.out.println("atomic length = " + result.length());
        System.out.println("contains A = " + result.contains("A"));
        System.out.println("contains B = " + result.contains("B"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ImmutableStringConcurrencyDemo.java
java ImmutableStringConcurrencyDemo
```

Đầu ra (độc lập với thứ tự cập nhật giữa các luồng, nếu không bị ngắt bất thường):

```text
original = Hi
updated = Hi!
unsafe length = 2
atomic length = 3
contains A = true
contains B = true
```

**Giải thích kết quả:**
- Lời gọi `concat("!")` tạo chuỗi `"Hi!"`, còn `original` tiếp tục là `"Hi"`.
- `CountDownLatch(2)` đảm bảo cả hai luồng đã đọc `"X"` trước khi bất kỳ luồng nào được đi tiếp đến phép gán. Vì mỗi luồng chỉ thêm một hậu tố vào cùng snapshot, giá trị cuối của `unsafe.value` có độ dài **2**, dù đã có hai lần “thêm”.
- `AtomicReference.updateAndGet` thực hiện một phép cập nhật nguyên tử theo hàm biến đổi. Nếu hai luồng cạnh tranh, một luồng có thể phải thử lại với giá trị vừa được luồng kia cập nhật. Vì vậy chuỗi cuối có độ dài **3** và chứa cả `A` lẫn `B`, tuy thứ tự `XAB` / `XBA` không xác định.
- `Thread.join()` giúp luồng `main` chờ các công việc kết thúc và nhìn thấy kết quả của chúng. `join()` **không** làm cho thao tác cập nhật dùng chung trong các luồng tự trở thành nguyên tử.
- Hàm đưa cho `updateAndGet` là `s -> s + suffix`, không có tác dụng phụ. Hàm cập nhật có thể bị gọi nhiều lần khi xảy ra cạnh tranh; đừng đặt thao tác gửi email, ghi file hoặc cập nhật hệ thống khác trong lambda này.

Đây là ví dụ minh họa **lost update**, không phải lời khuyên dùng biến chia sẻ không đồng bộ trong ứng dụng thực tế.

## 5. `volatile` giải quyết visibility, không tự giải quyết lost update

Khai báo:

```java
class Status {
    volatile String message = "starting";
}
```

Với `volatile`, lệnh ghi `message` và lần đọc `message` tương ứng có bảo đảm về khả năng nhìn thấy và thứ tự theo Java Memory Model. Các luồng đọc field `volatile` sẽ không bị giữ mãi giá trị cũ do cache/hoist theo cách vi phạm quy tắc này. Việc đọc/ghi **một tham chiếu** là thao tác nguyên tử, kể cả khi không khai báo `volatile`; điểm thêm vào của `volatile` là bảo đảm visibility và ordering.

Nếu chỉ có một luồng cập nhật thông báo còn các luồng khác đọc thông báo, mẫu dùng `volatile String` có thể phù hợp:

```java
final class Status {
    private volatile String message = "pending";

    void publish(String next) {
        message = next;
    }

    String current() {
        return message;
    }
}
```

Tuy nhiên:

```java
volatile String text = "X"; // Ví dụ một field trong lớp

void append(String suffix) {
    text = text + suffix;
}
```

**Vẫn có thể mất cập nhật.** `volatile` làm các lần đọc/ghi riêng lẻ có visibility, nhưng không gom phép **đọc → ghép → ghi** thành một giao dịch nguyên tử. Cả hai luồng vẫn có thể đọc cùng giá trị cũ rồi lần lượt ghi đè.

Ghi nhớ: **immutable** nói về trạng thái **của đối tượng**; **volatile** nói về visibility/ordering khi truy cập **field**; **atomicity** nói về tính không thể bị xen kẽ của **cả thao tác cập nhật**. Ba thuộc tính này khác nhau.

## 6. Giải pháp khi cần cập nhật chuỗi dùng chung

### 6.1. Đồng bộ bằng `synchronized`

Khi thao tác ghép cần bảo toàn mọi cập nhật, có thể bao toàn bộ đoạn đọc–tính–ghi trong cùng một khóa:

```java
final class SynchronizedText {
    private String value = "";

    public synchronized void append(String part) {
        value = value + part;
    }

    public synchronized String get() {
        return value;
    }
}
```

Hai luồng gọi `append("A")` và `append("B")` trên **cùng instance** sẽ không xen kẽ phần thân phương thức đồng bộ; chuỗi cuối chứa cả hai phần. Các phương thức `synchronized` trên cùng một đối tượng dùng chung monitor, đồng thời cung cấp quan hệ *happens-before* cho việc đọc/ghi được bảo vệ bởi monitor đó.

Nếu có nhiều field cần thay đổi nhất quán trong cùng một thao tác, `synchronized` hoặc một khóa phù hợp thường dễ biểu đạt toàn bộ bất biến hơn việc cập nhật từng field độc lập.

### 6.2. `AtomicReference<String>`

Khi cần cập nhật nguyên tử **một tham chiếu chuỗi**, không cần khóa ngoài cho toàn bộ thao tác:

```java
import java.util.concurrent.atomic.AtomicReference;

final class AtomicText {
    private final AtomicReference<String> value =
            new AtomicReference<>("");

    void append(String part) {
        value.updateAndGet(old -> old + part);
    }

    String get() {
        return value.get();
    }
}
```

`AtomicReference` sử dụng các thao tác nguyên tử như compare-and-set. Mỗi lần `updateAndGet` thành công đều được tính trên giá trị phù hợp với thứ tự cập nhật nguyên tử; khi cạnh tranh, lambda có thể chạy lại. Vì vậy **lambda nên thuần túy, không có tác dụng phụ**, và giá trị `part` nên ổn định trong phạm vi phép gọi.

Nếu nhiều tham chiếu cần cập nhật đồng thời theo một ràng buộc chung, một `AtomicReference` cho từng field **không đủ** để biến cả nhóm cập nhật thành nguyên tử. Có thể dùng khóa hoặc gom trạng thái vào một đối tượng giá trị bất biến rồi thay toàn bộ đối tượng qua một `AtomicReference<State>`.

### 6.3. Không chia sẻ trạng thái ghi được

Trong nhiều ứng dụng, giải pháp đơn giản nhất là mỗi luồng xử lý biến cục bộ riêng:

```java
String makeMessage(String name) {
    String result = "Hello, ";
    result = result + name;
    return result;
}
```

`result` là biến cục bộ mỗi lần gọi; nếu không đưa nó vào vùng trạng thái chia sẻ, các luồng không tranh chấp khi gán lại `result`. Việc dùng `String` bất biến giúp không xảy ra chỉnh sửa lén nội dung của một chuỗi đã được chuyển qua phương thức khác.

Đừng đồng bộ mọi thao tác đọc chuỗi chỉ vì chương trình đa luồng. Đồng bộ cần đặt đúng nơi **trạng thái mutable dùng chung** được đọc và ghi.

## 7. Container chứa `String` không tự trở thành thread-safe

Một tập hợp các phần tử bất biến vẫn có thể là một **đối tượng collection mutable**:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("An");
names.add("Bình");
```

Mỗi phần tử `String` là immutable, nhưng cấu trúc nội bộ của `ArrayList` (kích thước, mảng phần tử, việc thay đổi/duyệt) không được thiết kế cho các phép sửa đồng thời không đồng bộ. Nếu nhiều luồng cùng sửa `names`, tính bất biến của phần tử không bảo vệ cấu trúc danh sách.

Các tình huống tương tự:

| Cấu trúc | Tính chất cần nhớ | Khi chia sẻ nhiều luồng |
| --- | --- | --- |
| `ArrayList<String>` | Danh sách mutable, thao tác sửa không thread-safe theo mặc định. | Dùng khóa khi truy cập/sửa chung, hoặc chọn collection concurrent nếu bài toán phù hợp. |
| `HashMap<String, String>` | Key/value bất biến không bảo vệ bảng băm mutable. | Không sửa đồng thời mà thiếu đồng bộ; dùng `ConcurrentHashMap` cho truy cập/cập nhật concurrent. |
| `ConcurrentHashMap<String, String>` | Hỗ trợ các phép thao tác concurrent được tài liệu API bảo đảm. | Dùng `compute` / `merge` khi cần cập nhật một key dựa trên giá trị cũ. |
| `StringBuilder` | Bộ đệm ký tự mutable, **không** đồng bộ. | Dùng riêng từng luồng hoặc khóa quanh toàn bộ thao tác dùng chung. |
| `StringBuffer` | Nhiều phương thức có đồng bộ nội tại. | Một chuỗi nhiều lời gọi vẫn có thể cần đồng bộ bổ sung nếu phải nguyên tử ở mức nghiệp vụ. |
| `List.of("A", "B")` / `List.copyOf(...)` | Collection không cho phép thay đổi cấu trúc qua API collection. | Có thể chia sẻ để đọc sau khi công bố đúng cách; với phần tử mutable, đây không phải deep immutability. |

Ví dụ sai, vì hai bước `get` và `put` tách rời nhau:

```java
// map là ConcurrentHashMap<String, String>, key "log" đã tồn tại.
String old = map.get("log");
map.put("log", old + "A"); // Có thể ghi đè cập nhật của luồng khác.
```

Cách giữ phép cập nhật **một key** trong thao tác nguyên tử thích hợp:

```java
map.compute("log", (key, old) ->
        (old == null ? "" : old) + "A");
```

`ConcurrentHashMap.compute` đồng bộ logic cập nhật của key theo hợp đồng API; hãy giữ hàm ánh xạ ngắn gọn, tránh side effect và tránh thao tác đệ quy lên cùng map. Tương tự như `AtomicReference`, an toàn của thao tác collection được quyết định bởi **hợp đồng collection và cách dùng**, không chỉ bởi việc giá trị `String` bất biến.

### Wrapper và bất biến bề ngoài

`Collections.unmodifiableList(mutableList)` là **view không cho sửa qua wrapper**, nhưng danh sách gốc vẫn có thể bị sửa từ nơi khác. Wrapper không tự cung cấp đồng bộ hoặc snapshot. Ngược lại, `List.copyOf(source)` tạo một danh sách không thể sửa cấu trúc qua API và không phản ánh việc thêm/xóa ở danh sách nguồn; nó không sao chép sâu phần tử mutable.

Vì vậy “danh sách các `String` bất biến” và “danh sách bất biến” là hai nhận định khác nhau.

## 8. Công bố tham chiếu và Java Memory Model

Một tham chiếu tới `String` có thể được đọc qua nhiều luồng. Không thể từ việc chuỗi bất biến mà suy ra **mọi phép công bố hoặc thay thế tham chiếu** đều có quan hệ *happens-before*.

Ví dụ:

```java
class MessageBox {
    String latest = "initial";

    void set(String text) {
        latest = text;
    }

    String get() {
        return latest;
    }
}
```

Nếu một luồng gọi `set` trong lúc luồng khác gọi `get` mà không có đồng bộ khác, không có bảo đảm đủ mạnh rằng luồng đọc sẽ thấy **giá trị mới nhất** đúng thời điểm mong đợi. Bản thân nội dung đối tượng `String` vẫn bất biến, nhưng giao thức trao đổi cập nhật qua field `latest` còn thiếu.

Các cách tạo quan hệ đồng bộ/happens-before thường dùng:
- Dùng `volatile` khi cần công bố/thay thế **một tham chiếu** và không cần ghép cập nhật.
- Dùng khóa `synchronized`/`Lock` khi đọc và ghi một nhóm trạng thái theo bất biến chung.
- Dùng `AtomicReference` cho việc thay tham chiếu nguyên tử hoặc các phép cập nhật read–modify–write.
- Dùng collection/concurrent queue đúng hợp đồng hoặc cơ chế chuyển thông điệp nếu các luồng phải trao đổi dữ liệu.

Field `final` được khởi tạo đúng trong constructor mang lại bảo đảm đặc biệt cho quá trình khởi tạo theo Java Memory Model (giả định `this` không thoát ra trong lúc khởi tạo). Nhưng một đối tượng có field `final String` vẫn có thể chứa nhiều field mutable khác và **không tự nhiên an toàn đa luồng**.

## 9. Chọn cách thiết kế theo yêu cầu

| Yêu cầu | Hướng triển khai |
| --- | --- |
| Nhiều luồng chỉ đọc cùng một `String` đã được công bố đúng cách | Chia sẻ trực tiếp chuỗi; không cần khóa để bảo vệ nội dung bất biến. |
| Một luồng thay thông báo, nhiều luồng đọc thông báo mới | `volatile String` hoặc `AtomicReference<String>`, tùy nhu cầu API. |
| Nhiều luồng cùng “thêm” vào một biến chuỗi | `synchronized` hoặc `AtomicReference.updateAndGet`; tránh `+=` không đồng bộ. |
| Cập nhật nhiều field phải nhất quán với nhau | Khóa chung hoặc một đối tượng trạng thái bất biến được thay nguyên tử. |
| Nhiều luồng thao tác trên map chứa các `String` | `ConcurrentHashMap` với API cập nhật phù hợp; `get` rồi `put` có thể chưa đủ. |
| Ghép chuỗi dài, mỗi luồng có bộ đệm riêng | `StringBuilder` cục bộ; tạo `String` khi cần chia sẻ kết quả. |
| Cần danh sách chỉ đọc | Dùng bản sao immutable thích hợp và công bố đúng cách; phân biệt snapshot với unmodifiable view. |

**Lưu ý hiệu năng:** cập nhật chuỗi bằng `old + suffix` liên tục có thể tạo nhiều chuỗi trung gian do `String` bất biến. Với lượng nối lớn, nếu các luồng tạo dữ liệu độc lập, thường nên dùng `StringBuilder` cục bộ rồi kết hợp kết quả bằng cơ chế đồng bộ hợp lý. Đừng dùng một `StringBuilder` mutable chung mà không có đồng bộ chỉ để tránh tạo đối tượng.

## 10. Những khẳng định dễ nhầm

1. **“`String` immutable nên `shared += "x"` thread-safe.”** Sai: câu lệnh thay biến dùng chung qua nhiều bước.
2. **“Thêm `volatile` là mọi cập nhật an toàn.”** Sai: visibility không tự đảm bảo atomic read–modify–write.
3. **“`List<String>` luôn thread-safe vì phần tử là chuỗi.”** Sai: container mutable có trạng thái và quy tắc đồng bộ riêng.
4. **“`ConcurrentHashMap` khiến bất kỳ chuỗi thao tác `get` rồi `put` thành atomic.”** Sai: dùng `compute`/`merge` khi muốn cập nhật nguyên tử theo key.
5. **“Dùng `synchronized` khi đọc chuỗi là bắt buộc.”** Sai: đọc đối tượng chuỗi bất biến đã được công bố đúng cách không cần khóa riêng để bảo vệ nội dung; tuy nhiên giao thức trao đổi trạng thái xung quanh có thể cần khóa.
6. **“Có `final String` nên cả object an toàn đa luồng.”** Sai: field khác vẫn có thể mutable, và sự nhất quán giữa các field cần thiết kế riêng.

## 11. Bài tập áp dụng

**Bài 1.** Có một field dùng chung:

```java
volatile String log = "";

void add(String item) {
    log = log + item;
}
```

Hai luồng gọi `add("A")` và `add("B")`. Có bảo đảm `log` chứa cả hai phần không?

**Đáp án:** Không. Mỗi luồng có thể đọc cùng snapshot cũ trước khi gán; `volatile` không tạo atomicity cho cả phép ghép. Có thể thay bằng `AtomicReference<String>.updateAndGet` hoặc đồng bộ hóa toàn bộ thao tác.

**Bài 2.** Một dịch vụ công bố chuỗi trạng thái mới mà không cần ghép với trạng thái cũ; một luồng ghi, nhiều luồng đọc. Có cần dùng `AtomicReference.updateAndGet` không?

**Đáp án:** Không nhất thiết. Một field `volatile String status` cùng cách đọc/ghi đơn giản đã phù hợp với nhiều trường hợp công bố trạng thái độc lập. Nếu phải bảo đảm chuyển đổi có điều kiện dựa trên giá trị cũ, nên cân nhắc cơ chế atomic/locking.

**Bài 3.** Một `HashMap<String,String>` có key và value đều là `String`. Có thể vừa thay map từ nhiều luồng vừa duyệt trực tiếp không đồng bộ?

**Đáp án:** Không. Chuỗi bất biến không bảo vệ cấu trúc `HashMap` khi sửa đồng thời. Chọn `ConcurrentHashMap` hoặc đồng bộ ngoại vi theo nhu cầu nhất quán của thao tác.

**Bài 4.** Khi cần đọc một chuỗi đã tạo và chia sẻ qua thread-safe queue, phải khóa riêng cho `charAt` và `length` của chuỗi đó không?

**Đáp án:** Không cần khóa riêng để bảo vệ nội dung immutable của `String`. Việc chuyển chuỗi qua queue có hợp đồng concurrent thích hợp cung cấp cơ chế công bố/chuyển giao; còn các trạng thái mutable khác phải xét riêng.

## Tài liệu tham khảo

- [Java SE 17: `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17: `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [Java SE 17: `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
