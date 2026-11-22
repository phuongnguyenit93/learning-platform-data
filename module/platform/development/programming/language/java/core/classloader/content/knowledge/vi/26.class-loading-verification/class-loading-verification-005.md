# Kiểm chứng package-private khi dùng hai ClassLoader trong Java

## 1. Vấn đề: cùng tên package chưa chắc cùng quyền truy cập

Java cho phép các kiểu trong cùng một package sử dụng thành viên **package-private** của nhau. Một field, method hoặc constructor không ghi `public`, `protected` hay `private` có mức truy cập package-private (còn gọi là *package access*). Một top-level class không có `public` cũng chỉ có package access.

Ví dụ:

```java
package p;

public final class Gate {
    static String secret() {
        return "package ok";
    }
}
```

Một class khác có `package p;` thường có thể gọi `Gate.secret()` tại compile time. Tuy nhiên, khi tách các classes vào **hai defining ClassLoaders**, JVM có thể từ chối thao tác ấy dù **tên package không thay đổi**.

Theo **JVMS 17 `5.3**, một runtime package được xác định bởi **package name và defining ClassLoader**. Hai classes thông thường có cùng tên `p` nhưng được hai loaders khác nhau định nghĩa sẽ thuộc **hai runtime packages khác nhau**.

Đây là một lỗi dễ gặp trong kiến trúc plugin, servlet container, test runner và custom class loading:
- Maven/Gradle/IDE biên dịch hợp lệ vì source classes cùng `package p`.
- Sau deployment, class A do parent loader định nghĩa, class B do plugin/child loader định nghĩa.
- Lời gọi một method package-private từ B sang A không còn hợp lệ tại runtime.
- JVM ném **`IllegalAccessError`**, chứ không phải `ClassNotFoundException`.

Bài học hướng dẫn kiểm chứng **từng mắt xích**, có chương trình Java 17+ chạy được và stdout xác định.

## 2. Phân biệt compile-time package và runtime package

### 2.1. Khi Java compiler kiểm tra source

Hai source files:

```java
// File p/Gate.java
package p;

public class Gate {
    static String secret() {
        return "package ok";
    }
}
```

```java
// File p/Caller.java
package p;

public class Caller {
    public static String call() {
        return Gate.secret();
    }
}
```

Cả hai cùng được compiler nhìn nhận thuộc package `p`. Khi compile trong một module/source context thích hợp, `Gate.secret()` được phép vì Caller ở cùng package.

Compiler sẽ sinh một symbolic reference tới method `p/Gate.secret:()Ljava/lang/String;` trong bytecode Caller. Reference này **chưa trỏ trực tiếp tới một đối tượng Class cố định trong JVM chạy sau này**.

### 2.2. Khi JVM giải quyết reference

Ở runtime, JVM xác định:
- `p.Caller` là runtime class do loader nào định nghĩa?
- `p.Gate` được tìm/định nghĩa bởi loader nào?
- Hai runtime classes có **cùng runtime package** không?
- Method `secret()` có access flags gì?
- Trong named modules, readability/exports còn ảnh hưởng tới các kiểu công khai không?

Nếu Caller và Gate ở hai defining loaders khác nhau, chỉ cùng text package name `"p"` là **không đủ** để cho package-private access.

### 2.3. Sơ đồ hai trạng thái

```text
Trường hợp A: cùng defining loader
  SharedLoader
    ├── p.Gate   (package p, loader SharedLoader)
    └── p.Caller (package p, loader SharedLoader)
  Caller.call() → Gate.secret() → OK

Trường hợp B: hai defining loaders
  GateLoader
    └── p.Gate   (package p, loader GateLoader)
         ▲
         │ parent delegation
  CallerLoader
    └── p.Caller (package p, loader CallerLoader)
  Caller.call() → Gate.secret() → IllegalAccessError
```

**Định nghĩa type identity:** runtime class thường được xác định bởi **binary name + defining loader**. Runtime package dùng **package name + defining loader**. Hai quy tắc có liên quan nhưng không được gộp thành một.

## 3. Initiating loader không nhất thiết là defining loader

`ClassLoader.loadClass("p.Gate")` có thể được gọi trên `CallerLoader` nhưng kết quả thực sự do `GateLoader` (parent) định nghĩa.

Ví dụ:

```text
CallerLoader.loadClass("p.Gate")
     │
     ├── findLoadedClass("p.Gate") không có
     │
     ▼
