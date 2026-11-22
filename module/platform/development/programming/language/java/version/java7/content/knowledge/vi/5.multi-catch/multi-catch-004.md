# Kiểu quan sát được của tham số catch trong Java multi-catch

**Chủ đề:** Java 7 — Multi-catch  
**Bài học:** Kiểu quan sát được của tham số catch  
**Phạm vi:** Quy tắc kiểu mà compiler áp dụng cho biến exception trong `catch (A | B ex)`, sự khác biệt với lớp ngoại lệ thực tế khi chạy, khả năng truy cập phương thức, giao diện chung, `instanceof`, `final` và `precise rethrow`. Đây đều là kiến thức **vẫn còn áp dụng trên JDK hiện đại**; các ví dụ chạy với Java 17+.

Multi-catch là tính năng Java 7 cho phép xử lý **nhiều loại ngoại lệ trong cùng một khối** khi chúng thực sự có cùng chính sách xử lý:

```java
try {
    operation();
} catch (IOException | SQLException ex) {
    System.out.println(ex.getMessage());
}
```

Đây là **đoạn minh họa**, giả sử `operation()` có thể ném hai checked exception và các lớp đã được import. Câu hỏi then chốt không chỉ là “bắt được lỗi nào?” mà là **“trong thân catch, trình biên dịch nhìn biến ex theo kiểu gì?”**

## 1. Kiểu tĩnh của tham số catch khác kiểu runtime của ngoại lệ

Cần tách hai ý:

- **Kiểu tĩnh / kiểu được khai báo (*declared type*)** của tham số là kiểu mà compiler sử dụng để kiểm tra phép gán, gọi phương thức, truy cập thành viên và lựa chọn overload. Với multi-catch, kiểu này là **least upper bound** (`lub`) của các loại exception được liệt kê.
- **Kiểu runtime** là lớp thực sự của đối tượng đã được `throw`, như `IOException`, `FileNotFoundException` hoặc `SQLException`. Multi-catch **không tạo đối tượng exception mới**, không sửa cause hay stack trace, và không biến một `SQLException` thành instance `IOException`.

Ví dụ:

```java
catch (IOException | SQLException ex) {
    Exception general = ex; // Hợp lệ.
    // IOException onlyIo = ex; // Không hợp lệ.
    System.out.println(ex.getClass().getSimpleName());
}
```

Đây là code **minh họa**, chưa phải lớp Java hoàn chỉnh. Hai loại exception ở lựa chọn này cùng có superclass phù hợp là `Exception`, nên compiler có thể cho phép `Exception general = ex`; nhưng không thể bảo đảm `ex` là `IOException` trong mọi lần chạy.

**Điều thường gây nhầm:** một lần log in ra `SQLException` không khiến biến `ex` được xem là `SQLException` ở mọi dòng trong thân `catch`. Compiler phải bảo vệ **cả hai khả năng** của multi-catch.

## 2. Công thức chính xác: least upper bound (LUB)

