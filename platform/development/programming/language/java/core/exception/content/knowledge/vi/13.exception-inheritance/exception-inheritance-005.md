# Một phương thức thực thi nhiều interface có `throws` khác nhau trong Java

> **Chủ đề:** Java Core → Exception → Kế thừa và hợp đồng. Một lớp Java có thể `implements` nhiều interface chứa **cùng một phương thức trừu tượng** (cùng tên và danh sách tham số) nhưng khai báo **checked exception khác nhau** trong mệnh đề `throws`. Khi đó, **một phương thức implementation phải tuân thủ hợp đồng của tất cả phương thức mà nó override**. Nó không được tùy tiện gộp các ngoại lệ thành `throws A, B` nếu một interface không cho phép loại checked tương ứng.

## 1. Vấn đề cốt lõi: một implementation, nhiều hợp đồng

Xem hai interface:

```java
interface FileAction {
    void execute() throws java.io.IOException;
}

interface DatabaseAction {
    void execute() throws java.sql.SQLException;
}
```

Cả hai khai báo cùng một phương thức `void execute()`, nhưng khác `throws`:

- `FileAction.execute()` cho phép checked `IOException`.
- `DatabaseAction.execute()` cho phép checked `SQLException`.
- Một lớp thực thi **cả hai** phải có `execute()` hợp lệ khi được gọi qua **bất kỳ interface nào**.

Đây là implementation hợp lệ:

```java
final class CombinedAction implements FileAction, DatabaseAction {
    @Override
    public void execute() {
        System.out.println("Hoàn tất");
    }
}
```

Vì implementation **không khai báo checked exception nào**, nó không làm người dùng của interface nào phải xử lý thêm loại checked exception nằm ngoài hợp đồng của interface đó.

Đây lại là implementation **không hợp lệ**:

```java
// CỐ Ý SAI, KHÔNG BIÊN DỊCH:
final class BadAction implements FileAction, DatabaseAction {
    @Override
    public void execute()
            throws java.io.IOException, java.sql.SQLException {
        // ...
    }
}
```

**Lý do:** người dùng `FileAction` chỉ được hứa khả năng checked `IOException`, không bị yêu cầu xử lý checked `SQLException`. Tương tự, người dùng `DatabaseAction` không được bất ngờ nhận `IOException` trong hợp đồng checked. Implementation phải thỏa **đồng thời**, không được lấy **hợp** hai danh sách `throws`.

### 1.1. Quy tắc ghi nhớ

**Với mỗi checked exception được khai báo bởi phương thức implementation, loại đó phải được cho phép bởi từng khai báo phương thức bị override.** “Được cho phép” nghĩa là nó thuộc kiểu checked được khai báo, hoặc là **subtype** của một kiểu checked mà interface tương ứng khai báo.

Với hai interface độc lập nêu trên, `IOException` và `SQLException` nằm ở hai nhánh lớp khác nhau. Không có lớp checked exception thông thường nào đồng thời là subtype của cả hai (Java chỉ cho một superclass trực tiếp), nên implementation **không được khai báo checked exception nào thuộc hai nhánh đó**.

**Ngoại lệ quan trọng:** quy tắc giới hạn này nói về **checked exception**. Method implementation vẫn có thể ném `RuntimeException`/`Error` và các subtype dù interface không khai báo; điều này đúng cú pháp nhưng không bảo đảm cách xử lý đó hợp lý về nghiệp vụ.

## 2. Phân biệt `throws` với `throw` để tránh hiểu sai

`throws` xuất hiện trong khai báo:

```java
void load() throws java.io.IOException;
```

Nó công bố những **kiểu checked exception có thể thoát khỏi method** và ảnh hưởng nghĩa vụ compile-time của caller.

`throw` là câu lệnh thực thi:

```java
throw new java.io.IOException("Đọc lỗi");
```

Nếu implementation bị hạn chế không được khai báo `throws IOException`, nó cũng **không thể để checked IOException thoát ra** từ thân method đó. Nó phải thực sự xử lý checked exception, hoặc đổi cấu trúc API. Bỏ từ khóa `throws` khỏi chữ ký **không tự xử lý** một lời gọi I/O ném IOException trong thân.

Cần giữ riêng ba câu hỏi:

1. Interface công bố những loại checked nào?
2. Implementation muốn để những loại checked nào thoát?
3. Caller có kiểu tham chiếu tĩnh là interface nào khi biên dịch?

Ba câu hỏi liên quan nhưng không đồng nhất. `throws` của một interface không quyết định ngoại lệ nào **chắc chắn** sẽ xuất hiện ở một lần chạy.

## 3. Bảng các trường hợp cơ bản

Giả sử cả hai interface có cùng `void run()`:

| Interface A | Interface B | `throws` hợp lệ ở implementation | Ghi chú |
| --- | --- | --- | --- |
| `throws IOException` | `throws SQLException` | Không có checked exception nào thuộc hai nhánh riêng | Hai loại không liên quan |
| `throws IOException` | `throws FileNotFoundException` | `throws FileNotFoundException` hoặc subtype của nó | `FileNotFoundException extends IOException` |
| `throws Exception` | `throws IOException` | `throws IOException` hoặc checked subtype phù hợp | `Exception` ở A bao phủ `IOException` |
| `throws IOException` | Không khai báo checked exception | Không khai báo checked exception | Interface B nghiêm ngặt hơn |
| `throws FileNotFoundException` | `throws EOFException` | Không có checked exception thuộc cả hai nhánh | Hai subtype khác nhau của `IOException` |
| `throws Exception` | `throws Exception` | `throws Exception` hoặc subtype checked phù hợp | Hai hợp đồng tương thích |
| Không khai báo checked exception | Không khai báo checked exception | Không khai báo checked exception | Unchecked exceptions vẫn có thể xảy ra |

Ở bảng này, “không khai báo checked exception” **không** có nghĩa method không bao giờ thất bại; nó chỉ nói về ràng buộc `throws` đối với checked exceptions.

### 3.1. Cách xét một loại exception cụ thể

Giả sử implementation muốn khai báo `throws FileNotFoundException`:

- Đối với interface A `throws IOException`: **hợp lệ**, vì `FileNotFoundException extends IOException`.
- Đối với interface B `throws FileNotFoundException`: **hợp lệ**, vì loại trùng khớp.
- Vì cả hai đều cho phép, implementation có thể khai báo `throws FileNotFoundException`.

Nếu implementation muốn khai báo `throws IOException` thì thất bại trước B: `IOException` **rộng hơn** `FileNotFoundException`, nghĩa là nó có thể bao gồm những lỗi B chưa hứa cho caller.

### 3.2. Vì sao không phải “lấy giao nguyên văn hai danh sách”?

Một cách nhớ ngắn là tập checked exception hợp lệ của implementation phải nằm trong **phần chung của các hợp đồng**, nhưng đừng hiểu đó là phép giao chuỗi tên:

```text
A: throws IOException
B: throws FileNotFoundException
```

Hai danh sách tên **không giống nhau**, nhưng implementation vẫn được khai báo `throws FileNotFoundException` bởi **quan hệ kế thừa**. Phải xét **tập các subtype được từng hợp đồng bao phủ**, chứ không so sánh hai văn bản `throws`.

## 4. Cơ chế override với nhiều interface

Trong Java, hai method instance có cùng tên và cùng signature tham số được một class thực thi bằng **một** implementation phù hợp nếu thỏa các quy tắc về kiểu trả về, khả năng truy cập và exception.

Ví dụ:

```java
interface First {
    String query() throws java.io.IOException;
}

interface Second {
    String query() throws java.sql.SQLException;
}

final class QueryService implements First, Second {
    @Override
    public String query() {
        return "OK";
    }
}
```

Đây là các khai báo kiểu hợp lệ, nhưng chưa có `main`. Một `QueryService.query()` thỏa cả hai:

- `public` là cần thiết vì các method của interface ở đây là `public`.
- `String` là kiểu trả về tương thích với cả hai khai báo.
- Không có checked `throws`, nên không vi phạm hợp đồng nào.
- `@Override` giúp compiler xác nhận đây là implementation của method được override.

**Đừng tạo hai phương thức phân biệt chỉ bằng `throws`:**

```java
// CỐ Ý SAI: không thể overload chỉ bằng throws.
public void query() throws java.io.IOException { }
public void query() throws java.sql.SQLException { }
```

`throws` không nằm trong **method signature dùng để phân biệt overload**. Hai khai báo trên có cùng tên/danh sách tham số, gây lỗi khai báo trùng phương thức. Muốn hai hành vi độc lập có checked exceptions khác nhau, cân nhắc **đổi tên hoặc tham số có ý nghĩa**, hoặc thiết kế hai adapter/interface khác nhau.

### 4.1. Cùng tên nhưng khác tham số thì không phải tình huống này

```java
interface ById {
    void load(int id) throws java.io.IOException;
}

interface ByName {
    void load(String name) throws java.sql.SQLException;
}
```

Đây là hai signature khác nhau: `load(int)` và `load(String)`. Một lớp có thể triển khai **hai method overload độc lập** với hai `throws` khác nhau, miễn mỗi method đáp ứng đúng hợp đồng của nó. Không cần ép cả hai danh sách `throws` vào cùng một implementation.

### 4.2. `@Override` không “gộp” các ngoại lệ

Annotation `@Override` chỉ yêu cầu compiler kiểm tra đúng việc override/implementation. Nó **không** cho phép bỏ qua quy tắc checked exception. Dù bỏ annotation, declaration không tương thích `throws` vẫn bị từ chối.

## 5. Ví dụ Java 17 hoàn chỉnh: hai interface có checked exception không liên quan

Chương trình này chứng minh một implementation không khai báo checked exception vẫn được gọi qua **hai interface công bố những kiểu checked khác nhau**.

Lưu thành **`DisjointThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class DisjointThrowsDemo {
    interface FileAction {
        String execute() throws IOException;
    }

    interface DatabaseAction {
        String execute() throws SQLException;
    }

    static final class CombinedAction
            implements FileAction, DatabaseAction {
        @Override
        public String execute() {
            return "OK";
        }
    }

    static void fromFile(FileAction action) {
        try {
            System.out.println("File: " + action.execute());
        } catch (IOException e) {
            System.out.println("File lỗi: " + e.getMessage());
        }
    }

    static void fromDatabase(DatabaseAction action) {
        try {
            System.out.println("DB: " + action.execute());
        } catch (SQLException e) {
            System.out.println("DB lỗi: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        CombinedAction implementation = new CombinedAction();

        System.out.println("Impl: " + implementation.execute());
        fromFile(implementation);
        fromDatabase(implementation);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 DisjointThrowsDemo.java
java DisjointThrowsDemo
```

Stdout:

```text
Impl: OK
File: OK
DB: OK
```

**Điều đáng chú ý:**

1. `CombinedAction.execute()` không khai báo `throws`, nhưng vẫn thực thi hai interface.
2. `implementation.execute()` ở `main` có kiểu receiver `CombinedAction`, nên **không cần** bắt checked `IOException` hoặc `SQLException` cho riêng lời gọi đó.
3. `fromFile(FileAction action)` gọi qua kiểu tĩnh `FileAction`; compiler thấy `throws IOException` nên cần bắt hoặc khai báo.
4. `fromDatabase(DatabaseAction action)` gọi qua kiểu tĩnh `DatabaseAction`; compiler thấy `throws SQLException`.
5. Cùng **một object runtime** có thể được gọi qua các kiểu receiver khác nhau, nên **nghĩa vụ checked lúc biên dịch khác nhau** trong khi kết quả thực thi ở ví dụ đều là `"OK"`.

Điểm này rất quan trọng: `throws` ở **khai báo nhìn thấy tại call site** là một phần hợp đồng API; implementation hẹp hơn không khiến caller dùng interface tự biết và bỏ nghĩa vụ checked.

## 6. Khi hai interface có ngoại lệ kiểu cha–con

Đây là trường hợp hai hợp đồng **tương thích một phần**.

```java
interface GeneralReader {
    void open() throws java.io.IOException;
}

interface FileReaderContract {
    void open() throws java.io.FileNotFoundException;
}
```

`FileNotFoundException` là subtype của `IOException`. Implementation có thể:

- Không khai báo checked exception nào; hoặc
- Khai báo `throws FileNotFoundException` (hoặc checked subtype phù hợp nếu có).

Nó **không** được khai báo `throws IOException`, bởi `FileReaderContract.open()` không cho phép loại rộng như vậy.

### 6.1. Ví dụ Java 17 hoàn chỉnh

Tạo **`CompatibleThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CompatibleThrowsDemo {
    interface GeneralReader {
        void open() throws IOException;
    }

    interface NarrowReader {
        void open() throws FileNotFoundException;
    }

    static final class MissingReader
            implements GeneralReader, NarrowReader {
        @Override
        public void open() throws FileNotFoundException {
            throw new FileNotFoundException("Không thấy tệp");
        }
    }

    public static void main(String[] args) {
        MissingReader implementation = new MissingReader();

        try {
            implementation.open();
        } catch (FileNotFoundException e) {
            System.out.println("Concrete: " + e.getMessage());
        }

        GeneralReader broadReference = implementation;
        try {
            broadReference.open();
        } catch (IOException e) {
            System.out.println("General: "
                    + e.getClass().getSimpleName());
        }

        NarrowReader narrowReference = implementation;
        try {
            narrowReference.open();
        } catch (FileNotFoundException e) {
            System.out.println("Narrow: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CompatibleThrowsDemo.java
java CompatibleThrowsDemo
```

Stdout:

```text
Concrete: Không thấy tệp
General: FileNotFoundException
Narrow: Không thấy tệp
```

Phân tích:

- Implementation `MissingReader.open()` khai báo `throws FileNotFoundException`, hợp lệ với cả hai interface.
- Khi gọi qua `GeneralReader`, caller phải xử lý checked `IOException` theo chữ ký interface, dù đối tượng runtime tạo `FileNotFoundException`.
- Khi gọi qua `NarrowReader`, caller biết hợp đồng checked hẹp hơn.
- `getClass().getSimpleName()` phản ánh **kiểu runtime của exception**, không bị biến thành `IOException` khi lời gọi được thực hiện qua `GeneralReader`.

**Lỗi thường gặp:** nghĩ “`IOException` chứa `FileNotFoundException` nên muốn ghi `throws IOException` trong implementation cũng được”. Chiều subtype ở đây ngược lại: interface hẹp chỉ cho phép **FileNotFoundException**, nên implementation không được mở rộng lên IOException.

## 7. Trường hợp một interface không khai báo checked exception

```java
interface Alpha {
    void run() throws java.io.IOException;
}

interface Beta {
    void run();
}
```

Với một implementation của cả hai, `Beta.run()` là hợp đồng **không cho checked exception thoát ra**. Vì vậy:

```java
final class Both implements Alpha, Beta {
    @Override
    public void run() {
        System.out.println("Run");
    }
}
```

là hợp lệ, còn:

```java
// CỐ Ý SAI:
final class InvalidBoth implements Alpha, Beta {
    @Override
    public void run() throws java.io.IOException {
    }
}
```

không hợp lệ do xung đột với `Beta.run()`.

Từ góc nhìn caller:

- `Alpha alpha = new Both();` → lời gọi `alpha.run()` chịu hợp đồng checked `IOException`.
- `Beta beta = new Both();` → lời gọi `beta.run()` không cần bắt checked IOException do khai báo của `Beta`.
- `Both both = new Both();` → lời gọi `both.run()` cũng không cần bắt checked IOException do khai báo thực thi.

**Đây không phải compiler suy đoán runtime instance ở mọi nơi.** Nó tuân theo phương thức được xác định bằng **kiểu tĩnh của biểu thức receiver** tại vị trí gọi.

## 8. Unchecked exception vẫn có thể xảy ra

Giới hạn của checked `throws` **không** ngăn implementation ném:

- `IllegalStateException`;
- `IllegalArgumentException`;
- `NullPointerException`;
- các `RuntimeException` subtype khác;
- `Error` subtype (dù không nên dùng `Error` cho lỗi nghiệp vụ).

Ví dụ hoàn chỉnh giúp thấy hai interface không liên quan vẫn được một implementation thỏa mãn dù method ném unchecked error trong đường chạy cụ thể.

Lưu **`UncheckedAcrossInterfacesDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class UncheckedAcrossInterfacesDemo {
    interface FileStep {
        void process() throws IOException;
    }

    interface SqlStep {
        void process() throws SQLException;
    }

    static final class SharedStep implements FileStep, SqlStep {
        @Override
        public void process() {
            throw new IllegalStateException("Trạng thái không hợp lệ");
        }
    }

    public static void main(String[] args) {
        SharedStep implementation = new SharedStep();

        FileStep asFile = implementation;
        try {
            asFile.process();
        } catch (IOException e) {
            System.out.println("Checked I/O");
        } catch (IllegalStateException e) {
            System.out.println("File ref: "
                    + e.getClass().getSimpleName());
        }

        SqlStep asSql = implementation;
        try {
            asSql.process();
        } catch (SQLException e) {
            System.out.println("Checked SQL");
        } catch (IllegalStateException e) {
            System.out.println("SQL ref: "
                    + e.getClass().getSimpleName());
        }

        try {
            implementation.process();
        } catch (IllegalStateException e) {
            System.out.println("Concrete: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 UncheckedAcrossInterfacesDemo.java
java UncheckedAcrossInterfacesDemo
```

Stdout:

```text
File ref: IllegalStateException
SQL ref: IllegalStateException
Concrete: IllegalStateException
```

**Hai bài học riêng:**

1. `SharedStep.process()` không khai báo checked exceptions nên hợp lệ với cả hai interface; unchecked `IllegalStateException` không bị quy tắc override checked `throws` cấm.
2. Đây **không** phải khuyến nghị đổi mọi I/O/SQL failure thành `IllegalStateException`. Nếu chuyển loại exception, cần có chính sách hợp đồng, giữ `cause` và không làm caller hiểu nhầm thao tác thành công.

### 8.1. Vì sao `catch (IOException)` ở lời gọi qua `FileStep` hợp lệ?

Biến `asFile` có kiểu tĩnh `FileStep`, nơi phương thức công bố `throws IOException`. Compiler chấp nhận handler checked đó ngay cả khi implementation `SharedStep.process()` không ném IOException.

