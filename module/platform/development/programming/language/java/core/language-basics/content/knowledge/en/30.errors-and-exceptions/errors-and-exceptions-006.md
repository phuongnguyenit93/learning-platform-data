# Nhận diện checked exception và unchecked exception — Java 17+

## 1. Hai nhóm ngoại lệ khác nhau ở quy tắc biên dịch

Trong Java, ngoại lệ (*exception*) biểu diễn tình huống bất thường trong khi thực thi: dữ liệu không hợp lệ, tài nguyên không sẵn có, trạng thái không cho phép thực hiện thao tác... Java chia các kiểu có thể ném thành **checked** và **unchecked** dựa trên **hệ phân cấp lớp**, chứ không dựa vào mức độ “nghiêm trọng” hoặc nội dung thông điệp.

- **Checked exception:** khi một lệnh có thể phát sinh kiểu checked, mã gọi phải **bắt (catch)** hoặc **khai báo chuyển tiếp (throws)** ngoại lệ theo quy tắc của trình biên dịch.
- **Unchecked exception:** trình biên dịch **không bắt buộc** người gọi phải catch hoặc khai báo throws; tuy nhiên ngoại lệ vẫn có thể được ném khi chạy, có stack trace và có thể được xử lý khi phù hợp.

~~~java
// IOException là checked: phải xử lý hoặc khai báo.
static String load(String key) throws java.io.IOException {
    if (key.isBlank()) {
        throw new java.io.IOException("empty key");
    }
    return key;
}

// IllegalArgumentException là unchecked.
static int requirePositive(int n) {
    if (n <= 0) {
        throw new IllegalArgumentException("n must be positive");
    }
    return n;
}
~~~

**Lưu ý:** `throws` không làm phương thức tự động ném ngoại lệ. Nó **khai báo khả năng ngoại lệ thoát ra** từ phương thức; `throw` mới thực hiện thao tác ném một đối tượng ngoại lệ cụ thể.

## 2. Nhận diện từ cây kế thừa

Trong Java 17, các kiểu có thể được ném bằng `throw` phải thuộc `Throwable` (hoặc lớp con).

~~~text
java.lang.Throwable
├── java.lang.Error                  [unchecked]
│   ├── VirtualMachineError         [unchecked]
│   │   ├── StackOverflowError      [unchecked]
│   │   └── OutOfMemoryError        [unchecked]
│   └── AssertionError              [unchecked]
└── java.lang.Exception
    ├── IOException                 [checked]
    ├── SQLException                [checked]
    ├── InterruptedException        [checked]
    ├── ClassNotFoundException      [checked]
    └── RuntimeException            [unchecked]
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        ├── NullPointerException
        ├── ArithmeticException
        └── IndexOutOfBoundsException
            └── ArrayIndexOutOfBoundsException
~~~

Quy tắc phân loại theo lớp gốc:

| Kiểu kế thừa từ | Nhóm | Nghĩa vụ compiler |
|---|---|---|
| `Exception` nhưng **không** nằm dưới `RuntimeException` | **Checked exception** | Phải catch hoặc declare (`throws`) nếu ngoại lệ có thể thoát ra |
| `RuntimeException` và mọi lớp con | **Unchecked exception** | Không bắt buộc catch/declare |
| `Error` và mọi lớp con | **Unchecked exception classes** | Không bắt buộc catch/declare, nhưng thường không nên xem là lỗi nghiệp vụ để phục hồi |
| `Throwable` trực tiếp hoặc các lớp con không thuộc nhánh `Error`/`RuntimeException` | **Checked** theo quy tắc Java | Catch hoặc declare nếu có thể thoát ra |

**Phân biệt quan trọng:** từ “unchecked exception classes” trong đặc tả Java bao gồm cả nhánh `Error`. Trong trao đổi thực tế, người ta thường gọi nhánh `RuntimeException` là “unchecked exceptions” và nói riêng “Errors”. `Error` **không phải** là lớp con của `RuntimeException`.

Một lớp tự định nghĩa kế thừa `Exception` (không qua `RuntimeException`) là checked; kế thừa `RuntimeException` là unchecked.

## 3. Các ví dụ nhận diện thường gặp

