# Dynamic Proxy và khả năng nhìn thấy các interface trong Java ClassLoader

## 1. Bài toán: vì sao một interface tồn tại nhưng không thể tạo Dynamic Proxy?

Java Dynamic Proxy là cơ chế tạo **một class triển khai interface ngay khi chạy**, không cần biên dịch trước một implementation cố định. API cốt lõi là `java.lang.reflect.Proxy.newProxyInstance`:

~~~java
Object proxy = Proxy.newProxyInstance(
        chosenLoader,
        new Class<?>[] { SomeService.class },
        invocationHandler
);
~~~

Trong chương trình đơn giản, chọn `SomeService.class.getClassLoader()` hoặc một loader tương thích thường hoạt động. Nhưng trong plugin system, application server, JPMS layer hoặc hot reload, một đối tượng `Class<?>` của interface có thể **không nhìn thấy được theo tên** từ ClassLoader được chọn để định nghĩa proxy. Khi đó Java có thể ném **`IllegalArgumentException`** trong chính lời gọi tạo proxy.

**Khái niệm then chốt:** Không đủ để loader “tìm thấy một interface cùng tên”. Nó phải tìm được **đúng cùng đối tượng `Class<?>` của interface**.

Java 17 định nghĩa điều kiện cần kiểm tra đối với từng interface `i` và loader `cl`:

~~~java
Class.forName(i.getName(), false, cl) == i
~~~

Dấu `==` là **đồng nhất Class runtime**, không phải so tên chuỗi. Nếu biểu thức trả false, `i` **không visible by name** qua loader được yêu cầu cho proxy. Nếu `Class.forName` ném `ClassNotFoundException`, interface còn chưa tìm được bằng loader ấy.

Trong nhiều trường hợp lỗi phát sinh vì:

- Chọn **bootstrap/platform loader** cho một interface chỉ có ở application loader.
- Chọn **sibling loader** không thể delegate sang nơi đã định nghĩa interface.
- Plugin loader child-first tự định nghĩa một bản **interface cùng binary name** với bản host.
- Các **kiểu nằm trong public method signatures** của interface không thấy được qua loader proxy.
- Interface **non-public** nằm khác package/module, khác defining loader hoặc không thể truy cập theo quy tắc của `Proxy`.
- Interface **sealed** (Java 17) hoặc **hidden** không hợp lệ để Dynamic Proxy implement.
- Một nhóm interface có các phương thức trùng signature nhưng return types không tương thích.

Bài này giải thích điều kiện Java 17, cách chọn loader, thí nghiệm “không nhìn thấy / nhìn thấy bản sao / nhìn thấy đúng” có thể chạy được, các giới hạn với JPMS, xử lý `InvocationHandler`, lỗi phổ biến và cách thiết kế plugin boundary.

## 2. Dynamic Proxy hoạt động theo sơ đồ nào?

Một object proxy có hai phần chính:

1. **Proxy class runtime** do JDK sinh ra, implements các interface được chỉ định, extends `java.lang.reflect.Proxy`.
2. **InvocationHandler** chứa logic xử lý những lời gọi qua interface methods.

~~~text
Consumer code
   |
   v
SomeService service = (SomeService) proxy;
   |
   v
service.request("x")
   |
   v
Generated proxy class
   |
   v
InvocationHandler.invoke(proxy, Method request, ["x"])
   |
   v
Handler logic -> return value / throw exception
   |
   v
Consumer receives result
~~~

Với proxy được tạo đúng, `proxy instanceof SomeService` là true; cast `(SomeService) proxy` thành công. Khi gọi method qua proxy, JDK truyền tới handler ba thông tin:

- `proxy`: chính instance proxy.
- `method`: một `java.lang.reflect.Method` mô tả interface method được gọi; có thể thuộc inherited superinterface.
- `args`: mảng tham số; nếu method không có tham số thì có thể là **`null`**, không được mặc định là mảng rỗng.

Handler trả một `Object`. Proxy phải chuyển giá trị trả về phù hợp với kiểu khai báo: primitive yêu cầu wrapper đúng để unbox, kiểu reference phải assignable; sai kiểu có thể ném `ClassCastException` hoặc `NullPointerException`.

Dynamic Proxy **không tự thực thi body của một concrete implementation**. Nếu handler muốn forward tới target object, handler phải chủ động gọi target; nếu muốn tính giá trị, nó tự tính. Với **default methods** của interface, `InvocationHandler.invokeDefault` (Java 16+) là lựa chọn khi muốn gọi triển khai default thực sự.

## 3. Interface visibility là identity, không phải tên

Theo đặc tả JVM, class/interface được nhận diện bằng **(binary name, defining ClassLoader)**. Hai loaders có thể định nghĩa hai interface tên `api.Greeter` riêng:

~~~text
Host application loader:
    api.Greeter  -> Class H

Plugin child-first loader:
    api.Greeter  -> Class P

H.getName().equals(P.getName()) == true
H == P                              == false
~~~

Nếu host truyền `H` cho `Proxy.newProxyInstance(pluginLoader, new Class<?>[]{H}, h)`, nhưng `pluginLoader.loadClass("api.Greeter")` trả `P`, proxy **không được tạo**. Loader ấy nhìn thấy **P**, không nhìn thấy **H** bằng binary name.

Hai biến thể cần phân biệt:

| Hiện tượng | Kết quả khi hỏi interface bằng proxy loader |
| --- | --- |
| Loader không thể tìm interface | `ClassNotFoundException` khi thử `Class.forName` |
| Loader tìm interface cùng tên nhưng bản riêng | `Class.forName(..., loader) != expectedInterface` |
| Loader delegate đúng parent và nhận cùng Class | `Class.forName(..., loader) == expectedInterface` |

Trường hợp thứ hai rất nguy hiểm khi chỉ xem log: tên interface hoàn toàn đúng nhưng identity sai. Đây cũng là nguồn lỗi `ClassCastException` “`api.Greeter cannot be cast to api.Greeter`” và provider **not a subtype** trong các kiến trúc plugin khác.

**Điều kiện proxy không đòi tất cả interface phải được định nghĩa bởi chính loader truyền vào.** Một child loader **có thể delegate** các shared interface cho parent và vẫn tạo proxy hợp lệ, miễn kết quả lookup đúng chính Class runtime.

## 4. Chữ ký API, ý nghĩa từng tham số

Chữ ký Java 17:

~~~java
public static Object newProxyInstance(
        ClassLoader loader,
        Class<?>[] interfaces,
        InvocationHandler h
)
~~~

- `loader`: loader được JDK dùng để **định nghĩa proxy class** và kiểm tra visibility.
- `interfaces`: tập các **Class objects đại diện interface** mà proxy class sẽ implement, theo thứ tự chỉ định.
- `h`: InvocationHandler được gọi khi một interface method được thực thi.

Nên dùng:

~~~java
Greeter proxy = (Greeter) Proxy.newProxyInstance(
        Greeter.class.getClassLoader(),
        new Class<?>[] { Greeter.class },
        (p, method, arguments) -> "Hello"
);
~~~

Đây là **đoạn minh họa** giả định `Greeter` có đúng method signature tương ứng, không phải một file runnable độc lập. Để chạy ổn định và có câu trả lời chính xác, xem chương trình đầy đủ ở mục 7.

### 4.1. Có thể truyền null loader không?

`loader == null` nghĩa sử dụng bootstrap class loader trong những hoàn cảnh API cho phép. Nó **không** phải ký hiệu cho “auto choose suitable loader”. Với interface của ứng dụng định nghĩa bởi application loader, bootstrap loader thông thường **không thể nhìn thấy interface ấy**, nên truyền null không giải quyết được vấn đề.

### 4.2. Interface array cần Class<?> thật

`interfaces` không nhận các tên chuỗi; nó nhận đúng `Class<?>` của các interface. Nếu cần load theo tên từ plugin, phải kiểm tra rõ provenance và identity của từng Class. Đừng biến danh sách tên lấy từ input ngoài thành các interfaces tùy ý rồi mong proxy là một security boundary.

### 4.3. Vì sao handler không quyết định visibility?

`InvocationHandler` được truyền **sau** phần lựa chọn loader và interface Class objects. Handler có thể là lambda của host, nhưng điều đó không cho phép một proxy Class thiếu access hay không nhìn thấy interface tự nhiên được sinh ra. Visibility check diễn ra trong quá trình tạo proxy, trước khi handler được gọi.

## 5. Những ràng buộc trong Proxy.newProxyInstance trên Java 17

Để proxy class được tạo hợp lệ, Java 17 yêu cầu nhiều điều kiện, không chỉ visibility:

| Điều kiện | Lý do |
| --- | --- |
| Mỗi phần tử `interfaces` là một interface | Proxy tạo implementation của interfaces, không kế thừa arbitrary class |
| Interface không phải `hidden` | Hidden class không hỗ trợ lookup bằng tên như yêu cầu |
| Interface không phải `sealed` | Dynamic proxy không phải một permitted implementation tĩnh trong sealed hierarchy |
| Không lặp cùng một `Class<?>` trong mảng | Danh sách interfaces cần không duplicate |
| Mọi interface visible by name qua loader | `Class.forName(i.getName(), false, loader) == i` |
| Mọi kiểu trong **public method signatures** của interfaces cũng visible by name | Proxy class phải khai báo hợp lệ method descriptors |
| Mọi **non-public interfaces** phải cùng package và module, được loader chỉ định định nghĩa | Đảm bảo một proxy class có thể truy cập toàn bộ interfaces |
| Trùng method signature phải có return types tương thích | Proxy chỉ sinh một implementation cho một signature |
| Không vượt VM class/interface limits | Class file/VM có giới hạn cấu trúc |

Vi phạm các restrictions này thường khiến `newProxyInstance` ném **`IllegalArgumentException`**. Null array, phần tử null hoặc handler null có thể khiến `NullPointerException`; một số policy runtime cũ có thể báo `SecurityException`, phụ thuộc JVM và security manager configuration.

**Trường hợp visibility cần nhớ nguyên văn ý tưởng:**

~~~java
boolean visible =
        Class.forName(iface.getName(), false, chosenLoader) == iface;
~~~

Trong mã thực tế, câu lệnh cần `throws ClassNotFoundException` hoặc `try/catch`. Nếu `visible` false dù tên trùng, đổi loader hoặc sửa cách nạp shared API; không “sửa” bằng cách so String.

## 6. Chọn ClassLoader nào khi tạo proxy?

### 6.1. Một interface public thuộc application classpath

Cách phổ biến:

~~~java
ClassLoader loader = ServiceApi.class.getClassLoader();
Object proxy = Proxy.newProxyInstance(
        loader, new Class<?>[] { ServiceApi.class }, handler);
~~~

**Mã minh họa**, giả sử `ServiceApi` và `handler` hợp lệ. Chọn defining loader của API có lợi vì loader ấy phải nhìn thấy chính interface, nhưng vẫn cần xét **signature types** và những interface bổ sung khi tạo proxy đa interface.

