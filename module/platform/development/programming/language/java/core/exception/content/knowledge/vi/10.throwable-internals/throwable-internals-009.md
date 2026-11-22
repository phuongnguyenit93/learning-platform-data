# `addSuppressed` và `getSuppressed` trong Java — giữ đầy đủ lỗi khi dọn dẹp

## 1. Mục tiêu bài học

Trong Java, một thao tác có thể **thất bại lần thứ nhất** khi đang xử lý công việc, rồi **thất bại lần thứ hai** lúc đóng file, stream, socket hoặc tài nguyên khác. Nếu chỉ truyền ra một ngoại lệ mà bỏ qua lỗi còn lại, việc chẩn đoán sẽ thiếu dữ kiện. `Throwable.addSuppressed(Throwable)` và `Throwable.getSuppressed()` giải quyết bài toán lưu giữ **ngoại lệ bổ sung** bên cạnh **ngoại lệ chính** (*primary exception*).

Từ Java 7, `try-with-resources` sử dụng cơ chế suppressed exceptions để giữ lỗi đóng tài nguyên mà không che mất lỗi ban đầu của phần thân. Lập trình viên cũng có thể gọi `addSuppressed` trong mã dọn dẹp thủ công khi có lý do rõ ràng.

Bạn sẽ học được:

- Khác biệt giữa **ngoại lệ chính**, **ngoại lệ suppressed** và **nguyên nhân `cause`**.
- Cách gọi `addSuppressed`/`getSuppressed` trên `Throwable` và đọc danh sách ngoại lệ.
- Thứ tự lỗi chính và lỗi suppressed khi một hoặc nhiều resource cùng thất bại.
- Hành vi khi không có suppressed exceptions, khi truyền `null`, khi thêm chính mình, khi thêm nhiều lỗi.
- Cách tắt suppression bằng constructor protected của `Throwable`/`Exception` và tác động tới API.
- Quan hệ với `try-with-resources`, `close()`, ngoại lệ từ khởi tạo resource, `catch`/`finally` và `printStackTrace`.
- Những sai lầm dễ gây mất nguyên nhân gốc và cách bảo toàn thông tin lỗi ở tầng ứng dụng.

Các ví dụ độc lập dùng Java 17+; kết quả `stdout` được ghi cụ thể. Trường hợp cố ý gây lỗi biên dịch hoặc chỉ là mảnh mã sẽ được đánh dấu.

## 2. Ba loại liên kết lỗi: primary, suppressed và cause

Xét một chương trình xử lý tệp:

```text
Mở tài nguyên thành công
       |
       v
Đọc dữ liệu bị lỗi: IOException("read failed")    <-- primary
       |
       v
Đóng tài nguyên cũng lỗi: IOException("close failed")
       |
       v
try-with-resources giữ "read failed" làm primary
và gắn "close failed" vào danh sách suppressed
```

Ngoại lệ chính là đối tượng được truyền ra cho `catch` hoặc caller. Lỗi suppressed được **đính kèm vào đối tượng chính**, chứ không ném thay cho lỗi chính. Có thể quan sát chúng bằng `primary.getSuppressed()`.

Phân biệt các khái niệm:

| Quan hệ | API | Ý nghĩa điển hình |
| --- | --- | --- |
| **Primary exception** | Đối tượng đang được `throw`/`catch` xử lý | Lỗi chính làm thao tác hiện tại thất bại |
| **Cause** | `getCause()`, constructor nhận cause, `initCause(...)` | Ngoại lệ trước đó **dẫn đến** hoặc được bọc bởi lỗi hiện tại |
| **Suppressed** | `addSuppressed(other)`, `getSuppressed()` | Lỗi **bổ sung** cần giữ lại dù không thay thế lỗi chính |

Ví dụ: đọc một cấu hình gây `IOException("read")`; đóng nguồn gây `IOException("close")`. Lỗi đóng thường là suppressed của lỗi đọc. Ngược lại, nếu bạn chủ động chuyển `NumberFormatException` thành `ParseException` vì muốn thông báo lỗi phân tích dữ liệu, `NumberFormatException` thường là **cause** của `ParseException`.

Không có quy tắc “mọi lỗi xảy ra sau đều tự trở thành suppressed”: Java tự thực hiện việc đính kèm ở các cấu trúc có quy định, nổi bật là `try-with-resources`. Một khối `finally` thủ công không mặc nhiên thêm suppressed nếu nó ném lỗi khác.

## 3. Hai phương thức trên `Throwable`

### 3.1. `addSuppressed(Throwable exception)`

Khai báo API:

```java
public final synchronized void addSuppressed(Throwable exception)
```

Phương thức thêm đối tượng `exception` vào danh sách suppressed của **đối tượng đang nhận lời gọi**, nếu suppression được bật cho đối tượng đó.

Ví dụ:

```java
Throwable primary = new IllegalStateException("work failed");
Throwable cleanup = new java.io.IOException("cleanup failed");

primary.addSuppressed(cleanup);
```

