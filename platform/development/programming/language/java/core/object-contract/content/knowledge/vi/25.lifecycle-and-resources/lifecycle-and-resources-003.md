# Phân biệt `final`, `finally` và `finalize()` trong Java

Ba tên này trông giống nhau nhưng thuộc **ba cơ chế hoàn toàn khác nhau**: `final` ràng buộc việc gán/ghi đè/kế thừa ở mức ngôn ngữ; `finally` là khối thực thi khi rời cấu trúc `try`; còn `finalize()` là cơ chế dọn dẹp đối tượng kiểu cũ, hiện **đã bị deprecated for removal**. Không thể dùng chúng thay thế cho nhau.

| Khía cạnh | `final` | `finally` | `finalize()` |
| --- | --- | --- | --- |
| Bản chất | Từ khóa (modifier) | Từ khóa chỉ khối lệnh của `try` | Phương thức kế thừa từ `java.lang.Object` |
| Đặt ở đâu? | Biến, tham số, trường, phương thức, lớp | Sau `try`/`catch`; cũng có thể sau `try-with-resources` | Định nghĩa ghi đè trong lớp kiểu cũ |
| Mục đích | Hạn chế phép gán lại, ghi đè hoặc kế thừa | Thực hiện thao tác cuối khi rời `try`, kể cả lúc `return`/`throw` | Từng được dùng làm điểm móc trước khi GC thu hồi đối tượng |
| Thời điểm | Quy tắc được kiểm tra khi biên dịch (với biến, method, class) | Trong luồng điều khiển khi `try` hoàn tất | Nếu JVM có chạy thì diễn ra bất định, do bộ máy finalization |
| Có bảo đảm dọn tài nguyên? | Không | Có ích trong luồng thoát thông thường, nhưng không phải mọi cách JVM dừng | **Không**; không có bảo đảm sẽ được gọi |
| Thực hành Java hiện đại | Dùng khi cần ràng buộc rõ ràng | Dùng để khôi phục trạng thái, nhưng ưu tiên `try-with-resources` để đóng tài nguyên | Tránh sử dụng; ưu tiên `AutoCloseable` và `try-with-resources` |

## 1. `final` — ràng buộc ở thời điểm viết chương trình

### 1.1. `final` với biến, tham số và trường

Một biến `final` **chỉ được gán đúng một lần** sau khi xác định giá trị của nó. Đó là giới hạn đối với **biến/tham chiếu**, không có nghĩa toàn bộ đối tượng mà biến trỏ đến là bất biến.

```java
final int maxRetries = 3;
// maxRetries = 4; // Lỗi biên dịch: không thể gán lại.

final StringBuilder message = new StringBuilder("Hello");
message.append(" Java"); // Hợp lệ: thay đổi trạng thái đối tượng.
// message = new StringBuilder("Other"); // Lỗi: gán lại tham chiếu.

final int[] numbers = {1, 2};
numbers[0] = 99; // Hợp lệ: phần tử mảng có thể thay đổi.
// numbers = new int[] {3, 4}; // Lỗi: gán lại biến mảng.
```

Các trường hợp thường gặp:

- **Biến cục bộ `final`**: phải được gán trước khi đọc và không thể gán lại. `final int value; value = 10;` hợp lệ nếu mọi đường đi dùng biến đều đã khởi tạo và không gán lần thứ hai.
- **Tham số `final`**: không thể gán lại tên tham số trong thân phương thức; trạng thái của đối tượng truyền vào vẫn có thể thay đổi nếu API cho phép.
- **Trường instance `final`**: phải được gán tại khai báo, trong initializer hoặc trong mọi đường đi hoàn tất bình thường của constructor phù hợp. Sau khi đối tượng được xây xong, trường không thể được gán lại bằng mã Java thông thường.
- **Trường `static final`**: chỉ được khởi tạo một lần cho lớp, thường dùng làm hằng số. Không phải mọi `static final` đều là hằng số biên dịch: `static final int LIMIT = 10` là một biểu thức hằng, còn `static final List<String> ITEMS = new ArrayList<>()` giữ một tham chiếu duy nhất tới danh sách vẫn có thể thay đổi.
- **Biến được lambda/lớp cục bộ capture**: phải là `final` hoặc *effectively final* (không bị gán lại sau lần khởi tạo). Không bắt buộc viết từ khóa nếu biến vốn không đổi.