### 6.2. Nhiều interfaces từ nhiều loaders

Nếu một proxy phải implement cả `ApiA.class` và `ApiB.class`, loader cần nhìn thấy **cả hai Class runtime** bằng tên, bao gồm những types dùng trong public method signatures. Một loader child có parent chung và biết về cả interfaces có thể phù hợp; không có công thức “lấy loader của interface đầu tiên” luôn đúng.

Sơ đồ:

~~~text
         Common parent loader
        /                    \
  Interface A               Interface B
        \                    /
         \                  /
         chosen proxy loader
             sees A and B?
                 |
            yes -> proxy
            no  -> IllegalArgumentException
~~~

Nếu A và B nằm trong **sibling loaders** không có delegation phù hợp, bạn cần kiến trúc loader chung hoặc adapter/boundary khác. Không thể ép hai Class trùng tên/khác loader trở thành một.

### 6.3. API host và implementation plugin

Thiết kế thường dùng:

~~~text
      Host/CommonLoader
         shared.Api
         shared.Dto
             ^
             | parent delegation
             |
         PluginLoader
       plugin.Implementation
       plugin.PrivateDependency
~~~

Nếu host cần cast proxy sang `shared.Api`, hãy bảo đảm `shared.Api` là **một Class runtime chung**, thường do common parent định nghĩa. Plugin loader có thể tìm implementation/private dependencies riêng; Dynamic Proxy không phải lý do để copy service interface vào mỗi plugin.

### 6.4. Thread Context ClassLoader

`Thread.currentThread().getContextClassLoader()` (TCCL) hữu ích cho discovery frameworks, nhưng **không luôn là lựa chọn đúng** cho `Proxy.newProxyInstance`. TCCL có thể là plugin loader đang child-first cho bản API khác, hoặc một loader không nhìn thấy API của host.

Đừng mặc định:

~~~java
Proxy.newProxyInstance(
        Thread.currentThread().getContextClassLoader(),
        new Class<?>[] { HostApi.class },
        handler
);
~~~

Nếu TCCL không nhìn thấy **chính HostApi Class**, lời gọi thất bại. Dùng explicit visibility check và chọn loader dựa trên ownership của contract.

## 7. Thí nghiệm Java 17+ hoàn chỉnh: không thấy, thấy bản sao, thấy đúng

Thí nghiệm sử dụng:

- Một interface public `api.Greeter` trong **host classpath**.
- Một bản bytecode của **cùng interface** trong thư mục riêng `shadow-classes`.
- Một `URLClassLoader` cô lập không nhìn thấy host API.
- Một custom `URLClassLoader` child-first cho chính tên `api.Greeter` nhằm tạo **bản sao runtime**.
- Một proxy được tạo từ loader của host API, dùng chung Class đúng.

### 7.1. Cây thư mục

~~~text
proxy-visibility-demo/
├── src-api/
│   └── api/
│       └── Greeter.java
└── src-host/
    └── ProxyVisibilityDemo.java
~~~

Sau compile:

~~~text
host-classes/
├── ProxyVisibilityDemo.class
├── ProxyVisibilityDemo$ShadowLoader.class
└── api/
    └── Greeter.class

shadow-classes/
└── api/
    └── Greeter.class
~~~

**Không đưa `shadow-classes` vào `java -cp` của host**, để parent application class loader chỉ biết bản host API. `ShadowLoader` nhận đường dẫn đó như một `URLClassLoader` root riêng.

### 7.2. File src-api/api/Greeter.java

~~~java
package api;

public interface Greeter {
    String greet(String name);
}
~~~

Interface public, không sealed, chỉ nhắc tới Java core `String` trong method signature. Vì vậy ví dụ tập trung vào visibility của **chính interface**, không bị ảnh hưởng bởi một DTO khác khó tìm.

### 7.3. File src-host/ProxyVisibilityDemo.java

