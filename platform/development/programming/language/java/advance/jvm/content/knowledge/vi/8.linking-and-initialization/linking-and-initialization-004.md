# Preparation: tạo trường static và thiết lập giá trị mặc định trong JVM

## Mục tiêu

Trong vòng đời một lớp hoặc interface, **preparation** là giai đoạn thuộc **linking**. Ở bước này, JVM tạo trạng thái cho các **static fields** của lớp/interface và đặt chúng về **giá trị mặc định theo kiểu**. Preparation không thực thi các lệnh Java dùng để khởi tạo trường thành giá trị mà lập trình viên viết trong mã nguồn.

Bài học giúp bạn:
- Phân biệt **loading, verification, preparation, resolution và initialization**.
- Liệt kê giá trị mặc định của mọi kiểu trường tĩnh primitive/reference, kể cả số không dấu phẩy động và `char`.
- Giải thích vì sao `static int x = 10` vẫn có giá trị mặc định **0** khi preparation hoàn tất.
- Phân biệt `<clinit>`, `ConstantValue`, inline compile-time constants và các thao tác kích hoạt initialization.
- Phân tích trường hợp có thể thấy giá trị 0/null trong khi static initializer đang chạy, mà không ngộ nhận rằng mã Java chạy trong preparation.
- Thử ví dụ Java 17+, dùng `javap -c -v -p` quan sát class file và nhận diện code initialization.
- Tránh nhầm static state với instance fields, array elements và local variables.

## 1. Vị trí của preparation trong vòng đời class

Một sơ đồ khái quát theo JVMS:

~~~text
             Biểu diễn nhị phân của class / interface
                           |
                           v
                         LOADING
                 Tạo class/interface runtime
                           |
                           v
                         LINKING
                           |
                 +---------+---------+
                 |         |         |
           Verification  Preparation  Resolution
                           |
                 Static fields nhận
                 giá trị MẶC ĐỊNH
                           |
                           v
                     INITIALIZATION
             Giá trị ConstantValue nếu có
             và chạy <clinit> theo quy tắc
                           |
                           v
                        EXECUTION
~~~

Sơ đồ mô tả các khái niệm, **không** yêu cầu resolution của mọi symbolic reference phải hoàn tất trước lúc initialization. JVM có thể resolve sớm hoặc theo nhu cầu, trong các giới hạn mà đặc tả cho phép. Điều được bảo đảm rõ ràng: **preparation phải hoàn thành trước initialization** của class/interface.

| Giai đoạn | Công việc tiêu biểu | Không đồng nghĩa |
| --- | --- | --- |
| Loading | Từ dữ liệu class/JAR hoặc nguồn khác tạo class/interface runtime | Mọi lệnh trong static block đã chạy |
| Verification | Xác minh bytecode và ràng buộc kiểu hợp lệ | Chạy nghiệp vụ Java |
| **Preparation** | Tạo các static fields, đặt default values, kiểm tra một số loading constraints | Chạy biểu thức `= 5` hay constructor |
| Resolution | Giải quyết symbolic references tới class/field/method... | Tự động gọi mọi static initializer liên quan |
| Initialization | Thực thi quy trình khởi tạo lớp, kể cả `ConstantValue` và `<clinit>` nếu có | Chỉ đơn giản đặt 0 cho các static fields |

