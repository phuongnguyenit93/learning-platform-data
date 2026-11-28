# Phân biệt tìm được metadata với được phép gọi hoặc truy cập member

## 1. Vấn đề: nhìn thấy mô tả chưa có nghĩa được sử dụng

Trong Java Reflection, có hai câu hỏi khác nhau:

1. **Có tìm được metadata của một thành viên (member) không?** Chẳng hạn lấy được đối tượng `Method` mô tả một phương thức `private`, hoặc đối tượng `Field` mô tả một trường không công khai.
2. **Mã hiện tại có quyền thực hiện thao tác trên thành viên đó không?** Chẳng hạn gọi `Method.invoke(...)`, đọc `Field.get(...)`, ghi `Field.set(...)` hoặc tạo đối tượng qua `Constructor.newInstance(...)`.

Lấy được metadata là bước **khám phá cấu trúc**; thực hiện hành vi là bước **kiểm tra quyền truy cập và gọi/đọc/ghi thực tế**. Hai bước có điều kiện riêng. Một framework có thể lấy được `Method` của phương thức `private` bằng `getDeclaredMethod(...)` nhưng vẫn nhận `IllegalAccessException` khi gọi `invoke(...)`.

Bài học nằm trong chương **Quyền reflection** của `JAVA_VERSION_JAVA18`, thuộc nội dung học Java 18 vẫn có giá trị trên JDK hiện đại. Các thay đổi nội bộ về Core Reflection từ Java 18 không làm mất đi phân biệt căn bản giữa metadata, kiểm tra quyền truy cập của ngôn ngữ Java và ranh giới module. Nội dung sử dụng API công khai còn được hỗ trợ, phù hợp yêu cầu kiểm chứng hợp đồng API trên JDK đang chạy.

Mô hình tổng quát:

```text
Class<?> target
    |
    +-- getDeclaredMethod / getDeclaredField
    |       |
    |       +-- trả về Method / Field: có metadata
    |               |
    |               +-- canAccess(receiver): được truy cập ngay lúc này?
    |               |
    |               +-- trySetAccessible(): có thể bật bỏ qua kiểm tra
    |               |                      truy cập thông thường không?
    |               |
    |               +-- invoke / get / set: thực hiện, vẫn có thể lỗi
    |
    +-- Không tìm được thành viên: NoSuchMethodException /
                                      NoSuchFieldException
```

**Quy tắc chính:** Không dùng việc gọi `getDeclaredMethod(...)` hoặc `getDeclaredField(...)` thành công làm bằng chứng rằng `invoke(...)` hoặc `get(...)` chắc chắn thành công.

## 2. Những API dùng để khám phá metadata

Reflection cung cấp hai nhóm phương thức quan trọng trên `java.lang.Class`:

| API | Thành viên có thể tìm thấy | Điểm cần nhớ |
|---|---|---|
| `getMethod(name, parameterTypes...)` | Phương thức `public` phù hợp, kể cả thành viên công khai được kế thừa theo hợp đồng API | Không tự chứng minh caller được quyền gọi khi có module hoặc lớp không truy cập được |
| `getDeclaredMethod(name, parameterTypes...)` | Phương thức được khai báo trực tiếp trong kiểu, bao gồm `private`, `protected`, package-private và `public` | Không tự tìm khai báo kế thừa |
| `getField(name)` | Trường `public` phù hợp, gồm trường được kế thừa | Không bảo đảm quyền đọc/ghi thực tế |
| `getDeclaredField(name)` | Trường khai báo trực tiếp, bất kể modifier | Trường `private` vẫn có thể được mô tả |
| `getConstructor(parameterTypes...)` | Constructor `public` phù hợp | Chỉ là bước tra cứu, chưa tạo đối tượng |
| `getDeclaredConstructor(parameterTypes...)` | Constructor khai báo trực tiếp với bất kỳ mức truy cập | Có thể lấy constructor `private` dù chưa được phép gọi |

Các biến thể số nhiều như `getDeclaredMethods()` hoặc `getDeclaredFields()` cũng chủ yếu dùng để **liệt kê mô tả**. Việc thấy tên, kiểu tham số, kiểu trả về hoặc modifier không đồng nghĩa với quyền gọi, đọc hoặc ghi.

Ví dụ về mặt ý tưởng:

```java
Method method = SomeType.class.getDeclaredMethod("secretAction");
System.out.println(method.getName());       // Có metadata
System.out.println(method.getModifiers());  // Có modifier

// Hai thao tác sau là câu hỏi khác:
// method.invoke(receiver);
// method.trySetAccessible();
```

`Class.getDeclaredMethod(...)` có thể ném `NoSuchMethodException` nếu không có khai báo khớp tên và danh sách kiểu tham số. Đây là lỗi **tra cứu**, khác với `IllegalAccessException` do **không được phép thực thi**.

## 3. Ví dụ đầy đủ: tìm thấy `private Method` nhưng chưa gọi được

Lưu đoạn mã sau vào một tệp tên `ReflectionAccessDemo.java`, trên **classpath** của một ứng dụng Java thông thường. Hai lớp ở đây là **hai lớp top-level độc lập** cùng package mặc định; `Settings` không phải lớp lồng của `ReflectionAccessDemo`. Cách tổ chức này giúp minh họa kiểm tra `private` một cách rõ ràng.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionAccessDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Settings receiver = new Settings();

        // Thành viên public: tra cứu và gọi thành công.
        Method publicMethod = Settings.class.getMethod("label");
        System.out.println(publicMethod.invoke(receiver));

        // Thành viên private: lấy metadata vẫn thành công.
        Method privateMethod =
                Settings.class.getDeclaredMethod("secretLabel");

        System.out.println(privateMethod.getName());
        System.out.println(privateMethod.canAccess(receiver));

        try {
            privateMethod.invoke(receiver);
        } catch (IllegalAccessException expected) {
            System.out.println(expected.getClass().getSimpleName());
        }

        // Trên classpath thông thường, package của unnamed module
        // được mở cho reflection, nên thao tác này thành công.
        boolean enabled = privateMethod.trySetAccessible();
        System.out.println(enabled);
        System.out.println(privateMethod.canAccess(receiver));

        if (enabled) {
            System.out.println(privateMethod.invoke(receiver));
        }

        // Trường private có cùng phân biệt metadata / quyền truy cập.
        Field field = Settings.class.getDeclaredField("code");
        System.out.println(field.canAccess(receiver));

        if (field.trySetAccessible()) {
            System.out.println(field.get(receiver));
        }
    }
}

class Settings {
    private final String code = "A-17";

    public String label() {
        return "settings";
    }

