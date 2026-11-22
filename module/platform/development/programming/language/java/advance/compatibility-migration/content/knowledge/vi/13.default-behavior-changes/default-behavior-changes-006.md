# Kiểm tra đối số, loại ngoại lệ và thông báo lỗi có thể thay đổi

Trong quá trình **Java Advance Compatibility Migration**, nhiều thay đổi không làm hỏng quá trình biên dịch nhưng vẫn làm thay đổi cách chương trình xử lý đầu vào sai. Một phương thức trước đây chấp nhận giá trị **null**, chỉ kiểm tra giới hạn khi sử dụng dữ liệu hoặc trả về một ngoại lệ cụ thể, có thể chuyển sang kiểm tra sớm hơn, ném ngoại lệ khác hoặc tạo thông báo lỗi khác sau khi nâng JDK, framework hay dependency.

Đây là phần của chương **Hành vi mặc định**. Để migration an toàn, cần xem **kiểm tra đối số (argument validation)**, **loại ngoại lệ (exception type)** và **thông báo lỗi (error message)** như ba chiều hành vi có liên quan nhưng không giống nhau. Nếu hệ thống có consumer hoặc đối tác đang dựa vào một trong các chiều này, thay đổi dù chỉ ở một nhánh lỗi cũng có thể tác động đến tính tương thích.

Ví dụ:

- API cũ chấp nhận chuỗi rỗng rồi trả kết quả mặc định; API mới ném **IllegalArgumentException**.
- Code cũ ném **NullPointerException** khi dereference về sau; code mới dùng **Objects.requireNonNull** và ném lỗi ngay tại đầu phương thức.
- Một thư viện đổi **NumberFormatException** thành ngoại lệ miền nghiệp vụ hoặc ngược lại.
- JVM mới cung cấp thông báo **NullPointerException** chi tiết hơn, khiến test so sánh nguyên văn thông báo bị thất bại.
- Thứ tự validation đổi từ kiểm tra trạng thái sang kiểm tra đối số, nên cùng một lời gọi sai có thể nhận ngoại lệ khác.
- Framework thay đổi cách ánh xạ ngoại lệ thành HTTP status, error code hoặc response body.

Bài học tập trung vào cách nhận diện, thiết kế và kiểm thử những thay đổi này mà không nhầm lẫn tương thích nhị phân với tương thích hành vi.

## 1. Hợp đồng lỗi là một phần của hành vi API

Một API không chỉ có hợp đồng cho input hợp lệ. Nó còn có hành vi khi input không hợp lệ, tài nguyên thiếu hoặc hệ thống ở trạng thái không cho phép thao tác.

Xét phương thức:

~~~java
public Money transfer(String accountId, long amount);
~~~

Đối với input hợp lệ, consumer quan tâm kết quả chuyển tiền. Với input sai, consumer có thể quan tâm:

- **accountId = null** được hiểu là tài khoản mặc định hay bị từ chối?
- **accountId = ""** có được chấp nhận không?
- **amount = 0** là hợp lệ hay lỗi?
- **amount < 0** gây ngoại lệ nào?
- Có kiểm tra đối số trước khi truy cập database không?
- Ngoại lệ có chứa mã lỗi ổn định để consumer phân nhánh không?
- Trong trường hợp có nhiều lỗi đầu vào, lỗi nào được trả trước?
- Ngoại lệ có bị bọc bởi một lớp khác tại boundary không?
- Có thông tin nhạy cảm trong message hoặc log không?

Một consumer có thể bắt ngoại lệ cụ thể:

~~~java
try {
    transferService.transfer(accountId, amount);
} catch (IllegalArgumentException ex) {
    showInputError();
}
~~~

Nếu phiên bản mới chuyển sang **IllegalStateException** cho cùng điều kiện, source consumer vẫn compile và bytecode vẫn link được; nhưng nhánh **catch** không còn hoạt động theo mong đợi.

**Tương thích source/binary không bảo đảm tương thích hành vi trong nhánh lỗi.**

### 1.1. Phân loại các chiều cần khảo sát

| Chiều | Câu hỏi | Ví dụ thay đổi |
|---|---|---|
| Input domain | Tập đối số được chấp nhận có đổi không? | Không còn cho phép null |
| Validation timing | Kiểm tra ở thời điểm nào? | Ném lỗi ngay khi gọi, thay vì lúc xử lý |
| Validation precedence | Nếu nhiều đối số sai, lỗi nào được ưu tiên? | Kiểm tra index trước payload |
| Exception class | Loại ngoại lệ có thay đổi không? | IllegalArgumentException sang NullPointerException |
| Exception hierarchy | Consumer bắt theo superclass hay subtype? | RuntimeException chuyên biệt được thêm vào |
| Exception wrapping | Có lớp ngoại lệ bọc bên ngoài không? | CompletionException bao lỗi gốc |
| Message | Nội dung, cấu trúc, locale có đổi không? | Thông báo có thêm tên biến |
| Cause and suppressed | Chuỗi cause có khác không? | Lỗi I/O được giữ làm cause |
| Side effects | Đã có tác dụng phụ trước khi ném lỗi chưa? | Ghi log/event trước validation |
| Public error representation | HTTP/gRPC/message error có đổi không? | HTTP 400 sang 422, code JSON đổi |

Phân loại này giúp nhóm không sửa một lỗi message bằng cách thay đổi loại exception khi chưa hiểu hợp đồng consumer.

## 2. Tại sao nâng Java có thể làm thay đổi validation?

Thay đổi có thể xuất hiện ở nhiều lớp:

1. **JDK:** API chuẩn sửa thuật toán kiểm tra hoặc cải thiện diagnostics; hành vi cụ thể phụ thuộc đặc tả và release.
2. **Thư viện:** dependency cập nhật logic guard, parser, mapper hoặc wrapper.
3. **Framework:** binding, conversion, bean validation hoặc exception resolver thay đổi.
4. **Ứng dụng:** refactor làm thay đổi thứ tự kiểm tra và ngoại lệ được ném.
5. **Runtime/configuration:** locale, charset, timezone, provider hoặc JVM flags làm thay đổi biểu diễn lỗi.
6. **Môi trường triển khai:** proxy, classloader, driver và serialization layer thay đổi cách propagate exception.
7. **Mã sinh tự động:** code generator, annotation processor hoặc bytecode enhancement có thể đưa vào validation khác với bản trước.

Khi một test đang báo thông báo khác đi sau migration, không nên tự động kết luận đó là thay đổi của Java. Cần xác định **lớp thực sự ném ngoại lệ** và phiên bản artifact tương ứng.

### 2.1. Kiểm tra đặc tả trước khi suy đoán

Mỗi API có thể công bố một số ngoại lệ trong Javadoc. Ví dụ, các phương thức factory bất biến như **List.of(...)** từ chối phần tử null; những hành vi này cần được xác nhận từ contract của API.

Tuy nhiên, **chuỗi message chính xác** thường không được cam kết là API ổn định, kể cả khi loại ngoại lệ được mô tả. Không được biến một message xuất hiện trong test của JDK hiện tại thành hợp đồng lâu dài nếu không có tài liệu công bố rõ.

