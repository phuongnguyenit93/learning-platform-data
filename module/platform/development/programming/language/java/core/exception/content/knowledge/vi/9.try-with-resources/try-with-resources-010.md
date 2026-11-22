# Try-with-resources kết hợp `catch` và `finally` trong Java

> **Bối cảnh:** Java Core → Exception → Try-with-resources. Cấu trúc `try-with-resources` (TWR, được giới thiệu từ Java 7) quản lý việc gọi `close()` của các tài nguyên `AutoCloseable`. Khi kết hợp thêm `catch` và `finally`, điểm quan trọng nhất là **tài nguyên đã được đóng theo cơ chế TWR trước khi các `catch` và `finally` gắn với cấu trúc đó được thực hiện**. Vì vậy `catch` có thể bắt lỗi phát sinh từ **thân `try`, khởi tạo tài nguyên hoặc `close()`**; `finally` thích hợp để hoàn tất những công việc khác, không cần đóng lại các tài nguyên đã giao cho TWR.

## 1. Mẫu cú pháp và thứ tự tổng quát

Dạng đầy đủ:

```java
try (ResourceType resource = acquire()) {
    use(resource);
} catch (SomeException e) {
    handle(e);
} finally {
    afterOperation();
}
```

Đây là **mã mẫu**, `ResourceType` và các phương thức chưa được định nghĩa; không phải tệp chạy độc lập.

- `try ( ... )` khai báo hoặc tham chiếu tài nguyên cần tự đóng.
- Thân `{ ... }` thực hiện công việc có thể thành công hoặc ném exception.
- Khi rời thân (theo đường Java thông thường), hệ thống gọi `close()` đối với các resource đã được khởi tạo thành công, theo **thứ tự ngược thứ tự khai báo**.
- `catch` tương thích xử lý `Throwable` đang lan truyền từ cấu trúc TWR nếu có.
- `finally` thực hiện công việc hoàn tất chung theo quy tắc `try`/`finally`, sau khi đóng resource và sau `catch` nếu có.
- Cả `catch` lẫn `finally` đều **không bắt buộc** đối với TWR: một `try (resource) { ... }` đứng riêng là hợp lệ.

Hình dung đường thành công và thất bại:

```text
      Khởi tạo resource(s)
                │
                ▼
           Thân try
          /        \
      thành công   phát sinh Throwable
          \        /
                ▼
        TWR gọi close()
        (đảo thứ tự khai báo)
                │
                ▼
     Có Throwable thoát ra?
          /          \
        Có            Không
        │              │
        ▼              │
  catch phù hợp?       │
  (nếu có)             │
        \              /
                 ▼
              finally
                 │
                 ▼
        Kết thúc hoặc lan lỗi
```

**Không phải:** `thân try → catch → close → finally`. Đối với handler gắn trực tiếp sau một TWR, Java **đóng trước khi vào handler**. Một lỗi mới từ `close()` có thể khiến dòng code vốn tưởng đã thành công rẽ sang `catch`.

### 1.1. Ví dụ tối giản có `catch` và `finally`

```java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Java"))) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    System.out.println("Đọc hoặc đóng lỗi: " + e.getMessage());
} finally {
    System.out.println("Kết thúc thao tác");
}
```

Đây là đoạn trong một method Java phù hợp. `BufferedReader` có phương thức `readLine()`/`close()` khai báo `IOException`; dùng `catch(IOException)` ở đây hợp lệ. Dữ liệu đọc trong bộ nhớ và việc đóng thường thành công, cho stdout:

```text
Java
Kết thúc thao tác
```

Không xuất hiện dòng của `catch` vì không có `IOException` phát sinh trong lượt này. Sự tồn tại của `catch` không tự tạo ra ngoại lệ.

## 2. Ba vai trò riêng: `try(resource)`, `catch` và `finally`

| Thành phần | Vai trò đúng | Điều **không** tự làm |
| --- | --- | --- |
| `try (resource)` | Xác lập **quyền sở hữu tạm thời** và tự gọi `close()` khi rời khối | Không bảo đảm đọc/ghi thành công; không tự rollback giao dịch |
| `catch (T e)` | Chọn handler theo kiểu đối tượng được ném; phục hồi, báo lỗi, chuyển đổi hoặc ném tiếp | Không tự đóng resource khác, không tự hoàn tác trạng thái, không biến mọi lỗi thành thành công |
| `finally` | Thực hiện hành động hoàn tất chung trong phạm vi `try` tương ứng | Không nhất thiết chạy nếu JVM/process bị chấm dứt bất thường; không nên che exception gốc bằng `return`/`throw` mới |

Một lý do phổ biến để dùng TWR **cùng** `catch` và `finally` là phân tách trách nhiệm:

1. Resource được quản lý tập trung, không cần lặp mã đóng ở đường thành công và thất bại.
2. Handler chỉ tập trung vào **quyết định nghiệp vụ khi thao tác thất bại**.
3. Khối `finally` làm một công việc kết thúc khác, như ghi trạng thái hoàn tất lượt xử lý, khôi phục context hoặc giải phóng cơ chế không thuộc resource `AutoCloseable`.

