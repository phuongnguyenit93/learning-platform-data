# Phạm vi của biến trong `try` và tham số `catch` trong Java

Một đoạn mã xử lý ngoại lệ trong Java có thể **biên dịch sai dù cách bắt exception hoàn toàn đúng**, chỉ vì biến được khai báo ở một phạm vi không còn hiệu lực, hoặc vì trình biên dịch không thể chứng minh biến đã được gán giá trị trước khi sử dụng. Để viết `try/catch` rõ ràng và an toàn, cần phân biệt ba vấn đề:

1. **Scope (phạm vi nhìn thấy tên)**: từ vị trí nào đến đâu một biến có thể được gọi tên?
2. **Lifetime (thời gian tồn tại của dữ liệu/đối tượng)**: khi thoát khối, đối tượng được tham chiếu có nhất thiết bị hủy hay không?
3. **Definite assignment (chắc chắn đã được gán)**: ở một điểm đọc biến cục bộ, compiler có chứng minh biến đã nhận giá trị trên mọi đường thực thi có thể tới điểm đó không?

`try`, `catch`, `finally` là những khối có dấu ngoặc nhọn riêng. **Biến cục bộ khai báo bên trong thân `try` không nhìn thấy trong thân `catch` hoặc `finally`**. Ngược lại, biến cục bộ được khai báo trước `try` trong cùng phạm vi bao ngoài có thể được dùng bên trong các khối con, miễn là đã được gán hợp lệ. **Tham số `catch (SomeException e)` chỉ thuộc phạm vi của chính thân `catch` tương ứng**, không thuộc `try`, handler khác hoặc các lệnh sau cấu trúc.

Bài này tập trung vào phạm vi biến quanh `try/catch` trong Java 17+, giải thích cả lỗi biên dịch lẫn cách thiết kế mã sao cho xử lý ngoại lệ không làm mất dữ liệu hoặc che mất tín hiệu thất bại.

## 1. Bản đồ phạm vi của `try`, `catch`, `finally`

Xem đoạn mã khung sau. Đây là minh họa quy tắc scope; các lệnh có tên `work`, `recover` và `cleanup` chưa được định nghĩa nên đoạn này không phải chương trình độc lập:

```java
String shared = "trước try";       // Phạm vi bao ngoài

try {
    int onlyInTry = 10;          // Chỉ thuộc khối try
    work(shared, onlyInTry);
} catch (IllegalStateException problem) {
    recover(shared, problem);    // shared và problem nhìn thấy ở đây
    // onlyInTry: KHÔNG nhìn thấy
} finally {
    cleanup(shared);             // shared nhìn thấy ở đây
    // onlyInTry và problem: KHÔNG nhìn thấy
}

System.out.println(shared);      // shared vẫn nhìn thấy
// onlyInTry và problem: KHÔNG nhìn thấy
```

| Biến | Khai báo ở đâu? | Trong `try` | Trong `catch` | Trong `finally` | Sau cấu trúc |
| --- | --- | --- | --- | --- | --- |
| `shared` | Trước `try`, ở khối bao ngoài | Có | Có | Có | Có, đến hết scope bao ngoài |
| `onlyInTry` | Trong thân `try` | Có, từ khai báo tới hết scope | Không | Không | Không |
| `problem` | Tham số `catch` | Không | Có, trong chính thân handler | Không | Không |
| Biến khai báo trong `catch` | Trong thân `catch` | Không | Chỉ chính handler đó | Không | Không |
| Biến khai báo trong `finally` | Trong thân `finally` | Không | Không | Có, trong `finally` | Không |

**Cẩn thận với cách đọc bảng:** “Có” nói về *phạm vi tên biến*, chưa khẳng định biến đã được khởi tạo/gán hợp lệ. Một local variable có thể nhìn thấy trong một khối nhưng vẫn bị trình biên dịch từ chối sử dụng vì chưa **definitely assigned**.

Các nhánh `catch` của cùng một `try` có scope riêng, nên có thể đặt tên tham số giống nhau ở nhiều handler:

```java
try {
    operation();
} catch (java.io.IOException e) {
    System.out.println("I/O: " + e.getMessage());
} catch (IllegalArgumentException e) {
    System.out.println("Input: " + e.getMessage());
}
```

Đây là **khung minh họa**, giả sử `operation()` là phương thức có thể ném `IOException` và `IllegalArgumentException`. Hai tham số cùng tên `e` là hợp lệ vì thuộc **hai khối `catch` tách biệt**, không hoạt động đồng thời.

## 2. Một biến khai báo trong `try` không xuất hiện trong `catch`

Lỗi rất thường gặp là khai báo giá trị trả về bên trong `try` rồi muốn in giá trị đó tại `catch` hoặc ngay sau `try/catch`.

Ví dụ **cố ý không biên dịch**:

```java
try {
    int quantity = Integer.parseInt("12");
    System.out.println(quantity);
} catch (NumberFormatException e) {
    System.out.println(quantity); // Lỗi: không tìm thấy quantity
}
System.out.println(quantity);     // Lỗi: không tìm thấy quantity
```

Tên `quantity` thuộc phạm vi khối `try`. Khi compiler phân tích handler `catch` và câu lệnh bên ngoài, **không có biến cục bộ tên `quantity` nhìn thấy ở hai nơi đó**. Lỗi scope được kiểm tra lúc biên dịch, cho dù bạn tin rằng khi `parseInt` thành công thì biến chắc chắn đã được tạo.

Cách sửa phụ thuộc nhu cầu thực tế:

- Nếu chỉ cần `quantity` để xử lý bên trong đường thành công, hãy **giữ cả phần sử dụng bên trong `try`**; không kéo biến ra ngoài không cần thiết.
- Nếu cần kết quả cho cả đường thành công và đường xử lý ngoại lệ, hãy **khai báo biến ở khối bao ngoài** và bảo đảm mọi đường đi hợp lệ đều gán giá trị trước khi đọc.
- Nếu một thao tác có thể thất bại và không tồn tại giá trị số hợp lệ, có thể dùng **`OptionalInt`, kiểu kết quả có trạng thái**, hoặc trả về sớm từ phương thức; không buộc một số dự phòng trở thành dữ liệu hợp lệ.

