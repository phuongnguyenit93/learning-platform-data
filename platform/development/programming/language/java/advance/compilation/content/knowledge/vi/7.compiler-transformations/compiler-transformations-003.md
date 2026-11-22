# Biên dịch lớp lồng nhau, lớp cục bộ và lớp vô danh trong Java

## 1. Mục tiêu và bức tranh tổng thể

Java cho phép viết các lớp bên trong khai báo lớp khác hoặc trong các khối lệnh. Source trông như một cấu trúc lồng nhau, nhưng JVM làm việc với **các class độc lập ở dạng bytecode**, mỗi class có danh tính riêng và có thể được nạp theo nhu cầu. Vì thế, `javac` phải chuyển các quan hệ phạm vi trong mã nguồn thành các quan hệ có thể biểu diễn bằng class file: tham chiếu đến đối tượng bao quanh, dữ liệu được *capture*, constructor, metadata của lớp và các lệnh gọi tương ứng.

Trong Java, **nested class** bao gồm các loại thường gặp:

| Dạng | Nơi khai báo | Có cần đối tượng lớp bao quanh khi tạo không? | Cơ chế biên dịch tiêu biểu |
| --- | --- | --- | --- |
| **Static nested class** | Thành viên `static class Nested` của lớp khác | Không | Một class file riêng; không có tham chiếu enclosing instance chỉ vì được khai báo lồng nhau |
| **Inner member class** | Thành viên `class Inner` không `static` | Có trong ngữ cảnh khởi tạo thông thường | Một class file riêng, thường có constructor nhận enclosing instance và field giữ tham chiếu |
| **Local class** | Khai báo có tên trong block, chẳng hạn thân method | Phụ thuộc ngữ cảnh tĩnh/không tĩnh và cách khai báo | Class file riêng; có thể giữ biến cục bộ được capture và enclosing instance |
| **Anonymous class** | Biểu thức `new SuperType(...) { ... }` | Phụ thuộc ngữ cảnh | Class file riêng cho khai báo anonymous, có thể giữ giá trị capture; không có tên đơn giản trong source |

Theo Java Language Specification, **inner class** là nested class không được khai báo `static` một cách tường minh hoặc ngầm định. Vì vậy static nested class vẫn là *nested class*, nhưng không phải *inner class*. Enum, record lồng nhau và member interface có quy tắc `static` ngầm định riêng; không nên áp dụng máy móc cách capture của inner class cho chúng.

Bài này tập trung vào **biến đổi mã trong lúc biên dịch**: compiler phải sinh thêm cái gì, truyền dữ liệu bằng cách nào, và JVM nhìn các kiểu đó ra sao. Tên tệp `.class` chỉ là một phần của kết quả.

## 2. Lớp lồng nhau đi qua chu trình biên dịch thế nào?

Có thể hình dung việc `javac` xử lý source như sau:

~~~text
CompilationDemo.java
      |
      v
Parse: nhận diện top-level class, member class, local class,
       anonymous class expression; xây dựng cấu trúc cú pháp
      |
      v
Resolve / attribute / kiểm tra hợp lệ:
       phạm vi tên, kiểu, access, enclosing instance,
       supertype, final / effectively final của capture
      |
      v
Lowering / biến đổi biểu diễn:
       chuẩn bị class độc lập, đường truyền enclosing instance,
       captured values và constructor/field cần thiết
      |
      v
Sinh bytecode + metadata:
       CompilationDemo.class
       CompilationDemo$StaticNested.class
       CompilationDemo$Inner.class
       CompilationDemo$1Local.class
       CompilationDemo$1.class
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết tất cả bước nội bộ của `javac` luôn diễn ra đúng một lần theo thứ tự tuyến tính này. Compiler có thể kết hợp xử lý symbol, attribution, annotation processing, lowering và generation qua nhiều pha; tuy nhiên từ góc độ Java source, các dạng lớp này phải được kiểm tra ngữ nghĩa và chuyển thành cấu trúc JVM có thể chạy.

Những điều cần phân biệt:

