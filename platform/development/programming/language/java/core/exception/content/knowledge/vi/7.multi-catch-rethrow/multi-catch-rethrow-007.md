# Ảnh hưởng của `final`, *effectively final* và việc gán lại tham số `catch` trong Java

Trong Java, biến tham số của `catch` không chỉ dùng để đọc thông điệp ngoại lệ. **Có được gán lại tham số đó hay không** còn tác động đến khả năng sử dụng trong lambda/lớp ẩn danh và, đặc biệt, cách trình biên dịch phân tích kiểu checked exception khi viết `throw ex;` (*precise rethrow*).

Ba quy tắc cốt lõi:

1. Tham số của **single-catch** (ví dụ `catch (IOException ex)`) thông thường **có thể gán lại** nếu không khai báo `final`. Nếu mã thực tế không gán lại, tham số có thể là **effectively final**.
2. Tham số của **multi-catch** (ví dụ `catch (IOException | SQLException ex)`) **ngầm là `final`**. Không thể gán lại nó, ngay cả khi không viết từ khóa `final`.
3. Một tham số `catch` đơn với kiểu rộng như `Exception` có thể được trình biên dịch phân tích **ném lại chính xác hơn kiểu khai báo** nếu nó `final` hoặc *effectively final*. Gán lại tham số có thể làm mất tính chính xác đó và dẫn đến lỗi biên dịch checked exception.

Vì vậy, phải phân biệt **kiểu tĩnh của tham số `catch`**, **kiểu runtime của đối tượng ngoại lệ**, **khả năng gán lại biến**, và **hợp đồng `throws` của phương thức**. Chúng liên quan nhưng không đồng nhất.

## 1. Nhắc lại: tham số `catch` là gì?

Một mệnh đề `catch` khai báo một tham số đại diện cho đối tượng ngoại lệ được handler tiếp nhận:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Đầu ra:

```text
NumberFormatException
```

- `NumberFormatException` là **kiểu khai báo** của tham số.
- `ex` là **biến tham chiếu** tới đối tượng ngoại lệ đang được xử lý.
- `ex.getMessage()`, `ex.getCause()`, `ex.getStackTrace()` cho phép xem thông tin chẩn đoán, tùy tình huống.
- Phạm vi của `ex` là **thân handler `catch`** tương ứng; biến này không tồn tại ở các nhánh `catch` anh em hay sau cấu trúc `try-catch`.

Thông thường, bạn **không cần gán lại `ex`**. Người viết code sẽ đọc ngoại lệ, xử lý hoặc ném lại. Nhưng Java cho phép gán lại một số biến `catch`, và ở đó phát sinh khác biệt giữa single-catch và multi-catch.

## 2. `final` thực sự có nghĩa gì với tham số `catch`?

`final` trên một biến tham chiếu cấm thay đổi **giá trị tham chiếu của biến đó** sau khi biến được khởi tạo. Nó **không làm đối tượng được tham chiếu trở thành bất biến**.

Ví dụ minh họa trong một phương thức:

```java
try {
    throw new IllegalArgumentException("bad input");
} catch (final IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
    // ex = new IllegalArgumentException("other"); // Lỗi biên dịch.
}
```

Đây là code minh họa; dòng bị comment nếu bỏ comment sẽ cố ý không biên dịch, do `ex` được khai báo `final`.

Điều **không** được phép với biến `final`:

```java
// Sai nếu ex đã được khai báo final:
ex = new IllegalArgumentException("replacement");
ex = null;
```

Điều **có thể** làm:

```java
System.out.println(ex.getMessage());
Throwable cause = ex.getCause();
```

`final` không làm biến mất khả năng gọi phương thức trên đối tượng. Các phương thức của đối tượng có thể thay đổi trạng thái nếu API cho phép; `final` chỉ kiểm soát việc gán lại **biến tham chiếu**.

**Phân biệt:** `final` không ngăn `throw ex;`. Lệnh `throw` chỉ sử dụng tham chiếu để ném đối tượng, không phải phép gán vào biến `ex`.

## 3. *Effectively final* là gì?

Một biến hoặc tham số được gọi là **effectively final** khi mã tuân thủ các quy tắc không gán lại phù hợp của ngôn ngữ, dù **không viết rõ từ khóa `final`**. Với tham số `catch` đơn, hiểu thực hành là: sau khi tham số nhận đối tượng ngoại lệ, mã không gán lại giá trị cho tham số đó.

Ví dụ:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getMessage());
    // Không có phép gán ex = ...
}
```

`ex` không khai báo `final`, nhưng vẫn **effectively final**.

Ngược lại:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    ex = new NumberFormatException("custom description");
    System.out.println(ex.getMessage());
}
```

