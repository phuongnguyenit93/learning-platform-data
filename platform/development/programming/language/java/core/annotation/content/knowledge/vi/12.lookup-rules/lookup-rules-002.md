# getAnnotation so với getDeclaredAnnotation trong Java

Khi đọc annotation bằng reflection, hai phương thức có tên rất giống nhau nhưng **khác về phạm vi tra cứu**:

- `getAnnotation(AnnotationType.class)`: tìm một annotation của kiểu chỉ định nếu annotation ấy **present** (*hiện diện theo quy tắc Java*). Với `Class`, kết quả có thể đến từ superclass khi kiểu annotation được đánh dấu `@Inherited`.
- `getDeclaredAnnotation(AnnotationType.class)`: chỉ tìm annotation **directly present** (*được khai báo trực tiếp trên phần tử đang xét*). Phương thức này **không lấy annotation kế thừa**.

Cả hai đều thuộc API `java.lang.reflect.AnnotatedElement`, được các lớp reflection như `Class`, `Method`, `Field`, `Constructor` triển khai. Chúng trả về annotation tương ứng hoặc `null` nếu không tìm thấy theo phạm vi tra cứu.

Sự khác biệt quan sát rõ nhất với **annotation có `@Inherited` gắn trên một class cha và được truy vấn ở class con**. Tuy nhiên, không nên hiểu rằng `getAnnotation()` “tìm trên mọi nơi có liên quan”: nó có các quy tắc chặt chẽ, đặc biệt ở interface, method override và repeatable annotation.

## 1. Mô hình cốt lõi: directly present và present

Hãy tưởng tượng một annotation `@Role("ADMIN")` xuất hiện trên khai báo `BaseController`, còn `AdminController extends BaseController` không khai báo annotation ấy.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Role("ADMIN")
class BaseController {}

class AdminController extends BaseController {}
```

Đây là **các khai báo hợp lệ**, chưa có phương thức `main`. `@Inherited` cho phép Java reflection khi truy vấn **class con** nhận một annotation của kiểu `Role` từ superclass, nếu class con không khai báo trực tiếp kiểu annotation đó.

Các phép đọc sau có kết quả:

```java
Role a = AdminController.class.getAnnotation(Role.class);
// a != null, a.value().equals("ADMIN")

Role b = AdminController.class.getDeclaredAnnotation(Role.class);
// b == null

Role c = BaseController.class.getDeclaredAnnotation(Role.class);
// c != null, c.value().equals("ADMIN")
```

Đây là **đoạn biểu thức minh họa**, có thể đặt trong method sau khi các class trên đã tồn tại.

### Bảng so sánh trực tiếp

| Thuộc tính | `getAnnotation(A.class)` | `getDeclaredAnnotation(A.class)` |
| --- | --- | --- |
| Kiểu trả về | `A` hoặc `null` | `A` hoặc `null` |
| Đọc annotation trực tiếp trên phần tử? | Có | Có |
| Với `Class`: có thể thấy annotation từ superclass? | Có, nếu annotation type là `@Inherited` và thỏa quy tắc kế thừa | Không |
| Tự đọc annotation trên interface đã `implements`? | Không | Không |
| Tự lấy annotation từ method bị override? | Không | Không |
| Tự bung nhiều annotation `@Repeatable` khỏi container? | Không; dùng `getAnnotationsByType` | Không; dùng `getDeclaredAnnotationsByType` |
| Trả về gì nếu không có annotation hợp lệ trong phạm vi? | `null` | `null` |
| Có cần runtime retention khi dùng reflection? | Có | Có |

Về khái niệm trong `AnnotatedElement`:

- **Directly present:** annotation được khai báo trực tiếp trên phần tử, có metadata runtime phù hợp.
- **Present:** directly present **hoặc**, khi phần tử là class và annotation type có tính inheritable, được tìm thấy thông qua superclass theo quy tắc `@Inherited`.
- **Indirectly present:** một annotation repeatable nằm bên trong container annotation.
- **Associated:** phạm vi dùng cho `getAnnotationsByType`, gồm trực tiếp/gián tiếp và một số trường hợp kế thừa.

Các thuật ngữ này không hoán đổi cho nhau. Với repeatable annotations, sự khác biệt giữa **present** và **associated** đặc biệt quan trọng.

## 2. @Inherited quyết định được tìm lên superclass hay không

`@Inherited` là meta-annotation chuẩn của `java.lang.annotation`. Nó được gắn trên **định nghĩa kiểu annotation**:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {}
```

