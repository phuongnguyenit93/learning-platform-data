# Ngoại lệ phát sinh ngay trong khối `catch` của Java

Khi một khối `catch` đang xử lý ngoại lệ, **chính các câu lệnh bên trong `catch` vẫn có thể phát sinh ngoại lệ khác**. Lỗi có thể xuất hiện do gọi một API I/O, truy cập tham chiếu `null`, chuyển đổi dữ liệu sai, thao tác ghi log, thực hiện phương án khôi phục thất bại hoặc do lập trình viên chủ động `throw` một ngoại lệ mới.

Điểm quan trọng nhất: **ngoại lệ mới được ném bên trong một `catch` không được xử lý bởi các khối `catch` cùng cấp của chính cấu trúc `try` đó**. Nó được truyền ra ngoài, sau khi thực hiện `finally` liên quan (nếu có), để tìm một bộ xử lý phù hợp ở ngữ cảnh bao ngoài hoặc các lời gọi phía trên. Nếu muốn xử lý ngay lỗi mới, cần một `try/catch` lồng bên trong khối `catch`.

Bài học này phân biệt ngoại lệ gốc, ngoại lệ phát sinh trong handler, việc ném lại, bọc nguyên nhân và tương tác với `finally`; đồng thời hướng dẫn tránh việc một lỗi phụ che mất sự cố ban đầu. Các chương trình hoàn chỉnh chạy với JDK 17 trở lên.

## 1. Một `try` có nhiều `catch` hoạt động như thế nào?

Một cấu trúc thường gặp:

~~~java
try {
    // Thao tác có thể phát sinh lỗi.
} catch (IllegalArgumentException ex) {
    // Xử lý IllegalArgumentException.
} catch (IllegalStateException ex) {
    // Xử lý IllegalStateException phát sinh ở khối try.
} finally {
    // Dọn dẹp cần thiết.
}
~~~

Khi ngoại lệ phát sinh **trong phần thân `try`**, Java tìm `catch` tương thích đầu tiên trong danh sách. Nếu `catch` được chọn chạy xong bình thường, những `catch` còn lại **không chạy tiếp** như các nhánh `if`.

Nếu chính câu lệnh ở nhánh `catch (IllegalArgumentException)` ném `IllegalStateException`, nhánh `catch (IllegalStateException)` nằm bên cạnh **không bắt lỗi mới đó**, vì phạm vi mà cả hai handler bảo vệ là **phần `try` tương ứng**, không phải phần thân của một handler khác.

Đây là điểm dễ nhầm nhất khi đọc một cấu trúc có nhiều `catch`: **các `catch` ngang hàng là những lựa chọn xử lý lỗi của cùng một khối `try`**, không phải một chuỗi tầng bảo vệ lẫn nhau.

Mô hình:

~~~text
try bên trong
    |
    | ném IllegalArgumentException
    v
catch (IllegalArgumentException)  <-- được chọn
    |
    | xử lý lỗi nhưng ném IllegalStateException mới
    v
finally của try bên trong (nếu có)
    |
    v
thoát khỏi toàn bộ try/catch/finally bên trong
    |
    +--> catch của try bao ngoài (nếu tương thích)
    |
    +--> hoặc tiếp tục lan truyền lên phương thức gọi

catch (IllegalStateException) cùng cấp: KHÔNG được chọn cho lỗi từ sibling catch
~~~

Việc tìm handler phụ thuộc vào **phạm vi động của `try` đang bao quanh điểm ném** và kiểu đối tượng `Throwable`. Một `catch` không tự tạo ra một `try` ẩn bảo vệ phần thân của nó.

## 2. Ví dụ Java hoàn chỉnh: ngoại lệ mới từ `catch` đi ra `catch` bao ngoài

Lưu thành tệp `CatchThrowsDemo.java`:

~~~java
public class CatchThrowsDemo {
    static void execute() {
        try {
            try {
                System.out.println("1. Trong try");
                throw new IllegalArgumentException("đầu vào lỗi");
            } catch (IllegalArgumentException original) {
                System.out.println("2. Catch đầu: " + original.getMessage());
                throw new IllegalStateException("khôi phục thất bại", original);
            } catch (IllegalStateException sibling) {
                System.out.println("Không chạy: sibling catch");
            } finally {
                System.out.println("3. Finally bên trong");
            }
        } catch (IllegalStateException ex) {
            System.out.println("4. Catch ngoài: " + ex.getMessage());
            System.out.println("5. Nguyên nhân: " + ex.getCause().getMessage());
        }
        System.out.println("6. Tiếp tục");
    }

