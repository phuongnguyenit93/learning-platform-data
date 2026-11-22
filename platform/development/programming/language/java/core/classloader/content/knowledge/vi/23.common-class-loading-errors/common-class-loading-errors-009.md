# IllegalAccessError, IllegalAccessException và InaccessibleObjectException trong Java ClassLoader

## 1. Ba lỗi khác nhau dù tên rất giống nhau

Khi Java làm việc với `ClassLoader`, reflection và JPMS, một chương trình có thể gặp các lỗi cùng chứa cụm “Illegal Access” nhưng phát sinh từ những cơ chế khác nhau:

- **`java.lang.IllegalAccessError`**: lỗi khi **JVM liên kết/giải quyết hoặc sử dụng một symbolic reference** tới class, field hay method mà caller không được phép truy cập. Đây là một `Error` thuộc nhánh `LinkageError`; thường xuất hiện nếu class được biên dịch với một version của API nhưng chạy với version có visibility thay đổi không tương thích.
- **`java.lang.IllegalAccessException`**: một **checked exception**, điển hình khi code sử dụng `Method.invoke`, `Field.get`, `Field.set` hay `Constructor.newInstance` nhưng Java reflection access checks vẫn có hiệu lực và caller không được quyền truy cập member.
- **`java.lang.reflect.InaccessibleObjectException`**: một **unchecked exception** xuất hiện khi code **đòi suppress các access checks** qua `setAccessible(true)` nhưng không được phép, nhất là khi một named module không mở package cho caller trong Java 9+.

Không nên kết luận “chỉ cần gọi `setAccessible(true)`” mỗi khi nhìn thấy một trong ba lỗi. Với `IllegalAccessError`, đó thường là vấn đề **binary compatibility hoặc JVM access linkage**. Với `IllegalAccessException`, cần xem caller/member và các thao tác reflection. Với `InaccessibleObjectException`, cần xem **quyền mở package của module** và có thật sự cần deep reflection không.

~~~text
                 THAO TÁC TRUY CẬP
                        |
      +-----------------+------------------+
      |                 |                  |
      v                 v                  v
 bytecode call     Method.invoke      setAccessible(true)
 getfield / etc.   Field.get ...           |
      |                 |                  |
  access check     access checks      được suppress?
      |                 |                  |
 illegal          illegal              không
      |                 |                  |
      v                 v                  v
 IllegalAccessError  IllegalAccessException  InaccessibleObjectException
~~~

Sơ đồ chỉ mô tả nguyên nhân điển hình, không phải mọi lỗi có thể xảy ra. Ví dụ, một method được gọi thành công qua reflection nhưng body ném exception thì reflection có thể bọc cause trong `InvocationTargetException`, không phải mặc nhiên ném `IllegalAccessException`.

## 2. So sánh theo lớp lỗi, thời điểm và cách sửa

| Đặc điểm | IllegalAccessError | IllegalAccessException | InaccessibleObjectException |
| --- | --- | --- | --- |
| Package | `java.lang` | `java.lang` | `java.lang.reflect` |
| Thừa kế | `Error → LinkageError → IncompatibleClassChangeError` | `Exception → ReflectiveOperationException` | `RuntimeException` |
| Checked exception? | Không | Có | Không |
| API/ngữ cảnh thường thấy | `invokevirtual`, `invokestatic`, truy cập symbolic class/field/method | `Method.invoke`, `Field.get`, `Constructor.newInstance` | `AccessibleObject.setAccessible(true)` |
| Nguyên nhân thường gặp | Runtime binary không còn cho phép direct access đã compile | Reflection caller không có quyền với private/package-private member | JPMS package không `opens` tới caller |
| Có bắt bởi `catch (Exception)`? | Không | Có | Có |
| Biện pháp gốc | Đồng bộ JAR versions, visibility, exports và class loader | Public API hoặc reflection có quyền hợp lệ | Public API, `opens` hợp lý, library/JDK compatibility |
| `--add-opens` luôn sửa được? | Không | Không phải cho mọi trường hợp | Có thể giúp riêng nguyên nhân JPMS chưa mở package |

**Cẩn thận thứ tự cây kế thừa:** `IllegalAccessError` trực tiếp kế thừa `IncompatibleClassChangeError`, rồi tới `LinkageError`, `Error`. `IllegalAccessException` không nằm cùng nhánh dù tên rất giống.

