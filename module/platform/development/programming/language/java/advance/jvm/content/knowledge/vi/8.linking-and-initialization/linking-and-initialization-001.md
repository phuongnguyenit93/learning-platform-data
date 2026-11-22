# Phân biệt nạp, liên kết và khởi tạo trong vòng đời một lớp

## 1. Mục tiêu và mô hình tổng quan

Một lớp Java có thể đã tồn tại dưới dạng **Class object** trong JVM nhưng **chưa chạy static initializer**. Nó có thể đã được xác minh và chuẩn bị, trong khi một số symbolic references vẫn chưa được giải quyết. Ngược lại, khi ứng dụng thực sự dùng lớp, JVM phải đảm bảo các bước cần thiết đã hoàn tất đúng trình tự và đúng quy tắc an toàn kiểu.

Ba thuật ngữ chính của Java Virtual Machine Specification (JVMS) là:

1. **Loading (nạp):** tìm/thu nhận biểu diễn nhị phân của một class/interface và tạo lớp runtime tương ứng.
2. **Linking (liên kết):** đưa lớp vừa nạp vào trạng thái JVM có thể sử dụng, gồm **verification**, **preparation** và **resolution**; resolution có thể được thực hiện từng phần hoặc sớm tùy các điều kiện đặc tả.
3. **Initialization (khởi tạo):** thực thi công việc khởi tạo của class/interface, thường là những **static field initializers** và **static initializer blocks**, được compiler thể hiện trong phương thức đặc biệt **<clinit>** nếu cần.

Sau bài học, bạn cần:

- Phân biệt được ba giai đoạn, hiểu **verification**, **preparation**, **resolution** và mốc đảm bảo trước initialization.
- Nêu đúng các thao tác gây **active use**: tạo instance, gọi static method, đọc/ghi static field phù hợp, reflection yêu cầu khởi tạo.
- Giải thích vì sao **Class.forName(name, false, loader)**, **T.class**, hoặc một **compile-time constant** không nhất thiết kích hoạt initialization.
- Mô phỏng chính xác thứ tự static initializers, superclass và class con; phân biệt trường hợp interface.
- Phân biệt các lỗi **ClassNotFoundException**, **ClassFormatError**, **VerifyError**, **NoSuchMethodError**, **ExceptionInInitializerError** và **NoClassDefFoundError**.
- Dùng Java 17+, **javap** và class-loading logs để quan sát điều có thể quan sát, đồng thời không suy diễn quá mức về thời điểm verifier/resolver hoạt động.

**Ngữ cảnh:** Bài học nói về vòng đời một **class hoặc interface trong một JVM**; không đồng nghĩa vòng đời của một **đối tượng instance**, của **ClassLoader** hay toàn bộ tiến trình JVM.

## 2. Sơ đồ vòng đời và những mốc bắt buộc

Hãy đọc sơ đồ như một **mô hình phụ thuộc**, không phải một lịch trình đồng bộ tuyệt đối cho mọi lớp trong chương trình:

~~~text
Nguồn class bytes / module / classpath
               |
               v
        [1] LOADING
     - Tìm biểu diễn nhị phân
     - Tạo lớp runtime, Class object
     - Gắn defining class loader
               |
               v
        [2] LINKING
     +-------------------------------+
     | Verification                  |
     |   Kiểm tra tính hợp lệ/an toàn|
     |                               |
     | Preparation                   |
     |   Tạo static fields           |
     |   Gán giá trị mặc định        |
     |                               |
     | Resolution                    |
     |   Symbolic ref -> entity thật |
     |   Có thể xảy ra từng phần     |
     +-------------------------------+
               |
               v
        [3] INITIALIZATION
     - Gắn trạng thái đang khởi tạo
     - Khởi tạo superclass/phần
       superinterface thích hợp
     - Thực thi static initialization
       và các ConstantValue cần áp dụng
               |
               v
      SẴN SÀNG CHO ACTIVE USE
~~~

Các ràng buộc quan trọng theo JVMS:

- Một class/interface phải được **nạp hoàn chỉnh trước khi liên kết**.
- Nó phải được **xác minh và chuẩn bị hoàn chỉnh trước khi khởi tạo**.
- **Resolution** của từng symbolic reference có thể trì hoãn cho đến lúc tham chiếu đó thực sự được sử dụng, hoặc được thực hiện sớm khi JVM đủ điều kiện. Vì vậy không cần mọi dependency của lớp đã được resolve trước khi chạy phần static initializer đầu tiên.
- Các hoạt động có thể kích hoạt nạp/link gián tiếp lớp khác. Không thể liệt kê duy nhất một đường đi tuần tự từ lớp A tới lớp B mà mọi JVM đều phải thực hiện.
- **Khởi tạo** là sự kiện ở cấp lớp, được phối hợp khi nhiều thread cùng yêu cầu; **không chạy lại static initializer sau mỗi lần new**.

Bảng so sánh nhanh:

| Tiêu chí | Loading | Linking | Initialization |
| --- | --- | --- | --- |
| Kết quả chính | Lớp runtime được tạo và gắn loader | Metadata, tính hợp lệ, static storage, symbolic references được xử lý theo yêu cầu | Static initialization của lớp hoàn tất hoặc thất bại |
| Có thực thi code static initializer của lớp mục tiêu? | Không phải nội dung của giai đoạn loading | **Không** phải nhiệm vụ của verification/preparation/resolution | **Có**, nếu class/interface có code khởi tạo cần chạy |
| Liên quan class bytes? | Có | Có, nhất là verification/descriptors/constant pool | Dựa vào code và metadata đã được nạp/liên kết |
| Có thể gây ra nạp lớp khác? | Có, ví dụ superclass/superinterface | Có, khi xác minh/resolve type/reference | Có, do dùng class khác trong static code |
| Có hoàn tất tất cả symbolic references không? | Không | **Không bắt buộc** ngay lúc đầu | Không nhất thiết; resolution vẫn có thể diễn ra về sau |

## 3. Loading: class trở thành kiểu runtime như thế nào?

### 3.1. Định danh lớp không chỉ là tên

Với lớp thường, JVM nhận diện một kiểu qua **binary name** và **defining loader**:

~~~text
(com.example.Order, LoaderA)
(com.example.Order, LoaderB)
~~~

Nếu LoaderA và LoaderB định nghĩa hai lớp có cùng tên, đây vẫn là **hai runtime classes khác nhau**. Truyền một object của lớp thứ nhất sang nơi yêu cầu lớp thứ hai có thể thất bại khi cast, reflection, interface method invocation hoặc linking constraints.

