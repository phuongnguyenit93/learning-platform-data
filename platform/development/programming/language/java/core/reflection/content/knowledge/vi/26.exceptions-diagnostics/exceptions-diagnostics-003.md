# IllegalAccessException khác InaccessibleObjectException như thế nào trong Java Reflection?

Khi dùng Reflection để đọc trường, gọi method hoặc tạo đối tượng, lập trình viên thường gặp hai lỗi có tên gần giống nhau:

- `java.lang.IllegalAccessException`: thao tác Reflection **không được phép truy cập một member** theo các quy tắc access đang áp dụng.
- `java.lang.reflect.InaccessibleObjectException`: chương trình **cố yêu cầu bỏ qua access check bằng Reflection nhưng JVM không cho phép bật quyền đó**, thường do tính đóng gói mạnh của Java Platform Module System (JPMS).

Hai exception giải quyết **hai câu hỏi khác nhau**. `IllegalAccessException` thường xảy ra lúc **thực hiện thao tác lên member**; `InaccessibleObjectException` thường xảy ra khi **cố mở quyền Reflection trước khi thao tác**, chẳng hạn với `setAccessible(true)`. Chúng có thể liên quan đến cùng một member, nhưng không đồng nghĩa và không thể sửa bằng cùng một biện pháp trong mọi trường hợp.

## 1. Nắm mô hình access trước khi xem lỗi

Trong Java có hai lớp quy tắc quan trọng:

1. **Quyền truy cập của ngôn ngữ Java**: `public`, `protected`, package-private (không ghi modifier), `private` và quan hệ class/package/subclass/nestmate.
2. **Ranh giới module của JPMS (Java 9+)**: một package thuộc named module có thể được **export** để hỗ trợ truy cập API công khai, hoặc được **open** để cho phép Reflection truy cập sâu hơn vào các member không public.

Reflection có thể tìm ra metadata về một member bằng `getDeclaredMethod(...)`, `getDeclaredField(...)` hoặc `getDeclaredConstructor(...)` dù việc **gọi/đọc/ghi** member đó vẫn bị từ chối. “Nhìn thấy metadata” không đồng nghĩa “được quyền dùng member”.

Ví dụ:

```java
Method method = type.getDeclaredMethod("secret"); // Lấy metadata.
method.invoke(target);                            // Thực hiện lời gọi; có thể thất bại.
```

Đây là **đoạn minh họa**, giả định `type` và `target` đã tồn tại. Lúc `invoke`, JVM kiểm tra quyền của caller nếu access checks chưa được bỏ qua hợp lệ.

### Vai trò của AccessibleObject

`Method`, `Field` và `Constructor` kế thừa `AccessibleObject`. Các API có ý nghĩa khác nhau:

- `canAccess(receiver)`: kiểm tra caller hiện tại có quyền truy cập member với receiver tương ứng hay không. Với static member/constructor, receiver cần dùng theo hợp đồng riêng của API, thường là `null`.
- `trySetAccessible()`: thử bật chế độ bỏ qua access checks cho đối tượng Reflection; trả `true` nếu thành công, `false` nếu không thể bật do ràng buộc truy cập. Một số kiểm tra bảo mật riêng vẫn có thể ném exception.
- `setAccessible(true)`: yêu cầu bỏ qua access checks; nếu không thể bật vì quy tắc module, có thể ném `InaccessibleObjectException`.
- `setAccessible(false)`: tắt việc bỏ qua access checks đã bật trên đối tượng Reflection ấy; **không** sửa modifier của class/member.

Tên `setAccessible(true)` dễ gây hiểu nhầm: đây **không phải** lệnh biến method `private` thành `public` hoặc mở package toàn cục. Nó chỉ tác động đến đối tượng `AccessibleObject` theo quyền JVM cho phép.

## 2. IllegalAccessException: bị chặn khi đọc, ghi, gọi hoặc tạo đối tượng

`IllegalAccessException` là **checked exception** kế thừa `ReflectiveOperationException`. Các thao tác như sau có thể ném exception này khi caller không được phép truy cập:

- `Method.invoke(target, args)` khi method hoặc class khai báo không khả dụng với caller.
- `Field.get(target)` hoặc `Field.set(target, value)` khi quyền đọc/ghi qua Reflection không được cấp. Với trường `final` còn có các giới hạn ghi riêng.
- `Constructor.newInstance(args)` khi constructor không khả dụng với caller.

Ví dụ `getDeclaredMethod("secret")` có thể trả về một `Method` mô tả method private. Nếu method nằm trong một class không cùng nest và caller không có quyền truy cập, `invoke` sẽ ném `IllegalAccessException`, trừ khi caller đã bật chế độ bỏ qua access checks một cách hợp lệ.

Điểm cần phân biệt:

- `IllegalAccessException` đến từ **quyền sử dụng member khi thực hiện Reflection**.
- `IllegalAccessError` là một **LinkageError**, thường phát sinh khi bytecode tham chiếu đến class/member không thể truy cập theo ràng buộc liên kết runtime; đây **không phải** exception checked của `Method.invoke`.
- Lỗi biên dịch Java kiểu “has private access” cũng **không phải** `IllegalAccessException` của Reflection: compiler có thể từ chối mã truy cập trực tiếp trước khi chạy.

### Cách chẩn đoán

Đầu tiên kiểm tra class khai báo member, modifier và ngữ cảnh caller:

```java
Method method = target.getClass().getDeclaredMethod("secret");
System.out.println(method.getDeclaringClass().getName());
System.out.println(Modifier.toString(method.getModifiers()));
```

Đây là **đoạn minh họa**, cần `import java.lang.reflect.Method;` và `import java.lang.reflect.Modifier;`, giả định `target` đã tồn tại và method đúng tên. `getDeclaredMethod` **không** tự tìm method được kế thừa từ superclass; dùng `getMethod` khi muốn tìm public member theo hợp đồng của API.

Nếu có thể, hãy sử dụng API `public` được thiết kế cho caller. Nếu phải gọi một member không public trong code có kiểm soát, có thể cân nhắc `trySetAccessible()` nhưng phải xem xét ranh giới module và quyền truy cập.

## 3. InaccessibleObjectException: thất bại khi yêu cầu truy cập sâu

`InaccessibleObjectException` là **unchecked exception** kế thừa `RuntimeException`, thuộc package `java.lang.reflect`. Trường hợp phổ biến:

```java
Method method = someClass.getDeclaredMethod("hidden");
method.setAccessible(true); // Có thể ném InaccessibleObjectException.
```

Đây là **đoạn minh họa**. Trên Java 17+, nhiều package nội bộ của JDK thuộc named module và không được mở cho mọi caller. Việc `getDeclaredMethod` tìm được metadata **không** có nghĩa JVM cho phép `setAccessible(true)`.

Ví dụ cụ thể: package `java.lang` của module `java.base` được export để sử dụng API public, nhưng **không mặc nhiên được open** cho ứng dụng ở unnamed module để truy cập sâu vào protected/private member của JDK. Vì vậy việc cố mở `ClassLoader#defineClass(...)` bằng Reflection thường bị từ chối khi chạy Java 17 với cấu hình module mặc định.

Khác với `IllegalAccessException` xảy ra khi `invoke/get/set/newInstance` không có quyền, `InaccessibleObjectException` chỉ ra rằng **chính hành động yêu cầu vượt qua access check không được chấp nhận**. Chưa cần gọi member thật cũng có thể gặp lỗi.

**Quan trọng:** `setAccessible(true)` có thể thành công với private member trong **cùng module** hoặc trong package được open phù hợp, tùy quy tắc API. Vì vậy không được kết luận “Java 17 luôn cấm Reflection với private member”. Java 17 vẫn cho phép deep reflection trong nhiều trường hợp; điểm khác biệt là phạm vi access và module.

## 4. Ví dụ Java 17+ chạy được: hai exception, hai thời điểm

