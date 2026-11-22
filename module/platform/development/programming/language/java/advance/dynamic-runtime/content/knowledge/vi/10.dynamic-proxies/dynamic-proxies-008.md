# 10.8. Thiết kế hành vi equals, hashCode và toString cho proxy động

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao `equals(Object)`, `hashCode()` và `toString()` trên **JDK dynamic proxy** đều được chuyển tới `InvocationHandler.invoke` thay vì tự động hành xử như một đối tượng `Object` thông thường.
- Nhận biết chính xác các lời gọi Object method bằng đối tượng `Method`, kể cả khi interface của proxy **khai báo lại** ba chữ ký này.
- Thiết kế hai chính sách rõ ràng: **proxy identity** (mỗi proxy là một thực thể riêng) và **logical/key equality** (các proxy cùng danh tính nghiệp vụ được xem như bằng nhau).
- Giữ các hợp đồng `equals`–`hashCode` nhất quán để sử dụng đúng trong `HashMap`, `HashSet` và các cấu trúc dữ liệu dựa trên hash.
- Viết `toString()` hữu ích nhưng không gây đệ quy, không lộ thông tin nhạy cảm và không thực hiện thao tác ngoài dự kiến.
- Phát hiện lỗi vòng lặp `method.invoke(proxy, ...)`, “forward hết sang target”, trả về sai kiểu và vấn đề đối xứng khi so sánh với target hoặc các proxy từ thư viện khác.

**Phạm vi:** Bài nói về proxy động chuẩn của JDK được tạo bằng `java.lang.reflect.Proxy`. Những thư viện tạo subclass proxy bằng bytecode (ví dụ subclass-based interceptor) có thể có cơ chế Object methods khác; không tự đồng nhất chúng với JDK dynamic proxy.

## 1. Tại sao equals, hashCode, toString cần được thiết kế riêng?

JDK dynamic proxy là một đối tượng được tạo lúc chạy, triển khai một hoặc nhiều interface do ta chọn. Thay vì chứa trực tiếp logic của từng phương thức interface, proxy chuyển lời gọi vào một `InvocationHandler`:

~~~text
Ứng dụng gọi: proxy.execute("A")
            |
            v
Lớp proxy do JDK sinh
            |
            v
handler.invoke(proxy, Method, Object[] {"A"})
            |
            v
Handler quyết định trả dữ liệu, ủy quyền hay báo lỗi
~~~

Ba lời gọi sau cũng đi qua handler:

~~~java
// Fragment: proxy là một JDK dynamic proxy đã được khởi tạo.
boolean same = proxy.equals(other);
int code = proxy.hashCode();
String description = proxy.toString();
~~~

**Điểm đặc biệt:** Theo hợp đồng `java.lang.reflect.Proxy` (Java 17), các lời gọi `equals`, `hashCode`, `toString` được mã hóa và chuyển tới handler **như lời gọi phương thức của interface**. Đối tượng `Method` truyền cho `invoke` có `getDeclaringClass() == Object.class` đối với ba chữ ký đó.

Ngay cả nếu interface **tự khai báo lại** một trong ba method, `Method` nhận trong handler vẫn do `java.lang.Object` khai báo. Đây là quy tắc ưu tiên riêng cho ba Object methods trong JDK proxy.

| Lời gọi | Method nhận tại `invoke` | `args` | Handler nên trả về |
| --- | --- | --- | --- |
| `proxy.equals(x)` | `Object.equals(Object)` | Một phần tử, có thể là `null` | `Boolean`, được unbox thành `boolean` |
| `proxy.hashCode()` | `Object.hashCode()` | Không có đối số; `args` thường là `null` | `Integer`, được unbox thành `int` |
| `proxy.toString()` | `Object.toString()` | Không có đối số; `args` thường là `null` | `String` |

Không phải mọi phương thức kế thừa từ `Object` đều được chuyển vào handler. Ví dụ `getClass()`, `wait()`, `notify()` và `notifyAll()` vẫn hành xử như các public final method của `Object`; proxy không override chúng theo cơ chế ba phương thức trên.

### 1.1. Nhận diện Object methods an toàn

Trong một handler phục vụ các interface thông thường, có thể phân nhánh:

~~~java
// Fragment: nằm bên trong InvocationHandler.invoke(...).
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "equals" -> proxy == args[0];
        case "hashCode" -> System.identityHashCode(proxy);
        case "toString" -> "ServiceProxy";
        default -> throw new UnsupportedOperationException(method.getName());
    };
}
~~~

Đây là **fragment**, không phải chương trình độc lập; các biến `method`, `proxy`, `args` là tham số của `InvocationHandler.invoke`. Với phương thức `equals`, `args` chứa một đối số, ngay cả khi đối số là `null`. Với `hashCode` và `toString`, không được giả định `args` luôn là một mảng rỗng; nó có thể là `null`.

So khớp `getDeclaringClass() == Object.class` ở đây là quyết định có căn cứ trong đặc tả JDK proxy. Chỉ `method.getName().equals("equals")` mà không xét chữ ký/ngữ cảnh có thể gây nhầm lẫn nếu code xử lý nhiều loại phương thức hoặc adapter tự thiết kế.

