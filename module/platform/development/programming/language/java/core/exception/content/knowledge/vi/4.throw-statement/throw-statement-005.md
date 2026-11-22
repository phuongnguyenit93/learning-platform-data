# throw null và NullPointerException trong Java

> Java Core – Exception · Nhóm: Lệnh throw · Ví dụ chạy trên Java 17 trở lên.

## 1. Hiểu đúng trong một câu

`throw null;` **biên dịch được**, nhưng khi câu lệnh này thực sự chạy, Java **tạo và ném một đối tượng `NullPointerException`**. Giá trị `null` không phải là đối tượng ngoại lệ; không tồn tại việc một khối `catch` nhận “exception có giá trị null”.

Đây là quy tắc của **Java Language Specification (JLS), mục 14.18**, áp dụng cho mọi giá trị tham chiếu null mà một biểu thức `throw` trả về bình thường, không riêng từ khóa `null` viết trực tiếp trong mã.

Sau bài học, bạn sẽ phân biệt được:

1. `throw null` với `throw new NullPointerException(...)`.
2. `throw variable` khi biến chứa null và khi biến chứa đối tượng `Throwable` thực.
3. `throw factory()` khi factory trả về null so với khi factory tự ném exception trước khi trả về.
4. Ràng buộc kiểu tĩnh tại thời điểm biên dịch so với kiểu ngoại lệ được ném tại runtime.
5. Cách bắt, chẩn đoán và tránh những lỗi “throw null” phát sinh từ code thực tế.

## 2. Quy tắc chuẩn cho câu lệnh throw

Java dùng cú pháp:

```java
throw expression;
```

Theo [JLS 17 – The throw Statement, mục 14.18](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18), biểu thức sau `throw` cần có kiểu có thể gán cho `Throwable` hoặc là giá trị null literal. Trong lúc thực thi, Java đánh giá biểu thức trước, rồi xử lý theo một trong ba tình huống:

| Kết quả của `expression` | Hành vi của `throw` | Ngoại lệ quan sát được |
| --- | --- | --- |
| Đánh giá xong bình thường, nhận một đối tượng khác null | Ném **chính đối tượng đó** | Kiểu runtime của đối tượng |
| Đánh giá xong bình thường, nhận tham chiếu `null` | **Tạo và ném** một đối tượng `NullPointerException` | `NullPointerException` |
| Bản thân biểu thức ném exception trước khi có kết quả | Lệnh `throw` kết thúc bất thường bởi exception đó; không có bước ném giá trị cuối | Kiểu exception do biểu thức gây ra |

Có thể hình dung:

```text
              throw expression;
                       |
                 Tính expression
                  /          \
         Thành công           Tự ném exception E
             |                      |
      Kết quả là gì?                v
        /          \            Lan truyền E
   Khác null       null
      |             |
      v             v
 Ném chính      JVM tạo NPE
 đối tượng      rồi ném NPE
      \             /
       \           /
          Tìm catch
          hoặc lan lên caller
```

JLS định nghĩa rõ hai điều dễ nhầm: `throw` nhận biểu thức **không bắt buộc là lệnh `new`**, và giá trị cần ném **không được trở thành một Throwable có giá trị null**. Nếu kết quả là null, một NPE mới xuất hiện thay thế.

### Câu lệnh throw kết thúc bất thường

Trong cấu trúc:

```java
try {
    throw null;
    // Không được viết thêm câu lệnh có thể thực thi ở đây:
    // javac sẽ đánh dấu unreachable statement.
} catch (NullPointerException ex) {
    System.out.println("caught NPE");
}
```

Những dòng sau `throw` trong cùng một nhánh thông thường không thể chạy. Nếu đặt một câu lệnh thực thi vô điều kiện sau `throw null;` trong cùng khối, compiler sẽ báo *unreachable statement*. Các dòng chú thích ở ví dụ không phải câu lệnh thực thi, nên đoạn minh họa có thể dùng bên trong một phương thức.

Nếu nhánh `catch` phù hợp, chương trình có thể tiếp tục **sau cấu trúc try/catch**, không quay về chỗ throw.

## 3. Vì sao throw null không gây lỗi biên dịch?

Java có **null type** cho literal `null`. JLS quy định đây là giá trị được phép sử dụng trực tiếp trong biểu thức của câu lệnh `throw`. Vì vậy:

```java
throw null;
```

là cú pháp hợp lệ. Đây là ví dụ minh họa đặt trong phương thức thích hợp; riêng tệp nguồn chỉ chứa dòng này ngoài lớp Java thì không phải chương trình độc lập.

Các ví dụ gần nhau có kết quả khác biệt:

| Mã nguồn (đặt đúng ngữ cảnh) | Hợp lệ ở compile time? | Điều xảy ra khi chạy |
| --- | --- | --- |
| `throw null;` | Có | NPE do runtime tạo |
| `throw (RuntimeException) null;` | Có | NPE do runtime tạo; ép kiểu null vẫn là null |
| `RuntimeException ex = null; throw ex;` | Có | NPE do runtime tạo |
| `throw new NullPointerException("bad");` | Có | Ném NPE do lập trình viên tạo, message `bad` |
| `throw new IllegalStateException("failed");` | Có | Ném `IllegalStateException`, không phải NPE |
| `throw 42;` | Không | `int` không phù hợp với `Throwable` |
| `throw "failed";` | Không | `String` không phải subtype của `Throwable` |
| `throw new Object();` | Không | `Object` không gán được cho `Throwable` |
| `throw (Object) null;` | Không | Kiểu tĩnh `Object` không phù hợp dù giá trị là null |
| `throw;` | Không | Java yêu cầu biểu thức sau `throw` |

Lỗi của các dòng cố ý không hợp lệ thuộc **biên dịch**; NPE của `throw null` thuộc **runtime**. Không nên trộn hai giai đoạn khi giải thích.

## 4. Ba nguồn NullPointerException hay bị gộp

Xét ba đoạn minh họa, mỗi đoạn được viết trong một phương thức Java thích hợp.

**Trường hợp A — ném null:**

```java
throw null;
```

Biểu thức `null` hoàn thành bình thường, nhưng giá trị cần ném là null; Java tạo NPE.

**Trường hợp B — chủ động tạo một đối tượng NPE:**

```java
throw new NullPointerException("customerId must not be null");
```

Đối tượng NPE đã được tạo bằng `new` với message có ý nghĩa. `throw` ném chính đối tượng đó.

**Trường hợp C — sử dụng tham chiếu null sai cách:**

```java
String customerName = null;
int length = customerName.length();
```

Không có lệnh `throw` tường minh trong code, nhưng JVM ném NPE khi cố gọi phương thức qua tham chiếu null.

Các đoạn trên đều có thể dẫn đến **cùng kiểu NPE**, song khác nguyên nhân và vị trí trong stack trace. Đừng sửa tất cả NPE bằng cách thêm `catch (NullPointerException)`: cần tìm nguồn vi phạm hợp đồng null.

### Kiểu và phân loại NPE

```text
java.lang.Throwable
    └── java.lang.Exception
        └── java.lang.RuntimeException
            └── java.lang.NullPointerException
```

NPE là **unchecked exception** vì kế thừa `RuntimeException`. Do đó phương thức có thể ném NPE mà không bắt buộc viết `throws NullPointerException`. Điều này không có nghĩa lỗi không cần được xem xét; NPE thường báo hiệu trạng thái hoặc tham số không đáp ứng giả định của chương trình.

## 5. Ví dụ hoàn chỉnh Java 17: literal, biến, factory và lỗi chủ động

Lưu mã sau thành đúng tên tệp **`ThrowNullDemo.java`**. Đây là một chương trình chạy độc lập, không cần thư viện ngoài. Mỗi nhánh được bao bởi cùng một hàm kiểm thử để quan sát handler và cleanup.

```java
public class ThrowNullDemo {
    private static RuntimeException returnsNull() {
        System.out.println("factory returned null");
        return null;
    }

    private static RuntimeException failsFirst() {
        System.out.println("factory started");
        throw new IllegalStateException("factory failed");
    }

    private static void test(String label, Runnable task) {
        System.out.println("== " + label + " ==");
        try {
            task.run();
            System.out.println("unreachable");
        } catch (NullPointerException ex) {
            System.out.println("caught=NullPointerException");
            if (label.equals("explicit")) {
                System.out.println("message=" + ex.getMessage());
            }
        } catch (IllegalStateException ex) {
            System.out.println(
                    "caught=IllegalStateException: " + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }

    public static void main(String[] args) {
        test("literal", () -> { throw null; });

        test("variable", () -> {
            RuntimeException ex = null;
            throw ex;
        });

        test("returned-null", () -> { throw returnsNull(); });

        test("factory-throws", () -> { throw failsFirst(); });

        test("explicit", () -> {
            throw new NullPointerException("manual message");
        });
    }
}
```

