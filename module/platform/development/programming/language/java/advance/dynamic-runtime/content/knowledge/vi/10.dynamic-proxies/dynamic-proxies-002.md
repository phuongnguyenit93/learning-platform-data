# 10.2 Tạo proxy bằng `Proxy.newProxyInstance` và lựa chọn bộ nạp lớp

**Dynamic proxy** của Java cho phép tạo một đối tượng triển khai một hoặc nhiều **interface** tại runtime. Khi client gọi method trên đối tượng này, JVM chuyển lời gọi đến `InvocationHandler` do ta cung cấp. Đây là cơ chế thường dùng để tạo lớp bọc logging, đo thời gian, kiểm tra quyền, gọi RPC, adapter plugin hoặc facade cho một service dựa trên interface.

Điểm quan trọng của bài: **`ClassLoader` truyền vào `Proxy.newProxyInstance` phải nhìn thấy đúng những `Class<?>` của các interface cần triển khai**, chứ không chỉ tìm được một tên class giống nhau. Trong ứng dụng một bộ nạp lớp, chọn loader thường đơn giản. Với plugin, container, ứng dụng nhiều module hoặc nhiều class loader, lựa chọn sai có thể làm proxy không tạo được hoặc đối tượng không ép kiểu về interface mà caller đang dùng.

Các ví dụ sau sử dụng **Java 17+**, API chuẩn trong `java.lang.reflect`.

## 1. Ba tham số của `Proxy.newProxyInstance`

Chữ ký:

~~~java
public static Object newProxyInstance(
    ClassLoader loader,
    Class<?>[] interfaces,
    InvocationHandler h)
~~~

| Tham số | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `loader` | Class loader được chọn để **định nghĩa lớp proxy sinh ra** | Phải phân giải được từng interface thành **đúng đối tượng `Class`**. Giá trị `null` biểu thị bootstrap class loader, không phải cơ chế tự tìm loader phù hợp |
| `interfaces` | Danh sách interface mà lớp proxy sẽ triển khai, **đúng thứ tự** | Phải là các interface hợp lệ, không lặp, không hidden, không sealed; một số tổ hợp method và access không được phép |
| `h` | `InvocationHandler` xử lý các lời gọi method trên proxy | Không được `null`. Trả về đối tượng phù hợp kiểu trả về, xử lý cả các method `Object` và default method nếu cần |

Ví dụ mẫu khi chỉ có một contract mà ứng dụng có thể nhìn thấy:

~~~java
ClassLoader loader = Service.class.getClassLoader();
Service proxy = (Service) Proxy.newProxyInstance(
        loader,
        new Class<?>[] { Service.class },
        handler);
~~~

Đoạn này là **mẫu minh họa**, giả sử `Service` và `handler` đã được khai báo; chương trình đầy đủ có thể chạy nằm ở phần 6.

Kết quả của `newProxyInstance` có kiểu trả về tĩnh là `Object` nhưng đối tượng runtime triển khai những interface được liệt kê, nên có thể cast sang interface tương ứng. Lớp proxy sinh ra là một **class cuối cùng (`final`)**, kế thừa `java.lang.reflect.Proxy`. Nó không phải subclass của một class nghiệp vụ tùy ý.

## 2. Đường đi của một lời gọi

~~~text
Client code
   │  Greeting greeting = (Greeting) proxy
   │  greeting.greet("Java")
   ▼
Lớp proxy do JVM tạo
   │  implements Greeting
   │  đóng gói Method + Object[] args
   ▼
InvocationHandler.invoke(proxy, method, args)
   │  tra cứu / ghi log / kiểm tra / gọi đối tượng thật
   │  return "Hello, Java"
   ▼
Lớp proxy kiểm tra/ép kiểu kết quả
   │
   ▼
Client nhận "Hello, Java"
~~~

Handler có chữ ký:

~~~java
Object invoke(Object proxy, java.lang.reflect.Method method, Object[] args)
        throws Throwable;
~~~