Theo Java Language Specification (JLS `14.20), nếu tham số được viết là `catch (D1 | D2 | ... | Dn ex)` thì **kiểu khai báo của `ex` là `lub(D1, D2, ..., Dn)`**. Với một `catch (D ex)` chỉ có một loại, kiểu khai báo là `D`.

```text
    catch (D1 | D2 | ... | Dn ex)
             |
             v
  declared type = lub(D1, ..., Dn)
             |
             v
  compiler kiểm tra thành viên, phép gán,
  overload và biểu thức sử dụng ex
```

LUB không có nghĩa “luôn chọn `Exception`” và cũng không phải kiểu union để sử dụng tùy ý ở mọi chỗ trong chương trình. Nó là kết quả phân tích **hệ phân cấp class + interface** của những kiểu được liệt kê.

| Các lựa chọn | Kiểu được compiler quan sát trong thân catch | Lý do |
| --- | --- | --- |
| `IOException | SQLException` | `Exception` | Hai lớp không có superclass chung cụ thể hơn `Exception`. |
| `ClassNotFoundException | IllegalAccessException` | `ReflectiveOperationException` | Hai exception cùng kế thừa từ `ReflectiveOperationException`. |
| Hai exception khác nhau cùng triển khai `Retryable` | LUB có thể mang thêm thành phần interface `Retryable` | Phương thức của interface chung có thể gọi trực tiếp nếu Java chứng minh được. |

**Cần chính xác khi diễn đạt:** LUB có thể là một kiểu giao (*intersection type*) chứa thông tin từ interface. Vì thế, khẳng định “một multi-catch chỉ gọi được method của `Exception`” là **quá đơn giản và có thể sai**.

### 2.1. Sơ đồ cho cặp IOException và SQLException

```text
                 Throwable
                     |
                 Exception <-- nhìn thấy ở compile time trong ví dụ
                 /       \
         IOException   SQLException
              |
    FileNotFoundException
```

Tại runtime, tham số vẫn giữ đối tượng thực tế. Ví dụ `ex.getClass()` có thể cho biết lớp con, nhưng compiler lựa chọn overload và xác nhận method theo kiểu tĩnh của `ex`.

### 2.2. Multi-catch không tạo union type đa dụng

Dấu `|` này chỉ là cú pháp **các lựa chọn ngoại lệ trong tham số catch**:

```java
// Sai: khai báo biến bằng một union type:
// IOException | SQLException ex;

// Sai: ngăn cách ngoại lệ của throws bằng dấu |:
// void work() throws IOException | SQLException { }

// Đúng ở khai báo throws:
// void work() throws IOException, SQLException { }
```

Các dòng trên đều được comment nên không phải một chương trình độc lập. Đừng dùng kiểu union của multi-catch để suy luận cú pháp Java cho field, local variable hoặc return type.

## 3. Ví dụ hoàn chỉnh: kiểu tĩnh quyết định overload

Tạo tệp `CatchObservedTypeDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class CatchObservedTypeDemo {
    static String describe(Exception ex) {
        return "overload=Exception";
    }

    static String describe(IOException ex) {
        return "overload=IOException";
    }

    static void process(boolean fileError) {
        try {
            if (fileError) {
                throw new IOException("file");
            }
            throw new SQLException("database", "42000");
        } catch (IOException | SQLException ex) {
            Exception general = ex;

            System.out.println(
                    "runtime=" + ex.getClass().getSimpleName());
            System.out.println(describe(ex));
            System.out.println("message=" + general.getMessage());

            if (ex instanceof SQLException sql) {
                System.out.println(
                        "sqlState=" + sql.getSQLState());
            }
        }
    }

    public static void main(String[] args) {
        process(true);
        process(false);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 CatchObservedTypeDemo.java
java CatchObservedTypeDemo
```

**Kết quả stdout chính xác:**

```text
runtime=IOException
overload=Exception
message=file
runtime=SQLException
overload=Exception
message=database
sqlState=42000
```

Phân tích từng điểm:

1. `process(true)` tạo `IOException` thật; `process(false)` tạo `SQLException` thật. Dòng `runtime=...` phản ánh đúng **kiểu runtime**.
2. Tuy có overload `describe(IOException)`, cả hai lần `describe(ex)` đều gọi **`describe(Exception)`**. **Overloading được giải quyết lúc biên dịch** từ kiểu tĩnh của `ex`, tức `Exception` trong multi-catch này.
3. `Exception general = ex` biên dịch và tham chiếu **cùng đối tượng**; việc gán sang superclass không xóa cause/stack trace.
4. `getMessage()` có sẵn trong API kế thừa từ `Throwable` nên được gọi trên kiểu chung.
5. `SQLException.getSQLState()` **không** thuộc API của `Exception`. Chỉ sau `if (ex instanceof SQLException sql)`, Java 17 mới cho phép gọi `sql.getSQLState()` vì biến mẫu `sql` được compiler xác nhận là `SQLException`.

Đoạn `instanceof SQLException sql` sử dụng **pattern matching for instanceof** (chính thức từ Java 16). Nó phù hợp khi học Java hiện đại nhưng không thuộc cú pháp Java 7 ban đầu.

### 3.1. Thành viên của subtype không tự hiện ra

Các dòng sau **không hợp lệ nếu bỏ comment** bên trong `catch (IOException | SQLException ex)`:

```java
// IOException io = ex;          // ex cũng có thể là SQLException.
// ex.getSQLState();             // Exception không có method này.
// SQLException sql = ex;        // ex cũng có thể là IOException.
```

Đây là **mã cố ý sai đã comment**. Khi cần thành viên riêng của một subtype, dùng `instanceof` để thu hẹp kiểu hoặc tách các `catch`.

### 3.2. Phân biệt overload với override

Ví dụ chọn giữa `describe(Exception)` và `describe(IOException)` là **overload**, xét theo kiểu tĩnh của biểu thức đối số. Nếu exception subclass **override một instance method**, Java vẫn thực hiện dynamic dispatch theo lớp runtime khi gọi method đó qua biến `ex`. Multi-catch không tắt đa hình của đối tượng.

## 4. Khi các ngoại lệ cùng có superclass cụ thể hơn

`ClassNotFoundException` và `IllegalAccessException` đều kế thừa `ReflectiveOperationException`. Trong trường hợp này LUB của chúng là `ReflectiveOperationException`, cụ thể hơn `Exception`.

Tạo `CommonParentCatchDemo.java`:

```java
public class CommonParentCatchDemo {
    static void access(boolean missing)
            throws ClassNotFoundException, IllegalAccessException {
        if (missing) {
            throw new ClassNotFoundException("missing class");
        }
        throw new IllegalAccessException("private member");
    }

    static void run(boolean missing) {
        try {
            access(missing);
        } catch (ClassNotFoundException | IllegalAccessException ex) {
            ReflectiveOperationException common = ex;
            System.out.println(
                common.getClass().getSimpleName()
                + ":" + common.getMessage());
        }
    }

    public static void main(String[] args) {
        run(true);
        run(false);
    }
}
```

```bash
javac -encoding UTF-8 CommonParentCatchDemo.java
java CommonParentCatchDemo
```

```text
ClassNotFoundException:missing class
IllegalAccessException:private member
```

Dòng `ReflectiveOperationException common = ex;` chứng minh **compiler biết loại cha cụ thể hơn**. Lúc chạy, `getClass().getSimpleName()` vẫn trả lớp thực được ném.

Các kiểu được liệt kê trong multi-catch phải có quan hệ phù hợp để khối catch hợp lệ; không nhất thiết phải có cùng một superclass mới dùng được, nhưng compiler chỉ cho phép gọi những thành viên mà LUB bảo đảm.

## 5. Khi các ngoại lệ chia sẻ interface

Java cho phép ngoại lệ triển khai interface mô tả hợp đồng nghiệp vụ chung. Ví dụ sau kiểm tra xem lỗi có phù hợp để thử lại không mà không cần biết cụ thể exception nào đã được ném.

Tạo `SharedInterfaceCatchDemo.java`:

```java
public class SharedInterfaceCatchDemo {
    interface Retryable {
        boolean canRetry();
    }

    static final class InputProblem extends Exception
            implements Retryable {
        private static final long serialVersionUID = 1L;

        InputProblem(String message) {
            super(message);
        }

        @Override
        public boolean canRetry() {
            return true;
        }
    }

    static final class OutputProblem extends Exception
            implements Retryable {
        private static final long serialVersionUID = 1L;

        OutputProblem(String message) {
            super(message);
        }

        @Override
        public boolean canRetry() {
            return false;
        }
    }

    static void run(boolean input) {
        try {
            if (input) {
                throw new InputProblem("input");
            }
            throw new OutputProblem("output");
        } catch (InputProblem | OutputProblem ex) {
            System.out.println(
                ex.getMessage() + ":retry=" + ex.canRetry());
        }
    }

    public static void main(String[] args) {
        run(true);
        run(false);
    }
}
```

```bash
javac -encoding UTF-8 SharedInterfaceCatchDemo.java
java SharedInterfaceCatchDemo
```

```text
input:retry=true
output:retry=false
```

Phương thức `canRetry()` chỉ có trong `Retryable`, không thuộc `Exception`. Dòng `ex.canRetry()` **vẫn biên dịch** vì cả `InputProblem` và `OutputProblem` đều triển khai interface này và phép suy luận LUB giữ được hợp đồng chung tương ứng.

**Ý nghĩa:** “kiểu quan sát được” có thể mang thành phần interface, nên **không nhất thiết chỉ có các method của superclass gần nhất**. Nếu bỏ `implements Retryable` khỏi một exception, code trên sẽ không được bảo đảm có method `canRetry()` đối với mọi lựa chọn; compiler sẽ từ chối lời gọi trực tiếp.

Thiết kế interface này chỉ nên dùng khi **đúng là một hợp đồng chung** giữa hai lỗi. Không nên thay toàn bộ thiết kế xử lý ngoại lệ bằng hàng loạt interface chỉ nhằm cố làm multi-catch ngắn hơn.

## 6. Thu hẹp kiểu khi cần xử lý riêng

Nếu phần lớn công việc chung nhưng một số thao tác riêng, có ba lựa chọn:

| Cách viết | Phù hợp khi | Giới hạn |
| --- | --- | --- |
| `catch (A | B ex)` rồi dùng method chung | Hai lỗi có chính sách xử lý giống nhau: log, wrap, chuyển thành một trạng thái | Method riêng không tự có trên kiểu LUB. |
| `catch (A | B ex)` + `instanceof` | Xử lý chung nhưng cần một vài nhánh phụ có thông tin loại cụ thể | Khi nhiều nhánh riêng, code có thể khó đọc. |
| `catch (A ex)` và `catch (B ex)` riêng | Hai lỗi cần retry, rollback, báo lỗi hoặc phân quyền khác nhau | Có thể có ít đoạn code xử lý chung cần tách helper để tránh lặp. |

Ví dụ minh họa:

```java
try {
    operation();
} catch (IOException | SQLException ex) {
    System.err.println(ex.getMessage());

    if (ex instanceof SQLException sql) {
        System.err.println("SQLState=" + sql.getSQLState());
    } else if (ex instanceof IOException io) {
        System.err.println("I/O=" + io.getMessage());
    }
}
```

Đây là **đoạn minh họa**, cần `operation()` và import thích hợp. `instanceof` kiểm tra **lớp runtime**, và compiler chỉ cho biến `sql`/`io` kiểu hẹp trong nhánh đã được kiểm chứng. Không cast `(SQLException) ex` ngay trong body nếu chưa kiểm tra, vì exception thực tế có thể là `IOException` và cast sẽ ném `ClassCastException` ngoài ý muốn.

Với những thao tác thực sự khác nhau (chẳng hạn SQL rollback riêng, lỗi file retry riêng), hãy ưu tiên tách hai `catch` cho rõ hợp đồng hơn.

## 7. Tham số multi-catch ngầm final

JLS quy định tham số của multi-catch **implicitly final**, kể cả khi không viết từ khóa `final`. Vì vậy không được gán lại:

```java
// Giả sử nằm trong catch (IOException | SQLException ex):
// ex = new IOException("changed"); // Lỗi biên dịch.
```

Đây là **đoạn code cố ý sai đã comment**. Tính `final` áp dụng cho **tham chiếu biến** `ex`, không biến đối tượng exception thành immutable. Nếu hợp lệ theo API, ta vẫn có thể gọi phương thức trên đối tượng exception hoặc thêm suppressed exception; điều bị cấm là gán lại biến tham số.

Cần phân biệt:

- **Multi-catch:** tham số **implicitly final**, không thể gán lại trong block.
- **Uni-catch `catch (Exception ex)`:** tham số **không implicitly final**; nếu không bị gán lại, nó có thể **effectively final**. Đây là một quy tắc khác với “implicitly final”, dù đều giúp compiler kiểm soát một số tình huống.
- Có thể viết `catch (final IOException | SQLException ex)` khi cần biểu đạt rõ, nhưng bản thân multi-catch đã cấm gán lại nên không cần thêm `final` để bảo vệ hành vi ấy.

## 8. Precise rethrow và kiểu mà compiler nhìn thấy

Java 7 còn bổ sung **precise rethrow**: khi ném lại đúng tham số `catch` đủ điều kiện, compiler phân tích những checked exception mà `try` thực sự có thể ném, thay vì luôn buộc phương thức khai báo một kiểu quá rộng.

Điều này **khác** với kiểu tĩnh của biến trong thân catch. Ví dụ `catch (Exception ex)` cho phép compiler xem `ex` là `Exception` để gọi method, nhưng `throw ex` có thể được phân tích chính xác hơn nếu `ex` **effectively final**.

Tạo `PreciseRethrowDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class PreciseRethrowDemo {
    static void perform(int kind)
            throws IOException, SQLException {
        if (kind == 1) {
            throw new IOException("disk");
        }
        if (kind == 2) {
            throw new SQLException("db");
        }
    }

    static void viaMultiCatch(int kind)
            throws IOException, SQLException {
        try {
            perform(kind);
        } catch (IOException | SQLException ex) {
            System.out.println(
                "multi:" + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    static void viaSingleCatch(int kind)
            throws IOException, SQLException {
        try {
            perform(kind);
        } catch (Exception ex) {
            System.out.println(
                "single:" + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            viaMultiCatch(1);
        } catch (IOException | SQLException ex) {
            System.out.println("caller:" + ex.getMessage());
        }

        try {
            viaSingleCatch(2);
        } catch (IOException | SQLException ex) {
            System.out.println("caller:" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

```text
multi:IOException
caller:disk
single:SQLException
caller:db
```

**Lưu ý về hai phương thức:**

- `viaMultiCatch` bắt hai checked exception và tham số `ex` ngầm final. `throw ex;` được phép, và chữ ký vẫn là `throws IOException, SQLException`.
- `viaSingleCatch` bắt kiểu rộng `Exception` nhưng **không gán lại `ex`**, nên tham số effectively final. Compiler biết `perform` chỉ có thể ném `IOException` hoặc `SQLException`; do đó phương thức vẫn có thể khai báo chính xác hai loại ấy, **không nhất thiết phải mở rộng thành `throws Exception`**.
- Nếu thêm phép gán lại vào tham số của **uni-catch**, điều kiện effectively final mất và phân tích `throw ex` có thể yêu cầu kiểu `throws` rộng hơn. Multi-catch không cho phép gán lại ngay từ đầu.

Cơ chế này giúp giữ hợp đồng checked exception chặt chẽ mà không phải bắt rồi chuyển hết thành `Exception`. Nó **không** khiến mọi biểu thức `ex` trong thân catch tự trở thành `IOException` hay `SQLException`.

**Không dùng cast để ép hợp đồng throws:** `throw (IOException) ex;` sẽ thất bại nếu ngoại lệ thực tế là `SQLException`. Khi muốn chuyển lỗi thành một loại ngoại lệ nghiệp vụ, hãy wrap đúng cách và **giữ cause**, chẳng hạn `new IllegalStateException("operation failed", ex)` nếu chính sách ứng dụng chấp nhận.

## 9. Các hạn chế cú pháp phải nhớ

### 9.1. Không được dùng hai lựa chọn có quan hệ subtype/supertype

Những câu sau không biên dịch nếu bỏ comment:

```java
// FileNotFoundException là subtype của IOException:
// catch (FileNotFoundException | IOException ex) { }

// SQLException là subtype của Exception:
// catch (SQLException | Exception ex) { }
```

Khi kiểu con đã được kiểu cha bao phủ, Java **không cho phép** đặt cả hai trong cùng union của multi-catch. Nếu cần chính sách khác nhau, tách thành hai `catch` và bắt **loại cụ thể trước** rồi đến loại cha.

### 9.2. Checked exception phải có đường có thể ném

Đối với checked exception, compiler kiểm tra khối `try` có thể phát sinh kiểu ngoại lệ được bắt theo quy tắc reachability/exception analysis. Nếu khối `try` chỉ gọi một API có `throws IOException` mà không có khả năng `SQLException`, viết `catch (IOException | SQLException ex)` có thể dẫn tới lỗi vì `SQLException` không bao giờ được ném trong ngữ cảnh ấy.

Đây là lý do các ví dụ runnable chủ động tạo đường ném cả hai exception. Đừng liệt kê mọi kiểu exception của chương trình vào `catch` cho “đủ”; chỉ bắt các loại mà khối `try` thực sự có thể ném.

### 9.3. Không dùng `var` làm exception parameter

`catch (var ex)` không phải cú pháp Java hợp lệ. Multi-catch đòi hỏi **class types của `Throwable` hoặc các subtype** được phân cách bằng `|`; không được dùng generic type variable `T extends Exception` trực tiếp làm exception parameter.

### 9.4. `catch` không tự thay chính sách xử lý

Cặp exception hợp lệ về cú pháp **không đồng nghĩa** chúng có cùng ý nghĩa nghiệp vụ. Nếu lỗi file cần retry còn lỗi cơ sở dữ liệu cần rollback hoặc chặn request, tách xử lý sẽ rõ ràng hơn. Multi-catch là công cụ gom **logic trùng nhau**, không phải cách ẩn đi những khác biệt quan trọng.

## 10. Những hiểu nhầm khi xem kiểu quan sát được

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`ex` là `IOException` khi dòng đầu ném IOException.” | Đối tượng runtime có thể là IOException; nhưng trong `catch(IOException | SQLException ex)`, compiler xem `ex` theo LUB của **cả hai** lựa chọn. |
| “Tham số multi-catch luôn có kiểu `Exception`.” | Có thể là `ReflectiveOperationException` hoặc LUB bao gồm interface chung; phụ thuộc hệ phân cấp. |
| “`ex.getClass()` cho phép gọi method riêng ngay.” | `getClass()` cung cấp thông tin runtime; muốn gọi member riêng phải có kiểu tĩnh phù hợp, ví dụ sau `instanceof`. |
| “Overload sẽ chọn `describe(IOException)` ở runtime.” | Overload dựa trên **kiểu tĩnh**; dynamic dispatch chỉ xảy ra với instance method đã được chọn để gọi. |
| “`A | B` có thể dùng để khai báo field, biến hay `throws`.” | Trong trường hợp này `|` là cú pháp riêng của multi-catch; `throws` dùng dấu phẩy. |
| “Có thể gán lại `ex` để đổi loại lỗi được xử lý.” | Tham số multi-catch implicitly final; việc gán lại bị compiler chặn. |
| “`catch(Exception ex) { throw ex; }` luôn cần `throws Exception`.” | Precise rethrow có thể giữ tập checked exception hẹp hơn nếu điều kiện compile-time được đáp ứng. |
| “Gộp catch không ảnh hưởng đường đi của API.” | Thay kiểu tĩnh có thể thay overload được chọn; logic riêng biệt nên đánh giá trước khi gom. |
| “`instanceof` là cú pháp bắt buộc cho mọi multi-catch.” | Không; nếu dùng method chung và xử lý chung thì không cần; chỉ narrowing khi thật sự cần subtype-specific API. |

## 11. Checklist cho code review

Khi đọc hoặc sửa mã chứa multi-catch:

1. **Xác định hai (hoặc nhiều) exception types** được liệt kê; kiểm tra không có cặp subtype/supertype.
2. **Tìm LUB** bằng hệ phân cấp class/interface; thử biên dịch phép gán tới kiểu chung nếu cần xác minh.
3. **Kiểm tra member access:** method gọi trực tiếp trên `ex` có tồn tại trong kiểu chung không? Nếu không, tách catch hay thu hẹp kiểu hợp lệ.
4. **Rà soát overload:** method overload nào sẽ được chọn từ kiểu tĩnh của `ex`? Kết quả có giống điều kiện nghiệp vụ trước khi gộp catch không?
5. **Kiểm tra kiểu runtime:** khi cần phân nhánh theo subclass, dùng `instanceof`/pattern matching, không phụ thuộc vào chuỗi tên lớp.
6. **Xem tham số bị gán lại không:** multi-catch implicitly final. Với uni-catch có rethrow, giữ tham số effectively final khi cần precise rethrow.
7. **Kiểm tra hợp đồng `throws` và cause:** nếu ném lại hoặc wrap, giữ nguyên thông tin gốc, tránh biến checked exception thành một lỗi phụ `ClassCastException`.
8. **Chạy thử đủ loại exception:** một lần ném từng loại, kiểm tra output, các nhánh xử lý và trường hợp lỗi.
9. **Đánh giá chính sách vận hành:** việc gom catch có thực sự giảm trùng lặp mà không làm mất khác biệt retry, rollback, báo lỗi hay logging?

Trong code xử lý lỗi thật, nên log **đối tượng exception** để giữ nguyên cause/stack trace thay vì chỉ in `getMessage()` hoặc `getSimpleName()`. Các ví dụ nhỏ trong bài in chuỗi để kiểm tra hành vi có thể dự đoán được; đó không phải mẫu logging đầy đủ cho production.

## 12. Bài thực hành

**Bài 1 — Dự đoán overload:** Chạy `CatchObservedTypeDemo`. Vì sao khi runtime là `IOException`, kết quả vẫn là `overload=Exception`? Hãy thử tách thành hai `catch` và so sánh lời gọi `describe(...)`.

**Bài 2 — Đọc LUB:** Chạy `CommonParentCatchDemo`, thử thêm `ReflectiveOperationException r = ex;` và sau đó thử `ClassNotFoundException x = ex;`. Giải thích tại sao phép gán đầu biên dịch còn phép gán sau không.

**Bài 3 — Interface chung:** Chạy `SharedInterfaceCatchDemo`, thử bỏ `implements Retryable` khỏi `OutputProblem` rồi biên dịch lại. Vì sao `ex.canRetry()` không còn được compiler bảo đảm cho cả hai lựa chọn?

**Bài 4 — Thu hẹp kiểu:** Trong `CatchObservedTypeDemo`, dùng nhánh `instanceof SQLException sql` để gọi `getSQLState()`. Viết phiên bản dùng hai `catch` riêng và so sánh mức độ rõ ràng.

**Bài 5 — Precise rethrow:** Chạy `PreciseRethrowDemo`. Giữ chữ ký `throws IOException, SQLException` trên cả hai phương thức. Thử gán lại `ex` trong uni-catch rồi xem tác động tới việc phân tích `throw ex;`; trong multi-catch, compiler phản ứng ra sao?

**Bài 6 — Quyết định xử lý:** Một API đọc file rồi ghi dữ liệu. Chỉ gom lỗi I/O và SQL nếu có cùng cách xử lý; nếu một loại cần thử lại còn loại kia phải rollback, viết hai `catch` riêng. Kiểm tra không nuốt ngoại lệ và vẫn giữ cause khi wrap.

## 13. Kết luận

- **Kiểu khai báo trong multi-catch là LUB của các lựa chọn**, không phải kiểu runtime của lần ném cụ thể.
- **Runtime class vẫn nguyên**, nhưng compiler xét LUB cho member access, phép gán và overload.
- **LUB có thể giữ superclass hoặc interface chung**, như `ReflectiveOperationException` hoặc `Retryable`; không tự mặc định mọi trường hợp chỉ là `Exception`.
- **Dùng `instanceof` hoặc catch riêng** nếu cần method chuyên biệt, không dựa vào ép kiểu chưa được kiểm chứng.
- **Tham số multi-catch implicitly final**, và quy tắc precise rethrow giúp giữ hợp đồng checked exception hẹp trong trường hợp hợp lệ.
- **Multi-catch từ Java 7 vẫn hiện hành**; mã mới trên JDK 17+ có thể kết hợp pattern matching for `instanceof` để thu hẹp kiểu rõ ràng, an toàn.
- **Chỉ gom ngoại lệ khi chung chính sách xử lý**, bảo toàn cause và kiểm tra từng loại exception khi test.

## Tài liệu tham khảo chính thức

- [Java Language Specification, `14.20 — The try statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20): LUB, kiểu khai báo của tham số catch, implicitly final và điều kiện lựa chọn.
- [Java Language Specification, `11.2.2 — Exception analysis](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.2): phân tích những ngoại lệ có thể được ném.
- [Dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): hướng dẫn multi-catch hiện đại.
