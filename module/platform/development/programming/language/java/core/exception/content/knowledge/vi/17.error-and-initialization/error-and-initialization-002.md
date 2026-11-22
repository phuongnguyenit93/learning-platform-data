# `AssertionError` và câu lệnh `assert` trong Java

`assert` là một câu lệnh của Java dùng để kiểm tra **giả định nội bộ của chương trình** (*internal invariant*): một điều kiện mà lập trình viên tin rằng phải đúng nếu phần còn lại của mã hoạt động theo thiết kế. Khi các assertion được **bật** và điều kiện sai, Java ném `java.lang.AssertionError`. Khi assertion được **tắt**, Java **không đánh giá** điều kiện lẫn biểu thức thông báo đi kèm.

Đây là khác biệt quan trọng với validation thông thường: `assert` **mặc định bị tắt** trong một lần chạy JVM phổ biến, và có thể bật/tắt qua tùy chọn khi khởi chạy. Vì vậy, không dùng `assert` làm cơ chế duy nhất để xác minh tham số public API, dữ liệu người dùng, quyền truy cập, số dư hoặc điều kiện có ảnh hưởng đến tính đúng đắn khi chạy production.

Bài thuộc Java Core – Exception, ngữ cảnh **Error và khởi tạo**, tập trung vào cú pháp và cơ chế `assert`, `AssertionError` trong cây kế thừa, lệnh `-ea`/`-da`, khác biệt giữa assertion và exception hợp đồng, đánh giá biểu thức, side effect, liên hệ class initialization và ví dụ Java 17+ chạy độc lập.

## 1. Nhận diện `AssertionError`

Phân cấp rút gọn:

~~~text
java.lang.Object
    └── java.lang.Throwable
        ├── java.lang.Exception
        │   └── java.lang.RuntimeException
        │       ├── IllegalArgumentException
        │       ├── IllegalStateException
        │       └── NullPointerException
        └── java.lang.Error
            └── java.lang.AssertionError
~~~

Các hệ quả:

- `AssertionError` là **unchecked throwable** vì kế thừa `Error`.
- Trình biên dịch **không yêu cầu** phải viết `throws AssertionError`.
- `catch (Exception e)` **không bắt** `AssertionError`, vì `Error` không nằm trong nhánh `Exception`.
- `catch (AssertionError e)`, `catch (Error e)` hoặc `catch (Throwable e)` có thể bắt được nó về mặt kiểu, nhưng **không nên bắt rồi bỏ qua mặc định** trong code nghiệp vụ.
- `AssertionError` thường báo một **giả định lập trình hoặc phép kiểm tra nội bộ bị vi phạm**, không phải một cách biểu diễn mọi lỗi nhập liệu hoặc lỗi kinh doanh thông thường.

**Tên `Error` không có nghĩa mọi `AssertionError` đều do JVM tự phát sinh.** Code có thể tự viết `throw new AssertionError("...");`, hoặc sử dụng câu lệnh `assert` để JVM thực hiện phép kiểm tra tùy trạng thái bật/tắt assertion.

## 2. Cú pháp của câu lệnh `assert`

Java có hai dạng:

~~~java
assert condition;
~~~

và:

~~~java
assert condition : detailExpression;
~~~

`condition` phải có kiểu `boolean` hoặc `Boolean` (nếu là `Boolean`, cần unboxing thành giá trị boolean khi đánh giá). Biểu thức `detailExpression` là một biểu thức không được có kiểu `void`; nó giúp tạo thông điệp chi tiết khi assertion thất bại.

Ví dụ:

~~~java
int size = 5;
assert size >= 0;
assert size < 100 : "size vượt giới hạn nội bộ: " + size;
~~~

Các dòng này là **mảnh mã Java** trong một phương thức hoặc block. Nếu assertions đã bật:

- Khi điều kiện đúng, Java tiếp tục, không ném lỗi.
- Khi điều kiện sai, Java ném `AssertionError`.
- Nếu có `: detailExpression` và điều kiện sai, Java tính biểu thức detail để xây `AssertionError`.

Để chạy trong một chương trình, bạn không phải import `assert` hoặc `AssertionError`; `assert` là từ khóa của ngôn ngữ, còn `AssertionError` thuộc `java.lang`.

### `assert` là statement, không phải method

`assert condition;` không trả về một giá trị để dùng như một biểu thức:

~~~java
boolean ok = assert (5 > 0); // KHÔNG BIÊN DỊCH.
~~~

Đây là phản ví dụ. `assert` là một câu lệnh, không phải phép gọi method kiểu `check(...)` và cũng không phải toán tử có giá trị trả về.

## 3. Cơ chế khi assertion được bật

Giả sử:

~~~java
int count = -1;
assert count >= 0 : "count must not be negative";
System.out.println("continue");
~~~

Nếu assertions bật cho class đang chạy, điều kiện `count >= 0` là `false`. Java tạo và ném `AssertionError` với thông điệp được tính. Dòng `System.out.println("continue")` **không chạy**, trừ khi có khối xử lý thích hợp làm thay đổi luồng điều khiển.

Luồng logic:

~~~text
Đến câu lệnh assert
          |
          v
Assertions được bật cho class?
     |                 |
    Không             Có
     |                 |
 Bỏ qua toàn bộ    Đánh giá condition
 assert                 |
                    +---+---+
                    |       |
                  true     false
                    |       |
                Tiếp tục  Nếu có: tính detail
                            |
                            v
                       throw AssertionError
~~~

Nếu detail chứa số hay object, constructor thích hợp của `AssertionError` tạo phần mô tả lỗi theo ngữ nghĩa của API. **Không nên coi cách format thông điệp tự động là một giao thức máy đọc ổn định.**

### Điều kiện `true` thì detail không được đánh giá

~~~java
assert 2 + 2 == 4 : expensiveDiagnostic();
~~~

Nếu assert bật và điều kiện đúng, `expensiveDiagnostic()` **không chạy**. Nếu assert tắt, cả điều kiện lẫn `expensiveDiagnostic()` đều không chạy. Chỉ khi assert bật **và** điều kiện sai thì biểu thức detail mới được đánh giá.

Đây là lý do các detail expression nên đơn giản, không thay đổi trạng thái chương trình và không ném lỗi phụ gây che mất nguyên nhân gốc.

## 4. Cơ chế khi assertion bị tắt

Với mặc định thông thường khi không bật assertions qua tham số JVM, câu lệnh:

~~~java
assert calculateCondition() : createDetail();
~~~

