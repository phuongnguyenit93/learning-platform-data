# Cách xác định phương thức abstract được kế thừa từ các interface cha

Trong Java, một interface có thể `extends` nhiều interface. Khi đó interface con kế thừa các phương thức thành viên từ toàn bộ hệ interface cha, kể cả những phương thức được khai báo ở các interface tổ tiên xa hơn. Để biết một lớp cụ thể phải cài đặt những phương thức nào, cần xét chữ ký phương thức, quan hệ kế thừa, kiểu trả về và các phương thức `default` đã có phần thân. Không thể chỉ đếm số dòng khai báo có từ khóa `abstract`.

## 1. Phương thức nào trong interface là abstract?

Một phương thức instance được khai báo trong interface mà không có thân thường là phương thức `public abstract` ngầm định. Vì vậy, hai khai báo sau tương đương về ý nghĩa:

```java
interface Reader {
    String read();
}
```

và

```java
interface Reader {
    public abstract String read();
}
```

Các loại phương thức cần phân biệt:

- **Phương thức abstract:** không có thân; lớp cụ thể phải cung cấp một triển khai phù hợp, trừ khi đã có triển khai hợp lệ được kế thừa từ lớp cha hoặc phương thức `default` thích hợp.
- **Phương thức default:** có thân và được kế thừa như một triển khai instance. Lớp có thể dùng luôn hoặc ghi đè.
- **Phương thức static:** thuộc về chính interface khai báo; không được kế thừa như phương thức instance và không tạo nghĩa vụ triển khai cho lớp.
- **Phương thức private:** chỉ phục vụ bên trong interface khai báo, không phải phương thức được interface con kế thừa.

Trong interface, phương thức instance không có thân và không được khai báo `private` hoặc `default` là abstract theo quy tắc của Java, kể cả khi không viết từ khóa `abstract`.

## 2. Xác định nghĩa vụ qua toàn bộ cây interface

Hãy đọc từ interface đang xét rồi lần theo tất cả interface cha trực tiếp và gián tiếp. Ví dụ:

```java
interface HasId {
    String id();
}

interface HasName {
    String name();
}

interface Person extends HasId, HasName {
}
```

`Person` không khai báo phương thức nào trực tiếp, nhưng vẫn kế thừa hai phương thức abstract:

- `String id()` từ `HasId`.
- `String name()` từ `HasName`.

Một lớp cụ thể triển khai `Person` phải đáp ứng cả hai nghĩa vụ. Chương trình độc lập sau chạy được trên Java 17 trở lên:

```java
interface HasId {
    String id();
}

interface HasName {
    String name();
}

interface Person extends HasId, HasName {
}

final class User implements Person {
    @Override
    public String id() {
        return "u-1";
    }

    @Override
    public String name() {
        return "An";
    }
}

public class Main {
    public static void main(String[] args) {
        Person person = new User();
        System.out.println("id=" + person.id());
        System.out.println("name=" + person.name());
    }
}
```

Lưu mã vào `Main.java`, rồi chạy:

```text
javac Main.java
java Main
```

Kết quả chuẩn:

```text
id=u-1
name=An
```

Tên file phải là `Main.java` vì lớp `public` là `Main`. Nếu `User` thiếu một trong hai phương thức, trình biên dịch báo lỗi vì lớp cụ thể chưa thực hiện đầy đủ hợp đồng của `Person`.

## 3. Gom các khai báo có cùng chữ ký

Nhiều interface cha có thể khai báo cùng một phương thức. Nếu các khai báo tương thích và cùng biểu diễn một chữ ký phương thức, lớp chỉ cần một triển khai đáp ứng chúng; không cần tạo một phương thức riêng cho từng interface.

```java
interface A {
    void reset();
}

interface B {
    void reset();
}

interface C extends A, B {
}

final class Device implements C {
    @Override
    public void reset() {
        System.out.println("reset");
    }
}
```

`C` kế thừa hai khai báo `reset()`, nhưng một phương thức `public void reset()` của `Device` đáp ứng cả hai.

