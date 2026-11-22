# Bắt ngoại lệ theo kiểu đối tượng thực tế — `try` và `catch` trong Java

> **Ngữ cảnh:** Java Core → Exception → Try và catch. Khi một ngoại lệ được ném, Java chọn `catch` dựa trên **kiểu thực tế (runtime class) của đối tượng `Throwable` đang lan truyền** và quan hệ kế thừa của kiểu đó. Kiểu của biến tham chiếu tại nơi `throw`, tên kiểu trong `throws` và lớp nằm trong `getCause()` có vai trò riêng; chúng **không thay thế** kiểu runtime của đối tượng được ném khi quyết định nhánh `catch`.

## 1. Kết luận cần nhớ

Cho hai lớp:

```text
Throwable
└── Exception
    └── RuntimeException
        └── IllegalArgumentException
            └── NumberFormatException
```

Với đối tượng `new NumberFormatException(...)`:

- `catch (NumberFormatException e)` nhận được nó.
- `catch (IllegalArgumentException e)` cũng có thể nhận được nó vì là kiểu cha.
- `catch (RuntimeException e)`, `catch (Exception e)` và `catch (Throwable e)` cũng tương thích.
- `catch (IOException e)` không tương thích vì nhánh kế thừa khác.
- Nếu nhiều nhánh `catch` nối tiếp cùng một `try`, **nhánh tương thích đầu tiên theo thứ tự mã nguồn** được chọn. Vì Java kiểm tra các nhánh không thể tới được, nhánh cho lớp con phải đặt trước lớp cha bao trùm nó.

Phân biệt ngay hai thời điểm:

1. **Compile-time:** trình biên dịch kiểm tra cú pháp, kiểu hợp lệ của tham số `catch`, thứ tự handler và nghĩa vụ với checked exception.
2. **Runtime:** khi một đối tượng thực sự bị ném, JVM xét loại thực tế của đối tượng để tìm handler tương thích đang bao quanh đường thực thi.

Một biến có kiểu khai báo `Exception` hoàn toàn có thể trỏ đến `NumberFormatException`. Điều quan trọng với `catch` là **đối tượng thực tế**, miễn đoạn code đã qua kiểm tra của compiler.

## 2. Quy tắc chọn handler chi tiết

Dạng thường gặp:

```java
try {
    operation();
} catch (SpecificException e) {
    handleSpecific(e);
} catch (GeneralException e) {
    handleGeneral(e);
}
```

Đây là **mẫu cú pháp**, các lớp `SpecificException`/`GeneralException` và phương thức xử lý chưa được định nghĩa; không phải chương trình chạy độc lập.

Khi `operation()` ném một `Throwable` và lỗi thoát khỏi câu lệnh đó, Java tìm handler phù hợp theo chuỗi:

1. Xác định đối tượng `Throwable` đang bị ném, ví dụ một `NumberFormatException`.
2. Xem các handler thuộc khối `try` liên quan, theo thứ tự khai báo.
3. Với mỗi `catch (T e)`, kiểm tra đối tượng có phải instance của `T` hoặc lớp con của `T` không. Với multi-catch, chỉ cần khớp một trong các loại được khai báo.
4. Chọn handler **đầu tiên** thỏa điều kiện; biến `e` tham chiếu đến đối tượng đang được ném.
5. Nếu không có handler phù hợp ở phạm vi hiện tại, lỗi lan ra phương thức gọi; Java tiếp tục tìm handler bên ngoài và xử lý các bước dọn dẹp theo quy tắc.
6. Nếu lỗi không được xử lý đến ranh giới của thread, cơ chế uncaught exception của thread nhận được nó; không nên coi mọi ngoại lệ không bắt là lý do toàn bộ JVM phải kết thúc ngay.

**Điều quan trọng:** `catch` không dùng phép so sánh kiểu “phải giống hệt”. Nó hỗ trợ **đa hình**: handler khai báo kiểu cha có thể bắt exception thuộc một lớp con.

### 2.1. Phép kiểm tra tương thích kiểu

Về mặt trực giác, có thể hình dung quy tắc chọn một handler đơn như:

```java
// Minh họa tư duy, không phải implementation của JVM.
if (thrown instanceof HandlerType) {
    // Handler tương ứng có thể nhận đối tượng bị ném.
}
```

Đoạn trên là mã **minh họa**, `HandlerType` đại diện tên lớp catch thực tế. Java biên dịch handler thành cơ chế xử lý ngoại lệ, không chạy nguyên văn đoạn `if` này.

Một `catch (Exception e)` có thể bắt `IllegalArgumentException`, `IOException` hoặc `NullPointerException` vì tất cả là lớp con của `Exception`. Nhưng không bắt `AssertionError`, vì `AssertionError extends Error` và `Error` không kế thừa `Exception`.

### 2.2. Bảng kiểm tra nhanh