- **Phạm vi từ vựng** (lexical scope): nơi mã nguồn được phép gọi tên `Inner`, `Local`, biến method, field của lớp bao quanh.
- **Đối tượng bao quanh** (enclosing instance): instance được gắn với một inner class để truy cập trạng thái instance của lớp bao quanh.
- **Captured variable**: giá trị một biến local hoặc parameter được sử dụng từ bên trong local/anonymous class sau khi vượt qua ranh giới phạm vi của Java source.
- **Tên nhị phân và class file**: cơ chế xác định danh tính và nạp class; quan hệ lồng nhau không có nghĩa nhiều khai báo bị gộp thành một `.class`.

## 3. Ví dụ Java 17+ đầy đủ, chạy được

Tạo tệp **`src/demo/CompilationDemo.java`** đúng nội dung dưới đây, lưu UTF-8:

~~~java
package demo;

public class CompilationDemo {
    private final String owner;
    private int secret = 7;

    public CompilationDemo(String owner) {
        this.owner = owner;
    }

    public static class StaticNested {
        public String label() { return "static"; }
    }

    public class Inner {
        public String label() { return owner + ":" + secret; }
    }

    public void work(int offset) {
        String suffix = "!";

        class Local {
            String label() { return "local:" + (secret + offset) + suffix; }
        }

        Runnable anonymous = new Runnable() {
            @Override public void run() {
                System.out.println("anonymous:" + owner + ":" + offset + suffix);
            }
        };

        System.out.println(new StaticNested().label());
        System.out.println(new Inner().label());
        System.out.println(new Local().label());
        anonymous.run();

        System.out.println("inner declaring: "
                + (Inner.class.getDeclaringClass() == CompilationDemo.class));
        System.out.println("local enclosing: "
                + Local.class.getEnclosingMethod().getName());
        System.out.println("anon anonymous: "
                + anonymous.getClass().isAnonymousClass());
    }

    public static void main(String[] args) {
        new CompilationDemo("A").work(5);
    }
}
~~~

Trong Bash, đứng ở thư mục chứa `src` và chạy:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/CompilationDemo.java
java -cp out demo.CompilationDemo
~~~

Trong PowerShell, có thể dùng `New-Item -ItemType Directory -Force out` để tạo thư mục. Cùng lệnh `javac` và `java` chạy được nếu JDK nằm trên `PATH`.

**Stdout chính xác** của ví dụ khi chạy thành công:

~~~text
static
A:7
local:12!
anonymous:A:5!
inner declaring: true
local enclosing: work
anon anonymous: true
~~~

Giải thích:
- `StaticNested` là một class độc lập không cần instance `CompilationDemo`.
- `Inner` đọc `owner` và `secret` của đối tượng `CompilationDemo` hiện tại.
- `Local` đọc field `secret`, parameter `offset=5`, local `suffix="!"`; vì vậy tính ra `7+5=12`.
- Anonymous class cài đặt `Runnable` và cũng tham chiếu tới `owner`, `offset`, `suffix`.
- Reflection phân biệt member class, enclosing method của local class và anonymous class.

Với chính source và `javac --release 17` này, thư mục `out/demo/` có các tệp:

~~~text
out/
└── demo/
    ├── CompilationDemo.class
    ├── CompilationDemo$StaticNested.class
    ├── CompilationDemo$Inner.class
    ├── CompilationDemo$1Local.class
    └── CompilationDemo$1.class
~~~

Thứ tự liệt kê trên hệ điều hành không cố định. Tên có số như `$1Local` hoặc `$1` là chi tiết của kết quả biên dịch cụ thể, không phải một contract để dùng trong chương trình. Khi chèn thêm anonymous/local declaration hoặc đổi compiler, các số có thể thay đổi.

**Một file source tạo nhiều class file** vì mỗi khai báo lớp có biểu diễn riêng trong JVM. Về mặt runtime, việc thực hiện `work()` nhiều lần tạo **nhiều object** `Local` và anonymous, chứ không biên dịch hoặc định nghĩa một class mới cho mỗi lần gọi.

## 4. Static nested class: lồng về tên nhưng không giữ enclosing instance

Trong source:

~~~java
public static class StaticNested {
    public String label() { return "static"; }
}
~~~

Class này được đặt trong `CompilationDemo` về mặt khai báo, nhưng **không cần một object `CompilationDemo` để khởi tạo**:

~~~java
CompilationDemo.StaticNested value = new CompilationDemo.StaticNested();
System.out.println(value.label()); // static
~~~