Nếu chỉ cần tự đóng resource, hãy dùng TWR đơn giản, **không thêm `catch`/`finally` vô ích**. Nếu không biết xử lý exception tại tầng hiện tại, có thể để nó lan ra caller thay vì bắt rồi bỏ qua.

## 3. Chương trình Java 17: kiểm chứng thứ tự ở cả đường thành công và lỗi

Lưu tệp **`TwrCatchFinallyOrderDemo.java`**:

```java
public class TwrCatchFinallyOrderDemo {
    static final class Probe implements AutoCloseable {
        private final String name;

        Probe(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        void use() {
            System.out.println("Dùng " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    static void run(boolean fail) {
        try (Probe p = new Probe("R")) {
            p.use();
            if (fail) {
                throw new IllegalStateException("Lỗi thân try");
            }
            System.out.println("Thân try thành công");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally: kết thúc lượt");
        }
    }

    public static void main(String[] args) {
        run(false);
        System.out.println("---");
        run(true);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 TwrCatchFinallyOrderDemo.java
java TwrCatchFinallyOrderDemo
```

**Stdout chính xác:**

```text
Mở R
Dùng R
Thân try thành công
Đóng R
Finally: kết thúc lượt
---
Mở R
Dùng R
Đóng R
Catch: Lỗi thân try
Finally: kết thúc lượt
```

**Phân tích:**

- `run(false)`: khởi tạo → dùng → thân thành công → `close()` → bỏ qua `catch` → `finally`.
- `run(true)`: khởi tạo → dùng → ném `IllegalStateException` → `close()` → `catch` → `finally`.
- Dòng `Đóng R` luôn xuất hiện **trước `Catch: ...`** khi thân có lỗi.
- `finally` không cần gọi lại `p.close()`. Nó chỉ thực hiện công việc độc lập khi lượt xử lý kết thúc.
- Resource `Probe` có `close()` không khai báo checked exception, nên không phải xử lý `IOException`/`Exception` do riêng `close()` này.

Đây là tình huống quan sát rõ ràng nhất cho yêu cầu “TWR kết hợp catch và finally”.

## 4. Lỗi ở `close()` cũng có thể kích hoạt `catch`

Người học đôi khi cho rằng `catch` gắn với TWR chỉ xử lý lỗi trong **thân** khối `try`. Điều đó không đúng: ngoại lệ của `close()` có thể là ngoại lệ thoát khỏi toàn bộ phần được bảo vệ.

Ví dụ: thân hoàn tất thành công, nhưng resource không đóng được.

Tạo **`TwrCloseFailureDemo.java`**:

```java
import java.io.IOException;

public class TwrCloseFailureDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Close được gọi");
            throw new IOException("Không thể đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingResource r = new FailingResource()) {
            System.out.println("Công việc đã xong");
        } catch (IOException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally: ghi nhận kết thúc");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwrCloseFailureDemo.java
java TwrCloseFailureDemo
```

Stdout:

```text
Công việc đã xong
Close được gọi
Catch: Không thể đóng
Finally: ghi nhận kết thúc
```

Điểm cần hiểu:

- Thân `try` không chủ động ném exception.
- Khi rời thân, Java gọi `close()` và nhận `IOException`.
- `catch(IOException)` nhận exception từ **đóng tài nguyên**.
- `finally` chạy sau handler.
- Vì `close()` công bố `throws IOException` nên handler checked này hợp lệ, dù thân `try` chỉ in một dòng.

**Khi nào lỗi `close()` là vấn đề nghiêm trọng?** Với writer/buffered stream, quá trình đóng có thể flush dữ liệu và thất bại; vì vậy không được mặc định xem `Công việc đã xong` là bằng chứng chắc chắn dữ liệu đã được ghi thành công và bền vững. Cần để lỗi đóng ảnh hưởng đến kết quả nghiệp vụ nếu hợp đồng yêu cầu.

## 5. Cả thân `try` và `close()` cùng lỗi: primary và suppressed

Đây là khác biệt quan trọng giữa TWR và một số mẫu `finally` đóng tài nguyên thủ công. Nếu thân đã ném exception **và** resource đóng cũng ném exception, Java thường giữ lỗi từ thân làm **primary exception** và gắn lỗi đóng vào `getSuppressed()`.

Hai quan hệ không đồng nghĩa:

- `getCause()`: “ngoại lệ này được gây ra bởi ngoại lệ nào?” — thường do code tạo wrapper và truyền `cause`.
- `getSuppressed()`: “những ngoại lệ nào bị đặt vào danh sách phụ?” — TWR tự dùng cơ chế này cho lỗi phát sinh khi đóng sau khi đã có primary.

Tạo **`TwrSuppressedWithFinallyDemo.java`**:

```java
import java.io.IOException;

public class TwrSuppressedWithFinallyDemo {
    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Close thất bại");
            throw new IOException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingClose r = new FailingClose()) {
            System.out.println("Thân đang chạy");
            throw new IllegalStateException("Lỗi xử lý");
        } catch (IllegalStateException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed[0]: "
                    + e.getSuppressed()[0].getMessage());
        } catch (IOException e) {
            System.out.println("Lỗi chỉ xảy ra khi đóng: "
                    + e.getMessage());
        } finally {
            System.out.println("Finally: hoàn tất");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 TwrSuppressedWithFinallyDemo.java
java TwrSuppressedWithFinallyDemo
```

