# Catch không thể tới do khối catch trước đã bao phủ

## 1. Mục tiêu học tập

Trong Java, các mệnh đề `catch` của **cùng một câu lệnh `try`** được xét theo thứ tự từ trên xuống khi xảy ra ngoại lệ. Nếu một `catch` đứng trước đã bắt được **mọi đối tượng thuộc kiểu mà `catch` đứng sau định bắt**, `catch` đứng sau không có cơ hội nhận ngoại lệ. Java phát hiện trường hợp này khi biên dịch và báo lỗi.

Sau bài học, bạn có thể:

- Giải thích vì sao thứ tự `catch` liên quan trực tiếp đến quan hệ kế thừa giữa các lớp ngoại lệ.
- Nhận ra lỗi một `catch` không thể tới được vì `catch` trước đã bao phủ kiểu của nó.
- Sắp xếp các handler từ kiểu cụ thể đến kiểu tổng quát mà vẫn giữ đúng ý nghĩa xử lý.
- Phân biệt **lỗi thứ tự do bị bao phủ** với **lỗi do bắt checked exception không thể được ném từ khối `try`**.
- Viết đúng `multi-catch` và nhận ra trường hợp các nhánh của multi-catch bị trùng quan hệ cha–con.
- Hiểu tác động của `catch (Exception)`, `catch (Throwable)`, các nhánh anh em, `try` lồng nhau và `finally`.
- Đọc lỗi của `javac`, sửa đúng vị trí và kiểm tra lại bằng chương trình Java 17+.

## 2. Cơ chế lựa chọn `catch` khi một ngoại lệ xuất hiện

Một `try` có thể có nhiều `catch` đứng liên tiếp:

```java
try {
    riskyOperation();
} catch (SpecificException e) {
    handleSpecific(e);
} catch (GeneralException e) {
    handleGeneral(e);
}
```

Đây là đoạn mã minh họa, cần định nghĩa các kiểu ngoại lệ và phương thức tương ứng. Về nguyên tắc, Java xem các `catch` theo **thứ tự viết trong mã nguồn**, chọn handler đầu tiên có kiểu tương thích với **đối tượng ngoại lệ thực tế**. Các `catch` còn lại của cùng `try` không chạy cho đối tượng đó.

Điều kiện tương thích có thể hiểu theo phép gán kiểu tham chiếu: một handler kiểu `Exception` có thể nhận đối tượng `IOException` vì `IOException` kế thừa `Exception`; handler kiểu `IOException` không nhận một đối tượng `Exception` bất kỳ.

Ví dụ sơ đồ rút gọn:

```text
java.lang.Throwable
├── java.lang.Error
│   ├── AssertionError
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException
    │   ├── java.io.FileNotFoundException
    │   └── ...
    ├── java.sql.SQLException
    └── java.lang.RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── NullPointerException
        └── ...
```

Đây là các nhánh tiêu biểu, không phải toàn bộ cây `Throwable`.

Hai quy tắc cần ghi nhớ:

1. **Lớp cha đứng trước lớp con trong các `catch` cùng cấp** là một trường hợp bị bao phủ: `catch (Exception)` đứng trước `catch (IOException)` khiến nhánh sau không thể được chọn.
2. **Lớp con đứng trước lớp cha** có thể hợp lệ: `catch (FileNotFoundException)` rồi `catch (IOException)` cho phép xử lý lỗi không tìm thấy file riêng, còn các lỗi I/O khác do handler rộng hơn nhận.

`catch` không hoạt động như câu lệnh `if` độc lập mà mọi nhánh có thể lần lượt chạy. Chỉ một handler của **cùng `try`** được chọn cho ngoại lệ đang lan truyền; sau khi handler đó hoàn tất, không có cơ chế “fall-through” sang handler tiếp theo.

## 3. Vì sao Java từ chối một `catch` đã bị bao phủ?

Xét ví dụ sau. **Đây là mã cố ý không biên dịch**; lưu thành `WrongCatchOrder.java` để quan sát lỗi:

```java
import java.io.IOException;

public class WrongCatchOrder {
    public static void main(String[] args) {
        try {
            throw new IOException("read failed");
        } catch (Exception failure) {
            System.out.println("general handler");
        } catch (IOException failure) {
            System.out.println("IO handler");
        }
    }
}
```

Lệnh kiểm tra:

```bash
javac WrongCatchOrder.java
```

`javac` báo lỗi biên dịch tại handler `catch (IOException failure)`. Thông điệp tiếng Anh trên JDK phổ biến có ý tương đương **“exception IOException has already been caught”**; vị trí và định dạng chi tiết có thể khác theo phiên bản/compiler. Không có lệnh `java WrongCatchOrder` hợp lệ vì quá trình biên dịch chưa tạo chương trình thành công.

Nguyên nhân:

- Kiểu thực tế `IOException` có thể gán cho `Exception`.
- Handler `catch (Exception)` đứng trước và đã bao phủ toàn bộ các đối tượng `IOException`.
- Do đó handler `catch (IOException)` ở dưới không bao giờ được chọn trong cùng `try`.
- Trình biên dịch phát hiện xung đột này ngay cả khi không chạy chương trình; đây là **lỗi ngôn ngữ tại compile time**.

Việc đặt `throw new IOException(...)` trong khối `try` chỉ giúp ví dụ có tình huống rõ ràng. Ngay cả khi luồng thực thi thực tế chưa từng phát sinh lỗi, **mối quan hệ kiểu và thứ tự handler** vẫn khiến hai handler ở trên không hợp lệ.

### Cách sửa

Đặt handler cụ thể trước, handler rộng sau:

```java
import java.io.IOException;

public class CorrectCatchOrder {
    public static void main(String[] args) {
        try {
            throw new IOException("read failed");
        } catch (IOException failure) {
            System.out.println("IO handler: " + failure.getMessage());
        } catch (Exception failure) {
            System.out.println("general handler");
        }
    }
}
```

Lưu thành **`CorrectCatchOrder.java`**, biên dịch và chạy:

```bash
javac CorrectCatchOrder.java
java CorrectCatchOrder
```

Kết quả `stdout` chính xác:

```text
IO handler: read failed
```

`catch (IOException)` nhận đối tượng và in thông tin lỗi. `catch (Exception)` ở cuối không chạy đối với lần ném này. Handler rộng có thể phục vụ những ngoại lệ thuộc nhánh `Exception` khác mà đoạn `try` có thể ném. Trong ví dụ đơn giản, handler rộng không bắt buộc để xử lý riêng `IOException`, nhưng cấu trúc **cụ thể trước, tổng quát sau** là hợp lệ.

## 4. Cơ chế bao phủ dựa trên kiểu, không dựa vào tên biến

Đặt cạnh nhau hai đoạn mã:

**Sai, lớp cha đứng trước lớp con:**

```java
try {
    load();
} catch (java.io.IOException ex) {
    // Bao phủ mọi FileNotFoundException.
} catch (java.io.FileNotFoundException missing) {
    // Không thể tới: FileNotFoundException là IOException.
}
```

Đây là **mảnh minh họa lỗi biên dịch**, giả định `load()` là một lời gọi có thể phát sinh checked `IOException`. Việc đổi tên biến `missing` hoặc `ex` không thay đổi quan hệ kế thừa giữa các kiểu.

**Đúng về thứ tự:**

```java
try {
    load();
} catch (java.io.FileNotFoundException missing) {
    // Xử lý riêng trường hợp file không tồn tại.
} catch (java.io.IOException ex) {
    // Xử lý những IOException khác.
}
```

Đây là **mảnh minh họa**, cần có `load()` được định nghĩa phù hợp. Handler kiểu cha được đặt sau có thể bắt những kiểu cùng nhánh không bị handler trước bao phủ.

Hình dung tập kiểu bắt được:

```text
catch (IOException)
    ├── IOException
    ├── FileNotFoundException
    └── các lớp con IOException khác

catch (FileNotFoundException)
    └── FileNotFoundException và lớp con của nó
```

