# `try-with-resources` trong Java: Phạm vi biến và tài nguyên tham chiếu `null`

## 1. Mục tiêu và quy tắc cốt lõi

`try-with-resources` được đưa vào Java 7 để **đóng tài nguyên tự động**. Một tài nguyên phải có kiểu triển khai `AutoCloseable` (hoặc giao diện con, chẳng hạn `Closeable`). Sau khi phần thân `try` kết thúc, Java gọi `close()` cho từng tài nguyên được quản lý, kể cả khi khối `try` kết thúc do exception hay `return`, theo các quy tắc ngôn ngữ hiện hành.

Hai chi tiết cần hiểu rõ:

1. **Phạm vi biến (scope):** biến tài nguyên **khai báo trực tiếp trong `try (...)`** chỉ có thể truy cập trong phần còn lại của resource specification và trong **thân khối `try`**. Nó không tự nằm trong phạm vi của `catch`, `finally` hoặc đoạn mã phía sau `try`.
2. **Tài nguyên là `null`:** nếu một tài nguyên được khởi tạo với tham chiếu `null`, `try-with-resources` **không gọi `close()`** cho tài nguyên đó. Việc tham chiếu là `null` **không tự làm thân `try` bị bỏ qua** và cũng không tự gây `NullPointerException` trong bước đóng. Nhưng nếu mã bên trong thực sự gọi phương thức trên tham chiếu `null`, Java vẫn có thể ném `NullPointerException` như bình thường.

```java
try (java.io.InputStream input = null) {
    System.out.println("Thân try vẫn chạy");
} // input == null nên không có close() để gọi
```

Đoạn trên **hợp lệ** và in một dòng. Tuy nhiên, việc cho phép tài nguyên `null` không có nghĩa là bạn nên chủ động thiết kế API trả `null` để báo không mở được tài nguyên: thông thường, lỗi mở tài nguyên cần được biểu diễn rõ bằng exception hoặc kết quả theo hợp đồng.

**Phân biệt phiên bản:** Java 7 hỗ trợ **khai báo biến mới** trong `try (...)`. Kể từ Java 9, có thể dùng **biến đã khai báo từ trước**, nếu biến đó là `final` hoặc *effectively final*. Cả hai cách vẫn dùng được trong Java 17+.

## 2. Phạm vi của biến được khai báo trong dấu ngoặc `try (...)`

### 2.1. Biến dùng được ở đâu?

Ví dụ với `BufferedReader`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void readFirstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        String line = reader.readLine();  // hợp lệ: reader trong phạm vi
        System.out.println(line);
    }

    // System.out.println(reader); // LỖI biên dịch: reader ngoài phạm vi
}
```

Đây là **phương thức minh họa**, không phải chương trình độc lập. Ngay khi biên dịch, biến `reader` chỉ tồn tại trong phạm vi lexical mà ngôn ngữ quy định.

- Trong resource specification, `reader` nằm trong phạm vi **từ vị trí khai báo của nó sang phải**, vì vậy biến tài nguyên được khai báo sau có thể tham chiếu biến trước, miễn mọi quy tắc gán giá trị và kiểu dữ liệu được thỏa.
- Trong **thân `try`**, có thể gọi `reader.readLine()`, truyền `reader` làm đối số và đọc trạng thái của tài nguyên.
- Trong `catch` hoặc `finally` gắn với `try-with-resources` đó, **không thể gọi trực tiếp tên `reader`** nếu nó chỉ được khai báo trong dấu ngoặc.
- Trong các câu lệnh sau toàn bộ `try-with-resources`, tên `reader` cũng không còn trong phạm vi.
- Quy tắc này là quy tắc **phạm vi tên biến ở thời điểm biên dịch**, khác với việc object còn được một biến khác tham chiếu hoặc đã bị đóng hay chưa.

**Không nên hiểu "biến hết scope" là "đối tượng chắc chắn biến mất ngay lập tức".** `close()` là thao tác giải phóng tài nguyên theo hợp đồng API, còn vòng đời của đối tượng trong bộ nhớ do khả năng truy cập (reachability) và cơ chế quản lý bộ nhớ của JVM quyết định.

### 2.2. Không thể dùng biến trong `catch` và `finally`

Ví dụ **cố ý sai** (chỉ để minh họa lỗi biên dịch):

```java
// try (BufferedReader reader = Files.newBufferedReader(path)) {
//     System.out.println(reader.readLine());
// } catch (IOException e) {
//     System.out.println(reader); // lỗi: reader không trong scope của catch
// } finally {
//     System.out.println(reader); // lỗi: reader không trong scope của finally
// }
```

Lúc `catch` hoặc `finally` của `try-with-resources` chạy, những tài nguyên đã được quản lý trong phần header đã được xử lý đóng theo quy tắc của cấu trúc đó. Vì vậy, dù đưa biến ra scope ngoài để vẫn truy cập được, cũng **không nên mặc định rằng resource còn mở ở `catch` hoặc `finally`**.

Nếu cần quan sát lỗi, dùng **đối tượng exception** được bắt, thông tin từ các biến đã khai báo ngoài `try` hoặc dữ liệu bất biến đã thu thập trong lúc tài nguyên còn mở; không dựa vào việc sử dụng lại một resource đã đóng.

### 2.3. Tham chiếu từ tài nguyên sau tới tài nguyên trước

Có thể sử dụng biến được khai báo trước trong header để tạo tài nguyên tiếp theo. Ví dụ:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void readText(Path path) throws IOException {
    try (java.io.InputStream input = Files.newInputStream(path);
         BufferedReader reader = new BufferedReader(
                 new InputStreamReader(input, StandardCharsets.UTF_8))) {
        System.out.println(reader.readLine());
    }
}
```