Khi đánh giá thay đổi, hãy phân biệt:

- **Specified behavior:** được Javadoc hoặc hợp đồng công khai quy định.
- **Documented framework behavior:** được nhà cung cấp mô tả cho một phiên bản cụ thể.
- **Observed behavior:** được thấy trong log/test nhưng có thể là chi tiết triển khai.
- **Application-owned contract:** do chính nhóm phát hành và có thể kiểm soát.

## 3. Các ngoại lệ Java phổ biến liên quan đến đối số

Một số ngoại lệ thường xuất hiện khi xử lý đối số sai:

| Ngoại lệ | Ý nghĩa điển hình | Ví dụ |
|---|---|---|
| **IllegalArgumentException** | Giá trị đối số không hợp lệ đối với phương thức | amount âm khi nghiệp vụ cấm |
| **NullPointerException** | Yêu cầu tham chiếu không null bị vi phạm hoặc dereference null | Objects.requireNonNull |
| **IndexOutOfBoundsException** | Index hoặc range nằm ngoài giới hạn | Objects.checkIndex |
| **NumberFormatException** | Chuỗi không chuyển được thành dạng số mong đợi | Integer.parseInt |
| **IllegalStateException** | Trạng thái của đối tượng không cho phép thao tác hiện tại | Thao tác sau khi close |
| **UnsupportedOperationException** | Thao tác không được hỗ trợ bởi implementation | Gọi add trên collection bất biến |
| **ClassCastException** | Cast thực tế không phù hợp với kiểu | Ép kiểu sai tại runtime |
| **DateTimeParseException** | Không parse được chuỗi ngày giờ theo formatter | LocalDate.parse |
| **PatternSyntaxException** | Biểu thức chính quy không hợp lệ | Pattern.compile |
| **SecurityException** | Chính sách bảo mật từ chối thao tác | Truy cập bị chặn trong một số API |
| **IOException** | Sự cố I/O, có thể được wrap ở lớp cao hơn | Đọc từ stream |
| **CompletionException** | Bao ngoại lệ trong xử lý bất đồng bộ | CompletableFuture.join |

**NumberFormatException** kế thừa **IllegalArgumentException**, còn **DateTimeParseException** cũng thuộc một nhánh ngoại lệ runtime chuyên biệt. Nhóm cần quan tâm đến cây kế thừa nếu consumer bắt bằng superclass.

### 3.1. Loại ngoại lệ không chỉ thể hiện mức nghiêm trọng

Đôi khi hai ngoại lệ cùng là **RuntimeException** nhưng có ngữ nghĩa khác nhau:

- **IllegalArgumentException:** caller cung cấp giá trị không hợp lệ.
- **IllegalStateException:** object/service đang ở trạng thái không cho phép.
- **NullPointerException:** tham chiếu bắt buộc không được phép null.
- **IndexOutOfBoundsException:** giá trị index/range không thuộc miền chỉ số hợp lệ.

Đổi loại exception có thể làm thay đổi cách client phân loại lỗi, retry, báo cáo hoặc chuyển lỗi thành HTTP status. Vì vậy, không nên thay **NullPointerException** bằng **IllegalStateException** chỉ vì cả hai đều là unchecked exception.

### 3.2. Thông điệp từ API chuẩn

Ví dụ minh họa các trường hợp input sai:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class InvalidArgumentsDemo {
    public static void main(String[] args) {
        // NullPointerException: List.of cấm phần tử null.
        List.of("A", null);

        // IllegalArgumentException: Map.of cấm key trùng nhau.
        // Map.of("k", 1, "k", 2);

        // IndexOutOfBoundsException cho index ngoài giới hạn.
        // Objects.checkIndex(10, 3);

        // NumberFormatException nếu chuỗi không là số nguyên hợp lệ.
        // Integer.parseInt("12x");
    }
}
~~~

Các dòng được comment là ví dụ độc lập để thử từng trường hợp, tránh việc ví dụ dừng ngay ở lỗi đầu tiên. Không nên viết unit test bắt buộc các ví dụ này luôn chứa cùng một message tiếng Anh.

## 4. Kiểm tra null: hành vi tường minh và ngầm định

### 4.1. NullPointerException do dereference

~~~java
public String normalize(String input) {
    return input.trim();
}
~~~

Nếu **input == null**, lỗi xảy ra khi gọi **trim()**. Thông báo của NPE phụ thuộc runtime và có thể thay đổi khi nâng JDK.

### 4.2. NullPointerException do requireNonNull

~~~java
import java.util.Objects;

public String normalize(String input) {
    Objects.requireNonNull(input, "input must not be null");
    return input.trim();
}
~~~

Trong trường hợp này, API chủ động kiểm tra và cung cấp message do ứng dụng sở hữu. Điều này có các ưu điểm:

- Lỗi xuất hiện ngay tại entry point.
- Có thể diễn đạt điều kiện vi phạm rõ ràng.
- Ít phụ thuộc vào dạng thông báo NPE tự động của JVM.
- Hỗ trợ test contract chính xác hơn nếu ứng dụng công bố message.

Nhưng chuyển từ dereference ngầm định sang validation tường minh có thể thay đổi **vị trí lỗi**, **stack trace** và thứ tự so với các thao tác khác. Nếu consumer phụ thuộc vào những yếu tố này, cần kiểm tra tương thích.

### 4.3. Chọn NPE hay IllegalArgumentException cho null?

Java cho phép ứng dụng thiết kế hợp đồng riêng. **Objects.requireNonNull** sử dụng **NullPointerException**. Một số API nghiệp vụ chọn **IllegalArgumentException** để biểu diễn mọi đối số không hợp lệ, kể cả null.

Không có lợi ích khi áp dụng hai cách lẫn lộn rồi thay đổi mỗi lần refactor. Hãy đặt quy ước cho public API, ghi trong Javadoc và kiểm thử.

Ví dụ dùng ngoại lệ riêng:

~~~java
public final class RegistrationService {
    public String register(String email) {
        if (email == null) {
            throw new IllegalArgumentException("email is required");
        }
        if (email.isBlank()) {
            throw new IllegalArgumentException("email must not be blank");
        }
        return email.strip();
    }
}
~~~

Nếu hợp đồng v1 công bố **IllegalArgumentException** khi email null, thay sang **NullPointerException** trong v2 có thể phá vỡ các consumer đang bắt ngoại lệ cụ thể. Sự lựa chọn cần xét lịch sử API và chính sách tương thích, không chỉ phong cách code.

### 4.4. Null và collection factory

Những API như **List.of(...)**, **Set.of(...)** và **Map.of(...)** không cho phép null. Chuyển từ **ArrayList** có thể chứa null sang **List.of** không chỉ thay đổi mutability mà còn thay đổi input domain.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> mutable = new ArrayList<>();
mutable.add(null);             // Có thể chứa null.

List<String> immutable = List.of("A");
// immutable.add("B");         // UnsupportedOperationException.
// List.of("A", null);         // NullPointerException.
~~~

