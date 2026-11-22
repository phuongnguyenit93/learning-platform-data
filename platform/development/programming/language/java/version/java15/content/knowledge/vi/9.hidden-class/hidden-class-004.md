# Hidden class: giới hạn tham chiếu theo tên từ bytecode của lớp khác

> **Ngữ cảnh Java 15:** JEP 371 đưa **hidden classes** vào JDK 15. Đây là tính năng JVM/API công khai, ổn định và vẫn có trên các JDK hiện đại. Bài học tập trung vào quy tắc cốt lõi: **một hidden class không thể được tham chiếu theo tên qua constant pool của lớp khác**, nhưng vẫn có thể được sử dụng **gián tiếp** qua đối tượng, interface, `Class<?>`, reflection và method handle.

## 1. Vấn đề: vì sao bytecode thường cần tên lớp?

Trong Java thông thường, ta có thể viết:

~~~java
Worker worker = new Worker();
worker.run();
~~~

Đây là **mã minh họa**, giả sử có lớp `Worker` truy cập được. Khi biên dịch, bytecode sử dụng các **symbolic references** đến những kiểu/thành viên cần thiết. Ví dụ:

- Lệnh `new` cần một tham chiếu kiểu lớp có thể phân giải.
- `checkcast` và `instanceof` kiểm tra kiểu được mã hóa trong constant pool.
- `getfield`, `putfield`, `invokevirtual`, `invokestatic` và các lệnh tương tự phân giải các tham chiếu thành viên dựa trên thông tin symbolic.
- Descriptor của field, parameter, return type hoặc superclass/superinterface trong class file cũng có thể đề cập tên kiểu.

Các tham chiếu này dựa trên **internal form của binary name** — ví dụ binary name `com.example.Worker` được ghi dưới dạng nội bộ `com/example/Worker`. JVM dùng tên và ngữ cảnh class loader để phân giải tham chiếu đến lớp tương ứng.

Một **named class** được định danh bằng binary name hợp lệ. Vì thế, bytecode từ các lớp khác có thể dùng tham chiếu symbolic đến nó, nếu thỏa các quy tắc visibility, access, module, loader và linking.

**Hidden class khác ở điểm căn bản:** tên runtime của nó **không phải binary name**, nên không thể dùng để tạo một tham chiếu symbolic hợp lệ từ constant pool của lớp khác.

## 2. Định nghĩa hidden class theo API hiện hành

Hidden class là class/interface được định nghĩa qua API:

~~~java
MethodHandles.Lookup.defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options
)
~~~

Method trên thuộc `java.lang.invoke.MethodHandles.Lookup` và có từ Java 15. Nó nhận **bytes của một class file hợp lệ**, tạo một class mới ở runtime và trả về **`MethodHandles.Lookup` trỏ vào class vừa tạo**.

Khác với cách thông thường dùng `ClassLoader.defineClass` để tạo named class, `defineHiddenClass` tạo một runtime class có thể tồn tại và hoạt động mà **không được đăng ký để các lớp khác tìm theo binary name**.

Những đặc điểm nên nhớ:

1. Hidden class có **định danh class thực sự** trong JVM, có thể có fields, methods, constructor và instance.
2. Class này có một **`Class<?>` object** và các API phản chiếu có thể mô tả nó.
3. `Class.isHidden()` trả về `true`.
4. `Class.getName()` trả về một chuỗi tên đặc biệt chứa dấu gạch chéo `/` và một hậu tố runtime; chuỗi đó **không phải binary name**.
5. Không thể tra hidden class bằng `Class.forName(...)`, `ClassLoader.loadClass(...)` hoặc `Lookup.findClass(String)` chỉ bằng chuỗi tên của nó.
6. **Lớp khác không thể nhắc đến hidden class bằng một entry trong constant pool**, bất kể hidden class có phương thức `public` hay được tạo từ bytes vốn là một class `public`.

Đây là **giới hạn tham chiếu theo tên (nominal/symbolic reference)**; không nên diễn giải thành “hidden class không có tên hiển thị”, “không có `Class` object”, “không thể có instance” hoặc “hoàn toàn không thể gọi phương thức của nó”.