- `proxy` chính là đối tượng proxy đang bị gọi; **đừng** gọi `method.invoke(proxy,args)` một cách vô điều kiện trong handler, vì điều đó có thể gọi lại handler và gây đệ quy vô hạn.
- `method` mô tả method được gọi qua interface (hoặc một trong ba method đặc biệt của `Object`).
- `args` có thể là **`null` nếu method không có tham số**; tham số primitive như `int` được đóng hộp thành wrapper (`Integer`, v.v.).
- Kết quả trả về phải phù hợp với kiểu return của interface. Với return primitive như `int`, handler cần trả wrapper tương ứng; trả `null` dẫn tới `NullPointerException` khi proxy cố unbox. Trả giá trị không tương thích có thể dẫn tới `ClassCastException`.
- Handler có thể ném exception. Checked exception không tương thích với `throws` của method interface sẽ được proxy bọc bằng `UndeclaredThrowableException`.

**Tách vai trò:** `ClassLoader` quyết định **có tạo và liên kết được class proxy không**; `InvocationHandler` quyết định **mỗi lời gọi thực hiện công việc gì**. Loader đúng không bảo đảm handler đúng.

## 3. Chọn class loader: nguyên tắc cốt lõi

Với từng interface `intf` trong mảng `interfaces`, JVM yêu cầu:

~~~java
Class.forName(intf.getName(), false, loader) == intf
~~~

Đây là **điều kiện cùng định danh kiểu**, không chỉ so tên. Hai class có cùng tên nhị phân nhưng được định nghĩa bởi hai loader khác nhau có thể là hai kiểu Java khác nhau. Trong Java, định danh kiểu gắn với **tên class và defining class loader**.

- `Class.forName(name, false, loader)` tìm/lấy lớp bằng loader được chỉ định, nhưng không chủ động khởi tạo class do `initialize=false`. Loader vẫn có thể thực hiện việc nạp/liên kết cần thiết.
- Phép so sánh `==` kiểm tra đúng đối tượng `Class<?>`.
- Một **child loader** có thể nhìn thấy interface do **parent loader** định nghĩa thông qua cơ chế delegation. Vì vậy loader của proxy **không buộc** chính là loader đã định nghĩa interface; chỉ cần phân giải ra đúng `Class`.
- Nếu loader trả về một bản interface cùng tên nhưng khác identity, điều kiện trên **không đạt**.
- Ngoài các interface, những kiểu được tham chiếu trong chữ ký **public method** của các interface và superinterface cũng cần được loader nhìn thấy đúng cách.

Với một interface, mặc định hợp lý là **loader gắn với chính interface**:

~~~java
ClassLoader chosen = MyApi.class.getClassLoader();
Object proxy = Proxy.newProxyInstance(
        chosen, new Class<?>[] { MyApi.class }, handler);
~~~

`MyApi.class.getClassLoader()` **có thể trả `null`**, ví dụ với class do bootstrap loader định nghĩa. Khi đó `null` có ý nghĩa hợp lệ đối với các interface mà bootstrap loader thực sự thấy; nó **không** phải “chọn loader hệ thống” hoặc “chọn theo thread”.

## 4. So sánh những nguồn chọn loader thường gặp

| Cách lấy loader | Khi hữu ích | Điểm phải kiểm tra |
| --- | --- | --- |
| `SomeInterface.class.getClassLoader()` | Một interface hoặc nhiều interface cùng vùng visibility | Interface khác, kiểu trong public signatures, và module access có tương thích không? |
| `Thread.currentThread().getContextClassLoader()` (TCCL) | Framework/plugin container chủ động đặt loader theo ngữ cảnh thread | TCCL có thể `null`, khác nhau giữa thread và không nhìn thấy interface thật; **phải kiểm tra** trước khi dùng |
| `SomeImplementation.class.getClassLoader()` | Loader triển khai đã được xác định và đồng thời nhìn thấy toàn bộ contracts | Có thể nhìn thấy implementation nhưng không phân giải đúng `Class<?>` contract của caller |
| `ClassLoader.getSystemClassLoader()` | Ứng dụng đơn giản toàn bộ chạy dưới system/application loader | Không mặc định nhìn thấy kiểu ở loader con/isolated hoặc lớp plugin |
| `new ClassLoader(parent) { ... }` | Tạo một vùng namespace riêng, chủ đích cho proxy với delegation phù hợp | Được phép tạo proxy khi child nhìn thấy contract; proxy class do child định nghĩa làm thay đổi lifecycle và retention |
| `null` | Interface và signature types đều được bootstrap loader nhìn thấy | Không thể proxy interface của ứng dụng chỉ vì đặt `null`; thường thất bại với visibility |

