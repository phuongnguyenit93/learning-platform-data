# Package, lớp khai báo và thành viên public trong kiểu không public (Java Reflection)

## 1. Vấn đề: `public` của thành viên chưa đủ để truy cập được

Trong Java, từ khóa `public` đặt trên **method hoặc field** mô tả mức truy cập của **thành viên đó**. Nó không tự biến **lớp khai báo thành viên** thành một lớp có thể nhìn thấy từ mọi package.

Ví dụ, Java cho phép khai báo lớp cấp cao nhất không có `public`:

```java
package demo.api;

class HiddenGreeting {
    public String greet() {
        return "Hello";
    }
}
```

`HiddenGreeting` có mức truy cập **package-private** vì khai báo lớp không có từ khóa `public`. Method `greet()` là `public`, nhưng code trong `demo.client` không thể trực tiếp khai báo biến kiểu `demo.api.HiddenGreeting` hay import lớp đó. Khi dùng Reflection, code bên ngoài có thể **tìm thấy metadata** của `greet()` mà vẫn bị chặn lúc **gọi method**.

Ba câu hỏi phải tách bạch:

1. **Package nào là ngữ cảnh của code gọi?** Hai lớp thuộc cùng package hay khác package? Có ranh giới module hoặc class loader không?
2. **Thành viên được khai báo trên lớp/interface nào?** Đọc `Method.getDeclaringClass()` hoặc `Field.getDeclaringClass()`; đừng mặc nhiên coi kiểu runtime là lớp khai báo.
3. **Cả lớp khai báo lẫn thành viên có thể truy cập từ nơi gọi không?** `Modifier.isPublic(method.getModifiers())` chỉ trả lời phần **member**, chưa kiểm tra visibility của lớp, package/module và toàn bộ quy tắc truy cập.

Nguyên tắc: **Có thể tra cứu metadata không đồng nghĩa được quyền sử dụng thành viên qua Reflection.**

## 2. Package và mức truy cập của lớp

Một *top-level class* (lớp khai báo trực tiếp trong file, không nằm trong lớp khác) chỉ có thể là `public` hoặc **package-private** ở góc độ access modifier; Java không cho khai báo top-level `private` hay `protected`.

| Khai báo lớp | Code trong cùng package | Code trong package khác |
| --- | --- | --- |
| `public class Api` | Có thể tham chiếu nếu đáp ứng ranh giới module | Có thể tham chiếu nếu package được xuất phù hợp và API tiếp cận được |
| `class Implementation` | Có thể tham chiếu theo quy tắc package | Không thể trực tiếp tham chiếu lớp bằng mã Java thông thường |

Java dùng tên package được khai báo bằng `package ...;` để xác định quan hệ truy cập, không dựa vào tên thư mục tình cờ giống nhau. Ở runtime, danh tính package còn phụ thuộc class loader và module; **hai lớp có cùng chuỗi tên package không mặc nhiên được hưởng package-private access** nếu chúng ở các runtime package khác nhau.

Một thành viên `public` có thể nằm trong lớp package-private; điều này hợp lệ. Trong cùng package, code gọi thường có thể sử dụng lớp và method ấy. Ngoài package, việc truy cập trực tiếp bằng tên lớp sẽ thất bại ngay ở bước biên dịch. Với Reflection, lỗi có thể chỉ xuất hiện khi `Method.invoke(...)` thực hiện kiểm tra truy cập.

Với **nested class**, cần xem cả chuỗi lớp bao ngoài và modifier của nested class. Ví dụ `private static class Impl` có thể chứa `public void run()`, nhưng chữ `public` của `run()` không làm `Impl` thành kiểu có thể tham chiếu từ code bên ngoài. Khả năng truy cập không chỉ là modifier của method.

## 3. Ví dụ Java 17+ hoàn chỉnh: method public nhưng gọi Reflection bị chặn

Ví dụ sau có **hai package** để thể hiện đúng ranh giới: `demo.api` giữ lớp triển khai kín bên trong, còn `demo.client` là người dùng API. Lớp triển khai là package-private, method triển khai là public; giao diện cung cấp hợp đồng public để gọi an toàn.

