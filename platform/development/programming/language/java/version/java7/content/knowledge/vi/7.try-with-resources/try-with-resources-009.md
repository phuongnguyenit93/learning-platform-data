# Đọc ngoại lệ bị giữ lại bằng `getSuppressed()` trong Java `try-with-resources`

## 1. Vì sao cần `getSuppressed()`?

Khi làm việc với file, luồng I/O, kết nối hoặc đối tượng có `close()`, **hai lỗi có thể xảy ra trong cùng một lần sử dụng tài nguyên**:

1. Phần thân `try` gặp lỗi khi đang thực hiện công việc.
2. Tài nguyên lại gặp lỗi khi Java tự gọi `close()` để dọn dẹp.

Nếu chỉ được truyền ra một ngoại lệ, làm thế nào để **không đánh mất thông tin lỗi còn lại**? Từ Java 7, `try-with-resources` tích hợp cơ chế *suppressed exceptions*: giữ một ngoại lệ đóng vai trò **primary** (ngoại lệ chính) và gắn các lỗi phát sinh sau vào danh sách **suppressed** của nó. Lập trình viên đọc danh sách ấy qua phương thức **`Throwable.getSuppressed()`**.

Cơ chế này **vẫn còn nguyên giá trị trong Java hiện đại**. Tên phương thức `getSuppressed()` không thuộc riêng `Exception` hay `IOException`; nó được khai báo trong `java.lang.Throwable`, nên cũng có trên các lớp kế thừa như `RuntimeException` và `Error`.

### Mục tiêu của bài

- Nhận diện ngoại lệ **primary**, ngoại lệ **suppressed** và hoàn cảnh Java tạo mối quan hệ giữa chúng.
- Gọi `getSuppressed()`, duyệt mảng `Throwable[]` và đọc đúng loại lỗi, thông điệp, stack trace của từng mục.
- Dự đoán ngoại lệ nào là primary khi **thân `try` lỗi**, khi **chỉ `close()` lỗi**, khi có **nhiều resource**, hoặc khi **khởi tạo resource thất bại**.
- Phân biệt **`getSuppressed()`** và **`getCause()`**; chúng mô tả hai mối quan hệ khác nhau và có thể xuất hiện đồng thời.
- Biết xử lý trường hợp **danh sách rỗng**, **suppression bị vô hiệu hóa** hoặc cần ghi log/test một cách an toàn.
- Áp dụng các ví dụ Java **17+ có thể biên dịch và chạy độc lập**; kết quả stdout được trình bày tách biệt với thông báo lỗi compiler/JVM thay đổi theo môi trường.

**Mốc phiên bản:** `try-with-resources`, `getSuppressed()` và `addSuppressed()` xuất hiện từ **Java 7** và tiếp tục được quy định bởi [JLS Java SE 26 §14.20.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3) và [API `Throwable` Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html). Bài dùng các ví dụ tương thích Java 17+ để minh họa quy tắc hiện hành, không hướng dẫn quản lý thủ công tài nguyên theo cách đã không còn phù hợp làm lựa chọn mặc định.

## 2. Primary và suppressed trong `try-with-resources`

Cấu trúc minh họa:

~~~java
try (Resource resource = openResource()) {
    doWork(resource);
} catch (Exception ex) {
    System.err.println("Primary: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Suppressed: " + suppressed);
    }
}
~~~

Đây là **đoạn minh họa**, giả định các kiểu/phương thức `Resource`, `openResource()`, `doWork(...)` do ứng dụng khai báo. Mã cho thấy **đọc suppressed ngay tại handler**, không phải chương trình độc lập.

Luồng thực thi cơ bản:

1. Java khởi tạo tài nguyên trong ngoặc `try (...)`.
2. Thân `try` sử dụng tài nguyên.
3. Khi thoát, Java tự gọi `close()` trên tài nguyên đã khởi tạo thành công.
4. Nếu thân `try` ném lỗi **A** và `close()` ném lỗi **B**, lỗi **A** thường là **primary** được truyền ra ngoài; lỗi **B** được thêm bằng cơ chế tương đương `A.addSuppressed(B)`.
5. Ở nhánh `catch` bao quanh, `ex` tham chiếu đến ngoại lệ chính. `ex.getSuppressed()` trả các ngoại lệ đã được ghi nhận là suppressed trên **chính đối tượng `ex` ấy**.

**Không phải mọi ngoại lệ được bắt đều có suppressed exceptions.** Nếu không có lỗi thứ hai, nếu các lời gọi `close()` thành công, hoặc nếu suppression bị vô hiệu hóa trên ngoại lệ chính, danh sách trả về có thể rỗng.

### 2.1. Không đánh đồng lỗi chính với lỗi “nghiêm trọng nhất”

