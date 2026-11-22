# Khối `finally` khi `try` hoàn tất bình thường hoặc phát sinh ngoại lệ trong Java

Khối **`finally`** là phần tùy chọn của cấu trúc `try` trong Java, dùng để thực hiện công việc cần làm **khi luồng điều khiển rời cấu trúc `try`**, bất kể phần `try` hoàn tất bình thường hay kết thúc bất thường vì ngoại lệ. Nếu có `catch`, `finally` còn chạy sau khi nhánh `catch` được chọn hoàn tất hoặc trước khi một ngoại lệ từ `catch` tiếp tục truyền ra ngoài.

Điều quan trọng là **`finally` không tự bắt ngoại lệ và cũng không bảo đảm chương trình tiếp tục chạy bình thường**. Nó là bước trong quá trình rời khối; sau khi `finally` hoàn tất bình thường, kết quả đang chờ từ `try`/`catch` được giữ nguyên. Nếu chính `finally` ném ngoại lệ hoặc `return`, nó có thể thay thế kết quả đang chờ, thậm chí che mất lỗi gốc.

Bài học này tập trung vào hai đường đi cốt lõi: **`try` hoàn tất bình thường** và **`try` phát sinh ngoại lệ**. Đồng thời, bạn sẽ thấy các trường hợp `catch`, `return`, `throw`, `finally` lồng nhau, giới hạn bảo đảm thực thi và cách dọn dẹp tài nguyên đúng trên Java 17+.

## 1. Cú pháp và vị trí của `finally`

Một cấu trúc `try-catch-finally` thông thường:

~~~java
try {
    // Tác vụ có thể thành công hoặc ném ngoại lệ.
} catch (SomeException ex) {
    // Xử lý ngoại lệ tương ứng.
} finally {
    // Công việc cần thực hiện khi rời cấu trúc.
}
~~~

Đây là khung minh họa; `SomeException` phải là kiểu ngoại lệ hợp lệ và các phần thân cần được thay bằng mã thật.

Java cho phép một số cách tổ chức:

~~~java
// Chỉ try-finally, không có catch.
try {
    work();
} finally {
    cleanup();
}
~~~

~~~java
// Có catch và finally.
try {
    work();
} catch (IOException ex) {
    handle(ex);
} finally {
    cleanup();
}
~~~

~~~java
// Có nhiều catch và một finally.
try {
    work();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
} finally {
    cleanup();
}
~~~

Những đoạn trên là **minh họa cấu trúc**, giả định các phương thức/kiểu/import đã được định nghĩa. Một `try` truyền thống phải có ít nhất một `catch` hoặc một `finally`. Khối `finally` đứng **sau toàn bộ `catch`** của cấu trúc đó và chỉ có **một khối `finally`** trực tiếp cho mỗi `try`.

`finally` không phải phương thức, không có kiểu trả về, không nhận tham số và không có danh sách ngoại lệ `throws` riêng. Nếu câu lệnh bên trong `finally` có thể ném checked exception, nghĩa vụ bắt/khai báo thuộc về phương thức hoặc constructor chứa câu lệnh đó.

## 2. Khi `try` hoàn tất bình thường

**Hoàn tất bình thường** nghĩa là luồng thực thi đi đến hết phần thân `try` mà không bị chuyển hướng bởi một nguyên nhân kết thúc bất thường như ngoại lệ hoặc `return`. Khi đó:

1. Các câu lệnh trong `try` lần lượt được thực thi.
2. Không nhánh `catch` nào của cấu trúc này được chọn.
3. Khối `finally` chạy.
4. Nếu `finally` hoàn tất bình thường, chương trình tiếp tục tại câu lệnh sau toàn bộ cấu trúc `try`/`catch`/`finally`.

Ví dụ ngắn:

~~~java
// Đoạn minh họa bên trong một phương thức.
try {
    System.out.println("A. Trong try");
    System.out.println("B. Try thành công");
} finally {
    System.out.println("C. Trong finally");
}
System.out.println("D. Sau try");
~~~