Nếu đổi thành:

```java
SharedStep concrete = new SharedStep();
try {
    concrete.process();
} catch (java.io.IOException e) {
    // CỐ Ý SAI nếu trong try không còn nguồn IOException khác.
}
```

thì `catch(IOException)` bị từ chối vì compile-time nhìn thấy chữ ký implementation **không khai báo checked IOException**. Đây là tác động của **kiểu receiver**, không phải của giá trị runtime.

## 9. Nếu thân implementation thực sự cần gọi API ném checked exception?

Đây mới là bài toán kỹ thuật quan trọng trong dự án. Xét `CombinedAction.execute()` phải dùng một hàm đọc cấu hình khai báo `throws IOException`. Vì hai interface chỉ cho những tập checked không tương thích, nó **không thể đơn giản thêm `throws IOException` vào implementation**.

Bạn có vài hướng lựa chọn:

1. **Xử lý tại implementation** khi có cách phục hồi thật: thử nguồn khác, ghi kết quả thất bại có nghĩa hoặc bỏ thao tác theo hợp đồng.
2. **Chuyển sang unchecked exception phù hợp** và giữ `cause`, nhưng chỉ khi hợp đồng API chấp nhận cách báo lỗi đó; caller vẫn cần biết có thể thất bại.
3. **Tái thiết kế interface** để tránh ép một method có hai nghĩa/hợp đồng xung đột vào một chữ ký duy nhất.
4. **Tách adapter**: mỗi interface có một implementation riêng, cả hai dùng chung một service nội bộ, nhưng mỗi adapter tự quyết định cách xử lý checked exception.
5. **Dùng result type** khi thất bại là một kết quả dự kiến thay vì điều kiện phải unwind bằng exception.

Không có một cách sửa tự động đúng cho mọi hệ thống. **Che lỗi hoặc trả thành công giả** không phải lựa chọn hợp lệ chỉ vì compiler cấm `throws` rộng hơn.

### 9.1. Ví dụ Java 17: chuyển checked I/O thành unchecked có cause

`java.io.UncheckedIOException` là wrapper unchecked chuyên dành cho `IOException`. Trong ví dụ, adapter buộc giữ chữ ký không có checked exception nhưng vẫn có thể truyền nguyên nhân ra caller.

Tạo **`HandledCheckedInsideDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.sql.SQLException;

public class HandledCheckedInsideDemo {
    interface FileTask {
        void perform() throws IOException;
    }

    interface DatabaseTask {
        void perform() throws SQLException;
    }

    static final class CombinedTask
            implements FileTask, DatabaseTask {
        @Override
        public void perform() {
            try {
                readConfiguration();
            } catch (IOException original) {
                throw new UncheckedIOException(
                        "Không nạp được cấu hình", original);
            }
        }
    }

    static void readConfiguration() throws IOException {
        throw new IOException("Nguồn cấu hình lỗi");
    }

    public static void main(String[] args) {
        CombinedTask task = new CombinedTask();

        try {
            task.perform();
        } catch (UncheckedIOException e) {
            System.out.println("Exception: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 HandledCheckedInsideDemo.java
java HandledCheckedInsideDemo
```

Stdout:

```text
Exception: UncheckedIOException
Cause: IOException
Message: Không nạp được cấu hình
```

Giải thích:

- `readConfiguration()` thực sự ném checked `IOException`.
- `CombinedTask.perform()` **bắt** loại đó, rồi ném wrapper unchecked `UncheckedIOException`.
- `perform()` không khai báo `throws IOException` hoặc `throws SQLException`, nên hợp lệ với hai interface.
- `getCause()` vẫn giữ đối tượng `IOException` gốc.
- Việc đổi checked thành unchecked **không phục hồi** lỗi cấu hình và cũng không làm side effect đã xảy ra biến mất; nó chỉ thay đổi hợp đồng báo lỗi ở biên này.

**Cảnh báo:** nếu hai interface đại diện hai ý nghĩa thực sự khác nhau (đọc file và ghi database), dùng một implementation cho cùng tên method có thể là thiết kế gây hiểu nhầm. Đừng biến mọi checked exception thành unchecked chỉ để “qua compiler”; khi có thể, thiết kế hai operation khác nhau rõ hơn.

### 9.2. Tại sao `throw new RuntimeException(e.getMessage())` không tốt?

Nó làm mất đối tượng gốc và stack trace liên kết `cause`. Nếu wrapper hợp lý, dùng constructor giữ nguyên nhân (ví dụ `new UncheckedIOException(message, e)` hoặc custom exception có `super(message, e)`). Ngoài ra không nên log rồi nuốt lỗi chỉ để giữ method không có `throws`.

## 10. Caller nhìn thấy `throws` qua kiểu tham chiếu tĩnh

Đây là một phần quan trọng nhất của bài, nên xét rõ từng kiểu receiver.

Cho:

```java
interface A {
    void run() throws java.io.IOException;
}
interface B {
    void run() throws java.sql.SQLException;
}
final class C implements A, B {
    @Override
    public void run() {
        System.out.println("OK");
    }
}
```

Đây là khai báo lớp/interface minh họa, không có `main`. Ở call site:

```java
C c = new C();
c.run(); // Không yêu cầu xử lý checked exception.

A a = c;
// a.run(); // Phải bắt/khai báo IOException.

B b = c;
// b.run(); // Phải bắt/khai báo SQLException.
```

Dù cả ba biến đều trỏ tới cùng một `C`, compiler xác định phương thức được gọi qua **kiểu tĩnh** của receiver:

- `C.run()` không khai báo checked exception.
- `A.run()` khai báo `IOException`.
- `B.run()` khai báo `SQLException`.

**Đừng nhầm** “implementation không ném checked exception” với “caller gọi qua interface không cần xử lý checked exception”. Caller được biên dịch theo **API nó nhìn thấy**, giúp code tương thích khi sau này thay implementation bằng loại khác vẫn hợp lệ với cùng interface.

### 10.1. `catch` sai nguồn checked exception

Đoạn sau cố ý **không biên dịch**:

```java
A a = new C();
try {
    a.run();
} catch (java.sql.SQLException e) {
    System.out.println("SQL lỗi");
}
```

