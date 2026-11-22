# 10.11. Package, module động của lớp proxy và cách nhận diện proxy qua API

> **Ngữ cảnh:** Bài Knowledge thuộc **10. Proxy động** của module **Java Advance – dynamic-runtime**. Trong Java 21, `java.lang.reflect.Proxy` sinh **một class tại runtime** để triển khai các interface, nhưng **package và module của class được sinh không tùy ý cố định**. Chúng tuân theo khả năng truy cập của những interface, có thể nằm trong **dynamic module** và cần được kiểm tra bằng các API chính thức. Bài tập trung vào quy tắc lựa chọn package/module, các giới hạn JPMS, và cách nhận diện proxy thật mà không dựa vào tên `$Proxy...`.

## 1. Mục tiêu và kiến thức nền

Sau bài này, bạn phải giải thích và thực hành được:

1. Phân biệt **proxy class**, **proxy instance**, **proxy interface** và **InvocationHandler**.
2. Áp dụng đúng ma trận Java 21 về **interface public / non-public** và **package exported/open / non-exported-and-non-open** để suy ra vị trí và khả năng truy cập của proxy class.
3. Giải thích **dynamic module** là một named module sinh ở runtime, trường hợp nào proxy public được đặt trong package bị đóng của module đó, và vì sao không thể tự gọi constructor của proxy class đó từ bên ngoài.
4. Đọc `Class.getPackageName()`, `Class.getModule()`, `Class.getClassLoader()`, `Modifier.isPublic` cùng `Module.isExported/isOpen/canRead` để chẩn đoán.
5. Dùng `Proxy.isProxyClass(Class<?>)` và `Proxy.getInvocationHandler(Object)` để nhận diện proxy theo API; biết vì sao so tên class hoặc `Proxy.class.isAssignableFrom` không tương đương.
6. Đọc lỗi `IllegalArgumentException` khi interface sealed/không phải interface, bị trùng, không visible theo loader, hoặc các interface non-public không chung package/module.
7. Viết và chạy các ví dụ Java 21 thuần JDK cho proxy public, interface package-private, public interface trong named module không export, và các trường hợp tạo proxy không hợp lệ.

**Yêu cầu trước:** interface, package và access modifiers, `ClassLoader`, Reflection (`Class<?>`), khái niệm JPMS (`module-info.java`, `exports`, `opens`), terminal `javac`/`java`. Không dùng CGLIB, Byte Buddy, Spring AOP hay thư viện khác: những công cụ đó có thể sinh subclass proxy với quy tắc khác.

## 2. Lớp proxy động là gì?

Ví dụ cơ bản:

```java
// Đoạn minh họa, chạy bên trong class có import java.lang.reflect.*;
interface Greeting {
    String say(String who);
}

InvocationHandler handler = (proxy, method, args) -> "Hello " + args[0];
Greeting greeting = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

Ở đây `Proxy.newProxyInstance` tạo **một object** thuộc class do JVM/JDK sinh khi chạy. Class ấy triển khai các interface được yêu cầu; lời gọi từ interface đến object được dispatch qua `InvocationHandler.invoke`. `handler` không phải proxy class, và `Greeting.class` không phải proxy class.

Các thuộc tính được Javadoc `Proxy` bảo đảm:

- Class được sinh **final**, **không abstract**, và có **direct superclass** là `java.lang.reflect.Proxy`.
- Nó implements **đúng danh sách các interface được yêu cầu, theo đúng thứ tự**. `proxyClass.getInterfaces()` trả danh sách theo thứ tự này.
- Tên **đơn giản** và tên package/module của proxy class không được coi là một contract cố định; không dựa vào quy tắc ghép `$Proxy0` hoặc `jdk.proxy1`.
- Instance được sinh là instance của mỗi interface tương ứng, nên `proxy instanceof Interface` và cast sang interface hợp lệ.
- Mỗi proxy instance gắn với một `InvocationHandler`, được truy xuất bằng `Proxy.getInvocationHandler`.
- Method interface (và một số method của `Object` như `equals`, `hashCode`, `toString`) được chuyển tới handler.
- `Proxy.isProxyClass` là API đáng tin để xác định **class đã được sinh bởi proxy mechanism**, không chỉ là class có tên/cha trông tương tự.

`Proxy` là **interface-based proxy**: không tạo subclass tùy ý của một concrete class. `Proxy.newProxyInstance` không chấp nhận một `Class<?>` là concrete class thay cho interface, và trong Java 21 không tạo proxy trực tiếp cho sealed interface.

### 2.1. Phân biệt identity và ngoại hình

```text
Interface A + Interface B + một ClassLoader
                |
                v
       Proxy.newProxyInstance(...)
                |
                +--> generated proxy Class<?>
                |     superclass = Proxy
                |     implements = [A, B] theo đúng thứ tự
                |     package/module phụ thuộc quyền của interfaces
                |
                +--> proxy instance
                      |
                      +--> InvocationHandler