~~~java
import api.Greeter;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyVisibilityDemo {
    static final class ShadowLoader extends URLClassLoader {
        ShadowLoader(Path classes) throws Exception {
            super(
                    new URL[] { classes.toAbsolutePath().toUri().toURL() },
                    ProxyVisibilityDemo.class.getClassLoader()
            );
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals("api.Greeter")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = findClass(name);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    static boolean visible(ClassLoader loader, Class<?> type) {
        try {
            return Class.forName(type.getName(), false, loader) == type;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }

    static InvocationHandler handler() {
        return (proxy, method, args) -> {
            if (method.getName().equals("greet")) {
                return "Hello, " + args[0];
            }
            throw new UnsupportedOperationException(method.getName());
        };
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ProxyVisibilityDemo <shadow-classes-dir>");
        }

        ClassLoader hostLoader = Greeter.class.getClassLoader();

        try (URLClassLoader isolated = new URLClassLoader(
                        new URL[0],
                        ClassLoader.getPlatformClassLoader());
             ShadowLoader shadow = new ShadowLoader(Path.of(args[0]))) {

            System.out.println("isolated sees host interface: "
                    + visible(isolated, Greeter.class));

            try {
                Proxy.newProxyInstance(
                        isolated,
                        new Class<?>[] { Greeter.class },
                        handler());
                System.out.println("isolated rejected: false");
            } catch (IllegalArgumentException expected) {
                System.out.println("isolated rejected: true");
            }

            Class<?> foreign = shadow.loadClass("api.Greeter");
            System.out.println("shadow same name: "
                    + foreign.getName().equals(Greeter.class.getName()));
            System.out.println("shadow same Class: "
                    + (foreign == Greeter.class));
            System.out.println("shadow sees host interface: "
                    + visible(shadow, Greeter.class));

            try {
                Proxy.newProxyInstance(
                        shadow,
                        new Class<?>[] { Greeter.class },
                        handler());
                System.out.println("shadow host proxy rejected: false");
            } catch (IllegalArgumentException expected) {
                System.out.println("shadow host proxy rejected: true");
            }

            Object foreignProxy = Proxy.newProxyInstance(
                    shadow,
                    new Class<?>[] { foreign },
                    handler());

            System.out.println("foreign proxy is host Greeter: "
                    + (foreignProxy instanceof Greeter));
            System.out.println("foreign proxy call: "
                    + foreign.getMethod("greet", String.class)
                             .invoke(foreignProxy, "Ada"));

            Greeter good = (Greeter) Proxy.newProxyInstance(
                    hostLoader,
                    new Class<?>[] { Greeter.class },
                    handler());

            System.out.println("shared proxy is host Greeter: "
                    + (good instanceof Greeter));
            System.out.println("shared proxy call: "
                    + good.greet("Ada"));
        }
    }
}
~~~

### 7.4. Biên dịch và chạy

Đứng ở thư mục `proxy-visibility-demo` với JDK 17+:

~~~bash
javac --release 17 -d host-classes src-api/api/Greeter.java src-host/ProxyVisibilityDemo.java
javac --release 17 -d shadow-classes src-api/api/Greeter.java
java -cp host-classes ProxyVisibilityDemo shadow-classes
~~~

Ba lệnh này có cùng cú pháp cơ bản trên PowerShell, CMD, bash, zsh vì không cần separator liệt kê nhiều classpath entries.

**Stdout dự kiến chính xác** với mã và cấu trúc thư mục trên:

~~~text
isolated sees host interface: false
isolated rejected: true
shadow same name: true
shadow same Class: false
shadow sees host interface: false
shadow host proxy rejected: true
foreign proxy is host Greeter: false
foreign proxy call: Hello, Ada
shared proxy is host Greeter: true
shared proxy call: Hello, Ada
~~~

### 7.5. Giải thích từng trường hợp

**Loader không thấy interface:**

- `isolated` có parent là platform loader, **không phải application loader** chứa `api.Greeter`.
- URL list rỗng, nên `Class.forName("api.Greeter", false, isolated)` không tìm được API host.
- Lời gọi `newProxyInstance(isolated, [Greeter.class], handler)` bị từ chối bằng `IllegalArgumentException`.

**Loader thấy bản riêng cùng tên:**

- `shadow` kế thừa `URLClassLoader` nhưng override `loadClass` **chỉ cho `api.Greeter`** thành child-first, lấy bytes từ `shadow-classes`.
- Class do shadow tự define khác `Greeter.class` của host, dù cả hai có `getName() == "api.Greeter"`.
- Truyền **host Greeter.class** với `shadow` thất bại visibility condition vì shadow sẽ tìm thấy Class bản sao.
- Truyền **foreign Class** cho shadow lại hợp lệ: shadow nhìn thấy đúng Class của nó, proxy được tạo.
- Tuy nhiên foreign proxy implements foreign `api.Greeter`, không implements host `api.Greeter`. Do đó `instanceof Greeter` false. Reflection theo foreign interface vẫn gọi được `greet("Ada")`.

**Chọn shared/host loader đúng:**

- `hostLoader` nhìn thấy đúng `Greeter.class`.
- Proxy được định nghĩa để implement interface Class của host, cast thành `Greeter` hợp lệ và gọi method trả chuỗi dự kiến.

**Kết luận thực nghiệm:** Tạo được một proxy trong loader plugin chưa đồng nghĩa host cast được nó sang một interface cùng tên. Cần đồng nhất **contract Class identity** ở ranh giới trao đổi.

## 8. Chọn đúng interface Class khi plugin có API trùng

Có hai quyết định khác nhau:

1. **Tôi muốn proxy implement interface của ai?** Nếu host sẽ dùng proxy qua `HostApi`, interface array **phải chứa `HostApi.class` của host**.
2. **Loader nào có thể nhìn thấy chính Class ấy?** Chọn một loader mà `Class.forName(HostApi.class.getName(), false, loader) == HostApi.class`, đồng thời nhìn thấy các kiểu signature và các interfaces khác.

Nếu chỉ đổi interface array sang bản `PluginApi` để làm `newProxyInstance` hết lỗi, bạn có thể tạo một proxy **chạy được trong plugin** nhưng **không dùng được qua host contract**. Lựa chọn sửa đúng thường là đưa API types vào **parent/common loader**, bắt plugin delegate `shared.api.*` về đó.

Một adapter có thể chuyển data giữa hai contract không tương thích khi không thể thống nhất loader, nhưng không nên ép cast Class runtime sai.

## 9. Kiểm tra kiểu trong public method signatures

Java 17 còn yêu cầu **các loại dữ liệu tham chiếu xuất hiện trong mọi public method signatures** của proxy interfaces và inherited superinterfaces nhìn thấy được theo tên qua loader đã chọn.

Ví dụ interface:

~~~java
package api;

public interface Processor {
    api.dto.Result process(api.dto.Request input);
}
~~~

Đây là **mã minh họa**, giả sử `api.dto.Request` và `api.dto.Result` đã có. Dù `Processor.class` visible qua loader, proxy vẫn có thể không được định nghĩa nếu loader không nhìn thấy chính các Class runtime tương ứng với `Request` và `Result`.

Điều này có thể xảy ra khi:

- Host API interface nằm trong parent loader nhưng DTO của cùng contract vô tình được loader con định nghĩa riêng.
- Interface public method dùng exception/return/parameter types nằm trong module/plugin loader khác không được chọn loader proxy nhìn thấy phù hợp.
- Một inherited superinterface đưa vào type tham chiếu mà người viết chỉ xem methods khai báo trực tiếp đã bỏ sót.

**Đừng chỉ kiểm tra visibility của interface bề mặt.** Cần thiết kế toàn bộ **API surface** thống nhất: parameter types, return types, interfaces liên quan và public method signatures. Các types private implementation không lộ ra ở signature có thể tiếp tục cô lập.

Một checker cơ bản minh họa:

~~~java
static boolean visibleByName(ClassLoader loader, Class<?> type) {
    try {
        return Class.forName(type.getName(), false, loader) == type;
    } catch (ClassNotFoundException e) {
        return false;
    }
}
~~~

Đây là **đoạn minh họa**, không phải test tổng quát đủ mọi kiểu vì array/primitive types và method signature traversal có những chi tiết riêng. Khi làm framework, cần xử lý `void`, primitives, array component types và all inherited methods đúng quy tắc.

## 10. Non-public interfaces: cùng package/module và defining loader

Một interface chỉ có package-private access, ví dụ:

~~~java
package internal;

interface HiddenContract {
    String value();
}
~~~

không giống interface `public`. Dynamic Proxy vẫn có thể implement non-public interfaces trong những điều kiện thích hợp, nhưng Java 17 yêu cầu **tất cả non-public proxy interfaces**:

- Nằm **cùng package và cùng module**.
- Được **loader chỉ định cho proxy định nghĩa**.
- Module chứa non-public interfaces có thể truy cập toàn bộ interface types được yêu cầu.

Một proxy class có non-public interface thường không public và được đặt trong package/module của non-public interfaces. Vì vậy chỉ hỏi “loader nhìn thấy interface” là **chưa đủ** để chứng minh tổ hợp interfaces hợp lệ.

Đây là lý do không thể tùy tiện trộn:

~~~text
package a; interface A { ... }  // non-public
package b; interface B { ... }  // non-public
~~~

thành một proxy triển khai cả hai nếu chúng ở các package/module khác nhau. Lỗi dự kiến là `IllegalArgumentException` trong lời gọi tạo proxy.

Nếu plugin API cần chia sẻ cho code ngoài package/module, cân nhắc một interface **public, nằm trong package được export phù hợp**, thay vì dùng package-private interface làm contract xuyên loader. Không cố khắc phục bằng `setAccessible(true)`; JPMS và Dynamic Proxy có ràng buộc structural riêng.

## 11. JPMS: proxy class được đặt trong module nào?

Từ Java 9+, Dynamic Proxy còn phải tương thích Java Platform Module System (**JPMS**). Tên/package/module của proxy class **không được giả định cố định**. Java 17 chọn vị trí sinh proxy sao cho mức độ truy cập tương thích với các proxy interfaces.

Các nhánh phổ biến trong Javadoc:

| Proxy interfaces | Proxy class ở đâu? |
| --- | --- |
| Tất cả public, thuộc các package được export/open phù hợp | Public proxy trong một package được export vô điều kiện nhưng không open; tên package/module không được bảo đảm |
| Có non-public interfaces | Proxy non-public trong package/module của các non-public interfaces, với điều kiện cùng package/module và loader |
| Có public interface thuộc package không export và không open rộng rãi | Proxy có thể là public class trong **dynamic module**, ở package không export và không open |
| Hỗn hợp accessibilities | Mức truy cập thấp nhất của interfaces chi phối khả năng truy cập proxy class |

**Dynamic module** ở đây là một named module được tạo bởi cơ chế proxy tại runtime, không phải tên module bạn tự đặt trong `module-info.java`. Proxy trong dynamic module có thể bị encapsulation che khỏi constructor reflection ở ngoài module.

Ví dụ:

~~~java
Object p = Proxy.newProxyInstance(loader, interfaces, handler);
~~~

được khuyến nghị thay cho pattern tạo proxy class rồi gọi constructor reflection bằng tay. API `Proxy.getProxyClass` đã **deprecated** trong Java 17, vì proxy classes thuộc named/dynamic modules có thể không cho caller ngoài module gọi constructor qua reflection. `Proxy.newProxyInstance` xử lý các điều kiện hợp đồng cần thiết.

### Module exports/opens và interface visibility khác nhau

- **Visible by name** hỏi loader có resolve ra **đúng Class object** không.
- **Readability/exports/opens** hỏi code/module nào có quyền truy cập types/packages ở runtime.
- Hai điều kiện có liên hệ nhưng **không tương đương**. Một loader có thể thấy Class bằng tên mà một module/caller vẫn chưa được quyền truy cập trực tiếp nó.
- Không nên dùng `--add-opens`/`--add-exports` ngẫu nhiên để chữa lỗi duplication do class loader. Nếu Class identity khác nhau, đổi access flags không làm hai Class hợp nhất.

## 12. Dynamic Proxy không hỗ trợ sealed/hidden interface theo Java 17

Java 17 có sealed types, ví dụ:

~~~java
public sealed interface Operation permits FixedOperation {
    int run();
}

final class FixedOperation implements Operation {
    @Override
    public int run() {
        return 1;
    }
}
~~~

**Mã minh họa**, không phải một file runnable có main. `Operation` là sealed interface; một Dynamic Proxy class không nằm trong permits clause được compiler khai báo nên Java 17 `Proxy.newProxyInstance` **từ chối** loại interface này theo restriction **non-sealed interface**. Không phải lỗi do loader visibility.

Tương tự, một **hidden interface** không đáp ứng yêu cầu interface visible by name. Không cố dùng `Lookup.defineHiddenClass` rồi bắt proxy generator tự implements hidden interface; API Java 17 yêu cầu non-hidden interfaces.

Một class bất kỳ cũng không được cung cấp vào `interfaces` array; mỗi phần tử phải là **interface type**. Với interface marker thông thường hoặc interface có default methods, proxy có thể tạo được nếu các điều kiện khác được đáp ứng.

## 13. Nhiều interfaces có methods trùng nhau

Dynamic Proxy có thể implements hơn một interface:

~~~java
interface A {
    Number get();
}

interface B {
    Integer get();
}
~~~

**Đoạn minh họa**. Hai methods có cùng name và parameters, nhưng return types covariant: `Integer` assignable vào `Number`. Java có thể tạo proxy nếu điều kiện loader/access phù hợp.

Ngược lại:

~~~java
interface Left {
    String value();
}

interface Right {
    Integer value();
}
~~~

**Đoạn minh họa**. Hai return types không tương thích, nên một proxy không thể triển khai cả hai cùng method signature và đáp ứng rules; `newProxyInstance` có thể ném `IllegalArgumentException`.

Khi cả A và B cùng khai báo method name/parameter signature:

- **Thứ tự interfaces** trong array có ý nghĩa. Method object đưa đến handler có thể thuộc **interface xuất hiện trước** chứa method ấy, dù caller gọi qua reference kiểu interface khác.
- Nếu method là `equals`, `hashCode` hoặc `toString` của `Object`, handler nhận Method có declaring class là `java.lang.Object`.
- Checked exceptions ném từ handler phải tương thích với **throws clauses** của các method signatures trùng nhau. Nếu không, proxy có thể bọc trong `UndeclaredThrowableException`.

Đừng dùng `method.getDeclaringClass()` như phép đo duy nhất để biết caller đã gọi qua interface reference nào; với methods trùng nhau, Javadoc nêu rõ nó không đủ.

## 14. Handler: default methods, Object methods và exceptions

### 14.1. Object methods cũng đi qua handler

Proxy chuyển các lời gọi `equals`, `hashCode`, `toString` public từ `Object` vào InvocationHandler. Nếu handler chỉ xử lý một method nghiệp vụ rồi ném `UnsupportedOperationException` cho tất cả trường hợp khác, code framework/logging gọi `proxy.toString()` có thể thất bại.

Một handler đủ rõ để minh họa:

~~~java
InvocationHandler h = (proxy, method, args) -> {
    switch (method.getName()) {
        case "toString":
            return "GreeterProxy";
        case "hashCode":
            return System.identityHashCode(proxy);
        case "equals":
            return proxy == args[0];
        case "greet":
            return "Hello, " + args[0];
        default:
            throw new UnsupportedOperationException(method.toString());
    }
};
~~~

**Đoạn code minh họa** cần biến và interface phù hợp. Trong handler, đừng gọi `proxy.toString()` để triển khai `toString`, vì nó sẽ quay lại chính handler gây recursion. Với `equals`, cần quyết định semantics rõ thay vì mặc nhiên delegate tới một target không cùng identity.

### 14.2. Gọi default method

Java 17 hỗ trợ:

~~~java
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(
            proxy, method, args == null ? new Object[0] : args);
}
~~~

Đây là **đoạn minh họa** dùng bên trong InvocationHandler. `InvocationHandler.invokeDefault` (Java 16+) thực hiện default implementation theo rules của proxy interface; chỉ dùng khi `method` thực sự là default method được phép. Nếu handler tự trả kết quả thì default method không tự chạy.

### 14.3. Checked exception không khai báo

Nếu handler ném checked exception không được cho phép bởi interface method's `throws` clause, lời gọi qua proxy có thể ném `UndeclaredThrowableException`. Nó là `RuntimeException` wrapper, không phải bằng chứng rằng proxy loader nhìn sai interface.

Lỗi theo các tầng:

| Giai đoạn | Lỗi điển hình |
| --- | --- |
| Tạo proxy; interface không nhìn thấy/không hợp lệ | `IllegalArgumentException` |
| Tạo proxy; interface array, phần tử, handler null | `NullPointerException` |
| Cast proxy vào interface Class khác runtime | `ClassCastException` |
| Handler trả null cho primitive | `NullPointerException` khi unbox |
| Handler trả giá trị không tương thích declared return | `ClassCastException` |
| Handler ném checked exception ngoài `throws` | `UndeclaredThrowableException` |
| JPMS reflection tới proxy constructor bị encapsulate | `IllegalAccessException` / access error phù hợp |
| Class initialization/linkage/dependency bị lỗi | `LinkageError` hoặc error phù hợp hoàn cảnh |

**Không gom mọi lỗi ở ứng dụng dùng Dynamic Proxy thành lỗi ClassLoader.** Cần tách lỗi lúc generate proxy, lúc handler dispatch và lúc caller cast/consume result.

## 15. Thiết kế proxy trong hệ thống plugin

Một kiến trúc thông thường:

~~~text
                         Host process
             +--------------------------------+
             | Shared API (loader H)          |
             | api.Service                    |
             | api.Request / api.Response     |
             +----------------+---------------+
                              ^
                 parent delegation
                              |
          +-------------------+------------------+
          |                                      |
       Plugin A                                 Plugin B
       loader A                                 loader B
       impl.*                                   impl.*
       private.lib.*                            private.lib.*
          |                                      |
      handler A                              handler B
          |                                      |
          +-------- proxy as api.Service --------+
                              |
                           Host caller
~~~

Các nguyên tắc:

1. **Đặt service API trong common parent loader/module** mà host và plugins đều nhìn thấy cùng Class runtime.
2. **Không đóng gói bản API bị child-first define lại** chỉ để plugin compile. Có thể đưa API dependency vào compile classpath mà không đưa bản duplicate vào packaged plugin, tùy Maven/Gradle setup.
3. **DTO, callbacks, exception types** trong public method signatures cũng là phần của shared contract; không chỉ interface chính.
4. **Dùng interface array của host** nếu proxy cần trả về cho host. Không dùng Class cùng tên do plugin tự define.
5. **Chọn một proxy loader nhìn thấy toàn bộ interfaces** và signature types, không mặc định sử dụng TCCL.
6. **Tách implementation logic khỏi API identity.** InvocationHandler có thể gọi private target của plugin; kết quả/exception cần được chuyển về shared contract hợp lệ.
7. **Không dựa vào proxy để sandbox code plugin.** JDK proxy chỉ điều phối method invocations; code của handler/target vẫn có quyền của process/container tương ứng.
8. **Quản lý lifecycle/hot reload.** Các caches của proxy Classes và references từ InvocationHandler có thể giữ plugin ClassLoader cũ sống lâu hơn mong đợi. Khi reload cần release references và tạo loader/target mới có chủ đích.

Nếu dùng `ServiceLoader` để tìm implementations rồi bọc proxy, ServiceLoader provider cũng phải implement đúng shared service Class. Proxy không phải biện pháp bỏ qua lỗi “provider not a subtype”.

## 16. Ví dụ kiểm tra trước khi tạo proxy

Đây là một **mẫu helper** (không phải validator tổng quát hết mọi điều kiện):

~~~java
static void requireVisible(
        ClassLoader chosen, Class<?> iface)
        throws ClassNotFoundException {
    if (!iface.isInterface()) {
        throw new IllegalArgumentException(
                "Not an interface: " + iface.getName());
    }
    Class<?> fromChosen = Class.forName(
            iface.getName(), false, chosen);
    if (fromChosen != iface) {
        throw new IllegalArgumentException(
                "Same binary name, different runtime Class: "
                + iface.getName());
    }
}
~~~

**Điểm mạnh:** helper cung cấp thông báo rõ hơn về tên trùng nhưng loader khác, có ích cho log.

**Giới hạn:** helper chưa kiểm tra interfaces trùng trong array, sealed/hidden, non-public rules, module access, return-type compatibility hay types được tham chiếu trong public signatures. Với production framework, nên để `Proxy.newProxyInstance` thực hiện các checks đầy đủ và dùng helper chỉ để chẩn đoán.

Dùng `Class.forName(name, false, chosen)` **không yêu cầu chạy static initializer** của interface chỉ vì kiểm tra visibility, tránh tác dụng phụ không cần thiết trong preflight.

## 17. Chẩn đoán một lỗi IllegalArgumentException khi tạo proxy

Cách tiếp cận có hệ thống:

1. **Lấy chính xác loader truyền vào `newProxyInstance`.** Đừng chỉ nhìn `Thread.currentThread().getContextClassLoader()` nếu code đã truyền một loader khác.
2. **Lấy các `Class<?>` thật trong interface array.** Với mỗi phần tử: `isInterface()`, `getName()`, `getClassLoader()`, `getModule()`.
3. **Thử visibility predicate**: `Class.forName(iface.getName(), false, chosenLoader) == iface` và ghi rõ `ClassNotFoundException` hay cùng tên khác Class.
4. **Xem loader hierarchy**: parent-first, child-first theo package, sibling loader hoặc layer-specific loader.
5. **Kiểm tra API JAR duplicate** trong plugin classpath/fat JAR, application server hoặc hot reload build.
6. **Kiểm tra public method signatures** và inherited interfaces cho DTO/exception/parameter/return type mà proxy loader không nhìn thấy.
7. **Kiểm tra non-public interfaces**: cùng package, module và loader theo JDK rules?
8. **Kiểm tra sealed/hidden interfaces**, duplicate Class objects và return signatures xung đột.
9. **Với JPMS**, xem module membership và package exports/opens; không đánh đồng access issue với type identity.
10. **Sau khi sửa**, test cả tạo proxy, cast vào host interface và gọi methods; chỉ việc tạo thành công chưa bảo đảm cast qua boundary đúng.

Một helper log:

~~~java
static void describe(Class<?> c) {
    System.out.println("name=" + c.getName());
    System.out.println("loader=" + c.getClassLoader());
    System.out.println("module=" + c.getModule());
}
~~~

Đây là **đoạn code minh họa**, không có main. Khi thấy hai types cùng binary name nhưng khác loader, in thêm `(a == b)`; tên string không kết luận được identity.

Có thể bật class loading logging trong OpenJDK/HotSpot:

~~~bash
java -Xlog:class+load=info -cp host-classes ProxyVisibilityDemo shadow-classes
~~~

Log JVM không có stdout cố định và thay đổi theo JDK. Nếu cần phân tích proxy class sinh ra, một số JVM cung cấp diagnostic settings, nhưng **đừng phụ thuộc vào tên `$Proxy0` hoặc package sinh ra** như hợp đồng lâu dài.

## 18. Sai lầm phổ biến

| Sai lầm | Điều đúng |
| --- | --- |
| “Tên interface giống nhau là proxy được” | Loader phải thấy **chính Class runtime** |
| “Tôi có Class<?> rồi nên loader nào cũng tạo proxy được” | Loader truyền vào phải lookup được interface theo tên với identity đúng |
| “Dùng bootstrap loader là auto” | Bootstrap thường không thấy app interface |
| “Child loader khác parent thì chắc chắn không thấy API parent” | Delegation có thể trả đúng API Class |
| “Plugin loader tự define API copy vẫn dùng được với HostApi” | Proxy có thể hoạt động trong plugin nhưng host cast thất bại |
| “Chỉ interface chính cần nhìn thấy” | Public method signature types và inherited interfaces cũng phải visible |
| “Dynamic Proxy có thể implement concrete class” | JDK Dynamic Proxy implements interfaces, không extends arbitrary class |
| “Sealed interface được proxy tự do” | Java 17 yêu cầu non-sealed interfaces |
| “Non-public interface từ mọi package có thể gom một proxy” | Phải tuân thủ same-package/module/loader conditions |
| “Tên/package `$ProxyN` là cố định” | Proxy class names và dynamic modules không được cam kết cố định |
| “`getProxyClass` là cách tạo instance được ưu tiên” | Java 17 API này deprecated; dùng `newProxyInstance` |
| “InvocationHandler tự gọi default methods” | Handler cần dispatch, có thể dùng `InvocationHandler.invokeDefault` |
| “`equals`/`hashCode`/`toString` không qua handler” | Các lời gọi Object methods này cũng được dispatch |
| “Handler checked exception nào cũng ném thẳng ra caller” | Checked exception không nằm trong `throws` có thể bị wrap |
| “TCCL luôn đúng” | TCCL có thể không nhìn thấy host Class hoặc thấy bản sao |
| “Proxy sửa được SPI type duplication” | API/shared contract vẫn cần một runtime Class |
| “Dùng ClassCastException để chẩn đoán lỗi proxy constructor” | Constructor proxy thường IllegalArgumentException; cast mismatch xảy ra sau đó |

## 19. Bài tập và câu hỏi tự kiểm tra

**1. Vì sao JDK kiểm tra `Class.forName(i.getName(), false, loader) == i` thay vì `getName().equals`?**  
Vì cùng binary name có thể được các defining loaders khác nhau định nghĩa thành các runtime types khác nhau.

**2. Một child loader delegate đúng shared API về parent. Nó có thể tạo proxy cho parent API không?**  
Có, nếu mọi interface/signature type nhìn thấy theo đúng identity và các restrictions khác cũng thỏa.

**3. Loader không tìm ra interface Class. Lỗi từ `newProxyInstance` thường là gì?**  
`IllegalArgumentException` cho vi phạm interface visibility, không nhất thiết là `ClassNotFoundException` thoát ra ngoài.

**4. Loader tìm được interface cùng tên nhưng khác Class. Sửa bằng cách truyền bản interface đó vào array có đủ để host dùng proxy không?**  
Không; proxy sẽ implements interface của plugin, host có thể không cast được. Cần chia sẻ đúng contract Class.

**5. Nếu `Greeter.class` visible nhưng method có tham số `Request` từ loader khác thì sao?**  
Proxy vẫn có thể không được tạo vì public method signature types cũng phải visible.

**6. Hai non-public interfaces thuộc hai packages khác nhau có thể dùng chung một proxy không?**  
Không theo constraints Java 17 đối với non-public proxy interfaces.

**7. Vì sao sealed interface không hợp lệ làm proxy interface trong Java 17?**  
Vì dynamic proxy class không thuộc permitted implementations tĩnh và `Proxy` API yêu cầu interface không sealed.

**8. `InvocationHandler.invoke` nhận args thế nào khi method không có tham số?**  
`args` có thể là `null`.

**9. Handler trả null cho method trả `int` thì sao?**  
Lời gọi proxy có thể ném `NullPointerException` khi unbox.

**10. Handler ném checked exception không có trong `throws` thì sao?**  
Có thể bị bọc trong `UndeclaredThrowableException`.

**11. Có thể dựa vào tên `$Proxy0` để xác định đúng module không?**  
Không. Tên/package/module của proxy class không phải giao diện ổn định để logic nghiệp vụ dựa vào.

**12. Cần test những gì sau khi sửa loader?**  
Tạo proxy thành công, cast sang host API, xử lý methods, kết quả/exception, và tương thích các types trong signatures.

## 20. Tài liệu chính thức

- **Java SE 17 — `java.lang.reflect.Proxy` API**: restrictions, interface visibility, JPMS dynamic modules, duplicated method signatures, `newProxyInstance`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- **Java SE 17 — `InvocationHandler` API**: `invoke`, object/primitive returns, checked exceptions, `invokeDefault`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html
- **Java SE 17 — `ClassLoader` API**: `loadClass`, parent delegation và defining loaders: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — `Class` API**: `forName`, `getClassLoader`, `getModule`, `isAssignableFrom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 — `UndeclaredThrowableException`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html
- **JVM Specification 17, §5.3 — Creation and Loading**: runtime class identity: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JLS 17 §12.2 — Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
