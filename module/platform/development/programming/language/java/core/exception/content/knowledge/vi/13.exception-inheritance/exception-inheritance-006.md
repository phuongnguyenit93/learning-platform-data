# Overload, kiểu khai báo của tham chiếu và tập ngoại lệ cần xử lý trong Java

Khi một lớp Java có nhiều phương thức cùng tên nhưng khác danh sách tham số (*method overloading*), lập trình viên dễ cho rằng JVM sẽ chọn phiên bản theo **kiểu thực tế của đối tượng** và từ đó quyết định ngoại lệ phải bắt. Thực tế, Java có hai bước tách biệt:

1. **Lúc biên dịch:** compiler chọn **overload** áp dụng được và cụ thể nhất theo tên phương thức, các phương thức nhìn thấy từ **kiểu tĩnh của biểu thức nhận** (*receiver*), số lượng và **kiểu ở thời điểm biên dịch** của các đối số. Việc phương thức được chọn khai báo `throws IOException` hay `throws SQLException` **không phải tiêu chí chọn overload**.
2. **Sau khi chọn overload:** compiler xác định **các checked exception có thể phát sinh từ lời gọi** theo hợp đồng của phương thức được chọn, và yêu cầu bắt hoặc khai báo `throws` cho những kiểu checked chưa được xử lý. Khi chương trình chạy, **override** có thể điều phối đến phần thân phương thức ở lớp con nhưng không tự chuyển lời gọi sang một overload khác.

Đó là lý do cùng một đối tượng `String` có thể đi vào hai overload khác nhau nếu được chứa trong biến kiểu `String` hoặc `Object`, và vì sao cùng một đối tượng lớp con có thể bị kiểm tra `throws IOException` khác nhau tùy tham chiếu đang được khai báo kiểu lớp cha hay lớp con.

Bài này giải thích có ví dụ Java 17+ chạy được: overload resolution, kiểu tĩnh và runtime, override, checked exception checking, `null` và overload mơ hồ, primitive widening/boxing, generics, constructor overload, giới hạn khi override và cách thiết kế API ngoại lệ dễ dùng.

## 1. Phân biệt overload và override

Hai khái niệm có thể xuất hiện trong cùng một chương trình nhưng giải quyết hai việc khác nhau:

| Tiêu chí | Overload | Override |
| --- | --- | --- |
| Bản chất | Nhiều phương thức cùng tên nhưng **khác chữ ký tham số** | Lớp con định nghĩa lại phương thức kế thừa với chữ ký override-compatible |
| Thời điểm chọn chữ ký | **Compile-time** | Chữ ký lời gọi vẫn được xác định ở compile-time |
| Chọn phần thân thực thi | Phần thân của overload đã chọn, có thể còn chịu dispatch nếu overload đó bị override | **Runtime dispatch** cho instance method có thể chọn implementation ở lớp con |
| Vai trò của `throws` | Không phân biệt hai overload | Override **không được mở rộng checked exceptions** ngoài hợp đồng phương thức cha |
| Vai trò của kiểu tĩnh tham chiếu | Quyết định tập phương thức ứng viên nhìn thấy | Quyết định hợp đồng compile-time tại nơi gọi |
| Vai trò của kiểu runtime đối tượng | Không tự chọn overload khác | Có thể quyết định implementation thực sự của chữ ký đã chọn |

Ví dụ khai báo overload:

```java
void load(Object value) throws java.io.IOException { /* ... */ }

void load(String value) throws java.text.ParseException { /* ... */ }
```

Hai phương thức trên khác danh sách kiểu tham số: `Object` so với `String`, nên Java cho phép chúng có các mệnh đề `throws` khác nhau. Ngược lại, hai phương thức **chỉ khác `throws`** mà danh sách tham số giống hệt nhau **không tạo thành overload hợp lệ**.

Trong một chương trình Java, `throws` đóng vai trò mô tả **hợp đồng ngoại lệ checked của phương thức** chứ không phải thành phần làm độc nhất chữ ký overload.

## 2. Ví dụ hoàn chỉnh: cùng đối tượng `String`, hai kiểu tham chiếu đối số

Lưu thành `OverloadCheckedDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class OverloadCheckedDemo {
    static void inspect(Object value) throws IOException {
        System.out.println("selected=Object");
        throw new IOException("object-path");
    }

    static void inspect(String value) throws ParseException {
        System.out.println("selected=String");
        throw new ParseException("string-path", 0);
    }

    public static void main(String[] args) {
        String narrow = "hello";
        Object broad = narrow;

        try {
            inspect(narrow);
        } catch (ParseException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        try {
            inspect(broad);
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        try {
            inspect((String) broad);
        } catch (ParseException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 OverloadCheckedDemo.java
java OverloadCheckedDemo
```

Kết quả:

