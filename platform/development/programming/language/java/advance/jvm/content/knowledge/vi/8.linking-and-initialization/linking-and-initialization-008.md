# Hằng số biên dịch, class literal và truy cập trường khai báo ở lớp cha

## 1. Vấn đề cốt lõi: nhắc tới một kiểu không nhất thiết khởi tạo kiểu đó

Khi Java source viết **T.CONSTANT**, **T.class**, **Child.someField** hoặc **T.staticMethod()**, tên kiểu đứng trong biểu thức có thể giống nhau, nhưng **quy tắc khởi tạo lớp (class initialization)** không giống nhau. JVM phân biệt **lớp chứa mã nguồn tham chiếu**, **lớp thực sự khai báo thành viên**, **trường có phải constant variable hay không**, và **thao tác có yêu cầu active use**.

Ba hiện tượng cần nắm vững:

1. **Compile-time constants:** Một constant variable có kiểu nguyên thủy hoặc String, được khai báo final và khởi tạo bằng constant expression, thường được biên dịch thành **giá trị hằng tại nơi dùng**. Đọc field này **không buộc lớp khai báo phải initialization**.
2. **Class literal:** Biểu thức **SomeType.class** nhận **Class<?>** tương ứng mà **không tự buộc chạy static initializer** của SomeType. Lấy Class object khác với gọi **Class.forName(name)** yêu cầu initialization.
3. **Inherited static field:** Nếu **Child.VALUE** thực chất tham chiếu field **VALUE khai báo trong Parent**, thì quy tắc initialization xét **Parent**, không phải tự động xét Child. Dấu tên **Child** trong source không biến field trở thành field do Child khai báo.

Mục tiêu của bài học là dự đoán chính xác **khi nào một lớp được initialized, static code nào chạy, giá trị nào được in**, rồi đối chiếu bằng **javap** và Java 17+. Đồng thời bạn cần hiểu ảnh hưởng tới binary compatibility, JVM class loading và reflection.

## 2. Đặt vấn đề trong vòng đời JVM

Một class/interface thông thường có ba nhóm công việc liên quan:

~~~text
Class bytes
    |
    v
LOADING
  - Tìm/đọc định nghĩa
  - Tạo runtime class và Class object
  - Gắn defining class loader
    |
    v
LINKING
  - Verification: kiểm tra cấu trúc và bytecode
  - Preparation: tạo static fields và giá trị mặc định
  - Resolution: giải quyết symbolic references khi cần
    |
    v
INITIALIZATION khi có yêu cầu
  - Đảm bảo superclass và các superinterface
    thuộc diện cần khởi tạo được xử lý
  - Thi hành quy tắc ConstantValue và code <clinit>
  - Chạy static field initializers / static blocks
    |
    v
Class sẵn sàng cho active use
~~~

**Loading không đồng nghĩa Initialization.** Việc biểu diễn một class tồn tại ở runtime, lớp được verify/prepare hay một symbolic reference đã được resolve **không tự chứng minh static block của class đã chạy**.

**Initialization** xảy ra theo những điều kiện cụ thể trong JLS §12.4.1 và JVMS §5.5. Việc một dòng Java ghi tên lớp chưa đủ để quyết định.

### 2.1. Bảng kiểm tra nhanh

| Thao tác Java | Có yêu cầu initialization của T không? |
| --- | --- |
| **new T()** | **Có**, nếu T là class và chưa được initialized |
| **T.someStaticMethod()** khi method thực sự khai báo tại T | **Có** |
| Ghi **T.someStaticField = value** khi field do T khai báo | **Có** theo quy tắc dùng field |
| Đọc **T.mutableOrRuntimeStaticField** do T khai báo | **Có** nếu field không là constant variable |
| Đọc **T.COMPILE_TIME_CONSTANT** | **Không** kích hoạt initialization chỉ bởi thao tác đọc constant variable |
| **T.class** | **Không** kích hoạt initialization của T chỉ bởi class literal |
| **Class.forName("pkg.T")** | **Có** yêu cầu initialization theo overload một tham số |
| **Class.forName("pkg.T", false, loader)** | **Không** yêu cầu initialization, nhưng vẫn có thể load/link |
| **ClassLoader.loadClass("pkg.T")** thông thường | Không tự yêu cầu initialization |
| **new T[10]** | Không init component class T chỉ vì tạo array |
| **Child.inheritedStaticField** | Xét lớp/interface **thực sự khai báo field**, không suy từ chữ Child |

Bảng nói về **lớp mục tiêu**. Một biểu thức có thể làm **lớp khác** khởi tạo, chẳng hạn code ở biểu thức receiver hoặc một static method được gọi phụ trợ. Cần xác định operation hoàn chỉnh nếu có side effects.

## 3. Constant variable là gì, chính xác theo JLS?

JLS §4.12.4 định nghĩa **constant variable**: một biến **final**, có kiểu **primitive** hoặc **String**, được **khởi tạo bằng một constant expression** (JLS §15.29).

Ba điều kiện đều cần:

1. **final:** giá trị biến không được gán lại sau khi khởi tạo hợp lệ.
2. **Kiểu primitive hoặc String:** ví dụ int, long, boolean, char, double, String; **không** bao gồm Integer, Long, Object, List.
3. **Initializer là constant expression:** biểu thức có thể được compiler tính theo ngữ nghĩa compile time, ví dụ **10 + 20**, **"Hello" + "!"**, **5 > 3**.

**static không nằm trong định nghĩa chung** của constant variable. Tuy nhiên bài này chú trọng **static final fields** vì quy tắc class initialization trực tiếp liên quan tới truy cập static field. Một local variable hoặc instance final field cũng có thể thỏa định nghĩa constant variable theo JLS trong ngữ cảnh của nó.

### 3.1. Ví dụ là compile-time constants

~~~java
// Mã minh họa khai báo trong một class Java:
static final int MAX_USERS = 10 * 4;
static final long TIMEOUT = 2_000L + 500L;
static final String VERSION = "v" + "1";
static final boolean ENABLED = 3 < 5;
static final char LETTER = 'A';
static final double RATIO = 0.5;
~~~

Mỗi field trên có kiểu primitive hoặc String, final, và initializer là một constant expression hợp lệ.

Đặc biệt **VERSION** là String constant expression dù có phép **+**; compiler có thể gộp thành **"v1"** ngay khi biên dịch client.

### 3.2. Những field static final nhưng **không** là constant variable