Stdout:

```text
Thân đang chạy
Close thất bại
Primary: Lỗi xử lý
Suppressed count: 1
Suppressed[0]: Lỗi đóng
Finally: hoàn tất
```

Giải thích theo thứ tự:

1. Thân `try` ném `IllegalStateException("Lỗi xử lý")`.
2. Java tiến hành đóng resource; `close()` ném `IOException("Lỗi đóng")`.
3. Ngoại lệ từ thân được giữ làm **primary**, lỗi đóng được gắn suppressed.
4. `catch(IllegalStateException)` được chọn theo kiểu của **primary**, không phải theo kiểu của suppressed exception.
5. `catch(IOException)` không chạy ở đường này, dù suppressed exception là `IOException`.
6. `finally` chạy sau `catch`.

Có mặt `catch(IOException)` ở chương trình là hợp lệ do `close()` có thể tạo `IOException` làm primary khi không có lỗi thân.

### 5.1. Nếu chỉ có lỗi đóng?

Nếu bỏ `throw new IllegalStateException(...)` trong thân, khi `close()` ném `IOException` sẽ không có primary từ thân. Khi ấy `IOException` đóng có thể trở thành **primary**, nên nhánh `catch(IOException)` sẽ chạy. Đừng viết handler `catch(IllegalStateException)` và tưởng nó luôn xử lý cả lỗi đóng.

### 5.2. Tại sao phải kiểm tra suppressed?

Nếu chỉ in `e.getMessage()`, người phát triển sẽ không thấy lỗi đóng. Với một logger ghi stack trace đầy đủ, suppressed thường có thể được hiển thị; nếu xây logging riêng, hãy cân nhắc lưu cả `getSuppressed()`.

Không nên “xử lý” một suppressed exception như thể lỗi chính đã biến mất. Đây là thông tin chẩn đoán bổ sung, không phải một luồng `catch` độc lập được tự kích hoạt.

## 6. Nhiều resource: đóng ngược thứ tự và xử lý lỗi sau khi đóng xong

Với:

```java
try (Resource first = openFirst();
     Resource second = openSecond();
     Resource third = openThird()) {
    work();
} catch (Exception e) {
    report(e);
} finally {
    finish();
}
```

Đây là mã mẫu, chưa phải chương trình độc lập. Thứ tự **khởi tạo**: `first → second → third`. Thứ tự **đóng**: `third → second → first`. Nếu `third.close()` phát sinh lỗi, Java vẫn tiến hành đóng các resource còn lại theo quy tắc ngôn ngữ; ngoại lệ tiếp theo có thể bị suppressed.

Tạo **`TwrMultipleResourcesDemo.java`**:

```java
import java.io.IOException;

public class TwrMultipleResourcesDemo {
    static final class Named implements AutoCloseable {
        private final String name;

        Named(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Named a = new Named("A");
             Named b = new Named("B")) {
            System.out.println("Thân thành công");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + suppressed.getMessage());
            }
        } finally {
            System.out.println("Finally");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwrMultipleResourcesDemo.java
java TwrMultipleResourcesDemo
```

Stdout:

```text
Mở A
Mở B
Thân thành công
Đóng B
Đóng A
Primary: close B
Suppressed: close A
Finally
```

Vì thân thành công, lỗi đóng đầu tiên (ở `B`) làm primary, còn lỗi khi đóng `A` bị suppressed vào đó. Handler chạy **sau khi Java đã thử đóng cả hai tài nguyên**; `finally` chạy sau handler.

### 6.1. Khi thân cũng có lỗi với nhiều tài nguyên

Giả sử thân ném `IllegalStateException("body")` trước khi đóng `B` và `A`, trong khi cả hai `close()` ném `IOException`. Khi đó:

- Primary là `IllegalStateException("body")`.
- Các lỗi đóng của `B` và `A` được ghi suppressed theo thứ tự chúng xảy ra.
- `catch(IllegalStateException)` nhận primary.
- `finally` chạy sau khi handler hoàn tất.

Đừng dựa vào `catch(IOException)` để đón từng lỗi đóng trong tình huống này. Các lỗi đó không trở thành primary khi đã có lỗi chính từ thân; cần đọc `getSuppressed()`.

### 6.2. Nếu khởi tạo resource thứ hai bị lỗi?

Một resource đã được khởi tạo thành công vẫn được đóng nếu quá trình mở resource sau thất bại. Chẳng hạn:

```java
try (Resource a = openA();
     Resource b = openBThatThrows()) {
    work();
} catch (IOException e) {
    report(e);
} finally {
    finish();
}
```

Đây là minh họa, giả sử `openA` trả resource, `openBThatThrows` có `throws IOException`. Nếu mở `a` thành công, mở `b` ném `IOException`, Java đóng `a` trước khi vào handler. Nếu `a.close()` cũng ném, lỗi mở `b` thường được giữ primary và lỗi đóng `a` bị suppressed.

TWR không thể đóng một đối tượng mà initializer **chưa trả về/khởi tạo thành công**. Nếu initializer tự mở resource phụ rồi ném lỗi giữa chừng, mã bên trong initializer phải chịu trách nhiệm không làm rò rỉ resource phụ đó.