Ở đây, `input` nằm trong phạm vi của biểu thức khởi tạo `reader`. Khi thoát, Java cố đóng `reader` trước rồi `input` sau vì tài nguyên được đóng theo **thứ tự ngược với khai báo**.

**Lưu ý về ownership:** `BufferedReader`/`InputStreamReader` là wrapper có thể đóng stream nền. Việc còn đăng ký `input` riêng trong header có thể dẫn đến lời gọi đóng lặp trên stream nền. Nhiều stream chuẩn xử lý đóng lặp tương đối an toàn, nhưng **không phải mọi `AutoCloseable` đều bắt buộc có `close()` idempotent**. Nếu wrapper sở hữu hoàn toàn stream nền, thường chỉ cần quản lý wrapper cao nhất theo hợp đồng API. Phần minh họa ở đây nhằm giải thích **phạm vi biến**, không phải khuyến khích đóng hai lần cùng một tài nguyên.

## 3. Biến tài nguyên khai báo trong header là `final` ngầm định

Biến được khai báo như sau:

```java
try (TrackedResource resource = new TrackedResource("r")) {
    resource.work();
    // resource = new TrackedResource("other"); // LỖI biên dịch
}
```

`TrackedResource` là lớp minh họa có `close()` ở phần chương trình đầy đủ bên dưới.

Biến `resource` khai báo trong header là **implicitly final**, nghĩa là Java không cho gán tham chiếu mới cho nó trong thân `try`. Điều này giúp đảm bảo việc đóng tài nguyên không bị phá vỡ bằng cách vô tình thay biến sang một đối tượng khác.

**Tuy nhiên, `final` đối với biến tham chiếu không đồng nghĩa với đối tượng bất biến.** Ta vẫn có thể gọi `resource.work()` hoặc những phương thức thay đổi trạng thái của object nếu loại tài nguyên cho phép. `final` chỉ không cho thay đổi tham chiếu lưu trong biến đó.

Nếu cần sử dụng nhiều tài nguyên khác nhau, hãy khai báo mỗi tài nguyên với một tên riêng hoặc tổ chức những khối `try-with-resources` riêng, thay vì cố gán lại biến header.

## 4. Từ Java 9: dùng tài nguyên đã khai báo bên ngoài `try`

### 4.1. Cú pháp và phạm vi

Nếu đã có một biến tài nguyên `final` hoặc *effectively final* (được khởi tạo và không bị gán lại), từ Java 9 bạn có thể tham chiếu **trực tiếp** trong resource specification:

```java
TrackedResource external = new TrackedResource("external");

try (external) { // Java 9+, vẫn hợp lệ trên Java 17+
    external.work();
}

System.out.println(external.isClosed()); // true trong ví dụ TrackedResource
```