Dùng JDK 17 trở lên, trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 ThrowNullDemo.java
java ThrowNullDemo
```

Stdout **chính xác** của chương trình:

```text
== literal ==
caught=NullPointerException
finally
after
== variable ==
caught=NullPointerException
finally
after
== returned-null ==
factory returned null
caught=NullPointerException
finally
after
== factory-throws ==
factory started
caught=IllegalStateException: factory failed
finally
after
== explicit ==
caught=NullPointerException
message=manual message
finally
after
```

Kết quả đã được đối chiếu khi biên dịch và chạy trên OpenJDK. Mã cố ý **không in `ex.getMessage()` đối với NPE do JVM tạo**, để stdout không phụ thuộc chi tiết chẩn đoán giữa các JVM. Riêng nhánh `explicit` in message do chính mã nguồn truyền vào constructor.

### Phân tích năm nhánh

1. **`literal`:** Thực thi `throw null`, nhận NPE do JVM tạo. Handler `catch (NullPointerException ex)` bắt đối tượng này.
2. **`variable`:** Biến có kiểu tĩnh `RuntimeException` nhưng giá trị thực là null. Kiểu tĩnh hợp lệ không biến null thành instance của RuntimeException; khi ném, NPE xuất hiện.
3. **`returned-null`:** `returnsNull()` in `factory returned null` rồi trả null bình thường. Chỉ **sau đó** lệnh `throw` mới tạo NPE. Side effect in dòng trước đã xảy ra.
4. **`factory-throws`:** `failsFirst()` in `factory started` rồi tự ném `IllegalStateException` trước khi trả về. Không có kết quả null để lệnh throw xử lý; exception gốc đi thẳng đến nhánh catch tương ứng.
5. **`explicit`:** `new NullPointerException("manual message")` tạo đối tượng có message xác định; `throw` ném đối tượng đó.

Ở mọi nhánh, `task.run()` kết thúc bất thường nên dòng `unreachable` không bao giờ được in. `finally` chạy, rồi dòng `after` chạy bởi handler đã xử lý xong và hoàn thành bình thường. Không có nhánh nào thực thi nốt phần thân của lambda sau khi lỗi đã xảy ra.

## 6. Đọc đúng biểu thức phía sau throw

Một lỗi phân tích phổ biến là thấy:

```java
throw createException();
```

rồi kết luận chương trình luôn ném đúng kiểu mà `createException()` khai báo là trả về. Thực tế phải tách hai giai đoạn:

- **Giai đoạn đánh giá:** Gọi `createException()`. Nếu nó ném một ngoại lệ trước khi trả về, ngoại lệ đó lan đi ngay.
- **Giai đoạn ném:** Chỉ xảy ra nếu lời gọi trả về bình thường. Kết quả không null được ném trực tiếp; kết quả null gây NPE.

Xem một factory minh họa (phương thức đặt trong một lớp Java; chưa là tệp độc lập):

```java
static RuntimeException createFailure(boolean hasReason) {
    return hasReason
            ? new IllegalArgumentException("bad input")
            : null;
}
```

- `throw createFailure(true);` ném `IllegalArgumentException`.
- `throw createFailure(false);` ném NPE.
- Nếu chính quá trình tính điều kiện hoặc tạo đối tượng ném lỗi, lỗi đó là lý do kết thúc bất thường tại thời điểm ấy.

Điều này quan trọng khi một factory, hàm chuyển đổi, bộ dựng exception hoặc callback vô tình **trả về null như tín hiệu “không có lỗi”**. Dùng kết quả này trong câu lệnh `throw` khiến “không có lỗi” bị hiểu thành NPE bất ngờ.

## 7. Quan hệ giữa throw null, catch và finally

NPE tạo từ `throw null` vẫn là một instance của lớp `NullPointerException`. Vì thế:

```java
try {
    throw null;
} catch (NullPointerException ex) {
    System.out.println(ex != null);
}
```

Đoạn trong một phương thức hợp lệ sẽ in `true`. Biến `ex` tham chiếu tới NPE mà runtime tạo. Java không cho phép một biến handler nhận “ngoại lệ null” trong trường hợp này.

Nếu muốn xử lý NPE cụ thể rồi mới đến loại RuntimeException khác, đặt handler cho kiểu con trước kiểu cha:

```java
try {
    throw null;
} catch (NullPointerException ex) {
    System.out.println("NPE");
} catch (RuntimeException ex) {
    System.out.println("other runtime failure");
}
```

Đảo hai nhánh `catch` gây lỗi biên dịch vì nhánh NPE phía sau không thể tới được. `catch (Exception)` cũng có thể bắt NPE, nhưng bắt rộng theo thói quen dễ che các lỗi logic.

Với `finally`:

```java
try {
    throw null;
} catch (NullPointerException ex) {
    System.out.println("caught");
} finally {
    System.out.println("cleanup");
}
System.out.println("continue");
```

Nếu nằm trong một phương thức, stdout là:

```text
caught
cleanup
continue
```

`finally` là nhánh dọn dẹp khi rời cấu trúc, **không** khiến phép đánh giá bị lỗi được chạy lại. Nếu `finally` lại ném exception khác, kết quả điều khiển có thể bị thay thế và exception ban đầu bị che mất. Tránh viết `return` hay `throw` mới trong `finally` khi không có lý do rõ ràng.

## 8. Phân biệt loại ngoại lệ runtime và kiểu tĩnh tại compile time

Đây là một điểm dễ gây bất ngờ: `throw null;` có biểu thức thuộc **null type**, được JLS cho phép trực tiếp. Nhưng khi ném **một biến có kiểu checked exception**, compiler xét kiểu tĩnh, dù giá trị thực của biến là null.

Ví dụ Java 17 độc lập, lưu thành `TypedNullExample.java`:

```java
import java.io.IOException;

