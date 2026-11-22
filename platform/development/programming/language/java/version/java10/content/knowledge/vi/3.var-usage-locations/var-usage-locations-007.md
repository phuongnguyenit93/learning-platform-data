# Giới hạn của `var` trong tham số `catch` (Java 10 và JDK hiện đại)

## 1. Quy tắc cần nhớ

**Không được khai báo tham số của `catch` bằng `var`.** Cú pháp `catch (var ex)` là lỗi biên dịch trong Java 10 và vẫn không hợp lệ trên các phiên bản Java hiện đại. Đây là một giới hạn của tính năng **local-variable type inference** (suy luận kiểu biến cục bộ) được giới thiệu trong Java 10.

```java
// KHÔNG HỢP LỆ — chỉ minh họa lỗi, đừng đặt trong chương trình thực thi.
try {
    Integer.parseInt("abc");
} catch (var ex) {                // Lỗi biên dịch: var không được dùng làm kiểu của catch.
    System.out.println(ex.getMessage());
}
```

Cần khai báo **kiểu ngoại lệ cụ thể** hoặc **nhiều kiểu ngoại lệ tường minh** bằng multi-catch:

```java
// HỢP LỆ — catch một kiểu ngoại lệ.
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

```java
// HỢP LỆ — multi-catch, khi try có thể ném cả hai kiểu ngoại lệ.
try {
    readNumber();
} catch (java.io.IOException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
}
```

Trong ví dụ multi-catch vừa nêu, `readNumber()` là tên phương thức minh họa, có thể ném `IOException` hoặc `NumberFormatException`; đoạn này **không phải một chương trình độc lập**. Phần lab phía dưới cung cấp tệp đầy đủ có thể chạy.

## 2. Vì sao `catch (var ex)` không hợp lệ?

`var` cho phép compiler suy luận **kiểu tĩnh** từ biểu thức khởi tạo của biến cục bộ, chẳng hạn `var count = 5;` được suy luận là `int`. Nó không biến Java thành ngôn ngữ có kiểu động và không có nghĩa là “chấp nhận mọi kiểu”.

Tham số của `catch` thuộc loại *exception parameter*, không phải khai báo biến cục bộ có initializer. Cú pháp ngôn ngữ yêu cầu:

```text
catch (ExceptionType ex) { ... }
catch (TypeA | TypeB ex) { ... }
```

`ExceptionType`, `TypeA`, `TypeB` phải là kiểu lớp có thể bắt ngoại lệ (là `Throwable` hoặc lớp con). Compiler cần các kiểu tường minh đó để xác định ngoại lệ nào được bắt, kiểm tra ngoại lệ checked và phát hiện những nhánh `catch` không thể tới được. Không có một biểu thức khởi tạo tại vị trí tham số `catch` để `var` suy luận kiểu.

Theo Java Language Specification, `CatchFormalParameter` sử dụng `CatchType` là một kiểu lớp hoặc một union của nhiều kiểu lớp. `var` không thuộc cú pháp đó. Vì vậy, không tồn tại lựa chọn compiler nào để tự “đoán” kiểu trong `catch (var ex)` dựa trên các câu lệnh trong `try`.

### Bảng phân biệt các vị trí

| Vị trí | Ví dụ | Hợp lệ? | Giải thích |
| --- | --- | --- | --- |
| Tham số `catch` | `catch (var ex)` | **Không** | `catch` bắt buộc khai báo kiểu ngoại lệ. |
| Tham số `catch` một kiểu | `catch (IOException ex)` | **Có** | Kiểu ngoại lệ được khai báo tường minh. |
| Tham số multi-catch | `catch (IOException \| NumberFormatException ex)` | **Có** | Khai báo một tập kiểu ngoại lệ hợp lệ, không phải suy luận `var`. |
| Biến bên trong khối `catch` | `var message = ex.getMessage();` | **Có** | Đây là khai báo biến cục bộ **có initializer**; kiểu suy luận là `String`, dù giá trị thực có thể `null`. |
| Biến tài nguyên trong `try-with-resources` | `try (var reader = new BufferedReader(...))` | **Có** | Đây là biến resource có initializer, được phép suy luận kiểu. |
| Biến cục bộ trong `try` | `var number = Integer.parseInt("42");` | **Có** | Biểu thức khởi tạo xác định kiểu `int`. |

Hai vị trí dễ nhầm nhất là **tham số `catch`** và **biến trong thân `catch`**:

```java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException ex) {     // Phải viết kiểu cụ thể.
    var errorType = ex.getClass().getSimpleName(); // Được phép: biến cục bộ.
    System.out.println(errorType);
}
```

Lệnh trên in `NumberFormatException`. Lưu ý rằng các đoạn ví dụ ngắn ở phần này mô tả mã **trong một phương thức**; chương trình hoàn chỉnh xuất hiện ở phần tiếp theo.

## 3. Lab chạy được: uni-catch, multi-catch và `var` đúng vị trí

### 3.1. Chuẩn bị

Dùng JDK hiện đại còn được nhà cung cấp bảo trì (ví dụ một bản phân phối JDK 21 hoặc 25 LTS có cập nhật bảo mật). Mọi cú pháp chính trong lab đều phù hợp từ Java 10; không yêu cầu cài lại JDK 10 đã cũ. Kiểm tra môi trường:

```bash
java -version
javac -version
```

Lưu mã dưới đây vào **`CatchVarLimits.java`**. Tên tệp phải khớp với tên `public class`.

### 3.2. Chương trình hoàn chỉnh

```java
public class CatchVarLimits {
    public static void main(String[] args) {
        demoSingle();
        process("42", false);
        process("abc", false);
        process("99", true);
    }

