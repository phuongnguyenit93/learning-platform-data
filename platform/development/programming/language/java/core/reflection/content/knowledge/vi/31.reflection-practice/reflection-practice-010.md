# Hoàn thiện ví dụ module hóa cùng bộ kiểm thử quyền truy cập trong Java Reflection

## 1. Mục tiêu thực hành

Trong Java 9+, Java Platform Module System (**JPMS**) không chỉ tổ chức dependency giữa các thư viện mà còn đặt **ranh giới truy cập package tại runtime**. Vì thế, một công cụ Reflection không thể giả định rằng nhìn thấy `Class<?>`, `Field` hoặc `Constructor` đồng nghĩa có thể gọi hoặc đọc mọi thành viên.

Bài thực hành xây dựng hai **named modules** chạy trên Java 17+:

- `lab.model`: module chứa dữ liệu/API, với ba package có chính sách khác nhau.
- `lab.probe`: module đóng vai trò người sử dụng và bộ kiểm thử Reflection; khai báo `requires lab.model`.

Bộ kiểm thử chạy thật, có assertion, phân biệt rõ bốn tình huống: public API trong package được `exports`; private field trong package chỉ `exports`; private field trong package `opens ... to ...`; và public constructor trong package không `exports`/`opens`.

**Kết quả cần đạt:** công cụ chỉ chấp nhận quyền mà module cấp rõ ràng, ghi nhận trường hợp bị từ chối thay vì âm thầm gọi `setAccessible(true)` hoặc thêm `--add-opens` vô điều kiện.

## 2. Ba quy tắc cơ bản của JPMS cần kiểm chứng

### 2.1. `requires`: quan hệ đọc module

Trong `module-info.java` của `lab.probe`, khai báo `requires lab.model;` giúp module `lab.probe` **đọc được** module `lab.model`. Đây là bước cần thiết cho đoạn mã sử dụng kiểu API public của module kia theo cách thông thường, nhưng **không tự mở toàn bộ package** cho truy cập sâu bằng Reflection.

### 2.2. `exports`: công khai kiểu và thành viên public

Trong `lab.model`:

~~~java
exports lab.model.api;
~~~

Mã của module đọc `lab.model` có thể biên dịch với public type `lab.model.api.PublicOrder` và gọi phương thức `public number()`, nếu các quy tắc truy cập Java khác cũng đáp ứng. `getMethod("number").invoke(order)` hợp lệ trong demo.

Tuy nhiên **`exports` không có nghĩa `private` được phép đọc qua deep reflection**. Với field `private secret`, `getDeclaredField("secret")` tìm được metadata nhưng `trySetAccessible()` từ module khác trả `false`, và `Field.get` không có quyền sẽ ném `IllegalAccessException`.

### 2.3. `opens`: cho phép deep reflection, có thể giới hạn theo module đích

Trong `lab.model`:

~~~java
opens lab.model.view to lab.probe;
~~~

Câu lệnh này **mở package `lab.model.view` cho Reflection từ `lab.probe`**, kể cả thành viên `private`; nó **không phải khai báo `exports`** cho mã Java thông thường có thể `import lab.model.view.AuditView`.

Trong demo, `lab.probe` dùng `Class.forName("lab.model.view.AuditView")` để lấy `Class<?>` mà không viết `import`. Sau đó `Constructor.trySetAccessible()` và `Field.trySetAccessible()` thành công vì package được mở đúng module đích.

Package `lab.model.closed` không được `exports` cũng không `opens`. Việc tìm metadata constructor vẫn có thể thực hiện, nhưng truy cập constructor từ module khác bị chặn.

| Cấu hình package của `lab.model` | Dùng public type qua `import` trong `lab.probe` | Deep reflection tới private member từ `lab.probe` |
| --- | --- | --- |
| `exports lab.model.api;` | Có | Không chỉ vì `exports` |
| `opens lab.model.view to lab.probe;` | Không, vì thiếu `exports` | Có, vì mở cho module `lab.probe` |
| Không khai báo `exports` / `opens` cho `lab.model.closed` | Không | Không |

