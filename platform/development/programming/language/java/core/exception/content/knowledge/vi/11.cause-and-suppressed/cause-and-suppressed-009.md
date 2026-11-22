# Giữ cả lỗi chính và lỗi cleanup khi quản lý tài nguyên thủ công trong Java

## 1. Mục tiêu học tập

Khi một thao tác thất bại, chương trình có thể cần **dọn dẹp tài nguyên** như stream, tệp, kết nối, khóa hoặc trạng thái tạm. Nếu dọn dẹp cũng ném ngoại lệ, bạn có **hai thông tin lỗi quan trọng**: lỗi làm công việc thất bại ban đầu và lỗi phát sinh khi dọn dẹp.

Một `finally` tưởng như đúng có thể khiến lỗi cleanup **che mất lỗi chính**:

```java
try {
    doWork();        // Ném IOException("work failed").
} finally {
    resource.close(); // Cũng ném IOException("close failed").
}
```

Đây là **mảnh minh họa** phụ thuộc `doWork()` và `resource` có sẵn. Nếu cả hai dòng đều ném, ngoại lệ thoát khỏi `finally` có thể thay thế ngoại lệ đang lan truyền từ `try`; người gọi chỉ quan sát trực tiếp lỗi `close failed`, còn `work failed` có thể bị mất khỏi chuỗi chẩn đoán.

Muốn giữ cả hai, hãy ưu tiên `try-with-resources` khi phù hợp. Nếu phải quản lý thủ công, hãy xác định **ngoại lệ chính** (*primary*) và đính kèm lỗi dọn dẹp vào nó qua `Throwable.addSuppressed(...)`. Khi công việc thành công nhưng cleanup lỗi, **lỗi cleanup phải được truyền lên hoặc xử lý**, thay vì âm thầm bị bỏ qua.

Sau bài học, bạn có thể:

- Phân biệt lỗi primary, lỗi cleanup, `cause` và `suppressed`.
- Giải thích vì sao `finally { close(); }` thuần túy có thể che mất lỗi đang chờ.
- Viết một mẫu cleanup thủ công đúng cho cả đường thành công và đường thất bại.
- Bảo toàn thứ tự khi nhiều tài nguyên được đóng; tiếp tục cố đóng tài nguyên còn lại nếu một `close()` gặp lỗi.
- Quản lý đúng thất bại khi **khởi tạo tài nguyên thứ hai** hoặc **trả về sớm**.
- Tránh bỏ qua `RuntimeException`/`Error` khi chỉ bắt `IOException`; hiểu giới hạn của `catch (Throwable)`.
- Giữ nguyên stack trace, cause và suppressed thay vì chỉ sao chép thông điệp.
- Biết khi nào nên dùng `try-with-resources`, khi nào cleanup thủ công thật sự có giá trị.

Ví dụ biên dịch/chạy với Java 17+, không phụ thuộc hệ thống tệp hoặc mạng, nên có `stdout` xác định.

## 2. Phân biệt lỗi chính và lỗi dọn dẹp

Giả sử một thao tác gửi dữ liệu làm hai việc:

1. `writeData()` ghi dữ liệu và thất bại: `IOException("write failed")`.
2. Khi kết thúc, `close()` cũng thất bại: `IOException("close failed")`.

Hai lỗi đều quan trọng, nhưng chúng không có cùng vai trò:

```text
operation starts
      |
      v
writeData() throws IOException("write failed")
      |
      |  lỗi chính / primary
      v
cleanup: close() throws IOException("close failed")
      |
      |  lỗi bổ sung / suppressed
      v
Caller nhận IOException("write failed")
  + getSuppressed()[0] = IOException("close failed")
```

**Lỗi chính** là lý do ban đầu khiến đơn vị công việc không hoàn thành. **Lỗi cleanup** là một thất bại tiếp theo trong lúc giải phóng tài nguyên. Java có cơ chế `Throwable.addSuppressed(Throwable)` để liên kết lỗi cleanup với lỗi chính mà không thay thế nó.

Điểm cần hiểu:

- `primary.addSuppressed(cleanup)` **không ném** `cleanup`; nó ghi nhận lỗi bổ sung trên đối tượng `primary`.
- `primary.getSuppressed()` trả mảng `Throwable[]` chứa các lỗi đã được ghi nhận.
- `getCause()` thể hiện quan hệ nguyên nhân khi một ngoại lệ được bọc bằng ngoại lệ khác; nó **không đồng nghĩa** với `getSuppressed()`.
- Nếu công việc thành công nhưng cleanup gặp lỗi, lỗi cleanup thường trở thành **primary**, vì trước đó không có lỗi chính.
- “Suppressed” nghĩa là **không thay thế primary**, không phải “không đáng quan tâm”.

Bảng quyết định:

| Công việc | Cleanup | Kết quả nên quan sát |
| --- | --- | --- |
| Thành công | Thành công | Hoàn thành bình thường |
| Thất bại A | Thành công | Ném A |
| Thành công | Thất bại B | Ném B |
| Thất bại A | Thất bại B | Ném A, gắn B bằng `addSuppressed` |

Đây là chính sách giữ lỗi gốc mà `try-with-resources` cung cấp cho tài nguyên `AutoCloseable`.

## 3. Vì sao `finally` thủ công có thể đánh mất lỗi đầu tiên?

Java thực thi `finally` khi rời `try` theo đường bình thường, `return` hoặc exception. Nếu `finally` tự hoàn thành đột ngột bằng một ngoại lệ mới, lý do hoàn thành đột ngột từ `try` có thể bị **thay thế**.

Tạo tệp **`LosingPrimaryDemo.java`**:

```java
import java.io.IOException;

public class LosingPrimaryDemo {
    static void run() throws IOException {
        try {
            throw new IOException("work failed");
        } finally {
            throw new IOException("cleanup failed");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException failure) {
            System.out.println("observed=" + failure.getMessage());
            System.out.println("suppressed="
                    + failure.getSuppressed().length);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac LosingPrimaryDemo.java
java LosingPrimaryDemo
```

