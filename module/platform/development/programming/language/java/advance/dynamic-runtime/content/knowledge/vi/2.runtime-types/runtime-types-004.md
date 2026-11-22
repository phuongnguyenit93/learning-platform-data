# 2.4 Nhận diện lớp thành viên, lớp cục bộ, lớp vô danh và lớp ẩn

Trong Java, hai đối tượng đều có thể triển khai cùng một interface nhưng lớp thực tế của chúng được khai báo theo những cách rất khác nhau. Khi đọc stack trace, viết công cụ reflection, xử lý bytecode hoặc tìm hiểu cơ chế sinh lớp lúc chạy, cần phân biệt **lớp thành viên (member class)**, **lớp cục bộ (local class)**, **lớp vô danh (anonymous class)** và **lớp ẩn (hidden class)**. Java 17 cung cấp các phép kiểm tra trực tiếp trên `java.lang.Class`, vì vậy không cần đoán loại lớp từ tên có dấu `$`.

## 1. Bản đồ khái niệm

**Vị trí khai báo** trả lời lớp nằm ở đâu trong mã nguồn; **cơ chế định nghĩa lúc chạy** trả lời JVM có công bố lớp theo tên nhị phân bình thường hay không. Đây là hai góc nhìn liên quan nhưng không đồng nhất.

| Loại | Cách xuất hiện điển hình | Đặc điểm cần nhớ | API nhận diện |
| --- | --- | --- | --- |
| Lớp thành viên (`member class`) | Khai báo trực tiếp trong thân một lớp/interface | Có tên, gồm lớp thành viên `static` và lớp thành viên trong (`inner`) không `static` | `Class.isMemberClass()` |
| Lớp cục bộ (`local class`) | Khai báo có tên trong block, thường trong method/constructor | Tên kiểu chỉ dùng trong phạm vi khai báo; có thể dùng biến cục bộ được capture hợp lệ | `Class.isLocalClass()` |
| Lớp vô danh (`anonymous class`) | Biểu thức `new Interface() { ... }` hoặc `new Base() { ... }` | Không tự đặt tên lớp trong source; thường tạo một instance ngay tại biểu thức | `Class.isAnonymousClass()` |
| Lớp ẩn (`hidden class`) | Runtime định nghĩa từ bytecode bằng `MethodHandles.Lookup.defineHiddenClass(...)` | Có đối tượng `Class<?>` nhưng không có tên nhị phân để mã khác tìm qua `Class.forName` | `Class.isHidden()` |

**Điểm phân biệt quan trọng:** “anonymous” là dạng khai báo lớp trong ngôn ngữ Java; “hidden” là thuộc tính của lớp được định nghĩa bằng cơ chế riêng của JVM. Một anonymous class được viết bằng `new ... { }` không tự động là hidden class. Tên bytecode có `$1`, `$2` hoặc ký hiệu bất thường cũng không đủ để kết luận một lớp là anonymous hay hidden.

`Nested class` là khái niệm rộng hơn `member class`: lớp lồng nhau có thể là member, local hoặc anonymous. Trong nhóm member, `static nested class` không cần instance của lớp bao ngoài; `non-static member class` (inner member class) gắn với một instance bao ngoài. Vì vậy “member” và “inner” không phải hai nhãn đồng nghĩa.

## 2. Nhận biết từ cách khai báo và cách tạo đối tượng

Xem chương trình độc lập sau, lưu thành **`NestingAndCapture.java`**:

~~~java
public class NestingAndCapture {
    private final String prefix = "inner=";

    // Member class dạng static.
    static class StaticMember {
        String text() {
            return "static";
        }
    }

    // Member class không static: cần một enclosing instance.
    class InnerMember {
        String text() {
            return prefix + "ok";
        }
    }

