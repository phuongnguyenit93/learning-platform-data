# Thu hẹp hoặc bỏ khai báo checked exception khi ghi đè phương thức trong Java

Khi một lớp con **ghi đè (override)** phương thức của lớp cha hoặc **triển khai (implements)** một phương thức từ interface, Java cho phép phương thức mới **khai báo ít checked exception hơn**, khai báo **loại checked exception hẹp hơn**, hoặc **không khai báo checked exception nào**. Ngược lại, phương thức ghi đè không được tự ý mở rộng hợp đồng bằng một checked exception mới/rộng hơn mà lời khai báo ở kiểu cha không cho phép.

Đây là quy tắc quan trọng để bảo đảm **tính thay thế trong kế thừa**: nơi đang làm việc với đối tượng kiểu cha không phải bất ngờ xử lý thêm một loại lỗi checked hoàn toàn mới chỉ vì runtime chọn triển khai lớp con.

Ví dụ cốt lõi:

```java
interface DataSource {
    String read(String key) throws java.io.IOException;
}

class FileDataSource implements DataSource {
    @Override
    public String read(String key)
            throws java.io.FileNotFoundException {
        if ("missing".equals(key)) {
            throw new java.io.FileNotFoundException(key);
        }
        return "value:" + key;
    }
}

class MemoryDataSource implements DataSource {
    @Override
    public String read(String key) {
        return "value:" + key;
    }
}
```

Đây là **các khai báo minh họa** cần được đặt trong tệp/package Java hợp lệ. Hai lớp triển khai đều đúng hợp đồng `DataSource.read() throws IOException`:

- `FileNotFoundException` là **lớp con của `IOException`**, nên lớp triển khai được khai báo `throws FileNotFoundException`.
- `MemoryDataSource.read()` **bỏ hẳn `throws IOException`**, nên caller qua kiểu concrete không buộc phải bắt checked `IOException`.
- Tuy nhiên, nếu caller giữ tham chiếu kiểu `DataSource`, trình biên dịch vẫn nhìn thấy **hợp đồng kiểu cha `throws IOException`**, ngay cả khi đối tượng runtime là `MemoryDataSource`.

**Ghi nhớ:** quy tắc này liên quan tới **checked exception trong hợp đồng phương thức**, không phải việc runtime “đổi” kiểu đối tượng ngoại lệ hay bảo đảm lớp con sẽ không bao giờ gặp lỗi.

## 1. Phân biệt checked và unchecked exception

Trước khi hiểu thu hẹp `throws`, phải phân biệt hai nhóm theo quy tắc kiểm tra của Java.

| Nhóm | Các ví dụ | Trình biên dịch bắt buộc bắt/khai báo? |
| --- | --- | --- |
| **Checked exception** | `IOException`, `FileNotFoundException`, `SQLException`, `ParseException` | Có, khi một checked exception có thể thoát khỏi phương thức và chưa được xử lý |
| **Unchecked exception** | `RuntimeException` và các lớp con như `IllegalArgumentException`, `IllegalStateException` | Không |
| **Unchecked `Error`** | `Error` và các lớp con như `AssertionError`, `OutOfMemoryError` | Không, thường không phải lỗi nghiệp vụ có thể phục hồi |

Một phần cây kiểu:

```text
Throwable
├── Error                               (unchecked)
└── Exception
    ├── RuntimeException                (unchecked)
    │   ├── IllegalArgumentException
    │   └── IllegalStateException
    └── IOException                     (checked)
        ├── FileNotFoundException       (checked)
        └── EOFException                (checked)
```

Cây chỉ là một **trích đoạn minh họa**, không liệt kê tất cả loại ngoại lệ. `SQLException` là một nhánh checked khác thuộc `Exception`, không nằm dưới `IOException`.

Khi nói “override không được khai báo exception rộng hơn”, cần nói đầy đủ hơn:

> **Không được mở rộng tập checked exception theo cách vi phạm hợp đồng của phương thức được override.** Một phương thức override vẫn có thể khai báo hoặc ném **unchecked exceptions**; trình biên dịch không áp dụng giới hạn checked exception lên chúng theo cùng cách.

Ví dụ, phương thức cha không khai báo checked exception; phương thức con vẫn có thể viết `throws IllegalStateException` dù đây thường là khai báo không bắt buộc. Tuy nhiên, điều đó không có nghĩa tùy ý biến điều kiện thành công bình thường thành lỗi runtime là một thiết kế tốt.

## 2. Quy tắc override: cùng loại, hẹp hơn hoặc không có checked `throws`

Cho phương thức cha:

```java
class Parent {
    public void execute() throws java.io.IOException {
        // ...
    }
}
```

Khi một lớp con override `execute()`, những khai báo dưới đây **hợp lệ** nếu thân phương thức tuân thủ chúng.

### A. Giữ nguyên checked exception

```java
class KeepContract extends Parent {
    @Override
    public void execute() throws java.io.IOException {
        // Có thể phát sinh IOException.
    }
}
```

Lớp con giữ nguyên phạm vi lỗi I/O mà caller đã biết từ lớp cha.

### B. Thu hẹp sang lớp con của checked exception

```java
class NarrowContract extends Parent {
    @Override
    public void execute()
            throws java.io.FileNotFoundException {
        // Chỉ khai báo một loại checked exception hẹp hơn.
    }
}
```

`FileNotFoundException extends IOException`, nên caller được bảo vệ theo hợp đồng `IOException` của `Parent` vẫn đủ khả năng bắt ngoại lệ con.

