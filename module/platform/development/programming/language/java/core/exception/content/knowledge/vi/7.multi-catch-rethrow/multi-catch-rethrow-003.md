# Không đặt kiểu cha và kiểu con trong cùng multi-catch của Java

Trong Java, một nhánh **multi-catch** cho phép nhiều loại ngoại lệ dùng chung một phần xử lý:

~~~java
try {
    performOperation();
} catch (IOException | SQLException ex) {
    handleFailure(ex);
}
~~~

Đây là **đoạn minh họa**; `performOperation()` và `handleFailure(...)` cần được định nghĩa phù hợp. Dấu `|` giữa các kiểu ngoại lệ có nghĩa là “bắt một trong các loại được liệt kê”. Tuy nhiên, **không được liệt kê cùng lúc một kiểu cha và một kiểu con của nó trong cùng một multi-catch**:

~~~java
// KHÔNG HỢP LỆ: FileNotFoundException là lớp con của IOException.
catch (FileNotFoundException | IOException ex) {
    // ...
}
~~~

Đây là lỗi **biên dịch**, không phải lỗi chỉ phát sinh khi chạy. Nếu chỉ cần xử lý toàn bộ họ ngoại lệ theo một cách, hãy **bắt một kiểu cha duy nhất**. Nếu cần phân biệt cách xử lý loại cụ thể và loại tổng quát, hãy **dùng các `catch` riêng biệt, kiểu con đứng trước kiểu cha**. Nếu hai kiểu không kế thừa nhau và dùng chung logic xử lý, **multi-catch là lựa chọn hợp lệ**.

Bài học này trình bày quy tắc, lý do, cách xác định quan hệ kế thừa, cách sửa những lỗi thường gặp, tác động đến việc ném lại ngoại lệ và các ví dụ Java 17+ đã biên dịch/chạy kiểm chứng.

## 1. Nhắc lại: multi-catch dùng để làm gì?

Từ Java 7, một `catch` có thể liệt kê nhiều kiểu ngoại lệ độc lập bằng dấu `|` nếu cùng dùng một thân xử lý:

~~~java
try {
    performOperation();
} catch (java.io.IOException | java.sql.SQLException ex) {
    System.err.println(ex.getMessage());
}
~~~

Đây là đoạn minh họa cần `performOperation()` khai báo các checked exception tương ứng. Một ngoại lệ chỉ kích hoạt **một** handler phù hợp; dấu `|` không tạo nhiều biến hay nhiều lượt xử lý. Với bài này, trọng tâm không phải học lại cú pháp mà là **quan hệ subtype**: dù `A` và `B` đều thuộc `Exception`, một `catch (A | B e)` bị từ chối khi `A` kế thừa `B` hoặc ngược lại.

## 2. Vì sao không được ghép kiểu cha và kiểu con?

Xét phân cấp quen thuộc:

~~~text
java.lang.Exception
└── java.io.IOException
    ├── java.io.FileNotFoundException
    ├── java.io.EOFException
    ├── java.nio.file.FileSystemException
    │   └── java.nio.file.AccessDeniedException
    └── ...
~~~

`FileNotFoundException` là lớp con của `IOException`, tức:

~~~java
// Một FileNotFoundException cũng là một IOException.
IOException error = new java.io.FileNotFoundException("thiếu tệp");
~~~

Nếu một nhánh `catch` đã bắt `IOException`, nó **đương nhiên bắt được** mọi `FileNotFoundException` (và các lớp con khác của `IOException`) phát sinh từ phạm vi `try` đang bảo vệ. Do đó đoạn:

~~~java
// KHÔNG BIÊN DỊCH.
catch (FileNotFoundException | IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

chứa một lựa chọn **thừa về mặt bao phủ kiểu**. Java quy định các lựa chọn trong một multi-catch phải độc lập xét theo quan hệ kế thừa: không được có kiểu nào là lớp con của kiểu còn lại. Đảo thứ tự thành `IOException | FileNotFoundException` **vẫn sai**.

Quy tắc áp dụng cho **quan hệ kế thừa trực tiếp lẫn gián tiếp**. Ví dụ, `AccessDeniedException` là lớp con gián tiếp của `IOException` qua `FileSystemException`, nên `IOException | AccessDeniedException` cũng không hợp lệ.

Vì vậy, việc kiểm tra không chỉ nhìn hai tên có giống nhau hay không; phải đối chiếu **quan hệ subtype trong cây `Throwable`**.

## 3. Ví dụ biên dịch thất bại và cách đọc thông báo của `javac`

Tệp `InvalidMultiCatch.java` dưới đây được viết cố ý để minh họa lỗi; **không thể biên dịch thành chương trình chạy**:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

class InvalidMultiCatch {
    static void run() {
        try {
            throw new FileNotFoundException("missing");
        } catch (FileNotFoundException | IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InvalidMultiCatch.java
~~~

`javac` của JDK hiện đại báo lỗi chứa các dòng như:

~~~text
error: Alternatives in a multi-catch statement cannot be related by subclassing
Alternative FileNotFoundException is a subclass of alternative IOException
~~~

Vị trí dấu mũ trong thông báo thường trỏ đến một lựa chọn trong danh sách `catch`; đường dẫn, số dòng và trình bày lỗi phụ thuộc môi trường. Trọng tâm là: **một lựa chọn là lớp con của lựa chọn khác trong cùng multi-catch**.

Đây không phải lỗi vì `try` chỉ phát sinh một ngoại lệ hoặc vì các nhánh `catch` sai thứ tự. Ngay cả khi `try` thật sự có thể phát sinh cả `IOException` và `FileNotFoundException`, kiểu con vẫn đã được kiểu cha bao phủ, nên không được viết cả hai như những lựa chọn cùng cấp trong multi-catch.

## 4. Cách sửa thứ nhất: bắt một kiểu cha khi dùng chung cách xử lý

Nếu tất cả lỗi trong họ `IOException` đều cần cùng một cách xử lý, hãy viết:

~~~java
import java.io.IOException;

// Đoạn minh họa nằm trong phương thức phù hợp.
try {
    readData();
} catch (IOException ex) {
    System.err.println("Không đọc được dữ liệu: " + ex.getMessage());
}
~~~

`catch (IOException ex)` bắt được `FileNotFoundException`, `EOFException` và mọi lớp con của `IOException` phát sinh trong phạm vi `try`. Không cần viết:

~~~java
// Sai:
catch (IOException | FileNotFoundException | EOFException ex) {
    // ...
}
~~~

Ưu điểm của một `catch (IOException)` là đơn giản, không lặp lại kiểu con. Đổi lại, nó có thể **bắt cả những ngoại lệ I/O khác** ngoài hai loại bạn ban đầu muốn xử lý, như `AccessDeniedException`. Nếu các loại đó cần hành vi khác, nên chọn cách xử lý tách nhánh trong phần tiếp theo.

Không vì mục đích sửa lỗi cú pháp mà tự động mở rộng lên `catch (Exception)` hoặc `catch (Throwable)`: kiểu rộng hơn có thể che các lỗi bạn không định xử lý. Hãy chọn kiểu cha **đủ hẹp so với hợp đồng và cách phục hồi dự kiến**.

## 5. Cách sửa thứ hai: dùng các `catch` riêng khi cần xử lý khác nhau

Nếu muốn xử lý `FileNotFoundException` riêng và dành xử lý tổng quát cho các `IOException` còn lại, hãy dùng **hai nhánh `catch` riêng**:

~~~java
try {
    readData();
} catch (FileNotFoundException ex) {
    System.err.println("Hãy kiểm tra đường dẫn tệp.");
} catch (IOException ex) {
    System.err.println("Lỗi I/O khác: " + ex.getMessage());
}
~~~

Đây là **đoạn minh họa**, cần các `import` và phương thức `readData()` phù hợp. Cách viết này hợp lệ vì Java kiểm tra các nhánh **theo thứ tự**, từ trên xuống dưới. Nếu lỗi thực sự là `FileNotFoundException`, nó vào nhánh đầu; nếu là một `IOException` khác, nó đến nhánh thứ hai.

**Phải đặt kiểu con trước kiểu cha**. Viết ngược:

~~~java
// KHÔNG HỢP LỆ: nhánh sau không thể bắt thêm gì.
try {
    readData();
} catch (IOException ex) {
    System.err.println("I/O");
} catch (FileNotFoundException ex) {
    System.err.println("Thiếu tệp");
}
~~~

sẽ khiến `catch (FileNotFoundException)` bị xem là không thể tới, bởi `catch (IOException)` trước đó đã bao phủ kiểu con.

Lưu ý quan trọng: **quy tắc multi-catch và quy tắc nhiều catch riêng không giống nhau về cách sửa**:

- **Trong cùng một multi-catch:** `catch (FileNotFoundException | IOException ex)` **không hợp lệ ở bất kỳ thứ tự nào**.
- **Trong hai `catch` riêng:** `catch (FileNotFoundException)` rồi `catch (IOException)` **hợp lệ**, nhờ ưu tiên xử lý loại cụ thể trước.
- **Hai `catch` riêng theo thứ tự ngược:** `catch (IOException)` rồi `catch (FileNotFoundException)` **không hợp lệ** vì nhánh cụ thể bị che.

## 6. Ví dụ Java 17+ hoàn chỉnh: xử lý kiểu con trước kiểu cha

Tạo tệp `HierarchyCatchDemo.java`:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

public class HierarchyCatchDemo {
    static void load(boolean missing) throws IOException {
        if (missing) {
            throw new FileNotFoundException("thiếu tài liệu");
        }
        throw new IOException("lỗi đọc chung");
    }

    public static void main(String[] args) {
        for (boolean missing : new boolean[] {true, false}) {
            try {
                load(missing);
            } catch (FileNotFoundException ex) {
                System.out.println("Thiếu tệp: " + ex.getMessage());
            } catch (IOException ex) {
                System.out.println("I/O tổng quát: " + ex.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 HierarchyCatchDemo.java
java HierarchyCatchDemo
~~~

Stdout chính xác:

~~~text
Thiếu tệp: thiếu tài liệu
I/O tổng quát: lỗi đọc chung
~~~

Phân tích:

1. Trong lượt đầu, `load(true)` ném `FileNotFoundException`. Nhánh cụ thể bắt lỗi, nhánh tổng quát không chạy.
2. Lượt tiếp theo, `load(false)` ném một đối tượng `IOException`. Nhánh đầu không phù hợp; nhánh thứ hai xử lý.
3. Hai nhánh có thể dùng thông điệp và phương án phục hồi khác nhau. Nếu chúng hoàn toàn giống nhau, có thể thay cả hai bằng một `catch (IOException)`.

Đừng nhầm `throws IOException` trong chữ ký `load` với kiểu runtime của ngoại lệ thực tế. Chữ ký khai báo kiểu lỗi có thể truyền ra; `catch` lựa chọn nhánh dựa trên **đối tượng thực tế** khi chạy.

## 7. Cách sửa thứ ba: multi-catch những kiểu cùng nhánh nhưng không kế thừa nhau

Hai kiểu **cùng có cha là `IOException`** không có nghĩa một kiểu là con của kiểu kia. Chẳng hạn `FileNotFoundException` và `EOFException` đều là lớp con của `IOException`, nhưng **không có quan hệ kế thừa trực tiếp hoặc gián tiếp giữa hai kiểu ấy**. Chúng có thể đứng cùng một multi-catch:

~~~java
catch (FileNotFoundException | EOFException ex) {
    System.err.println("Nhóm lỗi tệp đặc biệt: " + ex.getMessage());
}
~~~

Bạn có thể thêm `catch (IOException ex)` **ở một nhánh riêng phía sau** để xử lý các lỗi I/O còn lại. Cấu trúc này phù hợp khi hai loại cụ thể cần một cách xử lý chung, nhưng các loại I/O khác lại cần cách xử lý khác.

Ví dụ hoàn chỉnh `MultiCatchSiblingsDemo.java`:

~~~java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class MultiCatchSiblingsDemo {
    static void load(String mode) throws IOException {
        switch (mode) {
            case "missing" -> throw new FileNotFoundException("thiếu tệp");
            case "ended" -> throw new EOFException("hết dữ liệu");
            case "denied" -> throw new IOException("không có quyền");
            default -> System.out.println("Đọc thành công");
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {"missing", "ended", "denied", "ok"}) {
            try {
                load(mode);
            } catch (FileNotFoundException | EOFException ex) {
                System.out.println("Nhóm cụ thể: " + ex.getClass().getSimpleName()
                        + " - " + ex.getMessage());
            } catch (IOException ex) {
                System.out.println("I/O khác: " + ex.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MultiCatchSiblingsDemo.java
java MultiCatchSiblingsDemo
~~~

Stdout chính xác:

~~~text
Nhóm cụ thể: FileNotFoundException - thiếu tệp
Nhóm cụ thể: EOFException - hết dữ liệu
I/O khác: không có quyền
Đọc thành công
~~~

Tại sao được phép?

- Hai lựa chọn `FileNotFoundException` và `EOFException` không có quan hệ kiểu cha–kiểu con với nhau.
- `catch (IOException)` là **nhánh riêng tiếp theo**, không phải lựa chọn `| IOException` trong nhánh multi-catch trước.
- Nếu `load` ném `FileNotFoundException` hay `EOFException`, chúng đi vào multi-catch đầu.
- Nếu `load` ném một `IOException` không khớp hai kiểu cụ thể, nó được xử lý ở nhánh `catch (IOException)` tiếp theo.
- Với `"ok"`, `load` hoàn thành bình thường nên các `catch` không chạy.

Ví dụ dùng `switch` expression-style arrow trong câu lệnh `switch`, tương thích Java 17. Những lỗi trong chương trình là ngoại lệ chủ động ném để kết quả minh họa ổn định; chúng không phụ thuộc vào một tệp thật có tồn tại hay không.

## 8. Các cặp kiểu: hợp lệ hay không?

| Các lựa chọn trong cùng `catch (... | ... ex)` | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `IOException | SQLException` | Có | Hai lớp ngoại lệ không kế thừa nhau. |
| `FileNotFoundException | EOFException` | Có | Cùng nhánh `IOException`, nhưng là hai nhánh con độc lập. |
| `IllegalArgumentException | IllegalStateException` | Có | Cùng nhánh `RuntimeException`, không phải lớp con của nhau. |
| `IOException | RuntimeException` | Có | Hai loại thuộc hai nhánh khác nhau của `Exception`. |
| `IOException | FileNotFoundException` | Không | `FileNotFoundException` kế thừa `IOException`. |
| `Exception | IOException` | Không | `IOException` kế thừa `Exception`. |
| `RuntimeException | IllegalArgumentException` | Không | `IllegalArgumentException` kế thừa `RuntimeException`. |
| `IllegalArgumentException | NumberFormatException` | Không | `NumberFormatException` kế thừa `IllegalArgumentException`. |
| `Throwable | Error` | Không | `Error` kế thừa `Throwable`. |
| `IOException | AccessDeniedException` | Không | `AccessDeniedException` là lớp con gián tiếp của `IOException`. |

Một cặp **không có quan hệ subtype** mới chỉ thỏa quy tắc về các lựa chọn của multi-catch. Toàn bộ câu lệnh còn phải thỏa quy tắc khác, ví dụ `try` có thể phát sinh những checked exception được bắt, thứ tự các nhánh trong cấu trúc lớn hơn và khả năng truy cập các kiểu/import.

Do đó, “hợp lệ” trong bảng có nghĩa **không vi phạm quy tắc quan hệ kế thừa của multi-catch**, không phải bất kỳ chương trình nào chứa cặp này cũng chắc chắn biên dịch.

## 9. `catch` chỉ xét kiểu runtime, không chọn theo vị trí trong danh sách `|`

Một số người viết:

~~~java
catch (IllegalArgumentException | IllegalStateException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
~~~

rồi tưởng rằng Java sẽ kiểm tra từ trái sang phải và giữ một thứ tự ưu tiên tương tự `catch` riêng. Thực tế, **cả hai lựa chọn dẫn đến cùng một khối xử lý**; không có hai nhánh khác nhau để chọn. Đối tượng bị bắt vẫn có **kiểu runtime thực tế**, ví dụ `IllegalArgumentException` hoặc `IllegalStateException`; `ex.getClass()` cho biết lớp thực tế ấy.

Trong khi đó:

~~~java
catch (IllegalArgumentException ex) {
    // Xử lý lỗi đối số.
} catch (IllegalStateException ex) {
    // Xử lý lỗi trạng thái.
}
~~~

là hai nhánh riêng, mỗi nhánh có logic xử lý khác nhau. Bạn nên dùng multi-catch khi **thật sự muốn xử lý chung**; đừng gộp cho ngắn nếu lỗi khác nhau đòi hỏi hành động khác nhau.

Tương tự, **đảo vị trí** `FileNotFoundException | IOException` thành `IOException | FileNotFoundException` không sửa được lỗi compiler vì quy tắc kiểm tra **quan hệ kiểu**, không phải ưu tiên thứ tự trong dấu `|`.

## 10. Kiểu của biến trong multi-catch và điều cần chú ý

Trong một nhánh multi-catch như:

~~~java
catch (FileNotFoundException | EOFException ex) {
    System.out.println(ex.getMessage());
}
~~~

compiler suy luận kiểu tham chiếu có thể sử dụng an toàn dựa trên các lựa chọn; ở ví dụ này, những phương thức chung từ `IOException`/`Throwable` như `getMessage()` đều dùng được. Kiểu runtime của đối tượng thực tế vẫn giữ nguyên.

Nhưng bạn không thể gọi trực tiếp phương thức chỉ tồn tại trên **một trong các lựa chọn** nếu kiểu tĩnh của `ex` không bảo đảm có phương thức đó. Khi thực sự cần hành vi riêng của mỗi kiểu, hãy tách thành những `catch` riêng hoặc kiểm tra kiểu đúng cách trong khối xử lý.

### Tham số multi-catch không được gán lại

Đoạn sau **không biên dịch**:

~~~java
// Ví dụ minh họa lỗi khi gán lại tham số multi-catch.
try {
    performOperation();
} catch (IOException | SQLException ex) {
    ex = new IOException("thay thế");
}
~~~

Tham số `ex` của multi-catch được coi là final theo quy tắc Java. Nếu cần tạo một ngoại lệ mới để truyền ra ngoài, viết `throw new ...` hoặc đặt tham chiếu mới vào **biến khác**. Không nên thay thế tham chiếu đối tượng gốc rồi vô tình làm mất thông tin chẩn đoán.

Việc gán lại biến không liên quan tới quy tắc cha–con, nhưng là một lỗi thường gặp khi chuyển từ nhiều nhánh `catch` sang multi-catch.

### Không thể dùng cả kiểu cha và kiểu con để “cung cấp nhiều phương thức hơn”

Nếu muốn gọi một API đặc thù của `FileNotFoundException`, thêm `IOException` vào danh sách `|` không giúp gì; nó chỉ tạo lỗi biên dịch. Lựa chọn đúng là bắt `FileNotFoundException` ở nhánh riêng, hoặc làm việc với giao diện chung của kiểu cha khi phù hợp.

## 11. `throw ex` bên trong multi-catch và kiểm tra checked exception

Câu lệnh `throw ex;` ném lại **chính đối tượng ngoại lệ** đã bắt. Dù hai lựa chọn trong multi-catch hợp lệ, compiler vẫn phải bảo đảm các checked exception có thể truyền ra được bắt hoặc khai báo.

Ví dụ:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Đoạn minh họa bên trong một lớp.
static void process() throws IOException, SQLException {
    try {
        operation(); // Có thể ném IOException hoặc SQLException.
    } catch (IOException | SQLException ex) {
        System.err.println("Không hoàn thành");
        throw ex;
    }
}
~~~

Đây là **đoạn minh họa**, cần định nghĩa `operation()` với chữ ký phù hợp. Java hỗ trợ phân tích ném lại ngoại lệ tương đối chính xác trong một số trường hợp, và ở ví dụ này `throws IOException, SQLException` bao phủ những checked exception cần công bố.

Không được sửa ví dụ thành `catch (IOException | FileNotFoundException ex)` chỉ vì cả hai loại đều có thể được `operation()` ném: quan hệ cha–con vẫn là lỗi cú pháp/kiểu của multi-catch, độc lập với việc bạn định ném lại.

Cần phân biệt:

- **`throw ex`**: ném lại đối tượng đã bắt, không tự tạo ngoại lệ mới.
- **`throw new SomeException(..., ex)`**: tạo ngoại lệ mới, giữ `ex` làm nguyên nhân khi constructor hỗ trợ.
- **`throws IOException, SQLException`**: khai báo checked exception có thể thoát từ phương thức, dùng dấu phẩy. Quy tắc cấm cha–con của multi-catch **không phải quy tắc cấm mọi danh sách `throws`**.
- **`catch (A | B ex)`**: danh sách lựa chọn trong *một nhánh xử lý*, dùng `|` và cấm quan hệ cha–con giữa hai lựa chọn.

Nếu chỉ muốn xử lý một họ `IOException` rồi ném lại, `catch (IOException ex) { throw ex; }` đã đủ; không cần liệt kê toàn bộ các lớp con.

## 12. Phân biệt multi-catch với nhiều `catch` riêng trong tình huống thực tế

Khi quyết định cấu trúc bắt lỗi, hãy bắt đầu từ **hành vi mong muốn**, không phải từ ý định gom nhiều tên exception vào cùng một dòng.

### Trường hợp A: xử lý mọi ngoại lệ I/O như nhau

~~~java
catch (IOException ex) {
    reportIoFailure(ex);
}
~~~

Một kiểu cha duy nhất phù hợp. Đây là phương án đơn giản nhất nếu tất cả `IOException` được xử lý chung.

### Trường hợp B: một loại cần phương án riêng, các loại còn lại xử lý chung

~~~java
catch (FileNotFoundException ex) {
    askForAnotherPath(ex);
} catch (IOException ex) {
    reportIoFailure(ex);
}
~~~

Hai nhánh riêng, kiểu con trước kiểu cha. Đây là cấu trúc đúng khi hành vi khác nhau và cần một nhánh dự phòng tổng quát.

### Trường hợp C: một số loại ngang hàng cùng xử lý, loại khác có nhánh riêng

~~~java
catch (FileNotFoundException | EOFException ex) {
    reportInputUnavailable(ex);
} catch (IOException ex) {
    reportOtherIoFailure(ex);
}
~~~

Multi-catch cho các loại không kế thừa nhau; nhánh kiểu cha tách riêng ở phía sau. Cách này phân nhóm điều kiện thất bại cụ thể mà vẫn có nhánh dự phòng.

### Trường hợp D: những loại ngoại lệ thuộc hai họ độc lập

~~~java
catch (IOException | SQLException ex) {
    reportExternalFailure(ex);
}
~~~

Có thể dùng một nhánh multi-catch vì hai kiểu không có quan hệ kế thừa. Tuy nhiên chỉ gộp nếu chúng thật sự có chung cách xử lý; một số trường hợp lỗi cơ sở dữ liệu đòi hỏi rollback trong khi lỗi I/O đòi hỏi chiến lược phục hồi khác, khi đó tách nhánh rõ ràng hơn.

Các tên phương thức `reportIoFailure`, `askForAnotherPath`, `reportInputUnavailable`, `reportOtherIoFailure`, `reportExternalFailure` trong các đoạn minh họa cần được định nghĩa trước khi biên dịch; những ví dụ có chương trình chạy hoàn chỉnh đã được cung cấp ở mục 6 và 7.

## 13. Lỗi thường gặp khi viết hoặc sửa multi-catch

| Sai lầm | Tại sao sai? | Cách sửa |
| --- | --- | --- |
| `catch (IOException | FileNotFoundException ex)` | Kiểu con nằm trong cùng multi-catch với kiểu cha. | Chỉ bắt `IOException`, hoặc tách hai `catch` theo đúng thứ tự. |
| `catch (IllegalArgumentException | NumberFormatException ex)` | `NumberFormatException extends IllegalArgumentException`. | Bắt `IllegalArgumentException` nếu xử lý chung, hoặc bắt loại cụ thể ở nhánh riêng trước. |
| Đảo thành `FileNotFoundException | IOException` để thử sửa lỗi | Quy tắc không phụ thuộc thứ tự lựa chọn. | Thay đổi cấu trúc, không chỉ hoán vị. |
| Đặt `catch (IOException)` trước `catch (FileNotFoundException)` | Nhánh thứ hai riêng biệt bị che bởi nhánh cha. | Đưa `FileNotFoundException` lên trước. |
| Dùng `catch (Exception | IOException ex)` | `IOException` là lớp con của `Exception`. | Chọn kiểu cha cần thiết, hoặc tách nhánh có hành vi riêng. |
| Nghĩ hai kiểu có cùng lớp cha thì không được gộp | Mọi lớp đều có tổ tiên chung; điều cấm là hai lựa chọn kế thừa **nhau**. | `FileNotFoundException | EOFException` hợp lệ xét quan hệ subtype. |
| Dùng dấu `||` hoặc dấu phẩy giữa các loại `catch` | Không đúng cú pháp multi-catch. | Dùng một dấu `|` cho các lựa chọn. |
| Gộp các lỗi có chính sách xử lý khác nhau | Cùng một khối khó phân biệt hành vi và có thể che thông tin. | Dùng những `catch` riêng khi cần. |
| Dùng kiểu cha quá rộng chỉ để làm mã biên dịch | Có thể bắt thêm lỗi không thuộc trách nhiệm xử lý. | Chọn kiểu cha phù hợp phạm vi lỗi thật sự. |
| Gán lại tham số multi-catch `ex` | Tham số multi-catch là final. | Dùng biến khác hoặc ném ngoại lệ mới đúng mục đích. |
| Suy ra chương trình chạy được chỉ vì hai kiểu không kế thừa nhau | Checked exception và các ràng buộc khác vẫn được kiểm tra. | Kiểm tra toàn bộ `try`, các nhánh `catch`, `throws` và import. |

Một mẹo kiểm tra trước khi viết multi-catch: đối với **mỗi cặp kiểu được đặt hai bên dấu `|`**, hỏi “A có thể gán cho biến kiểu B không, hoặc B có thể gán cho biến kiểu A không, do kế thừa?” Nếu có, đó là tín hiệu có quan hệ subtype, không nên để chúng nằm cùng một nhánh multi-catch.

## 14. Bài tập tự kiểm tra

**Bài 1.** Vì sao `catch (IOException | FileNotFoundException ex)` không hợp lệ?

**Đáp án:** `FileNotFoundException` kế thừa `IOException`. Một đối tượng kiểu `FileNotFoundException` vốn đã khớp `IOException`, nên hai lựa chọn không được đứng cùng một multi-catch.

**Bài 2.** Đổi thứ tự thành `catch (FileNotFoundException | IOException ex)` có sửa được không?

**Đáp án:** Không. Quan hệ kiểu cha–con vẫn tồn tại bất kể thứ tự.

**Bài 3.** Nếu `FileNotFoundException` cần thông báo riêng, còn các `IOException` khác cần thông báo chung, nên viết gì?

**Đáp án:** Hai nhánh riêng: `catch (FileNotFoundException ex) { ... }` trước, `catch (IOException ex) { ... }` sau.

**Bài 4.** `catch (FileNotFoundException | EOFException ex)` có vi phạm quy tắc này không?

**Đáp án:** Không. Hai kiểu là các lớp con độc lập của `IOException`; chúng không là lớp con của nhau. Chương trình vẫn phải thỏa các kiểm tra còn lại về checked exception.

**Bài 5.** `catch (IllegalArgumentException | NumberFormatException ex)` có hợp lệ không?

**Đáp án:** Không; `NumberFormatException` kế thừa `IllegalArgumentException`.

**Bài 6.** Nếu chỉ muốn một cách xử lý cho toàn bộ `IOException`, nên làm gì?

**Đáp án:** Dùng một `catch (IOException ex)`. Không cần liệt kê các lớp con.

**Bài 7.** Có thể có `catch (FileNotFoundException | EOFException ex)` rồi tiếp theo `catch (IOException ex)` không?

**Đáp án:** Có, nếu `try` và các quy tắc khác hợp lệ. Kiểu cha nằm trong nhánh **riêng** phía sau, không phải trong cùng danh sách `|`.

**Bài 8.** `throws IOException, FileNotFoundException` có bị cấm bởi quy tắc multi-catch không?

**Đáp án:** Không. `throws` và `catch (A | B)` có cú pháp và quy tắc khác nhau; tuy nhiên khai báo cả kiểu cha và kiểu con trong `throws` thường dư thừa về phạm vi lỗi.

**Bài 9.** `catch (Exception | RuntimeException ex)` có hợp lệ không?

**Đáp án:** Không, vì `RuntimeException` là lớp con của `Exception`.

**Bài 10.** Khi nào việc sửa một multi-catch sai thành hai `catch` riêng có ý nghĩa hơn việc xóa kiểu con?

**Đáp án:** Khi lỗi cụ thể phải được xử lý khác với các lỗi tổng quát, chẳng hạn cho người dùng chọn đường dẫn mới khi thiếu tệp nhưng báo lỗi hệ thống cho `IOException` còn lại.

## Tài liệu đối chiếu

- [Java Language Specification 17, §14.20 — The `try` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): quy tắc cú pháp `catch`, multi-catch, tính hợp lệ của các lựa chọn và xử lý.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): kiểm tra những checked exception có thể bị ném và được bắt.
- [Oracle Java Tutorials — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/multiple.html): ví dụ multi-catch và lý do không cho các lựa chọn có quan hệ subtype (hướng dẫn viết theo Java 7/8, quy tắc vẫn áp dụng trên Java 17).
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html) và [EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): đối chiếu quan hệ kế thừa của các loại I/O.

**Ghi nhớ:** trong **một** `catch (A | B ex)`, A và B không được là kiểu cha–kiểu con của nhau. Nếu cần bắt chung toàn bộ nhánh, bắt **kiểu cha**; nếu cần xử lý riêng, viết **các `catch` tách biệt theo thứ tự con trước cha**; nếu hai kiểu độc lập và logic giống nhau, dùng **multi-catch**.
