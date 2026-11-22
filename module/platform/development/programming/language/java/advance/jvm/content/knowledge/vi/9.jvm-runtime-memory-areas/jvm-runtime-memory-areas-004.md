# Method area và run-time constant pool trong mô hình trừu tượng JVM

## 1. Mục tiêu bài học

Trong Java Virtual Machine Specification (JVMS), **method area** và **run-time constant pool** là những thành phần của **run-time data areas**. Method area là vùng logic chia sẻ giữa các thread, phục vụ cấu trúc dữ liệu cấp lớp. Run-time constant pool là một phần của method area theo mô hình đặc tả: **mỗi runtime class/interface có một pool riêng**, tạo từ constant pool trong tệp class, chứa hằng và tham chiếu biểu tượng cần cho thực thi/liên kết.

Điểm quan trọng: đây là **mô hình trừu tượng**, không phải cam kết rằng mọi JVM phải lưu metadata tại cùng một địa chỉ, cùng một vùng heap vật lý hoặc cùng công nghệ cấp phát. Với HotSpot Java 17, nhiều loại class metadata được quản lý trong **Metaspace**; Metaspace là **chi tiết implementation**, không phải tên thay thế được đặc tả bắt buộc cho toàn bộ method area.

Học xong, bạn có thể:

- Phân biệt method area với heap, JVM stack, PC và native method stack.
- Kể các dữ liệu cấp class tiêu biểu nằm trong method area theo JVMS, cùng ý nghĩa chia sẻ giữa threads.
- Phân biệt **class-file constant pool**, **run-time constant pool**, **String intern pool**, **static field state** và **String objects**.
- Đọc các tag thường gặp trong class-file constant pool: Utf8, Class, String, Integer, Methodref, Fieldref, NameAndType, MethodHandle, MethodType, Dynamic và InvokeDynamic.
- Giải thích vai trò của constant-pool indexes trong **ldc**, **getstatic**, **invokevirtual**, **invokestatic** và cơ chế **resolution**.
- Phân biệt loading, linking, initialization; không nhầm việc resolve Class với chạy static initializer.
- Hiểu mối liên hệ của class loader, một runtime class và pool riêng; tại sao cùng tên class nhưng khác defining loader có thể tạo các pools khác nhau.
- Quan sát bằng Java 17+, javap và những công cụ HotSpot khi cần, đồng thời tránh suy diễn memory layout từ bytecode.

## 2. Bản đồ các vùng dữ liệu JVM

Theo JVMS §2.5, các vùng có phạm vi khác nhau:

~~~text
                        JVM đang thực thi
+----------------------------------------------------------------+
| Các vùng logic dùng chung giữa threads                         |
|                                                                |
|  HEAP                             METHOD AREA                  |
|  +--------------------------+    +--------------------------+  |
|  | Instances                |    | Cấu trúc cấp class       |  |
|  | Arrays                   |    | Thông tin fields/methods |  |
|  | String objects           |    | Code methods/ctors       |  |
|  | ...                      |    | Runtime pool của class A |  |
|  +--------------------------+    | Runtime pool của class B |  |
|                                  +--------------------------+  |
|                                                                |
| Mỗi thread:                                                    |
|  +-----------------------+  +-----------------------+          |
|  | PC register           |  | PC register           |          |
|  | JVM stack             |  | JVM stack             |          |
|  |   frame: locals       |  |   frame: locals       |          |
|  |   frame: operand stack|  |   frame: operand stack|          |
|  | native stack nếu dùng |  | native stack nếu dùng |          |
|  +-----------------------+  +-----------------------+          |
+----------------------------------------------------------------+
~~~

**Sơ đồ logic, không phải ảnh chụp RAM.** JVM được phép tổ chức nhiều thành phần bằng các cấu trúc nội bộ khác nhau miễn tuân thủ ngữ nghĩa chuẩn.

| Vùng | Thuộc phạm vi | Mục đích |
| --- | --- | --- |
| **Heap** | Dùng chung | Nơi tạo class instances và arrays theo mô hình JVM |
| **Method area** | Dùng chung | Cấu trúc cấp lớp, run-time constant pools, method/field data và code |
| **Run-time constant pool** | Một pool logic cho mỗi runtime class/interface | Constants và symbolic references phục vụ thực thi/linking |
| **PC register** | Riêng mỗi thread | Vị trí instruction JVM hiện hành theo quy tắc của VM |
| **JVM stack** | Riêng mỗi thread | Frames của các lời gọi method; mỗi frame có locals, operand stack |
| **Native method stack** | Theo thread nếu implementation cần | Thực thi native code |

Một **method call** tạo frame riêng; frame **không tự chứa bản sao toàn bộ metadata của class**. Method code/metadata có thể được các threads cùng sử dụng, nhưng locals và operand stack của từng lời gọi là trạng thái riêng.

### 2.1. Frame có tham chiếu tới runtime pool