~~~java
// Mã minh họa trong một class:
static final Integer BOXED = 10;
static final int PARSED = Integer.parseInt("10");
static final String CREATED = new String("hello");
static final String SYSTEM_VALUE = System.getProperty("app.mode");
static final java.util.List<String> NAMES = java.util.List.of("a");
static final int COMPUTED = compute();

static int compute() {
    return 42;
}
~~~

Lý do:

| Field | Vì sao không phải constant variable? |
| --- | --- |
| **BOXED** | Kiểu **Integer** là reference wrapper, không phải primitive hay String |
| **PARSED** | Có lời gọi method **Integer.parseInt**, không là constant expression |
| **CREATED** | Có **new String(...)**, không là constant expression |
| **SYSTEM_VALUE** | Giá trị đến từ runtime system property |
| **NAMES** | Kiểu List không nằm trong nhóm kiểu được JLS cho constant variable |
| **COMPUTED** | Có lời gọi method **compute()**, dù method luôn trả 42 |

Vì vậy **final** không đồng nghĩa “compiler đã biết giá trị”; **static final** cũng không đồng nghĩa “đọc vào không init lớp”. Phân biệt này là trọng tâm khi quan sát output của static blocks.

### 3.3. Constant expression có thể chứa gì?

Các dạng phổ biến theo JLS §15.29:

- Primitive literals, string literals và text blocks khi phù hợp.
- Unary operators **+**, **-**, **~**, **!**; không gồm **++/--**.
- Số học **+**, **-**, **\***, **/**, **%**; các phép dịch bit và một số phép so sánh.
- Logical/bitwise operators, **&&**, **||** và conditional operator **?:**.
- Cast hợp lệ và biểu thức trong dấu ngoặc.
- Tên đơn/qualified names tham chiếu những **constant variables** khác.

Không bao gồm method invocation, **new**, field đọc không phải constant variable, đọc file, đồng hồ, property runtime hoặc phép tính phụ thuộc trạng thái ứng dụng.

Ví dụ:

~~~java
// Mã minh họa:
static final int BASE = 40;
static final int ANSWER = BASE + 2;     // constant variable
static final int DELAY = loadDelay();   // không phải constant variable

static int loadDelay() {
    return 100;
}
~~~

**ANSWER** được tính từ constant variable **BASE** và literal 2 nên là compile-time constant; **DELAY** phụ thuộc lời gọi method.

## 4. Vì sao đọc compile-time constant không kích hoạt <clinit>?

Khi client biên dịch:

~~~java
int max = Config.MAX_USERS;
~~~

với **MAX_USERS** là một **static final int** constant variable, Java compiler phải dùng giá trị hằng của field tại compile time theo quy tắc binary form. Bytecode của client có thể dùng một instruction đẩy hằng như **bipush/sipush/ldc** thay vì **getstatic Config.MAX_USERS**.

Nếu không thực thi **getstatic** để đọc field runtime, thao tác ấy không cần khởi tạo Config chỉ để lấy MAX_USERS.

Ví dụ minh họa:

~~~text
Java source:
    System.out.println(Settings.PORT);

Với Settings.PORT là constant variable int = 8080:

Bytecode client về mặt khái niệm:
    getstatic java/lang/System.out:Ljava/io/PrintStream;
    sipush 8080
    invokevirtual java/io/PrintStream.println:(I)V

Không cần:
    getstatic Settings.PORT:I
~~~

**Dãy lệnh mang tính minh họa**; bytecode chính xác phụ thuộc compiler. Với số 8080, **sipush** là một cách biểu diễn phù hợp vì 8080 nằm trong miền signed short. Điều quan trọng là client sử dụng **giá trị hằng** chứ không bắt buộc đọc static field tại runtime.

**Lưu ý:** Không được suy rằng **Settings chưa được load** chỉ vì static block không in log. JVM có thể đã nạp/liên kết lớp vì lý do khác, nhưng chưa initialization. “Không init” và “chưa load” là hai kết luận khác nhau.

### 4.1. ConstantValue trong class file

Các static final constant fields có thể mang **ConstantValue attribute**. JVMS quy định cách gán giá trị ConstantValue như một phần của quá trình khởi tạo lớp, với thứ tự được đặc tả. Đây là metadata để runtime biết giá trị constant field **nếu/ khi class được khởi tạo**.

Hãy phân biệt hai góc nhìn:

- **Client compile-time:** đọc một constant variable theo Java source có thể dùng giá trị đã inlined, không cần active use khởi tạo lớp khai báo.
- **Class runtime:** class file có khai báo field và thông tin ConstantValue của nó; khi initialization class thực sự diễn ra, VM đảm bảo static constant fields có giá trị đúng theo đặc tả.

Do đó, không có mâu thuẫn khi một client in đúng giá trị 8080 dù static block trong Settings chưa chạy.

### 4.2. Giá trị constant có thể bị nhúng vào client cũ

Nếu thư viện phiên bản 1 có:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 5;
}
~~~

Client đã được biên dịch với phiên bản 1 có thể mang hằng **5** ngay trong bytecode.

Nếu thay thư viện thành:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 7;
}
~~~

mà **không biên dịch lại client**, client cũ có thể tiếp tục dùng **5**. Khi recompile client với phiên bản mới, nó có thể dùng **7**. Đây là một rủi ro **binary compatibility** khi publish public compile-time constants làm configuration thay đổi giữa các bản phát hành.

**Đừng chẩn đoán nhầm là classloader cache:** class runtime mới có thể được nạp đúng nhưng client bytecode vẫn chứa số cũ từ compile time. Muốn giá trị có thể đổi độc lập với client artifact, dùng API truy cập runtime phù hợp (ví dụ static method, cấu hình ngoài hoặc field không phải constant variable) và thiết kế compatibility rõ ràng.

## 5. Ví dụ Java 17+ chạy được: constant, class literal và active use

Tạo file **ConstantVsInitialization.java**:

~~~java
public class ConstantVsInitialization {
    static class Target {
        static final int PORT = 8080;
        static final String LABEL = "api" + "-v1";
        static final Integer BOXED = 12;
        static final int DYNAMIC = Integer.parseInt("21");

        static {
            System.out.println("Target:<clinit>");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("main:start");

        Class<?> type = Target.class;
        System.out.println("className=" + type.getSimpleName());

        Class.forName("ConstantVsInitialization$Target", false,
                ConstantVsInitialization.class.getClassLoader());

        System.out.println("port=" + Target.PORT);
        System.out.println("label=" + Target.LABEL);
        System.out.println("main:before-boxed");

        System.out.println("boxed=" + Target.BOXED);
        System.out.println("dynamic=" + Target.DYNAMIC);
        System.out.println("main:end");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ConstantVsInitialization.java
java ConstantVsInitialization
~~~

**Stdout chính xác cho một lần chạy mới:**

~~~text
main:start
className=Target
port=8080
label=api-v1
main:before-boxed
Target:<clinit>
boxed=12
dynamic=21
main:end
~~~

Phân tích theo các mốc:

1. **Target.class** lấy Class object của Target và **getSimpleName()** truy xuất tên; hai thao tác này không tự yêu cầu khởi tạo Target.
2. **Class.forName(...,false,loader)** không yêu cầu initialization, dù nó có thể thực hiện loading/linking.
3. **Target.PORT** và **Target.LABEL** đều là constant variables. Client đã biết giá trị nên không phải active use khởi tạo Target.
4. Đọc **Target.BOXED** là đọc static field **không phải constant variable**. JVM phải khởi tạo Target trước khi trả field; static initializers chạy theo thứ tự văn bản và in **Target:<clinit>**.
5. Target.BOXED trả Integer 12; khi nối string, giá trị được hiển thị **12**.
6. DYNAMIC được tính trong initialization nên đã có giá trị 21. Lần đọc sau không chạy static block lần nữa.

Ví dụ cố ý đặt **Class.forName(false)** và các constant reads trước nonconstant read. Nếu thay bằng **Class.forName("ConstantVsInitialization$Target")** (overload một tham số), Target có thể khởi tạo ngay tại lời gọi forName đó và thứ tự stdout sẽ khác.

## 6. Không phải mọi static final đều có cách đọc giống nhau

Xem các trường hợp:

| Khai báo | Constant variable? | Đọc lần đầu có yêu cầu class initialization không? |
| --- | --- | --- |
| **static final int A = 1;** | Có | Không chỉ vì đọc A |
| **static final String B = "ab" + "c";** | Có | Không chỉ vì đọc B |
| **static final boolean C = true;** | Có | Không chỉ vì đọc C |
| **static final Integer D = 1;** | Không | Có |
| **static final int E = Math.abs(-1);** | Không | Có |
| **static final String F = new String("abc");** | Không | Có |
| **static int G = 1;** | Không | Có |
| **static final int H = Other.CONST;** với Other.CONST là constant variable | Có nếu initializer là constant expression hợp lệ | Không chỉ vì đọc H |
| **static final int I = Other.runtimeValue;** | Không | Có |

Hãy dùng định nghĩa JLS để suy luận, không đoán bằng chữ **final** hay chỉ dựa vào việc giá trị “trông có vẻ đã biết”.

### 6.1. Compile-time constants không phải một cơ chế cấu hình runtime

Nếu chương trình phải đọc giá trị từ environment, system property, tệp cấu hình hoặc database, đó là runtime value. Không nên viết một public constant variable rồi kỳ vọng đổi JAR là tất cả client thấy giá trị mới ngay.

Lựa chọn thiết kế:

- Giá trị cố định theo API/protocol và không dự kiến thay đổi: **public static final primitive/String constant** có thể phù hợp.
- Giá trị có thể thay đổi theo môi trường: cung cấp method đọc configuration hoặc dependency injection, xác định caching/reload.
- Giá trị runtime bất biến sau bootstrap: dùng **static final** được tính lúc initialization (không phải compile-time constant) hoặc instance immutable config, cân nhắc thời điểm load/init và lỗi.
- Thông tin nhạy cảm: tránh hardcode thành public compile-time constant vì nó có thể xuất hiện trong bytecode client và công cụ phân tích.

## 7. Class literal: T.class cung cấp Class mà không gọi <clinit>

Trong Java, **class literal** là biểu thức như:

~~~java
String.class
int.class
int[].class
java.util.List.class
SomeType.class
~~~

Nó trả về **Class<?>** đại diện cho kiểu tương ứng; không phải thao tác tạo một instance của kiểu ấy.

Ví dụ:

~~~java
// Mã minh họa nằm trong một method:
Class<?> c = Heavy.class;
System.out.println(c.getName());
~~~

Nếu Heavy có static block in **"Heavy initialized"**, chỉ viết **Heavy.class** và gọi **getName()** **không bắt buộc** in thông điệp đó.

Các sự kiện cần phân biệt:

- Có **Class object** không có nghĩa **class đã được initialization**.
- Việc tạo/lấy Class object có thể liên quan loading/linking của kiểu, nhưng **không kích hoạt khởi tạo chỉ do class literal**.
- **Class.getName()**, **getSimpleName()** để nhận tên không tương đương lời gọi static method của chính Heavy.
- **Class.forName(name)** có behavior khác: overload một tham số yêu cầu initialization.
- **Class.forName(name,false,loader)** cho phép lookup không yêu cầu initialization; dùng đúng binary name, ví dụ nested member class có dấu **$**.

### 7.1. Class literal không chạy constructor

So sánh:

~~~java
Class<?> type = Widget.class;  // lấy mô tả kiểu
Widget instance = new Widget(); // tạo instance, active use
~~~

**Widget.class** không tạo Widget object và không gọi constructor. **new Widget()** yêu cầu class Widget được khởi tạo trước, rồi JVM cấp phát object và chạy constructor chain theo quy tắc.

Cũng cần phân biệt:

~~~java
Widget[] array = new Widget[3];
~~~

Dòng trên tạo array chứa ba tham chiếu ban đầu đều null. Nó không tạo ba Widget instances và không yêu cầu initialization của Widget chỉ vì component type là Widget.

### 7.2. Primitive và array class literals

**int.class**, **boolean.class**, **String[].class** đều có Class objects tương ứng; primitive/array types có quy tắc class loading riêng. Ví dụ **int.class.getName()** trả **int**, **int[].class.getName()** trả **[I**, **String[].class.getName()** trả **[Ljava.lang.String;**.

Đừng suy rằng có tệp nhị phân **int.class** hoặc **[I.class** trên classpath. Primitive và array runtime types được JVM xử lý theo cơ chế đặc biệt.

## 8. Ba cách lấy Class và khác biệt initialization

| Cách | Yêu cầu initialization? | Lưu ý |
| --- | --- | --- |
| **T.class** | Không tự yêu cầu | Type được biết tại compile time |
| **Class.forName("pkg.T")** | Có | Dùng overload gọi theo name, yêu cầu initialization |
| **Class.forName("pkg.T", true, loader)** | Có | Chọn loader và yêu cầu init |
| **Class.forName("pkg.T", false, loader)** | Không | Chọn loader, không yêu cầu init |
| **loader.loadClass("pkg.T")** | Thông thường không | Giao ước mặc định loadClass(name) không initialize |
| **obj.getClass()** | Không tự init kiểu mới chỉ từ Class object | Object đã tồn tại; lớp đã được init nếu việc tạo object từng cần |
| **T.class.getDeclaredFields()** | Không nhất thiết init T | Reflection metadata inspection không giống Field.get/Field.set |

Nếu dùng API Reflection **Field.get(null)** để đọc một **static field**, contract của Reflection có thể **khởi tạo class khai báo field trước khi lấy giá trị**, kể cả khi field tương ứng trong Java source là một compile-time constant. Vì vậy không được áp dụng quy tắc **source read of constant variable** một cách máy móc cho mọi reflective access.

### 8.1. Lựa chọn API khi viết framework

Với thư viện muốn **quan sát metadata mà chưa thực thi static code**:

~~~java
// Mã minh họa:
Class<?> cls = Class.forName(binaryName, false, loader);
var fields = cls.getDeclaredFields();
~~~

Đây là hướng tiếp cận thường gặp, nhưng vẫn có thể có tác động loading/linking và exception. Không dùng nó để cam kết “hoàn toàn không thực thi code nào trong hệ thống” — các thành phần liên quan khác có thể đã được khởi tạo trước hoặc có hoạt động riêng.

Khi framework cần tạo instance hoặc gọi static initialization, phải công khai thời điểm active use để người sử dụng hiểu side effects và dependency requirements.

## 9. Static field khai báo ở lớp cha: dấu Child không quyết định initialization

JLS §12.4.1 nói rõ: tham chiếu đến một **static field** chỉ gây initialization của **class/interface thực sự khai báo field** theo điều kiện của field, dù cú pháp có thể dùng tên subclass, subinterface hoặc class implement interface.

Xét:

~~~java
class Parent {
    static int count = 10;
}

class Child extends Parent {
    static {
        System.out.println("Child initialized");
    }
}
~~~

Khi viết:

~~~java
System.out.println(Child.count);
~~~

**count** được khai báo ở **Parent**, không phải Child. Nếu chưa được initialized, JVM phải khởi tạo Parent trước khi đọc nonconstant static field. Nhưng chỉ vì source viết **Child.count**, **không bắt buộc** chạy static initializer của Child.

So sánh hai quy tắc:

- **Child.count**: xác định field declaration thực là Parent.count → nonconstant static read → init Parent.
- **Child.ownCount** nếu field thực sự khai báo trong Child: nonconstant static read → init Child, kéo theo init Parent trước đó nếu chưa.

**Đây là quy tắc theo declaring type**, không phải quy tắc “lấy tên lớp gần dấu chấm nhất”.

### 9.1. Khi field của Parent là compile-time constant

~~~java
class Parent {
    static final int LIMIT = 10;
}

class Child extends Parent {}
~~~

**Child.LIMIT** tham chiếu tới **Parent.LIMIT**, một constant variable. Đọc nó **không yêu cầu initialization** của Parent hay Child chỉ từ thao tác đó. Compiler có thể nhúng literal 10 tại nơi dùng.

Như vậy có hai chiều độc lập:

1. **Ai là declaring class?** — Parent.
2. **Field có phải constant variable?** — Có hoặc không.

Cần trả lời cả hai, không áp dụng một quy tắc chung kiểu “static field luôn init lớp trước”.

### 9.2. Trường bị che khuất (field hiding) thì sao?

~~~java
class Parent {
    static int value = 1;
}

class Child extends Parent {
    static int value = 2;
}
~~~

Ở đây **Child.value** là field thực sự **khai báo trong Child**, không phải field được thừa kế. Vì vậy đọc **Child.value** là active use của Child; JVM phải init superclass Parent trước khi init Child.

Ngược lại, đọc **Parent.value** chỉ cần init Parent. Cùng identifier **value** nhưng là **hai fields khác nhau**, có thể có storage và lifecycle khác nhau.

**Không nhầm field hiding với overriding:** static fields không được override theo dispatch đa hình như instance methods. Compiler giải quyết field reference theo kiểu và declaration thích hợp.

## 10. Ví dụ Java 17+ chạy được: Parent field, Child field, compile-time constant

Tạo file **InheritedStaticDemo.java**:

~~~java
public class InheritedStaticDemo {
    static class Parent {
        static final int LIMIT = 3;

        static int count = startCount();

        static int startCount() {
            System.out.println("Parent:<clinit>");
            return 10;
        }
    }

    static class Child extends Parent {
        static int own = initializeOwn();

        static int initializeOwn() {
            System.out.println("Child:<clinit>");
            return 20;
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("constant=" + Child.LIMIT);
        System.out.println("inherited=" + Child.count);
        System.out.println("after-parent");
        System.out.println("own=" + Child.own);
        System.out.println("end");
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 InheritedStaticDemo.java
java InheritedStaticDemo
~~~

**Stdout chính xác:**

~~~text
begin
constant=3
Parent:<clinit>
inherited=10
after-parent
Child:<clinit>
own=20
end
~~~

Phân tích từng dòng:

1. **Child.LIMIT** là field constant khai báo ở Parent. Client dùng giá trị hằng 3; không yêu cầu Parent hay Child initialize.
2. **Child.count** được compiler xác định là **Parent.count**. Đây là nonconstant static field; JVM init Parent, gọi startCount() và in **Parent:<clinit>**.
3. **Child** vẫn chưa cần initialized sau lần đọc **Child.count**.
4. **Child.own** là nonconstant static field khai báo trong Child. JVM init Child; Parent đã init nên không chạy lại.
5. Parent và Child là hai runtime classes có trạng thái initialization riêng; thứ tự source qualifier không làm chúng nhập làm một.

Lưu ý chương trình **chỉ dùng static field reads** để minh họa; không cần tạo instance Child bằng **new Child()**.

## 11. Một trường static được truy cập qua một interface con

Quy tắc “khởi tạo lớp/interface khai báo field” cũng áp dụng với interfaces, nhưng **interface initialization** không giống class inheritance: initialization của subinterface **không tự động** làm tất cả superinterfaces initialize.

Xét chương trình Java 17+ độc lập **InterfaceFieldDemo.java**:

~~~java
public class InterfaceFieldDemo {
    interface Root {
        int CONST = 11;
        int RUNTIME = initRoot();

        static int initRoot() {
            System.out.println("Root:init");
            return 21;
        }
    }

    interface Branch extends Root {
        int OWN = initBranch();

        static int initBranch() {
            System.out.println("Branch:init");
            return 31;
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("constant=" + Branch.CONST);
        System.out.println("own=" + Branch.OWN);
        System.out.println("inherited=" + Branch.RUNTIME);
        System.out.println("end");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 InterfaceFieldDemo.java
java InterfaceFieldDemo
~~~

**Stdout:**

~~~text
begin
constant=11
Branch:init
own=31
Root:init
inherited=21
end
~~~

Tại sao không in **Root:init** trước **Branch:init**?

- **Root.CONST** là constant variable (interface fields được khai báo ngầm là public static final). Đọc **Branch.CONST** không init Root.
- **Branch.OWN** là field khai báo trong Branch và được tính bởi static method **initBranch()**, không phải constant variable. Đọc nó init Branch.
- **Khởi tạo một interface không tự động khởi tạo superinterfaces**; vì vậy Root chưa cần init vào thời điểm Branch.OWN được đọc.
- **Branch.RUNTIME** tham chiếu field thực sự khai báo trong Root; field không constant → init Root lúc đó.
- Không có nguyên tắc “interface con luôn init interface cha trước” giống superclass initialization của một class.

Đây là ví dụ rõ cho quy tắc **declaring interface** và sự khác biệt giữa kế thừa **class** với kế thừa **interface**.

## 12. Static method cũng xét nơi thực sự khai báo

Quy tắc active use còn liên quan đến static methods. Ví dụ:

~~~java
class Base {
    static void ping() {
        System.out.println("ping");
    }
}

class Derived extends Base {
    static {
        System.out.println("Derived:init");
    }
}
~~~

Nếu một method client viết **Derived.ping()**, Java giải quyết invocation theo declaration thực sự của method (ở đây **Base.ping**). Thao tác static invocation yêu cầu init **Base**, không chỉ vì dùng tên Derived mà làm **Derived** init.

**Tuy nhiên static methods không override đa hình:** Chúng có thể bị hide bởi static method cùng signature trong subclass; khi đó **Derived.ping()** có thể thực sự tham chiếu method khai báo trong Derived và kéo theo initialization của Derived.

Phân biệt các trường hợp:

| Biểu thức | Thành viên thực sự được chọn | Initialization liên quan |
| --- | --- | --- |
| **Derived.inherited** | Static field khai báo trong Base | Base nếu nonconstant |
| **Derived.CONSTANT** | Constant variable khai báo trong Base | Không active use chỉ bởi đọc hằng |
| **Derived.own** | Static field khai báo trong Derived | Derived, rồi superclass nếu cần |
| **Derived.ping()** nếu ping chỉ ở Base | Static method khai báo trong Base | Base |
| **Derived.ping()** nếu Derived khai báo method ẩn Base.ping | Method khai báo trong Derived | Derived |

Khi method hoặc field bị hide, cần xem compiler đã bind tên đến declaration nào. Không thể kết luận bằng cách nhìn identifier đơn lẻ.

## 13. Dùng javap để chứng minh thay vì chỉ đoán từ source

Sau khi tạo hai ví dụ trên, dùng:

~~~bash
javap -c -p ConstantVsInitialization
javap -c -p InheritedStaticDemo
javap -v -p 'InheritedStaticDemo$Parent'
javap -v -p 'InheritedStaticDemo$Child'
~~~

**javap -c** in bytecode, **javap -v** cho constant pool, method descriptors và attributes. Tên nested class có ký tự **$**; nên quote thích hợp trong shell có variable expansion.

### 13.1. Hằng được nạp như thế nào?

Khi in **Child.LIMIT**, compiler có thể sử dụng integer literal trực tiếp, như:

~~~text
iconst_3
~~~

hoặc đưa hằng đã gộp vào một phép nối chuỗi phù hợp. Với chương trình có lời gọi **println("constant=" + Child.LIMIT)**, compiler Java 17 có thể fold cả phần concatenation thành một literal **"constant=3"**. Điều đáng quan sát là việc **không cần getstatic Parent.LIMIT** để lấy giá trị runtime trong client được biên dịch theo JLS.

**Không ép compiler phải sinh một opcode cụ thể**, vì với cùng ngữ nghĩa có thể có tối ưu hằng, **invokedynamic** cho string concatenation và cách khác theo phiên bản.

### 13.2. Field khai báo ở Parent sẽ có owner nào?

Trong bytecode của **InheritedStaticDemo**, thao tác đọc **Child.count** thường chứa symbolic reference đến:

~~~text
getstatic InheritedStaticDemo$Parent.count:I
~~~

không phải **InheritedStaticDemo$Child.count:I**. Compiler xác định field declaration thực là Parent. Bạn có thể dùng **javap -c -p** để xem owner và **getstatic**.

Khi đọc **Child.own**, reference sẽ trỏ tới **InheritedStaticDemo$Child.own:I**; active use của field này khiến Child init.

### 13.3. Class literal thường sử dụng ldc Class

Với **Target.class**, bytecode thường có lệnh kiểu:

~~~text
ldc   #n      // class ConstantVsInitialization$Target
~~~

Đây là cách lấy **Class object**, không phải **invokestatic Target.method** hay **new Target**. Compiler có thể tối ưu tổ chức locals, nhưng semantics class literal không yêu cầu static initialization của Target.

### 13.4. Vì sao không thể dựa toàn bộ vào stdout?

Lớp có thể được **load, verify, prepare** trước khi stdout hiển thị static initializer. Bytecode còn có thể bị JVM resolve tham chiếu theo chiến lược sớm hoặc muộn. Từ **không thấy log "Target:<clinit>"** chỉ nên kết luận **đoạn code log đó chưa chạy**, không phải mọi trạng thái loading/linking đều chưa xảy ra.

## 14. Class literal của lớp cha hoặc lớp con: ví dụ đối chiếu

Tạo **ClassLiteralDemo.java**:

~~~java
public class ClassLiteralDemo {
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

    public static void main(String[] args) throws Exception {
        System.out.println("begin");

        System.out.println("name=" + Child.class.getSimpleName());
        System.out.println("parent=" + Child.class.getSuperclass().getSimpleName());
        System.out.println("after-literals");

        Class.forName("ClassLiteralDemo$Child", true,
                ClassLiteralDemo.class.getClassLoader());
        System.out.println("after-forName");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 ClassLiteralDemo.java
java ClassLiteralDemo
~~~

**Stdout:**

~~~text
begin
name=Child
parent=Parent
after-literals
Parent initialized
Child initialized
after-forName
~~~

**getSuperclass()** nhận metadata về Parent nhưng không cần chạy Parent static initializer chỉ từ thao tác hỏi superclass. **Class.forName(...,true,loader)** sau đó là active request khởi tạo Child, kéo theo khởi tạo Parent trước Child theo quy tắc class hierarchy.

Điểm đáng chú ý: **Child.class** không init Child; **Child.class.getSuperclass()** không khiến Parent init; nhưng **forName(true)** của Child cần hai lớp trong thứ tự Parent → Child khi chưa khởi tạo.

### 14.1. Lớp con static nested có phụ thuộc khởi tạo lớp ngoài không?

~~~java
class Outer {
    static { System.out.println("Outer initialized"); }

    static class Nested {
        static { System.out.println("Nested initialized"); }
    }
}
~~~

**Outer.Nested.class** không init Nested; active use **new Outer.Nested()** init Nested theo quy tắc riêng của runtime class này. Static nested class **không tự init Outer** chỉ vì về mặt source được khai báo bên trong Outer. Quan hệ tên lồng nhau khác với quan hệ superclass.

## 15. Compile-time inlining và binary compatibility

Xét quá trình build ứng dụng:

~~~text
Lần build 1:
  LibraryConfig.LIMIT = 5
  javac LibraryConfig.java Client.java
  Client.class có thể chứa literal 5

Lần deploy 2:
  Chỉ thay LibraryConfig.class (LIMIT = 7)
  Không biên dịch lại Client.class

Runtime:
  Client.class cũ vẫn có thể in 5
~~~

Các bước này mô tả một tình huống build/deploy, không phải script terminal tự chạy được. Khi class file của client đã lưu giá trị hằng được thay thế ở compile time, runtime **không cần hỏi LibraryConfig.LIMIT**.

### 15.1. Ví dụ hai phiên bản lớp thư viện

Phiên bản 1, tệp **LibraryConfig.java**:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 5;
}
~~~

Tệp client:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("limit=" + LibraryConfig.LIMIT);
    }
}
~~~

Biên dịch cả hai bằng Java 17:

~~~bash
javac --release 17 -encoding UTF-8 LibraryConfig.java Client.java
java Client
~~~

**Stdout phiên bản đầu:**

~~~text
limit=5
~~~

Sau đó thay **LibraryConfig.java** bằng:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 7;
}
~~~

**Chỉ biên dịch lại thư viện**, không biên dịch Client:

~~~bash
javac --release 17 -encoding UTF-8 LibraryConfig.java
java Client
~~~

**Stdout có thể vẫn là:**

~~~text
limit=5
~~~

Cuối cùng biên dịch lại Client với bản mới:

~~~bash
javac --release 17 -encoding UTF-8 Client.java
java Client
~~~

**Stdout sau khi biên dịch lại client:**

~~~text
limit=7
~~~

Các bước chạy giả định thực hiện trong cùng thư mục chứa đúng các tệp và không có một **LibraryConfig.class** khác đứng trước trên classpath. Đây là ví dụ điển hình tại sao public compile-time constants thay đổi có thể gây bất ngờ dù library JAR đã được thay.

### 15.2. Thay hằng bằng method có giải quyết hết không?

Một method như **LibraryConfig.limit()** được gọi tại runtime có thể tránh việc client nhúng hằng giá trị, nhưng phải cân nhắc:

- Thay field bằng method là **thay đổi binary API**: client cũ đang truy cập field có thể không tương thích và cần build lại.
- Runtime method vẫn có vấn đề versioning, class loader identity và config caching riêng.
- Nếu giá trị được đọc từ config, cần định nghĩa khi nào reload, validation và error handling.
- Với constant mang ý nghĩa cố định của protocol, việc inlining có thể là đặc tính được mong muốn.

Giải pháp hợp lý phụ thuộc vào **hợp đồng thay đổi giá trị** chứ không đơn thuần một quy tắc “luôn dùng method”.

## 16. Hằng ở interface và việc kế thừa

Interface fields mặc định là **public static final**, nhưng initializer có thể là runtime expression; vì thế không phải field nào trong interface cũng là constant variable.

~~~java
interface Options {
    int PORT = 8080;                    // constant variable
    int REAL_PORT = readPort();          // không phải constant variable

    static int readPort() {
        return 9090;
    }
}
~~~

Đọc **Options.PORT** không init Options chỉ bởi thao tác ấy. Đọc **Options.REAL_PORT** yêu cầu initialization Options nếu chưa.

Khi interface con kế thừa field:

~~~java
interface ParentInterface {
    int LIMIT = 10;
    int DYNAMIC = calculate();

    static int calculate() { return 20; }
}

interface ChildInterface extends ParentInterface {
    int OWN = 30;
}
~~~

**ChildInterface.LIMIT** và **ChildInterface.DYNAMIC** đều đề cập declarations thực trong ParentInterface. LIMIT là constant variable; DYNAMIC không constant nên khi đọc sẽ init ParentInterface, **không bắt buộc init ChildInterface** chỉ vì cú pháp dùng ChildInterface.

Ngược lại, đọc nonconstant field do ChildInterface tự khai báo sẽ init ChildInterface; interface initialization không tự kéo theo mọi superinterface như superclass initialization của class.

## 17. Một số tình huống nâng cao dễ nhầm

### 17.1. Field hiding khiến declaring type thay đổi

~~~java
class Parent {
    static final int CODE = 1;
}

class Child extends Parent {
    static final int CODE = 2;
}
~~~

**Child.CODE** tham chiếu **Child.CODE**, không phải Parent.CODE. Cả hai vẫn là constant variables nên source reads không tự init lớp tương ứng.

Nếu đổi **Child.CODE** thành **static int CODE = 2;**, đọc **Child.CODE** là active use của Child, kéo theo superclass initialization nếu cần. **Tên field giống nhau** không quyết định; **declaration và constant-variable status** mới quyết định.

### 17.2. Static field access qua expression có side effect

Trong Java, static field có thể được truy cập bằng một expression là tên tham chiếu:

~~~java
// Mã minh họa, giả định Base.number là static int:
Base ref = null;
int value = ref.number;
~~~

Dù ref là null, thao tác đọc **static field** không tự dereference ref như instance field nên không ném NullPointerException chỉ vì ref null. Truy cập static field vẫn xét declaring class, không dựa vào giá trị object reference.

Khi qualifier là một **expression có side effect**, Java có thể phải đánh giá expression theo quy tắc ngôn ngữ rồi bỏ giá trị đi trước khi thao tác field. Vì vậy để phân tích **mọi stdout và exceptions**, phải xét cả expression qualifier, không chỉ initialization của declaring class.

**Khuyến nghị:** Luôn viết **Base.number** thay vì **ref.number** với static field để tránh gây hiểu lầm.

### 17.3. Class literal và reflection không hoàn toàn tương đương

**T.class** không init T. Nhưng các reflection operations như **Field.get(null)**, **Field.set(null, value)** cho static field có thể yêu cầu initializing declaring class theo API. Do đó:

~~~java
// Minh họa trong method có throws Exception:
Class<?> type = T.class;                  // không yêu cầu init T
var field = type.getDeclaredField("X");   // xem metadata
Object value = field.get(null);           // có thể init declaring class
~~~

Code trên không độc lập vì **T** phải được khai báo và **X** phải tồn tại, accessible. Việc gọi getDeclaredField/getDeclaredFields có thể liên quan loading/linking metadata; không được suy thành một blanket promise “reflection không init”.

### 17.4. Đọc constant variable trong chính class khai báo

Nếu class có:

~~~java
static final int CONSTANT = 8;
static int VALUE = CONSTANT * 2;
~~~

**VALUE** được khởi tạo trong quá trình initialization, còn compiler có thể dùng constant expression **16** cho initializer. Điều này không có nghĩa class không bao giờ init: đọc **VALUE** từ bên ngoài vẫn là nonconstant static field access và yêu cầu class initialization.

Nếu class chỉ khai báo compile-time constants, compiler có thể không tạo một **<clinit>** chứa instructions. Dù vậy Java vẫn xác định lifecycle class; không có <clinit> output không cho phép kết luận “kiểu này hoàn toàn không có bước initialization trong mô hình JVM”.

### 17.5. Class loaders và hai runtime copies

Hai class loaders khác nhau có thể define hai classes cùng binary name. Mỗi class runtime có trạng thái initialization riêng và static fields riêng. Một client đã nhúng compile-time constant thậm chí không cần load class nơi field ban đầu được khai báo trong quá trình đọc hằng.

Ngược lại, khi dùng class literal hoặc forName qua loader khác, bạn có thể nhận **Class object khác**, dù tên giống nhau. Đây là lý do cần xác định **(binary name, defining loader)** khi điều tra sự cố class initialization trong plugin/application server.

## 18. Lỗi thường gặp và hướng sửa

| Nhận định sai | Vì sao sai | Cách kiểm tra |
| --- | --- | --- |
| “Tất cả static final đều không init class.” | Wrapper, new String, method calls... không là constant variables | Kiểm tra JLS 4.12.4 và initializer |
| “Chỉ cần source viết Child.X thì Child init.” | X có thể do Parent khai báo | Tìm declaring field; xem owner của getstatic trong javap |
| “Lấy Child.class sẽ in static block.” | Class literal không phải active use | Test static block và class literal |
| “Class.forName luôn chỉ load.” | forName(name) yêu cầu init; overload false không | Chọn overload đúng |
| “String constant có + thì không là hằng.” | Nối các compile-time string constants vẫn có thể là constant expression | Xem constant-expression grammar |
| “Client tự đọc giá trị constant mới khi đổi JAR.” | Giá trị có thể đã nhúng trong Client.class | Rebuild/recompile client; xem javap -c |
| “Có Class object chứng minh <clinit> đã chạy.” | Loading/linking khác initialization | Quan sát side effects của initializer và active use |
| “Static final Integer giống static final int.” | Integer là reference wrapper, không là constant variable | Xác định kiểu khai báo |
| “Truy cập Child.parentField gây cả Parent và Child init.” | Chỉ declaring field bị active use, nếu nonconstant | Quan sát hai static initializers độc lập |
| “Mọi reflection access đều không init.” | Field.get và một số operations có yêu cầu init | Đọc contract API tương ứng |
| “Tạo new T[10] làm T init.” | Array creation khác tạo T instance | Phân biệt anewarray với new |
| “Source chỉ có một class nên chỉ có một lifecycle.” | Nested/static member classes có runtime class riêng | Javap từng class, quan sát init riêng |

## 19. Quy trình dự đoán stdout cho một chương trình

Khi gặp câu hỏi có **static blocks, constants, class literals, Parent/Child**, đừng đoán bằng trực giác. Hãy thực hiện:

1. **Lập danh sách runtime classes** và cấu trúc kế thừa/interface; phân biệt nested class và superclass.
2. **Ghi nơi khai báo thật** của từng field/method được dùng, không suy theo tên qualifier đứng trước dấu chấm.
3. **Phân loại static fields:** constant variable nếu final + primitive/String + constant expression, hoặc runtime field nếu không.
4. **Đánh dấu tác vụ active use**: new instance, static method invocation, nonconstant static field read/write, reflective initialization; bỏ qua class literal hoặc constant read nếu chỉ có chúng.
5. **Khi class T init lần đầu**, thêm superclass initialization và các superinterfaces thích hợp theo quy tắc, rồi chạy static initializers của T theo thứ tự văn bản; class đã init thành công không chạy lại.
6. **Với interface**, nhớ initialization của interface không tự init tất cả superinterfaces.
7. **Đọc side effects** của những initializer thực sự được gọi, ghi stdout theo thứ tự.
8. **Xem class literal/forName(false)** như những thao tác có thể load/link nhưng chưa yêu cầu init.
9. **Đối chiếu javap**: constants xuất hiện dưới dạng literal, runtime static fields dùng getstatic với owner declaration; string concatenation có thể bị compiler fold.
10. **Nếu có nhiều class loaders**, tách trạng thái của từng runtime class theo defining loader trước khi lập timeline.

Bảng tự luyện:

| Bước | Biểu thức source | Declaring type | Constant variable? | Class nào phải init? | Output/side effect |
| --- | --- | --- | --- | --- | --- |
| 1 | **Child.CONST** | Parent | Có | Không do thao tác này | In hằng |
| 2 | **Child.runtimeValue** | Parent | Không | Parent | Parent static initializer |
| 3 | **Child.class** | Không phải field | Không áp dụng | Không do class literal | Nhận Class object |
| 4 | **Child.ownRuntime** | Child | Không | Child (và superclass chưa init nếu cần) | Child static initializer |

## 20. Bài tập tự kiểm tra

**Bài 1.** Field nào là constant variable?

~~~java
static final int A = 3 * 7;
static final Integer B = 21;
static final String C = "ja" + "va";
static final int D = Math.max(20, 21);
~~~

**Đáp án:** **A** và **C**. B có kiểu Integer; D có method call.

**Bài 2.** Đoạn sau có in **"init"** khi chỉ thực hiện dòng client không?

~~~java
class Settings {
    static final int PORT = 8080;
    static { System.out.println("init"); }
}
int p = Settings.PORT;
~~~

**Đáp án:** Không do thao tác đọc constant variable; compiler có thể dùng trực tiếp literal 8080. Phải đặt dòng client vào một phương thức hợp lệ để chạy chương trình.

**Bài 3.** Class literal của lớp có static block có init nó ngay không?

~~~java
Class<?> c = Settings.class;
~~~

**Đáp án:** Không. Class literal tạo/lấy Class object, không phải active use khởi tạo Settings.

**Bài 4.** Hai phương thức forName có tác dụng initialization giống nhau không?

~~~java
Class.forName("pkg.Settings");
Class.forName("pkg.Settings", false, loader);
~~~

**Đáp án:** Không. Overload một tham số yêu cầu initialization; overload **false** không yêu cầu. Ví dụ chỉ minh họa, cần lớp và loader hợp lệ.

**Bài 5.** Nếu **Parent.value** là nonconstant static field, còn **Child extends Parent** không khai báo value, đọc **Child.value** làm class nào init?

**Đáp án:** Parent; Child không init chỉ vì được dùng làm qualifier.

**Bài 6.** Nếu Child **khai báo** một field value mới có cùng tên với Parent.value, đọc **Child.value** thì sao?

**Đáp án:** Field được chọn là Child.value; nếu nonconstant, Child phải initialize (và superclass Parent được initialize trước nếu cần).

**Bài 7.** Interface Root khai báo **int C = 1** và **int R = compute()**, Branch extends Root. Đọc **Branch.C** và **Branch.R** có gì khác?

**Đáp án:** C là constant variable nên đọc không init Root; R là runtime field nên đọc gây init Root. Branch không tự init chỉ vì qualifier.

**Bài 8.** Thư viện thay **public static final String VERSION = "v1"** thành **"v2"**, nhưng client cũ vẫn in v1. Vì sao?

**Đáp án:** VERSION là constant variable, client có thể chứa hằng đã nhúng lúc biên dịch. Biên dịch lại client với thư viện mới; nếu cần runtime-configurable value, thiết kế API khác.

**Bài 9.** **static final String NAME = new String("A")** có phải compile-time constant không?

**Đáp án:** Không. Có **new**, không phải constant expression; đọc static field NAME yêu cầu init class.

**Bài 10.** Một chương trình chỉ làm **new Widget[3]** và chưa từng dùng Widget. Static block trong Widget có chạy bắt buộc không?

**Đáp án:** Không. Tạo array không tạo Widget instance, không phải active use khởi tạo Widget.

**Bài 11.** **Field.get(null)** đối với static final int constant có thể làm class khai báo init, dù đọc trực tiếp bằng Java source không làm không?

**Đáp án:** Có. Reflection Field.get với static field có hợp đồng riêng về initialization; không áp dụng quy tắc compiler inlining cho lời gọi reflection.

**Bài 12.** Vì sao **javap** có thể không có **getstatic Parent.LIMIT** cho dòng source **Child.LIMIT**?

**Đáp án:** LIMIT là constant variable, giá trị được giải quyết ở compile time và được sử dụng trực tiếp trong client bytecode. Child là qualifier source, không phải declaring type và không cần init để đọc hằng.

**Bài 13.** Đặt **Class.forName("ClassLiteralDemo$Child", true, loader)** sau một **Child.class.getName()** trong một JVM mới: lớp nào init trước nếu chưa init và Child extends Parent?

**Đáp án:** Lớp Parent được init trước Child khi JVM init Child; class literal/getName không buộc init cả hai trước lời gọi forName(true).

## 21. Checklist khi viết code và khi làm phỏng vấn JVM

- Trước tiên xác định **compile-time constant** hay **runtime static field**.
- Định nghĩa đúng: **final + primitive/String + constant expression**, không mặc định mọi **static final** là hằng biên dịch.
- Với **T.class**, không suy ra static code đã chạy; với **Class.forName**, đọc **đúng overload** và tham số initialize.
- Khi source ghi **Child.X**, tìm **lớp/interface thực sự khai báo X**; không tự cho Child initialize.
- Với field bị hide, xác định declaration được compiler chọn theo kiểu của expression.
- Với **subinterface**, nhớ init interface không tự init superinterfaces.
- Với client build lâu đời, nghi ngờ **inlined public constants** nếu runtime thấy giá trị cũ.
- Khi dùng Reflection, không áp dụng máy móc quy tắc constant read trong Java source; đọc API contract.
- Nếu cần giải thích chính xác, biên dịch và đọc **javap -c/-v**, quan sát hằng, **getstatic owner** và Class literal.
- Dùng static initializer có side effect một cách thận trọng: chúng chỉ chạy khi có initialization request và có thể ném lỗi khiến class ở trạng thái erroneous.
- Khi debugging với plugin, luôn xét **defining class loader**, vì cùng tên lớp có thể là hai runtime classes.
- Tránh phụ thuộc vào thời điểm loading/linking chi tiết mà JVM được phép quyết định linh hoạt.

### Tài liệu chuẩn

- **JLS Java SE 17, §4.12.4 — final Variables / Constant Variables:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4
- **JLS Java SE 17, §15.29 — Constant Expressions:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29
- **JLS Java SE 17, §12.4.1 — When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- **JLS Java SE 17, §12.4.2 — Detailed Initialization Procedure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- **JLS Java SE 17, §13.4.9 — final Fields and Constants / Binary Compatibility:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.4.9
- **JVMS Java SE 17, §5.5 — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JVMS Java SE 17, §4.7.2 — ConstantValue Attribute:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2
- **Java SE 17 API — Class.forName:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 API — java.lang.reflect.Field:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html

**Ghi nhớ:** **Constant variable** cho phép client dùng hằng compile time mà không buộc lớp khai báo init; **class literal** trả Class object nhưng không tự chạy **<clinit>**; **Child.field** phải được giải quyết về **declaring class/interface thực sự** rồi mới áp dụng quy tắc active use. Khi phân tích initializer, câu hỏi chính xác không phải “source có nhắc tới tên lớp nào?”, mà là **“thao tác runtime nào xảy ra, field/method khai báo ở đâu, và đó có phải constant variable không?”**.
