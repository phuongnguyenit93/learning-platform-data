# Giới hạn thành viên được truy cập qua tham số multi-catch trong Java

## 1. Mục tiêu học tập

Multi-catch cho phép xử lý nhiều loại ngoại lệ trong **một** khối `catch`:

```java
try {
    performOperation();
} catch (java.io.IOException | java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

Đây là đoạn minh họa bên trong một phương thức; `performOperation()` cần được định nghĩa và có khả năng ném các kiểu checked exception được bắt. Điểm quan trọng: dù tại thời điểm chạy `failure` là một đối tượng `IOException` **hoặc** `SQLException`, trình biên dịch không tự cho phép mọi phương thức riêng của hai lớp đó trên cùng biến `failure`.

Sau bài này, bạn có thể:

- Hiểu kiểu của tham số ngoại lệ trong `catch (A | B e)` được xác định theo **least upper bound** (giới hạn trên chung gần nhất theo quy tắc hệ thống kiểu Java).
- Phân biệt **kiểu thực tế của đối tượng tại runtime** với **kiểu tĩnh của biểu thức `e` tại compile time**.
- Nhận biết các thành viên được truy cập trực tiếp qua `e`, các thành viên riêng của từng nhánh và quy tắc access modifier.
- Dùng `instanceof` hoặc pattern matching cho `instanceof` trong Java 17 để truy cập API riêng sau khi kiểm tra kiểu.
- Hiểu vì sao không thể gán lại tham số multi-catch và cách rethrow giữ thông tin ngoại lệ.
- Nhận biết lỗi thường gặp với kiểu ngoại lệ cha–con trong multi-catch, phương thức overload và checked exception.
- Viết các chương trình Java 17+ biên dịch được với kết quả quan sát xác định.

Trọng tâm bài là **giới hạn thành viên có thể truy cập qua tham số multi-catch**. Các quy tắc liên quan đến rethrow, checked exception và phạm vi biến được trình bày để giải thích đầy đủ cơ chế này.

## 2. Multi-catch khác nhiều `catch` riêng ở điểm nào?

Cách viết hai handler có cùng logic:

```java
try {
    readOrQuery();
} catch (java.io.IOException failure) {
    System.out.println(failure.getMessage());
} catch (java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

Có thể gộp thành:

```java
try {
    readOrQuery();
} catch (java.io.IOException | java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

Cả hai là **mảnh mã minh họa**, đòi hỏi `readOrQuery()` phù hợp. Dấu `|` ở đây là cú pháp **multi-catch** (Java 7+), không phải toán tử OR logic trên biến và không tạo một kiểu union thông thường để sử dụng ở mọi nơi trong Java.

Ở cách thứ nhất, mỗi handler có một tham số có kiểu cụ thể: `IOException` hoặc `SQLException`. Ở cách thứ hai, **chỉ có một biến `failure`** trong thân handler. Biến đó phải dùng an toàn cho mọi kiểu mà handler có thể nhận.

### Không thể suy ra “cùng tên biến” nghĩa là “cùng kiểu cụ thể”

`IOException` và `SQLException` đều kế thừa `Exception`, nhưng có những phương thức riêng:

- `SQLException.getSQLState()` trả mã SQLSTATE, nếu có.
- `SQLException.getErrorCode()` trả mã lỗi đặc thù nhà cung cấp.
- `SQLException.getNextException()` theo chuỗi lỗi SQL.
- `IOException` không khai báo các phương thức `getSQLState()`, `getErrorCode()` hay `getNextException()`.

Do đó, câu lệnh `failure.getMessage()` hợp lệ trong multi-catch vì `getMessage()` thuộc `Throwable`, còn `failure.getSQLState()` không hợp lệ nếu chưa thu hẹp kiểu.

## 3. Kiểu tĩnh của tham số multi-catch

Với cú pháp:

```java
catch (TypeA | TypeB | TypeC ex) {
    // Trình biên dịch phải xác định kiểu của ex.
}
```

Java xác định kiểu của tham số theo phép **least upper bound** — thường viết `lub(TypeA, TypeB, TypeC)`. Ý tưởng là tìm giới hạn kiểu chung đủ để biểu diễn an toàn tất cả các lựa chọn ngoại lệ.

Trong ví dụ:

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getClass().getSimpleName());
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause());
}
```

Tham số `ex` có thể trỏ đến một đối tượng của bất kỳ lựa chọn nào tại runtime. Những phương thức ở trên hợp lệ vì đều là thành viên của `Object` hoặc `Throwable` trên hệ phân cấp chung.

**Chú ý về độ chính xác:** `lub` trong Java có thể là kiểu giao (*intersection type*) gồm một lớp chung và những interface phù hợp. Vì thế không nên khẳng định **mọi** multi-catch đều có kiểu tĩnh chính xác là `Exception`. Đối với việc gọi thành viên, hãy xem thành viên đó có mặt trong kiểu tĩnh mà compiler suy ra và có **truy cập được** tại vị trí gọi hay không.

Một mô hình tư duy hữu ích:

```text
IOException -----\
                   > tham số ex của catch
SQLException ----/   |
                       v
          các thành viên hợp lệ từ giới hạn kiểu chung
          (vd. getMessage(), getCause(), printStackTrace())
```

**Không phải:** trình biên dịch chấp nhận mọi thành viên của `IOException` **cộng với** mọi thành viên của `SQLException`. Điều đó sẽ không an toàn vì lúc chạy đối tượng có thể chỉ thuộc một nhánh.

### 3.1. Runtime type vẫn được giữ nguyên

Dù biểu thức `ex` có kiểu tĩnh chung, đối tượng mà nó tham chiếu **không bị chuyển đổi** thành một đối tượng `Exception` mới. Nếu phương thức ném `SQLException`, đối tượng thực sự vẫn là `SQLException`. Các thông tin như message, cause, SQL state và stack trace của đối tượng không tự mất đi.

Truy cập phương thức riêng bị hạn chế bởi **kiểm tra kiểu khi biên dịch**. Bạn có thể truy cập sau khi chứng minh được kiểu thực tế, như ví dụ `instanceof` ở phần sau.

### 3.2. Kiểu chung không đồng nghĩa chỉ có phương thức của `Object`

Nếu các lựa chọn kế thừa cùng một **lớp ngoại lệ trung gian** có phương thức ứng dụng tự định nghĩa, kiểu chung có thể cho phép truy cập phương thức ấy.

Ví dụ:

```text
Exception
    └── AppFailure (method: code())
        ├── NetworkFailure
        └── ValidationFailure
```

Trong `catch (NetworkFailure | ValidationFailure e)`, một phương thức `code()` public khai báo tại `AppFailure` có thể gọi trực tiếp bằng `e.code()`. Chúng ta sẽ kiểm chứng bằng chương trình độc lập ở mục 6.

## 4. Ví dụ chạy được: thành viên chung và phương thức riêng

Tạo tệp **`MultiCatchAccessDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchAccessDemo {
    private static void execute(String mode)
            throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("disk unavailable");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("connection refused", "08006");
        }
    }

    private static void run(String mode) {
        try {
            execute(mode);
            System.out.println(mode + ": success");
        } catch (IOException | SQLException failure) {
            System.out.println(failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());

            if (failure instanceof SQLException sqlFailure) {
                System.out.println("SQLSTATE=" + sqlFailure.getSQLState());
            }
        }
    }

    public static void main(String[] args) {
        run("io");
        run("sql");
        run("ok");
    }
}
```

Lệnh biên dịch/chạy với JDK 17+:

```bash
javac MultiCatchAccessDemo.java
java MultiCatchAccessDemo
```

Kết quả `stdout`:

```text
IOException: disk unavailable
SQLException: connection refused
SQLSTATE=08006
ok: success
```

Giải thích từng dòng:

1. `run("io")` nhận `IOException`; `getClass()` và `getMessage()` hợp lệ qua tham số multi-catch vì thuộc API chung.
2. `failure instanceof SQLException sqlFailure` là `false`, nên không in SQLSTATE.
3. `run("sql")` nhận `SQLException`; đối tượng vẫn giữ dữ liệu `SQLState` được truyền khi khởi tạo.
4. Mẫu `instanceof SQLException sqlFailure` kiểm tra runtime type và tạo biến `sqlFailure` có kiểu tĩnh cụ thể là `SQLException` ở nhánh đúng, nhờ đó `sqlFailure.getSQLState()` hợp lệ.
5. `run("ok")` không ném ngoại lệ, đi theo đường thành công.

Dạng `instanceof` với binding variable (`pattern matching for instanceof`) là tính năng chính thức trong Java 17, không cần bật preview.

## 5. Ví dụ **không biên dịch**: truy cập phương thức riêng trực tiếp

Đoạn sau có lỗi cố ý:

```java
import java.io.IOException;
import java.sql.SQLException;

public class InvalidMultiCatchMember {
    static void fail(boolean sql) throws IOException, SQLException {
        if (sql) {
            throw new SQLException("db error", "42000");
        }
        throw new IOException("IO error");
    }

    public static void main(String[] args) {
        try {
            fail(true);
        } catch (IOException | SQLException failure) {
            System.out.println(failure.getSQLState()); // LỖI BIÊN DỊCH
        }
    }
}
```

Nếu lưu thành `InvalidMultiCatchMember.java` và chạy:

```bash
javac InvalidMultiCatchMember.java
```

Compiler sẽ báo không tìm được phương thức phù hợp `getSQLState()` trên kiểu tĩnh của biểu thức `failure`. Văn bản chẩn đoán cụ thể có thể thay đổi theo bản JDK; **không chạy `java InvalidMultiCatchMember`** vì ví dụ này chủ ý không biên dịch.

**Tại sao `fail(true)` vẫn không giúp?** Trình biên dịch kiểm tra thân `catch` theo **kiểu khai báo của tham số**, không suy luận từ giá trị `true` của một lần gọi để biến `failure` thành `SQLException`. Hơn nữa, chữ ký `fail` có khả năng truyền hai loại checked exception.

Sửa bằng cách kiểm tra kiểu:

```java
if (failure instanceof SQLException sqlFailure) {
    System.out.println(sqlFailure.getSQLState());
}
```

Đây là **mảnh mã trong thân handler**, không phải chương trình độc lập. Việc thêm `instanceof` chuyển truy cập API riêng sang nhánh đã có bằng chứng kiểu tương thích.

### 5.1. Cũng không thể truyền tham số chung vào hàm chỉ nhận một loại

Ví dụ giả sử có phương thức:

```java
static void logSql(java.sql.SQLException failure) {
    System.out.println(failure.getSQLState());
}
```

Đoạn sau **không hợp lệ**:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    logSql(failure); // Không đảm bảo failure là SQLException.
}
```

Đây là đoạn đặt trong một chuỗi `try/catch` có các kiểu checked exception phù hợp. `logSql(SQLException)` đòi hỏi đối số có kiểu tương thích với `SQLException`, trong khi `failure` có thể là `IOException`.

Sửa:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    if (failure instanceof java.sql.SQLException sqlFailure) {
        logSql(sqlFailure);
    } else {
        System.out.println("Not a SQL exception");
    }
}
```

