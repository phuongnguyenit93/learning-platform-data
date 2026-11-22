# 5.2 Kiểm tra `public`, `protected`, package-private và `private` trong lời gọi động

**Ngữ cảnh:** Java Advance → dynamic-runtime → 5. Quyền truy cập.

Gọi phương thức bằng reflection, proxy hoặc cơ chế nạp động không làm biến mất các quy tắc truy cập của Java. Một chương trình có thể **tìm thấy** một `Method` đại diện cho thành viên `private`, nhưng vẫn bị từ chối khi gọi; một phương thức khai báo `public` vẫn có thể không gọi được nếu **class khai báo** nó không truy cập được; và `setAccessible(true)` chỉ có tác dụng khi ranh giới module cho phép. Bài này tập trung vào kiểm tra quyền khi thực hiện lời gọi động trong Java 17+.

## 1. Hai việc độc lập: phát hiện thành viên và được phép sử dụng thành viên

Cần tách hai câu hỏi:

1. **Có thể tìm ra metadata của thành viên không?** `Class.getMethod(...)`, `getDeclaredMethod(...)`, `getMethods()` và `getDeclaredMethods()` cho phép tìm thành viên theo những tập phạm vi khác nhau.
2. **Mã đang gọi có được quyền truy cập thành viên đó không?** Khi thực hiện `Method.invoke(receiver, args...)`, reflection kiểm tra quyền truy cập của **caller thực hiện lời gọi**, class khai báo phương thức, visibility của thành viên, ngữ cảnh package/module và receiver phù hợp. Nếu quyền không đủ, việc gọi có thể ném `IllegalAccessException`.

Ví dụ một class khai báo:

```java
package api;

public class AccessTarget {
    public String everyone() { return "public"; }
    protected String descendants() { return "protected"; }
    String neighbors() { return "package"; }
    private String secret() { return "private"; }
}
```

Hai API tìm kiếm có ý nghĩa khác nhau:

| API | Tìm thấy gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `getMethod(name, types...)` | Phương thức `public` nhìn thấy trong hệ phân cấp kiểu; có thể là phương thức kế thừa | Không bảo đảm class khai báo và method **truy cập được từ caller** |
| `getMethods()` | Danh sách phương thức `public`, gồm phương thức kế thừa phù hợp | Không nói các phương thức đó chắc chắn `invoke` thành công |
| `getDeclaredMethod(name, types...)` | Phương thức khai báo **trực tiếp** trên class, bất kể `public`/`protected`/package-private/`private` | Không tìm phương thức chỉ có ở superclass; cũng không tự cấp quyền gọi |
| `getDeclaredMethods()` | Danh sách phương thức khai báo trực tiếp, mọi mức visibility | Metadata có thể đọc không đồng nghĩa được phép chạy |
| `Method.invoke(receiver, args...)` | Thực hiện lời gọi đối với `Method` **đã chọn** | Có kiểm tra quyền runtime trừ khi được phép suppress access checks |

Ví dụ:

```java
Method visible = AccessTarget.class.getMethod("everyone");
Method privateMethod = AccessTarget.class.getDeclaredMethod("secret");
```

Đoạn trên là **snippet minh họa** trong chương trình đã import `java.lang.reflect.Method` và `api.AccessTarget`. Nó tìm được cả hai phương thức, nhưng thành viên `private` chưa tự động trở nên gọi được.

**Điểm quan trọng:** Lookup `getMethod("secret")` thất bại với `NoSuchMethodException` vì `secret` không `public`; lookup `getDeclaredMethod("secret")` thành công vì class khai báo trực tiếp phương thức đó. Lỗi khi **tìm** và lỗi khi **gọi** là hai giai đoạn khác nhau.

## 2. Bốn mức truy cập khi gọi động

Giả sử class `api.AccessTarget` là `public` và các class phía gọi nằm ở package `api` hoặc package khác là `client`.

| Modifier của phương thức | Gọi từ class khác cùng runtime package | Gọi từ class không phải subclass ở package khác | Gọi từ subclass ở package khác |
| --- | --- | --- | --- |
| `public` | Được, nếu class và module cho phép | Được, nếu class và module cho phép | Được, nếu class và module cho phép |
| `protected` | Được | Không được nếu chỉ là caller không có quan hệ kế thừa | Có điều kiện: caller là subclass; với instance member, **receiver phải đáp ứng quy tắc protected** |
| Không ghi modifier (package-private) | Được | Không | Không, chỉ kế thừa không tạo quyền truy cập package-private xuyên package |
| `private` | Không, trừ khi caller có quyền private phù hợp (ví dụ cùng nest) | Không | Không: subclass không tự có quyền truy cập `private` của parent |