## 3. Vì sao không thể tham chiếu từ constant pool của lớp khác?

### 3.1. Binary name và runtime name không giống nhau

Giả sử một class template ban đầu có binary name:

~~~text
sample.TaskTemplate
~~~

Khi được định nghĩa thành hidden class, runtime có thể đưa ra tên tương tự:

~~~text
sample.TaskTemplate/0x...
~~~

Phần `0x...` là **hậu tố phụ thuộc runtime**, chỉ minh họa; không được hardcode hay suy đoán giá trị cụ thể.

Các quy tắc:

- Binary name của class thông thường dùng dạng tên đủ điều kiện, chẳng hạn `sample.TaskTemplate`.
- Constant pool và class descriptors dùng dạng nội bộ của các binary names hợp lệ.
- Tên do `Class.getName()` trả về cho hidden class có hậu tố phân tách bởi `/` và **không phải binary name hợp lệ**.
- Vì không có binary name cho hidden class, không có tên lớp nội bộ hợp lệ nào mà **một lớp khác** có thể đặt trong `CONSTANT_Class_info` để phân giải ra đúng hidden class đó.

Hệ quả: **không thể lấy chuỗi `getName()` của hidden class rồi gắn vào constant pool của một class khác để JVM phân giải class đó như một named class.** Tên runtime dùng để quan sát/debug; nó không phải “đường dẫn công khai” đến class.

### 3.2. Những dạng tham chiếu theo tên bị giới hạn

Một lớp khác **không thể dùng hidden class làm mục tiêu được định danh symbolic** trong:

| Vị trí trong class/bytecode của lớp khác | Vì sao không thể đặt hidden class ở đây? |
| --- | --- |
| `new HiddenType` | `new` dùng symbolic class reference; hidden class không có binary name để phân giải |
| `checkcast HiddenType` / `instanceof HiddenType` | Loại đích phải được biểu diễn trong symbolic reference của lớp gọi |
| `HiddenType.class` | Class literal cần một symbolic class entry |
| Khai báo `HiddenType field;` | Field descriptor không thể định danh hidden class bằng binary name |
| Tham số `m(HiddenType value)` | Method descriptor của lớp khác không thể ghi tên hidden class theo dạng hợp lệ |
| Giá trị trả về `HiddenType m()` | Giới hạn tương tự trên method descriptor |
| `extends HiddenType` / `implements HiddenInterface` | Supertype/superinterface của lớp khác phải được ghi bằng symbolic name |
| Gọi trực tiếp thành viên với declaring type là `HiddenType` | Symbolic owner reference trong bytecode không thể là hidden class |

Đây là **quy tắc ở mức class file/JVM**, không đơn thuần là lỗi vì thiếu `import`, thiếu `public` hay do visibility của Java source. Ngay cả khi giữ được `Class<?>` object của hidden class, ta vẫn không làm xuất hiện một **binary name** để compiler/JVM giải quyết các mục trên.

### 3.3. “Lớp khác” và bản thân hidden class là hai ngữ cảnh khác nhau

JVM vẫn phải nạp, liên kết và thực thi bytecode **bên trong hidden class**. `defineHiddenClass` có quy trình tạo class và xử lý các tham chiếu phù hợp của chính class đó; không nên suy diễn rằng hidden class không thể thực thi một lệnh `new`, gọi phương thức của chính nó hay triển khai interface.

Quy tắc đang học là: **một class/interface khác không thể định danh hidden class qua constant pool của chính lớp khác đó**. Đây là ranh giới cần nêu chính xác.

## 4. Không tìm theo tên không có nghĩa là không thể sử dụng

Hidden class thường được sử dụng **gián tiếp**. Một framework có thể:

1. Tạo hoặc nhận bytes mô tả class cần sinh động.
2. Gọi `lookup.defineHiddenClass(...)` và giữ lại `Lookup` hoặc `Class<?>` được trả về.
3. Dùng `Lookup.findConstructor`, `findStatic`, `findVirtual`, method handle hoặc reflection có quyền truy cập phù hợp để tạo instance và gọi hành vi.
4. Truyền instance qua `Object` hoặc một **interface/superclass thông thường** mà lớp gọi biết trước.
5. Gọi các phương thức thông qua interface thông thường đó.

