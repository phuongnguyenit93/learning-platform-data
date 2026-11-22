# Tham số multi-catch ngầm định `final` trong Java

**Multi-catch** cho phép một khối `catch` xử lý nhiều kiểu ngoại lệ khi các kiểu đó cần cách ứng xử giống nhau:

~~~java
try {
    process();
} catch (java.io.IOException | java.sql.SQLException error) {
    System.out.println("Không xử lý được: " + error.getMessage());
}
~~~

Đây là đoạn minh họa: `process()` đại diện cho thao tác có thể ném các ngoại lệ tương ứng. Dấu `|` nối **các kiểu ngoại lệ**, không phải toán tử OR để kiểm tra biểu thức boolean. Java chọn nhánh khi đối tượng ngoại lệ đang truyền phù hợp với **bất kỳ** kiểu nào trong danh sách.

Một quy tắc đặc biệt của Java là: **tham số của multi-catch được xem là `final` ngầm định**. Vì vậy, trong ví dụ trên, tên `error` có thể dùng để đọc, chuyển cho hàm khác, ném lại hoặc truyền làm `cause`, nhưng **không thể được gán lại để trỏ sang ngoại lệ khác**.

~~~java
catch (java.io.IOException | java.sql.SQLException error) {
    error = new java.io.IOException("Lỗi mới"); // Không biên dịch.
}
~~~

Điều này khác với tham số của `catch` chỉ có một kiểu, vốn không mặc nhiên `final`. Nắm chắc quy tắc này giúp hiểu lỗi biên dịch, phạm vi biến, cách xử lý nhiều ngoại lệ và cơ chế **precise rethrow** (ném lại với phân tích kiểu ngoại lệ chính xác).

## 1. Cú pháp và lý do sử dụng multi-catch

Trước khi có multi-catch (Java 7), hai loại lỗi được xử lý giống nhau thường phải viết thành hai nhánh riêng:

~~~java
try {
    process();
} catch (java.io.IOException e) {
    report(e);
} catch (java.sql.SQLException e) {
    report(e);
}
~~~

Có thể gộp chúng khi cách xử lý thực sự giống nhau:

~~~java
try {
    process();
} catch (java.io.IOException | java.sql.SQLException e) {
    report(e);
}
~~~

Hai đoạn chỉ minh họa cấu trúc, giả định `process()` và `report(Throwable)` tồn tại. Cách gộp làm giảm lặp code; mỗi khi chỉ một trong hai loại lỗi được ném, **cùng một khối `catch`** được chạy đúng một lần.

Một số điểm cú pháp:

- Phần đầu là `catch (`, theo sau một danh sách **kiểu ngoại lệ** ngăn cách bằng `|`, rồi **một tên tham số duy nhất**.
- `e` là một biến tham chiếu có phạm vi bên trong khối `catch` tương ứng.
- Các kiểu liệt kê phải hợp lệ theo luật `catch` và **không được có quan hệ cha–con** trong cùng một multi-catch.
- Danh sách kiểu hỗ trợ cả checked và unchecked exceptions nếu cấu trúc bắt hợp lệ.
- Nếu mỗi ngoại lệ cần thông tin hoặc hành động khác nhau, tách thành các nhánh `catch` riêng có thể rõ nghĩa hơn.

Multi-catch không tạo ra một lớp ngoại lệ mới có tên `IOException | SQLException`. Đối tượng được bắt vẫn giữ **kiểu runtime ban đầu**.

## 2. `final` ngầm định nghĩa là gì?

Xét mã:

~~~java
catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getMessage()); // Được đọc.
    log(e);                              // Được truyền làm đối số.
    e = new java.io.IOException();       // Lỗi biên dịch.
}
~~~

Đây là đoạn minh họa thuộc một cấu trúc `try/catch` có đủ điều kiện; giả định `log(Throwable)` tồn tại. Dòng cuối sai vì tham số multi-catch được ngôn ngữ xem là `final`. Việc gán lại tham chiếu `e` không được phép.

Một cách hiểu đúng:

~~~text
Một ngoại lệ được ném
          |
          v
catch (IOException | SQLException e)
          |
          +-- e tham chiếu đến đối tượng ngoại lệ đã được bắt
          |
          +-- đọc / truyền / ném lại e: cho phép
          |
          +-- e = một ngoại lệ khác: bị cấm