Đây là đoạn minh họa chạy được khi đặt trong phương thức Java. Sau lời gọi, `primary` vẫn là `IllegalStateException("work failed")`; `cleanup` nằm trong tập lỗi bổ sung của `primary`.

Hành vi quan trọng:

- Không đổi `getMessage()`, `getCause()` hay kiểu thực tế của đối tượng primary.
- Không tự thực hiện `throw`; phương thức chỉ thay đổi thông tin đính kèm.
- Có thể thêm nhiều đối tượng suppressed, và thứ tự thêm có thể được quan sát khi gọi `getSuppressed()`.
- Không thể thêm chính đối tượng primary vào danh sách suppressed của nó.
- Không thể truyền `null` làm đối số.
- Nếu suppression đã được **vô hiệu hóa** khi xây dựng đối tượng primary, lời gọi hợp lệ không lưu thêm lỗi nào.
- Không cần và không nên bọc suppressed bằng một `RuntimeException` không có ý nghĩa chỉ để tương thích kiểu: tham số là `Throwable`.

### 3.2. `getSuppressed()`

Khai báo:

```java
public final synchronized Throwable[] getSuppressed()
```

Phương thức trả một **mảng** chứa các đối tượng suppressed đã được ghi nhận. Nó không trả `null` khi danh sách trống.

```java
Throwable[] secondaryFailures = primary.getSuppressed();
for (Throwable failure : secondaryFailures) {
    System.out.println(failure.getClass().getSimpleName()
            + ": " + failure.getMessage());
}
```

Đây là mảnh mã giả định `primary` đã được khai báo.

Quy tắc cần nhớ:

- Nếu không có lỗi bổ sung, độ dài mảng là `0`.
- Mảng là **bản sao biểu diễn danh sách tại thời điểm gọi**, không phải quyền truy cập sửa trực tiếp vào danh sách nội bộ.
- Mảng chứa **tham chiếu đến các đối tượng `Throwable`**, không phải bản sao sâu của từng ngoại lệ. Thay đổi nội dung của một đối tượng exception (nếu API cho phép) có thể được thấy qua nhiều tham chiếu.
- Muốn thêm suppressed exception, gọi `addSuppressed(...)`, không sửa một phần tử của mảng do `getSuppressed()` trả về.
- `getSuppressed()` có thể gọi nhiều lần; mỗi lần phản ánh trạng thái đã ghi nhận ở thời điểm tương ứng.

Mọi `Exception` và `Error` đều kế thừa `Throwable` nên có hai phương thức này; không cần ép kiểu thành một subclass cụ thể.

## 4. Ví dụ hoàn chỉnh: tự thêm và đọc lỗi suppressed

Tạo tệp **`ManualSuppressedDemo.java`**:

```java
import java.io.IOException;

public class ManualSuppressedDemo {
    public static void main(String[] args) {
        IllegalStateException primary =
                new IllegalStateException("operation failed");

        primary.addSuppressed(new IOException("close stream"));
        primary.addSuppressed(new IOException("release channel"));

        System.out.println("primary=" + primary.getMessage());
        System.out.println("count=" + primary.getSuppressed().length);

        for (Throwable suppressed : primary.getSuppressed()) {
            System.out.println("suppressed=" + suppressed.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ManualSuppressedDemo.java
java ManualSuppressedDemo
```

`stdout` chính xác:

```text
primary=operation failed
count=2
suppressed=close stream
suppressed=release channel
```

Giải thích:

1. `primary` là lỗi công việc được tạo đầu tiên.
2. Mỗi `addSuppressed` gắn **một đối tượng ngoại lệ khác** vào `primary`.
3. `getSuppressed()` trả về hai phần tử theo thứ tự đã thêm.
4. `primary` vẫn mang kiểu `IllegalStateException` và thông điệp `operation failed`; lỗi phụ không chiếm vị trí lỗi chính.

Trong ứng dụng thật, chỉ gọi `addSuppressed` khi các ngoại lệ thực sự liên quan đến **cùng thao tác thất bại** và việc giữ nguyên lỗi chính là chủ ý có căn cứ.

## 5. `try-with-resources` tự động tạo suppressed exception như thế nào?

Đoạn minh họa:

```java
try (AutoCloseable resource = acquire()) {
    work(); // Ném lỗi chính.
}
```

Đây là **mảnh mã**, cần khai báo `acquire()`, `work()` và bắt/khai báo kiểu checked exception tương ứng. Giả sử phần thân ném ngoại lệ A, rồi `resource.close()` ném ngoại lệ B. `try-with-resources` bảo toàn A làm lỗi chính và thêm B vào `A.getSuppressed()`.

Điều này khác với cách đóng thủ công thiếu cẩn trọng:

```java
try {
    work();
} finally {
    resource.close(); // Nếu cũng ném lỗi, có thể che lỗi work().
}
```

Đây cũng là mảnh minh họa. `finally` vẫn chạy khi khối `try` ném lỗi, nhưng ngoại lệ mới từ `close()` có thể **thay thế** lý do thoát cũ, khiến lỗi A bị che nếu không chủ động xử lý.

