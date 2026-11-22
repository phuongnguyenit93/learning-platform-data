# Phân biệt phương thức khởi tạo lớp <clinit> với constructor <init> trong Java

## 1. Hai thời điểm khởi tạo khác nhau

Khi đọc source Java, ta quen với từ khóa **static**, phương thức khởi tạo đối tượng (constructor), phép **new** và thứ tự chạy các khối lệnh. Khi đọc bytecode, JVM dùng hai tên phương thức đặc biệt:

- **<clinit>** là phương thức khởi tạo **lớp hoặc interface** ở cấp JVM (class/interface initialization method). Trong bytecode do javac tạo, nó chứa mã khởi tạo các trường static và các khối static initializer phải chạy tại thời điểm khởi tạo lớp. JVM quản lý việc gọi nó trong tiến trình khởi tạo lớp.
- **<init>** là phương thức khởi tạo **instance** ở cấp JVM (instance initialization method); mỗi constructor Java tương ứng với một phương thức <init> có descriptor phù hợp. Nó được thực thi khi tạo đối tượng qua constructor, theo chuỗi constructor của lớp và lớp cha.

Hai phương thức cùng có chữ “init”, nhưng khác **đối tượng được khởi tạo**, **điều kiện kích hoạt**, **số lần chạy**, **thứ tự phụ thuộc** và **cách xuất hiện trong bytecode**. Sự phân biệt này rất quan trọng trong chủ đề class loading: JVM có thể tải (load), liên kết (link), thậm chí lấy Class<?> cho một lớp trước khi thực hiện <clinit>. Ngược lại, constructor <init> thuộc giai đoạn khởi tạo một đối tượng cụ thể.

> Ghi nhớ: **<clinit> chuẩn bị trạng thái static của một Class runtime; <init> chuẩn bị trạng thái của từng instance.** Không phải mọi lớp đều có mã <clinit> và không phải mọi lần dùng một tên lớp đều khiến <clinit> chạy.

## 2. So sánh trực tiếp

| Tiêu chí | <clinit> | <init> |
| --- | --- | --- |
| Ngữ nghĩa | Khởi tạo class/interface | Khởi tạo đối tượng |
| Cú pháp nguồn tương ứng | static field initializer và static initializer block | Constructor Java, kết hợp mã khởi tạo instance |
| Tên trong JVM class file | Tên đặc biệt <clinit> | Tên đặc biệt <init> |
| Chữ ký thường gặp | Không tham số, trả void: **()V** | Tham số tùy constructor, trả void; ví dụ **()V**, **(I)V** |
| Số lượng trong một class file | Tối đa một <clinit>; có thể không có | Có thể có nhiều <init> khi overload; lớp thông thường thường có ít nhất một constructor, kể cả mặc định |
| Ai kích hoạt | Cơ chế class/interface initialization của JVM theo các điều kiện đặc tả | Chuỗi gọi constructor do bytecode thực hiện bằng **invokespecial** |
| Số lần chạy | Tối đa một lần thực thi khởi tạo thành công cho từng Class runtime; thất bại đưa lớp sang trạng thái lỗi | Mỗi lần một constructor được gọi trong quá trình tạo instance; có thể lặp nhiều lần |
| Gắn với đối tượng | Không có **this** của instance | Có receiver **this** trong quá trình khởi tạo đối tượng |
| Quan hệ kế thừa | Không kế thừa <clinit>; JVM điều phối khởi tạo các kiểu phụ thuộc | Constructor không được kế thừa; constructor lớp con gọi chuỗi constructor lớp cha |
| Từ Java source có gọi trực tiếp được không? | Không | Gọi bằng **new**, **this(...)**, **super(...)**, hoặc cơ chế reflection/API tương ứng; không viết tên <init> trực tiếp |

Trong bytecode, dấu ngoặc nhọn và hai dấu < > quanh tên là một phần của **tên đặc biệt do JVM định nghĩa**. Chúng không phải những tên phương thức Java mà ta được phép tự khai báo trong source.

## 3. <clinit> được hình thành như thế nào?

Một lớp Java có thể chứa các khai báo sau:

~~~java
class Settings {
    static int port = 8080;           // Khởi tạo trường static bằng biểu thức
    static String host;

    static {                          // Khối static initializer
        host = "localhost";
        System.out.println("Settings initialized");
    }
}
~~~

javac có thể biên dịch các thao tác static có tác dụng lúc chạy thành một phương thức **<clinit>()V**. Khi JVM khởi tạo Settings, nó thực hiện các chỉ thị đó theo thứ tự thích hợp. **Không có hàm main hoặc constructor nào phải gọi <clinit> bằng tên.**

Các phép gán giá trị cho biến static và khối static initializer được thực hiện theo **thứ tự văn bản** trong source đối với các initializer cần thực thi, sau khi áp dụng các quy tắc khởi tạo lớp cha/interface liên quan. Trước khi mã <clinit> chạy, vùng nhớ static đã nhận **giá trị mặc định** tương ứng với kiểu (0, false, null...), trong giai đoạn chuẩn bị (preparation). Do đó:

- static int count; không cần câu lệnh gán 0 tường minh để có giá trị 0 ban đầu.
- static int count = compute(); tạo mã thực thi khi khởi tạo lớp; giá trị được ghi lúc chạy.
- static final int LIMIT = 100; là ví dụ **constant variable** với biểu thức hằng ở thời điểm biên dịch; JVM có thể gán giá trị theo thuộc tính ConstantValue của class file, và javac không cần tạo <clinit> riêng chỉ vì trường ấy.
- static final String ID = makeId(); **không** phải hằng thời điểm biên dịch chỉ vì có static final; lời gọi makeId() cần diễn ra khi lớp được khởi tạo.

Nếu một lớp không có công việc khởi tạo static tại runtime, compiler **có thể không phát sinh <clinit>**. Điều này không có nghĩa lớp chưa từng được JVM khởi tạo; “class initialization” là trạng thái/quy trình của JVM, còn <clinit> là phương thức thực thi khi có mã cần chạy.

**Interface** cũng có thể có <clinit> (chẳng hạn khi trường static có initializer không phải biểu thức hằng). Interface không có instance constructor <init> vì không thể tạo đối tượng interface trực tiếp.

## 4. Constructor <init> được hình thành như thế nào?

Constructor trong Java source:

~~~java
class Account {
    private final String id;

    Account() {
        this("guest");          // Chuyển tới constructor khác cùng lớp
    }

    Account(String id) {
        this.id = id;
    }
}
~~~

Trong class file có các phương thức tên đặc biệt **<init>**, được phân biệt bởi danh sách tham số: **<init>()V** và **<init>(Ljava/lang/String;)V**. Giá trị trả về ở dạng descriptor là V (void); một constructor không thể khai báo kiểu trả về trong Java source.

Một số thuộc tính quan trọng:

1. Một lớp có thể khai báo nhiều constructor overload, tức có nhiều <init>, trong khi chỉ có tối đa một <clinit>.
2. Nếu không khai báo constructor, javac thường tự sinh constructor mặc định phù hợp với quy tắc ngôn ngữ. Điều này **không** tạo thêm <clinit>.
3. Một constructor có thể ủy quyền qua **this(...)** hoặc gọi constructor superclass qua **super(...)** (tường minh hoặc ngầm định). Ở mức bytecode, lời gọi constructor dùng chỉ thị **invokespecial** tới <init> phù hợp.
4. Constructor không được kế thừa. Nếu subclass không khai báo constructor, compiler tạo constructor của subclass để khởi tạo superclass theo đúng điều kiện hợp lệ.
5. Các instance field initializers và instance initializer blocks được biên dịch thành mã trong quá trình chạy <init>. Nếu có chuỗi this(...) trong cùng lớp, các đoạn initializer của lớp ấy chạy **một lần** tại constructor cuối cùng gọi super(...), không chạy lặp ở từng constructor ủy quyền.
6. Không tồn tại API Java source tên Account.<init>(); cách tạo đối tượng thông thường là **new Account()** hoặc **new Account("x")**, với việc cấp phát bộ nhớ và gọi constructor được JVM đảm nhiệm.

