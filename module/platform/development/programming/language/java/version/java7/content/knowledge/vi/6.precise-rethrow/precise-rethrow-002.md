# Suy luận chính xác hơn khi ném lại biến catch trong Java

## 1. Bài toán: `catch` rộng, `throws` hẹp

Trong Java, phương thức phải xử lý hoặc khai báo các **checked exception** có thể thoát khỏi nó. Giả sử một thao tác có thể thất bại theo hai cách: lỗi I/O (`IOException`) và lỗi phân tích dữ liệu (`ParseException`). Ta muốn ghi nhận cả hai trong một nhánh, rồi **ném lại chính ngoại lệ đã bắt** mà không thay đổi đối tượng.

Nếu nhánh bắt khai báo `catch (Exception ex)`, có phải phương thức luôn phải khai báo `throws Exception`? **Không.** Từ **Java 7**, Java hỗ trợ *more precise rethrow* (*precise rethrow*): trình biên dịch có thể tính chính xác hơn **tập các ngoại lệ được ném từ `throw ex;`** dựa trên các ngoại lệ mà thân `try` có thể ném ra, thay vì chỉ nhìn kiểu tĩnh `Exception` của biến `ex`.

Ví dụ về cấu trúc mong muốn:

~~~java
static void load() throws IOException, ParseException {
    try {
        // Chỉ các checked exception IOException và ParseException được
        // ném theo phân tích tĩnh của thân try.
    } catch (Exception ex) {
        // Có thể ghi nhận rồi ném tiếp chính ex:
        throw ex;
    }
}
~~~

Đây là **đoạn phác thảo**: thân `try` cần có thao tác thực tế và lớp chứa phương thức cần import thích hợp. Ví dụ chạy được đầy đủ ở phần 4.

**Mục tiêu học tập:** sau bài này, bạn có thể giải thích vì sao `throws IOException, ParseException` đủ trong tình huống phù hợp, phân biệt `final` với `effectively final` ở tham số `catch`, chỉ ra khi nào precise rethrow mất hiệu lực và lựa chọn cách viết bảo toàn lỗi gốc.

**Phiên bản:** Precise rethrow được đưa vào từ Java 7 và **vẫn còn áp dụng trong Java hiện đại**. Bài không phụ thuộc kiến thức legacy hoặc một JDK cũ; ví dụ được kiểm thử với `javac --release 21`.

## 2. Kiểu của `ex` và tập ngoại lệ mà `throw ex` có thể ném là hai khái niệm khác nhau

Giả sử trong một thân `try` có hai thao tác:

~~~java
if ("io".equals(key)) {
    throw new IOException("read failure");
}
if ("parse".equals(key)) {
    throw new ParseException("bad syntax", 0);
}
~~~

Hai lệnh trên là **đoạn minh họa**, không phải chương trình độc lập. Khi dùng `catch (Exception ex)`:

| Điều cần phân biệt | Trong ví dụ |
| --- | --- |
| Kiểu khai báo của tham số `ex` | `Exception` |
| Kiểu của đối tượng tại runtime | `IOException` hoặc `ParseException` tùy nhánh |
| Những **checked exception** mà thân `try` có thể ném theo phân tích tĩnh | `IOException` và `ParseException` |
| Kiểu phải khai báo trong `throws` khi ném tiếp `ex` đủ điều kiện | Có thể chỉ là `IOException, ParseException` |

Câu lệnh `throw ex;` **không thay đổi đối tượng lỗi**. Nó tiếp tục ném tham chiếu đang được `catch` giữ, cùng kiểu runtime, thông điệp và stack trace. Trình biên dịch cũng không biến kiểu tĩnh `Exception` của biến `ex` thành một kiểu khác: `ex.getMessage()` và những API khả dụng vẫn được xác định theo kiểu khai báo của biến.

Điều thay đổi chỉ là kết quả **phân tích ngoại lệ checked ở thời điểm biên dịch**: với điều kiện cụ thể, compiler không buộc bạn khai báo kiểu `Exception` quá rộng.

## 3. Điều kiện của precise rethrow theo Java Language Specification