| Kiểu ngoại lệ | Nhóm | Tình huống thường gặp |
|---|---|---|
| `java.io.IOException` | Checked | Đọc/ghi dữ liệu vào I/O thất bại |
| `java.sql.SQLException` | Checked | Thao tác JDBC gặp lỗi |
| `java.lang.ClassNotFoundException` | Checked | Tải lớp theo tên không tìm được lớp |
| `java.lang.InterruptedException` | Checked | Luồng bị ngắt khi chờ/ngủ |
| `java.text.ParseException` | Checked | Một API phân tích chuỗi khai báo lỗi parse |
| `java.lang.NumberFormatException` | Unchecked | Chuỗi không chuyển được thành số qua `Integer.parseInt` |
| `java.lang.NullPointerException` | Unchecked | Dùng tham chiếu `null` ở thao tác yêu cầu object |
| `java.lang.IllegalArgumentException` | Unchecked | Đối số vi phạm quy tắc API |
| `java.lang.IllegalStateException` | Unchecked | Trạng thái object không cho phép hành vi |
| `java.lang.ArrayIndexOutOfBoundsException` | Unchecked | Truy cập chỉ số ngoài phạm vi mảng |
| `java.lang.StackOverflowError` | Unchecked (Error) | Stack không đủ cho các lời gọi lồng nhau |

Tên lớp có hậu tố `Exception` **không bảo đảm checked**: `NumberFormatException` vẫn unchecked. Ngược lại, một số lỗi như `OutOfMemoryError` không phải ngoại lệ nghiệp vụ dù không cần khai báo `throws`.

Không phải mọi kiểu “parse dữ liệu” đều ném checked exception: `Integer.parseInt("abc")` ném **unchecked `NumberFormatException`**. Hãy xem **chính xác chữ ký API và lớp ngoại lệ**, không đoán theo tình huống.

## 4. Checked: catch hoặc declare (`throws`)

Giả sử `Files.readString(Path.of("settings.txt"))` có thể ném `IOException` (checked). Phương thức sau là **mã cố ý sai để minh họa lỗi biên dịch**:

~~~java
// KHÔNG BIÊN DỊCH nếu giữ nguyên:
static String readWrong() {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("settings.txt"));
}
~~~

Vì checked `IOException` có thể thoát ra, compiler yêu cầu xử lý. Có hai hướng chính:

**A. Khai báo chuyển tiếp:**

~~~java
static String readFile() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("settings.txt"));
}
~~~

Caller của `readFile()` phải tiếp tục **catch hoặc declare**, cho đến một ranh giới xử lý thích hợp. `throws IOException` **không đọc file hộ**, không tự catch và không bảo đảm thao tác sẽ lỗi khi chạy.

**B. Bắt ngoại lệ tại vị trí cần xử lý:**

~~~java
static String readOrDefault() {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of("settings.txt"));
    } catch (java.io.IOException ex) {
        return "DEFAULT";
    }
}
~~~

Khi file không tồn tại/không đọc được, nhánh catch trả giá trị dự phòng. Đoạn trên là minh họa API **có tương tác filesystem**, không phải ví dụ xác định stdout ở mục 9. Trong chương trình hoàn chỉnh, ta chủ động tạo ngoại lệ để kết quả giống nhau trên các máy.

**Không nên trả DEFAULT vô điều kiện trong mọi ứng dụng**: nếu không có mặc định hợp lệ, hãy thêm bối cảnh rồi chuyển tiếp lỗi hoặc xử lý phù hợp. Không nuốt lỗi để che sai sót nghiệp vụ.

## 5. Unchecked: compiler không ép catch/declare

~~~java
static int parseAge(String text) {
    int age = Integer.parseInt(text); // Có thể NumberFormatException.
    if (age < 0) {
        throw new IllegalArgumentException("age cannot be negative");
    }
    return age;
}
~~~

Phương thức trên **không cần** ghi `throws NumberFormatException` hoặc `throws IllegalArgumentException`. Tuy nhiên:

- `parseAge("20")` trả `20`.
- `parseAge("abc")` ném `NumberFormatException`.
- `parseAge("-2")` ném `IllegalArgumentException` do kiểm tra quy tắc.

