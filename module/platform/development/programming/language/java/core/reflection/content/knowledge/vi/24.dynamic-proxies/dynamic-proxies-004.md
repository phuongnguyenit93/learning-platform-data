# Điều kiện interface `public`, `non-public`, `hidden` và `sealed` khi dùng Java Dynamic Proxy

## 1. Mục tiêu và quy tắc quyết định

`java.lang.reflect.Proxy` tạo một lớp tại runtime để triển khai **một hoặc nhiều interface**, rồi chuyển lời gọi phương thức trên proxy đến `InvocationHandler.invoke`. Việc một giá trị `Class<?>` có `isInterface() == true` **chưa đủ** để dùng được với `Proxy.newProxyInstance`.

Trong Java 17+, tập interface đầu vào phải thỏa đồng thời những ràng buộc về **loại interface**, **class loader**, **khả năng nhìn thấy kiểu**, **package/module** và **chữ ký phương thức**. Hai trường hợp đặc biệt bị từ chối ngay từ thiết kế là **hidden interface** và **sealed interface**.

| Interface đầu vào | Có thể dùng với `Proxy.newProxyInstance`? | Điều kiện chính |
| --- | --- | --- |
| `public`, không `hidden`, không `sealed` | **Có**, nếu hợp lệ | Interface và các kiểu trong chữ ký public phải nhìn thấy qua loader truyền vào; cách đóng gói của module ảnh hưởng vị trí/quyền truy cập lớp proxy. |
| `non-public` (ví dụ package-private), không `hidden`, không `sealed` | **Có điều kiện** | Mọi interface non-public trong cùng lần tạo phải ở **cùng package và cùng module**, được định nghĩa bởi loader được truyền vào; module chứa chúng phải truy cập được các interface cần triển khai. |
| `hidden interface` | **Không** | API `Proxy` yêu cầu interface **không hidden**; vi phạm gây `IllegalArgumentException`. |
| `sealed interface` | **Không** | API `Proxy` yêu cầu interface **không sealed**; vi phạm gây `IllegalArgumentException` dù interface đó là `public`. |

Điểm cần nhớ: **`non-public` không có nghĩa là không thể proxy**. Ngược lại, `public` cũng không tự bảo đảm thành công nếu class loader, module hoặc chữ ký không hợp lệ.

## 2. Ba khái niệm dễ bị trộn lẫn

### 2.1. Quyền truy cập Java của interface

- `public interface Api` có modifier `public`: `Modifier.isPublic(Api.class.getModifiers())` là `true`.
- `interface InternalApi` ở cấp package, hoặc interface thành viên không khai báo `public`, có thể là `non-public`: `Modifier.isPublic(...)` là `false`.
- Khả năng nhìn thấy kiểu từ mã Java của người gọi và khả năng JVM tạo proxy hợp lệ là **hai câu hỏi khác nhau**. Có `Class<?>` của interface không tự xóa các giới hạn package/module.

Một **public interface nằm trong package không được export** của named module vẫn có modifier `public`. Nó **không tự biến thành non-public interface** chỉ vì module không export package đó.

### 2.2. Package, runtime module và class loader

Tên package giống nhau chưa chắc cùng runtime package/module trong JVM. Khi nhiều interface non-public cùng tham gia, JDK yêu cầu chúng cùng package **và cùng module**, và module/loader phải thỏa quy tắc định nghĩa lớp proxy.

Với mọi interface `i`, class loader `loader` được truyền vào `Proxy.newProxyInstance` cần nhìn thấy đúng **cùng đối tượng `Class`** theo kiểm tra:

```java
Class.forName(i.getName(), false, loader) == i
```

Đây là **biểu thức minh họa điều kiện Javadoc**, không phải mã độc lập và không phải khuyến nghị gọi `Class.forName` với hidden interface. Loader thấy một kiểu **cùng tên nhưng khác định danh `Class`** vẫn không đạt yêu cầu. Ngoài các interface, các kiểu xuất hiện trong chữ ký của mọi phương thức `public` (kể cả phương thức kế thừa từ superinterface) cũng phải nhìn thấy bằng tên qua loader này.

### 2.3. Interface bình thường, hidden và sealed

- **Interface bình thường** có tên nhị phân được loader tra cứu; `public` hay `non-public` là một chiều phân loại khác.
- **Hidden interface** được định nghĩa, chẳng hạn qua `MethodHandles.Lookup#defineHiddenClass`. `Class.isHidden()` trả `true`; nó không có binary name có thể được tra cứu theo cách thông thường. `Proxy` từ chối loại này.
- **Sealed interface** giới hạn những kiểu được phép triển khai qua `permits`; `Class.isSealed()` trả `true`. JDK `Proxy` không nhận sealed interface làm đầu vào, kể cả khi một cách thiết kế khác có thể tuân theo `permits`.

