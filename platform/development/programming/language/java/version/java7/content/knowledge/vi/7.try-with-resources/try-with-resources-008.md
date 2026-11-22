# Java 7 — try-with-resources: Ngoại lệ của phần xử lý và ngoại lệ khi đóng

## Mục tiêu bài học

**Try-with-resources** được đưa vào Java 7 và vẫn là cách tiêu chuẩn để quản lý tài nguyên triển khai `AutoCloseable` trên các JDK hiện đại. Tính năng này không chỉ tự gọi `close()`. Nó còn định nghĩa rõ **ngoại lệ nào là lỗi chính (primary exception)** và **ngoại lệ nào được ghi nhận là lỗi phụ (suppressed exception)** khi **cả phần xử lý lẫn thao tác đóng tài nguyên cùng thất bại**.

Trọng tâm của bài này là phân biệt:

- **Lỗi từ thân `try`:** đọc, ghi, tính toán hoặc xử lý dữ liệu thất bại khi tài nguyên đang được sử dụng.
- **Lỗi từ `close()`:** công việc có thể đã hoàn thành hoặc đã lỗi, nhưng việc đóng/flush/giải phóng tài nguyên lại ném thêm exception.
- **Lỗi chính (primary):** exception tiếp tục được truyền qua đường điều khiển tới `catch`/caller.
- **Lỗi bị suppressed:** exception xảy ra thêm trong lúc dọn dẹp và được gắn vào lỗi chính, xem qua `Throwable.getSuppressed()`.
- **Lỗi lúc khởi tạo tài nguyên:** khai báo tài nguyên thứ hai có thể thất bại trước khi vào thân `try`; các tài nguyên đã mở thành công trước đó vẫn phải được đóng.

Sau bài, bạn sẽ tự dự đoán được exception nào đến caller, thứ tự gọi `close()`, số lượng/thứ tự suppressed exceptions và điều kiện compile-time của checked exceptions. Các ví dụ chạy độc lập trên **JDK 17+** bằng `javac --release 17`; cú pháp và cơ chế được trình bày vẫn còn hiệu lực.

## 1. Bức tranh tổng quát: đóng tài nguyên là một phần của luồng điều khiển

Một tài nguyên có thể là reader, stream, connection hoặc đối tượng tự viết triển khai `AutoCloseable`. Cú pháp tiêu biểu:

```java
try (SomeResource resource = acquire()) {
    process(resource);
}
```

Đây là **mã minh họa**, trong đó `SomeResource`, `acquire`, `process` phải được định nghĩa trong ứng dụng, không phải chương trình độc lập. Khi điều khiển rời `try`, Java thực hiện đóng tài nguyên đã khởi tạo thành công. Việc đóng cũng có thể thất bại.

Hãy nghĩ về hai hoạt động:

```text
Bắt đầu
  |
  v
Khởi tạo resource
  |
  +-- thất bại: đóng resource đã mở trước đó -> chuyển ngoại lệ đi lên
  |
  v
Thực hiện thân try
  |
  +-- hoàn tất bình thường -------+
  |                               |
  +-- ném ngoại lệ thân try ------+
                                  |
                                  v
                              gọi close()
                                  |
                      +-----------+-----------+
                      |                       |
                  đóng OK                  close() lỗi
                      |                       |
                      v                       v
           giữ kết quả/lỗi đang có    chọn primary/suppressed
                      |                       |
                      +-----------+-----------+
                                  |
                                  v
                          catch/finally bên ngoài
                                  |
                                  v
                                 caller
```

Với try-with-resources, thao tác `close()` diễn ra **trước khi** phần `catch`/`finally` gắn với chính câu lệnh try-with-resources đó xử lý kết quả và trước khi phương thức gọi nhận lại kết quả/exception.

**Không nhầm:** `getSuppressed()` không có nghĩa Java “nuốt hẳn” lỗi đóng tài nguyên. Nó **lưu dấu vết ngoại lệ phụ** để lỗi chính không bị mất; người gọi có thể kiểm tra cùng với stack trace.

## 2. Bảng quyết định: ngoại lệ nào trở thành primary?

Với **một tài nguyên** đã mở thành công:

| Thân `try` | `close()` | Kết quả tới `catch`/caller | `getSuppressed()` |
| --- | --- | --- | --- |
| Thành công | Thành công | Hoàn tất bình thường, có thể trả giá trị | Không có exception để kiểm tra |
| Ném `BodyException` | Thành công | `BodyException` là lỗi chính | Rỗng (nếu không có ngoại lệ phụ khác) |
| Thành công | Ném `CloseException` | `CloseException` là lỗi chính | Rỗng trong tình huống đơn giản này |
| Ném `BodyException` | Ném `CloseException` | `BodyException` là lỗi chính | Chứa `CloseException` |
| Khởi tạo tài nguyên đầu tiên lỗi | Chưa tạo được tài nguyên để đóng | Lỗi khởi tạo là lỗi chính | Không tự phát sinh lỗi close cho đối tượng chưa mở xong |

**Thứ tự ưu tiên rất quan trọng:** Khi thân `try` đã ném ngoại lệ `B`, rồi `close()` ném `C`, Java giữ `B` làm lỗi chính và thêm `C` vào tập suppressed của `B`. Đây là khác biệt cốt lõi so với một số cách viết `finally` thủ công có thể làm mất lỗi `B`.