    public static void main(String[] args) {
        NestingAndCapture outer = new NestingAndCapture();

        System.out.println(new StaticMember().text());
        System.out.println(outer.new InnerMember().text());

        int multiplier = 3; // effectively final
        // Local class: khai báo có tên ngay trong method.
        class LocalMultiplier {
            int apply(int input) {
                return input * multiplier;
            }
        }
        System.out.println(new LocalMultiplier().apply(4));

        // Anonymous class: lớp được khai báo ở biểu thức new.
        Runnable job = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };
        job.run();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~sh
javac NestingAndCapture.java
java NestingAndCapture
~~~

Kết quả chuẩn:

~~~text
static
inner=ok
12
anonymous
~~~

Cách đọc:

- `StaticMember` và `InnerMember` được khai báo **trực tiếp trong thân** `NestingAndCapture`, nên cả hai đều là **member class**. `StaticMember` có thể tạo bằng `new StaticMember()` trong ngữ cảnh phù hợp, còn `InnerMember` cần `outer.new InnerMember()` nếu không có enclosing instance sẵn có.
- `InnerMember` có thể truy cập trực tiếp trường instance `prefix` của đối tượng bao ngoài. Lớp thành viên `static` không tự mang tham chiếu tới một instance bao ngoài.
- `LocalMultiplier` có tên nhưng chỉ nằm trong phạm vi khối `main`. Nó dùng `multiplier` hợp lệ vì biến đó **final hoặc effectively final**: sau khi gán, không bị gán lại. Nếu thêm `multiplier++` sau đó, trình biên dịch sẽ báo lỗi về capture biến cục bộ.
- Biểu thức `new Runnable() { ... }` khai báo một **anonymous class** triển khai `Runnable` và tạo instance. Nó vẫn có một lớp thực tế khi chạy, dù source không đặt tên kiểu cho lớp ấy.

Để phân biệt **lớp** và **đối tượng**, nhớ rằng `job` là biến có kiểu khai báo `Runnable`, còn `job.getClass()` là lớp runtime thực tế của instance. Tương tự, `getClass()` của một instance lớp con không nhất thiết bằng lớp cha hay interface được viết bên trái phép gán.

### Member class: các thuộc tính dễ nhầm

Một lớp thành viên có thể mang access modifier như `private`, `protected` hoặc `public` tùy ngữ cảnh. `private static class Helper` vẫn là member class. `static` ở đây mô tả **quan hệ với enclosing instance**, không có nghĩa lớp không được tạo đối tượng. Trong ví dụ, `StaticMember` và `InnerMember` cùng cho `isMemberClass() == true`; muốn biết member class có `static` hay không, dùng thêm `Modifier.isStatic(type.getModifiers())`.

Không phải cứ class có tham chiếu tới outer thì là member class: local/anonymous class cũng có thể giữ dữ liệu từ môi trường bao ngoài. Việc compiler sinh trường phụ trợ để capture là chi tiết triển khai, không phải tiêu chuẩn phân loại.

### Local class và anonymous class: phạm vi và capture

Local class có thể khai báo constructor, field và method, đặt tên kiểu trong block và tạo nhiều instance. Anonymous class thích hợp khi cần cài đặt ngắn cho một interface hoặc kế thừa một class ngay trong biểu thức. Chúng cũng có thể capture những local variable `final` hoặc effectively final.

Anonymous class **khác lambda**. Với `Runnable a = new Runnable() { ... };`, `a.getClass().isAnonymousClass()` là `true`. Với `Runnable b = () -> { };`, biểu thức lambda **không phải** là khai báo anonymous class, nên không được dùng `isAnonymousClass()` để nhận diện lambda. Runtime có thể triển khai lambda bằng lớp được sinh/ẩn, nhưng đó là lựa chọn triển khai; API/class name cụ thể của lambda không phải hợp đồng ổn định để ứng dụng phụ thuộc.

## 3. Nhận diện chính xác bằng Reflection

Sử dụng `Class<?>` làm nguồn sự thật. Lưu ví dụ độc lập dưới đây thành **`ClassKinds.java`**:

~~~java
public class ClassKinds {
    static class StaticMember {}
    class InnerMember {}

    static Class<?> localType() {
        class Local {}
        return Local.class;
    }