Phân biệt thao tác **cấp phát** với **khởi tạo instance**: bộ nhớ cho đối tượng được chuẩn bị với giá trị trường mặc định trước khi mã khởi tạo instance/constructor làm thay đổi các giá trị đó. Việc dùng các API cấp thấp hoặc cơ chế đặc biệt có thể tránh chuỗi constructor thông thường; không dùng ngoại lệ này làm mô hình mặc định khi học Java.

## 5. Ví dụ hoàn chỉnh: <clinit> một lần, <init> cho từng đối tượng

Tạo file **InitOrderDemo.java** với toàn bộ chương trình Java 17+:

~~~java
public class InitOrderDemo {
    static class Target {
        static int staticNumber = trace("S1 - static field");

        static {
            System.out.println("S2 - static block");
        }

        int number = trace("I1 - instance field");

        {
            System.out.println("I2 - instance block");
        }

        Target() {
            System.out.println("I3 - constructor body");
        }
    }

    static int trace(String label) {
        System.out.println(label);
        return 10;
    }

    public static void main(String[] args) {
        System.out.println("M - before first new");
        new Target();

        System.out.println("M - before second new");
        new Target();
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 InitOrderDemo.java
java InitOrderDemo
~~~

**Stdout chính xác:**

~~~text
M - before first new
S1 - static field
S2 - static block
I1 - instance field
I2 - instance block
I3 - constructor body
M - before second new
I1 - instance field
I2 - instance block
I3 - constructor body
~~~

**Giải thích từng giai đoạn:**

- Trước câu lệnh new Target() đầu tiên, lớp Target có thể đã được load/link nhưng chưa nhất thiết initialized. Khi cần tạo instance đầu tiên, JVM bảo đảm Target được khởi tạo. Mã static của Target chạy theo thứ tự **S1 → S2**.
- Sau khi bảo đảm Target đã initialized, JVM thực hiện công việc tạo đối tượng và constructor. Mã instance field initializer, instance initializer block rồi thân constructor chạy theo thứ tự **I1 → I2 → I3**.
- Với new Target() lần hai, Target đã được khởi tạo thành công nên **S1 và S2 không chạy lại**. Một instance mới vẫn chạy **I1 → I2 → I3**.
- Đối tượng InitOrderDemo bao ngoài không được tạo; việc Target là **static nested class** không buộc nó có một instance của lớp bao ngoài. Quan hệ lồng tên không tự động biến một constructor thành class initializer.

Giá trị 10 do trace() trả về được gán lần lượt cho staticNumber và number; ở đây ta quan sát **thời điểm gọi trace**, không cần in giá trị cuối cùng của trường.

## 6. Trigger của `<clinit>` nhìn từ việc tạo object

Một class có thể đã load/link nhưng chưa initialized. `new Target()` yêu cầu class initialization trước constructor nếu lớp chưa khởi tạo; `Target.class` không tự tạo yêu cầu ấy. Đọc constant variable có thể được compiler inline. Bốn lệnh `new`, `getstatic`, `putstatic`, `invokestatic` cùng reflection/MethodHandle được phân tích đầy đủ trong bài riêng về thao tác chủ động kích hoạt.

## 7. Thử phân biệt metadata và instance

`Class.forName("SomeType", false, loader)` có thể trả đối tượng `Class<?>` mà chưa yêu cầu khởi tạo `SomeType`. Nhưng `type.getDeclaredConstructor().newInstance()` thực sự tạo object và đòi initialization trước khi constructor thực hiện. Điều này phân biệt rõ việc **biết thông tin về kiểu** với **khởi tạo một object của kiểu**.

## 8. Kế thừa tạo hai luồng thứ tự riêng

Với `new Child()` khi `Child extends Parent`, JVM initialize `Parent` trước phần static của `Child` nếu cần; sau đó, constructor `Child.<init>` gọi `Parent.<init>` trước phần thân riêng của con. Đây là **hai chuỗi khác nhau**: class initialization liên quan trạng thái static của các lớp, còn constructor chain liên quan từng object. Bài về thứ tự superclass chứa chương trình quan sát static đầy đủ; ví dụ `InitOrderDemo` mục 5 đã làm rõ quá trình theo từng instance.

## 9. Quan sát <clinit> và <init> bằng javap

Sau khi biên dịch ví dụ InitOrderDemo, javac thông thường tạo hai class file:

~~~text
InitOrderDemo.class
InitOrderDemo$Target.class
~~~

Trên PowerShell hoặc shell hiểu ký tự $, đặt tên file/lớp trong **dấu nháy đơn** để tránh bị thay thế biến:

~~~bash
javap -p -c -v 'InitOrderDemo$Target'
~~~

Ở phần constant pool và biểu diễn bytecode chi tiết, hãy tìm các tên đặc biệt:

- **<clinit>:()V**, gắn với các lệnh gọi trace("S1 - static field"), gán Target.staticNumber và in "S2 - static block". Khối static và initializer static được gom theo thứ tự vào một phương thức class initialization.
- **<init>:()V**, gắn với constructor Target(). Bên trong có lời gọi **invokespecial** tới constructor của superclass, sau đó mã khởi tạo trường number, instance block và thân constructor.
- **invokestatic** có thể xuất hiện khi gọi phương thức static trace; **putstatic** khi gán trường staticNumber; **putfield** khi gán trường instance number. Mỗi chỉ thị cho biết loại thao tác, không có nghĩa cứ thấy invokestatic bất kỳ là một class initializer riêng.

Bạn cũng có thể chạy:

~~~bash
javap -p -c InitOrderDemo
~~~

để xem mã trong main. Thao tác **new InitOrderDemo$Target** ở bytecode kết hợp với lời gọi **invokespecial ...<init>** sau khi cấp phát đối tượng. JVM kiểm tra/tiến hành class initialization khi cần trước khi tạo instance; source không hiện ra một lệnh gọi trực tiếp tới <clinit>.

Các dấu mốc bytecode chính:

| Dấu hiệu | Ý nghĩa |
| --- | --- |
| **<clinit>()V** | Mã class/interface initialization khi compiler cần tạo |
| **<init>(...)V** | Một constructor với tham số đúng descriptor |
| **new** | Cấp phát instance của class; nếu cần sẽ kích hoạt class initialization |
| **invokespecial ...<init>** | Gọi constructor cụ thể |
| **getstatic / putstatic** | Truy cập trường static; có thể là điểm kích hoạt initialization |
| **getfield / putfield** | Truy cập trường instance của object |
| **invokestatic** | Gọi phương thức static; có thể là điểm kích hoạt initialization |

**Lưu ý:** javap có thể in constructor dưới dạng tên hiển thị thân thiện (ví dụ InitOrderDemo$Target()) thay vì nguyên văn <init> ở một số dòng, còn tùy chọn -v và constant pool cho thấy tên JVM rõ hơn. Không phụ thuộc chính xác số thứ tự constant pool, offset hoặc cách trình bày của javap qua các bản JDK.

## 10. Phạm vi “một lần” của `<clinit>`

Một runtime class (binary name và defining loader) hoàn tất initialization thành công một lần, được JVM điều phối giữa các thread; một loader khác tự định nghĩa lớp cùng tên có trạng thái riêng. `<init>` không có quy tắc một lần theo class: constructor chạy mỗi khi một instance được tạo thông thường. Chi tiết concurrency và vòng chờ được học tại bài đồng bộ initialization.

## 11. Khi <clinit> lỗi, hệ quả khác constructor lỗi

Nếu code trong <clinit> phát sinh exception, JVM có quy tắc đặc biệt cho initialization failure:

- Nếu throwable là một **Error**, JVM có thể chuyển tiếp chính Error đó.
- Nếu throwable không phải Error (chẳng hạn RuntimeException thoát khỏi static initializer), JVM thường bọc nguyên nhân trong **ExceptionInInitializerError** cho lần thất bại khởi tạo.
- Các lần sử dụng tiếp theo của cùng lớp ở trạng thái erroneous thường gặp **NoClassDefFoundError** báo rằng không thể initialize lớp. Lỗi này **không đồng nghĩa** với không tìm thấy file .class trên classpath.

Ví dụ đoạn source hợp lệ (minh họa, không phải chương trình độc lập):

~~~java
class Broken {
    static final int VALUE = read();

    static int read() {
        throw new IllegalStateException("bad config");
    }
}
~~~

Khi có một active use yêu cầu khởi tạo Broken, lỗi từ read() làm class initialization thất bại; JVM **không chạy lại read()** cho mỗi lần đọc Broken.VALUE về sau. Để phục hồi, chương trình thường cần sửa nguyên nhân và sử dụng một định nghĩa class runtime mới hoặc khởi động lại phần ứng dụng thích hợp.

Ngược lại, nếu **constructor <init>** của một class đã được khởi tạo bình thường ném exception, lần tạo instance ấy thất bại. Điều đó **không tự động biến cả class thành erroneous**: sau khi xử lý nguyên nhân, những lần gọi constructor sau vẫn có thể thành công. Đây là khác biệt rất lớn khi vận hành ứng dụng.

## 12. Ba bẫy khi phân biệt hai phương thức

- `javap` thường hiển thị `<clinit>` dưới nhãn `static {};`, dù trong đó có nhiều field initializer và nhiều khối static.
- Một class có thể không có `<clinit>` nếu không cần công việc static runtime; Java có thể sinh constructor mặc định khi source không khai báo constructor.
- Outer class và nested class là hai runtime classes riêng. Chỉ quan hệ lồng nhau không bảo đảm outer initializer chạy trước initializer của nested class.

## 13. Tìm lỗi theo cấp class hay instance

| Hiện tượng | Vị trí kiểm tra | Hệ quả |
| --- | --- | --- |
| Static field initializer/block ném exception | `<clinit>`, `ExceptionInInitializerError.getCause()`, superclass | Class có thể erroneous và không tự retry |
| Instance field initializer/constructor ném exception | `<init>`, `super(...)`, body constructor | Instance cụ thể thất bại; class không tự động erroneous |
| `javap` hiện nhiều `<init>` | Constructor overload | Không có nghĩa `<clinit>` chạy nhiều lần |

Bài về `ExceptionInInitializerError` đi sâu vào quy tắc lỗi; ở đây hãy xác định **đang khởi tạo class hay đang khởi tạo instance** trước khi chọn cách khắc phục.

## 14. Tự kiểm tra hiểu bài

1. **Hai lần new Target() nhưng một lần in từ static block. Vì sao?** Class initialization thành công một lần cho Class runtime của Target; mỗi instance vẫn chạy constructor.
2. **static final int LIMIT = 5; có nhất thiết tạo <clinit> không?** Không. Đó là constant variable và compiler có thể dùng ConstantValue/inlining; không cần mã runtime chỉ để gán giá trị này.
3. **static final Object VALUE = new Object(); có giống LIMIT không?** Không. new Object() không phải constant expression, nên việc đọc trường static ấy có thể kích hoạt class initialization.
4. **Có thể có <init>()V và <init>(I)V trong một class không?** Có; đó là hai constructor overload. <clinit> thì tối đa một.
5. **Class.forName(name, false, loader) đã có Class<?> thì static block chắc chắn đã chạy chưa?** Chưa; false không yêu cầu initialization. Trạng thái thực tế vẫn có thể là đã initialized do thao tác khác trước đó.
6. **Lỗi constructor có đồng nghĩa lớp bị erroneous không?** Không; lỗi class initialization và lỗi tạo một instance có ngữ nghĩa khác nhau.
7. **Trong new Child(), static block của Parent hay Child chạy trước khi cả hai chưa initialized?** Parent trước Child. Nhưng instance constructor Parent và Child chạy sau giai đoạn initialization thích hợp.
8. **Nếu cùng binary name được định nghĩa bởi hai class loader, <clinit> có thể chạy hai lần trên toàn JVM không?** Có, mỗi Class runtime riêng có chu trình initialization của nó.

## Tài liệu chuẩn

- **JLS §12.4 – Initialization of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- **JLS §12.5 – Creation of New Class Instances:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5
- **JLS §8.8 – Constructor Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8
- **JLS §8.7 – Static Initializers:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7
- **JVM Specification §2.9 – Special Methods:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.9
- **JVM Specification §5.5 – Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **Class.forName Java 17 API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)
