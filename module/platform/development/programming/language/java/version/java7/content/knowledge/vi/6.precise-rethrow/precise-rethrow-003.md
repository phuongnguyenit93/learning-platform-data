# Vai trò của `final` hoặc biến `catch` không bị gán lại khi ném lại ngoại lệ trong Java

## 1. Bối cảnh: ném lại ngoại lệ mà không mở rộng `throws`

Một tình huống phổ biến là phương thức cần ghi log rồi chuyển chính ngoại lệ vừa bắt được cho tầng gọi xử lý tiếp:

```java
try {
    readFile();
    executeQuery();
} catch (Exception ex) {
    logError(ex);
    throw ex;
}
```

Đây là **đoạn minh họa trong một phương thức**: `readFile`, `executeQuery` và `logError` đại diện cho những hàm do ứng dụng định nghĩa, không phải API tiêu chuẩn của Java. Hãy giả sử `readFile()` có thể ném `IOException`, còn `executeQuery()` có thể ném `SQLException`.

Nhìn kiểu tham số `catch` là `Exception`, người mới học dễ cho rằng phương thức phải khai báo `throws Exception`. Tuy nhiên, từ **Java 7**, Java hỗ trợ **precise rethrow**: trong những điều kiện nhất định, trình biên dịch xác định được các loại checked exception hẹp hơn mà `throw ex;` có thể ném lại. Phương thức có thể khai báo:

```java
throws IOException, SQLException
```

thay vì phải khai báo `throws Exception` quá rộng.

**Điều kiện then chốt của bài:** biến tham số `catch` được ném lại phải **được khai báo `final` hoặc không bị gán lại sau khi được tạo** (*effectively final*). Điều này cho phép trình biên dịch tin rằng biến `ex` vẫn trỏ đến chính ngoại lệ mà khối `catch` đã bắt, chứ không bị thay bằng một đối tượng ngoại lệ thuộc kiểu khác.

Tính năng precise rethrow của Java 7 vẫn hoạt động trên Java 17+ và những phiên bản Java hiện đại. Nó là quy tắc ngôn ngữ và kiểm tra kiểu tại thời điểm biên dịch, **không phải** một cơ chế runtime đặc biệt hay API đã lỗi thời.

## 2. Phân biệt `final` và *effectively final*

### 2.1. Tham số `catch` được khai báo `final`

```java
try {
    readFile();
} catch (final Exception ex) {
    System.err.println(ex.getMessage());
    throw ex;
}
```

Từ khóa `final` có nghĩa là: trong phạm vi `catch`, **không thể gán lại tham chiếu `ex`**. Nếu thử viết `ex = new Exception("other");`, trình biên dịch sẽ từ chối ngay vì `ex` là tham số `final`.

### 2.2. Tham số không ghi `final` nhưng không hề bị gán lại

```java
try {
    readFile();
} catch (Exception ex) {
    System.err.println(ex.getMessage());
    throw ex;
}
```

Ở đây không có từ khóa `final`, nhưng `ex` **không bị gán lại ở bất kỳ vị trí nào trong `catch`**. Với việc ném lại, Java áp dụng quy tắc tương đương *effectively final* và vẫn có thể suy luận các loại checked exception cụ thể từ khối `try`.

Đây là điểm rất quan trọng: **không bắt buộc phải viết `final` để precise rethrow hoạt động**. Cả hai cách có thể tạo ra cùng hợp đồng `throws`.

| Trường hợp | Có được gán lại `ex`? | Có thể dùng precise rethrow với `throw ex;`? |
| --- | --- | --- |
| `catch (final Exception ex)` | Không, compiler cấm | Có, nếu các điều kiện khác được đáp ứng |
| `catch (Exception ex)` và không có phép gán cho `ex` | Về cú pháp có thể, nhưng thực tế không gán | Có |
| `catch (Exception ex)` và có phép gán `ex = ...` | Có | Không theo quy tắc ném lại tham số không bị gán lại |
| `catch (IOException | SQLException ex)` | Không, tham số multi-catch ngầm `final` | Có thể ném lại các kiểu trong nhánh multi-catch |

**Lưu ý:** *Effectively final* là tính chất do compiler xác định dựa trên cách biến được sử dụng. Không phải mọi tham số không khai báo `final` đều tự động là effectively final; chỉ cần một phép gán lại có thể làm mất tính chất này.

## 3. Vì sao không gán lại giúp suy luận ngoại lệ chính xác?

Xét hai phương thức sau:

```java
static void read(boolean fail) throws java.io.IOException {
    if (fail) {
        throw new java.io.IOException("file");
    }
}

static void query(boolean fail) throws java.sql.SQLException {
    if (fail) {
        throw new java.sql.SQLException("database");
    }
}
```

Hai phương thức được gọi trong `try`:

```java
static void process(boolean fileFail, boolean dbFail)
        throws java.io.IOException, java.sql.SQLException {
    try {
        read(fileFail);
        query(dbFail);
    } catch (Exception ex) {
        System.err.println(ex.getClass().getSimpleName());
        throw ex;
    }
}
```

Đây là các **phương thức cùng thuộc một lớp**; mã chương trình chạy độc lập được trình bày ở mục 4.

Phân tích của compiler được hiểu theo chuỗi sau:

1. Lệnh `read(...)` có thể ném checked exception `IOException` theo chữ ký.
2. Lệnh `query(...)` có thể ném checked exception `SQLException` theo chữ ký.
3. `catch (Exception ex)` có thể bắt cả hai loại vì chúng kế thừa `Exception`.
4. `ex` không bị gán lại trong `catch`, nên `throw ex;` ném lại **đối tượng ban đầu được bắt**.
5. Vì vậy, các checked exception cần khai báo ở `process` là `IOException` và `SQLException`, không cần `Exception` chung chung.

Có thể hình dung:

```text
           +-- read(...) -----> IOException ------+
try -------|                                      +--> catch (Exception ex)
           +-- query(...) ----> SQLException -----+            |
                                                              |
                                                 ex không bị gán lại
                                                              |
                                                          throw ex
                                                              |
                                                 checked: IOException
                                                          SQLException
```

Đây là **phân tích tĩnh**. Compiler không chạy `read` hoặc `query` để quan sát lỗi. Nó căn cứ vào các biểu thức `throw`, chữ ký `throws` của phương thức/constructor, đường đi điều khiển và các nhánh `catch` có thể bắt lỗi. Trong mỗi lần thực thi, có thể không xảy ra lỗi nào hoặc chỉ xảy ra một lỗi; điều đó không làm thay đổi những loại checked exception mà phương thức phải cho phép.

Các `RuntimeException` có thể xuất hiện và cũng có thể bị `catch (Exception ex)` bắt, nhưng **unchecked exception không bắt buộc liệt kê trong `throws`**. Quy tắc precise rethrow thu hẹp hợp đồng **checked exception**, không chứng minh rằng chương trình sẽ không có lỗi runtime.

## 4. Ví dụ Java 17+ hoàn chỉnh: viết `final` hoặc bỏ `final`

Ví dụ này có hai phương thức chỉ khác nhau ở cách khai báo tham số `catch`. Cả hai đều chỉ khai báo hai checked exception cụ thể và ném lại chính ngoại lệ gốc.

