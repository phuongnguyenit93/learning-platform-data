# Ngoại lệ từ thân `try`, `close()` và nguyên tắc chọn ngoại lệ chính trong Java

Một tài nguyên có thể thất bại **khi khởi tạo**, **khi được sử dụng trong thân `try`** hoặc **khi `close()` được gọi**. Nếu hai hoặc nhiều lỗi cùng xuất hiện trong một câu lệnh `try-with-resources`, Java không chỉ chọn một lỗi để ném ra rồi bỏ mọi lỗi còn lại: ngôn ngữ có quy tắc xác định **ngoại lệ chính** (*primary exception*) và ghi các ngoại lệ phụ vào danh sách **suppressed exceptions**.

Đây là điểm khác biệt rất quan trọng so với việc tự viết `resource.close()` trong `finally`: với `try-finally` thủ công, một lỗi ném từ `finally` có thể thay thế lỗi ở thân `try`. Với `try-with-resources`, khi thân `try` đã ném một ngoại lệ, Java thường giữ **chính ngoại lệ ấy** làm lỗi chính, còn lỗi đóng tài nguyên được thêm vào qua `Throwable.addSuppressed(...)`.

Bài này tập trung vào **thứ tự sự kiện và nguyên tắc chọn lỗi chính**, bao gồm trường hợp một tài nguyên, nhiều tài nguyên, lỗi khởi tạo, `return`, `catch`, `finally`, cách đọc `getSuppressed()` và cách không làm mất lỗi gốc khi chuyển đổi ngoại lệ. Các chương trình hoàn chỉnh sử dụng **Java 17+**.

## 1. Khái niệm: ngoại lệ chính và ngoại lệ bị suppress

Xét tình huống đọc dữ liệu:

```text
Mở tài nguyên            thành công
      |
      v
Thân try                 ném IOException("read failed")
      |
      v
Tự động close()          ném IOException("close failed")
      |
      v
Ngoại lệ thoát ra        IOException("read failed")   ← primary
      |
      +-- getSuppressed() -> IOException("close failed")
```

Ở đây:

- **Ngoại lệ chính** là đối tượng `Throwable` được truyền ra khỏi `try-with-resources` để các `catch` ở ngoài xem xét. Trong tình huống này, đó là lỗi đọc dữ liệu.
- **Ngoại lệ suppressed** là ngoại lệ bổ sung xảy ra trong quá trình xử lý một ngoại lệ đã có. Nó được lưu trong mảng trả về bởi `primary.getSuppressed()`.
- **Cause** là một quan hệ khác: `primary.getCause()` mô tả ngoại lệ gây ra một ngoại lệ được bọc hoặc có liên hệ nguyên nhân. Ngoại lệ suppressed **không tự trở thành** `cause`.
- Một ngoại lệ có thể có **cả cause lẫn suppressed**. Hai cơ chế chứa thông tin khác nhau.

**Không được kết luận rằng “lỗi được ném sau cùng luôn là lỗi chính”.** Trong `try-with-resources`, việc đóng thường xảy ra sau khi thân `try` đã thất bại, nhưng lỗi thân `try` vẫn giữ vai trò chính. Nếu thân `try` không thất bại, lỗi đầu tiên phát sinh trong **thứ tự đóng** có thể trở thành lỗi chính.

## 2. Quy tắc nền tảng theo JLS §14.20.3

Java Language Specification (JLS) mô tả `try-with-resources` như một cấu trúc có quy tắc tự động đóng tài nguyên:

1. Các tài nguyên được **khởi tạo từ trái sang phải**.
2. Nếu khởi tạo thất bại ở tài nguyên phía sau, những tài nguyên trước đó **đã khởi tạo thành công** được đóng.
3. Nếu khởi tạo thành công, thân `try` được thực thi; khi rời thân `try`, các tài nguyên được đóng theo **thứ tự ngược** với khởi tạo.
4. Mỗi tài nguyên có giá trị khác `null` được đóng. Một lỗi từ thao tác đóng **không mặc nhiên ngăn** Java thử đóng các tài nguyên còn lại.
5. Nếu đã có một ngoại lệ chính từ quá trình khởi tạo, thân `try` hoặc thao tác đóng tài nguyên sau hơn trong thứ tự đóng, lỗi đóng tiếp theo được **suppress** vào ngoại lệ chính.
6. Nếu không có ngoại lệ nào đang được ném trước khi gọi `close()`, mà `close()` thất bại, lỗi đóng ấy trở thành **ngoại lệ chính**.
7. Với dạng `try-with-resources` có `catch`/`finally` đi kèm, tài nguyên được đóng **trước khi** Java chọn `catch` của cùng câu lệnh và thực hiện `finally`.