`hidden` và `sealed` là **hai thuộc tính khác nhau**. Một interface `non-sealed` trong phân cấp có sealed superinterface cần được đánh giá theo **chính đối tượng `Class<?>` đưa vào mảng interfaces**; đừng kết luận nó bị từ chối chỉ vì tổ tiên sealed. Tuy nhiên các điều kiện loader, module và chữ ký vẫn phải đạt.

## 3. Package/module của lớp proxy được chọn thế nào?

JDK chọn quyền truy cập của **lớp proxy được sinh ra** dựa trên tập interface:

| Tập interface | Quy tắc về lớp proxy |
| --- | --- |
| Tất cả interface đều `public`, và tất cả ở package được export hoặc open | Proxy class là `public` trong một package được export vô điều kiện nhưng **không open**; tên package/module cụ thể không được bảo đảm. |
| Tất cả interface đều `public`, nhưng ít nhất một interface ở package không export **và** không open | Proxy class là `public` trong package không export, không open của **dynamic module**; mã ngoài module không được mặc nhiên truy cập trực tiếp lớp proxy. |
| Có ít nhất một interface `non-public` | Proxy class là **non-public**, ở **cùng package và module** với các non-public interface. Tất cả non-public interface phải cùng package/module; nếu khác nhau thì không thể tạo proxy đó. |

**Tính khả dụng của proxy instance khác với quyền truy cập trực tiếp proxy class.** Người gọi thường chỉ cần:

```java
Object instance = Proxy.newProxyInstance(loader, interfaces, handler);
```

Sau đó ép kiểu về interface mà mã gọi được phép truy cập. Không nên dựa vào tên lớp có dạng `$Proxy...` hoặc tự gọi constructor của proxy class bằng Reflection. Với proxy trong dynamic module đóng, tự gọi constructor qua Reflection có thể bị `IllegalAccessException`. `Proxy.getProxyClass` cũng đã bị đánh dấu deprecated; ưu tiên `newProxyInstance`.

Nếu vừa có interface public vừa có non-public, quyền truy cập proxy class đi theo **interface hạn chế nhất**; thêm một interface public không làm proxy class non-public trở thành public.

## 4. Ví dụ hoàn chỉnh chạy được trên Java 17+

Ví dụ này minh họa **bốn trường hợp** trong một chương trình: public hợp lệ, non-public hợp lệ, sealed bị từ chối, hidden bị từ chối. Chương trình còn kiểm chứng trường hợp trộn public và non-public.

Lưu thành file **`ProxyInterfaceRulesDemo.java`** (không thêm khai báo `package` để chạy trực tiếp từ cùng thư mục):

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

public class ProxyInterfaceRulesDemo {
    public interface PublicApi {
        String message();
    }

    interface InternalApi {
        String internal();
    }

    public sealed interface SealedApi permits Approved {
        String execute();
    }

    public static final class Approved implements SealedApi {
        public String execute() { return "approved"; }
    }

    interface HiddenSeed {
        String hidden();
    }