Tạo tệp **`FinalCatchDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class FinalCatchDemo {

    static void doIO(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("disk");
        }
    }

    static void doDB(boolean fail) throws SQLException {
        if (fail) {
            throw new SQLException("db");
        }
    }

    // Không có final; ex vẫn là effectively final.
    static void withEffectiveFinal(boolean fileFail, boolean dbFail)
            throws IOException, SQLException {
        try {
            doIO(fileFail);
            doDB(dbFail);
        } catch (Exception ex) {
            System.out.println("non-final: "
                    + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    // Viết final tường minh để compiler cấm mọi phép gán lại.
    static void withFinal(boolean fileFail, boolean dbFail)
            throws IOException, SQLException {
        try {
            doIO(fileFail);
            doDB(dbFail);
        } catch (final Exception ex) {
            System.out.println("final: "
                    + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            withEffectiveFinal(true, false);
        } catch (IOException ex) {
            System.out.println("handled IOException");
        } catch (SQLException ex) {
            System.out.println("handled SQLException");
        }

        try {
            withFinal(false, true);
        } catch (IOException ex) {
            System.out.println("handled IOException");
        } catch (SQLException ex) {
            System.out.println("handled SQLException");
        }

        try {
            withEffectiveFinal(false, false);
            System.out.println("success");
        } catch (IOException | SQLException ex) {
            System.out.println("unexpected");
        }
    }
}
```

Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 FinalCatchDemo.java
java FinalCatchDemo
```

**Stdout:**

```text
non-final: IOException
handled IOException
final: SQLException
handled SQLException
success
```

Giải thích:

- Lượt 1: `doIO(true)` ném `IOException`, bị bắt bởi `catch (Exception ex)` trong `withEffectiveFinal`; biến `ex` không hề bị gán lại nên `throw ex` hợp lệ với `throws IOException, SQLException`. `main` bắt được `IOException`.
- Lượt 2: `doIO(false)` thành công, `doDB(true)` ném `SQLException`. `withFinal` khai báo `catch (final Exception ex)`, ghi thông tin rồi ném lại. `main` bắt được `SQLException`.
- Lượt 3: cả hai phương thức thao tác đều thành công; `withEffectiveFinal` không vào `catch` và in `success` ở `main`.
- Hai phương thức đều giữ **cùng hợp đồng checked exception**, dù một phương thức có `final` tường minh còn phương thức kia thì không.

Ở đây `catch (IOException | SQLException ex)` ở `main` là **multi-catch**, cho phép xử lý hai kiểu cùng một nhánh. Cú pháp multi-catch và precise rethrow đều được hỗ trợ từ Java 7 và vẫn có hiệu lực.

## 5. Điều gì xảy ra khi gán lại tham số `catch`?

Xét ví dụ **cố ý sai, không biên dịch**:

```java
// Đặt trong cùng lớp có doIO và doDB ở ví dụ trên.
static void badProcess(boolean fileFail, boolean dbFail)
        throws java.io.IOException, java.sql.SQLException {
    try {
        doIO(fileFail);
        doDB(dbFail);
    } catch (Exception ex) {
        ex = new Exception("replacement");
        throw ex; // Lỗi: checked Exception chưa được khai báo.
    }
}
```

Khi `ex = new Exception("replacement")`, tham chiếu `ex` không còn nhất thiết là ngoại lệ mà `try` đã ném ra. Vì `throw ex` lúc này được xét theo kiểu khai báo `Exception`, chữ ký chỉ có `IOException, SQLException` **không còn đủ**. Đây chính là tình huống mà quy tắc precise rethrow không được áp dụng.

Ngay cả phép gán tưởng như vô hại cũng làm mất điều kiện:

```java
// Cố ý sai nếu chữ ký chỉ throws IOException.
static void alsoBad() throws java.io.IOException {
    try {
        throw new java.io.IOException("read");
    } catch (Exception ex) {
        ex = ex; // Vẫn là một phép gán lại cho tham số catch.
        throw ex; // Không còn được suy luận hẹp: phải xét Exception.
    }
}
```

Compiler xem xét **việc biến có bị gán lại hay không**, chứ không đoán rằng phép gán `ex = ex` giữ cùng đối tượng và cho phép ngoại lệ vẫn hẹp. Ví dụ này cũng minh họa rằng chỉ cần gán lại ở trong khối `catch` có thể làm thay đổi kiểm tra kiểu khi biên dịch.

Nếu viết `catch (final Exception ex)`, phép gán `ex = ...` bị cấm ngay từ đầu:

```java
// Cố ý không biên dịch.
try {
    doIO(true);
} catch (final Exception ex) {
    // ex = new Exception("replacement"); // Lỗi: không thể gán biến final.
    throw ex;
}
```

Tại sao không nên "sửa nhanh" bằng cách mở rộng chữ ký thành `throws Exception`? Vì như vậy API buộc các tầng gọi xử lý một loại ngoại lệ checked rộng hơn, dù nghiệp vụ thực tế chỉ dự kiến `IOException` và `SQLException`. Nếu mục tiêu là log rồi ném lại, **giữ nguyên tham số bắt được** là giải pháp đúng hơn.

## 6. `final` của tham chiếu không có nghĩa đối tượng ngoại lệ bất biến

`final` chỉ bảo vệ **biến tham chiếu** khỏi việc trỏ tới đối tượng khác. Nó không tự làm cho đối tượng `Throwable` bất biến và không thay đổi nội dung đối tượng đã được bắt.

Ví dụ:

```java
try {
    doIO(true);
} catch (final java.io.IOException ex) {
    String message = ex.getMessage();
    System.err.println(message);
    throw ex;
}
```

Có thể đọc thuộc tính, gọi `getMessage()`, `getCause()`, `getSuppressed()`, truyền `ex` cho hàm ghi log hoặc kiểm tra kiểu thực tế. Các thao tác này **không gán lại biến `ex`**, nên không làm mất điều kiện về tham số final/effectively final.

Mặt khác, đối tượng `Throwable` có một số phương thức thay đổi trạng thái như `addSuppressed(...)` hoặc `setStackTrace(...)`. Từ khóa `final` **không ngăn** các lời gọi như vậy; tuy nhiên, không nên tùy tiện sửa dấu vết lỗi hoặc thêm thông tin sai. Nếu cần bổ sung ngữ cảnh, hãy ghi log đúng mức hoặc tạo ngoại lệ bọc lỗi theo hợp đồng API.

Một điểm nữa: `throw ex;` ném lại **chính đối tượng `ex`**, không tạo bản sao. Nó giữ loại ngoại lệ và thông tin nguyên nhân ban đầu (mặc dù thao tác ném lại có thể ảnh hưởng cách stack trace được quan sát theo ngữ cảnh runtime). Không thay `throw ex` bằng `throw new Exception(ex)` trừ khi thật sự muốn tạo một lớp ngoại lệ mới và chấp nhận thay đổi loại checked exception.

## 7. Biến bí danh `final` không thay thế được tham số `catch`

Đây là một khác biệt dễ bỏ sót. Giả sử `ex` là tham số `catch` không bị gán lại, nhưng ta sao chép tham chiếu sang một biến `final` cục bộ khác:

```java
// Cố ý không biên dịch với chữ ký throws IOException.
static void aliasDoesNotHelp() throws java.io.IOException {
    try {
        throw new java.io.IOException("file");
    } catch (Exception ex) {
        final Exception alias = ex;
        throw alias; // Lỗi: alias có kiểu khai báo Exception.
    }
}
```

Biến `alias` không bị gán lại, nhưng nó **không phải tham số `catch` đang được ném lại**. Quy tắc precise rethrow dành cho một biểu thức ném lại chính tham số `catch` trong điều kiện thích hợp; không có nghĩa mọi biến `final Exception` đều được suy luận là `IOException`.

Cách đúng khi mục đích chỉ là ghi log rồi chuyển tiếp:

```java
static void forwardOriginal() throws java.io.IOException {
    try {
        throw new java.io.IOException("file");
    } catch (Exception ex) {
        System.err.println(ex.getMessage());
        throw ex; // ex là tham số catch, không bị gán lại.
    }
}
```

Trường hợp trên khác với ném một đối tượng mới:

```java
// Cố ý không biên dịch nếu phương thức chỉ throws IOException.
static void newExceptionIsDifferent() throws java.io.IOException {
    try {
        throw new java.io.IOException("file");
    } catch (Exception ex) {
        throw new Exception("wrapped", ex); // Exception mới, kiểu checked rộng.
    }
}
```

**Nhớ rõ ba yếu tố:** tham số của `catch`, không bị gán lại, và biểu thức `throw` ném lại chính tham số đó. Chỉ có `final` trên một biến không đủ bảo đảm kiểu ngoại lệ ném ra sẽ được thu hẹp.

## 8. Liên hệ với multi-catch

Từ Java 7, nếu hai ngoại lệ cần xử lý giống hệt nhau, có thể viết:

```java
static void withMultiCatch(boolean fileFail, boolean dbFail)
        throws java.io.IOException, java.sql.SQLException {
    try {
        doIO(fileFail);
        doDB(dbFail);
    } catch (java.io.IOException | java.sql.SQLException ex) {
        System.err.println("failed: " + ex.getClass().getSimpleName());
        throw ex;
    }
}
```

Đây là đoạn phương thức thuộc cùng lớp với `doIO`/`doDB` ở mục 4. `catch (IOException | SQLException ex)` bắt **một trong hai kiểu** và dùng chung một nhánh xử lý. Tham số `ex` của multi-catch **ngầm là `final`**, nên gán lại bị cấm:

```java
// Ví dụ lỗi biên dịch, chỉ minh họa bên trong multi-catch.
// ex = new IOException("replacement"); // Không được gán lại.
```

Sự khác nhau:

- `catch (Exception ex)` có phạm vi bắt rộng (có thể bắt nhiều loại `Exception`, kể cả `RuntimeException`); precise rethrow giúp thu hẹp những checked exception cần khai báo **nếu không gán lại ex**.
- `catch (IOException | SQLException ex)` nêu rõ chính hai loại cần bắt; tham số ngầm `final` và không thể thay bằng một ngoại lệ tùy ý.
- `catch (IOException ex)` và `catch (SQLException ex)` tách riêng thích hợp khi từng lỗi cần **khả năng phục hồi khác nhau** thay vì cùng ghi log rồi ném lại.

Không thể viết `catch (IOException | Exception ex)` vì một kiểu bị kiểu kia bao trùm; không thể đặt `catch (Exception ex)` trước `catch (IOException ex)` trong chuỗi nhánh vì nhánh hẹp sau đó không thể tiếp cận. Cấu trúc `catch` cần đáp ứng quan hệ kế thừa và khả năng ngoại lệ phát sinh từ `try`.

## 9. Vì sao kiểu checked phải dựa trên `try`, không phải lần chạy?

Precise rethrow hoạt động nhờ thông tin compile-time. Ví dụ:

```java
static void checkedApi() throws java.io.IOException {
    // Có thể thành công ở lần chạy hiện tại.
}
```

Ở vị trí gọi `checkedApi()`, compiler **vẫn xét khả năng `IOException`** dựa trên chữ ký `throws IOException`. Không thể kết luận vì lần chạy thử không gặp lỗi nên việc ném lại sẽ không cần khai báo checked exception.

Khi một phương thức bên trong `try` công khai `throws Exception`, compiler cũng không thể tự đổi hợp đồng thành `throws IOException` chỉ vì implementation hiện tại luôn ném `IOException`. Một chữ ký quá rộng ở API được gọi vẫn có thể khiến nơi gọi cần hợp đồng rộng hơn.

Ví dụ khác, trong `try-with-resources`, ngoại lệ checked từ **khởi tạo**, **thân `try`** và **đóng tài nguyên** có thể tham gia phân tích. Với tài nguyên được khai báo kiểu `AutoCloseable`, `close()` có thể khai báo `throws Exception`; với các kiểu cụ thể như nhiều luồng vào/ra, hợp đồng có thể hẹp hơn như `IOException`. Tính final/effectively final của tham số `catch` không làm biến mất bất kỳ nguồn checked exception nào mà compiler phải tính đến.

**Đừng đồng nhất:**

1. Loại ngoại lệ thực sự được ném ở một lần chạy.
2. Loại ngoại lệ compiler phân tích là có thể thoát khỏi `try`.
3. Kiểu tĩnh của biến `catch`.
4. Các loại checked cần khai báo khi **ném lại** một tham số `catch` không bị gán lại.

Bốn điều này liên quan nhưng không đồng nhất. Precise rethrow cho phép dùng kết quả phân tích thứ hai để tránh bị giới hạn quá rộng bởi kiểu `Exception` thứ ba.

## 10. Khi nào nên viết `final` một cách tường minh?

Cả hai cách sau đều hợp lệ và có thể đạt cùng lợi ích precise rethrow:

```java
catch (Exception ex) {
    log(ex);
    throw ex;
}
```

```java
catch (final Exception ex) {
    log(ex);
    throw ex;
}
```

Trong ví dụ này, `log` là phương thức ghi log do ứng dụng định nghĩa, không phải phương thức dựng sẵn của Java.

**Chọn `final` tường minh khi:**

- Muốn biểu đạt ý định **không thay thế ngoại lệ gốc** ngay ở chữ ký `catch`.
- Muốn compiler chặn một thay đổi trong tương lai vô tình thêm `ex = ...`.
- Nhóm phát triển có quy ước sử dụng `final` cho các tham số tham chiếu không được gán lại.

**Không bắt buộc thêm `final` khi:**

- `catch` ngắn, rõ ràng và `ex` không bị gán lại.
- Nhóm ưu tiên ít từ khóa hơn nhưng vẫn giữ biến effectively final.
- Đã dùng multi-catch, trong đó tham số vốn ngầm `final`.

Đối với quy tắc precise rethrow, **hành vi quan trọng hơn phong cách**: phải ném lại tham số gốc không bị gán lại, và giữ hợp đồng `throws` đúng với ngoại lệ có thể phát sinh.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ phải có `final` mới được precise rethrow | Thêm từ khóa không cần thiết hoặc hiểu sai Java | `catch (Exception ex)` không gán lại cũng đủ điều kiện |
| Gán `ex = new Exception(...)` rồi `throw ex` | Không còn điều kiện suy luận ngoại lệ hẹp | Không gán lại; ném lại chính `ex` |
| Viết `ex = ex` và cho rằng không thay đổi gì | Vẫn mất tính effectively final | Bỏ phép gán |
| Gán vào biến `final Exception alias` rồi `throw alias` | Biến bí danh không phải tham số `catch` được precise rethrow | Dùng `throw ex` nếu cần ném lại gốc |
| Tưởng `final` làm đối tượng `Throwable` bất biến | Vẫn có API thay đổi trạng thái đối tượng | Hiểu `final` chỉ cấm gán lại tham chiếu |
| Cho rằng `catch (Exception ex)` luôn đòi `throws Exception` | Hợp đồng checked exception bị mở rộng quá mức | Giữ `ex` không bị gán lại và dựa vào precise rethrow |
| Bọc mọi lỗi thành `new Exception(ex)` | Đổi loại checked và có thể che ý nghĩa lỗi | Chỉ chuyển đổi lỗi có chủ đích, giữ `cause` |
| Nghĩ không thấy lỗi khi chạy nên `throws` không cần | Bỏ sót nguồn lỗi trong đường chạy khác | Xem chữ ký API và phân tích tĩnh |
| Gán lại biến trong multi-catch | Không biên dịch | Tham số multi-catch ngầm `final` |
| Bắt và nuốt mọi ngoại lệ `Exception` | Che giấu sự cố hoặc cho phép hệ thống tiếp tục sai | Xử lý đúng tầng hoặc ném lại; cân nhắc phạm vi bắt |

Precise rethrow giúp giữ hợp đồng của API chính xác, nhưng **không làm mọi `catch (Exception)` trở thành lựa chọn tốt**. Khi từng loại lỗi cần cách xử lý riêng, hãy bắt loại cụ thể hoặc sử dụng multi-catch thích hợp. Không nên dùng `catch (Exception)` chỉ để che lỗi lập trình; nó cũng bắt các `RuntimeException`, dù không bắt những `Error`.

## 12. Bài tập và đáp án

### Bài 1. Có cần `final` không?

```java
static void exercise() throws java.io.IOException {
    try {
        throw new java.io.IOException("fail");
    } catch (Exception ex) {
        System.out.println(ex.getMessage());
        throw ex;
    }
}
```

**Câu hỏi:** Đoạn này có biên dịch được với `throws IOException` không? Có bắt buộc đổi thành `catch (final Exception ex)` không?

**Đáp án:** Có thể biên dịch với `throws IOException` nhờ precise rethrow, vì `ex` là tham số `catch` không bị gán lại. Không cần thêm từ khóa `final`.

### Bài 2. Phép gán nào làm mất điều kiện?

```java
catch (Exception ex) {
    Exception copy = ex;
    System.err.println(copy);
    throw ex;
}
```

**Câu hỏi:** Việc gán `copy = ex` có làm `ex` mất effectively final không?

**Đáp án:** Không. Lệnh này khởi tạo một biến **khác** từ `ex` chứ không gán lại tham số `ex`. Lệnh cuối vẫn ném chính `ex`. Trái lại, nếu viết `ex = copy;`, dù cùng đối tượng, `ex` bị gán lại và không còn điều kiện precise rethrow.

### Bài 3. Vì sao biến bí danh không đủ?

```java
catch (Exception ex) {
    final Exception alias = ex;
    throw alias;
}
```

**Câu hỏi:** Nếu `try` chỉ có `IOException` checked, có thể luôn giữ `throws IOException` không?

**Đáp án:** Không trong trường hợp này. `alias` có kiểu tĩnh `Exception` và không phải tham số `catch` được ném lại trực tiếp; cần xử lý hoặc khai báo `Exception`, hoặc sửa thành `throw ex;`.

### Bài 4. Hai lỗi checked khác nhau

Giả sử `read() throws IOException` và `query() throws SQLException` được gọi trong `try`; `catch (final Exception ex)` chỉ ghi log và `throw ex;`.

**Câu hỏi:** Phương thức cần khai báo gì? Có cần `throws Exception` không?

**Đáp án:** `throws IOException, SQLException`, không cần `throws Exception`. Dù `ex` có kiểu khai báo là `Exception`, precise rethrow có thể dựa vào các loại checked exception có thể phát sinh từ `try`.

### Bài 5. Multi-catch và `final`

**Câu hỏi:** Trong `catch (IOException | SQLException ex)`, có thể thêm lệnh `ex = new IOException("x");` rồi ném lại không?

**Đáp án:** Không. Tham số multi-catch là ngầm `final` và không được gán lại.

**Ghi nhớ:** Trong Java 7+ đến Java hiện đại, khi `catch` bắt ngoại lệ bằng tham số `final` hoặc **không bị gán lại**, câu lệnh **`throw ex;`** có thể hưởng cơ chế **precise rethrow** để giữ các kiểu checked exception cụ thể đã được phân tích từ `try`. Hãy ném lại **chính tham số `catch`**; thêm `final` nếu muốn cấm gán lại tường minh, nhưng không coi nó là bắt buộc.