```java
static final int DEFAULT_PORT = 8080; // Giá trị hằng kiểu nguyên thủy.

private final String id;

public Example(String id) {
    this.id = id; // Gán trường final của đối tượng.
}
```

Đoạn trên chỉ minh họa khai báo bên trong một lớp tên `Example`; chưa phải tệp chạy độc lập.

**`final` không tự làm đối tượng immutable.** Chẳng hạn `final List<String> list = new ArrayList<>();` vẫn cho phép `list.add(...)`. Muốn thiết kế đối tượng bất biến, cần kết hợp đóng gói trạng thái, tránh setter, sao chép dữ liệu mutable phù hợp và không làm lộ tham chiếu mutable. `List.copyOf(...)` tạo danh sách không cho phép sửa bằng API danh sách, nhưng nếu phần tử bên trong mutable thì đó vẫn chỉ là sự bất biến *nông*.

Các trường `final` còn có quy tắc đặc biệt về khả năng nhìn thấy trạng thái sau khởi tạo trong Java Memory Model khi đối tượng được xây dựng đúng cách (không để `this` thoát trong constructor). Tuy nhiên, riêng `final` **không** làm một đối tượng mutable trở nên an toàn để nhiều thread cùng sửa.

### 1.2. `final` với phương thức và lớp

- **Phương thức `final`** không thể bị *override* bởi lớp con. Lớp con vẫn có thể gọi phương thức thừa kế (nếu nhìn thấy), và các phương thức cùng tên nhưng khác tham số vẫn có thể được *overload*.
- **Lớp `final`** không thể được `extends`. Điều này không cấm tạo instance hoặc lớp đó thực hiện interface.
- `final` và `abstract` không thể cùng đặt trên một lớp hoặc cùng trên một phương thức: một bên khóa mở rộng, bên kia yêu cầu triển khai ở lớp con.
- Với lớp được đánh dấu `final`, các instance method đủ điều kiện ghi đè vốn đã không thể bị lớp con ghi đè, vì không thể có lớp con.

```java
class Parent {
    final void identity() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    // void identity() {} // Lỗi biên dịch: không được override final method.

    void identity(String label) { // Hợp lệ: overload với tham số khác.
        System.out.println(label);
    }
}

final class Token {
}

// class SpecialToken extends Token {} // Lỗi: không được extends final class.
```

**Hiểu đúng:** `final` khóa một khả năng thay đổi cụ thể; nó không thay thế kiểm tra tính hợp lệ, kiểm soát truy cập, thiết kế immutable hay đồng bộ hóa.

## 2. `finally` — khối lệnh chạy khi rời `try`

Một cấu trúc thường gặp:

```java
try {
    // Thao tác có thể thành công hoặc ném ngoại lệ.
} catch (RuntimeException e) {
    // Xử lý ngoại lệ nếu phù hợp.
} finally {
    // Thực hiện khi thoát khỏi cấu trúc try/catch.
}
```

Trong hoạt động bình thường của JVM, `finally` được thực hiện sau khi nhánh `try` hoặc `catch` kết thúc, dù kết thúc do đi hết khối, `return`, `break`, `continue` hay ngoại lệ. Nếu ngoại lệ không được bắt, `finally` vẫn chạy **trước khi** ngoại lệ tiếp tục lan ra caller. Với `return`, biểu thức trả về được tính trước khi khối `finally` chạy; phương thức chỉ thực sự trả quyền điều khiển cho caller sau đó.

**Không được hiểu là tuyệt đối trong mọi tình huống:** nếu tiến trình bị chấm dứt đột ngột, JVM bị halt/crash hoặc không thể tiếp tục thực thi, `finally` có thể không chạy. Chẳng hạn `System.exit(...)` kết thúc JVM mà không bảo đảm thực hiện các khối `finally` còn đang chờ.

### 2.1. Ví dụ Java 17 chạy được: `final` và `finally`

Tạo tệp **`FinalFinallyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalFinallyDemo {
    private static final class Session {
        private final List<String> events = new ArrayList<>();

        void add(String value) {
            events.add(value);
        }

        int count() {
            return events.size();
        }
    }

    private static int parsePort(String input) {
        try {
            System.out.println("try: " + input);
            return Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            System.out.println("catch: invalid number");
            return -1;
        } finally {
            System.out.println("finally: input checked");
        }
    }

    public static void main(String[] args) {
        final Session session = new Session();
        session.add("started");
        System.out.println("event count=" + session.count());

        System.out.println("port=" + parsePort("8080"));
        System.out.println("port=" + parsePort("oops"));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac FinalFinallyDemo.java
java FinalFinallyDemo
```