## 3. Access modifiers và quyền truy cập trong JVM

Java có bốn mức visibility thường gặp:

- `public`: class/member có thể được truy cập khi declaring type, module và caller thỏa quy tắc liên quan.
- `protected`: ngoài cùng package, còn có quyền theo quan hệ subclass với các ràng buộc JVM riêng.
- **Package-private** (không ghi modifier): trong cùng **runtime package**.
- `private`: quyền truy cập hẹp theo class/nestmate rules, không phải cứ trùng package là được.

Ví dụ:

~~~java
package demo;

class HiddenClass {
    public static void run() {
        System.out.println("running");
    }
}
~~~

Đây là **mã minh họa**, không có main. Method `run` public nhưng class `HiddenClass` lại package-private. Caller package khác không mặc nhiên truy cập được method đó.

Với named module, còn phải xét:

1. Module caller có **đọc (reads)** module chứa target không?
2. Package target có **exports** tới caller để dùng public API không?
3. Nếu muốn deep reflection, package target có **opens** tới caller không?
4. Declaring class/member có thực sự thỏa Java language access rules không?
5. Khi có custom loaders, caller và target có thuộc đúng **runtime package** không?

Hai class cùng viết `package demo;` trong Java source **chưa chắc** cùng runtime package nếu hai defining class loaders khác nhau. `getPackageName()` chỉ cho tên chuỗi; không chứng minh có quyền package-private xuyên loader.

## 4. IllegalAccessError: direct JVM access thất bại

Theo Java SE 17 API, `IllegalAccessError` được ném khi ứng dụng cố truy cập/sửa field hoặc gọi method mà nó không có quyền truy cập. Java compiler thường phát hiện lỗi này nếu biên dịch toàn bộ source với cùng định nghĩa API. Vì vậy tại runtime, dấu hiệu này thường gợi ý **runtime class definition khác định nghĩa lúc compile**.

Ví dụ thay đổi không tương thích:

~~~text
Ở compile time:
  api.Library.greet() là public static

Ở runtime:
  api.Library.greet() là static, package-private

client.Main vẫn chứa bytecode gọi api.Library.greet()
=> JVM từ chối quyền gọi => IllegalAccessError
~~~

Các tình huống có thể gây ra:

- API public method bị hạ visibility trong version library mới.
- Public class bị chuyển thành package-private ở runtime.
- Module không export package tới caller dù bytecode có tham chiếu trực tiếp.
- Một dependency JAR không đúng version nằm trước version mong muốn trong classpath.
- Plugin loader hoặc hot reload lấy một class khác với class compiler từng dùng.
- Hai classes trùng package source được **định nghĩa bởi các loaders khác nhau**, làm mất package-private access.
- Bytecode weaving/shading/instrumentation tạo reference bị JVM từ chối.

Vì đây là `Error` trong nhánh **binary linkage**, catch rồi tiếp tục chạy như không có gì thường là cách xử lý sai. Cần sửa dependency graph, module ownership, source/API compatibility hay class loader routing.

## 5. Ví dụ Java 17+ hoàn chỉnh: tái hiện IllegalAccessError

Ví dụ này xây một client chạy bình thường với library v1, sau đó **chỉ thay class thư viện** bằng v2 mà không biên dịch lại client.

### 5.1. Cấu trúc thư mục

~~~text
linkage-demo/
├── v1-src/
│   └── api/
│       └── Library.java
├── v2-src/
│   └── api/
│       └── Library.java
└── client-src/
    └── client/
        └── Main.java
~~~

### 5.2. File v1-src/api/Library.java

~~~java
package api;

public class Library {
    public static String greet() {
        return "hello";
    }
}
~~~

### 5.3. File v2-src/api/Library.java

~~~java
package api;

public class Library {
    static String greet() { // Không còn public
        return "hello";
    }
}
~~~

### 5.4. File client-src/client/Main.java

~~~java
package client;

import api.Library;

public class Main {
    public static void main(String[] args) {
        try {
            System.out.println("call: " + Library.greet());
        } catch (IllegalAccessError expected) {
            System.out.println("call: IllegalAccessError");
        }
    }
}
~~~

### 5.5. Chạy v1