### C. Bỏ hoàn toàn checked `throws`

```java
class NoCheckedContract extends Parent {
    @Override
    public void execute() {
        // Không để checked exception thoát ra.
    }
}
```

Đây là lựa chọn hợp lệ. Việc phương thức cha khai báo `throws IOException` **không buộc lớp con phải giữ nguyên danh sách `throws`**.

### D. Bổ sung unchecked exception

```java
class RuntimeFailureContract extends Parent {
    @Override
    public void execute() throws IllegalStateException {
        throw new IllegalStateException("resource not ready");
    }
}
```

Ví dụ này hợp lệ về luật checked exception: `IllegalStateException` là unchecked. Nhưng caller phải xem xét ý nghĩa API và điều kiện lỗi thực tế, không lạm dụng unchecked exception để né ràng buộc thiết kế.

### E. Mở rộng checked exception — không hợp lệ

```java
// Cố ý KHÔNG BIÊN DỊCH.
class InvalidWiderContract extends Parent {
    @Override
    public void execute() throws Exception {
        // ...
    }
}
```

`Exception` bao trùm nhiều checked exception ngoài `IOException`, nên không thể thay thế hợp đồng đã có bằng một khai báo rộng hơn.

### F. Thêm một loại checked exception khác nhánh — không hợp lệ

```java
// Cố ý KHÔNG BIÊN DỊCH.
class InvalidNewChecked extends Parent {
    @Override
    public void execute() throws java.sql.SQLException {
        // ...
    }
}
```

`SQLException` không phải lớp con của `IOException`, nên caller qua `Parent` không được chuẩn bị để xử lý loại checked exception mới đó.

**Nguyên tắc tổng quát:** đối với mỗi loại checked exception được khai báo bởi override, phải có một loại checked exception tương ứng trong các khai báo được phép của phương thức bị override sao cho loại của override **cùng kiểu hoặc hẹp hơn**. Đồng thời, nếu thân override phát sinh checked exception khác không được bắt, bản thân thân phương thức vẫn phải tuân thủ danh sách `throws` đã khai báo.

## 3. Vì sao luật này bảo vệ khả năng thay thế kiểu cha?

Xét mã tầng gọi:

```java
static void process(Parent operation) {
    try {
        operation.execute();
    } catch (java.io.IOException ex) {
        System.out.println("I/O problem");
    }
}
```

Đây là phương thức minh họa, dựa trên lớp `Parent` có `throws IOException`. Tầng gọi nhận một biến kiểu `Parent` và biết rằng lỗi checked cần quan tâm thuộc nhóm `IOException`.

Giả sử lớp con được phép override thành `throws SQLException`. Khi runtime chọn lớp con:

1. Caller chỉ có `catch (IOException)` vì đó là hợp đồng công khai của `Parent`.
2. Lớp con có thể để `SQLException` đi ra.
3. Caller không hề được yêu cầu bắt/khai báo `SQLException` khi biên dịch theo kiểu `Parent`.
4. Hợp đồng về khả năng thay thế bị phá vỡ.

Bởi vậy Java cấm việc **mở rộng checked exception** trong override. Thu hẹp thì an toàn hơn: `catch (IOException)` của caller vẫn bắt được `FileNotFoundException` là lớp con, và nếu lớp con không ném checked exception nào thì càng không có thêm gánh nặng.

### “Lớp con hứa ít lỗi hơn” không có nghĩa “lớp con không thể hỏng”

Một implementation không khai báo `throws` vẫn có thể:

- Ném `IllegalArgumentException` khi tham số sai.
- Ném `IllegalStateException` khi trạng thái đối tượng không hợp lệ.
- Gặp `NullPointerException` do lỗi lập trình.
- Bị ảnh hưởng bởi `Error` nghiêm trọng của JVM.
- Chuyển một lỗi checked đã bắt thành unchecked wrapper nếu hợp đồng API cho phép.

Do đó, bỏ checked `throws` là **thay đổi về hợp đồng kiểm tra ở compile time**, không phải bảo đảm toàn bộ thực thi không bao giờ có ngoại lệ.

## 4. Java kiểm tra theo kiểu tĩnh của lời gọi, không chỉ theo đối tượng runtime

Một điểm dễ nhầm là cùng một đối tượng có thể được gọi qua hai loại tham chiếu khác nhau:

```java
DataSource source = new MemoryDataSource();
MemoryDataSource memory = new MemoryDataSource();
```

Đây là hai khai báo minh họa với các kiểu đã định nghĩa ở đầu bài.

Khi gọi:

```java
source.read("item");
```

trình biên dịch xem `source` có **kiểu tĩnh là `DataSource`**, nên lời gọi có hợp đồng `throws IOException`, dù đối tượng thật là `MemoryDataSource`.

Trong khi đó:

```java
memory.read("item");
```

trình biên dịch thấy phương thức được khai báo bởi `MemoryDataSource` **không có checked `throws`**. Vì vậy caller cụ thể này không phải bắt/khai báo `IOException` do lời gọi đó.

Tương tự nếu lớp con chỉ khai báo `throws FileNotFoundException`:

- Gọi qua **kiểu interface hoặc cha** có `throws IOException`: caller cần xử lý hoặc khai báo `IOException`.
- Gọi trực tiếp qua **kiểu lớp con** có `throws FileNotFoundException`: caller cần xử lý hoặc khai báo `FileNotFoundException` (hoặc một kiểu cha phù hợp).
- Đối tượng được ném tại runtime vẫn có **lớp thực tế**, không bị Java chuyển thành kiểu khai báo rộng hơn.