**Sự tinh tế khi kiểm tra:** `Module.isExported(packageName, targetModule)` phản ánh truy cập ở runtime và có thể trả `true` khi package được mở cho target module. Do đó **không dùng duy nhất** `isExported(packageName, target)` để chứng minh `module-info.java` có khai báo `exports`. Nếu cần kiểm tra **khai báo exports chính thức trong descriptor**, duyệt `module.getDescriptor().exports()`, như bộ kiểm thử bên dưới. Dùng `Module.isOpen(packageName, target)` để kiểm tra việc mở package cho Reflection.

## 3. Cấu trúc project có thể biên dịch trực tiếp

Tạo thư mục chứa đúng các file sau. Tên module **phải khớp** tên thư mục ngay dưới `src` để lệnh `--module-source-path src` hoạt động:

~~~text
reflection-access-lab/
├── src/
│   ├── lab.model/
│   │   ├── module-info.java
│   │   └── lab/model/
│   │       ├── api/PublicOrder.java
│   │       ├── view/AuditView.java
│   │       └── closed/ClosedService.java
│   └── lab.probe/
│       ├── module-info.java
│       └── lab/probe/AccessTest.java
└── out/                           # javac sinh ra, không tạo thủ công
~~~

Ví dụ chỉ dùng JDK, không cần Gradle, Maven, JUnit, Spring hay framework. Bộ kiểm thử sử dụng các phương thức `check(...)` tự ném `AssertionError` để có thể chạy mà không phụ thuộc thư viện kiểm thử.

## 4. Module cung cấp dữ liệu: `lab.model`

### File 1 — `src/lab.model/module-info.java`

~~~java
module lab.model {
    exports lab.model.api;
    opens lab.model.view to lab.probe;
}
~~~

Chính sách module:

1. `lab.model.api`: exported, không opened.
2. `lab.model.view`: **chỉ opened tới `lab.probe`**, không khai báo exports.
3. `lab.model.closed`: không export, không open.

Khai báo `opens ... to lab.probe` cho phép **đúng một module đích** được truy cập sâu. Nếu một module `lab.other` cùng thử đọc private field, kết quả vẫn có thể bị từ chối. Đừng thay bằng `open module lab.model` nếu bài toán chỉ cần mở một package cho một công cụ.

### File 2 — `src/lab.model/lab/model/api/PublicOrder.java`

~~~java
package lab.model.api;

public final class PublicOrder {
    private final String secret = "api-private";

    public String number() {
        return "ORD-7";
    }
}
~~~

`PublicOrder` là `public`, và package chứa nó được `exports`. Vì vậy `lab.probe` có thể `import lab.model.api.PublicOrder` và gọi `number()`. Nhưng field `secret` vẫn `private`; chỉ `exports` **chưa đủ** để module khác đọc giá trị field qua Reflection.

### File 3 — `src/lab.model/lab/model/view/AuditView.java`

~~~java
package lab.model.view;

public final class AuditView {
    private final String auditCode = "AUD-42";

    public AuditView() {}
}
~~~

`AuditView` và constructor đều `public` nhưng package không khai báo `exports`; do đó mã nguồn `lab.probe` không thể import kiểu này theo cách Java thông thường. Bài kiểm thử lấy `Class` theo tên, bật truy cập Reflection có kiểm soát và đọc field `auditCode`. Quyền đó phát sinh từ `opens lab.model.view to lab.probe`.

### File 4 — `src/lab.model/lab/model/closed/ClosedService.java`

~~~java
package lab.model.closed;

public final class ClosedService {
    public ClosedService() {}
}
~~~

`ClosedService` cũng là kiểu `public`, constructor `public`; tuy nhiên module không export hoặc open package này. Điều kiện `public` của class/constructor **không vượt qua được ranh giới module**. Demo vẫn có thể lấy `Class<?>` và metadata constructor theo tên, nhưng không thể thực thi constructor từ module kiểm thử bằng quyền truy cập mặc định.

## 5. Module kiểm thử: `lab.probe`

### File 5 — `src/lab.probe/module-info.java`

~~~java
module lab.probe {
    requires lab.model;
}
~~~

Không khai báo `opens` ở phía `lab.probe` để “xin” quyền mở package từ `lab.model`: **module sở hữu package mới quyết định exports/opens của package đó**. `requires` và `opens` phục vụ hai vấn đề khác nhau.

### File 6 — `src/lab.probe/lab/probe/AccessTest.java`

~~~java
package lab.probe;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import lab.model.api.PublicOrder;

public final class AccessTest {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        Module model = PublicOrder.class.getModule();
        Module probe = AccessTest.class.getModule();