Các cột giả định không bật `setAccessible(true)` và không gặp hạn chế module bổ sung. Hai nguyên tắc cần nhớ:

- **Package-private** (còn gọi là package access) là trường hợp **không có** modifier visibility trước thành viên. Nó không phải một từ khóa `package-private` trong source.
- **`protected` khi ở package khác không phải "subclass được gọi trên bất kỳ receiver nào"**. Với instance method của superclass, caller là subclass chỉ được truy cập qua receiver có kiểu thích hợp (thường là chính subclass đó hoặc subtype); không được lấy bất kỳ instance superclass rồi gọi một cách tùy ý.

Cách JVM hiểu **cùng runtime package** còn phụ thuộc class loader định nghĩa: về cơ bản dùng **(package name, defining class loader)**. Hai class cùng ghi `package api;` nhưng do hai defining loader khác nhau định nghĩa không mặc nhiên có đặc quyền package-private với nhau. Trong JPMS, module exports/opens bổ sung rào chắn truy cập liên module.

### `public`: thành viên công khai nhưng class có thể bị ẩn

Khi class `PackageHidden` là package-private còn phương thức `display()` là `public`, code package khác có thể nhận một đối tượng `Object` rồi dùng `getClass().getMethod("display")` để lấy metadata. Tuy vậy, `Method.invoke` vẫn có thể ném `IllegalAccessException`, vì **class khai báo** phương thức không công khai đối với caller. Đặt `public` trước method không biến class bao nó thành `public`.

### `protected`: kiểm tra quyền subclass và receiver

Với `AccessTarget.descendants()` được khai báo `protected`:

- Một class ở package `api` khác có thể gọi qua instance `AccessTarget` phù hợp.
- `client.Demo` không phải subclass nên bị từ chối.
- `client.SubclassProbe extends AccessTarget` có thể dùng `descendants()` trên chính `this`.
- Ngay trong subclass, cố gọi cùng method qua một đối tượng **`new AccessTarget()`** vẫn có thể bị từ chối vì receiver không thuộc subclass phù hợp.

Phân biệt **kế thừa method**, **được phép truy cập method**, và **kiểu receiver**. Đối với `protected static` có các quy tắc truy cập tương ứng nhưng không có receiver instance; ví dụ ở bài này dùng instance method để làm rõ ràng buộc receiver.

### `private`: giới hạn class/nest, không phải toàn package

`private` không được truy cập chỉ vì caller cùng package hoặc là subclass. Java 11+ có khái niệm **nestmates** (các class cùng nest, ví dụ outer class và nested class thích hợp), vốn có quyền truy cập private của nhau mà không phải gọi `setAccessible`. Vì thế diễn đạt chính xác là "private dành cho class và các thành viên nest được phép", chứ không phải "mọi class khác tuyệt đối không thể truy cập".

Đối với class thông thường nằm ngoài nest, `getDeclaredMethod` có thể đọc metadata của phương thức `private` nhưng `invoke` chưa được phép thực thi nếu chưa được cấp khả năng suppress checks hợp lệ.

## 3. Chương trình Java 17 chạy độc lập: kiểm tra cả bốn mức quyền

Tạo cấu trúc thư mục và năm file như sau. Ví dụ cố ý dùng **hai package** trên **classpath (unnamed module)** để tách quyền theo Java language access khỏi các hạn chế module; phần JPMS sẽ được kiểm chứng riêng ở mục 6.

```text
access-demo/
├── api/
│   ├── AccessTarget.java
│   ├── SamePackage.java
│   └── PublicFactory.java
└── client/
    ├── SubclassProbe.java
    └── Demo.java
```

### File `api/AccessTarget.java`

```java
package api;

public class AccessTarget {
    public String everyone() { return "public"; }
    protected String descendants() { return "protected"; }
    String neighbors() { return "package"; }
    private String secret() { return "private"; }
}
```

### File `api/SamePackage.java`

Code gọi nằm trong **cùng package `api`** với class đích:

```java
package api;

import java.lang.reflect.Method;

public final class SamePackage {
    public static void check(AccessTarget target) throws Exception {
        Method protectedMethod = AccessTarget.class.getDeclaredMethod("descendants");
        Method packageMethod = AccessTarget.class.getDeclaredMethod("neighbors");
        Method privateMethod = AccessTarget.class.getDeclaredMethod("secret");

        System.out.println("same-package protected=" + protectedMethod.invoke(target));
        System.out.println("same-package package=" + packageMethod.invoke(target));
        try {
            privateMethod.invoke(target);
        } catch (IllegalAccessException expected) {
            System.out.println("same-package private=IllegalAccessException");
        }
    }
}
```

### File `client/SubclassProbe.java`

Subclass ở **package khác** dùng quyền `protected` đúng với receiver là `this`, nhưng không thể dùng quyền đó để gọi trên một instance `AccessTarget` bất kỳ:

```java
package client;

import api.AccessTarget;
import java.lang.reflect.Method;

public class SubclassProbe extends AccessTarget {
    public void check() throws Exception {
        System.out.println("subclass direct=" + descendants());

        Method method = AccessTarget.class.getDeclaredMethod("descendants");
        System.out.println("subclass this=" + method.invoke(this));
        try {
            method.invoke(new AccessTarget());
        } catch (IllegalAccessException expected) {
            System.out.println("subclass base-instance=IllegalAccessException");
        }
    }
}
```

### File `api/PublicFactory.java`

Phương thức `public` nằm bên trong class `PackageHidden` vốn **không `public`**:

```java
package api;

class PackageHidden {
    public String display() {
        return "public method in package-private class";
    }
}

public class PublicFactory {
    public static Object hidden() {
        return new PackageHidden();
    }
}
```

### File `client/Demo.java`

```java
package client;

import api.AccessTarget;
import api.PublicFactory;
import api.SamePackage;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class Demo {
    private static void attempt(String label, Method method, Object receiver)
            throws InvocationTargetException {
        try {
            System.out.println(label + "=" + method.invoke(receiver));
        } catch (IllegalAccessException expected) {
            System.out.println(label + "=IllegalAccessException");
        }
    }

    public static void main(String[] args) throws Exception {
        AccessTarget target = new AccessTarget();
        Method publicMethod = AccessTarget.class.getMethod("everyone");
        Method protectedMethod = AccessTarget.class.getDeclaredMethod("descendants");
        Method packageMethod = AccessTarget.class.getDeclaredMethod("neighbors");
        Method privateMethod = AccessTarget.class.getDeclaredMethod("secret");

        attempt("other-package public", publicMethod, target);
        attempt("other-package protected", protectedMethod, target);
        attempt("other-package package", packageMethod, target);
        attempt("other-package private", privateMethod, target);

        try {
            AccessTarget.class.getMethod("secret");
        } catch (NoSuchMethodException expected) {
            System.out.println("getMethod private=NoSuchMethodException");
        }

        SamePackage.check(target);
        new SubclassProbe().check();

        System.out.println("private canAccess before=" + privateMethod.canAccess(target));
        System.out.println("private trySetAccessible=" + privateMethod.trySetAccessible());
        System.out.println("private canAccess after=" + privateMethod.canAccess(target));
        attempt("private after override", privateMethod, target);

        System.out.println("package trySetAccessible=" + packageMethod.trySetAccessible());
        attempt("package after override", packageMethod, target);

        Object hidden = PublicFactory.hidden();
        Method onHidden = hidden.getClass().getDeclaredMethod("display");
        attempt("public method on hidden class", onHidden, hidden);
        System.out.println("hidden trySetAccessible=" + onHidden.trySetAccessible());
        attempt("hidden after override", onHidden, hidden);
    }
}
```

Từ thư mục `access-demo/`, sử dụng JDK 17+ và biên dịch ở mức Java 17:

```bash
javac --release 17 -encoding UTF-8 -d out api/AccessTarget.java api/SamePackage.java api/PublicFactory.java client/SubclassProbe.java client/Demo.java
java -cp out client.Demo
```

**Stdout chính xác:**

```text
other-package public=public
other-package protected=IllegalAccessException
other-package package=IllegalAccessException
other-package private=IllegalAccessException
getMethod private=NoSuchMethodException
same-package protected=protected
same-package package=package
same-package private=IllegalAccessException
subclass direct=protected
subclass this=protected
subclass base-instance=IllegalAccessException
private canAccess before=false
private trySetAccessible=true
private canAccess after=true
private after override=private
package trySetAccessible=true
package after override=package
public method on hidden class=IllegalAccessException
hidden trySetAccessible=true
hidden after override=public method in package-private class
```

**Đọc kết quả theo từng ranh giới:**