### Ví dụ không biên dịch nếu chỉ dựa vào subtype runtime

```java
// Cố ý KHÔNG BIÊN DỊCH nếu DataSource.read khai báo throws IOException.
static void incorrect(DataSource source) {
    try {
        source.read("x");
    } catch (java.io.FileNotFoundException ex) {
        System.out.println("missing");
    }
}
```

Chỉ bắt `FileNotFoundException` không đủ để bao phủ các `IOException` khác mà interface cho phép. Sửa bằng `catch (IOException)` sau nhánh cụ thể hoặc khai báo `throws IOException` ở phương thức gọi.

**Điều phải nhớ:** Java bảo vệ hợp đồng theo **kiểu nhìn thấy ở thời điểm biên dịch**, chứ không cần chạy chương trình trước để biết implementation nào sẽ được gọi.

## 5. Ví dụ Java 17+ hoàn chỉnh: interface với override hẹp và override không checked exception

Lưu toàn bộ nội dung sau vào **`NarrowedThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class NarrowedThrowsDemo {

    interface DocumentSource {
        String load(String id) throws IOException;
    }

    static final class LocalSource implements DocumentSource {
        @Override
        public String load(String id) throws FileNotFoundException {
            if ("missing".equals(id)) {
                throw new FileNotFoundException("absent: " + id);
            }
            return "local:" + id;
        }
    }

    static final class MemorySource implements DocumentSource {
        @Override
        public String load(String id) {
            return "memory:" + id;
        }
    }

    static void viaInterface(DocumentSource source, String id) {
        try {
            System.out.println("interface value=" + source.load(id));
        } catch (IOException ex) {
            System.out.println(
                    "interface error=" + ex.getClass().getSimpleName());
        }
    }

    static void viaLocal(LocalSource source, String id) {
        try {
            System.out.println("local value=" + source.load(id));
        } catch (FileNotFoundException ex) {
            System.out.println("local error=" + ex.getMessage());
        }
    }

    static void viaMemory(MemorySource source, String id) {
        // Không có checked exception trong khai báo concrete này.
        System.out.println("memory value=" + source.load(id));
    }

    public static void main(String[] args) {
        LocalSource local = new LocalSource();
        MemorySource memory = new MemorySource();

        viaInterface(local, "missing");
        viaLocal(local, "missing");
        viaInterface(memory, "ok");
        viaMemory(memory, "ok");
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 NarrowedThrowsDemo.java
java NarrowedThrowsDemo
```

**Stdout chính xác:**

```text
interface error=FileNotFoundException
local error=absent: missing
interface value=memory:ok
memory value=memory:ok
```

### Phân tích kết quả

**`viaInterface(local, "missing")`:** biến `source` trong helper có kiểu tĩnh `DocumentSource`, nên handler `catch (IOException)` phù hợp. Thực thi động chọn `LocalSource.load`, ném đối tượng `FileNotFoundException`; handler lớp cha bắt được và `getClass().getSimpleName()` cho biết kiểu thực tế.

**`viaLocal(local, "missing")`:** helper nhận kiểu cụ thể `LocalSource`. Trình biên dịch biết `load` chỉ khai báo checked `FileNotFoundException`; handler `catch (FileNotFoundException)` là đủ. Message gốc được in mà không bị đổi kiểu.

**`viaInterface(memory, "ok")`:** caller vẫn dùng kiểu interface có `throws IOException` và phải xét checked exception theo hợp đồng, nhưng implementation `MemorySource.load` chạy thành công và không ném checked exception.

**`viaMemory(memory, "ok")`:** caller dùng kiểu concrete, phương thức không khai báo checked exception, nên lời gọi không cần `try-catch` hay `throws IOException`.

Ví dụ cố tình không đọc file thật, nhờ đó kết quả ổn định giữa các máy và tập trung đúng quy tắc override.

## 6. Khi nào bỏ `throws` là đúng, khi nào là cách che lỗi?

Bỏ `throws IOException` khỏi override là hợp lệ **nếu phần thân không để checked `IOException` thoát ra**. Ví dụ một implementation lưu hoàn toàn trong bộ nhớ không dùng I/O checked, nên bỏ `throws` là tự nhiên.

Ngược lại, nếu lớp con thực sự gọi một API có thể ném `IOException`:

```java
class RealFileSource implements DataSource {
    @Override
    public String read(String key) {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of(key));
    }
}
```

Đây là **ví dụ cố ý KHÔNG BIÊN DỊCH**: `Files.readString` có thể ném checked `IOException`, nhưng phương thức override không bắt lỗi và cũng không khai báo loại checked exception đó.

Có hai hướng sửa hợp lệ tùy thiết kế:

**Giữ khai báo checked exception phù hợp:**

```java
@Override
public String read(String key) throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of(key));
}
```

**Hoặc xử lý lỗi checked bên trong, không để nó đi ra:**

```java
@Override
public String read(String key) {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of(key));
    } catch (java.io.IOException cause) {
        throw new java.io.UncheckedIOException(
                "Cannot read required data", cause);
    }
}
```

Các đoạn trên là **phần phương thức minh họa** cho một lớp triển khai `DataSource`; không phải hai phương thức cùng chữ ký để đặt đồng thời trong một lớp.