Theo **JVMS `5.4.2**, preparation có thể xảy ra sau khi class/interface đã được tạo và phải xong trước initialization. Từ mã Java thông thường, không có API phổ quát để dừng quá trình chuẩn bị ở một điểm chính xác, sau đó tùy ý đọc static fields mà không chịu các quy tắc khởi tạo class.

## 2. Preparation thực hiện điều gì?

Giả sử:

~~~java
class Profile {
    static int visits = 10;
    static boolean ready;
    static String title = "Java";
    static Object resource = new Object();
}
~~~

Đây là **class minh họa**, chưa có phương thức `main`. Khi preparation của `Profile` hoàn tất, semantics của static fields là:

| Static field | Giá trị sau preparation | Mã ở initialization sẽ làm gì? |
| --- | --- | --- |
| `visits` | `0` | Gán thành `10` |
| `ready` | `false` | Không có initializer, nên tiếp tục là false nếu không bị gán sau đó |
| `title` | `null` | Gán tham chiếu String tương ứng với `"Java"` |
| `resource` | `null` | Chạy biểu thức `new Object()`, sau đó gán tham chiếu |

**Không** có đối tượng `Object` mới được tạo chỉ vì `resource` có kiểu reference. Trong preparation, trường tham chiếu được mặc định là `null`. Việc chạy `new Object()` thuộc **initialization**, không thuộc preparation.

JVM không cần chạy một đoạn bytecode như `putstatic Profile.visits` với giá trị 0 cho mỗi field ở preparation. Đây là hoạt động liên kết của VM; vì thế không thấy “code gán mặc định” trong `javap -c` cũng là điều bình thường.

### Cụm từ “tạo trường static” có nghĩa gì?

Nó có nghĩa VM chuẩn bị **trạng thái field tĩnh của class/interface runtime**. JVMS quy định kết quả ngữ nghĩa, **không bắt buộc** vị trí vật lý hay layout bộ nhớ phải đồng nhất trên mọi JVM. Tránh các nhận định không có căn cứ như “mọi static fields của mọi phiên bản JVM luôn nằm đúng tại một địa chỉ cố định trong Metaspace”.

Các field được tạo theo **declaring class/interface**. Hai class loader có thể định nghĩa hai kiểu runtime khác nhau dù có cùng tên nhị phân, và mỗi kiểu runtime đó có **bản static state riêng**. Static không mang nghĩa “một biến duy nhất cho mọi class loader trong tiến trình”.

## 3. Bảng giá trị mặc định đầy đủ

| Loại field | Ví dụ khai báo | Giá trị mặc định |
| --- | --- | --- |
| `byte` | `static byte b;` | `0` |
| `short` | `static short s;` | `0` |
| `int` | `static int i;` | `0` |
| `long` | `static long l;` | `0L` |
| `float` | `static float f;` | `+0.0f` |
| `double` | `static double d;` | `+0.0d` |
| `char` | `static char ch;` | NUL, mã số `0` (`'\u0000'`) |
| `boolean` | `static boolean ok;` | `false` |
| Class/interface reference | `static String str;` | `null` |
| Array reference | `static int[] data;` | `null` |
| Reference đến object tự định nghĩa | `static Worker worker;` | `null` |

Điểm dễ nhầm:

- `char` nhận **code unit 0**, khác ký tự chữ số `'0'` (code unit 48) và khác khoảng trắng.
- `float` và `double` mặc định là **dương 0**, không phải NaN, vô cực hoặc âm 0.
- `String` mặc định **null**, không phải chuỗi rỗng `""`.
- Array reference mặc định **null**, không phải mảng độ dài 0.
- Các field số nguyên đều có giá trị số học 0; `boolean` là false, không phải một object `Boolean.FALSE` được tạo.
- Bảng trên nói về trạng thái **sau preparation**; field có thể tiếp tục giữ giá trị đó sau initialization nếu không có phép gán thay thế.

### Static fields không phải local variables

Ví dụ:

~~~java
class Example {
    static int shared;

    void work() {
        int local;
        // System.out.println(local); // Không hợp lệ: local chưa được gán.
        System.out.println(shared);    // Hợp lệ: static field có default 0.
    }
}
~~~

Đây là code class minh họa, không phải chương trình độc lập. Java yêu cầu **definite assignment** đối với local variables trước khi đọc chúng. Field là phần trạng thái được VM gán default values theo quy tắc của field; không được lẫn hai cơ chế.

## 4. Preparation khác hẳn initialization

So sánh:

~~~java
class ClockState {
    static int ticks = 15;

    static {
        System.out.println("static block");
    }
}
~~~

Trong preparation, `ticks` có default `0`. Khi initialization thực thi, biểu thức `ticks = 15` và static block chạy theo thứ tự mã nguồn thích hợp. Compiler Java thường phát bytecode trong phương thức **`<clinit>`**:

~~~text
bipush        15
putstatic     #N    // ClockState.ticks:I
getstatic     #M    // java/lang/System.out
ldc           #K    // "static block"
invokevirtual #P    // java/io/PrintStream.println
return
~~~

Đây là **bytecode minh họa**, không phải output đảm bảo cùng chỉ số `#N`/`#M` trên mọi compiler. Thấy `putstatic` dùng để gán 15 nghĩa là đã có **explicit initialization logic**. Preparation đã tạo field và default value từ trước; nó không cần chạy code này.