`stdout`:

```text
observed=cleanup failed
suppressed=0
```

Cơ chế:

1. `try` ném `IOException("work failed")`.
2. Trước khi ngoại lệ ấy thoát, `finally` chạy.
3. `finally` ném `IOException("cleanup failed")`.
4. Ngoại lệ thứ hai trở thành ngoại lệ quan sát được; lỗi công việc không được tự đính kèm `suppressed`.
5. `getSuppressed().length` của ngoại lệ mới là 0 trong ví dụ này.

Không nên cố “sửa” bằng cách đặt `return` trong `finally`: `return` cũng có thể **nuốt hoàn toàn ngoại lệ** đang chờ. Một `finally` chuyên dọn dẹp không nên thay đổi lý do thoát một cách bất ngờ.

### Vì sao bắt rồi chỉ log cleanup cũng không đủ?

Cách viết:

```java
try {
    doWork();
} finally {
    try {
        resource.close();
    } catch (IOException cleanupFailure) {
        System.err.println(cleanupFailure.getMessage());
    }
}
```

Đây là **mảnh minh họa**. Nó không làm lỗi close thay thế lỗi của `doWork()`, nhưng có thể **bỏ qua lỗi close về mặt hợp đồng**: nếu công việc thành công mà close thất bại, phương thức vẫn có thể hoàn thành bình thường. Với luồng ghi, lỗi close/flush có thể là lỗi nghiêm trọng liên quan dữ liệu chưa được ghi ra an toàn.

Để giữ cả hai lỗi một cách có cấu trúc, cần phân biệt **đã có primary hay chưa**. Nếu có, đính kèm cleanup; nếu chưa, cleanup trở thành lỗi báo ra.

## 4. `addSuppressed` và `getSuppressed` trong mẫu quản lý thủ công

API trên `java.lang.Throwable`:

```java
primary.addSuppressed(cleanupFailure);
Throwable[] extras = primary.getSuppressed();
```

Đây là **mảnh mã** với hai biến `Throwable` đã tồn tại.

Các quy tắc cần nắm:

- `addSuppressed` **thêm một đối tượng `Throwable`** vào lỗi đang nhận lời gọi.
- Không được truyền `null` (gây `NullPointerException`) hoặc chính đối tượng primary vào `primary.addSuppressed(primary)` (gây `IllegalArgumentException`).
- Với một exception được tạo bình thường, suppression được bật theo mặc định. Một lớp throwable đặc biệt có thể tắt suppression qua constructor protected phù hợp, khi đó `getSuppressed()` vẫn là mảng rỗng.
- `getSuppressed()` không trả `null`. Mảng kết quả là bản sao, nhưng chứa tham chiếu tới các đối tượng `Throwable` đã gắn.
- Đính kèm suppressed không tự `throw` lỗi chính. Bạn vẫn phải **ném tiếp primary**, trả trạng thái thất bại hoặc xử lý nó theo hợp đồng.
- Không nên thêm một ngoại lệ cleanup vào primary nhiều lần nếu nó đã được `try-with-resources` ghi nhận tự động.
- Một suppressed exception cũng có thể có `cause` và suppressed riêng; đừng chỉ đọc message của primary rồi kết luận không còn lỗi nào khác.

### Mẫu thuật toán cốt lõi

```text
primary = null
thử thực hiện công việc
    nếu công việc lỗi:
        primary = lỗi đó

thử dọn dẹp
    nếu dọn dẹp lỗi:
        nếu primary chưa có:
            primary = lỗi dọn dẹp
        ngược lại:
            gắn lỗi dọn dẹp thành suppressed của primary

nếu primary tồn tại:
    ném primary hoặc báo thất bại theo hợp đồng
```

Đây là **pseudocode**, không phải mã Java chạy trực tiếp. Điểm đặc biệt so với `finally` thuần túy là **không để cleanup exception vô tình thay primary**.

## 5. Ví dụ Java đầy đủ: quản lý một resource theo bốn kịch bản

Tạo tệp **`ManualCleanupDemo.java`**:

```java
import java.io.IOException;

public class ManualCleanupDemo {
    static class TrackedResource implements AutoCloseable {
        private final boolean closeFails;

        TrackedResource(boolean closeFails) {
            this.closeFails = closeFails;
        }

        void work(boolean fail) throws IOException {
            if (fail) {
                throw new IOException("work failed");
            }
        }

        @Override
        public void close() throws IOException {
            System.out.println("closing");
            if (closeFails) {
                throw new IOException("close failed");
            }
        }
    }

    static void execute(boolean workFails, boolean closeFails)
            throws IOException {
        TrackedResource resource = new TrackedResource(closeFails);
        Throwable primary = null;

        try {
            resource.work(workFails);
        } catch (Throwable failure) {
            primary = failure;
            throw failure;
        } finally {
            if (primary != null) {
                try {
                    resource.close();
                } catch (Throwable cleanup) {
                    if (cleanup != primary) {
                        primary.addSuppressed(cleanup);
                    }
                }
            } else {
                resource.close();
            }
        }
    }

    static void show(String label, boolean workFails,
                     boolean closeFails) {
        System.out.println("-- " + label + " --");
        try {
            execute(workFails, closeFails);
            System.out.println("success");
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            for (Throwable extra : failure.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        show("both ok", false, false);
        show("work only", true, false);
        show("close only", false, true);
        show("both fail", true, true);
    }
}
```

```bash
javac ManualCleanupDemo.java
java ManualCleanupDemo
```

`stdout` chính xác:

```text
-- both ok --
closing
success
-- work only --
closing
primary=work failed
-- close only --
closing
primary=close failed
-- both fail --
closing
primary=work failed
suppressed=close failed
```

**Từng nhánh của `execute`:**