JVMS §2.6.3 về dynamic linking quy định mỗi frame chứa tham chiếu tới **run-time constant pool của class chứa method đang được thực thi**. Khi method ở class A gọi method của class B, instruction trong A có thể dùng pool entry của A để resolve tới B. Khi phương thức B chạy, frame mới dùng pool của **B**.

~~~text
Class A runtime pool
  #n: symbolic Methodref B.work:()V
       |
       v
Frame đang chạy A.execute()
  - locals
  - operand stack
  - reference -> A runtime pool
       |
       v
invoke B.work
       |
       v
Frame mới của B.work()
  - locals
  - operand stack
  - reference -> B runtime pool
~~~

**Không được nhầm pool owner với method owner**: entry trong caller A mô tả B.work có thể nằm ở pool của A, không phải do đó được lưu trong pool của B.

## 3. Method area theo đặc tả

JVMS §2.5.4 mô tả method area:

- Tồn tại ở cấp JVM và **dùng chung giữa tất cả JVM threads**.
- Được tạo khi JVM khởi động.
- Lưu **per-class structures**, như runtime constant pool, field/method data và code methods/constructors; có cả code dùng cho class/interface initialization và instance initialization.
- **Logically part of heap**, nhưng **đặc tả không bắt buộc vị trí vật lý hay chính sách thu gom/compact cụ thể**.
- Có thể cố định kích thước hoặc mở rộng khi cần, tùy implementation.
- Nếu không cấp phát đủ vùng cần thiết, JVM có thể ném **OutOfMemoryError**.

### 3.1. Per-class metadata không phải object instance

Ví dụ:

~~~java
class Customer {
    private int id;
    static int created;

    Customer(int id) {
        this.id = id;
        created++;
    }
}
~~~

Theo ý nghĩa logic:

- **Thông tin của class Customer**: tên, fields/methods, descriptors, code constructor và những cấu trúc liên quan thuộc per-class metadata.
- **Một instance Customer**: object có instance field **id** theo mô hình heap.
- **Static field created**: trạng thái cấp runtime class; metadata mô tả field khác với giá trị hiện tại có thể thay đổi.
- **Frame khi chạy constructor Customer(int)**: locals/operand stack thuộc JVM stack của thread đang gọi.

Không thể kết luận từ bảng khái niệm này rằng byte của static field chắc chắn nằm đúng một offset trong method area trên mọi JVM; **bố trí storage vật lý là chi tiết VM**.

### 3.2. “Logically part of heap” cần đọc chính xác

Câu của JVMS là mô tả trừu tượng, không có nghĩa:

- **-Xmx** tự động kiểm soát toàn bộ class metadata của HotSpot.
- Object heap và method area phải là một vùng native memory liên tục.
- PermGen là tên chuẩn của JVM method area.
- Một heap dump luôn thể hiện nguyên trạng run-time pool như văn bản trong javap.
- JVM bắt buộc GC method area giống Java object heap.

Trong HotSpot Java 17, metadata thường thuộc các cơ chế Metaspace/native memory; nhiều String objects vẫn được cấp phát trên managed heap. Không gắn mọi thành phần JVM abstraction với một vùng cấp phát duy nhất do JVM implementation có thể thay đổi.

## 4. Run-time constant pool theo đặc tả

JVMS §2.5.5: **mỗi runtime class hoặc interface có run-time constant pool** được tạo khi lớp đó được tạo trong quá trình loading. Pool là representation lúc chạy của **constant_pool** trong class file, chứa cả những hằng số đã biết lúc biên dịch lẫn các tham chiếu tượng trưng được resolve khi cần.

Nhìn hai tầng:

~~~text
Trước runtime:
  Example.class
    constant_pool_count
    constant_pool[]:
      #1 Utf8       "demo/Example"
      #2 Class      -> #1
      #3 Utf8       "value"
      #4 Utf8       "I"
      #5 NameAndType -> #3,#4
      #6 Fieldref   -> Class+NameAndType
      ...

Khi tạo runtime class:
  ("demo.Example", defining loader)
    -> per-class metadata
    -> run-time constant pool
       - symbolic references
       - literal constants / loadable constants
       - trạng thái liên kết thích hợp
    -> methods/fields/code và các cấu trúc cần thiết
~~~

Các chỉ số ví dụ ở trên **không đại diện cho class file thật**. Đặc tả mô tả nghĩa của các entry, không quy định JVM phải clone nguyên mảng cp_info vào RAM rồi thay từng string bằng pointer.

### 4.1. Pool không chỉ lưu số và String literal