### 1.2. Có “mặc định Java” không?

Nếu viết `class X {}` rồi không override Object methods, class thường kế thừa hành vi identity equality từ `Object`. Nhưng JDK dynamic proxy **sinh phần override** cho ba phương thức nói trên và ủy quyền cho handler. Vì vậy handler **phải quyết định** semantics.

Nếu handler không phân biệt Object methods và lập tức gọi `method.invoke(target, args)`, kết quả `equals` có thể vi phạm hợp đồng của Java. Nếu handler trả `null` cho `hashCode`, lời gọi primitive return sẽ bị lỗi unboxing. Không nên để ba method này trở thành “trường hợp tình cờ” trong một nhánh delegation chung.

## 2. Hợp đồng equals, hashCode và toString phải được giữ

### 2.1. Hợp đồng equals(Object)

Một phép so sánh bình đẳng đúng cần:

1. **Reflexive:** Với đối tượng `x` khác null, `x.equals(x)` phải `true`.
2. **Symmetric:** `x.equals(y)` và `y.equals(x)` phải có cùng giá trị.
3. **Transitive:** Nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)`.
4. **Consistent:** Nếu các thông tin tham gia so sánh không thay đổi, nhiều lần gọi cho cùng kết quả.
5. **Non-null:** `x.equals(null)` luôn `false`.

Phải quyết định **định nghĩa danh tính** trước khi viết code. Với proxy, lựa chọn thường gặp là danh tính **đối tượng proxy**, **đối tượng target**, hoặc **khóa nghiệp vụ**. Không có một quy tắc duy nhất áp dụng được cho mọi hệ thống.

### 2.2. Hợp đồng hashCode()

Bất biến quan trọng:

~~~text
Nếu x.equals(y) == true
=> x.hashCode() == y.hashCode()
~~~

Chiều ngược lại **không bắt buộc**: hai đối tượng khác nhau vẫn có thể trùng hash code. Giá trị hash code cũng **không phải** mã định danh duy nhất có thể lưu vào database hoặc truyền qua phiên chạy JVM khác.

Nếu dùng proxy làm key của `HashMap` hoặc phần tử của `HashSet`, hash và các trường ảnh hưởng tới equals phải **ổn định trong suốt thời gian đối tượng nằm trong collection**. Nếu hash thay đổi sau khi thêm vào set, việc tìm lại key có thể thất bại.

### 2.3. Vai trò của toString()

`toString()` không bắt buộc phải là ID toàn cục; mục tiêu thường là một biểu diễn **đủ ý nghĩa để debug**, ổn định theo thiết kế, không gây side effects. Hạn chế:

- Không gọi `proxy.toString()` từ chính handler xử lý `toString()` của proxy đó (đệ quy).
- Không dựa vào tên lớp proxy được sinh ra như một API ổn định.
- Không in secret, token, mật khẩu, nội dung request cá nhân hoặc toàn bộ dữ liệu target một cách tự động.
- Tránh truy vấn mạng/DB trong `toString()`, vì debugger, logger hoặc IDE có thể gọi nó ngoài dự tính.
- Định dạng có thể dùng tên interface + khóa đã lọc, ví dụ `ServiceProxy[id=order-7]`, nếu chính sách bảo mật cho phép hiển thị ID đó.

## 3. Chọn chính sách equality trước khi code

| Chính sách | Khi hai proxy bằng nhau | `hashCode` hợp lý | Tình huống sử dụng |
| --- | --- | --- | --- |
| **Proxy identity** | Chỉ khi `proxyA == proxyB` | `System.identityHashCode(proxy)` | Interceptor, adapter độc lập, nơi mỗi wrapper là thực thể riêng |
| **Stable business key** | Hai proxy cùng **loại hợp đồng** và cùng khóa không đổi | `key.hashCode()` hoặc kết hợp các trường bất biến của key | Client proxy cho resource, service handle có ID, cache |
| **Target identity** | Hai proxy tham chiếu **cùng target instance** theo quy tắc đã thống nhất | `System.identityHashCode(target)` nếu equality thật sự dựa vào `target == otherTarget` | Một số wrapper nội bộ |
| **Target value equality** | Hai target bằng nhau theo `target.equals(otherTarget)`, trong **một miền so sánh đồng nhất** | Hash tương ứng với value equality của target | Value-like adapter nếu target có equality/hashing ổn định |

**Cẩn thận:** Hai hàng cuối đòi thuật toán xử lý **hai wrapper** và quyết định liệu object không phải proxy có được coi là bằng nhau hay không. Gọi `target.equals(other)` một cách mù quáng không tự tạo ra chính sách target equality đúng. Bài này sẽ minh họa chi tiết hai lựa chọn dễ kiểm soát nhất: identity và stable key.

**Khuyến nghị thiết kế:** Chọn chính sách dựa trên API contract. Nếu người sử dụng gọi nhiều lần một hàm tạo proxy cho cùng target và mong các proxy tương đương, identity policy có thể **không phù hợp**; thay vào đó, cân nhắc reuse/canonicalize một proxy hoặc tạo equality theo khóa/target ổn định.

## 4. Ví dụ hoàn chỉnh 1: equality theo chính instance proxy

Ví dụ dưới tạo hai proxy khác nhau bao cùng một target. Chính sách được chọn: **hai proxy vẫn khác nhau**, vì mỗi wrapper là một thực thể riêng.

Lưu file **IdentityProxyDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashSet;
import java.util.Set;

public class IdentityProxyDemo {
    interface Greeter {
        String greet(String name);
        boolean equals(Object other);
        int hashCode();
        String toString();
    }

    static final class GreeterImpl implements Greeter {
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    static final class IdentityHandler implements InvocationHandler {
        private final Greeter target;
        private final String label;
        boolean sawObjectMethod;

        IdentityHandler(Greeter target, String label) {
            this.target = target;
            this.label = label;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                sawObjectMethod = true;
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "GreeterProxy[" + label + "]";
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }
    }

    static Greeter newProxy(IdentityHandler handler) {
        return (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[]{Greeter.class},
                handler);
    }

    public static void main(String[] args) throws Exception {
        Greeter target = new GreeterImpl();
        IdentityHandler first = new IdentityHandler(target, "first");
        IdentityHandler second = new IdentityHandler(target, "second");
        Greeter a = newProxy(first);
        Greeter b = newProxy(second);

        System.out.println("greeting=" + a.greet("Mai"));
        System.out.println("reflexive=" + a.equals(a));
        System.out.println("sameTargetEquals=" + a.equals(b));
        System.out.println("nullEquals=" + a.equals(null));
        System.out.println("symmetric=" + (a.equals(b) == b.equals(a)));
        System.out.println("identityHash="
                + (a.hashCode() == System.identityHashCode(a)));
        Set<Greeter> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(a);
        System.out.println("setSize=" + set.size());
        System.out.println("toString=" + a.toString());
        System.out.println("ObjectDeclaringClass=" + first.sawObjectMethod);
        System.out.println("interfaceRedeclares="
                + (Greeter.class.getMethod("equals", Object.class)
                    .getDeclaringClass() == Greeter.class));

        InvocationHandler blindForwarder =
                (proxy, method, actual) -> method.invoke(target, actual);
        Greeter broken = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[]{Greeter.class},
                blindForwarder);
        System.out.println("brokenReflexive=" + broken.equals(broken));
        System.out.println("brokenProxyEqualsTarget=" + broken.equals(target));
        System.out.println("targetEqualsBrokenProxy=" + target.equals(broken));
    }
}
~~~

Biên dịch và chạy trên **JDK 17+**:

~~~bash
javac -encoding UTF-8 IdentityProxyDemo.java
java IdentityProxyDemo
~~~

Stdout:

~~~text
greeting=Hello, Mai
reflexive=true
sameTargetEquals=false
nullEquals=false
symmetric=true
identityHash=true
setSize=2
toString=GreeterProxy[first]
ObjectDeclaringClass=true
interfaceRedeclares=true
brokenReflexive=false
brokenProxyEqualsTarget=true
targetEqualsBrokenProxy=false
~~~

### 4.1. Vì sao identity equality phù hợp ở đây?

Handler không hỏi “hai proxy có bao cùng target không?” mà hỏi **“hai reference có cùng một proxy object không?”**:

~~~java
// Fragment: biểu thức trả về trong nhánh equals của handler.
proxy == args[0]
~~~

Với `a.equals(a)`, kết quả true; với `a.equals(b)` (hai proxy khác instance) kết quả false, dù cả hai trỏ về cùng `GreeterImpl`. So sánh với `null` false. Quy tắc này tự nhiên có tính reflexive, symmetric và transitive.

`System.identityHashCode(proxy)` lấy identity-based hash **không thông qua `proxy.hashCode()`**, nên không gọi lại handler. Hash có thể trùng giữa hai object khác nhau, điều đó không vi phạm hợp đồng. Kết quả test cố tình so sánh boolean, không in một con số hash ngẫu nhiên không ổn định giữa các JVM.

Một `HashSet` chứa hai proxy `a`, `b` cho size 2; thêm lại `a` không tạo phần tử mới. `toString()` trả chuỗi xác định `GreeterProxy[first]`, không phụ thuộc format tên class sinh bởi JVM.

### 4.2. Vì sao ObjectDeclaringClass=true khi interface tự khai báo lại equals?

Interface `Greeter` trong ví dụ **tự có chữ ký `boolean equals(Object)`** và cả `hashCode`, `toString`. Phép kiểm tra reflection của chính interface trả:

~~~text
interfaceRedeclares=true
~~~

Nhưng tại runtime, lời gọi `a.equals(...)`, `a.hashCode()`, `a.toString()` vẫn truyền Method có declaring class là **`Object.class`** cho handler. Vì vậy `ObjectDeclaringClass=true`.

Đây là quy tắc đặc biệt được tài liệu của `java.lang.reflect.Proxy` công bố; không nên thay bằng giả định method luôn được khai báo từ interface đầu tiên.

### 4.3. Vì sao phải unwrap InvocationTargetException ở nhánh business method?

Lời gọi `a.greet("Mai")` được chuyển vào handler, rồi `method.invoke(target,args)` gọi implementation trên GreeterImpl. Khi method nghiệp vụ ném exception, `Method.invoke` bọc exception gốc trong `InvocationTargetException`. Handler trong ví dụ trả lại **cause thực** để proxy xử lý exception theo hợp đồng method interface.

Việc này cần thiết khi dùng reflection để delegate. Lỗi checked exception không khai báo trong interface vẫn có thể bị proxy bao bọc bằng `UndeclaredThrowableException`; không được dùng unwrap như một cách bypass luật checked exception của method.

## 5. Phản ví dụ đã chạy: chuyển hết Object methods sang target là sai

Trong cùng chương trình trên, một proxy thứ ba dùng handler:

~~~java
// Fragment từ IdentityProxyDemo.java, minh họa SAI:
InvocationHandler blindForwarder =
        (proxy, method, actual) -> method.invoke(target, actual);
~~~

Với `target` sử dụng `Object.equals` theo identity, chuyện gì xảy ra?

- `broken.equals(broken)` gọi thực tế `target.equals(broken)` và trả **false** vì target khác proxy. Vậy đối tượng không bằng chính nó: **vi phạm reflexivity**.
- `broken.equals(target)` gọi `target.equals(target)` và trả **true**.
- Nhưng `target.equals(broken)` trả **false**. Vậy **vi phạm symmetry**.

Stdout của ví dụ phản chứng đã in đủ ba trường hợp:

~~~text
brokenReflexive=false
brokenProxyEqualsTarget=true
targetEqualsBrokenProxy=false
~~~

Nghĩa là **“delegate mọi method” không phải là một thiết kế equality**. Target có thể có `equals` và `hashCode` tuyệt vời với các target khác, nhưng handler vẫn phải hiểu **proxy và target nằm trong cùng miền equality không**.

`toString()` cũng không nên chuyển tiếp mù quáng nếu target mặc định in class name/hash không giúp người sử dụng, hoặc nếu target chứa dữ liệu nhạy cảm. Handler cần thiết kế định dạng của proxy riêng biệt.

## 6. Ví dụ hoàn chỉnh 2: equality theo khóa nghiệp vụ bất biến

Một số proxy đại diện cho **một resource logic**; hai wrapper được tạo ở hai thời điểm khác nhau nhưng cùng ID có thể cần được coi là tương đương. Ví dụ service proxy cho resource `order-7` từ registry.

Thiết kế dưới đây chủ động giới hạn equality trong **cùng loại proxy do KeyedHandler tạo ra**, cùng interface Service và cùng key. Nó **không tự cho proxy bằng đối tượng target gốc**. Mọi instance được tạo theo factory này dùng cùng quy tắc nên có tính đối xứng trong miền ấy.

Lưu file **KeyedProxyDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class KeyedProxyDemo {
    interface Service {
        String read();
    }

    static final class KeyedHandler implements InvocationHandler {
        private final String key;
        private final Service target;

        KeyedHandler(String key, Service target) {
            this.key = Objects.requireNonNull(key);
            this.target = Objects.requireNonNull(target);
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> equalsProxy(proxy, args[0]);
                    case "hashCode" -> key.hashCode();
                    case "toString" -> "ServiceProxy[id=" + key + "]";
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }

        private boolean equalsProxy(Object self, Object other) {
            if (self == other) {
                return true;
            }
            if (!(other instanceof Service)
                    || !Proxy.isProxyClass(other.getClass())) {
                return false;
            }
            InvocationHandler otherHandler = Proxy.getInvocationHandler(other);
            return otherHandler instanceof KeyedHandler matching
                    && key.equals(matching.key);
        }
    }

    static Service wrap(String key, Service target) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[]{Service.class},
                new KeyedHandler(key, target));
    }

    public static void main(String[] args) {
        Service target = () -> "payload";
        Service first = wrap("order-7", target);
        Service second = wrap("order-7", target);
        Service third = wrap("order-8", target);

        System.out.println("sameKey=" + first.equals(second));
        System.out.println("reverse=" + second.equals(first));
        System.out.println("differentKey=" + first.equals(third));
        System.out.println("nullEquals=" + first.equals(null));
        System.out.println("rawTargetEquals=" + first.equals(target));
        System.out.println("hashConsistent="
                + (first.hashCode() == second.hashCode()));
        Set<Service> set = new HashSet<>();
        set.add(first);
        set.add(second);
        set.add(third);
        System.out.println("setSize=" + set.size());
        Map<Service, String> cache = new HashMap<>();
        cache.put(first, "cached");
        System.out.println("mapLookup=" + cache.get(second));
        System.out.println("toString=" + first);
        System.out.println("read=" + first.read());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 KeyedProxyDemo.java
java KeyedProxyDemo
~~~

Stdout:

~~~text
sameKey=true
reverse=true
differentKey=false
nullEquals=false
rawTargetEquals=false
hashConsistent=true
setSize=2
mapLookup=cached
toString=ServiceProxy[id=order-7]
read=payload
~~~

### 6.1. Ý nghĩa của logic so sánh

`first.equals(second)` và `second.equals(first)` cùng true vì cả hai có handler `KeyedHandler` và key `order-7`. `first.equals(third)` false vì `order-8` là resource khác.

`Proxy.isProxyClass(other.getClass())` bảo đảm object đang xét là **JDK proxy class**. `Proxy.getInvocationHandler(other)` trả về handler gắn với proxy ấy; trong ví dụ này, ta tiếp tục chỉ chấp nhận `KeyedHandler` để tránh diễn giải nhầm một proxy lạ do framework khác tạo.

Không đủ nếu chỉ viết `other instanceof Service`: target thật cũng có thể là Service nhưng không dùng cùng equality policy. Trường hợp `rawTargetEquals=false` thể hiện **quyết định có chủ đích**: “service proxy với ID” khác “object target gốc”.

**Giới hạn của thiết kế:** Quy tắc so sánh đảm bảo hợp đồng **trong họ proxy do factory này kiểm soát**. Nếu một class hoặc một proxy handler *khác* chủ động báo nó bằng KeyedProxy trong khi KeyedProxy lại trả false, symmetry toàn hệ thống có thể vỡ. Vì thế các implementer tham gia cùng miền equality phải thống nhất contract; một handler không thể buộc mọi class khác cư xử đối xứng.

### 6.2. HashMap và HashSet dựa trên key

Hai wrapper có key bằng nhau trả cùng hash vì `hashCode` dựa trên chính **String key bất biến**. Do đó:

- `HashSet` có ba proxy được tạo nhưng chỉ hai phần tử logic: `setSize=2`.
- `cache.put(first, "cached")` rồi `cache.get(second)` trả `cached`. Các key thuộc cùng equality policy và cùng hash.
- `first.read()` vẫn gọi target nghiệp vụ và trả `payload`; equality của proxy không làm thay đổi delegation của business method.

Nếu các request có thể trỏ tới target khác nhau nhưng cùng `order-7`, kiểu equality này có nghĩa hai proxy vẫn được xem là **cùng resource logic**. Bạn phải xác nhận đó là quy tắc nghiệp vụ đúng. Nếu ID chỉ có ý nghĩa trong một tenant, environment hoặc type, key cần bao gồm tenant/type để tránh gộp nhầm.

### 6.3. Vì sao key nên immutable?

Hãy xem hai object `a`, `b` cùng key `order-7`. Nếu cho phép thay key của `a` sau khi thêm vào HashMap, `a.hashCode()` sẽ thay đổi và HashMap có thể không tìm lại được entry. Điều tương tự áp dụng với target whose `hashCode` depends on mutable fields.

Trong code mẫu, `key` là `private final String` và bắt buộc khác null. String là immutable nên equality/hash ổn định theo dữ liệu được dùng. Với composite key, hãy dùng một value object immutable, ví dụ record chứa `tenant`, `resourceType`, `resourceId`, và bảo đảm các thành phần ổn định.

### 6.4. toString phản ánh proxy, không phải toàn bộ target

`ServiceProxy[id=order-7]` là format riêng của proxy, dễ phân biệt với target object và không phụ thuộc tên lớp runtime. Trong hệ thống thực tế, ID có thể chứa thông tin cần ẩn; hãy cân nhắc dạng `ServiceProxy[type=Order, state=ready]` hoặc ID rút gọn/đã mask, tùy chính sách log.

Đặc biệt không được gọi network chỉ để dựng `toString`. Nếu proxy là RPC client, việc logger vô tình in proxy không nên tạo request mạng mới.

## 7. Bốn kiểu bug khi implement ba Object methods

### 7.1. Gọi ngược chính proxy dẫn tới đệ quy

Đoạn sai:

~~~java
// Fragment SAI bên trong handler:
if (method.getName().equals("toString")) {
    return proxy.toString(); // proxy.toString() lại gọi chính handler!
}
~~~

Hành trình:

~~~text
proxy.toString()
  -> handler.invoke(proxy, Object.toString, ...)
      -> proxy.toString()
          -> handler.invoke(...)
              -> ... lặp đến StackOverflowError
~~~

Tương tự, `proxy.equals(other)` bên trong nhánh `equals` hoặc `proxy.hashCode()` bên trong nhánh `hashCode` đều có thể tự gọi handler vô hạn. Không dùng `Objects.hash(proxy)` nếu nó dẫn tới `proxy.hashCode()` tại cùng nhánh. Dùng `proxy == other`, `System.identityHashCode(proxy)`, hoặc các field bất biến của handler theo chính sách thiết kế.

**Logging cũng là một đường đệ quy gián tiếp.** Ví dụ `System.out.println("handling " + proxy)` trong handler sẽ kích hoạt `proxy.toString()`. Nếu dòng log nằm ngay trong handler `toString`, chương trình có thể bị lặp vô hạn. Khi debug, log loại method và nhãn handler thay vì nội suy proxy trực tiếp.

### 7.2. Trả về sai kiểu cho signature

Theo `InvocationHandler.invoke`, giá trị trả về phải tương thích với return type của method được gọi:

| Method | Return type Java | Handler trả đúng | Trả sai dễ gây |
| --- | --- | --- | --- |
| `equals(Object)` | `boolean` | `Boolean.TRUE` / `Boolean.FALSE` | `NullPointerException` khi trả null; `ClassCastException` khi trả kiểu khác |
| `hashCode()` | `int` | Một `Integer` | Lỗi unbox/cast nếu null hoặc sai wrapper |
| `toString()` | `String` | Một `String` phù hợp | Cast lỗi nếu trả đối tượng không phải String |

Việc `InvocationHandler.invoke` khai báo return type là `Object` **không có nghĩa** có thể trả bất kỳ object nào. Proxy generated code phải chuyển kết quả sang kiểu của phương thức. Đối với equals/hashCode, nên trả boolean/int ngay trong Java source để autoboxing đúng wrapper.

### 7.3. Đưa exception không phù hợp ra khỏi Object methods

`InvocationHandler.invoke` có thể ném `Throwable`, nhưng method được proxy gọi vẫn có hợp đồng checked exception riêng. Ba phương thức `Object.equals/hashCode/toString` không khai báo checked exception. Nếu handler ném một checked exception không được chữ ký cho phép, generated proxy thường bao nó bằng `UndeclaredThrowableException`.

Vì vậy equality/toString nên là các thao tác **nhẹ, không I/O** và có semantics xác định. Đừng để `equals` phải gọi database, RPC hoặc class loader bên ngoài rồi bất ngờ ném checked exception trong lúc HashMap tìm key.

Khi business method được delegate qua `Method.invoke(target,args)`, thường cần unwrap `InvocationTargetException.getCause()` để proxy thấy lỗi gốc. Nhưng việc unwrap vẫn phải tuân thủ `throws` của interface; checked exception bất tương thích không thể được “hợp pháp hóa” bởi handler.

### 7.4. Chọn hashCode không đi cùng equals

Ví dụ sai:

~~~java
// Fragment SAI: hai proxy cùng ID được coi bằng nhau...
case "equals" -> id.equals(idOfOtherProxy);
// ...nhưng hash lại lấy identity riêng từng wrapper.
case "hashCode" -> System.identityHashCode(proxy);
~~~

Nếu `a.equals(b)` true mà hash khác nhau, việc dùng làm key trong HashMap/HashSet sẽ không ổn định theo contract. Ví dụ code này là **mảnh minh họa lỗi**, không phải chương trình độc lập; `id` và `idOfOtherProxy` phải do logic ứng dụng định nghĩa.

Muốn equality theo ID, hash cũng phải theo cùng ID (và các thành phần khác dùng trong equals). Muốn equality theo proxy identity, hash theo proxy identity. Không trộn hai chính sách.

## 8. Phân biệt so sánh proxy, target và proxy khác framework

### 8.1. Hai proxy bọc cùng target

Không thể tự suy ra chúng bằng nhau. Ba lựa chọn thường hợp lệ:

- **Wrapper identity:** `a.equals(b) == false` nếu `a != b`; rõ ràng mỗi wrapper là một instance riêng.
- **Same-target identity:** `a.equals(b) == true` nếu hai handler tham chiếu cùng một target theo `==`; hash dựa identity của target.
- **Same logical resource:** `a.equals(b) == true` nếu cùng khóa nghiệp vụ bất biến; target instance có thể khác.

Chọn một quy tắc, ghi vào tài liệu của factory, và giữ nhất quán trong cả `equals`, `hashCode`, cache, collection và test.

### 8.2. Proxy có bằng object target thật hay không?

Thường **an toàn hơn** khi quy định proxy **chỉ so sánh với proxy cùng contract**, không tự động bằng object target. Nếu muốn equality giữa proxy và target, hai chiều so sánh phải được phối hợp: target cũng phải được thiết kế để `target.equals(proxy)` trả cùng kết quả. Điều này khó nếu target là class đã tồn tại, dùng `Object.equals` hoặc dùng kiểm tra `getClass()` nghiêm ngặt.

Phản ví dụ ở mục 5 là bằng chứng cụ thể: `broken.equals(target)` true nhưng `target.equals(broken)` false.

### 8.3. Nhiều interface, class loader và proxy class

Một proxy có thể triển khai nhiều interface; class do Proxy tạo phụ thuộc loader và danh sách interface theo quy tắc API. Không nên dựa vào tên như `$Proxy0`, vào việc hai proxy có cùng generated class hay không, hoặc vào thứ tự các Method ngẫu nhiên để quyết định equality.

Với **các interface thường có chữ ký trùng nhau**, `Proxy` có quy tắc xác định Method dựa trên thứ tự interface. Riêng ba chữ ký Object methods có ưu tiên `Object.class`. Nếu handler cần phân nhánh nhiều method nghiệp vụ trùng tên, hãy nhận diện chữ ký, type/declaring class và quy tắc interface theo API; không chọn bằng tên method đơn lẻ mà bỏ qua tham số.

Trong môi trường plugin/multiple class loader, hai interface cùng **tên chuỗi** nhưng được load bởi loader khác không nhất thiết cùng `Class`. Nếu so sánh object hoặc handler giữa các loader, tránh cast bừa; test cụ thể môi trường loader. Việc proxy không thuộc cùng classloader có thể khiến contract dự kiến từ cấu hình không áp dụng được.

### 8.4. Không thể tự “sửa” symmetry từ một phía

Giả sử KeyedHandler trả false với một object ngoài factory, nhưng object kia lại trả true khi so với KeyedProxy. Symmetry bị vi phạm dù KeyedHandler đã làm đúng policy cục bộ. Để có equality xuyên nhiều class/framework, cần:

- Một hợp đồng chung về loại đối tượng được coi là tương đương.
- Cùng định nghĩa khóa/so sánh và hash.
- Thỏa thuận xử lý `null`, subtype, proxy class và những trường hợp bất thường.
- Test hai chiều và tính bắc cầu giữa các implementer.

Nếu không kiểm soát tất cả implementer, **giới hạn miền equality** thường dễ bảo trì hơn so với cố ép proxy bằng mọi target có “cùng nội dung”.

## 9. Thực hành thiết kế cho ứng dụng thật

### 9.1. Đề xuất quy trình

1. **Xác định proxy dùng để làm gì.** Ví dụ logging/interceptor tạm thời, RPC resource handle, hoặc đại diện cho identity của entity.
2. **Chọn equality policy rõ ràng.** Nếu identity, so `proxy == other`; nếu logical, định nghĩa key bất biến và miền so sánh.
3. **Viết equals trước, hashCode ngay sau.** Chứng minh “equals true ⇒ hash bằng nhau”, rồi kiểm tra null/reflexivity/symmetry/transitivity.
4. **Thiết kế toString tách biệt.** Chỉ chứa metadata được phép log, không truy cập dịch vụ bên ngoài và không nội suy proxy vào chính handler.
5. **Xử lý Object methods trước business methods.** Dùng `Method.getDeclaringClass() == Object.class` theo API JDK proxy, sau đó mới delegate phần còn lại.
6. **Bảo đảm kiểu trả về.** equals → boolean, hashCode → int, toString → String.
7. **Xem lại exception boundary.** Unwrap lỗi từ `Method.invoke(target,args)`, nhưng không ném checked exception ngoài chữ ký interface.
8. **Thử trong HashMap/HashSet.** Kiểm tra lookup với proxy tương đương, không chỉ test `equals` trực tiếp.
9. **Test với nhiều factory call.** Nhiều proxy quanh cùng target, nhiều target cùng ID, khác ID, null, foreign proxy, target thật.
10. **Document và giữ tương thích.** Thay đổi equality policy trong bản release mới có thể làm đổi hành vi cache, set membership và các dependency của ứng dụng.

### 9.2. Có nên cache một proxy để giữ reference identity?

Nếu requirement là **cùng resource luôn trả về đúng một instance proxy** (so `==`), equality policy một mình không đáp ứng. Một factory có thể cần **interning/canonicalization**, một map từ stable ID đến proxy được reuse, cộng với chiến lược vòng đời/weak references nếu cần. Khi đó `System.identityHashCode` vẫn phù hợp với identity semantics.

Nhưng nếu ứng dụng không thể bảo đảm đúng một proxy instance (ví dụ distributed client tái tạo wrapper nhiều lần), identity equality có thể gây bất ngờ. Cân nhắc stable-key policy và tách việc giữ cache proxy instance khỏi việc định nghĩa resource equality.

### 9.3. Đừng biến equals thành thao tác nghiệp vụ nặng

`HashMap.get` có thể gọi `hashCode` và `equals` nhiều lần. Nếu mỗi lần so sánh proxy lại gọi RPC, load metadata hoặc khóa mutex nhiều tầng, thao tác collection tưởng nhẹ có thể chậm hoặc fail. `equals`, `hashCode`, `toString` nên dùng **trạng thái cục bộ, bất biến, rẻ** khi khả thi.

Với lazy proxy, tránh khởi tạo target chỉ để trả lời `hashCode` hoặc `toString`. Equality identity/key có thể được xác định mà không chạm vào target thật, nhờ vậy logging và collection không gây side effect.

## 10. Checklist QA trước khi giao proxy factory

| Câu hỏi thử nghiệm | Kết quả kỳ vọng theo chính sách |
| --- | --- |
| `p.equals(p)`? | **Luôn true** |
| `p.equals(null)`? | **Luôn false** |
| `p.equals(q)` so với `q.equals(p)`? | **Cùng giá trị** trong miền equality đã định |
| `p.equals(q)` true thì hai hash? | **Bằng nhau** |
| Ba proxy `p,q,r` có tính bắc cầu? | Nếu `p=q` và `q=r`, thì `p=r` |
| Thêm rồi lấy lại từ `HashMap` với key tương đương? | Nhận được giá trị đã lưu |
| Hash có thay đổi khi target mutate? | Không, nếu equality policy không thay đổi |
| `p.toString()` có đệ quy? | Không |
| `p.toString()` có leak secret hay phát sinh I/O? | Không |
| Interface redeclare `equals/hashCode/toString`? | Handler vẫn nhận Method thuộc `Object.class` |
| `p.equals(target)` và `target.equals(p)`? | Đồng bộ policy hoặc **cùng false** |
| Handler trả `null` cho `hashCode`? | **Không được** |
| Foreign proxy hoặc loader khác? | Không cast mù; xử lý theo domain rõ ràng |

Một bộ kiểm thử property-based có thể sinh nhiều proxy từ các ID khác nhau và kiểm tra tính reflexive/symmetric/transitive. Các test bằng `HashSet` và `HashMap` phát hiện trực tiếp lỗi hash/equality không nhất quán mà những test chỉ gọi `equals` có thể bỏ sót.

## 11. Câu hỏi tự kiểm tra

**1.** Vì sao `proxy.hashCode()` lại có thể gọi tới InvocationHandler?

**Đáp án:** JDK proxy sinh override của `Object.hashCode()` và dispatch sang `InvocationHandler.invoke`, giống với `equals` và `toString`. Handler phải quyết định hash của proxy.

**2.** Interface tự khai báo `boolean equals(Object)`. Method mà handler nhận cho lời gọi đó có declaring class nào?

**Đáp án:** `java.lang.Object.class`, theo quy tắc đặc biệt của JDK proxy, dù interface có khai báo lại.

**3.** Muốn mỗi proxy độc lập, kể cả bao cùng target, thì equals và hashCode nên dựa vào gì?

**Đáp án:** `proxy == other` và `System.identityHashCode(proxy)`. Không gọi `proxy.hashCode()` từ handler xử lý hashCode, vì sẽ đệ quy.

**4.** Hai proxy có cùng ID được coi bằng nhau. Có thể dùng `System.identityHashCode(proxy)` làm hash cho từng instance không?

**Đáp án:** Không. Hai proxy có thể có identity hash khác nhau dù equality trả true, vi phạm contract. Phải tính hash từ cùng dữ liệu key bất biến.

**5.** Vì sao `method.invoke(target,args)` cho mọi method có thể khiến `broken.equals(broken)` trả false?

**Đáp án:** Lời gọi đang dùng `target.equals(broken)` thay cho `broken` so sánh với chính nó. Nếu target dùng Object identity equality, target khác broken, nên false.

**6.** Tại sao `System.out.println(proxy)` có thể nguy hiểm bên trong handler?

**Đáp án:** Nó có thể gọi `proxy.toString()`, lại dispatch vào cùng handler; nếu làm điều này trong nhánh toString hoặc log chung không có guard, có thể gây đệ quy vô hạn.

**7.** Handler trả `null` cho `hashCode()` có hợp lệ vì `invoke` trả Object không?

**Đáp án:** Không. Proxy phải chuyển kết quả thành primitive `int`; null không thể unbox nên có thể gây `NullPointerException`.

**8.** Một KeyedProxy có key `order-7`, proxy khác key `order-7` nhưng target là object khác. Có nên equals true không?

**Đáp án:** Phụ thuộc contract. Nếu key định danh **cùng resource logic** và có cùng namespace, true là hợp lý; nếu key chỉ cục bộ hoặc target identity quan trọng hơn, cần chính sách khác.

**9.** `getClass()` trên JDK proxy có đi vào handler như `toString()` không?

**Đáp án:** Không. `getClass()` là final method được kế thừa từ Object, không thuộc ba Object methods được proxy override và dispatch.

## Ghi nhớ

- **JDK dynamic proxy chuyển `equals`, `hashCode`, `toString` vào `InvocationHandler.invoke`.** Method được truyền có declaring class là Object, kể cả interface redeclare chữ ký tương ứng.
- **Equality là quyết định thiết kế.** Proxy identity, target identity và stable key tạo ra hành vi khác nhau; không ủy quyền mù quáng.
- **Equals và hashCode phải nhất quán**, đặc biệt khi proxy làm key của `HashMap` hoặc phần tử của `HashSet`.
- **toString phải rõ ràng, an toàn, không đệ quy**, không log secret và không tự tạo I/O ngoài ý muốn.
- **Tránh `method.invoke(proxy,...)` hoặc gọi lại Object methods của proxy trong chính handler.** Với business method, nếu delegate qua reflection thì xử lý `InvocationTargetException` đúng cách.
- **Kiểm thử hai chiều và nhiều instance**: proxy với chính nó, với target, với proxy cùng ID, khác ID và với foreign proxy. Đừng chỉ dựa vào một ví dụ đơn giản.

## Tài liệu tham khảo

- Java SE 17, **Proxy** — hành vi `equals`, `hashCode`, `toString`, quy tắc Method declaring class, các method trùng giữa interface: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- Java SE 17, **InvocationHandler** — `invoke`, kiểu trả về và ngoại lệ: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html
- Java SE 17, **Object** — hợp đồng `equals`, `hashCode`, `toString`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- Java SE 17, **InvocationTargetException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html