        check(model.isNamed() && probe.isNamed(), "named modules required");
        check(model.isExported("lab.model.api", probe), "API must be exported");
        check(!model.isOpen("lab.model.api", probe), "API must not be open");
        check(model.isOpen("lab.model.view", probe), "view must open to probe");
        check(!model.getDescriptor().exports().stream()
                .anyMatch(e -> e.source().equals("lab.model.view")),
                "view has exports declaration");
        check(!model.isExported("lab.model.closed", probe), "closed exported");
        check(!model.isOpen("lab.model.closed", probe), "closed open");
        System.out.println("module rules: PASS");

        PublicOrder order = new PublicOrder();
        check(order.number().equals("ORD-7"), "public API mismatch");
        Object number = PublicOrder.class.getMethod("number").invoke(order);
        check(number.equals("ORD-7"), "public method invoke failed");
        System.out.println("exported public API: PASS");

        Field secret = PublicOrder.class.getDeclaredField("secret");
        check(!secret.trySetAccessible(), "private API must remain closed");
        boolean denied = false;
        try { secret.get(order); }
        catch (IllegalAccessException expected) { denied = true; }
        check(denied, "private API read should fail");
        System.out.println("exported private field: DENIED");

        Class<?> view = Class.forName("lab.model.view.AuditView");
        Constructor<?> ctor = view.getDeclaredConstructor();
        check(ctor.trySetAccessible(), "open constructor expected");
        Object audit = ctor.newInstance();
        Field auditCode = view.getDeclaredField("auditCode");
        check(auditCode.trySetAccessible(), "open private field expected");
        check(auditCode.get(audit).equals("AUD-42"), "audit mismatch");
        System.out.println("qualified opens + private field: PASS");

        Class<?> closed = Class.forName("lab.model.closed.ClosedService");
        Constructor<?> cctor = closed.getDeclaredConstructor();
        check(!cctor.trySetAccessible(), "closed constructor exposed");
        boolean blocked = false;
        try { cctor.newInstance(); }
        catch (IllegalAccessException expected) { blocked = true; }
        check(blocked, "closed constructor must be blocked");
        System.out.println("non-exported non-open constructor: DENIED");
        System.out.println("ALL ACCESS TESTS PASSED");
    }
}
~~~

**Vì sao đoạn mã này là bộ kiểm thử chứ không chỉ trình diễn?**

- Mỗi hành vi quan trọng có `check(...)`; nếu sai, chương trình ném `AssertionError` và không in dòng thành công cuối.
- Kỳ vọng bị từ chối kiểm **cả kết quả của `trySetAccessible()` lẫn exception khi chưa có quyền**.
- Dữ liệu kiểm thử cố định `ORD-7`, `AUD-42` để xác minh method/field đọc đúng.
- Kiểm tra tên module và descriptor để giảm khả năng chạy nhầm trên classpath hoặc bị thay đổi `module-info.java` mà vẫn báo pass.
- Tên package public/opened/closed tách biệt; không phụ thuộc lỗi từ một class không tìm thấy.

## 6. Biên dịch và chạy đúng ở module path

Đứng trong thư mục gốc `reflection-access-lab` (cùng cấp với thư mục `src`). Chạy:

~~~bash
javac --release 17 -d out --module-source-path src -m lab.model,lab.probe
java --module-path out --module lab.probe/lab.probe.AccessTest
~~~

`javac --release 17` giới hạn ngôn ngữ và API công khai theo Java 17, `-d out` lưu output theo module, `--module-source-path src` cho javac biết hai module nguồn và `-m lab.model,lab.probe` chọn các module biên dịch.

Lệnh `java --module-path out --module lab.probe/lab.probe.AccessTest` chạy **module `lab.probe`** và main class `lab.probe.AccessTest`. Không thay `--module-path` bằng `--class-path`: nếu mọi class chạy trên classpath/unnamed module, ranh giới module cần kiểm thử không còn như mong đợi.

**Output kiểm chứng:**

~~~text
module rules: PASS
exported public API: PASS
exported private field: DENIED
qualified opens + private field: PASS
non-exported non-open constructor: DENIED
ALL ACCESS TESTS PASSED
~~~