Khác với `try (TrackedResource external = ...)`:

- Biến `external` đã được khai báo **trước `try`**, nên phạm vi của biến vẫn kéo dài đến cuối khối bao ngoài nơi nó được khai báo.
- `try (external)` chỉ đăng ký tham chiếu hiện có làm tài nguyên để đóng tự động; nó **không khai báo một biến mới** mang tên `external`.
- Sau khi kết thúc `try`, **tên `external` vẫn truy cập được**, nhưng tài nguyên **đã bị đóng**. Còn truy cập được tham chiếu **không có nghĩa** có thể tiếp tục đọc/ghi tài nguyên.
- Vì `external` được dùng làm tài nguyên nên Java yêu cầu biến này có kiểu phù hợp với `AutoCloseable`, được gán giá trị trước khi dùng, và là `final` hoặc *effectively final*.

**Effectively final** nghĩa là trong ngữ cảnh này, biến không bị gán lại sau khi khởi tạo, dù không viết từ khóa `final`:

```java
TrackedResource resource = new TrackedResource("one");
try (resource) {
    resource.work();
}
// resource = new TrackedResource("two"); // nếu viết dòng này, biến
// sẽ không còn effectively final và toàn bộ try(resource) không hợp lệ
```

Kể cả nếu phép gán lại nằm **sau** khối `try`, phép gán đó vẫn có thể làm biến không đủ điều kiện *effectively final* khi dùng làm resource trong `try (resource)`. Nếu thực sự phải đổi sang một resource khác, cần thiết kế lại trách nhiệm sở hữu và phạm vi từng tài nguyên.

### 4.2. Trên Java 7/8 phải khai báo biến mới trong header

```java
TrackedResource external = new TrackedResource("external");

try (TrackedResource managed = external) {
    managed.work();
}
// external vẫn nằm trong scope, nhưng đối tượng nó trỏ tới đã bị đóng
```

Đây là cách viết có thể biên dịch từ Java 7, vì header vẫn có **khai báo biến tài nguyên mới** là `managed`. Cú pháp `try (external)` ngắn gọn chỉ xuất hiện từ Java 9. Cả hai cách đều đang được hỗ trợ; không cần dùng một kỹ thuật cũ khi project đã hướng tới Java 17+, nhưng cần phân biệt rõ mốc phiên bản để đọc đúng mã nguồn.

### 4.3. Không thể dùng tùy ý biểu thức trong danh sách tài nguyên

Phần tử trong resource specification là **khai báo biến tài nguyên** hoặc **truy cập biến đã có** (với quy tắc Java 9+). Nó không phải vị trí dành cho mọi biểu thức.

```java
// Hợp lệ:
try (TrackedResource r = openResource()) {
    r.work();
}

// Hợp lệ từ Java 9, nếu existing là final/effectively final:
try (existing) {
    existing.work();
}

// Không hợp lệ:
// try (openResource()) { ... } // không phải một resource declaration hay variable access
```

Những ví dụ này là **minh họa cú pháp trong phương thức** có `openResource()`, `existing` và `TrackedResource` được định nghĩa tương ứng; không phải chương trình chạy độc lập. Nếu muốn quản lý một kết quả trả về từ phương thức, hãy **gán nó cho biến trong header**.

## 5. Tài nguyên nhận giá trị `null`: điều gì thật sự xảy ra?

### 5.1. `null` không được tự động đóng

Theo quy tắc Java, sau khi việc khởi tạo resource specification hoàn tất, `try-with-resources` **chỉ gọi `close()` trên tài nguyên được khởi tạo với giá trị khác `null`**.

```java
try (java.io.InputStream input = null) {
    System.out.println(input == null); // true
}
```

Kết quả in `true`, không có lời gọi `input.close()` và không có `NullPointerException` do bước đóng tài nguyên.

Điều này áp dụng cả cho tài nguyên được **khai báo mới** và tham chiếu **đã có từ trước** trong `try (existing)` ở Java 9+:

```java
java.io.InputStream maybeInput = null;

try (maybeInput) {
    System.out.println("still in try");
}
```