Khái niệm cần phân biệt:

- **Defining loader:** loader thực sự định nghĩa class.
- **Initiating loader:** loader bắt đầu/yêu cầu quá trình nạp và có thể đã ủy quyền thành công cho một loader khác.
- **Bootstrap loader:** loader nền tảng của JVM; Java API thường biểu diễn nó bằng **null** khi đọc **Class.getClassLoader()** trên một class tương ứng.
- **Application/platform/custom loader:** các nguồn lookup khác nhau; cơ chế ủy quyền tùy loader và module configuration.

Nạp một class thông thường không đồng nghĩa tự động mở quyền truy cập reflection trong Java Platform Module System. Module readability/exports/opens còn chịu quy tắc riêng.

### 3.2. Một số API khiến người học tưởng là khởi tạo

~~~java
// Các dòng minh họa đặt trong một phương thức có throws Exception.
Class<?> a = SomeType.class;
Class<?> b = Class.forName("SomeType", false,
        SomeType.class.getClassLoader());
Class<?> c = SomeType.class.getClassLoader()
        .loadClass("SomeType");
~~~

Chúng đều có thể dẫn tới hoặc sử dụng Class object, nhưng **không yêu cầu thực thi static initializer của SomeType** chỉ vì lấy class literal, dùng overload forName với **initialize=false**, hay dùng **loadClass(name)** thông thường.

Ngược lại:

~~~java
// Mã minh họa bên trong một phương thức có throws Exception.
Class<?> c = Class.forName("SomeType"); // overload một tham số
~~~

**Class.forName(String)** dùng initiating class loader thích hợp và **yêu cầu initialization** theo contract của API. **Class.forName(name, true, loader)** cũng vậy. Nói “Class.forName chỉ nạp lớp” mà không phân biệt overload là không chính xác.

**Chú ý ngữ cảnh:** Trong ví dụ các dòng minh họa, **SomeType** phải là class thực sự có thể được tìm thấy bằng tên phù hợp. Tên nested class sử dụng ký tự **$** trong binary name, ví dụ **Example$Inner**, không phải **Example.Inner**.

### 3.3. Loading có thể là kết quả gián tiếp

JVM có thể phải nạp superclass, implemented interfaces hoặc một class được tham chiếu trong descriptor để xác minh/giải quyết ràng buộc. Việc bytecode chứa tên một class khác **không đảm bảo** class đó được nạp vào đúng một offset cố định trên mọi JVM.

Ví dụ, compiler có thể phát ra constant-pool entry trỏ tới **com.example.OptionalFeature** trong một method chỉ được gọi khi có cấu hình tương ứng. JVM có quyền dùng cách resolution eager hoặc lazy trong phạm vi đặc tả. Hãy tránh phụ thuộc vào suy luận “chưa gọi method đó nên class kia chắc chắn chưa được nạp” khi thiết kế hệ thống.

### 3.4. Array classes khác các class file thông thường