Ví dụ sau không cần thư viện ngoài. Nó đặt `SecretBox` thành một **top-level class khác** trong cùng file, thay vì nested class cùng nest, để trình diễn `IllegalAccessException` một cách rõ ràng. Sau đó nó thử truy cập một protected method của JDK để quan sát `InaccessibleObjectException`.

Lưu **toàn bộ** mã vào file `AccessErrorsDemo.java`:

```java
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;

public class AccessErrorsDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Method local = SecretBox.class.getDeclaredMethod("reveal");
        System.out.println("lookup: " + local.getName());

        try {
            local.invoke(new SecretBox());
        } catch (IllegalAccessException ex) {
            System.out.println("invoke before suppression: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("local trySetAccessible: "
                + local.trySetAccessible());
        System.out.println("invoke after suppression: "
                + local.invoke(new SecretBox()));

        Method defineClass = ClassLoader.class.getDeclaredMethod(
                "defineClass", String.class, byte[].class, int.class, int.class);
        System.out.println("JDK trySetAccessible: "
                + defineClass.trySetAccessible());

        try {
            defineClass.setAccessible(true);
            System.out.println("setAccessible JDK: granted");
        } catch (InaccessibleObjectException ex) {
            System.out.println("setAccessible JDK: "
                    + ex.getClass().getSimpleName());
        }
    }
}

class SecretBox {
    private String reveal() {
        return "secret value";
    }
}
```

Biên dịch/chạy bằng **JDK 17+**, với khởi chạy **mặc định** (không cấp thêm `--add-opens`):

```bash
javac --release 17 -encoding UTF-8 AccessErrorsDemo.java
java AccessErrorsDemo
```

Stdout trên OpenJDK với cấu hình module mặc định:

```text
lookup: reveal
invoke before suppression: IllegalAccessException
local trySetAccessible: true
invoke after suppression: secret value
JDK trySetAccessible: false
setAccessible JDK: InaccessibleObjectException
```

**Đọc kết quả theo thứ tự:**

1. `getDeclaredMethod("reveal")` tìm được metadata của private method, chưa gọi method và chưa thay đổi access.
2. `local.invoke(new SecretBox())` thất bại với `IllegalAccessException` vì `AccessErrorsDemo` và `SecretBox` là hai top-level class **khác nest**, và method `reveal()` là `private`.
3. `local.trySetAccessible()` thành công vì cả hai class thuộc cùng unnamed module, nơi JVM cho phép bỏ qua access checks cho tình huống này.
4. `invoke` lần hai trả `secret value`: việc truy cập private member giờ hợp lệ đối với đối tượng `Method` đã được mở.
5. `ClassLoader#defineClass(String, byte[], int, int)` là protected method trong package `java.lang` thuộc named module `java.base`. Chương trình ở unnamed module không được cấp deep reflection vào package này theo cấu hình mặc định, nên `trySetAccessible()` trả `false`.
6. Cùng member JDK ấy, `setAccessible(true)` ném `InaccessibleObjectException`. Không có lời gọi `defineClass(...)` nào được thực hiện.

**Vì sao có thể đổi kết quả?** Nếu JVM được chạy với tham số mở module, ví dụ:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED AccessErrorsDemo
```

Thì thao tác mở `ClassLoader#defineClass` có thể thành công: `JDK trySetAccessible` thành `true` và thông báo `setAccessible JDK: granted`. Điều đó minh họa vai trò của module openness. Tùy môi trường/runtime, các cờ mở package sẵn có cũng ảnh hưởng kết quả; không dùng stdout của ví dụ như lời khẳng định cho mọi cấu hình JVM.

**Không dùng `--add-opens` bừa bãi trong production** chỉ để làm mất exception. Đó là thay đổi ranh giới encapsulation, có thể phụ thuộc mạnh vào chi tiết JDK.

## 5. JPMS: exports khác opens thế nào?

Xét named module `billing.core` với package `billing.api` chứa class và method public, cùng package `billing.internal` có private field cần Reflection.