| Entry thường gặp | Dữ liệu/vai trò |
| --- | --- |
| **CONSTANT_Utf8** | Chuỗi ký tự metadata: tên class, field/method, descriptors... |
| **CONSTANT_Integer / Float / Long / Double** | Numeric constants |
| **CONSTANT_Class** | Tham chiếu tượng trưng tới class/interface hoặc array class |
| **CONSTANT_String** | String constant mô tả qua Utf8 reference |
| **CONSTANT_Fieldref** | Symbolic field reference |
| **CONSTANT_Methodref** | Symbolic method reference |
| **CONSTANT_InterfaceMethodref** | Symbolic interface-method reference |
| **CONSTANT_NameAndType** | Tên member cùng descriptor |
| **CONSTANT_MethodHandle** | Method-handle constant, reference kind và target |
| **CONSTANT_MethodType** | Method type constant |
| **CONSTANT_Dynamic** | Dynamically-computed constant theo bootstrap resolution |
| **CONSTANT_InvokeDynamic** | Dynamically-computed call site |
| **CONSTANT_Module / Package** | Dữ liệu module/package theo ngữ cảnh class file |

**CONSTANT_Utf8 không đồng nghĩa một String object đã được tạo cho mỗi entry.** Nó là dữ liệu biểu diễn text trong class-file constant pool. Với String literal, pool metadata có thể dẫn đến String reference trong runtime theo ngữ nghĩa intern/literal, nhưng metadata và object là hai thực thể có vai trò khác nhau.

### 4.2. Giới hạn của class-file pool

Tệp class dùng:

~~~text
u2 constant_pool_count;
cp_info constant_pool[constant_pool_count - 1];
~~~

Vì vậy giá trị lớn nhất có thể biểu diễn cho **constant_pool_count** là **65.535**; các vị trí entry thường có index **1 đến count-1**. Chỉ số **0 không phải entry thông thường**. **CONSTANT_Long/Double** chiếm hai index slots trong việc đánh số, dù là một cp_info entry được mã hóa.

**CONSTANT_Utf8** dùng u2 length, tối đa **65.535 byte Modified UTF-8**. Đây là giới hạn **số byte đã mã hóa**, không phải 65.535 Unicode code points hay số ký tự Java.

Không suy:

- JVM chỉ có một constant pool 65.535 slots cho tất cả classes.
- JVM chỉ có thể nạp 65.535 classes.
- Một class-file constant pool nhỏ chắc chắn nghĩa là ứng dụng không thể bị Metaspace OOME.
- Một String object ở runtime chỉ dài tối đa 65.535 byte.
- Toàn bộ runtime pool có kích thước cố định bằng số entries nhân một số byte cứng.

Giới hạn định dạng **một class file** là vấn đề khác với giới hạn **tài nguyên bộ nhớ của tiến trình**.

## 5. Phân biệt bốn kiểu “pool” và storage thường bị trộn lẫn

| Khái niệm | Nó là gì? | Sai lầm phổ biến |
| --- | --- | --- |
| **Class-file constant pool** | Dữ liệu nhị phân cp_info trong .class | Coi đây là object array Java đang chạy |
| **Run-time constant pool** | Pool logic thuộc runtime class/interface trong method area | Coi toàn JVM chỉ có một pool chung |
| **String intern pool** | Canonical String identity qua literals và String.intern() | Coi đây là toàn bộ CONSTANT_Utf8/Methodref/Class entries |
| **Static field storage** | Trạng thái cấp lớp của static fields | Coi mọi giá trị static là constant-pool entries |

Ngoài ra **JIT code cache** phục vụ compiled native machine code trong HotSpot; nó không đồng nghĩa class-file bytecode hoặc run-time constant pool.

### 5.1. “String literal nằm trong constant pool” nghĩa chính xác là gì?

Một string literal như **"hello"** có representation phù hợp trong class file constant pool. Khi instruction cần giá trị, JVM cung cấp một **reference tới String instance** theo ngữ nghĩa của ngôn ngữ Java và String intern mechanism.

Do đó cần phân biệt ba thứ:

1. **Metadata** mô tả literal trong class file/runtime pool.
2. **String object** được Java code quan sát.
3. **Reference** tới String object nằm trên operand stack/local variable hoặc một field.

Nếu dùng **ldc** nạp String reference, đừng kết luận String object bắt buộc nằm trong method area chỉ vì ldc sử dụng runtime constant pool.

## 6. Resolution: từ symbolic reference tới entity runtime

Giả sử mã Java:

~~~java
// Minh họa trong một method:
int length = text.length();
~~~

Caller class có thể chứa symbolic method reference:

~~~text
Owner internal name: java/lang/String
Method name:          length
Method descriptor:    ()I
Kind:                 Methodref
~~~

Bytecode tương ứng có thể là:

~~~text
aload <slot>
invokevirtual #n    // Method java/lang/String.length:()I
istore <slot>
~~~

**#n** là index vào constant pool của **class chứa instruction**. Khi reference được resolve, JVM xác định class/method phù hợp, kiểm tra loại reference, access rules, class loaders và những constraints bắt buộc.

Việc resolution có thể được cache/biểu diễn theo bất cứ cách nào JVM triển khai cho phép. **Không có yêu cầu** runtime phải lưu một native pointer ngay trong bytes của constant pool giống tất cả JVM khác.

### 6.1. Resolution không đồng nghĩa initialization

Một class có thể:

- Đã được load và tạo run-time constant pool.
- Đã hoàn tất verification và preparation.
- Có một số symbolic references đã resolve.
- Nhưng **chưa chạy static initializer (<clinit>)**.

Ngược lại, khi active use yêu cầu initialization, JVM đảm bảo các bước chuẩn bị và thứ tự khởi tạo thích hợp; một số symbolic references vẫn có thể resolve về sau. JVMS cho phép resolution eager/lazy theo các quy tắc của nó, không bắt buộc “resolve tất cả trước lúc bắt đầu <clinit>”.

### 6.2. Những lỗi liên quan symbolic references

| Lỗi | Nhóm nguyên nhân có thể có |
| --- | --- |
| **NoSuchMethodError** | Class runtime không còn method với name/descriptor như caller kỳ vọng |
| **NoSuchFieldError** | Không tìm thấy field với định danh như caller yêu cầu |
| **IllegalAccessError** | Truy cập member/class không hợp lệ theo JVM access/module rules |
| **IncompatibleClassChangeError** | Sự khác biệt về class/interface/static/instance không phù hợp |
| **NoClassDefFoundError** | JVM không lấy được class cần dùng hoặc class đã ở trạng thái erroneous |
| **BootstrapMethodError** | Bootstrap cho dynamic constant/invokedynamic có vấn đề tương ứng |

Các lỗi này không chứng minh run-time pool “đầy”. Nếu thiếu Metaspace/native memory, thông thường cần chẩn đoán **OutOfMemoryError** riêng; nếu class file vượt số slots được phép, compiler/generator có thể báo lỗi định dạng **trước runtime**.

## 7. Những lệnh bytecode thường dùng constant-pool index

| Opcode | Nội dung được liên kết qua pool | Lưu ý |
| --- | --- | --- |
| **ldc** | Loadable constants: int/float, String, Class, MethodHandle, MethodType, dynamic constant phù hợp | Index 1 byte; không nạp long/double thông thường |
| **ldc_w** | Tương tự ldc | Index 2 byte |
| **ldc2_w** | long/double hoặc dynamic constant dạng category 2 thích hợp | Nạp giá trị loại 2 |
| **getstatic** | Fieldref | Đọc field static, có quy tắc initialization |
| **putstatic** | Fieldref | Ghi field static |
| **getfield / putfield** | Fieldref | Đọc/ghi instance field qua object reference |
| **invokevirtual** | Methodref | Virtual method dispatch |
| **invokestatic** | Methodref/InterfaceMethodref phù hợp | Gọi static method, có thể trigger initialization |
| **invokeinterface** | InterfaceMethodref | Interface method dispatch |
| **invokedynamic** | InvokeDynamic entry | Liên kết dynamic call site qua bootstrap |
| **new** | Class reference | Tạo instance, phải tuân initialization |
| **checkcast / instanceof** | Class reference | Kiểm tra type, không tự init class mục tiêu chỉ bởi cast/test |

**Điểm dễ nhầm:** opcode dùng constant-pool entry không có nghĩa operand stack chứa cả pool. **ldc** đẩy giá trị/tham chiếu phù hợp; **invokevirtual** gọi method sau resolution; **getstatic** đọc trạng thái field — các thao tác có tác dụng khác nhau.

### 7.1. Constant pool và dynamic linkage trong Java hiện đại

Java 17 có thể dùng **invokedynamic** cho string concatenation hoặc lambdas tùy cách compiler sinh bytecode. Constant-pool entry tương ứng liên kết với thông tin **BootstrapMethods attribute** và bootstrap method thích hợp.

**Bootstrap method của invokedynamic không đồng nghĩa bootstrap class loader.** Đây là hai thuật ngữ cùng có từ “bootstrap” nhưng mang vai trò hoàn toàn khác:

- Bootstrap **class loader** là một nguồn định nghĩa lớp lõi.
- Bootstrap **method** của invokedynamic/condy tham gia tính toán call site/constant qua cơ chế dynamic linkage.

Đừng giả định mọi string concatenation trong mọi class file Java 17 bắt buộc dùng đúng một dãy indy instructions; xem javap trên artifact thực tế.

## 8. Ví dụ Java 17+: pool, hằng và class initialization

Tạo file **RuntimePoolDemo.java**:

~~~java
public class RuntimePoolDemo {
    static class Target {
        static final int LIMIT = 40 + 2;
        static final String LABEL = "java" + "-vm";
        static int COMPUTED = loadComputed();

        static int loadComputed() {
            System.out.println("Target:<clinit>");
            return 7;
        }

