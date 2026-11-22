# Checked exception trong phương thức ghi đè (`override`) của Java

## 1. Mục tiêu học tập

Khi một lớp con **ghi đè phương thức** của lớp cha hoặc một lớp **triển khai phương thức interface**, Java không chỉ kiểm tra tên, tham số, quyền truy cập và kiểu trả về: nó còn kiểm tra **hợp đồng checked exception**. Phương thức ghi đè **không được tự ý khai báo một checked exception mới hoặc rộng hơn** những ngoại lệ mà khai báo được ghi đè cho phép.

Ví dụ, nếu lớp cha khai báo `read() throws IOException` thì lớp con có thể giữ `IOException`, thu hẹp thành `FileNotFoundException`, hoặc bỏ checked exception. Lớp con **không** được đổi thành `throws Exception` hay `throws SQLException`, vì bên gọi đang dựa trên hợp đồng cũ và không phải chuẩn bị cho các checked exception ngoài hợp đồng đó.

Sau bài này bạn sẽ có thể:

- Hiểu quy tắc `throws` khi `@Override` đối với class, abstract class và interface.
- Phân biệt ba lựa chọn hợp lệ: **giữ**, **thu hẹp** hoặc **bỏ** checked exception.
- Nhận ra trường hợp **mở rộng** hoặc **thêm checked exception khác nhánh** gây lỗi biên dịch.
- Biết vì sao checked exception vẫn phải được xử lý nếu lời gọi có **kiểu tĩnh là lớp cha/interface**, dù implementation không ném lỗi ấy.
- Phân biệt kiểm tra checked exception với `RuntimeException` và `Error` (unchecked).
- Hiểu các ràng buộc khi một lớp triển khai **hai interface** có phương thức cùng chữ ký nhưng khác `throws`.
- Xem đúng vai trò của `throws`, `throw`, `try/catch`, `instanceof`, và kiểu tham số tổng quát trong hợp đồng exception.
- Thiết kế API bảo toàn khả năng thay thế đối tượng (*substitutability*), không làm caller phải thay đổi ngoài ý muốn.

Ví dụ tương thích Java 17+, các chương trình hoàn chỉnh có tên tệp, lệnh `javac`/`java` và kết quả `stdout` ổn định.

## 2. Quy tắc cốt lõi: phương thức ghi đè không mở rộng checked exception

Xem hợp đồng của lớp cha:

```java
class BaseReader {
    String read() throws java.io.IOException {
        return "data";
    }
}
```

Một phương thức override ở lớp con phải tương thích với hợp đồng ấy. Về checked exception, các khai báo dưới đây là **hợp lệ khi xét riêng điều kiện `throws`**:

```java
class SameReader extends BaseReader {
    @Override
    String read() throws java.io.IOException {
        return "same";
    }
}

class SpecificReader extends BaseReader {
    @Override
    String read() throws java.io.FileNotFoundException {
        return "specific";
    }
}

class CachedReader extends BaseReader {
    @Override
    String read() {
        return "cached";
    }
}
```

Ba class trên là **mã khai báo minh họa**, chưa có `main`. Điều kiện hợp lệ:

- `IOException` là chính kiểu checked exception mà `BaseReader.read()` cho phép.
- `FileNotFoundException` là **lớp con của `IOException`**, nên thu hẹp hợp đồng.
- Không khai báo checked exception là hợp lệ nếu thân phương thức không truyền checked exception trái phép ra ngoài.

Ngược lại, hai khai báo sau là **không hợp lệ** nếu dùng để override `BaseReader.read()`:

```java
class TooBroadReader extends BaseReader {
    @Override
    String read() throws Exception {
        return "invalid"; // LỖI BIÊN DỊCH: Exception rộng hơn IOException.
    }
}

class WrongBranchReader extends BaseReader {
    @Override
    String read() throws java.sql.SQLException {
        return "invalid"; // LỖI BIÊN DỊCH: SQLException không thuộc IOException.
    }
}
```

Hai class này chỉ dùng để giải thích lỗi; **không đưa vào cùng dự án đang muốn build thành công**. Cả `Exception` và `SQLException` đều là checked exception, nhưng không được hợp đồng của `BaseReader.read()` bao phủ.

### Câu hỏi cần tự đặt

Nếu chương trình bên gọi chỉ biết một đối tượng dưới kiểu `BaseReader`, trình biên dịch đã buộc nó xử lý hoặc khai báo `IOException`. Nếu lớp con bất ngờ được phép ném `SQLException` hoặc `Exception` rộng hơn, caller có thể gặp một checked exception mà chữ ký lớp cha không báo trước. Java ngăn tình huống này ở **compile time**.

Quy tắc có thể hình dung:

```text
BaseReader.read() throws IOException
                  |
                  v
        override được phép:
          IOException
          FileNotFoundException
          không checked exception
                  |
                  x
        override không được:
          Exception
          SQLException
          ParseException
```

Đây là sơ đồ minh họa những kiểu ngoại lệ tiêu biểu. Quy tắc chính xác phải xét **quan hệ kiểu kế thừa**, không đơn thuần dựa vào tên ngoại lệ.