| Câu hỏi | Preparation | Initialization |
| --- | --- | --- |
| Field `static int x = 15` có trạng thái chưa? | Có, default 0 | Gán x thành 15 |
| JVM chạy phương thức `initializeX()` không? | Không | Có nếu explicit initializer cần |
| Static block chạy không? | Không | Có |
| `<clinit>` chạy không? | Không | Có nếu class có và cần chạy |
| Field tham chiếu `= new Object()` đã có object chưa? | Chưa, default null | Constructor/new chạy theo initializer |
| Có liên quan `ConstantValue` không? | Không gán giá trị đó ở preparation theo JVMS 21 | Gán theo quy trình initialization, **trước** `<clinit>` |

Phải phân biệt **thứ tự thành phần trong đặc tả** với thời điểm một thread ứng dụng có thể quan sát. Không có nghĩa một câu lệnh ngoài lớp có thể chủ động đọc static field giữa hai giai đoạn mà không kích hoạt initialization.

## 5. Ví dụ Java 17+ quan sát tác dụng của default value

Ví dụ hoàn chỉnh sau giúp quan sát giá trị mặc định của field trong **quá trình chạy initializer**, trước khi một initializer phía sau được thực hiện. Nó không làm JVM thực thi Java code trong preparation.

Tạo tệp **`PreparationDemo.java`**:

~~~java
public class PreparationDemo {
    static class State {
        static boolean enabled;
        static long requests;
        static double ratio;
        static char letter;
        static Object object;

        static int first = readLater();
        static int later = 21;
        static final int CONSTANT = 7;

        static int readLater() {
            System.out.println("during init: later=" + later);
            return later + 1;
        }
    }