public class TypedNullExample {
    static void fail() throws IOException {
        IOException ex = null;
        throw ex;
    }

    public static void main(String[] args) {
        try {
            fail();
        } catch (IOException ex) {
            System.out.println("caught IOException");
        } catch (NullPointerException ex) {
            System.out.println("caught NPE");
        }
    }
}
```

Chạy:

```bash
javac TypedNullExample.java
java TypedNullExample
```

Output:

```text
caught NPE
```

**Giải thích:** `ex` có kiểu tĩnh `IOException` (checked), vì vậy phương thức `fail()` khai báo `throws IOException`. Tuy nhiên, giá trị runtime của `ex` là null nên câu lệnh ném dẫn tới NPE unchecked. Không có `IOException` thực sự nào được tạo hoặc ném trong lần chạy này.

Một biến kiểu `Exception` hoặc `Throwable` càng cần xem kỹ điều kiện bắt/khai báo checked exception. Đừng bỏ qua ràng buộc compiler chỉ vì test cho thấy một nhánh hiện tại trả về null. Ngược lại, viết `throws NullPointerException` là tùy chọn về mặt ngôn ngữ do NPE là unchecked exception.

## 9. Helpful NullPointerExceptions và thông điệp lỗi

Các JDK hiện đại có khả năng đưa ra thông điệp NPE hữu ích dựa trên thao tác bytecode gây lỗi. OpenJDK JEP 358 bổ sung cơ chế này từ JDK 14; trên HotSpot, tùy chọn `ShowCodeDetailsInExceptionMessages` được bật mặc định từ JDK 15.

Trong một số tình huống, message có thể cho biết đang cố gọi phương thức, đọc trường hoặc **ném một tham chiếu null**. Nhưng phải phân biệt:

| Phần nào | Tính ổn định |
| --- | --- |
| Giá trị sau `throw` là null → Java ném NPE | Quy tắc ngôn ngữ, được JLS xác định |
| `getMessage()` của NPE do JVM tạo | Có thể phụ thuộc JVM, bytecode và cấu hình |
| `new NullPointerException("manual")` → message `manual` | Thông điệp được constructor nhận từ code ứng dụng |
| Stack trace, số dòng, tên biến biểu thị null | Phụ thuộc cách biên dịch và thông tin runtime |

Theo tài liệu API Java 17, `NullPointerException.getMessage()` có thể trả về message do constructor cung cấp, thông điệp tùy triển khai hoặc `null`. Với một NPE do người viết mã chủ động tạo không có message, không mặc định suy ra hệ thống sẽ bổ sung thông điệp phân tích biểu thức.

Nếu dùng JVM HotSpot có hỗ trợ, có thể bật hoặc tắt phần thông tin này để chẩn đoán:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages ThrowNullDemo
java -XX:-ShowCodeDetailsInExceptionMessages ThrowNullDemo
```