Nếu một migration thay cách tạo collection vì muốn tối ưu bộ nhớ hoặc dùng API Java mới, cần kiểm tra dữ liệu thực tế có null hay không. Test chỉ kiểm tra collection với phần tử hợp lệ không phát hiện thay đổi này.

## 5. Validation miền số, index và range

### 5.1. Kiểm tra số âm, zero và overflow

Một API xử lý số cần xác định:

- Có chấp nhận giá trị âm không?
- Zero là trường hợp hợp lệ hay sentinel?
- Giá trị biên lớn nhất có được phép không?
- Có rủi ro integer overflow trong quá trình tính toán không?
- Có phân biệt NaN và infinity nếu dùng floating-point không?

Ví dụ:

~~~java
public long calculateFee(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException(
            "amount must be greater than or equal to 0"
        );
    }
    return Math.multiplyExact(amount, 2);
}
~~~

Trong ví dụ, một số đầu vào dương rất lớn có thể khiến **Math.multiplyExact** ném **ArithmeticException** vì overflow. Nếu v1 từng âm thầm wrap overflow mà v2 dùng **multiplyExact**, đây là thay đổi hành vi đối với input biên dù cả hai phiên bản đều compile.

### 5.2. IndexOutOfBoundsException và thứ tự kiểm tra

~~~java
import java.util.Objects;

public char characterAt(String text, int index) {
    Objects.requireNonNull(text, "text");
    Objects.checkIndex(index, text.length());
    return text.charAt(index);
}
~~~

Nếu **text == null** và **index** cũng sai, NPE xảy ra trước khi kiểm tra index. Đảo thứ tự guard có thể khiến một lỗi khác xuất hiện trước.

Trong Java, **Objects.checkIndex** kiểm tra chỉ số và ném **IndexOutOfBoundsException** khi không hợp lệ. Với khoảng bắt đầu/kết thúc, có các API **checkFromToIndex** và **checkFromIndexSize** để mô tả quy tắc range rõ hơn.

### 5.3. Thứ tự guard là hành vi có thể quan sát

Ví dụ v1:

~~~java
public void update(int index, String value) {
    if (index < 0) {
        throw new IndexOutOfBoundsException("index");
    }
    if (value == null) {
        throw new IllegalArgumentException("value");
    }
    // Update...
}
~~~

Ví dụ v2:

~~~java
public void update(int index, String value) {
    Objects.requireNonNull(value, "value");
    if (index < 0) {
        throw new IndexOutOfBoundsException("index");
    }
    // Update...
}
~~~

Với **index = -1** và **value = null**, v1 ném **IndexOutOfBoundsException**; v2 ném **NullPointerException**.

Nếu hệ thống muốn cam kết một thứ tự kiểm tra, hãy ghi nó trong contract. Nếu không, test nên tập trung vào một điều kiện sai tại một thời điểm để tránh cố định một thứ tự vốn không được bảo đảm.

## 6. Chuỗi, parsing và định dạng dữ liệu

Nâng phiên bản JDK, parser, validation library hoặc configuration có thể làm thay đổi cách input được phân tích.

### 6.1. Chuỗi rỗng khác chuỗi null

~~~java
String input = "";
~~~

**input** ở đây không null, nhưng rỗng. Một API có thể chấp nhận chuỗi rỗng như giá trị mặc định hoặc từ chối nó. Chuyển từ:

~~~java
if (input == null) {
    throw new IllegalArgumentException("missing");
}
~~~

sang:

~~~java
if (input == null || input.isBlank()) {
    throw new IllegalArgumentException("missing or blank");
}
~~~

sẽ mở rộng tập đầu vào bị từ chối. **String.isBlank()** kiểm tra các ký tự whitespace theo quy tắc Java, khác với **isEmpty()** chỉ kiểm tra chiều dài bằng 0.

### 6.2. Parsing số

~~~java
int value = Integer.parseInt("12");
~~~

Chuỗi không hợp lệ ném **NumberFormatException**. Tuy nhiên, một parser khác có thể hỗ trợ khoảng trắng, dấu phân cách hoặc fallback. Nếu migration đổi parser, tập input hợp lệ có thể thay đổi.

Ví dụ:

~~~java
Integer.parseInt(" 12 "); // NumberFormatException
Integer.parseInt("12");   // Thành công
~~~

Không nên “sửa” lỗi bằng cách trim input không có chủ đích nếu hợp đồng cũ yêu cầu từ chối khoảng trắng. Ngược lại, nếu API trước đây chấp nhận input có khoảng trắng, bỏ bước trim trong phiên bản mới là breaking behavior.

### 6.3. Parsing ngày giờ

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

try {
    LocalDate.parse("2026-02-30");
} catch (DateTimeParseException ex) {
    System.out.println(ex.getErrorIndex());
}
~~~

**DateTimeParseException** cung cấp thông tin chuyên biệt như chuỗi đầu vào được parse và error index. Nó có thể hữu ích cho diagnostics, nhưng khi một thư viện/framework bọc ngoại lệ này, consumer có thể nhận ngoại lệ cấp cao khác.

Đừng so sánh nguyên văn message từ parser nếu tài liệu không bảo đảm nội dung và ngôn ngữ của chuỗi đó. Với public API, nên chuyển thông tin cần thiết thành **error code** và **field path** ổn định.

### 6.4. Locale và encoding

Thông báo lỗi từ framework, validation provider hoặc hệ điều hành có thể được localize. Cùng một lỗi có thể có chuỗi tiếng Việt, tiếng Anh hoặc ngôn ngữ khác tùy locale.

Nếu test phụ thuộc message, hãy xác định locale và source của message. Tuy nhiên, ổn định hơn là assert error code/field/type thay vì văn bản hiển thị.

Với input JSON, XML hoặc văn bản, còn cần xét encoding và cấu hình parser. Một chuỗi được giải mã khác có thể dẫn đến validation khác dù source Java không đổi.

## 7. Helpful NullPointerException và thông báo do JVM tạo

Các JDK mới hỗ trợ thông báo NPE chi tiết hơn trong nhiều trường hợp, giúp xác định biểu thức nào gây dereference null. Tính năng **Helpful NullPointerExceptions** được giới thiệu trong JDK 14 (JEP 358) và được bật mặc định trong các release sau.

Ví dụ:

~~~java
public class Example {
    static class Customer {
        String name;
    }

    public static void main(String[] args) {
        Customer customer = null;
        System.out.println(customer.name.length());
    }
}
~~~

Một JVM hỗ trợ helpful NPE có thể giải thích rằng không thể đọc field vì biến hoặc kết quả trung gian là null. Cách diễn đạt cụ thể có thể phụ thuộc JVM, release, bytecode và vị trí lỗi.

### 7.1. Không xem message JVM là hợp đồng API

Một test như sau rất dễ bị lỗi khi nâng JDK:

~~~java
assertEquals(
    "expected exact JVM text",
    exception.getMessage()
);
~~~

Nếu ngoại lệ là NPE tự động do JVM sinh, chuỗi này thường là diagnostics, không phải contract do ứng dụng kiểm soát.

Ưu tiên:

~~~java
assertThrows(NullPointerException.class, () -> service.run(null));
~~~