1. **Thành công cả hai:** `work()` hoàn thành, biến `primary` vẫn null; `finally` gọi `close()` thành công; method kết thúc bình thường.
2. **Chỉ work lỗi:** `catch (Throwable failure)` ghi nhận lỗi chính và ném lại. `finally` đóng thành công; IOException cũ tiếp tục lan ra.
3. **Chỉ close lỗi:** chưa có primary, nên `resource.close()` được gọi trong nhánh `else` và ném `IOException("close failed")` như lỗi chính.
4. **Cả hai lỗi:** primary là chính đối tượng `IOException("work failed")`. Trong nhánh cleanup, IOException từ `close()` được bắt và thêm vào `primary` bằng `addSuppressed`. `finally` hoàn thành bình thường, nên Java tiếp tục ném **đối tượng primary ban đầu** cùng danh sách suppressed.

### Vì sao `catch (Throwable)` ở đây vẫn biên dịch với `throws IOException`?

Đây là cơ chế **precise rethrow** (Java 7+). Tham số `failure` trong `catch` không bị gán lại, nên trình biên dịch có thể dựa trên những checked exception mà `try` thực sự có thể ném. Trong ví dụ, `resource.work(...)` khai báo `IOException`; các ngoại lệ unchecked có thể được ném mà không cần thêm `throws`. Do đó `throw failure;` không buộc chữ ký `execute` phải ghi `throws Throwable`.

Đoạn này chủ ý sử dụng `catch (Throwable)` **ở bên trong vùng bảo toàn lỗi** để không bỏ sót việc gắn lỗi cleanup vào một primary thuộc `RuntimeException` hoặc `Error`. Nó **không có nghĩa** ứng dụng nên bắt rồi phục hồi mọi `Error`. Lệnh `throw failure;` truyền lỗi ban đầu ra ngoài; mã không cố tiếp tục thực hiện nghiệp vụ sau sự cố.

Cần thận trọng hơn nữa trong sản phẩm:

- Nếu một `Error` nghiêm trọng xảy ra (ví dụ thiếu bộ nhớ), thao tác tạo suppressed, ghi log hoặc cleanup có thể cũng không an toàn/không thực hiện được.
- Một số chương trình muốn dùng kiểu cụ thể hơn để giảm mức bắt. Tuy nhiên, chỉ bắt `IOException` sẽ không bảo toàn chính sách suppressed cho một `RuntimeException` hoặc `Error` bất ngờ trong phần thân.
- Mã tổng quát phải xét **toàn bộ checked exception** do công việc và `close()` có thể ném, không áp cứng `IOException` của ví dụ.
- `try-with-resources` đã giải quyết phần logic này và thường là giải pháp dễ kiểm chứng hơn.

### Tại sao cần kiểm tra `cleanup != primary`?

`addSuppressed` cấm một `Throwable` suppress chính nó. Mặc dù ít gặp, resource tự định nghĩa có thể ném **chính đối tượng Throwable đang là primary**. Trong mẫu thủ công, `if (cleanup != primary)` tránh tạo một `IllegalArgumentException` mới chỉ vì self-suppression, nhờ đó không vô tình che lỗi gốc.

**Không suy ra** mẫu này luôn tái hiện mọi tình huống bytecode của `try-with-resources`. Đây là chính sách bảo toàn lỗi **có chủ đích** của ví dụ; JLS định nghĩa ngữ nghĩa chính thức của TWR, và khi cùng một đối tượng được ném trong các tình huống bất thường, xử lý self-suppression của mã thủ công cần được thiết kế rõ ràng.

## 6. Mẫu tối giản khi chỉ có `IOException`: hiểu rõ giới hạn

Nếu một API chắc chắn chỉ muốn xử lý lỗi checked I/O và không cần mô phỏng hoàn toàn các trường hợp unchecked, bạn có thể thấy mã sau:

```java
IOException primary = null;
try {
    performIo();
} catch (IOException failure) {
    primary = failure;
} finally {
    try {
        resource.close();
    } catch (IOException cleanup) {
        if (primary == null) {
            primary = cleanup;
        } else if (primary != cleanup) {
            primary.addSuppressed(cleanup);
        }
    }
}
if (primary != null) {
    throw primary;
}
```

Đây là **mảnh mã minh họa** trong phương thức `throws IOException`, giả định `performIo()` và `resource` phù hợp. Nó mô tả cách gom một lỗi I/O chính và một lỗi I/O cleanup; tuy nhiên **không phải phiên bản tổng quát an toàn cho mọi Throwable**.

**Giới hạn nguy hiểm:** nếu `performIo()` ném một `RuntimeException` hoặc `Error` mà `catch (IOException)` không bắt, khối `finally` vẫn chạy. Nếu `close()` ném `IOException`, handler cleanup sẽ bắt IOException và ghi vào biến `primary` (đang null). Vì control flow đang thoát do lỗi unchecked nên đoạn `if (primary != null)` **sau finally không chạy**, và ngoại lệ cleanup không được gắn vào unchecked primary. Lỗi công việc vẫn truyền đi, nhưng bạn đã bỏ mất chẩn đoán về cleanup.

Nếu yêu cầu là **giữ cả lỗi chính và lỗi cleanup bất kể primary thuộc nhánh nào**, hãy dùng mẫu `catch (Throwable)` rồi ném lại (trong phạm vi phù hợp), hoặc `try-with-resources`.

Đừng giới thiệu mẫu tối giản này như một bản thay thế hoàn chỉnh cho TWR.

## 7. Tài nguyên `AutoCloseable` và checked exception

`AutoCloseable.close()` khai báo `throws Exception`; các implementation có thể thu hẹp loại ngoại lệ trong override, ví dụ `Closeable.close() throws IOException` hoặc một lớp đóng không ném checked exception.

Khi viết cleanup thủ công, **kiểu tĩnh** của resource ảnh hưởng tới nghĩa vụ bắt/khai báo:

```java
AutoCloseable resource = obtainResource();
try {
    useResource(resource);
} finally {
    resource.close(); // Có thể ném Exception theo AutoCloseable.
}
```

Đây là mảnh minh họa. Phương thức chứa nó phải xử lý hoặc khai báo `Exception`, trừ khi được tổ chức lại phù hợp. Không thể giả định mọi `AutoCloseable` chỉ ném `IOException`.

