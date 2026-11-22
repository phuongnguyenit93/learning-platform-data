# 10.3 Điều kiện về interface công khai, không công khai, sealed và khả năng nhìn thấy kiểu

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 10. Proxy động  
**Phiên bản minh họa:** Java 17 trở lên; API chính: `java.lang.reflect.Proxy` và `InvocationHandler`.

## Mục tiêu

`Proxy.newProxyInstance(loader, interfaces, handler)` không chấp nhận mọi tập hợp interface. JVM cần sinh một class thực sự implement được từng interface; class được sinh còn phải tuân theo **quy tắc Java accessibility, định danh kiểu theo class loader, Java Platform Module System (JPMS), và sealed hierarchy**.

Sau bài này, bạn có thể:

1. Giải thích vì sao proxy động của JDK **chỉ triển khai interface**, và interface phải **non-hidden, non-sealed**, không trùng `Class<?>`.
2. Phân biệt interface `public` và interface **không public** (ví dụ package-private): khi nào có thể dùng cùng nhau và tại sao interface không public phải nằm trong **cùng package, cùng module, cùng defining loader** phù hợp.
3. Hiểu sự khác biệt giữa **nhìn thấy kiểu theo tên qua class loader** và **truy cập kiểu theo ngữ nghĩa Java/JPMS**.
4. Biết quy tắc kiểm tra các kiểu xuất hiện trong **public method signatures**, kể cả method kế thừa; các ràng buộc về return type khi nhiều interface khai báo cùng signature.
5. Đọc quy tắc lựa chọn **package/module** của lớp proxy khi package interface được export/open hoặc bị đóng.
6. Thử các ví dụ Java 17 đã chạy thực tế: thành công với `public`/package-private, thất bại với `sealed`/duplicate/invisible loader/khác package/sai return type và trường hợp named module có interface `public` nhưng **không export package**.
7. Thiết kế SPI công khai ổn định mà không phụ thuộc vào tên hoặc quyền truy cập của lớp proxy được sinh ra.

## 1. Proxy động của JDK thực sự tạo ra cái gì?

API điển hình:

~~~java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[]{SomeInterface.class},
        handler);
~~~

Đây là **đoạn minh họa** cần có biến `loader`/`handler` và interface thực tế. `Proxy` tạo một **class mới tại runtime** kế thừa `java.lang.reflect.Proxy`, đồng thời implements danh sách interface được cung cấp. Mỗi instance gắn với một `InvocationHandler`; khi gọi phương thức interface trên proxy, JVM chuyển lời gọi đến `handler.invoke(proxy, method, args)`.

Khác với thư viện tạo subclass bằng bytecode, **JDK dynamic proxy không được dùng để kế thừa một class nghiệp vụ bất kỳ**. Truyền `String.class`, `ArrayList.class` hoặc class triển khai thay cho interface là lỗi.

Sơ đồ:

~~~text
Caller
  |
  | gọi Greeting.greet("An")
  v
Proxy instance: implements Greeting
  |
  | chuyển sang InvocationHandler.invoke(proxy, Method, Object[])
  v
Handler
  | thực hiện logic / chuyển tiếp / log / cache
  v
Giá trị trả về cho caller, hoặc exception
~~~

Lớp proxy **không phải** `Greeting` được triển khai trước bằng source code, nhưng vẫn có thể ép kiểu sang `Greeting` khi một trong các interface proxy là `Greeting`. Tên lớp được sinh, package và module có thể thay đổi theo môi trường và quy tắc của JDK. Đừng lập trình dựa trên tên dạng `$Proxy0` hoặc tên module động cụ thể.

**Hai câu hỏi độc lập:** (1) interface đầu vào có **hợp lệ để sinh lớp proxy** không? (2) code caller có **quyền import, ép kiểu, phản chiếu hoặc gọi phương thức** trên các kiểu liên quan không? Một proxy tạo được chưa có nghĩa mọi caller đều nhìn thấy đầy đủ các kiểu của nó.

## 2. Checklist điều kiện mà `Proxy.newProxyInstance` phải thỏa

Java 17 ghi rõ các ràng buộc sau; vi phạm thường tạo `IllegalArgumentException` ngay lúc yêu cầu proxy:

| Điều kiện | Vì sao cần? | Ví dụ gây lỗi |
| --- | --- | --- |
| Mỗi phần tử trong `interfaces` là **interface**, **non-hidden** và **non-sealed** | Lớp sinh ra phải được phép trực tiếp implement interface | `String.class`, interface `sealed` |
| Không lặp cùng một đối tượng `Class<?>` trong mảng | Mỗi proxy interface chỉ được xuất hiện một lần | `{Greeting.class, Greeting.class}` |
| Mỗi interface **nhìn thấy bằng tên** qua `loader` đã chọn | Proxy phải tham chiếu đúng định danh runtime của interface | Loader cô lập không tải được `Greeting` |
| Mọi kiểu xuất hiện trong **public method signatures**, bao gồm method kế thừa, nhìn thấy qua `loader` | Bytecode của proxy cần mô tả các parameter/return type đó | Phương thức nhận class chỉ thấy qua loader khác |
| Các interface **không public** phải cùng **package và module**, được định nghĩa bởi loader đã cho; module đó phải truy cập được các kiểu interface liên quan | Proxy class non-public chỉ có một vị trí package/module hợp lệ | Hai interface package-private thuộc hai package |
| Các method trùng tên và danh sách kiểu tham số phải có return type tương thích | Một method proxy không thể hợp lệ với hai return type xung đột | `Number result()` và `String result()` |
| Không vượt các giới hạn classfile/JVM | Class được sinh cần cấu trúc hợp lệ | Vượt giới hạn số interface của JVM |

