# Hai lớp cùng tên nhưng khác ClassLoader là hai kiểu khác nhau trong Java

## 1. Quy tắc định danh kiểu ở JVM

Trong Java, tên đầy đủ của một lớp như `com.example.Plugin` rất quan trọng, nhưng **chỉ biết tên lớp chưa đủ để xác định một kiểu ở runtime**. Với một lớp hoặc interface thông thường, JVM xác định danh tính bằng **cặp gồm tên nhị phân (binary name) và class loader đã định nghĩa lớp (defining class loader)**:

~~~text
Runtime type identity = (binary name, defining ClassLoader)
~~~

Ví dụ, giả sử hai loader độc lập thực sự định nghĩa bytecode cho `com.example.Plugin`:

~~~text
Loader A -- defineClass("com.example.Plugin", bytes) --> Class A
Loader B -- defineClass("com.example.Plugin", bytes) --> Class B

Class A.getName() == "com.example.Plugin"
Class B.getName() == "com.example.Plugin"

Class A != Class B
~~~

Kể cả hai mảng bytecode giống hệt nhau, JVM vẫn có thể tạo **hai kiểu runtime khác nhau** nếu chúng được định nghĩa bởi **hai defining loader khác nhau**. Đối tượng tạo từ kiểu thứ nhất không tự động là instance của kiểu thứ hai; cast giữa chúng có thể gây `ClassCastException`.

**Điều kiện quan trọng:** hai đối tượng `ClassLoader` khác nhau *không nhất thiết* sinh ra hai lớp khác nhau. Nếu cả hai **ủy quyền cho cùng một parent** và parent định nghĩa lớp, chúng có thể nhận về **chính một đối tượng `Class<?>`**. Chỉ khi có **hai định nghĩa runtime khác nhau** do hai defining loader khác nhau, kết luận “hai kiểu khác nhau” mới áp dụng.

Bài này giải thích cơ chế, ví dụ chạy được với Java 17+, khác biệt giữa initiating loader và defining loader, kết quả `instanceof` / `isInstance` / cast, trạng thái `static`, cũng như cách chẩn đoán lỗi trong plugin và application server.

## 2. Vì sao chỉ so sánh tên lớp là sai?

Trong mã nguồn Java, import `com.example.Plugin` có vẻ chỉ tới một kiểu. Tuy nhiên môi trường runtime có thể gồm nhiều miền tải lớp:

- Ứng dụng chính nạp API và dependency bằng application/system loader.
- Một container tạo loader riêng cho mỗi ứng dụng được triển khai.
- Mỗi plugin có loader riêng, có thể mang phiên bản thư viện khác nhau.
- Công cụ phát triển, test runner hoặc framework hot reload tạo loader mới khi mã thay đổi.
- Runtime chạy nhiều module layer có thể liên hệ các module với loader khác nhau.

Do đó hai đoạn code cùng thấy chuỗi `"com.example.Plugin"` vẫn có thể đang thao tác với hai đối tượng `Class` khác nhau.

Các phép quan sát cơ bản:

~~~java
Class<?> left = objectA.getClass();
Class<?> right = objectB.getClass();

boolean sameName = left.getName().equals(right.getName());
boolean sameType = left == right;

ClassLoader loaderA = left.getClassLoader();
ClassLoader loaderB = right.getClassLoader();
~~~

Đây là **mã minh họa trong một phương thức có sẵn hai đối tượng**, không phải chương trình độc lập.

- `sameName` trả lời: **tên nhị phân có giống nhau không?**
- `sameType` trả lời: **có đúng là một kiểu runtime không?**
- `getClassLoader()` cho biết loader định nghĩa kiểu. Đối với nhiều lớp lõi Java do bootstrap loader định nghĩa, kết quả là `null`.
- Không dùng `left.toString().equals(right.toString())` để xác định cùng kiểu: một số chuỗi in ra không mang đủ thông tin về defining loader.

Quy tắc này gắn với JVM và bộ xác minh kiểu, chứ không phải chỉ một thói quen đặt tên class của compiler.

## 3. Phân biệt defining loader và initiating loader

**Defining class loader** là loader thực sự **định nghĩa** một lớp bằng dữ liệu class file hoặc cơ chế định nghĩa hợp lệ tương ứng. Danh tính runtime của lớp gắn với defining loader đó.