```text
selected=String
caught=string-path
selected=Object
caught=object-path
selected=String
caught=string-path
```

Ba lời gọi minh họa rõ:

1. `inspect(narrow)`: biểu thức đối số có kiểu tĩnh `String`. Cả `inspect(Object)` và `inspect(String)` đều áp dụng được, nhưng `String` cụ thể hơn nên compiler chọn phiên bản `String` và cần xử lý `ParseException`.
2. `inspect(broad)`: cùng đối tượng runtime nhưng biểu thức đối số có kiểu tĩnh `Object`. `inspect(String)` không áp dụng được cho đối số kiểu `Object` nếu không ép kiểu; compiler chọn `inspect(Object)` và cần xử lý `IOException`.
3. `inspect((String) broad)`: ép kiểu làm biểu thức đối số có kiểu tĩnh `String`. Lời gọi lại chọn overload `inspect(String)` và cần xử lý `ParseException`. Ép kiểu chỉ an toàn khi đối tượng thực tế tương thích; với đối tượng không phải `String`, phép cast có thể ném `ClassCastException`.

**Kết luận:** ngoại lệ checked tại vị trí gọi được xác định từ **overload đã được compiler chọn**. Đừng quyết định `catch` dựa trên `broad.getClass()` hoặc việc biết đối tượng runtime chứa văn bản.

## 3. Compiler lựa chọn overload theo các bước nào?

Theo JLS §15.12, việc xử lý lời gọi phương thức gồm các bước lớn:

1. Xác định **kiểu cần tìm phương thức** và tên phương thức. Đối với lời gọi `receiver.method(...)`, kiểu khai báo của `receiver` giới hạn tập phương thức có thể nhìn thấy tại nơi gọi.
2. Xác định các phương thức có tên phù hợp, số đối số và khả năng áp dụng theo **kiểu tĩnh của biểu thức đối số**, generic type inference và các quy tắc chuyển đổi hợp lệ.
3. Ưu tiên các pha áp dụng: lời gọi chặt (*strict invocation*), lời gọi cho phép chuyển đổi rộng hơn (*loose invocation*, gồm boxing/unboxing), rồi lời gọi varargs khi cần.
4. Chọn phương thức **cụ thể nhất** trong tập ứng viên áp dụng của pha được sử dụng. Nếu không có một lựa chọn duy nhất phù hợp, lời gọi có thể mơ hồ và không biên dịch.
5. Sau khi có khai báo được chọn, kiểm tra các điều kiện của lời gọi, gồm kiểm tra khả năng phát sinh checked exceptions.
6. Khi chạy, đánh giá đối tượng nhận và các đối số; nếu là instance method có khả năng override, JVM tìm phần thân triển khai thích hợp cho **chữ ký đã được chọn**.

Mệnh đề `throws` không được dùng để “bỏ phiếu” cho overload nào an toàn hơn. Ví dụ, dù người gọi đã viết `catch (IOException)` thì compiler **không vì thế** ưu tiên `inspect(Object)` trước `inspect(String)`.

**Lưu ý:** độ cụ thể của overload không luôn chỉ là “kiểu con thắng kiểu cha”. Java còn có generic methods, boxing/unboxing, varargs và target typing. Khi lời gọi phức tạp, cần áp dụng đúng các pha của JLS §15.12 thay vì suy luận bằng tên biến hay kiểu runtime.

## 4. `throws` không tham gia phân biệt chữ ký overload

Mã sau **cố ý không biên dịch**:

```java
import java.io.IOException;
import java.sql.SQLException;

class InvalidOverloadByThrows {
    void work(String input) throws IOException { }

    void work(String input) throws SQLException { }
    // Lỗi: cùng tên và cùng danh sách tham số.
}
```

Hai khai báo có cùng chữ ký; chỉ khác danh sách ngoại lệ checked. Java không xem chúng là hai overload hợp lệ. Tương tự, chỉ thay đổi **kiểu trả về** cũng không tạo overload khác:

```java
class InvalidOverloadByReturnType {
    String convert(int value) { return "text"; }

    int convert(int value) { return value; }
    // Lỗi: không thể phân biệt bằng return type.
}
```

Cách sửa là chọn tham số khác (nếu thực sự là hai thao tác khác nhau) hoặc đặt tên phương thức khác thể hiện ngữ nghĩa khác nhau:

```java
void readFromFile(String path) throws IOException { }

void readFromDatabase(String query) throws SQLException { }
```

Ba đoạn trong phần này dùng để **minh họa quy tắc khai báo**; đoạn thứ ba muốn biên dịch độc lập phải đặt trong một lớp và thêm import phù hợp.

Hãy nhớ: **đối với overload, tham số phân biệt phương thức; `throws` mô tả nghĩa vụ xử lý lỗi sau khi đã chọn phương thức**.

## 5. Kiểu tĩnh của receiver giới hạn những overload nào nhìn thấy