## 3. Checked và unchecked exception khác nhau thế nào?

Java phân loại:

```text
Throwable
├── Error                    (unchecked)
└── Exception
    ├── IOException          (checked)
    │   └── FileNotFoundException (checked)
    ├── SQLException         (checked)
    ├── ParseException       (checked)
    └── RuntimeException    (unchecked)
        ├── IllegalArgumentException
        └── IllegalStateException
```

Đây là sơ đồ **rút gọn**. Checked exception là các kiểu `Throwable` không thuộc `RuntimeException` hoặc `Error` (và các lớp con của chúng).

Với **checked exception**, phương thức override không được thêm kiểu nằm ngoài phạm vi cho phép của khai báo bị ghi đè. Với **unchecked exception**, compiler không buộc override phải giới hạn tương tự. Điều này có nghĩa:

```java
class BaseService {
    void execute() {
        // Không khai báo checked exception.
    }
}

class StrictService extends BaseService {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("invalid state");
    }
}
```

Đây là các class minh họa hợp lệ. `IllegalStateException` kế thừa `RuntimeException` nên dù phương thức cha không khai báo nó, lớp con vẫn được phép `throw` và tùy chọn công bố trong `throws`.

Tuy nhiên, **hợp lệ về cú pháp không có nghĩa thiết kế API đã tốt**: thêm những unchecked exception bất ngờ vẫn có thể gây lỗi runtime và vi phạm kỳ vọng nghiệp vụ. Quy tắc chỉ nói rằng compiler không áp hạn chế checked exception tương ứng.

### Tại sao `Error` không bị kiểm tra giống checked exception?

Các loại `Error` (ví dụ `OutOfMemoryError`) thuộc nhánh unchecked và có thể phát sinh ngay cả khi không nằm trong `throws`. Đừng viết `catch (Throwable)` để “sửa” hợp đồng override hoặc cố coi mọi `Error` là lỗi có thể phục hồi. Nguyên tắc xử lý checked/unchecked và chính sách khôi phục là hai chủ đề khác nhau.

## 4. Ví dụ chạy được: lớp con bỏ checked exception

Tạo file **`OverrideNoCheckedDemo.java`**:

```java
import java.io.IOException;

class ParentReader {
    String read() throws IOException {
        return "parent";
    }
}

class MemoryReader extends ParentReader {
    @Override
    String read() {
        return "memory";
    }
}

public class OverrideNoCheckedDemo {
    public static void main(String[] args) throws IOException {
        ParentReader parentView = new MemoryReader();
        MemoryReader childView = new MemoryReader();

        System.out.println("parent type=" + parentView.read());
        System.out.println("child type=" + childView.read());
    }
}
```

Biên dịch/chạy:

```bash
javac OverrideNoCheckedDemo.java
java OverrideNoCheckedDemo
```

`stdout` chính xác:

```text
parent type=memory
child type=memory
```

Giải thích:

1. `ParentReader.read()` khai báo `throws IOException`.
2. `MemoryReader.read()` ghi đè hợp lệ vì **không khai báo checked exception**.
3. Tại runtime, cả `parentView.read()` và `childView.read()` đều chạy implementation của `MemoryReader` do dynamic dispatch.
4. Tuy nhiên, `parentView` có **kiểu tĩnh `ParentReader`**, nên trình biên dịch xem lời gọi đó có thể ném `IOException` theo hợp đồng lớp cha. `main` khai báo `throws IOException` để thỏa điều kiện.
5. `childView` có kiểu tĩnh `MemoryReader`; chỉ xét lời gọi này, compiler không yêu cầu bắt `IOException` vì phương thức trong kiểu được nhìn thấy không khai báo checked exception đó.

**Phân biệt quan trọng:** phương thức thực sự chạy được chọn theo **kiểu runtime**, còn nghĩa vụ checked exception tại chỗ gọi dựa trên **kiểu tĩnh và khai báo phương thức được compiler chọn**.

### Không được xóa nghĩa vụ chỉ vì biết đối tượng thật là lớp con

Giả sử đoạn mã:

```java
ParentReader reader = new MemoryReader();
System.out.println(reader.read());
```

Nếu đặt trong một phương thức **không có `throws IOException` và không có `try/catch`**, nó sẽ **không biên dịch**. Biết được implementation ở runtime không xóa hợp đồng `throws IOException` của kiểu `ParentReader` tại compile time.

Ngược lại:

```java
MemoryReader reader = new MemoryReader();
System.out.println(reader.read());
```

Đây là mảnh minh họa được phép dùng mà không cần checked handler cho `IOException` từ lời gọi `read()` đó, vì chữ ký của `MemoryReader.read()` không khai báo checked exception.

## 5. Ví dụ chạy được: thu hẹp từ `IOException` xuống `FileNotFoundException`

