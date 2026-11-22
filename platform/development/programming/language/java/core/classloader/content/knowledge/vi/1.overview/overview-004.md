# Phân biệt nạp lớp, liên kết và khởi tạo trong Java

## 1. Mục tiêu và bức tranh tổng quan

Khi JVM sử dụng một lớp, ba khái niệm thường bị gọi chung là “load class”, nhưng thực chất chúng làm ba công việc khác nhau:

1. **Nạp lớp (loading):** tìm hoặc tạo biểu diễn của lớp/giao diện trong JVM từ tên và định nghĩa của nó.
2. **Liên kết (linking):** kiểm tra tính hợp lệ, chuẩn bị trạng thái tĩnh và xử lý các tham chiếu ký hiệu để lớp có thể được sử dụng an toàn.
3. **Khởi tạo (initialization):** thực thi logic khởi tạo biến tĩnh và khối static của lớp/giao diện vào thời điểm Java quy định.

Một mô hình đọc nhanh:

~~~text
Mã nguồn .java
  │ javac (biên dịch trước khi chạy)
  ▼
Bytecode .class
  │
  ▼
LOADING
  ├─ Tìm bytecode / định nghĩa lớp
  ├─ Tạo biểu diễn runtime và đối tượng java.lang.Class
  └─ Xác định lớp qua (tên nhị phân, defining class loader)
  │
  ▼
LINKING
  ├─ Verification: kiểm tra bytecode và các ràng buộc an toàn
  ├─ Preparation: cấp phát/trang bị giá trị ban đầu cho static fields
  └─ Resolution: đổi tham chiếu ký hiệu thành thực thể runtime
  │
  ▼
INITIALIZATION
  ├─ Khởi tạo những lớp/interface tiên quyết theo quy tắc JVM
  └─ Chạy mã khởi tạo static của chính lớp (nếu có)
  │
  ▼
Sử dụng lớp: tạo instance, gọi phương thức, đọc/ghi trạng thái...
~~~

**Điểm then chốt:** lớp đã được nạp không có nghĩa là nó đã được khởi tạo; lớp có thể đã được liên kết mà khối static vẫn chưa chạy. JVM có quyền giải quyết nhiều tham chiếu ký hiệu theo kiểu **lazy**, nên không nên giả định rằng toàn bộ công việc resolution đều hoàn tất ngay khi lần đầu thấy lớp.

## 2. Nạp lớp (loading) thực sự làm gì?

JVM cần một định nghĩa runtime cho kiểu được nhắc tới. Với lớp do lập trình viên khai báo, nó thường dùng một **class loader** để tìm bytecode và tạo định nghĩa lớp. Bộ nạp lớp có thể lấy bytecode từ classpath, module, JAR, mạng hoặc nguồn riêng theo thiết kế ứng dụng. Cơ chế delegation thường cho loader cha cơ hội xử lý trước; các custom loader có thể có chính sách khác.

Kết quả có đối tượng **java.lang.Class** đại diện cho kiểu. JVM dùng **tên nhị phân + defining class loader** để phân biệt các định nghĩa lớp: hai loader khác nhau có thể tạo ra hai lớp khác nhau dù cùng tên đầy đủ. Vì vậy, ở môi trường plugin/container, hai lớp cùng tên chưa chắc ép kiểu được cho nhau.

Loading **không chạy** static block, không gọi constructor và không tự tạo instance của lớp. Mảng có quy tắc tạo lớp mảng riêng do JVM thực hiện; tạo một mảng chứa phần tử kiểu Foo không đồng nghĩa với khởi tạo Foo.

Cần phân biệt thao tác yêu cầu loader và kết quả JVM có thể thực hiện: **ClassLoader.loadClass("pkg.Foo")** theo hợp đồng thông thường trả về Class mà không chủ động khởi tạo Foo; việc JVM nạp hoặc liên kết những kiểu liên quan có thể diễn ra khi cần. Đừng dùng các log nạp lớp để suy luận rằng logic static đã chạy.

## 3. Liên kết (linking): ba hoạt động với trách nhiệm riêng