**Đừng cố sửa bằng cách tạo lại một biến cùng tên trong `catch`** rồi kỳ vọng đó là biến bên `try`. Hai khai báo ở hai scope khác nhau là **hai biến khác nhau**, không truyền dữ liệu qua lại.

## 3. Ví dụ Java 17 đầy đủ: đặt biến ở đúng phạm vi

Tệp `TryVariableScopeDemo.java`:

```java
public class TryVariableScopeDemo {
    static void process(String input) {
        System.out.println("Input: " + input);
        try {
            int number = Integer.parseInt(input);
            System.out.println("Trong try: " + (number * 2));
        } catch (NumberFormatException e) {
            System.out.println("Trong catch: không phải số nguyên");
        }
        System.out.println("Sau try/catch");
    }

    public static void main(String[] args) {
        process("7");
        process("abc");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 TryVariableScopeDemo.java
java TryVariableScopeDemo
```

**Stdout chính xác** trên terminal hiển thị UTF-8:

```text
Input: 7
Trong try: 14
Sau try/catch
Input: abc
Trong catch: không phải số nguyên
Sau try/catch
```

Trong ví dụ này, `number` chỉ cần phục vụ đường parse thành công, nên phạm vi trong `try` là hợp lý. Khi `"abc"` không chuyển đổi được, exception được bắt; không có giá trị `number` nào cần được dùng trong handler. Lệnh nằm sau cấu trúc chạy trên cả hai đường đi nếu handler kết thúc bình thường.

Điểm đáng chú ý: **scope của `number` không mở rộng sau khi exception được bắt**. Kết thúc bất thường hay thành công của thao tác không làm thay đổi luật scope do compiler xác định từ cấu trúc mã nguồn.

## 4. Biến ở khối ngoài dùng được trong cả `try` và `catch`

Khi cả hai nhánh cần cập nhật một kết quả chung, khai báo biến trước `try`:

```java
String label;

try {
    int quantity = Integer.parseInt(input);
    label = "Số lượng: " + quantity;
} catch (NumberFormatException e) {
    label = "Số lượng không hợp lệ";
}

System.out.println(label);
```

Đây là **khung phương thức minh họa**, giả sử đã có tham số `input` kiểu `String`. `label` nhìn thấy trong cả `try` lẫn `catch` vì khai báo ở khối bao ngoài. Việc đọc `label` sau cấu trúc có thể hợp lệ vì:

- Nếu lời gọi parse và phần gán thành công, `label` được gán ở nhánh `try`.
- Nếu parse ném `NumberFormatException` và handler kết thúc bình thường, `label` được gán ở `catch`.
- Nếu có một exception khác không được bắt, phương thức không tiếp tục bình thường tới `println`, nên đường đó không làm cho biến bị đọc chưa gán.

Java kiểm tra những điều này bằng quy tắc **definite assignment**, không đơn thuần chỉ nhìn thấy có một phép gán ở đâu đó trong mã.

Để dễ kiểm chứng, chương trình độc lập sau gán kết quả ở cả hai nhánh. Lưu thành `SharedResultDemo.java`:

```java
public class SharedResultDemo {
    static String describe(String text) {
        String result;
        try {
            int value = Integer.parseInt(text);
            result = "Hợp lệ: " + value;
        } catch (NumberFormatException e) {
            result = "Không hợp lệ";
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(describe("42"));
        System.out.println(describe("x"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 SharedResultDemo.java
java SharedResultDemo
```

Stdout:

```text
Hợp lệ: 42
Không hợp lệ
```

Biến `result` **không cần gán một giá trị giả ban đầu** vì mọi đường đi tới `return result` đã gán cho nó. Nếu mục tiêu là ngăn caller hiểu nhầm thất bại thành thành công, kiểu dữ liệu kết quả chứa trạng thái hoặc trả về từ từng nhánh cũng có thể rõ ràng hơn.

## 5. Scope khác với definite assignment

Hai lỗi compiler nhìn giống nhau trong mắt người mới học nhưng có nguyên nhân khác:

- **Tên biến ngoài phạm vi**: biến được khai báo trong `try` rồi dùng ở `catch`. Compiler không tìm thấy tên ở nơi đang dùng.
- **Biến chưa chắc đã được gán**: biến được khai báo ngoài `try` và nhìn thấy ở mọi nhánh, nhưng compiler không chứng minh nó đã nhận giá trị trước khi đọc.

Ví dụ thứ hai, **cố ý không biên dịch**:

```java
int quantity;
try {
    quantity = Integer.parseInt(input);
} catch (NumberFormatException e) {
    System.out.println("Đầu vào sai");
}
System.out.println(quantity); // Variable quantity might not have been initialized
```

Đây là khung minh họa có biến `input` từ phạm vi bao ngoài. Vì handler có thể hoàn tất mà không gán `quantity`, câu lệnh cuối có thể đọc biến chưa khởi tạo. Việc `quantity` nằm đúng phạm vi **không làm cho nó được definite assigned**.

Một bản sửa tùy nhu cầu:

```java
int quantity;
try {
    quantity = Integer.parseInt(input);
} catch (NumberFormatException e) {
    throw new IllegalArgumentException("Số lượng phải là số nguyên", e);
}
System.out.println(quantity);
```

Đây vẫn là khung minh họa; đoạn sau `catch` chỉ được thực thi khi phép chuyển đổi thành công, vì handler ném exception mới thay vì hoàn tất bình thường. Trong cách viết này, `quantity` đã được definite assigned trên mọi đường có thể tới lệnh in. Nếu tầng giao tiếp cần xử lý lỗi nhập liệu như kết quả dự kiến, một cách khác là trả trạng thái xác thực thay vì chuyển nó thành exception mới.