~~~

Quy tắc chỉ hạn chế **gán lại biến tham số `e`**; nó không làm mọi đối tượng ngoại lệ trở thành immutable. Chẳng hạn, các thao tác phù hợp trên đối tượng ngoại lệ vẫn có thể được gọi qua tham chiếu `e`. Tuy nhiên không nên tùy tiện thay đổi cause, stack trace hoặc suppressed exceptions, vì những thông tin đó phục vụ chẩn đoán.

`final` ngầm định áp dụng **không phụ thuộc** ngoại lệ đang được bắt thực tế là `IOException` hay `SQLException`. Compiler xác định đặc tính này từ **cú pháp multi-catch** ngay tại thời điểm biên dịch.

### Có bắt buộc viết từ khóa `final` không?

Không. Viết:

~~~java
catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getMessage());
}
~~~

là đủ để `e` được coi là final ngầm định. Có thể gặp cú pháp khai báo tham số với `final` tường minh:

~~~java
catch (final java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getMessage());
}
~~~

Kết quả quan trọng giống nhau: `e` không được gán lại. Với multi-catch, viết thêm `final` không phải điều kiện để compiler áp dụng quy tắc.

## 3. So sánh single-catch và multi-catch

| Tính chất | `catch (IOException e)` | `catch (IOException | SQLException e)` |
| --- | --- | --- |
| Số kiểu được liệt kê | Một | Hai hoặc nhiều |
| Tham số mặc nhiên `final`? | Không | **Có** |
| Có thể viết `e = ...`? | Về mặt `final`, có nếu không khai báo `final`; còn phải hợp kiểu | **Không**, luôn báo lỗi biên dịch |
| Có thể đọc `e.getMessage()`? | Có | Có |
| Có thể `throw e;`? | Có, theo quy tắc kiểm tra ngoại lệ | Có, theo quy tắc kiểm tra ngoại lệ và precise rethrow |
| Kiểu của `e` | Kiểu đã khai báo trong nhánh | Kiểu tính từ các alternative, thường chỉ dùng được API chung |
| Có thể truyền `e` làm `Throwable`? | Có | Có |

Ví dụ single-catch **được phép gán lại**:

~~~java
try {
    throw new java.io.IOException("old");
} catch (java.io.IOException e) {
    e = new java.io.IOException("replacement");
    System.out.println(e.getMessage());
}
~~~

Đây là đoạn có thể đặt trong một phương thức Java: dòng in ra là `replacement`. Sau câu lệnh gán, `e` tham chiếu tới đối tượng mới. Dù hợp lệ về cú pháp, **đánh mất tham chiếu tới ngoại lệ gốc** dễ làm việc chẩn đoán trở nên khó khăn. Thông thường nên giữ biến bắt lỗi ban đầu và tạo một biến khác nếu cần.

Thử thay `catch (IOException e)` bằng `catch (IOException | SQLException e)` trong một `try` có khả năng ném cả hai kiểu thì câu lệnh gán `e = ...` sẽ bị từ chối. Sự khác biệt nằm ở **thể loại tham số bắt ngoại lệ**, không phải ở việc vế phải của phép gán là `IOException`.

## 4. `final` của biến tham chiếu không đồng nghĩa đối tượng bất biến

Ví dụ:

~~~java
try {
    mayFail();
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getClass().getSimpleName());
    System.out.println(e.getMessage());
    throw e;
}
~~~

Đây là phương thức minh họa, trong đó `mayFail()` có thể ném hai ngoại lệ và phương thức bao quanh cần đáp ứng hợp đồng `throws`. `getClass()`, `getMessage()` và `throw e` đều dùng chính đối tượng ngoại lệ ban đầu; không gán lại biến `e`.

Ngược lại, lệnh:

~~~java
e = new java.io.IOException("another");
~~~

thay giá trị tham chiếu của biến `e`, vì vậy không được phép trong multi-catch.

Điều `final` **không bảo đảm**:

- Không bảo đảm đối tượng ngoại lệ không có trạng thái có thể thay đổi.
- Không bảo đảm không có code nào khác đang giữ tham chiếu tới cùng đối tượng.
- Không bảo đảm ngoại lệ không thể được truyền, ném lại hoặc bọc làm cause.
- Không tạo bản sao bất biến của `Throwable`.

Nếu muốn thêm thông tin nghiệp vụ, cách rõ ràng là **tạo một ngoại lệ bọc mới** và giữ đối tượng gốc làm cause:

~~~java
catch (java.io.IOException | java.sql.SQLException e) {
    throw new IllegalStateException(
            "Không thể hoàn thành thao tác dữ liệu", e);
}
~~~

Đây là đoạn minh họa dùng trong một `try` có thể ném hai kiểu lỗi. `e` không bị gán lại; constructor của `IllegalStateException` giữ được nguyên nhân bằng `getCause()`.

## 5. Kiểu tĩnh của tham số khi gộp nhiều ngoại lệ

Trong single-catch:

~~~java
catch (java.sql.SQLException e) {
    System.out.println(e.getSQLState());
}
~~~

biến `e` được khai báo với kiểu `SQLException`, nên có thể gọi `getSQLState()`.

Nhưng khi viết:

~~~java
catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getMessage()); // Hợp lệ: API chung.
    // System.out.println(e.getSQLState()); // Không hợp lệ.
}
~~~

`e` có kiểu được Java tính từ **least upper bound** (LUB) của các alternative, đôi khi là dạng kiểu giao (*intersection type*). Nó không được xem là `SQLException` một cách vô điều kiện, vì tại runtime `e` cũng có thể tham chiếu tới `IOException`.

Vì vậy, bên trong multi-catch, chỉ nên dựa vào **những phương thức có thể sử dụng an toàn trên kiểu tĩnh** mà compiler xác định, ví dụ `getMessage()`, `getCause()`, `getClass()`, `printStackTrace()`.

Nếu cần API riêng của một loại lỗi, có hai cách.

**Cách A — tách catch theo loại:**

~~~java
try {
    mayFail();
} catch (java.sql.SQLException e) {
    System.out.println(e.getSQLState());
} catch (java.io.IOException e) {
    System.out.println(e.getMessage());
}
~~~

**Cách B — kiểm tra subtype trong multi-catch:**

~~~java
try {
    mayFail();
} catch (java.io.IOException | java.sql.SQLException e) {
    if (e instanceof java.sql.SQLException sqlError) {
        System.out.println(sqlError.getSQLState());
    } else {
        System.out.println(e.getMessage());
    }
}
~~~

Các ví dụ giả định `mayFail()` có khai báo checked exception tương ứng. Cú pháp `instanceof` với pattern variable `sqlError` được Java 17 hỗ trợ; nó tạo một **biến riêng** có kiểu `SQLException` trong phạm vi thích hợp, không gán lại `e`.

Không nên ép kiểu không kiểm tra `(SQLException) e` rồi gọi phương thức chuyên biệt: khi đối tượng thực tế là `IOException`, sẽ phát sinh `ClassCastException`.

## 6. Không được gộp kiểu cha và kiểu con cùng một multi-catch

Cú pháp `catch (FileNotFoundException | IOException ex)` là **lỗi biên dịch** vì `FileNotFoundException extends IOException`. Nếu mọi lỗi I/O có chung cách xử lý, dùng một `catch (IOException ex)`; nếu khác nhau, dùng hai handler với `FileNotFoundException` **trước** `IOException`. Compiler cũng kiểm tra khả năng phát sinh checked exceptions ở `try`.

Quy tắc này **độc lập** với trọng tâm của bài: kể cả khi hai alternative hoàn toàn hợp lệ, tham số chung của multi-catch vẫn **ngầm `final`**, không được gán lại. Việc sửa danh sách alternative không biến `ex` thành biến có thể gán như single-catch.

## 7. Multi-catch và precise rethrow

`throw ex;` trong multi-catch **ném lại đúng đối tượng đang bắt**. Với ví dụ sau, chữ ký giữ hai loại checked exception cụ thể, còn tham số `ex` không thể bị gán lại:

~~~java
static void relay() throws java.io.IOException, java.sql.SQLException {
    try {
        perform();
    } catch (java.io.IOException | java.sql.SQLException ex) {
        throw ex;
    }
}
~~~