GateLoader.loadClass("p.Gate")
     │
     └── GateLoader.findClass → defineClass
               │
               ▼
         Trả Class<?> của GateLoader
```

Vì vậy:
- **Initiating loader:** loader được dùng để khởi xướng hoặc ghi nhận yêu cầu load.
- **Defining loader:** loader thực sự định nghĩa runtime class.
- `Class.getClassLoader()` trả **defining loader**.
- Gọi `loadClass` trên loader con không biến mọi class nó trả về thành class do loader con định nghĩa.

Điều này giải thích tại sao `CallerLoader` tìm thấy `Gate` bình thường mà **không** có quyền package-private với `Gate`.

## 4. Một chương trình Java 17+ tái hiện đúng lỗi

Thí nghiệm sẽ tạo **một tập bytecode duy nhất** cho `Gate` và `Caller`, sau đó chạy hai cấu hình loader khác nhau. Ta không thay source/bytecode giữa hai cấu hình. Như vậy khác biệt quan sát được đến từ **defining ClassLoader identity**.

### 4.1. Cấu trúc thư mục

```text
package-access-demo/
├── src/
│   └── p/
│       ├── Gate.java
│       └── Caller.java
├── Host.java
├── compiled/
│   └── p/
│       ├── Gate.class
│       └── Caller.class
└── host-out/
    └── Host.class
```

Ban đầu chỉ cần tạo `src/p/Gate.java`, `src/p/Caller.java` và `Host.java`. Các thư mục output sẽ được compiler tạo khi chạy lệnh cuối bài.

### 4.2. File `src/p/Gate.java`

```java
package p;

public final class Gate {
    static String secret() {
        return "package ok";
    }
}
```

`Gate` là class public. Riêng method `secret` không có access modifier, tức **package-private**.

### 4.3. File `src/p/Caller.java`

```java
package p;

public final class Caller {
    public static String call() {
        return Gate.secret();
    }
}
```

`Caller.call()` là public entry point để host gọi qua reflection. Phép truy cập package-private xảy ra **bên trong method Caller's bytecode**.

### 4.4. File `Host.java` — toàn bộ source

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

public final class Host {
    static final class DiskLoader extends ClassLoader {
        private final Path root;
        private final Set<String> owned;

        DiskLoader(Path root, ClassLoader parent,
                   Set<String> owned) {
            super(parent);
            this.root = root;
            this.owned = owned;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = owned.contains(name)
                            ? findClass(name)
                            : super.loadClass(name, false);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!owned.contains(name)) {
                throw new ClassNotFoundException(name);
            }

            Path file = root.resolve(
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("compiled");

        // Cấu hình A: cùng loader định nghĩa cả hai lớp.
        DiskLoader shared = new DiskLoader(
                root,
                Host.class.getClassLoader(),
                Set.of("p.Gate", "p.Caller"));

        Class<?> goodCaller = shared.loadClass("p.Caller");
        Class<?> goodGate = shared.loadClass("p.Gate");

        System.out.println("same-loader class access: "
                + goodCaller.getMethod("call").invoke(null));
        System.out.println("same-loader defining identity: "
                + (goodCaller.getClassLoader()
                   == goodGate.getClassLoader()));

        // Cấu hình B: parent định nghĩa Gate,
        // child định nghĩa Caller.
        DiskLoader gateLoader = new DiskLoader(
                root,
                Host.class.getClassLoader(),
                Set.of("p.Gate"));

        DiskLoader callerLoader = new DiskLoader(
                root,
                gateLoader,
                Set.of("p.Caller"));

        Class<?> gate = gateLoader.loadClass("p.Gate");
        Class<?> caller = callerLoader.loadClass("p.Caller");

        System.out.println("same package text: "
                + gate.getPackageName().equals(
                        caller.getPackageName()));
        System.out.println("same defining loader: "
                + (gate.getClassLoader()
                   == caller.getClassLoader()));
        System.out.println("same runtime class Gate: "
                + (gate == goodGate));

        try {
            System.out.println("cross-loader call: "
                    + caller.getMethod("call").invoke(null));
        } catch (InvocationTargetException error) {
            // Method.invoke bọc lỗi ném từ target method.
            if (error.getCause() instanceof IllegalAccessError) {
                System.out.println(
                        "cross-loader call: IllegalAccessError");
            } else {
                throw error;
            }
        } catch (IllegalAccessError error) {
            System.out.println(
                    "cross-loader call: IllegalAccessError");
        }

        // Reflection từ Host ngoài package p:
        Method secret = gate.getDeclaredMethod("secret");
        try {
            secret.invoke(null);
            System.out.println(
                    "host reflection: unexpectedly allowed");
        } catch (IllegalAccessException error) {
            System.out.println(
                    "host reflection: IllegalAccessException");
        }
    }
}
```