Khi so sánh phương thức, hãy chú ý:

- Tên và danh sách kiểu tham số quyết định chữ ký; kiểu trả về không tạo một overload mới.
- Hai phương thức `m(int)` và `m(String)` là hai chữ ký khác nhau, nên có thể tạo hai nghĩa vụ riêng.
- Hai phương thức cùng tên và cùng kiểu tham số nhưng có kiểu trả về không tương thích không thể được xử lý bằng hai phương thức chỉ khác kiểu trả về. Java không cho phép overload chỉ bằng kiểu trả về.
- Điều khoản `throws` không tạo ra một chữ ký khác. Khi ghi đè, kiểu ngoại lệ checked được khai báo phải tuân thủ quy tắc của phương thức bị ghi đè, thường là giữ nguyên hoặc thu hẹp phạm vi ngoại lệ được phép.
- Với generic, phải xét kiểu đã được thay thế theo ngữ cảnh kế thừa, không chỉ so sánh nguyên văn tên kiểu trong khai báo.

### Kiểu trả về covariant

Các khai báo cùng chữ ký có thể có kiểu trả về khác nhau nếu kiểu trả về được chọn tương thích theo quy tắc Java. Ví dụ, `Integer` là kiểu con của `Number`:

```java
interface A {
    Number value();
}

interface B {
    Integer value();
}

interface C extends A, B {
}

final class NumberValue implements C {
    @Override
    public Integer value() {
        return 7;
    }
}

public class Main {
    public static void main(String[] args) {
        C value = new NumberValue();
        System.out.println(value.value());
    }
}
```

Kết quả:

```text
7
```

`Integer value()` có thể đáp ứng cả hai khai báo. Ngược lại, nếu một interface cha yêu cầu `String value()` và interface khác yêu cầu `Integer value()` với cùng tham số, hai kiểu trả về không tương thích; interface con không thể hợp nhất chúng thành một hợp đồng hợp lệ. Đây là lỗi biên dịch, không phải tình huống có thể khắc phục bằng cách viết hai phương thức cùng tên và cùng danh sách tham số.

## 4. Generic và phương thức được kế thừa

Khi interface cha có tham số kiểu, hãy thay tham số kiểu theo cách interface con mở rộng nó:

```java
interface Box<T> {
    T get();
}

interface TextBox extends Box<String> {
}

final class MessageBox implements TextBox {
    @Override
    public String get() {
        return "hello";
    }
}
```

Trong `TextBox`, hợp đồng `T get()` được áp dụng với `T = String`. Vì vậy, triển khai phù hợp trong `MessageBox` là `String get()`.

Với hệ interface generic phức tạp, cần xét cả việc thay tham số kiểu và quy tắc xóa kiểu (type erasure). Các khai báo có thể gây xung đột sau khi xóa kiểu hoặc không có kiểu trả về tương thích sẽ bị trình biên dịch từ chối. Không nên kết luận rằng hai phương thức khác nhau chỉ vì chúng dùng tên tham số kiểu khác nhau trong mã nguồn.

## 5. Phân biệt abstract với default

Phương thức `default` có phần thân nên có thể cung cấp triển khai cho lớp. Nếu một interface con kế thừa một default method từ interface cha cụ thể hơn, triển khai đó thường được ưu tiên hơn một khai báo cùng chữ ký từ interface tổ tiên của nó.

```java
interface A {
    default String label() {
        return "A";
    }
}

interface B extends A {
    @Override
    default String label() {
        return "B";
    }
}

interface C extends B {
}

final class Item implements C {
}

public class Main {
    public static void main(String[] args) {
        System.out.println(new Item().label());
    }
}
```

Kết quả là:

```text
B
```

`Item` không phải tự triển khai `label()` vì có một default method phù hợp được kế thừa qua `B`.

Có hai tình huống quan trọng khác:

1. **Hai default method xung đột:** nếu hai interface cha không có quan hệ cha-con cùng cung cấp default method có chữ ký tương đương, Java không tự chọn một bên. Interface con hoặc lớp triển khai phải ghi đè để giải quyết xung đột. Ví dụ:

   ```java
   interface Left {
       default String name() {
           return "left";
       }
   }

   interface Right {
       default String name() {
           return "right";
       }
   }

   final class Both implements Left, Right {
       @Override
       public String name() {
           return Left.super.name();
       }
   }
   ```

   Ở đây `Both` chọn rõ ràng triển khai của `Left` bằng `Left.super.name()`. Lớp có thể viết phần thân riêng thay vì gọi một default method.

2. **Interface con khai báo lại một default method thành abstract:** interface con có thể cố ý bỏ phần triển khai mặc định đối với hợp đồng đó. Khi ấy lớp cụ thể triển khai interface con phải cung cấp phương thức tương ứng:

   ```java
   interface Base {
       default void run() {
           System.out.println("base");
       }
   }

   interface RequiresRun extends Base {
       @Override
       void run();
   }

   final class Job implements RequiresRun {
       @Override
       public void run() {
           System.out.println("job");
       }
   }
   ```

   `RequiresRun` tái khai báo `run()` mà không có thân, nên lớp `Job` phải triển khai phương thức đó.

Khi abstract method và default method cùng xuất hiện từ các nhánh kế thừa khác nhau, hãy xét quy tắc ghi đè và tính cụ thể của khai báo. Đặc biệt, không suy ra kết quả chỉ từ việc nhìn thấy một phương thức có thân: phải xác định phương thức nào thực sự được kế thừa sau khi áp dụng các quy tắc của Java. Nếu các khai báo xung đột hoặc không tương thích, trình biên dịch sẽ báo lỗi và cần sửa quan hệ khai báo hoặc ghi đè rõ ràng.

## 6. Khi nào lớp đã có triển khai mà không cần viết lại?

Nghĩa vụ abstract có thể được đáp ứng bởi một phương thức instance công khai phù hợp được kế thừa từ lớp cha. Vì thế, không phải lúc nào cũng cần thấy phương thức được viết trực tiếp trong lớp đang xét.

```java
interface Identifiable {
    String id();
}

class BaseRecord {
    public String id() {
        return "base-1";
    }
}

final class Record extends BaseRecord implements Identifiable {
}

public class Main {
    public static void main(String[] args) {
        Identifiable record = new Record();
        System.out.println(record.id());
    }
}
```

Kết quả:

```text
base-1
```

Phương thức `public String id()` được kế thừa từ `BaseRecord` đáp ứng hợp đồng `Identifiable`. Phương thức của lớp cha phải có khả năng truy cập và tương thích với hợp đồng interface; một phương thức `protected` không đáp ứng yêu cầu `public` của phương thức interface.

Quy tắc ưu tiên phương thức của lớp cũng cần được nhớ: một phương thức instance được kế thừa từ lớp cha có vai trò quan trọng khi trùng chữ ký với default method. Nếu lớp cha có phương thức abstract, việc lớp cha khai báo phương thức đó vẫn có thể khiến lớp con phải cung cấp phần thân, dù một interface cũng có default method cùng chữ ký.

Một lớp được khai báo `abstract` có thể giữ lại các nghĩa vụ chưa triển khai. Lớp cụ thể cuối cùng trong chuỗi kế thừa phải đáp ứng tất cả phương thức abstract còn lại.

## 7. Quy trình kiểm tra thực tế

Khi được giao xác định các phương thức abstract mà một interface hoặc lớp kế thừa, hãy làm theo thứ tự sau:

1. **Xác định nút cần xét.** Đó là interface con đang `extends` hay lớp đang `implements` interface nào?
2. **Liệt kê toàn bộ interface cha.** Theo các nhánh cha trực tiếp và gián tiếp, tránh bỏ sót tổ tiên xa.
3. **Phân loại phương thức.** Ghi lại các phương thức instance abstract, default, static và private; static/private không tạo nghĩa vụ instance cho lớp triển khai.
4. **Chuẩn hóa chữ ký.** Xét tên, tham số, generic đã thay thế và kiểu trả về. Gom các khai báo tương đương, rồi kiểm tra chúng có tương thích hay không.
5. **Giải quyết kế thừa và ghi đè.** Xác định khai báo nào cụ thể hơn, default nào có thể được dùng, khai báo abstract nào ghi đè default, và có xung đột từ nhiều nhánh hay không.
6. **Kiểm tra triển khai từ lớp cha.** Một phương thức instance `public` đã được kế thừa có thể đáp ứng hợp đồng; không chỉ tìm trong phần thân của lớp hiện tại.
7. **Liệt kê nghĩa vụ còn lại.** Với lớp cụ thể, mỗi phương thức abstract còn lại phải có triển khai phù hợp và công khai. Với lớp abstract, có thể giữ lại nghĩa vụ để lớp con thực hiện.
8. **Để trình biên dịch xác nhận.** Biên dịch toàn bộ các interface và lớp liên quan. Lỗi biên dịch giúp phát hiện chữ ký không tương thích, xung đột default, thiếu triển khai hoặc lỗi generic mà việc đọc từng tệp riêng lẻ dễ bỏ qua.

Có thể dùng bảng kiểm nhanh sau:

| Dấu hiệu | Cách xử lý |
| --- | --- |
| Interface khai báo `void m();` | Xem là phương thức abstract ngầm định |
| Hai interface cha cùng khai báo `m()` tương thích | Một triển khai có thể đáp ứng cả hai |
| Các kiểu trả về cùng chữ ký tương thích theo quan hệ subtype | Chọn triển khai có kiểu trả về đáp ứng tất cả hợp đồng |
| Kiểu trả về cùng chữ ký không tương thích | Lỗi biên dịch; không thể tạo hai overload chỉ khác kiểu trả về |
| Có default method phù hợp từ interface cha | Có thể dùng triển khai được kế thừa nếu không bị ghi đè hoặc xung đột |
| Hai default method không liên quan xung đột | Ghi đè để giải quyết rõ ràng |
| Interface con khai báo lại default method mà không có thân | Nghĩa vụ abstract được khôi phục cho lớp triển khai |
| Lớp cha đã có phương thức `public` tương thích | Phương thức kế thừa có thể đáp ứng hợp đồng |
| Lớp được khai báo `abstract` | Có thể giữ lại các phương thức chưa triển khai |

## 8. Những lỗi suy luận thường gặp

- **Chỉ đọc interface trực tiếp:** phương thức có thể được kế thừa từ tổ tiên xa hơn nhiều cấp.
- **Đếm từng khai báo thành một nghĩa vụ riêng:** nhiều khai báo cùng chữ ký và tương thích có thể được đáp ứng bởi một triển khai.
- **Bỏ qua `default`:** phương thức có thân có thể đáp ứng hợp đồng, nhưng vẫn phải kiểm tra quan hệ cụ thể và xung đột.
- **Coi static/private là phương thức phải triển khai:** hai loại này không phải nghĩa vụ instance được kế thừa cho lớp.
- **Dùng kiểu trả về để phân biệt overload:** Java không cho phép hai phương thức chỉ khác kiểu trả về.
- **Bỏ qua generic:** phải thay tham số kiểu theo interface con trước khi xác định chữ ký và kiểu trả về.
- **Cho rằng mọi lớp đều phải viết lại phương thức:** triển khai phù hợp có thể đã được kế thừa từ lớp cha hoặc default method.
- **Cho rằng lớp abstract phải hoàn tất mọi phương thức:** lớp abstract có thể chuyển nghĩa vụ còn lại cho lớp con, còn lớp cụ thể phải đáp ứng chúng.
- **Tự đoán khi các nhánh kế thừa xung đột:** kiểm tra quy tắc override và kết quả biên dịch; không tùy ý chọn một khai báo.

Điểm cốt lõi là xác định **tập phương thức thực sự được kế thừa sau khi áp dụng quy tắc chữ ký, kiểu trả về, ghi đè và default method**. Tập phương thức abstract còn lại mới là danh sách nghĩa vụ cần triển khai, chứ không phải tổng số dòng khai báo trong các interface cha.