Với giả định `try` chỉ có lời gọi `a.run()`, checked `SQLException` không có nguồn khai báo tương thích. `A.run()` công bố `IOException`, nên phải xử lý hoặc khai báo `IOException`.

Thêm một multi-catch `catch (IOException | SQLException e)` cũng không khắc phục sự thiếu nguồn cho checked `SQLException` ở `try` này. Multi-catch không tự mở rộng hợp đồng nguồn lỗi.

### 10.2. `throws` là hợp đồng cho compiler, không phải danh sách toàn bộ lỗi runtime

`A.run() throws IOException` **không** cam kết phương thức không bao giờ ném `RuntimeException`. Một `NullPointerException` hoặc `IllegalStateException` có thể xảy ra theo đường runtime mà không được kê trong `throws`. Người sử dụng API vẫn cần chính sách phù hợp cho lỗi không dự kiến ở tầng ranh giới của hệ thống.

## 11. Thực thi phương thức đã kế thừa từ superclass

Một lớp có thể `extends` superclass đồng thời `implements` nhiều interface. Khi đó, method public được kế thừa từ superclass đôi khi đủ để thực hiện interface — **nhưng vẫn phải thỏa tất cả hợp đồng checked `throws`**.

Xem:

```java
class BaseService {
    public void sync() throws java.io.IOException {
        System.out.println("Base");
    }
}

interface NetworkContract {
    void sync() throws java.io.IOException;
}

interface SqlContract {
    void sync() throws java.sql.SQLException;
}
```

`BaseService.sync() throws IOException` không thể dùng nguyên trạng để đáp ứng `SqlContract.sync() throws SQLException` vì hai loại checked không tương thích. Lớp con có thể **override và thu hẹp** hợp đồng:

```java
final class UnifiedService
        extends BaseService
        implements NetworkContract, SqlContract {
    @Override
    public void sync() {
        System.out.println("Unified");
    }
}
```

### 11.1. Java 17 — ví dụ superclass, hai interface, một override

Tạo **`InheritedThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class InheritedThrowsDemo {
    static class BaseService {
        public void sync() throws IOException {
            System.out.println("Base");
        }
    }

    interface NetworkContract {
        void sync() throws IOException;
    }

    interface SqlContract {
        void sync() throws SQLException;
    }

    static final class UnifiedService extends BaseService
            implements NetworkContract, SqlContract {
        @Override
        public void sync() {
            System.out.println("Unified");
        }
    }

    public static void main(String[] args) {
        UnifiedService concrete = new UnifiedService();
        concrete.sync();

        BaseService asBase = concrete;
        try {
            asBase.sync();
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }

        SqlContract asSql = concrete;
        try {
            asSql.sync();
        } catch (SQLException e) {
            System.out.println("SQL: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InheritedThrowsDemo.java
java InheritedThrowsDemo
```

Stdout:

```text
Unified
Unified
Unified
```

Giải thích:

1. `UnifiedService.sync()` override method từ `BaseService`, thực thi cả hai interface và bỏ checked `throws`.
2. Khi gọi qua `UnifiedService`, compiler không yêu cầu xử lý checked.
3. Khi gọi qua `BaseService`, compiler yêu cầu xét `IOException` vì đó là chữ ký cấp cha.
4. Khi gọi qua `SqlContract`, compiler yêu cầu xét `SQLException`.
5. Dispatch runtime vẫn gọi **`UnifiedService.sync()`** trong cả ba trường hợp, nên đều in `Unified`.

Nếu bỏ override trong `UnifiedService`, method kế thừa từ `BaseService` có `throws IOException` không đáp ứng hợp đồng của `SqlContract`; class sẽ không biên dịch thành một implementation hợp lệ.

## 12. Checked exception là ràng buộc override, không phải biến thể overload

Nhìn một tập quy tắc đối chiếu:

| Tình huống | Quy tắc |
| --- | --- |
| Cùng tên, cùng tham số, khác `throws` | Không tạo overload; phải đáp ứng override/implementation |
| Cùng tên, khác tham số | Có thể là overload; mỗi method xét hợp đồng của signature riêng |
| Một implementation của hai interface cùng signature | Thỏa đồng thời các mệnh đề checked `throws` |
| Implementation khai báo **ít** checked exception hơn interface | Hợp lệ |
| Implementation khai báo subtype checked của loại interface cho phép | Hợp lệ |
| Implementation khai báo checked rộng hơn bất kỳ interface liên quan | Không hợp lệ |
| Implementation ném unchecked `RuntimeException` | Không bị hạn chế bởi khai báo checked `throws` của interface |
| Caller gọi qua một interface | Nghĩa vụ checked dựa trên method được xác định ở compile-time qua interface đó |
| Caller gọi qua class implementation | Nghĩa vụ checked dựa trên chữ ký method tương ứng của class |
| Interface có generic method/return type khác biệt | Ngoài checked `throws` còn phải thỏa quy tắc signature, type parameter, return-type substitutability |

Đừng suy luận rằng hai method có `throws` khác nhau thì compiler sẽ tạo hai implementation tách biệt. Java dispatch dựa trên method signature và receiver, không chọn method theo loại checked exception được kê trong `throws`.

## 13. Những ví dụ cố ý sai và cách đọc thông báo compiler

### 13.1. Sai vì thêm hai checked exception không tương thích

```java
interface Readable {
    void process() throws java.io.IOException;
}
interface Writable {
    void process() throws java.sql.SQLException;
}
class Invalid implements Readable, Writable {
    @Override
    public void process()
            throws java.io.IOException, java.sql.SQLException {
    }
}
```

**Không biên dịch:** implementation khai báo những checked exception mà **một interface tương ứng không cho phép**.

Giải pháp tùy ngữ cảnh: bỏ các checked `throws` và xử lý lỗi trong method; dùng unchecked wrapper có cause khi phù hợp; hoặc đổi thiết kế API để phân biệt hai hợp đồng.

### 13.2. Sai vì implementation khai báo kiểu rộng hơn hợp đồng hẹp

```java
interface Narrow {
    void open() throws java.io.FileNotFoundException;
}
interface Broad {
    void open() throws java.io.IOException;
}
class TooBroad implements Narrow, Broad {
    @Override
    public void open() throws java.io.IOException {
    }
}
```