| Hoạt động | Ý nghĩa | Điều không được suy diễn |
| --- | --- | --- |
| **Verification** (xác minh) | Kiểm tra cấu trúc và tính hợp lệ của bytecode/ràng buộc kiểu; có thể báo VerifyError khi định nghĩa không hợp lệ. | Không phải bước thực thi hàm static hay constructor. |
| **Preparation** (chuẩn bị) | Chuẩn bị lưu trữ cho static fields và giá trị mặc định của chúng; với constant variables thích hợp, giá trị từ ConstantValue có thể được thiết lập ngay trong bước này. | Không chạy biểu thức khởi tạo static tùy ý của chương trình. |
| **Resolution** (phân giải) | Biến các symbolic references trong constant pool thành tham chiếu runtime tương ứng: lớp, field, method...; kiểm tra khả năng truy cập/ràng buộc khi cần. | Không nhất thiết phân giải tất cả trong một lần hoặc đúng một thời điểm cố định. |

Ví dụ, khai báo:

~~~java
class Sample {
    static int counter = 42;
    static final int LIMIT = 10;
    static final String LABEL = "ready";
    static final Object TOKEN = new Object();
}
~~~

Trong **preparation**, các trường static được cấp trạng thái mặc định: kiểu int thông thường bắt đầu là 0, tham chiếu Object mặc định null. Hai **constant variables** LIMIT và LABEL có giá trị constant expression, được biểu diễn bằng ConstantValue và có thể được thiết lập theo quy tắc preparation. Ngược lại, **counter = 42** và **new Object()** là công việc của initialization: chúng không được thực thi chỉ vì class đã chuẩn bị xong.

Đừng xem bảng trên như một danh sách sự kiện có thể nhìn thấy đầy đủ qua log. Java Virtual Machine Specification cho phép **resolution xảy ra muộn**, thậm chí chỉ khi một tham chiếu được sử dụng. Sự xuất hiện của lỗi như NoSuchMethodError hoặc IllegalAccessError có thể phản ánh một tham chiếu vừa được phân giải trong lúc chạy, không nhất thiết là khi JVM lần đầu load lớp.

## 4. Khởi tạo (initialization): thời điểm mã static thực sự chạy

Initialization là giai đoạn JVM thực thi phương thức khởi tạo lớp đặc biệt **<clinit>** (nếu compiler tạo ra) từ các static field initializers và static initializer blocks, theo **thứ tự xuất hiện trong mã nguồn**. Đó không phải constructor của đối tượng. Constructor chạy mỗi khi tạo một instance thích hợp; initialization của một định nghĩa lớp thành công thông thường chỉ diễn ra **một lần trong vòng đời của Class tương ứng**.

Trước khi khởi tạo một class, JVM bảo đảm khởi tạo superclass cần thiết và các superinterface thuộc diện quy định (đáng chú ý superinterface khai báo default method). Việc khởi tạo một interface thông thường không mặc nhiên khởi tạo tất cả superinterface của nó. Trình tự và việc đồng bộ giữa các thread do JVM kiểm soát: thread khác cần sử dụng class có thể phải đợi quá trình khởi tạo đang diễn ra. Nếu initialization thất bại, class có thể bị đánh dấu trạng thái lỗi và các lần sử dụng sau gặp lỗi liên quan.

**Lưu ý về giá trị trong static initialization:** static fields đã có trạng thái mặc định từ preparation. Nếu một static initializer gọi phương thức đọc một field được gán ở phần mã nằm phía sau, phương thức có thể quan sát giá trị mặc định (ví dụ 0), không phải giá trị cuối cùng. Không đánh đồng cấp giá trị mặc định với việc thực thi các dòng gán.

## 5. Khi nào một thao tác làm class được khởi tạo?

Theo các điều kiện của Java Language Specification, các hành vi **active use** tiêu biểu dưới đây dẫn tới initialization của class tương ứng nếu class chưa được khởi tạo:

| Thao tác | Khởi tạo lớp đích? | Giải thích |
| --- | --- | --- |
| Tạo đối tượng bằng **new Foo()** | **Có** | Foo cần được khởi tạo trước khi tạo instance. |
| Đọc/ghi **Foo.staticField** không phải constant variable | **Có** | Khởi tạo **lớp khai báo field thực sự**, không nhất thiết là tên lớp viết bên trái dấu chấm. |
| Gọi **Foo.staticMethod()** | **Có** | Lớp khai báo phương thức static được khởi tạo trước lời gọi. |
| **Class.forName("pkg.Foo")** | **Có, theo mặc định** | Dạng một đối số yêu cầu load/link/initialize kiểu tìm được. |
| **Class.forName(name, false, loader)** | **Không chủ động khởi tạo** | Thích hợp để lấy Class và trì hoãn initialization. |
| **loader.loadClass(name)** | **Không chủ động khởi tạo** | Trả Class theo hợp đồng của phương thức; class có thể được link. |
| **Foo.class** | **Không** | Class literal không phải active use làm chạy static block. |
| **new Foo[3]** | **Không khởi tạo Foo** | Tạo class mảng/đối tượng mảng; chưa tạo instance Foo. |
| Đọc **Foo.CONSTANT** với compile-time constant primitive/String | **Thông thường không** | Compiler có thể thay bằng hằng ngay trong bytecode của caller, không phát sinh getstatic. |
| Truy cập **static final** khởi tạo bằng lời gọi hàm hoặc tạo object | **Có khi field được đọc trực tiếp** | final không đồng nghĩa với compile-time constant. |

Ví dụ **Parent.X** khi X thực ra được khai báo trong Parent và được truy cập qua tên Child sẽ khởi tạo **Parent**, không mặc nhiên khởi tạo Child. Một interface có quy tắc initialization riêng: việc gọi static method hoặc đọc static field không phải constant variable của interface cũng có thể kích hoạt khởi tạo interface đó.

Đối với reflection, việc chỉ lấy đối tượng Class hoặc xem metadata chưa cho phép kết luận static initializer chạy; những thao tác như đọc static field bằng reflection hay gọi static method bằng reflection có thể kích hoạt initialization. Tương tự, các cơ chế MethodHandle, lần khởi động JVM hay API đặc biệt có quy tắc liên quan: bảng trên trình bày **các trường hợp cốt lõi**, không phải danh sách đầy đủ mọi trigger của đặc tả.

## 6. Ví dụ chạy được: chứng minh “có Class” khác “đã chạy static”

Tạo tệp **LoadLinkInitDemo.java**:

~~~java
public class LoadLinkInitDemo {
    static class Target {
        static final int COMPILE_TIME_CONST = 7;

        static int value = initValue();

        static {
            System.out.println("Target: static block");
        }

        static int initValue() {
            System.out.println("Target: init value");
            return 42;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("1. constant = " + Target.COMPILE_TIME_CONST);

        Class<?> type = Target.class;
        System.out.println("2. class literal = " + type.getSimpleName());

        Class.forName(type.getName(), false, type.getClassLoader());
        System.out.println("3. forName(false) completed");

        System.out.println("4. value = " + Target.value);
        System.out.println("5. value again = " + Target.value);
    }
}
~~~

Chạy với Java 17 trở lên:

~~~bash
javac LoadLinkInitDemo.java
java LoadLinkInitDemo
~~~

Stdout kỳ vọng của chương trình:

~~~text
1. constant = 7
2. class literal = Target
3. forName(false) completed
Target: init value
Target: static block
4. value = 42
5. value again = 42
~~~

Giải thích từng mốc:

1. **COMPILE_TIME_CONST** là constant variable: compiler có thể in-line giá trị 7 vào caller, nên chưa cần initialization của Target.
2. **Target.class** tạo/lấy đối tượng Class mà không khởi tạo Target. Lớp có thể đã được nạp, và JVM có thể làm một số việc liên kết, nhưng không có dòng static nào được in.
3. **Class.forName(..., false, ...)** yêu cầu lấy Class nhưng tham số false ngăn initialization theo yêu cầu gọi API. Không được kết luận tại đây mọi resolution của Target đều đã hoàn tất.
4. Lần đầu **Target.value** là active use: trước khi in “4. value”, JVM thực thi **initValue()**, rồi static block theo thứ tự nguồn. Sau đó phép đọc trả về 42.
5. Lần đọc sau **không chạy lại** static block: cùng một định nghĩa class đã được khởi tạo thành công.

Đây là minh chứng cho **initialization**, không phải công cụ đo chính xác thời điểm verification hoặc resolution. Dựa vào riêng stdout không thể dựng lại toàn bộ vòng đời linking.

## 7. Ví dụ thứ hai: thứ tự superclass và số lần khởi tạo

Tạo **InitOrderDemo.java**:

~~~java
public class InitOrderDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) {
        new Child();
        new Child();
    }
}
~~~

