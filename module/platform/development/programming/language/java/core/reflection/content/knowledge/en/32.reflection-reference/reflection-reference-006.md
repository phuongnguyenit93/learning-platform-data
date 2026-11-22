# Bảng quyền truy cập theo modifier, package, nest và module trong Java Reflection

## 1. Bốn tầng phải xét khi gọi một member bằng reflection

Khi sử dụng `java.lang.reflect.Method`, `Field` hoặc `Constructor`, câu hỏi “Có thể truy cập được không?” không chỉ phụ thuộc vào `public`/`protected`/`private`. Hãy phân biệt **bốn tầng**:

1. **Tìm thấy metadata**: `getMethod`/`getDeclaredMethod` hoặc `getField`/`getDeclaredField` có trả lại đối tượng phản chiếu không?
2. **Quyền ngôn ngữ Java**: modifier của member; quyền nhìn thấy declaring class; quan hệ package, subclass, và **nestmate** của caller.
3. **Ranh giới module JPMS** (Java 9+): package có được `exports` cho module cần gọi không; khi cần deep reflection, có được `opens` không?
4. **Tình trạng invocation**: receiver có đúng kiểu, đối số hợp lệ, và reflective object có cờ suppress-access-check hay không?

**Có metadata ≠ có quyền sử dụng**. Chẳng hạn, `getDeclaredMethod("secret")` có thể trả một private method, nhưng `Method.invoke` có thể ném `IllegalAccessException` khi code gọi không có quyền và chưa được cho phép suppress access check.

Bài này là **bảng tra cứu quyền truy cập** dành cho Java 17+, ưu tiên phân biệt public API contract và những yếu tố làm thay đổi kết quả theo ngữ cảnh.

## 2. Bảng tổng hợp modifier khi chưa bypass access checks

Giả định member nằm trong một **class mà caller có quyền truy cập** và package/module gates đã được đáp ứng. Bảng này nói về quyền theo Java language access control, **chưa tính `setAccessible(true)`**.

| Modifier của member | Chính class khai báo | Lớp khác cùng nest | Lớp khác cùng runtime package, không cùng nest | Subclass khác package | Lớp không liên quan khác package |
| --- | --- | --- | --- | --- | --- |
| `public` | Có | Có | Có | Có | Có |
| `protected` | Có | Có | Có | Có, **với điều kiện về receiver/qualified access** | Không |
| Không ghi modifier (*package-private*) | Có | Có | Có | Không | Không |
| `private` | Có | Có, vì *nestmate* | Không | Không, trừ khi cũng là nestmate | Không |

**Các điều kiện đọc bảng:**

- “Cùng package” về mặt runtime không phải chỉ trùng chuỗi tên package. Các class phải thuộc **cùng runtime package**, thường xét cả tên package và *defining classloader*. Hai plugin có package cùng tên nhưng do classloader riêng định nghĩa không mặc nhiên được xem là cùng runtime package.
- `protected` trong subclass **khác package** không đơn giản là được gọi trên mọi instance của superclass. Access tới instance member có điều kiện receiver: trong ngữ cảnh subclass `S`, qualified receiver nhìn chung phải thuộc `S` hoặc subclass của `S`. Quyền gọi một protected instance method trên instance thuần của superclass không tự có chỉ vì caller là subclass.
- `private` từ Java 11 có ngữ nghĩa **nest-based access control**: các class cùng nest có thể truy cập private member của nhau (khi đáp ứng ràng buộc runtime), không cần `setAccessible` chỉ vì chúng khác class.
- Access tới **declaring type** vẫn phải hợp lệ. Một public method trong một class không public không tự trở nên callable từ một class ở package khác chỉ vì method có modifier `public`.
- Với code nằm ở **named modules khác nhau**, bảng trên còn cần JPMS gate (mục 5). Module `exports` không biến member `private` hoặc package-private thành public.

### Ghi chú về package-private

Không có keyword `package-private` trong Java. Một member khai báo không có `public`, `protected` hay `private` thường có quyền package access. Ví dụ:

```java
class Example {
    String packageName() { return "default access"; }
}
```

