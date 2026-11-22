# Suy luận kiểu với `throws` và rủi ro của `sneaky throw` trong Java

Java có cơ chế **checked exception**: nếu một phương thức hoặc biểu thức có thể làm một ngoại lệ checked thoát ra, compiler thường buộc code gọi phải `catch` hoặc khai báo `throws` phù hợp. Tuy nhiên, khi **generic type variable** xuất hiện trong mệnh đề `throws`, quá trình **suy luận kiểu (type inference)** có những quy tắc đặc biệt. Từ đó xuất hiện kỹ thuật thường được gọi là **sneaky throw**: làm một ngoại lệ checked thực sự lan ra ở runtime, trong khi chữ ký và việc kiểm tra tại điểm gọi không cho thấy nghĩa vụ checked exception tương ứng.

Điểm phân biệt quan trọng:

- **Generic `throws E` hợp lệ và hữu ích** khi thiết kế API cho lambda, method reference hoặc callback có khả năng ném loại checked exception của riêng chúng.
- **Suy luận kiểu của lambda có kiểm tra checked exception**; nó không tự động “bỏ qua” `IOException` hay `SQLException`.
- **Sneaky throw cố ý lợi dụng một trường hợp suy luận kiểu** để caller không bị compiler yêu cầu bắt một ngoại lệ checked, dù ngoại lệ đó có thể thực sự được ném.
- **Runtime không biến `IOException` thành `RuntimeException`**. Đối tượng được ném giữ nguyên loại và danh tính; chỉ **mô hình checked exception tại compile time** bị làm cho khác với hành vi thực tế.
- Kỹ thuật này có rủi ro lớn với hợp đồng API, `catch` theo kiểu cụ thể, code tích hợp và khả năng bảo trì. Trong phần lớn ứng dụng, nên **công bố checked exception minh bạch, xử lý ngay hoặc bọc thành một unchecked exception có cause rõ ràng**.

Bài này giải thích nền tảng JLS Java 17, các tình huống suy luận kiểu, ví dụ runnable, các ví dụ compiler từ chối, nguyên nhân runtime vẫn ném được `IOException`, rủi ro trong Stream/lambda, cách thay thế an toàn và các câu hỏi tự kiểm tra.

## 1. Ba tầng cần phân biệt: đối tượng, chữ ký và suy luận

Xét một ngoại lệ:

~~~java
java.io.IOException failure =
        new java.io.IOException("đọc dữ liệu thất bại");
~~~

Có ba câu hỏi khác nhau:

1. **Loại runtime của đối tượng là gì?** — `java.io.IOException`.
2. **Một phương thức công bố loại lỗi gì?** — Ví dụ `throws IOException`, `throws Exception`, `throws E` hoặc không có mệnh đề `throws`.
3. **Compiler suy ra nghĩa vụ nào tại một lời gọi generic cụ thể?** — Phụ thuộc type variable, bounds, đối số, target type và các ràng buộc từ lambda/method reference.

Các câu hỏi này không luôn cho cùng một tên kiểu. Ví dụ một đối tượng `FileNotFoundException` có thể được ném từ phương thức `throws IOException` vì nó thuộc nhánh `IOException`. Điều đó vẫn **đúng hợp đồng**. Ngược lại, khi một đối tượng `IOException` thoát khỏi phương thức mà caller không thấy bất kỳ checked `throws` nào, có thể đang có thiết kế sai hoặc một kỹ thuật cố ý làm mờ hợp đồng.

Trong các ví dụ của bài, **`throw`** là câu lệnh ném một đối tượng tại runtime, còn **`throws`** là phần khai báo khả năng thoát ngoại lệ trong phương thức. Sự khác nhau này là nền tảng để hiểu generic `throws E`.

## 2. Checked và unchecked exception trong Java 17

Phân cấp rút gọn:

~~~text
java.lang.Throwable
├── java.lang.Error                       unchecked
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException               checked
    │   └── FileNotFoundException          checked
    ├── java.sql.SQLException             checked
    └── java.lang.RuntimeException        unchecked
        ├── IllegalStateException
        └── IllegalArgumentException
~~~

**Checked exception** là các kiểu thuộc `Throwable` nhưng **không** nằm dưới `RuntimeException` hoặc `Error`. Với các ngoại lệ checked có thể thoát, code thường phải tuân theo luật **catch-or-declare**.

Ví dụ đơn giản:

~~~java
import java.io.IOException;

// Đoạn minh họa bên trong một lớp.
static void read() throws IOException {
    throw new IOException("không đọc được");
}

static void caller() {
    // read();  // Không biên dịch nếu không bắt hoặc khai báo IOException.
}
~~~

Một cách sửa hợp lệ:

~~~java
// Đoạn minh họa bên trong lớp có read() ở trên.
static void caller() {
    try {
        read();
    } catch (IOException ex) {
        System.out.println("Đã bắt lỗi I/O");
    }
}
~~~

Hoặc `caller()` có thể khai báo `throws IOException` để chuyển nghĩa vụ cho người gọi tiếp theo.

**Unchecked exception** có thể thoát mà compiler không buộc caller bắt/khai báo:

~~~java
static void failFast() {
    throw new IllegalStateException("trạng thái không hợp lệ");
}
~~~

Điều này không có nghĩa unchecked exception “an toàn hơn” hoặc “không phải ngoại lệ thật”. Nó chỉ khác về **quy tắc kiểm tra tại thời điểm biên dịch**.

## 3. Generic method có `throws E`

Một phương thức generic có thể công bố kiểu ngoại lệ bằng type parameter:

~~~java
// Đoạn minh họa bên trong một lớp.
static <E extends Exception> void perform(ThrowingAction<E> action) throws E {
    action.run();
}
~~~

Trong đó `ThrowingAction<E>` là functional interface:

~~~java
@FunctionalInterface
interface ThrowingAction<E extends Exception> {
    void run() throws E;
}
~~~

Kiểu `E` được dùng ở cả **chữ ký callback** và **mệnh đề throws của phương thức nhận callback**. Khi gọi, compiler có thông tin từ lambda hoặc kiểu của biến callback để quyết định checked exception cần xử lý.

Ví dụ:

~~~java
// Đoạn minh họa dùng hai khai báo trên.
perform(() -> {
    throw new java.io.IOException("lỗi I/O từ lambda");
});
~~~

Nếu lời gọi nằm trong một phương thức không khai báo `throws IOException` và không có `catch` phù hợp, nó **không được phép tự nhiên “thoát” lỗi này chỉ vì `E` là generic**. Ràng buộc phát sinh từ lambda có thể khiến `E` phải bao phủ `IOException`, vì vậy caller phải xử lý.