**Initiating class loader** là loader tham gia khởi phát việc nạp lớp theo yêu cầu của JVM, kể cả khi công việc cuối cùng được ủy quyền cho loader khác.

Xét tình huống:

~~~text
ChildLoader.loadClass("example.Service")
        |
        v
ChildLoader ủy quyền -> ParentLoader.loadClass("example.Service")
                                 |
                                 v
                            ParentLoader định nghĩa
                                 |
                                 v
                  trả về cùng Class<?> cho ChildLoader
~~~

`ChildLoader` có thể là initiating loader của yêu cầu, nhưng **ParentLoader mới là defining loader** của `example.Service`. Khi đó `Service.class.getClassLoader()` (hoặc `loadedClass.getClassLoader()`) cho thấy defining loader là parent.

Các loader có thể duy trì quan hệ ủy quyền và cache kết quả để những lần tải sau trả về cùng `Class<?>`. Vì vậy câu “nạp lớp qua hai loader khác nhau” **không đủ** để suy ra có hai kiểu khác nhau.

### Child-first không phải mặc định

`ClassLoader.loadClass(String, boolean)` mặc định tìm lớp đã tải, thử parent hoặc bootstrap, rồi mới gọi `findClass` của loader hiện tại. Đây là chiến lược **parent-first delegation** phổ biến. Một custom loader có thể thay chiến lược tìm kiếm cho phạm vi được phép, chẳng hạn **child-first** khi cần cô lập thư viện của plugin.

Không được cho rằng cứ tạo `new ClassLoader(parent)` là đã cô lập toàn bộ lớp. Nếu nó không tự định nghĩa tên lớp đang xét và parent tìm thấy lớp ấy, nó thường trả về lớp do parent định nghĩa.

## 4. Ví dụ hoàn chỉnh Java 17+: hai class cùng tên, khác kiểu runtime

Ví dụ sau chủ động tạo **hai loader không dùng application loader làm parent** cho lớp mục tiêu. Cả hai đọc **cùng một file `Payload.class`** đã biên dịch; mỗi loader gọi `defineClass` để tạo một Class riêng. Ứng dụng vẫn có bản `Payload` do loader thông thường tải.

Tạo **hai file trong cùng thư mục**.

### File Payload.java

~~~java
public class Payload {
    private static int counter;

    public static int next() {
        return ++counter;
    }

    public String text() {
        return "hello";
    }
}
~~~

Lớp `Payload` có một constructor mặc định public, phương thức instance `text()` và trường static `counter`. Việc đặt tên file `Payload.java` đúng với tên lớp public là bắt buộc.

### File LoaderIdentityDemo.java

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    static final class IsolatedLoader extends ClassLoader {
        private final byte[] payloadBytes;

        IsolatedLoader(byte[] payloadBytes) {
            super(null); // Parent là bootstrap, tránh ủy quyền về app loader
            this.payloadBytes = payloadBytes.clone();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("Payload")) {
                throw new ClassNotFoundException(name);
            }

            return defineClass(
                    name, payloadBytes, 0, payloadBytes.length
            );
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("Payload.class"));

        Class<?> app = Payload.class;
        Class<?> first = new IsolatedLoader(bytes).loadClass("Payload");
        Class<?> second = new IsolatedLoader(bytes).loadClass("Payload");

        ClassLoader delegating = new ClassLoader(
                LoaderIdentityDemo.class.getClassLoader()) { };
        Class<?> delegated = delegating.loadClass("Payload");

        System.out.println("same name: "
                + app.getName().equals(first.getName()));
        System.out.println("app == first: " + (app == first));
        System.out.println("first == second: " + (first == second));
        System.out.println("delegated == app: " + (delegated == app));

        Object value = first.getDeclaredConstructor().newInstance();

        System.out.println("first.isInstance: "
                + first.isInstance(value));
        System.out.println("app.isInstance: "
                + app.isInstance(value));
        System.out.println("second.isInstance: "
                + second.isInstance(value));

        System.out.println("invoke method: "
                + first.getMethod("text").invoke(value));

        try {
            Payload cast = (Payload) value;
            System.out.println(cast.text());
        } catch (ClassCastException exception) {
            System.out.println("cast: ClassCastException");
        }

        System.out.println("app.next: " + Payload.next());
        System.out.println("first.next: "
                + first.getMethod("next").invoke(null));
        System.out.println("app.next again: " + Payload.next());
        System.out.println("first.next again: "
                + first.getMethod("next").invoke(null));
        System.out.println("second.next: "
                + second.getMethod("next").invoke(null));

        System.out.println("unnamed modules equal: "
                + (first.getModule() == second.getModule()));
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 17 trở lên, mở terminal **tại thư mục chứa hai file**:

~~~bash
javac --release 17 Payload.java LoaderIdentityDemo.java
java LoaderIdentityDemo
~~~

Chương trình đọc `Payload.class` bằng đường dẫn tương đối, nên cần chạy từ đúng thư mục có file đó. Không cần framework, dependency hoặc Java agent.

**Stdout chính xác khi chạy như trên với JVM Java 17+ thông thường:**

~~~text
same name: true
app == first: false
first == second: false
delegated == app: true
first.isInstance: true
app.isInstance: false
second.isInstance: false
invoke method: hello
cast: ClassCastException
app.next: 1
first.next: 1
app.next again: 2
first.next again: 2
second.next: 1
unnamed modules equal: false
~~~

### Phân tích kết quả từng nhóm

**1. Cùng tên nhưng không cùng Class.** `app.getName().equals(first.getName())` là `true` vì cả hai có binary name `Payload`. Tuy nhiên `app == first` và `first == second` đều `false` vì ba lớp được định nghĩa bởi ba defining loader khác nhau.

**2. Parent delegation có thể dẫn tới cùng kiểu.** `delegating` là loader mới với parent chính là loader của `LoaderIdentityDemo`. Nó không tự định nghĩa `Payload` nên ủy quyền cho parent; `delegated == app` là `true`.

**3. Đối tượng chỉ là instance của đúng kiểu.** `value` được tạo bằng constructor của `first`. Vì vậy `first.isInstance(value)` đúng, còn `app.isInstance(value)` và `second.isInstance(value)` đều sai.

**4. Reflection không xóa đi danh tính kiểu.** Gọi `first.getMethod("text").invoke(value)` thành công vì phương thức thuộc `first` và receiver cũng thuộc `first`. Nó trả về `String`, một kiểu lõi chia sẻ được. Nhưng ép kiểu `(Payload) value` yêu cầu `Payload` được tham chiếu bởi code ứng dụng, tức bản `app`; JVM phát hiện khác kiểu và ném `ClassCastException`.

**5. Mỗi lớp có static state của riêng mình.** `counter` tồn tại riêng trong `app`, `first` và `second`. Các lời gọi `next()` cho ra các chuỗi độc lập: `1, 2` ở `app`; `1, 2` ở `first`; `1` ở `second`. Điều này phản ánh trạng thái static gắn với từng lớp runtime đã được định nghĩa và khởi tạo.

**6. Unnamed module cũng riêng theo loader.** Trong Java 9+, mỗi class loader có unnamed module tương ứng. Vì vậy `first.getModule() == second.getModule()` là `false` dù hai class có cùng binary name và bytecode.

Ví dụ này không cố gắng định nghĩa lại các lớp có tên thuộc `java.*`. Custom loader vẫn ủy quyền nạp `java.lang.Object` và các lớp Java nền tảng cho bootstrap loader. JVM có hạn chế bảo vệ đối với một số tên/package được phép định nghĩa.

## 5. Tại sao phải gọi defineClass thật sự?

Phương thức `findClass` trong ví dụ chứa:

~~~java
return defineClass(name, payloadBytes, 0, payloadBytes.length);
~~~

Đây là nơi loader **định nghĩa Class runtime từ dữ liệu bytecode**. Tên `name` phải phù hợp với tên nhị phân thực sự trong class file; cố lấy bytes của `Payload` nhưng đổi tên thành `Other` sẽ không tạo ra một lớp `Other` hợp lệ một cách tùy ý. JVM kiểm tra nhất quán và có thể ném `NoClassDefFoundError` hoặc lỗi định nghĩa lớp thích hợp.

Ngược lại, code sau thường **không** tạo kiểu mới:

~~~java
ClassLoader app = Payload.class.getClassLoader();
ClassLoader childA = new ClassLoader(app) { };
ClassLoader childB = new ClassLoader(app) { };

Class<?> a = childA.loadClass("Payload");
Class<?> b = childB.loadClass("Payload");

System.out.println(a == b); // true nếu cùng delegate tới bản Payload của app
~~~