Chương trình trên đã được biên dịch thành công với `javac --release 17` và chạy trên JDK 24, chỉ sử dụng API được Java 17 hỗ trợ. Output là chính xác khi cấu trúc file và `module-info.java` giữ như ví dụ.

### Ý nghĩa từng kết quả

| Dòng output | Quan sát | Kết luận |
| --- | --- | --- |
| `module rules: PASS` | Hai module đều named; `api` exported; `view` opened cho probe nhưng không có exports declaration; `closed` không mở. | JPMS được cấu hình đúng. |
| `exported public API: PASS` | Cả gọi Java trực tiếp lẫn `Method.invoke` lên public method đều thành công. | `requires` + `exports` phù hợp public API. |
| `exported private field: DENIED` | `getDeclaredField` thấy metadata, `trySetAccessible` trả `false`, `Field.get` ném `IllegalAccessException`. | `exports` không cho phép deep reflection vào private member. |
| `qualified opens + private field: PASS` | `Class.forName` tải kiểu, constructor/field `trySetAccessible` thành công. | `opens ... to lab.probe` cấp quyền Reflection cho đúng target module. |
| `non-exported non-open constructor: DENIED` | Có metadata constructor, nhưng không thể bật accessible và `newInstance` bị chặn. | `public` không bỏ qua package-level module encapsulation. |

## 7. Phân biệt tìm metadata, bật quyền và thực thi

Với một class không được export/open, các giai đoạn là:

1. **Tìm class:** `Class.forName("lab.model.closed.ClosedService")` có thể trả `Class<?>` khi module đã được giải quyết và class loader biết class. **Class loading ≠ Java compile-time access**.
2. **Tìm thành viên:** `getDeclaredConstructor()` hoặc `getDeclaredField(...)` thu metadata về khai báo; API tìm không tự chạy constructor hoặc lấy giá trị field.
3. **Kiểm tra quyền:** `trySetAccessible()` hỏi liệu có thể bỏ kiểm tra truy cập với Reflection hay không. Với package không open/export phù hợp, có thể trả `false`.
4. **Thực thi:** `Constructor.newInstance`, `Method.invoke` hay `Field.get` là những bước thật sự chạy constructor/method hoặc đọc state. Lúc này có thể gặp `IllegalAccessException` hoặc `InvocationTargetException` nếu target code ném lỗi sau khi đã gọi được.

`setAccessible(true)` có thể ném `InaccessibleObjectException` khi không thể bật quyền; `trySetAccessible()` thường thuận tiện hơn cho probe vì trả boolean. **Bật accessible không tự tạo quyền truy cập từ module khác nếu JPMS không cho phép.**

Khi debugging, ghi rõ **giai đoạn thất bại**: không tìm được class, không tìm được member, không bật quyền, hoặc đã gọi vào target code nhưng target ném lỗi. Các lỗi này cần cách sửa khác nhau.

## 8. Một lỗi kiểm thử quan trọng: `isExported(package, target)` không chứng minh có câu lệnh `exports`

Với `opens lab.model.view to lab.probe;`, JDK cho phép deep reflection từ `lab.probe`. Ở runtime, kiểm tra như `Module.isExported("lab.model.view", probe)` **có thể cho kết quả `true` vì package đã được mở cho module đó**, mặc dù descriptor **không** có khai báo `exports lab.model.view`.

Do đó test phủ định sau là **sai mục tiêu** nếu ta muốn chứng minh không có câu lệnh exports:

~~~java
// Sai khi dùng để khẳng định không có khai báo "exports":
check(!model.isExported("lab.model.view", probe), "not exported");
~~~

Muốn kiểm tra đặc tả module, hãy đọc `ModuleDescriptor`:

~~~java
// Mảnh nằm trong main của AccessTest; biến model đã được khai báo.
boolean explicitlyExported = model.getDescriptor().exports().stream()
        .anyMatch(e -> e.source().equals("lab.model.view"));
check(!explicitlyExported, "view should not declare exports");
check(model.isOpen("lab.model.view", probe), "view must open to probe");
~~~

Đoạn trên kiểm tra **hai sự thật khác nhau**: `lab.model.view` không được khai báo `exports` và được `opens` cho module kiểm thử. Đừng dùng một giá trị boolean runtime để suy ngược nguyên văn `module-info.java`.