Với **nhiều tài nguyên**, chúng được đóng theo **thứ tự ngược lúc khai báo/khởi tạo**. Nếu thân đã lỗi, mỗi lỗi đóng phát sinh thêm được gắn vào lỗi thân. Nếu thân không lỗi nhưng **nhiều `close()` cùng ném**, lỗi của tài nguyên được đóng trước là primary; lỗi đóng tiếp theo trở thành suppressed.

### 2.1. Ba khái niệm không được đánh đồng

- **Primary exception:** đối tượng đang được truyền đi như lý do chính làm câu lệnh hoàn tất bất thường.
- **Cause:** được truy qua `getCause()`, thường là lỗi gốc được gắn vào một exception *mới* khi dịch/chuyển đổi ngoại lệ.
- **Suppressed:** được truy qua `getSuppressed()`, thường là lỗi phụ xảy ra trong lúc đóng tài nguyên khi đã có lỗi chính.

Ví dụ `throw new ServiceException("failed", e)` tạo **wrapper** mới có `cause=e`. Ngược lại, nếu phần xử lý ném `e` và `close()` ném `c` thì try-with-resources có thể giữ `e` làm primary, gắn `c` vào **suppressed** của `e`. Cause và suppressed phục vụ hai mối quan hệ khác nhau, không thay thế lẫn nhau.

## 3. Chương trình A — Thân `try` lỗi, `close()` cũng lỗi

Đây là ca quan trọng nhất. Ta tạo một resource có `close()` **cố ý** ném checked `IOException`. Trong thân `try`, ta ném unchecked `IllegalStateException` để minh họa lỗi nghiệp vụ. Trong ứng dụng thật, hãy thay resource giả lập bằng resource thực và **không** chủ động tạo lỗi đóng ngoài mục đích kiểm thử.

### Tệp `PrimarySuppressedDemo.java`

```java
import java.io.IOException;

public final class PrimarySuppressedDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("resource:close");
            throw new IOException("close failed");
        }
    }

    static void work() throws IOException {
        try (Resource resource = new Resource()) {
            System.out.println("body:work");
            throw new IllegalStateException("work failed");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (Exception e) {
            System.out.println("primary=" + e.getClass().getSimpleName()
                    + ":" + e.getMessage());
            System.out.println("suppressedCount=" + e.getSuppressed().length);
            for (Throwable extra : e.getSuppressed()) {
                System.out.println("suppressed=" + extra.getClass().getSimpleName()
                        + ":" + extra.getMessage());
            }
        }
    }
}
```

Chạy tại thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 PrimarySuppressedDemo.java
java PrimarySuppressedDemo
```

**Output chính xác:**

```text
body:work
resource:close
primary=IllegalStateException:work failed
suppressedCount=1
suppressed=IOException:close failed
```

### 3.1. Phân tích theo thứ tự dòng chạy

1. `new Resource()` khởi tạo thành công. Chưa có ngoại lệ.
2. Thân `try` in `body:work`, sau đó ném `IllegalStateException("work failed")`.
3. Java bắt đầu đóng resource, gọi `Resource.close()`, in `resource:close`, rồi `close()` ném `IOException("close failed")`.
4. Lỗi trong thân `try` **vẫn là primary**: `IllegalStateException("work failed")`.
5. `IOException` do `close()` được gắn vào `getSuppressed()` của primary, không tự thay thế primary ở ca này.
6. `main` bắt exception chính trong `catch (Exception e)` và in loại, message cùng danh sách suppressed.
7. Không có lệnh bình thường nào sau `throw new IllegalStateException(...)` trong thân `try` được thực hiện.

Sơ đồ:

```text
body: IllegalStateException("work failed")
  |
  |  close() -> IOException("close failed")
  |              |
  |              +-- addSuppressed(...) vào lỗi body
  v
caller catches IllegalStateException
  +-- getSuppressed()[0] == IOException("close failed")
```

**Điểm thiết kế:** `catch (Exception e)` trong chương trình demo chỉ để **quan sát kết quả của cả lỗi checked và unchecked**. Trong ứng dụng thật, nên chọn kiểu exception và boundary xử lý cụ thể hơn; không bắt quá rộng rồi coi mọi lỗi như nhau.

### 3.2. Vì sao `work() throws IOException` dù đường thử này ném `IllegalStateException`?

`Resource.close()` khai báo `throws IOException`. Theo phân tích checked exception của Java, có đường đi mà thân `try` hoàn tất bình thường rồi `close()` ném `IOException`. Do đó `work()` phải **bắt hoặc khai báo** checked `IOException`, kể cả khi lần chạy minh họa hiện tại luôn ném unchecked exception từ thân.

Điều kiện `throws` là thuộc **hợp đồng tại thời điểm biên dịch**, không phải kết luận dựa trên một output runtime. Cùng một chữ ký có thể có nhiều đường đi, và compiler phải xét các checked exceptions có thể thoát khỏi toàn bộ câu lệnh.

## 4. Chương trình B — Thân xử lý thành công nhưng đóng lỗi

Trong tình huống này, công việc đã tính ra kết quả, nhưng thao tác đóng không hoàn tất. Nếu không có lỗi trước đó, ngoại lệ của `close()` trở thành **primary**, không phải suppressed.

Đặc biệt: một câu lệnh `return` nằm trong thân `try` **không bảo đảm caller đã nhận được giá trị**, vì `close()` vẫn phải chạy trước khi phương thức thực sự hoàn tất bằng giá trị ấy.

### Tệp `CloseOnlyDemo.java`

```java
import java.io.IOException;