Nếu tập kiểu của `catch` sau **nằm hoàn toàn trong** tập kiểu của `catch` trước, handler sau bị bao phủ. Nếu hai tập kiểu là hai nhánh không bao phủ nhau, ta không kết luận lỗi thứ tự chỉ vì handler đặt trước hay sau.

## 5. Ví dụ chạy được: ba lớp xử lý theo mức độ cụ thể

Tạo file **`CatchHierarchyDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchHierarchyDemo {
    private static void load(String mode) throws IOException {
        if ("missing".equals(mode)) {
            throw new FileNotFoundException("missing.txt");
        }
        if ("io".equals(mode)) {
            throw new IOException("connection interrupted");
        }
        if ("bad".equals(mode)) {
            throw new IllegalArgumentException("invalid mode");
        }
    }

    private static void run(String mode) {
        try {
            load(mode);
            System.out.println(mode + ": success");
        } catch (FileNotFoundException failure) {
            System.out.println(mode + ": file not found");
        } catch (IOException failure) {
            System.out.println(mode + ": IO failure");
        } catch (IllegalArgumentException failure) {
            System.out.println(mode + ": invalid argument");
        }
    }

    public static void main(String[] args) {
        run("missing");
        run("io");
        run("bad");
        run("ok");
    }
}
```

```bash
javac CatchHierarchyDemo.java
java CatchHierarchyDemo
```

Kết quả `stdout`:

```text
missing: file not found
io: IO failure
bad: invalid argument
ok: success
```

Giải thích:

- `load("missing")` tạo `FileNotFoundException`; handler đầu tiên nhận lỗi vì đây là kiểu cụ thể nhất.
- `load("io")` tạo `IOException` không phải `FileNotFoundException`; handler thứ hai nhận.
- `load("bad")` tạo `IllegalArgumentException`, thuộc nhánh `RuntimeException`; hai handler I/O không tương thích và handler thứ ba nhận.
- `load("ok")` hoàn tất bình thường và chạy dòng thông báo thành công.

Trong ví dụ, `IOException` và `IllegalArgumentException` không có quan hệ kế thừa kiểu cha–con, nên việc đặt hai handler ở các vị trí khác nhau không tự tạo vấn đề bao phủ. Vẫn nên đặt chúng theo thứ tự dễ đọc và dựa trên ý nghĩa xử lý của ứng dụng.

## 6. `catch (Exception)` và `catch (Throwable)` có thể che khuất nhánh nào?

Hai kiểu này rất rộng nhưng không hoàn toàn tương đương.

### 6.1. `catch (Exception)` trước mọi lớp con `Exception`

Ví dụ **không biên dịch**:

```java
try {
    int value = Integer.parseInt("abc");
    System.out.println(value);
} catch (Exception failure) {
    System.out.println("general");
} catch (NumberFormatException failure) {
    System.out.println("parse failed");
}
```

`NumberFormatException` kế thừa `IllegalArgumentException → RuntimeException → Exception`. Vì `Exception` đứng trước, handler `NumberFormatException` bị bao phủ. Đổi thứ tự nếu thực sự cần xử lý riêng lỗi parse.

### 6.2. `catch (Throwable)` còn rộng hơn `catch (Exception)`

`Throwable` là kiểu cha của cả `Exception` và `Error`. Vì vậy:

```java
try {
    operation();
} catch (Throwable failure) {
    // Bao phủ cả Exception lẫn Error.
} catch (Exception failure) {
    // Không thể tới: đã thuộc Throwable.
}
```

Đây là **mảnh minh họa lỗi biên dịch**, cần định nghĩa `operation()` trong chương trình thật. Cùng lý do, đặt `catch (Throwable)` trước `catch (Error)` cũng làm nhánh `Error` phía sau không thể được chọn.

Trong ứng dụng thông thường, `catch (Throwable)` không nên dùng chỉ để “bắt tất cả”, vì nó còn bao gồm nhiều `Error` nghiêm trọng mà ứng dụng không chắc có thể phục hồi.

### 6.3. `catch (Exception)` trước `catch (Error)` thì sao?