Tạo tệp **`OverrideNarrowThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

class FileProvider {
    void open() throws IOException {
        throw new IOException("base IO failure");
    }
}

class MissingFileProvider extends FileProvider {
    @Override
    void open() throws FileNotFoundException {
        throw new FileNotFoundException("missing.txt");
    }
}

public class OverrideNarrowThrowsDemo {
    public static void main(String[] args) {
        FileProvider parentView = new MissingFileProvider();
        MissingFileProvider childView = new MissingFileProvider();

        try {
            parentView.open();
        } catch (IOException failure) {
            System.out.println("parent catch="
                    + failure.getClass().getSimpleName());
        }

        try {
            childView.open();
        } catch (FileNotFoundException failure) {
            System.out.println("child catch="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac OverrideNarrowThrowsDemo.java
java OverrideNarrowThrowsDemo
```

Kết quả:

```text
parent catch=FileNotFoundException
child catch=FileNotFoundException
```

- Khi nhìn qua `FileProvider`, bên gọi phải chuẩn bị cho `IOException`.
- Khi nhìn qua `MissingFileProvider`, bên gọi có thể bắt cụ thể `FileNotFoundException`.
- Trong cả hai lần chạy, implementation thực là `MissingFileProvider.open()` và ném cùng kiểu `FileNotFoundException`.
- `FileNotFoundException` có quan hệ kế thừa với `IOException`, nên hợp đồng lớp con không làm bên gọi của lớp cha bất ngờ với một checked exception ngoài phạm vi.

**Lưu ý:** `catch (IOException)` có thể bắt cả `FileNotFoundException`. Nhưng với `childView.open()`, `catch (FileNotFoundException)` cho phép xử lý chi tiết hơn dựa trên chữ ký đã thu hẹp.

## 6. Mở rộng checked exception: lỗi biên dịch dù thân không `throw`

Một quan niệm sai thường gặp: “Lớp con chỉ **khai báo** `throws Exception` nhưng thân không thực sự ném lỗi, vậy chắc hợp lệ.” Không đúng.

Ví dụ **cố ý không biên dịch**, nếu nằm trong cùng package/lớp phù hợp:

```java
import java.io.IOException;

class Parent {
    void run() throws IOException {
    }
}

class InvalidChild extends Parent {
    @Override
    void run() throws Exception {
        System.out.println("always succeeds");
    }
}
```

Compiler từ chối `InvalidChild.run()` vì `Exception` rộng hơn `IOException`, bất kể phần thân có ném hay không.

Lý do là **hợp đồng method declaration**, không phải thống kê một lần chạy. Khi thiết kế phương thức ghi đè, hãy đọc `throws` của các phương thức cha/interface liên quan thay vì chỉ nhìn vào những thao tác xảy ra trong implementation hiện tại.

### Cách sửa tùy mục đích

Nếu lớp con không ném checked exception, bỏ `throws Exception`:

```java
@Override
void run() {
    System.out.println("always succeeds");
}
```

Nếu thực sự cần ném `FileNotFoundException`:

```java
@Override
void run() throws java.io.FileNotFoundException {
    throw new java.io.FileNotFoundException("missing");
}
```

Cả hai đoạn chỉ là **mảnh phương thức minh họa** cho override của `Parent.run()`.

Nếu lỗi thực tế thuộc kiểu checked **khác nhánh** (chẳng hạn `SQLException`), bạn cần chọn một chiến lược hợp đồng hợp lệ:

- Xử lý lỗi SQL ngay tại implementation nếu có thể phục hồi.
- Chuyển đổi có ý nghĩa sang một **kiểu checked được hợp đồng lớp cha cho phép**, đồng thời giữ ngoại lệ SQL ban đầu làm `cause`.
- Thiết kế một API khác nếu bản chất thao tác đã thay đổi đến mức không còn thỏa hợp đồng ban đầu.
- Chỉ bọc thành unchecked exception khi phù hợp với semantics và chính sách ứng dụng; không chỉ để “lách” compile-time.

Không có cách viết `throws SQLException` trực tiếp trên override khi parent chỉ cho phép `IOException`.

## 7. Lớp cha không khai báo checked exception

Nếu lớp cha có:

```java
class AccountService {
    void update() {
        // ...
    }
}
```

Thì lớp con **không thể** ghi đè như sau:

```java
class CheckedAccountService extends AccountService {
    @Override
    void update() throws java.io.IOException {
        // Không hợp lệ: thêm checked IOException.
    }
}
```

Đây là ví dụ **cố ý không biên dịch**. Không có checked exception nào được khai báo trong `AccountService.update()`, nên override không được tự mở rộng thành `IOException`.

Nhưng lớp con có thể ném unchecked exception:

```java
class ValidatingAccountService extends AccountService {
    @Override
    void update() throws IllegalArgumentException {
        throw new IllegalArgumentException("account invalid");
    }
}
```

Đây là class minh họa hợp lệ. `IllegalArgumentException` thuộc `RuntimeException` nên không bị ràng buộc checked exception của override.

### Trường hợp cần gọi API có checked exception trong thân override

Giả sử bạn phải gọi một API I/O bên trong `update()`, trong khi phương thức cha không khai báo checked exception. Bạn không thể đẩy checked `IOException` ra ngoài trực tiếp bằng `throws`; cần **bắt và xử lý** hoặc **chuyển đổi** theo hợp đồng đã được chọn.