1. `client.Demo` ở ngoài `api` chỉ gọi được `everyone()` theo quyền truy cập thông thường. Reflection tìm được metadata của ba phương thức còn lại, nhưng `invoke` từ `Demo` bị `IllegalAccessException`.
2. `getMethod("secret")` ném `NoSuchMethodException`, vì API này tìm phương thức `public`. Sự tồn tại của `secret` được xác nhận bằng `getDeclaredMethod("secret")`; hai thao tác lookup có phạm vi khác nhau.
3. `api.SamePackage` gọi được `protected` và package-private qua reflection nhờ cùng runtime package; vẫn không gọi được `private` vì không phải cùng nest/caller có quyền.
4. `client.SubclassProbe` gọi được `descendants()` trên `this` cả bằng cú pháp Java trực tiếp lẫn `Method.invoke`. Nhưng receiver là `new AccessTarget()` không đáp ứng điều kiện đối với instance `protected` ở package khác.
5. `privateMethod.canAccess(target)` ban đầu là `false`. Trong ví dụ **unnamed module**, `trySetAccessible()` được phép bật suppress access checks, sau đó `canAccess(target)` là `true` và lời gọi `private` thành công.
6. `PublicFactory.hidden()` trả về instance của class package-private. Method `display()` có modifier `public`, nhưng caller bên ngoài không truy cập được **class** `PackageHidden`, nên `invoke` ban đầu thất bại. Với `trySetAccessible()` được phép trong unnamed module, lời gọi tiếp theo thành công.

Đây là ví dụ về **language access checks** và suppress-access checks trong môi trường classpath. Kết quả `trySetAccessible=true` sẽ không đúng ở mọi chương trình JPMS: cần xét quyền `opens`/`exports` của named module.

## 4. `canAccess`, `trySetAccessible` và `setAccessible` dùng đúng mục đích

`AccessibleObject` là superclass của `Method`, `Constructor` và `Field`. Ba thao tác hay gặp có ý nghĩa khác nhau:

| API | Ý nghĩa | Kết quả/ngoại lệ |
| --- | --- | --- |
| `method.canAccess(receiver)` | Hỏi **ngay tại caller hiện hành** liệu method có thể được truy cập với receiver này hay không, xét trạng thái suppress checks hiện tại | Trả `boolean`; có thể ném `IllegalArgumentException` nếu receiver không hợp lệ |
| `method.trySetAccessible()` | **Thử bật** suppress Java language access checks nếu module và quyền hiện tại cho phép | `true` nếu thành công; `false` khi không thể bật vì module không mở phù hợp; có thể có `SecurityException` trong môi trường có SecurityManager áp dụng |
| `method.setAccessible(true)` | Yêu cầu bật suppress checks | Thành công nếu được phép; nếu vi phạm encapsulation của module có thể ném `InaccessibleObjectException` (unchecked); môi trường kiểm soát bảo mật có thể ném `SecurityException` |

Không dùng `setAccessible(true)` chỉ để **khám phá** quyền; hãy thử `canAccess(receiver)` khi cần biết lời gọi bình thường có được phép. `trySetAccessible()` thường tốt hơn khi cần thử reflective access không được bảo đảm trước, vì nó biểu đạt rõ kết quả cho tình huống module không cho phép.

Ví dụ sử dụng để kiểm soát lỗi trong code hiện hữu (snippet, **không phải chương trình độc lập**):

```java
Method method = target.getClass().getDeclaredMethod("secret");
if (method.canAccess(target)) {
    Object result = method.invoke(target);
    System.out.println(result);
} else if (method.trySetAccessible()) {
    Object result = method.invoke(target);
    System.out.println(result);
} else {
    throw new IllegalStateException("Module/package does not allow deep reflection");
}
```

**Không suy luận sai từ `canAccess`:** với instance method, truyền receiver phải là đối tượng tương thích; với static method, tham số `receiver` để `canAccess` là `null`. Cả `setAccessible` và `trySetAccessible` đều **không** sửa bytecode, không thay modifier gốc và không cấp quyền truy cập vô điều kiện giữa các named module. Việc suppress check áp dụng cho đối tượng `Method`/`Field`/`Constructor` tương ứng; không có nghĩa toàn bộ chương trình tự được cấp cùng quyền.

**Một góc đặc biệt với `private`:** nếu caller và declaring class là nestmates, `canAccess` có thể là `true` ngay cả khi chưa gọi `trySetAccessible`. Trái lại, ở ví dụ `SamePackage`, hai class chỉ chung package, nên `private` vẫn bị từ chối.