Chú ý: lựa chọn thứ hai **không biến lỗi I/O thành thành công**. Nó chỉ chuyển một checked `IOException` thành unchecked `UncheckedIOException`, có giữ `cause`. Việc chuyển như vậy **có chủ đích** khi hợp đồng API chấp nhận unchecked failure; không nên chỉ bọc để tránh yêu cầu của compiler mà không xét trách nhiệm caller.

### Không thay bằng `catch (IOException ex) { return null; }` vô điều kiện

Một cách bỏ `throws` sai về nghiệp vụ:

```java
@Override
public String read(String key) {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of(key));
    } catch (java.io.IOException ex) {
        return null;
    }
}
```

Dù đoạn này **có thể biên dịch**, caller không biết `null` là nội dung hợp lệ, không tìm thấy file hay lỗi quyền truy cập. Lỗi I/O bị mất và chương trình có thể tiếp tục trong trạng thái sai.

**Bỏ khai báo checked exception phải phù hợp với hành vi và hợp đồng**, không đồng nghĩa nuốt ngoại lệ rồi coi như công việc thành công.

## 7. Override một phương thức của abstract class

Quy tắc áp dụng giống nhau nếu phương thức được khai báo trong **abstract class**:

```java
abstract class BaseReader {
    abstract String read()
            throws java.io.IOException;
}

final class ConstantReader extends BaseReader {
    @Override
    String read() {
        return "fixed";
    }
}

final class MissingReader extends BaseReader {
    @Override
    String read()
            throws java.io.FileNotFoundException {
        throw new java.io.FileNotFoundException("record absent");
    }
}
```

Đây là các khai báo minh họa hợp lệ trong tệp Java phù hợp. `BaseReader.read` cho phép `IOException`; lớp concrete có thể không ném checked exception hoặc khai báo subtype `FileNotFoundException`.

Không có ngoại lệ đặc biệt chỉ vì phương thức cha `abstract`. Nó vẫn công bố hợp đồng mà các lớp kế thừa phải tôn trọng.

### Một phương thức `final` thì không thể override

Nếu lớp cha đánh dấu phương thức `final`:

```java
class Base {
    public final void run() throws java.io.IOException {}
}
```

thì lớp con **không thể ghi đè** `run()` để đổi danh sách checked exception, bất kể định thu hẹp hay mở rộng. Bởi vì phương thức đã bị cấm override, các quy tắc cho override không còn tình huống để áp dụng.

## 8. Một phương thức có nhiều checked exception

Giả sử lớp cha khai báo hai nhánh lỗi:

```java
class Importer {
    public void importData()
            throws java.io.IOException, java.sql.SQLException {
        // ...
    }
}
```

Lớp con có thể:

- Giữ cả hai checked exception nếu thực sự cần.
- **Bỏ một nhánh** và giữ nhánh còn lại.
- Thu hẹp nhánh I/O từ `IOException` thành `FileNotFoundException`.
- Thu hẹp nhánh SQL từ `SQLException` thành `SQLTimeoutException` nếu phần thân chỉ phát sinh loại này.
- **Bỏ cả hai** nếu không để checked exception nào lan ra.

Ví dụ override hợp lệ:

```java
class SpecializedImporter extends Importer {
    @Override
    public void importData()
            throws java.io.FileNotFoundException,
                   java.sql.SQLTimeoutException {
        // ...
    }
}
```

Đây là ví dụ minh họa; hai loại được khai báo đều là subtype của hai nhánh checked mà lớp cha cho phép.

Override **không hợp lệ**:

```java
// Cố ý KHÔNG BIÊN DỊCH.
class WrongImporter extends Importer {
    @Override
    public void importData()
            throws java.text.ParseException {
        // ...
    }
}
```

`ParseException` là checked exception không được một trong hai nhánh của lớp cha bao phủ. Việc “có nhiều loại checked exception” trong cha không tạo quyền thêm bất kỳ loại checked exception mới nào.

### Có cần lặp lại subtype lẫn supertype?

Ví dụ `throws IOException, FileNotFoundException` là cú pháp có thể viết được nhưng `FileNotFoundException` đã được bao phủ bởi `IOException`, nên danh sách thường **dư thừa**. Tài liệu JavaDoc có thể mô tả chi tiết subtype phát sinh trong điều kiện nào mà không cần làm chữ ký dài hơn.

## 9. Một lớp triển khai nhiều interface cùng chữ ký

Đây là tình huống quan trọng để hiểu giới hạn **không mở rộng checked exception**.

Giả sử hai interface độc lập có cùng phương thức:

```java
interface FileSync {
    void sync() throws java.io.IOException;
}

interface DatabaseSync {
    void sync() throws java.sql.SQLException;
}
```

Một lớp triển khai cả hai:

```java
class HybridSync implements FileSync, DatabaseSync {
    @Override
    public void sync() {
        System.out.println("sync complete");
    }
}
```

**Hợp lệ.** Phương thức `sync()` của `HybridSync` không khai báo checked exception nào; vì vậy nó đáp ứng **đồng thời** hợp đồng của `FileSync` và `DatabaseSync`.

Nhưng thử khai báo:

```java
// Cố ý KHÔNG BIÊN DỊCH.
class InvalidHybridSync implements FileSync, DatabaseSync {
    @Override
    public void sync() throws java.io.IOException {
        // ...
    }
}
```

Không hợp lệ vì `DatabaseSync.sync()` **không cho phép checked `IOException`**. Tương tự, `throws SQLException` không phù hợp với `FileSync.sync()`.