Ngoài bảng, `interfaces` hoặc phần tử trong mảng là `null`, hay `handler` là `null`, sẽ gây `NullPointerException`. Các quy tắc bảo mật có thể liên quan `SecurityManager` ở những môi trường còn sử dụng cơ chế này, nhưng nó không thay thế các điều kiện cơ bản.

**Return type trùng chữ ký:** nếu nhiều interface khai báo method có cùng tên và parameter signature:
- Khi return là primitive hoặc `void`, các method tương ứng phải có **cùng return type chính xác**.
- Khi return là reference, phải có **một return type có thể gán cho tất cả return type còn lại** (covariant return). `String` và `CharSequence` tương thích; `String` và `Number` không tương thích.
- Chỉ đối chiếu return type theo quan hệ assignability là chưa đủ để bảo đảm logic handler đúng; khi trùng method, **thứ tự interface** ảnh hưởng `Method` được chuyển vào handler.

Một yêu cầu proxy theo tập interface và thứ tự khác nhau có thể dẫn đến lớp proxy khác nhau; không nên coi mảng interface như một tập hợp không có thứ tự.

## 3. Interface `public`, package-private và giới hạn truy cập

### 3.1. Tất cả interface public

Ví dụ:

~~~java
public interface Greeting {
    String greet(String name);
}
~~~

Nếu `Greeting.class` có thể nhìn thấy qua loader, không sealed/hidden, các kiểu public method signature cũng nhìn thấy, và các điều kiện khác thỏa, `Proxy.newProxyInstance` có thể tạo lớp proxy public.

Tuy nhiên, **`public` chỉ là một điều kiện**:

- Với Java classpath/unnamed module, package được kiểm soát theo mô hình class loader và Java visibility truyền thống.
- Với **named module**, một interface `public` vẫn có thể nằm trong package **không được `exports`**. Code ở module khác không thể trực tiếp `import` interface đó chỉ vì nó có modifier `public`.
- Proxy có thể tạo được theo cơ chế JPMS đặc biệt dù caller không có quyền import interface ở compile time. Nhưng caller vẫn phải có một đường **được phép** để làm việc với giá trị, chẳng hạn contract public đã export; không thể suy từ khả năng tạo proxy ra quyền gọi mọi thành viên nội bộ.

### 3.2. Có interface không public

Một interface top-level **package-private**:

~~~java
package lab.proxy;

interface LocalInternal {
    String identity();
}
~~~

Đoạn minh họa này biên dịch khi lưu đúng package; trong chương trình mục 6, nó nằm cùng file với class public. Interface này **không có modifier `public`**; code ngoài runtime package tương ứng không thể import/sử dụng kiểu trực tiếp như API công khai.

Nếu một mảng proxy chứa `LocalInternal.class`, lớp proxy sẽ có phạm vi truy cập **non-public**. Với nhiều interface không public, tất cả phải:

1. Nằm trong **cùng package**.
2. Nằm trong **cùng module**.
3. Được định nghĩa theo quy tắc class loader mà `Proxy` yêu cầu.
4. Có khả năng truy cập các kiểu liên quan để lớp proxy thực sự implement được những interface ấy.

**Có thể kết hợp** một interface public với một interface package-private trong cùng lời gọi. Mức truy cập của lớp proxy được sinh sẽ theo interface **ít công khai nhất**, tức **non-public**. Caller có thể vẫn gọi qua một interface public mà nó nhìn thấy, nhưng không thể mặc nhiên truy cập class proxy bằng tên hoặc dùng constructor của nó qua Reflection từ mọi nơi.

Các interface không public **ở hai package khác nhau** không thể cùng nằm trong một lớp proxy JDK, dù Java source có dùng Reflection lấy được cả hai `Class<?>`. Lý do không phải do `Proxy` ngại mix package về mặt cú pháp, mà do một class được sinh **chỉ thuộc một package và module**, nên không thể vừa thỏa mọi quy tắc truy cập cho hai non-public interface có package khác nhau.

### 3.3. `public interface` khác `public proxy class`

Có hai lớp quyền phải phân biệt:

- **Quyền trên interface:** caller có thể tham chiếu tên kiểu, import, cast và gọi method theo luật Java/module.
- **Quyền trên generated proxy class:** package/module mà `Proxy` chọn quyết định caller có được truy cập chính class, public constructor hoặc phản chiếu nó hay không.

Ngay cả khi generated class `public`, package của nó có thể **không export** cho caller trong JPMS. `Modifier.isPublic(proxy.getClass().getModifiers())` **không đủ** để kết luận caller có thể `Constructor.newInstance` hoặc `Class.forName` rồi dùng trực tiếp. Phần thực hành named module sẽ chứng minh điều này.

## 4. `sealed` và `non-sealed`: ranh giới của proxy động

Từ Java 17, `sealed interface` cho phép tác giả **giới hạn trực tiếp những kiểu được phép extends/implements** qua danh sách `permits`. Lớp proxy JDK sinh ra tại runtime không thể tùy ý được thêm vào danh sách các implementation được phép. Do đó điều kiện `Proxy` rất rõ: **interface được truyền trực tiếp trong mảng `interfaces` phải non-sealed**.