**Không biên dịch:** `Narrow.open()` chỉ cho checked `FileNotFoundException`, không cho mọi `IOException`.

Đổi thành `throws FileNotFoundException` hoặc không khai báo checked exception nào.

### 13.3. Sai vì chỉ bỏ `throws` mà không xử lý lời gọi

```java
interface A {
    void load() throws java.io.IOException;
}
interface B {
    void load() throws java.sql.SQLException;
}
class ForgotHandling implements A, B {
    @Override
    public void load() {
        java.nio.file.Files.readString(
                java.nio.file.Path.of("config.txt"));
    }
}
```

**Không biên dịch:** `Files.readString(...)` công bố checked `IOException`, nhưng `load()` không bắt/khai báo phù hợp. Thêm `throws IOException` vào `load()` lại xung đột với `B`. Phải xử lý checked exception trong thân hoặc thiết kế lại hợp đồng.

### 13.4. Sai vì quyền truy cập không đủ

```java
interface PublicTask {
    void execute();
}
class Hidden implements PublicTask {
    void execute() {
    }
}
```

**Không biên dịch:** method implementation phải là `public`, không được hạ mức truy cập từ method `public` của interface. Dù bài tập chính là `throws`, đừng quên đây là **một ràng buộc override độc lập**.

### 13.5. Không lạm dụng `throws Exception`

Một lớp có thể khai báo `throws Exception` khi cả hai interface đều cho phép `Exception`. Nhưng đó là hợp đồng rộng, ép caller xử lý nhiều loại checked không cụ thể. Nếu API có thể diễn đạt chính xác bằng `IOException` hoặc kiểu tùy chỉnh hẹp, nên cân nhắc mô tả cụ thể để caller hiểu mình có thể phục hồi ra sao.

Đặt `throws Exception` ở implementation **không sửa được** tình huống interface A chỉ cho `IOException` còn interface B chỉ cho `SQLException`; nó càng làm hợp đồng rộng hơn và không hợp lệ.

## 14. Có thể gộp hai interface thành một interface con không?

Một interface có thể `extends` nhiều interface:

```java
interface FileStep {
    void process() throws java.io.IOException;
}

interface SqlStep {
    void process() throws java.sql.SQLException;
}

interface CombinedStep extends FileStep, SqlStep {
}
```

Đây là **khai báo hợp lệ** khi hai method được kế thừa có cùng signature và kiểu trả về tương thích. Việc kế thừa không tự tạo một method “`throws IOException, SQLException`” như một hợp đồng rộng hơn để implementation dùng tùy ý.

Một class thực thi `CombinedStep` vẫn phải thỏa **cả hai** hợp đồng checked exception. Thông thường nó dùng `public void process()` không khai báo checked, như trường hợp `implements FileStep, SqlStep` trực tiếp.

### 14.1. Redeclare trong interface con để làm rõ hợp đồng

Có thể khai báo lại method với checked `throws` phù hợp:

```java
interface CombinedStep extends FileStep, SqlStep {
    @Override
    void process();
}
```

Đây là ví dụ interface minh họa. Khai báo lại không checked `throws` giúp người đọc biết hợp đồng của `CombinedStep.process()`. Nó **không** sửa chữ ký `FileStep.process()` hoặc `SqlStep.process()`; lời gọi qua từng interface gốc vẫn chịu checked exception mà interface gốc công bố.

Nếu đặt `throws IOException, SQLException` lên `CombinedStep.process()` để nới rộng, nó vi phạm quy tắc override đối với các interface cha.

### 14.2. Nếu chỉ muốn một chính sách thống nhất

Thay vì ép hai nghĩa khác nhau vào cùng `void process()`, cân nhắc:

```java
interface FileService {
    void readFile() throws java.io.IOException;
}

interface DatabaseService {
    void queryDatabase() throws java.sql.SQLException;
}
```

Một class có thể thực thi **cả hai**, với **hai method có tên khác nhau** và hai hợp đồng phù hợp. Đó thường là thiết kế rõ ràng hơn nếu một operation là đọc file và operation kia là truy vấn database.

## 15. Hệ quả đối với kiểm thử và thiết kế thư viện

### 15.1. Kiểm thử lời gọi theo từng kiểu tĩnh

Một test ở mức interface nên gọi qua interface thực sự được dùng trong production, không chỉ qua class implementation. Điều này giúp kiểm tra khả năng thay thế implementation và hợp đồng caller mong đợi.

Với `DisjointThrowsDemo`, thử viết hai hàm `fromFile(FileAction)` và `fromDatabase(DatabaseAction)` như ví dụ; mỗi hàm xử lý checked exception theo interface mình biết. Nếu sau này thay implementation, code caller vẫn đúng với hợp đồng đó.

### 15.2. Kiểm thử checked `throws` không giống kiểm thử exception runtime

Một method `FileAction.execute() throws IOException` có thể không ném lỗi khi chạy. Điều đó **không** nghĩa chữ ký vô dụng hoặc test đã chứng minh không bao giờ có IOException. Nó chỉ là hợp đồng cho nhiều implementation khác nhau.

Dùng test để xác minh hành vi runtime (thành công, lỗi có điều kiện, state sau lỗi), còn compiler xác minh các ràng buộc checked ở mỗi vị trí gọi. Các ví dụ “cố ý không biên dịch” ở trên được dùng để học quy tắc ngôn ngữ, không nên đặt chung vào source của những chương trình runnable.

### 15.3. Không tự suy luận một ngoại lệ “không thể xảy ra” vì implementation hiện tại

Nếu một biến được khai báo kiểu `FileAction`, compiler phải cho phép khả năng implementation hợp lệ khác của `FileAction` có thể ném `IOException`. Việc object cụ thể hiện tại là `CombinedAction` không khiến code dùng kiểu `FileAction` được miễn nghĩa vụ checked tại compile-time.

### 15.4. API thư viện nên tránh hợp đồng mâu thuẫn

Nếu hai interface do bạn kiểm soát cùng mô tả một operation nhưng `throws` không tương thích, hãy hỏi liệu chúng thực sự có nên dùng **cùng một method signature** hay không. Đôi khi đặt tên khác, đưa lỗi thành result type chung, hoặc tách một interface chức năng rõ ràng là giải pháp tốt hơn việc chuyển mọi checked exception thành unchecked.