Đây là đoạn mã dùng bên trong một phương thức hoặc chương trình đã khai báo `CompilationDemo`, không phải source độc lập.

Khi biên dịch, JVM nhận class riêng `demo.CompilationDemo$StaticNested`. Nó có constructor riêng; đoạn mẫu không buộc constructor phải nhận tham số `CompilationDemo`. Ký hiệu `$` ở binary name biểu thị cách đặt tên thành viên, **không thể dùng để suy ra lớp ấy có enclosing object**.

Một static nested class có thể truy cập member `static` phù hợp của outer class. Nó **không thể trực tiếp đọc `owner` hoặc `secret`**, vì đó là field instance; phải có đối tượng `CompilationDemo` cụ thể và quyền truy cập phù hợp.

## 5. Inner member class: compiler chuyển quan hệ enclosing instance thành dữ liệu

Trong source:

~~~java
public class Inner {
    public String label() { return owner + ":" + secret; }
}
~~~

Tại `work()` (một instance method của `CompilationDemo`), `new Inner()` dùng ngầm `this` của `CompilationDemo` làm **enclosing instance**.

Đặt bên ngoài class `CompilationDemo`, cách khởi tạo tương ứng là:

~~~java
CompilationDemo outer = new CompilationDemo("B");
CompilationDemo.Inner inner = outer.new Inner();
System.out.println(inner.label()); // B:7
~~~

Đoạn trên cũng là **trích đoạn sử dụng trong một method**, không phải tệp Java độc lập.

Ở mức bytecode, inner member class thường được compiler triển khai gần tương đương ý tưởng:

~~~java
// Pseudocode minh họa cấu trúc compiler có thể sinh;
// không phải mã nguồn thay thế hợp lệ cho khai báo ban đầu.
final class InnerLowered {
    private final CompilationDemo enclosing;

    InnerLowered(CompilationDemo enclosing) {
        this.enclosing = enclosing;
    }

    String label() {
        return enclosing.owner + ":" + enclosing.secret;
    }
}
~~~

Pseudocode trên chỉ nhằm giải thích **tại sao cần một tham chiếu outer**. Class thật có tên nhị phân riêng, metadata về nesting và quy tắc access do JVM quyết định. Không nên viết thủ công `InnerLowered` hoặc thay `new Inner()` bằng constructor nhân tạo trong source.

Khi dùng `javap -p` với bản biên dịch ví dụ, có thể thấy:

~~~text
public class demo.CompilationDemo$Inner {
  final demo.CompilationDemo this$0;
  public demo.CompilationDemo$Inner(demo.CompilationDemo);
  public java.lang.String label();
}
~~~

Ở kết quả `javac --release 17` được kiểm chứng, field `this$0` giữ tham chiếu outer; constructor thực tế nhận `CompilationDemo`. **Tên field/chiến lược tạo field là chi tiết triển khai của compiler**, không phải thuộc tính public để lập trình dựa vào. Từ các JDK mới, compiler còn có thể tối ưu tránh giữ tham chiếu outer khi không cần; quy tắc ngữ nghĩa Java mới là điều cần dựa vào.

Đối tượng outer còn tác động đến **lifetime**: nếu inner object giữ một tham chiếu mạnh tới outer, garbage collector không thu hồi outer trong khi quan hệ tham chiếu này vẫn còn. Đây là lý do cần cẩn thận khi giữ instance của non-static inner class lâu hơn dự định.

## 6. Local class: nâng biến cục bộ thành trạng thái của object

Local class trong ví dụ được khai báo trong thân method `work`:

~~~java
String suffix = "!";
class Local {
    String label() { return "local:" + (secret + offset) + suffix; }
}
~~~

Source cho phép `Local` đọc `offset` (method parameter) và `suffix` (local variable), dù JVM method stack frame cho `work` không phải nơi lưu trạng thái sống mãi cùng object `Local`. Compiler phải **capture giá trị** cần thiết vào dữ liệu mà object local class có thể truy cập, thường qua synthetic constructor parameters và fields.

Với `javac` trong phép thử, `javap -p` cho lớp `demo.CompilationDemo$1Local` cho thấy các field:

~~~text
final int val$offset;
final java.lang.String val$suffix;
final demo.CompilationDemo this$0;
~~~

`val$offset`, `val$suffix` và `this$0` là **tên compiler sinh**; Java source không được phép dựa vào tên này. Hình thức truyền giá trị vào constructor cần kiểm tra bằng `javap -c -p` hoặc descriptor trong `javap -v`; một số bản hiển thị `javap` có thể biểu diễn constructor local class bằng cách rút gọn hoặc khác với descriptor thực tế.

### Final và effectively final

Biến local/parameter được local hoặc anonymous class sử dụng phải là `final` hoặc **effectively final**: sau khi gán giá trị đúng quy tắc, không bị gán lại theo cách khiến nó mất tính final hiệu dụng.

Ví dụ sau **không biên dịch**:

~~~java
void broken() {
    int count = 1;
    class Local {
        int read() { return count; }
    }
    count++; // làm count không còn effectively final
}
~~~

Đây là trích đoạn trong một class, chủ ý **compile error**. `javac` sẽ báo biến được tham chiếu từ inner class cần final/effectively final. Lý do: nếu local object lưu snapshot của một biến mà method tiếp tục thay đổi, programmer dễ hiểu nhầm đó là một biến chia sẻ được cập nhật live.

**Capture biến tham chiếu không đồng nghĩa bất biến object được tham chiếu.** Nếu một local biến `final List<String> items` được capture, code vẫn có thể gọi `items.add(...)`; chỉ việc gán lại biến `items = ...` mới bị cấm. Cẩn thận với mutation đồng thời và khả năng nhìn thấy trạng thái giữa các thread; captured reference tự nó không thay thế cơ chế đồng bộ.

Local class có **phạm vi tên giới hạn** ở nơi khai báo. Compiler vẫn có thể tạo một `.class` riêng với binary name chứa phần số và tên lớp; không có nghĩa có thể gọi lớp `Local` bằng tên Java source từ ngoài method.

## 7. Anonymous class: biểu thức tạo object đồng thời khai báo một class

Đoạn:

~~~java
Runnable anonymous = new Runnable() {
    @Override public void run() {
        System.out.println("anonymous:" + owner + ":" + offset + suffix);
    }
};
~~~

khai báo một subclass/implementation không tên ở source, ngay tại biểu thức khởi tạo. Compiler tạo một kiểu class riêng, trong ví dụ là `demo.CompilationDemo$1`, implement `Runnable`, và triển khai `run()`. Kết quả `javap -p` từ ví dụ có thể chứa:

~~~text
class demo.CompilationDemo$1 implements java.lang.Runnable {
  final int val$offset;
  final java.lang.String val$suffix;
  final demo.CompilationDemo this$0;
  demo.CompilationDemo$1();
  public void run();
}
~~~

Lưu ý `javap` có thể hiển thị chữ ký constructor rút gọn; cần đọc descriptor bytecode để kiểm tra tham số truyền ngầm. Các field capture có thể đổi tên/biến mất theo phiên bản compiler và tối ưu hóa, nhưng hành vi Java source vẫn phải giữ nguyên.

Anonymous class có thể:
- **Extend một class**, hoặc **implement một interface** được chỉ ra trong biểu thức `new`.
- Override method, thêm field hoặc instance initializer hợp lệ.
- Capture biến local/parameter final hoặc effectively final; ở instance context cũng có thể liên hệ với enclosing instance.

Anonymous class **không có tên đơn giản trong source và không khai báo constructor có tên**, vì vậy muốn khởi tạo phức tạp có thể dùng instance initializer hoặc constructor của supertype, không thể gọi `new AnonymousName()` từ vị trí khác.

Khác với **lambda expression**: `Runnable r = () -> ...` có semantics khác `new Runnable() { ... }`, đặc biệt cách hiểu `this`; lambda thường được compiler hạ thông qua `invokedynamic` và runtime tạo implementation class phù hợp, không nhất thiết sinh `CompilationDemo$$Lambda$....class` lúc compile. Anonymous class ở ví dụ có `CompilationDemo$1.class` thật.

## 8. Quyền truy cập private và nestmates

Một inner class được phép truy cập private field của outer trong Java source, ví dụ `Inner.label()` đọc `owner` và `secret`, dù bytecode nằm trong **file class khác**.