Từ **primary** ở đây nói về **quy tắc ưu tiên khi lan truyền exception**, không phải xếp hạng độ nguy hiểm của sự cố. Nếu thân `try` thất bại khi đọc dữ liệu nhưng việc đóng file cũng thất bại, primary thường là lỗi đọc; suppressed ghi nhận lỗi đóng.

Lỗi đóng có thể cần điều tra độc lập, nhất là khi liên quan đến **flush, commit/rollback, gửi dữ liệu, giải phóng khóa, đóng giao dịch hoặc trạng thái tài nguyên** theo hợp đồng API. Đừng xóa, nuốt hay coi chúng là “không đáng quan tâm” chỉ vì bị suppressed.

### 2.2. Một tình huống, hai vị trí phát sinh lỗi

~~~text
try (resource) {
    work();             // IOException("work failure")
}
resource.close();       // IOException("close failure") - gọi tự động

Khi đi tới catch:
  primary   = IOException("work failure")
  suppressed[0] = IOException("close failure")
~~~

Đây là **sơ đồ luồng**, không phải Java source; dòng `resource.close()` tượng trưng cho bước đóng tự động, **không yêu cầu người viết gọi thêm `close()` bằng tay**.

## 3. Chương trình Java 17+: đọc `getSuppressed()` lần đầu