Không chỉ kiểu của **đối số**, mà kiểu tĩnh của **đối tượng nhận lời gọi** cũng rất quan trọng.

Lưu thành `ReceiverTypeDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class ReceiverTypeDemo {
    static class Parent {
        void send(Object value) throws IOException {
            System.out.println("Parent.send(Object)");
        }
    }

    static class Child extends Parent {
        @Override
        void send(Object value) throws IOException {
            System.out.println("Child.send(Object)");
        }

        void send(String value) throws SQLException {
            System.out.println("Child.send(String)");
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = new Child();

        try {
            parentView.send("abc");
        } catch (IOException ex) {
            System.out.println("parent-view error");
        }

        try {
            childView.send("abc");
        } catch (SQLException ex) {
            System.out.println("child-view error");
        }
    }
}
```

```bash
javac -encoding UTF-8 ReceiverTypeDemo.java
java ReceiverTypeDemo
```

Kết quả:

```text
Child.send(Object)
Child.send(String)
```

Giải thích chi tiết:

- `parentView` có kiểu **khai báo `Parent`**, dù đối tượng được tạo bằng `new Child()`. Compiler tìm trong API của `Parent` và chỉ thấy `send(Object)`. Vì vậy `parentView.send("abc")` chọn chữ ký `send(Object)` và phải xử lý `IOException`.
- Khi chạy, đối tượng runtime là `Child` nên phần thân **override `Child.send(Object)`** được thực thi. Nó in `Child.send(Object)`; Java **không chuyển sang `Child.send(String)`**.
- `childView` có kiểu khai báo `Child`, nên compiler thấy cả `send(Object)` và `send(String)`. Với đối số literal `"abc"`, nó chọn overload `send(String)` cụ thể hơn. Tại nơi gọi, nghĩa vụ checked exception là `SQLException`.

Đây là ví dụ then chốt về **hai vai trò của kiểu tĩnh**: kiểu receiver xác định overload có thể thấy, còn kiểu đối số xác định overload nào được chọn. Runtime dispatch chỉ ảnh hưởng implementation của phương thức đã chọn khi có override.

## 6. Override: vì sao tham chiếu lớp cha có thể cần `catch` dù lớp con không ném checked exception?

Xét lớp cha khai báo `throws IOException`, nhưng implementation lớp con thu hẹp hợp đồng và không ném checked exception.

Lưu thành `OverrideThrowsDemo.java`:

```java
import java.io.IOException;

public class OverrideThrowsDemo {
    static class Parent {
        void fetch() throws IOException {
            System.out.println("parent fetch");
        }
    }

    static class Child extends Parent {
        @Override
        void fetch() {
            System.out.println("child fetch");
        }
    }

    public static void main(String[] args) {
        Parent asParent = new Child();
        Child asChild = new Child();

        try {
            asParent.fetch();
        } catch (IOException ex) {
            System.out.println("caught I/O");
        }

        asChild.fetch();
    }
}
```

```bash
javac -encoding UTF-8 OverrideThrowsDemo.java
java OverrideThrowsDemo
```

Kết quả:

```text
child fetch
child fetch
```

Cả hai lời gọi đều chạy phần thân `Child.fetch()`, vì đối tượng runtime là `Child` và phương thức `fetch()` được override. Nhưng:

- `asParent.fetch()` được kiểm tra theo **khai báo `Parent.fetch() throws IOException`**. Vì vậy caller vẫn phải xử lý hoặc khai báo `IOException`, dù bạn biết lần này đối tượng là Child.
- `asChild.fetch()` được kiểm tra theo **khai báo `Child.fetch()`** không có checked exception, nên không cần `catch(IOException)`.

**Nghĩa vụ checked exception tại điểm gọi không đổi tùy lớp runtime của đối tượng.** Hợp đồng kiểu tĩnh cho phép thay thế implementation mà vẫn bảo đảm code caller đã được kiểm tra đúng.

Ngược lại, lớp con không được override và khai báo checked exception **rộng hơn** phương thức cha. Ví dụ, nếu cha khai báo `throws IOException`, lớp con không thể override cùng chữ ký bằng `throws Exception` hoặc thêm `SQLException` độc lập.

## 7. Ranh giới override: cùng chữ ký, không mở rộng checked exception

Mã **cố ý không biên dịch**:

```java
import java.io.IOException;
import java.sql.SQLException;

class ParentService {
    void execute() throws IOException { }
}

class InvalidChildService extends ParentService {
    @Override
    void execute() throws IOException, SQLException { }
    // SQLException không được khai báo bởi ParentService.execute().
}
```

Khi override phương thức có `throws IOException`, implementation có thể:

- Giữ `throws IOException`.
- Khai báo loại hẹp hơn, ví dụ `throws FileNotFoundException`.
- Không khai báo checked exception nào.
- Vẫn có khả năng ném unchecked `RuntimeException`, không bị giới hạn giống checked exception.

