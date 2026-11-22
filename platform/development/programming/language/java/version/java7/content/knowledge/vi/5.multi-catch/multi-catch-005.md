# Quy tắc không gán lại tham số multi-catch trong Java

## 1. Mục tiêu và bối cảnh

Trong xử lý ngoại lệ, nhiều lỗi khác loại có thể cần **cùng một cách phản ứng**: ghi nhận lỗi, chuyển thành kết quả thất bại, bổ sung ngữ cảnh rồi ném tiếp. Kể từ **Java 7**, cú pháp *multi-catch* cho phép viết nhiều loại ngoại lệ trong cùng một nhánh `catch`, ngăn cách bằng dấu `|`:

~~~java
try {
    // Tác vụ có thể gây IOException hoặc IllegalArgumentException
} catch (IOException | IllegalArgumentException ex) {
    // Xử lý chung cho hai loại lỗi
}
~~~

Đây là đoạn minh họa cú pháp, không phải một chương trình độc lập. Quy tắc trọng tâm: **tham số `ex` trong multi-catch là `final` ngầm định (implicitly final)**. Vì vậy, không được viết phép gán mới cho `ex` trong thân nhánh `catch`, kể cả gán bằng ngoại lệ cùng loại hoặc gán lại chính nó. Quy tắc này vẫn là một phần của ngôn ngữ Java hiện đại; bài dùng **Java 21** để thực hành, không yêu cầu chạy một JDK cũ.

Sau bài học, bạn sẽ hiểu lý do không gán lại `ex`, phân biệt `final` ngầm định với `effectively final`, biết cách xử lý hoặc bao bọc ngoại lệ mà không phá hủy tham chiếu gốc, và nhận ra các lỗi biên dịch thường gặp.

## 2. Đọc đúng khai báo multi-catch