Cú pháp này hợp lệ trên Java 17+ vì `maybeInput` là biến *effectively final*. Dù tham chiếu là `null`, thân `try` **vẫn thực thi bình thường**.

### 5.2. Tham chiếu `null` vẫn gây lỗi nếu bạn sử dụng như một đối tượng

```java
try (java.io.InputStream input = null) {
    input.read(); // ném NullPointerException do gọi read() trên null
}
```

Đây là lỗi **bên trong thân `try`**, không phải lỗi của cơ chế đóng tài nguyên. `try-with-resources` không tự tạo đối tượng thay cho `null`, không kiểm tra rằng resource là hữu dụng, và không thay thế một phép kiểm tra null theo hợp đồng API.

Nếu khối `try` ném `NullPointerException` như trên, cơ chế dọn dẹp vẫn được thực hiện cho **những tài nguyên khác khác `null`** đã được mở thành công; resource `null` đơn giản là không có gì để đóng.

### 5.3. Nhiều tài nguyên với một tham chiếu `null`

```java
try (TrackedResource first = new TrackedResource("first");
     TrackedResource middle = null;
     TrackedResource third = new TrackedResource("third")) {
    first.work();
    third.work();
    System.out.println(middle == null); // true
}
```

Các bước:

1. Tạo `first` và thực hiện constructor (ví dụ in `open first`).
2. Khởi tạo `middle = null`; không có đối tượng để đóng.
3. Tạo `third` và thực hiện constructor (in `open third`).
4. Thực thi **thân `try`** với hai tài nguyên thật; việc `middle` là `null` **không ngăn** phần thân chạy.
5. Khi rời khối, đóng `third` trước, bỏ qua `middle`, rồi đóng `first` sau.

Thứ tự đóng dựa trên **thứ tự khai báo ngược lại**, không dựa trên việc resource có được sử dụng trong thân `try` hay không.

### 5.4. Có nên dùng tài nguyên `null` để biểu diễn "không cần làm gì"?

Chỉ khi API **quy định rõ** rằng không có tài nguyên là trạng thái hợp lệ. Trong nhiều tình huống, dùng `null` như “lỗi mở file” sẽ làm che mất nguyên nhân và đẩy lỗi sang vị trí không liên quan.

Nếu một factory có thể trả `null` theo hợp đồng, hãy xử lý tường minh trước khi sử dụng:

```java
TrackedResource candidate = openOptionalResource();

if (candidate == null) {
    return; // hoặc một nhánh xử lý khác theo yêu cầu nghiệp vụ
}

try (candidate) { // Java 9+
    candidate.work();
}
```

Đây là đoạn **minh họa** trong một phương thức trả `void`, có factory `openOptionalResource()`. Tương đương Java 7/8 có thể viết `try (TrackedResource managed = candidate)`. Khi ứng dụng **không chấp nhận `null`**, kiểm tra sớm bằng `Objects.requireNonNull(...)` với thông điệp rõ nghĩa sẽ giúp phát hiện vi phạm hợp đồng gần vị trí khởi tạo hơn.

## 6. Chương trình đầy đủ Java 17+: quan sát scope và `null`

Tạo tệp **`ResourceScopeNullDemo.java`**:

```java
public final class ResourceScopeNullDemo {

    static final class TrackedResource implements AutoCloseable {
        private final String name;
        private boolean closed;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void work() {
            if (closed) {
                throw new IllegalStateException("resource already closed");
            }
            System.out.println("use " + name);
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        System.out.println("--declared--");

        try (TrackedResource first = new TrackedResource("first");
             TrackedResource middle = null;
             TrackedResource third = new TrackedResource("third")) {
            first.work();
            third.work();
            System.out.println("middleNull=" + (middle == null));
        }

        System.out.println("--existing--");

        TrackedResource external = new TrackedResource("external");
        try (external) {
            external.work();
        }
        System.out.println("externalClosed=" + external.isClosed());

        System.out.println("--null--");

        TrackedResource missing = null;
        try (missing) {
            System.out.println("bodyRuns=" + (missing == null));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac ResourceScopeNullDemo.java
java ResourceScopeNullDemo
```

**Stdout chính xác:**