Caller vẫn có thể catch ngoại lệ unchecked nếu lỗi là một kết quả dự kiến từ dữ liệu không đáng tin:

~~~java
try {
    int age = parseAge("abc");
    System.out.println(age);
} catch (NumberFormatException ex) {
    System.out.println("invalid number");
}
~~~

**Exact stdout:**

~~~text
invalid number
~~~

**Không có nghĩa unchecked = an toàn để bỏ qua.** Một lỗi unchecked không được bắt cũng có thể làm kết thúc luồng đang chạy và được handler mặc định thông báo bằng stack trace.

Một phương thức **được phép khai báo** `throws IllegalArgumentException` nhằm tài liệu hóa hợp đồng, nhưng đây không phải yêu cầu của compiler. Với các bug như `NullPointerException`, thường nên sửa nguyên nhân thay vì chỉ thêm catch chung chung.

## 6. Phân biệt `throw`, `throws`, `try` và `catch`

| Cú pháp | Vai trò | Ví dụ |
|---|---|---|
| `throw` | Ném một đối tượng `Throwable` cụ thể | `throw new IOException("failed");` |
| `throws` | Khai báo những ngoại lệ có thể thoát khỏi method/constructor | `void load() throws IOException` |
| `try` | Đánh dấu khối thực thi có thể phát sinh lỗi | `try { load(); }` |
| `catch` | Xử lý kiểu ngoại lệ khớp nhánh | `catch (IOException ex) { ... }` |
| `finally` | Khối dọn dẹp thường chạy khi rời try/catch | `finally { ... }` |

Chú ý mã Java phải có các import hoặc dùng tên đầy đủ cho `IOException`. Một ví dụ tự chứa về cú pháp:

~~~java
import java.io.IOException;

class Reader {
    static void run() throws IOException {
        throw new IOException("failed");
    }
}
~~~

Với checked exception, compiler sẽ kiểm tra việc **bắt hoặc khai báo** trên luồng điều khiển có thể thoát. Nó không yêu cầu mỗi method trong dự án phải có `throws`, cũng không bắt buộc catch tất cả nhánh unchecked.

Trong phương thức `main`, cũng có thể viết `public static void main(String[] args) throws IOException` để chuyển tiếp lỗi. Đây là cách biên dịch được nhưng không tự đem lại chính sách phục hồi hay thông báo thân thiện cho người dùng.

## 7. `catch` phải đúng quan hệ kế thừa và thứ tự

`NumberFormatException` là lớp con của `IllegalArgumentException`. Khi bắt nhiều loại liên quan, đưa loại **cụ thể trước**, loại **tổng quát sau**:

~~~java
try {
    Integer.parseInt("bad");
} catch (NumberFormatException ex) {
    System.out.println("invalid digits");
} catch (IllegalArgumentException ex) {
    System.out.println("other illegal argument");
}
~~~

**Exact stdout:**

~~~text
invalid digits
~~~

Đảo hai catch sẽ khiến nhánh `NumberFormatException` trở nên **không thể tới được**, do `IllegalArgumentException` đã bắt tất cả lớp con ấy. Compiler báo lỗi.

`catch (Exception ex)` có thể bắt checked/unchecked exceptions thuộc nhánh `Exception`, nhưng **không bắt `Error`**. `catch (Throwable ex)` bắt rộng hơn, thường không phù hợp cho xử lý nghiệp vụ thông thường. Chỉ dùng catch rộng tại ranh giới có chính sách rõ ràng (ghi log, chuyển đổi, đảm bảo cleanup), không che giấu những lỗi hệ thống khó phục hồi.

Đôi khi Java báo “exception is never thrown in body of corresponding try statement” khi catch một checked exception không thể phát sinh từ khối try theo phân tích của compiler. Không tạo catch checked “dự phòng” ở mọi nơi mà không có API phát sinh loại đó.

## 8. Checked không đồng nghĩa với luôn phục hồi được

Một exception được phân loại theo **kiểu lớp**, không theo việc xử lý có dễ hay không.