Class<?> name chứa "$Proxy"       : KHÔNG đủ để nhận diện
extends java.lang.reflect.Proxy : KHÔNG đủ để nhận diện
Proxy.isProxyClass(clazz)       : API nhận diện chính thức
```

Người dùng có thể tự viết class extends `Proxy` và gọi constructor protected của nó; class đó **không nhất thiết** là một *generated proxy class*. Đây là lý do dùng `isProxyClass` chứ không chỉ kiểm tra kế thừa.

## 3. Các khái niệm JPMS cần phân biệt

**Package** là namespace chứa type. **Module** là ranh giới đóng gói của Java Platform Module System (JPMS). **Class loader** là ngữ cảnh nạp/định nghĩa class. Ba thứ liên quan nhưng **không đồng nghĩa**.

### 3.1. `exports` khác `opens`

- `exports p;`: cho phép module khác truy cập **public types và public members** của package `p` theo kiểm tra truy cập Java/JVM thông thường.
- `opens p;`: cho phép **deep reflection** đến các member có thể truy cập khi code có quyền thích hợp, nhưng không biến mọi type thành public để compile truy cập bình thường.
- `exports p to x;` và `opens p to x;` là **qualified exports/opens**: chỉ cấp quyền cho module được liệt kê.
- Một package **không exported và không open** từ góc nhìn unqualified là package bị encapsulate; class public trong đó vẫn có thể không được truy cập bởi một module khác.
- `Module.isExported("p")`/`isOpen("p")` kiểm tra **unconditional** status; `isExported("p", targetModule)`/`isOpen("p", targetModule)` kiểm tra quyền theo **đích cụ thể**. Đừng nhầm kết quả của hai overload.

Trong quy tắc của `Proxy`, Javadoc gọi “non-exported package” là package **không export tới tất cả các module** (kể cả chỉ export qualified); “non-open package” cũng được hiểu tương tự với opens. Vì vậy package chỉ `exports ... to x` vẫn **không exported unconditionally**.

### 3.2. Named, unnamed và dynamic modules

- Class trên classpath thông thường thuộc **unnamed module** của class loader tương ứng; package trong unnamed module nhìn chung được exported/open theo quy tắc JPMS của unnamed module.
- Class trong một module có `module-info.java` thuộc **named module**. Module đó có thể không `exports` package, dù interface bên trong là public.
- **Dynamic module** ở đây là **named module được JDK tạo khi sinh proxy**, không phải “unnamed module” hay “automatic module”. Nó có package/module name không xác định theo API contract và có thể bị encapsulate hoàn toàn.

Một class có tên hợp lệ và loader thấy được **không đồng nghĩa** package/module của nó được export/open cho code hiện tại. Đó là lý do nhìn `Modifier.isPublic` thôi chưa đủ để kết luận có thể gọi constructor bằng Reflection từ module bên ngoài.

## 4. Ma trận package/module của generated proxy class trong Java 21

Javadoc `Proxy` chia theo **tính public của các interface** và **tình trạng exported/open của package chứa interface**.

| Tập interface được proxy | Các package interface đều exported hoặc open? | Generated proxy class ở đâu? | Mức truy cập |
| --- | --- | --- | --- |
| **Tất cả public** | **Có** | Package **exported unconditionally nhưng không open**, tên package/module **không được quy định cụ thể** | Proxy class **public** |
| **Ít nhất một non-public** | **Có** | **Cùng package và cùng module** với các non-public interfaces | Proxy class **non-public** |
| **Tất cả public** | **Không**: ít nhất một interface trong package non-exported và non-open | Package **non-exported, non-open** của một **dynamic module** | Proxy class **public**, nhưng package bị encapsulate |
| **Ít nhất một non-public** | **Không** | **Cùng package và cùng module** với các non-public interfaces | Proxy class **non-public** |

**Giới hạn bắt buộc:** nếu có nhiều interface **non-public**, chúng **phải cùng package và module** (và thỏa yêu cầu class loader của `Proxy.newProxyInstance`). Nếu không, không thể tạo class proxy tương ứng: thường nhận `IllegalArgumentException`.

### 4.1. Hai điều không được đọc nhầm từ bảng

1. **Proxy class public không có nghĩa mọi module đều truy cập được nó.** Trong nhánh dynamic module non-exported/non-open, `Modifier.isPublic(proxyClass.getModifiers())` có thể là `true`, nhưng code module khác vẫn không được truy cập class qua Java access checks và không thể dùng `Constructor.newInstance` từ bên ngoài.
2. **Interface public không có nghĩa proxy class nằm cạnh interface.** Khi interface nằm trong named module mà package không export/open, proxy class public được sinh trong **dynamic module riêng**, còn non-public interface đẩy proxy class về **chính package/module của interface non-public**.

Quy tắc nói rõ **khả năng truy cập**, không cam kết số thứ tự, simple name hoặc tên module/package cụ thể. Một phiên bản JDK có thể đặt class public proxy trong module tên kiểu `jdk.proxy1`; tên ấy không phải API ổn định để viết business logic.

### 4.2. Ví dụ phân loại nhanh

- Interface `public` trong module/unnamed package được exported hoặc open: **hàng 1**.
- Interface top-level `package-private` trong một package: **hàng 2** hoặc **hàng 4** tùy exports/opens, nhưng proxy vẫn **non-public trong cùng package/module**.
- Interface `public` của module `inventory.core` nhưng package `internal.spi` không được exports/opens: **hàng 3**, proxy public trong dynamic module đóng.
- Nhiều interface non-public từ **hai package khác nhau**: **không hợp lệ**, bất kể mỗi interface có thể được nhìn thấy qua Reflection.

Hãy nhớ: **least accessible proxy interface governs proxy accessibility**. Điều này đặc biệt quan trọng khi trộn public và non-public interfaces.

## 5. Lab 1 — public proxy và nhận diện bằng API

Tạo file **`PublicProxyLab.java`**:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

public class PublicProxyLab {
    public interface Hello {
        String say(String value);
    }

    static final class ManualProxy extends Proxy implements Hello {
        private static final long serialVersionUID = 1L;

        ManualProxy(InvocationHandler h) {
            super(h);
        }

        public String say(String value) {
            return value;
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.getName().equals("say")) {
                return "Hi " + arguments[0];
            }
            if (method.getName().equals("toString")) {
                return "public-proxy";
            }
            throw new UnsupportedOperationException(method.getName());
        };

        Hello proxy = (Hello) Proxy.newProxyInstance(
                Hello.class.getClassLoader(),
                new Class<?>[] { Hello.class },
                handler);

        Class<?> pc = proxy.getClass();
        Module module = pc.getModule();
        String pkg = pc.getPackageName();

        System.out.println("result=" + proxy.say("Java"));
        System.out.println("isProxy=" + Proxy.isProxyClass(pc));
        System.out.println("sameHandler=" + (Proxy.getInvocationHandler(proxy) == handler));
        System.out.println("implementsHello=" + Hello.class.isAssignableFrom(pc));
        System.out.println("directSuperclass=" + (pc.getSuperclass() == Proxy.class));
        System.out.println("publicFinal=" + (Modifier.isPublic(pc.getModifiers())
                && Modifier.isFinal(pc.getModifiers())));
        System.out.println("exportedUnconditionally=" + module.isExported(pkg));
        System.out.println("openUnconditionally=" + module.isOpen(pkg));

        System.out.println("manualIsProxy=" + Proxy.isProxyClass(ManualProxy.class));
        System.out.println("manualSuperclass=" +
                (ManualProxy.class.getSuperclass() == Proxy.class));

        try {
            Proxy.getInvocationHandler(new ManualProxy(handler));
            System.out.println("manualHandler=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("manualHandler=IllegalArgumentException");
        }
    }
}
```