Với hai loại checked exception không có quan hệ kế thừa như `IOException` và `SQLException`, implementation thỏa cả hai hợp đồng thường **không thể khai báo loại checked exception nào thuộc riêng một nhánh**. Nó phải xử lý checked exception trong thân hoặc lựa chọn thiết kế interface phù hợp.

### Quy tắc thực hành

Khi nhiều hợp đồng có phương thức cùng signature được một implementation thỏa đồng thời, checked exception của implementation phải nằm trong phần **giao nhau về những loại lỗi được phép**, chứ không phải phép **hợp** của danh sách `throws` từ tất cả interface.

Nếu các loại ở interface có quan hệ cha/con, implementation có thể khai báo loại phù hợp với **cả hai**. Nếu hai nhóm hoàn toàn độc lập và không có subtype checked chung thì khả năng bỏ hết checked `throws` có thể là cách hợp lệ duy nhất theo chữ ký.

## 10. Ví dụ Java 17+ hoàn chỉnh: thực hiện hai hợp đồng interface

Lưu tệp **`MultipleInterfaceThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultipleInterfaceThrowsDemo {

    interface FileSync {
        void sync() throws IOException;
    }

    interface DatabaseSync {
        void sync() throws SQLException;
    }

    static final class HybridSync
            implements FileSync, DatabaseSync {

        @Override
        public void sync() {
            System.out.println("hybrid: synced");
        }
    }

    static void viaFile(FileSync source) {
        try {
            source.sync();
            System.out.println("file: completed");
        } catch (IOException ex) {
            System.out.println("file: I/O error");
        }
    }

    static void viaDatabase(DatabaseSync source) {
        try {
            source.sync();
            System.out.println("database: completed");
        } catch (SQLException ex) {
            System.out.println("database: SQL error");
        }
    }

    static void viaHybrid(HybridSync source) {
        source.sync();
        System.out.println("hybrid: completed");
    }

    public static void main(String[] args) {
        HybridSync hybrid = new HybridSync();

        viaFile(hybrid);
        viaDatabase(hybrid);
        viaHybrid(hybrid);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MultipleInterfaceThrowsDemo.java
java MultipleInterfaceThrowsDemo
```

**Stdout chính xác:**

```text
hybrid: synced
file: completed
hybrid: synced
database: completed
hybrid: synced
hybrid: completed
```

### Vì sao code biên dịch?

- `HybridSync.sync()` không có checked `throws`, phù hợp với cả hai interface.
- `viaFile` nhận **kiểu tĩnh `FileSync`**, nên trình biên dịch yêu cầu xử lý hoặc khai báo `IOException`.
- `viaDatabase` nhận **kiểu tĩnh `DatabaseSync`**, nên phải xét `SQLException`.
- `viaHybrid` nhận **kiểu tĩnh `HybridSync`**, nên không cần bắt checked exception nào từ lời gọi `sync()`.
- Việc cả ba lời gọi cùng chạy đúng implementation là quyết định **dispatch ở runtime**; các nghĩa vụ checked exception vẫn được kiểm tra theo **khai báo kiểu ở điểm gọi**.

Ví dụ thể hiện rõ rằng **một implementation không cần sao chép `throws` của interface**, và caller có thể thấy hợp đồng khác nhau qua những kiểu tham chiếu khác nhau.

## 11. Nếu lớp cha không khai báo checked exception thì sao?

Nếu lớp cha đã có phương thức không khai báo checked exception:

```java
class BaseTask {
    public void run() {
        System.out.println("base task");
    }
}
```

Override hợp lệ:

```java
class FastTask extends BaseTask {
    @Override
    public void run() {
        System.out.println("fast task");
    }
}
```

Override không hợp lệ:

```java
// Cố ý KHÔNG BIÊN DỊCH.
class RiskyTask extends BaseTask {
    @Override
    public void run() throws java.io.IOException {
        throw new java.io.IOException("network unavailable");
    }
}
```

Lớp cha không công bố checked `IOException`, nên lớp con không thể tự mở rộng hợp đồng này. Nếu triển khai mới thực sự gọi API ném checked exception, phải tự bắt và xử lý hoặc chuyển sang unchecked exception có chủ đích; không thể đơn giản thêm `throws IOException` ở override.

Nếu muốn nhiều implementation có thể để lỗi I/O checked thoát ra, **hợp đồng cha/interface cần được thiết kế phù hợp từ đầu**. Thay đổi hợp đồng đã công khai có thể ảnh hưởng tới tất cả callers và implementers hiện hữu.

## 12. Checked exception từ thân phương thức vẫn phải được xử lý đúng

Quy tắc cho phép **bỏ** checked `throws` **không miễn** trách nhiệm kiểm tra exception trong thân override.

Ví dụ:

```java
@Override
public void save() {
    writeFile(); // writeFile() throws IOException
}
```

Đây là **ví dụ cố ý chưa hợp lệ**, giả định `writeFile()` ném checked `IOException` và `save` không được khai báo checked exception.

Muốn biên dịch:

- Thêm `throws IOException` nếu **hợp đồng cha cho phép**.
- Bắt `IOException` và thực sự phục hồi trong thân.
- Bọc thành một ngoại lệ unchecked phù hợp có `cause` nếu thiết kế API đòi hỏi.
- Thay đổi phân tách trách nhiệm hoặc thiết kế lại interface, nếu checked error thực sự thuộc hợp đồng không thể bỏ qua.

Không nên chỉ viết:

```java
catch (java.io.IOException ignored) {
}
```

Handler rỗng là một cách lách compiler nhưng thường che khuất thất bại. Đặc biệt với thao tác ghi dữ liệu, caller có thể nhận tín hiệu thành công sai.

## 13. Checked exception được kiểm tra theo chữ ký gọi, không theo nội dung `catch` bên trong

Một lớp con không khai báo checked exception có thể dùng `try-catch` trong thân:

```java
@Override
public void run() {
    try {
        externalOperation();
    } catch (java.io.IOException ex) {
        reportFailure(ex);
    }
}
```

Đây là mã minh họa; giả định `externalOperation` có thể ném checked `IOException`, `reportFailure` xử lý theo hợp đồng và không để checked error mới thoát ra.

Vì `IOException` đã được bắt và xử lý trong override, caller không bắt buộc phải bắt nó. Nhưng điều này chỉ đúng nếu handler **thực hiện hành động có nghĩa** hoặc diễn đạt lại thất bại theo kiểu kết quả hợp đồng, không tự động biến mọi lỗi thành thành công.

### Catch đã xử lý lỗi, Java không bắt bạn khai báo nó

`throws` là khai báo cho checked exception **có thể thoát khỏi phương thức**. Nếu mọi đường checked exception đều được xử lý thích hợp bên trong, danh sách `throws` có thể rỗng. Điều này giúp lớp con cung cấp triển khai ổn định hơn hợp đồng cha mà không gây thêm gánh nặng cho người gọi.

## 14. Unchecked exception: được phép nhưng vẫn cần hợp đồng

Giả sử phương thức cha:

```java
interface Processor {
    void process() throws java.io.IOException;
}
```

Một lớp triển khai có thể viết:

```java
class FailingProcessor implements Processor {
    @Override
    public void process() throws IllegalStateException {
        throw new IllegalStateException("processor not initialized");
    }
}
```

Đây là đoạn Java minh họa. `IllegalStateException` thuộc `RuntimeException` và là unchecked. Java cho phép khai báo dù interface không liệt kê nó.

Tuy nhiên, không nên kết luận “unchecked exception hoàn toàn không phải hợp đồng”. Ví dụ một thư viện có thể ghi rõ `IllegalArgumentException` cho tham số sai và `IllegalStateException` cho trạng thái không cho phép. Caller có thể quyết định xử lý những lỗi này, dù compiler không buộc.

**Đừng đổi checked thành unchecked chỉ để vượt qua lỗi biên dịch** nếu tầng gọi vẫn cần khôi phục hợp lý. Việc chọn loại lỗi là một quyết định thiết kế API.

## 15. Ghi đè, overload, constructor và method reference không phải một việc

### Override khác overload

Hai phương thức chỉ khác danh sách `throws` **không tạo thành overload**:

```java
// Cố ý KHÔNG BIÊN DỊCH nếu hai khai báo trong cùng một lớp.
void fetch() throws java.io.IOException {}
void fetch() throws java.io.FileNotFoundException {}
```

Java không dùng `throws` để phân biệt chữ ký overload. Override dựa trên tên/phần tham số và các quy tắc signature/subsignature của ngôn ngữ, không dựa vào việc danh sách `throws` có giống hệt hay không.

Một method overload mới với **danh sách tham số khác** có thể có hợp đồng checked exception riêng; quy tắc “không mở rộng `throws`” ở override không được áp dụng máy móc cho mọi overload.

### Constructor không được override

Một **constructor** không được kế thừa/override như phương thức thông thường. Constructor của lớp con có thể có danh sách `throws` riêng và phải tuân thủ checked exception phát sinh từ lời gọi `super(...)` cũng như phần khởi tạo của chính nó.

Vì vậy đừng áp đặt quy tắc override method một cách nguyên xi lên constructor của lớp con. Nếu constructor cha ném checked exception, constructor con phải xử lý/khai báo theo quy tắc khởi tạo đối tượng tương ứng.

### Method reference và lambda dùng hợp đồng của functional interface

Ví dụ:

```java
@FunctionalInterface
interface Loader {
    String load() throws java.io.IOException;
}
```

Một lambda triển khai `Loader` có thể không ném checked exception:

```java
Loader loader = () -> "cached";
```

Đây là các khai báo minh họa. Nhưng caller qua biến `Loader` vẫn có nghĩa vụ checked `IOException` khi gọi `loader.load()` theo khai báo của interface.

Ngược lại, lambda không thể tự ý ném một checked exception không tương thích với `throws` của functional method. Quy tắc phù hợp với hợp đồng của kiểu mục tiêu, dù lambda không có dòng khai báo `throws` riêng.

## 16. Vì sao nên đánh dấu `@Override`?

`@Override` giúp trình biên dịch xác nhận rằng phương thức thực sự ghi đè một khai báo hợp lệ. Điều này đặc biệt hữu ích nếu người viết đổi tên hoặc sai tham số:

```java
class Parent {
    void load(String path) throws java.io.IOException {}
}

class Child extends Parent {
    @Override
    void load() {
        // Sai: không override load(String).
    }
}
```

Đây là **mã cố ý không biên dịch**, bởi `load()` khác chữ ký của `load(String)`.

Nếu bỏ `@Override`, `Child.load()` có thể trở thành một overload độc lập, khiến người viết tưởng đã bỏ `throws IOException` của phương thức cha trong khi thực ra **chưa override phương thức cần sửa**.