Đứng trong thư mục `linkage-demo`, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -d out v1-src/api/Library.java client-src/client/Main.java
java -cp out client.Main
~~~

Stdout:

~~~text
call: hello
~~~

### 5.6. Thay chỉ thư viện bằng v2, giữ nguyên Main.class

~~~bash
javac --release 17 -d out v2-src/api/Library.java
java -cp out client.Main
~~~

Stdout:

~~~text
call: IllegalAccessError
~~~

**Giải thích:** `client.Main.class` vẫn tham chiếu `api.Library.greet()Ljava/lang/String;` qua instruction `invokestatic`. Khi JVM chạy trong **process mới** với `Library.class` của v2, method vẫn có tên/descriptor ấy nhưng đã thành package-private; `client.Main` ở package khác nên không có quyền gọi. Nếu biên dịch lại `Main.java` trực tiếp với v2, compiler sẽ báo access problem từ trước. Ta cố tình giữ client bytecode cũ để chứng minh **runtime binary incompatibility**.

Đây không phải `IllegalAccessException` vì không có `Method.invoke`, và không phải `InaccessibleObjectException` vì không có `setAccessible(true)`.

## 6. IllegalAccessException: access check của reflection

Khi dùng `java.lang.reflect.Method`, `Field` hoặc `Constructor`, Java reflection phải xác minh caller có được truy cập member không. `IllegalAccessException` là **checked exception** mô tả trường hợp thao tác reflection không có quyền.

Các API thường gặp:

~~~java
Method method = SomeClass.class.getDeclaredMethod("secret");
method.invoke(null);
~~~

Đây là **mã minh họa** giả sử `SomeClass` có static method `secret`. `getDeclaredMethod` có thể tìm **private method metadata**, nhưng `invoke` khi access checks còn bật vẫn có thể ném `IllegalAccessException`.

Phân biệt:

- `Class.getDeclaredMethod`: tìm method được khai báo trong class, kể cả private, không tự cấp quyền gọi.
- `Method.invoke`: thực thi Java access checks trừ khi đã được cho phép suppression, có thể ném `IllegalAccessException`.
- `Field.get/set`: checks với field cũng có thể tạo `IllegalAccessException`.
- `Constructor.newInstance`: constructor không accessible từ caller có thể gây `IllegalAccessException`.
- `MethodHandles.Lookup.findVirtual`, `findStatic`, `privateLookupIn` có access rules của MethodHandles; chúng cũng có thể ném `IllegalAccessException` nhưng **không phải cùng call path** với `Method.invoke`.

Nếu method thực sự được gọi rồi **body của nó ném exception**, `Method.invoke` thông thường bọc nó trong **`InvocationTargetException`**. Nên xem `getCause()` trước khi nói lỗi do reflection access.

## 7. Ví dụ Java 17+ hoàn chỉnh: IllegalAccessException rồi bật access

Tạo file **ReflectionDemo.java**:

~~~java
import java.lang.reflect.Method;

class Vault {
    private static String secret() {
        return "private-data";
    }
}