    public static void main(String[] args) {
        System.out.println("start");
        System.out.println("first=" + State.first);
        System.out.println("enabled=" + State.enabled);
        System.out.println("requests=" + State.requests);
        System.out.println("ratio=" + State.ratio);
        System.out.println("letterCode=" + (int) State.letter);
        System.out.println("object=" + State.object);
        System.out.println("later=" + State.later);
        System.out.println("constant=" + State.CONSTANT);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 PreparationDemo.java
java PreparationDemo
~~~

**Stdout chính xác:**

~~~text
start
during init: later=0
first=1
enabled=false
requests=0
ratio=0.0
letterCode=0
object=null
later=21
constant=7
~~~

Giải thích chi tiết:

1. Lớp outer `PreparationDemo` được khởi tạo khi launcher gọi `main`. Nested class `State` có vòng đời khởi tạo riêng.
2. Dòng `start` được in trước khi program cần giá trị của `State.first`.
3. Lần đọc `State.first` bằng static field access kích hoạt initialization của `State` theo quy tắc JVM, sau khi preparation của `State` đã hoàn tất.
4. Sau preparation, `State.first = 0` và `State.later = 0`. Các field khác có false/0/+0.0/NUL/null như bảng.
5. Trong `<clinit>`, initializer **`first = readLater()`** chạy **trước** initializer `later = 21`. Phương thức `readLater()` đọc `later` đang là 0, in `during init: later=0`, trả 1.
6. Lúc đó `first` được gán thành 1. Tiếp theo `later` được gán thành 21.
7. Sau khi initialization hoàn tất, các lần đọc trong `main` cho `first=1` và `later=21`.
8. `CONSTANT = 7` là compile-time constant variable. Compiler có thể **inline giá trị 7** vào caller; dòng in constant không chứng minh có `getstatic State.CONSTANT` tại runtime.

**Tại sao dùng phương thức `readLater()`?** Java cấm một số **illegal forward reference** trong field initializers khi truy cập trực tiếp field được khai báo ở phía sau bằng simple name. Đặt việc đọc trong phương thức hợp lệ là cách minh họa có thể compile. Dù JVMS đảm bảo default value, **Java compiler vẫn có quy tắc về tham chiếu trước khai báo** cần tuân thủ.

### Cách diễn đạt chính xác

Không nói “preparation chạy `readLater()`”. Đúng phải là: **preparation đặt `later` về 0; sau đó initialization chạy `readLater()` trước khi gán 21, nên method thấy 0**.

Điều này cũng giải thích tại sao việc thấy 0 không đủ để biết class *đang* ở preparation: field có thể có giá trị 0 trước khi initializer gán hoặc vì không có initializer nào, kể cả sau khi class đã khởi tạo xong.

## 6. ConstantValue: phân biệt với default value

Một bẫy kiến thức phổ biến là nói “`static final` có giá trị ngay trong preparation”. Để chính xác theo **JVMS Java SE 17 §5.4.2, §5.5 và §4.7.2**:

- **Preparation** tạo static fields và gán default values.
- **Initialization** gán giá trị của attribute **`ConstantValue`** cho những `static final` fields thích hợp, **trước khi gọi phương thức `<clinit>`**.
- Sau đó phần static initialization code trong `<clinit>` (nếu có) thực hiện các initializer còn lại.

Ví dụ:

~~~java
class Sample {
    static final int LIMIT = 10;
    static final String LABEL = "ok";
    static int counter = 5;
    static final Integer BOXED = Integer.valueOf(6);
}
~~~

Đây là class minh họa. Ý nghĩa từng field:

| Field | Default từ preparation | Có thể có `ConstantValue`? | Cách đạt giá trị khai báo |
| --- | --- | --- | --- |
| `LIMIT` | 0 | Có, `int 10` | Gán ConstantValue trong initialization |
| `LABEL` | null | Có, `String ok` | Gán ConstantValue trong initialization |
| `counter` | 0 | Không chỉ vì initializer literal, do không final | `<clinit>` gán 5 bằng `putstatic` |
| `BOXED` | null | Không theo quy tắc constant variable primitive/String | `<clinit>` gọi `Integer.valueOf` rồi gán |

### Ví dụ runnable để xem attribute

Tạo **`ConstantValueDemo.java`**:

~~~java
public class ConstantValueDemo {
    static final int LIMIT = 100;
    static final String LABEL = "ready";

    static int dynamic = 23;
    static final Integer BOXED = Integer.valueOf(7);

    static {
        System.out.println("initialized");
    }

    public static void main(String[] args) {
        System.out.println("limit=" + LIMIT);
        System.out.println("label=" + LABEL);
        System.out.println("dynamic=" + dynamic);
        System.out.println("boxed=" + BOXED);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 ConstantValueDemo.java
java ConstantValueDemo
javap -v -p ConstantValueDemo
javap -c -p ConstantValueDemo
~~~

**Stdout của chương trình:**

~~~text
initialized
limit=100
label=ready
dynamic=23
boxed=7
~~~

Khi đọc `javap -v`, tìm:
- `LIMIT`: flag `ACC_STATIC, ACC_FINAL`, descriptor `I`, attribute **`ConstantValue: int 100`**.
- `LABEL`: descriptor `Ljava/lang/String;` và attribute **`ConstantValue: String ready`**.
- `dynamic`: không có `ConstantValue` chỉ vì initializer là 23; thường được gán bằng `putstatic` trong `<clinit>`.
- `BOXED`: khởi tạo bằng lời gọi `Integer.valueOf(7)` trong `<clinit>`, không tự tạo object Integer ở preparation.

**Lưu ý:** các hằng compile-time có thể được compiler **inline vào caller**. Một class bên ngoài chỉ đọc `Sample.LIMIT` có thể không phát `getstatic` và không kích hoạt initialization của `Sample` vì giá trị đã ở chính caller. Nếu đổi giá trị constant trong thư viện nhưng không biên dịch lại caller, caller có thể còn giữ giá trị cũ.

Không dùng việc in `LIMIT=100` để suy diễn nó được gán lúc preparation; đặc tả quy định ranh giới gán ConstantValue rõ ràng.

## 7. Mã trong `<clinit>` và thứ tự chạy

Java compiler có thể tổng hợp các **static field initializers** và **static initialization blocks** thành method đặc biệt `<clinit>` theo thứ tự source. Ví dụ:

~~~java
class Steps {
    static int first = log("first", 1);

    static {
        System.out.println("block");
    }

    static int second = log("second", 2);

    static int log(String label, int result) {
        System.out.println(label);
        return result;
    }
}
~~~

Đây là class minh họa chưa có `main()`. Khi initialization của `Steps` được kích hoạt và diễn ra bình thường, side effects xuất hiện:

~~~text
first
block
second
~~~

Preparation đã tạo cả `first` và `second` với default 0 **trước** những dòng in này; nó không thực thi `log` hoặc `println`.

Không phải class nào cũng có `<clinit>` trong file biên dịch. Nếu không có phần static initialization bytecode cần chạy, compiler có thể không phát method đó. **Không thấy `<clinit>` không chứng minh đã bỏ qua preparation**.

### Class và interface

Interface cũng có static fields. Trong Java source, field của interface mặc nhiên là **`public static final`**, nhưng initializer có thể là một phép gọi method và **không phải compile-time constant**:

~~~java
interface FeatureFlags {
    int FAST_LIMIT = 64;
    String JAVA_VERSION = System.getProperty("java.version");
}
~~~

Đây là interface minh họa. Các static fields được preparation trước initialization. `FAST_LIMIT` có thể dùng `ConstantValue`, còn `JAVA_VERSION` cần code thực thi trong interface initialization. Interface có quy tắc kích hoạt initialization riêng; tạo object implementing interface không đơn giản đồng nghĩa “khởi tạo mọi interface liên quan ngay lập tức”.

## 8. Static field, instance field, array element và local variable

**Preparation là thao tác đối với static fields của class/interface**, không phải cơ chế cấp phát/đặt mặc định cho mọi dữ liệu trong chương trình.

| Loại dữ liệu | Nguồn của default value | Ví dụ |
| --- | --- | --- |
| **Static field** | Preparation của class/interface khai báo | `static int total;` → 0 |
| **Instance field** | Tạo object, trước constructor/instance initialization | `int age;` ở mỗi object mới → 0 |
| **Array element** | Tạo mảng, mỗi phần tử được gán default | `new int[3]` → 0,0,0 |
| **Local variable** | Java yêu cầu gán chắc chắn trước khi đọc; không được tự đọc một giá trị mặc định tùy ý | `int x; println(x);` lỗi compile-time |

Ví dụ hoàn chỉnh **`DefaultKindsDemo.java`**:

~~~java
import java.util.Arrays;

public class DefaultKindsDemo {
    static int shared;
    int perObject;

    public static void main(String[] args) {
        DefaultKindsDemo first = new DefaultKindsDemo();
        DefaultKindsDemo second = new DefaultKindsDemo();
        int[] numbers = new int[3];

        first.perObject = 5;

        System.out.println("shared=" + shared);
        System.out.println("first=" + first.perObject);
        System.out.println("second=" + second.perObject);
        System.out.println("array=" + Arrays.toString(numbers));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DefaultKindsDemo.java
java DefaultKindsDemo
~~~

**Stdout chính xác:**

~~~text
shared=0
first=5
second=0
array=[0, 0, 0]
~~~

`shared` là một static field được preparation, hai field `perObject` thuộc hai object khác nhau, còn ba phần tử array được mặc định khi cấp phát array. Tất cả có thể thấy số 0, nhưng **không phải đều là hậu quả của class preparation**.

## 9. JVM liên kết preparation với loại class nào?

Danh tính runtime của class/interface không chỉ dựa vào chữ tên lớp trong source: JVM phân biệt bằng **binary name + defining class loader**. Hai defining loaders khác nhau có thể tạo hai class runtime cùng binary name, với trạng thái static khác nhau:

~~~text
com.example.Config defined by Loader A
  -> static counter A
  -> preparation A / initialization A

com.example.Config defined by Loader B
  -> static counter B
  -> preparation B / initialization B
~~~

Đây là sơ đồ khái niệm. Do đó nói “static variable luôn chỉ có một bản trên toàn JVM” không chính xác đối với ứng dụng dùng plugin class loaders hoặc module layers.

### Loading constraints trong preparation

Ngoài việc gán default values, **JVMS `5.4.2** áp đặt những **loading constraints** khi xử lý một số method overriding/selection có type signature liên quan đến các class loaders khác nhau.

Mục tiêu là duy trì type identity và liên kết method an toàn. Nếu constraint bị vi phạm, JVM có thể ném **`LinkageError`**, khiến preparation/linking thất bại. Không nên coi preparation chỉ là một vòng đặt 0 mà hoàn toàn không thể liên quan đến lỗi kiểu/liên kết.

**Không đồng nhất với resolution**: resolution giải quyết symbolic references đến các class/field/method và thực thể khác theo quy tắc riêng. Nó có thể thực hiện sớm hoặc theo nhu cầu; preparation phải hoàn thành trước initialization.

## 10. Những thao tác kích hoạt initialization

Mã Java thường không được quan sát field ở trạng thái giữa preparation và initialization vì các thao tác dùng class hay static field có thể **kích hoạt initialization**. Một số nguyên nhân thường gặp:
- `new SomeClass()` (tạo instance).
- Đọc static field qua `getstatic` hoặc ghi qua `putstatic` theo các quy tắc của JVM.
- Gọi static method qua `invokestatic`.
- Một số hành động reflection hoặc method-handle được đặc tả kích hoạt initialization.
- Class được khởi tạo có thể đòi hỏi superclass hoặc superinterfaces liên quan được khởi tạo theo quy tắc.

Không phải mọi thao tác “nhắc tên lớp” đều kích hoạt initialization:
- Lấy class literal `SomeClass.class` không đơn thuần chạy static block chỉ vì tên lớp được nhắc.
- Compile-time constants có thể được inline, không cần đọc field runtime.
- `Class.forName(className, false, loader)` cho phép lấy Class mà không yêu cầu initialization do lời gọi ấy; nhưng điều đó **không có nghĩa bạn được đọc static field bằng reflection mà bỏ qua các quy tắc initialization**.

**Quan trọng:** một class có thể được loaded/linked trước khi initializer chạy; không được đồng nhất “JVM biết class rồi” với “mọi static initializer đã hoàn tất”.

## 11. Điều gì xảy ra khi nhiều thread cùng dùng class?

JVM có quy tắc đồng bộ hóa quá trình initialization để xử lý nhiều thread đồng thời. Một thread có thể đang chạy `<clinit>`, thread khác yêu cầu initialization của cùng class phải tuân thủ cơ chế chờ/thứ tự của JVM. Nếu chính thread đang khởi tạo lại gián tiếp yêu cầu cùng class, có quy tắc nhận diện **initialization in progress**.

Việc một initializer đọc field khác quá sớm có thể nhìn thấy giá trị **default** hoặc giá trị mới được gán một phần trong chuỗi initialization. Không nên dùng “thời gian ở giữa preparation và initialization” như một cơ chế giao tiếp thread. Thay vào đó, tổ chức khởi tạo không có vòng phụ thuộc hoặc có phương án điều phối rõ ràng.

Ví dụ **minh họa** vòng phụ thuộc:

~~~java
class A {
    static int x = B.y + 1;
}

class B {
    static int y = A.x + 1;
}
~~~

Đây là hai class declarations, không có main. Nếu A và B phụ thuộc vòng khi được initialized, việc một bên đọc static field của bên kia trước khi initializer tương ứng chạy có thể khiến nó thấy default 0. Tùy thứ tự kích hoạt và thực thi, kết quả cuối có thể khác mong đợi nếu giả định tất cả fields đã có giá trị cuối.

### Preparation không thay thế thread safety

Preparation đặt `static int counter` về 0, **không** làm `counter++` trở thành atomic. Về sau, nhiều thread cùng read-modify-write phải dùng công cụ synchronization phù hợp nếu cần tính đúng đắn, ví dụ `AtomicInteger` hoặc synchronized block theo thiết kế ứng dụng.

## 12. Sử dụng javap để thấy khác biệt

Đối với file đã biên dịch từ ví dụ `PreparationDemo.java`:

~~~bash
javap -v -p 'PreparationDemo$State'
javap -c -p 'PreparationDemo$State'
~~~

**Trong Windows cmd.exe**, có thể dùng biểu thức `PreparationDemo$State` theo cú pháp shell thích hợp; trong PowerShell, single quotes như trên ngăn shell can thiệp vào dấu `$`. Các ví dụ trên giả định file class đã được biên dịch trong thư mục hiện hành.

Khi đọc output:
1. Field declaration của nested class chứa `ACC_STATIC`; xác định tên, descriptor và các flags.
2. `first` và `later` có descriptor `I` (int); các field khác có các descriptor `Z`, `J`, `D`, `C` hoặc kiểu reference.
3. Trong `<clinit>`, tìm instruction gọi `readLater()`, `putstatic ...first:I`, nạp giá trị 21 rồi `putstatic ...later:I`.
4. Field `CONSTANT` có thể có attribute `ConstantValue` vì là compile-time constant.
5. Không có lệnh `putstatic` gán 0 ban đầu cho **mọi** field; default values thuộc preparation, không phải bytecode Java phải có trong `<clinit>`.
6. Bytecode index `#N` có thể khác giữa compiler và phiên bản JDK. Đừng hardcode chúng trong diễn giải.

Một sơ đồ class file:

~~~text
field_info later:
  access_flags: ACC_STATIC
  descriptor:   I

Preparation:
  later = 0          (hoạt động VM)

Initialization:
  <clinit>:
    bipush 21
    putstatic #N      // later:I
~~~

Đây là sơ đồ kết hợp thông tin class file và hoạt động runtime, **không** phải một dump nhị phân exact của toàn bộ class.

## 13. Lỗi và ngộ nhận thường gặp

| Nhận định hoặc triệu chứng | Phân tích đúng |
| --- | --- |
| “`static int x = 10` được gán 10 trong preparation.” | Preparation đặt 0; explicit initializer 10 thuộc initialization. |
| “Mọi field reference có object được tạo sẵn.” | Default là `null`; constructor/mảng chỉ được cấp phát khi code thực thi. |
| “`static final int X=10` nhất định được gán trong preparation.” | Theo JVMS 21, `ConstantValue` được gán trong quy trình initialization trước `<clinit>`. |
| “Giá trị field bằng 0 chứng minh JVM đang ở preparation.” | Không. Field có thể giữ 0 cả sau initialization hoặc được đọc trước initializer của nó trong `<clinit>`. |
| “Không thấy `<clinit>` nghĩa là preparation không xảy ra.” | Sai. Preparation là việc VM làm, không phải method Java bắt buộc xuất hiện trong class file. |
| “Static object field luôn có một bản duy nhất trong toàn JVM.” | Mỗi **class runtime** có static state riêng; class loaders khác nhau có thể định nghĩa class khác nhau. |
| “`Class.forName(name,false,loader)` cho phép đọc static values trước initialization.” | Không tự cung cấp khả năng bypass quy tắc initialization khi đọc static field. |
| “Default values của instance/array cũng do class preparation.” | Sai: instance/array nhận defaults lúc object/array creation. |
| “Preparation không bao giờ có lỗi.” | Loading constraints trong preparation có thể thất bại, gây `LinkageError`. |
| “Initialization thất bại có nghĩa preparation chưa làm.” | Sai: preparation phải hoàn tất trước initialization. |
| “Field `volatile` được chuẩn bị nên `x++` atomic.” | Sai: volatile là semantics về memory visibility/order, không biến read-modify-write thành atomic. |
| “Class đã loaded tức là đã initialized.” | Sai: loading/linking và initialization là các bước riêng. |

### Khi xảy ra lỗi

**`VerifyError`** thường liên quan verification, **`ClassFormatError`** liên quan định dạng class file, **`NoSuchFieldError`** liên quan field resolution, còn **`ExceptionInInitializerError`** thường bắt nguồn từ mã chạy trong initialization của class. Không nên quy toàn bộ lỗi vòng đời lớp về preparation.

Khi chẩn đoán, xem:
1. Mã đang load, link hay chạy static initializer?
2. Lỗi có cause từ `<clinit>` hay không?
3. Class và dependency/JAR nào thực sự được loader tải?
4. Có initializer đọc field khai báo phía sau hoặc có vòng phụ thuộc giữa các class?
5. Field bị thay descriptor/static modifier giữa build và runtime không?
6. Compiler có thể đã inline một compile-time constant không?

## 14. Câu hỏi tự kiểm tra

**1.** Preparation nằm trong loading, linking hay initialization?

**Đáp án:** Nó là một bước của **linking**; phải hoàn thành trước initialization.

**2.** Sau preparation, `static int count = 5;` có giá trị nào?

**Đáp án:** **0**. Lệnh gán 5 thuộc initialization.

**3.** `static String name;` mặc định có phải chuỗi rỗng không?

**Đáp án:** Không. Là `null`.

**4.** `static char letter;` là ký tự chữ số 0 hay code unit 0?

**Đáp án:** Code unit **0** (NUL, `'\u0000'`), không phải `'0'`.

**5.** Tại sao `State.readLater()` trong ví dụ lại nhìn thấy `later=0`?

**Đáp án:** Preparation đã đặt default 0. Phương thức được chạy **trong initialization**, trước câu lệnh gán `later = 21`.

**6.** `ConstantValue` của `static final int LIMIT` được gán ở preparation hay initialization theo JVMS 21?

**Đáp án:** Trong **initialization**, trước invocation của `<clinit>`.

**7.** Đọc một constant variable từ caller có chắc làm class khai báo initialized không?

**Đáp án:** Không. Compiler có thể inline giá trị, không cần `getstatic`.

**8.** Static field và instance field khác nhau thế nào ở thời điểm nhận default value?

**Đáp án:** Static field nhận default trong class/interface preparation; instance field nhận default khi object được cấp phát, trước constructor logic.

**9.** Hai class loader định nghĩa cùng tên class có bắt buộc chia sẻ static field không?

**Đáp án:** Không. Chúng có thể tạo các class runtime khác nhau, mỗi bên có state riêng.

**10.** Tại sao không nên coi preparation là chạy một loạt `putstatic 0` do compiler tạo?

**Đáp án:** Preparation được JVM làm như một bước liên kết, không yêu cầu chạy explicit Java bytecode.

**11.** Preparation có liên quan loading constraints không?

**Đáp án:** Có. JVMS `5.4.2 quy định các ràng buộc liên quan overriding/selection; vi phạm có thể gây `LinkageError`.

**12.** Không thấy static initializer trong class file thì class không cần preparation?

**Đáp án:** Sai. Preparation vẫn xảy ra theo cơ chế lifecycle, dù không có mã `<clinit>` cần chạy.

## 15. Ghi nhớ

~~~text
Class / interface đã được load
                |
                v
              LINKING
  +-------------+-------------+
  |             |             |
Verify      PREPARATION     Resolution
                |
                +-- tạo các static fields
                +-- gán DEFAULT VALUES
                |    primitive numeric 0
                |    boolean false
                |    char NUL
                |    references null
                +-- loading constraints cần thiết
                |
                v
           INITIALIZATION
     ConstantValue (nếu có)
     rồi <clinit> (nếu có)
     static initializers / static blocks
                |
                v
       Class initialized

Instance field default: khi tạo object
Array element default: khi tạo array
Local variable: definite assignment
~~~

**Kết luận:** Preparation **không phải** giai đoạn thực thi initializer của Java source. Nó tạo trạng thái static cho class/interface với giá trị **mặc định**, trước initialization. Tách bạch quá trình này với `ConstantValue`, `<clinit>`, object creation và constant inlining là nền tảng để hiểu vòng đời JVM đúng theo đặc tả.

## Tài liệu chính thức

- [JVMS Java SE 17 — 5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2).
- [JVMS Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5).
- [JVMS Java SE 17 — 4.7.2 ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2).
- [JVMS Java SE 17 — 2.3 Primitive Types and Values](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.3).
- [JVMS Java SE 17 — 2.4 Reference Types and Values](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.4).
- [JLS Java SE 17 — 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
- [JLS Java SE 17 — 8.3.3 Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3).
- [JDK 17 — javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