**Không có một lựa chọn luôn đúng cho mọi ứng dụng.** Khi có nhiều interface, cần **một loader duy nhất phân giải được tất cả** về đúng `Class` tương ứng, đồng thời nhìn thấy các kiểu liên quan trong chữ ký public. Không nhất thiết là loader của interface đầu tiên.

Với hệ thống plugin, một cấu trúc thường dùng là:

~~~text
Application / shared API loader
    └── định nghĩa PluginService và DTO chung
         ├── Plugin A loader (delegates to API loader)
         └── Plugin B loader (delegates to API loader)

Proxy sử dụng:
  - shared API loader nếu chỉ cần các contract chung;
  - một loader tương thích cụ thể nếu phải proxy thêm
    interface riêng mà loader ấy thật sự nhìn thấy.
~~~

Nếu hai interface chỉ được định nghĩa trong **hai loader độc lập** và không có loader nào nhìn thấy cả hai đúng identity, hãy thiết kế lại biên giới module/plugin hoặc cung cấp loader phù hợp; việc chuyển sang TCCL một cách mù quáng không giải quyết được điều kiện identity.

## 5. Bộ kiểm tra loader trước khi tạo proxy

Có thể kiểm tra sớm và đưa ra thông báo rõ ràng:

~~~java
static boolean sees(ClassLoader loader, Class<?> type) {
    try {
        return Class.forName(type.getName(), false, loader) == type;
    } catch (ClassNotFoundException ex) {
        return false;
    }
}
~~~

Đây là **helper minh họa**, không phải chương trình chạy độc lập. Kiểm tra này trả lời câu hỏi loader có nhìn thấy **đúng interface class** hay không; các hạn chế khác như non-public interface, sealed interface, method signatures hoặc module boundaries vẫn có thể làm tạo proxy thất bại.

Nếu loader không thấy lớp, chẩn đoán từ những quan sát thực tế:

~~~java
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(Thread.currentThread().getContextClassLoader());
System.out.println(type.getModule().getName());
~~~

Đoạn này giả sử biến `type` đã có giá trị. `ClassLoader.toString()` chỉ hỗ trợ nhận diện khi debug; **không** so các loader bằng chuỗi đó để quyết định cùng identity. Dùng `==` cho loader hoặc `Class<?>` khi cần so đối tượng.

## 6. Ví dụ Java 17 hoàn chỉnh: tạo proxy và kiểm chứng loader

Lưu **toàn bộ** mã bên dưới vào file **`ProxyLoaderDemo.java`** trong một thư mục trống. Mọi interface đều khai báo `public` bên trong class `ProxyLoaderDemo` để bên ngoài class cũng có thể sử dụng khi cần.

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public final class ProxyLoaderDemo {
    public interface Greeting {
        String greet(String name);
        default String farewell() { return "See you"; }
    }

    public interface Counter {
        int count();
    }

    public static void main(String[] args) {
        ClassLoader contractLoader = Greeting.class.getClassLoader();
        InvocationHandler handler = (proxy, method, callArgs) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreetingProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == callArgs[0];
                    default -> throw new UnsupportedOperationException(method.toString());
                };
            }
            if (method.isDefault()) {
                return InvocationHandler.invokeDefault(proxy, method, callArgs);
            }
            return switch (method.getName()) {
                case "greet" -> "Hello, " + callArgs[0];
                case "count" -> 3;
                default -> throw new UnsupportedOperationException(method.toString());
            };
        };

        Object object = Proxy.newProxyInstance(
                contractLoader, new Class<?>[] {Greeting.class, Counter.class}, handler);
        Greeting greeting = (Greeting) object;
        Counter counter = (Counter) object;

        System.out.println("greet: " + greeting.greet("Java"));
        System.out.println("default: " + greeting.farewell());
        System.out.println("count: " + counter.count());
        System.out.println("proxy class: " + Proxy.isProxyClass(object.getClass()));
        System.out.println("same loader: " + (object.getClass().getClassLoader() == contractLoader));
        System.out.println("same handler: " + (Proxy.getInvocationHandler(object) == handler));
        System.out.println("interfaces: " + object.getClass().getInterfaces().length);
        System.out.println("toString: " + object);
        System.out.println("equals self: " + object.equals(object));
        System.out.println("equals other: " + object.equals(new Object()));

        ClassLoader child = new ClassLoader(contractLoader) {};
        Object childObject = Proxy.newProxyInstance(
                child, new Class<?>[] {Greeting.class}, handler);
        System.out.println("child sees interface: " +
                (loadSameClass(child, Greeting.class)));
        System.out.println("child is proxy loader: " +
                (childObject.getClass().getClassLoader() == child));

        ClassLoader isolated = new ClassLoader(null) {};
        System.out.println("isolated sees interface: " +
                loadSameClass(isolated, Greeting.class));
        try {
            Proxy.newProxyInstance(isolated, new Class<?>[] {Greeting.class}, handler);
            throw new AssertionError("Expected visibility error");
        } catch (IllegalArgumentException expected) {
            System.out.println("isolated proxy: " + expected.getClass().getSimpleName());
        }

        try {
            Proxy.newProxyInstance(contractLoader,
                    new Class<?>[] {Greeting.class, Greeting.class}, handler);
            throw new AssertionError("Expected duplicate-interface error");
        } catch (IllegalArgumentException expected) {
            System.out.println("duplicate interface: " + expected.getClass().getSimpleName());
        }
    }

    private static boolean loadSameClass(ClassLoader loader, Class<?> type) {
        try {
            return Class.forName(type.getName(), false, loader) == type;
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }
}
~~~