public class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        Method method = Vault.class.getDeclaredMethod("secret");

        try {
            method.invoke(null);
            System.out.println("invoke without override: allowed");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "invoke without override: IllegalAccessException");
        }

        System.out.println("trySetAccessible: "
                + method.trySetAccessible());
        System.out.println("private result: "
                + method.invoke(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ReflectionDemo.java
java ReflectionDemo
~~~

Stdout chính xác:

~~~text
invoke without override: IllegalAccessException
trySetAccessible: true
private result: private-data
~~~

**Giải thích:**

1. `Vault.secret()` là private. `ReflectionDemo` là một top-level class khác, không phải nestmate được phép truy cập private member ấy.
2. `getDeclaredMethod` vẫn tìm được method metadata.
3. Lần đầu `invoke(null)` gặp access check và ném `IllegalAccessException`.
4. Vì `Vault` và `ReflectionDemo` cùng unnamed module, `trySetAccessible()` được phép trả true theo quy tắc `AccessibleObject`.
5. Lần `invoke` sau sử dụng accessible flag đã bật và thành công.

**Không suy rằng trySetAccessible luôn true.** Khi target nằm trong named module khác và package chưa open, suppression có thể bị từ chối, như ví dụ tiếp theo.

## 8. InaccessibleObjectException: setAccessible(true) bị từ chối

Trong Java 9+, **`InaccessibleObjectException` kế thừa `RuntimeException`**. Lỗi điển hình khi:

~~~java
Method method = targetClass.getDeclaredMethod("hidden");
method.setAccessible(true);
~~~

Đây là **đoạn minh họa**. Caller muốn tắt Java language access checks, nhưng module chứa declaring class chưa open package cho module của caller. `setAccessible(true)` ném `InaccessibleObjectException` ngay tại yêu cầu bật quyền.

Đặt cạnh nhau:

| Gọi API | Loại lỗi liên quan |
| --- | --- |
| `method.invoke(obj)` khi access check đang bật | `IllegalAccessException` |
| `method.setAccessible(true)` khi không được suppress | `InaccessibleObjectException` |
| `method.trySetAccessible()` khi không được suppress | Trả `false` theo hợp đồng thông thường |
| `method.invoke(obj)` sau khi bật suppression hợp lệ | Có thể thực thi method; body có thể ném exception riêng |

`trySetAccessible` là cách hỏi một cách mềm dẻo, **không phải cửa sau** vượt qua JPMS. Nếu trả false, ứng dụng vẫn cần lựa chọn public API khác hoặc điều chỉnh module ownership hợp lý.

Một lưu ý: với một số public members trong public classes được export, `setAccessible(true)` cũng có thể được cho phép theo các điều kiện JDK — **không phải mọi lời gọi setAccessible trên member của named module đều ném**. Vấn đề hay gặp là **private/protected/package-private members ở module khác mà package không open**.

## 9. Exports, opens, requires: ba thứ đừng đánh đồng

JPMS (Java 9+) có các modules có tên và descriptor `module-info.java`.

~~~java
module library.mod {
    exports sample.lib;
}
~~~

Descriptor này cho code ở module đọc `library.mod` dùng những **public types của package `sample.lib`** theo Java access rules. Tuy nhiên `exports` **không mặc nhiên cấp deep reflection** tới private fields/methods.

So sánh:

| Khai báo | Tác dụng chính |
| --- | --- |
| `requires library.mod;` | Consumer module được đọc module library |
| `exports sample.lib;` | Package cung cấp public API cho mọi module đọc |
| `exports sample.lib to app.mod;` | Public API chỉ export tới app.mod và những targets nêu rõ |
| `opens sample.lib;` | Mở package cho deep reflection từ modules khác |
| `opens sample.lib to app.mod;` | Chỉ mở deep reflection tới app.mod |
| `open module library.mod { ... }` | Mở package của module theo quy tắc open module |

**Một package đã exports chưa chắc opens.** Vì vậy code có thể compile và gọi `SecretBox.publicMessage()` bình thường, nhưng gọi `setAccessible(true)` trên `SecretBox.secretMessage()` vẫn bị từ chối.

Launcher có hai options tương ứng:

~~~text
--add-exports library.mod/sample.lib=app.mod
--add-opens library.mod/sample.lib=app.mod
~~~

`--add-exports` dùng cho access tới **public API** theo module rules; `--add-opens` cấp quyền **deep reflection** cho caller module được chỉ định. Không nên dùng `--add-opens` như “cách sửa chung mọi IllegalAccessError” vì nó không làm private member thành public trong bytecode và không sửa version mismatch.

## 10. Ví dụ Java 17+ hoàn chỉnh: exported package vẫn chặn deep reflection

Thí nghiệm named modules cho thấy **cùng một method private** gây `IllegalAccessException` khi gọi qua `invoke`, và `InaccessibleObjectException` khi cố bật accessible.

### 10.1. Cấu trúc thư mục

~~~text
jpms-access-demo/
└── src/
    ├── library.mod/
    │   ├── module-info.java
    │   └── sample/
    │       └── lib/
    │           └── SecretBox.java
    └── app.mod/
        ├── module-info.java
        └── sample/
            └── app/
                └── Main.java
~~~

### 10.2. src/library.mod/module-info.java

~~~java
module library.mod {
    exports sample.lib;
}
~~~

### 10.3. src/library.mod/sample/lib/SecretBox.java

~~~java
package sample.lib;

public class SecretBox {
    public static String publicMessage() {
        return "public";
    }

    private static String secretMessage() {
        return "private";
    }
}
~~~

### 10.4. src/app.mod/module-info.java

~~~java
module app.mod {
    requires library.mod;
}
~~~

### 10.5. src/app.mod/sample/app/Main.java

~~~java
package sample.app;

import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;
import sample.lib.SecretBox;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("public call: "
                + SecretBox.publicMessage());

        Method method = SecretBox.class
                .getDeclaredMethod("secretMessage");

        try {
            method.invoke(null);
            System.out.println("invoke private: allowed");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "invoke private: IllegalAccessException");
        }

        try {
            method.setAccessible(true);
            System.out.println("setAccessible: enabled");
            System.out.println("private result: "
                    + method.invoke(null));
        } catch (InaccessibleObjectException expected) {
            System.out.println(
                    "setAccessible: InaccessibleObjectException");
        }
    }
}
~~~