Hai nhánh `Exception` và `Error` **không nằm trong quan hệ cha–con**. Vì vậy, riêng xét vấn đề bao phủ kiểu, cách sắp xếp sau hợp lệ:

```java
try {
    operation();
} catch (Exception failure) {
    handleException(failure);
} catch (Error failure) {
    handleError(failure);
}
```

Đây là **mảnh minh họa**, không phải khuyến nghị luôn bắt `Error`. Các phương thức phải được định nghĩa. `catch (Exception)` không bắt đối tượng thuộc nhánh `Error`. Tuy nhiên, một số `Error` như `OutOfMemoryError` và `StackOverflowError` có thể khiến trạng thái hoặc tài nguyên JVM không còn đủ an toàn để tiếp tục, nên cần chính sách vận hành phù hợp.

## 7. `multi-catch` và trường hợp bị bao phủ

Từ Java 7, bạn có thể viết nhiều lựa chọn ngoại lệ trong **một `catch`** bằng dấu `|`:

```java
catch (IOException | SQLException failure) {
    // Xử lý chung hai nhánh ngoại lệ khác nhau.
}
```

`IOException` và `SQLException` là hai lớp checked exception khác nhánh; chúng không kế thừa nhau, vì vậy có thể cùng xuất hiện trong một multi-catch. Biến `failure` của multi-catch có tính chất hạn chế gán lại; bạn không thể gán đối tượng mới cho nó.

### 7.1. Multi-catch không cho phép các lựa chọn có quan hệ cha–con

Ví dụ **không biên dịch**:

```java
try {
    load();
} catch (java.io.FileNotFoundException
         | java.io.IOException failure) {
    System.out.println("IO failed");
}
```

`FileNotFoundException` đã thuộc `IOException` nên hai lựa chọn trong **cùng một multi-catch** có quan hệ kế thừa; Java từ chối cấu trúc này. Đây là quy tắc riêng của `multi-catch`, tương tự mục tiêu tránh những lựa chọn dư thừa do kiểu bao phủ.

Viết thành một handler rộng:

```java
try {
    load();
} catch (java.io.IOException failure) {
    System.out.println("IO failed");
}
```

Hoặc tách các handler cụ thể/rộng theo thứ tự đúng nếu cách xử lý khác nhau:

```java
try {
    load();
} catch (java.io.FileNotFoundException missing) {
    System.out.println("Missing file");
} catch (java.io.IOException failure) {
    System.out.println("Other IO issue");
}
```

Các đoạn trong mục này đều là **mảnh minh họa**, cần có `load()` có hợp đồng throws phù hợp và đặt trong phương thức/lớp hợp lệ.

### 7.2. Một `multi-catch` đứng trước có thể che khuất `catch` đứng sau

Ví dụ **không biên dịch**:

```java
try {
    process();
} catch (java.io.IOException | java.sql.SQLException failure) {
    handle(failure);
} catch (java.io.FileNotFoundException missing) {
    handle(missing);
}
```

Nhánh `FileNotFoundException` bị bao phủ bởi lựa chọn `IOException` trong multi-catch đứng trước. Mặc dù `SQLException` không liên quan đến `FileNotFoundException`, chỉ cần **một** lựa chọn ở trước đã bao phủ toàn bộ kiểu của handler sau là đủ để tạo lỗi.

Đoạn này minh họa quy tắc thứ tự; `process()` và `handle(...)` cần được khai báo tương thích.

### 7.3. Ví dụ multi-catch hợp lệ, chạy được

Tạo file **`MultiCatchDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchDemo {
    private static void execute(String mode)
            throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("read error");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("query error");
        }
    }

    private static void run(String mode) {
        try {
            execute(mode);
            System.out.println(mode + ": done");
        } catch (IOException | SQLException failure) {
            System.out.println(mode + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        run("io");
        run("sql");
        run("ok");
    }
}
```

```bash
javac MultiCatchDemo.java
java MultiCatchDemo
```

Kết quả `stdout`:

```text
io: IOException
sql: SQLException
ok: done
```