Hoặc gán ở cả hai nhánh với ý nghĩa cụ thể:

```java
int quantity;
try {
    quantity = Integer.parseInt(input);
} catch (NumberFormatException e) {
    quantity = 0; // Chỉ đúng nếu 0 là fallback được hợp đồng cho phép.
}
System.out.println(quantity);
```

Không dùng `0` hoặc `-1` như mã lỗi tùy tiện nếu chúng có thể là giá trị hợp lệ; trường hợp này nên biểu diễn rõ thành công/thất bại.

### Vì sao Java nghiêm ngặt?

Biến cục bộ trong Java **không có giá trị mặc định** chỉ vì được khai báo. Trường (field) của một đối tượng có giá trị mặc định theo quy tắc khởi tạo của Java, nhưng **biến cục bộ trong phương thức thì phải được gán trước khi đọc**. Sự khác biệt này giúp compiler ngăn nhiều lỗi dùng dữ liệu chưa khởi tạo.

Nếu bạn biết chắc dữ liệu luôn parse thành công trong một thử nghiệm, compiler vẫn không suy luận rằng nhánh exception là bất khả thi cho mọi đầu vào runtime. Cách viết phải đúng theo những đường thực thi mà ngôn ngữ cho phép.

## 6. Scope của tham số `catch`

Trong:

```java
catch (NumberFormatException e) {
    System.out.println(e.getMessage());
}
```

`e` là **tham số của mệnh đề `catch`**, có kiểu khai báo `NumberFormatException`. Nó được khai báo bởi phần tham số của handler và **nằm trong scope của block handler ấy**. Nó không tồn tại như một biến có thể tham chiếu bằng tên từ thân `try`, từ `finally`, từ handler khác hoặc ở câu lệnh sau toàn bộ cấu trúc.

Ví dụ **cố ý không biên dịch**:

```java
try {
    Integer.parseInt(input);
} catch (NumberFormatException e) {
    System.out.println(e.getClass().getSimpleName());
} finally {
    System.out.println(e.getMessage()); // Không có e trong scope finally
}
System.out.println(e);                 // Không có e ở scope ngoài
```

Nếu cần đưa thông tin về lỗi cho code ở scope ngoài, có thể khai báo một biến ở scope ngoài và gán thông tin thích hợp, nhưng phải cân nhắc xem việc lưu error có làm rối hợp đồng không. Trong đa số trường hợp, hãy xử lý lỗi ngay trong handler hoặc để exception lan truyền.

**Tên `e` không bắt buộc**; có thể dùng `ex`, `cause`, `error`... miễn tuân thủ luật định danh Java và tên biến không xung đột trong các scope chồng lên nhau. Đặt tên giúp diễn đạt trách nhiệm sẽ hữu ích hơn việc cố chấp dùng một ký tự.

## 7. Tham số `catch` là đối tượng lỗi, không phải bản sao của đối tượng

Khi handler nhận `catch (SomeException e)`, biến `e` chứa **tham chiếu** tới đối tượng exception đã được ném. Java truyền tham chiếu theo giá trị khi truyền tham số; bản thân tham số handler cũng chỉ là tên cục bộ. Điều này quan trọng cho scope và việc ném lại:

- `throw e;` ném **cùng đối tượng exception** đang được `e` tham chiếu.
- Đổi tên `e` không đổi loại runtime của đối tượng.
- Nếu dùng một `catch` đơn loại và gán `e` sang đối tượng khác (việc này có thể hợp lệ ở một số ngữ cảnh), `throw e` sau đó sẽ ném đối tượng mới mà biến đang trỏ tới. Như vậy không còn là ném lại cùng lỗi gốc.
- Tham số `catch` hết scope khi kết thúc handler, nhưng đối tượng exception **không bắt buộc bị thu hồi ngay**. Nó có thể vẫn được tham chiếu bởi nơi khác, ví dụ một wrapper exception, cơ chế log, hoặc caller bắt lại.

Lưu `CatchReferenceDemo.java`:

```java
public class CatchReferenceDemo {
    static IllegalArgumentException original;

    static void run() {
        original = new IllegalArgumentException("Lỗi dữ liệu");
        try {
            throw original;
        } catch (IllegalArgumentException e) {
            System.out.println("Trong catch: " + (e == original));
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IllegalArgumentException outer) {
            System.out.println("Trong main: " + (outer == original));
            System.out.println("Message: " + outer.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CatchReferenceDemo.java
java CatchReferenceDemo
```

Stdout:

```text
Trong catch: true
Trong main: true
Message: Lỗi dữ liệu
```

Tên `e` trong handler trong và `outer` trong handler ngoài khác nhau, nhưng chúng có thể tham chiếu **cùng một instance**. Ví dụ dùng field `original` chỉ để kiểm tra identity; không nên tạo state toàn cục chứa “exception mới nhất” để giao tiếp giữa các thread trong chương trình thực.

## 8. Các handler `catch` cùng cấp có phạm vi riêng

Hai handler của cùng một câu lệnh `try` có thể dùng cùng tên tham số:

```java
try {
    potentiallyFails();
} catch (java.io.IOException e) {
    System.out.println("I/O: " + e.getMessage());
} catch (IllegalArgumentException e) {
    System.out.println("Input: " + e.getMessage());
}
```

Đây là khung minh họa, giả định `potentiallyFails()` khai báo/cho phép những loại lỗi tương ứng. Java cho phép hai tên `e` vì mỗi tên chỉ tồn tại trong scope của handler riêng.

Tuy nhiên, **không được tạo thêm một biến cùng tên `e` ngay trong thân handler** khi nó trùng với tham số đang có:

```java
try {
    Integer.parseInt("x");
} catch (NumberFormatException e) {
    String e = "bad"; // Lỗi biên dịch: e đã được định nghĩa tại scope này
}
```

Thay `String e` bằng tên `message` sẽ hợp lệ.

Một nhầm lẫn tương tự là cho rằng `catch` thứ hai có thể đọc biến cục bộ được khai báo trong `catch` thứ nhất. Không được, vì hai handler là hai scope độc lập.