Với class file hiện đại (Java 11+), JVM hỗ trợ quan hệ **nestmate**: các class trong cùng một nest được phép truy cập private member của nhau khi metadata và quy tắc runtime tương ứng hợp lệ. Những thuộc tính quan trọng:

- `NestMembers` trên *nest host*, thường là class cấp cao nhất.
- `NestHost` trên nest member, ví dụ member/local/anonymous class tương ứng.
- `InnerClasses` diễn tả thông tin khai báo kiểu lồng nhau; không phải cơ chế duy nhất để kiểm tra private access.
- `EnclosingMethod` mô tả method hoặc constructor bao quanh đối với local/anonymous class.

Khi compile với đích bytecode cũ không hỗ trợ nestmates, compiler có thể phải sinh **synthetic access methods** để chuyển lời gọi private qua phương thức phụ trợ. Với `--release 17`, hãy quan sát `NestHost`/`NestMembers` và lệnh truy cập trực tiếp; đừng ngầm khẳng định mọi compiler đều phải tạo `access$000` hoặc phải có đúng tên synthetic method nào.

Trong class file, metadata khai báo nesting và metadata nest access là các khái niệm **liên quan nhưng khác nhau**. Một binary name chứa `$` chưa đủ chứng minh quan hệ nestmate hoặc quyền private access; đọc class metadata và xác nhận runtime package/nest host khi cần điều tra.

## 9. Đọc class file bằng javap

Sau khi build thành công ở phần 3, dùng:

~~~bash
javap -classpath out -p 'demo.CompilationDemo$StaticNested'
javap -classpath out -p 'demo.CompilationDemo$Inner'
javap -classpath out -p 'demo.CompilationDemo$1Local'
javap -classpath out -p 'demo.CompilationDemo$1'
~~~

Dấu nháy đơn giữ `$` nguyên vẹn trong Bash/PowerShell. Trong Windows `cmd.exe`, dùng nháy kép thay cho nháy đơn.

Để nhìn sâu hơn:

~~~bash
javap -classpath out -c -p 'demo.CompilationDemo$Inner'
javap -classpath out -v 'demo.CompilationDemo$1Local'
javap -classpath out -v demo.CompilationDemo
~~~

- `-p` hiển thị cả member không public, kể cả field compiler sinh được công cụ hiển thị.
- `-c` in JVM instructions, giúp tìm `new`, `dup`, `invokespecial`, `getfield`, `putfield` và các lệnh truy cập khác.
- `-v` in constant pool, descriptors và class-file attributes như `InnerClasses`, `EnclosingMethod`, `NestHost`, `NestMembers`.

Khi xem **constructor của inner member class**, phân biệt signature mà Java source khai báo với constructor descriptor thật; compiler truyền enclosing object dù source viết `new Inner()`. Với local/anonymous class, biến capture có thể được chuyển qua constructor parameters rồi gán vào fields. Đây là logic tương đương được tạo bởi compiler, không có nghĩa runtime JVM tự đi tìm các biến cục bộ của stack frame đã kết thúc.

Từ Java 9+, nối chuỗi có thể được triển khai bằng `invokedynamic` và `StringConcatFactory`; đừng kỳ vọng luôn thấy `new StringBuilder` trong bytecode. Chi tiết lowering không chỉ phụ thuộc vào việc class có lồng nhau hay không, mà còn phụ thuộc target version và phiên bản compiler.

### Đối chiếu với reflection

Một số API phản ánh quan hệ giữa các khai báo:

| API | Với dạng class tương ứng |
| --- | --- |
| `Class.getName()` | Tên nhị phân, như `demo.CompilationDemo$Inner`. |
| `Class.getCanonicalName()` | Member class: `demo.CompilationDemo.Inner`; local/anonymous: `null`. |
| `Class.getSimpleName()` | Member `Inner`, local `Local`, anonymous là chuỗi rỗng. |
| `Class.getDeclaringClass()` | Member class trả class khai báo trực tiếp; local/anonymous trả `null`. |
| `Class.getEnclosingClass()` | Có thể chỉ class chứa về mặt từ vựng, kể cả local/anonymous. |
| `Class.getEnclosingMethod()` | Local/anonymous khai báo trong method: phản ánh method chứa; member class có thể `null`. |
| `Class.isMemberClass()` / `isLocalClass()` / `isAnonymousClass()` | Xác định loại class theo metadata JVM. |