`throws IOException, SQLException` sử dụng **dấu phẩy** để khai báo nhiều kiểu trên phương thức; `catch (IOException | SQLException failure)` sử dụng **dấu `|`** để xử lý hai kiểu khác nhánh trong một handler. Hai cú pháp này có chức năng và quy tắc khác nhau.

## 8. Hai lỗi biên dịch dễ bị nhầm lẫn

Không phải mọi thông báo “unreachable” hoặc “never thrown” liên quan đến `catch` đều có cùng nguyên nhân.

### 8.1. Bị `catch` đứng trước bao phủ

```java
try {
    throw new java.io.IOException("x");
} catch (Exception failure) {
    // Bắt cả IOException.
} catch (java.io.IOException failure) {
    // Không thể tới: handler trước bao phủ.
}
```

Đoạn **không biên dịch** vì thứ tự các kiểu bắt. Dù trong `try` có ném `IOException`, handler cụ thể vẫn bị handler tổng quát chiếm hết.

### 8.2. Bắt checked exception mà khối `try` không thể ném

```java
try {
    int x = 1 + 2;
    System.out.println(x);
} catch (java.io.IOException failure) {
    System.out.println("IO error");
}
```

Đoạn **không biên dịch** vì trong `try` không có thao tác nào có thể ném checked `IOException` theo phân tích của trình biên dịch. Không có `catch` trước để che khuất; lỗi nằm ở **tính khả đạt và kiểm tra ngoại lệ từ khối `try`**.

Hai trường hợp cần sửa khác nhau:

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `IOException` sau `Exception` | Kiểu bị handler đứng trước bao phủ | Đưa `IOException` lên trên, hoặc bỏ handler dư |
| `catch (IOException)` trong `try` chỉ làm phép cộng và in | Không có đường ném checked `IOException` phù hợp | Bỏ handler không cần thiết, hoặc chuyển nó đến khối `try` thực sự gọi API I/O |
| `IOException` sau `FileNotFoundException` với `try` có thể ném `IOException` | Handler rộng vẫn có khả năng nhận loại I/O khác | Có thể hợp lệ, giữ thứ tự cụ thể trước |
| `catch (RuntimeException)` để nhận lỗi unchecked có thể xảy ra | Quy tắc kiểm tra khác checked exception | Không tự kết luận lỗi chỉ vì đường thử chưa từng ném |

Đặc biệt, một `catch` rộng đứng sau vài `catch` cụ thể có thể hoàn toàn hợp lệ, miễn là nó còn có thể nhận một loại ngoại lệ khác theo quy tắc của Java. Không nên chỉ dựa vào số lần handler đã chạy trong các bài kiểm thử để suy ra mã đúng hoặc sai khi biên dịch.

### 8.3. Có được bắt một kiểu con sau kiểu cha nếu cố tình viết `if`?

Không. Java kiểm tra quan hệ kiểu của chính các handler đứng cùng cấp. Bạn không thể sửa lỗi bằng cách thêm điều kiện trong `catch` đứng trước:

```java
try {
    load();
} catch (java.io.IOException failure) {
    if (!(failure instanceof java.io.FileNotFoundException)) {
        System.out.println("Other IO error");
    }
} catch (java.io.FileNotFoundException missing) {
    // Vẫn không thể tới.
}
```

Đây là **mảnh cố ý không biên dịch**. Dù handler trước chỉ thực hiện một nhánh `if` với một số ngoại lệ, handler ấy vẫn **bắt** mọi đối tượng `IOException`. Nếu muốn xử lý riêng `FileNotFoundException`, hãy đặt handler cụ thể lên trước; nếu muốn phân nhánh trong một handler rộng, làm ngay **bên trong cùng handler** và không tạo `catch` con ở phía sau.

## 9. Khác biệt giữa các `catch` cùng cấp và `try` lồng nhau

Quy tắc che khuất được xét đối với chuỗi `catch` của **cùng một `try`**. Một `try` nằm bên trong một `catch` hoặc một `try` khác tạo phạm vi xử lý riêng.