    private String secretLabel() {
        return "private:" + code;
    }
}
```

Kết quả dự kiến khi chạy trong môi trường classpath thông thường:

```text
settings
secretLabel
false
IllegalAccessException
true
true
private:A-17
false
A-17
```

Những điểm cần giải thích:

1. `getMethod("label")` tìm được phương thức `public`. Vì caller và lớp đích ở cùng package trên classpath, `invoke(receiver)` được phép thực hiện.
2. `getDeclaredMethod("secretLabel")` tìm được một phương thức `private`. Bước tìm metadata không ném lỗi chỉ vì thành viên đó có mức truy cập `private`.
3. `privateMethod.canAccess(receiver)` trả `false` trước khi bật quyền truy cập đặc biệt: mã ở lớp `ReflectionAccessDemo` không có quyền gọi phương thức `private` của lớp top-level `Settings` theo quy tắc truy cập Java thông thường.
4. `privateMethod.invoke(receiver)` ném `IllegalAccessException` do thiếu quyền truy cập; bản thân `secretLabel()` chưa được thực thi.
5. `trySetAccessible()` trả `true` trong tình huống này. Sau đó `canAccess(receiver)` trả `true` và `invoke(receiver)` chạy được phương thức.
6. `getDeclaredField("code")` cũng tìm được metadata của một trường `private`; quyền đọc qua `Field.get(receiver)` là bước khác.

Ví dụ cố ý minh họa cơ chế truy cập. Trong mã sản phẩm, nên ưu tiên API công khai được thiết kế cho nhu cầu sử dụng thực tế thay vì đọc trực tiếp trạng thái nội bộ.

### Điều gì xảy ra khi chọn nhầm phương thức tra cứu?

Nếu thay dòng:

```java
Settings.class.getDeclaredMethod("secretLabel");
```

bằng:

```java
Settings.class.getMethod("secretLabel");
```

thì `getMethod(...)` không tìm thấy thành viên `private` và ném `NoSuchMethodException`. Khi dùng `getDeclaredMethod(...)`, bước tra cứu lại thành công, nhưng `invoke(...)` vẫn có thể ném `IllegalAccessException` nếu chưa có quyền truy cập.

Vì thế cần phân biệt rõ:

- **Không tìm thấy:** `NoSuchMethodException` / `NoSuchFieldException` ở bước tìm metadata.
- **Tìm thấy nhưng chưa được phép:** `IllegalAccessException` khi gọi hoặc đọc/ghi.
- **Đã gọi thành công nhưng mã đích ném lỗi:** với `Method.invoke(...)`, lỗi do phương thức đích ném thường được bọc trong `InvocationTargetException`.

## 4. `canAccess()` và `trySetAccessible()` trả lời câu hỏi nào?

`java.lang.reflect.AccessibleObject` là lớp nền của `Method`, `Field` và `Constructor`. Các API hiện đại cần hiểu chính xác gồm:

| API | Công dụng | Kết quả hoặc lưu ý |
|---|---|---|
| `canAccess(receiver)` | Kiểm tra caller hiện tại có thể truy cập thành viên ở trạng thái hiện tại hay không | Trả `boolean`; truyền receiver đúng kiểu cho instance method/field |
| `trySetAccessible()` | Thử bật chế độ bỏ qua kiểm tra truy cập thông thường | Trả `true` nếu có thể bật; `false` nếu không thể do ranh giới truy cập, chẳng hạn module chưa mở package |
| `setAccessible(true)` | Yêu cầu bật chế độ tương tự nhưng báo lỗi khi không cho phép | Có thể ném `InaccessibleObjectException` trong trường hợp không thể bật do quy tắc module |
| `setAccessible(false)` | Tắt cờ bỏ qua kiểm tra truy cập trên đối tượng reflection đó | Không sửa modifier `private`/`public` của thành viên gốc |

`canAccess(...)` là phép kiểm tra **khả năng truy cập hiện tại**; nó không thay đổi quyền. `trySetAccessible()` thử thay đổi cờ trên đối tượng reflection cụ thể. Không phải mọi trường hợp đều có thể bật cờ: Java Platform Module System (JPMS) kiểm soát truy cập sâu qua ranh giới module.

Lưu ý cách truyền receiver:

```java
Method instanceMethod = Settings.class.getDeclaredMethod("label");
boolean a = instanceMethod.canAccess(new Settings());

Method staticMethod = Integer.class.getMethod(
        "parseInt", String.class);
boolean b = staticMethod.canAccess(null);
```

Với phương thức **instance**, cần receiver không null và là instance phù hợp của lớp khai báo. Với phương thức **static** và constructor, đối số của `canAccess(...)` là `null`. Truyền sai loại receiver vào `canAccess(...)` có thể gây `IllegalArgumentException`; nó không chỉ đơn thuần trả `false` cho mọi đầu vào sai.

**Không kiểm tra xong rồi giả định chắc chắn thành công:** dữ liệu receiver, chữ ký, loại thao tác và ngoại lệ của mã đích vẫn phải được xử lý khi gọi thực tế. Đối với framework, cách an toàn là sử dụng `trySetAccessible()` có kiểm tra kết quả, hoặc thiết kế API/module để truy cập hợp lệ ngay từ đầu.

## 5. JPMS: `exports` và `opens` giải quyết hai nhu cầu khác nhau

Từ Java 9, mô hình **named module** bổ sung ranh giới truy cập bên cạnh `public`, `protected`, package-private và `private`. Phân biệt hai khai báo:

- `exports package.name`: cho phép module đọc được module này **truy cập kiểu public và thành viên public** trong package theo quy tắc thông thường. Nó **không mặc định cho phép** reflection đi sâu vào thành viên `private`.
- `opens package.name`: cho phép **deep reflection** vào package theo các điều kiện API; ví dụ một framework có thể thử `trySetAccessible()` với thành viên không công khai. `opens` **không tự cung cấp quyền import các kiểu ở compile time** giống `exports`.

Nếu cần cả hai loại truy cập, module có thể khai báo cả `exports` và `opens` cho cùng một package.

### Ví dụ hai module tách biệt

Trong module `example.model`, giả sử có lớp dữ liệu:

```java
// example.model/api/Profile.java
package example.model.api;

public final class Profile {
    private final String token;

    public Profile(String token) {
        this.token = token;
    }