JLS `11.2.2 quy định: nếu biểu thức ném là **tham số ngoại lệ của một `catch`**, tham số đó là `final` hoặc `effectively final`, thì tập các loại ngoại lệ có thể được ném được tính từ:

1. **Các loại mà thân `try` tương ứng có thể ném theo phân tích tĩnh.**
2. **Những loại mà nhánh `catch` hiện tại có khả năng bắt.**
3. **Những loại chưa được các `catch` đứng trước trong cùng `try` bắt.**

Điều đó áp dụng cho lệnh `throw ex;`, không phải cơ chế “compiler chạy thử chương trình để đoán giá trị của `ex`”. Khi thân `try` gọi một phương thức khai báo `throws Exception`, compiler có thể phải coi `Exception` là loại checked có thể xuất hiện; precise rethrow **không thể tự thu hẹp một hợp đồng `throws` quá rộng nếu thiếu cơ sở tĩnh**.

### 3.1. `effectively final` trong single-catch

~~~java
catch (Exception ex) {
    System.err.println(ex.getClass().getSimpleName());
    throw ex;
}
~~~

Đây là **đoạn minh họa phải đặt trong một `try/catch` hợp lệ**. Không có câu lệnh gán lại `ex`. Vì thế, dù không ghi từ khóa `final`, tham số single-catch được xem là **effectively final**.

Những thao tác này không làm mất tính effectively final: `ex.getMessage()`, `ex.getClass()`, truyền `ex` vào hàm logging, tạo biến phụ như `String message = ex.getMessage()`, và `throw ex;`. Chúng **sử dụng** tham chiếu chứ không gán tham chiếu mới vào `ex`.

Bạn cũng có thể khai báo tường minh:

~~~java
catch (final Exception ex) {
    throw ex;
}
~~~

Trong code phù hợp, cả tham số được khai báo `final` và tham số *effectively final* đều có thể hưởng lợi từ precise rethrow.

### 3.2. `implicitly final` trong multi-catch

~~~java
catch (IOException | ParseException ex) {
    throw ex;
}
~~~

Đây là đoạn minh họa. Tham số của multi-catch là **final ngầm định**, nên không thể gán lại `ex`. Multi-catch phù hợp nếu chỉ muốn bắt những loại được liệt kê và tất cả cùng một cách xử lý.

**Chú ý:** single-catch `catch (Exception ex)` và multi-catch `catch (IOException | ParseException ex)` đều có thể ném tiếp chính ngoại lệ, nhưng chúng khác nhau về **phạm vi bắt lỗi**. Nhánh `catch (Exception ex)` có thể bắt cả các loại `Exception` khác, bao gồm unchecked exception, còn multi-catch trên chỉ bắt những subtype tương ứng hai lựa chọn.

### 3.3. Phải ném lại chính tham số ngoại lệ

~~~java
catch (Exception ex) {
    throw ex; // Dạng được xét cho precise rethrow
}
~~~

Trường hợp sau **không** được suy luận như ném lại chính tham số catch:

~~~java
catch (Exception ex) {
    Exception saved = ex;
    throw saved; // saved là biến cục bộ, có kiểu tĩnh Exception
}
~~~

Đây là những đoạn minh họa chứ không phải chương trình hoàn chỉnh. Ở đoạn thứ hai, `saved` có thể giữ cùng tham chiếu runtime, nhưng **quy tắc đặc biệt của precise rethrow áp dụng cho tham số `catch` được ném trực tiếp**, không phải tự động áp dụng cho một biến cục bộ có kiểu `Exception`. Vì vậy, phép ném `saved` có thể đòi `throws Exception` hoặc xử lý rộng hơn.

## 4. Ví dụ Java 21 hoàn chỉnh, biên dịch và chạy được

Tạo file `src/main/java/demo/PreciseRethrowExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.text.ParseException;
import java.util.List;

public final class PreciseRethrowExample {
    private PreciseRethrowExample() {
    }