Đây là **đoạn mã minh họa**, giả sử `Payload` đã có trên application class path, và loader ẩn danh không override `loadClass` / `findClass`. `childA` và `childB` là hai đối tượng loader khác nhau, nhưng **cả hai nhận về cùng Class từ parent**.

Một loader cũng không thể tùy ý định nghĩa cùng binary name nhiều lần trong cùng namespace đã sử dụng thành công. Lặp một định nghĩa trái phép có thể gây `LinkageError` vì JVM áp đặt sự nhất quán trong việc định nghĩa lớp.

## 6. Class.isInstance, instanceof, cast và reflection

Giả sử một đối tượng được tạo bằng bản `Plugin` do loader A định nghĩa:

| Thao tác | Ý nghĩa với hai định nghĩa `Plugin` độc lập |
| --- | --- |
| `pluginA.getName().equals(pluginB.getName())` | Có thể `true` |
| `pluginA == pluginB` | `false` |
| `pluginA.equals(pluginB)` | `false`, vì `Class` phản ánh danh tính kiểu |
| `pluginA.isInstance(objectA)` | `true` với đúng đối tượng |
| `pluginB.isInstance(objectA)` | `false` nếu hai kiểu không có quan hệ tương thích thích hợp |
| Cast `(PluginB) objectA` | Thông thường `ClassCastException` |
| `pluginA.isAssignableFrom(pluginB)` | `false` với hai lớp hoàn toàn độc lập |
| `pluginA.getDeclaredConstructor().newInstance()` | Tạo instance đúng lớp do A định nghĩa, nếu constructor được phép gọi |

**Đừng suy luận về khả năng cast chỉ bằng cách so sánh tên.** Thử nghiệm `Class.isInstance(Object)` hoặc `Class.isAssignableFrom(Class<?>)` trực tiếp trên những `Class` cụ thể.

Một class A có thể là subtype của một interface chung `api.Service` do parent loader định nghĩa, và một class B khác cũng có thể implement **chính interface chung ấy**. Khi đó cả hai object có thể cast sang **`api.Service` chung**, dù hai implementation không cast được lẫn nhau. Đây là thiết kế quan trọng cho hệ thống plugin.

### Kiểu thành viên và mảng

Tên nhị phân của nested class có thể chứa ký tự `$`, ví dụ `example.Outer$Inner`. Quy tắc danh tính kiểu vẫn sử dụng **toàn bộ binary name + defining loader**. Ký tự `$` tự nó không biểu thị một namespace loader khác.

Với kiểu mảng, JVM tạo array class theo cơ chế đặc biệt: `getClassLoader()` của mảng reference tương ứng với loader của element type. Ví dụ nếu hai phiên bản `Plugin` thuộc hai loader khác nhau, hai kiểu mảng `Plugin[]` tương ứng cũng không phải cùng kiểu runtime. Mảng có element primitive như `int[]` được bootstrap biểu diễn với loader `null` theo API.

## 7. Hai bộ static state, hai lượt class initialization

Mỗi class runtime có trạng thái trường static và chu trình khởi tạo riêng. Trong ví dụ, một tên `Payload` được định nghĩa ba lần nên tồn tại ba biến `counter` khác nhau.

Xét một lớp minh họa:

~~~java
public class SessionCounter {
    private static int count = initialize();

    private static int initialize() {
        System.out.println("Initializing SessionCounter");
        return 0;
    }

    public static int next() {
        return ++count;
    }
}
~~~

Nếu loader A và B thực sự định nghĩa hai bản `SessionCounter` từ cùng bytecode, mỗi bản có thể chạy class initializer `<clinit>` của chính mình khi được sử dụng tích cực lần đầu. Như vậy log `Initializing SessionCounter` có thể xuất hiện **một lần cho A và một lần cho B**. Hai chuỗi đếm `count` là độc lập.

Phân biệt đúng hai mốc:

- **Load/link** class không bắt buộc thực thi static initializer.
- **Initialize** thực hiện quy trình khởi tạo lớp theo quy định, tối đa một lần khởi tạo thành công đối với mỗi Class runtime.
- Tạo nhiều instance của cùng Class không làm `<clinit>` chạy lại.
- Định nghĩa class mới qua loader khác có thể có static state và quá trình khởi tạo riêng.

Điều này ảnh hưởng đến singleton static, cache static, logger registry, JDBC driver registry, thread-local registry hoặc thư viện có cờ `initialized`. Một “singleton” dựa trên trường static thực tế thường chỉ duy nhất **trong phạm vi một định nghĩa class**, không phải một singleton tuyệt đối cho toàn JVM khi có nhiều loader.

