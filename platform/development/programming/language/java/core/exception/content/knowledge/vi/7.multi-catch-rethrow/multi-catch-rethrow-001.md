# Multi-catch từ Java 7 và cú pháp dấu | trong Java

> Java Core – Exception · Nhóm: Multi-catch và rethrow · Trọng tâm: cú pháp từ Java 7, các alternative hợp lệ, kiểu tham số catch và cách dùng trong xử lý ngoại lệ. Ví dụ chính chạy với Java 17+.

## 1. Multi-catch dùng để làm gì?

Một tác vụ có thể gặp nhiều loại lỗi nhưng cần **cùng một cách xử lý**. Trước Java 7, cách thông thường là viết nhiều nhánh `catch` và lặp lại code:

```java
try {
    loadData();
} catch (IOException ex) {
    System.out.println("Cannot process data: " + ex.getMessage());
} catch (NumberFormatException ex) {
    System.out.println("Cannot process data: " + ex.getMessage());
}
```

Từ **Java 7**, multi-catch cho phép gom các kiểu ngoại lệ vào **một tham số catch**, phân tách bằng dấu gạch đứng `|`:

```java
try {
    loadData();
} catch (IOException | NumberFormatException ex) {
    System.out.println("Cannot process data: " + ex.getMessage());
}
```

Hai đoạn trên là **mã minh họa**, giả định có import `java.io.IOException` và hàm `loadData()` được khai báo thích hợp. Chúng chưa phải chương trình độc lập.

**Ý nghĩa:** Khi thân `try` ném một đối tượng exception phù hợp với **bất kỳ** kiểu nào được liệt kê, Java chỉ chạy **một handler chung**. Cú pháp này giảm code trùng, thể hiện rằng các lỗi có cùng chính sách xử lý và giữ nguyên đối tượng exception gốc.

### Kết quả học tập

Bạn sẽ biết cách:

1. Đọc và viết `catch (A | B ex)` đúng cú pháp Java 7+.
2. Xác định khi nào hai kiểu được ghép và khi nào compiler cấm vì có quan hệ subtype.
3. Phân biệt multi-catch với nhiều catch độc lập, hiểu kiểu tham số được suy luận và quy tắc ngầm `final`.
4. Bắt cả checked và unchecked exception trong cùng một handler khi có cùng chính sách.
5. Dùng `throw ex;` để truyền tiếp exception và hiểu liên hệ với precise rethrow từ Java 7.
6. Biên dịch chương trình Java 17, so sánh chính xác handler được chọn và stdout.

## 2. Cú pháp dấu | trong tham số catch

Cấu trúc:

```java
try {
    operation();
} catch (FirstException | SecondException ex) {
    handle(ex);
}
```

Đoạn này minh họa ngữ pháp; các tên kiểu/hàm chỉ là ký hiệu, chưa phải mã có thể biên dịch độc lập.

| Thành phần | Ý nghĩa |
| --- | --- |
| `try { ... }` | Khối thực thi có thể ném exception |
| `FirstException` | Alternative thứ nhất |
| `|` | Dấu ngăn cách các **kiểu ngoại lệ** trong union type |
| `SecondException` | Alternative thứ hai |
| `ex` | **Một biến tham số**, tham chiếu đối tượng exception thực tế |
| `{ handle(ex); }` | **Một khối handler** dùng chung cho các alternative |

Dấu `|` không phải `||`. Trong multi-catch, dấu này nằm **giữa những tên kiểu** và không thực hiện phép OR boolean hay bitwise OR trong lúc xử lý đối tượng.

Ví dụ **hợp lệ về mặt quan hệ các alternative**:

```java
catch (IOException | NumberFormatException | IllegalStateException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Ba loại không có quan hệ subtype với nhau. Khi đặt vào chương trình thật, vẫn phải đáp ứng các kiểm tra của compiler về checked exception và thứ tự handler.

Ngược lại, đây là ví dụ **cố ý sai cú pháp**:

```java
// Sai: không dùng || hoặc dấu phẩy phân cách kiểu:
catch (IOException || NumberFormatException ex) { }
catch (IOException, NumberFormatException ex) { }
```

Ngoài ra, union type ở đây dành cho khai báo tham số catch; không có cú pháp biến thông thường như `IOException | NumberFormatException ex;`.

**Mốc phiên bản:** Multi-catch được đưa vào Java SE 7 qua các cải tiến ngôn ngữ của Project Coin (JSR 334). Nó không yêu cầu thư viện ngoài. Nếu phải biên dịch theo cú pháp Java 6, tính năng này chưa tồn tại; nếu phải hỗ trợ Java 7 trở lên, cú pháp đã hợp lệ.

## 3. Quy tắc subtype: không được ghép lớp cha và lớp con

Đây là ràng buộc quan trọng nhất. Theo [JLS 17 mục 14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20), trong một union có nhiều alternative, **không được có một alternative là subtype của alternative khác**.

Quan sát cây kế thừa:

```text
java.lang.Throwable
└── java.lang.Exception
    ├── java.io.IOException
    │   └── java.io.FileNotFoundException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        │   └── java.lang.NumberFormatException
        └── java.lang.IllegalStateException