### 10.6. Biên dịch và chạy bình thường

Đứng tại `jpms-access-demo` và dùng JDK 17+:

~~~bash
javac --release 17 --module-source-path src -d mods -m library.mod,app.mod
java --module-path mods --module app.mod/sample.app.Main
~~~

Stdout chính xác:

~~~text
public call: public
invoke private: IllegalAccessException
setAccessible: InaccessibleObjectException
~~~

**Vì sao?** `app.mod` đã requires `library.mod` và package `sample.lib` được exports, do đó direct public call được phép. `Method.invoke` tới private method bị access checks chặn. `setAccessible(true)` cố suppress checks nhưng package chưa `opens` cho app.mod, nên báo `InaccessibleObjectException`.

### 10.7. Chạy lại với mở package hẹp cho app.mod

~~~bash
java --add-opens library.mod/sample.lib=app.mod --module-path mods --module app.mod/sample.app.Main
~~~

Stdout chính xác:

~~~text
public call: public
invoke private: IllegalAccessException
setAccessible: enabled
private result: private
~~~

**Điểm cần hiểu:** `--add-opens` cho phép yêu cầu `setAccessible(true)` thành công. Nó **không tự động tắt access checks** của lời `invoke` đầu tiên, vì đoạn code gọi `invoke` **trước khi setAccessible**.

Nếu sở hữu module library, một biến thể khai báo hẹp trong descriptor thay vì launcher flag là:

~~~java
module library.mod {
    exports sample.lib;
    opens sample.lib to app.mod;
}
~~~

Đây là **descriptor thay thế để hiểu ý**, không được dùng đồng thời với descriptor cũ. Chỉ mở package khi ứng dụng có lý do thực sự cần deep reflection; package private là một phần internal design contract.

## 11. ClassLoader và lỗi package-private access

Với custom class loaders, “cùng package trong source” có thể đánh lừa:

~~~text
Source of Host.class:    package tools;
Source of Helper.class:  package tools;

Host.class  -> defined by HostLoader
Helper.class -> defined by PluginLoader

Cùng package name?        Có
Cùng runtime package?     Không mặc nhiên
Có quyền package-private? Không chỉ nhờ tên giống
~~~

Theo JVM, runtime class identity phụ thuộc **binary name và defining loader**, còn runtime package gắn với package name và defining loader. Vì vậy package-private access trong bytecode có thể thất bại khi một application server hoặc plugin framework tách hai classes thuộc một source package sang loaders khác.

Trong Java 9+, module ownership và access rules cũng phải được xét; loader là một phần của câu chuyện, không phải toàn bộ.

Để giảm lỗi:

- Đặt **shared API/DTO/annotation/exception types** ở common parent loader/module.
- Không child-first một cách vô điều kiện cho package chứa các class vốn cần cùng runtime package access.
- Tránh copy JAR chứa API shared vào plugin fat JAR nếu loader có thể define lại types ấy.
- In `clazz.getClassLoader()`, `clazz.getModule()` và `clazz.getPackageName()` để quan sát thực tế.
- Đừng cho rằng sửa `setAccessible(true)` của một Method giúp lời gọi **bytecode trực tiếp** có quyền package-private; đó là hai đường truy cập khác nhau.

Một helper chẩn đoán:

~~~java
static void describe(Class<?> c) {
    System.out.println("name=" + c.getName());
    System.out.println("loader=" + c.getClassLoader());
    System.out.println("module=" + c.getModule());
}
~~~