## 16. Lưu ý về default method, generics và các quy tắc khác

Bài này chủ yếu xét **hai khai báo abstract instance method** có cùng signature và kiểu trả về tương thích. Java còn có các quy tắc độc lập:

- Nếu nhiều interface cung cấp **default method xung đột**, class thường phải override để giải quyết. Đó là bài toán **thừa kế implementation** chứ không chỉ `throws`.
- Khi kết hợp method trong interface có **kiểu trả về không tương thích**, một implementation có thể không tồn tại dù `throws` đã hợp lệ.
- Khi method generic hoặc erasure khiến nhiều khai báo đụng signature, compiler còn kiểm tra type parameters, method subsignature và name clash.
- Static/private method của interface không tạo hợp đồng abstract instance method như những ví dụ trong bài; không nên nhập chúng vào phép so sánh `throws` của cùng một override.
- Nếu class kế thừa method từ superclass và cũng implements interface, method kế thừa phải hợp đồng; nếu không, class cần override như `InheritedThrowsDemo`.

**Đừng lạm dụng quy tắc về `throws` để giải thích mọi lỗi compiler khi implements nhiều interface.** Đọc thông báo cụ thể và kiểm tra từng ràng buộc: tên/tham số, kiểu trả về, phạm vi truy cập, checked exception, default methods, generic erasure.

## 17. Một quy trình giải bài theo từng bước

Khi gặp yêu cầu “một class implements nhiều interface có `throws` khác nhau”, hãy thực hiện:

1. **Xác định đúng cùng signature:** tên method và kiểu tham số có thực sự khớp hay chỉ là overload?
2. **Đọc từng hợp đồng:** ghi lại các kiểu checked được khai báo ở mỗi interface. Bỏ qua sự khác biệt message và import alias.
3. **Vẽ quan hệ kế thừa:** ví dụ `FileNotFoundException <: IOException <: Exception`.
4. **Tìm các loại checked được mọi hợp đồng cho phép:** xét subtype, không chỉ giao hai danh sách tên.
5. **Chọn `throws` hẹp nhất cần thiết:** có thể bỏ hoàn toàn checked `throws` nếu implementation xử lý nội bộ.
6. **Xem thân method có thể ném gì:** kiểm tra lời gọi I/O/SQL, constructor/resource close, `throw` trực tiếp.
7. **Nếu không thể để checked exception thoát:** xử lý đúng ý nghĩa, bọc unchecked có cause khi hợp đồng cho phép, hoặc thiết kế lại API.
8. **Kiểm tra caller:** lời gọi qua A, B hay class implementation có thể có nghĩa vụ checked khác nhau.
9. **QA:** bảo đảm `public`, return type tương thích, `@Override` và không có lỗi do default/generics ngoài phạm vi.
10. **Test runtime:** xác nhận lỗi được báo thật sự, không nuốt, không trả thành công giả và không làm sai trạng thái dữ liệu.

Cách làm này thường hiệu quả hơn việc thử thay `throws Exception` khắp code cho đến khi compiler im lặng.

## 18. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Implementation được `throws IOException, SQLException` vì A cho IO còn B cho SQL.” | **Không**. Mỗi checked exception phải phù hợp với **tất cả** các contract mà method override. |
| “Chỉ việc giữ nguyên `throws` của interface thứ nhất.” | Phải xét cả interface còn lại. |
| “Khác `throws` nghĩa là hai overload khác nhau.” | `throws` không phân biệt overload; cùng tên/tham số thường vẫn là một signature. |
| “Không khai báo checked exception thì method không thể xảy ra lỗi.” | Vẫn có thể ném unchecked hoặc xử lý checked nội bộ. |
| “Implementation có thể ném `IOException` dù interface khác không cho vì method body thực sự gọi file.” | Compiler yêu cầu xử lý checked bên trong hoặc thay thiết kế; không cho vi phạm interface. |
| “Nếu A throws IOException, B throws FileNotFoundException thì implementation phải bỏ hết.” | Có thể khai báo `FileNotFoundException` vì đây là subtype của `IOException`. |
| “Implementation được ghi `throws IOException` vì B cho FileNotFoundException.” | Sai chiều subtype: IOException rộng hơn. |
| “Gọi qua kiểu class hay interface đều chịu cùng `throws`.” | Nghĩa vụ compile-time dựa trên khai báo method nhìn thấy qua **kiểu tĩnh** của receiver. |
| “Bắt IOException ở lời gọi qua class không `throws` luôn hợp lệ.” | Một handler checked cụ thể có thể bị compiler từ chối nếu `try` không có nguồn exception phù hợp. |
| “`@Override` giúp bỏ qua xung đột checked exception.” | `@Override` chỉ yêu cầu compiler kiểm tra quan hệ override. |
| “Biến checked thành unchecked luôn là cách thiết kế tốt.” | Chỉ hợp lý khi có hợp đồng và chính sách xử lý rõ, giữ cause, không che lỗi. |
| “Có thể bắt `Exception` rồi bỏ qua để thỏa cả hai interface.” | Có thể che thất bại nghiệp vụ và side effect; bắt phải đi kèm xử lý thật. |
| “Một class chỉ implements được một interface có method `run()`.” | Có thể implements nhiều interface chung signature nếu các hợp đồng tương thích. |
| “Superclass đã có method thì chắc chắn satisfies mọi interface.” | Method kế thừa vẫn phải thỏa checked `throws` của tất cả; có thể cần override. |
| “Đổi sang `throws Throwable` sẽ giải quyết xung đột.” | Càng rộng, thường bị từ chối và là hợp đồng không phù hợp. |
| “Các lỗi default method/generic đều do `throws`.” | Còn nhiều quy tắc độc lập về return type, signature, erasure, implementation conflict. |

## 19. Bài tập thực hành

### Bài 1 — Xung đột hai checked exception không liên quan

Cho hai interface:

```java
interface A {
    void run() throws java.io.IOException;
}
interface B {
    void run() throws java.sql.SQLException;
}
```