Nhưng không thể thêm `SQLException` (không thuộc `IOException`) hoặc `Exception` rộng hơn hợp đồng cha. Quy tắc này áp dụng tương tự khi triển khai phương thức interface.

**Khác với overload:** hai overload có chữ ký tham số khác nhau có thể khai báo các checked exceptions hoàn toàn khác nhau. Giới hạn thu hẹp checked exceptions là quy tắc của **override**, không phải quy tắc chung cho mọi phương thức trùng tên.

## 8. Tập ngoại lệ checked mà compiler yêu cầu được xác định thế nào?

Khi compiler thấy lời gọi:

```java
service.load(argument);
```

nó phân tích các phần theo thứ tự:

1. Xác định kiểu tĩnh của `service` và `argument`.
2. Chọn khai báo overload theo JLS §15.12.
3. Xác định **các checked exception mà lời gọi này có thể ném** từ kiểu lời gọi/khai báo đã chọn theo JLS §11.2.1.
4. Phân tích các `try-catch` bao quanh, mệnh đề `throws` của phương thức chứa, các kiểu cha/con của ngoại lệ và các quy tắc unreachable checked `catch`.
5. Nếu một checked exception có thể thoát ra ngoài mà không được xử lý hoặc khai báo phù hợp, báo lỗi biên dịch.

Ví dụ với hai overload:

```java
void load(Object source) throws IOException { /* ... */ }

void load(String source) throws SQLException { /* ... */ }
```

Khi gọi `load("abc")`, overload `String` được chọn. Việc caller có sẵn `catch(IOException)` **không làm Java chọn phương thức `load(Object)`**.

Đây là đoạn **cố ý không biên dịch** khi đặt trong lớp có hai overload trên:

```java
try {
    load("abc");  // Overload String: declares SQLException.
} catch (IOException ex) {
    System.out.println("caught I/O");
}
```

Một vấn đề là `SQLException` checked chưa được bắt hoặc khai báo. Đồng thời, với một `try` không có khả năng ném `IOException` checked theo phân tích của Java, nhánh `catch(IOException)` không phù hợp và có thể bị compiler từ chối với chẩn đoán “never thrown”.

Cách đúng là bắt hoặc khai báo **SQLException** của overload String:

```java
try {
    load("abc");
} catch (SQLException ex) {
    System.out.println("caught SQL");
}
```

Đây là mẫu trong thân phương thức với import và chữ ký hai overload đã có; việc thay `IOException` bằng `SQLException` **không thay đổi overload được chọn**, chỉ đáp ứng đúng hợp đồng ngoại lệ.

## 9. Không phải `catch` nào cũng cần và không phải `catch` nào cũng hợp lệ

Compiler không yêu cầu bắt mọi ngoại lệ được liệt kê ở mọi overload cùng tên. Nó xem xét ngoại lệ có thể phát sinh từ **đường lời gọi đang được biên dịch**.

Một vài nguyên tắc:

| Tình huống | Nghĩa vụ |
| --- | --- |
| Đã chọn overload `load(String) throws SQLException` | Bắt hoặc khai báo `SQLException`, nếu nó có thể thoát |
| Overload khác là `load(Object) throws IOException` nhưng không được chọn | Không tự phát sinh nghĩa vụ `IOException` từ lời gọi String |
| Phương thức được chọn chỉ khai báo `RuntimeException` | Không có nghĩa vụ checked exception tương ứng |
| Một `catch` bắt kiểu cha như `Exception` | Có thể bao quát nhiều checked exception, nhưng hợp đồng rộng hơn và kém cụ thể |
| Một overload khai báo `throws IOException` dù implementation hiện tại không ném | Caller vẫn phải dựa trên hợp đồng compile-time |
| Một `try` chứa nhiều lời gọi tới các overload khác nhau | Tập ngoại lệ cần xử lý có thể là hợp của các kiểu checked từ mọi lời gọi đó |

Ví dụ có hai lời gọi:

```java
try {
    load((Object) "file");
    load("database");
} catch (IOException ex) {
    handleIo(ex);
} catch (SQLException ex) {
    handleDatabase(ex);
}
```

Đây là mẫu minh họa, giả định overload và hàm xử lý đã khai báo. Lời gọi đầu chọn `load(Object)` và có thể ném `IOException`; nếu nó hoàn tất bình thường, lời gọi thứ hai chọn `load(String)` và có thể ném `SQLException`. Hai nhánh `catch` là hợp lý vì **cả hai loại đều có thể xuất hiện từ thân `try`**.

**Đừng kiểm tra checked exceptions bằng việc chạy thử một nhánh dữ liệu duy nhất.** Compiler phân tích hợp đồng có thể xảy ra, không chỉ sự kiện đã quan sát ở lần chạy đó.