Biên dịch ở mức ngôn ngữ Java 17, sau đó chạy:

~~~bash
javac --release 17 ProxyLoaderDemo.java
java ProxyLoaderDemo
~~~

**Stdout:**

~~~text
greet: Hello, Java
default: See you
count: 3
proxy class: true
same loader: true
same handler: true
interfaces: 2
toString: GreetingProxy
equals self: true
equals other: false
child sees interface: true
child is proxy loader: true
isolated sees interface: false
isolated proxy: IllegalArgumentException
duplicate interface: IllegalArgumentException
~~~

Các dòng liên quan trực tiếp tới chọn loader:

1. `same loader: true`: proxy đầu tiên được định nghĩa bởi `contractLoader` đã yêu cầu.
2. `child sees interface: true`: class loader con **ủy quyền cho parent** nên vẫn phân giải `Greeting.class` về cùng đối tượng `Class`.
3. `child is proxy loader: true`: proxy thứ hai được định nghĩa bởi **child loader**, dù interface do parent nạp.
4. `isolated sees interface: false`: loader có parent `null` chỉ tìm được những kiểu mà bootstrap loader nhìn thấy, không thấy nested interface ứng dụng `Greeting`.
5. `isolated proxy: IllegalArgumentException`: điều kiện visibility/identity bị vi phạm **ngay khi tạo proxy**.
6. `duplicate interface: IllegalArgumentException`: danh sách interface không được lặp lại cùng một `Class<?>`.

Handler cũng cho thấy: method `greet` trả `String`, `count` trả `Integer` boxing tự động cho return primitive `int`, default method `farewell` được chuyển tới implementation mặc định qua `InvocationHandler.invokeDefault`, và các lời gọi `toString`/`equals` do handler quyết định. Sự hiện diện của `default` không khiến proxy tự bỏ qua handler.

**Vì sao stdout không in tên class proxy?** Tên package/class cụ thể của proxy là chi tiết JVM có thể thay đổi theo lần chạy và môi trường. `Proxy.isProxyClass`, `getInterfaces()`, `getClassLoader()` là cách kiểm tra đáng tin cậy hơn so với giả định lớp luôn có tên dạng `$Proxy0`.

## 7. Khi có nhiều interface: thêm ràng buộc

`Proxy.newProxyInstance(loader, interfaces, handler)` không chỉ kiểm tra interface đầu tiên. Theo quy tắc Java 17, các hạn chế quan trọng gồm:

- Mọi phần tử phải là **interface thực**, **non-hidden** và **non-sealed**; không đưa class thường, primitive, `null` hoặc sealed interface vào danh sách.
- Không có hai phần tử `Class<?>` trùng nhau trong mảng, ngay cả khi ở hai vị trí khác nhau.
- Loader được chọn phải nhìn thấy **mỗi interface** và **mọi kiểu trong các public method signatures** liên quan (kể cả method kế thừa) đúng identity.
- Nếu có interface **không `public`**, tất cả interface không public phải ở cùng **package và module**, do loader đã chọn định nghĩa, và điều kiện truy cập khác phải thỏa. Không thể tùy tiện ghép hai package-private interface từ hai package khác nhau.
- Khi nhiều interface khai báo method có **cùng tên và kiểu tham số**, các kiểu trả về phải tương thích theo quy tắc của Proxy: cùng primitive/`void` chính xác, hoặc có một kiểu trả về reference gán được cho tất cả kiểu còn lại. Nếu không, tạo proxy thất bại.
- **Thứ tự interface có ý nghĩa.** Khi nhiều interface có cùng signature, `Method` giao cho handler tương ứng interface đứng sớm hơn trong danh sách áp dụng, không nhất thiết là interface mà kiểu tham chiếu phía caller đã dùng để gọi.