Tạo file `SuppressedBasicsDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedBasicsDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failure");
        }
    }

    public static void main(String[] args) {
        try (Resource r = new Resource()) {
            throw new IOException("work failure");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            for (Throwable other : ex.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
            System.out.println("cause=" + ex.getCause());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SuppressedBasicsDemo.java
java SuppressedBasicsDemo
~~~

Stdout **chính xác**:

~~~text
primary=work failure
suppressedCount=1
suppressed=close failure
cause=null
~~~

Phân tích:

- `Resource implements AutoCloseable`. Java thấy đây là tài nguyên hợp lệ để quản lý.
- Thân `try` ném `IOException("work failure")`. Đây là ngoại lệ chính.
- Khi đóng, `close()` ném `IOException("close failure")`. Java **không thay thế** lỗi làm việc bằng lỗi đóng mà lưu nó vào suppressed list của lỗi chính.
- `ex.getSuppressed().length` bằng `1`; vòng lặp `for (Throwable other : ...)` in thông điệp lỗi đóng.
- `ex.getCause()` là `null`, bởi chương trình **không thiết lập cause** cho `IOException("work failure")`. Sự tồn tại của suppressed exception **không tự tạo quan hệ cause**.
- Ngoại lệ được bắt sau khi Java đã cố thực hiện bước đóng. Đây là lý do có thể đọc danh sách suppressed **ngay trong `catch`** của cùng `try-with-resources`.

Trong ứng dụng thật, hàm `close()` không nên cố ý ném lỗi; ví dụ này tạo hai exception có chủ đích để nhìn rõ cơ chế và có stdout lặp lại được.

## 4. Hợp đồng chính xác của `Throwable.getSuppressed()`

Chữ ký API:

~~~java
public final synchronized Throwable[] getSuppressed()
~~~

Đây là **chữ ký ở mức mô tả API**: trong thực tế, `getSuppressed()` là phương thức `final` của `Throwable`; từ khóa đồng bộ và chi tiết triển khai không phải điều người gọi cần phụ thuộc. Cách dùng thông thường chỉ là:

~~~java
Throwable[] suppressed = ex.getSuppressed();
~~~

Dòng trên là **đoạn minh họa** với `ex` kiểu `Throwable` hoặc lớp con. Theo API hiện hành, cần nhớ:

| Thuộc tính | Ý nghĩa thực hành |
| --- | --- |
| Kiểu trả về | `Throwable[]`, **không phải** `Exception[]`, `List<Exception>` hoặc một chuỗi thông báo |
| Khi không có suppressed | Trả mảng **độ dài 0**, không trả `null` |
| Khi suppression disabled | Cũng trả mảng độ dài 0, ngay cả khi đã cố gọi `addSuppressed()` |
| Các phần tử | Là các đối tượng `Throwable`; có kiểu, thông điệp, stack trace và có thể có `getCause()`/suppressed của riêng chúng |
| Trạng thái mảng trả về | Thay đổi phần tử trong mảng đã nhận **không sửa** danh sách suppressed của exception; lời gọi sau không phụ thuộc những chỉnh sửa đó |
| Tính đồng thời | Phương thức được đặc tả an toàn khi gọi từ nhiều thread; nhưng điều đó không biến mọi thao tác cập nhật/traversal ngoại lệ thành cơ chế đồng bộ cho ứng dụng |
| Nguồn suppressed | Thường do Java tự thêm trong `try-with-resources`; code hoặc framework **cũng có thể tự gọi `addSuppressed()`** khi muốn giữ lỗi độc lập |

### 4.1. Cách đọc an toàn

~~~java
Throwable[] others = ex.getSuppressed();
if (others.length == 0) {
    System.out.println("No suppressed exception");
} else {
    for (Throwable other : others) {
        System.out.println(other.getClass().getName()
                + ": " + other.getMessage());
    }
}
~~~

Đây là đoạn bên trong một phương thức có biến `ex` kiểu `Throwable`; không phải chương trình độc lập.

**Không** viết mặc định `ex.getSuppressed()[0]` khi chưa kiểm tra độ dài: nếu mảng rỗng, code sẽ ném `ArrayIndexOutOfBoundsException`, che khuất vấn đề gốc. Không dựa chỉ vào `getMessage()` để xác định bản chất lỗi: thông điệp có thể là `null`, trùng nhau hoặc bị thay đổi theo thư viện/phiên bản. Xem **loại exception và stack trace** để điều tra chính xác.

### 4.2. Không sửa mảng để “xóa lỗi”

Mảng mà `getSuppressed()` trả về là dữ liệu đọc. Ví dụ:

~~~java
Throwable[] snapshot = ex.getSuppressed();
if (snapshot.length > 0) {
    snapshot[0] = new IllegalStateException("local replacement");
}
~~~

Đây là đoạn minh họa. Sửa `snapshot[0]` **không thay** suppressed exception thực đang được lưu trong đối tượng `ex`. Nếu cần lưu kết quả kiểm tra, hãy tạo cấu trúc báo cáo riêng, không tìm cách làm sạch exception bằng cách chỉnh mảng.

## 5. Nhiều resource: thứ tự suppressed thường theo thứ tự đóng ngược

Với:

~~~java
try (Resource left = openLeft(); Resource right = openRight()) {
    doWork();
}
~~~

Đây là đoạn minh họa có phương thức/class riêng chưa khai báo. Java khởi tạo **left → right**, rồi đóng **right → left**. Nếu thân `try` đã ném một exception, lỗi từ các lời gọi `close()` sau đó được ghi vào suppressed list của exception ấy khi chúng phát sinh.

Tạo file `MultiSuppressedDemo.java`:

~~~java
import java.io.IOException;

public class MultiSuppressedDemo {
    static final class Named implements AutoCloseable {
        final String name;

        Named(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close failed:" + name);
        }
    }

    public static void main(String[] args) {
        try (Named left = new Named("left");
             Named right = new Named("right")) {
            System.out.println("body");
            throw new IllegalArgumentException("body failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable other : ex.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 MultiSuppressedDemo.java
java MultiSuppressedDemo
~~~

Stdout chính xác:

~~~text
open:left
open:right
body
close:right
close:left
primary=body failed
suppressed=close failed:right
suppressed=close failed:left
~~~

**Diễn giải theo thời gian:**

1. `left` khởi tạo trước `right`.
2. Thân `try` in `body`, rồi ném `IllegalArgumentException("body failed")`. Ngoại lệ này là **primary**, mặc dù không phải `IOException`.
3. Khi dọn dẹp, `right.close()` được gọi trước; lỗi `IOException("close failed:right")` được thêm vào primary.
4. Sau đó `left.close()` cũng được gọi dù thao tác đóng `right` đã thất bại; lỗi của nó được thêm vào primary.
5. Trong `catch`, `getSuppressed()` chứa **hai phần tử** theo thứ tự được thêm: lỗi đóng `right` rồi lỗi đóng `left`.

**Không kết luận từ tên exception rằng lỗi đóng nào “nghiêm trọng hơn”.** Vị trí của chúng trong danh sách phản ánh thứ tự diễn tiến và cơ chế suppression của câu lệnh này. Nếu một `close()` không ném lỗi, tất nhiên nó không tạo thêm suppressed exception.

## 6. Thân `try` thành công nhưng `close()` lỗi: primary là lỗi đóng đầu tiên

Một hiểu lầm phổ biến: “Mọi lỗi từ `close()` luôn là suppressed.” **Sai.** Nếu trước bước đóng **chưa có ngoại lệ nào**, lỗi đóng đầu tiên sẽ là **primary**. Với nhiều resource, vì đóng từ phải sang trái, lỗi từ resource ở **phía phải nhất không đóng được** sẽ là primary. Những lỗi đóng xảy ra tiếp theo có thể trở thành suppressed.

Tạo file `CloseOnlyDemo.java`:

~~~java
import java.io.IOException;

public class CloseOnlyDemo {
    static final class Named implements AutoCloseable {
        final String name;

        Named(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close failed:" + name);
        }
    }

    public static void main(String[] args) {
        try (Named left = new Named("left");
             Named right = new Named("right")) {
            System.out.println("body-ok");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable other : ex.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 CloseOnlyDemo.java
java CloseOnlyDemo
~~~

Stdout chính xác:

~~~text
body-ok
close:right
close:left
primary=close failed:right
suppressed=close failed:left
~~~

Ở đây phần thân **không ném exception**. Khi đóng `right` thì phát sinh lỗi đầu tiên, vì vậy **lỗi đóng `right` là primary**, lỗi `left` trở thành suppressed. Nếu chỉ có một resource, thân thành công nhưng `close()` thất bại, ngoại lệ đóng đó sẽ được truyền ra trực tiếp và thường **không có suppressed exception**.

Điểm này đặc biệt quan trọng khi test: không được viết assertion cố định “mọi lỗi `close` phải nằm trong `getSuppressed()`” mà không xem **bước nào đã lỗi trước**.

## 7. Resource thứ hai khởi tạo lỗi: thông tin lỗi đóng resource trước vẫn được giữ

`try-with-resources` khởi tạo nhiều resource **từ trái sang phải**. Nếu khởi tạo resource thứ hai thất bại, thân `try` không chạy, nhưng Java vẫn cố đóng resource thứ nhất đã khởi tạo thành công.

Nếu việc đóng resource thứ nhất cũng thất bại, lỗi **khởi tạo** giữ vai trò primary; lỗi **đóng tài nguyên trước đó** nằm trong suppressed list.

Tạo file `InitSuppressedDemo.java`:

~~~java
import java.io.IOException;

public class InitSuppressedDemo {
    static final class Named implements AutoCloseable {
        final String name;

        Named(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close failed:" + name);
        }
    }

    static Named open(String name, boolean fail) throws IOException {
        System.out.println("init:" + name);
        if (fail) {
            throw new IOException("init failed:" + name);
        }
        return new Named(name);
    }

    public static void main(String[] args) {
        try (Named left = open("left", false);
             Named right = open("right", true)) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable other : ex.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 InitSuppressedDemo.java
java InitSuppressedDemo
~~~

Stdout chính xác:

~~~text
init:left
init:right
close:left
primary=init failed:right
suppressed=close failed:left
~~~

Bốn điều cần nhớ:

- Lệnh `open("right", true)` ném lỗi, nên **không** in `body`.
- `left` đã khởi tạo thành công trước đó nên Java đóng nó khi việc khởi tạo bên phải thất bại.
- `right` không tạo xong đối tượng, vì vậy không có một đối tượng `right` đã đăng ký để đóng.
- Ngoại lệ đóng `left` được suppressed vào lỗi khởi tạo `right`.

Cảnh báo thiết kế: nếu một hàm mở tài nguyên **tự cấp phát tài nguyên bên trong rồi ném lỗi trước khi trả về đối tượng**, nó vẫn phải tự dọn phần mở dở theo hợp đồng của chính hàm đó. `try-with-resources` không thể đóng một đối tượng chưa được trả về và chưa được ghi nhận là resource đã khởi tạo thành công.

## 8. `getSuppressed()` khác `getCause()` ở điểm nào?

Hai API đều có trên `Throwable`, nhưng diễn đạt **hai loại quan hệ khác nhau**:

| Câu hỏi | `getCause()` | `getSuppressed()` |
| --- | --- | --- |
| Quan hệ | Ngoại lệ **nào dẫn đến** ngoại lệ hiện tại (chuỗi nguyên nhân) | Các ngoại lệ khác **được giữ lại bên cạnh** ngoại lệ primary |
| Kiểu trả về | Một `Throwable` hoặc `null` | Mảng `Throwable[]`, có thể rỗng |
| Ví dụ | Bọc `IOException` thành `IllegalStateException("operation failed", io)` | Thân `try` lỗi, `close()` cũng lỗi nên lỗi đóng được suppressed |
| Số lượng trực tiếp | Một cause trực tiếp, có thể có cause của cause | Không giới hạn ở một lỗi; nhiều resource có thể sinh nhiều suppressed |
| Được JVM tự thêm khi `try-with-resources` đóng lỗi? | **Không** tự gán cause chỉ vì close lỗi | **Có**, theo quy tắc suppression |
| Khi không có quan hệ | `null` | Mảng rỗng |

Một exception có thể **đồng thời** có cause và có các suppressed exceptions. Điều đó không mâu thuẫn: cause giải thích nguồn gốc theo một chuỗi; suppressed giữ lại những lỗi song song đã phát sinh trong quá trình xử lý/cleanup.

Ví dụ file `CauseVsSuppressedDemo.java`:

~~~java
import java.io.IOException;

public class CauseVsSuppressedDemo {
    public static void main(String[] args) {
        IOException underlying = new IOException("disk");
        IllegalStateException ex =
                new IllegalStateException("operation failed", underlying);

        ex.addSuppressed(new IOException("cleanup"));

        System.out.println("message=" + ex.getMessage());
        System.out.println("cause=" + ex.getCause().getMessage());
        System.out.println("suppressed=" + ex.getSuppressed()[0].getMessage());
    }
}
~~~

~~~bash
javac --release 17 CauseVsSuppressedDemo.java
java CauseVsSuppressedDemo
~~~

Stdout chính xác:

~~~text
message=operation failed
cause=disk
suppressed=cleanup
~~~

Ở đây `getCause()` trả `IOException("disk")`, do constructor `IllegalStateException(..., underlying)` thiết lập. Còn `getSuppressed()[0]` trả `IOException("cleanup")`, do code **chủ động** gọi `addSuppressed()`. Đây là ví dụ minh họa rằng cơ chế suppressed không chỉ dành cho compiler; thư viện có thể sử dụng nó để giữ những lỗi **độc lập** mà chỉ một exception có thể được ném ra.

**Không thay mọi `getSuppressed()` bằng `getCause()`** và cũng không tự đặt tất cả lỗi đóng tài nguyên làm cause: như vậy sẽ mất ý nghĩa phân biệt của hai API.

## 9. Khi `getSuppressed()` trả mảng rỗng

### 9.1. Không hề có lỗi đóng

Ví dụ `NothingSuppressedDemo.java`:

~~~java
import java.io.IOException;

public class NothingSuppressedDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            // Đóng thành công.
        }
    }

    public static void main(String[] args) {
        try (Resource r = new Resource()) {
            throw new IOException("body only");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
        }
    }
}
~~~

~~~bash
javac --release 17 NothingSuppressedDemo.java
java NothingSuppressedDemo
~~~

Stdout chính xác:

~~~text
primary=body only
count=0
~~~

Có primary từ thân `try`, nhưng tài nguyên đóng thành công. Do không có lỗi khác cần giữ, `getSuppressed()` trả mảng rỗng. **Mảng rỗng không có nghĩa primary không xảy ra.**

### 9.2. Suppression được vô hiệu hóa trên ngoại lệ chính

`Throwable` có một constructor được bảo vệ cho phép bật/tắt suppression. Nếu tạo một Throwable với `enableSuppression=false`, `addSuppressed(...)` không giữ lại các ngoại lệ được thêm; `getSuppressed()` trả mảng rỗng. Đây là **khả năng còn tồn tại trong API hiện hành**, không phải lựa chọn mặc định nên áp dụng để giấu lỗi.

File `SuppressionDisabledDemo.java`:

~~~java
import java.io.IOException;

public class SuppressionDisabledDemo {
    static final class Disabled extends Exception {
        Disabled(String message) {
            super(message, null, false, true);
        }
    }

    public static void main(String[] args) {
        Disabled ex = new Disabled("primary");
        ex.addSuppressed(new IOException("cleanup"));

        System.out.println("primary=" + ex.getMessage());
        System.out.println("count=" + ex.getSuppressed().length);
    }
}
~~~

~~~bash
javac --release 17 SuppressionDisabledDemo.java
java SuppressionDisabledDemo
~~~

Stdout chính xác:

~~~text
primary=primary
count=0
~~~

Giải thích: tham số thứ ba của constructor `Throwable(String, Throwable, boolean, boolean)` quyết định suppression có bật hay không. Ở đây là `false`, nên lời gọi `addSuppressed(...)` không thay đổi danh sách. Ví dụ này dùng **để nhận diện điều kiện biên**; tránh vô hiệu hóa suppression trong exception tự viết khi ứng dụng cần giữ lỗi dọn dẹp. Với `try-with-resources`, nếu primary có suppression disabled, thông tin lỗi đóng có thể **không xuất hiện** trong `getSuppressed()` dù việc đóng đã gặp lỗi.

### 9.3. Không nhận suppressed ở đúng đối tượng ngoại lệ

Nếu code tạo exception wrapper mới sau khi bắt:

~~~java
try {
    operation();
} catch (IOException original) {
    throw new IllegalStateException("Cannot proceed", original);
}
~~~

Đây là đoạn minh họa trong phương thức, có `operation()` do ứng dụng định nghĩa. Sau khi bọc lỗi theo cách này:

- `wrapper.getCause()` là `original`.
- `wrapper.getSuppressed()` thường **rỗng**, nếu chưa thêm suppressed vào wrapper.
- Nếu `original` có suppressed exceptions, truy cập bằng `wrapper.getCause().getSuppressed()` (sau khi kiểm tra cause khác `null`), hoặc dùng công cụ ghi log biết duyệt cả cause và suppressed.

**Đừng nhầm danh sách của một ngoại lệ với toàn bộ cây lỗi.** `getSuppressed()` chỉ trả danh sách gắn trực tiếp với chính đối tượng được gọi.

## 10. Ghi log và điều tra: đừng chỉ in `ex.getMessage()`

Một câu lệnh như:

~~~java
logger.log(Level.SEVERE, "Failed while processing resource", ex);
~~~

là **đoạn minh họa** sử dụng `java.util.logging.Logger` và `java.util.logging.Level`; `logger` phải được khai báo. Việc truyền **đối tượng ngoại lệ gốc** cho logger giúp formatter/handler có cơ hội ghi stack trace cùng cause/suppressed. Cách trình bày phụ thuộc hệ thống logging thực tế; không hứa rằng mọi backend đều hiển thị tự động nếu cấu hình formatter đã loại bỏ thông tin throwable.

Với thư viện không tự thể hiện suppressed, có thể duyệt trực tiếp:

~~~java
static void logSuppressed(Throwable primary, java.util.logging.Logger logger) {
    logger.log(java.util.logging.Level.SEVERE, "Primary failure", primary);
    for (Throwable other : primary.getSuppressed()) {
        logger.log(java.util.logging.Level.WARNING, "Suppressed failure", other);
    }
}
~~~

Đây là một **phương thức minh họa đặt trong class**, không phải file Java độc lập. Ghi mỗi `Throwable` bằng tham số throwable thay vì chỉ nối `getMessage()` giúp giữ stack trace. Cân nhắc tránh **ghi trùng cùng ngoại lệ** nếu framework đã ghi được cả suppressed; tùy chính sách ứng dụng có thể ưu tiên một log chứa toàn bộ cây lỗi.

### 10.1. `printStackTrace()` hỗ trợ quan sát suppressed

`Throwable.printStackTrace()` của JDK có thể in cả nguyên nhân `Caused by:` và các dòng `Suppressed:`. Điều này hữu ích khi chạy thử:

~~~java
ex.printStackTrace();
~~~

Đây là đoạn minh họa trong một handler. **Không đưa stack trace đầy đủ làm stdout cố định**: tên file, số dòng, class loader và bố cục dòng có thể khác theo môi trường. Trong ứng dụng server, dùng logger có cấu hình thay vì in lỗi trực tiếp ra console một cách thiếu kiểm soát.

### 10.2. Kiểm tra suppressed khi viết test

Với các test lỗi cleanup, nên kiểm tra **cả primary và danh sách**:

~~~java
Throwable[] others = ex.getSuppressed();
if (others.length != 2) {
    throw new AssertionError("Expected two suppressed failures");
}
if (!"close failed:right".equals(others[0].getMessage())) {
    throw new AssertionError("Unexpected first close failure");
}
~~~

Đây là **đoạn bên trong một test/method** có `ex` tham chiếu ngoại lệ chính. Trong bài test thật, nên dùng framework assertion phù hợp và/hoặc kiểm tra **type** của exception. Đặt điều kiện số lượng trước khi truy cập chỉ số để lỗi test thể hiện rõ vấn đề. Không khẳng định test cần sử dụng đúng chuỗi thông báo lỗi của thư viện bên thứ ba nếu thông điệp không thuộc hợp đồng ổn định của nó.

### 10.3. Khi có nhiều tầng cause và suppressed

Một exception có thể giữ:

- Một `getCause()`; cause ấy có thể có cause tiếp.
- Nhiều `getSuppressed()`; một suppressed exception cũng có thể có cause hoặc suppressed của riêng nó.

Nếu viết công cụ duyệt toàn bộ đồ thị lỗi, dùng cơ chế đánh dấu đối tượng đã thăm (ví dụ tập dùng **identity**), vì cấu trúc lỗi do code/framework tự ghép không nên bị giả định luôn là một cây hoàn hảo. Đối với log ứng dụng thông thường, ưu tiên formatter/handler đáng tin đã hỗ trợ cấu trúc `Throwable` thay vì tự viết hàm đệ quy thiếu giới hạn.

## 11. Các nhầm lẫn cần tránh

| Nhận định sai | Quy tắc chính xác |
| --- | --- |
| “`getSuppressed()` chỉ dùng cho `IOException`” | Phương thức thuộc `Throwable`, áp dụng cho các lớp con và cả exception do app tạo |
| “Nếu thân `try` lỗi, lỗi `close()` sẽ thay thế nó” | Với `try-with-resources`, lỗi thân thường là primary và lỗi đóng được suppressed |
| “Mọi lỗi `close()` đều suppressed” | Nếu thân chạy thành công, lỗi đóng đầu tiên có thể là primary |
| “Có hai tài nguyên, lỗi đóng của tài nguyên khai báo trước sẽ xuất hiện trước” | Đóng ngược thứ tự; nếu cả hai lỗi, tài nguyên bên phải thường xuất hiện trước |
| “Nếu initializer thứ hai lỗi, resource thứ nhất không được đóng” | Java vẫn cố đóng tài nguyên đã khởi tạo thành công ở bên trái; lỗi đóng có thể suppressed vào lỗi initializer |
| “`getSuppressed()` trả `null` nếu không có gì” | Trả mảng `Throwable[]` rỗng |
| “Lấy `getSuppressed()[0]` lúc nào cũng an toàn” | Phải kiểm tra `length` trước |
| “`getSuppressed()` giống `getCause()`” | Cause mô tả quan hệ nguyên nhân; suppressed giữ các lỗi khác bên cạnh primary |
| “`ex.getCause()==null` thì không có suppressed” | Hai mối quan hệ độc lập; ví dụ đầu cho thấy cause `null` và suppressed có 1 phần tử |
| “Exception wrapper mới tự chép suppressed của cause” | Không tự chép; suppressed gắn với từng đối tượng ngoại lệ |
| “`addSuppressed()` chỉ compiler được gọi” | API công khai cho code gọi; cần giữ ý nghĩa là các lỗi độc lập, không phải chuỗi nhân quả |
| “Chỉnh mảng `getSuppressed()` sẽ xóa lỗi” | Không; mảng trả về không phải giao diện để sửa danh sách nội bộ |
| “Suppression luôn được bật trong mọi Throwable” | Một constructor của `Throwable` cho phép tắt; `getSuppressed()` khi đó rỗng |
| “Không thấy `Suppressed:` trong log tức không có lỗi đóng” | Có thể formatter loại bỏ thông tin hoặc suppression bị tắt; cần kiểm tra API và cấu hình |
| “Bắt lỗi và chỉ in message là đủ để điều tra” | Cần xem loại exception, stack trace, cause và suppressed, tránh làm mất chẩn đoán |

## 12. Bảng dự đoán hành vi trước khi chạy

Giả sử các tài nguyên đều tuân theo `AutoCloseable` và suppression được bật trên exception liên quan:

| Tình huống | Primary khi ra ngoài | `getSuppressed()` trên primary |
| --- | --- | --- |
| Thân `try` lỗi A, đóng một resource lỗi B | A | Có B |
| Thân `try` lỗi A, mọi resource đóng thành công | A | Rỗng |
| Thân `try` thành công, đóng một resource lỗi B | B | Thường rỗng |
| Thân `try` thành công, đóng right lỗi B rồi left lỗi C | B | Có C |
| Thân `try` lỗi A, đóng right lỗi B và left lỗi C | A | Có B, rồi C |
| Khởi tạo resource sau lỗi A, đóng resource trước lỗi B | A | Có B |
| Không có lỗi ở thân, khởi tạo, hay đóng | Không có exception | Không có primary để gọi phương thức |
| Primary bị tắt suppression | Primary theo luồng thông thường | Mảng rỗng dù có thể xảy ra lỗi đóng |

**Giới hạn của bảng:** Đây là mô hình các tình huống minh họa, không phải bảo đảm rằng mọi lần gọi `close()` đều ném một exception độc lập hoặc rằng mọi wrapper không có xử lý nội bộ. Một API tùy chỉnh có thể tự tạo suppressed exceptions, có thể có cause, hoặc có chính sách cleanup riêng. Khi chẩn đoán lỗi thực tế, kiểm tra cả hợp đồng resource, thứ tự thao tác và ngoại lệ thật được ném.

## 13. Quy trình xử lý sự cố `try-with-resources` trong dự án thực tế

1. **Xác định đoạn bị lỗi:** exception chính đến từ mở resource, thân xử lý hay `close()`? Đọc kiểu, thông điệp và stack trace của primary.
2. **Đọc suppressed:** gọi `getSuppressed()` trên **đúng primary đang xử lý**; nếu có nhiều mục, kiểm tra theo thứ tự được ghi nhận.
3. **Đọc cause:** kiểm tra `getCause()` riêng, nhất là khi exception đã được framework bọc lại.
4. **Vẽ lại thứ tự tài nguyên:** khai báo trái → phải, đóng phải → trái. Xác định resource đã mở thành công nếu lỗi phát sinh từ initializer.
5. **Đối chiếu hợp đồng `close()`:** resource có flush/ghi dữ liệu khi đóng không? Có thể ném checked exception nào? Wrapper có đóng resource nền không?
6. **Giữ nguyên bằng chứng:** không thay thế hoặc nuốt primary; khi chuyển sang lỗi tầng cao, dùng constructor nhận cause phù hợp. Đừng tự gán mọi lỗi cleanup làm cause.
7. **Ghi log đủ cấu trúc:** truyền đối tượng throwable cho logger; bảo đảm formatter có thể hiển thị cause và suppressed; tránh in dữ liệu nhạy cảm từ exception message.
8. **Thêm test hồi quy:** mô phỏng lỗi ở thân, đóng một resource, đóng nhiều resource và khởi tạo không thành công, rồi assert loại, thứ tự và số lượng suppressed.
9. **Không “sửa” bằng cách tắt suppression:** điều đó chỉ xóa dấu vết chẩn đoán. Ưu tiên khắc phục nguyên nhân lỗi đóng và bảo vệ trạng thái dữ liệu/tài nguyên.
10. **Lựa chọn code hiện hành:** tiếp tục dùng `try-with-resources` cho đối tượng `AutoCloseable`; không thêm `finally { resource.close(); }` trùng lặp nếu resource đã được quản lý đúng. Xử lý trường hợp riêng của API theo hợp đồng, không mặc định cleanup là hoàn toàn an toàn hay không bao giờ thất bại.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Thân `try` ném `IOException("read")`, resource `close()` ném `IOException("close")`. Exception truyền ra là gì?  
**Đáp án:** `IOException("read")` là primary; `getSuppressed()` trên nó có ngoại lệ đóng `IOException("close")`, trừ các điều kiện đặc biệt như suppression disabled.

**Câu 2.** Thân `try` chạy xong, resource duy nhất đóng bị lỗi. `getSuppressed()` có bắt buộc chứa lỗi đóng không?  
**Đáp án:** Không. Lỗi đóng là **primary** vì trước đó không có exception; danh sách suppressed thường rỗng.

**Câu 3.** `try (A a = ...; B b = ...)`, thân ném lỗi, cả hai `close()` lỗi. Thứ tự đọc suppressed?  
**Đáp án:** Thông thường lỗi `b.close()` trước, lỗi `a.close()` sau, do Java đóng theo thứ tự ngược khai báo.

**Câu 4.** `getCause()` trả `null`, có chắc `getSuppressed()` rỗng?  
**Đáp án:** Không. Cause và suppressed là hai quan hệ riêng; ví dụ `SuppressedBasicsDemo` có `cause=null` nhưng một suppressed exception.

**Câu 5.** Khi khởi tạo tài nguyên thứ hai lỗi, tại sao vẫn có suppressed exception?  
**Đáp án:** Vì tài nguyên thứ nhất đã được mở có thể bị lỗi khi Java cố đóng nó; lỗi đóng được thêm vào ngoại lệ khởi tạo thứ hai.

**Câu 6.** Có thể đổi nội dung `ex.getSuppressed()[0]` để sửa lỗi trong exception?  
**Đáp án:** Không. Việc đổi phần tử trong mảng trả về không thay danh sách suppressed bên trong `ex`.

**Câu 7.** `getSuppressed()` trả mảng rỗng; liệu chắc chắn không có lỗi tài nguyên?  
**Đáp án:** Không. Có thể không có lỗi thứ hai, lỗi đóng chính là primary, suppression đã tắt, hoặc bạn đang kiểm tra một wrapper thay vì exception gốc.

**Câu 8.** Có nên dùng `getSuppressed()` thay cho `getCause()` khi bọc `IOException` thành `IllegalStateException`?  
**Đáp án:** Không. Giữ cause cho quan hệ nguyên nhân; suppressed chỉ dành cho những lỗi khác cần giữ lại song song.

**Câu 9.** Mọi suppressed exception đều bắt nguồn từ `close()`?  
**Đáp án:** Không. Code cũng có thể chủ động dùng `addSuppressed()` để lưu các lỗi độc lập; trong `try-with-resources`, các lỗi đóng tự động là nguồn rất phổ biến.

**Câu 10.** Muốn thấy thông tin lỗi từ resource khi vận hành, có đủ nếu chỉ log `ex.getMessage()`?  
**Đáp án:** Không. Hãy log chính `Throwable`, kiểm tra stack trace, cause và suppressed, đồng thời xác nhận formatter không loại bỏ chúng.

## 15. Tài liệu chính thức

- [Java SE 26 JLS §14.20.3 — try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3): quy tắc khởi tạo, đóng ngược thứ tự và giữ suppressed exception, kể cả lỗi initializer.
- [Java SE 26 JLS §14.20.3.1 — Basic try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3.1): ngữ nghĩa primary/suppressed và phép diễn giải cấu trúc thành `try/catch/finally` để xác định lỗi được giữ.
- [Java SE 26 API — `Throwable.getSuppressed()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): kiểu `Throwable[]`, mảng rỗng và tính độc lập của mảng trả về.
- [Java SE 26 API — `Throwable.addSuppressed(Throwable)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): cách đăng ký lỗi suppressed và các giới hạn của đối số.
- [Java SE 26 API — `Throwable.getCause()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html#getCause()): quan hệ cause khác suppressed.
- [Java SE 26 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng tài nguyên được đóng tự động.
- [Java SE 7 JLS §14.20.3](https://docs.oracle.com/javase/specs/jls/se7/html/jls-14.html#jls-14.20.3): nguồn lịch sử xác nhận ngữ nghĩa cơ bản đã xuất hiện từ Java 7; khi viết Java hiện hành, ưu tiên đặc tả hiện hành ở các liên kết phía trên.

**Ghi nhớ:** `getSuppressed()` là công cụ **không làm mất dấu vết lỗi cleanup**. Hãy xác định **ngoại lệ nào xảy ra trước, tài nguyên nào đóng trước, có cause hay không và suppression có bật không**. Khi thân `try` lỗi, lỗi `close()` thường được giữ trong primary; khi thân thành công nhưng `close()` lỗi, lỗi đóng đầu tiên có thể chính là primary.