## 8. Runtime package cũng phụ thuộc vào loader

Ngoài type identity, defining loader còn tham gia xác định **runtime package**: hai class cùng tên package trong source nhưng do loader khác nhau định nghĩa không mặc nhiên có quyền truy cập package-private của nhau. Ví dụ truy cập package-private được kiểm tra ở bài chuyên về runtime package; điểm cần nhớ ở đây là **cùng source package không bảo đảm cùng runtime package**.

## 9. Phân biệt ClassNotFoundException, ClassCastException và LinkageError

Những lỗi này xảy ra ở các khâu khác nhau:

| Hiện tượng | Nguyên nhân thường gặp |
| --- | --- |
| `ClassNotFoundException` | API tìm theo tên không tìm được class. |
| `ClassCastException` | Object không tương thích với runtime type đích, kể cả khi tên class trùng. |
| `NoClassDefFoundError` | JVM không định nghĩa được class cần khi liên kết/chạy hoặc class initialization trước đó thất bại. |
| `LinkageError` | Vi phạm quy tắc liên kết, chẳng hạn loading constraint yêu cầu cùng kiểu. |

Hai định nghĩa cùng tên **không tự động** gây `LinkageError`; hãy xác định thao tác phát sinh lỗi trước khi xử lý.

## 10. Thiết kế plugin đúng cách với API chung

Một hệ thống plugin cần phân biệt **API contract dùng chung** với **implementation riêng từng plugin**. Host và các loader plugin cùng tham chiếu một interface `api.Plugin` đã được định nghĩa bởi shared/parent loader, trong khi mỗi plugin có thể tự định nghĩa `impl.*`. Nếu mỗi plugin tự nạp bản sao `api.Plugin` của riêng mình, phép cast sang interface của host vẫn có thể thất bại.

Khi cần cô lập các model không thể chia sẻ trực tiếp, chuyển đổi sang DTO thuộc API chung hoặc giao thức dữ liệu độc lập. Bài thiết kế ranh giới nhiều loader triển khai các cấu hình parent-first/child-first, ví dụ chạy được, versioning và vòng đời.

## 11. Các trường hợp có thể thấy cùng loader nhưng khác kết quả tìm lớp

### Một loader có thể biết nhiều Class, nhưng không đồng nghĩa tự định nghĩa tất cả

Trong Java, khi gọi `ChildLoader.loadClass(name)`, kết quả có thể là Class do parent định nghĩa. Trong trường hợp đó loader con tham gia quá trình nạp nhưng `Class.getClassLoader()` không trỏ về nó.

### Một loader không định nghĩa hai phiên bản cùng tên song song

Nếu muốn tải phiên bản mới của cùng binary name trong một plugin có bộ nạp riêng, thường tạo một **loader mới** và điều phối chuyển giao vòng đời. Cố gọi `defineClass` lần hai với cùng tên trong loader cũ không phải cách hot reload hoạt động.

### Cùng file class không phải điều kiện “cùng Class”

Hai loader đọc đúng cùng `Payload.class` vẫn có thể định nghĩa hai Class runtime độc lập. Ngược lại, hai đường class path khác nhau cùng tham chiếu một Class đã có thể cho cùng đối tượng Class nhờ ủy quyền.

### Tên lớp và nội dung bytecode đều có giới hạn

JVM yêu cầu class file hợp lệ và ràng buộc tên nhất quán. Hai loader có thể định nghĩa các bytecode **khác nhau** cho cùng binary name, dẫn tới khác API, dữ liệu hoặc hành vi; ngoài `ClassCastException` còn có thể gặp `NoSuchMethodError`, `NoSuchFieldError` hoặc lỗi liên kết nếu các thành phần kỳ vọng phiên bản không phù hợp.

## 12. Class.forName với loader cụ thể

Khi cần chọn loader, sử dụng overload nhận ba tham số:

~~~java
Class<?> type = Class.forName(
        "com.example.Plugin",
        false,
        pluginLoader
);
~~~

Đây là **đoạn minh họa**, giả sử `pluginLoader` là biến ClassLoader có thật và lớp `com.example.Plugin` tồn tại trong phạm vi tìm kiếm.