## 10. `null`: chọn overload cụ thể nhất hoặc gặp mơ hồ

Giá trị `null` không có lớp runtime để JVM dùng như một đối tượng thông thường. Trong overload resolution, nó có thể tương thích với nhiều kiểu tham chiếu và compiler chọn phiên bản cụ thể nhất khi có thể.

### Có quan hệ kế thừa: `String` cụ thể hơn `Object`

```java
static void show(Object x) throws IOException { /* ... */ }

static void show(String x) throws SQLException { /* ... */ }

show(null); // Chọn show(String), vì String cụ thể hơn Object.
```

Đây là đoạn minh họa trong một lớp với import phù hợp, không phải chương trình hoàn chỉnh. Nếu gọi trong phương thức thông thường, bên gọi phải xử lý hoặc khai báo `SQLException`. Việc biểu thức `null` không phải một `String` đang tồn tại không làm Java chọn `Object`.

### Không có quan hệ cụ thể hơn duy nhất: gọi mơ hồ

```java
import java.io.IOException;
import java.sql.SQLException;

class AmbiguousNullExample {
    static void show(String value) throws IOException { }

    static void show(Integer value) throws SQLException { }

    static void demo() {
        show(null); // Compile error: ambiguous method call.
    }
}
```

Đây là ví dụ **cố ý không biên dịch**. `String` và `Integer` không có quan hệ kiểu con/cha với nhau; cả hai overload đều áp dụng cho `null` nhưng không có lựa chọn cụ thể nhất duy nhất.

Hai cách sửa khi đó:

```java
show((String) null);  // Chọn overload String.
show((Integer) null); // Chọn overload Integer.
```

Đây là các dòng minh họa nằm trong lớp ví dụ nói trên, và phương thức chứa phải xử lý/khai báo `IOException` hoặc `SQLException` tương ứng.

**Không thể chữa lời gọi mơ hồ bằng cách thêm `catch(SQLException)` hoặc `throws IOException` ở ngoài.** Phải giải quyết chữ ký được chọn trước, sau đó mới kiểm tra checked exceptions.

## 11. Phân biệt widening, boxing và varargs khi overload

Lựa chọn overload còn phụ thuộc **pha áp dụng** chứ không chỉ vào mức độ gần nhau trong hệ phân cấp class. Với đối số số nguyên `int`, một overload nhận `long` có thể được chọn trong pha strict invocation trước một overload nhận `Integer` cần boxing.

Lưu thành `WideningVsBoxingDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class WideningVsBoxingDemo {
    static void process(long value) throws IOException {
        System.out.println("selected=long");
    }

    static void process(Integer value) throws SQLException {
        System.out.println("selected=Integer");
    }

    public static void main(String[] args) {
        try {
            process(7); // int -> long (primitive widening)
        } catch (IOException ex) {
            System.out.println("I/O");
        }

        Integer boxed = 7;
        try {
            process(boxed); // Integer overload is an exact match
        } catch (SQLException ex) {
            System.out.println("SQL");
        }
    }
}
```

```bash
javac -encoding UTF-8 WideningVsBoxingDemo.java
java WideningVsBoxingDemo
```

Kết quả:

```text
selected=long
selected=Integer
```

Cơ chế:

- `process(7)`: số literal có kiểu `int`; widening primitive sang `long` hợp lệ ở pha strict, nên Java không cần chuyển sang pha boxing để chọn `process(Integer)`. Nghĩa vụ checked tương ứng là `IOException`.
- `process(boxed)`: biểu thức có kiểu `Integer`, nên overload `Integer` là lựa chọn chính xác và có nghĩa vụ `SQLException`.

Varargs (`Type...`) được xét theo các quy tắc phù hợp của JLS, thường sau hai pha không cần variable arity. Đừng nhìn thấy một lời gọi có dấu `...` rồi mặc định nó luôn thắng bản nhận một tham số thường.

**Không sử dụng danh sách `throws` để dự đoán việc widening hay boxing.** Chọn overload xong mới xem hợp đồng ngoại lệ.

## 12. `var` và kiểu tĩnh được suy luận vẫn quyết định overload

Từ Java 10, `var` cho phép compiler suy luận kiểu biến cục bộ từ biểu thức khởi tạo. Điều này **không phải dynamic typing**: biến vẫn có một kiểu tĩnh xác định.

Ví dụ:

```java
var name = "alpha";   // compiler suy ra String
Object broad = name;  // kiểu khai báo Object

inspect(name);        // dùng overload inspect(String)
inspect(broad);       // dùng overload inspect(Object)
```

Đây là mẫu trong một phương thức, giả định hai overload ở phần 2 đã được khai báo và các checked exceptions được xử lý phù hợp.