hoặc nếu muốn bảo đảm input validation ở entry point, hãy kiểm tra một message do chính API chủ động tạo bằng **requireNonNull** và có công bố như một phần hợp đồng.

### 7.2. Vì sao message có thể không giống nhau?

- JDK version và JVM implementation khác nhau.
- Bytecode do compiler khác tạo ra.
- Một NPE phát sinh do dereference khác với NPE được ném tường minh.
- Một số tình huống runtime không có đủ thông tin để dựng cùng thông điệp.
- JVM flags có thể ảnh hưởng chi tiết của helpful NPE.
- Framework có thể catch và bọc ngoại lệ gốc.

Vì vậy, snapshot test stack trace hoặc message JVM từ một máy không nên là điều kiện tương thích xuyên JDK nếu không có lý do hợp đồng cụ thể.

## 8. Exception wrapping làm thay đổi loại lỗi mà consumer quan sát

Một lỗi validation có thể xuất phát từ **IllegalArgumentException** nhưng đến consumer dưới dạng **CompletionException**, **ExecutionException**, **InvocationTargetException** hoặc ngoại lệ framework khác.

### 8.1. Đồng bộ và bất đồng bộ

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class AsyncDemo {
    static String convert(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }
        return input.toUpperCase();
    }

    public static void main(String[] args) {
        CompletableFuture<String> task =
            CompletableFuture.supplyAsync(() -> convert(null));

        try {
            task.join();
        } catch (CompletionException ex) {
            System.out.println(ex.getCause().getClass().getName());
        }
    }
}
~~~

Với xử lý bất đồng bộ, consumer gọi **join()** có thể nhận **CompletionException** bọc lỗi gốc. **get()** sử dụng **ExecutionException** cho failure từ tác vụ. Nếu migration chuyển API đồng bộ sang bất đồng bộ hoặc đổi framework gọi, kiểu ngoại lệ được thấy ở boundary có thể đổi dù logic validation bên trong giữ nguyên.

### 8.2. Reflection và proxy

Gọi một method qua reflection có thể bọc ngoại lệ do method ném trong **InvocationTargetException**:

~~~java
try {
    method.invoke(target, arguments);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable root = ex.getCause();
    System.err.println(root);
}
~~~

Framework proxy có thể tiếp tục bọc hoặc chuyển đổi ngoại lệ. Khi phân tích bug, cần xem cả **top-level exception** và **root cause**; tránh chỉ chốt loại ngoại lệ từ một dòng log.

### 8.3. Đừng xóa cause khi chuyển đổi ngoại lệ

Nếu muốn API phát hành một ngoại lệ miền nghiệp vụ, nên giữ nguyên cause để hỗ trợ điều tra:

~~~java
public final class ImportException extends RuntimeException {
    public ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
try {
    parseDocument(input);
} catch (IllegalArgumentException ex) {
    throw new ImportException("Invalid document format", ex);
}
~~~

Cách này cung cấp loại ngoại lệ ổn định ở boundary, trong khi vẫn bảo toàn nguồn lỗi thực tế. Nếu consumer từng bắt **IllegalArgumentException** trực tiếp, chuyển sang **ImportException** vẫn là thay đổi contract cần đánh giá.

## 9. API ứng dụng nên định nghĩa hợp đồng lỗi như thế nào?

Một public API có thể chọn mức ổn định khác nhau cho các thành phần lỗi.

### 9.1. Tách machine-readable code khỏi human-readable message

Ví dụ mô hình lỗi miền nghiệp vụ:

~~~java
public enum ErrorCode {
    CUSTOMER_ID_REQUIRED,
    AMOUNT_OUT_OF_RANGE,
    RESOURCE_NOT_FOUND
}
~~~

~~~java
public final class DomainValidationException
        extends IllegalArgumentException {

    private final ErrorCode code;
    private final String field;

    public DomainValidationException(
            ErrorCode code, String field, String message) {
        super(message);
        this.code = code;
        this.field = field;
    }

    public ErrorCode getCode() {
        return code;
    }

    public String getField() {
        return field;
    }
}
~~~

~~~java
public final class PaymentService {
    public void pay(String customerId, long amount) {
        if (customerId == null || customerId.isBlank()) {
            throw new DomainValidationException(
                ErrorCode.CUSTOMER_ID_REQUIRED,
                "customerId",
                "Customer id is required"
            );
        }
        if (amount <= 0) {
            throw new DomainValidationException(
                ErrorCode.AMOUNT_OUT_OF_RANGE,
                "amount",
                "Amount must be positive"
            );
        }
        // Thực hiện nghiệp vụ sau validation.
    }
}
~~~

Tại boundary này, consumer có thể phân nhánh theo **ErrorCode** thay vì parse **getMessage()**. Message vẫn có thể phục vụ log hoặc UI và thay đổi theo locale.

### 9.2. Cần công bố điều gì?

| Thành phần lỗi | Nên xem là contract? | Ghi chú |
|---|---|---|
| Loại exception công khai | Có thể, nếu consumer được hướng dẫn bắt nó | Ghi trong Javadoc và migration guide |
| Error code ổn định | Nên có cho API ngoài tổ chức | Phù hợp máy đọc và định tuyến lỗi |
| Field/path gây lỗi | Có thể | Giữ format và tính riêng tư |
| HTTP status hoặc gRPC code | Có | Ảnh hưởng protocol behavior |
| Cấu trúc response body | Có | Bảo đảm schema compatibility |
| Message hiển thị | Thường không nên cố định | Có thể đổi cách diễn đạt hoặc ngôn ngữ |
| Stack trace và line number | Không | Phụ thuộc build/JDK/refactor |
| Tên class nội bộ và cause text | Thường không | Chi tiết triển khai |
| Thứ tự lỗi khi nhiều đối số sai | Chỉ khi có cam kết rõ | Nếu không, test từng invalid case |
| Retryability | Có thể | Quan trọng với consumer tự động |

Điểm then chốt là **không cần đóng băng tất cả thông tin lỗi**. Hãy đóng băng những phần consumer thực sự cần, và ghi rõ các phần chỉ có giá trị chẩn đoán.

### 9.3. Ghi Javadoc cho validation

~~~java
/**
 * Charges a positive amount for a nonblank customer id.
 *
 * @param customerId a nonblank customer id
 * @param amount amount greater than zero
 * @throws DomainValidationException
 *         if customerId is null/blank or amount is not positive
 */
public void pay(String customerId, long amount) {
    // Implementation...
}
~~~

Nếu lỗi có machine-readable code, có thể tham chiếu thêm bảng mã lỗi trong tài liệu API. Với phương thức public lâu dài, Javadoc giúp các nhóm migration đánh giá breaking behavior trước khi thay dependency.

## 10. Lớp framework: validation và HTTP error mapping

Trong Spring MVC, Jakarta Validation hoặc các framework tương tự, lỗi có thể xảy ra trước khi code controller chạy.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record PaymentRequest(
    @NotBlank String customerId,
    @Positive long amount
) {
}
~~~

Nếu controller sử dụng **@Valid** và binding được cấu hình phù hợp, framework có thể phát hiện constraint violation khi nhận request. Nhưng loại ngoại lệ nội bộ và cách biểu diễn HTTP response còn phụ thuộc controller signature, validator, framework version và exception handler.

### 10.1. Nâng framework có thể đổi đường lỗi

Ví dụ cùng một request sai:

~~~json
{
  "customerId": "",
  "amount": -10
}
~~~

Sau migration, có thể thay đổi:

- Validator chạy trước hay sau conversion.
- Request body lỗi cú pháp được phân loại khác với request hợp lệ về cú pháp nhưng sai constraint.
- Exception type framework ném ra.
- HTTP status và response content type mặc định.
- Tên field và error detail trong response.
- Cách framework xử lý **MethodArgumentNotValidException**, **ConstraintViolationException** hoặc những exception liên quan.

Không nên giả định rằng một tên ngoại lệ của Spring hoặc Jakarta Validator sẽ là duy nhất cho mọi trường hợp sai input. Test tại HTTP boundary mới cho thấy consumer thực sự nhận gì.

### 10.2. Cố định public error response tại boundary

Một lớp exception handler có thể chuyển các lỗi nội bộ thành mô hình chung:

~~~java
public record ApiError(
    String code,
    String field,
    String message
) {
}
~~~

Ví dụ response:

~~~json
{
  "code": "CUSTOMER_ID_REQUIRED",
  "field": "customerId",
  "message": "Customer id is required"
}
~~~

Consumer nên dùng **code** và **field** làm tín hiệu máy đọc. Nếu **message** được localize hoặc đổi câu chữ, vẫn có thể giữ backward compatibility ở mức code/schema.

Nếu service đang công bố exact message như contract, việc thay message vẫn cần phiên bản hóa hoặc thông báo migration. Tránh dùng lý do “message chỉ để hiển thị” để tự ý phá vỡ một hợp đồng đã được công bố và consumer đang phụ thuộc hợp lệ.

### 10.3. Spring có thể bọc ngoại lệ qua nhiều tầng

Service ném **IllegalArgumentException**, nhưng controller có thể áp dụng:

- Binding/conversion trước khi gọi service.
- Bean validation trước khi vào method.
- AOP proxy.
- Controller advice và exception resolver.
- Gateway/proxy HTTP phía trước.

Vì vậy, khi so sánh v1/v2 hãy quan sát **đầu ra cuối cùng của hệ thống**, không chỉ unit test trực tiếp gọi service.

## 11. Thứ tự validation và side effect

Một thay đổi rất dễ bỏ sót là **lỗi được phát hiện ở thời điểm khác**, kể cả khi loại ngoại lệ giữ nguyên.

### 11.1. Fail fast so với fail late

Version 1:

~~~java
public void submit(String requestId, String body) {
    audit.logReceived(requestId);
    String normalized = body.trim(); // Null -> NPE sau audit.
    repository.save(normalized);
}
~~~

Version 2:

~~~java
public void submit(String requestId, String body) {
    Objects.requireNonNull(body, "body");
    audit.logReceived(requestId);
    repository.save(body.trim());
}
~~~

Cả hai có thể ném NPE khi body null. Nhưng v1 đã ghi audit record trước khi lỗi, còn v2 không ghi. Nếu hệ thống dùng audit để thống kê request thất bại, hành vi observable đã thay đổi.

Với một public API, nên cân nhắc:

- Validation trước hay sau logging?
- Có thể tạo event, transaction hoặc ghi database trước khi ném lỗi không?
- Lỗi có được retry an toàn không?
- Có vi phạm idempotency không?
- Có gây partial update không?
- Có metric/alert dựa trên số lần gọi một phần code không?

### 11.2. Validation và transaction

~~~text
Request
   |
   v
Input validation
   |
   v
Begin transaction
   |
   v
Business operation
   |
   v
Commit
~~~

Đây là một luồng thường mong muốn cho input không hợp lệ, nhưng hệ thống có thể có yêu cầu audit, authentication hoặc authorization riêng. Không nhất thiết mọi validation phải diễn ra trước tất cả side effect; điều quan trọng là thứ tự được thiết kế rõ và nhất quán với hợp đồng.

Nếu migration chuyển validation ra ngoài transaction hoặc đưa nó vào một interceptor mới, cần kiểm tra rollback semantics và error mapping.

## 12. Kiểm thử các trường hợp lỗi bằng JUnit 5

Để kiểm tra validation, cần test không chỉ happy path mà cả các trường hợp biên, input null và sai kiểu.

### 12.1. assertThrows

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class PaymentServiceTest {
    @Test
    void rejectsNonPositiveAmount() {
        PaymentService service = new PaymentService();

        DomainValidationException ex = assertThrows(
            DomainValidationException.class,
            () -> service.pay("C-001", 0)
        );

        assertEquals(
            ErrorCode.AMOUNT_OUT_OF_RANGE,
            ex.getCode()
        );
        assertEquals("amount", ex.getField());
    }
}
~~~

**assertThrows** chấp nhận ngoại lệ thuộc kiểu được yêu cầu hoặc subtype của nó. Điều này phù hợp khi hợp đồng công bố một base exception và cho phép các subtype chuyên biệt.

### 12.2. assertThrowsExactly

Khi hợp đồng yêu cầu đúng một class cụ thể, JUnit 5 có **assertThrowsExactly**:

~~~java
@Test
void exactExceptionTypeIsRequired() {
    assertThrowsExactly(
        IllegalArgumentException.class,
        () -> legacyApi.rejectInvalidValue(-1)
    );
}
~~~

Nếu API có quyền chuyển từ **IllegalArgumentException** sang subtype cụ thể mà vẫn bảo đảm contract, assertThrowsExactly sẽ tạo test quá chặt. Chọn assertion theo hợp đồng cần giữ, không phải theo sở thích cá nhân.

### 12.3. Test message khi nào?

Một test kiểm tra message có thể phù hợp nếu thông báo là chuỗi do ứng dụng sở hữu và được cam kết, ví dụ:

~~~java
assertEquals(
    "amount must be positive",
    ex.getMessage()
);
~~~

Nhưng nếu message đến từ JDK, parser hoặc framework và không có cam kết ổn định, hãy ưu tiên assert:

- Exception class hoặc class hierarchy được công bố.
- Error code.
- Field/path.
- Nguyên nhân gốc phù hợp.
- Không xảy ra side effect không mong muốn.
- Response status/schema tại boundary.

### 12.4. Test tham số biên bằng parameterized tests

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AmountValidationTest {
    @ParameterizedTest
    @ValueSource(longs = {-100L, -1L, 0L})
    void rejectsNonPositiveAmount(long amount) {
        PaymentService service = new PaymentService();

        assertThrows(
            DomainValidationException.class,
            () -> service.pay("C-001", amount)
        );
    }
}
~~~

Ngoài các giá trị sai, cần test giá trị biên hợp lệ: số nhỏ nhất được chấp nhận, số lớn nhất, zero nếu hợp đồng cho phép, chuỗi Unicode, whitespace, danh sách rỗng và các trường hợp trùng key.

### 12.5. Test nhiều lỗi đầu vào

Khi nhiều field cùng sai, không nên assert một thông báo duy nhất nếu thứ tự validation không phải contract.

Có hai cách:

1. **Test độc lập mỗi rule:** tất cả field khác đều hợp lệ, chỉ một field sai.
2. **Test kết quả tổng hợp:** nếu API hỗ trợ trả danh sách violations, assert các code/field có mặt mà không phụ thuộc thứ tự, trừ khi API công bố thứ tự.

Ví dụ test một rule:

~~~java
@Test
void missingCustomerIdHasStableCode() {
    PaymentService service = new PaymentService();

    DomainValidationException ex = assertThrows(
        DomainValidationException.class,
        () -> service.pay(null, 100)
    );

    assertEquals(
        ErrorCode.CUSTOMER_ID_REQUIRED,
        ex.getCode()
    );
}
~~~

### 12.6. Kiểm tra không có side effect

Nếu lỗi validation phải được phát hiện trước khi ghi dữ liệu, có thể dùng mock hoặc fake repository:

~~~java
@Test
void invalidRequestMustNotWriteAnything() {
    PaymentService service = new PaymentService(repository);

    assertThrows(
        DomainValidationException.class,
        () -> service.pay(null, 100)
    );

    verifyNoInteractions(repository);
}
~~~

**verifyNoInteractions** là phương thức điển hình trong Mockito; đoạn code giả định repository được tạo như mock và PaymentService có constructor nhận repository. Khi dùng mẫu này trong dự án thật, cần điều chỉnh theo API thực tế.

## 13. Ma trận kiểm thử chéo phiên bản

Migration cần có baseline để phân biệt hành vi cũ với hành vi mới.

| Test case | Giá trị thử | Baseline cần ghi | Kết quả target cần đối chiếu |
|---|---|---|---|
| Null | **null** | Chấp nhận, default hay exception? | Input domain và exception |
| Empty string | **""** | Chấp nhận hay từ chối? | Validation rule |
| Blank | **"   "** | Trim, chấp nhận hay từ chối? | isBlank/normalization |
| Negative | **-1** | Loại ngoại lệ và thời điểm | Range contract |
| Zero | **0** | Sentinel hay giá trị hợp lệ? | Boundary semantics |
| Very large | **Long.MAX_VALUE** | Overflow, clamp, fail? | Arithmetic behavior |
| Duplicate keys | Hai key bằng nhau | Overwrite hay reject? | Collection API |
| Null element | Collection có null | Chấp nhận hay reject? | Factory contract |
| Invalid numeric string | **"12x"** | Parser/exception | Parser compatibility |
| Invalid date | Ngày không tồn tại | Parse/validation | DateTimeParseException/cause |
| Two invalid fields | Cả id và amount sai | Thứ tự hoặc tập lỗi | Priority nếu được công bố |
| Async failure | Task ném ngoại lệ | Wrapper/cause | Boundary exception |
| HTTP invalid request | JSON sai hoặc vi phạm constraint | Status/code/schema | Protocol compatibility |
| Locale change | Cùng lỗi với locale khác | Message và code | I18n vs machine contract |

Không nhất thiết tất cả các test phải assert exact message. Mục tiêu là ghi lại **hợp đồng thật sự cần bảo vệ**, kèm các quan sát hiện tại để nhóm quyết định phần nào được phép thay đổi.

### 13.1. Hai hướng kiểm thử khác nhau

**Golden regression** ghi nhận hành vi baseline và so với target. Nó giúp phát hiện mọi thay đổi quan sát được, kể cả thay đổi chưa có trong yêu cầu.

**Contract test** chỉ fail khi phần hợp đồng đã công bố bị vi phạm. Nó không nên fail chỉ vì stack trace có thêm một dòng hoặc một message chẩn đoán của JVM khác đi.

Kết hợp hai hướng sẽ hiệu quả hơn: dùng golden regression để **phát hiện**, dùng contract và quyết định migration để **phân loại** thay đổi có chấp nhận được không.

## 14. Cách khảo sát lỗi thực tế khi nâng JDK/framework

### Bước 1: Chốt môi trường baseline

Ghi:

- JDK vendor và version.
- JDK compiler, **--release**, bytecode target.
- Framework và dependency versions.
- Locale/timezone/charset liên quan.
- Cấu hình validation và exception handler.
- Artifact checksum và commit.
- Test logs/HTTP error samples.

Nếu baseline không tái tạo được, nhóm rất khó khẳng định một thay đổi là do migration hay vốn đã tồn tại.

### Bước 2: Tập hợp hợp đồng có consumer

Phân loại API:

- **Internal-only:** chỉ được dùng trong một module, có thể thay đổi cùng consumer.
- **Shared library:** có module khác dùng chung và có thể không nâng đồng thời.
- **Public SDK/SPI:** có consumer độc lập, thường cần chính sách tương thích rõ.
- **Network API:** consumer nhìn status, code và body thay vì Java exception trực tiếp.
- **Batch/event API:** consumer có thể thấy dead-letter message, retry policy hoặc error payload.

Đối với từng loại, xác định ngoại lệ nào nằm trong contract công khai, ngoại lệ nào chỉ là chi tiết triển khai.

### Bước 3: Thu thập negative cases

Tập trung vào:

- Null, empty, blank.
- Boundary value, overflows.
- Collection null, duplicate, empty.
- Parsing invalid/ambiguous input.
- Wrong state hoặc resource missing.
- Concurrent calls và async failures.
- Malformed JSON/XML.
- Multi-field validation và thứ tự lỗi.

Kết hợp dữ liệu synthetic với log đã khử thông tin nhạy cảm. Không đưa token, mật khẩu hoặc dữ liệu cá nhân nguyên văn vào test fixture/log.

### Bước 4: So sánh v1 và v2

Chạy cùng dữ liệu trên môi trường baseline và target. Lưu:

~~~text
Case ID:
Input class:
JDK / framework / library version:
Accepted / Rejected:
Exception type:
Exception superclass:
Root cause type:
Error code:
Field/path:
HTTP status (nếu có):
Message (diagnostic only nếu không thuộc contract):
Side effects:
Source artifact checksum:
Result: expected / changed / uncertain
~~~

### Bước 5: Phân loại thay đổi

| Loại thay đổi | Hướng xử lý |
|---|---|
| Specified JDK behavior vẫn được giữ | Giữ nguyên, cập nhật test quá chặt nếu cần |
| Message nội bộ đổi nhưng contract không đổi | Không cố giữ nguyên message; ghi diagnostic |
| Exception type công khai đổi | Đánh giá breaking change, wrapper hoặc compatibility layer |
| Validation rule chặt hơn | Kiểm tra dữ liệu thực, consumer và kế hoạch rollout |
| Validation rule lỏng hơn | Đánh giá security/invariant và rủi ro dữ liệu |
| HTTP error code/schema đổi | Chạy consumer contract test; cân nhắc versioning |
| Thời điểm validation/side effect đổi | Đánh giá transaction, audit, retry và idempotency |
| Exception chỉ đổi vì dependency conflict | Sửa dependency graph hoặc classpath |

### Bước 6: Đưa ra quyết định

Mỗi thay đổi cần được gắn với một trong các hướng:

- **Preserve:** giữ hành vi cũ bằng compatibility adapter hoặc explicit guard.
- **Adapt:** cập nhật consumer hoặc mapping để nhận hợp đồng mới.
- **Version:** tạo API version mới nếu thay đổi có tác động lớn.
- **Accept:** chấp nhận thay đổi diagnostics không phải contract.
- **Block:** hoãn migration nếu thiếu test/evidence cho một consumer quan trọng.

Không dùng nhãn “không ảnh hưởng” chỉ vì code vẫn compile.

## 15. Giữ backward compatibility bằng adapter

Giả sử dependency mới từ chối input bằng **IllegalStateException** nhưng API công khai trước đây đã cam kết **IllegalArgumentException**.

Có thể giữ loại ngoại lệ ở boundary:

~~~java
public final class LegacyCompatibleParser {
    private final NewParser parser;

