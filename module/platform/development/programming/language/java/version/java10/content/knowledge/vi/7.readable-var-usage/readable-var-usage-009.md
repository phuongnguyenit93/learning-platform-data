# Kiểm tra ảnh hưởng của `var` đến nạp chồng và khả năng thay thế triển khai

**Chủ đề:** Sử dụng `var` rõ ràng — Java 10 trở lên. Mục tiêu của bài là nhận biết khi nào suy luận kiểu cục bộ giúp mã dễ đọc và khi nào nó khiến mã phụ thuộc vào kiểu triển khai cụ thể, đặc biệt trong lời gọi phương thức **nạp chồng** (*overloading*) và khi đổi một implementation sang implementation khác. Quy tắc vẫn áp dụng với Java hiện đại; các ví dụ hoàn chỉnh được kiểm tra bằng `javac --release 10` và chạy trên JDK hiện đại.

## 1. `var` giữ kiểu tĩnh của biểu thức khởi tạo

Với khai báo:

~~~java
var names = new ArrayList<String>();
~~~

trình biên dịch xác định kiểu tĩnh của `names` là **`ArrayList<String>`**. Từ khóa `var` chỉ tiết kiệm việc viết tên kiểu ở bên trái; nó **không có nghĩa** `names` là một biến kiểu động, kiểu `Object` hoặc kiểu interface `List<String>`.

Trong khi đó:

~~~java
List<String> names = new ArrayList<>();
~~~

kiểu tĩnh của biến là **`List<String>`**, dù đối tượng được tạo ra cũng là `ArrayList<String>`. Đây là khác biệt về **hợp đồng mà mã gọi có thể thấy khi biên dịch**.

| Cách khai báo | Kiểu tĩnh của biến | Có thể gán lại một `LinkedList<String>`? | Có thể gọi API riêng `ArrayList`? |
| --- | --- | --- | --- |
| `var list = new ArrayList<String>();` | `ArrayList<String>` | Không | Có, nếu method khả dụng trên `ArrayList` |
| `ArrayList<String> list = new ArrayList<>();` | `ArrayList<String>` | Không | Có |
| `List<String> list = new ArrayList<>();` | `List<String>` | Có | Không, nếu method không thuộc `List` |
| `var list = List.of("a", "b");` | `List<String>` | Có thể gán một `List<String>` khác | Không có API riêng của `ArrayList` |

Một khai báo `var` **không tự động chọn kiểu trừu tượng nhất**. Nếu initializer trả về kiểu interface như `List.of(...)` thì `var` có thể suy luận kiểu interface; nếu initializer có kiểu implementation như `new ArrayList<String>()` thì nó suy luận kiểu implementation. Muốn biết chắc, hãy xem **kiểu tĩnh của biểu thức ở vế phải**.

## 2. Nạp chồng khác với ghi đè

Trước khi xem tác động của `var`, cần phân biệt hai cơ chế:

- **Nạp chồng (*overloading*):** Có nhiều phương thức cùng tên nhưng danh sách tham số khác nhau. Trình biên dịch chọn một chữ ký phù hợp tại **thời điểm biên dịch**, xét tên phương thức, kiểu tĩnh của đối số, chuyển đổi kiểu cho phép, mức độ đặc hiệu và các quy tắc JLS `15.12`. `varargs`, boxing và suy luận generic cũng có thể tham gia tùy lời gọi.
- **Ghi đè (*overriding*):** Một implementation cung cấp cách thực thi khác cho cùng hợp đồng phương thức của lớp cha hoặc interface. Với lời gọi phương thức instance cho phép dynamic dispatch, **implementation thực thi** được chọn theo đối tượng thực tế lúc chạy sau khi chữ ký phương thức đã được xác định.

`var` có thể làm **khác kiểu tĩnh** so với cách khai báo `List<String>`, nên có thể thay đổi **overload được chọn**. Nhưng `var` không sửa thuật toán overload, cũng không tắt cơ chế overriding hay dynamic dispatch.