Muốn chọn khác overload, bạn thay **kiểu biểu thức** qua cách khai báo hoặc ép kiểu đúng, chứ không chỉ đổi giá trị runtime của biến.

### Generic method cũng dựa trên bound ở vị trí gọi bên trong

Một tình huống dễ nhầm: một phương thức generic nhận `T` nhưng gọi một tên hàm đang có overload `Object` và `String`. Trong phần thân generic, `T` với bound mặc định `Object` **không tự biến thành `String`** chỉ vì một lần caller truyền String.

Lưu thành `GenericOverloadDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class GenericOverloadDemo {
    static void print(Object value) throws IOException {
        System.out.println("overload=Object");
    }

    static void print(String value) throws ParseException {
        System.out.println("overload=String");
    }

    static <T> void forward(T value) throws IOException {
        print(value);
    }

    public static void main(String[] args) {
        try {
            print("hello");
        } catch (ParseException ex) {
            System.out.println("parse failure");
        }

        try {
            forward("hello");
        } catch (IOException ex) {
            System.out.println("I/O failure");
        }
    }
}
```

```bash
javac -encoding UTF-8 GenericOverloadDemo.java
java GenericOverloadDemo
```

Kết quả:

```text
overload=String
overload=Object
```

Trong `forward(T value)`, compiler phân tích `print(value)` theo kiểu `T` được giới hạn mặc định bởi `Object`. Nó không chuyên biệt hóa bytecode thành `print(String)` cho mỗi lần truyền tham số generic. Vì vậy `forward` khai báo `throws IOException`, không phải `throws ParseException`.

Nếu nhu cầu nghiệp vụ là xử lý riêng từng loại dữ liệu, hãy truyền chiến lược xử lý (callback/interface) hoặc sử dụng overload tại tầng có thông tin kiểu phù hợp, thay vì kỳ vọng generic call tự chọn overload theo lớp runtime.

## 13. Constructor overload cũng có những quy tắc tương tự

Constructor có thể overload theo danh sách tham số; compiler chọn constructor ở **compile-time** dựa trên kiểu biểu thức truyền vào. Từng constructor có thể khai báo checked exceptions khác nhau.

Lưu thành `ConstructorOverloadDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class ConstructorOverloadDemo {
    static class Parser {
        Parser(Object source) throws IOException {
            System.out.println("constructor=Object");
        }

        Parser(String source) throws ParseException {
            System.out.println("constructor=String");
        }
    }

    public static void main(String[] args) {
        Object broad = "input";
        String narrow = "input";

        try {
            new Parser(broad);
        } catch (IOException ex) {
            System.out.println("I/O");
        }

        try {
            new Parser(narrow);
        } catch (ParseException ex) {
            System.out.println("parse");
        }
    }
}
```

```bash
javac -encoding UTF-8 ConstructorOverloadDemo.java
java ConstructorOverloadDemo
```

Kết quả:

```text
constructor=Object
constructor=String
```

Constructor không được override như instance method, nhưng nguyên tắc **chọn phiên bản có tham số phù hợp trước khi kiểm tra checked exceptions** vẫn tương tự. Nếu có nhiều overload constructor mơ hồ (ví dụ nhận `String` và `Integer` với đối số `null`), compiler cũng phải giải quyết mơ hồ chứ không dựa trên danh sách `throws` để chọn.

## 14. Giao diện và đa hình: chọn hợp đồng từ kiểu khai báo

Interface thường là nơi mô tả hợp đồng của một dịch vụ:

```java
import java.io.IOException;

interface ResourceService {
    void load(String key) throws IOException;
}
```

Implementation có thể thu hẹp checked exception:

```java
class CachedResourceService implements ResourceService {
    @Override
    public void load(String key) {
        System.out.println("cache=" + key);
    }
}
```

Đây là các khai báo minh họa trong cùng package có import phù hợp. Ở tầng gọi:

```java
ResourceService service = new CachedResourceService();

try {
    service.load("user-42");
} catch (IOException ex) {
    System.out.println("I/O failure");
}
```

Caller phải tuân thủ hợp đồng `ResourceService.load(String) throws IOException` theo kiểu khai báo của biến `service`, dù implementation hiện tại không ném checked exception. Nếu khai báo trực tiếp biến kiểu `CachedResourceService`, compiler có thể dựa vào chữ ký override hẹp hơn.

Điều đó giúp hệ thống thay implementation: một implementation khác có thể dùng I/O thực sự và phát sinh IOException, trong khi code caller dựa trên interface đã có cơ chế xử lý hợp lệ.

**Cẩn thận với API interface có nhiều overload:** những overload nào caller nhìn thấy cũng phụ thuộc interface, không phải mọi phương thức tồn tại trên implementation runtime.

## 15. Bắt lỗi ở đâu trong chuỗi gọi khi có overload?