        static String greet(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");

        Class<?> type = Target.class;
        System.out.println("class=" + type.getSimpleName());

        System.out.println("limit=" + Target.LIMIT);
        System.out.println("label=" + Target.LABEL);
        System.out.println("before-active-use");

        System.out.println("computed=" + Target.COMPUTED);
        System.out.println("greet=" + Target.greet("JVM"));
        System.out.println("end");
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 -encoding UTF-8 RuntimePoolDemo.java
java RuntimePoolDemo
~~~

**Stdout chính xác:**

~~~text
begin
class=Target
limit=42
label=java-vm
before-active-use
Target:<clinit>
computed=7
greet=Hello, JVM
end
~~~

Giải thích:

1. **Target.class** sử dụng class literal (có thể tương ứng ldc Class entry trong bytecode), nhưng không bắt buộc chạy **Target.<clinit>**.
2. **LIMIT** và **LABEL** là compile-time constant variables nên caller có thể dùng hằng đã tính sẵn.
3. **COMPUTED** không là constant variable; đọc nó là active use khiến Target initialization chạy lần đầu, in **Target:<clinit>**.
4. Gọi **Target.greet** sau đó không chạy lại static initializer.
5. Trên compiler Java 17 thông dụng, nối chuỗi với tham số có thể qua **invokedynamic**, nhưng điều đó là chi tiết bytecode cần quan sát thực tế.

**Không được dùng stdout trên để suy ra thời điểm chính xác mọi pool entry đã được resolve**. Không in static message không chứng minh class chưa load hoặc link.

### 8.1. Quan sát bằng javap

~~~bash
javap -v -p RuntimePoolDemo
javap -v -p 'RuntimePoolDemo$Target'
javap -c -p RuntimePoolDemo
javap -c -p 'RuntimePoolDemo$Target'
~~~

Trong output:

- **Constant pool** là bảng class-file entries gồm Utf8, Class, String, Fieldref, Methodref, NameAndType...
- **Code** có các instructions và indexes; **#n** là constant-pool index.
- Bạn có thể thấy **ldc** cho Class literal hoặc String constant; không phải mọi literal đều cần ldc riêng vì có tối ưu hằng.
- Với **Target.COMPUTED**, caller có thể có **getstatic RuntimePoolDemo$Target.COMPUTED:I**.
- Với **Target.LIMIT**, bytecode của caller có thể chứa trực tiếp **42** hoặc gộp sẵn vào chuỗi in, không cần getstatic.
- Nếu thấy **BootstrapMethods**, hãy xem các references tới dynamic linkage cho indy.

Output offset, index và trình tự mã lệnh có thể thay đổi theo compiler/JDK. Không coi **javap -v** là bản dump run-time pool trong bộ nhớ của tiến trình đang chạy; javap đọc **class file**.

## 9. Ví dụ Java 17+: String literal, new String và intern

Tạo file **StringIdentityDemo.java**:

~~~java
public class StringIdentityDemo {
    public static void main(String[] args) {
        String literal = "abc";
        String folded = "ab" + "c";
        String constructed = new String("abc");
        String canonical = constructed.intern();

        System.out.println("foldedSame=" + (literal == folded));
        System.out.println("newDifferent=" + (literal != constructed));
        System.out.println("internSame=" + (literal == canonical));
        System.out.println("contentSame=" + literal.equals(constructed));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 StringIdentityDemo.java
java StringIdentityDemo
~~~

**Stdout:**

~~~text
foldedSame=true
newDifferent=true
internSame=true
contentSame=true
~~~

**Lý do:**

- **"ab" + "c"** là compile-time constant expression, tương ứng string literal có nội dung **abc**.
- **new String("abc")** tạo object String khác về identity, dù nội dung bằng literal.
- **intern()** trả canonical String reference cho nội dung **abc**.
- **equals()** so nội dung, **==** so reference identity.

Thí nghiệm này giúp tách **metadata constant pool** khỏi **String object** được application code sử dụng. Với HotSpot hiện đại, String objects được quản lý trên Java heap; run-time constant pool không phải một mảng chứa nguyên các java.lang.String instances bất biến.

## 10. Class loader và nhiều run-time pools có cùng binary name

Runtime class identity không chỉ là binary name, mà gắn với **defining class loader**.

~~~text
Loader A defines demo.Widget
   -> Runtime class A
   -> Class metadata A
   -> Run-time constant pool A

Loader B defines demo.Widget
   -> Runtime class B
   -> Class metadata B
   -> Run-time constant pool B

Hai tên demo.Widget giống nhau; hai runtime classes khác nhau.
~~~

Nếu child loaders ủy quyền cho cùng parent đã định nghĩa class, kết quả có thể là **cùng** runtime class và pool, không tự nhân bản. Chỉ khi **defining loaders thực sự khác nhau**, các runtime classes mới là những kiểu khác nhau.

Điều này quan trọng khi:

- Application server có nhiều deployments/plugins dùng các loader riêng.
- Cùng tên thư viện được nạp ở các isolated loader namespaces.
- Framework sinh proxy classes/dynamic classes.
- Cần phân tích **ClassCastException** với hai tên kiểu nhìn y hệt.
- Theo dõi class unloading và memory retention.

Method area là vùng logic dùng chung giữa JVM threads; điều đó **không xóa ranh giới kiểu** giữa những class do loaders khác nhau định nghĩa.

## 11. HotSpot Metaspace và method area không đồng nhất

| Thuật ngữ | Cấp độ | Ý nghĩa |
| --- | --- | --- |
| **Method area** | JVMS abstraction | Vùng logic cấp lớp, gồm run-time pool và code/metadata theo đặc tả |
| **Metaspace** | HotSpot Java 8+ | Cơ chế cấp phát/quản lý nhiều loại class metadata trong native memory |
| **PermGen** | HotSpot lịch sử | Cơ chế cũ trước Java 8; không là vùng đang dùng của HotSpot Java 17 |
| **Compressed class space** | HotSpot implementation | Vùng metadata phụ thuộc cấu hình compressed class pointers |
| **Code cache** | JIT implementation | Nơi giữ machine code compiled bởi JIT; không phải class-file constant pool |
| **Java heap** | JVM abstraction và implementation | Nơi lưu objects/arrays, gồm String instances theo HotSpot hiện đại |

**Lưu ý:** Mô hình JVMS nói method area logically part of heap nhưng không bắt buộc layout, GC/compaction hoặc location. Mô tả “Metaspace lưu metadata bằng native memory” là mô tả **HotSpot implementation**, không làm sửa lại câu của đặc tả.

### 11.1. Điều gì không nên suy ra?

Không được kết luận:

- Run-time constant pool luôn có vị trí chính xác trong một native block.
- Tất cả numeric constants được lưu nguyên một cấu trúc Java object.
- Mỗi class có metadata kích thước bằng đúng tổng byte file .class.
- -Xmx là giới hạn chính của Metaspace.
- Bytecode trong .class và native instructions sau JIT nằm cùng khu vực vật lý.
- JVM nào cũng có **PermGen**, **Metaspace** hoặc cùng tên logging category.

## 12. Method area có được thu hồi bộ nhớ không?

JVMS **không bắt buộc** method area được garbage-collected hoặc compact theo cách cụ thể. Điều này **không** đồng nghĩa JVM bị cấm thu hồi metadata hoặc class unloading.

Trên HotSpot, khả năng class unloading/reclaim metadata phụ thuộc class loader reachability, GC, runtime state và implementation. Trong một hệ plugin:

~~~text
PluginLoader-v1 -> định nghĩa nhiều classes -> metadata/pools tương ứng
PluginLoader-v2 -> định nghĩa nhiều classes -> metadata/pools mới
PluginLoader-v3 -> ...
~~~

Nếu các plugin loaders cũ bị giữ sống qua **ThreadLocal, thread context loader, callback registry, static cache, executor hoặc MBean**, metadata của classes cũ có thể chưa được giải phóng. Metaspace usage có thể tăng theo số deployments.

**Không tự kết luận memory leak** chỉ vì Metaspace committed memory tăng sau một đợt class loading: JVM có chiến lược commit/reserve/cache và GC riêng. Phải đo xu hướng, số loaders/classes còn sống và các GC/unloading events.

### 12.1. Phân biệt OOME categories

| Thông báo/nhóm lỗi | Nên điều tra |
| --- | --- |
| **OutOfMemoryError: Java heap space** | Object retention, allocations, -Xmx, GC/heap |
| **OutOfMemoryError: Metaspace** | Class metadata, class loading/unloading, -XX:MaxMetaspaceSize và native budget |
| **OutOfMemoryError: Compressed class space** | Cấu hình compressed class metadata space trên HotSpot |
| **ClassFormatError / too many constants** | Class-file format/compiler/generator, không phải heap object usage |
| **NoSuchMethodError** | Linking/reference/binary compatibility, không phải cạn bộ nhớ |

Các chuỗi OOME là cách báo thường thấy trên HotSpot, không phải cam kết tất cả JVM implementations có wording y hệt.

## 13. Công cụ quan sát trên JDK 17

### 13.1. Đọc class-file constant pool

~~~bash
javac --release 17 RuntimePoolDemo.java
javap -v -p RuntimePoolDemo
javap -v -p 'RuntimePoolDemo$Target'
~~~

**javap -v** thể hiện class-file constant pool và attributes; **không cho phép kết luận chính xác kích thước RAM runtime pool**. Quan sát loại entry, name/descriptor và mối quan hệ các indices.

### 13.2. Xem class loading trên HotSpot

~~~bash
java -Xlog:class+load=info RuntimePoolDemo
java -Xlog:help
~~~

Dòng đầu hiển thị class-loading events và có thể in rất nhiều logging lines. Dòng thứ hai liệt kê logging options hỗ trợ. **Class load logs không phải log có <clinit> đã chạy**. Dùng stdout thực nghiệm cùng log để biết sự khác biệt.

### 13.3. Native Memory Tracking và jcmd

Có thể khởi chạy JVM HotSpot với:

~~~bash
java -XX:NativeMemoryTracking=summary RuntimePoolDemo
~~~

Dùng **jcmd** trên một tiến trình Java đang chạy đủ lâu:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.classloaders
jcmd <PID> VM.metaspace
~~~

**<PID>** là placeholder cần thay bằng process ID thực. Những diagnostic commands có thể khác theo bản JDK/JVM; hãy kiểm tra **jcmd <PID> help** trước. **NMT** thường phải được bật khi startup; chương trình demo ở trên thoát rất nhanh, vì vậy muốn attach có thể cần một ứng dụng chạy lâu hơn hoặc quy trình thử nghiệm phù hợp.

NMT giúp xem native allocations theo category nhưng **không phải công cụ đọc từng run-time pool entry**. Khi cần xem object retention, dùng profiler/heap dump; khi cần class-file structure, dùng javap; khi cần native metadata, dùng NMT/metaspace tools tương ứng.

### 13.4. -XX:MaxMetaspaceSize không phải -Xmx

Ví dụ cấu hình chỉ để minh họa cú pháp:

~~~bash
java -XX:MaxMetaspaceSize=128m RuntimePoolDemo
~~~

Không coi **128m** là khuyến nghị production. Đặt quá thấp có thể gây lỗi không cần thiết. Nếu gặp Metaspace OOME, điều tra class loaders/classes, dynamic bytecode generation, unloading/GC và tổng native memory trước khi chọn ngân sách mới.

## 14. Các lỗi nhận thức phổ biến

1. **“Method area chính là Java heap -Xmx trong mọi JVM.”** Sai: “logically part of heap” là abstraction; layout không được bắt buộc.
2. **“Metaspace là một mục bắt buộc trong JVMS.”** Sai: đây là implementation detail của HotSpot.
3. **“Mỗi JVM chỉ có một run-time constant pool duy nhất.”** Sai: một pool logic trên mỗi runtime class/interface.
4. **“Pool chỉ gồm literal strings.”** Sai: có numeric entries và references đến class/field/method, dynamic data...
5. **“CONSTANT_Utf8 là java.lang.String object.”** Sai: đó là constant-pool text metadata.
6. **“String intern pool là toàn bộ run-time constant pool.”** Sai: intern chỉ liên quan canonical String identity.
7. **“Một frame chứa bản copy toàn bộ pool.”** Sai: frame có reference đến pool của class chứa method.
8. **“Javap cho biết địa chỉ pool trong RAM.”** Sai: javap đọc artifact.
9. **“Class literal tự khởi tạo lớp được tham chiếu.”** Sai: việc có Class object không tự chạy <clinit>.
10. **“Resolution và initialization là một.”** Sai: resolution là phần linking, initialization có điều kiện riêng.
11. **“Tăng -Xmx luôn chữa được OOME Metaspace.”** Sai: HotSpot quản lý metadata bằng cơ chế native-memory riêng.
12. **“Method area tuyệt đối không thu hồi.”** Sai: JVMS không bắt buộc GC, không cấm class unloading.
13. **“Cùng tên class chỉ có một runtime pool.”** Sai khi different defining class loaders tạo các runtime classes riêng.
14. **“Constant pool entry count cho biết số object instances.”** Sai: metadata entries và runtime objects là các tập khác nhau.
15. **“Mọi class-file pool có giới hạn 65.535 entries thực.”** Chưa chính xác: count là u2, index 0 dành riêng, Long/Double chiếm hai index slots.
16. **“Run-time pool tối đa 65.535 byte.”** Sai: giới hạn 65.535 áp dụng cho u2 constant_pool_count và từng Utf8 payload (byte MUTF-8); không phải hard cap bộ nhớ runtime pool.

## 15. Bài tập tự kiểm tra

**Bài 1.** Method area chia sẻ giữa threads hay riêng mỗi thread? JVM stacks thì sao?

**Đáp án:** Method area dùng chung; mỗi JVM thread có stack của chính mình. Mỗi frame có reference tới run-time pool tương ứng chứ không chứa bản sao toàn bộ pool.

**Bài 2.** Class A gọi B.work() qua invokestatic. Methodref thường ở class-file constant pool của A hay B?

**Đáp án:** Nằm trong pool của class chứa instruction, tức A; runtime resolution trỏ đến method ở B.

**Bài 3.** Hai loaders định nghĩa cùng binary name C từ cùng bytes. Có mấy runtime pools?

**Đáp án:** Hai pool logic tương ứng hai runtime classes khác defining loader.

**Bài 4.** Việc đọc **C.class** có bảo đảm static initializer C chạy không?

**Đáp án:** Không. Class literal không yêu cầu initialization chỉ do thao tác đó; Class object có thể đã tồn tại sau loading/linking.

**Bài 5.** Nếu javap hiện **CONSTANT_String "abc"**, có phải một String object đang được lưu trong mảng cp_info ở heap không?

**Đáp án:** Không. Entry mô tả string constant; String object/reference runtime là thực thể khác. Javap đọc class file, không dump heap.

**Bài 6.** Một chương trình có 10.000 classes và mỗi class dùng 200 pool slots. Có vi phạm giới hạn một class-file constant pool không?

**Đáp án:** Không chỉ từ các con số đó; mỗi class có pool riêng. Tổng metadata có thể tăng, nhưng đó là bài toán memory khác.

**Bài 7.** Có thể kết luận từ **constant_pool_count=500** rằng runtime metadata đúng 500 × 8 byte không?

**Đáp án:** Không. Entries có loại khác nhau, có Long/Double two-slot rules, và runtime layout tùy JVM.

**Bài 8.** **NoSuchMethodError** liên quan điều gì?

**Đáp án:** Thường do symbolic method reference cần resolve không khớp binary class/method runtime; không chứng minh pool đầy.

**Bài 9.** Vì sao một plugin redeploy nhiều lần có thể làm Metaspace tăng?

**Đáp án:** Nếu loaders cũ và classes của chúng còn được giữ tham chiếu, runtime class metadata/pools không được unloading/reclaimed kịp thời.

**Bài 10.** **-Xmx** có phải tùy chọn chuẩn để giới hạn toàn bộ method area của JVM trên HotSpot Java 17 không?

**Đáp án:** Không. Nó chủ yếu giới hạn Java heap. Metaspace/class metadata có bộ cơ chế và giới hạn riêng ở HotSpot.

**Bài 11.** Class bị load và runtime pool đã hình thành nhưng static block chưa in log. Điều đó mâu thuẫn không?

**Đáp án:** Không. Class loading/linking không đồng nghĩa class initialization.

**Bài 12.** **String.intern()** có resolve tất cả Methodref entries trong pool của class đang gọi nó không?

**Đáp án:** Không. String intern chỉ giải quyết canonical String identity, không thay dynamic linking.

**Bài 13.** Vì sao phải phân biệt **BootstrapMethods attribute** và **bootstrap class loader**?

**Đáp án:** BootstrapMethods cung cấp dữ liệu cho dynamic linkage như invokedynamic; bootstrap loader phục vụ định nghĩa nhiều core classes. Chúng là hai cơ chế khác.

**Bài 14.** JVM có bắt buộc method area nằm trong một vùng contiguous native memory và được compact khi GC không?

**Đáp án:** Không. JVMS không bắt buộc vị trí, cấu trúc native allocation hoặc GC/compaction policies cụ thể.

## 16. Checklist vận dụng

- Xác định khi nào đang nói về **JVMS abstraction** và khi nào nói về **HotSpot implementation**.
- Khi xem memory, tách **method area logic**, **Metaspace**, **Java heap**, **code cache** và **native memory**.
- Nhớ **run-time pool gắn với runtime class/interface**, không với toàn process; xét defining class loader.
- Khi đọc bytecode, biết **pool index thuộc caller class chứa instruction**, không tự chuyển thành owner class của target.
- Khi nhìn **ldc**, phân biệt metadata entry, giá trị trên operand stack và object được tham chiếu.
- Khi nhìn **getstatic/invoke**, xem symbolic resolution, access constraints và quy tắc initialization.
- Khi nói tới constants, tách class-file Utf8/String entries khỏi String.intern và static fields.
- Khi chẩn đoán giới hạn, phân biệt **pool slots per class file**, **Utf8 MUTF-8 byte length**, **runtime metadata budget** và **Java heap**.
- Khi gặp linkage errors, kiểm tra descriptor, runtime dependency, module, class loader và class version.
- Khi nghi ngờ Metaspace leak, đo xu hướng class loaders/classes và kiểm tra references giữ loaders còn sống.
- Khi đưa dẫn chứng, ưu tiên **JVMS/JLS** cho semantics; chỉ dùng tài liệu HotSpot/JDK cho flags, Metaspace và các công cụ native.

### Tài liệu chính thức

- **JVMS Java SE 17, §2.5.3 — Heap:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3
- **JVMS Java SE 17, §2.5.4 — Method Area:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.4
- **JVMS Java SE 17, §2.5.5 — Run-Time Constant Pool:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.5
- **JVMS Java SE 17, §2.6.3 — Dynamic Linking:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.3
- **JVMS Java SE 17, §4.4 — The Constant Pool:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4
- **JVMS Java SE 17, §5.4.3 — Resolution:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3
- **JVMS Java SE 17, §6.5 — Instructions:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- **Oracle Java SE 17 VM Guide, Native Memory Tracking:** https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html

**Ghi nhớ cốt lõi:** **Method area** là vùng logic chứa metadata/method code và được chia sẻ giữa JVM threads; mỗi runtime class/interface có **run-time constant pool** riêng như một phần của vùng này. Pool chứa literals lẫn symbolic references và được dùng bởi instructions/dynamic linking. **String intern pool**, **static field values**, **heap objects** và **HotSpot Metaspace** là các khái niệm liên quan nhưng **không đồng nghĩa**. Muốn hiểu đúng, hãy phân biệt **mô hình chuẩn JVM** với **bố trí bộ nhớ của implementation cụ thể**.