Trong ví dụ chính, stdout **không đổi** vì mã chỉ in tên kiểu của NPE runtime, không in message của các NPE đó. Đây là tùy chọn VM cụ thể; không coi mọi JVM đều hỗ trợ nguyên xi cờ.

Với unit test, ưu tiên khẳng định **kiểu exception** và trạng thái chương trình. Chỉ khẳng định nguyên văn message khi nó do API của chính bạn hoặc hợp đồng thư viện bảo đảm.

## 10. Viết mã tốt hơn throw null

### Tạo ngoại lệ có ý nghĩa

Đối với tham số không hợp lệ:

```java
if (age < 0) {
    throw new IllegalArgumentException("age must be non-negative");
}
```

Đối với tham số bắt buộc khác null:

```java
if (customerId == null) {
    throw new NullPointerException("customerId must not be null");
}
```

Hai đoạn trên chỉ là ví dụ bên trong phương thức, giả định biến tương ứng đã khai báo. Chọn loại exception theo **hợp đồng của API**, thay vì sử dụng NPE cho mọi lỗi nghiệp vụ.

### Dùng Objects.requireNonNull khi cần kiểm tra null

Java chuẩn có `Objects.requireNonNull`; với overload nhận `String` message, nó trả về tham chiếu đầu vào nếu khác null, hoặc ném NPE với message chỉ định nếu đầu vào null.

Tệp Java 17 độc lập `RequireNonNullDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullDemo {
    static void process(String id) {
        String checked = Objects.requireNonNull(
                id, "id must not be null");
        System.out.println(checked);
    }

    public static void main(String[] args) {
        try {
            process(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac RequireNonNullDemo.java
java RequireNonNullDemo
```

Stdout:

```text
id must not be null
```

Đây là kiểm tra **ở ranh giới nhận dữ liệu**. Nếu null là trạng thái hợp lệ của API (ví dụ truy vấn không có kết quả), nên thiết kế cách biểu đạt trạng thái vắng mặt rõ ràng như `Optional<T>` khi phù hợp, thay vì cố dùng một exception để thay thế điều kiện bình thường.

### Không viết factory ngoại lệ trả về null

Thiết kế nguy hiểm:

```java
static RuntimeException buildFailure(String reason) {
    if (reason == null) {
        return null;
    }
    return new IllegalStateException(reason);
}
```

Nếu caller viết `throw buildFailure(null);`, chương trình ném NPE thay vì loại ngoại lệ nghiệp vụ định dùng.

Thiết kế rõ ràng hơn:

```java
static IllegalStateException buildFailure(String reason) {
    String message = reason == null
            ? "operation failed"
            : reason;
    return new IllegalStateException(message);
}
```

Hai đoạn factory chỉ minh họa một phương thức đặt trong class, **chưa phải tệp Java độc lập**. Chúng cần được điều chỉnh theo quy tắc nghiệp vụ thật: khi không có lỗi, đừng gọi `throw`; khi có lỗi, trả về hoặc tạo một Throwable không null, giữ `cause` khi bọc lỗi gốc.

## 11. Những lỗi hiểu sai thường gặp