Quy tắc này áp dụng cho cả những đối tượng implements `AutoCloseable` và `Closeable`, miễn chúng được dùng làm resource hợp lệ trong cú pháp `try (...)`. Nó cũng áp dụng khi sự hoàn tất của thân `try` diễn ra vì `return`, `break` hay `continue`, dù cách xác định ngoại lệ chính khác với trường hợp thân đã ném một lỗi.

### Bảng quyết định nhanh

| Điều xảy ra trước | Khi `close()` chạy | Ngoại lệ/chuyển quyền cuối cùng |
| --- | --- | --- |
| Thân `try` hoàn tất bình thường | `close()` bình thường | Toàn bộ câu lệnh có thể hoàn tất bình thường |
| Thân `try` ném A | `close()` bình thường | A tiếp tục được ném |
| Thân `try` ném A | `close()` ném B | A là **primary**, B là **suppressed** của A |
| Thân `try` bình thường | `close()` ném B | B trở thành **primary** |
| Tài nguyên thứ hai khởi tạo và ném A | `close()` tài nguyên thứ nhất ném B | A là **primary**, B bị suppress |
| Thân `try` dự định `return 42` | `close()` bình thường | Tiếp tục trả 42 |
| Thân `try` dự định `return 42` | `close()` ném B | B được ném ra; không trả 42 |
| Thân `try` ném A, nhiều `close()` lần lượt ném B, C | Các bước đóng được tiếp tục | A là **primary**, B và C được ghi suppressed theo thứ tự phát sinh |

Bảng mô tả luồng thông thường của `try-with-resources` và các đối tượng ngoại lệ khác nhau. Các trường hợp hiếm như một tài nguyên cố tình ném lại **chính cùng đối tượng `Throwable`** đã là ngoại lệ chính có thể tạo tình huống *self-suppression* đặc biệt; không nên thiết kế `close()` kiểu này.

## 3. Một tài nguyên: lỗi trong thân và lỗi ở `close()`

Đây là ví dụ cơ bản nhất: thao tác nghiệp vụ và cleanup đều thất bại. Lưu thành `BodyAndCloseDemo.java`:

```java
import java.io.IOException;

public class BodyAndCloseDemo {
    static class Resource implements AutoCloseable {
        Resource() {
            System.out.println("open");
        }

        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primaryType="
                    + ex.getClass().getSimpleName());
            System.out.println("primaryMessage=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);

            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressedType="
                        + extra.getClass().getSimpleName());
                System.out.println("suppressedMessage=" + extra.getMessage());
            }
        }
        System.out.println("after");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BodyAndCloseDemo.java
java BodyAndCloseDemo
```

Kết quả xác định:

```text
open
body
close
primaryType=IllegalStateException
primaryMessage=work failed
suppressedCount=1
suppressedType=IOException
suppressedMessage=close failed
after
```

Phân tích:

- Constructor `Resource()` hoàn tất nên đối tượng được đăng ký làm tài nguyên.
- Thân `try` ném `IllegalStateException("work failed")`. Đối tượng này được giữ làm lý do `throw` đang chờ.
- Trong bước tự động đóng, `close()` in `close` rồi ném `IOException("close failed")`.
- Vì đã có ngoại lệ chính từ thân, lỗi `close()` được thêm qua cơ chế suppressed; nó **không thay thế** `IllegalStateException`.
- Nhánh `catch (Exception ex)` bên ngoài phần quản lý tài nguyên nhận **IllegalStateException**, không phải IOException đóng tài nguyên.
- `catch` hoàn tất bình thường nên dòng `after` vẫn được thực thi.

Trong hệ thống thật, `catch (Exception)` nên được cân nhắc kỹ: ví dụ dùng nó để quan sát cơ chế với nhiều kiểu ngoại lệ; khi triển khai nghiệp vụ, nên chọn các loại lỗi mà tầng hiện tại thật sự xử lý được.

## 4. Nếu thân `try` thành công nhưng `close()` thất bại?

Một tài nguyên có thể hoạt động bình thường rồi thất bại khi flush dữ liệu, đồng bộ trạng thái hoặc đóng kết nối. Khi đó **không có ngoại lệ từ thân `try`** để được ưu tiên: chính lỗi đóng trở thành ngoại lệ thoát ra ngoài.

Lưu thành `CloseOnlyFailureDemo.java`:

```java
import java.io.IOException;

public class CloseOnlyFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("flush failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("work complete");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

Kết quả:

```text
work complete
close
primary=flush failed
suppressedCount=0
after
```

Thao tác chính in `work complete` nhưng câu lệnh `try-with-resources` không hoàn tất bình thường: `close()` ném `IOException`. Lỗi này được `catch (IOException)` bắt, không có lỗi khác phải suppress.

**Đừng bỏ qua lỗi đóng chỉ vì phần thân đã chạy xong.** Với một số định dạng ghi dữ liệu, lỗi khi flush/close có thể báo rằng dữ liệu chưa được ghi bền vững. Chính sách xử lý phụ thuộc hợp đồng của tài nguyên, nhưng không thể tùy tiện coi kết quả tác vụ là thành công.

## 5. Nhiều tài nguyên: lỗi đóng đầu tiên là lỗi chính nếu không có lỗi trước đó

Với nhiều resource, Java khởi tạo **trái → phải** và đóng **phải → trái**. Nếu thân `try` không ném lỗi và cả hai lệnh `close()` đều thất bại, **lệnh `close()` được gọi trước** sẽ tạo lỗi chính; lỗi đóng tiếp theo bị suppress.

Lưu thành `TwoCloseFailuresDemo.java`:

```java
import java.io.IOException;