## 7. `catch` xử lý loại lỗi nào? Chọn theo primary exception

Sau TWR, `catch` hoạt động theo **cơ chế chọn handler thông thường**: so kiểu runtime của đối tượng exception đang được ném với kiểu khai báo trong `catch`.

| Nguồn lỗi | Primary có thể là | Handler phù hợp |
| --- | --- | --- |
| Đọc file trong thân lỗi | `IOException` | `catch(IOException)` hoặc kiểu cha |
| Kiểm tra nghiệp vụ trong thân lỗi | `IllegalStateException` | `catch(IllegalStateException)` hoặc `catch(Exception)` |
| Thân thành công, `close()` ném `IOException` | `IOException` | `catch(IOException)` |
| Thân ném `IllegalStateException`, `close()` ném `IOException` | `IllegalStateException` với `IOException` suppressed | `catch(IllegalStateException)`; handler IOException không tự bắt suppressed |
| Khởi tạo resource ném `FileNotFoundException` | `FileNotFoundException` | `catch(FileNotFoundException)` hoặc `catch(IOException)` |
| Thân ném `AssertionError`, `close()` thành công | `AssertionError` | `catch(Error)` hoặc `catch(Throwable)` về mặt kiểu, **không** phải `catch(Exception)` |

Đặt handler cụ thể trước handler cha:

```java
try (java.io.BufferedReader reader = openReader()) {
    consume(reader);
} catch (java.io.FileNotFoundException e) {
    System.out.println("Không tìm thấy file");
} catch (java.io.IOException e) {
    System.out.println("Lỗi I/O");
} finally {
    System.out.println("Hoàn tất");
}
```

Đoạn trên là mẫu, `openReader` và `consume` phải được định nghĩa với những ngoại lệ checked phù hợp. Nếu đặt `catch(IOException)` trước `catch(FileNotFoundException)`, handler con phía sau bị che khuất và compiler từ chối.

**Nguyên tắc:** đừng dùng `catch(Exception)` chỉ để tránh nghiên cứu lỗi nào có thể phát sinh. Handler rộng có thể bắt các bug như `NullPointerException`, nhưng không tự phục hồi dữ liệu. Ở ranh giới một tác vụ độc lập, bắt rộng có thể hợp lý nếu luôn báo `FAILED` và cách ly trạng thái; trong phương thức đọc dữ liệu, bắt kiểu cụ thể thường sáng sủa hơn.

## 8. `finally` chạy sau `catch` — nhưng có những ngoại lệ quan trọng

Một `finally` gắn với TWR thường chạy:

- khi thân và close đều thành công;
- khi exception được `catch` xử lý thành công;
- khi exception không có handler phù hợp và tiếp tục lan ra;
- khi `catch` thực hiện `return` hoặc ném exception khác;
- khi thân `try` có một `return` hợp lệ.

Tuy nhiên **không thể hứa “luôn chạy trong mọi hoàn cảnh”**: nếu JVM/process bị kết thúc đột ngột, mất nguồn điện, lỗi native hoặc các tình huống không trở lại điều khiển Java bình thường, code không có bảo đảm tuyệt đối.

### 8.1. Không tự động nuốt exception gốc

Nếu `finally` chỉ ghi nhận kết thúc hoặc khôi phục một context an toàn, exception trước đó có thể tiếp tục lan truyền bình thường sau khi `finally` kết thúc.

Nếu `finally` thực hiện `return` hoặc ném exception mới, kết quả có thể **thay thế** exception đang chờ. Đây là lý do nên tránh `return` trong `finally` và cẩn trọng với các thao tác có thể ném lỗi mới tại đây.

Ví dụ sai về thiết kế:

```java
// Phản ví dụ trong method, không phải chương trình độc lập.
try (Resource resource = acquire()) {
    perform(resource);
} finally {
    return; // Có thể che mất exception đang lan truyền.
}
```

Nếu `perform` ném exception, một `return` trong `finally` có thể khiến caller không nhận được lỗi đó. TWR không thể bảo toàn primary exception khi người viết cố tình điều khiển lại luồng trong `finally`.

### 8.2. Exception phát sinh trong `finally` không được `catch` cùng cấp bắt

```java
try (Resource resource = acquire()) {
    System.out.println("Công việc");
} catch (Exception e) {
    System.out.println("Lỗi trong try/close");
} finally {
    throw new IllegalStateException("Lỗi finally");
}
```

Đây là mã mẫu cần định nghĩa resource. `IllegalStateException` được ném **trong `finally`**, không phải bên trong phần thân TWR đã được `catch` này bảo vệ, nên handler `catch(Exception)` kèm theo không tự bắt được ngoại lệ mới đó. Caller ở ngoài mới có thể nhận.

**Khuyến nghị:** để phần `finally` nhỏ, đơn giản, tránh những thao tác có thể thất bại. Với công việc đóng tài nguyên, giao cho TWR thay vì lặp lại trong `finally`.

## 9. Chương trình Java 17: ngoại lệ mới ở `catch`, `finally` vẫn chạy

Tạo **`TwrCatchRethrowFinallyDemo.java`**:

```java
public class TwrCatchRethrowFinallyDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Close");
        }
    }

    static void doWork() {
        try (Resource r = new Resource()) {
            System.out.println("Thân try");
            throw new IllegalArgumentException("Input sai");
        } catch (IllegalArgumentException e) {
            System.out.println("Catch: " + e.getMessage());
            throw new IllegalStateException("Không hoàn tất", e);
        } finally {
            System.out.println("Finally: giải phóng context");
        }
    }

    public static void main(String[] args) {
        try {
            doWork();
        } catch (IllegalStateException e) {
            System.out.println("Caller: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 TwrCatchRethrowFinallyDemo.java
java TwrCatchRethrowFinallyDemo
```

Stdout:

```text
Thân try
Close
Catch: Input sai
Finally: giải phóng context
Caller: Không hoàn tất
Cause: IllegalArgumentException
```

Lưu ý:

1. `close()` chạy trước handler nội bộ.
2. Handler tạo **wrapper `IllegalStateException`** mới, giữ `IllegalArgumentException` gốc làm `cause`.
3. `finally` vẫn chạy khi handler chuẩn bị ném wrapper ra ngoài.
4. `catch` ở `main` nhận wrapper **sau** khi phần `finally` trong `doWork` hoàn tất.
5. `getCause()` là ngoại lệ gốc; không lẫn với `getSuppressed()` dùng cho lỗi đóng tài nguyên.

Để đơn giản ví dụ, `Resource.close()` không ném checked exception. Với resource thực, thiết kế hợp đồng `close()` tương ứng.

## 10. Trường hợp `return` trong thân try và lỗi đóng

TWR gọi `close()` **trước khi hoàn tất `return` ra caller**. Nếu `close()` thất bại, code có thể không trả về giá trị đã chuẩn bị.

Tạo **`TwrReturnCloseDemo.java`**:

```java
import java.io.IOException;

public class TwrReturnCloseDemo {
    static final class CloseFails implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Close");
            throw new IOException("Lỗi đóng");
        }
    }

    static String calculate() {
        try (CloseFails resource = new CloseFails()) {
            System.out.println("Chuẩn bị return");
            return "SUCCESS";
        } catch (IOException e) {
            System.out.println("Catch: " + e.getMessage());
            return "FALLBACK";
        } finally {
            System.out.println("Finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + calculate());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwrReturnCloseDemo.java
java TwrReturnCloseDemo
```

Stdout:

```text
Chuẩn bị return
Close
Catch: Lỗi đóng
Finally
Kết quả: FALLBACK
```

Bởi `close()` ném lỗi, lời gọi không trả về `"SUCCESS"` như thân `try` đã chuẩn bị. `catch(IOException)` chọn một đường trả về khác; `finally` thực hiện trước khi `calculate()` trả `"FALLBACK"` cho caller.

**Trong thực tế**, chỉ dùng một “fallback” nếu thật sự có cách phục hồi hợp lệ. Nếu đóng writer thất bại, không nên trả “thành công” giả chỉ vì có một `catch`. Ví dụ này chứng minh thứ tự điều khiển, không khuyến khích nuốt lỗi đóng.

## 11. Phạm vi biến resource: khác nhau giữa khai báo trong `try` và biến bên ngoài

### 11.1. Java 7: tài nguyên khai báo trong ngoặc `try (...)`

```java
try (java.io.BufferedReader reader = openReader()) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    // reader KHÔNG nằm trong scope ở đây.
    System.out.println(e.getMessage());
} finally {
    // reader KHÔNG nằm trong scope ở đây.
    System.out.println("Hoàn tất");
}
```

Đây là đoạn minh họa, giả định `openReader()` trả `BufferedReader` và có hợp đồng checked exception phù hợp. Biến `reader` khai báo trong resource specification thuộc phạm vi resource specification và thân TWR; **không thể truy cập trực tiếp trong `catch`/`finally` gắn ngoài**.

Ví dụ cố ý sai:

```java
try (java.io.BufferedReader reader = openReader()) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    reader.close(); // Không biên dịch: reader không còn nằm trong scope.
}
```

Không cần tìm cách gọi thêm `reader.close()` ở handler; TWR đã đảm nhiệm việc đóng (nếu resource đã khởi tạo thành công).

### 11.2. Java 9+: biến đã khai báo bên ngoài và effectively final

Từ Java 9, cú pháp sau hợp lệ với biến `final` hoặc **effectively final**:

```java
java.io.BufferedReader reader = openReader();
try (reader) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    System.out.println("Lỗi: " + e.getMessage());
} finally {
    System.out.println("Đã rời try");
}
```

Biến `reader` vẫn nằm trong phạm vi từ vựng bên ngoài, nên handler có thể tham chiếu đến biến đó nếu cần quan sát thuộc tính. **Nhưng đối tượng đã được TWR đóng khi rời khối**, không được hiểu việc biến còn tồn tại đồng nghĩa resource vẫn mở.

Một bất tiện của việc mở resource **trước** `try (reader)`: nếu code giữa lời gọi mở và việc vào TWR phát sinh exception, resource có thể chưa được chuyển quyền quản lý cho TWR. Khi có thể, khai báo và khởi tạo ngay trong `try (...)` thường giảm rủi ro.

**Lưu ý phiên bản:** TWR xuất hiện từ Java 7; dùng biến có sẵn `try (reader)` được hỗ trợ từ Java 9; cú pháp `var` trong khai báo biến local/resource xuất hiện từ Java 10. Trên Java 17 đều có thể dùng đúng ngữ cảnh.