| Đối tượng thực tế được ném | `catch (NumberFormatException)` | `catch (IllegalArgumentException)` | `catch (Exception)` | `catch (Error)` |
| --- | --- | --- | --- | --- |
| `new NumberFormatException()` | Có | Có | Có | Không |
| `new IllegalArgumentException()` | Không | Có | Có | Không |
| `new IllegalStateException()` | Không | Không | Có | Không |
| `new java.io.IOException()` | Không | Không | Có | Không |
| `new AssertionError()` | Không | Không | Không | Có |

Bảng ghi **khả năng tương thích về kiểu**. Không thể ghép tùy ý mọi handler vào một `try` rồi hy vọng chương trình luôn biên dịch: Java còn kiểm tra thứ tự unreachable handler và tình trạng các checked exception có thể được ném từ vùng `try`.

## 3. Chương trình Java 17: cùng kiểu biến, nhiều kiểu đối tượng thực tế

Ví dụ này chứng minh điểm dễ nhầm nhất: tất cả phần tử trong mảng có **kiểu biến là `Exception`**, nhưng các đối tượng thực tế thuộc ba lớp khác nhau, nên mỗi lần ném có thể đi vào nhánh `catch` khác nhau.

Lưu tệp `CatchRuntimeTypeDemo.java`:

```java
import java.io.IOException;

public class CatchRuntimeTypeDemo {
    static void propagate(Exception problem) throws Exception {
        throw problem;
    }

    public static void main(String[] args) {
        Exception[] problems = {
                new NumberFormatException("không phải số"),
                new IllegalStateException("trạng thái sai"),
                new IOException("không đọc được")
        };

        for (Exception problem : problems) {
            try {
                propagate(problem);
            } catch (NumberFormatException e) {
                System.out.println("Parse: "
                        + e.getClass().getSimpleName());
            } catch (IOException e) {
                System.out.println("I/O: "
                        + e.getClass().getSimpleName());
            } catch (Exception e) {
                System.out.println("Còn lại: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CatchRuntimeTypeDemo.java
java CatchRuntimeTypeDemo
```

**Stdout chính xác:**

```text
Parse: NumberFormatException
Còn lại: IllegalStateException
I/O: IOException
```

Giải thích từng trường hợp:

- `problem` có **kiểu khai báo `Exception`** trong cả ba vòng lặp.
- Ở lượt đầu, đối tượng thực tế là `NumberFormatException`. Handler cụ thể nhận nó.
- Lượt hai là `IllegalStateException`. Nó không phải `NumberFormatException` hoặc `IOException`, nên được handler tổng quát `catch (Exception e)` nhận.
- Lượt ba là `IOException`. Handler `catch (IOException e)` nhận nó.
- `propagate(Exception problem) throws Exception` thực thi `throw problem;` và khai báo kiểu checked rộng `Exception`. Đây là ví dụ cố tình dùng chữ ký tổng quát để làm rõ khác biệt; trong API thực tế nên khai báo kiểu hẹp, có nghĩa nếu có thể.

Chúng ta **không cần ép kiểu** từ `Exception` sang `NumberFormatException` trước khi ném. Chỉ cần biến tham chiếu đến đúng đối tượng; kiểu runtime sẽ được sử dụng trong việc chọn handler.

### 3.1. Sự khác nhau giữa kiểu biến và kiểu đối tượng

Mẫu cốt lõi:

```java
Exception declaredAsException =
        new NumberFormatException("bad input");
// declaredAsException.getClass() là NumberFormatException.class.
```

Đây là đoạn minh họa trong method. Phía trái `Exception` là **kiểu tĩnh** mà compiler sử dụng để kiểm tra thao tác có thể gọi, đặc biệt đối với checked exceptions. Phía phải tạo đối tượng **`NumberFormatException`**. Không có “chuyển đổi” khiến đối tượng thành một `Exception` chung hơn; tham chiếu được gán lên kiểu cha nhưng đối tượng vẫn giữ đúng lớp của nó.

Gọi `getClass()` là cách quan sát kiểu runtime của đối tượng. Phép kiểm tra `instanceof` cũng phản ánh quan hệ instance/subtype, nhưng thường không cần tự dùng để chọn handler, vì cấu trúc `catch` đã giải quyết công việc đó.

## 4. Kế thừa quyết định phạm vi một handler

Cây phân cấp đơn giản:

```text
Throwable
├── Error
│   └── AssertionError
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    └── RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        └── IllegalStateException
```

Một `catch (IOException e)` có thể nhận `FileNotFoundException` hoặc `EOFException`. Tuy nhiên nó **không** nhận `NumberFormatException`, dù cả hai nhánh cuối cùng đều kế thừa `Exception`.