JVM tạo array classes theo cơ chế riêng. Không có quy ước tìm tệp **[I.class** cho kiểu **int[]**. Với **String[]**, array class có **Class** object nhưng không có mã **<clinit>** tự viết như class thường.

- **int[].class.getClassLoader()** thông thường trả **null** (primitive array).
- **UserType[].class.getClassLoader()** trả loader của reference component type theo API.
- Tạo **new UserType[10]** tạo mảng có phần tử null, **không tự khởi tạo UserType** chỉ vì array component có kiểu UserType.

## 4. Linking gồm chính xác ba công việc gì?

### 4.1. Verification: kiểm tra tính hợp lệ

**Verification** kiểm tra lớp đã nạp có cấu trúc và bytecode đáp ứng những quy tắc về type safety, operand stack, locals, control flow và constraints của JVM.

Những lỗi verifier có thể phát hiện hoặc liên quan:

- Một lệnh **ireturn** được dùng ở vị trí cần trả một reference không phù hợp.
- Một branch nhảy vào giữa operand bytes của instruction khác.
- Một instruction tiêu thụ giá trị khác kiểu được JVM cho phép từ operand stack.
- Độ sâu stack hoặc StackMapTable không nhất quán với các đường nhánh.
- Class file, inheritance hoặc descriptor vi phạm những ràng buộc JVM cần thiết.

Ví dụ bytecode ở mức khái niệm (không phải chương trình Java hợp lệ):

~~~text
iconst_1
areturn   // Không thể trả reference khi stack đang chứa int
~~~

**javac bình thường** không phát ra kiểu bytecode vi phạm này từ Java source hợp lệ. Người làm bytecode weaving/instrumentation hoặc generator cần dùng verifier, cập nhật stack map frames và tuân thủ class-file version/format.

Từ **ClassFormatError** (dữ liệu/định dạng class file không hợp lệ) đến **VerifyError** (bytecode không thỏa điều kiện xác minh) đều là lỗi liên quan class, nhưng **không nên đồng nhất nguyên nhân và giai đoạn**. Những loại lỗi này là các nhánh của **LinkageError**.

### 4.2. Preparation: chuẩn bị static storage và giá trị mặc định

Trong **preparation**, JVM tạo static fields cho class/interface và khởi tạo chúng về **default values** theo kiểu. Không cần thực thi mã Java để thực hiện công việc chuẩn bị này.

| Kiểu static field | Default value tại preparation |
| --- | --- |
| **int, short, byte, long** | 0 |
| **float, double** | 0.0 (kiểu tương ứng) |
| **boolean** | false |
| **char** | ký tự có giá trị 0 |
| **reference** | null |

Ví dụ:

~~~java
// Mã minh họa một phần class:
static int retries = 5;
static Object holder = new Object();
~~~

Trong preparation, hai field tồn tại với giá trị mặc định **0** và **null**. Việc thực hiện biểu thức **= 5** hay **new Object()** là công việc của **initialization** theo quy tắc class, không phải preparation.

**Ngoại lệ dễ nhầm:** Field **static final** có **ConstantValue** attribute (compile-time constant) được JVM gán giá trị constant trong **quy trình initialization**, trước bước khởi tạo superclass và chạy code <clinit> theo JVMS §5.5. Không nên khẳng định mọi static final constant được gán giá trị cuối cùng ngay ở preparation. Tuy nhiên, truy cập một Java constant variable từ client không bắt buộc kích hoạt initialization của lớp khai báo do compiler có thể dùng hằng đã biết; đây là một quy tắc khác.

### 4.3. Resolution: từ symbolic reference đến tham chiếu thật

Class file thường không chứa con trỏ trực tiếp tới method/field/class runtime khác. Nó giữ **symbolic references** trong constant pool, ví dụ:

~~~text
Owner internal name: java/lang/String
Method name:          length
Method descriptor:    ()I
~~~

**Resolution** tìm thực thể runtime phù hợp cho reference, kiểm tra khả năng truy cập, chữ ký, loại member và những constraints cần thiết. Nhiều bytecode instructions yêu cầu resolution, như **new**, **getstatic**, **putstatic**, **invokevirtual**, **invokestatic**, **getfield**, **checkcast**, **ldc** và **invokedynamic**.

Ví dụ:

~~~java
// Mã minh họa:
int size = someString.length();
~~~

Bytecode có thể chứa **invokevirtual** trỏ tới symbolic method reference **java/lang/String.length:()I**. Khi sử dụng reference này, JVM phải bảo đảm nó resolve thành method phù hợp.

Những lỗi liên quan resolution/linking gồm:

| Lỗi | Một nguyên nhân thường gặp |
| --- | --- |
| **NoSuchMethodError** | Binary class đang chạy không còn method với name+descriptor mà caller từng biên dịch dựa vào |
| **NoSuchFieldError** | Field tham chiếu không còn tồn tại như caller yêu cầu |
| **IllegalAccessError** | Truy cập member/class bị cấm theo access/module rules tại runtime |
| **IncompatibleClassChangeError** | Cấu trúc member/class khác giả định lúc biên dịch; ví dụ static/instance bị đổi không tương thích |
| **NoClassDefFoundError** | JVM cần một class dependency nhưng không thể tìm/nạp/khởi tạo theo điều kiện cụ thể |

**Quan trọng:** resolution không nhất thiết hoàn tất đồng loạt trước khi class bắt đầu initialization. JVM có thể resolve reference khi instruction sử dụng nó. Vì vậy lỗi liên kết đối với một method hiếm dùng có thể chỉ lộ ra khi method được thực hiện, tùy JVM và loại reference.

### 4.4. Eager và lazy resolution có nghĩa gì?

~~~text
Cách diễn giải A (chỉ mang tính minh họa):
Load C -> verify -> prepare -> resolve nhiều ref sớm
       -> init C -> gọi method cần dùng ref

Cách diễn giải B:
Load C -> verify -> prepare -> init C
       -> gọi method -> resolve đúng ref cần dùng
~~~

JVMS cho JVM quyền lựa chọn thời điểm resolution sớm hoặc muộn cho nhiều symbolic references, song phải đảm bảo các tính chất bắt buộc về kết quả liên kết và điểm phát sinh lỗi. Các **dynamically-computed constants/call sites** có quy tắc riêng, không được đem những sơ đồ trên áp dụng mù quáng cho mọi bootstrap resolution.

Kết luận: quan sát thấy **Class.forName(name,false,loader)** trả về không chứng minh mọi class mà target có thể dùng đã resolve.

## 5. Initialization: Java thực thi những gì?

Khi một class/interface cần được khởi tạo, JVM bảo đảm việc xác minh/chuẩn bị và các bước nền tảng cần thiết đã hoàn thành. Công việc khởi tạo thường bao gồm:

1. Chuyển trạng thái class sang **being initialized** và phối hợp với các thread khác.
2. Gán những **static final** có **ConstantValue** theo quy tắc JVM.
3. Với **class**, đảm bảo superclass và các superinterfaces thuộc diện cần khởi tạo được xử lý theo thứ tự quy định.
4. Thực thi code khởi tạo của class/interface theo thứ tự do compiler và đặc tả quy định.
5. Đánh dấu **fully initialized** nếu thành công, hoặc **erroneous** nếu quá trình thất bại.

### 5.1. <clinit> là gì?

Trong class file, mã khởi tạo static được compiler gộp vào phương thức đặc biệt **<clinit>** khi cần:

~~~java
class Configuration {
    static int port = loadPort();

    static {
        System.out.println("Configuration initialized");
    }

    static int loadPort() {
        return 8080;
    }
}
~~~

Về ngữ nghĩa, đoạn này chạy lần lượt lời gọi **loadPort()** rồi static block khi Configuration được khởi tạo; code tương ứng có thể xuất hiện trong **<clinit>**. <clinit> không phải constructor **<init>** và không được viết trực tiếp như một method Java bình thường.

Những lớp chỉ có static compile-time constants có thể **không cần** một <clinit> chứa code, nhưng vẫn có trạng thái lifecycle của class.

### 5.2. Static fields và static blocks chạy theo thứ tự văn bản

~~~java
class Steps {
    static int a = print("a", 1);
    static { System.out.println("block"); }
    static int b = print("b", 2);

    static int print(String label, int result) {
        System.out.println(label);
        return result;
    }
}
~~~

Khi Steps được khởi tạo lần đầu, trật tự lời in là:

~~~text
a
block
b
~~~

Không phải JVM chạy **mọi static field initializer trước**, rồi mới chạy **mọi static block**. Compiler phải bảo toàn thứ tự văn bản của các static initializers theo JLS.

### 5.3. Initialization không phải instance construction

~~~java
class Widget {
    static {
        System.out.println("class init");
    }

    {
        System.out.println("instance init");
    }

    Widget() {
        System.out.println("constructor");
    }
}
~~~

Khi **new Widget()** lần đầu:

~~~text
class init
instance init
constructor
~~~

Với **new Widget()** lần hai trong cùng runtime class:

~~~text
instance init
constructor
~~~

**Static initialization** xảy ra ở cấp class, còn **instance field initializers**, **instance initializer blocks** và constructor chạy theo quy tắc tạo từng object. Cả hai đều gọi là “khởi tạo” trong tiếng Việt, nhưng tuyệt đối không được trộn lại khi phân tích vòng đời class JVM.

## 6. Khi nào class/interface được khởi tạo?

Các trường hợp phổ biến theo JLS §12.4.1/JVMS §5.5:

- Tạo instance bằng **new C()** lần đầu làm C cần được khởi tạo (và lớp cha theo quy tắc).
- Gọi **static method thực sự được khai báo bởi C**.
- Ghi một **static field khai báo bởi C**.
- Đọc một **static field khai báo bởi C mà không phải constant variable**.
- Yêu cầu khởi tạo qua một số reflection APIs, chẳng hạn **Class.forName(name,true,loader)**.
- C được JVM chọn làm initial class khi bắt đầu tiến trình.
- Những tình huống đặc tả khác như method handles và việc khởi tạo subclass/superinterfaces thích hợp.

**Không coi mọi cú pháp nhắc tới tên C là một active use.**

### 6.1. Những thao tác thường không tự kích hoạt initialization

| Thao tác | Lưu ý |
| --- | --- |
| **C.class** | Class literal không tự chạy <clinit> của C |
| **obj instanceof C** | Không yêu cầu initialization của C chỉ vì kiểm tra kiểu |
| Cast **(C) obj** | Không tự khởi tạo C chỉ vì cast |
| Tạo **new C[10]** | Tạo mảng, không tạo C instances và không tự init C |
| Khai báo **C variable;** | Khai báo biến kiểu C không phải active use |
| **ClassLoader.loadClass(name)** | Thông thường không yêu cầu initialize |
| **Class.forName(name,false,loader)** | Yêu cầu load/link theo API, không initialize |
| Đọc compile-time constant **C.ANSWER** | Không khởi tạo C nếu field là constant variable theo quy tắc |
| Gọi **getDeclaredMethods()** trên Class | Không được suy rằng mọi reflection inspection đều init class; cần đọc contract của từng API |

**Lưu ý:** các thao tác không làm **initialize C** vẫn có thể khiến C hoặc lớp khác được **load**, **link**, **resolve** tùy trường hợp. Đây là lý do không in static log không thể được dùng làm bằng chứng rằng lớp chưa được nạp.

### 6.2. Static field khai báo ở lớp cha

Xét:

~~~java
class Base {
    static int number = 123;
}

class Child extends Base {
    static {
        System.out.println("Child init");
    }
}
~~~

Nếu client đọc:

~~~java
System.out.println(Child.number);
~~~

Field **number** thực sự được khai báo trong **Base**. Quy tắc Java chỉ yêu cầu khởi tạo lớp **Base** cho thao tác đó; không có yêu cầu khởi tạo **Child** vì tên Child xuất hiện bên trái dấu chấm.

Ngược lại, nếu đọc field không phải constant **Child.ownNumber** khai báo thực sự trong Child, class Child cần init và superclass Base cũng được init trước nếu chưa.

### 6.3. Compile-time constants và việc inlining

~~~java
class Constants {
    static final int LIMIT = 256;         // constant variable
    static final String MODE = "basic";    // constant variable
    static final int DYNAMIC = compute(); // không là constant variable

    static int compute() {
        return 7;
    }

    static {
        System.out.println("init Constants");
    }
}
~~~

Khi client viết **Constants.LIMIT** hoặc **Constants.MODE**, compiler có thể thay thành chính giá trị constant trong bytecode của client, nên việc đọc chúng **không làm Constants khởi tạo**.

Đọc **Constants.DYNAMIC** là một active use và phải kích hoạt initialization nếu chưa chạy.

Cẩn thận với **static final**: không phải field nào có cả hai từ khóa này cũng là constant variable. **static final Integer BOXED = 1**, **static final String TEXT = new String("x")**, và **static final int DYNAMIC = compute()** đều không phải Java constant variables theo quy tắc compile-time constant expression phù hợp.

**Hệ quả binary compatibility:** Khi thay đổi giá trị của một public static final compile-time constant trong thư viện, client cũ có thể tiếp tục dùng giá trị đã inlined cho đến khi được biên dịch lại. Không đánh đồng sự cố này với class loader cache hoặc lỗi initialization.

## 7. Ví dụ Java 17+ chạy được: nạp nhưng chưa khởi tạo

Tạo file **LifecycleObservation.java**:

~~~java
public class LifecycleObservation {
    static class Probe {
        static final int LIMIT = 42;
        static int current = initializeCurrent();

        static int initializeCurrent() {
            System.out.println("Probe:field");
            return 7;
        }

        static {
            System.out.println("Probe:block");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("main:start");

        ClassLoader loader =
                LifecycleObservation.class.getClassLoader();
        Class<?> type = Class.forName(
                "LifecycleObservation$Probe", false, loader);

        System.out.println("sameClass=" + (type == Probe.class));
        System.out.println("constant=" + Probe.LIMIT);
        System.out.println("main:before-active-use");

        System.out.println("value=" + Probe.current);
        System.out.println("valueAgain=" + Probe.current);

        Class.forName("LifecycleObservation$Probe", true, loader);
        System.out.println("main:end");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 LifecycleObservation.java
java LifecycleObservation
~~~

**Stdout chính xác trong một lần khởi chạy JVM mới:**

~~~text
main:start
sameClass=true
constant=42
main:before-active-use
Probe:field
Probe:block
value=7
valueAgain=7
main:end
~~~

Giải thích theo thứ tự:

1. Main class **LifecycleObservation** được khởi tạo trước khi gọi main.
2. **Class.forName(...,false,loader)** nạp/liên kết **Probe** theo contract nhưng chưa yêu cầu initialize.
3. **Probe.class** không phải active use, vì vậy phép so sánh Class objects không in thông điệp của Probe.
4. **Probe.LIMIT** là constant variable, client có thể dùng hằng 42 trực tiếp.
5. Dòng **Probe.current** lần đầu mới là active use: JVM chạy static initialization của Probe theo thứ tự **initializeCurrent()** rồi static block.
6. Đọc lại current trả 7 mà **không chạy lại** init.
7. Gọi **Class.forName(...,true,loader)** sau khi class đã khởi tạo thành công không khiến init chạy thêm lần nữa.

**Điều không thể suy từ stdout:** Không in gì khi forName(false) không chứng minh verifier chưa chạy hoặc pool chưa có symbolic references được resolve. Các bước linking không được thiết kế để in log từ Java source.

## 8. Preparation và giá trị mặc định quan sát được trong <clinit>

Tạo file **PreparationObservation.java**:

~~~java
public class PreparationObservation {
    static class State {
        static int first = readSecond();
        static int second = 9;

        static int readSecond() {
            return second;
        }

        static {
            System.out.println("State:ready");
        }
    }

    public static void main(String[] args) {
        System.out.println("first=" + State.first);
        System.out.println("second=" + State.second);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 PreparationObservation.java
java PreparationObservation
~~~

**Stdout:**

~~~text
State:ready
first=0
second=9
~~~

Phân tích:

- Khi liên kết State, static fields được tạo và nhận default value **0**.
- Khi khởi tạo State, initializer của **first** gọi method **readSecond()** trước khi initializer của **second** chạy.
- **readSecond()** có thể đọc **second** đang ở default value 0 (tham chiếu gián tiếp qua method, không vướng quy tắc cấm forward reference trực tiếp của Java source).
- Sau đó **second = 9**, rồi static block in **State:ready**.
- Main đợi State khởi tạo hoàn tất để in **first=0** và **second=9**.

Đây là hiện tượng do **thứ tự static initializers** trong class. Không kết luận preparation “chạy code của readSecond”; readSecond thực thi trong initialization.

Nếu thử viết trực tiếp **static int first = second; static int second = 9;**, compiler Java có thể báo **illegal forward reference**. Ví dụ dùng method để cho thấy state default hợp lệ khi khởi tạo theo thứ tự.

### 8.1. Giới hạn của quan sát

JVM không cung cấp một điểm Java thông thường để bạn xen lệnh println vào giữa verification/preparation của chính lớp rồi quan sát tùy ý. Chương trình trên **gián tiếp** cho thấy một static field chưa được gán biểu thức initializer trong <clinit> có default value khi code khởi tạo bắt đầu chạy.

Đừng đoán kích thước bộ nhớ của static fields hoặc thứ tự các internal data structures của VM từ output này.

## 9. Khởi tạo superclass trước subclass

Tạo file **InheritanceInitialization.java**:

~~~java
public class InheritanceInitialization {
    static class Parent {
        static int base = trace("Parent:field", 10);

        static {
            System.out.println("Parent:block");
        }
    }

    static class Child extends Parent {
        static int own = trace("Child:field", 20);

        static {
            System.out.println("Child:block");
        }
    }

    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("main:start");
        System.out.println("childOwn=" + Child.own);
        System.out.println("baseViaChild=" + Child.base);
        System.out.println("main:end");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 InheritanceInitialization.java
java InheritanceInitialization
~~~

**Stdout:**

~~~text
main:start
Parent:field
Parent:block
Child:field
Child:block
childOwn=20
baseViaChild=10
main:end
~~~

Nguyên nhân:

1. Đọc **Child.own** kích hoạt initialization của Child.
2. Trước đó JVM phải đảm bảo superclass **Parent** được khởi tạo.
3. Parent chạy các initializer theo thứ tự field rồi block.
4. Child mới chạy field initializer và static block.
5. Lệnh **Child.base** tiếp theo thực chất truy cập field khai báo tại Parent và **không init lại** lớp nào.

Nếu chỉ đọc **Child.base** trước mà chưa từng truy cập **Child.own**, JVM có thể init Parent mà **chưa cần init Child**.

### 9.1. Interface có quy tắc khác class

- Khởi tạo một **class** kéo theo khởi tạo superclass và những superinterfaces thuộc diện khai báo default methods theo quy tắc JVMS/JLS.
- Khởi tạo một **interface** **không tự động** khởi tạo toàn bộ superinterfaces của nó.
- Truy cập static field của interface được khai báo ở interface nào thì quy tắc active use xét interface khai báo đó; một constant variable không nhất thiết kích hoạt initialization.
- Có những default methods sinh bởi compiler; phân tích interface initialization phức tạp cần đối chiếu class file, không chỉ tên method nhìn thấy trong source.

Ví dụ interface có field:

~~~java
interface Flags {
    int STATIC_CONSTANT = 5;
    int DYNAMIC = initialize();

    static int initialize() {
        System.out.println("Flags:init");
        return 8;
    }
}
~~~

Đọc **Flags.STATIC_CONSTANT** không yêu cầu init; đọc **Flags.DYNAMIC** yêu cầu init Flags và chạy code của **initialize()**. Đây là mã minh họa độc lập về nguyên tắc; chỉ khi đặt vào chương trình có main và thực hiện truy cập mới có output.

## 10. Vòng đời lớp khi nhiều thread cùng yêu cầu initialization

JVM phải điều phối class initialization khi nhiều threads cùng active use:

- Nếu một thread đang init C, thread khác cần init C sẽ chờ theo cơ chế initialization lock mà VM quy định.
- Nếu chính thread đang init C đệ quy yêu cầu init lại C, VM có quy tắc xử lý yêu cầu đệ quy; nó không đơn giản chạy một <clinit> thứ hai.
- Khi init thành công, class đạt trạng thái fully initialized; những lần yêu cầu sau không chạy lại static initialization.
- Nếu init thất bại, class chuyển sang **erroneous state**; những yêu cầu init tiếp theo trong cùng runtime class không tự chạy lại <clinit>.

**Không đồng nhất initialization lock với việc mọi static method bị synchronized.** Sau khi lớp đã khởi tạo, static methods vẫn có các quy tắc đồng thời riêng; viết/đọc mutable static fields giữa threads phải theo Java Memory Model. Class initialization cung cấp bảo đảm xuất bản trạng thái khởi tạo theo ngữ nghĩa JVM, không biến toàn bộ static state về sau thành thread-safe.

### 10.1. Một lớp có được init hai lần trong cùng JVM không?

**Cùng runtime class**, tức cùng danh tính **(binary name, defining loader)**, thực hiện initialization một lần nếu thành công.

Nhưng hai defining class loaders khác nhau có thể định nghĩa hai runtime classes cùng binary name; mỗi runtime class có vòng đời initialization riêng. Đây là lý do web container/plugin được redeploy có thể thấy một bản sao static initializer mới khi dùng loader mới, trong khi lớp cũ vẫn tồn tại nếu loader cũ còn được tham chiếu.

## 11. Khởi tạo thất bại: trạng thái erroneous và lỗi sau đó

Một lỗi xảy ra trong static field initializer hoặc static block có thể làm initialization của lớp thất bại.

- Nếu code <clinit> ném một exception không phải Error, JVM thường báo **ExceptionInInitializerError** bọc lỗi gốc theo quy tắc JVMS.
- Nếu nguyên nhân đã là một **Error**, JVM có thể ném chính Error đó.
- Lớp bị đánh dấu **erroneous** khi initialization thất bại, và những active uses sau trong cùng runtime class có thể nhận **NoClassDefFoundError** thay vì chạy lại initializer.
- Các lớp phụ thuộc (ví dụ subclass) có thể thất bại khi việc init superclass bị lỗi.

### 11.1. Ví dụ runnable: lần đầu và lần sau khác nhau

Tạo file **FailedInitialization.java**:

~~~java
public class FailedInitialization {
    static class Broken {
        static int number = fail();

        static int fail() {
            System.out.println("Broken:init");
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(Broken.number);
        } catch (Throwable problem) {
            System.out.println("first="
                    + problem.getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.number);
        } catch (Throwable problem) {
            System.out.println("second="
                    + problem.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 FailedInitialization.java
java FailedInitialization
~~~

**Stdout:**

~~~text
Broken:init
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

- Lần truy cập đầu kích hoạt **Broken.<clinit>**. **fail()** in log rồi ném IllegalStateException; JVM bọc lỗi theo quy tắc nên caller nhìn thấy ExceptionInInitializerError.
- Lần truy cập tiếp theo không chạy lại **fail()**, do runtime class Broken đã ở **erroneous state**; JVM báo NoClassDefFoundError.
- Mẫu code bắt **Throwable** chỉ nhằm **quan sát lỗi trong bài thí nghiệm**. Production code không nên dùng catch(Throwable) chung để tiếp tục chạy sau các Error nghiêm trọng.

**Đừng vội giải thích mọi NoClassDefFoundError là “thiếu .class”**. Nó còn có thể xuất hiện do lớp đã thất bại khởi tạo trước đó. Luôn đọc **cause** và toàn bộ chuỗi lỗi lần đầu.

### 11.2. Có thể “thử lại” init bằng cách gọi Class.forName lần nữa không?

Với **cùng runtime class** đã erroneous, gọi lại **Class.forName(name,true,loader)** không hồi phục trạng thái; initialization vẫn thất bại. Muốn xử lý phải sửa nguyên nhân và thường cần tiến trình/cấu hình mới hoặc một runtime class **thực sự khác** do loader mới định nghĩa, nếu kiến trúc cho phép. Không dùng loader mới để che giấu lỗi và gây class-identity conflict.

## 12. Các nhóm lỗi theo vòng đời

| Lỗi | Nhóm vấn đề điển hình | Khi nào thường gặp? |
| --- | --- | --- |
| **ClassNotFoundException** | Yêu cầu lookup theo tên không tìm được class | **Class.forName**, **ClassLoader.loadClass** |
| **ClassFormatError** | Class file sai cấu trúc/tags/descriptors hoặc constraints định dạng | Nạp và kiểm tra dữ liệu class |
| **UnsupportedClassVersionError** | Runtime không hỗ trợ major/minor version class file | Nạp class version mới bằng JVM cũ |
| **VerifyError** | Bytecode/stack maps/control flow sai điều kiện xác minh | Linking — verification |
| **NoSuchFieldError** | Field từng được biên dịch dựa vào nhưng runtime không còn tương thích | Resolution/field access |
| **NoSuchMethodError** | Method đã đổi/xóa không tương thích tại runtime | Resolution/invocation |
| **IllegalAccessError** | Kiểm tra access/module permission không hợp lệ | Linking/resolution |
| **IncompatibleClassChangeError** | Kỳ vọng về class/member dạng instance/static/interface không khớp | Linking hoặc sử dụng reference |
| **ExceptionInInitializerError** | Static initializer ném exception không phải Error | Initialization lần đầu |
| **NoClassDefFoundError** | JVM không thể định nghĩa/nạp class theo nhu cầu hoặc class đã erroneous | Khi cần class, sau load/init failure |
| **ClassCircularityError** | Ràng buộc vòng kế thừa class không hợp lệ | Trong loading/linking |
| **OutOfMemoryError** | Tài nguyên JVM cạn, có thể xảy ra ở nhiều nơi | Không phải bằng chứng riêng của một phase |

**Một triệu chứng có thể có nhiều nguyên nhân.** Ví dụ NoClassDefFoundError không chỉ do classpath, và IllegalAccessError không giống lỗi biên dịch Java về private access vì class file runtime có thể khác các class lúc build.

**Kiểm tra root cause** luôn đáng giá hơn suy luận từ tên exception đơn lẻ.

## 13. Cách quan sát lifecycle bằng công cụ

### 13.1. javap: nhận diện <clinit>, không đo trực tiếp phase

Sau khi biên dịch:

~~~bash
javap -c -p LifecycleObservation
javap -c -p 'LifecycleObservation$Probe'
javap -v -p 'LifecycleObservation$Probe'
~~~

Lệnh có tên chứa **$** nên cần quote thích hợp với shell; các dòng trên phù hợp trong Bash/PowerShell có hỗ trợ dấu nháy đơn, còn với Command Prompt cần điều chỉnh cú pháp. **javap -p** hiển thị thành viên private; **-c** hiện bytecode; **-v** hiện thêm constant pool/attributes.

Bạn có thể tìm:

- Trong main: **ldc** chứa class literal, **getstatic** đối với Probe.current, và **invokestatic** cho Class.forName.
- Trong Probe: method đặc biệt **static {}** hoặc **<clinit>** theo cách javap trình bày, bao gồm lời gọi **initializeCurrent** và println.
- **ConstantValue** attribute hoặc cách compiler sử dụng hằng đối với **Probe.LIMIT**.
- Các class/method/field references trong constant pool.

**Giới hạn:** javap chỉ cho thấy **class file đã biên dịch**; nó không cho biết chính xác runtime ở thời điểm nào đã chạy verifier hoặc resolve từng reference trên mọi JVM.

### 13.2. Log nạp và khởi tạo lớp trên JVM hỗ trợ

Với HotSpot hỗ trợ Unified JVM Logging (Java 17):

~~~bash
java -Xlog:class+load=info LifecycleObservation
~~~

Dạng log này có thể ghi ra rất nhiều tên lớp, nguồn dữ liệu và thông tin khác; định dạng, cấp độ và thứ tự log tùy JVM. Log load **không phải** log đã chạy <clinit>.

Có thể tra các tag hỗ trợ bằng:

~~~bash
java -Xlog:help
~~~

Không khẳng định mọi VM/version có chung một tag riêng “init” ở cùng mức log hoặc cùng bố cục output. Dùng stdout có chủ đích từ static blocks kết hợp log runtime để phân biệt:

- **Lớp có thể được nạp trước** dòng println của initializer.
- **Một static initializer chạy một lần** khi active use.
- **Không có dòng initializer** chưa đủ kết luận lớp chưa load/link.

### 13.3. Quan sát class loader và module

~~~java
// Mã minh họa đặt trong một phương thức:
Class<?> type = LifecycleObservation.class;
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule().getName());
~~~

Tùy môi trường, loader có thể được in bằng tên implementation, module name có thể null với unnamed module. Do đó đây là các giá trị chẩn đoán động, không phải stdout cố định để học thuộc.

Muốn tìm Class object **mà không init**, dùng overload **Class.forName(name,false,loader)**; nhưng ngay cả API này vẫn có những tác động loading/linking và có thể ném linkage errors.

## 14. Dòng thời gian thực tế của một lệnh new

Khi chương trình gặp:

~~~java
// Mã minh họa một expression:
Widget w = new Widget();
~~~

Với **Widget** chưa từng được khởi tạo, tóm tắt hành vi:

1. JVM phải bảo đảm định nghĩa class Widget cần thiết đã được nạp/tạo.
2. JVM đảm bảo verification và preparation hoàn tất; resolution phù hợp được xử lý theo nhu cầu.
3. Vì **new Widget()** là active use, JVM cần initialization của Widget, bao gồm superclass và những trường hợp superinterface liên quan.
4. Sau khi initialization thành công, JVM thực hiện việc tạo instance: cấp phát, các giá trị mặc định cho instance fields, xử lý constructor chain, instance field initializers và constructor body theo quy tắc.
5. Trả reference tới đối tượng nếu toàn bộ thao tác thành công.

**Không đồng nhất** việc static field nhận giá trị mặc định ở **preparation** với việc instance fields nhận default values khi **tạo object**. Chúng diễn ra ở cấp khác nhau.

Trong bytecode, **new** và **invokespecial <init>** là các instruction/hoạt động khác nhau. **<clinit>** không phải constructor, và câu lệnh source **new Widget()** có thể làm cả class initialization lẫn instance initialization khi được dùng lần đầu.

## 15. Resolution, class initialization và startup dependency: một tình huống

Giả sử:

~~~java
// Mã minh họa trong class Service:
static {
    System.out.println("Service init");
}

static String loadData(boolean enabled) {
    if (enabled) {
        return OptionalLibrary.read();
    }
    return "disabled";
}
~~~

Nếu **OptionalLibrary** không tồn tại tại runtime, không thể kết luận chỉ từ source rằng **loadData(false)** luôn chạy được hay JVM nhất thiết ném lỗi ngay khi Service được load. Thời điểm resolution của reference còn chịu chiến lược JVM, điều kiện linkage và Java/module semantics.

Cách thiết kế tin cậy hơn:

- Nếu thư viện là dependency bắt buộc, đóng gói và kiểm tra nó ở deployment/build, đừng dựa vào lazy resolution để “né” dependency.
- Nếu tính năng thật sự tùy chọn, dùng class loading/reflection hoặc ranh giới module/plugin được thiết kế rõ, xử lý lỗi vắng dependency có chủ đích.
- Không đặt logic có side effects khó phục hồi vào static initializer chỉ để tải thư viện động.
- Viết test integration chạy với classpath/module path thật, không chỉ unit tests có đầy đủ dependency.

## 16. Lớp interface, enum, record và nested class có cùng những giai đoạn không?

**Có:** class và interface đều có loading, linking và initialization theo đặc tả, nhưng quy tắc initialization có điểm khác nhau.

- **Interface:** static fields của interface thường là **public static final**; một field được gán kết quả của lời gọi method không phải compile-time constant vẫn có thể yêu cầu interface initialization. Interface initialization không tự init tất cả superinterfaces của nó.
- **Enum:** là class có những bước khởi tạo liên quan enum constants; thao tác sử dụng enum có thể kích hoạt initialization của enum class, tạo các instance enum theo quy tắc.
- **Record:** là class chuyên biệt, vẫn có class initialization cho static members; record canonical constructor điều khiển instance initialization, không thay thế <clinit>.
- **Nested/static member class:** có binary name riêng và có vòng đời class riêng. Việc class ngoài được init **không tự động** init mọi static nested classes chỉ vì chúng được khai báo bên trong.
- **Anonymous/local class:** cũng có runtime class identity; chi tiết tên nhị phân do compiler tạo, và tạo instance của nó là active use thích hợp.

Ví dụ Java thường gọi “outer class” và “nested class” trong một đơn vị source, nhưng JVM nhìn chúng như các định nghĩa class riêng biệt trong class files và loader context.

## 17. Những hiểu lầm phải tránh

1. **“Đã load là đã chạy static block.”** Sai; load có thể xảy ra sớm hơn initialization.
2. **“Class.forName luôn chỉ load.”** Sai; overload một tham số và initialize=true có thể kích hoạt initialization.
3. **“C.class bảo đảm static initializer chạy.”** Sai; class literal không phải active use theo quy tắc thông thường.
4. **“Linking là một thao tác duy nhất, phải resolve xong mọi reference.”** Sai; gồm verification, preparation, resolution và resolution có thể lazy.
5. **“Preparation chạy static int x = compute().”** Sai; đó là initialization.
6. **“Preparation gán mọi static final field giá trị cuối cùng ngay lập tức.”** Không chuẩn xác; ConstantValue được áp dụng theo quy trình initialization riêng.
7. **“Nếu static final thì chắc chắn không init class khi đọc.”** Sai với static final không phải constant variable.
8. **“Tạo new C[10] cũng giống new C().”** Sai; array allocation không tạo C instance và không yêu cầu init C chỉ vì component type.
9. **“Đọc Child.parentField sẽ init Child.”** Không nếu field thực sự khai báo tại Parent và không có active use khác của Child.
10. **“Mọi interface parent phải init trước subinterface.”** Sai; interface có quy tắc khác class.
11. **“Static initializer chạy một lần cho mỗi object.”** Sai; chạy ở cấp runtime class.
12. **“NoClassDefFoundError chỉ có nghĩa .class thiếu.”** Sai; một class khởi tạo thất bại trước đó cũng có thể cho lỗi này.
13. **“Hai lớp cùng tên luôn dùng chung static state.”** Sai nếu được định nghĩa bởi loaders khác nhau.
14. **“javap cho thấy chính xác thời điểm JVM link mọi reference.”** Sai; nó cho bytecode/metadata, không phải timing runtime toàn cục.
15. **“JIT được phép bỏ quy tắc class initialization để nhanh hơn.”** Sai; mọi tối ưu phải bảo toàn ngữ nghĩa và side effects có thể quan sát được theo đặc tả.

## 18. Bài tập kiểm tra có đáp án

**Bài 1 — Nhận diện phase**

Một loader đã tìm được bytes và tạo Class object; JVM kiểm tra stack typing; sau đó một static block mới in log. Gán ba hành động với phase.

**Đáp án:** Tạo Class object thuộc **loading**; stack typing thuộc **linking/verification**; in log static block thuộc **initialization**.

**Bài 2 — Default value**

~~~java
class C {
    static int a = read();
    static int b = 15;

    static int read() { return b; }
}
~~~

Lần đầu truy cập **C.a**, giá trị là bao nhiêu?

**Đáp án:** **0**. Khi initializer của a chạy, b vẫn có giá trị mặc định vì initializer của b nằm phía sau trong thứ tự văn bản.

**Bài 3 — Class literal**

~~~java
class C {
    static { System.out.println("C initialized"); }
}
Class<?> type = C.class;
~~~

Lấy class literal có bắt buộc in chữ **C initialized** không?

**Đáp án:** Không. Class literal có thể lấy/làm lớp được nạp/liên kết theo nhu cầu, nhưng không phải active use khởi tạo class.

**Bài 4 — Static constant**

~~~java
class C {
    static final int X = 9;
    static final Integer Y = 9;
    static { System.out.println("init"); }
}
~~~

Đọc **C.X** và **C.Y** có cùng hành vi initialization không?

**Đáp án:** Không. **X** là constant variable nên đọc nó không yêu cầu init C; **Y** là boxed Integer, không phải compile-time constant variable nên **getstatic** để đọc Y kích hoạt initialization.

**Bài 5 — Truy cập static field kế thừa**

Có **Base.count** và **Child extends Base**. Chỉ đọc **Child.count**, nếu count thực sự khai báo tại Base, cần init class nào?

**Đáp án:** Class **Base** khi field không phải constant variable; không bắt buộc init Child vì nó không khai báo field.

**Bài 6 — Resolution sớm hay muộn**

Một method chưa gọi chứa symbolic ref tới class OptionalFeature. Có thể khẳng định JVM tuyệt đối chưa resolve ref đó không?

**Đáp án:** Không. JVMS cho phép resolution sớm hoặc muộn trong các ràng buộc quy định. Không dựa vào điểm này để thiếu dependency bắt buộc.

**Bài 7 — Initialization thất bại**

Một static initializer ném IllegalStateException lần đầu. Lần đầu và lần sau có thể là lỗi gì?

**Đáp án:** Thường **ExceptionInInitializerError** lần đầu; class chuyển erroneous, những active uses tiếp sau thường nhận **NoClassDefFoundError**; không tự chạy lại initializer.

**Bài 8 — Nested class**

Outer đã được khởi tạo. Có chắc static nested class **Outer.Helper** cũng đã init?

**Đáp án:** Không. Nested member class có runtime class riêng; khai báo lồng nhau không đồng nghĩa cùng vòng đời initialization.

**Bài 9 — Constructor vs <clinit>**

Một chương trình tạo hai đối tượng C liên tiếp. Một static block và constructor chạy mấy lần?

**Đáp án:** Nếu C mới được khởi tạo và cả hai lần tạo thành công, static block chạy **một lần**, constructor chạy **hai lần**.

**Bài 10 — Loader identity**

Hai class loaders khác nhau định nghĩa hai lớp cùng tên **example.Counter**. Static initializer/state có dùng chung không?

**Đáp án:** Không. Đây là hai runtime classes; mỗi loại có initialization và static storage riêng.

**Bài 11 — Kiểm tra lỗi**

Bản thư viện runtime đã xóa method nhưng caller được build với bản cũ. Đây thường là lỗi phase nào?

**Đáp án:** Nhóm **linking/resolution**, có thể hiện thành **NoSuchMethodError** khi reference cần giải quyết/sử dụng.

**Bài 12 — Lịch trình bắt buộc**

Tại thời điểm bắt đầu chạy <clinit> của một class, JVM bắt buộc đã verify/prepare class đó chưa? Mọi reference đã resolve chưa?

**Đáp án:** **Đã verify và prepare**, nhưng **không bắt buộc resolve mọi symbolic reference**.

## 19. Checklist khi chẩn đoán sự cố và thiết kế ứng dụng

1. **Xác định class thực sự:** binary name + defining loader + module, tránh nhầm hai lớp cùng tên trong plugin/application server.
2. **Tách câu hỏi:** “đã load?”, “đã verify/prepare?”, “symbolic reference nào đã resolve?”, “đã initialize?”.
3. **Dùng đúng API:** forName(name,false,loader) cho lookup không yêu cầu initialization; forName(name,true,loader) khi thật sự muốn initialization.
4. **Kiểm tra active use:** new, static read/write, static invoke, reflection và ngoại lệ compile-time constant.
5. **Theo dõi thứ tự <clinit>:** static fields/static blocks theo thứ tự văn bản, superclass và default-method superinterfaces khi cần.
6. **Chẩn đoán nguyên nhân:** ClassFormatError, VerifyError, NoSuchMethodError, ExceptionInInitializerError, NoClassDefFoundError là các tín hiệu khác nhau.
7. **Tránh static init nặng:** hạn chế I/O, kết nối mạng, thread creation, loading động hoặc phụ thuộc dễ thất bại trong static initializers; nếu cần, thiết kế initialization có thông báo lỗi rõ và test đầy đủ.
8. **Không dựa vào lazy resolution:** dependency bắt buộc phải đóng gói đầy đủ; dependency tùy chọn cần contract và biện pháp xử lý riêng.
9. **Dùng javap và runtime logging có mục tiêu:** đọc Code/constant pool và kết hợp trace thực tế, không suy từ source/stack trace một mình.
10. **Cẩn trọng với concurrency:** static mutable state sau initialization vẫn cần synchronization/happens-before phù hợp.
11. **Thử đúng môi trường:** JDK version, --release, module path, classpath, container/IDE loader và các phiên bản thư viện.
12. **Đoạn code có side effect:** nếu thay đổi thời điểm initialization bằng reflection, instrumentation hoặc lazy holder, phải bảo toàn thứ tự và contract người dùng có thể quan sát.

### Tài liệu chính thức

- **JVMS Java SE 17, §5.3 — Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS Java SE 17, §5.4 — Linking (Verification, Preparation, Resolution):** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS Java SE 17, §5.5 — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JLS Java SE 17, §12.2–12.3 — Loading, Linking:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **JLS Java SE 17, §12.4 — Initialization and active use:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- **Java 17 API, Class.forName:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java 17 API, ClassLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html

**Ghi nhớ cốt lõi:** **Loading** tạo lớp runtime; **Linking** xác minh, chuẩn bị static storage và giải quyết symbolic references theo nhu cầu; **Initialization** mới thực hiện mã khởi tạo của lớp theo các active uses và thứ tự quy định. **Đã có Class object không có nghĩa <clinit> đã chạy**; **đã bắt đầu <clinit> không có nghĩa mọi reference đã được resolve**. Khi chẩn đoán lỗi, hãy xác định đúng phase, đúng runtime class và đúng tác vụ gây ra lần sử dụng lớp đó.