Đừng âm thầm ghi log rồi trả về thành công nếu thao tác cập nhật bắt buộc đã thất bại. Khi thật sự cần một khả năng thất bại mới, có thể phải thay đổi thiết kế interface ở tầng trừu tượng cao hơn thay vì chỉ sửa lớp con.

## 8. Override trong interface: cùng quy tắc

Interface có thể công bố checked exception:

```java
interface DataSource {
    String load() throws java.io.IOException;
}
```

Lớp triển khai có thể giữ, thu hẹp hoặc bỏ checked exception. Ví dụ **chạy được**:

Tạo file **`InterfaceOverrideDemo.java`**:

```java
import java.io.IOException;

interface DataSource {
    String load() throws IOException;
}

class InMemoryDataSource implements DataSource {
    @Override
    public String load() {
        return "cached data";
    }
}

public class InterfaceOverrideDemo {
    public static void main(String[] args) throws IOException {
        DataSource source = new InMemoryDataSource();
        InMemoryDataSource direct = new InMemoryDataSource();

        System.out.println("interface=" + source.load());
        System.out.println("concrete=" + direct.load());
    }
}
```

```bash
javac InterfaceOverrideDemo.java
java InterfaceOverrideDemo
```

`stdout`:

```text
interface=cached data
concrete=cached data
```

Hai điểm bổ sung:

- Phương thức triển khai interface `public String load()` phải giữ quyền truy cập `public` đúng quy tắc Java. Việc bỏ `throws IOException` vẫn hợp lệ.
- `source` có kiểu tĩnh `DataSource` nên `main` phải bắt/khai báo `IOException`. `direct` có kiểu tĩnh lớp cụ thể không khai báo checked exception.

### Abstract class cũng vậy

Một lớp abstract có thể khai báo:

```java
abstract class Task {
    abstract void execute() throws java.io.IOException;
}

class PureTask extends Task {
    @Override
    void execute() {
        System.out.println("no IO");
    }
}
```

Đây là các class minh họa hợp lệ. Không có thân cho phương thức abstract, nhưng chữ ký `throws IOException` vẫn là **hợp đồng**. Class con được thu hẹp hoặc bỏ checked exception, nhưng không mở rộng ra loại checked khác.

## 9. Ghi đè một phương thức khai báo **nhiều** checked exception

Khi lớp cha khai báo:

```java
void process()
        throws java.io.IOException, java.text.ParseException {
    // ...
}
```

Phương thức con có thể giữ cả hai, giữ một trong hai, dùng các subtype hợp lệ, hoặc bỏ checked exception. Điều kiện quan trọng: **mỗi checked exception mà phương thức con khai báo phải được bao phủ bởi ít nhất một kiểu thích hợp trong tập ngoại lệ của phương thức cha**.

Ví dụ quan hệ:

```text
Parent: throws IOException, ParseException
  |
  +-- Child A: throws IOException
  +-- Child B: throws FileNotFoundException
  +-- Child C: throws ParseException
  +-- Child D: throws FileNotFoundException, ParseException
  +-- Child E: không có checked exception
  |
  x-- Child F: throws SQLException
  x-- Child G: throws Exception
```

`FileNotFoundException` là con của `IOException`. `SQLException` không phải con của `IOException` hay `ParseException`. `Exception` rộng hơn hai nhánh kia, không hợp lệ nếu thêm thành kiểu checked cho override.

**Không có ràng buộc rằng lớp con phải giữ đủ số lượng loại lỗi**. Tập ngoại lệ được phép có thể nhỏ hơn nhiều khi implementation sử dụng cache, dữ liệu trong bộ nhớ hoặc đã xử lý lỗi ở bên trong.

### Ví dụ chạy được với hai kiểu checked

Tạo file **`MultipleCheckedOverrideDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.text.ParseException;

class Importer {
    void load(String source) throws IOException, ParseException {
        throw new ParseException("bad data", 0);
    }
}

class FileImporter extends Importer {
    @Override
    void load(String source) throws FileNotFoundException {
        if ("missing".equals(source)) {
            throw new FileNotFoundException(source);
        }
        System.out.println("loaded " + source);
    }
}

public class MultipleCheckedOverrideDemo {
    public static void main(String[] args) {
        Importer parentView = new FileImporter();
        FileImporter childView = new FileImporter();

        try {
            parentView.load("missing");
        } catch (IOException | ParseException failure) {
            System.out.println("parent="
                    + failure.getClass().getSimpleName());
        }

        try {
            childView.load("ok");
        } catch (FileNotFoundException failure) {
            System.out.println("child error");
        }
    }
}
```

```bash
javac MultipleCheckedOverrideDemo.java
java MultipleCheckedOverrideDemo
```

`stdout`:

```text
parent=FileNotFoundException
loaded ok
```

Phân tích:

- `Importer.load(...)` công bố hai kiểu checked `IOException` và `ParseException`.
- `FileImporter.load(...)` chỉ khai báo `FileNotFoundException`, là subtype hợp lệ của `IOException`, và không ném `ParseException`.
- `parentView` được nhìn qua kiểu `Importer` nên handler có thể phải bao phủ **cả hai kiểu**.
- `childView` được nhìn qua lớp cụ thể nên handler có thể tập trung vào `FileNotFoundException`.
- Phương thức trong lớp con thực sự chỉ ném lỗi file ở đường `missing` hoặc in thành công ở đường `ok`; nó không bắt buộc ném mọi kiểu của lớp cha.

Không dùng dấu `|` trong `throws`: khai báo nhiều kiểu sử dụng dấu phẩy. `|` được sử dụng trong `multi-catch` như `catch (IOException | ParseException e)`.

## 10. Một lớp triển khai **hai interface** có cùng phương thức nhưng khác `throws`

Trường hợp này thường gây bất ngờ. Giả sử:

```java
interface FileAction {
    void run() throws java.io.IOException;
}

interface SqlAction {
    void run() throws java.sql.SQLException;
}
```

Một lớp vừa implements `FileAction`, vừa implements `SqlAction` phải cung cấp một phương thức `run()` tương thích **đồng thời với cả hai hợp đồng**.

Nếu viết:

```java
class InvalidCombined implements FileAction, SqlAction {
    @Override
    public void run() throws java.io.IOException {
        // LỖI: SQLException contract của SqlAction không cho phép IOException.
    }
}
```

Đây là class **cố ý không biên dịch**: dù `IOException` được `FileAction` cho phép, nó không được `SqlAction` bao phủ. Tương tự, chỉ khai báo `SQLException` cũng không tương thích với `FileAction`.

Trong trường hợp hai nhánh `IOException` và `SQLException` **không có subtype checked exception chung**, implementation không thể khai báo checked exception thuộc một trong hai nhánh; nhưng vẫn có thể **không khai báo checked exception**.

### Ví dụ hoàn chỉnh: cùng implementation, ba kiểu tham chiếu

Tạo tệp **`MultipleInterfacesThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

interface FileAction {
    void run() throws IOException;
}

interface SqlAction {
    void run() throws SQLException;
}

class CombinedAction implements FileAction, SqlAction {
    @Override
    public void run() {
        System.out.println("run");
    }
}

public class MultipleInterfacesThrowsDemo {
    public static void main(String[] args)
            throws IOException, SQLException {
        CombinedAction direct = new CombinedAction();
        FileAction asFile = direct;
        SqlAction asSql = direct;

        direct.run();
        asFile.run();
        asSql.run();
    }
}
```

```bash
javac MultipleInterfacesThrowsDemo.java
java MultipleInterfacesThrowsDemo
```

`stdout`:

```text
run
run
run
```

Chú ý:

- `CombinedAction.run()` không công bố checked exception; nó tương thích với **cả hai interface**.
- `direct.run()` nhìn qua lớp cụ thể nên không phát sinh nghĩa vụ checked `IOException`/`SQLException` từ chữ ký.
- `asFile.run()` nhìn qua `FileAction`, vẫn có thể ném `IOException` theo hợp đồng tĩnh.
- `asSql.run()` nhìn qua `SqlAction`, vẫn có thể ném `SQLException` theo hợp đồng tĩnh.
- Vì `main` gọi cả ba, chữ ký `main throws IOException, SQLException` là hợp lệ.

**Khái niệm then chốt:** khi một phương thức ghi đè/triển khai nhiều phương thức cha, ràng buộc checked exception cần tương thích với **từng khai báo bị ghi đè**, không lấy hợp của các danh sách `throws` rồi tự ý ném bất kỳ loại nào trong đó.

### Nếu hai interface khai báo cùng kiểu cha?

Ví dụ `A.run() throws IOException` và `B.run() throws Exception`: một implementation `run() throws IOException` có thể hợp lệ về exception, vì `IOException` nằm trong cả phạm vi `IOException` và `Exception`. Điều kiện là kiểu checked exception của override phải thỏa đồng thời những hợp đồng liên quan.

## 11. `RuntimeException` vẫn có thể xuất hiện dù interface không khai báo lỗi

Ví dụ interface `Runnable` có phương thức:

```java
public abstract void run();
```

Trong Java, `Runnable.run()` không khai báo checked exception. Vì vậy một implementation không được tự thêm `throws IOException`:

```java
// Không hợp lệ nếu dùng để triển khai Runnable.run():
@Override
public void run() throws java.io.IOException {
    // ...
}
```

Đây là **mảnh cố ý không biên dịch**. Trường hợp thường gặp là một worker cần gọi API I/O có checked exception. Người viết có thể **bắt và xử lý** I/O tại worker, hoặc **bọc thành unchecked exception** mà vẫn giữ cause theo hợp đồng ứng dụng.

### Ví dụ chạy được: bọc checked exception cho `Runnable`

Tạo file **`RunnableOverrideDemo.java`**:

```java
import java.io.IOException;

public class RunnableOverrideDemo {
    static class TaskFailure extends RuntimeException {
        TaskFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void readData() throws IOException {
        throw new IOException("source unavailable");
    }

    static class ReaderTask implements Runnable {
        @Override
        public void run() {
            try {
                readData();
            } catch (IOException original) {
                throw new TaskFailure("task failed", original);
            }
        }
    }

    public static void main(String[] args) {
        Runnable task = new ReaderTask();

        try {
            task.run();
        } catch (TaskFailure failure) {
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac RunnableOverrideDemo.java
java RunnableOverrideDemo
```

`stdout`:

```text
outer=task failed
cause=IOException
```

`ReaderTask.run()` không khai báo checked `IOException`; nó bắt lỗi I/O và **bọc** bằng `TaskFailure` (unchecked) trong khi giữ đối tượng nguyên nhân làm cause.

**Giới hạn ví dụ:** chương trình gọi `task.run()` **trực tiếp trên luồng `main`** để có output xác định. Nếu dùng `new Thread(task).start()`, ngoại lệ không được bắt trong worker sẽ đi theo cơ chế lỗi không được bắt của thread đó, **không tự ném lại** vào luồng main. Với `ExecutorService.submit(...)`, lỗi task có thể nằm trong `Future` và được quan sát qua `get()`. Không nhầm chính sách exception của các luồng khác với quy tắc override `throws`.

**Không dùng unchecked wrapper chỉ để che lỗi:** đây là quyết định API. Nếu caller có thể phục hồi từ lỗi đọc, hãy cung cấp một interface chức năng/phương thức có hợp đồng checked exception phù hợp thay vì ép tất cả lỗi sang RuntimeException.

## 12. Phương thức override không đồng nghĩa phương thức overload

Overriding là cung cấp implementation mới cho một chữ ký kế thừa phù hợp. Overloading là có các phương thức **khác danh sách tham số**.

Hai phương thức sau không tạo overload chỉ vì `throws` khác nhau:

```java
void load() throws java.io.IOException { }
void load() throws java.sql.SQLException { }
```

Đây là **mã cố ý không biên dịch** nếu đặt cả hai trong cùng một class: danh sách `throws` **không** tạo chữ ký overload khác nhau.

Ngược lại:

```java
void load(String key) throws java.io.IOException { }
void load(int id) throws java.sql.SQLException { }
```

Đây là hai method minh họa có **tham số khác nhau**, nên có thể là overload. Chúng không ghi đè nhau chỉ vì cùng tên. Mỗi lời gọi overload có hợp đồng exception riêng dựa trên phương thức được compiler chọn.

### Không nhầm phương thức `static` với override

Phương thức static cùng chữ ký ở lớp con **ẩn** phương thức static của lớp cha (*method hiding*), không tham gia dynamic dispatch như override. JLS vẫn đặt ràng buộc phù hợp về checked exception đối với static method hiding.

Không thể dùng `@Override` cho method static. Khi phân tích ngoại lệ của lời gọi static, cần xét phương thức được compiler chọn từ kiểu chứa/chữ ký, không mô tả đó là “ghi đè runtime”.

### Constructor không được override

Constructor có thể khai báo `throws` của riêng nó, và lời gọi `super(...)` có thể phát sinh checked exception. Nhưng constructor **không được kế thừa hoặc ghi đè**, vì vậy không áp quy tắc `@Override` của phương thức lên constructor theo cách máy móc. Có các quy tắc khởi tạo/checked exception riêng cần kiểm tra nếu constructor lớp cha ném lỗi.

## 13. Generic và kiểu ngoại lệ trong `throws`

Java cho phép một số API generic khai báo exception type parameter. Khi triển khai/gắn một tham số kiểu cụ thể, hợp đồng throws cũng được chuyên biệt hóa.

Ví dụ:

```java
interface CheckedTask<E extends Exception> {
    void execute() throws E;
}
```

Một implementation với tham số `IOException` có thể thu hẹp hơn, chẳng hạn `FileNotFoundException`. Điều này giống nguyên tắc lớp cha thường: kiểu checked được ném phải nằm trong phạm vi mà contract generic sau khi thay thế tham số kiểu cho phép.

### Ví dụ chạy được: generic checked exception

Tạo file **`GenericThrowsOverrideDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

interface CheckedTask<E extends Exception> {
    void execute() throws E;
}

class FileCheckTask implements CheckedTask<IOException> {
    @Override
    public void execute() throws FileNotFoundException {
        throw new FileNotFoundException("missing resource");
    }
}

public class GenericThrowsOverrideDemo {
    public static void main(String[] args) {
        CheckedTask<IOException> task = new FileCheckTask();

        try {
            task.execute();
        } catch (IOException failure) {
            System.out.println(
                    failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac GenericThrowsOverrideDemo.java
java GenericThrowsOverrideDemo
```

`stdout`:

```text
FileNotFoundException
```

`CheckedTask<IOException>` được nhìn qua kiểu interface có `execute() throws IOException` sau chuyên biệt hóa type parameter. Implementation chỉ ném subtype `FileNotFoundException` nên hợp lệ. `catch (IOException)` tại caller đủ để xử lý ngoại lệ.