    public static void main(String[] args) throws Throwable {
        ClassLoader loader = ProxyInterfaceRulesDemo.class.getClassLoader();
        InvocationHandler handler = (proxy, method, parameters) ->
                switch (method.getName()) {
                    case "message" -> "public-ok";
                    case "internal" -> "internal-ok";
                    default -> throw new UnsupportedOperationException(method.getName());
                };

        PublicApi publicProxy = (PublicApi) Proxy.newProxyInstance(
                loader, new Class<?>[]{PublicApi.class}, handler);
        System.out.println("public: " + publicProxy.message()
                + ", proxyPublic=" + Modifier.isPublic(publicProxy.getClass().getModifiers()));

        InternalApi internalProxy = (InternalApi) Proxy.newProxyInstance(
                loader, new Class<?>[]{InternalApi.class}, handler);
        System.out.println("non-public: " + internalProxy.internal()
                + ", proxyPublic=" + Modifier.isPublic(internalProxy.getClass().getModifiers()));

        Object mixed = Proxy.newProxyInstance(
                loader, new Class<?>[]{PublicApi.class, InternalApi.class}, handler);
        System.out.println("mixed: " + ((PublicApi) mixed).message()
                + ", proxyPublic=" + Modifier.isPublic(mixed.getClass().getModifiers()));

        System.out.println("sealed flag: " + SealedApi.class.isSealed());
        try {
            Proxy.newProxyInstance(loader, new Class<?>[]{SealedApi.class}, handler);
            System.out.println("sealed: unexpected success");
        } catch (IllegalArgumentException expected) {
            System.out.println("sealed rejected: " + expected.getClass().getSimpleName());
        }

        String resource = "/" + HiddenSeed.class.getName().replace('.', '/') + ".class";
        try (InputStream stream = HiddenSeed.class.getResourceAsStream(resource)) {
            if (stream == null) throw new IllegalStateException("Class bytes not found");
            byte[] bytes = stream.readAllBytes();
            Class<?> hidden = MethodHandles.lookup()
                    .defineHiddenClass(bytes, false).lookupClass();
            System.out.println("hidden flags: interface=" + hidden.isInterface()
                    + ", hidden=" + hidden.isHidden());
            try {
                Proxy.newProxyInstance(loader, new Class<?>[]{hidden}, handler);
                System.out.println("hidden: unexpected success");
            } catch (IllegalArgumentException expected) {
                System.out.println("hidden rejected: " + expected.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy trong thư mục có file nguồn bằng JDK 17 trở lên:

```bash
javac --release 17 ProxyInterfaceRulesDemo.java
java ProxyInterfaceRulesDemo
```

Output:

```text
public: public-ok, proxyPublic=true
non-public: internal-ok, proxyPublic=false
mixed: public-ok, proxyPublic=false
sealed flag: true
sealed rejected: IllegalArgumentException
hidden flags: interface=true, hidden=true
hidden rejected: IllegalArgumentException
```

**Giải thích kết quả:**

1. `PublicApi` là interface thành viên có `public`; proxy class tạo ra có `public`, handler trả `"public-ok"`.
2. `InternalApi` là interface thành viên không khai báo `public` nên non-public. Vì tạo một mình và đáp ứng quy tắc package/module/loader, proxy được tạo thành công nhưng proxy class không `public`.
3. Khi đưa đồng thời `PublicApi` và `InternalApi` vào mảng, proxy vẫn hợp lệ nhưng proxy class non-public theo interface hạn chế hơn. Vẫn có thể gọi `PublicApi.message()` qua kiểu interface public.
4. `SealedApi.class.isSealed()` là `true`; JDK từ chối ngay yêu cầu proxy interface đó bằng `IllegalArgumentException`. Một class `Approved` được liệt kê trong `permits` không làm cho JDK Proxy được phép tự bổ sung subclass.
5. `HiddenSeed` đầu tiên là interface **bình thường** với file `.class` do `javac` tạo ra. `defineHiddenClass` định nghĩa một **hidden interface mới** từ bytecode đó, rồi trả về `Class<?>` có `isInterface() == true` và `isHidden() == true`. Đây chính là loại JDK Proxy không nhận. Không nên đồng nhất `HiddenSeed.class` ban đầu với đối tượng `Class<?> hidden` mới.
6. Tên lớp proxy và tên hidden interface có thể thay đổi giữa các lần chạy hoặc các bản JDK; ví dụ chỉ in những đặc tính được API bảo đảm. `InvocationHandler` trong ví dụ xử lý hai phương thức nghiệp vụ đang gọi; một ứng dụng thực tế cần định nghĩa cách xử lý `equals`, `hashCode`, `toString` và các phương thức khác nếu được gọi.

Ví dụ đã được kiểm chứng bằng `javac --release 17` và thực thi trên JDK 24. Nó chỉ dùng API có sẵn từ Java 17, gồm `Class.isHidden()`, `Class.isSealed()` và `Lookup.defineHiddenClass`. Phần đọc `.class` cần các file được `javac` tạo nằm trên classpath khi chạy; lệnh ở trên đáp ứng điều đó.

## 5. Vì sao hidden và sealed không tạo proxy được?

### 5.1. Hidden interface

`MethodHandles.Lookup#defineHiddenClass(byte[], ...)` tạo hidden class hoặc hidden interface từ bytecode. Kiểu hidden không có binary name để loader thông thường tìm lại bằng tên; không thể giả định rằng `Class.forName(hidden.getName(), false, loader)` sẽ tìm ra chính nó.

Javadoc `Proxy.newProxyInstance` quy định rõ các phần tử trong mảng `interfaces` phải là interface **non-hidden**. Kể cả khi đã giữ tham chiếu `Class<?>` của hidden interface trong tay, việc truyền nó vào API này vẫn bị loại. Đây là **ràng buộc của cơ chế JDK dynamic proxy**, không có nghĩa mọi kỹ thuật sinh bytecode hoặc mọi framework tạo adapter đều không thể tương tác với đối tượng hidden theo cách khác.

### 5.2. Sealed interface

Ví dụ hợp lệ về khai báo:

```java
sealed interface Operation permits ReadOperation {}

final class ReadOperation implements Operation {}
```

Hai khai báo trên là **mảnh minh họa ở phạm vi package**, cần đặt trong file nguồn hợp lệ. `Operation.class.isSealed()` là `true`. Khi gọi `Proxy.newProxyInstance(..., new Class<?>[]{Operation.class}, ...)`, JDK từ chối `Operation` vì chính sách `non-sealed` của API. Không thể sửa bằng cách đưa proxy sinh động vào danh sách `permits` trong source code như với lớp cài đặt đã biết.

**Phân biệt `non-sealed` trong Java với “không bị sealed”:** từ khóa `non-sealed` được dùng cho một interface/class trực tiếp mở lại khả năng triển khai trong phân cấp sealed. `Class.isSealed()` của nó là `false`. Nếu bản thân interface đầu vào không hidden, không sealed và thỏa các điều kiện khác, riêng lịch sử kế thừa từ sealed superinterface không phải là lý do để từ chối nó.

## 6. Những kiểm tra khác vẫn phải làm cho interface public/non-public

Ngay cả khi từng interface có `isInterface() == true`, `isHidden() == false`, `isSealed() == false`, `Proxy.newProxyInstance` vẫn có thể ném `IllegalArgumentException`:

1. **Trùng interface:** cùng một đối tượng `Class<?>` xuất hiện hai lần trong mảng `interfaces`.
2. **Sai class loader:** interface không nhìn thấy được bằng tên qua loader được chỉ định, hoặc loader tìm ra một `Class` khác cùng tên; các kiểu được nhắc trong chữ ký `public` cũng phải nhìn thấy.
3. **Non-public khác package/module:** hai interface non-public của hai package khác nhau không thể cùng được một lớp proxy triển khai. Ngay cả khi tên package giống nhau, khác module vẫn không hợp lệ theo điều kiện của JDK.
4. **Loader không định nghĩa non-public interface:** loader chỉ *nhìn thấy* nó thông qua delegation chưa đủ nếu không đúng yêu cầu loader định nghĩa theo Javadoc.
5. **Module chứa non-public interface thiếu khả năng truy cập:** khi trộn non-public với các interface khác, module chứa proxy phải truy cập được những interface được triển khai.
6. **Trùng chữ ký nhưng kiểu trả về không tương thích:** các phương thức cùng tên và danh sách tham số mà kiểu trả về nguyên thủy/`void` khác nhau sẽ xung đột; với kiểu trả về tham chiếu, cần có một kiểu trả về là subtype phù hợp của các kiểu còn lại.
7. **Giới hạn JVM:** số lượng interface hoặc giới hạn về class file có thể khiến việc sinh proxy không thực hiện được.

Nếu `interfaces` hoặc phần tử của nó là `null`, hoặc `handler` là `null`, API có thể ném `NullPointerException` theo hợp đồng; đừng gom mọi thất bại vào `IllegalArgumentException`.

**Module access khác với điều kiện export/open:** public interface trong một package đóng có thể được đưa vào proxy theo quy tắc **dynamic module** của JDK. Việc tạo proxy thành công không biến package đó thành public API cho mọi mã Java khác. Cần phân biệt tạo proxy, ép kiểu hợp lệ từ vị trí người gọi và truy cập trực tiếp lớp proxy đã được sinh.

## 7. Chẩn đoán nhanh trước khi tạo proxy

Đoạn phương thức dưới đây dùng để **lọc sơ bộ** (đặt trong một class có `import java.lang.reflect.Modifier;`). Nó chỉ kiểm tra **loại interface**; kết quả `"candidate"` không có nghĩa mọi yêu cầu khác đã đạt.

```java
static String precheck(Class<?> type) {
    if (type == null) return "null";
    if (!type.isInterface()) return "not an interface";
    if (type.isHidden()) return "hidden interface: unsupported";
    if (type.isSealed()) return "sealed interface: unsupported";
    return Modifier.isPublic(type.getModifiers())
            ? "candidate: public"
            : "candidate: non-public; check package, module and loader";
}
```

Khi điều tra một thất bại, nên ghi nhận (mà không phụ thuộc vào tên proxy do JDK sinh):

- `type.getName()`, `type.isInterface()`, `type.isHidden()`, `type.isSealed()`, `Modifier.isPublic(type.getModifiers())`.
- `type.getPackageName()`, `type.getModule()`, `type.getClassLoader()` và loader thực sự truyền vào `Proxy.newProxyInstance`.
- Toàn bộ interface trong mảng, thứ tự và các kiểu xuất hiện trong chữ ký `public`, kể cả interface kế thừa.
- Loại exception và nguyên nhân; tránh dựa vào chuỗi thông báo exception chính xác vì thông báo có thể thay đổi theo JDK.

Ví dụ **không hợp lệ** về trùng interface:

```java
Proxy.newProxyInstance(
        PublicApi.class.getClassLoader(),
        new Class<?>[]{PublicApi.class, PublicApi.class},
        handler);
```

Đây là **mảnh minh họa** sử dụng `PublicApi` và `handler` đã khai báo ở chương trình trước, không phải chương trình độc lập. Lỗi này là `IllegalArgumentException` dù `PublicApi` hoàn toàn public, không hidden và không sealed.

## 8. Hiểu đúng các lỗi hay gặp

| Quan niệm hoặc cách sửa sai | Cách xử lý đúng |
| --- | --- |
| “Chỉ có `public interface` mới dùng được JDK Proxy.” | Non-public hợp lệ nếu đáp ứng chặt chẽ package/module/loader. |
| “Non-public interface đồng nghĩa package không export.” | Modifier của interface và mức export/open của package là hai khái niệm khác nhau. |
| “Có `Class<?>` của hidden interface thì vẫn proxy được.” | `isHidden() == true` bị JDK Proxy loại dù đã có đối tượng `Class`. |
| “Sealed interface public thì được.” | `isSealed() == true` bị từ chối độc lập với modifier `public`. |
| “Đổi loader sang `Thread.currentThread().getContextClassLoader()` chắc chắn sửa lỗi.” | Phải chứng minh loader chỉ định thấy đúng identity của mọi interface và mọi kiểu trong chữ ký, cùng quy tắc dành cho non-public. |
| “Đã tạo proxy thành công thì có thể gọi constructor lớp `$Proxy...`.” | Quyền truy cập lớp proxy có thể bị module đóng; dùng `Proxy.newProxyInstance`. |
| “`newProxyInstance` chỉ kiểm tra `isInterface()`.” | Javadoc còn ràng buộc sealed/hidden, trùng lặp, loader, chữ ký, package/module, VM limits. |
| “Mỗi interface có proxy riêng được thì ghép chúng luôn được.” | Tập interface kết hợp có thể xung đột về non-public package/module hoặc kiểu trả về của phương thức. |

## 9. Bài tập và câu hỏi tự kiểm tra

1. Hai interface **package-private** ở cùng package và cùng module, được định nghĩa bởi đúng class loader, có thể được đưa chung vào `newProxyInstance` không? Hãy giải thích các điều kiện còn lại vẫn phải kiểm tra.
2. Một `public interface` nằm trong package **không export, không open** của named module có bị từ chối chỉ vì package đóng không? Lớp proxy sẽ nằm ở đâu theo quy tắc JDK?
3. Trong ví dụ, vì sao `InternalApi` tạo được proxy dù `Modifier.isPublic(InternalApi.class.getModifiers()) == false`?
4. Vì sao `HiddenSeed.class` lúc mới biên dịch khác với `Class<?> hidden` do `defineHiddenClass` trả về?
5. Nếu một interface có `isSealed() == true` và đồng thời là `public`, điều kiện nào quyết định kết quả của `newProxyInstance`?
6. Nếu hai interface đều `public`, không hidden/sealed nhưng khai báo cùng phương thức `value()` với hai kiểu trả về nguyên thủy khác nhau, vì sao yêu cầu proxy có thể thất bại?

**Tự kiểm tra trước khi thiết kế thư viện:** Trước tiên phân loại `isInterface / isHidden / isSealed`; sau đó kiểm tra loader, tập interface, chữ ký, package/module và quyền truy cập từ mã sử dụng proxy. Dùng **`Proxy.newProxyInstance`** làm API tạo instance, sau đó làm việc qua các interface mà mã người gọi thực sự được phép truy cập.

## 10. Tài liệu chính thức

- [Oracle Java 17 — `java.lang.reflect.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): Restrictions, Package and Module Membership of Proxy Class, Dynamic Modules và ngoại lệ của `newProxyInstance`.
- [Oracle Java 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isInterface`, `isHidden`, `isSealed`, `getModifiers`, `getModule` và `getClassLoader`.
- [Oracle Java 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass` và cách tạo hidden class/interface.
- [Java Language Specification 17 — Sealed Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): ngữ nghĩa `sealed`, `permits`, `non-sealed`.