Ví dụ chạy được **`NestedCatchDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class NestedCatchDemo {
    private static void read() throws IOException {
        throw new FileNotFoundException("config.txt");
    }

    public static void main(String[] args) {
        try {
            try {
                read();
            } catch (FileNotFoundException missing) {
                System.out.println("inner: missing file");
                throw new IOException("cannot recover", missing);
            }
        } catch (IOException failure) {
            System.out.println("outer: " + failure.getMessage());
        }

        System.out.println("done");
    }
}
```

```bash
javac NestedCatchDemo.java
java NestedCatchDemo
```

Kết quả `stdout`:

```text
inner: missing file
outer: cannot recover
done
```

Lúc đầu, handler **bên trong** nhận `FileNotFoundException`. Handler đó ném **một đối tượng `IOException` mới** để báo rằng không thể phục hồi; `try` **bên ngoài** bắt đối tượng mới này. Hai handler không đứng cùng chuỗi `catch` nên không có lỗi “handler trước bao phủ handler sau”.

Cần nhớ: một ngoại lệ **được ném từ chính thân `catch`** không được các `catch` anh em của cùng `try` bắt lại. Nó đi ra phạm vi bao quanh tương ứng, và có thể được một `try` bên ngoài xử lý. Điều này khác với việc nhiều `catch` trong cùng danh sách chạy nối tiếp.

### `finally` không phải một handler thay thế

Nếu có `finally`, nó tham gia khi rời khối theo cơ chế bình thường hoặc do ngoại lệ. Nó không giúp một `catch` đã bị kiểu trước bao phủ trở nên hợp lệ:

```java
try {
    read();
} catch (java.io.IOException failure) {
    System.out.println("read failed");
} finally {
    System.out.println("cleanup");
}
```

Đây là **mảnh mã minh họa** với `read()` cần khai báo thích hợp. Thứ tự `catch` vẫn phải hợp lệ; `finally` không thay đổi quy tắc kiểm tra handler tại compile time. Nếu `finally` tự ném lỗi, nó có thể thay đổi ngoại lệ cuối cùng lan truyền, nhưng đó là một vấn đề luồng thực thi khác.

## 10. Khi các ngoại lệ là anh em, thứ tự có còn quan trọng?

Ví dụ `IOException` và `SQLException` đều kế thừa `Exception` nhưng không kế thừa nhau. Vì vậy, hai handler này không che khuất nhau về kiểu:

```java
try {
    process();
} catch (java.io.IOException io) {
    handleIo(io);
} catch (java.sql.SQLException sql) {
    handleSql(sql);
}
```

Với các phương thức `process()`, `handleIo()` và `handleSql()` được định nghĩa hợp lệ, đổi vị trí hai handler có thể vẫn biên dịch. Tuy nhiên, **điều kiện checked exception từ `try`** phải được thỏa như đã trình bày ở mục 8.

Tương tự, `NullPointerException` và `IllegalArgumentException` là hai nhánh khác nhau dưới `RuntimeException`. Một handler `RuntimeException` đặt phía trên sẽ bao phủ cả hai; nhưng hai handler chuyên biệt đặt cạnh nhau không che khuất nhau.

Đừng nhầm quan hệ cùng xuất phát từ một tổ tiên với quan hệ **kiểu này là con của kiểu kia**. Chỉ có quan hệ bao phủ thực sự mới khiến một handler sau không còn khả năng nhận đối tượng thuộc kiểu của nó.

## 11. Nguyên tắc thiết kế handler dễ bảo trì

### 11.1. Bắt kiểu đủ cụ thể ở vị trí có thể xử lý

Nếu `FileNotFoundException` yêu cầu báo người dùng chọn lại đường dẫn, nhưng `IOException` khác cần retry có giới hạn, bạn có cơ sở để tách handler. Nếu hai tình huống dùng đúng cùng cách xử lý, một handler `IOException` có thể là đủ; không cần thêm `FileNotFoundException` chỉ để làm mã dài hơn.

### 11.2. Handler tổng quát thường đặt cuối, nếu thật sự cần