Biên dịch/chạy từ thư mục chứa file bằng Java 21:

```sh
javac --release 21 -Xlint:all PublicProxyLab.java
java PublicProxyLab
```

**Stdout:**

```text
result=Hi Java
isProxy=true
sameHandler=true
implementsHello=true
directSuperclass=true
publicFinal=true
exportedUnconditionally=true
openUnconditionally=false
manualIsProxy=false
manualSuperclass=true
manualHandler=IllegalArgumentException
```

### 5.1. Giải thích output

- `Hello` là **public member interface**. JDK có thể sinh một class proxy **public final** ở một package **exported unconditionally nhưng non-open**; vì thế hai giá trị exported/open như trên.
- `Proxy.isProxyClass(pc)` là `true`, và `Proxy.getInvocationHandler(proxy) == handler` là `true`: handler thu được là cùng object đã đăng ký.
- `Hello.class.isAssignableFrom(pc)` xác nhận class được sinh implement interface, còn direct superclass là `Proxy.class`.
- `ManualProxy` cũng có direct superclass `Proxy.class` nhưng do ta **viết tay** chứ không được sinh qua proxy factory. `Proxy.isProxyClass(ManualProxy.class)` trả `false`; gọi `Proxy.getInvocationHandler` với instance này bị từ chối bằng `IllegalArgumentException`.
- Code **không in `pc.getName()` hoặc `module.getName()`** vì các tên đó không được dùng như kết quả cố định giữa JDKs.

**Phạm vi ví dụ:** handler chỉ xử lý `say` và `toString`; nếu ứng dụng thật gọi `equals`/`hashCode`, phải triển khai chính sách phù hợp, tránh trả về sai kiểu. Trong một handler chung, cũng phải xử lý exception và lời gọi default methods có chủ đích.

## 6. Các API dùng để nhận diện và quan sát proxy

| API | Ý nghĩa đúng | Giới hạn |
| --- | --- | --- |
| `Proxy.isProxyClass(clazz)` | `true` nếu `clazz` là generated proxy class hợp lệ | Không chỉ dựa vào tên hay `extends Proxy`; `clazz=null` ném `NullPointerException`. |
| `Proxy.getInvocationHandler(proxy)` | Trả handler gắn với **proxy instance** | Object không phải proxy: `IllegalArgumentException`; `null`: `NullPointerException`. |
| `obj.getClass()` | Runtime class cụ thể của object | Không tự chứng minh đây là proxy thật. |
| `clazz.getSuperclass()` | Generated proxy có direct superclass `Proxy.class` | Class tự extends `Proxy` cũng có thể thỏa; cần `isProxyClass`. |
| `clazz.getInterfaces()` | Danh sách interface proxy theo **thứ tự yêu cầu** | Không thể thay thế cho kiểm tra generated proxy identity. |
| `clazz.getPackageName()` | Tên package runtime | Không được hard-code tên package do JDK sinh. |
| `clazz.getModule()` | `Module` thực tế chứa class | Named module không tự chứng minh package đã exported/open. |
| `clazz.getClassLoader()` | Loader của class | Tên class tương tự không đủ suy ra class identity khi loader khác. |
| `Modifier.isPublic(clazz.getModifiers())` | Có flag `public` trên class | Một class public trong non-exported package vẫn không dễ truy cập ngoài module. |
| `module.isExported(pkg)` | Package exported **tới mọi module** | Khác `isExported(pkg, target)` khi có qualified export. |
| `module.isOpen(pkg)` | Package open **tới mọi module** | Khác `isOpen(pkg, target)`. |
| `module.canRead(otherModule)` | Module readability | Có read edge chưa đủ có quyền truy cập member trong package không exported. |

**Cách nhận diện một object proxy theo API:**

```java
// Helper minh họa, đặt trong class có import java.lang.reflect.Proxy.
static boolean isGeneratedProxy(Object value) {
    return value != null && Proxy.isProxyClass(value.getClass());
}
```

Nếu cần lấy handler, kiểm tra `isGeneratedProxy(value)` trước, hoặc để `Proxy.getInvocationHandler` ném lỗi phù hợp. `Proxy.isProxyClass` là phép kiểm tra **class được sinh bằng proxy mechanism**, **không** phải một bằng chứng an toàn rằng handler đáng tin, object được cấp quyền hay input hợp lệ.

## 7. Lab 2 — interface không public và proxy cùng package/module

Tạo đúng đường dẫn file **`src/edu/packageprivate/PackagePrivateProxyLab.java`**:

```java
package edu.packageprivate;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

interface HiddenTask {
    String run();
}

public class PackagePrivateProxyLab {
    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, values) -> "done";
        HiddenTask task = (HiddenTask) Proxy.newProxyInstance(
                HiddenTask.class.getClassLoader(),
                new Class<?>[] { HiddenTask.class },
                handler);

        Class<?> pc = task.getClass();
        System.out.println("result=" + task.run());
        System.out.println("isProxy=" + Proxy.isProxyClass(pc));
        System.out.println("public=" + Modifier.isPublic(pc.getModifiers()));
        System.out.println("samePackage=" +
                pc.getPackageName().equals(HiddenTask.class.getPackageName()));
        System.out.println("sameModule=" + (pc.getModule() == HiddenTask.class.getModule()));
        System.out.println("sameLoader=" +
                (pc.getClassLoader() == HiddenTask.class.getClassLoader()));
        System.out.println("moduleNamed=" + pc.getModule().isNamed());
    }
}
```