### 4.5. Biên dịch và chạy

Ở thư mục `package-access-demo` trên Bash/Linux/macOS:

```bash
mkdir -p compiled host-out
javac --release 17 -d compiled src/p/Gate.java src/p/Caller.java
javac --release 17 -d host-out Host.java
java -cp host-out Host
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force compiled,host-out | Out-Null
javac --release 17 -d compiled src/p/Gate.java src/p/Caller.java
javac --release 17 -d host-out Host.java
java -cp host-out Host
```

**Quan trọng:** Chỉ đưa `host-out` vào host application classpath. **Không** thêm `compiled` vào `-cp`, nếu không application parent loader có thể tự load Gate/Caller trước custom loader và vô tình phá giả thiết thí nghiệm.

`--release 17` chọn class-file version/API target Java 17; chương trình có thể chạy trên JDK 17+ phù hợp.

### 4.6. Stdout đã được kiểm chứng

```text
same-loader class access: package ok
same-loader defining identity: true
same package text: true
same defining loader: false
same runtime class Gate: false
cross-loader call: IllegalAccessError
host reflection: IllegalAccessException
```

Thí nghiệm đã biên dịch bằng `javac --release 17` và chạy trên OpenJDK 21. Các dòng in là các giá trị/loại lỗi, không phụ thuộc vào message chi tiết có thể khác giữa JVM implementations.

## 5. Tại sao cấu hình A thành công?

Trong cấu hình A:

```java
DiskLoader shared = new DiskLoader(
        root,
        Host.class.getClassLoader(),
        Set.of("p.Gate", "p.Caller"));
```

`shared` tự định nghĩa cả hai binary names. JVM thấy:
- `p.Gate` thuộc package `p` do `shared` định nghĩa.
- `p.Caller` cũng thuộc package `p` do `shared` định nghĩa.
- Cả hai có cùng **runtime package (p, shared)**.
- `Caller.call()` được phép tham chiếu method package-private `Gate.secret()`.

Kết quả:

```text
same-loader class access: package ok
same-loader defining identity: true
```

Host **không gọi `Gate.secret` trực tiếp**. Host gọi method `public Caller.call`, và JVM thực thi bytecode bên trong Caller — nơi runtime package access hợp lệ.

Sự khác nhau rất quan trọng: nếu Host trực tiếp reflectively invoke `Gate.secret` mà chưa có access override, reflective caller là Host (ở ngoài package), nên bị từ chối.

## 6. Tại sao cấu hình B ném IllegalAccessError?

Trong cấu hình B:

```java
DiskLoader gateLoader = new DiskLoader(
        root,
        Host.class.getClassLoader(),
        Set.of("p.Gate"));

DiskLoader callerLoader = new DiskLoader(
        root,
        gateLoader,
        Set.of("p.Caller"));
```

`callerLoader` sở hữu `p.Caller`, còn `p.Gate` được parent `gateLoader` định nghĩa. Khi Caller cần tham chiếu Gate, loader của Caller có thể delegate lên gateLoader, nên **class lookup thành công**.

Nhưng access check khác class lookup:
- `gate.getPackageName()` = `"p"`.
- `caller.getPackageName()` = `"p"`.
- `gate.getClassLoader() != caller.getClassLoader()`.
- Vậy **hai runtime packages khác nhau**.
- `Gate.secret()` vẫn package-private.
- Khi JVM resolve/access method reference, Caller không có quyền gọi.

Kết quả:

```text
same package text: true
same defining loader: false
same runtime class Gate: false
cross-loader call: IllegalAccessError
```