`catch (Exception)` bao gồm cả các `RuntimeException` như `NullPointerException`. Handler quá rộng có thể che giấu lỗi lập trình nếu chỉ ghi log sơ sài rồi tiếp tục báo thành công. Chọn ranh giới phù hợp để xử lý và cân nhắc ném tiếp khi không phục hồi được.

`catch (Throwable)` còn bao gồm cả `Error`. Chỉ dùng trong những hạ tầng đặc biệt có chính sách rõ ràng; đừng lạm dụng để khắc phục lỗi thứ tự `catch`.

### 11.3. Giữ nguyên nguyên nhân khi bọc lỗi

Nếu muốn chuyển đổi `FileNotFoundException` thành một ngoại lệ tầng nghiệp vụ, giữ `cause` qua constructor phù hợp hoặc `initCause`. Việc bọc không làm handler `catch` đã bị bao phủ trở nên chạy được; đó là thay đổi **đường truyền và kiểu ngoại lệ** cần được thiết kế riêng.

### 11.4. Kiểm tra ngay bằng biên dịch

Đối với lỗi handler bị bao phủ, lệnh `javac` đủ để phát hiện. Không cần cố chạy để kiểm tra nhánh bất khả đạt. Hãy sửa thứ tự các kiểu dựa trên hệ phân cấp; sau khi biên dịch thành công mới kiểm tra kết quả theo từng trường hợp đầu vào.

Một quy trình ngắn:

1. Liệt kê các kiểu xuất hiện trong chuỗi `catch`.
2. Vẽ quan hệ `extends` giữa chúng hoặc tra JavaDoc.
3. Nếu một kiểu con đứng sau kiểu cha đã bao phủ nó, di chuyển handler con lên trước hoặc bỏ handler thừa.
4. Với checked exception, bảo đảm khối `try` thực sự có khả năng ném kiểu tương ứng.
5. Với multi-catch, kiểm tra các lựa chọn không có quan hệ cha–con.
6. Biên dịch, sau đó thử ít nhất một đường đi cho mỗi handler có ý nghĩa.

## 12. Những hiểu lầm phổ biến

**“`catch` phía sau sẽ chạy nếu `catch` trước không in gì.”** Sai. Một handler vẫn **bắt** đối tượng dù thân nó trống hoặc không ghi log. `catch` kế tiếp của cùng `try` không được thử lại.

**“`catch (Exception)` đứng trước `catch (IOException)` hợp lệ nếu tôi chỉ xử lý RuntimeException trong handler đầu.”** Sai. Kiểu bắt của handler đầu vẫn là `Exception`, bao gồm cả `IOException`, bất kể phần thân có `if` nào.

**“Chỉ checked exception mới bị lỗi khi đặt handler con sau cha.”** Sai. `RuntimeException` đứng trước `NullPointerException` cũng gây che khuất. Với `Throwable` đứng trước `Error` cũng vậy.

**“`catch (Exception)` bao phủ mọi `Error`.”** Sai. `Error` cùng kế thừa `Throwable` nhưng không kế thừa `Exception`.

**“Hai kiểu cùng có cha `Exception` thì luôn che nhau.”** Sai. Chẳng hạn `IOException` và `SQLException` không kế thừa nhau.

**“`catch (FileNotFoundException | IOException e)` là cách viết gọn.”** Sai. Các lựa chọn trong multi-catch không được có quan hệ cha–con; chỉ dùng `catch (IOException e)` hoặc tách handler theo thứ tự phù hợp.

**“`catch (IOException)` sau `catch (FileNotFoundException)` lúc nào cũng sai.”** Sai. Handler rộng có thể bắt các `IOException` còn lại nếu khối `try` có thể tạo chúng theo phân tích checked exception.

**“Nếu `catch` không bao giờ chạy trong unit test, trình biên dịch bắt buộc báo không thể tới.”** Sai. Không bao giờ xảy ra trong một bộ dữ liệu thử nghiệm khác với tính khả đạt theo quy tắc ngôn ngữ.