public class TwoCloseFailuresDemo {
    static class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource a = new FailingResource("A");
             FailingResource b = new FailingResource("B")) {
            System.out.println("body ok");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 TwoCloseFailuresDemo.java
java TwoCloseFailuresDemo
```

Kết quả:

```text
open A
open B
body ok
close B
close A
primary=close B failed
suppressedCount=1
suppressed=close A failed
```

Điều cần ghi nhớ:

1. A và B đều khởi tạo thành công; `body ok` được in.
2. B được đóng trước A, vì B được khai báo sau.
3. `close B` ném IOException khi chưa có ngoại lệ đang chờ; nó trở thành **primary**.
4. Java vẫn thử đóng A; IOException từ `close A` được thêm vào danh sách suppressed của lỗi B.
5. Bên ngoài nhận `IOException("close B failed")`, kèm một ngoại lệ suppressed.

Với ba tài nguyên A, B, C đóng theo C → B → A, nếu chỉ có lỗi đóng thì lỗi đầu tiên xuất hiện trong thứ tự C → B → A là lỗi chính. Không nên hiểu “tài nguyên đầu tiên được khai báo” là “tài nguyên có lỗi chính”.

## 6. Thân `try` ném lỗi và nhiều tài nguyên cũng ném khi đóng

Nếu thân `try` đã ném ngoại lệ A, thì lỗi của từng thao tác đóng tiếp theo có thể được ghi trong danh sách suppressed của A, dù số lượng tài nguyên là bao nhiêu.

Lưu thành `BodyAndMultipleClosesDemo.java`:

```java
import java.io.IOException;

public class BodyAndMultipleClosesDemo {
    static class Failing implements AutoCloseable {
        private final String name;

        Failing(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Failing first = new Failing("first");
             Failing second = new Failing("second");
             Failing third = new Failing("third")) {
            System.out.println("work");
            throw new IllegalArgumentException("invalid input");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 BodyAndMultipleClosesDemo.java
java BodyAndMultipleClosesDemo
```

Kết quả:

```text
open first
open second
open third
work
close third
close second
close first
primary=invalid input
suppressedCount=3
suppressed=close third failed
suppressed=close second failed
suppressed=close first failed
```

Thứ tự các ngoại lệ suppressed phản ánh thứ tự các lỗi được phát hiện trong quá trình đóng. Việc lỗi từ `close third` phát sinh trước `close first` **không làm lỗi đóng nào trở thành primary** vì thân `try` đã có ngoại lệ chính `IllegalArgumentException("invalid input")`.

Có thể gặp `getSuppressed().length == 0` ngay cả khi có lỗi, nếu tài nguyên không ném khi đóng; không nên coi `getSuppressed()` là một bộ đếm lỗi nghiệp vụ tổng quát.

## 7. Nếu khởi tạo tài nguyên phía sau ném lỗi thì chọn ngoại lệ nào?

Khi một resource initializer ném ngoại lệ, thân `try` **chưa được thực thi**. Java vẫn đóng những tài nguyên khai báo trước đó đã khởi tạo thành công.

Nếu việc đóng những tài nguyên trước đó cũng ném lỗi, **ngoại lệ từ bước khởi tạo thất bại** là lỗi chính; những lỗi đóng phát sinh trong quá trình rollback việc khởi tạo được suppress vào lỗi ấy.

Lưu thành `InitializationFailureDemo.java`:

```java
import java.io.IOException;

public class InitializationFailureDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name, boolean failOpen) throws IOException {
            this.name = name;
            System.out.println("init " + name);
            if (failOpen) {
                throw new IOException("init " + name + " failed");
            }
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A", false);
             Resource b = new Resource("B", true)) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 InitializationFailureDemo.java
java InitializationFailureDemo
```

Kết quả:

```text
init A
init B
close A
primary=init B failed
suppressedCount=1
suppressed=close A failed
```

Điểm đáng chú ý: tài nguyên B ném lỗi **trong constructor**, nên câu lệnh khởi tạo B chưa hoàn tất thành công. Java không có một đối tượng B đã được khởi tạo thành công và đăng ký để tự gọi `B.close()`; A đã được khởi tạo thành công nên A được đóng. Thân `try` không chạy.

Nếu constructor B đã mở một tài nguyên nội bộ rồi ném lỗi trước khi trả về đối tượng, constructor/factory của B phải tự có chiến lược cleanup cho phần đã cấp phát; `try-with-resources` bên ngoài không thể tự giải phóng một resource chưa được trao cho nó.

## 8. Không chỉ lỗi: `return` vẫn phải đi qua bước `close()`

`return` là một cách câu lệnh hoàn tất đột ngột theo ngôn ngữ Java, nhưng nó **không tạo đối tượng ngoại lệ chính**. Vì vậy, nếu `try` dự định trả về một giá trị rồi `close()` ném lỗi, **lỗi `close()` được ném thay vì trả giá trị**.

Lưu thành `ReturnAndCloseFailureDemo.java`:

```java
import java.io.IOException;

public class ReturnAndCloseFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("cleanup failed");
        }
    }

    static int calculate() throws IOException {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            return 42;
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("value=" + calculate());
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
        }
    }
}
```

```bash
javac -encoding UTF-8 ReturnAndCloseFailureDemo.java
java ReturnAndCloseFailureDemo
```

Kết quả:

```text
body
close
caught=cleanup failed
suppressedCount=0
```

Biểu thức `return 42` đã được đánh giá, nhưng trước khi giá trị tới nơi gọi, Java chạy `close()`. Nó thất bại nên lời gọi `calculate()` ném `IOException`; `System.out.println("value=" + calculate())` không được thực hiện vì chưa có giá trị cho phép nối chuỗi.

Nếu `close()` hoàn tất bình thường, phương thức sẽ trả `42`. Tương tự, với `break` hoặc `continue` rời khỏi phạm vi quản lý tài nguyên, `close()` được thực hiện trước khi quyền điều khiển hoàn tất việc chuyển đi; nếu nó ném lỗi, đường đi bình thường dự kiến có thể bị thay thế bởi việc ném lỗi.

**Phân biệt:** khi thân `try` đã ném ngoại lệ A, một lỗi `close()` được suppress vào A. Khi thân `try` chỉ dự định `return`, không có A để suppress, nên lỗi `close()` có thể trở thành primary.

## 9. `catch` của cùng câu lệnh nhìn thấy ngoại lệ nào?

Một `try-with-resources` có thể có `catch` và `finally`:

```java
try (Resource resource = open()) {
    perform(resource);
} catch (IOException ex) {
    handleIo(ex);
} catch (RuntimeException ex) {
    handleRuntime(ex);
} finally {
    afterOperation();
}
```

Đây là mẫu minh họa, giả định các kiểu và phương thức hỗ trợ đã tồn tại. Thứ tự thực thi quan trọng:

1. Khởi tạo resource và thực hiện thân `try`.
2. Thực hiện logic **đóng tự động** và xác định ngoại lệ chính/suppressed.
3. Nếu có ngoại lệ được ném ra từ phần quản lý tài nguyên, chọn **nhánh `catch` đầu tiên tương thích với kiểu thực tế của ngoại lệ chính**.
4. Thực hiện khối `catch` được chọn, nếu có.
5. Thực hiện `finally`, sau đó hoàn tất chuyển quyền điều khiển.

Không có chuyện mỗi suppressed exception lại kích hoạt thêm một nhánh `catch`. Một lỗi suppressed là **thông tin đi kèm** đối tượng chính, không phải một lần `throw` mới lên mỗi `catch` cùng cấp.

### Chương trình Java 17+: nhánh `catch` dựa trên lỗi chính

Lưu thành `CatchPrimaryDemo.java`:

```java
import java.io.IOException;

