# NullPointerException: dereference, unboxing và đầu vào null trong Java

> **Java Core – Exception** · Nhóm: **Ngoại lệ runtime** · Phiên bản minh họa: **Java 17+**. Chủ đề tập trung vào ba nguồn lỗi thường gặp: truy cập qua tham chiếu `null`, chuyển wrapper sang primitive (*unboxing*) và hợp đồng xử lý tham số đầu vào có thể là `null`.

## 1. NullPointerException là gì?

`java.lang.NullPointerException` (viết tắt **NPE**) là một lớp con của `RuntimeException`. Nó biểu thị việc chương trình đã thực hiện một thao tác yêu cầu có đối tượng hoặc giá trị cụ thể, nhưng tham chiếu được sử dụng lại là `null`.

Tổng quan:

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.NullPointerException
~~~

NPE là **unchecked exception**: compiler **không buộc** phương thức khai báo `throws NullPointerException`, và cũng không buộc caller bắt nó. Tuy nhiên, nếu NPE được ném mà không được xử lý, luồng thực thi hiện tại có thể kết thúc bất thường.

Ví dụ điển hình:

~~~java
String name = null;
int length = name.length(); // NPE tại runtime.
~~~

Đây là **đoạn minh họa trong một method**, không phải chương trình độc lập. Biến `name` có **kiểu tham chiếu** `String` và giá trị `null`. Khi thực thi lời gọi method instance `name.length()`, Java không có đối tượng String thực tế làm receiver.

**Phân biệt:** `null` tự nó **không phải một exception** và cũng không phải giá trị mặc định của mọi biến. `null` là một giá trị tham chiếu đặc biệt thể hiện không tham chiếu tới object nào. Những biến primitive như `int`, `boolean` không nhận trực tiếp giá trị `null`.

### Những điều cần nắm sau bài

1. Nhận biết chính xác thao tác **dereference** nào ném NPE: gọi method instance, đọc/ghi field instance, truy cập mảng, lấy độ dài mảng và nhiều phép toán khác cần receiver khác null.
2. Hiểu vì sao **unboxing** một wrapper như `Integer` hoặc `Boolean` có giá trị null dẫn tới NPE dù không thấy method call tường minh.
3. Xác định rõ API **cho phép null, cấm null hay áp dụng giá trị mặc định**, tránh thiết kế phương thức mơ hồ.
4. Sử dụng kiểm tra null, `Objects.requireNonNull` và các API phù hợp mà không làm mất lỗi gốc.
5. Chẩn đoán NPE dựa trên stack trace và *helpful NullPointerException messages* của Java hiện đại, nhưng không phụ thuộc vào nguyên văn thông báo.
6. Biên dịch và chạy một chương trình Java 17 có stdout được kiểm chứng.

## 2. Null có thể xuất hiện ở đâu?

Một số ví dụ:

~~~java
String text = null;                 // Hợp lệ: String là kiểu tham chiếu.
Integer count = null;               // Hợp lệ: wrapper cũng là tham chiếu.
int[] numbers = null;               // Hợp lệ: mảng là đối tượng.
Object value = null;                // Hợp lệ.
int quantity = 0;                   // Primitive dùng một giá trị int.
boolean enabled = false;            // Primitive dùng một giá trị boolean.
~~~

Ngược lại:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
int quantity = null;
boolean enabled = null;
~~~

NPE liên quan tới **giá trị runtime** của tham chiếu, không đơn thuần là cách biến được khai báo. Một method có kiểu trả về `String` vẫn có thể trả `null` nếu hợp đồng/triển khai cho phép. Một field tham chiếu chưa được gán tường minh có thể có giá trị mặc định `null` khi object được tạo; còn **biến cục bộ** phải đáp ứng quy tắc *definite assignment* trước khi dùng, không được tự động xem là có giá trị null.

Ví dụ minh họa:

~~~java
class Record {
    String title; // Mặc định null nếu chưa được gán.
}
~~~

Nếu tạo `new Record()` rồi thực thi `record.title.length()`, NPE xảy ra ở **lời gọi length() trên giá trị field title**, không phải ở việc đọc field `title` từ một object `record` không null.

### Null không tự động ném lỗi

Các thao tác sau hợp lệ:

~~~java
String data = null;
boolean missing = (data == null); // true.
boolean matched = (data instanceof String); // false.
System.out.println(data);         // In chuỗi "null" theo println(Object).
~~~

Không có NPE chỉ vì gán, so sánh bằng `== null`, kiểm tra `instanceof`, hoặc truyền một tham chiếu null cho phương thức **có hỗ trợ null**. NPE xảy ra khi có **một thao tác cụ thể không chấp nhận null**, chẳng hạn dereference hoặc unboxing.

**Lưu ý:** `System.out.println(data)` ở ví dụ này in chữ `null` vì overload nhận String xử lý đầu vào null theo hợp đồng của `PrintStream`. Không được suy ra mọi API cũng xử lý null giống vậy.

## 3. Dereference: truy cập method và field qua null

### 3.1. Gọi instance method

~~~java
String input = null;
int size = input.trim().length(); // NPE tại bước gọi trim().
~~~

Receiver `input` là null, nên lời gọi instance method `trim()` không thể được thực hiện bình thường. Vì `trim()` đã thất bại nên bước `length()` phía sau cũng chưa được chạy.

Với chuỗi method dài:

~~~java
String city = order.getCustomer().getAddress().getCity();
~~~

đây là ví dụ minh họa, giả định các class và method đã định nghĩa. NPE có thể đến từ nhiều vị trí:

- `order` chính nó null khi gọi `getCustomer()`.
- `getCustomer()` trả null, rồi code gọi `getAddress()` trên null.
- `getAddress()` trả null, rồi code gọi `getCity()` trên null.
- Nếu `getCity()` trả null nhưng chỉ **gán** cho biến `city`, dòng đó có thể hoàn tất bình thường; NPE chỉ phát sinh sau khi có thao tác không chấp nhận giá trị null đó.

Vì vậy **NPE không đồng nghĩa toàn bộ biểu thức bên trái đều null**. Cần tìm chính xác đoạn dereference bị lỗi.

### 3.2. Đọc hoặc gán instance field

~~~java
class User {
    String email;
}