Ví dụ (**đoạn sai có chủ đích**, không chạy riêng):

~~~java
Proxy.newProxyInstance(
        contractLoader,
        new Class<?>[] { Greeting.class, Greeting.class },
        handler);
// IllegalArgumentException: cùng interface lặp trong mảng
~~~

Thậm chí khi tên binary của hai class giống hệt nhưng class loader khác nhau, việc đưa `Class<?>` từ loader A vào danh sách rồi tạo proxy bằng loader B vẫn có thể vi phạm identity. Không sửa bằng cách so `getName()`; cần chọn đúng loader hoặc hợp nhất contract ở một tầng API chung.

Nếu method interface trả về một kiểu domain được định nghĩa ở plugin loader mà loader của proxy không thấy, kiểm tra mỗi interface `Class` chưa đủ. Phải xem cả parameter/return/exception types trong **public method signatures** và cách chúng được nạp.

## 8. Module JPMS và nơi lớp proxy được đặt

Từ Java 9, một lớp không chỉ thuộc **class loader** mà còn thuộc **module**. Hai thông tin này không thay thế nhau. Gọi:

~~~java
Class<?> generated = proxy.getClass();
System.out.println(generated.getClassLoader());
System.out.println(generated.getModule());
~~~

Ở đây `proxy` là đối tượng đã tạo; đoạn code chỉ dùng để chẩn đoán.

Java 17 xác định **module và package chứa lớp proxy** dựa trên accessibility của các interface:

| Tình huống interface | Vị trí/khả năng truy cập của lớp proxy |
| --- | --- |
| Tất cả interface `public`, package của chúng được export hoặc open **vô điều kiện** | Proxy class `public` trong package được export vô điều kiện nhưng **không open**; tên package/module do JDK quyết định |
| Có interface không `public` (các ràng buộc cùng package và module đều thỏa) | Proxy class **không public**, nằm trong chính package và module của nhóm interface không public |
| Tất cả interface `public` nhưng ít nhất một interface nằm trong package **không export và không open vô điều kiện** | Proxy class `public` nằm trong một package **không export, không open** của **dynamic named module** do runtime tạo |

**Dynamic module** ở đây là một module có tên được tạo lúc chạy để đóng gói lớp proxy, không phải module mới mà lập trình viên cần tự thêm vào `module-info.java`. Một số quyền đọc/export cần thiết cho module này được runtime thiết lập. Kể cả nếu proxy class `public`, class trong package không được export vẫn có thể **không truy cập được từ bên ngoài module**. Vì vậy không nên giả định `proxy.getClass().getConstructor(...).newInstance(...)` luôn hợp lệ; dùng `Proxy.newProxyInstance` để tạo đối tượng.

Các điểm thực tế:

- `module-info.java` có `exports` hoặc `opens` thay đổi **ranh giới truy cập giữa module**; class loader quyết định **identity và visibility**. Cần kiểm tra cả hai tầng.
- Một public interface ở package không export vẫn có thể được JDK hỗ trợ tạo proxy trong trường hợp phù hợp; điều này **không** có nghĩa caller tùy ý import được interface đó hoặc có quyền reflective access vào lớp proxy sinh ra.
- **Unnamed module** (code trên class path) mặc định export và open các package của nó; tuy nhiên class loader vẫn phải thấy đúng interface.
- Trong môi trường dùng module path, các public method signatures, quan hệ đọc/export và module chứa interface phải nhất quán. Đừng sửa lỗi identity của loader chỉ bằng cách thêm `--add-opens`: flag này không tạo ra cùng `Class<?>` giữa các loader độc lập.
- **Tên module/package của proxy class không được bảo đảm cố định.** Không hardcode `jdk.proxy1` hoặc `$Proxy0` trong logic ứng dụng.

## 9. InvocationHandler: chi tiết cần xử lý đúng

### 9.1. `Object.toString`, `equals` và `hashCode`