public class CatchPrimaryDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("close io");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            throw new IllegalArgumentException("body invalid");
        } catch (IOException ex) {
            System.out.println("io catch");
        } catch (IllegalArgumentException ex) {
            System.out.println("runtime catch=" + ex.getMessage());
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 CatchPrimaryDemo.java
java CatchPrimaryDemo
```

Kết quả:

```text
body
close
runtime catch=body invalid
suppressed=close io
finally
after
```

Ở đây `IOException("close io")` xảy ra khi đóng, nhưng không chọn `catch (IOException)` vì nó đã bị suppress vào `IllegalArgumentException("body invalid")`. Nhánh runtime tiếp nhận **ngoại lệ chính**, in thông tin lỗi phụ, rồi `finally` chạy.

Nếu thân `try` bỏ câu lệnh `throw new IllegalArgumentException(...)` và hoàn tất bình thường, lỗi `IOException` từ `close()` sẽ trở thành chính và `catch (IOException)` có thể được chọn.

## 10. So sánh `try-finally` thủ công và `try-with-resources`

Với đoạn đóng thủ công:

```java
try {
    throw new IllegalStateException("work failed");
} finally {
    throw new IllegalArgumentException("close failed");
}
```

Đây là mã minh họa hợp lệ khi đặt trong phương thức, nhưng là **kiểu cleanup cần tránh**. Theo quy tắc `finally`, lý do mới từ `finally` thay thế lý do `throw` cũ. Bộ xử lý bên ngoài sẽ nhận `IllegalArgumentException("close failed")`, còn lỗi `IllegalStateException("work failed")` không tự động được ghi làm `cause` hoặc `suppressed`.

Ngược lại:

```java
try (Resource resource = new Resource()) {
    throw new IllegalStateException("work failed");
}
```

Đây là mẫu chỉ có nghĩa khi `Resource implements AutoCloseable`, `Resource.close()` có thể ném lỗi, và phương thức xử lý/khai báo ngoại lệ phù hợp. `try-with-resources` được thiết kế để không tùy tiện làm mất lỗi thân `try` vì một lỗi đóng bình thường của resource.

**Không được diễn giải `try-with-resources` là “`finally` đơn giản gọi `close()`” trong mọi trường hợp.** Ngữ nghĩa của JLS có logic giữ biến primary exception và gọi `addSuppressed` khi thích hợp. Đó là khác biệt cốt lõi.

Khi thiết kế code, ưu tiên `try-with-resources` cho tài nguyên implements `AutoCloseable`. Nếu có cleanup bổ sung phải làm thủ công, cần kiểm tra tác động khi cleanup ném lỗi để không ghi đè thông tin quan trọng.

## 11. `getSuppressed()`, `getCause()` và việc bọc lỗi ở tầng trên

Một tầng repository có thể ném `IOException` chính kèm suppressed từ lỗi đóng. Tầng service có thể quyết định chuyển đổi thành một lỗi nghiệp vụ `DataLoadException` bằng cách **gắn ngoại lệ ban đầu làm cause**. Khi đó:

```text
DataLoadException("cannot load")
   |
   +-- getCause() ---> IOException("read failed")       ← original primary
                           |
                           +-- getSuppressed()[0]
                                   |
                                   └── IOException("close failed")
```

Ngoại lệ mới ở tầng service không tự sao chép danh sách suppressed lên chính nó. **Danh sách suppressed vẫn nằm trên đối tượng cause ban đầu**, trừ khi code chủ động thao tác khác.

Lưu thành `WrappedPrimaryDemo.java`:

```java
import java.io.IOException;

public class WrappedPrimaryDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class DataLoadException extends Exception {
        DataLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws DataLoadException {
        try {
            repository();
        } catch (IOException ex) {
            throw new DataLoadException("cannot load", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (DataLoadException ex) {
            Throwable cause = ex.getCause();
            System.out.println("wrapper=" + ex.getMessage());
            System.out.println("wrapperSuppressed="
                    + ex.getSuppressed().length);
            System.out.println("cause=" + cause.getMessage());
            System.out.println("causeSuppressed="
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 WrappedPrimaryDemo.java
java WrappedPrimaryDemo
```

Kết quả:

```text
wrapper=cannot load
wrapperSuppressed=0
cause=read failed
causeSuppressed=close failed
```

Đây là cách thường gặp để chuyển đổi ngoại lệ ở ranh giới tầng mà không đánh mất nguyên nhân. Khi in stack trace bằng `printStackTrace()` hoặc dùng hệ thống logging hỗ trợ `Throwable`, phần cause và suppressed có thể được trình bày theo cấu trúc tương ứng.

Không nên chỉ dùng `throw new DataLoadException(ex.getMessage(), null)` hoặc ghi lại một message chung rồi bỏ đối tượng `ex`: thao tác đó có thể đánh mất cả stack trace, cause lẫn suppressed exception cần để điều tra.

## 12. Kiểm tra kiểu ngoại lệ khi đóng vẫn là vấn đề compile-time

`AutoCloseable.close()` được khai báo `throws Exception`; `Closeable.close()` được khai báo `throws IOException`. Một lớp cụ thể có thể override với loại checked hẹp hơn hoặc không có checked exception. Khi dùng `try-with-resources`, compiler xét:

- Những checked exceptions có thể phát sinh **lúc khởi tạo** tài nguyên.
- Những checked exceptions có thể phát sinh từ **thân `try`**.
- Những checked exceptions mà phương thức **`close()` của kiểu tài nguyên** có thể ném.
- Những ngoại lệ được `catch` xử lý tại chỗ và những loại còn có thể thoát ra để yêu cầu `throws`.

Ví dụ mã hợp lệ với kiểu tài nguyên cụ thể:

```java
class SilentResource implements AutoCloseable {
    @Override
    public void close() { }
}

class TypeCheckExample {
    static void useSilent() {
        try (SilentResource r = new SilentResource()) {
            System.out.println("work");
        }
    }
}
```

Đây là lớp minh họa hợp lệ nhưng không có `main`. Vì `SilentResource.close()` không khai báo checked exception, `useSilent()` không cần thêm `throws Exception` chỉ vì lớp implements `AutoCloseable`.

Ngược lại, với tham chiếu kiểu tĩnh `AutoCloseable`:

```java
static void useAsAutoCloseable(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("work");
    }
}
```

Đoạn thứ hai là phương thức minh họa (Java 9+), có thể đặt trong một lớp. Tham số `resource` không bị gán lại nên là effectively final và hợp lệ trong `try (resource)`. Kiểu tĩnh `AutoCloseable` có `close() throws Exception`, nên phương thức phải xử lý hoặc khai báo loại checked đó. Trong Java 17, mẫu này hợp lệ.

Quy tắc primary/suppressed là **hành vi runtime**. Nó không cho phép bỏ qua nghĩa vụ checked exception lúc biên dịch, kể cả khi bạn nghĩ rằng lỗi `close()` “chỉ bị suppress”. Nếu thân `try` bình thường, lỗi `close()` có thể chính là primary.

## 13. Ngoại lệ `Error`, interrupted cleanup và những trường hợp hiếm

`AutoCloseable.close()` có thể ném cả unchecked exceptions. Nếu resource `close()` ném `RuntimeException` hoặc `Error`, cách xác định lỗi chính/suppressed của `try-with-resources` về mặt ngữ nghĩa vẫn dựa trên các quy tắc `Throwable`; nhưng **không nên bắt `Throwable` một cách đại trà chỉ để tiếp tục chương trình**. Một `Error` nghiêm trọng có thể chỉ ra JVM hoặc trạng thái ứng dụng không còn phù hợp để phục hồi.

Theo Javadoc của `AutoCloseable`, nên tránh để `close()` ném `InterruptedException`. Nếu nó xuất hiện trong cleanup khi đã có lỗi chính, ngoại lệ bị suppress có thể làm ý nghĩa trạng thái interrupt khó quản lý; cần thiết kế API cleanup không làm mất yêu cầu hủy thread.

Ngoài ra, `Throwable.addSuppressed(...)` có giới hạn:

- Không thể suppress chính **cùng đối tượng** `Throwable` vào nó (*self-suppression*), vì đó là thao tác không hợp lệ.
- Một lớp `Throwable` có thể được xây dựng với suppression bị vô hiệu hóa (thông qua constructor phù hợp ở lớp con). Khi đó `addSuppressed(...)` không ghi lỗi phụ vào danh sách như trường hợp thông thường.
- Nếu một resource `close()` cố tình tái ném đúng cùng đối tượng đang là ngoại lệ chính, logic tự động có thể gặp lỗi self-suppression. Đừng tạo thiết kế dựa vào trường hợp đó.
- Nếu JVM/tiến trình bị chấm dứt ngoài đường đi Java thông thường, không có bảo đảm rằng `close()` hay `finally` đã chạy.

Những tình huống hiếm này không làm thay đổi nguyên tắc thực hành: **thiết kế `close()` có trách nhiệm, tránh ném cùng đối tượng lỗi đang truyền, và luôn giữ ngữ cảnh lỗi chính**.

## 14. Cách đọc log và stack trace khi có suppressed exception

Khi debug một thất bại có nhiều dấu vết lỗi:

1. Đọc **kiểu và message của ngoại lệ chính** đầu tiên. Nó cho biết hoạt động nào làm cấu trúc `try-with-resources` thất bại theo đường truyền ra ngoài.
2. Kiểm tra **cause chain** qua `getCause()` để xem ngoại lệ này có được tầng khác chuyển đổi từ nguyên nhân cụ thể nào không.
3. Kiểm tra `getSuppressed()` trên **từng đối tượng quan trọng trong cause chain**, không chỉ trên wrapper ngoài cùng.
4. Xem thứ tự các lỗi suppressed. Thứ tự này thường phản ánh thứ tự các bước đóng tài nguyên, tức **ngược với thứ tự khai báo**.
5. Từ loại resource, xác định liệu lỗi đóng chỉ là cleanup phụ hay có thể chứng tỏ dữ liệu chưa được hoàn tất an toàn (ví dụ lỗi flush).
6. Quyết định retry, rollback hoặc phục hồi theo hợp đồng nghiệp vụ; không tự động retry chỉ vì thông báo chứa chữ “close”.

Một cách ghi lỗi đủ dữ liệu:

```java
try (Resource resource = open()) {
    process(resource);
} catch (Exception ex) {
    logger.error("Operation failed", ex);
    throw ex;
}
```

Đây là **mẫu minh họa**, giả định `Resource implements AutoCloseable`, các hàm và logger đã được định nghĩa, và phương thức bao ngoài khai báo `throws` đúng với các checked exceptions có thể đi ra. Logger nhận nguyên đối tượng `ex` nên có cơ hội hiển thị cả stack trace, cause lẫn suppressed.

Hạn chế ghi cùng một lỗi đầy đủ ở mọi tầng rồi ném lại vì có thể tạo log trùng. Nên xác định tầng chịu trách nhiệm ghi nhận cuối cùng; những tầng trung gian chỉ bổ sung ngữ cảnh khi thật sự cần.

## 15. Các hiểu lầm thường gặp

| Nhận định sai | Điều đúng cần nhớ |
| --- | --- |
| “`close()` chạy sau nên lỗi của `close()` luôn là ngoại lệ chính.” | Nếu thân đã ném lỗi A thì A thường là chính; lỗi đóng bị suppress. |
| “Nếu thân `try` chạy thành công, lỗi `close()` không quan trọng.” | Lỗi đóng có thể thành ngoại lệ chính; thao tác nghiệp vụ chưa chắc hoàn tất an toàn. |
| “Nếu hai `close()` cùng lỗi, resource khai báo trước quyết định primary.” | Nếu trước đó chưa có lỗi, `close()` ném đầu tiên theo thứ tự **đóng ngược** quyết định primary. |
| “Khi B mở thất bại, Java không đóng A.” | Java đóng các tài nguyên đã khởi tạo thành công trước đó. |
| “Lỗi `close()` làm Java không đóng các resource còn lại.” | Cơ chế `try-with-resources` tiếp tục cố đóng những resource còn lại. |
| “Mỗi suppressed exception đi vào một nhánh `catch` khác nhau.” | `catch` được chọn theo ngoại lệ chính; suppressed chỉ là thông tin đi kèm. |
| “`getCause()` và `getSuppressed()` là cùng một mảng.” | Cause là một quan hệ nguyên nhân; suppressed là danh sách lỗi bổ sung. |
| “`return` trong `try` chắc chắn thắng lỗi khi `close()`.” | Lỗi đóng có thể thay thế đường `return` dự kiến. |
| “Khi bọc lỗi thành `ServiceException`, danh sách suppressed tự sao chép sang wrapper.” | Nó thường ở nguyên đối tượng cause; cần truy cause rồi suppressed. |
| “`finally` thủ công có cùng logic ưu tiên lỗi với `try-with-resources`.” | `finally` tự ném lỗi có thể ghi đè lỗi cũ; `try-with-resources` có cơ chế suppression riêng. |
| “Có `getSuppressed()` nên không cần quản lý ownership của resource.” | Ownership vẫn quyết định đối tượng nào được đóng, có đóng quá sớm/nhầm đối tượng không. |
| “`try-with-resources` bảo đảm đóng nếu tiến trình bị kill.” | Không; nó thực thi theo đường điều khiển Java khi JVM còn vận hành phù hợp. |

## 16. Quy trình phân tích một bài tập chọn ngoại lệ chính

Với một đoạn `try-with-resources` cụ thể, hãy phân tích đúng trình tự:

**Bước 1 — Khởi tạo:** đọc các resource từ **trái sang phải**. Nếu một initializer ném, ghi loại lỗi và danh sách những resource đã được tạo thành công trước đó.

**Bước 2 — Thân `try`:** chỉ thực hiện nếu các resource cần thiết đều khởi tạo xong. Ghi thân hoàn tất bình thường, `return`, `throw` hay chuyển quyền điều khiển khác.

**Bước 3 — Đóng:** đi qua các resource đã khởi tạo thành công theo **thứ tự ngược**. Với mỗi `close()`, xác định nó hoàn tất bình thường hay ném ngoại lệ.

**Bước 4 — Chọn primary/suppressed:** nếu đã có ngoại lệ từ initializer hoặc thân thì nó được ưu tiên; nếu chưa, lỗi `close()` đầu tiên trở thành chính; các lỗi đóng sau đó được suppress theo quy tắc.

**Bước 5 — Xử lý bên ngoài:** sau quá trình tự đóng, xác định `catch` đầu tiên phù hợp với **kiểu ngoại lệ chính**, rồi `finally` nếu có. Nếu không bắt được, ngoại lệ tiếp tục lan ra.

**Bước 6 — Giữ thông tin:** khi chuyển đổi hoặc log lỗi, đảm bảo vẫn có thể truy vấn `cause` và `suppressed` của đối tượng ban đầu; không chỉ giữ message.

Áp dụng vào ba tình huống sau:

```text
Tình huống A:
  body        -> throw IOException("read")
  close B     -> throw IOException("close B")
  close A     -> bình thường
  primary     -> IOException("read")
  suppressed  -> IOException("close B")

Tình huống B:
  body        -> bình thường
  close B     -> throw IOException("close B")
  close A     -> throw IOException("close A")
  primary     -> IOException("close B")
  suppressed  -> IOException("close A")

Tình huống C:
  init A      -> thành công
  init B      -> throw IOException("init B")
  close A     -> throw IOException("close A")
  body        -> không chạy
  primary     -> IOException("init B")
  suppressed  -> IOException("close A")
```

Cách ghi sự kiện từ trên xuống này giúp tránh nhầm thứ tự khởi tạo với thứ tự đóng, nhầm “lỗi ném sau cùng” với primary và nhầm suppressed với cause.

## 17. Tự kiểm tra

**Câu 1.** Thân `try` ném `IOException("read")`, `close()` ném `IOException("close")`. Lỗi chính là gì?  
**`IOException("read")`.** Lỗi đóng trở thành suppressed của lỗi đọc.

**Câu 2.** Thân `try` bình thường, `close()` ném `IOException("flush")`. Lỗi chính?  
**`IOException("flush")`.** Không có lỗi nào trước đó để được ưu tiên.

**Câu 3.** Khai báo A rồi B; cả hai đóng đều ném, thân thành công. Lỗi nào là chính?  
**Lỗi từ B.close()**, vì B đóng trước A. Lỗi A.close() được suppress.

**Câu 4.** Thân ném lỗi X; `close(B)` và `close(A)` đều ném. Có tổng cộng bao nhiêu suppressed errors thông thường?  
**Hai**, theo thứ tự B rồi A; X vẫn là primary.

**Câu 5.** Khởi tạo B thất bại, A đã khởi tạo thành công. A có được đóng không?  
**Có.** Nếu A.close() cũng ném, lỗi từ B initializer được ưu tiên làm primary.

**Câu 6.** `return 42` trong thân `try`, `close()` ném IOException. Hàm trả về 42 hay ném IOException?  
**Ném IOException.** Khi đóng thất bại, đường trả giá trị dự kiến bị thay thế.

**Câu 7.** Nếu có `catch (IOException)` và `catch (IllegalStateException)`, thân ném IllegalStateException còn `close()` ném IOException, nhánh nào chạy?  
**Nhánh `catch (IllegalStateException)`**, vì lỗi IOException đóng đã bị suppress, không phải primary.

**Câu 8.** Một `ServiceException` bọc `IOException` chính làm cause. Có thể tìm lỗi đóng ở đâu?  
Thường trong `serviceException.getCause().getSuppressed()`, không nhất thiết ở `serviceException.getSuppressed()`.

**Câu 9.** `getSuppressed()` và `getCause()` trả cùng một thông tin?  
**Không.** Cause liên kết nguyên nhân; suppressed lưu các lỗi phụ cùng quá trình xử lý.

**Câu 10.** Có nên bắt mọi `Throwable` để “cứ tiếp tục sau lỗi đóng” không?  
**Không.** Lỗi có thể chỉ ra tài nguyên hoặc JVM không còn trạng thái phù hợp để tiếp tục; việc xử lý phải dựa trên hợp đồng và khả năng phục hồi thực tế.

## Tài liệu chuẩn

- [Java Language Specification, Java SE 21 — §14.20.3: `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS 21 — §14.20.3.1: Basic `try-with-resources` và cách chuyển đổi về `try-catch-finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3.1).
- [JLS 21 — §14.20.3.2: Extended `try-with-resources` có `catch`/`finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3.2).
- [JLS 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).
- [Java SE 21 API — `Throwable.addSuppressed()` và `getSuppressed()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [Java SE 21 API — `AutoCloseable.close()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html).

**Ghi nhớ:** Trong `try-with-resources`, ngoại lệ đã phát sinh ở phần khởi tạo hoặc thân `try` thường được giữ làm **primary**; ngoại lệ từ `close()` được **suppress** vào nó. Nếu chưa có lỗi nào, lỗi đóng đầu tiên theo thứ tự **đóng ngược** trở thành primary. Java tự động đóng những tài nguyên còn lại, sau đó `catch` phân loại **lỗi chính**, không phân loại từng lỗi suppressed.