```text
--declared--
open first
open third
use first
use third
middleNull=true
close third
close first
--existing--
open external
use external
close external
externalClosed=true
--null--
bodyRuns=true
```

### Giải thích kết quả

- Ở phần `--declared--`, chỉ `first` và `third` gọi constructor nên chỉ xuất hiện `open first` và `open third`. Biến `middle` tồn tại trong scope nhưng tham chiếu bằng `null`, không có object nào được mở.
- `middleNull=true` xác nhận thân `try` vẫn chạy dù `middle == null`.
- `close third` xuất hiện trước `close first` đúng quy tắc đóng **ngược thứ tự khởi tạo**. Không có dòng `close middle`.
- Ở phần `--existing--`, biến `external` được khai báo **trước** `try (external)`, nên vẫn dùng được sau khối. Nhưng trạng thái `externalClosed=true` xác nhận object đã bị đóng.
- Ở phần `--null--`, biến `missing` là `null` và không gây lỗi do `try-with-resources`; thân `try` vẫn in `bodyRuns=true`. Không có đối tượng để gọi `close()`.

Chương trình minh họa này dùng `AutoCloseable.close()` không ném checked exception, nên không cần `catch` hoặc `throws`. Trong chương trình thực tế, cần xử lý checked exception do **thao tác trong khối `try`** hoặc do **`close()`** của loại tài nguyên đang dùng.

## 7. Thời điểm đóng, `catch`, `finally` và ngoại lệ

### 7.1. `close()` xảy ra trước `catch`/`finally` của cùng cấu trúc

```java
try (TrackedResource resource = new TrackedResource("r")) {
    resource.work();
} catch (RuntimeException e) {
    System.out.println("Failure: " + e.getMessage());
} finally {
    System.out.println("After resource cleanup");
}
```

Đoạn này là **minh họa trong phương thức** và giả sử `TrackedResource` giống ví dụ đầy đủ. Đối với resource được mở thành công, Java tiến hành đóng tài nguyên khi rời thân `try`, rồi mới tới các handler `catch`/`finally` của cấu trúc này. Tài nguyên cũng được đóng khi thân `try` kết thúc bất thường, trừ những tình huống tiến trình/JVM không thể tiếp tục thực thi thao tác cleanup bình thường (ví dụ bị kết thúc cưỡng bức).

Vì vậy, `finally` không phải nơi để “đợi một lúc rồi đóng lần nữa” với cùng resource; tránh gọi `close()` lặp trừ khi API đảm bảo an toàn và có lý do nghiệp vụ rõ ràng.

### 7.2. Nếu khởi tạo resource thất bại

Nếu nhiều tài nguyên được khởi tạo lần lượt và một initializer ném exception:

- Các tài nguyên **đã khởi tạo thành công trước đó** sẽ được đóng.
- Tài nguyên mà initializer thất bại sẽ không có đối tượng đã được đăng ký để đóng từ lần khởi tạo ấy.
- Các initializer phía sau **không chạy**, và thân `try` cũng không chạy.
- Nếu việc đóng tài nguyên trước đó lại ném lỗi, các lỗi đó có thể được lưu như **suppressed exceptions** trên exception chính.

Cơ chế này giúp tránh rò rỉ những tài nguyên mở trước khi một thao tác mở tài nguyên khác thất bại.

### 7.3. Lỗi trong thân `try` và lỗi trong `close()`

Giả sử khối `try` ném lỗi A rồi `close()` ném lỗi B. Java ưu tiên truyền lỗi A ra ngoài và gắn B qua `A.getSuppressed()`. Nếu không có lỗi A nhưng `close()` lỗi, lỗi khi đóng có thể được ném ra ngoài theo quy tắc `try-with-resources`.

**Trường hợp resource `null` không tạo lỗi `close()`**, vì không có lời gọi `close()` nào. Nhưng `null` **không ngăn** lỗi do những tài nguyên khác hoặc do thân `try`. Nếu muốn xử lý lỗi đúng, hãy ghi log hoặc kiểm tra cả exception chính và các suppressed exceptions thay vì chỉ giữ `getMessage()`.

Ví dụ khái niệm:

```java
try (java.io.InputStream input = null) {
    throw new IllegalStateException("operation failed");
} catch (IllegalStateException e) {
    System.out.println(e.getMessage()); // operation failed
    System.out.println(e.getSuppressed().length); // 0 trong ví dụ này
}
```

Ở đây không có lỗi thứ hai vì `input` là `null` và không có tài nguyên nào khác.

## 8. Scope và lifecycle không phải cùng một khái niệm

| Trường hợp | Biến dùng được ở đâu? | Tài nguyên có được đóng tự động? |
| --- | --- | --- |
| `try (Resource r = open())` | Header từ khai báo sang phải và thân `try` | Có, nếu `r != null` |
| `try (Resource r = null)` | Giống trên | Không gọi `close()` cho `r` |
| `Resource x = open(); try (x)` (Java 9+) | Theo khối bao ngoài nơi `x` được khai báo | Có, nếu `x != null` |
| `Resource x = null; try (x)` (Java 9+) | Theo khối bao ngoài | Không gọi `close()` cho `x` |
| `Resource x = open(); try (Resource r = x)` (Java 7+) | `r` chỉ trong header/thân `try`, `x` còn trong khối ngoài | Đối tượng được quản lý và đóng qua `r` |
| Biến của `try` đã hết scope | Không truy cập được bằng tên biến đó | Việc đóng đã được xử lý theo quy tắc khi rời `try`; scope không phải GC |

**Điểm dễ nhầm:** Nếu khai báo `Resource x` ngoài `try` rồi dùng `try (x)`, sau khối `try` bạn vẫn có thể gọi một phương thức trên `x` về mặt cú pháp, nhưng có thể nhận lỗi ở runtime do **resource đã bị đóng**. Ngược lại, nếu khai báo `r` trong header, compiler không cho dùng tên `r` sau khối, dù object gốc có thể được nơi khác giữ tham chiếu.

## 9. Những lỗi phổ biến

### 9.1. Cho rằng `null` làm `try-with-resources` bỏ qua thân khối

Sai. `try-with-resources` vẫn thực thi thân `try` nếu các initializer hoàn tất bình thường, kể cả khi một hoặc nhiều giá trị resource là `null`. Nó chỉ bỏ qua **lời gọi `close()` tương ứng** với resource `null`.

### 9.2. Cho rằng `null` tự động gây NPE trong phần cleanup

Sai. Java kiểm tra resource có khác `null` trước khi gọi `close()`. `NullPointerException` có thể đến từ **lời gọi trên tham chiếu `null` ở thân `try`** hoặc ở nơi khác, không phải từ thao tác đóng resource `null`.

### 9.3. Cố truy cập biến header trong `catch`, `finally` hoặc phía sau

Sai về phạm vi lexical; code không biên dịch. Nếu cần giữ một **tham chiếu bên ngoài**, khai báo biến ở ngoài; nhưng phải nhớ object vẫn có thể đã được đóng.

### 9.4. Cho rằng `final` ngăn mọi thay đổi của object

Sai. `final` ngăn biến trỏ sang object khác, không làm cho tài nguyên bất biến. `close()` có thể thay đổi trạng thái hoặc giải phóng kết nối/tệp.

### 9.5. Nhầm mốc phiên bản Java 7 và Java 9

`try (Resource r = open())` là cú pháp từ Java 7. `try (existingVariable)` yêu cầu Java 9+ (với biến `final` hoặc *effectively final*). Khi dự án đặt `--release 8`, không được viết biến có sẵn trực tiếp trong header dù chạy bằng JDK mới.

### 9.6. Khai báo ngoài để tiện dùng lại mà quên đã đóng

Giữ được **scope** không kéo dài **lifetime hữu dụng** của tài nguyên. Khi `try (resource)` kết thúc, việc tiếp tục gọi `read()`/`write()` có thể ném exception hoặc cho hành vi tùy contract. Không tái sử dụng resource đã đóng nếu API không cho phép.

### 9.7. Đóng nhiều lần cùng underlying resource

Nếu một wrapper đóng cả underlying stream và stream đó cũng được đăng ký riêng trong cùng header, có thể có hai lời gọi đóng đến cùng underlying resource. `AutoCloseable` **không bắt buộc** `close()` idempotent; hãy xác định **một chủ sở hữu có trách nhiệm đóng** theo hợp đồng API.