## 12. `catch`, `finally` và checked exception từ `close()`

`AutoCloseable.close()` khai báo `throws Exception`. Một lớp thực thi có thể thu hẹp loại lỗi, ví dụ `Closeable.close() throws IOException` hoặc `close()` không khai báo checked exception nào.

Compiler xét checked exception có thể phát sinh từ:

1. Resource initializer (constructor hoặc method tạo resource).
2. Lời gọi/câu lệnh bên trong thân `try`.
3. `close()` trên kiểu resource mà compiler nhìn thấy.

Ví dụ:

```java
static void useResource() throws Exception {
    try (AutoCloseable resource = acquire()) {
        System.out.println("Sử dụng");
    } finally {
        System.out.println("Kết thúc");
    }
}
```

Đây là phương thức minh họa cần định nghĩa `acquire()`. `finally` có mặt nhưng **không bắt** checked exception; vì kiểu tĩnh của resource là `AutoCloseable`, `close()` có thể ném `Exception`, nên khai báo `throws Exception` có thể cần thiết.

Nếu không muốn khai báo rộng, có thể bắt loại phù hợp với API:

```java
static void run() {
    try (MyResource resource = new MyResource()) {
        System.out.println("Thao tác");
    } catch (java.io.IOException e) {
        System.out.println("I/O thất bại: " + e.getMessage());
    } finally {
        System.out.println("Kết thúc");
    }
}
```

Mã này **chỉ là minh họa**: giả định `MyResource.close() throws IOException` và constructor không khai báo checked exception khác. Không thể tùy tiện dùng `catch(IOException)` nếu resource và thân không có nguồn checked exception tương thích; compiler sẽ báo “exception IOException is never thrown in body of corresponding try”.

### 12.1. Dùng `catch(Exception)` có cần thiết không?

Không mặc định. Nếu resource chỉ có khả năng ném `IOException`, handler cụ thể thường đủ. Nếu cần xử lý nhiều loại checked exception với **cùng** chính sách, có thể dùng multi-catch:

```java
try (Resource resource = acquire()) {
    process(resource);
} catch (java.io.IOException | java.sql.SQLException e) {
    reportFailure(e);
} finally {
    markFinished();
}
```

Ví dụ phụ thuộc vào định nghĩa `Resource`/`acquire`/`process` thực sự có khả năng ném cả hai loại. `catch(Exception)` rộng hơn multi-catch vì còn bắt nhiều unchecked exceptions. Nếu đặt handler rộng, cần bảo đảm nó không nuốt lỗi và giả rằng công việc hoàn tất thành công.

## 13. Nested try-with-resources và vị trí xử lý

Một chương trình có thể có TWR bên trong TWR khác, mỗi khối sở hữu resource riêng.

Ví dụ:

```java
try (OuterResource outer = openOuter()) {
    try (InnerResource inner = openInner(outer)) {
        use(inner);
    } catch (InnerException e) {
        handleInner(e);
    } finally {
        afterInner();
    }
} catch (OuterException e) {
    handleOuter(e);
} finally {
    afterOuter();
}
```

Đây là sơ đồ mã giả theo cú pháp Java; các kiểu và method chưa được định nghĩa.

Thứ tự nếu cả hai resource đã được mở và đường thực thi đi bình thường:

1. Thân TWR trong chạy.
2. `inner.close()`.
3. `finally` trong chạy (và `catch` trong nếu lỗi phù hợp).
4. Thân TWR ngoài tiếp tục hoặc kết thúc.
5. `outer.close()`.
6. `catch`/`finally` ngoài chạy theo điều kiện.

Nếu handler trong **ném lại** exception hoặc ném wrapper, exception có thể lan ra phạm vi ngoài **sau** phần dọn dẹp trong. Khi outer resource đóng và phát sinh thêm exception, logic primary/suppressed được áp dụng theo các mức TWR liên quan. Không thể mặc định hai `finally` chạy cùng lúc hoặc handler ngoài được chọn trước handler trong.

### 13.1. Exception được ném trong `catch` có được handler cùng cấp bắt tiếp không?

**Không.** Các `catch` đi kèm cùng một `try` là những handler thay thế đối với ngoại lệ thoát khỏi phần TWR được bảo vệ. Một exception **mới** do chính handler ném sẽ không được những `catch` tiếp theo của cùng cấu trúc tự bắt; nó tiếp tục ra một `try` bao ngoài hoặc caller.

Ví dụ trong `TwrCatchRethrowFinallyDemo`: handler trong tạo `IllegalStateException` mới, phần `finally` vẫn chạy, còn handler ở `main` mới nhận wrapper.

### 13.2. `finally` bên ngoài TWR khác với `finally` gắn cùng TWR

Đôi khi muốn tách khối quản lý resource và handler:

```java
try {
    try (Resource resource = acquire()) {
        perform(resource);
    }
} catch (Exception e) {
    report(e);
} finally {
    after();
}
```

Đây là mẫu minh họa. TWR trong tự đóng resource khi thoát; `catch` của outer try được xét sau khi inner TWR hoàn tất. Kết quả về thứ tự **vẫn là close trước catch/finally ngoài**, nhưng ranh giới mỗi cấu trúc cần được đọc đúng để suy luận nguồn lỗi.