Hãy viết `class C implements A, B` với một `public void run()` hợp lệ. Nếu code bên trong cần gọi API `throws IOException`, nêu hai lựa chọn có trách nhiệm: xử lý I/O nội bộ hoặc chuyển sang unchecked có cause theo hợp đồng. Vì sao thêm `throws IOException` trực tiếp lại sai?

### Bài 2 — Tìm kiểu checked hợp lệ

A khai báo `throws IOException`; B khai báo `throws FileNotFoundException`. Đánh giá implementation với: (a) không `throws`, (b) `throws FileNotFoundException`, (c) `throws IOException`, (d) `throws Exception`. **Đáp án:** (a) và (b) hợp lệ về mệnh đề throws; (c), (d) không hợp lệ so với B.

### Bài 3 — Nghĩa vụ khi upcast

Chạy `DisjointThrowsDemo`. Thay biến `CombinedAction implementation` ở `main` bằng `FileAction implementation`, rồi thử gọi `implementation.execute()` mà không catch/declare. Compiler phản hồi gì? Đổi tiếp kiểu tham chiếu thành `DatabaseAction` và so sánh.

### Bài 4 — Unchecked ngoại lệ không bị interface giới hạn

Chạy `UncheckedAcrossInterfacesDemo`. Vì sao `IllegalStateException` lọt qua cả hai hợp đồng checked `throws`? Có nên dùng `IllegalStateException` cho mọi lỗi I/O/SQL? **Không**; chọn exception dựa trên ngữ nghĩa, cách phục hồi và cause.

### Bài 5 — Superclass và interface

Trong `InheritedThrowsDemo`, bỏ override `UnifiedService.sync()`. Giải thích lỗi compile-time. Khôi phục override không `throws` và xác nhận code gọi qua `BaseService`, `SqlContract`, `UnifiedService` có nghĩa vụ checked khác nhau.

### Bài 6 — Đổi API để giảm mâu thuẫn

Giả sử hai interface đều có `void save()` nhưng một cái “save file”, một cái “save database”. Thiết kế lại thành `saveToFile() throws IOException` và `saveToDatabase() throws SQLException`. Phân tích vì sao hai method tách nghĩa dễ bảo trì hơn một `save()` phải chuyển loại lỗi.

### Bài 7 — Thứ tự handler không làm thay đổi nghĩa vụ `throws`

Một implementation thỏa cả hai interface bằng cách không khai báo checked. Caller `FileAction file = implementation;` có nên viết `catch(SQLException)` đơn độc quanh `file.execute()` không? **Không**, vì chữ ký nhìn thấy tại call site công bố `IOException`. Viết handler đúng rồi mô tả ngoại lệ runtime nếu implementation ném `IllegalStateException`.

### Bài 8 — Thiết kế adapter

Viết một service nội bộ `StorageService.read() throws IOException`. Tạo một adapter thực thi interface `Task.run()` không `throws`: adapter bắt `IOException` và trả status thất bại có cấu trúc (nếu giao diện cho phép), hoặc ném một unchecked wrapper với cause. Đảm bảo không trả kết quả thành công giả và không làm mất lỗi gốc.

### Bài 9 — Exception kiểu cha và con

Interface A `throws Exception`, interface B `throws IOException`. Implementation có thể `throws IOException`? **Có**. Có thể `throws SQLException`? **Không**, vì B không cho phép. Có thể `throws FileNotFoundException`? **Có**, vì nó là subtype của IOException.

### Bài 10 — Phân biệt method signature với `throws`

Cho hai method `load(int) throws IOException` và `load(String) throws SQLException`. Vì sao đây là overload hợp lệ, trong khi hai method `load(int)` chỉ khác `throws` lại không hợp lệ? Trình bày vai trò danh sách tham số và lý do return type/throws không tạo overload độc lập.

## 20. Checklist trước khi hoàn thành

- [ ] Tôi xác định đúng các method cùng signature và có thực sự phải chung implementation chưa?
- [ ] Đã đọc **tất cả** interface mà method implementation override chưa?
- [ ] Đã phân biệt checked `Exception` với unchecked `RuntimeException`/`Error` chưa?
- [ ] Mỗi checked exception trong `throws` của implementation đều được **mọi** hợp đồng cho phép chưa?
- [ ] Tôi đã xét quan hệ subtype, không chỉ so sánh danh sách tên exception chưa?
- [ ] Khi hai interface cho IOException và SQLException không liên quan, tôi có biết implementation không được khai báo cả hai không?
- [ ] Khi một interface cho IOException, interface kia cho FileNotFoundException, tôi chọn được throws hẹp không?
- [ ] Tôi đã kiểm tra checked exception phát sinh trực tiếp/gián tiếp trong thân implementation chưa?
- [ ] Nếu phải xử lý trong thân, tôi có tránh nuốt lỗi và giữ `cause` khi chuyển loại không?
- [ ] Tôi nhớ nghĩa vụ checked tại call site được xác định bởi **kiểu tĩnh của receiver** chưa?
- [ ] Tôi biết implementation không khai báo checked vẫn có thể ném unchecked exception chưa?
- [ ] Tôi đã để method thực thi interface ở mức truy cập `public` và dùng `@Override` chưa?
- [ ] Tôi không cố tạo overload chỉ khác `throws` chưa?
- [ ] Nếu có superclass, tôi đã kiểm tra method kế thừa và override bổ sung chưa?
- [ ] Tôi đã phân biệt lỗi `throws` với lỗi xung đột default method, generic erasure, kiểu trả về chưa?
- [ ] Test có kiểm tra cả đường thành công, lỗi thực tế và trạng thái sau thất bại chưa?

**Kết luận:** Khi một phương thức thực thi nhiều interface với các mệnh đề `throws` khác nhau, **implementation phải thỏa tất cả các hợp đồng checked exception cùng lúc**. Với `IOException` và `SQLException` không liên quan, method triển khai không được khai báo checked exception từ hai nhánh đó; với `IOException` và `FileNotFoundException`, có thể khai báo loại hẹp `FileNotFoundException`. Caller vẫn bị kiểm tra theo kiểu tham chiếu tĩnh của mình. Nếu implementation cần thao tác có checked exception nằm ngoài phần hợp đồng chung, phải xử lý có trách nhiệm hoặc thiết kế lại API, không chỉ “thêm `throws`” cho qua compiler.