Trong thư mục dự án có `src`:

```sh
javac --release 21 -Xlint:all -d out src/edu/packageprivate/PackagePrivateProxyLab.java
java -cp out edu.packageprivate.PackagePrivateProxyLab
```

**Stdout trong cách chạy trên classpath này:**

```text
result=done
isProxy=true
public=false
samePackage=true
sameModule=true
sameLoader=true
moduleNamed=false
```

### 7.1. Lý do package/module khác Lab 1

`HiddenTask` là top-level **package-private interface** (không có `public`). Theo specification, proxy class phải **non-public và ở cùng package/module** của interface này. Mọi non-public proxy interfaces (nếu nhiều) phải nằm trong **cùng package và module**, không chỉ trùng simple name.

`moduleNamed=false` trong lab vì các class đang chạy từ **classpath/unnamed module**. Nếu chuyển bài vào một **named module** thì kết quả này có thể thay đổi, nhưng yêu cầu **sameModule=true** đối với non-public interface vẫn giữ nguyên. Đừng nhầm “non-public proxy class” với “public proxy class trong non-exported dynamic module”: hai trường hợp khác nhau.

**Lưu ý quyền truy cập:** một class bên ngoài package `edu.packageprivate` không được tự ý cast sang `HiddenTask` từ Java source; ngay cả khi có `Class<?>` của proxy, public API Reflection vẫn phải tuân theo quyền truy cập vào class/member/package/module thực tế. Sử dụng factory/contract đúng module thay vì tìm cách phá access.

## 8. Dynamic modules xuất hiện khi nào?

Nếu **tất cả proxy interfaces đều public**, nhưng **ít nhất một interface** nằm trong package **không exported và không open**, proxy class được sinh **public trong package non-exported, non-open của một dynamic module**.

Ví dụ:

```java
// module-info.java của một module có interface public trong package ẩn.
module demo.hidden {
    // Cố ý KHÔNG exports/opens hidden.api.
}
```

Interface này có `public` nhưng module bên ngoài không thể dùng tên type đó trong Java source một cách bình thường nếu package không được exported. Mặc dù vậy, code có thể có `Class<?>` được lấy qua class loading/Reflection và yêu cầu JDK tạo proxy theo điều kiện hợp lệ.

### 8.1. Dynamic module khác gì module khai báo của interface?

- `proxyClass.getModule()` là một module do JDK tạo ở runtime, **khác** module chứa interface non-exported.
- Module của proxy có thể **read** module của các superinterfaces và module của các reference types xuất hiện trong các public method signatures.
- Khi một package chứa interface/loại tham chiếu cần thiết không được exported, JDK có thể cập nhật module chứa loại đó để **export package theo đích chỉ đến dynamic proxy module**. Điều này **không biến package thành exported unconditionally**, cũng không biến nó thành open đối với mọi code.
- Proxy package trong dynamic module là **non-exported/non-open**, nên caller từ module khác không thể truy cập generated proxy class qua reflection như một public class thông thường.
- Proxy class **vẫn có modifier `public`**, vì Java visibility flag và JPMS export/open là **hai tầng quyền khác nhau**.

**Hệ quả quan trọng của Javadoc Java 21:** gọi `Constructor.newInstance(...)` trên proxy class nằm trong dynamic module từ code ngoài module đó ném `IllegalAccessException`. Hãy dùng **`Proxy.newProxyInstance(...)`**, không cố tự instantiate constructor của generated class.

## 9. Lab 3 — một public interface nằm trong named module không export

Lab này cần **ba file**: một `module-info.java`, một interface public ở package ẩn, và chương trình classpath để quan sát proxy. Đặt đúng cấu trúc:

```text
project/
├── srcmods/
│   └── demo.hidden/
│       ├── module-info.java
│       └── hidden/api/SecretService.java
└── DynamicModuleProxyLab.java
```

**`srcmods/demo.hidden/module-info.java`:**

```java
module demo.hidden {
    // Không exports hidden.api và cũng không opens hidden.api.
}
```

**`srcmods/demo.hidden/hidden/api/SecretService.java`:**

```java
package hidden.api;

public interface SecretService {
    String ping();
}
```

**`DynamicModuleProxyLab.java`:**

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