Tạo cấu trúc:

```text
src/
  demo/
    api/
      GreetingService.java
      Services.java
    client/
      Main.java
```

### Tệp `src/demo/api/GreetingService.java`

```java
package demo.api;

public interface GreetingService {
    String greet();
}
```

### Tệp `src/demo/api/Services.java`

```java
package demo.api;

public final class Services {
    private Services() {}

    public static GreetingService create() {
        return new HiddenGreeting();
    }
}

class HiddenGreeting implements GreetingService {
    @Override
    public String greet() {
        return "Hello";
    }
}
```

`Services` là factory public; `HiddenGreeting` không có `public` nên chỉ là một kiểu package-private. `GreetingService` công khai hành vi cần dùng mà không phơi bày tên lớp triển khai.

### Tệp `src/demo/client/Main.java`

```java
package demo.client;

import demo.api.GreetingService;
import demo.api.Services;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        GreetingService service = Services.create();
        Method impl = service.getClass().getMethod("greet");

        System.out.println("Runtime class: " + service.getClass().getName());
        System.out.println("Class public: "
                + Modifier.isPublic(service.getClass().getModifiers()));
        System.out.println("Method public: "
                + Modifier.isPublic(impl.getModifiers()));
        System.out.println("Declared by: " + impl.getDeclaringClass().getName());
        System.out.println("Normal call: " + service.greet());

        try {
            System.out.println("Reflect impl: " + impl.invoke(service));
        } catch (IllegalAccessException e) {
            System.out.println("Reflect impl: IllegalAccessException");
        }

        Method api = GreetingService.class.getMethod("greet");
        System.out.println("Reflect API: " + api.invoke(service));
    }
}
```

Tại thư mục gốc chứa `src`, tạo thư mục `out` trước khi chạy; các lệnh sau sử dụng đường dẫn tường minh, phù hợp cả shell thông thường và PowerShell:

```bash
mkdir out
javac --release 17 -d out src/demo/api/GreetingService.java src/demo/api/Services.java src/demo/client/Main.java
java -cp out demo.client.Main
```

Kết quả stdout (đã kiểm chứng bằng biên dịch và chạy):

```text
Runtime class: demo.api.HiddenGreeting
Class public: false
Method public: true
Declared by: demo.api.HiddenGreeting
Normal call: Hello
Reflect impl: IllegalAccessException
Reflect API: Hello
```

**Phân tích chính xác từng kết quả:**

- `service.getClass()` trả `HiddenGreeting.class` vì đó là lớp runtime của object mà factory tạo ra, dù biến được khai báo theo interface `GreetingService`.
- `Modifier.isPublic(service.getClass().getModifiers())` trả `false` vì lớp triển khai là package-private.
- `getMethod("greet")` **tìm thấy method public**: nó chỉ tìm theo metadata của các method public trong phạm vi API, không bảo đảm caller có quyền gọi method.
- `impl.getDeclaringClass()` là `HiddenGreeting.class`. Method có modifier `public` nhưng lớp khai báo không accessible từ `demo.client.Main`, nên `impl.invoke(service)` ném `IllegalAccessException`.
- Lời gọi Java thông thường `service.greet()` hợp lệ vì static type `GreetingService` là interface public, method trong interface là public; JVM thực hiện dispatch tới implementation.
- `GreetingService.class.getMethod("greet")` lấy `Method` **khai báo trên interface public**. Gọi `api.invoke(service)` có thể truy cập method của interface rồi dispatch tới implementation; kết quả là `Hello`.

Đây là ví dụ chỉ dùng **classpath/unnamed module**, không cần `module-info.java`. Với named module, cần xét thêm quy tắc `exports`/`opens` ở phần sau.

## 4. “Lớp runtime” và “lớp khai báo” là hai khái niệm khác nhau

Xét một biến `GreetingService service`:

- **Kiểu của biến tại compile time:** `GreetingService` (public interface).
- **Kiểu runtime của object:** `HiddenGreeting` (package-private class).
- **Lớp khai báo của một đối tượng `Method`:** thứ được trả về bởi `method.getDeclaringClass()`. Nếu lấy method từ `HiddenGreeting` thì đó là `HiddenGreeting`; nếu lấy từ `GreetingService` thì đó là `GreetingService`.

Đặc biệt khi có kế thừa, `SomeSubclass.class.getMethod("action")` có thể trả `Method` khai báo ở một superclass hoặc interface, thay vì ở `SomeSubclass`. Mã biên dịch và công cụ sinh lớp cũng có thể bổ sung method chuyển tiếp, nên **không suy đoán declaring class chỉ từ tên lớp dùng khi gọi `getMethod`**. Luôn xem `getDeclaringClass()` của đối tượng `Method` thực tế.

Đừng nhầm hai API sau:

- `method.getDeclaringClass()`: kiểu **khai báo method**.
- `someClass.getDeclaringClass()`: khi gọi trên đối tượng `Class` của nested/member class, cung cấp thông tin về lớp chứa khai báo kiểu đó (không phải “lớp khai báo một method”).

Đối với `Field` và `Constructor` cũng có `getDeclaringClass()`. Lớp khai báo có thể không public dù member constructor/method/field trông như public trong metadata.

## 5. `getMethod`, `getDeclaredMethod` và kiểm tra truy cập

| API | Nó trả về cái gì? | Nó có tự bỏ qua kiểm tra access không? |
| --- | --- | --- |
| `type.getMethod("name", ...)` | Method public trong phạm vi tra cứu công khai, có thể kế thừa | Không |
| `type.getMethods()` | Mảng các method public theo hợp đồng Reflection | Không |
| `type.getDeclaredMethod("name", ...)` | Method **khai báo trực tiếp** tại `type`, không phụ thuộc public/private của method | Không |
| `type.getDeclaredMethods()` | Mảng các method khai báo trực tiếp, gồm private/protected/package-private | Không |
| `method.invoke(receiver, args...)` | Thực thi method, nếu receiver và quyền truy cập hợp lệ | **Có kiểm tra** truy cập khi chưa bật suppression hợp lệ |
| `method.canAccess(receiver)` | Kiểm tra tại nơi gọi hiện tại có thể truy cập member trên receiver phù hợp hay không | Chỉ kiểm tra, không tự cấp quyền |

Việc `getDeclaredMethod` nhìn thấy một method `private` không làm method đó trở thành public. Ngược lại, `getMethod` tìm thấy method public trong lớp không public cũng không khiến `invoke` mặc nhiên thành công.

**Thứ tự kiểm tra khi gặp sự cố** nên là: (1) kiểu runtime; (2) `getDeclaringClass()`; (3) modifier của declaring class và member; (4) package của caller; (5) module và chính sách `exports`/`opens`; (6) object nhận lời gọi, đối số và ngoại lệ thực thi.

Đối tượng `Method` được lưu/cached có thể được gọi ở những vị trí code khác nhau. Kiểm tra quyền truy cập thông thường được thực hiện đối với caller phản chiếu ở thời điểm gọi; đừng kết luận rằng một `Method` đã tìm thấy ở nơi có quyền thì tự mang quyền ấy tới mọi vị trí sử dụng.

## 6. Các cách giải quyết đúng theo thiết kế

### 6.1. Ưu tiên hợp đồng public

Nếu bạn kiểm soát API, hãy khai báo method trong **public interface** hoặc public class có thể truy cập và truyền object triển khai qua hợp đồng đó. Ví dụ `GreetingService.class.getMethod("greet")` trong bài chạy được mà không cần can thiệp kiểm tra truy cập.

Cách này cũng giữ được khả năng thay implementation mà không buộc phía dùng phải biết tên lớp package-private. Đối với public method trong public interface/public class, vẫn cần package được export thích hợp nếu chạy giữa các named module.

### 6.2. Công bố phương thức qua một public facade

Một public facade có thể **tự khai báo** phương thức public rồi ủy quyền cho implementation nội bộ:

```java
package demo.api;

public final class GreetingFacade {
    public String greet() {
        return new HiddenGreeting().greet();
    }
}
```

Đây là **mảnh code thêm vào ví dụ ở mục 3**, sử dụng `HiddenGreeting` trong cùng package; lưu tên file `GreetingFacade.java` nếu muốn dùng thực tế. Khi phía client lấy `GreetingFacade.class.getMethod("greet")`, declaring class là một kiểu public. Đây là cách thích hợp nếu public class là hình thức API mong muốn.

Lưu ý nếu facade **chỉ kế thừa** method từ một superclass không public, không thể khẳng định method Reflection nhận được có declaring class public. Kết quả có thể chịu ảnh hưởng method kế thừa/forwarder được biên dịch. Muốn hợp đồng nhất quán, tự khai báo/override method trên public facade và kiểm tra `getDeclaringClass()`.

### 6.3. Đưa code gọi vào cùng package khi đó là quyền nội bộ

Code trong cùng runtime package với lớp package-private thường được quyền truy cập lớp và public member của nó. Dùng cách này cho **mã nội bộ** khi thiết kế package cho phép; không nên thay đổi package của client tùy tiện chỉ để vượt ranh giới API. Cùng chuỗi tên package nhưng class loader/module khác có thể không tạo cùng runtime package.

### 6.4. `setAccessible`/`trySetAccessible` chỉ khi thực sự cần deep reflection

`AccessibleObject.trySetAccessible()` cố bật bỏ qua kiểm tra truy cập theo khả năng được phép và trả boolean; `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu Java module system không cho phép. Việc suppression thành công phụ thuộc lớp khai báo, module của caller, các package `opens`/`exports` và trường hợp cụ thể.

- Trên **classpath/unnamed module**, deep reflection đối với lớp của ứng dụng thường được phép, nên có thể quan sát thấy `trySetAccessible()` thành công.
- Giữa **named module**, một package chỉ `exports` chưa đủ để tự do deep-reflect member/lớp không public; `opens` tới module gọi (hoặc cấu hình mở tương đương) mới cho phép một số trường hợp suppression.
- Không lấy việc thử `setAccessible(true)` làm phương án sửa mặc định khi đã có public interface/facade đúng thiết kế. Không có bảo đảm có thể vượt mọi ranh giới access trên mọi JDK/module.

## 7. Vai trò của JPMS: `exports` khác `opens`

Từ Java 9, ngoài quyền truy cập theo Java language, named module còn có ranh giới package.

- `exports demo.api;` trong module cung cấp: cho các module đọc được module ấy truy cập **public types và public members** của package theo quy tắc Java. Nó **không làm `HiddenGreeting` thành public**.
- `opens demo.api;` hoặc `opens demo.api to some.module;`: cho phép deep reflection theo phạm vi mở; không đồng nghĩa mở quyền compile-time reference như `exports`.
- Package **không export** của named module có thể làm Reflection từ module khác bị chặn ngay cả với public class/method, nếu thiếu cấu hình truy cập tương ứng.
- `--add-exports` và `--add-opens` có thể dùng trong tình huống tích hợp/phân tích được kiểm soát, nhưng phải xác định đúng source module, package và target module; không sử dụng bừa bãi làm giải pháp API lâu dài.

Ví dụ, nếu `demo.api` nằm trong named module `demo.library` và `demo.client` trong `demo.app`, cần quan hệ module thích hợp (`requires` ở caller, `exports demo.api` ở thư viện) để mã Java ở phía client dùng `GreetingService`. Kể cả khi package được export, `HiddenGreeting` vẫn package-private, nên dùng `Method` khai báo trực tiếp tại lớp ấy để gọi từ module khác vẫn có thể bị `IllegalAccessException`. Một **public interface được export** vẫn là bề mặt API phù hợp.

## 8. Phân biệt lỗi tra cứu, lỗi quyền và lỗi khi method chạy

| Hiện tượng | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodException` tại `getMethod(...)` | Không có method public phù hợp theo tên/chữ ký được tra cứu | Kiểm tra tham số `Class<?>...`, overload, và `getDeclaredMethod` nếu cần |
| `IllegalAccessException` tại `invoke(...)` | Reflection không có quyền gọi method theo kiểm tra truy cập hiện hành | Xác định `getDeclaringClass()`, package/module, chọn public API thích hợp |
| `InaccessibleObjectException` tại `setAccessible(true)` | Không thể bật suppression do giới hạn encapsulation | Kiểm tra cấu hình `opens` và sự cần thiết của deep reflection |
| `InvocationTargetException` tại `invoke(...)` | Method đích đã được gọi và tự ném exception; nguyên nhân nằm trong `getCause()` | Xử lý lỗi logic/runtime của method đích, không quy ngay về visibility |
| `IllegalArgumentException` tại `invoke(...)` | Receiver sai kiểu hoặc đối số/số lượng/kiểu không phù hợp | Kiểm tra object và chữ ký method |