Đây là ý nghĩa lành mạnh của generic `throws E`: **truyền đúng hợp đồng checked exception từ callback tới người gọi**, thay vì buộc mọi callback phải công bố `throws Exception` rộng hoặc chuyển tất cả lỗi thành unchecked.

## 4. Suy luận `throws` trong JLS: điểm tinh tế

JLS §18 quy định suy luận kiểu cho generic method và các biểu thức lambda/method reference. Một số chi tiết có thể giải thích mà không cần thuộc toàn bộ thuật toán:

- Khi type variable `E` xuất hiện ở mệnh đề `throws E`, hệ thống suy luận lưu dấu một bound thông tin thường mô tả là **`throws α`** đối với inference variable tương ứng.
- Nếu không có ràng buộc cụ thể nào buộc `E` phải bao phủ checked exception, và các upper bounds cho phép, việc suy luận ưu tiên một **unchecked exception type**.
- Trong tình huống phổ biến khi upper bound là `Throwable` hoặc `Exception` và không có lower bound áp đặt kiểu checked, JLS §18.4 có quy tắc lựa chọn **`RuntimeException`** làm kiểu được suy ra.
- Ngược lại, **checked exception thực tế xuất hiện trong body lambda** có thể tạo ràng buộc bổ sung theo JLS §18.2.5, khiến `E` không còn tự do được chọn theo cách trên.
- Một **type witness** do lập trình viên chỉ rõ, ví dụ `SomeClass.<IOException>method(...)`, cũng có thể khiến caller phải tuân theo checked `throws IOException`.

Quy tắc này không có nghĩa compiler “đọc loại runtime” bằng cách chạy chương trình. Compiler giải các ràng buộc kiểu từ **chữ ký và biểu thức nguồn**, không quan sát sự cố ở runtime.

Đặc biệt, `throws α` trong giải thích JLS là **ký hiệu nội bộ của quá trình suy luận**, không phải cú pháp viết trực tiếp `throws α` trong mã Java thông thường. Lập trình viên viết type variable như `E`, còn ký hiệu α dùng để mô tả thuật toán.

## 5. Cơ chế của một helper `sneaky throw`

Một biến thể ngắn:

~~~java
@SuppressWarnings("unchecked")
static <E extends Throwable> void passThrough(Throwable failure) throws E {
    throw (E) failure;
}
~~~

Về cú pháp, phương thức này khai báo rằng nó có thể ném `E`, một subtype của `Throwable`. Bên trong, phép ép `(E) failure` là **unchecked cast** do thông tin generic bị xóa theo type erasure, nên annotation `@SuppressWarnings("unchecked")` chỉ nhằm loại bỏ cảnh báo liên quan. Annotation **không** tự bỏ qua compiler checking của caller.

Điểm mấu chốt nằm ở **chữ ký**:

- Đối số nhận vào có kiểu `Throwable`, **không phải `E`**.
- Vì vậy truyền `new IOException(...)` vào tham số `Throwable` **không trực tiếp áp đặt ràng buộc `E = IOException`** tại điểm gọi.
- Nếu không có ràng buộc khác, type variable `E` trong `throws E` có thể được compiler suy luận là `RuntimeException` theo quy tắc đã nêu.
- Caller không bị buộc `catch IOException`, dù đối tượng `Throwable` được truyền có thể đang là một `IOException`.

Ví dụ:

~~~java
static void hiddenFromSignature() {
    passThrough(new java.io.IOException("I/O ẩn"));
}
~~~

**Câu lệnh trên có thể biên dịch**, mặc dù `hiddenFromSignature()` không khai báo `throws IOException` và không bắt nó. Khi chạy, `IOException` vẫn được ném ra từ `passThrough`. Đây là điểm gây ra tên gọi **sneaky throw**.

Không nên khẳng định “Java luôn suy luận mọi `E extends Throwable` thành `RuntimeException`”. Suy luận còn phụ thuộc những ràng buộc khác từ tham số, target type, lambda hoặc type arguments tường minh. **Sneaky throw tận dụng đúng một tình huống cụ thể** mà các ràng buộc đó không buộc `E` thành checked exception.

## 6. Chương trình Java 17+ hoàn chỉnh: một `IOException` thực sự thoát ra

Tạo tệp `SneakyThrowDemo.java`:

~~~java
import java.io.IOException;

public class SneakyThrowDemo {
    @SuppressWarnings("unchecked")
    static <E extends Throwable> void passThrough(Throwable failure) throws E {
        throw (E) failure;
    }

    static void hiddenFromSignature() {
        passThrough(new IOException("I/O ẩn"));
    }

    static void explicitContract() throws IOException {
        SneakyThrowDemo.<IOException>passThrough(new IOException("I/O khai báo"));
    }