Đây là fragment, không phải chương trình hoàn chỉnh. Quyền này **không phụ thuộc** vào tên package con: `com.app` và `com.app.tools` là **hai package khác nhau**. Cùng module nhưng khác package cũng không được tự động truy cập package-private.

## 3. Nestmate: private có thể được truy cập giữa các class cùng nest

**Nest** là nhóm class được JVM xem có cùng nest host. Với class lồng nhau (`Outer`, `Outer.Inner`, `Outer.StaticNested`), chúng thường cùng nest và được phép truy cập private member của nhau. Nest support có trong JVM từ Java 11 (JEP 181).

Các API tra cứu:

- `Class#getNestHost()`: trả class đóng vai trò nest host.
- `Class#getNestMembers()`: trả thành viên nest của class theo thông tin runtime.
- `Class#isNestmateOf(Class<?>)`: kiểm tra hai class có cùng nest hay không.

Không nên dùng phép so `getEnclosingClass()` hoặc tên class chứa dấu `$` để thay thế phép kiểm tra nestmate. Class tải động, biến thể bytecode hoặc lớp không lồng nhau theo Java source cần dựa vào runtime metadata thực tế.

**Cùng nest khác với cùng package.** Một top-level class khác nằm cùng package với `Outer` không tự được quyền gọi `Outer.Inner` private member. Ngược lại, các nestmates không cần gọi `setAccessible(true)` để thực hiện private access vốn đã được Java cho phép.

Trong reflection, checks được đánh giá với **caller class thực tế** của API nhạy với caller. Nếu `Method.invoke` được thực hiện trong một nestmate thì có thể thành công; nếu đưa cùng đối tượng `Method` sang helper top-level khác không cùng nest và gọi từ đó thì có thể nhận `IllegalAccessException`. Đừng nhầm quyền của nơi **lấy metadata** với quyền của nơi **thực hiện lời gọi**.

## 4. Ví dụ Java 17+ chạy được: same package khác same nest

Chương trình có hai top-level class trong **cùng một file**, cùng *unnamed package* cho mục đích minh họa. `AccessMatrixDemo.Vault` và `AccessMatrixDemo.NestPeer` cùng nest; `PackagePeer` là top-level class khác, cùng runtime package nhưng **khác nest**.

Lưu toàn bộ mã sau vào **`AccessMatrixDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;

public class AccessMatrixDemo {
    public static class Vault {
        public String everyone() { return "public"; }
        protected String family() { return "protected"; }
        String samePackage() { return "package"; }
        private String secret() { return "secret"; }
    }

    public static class NestPeer {
        public static String readSecret(Vault target) throws Exception {
            Method secret = Vault.class.getDeclaredMethod("secret");
            return (String) secret.invoke(target); // Cùng nest, không gọi setAccessible.
        }
    }

    public static void main(String[] args) throws Exception {
        Vault target = new Vault();
        System.out.println("nestmates: "
                + Vault.class.isNestmateOf(NestPeer.class));
        System.out.println("nest private: "
                + NestPeer.readSecret(target));
        System.out.println("package-private: "
                + PackagePeer.readPackage(target));
        System.out.println("protected same package: "
                + PackagePeer.readProtected(target));
        System.out.println("private from non-nest: "
                + PackagePeer.readPrivate(target));
        System.out.println("public call: "
                + Vault.class.getMethod("everyone").invoke(target));
        System.out.println("declared finds private: "
                + (Vault.class.getDeclaredMethod("secret") != null));
        System.out.println("getMethods finds private: "
                + Arrays.stream(Vault.class.getMethods())
                        .anyMatch(m -> m.getName().equals("secret")));
        System.out.println("unnamed module: "
                + !Vault.class.getModule().isNamed());
    }
}

// Top-level class khác: cùng package, nhưng KHÔNG cùng nest với Vault.
class PackagePeer {
    static String readPackage(AccessMatrixDemo.Vault target)
            throws Exception {
        Method m = AccessMatrixDemo.Vault.class
                .getDeclaredMethod("samePackage");
        return (String) m.invoke(target);
    }

    static String readProtected(AccessMatrixDemo.Vault target)
            throws Exception {
        Method m = AccessMatrixDemo.Vault.class
                .getDeclaredMethod("family");
        return (String) m.invoke(target);
    }

    static String readPrivate(AccessMatrixDemo.Vault target)
            throws Exception {
        Method m = AccessMatrixDemo.Vault.class
                .getDeclaredMethod("secret");
        try {
            return (String) m.invoke(target);
        } catch (IllegalAccessException ex) {
            return ex.getClass().getSimpleName();
        }
    }
}
```