## 5. Mỗi kiểu kiểm tra xảy ra tại một thời điểm khác nhau

Trình tự thường thấy khi gọi method qua reflection:

```text
Class<?> / tên class
      |
      v
getMethod / getDeclaredMethod
      |  lookup tên + chữ ký: NoSuchMethodException nếu không thấy
      v
Method metadata
      |
      v
canAccess / trySetAccessible (nếu cần)
      |  kiểm tra caller, visibility, runtime package, module
      v
method.invoke(receiver, args...)
      |  IllegalAccessException nếu không có quyền
      |  IllegalArgumentException nếu receiver/đối số không tương thích
      |  NullPointerException nếu instance receiver là null
      v
Thân method chạy
      |  ngoại lệ do code đích ném → InvocationTargetException
      v
Giá trị trả về (boxed nếu trả primitive)
```

Bảng phân biệt lỗi:

| Lỗi | Giai đoạn | Ý nghĩa thực tế |
| --- | --- | --- |
| `NoSuchMethodException` | Lookup | Không có member khớp tên, loại lookup, danh sách kiểu tham số; **không phải** lỗi thiếu quyền invoke |
| `IllegalAccessException` | `Method.invoke` / `Constructor.newInstance` | Caller không đủ quyền theo visibility hoặc module |
| `InaccessibleObjectException` | `setAccessible(true)` | Java module system không cho suppress checks với thành viên/package này |
| `IllegalArgumentException` | `invoke` | Receiver không thuộc kiểu phù hợp, sai số tham số/kiểu tham số hoặc chuyển đổi đối số không hợp lệ |
| `NullPointerException` | `invoke` instance method với receiver null | Không có instance đích; với static method, receiver null được phép |
| `InvocationTargetException` | Body của method/constructor đã chạy | Exception do code đích ném được bọc lại; xem `getCause()` |
| `IllegalAccessError` | Linkage của bytecode đã biên dịch | Một lỗi linkage trong truy cập trực tiếp/JVM, **khác** checked `IllegalAccessException` của core reflection |

Sự khác biệt giữa `IllegalAccessException` và `InvocationTargetException` rất hữu ích: lỗi `IllegalAccessException` là thiếu quyền **trước khi thực thi thân method**; nếu thân method tự ném `IllegalArgumentException`, caller của reflection sẽ thấy `InvocationTargetException` với cause `IllegalArgumentException`.

Một phương thức `public` có thể được lookup thành công nhưng `invoke` vẫn thất bại do declaring class không public hoặc package không được module export. Vì thế đừng suy luận chỉ từ `Modifier.isPublic(method.getModifiers())`; phải xét **class**, **caller**, **receiver**, **runtime package**, **module**.

## 6. Java Platform Module System: `exports` khác `opens`

Với Java 9+ (bao gồm Java 17), **named module** bổ sung kiểm soát truy cập ngoài visibility của ngôn ngữ:

- `exports p`: cho phép module khác truy cập **public types** trong package `p` và public/protected members được phép theo Java language rules; không tự cho quyền gọi private qua deep reflection.
- `opens p`: cho phép module khác **deep reflection** vào package `p`, trong phạm vi API reflective checks tương ứng, kể cả khai báo non-public khi suppress access checks hợp lệ; không tự biến class non-public thành Java API cho cú pháp tham chiếu trực tiếp.
- `opens p to m`: mở package `p` riêng cho module `m`.
- Trong **unnamed module** (classpath), các package mở cho deep reflection theo cơ chế module mặc định; vì vậy demo mục 3 có thể `trySetAccessible() == true`.
- Với **named module**, muốn dùng `setAccessible(true)` để vượt qua kiểm tra language access của thành viên non-public ở module khác, package phải được mở phù hợp (hoặc thỏa điều kiện khác mà API cho phép, như cùng module). `exports` một mình không đủ.

Ví dụ module có thể mô tả ý định:

```java
module inventory.core {
    exports inventory.api;
    opens inventory.internal to inventory.tools;
}
```

Đoạn `module-info.java` này là **minh họa**; dự án hoàn chỉnh phải thực sự có các package/module nêu trên. `inventory.tools` được deep reflection vào `inventory.internal`, còn module khác không mặc nhiên có quyền đó. `exports inventory.api` dành cho API công khai.

### Thí nghiệm named module: cùng phương thức, khác quyền mở package

Tạo cấu trúc dự án thứ hai:

```text
modules-demo/
└── src/
    ├── alpha/
    │   ├── module-info.java
    │   └── alpha/
    │       └── PublicApi.java
    └── beta/
        ├── module-info.java
        └── beta/
            └── Main.java
```

**File `src/alpha/module-info.java`:**

```java
module alpha {
    exports alpha;
}
```

**File `src/alpha/alpha/PublicApi.java`:**

```java
package alpha;

class Hidden {
    public String message() { return "hidden"; }
}

public class PublicApi {
    public static Object hidden() { return new Hidden(); }
}
```

**File `src/beta/module-info.java`:**

```java
module beta {
    requires alpha;
}
```

**File `src/beta/beta/Main.java`:**

```java
package beta;

import alpha.PublicApi;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        Object hidden = PublicApi.hidden();
        Method method = hidden.getClass().getMethod("message");
        try {
            System.out.println("invoke=" + method.invoke(hidden));
        } catch (IllegalAccessException expected) {
            System.out.println("invoke=IllegalAccessException");
        }

        System.out.println("trySetAccessible=" + method.trySetAccessible());
        try {
            method.setAccessible(true);
            System.out.println("setAccessible=success");
        } catch (InaccessibleObjectException expected) {
            System.out.println("setAccessible=InaccessibleObjectException");
        }

        if (method.canAccess(hidden)) {
            System.out.println("after-open=" + method.invoke(hidden));
        }
    }
}
```

Biên dịch theo Java 17 từ thư mục `modules-demo/`:

```bash
javac --release 17 --module-source-path src -d out src/alpha/module-info.java src/alpha/alpha/PublicApi.java src/beta/module-info.java src/beta/beta/Main.java
java --module-path out -m beta/beta.Main
```

**Stdout khi module `alpha` chỉ `exports alpha`, chưa `opens`:**

```text
invoke=IllegalAccessException
trySetAccessible=false
setAccessible=InaccessibleObjectException
```

Dù `alpha` export package, class `Hidden` vẫn package-private. Vì vậy `getMethod("message")` tìm được phương thức public nhưng không thể invoke từ module `beta` bằng quyền truy cập thường. Đồng thời, `beta` không có quyền mở sâu package ấy, nên `trySetAccessible()` trả `false` và `setAccessible(true)` ném `InaccessibleObjectException`.

Chạy lại **không thay source** bằng quyền mở package ở JVM launch:

```bash
java --module-path out --add-opens alpha/alpha=beta -m beta/beta.Main
```

**Stdout với `--add-opens`:**

```text
invoke=IllegalAccessException
trySetAccessible=true
setAccessible=success
after-open=hidden
```

`--add-opens` cho phép `beta` thực hiện deep reflection vào package `alpha`. Lần gọi đầu vẫn thiếu quyền ngôn ngữ, nhưng sau khi `trySetAccessible()` thành công, lời gọi có thể chạy. Trong dự án thực tế, ưu tiên khai báo `opens ... to ...` rõ phạm vi theo hợp đồng module thay vì mở rộng quyền bằng JVM flags tràn lan; `--add-opens` hữu ích khi gỡ lỗi hoặc tích hợp thư viện cũ.

**Không nhầm `--add-exports` và `--add-opens`:** flag thứ nhất hỗ trợ truy cập **public API** của package không export theo cách thông thường; flag thứ hai phục vụ **deep reflection**. Chúng có mục đích khác nhau. Các module trong ví dụ có tên `alpha`, `beta`; tên lặp trong `--add-opens alpha/alpha=beta` lần lượt là **module/package=target-module**.

## 7. Những trường hợp dễ kết luận nhầm

### 7.1 `public` của method không đủ nếu class không public

`Modifier.isPublic(method.getModifiers())` có thể trả `true` với method khai báo trong class package-private. Cần xét quyền truy cập **tất cả thành phần cần thiết**, nhất là class khai báo method và module chứa nó. Chứng cứ nằm ở `public method on hidden class=IllegalAccessException` trong chương trình thứ nhất và thí nghiệm `alpha`/`beta` ở chương trình thứ hai.

### 7.2 `protected` không biến mọi object của superclass thành receiver hợp lệ

Subclass ở package khác có thể gọi `protected` instance method qua receiver phù hợp; `this` hợp lệ còn `new Superclass()` không mặc nhiên hợp lệ. Reflection thực hiện kiểm tra access với ngữ cảnh caller ở vị trí gọi `invoke`. Nếu thực thi qua helper không phải subclass, hãy xem helper đó có quyền `protected` không; quyền của subclass không tự "truyền" qua một lớp helper tùy ý.