Ví dụ:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    System.out.println("Chuỗi không phải số");
} catch (IllegalArgumentException e) {
    System.out.println("Tham số sai theo quy tắc khác");
}
```

Đây là một **đoạn bên trong method**. `NumberFormatException` kế thừa `IllegalArgumentException` nên cả hai handler **đều tương thích về kiểu**, nhưng handler cụ thể đứng trước nhận đối tượng. Handler sau sẽ chỉ được xét nếu handler trước không tương thích với ngoại lệ khác được ném.

### 4.1. Vì sao phải đặt `catch` của lớp con trước lớp cha?

Đoạn sau **cố ý sai, không biên dịch**:

```java
try {
    Integer.parseInt("abc");
} catch (IllegalArgumentException e) {
    System.out.println("Đã bắt");
} catch (NumberFormatException e) {
    System.out.println("Không thể tới đây");
}
```

`IllegalArgumentException` đã bao phủ `NumberFormatException`. Handler thứ hai không có cơ hội nhận đối tượng nào còn sót lại thuộc loại `NumberFormatException`, nên Java báo lỗi như “exception NumberFormatException has already been caught”.

Sắp đúng từ **cụ thể đến tổng quát**:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    System.out.println("Sai định dạng số");
} catch (IllegalArgumentException e) {
    System.out.println("Sai tham số");
}
```

Cũng là đoạn minh họa, không có `main`. Thứ tự ở đây không làm thay đổi kiểu đối tượng; nó quyết định **handler đầu tiên có cơ hội nhận**.

### 4.2. Mỗi ngoại lệ chỉ đi vào một nhánh `catch` của cùng một `try`

Khi handler phù hợp đã được chọn, Java không tự thực thi các `catch` còn lại như chuỗi `if`. Nếu cần phân loại chi tiết trước khi gom về xử lý chung, hãy để handler cụ thể gọi một phương thức xử lý chung, hoặc chuẩn hóa thông tin tại một tầng có trách nhiệm. Không trông chờ `catch (Exception)` phía sau được chạy tiếp sau `catch (NumberFormatException)`.

## 5. Checked exception ảnh hưởng compiler, không đổi matching runtime

**Checked** và **unchecked** là quy tắc về việc có bắt buộc bắt hoặc khai báo khi biên dịch hay không:

- Checked exception gồm các lớp con của `Throwable` không thuộc nhánh `RuntimeException` hoặc `Error`, ví dụ `IOException`.
- Unchecked gồm `RuntimeException`, `Error` và các lớp con, ví dụ `NumberFormatException` hoặc `AssertionError`.

Dù `NumberFormatException` là unchecked, `catch (Exception e)` vẫn bắt được, bởi `NumberFormatException extends RuntimeException extends Exception`.

Ngược lại, một lớp tự tạo **kế thừa trực tiếp `Throwable`** có thể là checked nhưng `catch (Exception)` vẫn không bắt được, vì lớp đó không ở dưới `Exception`. Do vậy:

**Việc một exception là checked hay unchecked không phải tiêu chí chọn handler ở runtime. Quan hệ kiểu kế thừa mới là tiêu chí.**

### 5.1. Kiểu tĩnh ảnh hưởng nghĩa vụ `throws`

Ví dụ:

```java
// Đây là đoạn minh họa nằm trong method, không phải chương trình đầy đủ.
Exception e = new NumberFormatException("sai số");
// throw e; // Nếu bỏ comment: thông thường cần bắt hoặc khai báo Exception.
```

Vì biểu thức `e` có **kiểu khai báo `Exception`**, compiler xét `throw e;` theo kiểu checked rộng này, mặc dù đối tượng cụ thể ở lần chạy minh họa là unchecked. Đây không phải dấu hiệu rằng `catch` sẽ chọn theo `Exception`: ở runtime, nếu đối tượng được ném vẫn là `NumberFormatException` thì `catch (NumberFormatException)` vẫn khớp.

Cần phân biệt với **precise rethrow** từ Java 7: trong một số điều kiện với biến tham số của `catch` không bị gán lại, compiler có thể suy luận tập checked exception cụ thể khi gặp `throw e;`. Đó là một quy tắc đặc biệt của ngôn ngữ cho việc phân tích checked exception, không thay đổi cách chọn handler runtime.

### 5.2. Ví dụ `throws IOException` nhưng runtime là lớp con

Method:

```java
static void load() throws java.io.IOException {
    throw new java.io.FileNotFoundException("Không tìm thấy dữ liệu");
}
```

Đoạn minh họa trên hợp lệ vì `FileNotFoundException extends IOException`. Caller có thể viết `catch (FileNotFoundException e)` trước `catch (IOException e)` nếu khối `try` có thể nhận lỗi loại tương ứng. Khi thực thi, nếu chính đối tượng `FileNotFoundException` được ném, handler hẹp được chọn. Tên `IOException` trong mệnh đề `throws` chỉ công bố kiểu checked mà caller phải xem xét; nó không “biến” đối tượng thành lớp `IOException`.

## 6. Chương trình Java 17: nhiều lớp con của `IOException`

Ví dụ thứ hai nhấn mạnh việc **cùng một method khai báo `throws IOException`**, nhưng mỗi lần chạy có thể ném một subtype khác nhau; handler xử lý theo kiểu thực tế.

Lưu `CatchIoSubtypeDemo.java`:

```java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchIoSubtypeDemo {
    static void read(String mode) throws IOException {
        switch (mode) {
            case "missing" ->
                    throw new FileNotFoundException("Thiếu tệp");
            case "empty" ->
                    throw new EOFException("Hết dữ liệu");
            default ->
                    throw new IOException("Lỗi I/O chung");
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {"missing", "empty", "other"}) {
            try {
                read(mode);
            } catch (FileNotFoundException e) {
                System.out.println(mode + ": thiếu tệp");
            } catch (EOFException e) {
                System.out.println(mode + ": hết dữ liệu");
            } catch (IOException e) {
                System.out.println(mode + ": lỗi I/O chung");
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CatchIoSubtypeDemo.java
java CatchIoSubtypeDemo
```

Stdout:

```text
missing: thiếu tệp
empty: hết dữ liệu
other: lỗi I/O chung
```

Diễn giải:

- Ở chế độ `"missing"`, method tạo `FileNotFoundException` và handler `FileNotFoundException` nhận nó.
- Ở chế độ `"empty"`, method tạo `EOFException` và handler `EOFException` nhận nó.
- Ở chế độ `"other"`, method tạo chính `IOException` và handler tổng quát `IOException` nhận nó.
- Cả ba đều thỏa khai báo `throws IOException`; khai báo này không khống chế mọi lời gọi phải ném cùng một subtype.
- Khi có một handler cụ thể khớp, nhánh `catch (IOException)` cuối không chạy tiếp.

**Điểm thiết kế:** bắt subtype riêng khi caller có hành động riêng, ví dụ cho phép chọn file khác nếu không tìm thấy, kết thúc đọc khi gặp EOF theo hợp đồng phù hợp, hoặc dừng thao tác với lỗi I/O khác. Nếu không có hành động khác nhau, một `catch (IOException)` chung có thể là đủ.

## 7. Kiểu runtime quyết định matching, nhưng thứ tự handler vẫn quan trọng

Khi nhiều handler cùng tương thích với một đối tượng, Java chọn handler **đầu tiên trong cùng chuỗi `catch`**. Tuy nhiên compiler loại trừ nhiều sắp xếp khiến nhánh sau không thể tới được.

Xét `new NumberFormatException()`:

```text
catch (NumberFormatException e)  ← phù hợp và đứng trước: nhận lỗi
catch (IllegalArgumentException e) ← cũng tương thích nhưng không chạy
catch (Exception e)              ← cũng tương thích nhưng không chạy
```

Nếu thay thứ tự và đặt `catch (Exception e)` lên đầu, các handler lớp con sau sẽ bị che và compile error. Vì vậy quy tắc thực hành vừa đúng ngữ nghĩa vừa giúp compiler chấp nhận mã là:

> **Đặt `catch` của lớp con/cụ thể trước, `catch` của lớp cha/tổng quát sau.**

Không phải các lớp exception nào cũng có quan hệ cha–con. Chẳng hạn `FileNotFoundException` và `NumberFormatException` không bao phủ nhau; về mặt kiểu, có thể đặt chúng theo thứ tự nào cũng được nếu khối `try` có thể phát sinh các kiểu checked tương ứng. Thứ tự quan trọng nhất khi có **quan hệ bao hàm**.

### 7.1. Một lưu ý về các nested `try`

Java không so sánh mọi `catch` trong cả chương trình cùng lúc. Handler ở `try` **gần nơi phát sinh lỗi** được xét trước trong phạm vi điều khiển tương ứng; nếu không có handler phù hợp, lỗi mới lan ra ngoài.

Ví dụ:

```java
try {
    try {
        Integer.parseInt("abc");
    } catch (IllegalArgumentException e) {
        System.out.println("Bắt bên trong");
    }
} catch (NumberFormatException e) {
    System.out.println("Bắt bên ngoài");
}
```

Đây là đoạn minh họa đặt trong method. Vì `IllegalArgumentException` bên trong nhận `NumberFormatException`, handler ngoài không được thực hiện. Ngoại lệ đã được xử lý trong phạm vi gần hơn; không có “cơ chế chọn handler cụ thể nhất của toàn bộ chương trình”.

Nếu handler trong **ném lại** exception, nó có thể lan ra `catch` của `try` bao ngoài, nhưng khi đó là một bước lan truyền tiếp theo, không phải Java bỏ qua handler trong để tự chọn handler ngoài.

## 8. Multi-catch cũng áp dụng theo kiểu đối tượng

Từ Java 7, có thể gộp các handler có cùng logic:

```java
catch (java.io.IOException | IllegalArgumentException e) {
    System.out.println("Không xử lý được yêu cầu: " + e.getMessage());
}
```

Đoạn trên là phần `catch` minh họa, phải đi sau một `try` phù hợp. Multi-catch khớp nếu đối tượng là một instance của **ít nhất một** kiểu được liệt kê. `IOException` và `IllegalArgumentException` thuộc hai nhánh riêng nên có thể viết chung.

Java **không cho phép** các kiểu trong cùng một multi-catch có quan hệ kế thừa trực tiếp hoặc gián tiếp theo kiểu một nhánh đã bao trùm nhánh kia. Ví dụ sai:

```java
// KHÔNG hợp lệ:
catch (NumberFormatException | IllegalArgumentException e) {
    System.out.println(e);
}
```

`NumberFormatException extends IllegalArgumentException` nên khai báo hai lựa chọn này là thừa và bị compiler từ chối.

### 8.1. Chương trình Java 17 chạy độc lập với multi-catch

Lưu `MultiCatchRuntimeDemo.java`:

```java
import java.io.IOException;

public class MultiCatchRuntimeDemo {
    static void execute(String input) throws IOException {
        if (input == null) {
            throw new IOException("Nguồn trống");
        }
        int number = Integer.parseInt(input);
        if (number <= 0) {
            throw new IllegalArgumentException("Phải dương");
        }
        System.out.println("OK: " + number);
    }

    public static void main(String[] args) {
        for (String input : new String[] {"5", "abc", "0", null}) {
            try {
                execute(input);
            } catch (IOException | IllegalArgumentException e) {
                System.out.println("Lỗi: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MultiCatchRuntimeDemo.java
java MultiCatchRuntimeDemo
```

Stdout:

```text
OK: 5
Lỗi: NumberFormatException
Lỗi: IllegalArgumentException
Lỗi: IOException
```

`NumberFormatException` được multi-catch nhận **qua nhánh `IllegalArgumentException`**. `IOException` được nhận qua nhánh kia. Cùng một khối xử lý dùng `getClass().getSimpleName()` để quan sát subtype thực sự, nên tên in ra vẫn khác nhau.

Biến `e` trong multi-catch là **implicitly final**, không được gán lại. Kiểu tĩnh chung của `e` cũng không nhất thiết là từng kiểu con cụ thể; nếu cần API riêng cho một subtype, nên dùng handler riêng hoặc kiểm tra kiểu cẩn thận.

## 9. `catch (Exception)` không bắt mọi `Throwable`

Một điều kiện cơ bản về cây phân cấp:

```text
Throwable
├── Exception
│   └── RuntimeException
│       └── NumberFormatException
└── Error
    └── AssertionError
```

`catch (Exception e)` có thể xử lý `NumberFormatException`, nhưng **không** bắt `AssertionError` vì `Error` không kế thừa `Exception`. `catch (Throwable t)` có thể bắt cả hai **về mặt kiểu**, nhưng không nên dùng như giải pháp “đỡ mọi lỗi” trong mã ứng dụng.

### 9.1. Minh họa không gây lỗi JVM thật

Lưu `CatchThrowableBranchesDemo.java`:

```java
public class CatchThrowableBranchesDemo {
    static void fail(boolean useError) {
        if (useError) {
            throw new AssertionError("Tình huống kiểm thử");
        }
        throw new IllegalStateException("Trạng thái không hợp lệ");
    }

    public static void main(String[] args) {
        for (boolean useError : new boolean[] {false, true}) {
            try {
                fail(useError);
            } catch (Exception e) {
                System.out.println("Exception: "
                        + e.getClass().getSimpleName());
            } catch (Error e) {
                System.out.println("Error: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CatchThrowableBranchesDemo.java
java CatchThrowableBranchesDemo
```

Stdout:

```text
Exception: IllegalStateException
Error: AssertionError
```

Ví dụ **chủ động tạo `AssertionError` để giải thích hệ kiểu**; đây không phải khuyến nghị bắt `Error` để cố hồi phục sau lỗi VM như `OutOfMemoryError` hoặc `StackOverflowError`. Đừng tạo các lỗi VM thực chỉ để thử handler, vì có thể làm tiến trình không còn đủ tài nguyên để chạy bình thường.

### 9.2. Checked/unchecked không quyết định handler

- `IOException` là checked và nằm trong `Exception`.
- `IllegalStateException` là unchecked và cũng nằm trong `Exception`.
- `AssertionError` là unchecked nhưng nằm trong `Error`.

Cả checked và unchecked đều tuân cùng nguyên tắc chọn `catch` theo **runtime type**. Phân loại checked/unchecked chỉ quy định một số nghĩa vụ lúc biên dịch.

## 10. Wrapper và `cause`: Java bắt lớp ở ngoài đang được ném

Một ngoại lệ có thể chứa một ngoại lệ khác làm **nguyên nhân** (`cause`). Ví dụ:

```java
throw new IllegalStateException(
        "Không hoàn tất thao tác",
        new java.io.IOException("Nguồn dữ liệu lỗi"));
```

Ở đây:

- Đối tượng **đang được ném** là `IllegalStateException`.
- `getCause()` của nó trỏ đến `IOException`.
- Handler `catch (IllegalStateException)` hoặc `catch (Exception)` có thể nhận wrapper.
- Handler `catch (IOException)` không tự lấy `cause` để bắt; muốn xử lý nguyên nhân thì cần kiểm tra sau khi đã nhận wrapper ở tầng thích hợp.

Cơ chế này tránh hiểu lầm rằng Java tự “bóc” chuỗi nguyên nhân để đi chọn handler. **Nó so kiểu của đối tượng đang được ném**, không đi tìm kiểu phù hợp sâu nhất trong `getCause()`.