được **bỏ qua** về mặt đánh giá runtime:

- `calculateCondition()` không được gọi.
- `createDetail()` không được gọi.
- Không có `AssertionError` do chính câu lệnh assert này ném.
- Những lệnh xung quanh vẫn chạy bình thường.

Điều này dễ gây hiểu nhầm khi thử chạy code trong IDE: một IDE có thể cấu hình `-ea` cho unit tests nhưng không bật cho một ứng dụng chạy bình thường. Cùng source code, nếu run configuration khác, một assertion có thể được kiểm tra ở môi trường này nhưng bị bỏ qua ở môi trường khác.

**Đừng suy ra rằng không thấy `AssertionError` nghĩa là invariant đã được xác minh**; hãy kiểm tra assertions đã được bật hay chưa.

### Assert không phải cơ chế bảo mật

Phản ví dụ nguy hiểm:

~~~java
assert currentUser.isAdmin() : "Permission denied";
deleteAllRecords();
~~~

Đây là mảnh mã minh họa, không phải mẫu bảo mật. Khi assertions tắt, không có kiểm tra quyền, và lệnh xóa vẫn chạy. Quyền truy cập phải được kiểm tra bằng cơ chế bảo mật/authorization luôn hoạt động theo thiết kế, không phải bằng `assert`.

## 5. Bật và tắt assertions bằng tùy chọn JVM