Ví dụ câu sau là sai về lập luận:

> “Method có modifier `public` và `getMethod` trả về thành công, vậy `invoke` chắc chắn thành công.”

Bài chạy ở mục 3 là phản ví dụ: cả hai điều kiện đúng nhưng `impl.invoke(service)` vẫn bị `IllegalAccessException` vì `HiddenGreeting` không public đối với caller ở package khác.

## 9. Quy trình thực hành khi viết công cụ Reflection

1. Xác định **public API contract** mà phía gọi được phép dùng (interface hoặc facade).
2. Nếu phải truy vấn một class runtime, ghi nhận `type.getName()` và `Modifier.isPublic(type.getModifiers())`.
3. Với mỗi method/field, kiểm tra `getDeclaringClass()` và modifier của cả member lẫn kiểu khai báo; cân nhắc mọi lớp bao ngoài nếu là nested type.
4. Phân biệt rõ thao tác **khám phá metadata** và thao tác **gọi/đọc thành viên**. Bản ghi metadata không thay cho một kiểm tra quyền hợp lệ.
5. Giữ nguyên ranh giới package/module khi có thể. Với plugin/framework cần deep reflection, tài liệu hóa package phải `opens` và xử lý trường hợp không được cấp quyền.
6. Bắt chính xác `IllegalAccessException` khi invoke, và tách khỏi `InvocationTargetException` vốn là lỗi phát sinh từ method đích.

## 10. Tự kiểm tra

1. `class Worker { public void run() {} }` nằm ở `demo.impl` và là top-level class package-private. Tại sao `demo.client` không thể trực tiếp viết `new Worker()`?
2. Tại sao `Modifier.isPublic(method.getModifiers()) == true` chưa đủ để kết luận `method.invoke(...)` thành công?
3. Với ví dụ `HiddenGreeting`, đối tượng `Method` của `GreetingService.class.getMethod("greet")` và của `service.getClass().getMethod("greet")` có cùng `getDeclaringClass()` không? Kết quả `invoke` khác nhau như thế nào?
4. Đối với named module, `exports` có làm một top-level package-private class thành public không? Khi nào `opens` có tác dụng?
5. `InvocationTargetException` có chứng minh caller bị từ chối truy cập method không?

**Đáp án định hướng:** (1) class package-private không accessible từ package khác; (2) quyền truy cập còn phụ thuộc lớp khai báo, caller và module; (3) lần lượt là public `GreetingService` và package-private `HiddenGreeting`, chỉ lời gọi qua interface thành công trong chương trình mẫu; (4) không, `opens` cho deep reflection có kiểm soát; (5) không, nó bọc exception do method đích ném.

**Ghi nhớ:** Khi Reflection xử lý một thành viên `public` nhưng lớp khai báo không public, hãy đặt câu hỏi **“`Method.getDeclaringClass()` là ai, và caller có thể truy cập lớp đó không?”**. Tách riêng modifier của member, accessibility của declaring type, package và JPMS sẽ giúp hiểu chính xác vì sao đọc được metadata nhưng gọi bị chặn; public interface/facade là lời giải sạch cho API được dùng từ package khác.