Ngược lại, trong `ManualCleanupDemo`, kiểu resource là `TrackedResource` với `close() throws IOException` nên `execute` chỉ cần khai báo checked `IOException`.

Một số lưu ý:

- `close()` có thể ném unchecked exception dù chữ ký chỉ liệt kê checked exception; xem contract của implementation.
- `close()` có thể có side effect và không nhất thiết idempotent với mọi `AutoCloseable`.
- Không dùng `catch (Exception)` rồi trả kết quả thành công nếu cleanup thất bại có ý nghĩa đối với dữ liệu.
- `ThreadDeath` và những `Error` nghiêm trọng không nên trở thành điều kiện phục hồi mặc định; cơ chế suppress chỉ bảo toàn thông tin lỗi trong khi vẫn truyền primary ra ngoài.

## 8. Quản lý **nhiều** tài nguyên thủ công: đóng hết và giữ thứ tự

Khi có hai tài nguyên độc lập, cleanup tốt thường cố đóng cả hai theo thứ tự ngược với thứ tự chúng được sở hữu/khởi tạo thành công. Một `finally` đơn giản như sau **có vấn đề**:

```java
finally {
    second.close();
    first.close();
}
```

Nếu `second.close()` ném, Java bỏ qua lệnh `first.close()`. Hậu quả: tài nguyên đầu tiên có thể bị leak. Hơn nữa, lỗi close thứ hai có thể che mất lỗi từ phần thân.

Một mẫu có kiểm soát là:

1. Giữ một biến `Throwable primary` đại diện cho lỗi ban đầu (nếu có).
2. Đóng `second`, nếu lỗi thì thêm nó vào primary hoặc trở thành primary nếu chưa có.
3. **Bất kể bước 2 có lỗi**, tiếp tục đóng `first`.
4. Ghi lại mọi lỗi sau thành suppressed của primary hiện hành.
5. Sau cleanup, ném lỗi primary hoặc trả kết quả nếu không có lỗi.

Đây cũng là cơ chế trực giác của `try-with-resources` khi có nhiều resource.

### Chương trình chạy được: nhiều lần đóng đều thất bại

Tạo file **`ManualMultipleResourcesDemo.java`**:

```java
import java.io.IOException;

public class ManualMultipleResourcesDemo {
    static class Resource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Resource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static Throwable closeKeepingPrimary(
            Resource resource, Throwable primary) {
        if (resource == null) {
            return primary;
        }

        try {
            resource.close();
        } catch (Throwable cleanup) {
            if (primary == null) {
                return cleanup;
            }
            if (cleanup != primary) {
                primary.addSuppressed(cleanup);
            }
        }
        return primary;
    }

    static void execute(boolean failBody) throws Throwable {
        Resource first = new Resource("first", true);
        Resource second = new Resource("second", true);

        Throwable primary = null;
        try {
            System.out.println("body");
            if (failBody) {
                throw new IOException("body failed");
            }
        } catch (Throwable failure) {
            primary = failure;
        } finally {
            primary = closeKeepingPrimary(second, primary);
            primary = closeKeepingPrimary(first, primary);
        }

        if (primary != null) {
            throw primary;
        }
    }

    public static void main(String[] args) {
        for (boolean failBody : new boolean[] {true, false}) {
            System.out.println("-- failBody=" + failBody + " --");
            try {
                execute(failBody);
            } catch (Throwable failure) {
                System.out.println("primary=" + failure.getMessage());
                for (Throwable extra : failure.getSuppressed()) {
                    System.out.println("suppressed=" + extra.getMessage());
                }
            }
        }
    }
}
```

```bash
javac ManualMultipleResourcesDemo.java
java ManualMultipleResourcesDemo
```

`stdout`:

```text
-- failBody=true --
body
close second
close first
primary=body failed
suppressed=close second failed
suppressed=close first failed
-- failBody=false --
body
close second
close first
primary=close second failed
suppressed=close first failed
```

Ở trường hợp `failBody=true`, lỗi từ phần thân đã tồn tại. Cả hai lỗi đóng trở thành suppressed theo thứ tự đóng: `second` trước, `first` sau.

Ở trường hợp `failBody=false`, lần đóng đầu tiên gặp lỗi là `second.close()`. Vì chưa có primary, lỗi đóng thứ hai về mặt thời gian trở thành primary; lỗi của `first.close()` được gắn vào nó. Cả hai tài nguyên vẫn được cố đóng ngay cả khi `second.close()` ném.

**Vì sao ví dụ khai báo `throws Throwable`?** Đây là một **mô hình học tập tổng quát** cần truyền lại đúng đối tượng primary bất kể là checked exception, `RuntimeException` hay `Error`. Trong API sản phẩm, `throws Throwable` thường quá rộng. Có thể thu hẹp chữ ký theo kiểu lỗi thực tế, dùng precise rethrow hoặc viết helper quản lý tài nguyên theo các generic exception type, nhưng không nên hy sinh tính đúng để chỉ giảm một từ khóa. Nếu dùng `try-with-resources` với các kiểu resource cụ thể, trình biên dịch thường tự kiểm tra những checked exception hợp lệ cho API tốt hơn.

### Self-suppression và duplicate suppressed

Helper kiểm tra `cleanup != primary` vì không được suppress cùng một đối tượng vào chính nó. Nếu resource liên tục ném **một đối tượng cleanup đã được gắn** ở nhiều chỗ, `addSuppressed` không tự loại trùng; việc quản lý đóng và ownership cần ngăn thêm lỗi trùng vô ý.

Trong mã thực, khi cleanup có thể thay đổi trạng thái của nhiều thành phần, bạn phải quyết định có nên cố dọn tiếp sau một số `Error` nghiêm trọng hay không. Mẫu trên phản ánh một chính sách thu thập lỗi rõ ràng nhưng không hứa phục hồi được mọi sự cố JVM.

## 9. Lỗi ngay trong giai đoạn **khởi tạo** tài nguyên