Đây là **đoạn minh họa trong một class Java**. Nó không tự kiểm tra module graph đầy đủ, nhưng giúp nhận ra các Class cùng tên/khác defining loader.

## 12. Kiểm tra runtime module access thay vì đoán

Module API Java 17 cho phép quan sát:

~~~java
Module caller = Caller.class.getModule();
Module target = Target.class.getModule();

System.out.println("canRead: "
        + caller.canRead(target));
System.out.println("exported: "
        + target.isExported(Target.class.getPackageName(), caller));
System.out.println("opened: "
        + target.isOpen(Target.class.getPackageName(), caller));
~~~

Đây là **mã minh họa** với hai classes được định nghĩa. Nó giúp phân biệt:

- `canRead`: caller module có đọc target module không?
- `isExported`: package có được export tới caller không?
- `isOpen`: package có được open tới caller không?

Ngay cả khi `isOpen` true, Java source bình thường cũng không được tự do gọi private method. **Open giúp reflective suppression theo quy tắc**, không thay Java visibility của member ở code source.

Một số reflection APIs có quy tắc caller module readability đặc biệt (ví dụ `AccessibleObject` giả định readability trong một số access checks); đừng kết luận `canRead(false)` luôn làm `Method.invoke` báo đúng một loại exception mà không xét API cụ thể.

## 13. Những lớp lỗi liên quan nhưng khác nghĩa

| Lỗi | Ý nghĩa phổ biến |
| --- | --- |
| `ClassNotFoundException` | Loader được hỏi không tìm thấy class theo binary name |
| `NoClassDefFoundError` | JVM không có được một định nghĩa cần thiết hoặc class đã thất bại khi initialize |
| `NoSuchMethodError` | Bytecode mong một method name/descriptor nhưng runtime definition không có |
| `NoSuchFieldError` | Tương tự với field |
| `IllegalAccessError` | Reference tồn tại nhưng caller không có quyền truy cập theo JVM |
| `IllegalAccessException` | Reflection/method-handle lookup bị access check từ chối |
| `InaccessibleObjectException` | Yêu cầu bật reflective access suppression bị từ chối |
| `ClassCastException` | Một object không tương thích runtime type; có thể liên quan duplicate loaders |
| `InvocationTargetException` | Wrapper khi method được gọi qua reflection tự ném exception |
| `ExceptionInInitializerError` | Class static initialization thất bại |
| `LinkageError` | Nhóm errors khi linking, có `IllegalAccessError` là một subclass |
| `SecurityException` | Quyền truy cập bị chặn bởi một runtime security mechanism theo cấu hình |

Không nên đổi tên exception bằng cách catch rồi rethrow ngẫu nhiên. Khi gói lỗi trong framework, giữ nguyên cause/stack trace để phân biệt **missing symbol, wrong loader, access violation, deep reflection denied**.

## 14. Những sai lầm phổ biến khi sửa lỗi

### Sai lầm 1: “Thêm setAccessible(true) sẽ sửa IllegalAccessError”

Sai. Direct bytecode access không đi qua Method object mà bạn vừa thay accessible flag. Nếu runtime API đã giảm visibility, cần sửa dependency hoặc biên dịch lại client với hợp đồng mới.

### Sai lầm 2: “exports là mở private fields”

Sai. Exports cho public API theo module access. Deep reflection đối với private member từ module khác thường cần `opens`, không chỉ `exports`.

### Sai lầm 3: “trySetAccessible trả false nghĩa là JVM có lỗi”

Không. False là kết quả hợp lệ khi không được phép suppress checks. Có thể fallback sang public API hoặc báo lỗi cấu hình rõ ràng.

### Sai lầm 4: “Cùng package text thì được package-private”

Sai trong môi trường khác defining loader. Kiểm tra runtime package và loader graph thực tế.

### Sai lầm 5: “Mọi lỗi khi Method.invoke đều là IllegalAccessException”

Sai. Nếu target method được gọi và body ném exception, wrapper là `InvocationTargetException`; nếu argument sai có thể `IllegalArgumentException`, receiver null với instance method có thể `NullPointerException`, v.v.

### Sai lầm 6: “Chỉ cần --add-opens toàn bộ JDK là xong”

