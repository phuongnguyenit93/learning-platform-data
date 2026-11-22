# Một phương thức đáp ứng nhiều interface có cùng chữ ký

Trong Java, một lớp có thể `implements` nhiều interface cùng yêu cầu một phương thức. Khi các khai báo có chữ ký phù hợp, **chỉ một phương thức instance trong lớp (hoặc kế thừa từ lớp cha) có thể đáp ứng tất cả các hợp đồng ấy**. Không cần, và cũng không thể, viết hai thân hàm chỉ khác nhau ở interface “sở hữu” phương thức.

Điều kiện không dừng ở tên và tham số: phương thức chung còn phải tương thích với mọi kiểu trả về, checked exception, mức truy cập và ý nghĩa hành vi do từng interface yêu cầu.

## 1. Ví dụ cơ bản: hai interface, một phương thức

Tạo tệp `SharedMethodDemo.java` (Java 17+):

```java
interface Describable {
    String code();
}

interface Trackable {
    String code();
}

final class Asset implements Describable, Trackable {
    private final String code;

    Asset(String code) {
        this.code = code;
    }

    @Override
    public String code() {
        return code;
    }
}

public class SharedMethodDemo {
    public static void main(String[] args) {
        Asset asset = new Asset("asset-42");
        Describable described = asset;
        Trackable tracked = asset;

        System.out.println("Describable: " + described.code());
        System.out.println("Trackable: " + tracked.code());
        System.out.println("Direct: " + asset.code());
    }
}
```

Biên dịch và chạy:

```bash
javac SharedMethodDemo.java
java SharedMethodDemo
```

```text
Describable: asset-42
Trackable: asset-42
Direct: asset-42
```

`Describable.code()` và `Trackable.code()` đều khai báo `String code()`. Phương thức `public String code()` duy nhất của `Asset` thỏa mãn cả hai. Hai biến kiểu interface tham chiếu cùng đối tượng `Asset`, vì vậy lời gọi qua mỗi biến cùng đi tới phần thân triển khai ấy. Annotation `@Override` dùng một lần để trình biên dịch kiểm tra hợp đồng.

Kiểu tham chiếu interface xác định những phương thức nào được phép gọi khi biên dịch; lớp của đối tượng tại thời điểm chạy xác định implementation được gọi. Không có hai “bản sao” độc lập của `code()` chỉ vì có hai interface.

## 2. Cùng chữ ký khác với cùng kiểu trả về

Đối với phương thức thông thường, chữ ký (`method signature`) dựa trên **tên phương thức và danh sách kiểu tham số**, cùng những quy tắc bổ sung cho phương thức generic. Tên của biến tham số không ảnh hưởng chữ ký. Kiểu trả về và mệnh đề `throws` không tạo ra overload mới.

| Khai báo ở hai interface | Kết luận |
| --- | --- |
| `void save(String id)` và `void save(String key)` | Cùng chữ ký; một `public void save(String)` có thể đáp ứng cả hai. |
| `String find(int id)` và `String find(int id)` | Một phương thức phù hợp có thể triển khai cả hai. |
| `Number value()` và `Integer value()` | Có thể dùng `Integer value()` nhờ kiểu trả về covariant. |
| `void send(String s)` và `void send(int n)` | Khác chữ ký; cần hai overload nếu lớp triển khai cả hai. |
| `String value()` và `Integer value()` | Không có kiểu trả về tương thích cho cả hai khai báo này. |
| `int count()` và `long count()` | Không thể dùng một override để thỏa cả hai kiểu trả về nguyên thủy. |

**Kiểu trả về covariant** cho phép phương thức override trả về subtype tham chiếu của kiểu được khai báo trong hợp đồng. Ví dụ chạy được trong `CovariantReturnDemo.java`:

```java
interface NumericValue {
    Number value();
}

interface IntegralValue {
    Integer value();
}

final class NumberItem implements NumericValue, IntegralValue {
    @Override
    public Integer value() {
        return 42;
    }
}

public class CovariantReturnDemo {
    public static void main(String[] args) {
        NumberItem item = new NumberItem();
        NumericValue n = item;
        IntegralValue i = item;
        System.out.println(n.value());
        System.out.println(i.value());
    }
}
```

```bash
javac CovariantReturnDemo.java
java CovariantReturnDemo
```