Không tự phân tích dấu `$` để thay thế các API này: định danh Java cũng cho phép `$` xuất hiện trong tên do lập trình viên đặt, còn phần số của local/anonymous class không ổn định.

## 10. Những quy tắc source Java ảnh hưởng bước lowering

### 10.1. Phải có đúng enclosing instance

Tạo non-static inner class bên trong static context mà không có outer object là compile error:

~~~java
public class WrongOuter {
    class Inner {}

    static void bad() {
        // new Inner(); // lỗi nếu mở comment: thiếu enclosing instance
        WrongOuter outer = new WrongOuter();
        Inner ok = outer.new Inner();
    }
}
~~~

File `WrongOuter.java` ở trên có thể compile vì dòng lỗi được comment. Nếu bỏ comment ở `new Inner()`, javac báo lỗi về non-static context; cách sửa là truyền object qua `outer.new Inner()` hoặc chuyển member class thành static nested nếu nó không cần outer state.

### 10.2. Local/anonymous capture cần final/effectively final

Tái gán `offset` hoặc `suffix` trong `CompilationDemo.work` (nơi được local/anonymous class sử dụng) sẽ làm source không còn hợp lệ. Compiler không “theo dõi biến đổi live” thay cho capture. Nếu cần trạng thái thay đổi có chủ đích, dùng một object giữ trạng thái và xét thêm tính thread-safe, thay vì trông chờ local primitive sẽ được cập nhật vào object đã capture.

### 10.3. Quy tắc `this` của anonymous class và lambda khác nhau

Trong anonymous class, `this` bên trong `run()` là **instance anonymous class**. Trong lambda, `this` nói đến enclosing instance theo lexical context. Khi chuyển anonymous class thành lambda để “ngắn hơn”, phải kiểm tra các tham chiếu `this`, `super`, scope và serialization; không coi hai hình thức luôn tương đương về semantic.

### 10.4. Số class file không luôn bằng số từ khóa `class`

Một anonymous class không chứa từ khóa khai báo `class` nhưng vẫn thường có file class. Một lambda không nhất thiết có class file riêng trong output của `javac`. Nested record, enum, synthetic helper hoặc lựa chọn của compiler cũng làm output khác nhau. Vì vậy hãy đọc kết quả build thực tế, không tính thủ công chỉ từ token trong source.

## 11. Kiểm thử và đóng gói sau khi biên dịch

Khi dựng JAR hoặc copy artifact, hãy đưa các class thực sự cần thiết vào output. Chỉ giữ `CompilationDemo.class` rồi bỏ các file `CompilationDemo$*.class` sẽ khiến chương trình có thể thất bại khi đường chạy cần một class đã bị thiếu, thường dẫn tới `NoClassDefFoundError` hoặc lỗi liên kết tương ứng.

Ví dụ tạo JAR sau build:

~~~bash
jar --create --file compilation-demo.jar -C out .
jar --list --file compilation-demo.jar
java -cp compilation-demo.jar demo.CompilationDemo
~~~

Các lệnh dùng công cụ JAR của JDK 17+. Nội dung JAR sẽ gồm các entry theo package `demo/`; thứ tự entry phụ thuộc công cụ. Nếu có script loại bỏ tệp chứa `$`, xác nhận quy tắc exclude không vô tình xóa member/local/anonymous class.

Khi debug:
- **`NoClassDefFoundError` ở production:** kiểm tra output và JAR có đủ class `$...` tương ứng; so sánh classpath/module path.
- **`ClassNotFoundException` khi reflect:** kiểm tra có truyền đúng **binary name** cho member class, chẳng hạn `demo.CompilationDemo$Inner`.
- **`cannot find symbol` với `Local`:** kiểm tra local class có nằm ngoài lexical scope của nó không.
- **`local variables ... must be final or effectively final`:** xem biến capture đã bị gán lại ở đâu.
- **Inner class giữ outer object quá lâu:** cân nhắc thiết kế static nested class hoặc tách top-level class nếu không cần enclosing instance.
- **Khác nhau giữa các bản JDK:** không khóa cứng tên field `this$0`, `val$...`, chỉ số local/anonymous hoặc lệnh bytecode; kiểm tra source semantics và class-file version.