    public static void main(String[] args) {
        try {
            hiddenFromSignature();
        } catch (Throwable ex) {
            System.out.println("Thực tế: " + ex.getClass().getSimpleName()
                    + " - " + ex.getMessage());
        }

        try {
            explicitContract();
        } catch (IOException ex) {
            System.out.println("Rõ ràng: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SneakyThrowDemo.java
java SneakyThrowDemo
~~~

Stdout chính xác:

~~~text
Thực tế: IOException - I/O ẩn
Rõ ràng: I/O khai báo
~~~

Phân tích:

1. `hiddenFromSignature()` không có `throws`. Call `passThrough(new IOException(...))` cho phép compiler suy ra một lựa chọn unchecked cho `E`, nên lời gọi hợp lệ xét checked exceptions.
2. Đối tượng thực sự được ném vẫn là `IOException`; `ex.getClass().getSimpleName()` in `IOException`. Không có lớp `RuntimeException` mới được tạo.
3. `catch (Throwable ex)` đủ rộng để nhận đối tượng đã thoát khỏi phương thức bất kể loại checked hay unchecked. Đây là một lựa chọn **chỉ nhằm minh họa**; ứng dụng bình thường không nên bắt `Throwable` rộng để che cả `Error`.
4. `explicitContract()` dùng **type witness** `<IOException>`, khiến `passThrough` được gọi như phương thức có `throws IOException`. Vì thế bản thân `explicitContract()` phải khai báo `throws IOException` hoặc xử lý lỗi.
5. `main()` có `catch (IOException)` hợp lệ quanh lời gọi `explicitContract()` vì **chữ ký tĩnh** của phương thức này công bố `throws IOException`.

Sự khác biệt giữa hai phần của chương trình không phải runtime biết loại ngoại lệ nào sẽ xuất hiện. Khác biệt nằm ở **hợp đồng mà compiler nhìn thấy** khi kiểm tra từng lời gọi.

## 7. Vì sao không có `ClassCastException` ở chỗ `(E) failure`?

Một câu hỏi tự nhiên: nếu compiler suy ra `E = RuntimeException`, tại sao `(E) failure` trong helper lại không gây `ClassCastException` khi đối tượng là `IOException`?

Giải thích: Java generic sử dụng **type erasure**. Với type variable `E extends Throwable`, biểu thức cast trong code generic không tương đương việc JVM luôn kiểm tra đối tượng theo kiểu cụ thể `RuntimeException` tại vị trí ném đó. Trong helper này, giới hạn runtime cơ bản của `E` là `Throwable`; đối tượng `IOException` đáp ứng giới hạn ấy.

Câu lệnh `throw` ở JVM ném một đối tượng thuộc `Throwable`, không có cơ chế runtime tự đối chiếu bắt buộc loại ngoại lệ với **danh sách `throws` được compiler suy ra tại điểm gọi**. Chữ ký generic và `throws` phần lớn phục vụ **kiểm tra ngôn ngữ tại compile time**, không phải bộ lọc ngoại lệ runtime.

**Không suy rộng:** có những unchecked cast khác trong Java sẽ tạo kiểm tra runtime và có thể ném `ClassCastException`, nhất là khi giá trị bị ép sang một kiểu cụ thể, hẹp hơn. Kết luận ở đây áp dụng cho **mẫu helper đang trình bày**, không phải lời bảo đảm rằng mọi cast generic đều an toàn.

Ngoài ra, helper chỉ ném cùng đối tượng; nếu có nhiều tầng bọc ngoại lệ khác trong chương trình, chúng có thể tạo cause hoặc stack trace riêng, nhưng đó là công việc của các tầng ấy chứ không tự xảy ra do suy luận kiểu.

## 8. Compile time và runtime có thể “bất đồng” về ngoại lệ

So sánh hai phát biểu sau:

| Câu hỏi | Compiler tại lời gọi `hiddenFromSignature()` | Runtime nếu helper ném `IOException` |
| --- | --- | --- |
| Có `throws IOException` tĩnh cần xử lý? | Không | Không dùng chữ ký để chặn đối tượng được ném |
| Có thể bắt bằng `catch (RuntimeException)` nếu đối tượng là `IOException`? | `catch` của RuntimeException có thể hợp lệ trong code | **Không**. `IOException` không là subtype của RuntimeException |
| Có thể bắt bằng `catch (Exception)` hoặc `catch (Throwable)`? | Các nhánh đủ rộng có thể hợp lệ | Có, vì `IOException` thuộc các nhánh ấy |
| Loại thực tế của đối tượng? | Không được suy ra chỉ từ lựa chọn `E` | `IOException` |
| Caller được compiler nhắc `catch IOException`? | Không trong đường sneaky đã kiểm chứng | Ngoại lệ có thể vẫn thoát nếu không có handler thực tế phù hợp |

Một `catch (RuntimeException ex)` được phép trong code không có checked `throws`, nhưng **nó không “hóa giải” `IOException`** đã bị ném lén. Nếu chương trình chỉ bắt `RuntimeException`, đối tượng `IOException` có thể tiếp tục lan truyền đến nơi xử lý ngoài cùng.

Tương tự, cơ chế dispatch `catch` của Java dựa trên **loại runtime của đối tượng**, không dựa trên kiểu `E` mà compiler đã suy ra cho một generic call trước đó.

## 9. Lỗi biên dịch bất ngờ: `catch (IOException)` không được coi là reachable

Tệp `CatchCheckedBad.java` sau đây được viết **cố ý không biên dịch**:

~~~java
import java.io.IOException;

class CatchCheckedBad {
    @SuppressWarnings("unchecked")
    static <E extends Throwable> void pass(Throwable t) throws E {
        throw (E) t;
    }

    static void run() {
        try {
            pass(new IOException("I/O"));
        } catch (IOException ex) {
            System.out.println("Đã bắt IOException");
        }
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 CatchCheckedBad.java
~~~

Thông báo trọng tâm của `javac` Java 17:

~~~text
error: exception IOException is never thrown in body of corresponding try statement
~~~

**Tại sao?** Ở lời gọi generic `pass(new IOException(...))`, compiler có thể chọn `E` unchecked và không coi body của `try` là có checked `IOException` được khai báo. Vì vậy `catch (IOException)` **chỉ dựa trên lời gọi đó** bị xem là không hợp lệ tại compile time, dù ở runtime đối tượng `IOException` thực sự có thể được ném.

Đây là một trong những rủi ro rõ nhất: **hợp đồng thiếu trung thực khiến caller không thể viết ngay handler checked chuyên biệt theo cách tự nhiên**.

Cách sửa đúng nếu được quyền thay đổi API là **công bố `throws IOException` rõ ràng**, hoặc dùng type witness có kiểm soát trong phương thức đã khai báo `throws IOException`, như `explicitContract()` ở mục 6. Nếu bất đắc dĩ phải tương tác với code legacy dùng sneaky throw, cần hiểu rõ nơi ngoại lệ thoát và quyết định một boundary xử lý có thể kiểm tra được; đừng dùng `catch (Throwable)` tràn lan để che mất tất cả lỗi hệ thống.

## 10. Lambda không tự động bỏ qua checked exception

Một lambda chỉ có nghĩa khi gắn với **functional interface target type**. `Runnable.run()` không khai báo checked exception nào:

~~~java
@FunctionalInterface
interface Runnable {
    void run();
}
~~~

Đây là dạng chữ ký rút gọn của `java.lang.Runnable`, không phải lời khuyên định nghĩa lại `Runnable` trong code sử dụng. Vì thế:

~~~java
import java.io.IOException;

// CỐ Ý SAI:
class RunnableCheckedBad {
    Runnable x = () -> {
        throw new IOException("checked");
    };
}
~~~

không biên dịch. `javac` báo dạng:

~~~text
error: unreported exception IOException; must be caught or declared to be thrown
~~~

**Lý do:** body lambda có thể ném checked `IOException`, nhưng phương thức trừu tượng duy nhất `Runnable.run()` không cho phép ngoại lệ đó thoát.

Không thể sửa bằng cách thêm `throws IOException` vào method bao ngoài chứa phép gán lambda rồi kỳ vọng target type `Runnable` thay đổi. Thân lambda phải phù hợp với chữ ký của **functional interface** mà nó đang triển khai. Phương thức bao ngoài có `throws IOException` chỉ công bố ngoại lệ trực tiếp ở thân phương thức đó, không tự thay `Runnable.run()`.

Có ba cách thiết kế phù hợp: dùng functional interface có `throws` phù hợp, xử lý lỗi ngay trong lambda, hoặc bọc lỗi thành unchecked có nguyên nhân được bảo toàn.

## 11. Generic functional interface giúp lan truyền đúng checked exception

Định nghĩa:

~~~java
@FunctionalInterface
interface ThrowingAction<E extends Exception> {
    void run() throws E;
}
~~~

Và phương thức generic:

~~~java
static <E extends Exception> void perform(ThrowingAction<E> action) throws E {
    action.run();
}
~~~

Nếu lambda body ném `IOException`, suy luận cần phản ánh loại checked ấy:

~~~java
// Minh họa trong phương thức đã khai báo throws IOException hoặc có catch.
perform(() -> {
    throw new java.io.IOException("lambda I/O");
});
~~~

Nếu caller chỉ muốn viết:

~~~java
static void ordinaryCaller() {
    perform(() -> {
        throw new java.io.IOException("lambda I/O");
    });
}
~~~

thì đoạn này **không biên dịch** do checked exception chưa được xử lý. Đây là điều nên có: caller nhìn thấy trách nhiệm về lỗi từ callback.

Tình huống không có checked exception trong lambda, chẳng hạn lambda chỉ in log hoặc ném `IllegalStateException`, có thể suy luận kiểu phù hợp mà không yêu cầu thêm `throws IOException`.

## 12. Chương trình Java 17+ hoàn chỉnh: generic lambda làm đúng hợp đồng

Lưu thành `GenericLambdaDemo.java`:

~~~java
import java.io.IOException;

public class GenericLambdaDemo {
    @FunctionalInterface
    interface ThrowingAction<E extends Exception> {
        void run() throws E;
    }

    static <E extends Exception> void perform(ThrowingAction<E> action) throws E {
        action.run();
    }

    static void checkedCase() throws IOException {
        perform(() -> {
            throw new IOException("lambda I/O");
        });
    }

    static void uncheckedCase() {
        perform(() -> {
            throw new IllegalStateException("lambda trạng thái");
        });
    }

    static void noThrowCase() {
        perform(() -> System.out.println("Lambda bình thường"));
    }

    public static void main(String[] args) {
        try {
            checkedCase();
        } catch (IOException ex) {
            System.out.println("Đã bắt: " + ex.getMessage());
        }

        try {
            uncheckedCase();
        } catch (IllegalStateException ex) {
            System.out.println("Unchecked: " + ex.getMessage());
        }

        noThrowCase();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericLambdaDemo.java
java GenericLambdaDemo
~~~

Stdout chính xác:

~~~text
Đã bắt: lambda I/O
Unchecked: lambda trạng thái
Lambda bình thường
~~~

Phân tích:

1. `checkedCase()` chứa lambda thực sự ném `IOException`; compiler yêu cầu phương thức này khai báo hoặc bắt checked exception. Ở đây chữ ký có `throws IOException`.
2. `main()` bắt `IOException` do chữ ký `checkedCase()` công bố loại đó.
3. `uncheckedCase()` có lambda ném `IllegalStateException`; đây là unchecked, nên không cần khai báo checked `throws`.
4. `noThrowCase()` dùng lambda hoàn tất bình thường. Không có checked exception cần công bố.
5. Method generic `perform` **không làm biến mất lỗi**; nó truyền contract type `E` từ callback lên caller. Đây là mô hình generic `throws` minh bạch, trái với sneaky throw chủ động che loại checked.

Cùng nguyên lý có thể áp dụng cho **method reference** có `throws` phù hợp, ví dụ một method reference tới phương thức đọc dữ liệu checked được dùng với một functional interface có khai báo `throws IOException`. Chữ ký của target type vẫn là điều kiện quan trọng, không chỉ cú pháp lambda hay `::`.

## 13. Suy luận khi không có lỗi checked khác với cố tình giấu lỗi

Hai lời gọi có thể trông tương tự:

~~~java
// Không tạo checked exception trong lambda:
perform(() -> System.out.println("x"));
~~~

~~~java
// Có checked IOException trong lambda:
perform(() -> { throw new java.io.IOException("lỗi"); });
~~~

Trong lời gọi đầu, không có ràng buộc phải bao phủ `IOException`, nên compiler có thể suy luận một ngoại lệ unchecked thích hợp cho `E`. Trong lời gọi thứ hai, body lambda góp ràng buộc checked exception; compiler không thể tùy ý bỏ nó để vẫn coi chương trình đúng.

**Sneaky throw khác ở chỗ đối tượng checked được đưa vào tham số kiểu `Throwable`, không phải qua chính một lambda body được kiểm tra đối với `throws E`.** Từ đó thiếu ràng buộc làm `E` biểu diễn chính xác loại checked của đối tượng.

Hãy đánh giá API dựa vào đường truyền thông tin kiểu:

~~~text
Generic callback an toàn:
lambda throws IOException
        ↓ (ràng buộc checked exception)
ThrowingAction<E>.run() throws E
        ↓
perform(...) throws E
        ↓
caller phải catch/declare IOException

Sneaky helper:
IOException object → tham số Throwable
        ↓ (không ép E = IOException)
passThrough(Throwable) throws E
        ↓ (có thể suy ra E = RuntimeException)
caller không bị catch/declare IOException
        ↓
runtime vẫn ném đối tượng IOException
~~~

Sơ đồ mô tả **hợp đồng compile time**, không phải một chuỗi wrapper runtime; với sneaky helper không có đối tượng `RuntimeException` được tự tạo trên đường này.

## 14. Rủi ro của sneaky throw đối với hợp đồng public API

Vấn đề lớn nhất không phải là helper dài hay ngắn, mà là **người dùng API không thể hiểu đúng từ chữ ký**.

Ví dụ:

~~~java
public void process() {
    passThrough(new java.io.IOException("không kết nối được"));
}
~~~

Người đọc thấy `process()` không khai báo `throws IOException`. Nếu triển khai hoặc thư viện không công bố hành vi ngoại lệ lén, caller có thể:

- Chỉ bắt `RuntimeException` với giả định tất cả lỗi không khai báo là unchecked.
- Không triển khai cleanup hoặc rollback phù hợp với lỗi I/O.
- Không biết phải dùng boundary nào để bắt một `IOException` runtime.
- Ghi log thiếu phân loại khiến chẩn đoán khó hơn.
- Viết test kỳ vọng `RuntimeException` nhưng nhận `IOException`.

Quan trọng hơn, việc **refactor** có thể làm đổi kết quả compiler nếu ràng buộc suy luận kiểu ở điểm gọi thay đổi. Một lời gọi có explicit type argument `<IOException>` không giống một lời gọi để compiler tự suy luận; thay đổi generic signature cũng có thể thay đổi nghĩa vụ `throws`.

**Đừng coi unchecked inference là sự cho phép về hợp đồng.** Java có quy tắc suy luận đặc biệt, nhưng người thiết kế API vẫn chịu trách nhiệm cung cấp hành vi dễ hiểu và có thể kiểm thử.

## 15. Nguy cơ khi dùng sneaky throw với callback, Stream và thư viện bên ngoài

Các API Java chuẩn như `Runnable`, `Supplier<T>`, `Function<T,R>`, `Consumer<T>`, `Predicate<T>` **không công bố checked exceptions** trong abstract method chính. Nếu một lambda bên trong muốn gọi API ném `IOException`, compiler từ chối đường checked trực tiếp:

~~~java
// CỐ Ý SAI nếu readFromDisk() throws IOException.
java.util.function.Supplier<String> supplier = () -> readFromDisk();
~~~

Một số người chuyển sang helper sneaky để đưa checked exception qua lambda mà không sửa kiểu. Cách đó có thể chạy, nhưng làm callback **vi phạm kỳ vọng ngữ nghĩa** của người dùng API.

Ví dụ rủi ro với pipeline Stream:

- Biểu thức `map(...)` có thể bị trì hoãn cho đến terminal operation; exception thực tế phát sinh ở lúc pipeline được thực thi.
- Một pipeline có nhiều bước có thể làm vị trí lỗi khó lần ra.
- `catch (IOException)` quanh terminal operation có thể **không được compiler chấp nhận** nếu chỉ căn cứ vào chữ ký Stream API không khai báo checked `IOException`.
- Nếu dùng thư viện hoặc framework bất đồng bộ, ngoại lệ có thể còn được wrap, truyền qua future/result object hoặc log ở nơi khác theo hợp đồng riêng của thư viện.
- Code downstream có thể phân loại nhầm nếu chỉ dựa vào giả định “callback không thể ném checked exception”.

Không có quy tắc rằng mọi API Stream sẽ tự **chuyển `IOException` sang unchecked**. Cách ngoại lệ lan truyền trong Stream phụ thuộc vào đối tượng được ném và các tầng bao quanh; sneaky throw khiến checked exception có thể thoát qua vị trí mà chữ ký không phản ánh nó.

Trong ứng dụng sản phẩm, **bọc `IOException` thành `UncheckedIOException` một cách tường minh** là lựa chọn rõ ràng hơn nếu API buộc dùng `Function` không khai báo checked exception.

## 16. Thay thế thứ nhất: `UncheckedIOException` với nguyên nhân được giữ lại

Nếu một lambda dùng API I/O chuẩn cần phù hợp với `Function<T,R>`, một phương án là bắt `IOException` và chuyển thành `UncheckedIOException`:

~~~java
// Mã minh họa trong lambda có biến name.
try {
    return readName(name);
} catch (java.io.IOException ex) {
    throw new java.io.UncheckedIOException("Không đọc được " + name, ex);
}
~~~

`UncheckedIOException` là một lớp unchecked được Java cung cấp **dành riêng cho lỗi I/O được bọc**, có `getCause()` trả về `IOException` gốc. Cách này làm rõ cho caller rằng có một **unchecked wrapper** cần được xử lý theo hợp đồng API, thay vì lén chuyển một `IOException` qua chữ ký không công bố.

**Không dùng `UncheckedIOException` cho mọi checked exception**. Constructor của nó đòi `IOException` làm cause; với `SQLException` hoặc exception nghiệp vụ, cần chọn unchecked wrapper có ý nghĩa đúng hoặc thiết kế một result/callback interface khác.

## 17. Ví dụ Java 17+ hoàn chỉnh: adapter rõ ràng cho Stream

Tệp `CheckedLambdaAdapterDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.function.Function;

public class CheckedLambdaAdapterDemo {
    static String readName(String name) throws IOException {
        if ("missing".equals(name)) {
            throw new IOException("không đọc được " + name);
        }
        return name.toUpperCase();
    }

    static Function<String, String> reader() {
        return name -> {
            try {
                return readName(name);
            } catch (IOException ex) {
                throw new UncheckedIOException("Lỗi đọc: " + name, ex);
            }
        };
    }

    public static void main(String[] args) {
        try {
            System.out.println(List.of("ok", "missing").stream()
                    .map(reader()).toList());
        } catch (UncheckedIOException ex) {
            System.out.println("Bao ngoài: " + ex.getMessage());
            System.out.println("Nguyên nhân: " + ex.getCause().getMessage());
        }
    }
}
~~~

Lệnh Java 17:

~~~bash
javac -encoding UTF-8 CheckedLambdaAdapterDemo.java
java CheckedLambdaAdapterDemo
~~~

Stdout chính xác:

~~~text
Bao ngoài: Lỗi đọc: missing
Nguyên nhân: không đọc được missing
~~~

Giải thích:

1. `reader()` trả `Function<String,String>`, là kiểu mà `Stream.map()` sử dụng.
2. `readName("ok")` thành công và trả `"OK"`. `readName("missing")` ném `IOException`.
3. Lambda bắt `IOException` và **tạo một `UncheckedIOException` rõ ràng**, truyền nguyên nhân qua constructor.
4. Khi terminal operation `toList()` thực thi pipeline, unchecked wrapper thoát ra; không có danh sách được in vì hoạt động `map` không hoàn tất.
5. `catch (UncheckedIOException)` ở `main` hợp lệ và nhận đúng kiểu wrapper; `getCause()` cho biết lỗi I/O gốc.
6. Ví dụ cố ý mô phỏng lỗi bằng điều kiện trên tên, không phụ thuộc vào tệp thực tế. Đường đi của `List.of(...).stream()` trong ví dụ là tuần tự, giúp kết quả ổn định.

Nếu API gọi dùng `Stream` của dữ liệu thật, vẫn cần quyết định **fail-fast, tiếp tục từng phần, lưu lỗi cho từng phần tử hay trả một kết quả tổng hợp**. `UncheckedIOException` minh bạch hơn sneaky throw nhưng không tự quyết định chính sách nghiệp vụ.

## 18. Thay thế thứ hai: `ThrowingFunction` hoặc `ThrowingSupplier`

Nếu bạn kiểm soát API, có thể thiết kế functional interface có tham số exception:

~~~java
@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}
~~~

Và hàm xử lý:

~~~java
static <T, E extends Exception> T supply(
        ThrowingSupplier<T, E> supplier) throws E {
    return supplier.get();
}
~~~

Khi truyền lambda ném `IOException`:

~~~java
// Đoạn minh họa trong phương thức throws IOException.
String value = supply(() -> readName("missing"));
~~~

`readName` là phương thức có `throws IOException`. Khi được suy luận theo kiểu functional interface trên, `IOException` không “biến mất”: caller của `supply` phải xử lý hoặc khai báo theo hợp đồng thực tế.

**Nhược điểm:** `ThrowingSupplier` tùy chỉnh không phải lúc nào thay trực tiếp được `java.util.function.Supplier` trong API chuẩn. Bạn cần một adapter có chính sách rõ ràng ở ranh giới chuyển đổi, hoặc sử dụng các API phù hợp cho checked callback.

**Ưu điểm:** callback và caller nhìn thấy đường lỗi theo compile-time checking. Đây là lựa chọn đặc biệt hữu ích cho thư viện nội bộ được thiết kế quanh I/O, database hoặc thao tác có checked exception một cách tự nhiên.

## 19. Thay thế thứ ba: xử lý hoặc trả về kết quả có cấu trúc

Không phải mọi thất bại của một bước xử lý phải được ném qua nhiều tầng:

~~~java
// Ví dụ minh họa phương thức có thể trả về một kiểu kết quả.
record ReadResult(String value, String error) {
    static ReadResult success(String value) {
        return new ReadResult(value, null);
    }

    static ReadResult failure(String reason) {
        return new ReadResult(null, reason);
    }
}
~~~

Đây là một record Java 17 hợp lệ; code ví dụ không biểu diễn đầy đủ invariants của result object, nên trong hệ thống thật cần đảm bảo hai trạng thái thành công/thất bại không nhập nhằng.

Với batch processing, một cấu trúc kết quả chứa `value` hoặc `error` trên từng phần tử có thể hợp lý hơn việc để một checked exception thoát lén qua `Stream.map()`. Caller có thể:

- Thu thập cả thành công lẫn thất bại.
- Xác định phần tử nào cần retry.
- Không cần dùng exception để biểu diễn một kết quả dự kiến thường gặp.
- Có chính sách riêng cho partial success.

Cần chú ý tránh trả thành công giả tạo khi thao tác thực tế đã thất bại. Một lựa chọn tốt không chỉ làm compiler hài lòng; nó phải giữ **ngữ nghĩa thất bại**.

## 20. So sánh `sneaky throw`, checked generic API và unchecked wrapper

| Tiêu chí | Generic API `throws E` minh bạch | Sneaky throw | `UncheckedIOException` |
| --- | --- | --- | --- |
| Checked exception của callback có được biểu diễn ở lời gọi? | Có, khi constraints/type witness truyền đúng checked type | Có thể bị suy luận thành unchecked tại call site | Không cần checked `throws`; wrapper là unchecked |
| Loại đối tượng ném ra | Thường giữ nguyên ngoại lệ của callback | Giữ nguyên checked exception gốc | Tạo **đối tượng wrapper mới** |
| Caller biết nên `catch IOException`? | Có khi hợp đồng công bố `IOException` | Thường không, có thể lỗi compile khi bắt chuyên biệt | Caller bắt `UncheckedIOException`, tìm `IOException` qua cause |
| Cause/stack trace | Phụ thuộc đối tượng gốc; không bắt buộc wrapper | Không tự tạo cause/wrapper | Giữ cause `IOException`, wrapper có stack trace riêng |
| Rõ ràng về hợp đồng | Cao | Thấp nếu không tài liệu hóa rất rõ | Cao hơn nếu API ghi nhận loại wrapper |
| Nên dùng cho ứng dụng thông thường? | Có, khi checked phù hợp | Thường nên tránh | Có, ở boundary API không hỗ trợ checked và lỗi đúng loại I/O |
| Rủi ro chính | Signature generic phức tạp nếu lạm dụng | Che loại checked runtime khỏi compiler | Chuyển nghĩa vụ checked sang unchecked; caller phải biết hợp đồng runtime |

Không có phương án nào miễn phí. Với unchecked wrapper, compiler vẫn không **bắt buộc** caller `catch`; điều nó cải thiện là **tính minh bạch về đối tượng thực tế và cách lấy cause**, không phải tự động khôi phục nghĩa vụ checked exception.

## 21. Sneaky throw khác với precise rethrow của Java

Java có một cơ chế khác thường bị nhầm với sneaky throw: **phân tích ném lại ngoại lệ tương đối chính xác** (`precise rethrow`) trong các trường hợp `catch` phù hợp.

Ví dụ:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Đoạn minh họa trong lớp có hàm operation() ném hai loại checked.
static void process() throws IOException, SQLException {
    try {
        operation();
    } catch (Exception ex) {
        throw ex;
    }
}
~~~

Ở đây `operation()` cần được định nghĩa với `throws IOException, SQLException`, và biến `ex` không bị gán lại. Compiler có thể phân tích những loại checked exception cụ thể phát sinh từ vùng `try` để chấp nhận mệnh đề `throws IOException, SQLException` thay vì ép method công bố `throws Exception` rộng.

**Đây không phải sneaky throw**:

- Các loại checked phù hợp vẫn xuất hiện trong hợp đồng method.
- Caller vẫn phải bắt hoặc khai báo chúng.
- Không cố dùng type variable không bị ràng buộc để làm mất nghĩa vụ checked.
- Việc phân tích phụ thuộc những điều kiện JLS quy định, gồm tình trạng *effectively final* của tham số catch và khả năng ném từ vùng `try`.

Đừng gom mọi trường hợp compiler suy ra một `throws` hẹp hơn vào nhãn “sneaky”. Suy luận chính xác để **bảo toàn** hợp đồng khác với thủ thuật cố ý **che** loại ngoại lệ.

## 22. Sneaky throw khác với `throw new RuntimeException(ex)`

So sánh:

~~~java
// Minh họa trong catch (IOException ex).
throw new RuntimeException("Không thể đọc dữ liệu", ex);
~~~

và:

~~~java
// Minh họa trong cùng ngữ cảnh, helper passThrough(...) đã định nghĩa.
passThrough(ex);
~~~

Ở trường hợp thứ nhất:

- Tạo **một đối tượng `RuntimeException` mới**.
- Đối tượng mới có `IOException` làm `cause`.
- `catch (RuntimeException)` bên ngoài có thể bắt wrapper.
- `getCause()` và stack trace cho thấy cả tầng bọc lẫn lỗi I/O gốc.

Ở trường hợp thứ hai:

- Không tự tạo wrapper mới.
- Nếu helper ném `ex`, đối tượng thoát ra vẫn chính là `IOException`.
- `catch (RuntimeException)` sẽ **không** bắt `IOException`.
- Danh tính đối tượng và các dữ liệu trên ngoại lệ gốc vẫn được giữ nguyên.
- `throws` tĩnh của phương thức caller có thể không phản ánh `IOException`.

Kỹ thuật thứ hai dễ gây bất ngờ hơn, vì người dùng phương thức không thể suy từ chữ ký rằng một checked exception cụ thể sẽ thoát.

## 23. Type witness tường minh có thể thay đổi nghĩa vụ `throws`

Trở lại helper:

~~~java
static <E extends Throwable> void passThrough(Throwable failure) throws E {
    throw (E) failure;
}
~~~

Đây là **mã minh họa không gồm annotation suppress warning**; bản thân generic cast có thể sinh cảnh báo unchecked. Khi gọi:

~~~java
passThrough(new java.io.IOException("I/O"));
~~~

compiler có thể suy ra `E` là một loại unchecked nếu không có constraints cụ thể khác. Nhưng nếu viết:

~~~java
SomeClass.<java.io.IOException>passThrough(
        new java.io.IOException("I/O"));
~~~

với `SomeClass` là lớp khai báo `passThrough`, `E` đã được người gọi chỉ định là `IOException`, khiến lời gọi thuộc đường checked exception. Caller phải xử lý hoặc khai báo `IOException`.

Sự khác biệt này chỉ liên quan **kiểm tra tĩnh**: runtime vẫn nhận cùng một kiểu đối tượng ngoại lệ trong hai lời gọi nếu tham số được tạo giống nhau.

Tuy nhiên không nên dùng type witness như một “giải pháp chữa sneaky throw” cho mọi caller bên ngoài. Một public API được thiết kế tốt nên công bố hợp đồng lỗi trực tiếp, thay vì buộc người dùng hiểu nội bộ generic và gắn type argument đặc biệt để làm compiler nhận diện checked exception.

## 24. Sự thật về `@SuppressWarnings("unchecked")`

Tên annotation có thể khiến người mới học hiểu sai:

~~~java
@SuppressWarnings("unchecked")
static <E extends Throwable> void passThrough(Throwable t) throws E {
    throw (E) t;
}
~~~

Annotation trên:

- **Không chuyển** `IOException` thành unchecked exception.
- **Không sửa** `throws E` thành `throws RuntimeException`.
- **Không thay** runtime dispatch của `catch`.
- **Không đảm bảo** cast là an toàn xét kiểu cụ thể.
- Chỉ **ẩn cảnh báo compiler** thuộc loại unchecked cast trong vùng áp dụng.

Lý do caller không bị buộc xử lý `IOException` trong một số lời gọi nằm ở **chữ ký generic và kết quả suy luận `E`**, chứ không nằm ở annotation.

Khi xem code có `@SuppressWarnings("unchecked")`, đừng kết luận tự động có sneaky throw. Rất nhiều generic API hợp lệ cũng phải sử dụng unchecked cast có kiểm soát. Nhưng nếu annotation xuất hiện cạnh helper `<E extends Throwable> ... throws E` nhận một tham số `Throwable` độc lập với `E`, đó là dấu hiệu cần rà soát hợp đồng ngoại lệ.

## 25. Một số điều sai dễ gặp trong bài toán này

| Phát biểu hoặc thói quen | Vì sao không đúng? | Cách hiểu đúng |
| --- | --- | --- |
| “Generic `throws E` luôn bỏ checked exception.” | Lambda có thể góp checked constraints, type witness có thể đặt `E` cụ thể. | Xem toàn bộ các ràng buộc suy luận và target type. |
| “Sneaky throw đổi `IOException` thành `RuntimeException`.” | Loại runtime đối tượng không thay đổi. | Compiler có thể suy luận `E` unchecked, còn đối tượng vẫn là `IOException`. |
| “`catch (RuntimeException)` chắc chắn bắt được lỗi sneaky.” | `IOException` không thuộc nhánh RuntimeException. | Dispatch theo class runtime thực tế. |
| “Cứ viết `catch (IOException)` quanh lời gọi sneaky là được.” | Compiler có thể cho rằng `try` không ném checked IOException. | Công bố checked contract hoặc xử lý ở boundary phù hợp. |
| “Đã dùng `@SuppressWarnings` thì mọi thứ an toàn.” | Annotation chỉ ẩn cảnh báo, không sửa logic. | Đánh giá cast và hợp đồng độc lập. |
| “Lambda trong `Runnable` được ném IOException nếu method ngoài có throws IOException.” | Target method `Runnable.run()` không khai báo checked exception. | Dùng functional interface phù hợp hoặc xử lý/wrap trong lambda. |
| “`Function<T,R>` tự chuyển checked thành unchecked.” | API không có cơ chế biến đổi ngoại lệ như vậy. | Bọc rõ ràng nếu cần hoặc dùng API khác. |
| “Mọi generic method có throws type variable đều sneaky.” | Nhiều generic method truyền checked constraints đúng. | Phân biệt callback `throws E` có ràng buộc với helper tách `Throwable` khỏi `E`. |
| “Sneaky throw chỉ là vấn đề biên dịch, không có hậu quả runtime.” | Đối tượng checked vẫn có thể thoát và không được handler kỳ vọng bắt. | Thiết kế chính sách lỗi và kiểm thử đường runtime. |
| “Unchecked wrapper và sneaky throw giống nhau.” | Wrapper tạo đối tượng mới có cause, sneaky thường ném chính đối tượng gốc. | Phân biệt danh tính, cause và kiểu runtime. |
| “Đã suy luận `E=RuntimeException`, JVM sẽ checkcast đối tượng IOException sang RuntimeException.” | Không phải hành vi của helper generic được type-erasure ở đây. | Hiểu erasure và cơ chế ném `Throwable` ở JVM. |
| “Không cần giữ cause khi bọc.” | Mất ngữ cảnh và stack trace lỗi tầng dưới. | Dùng constructor `(message,cause)`. |
| “Cứ dùng `catch(Throwable)` để sửa tất cả.” | Có thể che cả `Error`, làm xử lý lỗi thiếu kiểm soát. | Sửa API hoặc dùng boundary được thiết kế riêng. |

## 26. Cách nhận diện sneaky throw trong code review

Một checklist thực dụng:

1. Có helper generic dạng `<E extends Throwable> ... throws E` không?
2. Type variable `E` có thực sự được ràng buộc bởi kiểu tham số/functional interface, hay chỉ xuất hiện trong `throws` và cast?
3. Phương thức nhận `Throwable` độc lập với `E` và dùng `throw (E) t` không?
4. Caller có không khai báo checked exception mặc dù truyền `IOException`, `SQLException` hoặc checked exception khác không?
5. Có `@SuppressWarnings("unchecked")` gần cast generic liên quan không?
6. Có API `Runnable`, `Supplier`, `Function`, `Stream.map` hoặc callback không công bố checked exception không?
7. Thực tế runtime exception nào được ném — loại gốc hay wrapper?
8. Handler bên ngoài chỉ bắt `RuntimeException` hay có chiến lược phù hợp với loại thực tế?
9. Người dùng public API có được tài liệu hóa rõ loại checked exception có thể thoát không?
10. Có lựa chọn minh bạch hơn: checked generic callback, `UncheckedIOException`, custom unchecked wrapper, result object hoặc xử lý cục bộ không?

Nếu helper được dùng ở một thư viện legacy và chưa thể thay đổi ngay, cần kiểm thử **những tình huống thất bại thực tế**, không chỉ compile code gọi. Ghi rõ trong tài liệu kỹ thuật điểm nào có thể ném checked exception ngoài chữ ký và lên kế hoạch loại bỏ sự lệch hợp đồng khi có thể.

## 27. Kiểm thử đường lỗi sao cho không bị compiler đánh lừa

Khi nghi ngờ một API có sneaky throw, nên có cả hai loại kiểm thử:

**Kiểm thử compile-time:** xác minh một số lời gọi hợp lệ hay bị từ chối như dự kiến. Ví dụ `RunnableCheckedBad.java` và `CatchCheckedBad.java` ở bài này **cố ý không biên dịch**. Đây là bằng chứng compiler không coi hai trường hợp đó tương đương với việc công bố `throws IOException`.

**Kiểm thử runtime:** tạo đối tượng checked exception cụ thể và quan sát đối tượng cuối cùng mà một boundary bắt được:

~~~java
// Đoạn minh họa với helper passThrough được định nghĩa.
try {
    passThrough(new java.io.IOException("sự cố"));
} catch (Throwable ex) {
    System.out.println(ex.getClass().getName());
}
~~~

Sơ đồ này chỉ dành cho test/chẩn đoán. Trong code sản phẩm, `catch(Throwable)` quá rộng cho hầu hết nghiệp vụ; tránh nuốt `OutOfMemoryError`, `ThreadDeath` hoặc những loại `Error` không nên xử lý theo cách lỗi nghiệp vụ thông thường.

Với unchecked wrapper đúng thiết kế, có thể assert `ex instanceof UncheckedIOException` và `ex.getCause() instanceof IOException`. Với sneaky helper, có thể kiểm tra **cùng một đối tượng Throwable** được ném ra, nhưng phép thử đó không chứng minh API nên được dùng theo cách ấy.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** `IOException` có tự trở thành `RuntimeException` khi đi qua sneaky helper không?

**Đáp án:** Không. Runtime object vẫn là `IOException`; chỉ việc suy luận `throws E` tại compile time có thể không buộc caller xử lý checked exception.

**Câu 2.** Một lambda `() -> { throw new IOException(); }` có gán thẳng cho `Runnable` được không?

**Đáp án:** Không, vì `Runnable.run()` không khai báo checked `IOException`.

**Câu 3.** Vì sao `perform(() -> { throw new IOException(); })` với `ThrowingAction<E>` có thể khiến caller phải xử lý IOException?

**Đáp án:** Checked exception từ body lambda tạo ràng buộc đối với kiểu `E` trong `throws` của target functional interface và generic method.

**Câu 4.** Trong sneaky helper nhận `Throwable`, tại sao tham số là `Throwable` quan trọng?

**Đáp án:** Vì đối số `new IOException()` không trực tiếp bắt buộc `E=IOException`; type variable trong `throws E` có thể được suy ra unchecked khi không có ràng buộc khác.

**Câu 5.** Có thể tự động bắt đối tượng sneaky `IOException` bằng `catch(RuntimeException)` không?

**Đáp án:** Không. Catch dựa vào kiểu runtime, mà `IOException` không phải subtype của `RuntimeException`.

**Câu 6.** Nếu chỉ có lời gọi sneaky trong `try`, `catch(IOException)` có thể bị compiler từ chối không?

**Đáp án:** Có. Trong ví dụ kiểm chứng, `javac` báo `IOException` không được coi là ngoại lệ checked có thể ném từ thân `try` theo thông tin tĩnh.

**Câu 7.** `@SuppressWarnings("unchecked")` có phải thứ làm `throws E` trở thành unchecked không?

**Đáp án:** Không. Nó chỉ ẩn cảnh báo cast; kết quả là do suy luận kiểu và các ràng buộc generic.

**Câu 8.** Gọi `SneakyThrowDemo.<IOException>passThrough(...)` khác gì để compiler tự suy luận?

**Đáp án:** Type witness chỉ rõ `E=IOException`; lời gọi được kiểm tra theo checked `throws IOException`.

**Câu 9.** Vì sao `UncheckedIOException` thường minh bạch hơn sneaky throw trong Stream?

**Đáp án:** Vì caller thấy một **loại runtime ngoại lệ wrapper có chủ đích**, và lỗi I/O gốc được giữ ở `getCause()`, thay vì một checked exception thoát khỏi chữ ký không công bố nó.

**Câu 10.** Generic `throws E` có luôn là anti-pattern không?

**Đáp án:** Không. Nó hữu ích và đúng ngữ nghĩa với functional interface/callback có khai báo `throws E` và truyền checked constraints tới caller.

**Câu 11.** Precise rethrow `catch(Exception ex) { throw ex; }` có giống sneaky throw không?

**Đáp án:** Không. Precise rethrow suy ra các checked exception thực sự được vùng `try` phép ném theo điều kiện JLS; caller vẫn nhận hợp đồng `throws` đúng.

**Câu 12.** Khi refactor một public API đang dùng sneaky throw, nên làm gì?

**Đáp án:** Xác định những exception runtime thực sự thoát ra, quyết định contract checked hoặc unchecked minh bạch, giữ nguyên cause nếu bọc, cập nhật test/caller và công bố thay đổi tương thích.

## 29. Tài liệu tham khảo chính thức

- [Java Language Specification 17 — §18.1.3, Bounds](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.1.3): mô tả bound thông tin `throws α` khi inference variable xuất hiện trong `throws`.
- [Java Language Specification 17 — §18.2.5, Checked Exception Constraints](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.2.5): ràng buộc checked exception từ lambda/method reference.
- [Java Language Specification 17 — §18.4, Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.4): khi không có lower bounds phù hợp và upper bounds cho phép, một inference variable trong `throws` có thể được gán `RuntimeException`.
- [Java Language Specification 17 — §11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): quy tắc kiểm tra checked exception.
- [Java Language Specification 17 — §15.27.3, Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): lambda và target functional interface.
- [Java Language Specification 17 — §4.6, Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): ý nghĩa type erasure.
- [Java SE 17 API — `java.io.UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): unchecked wrapper có `IOException` làm cause.
- [Java SE 17 API — `java.util.function.Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): functional interface dùng trong Stream, không có checked `throws` ở phương thức `apply`.

**Kết luận:** Generic `throws E` là tính năng thiết kế API hợp lệ, đặc biệt khi kết hợp với lambda và functional interface có checked exceptions. **Sneaky throw** xuất hiện khi type variable dùng trong `throws` không bị ràng buộc đủ để giữ loại ngoại lệ checked; compiler có thể suy ra kiểu unchecked, còn runtime vẫn ném đối tượng `IOException` thật. Vì rủi ro đối với hợp đồng và handler của caller, nên ưu tiên **catch-or-declare minh bạch, callback có `throws E`, unchecked wrapper đúng ngữ nghĩa hoặc result object có cấu trúc** thay vì che checked exception.