Không nên. Việc mở rộng reflection access tăng phụ thuộc vào internal implementation và giảm ranh giới encapsulation. Ưu tiên cập nhật thư viện và dùng public APIs; nếu cần migration, cấp quyền hẹp đúng module/package.

### Sai lầm 7: “IllegalAccessError nên catch (Exception)”

`IllegalAccessError` kế thừa `Error`, không phải `Exception`. Một catch kiểu `Exception` sẽ không bắt nó. Catch đúng loại Error trong test hay ranh giới plugin để ghi log có thể hợp lý; không nên coi catch là phương án sửa deployment.

## 15. Quy trình điều tra lỗi trong ứng dụng thực tế

1. **Đọc tên exception đầy đủ và dòng stack trace đầu**: direct bytecode access, Method.invoke hay AccessibleObject.setAccessible?
2. **Chụp lại lệnh chạy thực tế**: `-cp`, `--module-path`, `--module`, `--add-exports`, `--add-opens` và plugin class loaders.
3. **Xem classfile được JVM nạp thật**: JAR version nào, class loader nào, module nào?
4. **Đối chiếu compile/runtime dependencies**: một API đã đổi access modifiers chưa?
5. **Nếu IllegalAccessError**, kiểm tra symbolic method/field access, class/interface visibility, runtime package identity và exported package.
6. **Nếu IllegalAccessException**, kiểm tra declaring class/member modifier và caller của reflection operation.
7. **Nếu InaccessibleObjectException**, tìm package/module mà framework cố open; xác định owner có `opens` tới caller không.
8. **Phân biệt access error với missing method/field**: `NoSuchMethodError` và `NoSuchFieldError` cần sửa binary version/signature.
9. **Nếu cần reflection**, ưu tiên public accessor, `trySetAccessible` để phát hiện graceful failure, và mở module hẹp nếu thực sự cần.
10. **Kiểm thử lại trong đúng runtime environment**, không chỉ IDE với một classpath khác.

Một số lệnh hỗ trợ:

~~~bash
jar --list --file library.jar
javap -classpath library.jar -p api.Library
javap -classpath out -c -p client.Main
~~~

Các lệnh là **mẫu**, giả định JAR/classes có thật. `javap -p` xem private/package-private members ở classfile runtime, `javap -c` xem bytecode callsite đã biên dịch. Đừng dựa chỉ vào source mới nhất mà không kiểm tra **artifact thực đang chạy**.

Khi chạy OpenJDK/HotSpot, có thể bật class loading logs:

~~~bash
java -Xlog:class+load=info -cp out client.Main
~~~

Output logs phụ thuộc JDK/JVM và có thể rất dài, nên không có một transcript cố định.

## 16. Strong encapsulation khi chuyển từ Java 8 lên Java 17

Một tình huống phổ biến: framework cũ gọi `setAccessible(true)` trên private fields thuộc classes của JDK. Trong Java 8, JPMS chưa tồn tại. Từ Java 9, các packages JDK được tổ chức thành named modules; trong giai đoạn chuyển tiếp từng có những tùy chọn compatibility.

**Java 17 mặc định mạnh tay encapsulate internals của JDK**. Vì vậy reflection vào private members của `java.base` (chẳng hạn nội bộ `java.lang.String`) có thể báo `InaccessibleObjectException` nếu package chưa open thích hợp. Đối với ứng dụng classpath, một flag có thể xuất hiện trong migration logs:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar main.Main
~~~

Đây chỉ là **minh họa cú pháp** cần artifact/main thực tế; không khuyến nghị bật rộng khi có public API thay thế. `ALL-UNNAMED` chỉ các unnamed modules. Nếu caller là một **named module**, nên chọn chính tên module đích được cho phép.

`--illegal-access` từng phục vụ quá trình migration ở các bản JDK cũ, nhưng trong **Java 17** không còn cách dùng hữu hiệu để bật deep reflection mặc định; không dựa vào nó để sửa hệ thống mới.

## 17. Test matrix nên có trong thư viện và plugin framework