public final class CloseOnlyDemo {
    static final class Resource implements AutoCloseable {
        private final boolean fail;

        Resource(boolean fail) {
            this.fail = fail;
        }

        @Override
        public void close() throws IOException {
            System.out.println(fail ? "close:fail" : "close:ok");
            if (fail) {
                throw new IOException("close failed");
            }
        }
    }

    static String work(boolean failClose) throws IOException {
        try (Resource resource = new Resource(failClose)) {
            System.out.println("body:success");
            return "READY";
        }
    }

    public static void main(String[] args) {
        for (boolean failClose : new boolean[]{false, true}) {
            System.out.println(failClose ? "case:close-fail" : "case:ok");
            try {
                System.out.println("caller:value=" + work(failClose));
            } catch (IOException e) {
                System.out.println("caller:primary=" + e.getClass().getSimpleName()
                        + ":" + e.getMessage());
                System.out.println("caller:suppressed=" + e.getSuppressed().length);
            }
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 CloseOnlyDemo.java
java CloseOnlyDemo
```

Output:

```text
case:ok
body:success
close:ok
caller:value=READY
case:close-fail
body:success
close:fail
caller:primary=IOException:close failed
caller:suppressed=0
```

### 4.1. Vì sao không thấy `caller:value=READY` ở ca đóng lỗi?

- Java đánh giá biểu thức `return "READY"` và chuẩn bị thoát thân `try`.
- Trước khi giá trị được chuyển tới caller, try-with-resources gọi `close()`.
- `close()` ném `IOException`; phương thức `work` **hoàn tất bất thường** thay vì trả `READY`.
- Vì lúc ấy chưa có lỗi khác đang được truyền đi, chính `IOException` là primary và `getSuppressed()` rỗng.

Không nên coi `body:success` đồng nghĩa **toàn bộ thao tác thành công**. Với một số resource, `close()` có thể flush/commit dữ liệu đệm hoặc thực hiện bước kết thúc quan trọng; thất bại trong đó có thể khiến kết quả không hợp lệ dù body đã in “success”.

Tuy nhiên, **không phải mọi resource đều flush/commit khi close**. Hành vi cụ thể phải đọc hợp đồng của implementation đang dùng; đừng suy rằng đóng thất bại chắc chắn làm hỏng dữ liệu hoặc chắc chắn không quan trọng. Đây là lý do caller phải có chính sách riêng cho close failure.

### 4.2. Khi nào trả kết quả trước khi đóng là nguy hiểm?

Nếu method trả một `InputStream` vừa được tạo **và đóng ngay trong try-with-resources**, caller có thể nhận stream đã đóng. Ngược lại, nếu muốn caller sử dụng stream sau khi return, thường caller phải là chủ sở hữu chịu trách nhiệm đóng stream; method không nên đóng nó trước khi giao.

Bài này không đề xuất chuyển quyền sở hữu resource một cách tùy tiện. Nó nhấn mạnh **resource ownership** phải rõ: ai mở, ai đóng, object nào còn được sử dụng sau khi return, và liệu đóng có thể ném exception không.

## 5. Chương trình C — Nhiều tài nguyên: thứ tự đóng ngược và thứ tự suppressed

Khi khai báo nhiều tài nguyên:

```java
try (Resource first = new Resource("first");
        Resource second = new Resource("second")) {
    // Thân xử lý.
}
```

Đây là đoạn cú pháp minh họa nằm trong phương thức có lớp `Resource` phù hợp. Java khởi tạo từ **trái sang phải**: `first` rồi `second`. Khi rời `try`, Java đóng từ **phải sang trái**: `second.close()` rồi `first.close()`.

Điều này có ý nghĩa khi tài nguyên có quan hệ phụ thuộc (ví dụ wrapper nằm ngoài một stream gốc). Thứ tự đóng là một phần ngữ nghĩa ngôn ngữ và không nên đảo khai báo một cách tùy tiện.

### Tệp `MultiResourceDemo.java`

```java
import java.io.IOException;

public final class MultiResourceDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close " + name + " failed");
        }
    }

    static void work(boolean failBody) throws IOException {
        try (Resource first = new Resource("first");
                Resource second = new Resource("second")) {
            System.out.println(failBody ? "body:fail" : "body:ok");
            if (failBody) {
                throw new IllegalArgumentException("body failed");
            }
        }
    }