**Quy tắc áp dụng cho cả tham số hàm**, phép gán và chọn overload. Không thể dùng trực tiếp biến multi-catch như thể nó luôn thuộc một nhánh cụ thể.

## 6. Ví dụ chạy được: cùng lớp cha tự định nghĩa

Để thấy kiểu chung không chỉ dừng ở `Throwable`, hãy tạo hai ngoại lệ khác nhau có cùng API chung.

Tạo tệp **`CommonCatchMemberDemo.java`**:

```java
abstract class AppFailure extends Exception {
    private final String code;

    protected AppFailure(String code) {
        super(code);
        this.code = code;
    }

    public String code() {
        return code;
    }
}

class NetworkFailure extends AppFailure {
    NetworkFailure() {
        super("NETWORK");
    }
}

class ValidationFailure extends AppFailure {
    ValidationFailure() {
        super("VALIDATION");
    }
}

public class CommonCatchMemberDemo {
    private static void fail(boolean network)
            throws NetworkFailure, ValidationFailure {
        if (network) {
            throw new NetworkFailure();
        }
        throw new ValidationFailure();
    }

    private static void inspect(boolean network) {
        try {
            fail(network);
        } catch (NetworkFailure | ValidationFailure failure) {
            System.out.println(failure.code()
                    + ": " + failure.getMessage());
        }
    }

    public static void main(String[] args) {
        inspect(true);
        inspect(false);
    }
}
```