    public LegacyCompatibleParser(NewParser parser) {
        this.parser = parser;
    }

    public ParsedValue parse(String value) {
        try {
            return parser.parse(value);
        } catch (IllegalStateException ex) {
            throw new IllegalArgumentException(
                "Invalid input", ex
            );
        }
    }
}
~~~

Đoạn code giả định **NewParser** và **ParsedValue** là kiểu ứng dụng. Adapter chỉ phù hợp nếu **IllegalStateException** ở đây thật sự đại diện cho input sai. Không nên bắt mọi IllegalStateException rồi biến thành lỗi của caller, vì loại đó có thể còn chỉ ra bug hoặc trạng thái hệ thống hỏng.

### 15.1. Khi nào nên sửa tại boundary?

- Thư viện phụ thuộc thay đổi exception type ngoài tầm kiểm soát.
- Consumer cũ bắt exception đã được công bố.
- Có thể ánh xạ chính xác từ lỗi nội bộ sang lỗi công khai.
- Chưa thể nâng đồng thời tất cả consumer.
- Có test cho các điều kiện và cause liên quan.

### 15.2. Khi nào không nên giữ hành vi cũ?

- Hành vi cũ bỏ qua dữ liệu sai, có nguy cơ bảo mật hoặc mất dữ liệu.
- Không thể phân biệt lỗi input với lỗi hệ thống một cách đáng tin cậy.
- Message cũ làm lộ dữ liệu nhạy cảm.
- Consumer chưa bao giờ được cam kết exact message.
- Giải pháp tương thích tạo ra ambiguity khiến lỗi hệ thống bị che giấu.

Trong trường hợp phải phá vỡ hành vi cũ, cần versioning, migration notes và thông báo rõ ràng đến consumer.

## 16. Bảo mật và khả năng quan sát của thông báo lỗi

Một message lỗi có thể hữu ích cho developer nhưng nguy hiểm khi trả trực tiếp cho client.

Ví dụ không nên trả nguyên văn:

~~~text
Failed SQL query in table user_tokens:
SELECT token FROM user_tokens WHERE customer_id='...'
~~~

Hoặc:

~~~text
Invalid password: secret-value
~~~

Các thông báo này làm lộ chi tiết database, câu truy vấn hoặc dữ liệu nhạy cảm. Khi nâng framework, default error handler có thể thay đổi lượng thông tin trả ra ngoài.

### 16.1. Tách external message và internal diagnostics

External response:

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "The request contains invalid data",
  "traceId": "request-123"
}
~~~

