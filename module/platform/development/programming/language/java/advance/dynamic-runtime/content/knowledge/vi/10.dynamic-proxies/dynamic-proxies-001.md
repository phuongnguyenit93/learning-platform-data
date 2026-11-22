# 10.1 Mô hình interface, proxy instance, `InvocationHandler` và đối tượng được ủy quyền

**Ngữ cảnh:** Java Advance → dynamic-runtime → 10. Proxy động.

Java Dynamic Proxy (`java.lang.reflect.Proxy`) cho phép tạo **một object tại runtime triển khai một hoặc nhiều interface**, rồi chuyển các lời gọi phương thức trên object đó đến một `InvocationHandler`. Handler quyết định xử lý lời gọi ra sao: có thể trả kết quả tự tạo, ghi log, kiểm soát quyền, đo thời gian, hoặc **ủy quyền** đến đối tượng thật (delegate/target).

Điểm quan trọng nhất là phân biệt bốn vai trò: **interface định nghĩa hợp đồng**, **proxy instance là object caller đang cầm**, **InvocationHandler là bộ điều phối lời gọi**, và **delegate là object thực thi nghiệp vụ nếu thiết kế có ủy quyền**. Chúng có trách nhiệm khác nhau, không nên gọi lẫn nhau bằng cùng một tên "proxy".

## 1. Bốn vai trò trong kiến trúc

| Thành phần | Bản chất | Trách nhiệm | Điều không nên hiểu nhầm |
| --- | --- | --- | --- |
| **Interface** | Hợp đồng kiểu Java, ví dụ `Store` | Khai báo các method caller được phép gọi; quy định kiểu tham số, return và checked exceptions | Interface không tự lưu delegate và không tự ghi log |
| **Proxy instance** | Object được `Proxy.newProxyInstance(...)` tạo; class phát sinh lúc chạy | Implement các interface đã đăng ký; nhận lời gọi theo chữ ký interface và định tuyến tới handler | Proxy **không phải** object delegate; không tự kế thừa class nghiệp vụ |
| **`InvocationHandler`** | Một object thực thi `InvocationHandler.invoke(proxy, method, args)` | Chứa chính sách interception, định tuyến, tiền/hậu xử lý, exception handling | Handler không bị bắt buộc phải dùng delegate |
| **Delegate / target** | Object thật, thường implement cùng interface | Chạy logic nghiệp vụ khi handler quyết định ủy quyền | Không phải mọi lời gọi trên delegate đều đi qua proxy; direct call có thể bỏ qua handler |

Sơ đồ lời gọi ủy quyền điển hình:

```text
                       Hợp đồng Store (interface)
                          ^               ^
                          | implements    | implements
                          |               |
Caller -------> proxy: Store                target: StoreImpl
   |                  |
   | proxy.find("A")  | dynamic dispatch tới generated proxy method
   |                  v
   |          InvocationHandler.invoke(
   |              proxy, Method find, Object[]{"A"})
   |                  |
   |                  | validate / log / auth / metrics
   |                  v
   |              method.invoke(target, args)
   |                  |
   |                  v
   |           StoreImpl.find("A")
   |                  |
   |             kết quả / exception
   |                  |
   +<---- handler trả về / ném lỗi <----+
```

Trong ví dụ này, caller **chỉ biết `Store`**. Nó không cần biết class proxy được phát sinh tên gì hay handler dùng delegate nào. Handler là **điểm mở rộng** cho cross-cutting concerns (logging, transaction, authorization, caching...) mà vẫn giữ hợp đồng API kiểu tĩnh.

### Lựa chọn ranh giới: proxy không nhất thiết có delegate

Java chỉ yêu cầu `InvocationHandler` xử lý method và trả giá trị/exception phù hợp. Handler có thể thay toàn bộ lời gọi bằng response tổng hợp, gọi service từ xa, truy vấn cache, hoặc từ chối truy cập. Vì vậy cần phân biệt:

- **Proxy với delegate:** handler gọi logic thật, thêm hành vi trước/sau.
- **Proxy không có delegate:** handler tự cung cấp hành vi, ví dụ mô phỏng test/mock, RPC client, lazy endpoint.
- **Proxy nhiều delegate:** handler chọn một target tùy method, tenant, trạng thái circuit breaker hoặc chiến lược định tuyến; đây vẫn là một handler của proxy.

Trong bài này, ta dùng trường hợp phổ biến nhất: handler **giữ reference đến delegate `StoreImpl`** và chuyển lời gọi nghiệp vụ đến nó, đồng thời cho thấy một nhánh mà handler không ủy quyền.

## 2. Vòng đời một dynamic proxy

Một cách nhìn hữu ích là phân biệt **thời điểm tạo** và **thời điểm gọi**.

**Bước 1 — Định nghĩa hợp đồng:** Viết interface với các method caller cần dùng.

```java
public interface Store {
    String find(String sku);
    int stock(String sku);
}
```

Đây là **snippet minh họa**, không phải chương trình Java độc lập theo cấu trúc đã trình bày. Interface có thể được nhiều implementation dùng chung.

**Bước 2 — Có delegate:** Một class như `StoreImpl implements Store` được khởi tạo và sẵn sàng thực hiện nghiệp vụ.

**Bước 3 — Có handler:** Tạo một `InvocationHandler`. Handler có thể giữ reference đến `StoreImpl`, cũng có thể giữ thông tin cấu hình, bộ kiểm tra quyền, logger, metric registry, v.v.

**Bước 4 — Tạo proxy instance:** Gọi:

```java
Store proxy = (Store) Proxy.newProxyInstance(
        Store.class.getClassLoader(),
        new Class<?>[]{Store.class},
        handler);
```