**Điều kiện gây lỗi không phải bytes hỏng**. Hai source files/bytecode giống hệt cấu hình A, và JVM đã tìm thấy cả hai. Khác biệt là **ai định nghĩa từng class**.

`IllegalAccessError` là subclass của `IncompatibleClassChangeError` rồi `LinkageError`. Nó không phải checked exception để code nghiệp vụ thông thường có thể xử lý như dữ liệu lỗi đầu vào.

## 7. Hai loại lỗi truy cập khác nhau: IllegalAccessError và IllegalAccessException

Mục cuối chương trình in:

```text
host reflection: IllegalAccessException
```

Tại đây Host lấy method qua reflection:

```java
Method secret = gate.getDeclaredMethod("secret");
secret.invoke(null);
```

`getDeclaredMethod` có thể tìm mô tả method, kể cả member không public. Nhưng `Method.invoke` thực hiện **reflection access check đối với reflective caller**. Host không thuộc runtime package của Gate, nên lời gọi khi chưa override gây **checked `IllegalAccessException`**.

Phân biệt:

| Lỗi | Cơ chế | Ví dụ |
|---|---|---|
| `IllegalAccessError` | JVM linkage/bytecode member hoặc type access | Caller cross-loader gọi Gate.secret |
| `IllegalAccessException` | Reflective invocation từ caller không có quyền | Host gọi Method.invoke chưa override |
| `InaccessibleObjectException` | `AccessibleObject.setAccessible` bị từ chối, thường vì JPMS encapsulation | Deep reflection từ module không có opens |
| `ClassCastException` | Runtime object không assignable tới target type | Hai bản api.Service khác defining loaders |
| `ClassNotFoundException` | Loader lookup không tìm thấy binary name | Directory/JAR không có class |

Nếu phản chiếu một method **public** của một **public class** mà module access phù hợp, reflection thường có thể gọi từ code ngoài package. Nhưng `getDeclaredMethod` “tìm thấy metadata” không làm package-private method tự thành public.

### Vì sao demo bắt InvocationTargetException?

`Method.invoke` có thể **bọc lỗi do target method ném** trong `InvocationTargetException`. Khi `Caller.call()` thực thi rồi ném `IllegalAccessError`, Host có thể nhận wrapper và phải kiểm tra `getCause()`. Do thời điểm resolution/linking có thể thay đổi, chương trình cũng bắt trực tiếp `IllegalAccessError` ở vùng thử nghiệm.

**Đừng biến mọi InvocationTargetException thành IllegalAccessError.** Phải kiểm tra cause thực tế và giữ lỗi khác, như chương trình đã làm.

## 8. Có thể dùng trySetAccessible để “sửa” không?

Đối với **unnamed modules** của ví dụ classpath này, một reflective caller có thể bật access override vào method package-private:

```java
// Trích đoạn, sau khi biến gate đã tồn tại.
Method secret = gate.getDeclaredMethod("secret");
boolean allowed = secret.trySetAccessible();

System.out.println("reflective override: " + allowed);

if (allowed) {
    System.out.println("reflected value: "
            + secret.invoke(null));
}
```

Trong fixture thuộc unnamed modules và với quyền truy cập thích hợp, kết quả dự kiến:

```text
reflective override: true
reflected value: package ok
```

**Nhưng đây không phải bản sửa cho direct bytecode access**:
- `trySetAccessible` thay đổi accessibility của **reflection operation** thông qua `Method` cụ thể.
- Nó không thay đổi defining ClassLoader của Gate/Caller.
- Nó không thay method access flags trong bytecode.
- Nó không làm hai runtime packages khác nhau thành một.
- `Caller.call()` vẫn gọi `invokestatic p/Gate.secret` không hợp lệ trong split-loader configuration.

Với **named modules**, deep reflection còn chịu điều kiện `opens` và các module access rules, nên `trySetAccessible()` có thể trả `false`. `setAccessible(true)` có thể ném `InaccessibleObjectException`.

**Đừng coi mở reflection là cách thiết kế plugin boundary.** Nếu host/plugin cần giao tiếp, nên sử dụng public shared API, không phụ thuộc vào reflective override.

## 9. Nếu Gate.secret là public thì chuyện gì đổi?

Giữ class Gate `public` nhưng đổi method thành:

```java
package p;

public final class Gate {
    public static String secret() {
        return "public API";
    }
}
```

Trong **mô hình unnamed-module classpath** của demo, caller thuộc runtime package khác vẫn có thể gọi public method trên public class nếu các điều kiện truy cập khác không cản trở.

Sau khi sửa source:
1. Biên dịch lại Gate/Caller đúng target.
2. Tạo **JVM hoặc loader mới** để tránh runtime class cũ đã được định nghĩa.
3. Chạy lại hai trường hợp và xác nhận method thực sự public trên artifact đích.

Nếu nội bộ framework không muốn method công khai, **đừng tùy tiện đổi toàn bộ package-private thành public**. Thiết kế tốt hơn:
- giữ nhóm implementation cooperating classes trong **cùng defining loader**;
- tạo **public facade/interface** nhỏ tại biên host/plugin;
- đưa shared API lên parent/common loader hoặc shared module.

### Quyền truy cập theo từng cấu hình

| Cấu hình | Package-private method qua direct bytecode | Public method trên public class |
|---|---|---|
| Cùng package name, cùng defining loader | Hợp lệ theo package access | Hợp lệ nếu không bị điều kiện khác chặn |
| Cùng package name, khác defining loaders | Không chỉ nhờ tên package | Có thể hợp lệ nếu class/member/module access phù hợp |
| Khác package name, cùng loader | Không có quyền package-private | Có thể hợp lệ |
| Child nhìn class parent qua delegation | Không thành cùng runtime package nếu defining loaders khác | Public API là cách chia sẻ phù hợp |
| Named modules/ModuleLayers | Còn phải xét module graph/runtime package | Còn phải xét readability/exports |

## 10. Package-private top-level type cũng bị ảnh hưởng

Một trường hợp nghiêm trọng hơn là class `Helper` tự nó package-private:

```java
package p;

final class Helper {
    static String value() {
        return "internal";
    }
}
```

Class khác trong package:

```java
package p;

public final class Entry {
    public static String run() {
        return Helper.value();
    }
}
```

Đây là **hai source files minh họa**, không phải một runnable project độc lập ở phần này. Compiler có thể cho phép `Entry` truy cập `Helper` nếu source thuộc cùng package.

Nhưng nếu runtime `Helper` được Loader-A định nghĩa, `Entry` được Loader-B định nghĩa, JVM có thể chặn việc truy cập **chính kiểu `Helper`** vì package-private type access, trước khi xét method bên trong.

Case chính cố ý dùng **public class Gate, package-private method secret** để minh họa một loại lỗi **member access** riêng, không trộn thêm quyền truy cập của class declaration.

## 11. Class.getPackageName và Package object dễ gây hiểu nhầm

`Class.getPackageName()` cho chuỗi tên package, không chứa defining loader identity. Do đó:

```java
boolean sameText =
        gate.getPackageName().equals(caller.getPackageName());
```

`sameText` là `true` trong case B nhưng Java vẫn từ chối package-private call.

`java.lang.Package` là metadata về package:
- `Class.getPackage()` trả thông tin Package tương ứng class.
- `ClassLoader.getDefinedPackage(name)` tra package do chính loader đó định nghĩa.
- `ClassLoader.getPackage(name)` đã deprecated từ Java 9 và có thể tìm qua parent loader; dùng nó để suy từ đó về quyền package-private rất dễ sai.

**Runtime package identity** không được suy chỉ từ `Package.getName()`, `Package.isSealed()` hoặc annotations. Nên lấy hai `Class<?>` và kiểm tra **tên package + defining loader**.

Cũng không nên dùng riêng `CodeSource`:
- Hai loaders có thể đọc **cùng tệp .class** trên đĩa nhưng tạo hai runtime classes khác nhau.
- Custom `defineClass` có thể gắn CodeSource null/không hữu ích.
- Java agent có thể transform bytes, khiến source URL và bytes cuối khác nhau.

`CodeSource` hữu ích để truy vết artifact, nhưng **không thay ClassLoader identity**.

## 12. ClassCastException cũng liên quan hai loader, nhưng là lỗi khác

Giả sử host và plugin tự định nghĩa riêng một interface cùng binary name:

```text
HostLoader
  └── api.Service [Class A]

PluginLoader
  ├── api.Service [Class B]
  └── plugin.Impl implements Class B
```

Host muốn ép object `plugin.Impl` sang `api.Service` của host (Class A). Hai runtime interfaces cùng tên nhưng khác defining loader nên **không phải cùng kiểu**. Phép cast có thể ném `ClassCastException`.

Đây **không phải** lỗi package-private của `Gate.secret`. Phân biệt:
- **`IllegalAccessError`:** quyền truy cập type/member không hợp lệ.
- **`ClassCastException`:** object không thuộc runtime target type.
- **`NoSuchMethodError`:** caller compiled method reference nhưng runtime class không có method signature phù hợp.

Ba lỗi đều có thể xuất hiện khi loader topology thay đổi, nhưng cách sửa không giống nhau.

## 13. Thiết kế shared API cho plugin

Kiến trúc nên ưu tiên:

```text
          Common Parent ClassLoader
                  │
                  └── api.PluginService
                      public interface
                         ▲
                         │ implements
            ┌────────────┴────────────┐
            │                         │
       PluginLoader-A             PluginLoader-B
       plugin.AImpl               plugin.BImpl
       plugin internals           plugin internals
```

Service contract có thể là:

```java
package api;

public interface PluginService {
    String execute();
}
```

Đây là file `api/PluginService.java` minh họa, biên dịch được nhưng không có main. Host và plugin phải dùng **cùng runtime Class<?> của interface này**, do parent/common loader định nghĩa.

Với mỗi plugin:
- Implementation classes và package-private helpers nên ở cùng defining loader nếu chúng cần package access.
- Giao tiếp cross-loader phải đi qua public shared types/contract hoặc dữ liệu trung gian.
- Tránh cho plugin child tự định nghĩa lại host API packages.
- Nếu dùng child-first để cô lập dependencies, bảo đảm shared API namespaces được delegate đúng parent.
- Chú ý method signatures của shared API: DTO/exception types cũng có thể bị định nghĩa trùng ở loader khác gây identity problems.
- Test plugin trong loader architecture thật, không chỉ với flat classpath IDE.

## 14. Tại sao child-first dễ tạo “split runtime package”?

Một custom child-first loader có thể ưu tiên class files trong plugin JAR:
- `p.Caller` có trong plugin → child tự define.
- `p.Gate` không có trong plugin → child delegate parent.
- Hai classes cùng package `p` trên source → nhưng runtime package khác.

Một số framework có parent-first ngoại lệ cho platform API, nhưng local-first với application classes. Mỗi container/plugin framework có rules riêng. Không được suy rằng loader nào cũng thực hiện parent-first chuẩn trong mọi namespace.

**Cách phòng ngừa:** Đừng split nửa nhóm internal classes giữa parent và child rồi kỳ vọng package-private. Hãy chọn một loader owner nhất quán cho nhóm đó hoặc publicize đúng extension boundary.

Những sự thay đổi như:
- chuyển JAR giữa common/lib và plugin/lib;
- shadow một package của host;
- nâng application server;
- chuyển test runner từ một loader sang nhiều loaders;
- tạo ModuleLayer mới;

đều cần regression test về runtime class identity và access.

## 15. JPMS bổ sung quyền nhưng không xóa runtime package

Java 9+ có named modules:
- `requires` / readability;
- `exports` cho API truy cập thông thường;
- `opens` cho deep reflection runtime;
- `ModuleLayer` và module-to-loader mapping.

**Exports không làm package-private members trở thành public.** **Opens không hợp pháp hóa direct bytecode invocation từ class khác runtime package.**

Ví dụ descriptor:

```java
module app.api {
    exports app.api;
}
```

```java
module app.plugin {
    requires app.api;
    provides app.api.Service with app.plugin.Impl;
}
```

Đây là **hai descriptors minh họa**, cần thực sự có `app.api.Service` và `app.plugin.Impl` khi đưa vào dự án hoàn chỉnh. Plugin có thể cung cấp implementation qua `ServiceLoader` mà không export toàn bộ implementation package cho consumer.

Với named modules, còn cần xác nhận các điều kiện module access cho public types. Nhưng **dù export package `p`, class ở hai defining loaders vẫn không được dùng package-private lẫn nhau chỉ nhờ trùng tên `p`**.