## 14. Đừng nhầm tự động đóng với transaction và khôi phục trạng thái

TWR **chỉ** quản lý những resource triển khai `AutoCloseable` được khai báo/tham chiếu trong resource specification. Nó không tự cung cấp:

- atomicity cho nhiều phép ghi dữ liệu;
- rollback thay đổi trên các đối tượng trong heap;
- rollback giao dịch JDBC sau một lỗi, trừ khi chính giao thức/driver có hành vi riêng và được cấu hình phù hợp;
- bảo đảm một yêu cầu HTTP chưa xử lý ở máy chủ nếu client ném exception;
- dữ liệu đã flush xuống thiết bị lưu trữ một cách bền vững khi mất điện;
- tự thử lại an toàn sau khi kết quả nghiệp vụ chưa chắc chắn.

Ví dụ trong JDBC:

```java
// Mã minh họa, phụ thuộc DataSource và SQL thực tế.
try (java.sql.Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateInventory(connection);
        insertOrder(connection);
        connection.commit();
    } catch (java.sql.SQLException e) {
        connection.rollback();
        throw e;
    }
} catch (java.sql.SQLException e) {
    reportFailure(e);
} finally {
    markRequestFinished();
}
```

Ở đây **`rollback()` là lời gọi tường minh**, không phải do TWR tự chèn. Nếu `rollback()` cũng ném lỗi, cần chiến lược chẩn đoán, nhất là khi đã có lỗi gốc. Hành vi khi đóng connection, trả connection về pool, hay tình trạng giao dịch khi process chết phụ thuộc API/driver/pool; không suy luận transaction an toàn chỉ từ cú pháp `try(connection)`.

Trong hệ thống thực tế, nên đặt trách nhiệm rõ ràng: transaction layer quyết định commit/rollback; TWR quản lý vòng đời connection; handler báo trạng thái thất bại cho caller và phần `finally` xử lý những công việc kết thúc không thuộc transaction.

## 15. Những sai lầm thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Thân `try` ném lỗi thì `catch` chạy trước khi resource đóng.” | TWR đóng các resource đã khởi tạo thành công **trước** handler gắn trực tiếp. |
| “Có TWR thì không cần bao giờ có `catch`.” | TWR tự đóng; nếu tầng này cần xử lý lỗi, vẫn dùng `catch` phù hợp. |
| “Có TWR thì `finally` bị cấm.” | `finally` vẫn hợp lệ và hữu ích cho công việc hoàn tất khác. |
| “Phải viết `finally { resource.close(); }`.” | Resource đã được TWR tự đóng; đóng lặp có thể gây side effect/lỗi. |
| “Lỗi `close()` không thể đi vào `catch`.” | Nếu close lỗi và exception đó trở thành primary, handler tương thích sẽ nhận. |
| “Thân và close đều lỗi thì catch bắt lỗi close.” | Thông thường lỗi thân là primary, lỗi close là suppressed. |
| “`getSuppressed()` giống `getCause()`.” | Hai quan hệ khác nhau; suppressed mô tả lỗi phụ, cause mô tả nguyên nhân của wrapper. |
| “Đã vào `catch` thì `finally` không chạy.” | `finally` vẫn thực hiện theo đường điều khiển Java bình thường. |
| “`finally` được phép `return` an toàn sau exception.” | `return` trong `finally` có thể che exception; nên tránh. |
| “Exception ném từ `finally` được `catch` trước đó bắt.” | Không; handler cùng cấp không tự nhận lỗi phát sinh ở `finally` của nó. |
| “Biến resource khai báo trong `try(...)` dùng được ở `catch`.” | Không, phạm vi biến resource khai báo trong specification không kéo dài sang handler gắn ngoài. |
| “Biến dùng trong `try(reader)` Java 9 vẫn chắc còn mở sau đó.” | Biến còn trong scope, nhưng resource đã đóng. |
| “`catch(IOException)` luôn hợp lệ trong TWR.” | Phải có nguồn checked `IOException` có thể phát sinh từ initializer, thân hoặc close. |
| “TWR tự rollback file, database, HTTP.” | TWR tự gọi `close()`; transaction và trạng thái nghiệp vụ là trách nhiệm khác. |
| “Đóng luôn tài nguyên do caller truyền vào là an toàn.” | Cần thỏa thuận ownership; đóng resource chia sẻ có thể phá code phía ngoài. |
| “`catch(Throwable)` giúp chương trình vượt qua mọi lỗi JVM.” | Có thể bắt `Error` về mặt kiểu nhưng không bảo đảm phục hồi an toàn hay process luôn tồn tại. |

## 16. Bài tập thực hành

### Bài 1 — Dự đoán thứ tự

Không chạy chương trình, hãy dự đoán stdout của `TwrCatchFinallyOrderDemo` với `run(false)` rồi `run(true)`. Chỉ ra chính xác vị trí các dòng `Đóng R`, `Catch: ...` và `Finally: ...`. Sau đó chạy để đối chiếu.

### Bài 2 — Lỗi chỉ ở `close()`