User user = null;
String email = user.email; // NPE khi đọc field instance.
~~~

Một thao tác ghi cũng có thể lỗi:

~~~java
User user = null;
user.email = "contact@example.com"; // NPE tại runtime.
~~~

Đây là các **đoạn minh họa trong method/class**, không đặt tất cả cùng một scope mà khai báo biến trùng tên. NPE ở đây là do **biến receiver `user` null**, không phải do bản thân field `email` có kiểu String.

So sánh trường hợp khác:

~~~java
User user = new User();
String email = user.email; // Hợp lệ, email == null.
~~~

Object `user` khác null nên đọc field thành công, dù **giá trị bên trong field** là null. Chỉ khi code làm `email.trim()` hoặc dereference tương tự mới có NPE.

### 3.3. Mảng null và phần tử mảng null là hai lỗi khác nhau

~~~java
String[] names = null;
int length = names.length; // NPE vì chính mảng null.
String first = names[0];   // NPE vì mảng null.
~~~

Một trường hợp khác:

~~~java
String[] names = new String[1]; // Mảng hợp lệ, phần tử names[0] mặc định null.
String first = names[0];        // Hợp lệ, first == null.
int length = first.length();    // NPE vì first null.
~~~

Phân biệt thêm với `ArrayIndexOutOfBoundsException`: nếu mảng **khác null** nhưng truy cập chỉ số không hợp lệ, đó là lỗi về giới hạn chỉ số, không phải lỗi tham chiếu null.

### 3.4. Các thao tác khác có thể yêu cầu giá trị khác null

Ngoài method/field/mảng, một số cấu trúc Java cũng có thể phát sinh NPE:

- `synchronized (lock) { ... }` nếu biểu thức `lock` cho kết quả null.
- Lệnh `throw ex;` nếu biểu thức `ex` cho kết quả null: Java tạo/ném một NullPointerException theo quy tắc `throw`.
- `switch` thông thường trên giá trị tham chiếu null trong Java 17 không có case null hợp lệ theo chế độ ngôn ngữ ổn định: selector null dẫn tới NPE.
- Unboxing `Integer`, `Long`, `Boolean` ... mà giá trị null.

Không phải thao tác nào cũng cần nhìn thấy dấu chấm `.` mới có NPE. Riêng **unboxing** là nguồn lỗi đặc biệt quan trọng vì code trông như đang thực hiện số học hoặc kiểm tra boolean bình thường.

## 4. Unboxing: vì sao wrapper null gây NullPointerException?

**Autoboxing** là chuyển đổi từ primitive sang wrapper, ví dụ `int → Integer`. **Unboxing** là chuyển ngược từ wrapper sang primitive, ví dụ `Integer → int`, khi ngữ cảnh yêu cầu.

Theo [JLS Java 17 mục 5.1.8 – Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8), chuyển đổi unboxing từ **tham chiếu null** sẽ ném `NullPointerException`.

### 4.1. Gán Integer cho int

~~~java
Integer boxed = null;
int number = boxed; // NPE.
~~~

Khi biên dịch, Java áp dụng unboxing conversion. Có thể hiểu khái niệm tương đương với việc lấy giá trị qua `boxed.intValue()`: nếu `boxed` null, không có số `int` nào được lấy ra. Đây là **mô tả ngữ nghĩa**, không phải bảo đảm compiler sinh đúng một chuỗi bytecode cố định.

So sánh:

~~~java
Integer boxed = 5; // Boxing số 5 thành Integer.
int number = boxed; // Unboxing thành int, number == 5.
~~~

Unboxing **không phải lúc nào cũng lỗi**; chỉ ném NPE nếu tham chiếu được chuyển đổi là null.

### 4.2. Phép toán số học cũng có thể tự unbox

~~~java
Integer count = null;
int next = count + 1; // NPE.
~~~

Toán tử `+` trong biểu thức này cần giá trị số primitive. `count` được unbox, nên dù bạn không viết `count.intValue()`, NPE vẫn có thể xảy ra.

Ví dụ khác:

~~~java
Integer left = null;
Integer right = 2;
int sum = left + right; // NPE do left.
~~~

NPE không liên quan đến phép cộng vượt phạm vi số hoặc dữ liệu nhập sai định dạng. Nó phát sinh tại thao tác **chuyển một wrapper null sang primitive**.

### 4.3. So sánh có thể kích hoạt unboxing

~~~java
Integer score = null;
boolean absent = score == null; // An toàn; so sánh tham chiếu.
boolean isZero = score == 0;    // NPE; so với int literal nên cần unboxing.
~~~

Phân biệt rõ hai biểu thức:

- `score == null` không yêu cầu giá trị primitive nên dùng để **kiểm tra null**.
- `score == 0` có operand `0` là `int`, dẫn đến unboxing `score`; nếu null thì lỗi.

Đừng suy ra mọi dấu `==` đều nguy hiểm hoặc mọi dấu `==` đều an toàn; ý nghĩa phụ thuộc **kiểu tĩnh của hai operand** và các quy tắc chuyển đổi.

### 4.4. Boolean null trong if, while và toán tử logic

~~~java
Boolean approved = null;
if (approved) {
    System.out.println("approved");
}
~~~

Điều kiện `if` cần `boolean` primitive, nên Java phải unbox `approved`. Khi `approved` null, chương trình ném NPE trước khi chọn nhánh.

Một cách xử lý nếu nghiệp vụ coi null là **không được phê duyệt**:

~~~java
if (Boolean.TRUE.equals(approved)) {
    System.out.println("approved");
}
~~~

`Boolean.TRUE` là đối tượng không null, `equals` so sánh an toàn với argument null. Kết quả khi `approved` null là false. Nhưng **không tự động thay mọi giá trị null bằng false**: nếu null nghĩa là “chưa được đánh giá”, ba trạng thái true/false/unknown có thể là một phần hợp đồng, không nên làm mất ý nghĩa.

### 4.5. Unboxing từ đầu ra của collection và generic

Ví dụ khá thường gặp:

~~~java
Map<String, Integer> quantities = new HashMap<>();
Integer boxed = quantities.get("missing"); // null nếu không có mapping.
int quantity = quantities.get("missing");   // NPE do unboxing.
~~~

