# Nhiều khối catch và thứ tự từ cụ thể đến tổng quát trong Java

> Java Core – Exception · Nhóm: **Try và catch** · Các ví dụ chạy độc lập dùng **Java 17+**.

## 1. Vấn đề cần giải quyết

Một thao tác Java có thể thất bại theo nhiều cách: tệp không tồn tại, lỗi đọc, dữ liệu sai kiểu, trạng thái ứng dụng không hợp lệ. Nếu các tình huống cần phản ứng khác nhau, ta có thể đặt **nhiều khối `catch` nối tiếp sau cùng một `try`**:

```java
try {
    // Thực hiện thao tác có thể phát sinh nhiều loại exception.
} catch (SpecificException ex) {
    // Xử lý loại cụ thể.
} catch (GeneralException ex) {
    // Xử lý loại rộng hơn.
}
```

Đây là **cú pháp minh họa**, chưa phải chương trình độc lập: `SpecificException` và `GeneralException` là tên tượng trưng.

**Nguyên tắc quan trọng:** Java kiểm tra các nhánh `catch` theo **thứ tự từ trên xuống dưới**; khi một ngoại lệ được ném, **khối phù hợp đầu tiên** sẽ được chọn. Vì vậy các lớp ngoại lệ có quan hệ kế thừa phải được đặt **từ cụ thể (lớp con) đến tổng quát (lớp cha)** để handler cụ thể còn cơ hội được thực thi.

Sau bài này, bạn có thể:

1. Dùng cây kế thừa ngoại lệ để xác định thứ tự các `catch` hợp lệ.
2. Giải thích vì sao `catch (IOException)` đặt trước `catch (FileNotFoundException)` sẽ lỗi biên dịch.
3. Dự đoán chính xác handler nào chạy với checked hoặc unchecked exception.
4. Phân biệt **nhiều catch nối tiếp** với **multi-catch** (ký hiệu `|`) và biết điều kiện không chồng kiểu.
5. Viết kiểm thử hành vi, tránh `catch (Exception)` quá rộng và hiểu vai trò của `finally`.

## 2. Cơ chế chọn catch theo JLS

Theo [Java Language Specification 17, mục 14.20.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1), nếu thân `try` ném một đối tượng ngoại lệ, Java tìm **catch đầu tiên có kiểu bắt tương thích với kiểu runtime của đối tượng bị ném**. Sau đó:

- Đối tượng ngoại lệ được gán cho tham số của catch đã chọn.
- Chỉ **khối handler được chọn** được thực thi; các `catch` còn lại của cùng cấu trúc không được chạy.
- Nếu handler hoàn thành bình thường, toàn cấu trúc `try/catch` cũng có thể hoàn thành bình thường, rồi điều khiển tiếp tục sau cấu trúc ấy.
- Nếu không có nhánh phù hợp, ngoại lệ tiếp tục lan ra ngoài; một `finally` liên quan vẫn được xét theo quy tắc của nó.
- Nếu handler lại ném exception, exception mới có thể lan tiếp; các sibling catch phía dưới **không tự bắt** lỗi mới ném từ handler phía trên.

Trong trường hợp có `finally`, xem thêm JLS mục 14.20.2: thông thường `finally` chạy sau thân `try` hoặc sau handler, kể cả khi rời phạm vi vì ngoại lệ. Nếu chính `finally` kết thúc bất thường, lý do chuyển điều khiển có thể thay đổi.

### 2.1. “Phù hợp” nghĩa là gì?

Ví dụ thứ bậc:

```text
java.lang.Throwable
├── java.lang.Error
└── java.lang.Exception
    ├── java.io.IOException
    │   └── java.io.FileNotFoundException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        │   └── java.lang.NumberFormatException
        └── java.lang.IllegalStateException
```

Một `FileNotFoundException` có thể được bắt bởi tham số kiểu `FileNotFoundException`, `IOException`, `Exception` hoặc `Throwable`, vì đó đều là các kiểu cha phù hợp. Một `NumberFormatException` có thể được bắt bởi `IllegalArgumentException` hoặc `RuntimeException`. Tuy nhiên `IOException` không có quan hệ cha–con với `IllegalArgumentException`, nên hai catch ấy **không có xung đột thứ tự chỉ do kế thừa**.