Chạy `TwrCloseFailureDemo`. Sửa `close()` để không ném exception; giải thích vì sao handler `catch(IOException)` có thể trở nên không hợp lệ **nếu không còn nguồn checked IOException khác**. Hãy đổi code hợp lý và không thêm handler checked thừa.

### Bài 3 — Primary và suppressed

Chạy `TwrSuppressedWithFinallyDemo`. Đổi lỗi thân từ `IllegalStateException` sang `IOException`, đồng thời giữ `close()` ném `IOException`. Dự đoán primary message, suppressed count và handler nào nhận exception. Viết test xác nhận `getSuppressed()[0].getMessage()`.

### Bài 4 — Thêm resource thứ ba

Thêm `Named c = new Named("C")` vào `TwrMultipleResourcesDemo`. Dự đoán thứ tự `Mở A/B/C`, `Đóng C/B/A`, primary là lỗi đóng của resource nào và thứ tự các suppressed. Sau đó kiểm tra chương trình bằng Java 17.

### Bài 5 — `return` bị lỗi đóng thay thế

Trong `TwrReturnCloseDemo`, đổi `CloseFails.close()` thành method in `Close` nhưng không ném IOException. Điều chỉnh `catch` nếu compiler yêu cầu. Phân biệt output khi resource đóng thành công với output khi `close()` phát sinh checked exception.

### Bài 6 — Exception ném trong handler

Trong `TwrCatchRethrowFinallyDemo`, bỏ truyền `e` vào constructor `IllegalStateException`. Quan sát xem `getCause()` có còn là `IllegalArgumentException` không. Vì sao cần giữ cause khi đổi exception tầng thấp thành wrapper tầng cao?

### Bài 7 — Phạm vi biến resource

Viết hai phiên bản: Java 7 khai báo `BufferedReader r` ngay trong `try(...)`, và Java 9+ khai báo biến trước rồi dùng `try(r)`. So sánh việc tham chiếu tới `r` trong `catch`/`finally`, sau đó trả lời vì sao **dù biến còn tồn tại thì resource vẫn đã được đóng**.

### Bài 8 — Thiết kế với ownership

Một method nhận `InputStream` từ caller và chỉ đọc vài byte. Nên tự đóng input bằng TWR hay trả quyền đóng về caller? Đưa ra hai hợp đồng API hợp lý tương ứng, mô tả rõ trách nhiệm đóng và viết test theo hợp đồng đã chọn.

### Bài 9 — Transaction không tự rollback

Trong ví dụ JDBC, nếu cập nhật tồn kho thành công nhưng chèn đơn hàng thất bại, phần nào của code chịu trách nhiệm rollback? `catch(SQLException)` trong khối transaction được gọi ở đâu, TWR đóng connection ở đâu, `finally` có nên dùng để commit không? Giải thích vì sao không được chỉ đóng connection rồi coi như đã rollback chắc chắn.

## 17. Checklist vận dụng TWR + catch + finally

- [ ] Resource thật sự triển khai `AutoCloseable`/`Closeable` và tầng hiện tại có quyền sở hữu để đóng chưa?
- [ ] Tôi đã viết `try(...)` khai báo/tái sử dụng resource hợp lệ với phiên bản Java của dự án chưa?
- [ ] Tôi nhớ **close trước catch và finally** đối với cấu trúc TWR gắn handler trực tiếp chưa?
- [ ] Tôi đã xét thứ tự **đóng ngược** khi có nhiều resource chưa?
- [ ] Nếu khởi tạo resource thứ hai lỗi, resource thứ nhất vẫn được TWR dọn đúng chưa?
- [ ] Các handler có thể nhận lỗi từ initializer, thân và `close()` không?
- [ ] Nếu thân và close cùng thất bại, tôi có biết cách xem `getSuppressed()` mà không mất primary không?
- [ ] Tôi có đặt `catch` theo kiểu phù hợp, cụ thể trước tổng quát chưa?
- [ ] `finally` chỉ làm công việc kết thúc khác, không đóng lại resource đã được TWR quản lý chứ?
- [ ] Tôi đã tránh `return` và ngoại lệ mới không cần thiết trong `finally` chưa?
- [ ] Tôi có biết `catch` cùng cấp không bắt exception mới ném từ `catch` hoặc `finally` của chính nó không?
- [ ] Tôi không truy cập biến resource ngoài phạm vi khai báo của nó chứ?
- [ ] Tôi đã giải quyết checked exception từ constructor, thân, `close()` theo hợp đồng compiler chưa?
- [ ] Tôi không nhầm tự động `close()` với commit/rollback transaction hay độ bền dữ liệu chưa?
- [ ] Test đã kiểm tra đường thành công, lỗi thân, lỗi đóng, nhiều resource, primary/suppressed, và thứ tự `finally` chưa?

**Kết luận:** TWR giúp sở hữu và đóng tài nguyên đúng quy tắc, `catch` xử lý **exception thoát khỏi phần TWR sau khi đóng**, còn `finally` đảm nhiệm công việc kết thúc độc lập. Hãy ghi nhớ **khởi tạo → thân → đóng → catch phù hợp → finally**, quan sát cả **primary lẫn suppressed** và không để hành động trong `finally` che mất lỗi gốc. Đó là nền tảng để xử lý lỗi Java đáng tin cậy khi có tài nguyên cần giải phóng.