    public String displayName() {
        return "profile";
    }
}
```

Module đích khai báo:

```java
// example.model/module-info.java
module example.model {
    exports example.model.api;
    opens example.model.api to example.reflector;
}
```

Module phía gọi khai báo:

```java
// example.reflector/module-info.java
module example.reflector {
    requires example.model;
}
```

Trong code thuộc module `example.reflector`, ta có thể viết (đặt trong một phương thức có xử lý ngoại lệ reflection):

```java
Profile profile = new Profile("sample-token");

Method publicMethod =
        Profile.class.getMethod("displayName");
System.out.println(publicMethod.invoke(profile)); // profile

Field privateField = Profile.class.getDeclaredField("token");
System.out.println(privateField.canAccess(profile)); // false

boolean allowed = privateField.trySetAccessible();  // true do opens
System.out.println(allowed);

if (allowed) {
    Object value = privateField.get(profile);
    System.out.println(value instanceof String);    // true
}
```

Giả định đã import `Profile`, `Method`, `Field` và xử lý ngoại lệ được kiểm tra. Đây là minh họa hoạt động của khai báo module; khi dùng thật, không nên in hoặc tiết lộ giá trị nhạy cảm của trường `token`.

Nếu module `example.model` **chỉ còn**:

```java
module example.model {
    exports example.model.api;
}
```

thì `example.reflector` vẫn có thể sử dụng constructor và phương thức `public` của `Profile`. Nó cũng có thể **tìm metadata** của `token` bằng `getDeclaredField("token")`, nhưng `trySetAccessible()` để đọc trường `private` từ module khác sẽ trả `false` vì package không được mở cho module gọi. Gọi `setAccessible(true)` trong hoàn cảnh không thể bật quyền có thể ném `InaccessibleObjectException`.

Nếu bỏ `exports` mà vẫn giữ `opens`, framework có thể có đường deep reflection phù hợp, nhưng các lớp bên ngoài không thể chỉ đơn giản `import example.model.api.Profile` để dùng như API public ở compile time.

### Bảng đối chiếu quyền truy cập giữa named modules

Giả sử caller ở module **A**, đối tượng `Method`/`Field` thuộc module **B**:

| Trạng thái package trong B | Public API ở A | Deep reflection của A |
|---|---|---|
| Package `exports` cho A, chưa `opens` | Được phép theo quy tắc đọc module và Java access | Không tự được phép truy cập thành viên private |
| Package `opens` cho A, chưa `exports` | Không trở thành API public để import | Có thể thử bật truy cập sâu |
| Package vừa `exports` vừa `opens` cho A | Truy cập public API | Có thể thử bật truy cập sâu |
| Package không `exports` và không `opens` cho A | Không được truy cập public API thông thường | Không thể dùng cờ reflection để vượt ranh giới module |
| Caller và member cùng module | Áp dụng access thông thường | Có thể bật truy cập sâu trong cùng module |

Bảng trên giả định các điều kiện khác phù hợp, chẳng hạn module readability, receiver, modifier và quyền của caller. Các khai báo có thể giới hạn phạm vi bằng `exports ... to ...` hoặc `opens ... to ...`; chỉ module được nêu tên mới có quyền tương ứng.

**Điểm dễ nhầm:** một đối tượng `Method` của phương thức `public` trong package **không exported** vẫn có thể xuất hiện khi khám phá metadata, nhưng lệnh `invoke(...)` từ module bên ngoài có thể bị từ chối bởi kiểm tra truy cập. Modifier `public` của phương thức là điều kiện cần nhưng chưa đủ khi xét ranh giới named module.

## 6. Phân biệt các loại lỗi theo bước thực thi

Để gỡ lỗi đúng, hãy xác định lỗi xảy ra ở **bước nào**:

| Hoạt động | Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
|---|---|---|---|
| `getDeclaredMethod(...)` | `NoSuchMethodException` | Sai tên, sai danh sách parameter types, phương thức chỉ được kế thừa | Chọn đúng tên/chữ ký hoặc `getMethod(...)` |
| `getDeclaredField(...)` | `NoSuchFieldException` | Không có field khai báo trực tiếp trong lớp | Xem lớp khai báo thực tế và quy tắc kế thừa |
| `Method.invoke(...)` | `IllegalAccessException` | Caller không được phép gọi member | Kiểm tra modifier, lớp khai báo, module exports/opens |
| `Field.get(...)` / `Field.set(...)` | `IllegalAccessException` | Caller không được phép đọc/ghi field | Truy cập qua API public hoặc mở package hợp lệ |
| `Constructor.newInstance(...)` | `IllegalAccessException` | Constructor hoặc lớp khai báo không truy cập được | Dùng constructor public hoặc thiết kế factory |
| `trySetAccessible()` | `false` | Không thể bật chế độ truy cập sâu | Điều chỉnh module descriptor nếu thực sự cần deep reflection |
| `setAccessible(true)` | `InaccessibleObjectException` | Không thể bật chế độ truy cập sâu, thường do module chưa mở | Kiểm tra `opens`, không buộc truy cập vào nội bộ JDK |
| `Method.invoke(...)` | `InvocationTargetException` | Phương thức đích **đã được gọi** và ném ngoại lệ | Xem `getCause()` để phân biệt lỗi nghiệp vụ |
| `Method.invoke(...)` | `IllegalArgumentException` | Sai số lượng/kiểu đối số hoặc receiver không tương thích | Kiểm tra chữ ký và đối tượng nhận lời gọi |

Chú ý: `IllegalAccessException` **khác** với `IllegalArgumentException`. Có đúng quyền truy cập mà truyền nhầm receiver hoặc đối số thì vẫn thất bại. Ngược lại, đối số đúng không thay thế quyền truy cập.

Nếu thân phương thức đích ném `IllegalStateException`, reflection có thể chuyển ngoại lệ ấy thành cause của `InvocationTargetException`:

```java
try {
    method.invoke(receiver);
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable fromTarget = e.getCause();
    // Phân loại / xử lý lỗi do logic của chính phương thức đích ném.
}
```

Trường hợp này chứng minh một khác biệt quan trọng: **thất bại vì không được truy cập** xảy ra trước khi code đích chạy; **thất bại từ bản thân code đích** xảy ra sau khi cơ chế reflection đã gọi thành công phương thức.

## 7. Quy tắc Java language access vẫn có ý nghĩa

JPMS không thay thế toàn bộ kiểm tra truy cập của ngôn ngữ Java. Ngay cả trong một module có `opens`, việc truy cập thông thường còn phụ thuộc vào:

- `public`: kiểu/thành viên công khai, nhưng với named modules còn cần package và module cho phép.
- `protected`: quyền truy cập phụ thuộc vào package, quan hệ lớp con và ngữ cảnh receiver.
- **Package-private** (không ghi modifier): chủ yếu dành cho mã trong cùng runtime package theo quy tắc ngôn ngữ/runtime.
- `private`: giới hạn trong phạm vi khai báo và quy tắc truy cập của Java (bao gồm nestmates), trừ khi reflection được phép bỏ qua kiểm tra thông thường.

Trong Java hiện đại, **nestmates** có thể truy cập thành viên private của nhau theo quy tắc JVM. Vì vậy, nếu minh họa `IllegalAccessException`, đừng tùy tiện đặt caller trong một lớp lồng của chính lớp đích rồi cho rằng private chắc chắn không truy cập được. Ví dụ ở phần 3 dùng hai lớp top-level tách biệt để tránh nhầm lẫn.

Ngoài ra, `Method.invoke(...)` gọi một phương thức instance có thể override vẫn thực hiện virtual dispatch theo receiver. Việc lấy được `Method` của lớp cha không có nghĩa reflection bỏ qua kiểm tra truy cập hoặc bỏ qua triển khai override của lớp con. **Quyền truy cập** và **lựa chọn thân phương thức** là hai cơ chế riêng.

## 8. Thiết kế framework và ứng dụng theo nguyên tắc quyền tối thiểu

Một serializer, test framework, dependency injection container hoặc ORM thường cần đọc metadata để xác định ánh xạ. Cách triển khai phù hợp trên JDK hiện đại:

1. **Khám phá trước, xác nhận quyền sau.** Dùng `getDeclared...` khi cần nhìn thấy thành viên không public; kiểm tra quyền bằng `canAccess(receiver)` hoặc thử `trySetAccessible()` với xử lý `false`.
2. **Ưu tiên API công khai.** Public factory, constructor, accessor hoặc interface ổn định giúp giảm phụ thuộc vào chi tiết triển khai và `opens`.
3. **Chỉ mở đúng package cho đúng framework.** Khi deep reflection thật sự là yêu cầu, cân nhắc `opens some.package to framework.module` thay vì mở mọi package một cách rộng rãi.
4. **Không mặc định mọi JVM đều là classpath.** Tác vụ hoạt động trong unnamed module có thể thất bại sau khi chuyển thành named modules vì ranh giới truy cập khác nhau.
5. **Phân loại lỗi theo nguyên nhân.** `NoSuchMethodException` là vấn đề metadata/chữ ký; `IllegalAccessException` là vấn đề quyền; `InvocationTargetException` chứa lỗi của mã đích.
6. **Không sử dụng reflection để chỉnh sửa trường `final` như một kỹ thuật cấu hình thông thường.** Khả năng đọc hoặc bật cờ truy cập không đồng nghĩa được bảo đảm có thể sửa mọi `final field`; các JDK hiện đại tiếp tục hạn chế và kiểm soát việc thay đổi trạng thái bất biến.
7. **Không phụ thuộc API nội bộ của JDK.** Các package không công khai hoặc không mở trong JDK không phải giao diện ổn định để truy cập sâu.

Khi dùng `MethodHandles.Lookup`, tư duy về quyền truy cập vẫn cần được duy trì: quá trình tìm method handle cũng được kiểm tra quyền của lookup context; `privateLookupIn(...)` có yêu cầu truy cập/module tương ứng. Không nên chuyển API từ reflection sang method handles rồi giả định các giới hạn module tự biến mất.

## 9. Kiểm chứng trên JDK hiện đang sử dụng

Để phân biệt rõ hợp đồng API với giả định theo môi trường, có thể thiết kế ma trận thử nghiệm sau:

| Tình huống kiểm tra | Kết quả mong đợi |
|---|---|
| Tìm `private` method bằng `getDeclaredMethod` | Lấy được metadata nếu khai báo tồn tại |
| Tìm cùng method bằng `getMethod` | `NoSuchMethodException` vì không phải public method |
| Gọi `private` method từ top-level caller không có quyền và chưa bật cờ | `IllegalAccessException` |
| Trên classpath, gọi `trySetAccessible` với private member ứng dụng | Thành công trong cấu hình thông thường của ví dụ |
| Từ named module khác, package chỉ `exports` | Public API hoạt động; bật quyền cho private member bị từ chối nếu không có điều kiện mở khác |
| Từ named module khác, package `opens` tới caller | Có thể bật quyền deep reflection phù hợp |
| Gọi method đích chủ động ném ngoại lệ | Nhận `InvocationTargetException` và xem `getCause()` |
| Truyền receiver sai kiểu cho instance method | `IllegalArgumentException` |

Nên chạy thử cả trên classpath và module path khi ứng dụng thực sự hỗ trợ hai cách đóng gói, tránh rút kết luận từ một chế độ duy nhất. Khi kiểm tra module, hãy ghi rõ **module của caller**, **module của class đích**, package có `exports` hay `opens` và giá trị trả về của `trySetAccessible()`.

### Câu hỏi tự kiểm tra

1. Vì sao `SomeClass.class.getDeclaredField("password")` có thể thành công, nhưng `field.get(object)` lại ném `IllegalAccessException`?
2. `getDeclaredMethod(...)` và `getMethod(...)` khác nhau thế nào khi phương thức là `private`?
3. Trong named modules, `exports` cho phép gì và vì sao vẫn chưa đủ để đọc một trường `private` từ module khác?
4. Khi nào nên dùng `trySetAccessible()` và cần xử lý kết quả `false` như thế nào?
5. Phân biệt ba lỗi `NoSuchMethodException`, `IllegalAccessException` và `InvocationTargetException` theo thời điểm xảy ra.
6. Một public method thuộc package không được export có nhất thiết gọi được qua `Method.invoke(...)` từ module bên ngoài hay không?

**Ghi nhớ:** Có được `Method`, `Field` hoặc `Constructor` chỉ xác nhận rằng mã đã khám phá được metadata. Quyền gọi/đọc/ghi được đánh giá theo quy tắc truy cập Java, trạng thái access override và ranh giới module trên JDK hiện tại. Xác định chính xác từng bước giúp thiết kế reflection an toàn, dễ gỡ lỗi và tương thích khi nâng JDK.