### 10.1. Chương trình Java 17 chứng minh wrapper/cause

Tạo `CatchWrapperTypeDemo.java`:

```java
import java.io.IOException;

public class CatchWrapperTypeDemo {
    static void load() {
        IOException original = new IOException("Không đọc được");
        throw new IllegalStateException("Không tải được dữ liệu", original);
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (IllegalStateException e) {
            System.out.println("Đã bắt: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CatchWrapperTypeDemo.java
java CatchWrapperTypeDemo
```

Stdout:

```text
Đã bắt: IllegalStateException
Cause: IOException
Message: Không tải được dữ liệu
```

Trong đoạn này, `IOException` chỉ được **tạo và truyền vào constructor** làm nguyên nhân; nó không tự lan ra khỏi `load()` như đối tượng exception chính. Vì vậy `load()` không cần khai báo `throws IOException`. Handler ở `main` nhận đúng `IllegalStateException`.

**Tình huống ngược:** nếu wrapper là một `IOException` với cause là `IllegalStateException` thì handler được chọn vẫn theo lớp của wrapper `IOException`. Cause giữ thông tin chẩn đoán và ngữ cảnh, không thay thế cơ chế matching.

### 10.2. Rethrow có thay đổi kiểu runtime không?

`throw e;` ném lại **chính đối tượng** mà `e` tham chiếu. Nó không tự chuyển đối tượng về kiểu khai báo của biến.

Ví dụ:

```java
// Minh họa trong method có throws Exception.
Exception e = new NumberFormatException("Sai số");
throw e;
```

Nếu runtime ném thành công, đối tượng vẫn là `NumberFormatException`. Khai báo `throws Exception` cần thiết do việc kiểm tra kiểu tĩnh trong trường hợp điển hình này, nhưng handler tương thích tại caller sẽ xét loại đối tượng thực tế.

Ngược lại, `throw new IllegalStateException("...", e)` tạo wrapper mới: **kiểu runtime của ngoại lệ đang lan truyền đã trở thành `IllegalStateException`**, còn `e` là cause. Đó là sự khác biệt lớn khi quyết định nên ném lại hay chuyển đổi ngoại lệ.

## 11. Ngoại lệ phát sinh trong `catch` có thể được bắt bởi nhánh `catch` kế bên không?

Không. Các nhánh `catch` của cùng một `try` là những **handler thay thế**, chứ không bao quanh nhau. Một ngoại lệ mới được ném **trong chính handler** sẽ không được những handler kế tiếp gắn với cùng `try` tự bắt.

Ví dụ:

```java
try {
    try {
        throw new NumberFormatException("bad");
    } catch (NumberFormatException e) {
        throw new IllegalStateException("Bọc lỗi", e);
    } catch (IllegalStateException e) {
        System.out.println("Không bắt wrapper từ catch phía trên");
    }
} catch (IllegalStateException e) {
    System.out.println("Wrapper được bắt ở try ngoài");
}
```

Đây là đoạn minh họa trong method. Handler `NumberFormatException` được chọn khi exception gốc được ném; handler đó lại tạo `IllegalStateException` mới. Handler `IllegalStateException` còn lại của **cùng `try` trong** không chạy; handler tương thích của `try` **ngoài** nhận wrapper.

Cần lưu ý compiler chỉ kiểm tra các nhánh unreachable theo quy tắc kiểu, còn sự khác nhau giữa lỗi ném trong `try` và lỗi ném trong `catch` là quy tắc **phạm vi xử lý**. Đừng suy luận rằng hai nhánh handler là một chuỗi xử lý tuần tự.

## 12. Vai trò của `finally` và try-with-resources

Khi exception được ném và một handler phù hợp được tìm thấy, các khối `finally` liên quan được thực thi theo quy tắc Java khi rời khỏi phạm vi. Cơ chế này hỗ trợ dọn dẹp nhưng **không tự quyết định lại** loại exception nào đang được lan truyền.

```java
try {
    throw new NumberFormatException("bad");
} catch (IllegalArgumentException e) {
    System.out.println("Đã bắt ngoại lệ con qua kiểu cha");
} finally {
    System.out.println("Đã dọn dẹp");
}
```

Đoạn minh họa trên in:

```text
Đã bắt ngoại lệ con qua kiểu cha
Đã dọn dẹp
```

`NumberFormatException` thực sự được ném, nhưng handler `IllegalArgumentException` vẫn nhận được vì quan hệ kế thừa.

**Ngoại lệ quan trọng:** nếu `finally` tự ném một exception khác hoặc thực hiện `return`, nó có thể thay thế/che mất kết quả hoặc exception đang chờ lan truyền. Nên tránh viết `return` trong `finally` hoặc tự ý ném lỗi mới từ phần dọn dẹp nếu mục tiêu là bảo toàn nguyên nhân gốc.

Với try-with-resources, nếu thân khối và `close()` đều ném exception, Java thường giữ lỗi từ thân khối làm exception chính và gắn lỗi khi đóng vào `getSuppressed()`. `catch` của luồng ngoài so với **exception chính đang được ném**, không so trực tiếp với suppressed exceptions.