Ba method `public` quen thuộc được proxy chuyển tới handler, với `method.getDeclaringClass() == Object.class`. Nếu handler chỉ biết method nghiệp vụ, cả gọi `toString()` trong logging cũng có thể dẫn tới lỗi không mong muốn.

Chương trình phần 6 xử lý ba method theo **identity semantics**: `equals` so `proxy == other`, `hashCode` dùng `System.identityHashCode(proxy)`, còn `toString` trả chuỗi cố định. Đây là một lựa chọn phù hợp cho proxy minh họa; trong sản phẩm, nếu dùng equality theo business key, phải thiết kế `equals` và `hashCode` nhất quán.

### 9.2. Default method của interface

Mặc dù interface có `default String farewell()`, proxy vẫn chuyển lời gọi đến handler. Trên Java 17, có thể chủ động gọi logic mặc định:

~~~java
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, callArgs);
}
~~~

Đoạn này là **trích từ chương trình đầy đủ**. `InvocationHandler.invokeDefault` có từ Java 16, thực hiện lời gọi default method được chọn trên proxy, với các ràng buộc về method hợp lệ. Đừng mặc định gọi `method.invoke(proxy, args)` để “đi tới default” vì điều đó có thể quay lại handler.

### 9.3. Delegation sang một đối tượng thật

Một handler forwarding có thể dùng `Method.invoke(realTarget, args)` **nếu realTarget thật sự triển khai interface chứa method**. Với reflection delegation, `InvocationTargetException` bọc exception do target ném:

~~~java
try {
    return method.invoke(realTarget, args);
} catch (java.lang.reflect.InvocationTargetException ex) {
    throw ex.getCause();
}
~~~

Đây là **đoạn minh họa bên trong `InvocationHandler.invoke`**, giả định `realTarget` phù hợp kiểu. Unwrap `getCause()` giúp không rò lớp bọc reflection vô cớ; tuy vậy checked exception vẫn phải tuân thủ `throws` của interface. Với đối tượng không triển khai interface liên quan, `Method.invoke` có thể báo `IllegalArgumentException`.

### 9.4. Kết quả primitive và checked exception

Handler là phương thức trả `Object`. Nếu interface có `int count()` thì trả `Integer` là hợp lệ; `return null` khiến proxy gặp `NullPointerException` ở bước unboxing. Nếu interface có `String name()` mà handler trả `Integer` sẽ phát sinh `ClassCastException` khi proxy chuyển kiểu kết quả.

Nếu handler ném checked exception mà method interface không khai báo và không cho phép, proxy chuyển nó thành `UndeclaredThrowableException`. Nên giữ contract exception rõ ràng thay vì ném checked exception tùy ý từ handler.

## 10. Lỗi hay gặp khi chọn loader và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException` ngay lúc `newProxyInstance` | Loader không thấy đúng một interface, một kiểu signature, interface bị lặp, sealed hoặc ràng buộc method không hợp lệ | Kiểm tra từng `Class`, `Class.forName(...,loader) == type`, danh sách interface và signature |
| `ClassCastException` khi cast kết quả về interface | Caller và proxy đang dùng hai bản interface **khác identity**, hoặc chưa đưa interface đó vào danh sách | In loader/`Class` identity của caller và interface đã đưa vào; chia sẻ contract qua loader chung |
| Chạy bình thường ở main thread nhưng lỗi ở worker thread | TCCL thay đổi theo thread hoặc bằng `null` | Dùng loader gắn với contract hoặc truyền loader rõ ràng; xác minh TCCL trước khi chọn |
| Plugin A chạy, Plugin B không | Hai plugin loader có visibility khác nhau | Đặt contract/DTO trong shared API loader hoặc cung cấp loader tương thích |
| Tạo proxy được nhưng reflective construction của lớp proxy thất bại | Proxy class nằm trong module/package được đóng gói | Dùng `Proxy.newProxyInstance`; kiểm tra module/package khi cần chẩn đoán |
| Gọi `toString`/`equals` lỗi hoặc đệ quy | Handler không xử lý `Object` methods, hoặc tự gọi method trên chính proxy | Branch riêng cho `Object`; tránh delegate vào proxy đang chặn |
| Default method không chạy | Handler chưa gọi `InvocationHandler.invokeDefault` | Gọi tường minh theo contract của interface |
| Method trả primitive gây `NullPointerException` | Handler trả `null` khiến proxy unbox | Trả wrapper hợp lệ, có kiểm tra dữ liệu |
| Checked exception bị bọc `UndeclaredThrowableException` | Handler ném checked exception ngoài contract `throws` của interface | Xử lý hoặc khai báo exception phù hợp contract |
| Loader thấy interface nhưng proxy vẫn lỗi | Public method signatures, non-public accessibility hoặc JPMS restrictions chưa được đáp ứng | Kiểm tra tất cả method types, module/package, duplicate signature và loader |