Ví dụ một hidden class triển khai `Runnable`. Bytecode của lớp gọi có thể chứa kiểu `java.lang.Runnable` và thực thi `Runnable.run()` trên đối tượng hidden class. Điều đó **không phải** là tham chiếu symbolic theo tên đến hidden class; JVM thực hiện lời gọi ảo qua interface đã được biết.

Mô hình:

~~~text
Host.class (named class)
    |
    | đọc bytes của một class template
    v
Lookup.defineHiddenClass(bytes, ...)
    |
    v
Lookup + Class<?> của hidden class
    |
    | findConstructor(...) -> MethodHandle -> instance
    v
Runnable task = (Runnable) instance
    |
    | invokeinterface Runnable.run
    v
Phương thức run() của instance hidden class
~~~

Trong class file của `Host`, kiểu dùng để gọi là **`java/lang/Runnable`**, không phải tên đặc biệt của hidden class.

## 5. Ví dụ chạy được: tạo hidden class và gọi gián tiếp qua Runnable

Ví dụ có **hai file nguồn độc lập** trong **cùng thư mục và cùng package mặc định**, để không phải thêm thư viện tạo bytecode. Đặt tên file đúng như dưới đây.

### File 1: `TaskTemplate.java`

~~~java
public class TaskTemplate implements Runnable {
    public TaskTemplate() {
    }

    @Override
    public void run() {
        System.out.println("Hidden task ran");
    }
}
~~~

Đây là **template class thông thường** được biên dịch thành `TaskTemplate.class`. Mục tiêu là dùng **bytes của class file đó** để định nghĩa **một class thứ hai, hidden**, có hành vi tương đương. Hai class runtime có **danh tính khác nhau**, dù có chung bytes nguồn.

### File 2: `HiddenClassBoundaryDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenClassBoundaryDemo {
    public static void main(String[] args) throws Throwable {
        byte[] classBytes =
                Files.readAllBytes(Path.of("TaskTemplate.class"));

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup()
                        .defineHiddenClass(classBytes, true);

        Class<?> hiddenType = hiddenLookup.lookupClass();

        System.out.println("isHidden: " + hiddenType.isHidden());
        System.out.println("nameHasSlash: "
                + hiddenType.getName().contains("/"));
        System.out.println("canonicalNameNull: "
                + (hiddenType.getCanonicalName() == null));

        try {
            Class.forName(hiddenType.getName());
            System.out.println("byName: found");
        } catch (ClassNotFoundException expected) {
            System.out.println("byName: not-found");
        }

        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(void.class));

        Runnable task = (Runnable) constructor.invoke();
        System.out.println("instanceHidden: "
                + task.getClass().isHidden());
        task.run();

        Class<?> ordinaryType = Class.forName("TaskTemplate");
        System.out.println("ordinaryClassHidden: "
                + ordinaryType.isHidden());
        System.out.println("distinctClass: "
                + (hiddenType != ordinaryType));
    }
}
~~~

Đây là **một chương trình Java hoàn chỉnh**, dùng các API công khai. `main` khai báo `throws Throwable` vì lời gọi method handle `invoke()` có thể ném `Throwable`.

### Biên dịch và chạy

Mở terminal tại đúng thư mục chứa hai file:

~~~bash
javac TaskTemplate.java HiddenClassBoundaryDemo.java
java HiddenClassBoundaryDemo
~~~

**Stdout chính xác trên JDK 17+ phù hợp:**

~~~text
isHidden: true
nameHasSlash: true
canonicalNameNull: true
byName: not-found
instanceHidden: true
Hidden task ran
ordinaryClassHidden: false
distinctClass: true
~~~

Phân tích từng kết quả:

1. `isHidden: true` xác nhận class được `defineHiddenClass` tạo thuộc loại hidden.
2. `nameHasSlash: true` cho thấy tên runtime có dạng không phải binary name; chương trình không dựa vào hậu tố động nên stdout vẫn xác định được.
3. `canonicalNameNull: true` phản ánh hidden class không có canonical name theo mô hình tên của Java source.
4. `byName: not-found`: truyền **tên runtime của chính hidden class** vào `Class.forName` không thể tìm lại nó.
5. `findConstructor` tạo method handle dựa trên **`Class<?> hiddenType`**; method handle cho phép tạo instance dù class không thể định danh qua constant pool của lớp gọi.
6. Instance được cast sang `Runnable` (một interface có binary name bình thường), vì template thực thi interface đó. `task.run()` gọi đúng code của hidden instance.
7. `Class.forName("TaskTemplate")` có thể tìm **named class thông thường** từ file `TaskTemplate.class` trên classpath. Đây **không phải** hidden class được `defineHiddenClass` tạo, nên `ordinaryClassHidden: false` và `distinctClass: true`.

**Điểm cần nhớ:** file `TaskTemplate.class` trên đĩa giúp demo đơn giản, nhưng hidden class mới được tạo bằng bytes này **không phải** class `TaskTemplate` thông thường mà class loader có thể tìm bằng tên. Một template tên giống nhau **không làm lộ** định danh hidden class.

### Điều kiện chạy và lỗi do môi trường

- Chạy hai lệnh `javac` và `java` trong cùng thư mục để `Path.of("TaskTemplate.class")` tìm được file. Nếu chạy từ thư mục khác, có thể gặp `NoSuchFileException`; đây là lỗi đường dẫn demo, không phải giới hạn của hidden class.
- `Lookup.defineHiddenClass` yêu cầu lookup có **full privilege access** phù hợp, và bytes phải mô tả class trong **cùng runtime package** với lookup class. Hai class của ví dụ cùng **unnamed package**, nên thỏa điều kiện. Trong dự án có package, hãy đặt host và template trong cùng package và đọc bytes bằng đường dẫn phù hợp.
- Dùng JDK 17+ được hỗ trợ và có cập nhật bảo mật. API được giới thiệu trong Java 15, không cần `--enable-preview`.
- Chỉ dùng bytes **đáng tin cậy và đã được kiểm tra**; việc tạo class runtime là một khả năng mạnh, không nên dùng bytes tùy ý do người dùng gửi vào ứng dụng.

Có thể kiểm tra nguồn/API Java 15 bằng JDK mới còn hỗ trợ target:

~~~bash
javac --release 15 TaskTemplate.java HiddenClassBoundaryDemo.java
~~~

Lệnh trên kiểm tra tính tương thích nguồn và API với Java 15. Việc chạy ứng dụng vẫn phụ thuộc JDK runtime và cấu hình thực tế.

## 6. Nhìn ở mức bytecode: điều gì xuất hiện và điều gì không?

Công cụ `javap` của JDK giúp đọc bytecode:

~~~bash
javap -c HiddenClassBoundaryDemo
javap -v HiddenClassBoundaryDemo
~~~

Bản hiển thị chính xác có thể khác theo phiên bản compiler; **không nên cố định số thứ tự constant pool hoặc mã bytecode của từng biểu thức**. Những điều có thể kiểm tra về mặt ý nghĩa:

- Mã gọi `MethodHandles.Lookup.defineHiddenClass`: đó là một lời gọi API công khai có tên và descriptor bình thường.
- Mã gọi `MethodHandle.invoke`/`Lookup.findConstructor`: đó là đường đi qua object `Class<?>`, `Lookup` và `MethodHandle` tại runtime.
- Mã ép kiểu `Runnable` và gọi `Runnable.run`: type được mã hóa là **`java/lang/Runnable`**.
- Chuỗi ký tự `"TaskTemplate.class"` và `"TaskTemplate"` trong source là **đường dẫn/tên của class template bình thường**. Chúng không phải tên được JVM tạo cho hidden instance.
- Tên hidden class có hậu tố runtime chỉ xuất hiện **sau khi** `defineHiddenClass` thực thi; lớp gọi không thể biên dịch một `CONSTANT_Class` symbolic để định danh hidden type đó.