Ví dụ:

~~~java
public sealed interface Restricted permits AllowedRestricted {
    String run();
}
public static final class AllowedRestricted implements Restricted {
    public String run() { return "direct"; }
}
~~~

Đây là đoạn minh họa **bên trong một class bao** (như mục 6), không phải một file độc lập. Với interface `Restricted`, lời gọi tương đương:

~~~java
Proxy.newProxyInstance(
        Restricted.class.getClassLoader(),
        new Class<?>[]{Restricted.class},
        handler);
~~~

sẽ ném `IllegalArgumentException`. Việc cung cấp `InvocationHandler` hợp lệ không giúp bỏ qua hạn chế sealed.

**Phân biệt quan trọng:** “Không được đưa sealed interface trực tiếp vào proxy interfaces” **không đồng nghĩa** “không thể có proxy mang quan hệ `instanceof` với một sealed superinterface”. Xem cây hợp lệ:

~~~text
sealed Parent
    |
    +-- permitted non-sealed Child
                         |
                         +-- generated proxy implements Child
~~~

Nếu `Child` là **non-sealed interface** được `Parent` cho phép extends, một lớp proxy có thể **trực tiếp implement Child**, từ đó **gián tiếp** implements `Parent`. Đây là kết quả bình thường của quy tắc sealed hierarchy: loại được kiểm soát là những **direct subclasses/subinterfaces** của `Parent`. Ví dụ chạy độc lập ở mục 7 xác nhận hành vi này.

Các class/interface `final`, `sealed`, `non-sealed` có ý nghĩa riêng:
- `final class` không được subclass; nó **không phải interface**, nên không truyền vào `interfaces` được.
- `sealed interface` là interface nhưng bị API `Proxy` từ chối khi được chỉ định trực tiếp.
- `non-sealed interface` có thể làm proxy interface nếu các điều kiện còn lại thỏa.
- Interface bình thường không khai báo sealed (tức non-sealed theo nghĩa không bị giới hạn) cũng hợp lệ; cú pháp từ khóa `non-sealed` chỉ áp dụng khi mở lại một quan hệ sealed phù hợp.

## 5. “Nhìn thấy kiểu” qua class loader không đồng nghĩa “được truy cập”

### 5.1. Phép kiểm tra định danh Class tại runtime

Với mỗi interface `i` và class loader `cl` truyền cho `Proxy`, Java 17 yêu cầu:

~~~java
Class.forName(i.getName(), false, cl) == i
~~~

Đây là đoạn **biểu thức kiểm tra**, không phải file chạy độc lập. So sánh dùng **`==` của đối tượng `Class<?>`**, chứ không chỉ so chuỗi `i.getName()`.

Vì sao?

- Danh tính runtime của một kiểu class/interface phụ thuộc cả **binary name** lẫn **defining class loader**; hai loader khác nhau có thể định nghĩa hai kiểu cùng tên nhưng **không gán được cho nhau**.
- Loader đưa cho proxy phải **tìm đúng kiểu đã truyền**. Nó có thể dùng **parent delegation**; **không đòi** `i.getClassLoader() == cl`, vì loader con có thể nhìn thấy interface do loader cha định nghĩa.
- `Class.forName(..., false, loader)` dùng tham số `false` để **không chủ động khởi tạo class** trong phép nạp tên; điều này khác với khởi tạo object hoặc thực thi handler.
- Có `Class<?>` lấy được từ một plugin loader **không bảo đảm** rằng app loader nhìn thấy chính đối tượng Class đó.

Ví dụ `new ClassLoader(null) {}` trong bài thực hành tạo loader không có parent ứng dụng. Nó không tìm được `lab.proxy.ProxyVisibilityDemo$Greeting`; `Proxy.newProxyInstance` từ chối vì điều kiện visibility, dù biến `Greeting.class` đã có sẵn ở mã gọi.

### 5.2. Phải nhìn thấy **mọi kiểu trong public method signatures**

Không chỉ bản thân interface. Ví dụ:

~~~java
public interface ShippingApi {
    Receipt ship(Order request);
}
~~~

Đây là **pseudocode về chữ ký** vì `Receipt`/`Order` chưa được khai báo. Nếu `Order` hoặc `Receipt` bị định nghĩa bởi một loader mà loader được chọn cho proxy không thể tìm thấy **đúng đối tượng Class theo tên**, proxy có thể không tạo được.

Quy tắc bao gồm cả **public method signatures của interface và các superinterface kế thừa**, không chỉ những method viết trực tiếp ở file hiện tại.

- Trước hết chú ý kiểu **erased** trong descriptor runtime (ví dụ generic `List<Order>` có raw descriptor kiểu `List`; thông tin generic khác là một tầng metadata riêng).
- Các kiểu **tham số** và **kiểu trả về** trong public signature phải nhìn thấy theo tên. Đừng chỉ kiểm tra `interface.getName()` rồi cho rằng toàn bộ API có thể được proxy.
- Với JPMS, một kiểu có thể **nhìn thấy bằng tên trong loader** nhưng **package không export** cho caller. Quy tắc module của Proxy có thể sắp xếp thêm quyền cần thiết cho **dynamic proxy module**, không có nghĩa ứng dụng bên ngoài tự được import kiểu đó.
- Khi plugin dùng class loader riêng, việc mang cùng một “bản sao tên” interface không đủ để cast về interface host. Thiết kế SPI thường đặt contract ở một module/loader chia sẻ có chủ đích.