```

### 3.1. Hai kiểu độc lập: hợp lệ

```java
catch (IOException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
}
```

Một `IOException` không phải `NumberFormatException`, và ngược lại. Ngoại lệ thực tế là kiểu nào thì biến `ex` tham chiếu chính đối tượng đó.

### 3.2. Cha và con: không hợp lệ

```java
// Sai, chỉ minh họa lỗi biên dịch:
catch (IOException | FileNotFoundException ex) {
    System.out.println(ex.getMessage());
}
```

`FileNotFoundException` là subtype của `IOException`. Union chồng lấp khiến compiler từ chối. Đảo thành `FileNotFoundException | IOException` **vẫn sai**, vì mối quan hệ kế thừa không thay đổi.

Tương tự:

```java
// Sai: NumberFormatException extends IllegalArgumentException.
catch (NumberFormatException | IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
```

Nếu hai loại cha–con **cần xử lý như nhau**, chỉ cần catch **kiểu cha**:

```java
catch (IOException ex) {
    System.out.println("I/O failure");
}
```

Nếu phải xử lý **khác nhau**, dùng hai catch theo thứ tự con trước cha:

```java
try {
    readFile();
} catch (FileNotFoundException ex) {
    System.out.println("Missing file");
} catch (IOException ex) {
    System.out.println("Other I/O error");
}
```

Đoạn trên giả định hàm `readFile()` có khả năng ném IOException, chỉ để minh họa thứ tự catch.

**So sánh then chốt:** Ở **multi-catch**, hai alternative cha–con bị cấm **trong mọi thứ tự**. Ở **nhiều catch riêng**, có thể khai báo cả hai nếu **lớp con đứng trước lớp cha** để handler của lớp con không bị che.

## 4. Khi thực thi, multi-catch bắt một đối tượng exception

Ví dụ:

```java
try {
    readThenParse();
} catch (IOException | NumberFormatException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Một lần ném sẽ truyền đi **một instance Throwable**, không tạo hai instance. Java kiểm tra các handler theo thứ tự và tìm catch đầu tiên phù hợp; trong union, chỉ cần **một alternative** phù hợp với kiểu runtime.

Giả sử hàm phát sinh `FileNotFoundException`:

- `FileNotFoundException` là subtype của `IOException`, nên alternative `IOException` bắt được.
- Biến `ex` giữ đối tượng `FileNotFoundException` ban đầu.
- `ex.getClass().getSimpleName()` cho kết quả `FileNotFoundException`, không phải `IOException` hay tên của union.
- Khối xử lý chạy **một lần**, các sibling catch còn lại của cùng try không được chạy.
- Nếu khối handler ném exception mới, các sibling catch không tự bắt exception mới phát sinh trong handler đó.

Multi-catch không phải cách gom nhiều lỗi đồng thời. Nếu lỗi đóng tài nguyên xuất hiện thêm khi một ngoại lệ chính đã ném trong `try-with-resources`, cơ chế có thể dùng `getSuppressed()` để bảo toàn lỗi phụ; đó là vấn đề khác với ký hiệu `|`.

## 5. Ví dụ Java 17 hoàn chỉnh và kết quả chuẩn

Lưu mã dưới đây thành **`MultiCatchDemo.java`**. Ví dụ dùng cú pháp `switch ->` của Java hiện đại nên cần **Java 17+**; riêng cú pháp multi-catch bên trong đã tồn tại từ Java 7.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class MultiCatchDemo {
    private static void perform(String mode) throws IOException {
        switch (mode) {
            case "missing" -> throw new FileNotFoundException("config.txt");
            case "io" -> throw new IOException("read failed");
            case "number" -> Integer.parseInt("NaN");
            case "argument" -> throw new IllegalArgumentException("unsupported input");
            case "ok" -> System.out.println("work=ok");
            default -> throw new IllegalStateException("unexpected mode");
        }
    }

    private static void run(String mode) {
        System.out.println("== " + mode + " ==");
        try {
            perform(mode);
            System.out.println("try completed");
        } catch (IOException | NumberFormatException ex) {
            System.out.println("group=" + ex.getClass().getSimpleName());
        } catch (IllegalArgumentException ex) {
            System.out.println("argument=" + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }

    private static void rethrowFileError() throws IOException {
        try {
            throw new FileNotFoundException("log.txt");
        } catch (IOException | IllegalArgumentException ex) {
            System.out.println("inside=" + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    public static void main(String[] args) {
        run("missing");
        run("io");
        run("number");
        run("argument");
        run("ok");

        System.out.println("== rethrow ==");
        try {
            rethrowFileError();
        } catch (IOException ex) {
            System.out.println("outside=" + ex.getClass().getSimpleName());
        }
    }
}
```

Với JDK hỗ trợ `--release 17`:

```bash
javac --release 17 -encoding UTF-8 MultiCatchDemo.java
java MultiCatchDemo
```

**Stdout chính xác** đã được đối chiếu bằng cách biên dịch và chạy chương trình:

```text
== missing ==
group=FileNotFoundException
finally
after
== io ==
group=IOException
finally
after
== number ==
group=NumberFormatException
finally
after
== argument ==
argument=unsupported input
finally
after
== ok ==
work=ok
try completed
finally
after
== rethrow ==
inside=FileNotFoundException
outside=FileNotFoundException
```

### Trường hợp missing

`perform("missing")` ném `FileNotFoundException`. Nó được bắt bởi alternative `IOException` vì thuộc cây kế thừa IOException. Handler nhóm in `group=FileNotFoundException` theo kiểu **runtime** thực tế, sau đó khối `finally` in `finally` rồi in `after`.

### Trường hợp io

`perform("io")` ném đối tượng `IOException`. Nó được bắt trực tiếp bởi alternative đầu tiên, in `group=IOException`. Không có handler nào khác của cấu trúc try chạy.

### Trường hợp number

`Integer.parseInt("NaN")` ném `NumberFormatException` do không phải dạng số nguyên hợp lệ. Alternative thứ hai bắt ngoại lệ này và chạy **cùng khối** với IOException. Điều đó chứng minh multi-catch có thể nhóm **checked** và **unchecked exception** khi chính sách xử lý giống nhau.

### Trường hợp argument

`perform("argument")` ném `IllegalArgumentException` thông thường. Nó là kiểu **cha** của `NumberFormatException`, nhưng không phải mọi IllegalArgumentException đều là NumberFormatException. Union phía trước chỉ bắt NumberFormatException, nên lỗi được chuyển sang `catch (IllegalArgumentException)` sau đó.

Một catch cho lớp cha có thể bắt instance lớp con, nhưng **không có chiều ngược lại**.

### Trường hợp ok

`perform("ok")` in `work=ok` và hoàn thành bình thường; thân try in tiếp `try completed`. Các catch không chạy. `finally` vẫn chạy, sau đó in `after`.

### Trường hợp rethrow

`rethrowFileError()` ném một `FileNotFoundException`, bắt nó ở union `IOException | IllegalArgumentException`, in `inside=FileNotFoundException` rồi `throw ex;`. Caller ở `main` nhận **cùng exception** qua `catch (IOException)`, in `outside=FileNotFoundException`.

`throw ex;` không tự tạo exception mới khi `ex` là tham chiếu hợp lệ đến đối tượng đã bắt.

## 6. Kiểu của tham số ex và quy tắc implicitly final

Trong multi-catch:

```java
catch (IOException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause());
}
```

tham số `ex` có **một kiểu khai báo** được compiler suy ra từ các alternative. Theo JLS, kiểu đó là **least upper bound**: `lub(D1, D2, ...)`. Nó có thể là một supertype hoặc một kiểu có ràng buộc chung, chứ không tùy theo từng lần chạy mà đổi kiểu tĩnh.

Do đó các thành viên **chung** của `Throwable` như `getMessage()`, `getCause()`, `getSuppressed()`, `printStackTrace()` và `getClass()` đều có thể dùng. Một phương thức chỉ có ở một subtype không được gọi trực tiếp trên `ex` nếu kiểu khai báo chung không cung cấp phương thức đó.

### Không được gán lại ex

Biến exception của multi-catch được **ngầm khai báo final** (*implicitly final*), nên đoạn sau bị compiler từ chối:

```java
try {
    readThenParse();
} catch (IOException | NumberFormatException ex) {
    // Sai nếu bỏ comment:
    // ex = new IOException("another failure");
}
```

Dù không viết từ khóa `final`, bạn không thể đổi `ex` sang một exception khác hoặc gán `null` vào nó.

So sánh: trong một **uni-catch** như `catch (IOException ex)`, tham số không được ngầm final. Nó có thể là *effectively final* nếu không bị gán lại. Dù cú pháp đơn catch cho phép gán lại trong một số trường hợp, việc đó thường không nên làm vì khiến khó theo dõi exception gốc và có thể ảnh hưởng đến phân tích rethrow.

**Không nhầm hai thuật ngữ:** Tham số multi-catch là **implicitly final**; tham số uni-catch chưa gán lại có thể là **effectively final**. JLS phân biệt hai trường hợp nhưng cả hai có vai trò trong việc bảo toàn kiểu exception khi rethrow.

## 7. Multi-catch và precise rethrow từ Java 7

Cùng với multi-catch, Java 7 cải tiến cách kiểm tra checked exception khi **ném lại chính tham số `catch`** bằng `throw ex;`. Trong chương trình `MultiCatchDemo` ở phần 5, `rethrowFileError()` bắt `IOException | IllegalArgumentException` rồi ném lại `ex`. Caller vẫn phân biệt được lỗi `FileNotFoundException` thực tế, và chữ ký `throws IOException` là đủ; không cần mở rộng thành `throws Exception`.

Đây là hai tính năng riêng: **multi-catch** gom các loại lỗi có chung handler; **precise rethrow** cho phép compiler suy luận tập checked exception có thể thoát khỏi `try` khi biến `catch` là `final` hoặc *effectively final*. Một `catch (Exception ex)` đơn, không gán lại `ex`, cũng có thể dùng precise rethrow. Nếu sửa tham chiếu `ex` trong single-catch, lợi ích suy luận ấy có thể mất.

Ở bước nhập môn, hãy kiểm tra ba điều: ngoại lệ thực có được giữ nguyên khi `throw ex` không, chữ ký `throws` có bao quát checked exception còn thoát ra không, và handler có phục hồi hay chỉ chuyển trách nhiệm lên tầng gọi. Phân tích chính xác tập ngoại lệ và ảnh hưởng của phép gán lại sẽ được đào sâu ở phần học về rethrow.

## 8. Checked, unchecked và các catch nằm sau union

`IOException` là checked: compiler yêu cầu bắt hoặc khai báo nếu có thể phát sinh. `NumberFormatException` là unchecked nên có thể không khai báo `throws`, nhưng vẫn được phép bắt. Multi-catch không biến checked thành unchecked.

Để một catch hợp lệ, ngoài điều kiện subtype, compiler còn kiểm tra **liệu checked exception có thể phát sinh trong try** theo quy tắc JLS. Ví dụ chỉ parse một chuỗi số và không gọi API I/O mà lại có catch `IOException` thì thường bị báo không thể bắt kiểu checked không phát sinh.

### Catch phía sau có thể bị che

Ví dụ **cố ý không biên dịch**, giả định `readFile()` có thể ném IOException:

```java
try {
    readFile();
} catch (IOException | NumberFormatException ex) {
    System.out.println("group");
} catch (FileNotFoundException ex) {
    System.out.println("missing");
}
```

`FileNotFoundException` đã được alternative IOException của catch đầu bao phủ. Do đó catch sau không thể nhận exception mà catch đầu không bắt, khiến compiler từ chối. Đây là lỗi **thứ tự catch**; khác với lỗi **alternative có subtype với nhau trong cùng union**.

Cách tổ chức hợp lệ nếu muốn phân biệt tệp thiếu và lỗi I/O khác:

```java
try {
    readFile();
} catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println("known failure");
} catch (IOException ex) {
    System.out.println("other I/O failure");
}
```

Hai alternative đầu không liên hệ cha–con, và catch IOException phía sau vẫn có thể nhận những IOException khác FileNotFoundException.

## 9. Khi nào dùng multi-catch và khi nào dùng catch riêng?

### Dùng multi-catch khi cùng một chính sách

Ví dụ chương trình đọc cấu hình rồi parse số. Nếu lỗi I/O và lỗi định dạng số cùng có nghĩa “cấu hình không sử dụng được”, có thể chuyển hai loại sang một ngoại lệ tầng ứng dụng:

```java
try {
    loadConfiguration();
} catch (IOException | NumberFormatException ex) {
    throw new IllegalStateException("Invalid configuration", ex);
}
```

Đây là đoạn minh họa, giả định hàm `loadConfiguration()` tồn tại. Constructor `IllegalStateException(String, Throwable)` giữ nguyên exception gốc ở `cause` cho việc chẩn đoán.

### Dùng catch riêng khi hướng khôi phục khác nhau

```java
try {
    loadConfiguration();
} catch (IOException ex) {
    retryLater(ex);
} catch (NumberFormatException ex) {
    askUserToCorrectInput(ex);
}
```

Đoạn này chỉ minh họa các hàm nghiệp vụ. Lỗi I/O có thể retry sau khi kiểm tra điều kiện; lỗi định dạng số cần sửa input. Việc ép cả hai vào một catch nhóm sẽ làm mất ý nghĩa nghiệp vụ.

### Không gom Exception hoặc Throwable theo thói quen

`catch (Exception)` có thể bắt cả lỗi logic unchecked như `NullPointerException`, dễ khiến ứng dụng tiếp tục ở trạng thái không hợp lệ. `catch (Throwable)` còn bao gồm cả `Error`, thường không thích hợp để “nuốt” lỗi rồi chạy tiếp. Dùng kiểu bắt đúng khả năng phục hồi của tầng hiện tại.

Multi-catch giúp loại bỏ code lặp, nhưng không phải lý do để bỏ qua các khác biệt quan trọng về xử lý lỗi.

## 10. Chương trình tối giản tương thích cú pháp Java 7

Ví dụ chính ở phần 5 dùng switch hiện đại để trình bày nhiều tình huống. Để xác nhận **riêng tính năng multi-catch từ Java 7**, có thể dùng chương trình sau với cú pháp cổ điển.

Lưu tên tệp **`Java7MultiCatch.java`**:

```java
import java.io.IOException;

public class Java7MultiCatch {
    static void work(int kind) throws IOException {
        if (kind == 1) {
            throw new IOException("io");
        }
        throw new NumberFormatException("number");
    }

    public static void main(String[] args) {
        try {
            work(1);
        } catch (IOException | NumberFormatException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
```

Nếu dùng JDK 7 thật:

```bash
javac Java7MultiCatch.java
java Java7MultiCatch
```

Stdout:

```text
IOException
```

Nếu thay `work(1)` bằng `work(2)`, output thành `NumberFormatException`. Hai lần chạy đều vào một catch nhóm nhưng vẫn bảo toàn **kiểu runtime**.

Không nên mặc định mọi compiler JDK mới còn hỗ trợ `--release 7`; dùng `javac --help` để xem mức hỗ trợ của compiler đang có. Bản Java 7 chạy trực tiếp với JDK 7 hoặc toolchain hỗ trợ release 7; ví dụ Java 17 ở phần 5 đã được kiểm chứng riêng bằng `javac --release 17`.

## 11. Bảng lỗi cú pháp và quy tắc thường gặp

| Cách viết | Kết luận | Giải thích |
| --- | --- | --- |
| `catch (IOException | NumberFormatException ex)` | Hợp lệ nếu try phù hợp | Hai kiểu không chồng subtype |
| `catch (IOException|NumberFormatException ex)` | Hợp lệ | Không bắt buộc có khoảng trắng quanh dấu gạch đứng |
| `catch (IOException || NumberFormatException ex)` | Sai | Dùng nhầm toán tử boolean `||` |
| `catch (IOException, NumberFormatException ex)` | Sai | Dấu phẩy không phân tách union |
| `catch (IOException | FileNotFoundException ex)` | Sai | Kiểu cha và con chồng nhau |
| `catch (IllegalArgumentException | NumberFormatException ex)` | Sai | NumberFormatException là subtype |
| `catch (IOException | IOException ex)` | Sai | Alternative lặp đúng cùng kiểu |
| `catch (IOException | NumberFormatException ex) { ex = null; }` | Sai | Tham số multi-catch ngầm final |
| `catch (IOException ex)` | Hợp lệ nếu try phù hợp | Uni-catch bình thường |
| `catch (IOException | IllegalStateException ex)` | Hợp lệ nếu try phù hợp | Checked và unchecked có thể nằm chung |

Các đoạn đánh dấu “Sai” dùng để minh họa lỗi biên dịch, **không đưa vào chương trình runnable**.

## 12. Quy trình kiểm thử multi-catch

Với một đoạn code mới, hãy kiểm tra theo trình tự:

1. **Xác định tập lỗi thực tế:** đọc chữ ký `throws` của API để biết checked exception; thêm những unchecked exception có ý nghĩa nghiệp vụ.
2. **Vẽ quan hệ `extends`:** đặc biệt kiểm tra cặp `FileNotFoundException/IOException`, `NumberFormatException/IllegalArgumentException` và các subtype khác.
3. **Chỉ gom lỗi có cùng chính sách:** nếu hướng phục hồi khác nhau, dùng catch riêng.
4. **Đặt multi-catch trong thứ tự handler hợp lệ:** subtype được xử lý trước supertype ở các catch nối tiếp.
5. **Không gán lại biến `ex`:** nó ngầm final trong multi-catch.
6. **Giữ cause khi bọc lại:** ví dụ constructor `new IllegalStateException(message, ex)`.
7. **Kiểm thử mỗi alternative:** một ca phát sinh alternative thứ nhất, một ca phát sinh alternative thứ hai, một ca không lỗi và một ca chỉ phù hợp với catch khác.
8. **Nếu rethrow, kiểm tra chữ ký và caller:** checked exception có thể cần `throws` tương ứng; tránh nuốt lỗi.
9. **Kiểm tra loại exception, không khóa cứng message hệ thống:** message I/O có thể khác môi trường và bản JDK.

### Tình huống bài tập

Giả sử `read()` có thể ném IOException:

```java
try {
    read();
} catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println("A");
} catch (IOException ex) {
    System.out.println("B");
}
```

Đây là đoạn minh họa đặt trong method có khai báo `read()`, chưa phải chương trình độc lập.

| Exception từ try | Output | Lý do |
| --- | --- | --- |
| `FileNotFoundException` | `A` | Khớp alternative FileNotFoundException |
| `NumberFormatException` | `A` | Khớp alternative NumberFormatException |
| IOException khác FileNotFoundException | `B` | Không khớp union đầu, khớp catch IOException |
| Không có exception | Không in A/B | Các catch không chạy |

Nếu đổi union đầu thành `IOException | FileNotFoundException`, compiler từ chối vì chồng subtype. Nếu đưa `catch (IOException)` lên trước union chứa `FileNotFoundException`, compiler từ chối vì nhánh nhóm bị che đối với loại FileNotFoundException.

## 13. Những hiểu nhầm cần tránh

- **“Dấu | làm cả hai handler chạy.”** Không: đó là một tham số, một khối xử lý và một đối tượng exception được ném.
- **“Kiểu cha và con hợp lệ nếu đảo thứ tự trong cùng union.”** Không: subtype bị cấm trong union ở mọi thứ tự.
- **“Multi-catch chỉ bắt checked exception.”** Không: có thể dùng cả checked và unchecked.
- **“ex đổi kiểu tĩnh theo từng alternative lúc chạy.”** Không: compiler xác định một kiểu khai báo chung; object runtime vẫn giữ kiểu cụ thể.
- **“Có thể gán ex sang exception khác.”** Không: tham số multi-catch ngầm final.
- **“Bắt NumberFormatException là bắt được mọi IllegalArgumentException.”** Không: một catch kiểu con không tự nhận mọi instance kiểu cha.
- **“Multi-catch tự thay thế throws.”** Không: checked exception vẫn được phân tích tại compile time.
- **“Một exception từ catch đầu sẽ được catch tiếp bởi sibling catch.”** Không: sibling catch của cùng try chỉ xử lý exception từ thân try.
- **“throw ex tạo exception mới.”** Không: với ex khác null, đây là ném lại cùng đối tượng.
- **“Multi-catch và precise rethrow là một tính năng.”** Không: chúng có mục đích khác nhau dù cùng xuất hiện từ Java 7.
- **“Càng gom nhiều kiểu càng tốt.”** Không: chỉ nên gom loại có chính sách xử lý giống nhau.
- **“Bắt exception là đã cleanup tài nguyên.”** Không: cleanup vẫn cần cấu trúc như `try-with-resources` hoặc `finally` thích hợp.

## 14. Câu hỏi tự kiểm tra

**1.** Multi-catch xuất hiện từ Java mấy và dấu phân tách alternative là gì?

*Đáp án:* Java 7; dùng một dấu `|` ở giữa các kiểu.

**2.** Tại sao `IOException | FileNotFoundException` không biên dịch?

*Đáp án:* Vì FileNotFoundException là subtype của IOException.

**3.** Ném FileNotFoundException có được catch bởi `IOException | NumberFormatException` không?

*Đáp án:* Có, thông qua alternative IOException.

**4.** Nếu `catch (IOException | NumberFormatException ex)` đã bắt NumberFormatException, catch IllegalArgumentException phía sau có chạy nữa không?

*Đáp án:* Không. Chỉ handler đầu tiên phù hợp được thực thi.

**5.** Tại sao một IllegalArgumentException trực tiếp không vào nhóm `IOException | NumberFormatException`?

*Đáp án:* Vì NumberFormatException là lớp con của IllegalArgumentException, không phải mọi instance IllegalArgumentException đều là NumberFormatException.

**6.** Có thể gán lại `ex` trong multi-catch không?

*Đáp án:* Không, nó ngầm final.

**7.** `throw ex;` trong catch nhóm có tạo IOException mới hay tự động bỏ yêu cầu checked exception không?

*Đáp án:* Không. Nó ném lại object hiện có; compiler vẫn phân tích checked exception có thể thoát ra và caller cần xử lý/khai báo phù hợp.

**8.** Nếu IOException cần retry còn NumberFormatException cần yêu cầu nhập lại, nên dùng multi-catch không?

*Đáp án:* Nên cân nhắc tách hai catch vì chính sách phục hồi khác nhau.

## 15. Tài liệu chính thức

- [Java Language Specification 17 – §14.20 The try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cú pháp multi-catch, union alternatives, ràng buộc subtype, kiểu tham số và ngầm final.
- [JLS 17 – §14.20.1 Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): nguyên tắc handler phù hợp đầu tiên.
- [JLS 17 – §11.2.2 Exception Analysis of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.2): cơ chế precise rethrow trong phân tích exception.
- [JLS 17 – §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): quy tắc checked exception.
- [Oracle tutorial – Catching Multiple Exception Types](https://docs.oracle.com/javase/tutorial/essential/exceptions/catch.html): diễn giải multi-catch và cách dùng thực tế.
- [JSR 334 – Small Enhancements to the Java Programming Language](https://jcp.org/en/jsr/detail?id=334): nhóm cải tiến ngôn ngữ trong Java 7.

**Ghi nhớ:** Cú pháp `catch (A | B ex)` gom các lỗi có cùng cách xử lý bằng **một handler**. Các alternative phải không có quan hệ subtype với nhau; `ex` được ngầm khai báo final; thứ tự catch khác vẫn có ý nghĩa; và khi ném lại, checked exception vẫn được compiler kiểm tra theo quy tắc rethrow của Java.