| Tình huống test | Kết quả cần quan sát |
| --- | --- |
| Client biên dịch với public API v1, chạy với v1 | Gọi thành công |
| Giữ Client.class v1, thay Library.class v2 giảm visibility | `IllegalAccessError` |
| Reflection gọi private method khi chưa suppress access | `IllegalAccessException` |
| Reflection trong cùng module, trySetAccessible hợp lệ | Trả true; invoke có thể thành công |
| Named module exports nhưng không opens, gọi private bằng invoke | `IllegalAccessException` |
| Named module exports nhưng không opens, gọi setAccessible(true) | `InaccessibleObjectException` |
| Mở package đúng target module rồi setAccessible | Thành công; invoke sau đó được |
| Hai classes cùng package source nhưng khác defining loader | Không tự cho package-private access |
| Plugin fat JAR có duplicated shared API | Kiểm tra correct defining loader và identity |
| Runtime dùng module path khác IDE | Kiểm tra exports/opens/readability và launcher arguments |
| Framework reflection vào JDK internals trên Java 17 | Đánh giá public API hoặc migration flag hẹp |
| Method body ném exception qua Method.invoke | `InvocationTargetException.getCause()` giữ lỗi thật |

Các tests này giúp phân biệt **lỗi linkage, lỗi reflection access và lỗi JPMS encapsulation** thay vì vá ngẫu nhiên một exception message.

## 18. Tự kiểm tra

**1. `IllegalAccessError` là checked exception?** Không; là Error thuộc nhánh IncompatibleClassChangeError/LinkageError.

**2. Vì sao code chạy với lib v1 nhưng lỗi khi chỉ thay lib v2?** Client bytecode được compile theo access contract v1, nhưng runtime definition v2 có visibility không tương thích.

**3. `IllegalAccessException` thường đến từ API nào?** Method.invoke, Field.get/set, Constructor.newInstance và một số APIs lookup tương ứng khi caller thiếu quyền.

**4. `InaccessibleObjectException` hay phát sinh ở đâu?** AccessibleObject.setAccessible(true) khi suppression bị từ chối, ví dụ package named module không opens tới caller.

**5. `getDeclaredMethod` tìm thấy private method có nghĩa gọi được không?** Không; metadata lookup và invocation access là hai thao tác khác nhau.

**6. `trySetAccessible()` trả false có giúp bypass access checks không?** Không. False báo suppression không được phép.

**7. `exports p` đủ gọi private method của p qua deep reflection?** Không thông thường; cần opens phù hợp hoặc caller có quyền hợp lệ theo API rules.

**8. `--add-opens` tự sửa IllegalAccessError do direct call tới method package-private?** Không; nó không biến private/package-private thành public cho direct bytecode access.

**9. Hai Class cùng source package do hai loaders khác nhau định nghĩa có tự là cùng runtime package không?** Không.

**10. InvocationTargetException khác IllegalAccessException thế nào?** Cái đầu bọc exception được ném **trong method đã được gọi**; cái sau ngăn invoke vì caller không có quyền.

**11. Nếu gặp lỗi truy cập khi chạy Java 17 mà Java 8 không gặp, kiểm tra gì?** JPMS strong encapsulation, opens/exports, runtime JDK và framework reflection vào JDK internals.

**12. `catch (Exception)` bắt được IllegalAccessError không?** Không, vì IllegalAccessError là Error.

**13. Khi một class có public method nhưng top-level class package-private, caller package khác có luôn gọi được không?** Không; quyền truy cập declaring class cũng được kiểm tra.

**14. Có nên mở mọi package cho mọi unnamed module để tiện debug không?** Không; hãy cập nhật code/library, chọn public API và chỉ mở scope cần thiết.

**15. Cần xác định gì ở một stack trace có custom class loader?** Binary caller/target, defining loaders, module membership, dependency version và runtime package identity.

## 19. Tài liệu chuẩn

- Java 17, **IllegalAccessError**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessError.html
- Java 17, **IllegalAccessException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html
- Java 17, **InaccessibleObjectException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- Java 17, **AccessibleObject** — `setAccessible`, `trySetAccessible`, `canAccess`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java 17, **Method** — `invoke` và checked access errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java 17, **Module** — readability, exported/open packages: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java 17, **ClassLoader** — defining loaders và delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JLS 17 `6.6 — Access Control: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6
- JVMS 17 `5.4.4 — Access Control: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- JLS 17 `13 — Binary Compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- Oracle JDK 17 Migration Guide — Strong Encapsulation: https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html