## 9. Shadowing và xung đột tên với biến bao ngoài

Java cho phép một biến cục bộ hoặc tham số handler che khuất (**shadow**) một field có cùng tên trong một phạm vi gần hơn; nhưng không cho phép tùy tiện khai báo biến cục bộ mới trùng tên với một biến cục bộ đã còn trong phạm vi bao quanh.

### Trùng với biến cục bộ bao ngoài: lỗi biên dịch

```java
void demonstrate() {
    String e = "đã có";
    try {
        Integer.parseInt("x");
    } catch (NumberFormatException e) { // Không hợp lệ: e đã có ở outer local scope
        System.out.println(e);
    }
}
```

Đây là phương thức minh họa **cố ý không biên dịch**. Tham số `catch` gây xung đột với biến cục bộ `e` ở phạm vi bao ngoài vẫn đang hoạt động. Sửa bằng tên khác, chẳng hạn `catch (NumberFormatException cause)`.

### Trùng với field: có thể hợp lệ

Ví dụ hoàn chỉnh trong `FieldShadowDemo.java`:

```java
public class FieldShadowDemo {
    private String error = "field";

    void demonstrate() {
        try {
            Integer.parseInt("invalid");
        } catch (NumberFormatException error) {
            System.out.println("Catch: " + error.getClass().getSimpleName());
            System.out.println("Field: " + this.error);
        }
    }

    public static void main(String[] args) {
        new FieldShadowDemo().demonstrate();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 FieldShadowDemo.java
java FieldShadowDemo
```

Stdout:

```text
Catch: NumberFormatException
Field: field
```

Trong handler, tên `error` trỏ tới tham số `catch`. Trường `error` của đối tượng vẫn tồn tại và có thể truy cập bằng `this.error`. Đây là **shadowing field**, khác với khai báo trùng một biến local trong scope lồng nhau đang hoạt động.

Nguyên tắc thiết kế: đặt tên tham số handler rõ ràng để tránh nhầm với state của đối tượng; đừng dựa vào shadowing khi không cần thiết.

## 10. `catch` một loại và tính `final` / `effectively final`

Một tham số `catch` đơn loại như `catch (IOException e)` thường có thể được gán lại nếu không khai báo `final`. Tuy vậy, **gán lại tham số handler thường là cách viết khó hiểu**: nó đánh mất tên tham chiếu ban đầu, có thể phá tác dụng của phân tích *precise rethrow*, và làm khó chẩn đoán lỗi.

So sánh:

```java
catch (IllegalArgumentException e) {
    // e không bị gán lại: effectively final.
    throw e;
}
```

với:

```java
catch (IllegalArgumentException e) {
    e = new IllegalArgumentException("Lỗi đã bị thay");
    throw e; // Ném đối tượng mới, không còn giữ identity của lỗi ban đầu.
}
```

Đây là **hai đoạn handler minh họa riêng biệt**, không đặt liên tiếp như một chương trình độc lập. Tham số handler đầu là *effectively final* vì không có phép gán lại; trong handler thứ hai, `e` không còn effectively final.

Có thể yêu cầu bất biến bằng từ khóa `final`:

```java
catch (final IllegalArgumentException e) {
    System.out.println(e.getMessage());
    // e = new IllegalArgumentException(); // Không hợp lệ
}
```

Cần phân biệt **không gán lại biến tham chiếu** với **đối tượng bất biến**. `final` hoặc *effectively final* chỉ hạn chế việc biến `e` trỏ sang instance khác; các phương thức trên đối tượng exception vẫn có thể sửa những thuộc tính cho phép thay đổi, chẳng hạn `addSuppressed` hoặc `setStackTrace`.

## 11. Multi-catch: một tham số có nhiều kiểu và ngầm định `final`

Java hỗ trợ multi-catch:

```java
try {
    readOrParse();
} catch (java.io.IOException | IllegalArgumentException e) {
    System.out.println(e.getClass().getSimpleName());
}
```

Đây là khung minh họa; phương thức `readOrParse()` cần được định nghĩa để chương trình biên dịch. Ở đây có **một tham số `e`** nhưng nó có thể nhận exception thuộc một trong hai nhánh kiểu khai báo. Java áp dụng các quy tắc chung của một loại kiểu tổng hợp/kiểu hợp thích hợp để kiểm tra các lời gọi trên `e`.

Điểm đáng nhớ:

- Tham số trong multi-catch là **implicitly final**: không được gán lại `e`.
- Các loại ở dấu `|` không được có quan hệ cha–con trực tiếp/gián tiếp khiến một loại là subtype của loại còn lại; ví dụ `IOException | Exception` là không hợp lệ.
- Scope của `e` vẫn chỉ ở **thân handler multi-catch**.
- Tham số chỉ lưu một đối tượng exception cụ thể tại mỗi lần handler chạy, không đồng thời lưu hai đối tượng.

Ví dụ đầy đủ trong `MultiCatchScopeDemo.java`:

```java
import java.io.IOException;

public class MultiCatchScopeDemo {
    static void process(String input) throws IOException {
        if (input.equals("io")) {
            throw new IOException("Hỏng nguồn");
        }
        int value = Integer.parseInt(input);
        System.out.println("Số: " + value);
    }

    public static void main(String[] args) {
        for (String input : new String[] {"4", "io", "abc"}) {
            try {
                process(input);
            } catch (IOException | NumberFormatException e) {
                System.out.println("Bắt: " + e.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 MultiCatchScopeDemo.java
java MultiCatchScopeDemo
```

Stdout:

```text
Số: 4
Bắt: IOException
Bắt: NumberFormatException
```

Phạm vi `e` chấm dứt sau handler. Nếu thêm `e = new IOException("Khác")` trong multi-catch, chương trình bị từ chối tại compile time vì tham số này ngầm định là `final`.

## 12. Precise rethrow liên quan thế nào đến phạm vi và việc gán lại tham số `catch`?