## 12. Bảng so sánh để ghi nhớ

| Câu hỏi | Static nested | Inner member | Local | Anonymous |
| --- | --- | --- | --- | --- |
| Có tên khai báo Java? | Có | Có | Có, chỉ trong scope | Không |
| Nơi xuất hiện | Body của type | Body của type | Block | Biểu thức `new` |
| Dạng tên class sinh tiêu biểu | `Outer$Nested` | `Outer$Inner` | `Outer$1Local` | `Outer$1` |
| Phải có enclosing instance? | Không | Có trong cách khởi tạo instance thông thường | Tùy context khai báo và semantics | Tùy context |
| Có thể capture local effectively final? | Không chỉ vì được lồng trong type | Không theo nghĩa lexical local capture của method; dùng outer fields | Có | Có |
| Có constructor có tên trong source? | Có thể khai báo | Có thể khai báo | Có thể khai báo | Không |
| Class file riêng? | Có | Có | Có | Có |
| Có canonical name? | Có | Có | Không | Không |

Các trường hợp generic, static context, enum/record hoặc compiler không phải `javac` có thể thay đổi chi tiết biểu diễn; bảng nhấn mạnh những khác biệt cốt lõi từ Java source đến bytecode.

## 13. Bài tập tự kiểm tra

**Bài 1.** Trong ví dụ, vì sao `StaticNested` không cần truyền `CompilationDemo` nhưng `Inner` lại có thể cần?  
**Đáp án:** static nested class không liên kết với một enclosing object; inner member class có semantics gắn với một enclosing instance, và `javac` phải bảo toàn quan hệ đó khi sinh class file.

**Bài 2.** Tại sao `offset` có thể xuất hiện dưới dạng field trong `CompilationDemo$1Local.class`?  
**Đáp án:** local object cần sử dụng giá trị `offset` khi thực thi method của nó; compiler chuyển capture qua constructor/field để không phụ thuộc vào stack frame của method bên ngoài.

**Bài 3.** Nếu gọi `new CompilationDemo("A").work(5)` một nghìn lần thì có một nghìn class `$1Local` khác nhau không?  
**Đáp án:** Không. Một class declaration được biên dịch thành class; mỗi invocation có thể tạo thêm **instance** của class đó.

**Bài 4.** Thêm `suffix = "?";` trước lệnh tạo `Local` có gây lỗi không?  
**Đáp án:** Có, vì biến `suffix` được capture không còn effectively final theo các quy tắc Java.

**Bài 5.** Khi biên dịch với Java 17, có cần compiler luôn sinh method `access$000` cho inner class đọc private outer field không?  
**Đáp án:** Không. Class-file nestmates từ Java 11 cho phép private access phù hợp mà không buộc phải sinh bridge/accessor kiểu cũ.

**Bài 6.** `Class.getDeclaringClass()` của local class trả class chứa hay `null`?  
**Đáp án:** `null`; `getEnclosingClass()` và `getEnclosingMethod()` là các API phù hợp để tìm ngữ cảnh từ vựng.

**Bài 7.** Nếu `CompilationDemo$1.class` biến thành `CompilationDemo$2.class` sau chỉnh sửa source, đó có nhất thiết là lỗi không?  
**Đáp án:** Không. Số thứ tự của anonymous/local class là chi tiết phát sinh; đừng đưa vào cấu hình hay public contract.

## 14. Tài liệu chuẩn để đối chiếu

- [Java Language Specification 17 — §8.1.3 Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3)
- [Java Language Specification 17 — §14.3 Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3)
- [Java Language Specification 17 — §15.9.5 Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5)
- [Java Virtual Machine Specification 17 — Class-file attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7)

**Kết luận kiến thức:** `javac` phải biến khai báo lồng nhau trong source thành class file JVM riêng, bảo toàn lexical scope, enclosing instance, captured values và access rules. Hãy dùng source-level semantics để thiết kế chương trình; dùng `javap`, class-file metadata và kết quả compile thực tế để hiểu chi tiết lowering, đồng thời tránh phụ thuộc vào tên synthetic hoặc số thứ tự do compiler sinh.