`Proxy.newProxyInstance` sử dụng class loader và danh sách interface để cung cấp một object triển khai những interface đó, và gắn `handler` vào object. Việc gọi `newProxyInstance` **không đồng nghĩa gọi một method nghiệp vụ**. Target thường được tạo riêng trước đó; proxy class và delegate class không phải cùng một type.

**Bước 5 — Caller gọi qua interface:** Ví dụ `proxy.find("A")`. Method của proxy chuyển lời gọi tới `handler.invoke(proxy, method, args)`.

**Bước 6 — Handler quyết định:** Nếu có delegate, handler thường gọi `method.invoke(delegate, args)` (hoặc sử dụng dispatcher khác) và trả kết quả. Có thể kiểm tra input, kiểm soát quyền, ghi log, chuyển exception, thay result.

**Bước 7 — Caller nhận kết quả qua interface:** Caller vẫn thấy return type `String` của `Store.find`, mặc dù `InvocationHandler.invoke` trả `Object` bên trong.

Việc gọi `delegate.find("A")` **trực tiếp** hoàn toàn bỏ qua handler. Vì vậy phải truyền **reference đến proxy** cho consumer muốn được intercept; nếu consumer giữ delegate gốc và gọi nó, interceptor không có cơ hội tham gia.

## 3. Hiểu ba tham số của `InvocationHandler.invoke`

Chữ ký chuẩn:

```java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
```

| Tham số | Giá trị thực | Sử dụng đúng |
| --- | --- | --- |
| `proxy` | **Proxy instance** mà caller vừa gọi, không phải delegate | Nhận diện proxy, xử lý `equals` theo identity, gọi interface default method bằng `InvocationHandler.invokeDefault` |
| `method` | `java.lang.reflect.Method` đại diện cho method interface được gọi; có thể đại diện `equals`/`hashCode`/`toString` của `Object` | Lấy `getName()`, `getDeclaringClass()`, `getParameterTypes()`, `isDefault()`, hoặc invoke trên delegate |
| `args` | `Object[]` chứa đối số của method; **`null` nếu method không nhận tham số** | Xử lý `null` trước khi lặp/ghi log, giữ thứ tự và kiểu giá trị |

Với lời gọi `proxy.find("A")`, handler thường nhận `method.getName().equals("find")` và `args[0].equals("A")`. Với `proxy.refresh()` không tham số, `args` có thể là **`null`**, không phải mảng độ dài 0. Khi cần log an toàn:

```java
Object[] safeArgs = args == null ? new Object[0] : args;
System.out.println(java.util.Arrays.toString(safeArgs));
```

Đây là **snippet** nằm trong `invoke`, không phải chương trình chạy độc lập.

### Kiểu primitive, return type và `void`

Vì `invoke` trả `Object`, Java proxy phải ghép ngược về signature interface:

- Nếu interface nhận primitive (ví dụ `int`), giá trị truyền trong `args` được boxing thành wrapper (`Integer`).
- Nếu interface trả `int`, handler phải trả **`Integer` tương ứng** (hoặc đối tượng hợp lệ đúng loại wrapper); generated proxy sẽ unbox về `int`.
- Handler trả `null` cho method có return primitive sẽ khiến lời gọi trên proxy ném `NullPointerException`.
- Handler trả đối tượng không thể ép sang return type tương ứng có thể gây `ClassCastException`.
- Method trả `void` không đòi return value có ý nghĩa; handler nên trả `null` để dễ hiểu. `method.invoke(delegate,args)` vốn trả `null` với method `void`.
- Nếu method trả reference, handler có thể trả `null` khi hợp đồng nghiệp vụ cho phép.

Đừng giả sử dynamic proxy sẽ tự parse `"7"` thành `int`, tự kiểm soát nullable parameter, hay tự làm conversion ngoài hợp đồng interface. Handler chịu trách nhiệm các bước bổ sung.

### `Method` trong callback không phải "method của delegate"

Thông thường `method.getDeclaringClass()` là interface khai báo method. Cùng một method interface có thể được invoke trên **bất cứ object delegate tương thích** nào:

```java
Object result = method.invoke(delegate, args);
```

Điều kiện: `delegate` phải là instance của declaring interface/class thích hợp; quyền truy cập và quy tắc reflection vẫn áp dụng. Nếu handler chọn một delegate không thực thi interface phù hợp, `Method.invoke` có thể ném `IllegalArgumentException`. Không dùng `method.invoke(proxy, args)` để "chuyển tiếp" vì như vậy thường **gọi lại chính proxy**, quay vào handler lần nữa và tạo vòng lặp vô hạn.

## 4. Chương trình Java 17 hoàn chỉnh: interface, proxy, handler, delegate

Ví dụ độc lập dưới đây kiểm chứng đầy đủ vai trò của bốn thành phần, lời gọi trực tiếp so với lời gọi qua proxy, giá trị trả về primitive/void, method của `Object`, default method và hai chính sách exception.

Tạo file **`DynamicProxyDemo.java`**. Tất cả type đều được đặt trong một file để có thể copy, biên dịch và chạy bằng Java 17 không cần thư viện ngoài JDK.