Ta có thể tưởng tượng đoạn Java sau, nhưng **không phải mã nguồn biên dịch được**:

~~~text
// Pseudocode: HiddenRuntimeType không phải tên kiểu hợp lệ.
HiddenRuntimeType object = new HiddenRuntimeType();
~~~

Ngay cả khi thay tên giả bằng chuỗi mà `hiddenType.getName()` trả về, nó không trở thành một Java binary name, và class file của **lớp khác** không có tham chiếu symbolic hợp lệ tới hidden class này.

## 7. Giải thích sâu hơn: cùng bytecode nhưng khác định danh runtime

Từ ví dụ có hai class:

~~~text
TaskTemplate (named class)
TaskTemplate/0x... (hidden class, tên chỉ mang tính minh họa)
~~~

Đừng cho rằng “cùng class file bytes thì phải cùng class runtime”. Với JVM, **định danh và cách class được định nghĩa** mới là điều quan trọng. `defineHiddenClass` tạo một định nghĩa mới dù bytes đầu vào xuất phát từ template.

Phân biệt:

| Thuộc tính | `TaskTemplate` named | Bản hidden tạo từ `TaskTemplate.class` |
| --- | --- | --- |
| Có `Class<?>` object | Có | Có |
| `Class.isHidden()` | `false` | `true` |
| Có binary name cho tham chiếu từ class khác | Có | **Không** |
| `Class.forName("TaskTemplate")` tìm đến | Có thể, nếu classpath/loader phù hợp | **Không**, đó là named class nếu tồn tại |
| `Class.forName(hiddenType.getName())` tìm đến | Không áp dụng như cách tìm named template | **Không** |
| Có thể triển khai `Runnable` | Có | Có |
| Instance có thể được cast sang `Runnable` | Có | Có |
| Dùng `hiddenLookup.findConstructor(hiddenType, ...)` | Không cần cho ví dụ named | Có, nếu lookup đủ quyền |
| Mục tiêu của tham chiếu constant pool trong class khác | Có thể | **Không thể theo tên** |

Vì sao `Runnable` là cầu nối hợp lý? Hidden class có thể triển khai một **interface đã biết trước**. Lớp khác tham chiếu đến interface bằng binary name `java.lang.Runnable`, dùng lệnh bytecode thông thường của interface, và JVM dispatch đến phương thức của object thực tế.

Vì vậy, câu “hidden class không thể được sử dụng trực tiếp bởi bytecode lớp khác” phải được hiểu là **không thể định danh trực tiếp hidden class bằng symbolic reference**. Nó **không** cấm bytecode lớp khác gọi `Runnable.run()` trên một object hidden class.

## 8. Reflection, method handles và giới hạn quyền truy cập

### 8.1. Method handles

API `Lookup.defineHiddenClass` trả về `Lookup` mà lookup class là **hidden class vừa tạo**. Đây là cách tự nhiên để framework có **capability** tìm constructor/method/field theo đối tượng `Class<?>`:

~~~java
// Mảnh minh họa; yêu cầu đã có hiddenLookup và hiddenType:
java.lang.invoke.MethodHandle runHandle =
        hiddenLookup.findVirtual(
                hiddenType,
                "run",
                java.lang.invoke.MethodType.methodType(void.class));
~~~

Lệnh ở trên **tạo một method handle tại runtime**. Không có `HiddenType` nào được viết trong Java source; `hiddenType` là biến giữ `Class<?>`. Việc tìm handle vẫn chịu kiểm tra quyền truy cập của `Lookup` và signature phù hợp; “hidden” không có nghĩa mọi member đều tự động được phép gọi từ bất kỳ ngữ cảnh nào.

### 8.2. Reflection

Nếu có `Class<?>` của hidden class, người dùng có thể truy vấn những metadata/method phù hợp qua reflection, ví dụ:

~~~java
// Mảnh minh họa trong phương thức:
java.lang.reflect.Method method =
        hiddenType.getDeclaredMethod("run");
~~~