- Tham số đầu là **binary name** của lớp thông thường.
- Tham số `false` không yêu cầu khởi tạo lớp ngay tại lời gọi.
- Tham số cuối là loader **được dùng để yêu cầu nạp**; kết quả có thể thuộc parent nếu có ủy quyền.

Khi truyền `true` thay vì `false`, API yêu cầu thực hiện class initialization nếu cần. **Initialization không làm hai định nghĩa của cùng tên trở thành một kiểu**.

Cẩn trọng với lời gọi không truyền loader:

~~~java
Class<?> type = Class.forName("com.example.Plugin");
~~~

Overload này sử dụng class loader của caller theo quy tắc API và có yêu cầu khởi tạo kiểu; trong plugin/container phức tạp, nó có thể không tìm lớp mà một plugin loader riêng có thể tìm được. Không được đồng nhất “loader của caller” với “system class loader” hoặc TCCL trong mọi môi trường.

## 13. Mảng, reflection, serialization và module

### Mảng

Nếu `Class<?> a` và `Class<?> b` là hai lớp reference có cùng binary name nhưng khác defining loader, hai kiểu mảng một chiều của chúng cũng tách biệt. JVM tạo array class theo thành phần được định nghĩa; không có cách cast mảng `A[]` sang `B[]` chỉ bằng việc hai thành phần trùng tên.

### Reflection

Reflection hoạt động trên **đối tượng Class cụ thể**. Muốn gọi phương thức từ kiểu A trên object được A tạo, dùng `a.getMethod(...)` và receiver tương ứng. Nếu lấy `b.getMethod(...)` từ kiểu B rồi áp dụng lên object A không tương thích, lời gọi không tự “hợp nhất” hai định nghĩa; API reflection báo lỗi thích hợp.

### Serialization

Serialization Java truyền thống lưu thông tin về tên lớp và cấu trúc dữ liệu, nhưng khi giải tuần tự hóa phải **phân giải tên thành Class runtime** thông qua cơ chế phân giải lớp. Chọn loader sai có thể dẫn tới không tìm thấy lớp hoặc khác loại; `serialVersionUID` giống nhau không tự xóa ranh giới danh tính kiểu. Với ứng dụng plugin, thường cần giao thức dữ liệu trung lập hoặc quy trình giải mã có chọn loader phù hợp.

### JPMS

Từ Java 9, mỗi Class thuộc một runtime module; gọi `type.getModule()` để quan sát. Hai Class runtime từ hai loader khác nhau có thể thuộc hai unnamed module khác nhau; named modules còn có các quy tắc đọc module (`reads`), xuất package (`exports`), mở package (`opens`) và class loading riêng. Không suy rằng module name bằng nhau tự động làm hai Class của hai loader trở thành cùng kiểu.

### Garbage collection và khả năng dỡ lớp

Một lớp có thể được unload khi đáp ứng điều kiện của JVM, đặc biệt liên quan tới khả năng thu hồi loader đã định nghĩa nó và những tham chiếu còn tồn tại. Giữ tham chiếu lâu dài tới Class, ClassLoader, thread, TCCL, static cache hay object của plugin có thể giữ loader cũ sống và ngăn dỡ các lớp sau reload. Không thể “thay bytecode” trong một Class cũ bằng cách xóa file .class khi loader còn sống.

## 14. Checklist điều tra lỗi “cùng tên mà không cast được”

Khi có `ClassCastException` hoặc lỗi liên kết đáng ngờ, đừng chỉ nhìn chuỗi tên class trong stack trace. Thu thập bằng chứng từ **hai đối tượng Class** thực tế:

~~~java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
~~~

Đây là **đoạn minh họa trong một lớp Java**, không phải chương trình độc lập.

Các bước xử lý:

1. **Lấy hai Class thực tế:** bên tạo object và bên đang cast/call. Khi có thể, so sánh `left == right`.
2. **In binary name:** `left.getName()` và `right.getName()`. Hai tên có thể giống nhau.
3. **In defining loader:** `left.getClassLoader()` và `right.getClassLoader()`. Chú ý loader của lớp lõi có thể là `null`.
4. **In module:** `getModule()`; dùng thêm nguồn JAR/module hoặc log class loading nếu cần.
5. **Kiểm tra đồ thị loader:** parent-first hay child-first, plugin isolation, app server deployment, TCCL.
6. **Tìm bản sao API/JAR:** API host có bị đóng gói riêng trong plugin? Có class cùng package/name được định nghĩa từ hai vị trí không?
7. **Xác định lỗi đang xảy ra ở bước nào:** tìm lớp, định nghĩa, liên kết, khởi tạo static, reflection hay cast.
8. **Sửa phạm vi chia sẻ kiểu:** thống nhất loader của API chung, thay loader khi hot reload, hoặc dùng DTO/protocol cho ranh giới cách ly.

