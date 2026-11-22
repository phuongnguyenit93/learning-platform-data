# Quy tắc bắt checked exception mà khối `try` không thể ném trong Java

> **Chủ đề:** Java Core → Exception → Try và catch. Java không cho phép khai báo tùy ý một `catch` dành cho **checked exception cụ thể** nếu phân tích tại thời điểm biên dịch cho thấy khối `try` tương ứng không thể ném ra một checked exception tương thích. Đây là quy tắc về **tính hợp lệ của chương trình ở compile-time**, khác với câu hỏi “ngoại lệ có thực sự xảy ra ở một lần chạy hay không”. Quy tắc có ngoại lệ quan trọng cho `catch (Exception)` và các kiểu cha của `Exception`, điển hình `catch (Throwable)`.

## 1. Câu trả lời cốt lõi

Xét ví dụ trong một phương thức Java:

```java
try {
    int value = Integer.parseInt("123");
    System.out.println(value);
} catch (java.io.IOException e) {
    System.out.println("Lỗi I/O");
}
```

Đoạn trên **không biên dịch**. `Integer.parseInt(String)` không khai báo ném checked `IOException`; `System.out.println` cũng không công bố checked `IOException`. `Integer.parseInt` có thể ném unchecked `NumberFormatException`, nhưng exception đó không thuộc nhánh `IOException`.

Compiler có thể báo tương tự:

```text
exception IOException is never thrown in body of corresponding try statement
```

Thông báo chính xác phụ thuộc compiler/JDK; không coi đây là stdout của chương trình.

Nếu muốn bắt lỗi parse số, dùng handler phù hợp:

```java
try {
    int value = Integer.parseInt("abc");
    System.out.println(value);
} catch (NumberFormatException e) {
    System.out.println("Giá trị nhập không phải số nguyên");
}
```

Đoạn sửa biên dịch được; ở trường hợp `"abc"` nhánh `NumberFormatException` được chọn.

**Quy tắc thực hành:** với một checked exception cụ thể như `IOException`, `SQLException`, `ParseException`, `InterruptedException` hay lớp con tự tạo của `Exception`, compiler đòi hỏi vùng `try` có khả năng ném một checked exception mà handler có thể bắt, trừ ngoại lệ đặc biệt của ngôn ngữ nêu ở Mục 4.

## 2. Thế nào là một checked exception?

Mọi đối tượng được ném trong Java thuộc hệ `java.lang.Throwable`. Hai nhánh lớn:

```text
java.lang.Throwable
├── java.lang.Error
│   └── AssertionError
└── java.lang.Exception
    ├── java.io.IOException
    │   ├── java.io.FileNotFoundException
    │   └── java.io.EOFException
    ├── java.text.ParseException
    ├── java.lang.InterruptedException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        │   └── java.lang.NumberFormatException
        └── java.lang.NullPointerException
```

Các loại được phân biệt:

- **Unchecked exception:** `RuntimeException` và các lớp con, `Error` và các lớp con. Code có thể ném chúng dù không khai báo `throws`; compiler không buộc caller bắt hoặc khai báo.
- **Checked exception:** các lớp con khác của `Throwable` nằm ngoài hai nhánh `RuntimeException` và `Error`. Ví dụ `IOException`, `Exception`, `Throwable` và một lớp trực tiếp `extends Throwable`. Khi chúng có thể thoát ra, quy tắc catch-or-declare áp dụng.
- **`Exception` không đồng nghĩa với checked:** `NumberFormatException` là một `Exception` nhưng vẫn unchecked do kế thừa `RuntimeException`.

Cần phân biệt **hai** phép kiểm tra:

1. Khi một phương thức có thể để checked exception thoát ra, caller thường phải **`catch` hoặc khai báo `throws`** phù hợp.
2. Khi một `catch` khai báo một kiểu checked cụ thể, compiler cũng kiểm tra vùng `try` có **khả năng ném ngoại lệ checked tương thích** hay không.

Bài này tập trung vào phép kiểm tra thứ hai, đồng thời giải thích những trường hợp dễ hiểu nhầm.

## 3. Chính xác compiler kiểm tra điều gì?