Một trường hợp dễ bỏ sót là lỗi xảy ra **trước khi vào khối try cuối cùng**:

```java
Resource first = openFirst();   // Thành công.
Resource second = openSecond(); // Ném IOException.
try {
    doWork(first, second);
} finally {
    second.close();
    first.close();
}
```

Đây là **mảnh mã sai thiết kế có chủ ý**: nếu `openSecond()` ném, Java chưa bước vào `try/finally` nên tài nguyên `first` chưa được cleanup theo khối này.

Cách tổ chức tốt hơn là bắt đầu phạm vi bảo vệ **ngay sau khi nhận ownership** của `first`. Nếu phải dùng cleanup thủ công, hãy khởi tạo biến `second` theo trạng thái chưa có, rồi đảm bảo `first` được đóng kể cả khi bước tạo `second` lỗi.

### Ví dụ chạy được: khởi tạo resource thứ hai thất bại

Tạo file **`InitializationCleanupDemo.java`**:

```java
import java.io.IOException;

public class InitializationCleanupDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException(name + " close failed");
        }
    }

    static Resource openSecond() throws IOException {
        throw new IOException("open second failed");
    }

    static void run() throws IOException {
        Resource first = new Resource("first");
        Throwable primary = null;

        try {
            Resource second = openSecond();
            try {
                System.out.println(second);
            } finally {
                second.close();
            }
        } catch (Throwable failure) {
            primary = failure;
            throw failure;
        } finally {
            if (primary != null) {
                try {
                    first.close();
                } catch (Throwable cleanup) {
                    if (cleanup != primary) {
                        primary.addSuppressed(cleanup);
                    }
                }
            } else {
                first.close();
            }
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            for (Throwable extra : failure.getSuppressed()) {
                System.out.println("suppressed=" + extra.getMessage());
            }
        }
    }
}
```

```bash
javac InitializationCleanupDemo.java
java InitializationCleanupDemo
```

`stdout`:

```text
close first
primary=open second failed
suppressed=first close failed
```

Phân tích:

1. `first` được tạo thành công và thuộc quyền sở hữu của `run()`.
2. Bước `openSecond()` ném `IOException("open second failed")`.
3. `second` không được khởi tạo nên khối `try/finally` bên trong **chưa bắt đầu**.
4. `catch (Throwable)` của phạm vi ngoài giữ lỗi khởi tạo làm primary và ném lại.
5. `finally` bên ngoài đóng `first`; việc đóng cũng lỗi và được đính kèm vào primary.
6. Bên gọi thấy lý do khởi tạo thất bại cùng lỗi cleanup của resource đã được mở trước đó.

Mẫu tổ chức thực tế nên đơn giản hơn nếu có thể dùng `try-with-resources`:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    doWork(first, second);
}
```

Đây là **mảnh minh họa**. Khi khởi tạo resource thứ hai thất bại trong header, Java tự đóng resource thứ nhất đã khởi tạo thành công và quản lý lỗi đóng như suppressed.

## 10. `return` trong `try` và lỗi `close()` khi trả về

Một phương thức có thể chuẩn bị giá trị trả về trước khi chạy `finally`. Nếu cleanup ném ngoại lệ, lời gọi **có thể không trả được giá trị** dù biểu thức `return` đã được đánh giá.

Ví dụ:

```java
static String calculate() throws IOException {
    Resource resource = open();
    try {
        return "ok";
    } finally {
        resource.close(); // Có thể ném IOException.
    }
}
```

Đây là mảnh minh họa, cần định nghĩa `Resource` và `open()`. Nếu `close()` thất bại, lỗi đóng thoát ra và **thay thế kết quả trả về dự kiến**. Vì phần thân chỉ có `return "ok"`, chưa có ngoại lệ công việc cần bảo toàn; lỗi đóng trở thành primary. Đó là hành vi phù hợp với chính sách “không báo thành công nếu dọn dẹp thất bại”.

Nếu một biểu thức `return compute();` tự ném ngoại lệ, thì primary xuất hiện ngay lúc đánh giá biểu thức. Cleanup phải giữ lỗi đó và đính kèm lỗi đóng như suppressed nếu phát sinh, thay vì thay thế nguyên nhân ban đầu.

**Không đặt `return` trong `finally`** để cố giữ kết quả: nó có thể che cả lỗi công việc lẫn lỗi cleanup. Với API trả kết quả, nên hoàn thành dọn dẹp rồi mới quyết định thành công, hoặc dùng `try-with-resources` để ngôn ngữ làm đúng việc.

## 11. Resource không thể đóng lần hai và quyền sở hữu tài nguyên

Giữ ngoại lệ không thể tách khỏi **quyền sở hữu tài nguyên**.

- Nếu một phương thức **tự mở** stream và không chuyển ownership ra ngoài, thường nó có trách nhiệm đóng.
- Nếu phương thức chỉ **mượn** `InputStream` hoặc `Connection` từ caller, tự gọi `close()` có thể sai kể cả khi code suppressed chính xác.
- Nếu trả một stream đang mở cho caller, phương thức không nên đóng stream trước khi trả; caller nhận trách nhiệm cleanup sau khi ownership được chuyển.
- Nếu nhiều wrapper cùng quản lý một delegate, đóng wrapper có thể đóng delegate và dẫn tới **double-close**. Một số API cho phép đóng lặp, nhưng `AutoCloseable` không bảo đảm mọi implementation đều idempotent.
- Với JDBC pool, `Connection.close()` có thể mang nghĩa trả logical handle về pool; phải xét scope của transaction hoặc caller đang giữ quyền quản lý.

**Lỗi cleanup của một tài nguyên không thuộc quyền sở hữu hiện tại** là hậu quả của quyết định đóng sai, không phải vấn đề có thể “chữa” chỉ bằng `addSuppressed()`.

Khi tạo mã cleanup thủ công, hãy ghi rõ đối tượng nào đã được khởi tạo thành công và ai có quyền đóng, trước khi tính đến cách bảo toàn exception.

## 12. Khác biệt giữa `cause` và `suppressed` khi bọc lỗi

Đôi khi tầng ứng dụng cần chuyển một `IOException` thành ngoại lệ nghiệp vụ. Hãy **giữ chính đối tượng gốc** làm cause; lỗi cleanup đã gắn trên nó sẽ được giữ nguyên:

```java
try {
    lowLevelOperation();
} catch (IOException original) {
    throw new IllegalStateException("Import failed", original);
}
```

Đây là mảnh minh họa; `lowLevelOperation()` phải được khai báo phù hợp.

Nếu `original.getSuppressed()` có lỗi đóng stream, caller có thể quan sát:

```text
IllegalStateException: Import failed     [wrapper]
    |
    +-- getCause() -> IOException        [primary thấp hơn]
                          |
                          +-- getSuppressed() -> close failure