~~~java
catch (IOException | IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
~~~

- `IOException` là ngoại lệ **checked**, thường xuất hiện khi thao tác I/O thất bại.
- `IllegalArgumentException` là ngoại lệ **unchecked**, thể hiện một tham số/giá trị không được chấp nhận. `NumberFormatException` là lớp con của `IllegalArgumentException`, nên cũng được nhánh này bắt.
- `|` trong khai báo `catch` phân tách **các loại ngoại lệ thay thế**; nó **không phải** phép toán OR đang tính toán hai giá trị boolean.
- `ex` là **một tham số duy nhất** trong khối `catch`. Khi một ngoại lệ phù hợp được ném, `ex` tham chiếu tới đối tượng ngoại lệ thực sự vừa bị bắt.
- Chỉ **một** thân `catch` được thực thi cho ngoại lệ đó; Java không chạy một vòng lặp qua các lựa chọn kiểu.

Multi-catch phát huy tác dụng khi **chính sách xử lý giống nhau** cho mọi loại được liệt kê. Nếu lỗi I/O cần retry nhưng dữ liệu sai cần trả lỗi validation, hai `catch` riêng thường rõ nghĩa hơn.

## 3. Vì sao `ex` không được gán lại?

Xem đoạn **cố ý sai, không biên dịch**:

~~~java
try {
    throw new IOException("original");
} catch (IOException | IllegalArgumentException ex) {
    ex = new IOException("replacement"); // LỖI BIÊN DỊCH
}
~~~

Trình biên dịch Java 21 báo:

~~~text
error: multi-catch parameter ex may not be assigned
~~~

Dù kiểu của giá trị mới có tương thích hay không, **bản thân việc gán vào tham số multi-catch đã bị cấm**. Những cách viết sau cũng sai trong cùng hoàn cảnh:

~~~java
// Trong catch (IOException | IllegalArgumentException ex):
// ex = null;           // Sai: gán lại ex
// ex = ex;             // Sai: dù giá trị tham chiếu không thay đổi
// ex = otherException; // Sai: không được thay ex bằng tham chiếu khác
~~~

Các dòng trên là ví dụ bị chú thích, không phải các lệnh cần chạy.

### 3.1. `implicitly final` khác gì `effectively final`?

| Trường hợp | Có thể gán lại tham số? | Vì sao? |
| --- | --- | --- |
| `catch (IOException | IllegalArgumentException ex)` | **Không** | `ex` là `final` **ngầm định** theo quy tắc multi-catch |
| `catch (final IOException ex)` | **Không** | `final` được khai báo tường minh |
| `catch (IOException ex)` không có `final` | **Có thể**, nếu phép gán hợp lệ về kiểu | Single-catch không tự động `final` |
| `catch (IOException ex)` không gán lại trong thân | Không có phép gán thực tế; tham số có thể **effectively final** | Trạng thái này phụ thuộc cách sử dụng biến, không phải do khai báo `final` |

Đối với **single-catch** (một loại ngoại lệ), mã sau có thể biên dịch, dù thường **không nên** viết như thế:

~~~java
catch (IOException ex) {
    ex = new IOException("replacement");
}
~~~

Đây là đoạn minh họa được đặt trong một `try/catch` phù hợp. Nếu thêm `final` vào tham số của single-catch, phép gán sẽ bị cấm.

**Điểm cần phân biệt:** JLS mô tả tham số multi-catch là **implicitly final**, không phải chỉ “effectively final”. Còn trong single-catch không khai báo `final`, tham số có thể *effectively final* nếu bạn không gán lại nó. Hai trạng thái có vẻ giống nhau ở code chỉ đọc, nhưng quy tắc kiểm tra phép gán khác nhau.

### 3.2. `final` khóa *tham chiếu*, không đóng băng *đối tượng*

`final` ngăn thay đổi giá trị tham chiếu nằm trong biến `ex`. Nó không tự biến đối tượng `Throwable` thành bất biến và không cấm:

~~~java
String message = ex.getMessage();
String typeName = ex.getClass().getSimpleName();
Throwable cause = ex.getCause();
~~~

Các lệnh trên chỉ đọc thuộc tính của ngoại lệ trong một thân `catch`; chúng không gán lại `ex`. Một số API của `Throwable` có thể thay đổi trạng thái đối tượng (ví dụ bổ sung *suppressed exception*), nhưng đó là chuyện khác với quy tắc gán biến. Trong xử lý lỗi thông thường, hãy **giữ nguyên ngoại lệ gốc**, ưu tiên đọc thông tin hoặc liên kết làm `cause` thay vì tùy tiện sửa nó.

## 4. Cách xử lý khi cần thêm thông tin mà không gán lại tham số

### 4.1. Tạo biến kết quả hoặc thông điệp riêng

~~~java
catch (IOException | IllegalArgumentException ex) {
    String kind = ex instanceof IOException ? "IO" : "INPUT";
    String description = kind + ": " + ex.getMessage();
    System.err.println(description);
}
~~~

Đây là **đoạn minh họa trong một `try/catch`**, không phải chương trình độc lập. `kind` và `description` là biến cục bộ mới. Việc gán chúng không ảnh hưởng tham chiếu `ex`. Kiểm tra `instanceof` giúp phân biệt loại lỗi khi cần thông tin phụ, dù các bước xử lý chung vẫn đặt trong một khối.

Nếu logic cho từng loại bắt đầu khác nhau đáng kể, nên tách thành hai `catch` riêng để tránh một khối chứa quá nhiều phân nhánh.

### 4.2. Bao bọc ngoại lệ, giữ nguyên nguyên nhân gốc

Nếu lớp hiện tại muốn báo lỗi dưới dạng một ngoại lệ có ngữ nghĩa của ứng dụng:

~~~java
catch (IOException | IllegalArgumentException ex) {
    throw new IllegalStateException("Cannot process request", ex);
}
~~~

Đây là đoạn minh họa. Ngoại lệ mới `IllegalStateException` nhận `ex` làm **cause**, giữ chuỗi nguyên nhân để người gọi có thể tìm hiểu lỗi ban đầu. Bạn không cần (và không được) làm như sau:

~~~java
// Sai trong multi-catch:
// ex = new IllegalStateException("Cannot process request", ex);
~~~

**Lưu ý thiết kế:** Không phải mọi ngoại lệ nên được chuyển thành `IllegalStateException`. Chọn kiểu exception mới có ý nghĩa với tầng mã đang gọi; tránh “bọc” lỗi chỉ để làm mất chi tiết phân loại. Nếu muốn tiếp tục đẩy ngoại lệ gốc lên trên, cân nhắc `throw ex;` và khai báo `throws` phù hợp.

### 4.3. Có thể ném lại `ex` mà không gán lại

~~~java
static int parseOrThrow(String text) throws IOException {
    try {
        if ("io".equals(text)) {
            throw new IOException("read failure");
        }
        return Integer.parseInt(text);
    } catch (IOException | IllegalArgumentException ex) {
        throw ex;
    }
}
~~~

Đây là **phương thức minh họa**, không phải file độc lập. `throw ex;` dùng lại tham chiếu ngoại lệ đang có; nó **không** gán lại tham số. Với phân tích *precise rethrow* của trình biên dịch, khai báo `throws IOException` là đủ cho ngoại lệ checked trong ví dụ này; `IllegalArgumentException` là unchecked nên không bắt buộc liệt kê trong `throws`. Điều này không làm thay đổi quy tắc `final`.

Nếu phương thức gọi muốn xử lý ngoại lệ cụ thể, hãy cân nhắc việc khai báo và truyền tiếp checked exception thay vì biến mọi lỗi thành một runtime exception chung.

## 5. Ví dụ Java hoàn chỉnh và có thể chạy

Ví dụ tạo ra hai nhóm lỗi một cách **xác định** để kiểm thử. Nhánh `IOException` được chủ động ném khi nhận từ khóa `"io"` nhằm mô phỏng lỗi I/O; đây là tình huống mô phỏng, không phải thao tác đọc tệp thật. `Integer.parseInt` có thể ném `NumberFormatException` (một `IllegalArgumentException`). Nếu số âm, chương trình ném `IllegalArgumentException` trực tiếp.

Tạo `src/main/java/demo/MultiCatchParameterExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.util.List;

public final class MultiCatchParameterExample {
    private MultiCatchParameterExample() {
    }

    static String parse(String input) {
        try {
            if ("io".equals(input)) {
                throw new IOException("simulated I/O failure");
            }
            int value = Integer.parseInt(input);
            if (value < 0) {
                throw new IllegalArgumentException("negative number");
            }
            return "OK:" + value;
        } catch (IOException | IllegalArgumentException ex) {
            String category = ex instanceof IOException ? "IO" : "INPUT";
            return "ERROR:" + category + ":" + ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        for (String input : List.of("21", "oops", "-2", "io")) {
            System.out.println(input + " -> " + parse(input));
        }
    }
}
~~~

Dùng JDK có trình biên dịch hỗ trợ `--release 21`. Từ thư mục chứa `src/`, chạy:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/MultiCatchParameterExample.java
java -cp out demo.MultiCatchParameterExample
~~~

Stdout chính xác:

~~~text
21 -> OK:21
oops -> ERROR:INPUT:NumberFormatException
-2 -> ERROR:INPUT:IllegalArgumentException
io -> ERROR:IO:IOException
~~~

**Giải thích:**

1. `"21"` chuyển thành số 21, không có ngoại lệ, nhận `OK:21`.
2. `"oops"` không phải literal số nguyên thập phân hợp lệ cho `Integer.parseInt`, vì vậy ném `NumberFormatException`; multi-catch bắt được vì nó là subtype của `IllegalArgumentException`.
3. `"-2"` phân tích thành số âm, bị nhánh validation ném `IllegalArgumentException`.
4. `"io"` gây `IOException` mô phỏng.
5. Cả ba loại lỗi đều đi qua **một `catch`**. Chương trình kiểm tra loại ngoại lệ bằng `instanceof` để tạo nhãn và chỉ **đọc** `ex.getClass().getSimpleName()`, không gán lại tham số.
6. `List.of(...)` là API hiện đại (từ Java 9); bài cố ý kiểm thử toàn bộ chương trình trên mức Java 21. Bản thân cú pháp multi-catch xuất hiện từ Java 7 và vẫn hữu dụng hiện nay.

## 6. Thí nghiệm bắt buộc thất bại khi biên dịch

Để hiểu đây là **lỗi do compiler** chứ không phải ngoại lệ xảy ra lúc chạy, có thể tạo file **riêng** `src/main/java/demo/InvalidReassignment.java`:

~~~java
package demo;

import java.io.IOException;

public class InvalidReassignment {
    void run() {
        try {
            throw new IOException("original");
        } catch (IOException | IllegalArgumentException ex) {
            ex = new IOException("replacement"); // CỐ Ý KHÔNG HỢP LỆ
        }
    }
}
~~~

Biên dịch riêng file minh họa lỗi, **không đưa nó vào lệnh biên dịch của chương trình hợp lệ phía trên**:

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/InvalidReassignment.java
~~~

Kết quả mong đợi là lệnh `javac` kết thúc **khác 0** và có thông báo lỗi trọng tâm:

~~~text
error: multi-catch parameter ex may not be assigned
~~~

Dòng số, đường dẫn file và bố cục con trỏ `^` trong thông báo đầy đủ có thể tùy vị trí code hoặc phiên bản compiler. Đây **không** phải stdout của chương trình Java, mà là thông báo của trình biên dịch ra stderr; không có chương trình hợp lệ để chạy từ file này. Muốn sửa, bỏ phép gán, tạo biến mới hoặc bao bọc ngoại lệ như `new IllegalStateException("...", ex)`.

## 7. Các quy tắc liên quan dễ bị nhầm

### 7.1. Các loại ngoại lệ trong một multi-catch không được quan hệ cha–con

Đoạn sau **không hợp lệ**:

~~~java
// Cố ý sai: FileNotFoundException là subtype của IOException
catch (IOException | java.io.FileNotFoundException ex) {
    // ...
}
~~~

Vì `IOException` đã bao phủ `FileNotFoundException`, không được đặt cả hai vào một multi-catch. Chọn `catch (IOException ex)` nếu xử lý chung; hoặc dùng hai `catch` theo thứ tự từ cụ thể tới tổng quát khi chính sách khác nhau.

Đoạn dùng trong ví dụ hoàn chỉnh, `catch (IOException | IllegalArgumentException ex)`, hợp lệ vì hai lựa chọn không kế thừa lẫn nhau.

### 7.2. `ex` không mặc nhiên có mọi phương thức riêng của các lựa chọn kiểu

Kiểu khai báo của tham số multi-catch được tính từ **least upper bound** của các loại ngoại lệ (theo JLS), không phải “có thể gọi bất kỳ phương thức nào của từng loại”. Các phương thức `getMessage()`, `getCause()`, `getClass()` là an toàn vì có ở kiểu chung. Nếu cần hành vi chỉ có ở một subtype cụ thể, dùng kiểm tra kiểu rõ ràng hoặc tách khối `catch`.

Ví dụ minh họa dùng cú pháp pattern matching `instanceof` có trong Java hiện đại:

~~~java
catch (IOException | IllegalArgumentException ex) {
    if (ex instanceof IOException ioError) {
        System.err.println("I/O: " + ioError.getMessage());
    } else {
        System.err.println("Input: " + ex.getMessage());
    }
}
~~~

Đây là đoạn minh họa, không phải file chạy độc lập. `ioError` là một biến pattern mới trong nhánh đúng, không phải phép gán vào `ex`. Không cần pattern matching nếu chỉ muốn phân nhánh bằng `instanceof IOException` như ví dụ chạy được.

### 7.3. `final` không bắt buộc bạn phải bắt mọi ngoại lệ

Multi-catch phải phù hợp với những ngoại lệ có thể ném ra từ `try` theo quy tắc kiểm tra ngoại lệ của Java. Ngoại lệ checked cần được ném hoặc khai báo/được xử lý đúng. Không bắt rộng `Exception` chỉ để tránh khai báo `throws` khi nghiệp vụ cần phân biệt lỗi. Không bắt `Error` để “nuốt” những lỗi hệ thống nghiêm trọng như một dạng lỗi đầu vào bình thường.

### 7.4. Tránh thay đổi nghĩa của lỗi bằng cách mất `cause`

Nếu muốn tạo lỗi mới, đừng chỉ viết một thông điệp không gắn nguyên nhân rồi vứt tham chiếu `ex`:

~~~java
// Ít thông tin hơn trong nhiều tình huống:
throw new IllegalStateException("Cannot process request");

// Có ngữ cảnh và giữ nguyên cause:
throw new IllegalStateException("Cannot process request", ex);
~~~

Hai dòng trên là các lựa chọn minh họa **bên trong `catch`**, không phải hai lệnh nối tiếp có thể thực thi cùng nhau. Giữ `cause` giúp phân tích root cause, stack trace và chuỗi lỗi, nhưng cần tránh hiển thị dữ liệu nhạy cảm từ exception trực tiếp ra người dùng.

## 8. Khi nào chọn multi-catch, khi nào tách nhánh?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Hai loại lỗi cần cùng phản ứng | `catch (A | B ex)` | Tránh lặp code và giữ chính sách chung |
| Lỗi A retry được, lỗi B phải báo sai đầu vào | Hai `catch` riêng | Xử lý khác nhau về bản chất |
| Cần phân loại nhẹ để ghi log/kết quả | Một multi-catch và `instanceof` nếu rõ ràng | Vẫn dùng được tham chiếu `final` |
| Cần ngoại lệ có thông điệp ngữ cảnh | Tạo wrapper mới với `cause=ex` | Không gán lại `ex` |
| Muốn đẩy nguyên lỗi lên caller | `throw ex;` và khai báo phù hợp | Giữ nguyên đối tượng lỗi |
| Các loại được liệt kê có quan hệ subtype | Bỏ loại dư hoặc tách `catch` phù hợp | Tránh lỗi biên dịch |
| Cố ý gán `ex = ...` | Không làm; dùng biến cục bộ mới | Multi-catch parameter implicitly final |

Đặt sự rõ ràng lên trước việc giảm số dòng. Multi-catch có giá trị khi **hành động chung thực sự giống nhau**; đừng ép các lỗi khác nghĩa vào một nhánh chỉ để viết ít `catch`.

## 9. Tự kiểm tra

**Câu 1.** Đoạn `catch (IOException | IllegalArgumentException ex) { ex = null; }` có biên dịch không?

**Đáp án:** Không. Lý do là **gán lại tham số multi-catch**, không phải vì riêng `null` có kiểu sai.

**Câu 2.** Có thể viết `ex.getMessage()` hoặc truyền `ex` cho một hàm xử lý lỗi không?

**Đáp án:** Có, nếu hàm nhận kiểu tham số tương thích. Đọc hoặc truyền tham chiếu không phải gán lại. `final` áp dụng với biến tham số, không cấm dùng đối tượng đó.

**Câu 3.** Có thể viết `catch (IOException | FileNotFoundException ex)` không?

**Đáp án:** Không. `FileNotFoundException` kế thừa `IOException`; các lựa chọn multi-catch không được quan hệ subtype. Chỉ bắt `IOException` hoặc tách các khối phù hợp.

**Câu 4.** Khác biệt giữa `catch (IOException ex)` và `catch (IOException | IllegalArgumentException ex)` là gì?

**Đáp án:** Single-catch không tự động `final`; multi-catch có tham số `final` ngầm định. Với single-catch, tham số có thể *effectively final* nếu không gán lại. Việc có thể gán lại trong single-catch **không đồng nghĩa nên làm vậy**.

**Câu 5.** Bạn muốn ném ngoại lệ nghiệp vụ mới nhưng giữ thông tin gốc. Cách làm nào đúng?

**Đáp án:** Tạo ngoại lệ mới và truyền `ex` vào constructor nhận `cause`, ví dụ `throw new IllegalStateException("Cannot process request", ex);`. Không gán ngoại lệ mới vào `ex`.

## 10. Checklist và tài liệu đối chiếu

- [ ] Chỉ kết hợp các loại ngoại lệ không kế thừa nhau và có cách xử lý chung.
- [ ] Xác định `ex` trong multi-catch là `implicitly final`; **không** gán lại, dù gán `null`, chính nó hoặc ngoại lệ mới.
- [ ] Khi cần kết quả hoặc thông điệp khác, tạo biến mới và không mất tham chiếu gốc.
- [ ] Khi bọc lỗi, giữ `cause` nếu đó là cách truyền thông tin phù hợp; khi ném tiếp, dùng `throw ex;`.
- [ ] Không nhầm multi-catch với single-catch và *effectively final*.
- [ ] Chỉ truy cập phương thức hợp lệ từ kiểu chung hoặc phân nhánh kiểu tường minh.
- [ ] Biên dịch ví dụ chạy được với `javac --release 21`; xem ví dụ gán lại như **negative compile test**, không như code production.

Tài liệu chính thức:

- [Java Language Specification SE 21 — `14.20 The `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20): quy tắc tham số multi-catch final ngầm định, gán lại và kiểm tra các loại ngoại lệ thay thế.
- [Dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): cú pháp multi-catch và ghi chú về tham số `final`.
- [JLS SE 21 — `4.12.4 final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): đối chiếu `final` với `effectively final`.

Cú pháp trong bài là kiến thức Java vẫn còn áp dụng; bài thực hành trên JDK hiện đại thay vì phụ thuộc Java 7 đã cũ.