```text
42
42
```

Vì `Integer` là subtype của `Number`, `Integer value()` tương thích với cả hai. Ngược lại, không thể viết hai phương thức `String value()` và `Integer value()` trong cùng lớp chỉ để phân biệt interface: Java không overload theo kiểu trả về.

## 3. Mức truy cập và checked exception cũng phải tương thích

Phương thức abstract thông thường trong interface có mức truy cập `public` mặc định. Phương thức triển khai phải là phương thức instance `public` thích hợp; bỏ `public` để thành package-private, dùng `protected` hay chuyển thành `static` không đáp ứng được hợp đồng instance đó.

Với checked exception, phương thức triển khai phải có khai báo `throws` hợp lệ **đối với từng interface**. Nếu một interface cho phép `IOException` nhưng interface kia chỉ cho phép `SQLException`, phương thức chung có thể không khai báo checked exception nào.

Ví dụ `CompatibleThrowsDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

interface FileAction {
    void run() throws IOException;
}

interface DatabaseAction {
    void run() throws SQLException;
}

final class UnifiedAction implements FileAction, DatabaseAction {
    @Override
    public void run() {
        System.out.println("finished");
    }
}

public class CompatibleThrowsDemo {
    public static void main(String[] args) {
        new UnifiedAction().run();
    }
}
```

```bash
javac CompatibleThrowsDemo.java
java CompatibleThrowsDemo
```

```text
finished
```

`UnifiedAction.run()` không khai báo checked exception nên không vi phạm bên nào. Nếu phương thức ấy khai báo `throws IOException`, nó không còn phù hợp với `DatabaseAction.run()`, vì `IOException` không phải subtype của `SQLException`. Các ngoại lệ unchecked như `RuntimeException` có quy tắc khác.

Một chi tiết quan trọng: nếu gọi `run()` qua biến có kiểu tĩnh `FileAction` hoặc `DatabaseAction`, trình biên dịch vẫn kiểm tra `throws` trong khai báo của **kiểu biến đó**, dù implementation `UnifiedAction` cụ thể không khai báo checked exception.

## 4. Trùng default method: buộc chọn hoặc kết hợp cách triển khai

Hai khai báo `abstract` cùng chữ ký có thể cùng được đáp ứng bằng một phương thức. Tuy nhiên, khi **hai interface độc lập cùng cung cấp `default` method cùng chữ ký**, Java không tự chọn một trong hai thân hàm.

Ví dụ `DefaultConflictDemo.java`:

```java
interface LeftTitle {
    default String title() {
        return "Left";
    }
}

interface RightTitle {
    default String title() {
        return "Right";
    }
}

final class CombinedTitle implements LeftTitle, RightTitle {
    @Override
    public String title() {
        return LeftTitle.super.title() + " & " + RightTitle.super.title();
    }
}

public class DefaultConflictDemo {
    public static void main(String[] args) {
        System.out.println(new CombinedTitle().title());
    }
}
```

```bash
javac DefaultConflictDemo.java
java DefaultConflictDemo
```

```text
Left & Right
```

Bỏ phương thức override ở `CombinedTitle` sẽ gây lỗi biên dịch về default method xung đột. Cú pháp `LeftTitle.super.title()` và `RightTitle.super.title()` gọi tường minh hai default implementation từ các direct superinterface. Đây là một lựa chọn; lớp cũng có thể tự viết hoàn toàn logic `title()` mới.

Một trường hợp khác là **phương thức concrete kế thừa từ lớp cha**. Phương thức `public` tương thích của lớp cha có thể triển khai interface và thường được ưu tiên trước default method (`class wins`):

```java
class ParentTitle {
    public String title() {
        return "class";
    }
}

interface Titled {
    default String title() {
        return "interface";
    }
}

final class ChildTitle extends ParentTitle implements Titled {
}

public class ClassMethodPriorityDemo {
    public static void main(String[] args) {
        System.out.println(new ChildTitle().title());
    }
}
```

Lưu trong `ClassMethodPriorityDemo.java`, rồi chạy:

```bash
javac ClassMethodPriorityDemo.java
java ClassMethodPriorityDemo
```

```text
class
```