Đặc biệt, `--add-opens` là giải pháp có phạm vi cho deep reflection khi hợp lệ, không phải “fix” cho một symbolic `invokestatic` package-private cross-loader.

## 16. Debug đúng lỗi trong container, test runner và plugin host

Checklist thực tế:

1. **Ghi error gốc**, class nào gọi member nào, không chỉ dòng “plugin failed”.
2. **Đọc cause chain**. Nếu gọi qua `Method.invoke`, phân biệt error trực tiếp và `InvocationTargetException.getCause()`.
3. **Lấy `Class<?>` của caller và target** từ đúng loader context nếu có thể.
4. **In tên package** bằng `getPackageName()`.
5. **In defining loaders** bằng `getClassLoader()` và so identity bằng `==`.
6. **Kiểm tra parent delegation graph** và nơi hai class được định nghĩa, không chỉ nơi caller gọi `loadClass`.
7. **Xem class file thực** bằng `javap -p -c`; xác định method/field có package access hay public/protected/private.
8. **Kiểm tra binary API mismatch** nếu có `NoSuchMethodError` thay vì `IllegalAccessError`.
9. **Kiểm tra JPMS** nếu class ở named modules hoặc reflection bị opens/exports từ chối.
10. **Kiểm tra test/prod classpaths** và việc host/container cung cấp shared classes bên ngoài plugin.
11. **Tạo loader/JVM mới cho thử nghiệm**, tránh cached class definitions.
12. **Chọn sửa API hoặc loader placement** rồi chạy integration test trên kiến trúc thực tế.

### ClassLoader probe độc lập

```java
public final class PackageProbe {
    private PackageProbe() {}

    public static void print(String name, Class<?> type) {
        System.out.println(name + " class=" + type.getName());
        System.out.println(name + " package="
                + type.getPackageName());
        System.out.println(name + " defining loader="
                + type.getClassLoader());
        System.out.println(name + " module="
                + type.getModule());
    }
}
```

Đây là file `PackageProbe.java` biên dịch được, **không có main**; tích hợp vào host/test code. Giá trị loader/module string là dữ liệu runtime, **không có stdout cố định**.

### Kiểm tra bytecode

Sau khi chạy ví dụ mục 4:

```bash
javap -p -c -classpath compiled p.Gate
javap -p -c -classpath compiled p.Caller
```

- `-p` hiển thị members không public.
- `-c` hiển thị instructions.
- Có thể thấy `Caller.call` chứa `invokestatic` tới `Gate.secret`.
- `javap` trên output files xác nhận **bytecode trên đĩa**; nó không tự nói JVM process đang dùng defining loader nào.

## 17. Vì sao Package Sealing không phải giải pháp?

JAR manifest có thể **seal package**, làm việc định nghĩa classes trong package tuân các ràng buộc về code source trong một loader. Package sealing và package-private access là hai khái niệm khác nhau.

Không suy từ:
- `Package.isSealed() == true`;
- cùng tên package;
- cùng JAR filename;
- cùng CodeSource URL;

rằng hai classes thuộc cùng runtime package nếu **defining loaders khác nhau**.

Sealing violation có thể có lỗi riêng, nhưng nó không gộp hai runtime packages thành một và không nâng quyền package-private.

## 18. Các hiểu nhầm phổ biến