```java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.util.Arrays;

public class DynamicProxyDemo {
    public interface Store {
        String find(String sku);
        int stock(String sku);
        void refresh();
        default String category() { return "general"; }
        String load(String sku) throws IOException;
    }

    static final class StoreImpl implements Store {
        @Override public String find(String sku) { return "item:" + sku; }
        @Override public int stock(String sku) { return 7; }
        @Override public void refresh() { System.out.println("delegate.refresh"); }
        @Override public String category() { return "special"; }
        @Override public String load(String sku) throws IOException {
            if ("missing".equals(sku)) throw new IOException("not found");
            return "loaded:" + sku;
        }
    }

    static final class LoggingHandler implements InvocationHandler {
        private final Store delegate;

        LoggingHandler(Store delegate) {
            this.delegate = delegate;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "StoreProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new AssertionError(method);
                };
            }
            Object[] safe = args == null ? new Object[0] : args;
            System.out.println("handler.before:" + method.getName() + ":" + Arrays.toString(safe));
            if ("find".equals(method.getName()) && "unhandled".equals(args[0])) {
                System.out.println("handler.throw:IOException");
                throw new IOException("synthetic");
            }
            try {
                Object result = method.isDefault()
                        ? InvocationHandler.invokeDefault(proxy, method, args)
                        : method.invoke(delegate, args);
                System.out.println("handler.after:" + method.getName() + ":" + result);
                return result;
            } catch (InvocationTargetException ex) {
                System.out.println("handler.cause:" + ex.getCause().getClass().getSimpleName());
                throw ex.getCause();
            }
        }
    }

    public static void main(String[] args) {
        Store delegate = new StoreImpl();
        LoggingHandler handler = new LoggingHandler(delegate);
        Store proxy = (Store) Proxy.newProxyInstance(
                Store.class.getClassLoader(),
                new Class<?>[]{Store.class},
                handler);

        System.out.println("isProxy=" + Proxy.isProxyClass(proxy.getClass()));
        System.out.println("sameDelegate=" + (proxy == delegate));
        System.out.println("handlerMatches=" + (Proxy.getInvocationHandler(proxy) == handler));
        System.out.println("direct=" + delegate.find("A"));
        System.out.println("proxied=" + proxy.find("A"));
        System.out.println("stock=" + proxy.stock("A"));
        proxy.refresh();
        System.out.println("default=" + proxy.category());
        System.out.println("delegateDefaultOverride=" + delegate.category());
        System.out.println("toString=" + proxy);
        System.out.println("equalsSelf=" + proxy.equals(proxy));
        System.out.println("equalsDelegate=" + proxy.equals(delegate));
        System.out.println("hashCodeIdentity=" + (proxy.hashCode() == System.identityHashCode(proxy)));

        try {
            proxy.load("missing");
        } catch (IOException ex) {
            System.out.println("caller.declared=" + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }
        try {
            proxy.find("unhandled");
        } catch (UndeclaredThrowableException ex) {
            System.out.println("caller.undeclared=" + ex.getUndeclaredThrowable().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 DynamicProxyDemo.java
java DynamicProxyDemo
```

**Stdout chính xác:**

```text
isProxy=true
sameDelegate=false
handlerMatches=true
direct=item:A
handler.before:find:[A]
handler.after:find:item:A
proxied=item:A
handler.before:stock:[A]
handler.after:stock:7
stock=7
handler.before:refresh:[]
delegate.refresh
handler.after:refresh:null
handler.before:category:[]
handler.after:category:general
default=general
delegateDefaultOverride=special
toString=StoreProxy
equalsSelf=true
equalsDelegate=false
hashCodeIdentity=true
handler.before:load:[missing]
handler.cause:IOException
caller.declared=IOException:not found
handler.before:find:[unhandled]
handler.throw:IOException
caller.undeclared=IOException
```

### Giải thích từng đoạn kết quả

1. `isProxy=true`: class runtime của `proxy` là class do cơ chế `java.lang.reflect.Proxy` sinh ra. **Không** suy luận từ tên class như `$Proxy0`, vì tên là chi tiết triển khai không ổn định.
2. `sameDelegate=false`: `proxy` và `delegate` là hai object khác nhau. Cả hai implement `Store`, nhưng reference identity không trùng.
3. `handlerMatches=true`: `Proxy.getInvocationHandler(proxy)` trả đúng object handler được dùng lúc tạo proxy.
4. `direct=item:A` không có dòng `handler.before`: gọi qua reference `delegate` **bỏ qua proxy**.
5. `proxied=item:A` có log `handler.before:find:[A]` và `handler.after:find:item:A`: lời gọi qua `proxy` đi qua handler trước/sau khi delegate chạy.
6. `stock=7` thể hiện interface method trả primitive `int`, trong khi `Method.invoke` và `InvocationHandler.invoke` giao tiếp qua `Object` (boxing/unboxing phù hợp).
7. `refresh()` không có tham số nên `args` là `null`; handler dùng `safe` để log `[]`. Method trả `void` nên `method.invoke` cho result `null`, hiện ở `handler.after:refresh:null`.
8. `category()` là **default method** trên interface. Handler gọi `InvocationHandler.invokeDefault` nên kết quả là `general`, **không** gọi override `StoreImpl.category()` (đang trả `special`). Vì vậy hai dòng `default=general` và `delegateDefaultOverride=special` khác nhau có chủ đích.
9. `toString`, `equals`, `hashCode` được handler trả lời riêng. Mẫu này chọn identity equality nên `equalsSelf=true`, `equalsDelegate=false`, `hashCodeIdentity=true`; các kết quả deterministic.
10. `StoreImpl.load("missing")` ném `IOException("not found")`. `Method.invoke` bọc nó thành `InvocationTargetException`, handler lấy `getCause()` và ném lại `IOException`. Vì `Store.load` **khai báo `throws IOException`**, caller bắt được `IOException` trực tiếp.
11. Handler cố ý ném `IOException("synthetic")` cho `Store.find("unhandled")`, trong khi `Store.find` **không khai báo** checked exception này. Proxy runtime bọc lỗi thành `UndeclaredThrowableException`. Đây là ví dụ giải thích hợp đồng `throws`, **không phải** hành vi nghiệp vụ nên dùng trong ứng dụng.

## 5. `Proxy.newProxyInstance`: ba đối số có ý nghĩa gì?

Signature:

```java
public static Object newProxyInstance(
        ClassLoader loader,
        Class<?>[] interfaces,
        InvocationHandler h);
```