Internal log có thể giữ thêm exception type, cause và stack trace theo chính sách bảo mật. **traceId** giúp đối chiếu lỗi mà không phải đưa internal implementation ra public API.

### 16.2. Thông báo lỗi nên có tính ổn định vừa đủ

Một nguyên tắc thực dụng:

- **Error code**: ổn định, có tài liệu.
- **Field/path**: ổn định trong phạm vi schema đã công bố.
- **Message**: rõ ràng cho con người, có thể được cải thiện hoặc localize nếu không cam kết nguyên văn.
- **Stack trace**: chỉ phục vụ chẩn đoán.
- **Cause**: lưu trong hệ thống để điều tra; không expose trực tiếp cho bên ngoài.
- **Correlation ID**: dùng để truy vết chéo giữa client và server.

## 17. Những sai lầm phổ biến khi migration

### 17.1. Chỉ test happy path

API có thể hoạt động chính xác với input hợp lệ nhưng đã đổi toàn bộ hành vi null/invalid.

Cách khắc phục: thêm negative tests có phân loại theo input domain và exception contract.

### 17.2. Assert nguyên văn message JVM hoặc thư viện

Thông báo có thể đổi theo runtime, locale, implementation, parser hoặc dependency.

Cách khắc phục: assert code/type/field và contract công khai; coi message không ổn định là diagnostic.

### 17.3. Bắt RuntimeException hoặc Exception quá rộng

~~~java
try {
    process();
} catch (RuntimeException ex) {
    return defaultValue();
}
~~~

Đoạn này có thể nuốt cả lỗi lập trình, lỗi trạng thái và lỗi do input. Khi migration làm phát sinh lỗi mới, chương trình có thể âm thầm trả giá trị mặc định.

Cách khắc phục: bắt loại exception chính xác ở boundary, giữ cause và log phù hợp.

### 17.4. Đổi exception type chỉ để dùng một utility mới

Thay validation thủ công bằng **Objects.requireNonNull** có thể làm đổi **IllegalArgumentException** thành **NullPointerException**. Đây không phải refactor hoàn toàn vô hại nếu consumer phụ thuộc loại ngoại lệ cũ.

Cách khắc phục: so sánh contract rồi giữ loại lỗi cũ nếu cần.

### 17.5. Dùng message string để điều khiển nghiệp vụ

~~~java
if (ex.getMessage().contains("not found")) {
    retry();
}
~~~

Đây là cơ chế dễ vỡ vì message không được thiết kế làm machine-readable code. Sau migration, câu chữ có thể đổi hoặc được dịch.

Cách khắc phục: dùng error code, exception subtype ổn định hoặc status chính thức.

### 17.6. Bỏ qua validation precedence

Hai field sai có thể được xử lý theo thứ tự khác sau refactor.

Cách khắc phục: chỉ cam kết thứ tự nếu có yêu cầu nghiệp vụ; còn lại test mỗi validation rule riêng, hoặc assert tập violations.

### 17.7. Đánh đồng root cause với exception quan sát ở public boundary

Một lỗi **NumberFormatException** có thể đến client dưới dạng **MethodArgumentTypeMismatchException** của framework hoặc HTTP error body khác.

Cách khắc phục: test ở đúng boundary và đọc cause chain.

### 17.8. Lạm dụng adapter để che lỗi hệ thống

Bắt mọi ngoại lệ và chuyển thành **INVALID_ARGUMENT** có thể khiến lỗi database, bug hoặc timeout bị coi là lỗi input.

Cách khắc phục: phân loại nguyên nhân theo khả năng chứng minh, không đoán từ message.

### 17.9. Không kiểm tra side effects khi lỗi

Lỗi xảy ra trước hay sau khi ghi event, lưu database hoặc mở transaction có thể thay đổi tính idempotent và retry behavior.