### 7.3 Chuyển `Method` qua nơi khác không "mang theo" quyền truy cập

Đối tượng `Method` chỉ là metadata và trạng thái `AccessibleObject`. Khi chưa suppress checks, quyền được kiểm tại **caller thực hiện `invoke`**. Một helper ở package `api` gọi được `package-private` không có nghĩa mọi caller nhận cùng `Method` đều gọi được. Nếu code đã bật thành công `trySetAccessible()` cho **chính** Method đó, những lời gọi về sau có trạng thái suppress checks và cần xem xét quyền module/bảo mật. Tránh sử dụng một Method đã mở quá quyền trong API chia sẻ mà không kiểm soát.

### 7.4 Runtime package khác dù cùng chuỗi tên

Trong hệ plugin, hot reload hoặc loader tùy biến, hai class ở package có cùng tên văn bản nhưng do loader khác nhau định nghĩa thường thuộc **hai runtime package khác nhau**. Vì vậy package-private/protected trong cùng runtime package không thể suy luận qua source declaration đơn thuần. Khi gặp lỗi khó hiểu, ghi thêm `getClassLoader()` của class nguồn và class đích.

### 7.5 Reflection không tự giải quyết interface/API visibility

Một library muốn cho plugin gọi động nên chủ động thiết kế một **public API hoặc interface** ở package được export, và implementation nằm trong module/package riêng. Nếu framework cần khởi tạo private constructor hoặc inject private field, thư viện thường yêu cầu mở package bằng `opens`; việc package đã `exports` không bảo đảm quyền deep reflection.

### 7.6 Method handles có mô hình quyền riêng, không bỏ qua access rules

`java.lang.invoke.MethodHandles.Lookup` mang thông tin về **lookup class** và các access modes. `privateLookupIn` có thể tạo lookup với quyền sâu hơn khi điều kiện quyền/module phù hợp, đặc biệt liên quan `opens`. `MethodHandle.invoke`/`invokeExact` có quy tắc chữ ký và kiểu gọi riêng; không được đồng nhất chúng với `Method.invoke` hoặc coi method handle như cách "vượt bảo mật" mà không có quyền truy cập.

## 8. Checklist chẩn đoán `IllegalAccessException` trong code reflection

Khi đang gặp lỗi gọi động, kiểm tra lần lượt:

1. **Xác định đúng member và declaring class.** In `method.getDeclaringClass().getName()`, `method.getName()`, `method.getModifiers()`. `getMethod` có thể trả thành viên kế thừa không khai báo trực tiếp ở class ban đầu.
2. **Xác định caller thật:** lệnh `invoke` nằm trong package/class nào? Có phải helper bên thứ ba đang thực hiện lệnh thay cho class dự kiến?
3. **Kiểm tra class visibility:** declaring class `public` hay package-private? Class khai báo có nằm trong package cùng runtime loader không?
4. **Kiểm tra member visibility:** `public`/`protected`/package-private/`private`. Nếu `protected` xuyên package, kiểm tra subclass relationship và **kiểu receiver**.
5. **Kiểm tra module:** `method.getDeclaringClass().getModule()`. Package có `exports` đối với caller module không? Có `opens` cho deep reflection không?
6. **Dùng `canAccess(receiver)` để đo quyền thông thường** khi receiver phù hợp; nếu cần deep reflection, dùng `trySetAccessible()` và xử lý `false` có chủ đích, đừng coi nó luôn thành công.
7. **Phân biệt loại lỗi:** `NoSuchMethodException` là lookup, `IllegalAccessException` là invoke/access, `InaccessibleObjectException` là yêu cầu suppress checks thất bại, `InvocationTargetException` là code bên trong method ném lỗi.
8. **Sửa thiết kế truy cập:** ưu tiên public exported API, đúng receiver và package boundary; với framework thực sự cần private members, cấp `opens` tối thiểu cho module của framework.

Snippet quan sát trong một code đang có biến `Method m` (không phải chương trình độc lập):

```java
Class<?> owner = m.getDeclaringClass();
System.out.println("declaringClass=" + owner.getName());
System.out.println("declaringLoader=" + owner.getClassLoader());
System.out.println("declaringModule=" + owner.getModule().getName());
System.out.println("methodModifiers=" + java.lang.reflect.Modifier.toString(m.getModifiers()));
System.out.println("classModifiers=" + java.lang.reflect.Modifier.toString(owner.getModifiers()));
```