`ChildTitle` không cần khai báo `title()` vì phương thức phù hợp của `ParentTitle` được kế thừa và đáp ứng hợp đồng `Titled`.

## 5. Phân biệt với overload và generic

Hai interface sau **không** có cùng chữ ký:

```java
interface TextSink {
    void send(String value);
}

interface NumberSink {
    void send(int value);
}

final class MixedSink implements TextSink, NumberSink {
    @Override
    public void send(String value) {
        System.out.println("text=" + value);
    }

    @Override
    public void send(int value) {
        System.out.println("number=" + value);
    }
}
```

Đây là đoạn mã minh họa lớp và interface, không có phương thức `main` độc lập. `MixedSink` phải có hai overload vì tham số lần lượt là `String` và `int`. Java chọn overload phù hợp với lời gọi lúc biên dịch.

Với generic, cần phân tích phương thức sau khi thay tham số kiểu và xét quy tắc `erasure`/`override-equivalent`. Chẳng hạn `interface Handler<T> { void handle(T v); }` được triển khai dưới dạng `Handler<String>` có yêu cầu `handle(String)`. Ngược lại, `List<String>` và `List<Integer>` cùng bị xóa về `List`; việc hai khai báo có cùng erasure có thể gây name clash hoặc đòi dùng kiểu thô với cảnh báo mất an toàn kiểu. Vì vậy không suy luận khả năng “một phương thức đáp ứng cả hai” chỉ bằng cách nhìn tên sau erasure.

Các phương thức `static` và `private` của interface không phải các phương thức instance abstract mà lớp `implements` phải ghi đè. Đừng nhầm tên trùng với việc đã triển khai hợp đồng.

## 6. Trùng chữ ký chưa bảo đảm đúng ý nghĩa hợp đồng

Giả sử `Auditable` yêu cầu `save(String id)` phải ghi sự kiện audit, còn `Persistable` yêu cầu chính chữ ký ấy phải lưu dữ liệu bền vững. Java có thể chấp nhận một phương thức `save(String)` về mặt kiểu, nhưng phần thân chỉ thực hiện audit sẽ **không** đáp ứng hành vi mà `Persistable` hứa hẹn.

Khi hợp nhất triển khai, cần làm rõ điều kiện đầu vào, tác dụng phụ, ngoại lệ và hậu điều kiện của *mọi* interface. Nếu các yêu cầu hành vi mâu thuẫn, nên xem lại thiết kế interface hoặc phân tách trách nhiệm; trình biên dịch không thể tự giải quyết mâu thuẫn ngữ nghĩa này.

## 7. Quy trình kiểm tra và lỗi phổ biến

1. Đặt khai báo của các interface cạnh nhau, so tên và kiểu tham số, kể cả generic sau khi thay kiểu.
2. Xác minh một kiểu trả về đáp ứng được tất cả; không cố phân biệt phương thức bằng return type.
3. Xác minh `public`, instance method và checked `throws` tương thích với mọi interface.
4. Xác định các khai báo là abstract hay default; nếu có hai default implementation xung đột, viết override rõ ràng.
5. Kiểm tra lớp cha đã có concrete method phù hợp hay chưa.
6. Gọi phương thức qua từng kiểu interface và viết test cho hành vi đã được mỗi hợp đồng hứa hẹn.

Lỗi hay gặp là viết phương thức package-private, khai báo một checked exception chỉ được một interface cho phép, quên override khi hai default method xung đột, hoặc cho rằng hai phương thức khác kiểu trả về là hai overload.

**Bài tập:** Tạo `EventPublisher` và `AuditPublisher` cùng khai báo `void publish(String message)`. Cho `ConsolePublisher` implements cả hai bằng một `public` method. Gọi qua hai biến interface, giải thích vì sao cùng một phần thân được thực thi. Sau đó thêm `default String channel()` vào cả hai interface với hai giá trị khác nhau; tự sửa xung đột bằng một override và chạy `javac` để kiểm chứng.

**Ghi nhớ:** Một implementation có thể thực hiện nhiều hợp đồng interface cùng chữ ký; kiểu trả về, checked exception và hành vi phải cùng thỏa mãn các hợp đồng. Hai default method xung đột phải được giải quyết tường minh, còn phương thức `public` phù hợp kế thừa từ lớp cha có thể đã đủ để đáp ứng interface.