## 13. Các câu hỏi kiểm tra nhanh

### 13.1. Biến `Exception` có thể bị `catch (IOException)` bắt không?

**Có**, nếu đối tượng thực tế được ném là `IOException` hoặc subtype và đoạn code hợp lệ theo quy tắc checked exception. Trong `CatchRuntimeTypeDemo`, `problem` có kiểu biến `Exception`, song lượt thứ ba được `catch (IOException)` nhận đúng.

### 13.2. `catch (Exception)` có bắt tất cả unchecked exceptions không?

**Không.** Nó bắt các unchecked exception thuộc nhánh `RuntimeException`, vì `RuntimeException extends Exception`. Nó không bắt các loại unchecked thuộc nhánh `Error`, ví dụ `AssertionError`.

### 13.3. `catch (Throwable)` có bắt mọi lỗi bất kể nơi phát sinh không?

**Không.** Nó là handler rộng theo hệ kiểu Java, nhưng chỉ xử lý các `Throwable` lan đến handler trên **luồng điều khiển đang được bảo vệ**. Nó không tự bắt exception xảy ra trên một thread khác, không bảo vệ khỏi JVM/process bị chấm dứt bất thường và không rollback side effect.

### 13.4. Handler hẹp nhất luôn được chọn dù nằm sau handler rộng hơn?

**Không.** Java dùng handler tương thích **đầu tiên trong phạm vi `catch` tương ứng**. Compiler chặn nhiều thứ tự khiến handler sau bị che bởi handler rộng ở trước. Java không đi tìm “handler nhỏ nhất trên toàn call stack” rồi bỏ qua handler gần hơn.

### 13.5. Nếu `getCause()` là `IOException`, `catch (IOException)` có bắt wrapper `IllegalStateException` không?

**Không.** `cause` là quan hệ nguyên nhân để chẩn đoán, không tham gia trực tiếp việc chọn `catch`. Muốn xử lý có ngữ nghĩa theo cause, trước hết bắt wrapper phù hợp rồi kiểm tra cause có chủ đích.

### 13.6. `catch (IllegalArgumentException)` bắt `NumberFormatException` thì `e.getClass()` trả gì?

Nó trả **`NumberFormatException.class`**, vì biến `e` vẫn tham chiếu đối tượng con. Java không thay đổi lớp thực tế của đối tượng chỉ vì handler có kiểu khai báo rộng hơn.

### 13.7. Một exception có thể được xử lý bởi hai handler cùng một khối `try` không?

**Không tự động.** Một exception đang được ném chọn một handler đầu tiên. Nếu handler ném lại hoặc tạo exception mới, một handler ở phạm vi bao ngoài có thể tiếp tục nhận, nhưng không phải nhánh kế tiếp của cùng chuỗi `catch`.

## 14. Các sai lầm thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Biến có kiểu `Exception` thì chỉ `catch (Exception)` được bắt.” | Kiểu thực tế của đối tượng có thể là subtype; handler hẹp tương thích vẫn nhận được. |
| “`throws IOException` làm exception thực tế đổi thành `IOException`.” | Mệnh đề `throws` khai báo hợp đồng checked; đối tượng `FileNotFoundException` vẫn giữ nguyên lớp của nó. |
| “`catch` chỉ nhận đúng cùng tên class.” | Kiểu cha cũng nhận được đối tượng thuộc lớp con. |
| “Các `catch` chạy lần lượt như nhiều phép `if` độc lập.” | Chỉ handler tương thích đầu tiên của cùng `try` được thực hiện. |
| “`catch (Exception)` đứng trước `catch (NumberFormatException)` là hợp lệ vì rộng hơn.” | Nhánh sau bị che và bị compiler từ chối. |
| “Unchecked exception không thể bị `catch`.” | Unchecked không bắt buộc xử lý compile-time nhưng vẫn có thể được bắt. |
| “`catch (Exception)` bắt `AssertionError` vì cũng là Throwable.” | `AssertionError` nằm dưới `Error`, là nhánh khác `Exception`. |
| “Handler tự tìm `getCause()` để chọn lớp lỗi phù hợp.” | Handler chỉ đối chiếu kiểu của đối tượng đang được ném. |
| “Exception ném trong `catch` sẽ được nhánh `catch` tiếp theo xử lý.” | Nó thoát ra phạm vi ngoài nếu không được xử lý bởi một `try` mới. |
| “Bắt được lỗi thì toàn bộ trạng thái trước đó trở về như cũ.” | `catch` không tự rollback thay đổi dữ liệu, I/O hoặc giao dịch. |
| “Bắt `Throwable` mọi nơi sẽ an toàn hơn.” | Có thể che lỗi nghiêm trọng của runtime và khiến chương trình tiếp tục trên trạng thái không tin cậy. |
| “Stack trace là một danh sách handler đã thử.” | Stack trace phản ánh chuỗi lời gọi và nguồn gốc lỗi; không phải log đầy đủ thứ tự thử từng nhánh `catch`. |