### 5.3. Không dùng class loader để thay thế phân quyền

Loader giải quyết **tìm thấy/định danh lớp** và góp phần tạo ranh giới module/class; nó không mặc nhiên là sandbox. Proxy/handler được chạy **trong tiến trình ứng dụng**, có thể thực thi logic có quyền của tiến trình. Không tin plugin thì cần kiểm soát capability, validate dữ liệu, quản lý resource và khi cần tách process.

## 6. Demo Java 17: public, package-private và các trường hợp bị từ chối

Demo gồm hai file ở hai package. File đầu có interface công khai, interface package-private, interface sealed và các trường hợp trùng return signature. File thứ hai dùng để chứng minh **hai interface không public ở hai package khác nhau không thể proxy cùng lúc**.

**Cấu trúc thư mục** (tính từ thư mục dự án trống):

~~~text
src/
  lab/
    proxy/
      ProxyVisibilityDemo.java
    other/
      ForeignInternal.java
~~~

### 6.1. `src/lab/proxy/ProxyVisibilityDemo.java`

~~~java
package lab.proxy;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

interface LocalInternal {
    String identity();
}

public final class ProxyVisibilityDemo {
    public interface Greeting {
        String greet(String name);
    }

    public sealed interface Restricted permits AllowedRestricted {
        String run();
    }

    public static final class AllowedRestricted implements Restricted {
        public String run() { return "direct"; }
    }

    public interface NumberResult { Number result(); }
    public interface StringResult { String result(); }

    private static final InvocationHandler HANDLER = (proxy, method, args) -> {
        return switch (method.getName()) {
            case "greet" -> "Hello " + args[0];
            case "identity" -> "internal";
            case "toString" -> "proxy-object";
            default -> throw new UnsupportedOperationException(method.getName());
        };
    };

    private static Object create(ClassLoader loader, Class<?>... interfaces) {
        return Proxy.newProxyInstance(loader, interfaces, HANDLER);
    }