**“Chuyển `catch` đến một khối `try` lồng nhau vẫn bị lỗi vì trùng kiểu.”** Sai. Mỗi chuỗi `catch` gắn với câu lệnh `try` của nó; các handler ở phạm vi khác nhau có thể phục vụ các ngoại lệ khác nhau.

**“`finally` giúp sửa lỗi biên dịch vì nó luôn chạy.”** Sai. `finally` không đổi quy tắc thứ tự và kiểu của `catch`.

## 13. Bài tập tự kiểm tra

### Bài 1: Thứ tự hai kiểu có quan hệ kế thừa

```java
try {
    read();
} catch (java.io.IOException e) {
    System.out.println("io");
} catch (java.io.FileNotFoundException e) {
    System.out.println("missing");
}
```

**Câu hỏi:** Có biên dịch được không? **Đáp án:** Không. `FileNotFoundException` là lớp con của `IOException`, nên handler phía dưới bị bao phủ. Đưa `FileNotFoundException` lên trước. Đây là mảnh minh họa, cần khai báo `read()`.

### Bài 2: Hai lớp anh em

```java
try {
    process();
} catch (java.io.IOException e) {
    System.out.println("io");
} catch (java.sql.SQLException e) {
    System.out.println("sql");
}
```

**Câu hỏi:** Có lỗi bao phủ do thứ tự không? **Đáp án:** Không. Hai kiểu checked exception khác nhánh. Để đoạn mã biên dịch đầy đủ, `process()` phải có đường có thể ném checked exception tương ứng. Đây là đoạn minh họa, chưa phải chương trình độc lập.

### Bài 3: Runtime exception

```java
try {
    System.out.println(Integer.parseInt("x"));
} catch (RuntimeException e) {
    System.out.println("runtime");
} catch (NumberFormatException e) {
    System.out.println("format");
}
```

**Câu hỏi:** Có thể vào `catch (NumberFormatException)` không? **Đáp án:** Không. `NumberFormatException` là một `RuntimeException`. Đưa handler cụ thể lên trên hoặc chỉ giữ handler rộng khi hợp đồng xử lý giống nhau.

### Bài 4: Lỗi không được ném từ `try`

```java
try {
    System.out.println("hello");
} catch (java.io.IOException e) {
    System.out.println("io");
}
```

**Câu hỏi:** Đây có phải lỗi do `catch` trước bao phủ? **Đáp án:** Không. `try` không thể ném checked `IOException` từ các thao tác hiển thị, nên handler không phù hợp với kiểm tra ngoại lệ tại compile time.

### Bài 5: `Throwable` rồi `Error`

```java
try {
    throw new AssertionError("assertion");
} catch (Throwable e) {
    System.out.println("anything");
} catch (Error e) {
    System.out.println("error");
}
```

**Câu hỏi:** Điều gì xảy ra? **Đáp án:** Lỗi biên dịch vì `Throwable` đứng trước đã bao phủ `Error`. Không nên “sửa” bằng cách bắt `Throwable` rộng hơn nữa; cần xác định có thực sự cần xử lý `Error` hay không.

## 14. Tài liệu Java 17

- [Java Language Specification 17 — `14.20.1 Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): chọn handler tương thích theo thứ tự xuất hiện.
- [Java Language Specification 17 — `11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): quy tắc compile-time về checked exception và handler.
- [Java Language Specification 17 — `14.21 Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): tính khả đạt của câu lệnh.
- [Java Language Specification 17 — `14.20 The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cú pháp `catch`, multi-catch và `finally`.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): quan hệ kiểu cha–con.
- [Java SE 17 API — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html), [Exception](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): các kiểu handler rộng.

**Kết luận học tập:** Khi một `catch` của cùng `try` đã bao phủ toàn bộ kiểu ngoại lệ mà một `catch` phía sau định nhận, handler phía sau không thể tới được và Java báo lỗi biên dịch. Hãy đối chiếu quan hệ kế thừa, đặt handler cụ thể trước handler tổng quát, kiểm tra riêng các điều kiện của checked exception và multi-catch rồi mới chạy chương trình.
