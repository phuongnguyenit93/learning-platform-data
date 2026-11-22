# getEnclosingMethod và getEnclosingConstructor

## 1. Hai API này trả lời câu hỏi gì?

Khi gặp một lớp cục bộ hoặc lớp vô danh, ta có thể muốn biết: **phần khai báo lớp đó nằm trong phương thức hay hàm khởi tạo nào?** Đây là thông tin về vị trí khai báo trong mã nguồn, được biểu diễn bằng metadata của lớp khi chạy.

Ví dụ, một phương thức tạo tác vụ bằng `new Runnable() { ... }`. Đối tượng tác vụ có thể được trả về và sử dụng sau khi phương thức đã kết thúc. Lớp vô danh của nó vẫn có thông tin về phương thức bao quanh phần khai báo.

Hai phương thức trên `Class<?>` phục vụ việc truy vấn này:

~~~java
// Chữ ký rút gọn của các API trên java.lang.Class:
public Method getEnclosingMethod();
public Constructor<?> getEnclosingConstructor();
~~~

`Method` và `Constructor` thuộc gói `java.lang.reflect`. Chúng mô tả một phương thức hoặc hàm khởi tạo; việc nhận các đối tượng này không tự thực thi mã được mô tả.

Trước khi đi tiếp, cần phân biệt ba khái niệm:

- **Lớp cục bộ (local class):** lớp có tên được khai báo trong một khối, chẳng hạn thân phương thức hoặc thân hàm khởi tạo.
- **Lớp vô danh (anonymous class):** lớp được khai báo ngay trong biểu thức tạo đối tượng, ví dụ `new Runnable() { ... }`.
- **Lớp thành viên (member class):** lớp được khai báo trực tiếp trong thân một lớp khác, ở cấp thành viên. Nó có thể có hoặc không có `static`.

Cả ba đều có thể liên quan đến lớp bao quanh, nhưng chỉ hai nhóm đầu có thể gắn trực tiếp với một phương thức hoặc hàm khởi tạo bao quanh. Không suy ra kết quả hai API chỉ từ việc tên lớp có ký tự `$`.

## 2. Quy tắc đọc kết quả

Với `Class<?> type`:

- `type.getEnclosingMethod()` trả về phương thức trực tiếp bao quanh nếu `type` biểu diễn lớp cục bộ hoặc lớp vô danh nằm trong phương thức đó; trường hợp khác trả về `null`.
- `type.getEnclosingConstructor()` trả về hàm khởi tạo trực tiếp bao quanh nếu `type` biểu diễn lớp cục bộ hoặc lớp vô danh nằm trong hàm khởi tạo đó; trường hợp khác trả về `null`.

Với một lớp thông thường do trình biên dịch Java sinh ra, hai kết quả không đồng thời khác `null`: một vị trí khai báo không đồng thời nằm trực tiếp trong cả phương thức và hàm khởi tạo.

| Vị trí khai báo của lớp đang xét | `getEnclosingMethod()` | `getEnclosingConstructor()` |
| --- | --- | --- |
| Lớp cục bộ hoặc vô danh trong phương thức | Phương thức bao quanh | `null` |
| Lớp cục bộ hoặc vô danh trong hàm khởi tạo | `null` | Hàm khởi tạo bao quanh |
| Lớp cục bộ hoặc vô danh trong khối khởi tạo đối tượng | `null` | `null` |
| Lớp cục bộ hoặc vô danh trong khối khởi tạo tĩnh | `null` | `null` |
| Lớp vô danh ngay trong biểu thức khởi tạo trường | `null` | `null` |
| Lớp thành viên, có hoặc không có `static` | `null` | `null` |
| Lớp ở cấp cao nhất | `null` | `null` |

**Hai kết quả cùng bằng `null` không chứng minh lớp nằm ở cấp cao nhất.** Lớp thành viên, lớp cục bộ trong khối khởi tạo và lớp vô danh trong biểu thức khởi tạo trường đều là những phản ví dụ.

Các token như `int.class`, `void.class` và `String[].class` cũng không có phương thức hoặc hàm khởi tạo khai báo bao quanh; cả hai API trả về `null`. Mảng của một lớp lồng không vì vậy mà có cùng kết quả với lớp phần tử.