Đoạn mã thứ hai **có thể biên dịch** vì đây là **single-catch** không khai báo `final`. Nhưng tham số `ex` không còn *effectively final*.

Cần chú ý:

- `ex = ex;` vẫn là **một phép gán**, nên không được coi là cách giữ *effectively final*.
- Một phép gán trong nhánh `if` có điều kiện cũng có thể làm mất thuộc tính này; không phải cứ nhánh đó ít chạy là trình biên dịch bỏ qua.
- Gọi `ex.getMessage()` không phải phép gán vào `ex`.
- Gán một biến **khác**, ví dụ `Exception original = ex;`, không làm thay đổi tính *effectively final* của `ex`.
- Thay đổi tham chiếu `ex` không thay đổi đối tượng ngoại lệ ban đầu; nó chỉ khiến tên biến `ex` trỏ tới đối tượng mới.

Một điểm thú vị: *effectively final* không phải kiểu dữ liệu mới, không xuất hiện ở runtime và không khiến JVM “khóa” đối tượng. Đây là khái niệm để **trình biên dịch** kiểm tra và phân tích chương trình.

## 4. Single-catch: được phép gán lại, nhưng nên hiểu hệ quả

`catch (IOException ex)` là **single-catch** với một kiểu ngoại lệ:

```java
try {
    readData();
} catch (java.io.IOException ex) {
    java.io.IOException original = ex;
    ex = new java.io.IOException("higher-level context", original);
    System.out.println(ex.getMessage());
}
```

Đây là **đoạn minh họa**, giả sử `readData()` có thể ném `IOException`. Nếu không khai báo `final`, phép gán `ex = ...` hợp lệ.

Tuy nhiên, có hai đối tượng cần phân biệt:

- `original` tiếp tục tham chiếu tới ngoại lệ được bắt ban đầu.
- `ex` sau phép gán trỏ tới ngoại lệ mới. Nếu code chỉ kết thúc handler bình thường thì ngoại lệ mới **không tự được ném** lên caller.

Do đó, **gán lại `ex` không phải là một cách để chuyển ngoại lệ**. Nếu cần bọc lỗi và gửi ra ngoài, hãy ném đối tượng mới:

```java
try {
    readData();
} catch (java.io.IOException cause) {
    throw new java.io.UncheckedIOException(
            "Cannot load required data", cause);
}
```

Đây là đoạn minh họa, cần có `readData()` thực sự; `UncheckedIOException` là lớp `RuntimeException` chuyên dùng để bọc `IOException`. Constructor giữ `cause` để truy vết.

**Thực hành tốt:** sử dụng một biến mới như `cause` hoặc `wrapped` khi cần biến đổi ngữ cảnh; không gán lại chính tham số `catch` chỉ để đổi thông điệp. Việc gán lại khiến mã khó đọc và, với một `catch` kiểu rộng, còn có thể ảnh hưởng đến phân tích *precise rethrow*.

## 5. Multi-catch: tham số ngầm `final`

Java hỗ trợ bắt nhiều loại lỗi khác nhánh bằng một handler:

```java
try {
    perform();
} catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Đây là cấu trúc minh họa. Để biên dịch nguyên dạng, `perform()` phải có hợp đồng phù hợp, chẳng hạn `throws IOException, SQLException`.

Trong multi-catch:

- Các loại trong danh sách phân cách bằng `|` không được có quan hệ **lớp cha – lớp con** với nhau.
- Các lựa chọn đều cùng dùng một biến `ex`.
- Biến `ex` **implicitly final**, nghĩa là ngầm được xem như `final` dù không có từ khóa này.
- Không thể gán lại `ex` bằng một ngoại lệ mới hay bằng `null`.
- Có thể đọc `ex`, xem kiểu thực tế, in thông điệp, chuyển nó làm `cause` hoặc `throw ex;` nếu hợp đồng checked exception cho phép.
- Kiểu tĩnh dùng để truy cập thành viên của `ex` được suy ra từ các lựa chọn của multi-catch; không thể mặc định gọi những phương thức chỉ có ở một nhánh nếu không kiểm tra kiểu phù hợp.

Ví dụ **cố ý không biên dịch**:

```java
try {
    perform();
} catch (java.io.IOException | java.sql.SQLException ex) {
    ex = new java.io.IOException("replacement"); // Lỗi: ex ngầm final.
}
```

Tương tự, dòng `ex = ex;` vẫn không được phép. Nếu cần một tham chiếu mới để thao tác, hãy khai báo **biến khác** trong handler; biến `ex` tiếp tục giữ đối tượng đã được bắt.

Một lỗi cú pháp/kiểu khác:

```java
// Sai: NumberFormatException là lớp con của IllegalArgumentException.
catch (NumberFormatException | IllegalArgumentException ex) {
    // ...
}
```

Đoạn trên **cố ý không biên dịch** vì lựa chọn thứ hai đã bao phủ lựa chọn thứ nhất. Sử dụng `catch (IllegalArgumentException ex)` hoặc tách handler cụ thể nếu hành động xử lý khác nhau.

## 6. Bảng so sánh chính xác

| Khía cạnh | Single-catch `catch (IOException ex)` | Single-catch `catch (final IOException ex)` | Multi-catch `catch (IOException | SQLException ex)` |
| --- | --- | --- | --- |
| Có từ khóa `final`? | Không | Có | Không cần |
| Biến có thể gán lại? | **Có**, trừ quy tắc khác áp dụng | **Không** | **Không**, vì ngầm `final` |
| Có thể effectively final? | **Có**, nếu không gán lại | Đã `final` tường minh | Đã `final` ngầm |
| Lambda có thể bắt giữ `ex`? | Có nếu effectively final | Có | Có |
| `throw ex;` có hợp lệ? | Có nếu thỏa quy tắc checked exception | Có nếu thỏa quy tắc checked exception | Có nếu thỏa quy tắc checked exception |
| Có thể áp dụng precise rethrow? | Có khi thỏa điều kiện phân tích kiểu | Có khi thỏa điều kiện | Có theo quy tắc phân tích kiểu tương ứng |
| `final` có đổi kiểu runtime không? | Không | Không | Không |

**Không nhầm:** `final` là quy tắc dành cho **biến**, không phải việc cấm ném ngoại lệ. Cũng không nên nói mọi `throw ex;` trong single-catch đều ném chính xác theo các ngoại lệ phát sinh bên trong `try`: điều đó phụ thuộc điều kiện phân tích và việc biến có bị gán lại hay không.

## 7. Vì sao *effectively final* quan trọng đối với lambda?

Biến cục bộ và tham số được **capture** từ phạm vi bên ngoài vào lambda cần là `final` hoặc *effectively final*.

Ví dụ single-catch hợp lệ:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    Runnable printer = () ->
            System.out.println(ex.getClass().getSimpleName());
    printer.run();
}
```

Stdout:

```text
NumberFormatException
```

Không có phép gán lại `ex`, nên lambda được dùng tham chiếu đó.

Nếu thêm phép gán vào `ex` trong handler:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    ex = new NumberFormatException("changed");
    Runnable printer = () -> System.out.println(ex.getMessage());
    printer.run();
}
```

Đoạn này **cố ý không biên dịch**: biến `ex` không còn *effectively final* nên không được capture từ lambda. Lỗi không phải do `Runnable` hay `NumberFormatException`, mà là do việc gán lại biến bị lambda tham chiếu.

Giải pháp rõ ràng hơn là **không gán lại ngoại lệ**, hoặc tạo một biến tách biệt:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    String description = "invalid number";
    Runnable printer = () -> System.out.println(description);
    printer.run();
}
```

Ở đây `description` là một biến cục bộ *effectively final*. Lambda đọc nó một cách hợp lệ. Nếu cần truyền cả ngoại lệ vào một tác vụ bất đồng bộ, phải xét thêm vòng đời dữ liệu, thread và chính sách bảo mật/logging; *effectively final* không tự bảo đảm thread safety của trạng thái bên trong đối tượng.

Với multi-catch, tham số `ex` ngầm `final`, nên việc capture không gặp trở ngại do gán lại chính biến đó. Điều này **không đồng nghĩa** tất cả đối tượng mà lambda sử dụng đều bất biến hoặc an toàn để dùng đồng thời.

## 8. Ví dụ Java 17+ hoàn chỉnh: gán lại single-catch và capture multi-catch