Một file `module-info.java` *minh họa*:

```java
module billing.core {
    exports billing.api;
    opens billing.internal to billing.tool;
}
```

Ý nghĩa:

- `exports billing.api;` cho các module khác sử dụng **public API** của `billing.api` theo luật module và Java access. Nó **không** tự cấp quyền deep reflection tới private field.
- `opens billing.internal to billing.tool;` cho phép module `billing.tool` thực hiện deep reflection vào package `billing.internal` theo điều kiện của API. Nó **không** đồng nghĩa cho module đó import mọi class package-private như API công khai.
- `open module billing.core { ... }` là cách mở mọi package của module cho Reflection; phạm vi rộng hơn và cần cân nhắc thiết kế.
- Một package có thể được both exported và opened; tác dụng của hai khai báo khác nhau.

Đây là **đoạn cấu hình minh họa**, không phải dự án module có thể chạy riêng; module `billing.tool` và các package cần hiện hữu để biên dịch ví dụ.

### Các biến thể ở command line

Khi không thể thay file `module-info.java`, JVM có tùy chọn:

```bash
java --add-opens billing.core/billing.internal=billing.tool \
     --module-path mods \
     --module billing.tool/billing.tool.Main
```

Lệnh trên minh họa cho shell hỗ trợ ký tự `\` nối dòng, giả định `mods` chứa các module đã biên dịch và main class chính xác. Cùng ý tưởng nhưng dùng `ALL-UNNAMED` nếu caller thuộc unnamed module.

**Phân biệt:**

- `--add-exports module/package=target`: bổ sung quyền export, phục vụ truy cập API công khai theo quy tắc access.
- `--add-opens module/package=target`: bổ sung quyền open package cho deep reflection, phù hợp hơn khi vấn đề là `setAccessible(true)` bị chặn bởi JPMS.

`--add-exports` đơn độc **không** đủ để mở các private member của package trong named module. `--add-opens` cũng **không** làm `private` thành public theo lời gọi Java thông thường.

### Unnamed module và same-module access

Ứng dụng chạy trên classpath thường thuộc unnamed module. Theo mô hình JPMS, package của unnamed module được coi là export và open rộng; vì vậy bài demo có thể bật access cho `SecretBox.reveal()`. Trong named module, Reflection vào member không public **bên trong cùng module** cũng có các trường hợp được phép bật access. Nhưng khi đi xuyên sang một named module khác có package không open, `setAccessible(true)` thường bị từ chối.

Cần kiểm tra **module của caller**, **module của declaring class** và trạng thái export/open của **package**; chỉ biết modifier `private` là chưa đủ để dự đoán `InaccessibleObjectException`.

## 6. Bảng so sánh nhanh

| Tiêu chí | `IllegalAccessException` | `InaccessibleObjectException` |
|---|---|---|
| Package | `java.lang` | `java.lang.reflect` |
| Loại | **Checked**, kế thừa `ReflectiveOperationException` | **Unchecked**, kế thừa `RuntimeException` |
| Bước hay xảy ra | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | `AccessibleObject.setAccessible(true)` |
| Câu hỏi JVM đang trả lời | “Caller có được phép thực hiện thao tác với member này không?” | “Có được phép bỏ qua access checks cho member này không?” |
| Nguyên nhân phổ biến | Private/protected/package-private hoặc class không accessible; chưa bật suppression hợp lệ | Package thuộc named module không open cho caller; quy tắc deep reflection từ chối |
| `trySetAccessible()` | Có thể thành công và cho phép thao tác về sau | Thường trả `false` trong tình huống module cản trở |
| Hướng xử lý ưu tiên | Dùng member public/contract phù hợp, sửa cách gọi, hoặc suppression hợp lệ | Mở package một cách chủ đích hoặc ngừng deep reflection vào internals |
| Điều không nên làm | Bắt rồi bỏ qua exception và giả định method đã được gọi | Bắt rồi tiếp tục coi `setAccessible(true)` đã thành công |

**Một member có thể dẫn tới cả hai exception tùy đường chạy:** nếu bỏ qua bước `setAccessible` và cố `invoke`, chương trình có thể gặp `IllegalAccessException`; nếu trước đó cố `setAccessible(true)` trong package bị JPMS khóa, chương trình có thể gặp `InaccessibleObjectException`. Không phải cùng lúc bắt buộc ném cả hai.

## 7. Quy trình chẩn đoán lỗi thực tế

### Bước 1: Xác định API ném exception

Đọc **stack trace đầy đủ** và chỉ ra call site đầu tiên từ code của bạn:

- `invoke/get/set/newInstance` → tập trung quyền truy cập member, modifiers và receiver.
- `setAccessible(true)` → kiểm tra quyền bypass và tình trạng package/module.
- `getDeclaredMethod/getDeclaredField` thất bại với `NoSuchMethodException/NoSuchFieldException` → đó là lỗi lookup khác, đừng gộp thành một trong hai access exception.

Không nên chỉ grep chữ “access” trong message rồi đoán lỗi.

### Bước 2: Kiểm tra metadata của member và module

Một số API có ích:

```java
Class<?> owner = method.getDeclaringClass();
Module module = owner.getModule();
String packageName = owner.getPackageName();