TWR thực hiện logic quản lý ngoại lệ đã được quy định trong ngôn ngữ Java: **đảm bảo đóng tài nguyên và giữ lại thông tin về các lỗi đóng** theo mối quan hệ primary/suppressed.

### 5.1. Ví dụ chạy được: lỗi thân và lỗi đóng

Tạo tệp **`BodyAndCloseFailureDemo.java`**:

```java
import java.io.IOException;

public class BodyAndCloseFailureDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing resource");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("doing work");
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException failure) {
            System.out.println("primary=" + failure.getMessage());

            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac BodyAndCloseFailureDemo.java
java BodyAndCloseFailureDemo
```

Kết quả `stdout`:

```text
doing work
closing resource
primary=body failed
suppressed=close failed
```

Diễn biến:

- Phần thân tạo `IllegalStateException("body failed")`. Đây là lý do làm khối kết thúc đột ngột.
- Khi rời TWR, Java gọi `close()`; dòng `closing resource` được in.
- `close()` ném `IOException("close failed")`. Vì đang có lỗi chính, TWR gắn lỗi đóng vào `getSuppressed()` của `IllegalStateException`.
- Handler nhận **IllegalStateException**, không phải `IOException`.
- Đối tượng IOException vẫn có đầy đủ message, stack trace và cause riêng khi được lưu vào danh sách suppressed.

Không viết `catch (IOException)` để bắt một cách riêng lẻ lỗi đóng trong ví dụ này: lỗi đóng đã trở thành suppressed của primary và cần được kiểm tra thông qua primary.

## 6. Nếu phần thân không lỗi, ngoại lệ từ `close()` là **lỗi chính**

Không phải mọi ngoại lệ từ `close()` đều là suppressed. Nếu phần thân hoàn thành bình thường, còn đóng resource thất bại, lỗi đóng có thể **truyền ra trực tiếp**.

Tạo file **`CloseOnlyFailureDemo.java`**:

```java
import java.io.IOException;

public class CloseOnlyFailureDemo {
    static class BrokenClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("cannot close");
        }
    }

    public static void main(String[] args) {
        try (BrokenClose resource = new BrokenClose()) {
            System.out.println("work succeeded");
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed count="
                    + failure.getSuppressed().length);
        }
    }
}
```

```bash
javac CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

`stdout`:

```text
work succeeded
closing
primary=cannot close
suppressed count=0
```

Không có lỗi công việc trước đó nên `IOException("cannot close")` trở thành primary. Vì đây là lỗi duy nhất, `getSuppressed()` trả mảng rỗng.

Đây là lý do khi ghi log TWR không nên giả định rằng **mọi IOException do close đều được lưu dưới suppressed**. Cần xác định đường thực thi và đối tượng exception đã thoát ra.

## 7. Nhiều tài nguyên: thứ tự đóng và danh sách suppressed

TWR đóng resource theo **thứ tự ngược** với thứ tự chúng xuất hiện trong resource specification. Khi nhiều `close()` cùng thất bại, thứ tự trong `getSuppressed()` phản ánh trình tự đính kèm khi đóng.

### 7.1. Thân ném lỗi, cả hai resource đóng đều lỗi

Tạo file **`MultipleSuppressedDemo.java`**:

```java
import java.io.IOException;

public class MultipleSuppressedDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {

            System.out.println("body");
            throw new IllegalArgumentException("body failed");

        } catch (IllegalArgumentException failure) {
            System.out.println("primary=" + failure.getMessage());

            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac MultipleSuppressedDemo.java
java MultipleSuppressedDemo
```

`stdout`:

```text
body
close second
close first
primary=body failed
suppressed=close second failed
suppressed=close first failed
```

Trình tự chính xác:

1. Tạo `first` rồi `second`.
2. Thân ném `IllegalArgumentException("body failed")` làm primary.
3. Java gọi `second.close()` **trước**, ghi nhận `IOException("close second failed")` thành suppressed.
4. Java gọi `first.close()`, ghi nhận `IOException("close first failed")` thành suppressed tiếp theo.
5. `catch` nhận lỗi thân và đọc danh sách hai lỗi bổ sung theo thứ tự chúng được ghi nhận.

Một tài nguyên khác có thể đóng thành công; khi đó không có suppressed exception bổ sung tương ứng. Thứ tự đóng không phụ thuộc thứ tự gọi resource trong thân chương trình.

### 7.2. Thân thành công nhưng **hai lần đóng** đều thất bại

Tạo file **`CloseOrderPrimaryDemo.java`**:

```java
import java.io.IOException;

public class CloseOrderPrimaryDemo {
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

    public static void main(String[] args) {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {

            System.out.println("body succeeded");

        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed count="
                    + failure.getSuppressed().length);

            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac CloseOrderPrimaryDemo.java
java CloseOrderPrimaryDemo
```

`stdout`:

```text
body succeeded
close second
close first
primary=second close failed
suppressed count=1
suppressed=first close failed
```

Lần đóng `second` gặp lỗi đầu tiên; tại thời điểm ấy chưa có lỗi primary từ phần thân. Vì vậy lỗi đóng của `second` trở thành primary, còn lỗi đóng `first` sau đó được đính kèm suppressed. Điều này giải thích vì sao **vị trí suppressed phụ thuộc thứ tự và thời điểm lỗi**, không chỉ phụ thuộc API nào ném exception.

### 7.3. Ngoại lệ khi khởi tạo resource thứ hai

Một tình huống cũng đáng chú ý:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    work();
}
```

Đây là **mảnh mã minh họa**. Nếu `openSecond()` ném lỗi sau khi `first` đã được khởi tạo thành công, TWR sẽ đóng `first`. Nếu `first.close()` cũng ném, lỗi đóng có thể được đính kèm suppressed vào lỗi khởi tạo `second`. Quy tắc này giúp giữ nguyên lỗi gốc **ở giai đoạn khởi tạo**, chứ không chỉ lỗi trong phần thân.

### 7.4. Không đồng nhất suppressed với thứ tự thời gian toàn cục

Một đối tượng `Throwable` có thể có suppressed được thêm thủ công ở bất kỳ giai đoạn thích hợp. Vì thế, danh sách suppressed không phải một timeline bất biến của toàn bộ ứng dụng. Nó chỉ phản ánh các đối tượng đã được ghi nhận thông qua cơ chế tương ứng. Muốn xác định nguyên nhân, cần đọc message, stack trace, cause, ngữ cảnh và lịch sử tài nguyên.

## 8. Lỗi sử dụng API: không được tự suppress hoặc truyền `null`

`Throwable.addSuppressed` có kiểm tra đầu vào nhằm tránh cấu trúc lỗi bất hợp lý.

### 8.1. Tự thêm chính mình: `IllegalArgumentException`

```java
Throwable failure = new IllegalStateException("root");
failure.addSuppressed(failure); // Lỗi: self-suppression.
```

Đây là mảnh mã có lỗi runtime cố ý. Chính ngoại lệ primary không được là suppressed của bản thân nó. Cấu trúc tự tham chiếu sẽ rất khó diễn giải khi in stack trace, và Java chủ động ngăn self-suppression trực tiếp.

### 8.2. Thêm `null`: `NullPointerException`

```java
Throwable failure = new IllegalStateException("root");
failure.addSuppressed(null); // Lỗi: null không phải Throwable hợp lệ.
```

Đây là mảnh mã cố ý gây lỗi runtime. Đối số suppressed phải là một đối tượng `Throwable` không null.

### 8.3. Ví dụ chạy được: kiểm tra hai trường hợp

Tạo file **`SuppressedValidationDemo.java`**:

```java
public class SuppressedValidationDemo {
    public static void main(String[] args) {
        IllegalStateException root =
                new IllegalStateException("root");

        try {
            root.addSuppressed(root);
        } catch (IllegalArgumentException failure) {
            System.out.println("self: "
                    + failure.getClass().getSimpleName());
        }

        try {
            root.addSuppressed(null);
        } catch (NullPointerException failure) {
            System.out.println("null: "
                    + failure.getClass().getSimpleName());
        }

        System.out.println("count=" + root.getSuppressed().length);
    }
}
```

```bash
javac SuppressedValidationDemo.java
java SuppressedValidationDemo
```

`stdout`:

```text
self: IllegalArgumentException
null: NullPointerException
count=0
```

Cả hai lần thêm đều thất bại; danh sách suppressed của `root` vẫn trống. Đừng “khắc phục” bằng cách bắt rồi bỏ qua lỗi API: điều đúng là **không truyền `null`, không tự tham chiếu** ngay từ đầu.

**Điểm tinh tế:** hạn chế là không được thêm **chính đối tượng nhận lời gọi**. Java không buộc mọi đối tượng suppressed phải có kiểu khác hay message khác. Một ngoại lệ có thể mang cùng loại, cùng thông điệp với một lỗi khác mà vẫn là đối tượng hợp lệ.

## 9. `getSuppressed()` trả mảng rỗng và không để caller sửa danh sách bên trong

Để duyệt an toàn:

```java
for (Throwable secondary : failure.getSuppressed()) {
    // Ghi log hoặc phân tích nguyên nhân phụ.
}
```

Đây là mảnh mã minh họa với `failure` là một `Throwable`. Không cần kiểm tra `getSuppressed() != null`; một đối tượng bình thường không có suppressed trả mảng độ dài 0.

### Ví dụ chạy được: sửa mảng trả về không sửa danh sách suppressed

Tạo file **`SuppressedArraySnapshotDemo.java`**:

```java
import java.io.IOException;

public class SuppressedArraySnapshotDemo {
    public static void main(String[] args) {
        Exception primary = new Exception("main");
        primary.addSuppressed(new IOException("original"));

        Throwable[] snapshot = primary.getSuppressed();
        snapshot[0] = new IOException("replacement");

        System.out.println("snapshot="
                + snapshot[0].getMessage());
        System.out.println("stored="
                + primary.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac SuppressedArraySnapshotDemo.java
java SuppressedArraySnapshotDemo
```

`stdout`:

```text
snapshot=replacement
stored=original
```

Mảng kết quả là một snapshot độc lập về **vị trí phần tử**, nên gán vào `snapshot[0]` không làm thay đổi mảng nội bộ của primary. Nhưng các phần tử của snapshot ban đầu vẫn là tham chiếu đến các đối tượng `Throwable` thực tế; nếu bạn dùng `snapshot[0].addSuppressed(...)` trước khi thay phần tử, bạn đang thao tác trên chính đối tượng lỗi đó.

Ngoài ra, không nên lưu mảng snapshot rồi cho rằng nó tự cập nhật nếu primary có suppressed mới. Muốn xem dữ liệu mới, gọi `getSuppressed()` lại.

## 10. Phân biệt `getCause()` và `getSuppressed()`

Hai API phục vụ **hai hướng liên kết** khác nhau. Có thể kết hợp cả hai trên cùng một đối tượng lỗi.

Tạo file **`CauseVsSuppressedDemo.java`**:

```java
import java.io.IOException;

public class CauseVsSuppressedDemo {
    public static void main(String[] args) {
        IllegalArgumentException parseCause =
                new IllegalArgumentException("invalid number");

        IOException failure =
                new IOException("cannot import", parseCause);
        failure.addSuppressed(
                new IllegalStateException("temporary file cleanup failed"));

        System.out.println("primary=" + failure.getMessage());
        System.out.println("cause=" + failure.getCause().getMessage());
        System.out.println("suppressed="
                + failure.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac CauseVsSuppressedDemo.java
java CauseVsSuppressedDemo
```

`stdout`:

```text
primary=cannot import
cause=invalid number
suppressed=temporary file cleanup failed
```

**Diễn giải:**

- `IOException("cannot import", parseCause)` là lỗi hiện tại, có **cause** giải thích thất bại sâu hơn lúc parse.
- `addSuppressed(...)` giữ một lỗi phát sinh thêm khi cleanup.
- `getCause()` trả **một** nguyên nhân (hoặc `null`), trong khi `getSuppressed()` trả **mảng** lỗi bổ sung (có thể rỗng).
- Suppressed không thay thế cause; một suppressed exception lại có thể có cause và suppressed riêng.

Ví dụ cây chẩn đoán:

```text
IOException: cannot import                 [primary]
  Caused by: IllegalArgumentException     [cause]
    invalid number
  Suppressed: IllegalStateException       [suppressed]
    temporary file cleanup failed
```

Đây là **sơ đồ khái niệm**, không phải nội dung `printStackTrace()` chính xác theo một phiên bản JVM. Phần trình bày stack trace thực tế có thể thụt dòng, cắt bớt frame trùng lặp hoặc hiển thị các phần theo bố cục khác.

Không tạo cause chain hoặc suppressed chỉ để có một hình thức stack trace đẹp. Chọn liên kết theo bản chất lỗi.

## 11. Tắt suppression: danh sách rỗng không chứng minh cleanup thành công

Lớp ngoại lệ con có thể gọi constructor `protected` với `enableSuppression=false`. Khi ấy `addSuppressed(validThrowable)` vẫn được gọi hợp lệ nhưng **không lưu** lỗi phụ, và `getSuppressed()` luôn là mảng rỗng trên chính đối tượng đó.

~~~java
class NoSuppressionFailure extends RuntimeException {
    NoSuppressionFailure(String message) {
        super(message, null, false, true);
    }
}
~~~

Trong `try-with-resources`, nếu thân khối ném `NoSuppressionFailure` rồi `close()` cũng lỗi, việc đóng **vẫn có thể thất bại** dù lỗi chính không chứa suppressed. Vì vậy đừng xem `getSuppressed().length == 0` là xác nhận mọi bước cleanup thành công.

Không vô hiệu hóa suppression theo thói quen. Các tổ hợp `enableSuppression`/`writableStackTrace`, cách constructor áp dụng cờ và ảnh hưởng tới cause/stack trace được thực hành đầy đủ ở bài cấu hình `Throwable`; ở đây chỉ cần nhớ ranh giới: API đọc lỗi phụ không thể khôi phục một lỗi phụ mà đối tượng chính **đã chọn không lưu**.

## 12. Nếu resource bị đóng nhiều lần, suppressed có tự loại trùng không?

`addSuppressed` không phải tập hợp duy nhất theo kiểu `Set`. Ngoài trường hợp tự suppress trực tiếp và đối số null, API không tự dùng message, class hay stack trace để lọc trùng theo nội dung.

Ví dụ:

```java
Throwable primary = new IllegalStateException("work");
Throwable cleanup = new java.io.IOException("cleanup");
primary.addSuppressed(cleanup);
primary.addSuppressed(cleanup);
```

Đây là mảnh mã hợp lệ: cùng **một đối tượng cleanup** được thêm hai lần. Danh sách phản ánh hai lần thêm. Do đó:

- Không diễn giải số phần tử suppressed như số tài nguyên duy nhất nếu mã có thể thêm cùng một lỗi nhiều lần.
- Tránh thêm một lỗi nhiều lần bằng tay khi nó đã được TWR tự ghi nhận.
- Không sử dụng `addSuppressed` như thay thế cho cơ chế deduplication theo ngữ nghĩa nghiệp vụ.

Khi thấy hai dòng lỗi cleanup giống nhau trong log, cần xem việc quản lý tài nguyên và nơi gọi `addSuppressed`, không vội kết luận JVM “đóng resource hai lần” nếu chưa có bằng chứng.

## 13. Stack trace hiển thị suppressed exceptions như thế nào?

`Throwable.printStackTrace()` được thiết kế để hiển thị cấu trúc nguyên nhân và suppressed exceptions. Trong stack trace văn bản phổ biến, một suppressed exception xuất hiện như một mục thụt dòng có tiền tố tương tự `Suppressed:` dưới ngoại lệ chứa nó; cause thường xuất hiện cùng nhãn `Caused by:`.

Ví dụ mảnh mã:

```java
try (FailingResource resource = acquire()) {
    performWork();
} catch (Exception failure) {
    failure.printStackTrace();
}
```

Đây là **mảnh minh họa**, cần định nghĩa `FailingResource`, `acquire()` và `performWork()` phù hợp. `printStackTrace()` thường ghi vào `System.err`, vì vậy không nên kiểm tra chính xác toàn bộ chuỗi stack trace như `stdout` cố định của các ví dụ.

Khi debug, nên đọc:

1. Kiểu và thông điệp của **primary**.
2. Những dòng frame cho biết nơi lỗi chính phát sinh.
3. `Caused by` để theo dõi nguyên nhân sâu hơn.
4. `Suppressed` để thấy những lỗi lúc cleanup hoặc hoạt động bổ sung.
5. Đường đi của resource và chính sách mở/đóng liên quan.

Mọi suppressed exception đều là một `Throwable` có thể có stack trace và cause riêng. Không nên chỉ ghi mỗi `failure.getMessage()` nếu ứng dụng cần thông tin pháp y đầy đủ; cách ghi log có cấu trúc hoặc in toàn bộ throwable thường hữu ích hơn, nhưng phải tuân thủ quy định bảo mật, không làm lộ dữ liệu nhạy cảm.

### Không phải “suppressed” nghĩa là lỗi đã được xử lý an toàn

Tên suppressed nói rằng lỗi **không được ném làm primary** trong tình huống đó. Nó không bảo đảm việc cleanup thành công hoặc có thể bỏ qua hậu quả. Đóng một file output không thành công có thể làm dữ liệu chưa được flush đúng; lỗi đó vẫn quan trọng cho vận hành và cần được xem xét.

## 14. Dùng `addSuppressed` thủ công khi nào?

`try-with-resources` đã tự quản lý phần lớn trường hợp resource `AutoCloseable`. Thủ công thường chỉ cần khi một tầng phối hợp thực hiện **nhiều thao tác dọn dẹp không thể biểu diễn phù hợp bằng TWR**, và muốn giữ lỗi chính thay vì cho lỗi dọn dẹp che khuất nó.

Ví dụ mẫu ý tưởng:

```java
try {
    doWork();
} catch (java.io.IOException primary) {
    try {
        cleanup();
    } catch (java.io.IOException cleanupFailure) {
        primary.addSuppressed(cleanupFailure);
    }
    throw primary;
}
```

Đây là **mảnh mã minh họa**, đòi hỏi `doWork()`/`cleanup()` đã được định nghĩa, phương thức bao ngoài bắt/khai báo `IOException` và có quy tắc dọn dẹp cả trên đường thành công. Mục tiêu là cho thấy cách bảo toàn lỗi ban đầu khi **cả hai thao tác đều thất bại**; nó **không** phải template thay thế đầy đủ `finally` hay `try-with-resources` vì đoạn chỉ dọn dẹp trong đường lỗi và không nói đến nhánh hoàn tất bình thường.

Khi tự triển khai cleanup cho nhiều tài nguyên, phải xét các nhánh:

- Công việc thành công, cleanup thành công.
- Công việc thành công, cleanup thất bại (lỗi cleanup cần được truyền ra hoặc xử lý).
- Công việc thất bại, cleanup thành công (giữ lỗi công việc).
- Công việc thất bại, cleanup cũng thất bại (giữ lỗi công việc, đính kèm lỗi cleanup).
- Khởi tạo resource thất bại sau khi một resource khác đã mở.
- Nhiều cleanup cùng thất bại; không dừng tại lần cleanup lỗi đầu nếu hợp đồng cần cố dọn tiếp.

Vì logic dễ sai, **ưu tiên TWR** bất cứ khi nào phạm vi sở hữu resource và kiểu API cho phép.

### Không “suppress” một lỗi không liên quan

`addSuppressed` không có ràng buộc kỹ thuật rằng ngoại lệ bổ sung bắt buộc từ `close()`. Tuy nhiên, nếu đính kèm lỗi hoàn toàn không liên quan, người đọc stack trace sẽ hiểu sai quan hệ nguyên nhân. Chỉ dùng khi các lỗi phát sinh trong cùng đơn vị công việc hoặc cleanup có quan hệ rõ ràng.

### Không dùng `initCause` để thay `addSuppressed` một cách tùy tiện

`initCause`/constructor cause thể hiện một **chuỗi nguyên nhân**: lỗi A dẫn tới lỗi B hoặc bị B bọc lại. Lỗi cleanup phát sinh **song song sau lỗi công việc** không thường là nguyên nhân làm công việc thất bại trước đó. Gắn cleanup làm cause của primary có thể tạo câu chuyện nhân quả sai; suppressed mới là quan hệ phù hợp hơn.

## 15. Tình huống thực tế và cách chọn xử lý

| Tình huống | Lỗi nên là primary | Suppressed nên chứa |
| --- | --- | --- |
| Đọc tệp lỗi, rồi đóng reader lỗi | Lỗi đọc | Lỗi đóng reader |
| Ghi dữ liệu thành công, chỉ flush/close lỗi | Lỗi flush/close | Có thể không có |
| Thân TWR lỗi, hai resource cùng đóng lỗi | Lỗi thân | Hai lỗi đóng theo trình tự |
| Thân TWR thành công, hai resource đóng lỗi | Lỗi đóng đầu tiên theo thứ tự đóng | Lỗi đóng tiếp theo |
| Tạo resource thứ hai lỗi, đóng resource thứ nhất lỗi | Lỗi tạo resource thứ hai | Lỗi đóng resource thứ nhất |
| Biến exception từ parse được bọc thành lỗi nghiệp vụ | Lỗi nghiệp vụ, với parse là **cause** | Chỉ lỗi phụ khi có |
| Resource khai báo kiểu có suppression disabled | Lỗi chính tùy đường chạy | Có thể không lưu được lỗi phụ |
| Cleanup thủ công ném lỗi mới trong `finally` mà không bắt | Lỗi mới có thể thay lỗi cũ | Không tự gắn suppressed như TWR |

Kết quả thực tế vẫn phụ thuộc lỗi nào phát sinh trước, resource nào đã được khởi tạo thành công, kiểu ngoại lệ nào được ném và việc suppression có bật cho **đối tượng primary** hay không.

### Ví dụ ứng dụng: log chính xác nhiều tầng

Một hàm điều phối có thể cần ghi một lỗi thất bại với cả cause và suppressed. Thay vì chỉ:

```java
System.err.println(failure.getMessage());
```

hãy cân nhắc gửi toàn bộ đối tượng throwable tới logging framework thích hợp hoặc chẩn đoán:

```java
failure.printStackTrace(System.err);
```

Đây là hai **mảnh lệnh minh họa** giả định `failure` là `Throwable`. Khi in toàn bộ exception, Java có khả năng trình bày cause/suppressed; khi chỉ in message, phần lớn thông tin lỗi bổ sung không được hiển thị.

Nếu chương trình chạy ở production, có thể dùng logger có cơ chế lưu exception object. Đừng log lặp ở mọi tầng khi cùng ngoại lệ tiếp tục được ném lên trên, vì có thể tạo nhiều bản ghi trùng và khó xác định sự cố chính.

## 16. Lỗi và hiểu nhầm phổ biến

**“Suppressed exception là lỗi bị bỏ qua hoàn toàn.”** Sai. Nó vẫn được lưu dưới đối tượng primary và có thể đọc/in để chẩn đoán; không trở thành primary không có nghĩa được bỏ qua về mặt vận hành.

**“Cứ có `close()` ném lỗi thì lỗi đóng luôn là suppressed.”** Sai. Khi phần thân thành công, lỗi đóng đầu tiên có thể là primary.

**“`getSuppressed()` trả `null` nếu không có lỗi phụ.”** Sai. Nó trả mảng rỗng.

**“`addSuppressed` sẽ ném lỗi phụ thay cho lỗi chính.”** Sai. Phương thức chỉ gắn thông tin vào một đối tượng Throwable; nó không tự thực hiện `throw`.

**“Có thể gọi `root.addSuppressed(root)`.”** Sai. Self-suppression bị từ chối bằng `IllegalArgumentException`.

**“`addSuppressed(null)` chỉ đơn giản bị bỏ qua.”** Sai. `null` bị từ chối bằng `NullPointerException`.

**“Đổi `getSuppressed()[0]` có thể sửa danh sách nội bộ.”** Sai. Mảng được trả là bản sao; sửa vị trí phần tử của nó không thay nội dung danh sách nội bộ.

**“`cause` và `suppressed` đều chỉ lỗi gốc, dùng cái nào cũng như nhau.”** Sai. Cause chỉ chuỗi nguyên nhân; suppressed ghi lỗi bổ sung, đặc biệt là cleanup thất bại.

**“`try-with-resources` chỉ lưu một lỗi đóng dù nhiều resource lỗi.”** Sai. Có thể lưu nhiều lỗi suppressed trong thứ tự ghi nhận, tùy chính sách suppression và đường thoát.

**“Lỗi đóng resource thứ nhất luôn làm primary dù được liệt kê bên trái.”** Sai. Java đóng từ phải sang trái; khi thân không lỗi, resource được đóng đầu tiên và thất bại có thể cung cấp primary.

**“Tắt suppression cũng tắt toàn bộ cơ chế kiểm tra tham số.”** Sai. `null` và self-suppression vẫn không hợp lệ.

**“Throwable nào cũng cho phép lưu suppressed.”** Không nhất thiết. Lớp con có thể tắt suppression lúc khởi tạo.

**“`finally` thủ công tự tạo suppressed y hệt TWR.”** Sai. Nếu `finally` ném lỗi mới, nó có thể che lỗi cũ. Muốn bảo toàn cần thiết kế thủ công hoặc dùng TWR.

**“`getSuppressed().length == 0` chứng minh không hề có lỗi cleanup.”** Không chắc. Có thể không có lỗi, có thể lỗi không được gắn vào primary, hoặc suppression trên primary đã bị vô hiệu hóa.

**“Các phần tử suppressed là bản sao của Throwable nên không còn stack trace thật.”** Sai. Mảng chứa tham chiếu đến các đối tượng Throwable gốc được ghi nhận.

**“Có thể bỏ qua lỗi close vì đã lưu trong suppressed.”** Sai. Một lỗi đóng stream ghi có thể mang hậu quả về dữ liệu, giao dịch hoặc resource leak và phải được xem xét theo yêu cầu ứng dụng.

## 17. Câu hỏi tự kiểm tra

1. **`Throwable.addSuppressed(x)` có thay đổi primary exception thành `x` không?** Không. Nó đính kèm `x` dưới primary.
2. **Khi nào lỗi `close()` là suppressed?** Khi đã có một primary đang được truyền đi và TWR ghi nhận lỗi đóng bổ sung vào nó.
3. **Nếu chỉ `close()` thất bại, không có lỗi thân, kết quả thường thế nào?** Lỗi đóng trở thành primary.
4. **`getSuppressed()` trả kiểu gì?** `Throwable[]`.
5. **Không có suppressed, mảng trả dài bao nhiêu?** `0`.
6. **`addSuppressed(root)` khi gọi trên `root` gây lỗi nào?** `IllegalArgumentException`.
7. **`addSuppressed(null)` gây lỗi nào?** `NullPointerException`.
8. **Hai resource A rồi B trong header TWR sẽ đóng theo thứ tự nào?** B rồi A.
9. **Thân thành công, B đóng lỗi rồi A đóng lỗi: lỗi nào là primary?** Lỗi đóng B, lỗi đóng A là suppressed của lỗi B.
10. **Thân ném E, B/A đều đóng lỗi: primary là gì?** E; các lỗi đóng được gắn suppressed theo quy tắc, nếu suppression bật.
11. **Có thể vừa có `getCause()` vừa có `getSuppressed()` trên một lỗi không?** Có. Hai quan hệ này độc lập về ý nghĩa.
12. **Nếu tắt suppression khi tạo exception, `getSuppressed()` thế nào?** Luôn trả mảng rỗng cho đối tượng đó.
13. **Sửa `Throwable[] result = ex.getSuppressed(); result[0] = ...;` có sửa danh sách bên trong không?** Không.
14. **`printStackTrace()` có thể biểu diễn suppressed không?** Có, nó được thiết kế để hiển thị cùng cause và stack trace.
15. **Nên thay TWR bằng `finally { resource.close(); }` cho đơn giản?** Thường không, vì dễ làm mất lỗi chính khi close cũng lỗi.
16. **Có nên thêm một ngoại lệ giống nhau nhiều lần chỉ để tăng số lượng suppressed?** Không, trừ khi có lý do thực sự và muốn lưu nhiều lần; API không phải hệ thống đếm resource duy nhất.
17. **Nếu suppressed chứa `IOException`, `catch (IOException)` đặt sau TWR có tự bắt lỗi phụ đó khi primary là `IllegalStateException` không?** Không. Handler chọn theo **loại của primary**; muốn đọc IOException phụ thì duyệt `getSuppressed()`.
18. **Lỗi bị suppressed có đồng nghĩa ứng dụng đã xử lý an toàn không?** Không; nó vẫn có thể biểu thị thao tác dọn dẹp thất bại nghiêm trọng.

## 18. Nguồn chuẩn Java 17

- [Java SE 17 API — Throwable.addSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): kiểm tra đối số và lưu suppressed exception.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): danh sách lỗi phụ, mảng kết quả và suppression disabled.
- [Java SE 17 API — Throwable constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `enableSuppression` và `writableStackTrace`.
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): ngữ nghĩa primary/suppressed và thứ tự đóng tài nguyên.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` và checked exception.
- [Java SE 17 API — Throwable.printStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#printStackTrace()): in nguyên nhân, stack trace và suppressed.

**Ghi nhớ:** `addSuppressed` gắn một lỗi bổ sung vào **một đối tượng Throwable chính**, còn `getSuppressed()` trả lại các lỗi bổ sung ấy theo dạng mảng. Trong `try-with-resources`, Java thường tự dùng cơ chế này để giữ lỗi công việc làm **primary** và lưu lỗi dọn dẹp thành **suppressed**. Đọc cả `cause` và `suppressed` để chẩn đoán, không nhầm suppression với việc lỗi đã được khắc phục.