### Ví dụ minh họa cùng tên phương thức

~~~java
static void inspect(List<String> values) { /* xử lý tổng quát */ }
static void inspect(ArrayList<String> values) { /* xử lý đặc thù ArrayList */ }
static void inspect(LinkedList<String> values) { /* xử lý đặc thù LinkedList */ }
~~~

Ba overload này hợp lệ vì kiểu tham số sau khi xét erasure vẫn khác nhau (`List`, `ArrayList`, `LinkedList`). Với `var a = new ArrayList<String>();`, overload `inspect(ArrayList<String>)` là ứng viên đặc hiệu nhất. Với `List<String> a = new ArrayList<>();`, lời gọi `inspect(a)` chỉ dựa trên kiểu tĩnh `List<String>` để xác định overload, nên chọn `inspect(List<String>)`.

**Không dựa vào việc đối tượng thực tế “vốn là `ArrayList`” để dự đoán overload.** Khi mã đã đi qua biến khai báo là `List<String>`, phương thức overload đặc thù `ArrayList` không được chọn chỉ vì runtime object thuộc `ArrayList`.

## 3. Ví dụ chạy được: đổi implementation làm thay đổi overload

Lưu chương trình sau thành **`VarOverloadDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class VarOverloadDemo {
    static void inspect(List<String> values) {
        System.out.println("overload=List");
    }

    static void inspect(ArrayList<String> values) {
        System.out.println("overload=ArrayList");
    }

    static void inspect(LinkedList<String> values) {
        System.out.println("overload=LinkedList");
    }

    public static void main(String[] args) {
        var concreteA = new ArrayList<String>();
        var concreteB = new LinkedList<String>();
        inspect(concreteA);
        inspect(concreteB);

        List<String> abstraction = new ArrayList<>();
        inspect(abstraction);
        abstraction = new LinkedList<>();
        inspect(abstraction);

        var inferred = new ArrayList<>();
        Object item = "hello";
        inferred.add(item);
        System.out.println("inferred=" + inferred.get(0));
    }
}
~~~

Biên dịch và chạy với JDK hỗ trợ mục tiêu Java 10:

~~~bash
javac --release 10 VarOverloadDemo.java
java VarOverloadDemo
~~~

**Kết quả chính xác:**

~~~text
overload=ArrayList
overload=LinkedList
overload=List
overload=List
inferred=hello
~~~

Phân tích từng lời gọi:

1. `concreteA` có kiểu tĩnh `ArrayList<String>`, nên `inspect(concreteA)` chọn overload `ArrayList`.
2. `concreteB` có kiểu tĩnh `LinkedList<String>`, nên lời gọi cùng tên chọn overload `LinkedList`.
3. `abstraction` có kiểu tĩnh `List<String>`, nên ngay cả khi đối tượng được tạo bằng `new ArrayList<>()`, phương thức được chọn vẫn là `inspect(List<String>)`.
4. Sau `abstraction = new LinkedList<>();`, kiểu của biến vẫn là `List<String>`. Overload được chọn **không đổi**.
5. `inferred` từ `new ArrayList<>()` không có ngữ cảnh phần tử rõ ràng sẽ có kiểu `ArrayList<Object>`. Các lời gọi thêm một `Object` sau đó không khiến trình biên dịch suy luận lại thành `ArrayList<String>`.

**Ý nghĩa thực tế:** Nếu các overload chứa logic khác nhau, thay `new ArrayList<>()` bằng `new LinkedList<>()` trong một khai báo `var` có thể đổi **hành vi được chọn ngay từ biên dịch**. Dùng một kiểu interface tường minh để bảo vệ mã gọi khỏi sự thay đổi overload khi muốn thay implementation mà vẫn giữ hợp đồng.

## 4. `var` làm thay đổi mức độ gắn kết với implementation

Giả sử cần chuyển từ `ArrayList` sang `LinkedList` do đặc điểm của workload hoặc quyết định thiết kế.

### Trường hợp khai báo theo implementation

~~~java
var queue = new ArrayList<String>();
queue.add("A");
// queue = new LinkedList<String>(); // KHÔNG BIÊN DỊCH
~~~

Kiểu của `queue` đã cố định là `ArrayList<String>`. `LinkedList<String>` không kế thừa `ArrayList<String>`; cả hai cùng triển khai các interface như `List`, nhưng điều đó **không làm chúng gán trực tiếp cho nhau được**.

Nếu sửa initializer thành `new LinkedList<String>()`, bản thân mã có thể biên dịch khi chỉ dùng các API chung, nhưng **kiểu tĩnh được suy luận lại thành `LinkedList<String>`**. Khi đó overload đã dùng `ArrayList` có thể đổi sang overload `LinkedList` hoặc `List`. Các method riêng của `ArrayList` cũng có thể không còn dùng được.

Ví dụ minh họa:

~~~java
var values = new ArrayList<String>();
values.ensureCapacity(100); // method của ArrayList

// Nếu đổi riêng constructor thành new LinkedList<String>(),
// câu gọi ensureCapacity(100) không còn biên dịch.
~~~

Đây là **đoạn minh họa trong phương thức**, không có `main` độc lập.

### Trường hợp khai báo theo hợp đồng interface

~~~java
List<String> queue = new ArrayList<>();
queue.add("A");
queue = new LinkedList<>();
queue.add("B");
~~~

Mã gọi chỉ dựa vào hợp đồng `List<String>`. Cả hai implementation đều phù hợp với kiểu khai báo, nên việc đổi instance là hợp lệ. Các overload nhận `List<String>` cũng được chọn nhất quán qua biến này.

**Giới hạn của khả năng thay thế:** Cùng triển khai `List` không có nghĩa mọi implementation đều giống nhau về hiệu năng, thứ tự xử lý trong mọi trường hợp, mutability hoặc những đặc tính ngoài hợp đồng. Ví dụ `List.of(...)` tạo danh sách không thể thêm/xóa; `ArrayList` và `LinkedList` ở ví dụ trên cho phép `add`. Cần kiểm tra cả **hợp đồng hành vi**, không chỉ việc biên dịch.

## 5. `var` và kiểu đối số cũng có thể ảnh hưởng overload

Overload được chọn dựa vào **kiểu tĩnh của đối số**, kể cả đối số là biến `var`. Điều này không giới hạn ở collections.

Chương trình **`VarStaticTypeDemo.java`**:

~~~java
public class VarStaticTypeDemo {
    static void view(Object value) {
        System.out.println("type=Object");
    }

    static void view(CharSequence value) {
        System.out.println("type=CharSequence");
    }

    static void view(String value) {
        System.out.println("type=String");
    }

    public static void main(String[] args) {
        var concrete = "java";
        CharSequence general = "java";

        view(concrete);
        view(general);

        var primitive = 5;
        int sum = primitive + 2;
        System.out.println("sum=" + sum);
    }
}
~~~

Chạy:

~~~bash
javac --release 10 VarStaticTypeDemo.java
java VarStaticTypeDemo
~~~

Stdout:

~~~text
type=String
type=CharSequence
sum=7
~~~

`concrete` được suy luận là `String`, nên chọn overload `view(String)`; `general` có kiểu tĩnh `CharSequence` nên chọn `view(CharSequence)`, dù cả hai cùng tham chiếu đến chuỗi Java ở runtime.

Trong ví dụ cuối, `var primitive = 5;` suy luận ra `int`, không phải `Integer`. Khi overload có phiên bản primitive, boxed và các phương thức với kiểu số khác nhau, **phân biệt kiểu primitive và wrapper** có thể quan trọng. Hãy xét kiểu tĩnh trước khi dự đoán kết quả nạp chồng.

## 6. Overriding vẫn phụ thuộc implementation thực tế

Để không nhầm với overload, xét một interface có cùng chữ ký phương thức được implement khác nhau. Đây là chương trình độc lập **`VarDispatchDemo.java`**:

~~~java
public class VarDispatchDemo {
    interface Formatter {
        String format(String text);
    }

    static final class Brackets implements Formatter {
        @Override
        public String format(String text) {
            return "[" + text + "]";
        }
    }

    static final class Uppercase implements Formatter {
        @Override
        public String format(String text) {
            return text.toUpperCase();
        }
    }

    static void print(Formatter formatter) {
        System.out.println("dispatch=" + formatter.format("java"));
    }

    public static void main(String[] args) {
        Formatter formatter = new Brackets();
        print(formatter);

        formatter = new Uppercase();
        print(formatter);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 VarDispatchDemo.java
java VarDispatchDemo
~~~

Kết quả:

~~~text
dispatch=[java]
dispatch=JAVA
~~~

Phương thức được gọi luôn là **`Formatter.format(String)` theo hợp đồng**, nhưng implementation thực thi tương ứng là `Brackets` rồi `Uppercase`. Đó là *dynamic dispatch* của phương thức được override.

So sánh:

| Câu hỏi | Overloading | Overriding |
| --- | --- | --- |
| “Trong các phương thức cùng tên, chữ ký nào được gọi?” | Phân giải chủ yếu tại biên dịch theo kiểu tĩnh và quy tắc áp dụng phương thức | Không phải câu hỏi cốt lõi của overriding |
| “Cách thực thi của chữ ký instance đã chọn nằm ở lớp nào?” | Overload resolution không tự quyết định runtime implementation | Có thể quyết định khi chạy theo đối tượng thực tế |
| `var` ảnh hưởng ở đâu? | Có thể làm đối số/receiver có kiểu tĩnh cụ thể hơn so với khai báo interface tường minh | Không thay đổi các quy tắc dynamic dispatch hiện có |

Trong thiết kế API, tránh sử dụng overload cho các implementation cụ thể nếu người dùng kỳ vọng mọi `List` có cùng cách xử lý. Khi muốn đa hình theo implementation, interface với phương thức override là cơ chế rõ ràng hơn.

## 7. Kiểm tra kiểu suy luận của generics trước khi gọi overload

`var` kết hợp với toán tử diamond `<>` có thể tạo kiểu khác ý định:

~~~java
var names = new ArrayList<>();  // ArrayList<Object>
names.add("An");
~~~

Giả sử có phương thức:

~~~java
static void consume(List<String> names) {
    System.out.println(names.size());
}
~~~

Thì `consume(names)` **không biên dịch**: `ArrayList<Object>` không phải `List<String>`. Thêm một chuỗi sau khai báo không thay đổi đối số kiểu generic đã được suy luận. Điều này cũng có thể khiến một overload mong muốn không áp dụng được, hoặc khiến một overload tổng quát hơn được chọn, tùy bộ overload cụ thể.

Muốn giữ kiểu phần tử `String` và công khai hợp đồng chung, chọn:

~~~java
List<String> names = new ArrayList<>();
consume(names);
~~~

Nếu vẫn muốn `var` thì cung cấp đối số kiểu từ initializer:

~~~java
var names = new ArrayList<String>();
consume(names);
~~~

**Đặc biệt lưu ý:** không thể nạp chồng hai phương thức chỉ khác đối số generic như `consume(List<String>)` và `consume(List<Integer>)`, vì cả hai có cùng *erasure* của tham số (`List`). Khi thiết kế overload, phương thức phải có chữ ký phân biệt hợp lệ; việc dùng `var` ở nơi gọi không loại bỏ ràng buộc này.

## 8. `var` không cung cấp target type cho một lambda đứng riêng

Khai báo dưới đây **không biên dịch**:

~~~java
// var operation = value -> value.trim(); // LỖI: lambda cần target functional interface
~~~

Với lambda, kiểu tĩnh của biểu thức cần được xác định qua **functional interface đích**. `var` ở khai báo biến cục bộ không tự cung cấp một target type để suy luận tham số lambda. Có thể viết:

~~~java
java.util.function.Function<String, String> operation = value -> value.trim();
~~~

Cần phân biệt tình huống này với `var result = someMethod(...)`: trong lời gọi method, bộ overload và quy tắc của biểu thức đối số đã xác định kiểu trả về của initializer theo ngữ cảnh áp dụng; `var` tiếp nhận kiểu kết quả đó. Không nên suy luận rằng thay một khai báo tường minh bằng `var` **luôn luôn** giữ nguyên target typing cho mọi loại biểu thức khởi tạo, nhất là các biểu thức *poly* như lambda và method reference.

Một nguyên tắc an toàn khi refactor:

1. Nếu initializer là một đối tượng cụ thể, xác định chính xác kiểu suy luận của `var`.
2. Nếu initializer phụ thuộc ngữ cảnh kiểu đích, kiểm tra cú pháp có còn hợp lệ và compiler còn chọn cùng overload hay không.
3. Không đổi `List<String> names = new ArrayList<>();` thành `var names = new ArrayList<>();` rồi giả định generic vẫn là `String`.

## 9. Bảng kiểm tra khi thay implementation

Giả sử yêu cầu là “đổi từ `ArrayList` sang `LinkedList` mà không thay đổi hợp đồng sử dụng”. Kiểm tra các điểm sau:

| Cần kiểm tra | Rủi ro khi dùng `var` | Cách xử lý |
| --- | --- | --- |
| Kiểu biến sau initializer | Có thể là lớp triển khai cụ thể | Dùng kiểu interface tường minh như `List<String>` nếu đó là hợp đồng cần giữ |
| Overload được chọn | Đổi `ArrayList` sang `LinkedList` có thể khiến một overload khác phù hợp hơn | Đảm bảo lời gọi đi qua kiểu interface chung; xem lại overload của API |
| Các method riêng implementation | `ensureCapacity` chỉ có ở `ArrayList` | Hạn chế gọi API riêng nếu muốn thay thế implementation |
| Generic type argument | `new ArrayList<>()` sau `var` có thể suy luận `Object` | Ghi rõ kiểu generic hoặc dùng type target tường minh |
| Khả năng gán lại | `var x = new ArrayList<String>();` không gán được `LinkedList<String>` | Khai báo `List<String> x` từ đầu |
| Runtime behavior | Đổi implementation có thể đổi đặc tính bộ nhớ, thao tác, hỗ trợ thay đổi hoặc hiệu năng | Kiểm tra yêu cầu nghiệp vụ và hiệu năng thực tế của từng implementation |
| Kiểm thử | Chỉ nhìn code compile không chứng minh overload chọn đúng và hành vi giữ nguyên | Dùng thử nghiệm/kiểm thử trên trường hợp có các overload gần nhau |

### Quy trình review thực tế

- Tìm các biến `var` được khởi tạo bởi `new SomeImplementation<...>()` và các phương thức nhận các biến này làm đối số.
- Trong IDE, xem **kiểu suy luận** của biến và **chữ ký overload thực sự được chọn**. Khi cần, dùng các phép gán tường minh hoặc tạo chương trình nhỏ để kiểm tra với `javac`.
- Kiểm tra API được gọi có overload khác biệt theo implementation (`List` so với `ArrayList`/`LinkedList`) không.
- Nếu implementation là chi tiết nội bộ và hợp đồng là interface, thay khai báo bằng kiểu interface rõ ràng; kiểm tra lại compilation, test hành vi và các thao tác runtime quan trọng.
- Không thay đổi kiểu khai báo máy móc chỉ để bỏ `var`: nếu initializer đã trả về interface thích hợp và kiểu suy luận rõ ràng, `var` vẫn là lựa chọn tốt.

## 10. Các lỗi hay gặp và cách nhận diện

**Lỗi 1 — Cho rằng `var` giống `Object` hoặc một kiểu cha tùy ý.** Thực tế Java chọn kiểu suy luận cụ thể theo initializer. `var list = new ArrayList<String>();` tương đương về kiểu biến với `ArrayList<String> list = new ArrayList<>();`.

**Lỗi 2 — Tưởng overload được chọn theo runtime implementation.** Với `List<String> list = new ArrayList<>();`, overload nhận `ArrayList<String>` không tự được ưu tiên. Overload được phân giải dựa vào kiểu tĩnh `List<String>`.

**Lỗi 3 — Tưởng thay implementation chỉ ảnh hưởng hiệu năng.** Với biến `var`, thay initializer có thể đổi kiểu tĩnh, overload áp dụng và khả năng truy cập method. Những thay đổi này có thể ảnh hưởng compilation hoặc kết quả khi chạy.

**Lỗi 4 — Nhầm overload với override.** Cùng tên `inspect(List)` và `inspect(ArrayList)` là hai overload; cùng `Formatter.format(String)` với hai implementation là override/dynamic dispatch.

**Lỗi 5 — Dùng `var` với diamond rỗng mà bỏ mất generic.** `var x = new ArrayList<>();` có thể suy luận `ArrayList<Object>`, khiến lời gọi cần `List<String>` không hợp lệ.

**Lỗi 6 — Nghĩ `var` chỉ đổi cú pháp, nên refactor không cần kiểm tra.** `var` không thay đổi ngữ nghĩa nếu nó giữ đúng cùng **kiểu tĩnh**, nhưng thay thế một khai báo interface tường minh bằng `var` thường **không giữ cùng kiểu** khi vế phải là lớp triển khai cụ thể.

## 11. Tự kiểm tra

1. Với `var items = new ArrayList<String>();` và hai overload `handle(List<String>)`, `handle(ArrayList<String>)`, overload nào được chọn khi gọi `handle(items)`?
2. Nếu đổi sang `List<String> items = new ArrayList<>();` thì overload nào được chọn?
3. Khi `List<String> items` được gán lại từ `ArrayList` sang `LinkedList`, overload được chọn có thay đổi theo runtime class không?
4. Vì sao `var items = new ArrayList<String>(); items = new LinkedList<String>();` không biên dịch?
5. Trong ví dụ `VarDispatchDemo`, tại sao `formatter.format("java")` cho hai kết quả khác nhau dù biến đều khai báo là `Formatter`?
6. Vì sao `var names = new ArrayList<>();` không phù hợp với một method yêu cầu `List<String>`?
7. Khi nào nên ưu tiên kiểu interface tường minh thay cho `var`?

**Đáp án:** (1) `handle(ArrayList<String>)`; (2) `handle(List<String>)`; (3) không, overload dựa vào kiểu tĩnh `List<String>`; (4) `var` suy luận `ArrayList<String>`, không gán được `LinkedList<String>`; (5) dynamic dispatch chọn implementation override của đối tượng thực; (6) suy luận thành `ArrayList<Object>` vì thiếu thông tin generic; (7) khi cần ổn định hợp đồng, hỗ trợ thay thế implementation hoặc tránh làm lộ các method/overload gắn với lớp cụ thể.

## 12. Tài liệu đối chiếu hiện hành

- **JEP 286 — Local-Variable Type Inference (Java 10):** https://openjdk.org/jeps/286
- **Java Language Specification `14.4 — Local Variable Declarations:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4
- **Java Language Specification `15.12 — Method Invocation Expressions:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12
- **Java Language Specification `8.4.9 — Overloading:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.9
- **Java Language Specification `8.4.8.1 — Overriding:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.1

Các khái niệm này là các quy tắc ngôn ngữ hiện còn được dùng trong Java; khi áp dụng vào dự án cụ thể, luôn kiểm tra mức source Java và các overload thực sự có trong API của dự án.