Từ Java 7, khi tham số handler là `final` hoặc *effectively final*, trình biên dịch có thể thực hiện phân tích **precise rethrow**: dù tham số khai báo kiểu rộng như `Exception`, tập checked exception thực sự có thể ném lại bằng `throw e` được xác định hẹp hơn từ `try`.

Ví dụ hợp lệ trong `PreciseRethrowScopeDemo.java`:

```java
import java.io.IOException;

public class PreciseRethrowScopeDemo {
    static void read() throws IOException {
        throw new IOException("Không đọc được");
    }

    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            System.out.println("Trong catch");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Ở caller: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowScopeDemo.java
java PreciseRethrowScopeDemo
```

Stdout:

```text
Trong catch
Ở caller: Không đọc được
```

Dù bắt `catch (Exception e)`, phương thức `relay` chỉ cần `throws IOException` trong ví dụ này, vì `e` không bị gán lại và Java xác định checked exception có thể phát sinh từ thân `try` là `IOException`. Unchecked exception nếu có không bắt buộc khai báo.

Nếu gán lại `e` trong cùng handler, Java không thể áp dụng cùng quy tắc thu hẹp kiểu như trên. Chẳng hạn đoạn sau **cố ý không biên dịch** với chữ ký chỉ `throws IOException`:

```java
static void relayBad() throws IOException {
    try {
        throw new IOException("Lỗi gốc");
    } catch (Exception e) {
        e = new IOException("Lỗi khác");
        throw e; // Có thể bị kiểm tra theo kiểu rộng Exception.
    }
}
```

Ví dụ nhấn mạnh **scope và trạng thái gán lại của tham số handler ảnh hưởng nghĩa vụ checked exception ở compile time**. Đừng gán lại tham số `catch` khi mục tiêu là lan truyền nguyên bản; đặt một biến khác nếu thực sự cần đại diện cho một lỗi mới, và khai báo hợp đồng phù hợp.

## 13. `try-with-resources` có scope riêng cho resource

Trong `try-with-resources`, tài nguyên khai báo ở phần đầu câu lệnh `try` có phạm vi trong **khối thân `try`**, không thuộc scope của handler `catch`, `finally` gắn liền hoặc các lệnh sau cấu trúc.

Ví dụ **cố ý không biên dịch** nếu thêm các dòng comment thành mã:

```java
try (java.io.StringReader reader = new java.io.StringReader("abc")) {
    System.out.println(reader.read());
} catch (java.io.IOException e) {
    // reader.read(); // Không có reader trong scope catch.
}
// reader.read(); // Không có reader sau try-with-resources.
```

`reader` được khai báo tại resource specification, được khởi tạo trước khi vào thân `try` và được Java tự động đóng khi rời phạm vi tài nguyên. Tham số `e` của handler vẫn chỉ sống trong thân `catch`.

Một chương trình độc lập giúp thấy phạm vi và thứ tự đóng, lưu `ResourceScopeDemo.java`:

```java
public class ResourceScopeDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở: " + name);
        }

        String read() {
            return "Dữ liệu từ " + name;
        }

        @Override
        public void close() {
            System.out.println("Đóng: " + name);
        }
    }

    public static void main(String[] args) {
        String result = "Chưa có dữ liệu";

        try (Resource resource = new Resource("A")) {
            result = resource.read();
            System.out.println("Trong try: " + result);
            throw new IllegalStateException("Lỗi sau khi đọc");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally");
        }

        System.out.println("Result ngoài: " + result);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ResourceScopeDemo.java
java ResourceScopeDemo
```

Stdout:

```text
Mở: A
Trong try: Dữ liệu từ A
Đóng: A
Catch: Lỗi sau khi đọc
Finally
Result ngoài: Dữ liệu từ A
```

Ở nhánh thành công của việc mở và đọc tài nguyên, `result` được gán trước lệnh `throw`. Tuy nhiên constructor hoặc `read()` vẫn có thể thất bại trước phép gán rồi đi vào `catch`; khởi tạo `result` với giá trị dự phòng giúp chương trình đáp ứng quy tắc **definite assignment**. Tài nguyên `resource` bị đóng **trước** khi handler được thực thi. Scope của `resource` không mở rộng ra handler, nhưng biến `result` được khai báo ở khối ngoài nên vẫn thấy ở cuối.

**Scope và cleanup là hai khái niệm độc lập:** một resource hết scope sau `try`, nhưng việc gọi `close()` có thời điểm cụ thể do `try-with-resources` quản lý. Một đối tượng đã đóng vẫn có thể được tham chiếu từ nơi khác nếu tham chiếu được giữ lại; điều đó không có nghĩa nó còn sử dụng tài nguyên được phép.

## 14. `try-with-resources` dùng biến đã khai báo trước (Java 9+)

Từ Java 9, resource specification có thể nhận một biến đã được khai báo ngoài `try`, nếu biến ấy là `final` hoặc *effectively final* và kiểu triển khai `AutoCloseable`. Khi đó, **phạm vi tên biến vẫn là scope nơi nó được khai báo ban đầu**.

Ví dụ Java 17 độc lập, lưu `ExistingResourceDemo.java`:

```java
public class ExistingResourceDemo {
    static class Resource implements AutoCloseable {
        private boolean closed;

        String read() {
            if (closed) {
                throw new IllegalStateException("Đã đóng");
            }
            return "ok";
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("Đang đóng");
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            System.out.println(resource.read());
        }

        System.out.println("Có thể gọi tên resource: " + resource.isClosed());
    }
}
```

Chạy:

```bash
javac --release 17 ExistingResourceDemo.java
java ExistingResourceDemo
```

Stdout:

```text
ok
Đang đóng
Có thể gọi tên resource: true
```

Biến `resource` được khai báo trước `try`, vì vậy tên vẫn trong scope sau cấu trúc, nhưng đối tượng đã được đóng. Điều kiện *effectively final* yêu cầu không gán lại biến `resource` sau khi gán ban đầu; nếu viết `resource = new Resource()` sau đó, compiler sẽ từ chối sử dụng `resource` theo dạng `try (resource)` này.