Biên dịch, chạy từ thư mục chứa file:

```bash
javac --release 17 AccessMatrixDemo.java
java AccessMatrixDemo
```

Output:

```text
nestmates: true
nest private: secret
package-private: package
protected same package: protected
private from non-nest: IllegalAccessException
public call: public
declared finds private: true
getMethods finds private: false
unnamed module: true
```

**Giải thích:** `NestPeer` gọi được `Vault.secret` vì hai class cùng nest. `PackagePeer` nằm trong cùng package nên gọi được phương thức package-private và protected, nhưng lời gọi private không được phép. `getDeclaredMethod` vẫn **tìm thấy** private method; `getMethods` chỉ liệt kê public methods và không lấy private member. Ví dụ chạy trên **classpath** (unnamed module) nên dòng cuối là `true`. Với named module cần xem thêm cấu hình `module-info.java` ở mục 5.

Chạy trên JDK 17 hoặc mới hơn là đủ; chương trình không dùng `--add-opens` và không gọi `setAccessible`.

## 5. JPMS: `exports` và `opens` không đồng nghĩa nhau

**Java Platform Module System (JPMS)** bổ sung lớp kiểm soát theo module kể từ Java 9. Với named modules, package là ranh giới của hai chỉ thị quan trọng:

- `exports pkg;`: công bố các **public types và public/protected members có thể truy cập theo quy tắc Java** của package đến các module được phép. `exports pkg to some.module;` giới hạn tới module chỉ định. Nó hỗ trợ truy cập thông thường và reflection đối với phần public phù hợp; không tự cấp deep reflection tới private member.
- `opens pkg;`: cho phép **deep reflection tại runtime** tới package theo điều kiện của `AccessibleObject.setAccessible/trySetAccessible`. `opens pkg to tool.module;` chỉ mở cho module chỉ định. Nó **không tự cung cấp quyền tham chiếu kiểu trong code nguồn** như `exports`.
- `open module my.module { ... }`: mở mọi package của module cho deep reflection; việc mở toàn module là phạm vi rộng, nên cân nhắc dùng `opens pkg to tool.module` hẹp hơn.
- Một `opens` **không buộc** công cụ phải dùng private field; công cụ vẫn nên có chính sách allowlist/authorization riêng.

### Ma trận giữa hai named modules

Giả sử module gọi là `client.module`, declaring class nằm trong `library.module`, hai module đã được xác định phù hợp. Bảng này mô tả **quyền qua ranh giới module** đối với public class/member hoặc khả năng bật deep reflection, còn Java language modifiers vẫn áp dụng.

| Trạng thái package trong `library.module` đối với caller | Dùng public API thông thường | `getDeclared...` có thể khám phá? | `trySetAccessible` cho private member từ module khác | Nhận xét |
| --- | --- | --- | --- | --- |
| `exports api;` hoặc `exports api to client.module;` | Có khi member/type public và các điều kiện ngôn ngữ thỏa | Có thể tìm metadata khi có `Class<?>` | **Không** nếu package không đồng thời open | Public export khác deep access |
| `opens internal;` hoặc `opens internal to client.module;`, không export | Không biến internal types thành API dùng tĩnh | Có thể tìm metadata khi nắm được `Class<?>` | **Có thể**, nếu điều kiện `setAccessible` được đáp ứng | Hướng tới framework reflection |
| Vừa `exports` vừa `opens` | Có với public contract | Có thể | Có thể | Quyền mở rộng hơn |
| Không `exports` cũng không `opens` | Không cho client bình thường dùng public type ở package này | Việc có `Class<?>` không tự cấp quyền | **Không** | Không bypass bằng `getDeclared...` |
| Hai caller/declaring class **trong cùng module** | Vẫn tuân theo modifier Java | Có thể | `setAccessible(true)` thường có thể suppress checks về modifier | Module cùng nhau không có nghĩa private truy cập trực tiếp giữa class không nest |