Các tùy chọn thường dùng:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-ea` hoặc `-enableassertions` | Bật assertions cho các class không thuộc system classes theo phạm vi mặc định |
| `-da` hoặc `-disableassertions` | Tắt assertions theo phạm vi mặc định |
| `-ea:ten.lop` | Bật cho một class được nêu theo tên đủ điều kiện |
| `-ea:ten.package...` | Bật cho một package và các subpackage theo quy tắc tùy chọn |
| `-da:ten.lop` | Tắt cho một class cụ thể |
| `-esa` hoặc `-enablesystemassertions` | Bật assertions cho system classes |
| `-dsa` hoặc `-disablesystemassertions` | Tắt cho system classes |

Hai lệnh cho chương trình độc lập ở phần sau:

~~~bash
java -da AssertionLanguageDemo
java -ea AssertionLanguageDemo
~~~

Tham số `-ea`/`-da` phải được JVM nhận như **tùy chọn khởi chạy**, trước tên main class trong hai câu lệnh trên.

Dạng tên class/package bên dưới chỉ minh họa nếu các class tương ứng tồn tại trong classpath:

~~~bash
java -ea:com.example.orders.OrderService com.example.Main
java -ea:com.example.orders... com.example.Main
~~~

Đừng chép nguyên một package chưa tồn tại vào chương trình ví dụ chính và mong Java tự tạo class.

### Bật theo phạm vi không phải bật toàn bộ hệ thống một cách vô hạn

`-ea` không phải đồng nghĩa với “bật mọi assertion của mọi class trong toàn bộ JVM mà không ngoại lệ”. JVM có quy tắc riêng cho system classes và các tùy chọn `-esa`/`-dsa`. Khi chẩn đoán, cần biết class nào thực sự được bật.

Các môi trường build/test như Maven, Gradle hoặc IDE có thể truyền các JVM flags thông qua cấu hình runner. Chỉ nhìn câu lệnh `javac` là không đủ để biết assertions khi chạy có bật hay không.

## 6. `-ea` là tùy chọn runtime, không phải kiểm tra đặc biệt khi biên dịch

Biên dịch:

~~~bash
javac AssertionLanguageDemo.java
~~~

Chạy tắt/bật:

~~~bash
java -da AssertionLanguageDemo
java -ea AssertionLanguageDemo
~~~

**Không cần biên dịch hai lần.** Bytecode của cùng class có thể chạy với hai chế độ kiểm tra assertion khác nhau. Việc bật/tắt là lựa chọn của JVM/class loader khi class được khởi tạo theo quy tắc liên quan.

Đừng sửa cú pháp Java thành `assert enabled(...)` chỉ vì muốn bật assertions; `assert` là một từ khóa của ngôn ngữ, còn chính sách bật/tắt do JVM quản lý.

## 7. `Class.desiredAssertionStatus()` giúp kiểm tra cấu hình

Java cung cấp:

~~~java
System.out.println(MyClass.class.desiredAssertionStatus());
~~~

Trong mảnh này, `MyClass` là class giả định. Method `desiredAssertionStatus()` cho biết trạng thái assertion mong muốn cho class theo cài đặt class loader. Nó hữu ích để **chẩn đoán cấu hình** trong ví dụ đơn giản.

Tuy nhiên, không nên tự viết một hệ thống nghiệp vụ dựa vào việc liên tục gọi method đó thay vì dùng `assert` đúng cú pháp. Trong các trường hợp khởi tạo class phức tạp, trạng thái assertion còn liên quan đến quy tắc class loading/initialization; không dùng method này như một cơ chế tự động thay thế mọi kiểm tra runtime.

Trong chương trình độc lập sắp tới, một class bình thường khi chạy `-da` sẽ hiển thị `false`; khi chạy `-ea` cho class đó sẽ hiển thị `true`.

## 8. Không dùng `assert` cho điều kiện đầu vào public API

Ví dụ sai:

~~~java
static int dividePositive(int numerator, int denominator) {
    assert denominator > 0 : "denominator must be positive";
    return numerator / denominator;
}
~~~

Nếu assertions tắt, input `denominator = -2` vẫn lọt qua và phương thức trả một kết quả âm, trái với hợp đồng “denominator must be positive”. Với `denominator = 0`, toán tử `/` sẽ ném `ArithmeticException`, nhưng đó không đảm bảo mọi trường hợp vi phạm điều kiện đều bị phát hiện đúng loại.

Cách đúng cho một **tiền điều kiện bắt buộc**:

~~~java
static int dividePositive(int numerator, int denominator) {
    if (denominator <= 0) {
        throw new IllegalArgumentException(
                "denominator must be positive");
    }
    return numerator / denominator;
}
~~~

Điều kiện này **luôn được đánh giá** khi method chạy. Khi đầu vào sai, caller thấy `IllegalArgumentException` theo hợp đồng.

### Kiểm tra null cũng không dùng assert

Không nên:

~~~java
static String trimRequired(String input) {
    assert input != null;
    return input.trim();
}
~~~

Khi assertions tắt, `input == null` vẫn tiến tới `trim()` và gây `NullPointerException` ở vị trí sử dụng, thay vì kiểm tra rõ ràng tại ranh giới.

Nên:

~~~java
static String trimRequired(String input) {
    java.util.Objects.requireNonNull(input, "input");
    return input.trim();
}
~~~

Nếu input khác null nhưng có thể rỗng/blank, cần thêm `isBlank()` hoặc các quy tắc tương ứng. `requireNonNull` chỉ kiểm tra tham chiếu null, không kiểm tra mọi điều kiện đầu vào.

## 9. Khi nào nên dùng `assert`?

Các tình huống thường có giá trị:

1. **Bất biến nội bộ** vừa được thiết lập bởi code của chính module và cần kiểm tra trong môi trường debug/test.
2. **Hậu điều kiện** (*postcondition*) mà thuật toán hứa phải đúng nếu các bước trước chính xác.
3. **Quan hệ giữa biến nội bộ** mà logic đã bảo đảm, ví dụ chỉ số được tính phải nằm trong miền trước khi chuyển đến một API khác.
4. **Nhánh không được kỳ vọng tới** theo một phép chứng minh trên các trạng thái đã đóng, nhưng không thể dùng assert làm biện pháp an toàn duy nhất nếu việc tiếp tục sẽ gây hậu quả.
5. **Phát hiện lỗi lập trình khi bật debug assertions** mà không bắt buộc chạy tất cả phép kiểm tra tốn kém trong production.

Ví dụ sau minh họa hậu điều kiện đơn giản của thuật toán:

~~~java
static int clampToRange(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    int result = Math.min(max, Math.max(min, value));
    assert result >= min && result <= max
            : "clamp result is outside expected bounds";
    return result;
}
~~~

Đây là một phương thức Java hợp lệ. `min > max` là input sai và luôn bị từ chối; assertion kiểm tra **hậu điều kiện nội bộ** mà thuật toán vừa tính. Khi `-ea` được bật, nếu code có bug khiến hậu điều kiện sai, `AssertionError` giúp phát hiện.

### Nguyên tắc không thể bỏ qua

Một assertion đúng nghĩa nên có đặc tính:

> Nếu loại bỏ toàn bộ lệnh `assert`, chương trình vẫn thực hiện logic nghiệp vụ và giữ các tiền điều kiện/điều kiện an toàn cần thiết.

Nếu xóa `assert` mà chương trình bỏ qua validation, không tăng biến đếm, không ghi dữ liệu hoặc làm thay đổi kết quả chính, assertion đang bị dùng sai.

## 10. Side effect trong điều kiện assert là lỗi thiết kế

Mẫu nguy hiểm:

~~~java
int counter = 0;
assert ++counter > 0;
System.out.println(counter);
~~~

Nếu assertions bật, `counter` tăng thành `1`. Nếu assertions tắt, `counter` **vẫn là 0**. Cùng input nhưng trạng thái chương trình khác nhau.

Đoạn trên là phản ví dụ cố ý; chỉ dùng để chứng minh **đánh giá điều kiện phụ thuộc `-ea`**.

Cách tách side effect:

~~~java
int counter = 0;
counter++;
assert counter > 0;
System.out.println(counter);
~~~

Giờ phép tăng `counter++` luôn xảy ra, bất kể trạng thái assertions. Phần assert chỉ kiểm tra giả định.

### Side effect có thể ẩn trong method

~~~java
assert saveRecordAndReturnSuccess();
~~~

Nếu hàm `saveRecordAndReturnSuccess()` ghi dữ liệu, thì thao tác ghi chỉ chạy khi assertions bật. Đây là bug nghiêm trọng.

Nên:

~~~java
boolean saved = saveRecordAndReturnSuccess();
assert saved : "record was not saved";
~~~

Đây là mảnh minh họa có method giả định. Tuy nhiên, nếu việc lưu không thành công là một lỗi nghiệp vụ có thể dự kiến, phải xử lý `saved == false` **bằng logic thường hoặc exception hợp đồng**, không chỉ assert. Assert chỉ phù hợp nếu việc `saved == false` thật sự là một bất biến không thể xảy ra theo thiết kế.

## 11. Biểu thức detail cũng không nên có side effect

Phản ví dụ:

~~~java
assert balance >= 0 : chargePenaltyAndDescribe();
~~~

Nếu điều kiện đúng hoặc assert tắt, `chargePenaltyAndDescribe()` không chạy. Nếu assert bật và điều kiện sai, nó chạy **trong đường tạo lỗi**. Vậy việc thu phí lại phụ thuộc trạng thái assertions — điều không chấp nhận được.

Đúng hơn:

~~~java
assert balance >= 0
        : "negative internal balance=" + balance;
~~~

Message nên ngắn, dễ chẩn đoán và không chứa dữ liệu nhạy cảm. Với những biểu thức detail đắt, việc tính chúng chỉ khi thất bại có thể hữu ích, nhưng chúng **không được thực hiện các thay đổi trạng thái bắt buộc**.

### Detail expression không chạy nếu điều kiện true

~~~java
assert value != null : expensiveExplain(value);
~~~

Nếu `value != null` và assertion bật, Java **không gọi `expensiveExplain`**. Nhưng nếu điều kiện false, detail có thể tự ném một ngoại lệ khác. Khi đó ngoại lệ phát sinh trong lúc tính detail có thể truyền ra, thay vì một `AssertionError` như người đọc kỳ vọng.

Do đó, đừng đưa lời gọi phức tạp hoặc không an toàn vào expression sau dấu `:`.

## 12. `AssertionError` khác các exception runtime thông thường

Bảng phân biệt:

| Điều kiện | Cơ chế thường phù hợp | Tại sao? |
| --- | --- | --- |
| Tham số của public method bằng null nhưng không cho phép | `Objects.requireNonNull` → `NullPointerException` | Tiền điều kiện luôn được kiểm tra |
| Số lượng được truyền là số âm | `IllegalArgumentException` | Giá trị đối số không hợp lệ |
| Object hiện chưa ở trạng thái hoạt động | `IllegalStateException` | Trạng thái receiver không cho phép thao tác |
| Mất kết nối file/network | `IOException` hoặc exception tầng tương ứng | Lỗi hạ tầng cần được xử lý theo hợp đồng |
| Bất biến nội bộ lẽ ra không thể sai | `assert` để kiểm chứng khi bật | Phát hiện bug trong đường chạy/debug |
| Một lỗi thuật toán phải luôn ngăn việc tiếp tục ngay cả khi `-ea` tắt | `throw new IllegalStateException(...)` hoặc loại phù hợp | Không phụ thuộc cờ JVM |
| Kết quả nghiệp vụ `DECLINED` hợp lệ | Kết quả/enum/record | Không phải giả định nội bộ bị phá vỡ |

Điểm khác biệt lớn nhất là **câu lệnh `assert` có thể hoàn toàn không chạy**. Điều kiện hợp đồng nghiệp vụ bắt buộc không được đặt duy nhất ở nơi có thể bị loại bỏ như vậy.

### `AssertionError` không giống `IllegalStateException`

Hai loại đều có thể gợi ý trạng thái sai, nhưng:

- `IllegalStateException` là `RuntimeException`, nằm trong nhánh `Exception`, thích hợp cho lỗi trạng thái mà caller có thể nhận theo hợp đồng.
- `AssertionError` nằm dưới `Error`, chủ yếu báo giả định lập trình/invariant nội bộ bị phá vỡ.
- `catch (Exception)` bắt `IllegalStateException` nhưng **không** bắt `AssertionError`.
- `new AssertionError(...)` tự ném ra **không** bị điều khiển bởi `-ea`; chỉ **câu lệnh ngôn ngữ `assert`** mới được bật/tắt như vậy.

Không đổi một lỗi trạng thái bình thường thành `AssertionError` chỉ vì muốn báo lỗi “mạnh hơn”.

## 13. Câu lệnh `assert` và `throw new AssertionError`

Hai cách sau khác nhau:

~~~java
assert false : "internal invariant failed";
~~~

và:

~~~java
throw new AssertionError("internal invariant failed");
~~~

Với câu lệnh `assert`:

- Khi `-ea` tắt, Java bỏ qua câu lệnh.
- Khi `-ea` bật, nó ném `AssertionError` vì điều kiện false.

Với `throw new AssertionError(...)`:

- Lỗi **luôn được ném** nếu đường code đó được thực hiện, bất kể `-ea` hay `-da`.
- Không cần khai báo checked exception.
- Có thể hữu ích trong một số trường hợp chứng minh nhánh không thể tới, nhưng cần cân nhắc làm thế có đúng hợp đồng hay không.

### Dùng `assert false` cho nhánh “không thể xảy ra”?

~~~java
switch (status) {
    case "OPEN" -> processOpen();
    case "CLOSED" -> processClosed();
    default -> {
        assert false : "unexpected status: " + status;
    }
}
~~~

Đây là mảnh minh họa cần `status` và hai method phù hợp. Khi assertions tắt, nhánh `default` **không làm gì** ngoài việc hoàn tất block. Nếu trạng thái mới xuất hiện, chương trình có thể tiếp tục im lặng.

Nếu yêu cầu **luôn dừng** khi trạng thái không hỗ trợ:

~~~java
switch (status) {
    case "OPEN" -> processOpen();
    case "CLOSED" -> processClosed();
    default -> throw new IllegalStateException(
            "unexpected status: " + status);
}
~~~

Dạng này biểu đạt hợp đồng an toàn độc lập trạng thái assertions. Với enum và switch expression trên các phiên bản Java mới, còn có những quy tắc kiểm tra tính đầy đủ tại compile-time; không nên phụ thuộc vào `assert false` để thay thế toàn bộ thiết kế xử lý trạng thái.

## 14. Java 17+ — chương trình độc lập minh họa khi tắt và bật `assert`

Chương trình sau cho thấy:

- Khi assertions tắt, điều kiện và message của `assert` đều không chạy.
- Khi bật `-ea`, điều kiện `true` chạy nhưng message không chạy; điều kiện `false` làm `AssertionError` xuất hiện.
- Kiểm tra input bằng `Objects.requireNonNull` và `IllegalArgumentException` **luôn hoạt động** dù `-ea` tắt.
- `throw new AssertionError` hoạt động độc lập cờ assertion.
- Chương trình chỉ bắt `AssertionError` để quan sát trong ví dụ học tập, **không khuyến nghị bỏ qua Error trong production**.

Lưu thành tệp **`AssertionLanguageDemo.java`**:

~~~java
import java.util.Objects;

public class AssertionLanguageDemo {
    private static int conditionCalls;
    private static int detailCalls;

    public static void main(String[] args) {
        System.out.println("enabled="
                + AssertionLanguageDemo.class.desiredAssertionStatus());

        assert condition(true) : detail();
        System.out.println(
                "trueCheck conditionCalls=" + conditionCalls
                        + ", detailCalls=" + detailCalls);

        try {
            assert condition(false) : detail();
            System.out.println("falseCheck completed");
        } catch (AssertionError error) {
            System.out.println(
                    "falseCheck caught=" + error.getMessage());
        }
        System.out.println(
                "afterFalse conditionCalls=" + conditionCalls
                        + ", detailCalls=" + detailCalls);

        try {
            validateRequest(null, 2);
        } catch (NullPointerException error) {
            System.out.println(
                    "nullInput="
                            + error.getClass().getSimpleName()
                            + ":" + error.getMessage());
        }

        try {
            validateRequest("A-1", 0);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "badQuantity=" + error.getMessage());
        }

        try {
            throw new AssertionError("explicit failure");
        } catch (AssertionError error) {
            System.out.println(
                    "explicit=" + error.getMessage());
        }

        System.out.println("done");
    }

    static boolean condition(boolean result) {
        conditionCalls++;
        return result;
    }

    static String detail() {
        detailCalls++;
        return "invariant failed";
    }

    static void validateRequest(String orderId, int quantity) {
        Objects.requireNonNull(orderId, "orderId");

        if (orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}
~~~

Biên dịch:

~~~bash
javac AssertionLanguageDemo.java
~~~

### Chạy chế độ assertions tắt

~~~bash
java -da AssertionLanguageDemo
~~~

**Stdout chính xác trong chế độ `-da`:**

~~~text
enabled=false
trueCheck conditionCalls=0, detailCalls=0
falseCheck completed
afterFalse conditionCalls=0, detailCalls=0
nullInput=NullPointerException:orderId
badQuantity=quantity must be positive
explicit=explicit failure
done
~~~

**Giải thích:**

1. `-da` tắt assertions cho class, nên `desiredAssertionStatus()` trả `false`.
2. Cả hai điều kiện `condition(true)` và `condition(false)` **không được gọi**, biến `conditionCalls` giữ `0`.
3. `detail()` cũng không chạy, `detailCalls` giữ `0`.
4. Nhánh có điều kiện false **không ném** `AssertionError` do assert, nên in `falseCheck completed`.
5. Hai precondition `requireNonNull`/`quantity <= 0` vẫn được thực hiện và vẫn ném loại exception đúng.
6. Lệnh `throw new AssertionError("explicit failure")` vẫn ném Error, vì đó không phải câu lệnh `assert`.

### Chạy chế độ assertions bật

~~~bash
java -ea AssertionLanguageDemo
~~~

**Stdout chính xác trong chế độ `-ea`:**

~~~text
enabled=true
trueCheck conditionCalls=1, detailCalls=0
falseCheck caught=invariant failed
afterFalse conditionCalls=2, detailCalls=1
nullInput=NullPointerException:orderId
badQuantity=quantity must be positive
explicit=explicit failure
done
~~~

**Giải thích:**

1. `-ea` bật assertion cho class, nên `desiredAssertionStatus()` trả `true`.
2. Assert đầu gọi `condition(true)` và tăng counter thành `1`. Điều kiện đúng, `detail()` không được gọi.
3. Assert thứ hai gọi `condition(false)`, tăng counter thành `2`. Vì false, Java gọi `detail()` một lần rồi ném `AssertionError("invariant failed")`.
4. Handler `catch (AssertionError error)` chỉ dùng để minh họa nên in `falseCheck caught=invariant failed`.
5. Các phần validation vẫn cho cùng kết quả như chế độ `-da`.
6. Lệnh `throw new AssertionError` cho cùng kết quả ở cả hai chế độ.

### Vì sao chương trình có side effect trong `condition()`?

`condition()` tăng counter để **chứng minh thực nghiệm** rằng assert có thể không đánh giá biểu thức. Đây là một kỹ thuật demo được dùng có chủ ý, **không phải thiết kế nên làm trong code nghiệp vụ**. Logic ứng dụng thực phải đặt mọi side effect cần thiết ngoài câu lệnh `assert`.

### Có cần phụ thuộc thư viện test hay database không?

Không. Chương trình dùng JDK 17, `java.util.Objects` và lớp `java.lang.AssertionError` có sẵn. Chỉ cần tạo đúng một tệp Java, chạy `javac` rồi dùng hai lệnh `java` ở trên.

## 15. Tự ném `AssertionError` và constructor của nó

Java có những constructor như:

~~~java
new AssertionError()
new AssertionError("message")
new AssertionError(42)
new AssertionError(false)
new AssertionError((Object) someValue)
~~~

Đây là các mảnh tạo object minh họa với biến `someValue` phù hợp. `AssertionError` cung cấp overload cho nhiều kiểu primitive và `Object` để phục vụ biểu thức detail của `assert`.

Đặc biệt khi dùng constructor nhận `Object`:

~~~java
Throwable root =
        new IllegalStateException("source invariant failed");

AssertionError error =
        new AssertionError((Object) root);

System.out.println(error.getCause() == root);
// true
~~~

Constructor `AssertionError(Object detailMessage)` có quy tắc: nếu đối tượng detail là một `Throwable`, nó có thể được đặt làm **cause** của `AssertionError`. Đây là hành vi API riêng, không nên nhầm với mọi constructor của mọi lớp exception.

Nếu muốn một lỗi ứng dụng với message/cause theo hợp đồng thông thường, dùng subclass `Exception`/`RuntimeException` phù hợp thay vì mặc định chuyển tất cả thành `AssertionError`.

### `AssertionError` không thay thế logic xử lý checked exception

Giả sử code đọc tệp có thể ném `IOException`. Việc viết:

~~~java
try {
    loadConfiguration();
} catch (java.io.IOException cause) {
    throw new AssertionError(cause);
}
~~~

đây là một mảnh minh họa. Nó biến checked `IOException` thành `Error`, thường **không phù hợp** nếu cấu hình có thể thiếu hoặc kết nối có thể thất bại trong vận hành bình thường. Tầng gọi sẽ không nhận hợp đồng checked ban đầu và `catch(Exception)` cũng không bắt lỗi mới.

Nếu cần chuyển abstraction, nên cân nhắc custom `Exception` hoặc `RuntimeException` có constructor giữ cause, với lý do thiết kế rõ ràng. Chỉ dùng `AssertionError` nếu lỗi thực sự mô tả một giả định nội bộ bị vi phạm, không phải bất kỳ lỗi hạ tầng nào.

## 16. Assertion trong constructor và trạng thái đối tượng

Một constructor có thể dùng `assert` để kiểm tra một invariant nội bộ, nhưng không được dùng làm điều kiện duy nhất để chấp nhận dữ liệu của caller.

Sai:

~~~java
final class UserId {
    private final String value;

    UserId(String value) {
        assert value != null : "value must not be null";
        this.value = value;
    }
}
~~~

Khi assertions tắt, constructor cho phép tạo `UserId` với `value == null`, phá hợp đồng bất biến của đối tượng.

Nên:

~~~java
final class UserId {
    private final String value;

    UserId(String value) {
        java.util.Objects.requireNonNull(value, "value");
        if (value.isBlank()) {
            throw new IllegalArgumentException("value is blank");
        }
        this.value = value;
        assert !this.value.isBlank();
    }
}
~~~

Ở đây:

- Hai validation ban đầu **luôn chạy**, bảo vệ hợp đồng constructor.
- Assertion cuối chỉ là một phép kiểm tra bổ sung đối với invariant đã được thiết lập.
- Nếu assertions tắt, object vẫn không thể được tạo thành công bằng constructor này với null hoặc blank input.

Không phải constructor nào cũng cần thêm assert cuối. Nếu điều kiện đã được chứng minh bằng code đơn giản, có thể không thêm kiểm tra trùng lặp.

## 17. Assertion ở nhánh xử lý exception

Một lỗi thường gặp là cho rằng có thể dùng `assert false` làm mặc định cho mọi exception được bắt:

~~~java
try {
    doSomething();
} catch (java.io.IOException e) {
    assert false : e;
}
~~~

Đây là mảnh mã minh họa có `doSomething()`, không phải chương trình độc lập. Với `-da`, handler **bắt IOException rồi không làm gì**; luồng tiếp tục, khiến lỗi I/O bị nuốt hoàn toàn.

Nếu tầng này không biết phục hồi, thường nên:

~~~java
try {
    doSomething();
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "cannot complete the operation", cause);
}
~~~

Hoặc để checked `IOException` lan truyền bằng `throws IOException` theo hợp đồng. Khi bắt ngoại lệ, phải **xử lý, chuyển đổi có cause, hoặc ném tiếp** theo trách nhiệm của tầng — không dựa vào `assert false`.

## 18. `AssertionError` trong static initializer

Vì chủ đề nằm trong nhóm **Error và khởi tạo**, cần hiểu ảnh hưởng của assertion khi JVM đang khởi tạo một class.

Ví dụ:

~~~java
final class StaticInvariant {
    static final int SIZE = calculateSize();

    static {
        assert SIZE > 0 : "static size must be positive";
    }

    static int calculateSize() {
        return -1;
    }

    static int size() {
        return SIZE;
    }
}
~~~

Đây là một class Java hợp lệ. Hành vi phụ thuộc việc assertions được bật cho `StaticInvariant` khi class khởi tạo:

- **Assertions tắt:** khối `static` không kiểm tra `SIZE > 0`; class có thể khởi tạo thành công với `SIZE == -1`.
- **Assertions bật:** phép kiểm tra `SIZE > 0` sai và câu lệnh ném `AssertionError` trong lúc class initialization.
- `AssertionError` là subtype của `Error`. Theo cơ chế khởi tạo lớp, một lỗi thoát ra đã thuộc `Error` có thể được truyền trực tiếp cho lần thất bại đầu tiên, **không bắt buộc bọc thành `ExceptionInInitializerError`**.
- Sau khi quá trình khởi tạo class thất bại, định nghĩa class có thể bị đánh dấu **erroneous**; các lần active use tiếp theo thường nhận `NoClassDefFoundError` trong cùng class loader thay vì tự chạy lại static initializer.

Đây là lý do không nên xem assertion như biện pháp duy nhất để bảo vệ một **trạng thái tĩnh cần thiết cho vận hành**.

### Nếu bắt buộc không chấp nhận giá trị sai dù `-da`?

Thay assertion bằng kiểm tra luôn chạy:

~~~java
final class StaticValidated {
    static final int SIZE = calculateSize();

    static {
        if (SIZE <= 0) {
            throw new IllegalStateException(
                    "static size must be positive");
        }
    }

    static int calculateSize() {
        return -1;
    }
}
~~~

Đoạn này là một class minh họa được biên dịch hợp lệ (static block vẫn có khả năng hoàn tất bình thường theo phân tích compiler). Khi initializer ném `IllegalStateException` — một `RuntimeException`, không phải `Error` — JVM thường bọc thất bại khởi tạo thành `ExceptionInInitializerError`.

**Cả hai hướng vẫn có thể làm class erroneous.** Nếu lỗi là điều kiện vận hành có thể phục hồi (ví dụ đọc cấu hình hoặc kết nối mạng), thường tốt hơn chuyển công việc sang **factory/loader** có hợp đồng checked/unchecked và retry rõ ràng, không làm thất bại class initialization.

## 19. Assertion trong static initializer và thời điểm bật trạng thái

JVM quản lý việc bật/tắt assertion theo class loader và trạng thái áp dụng khi class khởi tạo. Vì thế, việc dùng câu lệnh `assert` trong quá trình khởi tạo class có sắc thái riêng.

Các quy tắc đặc biệt về việc class được sử dụng **trong khi chính class còn đang khởi tạo** không nên được giản lược thành “mọi assert luôn tuân theo một boolean tự viết ở đầu chương trình”. Với code thông thường, hãy dùng `-ea`/`-da` rõ ràng khi khởi chạy và tránh xây logic khởi tạo phụ thuộc vào khả năng bật assertions.

Điều cần nhớ trong thực hành:

1. `assert` là phép kiểm tra có thể bỏ qua; không thay thế validation bắt buộc.
2. Một `AssertionError` thoát ra trong class initialization có thể làm class không sử dụng được ở các lần active use tiếp theo.
3. Chuyển thao tác dễ thất bại sang phương thức bình thường/instance factory giúp hệ thống có đường phục hồi rõ ràng hơn.

## 20. `catch (Exception)`, `catch (Error)` và `catch (Throwable)`

Đoạn sau minh họa **kiểu bắt**, không phải lời khuyên production:

~~~java
try {
    throw new AssertionError("internal bug");
} catch (Exception e) {
    System.out.println("Exception branch");
} catch (AssertionError e) {
    System.out.println("AssertionError branch");
}
~~~

Kết quả:

~~~text
AssertionError branch
~~~

`catch(Exception)` không bắt subtype của `Error`. Đây không phải là lý do để mọi service đổi sang `catch(Throwable)`.

### Vì sao không nên bắt rồi bỏ qua `AssertionError`?

Một assertion thất bại thường nói rằng **một giả định trong code sai**. Nếu code bắt nó rồi tiếp tục như không có vấn đề:

- Trạng thái object có thể không còn như thuật toán mong đợi.
- Các bước tiếp theo có thể sinh dữ liệu sai khó nhận diện.
- Debugging mất điểm báo lỗi đầu tiên.
- Nếu assertion nằm trong quá trình khởi tạo, class có thể đã ở trạng thái khởi tạo thất bại.

Trong test runner hoặc một số framework cấp thấp, handler có thể bắt `AssertionError` để **ghi nhận một kết quả test thất bại**, nhưng đó là trách nhiệm chuyên biệt.

Nếu buộc phải ghi log rồi chuyển lỗi tiếp, cần chính sách rất rõ; **đừng viết `catch(Throwable)` để biến mọi `Error` thành kết quả kinh doanh bình thường**.

## 21. `assert` của Java khác assertion của JUnit

Hai thứ thường có tên giống nhau nhưng cơ chế khác nhau:

**Java language assertion:**

~~~java
assert actual == expected : "values differ";
~~~

**JUnit 5 assertion:**

~~~java
org.junit.jupiter.api.Assertions.assertEquals(expected, actual);
~~~

Đoạn JUnit là **mảnh minh họa cần phụ thuộc JUnit 5**, không nằm trong chương trình standalone Java 17 phía trên.

Các điểm khác biệt:

| Tiêu chí | Java `assert` | JUnit 5 `assertEquals` |
| --- | --- | --- |
| Là gì? | Câu lệnh ngôn ngữ | Method của framework kiểm thử |
| Có cần thư viện ngoài JDK? | Không | Có |
| Phụ thuộc `-ea` để chạy phép kiểm tra? | **Có** | **Không**, method được gọi như code thường |
| Khi không thỏa? | `AssertionError` nếu assert bật | Framework ném lỗi kiểm thử, thường subtype `AssertionError` |
| Vai trò chính | Kiểm tra invariant nội bộ khi bật | Khẳng định kết quả mong đợi của một test |
| Khi assertions tắt | Bỏ qua cả condition/detail | Method test vẫn được thực thi |

Để kiểm thử kết quả một chức năng, thường nên dùng công cụ assertion của framework, ví dụ `assertEquals`, `assertThrows`, thay vì để toàn bộ test phụ thuộc tình trạng `-ea`.

### `AssertionError` trong test runner có ý nghĩa gì?

Test framework có thể dùng `AssertionError` hoặc subclass của nó để báo một test thất bại; runner bắt, ghi nhận và tiếp tục chạy test khác. Đây là **cơ chế chuyên biệt có chủ đích**, không phải tiền lệ cho ứng dụng nghiệp vụ bắt mọi `AssertionError` rồi tiếp tục.

## 22. Những nhầm lẫn phổ biến

### Sai lầm 1 — Tưởng `assert` luôn chạy

Không. Trong các lần chạy JVM thông thường, assertion có thể bị tắt. Cần bật `-ea` khi muốn kiểm tra.

### Sai lầm 2 — Dùng `assert` để kiểm tra input từ người dùng

Input có thể không hợp lệ theo thiết kế; cần validation luôn hoạt động với `IllegalArgumentException`, `NullPointerException` hoặc kết quả có cấu trúc.

### Sai lầm 3 — Cho rằng `catch (Exception)` bắt được `AssertionError`

Không. `AssertionError extends Error`, không phải `Exception`.

### Sai lầm 4 — Cho rằng `AssertionError` là checked exception

Không. Mọi subtype của `Error` là unchecked; không phải khai báo `throws`.

### Sai lầm 5 — Tưởng `throw new AssertionError` cũng bị tắt theo `-da`

Không. Tùy chọn assertions chỉ ảnh hưởng **câu lệnh `assert`**, không tự bỏ qua các lệnh `throw` viết trực tiếp.

### Sai lầm 6 — Đưa cập nhật biến đếm vào condition của assert

Khi assert tắt, cập nhật bị bỏ qua. Side effect phải nằm ở câu lệnh bình thường.

### Sai lầm 7 — Đưa thao tác mạng/ghi dữ liệu vào detail expression

Detail chỉ chạy khi assert bật và condition false, không thể làm đường xử lý nghiệp vụ bắt buộc.

### Sai lầm 8 — Dùng `assert false` để xử lý IOException

Với `-da`, code trong catch có thể không làm gì và vô tình nuốt ngoại lệ.

### Sai lầm 9 — Tưởng `assert false` luôn ngăn đi tiếp

Không nếu assertion tắt. Nếu phải luôn dừng, ném một exception/Error phù hợp theo thiết kế.

### Sai lầm 10 — Coi AssertionError là lỗi nghiêm trọng nhất nên dùng cho mọi failure

Mức độ thiệt hại nghiệp vụ không quyết định kế thừa `Error`. Một lỗi kết nối nghiêm trọng vẫn có thể cần `IOException` hoặc custom `Exception`.

### Sai lầm 11 — Dùng assert thay cho authorization

Bảo mật phải được kiểm tra độc lập trạng thái `-ea`/`-da`.

### Sai lầm 12 — Cho rằng mọi lỗi trong static block luôn bị bọc thành `ExceptionInInitializerError`

Nếu lỗi đã thuộc `Error`, JVM có thể truyền trực tiếp đối tượng đó ở lần khởi tạo thất bại đầu. `AssertionError` thuộc nhóm này.

### Sai lầm 13 — Nghĩ class tự khởi tạo lại sau `AssertionError` ở static block

Không. Một class initialization thất bại có thể khiến định nghĩa class erroneous; lần active use sau thường gặp `NoClassDefFoundError`.

### Sai lầm 14 — Tưởng JUnit `assertEquals` phụ thuộc `-ea`

Không. Đó là lời gọi method của framework, được chạy theo logic kiểm thử bình thường.

### Sai lầm 15 — Cho rằng biểu thức detail luôn được đánh giá

Không. Nó chỉ được đánh giá nếu assertion bật và condition false.

### Sai lầm 16 — Dùng `assert obj != null` rồi dereference `obj`

Khi assert tắt, null vẫn còn và việc dereference có thể ném NPE sâu hơn trong logic, không tạo một hợp đồng rõ ràng.

### Sai lầm 17 — Bắt `AssertionError` rồi dùng fallback mặc định

Nếu một invariant nội bộ sai, fallback có thể che bug và gây sai dữ liệu. Cần xác định mức độ phục hồi thật sự trước khi tiếp tục.

### Sai lầm 18 — Dùng assert để kiểm tra quy tắc giao dịch bất biến

Kiểm tra số dư/giới hạn/bảo mật phải luôn chạy và thường cần cơ chế đồng bộ/transaction; `assert` không giải quyết tính nhất quán của transaction.

### Sai lầm 19 — Coi message của AssertionError là mã lỗi máy

Message chủ yếu dành cho con người, có thể thay đổi. Dùng exception type hoặc error code riêng khi cần phân nhánh tự động.

### Sai lầm 20 — Đặt assert thay cho phép kiểm tra tính hợp lệ của dữ liệu cấu hình

Cấu hình là dữ liệu đầu vào từ môi trường và có thể sai. Hãy báo exception có ngữ nghĩa và đường phục hồi/khởi động lại rõ ràng, không phụ thuộc cờ assertions.

## 23. Checklist sử dụng `assert` đúng mục đích

Trước khi thêm một câu lệnh `assert`, hãy trả lời:

1. **Đây có phải một invariant nội bộ** mà logic trước đó đã có trách nhiệm bảo đảm không?
2. **Nếu assert bị tắt, code còn đúng và an toàn không?** Nếu không, hãy dùng `if`/`throw`.
3. **Condition có side effect không?** Không được dùng kết quả của condition để thay đổi trạng thái bắt buộc.
4. **Detail expression có side effect không?** Không nên.
5. **Dữ liệu đến từ public API/HTTP/file/database không?** Nếu có, validation phải luôn chạy.
6. **Có một exception hợp đồng phù hợp hơn không?** NPE/IAE/ISE/IOException thường rõ hơn với lỗi có thể dự kiến.
7. **Có cần thu thập lỗi người dùng để trả nhiều thông báo không?** Dùng cơ chế validation kết quả, không rely on assert.
8. **Môi trường test có bật `-ea` không?** Kiểm tra run configuration nếu bạn muốn assertion được thực thi.
9. **Có nên dùng JUnit assertions để kiểm thử kết quả không?** Thường có.
10. **Nếu assertion sai, chương trình có nên dừng thao tác không?** Đừng bắt và bỏ qua nếu chưa có chính sách chuyên biệt.
11. **Assertion có nằm trong static initializer không?** Có thể làm class không khởi tạo được khi bật.
12. **Thông điệp có chứa dữ liệu nhạy cảm không?** Không đưa token/secret hoặc toàn bộ dữ liệu người dùng vào message.

Một cách tự kiểm rất tốt: **tưởng tượng xóa hết `assert` khỏi source**. Nếu ứng dụng vẫn đáp ứng hợp đồng, chính sách an toàn và thứ tự side effect, bạn đang dùng assertion gần đúng mục đích.

## 24. Câu hỏi tự kiểm tra

1. `AssertionError` thuộc nhánh `Exception` hay `Error`?
2. Nó là checked hay unchecked? Có bắt buộc khai báo `throws` không?
3. Hai cú pháp của câu lệnh `assert` là gì?
4. `condition` trong assert phải có loại giá trị nào?
5. Khi assertions tắt, condition có được đánh giá không?
6. Khi assertions tắt, detail expression có được đánh giá không?
7. Khi assertions bật và condition true, detail expression có chạy không?
8. Khi assertions bật và condition false, chương trình ném gì?
9. `-ea` dùng để làm gì?
10. `-da` dùng để làm gì?
11. Có cần biên dịch lại class để đổi trạng thái assertions không?
12. `java -ea AssertionLanguageDemo` và `java -da AssertionLanguageDemo` có thể cho stdout khác nhau không?
13. Vì sao không được dùng `assert quantity > 0` làm validation duy nhất của public method?
14. `Objects.requireNonNull` khác `assert obj != null` ở điểm nào quan trọng nhất?
15. Có nên đặt `counter++` vào điều kiện assert không?
16. Nếu detail function ghi dữ liệu, có rủi ro gì?
17. `catch(Exception)` có bắt `AssertionError` không?
18. `throw new AssertionError("x")` có bị vô hiệu hóa bởi `-da` không?
19. Khi nào `assert` phù hợp cho hậu điều kiện của thuật toán?
20. Nếu code có `assert false` trong nhánh default, khi assertions tắt điều gì xảy ra?
21. Một `AssertionError` trong static initializer có thể được JVM ném trực tiếp ở lần khởi tạo thất bại đầu không?
22. Lần sử dụng sau một class đã khởi tạo thất bại thường gặp loại lỗi gì?
23. Vì sao không được dùng `assert` để kiểm tra quyền admin?
24. `AssertionError(Object detailMessage)` có quan hệ cause đặc biệt nào khi detail là `Throwable`?
25. JUnit 5 `assertEquals` có cần `-ea` không?
26. Vì sao không nên bắt và bỏ qua mọi `AssertionError` trong service?
27. Kiểm thử code ứng dụng nên dựa vào `assert` ngôn ngữ hay assertions của test framework khi có sẵn?
28. Nếu một method trong điều kiện assert ném exception khác, có bảo đảm luôn thu được `AssertionError` không?
29. Những thông điệp tạo bằng detail nên chứa dữ liệu gì?
30. Quy tắc một câu để quyết định có dùng `assert` hay không là gì?

### Đáp án gợi ý

1. Nhánh `Error`.
2. Unchecked; không cần khai báo `throws`.
3. `assert condition;` và `assert condition : detail;`.
4. `boolean` hoặc `Boolean` (có thể unbox khi đánh giá).
5. Không.
6. Không.
7. Không.
8. `AssertionError`, trừ khi quá trình đánh giá condition/detail tự ném lỗi trước đó.
9. Bật assertions trong phạm vi tương ứng.
10. Tắt assertions trong phạm vi tương ứng.
11. Không; cờ nằm ở runtime.
12. Có; điều kiện và detail có thể được bỏ qua khi disabled.
13. Tiền điều kiện input phải luôn được kiểm tra.
14. `requireNonNull` luôn chạy khi được gọi; `assert` có thể bị bỏ qua.
15. Không; side effect sẽ phụ thuộc `-ea`.
16. Chỉ chạy trên đường assertion thất bại; gây thay đổi trạng thái bất ngờ.
17. Không.
18. Không; lệnh `throw` vẫn chạy bình thường.
19. Khi đó là invariant nội bộ đã được thuật toán bảo đảm, chỉ cần kiểm chứng khi bật.
20. Nhánh đó có thể hoàn tất mà không ném lỗi.
21. Có; `AssertionError extends Error`.
22. Thường là `NoClassDefFoundError`.
23. Assertion có thể tắt; authorization phải luôn chạy.
24. Nếu detail là Throwable, constructor dạng `Object` có thể dùng nó làm cause.
25. Không.
26. Có thể che bug và khiến ứng dụng tiếp tục với invariant bị vi phạm.
27. Thường dùng assertions của framework để diễn đạt kết quả test.
28. Không; ngoại lệ phát sinh trong expression có thể lan truyền.
29. Mô tả invariant, ngữ cảnh kỹ thuật hữu ích, không chứa secret.
30. Nếu bỏ qua assertion mà chương trình **không còn đúng hoặc an toàn**, đừng dùng `assert` làm biện pháp duy nhất.

## 25. Tổng kết

**`assert` là công cụ kiểm tra giả định nội bộ có thể bật/tắt, còn `AssertionError` là một `Error` unchecked được ném khi assertion bật và điều kiện sai.** Không dùng `assert` để thay thế tiền điều kiện public API, bảo mật, kiểm tra dữ liệu bên ngoài hay các side effect bắt buộc, vì toàn bộ biểu thức assert có thể không được đánh giá. Dùng `-ea` khi muốn kiểm chứng invariant trong phát triển/test; dùng exception phù hợp như `IllegalArgumentException`, `NullPointerException` hoặc `IllegalStateException` cho hợp đồng luôn có hiệu lực.

Nếu `AssertionError` thoát khỏi static initializer, class initialization có thể thất bại và làm class không sử dụng được cho các lần active use sau. Cuối cùng, phân biệt rõ Java language assertion với các assertion method của test framework: **JUnit kiểm thử theo lời gọi method, không phụ thuộc vào việc bật `-ea` cho câu lệnh `assert`**.

### Tham khảo chuẩn Java 17

- Java Language Specification, `assert` statement: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.10
- `java.lang.AssertionError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AssertionError.html
- `java.lang.Class.desiredAssertionStatus()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#desiredAssertionStatus()
- `java` launcher, các tùy chọn assertion: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