    private static void demoSingle() {
        try {
            var age = Integer.parseInt("unknown");
            System.out.println(age);
        } catch (NumberFormatException ex) {
            var exceptionName = ex.getClass().getSimpleName();
            System.out.println("SINGLE: " + exceptionName);
        }
    }

    private static void process(String input, boolean failRead) {
        // var ở đây hợp lệ: reader là biến tài nguyên có initializer.
        try (var reader = new java.io.BufferedReader(newReader(input, failRead))) {
            var line = reader.readLine();
            var value = Integer.parseInt(line);
            System.out.println("OK: " + value);
        } catch (java.io.IOException | NumberFormatException ex) {
            // var ở đây hợp lệ: kind là biến cục bộ trong thân catch.
            var kind = ex.getClass().getSimpleName();
            System.out.println("HANDLED: " + kind);
        }
    }

    private static java.io.Reader newReader(String input, boolean failRead) {
        if (!failRead) {
            return new java.io.StringReader(input);
        }

        // Chỉ để mô phỏng lỗi đọc dữ liệu, không cần tệp ngoài.
        return new java.io.Reader() {
            @Override
            public int read(char[] buf, int off, int len) throws java.io.IOException {
                throw new java.io.IOException("simulated read failure");
            }

            @Override
            public void close() {
            }
        };
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac CatchVarLimits.java
java CatchVarLimits
```

### 3.3. Kết quả chuẩn (stdout)

```text
SINGLE: NumberFormatException
OK: 42
HANDLED: NumberFormatException
HANDLED: IOException
```

**Giải thích từng lời gọi:**

1. `demoSingle()`: `Integer.parseInt("unknown")` ném `NumberFormatException`, và `catch (NumberFormatException ex)` bắt đúng ngoại lệ. `var exceptionName` được chấp nhận vì có initializer trong **thân** `catch`.
2. `process("42", false)`: `StringReader` đọc chuỗi `"42"`, parse thành công, in `OK: 42`. Không chạy nhánh `catch`.
3. `process("abc", false)`: đọc được `"abc"` nhưng `Integer.parseInt` ném `NumberFormatException`, được multi-catch xử lý.
4. `process("99", true)`: một `Reader` mô phỏng ném `IOException` khi đọc, nên multi-catch bắt ngoại lệ này và in `HANDLED: IOException`. Không phải phụ thuộc tệp có sẵn hoặc hệ điều hành.

Trong `try (var reader = ...)`, compiler suy luận `reader` là `BufferedReader` vì initializer trả về đối tượng `BufferedReader`. Trong `catch (IOException | NumberFormatException ex)`, compiler biết **hai kiểu ngoại lệ được bắt** nhờ khai báo union; đây không phải là suy luận kiểu `var`. Biến `kind` lại là biến cục bộ bình thường, được suy luận là `String`.

## 4. Chọn cách khai báo `catch` phù hợp

### 4.1. Catch theo kiểu cụ thể

```java
try {
    var number = Integer.parseInt("oops");
    System.out.println(number);
} catch (NumberFormatException ex) {
    System.out.println("Đầu vào không phải số nguyên hợp lệ");
}
```

Đây là cách thường nên chọn khi biết rõ thao tác có thể lỗi thế nào. Nó giữ chính xác ngữ nghĩa xử lý và không che các lỗi không liên quan. Không cần ép kiểu `ex` khi đã khai báo rõ `NumberFormatException`.

### 4.2. Multi-catch khi nhiều ngoại lệ có chung cách xử lý

```java
try {
    runOperation();
} catch (java.io.IOException | java.sql.SQLException ex) {
    logFailure(ex);
}
```

`runOperation()` và `logFailure(ex)` là **tên hàm minh họa**, chưa được khai báo trong đoạn trên; chỉ sử dụng cấu trúc này khi thao tác bên trong `try` có thể ném các kiểu checked exception tương ứng.

Multi-catch giúp tránh lặp lại phần xử lý khi những kiểu ngoại lệ **không có quan hệ kế thừa trực tiếp với nhau** cần được xử lý giống nhau. Trong lab, `IOException` và `NumberFormatException` là ví dụ hợp lệ. Tham số multi-catch có kiểu tĩnh là kiểu chung do Java xác định từ các nhánh union, vì vậy các phương thức dùng trực tiếp trên `ex` cần có trong kiểu chung. `getMessage()` và `getClass()` dùng được cho các ngoại lệ đó.

Một tham số multi-catch được coi như **`final`**: không thể gán lại `ex` trong thân `catch`. Đây là quy tắc của multi-catch, không liên quan đến `var`:

```java
// KHÔNG HỢP LỆ — đoạn dưới để minh họa lỗi gán lại biến multi-catch.
try {
    operationThatMayThrow();
} catch (java.io.IOException | NumberFormatException ex) {
    ex = new java.io.IOException("replacement"); // Lỗi biên dịch: ex là final ngầm định.
}
```

`operationThatMayThrow()` chỉ là placeholder của ví dụ lỗi, không phải phương thức độc lập. Với uni-catch thông thường, biến không tự động `final`, nhưng vẫn nên tránh thay tham chiếu ngoại lệ vì làm khó theo dõi nguyên nhân gốc.

### 4.3. `catch (Exception ex)` hợp lệ nhưng cần thận trọng

```java
try {
    runTask();
} catch (Exception ex) {
    reportFailure(ex);
}
```

Hai hàm `runTask()` và `reportFailure(ex)` là minh họa. `Exception` là một kiểu tường minh hợp lệ, nhưng bắt quá rộng có thể gom nhiều lỗi vào cùng một cách xử lý không thích hợp. Trong mã ứng dụng, ưu tiên kiểu cụ thể hoặc multi-catch của những ngoại lệ thật sự có cùng chính sách xử lý; nếu bắt rộng ở biên tầng ứng dụng, phải có chiến lược log, chuyển đổi hoặc truyền lỗi phù hợp.

## 5. Những lỗi biên dịch hay gặp

| Mã | Vấn đề | Cách sửa |
| --- | --- | --- |
| `catch (var ex)` | `var` không được phép tại vị trí catch formal parameter. | `catch (NumberFormatException ex)` hoặc kiểu phù hợp. |
| `catch (IOException \| Exception ex)` | `IOException` là lớp con của `Exception`, union chứa hai lựa chọn chồng lấn. | Chọn `Exception` một mình nếu thực sự cần bắt rộng, hoặc liệt kê hai loại không cùng nhánh kế thừa. |
| `catch (IllegalArgumentException \| NumberFormatException ex)` | `NumberFormatException` kế thừa `IllegalArgumentException`, union không hợp lệ. | Chỉ dùng `IllegalArgumentException`, hoặc tách cách xử lý với thứ tự cụ thể trước. |
| `catch (String ex)` | `String` không phải `Throwable` hay lớp con. | Chọn một kiểu ngoại lệ hợp lệ. |
| `catch (Exception ex) ... catch (IOException ex)` | Nhánh `IOException` đứng sau `Exception` đã bắt được mọi `IOException`, nên không tới được. | Đặt nhánh cụ thể trước nhánh tổng quát. |
| Gán lại `ex` trong multi-catch | Tham số multi-catch là `final` ngầm định. | Dùng biến khác khi cần dữ liệu mới; giữ `ex` cho thông tin lỗi. |

**Phân biệt checked và unchecked:** `IOException` là checked exception; một nhánh `catch(IOException ex)` phải tương ứng với khả năng ném ngoại lệ checked từ `try` theo quy tắc biên dịch của Java. `NumberFormatException` là unchecked exception (kế thừa `RuntimeException`). Những quy tắc này giải thích vì sao việc khai báo kiểu ở `catch` mang ý nghĩa kiểm tra mã, không chỉ là chỗ đặt tên cho đối tượng ngoại lệ.

**Đừng nhầm với lambda:** Từ Java 11, `var` được phép trong tham số lambda ngầm định kiểu, ví dụ `(var x) -> x + 1` khi có target type. Quy định đó **không mở rộng** sang tham số `catch`. Trọng tâm Java 10 ở đây là giới hạn của local-variable type inference, vẫn còn hiệu lực trên JDK hiện đại.

## 6. Bài tập tự luyện

**Bài 1 — sửa mã sai.** Cho đoạn:

```java
try {
    Integer.parseInt("12x");
} catch (var err) {
    System.out.println("Invalid number");
}
```

Sửa **chỉ phần khai báo tham số** để compile được; dự đoán output và giải thích vì sao `var` trong `catch` không được chấp nhận. Đáp án cho phần khai báo là `catch (NumberFormatException err)`; output là `Invalid number`.

**Bài 2 — giữ `var` đúng vị trí.** Viết lại phần thân `catch (NumberFormatException err)` để khai báo `var message = err.getMessage();` và in thông điệp lỗi. Xác nhận rằng compiler chấp nhận `var` vì có initializer và biến nằm **bên trong** khối `catch`.

**Bài 3 — multi-catch và kế thừa.** Xét hai khai báo sau:

```java
catch (java.io.IOException | NumberFormatException ex)
catch (IllegalArgumentException | NumberFormatException ex)
```

Chúng là **các dòng cú pháp rời, dùng để phân tích**, không phải chương trình độc lập. Hãy xác định cái nào hợp lệ và giải thích: dòng thứ nhất có hai kiểu khác nhánh; dòng thứ hai chứa `NumberFormatException` là lớp con của `IllegalArgumentException` nên không hợp lệ.

**Bài 4 — kiểm thử đủ nhánh.** Chạy lại `CatchVarLimits` rồi thay `process("abc", false)` thành `process("8", false)`. Dự đoán dòng thứ ba sẽ thành `OK: 8`. Giữ lời gọi `process("99", true)` để chứng minh nhánh `IOException` vẫn hoạt động.

**Bài 5 — sửa lỗi sắp xếp handler.** Nếu xử lý riêng `NumberFormatException` và bắt `Exception` cho các lỗi khác, hãy đặt `catch (NumberFormatException ex)` **trước** `catch (Exception ex)`. Giải thích tại sao đảo ngược thứ tự lại làm nhánh cụ thể không thể tới được.

### Tự đánh giá sau bài

- [ ] Giải thích được vì sao `var` không áp dụng cho tham số `catch` từ Java 10 đến JDK hiện đại.
- [ ] Sửa được `catch (var ex)` thành `catch` khai báo kiểu tường minh phù hợp.
- [ ] Sử dụng được `var` cho biến cục bộ trong `try`/`catch` và biến resource có initializer.
- [ ] Phân biệt uni-catch với multi-catch; không ghép trong union hai kiểu có quan hệ cha–con.
- [ ] Biết multi-catch có tham số `final` ngầm định và biết sắp thứ tự các nhánh `catch`.
- [ ] Biên dịch/chạy lab, đối chiếu đúng bốn dòng output, hiểu nhánh checked/unchecked.

## 7. Tóm tắt áp dụng trong code thực tế

Khi review lỗi biên dịch liên quan `catch (var ex)`, hãy tìm loại ngoại lệ mà logic xử lý thực sự cần bắt, rồi khai báo kiểu đó trực tiếp ở tham số `catch`. Nếu nhiều loại ngoại lệ có chung cách xử lý, dùng multi-catch hợp lệ. Có thể tiếp tục dùng `var` trong thân `catch` cho các giá trị được tính từ `ex`, miễn mỗi biến có initializer rõ kiểu. Quy tắc này còn hữu ích trong JDK mới; không cần dùng Java 10 hết vòng đời để thử nghiệm.

### Tài liệu chuẩn

- [OpenJDK JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi `var` khi được giới thiệu trong Java 10; loại trừ tham số `catch`.
- [Oracle – Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): mô tả suy luận kiểu biến cục bộ và các vị trí được phép.
- [Java Language Specification, `14.20 – The try Statement](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20): cú pháp `CatchFormalParameter` và `CatchType`, multi-catch, `final` ngầm định.