Một tầng service có thể gọi các overload tùy ý nghĩa dữ liệu. Mỗi nhánh gọi có thể kéo theo các checked exceptions riêng:

```java
static void route(boolean fromFile) throws IOException, SQLException {
    if (fromFile) {
        load((Object) "file");
    } else {
        load("database");
    }
}
```

Đây là phương thức minh họa, giả định overload `load(Object) throws IOException` và `load(String) throws SQLException` đã được khai báo trong lớp phù hợp. Vì cả hai nhánh đều có thể được thực thi, `route` khai báo cả `IOException` và `SQLException` nếu không bắt ở trong.

Ở caller, có thể:

```java
try {
    route(sourceIsFile);
} catch (IOException ex) {
    handleIo(ex);
} catch (SQLException ex) {
    handleSql(ex);
}
```

Các tên `sourceIsFile`, `handleIo` và `handleSql` ở trên là **placeholder ngữ cảnh của một đoạn mã minh họa**, không phải lớp Java chạy độc lập. Mục đích là nhận ra **tập ngoại lệ checked của toàn phương thức** có thể là hợp của nhiều đường điều khiển; không phải caller chỉ cần bắt một ngoại lệ dựa trên dữ liệu của một lần chạy.

Nếu hai lỗi có cùng cách phục hồi, có thể dùng `catch (IOException | SQLException ex)` theo quy tắc multi-catch, miễn hành động chung có ý nghĩa nghiệp vụ. Nếu cần xử lý riêng, giữ hai `catch` tương ứng.

Không nên công bố `throws Exception` chỉ để tránh theo dõi loại ngoại lệ có thể xảy ra ở mỗi overload. Nó hợp lệ trong nhiều trường hợp nhưng làm hợp đồng kém rõ ràng và khiến caller khó quyết định chính sách xử lý.

## 16. Những điểm dễ gây lỗi biên dịch

| Tình huống | Vì sao sai? | Hướng sửa |
| --- | --- | --- |
| Viết hai phương thức khác nhau chỉ bởi `throws` | `throws` không phải yếu tố phân biệt overload | Đổi chữ ký tham số hoặc tách tên phương thức |
| Cho rằng runtime `String` trong biến `Object` sẽ chọn `load(String)` | Overload chọn theo kiểu tĩnh của biểu thức | Dùng kiểu đúng, ép kiểu có kiểm tra hoặc đổi API |
| Dùng `Parent ref = new Child(); ref.childOnlyOverload(...)` | Phương thức chỉ có ở Child không nhìn thấy qua Parent | Dùng hợp đồng phù hợp hoặc tham chiếu Child có chủ đích |
| `catch(IOException)` trong khi overload đã chọn chỉ khai báo `SQLException` checked | Compiler không đổi overload theo catch | Bắt/khai báo SQLException |
| `Child.override() throws Exception` trong khi Parent chỉ `throws IOException` | Override mở rộng checked exception | Thu hẹp hoặc bỏ loại checked mới |
| `show(null)` khi có `show(String)` và `show(Integer)` | Không có overload cụ thể nhất duy nhất | Ép kiểu có chủ đích hoặc đổi chữ ký |
| Cho rằng `var` là kiểu runtime tự thay đổi | `var` suy ra một kiểu tĩnh | Kiểm tra kiểu được suy ra |
| Cho rằng `T` generic sẽ chọn overload theo dữ liệu runtime | Compiler xử lý `T` theo type bound | Dùng overload ở tầng có kiểu cụ thể hoặc strategy |
| Chọn overload theo kiểu `catch` mà caller viết | `throws`/`catch` không tham gia overload resolution | Chọn phương thức trước, kiểm tra exception sau |
| Bắt mọi `Exception` để che lỗi thiết kế overload | Có thể bắt quá rộng và che lỗi | Bắt cụ thể các checked exceptions theo hợp đồng |
| Dùng `instanceof` để suy luận compiler sẽ chọn overload khác | `instanceof` runtime không viết lại lời gọi đã biên dịch | Phân nhánh rõ và gọi overload phù hợp nếu cần |
| Trông chờ override thay đổi những checked exception bắt buộc ở caller kiểu Parent | Caller được kiểm tra theo static type Parent | Dùng API public ổn định hoặc hẹp kiểu tham chiếu khi thích hợp |

## 17. Checklist phân tích một lời gọi bị báo lỗi checked exception

Khi gặp `unreported exception ... must be caught or declared to be thrown`:

1. **Viết rõ tên phương thức** đang gọi và những overload có thể nhìn thấy từ kiểu khai báo của receiver.
2. **Ghi kiểu tĩnh của mỗi đối số** — gồm literal, biến kiểu `Object`, `String`, biểu thức cast, `var` hoặc generic type variable.
3. **Xác định overload được chọn** theo khả năng áp dụng và độ cụ thể; nếu mơ hồ, giải quyết ambiguity trước.
4. **Đọc đúng `throws` của overload ấy**, không đọc tất cả `throws` của mọi phương thức cùng tên.
5. **Nếu có override**, phân biệt hợp đồng của chữ ký theo kiểu tĩnh với phần thân thực thi theo đối tượng runtime.
6. **Xét các lời gọi khác** trong cùng `try` hoặc phương thức có thể đóng góp loại checked exception khác.
7. **Xem quan hệ lớp ngoại lệ**: `IOException` có thể bao quát `FileNotFoundException`; các kiểu độc lập như `IOException` và `SQLException` cần xử lý riêng hoặc bằng lớp cha phù hợp.
8. **Chọn tầng xử lý**: có thể phục hồi ở đây thì `catch`; nếu không, khai báo `throws` hoặc chuyển thành ngoại lệ nghiệp vụ với cause rõ ràng.
9. **Kiểm tra hợp đồng interface/override**: không khai báo checked exception mới vượt quá quyền của lớp cha.
10. **Viết test compile-time và runtime riêng**: chạy thử chỉ cho biết overload/implementation và lỗi của dữ liệu thử, không thay việc compiler xác định nghĩa vụ checked.

## 18. Câu hỏi tự kiểm tra

**1.** `void read(Object) throws IOException` và `void read(String) throws SQLException`. Đối số `Object x = "abc"; read(x);` cần xử lý gì?  
**`IOException`**, vì kiểu tĩnh của `x` là Object nên chọn overload Object.

**2.** Với hai overload trên, `read("abc")` cần xử lý gì?  
**`SQLException`**, vì String là kiểu áp dụng cụ thể hơn.

**3.** Thêm `catch(IOException)` quanh `read("abc")` có khiến compiler chọn overload Object không?  
**Không.** Overload được chọn trước; phải xử lý hợp đồng SQLException đã được chọn.

**4.** `Parent p = new Child();`, Parent chỉ khai báo `execute(Object) throws IOException`, Child override nó và overload `execute(String) throws SQLException`. `p.execute("abc")` chọn gì?  
**Chọn chữ ký `execute(Object)`** theo Parent, và có thể chạy phần thân override Child.execute(Object). Caller phải xử lý IOException.

**5.** `Child c = new Child(); c.execute("abc")` thì sao?  
**Chọn overload `execute(String)`** nếu nó nhìn thấy và áp dụng cụ thể nhất; caller phải xử lý SQLException.

**6.** Có được viết hai overload chỉ khác `throws IOException` và `throws SQLException` không?  
**Không** nếu danh sách tham số giống nhau.

**7.** `show(String)` và `show(Integer)`, gọi `show(null)` có tự chọn kiểu có `throws` nhỏ hơn không?  
**Không.** Lời gọi mơ hồ; `throws` không giải quyết sự mơ hồ.

**8.** `Parent.fetch() throws IOException`, Child override `fetch()` không khai báo checked exceptions. Caller có biến Parent trỏ Child có còn phải xử lý IOException không?  
**Có.** Compiler kiểm tra theo Parent.fetch().

**9.** Generic method nhận `T` không giới hạn gì thêm và gọi `process(T)`, có tự chọn overload `process(String)` khi truyền String ở runtime không?  
**Không.** Phần thân được biên dịch theo type bound của T (mặc định Object).

**10.** Nếu một phương thức có hai đường gọi tới hai overload lần lượt `throws IOException` và `throws SQLException`, phương thức bao ngoài không bắt lỗi nên khai báo gì?  
Thông thường **`throws IOException, SQLException`** hoặc kiểu cha phù hợp. Nếu chính sách xử lý khác nhau, dùng `catch` ở tầng thích hợp.

## Tài liệu tham khảo chuẩn

- [Java Language Specification, Java SE 21 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): chọn overload ở compile-time và runtime invocation.
- [JLS 21 — §15.12.2 Choosing Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2): các pha áp dụng và phương thức cụ thể nhất.
- [JLS 21 — §11.2.1 Exception Analysis of Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.1): tập ngoại lệ mà biểu thức lời gọi phương thức có thể ném.
- [JLS 21 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3): nghĩa vụ bắt/khai báo checked exception.
- [JLS 21 — §8.4.9 Overloading](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.9): overload và ý nghĩa của kiểu đối số lúc biên dịch.
- [JLS 21 — §8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3): giới hạn checked exceptions khi override.
- [JLS 21 — §15.9 Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9): lựa chọn constructor overload.

**Ghi nhớ:** Java **chọn overload bằng kiểu tĩnh** của receiver/đối số và chữ ký phương thức tại compile-time; **kiểm tra checked exceptions theo overload đã chọn**; sau đó runtime dispatch mới có thể lựa chọn phần thân override. `throws` không giúp chọn overload và runtime type không âm thầm chuyển lời gọi sang một overload khác.