Từ Java 9, dạng truyền biến tồn tại này là cú pháp hợp lệ. Đối với Java 7/8, cú pháp quen thuộc là khai báo resource ngay trong phần `try (...)`, hoặc dùng một khai báo biến resource mới phù hợp với ngôn ngữ phiên bản đó.

## 15. Scope của `finally` và biến được chia sẻ

`finally` là một khối riêng. Nó không được quyền truy cập biến local khai báo bên trong `try` hoặc tham số `catch`, nhưng có thể truy cập biến ở scope bao ngoài.

```java
int attempts = 0;

try {
    attempts++;
    execute();
} catch (RuntimeException e) {
    System.out.println("Lỗi: " + e.getMessage());
} finally {
    System.out.println("Số lần thử: " + attempts);
}
```

Đây là mã minh họa, `execute()` chưa được định nghĩa. `attempts` nằm ở scope bao ngoài và đã có giá trị ban đầu, nên `finally` có thể đọc. Còn nếu viết `int attempts = 0;` **chỉ bên trong `try`**, `finally` không được quyền gọi tên biến ấy.

Nếu chỉ cần cleanup resource, ưu tiên `try-with-resources` với các đối tượng `AutoCloseable`. Nếu dùng `finally` cho việc khác, hạn chế `return` hoặc ném exception mới trong đó vì có thể ghi đè kết quả hoặc che exception đang lan truyền.

Không thể suy luận rằng có biến nhìn thấy trong `finally` là có giá trị đúng: nếu trạng thái chỉ được cập nhật ở giữa `try` rồi exception xảy ra trước đó, `finally` phải chịu được trạng thái cập nhật một phần.

## 16. Tham số `catch` và lambda: quy tắc biến được capture

Java cho phép lambda hoặc anonymous class sử dụng biến local từ phạm vi bao ngoài khi biến đó là `final` hoặc *effectively final*. Tham số `catch` cũng tuân thủ cơ chế này. Handler có thể tạo lambda sử dụng `e`, miễn là không gán lại `e` khi nó được capture.

Ví dụ hoàn chỉnh, lưu `CatchLambdaDemo.java`:

```java
public class CatchLambdaDemo {
    public static void main(String[] args) {
        Runnable report;

        try {
            Integer.parseInt("wrong");
            report = () -> System.out.println("Không có lỗi");
        } catch (NumberFormatException e) {
            report = () -> System.out.println(
                    "Lambda đọc: " + e.getClass().getSimpleName());
        }

        report.run();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 CatchLambdaDemo.java
java CatchLambdaDemo
```

Stdout:

```text
Lambda đọc: NumberFormatException
```

`report` được khai báo ở scope ngoài và gán trong các nhánh. Lambda được tạo bên trong `catch` có quyền capture tham số `e` khi `e` là effectively final. **Kết thúc scope `catch` không khiến đối tượng ngoại lệ tự bị hủy**: lambda có thể giữ tham chiếu cần dùng khi chạy sau đó.

Đây là lý do cần cân nhắc khi giữ lambda hoặc callback lâu dài: một exception có stack trace, cause và dữ liệu ngữ cảnh; việc capture có thể giữ nó trong bộ nhớ lâu hơn mong muốn hoặc vô tình làm lộ nội dung nếu chuyển qua các tầng không phù hợp.

Nếu gán lại `e` trong handler mà cũng muốn capture nó, compiler sẽ báo lỗi vì biến được capture không còn effectively final. Cách rõ hơn là giữ `e` nguyên trạng và, nếu cần, capture một chuỗi message hoặc mã lỗi đã được xử lý.

## 17. Scope không phải lúc nào cũng là “vòng đời đối tượng”

Một hiểu nhầm phổ biến: sau khi rời `catch`, vì tên `e` không còn trong scope, đối tượng exception cũng nhất định biến mất. Java không hoạt động như vậy.

- **Lexical scope** của tên `e` kết thúc tại đóng ngoặc của handler.
- **Reference reachability** của đối tượng exception phụ thuộc việc có nơi khác vẫn giữ tham chiếu hay không.
- Bộ thu gom rác (GC) chỉ có thể thu hồi những đối tượng không còn reachable theo các quy tắc của JVM; không có thời điểm thu hồi chính xác bảo đảm ngay khi thoát một khối.
- Nếu ném lại cùng đối tượng bằng `throw e`, caller có thể bắt được chính instance đó.
- Nếu bọc ngoại lệ bằng `new IllegalStateException("...", e)`, wrapper giữ `e` ở `cause`; exception gốc có thể tiếp tục sống theo vòng đời wrapper.
- Nếu capture `e` trong lambda được lưu lại, object có thể còn reachable dù handler đã kết thúc.

Đây là sự khác nhau giữa **tên biến có thể truy cập ở đâu** và **dữ liệu còn được tham chiếu ở đâu**. Tương tự, đóng resource không đồng nghĩa xóa ngay đối tượng Java chứa resource.

## 18. Phạm vi và xử lý ngoại lệ khi có vòng lặp

Biến khai báo trong thân vòng lặp hoặc trong `try` của mỗi lượt lặp có scope theo cấu trúc lặp. Biến ngoài vòng lặp có thể tích lũy kết quả.

Ví dụ `LoopScopeDemo.java`:

```java
public class LoopScopeDemo {
    public static void main(String[] args) {
        int validCount = 0;

        for (String text : new String[] {"2", "bad", "5"}) {
            try {
                int number = Integer.parseInt(text);
                System.out.println("Giá trị: " + number);
                validCount++;
            } catch (NumberFormatException e) {
                System.out.println("Bỏ qua: " + text);
            }
        }

        System.out.println("Hợp lệ: " + validCount);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 LoopScopeDemo.java
java LoopScopeDemo
```

Stdout:

```text
Giá trị: 2
Bỏ qua: bad
Giá trị: 5
Hợp lệ: 2
```