Để gọi method bằng reflection, vẫn phải thỏa **access checks** và các giới hạn module có liên quan. `Class.forName` **không** dùng để nhận `Class<?>` hidden class từ chuỗi tên; đối tượng `Class<?>` phải đến từ `Lookup`/đối tượng đang có hoặc một API đã có reference tương ứng.

### 8.3. Tên đặc biệt không phải khóa định danh cho hệ thống

Không dùng `hiddenType.getName()` làm tên để:

- Tải class lại trong phiên chạy khác.
- Đăng ký class vào cấu hình dependency injection dưới giả định đó là một binary name ổn định.
- Sinh một class file khác cần `extends`/`implements` hoặc trường/return type trực tiếp là hidden type.
- Dựng `ClassDesc.of(name)` với giả định có thể mô tả hidden class theo nominal descriptor chuẩn.

Hãy giữ các **runtime handles** hoặc giao diện được thiết kế rõ ràng, thay vì phụ thuộc vào hậu tố runtime.

## 9. `NESTMATE` và `STRONG` không xóa giới hạn tên

`defineHiddenClass` hỗ trợ các lựa chọn qua `MethodHandles.Lookup.ClassOption`:

- **`NESTMATE`:** làm hidden class trở thành một nestmate của lớp lookup gốc theo quy tắc JVM phù hợp, cho phép truy cập private theo cơ chế nestmate khi các điều kiện được thỏa.
- **`STRONG`:** tạo mối quan hệ mạnh với defining loader, ảnh hưởng đến điều kiện có thể unload của hidden class.

Các option này giải quyết **quyền truy cập** và **vòng đời**, không biến hidden class thành named class. Bất kể chọn `NESTMATE` hay `STRONG`, constant pool của lớp khác vẫn **không thể ghi tham chiếu symbolic bằng tên** đến hidden class đó.

Không suy diễn “hidden luôn unload ngay”: khả năng thu hồi còn phụ thuộc việc có đối tượng, `Class<?>`, method handle, lookup và các reference khác còn reachable hay không, cũng như quyết định GC. `STRONG` thay đổi mức ràng buộc vòng đời; nó không phải công tắc cho phép dùng hidden class làm kiểu trong source.

## 10. Ứng dụng thực tế còn phù hợp

**Sinh mã động cho framework/runtime:** hidden class hữu ích khi một công cụ cần tạo class để thực thi một hành vi nội bộ nhưng **không muốn tạo một loại được các lớp khác tham chiếu bằng tên ổn định**. Các framework có thể giữ method handle hoặc tạo instance triển khai interface được biết.

**Hỗ trợ các đối tượng hành vi tạm thời:** việc ẩn tên có thể giúp lớp được sinh động không trở thành một phần của API danh nghĩa; việc unload có thể thuận lợi hơn trong những tình huống phù hợp. Không được coi hidden class là API dành cho mọi ứng dụng thông thường.

**Giới hạn rò rỉ chi tiết triển khai:** lớp dùng hidden class thường chỉ lộ interface hoặc phương thức công khai ở mức thiết kế sản phẩm. Nhưng giới hạn **không cho phép symbolic reference** không phải hệ thống sandbox, mã hóa hay cơ chế bảo mật hoàn chỉnh. Nếu đã có `Class<?>`/reference, vẫn có thể khám phá và tương tác theo các quyền cho phép.

**Lambda và runtime:** một số triển khai JDK dùng hidden classes để hỗ trợ các cơ chế sinh lớp cho lambda. Đây là chi tiết triển khai có thể thay đổi; trong mã ứng dụng, nên lập trình theo hợp đồng ngôn ngữ của lambda và các interface chức năng, không dựa vào tên hay cấu trúc cụ thể của generated class.

## 11. Phân biệt hidden class với các khái niệm gần tên