**Đừng nhầm**: Java không tự chọn “kiểu cụ thể nhất trong tất cả catch” rồi bỏ qua thứ tự mã nguồn. Chính vì tìm **catch đầu tiên phù hợp**, nếu catch cha đặt trước, catch con phía sau sẽ không thể có cơ hội nhận ngoại lệ con. Compiler phát hiện trường hợp này và từ chối mã.

### 2.2. Thứ tự là một ràng buộc biên dịch

**Hợp lệ:**

```java
try {
    openFile();
} catch (java.io.FileNotFoundException ex) {
    System.out.println("File does not exist");
} catch (java.io.IOException ex) {
    System.out.println("Other I/O failure");
}
```

Đây là đoạn minh họa trong phương thức; giả định `openFile()` được định nghĩa với khả năng ném `IOException`.

**Không hợp lệ (cố ý để nhận diện lỗi compiler):**

```java
try {
    openFile();
} catch (java.io.IOException ex) {
    System.out.println("I/O failure");
} catch (java.io.FileNotFoundException ex) {
    System.out.println("Missing file"); // Unreachable catch block.
}
```

Lý do: catch đầu đã bao phủ cả `IOException` và mọi lớp con, trong đó có `FileNotFoundException`. Catch thứ hai không thể nhận bất cứ trường hợp nào mà catch đầu không nhận; đây là **lỗi biên dịch**, không phải nhánh chạy nhưng luôn trả về false ở runtime.

Các quan hệ tương tự:

- `catch (NumberFormatException)` phải nằm trước `catch (IllegalArgumentException)` nếu có cả hai.
- `catch (IllegalStateException)` phải nằm trước `catch (RuntimeException)` nếu có cả hai.
- `catch (RuntimeException)` phải đứng trước `catch (Exception)` nếu cùng cấu trúc.
- `catch (Exception)` đứng trước `catch (IOException)` sẽ làm catch IOException bị che hoàn toàn.
- `catch (Exception)` không bắt `Error`, vì Error là nhánh khác nằm trực tiếp dưới Throwable.

## 3. Chương trình Java 17 đầy đủ: nhiều catch, thứ tự và multi-catch