Đầu ra chính xác:

```text
event count=1
try: 8080
finally: input checked
port=8080
try: oops
catch: invalid number
finally: input checked
port=-1
```

Giải thích: `Session` là lớp `final`, trường `events` là tham chiếu `final` nhưng danh sách vẫn thêm phần tử được. `parsePort` trả `8080` từ `try` ở trường hợp đầu và `-1` từ `catch` ở trường hợp sau; cả hai đều in dòng `finally` trước khi caller in `port=...`.

### 2.2. Cạm bẫy: `return`/`throw` trong `finally` che khuất kết quả cũ

```java
static int misleading() {
    try {
        return 1;
    } finally {
        return 2; // Ghi đè việc return 1.
    }
}
```

`misleading()` trả về `2`. Tương tự, nếu `try` đã ném ngoại lệ mà `finally` lại ném ngoại lệ khác, ngoại lệ phát sinh sau có thể thay thế ngoại lệ gốc, khiến khó tìm nguyên nhân. Vì vậy **tránh `return`, `break`, `continue` hoặc `throw` không cần thiết trong `finally`**. Nếu phải chạy cleanup có thể ném lỗi, phải quyết định rõ cách ghi nhận/lan truyền lỗi để không vô tình che lỗi chính.

`finally` phù hợp với thao tác cần chạy khi ra khỏi một đoạn logic, chẳng hạn trả một cờ trạng thái về trạng thái trước đó hoặc giải phóng khóa đã giữ đúng cách. Riêng việc đóng `InputStream`, `Connection`, file, socket và tài nguyên có `AutoCloseable` nên ưu tiên **`try-with-resources`**.

## 3. `try-with-resources` và quan hệ với `finally`

Cấu trúc `try (Resource r = ...) { ... }` tự gọi `close()` trên tài nguyên khi rời khối. Tài nguyên phải triển khai `AutoCloseable`; các biến tài nguyên phải là final hoặc effectively final. Nếu khai báo nhiều tài nguyên, Java đóng **theo thứ tự ngược khi mở**. Với một `finally` đi kèm, việc đóng các tài nguyên từ phần ngoặc của `try` diễn ra trước khối `finally` đó.

Tệp **`ResourceDemo.java`** chạy độc lập với Java 17:

```java
public class ResourceDemo {
    private static final class Probe implements AutoCloseable {
        private final String name;

        Probe(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Probe first = new Probe("A");
             Probe second = new Probe("B")) {
            System.out.println("work");
        } finally {
            System.out.println("finally");
        }
    }
}
```

```bash
javac ResourceDemo.java
java ResourceDemo
```

```text
open A
open B
work
close B
close A
finally
```

**Vì sao ưu tiên cách này?** Việc đóng tài nguyên được gắn với phạm vi `try`, kể cả khi `return` hoặc ném ngoại lệ, và Java quản lý *suppressed exceptions*: nếu thân `try` ném lỗi chính rồi `close()` cũng ném lỗi, lỗi đóng được đính kèm qua `Throwable.getSuppressed()` thay vì mặc định che lỗi chính. Có thể quan sát và ghi nhận các lỗi phụ khi debug.

Một số lưu ý thực hành:

1. Tài nguyên phải thực sự do mã đang viết **sở hữu** và được phép đóng; không tự tiện đóng một đối tượng do caller quản lý.
2. Thứ tự đóng ngược với thứ tự mở, do đó khởi tạo tài nguyên phụ thuộc nhau theo thứ tự hợp lý.
3. `try-with-resources` không tự bảo đảm nghiệp vụ thành công; `close()` cũng có thể ném exception.
4. `finally` vẫn có chỗ dùng cho việc khôi phục trạng thái không biểu diễn thành tài nguyên; đừng dùng nó chỉ để viết một loạt lời gọi `close()` thủ công.