| Khái niệm | Có thể được lớp khác tham chiếu symbolic bằng tên? | Điểm khác biệt |
| --- | --- | --- |
| Named class `public` | Có, nếu access/module/loader phù hợp | Có binary name ổn định |
| Named class package-private | Có thể trong phạm vi truy cập hợp lệ | Vẫn có binary name; giới hạn là access control |
| Nested/private class đã biên dịch | Có binary name trong class file; việc dùng phụ thuộc quyền truy cập | `private` không tương đương `hidden` |
| Anonymous/local class từ mã Java | Compiler vẫn có cách biểu diễn class runtime/class file theo cơ chế thông thường; không tự động là hidden class | “Không viết tên trong source” không đồng nghĩa “không có binary name” |
| **Hidden class** qua `defineHiddenClass` | **Không, đối với constant pool của lớp khác** | Runtime name không phải binary name; dùng gián tiếp |
| Class được nạp từ custom `ClassLoader` | Có thể, nếu named class với binary name và loader phù hợp | Custom loader tự nó không làm class thành hidden |

Một nhầm lẫn quan trọng: **private class** có thể bị từ chối truy cập, nhưng kiểu của nó vẫn có thể được biểu diễn bằng binary name trong bytecode phù hợp. Hidden class đặt ra giới hạn mạnh hơn và khác về bản chất: **không có binary name để lớp khác dùng làm symbolic reference**.

## 12. Các lỗi phổ biến và cách khắc phục

| Nhận định hoặc thao tác sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Hidden class không có `Class<?>` object” | Không hiểu cách API trả về reference | Dùng `hiddenLookup.lookupClass()` |
| Gọi `Class.forName(hiddenType.getName())` và mong tìm được | `ClassNotFoundException` | Giữ `Class<?>`/`Lookup` hoặc interface |
| Nghĩ tên `getName()` là binary name để ghi class file khác | Không thể phân giải hidden type qua constant pool | Không dùng tên runtime làm symbolic type name |
| “Không tham chiếu được theo tên nghĩa là không tạo instance được” | Bỏ qua method handles/ reflection | Dùng `Lookup.findConstructor` và quyền hợp lệ |
| Nghĩ `Runnable.run()` trên hidden instance là “tham chiếu trực tiếp hidden class” | Nhầm symbolic reference với dispatch tại runtime | Bytecode đang gọi interface `Runnable` |
| Cho rằng `public` hoặc `NESTMATE` làm class trở thành named | Nhầm access control với identity/naming | Phân biệt tên symbolic, quyền và lifetime |
| Dùng `new TaskTemplate()` rồi tưởng đó là hidden instance | Tạo **named instance**, không phải bản hidden được định nghĩa từ bytes | Lấy instance qua `Lookup`/method handle của bản hidden |
| Đọc `TaskTemplate.class` từ sai thư mục | `NoSuchFileException` | Dùng working directory đúng hoặc resource path phù hợp |
| Định nghĩa hidden class từ bytes ở package khác với lookup | Không đáp ứng ràng buộc của API | Dùng lookup hợp lệ và template cùng package runtime |
| Dựa vào tên/hậu tố cụ thể của hidden class trong test | Test mong manh, phụ thuộc runtime | Kiểm tra `isHidden` và thuộc tính được đặc tả |
| Coi hidden class như sandbox thực thi mã không tin cậy | Vẫn có rủi ro từ mã động | Thẩm định code/bytes và quyền runtime; dùng ranh giới bảo mật thực sự |

## 13. Bài tập và đáp án

**Bài 1.** Vì sao bytecode lớp khác không thể dùng `new` với hidden class, dù có giữ chuỗi từ `getName()`?

**Đáp án:** `new` dùng một symbolic class reference trong constant pool. Hidden class không có binary name hợp lệ cho tham chiếu đó; chuỗi `getName()` mang hậu tố runtime, không trở thành class name có thể phân giải bằng cách chép vào class file khác.

**Bài 2.** Một instance hidden class triển khai `Runnable`. Có thể cast nó sang `Runnable` và gọi `run()` không?

**Đáp án:** Có, nếu object thực sự implements `Runnable`. Bytecode tham chiếu tên **`java.lang.Runnable`**, còn JVM dispatch đến implementation của object lúc chạy.

**Bài 3.** `Class.forName("TaskTemplate")` tìm được class và `isHidden()` là `false`. Điều này có chứng minh `defineHiddenClass` thất bại không?