1. **“throw null phải lỗi biên dịch.”** Sai: null literal được JLS cho phép; runtime ném NPE.
2. **“Có thể ném một đối tượng exception có giá trị null.”** Sai: null không phải một object; Java tạo NPE.
3. **“catch nhận null.”** Sai: handler nhận đối tượng NPE thực sự.
4. **“Biến có kiểu RuntimeException chắc chắn chứa một RuntimeException.”** Sai: biến tham chiếu có thể chứa null.
5. **“factory đã khai báo RuntimeException, vậy throw factory() chắc chắn ném RuntimeException.”** Sai: factory có thể trả null, hoặc tự ném một exception khác trước khi trả về.
6. **“throw new NullPointerException và throw null hoàn toàn giống nhau.”** Sai: cả hai có thể cùng kiểu NPE nhưng khác nguồn gốc object và cách tạo message.
7. **“Mọi NPE đều có message hữu ích.”** Sai: `getMessage()` có thể null hoặc thay đổi theo triển khai.
8. **“NPE là unchecked nên cứ bỏ qua.”** Sai: compiler không bắt buộc khai báo, nhưng lỗi vẫn gián đoạn luồng thực thi.
9. **“Biết biến checked exception là null nên không cần throws.”** Sai: kiểm tra checked exception phụ thuộc kiểu tĩnh của biểu thức.
10. **“Catch NPE là đã sửa bug null.”** Sai: thường cần kiểm tra hợp đồng, khởi tạo đúng và truy nguyên nơi tạo null.
11. **“throw null sẽ tự bảo toàn cause của lỗi trước.”** Sai: chưa có Throwable cụ thể để dùng làm cause; nếu cần bảo toàn, hãy tạo ngoại lệ mới với constructor nhận cause.
12. **“finally chạy sẽ tiếp tục nốt lệnh throw.”** Sai: cleanup chỉ diễn ra khi chuyển điều khiển, không làm phép đánh giá ban đầu chạy lại.

## 12. Bài tự kiểm tra

**Câu 1.** Kết quả của `throw null;` tại runtime là loại exception nào? Vì sao nó hợp lệ lúc biên dịch?

*Đáp án:* NPE. Java cho phép null literal sau `throw`, và nếu giá trị được ném là null, runtime tạo một NPE.

**Câu 2.** `RuntimeException ex = null; throw ex;` có ném chính đối tượng RuntimeException không?

*Đáp án:* Không có đối tượng RuntimeException nào trong biến. Giá trị null dẫn tới NPE do runtime tạo.

**Câu 3.** Với `throw makeException();`, nếu `makeException()` ném `IllegalStateException` trước khi trả về, kết quả là gì?

*Đáp án:* `IllegalStateException` lan truyền ngay. Lệnh throw không có giá trị trả về để xử lý thành NPE.

**Câu 4.** Vì sao method `fail() throws IOException` có thể chạy ra NPE khi thực thi `IOException x = null; throw x;`?

*Đáp án:* Kiểu tĩnh checked `IOException` quyết định yêu cầu khai báo, còn giá trị runtime null khiến Java tạo NPE.

**Câu 5.** Có nên viết test so sánh nguyên văn message do JVM tạo cho `throw null` không?

*Đáp án:* Không. Kiểu ngoại lệ ổn định theo JLS, còn message chẩn đoán có thể phụ thuộc triển khai.

**Câu 6.** Khi một factory trả null nhưng caller đang viết `throw factory();`, sửa ở đâu?

*Đáp án:* Xem lại hợp đồng: nếu không có lỗi thì tránh ném, nếu có lỗi thì phải tạo Throwable khác null với loại, message và cause phù hợp.

## 13. Tài liệu chuẩn

- [JLS 17, mục 14.18 – The throw Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): quy tắc đánh giá biểu thức và tạo NPE khi giá trị sau throw là null.
- [JLS 17, mục 11.2 – Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): cách compiler phân tích và yêu cầu khai báo checked exceptions.
- [Java 17 API – NullPointerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): phân cấp và thông điệp NPE, bao gồm trường hợp “throwing null”.
- [Java 17 API – Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): các overload `requireNonNull`.
- [OpenJDK JEP 358 – Helpful NullPointerExceptions](https://openjdk.org/jeps/358): cơ chế bổ sung chi tiết chẩn đoán NPE.

**Ghi nhớ:** Cần một **đối tượng Throwable thực** để ném một ngoại lệ có ý nghĩa. Nếu biểu thức sau `throw` chỉ trả về null, Java **ném NPE mới**. Hãy đặt ràng buộc null rõ ràng, đọc đúng kiểu tĩnh và bảo toàn nguyên nhân lỗi khi thiết kế exception.