`number` chỉ ở trong khối `try` của mỗi lượt; `e` chỉ trong handler của lần lỗi tương ứng; `text` được khai báo ở phần enhanced `for` và nhìn thấy trong cả `try` và `catch` bên trong thân vòng lặp; `validCount` nằm ngoài vòng lặp nên dùng được sau đó.

Nếu một exception bị bắt **bên ngoài toàn bộ vòng lặp**, vòng lặp bị thoát khi exception lan tới handler ngoài; Java không tự quay lại phần tử tiếp theo. Đặt `try/catch` ở đúng vị trí giúp biến và phạm vi xử lý phản ánh chủ ý: xử lý lỗi từng phần tử hay hủy cả đợt.

## 19. Mẫu thiết kế rõ ràng: đưa dữ liệu thành kết quả thay vì chia sẻ biến không an toàn

Không phải mọi xử lý lỗi đều nên cố tạo biến chung giữa `try` và `catch`. Nếu dữ liệu thực sự chỉ tồn tại khi thành công, có thể biểu diễn **kết quả có trạng thái**.

Java 17 hỗ trợ `record` và `sealed interface`, hữu ích cho ví dụ này. Lưu `ParseResultDemo.java`:

```java
public class ParseResultDemo {
    sealed interface ParseResult permits Success, Invalid {
    }

    record Success(int value) implements ParseResult {
    }

    record Invalid(String reason) implements ParseResult {
    }

    static ParseResult parse(String input) {
        try {
            int number = Integer.parseInt(input);
            return new Success(number);
        } catch (NumberFormatException e) {
            return new Invalid("Không phải số nguyên");
        }
    }

    static void describe(String input) {
        ParseResult result = parse(input);

        if (result instanceof Success success) {
            System.out.println("OK: " + success.value());
        } else if (result instanceof Invalid invalid) {
            System.out.println("Sai: " + invalid.reason());
        }
    }

    public static void main(String[] args) {
        describe("10");
        describe("x");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ParseResultDemo.java
java ParseResultDemo
```

Stdout:

```text
OK: 10
Sai: Không phải số nguyên
```

Dữ liệu `number` nằm ở `try` của phương thức parse, chỉ được chuyển sang `Success` khi parse thành công. Handler không cần gọi tên biến `number` vì chẳng có giá trị thành công hợp lệ nào được tạo trên đường lỗi. Bên ngoài, `result` là một giá trị luôn được trả về theo hợp đồng; kiểm tra kiểu quyết định sử dụng đúng nhánh.

Những biến pattern `success` và `invalid` cũng có phạm vi do **flow scoping** của pattern matching quy định, nhưng đây là cơ chế riêng của Java 17. Nó không mở rộng phạm vi của biến trong `try` hay tham số `catch`. Ví dụ chọn `if/else if` để người đọc thấy rõ mỗi giá trị chỉ được sử dụng sau khi kiểm tra kiểu thích hợp.

## 20. Các lỗi biên dịch thường gặp và cách sửa

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `cannot find symbol: variable x` khi đọc từ `catch` | `x` khai báo chỉ trong `try` | Đưa khai báo ra scope ngoài nếu thật sự cần hoặc xử lý `x` trong `try` |
| `variable x might not have been initialized` | `x` có scope đúng nhưng có đường đi không gán | Gán ở mọi đường bình thường, return/throw sớm, hoặc mô hình hóa kết quả rõ ràng |
| `variable e is already defined` | Tạo biến local `e` trùng tham số handler hoặc outer local | Đổi tên để không chồng scope |
| `multi-catch parameter e may not be assigned` | Gán lại tham số `catch (A \| B e)` | Không gán lại; tạo biến khác nếu cần |
| `local variables referenced from a lambda expression must be final or effectively final` | Capture tham số/biến đã bị gán lại | Giữ tham số effectively final hoặc capture giá trị khác |
| `unreported exception ... must be caught or declared to be thrown` | Một checked exception (kể cả khi `throw e`) chưa được xử lý/khai báo | Bắt phù hợp hoặc thêm `throws` theo hợp đồng |
| Handler không nhìn thấy resource đã khai báo trong `try (...)` | Resource specification tạo scope chỉ trong thân `try` | Dùng dữ liệu trước khi ra khỏi khối hoặc khai báo tham chiếu outer nếu thực sự cần |
| Cần dùng exception sau handler nhưng tên `e` mất | `e` chỉ trong scope handler | Xử lý trong handler, ném lại, hoặc chuyển thông tin ra ngoài bằng giá trị có kiểu phù hợp |

**Không nên “sửa” mọi lỗi scope bằng cách khai báo biến thành field hoặc `static`.** Điều đó mở rộng thời gian sống và chia sẻ state, có thể gây tranh chấp khi đa luồng và khó kiểm thử. Giữ phạm vi nhỏ nhất đáp ứng nhu cầu thực tế.

## 21. Lưu ý về ngoại lệ và đường đi thực thi khi phân tích biến

Compiler phân tích phạm vi biến **theo cấu trúc từ vựng của mã**, còn việc exception làm thay đổi điểm tiếp tục thực thi là **control flow**. Hai lớp quy tắc tương tác nhưng không thể thay thế nhau.

Ví dụ, nếu `try` gọi một phương thức có thể ném exception **trước** lệnh gán, nhánh `catch` có thể chạy khi biến outer chưa nhận giá trị. Nếu `catch` gán một fallback hợp lệ, biến mới trở thành definitely assigned sau toàn bộ cấu trúc. Nếu handler kết thúc bằng `return` hoặc `throw`, Java biết không có đường bình thường đi qua handler đó tới lệnh đọc biến.

Một sai lầm khác là đặt code đọc kết quả sau handler chỉ vì “lúc nào cũng có kết quả”. Nếu một lời gọi thất bại giữa chừng, **không thể coi dữ liệu trước lỗi là kết quả hoàn chỉnh**. Cần đảm bảo tính nhất quán của side effect, hợp đồng trả về và trạng thái chương trình, ngoài việc thoả compiler.