Tạo tệp **`CatchOrderDemo.java`**. Chương trình dùng các exception chuẩn có quan hệ kế thừa rõ ràng, in ra chính xác handler được chọn, đồng thời chạy một ví dụ multi-catch ở phần cuối.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchOrderDemo {
    private static void process(String action) throws IOException {
        switch (action) {
            case "missing" -> throw new FileNotFoundException("data.csv");
            case "io" -> throw new IOException("read failed");
            case "bad-number" -> throw new NumberFormatException("invalid integer");
            case "bad-state" -> throw new IllegalStateException("service unavailable");
            case "ok" -> System.out.println("processed ok");
            default -> throw new IllegalArgumentException("unsupported action");
        }
    }

    private static void runOne(String action) {
        System.out.println("== " + action + " ==");
        try {
            process(action);
            System.out.println("try completed");
        } catch (FileNotFoundException ex) {
            System.out.println("file handler: " + ex.getMessage());
        } catch (IOException ex) {
            System.out.println("io handler: " + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println("argument handler: "
                    + ex.getClass().getSimpleName());
        } catch (RuntimeException ex) {
            System.out.println("runtime handler: " + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }

    private static void runMultiCatch(String action) {
        System.out.println("== multi " + action + " ==");
        try {
            if (action.equals("file")) {
                throw new FileNotFoundException("missing.txt");
            }
            if (action.equals("number")) {
                throw new NumberFormatException("not a number");
            }
            System.out.println("normal");
        } catch (FileNotFoundException | NumberFormatException ex) {
            System.out.println("group handler: "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        runOne("missing");
        runOne("io");
        runOne("bad-number");
        runOne("bad-state");
        runOne("ok");
        runOne("unknown");
        runMultiCatch("file");
        runMultiCatch("number");
        runMultiCatch("other");
    }
}
```

Biên dịch theo mức ngôn ngữ Java 17, sau đó chạy:

```bash
javac --release 17 -encoding UTF-8 CatchOrderDemo.java
java CatchOrderDemo
```

**Stdout chính xác** sau khi chạy chương trình:

```text
== missing ==
file handler: data.csv
finally
after
== io ==
io handler: read failed
finally
after
== bad-number ==
argument handler: NumberFormatException
finally
after
== bad-state ==
runtime handler: service unavailable
finally
after
== ok ==
processed ok
try completed
finally
after
== unknown ==
argument handler: IllegalArgumentException
finally
after
== multi file ==
group handler: FileNotFoundException
== multi number ==
group handler: NumberFormatException
== multi other ==
normal
```

Đầu ra này đã được đối chiếu bằng `javac --release 17` và `java` trên JDK hỗ trợ Java 17. Các thông báo được cố ý tạo bằng chuỗi xác định trong mã, không phụ thuộc ngôn ngữ thông điệp I/O của hệ điều hành.

## 4. Đọc chương trình theo từng exception

### 4.1. Tình huống `missing`: lớp con xuất hiện trước lớp cha

`process("missing")` ném `FileNotFoundException` với message `data.csv`. Dù cả catch `FileNotFoundException` và catch `IOException` có thể nhận kiểu ngoại lệ này, **catch đầu tiên** được chọn. Chương trình chỉ in `file handler: data.csv` rồi chạy `finally` và `after`.

Lợi ích nghiệp vụ: khi tệp thiếu, ta có thể gợi ý kiểm tra tên hoặc vị trí tệp, trong khi lỗi I/O khác cần xử lý riêng.

### 4.2. Tình huống `io`: handler tổng quát hơn nhận lỗi còn lại

`process("io")` ném đúng `IOException`, không phải `FileNotFoundException`. Catch đầu không phù hợp, nên Java chọn catch `IOException` kế tiếp.

Không cần viết `catch (FileNotFoundException)` cho mọi chức năng đọc tệp nếu nghiệp vụ không có cách xử lý riêng; khi cần phân biệt, thứ tự cha–con là bắt buộc.

### 4.3. Tình huống `bad-number`: nhánh unchecked vẫn tham gia cơ chế chọn

`NumberFormatException` kế thừa `IllegalArgumentException`, nên nó được bắt bởi `catch (IllegalArgumentException)` trong chương trình. Catch `RuntimeException` phía sau không chạy. Việc exception là unchecked chỉ ảnh hưởng yêu cầu `throws`/`catch` bắt buộc ở compile time, **không thay đổi quy tắc tìm handler theo kiểu runtime**.

Nếu cần thông báo nhập số cụ thể, có thể thêm `catch (NumberFormatException)` phía **trước** `catch (IllegalArgumentException)`.

### 4.4. Tình huống `bad-state`: handler chung của RuntimeException

`IllegalStateException` không phải nhánh của `IllegalArgumentException`, nên các catch cho I/O và đối số đều không phù hợp. Catch `RuntimeException` cuối cùng nhận lỗi. Chương trình in message `service unavailable`.

Điều này không mặc nhiên có nghĩa bắt mọi RuntimeException là một thiết kế tốt: ví dụ cố ý làm rõ thứ tự. Trong ứng dụng thật, `NullPointerException` do lỗi lập trình cũng là RuntimeException và có thể bị bắt quá rộng.

### 4.5. Tình huống `ok`: không có catch nào chạy

`process("ok")` in `processed ok` rồi trả về bình thường. Câu lệnh sau lời gọi trong try in `try completed`. Không có exception nên các nhánh catch đều được bỏ qua; `finally` vẫn chạy, rồi tới `after`.

### 4.6. Tình huống `unknown`: không phải mọi IllegalArgumentException đều là NumberFormatException

Giá trị không hỗ trợ làm nhánh `default` ném `IllegalArgumentException`. Catch tương ứng nhận trực tiếp, và chương trình in tên class `IllegalArgumentException`. Điều này giúp thấy catch một lớp cha có thể bao phủ nhiều lớp con nhưng không cần khai báo catch cho từng lớp con khi cách xử lý giống nhau.

### 4.7. `multi file` và `multi number`: một block xử lý nhiều kiểu

Khối:

```java
catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println("group handler: "
            + ex.getClass().getSimpleName());
}
```

dùng cú pháp *multi-catch* giới thiệu trong Java 7. Hai kiểu trong dấu `|` không thuộc quan hệ cha–con. Khi một trong hai exception được ném, Java chạy **cùng một handler**; `ex.getClass().getSimpleName()` vẫn cho biết loại runtime cụ thể.

`runMultiCatch("other")` không ném exception, nên chỉ in `normal`.

## 5. Quan hệ kế thừa quyết định thứ tự hợp lệ

### 5.1. Không đặt catch cha trước catch con

Ví dụ cố ý **không biên dịch**:

```java
try {
    riskyIo();
} catch (IOException ex) {
    recoverIo();
} catch (FileNotFoundException ex) {
    recoverMissingFile();
}
```

Các hàm `riskyIo()`, `recoverIo()`, `recoverMissingFile()` là ký hiệu minh họa, không phải phương thức được cung cấp để chạy. Compiler không cần biết thực tế lúc chạy tệp có tồn tại hay không: chỉ xét việc catch đầu bao phủ mọi instance của lớp con. Vì thế mã sẽ lỗi **ngay khi biên dịch** do nhánh `FileNotFoundException` bị bắt hết bởi catch `IOException`.

Bản đúng:

```java
try {
    riskyIo();
} catch (FileNotFoundException ex) {
    recoverMissingFile();
} catch (IOException ex) {
    recoverIo();
}
```

### 5.2. Hai kiểu không có quan hệ cha–con có thể đổi thứ tự

Nếu một phương thức có thể ném `IOException` (checked) và `IllegalArgumentException` (unchecked):

```java
try {
    riskyOperation();
} catch (IOException ex) {
    handleIo();
} catch (IllegalArgumentException ex) {
    handleBadInput();
}
```

Hoặc đổi vị trí hai catch trên đều không tạo lỗi **do che khuất quan hệ kế thừa**, vì một IOException không phải IllegalArgumentException và ngược lại. Đây là đoạn minh họa chưa độc lập (các hàm tượng trưng); riêng điều kiện **checked exception có thể phát sinh từ try** vẫn cần thỏa.

Vì thế cách nói chính xác là: **với các kiểu có quan hệ bao hàm, đặt kiểu hẹp trước kiểu rộng**, thay vì ép tất cả exception của mọi package vào một bảng “mức độ cụ thể” chung không có nghĩa.

### 5.3. Kiểu runtime quyết định handler, còn compiler kiểm tra tính hợp lệ của mã

Nếu lời gọi được khai báo `throws IOException`, đối tượng thực tế có thể là `FileNotFoundException`. Compiler nhìn chữ ký khi kiểm tra checked exception; khi chạy, JVM so kiểu **instance bị ném** với các catch theo thứ tự.

Đừng suy rằng một method khai báo `throws Exception` thì chỉ chạy `catch (Exception)`, cũng đừng suy rằng một method không khai báo `throws` thì không thể ném `RuntimeException`.

## 6. Multi-catch không phải nhiều catch nối tiếp

Java có hai cơ chế khác nhau:

**Nhiều catch nối tiếp:** mỗi loại có một khối code riêng, phù hợp nếu phản ứng khác nhau.

```java
try {
    readAndParse();
} catch (IOException ex) {
    reportReadFailure(ex);
} catch (NumberFormatException ex) {
    reportInvalidNumber(ex);
}
```

**Một multi-catch:** nhóm các exception có chung cách xử lý.

```java
try {
    readAndParse();
} catch (IOException | NumberFormatException ex) {
    reportFailure(ex);
}
```

Hai đoạn trên chỉ minh họa ý tưởng thiết kế; `readAndParse`, `reportReadFailure`, `reportInvalidNumber` và `reportFailure` không được định nghĩa ở đây.

### 6.1. Các alternative trong cùng multi-catch không được chồng kiểu

Sai, **cố ý không thể biên dịch**:

```java
catch (FileNotFoundException | IOException ex) {
    // Sai: FileNotFoundException là subtype của IOException.
}
```

Đúng:

```java
catch (FileNotFoundException | NumberFormatException ex) {
    // Hai nhánh không có quan hệ kế thừa trực tiếp.
}
```

Java từ chối tổ hợp `FileNotFoundException | IOException` vì một alternative là subtype của alternative khác. Nếu hai kiểu liên quan cha–con và cùng được xử lý giống nhau, chỉ cần catch **kiểu cha phù hợp**, ví dụ `catch (IOException ex)`. Nếu cần xử lý khác nhau, viết nhiều catch riêng đúng thứ tự.

### 6.2. Tham số multi-catch được coi là final

Trong:

```java
catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
    // ex = new RuntimeException(); // Không hợp lệ.
}
```

tham số `ex` là *implicitly final* nên không được gán lại. Khi cần phân biệt hành vi theo loại, thường nên dùng các catch riêng để tránh kiểm tra `instanceof` dày đặc trong một catch nhóm.

Kiểu của tham số multi-catch còn được suy luận từ các alternative (để gọi phương thức chung an toàn); không thể giả định nó luôn có API riêng của từng alternative. Các phương thức chung của `Throwable` như `getMessage()` và `getCause()` luôn dùng được.

### 6.3. Có thể kết hợp multi-catch và catch tổng quát

```java
try {
    operation();
} catch (FileNotFoundException | NumberFormatException ex) {
    handleKnownCase(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
```

Trong ví dụ tượng trưng trên, nếu `operation()` có thể ném `IOException`, thứ tự hợp lệ: nhánh đầu bắt FileNotFoundException hoặc NumberFormatException; nhánh sau bắt các IOException còn lại. Một `FileNotFoundException` sẽ vào nhánh đầu, không tiếp tục xuống nhánh sau.

## 7. Catch rộng: dùng khi nào và rủi ro gì?

### 7.1. catch Exception

`catch (Exception ex)` bắt `IOException`, `IllegalArgumentException`, `NullPointerException` và rất nhiều lỗi khác dưới `Exception`. Nó không bắt các `Error` như `OutOfMemoryError`, vì `Error` không kế thừa Exception.

Dùng `catch (Exception)` ở lớp biên ứng dụng (ví dụ job runner) đôi khi phù hợp để gom lỗi, ghi thông tin và báo trạng thái cuối cùng, nhưng phải có **chính sách rõ**. Một catch rộng có thể vô tình nuốt lỗi lập trình và biến thất bại nghiêm trọng thành dữ liệu trả về bình thường.

Trong logic nghiệp vụ, ưu tiên catch những loại mà tầng hiện tại **biết cách phục hồi**, ví dụ parse sai dữ liệu từng dòng hoặc tệp chưa có. Nếu không có cách khôi phục hợp lệ, cho exception lan tới tầng xử lý thích hợp.

### 7.2. catch RuntimeException và Error

`catch (RuntimeException)` sẽ bao phủ rất nhiều lỗi do code như `NullPointerException`, `IndexOutOfBoundsException` và `IllegalStateException`. Khi handler này đứng trước `catch (IllegalArgumentException)` hoặc `catch (IllegalStateException)`, compiler báo handler cụ thể ở sau không thể tới được.

`catch (Throwable)` còn rộng hơn nữa vì bao gồm cả `Error`. Phần lớn chương trình không nên bắt `Throwable` chỉ để cố chạy tiếp, vì nhiều Error phản ánh vấn đề mà ứng dụng không thể khôi phục an toàn. Có thể có trường hợp framework cấp thấp đặc biệt, nhưng đó là quyết định thiết kế được kiểm soát.

### 7.3. Giữ cause và stack trace khi chuyển tầng

Nếu tầng xử lý cần tạo exception nghiệp vụ có ý nghĩa hơn, hãy bảo toàn nguyên nhân:

```java
try {
    readConfiguration();
} catch (IOException ex) {
    throw new IllegalStateException("Cannot load configuration", ex);
}
```

Đây là mã minh họa trong một phương thức có `readConfiguration()` phù hợp. Constructor `IllegalStateException(String, Throwable)` giữ nguyên `IOException` làm cause. Nếu chỉ viết `throw new IllegalStateException("failed");`, ta làm mất chuỗi nguyên nhân gốc trừ khi đã lưu riêng.

Nếu chỉ muốn cho cùng exception tiếp tục lan truyền, có thể dùng `throw ex;` (rethrow), với yêu cầu checked exception ở chữ ký hoặc caller tương ứng. Việc xử lý trong một catch không khiến các sibling catch của cùng try có cơ hội chạy tiếp.

## 8. catch và finally: thứ tự nhìn thấy trên stdout

Trong ví dụ chính, mỗi lần gọi `runOne` đều in `finally` rồi `after`, cả khi có exception lẫn khi thao tác thành công.

Với tình huống không có exception:

```text
try hoàn thành → bỏ qua tất cả catch → finally → câu lệnh sau try/catch/finally
```

Khi exception có handler tương ứng:

```text
throw → catch đầu tiên phù hợp → finally → câu lệnh sau try/catch/finally
```

Khi exception không được bắt tại cấu trúc hiện tại:

```text
throw → không có catch phù hợp → finally → tiếp tục lan lên caller
```

Trong trường hợp cuối, **câu lệnh nằm ngay sau cấu trúc try ở cùng đường thực thi sẽ không chạy bình thường**. Nếu `finally` tự ném exception khác, exception đó có thể thay thế exception đang lan truyền; không đặt `return` hay `throw` trong finally một cách tùy tiện.

**Một lưu ý khác:** `try-with-resources` đóng tài nguyên theo quy tắc riêng trước khi chuyển sang catch/finally bên ngoài cấu trúc mở rộng. Lỗi từ `close()` có thể trở thành suppressed exception; không vì thế mà bỏ qua thứ tự catch.

## 9. Những ràng buộc compiler ngoài thứ tự cha–con

Thứ tự không phải điều kiện biên dịch duy nhất.

### 9.1. Checked exception được catch phải có cơ sở phát sinh

Ví dụ **không hợp lệ**:

```java
try {
    int number = Integer.parseInt("123");
} catch (IOException ex) {
    System.out.println("I/O failed");
}
```

Compiler có thể chứng minh đoạn try này không ném checked `IOException` hoặc kiểu liên quan, nên catch IOException bị từ chối (theo quy tắc exception analysis). `NumberFormatException` thì khác: nó là unchecked, do đó có thể được bắt mà không cần một `throws` tương ứng.

Ở đây đừng lạm dụng cú pháp `catch IOException` “cho chắc”: hãy bắt loại mà mã có thể phát sinh, hoặc thiết kế cách truyền lỗi rõ ràng ở API.

### 9.2. Không được lặp catch có cùng kiểu

Đoạn sau cũng không thể biên dịch:

```java
try {
    possiblyFail();
} catch (IllegalArgumentException ex) {
    handleA(ex);
} catch (IllegalArgumentException ex) {
    handleB(ex);
}
```

Một catch đầu đã bao phủ toàn bộ những exception có thể vào catch thứ hai. Mã chỉ là minh họa, các method chưa được định nghĩa.

### 9.3. Đừng nhầm hai mức “không thể tới được”

- **Nhánh bị che bởi catch trước**: do kiểu cha đã bắt toàn bộ kiểu con, Java từ chối ở compile time.
- **Nhánh hợp lệ nhưng dữ liệu test hiện tại không kích hoạt**: vẫn là handler có thể dùng trong một lần chạy khác, nên không lỗi chỉ vì test hôm nay không gây ra ngoại lệ đó.

Ví dụ `catch (FileNotFoundException)` đứng trước `catch (IOException)` hoàn toàn hợp lệ khi thao tác có thể ném cả IOException chung. Trong lần chạy ném FileNotFoundException, catch IOException không chạy nhưng **không** bị coi là vô hiệu về ngôn ngữ.

## 10. Mẫu thiết kế và quy trình kiểm tra thực tế

Khi xây dựng nhiều catch cho một thao tác:

1. **Liệt kê lỗi có thể phát sinh**: xem `throws` của API cho checked exceptions; tìm những unchecked exception có ý nghĩa nghiệp vụ.
2. **Vẽ quan hệ kế thừa** giữa các kiểu dự kiến bắt; dùng Javadoc hoặc IDE để xác nhận kiểu cha–con.
3. **Chọn chính sách phục hồi riêng**: ví dụ tệp thiếu → thông báo đường dẫn; lỗi I/O khác → báo lỗi đọc; dữ liệu sai → yêu cầu sửa.
4. **Sắp xếp các handler có quan hệ kế thừa** từ subtype đến supertype.
5. **Gom thành multi-catch** nếu các kiểu không nằm trong quan hệ subtype và thực sự có cùng cách xử lý.
6. **Chọn ranh giới cleanup** bằng `try-with-resources` hoặc `finally` phù hợp.
7. **Biên dịch và test từng nhánh**: một input gây lỗi cụ thể, một input gây lỗi cha, một input thành công; kiểm tra chỉ đúng handler được chọn.
8. **Test đường lan truyền** khi không có catch phù hợp; xác nhận exception không bị nuốt và trạng thái sau lỗi nhất quán.

Bảng quyết định với ví dụ trong bài:

| Exception runtime | Catch đầu tiên phù hợp | Vì sao |
| --- | --- | --- |
| `FileNotFoundException` | `FileNotFoundException` | Nhánh cụ thể đầu tiên |
| `IOException` | `IOException` | Không phải FileNotFoundException |
| `NumberFormatException` | `IllegalArgumentException` | NumberFormatException là subtype |
| `IllegalStateException` | `RuntimeException` | Không thuộc nhánh IllegalArgumentException |
| `IllegalArgumentException` | `IllegalArgumentException` | Kiểu phù hợp trực tiếp |
| Không có exception | Không catch nào | Try hoàn thành bình thường |

Có thể xác nhận một cách tự động bằng JUnit/AssertJ nếu dự án có sẵn. Với ví dụ console nhỏ, kiểm tra stdout và so kiểu exception đã đủ thể hiện quy tắc, không cần phụ thuộc framework.

## 11. Lỗi phổ biến và cách sửa

- **Bắt cha trước con.** Sửa thứ tự `FileNotFoundException` trước `IOException`, `NumberFormatException` trước `IllegalArgumentException`.
- **Hiểu nhầm Java chọn “catch cụ thể nhất” bất kể vị trí.** Java xét theo thứ tự xuất hiện; compiler cấm trường hợp bị che hoàn toàn.
- **Tưởng nhiều catch có thể cùng chạy trên một exception.** Chỉ một catch của cùng cấu trúc được chọn.
- **Đưa hai kiểu cha–con vào cùng multi-catch.** `IOException | FileNotFoundException` không hợp lệ; dùng IOException đơn lẻ hoặc nhiều handler.
- **Dùng `catch (Exception)` để che mọi lỗi.** Dễ nuốt bug lập trình; chỉ dùng ở ranh giới có chính sách xử lý rõ.
- **Không phân biệt checked và unchecked.** Checked exception có phân tích compiler riêng; RuntimeException vẫn có thể được bắt và tuân thứ tự như thường.
- **Giả định `catch (Exception)` bao gồm `Error`.** Không; Error là nhánh khác dưới Throwable.
- **Catch một IOException mà try không thể ném.** Có thể lỗi biên dịch; đọc hợp đồng API trước.
- **Mất `cause` khi bọc exception.** Tạo exception mới với constructor nhận cause nếu cần giữ lỗi gốc.
- **Nghĩ handler tự động thử lại thao tác lỗi.** Catch chỉ chuyển luồng điều khiển; retry cần code riêng và cân nhắc side effects.
- **Quên `finally`/resource cleanup.** Sau handler có thể vẫn cần đóng tài nguyên; `try-with-resources` thường là lựa chọn tốt cho `AutoCloseable`.
- **So sánh toàn bộ thông điệp exception của hệ điều hành.** Message thực tế có thể khác môi trường; kiểm tra kiểu exception, chính sách và các chuỗi do ứng dụng định nghĩa.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Với một `FileNotFoundException`, nếu viết `catch (IOException)` trước `catch (FileNotFoundException)`, handler nào chạy?

*Đáp án:* Chương trình **không biên dịch** vì handler cụ thể phía sau bị che. Không có chuyện Java chạy rồi tùy runtime chọn một trong hai.

**Câu 2.** Nếu một `NumberFormatException` xuất hiện nhưng chỉ có `catch (IllegalArgumentException)`, nhánh ấy có bắt được không?

*Đáp án:* Có. NumberFormatException kế thừa IllegalArgumentException.

**Câu 3.** `IOException` và `IllegalArgumentException` có phải luôn sắp theo một “thứ tự kế thừa” bắt buộc không?

*Đáp án:* Không. Hai kiểu không có quan hệ cha–con; thứ tự giữa chúng có thể chọn theo cách tổ chức code và chính sách nghiệp vụ, miễn các ràng buộc compiler khác hợp lệ.

**Câu 4.** Khi handler đã bắt và hoàn thành bình thường, catch khác của cùng try có chạy tiếp không?

*Đáp án:* Không. Java chọn catch phù hợp đầu tiên, thực hiện handler đó rồi chuyển sang finally (nếu có) và phần sau cấu trúc.

**Câu 5.** Vì sao `catch (IOException | FileNotFoundException ex)` sai?

*Đáp án:* Một alternative là subtype của alternative khác. Nếu xử lý giống nhau, dùng một catch IOException; nếu khác, tách thành các catch theo thứ tự con trước cha.

**Câu 6.** Nếu catch được chọn lại ném một `IllegalStateException`, catch `RuntimeException` phía dưới của **cùng try** có bắt được không?

*Đáp án:* Không. Sibling catch chỉ tham gia chọn handler cho ngoại lệ từ **thân try**, không xử lý exception mới phát sinh trong sibling catch. Một try/catch bao ngoài mới có thể bắt.

**Câu 7.** Nếu try hoàn thành bình thường, finally có được chạy không?

*Đáp án:* Có, trong hoạt động bình thường của Java, finally vẫn được thực hiện theo quy tắc của cấu trúc. Các catch được bỏ qua.

## 13. Tài liệu đối chiếu chính thức

- [JLS Java SE 17 §14.20 – The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cú pháp nhiều catch, multi-catch và finally.
- [JLS Java SE 17 §14.20.1 – Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): quy tắc **chọn catch phù hợp đầu tiên** theo kiểu runtime.
- [JLS Java SE 17 §14.20.2 – Execution of try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): luồng thực thi sau catch và finally.
- [JLS Java SE 17 §11.2.3 – Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): checked exception có cơ sở phát sinh và lỗi khi catch bị che.
- [Java 17 API – FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html) và [IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): quan hệ kế thừa của exception I/O.
- [Java 17 API – NumberFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NumberFormatException.html) và [IllegalArgumentException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html): quan hệ kế thừa unchecked exception.

**Ghi nhớ:** Trong một `try` có nhiều `catch`, hãy bắt đầu bằng các ngoại lệ hẹp mà bạn cần xử lý riêng, sau đó mới đặt các kiểu cha rộng hơn. Java chọn **handler phù hợp đầu tiên**, multi-catch chỉ gom những kiểu không nằm trong quan hệ subtype với nhau, và compiler giúp phát hiện các nhánh bị che ngay trước lúc chạy.