    static String load(String key) throws IOException, ParseException {
        try {
            if ("io".equals(key)) {
                throw new IOException("read failure");
            }
            if ("parse".equals(key)) {
                throw new ParseException("bad syntax", 0);
            }
            return "OK:" + key;
        } catch (Exception ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    static String loadWithMultiCatch(String key)
            throws IOException, ParseException {
        try {
            if ("io".equals(key)) {
                throw new IOException("read failure");
            }
            if ("parse".equals(key)) {
                throw new ParseException("bad syntax", 0);
            }
            return "OK:" + key;
        } catch (IOException | ParseException ex) {
            throw ex;
        }
    }

    public static void main(String[] args) {
        for (String key : List.of("ready", "io", "parse")) {
            try {
                System.out.println(key + " -> " + load(key));
            } catch (IOException | ParseException ex) {
                System.out.println(key + " -> "
                        + ex.getClass().getSimpleName());
            }
        }
        try {
            System.out.println("multi -> "
                    + loadWithMultiCatch("io"));
        } catch (IOException | ParseException ex) {
            System.out.println("multi -> "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Trong thư mục chứa `src/`, biên dịch bằng JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/PreciseRethrowExample.java
java -cp out demo.PreciseRethrowExample
~~~

Kết quả stdout chính xác:

~~~text
ready -> OK:ready
caught=IOException
io -> IOException
caught=ParseException
parse -> ParseException
multi -> IOException
~~~

**Phân tích kết quả:**

- Với `"ready"`, không có exception; `load` trả `"OK:ready"`.
- Với `"io"`, `IOException` được ném; `catch (Exception ex)` nhận nó, in `caught=IOException`, rồi `throw ex;` ném **đúng đối tượng lỗi đó** tiếp lên `main`.
- Với `"parse"`, chu trình tương tự với `ParseException`.
- Phương thức `load` chỉ có `throws IOException, ParseException`. Điều này biên dịch được vì `ex` effectively final và compiler biết hai loại checked có thể xuất hiện từ thân `try`.
- Phương thức `loadWithMultiCatch` minh họa một lối viết hẹp hơn về phạm vi bắt lỗi; `throw ex;` hợp lệ vì `ex` implicitly final trong multi-catch.
- `List.of(...)` có từ Java 9. Chương trình cố tình chạy trên Java 21 để phù hợp JDK hiện đại; đó không phải điều kiện về phiên bản phát hành ban đầu của tính năng precise rethrow.

Mọi lỗi trong ví dụ được tạo có chủ đích để đầu ra ổn định, không phụ thuộc tệp thật, kết nối mạng, locale hoặc đồng hồ.

## 5. Khi nào suy luận mất độ chính xác? Gán lại biến `catch`

Với single-catch, `catch (Exception ex)` **có thể** gán lại tham số nếu không khai báo `final`. Nhưng khi làm thế, `ex` không còn *effectively final*, và lợi ích precise rethrow sẽ mất.

File sau **cố ý biên dịch lỗi**, cần để riêng tại `src/main/java/demo/InvalidReassignedCatch.java`:

~~~java
package demo;

import java.io.IOException;
import java.text.ParseException;

public final class InvalidReassignedCatch {
    static void load(String key) throws IOException, ParseException {
        try {
            if ("io".equals(key)) {
                throw new IOException("read failure");
            }
            if ("parse".equals(key)) {
                throw new ParseException("bad syntax", 0);
            }
        } catch (Exception ex) {
            ex = new IOException("replacement");
            throw ex; // CỐ Ý SAI: mất precise rethrow
        }
    }
}
~~~

Biên dịch riêng file lỗi (không biên dịch chung với ví dụ chạy được):

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/InvalidReassignedCatch.java
~~~

Thông báo lỗi trọng tâm trên `javac`:

~~~text
error: unreported exception Exception; must be caught or declared to be thrown
~~~

Đây là **diagnostic từ stderr của trình biên dịch**, không phải stdout của một chương trình chạy được. Đường dẫn, dòng số và dấu chỉ vị trí lỗi có thể khác.

**Giải thích:**

1. Phép gán `ex = new IOException("replacement")` làm `ex` **không còn effectively final**.
2. Khi nhìn `throw ex;`, compiler phải xét kiểu tĩnh của `ex` là `Exception`, chứ không dùng quy tắc precise rethrow dành cho tham số đủ điều kiện.
3. Phương thức chỉ khai báo `throws IOException, ParseException`, vốn không bao phủ mọi `Exception` checked, nên báo lỗi.
4. Nếu sửa thành `throws Exception`, code có thể biên dịch nhưng hợp đồng API bị mở rộng. Cách sửa phù hợp hơn trong tình huống này là **không gán lại `ex`** và ném tiếp ngoại lệ gốc.

Ngay cả `ex = ex;` vẫn là phép gán trong mã nguồn và làm mất điều kiện effectively final. Khi thật sự muốn thay đổi ngữ nghĩa lỗi, hãy **tạo đối tượng ngoại lệ mới** và ném đối tượng đó có chủ đích, thay vì sửa tham số `catch`.

### 5.1. Có thể bổ sung ngữ cảnh mà không gán lại `ex`

~~~java
catch (Exception ex) {
    String detail = "Failed while loading request";
    System.err.println(detail + ": " + ex.getClass().getSimpleName());
    throw ex;
}
~~~

Đây là đoạn minh họa. `detail` là biến riêng. Dùng `ex` để ghi log và ném lại không mất *effectively final*. Trong hệ thống thực tế, cân nhắc tránh ghi dữ liệu nhạy cảm vào log khi `getMessage()` có thể chứa thông tin từ người dùng.

### 5.2. Khi cần đổi loại lỗi, bảo toàn `cause`

~~~java
catch (Exception ex) {
    throw new IllegalStateException("Loading failed", ex);
}
~~~

Đây là đoạn minh họa. `IllegalStateException` là ngoại lệ **unchecked**; constructor nhận `ex` làm `cause`, giúp giữ nguyên nguyên nhân ban đầu. Tuy nhiên, không nên biến mọi lỗi I/O, parse hoặc validation thành `IllegalStateException` chỉ để tránh khai báo checked exception. Hãy chọn wrapper đúng hợp đồng ứng dụng và để người gọi phân biệt lỗi cần thiết.

## 6. Các ranh giới quan trọng khi áp dụng

### 6.1. Phân tích là tĩnh, không phải suy đoán theo giá trị runtime

~~~java
static void externalOperation() throws Exception {
    // Một API có hợp đồng lỗi rộng.
}
~~~

Nếu `try` gọi một hàm như thế, compiler phải cân nhắc `Exception` theo phần khai báo `throws`, dù tình huống bạn quan sát tại runtime chỉ gặp `IOException`. Precise rethrow không thay thế việc khai báo checked exception chính xác ở các API được gọi.

### 6.2. Thứ tự các nhánh `catch` có ảnh hưởng

~~~java
try {
    performOperation();
} catch (IOException ex) {
    handleIo(ex);
} catch (Exception ex) {
    throw ex;
}
~~~

Đây là **đoạn minh họa phụ thuộc vào định nghĩa `performOperation` và `handleIo`**. Những ngoại lệ đã được `catch (IOException ex)` phía trước bắt sẽ không còn là các ngoại lệ được ném lại bởi nhánh `catch (Exception ex)` phía sau. Quy tắc precise rethrow xét các handler đã xử lý trước, không chỉ kiểu `Exception` trên tham số.

### 6.3. Không phải mọi biến tên `ex` đều được hưởng quy tắc

Tên biến không quan trọng. Điều quan trọng là biểu thức `throw` trực tiếp tham chiếu **tham số của `catch`** có đủ điều kiện. Nếu sao chép tham chiếu sang biến cục bộ kiểu `Exception` rồi ném biến đó, compiler xét kiểu của biểu thức mới theo quy tắc thông thường.

### 6.4. Checked và unchecked vẫn khác nhau

`IOException` và `ParseException` là checked exceptions. Trong khi đó, các lớp con `RuntimeException`, ví dụ `IllegalArgumentException`, không bắt buộc phải khai báo `throws`. `catch (Exception ex)` cũng có thể bắt runtime exceptions nhưng không bắt `Error` (vì `Error` không kế thừa `Exception`).

Precise rethrow không có nghĩa tất cả lỗi runtime đều được đoán chính xác hoặc không thể thoát khỏi chương trình. Nó chỉ là quy tắc phân tích loại ngoại lệ trong Java.

### 6.5. Phạm vi `catch` nên theo trách nhiệm thực tế

Nếu hai loại lỗi cụ thể cần cùng phản ứng, `catch (IOException | ParseException ex)` thường rõ ràng và hạn chế phạm vi hơn `catch (Exception ex)`. Tuy vậy, với một lớp boundary có nhiệm vụ ghi nhận rồi ném tiếp các exception được xử lý có chủ đích, một `catch (Exception ex)` effectively final có thể phù hợp.

Không nên mở rộng mọi `catch` thành `Exception` chỉ vì precise rethrow cho phép phương thức vẫn khai báo `throws` hẹp.

## 7. Bảng quyết định ngắn

| Tình huống | Cách giải quyết | Lý do |
| --- | --- | --- |
| Một loại lỗi checked, không cần thay đổi | `catch (IOException ex) { throw ex; }` | Dễ hiểu và chính xác |
| Hai loại cần xử lý chung | `catch (IOException | ParseException ex) { throw ex; }` | Multi-catch implicitly final và phạm vi bắt rõ |
| Ghi nhận nhiều loại rồi ném nguyên trạng | Giữ `ex` effectively final, `throw ex;` | Tận dụng precise rethrow |
| Cần message bổ sung | Tạo biến message/log riêng | Không gán lại `ex` |
| Muốn tạo loại lỗi nghiệp vụ | Tạo exception mới với `cause=ex` | Giữ nguyên lỗi gốc và thay đổi hợp đồng có chủ đích |
| `try` gọi API khai báo `throws Exception` | Xem lại hợp đồng API hoặc xử lý/khai báo phù hợp | Compiler không thể tự đoán ra tập hẹp |
| Single-catch có `ex = ...` | Tránh gán lại nếu muốn precise rethrow | `ex` không còn effectively final |
| Sao chép `ex` sang `Exception saved` rồi `throw saved` | Ném trực tiếp `ex` nếu muốn giữ phân tích chính xác | Biến mới không phải tham số catch |

## 8. Tự kiểm tra

**Câu 1.** Một thân `try` theo phân tích tĩnh chỉ có thể ném checked `IOException` và `ParseException`. Vì sao `catch (Exception ex) { throw ex; }` có thể đi cùng `throws IOException, ParseException`?

**Đáp án:** Vì `ex` effectively final và được ném trực tiếp. Compiler phân tích loại lỗi có thể từ `try`, phù hợp với `catch` và chưa bị handler trước bắt, nên không phải khai báo `throws Exception`.

**Câu 2.** Sau khi thêm `ex = new IOException("replacement");` vào single-catch, vì sao `throw ex;` có thể yêu cầu `throws Exception`?

**Đáp án:** Vì tham số mất tính effectively final. Khi đó, không được suy luận theo tập lỗi từ thân `try`; `throw ex;` được xét theo kiểu tĩnh `Exception`.

**Câu 3.** Có thể gán lại `ex` trong `catch (IOException | ParseException ex)` không?

**Đáp án:** Không. Tham số của multi-catch là `final` ngầm định; phép gán sẽ bị từ chối ngay tại compile time.

**Câu 4.** `catch (Exception ex) { Exception saved = ex; throw saved; }` có được áp dụng quy tắc chính xác như `throw ex;` không?

**Đáp án:** Không. `saved` chỉ là biến cục bộ với kiểu tĩnh `Exception`, không phải tham số ngoại lệ mà quy tắc JLS đang xét.

**Câu 5.** Vì sao không nên chọn `catch (Exception ex)` trong mọi trường hợp?

**Đáp án:** Nó có phạm vi bắt lỗi rộng. Chọn `catch` theo trách nhiệm và chính sách xử lý lỗi, còn precise rethrow chỉ hỗ trợ giữ hợp đồng checked exception chính xác khi ném lại.

## 9. Checklist và nguồn chính thức

- [ ] Phân biệt kiểu tham số `catch` với tập checked exception suy luận cho `throw ex;`.
- [ ] Giữ tham số single-catch effectively final hoặc khai báo `final` tường minh khi muốn ném lại chính xác.
- [ ] Nhớ rằng tham số multi-catch là implicitly final, không được gán lại.
- [ ] Không gán `ex = ...`, kể cả `ex = ex`, chỉ để thay đổi thông điệp; tạo biến khác hoặc ngoại lệ wrapper nếu hợp đồng đòi hỏi.
- [ ] Kiểm tra các checked exception mà thân `try` có thể ném theo code và khai báo `throws` của phương thức được gọi.
- [ ] Xét các handler trước đó; tránh `catch` quá rộng khi phạm vi cụ thể dễ hiểu hơn.
- [ ] Nếu bọc lỗi, giữ `cause` khi phù hợp và không làm mất thông tin lỗi cần dùng.
- [ ] Biên dịch mã hợp lệ và negative test riêng trên JDK đang được hỗ trợ.

**Tài liệu chính thức (quy tắc vẫn áp dụng):**

- [JLS SE 21 `11.2.2 — Exception Analysis of Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.2): precise rethrow cho tham số ngoại lệ final/effectively final.
- [JLS SE 21 `14.20 — The `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20): khai báo single-catch, multi-catch và tham số implicitly final.
- [JLS SE 21 `4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): cách hiểu `final` và `effectively final`.

Bài chỉ sử dụng các quy tắc còn áp dụng trong Java hiện đại; không yêu cầu dùng JDK 7 cũ hoặc API legacy.