    public static void main(String[] args) {
        execute();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CatchThrowsDemo.java
java CatchThrowsDemo
~~~

**Stdout chính xác:**

~~~text
1. Trong try
2. Catch đầu: đầu vào lỗi
3. Finally bên trong
4. Catch ngoài: khôi phục thất bại
5. Nguyên nhân: đầu vào lỗi
6. Tiếp tục
~~~

Giải thích thứ tự:

1. Khối `try` trong cùng ném `IllegalArgumentException`. Java chọn nhánh `catch (IllegalArgumentException original)`.
2. Nhánh này in dòng 2, sau đó tạo và ném `IllegalStateException`. Constructor nhận tham số `original` để giữ ngoại lệ gốc làm nguyên nhân.
3. Nhánh `catch (IllegalStateException sibling)` của **cùng cấu trúc** không được dùng để xử lý ngoại lệ từ nhánh trước, nên câu `Không chạy: sibling catch` không bao giờ được in trong lượt này.
4. Trước khi thoát cấu trúc bên trong, `finally` in dòng 3. Nó kết thúc bình thường nên ngoại lệ mới tiếp tục truyền ra.
5. `catch (IllegalStateException ex)` của cấu trúc `try` bao ngoài được chọn. `ex.getCause()` trả về ngoại lệ `IllegalArgumentException` ban đầu.
6. `catch` ngoài hoàn thành bình thường và phương thức tiếp tục in dòng 6.

Hai quan sát cần nhớ: **nhánh sibling không xử lý lỗi từ handler**, và **`finally` nằm trên đường truyền ra ngoài**. Việc dùng constructor `(message, cause)` bảo toàn khả năng truy vết lỗi ban đầu; nó không tự động xảy ra nếu bạn ném một ngoại lệ mới mà không truyền nguyên nhân.

## 3. Bốn tình huống khi xử lý lỗi trong `catch`

Giả sử một thao tác đã ném `original`, rồi chương trình đang ở trong `catch`.

| Hành vi bên trong `catch` | Kết quả chính |
| --- | --- |
| Xử lý hợp lệ và kết thúc bình thường | Lỗi đã được xử lý; luồng có thể tiếp tục sau cấu trúc `try/catch/finally`. |
| `throw original;` | Ném lại **cùng đối tượng** ngoại lệ; tiếp tục lan truyền ra bên ngoài. |
| `throw new IllegalStateException("...", original);` | Tạo ngoại lệ khác và giữ `original` làm `cause`; bên ngoài nhận ngoại lệ mới. |
| Một thao tác bên trong `catch` tự phát sinh ngoại lệ, ví dụ `logger.write(...)` hay `nullValue.length()` | Ngoại lệ từ thao tác đó bắt đầu truyền ra ngoài; lỗi gốc có thể bị che nếu không được lưu làm nguyên nhân hoặc suppressed exception. |

Một khối `catch` cũng có thể `return`, `break` hoặc `continue` trong những ngữ cảnh hợp lệ; như các đường thoát khác, `finally` có thể tác động đến kết quả. Chủ đề này quan trọng khi chính `finally` ném lỗi, được giải thích ở phần 7.

**Khác biệt về đối tượng:**

~~~java
// Đoạn minh họa nằm trong một catch có biến original.
throw original;  // Cùng tham chiếu Throwable.
~~~

~~~java
// Đoạn minh họa nằm trong một catch có biến original.
throw new IllegalStateException("Không thể khôi phục", original);
// Một đối tượng mới, nguyên nhân nối tới đối tượng gốc.
~~~

~~~java
// Đoạn minh họa nằm trong một catch có biến original.
throw new IllegalStateException("Không thể khôi phục");
// Một đối tượng mới nhưng KHÔNG gắn nguyên nhân gốc.
~~~

Cách cuối hợp lệ nhưng có thể làm mất thông tin quan trọng. Chỉ chủ động bỏ `cause` khi có lý do thiết kế rõ ràng, chẳng hạn cần tránh tiết lộ dữ liệu nhạy cảm ở ranh giới công khai; thông thường nên giữ lỗi gốc trong hệ thống chẩn đoán nội bộ.

## 4. Ngoại lệ trong `catch` có thể là lỗi không chủ ý

Không phải mọi ngoại lệ bên trong handler đều do `throw new` tường minh. Các câu lệnh dùng để xử lý lỗi cũng có nguy cơ thất bại:

~~~java
// Đoạn minh họa: một lỗi phụ phát sinh trong catch.
try {
    Integer.parseInt("abc");
} catch (NumberFormatException original) {
    String message = null;
    System.out.println(message.length()); // Ném NullPointerException.
}
~~~

Trong ví dụ này, `NumberFormatException` gốc đã đưa luồng thực thi vào `catch`, nhưng dòng `message.length()` phát sinh `NullPointerException`. Nếu không có `try` khác bảo vệ câu lệnh này, ngoại lệ mới lan ra ngoài. Người theo dõi chỉ thấy `NullPointerException` ở tầng trên có thể nhầm đây là nguyên nhân chính, dù lỗi đầu tiên là chuyển đổi số.

Các nguồn lỗi phụ phổ biến:

- **Ghi log:** logger, formatter, phương thức `toString()` hoặc nơi gửi log có thể thất bại vì bug, tài nguyên hay I/O. Không nên tự xây thông báo lỗi bằng nhiều thao tác dễ phát sinh lỗi khác.
- **Dùng đối tượng lỗi:** gọi `ex.getCause().getMessage()` khi `getCause()` là `null` gây `NullPointerException`. Không được mặc định mọi `Throwable` đều có cause.
- **Khôi phục:** đọc bản sao dự phòng, gọi dịch vụ khác hoặc rollback có thể phát sinh exception.
- **Dọn dẹp thủ công:** đóng stream, giải phóng tài nguyên, lưu audit hoặc gọi `close()` trong handler có thể thất bại.
- **Chuyển đổi dữ liệu để hiển thị lỗi:** phân tích JSON, lấy thông điệp ngoại lệ từ hệ thống ngoài, mã hóa lại dữ liệu hoặc định dạng chuỗi có thể gây lỗi mới.

Trong thiết kế, **logic xử lý lỗi phải đủ đơn giản và có đường thất bại được tính trước**. Nếu một thao tác phụ không được phép che lỗi chính, hãy bảo vệ riêng thao tác đó và giữ lại ngoại lệ gốc để chuyển tiếp.

## 5. Dùng `try/catch` lồng bên trong chính `catch`

Bạn có thể xử lý lỗi phụ ngay tại `catch` bằng cách tạo cấu trúc `try` mới trong phần thân của handler. Khi đó handler bên trong mới có thể bắt ngoại lệ phát sinh từ thao tác phụ.

~~~java
// Mã minh họa nằm trong phương thức có throws IOException phù hợp,
// cùng với hàm audit(Throwable) throws IOException.
try {
    performAction();
} catch (IllegalArgumentException original) {
    try {
        audit(original);
    } catch (IOException auditFailure) {
        original.addSuppressed(auditFailure);
    }
    throw original;
}
~~~

Đây là **đoạn minh họa phụ thuộc các phương thức `performAction`, `audit`**. Ý nghĩa của nó:

1. Ngoại lệ ban đầu `IllegalArgumentException` đã được bắt bởi handler ngoài.
2. `audit(original)` là một thao tác riêng có thể lỗi I/O.
3. `catch (IOException auditFailure)` **nằm trong cấu trúc `try` mới** nên bắt được lỗi audit tại nơi xảy ra.
4. `addSuppressed` gắn lỗi phụ vào `original`, cho phép xem qua `getSuppressed()` nếu đối tượng hỗ trợ suppression.
5. `throw original` giữ nguyên ngoại lệ chính khi tiếp tục truyền ra ngoài.

`addSuppressed` chỉ phù hợp khi bạn muốn duy trì lỗi chính và xem lỗi phụ là sự cố thứ cấp trong lúc xử lý. Không tự thêm chính đối tượng `original` làm suppressed của nó; Java cấm self-suppression. Ngoài ra, lưu ý có thể có các loại `Throwable` tùy chỉnh không bật suppression.

Với thao tác phục hồi có ý nghĩa độc lập, một lựa chọn khác là ném ngoại lệ mới, **kèm `cause` từ lỗi gốc**, để thông báo rõ thất bại ở bước phục hồi. Cách nào đúng phụ thuộc ranh giới trách nhiệm và loại lỗi mà API muốn người gọi xử lý.

## 6. Checked exception được ném từ `catch`: compiler kiểm tra như thế nào?

Trình biên dịch Java kiểm tra các ngoại lệ **checked** có thể thoát khỏi phần thân `catch`, giống như đối với những câu lệnh khác. Nếu handler ném `IOException`, bạn phải bắt ở một cấu trúc `try` phù hợp bao ngoài hoặc khai báo trong `throws` của phương thức/constructor chứa nó.

Chương trình hoàn chỉnh `CheckedCatchThrowsDemo.java`:

~~~java
import java.io.IOException;

public class CheckedCatchThrowsDemo {
    static void convert(String raw) throws IOException {
        try {
            Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IOException("không chuyển đổi được", ex);
        }
    }

    public static void main(String[] args) {
        try {
            convert("abc");
        } catch (IOException ex) {
            System.out.println("Đã xử lý: " + ex.getMessage());
            System.out.println("Cause: " + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CheckedCatchThrowsDemo.java
java CheckedCatchThrowsDemo
~~~

Đầu ra chính xác:

~~~text
Đã xử lý: không chuyển đổi được
Cause: NumberFormatException
~~~

Phân tích:

- `Integer.parseInt("abc")` ném `NumberFormatException`, một unchecked exception.
- `catch (NumberFormatException ex)` bắt lỗi đó, rồi tạo và ném `IOException` **checked** mới.
- Vì `IOException` thoát khỏi phương thức `convert`, chữ ký phải khai báo `throws IOException`, hoặc phải có xử lý phù hợp ở tầng bao ngoài.
- `main` bắt `IOException`, đọc `getCause()` để thấy `NumberFormatException` gốc. Không có nghĩa vụ bắt `NumberFormatException` chỉ vì nó là cause.

Nếu bỏ `throws IOException` khỏi chữ ký `convert` mà không thêm handler phù hợp, chương trình sẽ lỗi biên dịch. Không thể giải quyết bằng cách viết một `catch (IOException)` **ngang hàng bên dưới** `catch (NumberFormatException)`: lỗi I/O được tạo trong handler nên không thuộc khối `try` do `catch` ngang hàng bảo vệ.

Cách hợp lệ khác là đặt toàn bộ `try/catch` bên trong một `try` bao ngoài, rồi `catch (IOException)` ở tầng ngoài. Khi đó ngoại lệ đã phát sinh **bên trong một khối `try` thực sự** thuộc tầng ngoài.

## 7. Vai trò của `finally` khi `catch` ném thêm ngoại lệ

`finally` liên quan đến cấu trúc `try/catch` vẫn được chạy khi khối `catch` kết thúc bất thường do `throw`.

Có hai tình huống khác nhau:

- **`finally` hoàn thành bình thường:** ngoại lệ đã được ném từ `catch` tiếp tục lan truyền ra ngoài.
- **`finally` tự kết thúc bất thường** (ví dụ ném thêm exception hoặc thực hiện `return`): lý do thoát ra của `catch` có thể bị thay thế, làm lỗi vừa ném từ `catch` không còn là ngoại lệ ngoài cùng.

Chương trình `FinallyMasksCatchDemo.java` chứng minh tình huống thứ hai:

~~~java
public class FinallyMasksCatchDemo {
    static void process() {
        try {
            try {
                throw new IllegalArgumentException("lỗi gốc");
            } catch (IllegalArgumentException ex) {
                throw new IllegalStateException("lỗi từ catch", ex);
            } finally {
                throw new UnsupportedOperationException("lỗi từ finally");
            }
        } catch (RuntimeException ex) {
            System.out.println("Bên ngoài: " + ex.getMessage());
            System.out.println("Cause null: " + (ex.getCause() == null));
        }
    }

    public static void main(String[] args) {
        process();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FinallyMasksCatchDemo.java
java FinallyMasksCatchDemo
~~~

Stdout chính xác:

~~~text
Bên ngoài: lỗi từ finally
Cause null: true
~~~

Diễn giải: `IllegalArgumentException("lỗi gốc")` đưa luồng vào `catch`; handler tạo `IllegalStateException("lỗi từ catch", ex)`. Nhưng `finally` lại ném `UnsupportedOperationException`. Trong ví dụ này, lỗi cuối được `catch` ngoài nhận là lỗi từ `finally`; nó không được tạo với `cause`, nên `getCause() == null`. Hai lỗi trước bị che khỏi chuỗi nguyên nhân ngoài cùng.

**Không nên dùng mẫu này trong mã thực tế.** Mục tiêu chỉ là quan sát quy tắc thứ tự thoát. Tránh `throw` hoặc `return` tùy tiện trong `finally`. Nếu công việc dọn dẹp có thể lỗi, hãy dùng cơ chế quản lý tài nguyên hoặc xử lý riêng để giữ lại lỗi chính.

Trường hợp `finally` chứa lệnh `return` cũng có thể che ngoại lệ đang truyền. Do đó `return` trong `finally` là một lỗi thiết kế thường gặp, kể cả khi không có `throw` rõ ràng ở đó.

## 8. `try-with-resources` khác gì với ngoại lệ phát sinh trong `catch`?

`try-with-resources` dùng cho các tài nguyên `AutoCloseable` và xử lý đặc biệt lỗi khi đóng tài nguyên. Nếu cả **thân `try`** và **`close()`** cùng ném ngoại lệ trong quá trình rời `try`, lỗi đóng thường được thêm vào `getSuppressed()` của ngoại lệ chính, giúp giữ lại dấu vết cả hai.

Tuy nhiên, với một cấu trúc như:

~~~java
// Đoạn minh họa có khai báo Resource và ErrorType phù hợp.
try (Resource resource = openResource()) {
    doWork(resource);
} catch (ErrorType original) {
    throw new IllegalStateException("Xử lý lỗi cũng thất bại", original);
}
~~~

Tài nguyên trong `try-with-resources` đã được đóng theo các quy tắc của cấu trúc **trước khi phần `catch` tương ứng xử lý ngoại lệ**. Nếu câu lệnh trong `catch` tạo thêm `IllegalStateException`, Java không tự động gắn `ErrorType original` thành suppressed của lỗi mới; ở đây programmer giữ nguyên nhân bằng tham số `original` trong constructor.

Vì thế cần phân biệt:

- **Suppressed do cơ chế đóng tài nguyên:** thể hiện các lỗi thứ cấp được ghi khi tài nguyên đóng trong `try-with-resources`.
- **`Cause` do code chủ động bọc lỗi:** biểu thị một ngoại lệ là nguyên nhân dẫn tới ngoại lệ khác, ví dụ `new IllegalStateException("...", original)`.
- **Ngoại lệ do handler vô tình ném:** có thể che nguyên nhân gốc nếu không được thiết kế đường xử lý cẩn thận.

`Throwable.getCause()` và `Throwable.getSuppressed()` phục vụ hai mục đích khác nhau. Khi debug một luồng lỗi phức tạp, cần kiểm tra cả hai.

## 9. Ném lại cùng ngoại lệ và giữ stack trace

Một nhánh `catch` có thể ném lại đối tượng đang được bắt:

~~~java
// Đoạn minh họa bên trong phương thức có throws IOException.
try {
    readFromDisk();
} catch (IOException ex) {
    System.err.println("Không đọc được tài nguyên");
    throw ex;
}
~~~

`throw ex;` **không tạo đối tượng mới**, do đó về thông thường không chụp lại stack trace ở vị trí `throw ex`. Stack trace của `Throwable` thường được ghi nhận lúc đối tượng được tạo hoặc tại lần gọi `fillInStackTrace()`; nếu chỉ ném lại tham chiếu cũ thì dấu vết ban đầu vẫn có thể được bảo toàn.

Trong khi đó:

~~~java
// Đoạn minh họa có IOException ex ở catch.
throw new IllegalStateException("Lỗi đọc dữ liệu ứng dụng", ex);
~~~

là tạo ngoại lệ mới tại tầng xử lý; ngoại lệ mới có stack trace riêng, còn `ex` được giữ làm cause. Khi hiển thị đầy đủ stack trace, thường có chuỗi `Caused by:` để lần về lỗi nguồn.

Cần cân nhắc giữa hai cách:

- **`throw ex`:** giữ loại ngoại lệ và danh tính đối tượng; phù hợp khi tầng hiện tại chưa có cách phục hồi và chưa cần đổi hợp đồng.
- **Bọc kèm cause:** hữu ích khi tầng hiện tại muốn cung cấp ngữ cảnh cấp cao hoặc chuyển đổi loại lỗi. Không bọc nhiều tầng chỉ để lặp lại cùng một thông điệp.
- **Không ném lại:** chỉ phù hợp khi `catch` đã thật sự xử lý, có kết quả thay thế hợp lệ hoặc chủ động chuyển sang một đường lỗi khác với tài liệu rõ ràng.

Khi `ex` là checked exception, hãy tuân thủ các quy tắc compiler về ngoại lệ được ném lại và chữ ký `throws`. Java có phân tích **precise rethrow** trong một số dạng `catch`, nhưng điều đó không biến unchecked thành checked hoặc thay đổi ý nghĩa của `throw ex;`.

## 10. Các chiến lược giữ lỗi gốc khi handler cũng thất bại

Hãy đặt câu hỏi: **lỗi nào phản ánh thất bại chính mà caller cần biết?** Sau đó chọn cách truyền phù hợp.

### Trường hợp A: lỗi xử lý mới cần được công bố, lỗi gốc là nguyên nhân

~~~java
// Đoạn minh họa trong một catch có biến original.
throw new IllegalStateException("Không thể khôi phục trạng thái", original);
~~~

Người gọi nhận một ngoại lệ mới và có thể dùng `getCause()` để đi đến nguồn lỗi. Phù hợp nếu nỗ lực khôi phục là bước quyết định thất bại và tầng hiện tại có trách nhiệm cung cấp ngữ cảnh mới.

### Trường hợp B: lỗi gốc là chính, lỗi audit/cleanup chỉ là phụ

~~~java
// Đoạn minh họa trong một catch có biến original, auditingFailure.
original.addSuppressed(auditingFailure);
throw original;
~~~

Cách này giữ nguyên lỗi gốc và lưu lỗi phụ. Nên kiểm tra các quy định về self-suppression và về việc dùng suppressed exceptions của lớp `Throwable` cụ thể.

### Trường hợp C: xử lý hoàn tất thật sự

~~~java
// Đoạn minh họa trong một catch có fallback phù hợp.
String cached = readValidCachedValue();
return cached;
~~~

Khi một giá trị dự phòng đáng tin được tính thành công và hợp đồng cho phép, handler có thể hoàn thành bình thường. Nếu `readValidCachedValue()` lại ném ngoại lệ, nó vẫn cần được xử lý hoặc truyền tiếp; việc đặt lời gọi trong `catch` không miễn trừ nguy cơ lỗi.

### Trường hợp D: chỉ cần báo lỗi, không có thao tác dễ thất bại

~~~java
// Đoạn minh họa bên trong catch với biến ex.
System.err.println("Không hoàn thành thao tác: " + ex.getMessage());
throw ex;
~~~

Đây là cách diễn giải cơ bản. Trong hệ thống thực, logger có thể thất bại hoặc log trùng qua nhiều tầng; nên dùng logger được quản lý đúng cách và lựa chọn một ranh giới chịu trách nhiệm ghi log. Tránh giả định mọi công việc trong handler là tuyệt đối an toàn.

Không có chiến lược bắt buộc áp dụng cho mọi hệ thống. Điều quan trọng là giữ được **ngữ nghĩa lỗi, khả năng kiểm tra nguyên nhân và hành vi caller mong đợi**.

## 11. Lưu ý về `catch` nhiều nhánh và kiểu ngoại lệ

Mỗi `catch` được chọn dựa vào kiểu runtime của đối tượng ngoại lệ phát sinh **trong phần được bảo vệ**. Một số quy tắc cần nhớ:

1. `catch (RuntimeException ex)` bắt được `IllegalArgumentException`, `IllegalStateException` và các lớp con phù hợp; nhưng không bắt `Error`.
2. Khi có nhiều `catch`, đặt kiểu con trước kiểu cha; `catch (Exception)` đứng trước `catch (IOException)` sẽ làm nhánh sau không thể tới và gây lỗi biên dịch.
3. Multi-catch như `catch (IOException | SQLException ex)` dùng để bắt một trong hai loại **từ cùng phần `try`**. Nó không giúp bắt ngoại lệ mới xuất hiện trong chính phần thân multi-catch.
4. Có thể dùng `catch (Exception ex)` nhưng không nên sử dụng quá rộng rồi bỏ trống, vì có thể vô tình biến lỗi nghiêm trọng thành thành công giả.
5. Nếu nhánh `catch` ném một kiểu checked exception mới, compiler kiểm tra khả năng thoát theo kiểu đó; `catch` sibling không làm ngoại lệ mới tự được xử lý.

Đặc biệt, đoạn sau **không hoạt động theo cách nhiều người tưởng**:

~~~java
// Đoạn minh họa có perform() phù hợp với ví dụ.
try {
    perform();
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("Handler failed", ex);
} catch (IllegalStateException ex) {
    System.out.println("Không bắt được lỗi từ catch trước!");
}
~~~

Nếu `perform()` ném `IllegalArgumentException`, handler đầu được chọn và ném `IllegalStateException` mới. Handler thứ hai không bắt ngoại lệ mới đó. Nhưng nếu **chính `perform()` ném `IllegalStateException`**, handler thứ hai có thể được chọn bình thường. Cùng là `IllegalStateException`, song **điểm ném và phạm vi `try`** quyết định nhánh nào được sử dụng.

## 12. Kiểm tra thực tế khi một `catch` không hoạt động như mong đợi

Khi xem log hoặc debug một ngoại lệ xuất hiện trong handler:

1. Xác định **ngoại lệ gốc nào dẫn tới nhánh `catch` đầu tiên**. Quan sát kiểu, thông điệp và stack trace ban đầu.
2. Đọc từng câu lệnh trong phần thân handler, đặc biệt những lời gọi ghi log, truy cập `getCause()`, đọc dữ liệu dự phòng và cleanup.
3. Xác định **dòng ném ngoại lệ thứ hai** và kiểu thực tế của nó. Đừng tự giả định nó cùng kiểu với lỗi gốc.
4. Đánh dấu `try` nào **thực sự bao quanh dòng ném mới**. Những `catch` sibling của cấu trúc hiện tại không phải handler cho lỗi phát sinh bên trong `catch`.
5. Kiểm tra `finally`: nó chạy theo đường nào và có ném/return đè lỗi đang được truyền không?
6. Ở handler bao ngoài, kiểm tra `getCause()` và `getSuppressed()`; nếu đều trống, xem code có làm mất lỗi gốc khi tạo ngoại lệ mới không.
7. Chọn chỗ xử lý hoặc chuyển tiếp có chủ đích, viết bài kiểm thử mô phỏng cả **thất bại ban đầu** và **thất bại của logic xử lý**.

Ví dụ kiểm thử đáng làm: giả lập API chính ném `IOException`, sau đó giả lập audit cũng ném `IOException`. Hãy xác minh rõ **loại lỗi mà caller nhận**, **cause/suppressed** và **trạng thái còn lại của tài nguyên**. Một bài kiểm thử chỉ chạy nhánh thành công sẽ bỏ sót các lỗi được che trong handler.

## 13. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Viết `catch (B)` cùng cấp rồi mong bắt B ném từ `catch (A)` | B tiếp tục lan ra ngoài, handler cùng cấp không được chọn. | Đặt `try/catch` lồng ngay trong handler hoặc dùng `try` bao ngoài. |
| Bọc ngoại lệ mới mà không giữ `cause` | Dấu vết lỗi gốc dễ bị mất. | Dùng constructor `(message, cause)` hoặc cơ chế lưu lỗi phụ phù hợp. |
| Gọi `ex.getCause().getMessage()` vô điều kiện | Có thể phát sinh `NullPointerException` ngay khi xử lý lỗi. | Kiểm tra `getCause()` khác `null` trước khi dùng. |
| Dùng `return` hoặc `throw` trong `finally` | Có thể che ngoại lệ từ `try`/`catch`. | Để `finally` dọn dẹp và hoàn thành bình thường khi có thể. |
| Cho rằng `catch` được chọn đã bảo đảm xử lý hoàn tất | Handler vẫn có thể thất bại giữa chừng. | Thiết kế và kiểm thử đường lỗi của handler. |
| Thêm một ngoại lệ checked mới trong `catch` nhưng bỏ khai báo `throws` | Lỗi biên dịch về checked exception. | Bắt trong `try` lồng, bọc hợp lý hoặc khai báo lên tầng gọi. |
| Ghi log cùng lỗi ở mọi tầng, đồng thời ném lại | Log trùng lặp, khó xác định số sự cố thật. | Log ở ranh giới chịu trách nhiệm hoặc chỉ thêm ngữ cảnh khi chuyển tầng. |
| Nuốt lỗi phụ mà không ghi nhận khi nó ảnh hưởng kết quả | Khó chẩn đoán vì mất dấu vết quá trình khôi phục. | Giữ lỗi phụ trong suppressed, cause hoặc cơ chế giám sát phù hợp. |
| Coi `finally` và `try-with-resources` hoàn toàn tương đương | Sai khác về cách bảo toàn lỗi đóng tài nguyên. | Dùng `try-with-resources` cho `AutoCloseable` khi thích hợp. |
| Hiểu `throw ex` là tạo lại exception tại handler | Có thể đọc sai stack trace. | Phân biệt ném lại tham chiếu và `throw new` tạo đối tượng mới. |

## 14. Tự kiểm tra

1. **Một `try` có `catch (IllegalArgumentException)` rồi `catch (IllegalStateException)`. Nếu nhánh đầu ném `IllegalStateException`, nhánh thứ hai có bắt không?** — Không. Nó chỉ có thể bắt `IllegalStateException` phát sinh ở phạm vi `try` đang bảo vệ, không phải từ sibling catch.
2. **Muốn bắt lỗi audit ngay khi đang ở `catch` phải làm gì?** — Đặt một `try/catch` mới lồng trong handler để bao quanh lời gọi audit.
3. **`catch` ném `IOException` checked, còn phương thức không có `throws IOException` và không có handler bao ngoài. Chương trình biên dịch không?** — Không; phải bắt hoặc khai báo checked exception mới.
4. **`throw original;` có tạo đối tượng khác không?** — Không, vẫn là chính tham chiếu `original`.
5. **`throw new IllegalStateException("fail", original);` cho phép lần theo lỗi gốc như thế nào?** — Qua `getCause()` và phần `Caused by:` của stack trace.
6. **Nếu `finally` ném ngoại lệ khác trong lúc handler đang ném lỗi, ngoại lệ nào có thể ra ngoài?** — Ngoại lệ mới từ `finally` có thể thay thế ngoại lệ đang chờ truyền ra.
7. **`getSuppressed()` và `getCause()` giống nhau không?** — Không. Suppressed chứa các lỗi phụ được ghi nhận; cause mô tả quan hệ nguyên nhân của ngoại lệ.
8. **`catch` ghi log rồi bị `NullPointerException` trong formatter, lỗi gốc có tự trở thành cause không?** — Không. Nếu không được giữ bằng code, lỗi gốc có thể mất khỏi chuỗi nguyên nhân.
9. **Tại sao cần thử cả nhánh lỗi của handler?** — Vì tác vụ khôi phục, audit và dọn dẹp cũng có thể thất bại và thay đổi ngoại lệ mà caller nhận được.
10. **Sau khi `catch` ném ngoại lệ mới và `finally` hoàn thành bình thường, chương trình có thực hiện dòng ngay sau cấu trúc đó không?** — Không ở đường thực thi này nếu ngoại lệ vẫn chưa được xử lý; nó tiếp tục truyền tới bộ xử lý bao ngoài hoặc lời gọi phía trên.

## Tài liệu tham khảo

- [Java Language Specification 17, §14.20.1 — Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): cách chọn và thực thi một nhánh `catch`.
- [Java Language Specification 17, §14.20.2 — Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): quy tắc `finally` trong đường kết thúc bất thường.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception phát sinh trong các câu lệnh của phương thức.
- [Java Language Specification 17, §11.3 — Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): tìm handler theo ngữ cảnh thực thi.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `addSuppressed()` và stack trace.

**Điểm cốt lõi:** một `catch` đang xử lý lỗi không có nghĩa mọi câu lệnh trong đó đều an toàn. Nếu handler ném ngoại lệ khác, ngoại lệ ấy được xử lý theo các `try` bao quanh **điểm ném mới**; các `catch` cùng cấp không bắt hộ. Thiết kế handler đơn giản, giữ lỗi gốc qua cause/suppressed khi cần và chú ý `finally` để chẩn đoán chính xác.