```

Không cần chuyển thủ công mọi suppressed từ cause sang wrapper nếu chỉ muốn **giữ thông tin lỗi**. Constructor `(message, cause)` đã lưu chính đối tượng gốc cùng danh sách suppressed của nó. Nếu tự sao chép từng suppressed rồi gắn cả trên wrapper, log có thể chứa thông tin lặp hoặc gây hiểu sai quan hệ lỗi.

Trường hợp `cause` và `suppressed`:

| API | Mục đích |
| --- | --- |
| `new DomainException("...", original)` | Bọc lỗi, giữ liên kết nhân quả với lỗi gốc |
| `primary.addSuppressed(cleanup)` | Gắn lỗi dọn dẹp bổ sung mà không đổi primary |
| `wrapper.getCause()` | Đọc nguyên nhân của wrapper |
| `primary.getSuppressed()` | Đọc lỗi phụ trực tiếp gắn trên primary |
| `printStackTrace()` | Trình bày stack trace, cause và suppressed nếu có |

### Ví dụ chạy được: bọc lỗi thủ công vẫn giữ suppressed

Tạo tệp **`WrappedManualCleanupDemo.java`**:

```java
import java.io.IOException;

public class WrappedManualCleanupDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("cleanup failed");
        }
    }

    static class ImportException extends Exception {
        ImportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void importData() throws ImportException {
        Resource resource = new Resource();
        IOException primary = null;

        try {
            throw new IOException("read failed");
        } catch (IOException failure) {
            primary = failure;
        } finally {
            try {
                resource.close();
            } catch (IOException cleanup) {
                if (primary == null) {
                    primary = cleanup;
                } else if (primary != cleanup) {
                    primary.addSuppressed(cleanup);
                }
            }
        }

        if (primary != null) {
            throw new ImportException("cannot import", primary);
        }
    }

    public static void main(String[] args) {
        try {
            importData();
        } catch (ImportException failure) {
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getMessage());
            System.out.println("suppressed="
                    + failure.getCause().getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac WrappedManualCleanupDemo.java
java WrappedManualCleanupDemo
```

`stdout`:

```text
outer=cannot import
cause=read failed
suppressed=cleanup failed
```

Ở đây code cố ý chỉ tạo **checked IOException** trong `try` và `close`, đủ để minh họa việc wrapper giữ cause có suppressed. Đó không phải template tổng quát cho mọi unchecked exception như mẫu ở mục 5. Khi viết helper tổng quát, hãy bảo toàn cả trường hợp phần thân ném `RuntimeException`/`Error`.

## 13. So sánh cleanup thủ công với `try-with-resources`

Một mục tiêu của `try-with-resources` (Java 7+) là tránh phải viết lại logic bảo toàn primary/suppressed phức tạp.

### Thủ công

```java
Resource resource = acquire();
Throwable primary = null;
try {
    work(resource);
} catch (Throwable failure) {
    primary = failure;
    throw failure;
} finally {
    if (primary != null) {
        try {
            resource.close();
        } catch (Throwable cleanup) {
            if (cleanup != primary) {
                primary.addSuppressed(cleanup);
            }
        }
    } else {
        resource.close();
    }
}
```

Đây là **mảnh mã ý tưởng**; phương thức bao ngoài phải xử lý/khai báo các checked exception của `acquire`, `work` và `close`, đồng thời tuân thủ các quy tắc precise rethrow nếu dùng `catch (Throwable)`. Mã cần bao phủ đầy đủ các đường resource acquisition, nhất là nếu nhiều bước khởi tạo có thể lỗi.

### TWR

```java
try (Resource resource = acquire()) {
    work(resource);
}
```

Đây cũng là **mảnh minh họa**. Nếu resource thực thi `AutoCloseable` và scope có quyền đóng, TWR bảo đảm cleanup khi rời scope, giữ lỗi thân làm primary và ghi lỗi close thành suppressed theo quy tắc JLS.

| Tiêu chí | Cleanup thủ công | `try-with-resources` |
| --- | --- | --- |
| Ít mã boilerplate | Không | Có |
| Đóng khi `return`/exception | Phải tự tổ chức đúng | Do ngôn ngữ quản lý |
| Bảo toàn lỗi thân và lỗi close | Phải bắt, giữ và `addSuppressed` đúng | Tự động trong tình huống chuẩn |
| Nhiều resource | Phải bảo đảm đóng hết, đúng thứ tự | Đóng ngược thứ tự header |
| Resource khởi tạo sau thất bại | Phải bảo vệ resource đã tạo | Tự đóng resource đã quản lý trước đó |
| Kiểm tra checked exception | Phải theo chữ ký từng phương thức | Compiler suy theo resource và thân |
| Cleanup không biểu diễn bằng `AutoCloseable` | Có thể cần | Cần adapter hoặc cơ chế bổ sung |
| Quyền sở hữu resource | Phải xét | **Vẫn phải xét** |

Dùng cleanup thủ công khi có nhu cầu thật: API legacy chỉ có phương thức giải phóng riêng, nhiều bước rollback cần xử lý đặc thù, hay tài nguyên không triển khai `AutoCloseable` và adapter không phù hợp. Không chọn thủ công chỉ vì muốn “kiểm soát hơn” nhưng lại bỏ sót primary/suppressed.

## 14. Khi cleanup không phải chỉ là `close()`

Một giao dịch có thể có nhiều bước hoàn tác: rollback, hủy tệp tạm, giải phóng lock. Không phải bước nào cũng phù hợp đưa vào `try-with-resources` một cách máy móc.

Ví dụ pseudocode:

```text
primary = lỗi của công việc (nếu có)
nếu công việc thất bại:
    thử rollback
        nếu rollback cũng lỗi: addSuppressed vào primary
thử xóa tệp tạm
    nếu lỗi: addSuppressed vào primary; hoặc là primary nếu chưa có
thử giải phóng tài nguyên còn lại
    nếu lỗi: ghi nhận tương tự
ném primary hoặc hoàn thành bình thường
```

Đây là **pseudocode mô tả chính sách**. Trong ứng dụng thật, rollback chỉ cần chạy theo điều kiện transaction, còn cleanup của những resource bắt buộc vẫn cần trên cả đường thành công và thất bại.

### Không cố tiếp tục sử dụng trạng thái đã thất bại

Ghi nhận suppressed không làm rollback thành công, không sửa dữ liệu, không khôi phục connection và không giải phóng tài nguyên thay bạn. Nếu một lần cleanup lỗi, tài nguyên có thể vẫn ở trạng thái không xác định. Hệ thống cần chính sách quan sát/khắc phục: log lỗi cùng primary, đánh dấu job thất bại, hủy scope hoặc yêu cầu can thiệp tùy mức độ.

### Không dùng một lỗi cleanup làm `cause` của lỗi công việc đã xảy ra trước

Nếu lỗi ghi dữ liệu xảy ra **trước**, rồi lỗi đóng phát sinh sau, lỗi đóng không phải nguyên nhân làm lỗi ghi xuất hiện. Đặt close failure làm `cause` của work failure thường thể hiện sai quan hệ nhân quả; dùng suppressed đúng hơn.

## 15. Các trường hợp ít gặp cần biết

### 15.1. Suppression có thể được vô hiệu hóa

Một custom exception có thể gọi constructor protected của `Throwable`/`Exception` với `enableSuppression=false`. Khi đó, `primary.addSuppressed(cleanup)` không ghi thêm lỗi, và `primary.getSuppressed()` trả mảng rỗng.

Trong đa số ứng dụng, giữ suppression bật là lựa chọn phù hợp. Không nên nói rằng `addSuppressed` chắc chắn luôn lưu được lỗi phụ trong mọi loại custom Throwable.

### 15.2. Exception từ `close()` có thể giống đối tượng primary

Nếu chính **một đối tượng Throwable** bị ném lại từ `close()`, `addSuppressed` trên cùng đối tượng gây self-suppression. Mẫu thủ công trong bài tránh điều đó bằng so sánh tham chiếu `cleanup != primary`. Nếu bạn cần một chính sách khác, phải xây dựng một cơ chế biểu diễn lỗi phù hợp, không chỉ bỏ điều kiện và để lỗi mới che primary.

### 15.3. `finally` không được bảo đảm khi JVM dừng cưỡng bức

`finally` và TWR hoạt động theo đường thực thi Java thông thường. Chúng không bảo đảm chạy khi JVM bị dừng cưỡng bức, `Runtime.halt` được gọi hoặc tiến trình gặp sự cố ngoài mô hình exception bình thường. Không dựa vào cleanup duy nhất để giữ tính toàn vẹn của dữ liệu cần khả năng phục hồi sau mất điện.

### 15.4. `close()` cũng có thể là thao tác nghiệp vụ quan trọng

Một output stream có buffer có thể flush khi đóng. Nếu đóng thất bại, đừng in “saved successfully” hoặc tiếp tục như thể dữ liệu đã bền vững. Đôi khi **cleanup failure là primary**, và đó là điều đúng nếu công việc trước đó chưa gây lỗi.

### 15.5. Log thông tin lỗi mà không đánh mất cấu trúc

`System.err.println(failure.getMessage())` không hiển thị cause và suppressed. Khi cần phân tích, có thể dùng `failure.printStackTrace()` hoặc logging framework nhận **đối tượng throwable**. Tránh in stack trace nhạy cảm cho người dùng cuối và tránh ghi cùng lỗi lặp ở mọi tầng.

## 16. Những lỗi và hiểu nhầm phổ biến

**“`finally { resource.close(); }` luôn giữ lỗi gốc.”** Sai. Nếu close ném, ngoại lệ close có thể thay thế ngoại lệ từ work.

**“Bắt lỗi close và không làm gì là an toàn.”** Không hẳn. Nếu work thành công mà close lỗi, bạn có thể báo thành công sai và mất dấu việc flush/đóng thất bại.

**“`addSuppressed` tự ném primary.”** Sai. Nó chỉ ghi nhận một lỗi phụ vào đối tượng primary; code vẫn phải xử lý hoặc truyền lỗi theo hợp đồng.

**“Lỗi close luôn là suppressed.”** Sai. Nếu không có primary trước đó, lỗi close trở thành primary.

**“Chỉ cần bắt `IOException` trong work là đã lưu được mọi primary.”** Sai. Work vẫn có thể ném `RuntimeException` hay `Error` và cần xét riêng khi thiết kế mẫu cleanup tổng quát.

**“Đã gọi `close()` của resource thứ hai thì chắc chắn resource thứ nhất cũng được đóng.”** Sai trong cleanup thủ công dùng hai lời gọi liên tiếp nếu lời gọi đầu ném ngoại lệ và không được bắt.

**“Đóng hai resource phải từ trái sang phải.”** Không phải quy tắc TWR; TWR đóng ngược thứ tự header. Khi tự quản lý, chọn thứ tự theo phụ thuộc thực tế, thường đóng ngược thứ tự sở hữu/khởi tạo.

**“Nếu tạo resource thứ hai thất bại, `finally` viết ở phía sau vẫn luôn đóng resource thứ nhất.”** Sai. Chưa vào khối `try` thì `finally` của nó không hoạt động.

**“Bọc exception bằng message là đủ.”** Sai. Phải giữ chính đối tượng primary làm cause để truy vết stack trace và suppressed.

**“`getSuppressed()` trả về null khi trống.”** Sai. Nó trả mảng rỗng.

**“Có thể `primary.addSuppressed(primary)`.”** Sai. Java từ chối self-suppression trực tiếp.

**“Nếu không có suppressed thì chắc chắn không có lỗi cleanup.”** Không chắc. Cleanup có thể chưa chạy, lỗi đã bị bỏ qua, hoặc suppression trên primary bị tắt.

**“Mọi `AutoCloseable.close()` đều chỉ ném `IOException`.”** Sai. `AutoCloseable.close()` khai báo `throws Exception`; kiểu cụ thể có thể khác.

**“Dùng TWR là không cần xét ownership.”** Sai. Nếu resource được mượn từ caller hay framework, đóng tự động sai scope vẫn gây hỏng luồng công việc.

**“Suppressed là lỗi đã được sửa.”** Sai. Đây chỉ là cơ chế **giữ thông tin**, không phải phục hồi.

**“Đóng trùng một resource luôn vô hại.”** Không. Tùy API, close có thể có side effect, ném lỗi hoặc không idempotent.

**“Bắt mọi `Throwable` rồi tiếp tục chạy sau `Error` là thực hành tốt.”** Không. Nếu catch Throwable để giữ nguyên lỗi lúc cleanup, cần **ném lại** và không xem các `Error` nghiêm trọng là tình huống phục hồi mặc định.

## 17. Bài tập tự kiểm tra

1. **Work ném A, close ném B, `finally` gọi close trực tiếp: có thể quan sát lỗi nào?** B có thể thay A nếu không có cơ chế giữ A.
2. **Muốn giữ A, B ở đâu?** A là primary; B là suppressed gắn vào A qua `addSuppressed`.
3. **Work thành công, close ném B, nên làm gì?** B trở thành primary hoặc được xử lý như thất bại theo hợp đồng; không tự báo thành công.
4. **`addSuppressed(B)` có thay đổi kiểu của A không?** Không.
5. **Nếu có B và C từ hai bước cleanup, có thể gắn cả hai không?** Có, qua hai lần `addSuppressed` trên primary, theo thứ tự ghi nhận.
6. **Hai resource first/second, second close lỗi: có nên cố đóng first?** Có nếu hợp đồng cleanup yêu cầu và có thể thực hiện an toàn; không để lỗi đầu ngăn việc đóng resource còn lại.
7. **Nếu work thành công và second close là lỗi đầu tiên, còn first close lỗi sau, primary là gì?** Lỗi đóng second; lỗi đóng first là suppressed của nó.
8. **Nếu việc tạo second thất bại trước khi vào try, first có chắc được đóng bởi finally phía sau không?** Không.
9. **Tại sao bắt duy nhất `IOException` chưa đủ làm mẫu tổng quát?** Vì work/cleanup có thể có unchecked `RuntimeException` hoặc `Error`.
10. **Có thể dùng `primary.addSuppressed(primary)` không?** Không, gây `IllegalArgumentException`.
11. **Nếu custom primary có suppression disabled, `getSuppressed()` như thế nào?** Mảng rỗng; không ghi được lỗi phụ bằng cơ chế chuẩn này.
12. **Bọc primary thành DomainException thì lưu ở đâu?** Ở `cause` của wrapper; suppressed của primary đi theo đối tượng cause.
13. **Lỗi rollback phát sinh sau lỗi ghi dữ liệu có phải cause của lỗi ghi không?** Thường không; đó là lỗi bổ sung và nên là suppressed nếu cùng đơn vị công việc.
14. **Vì sao TWR thường an toàn hơn?** Java tự đóng đúng scope, bảo toàn primary/suppressed và xử lý nhiều resource theo quy tắc được đặc tả.
15. **Một phương thức được truyền resource borrowed có nên tự động đóng để tránh leak không?** Không nếu hợp đồng caller giữ ownership; hãy xác định quyền đóng.
16. **`finally` chạy chắc chắn khi process bị kill cưỡng bức?** Không.
17. **Đọc chỉ `getMessage()` có đủ chẩn đoán lỗi cleanup không?** Thường không; cần xem throwable đầy đủ và `getSuppressed()`.
18. **Nếu một handler bắt `Throwable` để nhớ primary, sau cleanup có nên nuốt lỗi không?** Không; phải ném lại hoặc đưa sang cơ chế báo thất bại tương ứng, không giả định có thể tiếp tục.

## 18. Tài liệu chuẩn Java 17

- [Java Language Specification 17 — `14.20.2, Execution of try-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): ngoại lệ mới từ `finally` có thể thay thế lý do thoát cũ.
- [Java Language Specification 17 — `14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cách Java giữ primary/suppressed, thứ tự đóng và lỗi khi khởi tạo resource.
- [Java Language Specification 17 — `11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception và precise rethrow.
- [Java SE 17 API — Throwable.addSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): kiểm tra null và self-suppression.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): đọc danh sách lỗi phụ.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`, checked exception và idempotency.
- [Java SE 17 API — Throwable.getCause](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getCause()): phân biệt nguyên nhân và lỗi phụ.

**Ghi nhớ:** Khi phải dọn dẹp thủ công, đừng để lỗi cleanup **che mất** lỗi công việc. Nếu đã có primary, giữ nguyên đối tượng đó và gắn lỗi cleanup bằng `addSuppressed`; nếu chưa có primary, lỗi cleanup phải được báo như một lỗi thực sự. Với nhiều resource, cố đóng các resource còn thuộc quyền sở hữu, giữ thứ tự và cả các lỗi phát sinh. Nếu dùng được `try-with-resources`, hãy ưu tiên nó để tránh tự triển khai sai một quy trình xử lý ngoại lệ vốn rất dễ sót nhánh.