    public static void main(String[] args) {
        for (boolean failBody : new boolean[]{true, false}) {
            System.out.println(failBody ? "case:body-fail" : "case:close-only");
            try {
                work(failBody);
            } catch (Exception e) {
                System.out.println("primary=" + e.getClass().getSimpleName()
                        + ":" + e.getMessage());
                for (Throwable suppressed : e.getSuppressed()) {
                    System.out.println("suppressed="
                            + suppressed.getClass().getSimpleName()
                            + ":" + suppressed.getMessage());
                }
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MultiResourceDemo.java
java MultiResourceDemo
```

Output chính xác:

```text
case:body-fail
open:first
open:second
body:fail
close:second
close:first
primary=IllegalArgumentException:body failed
suppressed=IOException:close second failed
suppressed=IOException:close first failed
case:close-only
open:first
open:second
body:ok
close:second
close:first
primary=IOException:close second failed
suppressed=IOException:close first failed
```

### 5.1. Lần thứ nhất: thân lỗi và cả hai lần đóng lỗi

- `first` và `second` được tạo theo thứ tự khai báo.
- Thân ném `IllegalArgumentException("body failed")`.
- `second.close()` chạy trước, ném `IOException("close second failed")`; exception này được suppress vào lỗi body.
- `first.close()` chạy sau, ném `IOException("close first failed")`; exception này cũng được suppress vào lỗi body.
- Caller nhận primary là `IllegalArgumentException("body failed")` với **hai suppressed exceptions**, theo thứ tự được thêm: `second` rồi `first`.

Ở đây “hai lỗi đóng” không làm mất lỗi body. Không nên chỉ in `e.getMessage()` rồi kết luận toàn bộ câu chuyện lỗi đã được thấy; danh sách suppressed cung cấp bằng chứng bổ sung quan trọng.

### 5.2. Lần thứ hai: thân bình thường nhưng cả hai lần đóng lỗi

- Thân in `body:ok` và kết thúc bình thường.
- `second.close()` chạy **đầu tiên** trong chuỗi đóng và ném `IOException("close second failed")`. Do chưa có lỗi trước đó, exception này trở thành **primary**.
- Java vẫn cố gọi `first.close()`. Exception từ `first` trở thành **suppressed** của primary `second`.
- Caller nhận `IOException("close second failed")` và một suppressed `IOException("close first failed")`.

Không có chuyện Java bỏ qua việc đóng `first` chỉ vì `second.close()` ném lỗi. Try-with-resources vẫn thực hiện quy tắc đóng các tài nguyên đã khởi tạo thành công.

### 5.3. Quy tắc suy luận khi có N tài nguyên

Với `r1, r2, ..., rN`, thứ tự đóng là `rN, ..., r2, r1`. Nếu body đã ném lỗi, lỗi body là primary; các lỗi `close()` phát sinh thêm trên đường đóng có thể được gắn vào primary. Nếu body bình thường, **lỗi đóng đầu tiên phát sinh trong thứ tự thực thi đóng** là primary; các lỗi đóng sau được suppress vào primary đó.

Vì vậy, câu “lỗi của resource khai báo đầu tiên luôn là primary” là **sai**. Cần đi theo **đường chạy thực tế**, không dựa vào vị trí khai báo mà bỏ qua thứ tự đóng.

## 6. Chương trình D — Khởi tạo tài nguyên thứ hai thất bại

Một ngoại lệ có thể xảy ra **trước khi chương trình bước vào thân `try`**: constructor/factory tạo tài nguyên thứ hai có thể lỗi. Java vẫn đóng các tài nguyên khai báo trước đó **đã khởi tạo thành công**.

### Tệp `InitFailureDemo.java`

```java
import java.io.IOException;

public final class InitFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name, boolean failOpen) throws IOException {
            this.name = name;
            System.out.println("open:" + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close " + name + " failed");
        }
    }

    static void work() throws IOException {
        try (Resource first = new Resource("first", false);
                Resource second = new Resource("second", true)) {
            System.out.println("body:unreachable");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IOException e) {
            System.out.println("primary=" + e.getClass().getSimpleName()
                    + ":" + e.getMessage());
            for (Throwable extra : e.getSuppressed()) {
                System.out.println("suppressed="
                        + extra.getClass().getSimpleName()
                        + ":" + extra.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InitFailureDemo.java
java InitFailureDemo
```

Output:

```text
open:first
open:second
close:first
primary=IOException:open second failed
suppressed=IOException:close first failed
```

### 6.1. Điều gì đã xảy ra?

1. Constructor của `first` hoàn tất, nên `first` là resource hợp lệ phải được đóng.
2. Constructor của `second` in `open:second` rồi ném `IOException("open second failed")`. Không có `second` được khởi tạo thành công để try-with-resources gọi `close()`.
3. Thân `try` không bắt đầu, vì vậy không in `body:unreachable`.
4. Java đóng `first`. Lần đóng ấy ném `IOException("close first failed")`.
5. Ngoại lệ khởi tạo `second` vẫn là **primary**, còn lỗi đóng `first` được lưu thành **suppressed**.

Đây là ca cần test khi một operation khởi tạo nhiều resource theo chuỗi, ví dụ file + decoder + database stream. Đừng nghĩ rằng resource chưa vào thân `try` thì mọi thứ chưa cần cleanup.

**Ranh giới trách nhiệm:** Nếu constructor/factory của `second` đã cấp phát một số tài nguyên nội bộ rồi ném exception **trước khi trả về một object hợp lệ**, try-with-resources không thể tự gọi `close()` trên object chưa được tạo thành công. Chính constructor/factory phải quản lý tài nguyên nội bộ phát sinh trong quá trình khởi tạo thất bại.

## 7. `try-with-resources` so với `try/finally` thủ công

Trước khi có cơ chế quản lý resource của `try-with-resources`, có thể tự gọi `close()` trong `finally`. Cách viết thủ công rất dễ làm mất ngoại lệ quan trọng:

```java
try {
    throw new IllegalStateException("work failed");
} finally {
    throw new java.io.IOException("close failed");
}
```

Đây là **mã minh họa có chủ ý sai về chính sách xử lý**, không phải lớp độc lập. Khi `finally` tự ném `IOException`, nó có thể thay thế ngoại lệ `IllegalStateException` đang được truyền đi. Lỗi từ body bị che khuất nếu không có mã bổ sung bảo toàn nó.

Còn với try-with-resources, Java định nghĩa quy tắc primary/suppressed để tránh mất lỗi body trong ca đóng resource thất bại:

```java
try (Resource resource = acquire()) {
    doWork(resource);
}
```

Đoạn này không biên dịch độc lập vì cần định nghĩa `Resource`, `acquire` và `doWork`, nhưng mô tả cơ chế đang được dùng. Trong code thật, **ưu tiên `try-with-resources`** khi bạn sở hữu một resource triển khai `AutoCloseable` và muốn đóng nó trong phạm vi đã xác định.

**Lưu ý:** `finally` không bị loại bỏ khỏi Java và vẫn hữu ích cho cleanup phi-resource hoặc điều khiển tương ứng. Vấn đề ở đây là **tránh viết `close()` thủ công gây thay đổi đường đi exception**, không phải nói rằng mọi `finally` đều sai.

### 7.1. `catch` và `finally` ở đâu so với `close()`?

```java
try (Resource resource = acquire()) {
    doWork(resource);
} catch (IOException e) {
    handleIo(e);
} finally {
    afterAttempt();
}
```

Đây là đoạn minh họa cần các hàm/lớp được định nghĩa ở ứng dụng, không phải chương trình độc lập. Trong cấu trúc này:

1. Thân `try` chạy hoặc lỗi.
2. Java gọi `close()` trên các resource đã mở hợp lệ.
3. Sau đó handler `catch` của chính try-with-resources (nếu có và phù hợp) nhận **exception chính sau khi đóng**; nó có thể đọc `getSuppressed()`.
4. `finally` gắn với câu lệnh cũng thực thi theo quy tắc chuyển điều khiển.
5. Caller nhận kết quả hoặc exception còn tiếp tục được ném ra.

Đừng giả định `catch` sẽ chạy *trước khi resource được đóng*. Điều đó dẫn đến việc debug thiếu chính xác: `catch` có thể nhận ngoại lệ mà danh sách suppressed đã được gắn đầy đủ.

### 7.2. Có nên `close()` thêm một lần trong `finally`?

Không nên gọi `close()` lần hai chỉ vì quên rằng try-with-resources **đã đóng** resource. Không phải tất cả các implementation của `AutoCloseable` đều bảo đảm gọi `close()` nhiều lần có cùng hiệu quả. Đóng lặp có thể gây lỗi, làm nhiễu log hoặc sai hợp đồng resource.

Đừng nhầm “tài nguyên cần đóng” với “mọi object phải đóng ngay khi rời một method”. Hãy xác định rõ **ownership và lifetime** trước khi đặt resource vào header của try-with-resources.

## 8. Checked exceptions và hợp đồng của `AutoCloseable.close()`

Một tình huống phổ biến: thân `try` không ném checked exception, nhưng `close()` có thể ném. Compiler vẫn xem lời gọi đóng như **nguồn checked exception**.

```java
static final class Resource implements AutoCloseable {
    @Override
    public void close() throws java.io.IOException {
        throw new java.io.IOException("close failed");
    }
}
```

Đoạn trên là một **lớp lồng minh họa**, có thể đặt trong một lớp Java khác. Nếu viết phương thức:

```java
static void work() {
    try (Resource resource = new Resource()) {
        System.out.println("body ok");
    }
}
```

thì đó là **ví dụ cố ý thiếu xử lý ngoại lệ**, sẽ không biên dịch vì `Resource.close()` khai báo checked `IOException` nhưng `work()` không `catch` và cũng không `throws IOException`.

Hai cách đúng nếu hợp đồng API cho phép:

```java
// Cách A: cho checked exception lan tới caller.
static void work() throws java.io.IOException {
    try (Resource resource = new Resource()) {
        System.out.println("body ok");
    }
}
```

```java
// Cách B: xử lý ở boundary hiện tại.
static void work() {
    try (Resource resource = new Resource()) {
        System.out.println("body ok");
    } catch (java.io.IOException e) {
        System.out.println("close or body failed: " + e.getMessage());
    }
}
```

Các đoạn là **phương thức minh họa đặt trong lớp có `Resource` ở trên**; chúng là hai phương án thay thế, không đặt cùng signature `work()` trong một lớp.

- `AutoCloseable.close()` ở interface gốc có thể khai báo `throws Exception`. Nhiều lớp cụ thể thu hẹp loại checked exception; ví dụ `java.io.Closeable.close()` khai báo `throws IOException`.
- Compiler xét **kiểu tĩnh và chữ ký `close()`** của resource khi kiểm tra checked exceptions.
- Một method không tự trở thành hợp lệ chỉ vì thực tế lần chạy không làm `close()` thất bại.
- Khi có hai resource với các checked exception khác nhau, chữ ký `throws` hoặc cách catch phải xét **cả các đường đóng**, cùng ngoại lệ từ body và khởi tạo.
- Nếu code chuyển ngoại lệ thành một domain exception, đừng giấu lỗi đóng không phù hợp; wrapper nên giữ cause của primary, còn suppressed exceptions vẫn có thể nằm trên primary đó.

### 8.1. Ba negative compile tests nên thực hiện

Tạo các file tối giản riêng để quan sát compiler từ chối:

1. **Bỏ `throws IOException`** khi `close()` có thể ném checked `IOException` và không có catch phù hợp — `javac` báo unreported exception.
2. **Dùng một `String` làm resource**: `try (String s = "x") { ... }` — không hợp lệ vì `String` không triển khai `AutoCloseable`.
3. **Chỉ catch `IllegalStateException`** trong khi `close()` có thể ném checked `IOException` — không đủ để xử lý checked failure của `close()`.

Có thể lưu ví dụ độc lập tối thiểu sau dưới tên `BadCloseContract.java`:

```java
import java.io.IOException;

public final class BadCloseContract {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void run() {
        try (Resource resource = new Resource()) {
            System.out.println("body done");
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BadCloseContract.java
```

**Kỳ vọng:** compiler thất bại; `run()` chưa bắt hoặc khai báo ngoại lệ `IOException` của `close()`. Đây là **test cố ý sai**, không phải mã đưa vào sản phẩm. Sửa bằng cách khai báo `static void run() throws IOException` hoặc catch/translate theo chính sách thật sự cần.

## 9. Cách chẩn đoán: xem primary, cause và suppressed đúng thứ tự

Để debug một thất bại có liên quan resource, có thể lấy thông tin an toàn tại boundary:

```java
static void report(Throwable failure) {
    System.out.println("primary=" + failure.getClass().getSimpleName());
    System.out.println("message=" + failure.getMessage());

    if (failure.getCause() != null) {
        System.out.println("cause=" + failure.getCause().getClass().getSimpleName());
    }

    for (Throwable extra : failure.getSuppressed()) {
        System.out.println("suppressed=" + extra.getClass().getSimpleName()
                + ":" + extra.getMessage());
    }
}
```

Đây là **phương thức minh họa** để đưa vào một lớp Java, không phải chương trình độc lập. Mẫu trên chỉ in thông tin ngắn để học. Hệ thống thật nên dùng cơ chế logging/tracing có kiểm soát, phù hợp quy định bảo vệ dữ liệu và không log trùng cùng lỗi ở mọi tầng.

### 9.1. Kiểm tra theo thứ tự nào?

1. **Loại exception chính** (`getClass()`): là lỗi xử lý hay lỗi đóng?
2. **Message và stack trace** của primary: lỗi xảy ra ở body, constructor hay close?
3. **Cause chain** (`getCause()`): primary có phải domain wrapper của lỗi khác không?
4. **Suppressed exceptions** (`getSuppressed()`): đóng tài nguyên hoặc các bước cleanup bổ sung có thất bại không? Theo thứ tự nào?
5. **Tình trạng thao tác**: body có hoàn tất bình thường nhưng close lỗi không? Có side effect nào đã xảy ra trước khi exception ra tới caller?
6. **Hợp đồng API**: caller cần retry, báo lỗi nhập liệu, rollback hay chuyển trạng thái?
7. **Ranh giới log**: tránh cùng một primary/cause/suppressed bị log lặp vô ích ở nhiều tầng.

Khi dùng phương thức logger hoặc `Throwable.printStackTrace()`, Java thường hiển thị thông tin suppressed trong stack trace. Tuy nhiên, một hệ thống log tùy chỉnh chỉ ghi `e.getMessage()` có thể bỏ sót chúng; nếu nghiệp vụ cần chẩn đoán, hãy kiểm tra logger thực sự thu thập đầy đủ cấu trúc exception.

### 9.2. Điều gì xảy ra khi wrap primary?

Ví dụ:

```java
catch (java.io.IOException e) {
    throw new IllegalStateException("cannot finish operation", e);
}
```

Đây là mảnh code minh họa đặt sau một `try` và cần bối cảnh phù hợp. Nếu `e` là primary có suppressed exceptions do đóng resource, wrapper mới có `cause=e`. Caller phải xem cả **wrapper cause chain** lẫn `e.getSuppressed()`; không suy rằng suppressed đã tự chuyển hết lên mảng suppressed của wrapper.

Đừng chủ động xóa cause/suppressed chỉ để có thông điệp ngắn hơn. Cũng không nên trả toàn bộ stack trace trực tiếp ra API công khai, vì có thể tiết lộ đường dẫn hoặc cấu trúc hệ thống.

## 10. Kịch bản thực tế và cách ra quyết định

### 10.1. Đọc tệp với `Files.newBufferedReader`

Khi đọc file, pattern hiện đại:

```java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
    String firstLine = reader.readLine();
    process(firstLine);
}
```

Đây là **mã minh họa** cần biến `path` kiểu `Path` và hàm `process` đã được định nghĩa. Resource `BufferedReader` được tự động đóng sau khi thân `try` kết thúc, kể cả khi `readLine()` hoặc `process()` ném lỗi. Nếu có lỗi I/O từ việc đóng, nó được xử lý theo quy tắc primary/suppressed của try-with-resources.

Hợp đồng caller cần làm rõ: nếu body parse sai dữ liệu, đóng cũng lỗi, caller có cần cả hai thông tin không? Trong phần lớn trường hợp, giữ lỗi parse/body là chính, đồng thời không đánh mất close failure để hỗ trợ chẩn đoán.

### 10.2. Ghi tệp hoặc ghi dữ liệu có bộ đệm

Với các resource buffered, thao tác `close()` có thể tham gia flush dữ liệu, và `close()` thất bại có thể là lỗi quan trọng. Khi body đã “ghi xong” nhưng close lỗi, không tự động coi giao dịch thành công. Tuy nhiên, semantics chính xác phụ thuộc implementation, filesystem hoặc giao thức. Cần test với resource/adapter thật và hợp đồng đảm bảo ghi.

### 10.3. Kết nối hoặc transaction

Không nên đánh đồng `close()` với `commit()`. Nhiều API quản lý transaction có quy tắc commit/rollback riêng. Dùng try-with-resources để quản lý vòng đời resource, còn quyết định commit/rollback phải tuân theo hợp đồng của transaction API. Một exception từ close không tự xác nhận rằng dữ liệu đã rollback; cần chính sách nhất quán của tầng dữ liệu.

### 10.4. Resource được sở hữu bởi caller

Nếu phương thức nhận vào stream do caller mở và caller vẫn phải dùng nó sau lời gọi, không tùy tiện đặt stream đó vào try-with-resources của callee rồi đóng trước khi trả điều khiển. Phải xác định ai sở hữu và ai chịu trách nhiệm đóng. Bài này tập trung vào **ngoại lệ phát sinh khi đóng những resource mà khối try sở hữu**.

## 11. Những lỗi thường gặp

### 11.1. Chỉ in exception chính, bỏ qua suppressed

```java
catch (Exception e) {
    System.out.println(e.getMessage());
}
```

Trong tình huống body và close đều lỗi, dòng trên chỉ cho thấy primary message. Lỗi đóng vẫn nằm trong `getSuppressed()` nhưng không được trình bày. Khi cần chẩn đoán đầy đủ, dùng logging có stack trace hoặc truy danh sách suppressed.

### 11.2. Cho rằng lỗi `close()` luôn là suppressed

Sai. Nếu body bình thường và `close()` lỗi, **lỗi đóng là primary**. Nếu nhiều close lỗi nhưng body bình thường, **lỗi close phát sinh đầu tiên khi đóng theo thứ tự ngược** là primary và các lỗi sau có thể thành suppressed. Hãy đọc bảng tình huống, không áp dụng một câu ghi nhớ chung cho mọi ca.

### 11.3. Cho rằng lỗi trong body sẽ làm Java bỏ qua việc đóng

Sai. Try-with-resources vẫn đóng các resource đã được khởi tạo thành công, kể cả body ném lỗi. Đây là lợi ích chính của cơ chế. Với nhiều resource, chúng được đóng theo thứ tự ngược.

### 11.4. Quên trường hợp constructor thứ hai lỗi

Body chưa chạy không có nghĩa không cần cleanup. Tài nguyên thứ nhất đã mở vẫn được đóng. Đồng thời, resource có constructor lỗi trước khi trả về **không được xem là đã khởi tạo thành công** để try-with-resources tự gọi close.

### 11.5. Catch rộng rồi trả success giả

```java
catch (Exception e) {
    return "SUCCESS";
}
```

Nếu body hoặc close thất bại theo hợp đồng quan trọng, việc trả success có thể che giấu dữ liệu chưa được ghi hoặc tài nguyên không hoàn tất. Chỉ coi thất bại là một trạng thái có thể phục hồi khi nghiệp vụ cho phép và có kiểm chứng.

### 11.6. Đóng resource thủ công một lần nữa

Đặt tài nguyên vào try-with-resources rồi gọi `close()` thêm từ `finally` không phải biện pháp “an toàn hơn”. Tính idempotent của close phụ thuộc implementation; đóng trùng có thể tạo thêm exception hoặc làm trạng thái không rõ.

### 11.7. Gộp cause và suppressed làm một

`getCause()` biểu diễn mối quan hệ nguyên nhân, thường do tạo wrapper; `getSuppressed()` biểu diễn những exception phụ bị giữ lại khi đã có primary. Một exception có thể vừa có cause vừa có suppressed. Không chỉ đọc một trong hai rồi coi đã thấy tất cả.

### 11.8. Bỏ qua checked exception của `close()`

`AutoCloseable.close()` hoặc implementation của nó có thể khai báo checked exceptions. Khi `try`/`close` có thể để lỗi ấy thoát ra, phương thức phải **bắt hoặc khai báo**. Chương trình có body toàn `println` vẫn có thể cần `throws IOException` nếu `close()` khai báo loại đó.

### 11.9. Cho rằng suppressed exceptions bảo đảm việc cleanup đã thành công

Nếu thấy một suppressed exception, ít nhất một bước cleanup đã **thất bại**. Việc Java tiếp tục gọi `close()` cho tài nguyên khác không đồng nghĩa mọi resource đều được giải phóng hoàn hảo. Cần xem hợp đồng thực tế của từng resource, theo dõi và có phương án vận hành.

### 11.10. Log quá nhiều hoặc tiết lộ dữ liệu nhạy cảm

Không log message/stack trace ở tất cả tầng và cũng không đổ toàn bộ thông tin lỗi cho người dùng cuối. Chọn boundary chịu trách nhiệm quan sát một sự cố, giữ bằng chứng primary/cause/suppressed để chẩn đoán theo chính sách bảo mật.

## 12. Ma trận test có thể tái sử dụng

Bốn chương trình của bài dùng resource giả lập có kết quả tất định. Hãy kiểm tra bằng `javac --release 17` và quan sát theo ma trận sau:

| Chương trình/đường đi | Thân xử lý | Đóng tài nguyên | Primary | Suppressed |
| --- | --- | --- | --- | --- |
| `PrimarySuppressedDemo` | `IllegalStateException("work failed")` | `IOException("close failed")` | `IllegalStateException` | Một `IOException` |
| `CloseOnlyDemo` / `case:ok` | `return "READY"` | Đóng thành công | Không có | Không áp dụng |
| `CloseOnlyDemo` / `case:close-fail` | `return "READY"` đã được chuẩn bị | Đóng ném `IOException` | `IOException` | Rỗng |
| `MultiResourceDemo` / `body-fail` | `IllegalArgumentException("body failed")` | `second` rồi `first` đều lỗi | `IllegalArgumentException` | Hai `IOException` theo thứ tự `second`, `first` |
| `MultiResourceDemo` / `close-only` | Bình thường | `second` rồi `first` đều lỗi | `IOException("close second failed")` | `IOException("close first failed")` |
| `InitFailureDemo` | Không chạy | Chỉ `first` được đóng và đóng lỗi | `IOException("open second failed")` | `IOException("close first failed")` |

### 12.1. Checklist test khi đưa vào codebase

- [ ] Có test đường body thành công và close thành công.
- [ ] Có test body lỗi, close thành công.
- [ ] Có test body thành công nhưng close lỗi.
- [ ] Có test body lỗi đồng thời close lỗi, kiểm tra đúng primary và suppressed.
- [ ] Với nhiều resource: kiểm tra thứ tự mở, thứ tự đóng và thứ tự suppressed.
- [ ] Có test khởi tạo tài nguyên sau thất bại khi tài nguyên trước đã mở.
- [ ] Kiểm tra chữ ký `throws`/checked exceptions của constructor, body và `close()`.
- [ ] Kiểm tra giá trị trả về không được giao cho caller nếu close buộc method hoàn tất bất thường.
- [ ] Kiểm tra response/rollback/logging đúng hợp đồng khi xảy ra lỗi đóng.
- [ ] Với resource có trạng thái hoặc side effect thực: test bằng implementation thật hoặc test double phản ánh đúng contract.

### 12.2. Bài tập tự luyện

**Bài 1 — Dự đoán output:** Trong `PrimarySuppressedDemo`, cho thân `try` hoàn tất bình thường nhưng giữ nguyên `close()` lỗi. Loại exception chính và độ dài `getSuppressed()` sẽ là gì? Đối chiếu với `CloseOnlyDemo`.

**Bài 2 — Đảo thứ tự tài nguyên:** Trong `MultiResourceDemo`, đảo `first` và `second` ở phần khai báo (nhưng vẫn giữ tên và cách tạo). Thứ tự in `close:...` và thứ tự suppressed thay đổi thế nào? Không thay đổi logic body khi so sánh.

**Bài 3 — Bỏ lỗi body:** Với `MultiResourceDemo`, dùng `failBody=false`. Vì sao `IOException("close second failed")` là primary, còn lỗi close của `first` bị suppressed?

**Bài 4 — Khởi tạo thất bại:** Sửa `InitFailureDemo` để constructor của `first` lỗi ngay. Đoán liệu `close:first` có được in không. Phân biệt cleanup do try-with-resources thực hiện với cleanup nội bộ mà constructor phải tự quản lý.

**Bài 5 — Hợp đồng compile-time:** Tạo `BadCloseContract.java` và quan sát lỗi compiler. Sửa theo hai phương án: `throws IOException` hoặc `catch IOException`. Khi nào chọn một trong hai theo hợp đồng caller?

**Bài 6 — Cause và suppressed:** Bắt `IOException` do close rồi tạo wrapper `new IllegalStateException("failed", e)`. Kiểm tra `wrapper.getCause() == e` và `e.getSuppressed()`. Có nên kỳ vọng `wrapper.getSuppressed()` tự chứa danh sách của `e` không?

**Bài 7 — Audit luồng:** Thiết kế một bộ đọc file vừa có thể ném lỗi parsing vừa có thể gặp lỗi đóng. Xác định lỗi nào là primary, lỗi nào là suppressed, API sẽ báo thông tin gì và tầng nào chịu trách nhiệm log.

## Tài liệu tham khảo chính thức (kiến thức còn hiệu lực)

- [Java Language Specification 17 — `14.20.3 Try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): ngữ nghĩa khởi tạo, đóng, thứ tự và suppressed exceptions.
- [Java Language Specification 17 — `14.20 Try Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): tương tác với `catch` và `finally`, abrupt completion.
- [Java SE 17 — `AutoCloseable` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`.
- [Java SE 17 — `Throwable` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `addSuppressed()`, `getCause()`.
- [Java SE 17 — `Closeable` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): subtype của `AutoCloseable` với chữ ký close của nhóm I/O.

**Ghi nhớ:** Khi body và `close()` cùng thất bại, try-with-resources thường giữ **lỗi body làm primary** và gắn **lỗi close vào suppressed**. Khi body bình thường, **lỗi close trở thành primary**. Với nhiều tài nguyên, đóng từ **phải sang trái**; với khởi tạo thất bại, các tài nguyên đã mở thành công trước đó vẫn được đóng. Muốn xử lý đúng, hãy kiểm tra **đường đi thực tế, chữ ký checked exception, primary, cause và suppressed**, không chỉ dòng log đầu tiên.