Stdout:

~~~text
A. Trong try
B. Try thành công
C. Trong finally
D. Sau try
~~~

**Điểm cần nhớ:** `finally` không chỉ chạy khi có ngoại lệ. Nếu `try` đi hết bình thường, `finally` vẫn chạy như bước cuối trước khi rời cấu trúc. Vì vậy không nên coi `finally` là một loại `catch` đặc biệt hay nơi chỉ chứa logic xử lý lỗi.

## 3. Khi `try` phát sinh ngoại lệ và có `catch` phù hợp

Nếu ngoại lệ được ném từ phần thân `try`, Java tìm `catch` phù hợp theo thứ tự đã khai báo. Khi một `catch` bắt được và xử lý thành công:

1. Các câu lệnh còn lại trong phần `try` sau điểm ném bị bỏ qua.
2. Nhánh `catch` phù hợp được thực thi.
3. Sau khi `catch` hoàn tất bình thường, `finally` được thực thi.
4. Nếu `finally` cũng hoàn tất bình thường, chương trình tiếp tục sau toàn bộ cấu trúc.

Ví dụ:

~~~java
// Đoạn minh họa bên trong một phương thức.
try {
    System.out.println("Trong try");
    throw new IllegalArgumentException("dữ liệu sai");
} catch (IllegalArgumentException ex) {
    System.out.println("Đã bắt: " + ex.getMessage());
} finally {
    System.out.println("Trong finally");
}
System.out.println("Sau cấu trúc");
~~~

Stdout:

~~~text
Trong try
Đã bắt: dữ liệu sai
Trong finally
Sau cấu trúc
~~~

Ngoại lệ ở đây **đã được xử lý trong `catch`**. Vì thế, sau `finally`, luồng thực thi có thể tiếp tục bình thường. Điều này không có nghĩa `finally` đã xử lý ngoại lệ. Chính `catch` làm việc đó; `finally` chỉ thực hiện bước cuối khi rời cấu trúc.

Một `catch` khác cùng cấp không được chạy thêm chỉ vì `catch` thứ nhất đã kết thúc. Các `catch` là những nhánh lựa chọn để xử lý một ngoại lệ từ phạm vi `try`, không phải một chuỗi thực hiện tuần tự.

## 4. Khi `try` phát sinh ngoại lệ nhưng không có `catch` phù hợp

Nếu không có `catch` nào xử lý được ngoại lệ, **`finally` vẫn có cơ hội chạy trước khi ngoại lệ tiếp tục lan truyền** đến nơi gọi hoặc bộ xử lý bao ngoài.

~~~java
// Đoạn minh họa nằm trong phương thức không tự bắt IllegalStateException.
try {
    System.out.println("Trong try");
    throw new IllegalStateException("trạng thái sai");
} finally {
    System.out.println("Trong finally");
}
~~~

Khi thực hiện, chương trình in:

~~~text
Trong try
Trong finally
~~~

Sau đó, `IllegalStateException` vẫn đang được ném. Nếu phương thức gọi không bắt được, lỗi tiếp tục đi qua chuỗi lời gọi. Nếu không có bộ xử lý phù hợp, luồng có thể kết thúc bất thường và trình xử lý ngoại lệ chưa bắt có thể in stack trace ra stderr.

Trong trường hợp này, `finally` **không biến đường đi bất thường thành bình thường**. Nó chạy rồi cho phép nguyên nhân thoát ban đầu tiếp tục, miễn là bản thân `finally` hoàn tất bình thường.

Điều tương tự xảy ra khi `catch` được chọn nhưng **tự ném lại** ngoại lệ hoặc tạo ngoại lệ khác: `finally` được thực thi trên đường truyền ngoại lệ ra ngoài. Khác biệt là ngoại lệ cuối cùng được truyền có thể là lỗi gốc hoặc một ngoại lệ mới do code trong `catch` tạo ra.

## 5. Chương trình hoàn chỉnh: so sánh ba đường thực thi

Lưu chương trình sau vào `FinallyPathsDemo.java`:

~~~java
public class FinallyPathsDemo {
    static void run(String mode) {
        System.out.println("Bắt đầu: " + mode);
        try {
            System.out.println("Trong try");
            if (mode.equals("caught")) {
                throw new IllegalArgumentException("đầu vào sai");
            }
            if (mode.equals("uncaught")) {
                throw new IllegalStateException("trạng thái sai");
            }
            System.out.println("Try hoàn tất");
        } catch (IllegalArgumentException ex) {
            System.out.println("Catch: " + ex.getMessage());
        } finally {
            System.out.println("Finally: " + mode);
        }
        System.out.println("Sau try: " + mode);
    }

    public static void main(String[] args) {
        run("normal");
        run("caught");
        try {
            run("uncaught");
        } catch (IllegalStateException ex) {
            System.out.println("Catch ngoài: " + ex.getMessage());
        }
        System.out.println("Kết thúc main");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 FinallyPathsDemo.java
java FinallyPathsDemo
~~~

Stdout chính xác:

~~~text
Bắt đầu: normal
Trong try
Try hoàn tất
Finally: normal
Sau try: normal
Bắt đầu: caught
Trong try
Catch: đầu vào sai
Finally: caught
Sau try: caught
Bắt đầu: uncaught
Trong try
Finally: uncaught
Catch ngoài: trạng thái sai
Kết thúc main
~~~

**Phân tích từng lượt:**

- **`normal`:** không có ngoại lệ. `try` hoàn tất, `finally` chạy, sau đó dòng `Sau try: normal` chạy.
- **`caught`:** `IllegalArgumentException` phát sinh rồi được `catch` cùng cấu trúc xử lý. `finally` chạy sau handler, và dòng `Sau try: caught` vẫn được in.
- **`uncaught`:** `IllegalStateException` không khớp `catch (IllegalArgumentException)`. `finally` vẫn chạy, rồi lỗi truyền lên `catch (IllegalStateException)` của `main`. Dòng `Sau try: uncaught` **không chạy**, vì phương thức `run` đã kết thúc bất thường.

Đây là minh họa cụ thể cho sự khác biệt giữa **có chạy `finally`** và **có tiếp tục sau cấu trúc `try` hay không**. Hai kết quả đó phải xét riêng.

## 6. Bảng diễn tiến luồng điều khiển

| Trường hợp | `catch` cùng cấu trúc | `finally` | Sau cấu trúc `try` |
| --- | --- | --- | --- |
| Phần `try` chạy hết bình thường | Không chạy | Chạy | Chạy nếu `finally` hoàn tất bình thường |
| `try` ném ngoại lệ, `catch` phù hợp xử lý xong | Chạy | Chạy | Chạy nếu `catch` và `finally` hoàn tất bình thường |
| `try` ném ngoại lệ, không có `catch` phù hợp | Không xử lý lỗi đó | Chạy trên đường thoát | Không chạy trong cùng đường thực thi nếu ngoại lệ vẫn lan truyền |
| `catch` ném lại hoặc ném ngoại lệ khác | Nhánh được chọn kết thúc bất thường | Chạy trước khi thoát | Không chạy nếu ngoại lệ vẫn lan truyền |
| `try` hoặc `catch` thực hiện `return` | Tùy đường đi | Chạy trước khi trả về | Không chạy trong phương thức đó nếu `return` vẫn có hiệu lực |
| Chính `finally` ném hoặc `return` | Tùy đường đi | Kết thúc bất thường | Kết quả đang chờ có thể bị thay thế |

Bảng giả định mã thật sự đi đến điểm rời cấu trúc và môi trường thực thi cho phép các bước Java tiếp tục. Trường hợp chấm dứt JVM cưỡng bức, luồng không bao giờ rời vòng lặp hoặc lỗi máy nghiêm trọng được bàn ở phần giới hạn.

## 7. `finally` còn chạy khi `try` hoặc `catch` có `return`

Một trường hợp dễ nhầm là `return` không phải ngoại lệ, nhưng vẫn là **nguyên nhân hoàn tất bất thường của câu lệnh `try` theo thuật ngữ JLS**: quyền điều khiển chuẩn bị rời phương thức. Trước khi việc trả về có hiệu lực, Java thực hiện khối `finally`.

Ví dụ:

~~~java
// Đoạn minh họa đặt trong một lớp.
static int ten() {
    try {
        return 10;
    } finally {
        System.out.println("Finally trước return");
    }
}
~~~

Nếu in `ten()`, thứ tự sẽ là:

~~~text
Finally trước return
10
~~~

Với `return expression;`, Java **đánh giá biểu thức trả về trước khi chạy `finally`**. Nếu `finally` hoàn tất bình thường, giá trị đã được tính sẽ được trả về. Điều này đặc biệt quan trọng khi `finally` sửa một **biến cục bộ** sau khi giá trị primitive đã được chuẩn bị trả về.

### Ví dụ Java hoàn chỉnh với `return`

Tệp `FinallyReturnDemo.java`:

~~~java
public class FinallyReturnDemo {
    static int compute() {
        int value = 10;
        try {
            System.out.println("Try chuẩn bị return");
            return value;
        } finally {
            value = 20;
            System.out.println("Finally đổi local thành " + value);
        }
    }

    static int catchAndReturn() {
        try {
            throw new IllegalArgumentException("lỗi");
        } catch (IllegalArgumentException ex) {
            System.out.println("Catch chuẩn bị return");
            return 3;
        } finally {
            System.out.println("Finally chạy sau catch");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + compute());
        System.out.println("Kết quả catch: " + catchAndReturn());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
~~~

Stdout:

~~~text
Try chuẩn bị return
Finally đổi local thành 20
Kết quả: 10
Catch chuẩn bị return
Finally chạy sau catch
Kết quả catch: 3
~~~

Lý do `compute()` trả về `10` là biểu thức `return value` được đánh giá **trước** khi `finally` sửa biến `value` thành `20`. `finally` không tự đánh giá lại biểu thức trả về.

Lưu ý: đối với **kiểu tham chiếu**, giá trị trả về là tham chiếu đã tính. Nếu `finally` thay đổi trạng thái của **chính đối tượng** được tham chiếu, người gọi có thể quan sát thay đổi đó; nhưng việc gán biến cục bộ sang một tham chiếu khác trong `finally` không tự đổi tham chiếu đã được chọn để trả về.

Phương thức `catchAndReturn()` cho thấy một `return` trong `catch` cũng đi qua `finally` trước khi kết thúc phương thức.

## 8. Khi `finally` cũng phát sinh ngoại lệ: nguy cơ che lỗi gốc

Giả sử phần `try` ném lỗi A, nhưng trong quá trình dọn dẹp, `finally` lại ném lỗi B:

~~~java
// Đoạn minh họa một tình huống nguy hiểm.
try {
    throw new IllegalStateException("lỗi A");
} finally {
    throw new IllegalArgumentException("lỗi B");
}
~~~

Trong đường đi này, lỗi B từ `finally` **thay thế nguyên nhân thoát đang chờ** là lỗi A. Nếu bộ xử lý phía ngoài bắt một `RuntimeException`, nó thấy `IllegalArgumentException("lỗi B")`. Java không tự động nối lỗi A làm `cause` hoặc `suppressed` của lỗi B đối với `finally` thủ công.

Cũng vậy, `return` trong `finally` có thể **che cả ngoại lệ đang lan truyền**. Đó là lý do không nên viết `return` hoặc `throw` tùy tiện trong `finally`.

### Chương trình kiểm chứng hành vi che lỗi

Tệp `FinallyOverridesDemo.java`:

~~~java
public class FinallyOverridesDemo {
    static int unsafe() {
        try {
            throw new IllegalStateException("lỗi gốc");
        } finally {
            return 99;
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + unsafe());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FinallyOverridesDemo.java
java FinallyOverridesDemo
~~~

Stdout chính xác:

~~~text
Kết quả: 99
~~~

Đây là ví dụ **cố ý minh họa cách viết không an toàn**. Ngoại lệ `IllegalStateException` bị bỏ qua khỏi đường lỗi ra ngoài vì `finally` kết thúc bằng `return 99`. Trong ứng dụng thật, cách này có thể làm một sự cố nghiêm trọng trông như một lượt thực thi thành công.

Đặc biệt với cleanup thủ công:

~~~java
// Đoạn minh họa có close() có thể ném IOException.
try {
    doWork();
} finally {
    resource.close();
}
~~~

Nếu cả `doWork()` và `resource.close()` cùng ném ngoại lệ, lỗi đóng tài nguyên có thể che lỗi từ `doWork()`. Khi quản lý `AutoCloseable`, ưu tiên **`try-with-resources`** để có cơ chế suppressed exception thay vì tự viết cleanup thiếu kiểm soát.

## 9. `finally` và `try-with-resources`: thời điểm và bảo toàn lỗi

Cú pháp `try-with-resources`:

~~~java
// Đoạn minh họa dùng đối tượng AutoCloseable do openResource() trả về.
try (Resource resource = openResource()) {
    work(resource);
} catch (IOException ex) {
    handle(ex);
} finally {
    afterWork();
}
~~~

Đoạn trên cần các khai báo `Resource`, `openResource`, `work`, `handle`, `afterWork` và import phù hợp. Với `try-with-resources`, Java tự đóng tài nguyên đã khởi tạo thành công khi rời phần thân `try`, theo thứ tự **ngược** với thứ tự khởi tạo thành công.

Trong cấu trúc trên, việc đóng tài nguyên diễn ra **trước khi** `catch` hoặc `finally` đi kèm của chính cấu trúc đó chạy. Vì vậy handler có thể nhận một ngoại lệ phát sinh từ body hoặc từ việc đóng tài nguyên.

Khi thân `try` ném ngoại lệ chính và `close()` cũng ném, ngoại lệ đóng thường được thêm vào danh sách **suppressed exceptions** của ngoại lệ chính. Xem `ex.getSuppressed()` nếu cần chẩn đoán nhiều lỗi cùng lúc.

| Cơ chế | Lỗi từ phần thân và lỗi đóng tài nguyên |
| --- | --- |
| `try` + `finally { resource.close(); }` viết thủ công | Lỗi `close()` có thể thay thế lỗi gốc nếu chính `finally` ném |
| `try-with-resources` | Lỗi `close()` thường được gắn làm suppressed của lỗi chính |
| `catch` bọc lỗi bằng `new ...(..., cause)` | Lỗi gốc được lưu như **cause**, khác với suppressed |

`try-with-resources` phù hợp cho tài nguyên `AutoCloseable` như stream, reader hoặc kết nối. `finally` vẫn hữu ích cho thao tác kết thúc khác, ví dụ khôi phục trạng thái hoặc ghi nhận thời gian hoàn tất, nhưng nên giữ phần thân gọn và hạn chế các thao tác có thể thất bại khi một lỗi khác đang truyền ra.

Không nên tự đóng tài nguyên hai lần nếu đã để `try-with-resources` chịu trách nhiệm; đóng lặp có thể thừa hoặc gây hệ quả tùy loại tài nguyên.

## 10. `finally` chạy sau `catch`, kể cả khi `catch` ném tiếp

Ví dụ:

~~~java
// Đoạn minh họa nằm trong phương thức có thể ném IllegalStateException.
try {
    throw new IllegalArgumentException("đầu vào sai");
} catch (IllegalArgumentException ex) {
    System.out.println("Trong catch");
    throw new IllegalStateException("xử lý thất bại", ex);
} finally {
    System.out.println("Trong finally");
}
~~~

Stdout trước khi ngoại lệ mới tiếp tục truyền:

~~~text
Trong catch
Trong finally
~~~

Ở đây, `IllegalStateException` được tạo trong `catch`, lấy `IllegalArgumentException` làm nguyên nhân. Sau `finally` (nếu nó hoàn tất bình thường), ngoại lệ mới tiếp tục đến cấu trúc `try` bao ngoài hoặc phương thức gọi.

Các `catch` cùng cấp của chính cấu trúc này **không bắt ngoại lệ mới ném từ một `catch` khác**. Khi cần xử lý lỗi phát sinh trong handler, đặt một `try/catch` lồng trong handler hoặc một `try` thực sự bao quanh toàn bộ cấu trúc.

Điểm này củng cố hai chức năng riêng:

- `catch` chọn cách xử lý ngoại lệ phù hợp và có thể kết thúc bình thường hoặc ném tiếp.
- `finally` thực hiện bước cuối của cấu trúc bất kể nhánh `catch` được chọn đã hoàn tất theo cách nào, miễn quá trình thực thi còn tiếp tục tới bước đó.

## 11. Các khối `finally` lồng nhau chạy theo thứ tự nào?

Trong các cấu trúc `try` lồng nhau, một ngoại lệ phát sinh ở tầng sâu có thể đi qua nhiều `finally`. Về mặt luồng điều khiển, `finally` ở **cấu trúc bên trong** chạy trước, rồi tới các `finally` bao ngoài khi luồng tiếp tục rời từng cấu trúc.

~~~java
// Đoạn minh họa bên trong một phương thức.
try {
    try {
        System.out.println("Trong try trong");
        throw new IllegalStateException("lỗi");
    } finally {
        System.out.println("Finally trong");
    }
} catch (IllegalStateException ex) {
    System.out.println("Catch ngoài");
} finally {
    System.out.println("Finally ngoài");
}
~~~

Stdout:

~~~text
Trong try trong
Finally trong
Catch ngoài
Finally ngoài
~~~

Giải thích: ngoại lệ xuất hiện trong `try` bên trong, không có handler ở chính cấu trúc bên trong nên `finally` của nó chạy rồi lỗi được chuyển đến `catch` của tầng ngoài. Sau khi handler ngoài hoàn tất bình thường, `finally` ngoài thực thi.

Nếu một `finally` ở tầng sâu ném ngoại lệ mới, tầng ngoài có thể nhận ngoại lệ mới đó; điều này làm việc đọc stack trace và chuỗi nguyên nhân trở nên quan trọng hơn khi debug.

## 12. `finally` có được bảo đảm chạy trong mọi hoàn cảnh không?

**Không phải trong mọi hoàn cảnh tuyệt đối.** Theo ngữ nghĩa của Java, khi luồng điều khiển **rời một cấu trúc `try` theo các đường được đặc tả** (thành công, ngoại lệ, `return`, `break`, `continue`), `finally` liên quan được thực thi trước khi hoàn tất việc rời cấu trúc. Nhưng điều đó không đảm bảo `finally` luôn chạy dù chương trình hoặc môi trường đã ngừng thực thi.

Ví dụ về giới hạn:

- **`System.exit(...)` hoặc `Runtime.halt(...)`:** có thể làm JVM kết thúc mà không tiếp tục thực hiện các `finally` của những lời gọi đang hoạt động; `System.exit` thực hiện cơ chế shutdown, nhưng không quay lại unwinding các stack như khi `throw` thông thường.
- **Tiến trình bị kết thúc cưỡng bức, JVM bị crash, mất điện:** không thể trông cậy vào `finally` để hoàn tất một thao tác bên ngoài.
- **Luồng không bao giờ rời `try`** (chẳng hạn bị kẹt vô hạn): `finally` chưa có cơ hội chạy.
- **Lỗi cực kỳ nghiêm trọng của VM hoặc môi trường:** không thể luôn bảo đảm các bước cleanup tiếp tục.

Vì vậy, `finally` phù hợp cho cleanup **trong vòng đời thực thi Java bình thường**, nhưng không thay thế cơ chế lưu trữ bền vững, transaction hoặc thiết kế chịu lỗi khi cần đảm bảo hệ thống phục hồi sau crash.

Tránh nhầm với các lỗi runtime thông thường như `NullPointerException`: chúng vẫn là đối tượng `Throwable`; khi được ném và Java thực hiện đường thoát có thể xử lý, `finally` liên quan vẫn chạy.

## 13. `finally` trong vòng lặp với `break` và `continue`

Khi phần thân `try` được đặt trong vòng lặp, `break` hoặc `continue` có thể yêu cầu chuyển quyền điều khiển khỏi khối. Nếu đường chuyển này rời cấu trúc `try`, `finally` vẫn chạy trước khi vòng lặp thoát hoặc bắt đầu lượt tiếp theo.

~~~java
// Đoạn minh họa bên trong một phương thức.
for (int i = 0; i < 3; i++) {
    try {
        if (i == 1) {
            continue;
        }
        System.out.println("Try: " + i);
    } finally {
        System.out.println("Finally: " + i);
    }
}
~~~

Stdout:

~~~text
Try: 0
Finally: 0
Finally: 1
Try: 2
Finally: 2
~~~

Ở `i == 1`, câu `continue` bỏ qua phần in của `try`, nhưng `finally` vẫn được thực hiện trước khi chuyển sang lượt `i == 2`. Với `break`, `finally` cũng sẽ chạy trước khi rời vòng lặp.

Đây là lý do khi đọc code có `return`, `break`, `continue` hoặc `throw`, cần tính cả tác động của `finally` trước khi quyết định câu lệnh tiếp theo nào thật sự chạy.

## 14. Lỗi phổ biến khi sử dụng `finally`

| Hiểu nhầm hoặc lỗi thiết kế | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `finally` chỉ chạy khi có lỗi | Bỏ sót công việc cuối trên đường thành công | Hiểu rằng `finally` chạy khi rời `try` cả bình thường lẫn bất thường |
| Nghĩ `finally` tự bắt ngoại lệ chưa xử lý | Ngoại lệ vẫn lan ra ngoài sau `finally` | Dùng `catch` phù hợp ở nơi có thể xử lý |
| Nghĩ các câu lệnh sau `throw` trong `try` vẫn chạy trước `finally` | Đọc sai luồng điều khiển | Đi từ điểm ném tới handler/`finally`, bỏ qua đường bình thường còn lại |
| Đặt `return` trong `finally` | Có thể thay thế `return` hoặc che ngoại lệ từ `try`/`catch` | Tránh `return` trong `finally` |
| Thực hiện cleanup dễ ném lỗi trong `finally` thủ công | Có thể che lỗi ban đầu | Ưu tiên `try-with-resources` hoặc xử lý lỗi cleanup có chủ đích |
| Nghĩ thay đổi biến cục bộ trong `finally` sẽ làm `return value` trả giá trị mới | `return` đã đánh giá biểu thức trước đó | Xác định giá trị chờ trả và phân biệt kiểu primitive/tham chiếu |
| Bỏ qua `finally` của các `try` lồng nhau | Đoán sai thứ tự log/dọn dẹp | Theo dõi thứ tự rời khối từ trong ra ngoài |
| Coi `finally` là nơi phù hợp để xử lý mọi ngoại lệ | Mất phân loại và cách phục hồi từng lỗi | Dùng `catch` cho xử lý, `finally` cho công việc cuối |
| Cho rằng `finally` chắc chắn chạy dù gọi `System.exit` | Có thể bỏ lỡ cleanup khi JVM kết thúc | Dùng cơ chế quản lý vòng đời phù hợp khi cần shutdown |
| Chỉ thử đường thành công | Không phát hiện lỗi cleanup hoặc ngoại lệ bị che | Kiểm thử cả thành công, caught, uncaught và lỗi phát sinh trong cleanup |

Nên giữ công việc trong `finally` **ngắn, dễ dự đoán và ít khả năng thất bại**. Nếu nghiệp vụ cần rollback thực sự hoặc tính nguyên tử của dữ liệu, hãy dùng transaction hoặc một cơ chế phù hợp; `finally` chỉ kiểm soát luồng điều khiển Java.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `try` chạy thành công đến hết. `finally` có chạy không?

**Trả lời:** Có, nếu luồng điều khiển rời cấu trúc bình thường và môi trường tiếp tục thực thi.

**Câu 2.** `try` ném `IllegalArgumentException`, `catch` phù hợp xử lý xong. Thứ tự là gì?

**Trả lời:** Điểm ném trong `try` → `catch` phù hợp → `finally` → câu lệnh sau toàn bộ cấu trúc (nếu `finally` hoàn tất bình thường).

**Câu 3.** `try` ném `IllegalStateException` nhưng không có `catch` phù hợp. `finally` có làm lỗi biến mất không?

**Trả lời:** Không. `finally` chạy trước khi lỗi tiếp tục lan ra ngoài, miễn `finally` hoàn tất bình thường.

**Câu 4.** `return 10;` trong `try`, sau đó `finally` gán biến cục bộ ban đầu thành `20`. Giá trị trả về là gì?

**Trả lời:** Nếu biểu thức `return` đã được tính là `10` và `finally` hoàn tất bình thường, kết quả là `10`. Với đối tượng tham chiếu cần phân biệt việc thay đổi chính đối tượng.

**Câu 5.** Nếu `finally` có `return 99;` trong lúc `try` ném ngoại lệ, điều gì có thể xảy ra?

**Trả lời:** `return 99` có thể thay thế nguyên nhân thoát từ `try`, làm ngoại lệ bị che.

**Câu 6.** Nếu `finally` ném IOException trong khi `try` đang ném lỗi khác, lỗi nào có thể truyền ra?

**Trả lời:** Ngoại lệ từ `finally` có thể thay thế lỗi trước đó khi sử dụng cleanup thủ công. Nếu được quản lý bằng `try-with-resources`, lỗi đóng tài nguyên có cơ chế suppressed exception.

**Câu 7.** `finally` của `try` lồng nhau chạy trước hay sau `finally` ngoài?

**Trả lời:** Theo thứ tự rời cấu trúc, `finally` của tầng trong thường chạy trước tầng ngoài.

**Câu 8.** `continue` trong `try` có bỏ qua `finally` không?

**Trả lời:** Không, `finally` liên quan chạy trước khi chuyển sang lượt lặp tiếp theo, nếu việc chuyển đó rời cấu trúc.

**Câu 9.** Có nên dùng `finally` để đóng mọi tài nguyên `AutoCloseable` bằng tay không?

**Trả lời:** Thường nên ưu tiên `try-with-resources` vì nó quản lý việc đóng và giúp bảo toàn lỗi đóng qua suppressed exceptions.

**Câu 10.** `finally` có chắc chắn chạy sau `System.exit(0)` không?

**Trả lời:** Không; không nên phụ thuộc vào `finally` để cleanup khi JVM bị kết thúc.

## Tài liệu đối chiếu

- [Java Language Specification 17, §14.20.2 — Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): quy tắc `finally` khi `try` hoàn tất bình thường hoặc bất thường.
- [Java Language Specification 17, §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): đóng tài nguyên, suppressed exceptions và thứ tự thực thi.
- [Java Language Specification 17, §14.17 — The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): đánh giá biểu thức `return` trước khi rời phương thức.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()` và stack trace.
- [Oracle Java Tutorials — The finally Block](https://docs.oracle.com/javase/tutorial/essential/exceptions/finally.html): giải thích trực quan về cleanup (ví dụ trong tutorial lịch sử, quy tắc nền tảng vẫn áp dụng).

**Ghi nhớ:** khi `try` hoàn tất bình thường, `finally` chạy trước khi chương trình đi tiếp; khi `try` ném ngoại lệ, `finally` chạy trên đường xử lý hoặc lan truyền lỗi. Nếu chính `finally` kết thúc bất thường, nó có thể thay đổi toàn bộ kết quả. Vì vậy hãy dùng `catch` để xử lý ngoại lệ, `finally` cho công việc cuối, và `try-with-resources` để quản lý tài nguyên `AutoCloseable` khi phù hợp.