Vì thế khi thu hẹp hoặc bỏ checked `throws`, dùng `@Override` là thói quen quan trọng để chắc chắn bạn đang sửa đúng hợp đồng kế thừa.

### Quyền truy cập cũng phải tương thích

Một override không được làm quyền truy cập hẹp hơn so với phương thức mà nó ghi đè. Chẳng hạn một phương thức `public` từ interface phải được triển khai bằng phương thức `public`. Đây là ràng buộc **khác** với checked exception nhưng thường xuất hiện đồng thời khi viết code override.

## 17. Lỗi thường gặp trong thiết kế hợp đồng checked exception

| Sai lầm | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Lớp con khai báo `throws Exception` khi cha chỉ cho `IOException` | Mở rộng checked exception | Giữ `IOException` hoặc subtype phù hợp |
| Lớp con khai báo `throws SQLException` khi cha chỉ cho `IOException` | Thêm checked exception khác nhánh | Bắt/đổi lỗi trong implementation hoặc thiết kế lại hợp đồng |
| Nghĩ lớp con bắt buộc giữ `throws IOException` từ interface | Override có thể thu hẹp hoặc bỏ checked `throws` | Chỉ khai báo những checked exception còn được để thoát ra |
| Bỏ `throws` nhưng vẫn gọi `Files.readString` không bắt lỗi | Checked `IOException` chưa được xử lý | Bắt, khai báo trong phạm vi cha cho phép hoặc chuyển lỗi có chủ đích |
| Bắt lỗi rồi trả `null` không có hợp đồng | Che thất bại, dễ gây lỗi ở tầng gọi | Phục hồi có nghĩa hoặc báo lỗi tường minh |
| Nghĩ gọi object qua interface đã biết implementation không ném thì bỏ `catch` được | Compile-time kiểm tra kiểu interface | Xử lý theo `throws` của kiểu tĩnh |
| Nghĩ unchecked exception cũng bị cấm tuyệt đối khi override | Ràng buộc chính áp dụng cho checked exception | Hiểu `RuntimeException` và `Error` |
| Nghĩ nhiều interface được phép hợp tất cả danh sách `throws` | Implementation phải thỏa đồng thời mọi hợp đồng | Dùng tập checked exception phù hợp với tất cả |
| Nghĩ constructor chịu cùng quy tắc override | Constructor không được override | Kiểm tra quy tắc khởi tạo và `super(...)` |
| Nghĩ thay `throws` tạo overload khác | `throws` không nằm trong tiêu chí phân biệt overload | Phân biệt tên và danh sách tham số |
| Không viết `@Override` rồi vô tình overload | Có thể không ghi đè phương thức dự kiến | Thêm `@Override` để compiler kiểm tra |
| Đổi checked exception thành unchecked tùy tiện | Có thể làm caller khó phục hồi hợp lý | Thiết kế hợp đồng và cause rõ ràng |
| Chỉ dựa vào runtime type mà bỏ trách nhiệm checked exception | Compiler xét kiểu tĩnh | Đọc chữ ký của phương thức được gọi |

## 18. Checklist khi override một phương thức có `throws`

Trước khi sửa chữ ký trong lớp con:

1. **Xác định phương thức được ghi đè** và thêm `@Override`.
2. **Đọc `throws` ở lớp cha/interface**: những loại checked exception nào được cho phép?
3. **Xác định lỗi thực tế của implementation**: I/O, SQL, parse hay không có lỗi checked nào?
4. **Nếu giữ checked `throws`**, xác nhận từng loại là cùng kiểu hoặc subtype được hợp đồng cha bao phủ.
5. **Nếu bỏ `throws`**, bảo đảm mọi checked exception phát sinh trong thân đã được xử lý có nghĩa hoặc không còn có thể thoát ra.
6. **Nếu dùng nhiều interface**, kiểm tra implementation thỏa đồng thời mọi khai báo cùng signature.
7. **Đọc kiểu tĩnh của caller**: qua interface/cha hay kiểu concrete? Nghĩa vụ bắt/khai báo có thể khác nhau.
8. **Xét unchecked exception** có thể xảy ra: quy tắc compiler khác nhưng trách nhiệm tài liệu hóa API vẫn còn.
9. **Đừng nuốt lỗi để được biên dịch**: fallback phải có hợp đồng, không trả thành công giả.
10. **Nếu bọc lỗi checked sang unchecked**, cân nhắc giữ `cause` và chọn subtype thích hợp với tầng nghiệp vụ.
11. **Kiểm tra access và chữ ký**: không giảm phạm vi truy cập, không vô tình overload.
12. **Dùng test/compile thực tế**: thử lời gọi qua cả kiểu cha và kiểu con, kể cả trường hợp có lỗi.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Cha khai báo `void work() throws IOException`. Con khai báo `void work() throws FileNotFoundException` có hợp lệ không?

**Có.** `FileNotFoundException` là subtype của `IOException`.

**Câu 2.** Con bỏ hoàn toàn `throws` có được không?

**Có**, nếu thân override không để checked exception chưa được xử lý thoát ra.

**Câu 3.** Cha khai báo `throws IOException`; con khai báo `throws Exception` có hợp lệ không?

**Không.** `Exception` rộng hơn `IOException` và có thể cho phép checked exception mới.

**Câu 4.** Cha khai báo `throws IOException`; con khai báo `throws SQLException` có hợp lệ không?

**Không.** Hai loại checked exception ở hai nhánh độc lập.