Đây là đoạn minh họa, cần import `Map` và `HashMap`. Generic `Integer` **không bảo đảm** mọi giá trị lấy từ map đều khác null. Một phép gọi `get()` có thể trả null do khóa không tồn tại, hoặc vì map cho phép mapping tới null.

**Cẩn trọng với `getOrDefault(key, defaultValue)`:** Nếu một map chứa khóa đó nhưng giá trị liên kết là null, một số implementation tuân hợp đồng `Map.getOrDefault` sẽ trả **null** (vì khóa có mapping), không trả default. Do đó không nên khẳng định `getOrDefault` luôn loại bỏ NPE do unboxing trong mọi trạng thái map.

Phải xác định contract: null là “không có dữ liệu” hay một giá trị hợp lệ? Nếu null bị cấm, kiểm tra sớm hoặc chọn cấu trúc lưu trữ ngăn null; nếu cho phép, phải quyết định cách chuyển sang primitive.

## 5. Chương trình Java 17 hoàn chỉnh để kiểm chứng

Tạo tệp **`NullPointerExceptionDemo.java`**. Ví dụ trình bày nhiều nguyên nhân NPE theo từng ca, bắt NPE **chỉ ở phạm vi demo** để tiếp tục chạy các ca khác. Trong ứng dụng thật, tránh bắt và im lặng bỏ qua lỗi lập trình như thế này.

~~~java
import java.util.Objects;

public class NullPointerExceptionDemo {
    private static final class Profile {
        private final String name;

        private Profile(String name) {
            this.name = name;
        }

        private String upperName() {
            return name.toUpperCase();
        }
    }

    private static String findName() {
        return null;
    }

    private static void requireName(String name) {
        Objects.requireNonNull(name, "name must not be null");
        System.out.println("accepted=" + name);
    }

    private static String normalize(String raw) {
        return raw == null ? "" : raw.trim();
    }