~~~bash
javac InitOrderDemo.java
java InitOrderDemo
~~~

Stdout:

~~~text
Parent initialized
Child initialized
~~~

Superclass được khởi tạo trước Child; hai biểu thức new tạo **hai đối tượng** nhưng không chạy static initializer hai lần. Nếu có constructor in ra màn hình, phần constructor sẽ chạy cho mỗi đối tượng, khác với hai dòng trên.

## 8. Lỗi thường gặp nằm ở giai đoạn nào?

| Hiện tượng hoặc lỗi | Cách hiểu phù hợp |
| --- | --- |
| **ClassNotFoundException** khi gọi Class.forName/loadClass | Loader được yêu cầu tìm lớp theo tên nhưng không tìm/không nạp được; đây thường là checked exception của API tìm lớp. |
| **NoClassDefFoundError** | JVM không thể có định nghĩa class cần dùng tại thời điểm liên kết/thực thi, hoặc class đã rơi vào trạng thái lỗi sau initialization thất bại; không hoàn toàn đồng nghĩa ClassNotFoundException. |
| **VerifyError** | Bytecode vi phạm quy tắc xác minh; thuộc nhóm vấn đề linking/verification. |
| **NoSuchMethodError / NoSuchFieldError / IllegalAccessError** | Mismatch của binary/API/truy cập bộc lộ khi tham chiếu được phân giải hoặc sử dụng; cần kiểm tra dependency/classpath/loader. |
| **ExceptionInInitializerError** | Initialization có exception không thuộc Error được ném ra khỏi logic khởi tạo static; JVM bọc exception gốc vào lỗi này. |
| **Exception hoặc Error trong <clinit>** | Không phải mọi lỗi initialization đều được bọc giống nhau: một Error có thể được ném trực tiếp; các lần dùng class sau đó có thể nhận NoClassDefFoundError. |

Một lỗi phát sinh “lúc khởi động ứng dụng” **không đủ** để xác định nó thuộc loading, linking hay initialization. Hãy xem **loại Throwable, chuỗi cause và stack trace**, xác định lớp nào được JVM yêu cầu, dependency nào đang có trên runtime classpath và class nào **định nghĩa** field/method đang được dùng.

Ví dụ, static initializer phụ thuộc vào cấu hình môi trường chưa sẵn sàng có thể làm toàn bộ class không khởi tạo được. Đưa tác vụ có thể thất bại (kết nối mạng, đọc secrets, I/O) ra khỏi static initializer thường giúp startup rõ ràng hơn, xử lý và thử lại lỗi dễ hơn.

## 9. Cách phân tích một tình huống thực tế

Khi thấy “lớp đã load nhưng chưa in dòng trong static block”, kiểm tra theo thứ tự:

1. **Tác vụ cụ thể là gì?** Chỉ gọi loadClass, lấy Foo.class, tra metadata hay đã dùng new/getstatic/invokestatic?
2. **Field có phải constant variable?** Một giá trị static final có kiểu primitive/String với constant expression có thể được compiler in-line. Kiểm tra bytecode caller bằng **javap -c** nếu cần.
3. **Thành viên thật sự được khai báo ở lớp nào?** Truy cập inherited static field qua subclass không làm subclass initialization chỉ vì cú pháp dùng tên subclass.
4. **Loader nào đã định nghĩa class?** Trong plugin server, nhiều loader có thể tạo Class cùng tên. Kiểm tra **type.getClassLoader()** và module/classpath thực tế.
5. **Có lỗi ở initialization trước đó không?** Tìm exception đầu tiên và cause gốc; NoClassDefFoundError xuất hiện sau chỉ có thể là hậu quả.
6. **Đừng đánh giá resolution qua một mốc duy nhất.** JVM được phép giải quyết các symbolic references theo yêu cầu trong quá trình chạy.