Cách khắc phục: kiểm tra trạng thái sau invalid request, không chỉ loại exception.

## 18. Kế hoạch rollout cho thay đổi validation

Nếu migration cố ý siết chặt validation, cần thiết kế chuyển tiếp cho dữ liệu và consumer cũ.

Một lộ trình tham khảo:

~~~text
Baseline
    |
    v
Thu thập input thực tế, thống kê vi phạm
    |
    v
Định nghĩa contract mới và mã lỗi
    |
    v
Thông báo consumer, hỗ trợ song song nếu cần
    |
    v
Triển khai quan sát/feature flag phù hợp
    |
    v
Kiểm thử negative/contract/integration
    |
    v
Canary hoặc rollout có kiểm soát
    |
    v
Theo dõi tỉ lệ lỗi, support tickets, retry
    |
    v
Hoàn tất hoặc rollback theo tiêu chí
~~~

### 18.1. Metrics nên theo dõi

- Số request bị từ chối theo **error code**.
- Tỉ lệ HTTP 4xx/5xx nếu là network API.
- Số ngoại lệ theo class và vị trí phát sinh.
- Số retry và dead-letter message.
- Số lỗi parsing/conversion theo field.
- Số giao dịch có side effect trước khi thất bại.
- Sự khác biệt giữa các phiên bản service đang chạy song song.

Không đưa raw input nhạy cảm làm metric label. Dùng code/field có cardinality được kiểm soát.

### 18.2. Điều kiện rollback

Rollback được cân nhắc nếu:

- Tỉ lệ lỗi tăng đột biến ngoài dự kiến.
- Consumer quan trọng không xử lý được error code/type mới.
- Dữ liệu hợp lệ theo hợp đồng cũ bị từ chối mà chưa có migration.
- Retry behavior gây khuếch đại lưu lượng.
- Lỗi validation mới che giấu lỗi hệ thống.
- Error response vô tình lộ dữ liệu nhạy cảm.

Nếu thay đổi đã khiến dữ liệu được ghi theo định dạng mới, rollback code đơn thuần có thể không đủ. Cần kiểm tra khả năng đọc/ghi dữ liệu hai chiều.

## 19. Mẫu tài liệu thay đổi hành vi

Khi cần ghi một behavioral change vào migration register, có thể dùng mẫu:

~~~text
Change ID:
API/Method/Endpoint:
Owner:
Baseline JDK/framework/dependency:
Target JDK/framework/dependency:

Input case:
Old behavior:
Old exception type:
Old error code/status:
Old message (diagnostic or contract):
Old side effects:

New behavior:
New exception type:
New error code/status:
New message (diagnostic or contract):
New side effects:

Source of change:
Specified/documented/observed:
Affected consumers:
Compatibility decision:
Migration action:
Acceptance criteria:
Tests/evidence:
Rollback plan:
Residual risk:
~~~

### 19.1. Ví dụ quyết định

~~~text
Change ID: BEH-014
API: POST /payments
Input case: amount = 0

Old behavior: Accepted and ignored payment
New behavior: Rejected before persistence

Public code: AMOUNT_OUT_OF_RANGE
HTTP status: 400
Message: Display text; may be localized

Compatibility decision:
- Breaking for clients sending zero as no-op.
- Provide migration notes and consumer update window.
- Keep code/status stable once new API version is published.

Acceptance:
- Valid payments unchanged.
- Zero rejected consistently.
- No payment event or database write on rejection.
- No sensitive payload in response/log.
~~~

Các giá trị trong ví dụ là chính sách giả định của ứng dụng, không phải quy tắc mặc định bắt buộc của JDK hoặc Spring.

## 20. Checklist trước khi kết luận migration tương thích

### Hợp đồng đầu vào

- [ ] Đã xác định các đầu vào null, empty, blank, giá trị biên và invalid format.
- [ ] Đã phân biệt behavior được đặc tả và behavior chỉ quan sát.
- [ ] Đã tìm những lần thay đổi parser, collection factory và validation utility.
- [ ] Đã xem xét thứ tự validation khi có nhiều lỗi.
- [ ] Đã xác định thay đổi input domain là chủ đích hay ngoài ý muốn.

### Ngoại lệ và thông báo

- [ ] Đã lập danh sách exception type công khai cần giữ.
- [ ] Đã xem xét superclass/subtype của exception.
- [ ] Đã kiểm tra wrapper và root cause qua các tầng sync/async/framework.
- [ ] Không dùng JVM-generated message như contract nếu không có cam kết.
- [ ] Có error code/status/field ổn định cho consumer máy đọc.
- [ ] Không làm lộ dữ liệu nhạy cảm qua error message.

### Kiểm thử

- [ ] Có negative tests cho null, range, parsing và duplicate.
- [ ] Có test loại ngoại lệ theo đúng mức contract: subtype hoặc exact.
- [ ] Có test HTTP error schema nếu API qua mạng.
- [ ] Có test bảo đảm không có side effect ngoài mong đợi.
- [ ] Đã chạy cùng trường hợp trên baseline và target.
- [ ] Đã lưu artifact, JDK, dependency versions và test evidence.
- [ ] Đã tách golden observation khỏi acceptance criteria công khai.

### Vận hành

- [ ] Đã xác định consumer bị ảnh hưởng bởi exception/status/code mới.
- [ ] Có kế hoạch tương thích/adapter/versioning nếu breaking.
- [ ] Có telemetry theo error code và tỉ lệ invalid request.
- [ ] Đã đánh giá retry, transaction, idempotency và rollback.
- [ ] Có owner phê duyệt rủi ro còn lại.

## 21. Tài liệu tham khảo cho việc đối chiếu

Khi xử lý một trường hợp thực tế, nên đọc đặc tả và tài liệu đúng phiên bản:

- **Java Language Specification – Exceptions:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html
- **Objects API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html
- **NullPointerException API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NullPointerException.html
- **JEP 358 – Helpful NullPointerExceptions:** https://openjdk.org/jeps/358
- **Java Collections factory methods:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html
- **JUnit 5 User Guide:** https://junit.org/junit5/docs/current/user-guide/
- **Jakarta Validation:** https://jakarta.ee/specifications/bean-validation/
- **Spring Framework Reference:** https://docs.spring.io/spring-framework/reference/

Tài liệu JDK và framework mô tả contract theo release; thông báo lỗi cụ thể từ một build chỉ là bằng chứng quan sát. Khi có mâu thuẫn, cần xác minh artifact, runtime, API được dùng và loại lỗi ở đúng boundary.

---

**Kết luận:** Kiểm tra đối số, loại ngoại lệ và thông báo lỗi đều là hành vi có thể thay đổi trong Java migration. Muốn giữ tương thích, hãy quyết định rõ phần nào là hợp đồng ổn định, phần nào chỉ là diagnostics, xây dựng negative/contract tests cho các trường hợp sai, quan sát cả root cause lẫn lỗi ở public boundary và bảo vệ invariant/side effect. Đừng xem một message khác đi là breaking change nếu nó chưa từng được cam kết, nhưng cũng đừng xem thay đổi validation hoặc exception type là vô hại chỉ vì tất cả source vẫn biên dịch thành công.