**Đáp án:** Không. Nó chứng minh chỉ rằng **named class** `TaskTemplate` được classpath/loader tìm thấy. Bản hidden tạo từ cùng bytes là **một class khác**; kiểm tra object `Class<?>` do returned `Lookup` cung cấp.

**Bài 4.** Chọn option `NESTMATE` cho `defineHiddenClass` có làm code lớp khác viết được một field trực tiếp kiểu hidden class không?

**Đáp án:** Không. `NESTMATE` liên quan quyền private access theo nestmate, không cung cấp binary name để ghi field descriptor.

**Bài 5.** Có thể dùng `MethodType`/`MethodHandle` với `Class<?>` hidden class ở runtime không?

**Đáp án:** Có, với quyền và chữ ký phù hợp. `MethodType`/method handle có thể giữ trực tiếp object kiểu tại runtime, không yêu cầu class khác có symbolic entry định danh hidden class bằng binary name.

**Bài 6.** Hidden class có tác dụng gì cho framework mà một named class tạo động không đáp ứng hoàn toàn?

**Đáp án:** Nó cho phép framework tạo class có hành vi thực thi nhưng không cung cấp tên nhị phân để các class khác tham chiếu symbolic, đồng thời hỗ trợ lựa chọn về vòng đời và cơ chế truy cập theo API. Đây là lựa chọn kiến trúc; không nên áp dụng chỉ vì muốn “ẩn” code.

## 14. Quy trình nhận diện khi đọc code/bytecode

Khi thấy một ví dụ hoặc công cụ dùng hidden class, hãy lần lượt hỏi:

1. **Class được tạo bằng API nào?** `Lookup.defineHiddenClass` tạo hidden class; `ClassLoader.defineClass` và `Lookup.defineClass` thường tạo named class theo hợp đồng riêng.
2. **Đang giữ gì?** Byte array, `Lookup`, `Class<?>`, `MethodHandle`, instance hay chỉ chuỗi tên? Chỉ chuỗi tên không đủ để tra hidden class.
3. **Đường gọi thuộc loại nào?** Gọi trực tiếp một symbolic owner/type trong constant pool, hay gọi method handle/reflective API hoặc interface thông thường?
4. **Giới hạn gặp phải ở tầng nào?** Không có binary name, không đủ lookup privilege, package của class bytes không phù hợp, hay sai path đến file?
5. **Tại sao cần hidden?** Sinh hành vi động theo hợp đồng framework, tránh lộ API danh nghĩa, quản lý vòng đời; nếu ứng dụng chỉ cần class bình thường thì không cần kỹ thuật này.
6. **Có đang phụ thuộc chi tiết triển khai không?** Không hardcode hậu tố runtime, không giả định tên mang dạng cố định hay một GC sẽ unload ngay.

Điều này giúp phân biệt **lỗi định danh symbolic** với **lỗi quyền truy cập** và **lỗi chạy chương trình**, vốn thường bị gom nhầm vào một nguyên nhân.

## 15. Tài liệu chính thức vẫn áp dụng

- **JEP 371 — Hidden Classes (Java 15):** https://openjdk.org/jeps/371
- **Java SE 21 — `java.lang.Class`, mục Hidden Classes:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- **Java SE 21 — `MethodHandles.Lookup.defineHiddenClass`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)
- **Java Virtual Machine Specification — Constant Pool, Class and Interface Resolution:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **JDK 15 Release Notes — JEP 371 Hidden Classes:** https://www.oracle.com/java/technologies/javase/15-relnote-issues.html

**Điểm cốt lõi:** hidden class **không thể là đối tượng được định danh theo tên trong constant pool của lớp khác** vì nó **không có binary name**. Nó vẫn là một class thực trong JVM với `Class<?>`, instance và members; code khác có thể dùng nó **gián tiếp** qua reference, interface, reflection và method handles theo quyền hợp lệ. Phân biệt rạch ròi hai ý này là cách hiểu đúng JEP 371 trên Java 15 và các JDK hiện đại.