System.out.println("owner = " + owner.getName());
System.out.println("module = " + module.getName());
System.out.println("modifiers = "
        + java.lang.reflect.Modifier.toString(method.getModifiers()));
System.out.println("package = " + packageName);
```

Đây là **đoạn minh họa**, giả định biến `method` kiểu `Method` đã tồn tại. `module.getName()` có thể là `null` với unnamed module. Để kiểm tra chính xác quyền của caller, xem thêm `Class::getModule` trên caller và `Module::isExported`, `Module::isOpen` với tên package/target module thích hợp.

### Bước 3: Đánh giá cách mở access hợp lệ

Nếu thực sự có chủ đích dùng Reflection với member không public:

```java
if (!method.trySetAccessible()) {
    throw new IllegalStateException(
            "Member is not open for deep reflection: " + method);
}
Object result = method.invoke(target);
```

Đây là **đoạn minh họa**, giả định method không static và `target` phù hợp; thêm xử lý các checked exceptions của `invoke` trong code gọi. `trySetAccessible()` giúp xử lý nhánh không được mở mà không phải phụ thuộc vào exception `InaccessibleObjectException` từ `setAccessible(true)`. Nó **không** bảo đảm việc gọi method sau đó thành công: method có thể ném exception, receiver sai, đối số sai hoặc gặp các lỗi runtime khác.

### Bước 4: Sửa theo đúng lớp nguyên nhân

- Nếu API có public method/getter phù hợp, hãy ưu tiên dùng API đó.
- Nếu class nằm trong code mình kiểm soát, cân nhắc điều chỉnh visibility/contract hoặc tổ chức lại code; không mở rộng quyền chỉ vì một công cụ Reflection.
- Nếu package thuộc **named module do mình sở hữu**, mở có chọn lọc bằng `opens package to module;` khi thực sự cần deep reflection (ví dụ serializer/framework).
- Nếu module thuộc **thư viện/JDK**, xem tài liệu API và khả năng dùng public API thay thế; `--add-opens` chỉ nên là giải pháp có chủ đích trong môi trường được kiểm soát.
- Nếu exception xuất hiện sau khi nâng từ Java 8 lên Java 17+, kiểm tra kỹ module encapsulation và thư viện đang cố truy cập JDK internals; cập nhật thư viện thường bền vững hơn can thiệp JVM flags.

## 8. Những lỗi chẩn đoán phổ biến

**Nhầm 1: “Có `getDeclaredMethod` nghĩa là gọi được.”** Sai. Lookup và access check là hai bước khác nhau.

**Nhầm 2: “Gọi `setAccessible(true)` luôn sửa `IllegalAccessException`.”** Sai. Nếu module không mở package tương ứng, chính lời gọi này có thể ném `InaccessibleObjectException`.

**Nhầm 3: “Java 17 cấm truy cập private bằng Reflection.”** Sai. Các private member cùng module hoặc trong package được open vẫn có trường hợp cho phép suppression.

**Nhầm 4: “Thêm `exports` là đủ để đọc private field.”** Sai. `exports` và `opens` có mục đích khác nhau.

**Nhầm 5: “`InaccessibleObjectException` là checked, cần khai báo `throws`.”** Sai. Nó là unchecked exception; trong khi `IllegalAccessException` là checked.

**Nhầm 6: “Bắt cả hai exception và bỏ qua là xử lý xong.”** Sai. Quyền truy cập **chưa được cấp** và operation có thể chưa được thực hiện; bắt rồi bỏ qua có thể che giấu lỗi logic hoặc bảo mật.

**Nhầm 7: “Mọi exception từ `Method.invoke` đều là IllegalAccessException.”** Sai. Nếu method thật ném exception, Reflection thường bọc bằng `InvocationTargetException`; sai đối số có thể là `IllegalArgumentException`; lỗi khởi tạo class hoặc linkage có cơ chế khác.

**Nhầm 8: “Một method private trong nested class luôn gây IllegalAccessException.”** Không hẳn. Java có **nest-based access control**: các nestmate có thể truy cập private member của nhau theo quy tắc ngôn ngữ/JVM. Đó là lý do ví dụ runnable dùng hai **top-level class** khác nhau.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** `getDeclaredField("password")` trả về `Field` thành công; ngay sau đó `field.get(target)` ném `IllegalAccessException`. Tại sao?

**Trả lời:** Lookup metadata thành công, nhưng caller không có quyền thực hiện thao tác đọc member. Cần kiểm tra declaring class/member và access checks.

**Câu 2.** `field.setAccessible(true)` ném `InaccessibleObjectException` trên Java 17. Có chắc chỉ cần đổi field thành `public` không?

**Trả lời:** Không. Phải xét named module và quyền export/open của package; thay modifier riêng có thể không đủ. Ưu tiên public API hoặc cấu hình openness có chủ đích.

**Câu 3.** `trySetAccessible()` trả `false`: có nên gọi tiếp `field.get(...)` như thể đã được mở quyền không?

**Trả lời:** Không. Lời gọi mở access đã thất bại; cần xử lý nhánh này, hoặc xác minh caller thực ra có quyền qua Java access checks thông thường bằng `canAccess(...)`.

**Câu 4.** Vì sao `--add-exports java.base/java.lang=ALL-UNNAMED` không phải cách tương đương với `--add-opens java.base/java.lang=ALL-UNNAMED`?

**Trả lời:** Export phục vụ khả năng sử dụng thành phần public; open cho phép deep reflection theo quy tắc JPMS. Chúng không đồng nghĩa.

**Câu 5.** Nếu code Java 8 dùng Reflection truy cập các internal field của JDK và lên Java 17 bị lỗi, nên kiểm tra gì đầu tiên?

**Trả lời:** Stack trace, thư viện/framework nào đang dùng internal reflection, public API có thể thay thế, ranh giới module và khả năng cập nhật thư viện; chỉ dùng JVM opening flags sau khi hiểu mục đích.

## Tài liệu chuẩn

- Java SE API: [`IllegalAccessException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html).
- Java SE API: [`InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html).
- Java SE API: [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html) — `setAccessible`, `trySetAccessible`, `canAccess`.
- Java SE API: `Method.invoke`, `Field.get/set`, `Constructor.newInstance`, `Module.isOpen/isExported`.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403), có hiệu lực từ JDK 17.

**Ghi nhớ:** `IllegalAccessException` cho biết **thao tác Reflection trên member không được phép**; `InaccessibleObjectException` cho biết **nỗ lực mở quyền deep reflection bị từ chối**. Muốn xử lý đúng, xác định **API ném lỗi**, **modifier/member**, **module/package của caller và declaring class**, sau đó chọn public API hoặc mở quyền một cách chủ đích.