Trong OpenJDK/HotSpot, có thể bật JVM unified logging để quan sát lớp nào được load và nguồn nào cung cấp dữ liệu:

~~~bash
java -Xlog:class+load=info LoaderIdentityDemo
~~~

Lệnh này áp dụng cho ví dụ sau khi đã biên dịch, và log JVM phụ thuộc phiên bản/môi trường, **không có stdout cố định**. Một số log không cho biết toàn bộ quan hệ initiating/defining loader; kết hợp log với `Class.getClassLoader()`.

## 15. Những ngộ nhận thường gặp

| Ngộ nhận | Điều đúng cần nhớ |
| --- | --- |
| “Cùng tên đầy đủ là cùng kiểu Java” | Runtime type identity dùng binary name **và defining loader** |
| “Hai biến ClassLoader khác nhau luôn cho hai Class khác nhau” | Chúng có thể ủy quyền và nhận cùng Class từ parent |
| “File .class có hash giống nhau nên cast được” | Bytecode giống nhau không vượt qua ranh giới defining loader |
| “`obj.getClass().getName()` giống là cast an toàn” | Dùng `isInstance` / `isAssignableFrom` và định danh Class thực |
| “Đổi TCCL đổi luôn loader đã định nghĩa object” | TCCL chỉ đổi loader ngữ cảnh cho API dùng nó; không sửa defining loader của Class có sẵn |
| “Singleton static luôn duy nhất cho cả JVM” | Static state tách theo Class runtime; mỗi loader định nghĩa riêng có trạng thái riêng |
| “Đưa API JAR vào mọi plugin là tốt” | Dễ tạo nhiều bản API và làm cast phía host thất bại |
| “Lỗi cùng tên chỉ xảy ra khi cast” | JVM còn áp đặt loader constraints, có thể lỗi ở lúc liên kết |
| “Nạp lại file class bằng loader cũ là reload an toàn” | Thường cần loader mới và dỡ bỏ tham chiếu tới loader cũ |
| “Chuỗi `ClassLoader.toString()` xác định toàn bộ kiểu” | Dùng chính đối tượng `Class<?>` và defining loader khi debug |

## 16. Câu hỏi tự kiểm tra

1. **Hai đối tượng loader A và B gọi `loadClass("X")`, đều được parent trả về cùng `Class<?>`. Có hai kiểu X không?** Không; chỉ có một Class được parent định nghĩa trong kịch bản này.
2. **Hai loader A/B gọi `defineClass` hợp lệ từ cùng bytes của X. `AClass.getName().equals(BClass.getName())` có thể true không?** Có; tên bằng nhau nhưng `AClass == BClass` vẫn false.
3. **Một object là instance của X do loader A định nghĩa, có tự nhiên cast sang X do B định nghĩa được không?** Không. Hai kiểu độc lập; cast có thể gây `ClassCastException`.
4. **Static int counter trong hai Class runtime X có dùng chung biến không?** Không. Mỗi định nghĩa class có static state riêng.
5. **Hai class khác loader nhưng cùng package trong source có là cùng runtime package không?** Không, vì runtime package còn phụ thuộc defining loader.
6. **Vì sao host và plugin nên dùng chung một interface API do parent loader định nghĩa?** Để cả hai cùng nhận một kiểu runtime và cast/call qua interface đó được kiểm tra nhất quán.
7. **Nếu in `obj.getClass().getClassLoader()`, ta đang nhìn initiating hay defining loader?** Defining loader.
8. **Nếu class literal `X.class` của host và `loader.loadClass("X")` trả hai Class khác nhau, nên kiểm tra gì?** Kiểm tra binary name, defining loaders, parent chain, path/JAR/module, isolation và có bản sao API hay không.

## Tài liệu chuẩn

- **JVM Specification Java 17, `5.3` – Creation and Loading** (định danh runtime, defining/initiating loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVM Specification Java 17, `5.3.4` – Loading Constraints**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- **Java Language Specification Java 17, `12.2` – Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- **Java SE 17 API, java.lang.ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API, java.lang.Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 API, java.lang.reflect.Method**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