Lưu tên tệp **`CatchParameterDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class CatchParameterDemo {

    static void perform(String mode) throws IOException, SQLException {
        switch (mode) {
            case "io" -> throw new IOException("disk unavailable");
            case "sql" -> throw new SQLException("database unavailable");
            default -> System.out.println("task: ok");
        }
    }

    static void single(String mode) {
        try {
            perform(mode);
        } catch (IOException ex) {
            IOException original = ex;

            // Single-catch không final: phép gán lại hợp lệ.
            ex = new IOException("context added", original);

            System.out.println("single: rebound=" + ex.getMessage());
            System.out.println("single: source=" + original.getMessage());

        } catch (final SQLException ex) {
            // ex = new SQLException("another"); // Cố ý không hợp lệ.
            System.out.println("single: sql=" + ex.getMessage());
        }
    }

    static void multi(String mode) {
        try {
            perform(mode);
        } catch (IOException | SQLException ex) {
            // ex = new IOException("another"); // Cố ý không hợp lệ.
            Runnable printer = () ->
                    System.out.println(
                            "multi: " + ex.getClass().getSimpleName()
                            + ": " + ex.getMessage());
            printer.run();
        }
    }

    static void capture(String text) {
        try {
            Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            // Không gán lại ex => effectively final.
            Runnable printer = () ->
                    System.out.println(
                            "captured: " + ex.getClass().getSimpleName());
            printer.run();
        }
    }

    public static void main(String[] args) {
        single("io");
        single("sql");
        multi("io");
        multi("sql");
        multi("ok");
        capture("abc");
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CatchParameterDemo.java
java CatchParameterDemo
```

**Stdout chính xác:**

```text
single: rebound=context added
single: source=disk unavailable
single: sql=database unavailable
multi: IOException: disk unavailable
multi: SQLException: database unavailable
task: ok
captured: NumberFormatException
```

### Đọc hành vi trong ví dụ

**`single("io")`:** `perform` ném `IOException`. Trong handler đơn, `original` giữ tham chiếu tới lỗi gốc; `ex` được gán sang đối tượng mới. Vì handler chỉ in rồi kết thúc, đối tượng mới **không trở thành ngoại lệ bị ném ra khỏi `single`**. Đây là ví dụ minh họa tính hợp lệ của phép gán, không phải khuyến nghị xử lý lỗi theo cách này.

**`single("sql")`:** lỗi `SQLException` được bắt bởi handler có tham số `final SQLException ex`. Đọc thông điệp được; nếu bỏ comment dòng gán lại sẽ gây lỗi biên dịch.

**`multi("io")` và `multi("sql")`:** cùng một multi-catch xử lý hai loại checked exception không có quan hệ cha/con. Biến `ex` có kiểu tĩnh được suy ra phù hợp với cả hai lựa chọn, trong khi `ex.getClass().getSimpleName()` vẫn phản ánh loại **runtime thực tế**. Lambda được phép capture `ex`; code không và cũng không thể gán lại nó.

**`multi("ok")`:** không có ngoại lệ; handler không chạy, chỉ in `task: ok`.

**`capture("abc")`:** tham số single-catch không viết `final` nhưng không bị gán lại, nên là *effectively final* và được lambda sử dụng.

## 9. Precise rethrow là gì?

Đây là điểm dễ bị bỏ qua khi học `final` trong `catch`.

Thông thường, nếu ta có biến tham chiếu `Exception ex` rồi viết `throw ex;`, việc kiểm tra checked exception có thể bị hiểu là phải tính tới loại `Exception` rộng. Nhưng trong những điều kiện nhất định, Java phân tích được rằng tham số `catch` này chỉ có thể nhận **các ngoại lệ checked thực sự có thể phát sinh từ phần `try` tương ứng**, sau khi xét những handler đứng trước. Đó là **precise rethrow**, được giới thiệu từ Java 7.

Ví dụ:

```java
static void risky(String mode)
        throws java.io.IOException, java.sql.SQLException {
    if ("io".equals(mode)) {
        throw new java.io.IOException("disk error");
    }
    if ("sql".equals(mode)) {
        throw new java.sql.SQLException("query error");
    }
}

static void relay(String mode)
        throws java.io.IOException, java.sql.SQLException {
    try {
        risky(mode);
    } catch (Exception ex) {
        // ex không bị gán lại => effectively final.
        throw ex;
    }
}
```

Đây là **các phương thức minh họa**. `risky` có thể ném `IOException` hoặc `SQLException`, và `relay` **chỉ khai báo hai kiểu checked exception ấy**. Mặc dù tham số `catch` được khai báo là `Exception ex`, mã vẫn có thể biên dịch vì Java phân tích chính xác việc ném lại khi tham số không bị gán lại.

Nếu không có precise rethrow, người đọc có thể tưởng rằng `relay` buộc phải khai báo `throws Exception`. Đó không phải yêu cầu trong tình huống này.

### Điều kiện cần hiểu

Để được lợi từ phân tích precise rethrow cho tham số `catch` có kiểu rộng:

1. Ngoại lệ xuất phát từ các đường thực thi của `try` tương ứng có thể được phân tích theo luật kiểm tra ngoại lệ Java.
2. `ex` là tham số của `catch` đang bắt ngoại lệ đó.
3. Tham số không bị gán lại theo cách làm mất điều kiện `final`/*effectively final*.
4. Những kiểu checked exception còn có thể ném ra phải được bắt hoặc khai báo trong phương thức chứa `throw ex;`.

Nếu một `catch (Exception ex)` bắt cả unchecked exceptions, việc phân tích checked exception vẫn phải tuân theo quy tắc ngôn ngữ; không phải cứ có `catch (Exception)` là mọi phương thức đều tự động được khai báo bất kỳ kiểu nào.

**Quan trọng:** precise rethrow là **kiểm tra tại thời điểm biên dịch**; nó không “biến” đối tượng `IOException` thành `SQLException` hay thay đổi `getClass()` lúc chạy.

## 10. Ví dụ Java 17+ hoàn chỉnh: precise rethrow với tham số effectively final

Lưu tên tệp **`EffectivelyFinalRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class EffectivelyFinalRethrowDemo {

    static void risky(String mode) throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("storage unavailable");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("database unavailable");
        }
    }

    static void relay(String mode) throws IOException, SQLException {
        try {
            risky(mode);
        } catch (Exception ex) {
            System.out.println(
                    "relay: " + ex.getClass().getSimpleName());

            // ex effectively final, nên precise rethrow áp dụng.
            throw ex;
        }
    }

    static void runCase(String mode) {
        System.out.println("mode=" + mode);

        try {
            relay(mode);
            System.out.println("result=ok");
        } catch (IOException ex) {
            System.out.println("io: " + ex.getMessage());
        } catch (SQLException ex) {
            System.out.println("sql: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        runCase("io");
        runCase("sql");
        runCase("ok");
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 EffectivelyFinalRethrowDemo.java
java EffectivelyFinalRethrowDemo
```

**Stdout chính xác:**

```text
mode=io
relay: IOException
io: storage unavailable
mode=sql
relay: SQLException
sql: database unavailable
mode=ok
result=ok
```

### Phân tích từng đường chạy

- `risky("io")` ném `IOException`. `relay` bắt qua tham số kiểu rộng `Exception`, in loại thực tế rồi ném **cùng đối tượng** bằng `throw ex;`. `runCase` bắt `IOException`.
- `risky("sql")` tương tự với `SQLException`, và caller chọn handler `SQLException`.
- `risky("ok")` không ném; `catch` trong `relay` không chạy, nên `runCase` in `result=ok`.
- Chữ ký `relay(String mode) throws IOException, SQLException` là hợp lệ, **không cần đổi thành `throws Exception`**, vì tham số `ex` chưa hề được gán lại và trình biên dịch có thể xác định những loại checked exception từ `try`.

Ví dụ cho thấy sự khác nhau giữa **bắt bằng một kiểu cha để thực hiện một hành động chung** và **bảo toàn các kiểu checked exception của hợp đồng khi ném lại**.

Trong dự án thật, một handler chỉ để `throw ex;` thường thừa. Precise rethrow có giá trị khi handler cần làm việc có chủ đích trước khi chuyển lỗi tiếp: ghi nhận trạng thái tác vụ, bổ sung sự kiện giám sát hoặc quản lý một chính sách cục bộ.

## 11. Gán lại tham số `catch` có thể làm mất precise rethrow

Xem phiên bản **cố ý không biên dịch** sau:

```java
static void relayBad(String mode)
        throws java.io.IOException, java.sql.SQLException {
    try {
        risky(mode);
    } catch (Exception ex) {
        ex = new Exception("replacement");
        throw ex; // Lỗi biên dịch: Exception checked chưa được khai báo.
    }
}
```

Đây là **mã cố ý sai**, giả định phương thức `risky` ở ví dụ phía trước tồn tại và khai báo `throws IOException, SQLException`.

Nguyên nhân:

1. `catch (Exception ex)` đơn không viết `final` cho phép **gán lại** tham số.
2. Sau phép gán `ex = new Exception(...)`, tham số `ex` **không còn effectively final**.
3. Trình biên dịch không thể áp dụng phân tích ném lại chính xác như trước. Biểu thức `throw ex` lúc này cần được kiểm tra theo kiểu tĩnh rộng `Exception`.
4. Chữ ký `throws IOException, SQLException` không bao phủ mọi checked `Exception`, vì vậy báo lỗi.

Các cách sửa tùy ý định:

- **Không gán lại `ex`** nếu chỉ muốn chuyển tiếp đúng lỗi gốc; giữ `throw ex;`.
- **Khai báo `final Exception ex`** để người viết vô tình gán lại sẽ được báo lỗi ngay tại phép gán.
- Nếu thật sự muốn **ném ngoại lệ mới** kiểu `Exception`, khai báo/catch phù hợp theo hợp đồng, hoặc chọn một kiểu cụ thể có ý nghĩa và giữ ngoại lệ gốc làm `cause`.
- **Đừng mở chữ ký thành `throws Exception` chỉ để che thiết kế lỗi không rõ ràng**, nếu caller chỉ cần xử lý `IOException` và `SQLException`.

Lưu ý tinh tế: gán lại một tham số `catch (IOException ex)` cũng làm mất *effectively final*, nhưng `throw ex;` vẫn có thể hợp lệ trong phương thức `throws IOException`, bởi **kiểu tĩnh của `ex` vốn đã là `IOException`**. Vấn đề precise rethrow biểu hiện rõ nhất khi handler dùng **kiểu khai báo rộng hơn các checked exception có thể thực sự phát sinh từ `try`**.

## 12. `final` tường minh trong single-catch có tác dụng thế nào?

Thay vì:

```java
catch (Exception ex) {
    throw ex;
}
```

có thể viết:

```java
catch (final Exception ex) {
    throw ex;
}
```

Trong bối cảnh `try` và chữ ký phù hợp, cả hai đều có thể hưởng phân tích precise rethrow. Khác biệt chính là:

- `final` tường minh làm **mọi phép gán lại `ex` bị báo lỗi ngay**.
- Không viết `final` nhưng giữ *effectively final* vẫn đủ cho các quy tắc liên quan.
- Dùng `final` thể hiện chủ ý rõ ràng rằng biến tham chiếu không nên bị thay đổi.
- `final` **không** tự khiến một handler kiểu rộng trở thành cách xử lý tốt: nó không quyết định chính sách phục hồi, không bảo vệ dữ liệu nhạy cảm và không thay thế việc chọn loại lỗi thích hợp.

Trong Java hiện đại, có thể chọn phong cách dự án: khai báo `final` cho các tham số quan trọng, hoặc dựa vào *effectively final*. Nhưng **không nên gán lại tham số bắt lỗi chỉ vì cú pháp cho phép**.

## 13. `catch` kiểu rộng, thứ tự các handler và giới hạn precise rethrow

Giả sử `try` có thể ném cả `IOException` và `SQLException`. Một handler cụ thể có thể xử lý một phần, còn handler sau ném lại phần còn lại:

```java
static void caller() throws java.sql.SQLException {
    try {
        performDatabaseAndFileOperation();
    } catch (java.io.IOException ex) {
        System.out.println("I/O issue has been handled");
    } catch (Exception ex) {
        throw ex;
    }
}
```

Đây là **các khai báo minh họa**, giả định `performDatabaseAndFileOperation()` có `throws IOException, SQLException` và không có checked exception khác. Khi handler `IOException` trước đã xử lý nhóm I/O, handler `catch (Exception ex)` sau chỉ cần ném lại nhóm checked còn lại `SQLException`, nên khai báo `throws SQLException` của `caller` có thể đủ theo quy tắc precise rethrow.

Không đảo thứ tự thành `catch (Exception)` trước `catch (IOException)`: handler lớp cha phía trước sẽ khiến handler lớp con không thể tới được.

**Vì sao điều này quan trọng?** Trình biên dịch không chỉ nhìn một dòng `throw ex;` mà còn phân tích các loại checked exception trong phần `try` và những handler đã bắt chúng trước đó. Đây là lý do không nên đơn giản hóa precise rethrow thành câu “`catch (Exception)` luôn đòi `throws Exception`” hay “`catch (Exception)` luôn có thể khai báo tùy ý”.

Nếu chưa chắc kiểu nào có thể thoát ra, hãy biên dịch một ví dụ độc lập và kiểm tra chữ ký, thay vì đổi ngẫu nhiên toàn bộ các loại `throws` thành `Exception`.

## 14. Multi-catch và việc ném lại

Một multi-catch có thể ném lại đối tượng:

```java
static void relayMulti(String mode)
        throws java.io.IOException, java.sql.SQLException {
    try {
        risky(mode);
    } catch (java.io.IOException | java.sql.SQLException ex) {
        throw ex;
    }
}
```

Đoạn này là **phương thức minh họa**, giả định `risky(mode)` đã được định nghĩa với cùng hợp đồng checked exception. `IOException` và `SQLException` là hai lớp không có quan hệ cha/con, nên multi-catch hợp lệ. `ex` ngầm `final`; `throw ex;` giữ đối tượng lỗi thực tế và cho phép hợp đồng liệt kê hai loại checked exception.

Sự khác nhau cần nhớ:

- Trong **multi-catch**, không thể gán lại tham số dù bạn **không** ghi `final`. Đây là quy tắc trực tiếp của ngôn ngữ.
- Trong **single-catch**, muốn ngăn gán lại có thể ghi `final`; nếu không ghi và không gán thì biến vẫn effectively final.
- Cả hai hình thức đều có thể ném lại lỗi; việc cho phép về mặt biên dịch vẫn phụ thuộc hợp đồng checked exception.
- `throw ex;` không tạo wrapper, nên không tự bổ sung thông điệp/ngữ cảnh. Nếu cần đổi loại ngoại lệ, tạo đối tượng mới có `cause` và xử lý hợp đồng theo kiểu ngoại lệ mới.

### Multi-catch không thay đổi kiểu runtime

Nếu `risky` ném `SQLException`, tham số `ex` ở multi-catch tham chiếu tới một **đối tượng `SQLException` thực tế**. `ex.getClass().getSimpleName()` trả về `SQLException`, dù handler được chia sẻ với `IOException`.

Không nên nhầm kiểu tĩnh chung của tham số với việc chuyển đổi đối tượng lúc chạy. Việc `ex` là ngầm `final` cũng chỉ hạn chế thay đổi **tham chiếu**, không biến ngoại lệ thành bất biến.

## 15. Những lỗi lập trình thường gặp

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ mọi tham số `catch` đều tự động `final` | Single-catch không có `final` cho phép gán lại | Phân biệt single-catch và multi-catch |
| Nghĩ multi-catch có thể gán lại `ex` vì không viết `final` | Tham số multi-catch ngầm `final` | Tạo biến mới nếu cần xử lý giá trị khác |
| Gán `ex = new Exception(...)` rồi `throw ex` trong handler `catch (Exception)` và chỉ khai báo `throws IOException, SQLException` | Mất *effectively final*, làm mất precise rethrow | Không gán lại hoặc dùng hợp đồng checked phù hợp |
| Bắt lỗi rồi chỉ gán `ex` sang đối tượng mới | Không ném ngoại lệ mới cho caller | `throw new SomeException("context", ex)` nếu muốn chuyển lỗi |
| Dùng biến `catch` đã gán lại trong lambda | Biến không còn *effectively final* | Giữ tham số không gán lại hoặc capture giá trị khác |
| Hiểu `final` khiến đối tượng `Throwable` bất biến | `final` chỉ khóa việc gán lại tham chiếu | Phân biệt tham chiếu và trạng thái đối tượng |
| Dùng `catch (IOException | FileNotFoundException)` | Có quan hệ cha/con giữa hai lựa chọn | Dùng `catch (IOException)` hoặc handler riêng |
| Đặt `catch (Exception)` trước handler subtype | Handler sau bị che khuất | Đặt kiểu cụ thể trước kiểu cha |
| Nghĩ `throw ex;` tự tạo stack trace/cause mới | Đây là ném lại cùng đối tượng | Tạo wrapper có cause nếu thật sự cần thêm ngữ cảnh |
| Bắt `Exception` ở mọi tầng chỉ để ghi log rồi ném | Tạo nhiễu, che ranh giới trách nhiệm | Bắt ở tầng có hành động hữu ích |

### Tránh nhầm “đã bị bắt” với “được xử lý xong”

Một `catch` có thể làm ba việc rất khác nhau:

```java
// A. Phục hồi có chủ đích và hoàn tất bình thường.
catch (KnownRecoverableException ex) {
    useVerifiedFallback();
}

// B. Ném lại cùng đối tượng.
catch (KnownRecoverableException ex) {
    throw ex;
}

// C. Bọc với ngữ cảnh mới và giữ nguyên nhân.
catch (KnownRecoverableException ex) {
    throw new HigherLevelException("operation failed", ex);
}
```

Các đoạn trên **chỉ minh họa**, cần định nghĩa các kiểu/phương thức cho ứng dụng thực; không phải tệp Java độc lập. Ở trường hợp A, caller không nhận ngoại lệ nếu fallback thành công. Ở B, caller nhận cùng đối tượng. Ở C, caller nhận đối tượng mới và có thể truy nguyên theo `getCause()`.

Sự lựa chọn này liên quan **chính sách lỗi và ranh giới xử lý**, không phải do tham số `catch` có `final` hay không.

## 16. Checklist khi dùng `final` và precise rethrow

Khi đọc hoặc sửa một khối `catch`, hãy kiểm tra:

1. **Đây là single-catch hay multi-catch?** Multi-catch có tham số ngầm `final`; single-catch chỉ `final` nếu khai báo tường minh.
2. **Có gán lại biến ngoại lệ không?** Tìm `ex = ...`, kể cả trong nhánh điều kiện. Nếu có, single-catch không còn *effectively final*.
3. **Có lambda/lớp ẩn danh capture tham số này không?** Biến capture phải `final` hoặc *effectively final*.
4. **Có `throw ex;` trong handler kiểu rộng không?** Nếu có, kiểm tra precise rethrow và các loại checked exception được phân tích từ phần `try`.
5. **Chữ ký `throws` đã bao phủ đúng các checked exception chưa?** Không tự ý mở thành `throws Exception` khi phần `try` thực chất chỉ có `IOException` và `SQLException`.
6. **Ngoại lệ nào đang được ném thật?** Gán lại tham số không biến đổi đối tượng cũ; ném lại có nghĩa khác với tạo wrapper.
7. **Có cần giữ `cause` không?** Khi chuyển sang ngoại lệ mới, truyền lỗi gốc qua constructor nhận cause nếu phù hợp.
8. **Multi-catch có các loại cha/con trùng nhau không?** Nếu có, tách hoặc rút gọn các lựa chọn.
9. **Có thể làm đơn giản hơn không?** Nếu handler chỉ `throw ex;` và không có công việc có ý nghĩa, để ngoại lệ tự lan truyền thường rõ hơn.
10. **Đã thử biên dịch các đường lỗi quan trọng chưa?** Đặc biệt các ví dụ gán lại tham số và phương thức khai báo checked exception hẹp.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `catch (IOException ex)` có cho phép `ex = new IOException("other");` không?

**Có**, nếu đây là single-catch và tham số không khai báo `final`. Tuy nhiên, phép gán khiến `ex` không còn *effectively final*, và không tự ném ngoại lệ mới.

**Câu 2.** `catch (IOException | SQLException ex)` có cho phép gán lại `ex` không?

**Không.** Multi-catch có tham số ngầm `final`.

**Câu 3.** `catch (Exception ex) { throw ex; }` có nhất thiết buộc phương thức khai báo `throws Exception` không?

**Không.** Khi `ex` không bị gán lại và các điều kiện precise rethrow thỏa mãn, trình biên dịch có thể xác định tập checked exception hẹp hơn từ phần `try`, ví dụ `IOException` và `SQLException`.

**Câu 4.** Nếu viết `ex = new Exception("new"); throw ex;` trong handler `catch (Exception ex)` thì sao?

Tham số không còn *effectively final*. Với một phương thức chỉ `throws IOException, SQLException`, lỗi kiểu checked `Exception` rộng hơn có thể gây lỗi biên dịch. Muốn ném đối tượng mới thì cần thiết kế hợp đồng phù hợp, chứ không dựa vào precise rethrow.

**Câu 5.** Một tham số `catch` không có từ khóa `final` nhưng không hề bị gán lại có thể được lambda sử dụng không?

**Có.** Nó là *effectively final* theo quy tắc của Java.

**Câu 6.** `final IOException ex` có ngăn code gọi `ex.getMessage()` hoặc `throw ex;` không?

**Không.** `final` cấm gán lại biến `ex`, không cấm đọc tham chiếu hoặc ném cùng đối tượng.

**Câu 7.** Gán `ex = new IOException("context", original)` có tự làm caller nhận lỗi mới không?

**Không.** Nếu handler kết thúc bình thường mà không `throw`, caller không nhận ngoại lệ mới chỉ vì có phép gán.

**Câu 8.** Multi-catch có thể chứa `NumberFormatException | IllegalArgumentException` không?

**Không.** Hai lựa chọn có quan hệ kế thừa; `NumberFormatException` là lớp con của `IllegalArgumentException`.

**Kết luận:** tham số **single-catch** có thể được gán lại nếu không khai báo `final`; tham số **multi-catch** thì ngầm `final`. Một tham số single-catch **không bị gán lại** là *effectively final*, có thể được lambda capture và giúp trình biên dịch áp dụng **precise rethrow** trong những tình huống thích hợp. Khi cần chuyển lỗi, hãy chọn hành động rõ ràng—xử lý, ném lại hoặc bọc có `cause`—thay vì gán lại biến ngoại lệ một cách khó hiểu.