Có thể dùng **javap -c LoadLinkInitDemo** để quan sát những lệnh bytecode khác nhau (ví dụ in-line constant khác với **getstatic**); với HotSpot trên Java hiện đại, **java -Xlog:class+load=info LoadLinkInitDemo** hỗ trợ quan sát sự kiện nạp lớp. Log class loading không trực tiếp chứng minh thời điểm khởi tạo: để thấy điều đó, hãy dùng output có kiểm soát từ static initializer như ví dụ. Tùy phiên bản/VM, kiểm tra các tag logging thực tế bằng **java -Xlog:help**.

## 10. Những hiểu nhầm cần tránh

- **“Nạp lớp là chạy static block.”** Sai. Nạp lớp tạo định nghĩa runtime; static block thuộc initialization.
- **“Linking chỉ là kiểm tra bytecode.”** Thiếu. Linking gồm verification, preparation và resolution.
- **“Static field nhận giá trị gán trong mã ngay khi preparation.”** Sai với biểu thức khởi tạo thông thường: preparation thiết lập giá trị mặc định; mã gán chạy khi initialization. ConstantValue là trường hợp phải phân biệt.
- **“final nghĩa là hằng compile-time.”** Sai. **static final Object TOKEN = new Object()** và **static final int N = calculate()** không phải constant variables.
- **“Gọi class literal chắc chắn chạy <clinit>.”** Sai. **Foo.class** chưa phải active use kích hoạt initialization.
- **“Class.forName luôn chỉ load.”** Sai. Dạng một tham số thường khởi tạo class; overload có cờ initialize mới điều khiển được hành vi này.
- **“Một class được khởi tạo đúng một lần theo tên.”** Thiếu điều kiện: cùng một tên có thể được định nghĩa bởi những loader khác nhau, và mỗi **Class** có trạng thái initialization riêng.
- **“Nhìn thấy lỗi lúc đầu chương trình tức là lỗi loading.”** Sai. Linking và initialization cũng có thể gây lỗi sớm, và lazy resolution có thể gây lỗi muộn.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Nếu class A có static block, lệnh **Class<?> x = A.class;** có bảo đảm static block chạy chưa?

**Đáp án:** Không. Lấy class literal không chủ động initialization.

**Câu 2.** Nếu **static final int MAX = 100;**, vì sao việc in **A.MAX** có thể không chạy static block của A?

**Đáp án:** MAX là constant variable có compile-time constant expression. Caller có thể chứa trực tiếp giá trị 100 mà không truy cập static field lúc chạy.

**Câu 3.** Nếu class đã được load và preparation xong, có thể còn symbolic reference chưa resolution không?

**Đáp án:** Có. Resolution có thể được thực hiện lazy khi tham chiếu cần thiết.

**Câu 4.** Hai plugin loader định nghĩa riêng **example.Task**. Tại sao cả hai đều có thể chạy logic static initializer của Task?

**Đáp án:** Chúng là hai định nghĩa runtime khác nhau vì defining loader khác nhau; initialization được theo dõi cho từng Class.

**Câu 5.** Code gọi static field lần đầu thì gặp **ExceptionInInitializerError**, lần sau gặp **NoClassDefFoundError**. Nên điều tra lỗi nào trước?

**Đáp án:** Điều tra exception/cause của lần initialization thất bại ban đầu. Lần sau class có thể đã ở trạng thái lỗi, khiến NoClassDefFoundError chỉ là triệu chứng.

## 12. Ghi nhớ

**Loading** trả lời: *JVM có định nghĩa của kiểu này chưa, và loader nào định nghĩa nó?*  
**Linking** trả lời: *Định nghĩa đó đã được kiểm tra/chuẩn bị, và những tham chiếu cần thiết đã được phân giải thế nào?*  
**Initialization** trả lời: *Khi nào mã static thực thi, theo thứ tự nào, và kết quả thành công hay thất bại?*

Khi gỡ lỗi, hãy tách ba câu hỏi này. Đừng suy ra thời điểm chạy static initializer chỉ từ việc JVM đã nhận diện được Class, và cũng đừng cho rằng mọi tham chiếu đều phải resolution ngay lúc load.

**Tài liệu gốc:** Java Language Specification §12.2–12.4 (loading, linking, initialization) và Java Virtual Machine Specification §5.3–5.5 (creation/loading, linking, initialization), bản Java SE 21:
- https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
- https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