Mặt khác, nếu cần phân biệt **exports có điều kiện** với exports cho tất cả module, hãy xem `ModuleDescriptor.Exports.isQualified()` và `targets()` hoặc dùng các overload phù hợp của `Module.isExported` theo yêu cầu bài test. Chỉ nhìn một method không đủ để lập lại toàn bộ module descriptor.

## 9. Bốn biến thể bài kiểm thử nên thực hiện

Các thay đổi dưới đây là **thí nghiệm riêng biệt**: chỉnh `module-info.java` hoặc file được chỉ định, biên dịch lại từ đầu rồi dự đoán kết quả. Không ghép tất cả thay đổi vào một lần kiểm thử.

### Biến thể A: Gỡ `opens lab.model.view to lab.probe`

Giữ `AuditView` như cũ nhưng xóa dòng `opens`. Khi chạy, `model.isOpen("lab.model.view", probe)` sẽ sai và test báo fail. Nếu bỏ check về module rule để thử tiếp, `trySetAccessible()` trên constructor/field bên `lab.model.view` không còn được phép. **Đây là minh chứng rằng quyền deep reflection đến từ module owner**.

### Biến thể B: Đổi `exports lab.model.api` thành `opens lab.model.api to lab.probe`

`lab.probe.AccessTest` đang có `import lab.model.api.PublicOrder`. Nếu package chỉ `opens` mà không `exports`, quá trình **biên dịch** module probe không còn hợp lệ vì public API không được export tới module đọc. Deep reflection có thể được cho phép ở runtime nhưng không thay thế compile-time public API. Đừng coi lỗi biên dịch và lỗi Reflection là một.

### Biến thể C: Đổi thành `exports lab.model.api; opens lab.model.api to lab.probe;`

Khi package vừa được export vừa open cho probe, private field `secret` có thể được bật accessible từ `lab.probe`, do đó phép kiểm `!secret.trySetAccessible()` dự kiến thất bại. Điều này minh họa cách `opens` thay đổi chính sách runtime mà không làm method `number()` khác đi.

### Biến thể D: Thêm `exports lab.model.closed;`

Khi đó probe có thể truy cập **public class và public constructor** trong package này bằng Java/Reflection nếu module đọc và các điều kiện khác đáp ứng. Tuy nhiên private member trong package chỉ export vẫn không tự động được mở cho deep reflection. Cần cập nhật assertions từ DENIED sang PASS đúng với chính sách mới.

## 10. Khả năng áp dụng vào thư viện Reflection thực tế

Công cụ của production có thể vận hành với nhiều module owner, nhiều lớp và chính sách khác nhau. Một pipeline an toàn:

1. **Định nghĩa contract:** module nào được đọc, package nào public API, package nào cho Reflection framework cụ thể.
2. **Ưu tiên public API:** có thể dùng getter, constructor/factory public hoặc DTO thay vì deep reflection khi không cần.
3. **Quét metadata có giới hạn:** `getDeclaredFields`/`getDeclaredMethods` có thể tìm private member; không tự suy ra quyền gọi.
4. **Kiểm tra access có kiểm soát:** `trySetAccessible` hoặc các điều kiện module theo `Module.isOpen`; không tự động bật quyền cho mọi member của mọi module.
5. **Xử lý lỗi theo chính sách:** trường bắt buộc không truy cập được thì trả lỗi rõ; trường tùy chọn có thể bị bỏ có ghi chú; không tự lén trả `null` khiến dữ liệu sai.
6. **Tạo test module độc lập:** test code chạy ở **module khác** với module được kiểm để thấy đúng boundary. Test đặt cùng module hoặc chạy classpath có thể che giấu vấn đề.
7. **Dùng quyền tối thiểu:** `opens some.package to specific.framework.module;` thay cho `open module` hoặc `--add-opens` rộng khi có thể.

Không sử dụng `--add-opens` như cách sửa mặc định chỉ để làm test xanh. Cờ runtime này có thể là công cụ chuyển tiếp/môi trường kiểm thử chủ động, nhưng nếu dùng nó mà quên ghi rõ thì test không còn xác nhận module descriptor thật sự đang bảo vệ package.

### Các exception nên phân biệt