    static Class<?> anonymousType() {
        return new Runnable() {
            @Override
            public void run() {}
        }.getClass();
    }

    static void show(String label, Class<?> type) {
        System.out.printf(
            "%s: member=%s, local=%s, anonymous=%s, hidden=%s%n",
            label,
            type.isMemberClass(),
            type.isLocalClass(),
            type.isAnonymousClass(),
            type.isHidden()
        );
    }

    public static void main(String[] args) {
        show("static", StaticMember.class);
        show("inner", InnerMember.class);
        show("local", localType());
        show("anonymous", anonymousType());

        System.out.println(
            "declaring=" + StaticMember.class.getDeclaringClass().getSimpleName()
        );
        System.out.println(
            "localMethod=" + localType().getEnclosingMethod().getName()
        );
        System.out.println(
            "anonSimpleEmpty=" + anonymousType().getSimpleName().isEmpty()
        );
    }
}
~~~

~~~sh
javac ClassKinds.java
java ClassKinds
~~~

Kết quả:

~~~text
static: member=true, local=false, anonymous=false, hidden=false
inner: member=true, local=false, anonymous=false, hidden=false
local: member=false, local=true, anonymous=false, hidden=false
anonymous: member=false, local=false, anonymous=true, hidden=false
declaring=ClassKinds
localMethod=localType
anonSimpleEmpty=true
~~~

Ví dụ này kiểm tra cả member `static` và member không `static`, local class, anonymous class. Không có hidden class được tạo trong chương trình này, nên cột `hidden` đều `false`.

### Ý nghĩa của từng API

| API | Câu hỏi nó trả lời | Cạm bẫy |
| --- | --- | --- |
| `isMemberClass()` | Lớp có được khai báo là thành viên của một lớp khác không? | Không phân biệt `static` với instance member. |
| `isLocalClass()` | Đây có phải local class theo khai báo ngôn ngữ không? | Không áp dụng cho class tự sinh lúc chạy chỉ vì nó tồn tại “cục bộ”. |
| `isAnonymousClass()` | Đây có phải anonymous class theo cú pháp Java không? | Không tương đương `isHidden()` hay “lambda”. |
| `isHidden()` | Lớp có được JVM định nghĩa là hidden class không? | Chỉ có từ Java 15; kiểm tra trực tiếp, đừng đoán qua tên. |
| `getDeclaringClass()` | Nếu là member, lớp khai báo nó là lớp nào? | Thường `null` với local/anonymous/top-level. |
| `getEnclosingClass()` | Lớp bao ngoài gần nhất là gì? | Có thể hữu ích với cả member/local/anonymous; khác `getDeclaringClass()`. |
| `getEnclosingMethod()` | Method bao trực tiếp local/anonymous class là gì? | `null` với member; cũng `null` nếu local/anonymous nằm trong initializer hoặc không có enclosing method. |
| `getEnclosingConstructor()` | Constructor bao trực tiếp local/anonymous class là gì? | Không thể dùng thay `getEnclosingMethod()` một cách tổng quát. |
| `getSimpleName()` | Tên ngắn của lớp là gì? | Anonymous class trả chuỗi rỗng; không dùng tên để xác định hidden. |
| `getCanonicalName()` | Lớp có tên canonical theo Java không? | Local, anonymous và hidden class không có canonical name (`null`). |
| `getName()` | Tên mà API `Class` trả về là gì? | Với hidden class, đây **không phải binary name** có thể truyền cho `Class.forName`. |

Nếu đang viết công cụ phân loại, có thể kiểm tra theo thứ tự dễ đọc sau:

~~~java
static String kind(Class<?> type) {
    if (type.isHidden()) return "hidden";
    if (type.isAnonymousClass()) return "anonymous";
    if (type.isLocalClass()) return "local";
    if (type.isMemberClass()) {
        boolean isStatic =
            java.lang.reflect.Modifier.isStatic(type.getModifiers());
        return isStatic ? "static member" : "inner member";
    }
    return "other (top-level, array, primitive, ...)";
}
~~~

**Lưu ý:** hàm trên là một quy tắc **gắn nhãn ưu tiên để hiển thị**, không phải chứng minh rằng mọi thuộc tính runtime đều loại trừ nhau. Với hidden class, hãy ghi nhận `isHidden()` riêng nếu cần phân tích các metadata khác. Nhánh `other` cũng gồm interface top-level, array, primitive và các loại không thuộc bốn mục đang học; không được mặc định nó luôn là top-level class.

### `getDeclaringClass` khác `getEnclosingClass` như thế nào?

- Với `ClassKinds.StaticMember` hay `ClassKinds.InnerMember`, hai API đều dẫn tới `ClassKinds.class`.
- Với `Local` được khai báo trong `localType()`, `getEnclosingClass()` là `ClassKinds.class` nhưng `getDeclaringClass()` là `null`; `getEnclosingMethod().getName()` là `"localType"`.
- Với anonymous class trong `anonymousType()`, cách xét enclosing tương tự local class. Nó có tên đơn giản rỗng, dù bytecode compiler vẫn gán một tên lớp nội bộ.
- Nếu local/anonymous class xuất hiện ngay trong block khởi tạo instance/static thay vì trong một method/constructor, đừng suy diễn rằng `getEnclosingMethod()` phải khác `null`.

`getDeclaredClasses()` của lớp ngoài chủ yếu liệt kê **member types được khai báo** trong lớp đó, không phải một danh mục đầy đủ các local/anonymous classes ở mọi method. Muốn phân tích local/anonymous, cần đối tượng `Class<?>` tương ứng hoặc quét metadata bytecode thích hợp.

## 4. Hidden class: tại sao JVM cần lớp không tìm được theo tên?

Từ **Java 15** (ổn định trong Java 17), JVM hỗ trợ **hidden class** theo JEP 371. Đây là lớp/interface thực sự ở runtime; có thể có instance, method, field, và `Class<?>` để reflection. Nhưng nó **không có binary name thông thường**, nên công cụ khác không thể tìm nó bằng `Class.forName(hidden.getName())` hoặc `ClassLoader.loadClass(...)`. Cơ chế này hữu ích cho runtime tạo implementation phụ trợ ngắn hạn, chẳng hạn một số chiến lược hiện thực lambda hoặc framework sinh mã động.

Cần phân biệt ba trường hợp:

1. **Anonymous class** viết từ source `new Runnable() { ... }`: không đặt tên trong source nhưng vẫn là lớp thông thường có tên nhị phân do compiler tạo. Nó **không phải hidden class**.
2. **Class được sinh bytecode rồi định nghĩa qua API thông thường** (ví dụ custom class loader): việc nó được sinh động không tự khiến `isHidden()` thành `true`.
3. **Class được định nghĩa qua `Lookup.defineHiddenClass(...)`**: `isHidden()` là `true`; không thể tra cứu qua tên nhị phân như class thông thường.

### Ví dụ Java 17 chạy được: tạo một hidden class

Lưu toàn bộ hai khai báo top-level sau vào **`HiddenClassExample.java`**. Cả hai cùng thuộc unnamed package; sau biên dịch, ví dụ dùng bytes của `HiddenTemplate.class` để định nghĩa **một lớp mới** ở dạng hidden. Đây là một bài thí nghiệm, không phải cách nên dùng cho class ứng dụng bình thường.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class HiddenClassExample {
    public static void main(String[] args) throws Exception {
        byte[] classBytes;
        try (InputStream in =
                 HiddenClassExample.class.getResourceAsStream(
                     "HiddenTemplate.class")) {
            if (in == null) {
                throw new IOException("Missing HiddenTemplate.class");
            }
            classBytes = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
            MethodHandles.lookup().defineHiddenClass(
                classBytes, true
            );
        Class<?> hidden = hiddenLookup.lookupClass();

        System.out.println(hidden.isHidden());
        System.out.println(hidden.isAnonymousClass());
        System.out.println(hidden.getCanonicalName() == null);
        System.out.println(hidden.getName().contains("/"));
    }
}

class HiddenTemplate {
}
~~~

~~~sh
javac HiddenClassExample.java
java HiddenClassExample
~~~

Kết quả trên JDK 17:

~~~text
true
false
true
true
~~~

Giải thích tuần tự:

1. `javac` biên dịch hai top-level classes; `HiddenTemplate.class` là một file class hợp lệ trong cùng package với `HiddenClassExample`.
2. `getResourceAsStream("HiddenTemplate.class")` đọc bytes của file đó từ classpath. Nếu dùng IDE hoặc bản đóng gói riêng, cần đảm bảo resource này có mặt.
3. `MethodHandles.lookup()` lấy lookup gắn với quyền truy cập của lớp gọi. `defineHiddenClass(classBytes, true)` tạo/lien kết một **định nghĩa lớp mới** từ bytes, không phải đổi thuộc tính của `HiddenTemplate.class` đã biên dịch. Tham số `true` yêu cầu khởi tạo lớp mới.
4. `hiddenLookup.lookupClass()` trả về handle `Class<?>` của lớp hidden vừa tạo. Nó là hidden, không là anonymous, không có canonical name. Theo đặc tả `Class.getName()`, tên hidden class chứa dấu `/` và hậu tố nội bộ; **không phụ thuộc giá trị cụ thể của hậu tố**.
5. Để gọi constructor/method của hidden class, runtime có thể dùng `Lookup`, `MethodHandle` hoặc reflection phù hợp quyền truy cập. Không sử dụng chuỗi từ `getName()` làm tên tra cứu `Class.forName`.

**Điều kiện của `defineHiddenClass`:** bytes phải là class file hợp lệ; tên lớp khai trong bytes phải cùng package với lookup class; lookup phải có quyền cần thiết (bao gồm full privilege access theo API). Lỗi thường gặp gồm `IllegalAccessException`, `IllegalArgumentException`, `ClassFormatError` hoặc lỗi liên kết/verify khác. Đừng coi đây là API nhận bytes tùy ý không đáng tin cậy.

### Quan hệ nestmate và vòng đời

`defineHiddenClass(bytes, initialize, options...)` nhận các `ClassOption` tùy chọn:

- `NESTMATE`: thêm lớp hidden vào nest của lookup class, nhờ đó có thể có quyền truy cập private giữa các nestmates. Nó **không** biến hidden class thành member class được khai báo trong source.
- `STRONG`: gắn vòng đời mạnh với defining class loader như class thông thường. **Mặc định khi không chọn `STRONG`**, hidden class có thể được unload ngay cả khi defining loader còn reachable, miễn là bản thân lớp và các đối tượng tham chiếu giữ nó không còn reachable.
- Không có `ClassOption` nào tự chuyển một anonymous class đã được tạo thành hidden class; mỗi định nghĩa lớp có danh tính riêng.

Các lớp được loader định nghĩa theo cách thông thường không có cùng đặc tính unload mặc định này. Nếu runtime sinh rất nhiều lớp, cần cân nhắc lifetime, reference tới `Class<?>`/instance và việc sử dụng `STRONG` thay vì mặc định coi tạo lớp là miễn phí.

## 5. Soi bytecode để đối chiếu với Reflection

Khi cần giải thích vì sao reflection trả kết quả nào đó, hãy kiểm tra metadata của `.class` thay vì đoán từ tên file. Với các ví dụ ở trên:

~~~sh
javac ClassKinds.java
javap -v ClassKinds.class
~~~

Trong output `javap -v`, hãy tìm các thuộc tính (nếu thích hợp với class file được kiểm tra):

- **`InnerClasses`** ghi metadata về lớp lồng/member và tên liên quan. Đây không phải lời đảm bảo rằng tất cả các tên chứa `$` đều là nested classes.
- **`EnclosingMethod`** gắn class file local/anonymous với lớp bao ngoài và có thể với method/constructor. Java reflection dùng metadata tương ứng cho `getEnclosingMethod()`/`getEnclosingConstructor()`.
- **`NestHost` / `NestMembers`** thể hiện quan hệ nest phục vụ quyền truy cập private giữa nestmates (Java 11+). **Nestmate không đồng nghĩa member class**.
- **`ACC_SYNTHETIC` và các thành viên synthetic** có thể xuất hiện vì compiler sinh chi tiết phụ trợ. `isSynthetic()` không thể thay thế `isAnonymousClass()`, `isLocalClass()` hoặc `isHidden()`.

Ví dụ compiler thường sinh các file class có dấu `$` cho member/local/anonymous, nhưng thứ tự đánh số và hình dạng tên là chi tiết triển khai; phiên bản compiler, thay đổi source và công cụ sinh bytecode có thể làm tên khác. Ngay cả `Class.getName()` cũng không nên được phân tích bằng regex như `.*\$[0-9]+.*` để phân loại.

Với hidden class, `getName()` chứa dấu `/` và hậu tố đặc biệt theo tài liệu API. Hidden class không thể được load lại bằng tên đó, và bạn không nhất thiết có file `.class` độc lập tương ứng ở filesystem: bytecode có thể chỉ tồn tại khi runtime định nghĩa lớp. Hãy dùng `Class.isHidden()` và lookup đã tạo lớp để quan sát nó.

## 6. Các tình huống sử dụng và lỗi thường gặp

**Tình huống A — viết công cụ Reflection / logging.** Nhận một `Object`, gọi `obj.getClass()` để lấy loại runtime, ghi các cờ `isHidden()`, `isMemberClass()`, `isLocalClass()`, `isAnonymousClass()`. Ghi thêm `getEnclosingClass()` hoặc `getEnclosingMethod()` nếu có. Với hidden class, giữ `Class<?>` làm định danh trong lúc xử lý; không hứa rằng có thể tái tạo lớp chỉ từ tên log.

**Tình huống B — nhận một `Runnable`.** `Runnable` là interface, không cho biết object đến từ class có tên, anonymous class hay lambda. Phải xem đối tượng thực tế. Không bắt buộc mỗi lambda tạo class riêng, không giả định `lambda.getClass().isHidden()` có cùng kết quả trên mọi JVM/phiên bản.

**Tình huống C — inner member class gây lỗi khởi tạo.** `new Outer.Inner()` áp dụng được cho `static nested`; với `non-static Inner` từ ngữ cảnh ngoài, cần `outer.new Inner()`. Khi dùng reflection, non-static member class cũng có thể có constructor thực tế mang tham số enclosing instance; chỉ tìm zero-arg constructor là chưa đủ.

**Tình huống D — local class dùng biến ngoài.** Biến local được capture phải final hoặc effectively final. Với mutable state, thay vì gán lại biến được capture, hãy thiết kế trạng thái trong object phù hợp hoặc truyền dữ liệu theo tham số; đừng dựa vào chi tiết field do compiler sinh ra.

**Tình huống E — muốn class runtime “không public”.** `private`, package-private, anonymous và hidden diễn tả những khái niệm khác nhau. `private member class` vẫn có class name bình thường. Hidden class không phải một access modifier; nó giải quyết khả năng truy cập lớp bằng tên và vòng đời của lớp được runtime định nghĩa.

Các kết luận sai cần tránh:

- “Tên có `$` là anonymous” — sai: member/local classes cũng có thể có `$`; tên compiler không phải bằng chứng chuẩn.
- “Anonymous class là hidden class” — sai; `isAnonymousClass()` và `isHidden()` kiểm tra hai thuộc tính khác nhau.
- “`static nested` không phải member class” — sai; cả hai biến thể member đều trả `isMemberClass() == true`.
- “`getDeclaringClass() == null` nghĩa là top-level” — sai; local và anonymous cũng thường cho `null`.
- “`getEnclosingMethod() == null` nghĩa là không lồng” — sai; member class và local/anonymous trong initializer có thể cho `null`.
- “Mọi class sinh lúc chạy đều hidden” — sai; phải xem nó được định nghĩa bằng cơ chế nào.
- “Có thể dùng `Class.forName` để tìm lại hidden class qua `getName()`” — sai; hidden class không có binary name cho lookup thông thường.
- “`isSynthetic()` thay thế `isHidden()`” — sai; synthetic là nhãn khác với hidden.
- “Một lambda chắc chắn là anonymous class” — sai; lambda là cấu trúc ngôn ngữ khác.
- “Tên của local/anonymous class hoặc hậu tố hidden ổn định giữa các lần build/run” — không có bảo đảm đó.

## 7. Quy trình nhận diện khi điều tra hệ thống thật

1. **Lấy `Class<?>` thực tế**: từ `obj.getClass()`, `SomeType.class`, API reflection hoặc `Lookup.lookupClass()` khi runtime sinh hidden class.
2. **Kiểm tra các cờ chính thức**: `isHidden()`, `isAnonymousClass()`, `isLocalClass()`, `isMemberClass()`. Với member, thêm `Modifier.isStatic(getModifiers())`.
3. **Khôi phục ngữ cảnh**: `getDeclaringClass()` cho member; `getEnclosingClass()` và `getEnclosingMethod()`/`getEnclosingConstructor()` khi thích hợp.
4. **Quan sát tên để hiển thị, không để suy diễn loại**: `getSimpleName()`, `getCanonicalName()` và `getName()` có ý nghĩa khác nhau; một số có thể rỗng hoặc `null`.
5. **Khi cần chứng cứ sâu hơn**, đọc class metadata với `javap -v` hoặc công cụ bytecode. Đối với hidden class, lấy thông tin từ runtime định nghĩa nó thay vì giả định tra cứu file bằng tên.
6. **Khi tạo instance hoặc gọi method**, xét điều kiện enclosing instance, quyền truy cập, lookup, class loader và module; phân loại đúng chưa tự động đảm bảo gọi được mọi constructor/method.

### Tự kiểm tra

**Câu 1.** `static class Cache { }` khai báo trực tiếp trong `Outer`: `isMemberClass()` trả gì? Nó cần `Outer` instance không?

**Đáp án:** `true`; không cần enclosing instance. Dùng `Modifier.isStatic(...)` để xác nhận kiểu member `static`.

**Câu 2.** `class Temp { }` khai báo trong một method: vì sao `getDeclaringClass()` có thể `null` trong khi `getEnclosingMethod()` khác `null`?

**Đáp án:** `Temp` là local class, không phải member class; `getEnclosingMethod()` nói về ngữ cảnh method bao ngoài, không phải lớp khai báo member.

**Câu 3.** `new Runnable() { public void run() {} }` và `() -> {}` được gán cho `Runnable` có cùng là anonymous class không?

**Đáp án:** Không. Cú pháp `new ... { }` là anonymous class; lambda là biểu thức lambda, implementation có thể phụ thuộc JVM.

**Câu 4.** `Class<?> c` được lấy từ `defineHiddenClass`: muốn nhận diện và dùng nó, nên làm gì?

**Đáp án:** Kiểm tra `c.isHidden()`, giữ `Class<?>`/`Lookup`/`MethodHandle` cần thiết để tương tác. Không gọi `Class.forName(c.getName())` để tìm lại nó.

## 8. Tài liệu chuẩn để tra cứu thêm

- Java SE 17 — `java.lang.Class` (các API `isMemberClass`, `isLocalClass`, `isAnonymousClass`, `isHidden`, `getDeclaringClass`, `getEnclosingMethod`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — `MethodHandles.Lookup.defineHiddenClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)
- Java SE 17 — `MethodHandles.Lookup.ClassOption` (`NESTMATE` và `STRONG`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- OpenJDK JEP 371 — Hidden Classes: https://openjdk.org/jeps/371

**Ghi nhớ:** Khi hỏi “lớp này là loại gì?”, hãy bắt đầu từ cờ của `Class` và ngữ cảnh khai báo; khi hỏi “vì sao lớp này không thể load theo tên?”, hãy kiểm tra cơ chế định nghĩa runtime, đặc biệt `isHidden()`.