### 9.8. Quên rằng `close()` cũng có thể ném exception

`AutoCloseable.close()` có khai báo `throws Exception`; implementer có thể dùng kiểu checked exception hẹp hơn hoặc không ném. Hãy kiểm tra loại resource thực tế, chữ ký `close()` và các exception cần xử lý. Đừng nuốt lỗi đóng và làm mất nguyên nhân chính.

### 9.9. Dùng `try (methodReturningResource())`

Đây không phải resource declaration/variable access hợp lệ. Hãy viết `try (Resource r = methodReturningResource())`. Các biến đã khai báo trước chỉ dùng trực tiếp khi thỏa điều kiện phiên bản và tính `final`/*effectively final*.

## 10. Bài tập tự kiểm tra

**Câu 1.** Trong `try (InputStream in = open()) { ... }`, có thể gọi `in.close()` trong `finally` gắn với `try` này không?  
**Đáp án:** Không gọi bằng **tên `in`** trong `finally` được vì biến header không ở scope đó. Hơn nữa, Java đã tự thực hiện đóng khi rời phần thân `try` nên không nên đóng thủ công lần nữa.

**Câu 2.** `try (InputStream in = null) { System.out.println("X"); }` có in `X` không?  
**Đáp án:** Có. `null` không tự bỏ qua thân `try` và Java không gọi `close()` trên `null`.

**Câu 3.** Nếu một tài nguyên trong danh sách là `null` và hai tài nguyên khác không-null, Java có bỏ đóng cả ba không?  
**Đáp án:** Không. Java bỏ qua đúng tài nguyên `null`, đóng những tài nguyên còn lại theo thứ tự ngược với lúc khởi tạo.

**Câu 4.** `Resource r = open(); try (r) { ... }` hoạt động từ Java nào? Sau đó biến `r` có còn trong scope không?  
**Đáp án:** Java 9+ nếu `r` là `final` hoặc *effectively final*. `r` vẫn trong scope của khối ngoài, nhưng đối tượng đã được đóng khi ra khỏi `try`.

**Câu 5.** Vì sao `try (r)` có thể lỗi biên dịch nếu sau đó xuất hiện `r = openAnother();`?  
**Đáp án:** Vì `r` không còn *effectively final*; điều kiện áp dụng dạng dùng biến có sẵn không thỏa.

**Câu 6.** `try (Resource r = open()) { ... } catch (Exception e) { System.out.println(r); }` hợp lệ không?  
**Đáp án:** Không. `r` được khai báo trong resource specification nên không nằm trong scope của `catch`.

**Câu 7.** Sau `try (existingResource)`, có nên tiếp tục gọi `existingResource.work()` chỉ vì biến vẫn tồn tại không?  
**Đáp án:** Không nên mặc định như vậy. Scope vẫn còn nhưng resource có thể đã đóng, cần tuân thủ lifecycle do API quy định.

## 11. Tóm tắt và tài liệu chính thức

**Cốt lõi:** Trong `try-with-resources`, **phạm vi tên biến** và **trạng thái tài nguyên** là hai vấn đề khác nhau. Biến khai báo trong header chỉ nằm trong header tính từ chỗ khai báo và thân `try`; biến có sẵn sử dụng trực tiếp trong header trên Java 9+ vẫn nằm trong scope ngoài, nhưng object vẫn được đóng. **Giá trị `null` không được đóng và không làm thân `try` tự bỏ qua.** Với nhiều tài nguyên, Java chỉ đóng các đối tượng khác `null` theo **thứ tự ngược**; exception trong cleanup được xử lý theo các quy tắc của `try-with-resources`.

Nguồn chuẩn còn hiệu lực:

- [Java Language Specification 17, `14.20.3 — `try`-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): khởi tạo, đóng ngược thứ tự, bỏ qua giá trị `null`, xử lý exception.
- [Java Language Specification 17, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi biến khai báo trong resource specification.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): giao diện `close()` và hợp đồng về idempotence/exception.
- [Oracle — Java 9 Language Changes: More Concise Try-with-resources](https://docs.oracle.com/javase/9/language/): dùng biến `final` hoặc *effectively final* đã khai báo từ trước.