**Chú ý tinh tế:** Kiểm tra access do `AccessibleObject` thực hiện có một điểm khác quy tắc ngôn ngữ thông thường: **reflection giả định module của caller có readability đối với module của declaring class** (xem Javadoc). Khi **biên dịch/tham chiếu tĩnh** từ named module khác, dependency `requires` và package `exports` vẫn là điều kiện liên quan. Đừng đánh đồng khả năng phản chiếu qua tên class đã có với khả năng `import` type từ source code.

### Hai đoạn `module-info.java` minh họa

Giả sử thư viện cung cấp package `com.example.api` cho app và mở package nội bộ cho framework:

```java
// module-info.java của thư viện; ví dụ cấu hình, không chạy một mình.
module example.library {
    exports com.example.api to example.client;
    opens com.example.internal to example.serializer;
}
```

Một ứng dụng tham chiếu public API thư viện:

```java
// module-info.java của client; ví dụ cấu hình.
module example.client {
    requires example.library;
}
```

`example.client` được truy cập public API trong `com.example.api`; `example.serializer` có thể sử dụng deep reflection tới `com.example.internal` khi gọi `setAccessible` trong phạm vi package được mở, đồng thời còn cần các điều kiện truy cập, class loading và API tương ứng. Mã này là **fragment cấu hình**; muốn build cần tạo đủ các module/package và nguồn cụ thể. Không coi `opens` là giải pháp ủy quyền an toàn cho mã không tin cậy.

### Named, unnamed, automatic và open module

Trên **classpath**, class thường thuộc **unnamed module**; các package của unnamed module được coi là exported và open với các module khác theo Javadoc `AccessibleObject`. Named module thì tuân theo `module-info.java` (trừ các cấu hình bổ sung lúc chạy). **Automatic modules** hình thành khi đặt JAR thông thường lên module path, có các đặc tính export/open riêng của automatic module, nhưng đừng dùng nó làm thiết kế lâu dài cho ranh giới bảo mật; khi chuyển sang explicit named module, kết quả deep reflection có thể đổi.

Các tùy chọn launcher như `--add-exports`/`--add-opens` có thể mở đường cho tương thích trong môi trường được quản lý, nhưng đây là ngoại lệ cấu hình, không phải lý do để dùng chúng đại trà. Ưu tiên thư viện cung cấp public API hoặc mở đúng package cho đúng framework.

## 6. Bảng `setAccessible`, `trySetAccessible` và `canAccess`

Bình thường, khi `Method.invoke`/`Field.get`/`Constructor.newInstance` được gọi, access checks được áp dụng. `AccessibleObject` cung cấp API để kiểm tra hoặc cho phép suppress checks trong phạm vi JDK cho phép:

| API | Mục đích | Kết quả / ngoại lệ đáng nhớ |
| --- | --- | --- |
| `member.canAccess(receiver)` | Hỏi **caller hiện tại** có thể truy cập thành viên trên receiver đó không | Trả boolean; có thể ném `IllegalArgumentException` nếu receiver dùng sai loại (constructor/static cần `null`) |
| `member.trySetAccessible()` | Xin bật cờ suppress Java access checks nếu được phép | `true` khi bật được, `false` nếu không thể bật vì access rules; vẫn có thể có `SecurityException` theo cấu hình |
| `member.setAccessible(true)` | Bật suppress checks nếu được phép | Có thể ném `InaccessibleObjectException` khi module không cho phép, hoặc lỗi security khác theo môi trường |
| `member.setAccessible(false)` | Trở về access checks mặc định | Không phải “đóng” package hoặc thu hồi mọi tham chiếu handle đã phát hành |
| `member.isAccessible()` | API cũ chỉ hỏi trạng thái flag | **Deprecated**; không thay được `canAccess` |

**Hợp đồng chính xác của `setAccessible(true)` trong Java 17** cho phép caller class `C` bật access checks suppression cho member khai báo trong class `D` nếu có ít nhất một điều kiện:

1. `C` và `D` nằm **cùng module**; hoặc
2. Member `public`, class `D` `public`, package của `D` **exported** tới module của `C`; hoặc
3. Member `protected static`, class `D` `public`, package của `D` exported tới caller module, và `C` là subclass của `D`; hoặc
4. Package của `D` **opens** tới module của `C`.

Nếu `C` nằm module khác, package của `D` không mở tới `C`, thì **không thể** dùng `setAccessible(true)` để bật quyền private, package-private, protected instance hoặc protected constructor chỉ dựa vào tên member. Với trường `final` thuộc loại không thể sửa như `static final`, final của record hoặc hidden class, bật flag cũng **không cấp quyền ghi**.

Với instance field/method, `canAccess(instance)` đòi instance phù hợp; với constructor/static member, `canAccess(null)` là cú pháp phù hợp. **`canAccess` không phải hàm tự động sửa quyền** và không phải phép kiểm tra xem tên method có tồn tại.

Ví dụ an toàn để không ép deep access:

```java
Method m = type.getDeclaredMethod("operation"); // fragment
if (m.canAccess(instance) || m.trySetAccessible()) {
    Object result = m.invoke(instance);
    // Xử lý result
} else {
    // Không đủ quyền: chuyển sang API public hoặc báo lỗi cấu hình rõ ràng.
}
```

Fragment này giả sử `type`, `instance` và method zero-argument đã hợp lệ, đồng thời caller xử lý checked exceptions. Trong thư viện tổng quát nên phân loại nguyên nhân lỗi, kiểm tra receiver trước, tránh tự ý `trySetAccessible` khi đang xử lý code/plugin không tin cậy; khả năng kỹ thuật không đồng nghĩa được phép đọc nội dung.

## 7. `protected` ở khác package: vì sao receiver quan trọng?

Đặt superclass và subclass ở hai package:

```java
// file base/Parent.java
package base;
public class Parent {
    protected String token() { return "token"; }
}
```

```java
// file child/Child.java
package child;
public class Child extends base.Parent {
    public String onChild() {
        return token(); // Hợp lệ: gọi trên chính instance thuộc Child.
    }

    public String onReceiver(Child other) {
        return other.token(); // Hợp lệ: receiver được phép.
    }

    // public String wrong(base.Parent parent) {
    //     return parent.token(); // Không hợp lệ ở đây: qualifier Parent.
    // }
}
```

Hai đoạn là **fragment độc lập theo đường dẫn nguồn**, không thuộc ví dụ chạy một file ở mục 4. Ý nghĩa là subclass ngoài package có quyền dùng protected member trong phạm vi đã định, nhưng không được phép truy cập protected instance member thông qua mọi receiver kiểu superclass. Reflection cũng không được hiểu là cách vô điều kiện né hạn chế đó.

Đối với member `protected static`, kiểm tra có điều kiện riêng theo quy tắc `AccessibleObject.setAccessible` khi xét khác module; nó không bị ràng buộc bởi instance receiver giống protected instance method. Khi phân tích class kế thừa khác module, trước tiên phải xét declaring type/package có exported phù hợp không.

## 8. `MethodHandles.Lookup` có hệ quyền riêng, không tự bỏ qua JPMS

`java.lang.invoke.MethodHandles.Lookup` là đối tượng đại diện năng lực tra cứu/gọi với **access modes** phụ thuộc context. `MethodHandles.lookup()` tạo lookup theo class nơi được gọi; `MethodHandles.publicLookup()` hạn chế vào thành viên public khả dụng.

`Lookup.findVirtual`, `findStatic`, `findGetter`, `findVarHandle`... kiểm tra quyền khi tìm handle. Không nên nghĩ `MethodHandle` hoặc `VarHandle` sẽ bỏ qua modifier hoặc module vì code không trực tiếp gọi `Method.invoke`.

`MethodHandles.privateLookupIn(Target.class, callerLookup)` có thể cho phép lookup tới private members khi caller có đủ quyền và điều kiện module (bao gồm `opens` khi crossing module) phù hợp. Nó **không phải cửa hậu** tự động đọc private member trong mọi named module. Không trao lookup có quyền private rộng cho mã không tin cậy.