Ví dụ kinh điển với stream:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadFirstLine {
    static String read(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

Đoạn `ReadFirstLine` là lớp minh họa API, không có `main`. `BufferedReader` tự được đóng khi hết phạm vi, kể cả lúc đọc lỗi. Giá trị trả về vẫn có thể là `null` nếu tệp rỗng; `final` và `finally` không liên quan đến kết quả này.

## 4. `finalize()` — callback lịch sử, không phải `finally`

`Object.finalize()` là phương thức kiểu cũ được JVM cân nhắc thực thi khi đối tượng đủ điều kiện finalization; thời điểm và việc có chạy trước khi ứng dụng kết thúc đều **không được bảo đảm**. API bị deprecated từ Java 9 và deprecated for removal theo JEP 421 (JDK 18). Không viết finalizer mới để đóng file, socket hoặc thực hiện nghiệp vụ bắt buộc.

Khác biệt dễ nhầm nằm ở câu hỏi **ai quyết định thời điểm**: `finally` gắn với đường thoát khỏi `try`, còn `finalize()` phụ thuộc cơ chế GC và có thể không chạy. `final` chỉ ràng buộc khai báo, không quản lý vòng đời tài nguyên. Khi cần cleanup, owner gọi `close()` hoặc dùng `try-with-resources`; `Cleaner` (nếu có nhu cầu với native handle) chỉ là fallback và cũng không có deadline. Các bài trước và sau trình bày riêng thời điểm finalization, cách chuyển đổi mã cũ và API đóng chủ động.

## 5. Chọn đúng công cụ trong tình huống thực tế

| Tình huống | Cách chọn | Điều không nên suy diễn |
| --- | --- | --- |
| Không muốn biến cấu hình được gán lại sau khi khởi tạo | `final` | Chưa chắc đối tượng trong trường là immutable |
| Không cho subclass thay đổi thuật toán quan trọng | `final` trên method; hoặc `final` trên class nếu muốn ngăn kế thừa | Không ngăn được mọi cách làm thay đổi dữ liệu |
| Cần ghi log/khôi phục trạng thái khi rời `try` | `finally` | Không được dùng `return` ở đây để thay đổi kết quả |
| Cần đóng file sau khi đọc | `try-with-resources` | Không trông đợi GC hay `finalize()` |
| Code cũ đóng socket bằng `finalize()` | Chuyển sang `AutoCloseable`/`close()` do owner gọi | Không xem finalization là cơ chế cleanup đáng tin |
| Lambda dùng biến cục bộ đã khai báo ngoài lambda | Biến phải `final` hoặc effectively final | Không bắt buộc thêm chữ `final` nếu biến không bị gán lại |

## 6. Lỗi thường gặp và cách kiểm tra

**Lỗi 1 — Tưởng `final` làm cả object bất biến.** Hỏi rõ đang muốn khóa **tham chiếu** hay khóa **trạng thái**. Muốn khóa trạng thái, xem API sửa đổi, alias của collection và cách phòng vệ bằng bản sao.

**Lỗi 2 — Tưởng `final method` không thể gọi từ lớp con.** Lớp con được thừa kế/gọi method có quyền truy cập phù hợp, nhưng không được override nó. Overload là chuyện khác.

**Lỗi 3 — Tưởng `finally` chỉ chạy khi có exception.** Nó chạy cả khi thành công và khi `return` sớm trong hoạt động bình thường. Đặt log trong ví dụ `parsePort` để quan sát đúng thứ tự.

**Lỗi 4 — Viết `return` hoặc ném lỗi mới trong `finally`.** Việc này có thể làm mất giá trị trả về hoặc che ngoại lệ trước đó. Giữ cleanup gọn, xem xét suppressed exceptions nếu có nhiều lỗi.

**Lỗi 5 — Dùng `finalize()` để đóng file/database connection.** Không có thời hạn hay bảo đảm gọi. Chuyển quyền sở hữu đóng tài nguyên sang `try-with-resources` hoặc `close()` tường minh.

**Lỗi 6 — Gọi `System.gc()` rồi chờ `finalize()`.** `System.gc()` chỉ là lời đề nghị và không bảo đảm finalization diễn ra; đây không phải chiến lược correctness hay test đáng tin cậy.

**Tự kiểm tra:** (1) `final List<String> names` có cho phép `names.add("A")` không? Có, nếu danh sách hỗ trợ sửa. (2) `finally` có chạy trước khi caller nhận giá trị `return` không? Có trong luồng kết thúc bình thường. (3) Có thể dựa vào `finalize()` để đóng socket đúng lúc không? Không. (4) API nên dùng để đóng tài nguyên khi ra khỏi block? `AutoCloseable` với `try-with-resources`.

**Ghi nhớ:** `final` là ràng buộc của khai báo; `finally` là bước xử lý khi thoát `try`; `finalize()` là cơ chế finalization cũ không phù hợp cho quản lý tài nguyên Java hiện đại.
