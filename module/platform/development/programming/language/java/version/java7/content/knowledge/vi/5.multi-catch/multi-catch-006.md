# Thứ tự `catch` và phát hiện nhánh không thể chạy trong Java (Multi-catch)

## Mục tiêu

Một `try` có thể đi kèm nhiều nhánh `catch`, nhưng **Java không tự chọn nhánh có kiểu cụ thể nhất ở bất kỳ vị trí nào**. Khi phát sinh ngoại lệ, runtime đi theo **thứ tự khai báo từ trên xuống**, chọn nhánh `catch` **đầu tiên** có thể nhận kiểu thực tế của ngoại lệ. Compiler đồng thời kiểm tra các nhánh bị che khuất và khả năng bắt checked exception theo những gì khối `try` có thể ném.

Trong phạm vi Java 7, **multi-catch** là cú pháp gom nhiều loại ngoại lệ trong một nhánh, ví dụ `catch (IOException | SQLException ex)`. Cú pháp này vẫn phù hợp trong Java hiện đại. Khi dùng nó, phải xét cả **quan hệ kế thừa giữa các nhánh `catch`** và **quan hệ giữa các kiểu ở cùng một nhánh `|`**.

Sau bài này, bạn sẽ:

- Đọc đúng thứ tự chọn `catch` tại runtime và phân biệt nó với kiểm tra lỗi lúc biên dịch.
- Nhận diện nhánh bị che hoàn toàn bởi `catch` trước, như `catch (Exception)` đứng trước `catch (IOException)`.
- Phát hiện `catch` dành cho một **checked exception** mà khối `try` không có khả năng ném theo phân tích tĩnh.
- Viết multi-catch hợp lệ với những kiểu ngoại lệ không có quan hệ cha–con; hiểu `final` ngầm của tham số.
- Biết các trường hợp **không bao giờ chạy trong một kịch bản cụ thể nhưng vẫn biên dịch hợp lệ**, tránh khẳng định sai về reachability.
- Kiểm tra kết luận bằng `javac --release 17`, ví dụ Java chạy được, và quy tắc JLS hiện hành.

**Phạm vi phiên bản:** Multi-catch có từ **Java 7** và vẫn được hỗ trợ. Bài dùng JLS Java SE 26 để nói về quy tắc còn áp dụng, cùng ví dụ Java 17+ để kiểm chứng. Không cần chạy ứng dụng mới trên JDK 7 đã cũ để học tính năng này.

## 1. Quy tắc cơ bản: `catch` được xét từ trên xuống

Xét phần đơn giản sau, giả sử `work()` có thể ném `FileNotFoundException` hoặc `IOException`:

~~~java
try {
    work();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
~~~

**Đây là đoạn minh họa trong một phương thức**; `work`, `handleMissing` và `handleOtherIo` do ứng dụng định nghĩa.

Nếu `work()` ném `FileNotFoundException`, nhánh thứ nhất xử lý vì kiểu đó là `FileNotFoundException`. Nếu ném một `IOException` khác mà nhánh đầu không nhận, nhánh thứ hai xử lý. Một ngoại lệ không được bất kỳ nhánh nào bắt sẽ truyền ra ngoài để tìm handler bao quanh.

Có thể hình dung một phần cây kế thừa:

~~~text
Throwable
└── Exception
    ├── IOException
    │   └── FileNotFoundException
    ├── SQLException
    └── RuntimeException  (unchecked)
        └── IllegalArgumentException  (unchecked)
~~~

Đây chỉ là **một phần** của cây ngoại lệ Java; các lớp khác không được liệt kê.

- `FileNotFoundException` là lớp con của `IOException`. `catch (IOException)` bắt được cả `FileNotFoundException`.
- `IOException` và `SQLException` là hai nhánh khác nhau bên dưới `Exception`; cả hai là checked exception.
- `RuntimeException` và các lớp con như `IllegalArgumentException` là unchecked exception. Chúng **vẫn chịu quy tắc thứ tự nhánh**.
- `catch (Exception)` có thể bắt hầu hết ngoại lệ ứng dụng thường xử lý, gồm checked exception và `RuntimeException`, nhưng **không bắt các `Error`** nằm ở nhánh khác của `Throwable`.

**Không có cơ chế “tìm tất cả nhánh rồi chọn lớp con cụ thể nhất”.** Java chọn **nhánh phù hợp đầu tiên**. Chính vì vậy, thứ tự khai báo là một phần có ý nghĩa của code.

Nguồn ngữ nghĩa: [JLS §14.20.1 — Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20.1).

## 2. Lỗi thứ tự: nhánh sau bị nhánh trước bao phủ

### 2.1. Trường hợp compiler bắt lỗi ngay

Nếu đã đặt `catch (IOException)` trước, mọi `FileNotFoundException` đã bị nhánh này bắt. Nhánh `catch (FileNotFoundException)` phía sau không còn cơ hội nhận bất kỳ ngoại lệ nào của kiểu đó. Đây là **lỗi biên dịch**:

~~~java
try {
    readFile();
} catch (IOException ex) {
    System.out.println("IO");
} catch (FileNotFoundException ex) { // LỖI: đã bị IOException bắt
    System.out.println("not found");
}
~~~

Đây là **đoạn cố ý không biên dịch**; `readFile()` chỉ đại diện cho thao tác có thể ném ngoại lệ. Trình biên dịch không cần chạy chương trình để thấy `FileNotFoundException <: IOException`.

Cách sửa khi muốn xử lý “không tìm thấy file” riêng:

~~~java
try {
    readFile();
} catch (FileNotFoundException ex) {
    System.out.println("not found");
} catch (IOException ex) {
    System.out.println("other IO");
}
~~~

Nếu hai loại ngoại lệ cần **chính xác cùng một hành vi**, không nhất thiết phải tách làm hai nhánh. Có thể chỉ dùng `catch (IOException ex)`; hoặc khi gộp với loại độc lập khác, dùng multi-catch hợp lệ.

**Nguyên tắc:** Với nhiều `catch` có quan hệ kế thừa, đặt **kiểu cụ thể trước, kiểu tổng quát sau**. Điều này áp dụng cả cho checked và unchecked exceptions.

### 2.2. Hai mẫu sai phổ biến khác

~~~java
try {
    perform();
} catch (Exception ex) {
    // Xử lý tổng quát trước
} catch (SQLException ex) {    // LỖI: Exception đã bắt SQLException
    // Không thể chọn nhánh này
}
~~~

~~~java
try {
    perform();
} catch (RuntimeException ex) {
    // Đã bắt các RuntimeException
} catch (IllegalArgumentException ex) { // LỖI: là con RuntimeException
    // Không thể chọn nhánh này
}
~~~

Hai block trên chỉ minh họa **sai thứ tự** và không phải chương trình độc lập; `perform()` là tên đại diện. Đừng nghĩ unchecked exception được miễn trừ quy tắc nhánh trước bao phủ nhánh sau.

### 2.3. Chương trình không biên dịch để tái hiện thông báo

Tạo file `WrongCatchOrder.java`:

~~~java
import java.io.*;

public class WrongCatchOrder {
    public static void main(String[] args) {
        try {
            throw new FileNotFoundException();
        } catch (Exception e) {
            System.out.println("general");
        } catch (FileNotFoundException e) {
            System.out.println("specific");
        }
    }
}
~~~

Biên dịch thử:

~~~bash
javac --release 17 WrongCatchOrder.java
~~~

**Kết quả kỳ vọng:** `javac` trả mã lỗi (không tạo một chương trình chạy được), vì `FileNotFoundException` đã được nhánh `Exception` phía trên bắt. Nội dung tiếng Anh, số dòng và định dạng thông báo lỗi phụ thuộc compiler, không có stdout của chương trình để đối chiếu.

Để sửa, đảo thứ tự hai nhánh nếu thật sự cần hai cách xử lý; hoặc xóa nhánh cụ thể nếu chỉ có một chính sách chung. Chuyển đổi không thay đổi mục đích nghiệp vụ mới là cách sửa đúng.

## 3. Phân tích checked exception: có loại ngoại lệ nào để bắt không?

“Nhánh không thể chạy” không chỉ xuất hiện do **kế thừa**. Với **checked exception**, compiler còn phân tích những ngoại lệ mà `try` **có thể ném theo kiểu tĩnh**.

Ví dụ: `IOException` là checked exception; một khối chỉ in chuỗi không có thao tác được xác định có thể ném `IOException`. Bắt `IOException` ở đây là lỗi biên dịch:

~~~java
try {
    System.out.println("normal");
} catch (IOException ex) { // LỖI: try không thể ném IOException
    System.out.println("io");
}
~~~

Đây là **đoạn cố ý sai**, giả sử đã import `java.io.IOException`. Compiler không coi một nhánh `catch` cho checked exception là “để phòng xa” nếu phân tích tĩnh không cho phép ngoại lệ đó phát sinh.

Ví dụ độc lập `CheckedNotThrown.java`:

~~~java
import java.io.*;

public class CheckedNotThrown {
    public static void main(String[] args) {
        try {
            System.out.println("normal");
        } catch (IOException e) {
            System.out.println("io");
        }
    }
}
~~~

~~~bash
javac --release 17 CheckedNotThrown.java
~~~

**Kết quả kỳ vọng:** compile error, thường được diễn đạt là `IOException` không được ném từ phần `try` tương ứng. Không có stdout của chương trình do không biên dịch thành công.

### 3.1. “Có thể ném” là khái niệm theo mã và chữ ký, không phải dự đoán mỗi lần chạy

Compiler xét các lệnh `throw`, lời gọi phương thức/constructor, các `throws` được khai báo và trường hợp đóng resource trong `try-with-resources`. Nó không chạy mọi nhánh logic để đoán chính xác dữ liệu thực tế.

Giả sử có một phương thức:

~~~java
static void load() throws IOException {
    // Nội dung hiện tại không ném IOException
}
~~~

Đây là **phương thức minh họa**. Một chỗ gọi `load()` có thể viết `catch (IOException)` vì **hợp đồng chữ ký** khai báo khả năng ném checked exception, dù lần chạy hiện tại không phát sinh lỗi. Khi refactor và thay chữ ký `throws`, cần xem lại các `catch` ở caller vì phân tích tĩnh có thể thay đổi.

Một trường hợp dễ bỏ sót: bản thân phần thân `try-with-resources` không ném gì, nhưng `close()` của resource có thể ném checked exception. Compiler phải xét ngoại lệ từ việc **đóng tài nguyên tự động**.

### 3.2. Unchecked exception và các ngoại lệ tổng quát

Không được suy ra “không nhìn thấy lệnh throw” thì mọi `catch` đều sai.

- `catch (RuntimeException)` hoặc `catch (IllegalArgumentException)` có thể hợp lệ ngay cả khi compiler không xác định cụ thể chỗ ném unchecked exception.
- `catch (Exception)` (hoặc lớp cha của `Exception`) được JLS cho phép trong phân tích checked exception ngay cả khi không có một checked exception cụ thể; đây là ngoại lệ trong quy tắc kiểm tra tĩnh.
- Tuy nhiên, **nhánh sau vẫn bị từ chối** nếu nhánh trước đã bắt kiểu đó hoặc một lớp cha của nó. Quy tắc thứ tự không bị bỏ qua.

Không nên thêm `catch (Exception)` hay `catch (Throwable)` chỉ để tránh lỗi biên dịch. Chọn loại ngoại lệ đúng với khả năng phục hồi và hợp đồng tầng ứng dụng.

Nguồn: [JLS §11.2.1–§11.2.3 — Exception Analysis and Checking](https://docs.oracle.com/javase/specs/jls/se26/html/jls-11.html#jls-11.2.3).

## 4. Multi-catch: hai cấp kiểm tra thứ tự và kiểu

Từ Java 7, cú pháp:

~~~java
try {
    work();
} catch (IOException | SQLException ex) {
    report(ex);
}
~~~

có nghĩa là **cùng một handler** nhận ngoại lệ thuộc một trong hai nhánh kiểu. Đây là **đoạn minh họa**; `work()` phải có khả năng ném các loại checked exception liên quan, và `report()` được ứng dụng định nghĩa. Lợi ích là tránh lặp code khi xử lý giống nhau.

### 4.1. Các alternatives trong cùng multi-catch không được có quan hệ cha–con

**Hợp lệ:** `IOException | SQLException` vì hai lớp này không là lớp con của nhau.

**Không hợp lệ:** `FileNotFoundException | IOException`, bởi `FileNotFoundException` là con của `IOException`. Viết đảo lại `IOException | FileNotFoundException` cũng vẫn sai; đổi thứ tự quanh dấu `|` không giải quyết vấn đề.

Một lỗi tương tự: `IllegalArgumentException | RuntimeException` (quan hệ con–cha).

Ví dụ độc lập cố ý không biên dịch, file `BadMultiCatch.java`:

~~~java
import java.io.*;

public class BadMultiCatch {
    public static void main(String[] args) {
        try {
            throw new FileNotFoundException();
        } catch (FileNotFoundException | IOException e) {
            System.out.println("IO");
        }
    }
}
~~~

~~~bash
javac --release 17 BadMultiCatch.java
~~~

**Kết quả kỳ vọng:** compile error vì các alternatives của multi-catch có quan hệ kế thừa. Cách đơn giản nhất nếu muốn xử lý chung là `catch (IOException ex)`. Nếu cần xử lý khác nhau cho trường hợp không tìm thấy file, viết hai `catch` riêng và đặt `FileNotFoundException` trước `IOException`.

### 4.2. Multi-catch vẫn bị ảnh hưởng bởi những `catch` đứng trước

Ví dụ dưới đây **hợp lệ** nếu khối `try` có thể ném các exception tương ứng:

~~~java
try {
    work();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException | SQLException ex) {
    handleOther(ex);
}
~~~

`IOException` là kiểu cha của `FileNotFoundException`, nhưng **hai kiểu không nằm cùng một union**: `FileNotFoundException` được ưu tiên ở nhánh trước; nhánh sau vẫn xử lý được những `IOException` khác và `SQLException`.

Ngược lại, đoạn này **sai**:

~~~java
try {
    work();
} catch (IOException ex) {
    handleIo(ex);
} catch (FileNotFoundException | SQLException ex) {
    handleOther(ex); // LỖI: alternative FileNotFoundException đã bị bắt
}
~~~

Bản thân union `FileNotFoundException | SQLException` có hai kiểu không là con của nhau, **nhưng** một alternative của nó bị nhánh `catch (IOException)` trước đó che hoàn toàn. Java vẫn báo lỗi; việc có `SQLException` còn nhận được không “cứu” alternative đã bị che.

**Quy trình khi review multi-catch:** xét quan hệ giữa các alternatives **bên trong dấu `|`**, rồi xét **từng alternative** so với tất cả nhánh `catch` trước đó.

### 4.3. Tham số multi-catch là `final` ngầm

Trong `catch (IOException | SQLException ex)`, biến `ex` **không được gán lại**. Nó có kiểu tổng hợp gần nhất dùng được cho các alternatives, nên chỉ gọi được các phương thức phù hợp với kiểu được suy ra, như `getMessage()` hay `getClass()`. Không thể gọi ngay phương thức chỉ có ở `SQLException` cho mọi giá trị `ex`.

~~~java
catch (IOException | SQLException ex) {
    System.out.println(ex.getMessage());
    // ex = new IOException("replace"); // LỖI: multi-catch parameter final
}
~~~

Đây là **đoạn bên trong cấu trúc try-catch**, không phải chương trình độc lập. Nếu cần chính sách khác nhau theo từng loại ngoại lệ, sử dụng `catch` tách biệt thường rõ hơn. Không dùng ép kiểu không kiểm tra để qua compiler.

JLS hiện hành: [§14.20 — The try statement](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20). Tài liệu hướng dẫn nguồn gốc: [Oracle — Catching Multiple Exception Types](https://docs.oracle.com/javase/8/docs/technotes/guides/language/catch-multiple.html).

## 5. Chương trình Java 17+: thứ tự hợp lý và multi-catch cùng tồn tại

Tạo file `CatchOrderDemo.java`:

~~~java
import java.io.*;
import java.sql.SQLException;

public class CatchOrderDemo {
    static void action(String mode) throws IOException, SQLException {
        switch (mode) {
            case "missing" -> throw new FileNotFoundException("missing.txt");
            case "io" -> throw new IOException("disk");
            case "sql" -> throw new SQLException("database");
            case "bad" -> throw new IllegalArgumentException("input");
            default -> System.out.println("ok");
        }
    }

    static void handle(String mode) {
        try {
            action(mode);
        } catch (FileNotFoundException ex) {
            System.out.println("missing-file");
        } catch (IOException | SQLException ex) {
            System.out.println("io-or-sql:" + ex.getClass().getSimpleName());
        } catch (IllegalArgumentException ex) {
            System.out.println("bad-input");
        }
    }

    public static void main(String[] args) {
        handle("missing");
        handle("io");
        handle("sql");
        handle("bad");
        handle("other");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CatchOrderDemo.java
java CatchOrderDemo
~~~

Stdout chính xác:

~~~text
missing-file
io-or-sql:IOException
io-or-sql:SQLException
bad-input
ok
~~~

**Phân tích:**

1. `FileNotFoundException` là một `IOException` nhưng nhánh cụ thể đứng trước, nên `missing-file` được in.
2. `IOException` thông thường không khớp nhánh đầu; đến `catch (IOException | SQLException)` và in tên lớp `IOException`.
3. `SQLException` thuộc alternative còn lại của cùng multi-catch và in `SQLException`.
4. `IllegalArgumentException` là unchecked exception, đi tới nhánh riêng `catch (IllegalArgumentException)`; sự hiện diện của các checked catches phía trước không làm nó bị bắt.
5. Với `"other"`, không có ngoại lệ; mọi `catch` đều được bỏ qua, và phần `try` in `ok`.

Cú pháp `switch ->` được chuẩn hóa trong Java 14; đây là **chương trình Java 17+** để minh họa thứ tự `catch`. **Multi-catch bắt đầu từ Java 7**, còn việc sử dụng cú pháp `switch` hiện đại không phải điều kiện để multi-catch hoạt động.

## 6. Phân biệt nhánh bị compiler bác bỏ và nhánh ít khi thực thi

Từ “không thể chạy” dễ dẫn đến hai khẳng định khác nhau:

| Tình huống | Có compile không? | Lý do |
| --- | --- | --- |
| `catch (IOException)` rồi `catch (FileNotFoundException)` | **Không** | Nhánh sau bị kiểu cha trước bao phủ |
| `catch (Exception)` rồi `catch (SQLException)` | **Không** | Mọi `SQLException` đã vào nhánh `Exception` |
| `catch (FileNotFoundException | IOException)` | **Không** | Hai alternatives trong union có quan hệ con–cha |
| `try` không thể ném checked `IOException` nhưng vẫn `catch (IOException)` | **Không** | Kiểm tra ngoại lệ checked không thỏa |
| `try` đơn giản nhưng có `catch (RuntimeException)` | **Có** | Unchecked exception không chịu kiểm tra “phải được ném” giống checked |
| `try` không ném checked cụ thể nhưng có `catch (Exception)` | **Có**, nếu không bị nhánh trước che | JLS có ngoại lệ riêng cho `Exception` hoặc lớp cha |
| `try` ném đúng `FileNotFoundException`, `catch (FileNotFoundException)` rồi `catch (IOException)` | **Có thể hợp lệ**, compiler có thể cảnh báo | Kiểm tra tĩnh của JLS không loại bỏ mọi nhánh nhìn như không thể chạy trong một kịch bản |

### 6.1. Một trường hợp tinh tế: compiler có thể chấp nhận nhánh không nhận được lỗi ở ví dụ cụ thể

Xét:

~~~java
try {
    throw new FileNotFoundException();
} catch (FileNotFoundException ex) {
    System.out.println("specific");
} catch (IOException ex) {
    System.out.println("other IO");
}
~~~

Đây là đoạn minh họa trong nơi đã import các lớp exception. Ở chính ví dụ này, lệnh `throw` có kiểu tĩnh cụ thể là `FileNotFoundException`, nên nó sẽ được nhánh đầu bắt; nhánh `IOException` sau **không nhận được ngoại lệ từ lệnh `throw` ấy**. Tuy nhiên, mẫu này được JLS nêu là **hợp lệ**, và compiler được khuyến khích cảnh báo trong tình huống đã bắt hết các loại con mà `try` được phân tích là có thể ném.

Điều này **không mâu thuẫn** với quy tắc thứ tự: `catch (IOException)` đứng **sau** một loại con `FileNotFoundException` chưa hề bị một nhánh kiểu cha trước nó che hoàn toàn. Chỉ vì code `try` hiện tại có đúng một đường phát sinh ngoại lệ mà không đồng nghĩa mọi trình biên dịch phải từ chối nhánh tổng quát.

**Không đồng nhất ba khái niệm:**

- **Lỗi vì bị che:** nhánh trước bắt cùng kiểu hoặc một lớp cha của kiểu nhánh sau → compile error.
- **Lỗi vì checked exception không có khả năng phát sinh:** kiểm tra ngoại lệ tĩnh theo JLS → compile error.
- **Ít khi/không bao giờ thực thi với trạng thái hiện tại:** nhận định về đường chạy cụ thể; compiler có thể vẫn chấp nhận. Dùng test và kiểm tra logic, đừng trông chờ compiler bắt mọi nhánh thiếu ý nghĩa.

Nguồn trực tiếp: [JLS §11.2.3, Example 11.2.3-1](https://docs.oracle.com/javase/specs/jls/se26/html/jls-11.html#jls-11.2.3).

### 6.2. Khi API khai báo kiểu tổng quát, compiler không đoán chính xác lớp con

Một phương thức được khai báo `throws IOException` có thể ném `FileNotFoundException` hoặc một kiểu `IOException` khác tại runtime. Dù implementation hiện tại chỉ ném một kiểu cụ thể, caller vẫn phải viết logic phù hợp **hợp đồng `throws`**.

~~~java
static void read() throws IOException {
    throw new FileNotFoundException("file.txt");
}
~~~

Trong ví dụ minh họa này, bên gọi có thể dùng:

~~~java
try {
    read();
} catch (FileNotFoundException ex) {
    System.out.println("missing");
} catch (IOException ex) {
    System.out.println("other IO");
}
~~~

Compiler không nhìn vào từng lần chạy để khẳng định `read()` luôn ném cùng một lớp con. Nếu code thư viện thay đổi cách thực hiện mà vẫn giữ hợp đồng `throws IOException`, thứ tự xử lý ở caller còn hợp lệ.

## 7. `try-with-resources`: ngoại lệ có thể đến từ `close()`

Một nhánh `catch` bắt checked exception **không nhất thiết yêu cầu câu lệnh trong thân `try` tự ném ngoại lệ**. Khi dùng `try-with-resources`, phần khởi tạo tài nguyên và lời gọi `close()` tự động cũng tham gia exception analysis.

Tạo file `CloseCatchDemo.java`:

~~~java
import java.io.IOException;

public class CloseCatchDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close");
        }
    }

    public static void main(String[] args) {
        try (Resource r = new Resource()) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("caught:" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 CloseCatchDemo.java
java CloseCatchDemo
~~~

Stdout chính xác:

~~~text
body
caught:close
~~~

Thân `try` chỉ in `body`, nhưng khi rời phạm vi resource, `close()` tự động ném `IOException`. Do đó `catch (IOException)` **hợp lệ và có thể chạy**. Đây là lý do khi đánh giá một nhánh catch, phải xem **khởi tạo và đóng tài nguyên** chứ không chỉ nhìn các dòng trong thân `try`.

Ví dụ cố ý tạo lỗi trong `close()` để minh họa cơ chế. Trong ứng dụng thật, resource cần đóng đúng hợp đồng và có thể dùng lỗi được ghi log/lan truyền theo chính sách; không chủ động tạo exception trong `close()`.

## 8. Ngoại lệ bị ném từ một `catch` không đi sang `catch` kế tiếp cùng `try`

Các nhánh `catch` cùng cấp **chỉ xử lý ngoại lệ từ phần `try` tương ứng**. Khi một `catch` đang chạy và ném một ngoại lệ **mới**, Java không bắt đầu duyệt tiếp các `catch` còn lại cùng `try`. Ngoại lệ sẽ truyền lên một handler bao quanh.

Tạo file `CatchFromCatchDemo.java`:

~~~java
import java.io.IOException;

public class CatchFromCatchDemo {
    static void run() {
        try {
            throw new IOException("first");
        } catch (IOException ex) {
            throw new IllegalStateException("from-handler");
        } catch (IllegalStateException ex) {
            System.out.println("inner");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IllegalStateException ex) {
            System.out.println("outer:" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 CatchFromCatchDemo.java
java CatchFromCatchDemo
~~~

Stdout chính xác:

~~~text
outer:from-handler
~~~

Phần `catch (IllegalStateException)` **bên trong `run()`** không chạy; nhánh `catch` **bên ngoài** ở `main()` nhận lỗi mới. Dù nhánh trong có thể không được kích hoạt bởi chính code hiện tại, nó **vẫn biên dịch** vì đó là unchecked exception không bị nhánh trước che theo quan hệ kiểu. Ví dụ phân biệt rõ “biên dịch hợp lệ” và “có thể đi tới nhánh này theo luồng thực tế”.

Nếu cần biến đổi lỗi tầng thấp thành lỗi tầng cao, nên bọc nguyên nhân để không làm mất thông tin, ví dụ `new IllegalStateException("Cannot load", ex)`. Tầng caller hoặc global handler có trách nhiệm quyết định báo lỗi hay phục hồi.

## 9. Cách rà soát nhanh một chuỗi `catch`

Khi IDE báo `exception ... has already been caught`, `alternatives ... cannot be related by subclassing`, hoặc `exception ... is never thrown`, làm theo thứ tự này:

1. **Ghi lại cây kế thừa** của từng exception (dựa trên JDK API), phân biệt checked và unchecked.
2. **Đọc từ trên xuống:** ở nhánh sau, có kiểu nào đã bị `catch` phía trước hoặc alternative trước đó che bằng cùng kiểu/lớp cha không? Nếu có, đặt nhánh cụ thể trước hoặc bỏ nhánh trùng.
3. **Kiểm tra từng multi-catch:** mọi alternatives trong cùng `|` phải không có quan hệ tổ tiên–hậu duệ; mỗi alternative còn phải hợp lệ so với các nhánh trước.
4. **Phân tích checked exceptions từ `try`:** gồm `throw`, chữ ký `throws` của lệnh gọi/constructor, tài nguyên và `close()`, theo quy tắc tĩnh JLS. Nếu API không thể ném checked exception đang bắt, bỏ nhánh đó hoặc sửa ranh giới xử lý đúng tầng.
5. **Phân biệt hành vi muốn khác nhau hay giống nhau:** khác nhau → `catch` riêng theo độ cụ thể; giống nhau → cân nhắc multi-catch với các alternatives độc lập hoặc bắt một kiểu cha đủ hẹp.
6. **Xem trường hợp không có ngoại lệ:** khi `try` hoàn thành bình thường, các nhánh `catch` đều bị bỏ qua.
7. **Xem lỗi ném trong handler:** nhánh `catch` kế tiếp cùng `try` không tiếp nhận; phải có handler bao ngoài hoặc khai báo/lan truyền phù hợp.
8. **Biên dịch ở mức Java mục tiêu** bằng `javac --release 17 ...` hoặc release mà dự án thực sự hỗ trợ. Với lỗi compile, xem chẩn đoán của compiler; với code hợp lệ, chạy test cho từng kiểu exception có chủ đích.

### Chọn độ rộng của handler theo khả năng phục hồi

- `catch (FileNotFoundException)` khi có cách phục hồi cụ thể, chẳng hạn báo thiếu file cấu hình với thông điệp rõ ràng.
- `catch (IOException | SQLException)` khi **chính sách xử lý thực sự giống nhau** và caller có đủ thông tin để xử lý ở cùng một tầng.
- `catch (Exception)` ở ranh giới có trách nhiệm điều phối lỗi (ví dụ lớp giao diện/handler tổng quát) nếu đó là chủ ý của thiết kế. Tránh bắt rộng một cách cơ học khiến lỗi lập trình bị biến thành thành công giả hoặc bị nuốt.
- Không dùng `catch (Throwable)` để gom mọi lỗi ứng dụng thường ngày; nó còn bao gồm `Error` và có thể che khuất các lỗi nghiêm trọng mà ứng dụng không thể phục hồi.

**Lưu ý:** Đừng đưa mọi loại checked exception vào `|` chỉ vì chúng cùng extends `Exception`. Ngoài quan hệ kiểu, compiler còn cần khối `try` có khả năng ném các loại checked exception đó theo quy tắc phân tích tĩnh.

## 10. Câu hỏi tự kiểm tra

**1.** Hai nhánh `catch (IOException)` rồi `catch (FileNotFoundException)` có hợp lệ?  
**Đáp án:** Không. Nhánh `IOException` đứng trước bắt cả kiểu con `FileNotFoundException`, nên nhánh sau bị che.

**2.** Đảo thành `catch (FileNotFoundException)` rồi `catch (IOException)` có luôn sai nếu `try` hiện chỉ có lệnh `throw new FileNotFoundException()`?  
**Đáp án:** Không. JLS cho phép trường hợp này, compiler có thể cảnh báo. Nhánh `IOException` sau không nhận ngoại lệ từ đúng lệnh `throw` đó, nhưng không bị một nhánh kiểu cha trước nó che.

**3.** `catch (IOException | FileNotFoundException ex)` có hợp lệ nếu đặt đúng vị trí?  
**Đáp án:** Không. Hai alternatives cùng union có quan hệ con–cha; đổi thứ tự trong `|` không sửa được.

**4.** `catch (IOException | SQLException ex)` có hợp lệ nếu khối `try` có thể ném cả hai?  
**Đáp án:** Có. Chúng là hai checked exception không có quan hệ kế thừa với nhau; cùng handler xử lý.

**5.** Không có lời gọi nào ghi `throws IOException` bên trong thân `try-with-resources` thì `catch (IOException)` chắc chắn sai?  
**Đáp án:** Không. `close()` và khởi tạo resource có thể ném checked exception; phải xét cả chúng.

**6.** Nếu `catch (IOException ex)` ném `IllegalStateException`, `catch (IllegalStateException)` kế sau trong cùng một `try` có bắt lỗi mới đó không?  
**Đáp án:** Không. Lỗi mới truyền ra handler bao ngoài; các nhánh cùng cấp không bắt ngoại lệ phát sinh từ nhau.

**7.** Vì sao `catch (RuntimeException)` có thể biên dịch dù khối `try` không có dòng `throw new RuntimeException()`?  
**Đáp án:** Vì đây là unchecked exception; kiểm tra “checked exception có thể ném từ try” không áp dụng giống nhau. Tuy nhiên quy tắc nhánh trước che nhánh sau vẫn áp dụng.

## Tài liệu chính thức

- [Java Language Specification, Java SE 26 — §14.20 The try statement](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20): định nghĩa uni-catch, multi-catch, giới hạn subtype và tham số final.
- [JLS Java SE 26 — §14.20.1 Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20.1): chọn handler đầu tiên tương thích kiểu lúc runtime.
- [JLS Java SE 26 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se26/html/jls-11.html#jls-11.2.3): kiểm tra compile-time với checked exception, các nhánh bị che và trường hợp compiler có thể cảnh báo.
- [JLS Java SE 26 — §11.2.2 Exception Analysis of Statements](https://docs.oracle.com/javase/specs/jls/se26/html/jls-11.html#jls-11.2.2): tính những exception có thể phát sinh, gồm khởi tạo và đóng resource.
- [Oracle Dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): hướng dẫn multi-catch, giới hạn alternatives, tham số implicitly final.
- [Oracle — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/catch-multiple.html): giải thích lịch sử tính năng từ Java SE 7. Dùng để xác minh mốc xuất hiện; dùng JLS hiện hành cho quy tắc áp dụng hôm nay.

**Ghi nhớ:** `catch` được chọn **theo thứ tự từ trên xuống**. Một nhánh không hợp lệ có thể do **đã bị nhánh trước che**, do **union có kiểu cha–con**, hoặc do **checked exception không phù hợp phân tích tĩnh của `try`**. Đừng nhầm compile-time error với một nhánh hợp lệ nhưng không xuất hiện trong lần chạy hiện tại.