| Nhận định sai | Điều đúng |
|---|---|
| Hai classes có cùng `package p;` thì chắc cùng package runtime | Phải có cùng defining loader (theo JVMS `5.3) |
| Code compile được thì package-private chắc chạy được | Deployment có thể thay loader boundaries |
| Loader child tìm class parent nên class đó thuộc child | Parent vẫn có thể là defining loader |
| `getPackageName` giống là đủ | Cần so defining loaders |
| Hai class files giống hệt bytes nghĩa là cùng runtime Class | Không nếu do hai loaders độc lập định nghĩa |
| `ClassLoader.getPackage(name)` đủ xác nhận package-private | Có thể tìm Package metadata từ parent; không kết luận runtime package |
| `CodeSource` giống thì runtime class giống | Không; type identity phụ thuộc loader |
| `setAccessible(true)` sửa mọi lỗi package-private | Chỉ ảnh hưởng reflection access theo điều kiện |
| `--add-opens` sửa direct package-private bytecode access | Không |
| Cứ đổi child-first sang parent-first là an toàn | Cần kiểm tra shared API, versions và classpath |
| `IllegalAccessException` và `IllegalAccessError` là một | Reflection checked exception khác linkage Error |
| `ClassCastException` hai loaders cũng chính là package-private error | Khác: type assignability so với member access |
| JPMS exports mọi thứ trong package là public | Không làm non-public members thành public |
| Thay JAR trên disk làm JVM dùng class mới ngay | Runtime classes đã loaded thường cần loader/process mới |
| Đặt plugin internal cùng package name của host là được phép truy cập host internals | Không nếu defining loaders khác, còn module constraints |

## 19. Câu hỏi tự kiểm tra

1. **Package-private cần modifier nào?** Không ghi `public`, `protected` hoặc `private`.
2. **Dòng `package p;` có đủ xác nhận package runtime identity không?** Không.
3. **JVMS xác định runtime package bằng gì?** Package name và defining ClassLoader.
4. **Defining loader có phải luôn là loader mà client gọi `loadClass` không?** Không.
5. **Hai loaders khác nhau đọc cùng bytecode có tạo cùng runtime class không?** Không nếu mỗi loader tự define.
6. **Vì sao cấu hình A gọi `Gate.secret` được?** Gate/Caller thuộc cùng runtime package do shared loader định nghĩa.
7. **Vì sao cấu hình B bị từ chối?** Gate/Caller do hai loaders khác nhau định nghĩa; package-private không accessible.
8. **Lỗi trong Caller.call ở cấu hình B?** `IllegalAccessError`.
9. **Lỗi Host reflective invoke `secret` chưa override?** `IllegalAccessException`.
10. **`InvocationTargetException` có thể bọc lỗi nào?** Throwable do target method ném, gồm `IllegalAccessError` trong tình huống minh họa.
11. **`trySetAccessible` có làm JVM package identity thay đổi không?** Không.
12. **Mở module bằng `opens` có làm direct cross-loader package-private call hợp lệ không?** Không.
13. **`Class.getPackageName()` hai classes bằng nhau mà loader khác thì sao?** Chúng vẫn khác runtime package.
14. **Top-level class package-private có thể bị access check từ loader khác không?** Có.
15. **Khi Gate.secret đổi thành public, mô hình unnamed-module còn bị package-private chặn không?** Không, miễn các điều kiện access khác thỏa.
16. **Một public interface để chia sẻ host/plugin nên đặt ở đâu?** Shared parent loader/module ổn định.
17. **Vì sao Host chỉ chạy `-cp host-out`?** Tránh parent định nghĩa các target classes từ compiled.
18. **Muốn chẩn đoán runtime package, nên in những gì?** Class name, package name, defining loader, module và source nếu có.
19. **Sealing package có gộp hai loaders không?** Không.
20. **Compile pass nhưng runtime IllegalAccessError nên kiểm tra gì trước?** Member flags, caller/target defining loaders, loader topology và module rules.

## 20. Tài liệu tham khảo chính thức

- [JVMS 17 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining/initiating loader, runtime class identity, **runtime package**.
- [JVMS 17 5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): JVM checks khi resolution classes/members.
- [JLS 17 6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): package-private, protected, public và private trong Java source.
- [Java SE 17 ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass` và `getDefinedPackage`.
- [Java SE 17 Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getPackageName`, `getClassLoader` và `getModule`.
- [Java SE 17 IllegalAccessError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessError.html): lỗi truy cập member/type lúc linkage/runtime.
- [Java SE 17 Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke` và InvocationTargetException.
- [Java SE 17 AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, các quy tắc reflection access.
- [Java SE 17 Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module readability, exports và opens.

**Kết luận:** Khi code Java dùng package-private, **cùng tên package trong source không đủ**. Hai classes phải thuộc **cùng runtime package**, tức có package name và defining ClassLoader tương ứng. Trong ví dụ, **cùng loader → thành công**, còn **tách Gate và Caller qua parent/child defining loaders → IllegalAccessError**. Để thiết kế plugin/container đáng tin, hãy đặt các internal classes cần package access ở **cùng loader**, và giao tiếp qua **public shared API** khi đi qua ranh giới loader.