**Câu 5.** Cha không khai báo checked exception; con khai báo `throws IllegalStateException` được không?

**Được**, vì `IllegalStateException` là unchecked. Nhưng thiết kế hành vi vẫn phải hợp lý.

**Câu 6.** Interface khai báo `load() throws IOException`. Lớp concrete override không có `throws`. Caller giữ biến kiểu interface có được bỏ hoàn toàn việc bắt/khai báo `IOException` khi gọi `load()` không?

**Không.** Compiler nhìn hợp đồng của kiểu interface ở điểm gọi.

**Câu 7.** Lớp concrete không khai báo checked exception; caller chỉ gọi qua kiểu concrete. Compiler có buộc bắt `IOException` không?

**Không**, nếu đó là lời gọi duy nhất và không có nguồn checked `IOException` khác trong biểu thức/phạm vi cần xét.

**Câu 8.** Hai interface có cùng `sync()`, một bên `throws IOException`, bên kia `throws SQLException`. Implementation không khai báo checked exception có hợp lệ không?

**Có.** Nó thỏa cả hai hợp đồng.

**Câu 9.** Nếu phương thức con muốn ném checked `ParseException` nhưng cha chỉ cho `IOException`, nên làm gì?

**Không** thể thêm trực tiếp `throws ParseException` vào override. Cần xử lý trong thân, chuyển sang kiểu được hợp đồng cho phép khi có ý nghĩa, hoặc thiết kế lại API ở một ranh giới có thẩm quyền.

**Câu 10.** Thêm `throws RuntimeException` có làm caller bắt buộc `catch RuntimeException` không?

**Không.** `RuntimeException` là unchecked, dù có được ghi tường minh trong `throws`.

**Câu 11.** Hai phương thức cùng tên và cùng tham số, một `throws IOException` và một `throws FileNotFoundException`, có tạo overload hợp lệ không?

**Không.** Chỉ khác `throws` không tạo hai chữ ký overload khác nhau.

**Câu 12.** Constructor lớp con có “override constructor cha” và phải khai báo checked exception hẹp hơn không?

**Không.** Constructor không được override; kiểm tra lỗi của constructor con theo luật khởi tạo và `super(...)`.

## 20. Hướng dẫn thiết kế API để không phải “lách” checked exception

### Chọn mức trừu tượng của loại lỗi

Một interface có nhiều implementation — file, network, memory — có thể chọn `throws IOException` nếu tất cả thao tác đều được mô hình hóa nhất quán thành I/O. Nhưng nếu chỉ có một implementation truy cập database còn interface không phải hợp đồng lưu trữ chung, thêm `throws SQLException` ở lớp cụ thể không tự tương thích với interface cũ.

Ở bước thiết kế, hãy hỏi:

- Caller có thực sự có khả năng **phục hồi** lỗi checked này không?
- Hợp đồng của kiểu cha có dự kiến **nhiều implementation** không?
- Có cần một exception trừu tượng theo domain để tách caller khỏi chi tiết file/SQL không?
- Một lỗi có phải failure có thể đoán trước theo nghiệp vụ hay là bug/precondition không?
- Có phù hợp khi dùng dạng kết quả như `Optional`, `Result` hoặc status rõ ràng thay vì checked exception cho một kết quả “không tìm thấy” bình thường không?

Trả lời những câu này giúp giảm việc phải bắt rồi nuốt hoặc bọc lỗi chỉ vì khác biệt chữ ký.

### Thay đổi hợp đồng công khai cần đánh giá tương thích

Thu hẹp `throws` ở một override cụ thể thường không tạo nghĩa vụ checked mới cho caller, nhưng **đổi `throws` của interface hoặc phương thức cha** có thể ảnh hưởng các implementation khác. Nếu bỏ `throws IOException` ở interface, những lớp triển khai còn khai báo `throws IOException` sẽ có nguy cơ không biên dịch sau thay đổi đó.

Vì vậy phải phân biệt:

- **Thu hẹp ở override của lớp con:** thường là lựa chọn hợp lệ trong giới hạn của hợp đồng cha hiện có.
- **Thay đổi hợp đồng ở lớp cha/interface:** là thay đổi API rộng hơn, cần xem xét toàn bộ implementers/callers và tương thích của thư viện.

Đừng áp dụng quy tắc thu hẹp ở một phương thức lớp con để kết luận việc xóa checked `throws` ở interface luôn an toàn cho toàn hệ thống.

## Kết luận

Khi ghi đè một phương thức trong Java, lớp con có thể **giữ nguyên**, **thu hẹp** hoặc **bỏ hoàn toàn** những checked exception mà lớp cha/interface cho phép, nhưng **không được mở rộng sang một loại checked exception mới hoặc rộng hơn**. Quy tắc này bảo vệ người gọi sử dụng kiểu cha: implementation mới không được tạo thêm nghĩa vụ checked exception mà hợp đồng gốc chưa công bố.

Hãy luôn phân biệt **hợp đồng kiểu tĩnh ở caller**, **kiểu runtime của ngoại lệ**, và **ngoại lệ thực sự thoát khỏi thân override**. Việc giảm danh sách `throws` phải phản ánh hành vi xử lý thật, chứ không phải nuốt lỗi hoặc bọc thành unchecked exception một cách tùy tiện. Với nhiều interface cùng chữ ký, implementation phải thỏa **đồng thời** mọi ràng buộc checked exception, còn constructor, overload và các ngoại lệ unchecked có những quy tắc riêng cần xem đúng ngữ cảnh.