**Ghi chú nâng cao:** Khi dùng generic methods, type erasure, hoặc nhiều khai báo được kế thừa cùng chữ ký, JLS quy định chi tiết cách đánh giá tính tương thích checked exception (bao gồm các điều kiện với erasure). Trước khi thiết kế một API generic phức tạp, nên đọc quy tắc chính thức chứ không suy luận bằng so sánh văn bản đơn giản của các danh sách `throws`.

## 14. Các lỗi biên dịch hay gặp và cách sửa

| Khai báo lớp cha/interface | Override hoặc implementation | Hợp lệ? | Giải thích |
| --- | --- | --- | --- |
| `throws IOException` | `throws IOException` | Có | Giữ nguyên loại checked |
| `throws IOException` | `throws FileNotFoundException` | Có | Thu hẹp sang subtype |
| `throws IOException` | Không có `throws` | Có | Bỏ checked exception |
| `throws IOException` | `throws Exception` | **Không** | `Exception` rộng hơn `IOException` |
| `throws IOException` | `throws SQLException` | **Không** | Khác nhánh checked |
| `throws IOException` | `throws IOException, SQLException` | **Không** | Thêm `SQLException` ngoài phạm vi |
| Không có checked exception | `throws IOException` | **Không** | Thêm checked exception |
| Không có checked exception | `throws IllegalStateException` | Có | Unchecked |
| `throws Exception` | `throws IOException` | Có | Thu hẹp từ `Exception` |
| `throws FileNotFoundException` | `throws IOException` | **Không** | Nới rộng loại checked |
| `throws IOException, ParseException` | `throws FileNotFoundException` | Có | Được bao phủ bởi `IOException` |
| `throws IOException, ParseException` | `throws SQLException` | **Không** | Không nằm trong hai loại được phép |

Bảng xét **riêng quy tắc checked exception khi ghi đè**, giả định phần còn lại của khai báo (kiểu trả về, tham số, quyền truy cập, kế thừa) đã hợp lệ. Một override vẫn có thể không biên dịch vì lý do khác: quyền truy cập bị giảm, tên/tham số không khớp, kiểu trả về không tương thích, hoặc cố override phương thức `final`.

### Ba cách sửa phổ biến

**Cách 1 — Thu hẹp `throws` đúng kiểu subtype:** Nếu API trong lớp con thực sự ném `FileNotFoundException`, hãy khai báo loại này thay vì `Exception`.

**Cách 2 — Bắt và xử lý tại lớp con:** Nếu lớp con gọi API có checked exception ngoài hợp đồng, xử lý theo chính sách có khả năng phục hồi trước khi thoát phương thức.

**Cách 3 — Chuyển đổi lỗi hợp lý và giữ cause:** Khi phải chuyển tầng, sử dụng một loại lỗi được hợp đồng cho phép hoặc unchecked exception có ngữ nghĩa rõ ràng và giữ `cause` gốc. Không xóa chi tiết nguồn lỗi bằng cách chỉ in `getMessage()` rồi trả về thành công giả.

Không tùy tiện sửa lớp cha bằng cách thêm `throws Exception` nếu đây là API công khai đã có caller. Mở rộng hợp đồng của lớp cha có thể làm **mọi bên gọi** phải bắt hoặc khai báo lỗi rộng hơn, gây tác động tương thích nguồn (*source compatibility*).

## 15. Thiết kế API: đừng biến `throws` thành danh sách dự phòng

### 15.1. Khai báo kiểu cụ thể nhất có ích cho caller

Nếu một phương thức chỉ làm đọc tệp, `IOException` thường có nghĩa hơn `Exception`. Lớp con có thể thu hẹp thành `FileNotFoundException` nếu bản chất thao tác của nó cho phép. Với interface dùng nhiều implementation, nên chọn hợp đồng phù hợp với **mọi implementation hợp lệ** mà bên gọi cần hỗ trợ.

### 15.2. Đừng lạm dụng `throws Exception` để “dễ code”

`throws Exception` cho phép nhiều loại checked exception, nhưng khiến bên gọi khó xử lý có chọn lọc. Trong quá trình override, nó còn không hợp lệ nếu lớp cha chỉ công bố loại hẹp hơn. Việc khai báo rộng ngay từ interface ban đầu nên là một quyết định API có cân nhắc, không phải mặc định.

### 15.3. Không ném lỗi để thực hiện nhánh điều khiển thông thường

Nếu tình huống “không tìm thấy giá trị” là kết quả bình thường, có thể cân nhắc `Optional` hoặc kiểu kết quả chuyên biệt thay vì exception (tùy API). Nhưng nếu lỗi I/O thực sự ngăn thao tác hoàn thành, không nên giả vờ thành công chỉ để bỏ `throws` ở lớp con.

### 15.4. Bảo toàn nguyên nhân khi đổi loại lỗi

Ví dụ mảnh mã:

```java
try {
    readFromDatabase();
} catch (java.sql.SQLException original) {
    throw new IllegalStateException(
            "Cannot load current configuration", original);
}
```

`readFromDatabase()` ở đây là phương thức minh họa chưa khai báo. `IllegalStateException` là unchecked, nên không trái quy tắc compile-time checked exception của override. Nhưng ứng dụng vẫn phải có chính sách xử lý khi lỗi xảy ra; không xem wrapper như cách “xử lý xong” sự cố.