Với unnamed module, `owner.getModule().getName()` có thể là `null`. Có thể dùng `owner.getModule().isExported(packageName, callerModule)` và `isOpen(packageName, callerModule)` khi đã xác định **đúng caller module**, nhưng API này chỉ xác nhận một phần điều kiện; không thay thế kiểm tra visibility của class/member/receiver.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Code ở package khác gọi `Class.getDeclaredMethod("secret")` và nhận về `Method` cho `private secret()`. Đã có quyền gọi chưa?

**Trả lời:** Chưa. Lookup tìm thấy metadata; `invoke` vẫn kiểm tra Java access. Cần caller có quyền private phù hợp hoặc được phép suppress checks.

**Câu 2.** Một class `A` có method `public void f()`, nhưng chính `A` là package-private. Một caller ở package khác lấy được Method bằng `getMethod("f")`. `invoke` có chắc thành công?

**Trả lời:** Không. Quyền truy cập class `A` vẫn quan trọng; `public` của method chưa đủ.

**Câu 3.** `Sub extends Base` khác package với `Base`. `Base` khai báo `protected void p()`. Trong phương thức của `Sub`, gọi reflection trên `this` và trên `new Base()` có tương đương không?

**Trả lời:** Không. `this` có kiểu subclass hợp lệ; `new Base()` không đáp ứng quy tắc receiver của `protected` instance method khi caller là subclass khác package.

**Câu 4.** Có thể gọi package-private method chỉ vì hai class đều ghi `package demo;` không?

**Trả lời:** Chưa đủ để kết luận. Phải cùng **runtime package**, gắn với package name và defining class loader; JPMS còn có access controls bổ sung.

**Câu 5.** `trySetAccessible()` trả `false` và `setAccessible(true)` ném `InaccessibleObjectException` khi reflection vào một named module. Nên thử ép `invoke` nhiều lần không?

**Trả lời:** Không. Xác định module và package; nếu thiết kế cho phép deep reflection, cấu hình `opens package to target.module` hoặc cơ chế cấp quyền có phạm vi phù hợp. Lặp `invoke` không tự thay đổi quyền.

**Câu 6.** Method `private` ném `IllegalStateException` từ body khi đã được phép gọi bằng reflection. Caller thấy ngoại lệ gì?

**Trả lời:** `InvocationTargetException`, với `getCause()` là `IllegalStateException`; đây là lỗi từ thân method, không phải lỗi access.

**Câu 7.** Vì sao `getDeclaredMethods()` cho biết mọi method nhưng không có nghĩa chương trình có thể gọi mọi method?

**Trả lời:** API liệt kê **khai báo**, không cấp quyền invoke. Access được kiểm tra theo caller, member, declaring class, runtime package, receiver và module.

**Câu 8.** Nếu module `core` chỉ có `exports p;` mà không `opens p;`, module khác có thể bật `setAccessible(true)` cho mọi private method trong package `p` không?

**Trả lời:** Không. `exports` phục vụ public API. Để deep reflection từ module khác qua ranh giới named module cần thỏa những điều kiện mở package/reflective access thích hợp; `exports` không mặc nhiên cho phép private access.

## 10. Ghi nhớ

- **Tìm thấy không bằng truy cập được.** `getDeclaredMethod` tìm cả non-public, nhưng `invoke` vẫn có thể ném `IllegalAccessException`.
- **Xét đầy đủ class, method, caller, runtime package và module.** `public` ở method không bù cho declaring class không public.
- **`protected` xuyên package cần subclass và receiver hợp lệ** với instance method; kế thừa không cấp toàn quyền gọi trên superclass instances.
- **Package-private cần cùng runtime package**, không chỉ trùng chuỗi tên package.
- **`private` có quyền của class/nestmates**, không phải đặc quyền chung của package hay subclass.
- **`trySetAccessible`/`setAccessible` có giới hạn JPMS.** `exports` dành cho public API; `opens` dành cho deep reflection phù hợp.
- **Phân loại lỗi theo bước:** lookup, access, binding args và exception do code đích ném là những vấn đề khác nhau.

### Tài liệu chuẩn

- [Java SE 17 API: `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 API: `AccessibleObject.canAccess`, `trySetAccessible`, `setAccessible`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JLS Java SE 17 `6.6 Access Control, đặc biệt `6.6.2 protected access](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6)
- [Java SE 17 API: `Module` và `isOpen`/`isExported`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [JLS Java SE 17 `7.7 Module Declarations, `exports` và `opens`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)