```bash
javac CommonCatchMemberDemo.java
java CommonCatchMemberDemo
```

Kết quả:

```text
NETWORK: NETWORK
VALIDATION: VALIDATION
```

`NetworkFailure` và `ValidationFailure` đều kế thừa `AppFailure`; tại điểm `catch`, tham số có thể dùng phương thức public `code()` của lớp cha chung. Không cần ép kiểu về từng lớp con khi chỉ truy cập thông tin mà cả hai **đều cam kết có**.

Chương trình được chủ động thiết kế đơn giản để chỉ tập trung vào vấn đề thành viên chung. Trong hệ thống thật, hãy cân nhắc ngoại lệ ứng dụng có nên công bố một lớp cha dùng chung hoặc một hợp đồng interface ổn định để handler xử lý nhất quán hay không.

### 6.1. Interface chung và kiểu giao

Least upper bound trong hệ thống kiểu Java có thể chứa cả các interface mà những lựa chọn ngoại lệ cùng thực thi. Khi đó, các thành viên interface **có thể** được truy cập từ tham số multi-catch nếu Java suy ra kiểu giao tương thích và quy tắc truy cập cho phép.

Tuy nhiên, việc một interface có cùng **tên phương thức** nhưng không thật sự là interface chung của các lớp không đủ để đảm bảo compiler cho phép gọi. Đừng dựa trên “duck typing” (hai lớp tình cờ có phương thức cùng tên): Java kiểm tra kiểu tĩnh, hệ kế thừa và interface.