Cần import các kiểu liên quan như trong ví dụ phần 1. Với một annotation type như `Audited`, các class con có thể tra được annotation từ superclass dù không trực tiếp khai báo.

Điểm mấu chốt:

1. `@Inherited` **không khiến annotation tự được sao chép thành dòng khai báo trên class con**; nó điều khiển **cách tìm annotation**.
2. Cơ chế chuẩn chỉ duyệt **superclass của class**, không duyệt các interface do class triển khai.
3. Nếu class con trực tiếp khai báo **cùng kiểu annotation**, khai báo của con được ưu tiên khi gọi `getAnnotation()`.
4. Nếu không có `@Inherited`, `getAnnotation()` trên class con sẽ **không** tự lấy annotation chỉ gắn ở cha.
5. Muốn truy xuất bằng reflection lúc chạy, kiểu annotation phải có `@Retention(RetentionPolicy.RUNTIME)`. Nếu không đặt `@Retention`, mặc định là `CLASS`.

### Có @Inherited và không có @Inherited

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ConfigSource {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DirectOnly {}

@ConfigSource
@DirectOnly
class Parent {}

class Child extends Parent {}
```

Đây là **các khai báo minh họa**, cần các import tương ứng.

Với `Child.class`:

| Lời gọi | Kết quả |
| --- | --- |
| `getAnnotation(ConfigSource.class)` | Khác `null`, nhận từ `Parent` |
| `getDeclaredAnnotation(ConfigSource.class)` | `null` |
| `getAnnotation(DirectOnly.class)` | `null` |
| `getDeclaredAnnotation(DirectOnly.class)` | `null` |

Nếu gọi trên `Parent.class`, cả hai phương thức đều thấy từng annotation vì chúng được khai báo trực tiếp trên `Parent`.

### Class con khai báo cùng annotation thì sao?

```java
@Role("PARENT")
class Account {}

@Role("CHILD")
class PremiumAccount extends Account {}
```

Đây là **đoạn minh họa** sử dụng kiểu `Role` từ phần 1.

- `PremiumAccount.class.getAnnotation(Role.class).value()` trả về `"CHILD"`.
- `PremiumAccount.class.getDeclaredAnnotation(Role.class).value()` cũng trả về `"CHILD"`.
- Nếu muốn biết cha khai báo giá trị gì, hãy tra trực tiếp `Account.class`.

Java không gộp `"PARENT"` với `"CHILD"` thành một giá trị; với kiểu annotation đơn lẻ, khai báo trên lớp con che trường hợp cùng kiểu từ cha khi tìm kiếm.

## 3. Không tự kế thừa annotation từ interface

Một nhầm lẫn phổ biến: class triển khai interface đã được đánh dấu `@Inherited` thì `getAnnotation()` trên class đó sẽ trả về annotation ở interface.

Không đúng. Java chỉ xét **superclass** theo quy tắc này:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Marker {}

@Marker
interface ServiceApi {}

class ServiceImpl implements ServiceApi {}
```

Đây là **đoạn minh họa**, cần các import annotation chuẩn.

```java
ServiceApi.class.getAnnotation(Marker.class) != null;   // true
ServiceImpl.class.getAnnotation(Marker.class) == null;  // true
ServiceImpl.class.getDeclaredAnnotation(Marker.class) == null; // true
```

Hai điều cuối là `true` vì `implements ServiceApi` không phải quan hệ `extends` giữa hai class. Dù interface có thể mở rộng interface khác, `@Inherited` vẫn không tự tạo đường truyền qua cây interface.

Nếu một framework muốn “tìm annotation qua các interface”, nó phải chủ động duyệt các interface và định nghĩa cách xử lý xung đột. Đó không phải hành vi mặc định của `Class.getAnnotation()`.

## 4. Với method, field và constructor: không có tìm kiếm kế thừa kiểu class

Vì `getAnnotation()` nằm trong `AnnotatedElement`, bạn cũng có thể gọi trên `Method`, `Field` và `Constructor`. Nhưng **không được lấy quy tắc @Inherited của class áp vào các phần tử này**.

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Operation {
    String value();
}

class ParentService {
    @Operation("base")
    public void execute() {}
}

class ChildService extends ParentService {
    @Override
    public void execute() {}
}
```

Đây là **đoạn minh họa**, cần các import `Retention`, `RetentionPolicy`, `Target`, `ElementType`.

Nếu tìm method `execute()` khai báo trong `ChildService`:

```java
java.lang.reflect.Method childMethod =
    ChildService.class.getDeclaredMethod("execute");

childMethod.getAnnotation(Operation.class);          // null
childMethod.getDeclaredAnnotation(Operation.class);  // null
```

Dù method của cha có `@Operation("base")`, method **override** của con là một khai báo khác. Java không sao chép annotation từ khai báo bị override sang khai báo override.

### Phân biệt tìm Method object với tìm annotation của Method

Có hai thao tác khác nhau:

- `Class.getMethod("execute")[ [T]]: tìm một **public Method object**, có thể tìm thấy method được thừa hưởng từ superclass nếu class con không override.
- `Method.getAnnotation(Operation.class)`: đọc annotation của **Method object đã nhận được**, theo quy tắc `AnnotatedElement`.

Nếu `ChildService` **không override** `execute()`, `ChildService.class.getMethod("execute")` có thể trả về `Method` phản chiếu method **khai báo tại `ParentService`**. Khi đó `getAnnotation(Operation.class)` có thể thấy `@Operation("base")` vì đó chính là annotation trên method cha đã tìm được, **không phải** vì `Method.getAnnotation()` kế thừa annotation qua override.

Tương tự:

- Field bị **shadow/hide** ở class con không tự nhận annotation của field cùng tên ở cha.
- Constructor của class con không kế thừa từ constructor của class cha; annotation gắn trên constructor cha không tự hiện trên constructor con.
- `@Inherited` có phạm vi hữu ích khi annotation type được dùng trên **class declaration**, không làm annotation trên method/field/constructor tự truyền qua quan hệ thành viên.

## 5. Ví dụ Java 17+ độc lập: so sánh trong một chương trình

Tạo một tệp **`AnnotationLookupDemo.java`** và chép toàn bộ mã dưới đây. Ví dụ có:

- `InheritedFlag` được đánh dấu `@Inherited`.
- `LocalFlag` không được đánh dấu `@Inherited`.
- Một class con không khai báo thêm annotation.
- Một class con ghi annotation cùng kiểu để override metadata nhìn thấy được.
- Một class triển khai interface có annotation.
- Một method override không nhận annotation từ method cha.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InheritedFlag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface LocalFlag {
    String value();
}

@InheritedFlag("base")
@LocalFlag("base-only")
class Base {
    @LocalFlag("base-method")
    public void execute() {}
}

class Child extends Base {
    @Override
    public void execute() {}
}

@InheritedFlag("child")
class ExplicitChild extends Base {}

@InheritedFlag("interface")
interface MarkedInterface {}

class Implementation implements MarkedInterface {}

public class AnnotationLookupDemo {
    private static String value(InheritedFlag flag) {
        return flag == null ? "null" : flag.value();
    }

    public static void main(String[] args) throws NoSuchMethodException {
        System.out.println("child.getAnnotation="
                + value(Child.class.getAnnotation(InheritedFlag.class)));

        System.out.println("child.getDeclaredAnnotation="
                + value(Child.class.getDeclaredAnnotation(InheritedFlag.class)));

        System.out.println("child.localFlagAbsent="
                + (Child.class.getAnnotation(LocalFlag.class) == null));

        System.out.println("explicit.getAnnotation="
                + value(ExplicitChild.class.getAnnotation(InheritedFlag.class)));

        System.out.println("explicit.getDeclaredAnnotation="
                + value(ExplicitChild.class.getDeclaredAnnotation(InheritedFlag.class)));

        System.out.println("interface.impl="
                + value(Implementation.class.getAnnotation(InheritedFlag.class)));

        Method parent = Base.class.getDeclaredMethod("execute");
        Method child = Child.class.getDeclaredMethod("execute");

        System.out.println("parent.method="
                + parent.getAnnotation(LocalFlag.class).value());

        System.out.println("child.method.getAnnotationAbsent="
                + (child.getAnnotation(LocalFlag.class) == null));

        System.out.println("child.method.getDeclaredAnnotationAbsent="
                + (child.getDeclaredAnnotation(LocalFlag.class) == null));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 AnnotationLookupDemo.java
java AnnotationLookupDemo
```

Stdout **chính xác**:

```text
child.getAnnotation=base
child.getDeclaredAnnotation=null
child.localFlagAbsent=true
explicit.getAnnotation=child
explicit.getDeclaredAnnotation=child
interface.impl=null
parent.method=base-method
child.method.getAnnotationAbsent=true
child.method.getDeclaredAnnotationAbsent=true
```

Diễn giải:

1. `child.getAnnotation=base`: `Child` không khai báo `InheritedFlag`, nhưng annotation type có `@Inherited`, nên nhận từ `Base`.
2. `child.getDeclaredAnnotation=null`: `Child` không có khai báo `InheritedFlag` trực tiếp.
3. `child.localFlagAbsent=true`: `LocalFlag` chỉ được khai báo ở `Base` và không phải kiểu annotation có `@Inherited`.
4. Hai dòng `explicit...=child`: `ExplicitChild` ghi `@InheritedFlag("child")` trực tiếp, nên cả hai phương thức lấy giá trị của con.
5. `interface.impl=null`: `Implementation` chỉ `implements MarkedInterface`, không phải subclass của interface này theo cây superclass.
6. `parent.method=base-method`: Method object từ `Base` có annotation `@LocalFlag("base-method")`.
7. Hai dòng `child.method...Absent=true`: `Child.execute()` override method, nhưng không ghi annotation trực tiếp. Không có cơ chế tự kế thừa annotation của method bị override.

Chương trình chỉ đọc annotation và in ra kết quả; **annotation không tự kích hoạt nghiệp vụ**. Không có library ngoài JDK và không cần command-line argument.

### Nếu bỏ @Retention(RUNTIME) thì sao?

Annotation có retention mặc định `RetentionPolicy.CLASS`, tức compiler có thể lưu vào class file nhưng reflection thông thường lúc chạy không truy xuất như trong chương trình trên. Nếu xóa `@Retention(RetentionPolicy.RUNTIME)` khỏi `InheritedFlag`, phép `getAnnotation(InheritedFlag.class)` sẽ không trả về annotation runtime được như ví dụ và những dòng tương ứng thay đổi.

Đừng nhầm `@Inherited` với `@Retention`: một cái mô tả **phạm vi tìm kiếm qua class cha**, một cái xác định annotation có **tồn tại để đọc tại runtime** hay không.

## 6. getAnnotations và getDeclaredAnnotations: cùng nguyên tắc ở dạng mảng

Ngoài phương thức đọc một kiểu annotation, Java cung cấp:

```java
java.lang.annotation.Annotation[] all =
    Child.class.getAnnotations();

java.lang.annotation.Annotation[] direct =
    Child.class.getDeclaredAnnotations();
```

Đây là **biểu thức minh họa** với `Child` của ví dụ hoàn chỉnh.

- `getAnnotations()` trả về các annotation **present** trên phần tử. Khi là class, danh sách có thể bao gồm kiểu annotation `@Inherited` từ superclass.
- `getDeclaredAnnotations()` chỉ trả các annotation **directly present**; không nhận từ class cha.
- Trả về **mảng rỗng** khi không có, không phải `null`.
- Thứ tự của các annotation khác kiểu trong mảng thường **không nên dùng làm hợp đồng nghiệp vụ**; hãy xét theo annotation type.

Hai cặp API đối chiếu:

| Muốn đọc | Một kiểu annotation | Tất cả annotation hiện diện theo phạm vi |
| --- | --- | --- |
| Hiện diện / có thể inherited trên class | `getAnnotation(A.class)` | `getAnnotations()` |
| Khai báo trực tiếp | `getDeclaredAnnotation(A.class)` | `getDeclaredAnnotations()` |

Chọn API dựa vào câu hỏi nghiệp vụ: cần **cấu hình hiệu lực** thừa hưởng qua class cha, hay cần biết **class hiện tại thực sự khai báo gì**?

## 7. Repeatable annotation: vì sao cần getAnnotationsByType?

`@Repeatable` cho phép gắn nhiều annotation cùng kiểu lên một phần tử. Compiler có thể biểu diễn nhiều lần xuất hiện thông qua **container annotation**. Do đó, việc gọi `getAnnotation(A.class)` hoặc `getDeclaredAnnotation(A.class)` chưa chắc lấy được những annotation `A` được chứa gián tiếp.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RoleName {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    RoleName[] value();
}

@RoleName("READ")
@RoleName("WRITE")
class PermissionBase {}

class PermissionChild extends PermissionBase {}
```

Đây là **các khai báo minh họa hợp lệ**; không có method `main`. Kiểu container `Roles` được đánh dấu `@Inherited` tương thích với kiểu annotation `RoleName`. Với `PermissionChild`:

```java
// Các biểu thức minh họa:
PermissionChild.class.getAnnotation(RoleName.class);         // null
PermissionChild.class.getDeclaredAnnotation(RoleName.class); // null

PermissionChild.class.getAnnotationsByType(RoleName.class).length; // 2
PermissionChild.class.getDeclaredAnnotationsByType(RoleName.class).length; // 0
```

Tại sao có kết quả khác nhau?

1. Hai lần `@RoleName` trên `PermissionBase` được compiler biểu diễn qua một container `@Roles`.
2. `getAnnotation(RoleName.class)` tìm **một annotation RoleName present**; nó **không tự giải nén container**.
3. `getAnnotationsByType(RoleName.class)` là API hỗ trợ repeatable annotation: nó xem xét các annotation **associated**, bao gồm trường hợp nằm trong container.
4. `PermissionChild` không khai báo trực tiếp `RoleName` hay `Roles`, nên `getDeclaredAnnotationsByType(RoleName.class)` trả về mảng rỗng. Phiên bản không có `Declared` có thể tìm lên superclass nhờ các quy tắc tương ứng của repeatable `@Inherited`.

### Khi con tự ghi repeatable annotation

Nếu `PermissionChild` ghi một `@RoleName("ADMIN")` trực tiếp, `getAnnotationsByType(RoleName.class)` trên con trả annotation liên quan trực tiếp tới con; nó **không cộng dồn mặc định** `READ`/`WRITE` từ cha. Khi Java quyết định kiểu annotation đó đã có thông tin trực tiếp/gián tiếp trên con, việc tra lên superclass cho kiểu ấy không còn cần thiết.

Vì vậy, khi viết code hỗ trợ annotation lặp, dùng:

- `getAnnotationsByType(A.class)` nếu muốn đọc tất cả annotation cùng kiểu *associated*, có xét trường hợp kế thừa theo chuẩn.
- `getDeclaredAnnotationsByType(A.class)` nếu muốn đọc tất cả annotation cùng kiểu có mặt trực tiếp hoặc gián tiếp qua container **ngay trên phần tử hiện tại**.

Không thể chỉ thay `getAnnotation` bằng `getDeclaredAnnotation` mà mong xử lý đúng danh sách repeatable.

## 8. Phân biệt khai báo annotation, meta-annotation và type-use

### Meta-annotation không tự “truyền” qua getAnnotation

Giả sử:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tracked {}

@Tracked
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface AuditEnabled {}

@AuditEnabled
class BillingService {}
```

Đây là các **khai báo minh họa**, cần import các annotation chuẩn. `AuditEnabled` được **meta-annotated** bằng `Tracked`, nhưng `BillingService` chỉ khai báo trực tiếp `AuditEnabled`.

```java
BillingService.class.getAnnotation(Tracked.class);       // null
AuditEnabled.class.getAnnotation(Tracked.class);         // khác null
```

Java reflection thuần túy không tự đi vào định nghĩa mọi annotation đang có rồi tổng hợp chúng thành annotation của class. Một framework có thể hỗ trợ meta-annotation traversal, nhưng đó là logic bổ sung của framework.

### Type-use annotation cần API phản chiếu khác

`Class.getAnnotation()` và `Method.getAnnotation()` chủ yếu đọc **declaration annotations**. Nếu annotation nằm trên **lần sử dụng kiểu**, chẳng hạn:

```java
// Giả sử @Mark cho phép TYPE_USE.
java.util.List<@Mark String> values;
```

annotation ở đây thuộc type argument `String`, không tự nằm trên field `values`. Cần đi qua `Field.getAnnotatedType()`, `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` và API `AnnotatedType.getAnnotation()` để đọc đúng vị trí.

Không đánh đồng `getDeclaredAnnotation()` với “đọc mọi annotation nằm bên trong khai báo hiện tại”. Nó chỉ đổi phạm vi **directly present** tại `AnnotatedElement` cụ thể bạn đang gọi.

## 9. Quy trình chọn đúng phương thức khi xây framework

**Bước 1 — Xác định phần tử cần đọc.** Đó là `Class`, `Method`, `Field`, `Constructor`, `Parameter` hay `AnnotatedType`? Một method đã override và method ở cha là hai phần tử khác nhau.

**Bước 2 — Xác định chính sách tìm kiếm.** Nếu cấu hình được phép kế thừa qua class hierarchy theo `@Inherited`, cân nhắc `Class.getAnnotation`. Nếu cần kiểm tra khai báo **cục bộ** phục vụ validation, diff hoặc phát hiện override, dùng `getDeclaredAnnotation`.

**Bước 3 — Kiểm tra retention.** Reflection không thấy annotation có retention `SOURCE` hoặc `CLASS` bằng những lời gọi runtime này; đối với runtime, cần `RUNTIME`.

**Bước 4 — Xét repeatable.** Nếu kiểu annotation có `@Repeatable` và có thể xuất hiện nhiều lần, ưu tiên API `getAnnotationsByType` / `getDeclaredAnnotationsByType`; đừng cố lấy bằng một `getAnnotation` duy nhất.

**Bước 5 — Xem giới hạn interface/override.** Java không tự duyệt interface để “kế thừa annotation”; không tự kế thừa metadata của method bị override. Nếu cần quy tắc nghiệp vụ đó, công cụ phải tự duyệt.

**Bước 6 — Xử lý null, mảng rỗng và lỗi cấu hình.** Với `getAnnotation`, luôn kiểm tra `null` trước khi gọi element như `value()`. Với API trả về mảng, kiểm tra `length` hoặc duyệt mảng; không giả định có kết quả.

**Bước 7 — Viết test với class cha/con.** Tạo một class không có annotation, một class con có override annotation, một interface được gắn annotation, một method override và một repeatable container. Một bài test rõ ràng tốt hơn suy luận từ tên API.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`getAnnotation()` luôn truy lên toàn bộ parent/interface” | Chỉ có quy tắc kế thừa chuẩn qua **superclass** đối với annotation type `@Inherited` trên class |
| “`getDeclaredAnnotation()` cũng lấy từ superclass” | Chỉ nhận annotation **trực tiếp** trên phần tử đang tra |
| “Thêm `@Inherited` thì mọi annotation trên method cũng kế thừa” | Không. `@Inherited` không áp dụng cho method override theo cách đó |
| “Con khai báo annotation cùng kiểu thì hệ thống tự gộp với cha” | Thường dùng khai báo trực tiếp của con; không tự merge |
| “`getAnnotation()` luôn lấy ra repeatable annotations” | Với các annotation gián tiếp trong container, dùng `getAnnotationsByType` |
| “`getDeclaredAnnotation()` thấy tất cả type-use lồng trong generic” | Phải đọc đúng `AnnotatedType` tương ứng |
| “Annotation `@Retention(CLASS)` vẫn được `getAnnotation()` truy ra” | Reflection runtime cần `RUNTIME` |
| “`getAnnotation()` không thấy annotation nghĩa là class không có metadata gì” | Có thể annotation nằm ở type-use, repeatable container, interface/framework quy ước, hoặc thiếu runtime retention |
| “Đọc `@Tracked` trên annotation type sẽ làm class được gắn annotation ấy gián tiếp” | Java không tự suy ra meta-annotation như một annotation trên class dùng nó |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `Base` có `@Inherited @interface Flag` với `@Flag` trên khai báo class, còn `Child extends Base` không khai báo `@Flag`. Phương thức nào thấy annotation trên `Child.class`?

**Đáp án:** `getAnnotation(Flag.class)` nếu annotation có retention `RUNTIME` và đúng quy tắc `@Inherited`. `getDeclaredAnnotation(Flag.class)` trả về `null`.

**Câu 2.** Vì sao `Child.class.getDeclaredAnnotation(Flag.class)` có thể trả về `null` trong khi `Child.class.getAnnotation(Flag.class)` khác `null`?

**Đáp án:** Cái thứ nhất đòi annotation **khai báo trực tiếp**; cái thứ hai cho phép trường hợp **present** nhờ `@Inherited` trên superclass.

**Câu 3.** Một interface được gắn annotation `@Inherited`, class triển khai interface có tự thấy annotation khi gọi `getAnnotation()` không?

**Đáp án:** Không. Java không lấy annotation từ interface theo cơ chế `@Inherited`.

**Câu 4.** Method ở subclass override method cha có annotation `@Action`. `getAnnotation(Action.class)` trên method **override** có tự trả annotation của method cha không?

**Đáp án:** Không. Phải tự định nghĩa chính sách tìm metadata ở method cha nếu ứng dụng cần.

**Câu 5.** Nếu annotation `@Tag` được lặp hai lần và chứa trong `@Tags`, phương thức nào đọc đủ hai giá trị?

**Đáp án:** `getAnnotationsByType(Tag.class)` hoặc `getDeclaredAnnotationsByType(Tag.class)`, tùy cần xét trường hợp kế thừa hay chỉ khai báo ngay trên phần tử.

**Câu 6.** `getDeclaredAnnotations()` khi không có annotation trả `null` hay mảng rỗng?

**Đáp án:** Mảng rỗng.

**Câu 7.** Khi nào nên chọn `getDeclaredAnnotation()` cho hệ thống cấu hình?

**Đáp án:** Khi cần xác nhận phần tử hiện tại **tự khai báo** annotation, ví dụ quyết định một class có override metadata cấu hình cha hay không; dùng `getAnnotation()` khi chính sách thực sự cho phép kế thừa theo chuẩn.

## Nguồn tham khảo

- [Java SE 17 API — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): định nghĩa directly present, present, associated và các phương thức tra cứu.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): hành vi `getAnnotation`, `getDeclaredAnnotation` và các API liên quan.
- [Java SE 17 API — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): giới hạn kế thừa annotation trên class.
- [Java SE 17 API — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): container annotation và nhiều annotation cùng kiểu.
- [Java Language Specification 17, §9.6.4.3 — @Inherited](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3).

**Ghi nhớ:** `getDeclaredAnnotation()` trả lời “phần tử **này tự khai báo** annotation gì?”; `getAnnotation()` trả lời “annotation **present theo quy tắc Java** là gì?”. Với class hierarchy, `@Inherited` có thể làm hai câu trả lời khác nhau. Với repeatable annotation, interface hoặc method override, phải chọn API và chính sách tìm kiếm chính xác thay vì suy luận từ tên hàm.