public class DynamicModuleProxyLab {
    public static void main(String[] args) throws Exception {
        Class<?> api = Class.forName("hidden.api.SecretService");
        Module apiModule = api.getModule();
        InvocationHandler handler = (proxy, method, values) -> "handled";

        Object proxy = Proxy.newProxyInstance(
                api.getClassLoader(), new Class<?>[] { api }, handler);
        Class<?> pc = proxy.getClass();
        Module pm = pc.getModule();
        String proxyPkg = pc.getPackageName();
        String apiPkg = api.getPackageName();

        System.out.println("apiNamed=" + apiModule.isNamed());
        System.out.println("apiExportedToAll=" + apiModule.isExported(apiPkg));
        System.out.println("apiOpenToAll=" + apiModule.isOpen(apiPkg));
        System.out.println("isProxy=" + Proxy.isProxyClass(pc));
        System.out.println("proxyPublic=" + Modifier.isPublic(pc.getModifiers()));
        System.out.println("proxyNamed=" + pm.isNamed());
        System.out.println("differentModule=" + (pm != apiModule));
        System.out.println("proxyExportedToAll=" + pm.isExported(proxyPkg));
        System.out.println("proxyOpenToAll=" + pm.isOpen(proxyPkg));
        System.out.println("canReadApi=" + pm.canRead(apiModule));
        System.out.println("apiExportedToProxy=" + apiModule.isExported(apiPkg, pm));
        System.out.println("sameHandler=" + (Proxy.getInvocationHandler(proxy) == handler));

        Constructor<?> ctor = pc.getConstructor(InvocationHandler.class);
        try {
            ctor.newInstance(handler);
            System.out.println("ctorAccess=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("ctorAccess=IllegalAccessException");
        }
    }
}
```

### 9.1. Biên dịch và chạy với module path

Chạy từ thư mục `project`:

```sh
javac --release 21 -Xlint:all -d mods/demo.hidden srcmods/demo.hidden/module-info.java srcmods/demo.hidden/hidden/api/SecretService.java
javac --release 21 -Xlint:all -d out DynamicModuleProxyLab.java
java --module-path mods --add-modules demo.hidden -cp out DynamicModuleProxyLab
```

Lệnh `--add-modules demo.hidden` yêu cầu JVM đưa named module **demo.hidden** vào module graph khi khởi chạy. Nếu không resolve module, `Class.forName` sẽ không có sẵn class `hidden.api.SecretService` theo cách chạy này. Chương trình nằm ở **unnamed module** trên classpath; nó **không import interface ẩn** vào source mà dùng `Class.forName` lấy `Class<?>`.

**Stdout của cấu hình lab:**

```text
apiNamed=true
apiExportedToAll=false
apiOpenToAll=false
isProxy=true
proxyPublic=true
proxyNamed=true
differentModule=true
proxyExportedToAll=false
proxyOpenToAll=false
canReadApi=true
apiExportedToProxy=true
sameHandler=true
ctorAccess=IllegalAccessException
```

### 9.2. Diễn giải quan trọng

1. **`apiNamed=true`**: interface thuộc named module `demo.hidden` được khai báo bởi `module-info.java`.
2. **`apiExportedToAll=false`, `apiOpenToAll=false`**: package `hidden.api` không được public export hoặc open.
3. **`isProxy=true`**: object thực sự được sinh bằng `Proxy` factory, không phải class tự viết.
4. **`proxyPublic=true`**: access flag trên generated class là `public`.
5. **`proxyNamed=true` và `differentModule=true`**: generated class nằm trong một **dynamic named module khác** với module chứa interface.
6. **`proxyExportedToAll=false` / `proxyOpenToAll=false`**: package của generated class được encapsulate, dù class có flag public.
7. **`canReadApi=true`**: dynamic proxy module có read edge đến module chứa interface.
8. **`apiExportedToProxy=true`**: JDK mở **đường export có đích** từ package chứa interface tới dynamic module, giúp generated class triển khai interface. Package vẫn **không exported tới mọi module**.
9. **`sameHandler=true`**: handler vẫn được truy xuất qua `Proxy.getInvocationHandler` từ bên ngoài dynamic module.
10. **`ctorAccess=IllegalAccessException`**: dù lấy được `Constructor<?>` public, `Constructor.newInstance` từ caller bên ngoài không có quyền vì proxy package không exported. Cách tạo instance đúng là `Proxy.newProxyInstance`.

Kết quả của lab cố tình chỉ in **boolean properties**, không in generated module name hoặc proxy package name. JDK có thể dùng tên nội bộ khác; logic ứng dụng không được dựa vào chúng.

### 9.3. Không đồng nhất exported với open

`apiModule.isExported(apiPkg,pm) == true` **không có nghĩa** `apiModule.isOpen(apiPkg) == true` hoặc `pm.isOpen(proxyPkg) == true`. **Exports** phục vụ Java access checks cho public types; **opens** phục vụ deep reflection. Dynamic module được thiết kế để hỗ trợ proxy hoạt động mà vẫn giữ encapsulation đối với các module không được cấp quyền.

## 10. Nhận diện và lấy handler đúng cách

### 10.1. Một quy trình kiểm tra gọn

Khi có một object `candidate`:

```text
candidate == null ?
   |
   +--> yes: không phải proxy instance
   |
   +--> no:
          |
          +--> Class<?> clazz = candidate.getClass()
          |
          +--> Proxy.isProxyClass(clazz) ?
                   |
                   +--> false: không phải generated proxy
                   |
                   +--> true:
                          |
                          +--> Proxy.getInvocationHandler(candidate)
                          |
                          +--> clazz.getInterfaces()
                          +--> clazz.getModule()
                          +--> clazz.getPackageName()
```

Không gọi `getInvocationHandler` với object không phải proxy để tránh `IllegalArgumentException`, hoặc bắt lỗi theo đúng trách nhiệm API của bạn. Đừng dùng `candidate.toString()` để log nhận diện một cách vô điều kiện: nếu candidate là proxy, `toString()` **có thể gọi handler** và sinh side effects.

### 10.2. Handler không chứng minh trust

`Proxy.isProxyClass` phục vụ **nhận diện generated proxy class**. Nó không chứng minh invocation handler đáng tin cậy, không đảm bảo phương thức interface tuân thủ logic nghiệp vụ, cũng không xác thực quyền của người gọi. `getInvocationHandler` cho bạn thấy **đối tượng handler** được gắn với instance, nhưng việc inspect handler class có thể có giới hạn quyền/package/module.

Nếu hệ thống plugin dùng dynamic proxy để bọc service, hãy kiểm tra **contract interface** và **nguồn tạo proxy** theo thiết kế của hệ thống, không cho phép bất kỳ proxy instance nào trở thành capability được tin cậy chỉ vì `isProxyClass` trả true.

### 10.3. Tên và thứ tự interfaces

`getInterfaces()` của generated class giữ đúng thứ tự giao diện đưa vào factory. Đối với các interface có method cùng tên và cùng parameter signature, **thứ tự interfaces** còn có thể ảnh hưởng đến `Method` được handler nhận. Vì thế không gộp tùy tiện danh sách interfaces thành một `Set` rồi làm mất thứ tự trước khi tạo proxy.

`Proxy.newProxyInstance(loader, [A.class,B.class], h)` và `Proxy.newProxyInstance(loader, [B.class,A.class], h)` có thể tạo **hai proxy classes khác nhau** theo specification. Không dựa vào tên class để cache; hãy hiểu danh sách **có thứ tự** cùng loader/context.

## 11. Những ràng buộc đầu vào của `Proxy.newProxyInstance`

Javadoc Java 21 quy định một số điều kiện cơ bản:

| Điều kiện | Hợp lệ? | Vấn đề thường gặp |
| --- | --- | --- |
| Mỗi phần tử `Class<?>` là **interface**, không phải class/primitive | Bắt buộc | Truyền `String.class` hoặc `int.class`. |
| Interface **không hidden và không sealed** | Bắt buộc | Sealed interface không thể được triển khai bởi generated proxy class không nằm trong danh sách `permits`. |
| Không có hai phần tử interface là **cùng Class object** | Bắt buộc | Đưa `A.class` hai lần. |
| Interface visible theo class loader yêu cầu | Bắt buộc | `Class.forName(i.getName(),false,loader) != i`. |
| Các kiểu trong **public method signatures** visible theo loader | Bắt buộc | Loader thấy interface nhưng không thấy parameter/return type của method. |
| Mọi non-public interfaces phải ở **cùng package/module** và được define bởi loader thích hợp | Bắt buộc | Trộn hai package-private interfaces ở hai package khác nhau. |
| Với method cùng signature của nhiều interfaces, return types tương thích | Bắt buộc | Hai primitive return types khác nhau không thể hợp nhất. |
| Không vượt giới hạn classfile/JVM | Bắt buộc | Quá nhiều interfaces hoặc metadata. |

Vi phạm các giới hạn này dẫn đến `IllegalArgumentException` theo hợp đồng của `newProxyInstance` (bên cạnh các lỗi khác như `NullPointerException` cho tham số null). Không sửa bằng cách đặt tên generated class, vì factory đã chọn package/module theo quy tắc.

**Ranh giới class loader:** phép kiểm tra `Class.forName(i.getName(), false, loader) == i` nhấn mạnh **class identity**. Hai interface có cùng binary name nhưng do hai loaders định nghĩa có thể là hai `Class<?>` khác nhau. Việc nhìn tên trong logs không đủ đảm bảo proxy factory có thể dùng interface đó.

## 12. Lab 4 — thứ tự interfaces và các trường hợp không tạo được proxy

Lab này dùng một class chính và hai interface package-private nằm ở **hai package khác nhau**, để tự thấy lỗi về phạm vi package/module.

Tạo đúng ba file:

```text
project/
├── InvalidProxyLab.java
└── src/
    ├── edu/one/HiddenOne.java
    └── edu/two/HiddenTwo.java
```

**`src/edu/one/HiddenOne.java`:**

```java
package edu.one;
interface HiddenOne { void run(); }
```

**`src/edu/two/HiddenTwo.java`:**

```java
package edu.two;
interface HiddenTwo { void run(); }
```

**`InvalidProxyLab.java`:**

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class InvalidProxyLab {
    public sealed interface SealedTask permits ApprovedTask {
        void run();
    }

    public static final class ApprovedTask implements SealedTask {
        public void run() {}
    }

    public interface First { void f(); }
    public interface Second { void g(); }

    public static void main(String[] args) throws ClassNotFoundException {
        InvocationHandler handler = (proxy, method, values) -> null;
        ClassLoader loader = InvalidProxyLab.class.getClassLoader();

        Object first = Proxy.newProxyInstance(
                loader, new Class<?>[]{First.class, Second.class}, handler);
        Object reverse = Proxy.newProxyInstance(
                loader, new Class<?>[]{Second.class, First.class}, handler);
        System.out.println("orderChangesProxyClass=" +
                (first.getClass() != reverse.getClass()));
        System.out.println("firstInterface=" +
                first.getClass().getInterfaces()[0].getSimpleName());

        try {
            Proxy.newProxyInstance(loader, new Class<?>[]{SealedTask.class}, handler);
            System.out.println("sealed=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("sealed=IllegalArgumentException");
        }

        try {
            Proxy.newProxyInstance(loader, new Class<?>[]{String.class}, handler);
            System.out.println("class=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("class=IllegalArgumentException");
        }

        Class<?> one = Class.forName("edu.one.HiddenOne");
        Class<?> two = Class.forName("edu.two.HiddenTwo");
        try {
            Proxy.newProxyInstance(loader, new Class<?>[]{one, two}, handler);
            System.out.println("nonPublicMixed=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nonPublicMixed=IllegalArgumentException");
        }

        try {
            Proxy.newProxyInstance(loader, new Class<?>[]{First.class, First.class}, handler);
            System.out.println("duplicate=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("duplicate=IllegalArgumentException");
        }
    }
}
```

**Lệnh biên dịch và chạy:**

```sh
javac --release 21 -Xlint:all -d out InvalidProxyLab.java src/edu/one/HiddenOne.java src/edu/two/HiddenTwo.java
java -cp out InvalidProxyLab
```

**Stdout:**

```text
orderChangesProxyClass=true
firstInterface=First
sealed=IllegalArgumentException
class=IllegalArgumentException
nonPublicMixed=IllegalArgumentException
duplicate=IllegalArgumentException
```

**Lý giải:**

- Interface order là một phần input của proxy class creation, không phải chỉ tập hợp tên.
- `SealedTask` bị từ chối vì JDK proxy factory không nhận sealed interface.
- `String.class` là concrete class chứ không phải interface.
- `edu.one.HiddenOne` và `edu.two.HiddenTwo` đều là non-public interfaces nhưng khác package; không thể đặt một generated class non-public cùng lúc trong hai package.
- Cùng `First.class` hai lần vi phạm yêu cầu không duplicate `Class<?>` trong mảng interfaces.

Các trường hợp khác cần kiểm tra riêng khi làm plugin thực: hidden interfaces, return types không tương thích khi trùng signature, class loader không nhìn thấy interface types, và module access tương ứng.

## 13. Vì sao không nên tự tạo object qua generated constructor?

`Proxy.getProxyClass(loader, interfaces...)` vẫn tồn tại nhưng **deprecated** từ Java 9. Một lý do lớn là proxy class sinh trong **named/dynamic module** có thể bị encapsulate: lấy được `Class<?>` không bảo đảm bạn được phép gọi constructor của nó.

**Không khuyến nghị:**

```java
// Đoạn minh họa anti-pattern: phản chiếu constructor của generated proxy.
Class<?> proxyClass = proxy.getClass();
var constructor = proxyClass.getConstructor(java.lang.reflect.InvocationHandler.class);
Object another = constructor.newInstance(handler); // Có thể IllegalAccessException!
```

**Khuyến nghị:**

```java
// Đặt bên trong class có import java.lang.reflect.Proxy.
// loader và apiInterface đều phải chỉ đúng runtime Class<?> identity.
Object another = Proxy.newProxyInstance(
        apiInterface.getClassLoader(),
        new Class<?>[]{apiInterface},
        handler);
```

Đối với dynamic module non-exported/non-open, `Constructor.newInstance` bị từ chối từ caller ngoài module. Việc thử `setAccessible(true)` không phải giải pháp chung: JPMS có thể chặn deep reflection với `InaccessibleObjectException` vì package không open cho caller. Không thêm `--add-opens` hoặc phá module boundaries chỉ để tránh dùng factory đã được thiết kế cho việc này.

**Góc nhìn thiết kế:** `Proxy.newProxyInstance` chịu trách nhiệm sinh class và trả instance phù hợp. Code client nên thao tác qua **public interface contract**, thay vì phụ thuộc cấu trúc package/module của generated class.

## 14. InvocationHandler và các method do proxy dispatch

Proxy class là phần *hình dạng runtime*, handler là phần *hành vi*. Một interface method invocation vào proxy được mã hóa thành lời gọi `InvocationHandler.invoke(proxy, method, args)`.

- `Method` được nhận là mô tả method đã gọi theo quy tắc dispatch của proxy; với method trùng giữa interfaces, **interface order** ảnh hưởng `Method.getDeclaringClass()`.
- Với `equals`, `hashCode` và `toString` được proxy xử lý từ `Object`, handler nhận `Method` có declaring class là `Object.class`. Viết handler phải đáp ứng return type (`boolean`/`int`/`String`) và quy tắc identity hoặc value semantics mong muốn.
- `args` có thể `null` khi method không có tham số. Đừng luôn truy cập `args[0]` mà không biết method được gọi.
- Default method trên proxy interface có thể được gọi qua `InvocationHandler.invokeDefault` nếu ứng dụng muốn dùng implementation mặc định, thay vì mặc nhiên tự gọi lại `method.invoke(proxy, args)` dễ dẫn đến recursion.
- Handler phải tuân theo các checked exception types mà interface khai báo; checked exception ngoài hợp đồng có thể bị bọc trong `UndeclaredThrowableException`.

**Liên hệ với module:** nếu generated proxy class nằm trong dynamic module bị encapsulate, bạn vẫn có thể gọi qua **interface được phép truy cập** hoặc dùng factory/handler API thích hợp. Việc này **không cấp quyền tự động** cho code module khác gọi mọi public method trên generated class bằng Reflection.

### 14.1. Đừng log `proxy.toString()` để “nhận diện cho chắc”

Với dynamic proxy, `toString()` có thể được dispatch tới handler. Một log statement vô tình có thể gọi code nghiệp vụ hoặc gây exception. Nếu chỉ muốn quan sát kiểu, lấy `proxy.getClass()`, `Proxy.isProxyClass`, `getModule()` và các metadata API; tránh invoke methods có side effect.

## 15. Lỗi phổ biến và quy trình chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách sửa/kiểm chứng |
| --- | --- | --- |
| `isProxyClass=false` dù class extends `Proxy` | Class là subclass tự viết, không phải generated proxy | Dùng `Proxy.newProxyInstance` và `Proxy.isProxyClass`. |
| `isProxyClass=false` dù tên chứa `$Proxy` | Tên class không phải bằng chứng proxy | Không đoán từ tên; dùng API. |
| `IllegalArgumentException` khi tạo proxy | Interface không hợp lệ, trùng, sealed, khác package/module, không visible hoặc return type xung đột | Kiểm tra đầu vào factory theo Javadoc Java 21. |
| `IllegalAccessException` khi gọi generated constructor | Proxy class public nhưng package trong dynamic module non-exported | Dùng `Proxy.newProxyInstance`. |
| `InaccessibleObjectException` sau `setAccessible(true)` | Package non-open với caller | Không lách JPMS; thay cách tạo/truy cập qua factory/interface. |
| `ClassCastException` giữa hai interface tên giống | Hai types có cùng binary name nhưng khác class loader identity | So `Class<?>` và loader, dùng shared API module/loader. |
| `getInvocationHandler` ném `IllegalArgumentException` | Object không phải proxy instance do factory sinh | Kiểm tra `isProxyClass` trước. |
| `getInvocationHandler(null)` bị lỗi | `null` không phải instance | Kiểm tra null rõ ràng. |
| `Modifier.isPublic=true` nhưng Reflection không truy cập được | JPMS package không export cho caller | Kiểm tra `clazz.getModule().isExported(pkg, callerModule)`. |
| `Module.isExported(pkg) == false` nhưng generated class dùng được interface | Package được **qualified export** tới dynamic proxy module | Kiểm tra overload `isExported(pkg, proxyModule)`. |
| Proxy khác class khi đảo thứ tự interfaces | Interface list order là đầu vào có nghĩa | Bảo toàn thứ tự khi cache/khởi tạo. |
| Proxy mang package/module tên lạ | Tên generated package/module không được đảm bảo cố định | Đọc bằng `getPackageName()`, `getModule()`; đừng hard-code. |
| Handler lặp vô hạn hoặc ném lỗi với `toString`/`equals` | Dispatch qua handler chưa xử lý `Object` methods | Xử lý theo method contract, không gọi lại proxy method ngây thơ. |

**Quy trình debug có thứ tự:**

```text
[1] Xác định interface list (thứ tự, public/non-public, sealed, duplicates)
   |
[2] Xem mỗi interface: ClassLoader, Module, package exported/open?
   |
[3] Xác nhận Class.forName(name,false,loader) == interfaceClass
   |
[4] Proxy.newProxyInstance(...) và phân loại lỗi tạo proxy
   |
[5] Với instance: Proxy.isProxyClass(proxy.getClass())
   |
[6] Quan sát proxyClass.getPackageName(), getModule(), flags
   |
[7] Phân biệt isExported(pkg) với isExported(pkg, callerModule)
   |
[8] Proxy.getInvocationHandler(proxy), kiểm tra hợp đồng handler
   |
[9] Gọi qua interface contract có quyền, tránh generated constructor
```

Không biến một lỗi class loading hoặc module visibility thành quyết định “thử mọi package/module” theo cách không kiểm soát; class identity và access policy phải được thiết kế rõ ràng.

## 16. Bài tập và đáp án định hướng

**Bài 1 — Ma trận.** Cho bốn tập interface: (a) tất cả public trong exported packages; (b) hai package-private cùng package/module; (c) public interface trong named module không exports/opens package; (d) hai package-private khác package. Xác định proxy class public hay non-public, vị trí package/module và trường hợp bị từ chối. Đáp án: (a) proxy public ở exported non-open package không bảo đảm tên; (b) non-public cùng package/module; (c) public trong dynamic module non-exported/non-open; (d) không tạo được.

**Bài 2 — API recognition.** Dùng `PublicProxyLab`: Vì sao `Proxy.class.isAssignableFrom(ManualProxy.class)` đúng nhưng `Proxy.isProxyClass(ManualProxy.class)` sai? Nêu khác biệt “inheritance shape” so với “được sinh bởi JDK proxy mechanism”.

**Bài 3 — JPMS export.** Dùng `DynamicModuleProxyLab`: Tại sao `apiModule.isExported(apiPkg) == false` mà `apiModule.isExported(apiPkg, pm) == true`? Định nghĩa “unqualified export” so với “qualified export”, và chứng minh kết quả không đồng nghĩa `isOpen`.

**Bài 4 — Constructor restriction.** Thay `Proxy.newProxyInstance` bằng lấy generated constructor trong Lab 3. Dự đoán `IllegalAccessException`, sau đó sửa trở lại bằng factory. Giải thích vì sao modifier `public` không loại bỏ kiểm tra module exports.

**Bài 5 — Classpath và named module.** Chuyển `PackagePrivateProxyLab` vào named module có một package hợp lệ; quan sát `samePackage`/`sameModule` vẫn true trong khi `moduleNamed` có thể thành true. Đừng giả sử non-public interface luôn thuộc unnamed module.

**Bài 6 — Interface order.** Thử `new Class<?>[]{First.class,Second.class}` và thứ tự đảo trong `InvalidProxyLab`, so sánh `getInterfaces()` và generated class identity. Giải thích vì sao thứ tự còn ảnh hưởng đến `Method` do handler nhận khi hai interfaces khai báo method cùng chữ ký.

**Bài 7 — Handler.** Bổ sung xử lý `hashCode`, `equals`, `toString` trong Lab 1. Bảo đảm các return types lần lượt là `int`, `boolean`, `String`; không gọi `proxy.toString()` bên trong handler `toString` để tránh đệ quy vô tận.

**Bài 8 — Loader visibility.** Chạy một interface bằng class loader không thấy được type, rồi kiểm tra điều kiện `Class.forName(i.getName(),false,loader)==i`. Giải thích vì sao hai classes cùng binary name do loaders khác nhau định nghĩa không thể thay thế cho nhau ở factory.

**Bài 9 — Thiết kế plugin.** Một API module cung cấp `public interface ApiService`, nhưng triển khai plugin là package-private class. Bạn cần proxy **interface public** hay proxy **class triển khai**? Chọn interface public được export từ shared module; mô tả lợi ích của việc không phụ thuộc tên generated proxy class.

**Tiêu chí hoàn thành bài:**

- [ ] Phân loại đúng cả bốn nhánh public/non-public và exported/open/non-exported.
- [ ] Giải thích được tại sao class `public` trong dynamic module non-exported vẫn inaccessible từ ngoài module.
- [ ] Dùng đúng `Proxy.isProxyClass`, `Proxy.getInvocationHandler` và `Module.isExported/isOpen`.
- [ ] Chạy được Lab 1–4 và hiểu stdout, đặc biệt `manualIsProxy=false`, `apiExportedToProxy=true` và `ctorAccess=IllegalAccessException`.
- [ ] Không dùng tên `$Proxy...` hoặc `jdk.proxy...` cố định, không cố instantiate qua generated constructor.
- [ ] Chỉ ra cách xử lý lỗi factory, access exception, handler contract và loader identity đúng bản chất.

## 17. Tài liệu Java 21 chính thức

1. [Java SE 21 — `java.lang.reflect.Proxy`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html): xem mục **Package and Module Membership of Proxy Class**, **Dynamic Modules**, `isProxyClass`, `getInvocationHandler` và các giới hạn `newProxyInstance`.
2. [Java SE 21 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html): dispatch method, `invokeDefault` và checked exceptions.
3. [Java SE 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `isNamed`, `isExported`, `isOpen`, `canRead`.
4. [Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getPackageName`, `getModule`, `getClassLoader`, `getInterfaces`.
5. [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html): phạm vi reflective access trong JPMS.
6. [Java SE 21 — Java Language Specification `7.7`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): module declarations, exports, opens.
7. [Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): metadata member mà handler có thể nhận.

**Kết luận:** Hãy xác định proxy qua **`Proxy.isProxyClass`**, kiểm tra handler bằng **`Proxy.getInvocationHandler`**, và đọc package/module bằng **`Class` + `Module` APIs**. Vị trí class được sinh phụ thuộc khả năng truy cập của interfaces: **public/non-public**, **exported/open hay không**, và **class loader identity**. Một proxy class mang flag **public** vẫn có thể bị khóa bên trong **dynamic module non-exported/non-open**; khi tạo instance, hãy dùng **`Proxy.newProxyInstance`**, không suy từ tên class hay gọi constructor tùy tiện.