### `loader`: bối cảnh nạp class proxy

`loader` là class loader dùng để định nghĩa proxy class, phải có khả năng **resolve đúng object `Class<?>` của từng interface** theo tên (gắn với class loader identity). Trong ứng dụng thường, `MyApi.class.getClassLoader()` là lựa chọn tự nhiên nếu proxy triển khai `MyApi`. Với plugin systems, có thể cần thiết kế loader khác phù hợp để cả caller và proxy cùng nhìn thấy interface dùng chung.

Không tự động lấy loader của delegate nếu nó không nhìn thấy interface với cùng runtime type identity. Hai class có cùng fully-qualified name nhưng do loader khác nhau định nghĩa có thể là hai kiểu runtime khác nhau. Proxy có thể không tạo được hoặc không cast được về interface caller mong đợi.

### `interfaces`: danh sách hợp đồng proxy công khai

Ví dụ `new Class<?>[]{Store.class}` yêu cầu proxy implement `Store`. Có thể đăng ký nhiều interface trong một proxy nếu các ràng buộc về method compatibility, class loader, package/module được thỏa.

Những nguyên tắc cơ bản:

- Mỗi phần tử phải là **interface**, không phải class cụ thể như `StoreImpl.class`.
- Danh sách không được chứa các interface trùng lặp.
- Những interface không public khi được đưa vào proxy chịu các ràng buộc package/module chặt hơn; không thể tùy tiện gộp interface package-private đến từ các package/module không tương thích.
- Các signature trùng nhau từ nhiều interface phải có return types tương thích theo quy tắc Proxy API; nếu không, proxy creation có thể bị từ chối.
- **Thứ tự interface trong mảng có ý nghĩa**, nhất là khi nhiều interface có method trùng signature: `Method` nhận ở handler không phải lúc nào cũng phản ánh chính xác static interface type mà caller sử dụng.

Khi bài tập cần nhiều interface, hãy viết unit tests cho signature trùng nhau và kiểm tra `method.getDeclaringClass()`, không chỉ dispatch bằng `getName()`.

### `h`: handler gắn với từng proxy instance

Đây là object chứa cơ chế interception. Handler có thể được chia sẻ giữa nhiều proxy instance nếu logic và state cho phép. Dù object handler là một instance Java bình thường, không nên chia sẻ mutable state không thread-safe nếu nhiều thread có thể gọi proxy.

Tạo proxy yêu cầu `h` khác `null`; việc truyền không đúng các tham số class loader/interface hoặc trùng lặp có thể gây `IllegalArgumentException` hay lỗi kiểm tra module/visibility. Quy trình chuẩn là tạo một proxy từ danh sách interface đã xác định và handler không null; sau đó cast về một trong các interface đã khai báo.

### Proxy không kế thừa `StoreImpl`

JDK dynamic proxy là một subclass của `java.lang.reflect.Proxy` và implement các interface chỉ định. Nó **không extends `StoreImpl`**, không copy field từ delegate và không được cast thành `StoreImpl`. Ví dụ:

```java
Store proxiedStore = (Store) Proxy.newProxyInstance(
        Store.class.getClassLoader(),
        new Class<?>[]{Store.class},
        handler);

// Hợp lệ: caller cầm kiểu interface Store.
// Không hợp lệ: (StoreImpl) proxiedStore
```

Snippet trên giả định các type `Store`, `StoreImpl` và biến `handler` đã có từ ứng dụng; nó **không** phải chương trình độc lập. Khi cần tạo proxy của class không có interface, JDK `Proxy` không phải công cụ thích hợp; cần đổi API sang interface hoặc cân nhắc cơ chế subclass/bytecode generation riêng và các giới hạn của cơ chế đó.

## 6. `InvocationHandler` không bắt buộc ủy quyền: cấu trúc handler điển hình

Handler tối giản có thể được viết:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("find")) {
        return "fixture-value";
    }
    throw new UnsupportedOperationException(method.getName());
};
```

Đây là **snippet minh họa** một mock handler, không phải ứng dụng độc lập. Nếu gắn với interface `Store`, handler đang tự trả một chuỗi cho `find` mà không gọi `StoreImpl`. Mỗi method còn lại sẽ lỗi nếu caller gọi; vì vậy production code phải định nghĩa rõ chính sách xử lý toàn bộ interface methods cần hỗ trợ (bao gồm các method của `Object`).

Handler ủy quyền thường có các bước logic:

```text
invoke(proxy, method, args)
   |
   +-- Object.equals / hashCode / toString?
   |      +-- chính sách identity hay semantic equality
   |
   +-- Kiểm tra quyền / validate / log trước
   |
   +-- Method default?
   |      +-- gọi default method của interface, nếu đó là chủ đích
   |
   +-- Delegate branch
   |      +-- method.invoke(delegate, args)
   |      +-- unwrap InvocationTargetException
   |
   +-- Ghi nhận kết quả / metric
   |
   +-- Return object tương thích với return type của interface