- **Checked `IOException`:** có thể do file không tồn tại, hết quyền truy cập hoặc sự cố I/O. Có thể retry/fallback hoặc chuyển tiếp tùy tình huống.
- **Unchecked `IllegalArgumentException`:** có thể được catch ở ranh giới nhập liệu để báo người dùng giá trị sai.
- **Unchecked `NullPointerException`:** thường biểu thị lỗi logic/hợp đồng ở một đoạn code; xử lý hiệu quả có thể là ngăn null từ sớm.
- **`Error`:** nhiều trường hợp biểu thị vấn đề VM/tài nguyên (như `StackOverflowError` và `OutOfMemoryError`) nên không coi `catch (Error)` là giải pháp mặc định.

Khi thiết kế API:

- Chọn **checked** cho điều kiện mà caller được yêu cầu xử lý hoặc quyết định chuyển tiếp.
- Chọn **unchecked** cho vi phạm hợp đồng, lập trình sai hoặc tình huống được API thiết kế trả về dưới dạng runtime exception.
- Không phải mọi thư viện đều chọn giống nhau; luôn đọc **chữ ký method, Javadoc và tài liệu hợp đồng**.

Một method khai báo `throws IOException` không chắc chắn **sẽ ném** exception mỗi lần gọi; chỉ nói nó **có khả năng thoát ra** theo hợp đồng và compiler sẽ kiểm tra.

## 9. Ví dụ Java 17+ chạy độc lập

Tạo file đúng tên **`CheckedUncheckedDemo.java`**:

~~~java
import java.io.IOException;

public final class CheckedUncheckedDemo {
    private CheckedUncheckedDemo() {}

    static String loadFromSource(String key) throws IOException {
        if (key == null || key.isBlank()) {
            throw new IOException("missing configuration key");
        }
        return "value-" + key.strip();
    }

    // Khai báo chuyển tiếp IOException checked.
    static String prepare(String key) throws IOException {
        return loadFromSource(key) + "!";
    }

    // Bắt checked exception ở một ranh giới có fallback phù hợp.
    static String loadOrDefault(String key) {
        try {
            return prepare(key);
        } catch (IOException ex) {
            return "DEFAULT";
        }
    }

    // Unchecked: không bắt buộc khai báo throws.
    static int parseAge(String raw) {
        int age = Integer.parseInt(raw);
        if (age < 0) {
            throw new IllegalArgumentException("age cannot be negative");
        }
        return age;
    }