Đây là phương thức minh họa; `perform()` cần khai báo có thể ném `IOException` và `SQLException`. **Precise rethrow** là quy tắc compiler có thể suy luận những checked exception cụ thể thoát ra từ `try` khi `throw ex` và tham số `catch` `final` hoặc *effectively final*.

Đừng nhầm: **multi-catch ngầm `final`** là quy tắc cấm gán lại tham số; **precise rethrow** là quy tắc kiểm tra ngoại lệ khi ném lại. Chúng bổ trợ nhau nhưng không đồng nhất. Ngay cả `catch (Exception ex)` đơn, nếu `ex` không bị gán lại, cũng có thể được suy luận hẹp. Nếu tham số single-catch bị gán lại, điều kiện precise rethrow có thể mất. Việc ném lại không thay đổi lớp runtime, không tự phục hồi thất bại và vẫn phải đáp ứng `throws` của tầng gọi.

## 8. Ví dụ Java 17+ hoàn chỉnh

Chương trình minh họa:

1. Một `try` có thể ném hai kiểu checked exception khác nhau.
2. Tham số `catch (IOException | SQLException e)` được dùng để log rồi **ném lại** mà không gán lại.
3. `main` bắt riêng từng kiểu sau khi nhận ngoại lệ từ phương thức trung gian.
4. Nhánh không lỗi không đi vào `catch`.