    private static void rejected(String label, Runnable attempt) {
        try {
            attempt.run();
            System.out.println(label + "=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = ProxyVisibilityDemo.class.getClassLoader();

        Greeting publicProxy = (Greeting) create(appLoader, Greeting.class);
        System.out.println("publicCall=" + publicProxy.greet("An"));
        System.out.println("publicProxy="
                + Modifier.isPublic(publicProxy.getClass().getModifiers()));
        System.out.println("isProxy=" + Proxy.isProxyClass(publicProxy.getClass()));

        Object mixed = create(appLoader, Greeting.class, LocalInternal.class);
        System.out.println("mixedGreeting=" + ((Greeting) mixed).greet("Binh"));
        System.out.println("mixedInternal=" + ((LocalInternal) mixed).identity());
        System.out.println("mixedProxyPublic="
                + Modifier.isPublic(mixed.getClass().getModifiers()));
        System.out.println("samePackage=" + mixed.getClass().getPackageName()
                .equals(LocalInternal.class.getPackageName()));
        System.out.println("sameModule=" + (mixed.getClass().getModule()
                == LocalInternal.class.getModule()));

        rejected("sealed", () -> create(appLoader, Restricted.class));
        rejected("duplicate",
                () -> create(appLoader, Greeting.class, Greeting.class));
        rejected("notInterface", () -> create(appLoader, String.class));
        rejected("hiddenByLoader",
                () -> create(new ClassLoader(null) {}, Greeting.class));

        Class<?> foreign = Class.forName("lab.other.ForeignInternal");
        rejected("differentPackages",
                () -> create(appLoader, LocalInternal.class, foreign));
        rejected("conflictingReturns",
                () -> create(appLoader, NumberResult.class, StringResult.class));
    }
}
~~~

### 6.2. `src/lab/other/ForeignInternal.java`

~~~java
package lab.other;

interface ForeignInternal {
    void ping();
}
~~~

### 6.3. Biên dịch và chạy

Đứng trong thư mục chứa `src/`:

~~~bash
javac --release 17 -d out src/lab/proxy/ProxyVisibilityDemo.java src/lab/other/ForeignInternal.java
java -cp out lab.proxy.ProxyVisibilityDemo
~~~

Lệnh trên dùng được trong terminal có JDK 17+ trên Windows, Linux, macOS khi không tự chèn cú pháp shell khác. `javac` có thể tạo thư mục `out` trong trường hợp chưa tồn tại.

**Stdout chính xác** của demo đã được biên dịch/chạy:

~~~text
publicCall=Hello An
publicProxy=true
isProxy=true
mixedGreeting=Hello Binh
mixedInternal=internal
mixedProxyPublic=false
samePackage=true
sameModule=true
sealed=IllegalArgumentException
duplicate=IllegalArgumentException
notInterface=IllegalArgumentException
hiddenByLoader=IllegalArgumentException
differentPackages=IllegalArgumentException
conflictingReturns=IllegalArgumentException
~~~

**Giải thích:**

- `Greeting` là `public`, non-sealed và nhìn thấy qua app loader; `publicCall` thành công.
- `Proxy.isProxyClass(...) == true` xác nhận đây thực sự là class proxy JDK. Đừng thay bằng kiểm tra tên chứa `$Proxy`.
- `Greeting + LocalInternal` cùng package cho class proxy non-public; lớp đó nằm trong package và module của interface non-public; vẫn có thể gọi `Greeting.greet` và `LocalInternal.identity` từ code có quyền.
- `Restricted` là sealed interface nên bị từ chối. Đây là giới hạn được API kiểm tra, không phải `ClassCastException` do ép kiểu sau tạo instance.
- Interface lặp, class không phải interface, loader không nhìn thấy tên và hai interface non-public ở hai package khác nhau lần lượt vi phạm các điều kiện độc lập.
- `NumberResult.result()` trả `Number` và `StringResult.result()` trả `String`; hai reference return type không có kiểu nào assignable đến kiểu còn lại, nên tổ hợp bị từ chối.
- Trong mã `rejected`, ta chỉ in **loại lỗi** chứ không hardcode `Exception.getMessage()` vì message có thể khác giữa JDK; các dòng ở trên ổn định với ví dụ.

Để xem nguyên nhân thực tế lúc thử nghiệm, tạm log `expected.getMessage()` hoặc stack trace, nhưng không dựa vào nội dung message như một API contract để điều khiển ứng dụng.

## 7. Demo Java 17: sealed parent và non-sealed child

Một sealed parent có thể cho phép một **non-sealed subinterface** mở rộng. Proxy được tạo từ **subinterface non-sealed** là hợp lệ và cũng thỏa `instanceof` cho sealed parent vì quan hệ extends đã được cho phép.

**File chạy độc lập:** `SealedParentCheck.java`

~~~java
import java.lang.reflect.Proxy;

public class SealedParentCheck {
    public sealed interface Parent permits Child {
        String value();
    }

    public non-sealed interface Child extends Parent { }

    public static void main(String[] args) {
        Object instance = Proxy.newProxyInstance(
                Child.class.getClassLoader(),
                new Class<?>[]{Child.class},
                (p, m, a) -> "ok");

        System.out.println("childResult=" + ((Child) instance).value());
        System.out.println("parentInstance=" + (instance instanceof Parent));
    }
}
~~~

Biên dịch và chạy (trong thư mục chứa file):

~~~bash
javac --release 17 SealedParentCheck.java
java SealedParentCheck
~~~

Stdout đã kiểm chứng:

~~~text
childResult=ok
parentInstance=true
~~~

Phân biệt hai mảng truyền vào `Proxy`:

~~~java
new Class<?>[]{Parent.class} // Bị từ chối: Parent sealed.
new Class<?>[]{Child.class}  // Hợp lệ: Child non-sealed.
~~~

Đây là **hai biểu thức minh họa**, không phải khai báo biến hoàn chỉnh. Trường hợp thành công vẫn có thể bị từ chối nếu những điều kiện khác (loader visibility, return type trùng...) bị vi phạm.

## 8. Named modules (JPMS): public interface không export package

Từ Java 9, tính công khai của interface **không đủ** để xác định tính công khai của package từ một module khác. Quy tắc lựa chọn package/module của generated proxy, theo Java 17, là:

| Tập interface | Package chứa các interface | Package/module của proxy sinh ra |
| --- | --- | --- |
| Tất cả interface `public` | Mọi package được **export hoặc open vô điều kiện** | Lớp proxy **public** trong một package **unconditionally exported, non-open**; tên package và module không được bảo đảm |
| Có ít nhất một interface **non-public** | Mọi package được export/open vô điều kiện | Lớp proxy **non-public** trong đúng package/module của các interface non-public; mọi interface non-public phải cùng package/module |
| Tất cả interface `public` | Có ít nhất một package **không export và không open vô điều kiện** | Lớp proxy **public** trong package **non-exported, non-open** thuộc **dynamic named module**; tên package/module không được bảo đảm |
| Có ít nhất một interface **non-public** | Có package không export/open vô điều kiện | Lớp proxy **non-public** trong package/module của các interface non-public, nếu các điều kiện chung đều hợp lệ |

**Đọc bảng đúng cách:**

- Từ “exported/open” trong phần này là **unqualified exports/opens**, tức mở cho mọi module. `exports p to friend;` hoặc `opens p to mapper;` là **qualified**, không trở thành unqualified export/open.
- Một package được `opens` nhưng không `exports` cho phép truy cập Reflection ở runtime theo luật module, **không phải** API import trực tiếp tại compile time từ module khác.
- **Lớp proxy `public`** trong dynamic module có package **không export** vẫn không cho arbitrary caller quyền dùng public constructor. JDK khuyến nghị **`Proxy.newProxyInstance`** để tạo instance.
- Các tên module sinh ra như `jdk.proxy1` và tên proxy class không phải contract. Không ép ứng dụng phụ thuộc những tên đó.
- Dynamic module có cơ chế đọc các module chứa interface và kiểu trong public signatures, đồng thời có thể được cấp export phù hợp để generated proxy dùng các kiểu ấy. Điều này không xuất toàn bộ package cho host hoặc toàn bộ ứng dụng.

### 8.1. Thực hành với hai named modules

Tạo cây:

~~~text
module-src/
  demo.hidden/
    module-info.java
    demo/hidden/api/HiddenService.java
  demo.host/
    module-info.java
    demo/host/Main.java
~~~

**`module-src/demo.hidden/module-info.java`**

~~~java
module demo.hidden { }
~~~

**`module-src/demo.hidden/demo/hidden/api/HiddenService.java`**

~~~java
package demo.hidden.api;

public interface HiddenService {
    String value();
}
~~~

Interface `HiddenService` là public nhưng package `demo.hidden.api` **không được export** trong `module-info.java`.

**`module-src/demo.host/module-info.java`**

~~~java
module demo.host { }
~~~

Host không `requires demo.hidden` vì ví dụ chỉ lấy class theo tên qua Reflection; dùng `--add-modules demo.hidden` ở runtime để bảo đảm module này nằm trong module graph.

**`module-src/demo.host/demo/host/Main.java`**

~~~java
package demo.host;

import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

public final class Main {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = Main.class.getClassLoader();
        Class<?> contract = Class.forName(
                "demo.hidden.api.HiddenService", false, loader);

        Object proxy = Proxy.newProxyInstance(
                loader,
                new Class<?>[]{contract},
                (instance, method, values) -> "ok");
        Class<?> generated = proxy.getClass();

        System.out.println("interfacePublic="
                + Modifier.isPublic(contract.getModifiers()));
        System.out.println("interfaceExported="
                + contract.getModule().isExported(
                        contract.getPackageName(), Main.class.getModule()));
        System.out.println("proxyPublic="
                + Modifier.isPublic(generated.getModifiers()));
        System.out.println("proxyNamedModule="
                + generated.getModule().isNamed());
        System.out.println("proxyExported="
                + generated.getModule().isExported(
                        generated.getPackageName(), Main.class.getModule()));

        Constructor<?> ctor = generated.getConstructor(InvocationHandler.class);
        try {
            ctor.newInstance((InvocationHandler) (p, m, a) -> "no");
            System.out.println("directConstructor=allowed");
        } catch (IllegalAccessException expected) {
            System.out.println("directConstructor=blocked");
        }
    }
}
~~~

**Bash (Linux/macOS)** — từ thư mục chứa `module-src/`:

~~~bash
javac --release 17 --module-source-path module-src -d modules $(find module-src -name '*.java')
java --module-path modules --add-modules demo.hidden --module demo.host/demo.host.Main
~~~

**PowerShell (Windows)** — tương đương, dùng collection nguồn thay vì `find`:

~~~powershell
$files = Get-ChildItem module-src -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName
javac --release 17 --module-source-path module-src -d modules $files
java --module-path modules --add-modules demo.hidden --module demo.host/demo.host.Main
~~~

**Stdout đã kiểm chứng khi chạy đúng hai module trên:**

~~~text
interfacePublic=true
interfaceExported=false
proxyPublic=true
proxyNamedModule=true
proxyExported=false
directConstructor=blocked
~~~

**Giải thích kết quả:**

1. `interfacePublic=true` vì `HiddenService` là interface public. Tuy nhiên `interfaceExported=false` đối với module `demo.host`: mã host **không thể import/gọi trực tiếp** interface bằng source Java thông thường.
2. `Class.forName(...)` vẫn lấy được đối tượng `Class<?>` khi module đã được resolve và loader nhìn thấy tên. **Khả năng nạp tên không đồng nghĩa khả năng truy cập thành viên**.
3. `Proxy.newProxyInstance` tạo được instance từ interface public trong package không export, nhưng generated class đặt trong **dynamic named module** ở package không export, nên `proxyPublic=true` **không mâu thuẫn** với `proxyExported=false`.
4. `generated.getConstructor(InvocationHandler.class)` có thể tìm được public constructor; việc **thực thi constructor bằng Reflection** từ host vẫn bị chặn vì package chứa generated class không được export cho host.
5. `Proxy.newProxyInstance` đã trả object proxy thành công. Đây là cách chính thức để tạo proxy thay vì cố gọi constructor của generated proxy class.

**Không suy diễn rằng host sẽ có quyền gọi `HiddenService.value()` chỉ vì instance được tạo.** Bài này minh họa việc tạo/định vị proxy, không phải một API public được phép sử dụng qua module boundary. Nếu consumer cần gọi typed method, thư viện nên export một contract SPI phù hợp.

## 9. Cách kiểm tra một tập interface trước khi yêu cầu proxy

Đối với một plugin manager hoặc framework, nên có bước kiểm tra có chủ đích để báo lỗi dễ hiểu. Không nhất thiết tự tái triển khai toàn bộ logic của `Proxy`, nhưng nên log những gì có giá trị cho developer.

### 9.1. Thông tin cần kiểm tra

Với mỗi `Class<?> itf`:

~~~java
System.out.println("name=" + itf.getName());
System.out.println("interface=" + itf.isInterface());
System.out.println("sealed=" + itf.isSealed());
System.out.println("hidden=" + itf.isHidden());
System.out.println("public=" + java.lang.reflect.Modifier.isPublic(itf.getModifiers()));
System.out.println("package=" + itf.getPackageName());
System.out.println("module=" + itf.getModule());
System.out.println("loader=" + itf.getClassLoader());
~~~

Đây là **đoạn mã minh họa trong scope có `itf`**, không phải file độc lập. Tránh in toàn bộ đường dẫn hệ thống hoặc data nhạy cảm vào log sản xuất.

Kiểm tra tiếp:

- Các interface có trùng nhau **theo đối tượng `Class<?>`** không? `Set<Class<?>>` hữu ích, nhưng đừng vô tình sắp xếp lại thứ tự interface khi thứ tự có ý nghĩa.
- Loader được chọn có thể resolve **chính interface** và toàn bộ **types trong public method signatures** không?
- Nếu có interface non-public, các interface ấy có cùng package/module/loader và điều kiện truy cập cần thiết không?
- Các method cùng tên và parameter signature có return types tương thích không?
- Với named module, package được export/open theo kiểu nào, và chính generated proxy module sẽ nằm ở trường hợp nào?
- Consumer có thực sự cần Reflection trên generated proxy class không, hay chỉ cần trả một instance typed theo interface public?

### 9.2. Mã kiểm tra loader visibility (đoạn minh họa)

~~~java
static boolean visibleByName(ClassLoader loader, Class<?> type) {
    try {
        return Class.forName(type.getName(), false, loader) == type;
    } catch (ClassNotFoundException e) {
        return false;
    }
}
~~~

Phương thức này cần đặt **bên trong một class Java**. Nó minh họa một trong các điều kiện quan trọng, **không phải validator hoàn chỉnh**: vẫn cần kiểm tra sealed/hidden, duplicates, non-public package/module, kiểu trong signatures, compatible returns và giới hạn JVM. Không nên thay thế toàn bộ kiểm tra của `Proxy` bằng một helper tự viết chưa bao quát các trường hợp module.

### 9.3. Quy trình lựa chọn giải pháp

~~~text
Cần làm proxy cho class cụ thể?
  -> JDK dynamic proxy không subclass class nghiệp vụ; chọn interface/adapter
      |
      v
Interface là non-hidden và non-sealed?
  -> Không: bỏ interface đó khỏi proxy list hoặc thiết kế contract khác
      |
      v
Loader nhìn thấy các interface và kiểu trong public signatures?
  -> Không: sửa topology module/loader, chia sẻ SPI hoặc loại bỏ lệch phiên bản
      |
      v
Có interface non-public?
  -> Có: xác minh cùng package/module/loader hợp lệ
      |
      v
Các return type trùng method có tương thích?
  -> Không: tách proxy hoặc điều chỉnh contract
      |
      v
Proxy.newProxyInstance(...)
  -> Trả qua interface public hợp pháp; không dựa vào tên class proxy
~~~

## 10. Sai lầm phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng chẩn đoán |
| --- | --- | --- |
| `IllegalArgumentException` với interface sealed | Interface được truyền trực tiếp có `isSealed() == true` | Dùng contract non-sealed hợp lệ, hoặc viết adapter/implementation tường minh |
| `IllegalArgumentException` với class thường | `interfaces` chứa một `Class<?>` không đại diện interface | Kiểm tra `isInterface()` trước |
| `IllegalArgumentException` khi dùng loader riêng | Loader không resolve được chính object `Class<?>` của interface | Kiểm tra `Class.forName(..., false, loader) == itf` |
| Interface có thể resolve nhưng proxy vẫn lỗi | Kiểu trong public method signatures không thấy qua loader | Kiểm tra public methods kể cả kế thừa và các parameter/return types |
| Hai interface package-private không ghép được | Chúng thuộc package hoặc module khác nhau | Tách proxy hoặc công bố SPI public thích hợp |
| Một proxy từ nhiều interface có method trùng tên bị từ chối | Return type không tương thích | So sánh return assignability; tách contract nếu cần |
| `proxy instanceof API` đúng nhưng caller không cast được sang internal interface | Internal interface không accessible cho caller | Trả/gọi qua public exported interface, không ép dùng internal |
| Class proxy `public` nhưng constructor Reflection bị chặn | Generated class nằm trong package non-exported của dynamic module | Dùng `Proxy.newProxyInstance`, không cố mở constructor |
| `Class.forName` tìm được interface nhưng import trực tiếp thất bại | Visibility theo tên khác Java/JPMS accessibility | Kiểm tra `module-info.java` và package exports |
| `ClassCastException` khi cast proxy sang interface “cùng tên” | Hai loader định nghĩa hai `Class<?>` khác nhau | Thống nhất nơi định nghĩa SPI/interface, kiểm tra identity |
| `UndeclaredThrowableException` khi handler ném checked exception | Checked exception không được method interface cho phép | Chọn exception policy phù hợp chữ ký |
| Proxy method trả primitive bị `NullPointerException` | Handler trả `null` cho method primitive | Handler phải trả wrapper tương ứng không null |

Không phải mọi `IllegalArgumentException` đến từ `Proxy` đều giống nhau. Nên log **danh sách interface theo đúng thứ tự**, module, loader, trạng thái sealed/hidden/public và method signatures để tìm đúng rule. Không dựa vào substring của `getMessage()` vì text lỗi không phải compatibility guarantee.

### 10.1. Default method, `Object` methods và handler

Những điểm này không thay đổi điều kiện **tạo** proxy, nhưng cần biết để không nhầm lỗi khi **gọi**:

- `equals`, `hashCode` và `toString` của proxy được dispatch đến handler; `Method` tương ứng có thể có declaring class là `java.lang.Object`.
- Handler nhận `Object[] args`; đối với method không có tham số, `args` có thể `null`. Kiểu primitive của argument sẽ được boxing.
- `InvocationHandler.invokeDefault` (Java 16+) có thể thực hiện default method của proxy interface khi nó hợp lệ; một default method không tự bảo đảm được gọi nếu handler không điều phối nó.
- Handler phải trả giá trị tương thích với return type; `null` cho primitive return gây `NullPointerException`. Checked exception không được khai báo phù hợp có thể bị bọc trong `UndeclaredThrowableException`.
- Đây là **quy tắc invocation sau khi proxy đã tạo thành công**, không phải phép “sửa” được lỗi sealed, loader visibility hay module access.

## 11. Thiết kế thư viện động an toàn và dễ nâng cấp

1. **Tách contract khỏi implementation.** Đặt public SPI/interface ở module/loader mà host và plugin đều nhìn thấy đúng **cùng đối tượng `Class<?>`**. Đừng yêu cầu host compile trực tiếp với package implementation nội bộ.
2. **Export API có chủ đích** trong JPMS nếu consumer cần import/gọi typed methods. Không dùng `opens` cả module để giải quyết lỗi class loader hoặc sealed: hai lỗi đó có nguyên nhân khác.
3. **Sealed hierarchy chỉ dùng khi muốn đóng danh sách direct implementors.** Nếu hệ thống cần plugin runtime tự do, một interface non-sealed chuyên cho extension là lựa chọn tự nhiên hơn so với cố proxy trực tiếp sealed interface.
4. **Ưu tiên interface public ổn định.** Mỗi interface non-public đưa vào proxy thu hẹp nơi class proxy có thể đặt và tính khả dụng của nó. Khi cần bọc cả method internal, tạo adapter/factory trong cùng package/module có quyền rồi xuất kết quả qua public interface hợp lệ.
5. **Kiểm soát topology class loader.** Nạp nhiều bản SPI độc lập dẫn tới cùng binary name nhưng không cùng runtime type; luôn kiểm tra class identity khi có plugin class loader hoặc custom module layer.
6. **Đừng phụ thuộc tên generated class hoặc constructor.** `Proxy.getProxyClass` đã deprecated trong JDK 17; dùng `Proxy.newProxyInstance`. Đừng gọi `setAccessible(true)`/`--add-opens` để né encapsulation chỉ vì muốn tự khởi tạo generated proxy.
7. **Không xem proxy là sandbox.** Handler là mã chạy trong tiến trình; giới hạn module/loader không thay thế authorization, sandbox hệ điều hành, isolation, timeout hoặc audit.
8. **Kiểm thử tổ hợp interface khi phát hành API.** Thêm method với return type xung đột, sealed hóa interface, chuyển package, đổi module exports hoặc thay class loader có thể làm plugin đang hoạt động không còn tạo proxy được.

## 12. Bài tập tự kiểm tra

1. **Phạm vi public:** Dùng ví dụ mục 6, giữ `Greeting` nhưng bỏ `LocalInternal` khỏi mảng proxy. `publicProxy` và `mixedProxyPublic` sẽ thay đổi thế nào? Vì sao?
2. **Khác package:** Chuyển `ForeignInternal` vào package `lab.proxy`, biên dịch lại. Dự đoán kết quả khi ghép nó với `LocalInternal`; liệu chỉ cùng package name nhưng khác defining loader đã đủ chưa?
3. **Sealed:** So sánh `Proxy.newProxyInstance` với `Parent.class` và `Child.class` trong mục 7. Phân biệt “implement trực tiếp sealed interface” và “kế thừa quan hệ sealed thông qua subinterface non-sealed được permit”.
4. **Class loader:** Thay loader tạo proxy public ở mục 6 bằng một loader con có parent là app loader. Dự đoán việc `Class.forName(..., false, childLoader) == Greeting.class`. Vì sao không nên kiểm tra chỉ bằng `type.getClassLoader() == childLoader`?
5. **Signature visibility:** Tạo một public interface có method nhận type thuộc một plugin loader riêng. Thiết kế một loader cho proxy không thể resolve type này; giải thích vì sao việc nạp được interface chưa đủ.
6. **JPMS:** Trong mục 8, thử export `demo.hidden.api` vô điều kiện rồi biên dịch/chạy lại. Dự đoán việc lựa chọn module/package cho proxy. Có nên kiểm tra bằng **tên cụ thể** của generated class không?
7. **Return collisions:** Thay `NumberResult` thành trả `CharSequence` còn `StringResult` vẫn trả `String`. Dự đoán proxy có được tạo không, và vì sao interface order vẫn quan trọng cho method trùng tên?
8. **API design:** Cho một plugin system đang truyền cả package-private `InternalHook` từ hai package khác nhau vào `Proxy`. Đề xuất một public SPI ổn định mà không cần mở rộng visibility của mọi implementation.

## Kết luận

Một JDK dynamic proxy được tạo thành công khi **danh sách interface, class loader và quan hệ accessibility** cùng hợp lệ. Interface phải **non-hidden, non-sealed, không trùng**; loader phải nhìn thấy **đúng đối tượng kiểu** của từng interface và các kiểu trong public method signatures; các interface **non-public phải cùng package/module** hợp lệ; return types ở các method trùng signature phải tương thích. `public` của một interface không đồng nghĩa package JPMS đã export, và `public` của generated proxy không đồng nghĩa class đó mở cho Reflection từ mọi module.

Thiết kế thư viện động nên để host phụ thuộc **contract public được export và chia sẻ qua đúng loader**, để proxy class được sinh ở nơi JDK lựa chọn, và tránh dùng `sealed` trực tiếp cho điểm mở rộng cần implementation ở runtime.

## Tài liệu tham khảo chính thức

- [Java SE 17 — `java.lang.reflect.Proxy`: restrictions, package and module membership, dynamic modules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — `InvocationHandler`: dispatch, checked exceptions, return types](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — `java.lang.Class`: `isInterface`, `isSealed`, `isHidden`, `getModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java Language Specification 17 — `8.1.1.2`: sealed, non-sealed classes; `9.1.1.4`: sealed interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4)
- [Java Language Specification 17 — `7.7`: module declarations, `exports`, `opens`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