    static void assertReady(boolean ready) {
        if (!ready) {
            throw new IllegalStateException("service not ready");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("checked success=" + prepare(" config "));
        } catch (IOException ex) {
            System.out.println("checked unexpected failure");
        }

        System.out.println("checked fallback=" + loadOrDefault(""));

        try {
            prepare("");
        } catch (IOException ex) {
            System.out.println("checked caught="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        System.out.println("unchecked success=" + parseAge("20"));
        try {
            parseAge("abc");
        } catch (NumberFormatException ex) {
            System.out.println("unchecked parse="
                    + ex.getClass().getSimpleName());
        }

        try {
            parseAge("-2");
        } catch (IllegalArgumentException ex) {
            System.out.println("unchecked validation="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        try {
            assertReady(false);
        } catch (IllegalStateException ex) {
            System.out.println("unchecked state="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        System.out.println("checked parent="
                + IOException.class.getSuperclass().getSimpleName());
        System.out.println("unchecked parent="
                + IllegalStateException.class.getSuperclass().getSimpleName());
        System.out.println("program continues=true");
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 CheckedUncheckedDemo.java
java -cp . CheckedUncheckedDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\CheckedUncheckedDemo.java
java -cp . CheckedUncheckedDemo
~~~

Ví dụ **không truy cập filesystem**, mạng hoặc cơ sở dữ liệu; checked `IOException` được ném trực tiếp có kiểm soát. Không cần Maven/Gradle, thư viện ngoài hoặc preview features.

### Exact expected stdout

~~~text
checked success=value-config!
checked fallback=DEFAULT
checked caught=IOException:missing configuration key
unchecked success=20
unchecked parse=NumberFormatException
unchecked validation=IllegalArgumentException:age cannot be negative
unchecked state=IllegalStateException:service not ready
checked parent=Exception
unchecked parent=RuntimeException
program continues=true
~~~

**Đọc kết quả:**

1. Với key hợp lệ, `prepare(...)` trả chuỗi bình thường, dù method **có khai báo** `throws IOException`.
2. Với key rỗng, `loadFromSource(...)` ném checked `IOException`; `loadOrDefault(...)` bắt để trả `DEFAULT`. Một lời gọi khác bắt lỗi và in loại + thông điệp.
3. `parseAge("abc")` tạo unchecked `NumberFormatException`; `parseAge("-2")` ném unchecked `IllegalArgumentException`. Hai loại vẫn có thể catch bình thường.
4. `assertReady(false)` ném unchecked `IllegalStateException`.
5. Hai dòng `parent` cho thấy `IOException` kế thừa trực tiếp `Exception` và `IllegalStateException` kế thừa trực tiếp `RuntimeException`.
6. Vì các ngoại lệ đều được xử lý có chủ đích, chương trình chạy đến dòng `program continues=true`.

## 10. Tự định nghĩa checked và unchecked exception

Một class tùy chỉnh có thể phân loại qua **lớp cha**, không cần đăng ký với JVM.

~~~java
// Minh họa độc lập trong phạm vi cùng package:
class MissingRecordException extends Exception {
    MissingRecordException(String message) {
        super(message);
    }
}

class InvalidRecordStateException extends RuntimeException {
    InvalidRecordStateException(String message) {
        super(message);
    }
}
~~~

- `MissingRecordException extends Exception` → checked. Phương thức có thể ném kiểu này phải tuân thủ quy tắc catch/declare.
- `InvalidRecordStateException extends RuntimeException` → unchecked. Compiler không ép caller catch/declare.
- Cả hai vẫn là `Throwable`; cả hai có thể đi kèm thông điệp/cause, được in stack trace và được catch tương ứng.

Khi bọc lỗi để giữ nguyên nguyên nhân, có thể gọi constructor như `new IOException("cannot load config", cause)`. Đừng làm mất `cause` khi chuyển đổi exception nếu hệ thống cần chẩn đoán nguồn gốc lỗi.

## 11. `try-with-resources` không thay quy tắc checked

Nhiều API I/O yêu cầu đóng resource, ví dụ:

~~~java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Đây là **mã minh họa method**, không chạy trong demo không phụ thuộc môi trường ở mục 9.

`try-with-resources` bảo đảm tài nguyên được quản lý đóng khi rời khối, kể cả khi có lỗi, nhưng hoạt động đọc/đóng **vẫn có thể ném checked `IOException`**. Vì vậy, ví dụ khai báo `throws IOException` thay vì giả định try-with-resources đã “xử lý mọi lỗi”.

Nếu dùng `InterruptedException` từ `Thread.sleep(...)`, không nên nuốt tín hiệu ngắt. Tùy hợp đồng, có thể chuyển tiếp `throws InterruptedException` hoặc khi bắt để phục hồi trạng thái thì khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` theo yêu cầu thiết kế.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Hiểu đúng |
|---|---|
| Tên kết thúc `Exception` chắc chắn là checked | `RuntimeException` và các lớp con như `NumberFormatException` là unchecked |
| Unchecked nghĩa là không bao giờ ném khi chạy | Vẫn được ném và có thể làm dừng luồng nếu không được xử lý |
| Checked nghĩa là lúc chạy luôn có lỗi | Compiler yêu cầu xử lý/khai báo khả năng; đường chạy hợp lệ có thể không ném |
| `throws` tự ném ngoại lệ | `throws` chỉ khai báo; `throw` ném |
| Catch unchecked là không hợp lệ | Catch được khi phù hợp, chỉ là compiler không bắt buộc |
| Thấy `Error` liền coi là checked vì khác `RuntimeException` | Các lớp con `Error` cũng unchecked theo phân loại Java |
| `catch (Exception)` bắt luôn `OutOfMemoryError` | `Error` không kế thừa `Exception` |
| Thêm `catch (IOException)` quanh mọi lệnh cho chắc | Compiler có thể từ chối catch checked không thể phát sinh |
| Catch `IllegalArgumentException` rồi đến `NumberFormatException` | Nhánh con phía sau không thể tới được; đảo thứ tự |
| `throws Exception` luôn là thiết kế tốt | Quá rộng, che mất hợp đồng ngoại lệ cụ thể; dùng kiểu phù hợp |
| Catch và bỏ trống để ứng dụng khỏi crash | Có thể che giấu lỗi; xử lý, log hoặc chuyển tiếp có chủ đích |
| `finally` tự biến ngoại lệ thành thành công | Cleanup không đồng nghĩa với xử lý nguyên nhân |

## 13. Bài tập có đáp án

**A.** Phân loại `IOException`, `SQLException`, `IllegalStateException`, `NumberFormatException`, `StackOverflowError`.

**Đáp án:** `IOException` và `SQLException` **checked**; `IllegalStateException` và `NumberFormatException` **unchecked RuntimeException**; `StackOverflowError` là **unchecked Error**.

**B.** Vì sao lời gọi `Files.readString(Path.of("a.txt"))` trong method không catch/không throws báo lỗi compiler?

**Đáp án:** vì API có thể ném checked `IOException`. Caller phải catch hoặc thêm `throws IOException` (hoặc siêu kiểu checked hợp lệ) trong khai báo.

**C.** Khi gọi `Integer.parseInt("bad")`, có cần khai báo `throws NumberFormatException` không?

**Đáp án:** **Không**, `NumberFormatException` nằm dưới `RuntimeException`. Caller có thể catch nếu đầu vào không hợp lệ là trường hợp dự kiến.

**D.** Một class `class MyFailure extends Exception` là checked hay unchecked? Nếu `extends RuntimeException` thì sao?

**Đáp án:** `extends Exception` trực tiếp là **checked**, còn `extends RuntimeException` là **unchecked**.

**E.** Tại sao phải catch `NumberFormatException` trước `IllegalArgumentException` nếu cả hai đều có catch riêng?

**Đáp án:** vì `NumberFormatException` là lớp con; bắt cha trước sẽ khiến bắt con sau **không thể tới được**.

**F.** `catch (Exception ex)` có bắt được `StackOverflowError` không?

**Đáp án:** **Không**, `StackOverflowError` kế thừa `Error`, không phải `Exception`.

**G.** Khi hàm khai báo `throws IOException` nhưng nhận dữ liệu hợp lệ và không có lỗi nào, có nhất định ném IOException không?

**Đáp án:** **Không**. `throws` chỉ là khai báo một khả năng; ví dụ `prepare(" config ")` trả `value-config!`.

## 14. Checklist và kết luận

- [ ] Xác định checked/unchecked bằng **hệ phân cấp `Throwable`**, không dựa vào tên/độ nghiêm trọng.
- [ ] Biết `Exception` (không nằm dưới `RuntimeException`) thường là checked.
- [ ] Biết nhánh `RuntimeException` và nhánh `Error` đều unchecked theo compiler.
- [ ] Đọc được `throws IOException` trong chữ ký phương thức.
- [ ] Phân biệt `throws` khai báo với `throw` ném.
- [ ] Biết hai cách xử lý checked: `try-catch` hoặc tiếp tục khai báo `throws`.
- [ ] Hiểu unchecked vẫn có thể bắt nhưng không bị compiler buộc bắt.
- [ ] Sắp xếp các `catch` theo thứ tự kiểu cụ thể trước kiểu tổng quát.
- [ ] Không nhầm `catch (Exception)` với bắt tất cả `Throwable`.
- [ ] Giữ cause/stack trace khi chuyển tiếp hoặc bọc lỗi cần chẩn đoán.
- [ ] Không dùng try-with-resources như lý do bỏ qua checked I/O exceptions.
- [ ] Biên dịch, chạy `CheckedUncheckedDemo.java` trên JDK 17+ và kiểm tra exact stdout.

**Kết luận:** **Checked exception** buộc phía gọi **bắt hoặc khai báo** khả năng ngoại lệ theo quy tắc biên dịch Java. **Unchecked** thuộc nhánh `RuntimeException` hoặc `Error` và không có nghĩa vụ compile-time ấy, nhưng vẫn cần thiết kế xử lý lỗi hợp lý. Hãy nhìn **kiểu kế thừa**, **chữ ký API** và **hợp đồng ứng dụng** trước khi quyết định catch, throws hay sửa logic.