Tạo tệp **`MultiCatchFinalDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchFinalDemo {
    public static void main(String[] args) {
        for (String source : new String[] {"ok", "file", "database"}) {
            try {
                relay(source);
            } catch (IOException e) {
                System.out.println("main IO: " + e.getMessage());
            } catch (SQLException e) {
                System.out.println("main SQL: " + e.getMessage());
            }
        }
    }

    static void relay(String source)
            throws IOException, SQLException {
        try {
            perform(source);
        } catch (IOException | SQLException problem) {
            System.out.println(
                    "relay caught: " + problem.getClass().getSimpleName());
            throw problem;
        }
    }

    static void perform(String source)
            throws IOException, SQLException {
        if ("file".equals(source)) {
            throw new IOException("file unavailable");
        }
        if ("database".equals(source)) {
            throw new SQLException("query unavailable");
        }
        System.out.println("operation ok");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MultiCatchFinalDemo.java
java MultiCatchFinalDemo
~~~

**Stdout chính xác:**

~~~text
operation ok
relay caught: IOException
main IO: file unavailable
relay caught: SQLException
main SQL: query unavailable
~~~

### Lần theo luồng thực thi

- Với `"ok"`, `perform` in `operation ok` và kết thúc bình thường. `relay` không đi vào `catch`, vì không có ngoại lệ để bắt.
- Với `"file"`, `perform` ném `IOException`. `catch` trong `relay` nhận nó, in tên kiểu, rồi `throw problem;` ném lại đúng đối tượng. `main` nhận ở nhánh `catch (IOException e)`.
- Với `"database"`, đối tượng được ném là `SQLException`. Cùng khối multi-catch bên trong xử lý bước ghi nhận và ném lại; `main` bắt ở nhánh `catch (SQLException e)`.
- Ở cả hai đường lỗi, không có lệnh `problem = ...;`. Tham số multi-catch vẫn tham chiếu tới cùng ngoại lệ runtime được truyền vào.

**Tại sao `relay` không cần khai báo `throws Exception`?** Vì khai báo `throws IOException, SQLException` tương thích với hai loại ngoại lệ checked cụ thể có thể được chuyển tiếp. Việc xử lý gộp không làm “biến” chúng thành một đối tượng `Exception` mới.

### Thử thay đổi để thấy lỗi biên dịch

Trong mã trên, nếu thêm dòng:

~~~java
problem = new IOException("replacement");
~~~

vào khối `catch (IOException | SQLException problem)`, trình biên dịch sẽ từ chối **ngay tại phép gán** vì `problem` là tham số multi-catch ngầm định `final`. Đây là một đoạn phản ví dụ, không phải phần của chương trình chạy được.

Nếu nhu cầu thực sự là bọc lỗi với thông điệp ở tầng cao hơn, có thể giữ nguyên `problem`:

~~~java
catch (IOException | SQLException problem) {
    throw new IllegalStateException(
            "Không thể hoàn tất tải dữ liệu", problem);
}
~~~

Đây là đoạn minh họa về cách đổi chính sách lỗi: `IllegalStateException` là unchecked; cause giữ ngoại lệ gốc. Nếu API phải chuyển tiếp đúng hai loại checked exception, hãy tiếp tục dùng `throw problem;` như chương trình chính.

## 9. Tại sao tham số multi-catch cần ngầm định `final`?

Quy tắc giúp **một biến bắt lỗi đại diện ổn định cho chính ngoại lệ được bắt** trong suốt khối multi-catch. Khi một biến có thể đại diện cho nhiều kiểu checked exception, việc cho gán một ngoại lệ mới vào cùng biến sẽ tạo nhầm lẫn giữa:

- **Ngoại lệ gốc đã được ném từ khối `try`**; và
- **Ngoại lệ mới được tạo bên trong `catch`**.

Ví dụ ý tưởng không hợp lệ:

~~~java
catch (IOException | SQLException e) {
    e = new IOException("Thay thế lỗi đã nhận");
    throw e;
}
~~~

Ở mức ý nghĩa, đoạn này làm mất tham chiếu tên `e` đến đối tượng gốc. Ở mức luật Java, nó đơn giản là **không biên dịch**. Nếu muốn đổi đối tượng lỗi, hãy viết tên khác:

~~~java
catch (IOException | SQLException e) {
    IllegalStateException wrapped =
            new IllegalStateException("Thao tác thất bại", e);
    throw wrapped;
}
~~~

Bằng cách đó, `e` tiếp tục chỉ tới lỗi gốc; `wrapped` chỉ tới lỗi mới và `wrapped.getCause() == e` là `true`. Mã thể hiện rõ rằng đang bọc lỗi thay vì thay đổi tham số bắt lỗi.

Quy tắc ngầm định `final` giúp hỗ trợ mô hình phân tích kiểu cho multi-catch, đồng thời làm mã dễ theo dõi hơn. Tuy nhiên, **không có nghĩa mọi single-catch đều nên gán lại tham số chỉ vì Java cho phép**. Giữ nguyên đối tượng gốc thường là thực hành tốt cho cả hai loại catch.

## 10. Phạm vi tham số và tác động tới xử lý ngoại lệ

Tên tham số `e` chỉ có hiệu lực trong khối `catch`:

~~~java
try {
    perform("file");
} catch (IOException | SQLException e) {
    System.out.println(e.getMessage());
}
// System.out.println(e); // Sai: e ở ngoài phạm vi catch.
~~~

Đây là đoạn minh họa cần nằm trong một phương thức phù hợp. Không thể truy cập `e` sau dấu `}` kết thúc `catch`.

`final` không mở rộng phạm vi biến. Nó chỉ hạn chế **phép gán lại biến tham số** khi biến còn trong phạm vi.

Nếu cần một kết quả bên ngoài `catch`, phải thiết kế biến kết quả, giá trị trả về hoặc ngoại lệ chuyển tiếp sao cho hợp lệ theo quy tắc biến cục bộ và luồng điều khiển. Không nên đưa một biến ngoại lệ chưa được khởi tạo ra ngoài rồi tìm cách gán trong mọi nhánh chỉ để quan sát nó.

Ví dụ rõ ràng hơn cho mã gọi:

~~~java
static boolean completed(String source) {
    try {
        perform(source);
        return true;
    } catch (IOException | SQLException e) {
        return false;
    }
}
~~~

Đây là phương thức minh họa. `return true` chỉ chạy khi `perform` hoàn tất; đường ném ngoại lệ phù hợp đi vào `catch` rồi trả `false`. Không cần gán lại `e` hay truy cập nó ngoài phạm vi.

Nếu cần đưa ra lý do lỗi, một kết quả có cấu trúc hoặc ngoại lệ chuyển tiếp thường có ích hơn boolean.

## 11. Trường hợp nên và không nên dùng multi-catch

Multi-catch phù hợp khi hai loại lỗi **có cùng chính sách xử lý**:

~~~java
try {
    perform("file");
} catch (IOException | SQLException e) {
    recordFailure(e);
    throw new IllegalStateException("Không thể xử lý", e);
}
~~~

Đây là đoạn minh họa có phương thức `recordFailure(Throwable)`. Cùng chính sách: ghi nhận lỗi và chuyển nó thành lỗi ở tầng cao hơn.

Nếu mỗi loại lỗi cần hướng phục hồi khác nhau, dùng catch riêng có thể thích hợp hơn:

~~~java
try {
    perform("file");
} catch (IOException e) {
    System.out.println("Yêu cầu chọn nguồn dữ liệu khác");
} catch (SQLException e) {
    System.out.println("Yêu cầu kiểm tra kết nối cơ sở dữ liệu");
}
~~~

Hai trường hợp cần phân biệt:

| Tình huống | Cách viết thích hợp |
| --- | --- |
| Hai ngoại lệ có cùng kết quả xử lý, thông điệp và cách chuyển tiếp | `catch (A | B e)` |
| Phải dùng API chuyên biệt từng loại lỗi | Hai `catch` hoặc `instanceof` có kiểm tra |
| Muốn ném lại cùng ngoại lệ đã bắt | `throw e;`; multi-catch hỗ trợ precise rethrow |
| Muốn tạo lỗi mới, giữ lỗi gốc | `throw new SomeException(message, e);` |
| Muốn gán lại biến `e` | Multi-catch **không cho phép**; tạo biến mới nếu cần |
| Hai alternative có quan hệ cha–con | Không dùng cùng một multi-catch |

Multi-catch chỉ là **cách gộp xử lý ngoại lệ**, không tự quyết định ngoại lệ có thể phục hồi được hay không. Kiểu checked/unchecked cũng vẫn tuân theo phân cấp lớp gốc của đối tượng ngoại lệ.

## 12. Những lỗi thường gặp

### Lỗi 1 — Cố gán lại tham số multi-catch

~~~java
catch (IOException | SQLException e) {
    e = new IOException("new");
}
~~~

Không biên dịch: `e` ngầm định `final`. Giải pháp là **không gán lại**. Để đổi lỗi, tạo đối tượng mới vào một biến khác hoặc ném đối tượng bọc với `cause`.

### Lỗi 2 — Nhầm `final` với việc cấm ném lại

~~~java
catch (IOException | SQLException e) {
    throw e;
}
~~~

Hoàn toàn có thể hợp lệ nếu hợp đồng checked exception của phương thức bao quanh cho phép. `throw e` không phải phép gán lại `e`; nó dùng tham chiếu hiện tại để ném.

### Lỗi 3 — Nghĩ multi-catch biến mọi lỗi thành `Exception`

Không. Đối tượng runtime vẫn là `IOException` hoặc `SQLException`. Gộp `catch` không xóa loại cụ thể trong `e.getClass()`, `cause` hoặc stack trace.

### Lỗi 4 — Gọi API chỉ có ở một alternative

~~~java
catch (IOException | SQLException e) {
    // e.getSQLState(); // Sai về kiểu tĩnh.
}
~~~

Không thể giả định mọi đối tượng trong multi-catch đều có API của `SQLException`. Tách catch hoặc kiểm tra `instanceof SQLException sql`.

### Lỗi 5 — Gộp cha và con

`catch (FileNotFoundException | IOException e)` không hợp lệ. `FileNotFoundException` đã thuộc nhóm `IOException`.

### Lỗi 6 — Nghĩ single-catch cũng mặc nhiên final

`catch (IOException e)` thông thường có thể gán lại `e` nếu không khai báo `final`. Nhưng sau khi gán lại, `e` có thể mất tính effectively final, ảnh hưởng precise rethrow và làm mất liên kết tới lỗi gốc.

### Lỗi 7 — Nhầm “effectively final” với “được khai báo final”

Một biến **effectively final** không có từ khóa `final` nhưng trong thực tế không bị gán lại sau khi được khởi tạo. Single-catch có thể đạt điều kiện đó. Multi-catch là trường hợp **ngôn ngữ bắt buộc final ngầm định**. Hai khái niệm liên quan nhưng không giống nhau.

### Lỗi 8 — Nghĩ catch gộp bỏ qua checked exception

`IOException` và `SQLException` vẫn là checked. Khi chuyển tiếp `throw e;`, phương thức phải xử lý hoặc khai báo đúng các loại checked exception có thể thoát ra. Multi-catch không miễn quy tắc biên dịch.

### Lỗi 9 — Gán lại để “đổi thông báo” thay vì bọc lỗi

Thay tham chiếu `e` có thể làm mất cause, stack trace và thông điệp gốc. Với multi-catch, phép gán bị chặn; dùng `new IllegalStateException("...", e)` khi chính sách API muốn bọc lỗi và bảo toàn nguyên nhân.

### Lỗi 10 — Bắt quá rộng chỉ để tránh viết nhiều tên ngoại lệ

`catch (Exception e)` có thể che các lỗi lập trình unchecked ngoài dự kiến. Multi-catch thường diễn đạt tốt hơn ý định **xử lý đúng một tập hợp loại lỗi**; tuy nhiên khi một loại lỗi không còn cần cùng chính sách, đừng cố giữ chung cho ngắn mã.

## 13. Tự kiểm tra

1. Vì sao `catch (IOException | SQLException e)` không cho phép `e = new IOException(...)` dù đối tượng mới thuộc một trong hai kiểu?
2. Tham số `e` của `catch (IOException e)` có ngầm định `final` không? Từ khóa nào có thể dùng nếu muốn cấm gán lại tường minh?
3. `throw e;` có thay đổi giá trị tham chiếu của `e` không? Vì sao lệnh đó không vi phạm `final`?
4. Tại sao `e.getSQLState()` không được phép trực tiếp trong multi-catch `IOException | SQLException`?
5. Nếu cần đọc SQL state, bạn có thể làm gì mà vẫn giữ multi-catch?
6. Vì sao `catch (FileNotFoundException | IOException e)` không hợp lệ?
7. Precise rethrow giúp giữ chữ ký `throws` hẹp như thế nào?
8. Một single-catch `catch (Exception e)` không gán lại `e` có thể được precise rethrow không?
9. Nếu single-catch `catch (Exception e)` gán `e = new Exception(...)` rồi `throw e;`, compiler còn có thể suy ra chính xác hai loại checked ban đầu không?
10. `final` ngầm định có khiến đối tượng ngoại lệ bất biến không?
11. Nếu muốn thêm ngữ cảnh mà vẫn giữ nguyên nhân, nên làm gì thay vì gán lại `e`?
12. Nếu `perform("ok")` không ném lỗi, khối multi-catch có chạy không?
13. Đối tượng bị bắt là `SQLException` nhưng tham số `e` có nhiều kiểu alternative; `e.getClass().getSimpleName()` cho biết kiểu nào?
14. Khi hai ngoại lệ cần hai phương án khôi phục khác nhau, có nhất thiết gộp vào multi-catch không?

**Đáp án tóm tắt:** (1) Tham số multi-catch ngầm định `final`; (2) không, có thể thêm `final`; (3) không, chỉ ném tham chiếu đã có; (4) kiểu tĩnh phải an toàn với cả hai alternative; (5) `instanceof SQLException sql` hoặc tách catch; (6) kiểu cha–con không được đồng xuất hiện; (7) compiler giới hạn loại ngoại lệ có thể ném lại; (8) có khi thỏa quy tắc effectively final và phân tích nguồn exception; (9) không, biến đã bị gán lại; (10) không; (11) tạo ngoại lệ bọc với cause; (12) không; (13) `SQLException`; (14) không, tách catch có thể rõ ràng hơn.

## 14. Ghi nhớ

**Tham số của `catch (A | B e)` là `final` ngầm định**: Java không cho phép gán lại `e`, nhưng vẫn cho đọc, truyền, ghi nhận và ném lại đối tượng ngoại lệ. Các đối tượng được bắt vẫn giữ kiểu runtime ban đầu, còn kiểu tĩnh của tham số chỉ cho phép những thao tác an toàn với các alternative. Khi cần chuyển đổi lỗi, hãy tạo ngoại lệ mới và giữ `e` làm cause; khi cần chuyển tiếp, `throw e;` cùng cơ chế **precise rethrow** giúp giữ hợp đồng checked exception rõ ràng.