### Checklist điều tra theo thứ tự

1. Xác định **tập interface thực tế** cần proxy, lấy từ các `Class<?>` đang dùng trong ứng dụng; không dựng lại `Class` chỉ bằng chuỗi tên.
2. Chọn một loader và kiểm tra `Class.forName(i.getName(), false, loader) == i` **cho từng interface**, không chỉ phần tử đầu.
3. Kiểm tra các kiểu trong chữ ký public method và các interface kế thừa có được loader đó thấy đúng cách.
4. Đối chiếu `public`/package-private, sealed/hidden và các signature trùng nhau; xác nhận các package/module có thể kết hợp.
5. In `interfaceClass.getClassLoader()`, `interfaceClass.getModule()` và `Thread.currentThread().getContextClassLoader()` để xác định khác biệt giữa môi trường thực thi.
6. Nếu class proxy đã tạo, kiểm tra `Proxy.isProxyClass(proxy.getClass())`, `proxy.getClass().getClassLoader()`, `proxy.getClass().getInterfaces()` và `Proxy.getInvocationHandler(proxy)`.
7. Phân tách lỗi **tạo proxy** khỏi lỗi **invoke handler** và **cast kết quả**. Ba vị trí lỗi cần các cách sửa khác nhau.

`Proxy.getProxyClass(loader, interfaces...)` tồn tại để lấy proxy class nhưng đã bị **deprecated** trong Java 17; khi cần một đối tượng chạy thực tế, ưu tiên `Proxy.newProxyInstance`. Việc giữ strong reference đến class loader, generated class hoặc proxy trong cache dài hạn có thể ngăn loader/plugin được thu hồi; quản lý vòng đời cache có chủ đích.

## 11. Bài tập tự kiểm tra

**Tình huống 1.** `Api.class` được định nghĩa trong shared parent loader. Plugin loader con ủy quyền cho parent; system loader không thấy các class đặc thù của plugin. Bạn cần proxy đồng thời `Api` và `PluginOnly`. Có thể dùng ngay `Api.class.getClassLoader()` không?  
**Đáp:** Chỉ khi loader đó cũng nhìn thấy `PluginOnly.class` và mọi public signature types. Thông thường sẽ cần loader plugin **có khả năng nhìn thấy cả hai**; kiểm tra từng identity trước.

**Tình huống 2.** Hai loader độc lập cùng nạp class có tên `com.example.Api`; bằng tên chúng hoàn toàn giống nhau. Một proxy tạo từ `Api` của loader A có ép về `Api` của loader B được không?  
**Đáp:** Không có gì bảo đảm. Hai `Class<?>` khác identity; cast có thể gây `ClassCastException`. Giải pháp bền vững là thống nhất vùng nạp contract.

**Tình huống 3.** Thread pool gán TCCL về loader chỉ nhìn thấy JDK classes; `MyApi` được application loader định nghĩa. Vì sao `Proxy.newProxyInstance(TCCL, ...)` thất bại?  
**Đáp:** TCCL không thấy đúng `MyApi.class`. Lựa chọn theo thread không đáp ứng điều kiện `Class.forName(...) == MyApi.class`.

**Tình huống 4.** Interface có default method nhưng handler không gọi logic default. JVM có tự chạy default method không?  
**Đáp:** Không. Invocation đi qua handler; với Java 17 cần gọi `InvocationHandler.invokeDefault` nếu muốn hành vi mặc định.

**Tình huống 5.** Vì sao nhìn thấy `proxy.getClass().getModule().isNamed()` trả `true` không chứng minh input interface đang nằm trong named module?  
**Đáp:** Runtime có thể đặt generated proxy class vào một **dynamic named module** khác. Phải kiểm tra riêng `interfaceClass.getModule()` và `proxy.getClass().getModule()`.

## Tài liệu chính thức

- [Java SE 17 — `java.lang.reflect.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — `InvocationHandler` và `invokeDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)