Cũng không nhầm checked exception với biến scope: `IOException` được khai báo bằng `throws` là vấn đề về **hợp đồng ném lỗi**, còn `cannot find symbol` với biến trong `try` là vấn đề **phạm vi tên**. Thêm `throws` không mở rộng scope biến.

## 22. Bài tập tự kiểm tra

**Câu 1.** Biến `x` khai báo trong `try` có được gọi tên trong `catch` gắn với `try` đó không?  
**Đáp án:** Không. Hai thân khối khác nhau; `x` chỉ nằm trong scope của thân `try`.

**Câu 2.** Biến `result` khai báo trước `try` nhưng chỉ gán khi parse thành công. Nếu `catch` chỉ in lỗi rồi kết thúc bình thường, có đọc `result` ở sau cấu trúc được không?  
**Đáp án:** Không chắc. Compiler có thể báo chưa được gán vì đường handler vẫn có thể tới chỗ đọc. Cần xử lý tất cả đường đi hoặc return/throw khỏi nhánh lỗi.

**Câu 3.** Hai nhánh `catch` khác nhau có thể đều dùng tham số tên `e` không?  
**Đáp án:** Có. Scope của các tham số thuộc hai handler riêng biệt.

**Câu 4.** Có thể khai báo `String e` bên trong handler đã có tham số `catch (IOException e)` không?  
**Đáp án:** Không. Đó là xung đột khai báo trong phạm vi đã có `e`.

**Câu 5.** Tham số multi-catch có thể gán lại không?  
**Đáp án:** Không. Tham số của multi-catch là implicitly final.

**Câu 6.** `catch (Exception e) { throw e; }` có luôn buộc khai báo `throws Exception` không?  
**Đáp án:** Không. Với tham số final/effectively final, Java có thể dùng precise rethrow để xác định tập checked exception hẹp hơn từ thân `try`.

**Câu 7.** Resource khai báo trong `try (Resource r = ...)` có nhìn thấy trong `catch` trực tiếp gắn với cấu trúc không?  
**Đáp án:** Không. Resource specification giới hạn scope của `r` trong thân `try`.

**Câu 8.** Với `Resource r = new Resource(); try (r) {...}` trên Java 17, có thể gọi tên `r` ở sau `try` không?  
**Đáp án:** Có, vì `r` được khai báo ngoài `try`. Tuy nhiên resource đã được cố đóng khi rời khối.

**Câu 9.** Từ khóa `final` trên tham số `catch` có làm object exception bất biến tuyệt đối không?  
**Đáp án:** Không. Nó cấm gán lại tham số, chứ không ngăn các phương thức hợp lệ sửa thuộc tính của đối tượng.

**Câu 10.** Nếu lambda được tạo trong `catch` giữ tham chiếu `e` và chạy sau handler, liệu có vi phạm scope không?  
**Đáp án:** Không, nếu `e` được capture hợp lệ (final/effectively final). Lambda giữ tham chiếu object; việc tên `e` hết scope ở mã ngoài handler không làm lambda mất tham chiếu đã capture.

## 23. Checklist khi viết `try/catch`

Trước khi hoàn tất một phương thức xử lý exception, hãy rà soát:

1. **Tên biến được khai báo ở scope nào?** Chỉ đưa khai báo ra ngoài `try` khi các nhánh thực sự cần cùng biến.
2. **Có dùng biến trong `catch`/`finally` mà nó chỉ thuộc `try` không?** Nếu có, chỉnh lại cấu trúc dữ liệu.
3. **Biến outer được gán trên mọi đường đi bình thường chưa?** Xét cả exception xảy ra trước phép gán và việc handler hoàn tất.
4. **Tham số `catch` có trùng tên local ngoài hoặc biến trong handler không?** Tránh xung đột scope.
5. **Có gán lại tham số handler không?** Giữ nguyên exception gốc khi ném lại và bảo toàn khả năng precise rethrow.
6. **Multi-catch có đúng luật kiểu và final không?** Không gán lại tham số, không ghép hai loại có quan hệ cha–con.
7. **Resource có được dùng trong phạm vi hợp lệ không?** Nhớ rằng resource khai báo tại `try (...)` không nhìn thấy ở `catch` và được tự đóng.
8. **Lambda có capture biến hợp lệ không?** Kiểm tra final/effectively final và nguy cơ giữ tham chiếu dài hạn.
9. **Có dùng kết quả chưa hoàn chỉnh sau đường thất bại không?** Đảm bảo trạng thái và ý nghĩa nghiệp vụ, không chỉ khả năng biên dịch.
10. **Ví dụ và test có bao phủ cả đường thành công lẫn đường lỗi không?** Đây là cách tốt nhất để xác nhận nhánh scope/assignment được hiểu chính xác.

## 24. Ghi nhớ

**Trong Java, thân `try`, từng thân `catch` và thân `finally` là các phạm vi biến riêng.** Biến khai báo trong `try` không gọi được ở `catch`; tham số `catch` chỉ gọi được trong handler tương ứng; biến khai báo trước cấu trúc có thể xuất hiện ở các khối con và ở phía sau, miễn tuân thủ **definite assignment**.

Với multi-catch, tham số handler ngầm định là `final`. Với catch một loại, giữ tham số *effectively final* là thực hành tốt để bảo toàn identity và hỗ trợ **precise rethrow**. `try-with-resources` có quy tắc scope của resource riêng; trường hợp sử dụng biến đã khai báo trước (`try (resource)`, Java 9+) cần phân biệt scope của tên với việc tài nguyên đã đóng.

Hãy giữ biến ở **phạm vi nhỏ nhất có ý nghĩa**, gán rõ trên những đường đi có thể tiếp tục, và không biến thất bại thành dữ liệu thành công giả chỉ để giải quyết lỗi scope. Cách nghĩ đó giúp mã `try/catch` vừa biên dịch đúng vừa phản ánh trung thực luồng xử lý ngoại lệ.