Theo quy tắc `try`/`catch` của Java Language Specification (JLS `14.20), với một kiểu checked `E` mà handler có thể bắt, chương trình có thể bị lỗi nếu vùng `try` không thể ném một checked exception có quan hệ kiểu phù hợp với `E`. Có **ngoại lệ đặc biệt** khi `E` là `Exception` hoặc một **lớp cha của `Exception`**.

Diễn đạt dễ sử dụng:

- `catch (IOException e)` yêu cầu vùng `try` có đường có thể ném loại checked liên quan (chẳng hạn `IOException`, subtype như `FileNotFoundException`, hoặc kiểu khai báo rộng như `Exception` có thể chứa `IOException`).
- `catch (ParseException e)` không hợp lệ nếu vùng `try` chỉ gọi những phương thức không khai báo kiểu checked tương thích và không tự ném một kiểu như thế.
- `catch (RuntimeException e)` hợp lệ dù vùng `try` không có dòng nào “rõ ràng” ném unchecked exception.
- `catch (Exception e)` hợp lệ ngay cả khi vùng `try` không khai báo phát sinh checked exception.
- `catch (Throwable t)` cũng hợp lệ trong trường hợp tương tự, nhưng bắt rộng như vậy thường không thích hợp ở tầng nghiệp vụ.

**Đây không phải phân tích chứng minh chắc chắn ngoại lệ xảy ra ở runtime.** Compiler chủ yếu dựa vào các kiểu ngoại lệ mà các biểu thức, lời gọi, resource và cấu trúc ngôn ngữ **có thể ném** theo hợp đồng tĩnh, cùng các quy tắc phân tích luồng đặc thù. Một method khai báo `throws IOException` có thể luôn trả về bình thường trong implementation hiện tại, nhưng caller vẫn có thể viết `catch (IOException)` hợp lệ.

### 3.1. Bảng dự đoán khả năng biên dịch

Xét từng cặp vùng `try`/`catch` độc lập:

| Code trong `try` | Handler | Kết quả | Lý do |
| --- | --- | --- | --- |
| `System.out.println("Hi");` | `catch (IOException e)` | **Lỗi biên dịch** | Không có checked `IOException` phù hợp từ vùng `try`. |
| `Integer.parseInt("abc");` | `catch (NumberFormatException e)` | Hợp lệ | `NumberFormatException` là unchecked; có thể bắt. |
| `System.out.println("Hi");` | `catch (RuntimeException e)` | Hợp lệ | Unchecked exception không bị giới hạn bởi quy tắc catch checked cụ thể. |
| `System.out.println("Hi");` | `catch (Exception e)` | Hợp lệ | `Exception` là trường hợp được JLS cho phép đặc biệt. |
| `System.out.println("Hi");` | `catch (Throwable t)` | Hợp lệ | `Throwable` là lớp cha của `Exception`. |
| `readFromFile();` với `throws IOException` | `catch (IOException e)` | Hợp lệ | Chữ ký method con công bố đường có thể ném `IOException`. |
| `readFromFile();` với `throws IOException` | `catch (FileNotFoundException e)` | Có thể hợp lệ nếu các handler còn lại/khai báo bao phủ checked exceptions | `FileNotFoundException` là subtype có thể nằm trong `IOException` công bố. |
| `readFromFile();` với `throws IOException` | `catch (SQLException e)` | Lỗi nếu không có nguồn SQLException khác | Hai nhánh checked khác nhau, không tương thích. |

Trong trường hợp handler chỉ bắt subtype `FileNotFoundException` từ method khai báo `throws IOException`, compiler vẫn cần code giải quyết **phần IOException còn lại** bằng handler tiếp theo hoặc `throws IOException` của method bao quanh. Khả năng handler tồn tại hợp lệ không tự có nghĩa đã xử lý đầy đủ mọi checked exception.

## 4. Vì sao `catch (Exception)` và `catch (Throwable)` thường không bị lỗi “never thrown”?

Đây là ngoại lệ quan trọng cần nhớ chính xác:

```java
try {
    System.out.println("Hello");
} catch (Exception e) {
    System.out.println("Có Exception");
}
```

Đoạn này **hợp lệ về mặt biên dịch**, dù `println` không khai báo ném một checked `Exception`. `catch (Exception)` có phạm vi bao gồm cả `RuntimeException`; quan trọng hơn, JLS có ngoại lệ trực tiếp cho `Exception` và các lớp cha của nó trong kiểm tra checked exception “not thrown”. `catch (Throwable)` cũng nằm trong ngoại lệ này.

Đặt cạnh đó:

```java
try {
    System.out.println("Hello");
} catch (java.io.IOException e) {
    System.out.println("Có IOException");
}
```

Lại **không hợp lệ**, vì `IOException` là checked subtype cụ thể và vùng `try` không có khả năng ném checked exception tương thích.

Đừng suy luận rằng vì `Exception` là checked nên `catch (Exception)` phải bị cấm. Đây là một **ngoại lệ được định nghĩa trong quy tắc biên dịch**, không phải lỗ hổng của compiler. Tương tự, sự hợp lệ của `catch (Throwable)` **không** đồng nghĩa nó là handler an toàn cho chương trình: nó có thể bắt cả `Error` mà code nghiệp vụ không nên nuốt.

### 4.1. Hợp lệ về cú pháp chưa có nghĩa là handler sẽ chạy

```java
try {
    System.out.println("OK");
} catch (Exception e) {
    System.out.println("Không mong đợi");
}
```

Chỉ với ví dụ trên, stdout bình thường là:

```text
OK
```

Handler không chạy vì không có `Exception` nào được ném trong lần chạy đó. Java cho phép khai báo handler này, nhưng không tự tạo lỗi để kích hoạt nó.

### 4.2. Không lẫn với handler bị che bởi loại cha

Đoạn sau **vẫn sai**, dù `catch (Exception)` đứng trong trường hợp đặc biệt:

```java
try {
    System.out.println("Hello");
} catch (Exception e) {
    System.out.println("Exception");
} catch (RuntimeException e) {
    System.out.println("RuntimeException");
}
```

Handler `RuntimeException` đứng sau đã bị `Exception` bao phủ, nên compiler báo handler không thể tới được. **Hai quy tắc riêng biệt** cùng tồn tại:

- Quy tắc “try có thể ném checked exception mà catch nhận hay không?”
- Quy tắc “handler này có bị handler đứng trước bao phủ hoàn toàn hay không?”

Dù được miễn quy tắc thứ nhất, `catch (Exception)` vẫn có thể làm các handler phía sau trở thành unreachable.

## 5. Chương trình Java 17: ba handler hợp lệ, dù không có checked exception

Tạo tệp `LegalCatchWithoutCheckedDemo.java`:

```java
public class LegalCatchWithoutCheckedDemo {
    static void inspect(boolean bad) {
        try {
            int value = bad
                    ? Integer.parseInt("không-phải-số")
                    : Integer.parseInt("20");
            System.out.println("Giá trị: " + value);
        } catch (NumberFormatException e) {
            System.out.println("Lỗi parse: "
                    + e.getClass().getSimpleName());
        } catch (Exception e) {
            System.out.println("Exception khác: "
                    + e.getClass().getSimpleName());
        } finally {
            System.out.println("Hoàn tất lượt kiểm tra");
        }
    }

    public static void main(String[] args) {
        inspect(false);
        inspect(true);
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac -encoding UTF-8 LegalCatchWithoutCheckedDemo.java
java LegalCatchWithoutCheckedDemo
```

Stdout chính xác:

```text
Giá trị: 20
Hoàn tất lượt kiểm tra
Lỗi parse: NumberFormatException
Hoàn tất lượt kiểm tra
```

Tại sao hai `catch` hợp lệ?

1. `NumberFormatException` thuộc nhánh unchecked `RuntimeException`.
2. `catch (Exception)` được phép dù vùng `try` không có checked exception nào được khai báo.
3. Handler hẹp `NumberFormatException` đặt trước handler rộng `Exception` để tránh lỗi unreachable.
4. `finally` thường được thực hiện sau mỗi lượt, kể cả khi có exception được bắt. Trong ví dụ này nó in một dòng sau cả hai tình huống.

Chương trình không có checked exception ở đường parse; không cần `throws IOException` hay một `catch IOException` giả tạo.

## 6. Trường hợp sai: bắt `IOException` khi `try` chỉ xử lý dữ liệu trong bộ nhớ

Ví dụ sau là một chương trình **cố ý không biên dịch**; lưu thành `InvalidCheckedCatchDemo.java` chỉ khi bạn muốn quan sát chẩn đoán compiler:

```java
import java.io.IOException;

public class InvalidCheckedCatchDemo {
    public static void main(String[] args) {
        try {
            int number = Integer.parseInt("123");
            System.out.println(number);
        } catch (IOException e) {
            System.out.println("I/O thất bại");
        }
    }
}
```

Chạy lệnh kiểm tra:

```bash
javac -encoding UTF-8 InvalidCheckedCatchDemo.java
```

**Kết quả mong đợi:** `javac` không tạo chương trình hợp lệ vì `IOException` không được ném từ vùng `try` tương ứng. Đường đi của `Integer.parseInt` có thể ném `NumberFormatException` (unchecked), không phải checked `IOException`. Không nên dự báo stdout, vì chương trình không biên dịch.

### 6.1. Sửa theo lỗi thực sự có thể xảy ra

Nếu nhu cầu là xử lý input không parse được, sửa handler:

```java
catch (NumberFormatException e) {
    System.out.println("Không thể chuyển thành số");
}
```

Đây là **đoạn handler để thay thế**, không đứng độc lập ngoài `try`. Nếu muốn đọc dữ liệu từ file, hãy thực sự dùng API đọc có thể ném `IOException` (và cân nhắc try-with-resources) thay vì thêm một handler checked không liên quan.

### 6.2. Không sửa bằng cách viết `throws IOException` trên method chứa `try`

Chỉ thêm:

```java
public static void main(String[] args) throws java.io.IOException {
    // Vùng try chỉ parse số.
}
```

**không làm `catch (IOException)` bên trong tự trở nên hợp lệ**. `throws` trên method ngoài chỉ công bố ngoại lệ có thể **thoát khỏi method**; nó không khiến các câu lệnh bên trong `try` bất ngờ có khả năng ném `IOException`.

Ngược lại, thay đổi **chữ ký của một method con thực sự được gọi trong `try`** có thể làm quy tắc checked catch thay đổi vì vùng `try` nay có một lời gọi khai báo kiểu checked tương ứng.

## 7. Một lời gọi có `throws` làm `catch` hợp lệ dù lần chạy không có lỗi

Tạo `DeclaredThrowsCatchDemo.java`:

```java
import java.io.IOException;

public class DeclaredThrowsCatchDemo {
    static String readConfig(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("Không có cấu hình");
        }
        return "ready";
    }

    public static void main(String[] args) {
        for (boolean fail : new boolean[] {false, true}) {
            try {
                System.out.println("Cấu hình: " + readConfig(fail));
            } catch (IOException e) {
                System.out.println("Lỗi đọc: " + e.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DeclaredThrowsCatchDemo.java
java DeclaredThrowsCatchDemo
```

Stdout:

```text
Cấu hình: ready
Lỗi đọc: Không có cấu hình
```

- `readConfig` công bố `throws IOException`.
- Ở lượt `false`, không có exception: Java không yêu cầu một handler phải được chạy mới được coi là hợp lệ.
- Ở lượt `true`, `IOException` thực sự được ném: handler tương ứng chạy.
- Khả năng `try` ném checked exception được xét theo lời gọi `readConfig(fail)` và chữ ký của method, không dựa vào việc người lập trình “biết trước” một lần chạy sẽ đi nhánh nào.

### 7.1. Implementation không thật sự ném nhưng vẫn khai báo `throws`

Phương thức có thể viết:

```java
static String cachedValue() throws java.io.IOException {
    return "cached";
}
```

Một caller trực tiếp có thể bắt `IOException` quanh lời gọi `cachedValue()`, dù thân hiện tại chỉ trả về chuỗi. Trình biên dịch caller dựa trên **hợp đồng khai báo của method**. Trong mã sản xuất, nên giữ chữ ký phản ánh khả năng thất bại thực tế hoặc hợp đồng interface, tránh khai báo checked exception rộng vô ích; nhưng hợp lệ về ngôn ngữ không phụ thuộc vào việc một lần chạy đã thực sự ném.

## 8. Quan hệ kế thừa: `try` có thể ném kiểu cha hoặc kiểu con

Không nhất thiết kiểu checked trong `throws` phải **giống hệt** tên trong `catch`.

Ví dụ hợp lệ và có ý nghĩa:

```java
static void load() throws java.io.IOException {
    throw new java.io.FileNotFoundException("Thiếu file");
}
```

Caller có thể dùng:

```java
try {
    load();
} catch (java.io.FileNotFoundException e) {
    System.out.println("Chọn tệp khác");
} catch (java.io.IOException e) {
    System.out.println("I/O khác");
}
```

Các đoạn trên là minh họa phương thức và lời gọi; cần đặt trong lớp/method đúng ngữ cảnh. Dù `load()` khai báo `throws IOException`, thực tế có thể ném `FileNotFoundException` — một lớp con. Handler con đứng trước handler cha là hợp lệ. Handler `IOException` còn lại xử lý mọi `IOException` khác có thể phát sinh theo hợp đồng.

### 8.1. Catch subtype của loại checked được khai báo rộng

Giả sử `read() throws IOException`; có thể viết `catch (EOFException)` trước `catch (IOException)` dù chữ ký chỉ nói `IOException`. Lý do: một đối tượng thuộc `EOFException` cũng là `IOException`, nên đường checked tương ứng **không bị loại trừ bởi khai báo kiểu cha**.

Tương tự, nếu `operation() throws Exception`, vùng `try` có thể bị xem là có khả năng ném `IOException` hoặc `ParseException` ở mức kiểu, nhưng **caller vẫn phải xử lý phần `Exception` còn lại**. Không thể chỉ viết handler cho hai subtype rồi coi `throws Exception` đã được xử lý hết.

### 8.2. Catch loại checked không có quan hệ kế thừa sẽ bị lỗi

Nếu vùng `try` chỉ gọi `read() throws IOException`, thì `catch (java.sql.SQLException e)` không hợp lệ khi không có nguồn checked `SQLException` khác trong vùng `try`. Cả hai cùng kế thừa `Exception` không đủ: `IOException` và `SQLException` là hai nhánh khác nhau, nên ném một `IOException` không tạo khả năng ném `SQLException`.

**Mẹo:** đọc chuỗi tổ tiên của kiểu lỗi. Handler `catch (Parent)` bắt `Child` nếu `Child extends Parent`. Ngược lại, khi phương thức **khai báo một kiểu cha** trong `throws`, compiler có thể cho phép handler subtype vì một đối tượng thuộc subtype vẫn thỏa kiểu cha đã khai báo.

## 9. Try-with-resources: `close()` cũng là nguồn checked exception

Một trường hợp rất dễ bỏ sót: ngay cả khi **thân `try` không tự đọc hay ném checked exception**, thao tác **đóng resource** trong try-with-resources có thể khai báo checked exception. Khi đó handler checked là hợp lệ.

Tạo `ResourceCloseCatchDemo.java`:

```java
import java.io.IOException;

public class ResourceCloseCatchDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Đóng thất bại");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Đang thực hiện");
        } catch (IOException e) {
            System.out.println("Lỗi tài nguyên: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ResourceCloseCatchDemo.java
java ResourceCloseCatchDemo
```

Stdout chính xác:

```text
Đang thực hiện
Đang đóng
Lỗi tài nguyên: Đóng thất bại
```

Vì sao `catch (IOException)` hợp lệ dù thân khối chỉ có `println`?

- Resource `Resource` triển khai `AutoCloseable` và `close() throws IOException`.
- Try-with-resources thực thi `close()` khi rời khối.
- `close()` có thể ném checked `IOException`, nên toàn bộ construct có đường lỗi phù hợp với handler.
- Exception do `close()` được bắt ở `catch` gắn với try-with-resources đó.

Với nhiều resource, Java đóng theo thứ tự ngược thứ tự khai báo. Nếu thân khối đã ném exception và `close()` cũng ném, lỗi đóng thường được ghi vào `getSuppressed()` của exception chính, thay vì tự thay thế ngoại lệ đầu tiên.

### 9.1. Không phải mọi `close()` đều khai báo IOException

Ví dụ `StringReader.close()` không khai báo checked `IOException`; tạo `StringReader` với chuỗi và chỉ gọi `println` trong thân khối sẽ không tự khiến `catch (IOException)` hợp lệ chỉ vì tên cấu trúc là try-with-resources.

Điều quan trọng là **kiểu và phương thức `close()` thực tế được compiler nhìn thấy**, cùng các constructor/initializer và thao tác trong thân khối. Nếu khai báo resource dưới kiểu rộng `AutoCloseable`, `close()` trong interface công bố `throws Exception`; điều đó có thể tạo nghĩa vụ checked rộng hơn so với dùng kiểu cụ thể có chữ ký `close()` hẹp hơn.

### 9.2. Lỗi từ resource initializer cũng được xét

Phần khởi tạo resource trong `try ( ... )` có thể gọi constructor hoặc phương thức khai báo checked exception. Những lỗi checked phát sinh trong quá trình **tạo resource** cũng thuộc đường lỗi cần xử lý theo quy tắc ngôn ngữ; không chỉ có các câu lệnh trong cặp ngoặc nhọn.

## 10. Multi-catch: mỗi lựa chọn checked vẫn phải có lý do hợp lệ

Cú pháp multi-catch:

```java
catch (java.io.IOException | IllegalArgumentException e) {
    System.out.println(e.getMessage());
}
```

Đây là một handler minh họa, cần đi sau `try`. Một multi-catch có thể gộp nhiều kiểu không có quan hệ kế thừa subtype với nhau, khi chúng được xử lý giống nhau.

Tuy nhiên, việc thêm một nhánh unchecked **không hợp thức hóa** nhánh checked không thể xảy ra:

```java
// CỐ Ý SAI NẾU TRY CHỈ PARSE SỐ:
try {
    Integer.parseInt("123");
} catch (java.io.IOException | NumberFormatException e) {
    System.out.println("Có lỗi");
}
```

`NumberFormatException` là unchecked, phù hợp. Nhưng `IOException` là checked và `try` không thể ném nó, nên cấu trúc trên không hợp lệ.

Cách sửa dựa vào nguồn lỗi có thật:

- Nếu chỉ parse số, bỏ `IOException` khỏi multi-catch.
- Nếu `try` thực sự gọi I/O có `throws IOException`, khi ấy multi-catch có thể hợp lệ nếu các kiểu không có quan hệ subclass với nhau và logic xử lý phù hợp.

**Không được** gộp `IOException | FileNotFoundException` trong một multi-catch, vì `FileNotFoundException extends IOException`. Đây là quy tắc khác với “checked exception không được ném”, nhưng cũng gây lỗi compile-time.

### 10.1. Chương trình Java 17 với hai loại thực sự có thể xảy ra

Tạo `MultiCatchCheckedDemo.java`:

```java
import java.io.IOException;

public class MultiCatchCheckedDemo {
    static void handle(String text) throws IOException {
        if (text == null) {
            throw new IOException("Thiếu nguồn");
        }
        System.out.println("Số: " + Integer.parseInt(text));
    }

    public static void main(String[] args) {
        for (String text : new String[] {"8", "abc", null}) {
            try {
                handle(text);
            } catch (IOException | NumberFormatException e) {
                System.out.println("Lỗi: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MultiCatchCheckedDemo.java
java MultiCatchCheckedDemo
```

Stdout:

```text
Số: 8
Lỗi: NumberFormatException
Lỗi: IOException
```

Đây là trường hợp multi-catch hợp lệ: `handle` công bố `throws IOException`, còn `Integer.parseInt` bên trong có thể phát sinh unchecked `NumberFormatException`. Hai kiểu không có quan hệ cha–con, và cùng dùng một chiến lược hiển thị lỗi.

Biến exception của multi-catch là **implicitly final**; không thể gán lại nó. Khi cần logic xử lý khác nhau cho hai loại, tách ra hai handler riêng giúp hợp đồng rõ hơn.

## 11. Nested `try`, `catch` đã xử lý và `finally`

Câu hỏi “khối `try` có thể ném loại checked nào?” phải đặt trong **phạm vi chính xác** mà handler đang gắn vào.

### 11.1. Exception đã được bắt ở `try` trong

Đoạn minh họa:

```java
try {
    try {
        throw new java.io.IOException("Đã có lỗi");
    } catch (java.io.IOException handled) {
        System.out.println("Đã xử lý ở trong");
    }
} catch (java.io.IOException e) {
    System.out.println("Bắt ở ngoài");
}
```

Đoạn trên **cố ý không biên dịch** vì IOException đã được xử lý bên trong, không còn đường checked IOException truyền ra khỏi thân `try` ngoài. Handler ở ngoài không thể nhận IOException từ tình huống này.

Nếu handler trong `throw handled;` hoặc khối try ngoài thực sự gọi thao tác khác có thể ném IOException, việc đánh giá sẽ khác. Compiler xét khả năng exception có thể **thoát khỏi** cấu trúc con, không đơn giản đếm số chữ `throw` xuất hiện ở mọi cấp.

### 11.2. Exception mới ném trong một `catch` cùng cấp

Xét:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    throw new java.io.IOException("Lỗi chuyển đổi", e);
} catch (java.io.IOException e) {
    System.out.println("Không bắt lỗi vừa ném từ catch bên trên");
}
```

Mảnh trên **cố ý không biên dịch** nếu chỉ có nguồn lỗi như đã nêu: handler `IOException` cuối không nhận exception mới ném trong `catch` khác thuộc cùng `try`; đồng thời method bao quanh phải xử lý/khai báo checked IOException mà handler đầu tạo ra.

Một ngoại lệ mới được ném trong handler cần được xử lý bởi một **`try` mới hoặc phạm vi bên ngoài**, hoặc phải được khai báo tiếp. Các `catch` của cùng một `try` là những nhánh thay thế, không phải chuỗi handler tuần tự.

### 11.3. Exception phát sinh trong `finally`

Một ngoại lệ được ném trong `finally` của cùng construct không được handler `catch` kèm theo xử lý như thể nó đến từ thân `try`. Nó có thể lan lên tầng gọi hoặc handler bên ngoài.

Ví dụ phương thức minh họa:

```java
static void cleanup() throws java.io.IOException {
    try {
        System.out.println("Làm việc");
    } finally {
        throw new java.io.IOException("Lỗi khi dọn dẹp");
    }
}
```

Method phải khai báo `throws IOException`; không thể thêm `catch (IOException)` ở ngay chuỗi handler của `try` cùng cấp để xử lý exception sinh ra từ `finally` đó. Muốn xử lý tại đây, dùng `try` lồng phù hợp ở vị trí dọn dẹp hoặc để caller xử lý theo hợp đồng.

**Đừng nhầm `finally` với try-with-resources:** với try-with-resources, các lỗi checked do `close()` có thể được xử lý bởi `catch` gắn với cấu trúc đó.

## 12. Lý do compiler cần quy tắc này

Một `catch (IOException)` nằm sau `try` chỉ tính toán số nguyên thường biểu đạt sai hợp đồng: code ở vùng `try` không thao tác với nguồn I/O theo thông tin kiểu tĩnh. Quy tắc giúp phát hiện:

1. **Sai loại exception:** người viết nhầm `NumberFormatException` với `IOException`.
2. **Refactor chưa cập nhật:** một lời gọi I/O bị thay bằng tính toán trong RAM nhưng handler cũ vẫn tồn tại.
3. **Hiểu nhầm `throws`:** người viết tưởng thêm `throws` ở method bao ngoài khiến một `catch` bất kỳ hợp lệ.
4. **Nhầm phạm vi:** exception phát sinh trong `catch` hoặc `finally`, nhưng người viết mong handler cùng cấp nhận được.
5. **Multi-catch thừa loại checked:** gom cả những lỗi không có nguồn phát sinh.

Mặt khác, do quy tắc dựa vào **khả năng theo static type** (không phải kết quả chắc chắn mỗi lần chạy), compiler vẫn có thể cho phép handler không bao giờ thực sự chạy, chẳng hạn method con khai báo `throws IOException` nhưng implementation đang luôn trả thành công. Đó là cách chữ ký và tương thích API được duy trì.

## 13. Phân biệt với các lỗi biên dịch gần giống

| Lỗi | Ví dụ ý tưởng | Bản chất |
| --- | --- | --- |
| “exception X is never thrown in body of corresponding try” | `catch(IOException)` sau parse số thuần | Handler checked cụ thể không có nguồn tương thích. |
| “unreported exception X; must be caught or declared” | Gọi `readLine()` không bắt/khai báo `IOException` | Một checked exception có thể thoát nhưng chưa được xử lý đúng. |
| “exception X has already been caught” | `catch(Exception)` đứng trước `catch(IOException)` | Handler trước che phủ handler sau. |
| “Alternatives in a multi-catch statement cannot be related by subclassing” | `catch(IOException \| FileNotFoundException)` | Hai kiểu trong cùng multi-catch có quan hệ cha–con. |
| “unreachable statement” | Câu lệnh bình thường ngay sau một `throw` vô điều kiện | Luồng thực thi không thể tới câu lệnh đó. |
| “incompatible types ... cannot be converted to Throwable” | `throw "error";` | Biểu thức sau `throw` không phải kiểu throwable phù hợp. |

Khi gặp lỗi, đọc **cụm từ trọng tâm** và kiểm tra quan hệ kiểu giữa nguồn gây lỗi trong `try` và handler; đừng sửa bằng cách thêm `catch (Exception)` ở mọi nơi nếu không biết phần nào cần xử lý.

## 14. Các sai lầm phổ biến và cách sửa

### 14.1. “Bất kỳ `catch` nào cũng hợp lệ vì JVM có thể gặp lỗi bất ngờ”

Không đúng với checked exception cụ thể. Một nguồn có thể ném unchecked `RuntimeException` hoặc `Error`, nhưng điều đó không tạo ra khả năng ném `IOException` theo hợp đồng checked. `catch(IOException)` vẫn cần cơ sở trong vùng `try`.

### 14.2. “`catch (Exception)` phải bị cấm nếu `try` không ném checked exception”

Không đúng. `catch (Exception)` được ngôn ngữ cho phép đặc biệt; nó cũng có thể xử lý unchecked `RuntimeException`. Tương tự `catch (Throwable)` vẫn biên dịch nhưng thường quá rộng cho tầng nghiệp vụ.

### 14.3. “Viết một `throws IOException` ở method hiện tại là đủ để catch IOException”

Không. `throws` mô tả checked exception **thoát khỏi method**, không tự đổi nội dung hoặc khả năng ném của `try` con. Đọc chính xác method nào được gọi bên trong `try` và chữ ký của nó.

### 14.4. “Nếu code chỉ tạo `FileNotFoundException` thì `catch(IOException)` bị cấm vì tên khác”

Sai. `FileNotFoundException extends IOException`; handler kiểu cha bắt subtype được. Quy tắc compiler cho phép quan hệ kiểu phù hợp, không đòi tên giống hệt.

### 14.5. “Nếu `try` gọi method throws IOException, `catch(SQLException)` cũng hợp lệ vì cùng checked”

Sai. Hai nhánh không liên quan; không có nguồn checked SQLException được công bố nên handler riêng đó không hợp lệ trong hoàn cảnh đã nêu.

### 14.6. “Try-with-resources chỉ xét lệnh trong cặp ngoặc nhọn”

Sai. Resource initializer và `close()` có thể ném checked exception. `catch(IOException)` có thể hoàn toàn hợp lệ khi thân khối chỉ in một chuỗi, nếu resource `close()` khai báo `throws IOException`.

### 14.7. “Checked exception xuất hiện ở nested try thì outer catch luôn hợp lệ”

Sai. Nếu inner `catch` đã xử lý xong và không ném lại, checked exception tương ứng có thể không thoát ra vùng `try` ngoài. Phải xét **đường truyền thực sự theo cấu trúc**, không chỉ tìm chuỗi `throw IOException` trong file.

### 14.8. “Exception được ném trong `catch` sẽ được handler kế tiếp bắt”

Sai. Các handler cùng cấp là các lựa chọn thay thế cho ngoại lệ thoát khỏi **thân try**. Exception mới trong `catch` phải được xử lý ở một phạm vi khác hoặc khai báo truyền tiếp.

### 14.9. “Compiler luôn chứng minh method con có thể ném thật hay không”

Không. Compiler dùng chữ ký của method con và các quy tắc exception analysis. Một implementation có `throws IOException` dù thân chỉ `return` vẫn đủ tạo khả năng checked cho caller. Đây là cơ chế tương thích khi dùng thư viện/interface.

### 14.10. “Sửa lỗi biên dịch bằng cách nuốt mọi exception”

Không nên. Xóa `IOException` không liên quan khỏi handler khi nguồn lỗi là parse số; hoặc đặt handler ở tầng thực sự xử lý I/O. Bắt rồi bỏ qua lỗi có thể khiến caller hiểu nhầm chương trình đã hoàn tất, còn trạng thái có thể đã thay đổi một phần.

## 15. Bài tập tự kiểm tra

### Bài tập 1 — Hợp lệ hay không?

Đánh giá độc lập các đoạn `try/catch` sau (đặt trong một method thích hợp).

**A.**

```java
try {
    System.out.println(10 / 2);
} catch (java.io.IOException e) {
    System.out.println("I/O");
}
```

**Đáp án:** không hợp lệ. Vùng `try` không có nguồn checked IOException.

**B.**

```java
try {
    System.out.println(10 / 2);
} catch (Exception e) {
    System.out.println("Exception");
}
```

**Đáp án:** hợp lệ; `Exception` là ngoại lệ đặc biệt của quy tắc.

**C.**

```java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException e) {
    System.out.println("Bad number");
}
```

**Đáp án:** hợp lệ; `NumberFormatException` là unchecked. Khi chạy, in `Bad number`.

**D.**

```java
try {
    Thread.sleep(1);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
```

**Đáp án:** hợp lệ; `Thread.sleep` khai báo checked `InterruptedException`. Khi bắt interruption, khôi phục interrupt flag có thể phù hợp với chính sách dừng tác vụ; ví dụ không có stdout ổn định vì phụ thuộc thread interruption.

### Bài tập 2 — Thay lời gọi và quan sát compiler

Tạo method `static String read() throws IOException` rồi đặt lời gọi trong `try` có `catch(IOException)`. Sau đó thay lời gọi bằng `return "OK"` hoặc `println("OK")` trong vùng `try`. Vì sao handler checked trở nên không hợp lệ? Việc xóa nguồn khả năng ném checked exception là thay đổi hợp đồng tại phạm vi đó.

### Bài tập 3 — Kiểu cha và kiểu con

Một method khai báo `throws IOException` và bên trong có thể ném `EOFException`. Viết handler `catch(EOFException)` trước `catch(IOException)`. Giải thích lý do cả hai hợp lệ và handler thứ hai còn cần để xử lý các loại IOException khác.

### Bài tập 4 — Resource đóng lỗi

Chạy `ResourceCloseCatchDemo`, sau đó sửa `Resource.close()` để không khai báo/ném IOException và chỉ in “Đang đóng”. Có còn nguồn checked IOException nào trong `try` không? Nếu không, `catch(IOException)` trở thành không hợp lệ. Hãy sửa handler để chương trình biên dịch lại mà vẫn đóng tài nguyên.

### Bài tập 5 — Multi-catch

Tại sao `catch(IOException | NumberFormatException)` hợp lệ trong `MultiCatchCheckedDemo` nhưng lại sai khi vùng `try` chỉ gọi `Integer.parseInt(...)`? Giải thích riêng hai ý: nguồn checked IOException và unchecked NumberFormatException.

### Bài tập 6 — Exception đã được xử lý ở trong

Dùng nested `try` ở Mục 11.1. Thêm `throw handled;` trong inner handler (và khai báo hoặc xử lý hợp lệ ở phạm vi ngoài). Lý giải vì sao việc ném lại làm outer `catch(IOException)` nhận được ngoại lệ, thay vì inner handler hoàn tất bình thường.

## 16. Checklist trước khi thêm một checked `catch`

- [ ] Tôi biết exception cần bắt là checked hay unchecked chưa?
- [ ] Có lời gọi, `throw` hoặc resource nào trong **đúng vùng try** có thể ném checked exception tương thích không?
- [ ] Đã xét initializer và `close()` của try-with-resources chưa?
- [ ] Đã kiểm tra quan hệ cha–con giữa kiểu trong `throws` và kiểu `catch` chưa?
- [ ] Exception có bị xử lý hoàn toàn bởi nested `catch` trước khi tới handler này không?
- [ ] Ngoại lệ có thực ra phát sinh ở `catch`/`finally` cùng cấp, ngoài phạm vi mà handler này bảo vệ không?
- [ ] Có nhầm một unchecked exception từ parser với checked IOException không?
- [ ] Có biết quy tắc đặc biệt của `catch(Exception)` và `catch(Throwable)` mà vẫn cân nhắc phạm vi bắt phù hợp không?
- [ ] Với multi-catch, mọi lựa chọn checked đều có cơ sở và các kiểu không bao phủ nhau chưa?
- [ ] Nếu chỉ cần báo input sai, tôi đã chọn loại ngoại lệ đúng thay vì thêm handler checked không liên quan chưa?
- [ ] Các handler đã theo thứ tự cụ thể trước tổng quát, không có nhánh unreachable chưa?
- [ ] Code có còn phân biệt thất bại và thành công đúng hợp đồng, không nuốt lỗi quan trọng chưa?

**Ghi nhớ:** compiler không cho phép `catch` một **checked exception cụ thể** khi vùng `try` không thể ném checked exception tương thích, với ngoại lệ ngôn ngữ cho `Exception` và các kiểu cha của nó. Hãy xét **nguồn ngoại lệ theo chữ ký kiểu và phạm vi `try`**, rồi mới quyết định handler; tránh tự tạo `catch` thừa hoặc thay mọi lỗi bằng một handler quá rộng.