Khi wrapper là checked exception, nó vẫn phải thuộc tập kiểu mà phương thức cha/interface cho phép.

### 15.5. Bảo đảm thay thế được lớp con cho lớp cha

Một caller dùng `BaseReader` không nên phải được viết lại chỉ vì lúc chạy đối tượng là `SomeSubclass`. Hạn chế checked exception của `@Override` giúp các implementation không phá vỡ hợp đồng bắt/khai báo checked exception mà caller đã tin tưởng.

## 16. Câu hỏi tự kiểm tra

1. **Parent khai báo `throws IOException`, Child có thể khai báo `throws FileNotFoundException` không?** Có, vì là subtype.
2. **Parent khai báo `throws IOException`, Child khai báo `throws Exception` hợp lệ?** Không, vì rộng hơn.
3. **Parent không khai báo checked exception, Child thêm `throws IOException` hợp lệ?** Không.
4. **Parent không khai báo checked exception, Child ném `IllegalStateException` được không?** Có về quy tắc checked exception, vì unchecked.
5. **Child không còn khai báo `IOException`, caller tham chiếu kiểu Parent có phải bắt IOException không?** Có, nếu khai báo Parent tại vị trí gọi còn `throws IOException`.
6. **Hai interface cùng `run()`, một throws IOException, một throws SQLException: implementation có được throws IOException không?** Không, vì không tương thích với interface thứ hai.
7. **Implementation của `Runnable.run()` có thể khai báo `throws IOException` không?** Không.
8. **Nếu cần gọi API I/O trong `Runnable.run()`, làm gì?** Bắt và xử lý hoặc đổi thành unchecked wrapper có cause theo hợp đồng.
9. **`throw` và `throws` khác nhau thế nào?** `throw` thực sự ném đối tượng; `throws` khai báo kiểu lỗi được phép truyền ra.
10. **Đổi thứ tự các loại trong danh sách `throws` có sửa được lỗi override không?** Không. Quy tắc là quan hệ kiểu, không phải thứ tự.
11. **Có thể overload hai phương thức chỉ khác `throws` không?** Không.
12. **Constructor có chịu quy tắc `@Override` của method không?** Không, constructor không được override.
13. **Implementation chỉ dùng bộ nhớ, không thể phát sinh IOException: có bắt buộc giữ `throws IOException` của interface không?** Không; có thể bỏ.
14. **Phương thức con `throws IOException` khi parent `throws FileNotFoundException` có hợp lệ?** Không, vì mở rộng từ subtype lên supertype.
15. **Khi parent `throws IOException, ParseException`, child chỉ `throws FileNotFoundException` có hợp lệ không?** Có.
16. **Nếu child phải báo SQLException nhưng parent chỉ IOException, có được khai báo trực tiếp SQLException không?** Không; cần thiết kế xử lý hoặc chuyển đổi phù hợp.
17. **Runtime chọn override nào, compiler kiểm tra checked exception theo điều gì?** Runtime dispatch chọn implementation; compiler kiểm tra theo khai báo phương thức ứng với kiểu tĩnh tại lời gọi.
18. **`@Override` có ý nghĩa gì?** Giúp compiler xác nhận method thực sự override/implement đúng chữ ký; nó không nới lỏng hợp đồng throws.
19. **Nếu lời gọi qua kiểu interface ném một unchecked exception không được công bố, Java có cho chạy?** Có thể xảy ra ở runtime; kiểm tra checked exception không ngăn unchecked exceptions.
20. **Nên làm gì trước khi đổi `throws` của một API công khai?** Xem callers và implementations hiện có, yêu cầu tương thích nguồn và chính sách xử lý lỗi.

## 17. Tài liệu Java chính thức

- [Java Language Specification 17 — `8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): mệnh đề throws, checked exception và exception type parameter.
- [Java Language Specification 17 — `8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception khi override và hide method.
- [Java Language Specification 17 — `9.4.1 Interface Method Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1): các quy tắc liên quan phương thức của interface.
- [Java Language Specification 17 — `11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): nghĩa vụ bắt hoặc khai báo checked exception.
- [Java Language Specification 17 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): kiểm tra lời gọi, kiểu biên dịch và phương thức được chọn.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): quan hệ ngoại lệ cha–con.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): interface với `run()` không khai báo checked exception.
- [Java SE 17 API — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): nhánh unchecked không chịu cùng hạn chế checked throws của override.

**Ghi nhớ:** Khi `@Override`, phương thức con được **giữ, thu hẹp hoặc bỏ** checked exception trong hợp đồng phương thức cha/interface, nhưng **không được thêm hoặc mở rộng** loại checked exception ngoài phạm vi ấy. `RuntimeException` và `Error` thuộc nhánh unchecked nên không chịu cùng kiểm tra biên dịch. Nghĩa vụ `try/catch` hoặc `throws` tại bên gọi phụ thuộc **kiểu tĩnh của tham chiếu**; implementation thực tế vẫn được chọn bằng dynamic dispatch.