    private static void test(String label, Runnable task) {
        System.out.println("== " + label + " ==");
        try {
            task.run();
            System.out.println("completed");
        } catch (NullPointerException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
            if ("explicit validation".equals(label)) {
                System.out.println("message=" + ex.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        Profile profile = null;
        int[] numbers = null;
        Integer count = null;
        Boolean approved = null;

        test("method dereference", () -> System.out.println(profile.upperName()));
        test("field dereference", () -> System.out.println(profile.name));
        test("array length", () -> System.out.println(numbers.length));
        test("array element", () -> System.out.println(numbers[0]));
        test("unbox assignment", () -> {
            int value = count;
            System.out.println(value);
        });
        test("unbox arithmetic", () -> System.out.println(count + 1));
        test("unbox condition", () -> {
            if (approved) {
                System.out.println("approved");
            }
        });
        test("nullable return", () -> System.out.println(findName().length()));
        test("explicit validation", () -> requireName(null));

        System.out.println("== safe operations ==");
        System.out.println("null comparison=" + (profile == null));
        System.out.println("instanceof=" + (profile instanceof Profile));
        System.out.println("literal equals=" + "admin".equals(findName()));
        System.out.println("objects equals=" + Objects.equals(null, null));
        System.out.println("normalize=[" + normalize(null) + "]");

        System.out.println("== valid input ==");
        requireName("Lan");
    }
}
~~~

Biên dịch với JDK 17 hoặc mới hơn và chọn mức ngôn ngữ 17:

~~~bash
javac --release 17 -encoding UTF-8 NullPointerExceptionDemo.java
java NullPointerExceptionDemo
~~~

**Stdout chính xác đã kiểm chứng bằng việc biên dịch và chạy:**

~~~text
== method dereference ==
caught=NullPointerException
== field dereference ==
caught=NullPointerException
== array length ==
caught=NullPointerException
== array element ==
caught=NullPointerException
== unbox assignment ==
caught=NullPointerException
== unbox arithmetic ==
caught=NullPointerException
== unbox condition ==
caught=NullPointerException
== nullable return ==
caught=NullPointerException
== explicit validation ==
caught=NullPointerException
message=name must not be null
== safe operations ==
null comparison=true
instanceof=false
literal equals=false
objects equals=true
normalize=[]
== valid input ==
accepted=Lan
~~~

Chương trình cố ý **không in thông điệp NPE do JVM tự tạo** ở các ca dereference/unboxing, bởi những thông điệp đó có thể khác nhau giữa JVM và cấu hình. Chỉ có message do `Objects.requireNonNull(name, "name must not be null")` cung cấp là được in tường minh.

### 5.1. Những ca dereference

- `method dereference`: biến `profile` null nên lời gọi `profile.upperName()` phát sinh NPE.
- `field dereference`: `profile.name` thất bại vì receiver `profile` null.
- `array length`: `numbers.length` yêu cầu mảng khác null.
- `array element`: `numbers[0]` cần một mảng thực tế; khi mảng null thì NPE.
- `nullable return`: `findName()` trả null; lời gọi `length()` trên kết quả đó ném NPE.

Ở ca `method dereference`, phương thức `upperName()` **không chạy được** vì không có Profile làm receiver. Đừng nhầm với tình huống `profile != null` nhưng field `name == null`: khi ấy phương thức có thể được gọi và NPE xuất hiện **bên trong** `upperName()` ở lệnh `name.toUpperCase()`.

### 5.2. Những ca unboxing

- `unbox assignment`: `Integer count = null` phải chuyển sang `int value`.
- `unbox arithmetic`: toán tử `count + 1` cần số primitive.
- `unbox condition`: `Boolean approved = null` phải chuyển sang `boolean` cho điều kiện `if`.

Ba thao tác không chứa lời gọi method `.intValue()` hoặc `.booleanValue()` tường minh, nhưng compiler vẫn áp dụng quy tắc unboxing. Đây là nhóm lỗi khó thấy nếu người đọc chỉ tìm những dấu chấm dereference trong source code.

### 5.3. Kiểm tra đầu vào và hành vi an toàn

- `explicit validation`: `Objects.requireNonNull` kiểm tra ngay khi method nhận argument null và ném NPE với message do lập trình viên quy định.
- `null comparison`: `profile == null` là true.
- `instanceof`: toán hạng null làm biểu thức `instanceof Profile` trả false.
- `literal equals`: `"admin".equals(null)` trả false vì receiver `"admin"` khác null.
- `objects equals`: `Objects.equals(null, null)` trả true theo hợp đồng API.
- `normalize`: chọn chính sách rõ ràng **null thành chuỗi rỗng**, không dereference null.
- `valid input`: `requireName("Lan")` chấp nhận argument hợp lệ và in `accepted=Lan`.

**Không tổng quát hóa** rằng mọi null nên biến thành chuỗi rỗng hoặc số 0; đó chỉ là **một chính sách nghiệp vụ minh họa**.

## 6. Null là đầu vào: truyền null và dereference là hai sự kiện khác nhau

Một API có thể nhận được `null` mà **không lập tức ném NPE**:

~~~java
static void send(String recipient) {
    // Chỉ nhận tham chiếu; chưa dereference.
}
send(null); // Không tự phát sinh NPE chỉ do truyền argument.
~~~

Đây là đoạn minh họa, đặt ở đúng ngữ cảnh class và method. Nếu `send` sau đó làm `recipient.trim()`, nó có thể ném NPE; còn nếu nó chủ động kiểm tra null, hành vi phụ thuộc nhánh xử lý.

Nên quyết định **hợp đồng tham số** trước khi viết code:

| Chính sách API | Ý nghĩa của null | Cách triển khai thường gặp |
| --- | --- | --- |
| **Cấm null** | Caller vi phạm tiền điều kiện | `Objects.requireNonNull(arg, "arg must not be null")` |
| **Cho phép null** | Null có ý nghĩa như “chưa biết”/“không có” | Nhánh điều kiện riêng hoặc kiểu dữ liệu biểu diễn trạng thái rõ |
| **Null dùng default** | Nếu vắng dữ liệu thì chọn giá trị mặc định đã định nghĩa | Ternary, `Objects.requireNonNullElse`, logic default |
| **Không dùng null ở public API** | Caller phải truyền một object/value hợp lệ | Factory/validation và hợp đồng nhất quán |

Một chương trình có API không rõ nullability rất dễ sinh ra NPE xa nơi nguyên nhân bắt đầu: input null đi qua ba tầng rồi mới bị dereference. Kiểm tra tại ranh giới giúp xác định **đúng trách nhiệm** giữa bên gọi và bên được gọi.

### 6.1. Cấm null: fail fast

~~~java
import java.util.Objects;

class Account {
    private final String id;

    Account(String id) {
        this.id = Objects.requireNonNull(id, "id must not be null");
    }
}
~~~

Class này có thể biên dịch độc lập (trong file phù hợp). Nếu caller truyền null, constructor ném NPE **tại điểm validate**, với thông điệp nhất quán, thay vì lưu null vào field rồi phát sinh NPE tại một phương thức không liên quan về sau.

Lợi ích:

- Phát hiện sai hợp đồng gần **điểm nhận dữ liệu**.
- Giảm khả năng object được tạo ở trạng thái vi phạm invariant.
- Giữ stack trace gắn với nơi xác thực tiền điều kiện, dễ tìm bug của caller.
- Không cần trải các câu kiểm tra null trùng lặp ở mọi method nếu invariant đã được bảo đảm.

Tuy vậy, `Objects.requireNonNull` chỉ kiểm tra **null**, không kiểm tra chuỗi rỗng/blank, giá trị âm hoặc quy tắc nghiệp vụ khác. Với `String`, có thể cần xác thực thêm.

### 6.2. Cho phép null: xử lý đúng ý nghĩa

~~~java
static String displayName(String nickname) {
    return nickname == null ? "(anonymous)" : nickname.trim();
}
~~~

Đây là phương thức minh họa. Nó **chủ động xác định** ý nghĩa của null là dùng tên thay thế. Điều này phù hợp nếu null được phép mang nghĩa “không có nickname”.

Một số ứng dụng lại cần phân biệt:

- Người dùng chưa nhập dữ liệu.
- Người dùng cố tình xóa giá trị.
- Dữ liệu bị thiếu do lỗi hệ thống.

Nếu ba trạng thái này quan trọng, việc tự động đổi mọi null thành `""` có thể làm mất thông tin. Nên dùng enum, result type, validation state hoặc thiết kế API phù hợp, không mặc định null đồng nghĩa chuỗi rỗng.

### 6.3. Cần giá trị default: dùng utility nhưng hiểu điều kiện

Từ Java 9, `Objects.requireNonNullElse(value, defaultValue)` trả đối số thứ nhất nếu không null, ngược lại trả default **phải khác null**:

~~~java
String language = Objects.requireNonNullElse(requestedLanguage, "vi");
~~~

Đoạn minh họa cần import `Objects` và biến `requestedLanguage`. Nếu cả hai đối số đều null, API ném NPE vì không thể trả về một fallback hợp lệ.

Ngoài ra có `Objects.requireNonNullElseGet(value, supplier)` để tính fallback theo nhu cầu; supplier hoặc kết quả fallback null cũng có thể gây NPE. Không coi utility này là bằng chứng tự động rằng mọi value từ ngoài đều đáng tin cậy.

## 7. Chọn cách kiểm tra null phù hợp

Chọn cách xử lý dựa trên **hợp đồng của tham chiếu**, không chỉ dựa vào việc muốn tránh stack trace:

| Hợp đồng | Cách viết thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| `null` là dữ liệu tùy chọn | `if (value == null)` | Phân nhánh rõ ràng, không giả vờ dữ liệu có mặt |
| `null` bị cấm | `Objects.requireNonNull(value, "value")` | Báo NPE sớm, có tên tham số |
| So sánh chuỗi với literal cố định | `"admin".equals(role)` | Không dereference biến `role` có thể null |
| So sánh hai đối tượng có thể null | `Objects.equals(a, b)` | Xử lý cả trường hợp hai bên cùng null |
| Kiểm tra kiểu dữ liệu động | `value instanceof String` | Với null, biểu thức là `false`, không NPE |
| Kết quả tra cứu có thể vắng mặt | `Optional.ofNullable(findName())` | Diễn đạt giá trị tùy chọn |

Các đoạn ví dụ trong bảng giả định biến/method và import `java.util.Objects`, `java.util.Optional` thích hợp.

Hai cách có hợp đồng khác nhau:

~~~java
static String normalizeOptional(String raw) {
    return raw == null ? "" : raw.trim();
}

static String normalizeRequired(String raw) {
    return java.util.Objects.requireNonNull(raw, "raw").trim();
}
~~~

Đây là các phương thức hợp lệ khi đặt trong một lớp Java. `normalizeOptional(null)` trả chuỗi rỗng **vì API cho phép fallback**, còn `normalizeRequired(null)` ném `NullPointerException` có chủ đích. Đừng tùy tiện thay một hợp đồng bằng hợp đồng kia.

`Objects.equals(null, null)` trả `true`, nhưng không thay thế phép tính trên primitive và có thể có ý nghĩa khác so với unboxing wrapper. `Optional.ofNullable(null)` tạo Optional rỗng; trái lại `Optional.of(null)` ném NPE và `Optional.get()` trên giá trị rỗng ném `NoSuchElementException`. Các overload của `Objects.requireNonNull`, `requireNonNullElse` và cách thiết kế tiền điều kiện được trình bày kỹ hơn ở bài về kiểm tra điều kiện đầu vào.

## 8. Unboxing null: ba hướng phòng tránh có chủ đích

### Hướng A: kiểm tra trước khi chuyển sang primitive

~~~java
Integer quantity = lookupQuantity();
if (quantity == null) {
    throw new IllegalArgumentException("quantity is required");
}
int count = quantity;
~~~

Đây là mã minh họa; `lookupQuantity()` chưa có định nghĩa. Với hợp đồng **bắt buộc có quantity**, ném lỗi xác thực nghiệp vụ có thể hợp lý hơn mặc định thay null bằng 0.

Nếu null là lỗi của caller, cũng có thể dùng `Objects.requireNonNull(quantity, "quantity required")`. Việc chọn NPE hay IllegalArgumentException phụ thuộc quy ước API; quan trọng là thông điệp và thời điểm kiểm tra rõ ràng.

### Hướng B: default trước khi unbox

~~~java
Integer quantity = lookupQuantity();
int count = quantity != null ? quantity : 0;
~~~

Đây là mã minh họa. Nếu null **thật sự có nghĩa là không có số lượng, xem như 0**, cách này tránh NPE. Nhưng với giao dịch, tồn kho hay dữ liệu quan trọng, “không rõ số lượng” và “số lượng bằng 0” thường không tương đương. Không tự default để cho chương trình tiếp tục mà mất ý nghĩa dữ liệu.

Có thể viết:

~~~java
int count = Objects.requireNonNullElse(quantity, 0);
~~~

với Java 9+ và import `Objects`. Cả hai nhánh của utility trả một `Integer` khác null (nếu fallback đúng), sau đó unboxing an toàn.

### Hướng C: giữ kiểu wrapper cho trạng thái thiếu dữ liệu

~~~java
Integer quantity = lookupQuantity();
if (quantity == null) {
    showMissingQuantity();
} else {
    showQuantity(quantity.intValue());
}
~~~

Đây là mã minh họa; các method cần định nghĩa. Nếu trạng thái “missing” là một trường hợp hợp lệ, không nên ép chuyển ngay sang primitive rồi mới xử lý lỗi.

Với `Boolean`, một phép kiểm tra như `Boolean.TRUE.equals(flag)` có thể diễn giải null thành false, **nhưng chỉ nếu hợp đồng muốn vậy**. Nếu null biểu thị “unknown”, nên mô hình hóa ba trạng thái một cách rõ ràng.

## 9. NPE do API trả null và tác động của collection

Không phải NPE nào cũng xuất hiện từ **tham số đầu vào**. Giá trị null có thể đi vào qua:

- Một factory hoặc repository trả null để biểu thị “không tìm thấy”.
- Một method getter của object chưa được khởi tạo đầy đủ.
- Một phần tử của array hoặc collection.
- Một key không tồn tại trong map.
- Một API bên ngoài có contract cho phép null.
- Một đoạn code chuyển đổi dữ liệu mà không xác thực giá trị được trả về.

Ví dụ:

~~~java
Integer current = counters.get("login");
int next = current + 1; // NPE nếu current null.
~~~

Đây là đoạn minh họa; `counters` cần là map phù hợp. Kiểu `Map<String,Integer>` không có nghĩa giá trị đọc từ map luôn là một Integer khác null. Mỗi ranh giới dữ liệu cần quyết định rõ khi không tìm thấy khóa hoặc khi giá trị null.

**Mẫu thiết kế tốt hơn:** Nếu không tồn tại khóa, câu lệnh có thể cố tình dùng 0 như default; nếu null biểu thị lỗi dữ liệu, hãy báo lỗi thay vì mặc định. Đừng bắt NPE ở đoạn cộng để suy ra “không tìm thấy số đếm”; điều đó có thể che một NPE khác xuất phát từ bản thân map null hoặc logic ngoài dự kiến.

## 10. Helpful NullPointerException messages từ Java hiện đại

Từ JEP 358 (*Helpful NullPointerExceptions*, được đưa vào JDK 14), các JVM hỗ trợ có thể bổ sung **thông tin mô tả dereference nào là null** khi NPE được JVM tạo ra tại các vị trí có thể phân tích bytecode.

Ví dụ thông báo có thể giống:

~~~text
Cannot invoke "String.length()" because "name" is null
~~~

Đây là **chuỗi minh họa**, không phải stdout bắt buộc của chương trình chính. Một trường hợp method chain có thể được mô tả theo kết quả getter trả null, như:

~~~text
Cannot invoke "Address.getCity()" because the return value of "Customer.getAddress()" is null
~~~

Tên class, thông điệp, đường dẫn, biến cục bộ được khôi phục và ngôn ngữ hiển thị có thể khác nhau tùy bản build, bytecode và JVM. Thậm chí `getMessage()` vẫn có thể là null với một số NPE.

### Vì sao có khi không có helpful message?

- NPE **được tạo hoặc ném tường minh**, như `new NullPointerException("manual")`, có message do code cung cấp; cơ chế thông báo diễn giải tự động không áp dụng giống cách JVM tạo lỗi dereference.
- NPE được tạo tại thời điểm/cơ chế mà JVM không có dữ liệu bytecode phù hợp để phân tích.
- Một số cấu hình JVM có thể tắt hỗ trợ thông điệp chi tiết.
- Tối ưu và công cụ biên dịch có thể ảnh hưởng thông tin được ghi trong stack trace.

Với HotSpot/Java 17, có thể kiểm tra hoặc điều chỉnh lựa chọn liên quan thông qua flag VM `-XX:+ShowCodeDetailsInExceptionMessages` và lựa chọn tắt tương ứng `-XX:-ShowCodeDetailsInExceptionMessages` khi JVM hỗ trợ. Không nên giả định flag tương tự tồn tại trên mọi nhà cung cấp JVM.

**Không viết unit test phụ thuộc nguyên văn helpful NPE message.** Hãy test loại lỗi, hành vi và message do API của chính bạn quy định; dùng helpful message như công cụ chẩn đoán bổ sung.

## 11. Cách debug NullPointerException có hệ thống

Khi thấy stack trace báo NPE:

1. **Tìm frame đầu tiên thuộc code của bạn**, file, số dòng và method tương ứng. NPE có thể phát sinh trong thư viện, nhưng nguyên nhân lại do input không hợp lệ ở caller.
2. **Đọc toàn bộ biểu thức ở dòng lỗi**: có method chain, field, mảng, unboxing hoặc result từ API không?
3. **Xác định từng tham chiếu có thể null**: receiver, getter result, phần tử mảng, wrapper Integer/Boolean, tham số, return value.
4. **Xem helpful NPE message nếu có**, nhưng không coi nó thay thế việc đọc source và xác minh dữ liệu thực.
5. **Kiểm tra đường đi của giá trị** từ input, map, repository, JSON parser, API bên ngoài tới nơi dereference.
6. **Xác định hợp đồng nullability**: null hợp lệ, thiếu dữ liệu hay caller vi phạm tiền điều kiện?
7. **Sửa ở điểm chịu trách nhiệm**: validate sớm, trả model đúng, hoặc xử lý nhánh thiếu dữ liệu có chủ đích.
8. **Thêm test** cho input null, giá trị hợp lệ, return null, empty collection, wrapper null và các nhánh nghiệp vụ quan trọng.

Nếu một dòng chứa:

~~~java
int total = repository.findOrder(id).getItems().size();
~~~

thì NPE có thể phát sinh do `repository` null, `findOrder(id)` trả null hoặc `getItems()` trả null. Nếu `getItems()` trả collection hợp lệ nhưng rỗng, `size()` thường trả 0; đó không phải NPE. Nếu truy cập tiếp đến field/element null lại là câu chuyện khác.

Đây là dòng **minh họa**, yêu cầu class/method tương ứng; không thể suy nguyên nhân chính xác chỉ bằng cách thấy từ `size()`.

### Vì sao không nên sửa bằng catch NPE rồi trả kết quả mặc định?

~~~java
// ANTI-PATTERN: dễ che bug, không nên sao chép làm giải pháp chung.
try {
    return repository.getCustomer(id).getName();
} catch (NullPointerException ex) {
    return "(unknown)";
}
~~~

Đây là đoạn minh họa trong method trả String, với các biến/method cần định nghĩa. Nó có thể che **nhiều nguyên nhân khác nhau**: repository null, customer null, hay bug xảy ra bên trong getter. Mặc định trả giá trị có thể khiến hệ thống báo thành công dù dữ liệu bị hỏng.

Thay vào đó, kiểm tra **đúng điều kiện null đã được cho phép**:

~~~java
Customer customer = repository.getCustomer(id);
if (customer == null) {
    return "(unknown)"; // Chỉ khi contract cho phép thiếu customer.
}
return Objects.requireNonNull(
        customer.getName(), "customer.name must not be null");
~~~

Đây là đoạn minh họa, cần định nghĩa `Customer`, `repository`, `id` và import Objects. Chính sách là: “không có customer” được chấp nhận, nhưng “có customer mà name null” là lỗi contract. Việc phân biệt này có giá trị lớn hơn một catch NPE rộng.

## 12. NPE có phải luôn là lỗi của caller?

Không thể kết luận chỉ dựa vào class NPE.

Một số tình huống:

| Tình huống | Ai có thể cần sửa? | Gợi ý điều tra |
| --- | --- | --- |
| Caller truyền null vào param đã tài liệu hóa non-null | Caller | Validate tại ranh giới; sửa nơi gọi |
| API cho phép null, implementation dereference không kiểm tra | Implementation | Bổ sung nhánh null phù hợp |
| Getter trả null trái invariant đã cam kết | Tầng tạo/duy trì object | Sửa invariant, khởi tạo và test |
| Map trả null vì thiếu key, caller unbox | Hợp đồng tích hợp hai phía | Quy định cách biểu diễn missing và default |
| Boolean wrapper null do trạng thái “unknown” | Thiết kế domain | Không ép thành primitive trước khi quyết định |
| Một bug nội bộ làm field chưa được khởi tạo | Code sở hữu trạng thái | Sửa logic, không chỉ catch ở UI |

**NPE là tín hiệu về một thao tác không hợp lệ với null**, không tự chỉ ra trách nhiệm cuối cùng. Để xác định trách nhiệm, cần biết **hợp đồng ở ranh giới** và luồng dữ liệu.

### NPE hay IllegalArgumentException khi param null?

Trong Java API có những phương thức dùng `NullPointerException` khi tham chiếu null bị cấm, và có những thư viện chọn `IllegalArgumentException` cho đầu vào sai hợp đồng. Không có một câu trả lời duy nhất dùng đúng cho mọi API.

Gợi ý thực hành:

- Nếu null bị cấm và bạn muốn fail fast, `Objects.requireNonNull` cung cấp một cách diễn đạt trực tiếp bằng NPE.
- Nếu giá trị khác null nhưng sai quy tắc nghiệp vụ, có thể chọn `IllegalArgumentException` hoặc exception nghiệp vụ riêng.
- Nếu null là trường hợp hợp lệ, không nên ném NPE; thực hiện nhánh null theo contract.
- Trong API công khai, **nhất quán, tài liệu hóa rõ và kiểm thử** quan trọng hơn tranh luận tuyệt đối về một class exception.

## 13. Các lỗi thiết kế thường dẫn đến NPE

1. **Trả null nhưng không ghi contract**, khiến caller mặc định rằng kết quả luôn có object.
2. **Unbox wrapper không có null-check**, đặc biệt khi đọc từ Map, ORM hoặc JSON.
3. **Dùng `Boolean` như `boolean`**, quên trạng thái thứ ba có thể là null.
4. **Chỉ kiểm tra object cha**, bỏ qua getter trả null ở bước tiếp theo.
5. **Gọi `value.equals(expected)` khi value có thể null**, thay vì áp dụng cách so sánh null-safe có ý nghĩa.
6. **Tự động default null thành 0/false/rỗng**, làm mất trạng thái thiếu dữ liệu quan trọng.
7. **Cứ bắt NPE rồi retry**: NPE thường liên quan invariant/contract, retry mù có thể không giải quyết bug.
8. **Chỉ đọc phần đầu của method chain trong lỗi**; thực tế có thể là return value giữa chuỗi bị null.
9. **Không kiểm tra result từ Map** trước khi dùng trong phép toán primitive.
10. **Nhầm NPE với ArrayIndexOutOfBoundsException** khi truy cập mảng.
11. **Nhầm `Optional.get()` trên empty với NPE**; đó thường là `NoSuchElementException`.
12. **Tưởng `Optional.of(null)` an toàn**, trong khi API ném NPE; dùng `ofNullable` khi null được phép.
13. **So sánh `Integer == 0` mà quên unboxing**, dù trước đó đã viết mã “tránh dấu chấm”.
14. **Viết test so nguyên văn helpful NPE message**, dễ phụ thuộc JVM/build.
15. **Chèn hàng loạt `Objects.requireNonNull` vào mọi chỗ**, nhưng không xác định null hợp lệ ở đâu, dẫn tới fail fast sai yêu cầu nghiệp vụ.
16. **Nuốt lỗi bằng `catch (Exception)` rồi trả success**, làm bug khó phát hiện và trạng thái không nhất quán.
17. **Tin rằng annotation `@NonNull` luôn được javac kiểm tra sẵn**, trong khi nhiều annotation nullness cần static analyzer/IDE/toolchain riêng.
18. **Không làm test cho giá trị null ở các ranh giới**: constructor, service, parser, repository, DTO.

## 14. Nullness annotations và giới hạn của compiler Java

Java 17 có hệ thống kiểu tĩnh phân biệt **primitive** và **reference**, nhưng ngôn ngữ Java chuẩn không tự coi mọi `String` là non-null. Vì vậy `String name` **không bảo đảm** runtime có giá trị khác null.

Các annotation nullness như `@Nullable`, `@NonNull` hoặc các annotation từ thư viện/framework có thể giúp công cụ phân tích và người đọc hiểu contract. Nhưng:

- Chúng đến từ nhiều chuẩn/thư viện khác nhau và có mức hỗ trợ khác nhau.
- Việc thêm annotation không tự bảo đảm runtime không có NPE.
- `javac` chuẩn không mặc định thực hiện kiểm tra nullness tổng quát cho mọi annotation tùy ý.
- IDE, NullAway, Checker Framework hoặc công cụ phân tích tương tự có thể đưa ra cảnh báo khi được cấu hình; cần hiểu chính xác toolchain dự án.
- Runtime validation vẫn cần thiết khi dữ liệu đến từ nguồn không đáng tin hoặc hợp đồng đòi fail fast.

Ví dụ khai báo `@NonNull String value` chỉ có ý nghĩa cụ thể khi annotation và các công cụ theo dự án được xác định. Đừng tự kết luận một tham số không thể null chỉ vì nhìn thấy một tên annotation.

## 15. Những điều dễ nhầm về Java runtime

### NPE khác lỗi biên dịch

~~~java
String name = null;
int size = name.length();
~~~

Đây là **mã biên dịch hợp lệ**: compiler kiểm tra kiểu và method `String.length()` tồn tại, nhưng không từ chối chỉ vì một tham chiếu runtime bằng null. Lỗi phát sinh **khi thực thi** lời gọi.

Ngược lại, `int number = null;` không biên dịch vì giá trị null không thể được gán trực tiếp cho primitive int. Hai lỗi thuộc hai nhóm khác nhau.

### null không phải object

Không có một đối tượng Java thông thường tên là “null object” để gọi method instance trên nó. `null` là một giá trị tham chiếu đặc biệt. `((Object) null) instanceof Object` trả false; việc cast null sang kiểu tham chiếu thích hợp không tự tạo object mới.

### Không phải lời gọi method nào với null cũng ném NPE tại điểm gọi

~~~java
static void acceptNullable(String value) {
    System.out.println(value == null);
}

acceptNullable(null);
~~~

Đoạn minh họa có thể chạy và in `true` nếu được đặt đúng trong một class/method. Lời gọi `acceptNullable(null)` hợp lệ, vì không có dereference null ở caller; method xử lý null một cách có chủ đích.

Đó là sự khác biệt giữa **truyền null cho tham số** và **gọi method trên receiver null**.

### NPE không chỉ xảy ra trong code do bạn viết

Library có thể chủ động validate và ném NPE nếu một API không chấp nhận null. Ví dụ `Objects.requireNonNull`, `Optional.of(null)` và nhiều factory trong thư viện chuẩn có quy tắc riêng. Hãy đọc Javadoc thay vì dự đoán rằng mọi API đều bỏ qua null hoặc luôn ném cùng kiểu lỗi.

## 16. Bài tập dự đoán hành vi

**Câu 1.** Vì sao hai đoạn sau có kết quả khác?

~~~java
Integer n = null;
boolean a = n == null;
boolean b = n == 0;
~~~

*Đáp án:* `n == null` là so sánh tham chiếu, trả true. `n == 0` yêu cầu unboxing sang int nên ném NPE; biến `b` không được gán giá trị.

**Câu 2.** `Boolean flag = null; if (flag) { ... }` gặp lỗi gì?

*Đáp án:* NPE do Boolean null phải unbox sang boolean trong biểu thức điều kiện.

**Câu 3.** `String[] names = new String[1]; String first = names[0];` có ném NPE không?

*Đáp án:* Không; mảng đã được tạo và đọc phần tử null là hợp lệ. Nhưng `first.length()` sẽ ném NPE.

**Câu 4.** Khi `User user = null;`, `user.email` gây lỗi gì?

*Đáp án:* NPE vì dereference receiver null để đọc instance field.

**Câu 5.** Khi `User user = new User(); user.email == null;`, đọc `user.email` có tự ném NPE không?

*Đáp án:* Không. Đọc một field từ object hợp lệ có thể trả null; dereference giá trị null được trả về mới gây NPE.

**Câu 6.** `"ready".equals(null)` có ném NPE không?

*Đáp án:* Không; receiver literal khác null và equals nhận argument null, trả false.

**Câu 7.** `Objects.equals(null, null)` trả gì?

*Đáp án:* True theo hợp đồng của `Objects.equals`.

**Câu 8.** `Objects.requireNonNull(name, "name required")` khi name null có hành vi gì?

*Đáp án:* Ném NPE tại bước kiểm tra với message do code cung cấp; không tiếp tục dùng name.

**Câu 9.** `Optional.of(null)` và `Optional.ofNullable(null)` khác nhau thế nào?

*Đáp án:* `of(null)` ném NPE; `ofNullable(null)` trả Optional rỗng.

**Câu 10.** Khi method `findUser()` trả null, `findUser().getName()` có thể ném gì?

*Đáp án:* NPE khi gọi `getName()` trên return value null.

**Câu 11.** Tại sao `Map<String, Integer>` không bảo đảm `int n = map.get(key);` an toàn?

*Đáp án:* `get(key)` có thể trả null nếu thiếu key hoặc có mapping null; auto-unboxing null sang int gây NPE.

**Câu 12.** Có nên sửa tất cả NPE bằng cách catch rồi trả chuỗi rỗng?

*Đáp án:* Không. Điều đó có thể che bug hoặc mất trạng thái dữ liệu; phải tìm hợp đồng nullability và sửa ở ranh giới chịu trách nhiệm.

**Câu 13.** Helpful NullPointerException message có nên là hợp đồng JSON trả cho client?

*Đáp án:* Không. Nội dung có thể phụ thuộc JVM/build, tiết lộ chi tiết code và không phải thông điệp nghiệp vụ ổn định.

**Câu 14.** Nếu một method chỉ nhận tham số `String text` và caller truyền null, lời gọi method có tự gây NPE trước khi vào thân không?

*Đáp án:* Không chỉ vì argument null. Nếu thân method hoặc validation yêu cầu non-null, khi đó hành vi phụ thuộc code/API được gọi.

## 17. Checklist thiết kế và kiểm thử

Khi review một method có nguy cơ NPE, tự hỏi:

1. **Input nào có thể null?** Method parameter, field, return value, element, map value, wrapper.
2. **Null có được phép theo hợp đồng không?** Nếu không, validate sớm.
3. **Điểm dereference đầu tiên nằm ở đâu?** Gọi method, field, mảng, unboxing, API không nhận null.
4. **Có wrapper primitive nào đang được implicit unbox không?** Đặc biệt `Integer` và `Boolean`.
5. **Giá trị mặc định có đúng nghiệp vụ không?** Đừng chọn 0/false/rỗng tùy tiện.
6. **API có kết quả nullable?** Nếu có, caller đã xử lý nhánh thiếu chưa?
7. **Các collection có thể chứa null không?** Kiểm tra hợp đồng cụ thể.
8. **Có dùng null-safe equals/instanceof đúng chỗ không?** Không lạm dụng khi cần kiểm tra invariant.
9. **Exception được log có đầy đủ stack trace không?** Đừng chỉ in `ex.getMessage()`.
10. **Test có tách giá trị null, non-null, empty, blank và invalid không?** Đây là các trường hợp khác nhau.
11. **Có static analyzer hỗ trợ nullness không?** Sử dụng nếu có, nhưng không coi annotation như runtime guarantee.
12. **Có đang bắt và nuốt NullPointerException không?** Chỉ catch ở ranh giới có chính sách rõ, tránh che lỗi lập trình.

Một bộ test tối thiểu cho phương thức nhập dữ liệu thường cần: đầu vào hợp lệ, tham chiếu null, chuỗi rỗng, chuỗi toàn khoảng trắng, trường nested nullable, wrapper null và dữ liệu trả về từ repository không tìm thấy. Những tình huống cụ thể phụ thuộc contract của hệ thống.

## 18. Tài liệu chính thức Java 17

- [Java SE 17 API – NullPointerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): loại lỗi và ví dụ tình huống chương trình dùng null không hợp lệ.
- [Java SE 17 API – Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull`, `equals`, `requireNonNullElse` và các utility liên quan.
- [JLS Java SE 17 mục 5.1.8 – Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): unboxing wrapper và quy tắc NPE khi giá trị null.
- [JLS Java SE 17 mục 15.12.4 – Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): điều kiện thực thi method invocation và receiver.
- [JLS Java SE 17 mục 15.11 – Field Access Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.11): đánh giá truy cập field, bao gồm trường hợp receiver null.
- [JLS Java SE 17 mục 15.10.4 – Run-Time Evaluation of Array Access Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.4): truy cập array và điều kiện lỗi.
- [JLS Java SE 17 mục 14.18 – The throw Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): ngoại lệ khi biểu thức được throw có giá trị null.
- [JEP 358 – Helpful NullPointerExceptions](https://openjdk.org/jeps/358): ngữ nghĩa và giới hạn của thông điệp mô tả NPE do JVM tạo.
- [Java SE 17 API – Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): phân biệt `of`, `ofNullable` và Optional rỗng.

**Kết luận:** `NullPointerException` là unchecked exception phát sinh khi Java cần tham chiếu khác null nhưng gặp null. Ba nhóm đáng kiểm tra nhất là **dereference**, **unboxing wrapper null**, và **đầu vào/giá trị trả về nullable bị sử dụng trái hợp đồng**. Phòng ngừa đúng cách không phải “chặn mọi null”, mà là định nghĩa rõ **null có nghĩa gì**, validate ở ranh giới chịu trách nhiệm và chỉ dùng default khi hợp đồng thực sự cho phép.