Trong một số framework, chiến lược sạch hơn là dùng public contract/annotation cho các thành viên được phép, tạo đúng handle cần thiết trong ngữ cảnh có quyền rồi cung cấp handle đó. Phân biệt metadata discovery với khả năng thao tác được ủy quyền.

## 9. Tra cứu reflection: declared, public, inherited và access

| Lệnh | Phạm vi khám phá | Điểm dễ nhầm |
| --- | --- | --- |
| `type.getMethod(name, parameterTypes)` | Method `public` của type, gồm method public inherited phù hợp | Không tìm protected/package-private/private method |
| `type.getDeclaredMethod(name, parameterTypes)` | Method khai báo **trực tiếp** trong type, mọi modifier | Không tìm inherited; trả metadata không cho quyền gọi |
| `type.getMethods()` | Các public methods được cung cấp (gồm inherited) | Thứ tự không phải contract sắp xếp |
| `type.getDeclaredMethods()` | Methods khai báo trực tiếp, kể cả private/protected/package-private | Không tự thực hiện access suppression |
| `type.getField(name)` / `getFields()` | Public fields phù hợp (kể cả inherited) | Field hiding cần xét declaring class |
| `type.getDeclaredField(name)` / `getDeclaredFields()` | Field khai báo trực tiếp, mọi modifier | Không tự lấy inherited; không có quyền đọc mặc nhiên |
| `type.getConstructor(parameterTypes)` | Public constructor của type | Constructor không được kế thừa |
| `type.getDeclaredConstructor(parameterTypes)` | Constructor khai báo trong type, kể cả private | Vẫn cần kiểm tra access khi tạo instance |

`Modifier.toString(member.getModifiers())` cho biết biểu diễn modifier. `member.getDeclaringClass()` cho biết class khai báo. Khi build tool, nhớ lọc bridge/synthetic members theo ngữ cảnh; đôi khi chúng xuất hiện trong metadata nhưng không phải public business contract. Việc lấy được một `Class<?>` bằng `Class.forName` cũng không hàm ý mọi member bên trong class sẽ có quyền truy cập.

## 10. Chẩn đoán theo loại lỗi