Quy tắc trả về và những trường hợp khởi tạo được nêu trong tài liệu [Class.getEnclosingMethod](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getEnclosingMethod()) và [Class.getEnclosingConstructor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getEnclosingConstructor()).

## 3. Chương trình hoàn chỉnh: đối chiếu 11 trường hợp

Lưu mã sau vào tệp `EnclosingExecutableDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class EnclosingExecutableDemo {
    static class Member {
    }

    class InnerMember {
    }

    static Class<?> localInMethod() {
        class Local {
        }
        return Local.class;
    }

    static Class<?> anonymousInMethod() {
        return new Runnable() {
            @Override
            public void run() {
            }
        }.getClass();
    }

    static class Box {
        final Class<?> localType;
        final Class<?> anonymousType;

        Box(int id) {
            class Local {
            }
            localType = Local.class;
            anonymousType = new Runnable() {
                @Override
                public void run() {
                }
            }.getClass();
        }
    }

    static Class<?> staticBlockType;

    static {
        class StaticLocal {
        }
        staticBlockType = StaticLocal.class;
    }

    final Class<?> instanceBlockType;

    {
        class InstanceLocal {
        }
        instanceBlockType = InstanceLocal.class;
    }

    final Runnable fieldTask = new Runnable() {
        @Override
        public void run() {
        }
    };

    static final Runnable STATIC_FIELD_TASK = new Runnable() {
        @Override
        public void run() {
        }
    };

    static String className(Class<?> type) {
        return type == null ? "null" : type.getSimpleName();
    }

    static String parameters(Executable executable) {
        return Arrays.stream(executable.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ", "(", ")"));
    }

    static String methodName(Method method) {
        return method == null ? "null"
                : method.getDeclaringClass().getSimpleName()
                  + "." + method.getName() + parameters(method);
    }

    static String constructorName(Constructor<?> constructor) {
        return constructor == null ? "null"
                : constructor.getDeclaringClass().getSimpleName()
                  + parameters(constructor);
    }

    static void inspect(String label, Class<?> type) {
        System.out.println(label
                + " -> enclosing=" + className(type.getEnclosingClass())
                + "; method=" + methodName(type.getEnclosingMethod())
                + "; constructor=" + constructorName(type.getEnclosingConstructor())
                + "; declaring=" + className(type.getDeclaringClass()));
    }

    public static void main(String[] args) {
        EnclosingExecutableDemo demo = new EnclosingExecutableDemo();
        Box box = new Box(7);

        inspect("top-level", EnclosingExecutableDemo.class);
        inspect("static member", Member.class);
        inspect("inner member", InnerMember.class);
        inspect("method local", localInMethod());
        inspect("method anonymous", anonymousInMethod());
        inspect("constructor local", box.localType);
        inspect("constructor anonymous", box.anonymousType);
        inspect("static block", staticBlockType);
        inspect("instance block", demo.instanceBlockType);
        inspect("instance field", demo.fieldTask.getClass());
        inspect("static field", STATIC_FIELD_TASK.getClass());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 EnclosingExecutableDemo.java
java EnclosingExecutableDemo
~~~

Kết quả chính xác:

~~~text
top-level -> enclosing=null; method=null; constructor=null; declaring=null
static member -> enclosing=EnclosingExecutableDemo; method=null; constructor=null; declaring=EnclosingExecutableDemo
inner member -> enclosing=EnclosingExecutableDemo; method=null; constructor=null; declaring=EnclosingExecutableDemo
method local -> enclosing=EnclosingExecutableDemo; method=EnclosingExecutableDemo.localInMethod(); constructor=null; declaring=null
method anonymous -> enclosing=EnclosingExecutableDemo; method=EnclosingExecutableDemo.anonymousInMethod(); constructor=null; declaring=null
constructor local -> enclosing=Box; method=null; constructor=Box(int); declaring=null
constructor anonymous -> enclosing=Box; method=null; constructor=Box(int); declaring=null
static block -> enclosing=EnclosingExecutableDemo; method=null; constructor=null; declaring=null
instance block -> enclosing=EnclosingExecutableDemo; method=null; constructor=null; declaring=null
instance field -> enclosing=EnclosingExecutableDemo; method=null; constructor=null; declaring=null
static field -> enclosing=EnclosingExecutableDemo; method=null; constructor=null; declaring=null
~~~

Chương trình chủ động in tên lớp và chữ ký theo cách ngắn gọn. Nó không dựa vào số thứ tự trong tên nhị phân của lớp vô danh, cũng không dựa vào cách `Method.toString()` ghép toàn bộ thông tin.

### 3.1. Lớp trong phương thức

`localInMethod()` khai báo lớp `Local` rồi trả về `Local.class`. Khi `main()` truy vấn token đó, kết quả vẫn là `EnclosingExecutableDemo.localInMethod()`.

Tương tự, lớp vô danh tạo ra trong `anonymousInMethod()` gắn với phương thức này. Phương thức bao quanh là phương thức chứa **phần khai báo lớp**, không phải phương thức đang gọi Reflection.

Do đó, hai dòng có nhãn `method local` và `method anonymous` đều có:

- `enclosing=EnclosingExecutableDemo`: lớp bao quanh.
- `method` khác `null`: phương thức chứa khai báo lớp cục bộ hoặc vô danh.
- `constructor=null`: khai báo không nằm trực tiếp trong hàm khởi tạo.
- `declaring=null`: lớp đang xét không phải lớp thành viên.

### 3.2. Lớp trong hàm khởi tạo

Hai lớp được khai báo trong `Box(int id)` trả về `Box(int)` qua `getEnclosingConstructor()`. Đó là hàm khởi tạo của **Box**, không phải hàm khởi tạo của chính lớp cục bộ hoặc lớp vô danh.

Trong chương trình, tham số `id` không được sử dụng để giữ ví dụ tập trung vào vị trí khai báo. Số `7` truyền khi tạo `Box` không xuất hiện trong kết quả Reflection: metadata mô tả kiểu tham số `int`, không lưu giá trị của lần gọi hàm khởi tạo đó.

`getEnclosingMethod()` trả về `null` trong hai trường hợp này. Dù hàm khởi tạo có mã thực thi và tham số, Java Reflection biểu diễn nó bằng `Constructor<?>`, không phải `Method`.

### 3.3. Khối khởi tạo và biểu thức khởi tạo trường

Bốn trường hợp cuối cùng đều có lớp bao quanh nhưng không có phương thức hoặc hàm khởi tạo bao quanh:

- `static block`: lớp cục bộ trong `static { ... }`.
- `instance block`: lớp cục bộ trong khối `{ ... }` dùng khi khởi tạo đối tượng.
- `instance field`: lớp vô danh trong biểu thức khởi tạo trường `fieldTask`.
- `static field`: lớp vô danh trong biểu thức khởi tạo trường `STATIC_FIELD_TASK`.

Đặc biệt, mã khởi tạo trường đối tượng và khối khởi tạo đối tượng có thể được trình biên dịch đưa vào mã khởi tạo của lớp. Điều đó **không làm thay đổi vị trí khai báo trong mã nguồn thành một thân constructor**. Vì thế không được suy luận rằng `getEnclosingConstructor()` phải trả về constructor đã thực hiện việc khởi tạo.

Đối với khối tĩnh, `getEnclosingMethod()` cũng không trả về một `Method` tên `<clinit>`. Hai API này không dùng để liệt kê mọi đơn vị thực thi ở cấp bytecode.

## 4. So sánh với getEnclosingClass và getDeclaringClass

Bốn truy vấn thường xuất hiện cạnh nhau, nhưng trả lời các câu hỏi khác nhau:

| Truy vấn trên `Class<?> type` | Câu hỏi |
| --- | --- |
| `getEnclosingClass()` | Lớp nào trực tiếp bao quanh lớp đang xét? |
| `getDeclaringClass()` | Lớp nào khai báo lớp đang xét như một thành viên? |
| `getEnclosingMethod()` | Phương thức nào trực tiếp bao quanh khai báo lớp cục bộ hoặc vô danh? |
| `getEnclosingConstructor()` | Hàm khởi tạo nào trực tiếp bao quanh khai báo lớp cục bộ hoặc vô danh? |

Trong ví dụ:

- `Member.class` và `InnerMember.class` đều có `getDeclaringClass()` là `EnclosingExecutableDemo.class`, vì đều được khai báo ở cấp thành viên.
- Lớp cục bộ trong `localInMethod()` có `getEnclosingClass()` là `EnclosingExecutableDemo.class`, nhưng `getDeclaringClass()` là `null`.
- Lớp cục bộ trong constructor của `Box` có `getEnclosingClass()` là `Box.class`, không phải lớp ngoài cùng `EnclosingExecutableDemo.class`.

Không nên đánh đồng `getEnclosingClass()` với lớp gốc của một nhóm nest. Quan hệ nest phục vụ một mục đích riêng liên quan đến truy cập thành viên; nếu cần khảo sát nó thì dùng các API nest tương ứng.

Cũng cần nhìn đúng **đối tượng nhận lời gọi**. Hai biểu thức sau không hỏi cùng một điều:

~~~java
// Đoạn minh họa, dùng các lớp/phương thức trong chương trình ở trên.
Class<?> localType = EnclosingExecutableDemo.localInMethod();
Method enclosing = localType.getEnclosingMethod();

System.out.println(localType.getDeclaringClass()); // null
System.out.println(enclosing.getDeclaringClass()
        == EnclosingExecutableDemo.class);        // true
~~~

`localType.getDeclaringClass()` hỏi lớp đang xét có phải một lớp thành viên hay không. `enclosing.getDeclaringClass()` hỏi lớp nào khai báo **phương thức** đã tìm được. Trùng tên API không có nghĩa trùng vai trò.

## 5. “Bao quanh” là quan hệ khai báo, không phải lịch sử chạy

Một lớp có thể được tạo đối tượng ở nhiều nơi, nhưng nơi tạo đối tượng không sửa lại quan hệ khai báo của lớp.

Trong ví dụ, `main()` gọi `localInMethod()`. Sau khi phương thức này đã trả về, `inspect()` mới đọc metadata. `getEnclosingMethod()` vẫn chỉ đến `localInMethod()`, không chỉ đến `main()` hoặc `inspect()`.

Từ kết quả này không thể biết:

- Lần gọi nào đã tạo ra một đối tượng cụ thể.
- Luồng nào đã thực hiện lần gọi đó.
- Giá trị biến cục bộ hoặc tham số khi đối tượng được tạo.
- Phương thức nào vừa gọi một phương thức khác trong ngăn xếp hiện tại.
- Một đối tượng đã được truyền qua những phương thức nào sau khi tạo.

Nếu cần ngăn xếp lời gọi hiện tại, đó là bài toán khác, chẳng hạn khảo sát bằng `StackWalker`. Nếu cần dữ liệu của một lần thực thi, hãy truyền và lưu dữ liệu đó bằng thiết kế chương trình thích hợp.

Từ “trực tiếp” cũng có ý nghĩa. Giả sử một phương thức `factory()` khai báo lớp cục bộ `Container`; trong phương thức `build()` của `Container` lại khai báo lớp cục bộ `Part`. Với `Part.class`, phương thức trực tiếp bao quanh là `Container.build()`. Không bỏ qua cấp này để kết luận `factory()` là kết quả.

## 6. Metadata đến từ đâu?

Class file của lớp cục bộ hoặc lớp vô danh có thuộc tính `EnclosingMethod`. Tên thuộc tính này có thể gây hiểu nhầm: nó biểu diễn cả trường hợp phương thức, hàm khởi tạo và trường hợp không có đơn vị nào thuộc hai loại đó trực tiếp bao quanh.

Có thể hình dung thông tin chính như sau:

~~~text
Lớp bao quanh
    +
Tên và descriptor của phương thức/constructor bao quanh
    hoặc
Không có phương thức/constructor bao quanh
~~~

Theo [JVMS §4.7.7](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.7), thuộc tính có `class_index` và `method_index`. `method_index = 0` khi lớp không được bao quanh trực tiếp bởi phương thức hoặc hàm khởi tạo; các khối khởi tạo và biểu thức khởi tạo trường là những trường hợp quan trọng.

Điều này giải thích ba điểm thực tế:

1. Reflection không cần mở lại tệp `.java` để tìm phương thức bao quanh.
2. Thông tin này không phải tên biến cục bộ trong bảng debug. Không cần thêm `-parameters` để hai API hoạt động; tùy chọn đó liên quan đến tên tham số.
3. Tên và descriptor giúp xác định đúng phương thức hoặc constructor khi có nạp chồng. Chỉ lấy `getName()` rồi bỏ kiểu tham số sẽ làm mất một phần thông tin cần phân biệt.

Ví dụ trong chương trình, `parameters(Executable)` đọc các kiểu tham số theo thứ tự và tạo chuỗi `(int)` cho constructor của `Box`. Không suy đoán constructor từ tên lớp và không tìm “constructor đầu tiên” trong một mảng kết quả.

Với bytecode được sinh hoặc biến đổi bởi công cụ khác, cần xem metadata của chính class file. Đừng dùng dấu `$` hoặc mẫu tên như `Outer$1` làm bằng chứng thay cho API. Cũng không nên phụ thuộc vào số đánh thứ tự mà một lần biên dịch gán cho lớp vô danh.

## 7. Cách dùng trong mã khảo sát hoặc công cụ

Một công cụ có thể muốn thống nhất phương thức và constructor bao quanh dưới kiểu chung `Executable`. Lớp này là lớp cha của `Method` và `Constructor`.

Đoạn sau là phương thức hỗ trợ; thêm các import `java.lang.reflect.Executable`, `java.lang.reflect.Method` và `java.util.Objects` vào lớp chứa nó:

~~~java
static Executable findEnclosingExecutable(Class<?> type) {
    Objects.requireNonNull(type, "type");

    Method method = type.getEnclosingMethod();
    if (method != null) {
        return method;
    }
    return type.getEnclosingConstructor();
}
~~~

Cách dùng minh họa khi đặt phương thức hỗ trợ trong cùng chương trình:

~~~java
Executable enclosing =
        findEnclosingExecutable(EnclosingExecutableDemo.localInMethod());

if (enclosing == null) {
    System.out.println("Khong co method/constructor bao quanh");
} else {
    System.out.println(enclosing.getDeclaringClass().getSimpleName());
    System.out.println(enclosing.getParameterCount());
}
~~~

Với lớp do `localInMethod()` trả về, hai dòng được in là:

~~~text
EnclosingExecutableDemo
0
~~~

Ở đây `null` là kết quả hợp lệ khi không có đơn vị khai báo tương ứng. Không biến nó thành lỗi “không tìm thấy lớp”, và không gọi tiếp `getName()` trên kết quả chưa kiểm tra.

Một vài nguyên tắc sử dụng:

- **Lấy đúng lớp cần khảo sát.** Nếu đang có đối tượng, `object.getClass()` lấy lớp thực tế của đối tượng; `Runnable.class` chỉ là token của interface và không đại diện cho lớp vô danh triển khai nó.
- **Giữ chữ ký khi cần nhận diện chính xác.** Ngoài tên phương thức, xem lớp khai báo và kiểu tham số. Với constructor, `getDeclaringClass()` thể hiện lớp được khởi tạo.
- **Tách truy vấn metadata khỏi thực thi.** Nhận một `Method` hoặc `Constructor` không cấp quyền gọi nó và không tự bỏ qua kiểm soát truy cập. Không thêm `setAccessible(true)` chỉ để đọc tên hoặc kiểu tham số.
- **Không yêu cầu đối tượng của lớp bao quanh để truy vấn.** Các API được gọi trên `Class<?>`. Việc một lớp bên trong cần đối tượng bao quanh để tạo instance là vấn đề khác.
- **Không dùng như bộ máy tìm tất cả lớp cục bộ.** Hai API nhận một lớp đã biết và đi từ lớp đó về nơi khai báo. Chúng không trả về danh sách mọi lớp được khai báo trong một phương thức.
- **Không suy diễn từ lambda.** Lambda không đồng nghĩa với khai báo lớp vô danh. Không thiết kế chức năng tìm phương thức nguồn của lambda dựa trên giả định lớp thực thi lambda có cùng metadata bao quanh như `new Runnable() { ... }`.

Khi chạy trên môi trường Java cũ có cấu hình Security Manager, các API có thể chịu kiểm tra bảo mật và ném `SecurityException` theo tài liệu phiên bản tương ứng. Ví dụ học tập ở trên không cần thay đổi chính sách bảo mật hoặc mở truy cập sâu vào JDK.

## 8. Lỗi thường gặp

### Gọi getEnclosingConstructor để tìm constructor của chính lớp

Đó là nhầm hướng truy vấn. Muốn xem constructor thuộc lớp đang xét, dùng `getDeclaredConstructors()` hoặc tìm chữ ký thích hợp bằng `getDeclaredConstructor(...)`.

`getEnclosingConstructor()` đi ra ngoài lớp đang xét, đến constructor chứa **khai báo** lớp cục bộ hoặc vô danh đó.

### Cho rằng mọi lớp không có static đều có enclosing constructor

`InnerMember` trong chương trình là lớp thành viên không có `static`, nhưng hai API đều trả về `null`. Quan hệ với một đối tượng bao quanh không tự tạo ra một constructor khai báo bao quanh.

### Thấy hai kết quả null rồi kết luận không có lớp bao quanh

Trường hợp lớp trong khối khởi tạo có thể có `getEnclosingClass()` khác `null` dù cả hai kết quả đang học đều bằng `null`. Muốn trả lời câu hỏi về lớp bao quanh thì phải hỏi `getEnclosingClass()`.

### Nghĩ lớp vô danh không có tên nên không có metadata khai báo

Lớp vô danh không có tên đơn giản trong mã nguồn, nhưng vẫn có một `Class<?>` và có thể được truy vấn. Hãy lấy token từ đối tượng, không tự dựng tên nhị phân.

### Mong getEnclosingMethod trả về run()

Với lớp vô danh triển khai `Runnable`, `run()` là phương thức **của lớp đó**. Nếu khai báo lớp vô danh nằm trong `anonymousInMethod()`, phương thức bao quanh là `anonymousInMethod()`. Muốn tìm `run()` trên lớp đang xét, đó là truy vấn thành viên như `getDeclaredMethod("run")`, không phải truy vấn enclosing.

## 9. Tự kiểm tra

1. Một lớp cục bộ được khai báo trong phương thức `create()`. Khi chương trình giữ `Class<?>` của nó sau khi `create()` kết thúc, `getEnclosingMethod()` còn trả về `create()` không?
2. Một lớp vô danh được khai báo trong constructor `Store(String name)`. Hai API trả về gì?
3. Một lớp vô danh nằm trong biểu thức khởi tạo trường đối tượng. Vì sao không thể mặc định constructor của đối tượng là kết quả của `getEnclosingConstructor()`?
4. Một lớp thành viên không có `static` được tạo đối tượng ngay trong `main()`. `getEnclosingMethod()` có trả về `main()` không?
5. Với lớp cục bộ trong phương thức, `Class.getDeclaringClass()` và `Method.getDeclaringClass()` trên phương thức bao quanh có nhất thiết giống nhau không?
6. Từ kết quả `getEnclosingConstructor()`, có đọc được giá trị tham số của lần tạo một đối tượng cụ thể không?

Đáp án:

1. Có. Đây là metadata về khai báo, không phụ thuộc phương thức còn trên ngăn xếp hay không.
2. `getEnclosingMethod()` trả về `null`; `getEnclosingConstructor()` mô tả `Store(String)`.
3. Vị trí khai báo thuộc biểu thức khởi tạo trường, không thuộc thân constructor trong mã nguồn; cả hai API trả về `null`.
4. Không. Lớp thành viên vẫn là lớp thành viên; nơi tạo instance không đổi vị trí khai báo của nó.
5. Không. Truy vấn trên lớp cục bộ trả về `null`; truy vấn trên phương thức cho lớp khai báo phương thức.
6. Không. Kết quả mô tả chữ ký và metadata của constructor, không lưu dữ liệu từng lần thực thi.