```

Tùy ứng dụng, có thể bỏ branch default, đổi delegate, gắn cache, trả response synthetic hoặc gọi một remote client. Điều quan trọng là **giao kèo method** vẫn phải được giữ: kiểu trả về, checked exceptions, thread-safety, identity semantics.

## 7. Ba nhóm lời gọi cần xử lý cẩn thận

### 7.1 Method nghiệp vụ được khai báo trong interface

Các method như `find`, `stock` và `load` xuất hiện trong `Store`. Trong handler, `method` tương ứng với method interface. Nếu delegate implement cùng interface, `method.invoke(delegate,args)` là cách ủy quyền dễ hiểu, dù cần xử lý `InvocationTargetException`.

Với method overload, **không dispatch chỉ bằng tên**. Ví dụ hai method `find(String)` và `find(long)` có tên giống nhau; phân biệt bằng `method.getParameterTypes()`, `method.getReturnType()` hoặc so sánh với `Method` đã lookup trước đó. Dispatch dựa trên `getName()` đủ cho ví dụ nhỏ, nhưng dễ sai khi API mở rộng.

### 7.2 Method của `Object`: `equals`, `hashCode` và `toString`

Các lời gọi đến ba method này trên proxy cũng được gửi đến handler; `Method` tương ứng có `getDeclaringClass() == Object.class`. Điều đó đúng ngay cả khi interface khai báo một method có cùng signature công khai.

Trong chương trình trên, handler chọn:

```java
case "toString" -> "StoreProxy";
case "hashCode" -> System.identityHashCode(proxy);
case "equals" -> proxy == args[0];
```

Snippet này là một phần `switch` trong `InvocationHandler.invoke`. Nó đưa ra một chính sách **identity equality** nhất quán: proxy chỉ bằng chính nó và `hashCode` đi theo identity. Với một proxy làm value object, ứng dụng có thể chọn semantic equality, nhưng phải đảm bảo `equals` đối xứng, bắc cầu, nhất quán và tương thích `hashCode`.

**Sai lầm phổ biến:** Trong handler, ghi log như `System.out.println(proxy)` sẽ gọi `proxy.toString()`, quay trở lại chính handler. Nếu nhánh xử lý `toString` cũng lại log `proxy`, có thể dẫn đến đệ quy vô hạn. Dùng identifier an toàn hoặc gọi `System.identityHashCode(proxy)` thay vì tự in `proxy` trong handler. Cũng không gọi `method.invoke(proxy,args)` để ủy quyền, vì sẽ quay lại handler.

Các method `Object` khác như `getClass()` không phải method proxy override để gửi qua handler theo cùng cơ chế; `getClass()` là `final` và sẽ phản ánh **class của proxy**, không phải delegate.

### 7.3 Default methods trên interface

Java interface có thể khai báo `default` method, ví dụ `Store.category()`. Proxy vẫn định tuyến lời gọi default method đến handler; handler cần chọn **cách thực thi**.

Có hai lựa chọn đáng phân biệt:

- **Ủy quyền qua delegate:** `method.invoke(delegate,args)` sẽ dispatch theo implementation của delegate, bao gồm **override** của delegate. Trong demo, `StoreImpl.category()` trả `"special"`.
- **Gọi default method của interface qua proxy:** `InvocationHandler.invokeDefault(proxy, method, args)` gọi đúng default implementation được phép trên proxy; trong demo trả `"general"`.

`InvocationHandler.invokeDefault` có từ Java 16, nên dùng tốt trên Java 17. Method truyền vào phải là default method hợp lệ được proxy interface khai báo hoặc kế thừa; API có những ràng buộc đặc biệt với method override nhiều tầng. Không dùng `method.invoke(proxy,args)` để "gọi default" vì cách đó lại dispatch đến handler.

Đừng nghĩ dynamic proxy "tự chạy default method khi không có override". Handler vẫn kiểm soát lời gọi; nếu handler không chủ động gọi default hoặc delegate, default body có thể không bao giờ chạy.

## 8. Ngoại lệ khi delegate hoặc handler thất bại

Có **hai lớp giao tiếp** cần phân biệt:

1. **Handler → delegate bằng Reflection:** `method.invoke(delegate,args)`.
2. **Proxy → caller:** handler trả object hoặc ném `Throwable` ra ngoài `InvocationHandler.invoke`.

Nếu body của delegate ném exception, `Method.invoke` thường bọc lỗi thực trong `InvocationTargetException`. Handler nên lấy `getCause()` và xử lý/ném lại **nguyên nhân nghiệp vụ**, thay vì đưa wrapper Reflection ra ngoài theo cách gây sai hợp đồng `throws`:

```java
try {
    return method.invoke(delegate, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
```

Snippet này thuộc `InvocationHandler.invoke` với `throws Throwable`, không phải chương trình độc lập.

### Quy tắc checked exceptions

| Exception handler ném ra | Interface method khai báo | Caller thấy gì? |
| --- | --- | --- |
| `RuntimeException` hoặc `Error` | Không cần khai báo | Lỗi unchecked truyền trực tiếp |
| `IOException` | Có `throws IOException` | `IOException` đi tới caller |
| `IOException` | Không có `throws IOException` (hoặc supertype phù hợp) | Proxy bọc bằng `UndeclaredThrowableException` |
| `InvocationTargetException` chưa unwrap | Method chỉ khai báo `IOException` | Wrapper là checked exception khác; có thể bị proxy bọc `UndeclaredThrowableException` |
| `IllegalArgumentException` từ handler | Không cần khai báo | Truyền như unchecked exception |
| `NullPointerException` do handler tự dereference null | Không cần khai báo | Truyền như unchecked exception |

Mẫu chính là **không để `InvocationTargetException` lộ ra ngoài handler nếu đó chỉ là wrapper do `Method.invoke` tạo**. Nhưng nếu code đích cố ý ném một `InvocationTargetException` như ngoại lệ nghiệp vụ (hiếm), cần phân loại theo thiết kế thực tế.

Trong chương trình:

- `load("missing")`: delegate ném `IOException`, handler unwrap, interface khai báo checked exception → caller bắt `IOException`.
- `find("unhandled")`: handler cố ý ném `IOException` nhưng `find` không khai báo → caller thấy `UndeclaredThrowableException`. Dùng `getUndeclaredThrowable()` để xem exception gốc.

Nếu một proxy implement **nhiều interface có method cùng chữ ký** nhưng khai báo những checked exceptions khác nhau, tập checked exception handler được phép ném có thể bị hạn chế hơn một interface đơn lẻ. Xem `Proxy` Javadoc và viết test trước khi gộp interfaces phức tạp.

### Lỗi về kiểu trả về và đối số

Cả `InvocationHandler.invoke` lẫn `Method.invoke` dùng object-level API, nhưng hợp đồng method của interface vẫn chặt chẽ:

- Với `Store.stock(String)` trả `int`, handler cần trả `Integer`. Trả `"7"` không tự parse thành `int`.
- Nếu handler trả `null` cho `int`, caller nhận `NullPointerException` khi proxy unbox.
- Nếu handler trả object không phù hợp với `String`, caller nhận `ClassCastException`.
- `args` bằng `null` cho method không tham số không có nghĩa caller đã truyền một đối số `null`.
- Nếu delegate không implement declaring interface của `method`, việc `method.invoke(delegate,args)` không tạo được call hợp lệ và có thể ném `IllegalArgumentException`.

Cần tách lỗi binding/compatibility của proxy, lỗi Reflection trong handler, và lỗi nghiệp vụ do delegate ném.

## 9. Quy tắc công khai API, class loader và module

Dynamic proxy là công cụ runtime, nhưng **không tự vượt qua Java access controls**. Khi thiết kế hợp đồng trong hệ plugin, microservice client hoặc framework:

1. **Interface phải chia sẻ đúng runtime type identity:** caller, handler và proxy phải cùng hiểu `Class<?>` của interface. Với plugin loader, đừng chỉ so tên bằng chuỗi.
2. **Class loader tạo proxy phải nhìn thấy các interface được yêu cầu.** Nếu loader resolve cùng tên sang class khác, proxy creation hoặc cast có thể thất bại.
3. **Non-public interfaces có ràng buộc package/module.** Không được giả định một loader bất kỳ có thể implement mọi tập interface riêng tư.
4. **JPMS có `exports`/`opens` riêng:** Public API trong named module cần được tiếp cận theo quy tắc module. Nếu handler cần reflection vào private members của delegate, `setAccessible`/`privateLookupIn` chịu điều kiện module/open-package tương ứng.
5. **Đừng đồng nhất tính public của interface và tính public của implementation.** Caller làm việc qua interface; handler có thể giữ implementation package-private/private nội bộ khi quyền và cơ chế ủy quyền cho phép.
6. **Không cast proxy thành implementation class.** Ngay cả khi target và proxy implement cùng interface, class identity của chúng khác nhau.

**Ví dụ thiết kế package:** Đặt `api.Store` làm hợp đồng được chia sẻ (và export nếu là named module); đặt `impl.StoreImpl` phía implementation; cung cấp một factory trả về `Store` proxy cho caller. Consumer không cần biết `StoreImpl` hoặc handler class cụ thể. Đây là cách tách cross-cutting concerns khỏi business code.

## 10. Những hạn chế quan trọng của JDK Dynamic Proxy

### Chỉ proxy interface, không tự động proxy class cụ thể

`java.lang.reflect.Proxy` tạo instance implement interfaces. Nó không tạo subclass của `final class` hay bắt chặn method không nằm trong interface hợp đồng để người gọi tiếp cận qua kiểu class cụ thể. Nếu cần intercept method của class implementation không nằm trong interface, JDK Dynamic Proxy không thực hiện việc đó chỉ nhờ tạo proxy.

Một số framework dùng subclass proxy hoặc bytecode generation riêng để hỗ trợ tình huống khác. Đây là **cơ chế khác**, có ràng buộc riêng với `final`, constructor, module và identity; không nên nhầm với core JDK interface proxy.

### Internal call và self-invocation

Giả sử `StoreImpl.find` tự gọi `this.stock(...)` trên cùng implementation object. Nếu handler chỉ chuyển tiếp `find` qua `method.invoke(delegate,args)`, lời gọi `this.stock` bên trong delegate **không đi qua proxy**; nó là lời gọi nội bộ của delegate. Đó là bẫy thường gặp khi áp dụng logging, authorization hoặc transaction ở lớp proxy: chỉ **lời gọi thực sự đi qua reference proxy** mới được intercept.

Nếu cần các lời gọi nội bộ cũng chạy qua interceptor, phải thiết kế lại điểm gọi, sử dụng proxy reference có kiểm soát hoặc chuyển hành vi quan trọng vào lớp domain/service riêng. Không cố "sửa" bằng cách cho handler gọi lại chính proxy mà không có chiến lược kết thúc vòng lặp.

### Proxy không làm code trở nên thread-safe

Proxy và handler có thể được dùng từ nhiều thread. Nếu handler lưu cache mutable, sequence number hoặc delegate không thread-safe, dynamic proxy **không** tự đồng bộ chúng. Với logging và metrics, ưu tiên counters/registries thread-safe; với delegate, áp dụng quy tắc concurrency của service đó.

### Hiệu năng phụ thuộc workload

Qua proxy phát sinh ít nhất một lớp dispatch tới handler và có thể thêm Reflection invocation, logging hoặc validation. JIT có thể tối ưu một số đường gọi ổn định, nhưng không thể suy ra mọi proxy "nhanh hơn" hoặc "chậm đến mức không dùng được". Đo thực tế trong môi trường production và tránh tạo lại proxy ở mỗi lần gọi nếu proxy và cấu hình được dùng lâu dài.

### Quản lý vòng đời và class loader

JDK có cơ chế quản lý class proxy theo tổ hợp loader/interface; không nên tự giữ vô hạn cache strong references đến class loader, proxy instances, Method objects hoặc handlers của plugin vừa unload. Trong hệ hot-reload, bảo đảm lifecycle của proxy/handler/delegate phù hợp vòng đời class loader để tránh giữ lại phiên bản plugin cũ trong bộ nhớ.

## 11. Anti-patterns và cách sửa

| Anti-pattern | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Handler gọi `method.invoke(proxy,args)` để ủy quyền | Dispatch lại proxy → handler recursion | Gọi trên `delegate` hoặc thực thi branch khác rõ ràng |
| Handler giả sử `args.length` luôn hợp lệ | Method không tham số có `args == null` | Chuẩn hóa null thành mảng rỗng khi cần |
| Log `proxy.toString()` ngay trong xử lý `toString` | Có thể đệ quy qua chính handler | Tách nhánh `Object`, dùng identity metadata an toàn |
| Trả `null` cho method return `int` | Proxy cần unbox wrapper → NPE | Trả `Integer` có giá trị phù hợp |
| Trả `String` cho method return `long` | Kiểu trả về không tương thích → ClassCastException | Chuẩn hóa kiểu ở handler theo đúng interface |
| Ném nguyên `InvocationTargetException` do delegate | Che exception nghiệp vụ và có thể bị proxy wrap | Unwrap `getCause()` khi chuyển tiếp |
| Handler ném checked exception không được method khai báo | Proxy sẽ bọc `UndeclaredThrowableException` | Giữ hợp đồng `throws`, dùng unchecked domain exception nếu phù hợp |
| Cast proxy thành `StoreImpl` | Proxy chỉ implement interface, không kế thừa implementation | Caller giữ kiểu `Store` |
| Gọi trực tiếp `delegate` nhưng chờ log proxy | Bỏ qua interception | Đưa proxy vào nơi consumer gọi |
| Chỉ dispatch theo `method.getName()` | Overload/duplicate signatures có thể bị xử lý sai | Xét full signature và interface context |
| Tin rằng default method tự chạy | Default call được gửi tới handler | Chọn `invokeDefault` hoặc ủy quyền có chủ đích |
| Dùng class loader bất kỳ | Không nhìn thấy cùng interface runtime type | Dùng loader tương thích với API contract |
| Giữ full mutable state trong singleton handler không đồng bộ | Race condition | Thiết kế thread-safe hoặc giới hạn scope handler |
| Coi dynamic proxy là biên giới bảo mật chắc chắn | Caller có thể giữ delegate gốc và bỏ qua proxy | Bảo vệ ở tầng service/data và không cấp reference bypass |

## 12. Debug một lời gọi không đi qua handler

Điều tra theo thứ tự:

1. **Object caller đang cầm là proxy hay delegate?** Dùng `Proxy.isProxyClass(obj.getClass())` khi obj hợp lệ. Nếu `false`, có thể caller đang dùng implementation object trực tiếp.
2. **Proxy được tạo cho interface nào?** Kiểm tra danh sách interface trong factory và kiểu reference consumer nhận.
3. **Handler có gắn đúng instance?** Với object đã được xác minh là proxy, `Proxy.getInvocationHandler(proxy)` có thể giúp đối chiếu.
4. **Lời gọi có phải method interface không?** Final method của `Object` như `getClass()` không được dispatch qua handler như các method interface.
5. **Có internal call bên trong delegate không?** Những lời gọi trên `this` có thể bỏ qua proxy.
6. **Handler có branch early-return hoặc cache hit không?** Việc không thấy log delegate chưa chắc handler không chạy.
7. **Handler có tạo vòng lặp?** Kiểm tra `method.invoke(proxy,args)` và cách xử lý `toString`/`equals`.
8. **Có method overload hoặc duplicate signature?** Log `method.toGenericString()`, `method.getDeclaringClass()`, danh sách `getParameterTypes()`.
9. **Exception nằm ở lớp nào?** `InvocationTargetException` trong Reflection delegation, `UndeclaredThrowableException` ở proxy boundary, lỗi kiểu return khi generated proxy chuyển từ `Object` sang contract type.
10. **Nếu lỗi riêng cho plugin/module, xác minh class loader, module exports/opens và runtime class identity.**

Đoạn debug sau là **snippet** trong một handler đã có `method` và `args`, không phải ứng dụng độc lập:

```java
System.out.println("declaring=" + method.getDeclaringClass().getName());
System.out.println("signature=" + method.toGenericString());
System.out.println("default=" + method.isDefault());
System.out.println("argCount=" + (args == null ? 0 : args.length));
```

Tránh in toàn bộ `args` trong production nếu đối số chứa mật khẩu, token, PII hoặc object có `toString` tốn kém/có side effect. Log tên method, số đối số, thời lượng hoặc các metadata đã được phép thay vì rò rỉ dữ liệu.

## 13. Bài tập kiểm tra kiến thức

**Câu 1.** Interface `Service` có method `run()`. Consumer cầm reference `Service proxy`. Call `proxy.run()` sẽ đi qua những object nào trong mô hình có delegate?

**Đáp án:** Caller → proxy instance → `InvocationHandler.invoke` → delegate (nếu handler chọn ủy quyền) → handler → proxy/caller. Interface là hợp đồng kiểu, không phải một object thực thi riêng.

**Câu 2.** Một handler có bắt buộc phải giữ delegate không?

**Đáp án:** Không. Handler có thể trả response synthetic, gọi remote service, mock hành vi hoặc từ chối truy cập. Delegate chỉ là một lựa chọn thiết kế.

**Câu 3.** Trong `InvocationHandler.invoke`, biến `proxy` có phải target implementation không?

**Đáp án:** Không. `proxy` chính là object runtime proxy caller vừa gọi. Delegate là reference khác do handler giữ hoặc lựa chọn.

**Câu 4.** Interface có `void refresh()`. `args` trong handler có giá trị gì và handler nên trả gì?

**Đáp án:** Với method không tham số, `args` là `null`. Handler nên trả `null` cho `void`, và có thể chuẩn hóa thành mảng rỗng khi cần lặp/log.

**Câu 5.** Interface có `int stock()`. Handler trả `null` thì kết quả gì?

**Đáp án:** Khi proxy chuyển giá trị `Object` thành primitive `int`, `null` không thể unbox → `NullPointerException`.

**Câu 6.** Có thể cast một instance do `Proxy.newProxyInstance` tạo thành `StoreImpl` không?

**Đáp án:** Không, trừ các quan hệ kiểu đặc biệt không áp dụng ở mô hình JDK proxy chuẩn: proxy implement `Store`, không extends `StoreImpl`. Hãy làm việc qua interface.

**Câu 7.** Vì sao `method.invoke(proxy, args)` trong handler có nguy cơ `StackOverflowError`?

**Đáp án:** Nó gọi method trên chính proxy, proxy lại gọi handler, handler lại invoke proxy... Thực thi không bao giờ tới delegate nếu không có branch kết thúc phù hợp.

**Câu 8.** Phương thức default `Store.category()` trả `"general"`, nhưng `StoreImpl` override trả `"special"`. Muốn gọi đúng default interface trên proxy trong Java 17 thì làm gì?

**Đáp án:** Trong handler, dùng `InvocationHandler.invokeDefault(proxy, method, args)` với `method` default hợp lệ. Gọi `method.invoke(delegate,args)` sẽ dispatch theo implementation của delegate và có thể trả `"special"`.

**Câu 9.** Delegate ném `IOException` và method interface có `throws IOException`. Handler đã dùng `method.invoke(delegate,args)`. Cần làm gì để caller nhận đúng `IOException`?

**Đáp án:** Bắt `InvocationTargetException`, ném lại `ex.getCause()`. Vì interface khai báo checked exception đó, proxy chuyển nó tới caller theo hợp đồng.

**Câu 10.** Handler ném một checked `IOException` cho method interface không khai báo checked exceptions. Caller thấy gì?

**Đáp án:** `UndeclaredThrowableException`, với `getUndeclaredThrowable()` chứa `IOException` gốc.

**Câu 11.** Có phải mọi lời gọi nội bộ `this.method()` trong delegate đều bị intercept vì delegate từng được gọi qua proxy?

**Đáp án:** Không. Chỉ lời gọi qua reference proxy mới đi tới handler. Lời gọi nội bộ trên delegate có thể chạy trực tiếp không qua proxy.

**Câu 12.** Proxy class có cùng class name trên các lần chạy không? Có nên dựa vào tên `$Proxy0`?

**Đáp án:** Không nên. Tên/lớp do runtime sinh là chi tiết triển khai; sử dụng `Proxy.isProxyClass`, interface và `Proxy.getInvocationHandler` để xác minh thay vì parse tên generated class.

**Câu 13.** Một interface `Repository` và một class `RepositoryImpl` cùng được tải qua nhiều class loaders. Vì sao gọi `Proxy.newProxyInstance` đôi khi lỗi dù tên interface giống nhau?

**Đáp án:** Runtime type identity bao gồm defining class loader. Loader dùng tạo proxy phải resolve **đúng `Class<?>` của interface** mà caller và handler thỏa thuận; cùng chuỗi tên không đủ.

**Câu 14.** Có thể gộp hai interface vào một proxy rồi chỉ cần phân biệt method bằng tên không?

**Đáp án:** Không nên. Có overload và duplicate signatures; cần xét đầy đủ method signature, declaring interface và compatibility rules. Có trường hợp proxy runtime truyền `Method` đại diện cho interface đứng trước trong danh sách.

**Câu 15.** Handler dùng `proxy.equals(delegate)` để kiểm tra delegate có cùng object không. Tại sao trả `false` ở demo?

**Đáp án:** Demo chọn identity equality: handler trả `proxy == args[0]`. Proxy và delegate là hai instance khác nhau. Mô hình hoàn toàn có thể chọn semantic equality khác nhưng phải giữ contract `equals`/`hashCode`.

## 14. Tóm tắt cần nhớ

- **Interface** là hợp đồng; **proxy instance** là object caller sử dụng; **InvocationHandler** nhận và xử lý lời gọi; **delegate** là object nghiệp vụ nếu handler quyết định ủy quyền.
- `Proxy.newProxyInstance(loader, interfaces, handler)` tạo một proxy implement các interface đã chỉ định; **không** biến delegate thành proxy và **không** tạo subclass của implementation class.
- `invoke(proxy, method, args)` nhận proxy instance, `Method` và `Object[]`; với method không tham số, `args` có thể `null`.
- Khi ủy quyền, dùng `method.invoke(delegate, args)` **không phải** `method.invoke(proxy,args)`; nếu delegate ném lỗi thì cân nhắc unwrap `InvocationTargetException`.
- Return type và `throws` của interface vẫn được giữ: primitive cần wrapper, checked exception không khai báo bị bọc `UndeclaredThrowableException`.
- `equals`, `hashCode` và `toString` của proxy đi qua handler; phải có chính sách identity/equality an toàn và tránh đệ quy.
- Default methods vẫn do handler quyết định; Java 17 có `InvocationHandler.invokeDefault` để gọi đúng implementation default của interface.
- **Direct calls, self-invocation và implementation-only methods không tự đi qua proxy.** Consumer cần cầm proxy reference để interception hoạt động.
- Class loader, interface visibility và module boundaries rất quan trọng trong ứng dụng có plugin/hot reload; proxy không tự vượt Java access controls.

### Tài liệu chính thức (Java SE 17)

- [Oracle — `java.lang.reflect.Proxy`, dynamic proxy class và `newProxyInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Oracle — `InvocationHandler.invoke` và `InvocationHandler.invokeDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Oracle — `Method.invoke` và `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Oracle — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)