| Kết quả / lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchMethodException` | Tên hoặc kiểu parameter không khớp; dùng `getMethod` cho private method | So metadata với overload đúng, chuyển `getDeclaredMethod` khi cần khám phá member declared |
| `IllegalAccessException` ở `Method.invoke`/`Field.get` | Caller không có quyền Java reflection hiện tại | Xem modifier, declaring class, package/nest/module; ưu tiên public API |
| `InaccessibleObjectException` từ `setAccessible(true)` | Không được suppress checks theo module boundaries | Cân nhắc `opens` có phạm vi hẹp hoặc thiết kế API public; không ép mở toàn JVM |
| `trySetAccessible() == false` | Không được bật access flag | Xử lý gracefully, ghi lý do cấu hình, không thử đi thử lại vô hạn |
| `IllegalArgumentException` từ `Method.invoke` | Receiver sai class, sai số lượng/kiểu đối số, primitive conversion không hợp lệ | Kiểm tra `getDeclaringClass`, `getParameterTypes` và receiver |
| `NullPointerException` từ instance invocation với receiver `null` | Không có receiver cho instance member | Kiểm tra `receiver != null` trước khi gọi |
| `InvocationTargetException` | Chính method/constructor đích ném exception | Kiểm tra `getCause()`, không nhầm với lỗi access |
| `ExceptionInInitializerError` | Static initialization của declaring class thất bại | Phân tích initializer và root cause |

**Đừng dùng `setAccessible(true)` như cách chữa chung** cho mọi lỗi: lỗi sai receiver, sai parameter signature, không tìm thấy member hay exception do method đích không thể sửa bằng access flag.

### Checklist điều tra

1. `member.getDeclaringClass()` là lớp nào? Declaring class có thực sự accessible không?
2. Modifier của member và của declaring class là gì?
3. Code **gọi `invoke/get/set`** nằm trong class/nest/package nào? Nó có quyền riêng không?
4. Nếu khác package: caller là subclass? Receiver có đúng subtype theo luật protected?
5. Nếu khác named module: target package `exports` hay `opens` cho module nào? Cần truy cập public hay deep access?
6. Có gọi `setAccessible`/`trySetAccessible` không, và kết quả thực tế?
7. Receiver là instance hợp lệ, static member dùng receiver thích hợp, đối số đúng chữ ký không?
8. Nếu chạy trên JVM có nhiều classloader: hai class “cùng tên package” có thực sự cùng runtime package không?
9. Có đang vô tình cho plugin hoặc dữ liệu không tin cậy quyền inspect/gọi mọi private member?
10. Có thể thay deep reflection bằng interface/public factory/API được chủ sở hữu định nghĩa không?

## 11. Các lỗi suy luận thường gặp

- **“`private` chỉ truy cập trong đúng class khai báo”:** thiếu ngữ cảnh Java 11+; nestmates có thể truy cập private member của nhau.
- **“Cùng package name là đủ”:** runtime package còn liên quan defining classloader, đặc biệt với plugin.
- **“Cùng module nghĩa là cùng package”:** sai; hai package khác nhau trong cùng module vẫn chịu package access.
- **“`protected` cho phép subclass gọi trên mọi Parent instance”:** sai ở khác package với protected instance members.
- **“`getDeclaredMethod` tìm được thì `invoke` chắc chắn thành công”:** sai; metadata discovery khác access, receiver và argument contract.
- **“`exports` cũng mở được private reflection”:** sai; deep reflection từ module khác thường cần `opens`/một điều kiện phù hợp trong `AccessibleObject`.
- **“`opens` giống `exports`, app có thể `import` mọi type”:** sai; `opens` dành cho reflective access, không tạo compile-time API export.
- **“`trySetAccessible()` luôn trả true nếu caller có `Class<?>`”:** sai; strong encapsulation có thể cản.
- **“`setAccessible(true)` cho phép sửa mọi final field”:** sai; có non-modifiable final fields (static final, record final, hidden class final) mà flag không cấp quyền ghi.
- **“`MethodHandle` bỏ qua Java security và JPMS”:** sai; `Lookup` mang và kiểm tra access modes.

## 12. Tự kiểm tra nhanh

1. `Outer.A` và `Outer.B` là hai nestmates, `A` khai báo private method. `B` có thể reflective invoke method đó khi không bật accessible flag không? **Có thể**, nếu đúng nest và các điều kiện gọi khác hợp lệ.
2. Hai top-level class cùng package, khác nest, một class có private field. Class còn lại đọc bằng `Field.get` không bật flag được không? **Không**.
3. `Library` là named module, export `api` nhưng không open `api`; client module đọc public API được, còn private field từ client bằng `trySetAccessible` được không? **Không theo mặc định**.
4. Mở `opens internal to framework.module;` có cho một app khác tự động `import internal.Hidden` ở thời điểm biên dịch không? **Không**.
5. Subclass khác package có quyền protected instance member khi receiver là một instance bất kỳ của superclass không? **Không, có điều kiện receiver/qualifier**.
6. `getDeclaredMethods()` trả private member thì có mặc nhiên gọi được không? **Không**.
7. `canAccess(null)` phù hợp cho instance method hay constructor/static member? **Constructor/static**; instance yêu cầu receiver thuộc declaring class.
8. Class name giống nhau, package giống nhau nhưng do hai defining classloader khác nhau tải: có tự chia sẻ package-private access không? **Không**.
9. Cần công cụ đọc private field thuộc named module khác: `exports` là đủ chưa? **Chưa**; xem `opens` và quy tắc `AccessibleObject`.
10. Một lời gọi reflection ném `InvocationTargetException`: kiểm tra gì trước? **`getCause()` để xem lỗi do chính code đích**.

Tài liệu chuẩn Java 17:

- [JLS `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6)
- [JLS `6.6.2.1 — Access to a protected Member](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6.2.1)
- [JLS `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Javadoc `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Javadoc `Class.getNestHost` / `isNestmateOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Javadoc `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181)