| Exception | Giai đoạn thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | Tìm tên class | Module có được resolve? Tên package/class có đúng? Loader có nhìn thấy? |
| `NoSuchMethodException` / `NoSuchFieldException` | Truy vấn metadata | Chữ ký tên/kiểu tham số đúng? `getMethod` hay `getDeclaredMethod`? |
| `IllegalAccessException` | `invoke`, `get`, `newInstance` | Java access rules, `exports`/`opens`, access flag trên member. |
| `InaccessibleObjectException` | `setAccessible(true)` | Package không open tới module của caller hoặc member bị hạn chế bởi quy tắc truy cập. |
| `InvocationTargetException` | Target method/constructor được gọi và ném exception | Đọc `getCause()` để phân biệt lỗi từ target code với lỗi Reflection. |
| `IllegalArgumentException` | Sai receiver, tham số hoặc kiểu argument | Kiểm chữ ký và giá trị truyền vào, không gộp thành lỗi module. |

## 11. Sai lầm thường gặp

- **“Có `requires` là có thể truy cập private member.”** `requires` tạo quan hệ đọc module, không mở mọi package.
- **“`public class` luôn gọi được từ module khác.”** Kiểu public trong package không `exports` có thể bị chặn ở biên dịch và Reflection.
- **“`exports` cũng cho phép `setAccessible(true)` trên private.”** Deep reflection từ module khác thường cần package được `opens` phù hợp.
- **“`opens` nghĩa là mã khác có thể `import` public class.”** `opens` chủ yếu cho truy cập Reflection ở runtime; source-level API vẫn cần `exports`.
- **“Tìm thấy `getDeclaredField` nghĩa là đọc được field.”** Metadata lookup khác với `Field.get`.
- **“Nếu `isExported(package, target)` là true thì descriptor nhất định có `exports`.”** Runtime API và khai báo module không luôn suy ngược được như vậy; đọc `ModuleDescriptor`.
- **“Chạy test trên classpath cũng kiểm được JPMS.”** Classpath/unnamed module có ngữ nghĩa khác; phải đặt các module trên module path.
- **“Thêm `--add-opens` là sửa được code.”** Flag có thể che khuất lỗi quyền trong module descriptor và làm kết quả test không đại diện cho runtime thật.

## 12. Bài tập tự kiểm tra

1. Trong cùng module `lab.model`, gọi `Field.trySetAccessible` tới `PublicOrder.secret` từ code cùng module. So với kết quả trong `lab.probe`, sự khác biệt phát sinh từ điều kiện nào?
2. Gỡ `opens lab.model.view to lab.probe`. Hãy xác định assertion đầu tiên thất bại, sau đó bỏ assertion đó để kiểm tra trực tiếp constructor/field.
3. Thử thêm `exports lab.model.view to lab.probe;` thay cho `opens`. Public constructor gọi được không? Private `auditCode` được mở không? Giải thích từng kết quả.
4. Thêm module thứ ba `lab.other` cùng `requires lab.model`. Nó có đọc private `auditCode` qua Reflection không khi directive vẫn là `opens ... to lab.probe`?
5. Thay `trySetAccessible()` ở package đóng bằng `setAccessible(true)`. Bắt riêng `InaccessibleObjectException`, so sánh exception này với `IllegalAccessException` của `newInstance`.
6. Đo `model.isExported("lab.model.view", probe)` và kiểm tra `model.getDescriptor().exports()`; giải thích vì sao hai quan sát có thể khác kỳ vọng nếu chỉ đọc `module-info.java`.
7. Tạo thêm một package nội bộ chỉ cho serializer `opens ... to specific.serializer.module`. Thiết kế test chứng minh module serializer có quyền mà module ngoài danh sách không có.

**Tiêu chí đạt bài:** hai module thực sự chạy trên module path; module descriptor thể hiện quyền rõ ràng; các trường hợp được phép và bị từ chối đều có assertion; test không phụ thuộc exact exception message; không dựa vào `setAccessible` như quyền vô điều kiện; output cuối chỉ xuất hiện nếu toàn bộ kiểm thử pass.

## 13. Tài liệu chuẩn để đối chiếu

- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isExported`, `isOpen`, `getDescriptor`.
- [Java SE 17 — ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): `exports()`, `opens()` và qualified directives.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible` và các điều kiện module.
- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `getDeclaredField`, `Field.get`, quyền truy cập.
- [Java SE 17 — Constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance` và exception.
- [Java Language Specification, Chương 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): cú pháp và ý nghĩa `requires`, `exports`, `opens`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): cơ chế JPMS và lựa chọn command-line ở runtime.