## 15. Bài tập thực hành

### Bài tập 1 — Dự đoán handler theo lớp thực tế

Cho đoạn minh họa:

```java
Exception problem = new NumberFormatException("Sai");
try {
    throw problem;
} catch (NumberFormatException e) {
    System.out.println("A");
} catch (IllegalArgumentException e) {
    System.out.println("B");
} catch (Exception e) {
    System.out.println("C");
}
```

Đây là đoạn code đặt trong phương thức đã xử lý nghĩa vụ checked exception tại handler. **Đáp án:** in `A`. Dù `problem` là biến kiểu `Exception`, đối tượng thực tế thuộc `NumberFormatException`. Nếu bỏ nhánh `catch (NumberFormatException)`, kết quả trở thành `B`; nếu bỏ tiếp `catch (IllegalArgumentException)`, kết quả trở thành `C`.

### Bài tập 2 — Sửa lỗi unreachable handler

Từ:

```java
try {
    Integer.parseInt("x");
} catch (RuntimeException e) {
    System.out.println("Rộng");
} catch (NumberFormatException e) {
    System.out.println("Hẹp");
}
```

Hãy đổi thứ tự để handler `NumberFormatException` đứng trước. Giải thích vì sao đoạn gốc không biên dịch: `NumberFormatException` là lớp con của `RuntimeException` và đã bị handler rộng bao phủ.

### Bài tập 3 — Thay wrapper và dự đoán nhánh xử lý

Trong `CatchWrapperTypeDemo`, thử thay `IllegalStateException` bằng `java.io.UncheckedIOException` có cause là `IOException`, rồi thay handler ngoài để bắt `UncheckedIOException` hoặc `RuntimeException`. Giải thích vì sao handler `catch (IOException)` không tự nhận wrapper. Nếu dùng constructor thực tế `new UncheckedIOException(original)`, nhớ import `java.io.UncheckedIOException`.

### Bài tập 4 — Đọc exception qua nhiều tầng

Viết ba method `main() → service() → parse()`. Trong `parse()` ném `NumberFormatException`; trong `service()` khai báo `throws Exception` hoặc chuyển tiếp exception phù hợp; tại `main()` bắt riêng `NumberFormatException`. Giải thích **kiểu static được compiler đọc ở từng lời gọi** và **kiểu runtime được handler so khớp**.

### Bài tập 5 — Thay chuỗi `catch` bằng multi-catch

Với `MultiCatchRuntimeDemo`, thay handler multi-catch bằng hai handler riêng `IOException` và `IllegalArgumentException` để mỗi loại hiển thị thông điệp khác nhau. Có cần thêm handler riêng cho `NumberFormatException` không? **Không bắt buộc** vì `IllegalArgumentException` đã bao phủ nó, nhưng có thể thêm **trước** handler cha nếu cần báo lỗi parse riêng.

### Bài tập 6 — Lỗi ném trong handler

Dự đoán stdout của ví dụ ở Mục 11. Giải thích tại sao handler ngoài nhận được `IllegalStateException` mới và vì sao handler `catch (IllegalStateException)` còn lại của `try` trong không chạy.

## 16. Checklist hiểu đúng

- [ ] Phân biệt được **kiểu biến**, **kiểu khai báo trong `throws`** và **kiểu runtime của đối tượng**.
- [ ] Vẽ được quan hệ `NumberFormatException → IllegalArgumentException → RuntimeException → Exception → Throwable`.
- [ ] Giải thích vì sao `catch (IOException)` bắt được `FileNotFoundException` và `EOFException`.
- [ ] Đặt handler cho lớp con trước handler lớp cha để tránh unreachable catch.
- [ ] Chạy `CatchRuntimeTypeDemo.java` và giải thích cả ba dòng stdout.
- [ ] Chạy `CatchIoSubtypeDemo.java` và dự đoán đúng handler cho từng subtype.
- [ ] Viết multi-catch với hai kiểu không có quan hệ kế thừa và nêu lý do không được dùng các kiểu bao trùm nhau.
- [ ] Biết `catch (Exception)` bắt unchecked `RuntimeException` nhưng không bắt `Error`.
- [ ] Phân biệt wrapper và cause; handler dựa trên wrapper đang được ném, không tự đi xuống `cause`.
- [ ] Nhận ra exception ném từ một `catch` cần handler ở phạm vi khác phù hợp.
- [ ] Không nhầm `finally`/try-with-resources với cơ chế chọn handler hoặc rollback.
- [ ] Thiết kế `catch` theo khả năng xử lý thực sự, không nuốt lỗi một cách vô điều kiện.

**Ghi nhớ cuối:** **Runtime type** của đối tượng `Throwable` đang được ném quyết định những `catch` nào tương thích; phạm vi `try` và thứ tự các nhánh quyết định handler được chọn; compiler kiểm tra các quy tắc kiểu và checked exception trước khi chương trình chạy. Hiểu đồng thời cả ba giúp dự đoán đúng luồng xử lý lỗi trong Java.