Trong API ứng dụng, **lớp cha chung có hợp đồng rõ ràng** như `AppFailure` thường là ví dụ dễ đọc nhất. Với kiểu giao phức tạp/generics, nên kiểm tra kết quả biên dịch cụ thể của mã đang dùng.

## 7. Kiểu tĩnh quyết định việc chọn phương thức overload

Ngay cả khi mọi đối tượng lúc chạy đều có một kiểu cụ thể, Java quyết định **overload** tại compile time dựa trên kiểu của biểu thức truyền vào.

Giả sử có hai overload:

```java
static void report(Exception failure) {
    System.out.println("general");
}

static void report(java.sql.SQLException failure) {
    System.out.println("SQL-specific");
}
```

Nếu đặt đoạn sau trong một phương thức thích hợp:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    report(failure);
}
```

Lời gọi `report(failure)` không được lựa chọn overload nhận `SQLException` chỉ vì tại runtime đối tượng thực tế có thể là `SQLException`. Compiler sẽ chọn overload áp dụng được với **kiểu tĩnh chung** của `failure`; trong ví dụ này overload nhận `Exception` phù hợp.

Để gọi overload chuyên biệt:

```java
if (failure instanceof java.sql.SQLException sqlFailure) {
    report(sqlFailure);
} else {
    report(failure);
}
```

Đây là các mảnh mã minh họa được dùng trong phạm vi xử lý ngoại lệ, không phải chương trình `main` độc lập. Quy tắc chung là **overload resolution** dùng kiểu tĩnh, còn **override dispatch** tại runtime có thể chọn phiên bản ghi đè theo lớp của đối tượng đã được chọn phương thức tương ứng.

## 8. Điều gì xảy ra với các thành viên `protected` và `private`?

Khả năng truy cập qua tham số multi-catch còn chịu quy tắc truy cập thành viên thông thường của Java:

- `public`: có thể gọi nếu thành viên xuất hiện trong kiểu tĩnh phù hợp và các kiểu liên quan truy cập được.
- `protected`: có những quy tắc riêng theo package, kế thừa và kiểu của biểu thức nhận; không tự nhiên thành public chỉ vì hai ngoại lệ đều có thành viên đó.
- Thành viên không ghi access modifier (*package-private*): phụ thuộc package đang truy cập.
- `private`: chỉ truy cập được trong phạm vi được Java cho phép; multi-catch không cấp quyền truy cập ngoại lệ vào dữ liệu riêng của lớp khác.

Ví dụ có hai lớp ngoại lệ khác nhau, mỗi lớp tự khai báo phương thức `detail()`, **nhưng không có lớp cha/interface chung khai báo `detail()`**. Không thể giả định `failure.detail()` hợp lệ chỉ vì hai lớp đều có phương thức cùng tên. Trường hợp đó cần thiết kế API chung hoặc kiểm tra kiểu cụ thể.

Ngoài ra, phương thức có thể được khai báo ở lớp cha chung nhưng `protected`, và mã gọi ở package không thỏa điều kiện bảo vệ thì vẫn không gọi được. Đây là vấn đề **accessibility**, tách biệt với việc tìm được thành viên trong loại tĩnh.

## 9. Tham số multi-catch là implicitly final

Trong `catch (IOException | SQLException failure)`, `failure` **ngầm `final`**. Không thể gán `failure = new IOException("other")`, nhưng vẫn được gọi những phương thức mà kiểu tĩnh chung cho phép, kiểm tra `instanceof` hoặc ném lại chính đối tượng đó. Quy tắc này **không cấp thêm thành viên** cho biến: việc không được gán lại và việc có thể gọi `SQLException.getSQLState()` là hai câu hỏi kiểu học độc lập. Muốn dùng API riêng cho một nhánh, hãy thu hẹp kiểu an toàn hoặc tách handler theo chính sách.

## 10. Rethrow và mối liên hệ với kiểu multi-catch

Một điểm hữu ích của multi-catch là có thể ghi log/đính kèm ngữ cảnh chung rồi `throw failure;`. Khi làm vậy, Java vẫn kiểm tra checked exception mà lời gọi có thể truyền ra.

Tạo file **`MultiCatchRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchRethrowDemo {
    private static void execute(String mode)
            throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("read failed");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("query failed");
        }
    }

    private static void relay(String mode)
            throws IOException, SQLException {
        try {
            execute(mode);
        } catch (IOException | SQLException failure) {
            System.out.println("forward: "
                    + failure.getClass().getSimpleName());
            throw failure;
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {"io", "sql", "ok"}) {
            try {
                relay(mode);
                System.out.println(mode + ": success");
            } catch (IOException | SQLException failure) {
                System.out.println("received: "
                        + failure.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac MultiCatchRethrowDemo.java
java MultiCatchRethrowDemo
```

`stdout`:

```text
forward: IOException
received: IOException
forward: SQLException
received: SQLException
ok: success
```

`relay` khai báo `throws IOException, SQLException`; khi ném lại `failure`, chính đối tượng đã nhận được truyền lên caller. Java cho phép phân tích chính xác hơn các checked exception có thể được rethrow trong ngữ cảnh bắt ngoại lệ phù hợp, thay vì buộc khai báo `throws Exception` một cách không cần thiết.

**Không lẫn lộn:** kiểu tĩnh chung giới hạn **thành viên bạn được gọi trên `failure`**; quy tắc exception checking khi `throw failure;` có thể xem xét các kiểu ngoại lệ bắt được và đường phát sinh trong `try`. Vì vậy, việc `failure.getSQLState()` bị từ chối không ngụ ý `throw failure;` cũng phải bị từ chối nếu phương thức đã khai báo hai loại checked exception tương ứng.

### 10.1. `catch` một loại và precise rethrow

Java 7 còn có cơ chế phân tích rethrow chính xác cho một số tham số `catch` **effectively final** của handler một kiểu, dựa trên các loại checked exception mà `try` có thể ném. Điều này liên quan nhưng **không đồng nhất** với quy tắc tham số multi-catch **implicitly final**.

Nếu cần sửa một handler khiến precise rethrow không còn áp dụng, xem liệu tham số có bị gán lại hay không và kiểm tra những loại checked exception có thể thoát thực tế từ khối `try`. Hãy tránh đánh đồng “có nhiều kiểu trong `catch`” với “mọi cách rethrow đều có cùng luật”.

### 10.2. Khi nào nên ném lại, khi nào nên bọc?

- **Ném lại** `throw failure;` khi tầng hiện tại không thể phục hồi và hợp đồng của tầng trên vẫn cho phép các kiểu checked exception đó.
- **Bọc** bằng ngoại lệ có `cause` khi tầng hiện tại thêm ý nghĩa miền nghiệp vụ hoặc cần đổi giao diện lỗi.
- **Xử lý tại chỗ** nếu biết cách phục hồi thực sự, không chỉ ghi log rồi giả định thao tác thành công.

Trong mọi trường hợp, đừng viết một handler chỉ để bắt, in stack trace nhiều lần và làm mất đường đi của lỗi.

## 11. Các giới hạn khác của cú pháp multi-catch

### 11.1. Những kiểu thay thế không được có quan hệ cha–con

Đoạn này **không biên dịch**:

```java
catch (java.io.IOException
       | java.io.FileNotFoundException failure) {
    System.out.println(failure.getMessage());
}
```

`FileNotFoundException` là lớp con của `IOException`, nên hai lựa chọn trong **cùng một multi-catch** có quan hệ subtype và bị Java cấm. Thay bằng:

```java
catch (java.io.IOException failure) {
    System.out.println(failure.getMessage());
}
```

Nếu muốn hai cách xử lý khác nhau, dùng hai `catch` liên tiếp theo thứ tự **FileNotFoundException trước, IOException sau**. Đừng dùng multi-catch để liệt kê kiểu rộng và chính lớp con của nó.

### 11.2. Không thể viết multi-catch với danh sách kiểu bất kỳ

Mỗi lựa chọn phải là một kiểu ngoại lệ hợp lệ theo ngữ pháp/các giới hạn của Java, được ngăn cách bằng `|`. Một số ví dụ cú pháp **sai**:

```java
catch (java.io.IOException, java.sql.SQLException e) { } // Sai dấu phẩy.
catch (new java.io.IOException() | java.sql.SQLException e) { } // Sai: đối tượng không phải kiểu.
```

Đây là hai mảnh cố ý không biên dịch. Trong mệnh đề `throws`, các **kiểu** lại được phân cách bằng dấu phẩy: `throws IOException, SQLException`. Không trộn hai vị trí cú pháp này.

### 11.3. Kiểm tra checked exception vẫn áp dụng

Multi-catch không miễn các quy tắc về checked exception. Một handler có thể không hợp lệ nếu `try` không có cách nào ném một kiểu checked exception mà nó khai báo bắt, ngay cả khi kiểu khác là hợp lệ.

Ví dụ đoạn sau **không biên dịch** vì `try` không có thao tác có khả năng phát sinh checked `SQLException`:

```java
try {
    System.out.println("hello");
} catch (java.io.IOException | java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

Trên thực tế, cả `IOException` và `SQLException` đều không thể phát sinh từ khối `try` đang hiển thị, nên compiler có đủ căn cứ từ chối. Khi kiểm tra một multi-catch cụ thể, hãy phân biệt:
- Các lựa chọn ngoại lệ có quan hệ subtype không hợp lệ.
- Một kiểu checked exception có thể không được ném bởi khối `try`.
- Cố gọi phương thức riêng không có trên kiểu tĩnh của tham số.
- Cố gán lại biến multi-catch implicitly final.

Các lỗi có chẩn đoán khác nhau và cần cách sửa khác nhau.

## 12. Lựa chọn thiết kế: giữ một handler chung hay tách handler?

Không có quy tắc rằng cứ có hai loại ngoại lệ là phải dùng multi-catch. Hãy chọn dựa trên **logic xử lý**:

| Nhu cầu | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Hai lỗi có cùng chính sách ghi nhận và truyền tiếp | Một `catch (A | B e)` | Tránh lặp logic, chỉ dùng API chung |
| Hai loại cần cách phục hồi khác nhau | Hai `catch` riêng | Mỗi handler có tham số kiểu cụ thể |
| Cả hai có một lớp cha ứng dụng với API chung | Multi-catch hoặc bắt lớp cha thích hợp | Truy cập được hợp đồng chung; cân nhắc độ rộng API |
| Chỉ một nhánh cần API riêng | Multi-catch + `instanceof` khi phân nhánh nhỏ | Thu hẹp kiểu an toàn, tránh ép kiểu vô điều kiện |
| Hầu hết logic khác nhau theo từng loại | Hai `catch` riêng | Dễ hiểu hơn chuỗi `instanceof` phức tạp |
| Cần giữ loại checked exception khi truyền lên | Rethrow với hợp đồng `throws` đúng | Không mất đối tượng gốc và thông tin kiểu |
| Muốn đổi tầng trừu tượng lỗi | Tạo ngoại lệ mới kèm `cause` | Thể hiện ngữ cảnh nhưng giữ nguyên nhân |

### 12.1. Tách handler khi cần phương thức chuyên biệt thường xuyên

Ví dụ:

```java
try {
    perform();
} catch (java.sql.SQLException sql) {
    System.err.println("SQLSTATE: " + sql.getSQLState());
    System.err.println("Vendor code: " + sql.getErrorCode());
} catch (java.io.IOException io) {
    System.err.println("File I/O: " + io.getMessage());
}
```

Đây là mảnh minh họa, cần định nghĩa `perform()` có khả năng ném hai loại checked exception. Với xử lý chuyên biệt này, hai handler riêng thường dễ đọc hơn multi-catch rồi nhiều `instanceof`.

### 12.2. Dùng `instanceof` đúng lúc

`instanceof` hữu ích khi chỉ có một phần nhỏ cần xử lý theo kiểu cụ thể; nhưng nếu bạn phải lặp lại kiểm tra `instanceof` hàng chục lần, handler chung có thể đang che khuất hai chính sách xử lý khác nhau. Hãy tách handler nếu chúng cần các thao tác riêng biệt.

Không dùng cast thiếu kiểm tra:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    java.sql.SQLException sql =
            (java.sql.SQLException) failure; // Có thể ClassCastException khi là IOException.
}
```

Đoạn này có thể **biên dịch** trong một `try/catch` hợp lệ, nhưng cast chỉ an toàn nếu đối tượng thực sự là `SQLException`. Đừng giả định vì một nhánh thử nghiệm hay chạy với SQL mà mọi lần runtime đều đi qua loại đó.

Nên dùng:

```java
if (failure instanceof java.sql.SQLException sql) {
    System.out.println(sql.getSQLState());
}
```

Đây là mảnh trong thân handler; Java 17 hỗ trợ type pattern trong `instanceof` mà không cần cast thêm.

## 13. Bài tập tự kiểm tra

### Bài 1 — Thành viên chung

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause());
}
```

**Đúng hay sai?** Đúng về truy cập thành viên. Các phương thức này được công bố trong `Throwable` nên hợp lệ qua kiểu tĩnh chung, giả sử câu lệnh `try` tương ứng có thể ném các checked exception đó.

### Bài 2 — Thành viên chỉ thuộc `SQLException`

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getErrorCode());
}
```

**Đúng hay sai?** Sai về kiểm tra kiểu tại compile time: `getErrorCode()` không thuộc API chung của hai lựa chọn. Kiểm tra `ex instanceof SQLException sql` trước khi gọi `sql.getErrorCode()` hoặc tách handler.

### Bài 3 — Gán lại tham số

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    ex = new java.io.IOException("new");
}
```

**Đúng hay sai?** Sai. Tham số multi-catch implicitly final, không thể gán lại.

### Bài 4 — Lớp cha chung

Giả sử `ReadFailure` và `WriteFailure` đều kế thừa `StorageFailure` với phương thức public `kind()`. Có gọi `ex.kind()` trong `catch (ReadFailure | WriteFailure ex)` không?

**Đáp án:** Có, nếu những khai báo kiểu hợp lệ và `kind()` thực sự truy cập được qua kiểu chung mà Java suy ra.

### Bài 5 — Rethrow

Phương thức `execute()` khai báo `throws IOException, SQLException` và trong `try` chỉ gọi phương thức đó; trong `catch (IOException | SQLException ex)` có `throw ex;`. Phương thức bao ngoài cần làm gì?

**Đáp án:** Bắt hoặc khai báo các checked exception có thể truyền ra, chẳng hạn `throws IOException, SQLException`. Không cần tự mở rộng thành `throws Exception` chỉ vì biểu thức `ex` có kiểu chung.

### Bài 6 — Hai lựa chọn trong một nhánh subtype

`catch (IOException | FileNotFoundException ex)` hợp lệ không?

**Đáp án:** Không. `FileNotFoundException` kế thừa `IOException` nên vi phạm giới hạn của multi-catch.

### Bài 7 — Overload

Có `report(Exception)` và `report(SQLException)`. Trong `catch (IOException | SQLException ex)`, gọi `report(ex)` có tự chọn phiên bản SQLException khi runtime nhận SQLException không?

**Đáp án:** Không. Chọn overload tại compile time theo kiểu tĩnh của `ex`, không dựa vào class thực tế để chuyển sang overload SQL.

## 14. Những nhầm lẫn thường gặp

**“`IOException | SQLException` tạo một đối tượng vừa là IOException vừa là SQLException.”** Sai. Multi-catch nhận một đối tượng thuộc một trong các nhánh ngoại lệ phù hợp.

**“Có thể gọi tổng hợp mọi phương thức của các lớp sau dấu `|`.”** Sai. Trình biên dịch chỉ cho phép thành viên phù hợp với kiểu tĩnh chung và quy tắc truy cập.

**“Compiler biết lần này SQL nên `ex.getSQLState()` luôn hợp lệ.”** Sai. Kiểu tĩnh không tự trở thành `SQLException` vì dữ liệu chạy hoặc nhánh thử nghiệm.

**“`ex.getMessage()` không hợp lệ vì không biết kiểu cụ thể.”** Sai. `getMessage()` thuộc `Throwable` nên dùng được.

**“Trong multi-catch, tham số luôn được khai báo chính xác là `Exception`.”** Sai. Kiểu dùng `lub` và có thể có các thành phần kiểu giao hoặc lớp cha chung khác.

**“Chỉ cần hai lớp có phương thức trùng tên là biến multi-catch gọi được phương thức đó.”** Sai. Java dùng quan hệ kiểu, không dùng cơ chế duck typing.

**“`final` nghĩa là không thể gọi phương thức thay đổi đối tượng ngoại lệ.”** Sai. `final` áp dụng cho phép gán biến tham số, không làm đối tượng bất biến.

**“`throw ex` bắt buộc phải khai báo `throws Exception` vì kiểu tĩnh chung.”** Sai trong nhiều tình huống precise rethrow, khi Java có thể xác định các loại checked exception được bắt và truyền lại.

**“`catch (FileNotFoundException | IOException e)` giúp xử lý riêng hai trường hợp.”** Sai. Đây là hai loại có quan hệ cha–con nên multi-catch không hợp lệ.

**“Ép kiểu `(SQLException) ex` luôn an toàn nếu catch có SQL.”** Sai. Ex có thể là `IOException`, cast có thể ném `ClassCastException`.

**“Muốn dùng API SQL riêng thì luôn phải multi-catch rồi instanceof.”** Sai. Nếu đường phục hồi khác nhau đáng kể, hai `catch` riêng có thể rõ ràng hơn.

## 15. Tài liệu chính thức

- [Java Language Specification 17 — `14.20, The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cú pháp multi-catch, kiểu của tham số và ràng buộc các lựa chọn.
- [Java Language Specification 17 — `11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): kiểm tra checked exception và rethrow.
- [Java Language Specification 17 — `4.10.4, Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4): cách Java xác định giới hạn kiểu chung.
- [Java Language Specification 17 — `15.20.2, Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): kiểm tra và thu hẹp kiểu với `instanceof`.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): các thành viên chung như `getMessage()`, `getCause()`.
- [Java SE 17 API — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): các thành viên riêng của ngoại lệ SQL.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): loại ngoại lệ I/O thường được dùng trong multi-catch.

**Ghi nhớ:** `catch (A | B e)` bắt được hai nhánh ngoại lệ, nhưng tham số `e` chỉ được truy cập những thành viên mà **kiểu tĩnh chung suy ra từ các lựa chọn** cho phép. Muốn dùng thành viên chỉ có ở một nhánh, hãy thu hẹp kiểu an toàn bằng `instanceof` hoặc tách các handler khi chính sách xử lý khác nhau. Rethrow có thể bảo toàn chính loại ngoại lệ ban đầu mà không nới rộng hợp đồng checked exception một cách không cần thiết.
