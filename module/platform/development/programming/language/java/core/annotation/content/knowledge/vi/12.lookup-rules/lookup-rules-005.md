# Khi nào Java Reflection nhìn xuyên qua annotation chứa (container annotation)?

## 1. Câu hỏi chính

Từ Java 8, một annotation type có thể được khai báo là **repeatable** bằng `@Repeatable`, tức có thể gắn cùng annotation nhiều lần tại một vị trí. Java dùng một **containing annotation type** (annotation chứa, gọi ngắn là *container*) để biểu diễn các annotation thành phần.

Ví dụ:

```java
@Role("READ")
@Role("WRITE")
class DocumentService {}
```

Hai dòng trên hợp lệ nếu `Role` được khai báo là repeatable với container `Roles`. Khi biên dịch, hai `@Role` này được biểu diễn gián tiếp thông qua một annotation `@Roles` với mảng chứa các `@Role`. Do vậy có một điểm quan trọng: **không phải mọi API reflection đều tự mở container**.

- `getAnnotation(Role.class)` tìm **một annotation `Role` hiện diện** theo quy tắc của `AnnotatedElement`; nó **không tự bung `Roles`** để lấy một `Role` thành phần.
- `getAnnotationsByType(Role.class)` là API **có hiểu repeatable annotation**: tìm các `Role` xuất hiện trực tiếp hoặc **gián tiếp trong container tương ứng**, rồi trả một mảng.
- `getDeclaredAnnotationsByType(Role.class)` cũng mở container, nhưng chỉ lấy những annotation được khai báo **trên chính phần tử đang xét**; không tìm lên superclass.
- `getAnnotation(Roles.class)` tìm chính **annotation chứa**, không tự động chuyển kết quả thành `Role[]`; sau khi nhận `Roles`, bạn có thể gọi `value()` để lấy mảng phần tử.

Nói ngắn gọn: **muốn thấy toàn bộ các annotation lặp kiểu T, dùng các phương thức `*AnnotationsByType(T.class)`**. API đơn lẻ `getAnnotation(T.class)` có thể trả `null` ngay cả khi source cho thấy nhiều `@T`.

## 2. Định nghĩa repeatable annotation và container đúng cách

Để ví dụ `@Role` lặp được, cần **cả hai kiểu annotation**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

Đây là ví dụ khai báo hỗ trợ, chưa có `main`.

Giải thích từng phần:

1. `@Repeatable(Roles.class)` được đặt trên **annotation type thành phần** `Role`; tham số cho biết annotation type nào đóng vai trò container.
2. `Roles` phải khai báo **element có tên chính xác `value()`** với kiểu trả về **`Role[]`**. Một container chứa `String[]` hoặc `Object[]` không được xem là container hợp lệ của `Role`.
3. Nếu container còn có các element khác ngoài `value()`, những element đó phải có giá trị mặc định theo các ràng buộc Java áp dụng cho container.
4. Retention và target giữa `Role` và `Roles` phải tương thích theo quy tắc `@Repeatable`. Ví dụ cả hai đều `@Retention(RUNTIME)` và `@Target(TYPE)` cho một chương trình đọc annotation trên class bằng reflection.
5. `RUNTIME` là cần thiết cho ví dụ reflection. Nếu dùng retention `CLASS` (mặc định khi không khai báo `@Retention`), annotation có thể được lưu trong class file nhưng **không** được các API reflection runtime này trả về.
6. Nếu annotation thành phần được gắn `@Inherited`, annotation container tương ứng cũng phải thỏa quy tắc `@Inherited`; phần sau sẽ minh họa cả hai cùng mang `@Inherited`.

Trong trường hợp trên, hai cú pháp:

```java
@Role("READ")
@Role("WRITE")
class DocumentService {}
```

và:

```java
@Roles({@Role("READ"), @Role("WRITE")})
class DocumentService {}
```

mô tả cùng hai phần tử `Role` với cùng thứ tự đối với API tra cứu theo kiểu `Role`. **Chúng là hai cách viết thay thế để minh họa, không phải hai khai báo `DocumentService` được đặt cùng nhau trong một tệp Java.**

Không nên hiểu Java tạo ra hai annotation loại `Role` được coi là “trực tiếp hiện diện” giống hệt với trường hợp chỉ có một `@Role`. Khi lặp nhiều lần, mô hình reflection phân biệt annotation **trực tiếp** và annotation **hiện diện gián tiếp** trong container.

## 3. Bốn khái niệm nền tảng: trực tiếp, gián tiếp, present và associated

Javadoc của giao diện `AnnotatedElement` phân biệt một số quan hệ giữa một annotation và phần tử phản chiếu đang xét.

### 3.1. Directly present — hiện diện trực tiếp

Nếu khai báo chỉ có một `@Role("READ")` thì `Role` có thể hiện diện trực tiếp trên phần tử. Vì vậy:

```java
@Role("READ")
class SingleRole {}
```

`SingleRole.class.getAnnotation(Role.class)` sẽ tìm được `Role` khi có retention `RUNTIME`. `getAnnotationsByType(Role.class)` cũng trả một mảng một phần tử.

### 3.2. Indirectly present — hiện diện gián tiếp thông qua container

Nếu source khai báo nhiều `@Role` cùng đích:

```java
@Role("READ")
@Role("WRITE")
class TwoRoles {}
```

thì `Role` được coi là **indirectly present** qua `Roles`. Với cấu hình retention `RUNTIME` trong bài:

- `TwoRoles.class.getAnnotation(Role.class)` trả `null` nếu `Role` chỉ xuất hiện gián tiếp.
- `TwoRoles.class.getAnnotation(Roles.class)` trả một `Roles` có thể gọi `value()`.
- `TwoRoles.class.getAnnotationsByType(Role.class)` trả hai `Role`, theo thứ tự `READ`, `WRITE`.
- `TwoRoles.class.getDeclaredAnnotationsByType(Role.class)` cũng trả hai `Role` vì chúng được khai báo tại chính class này.

Điểm cốt lõi: **sự tồn tại của container không làm `getAnnotation(Role.class)` tự đổi sang API đa phần tử**.

### 3.3. Present — hiện diện theo quy tắc tra cứu đơn lẻ

Một annotation type `T` được xem là **present** trên phần tử khi nó trực tiếp hiện diện, hoặc trong những trường hợp `Class` và `@Inherited` phù hợp, được kế thừa theo quy tắc API. “Present” theo nghĩa này không đồng nghĩa “indirectly present” của repeatable annotation.

Vì vậy, `getAnnotation(T.class)` có thể nhìn lên superclass đối với annotation class được đánh dấu `@Inherited`, nhưng **không** có nghĩa nó bung container của `T`.

### 3.4. Associated — liên kết theo quy tắc ByType

Các API `getAnnotationsByType` dùng khái niệm **associated**. Với một phần tử, annotation type có thể được kết nối với nó do có một annotation **trực tiếp**, có nhiều annotation **gián tiếp trong container**, hoặc được **kế thừa** theo quy tắc `@Inherited` áp dụng cho class.

Điều này giải thích vì sao `getAnnotationsByType(T.class)` là API đúng khi cần bao quát cả một annotation trực tiếp lẫn nhiều annotation thành phần trong container.

## 4. Bảng tra cứu: API nào nhìn xuyên container?

Giả sử `Role` được khai báo như mục 2 và các class có annotation runtime hợp lệ.

| API | Một `@Role("A")` trực tiếp | Hai `@Role("A") @Role("B")` | Container tường minh `@Roles({@Role("A"), @Role("B")})` |
| --- | --- | --- | --- |
| `getAnnotation(Role.class)` | Một `Role("A")` | `null` nếu chỉ có container | `null` nếu chỉ có container |
| `getDeclaredAnnotation(Role.class)` | Một `Role("A")` | `null` | `null` |
| `getAnnotationsByType(Role.class)` | `[A]` | `[A, B]` | `[A, B]` |
| `getDeclaredAnnotationsByType(Role.class)` | `[A]` | `[A, B]` | `[A, B]` |
| `getAnnotation(Roles.class)` | Thông thường `null` | Container `Roles` | Container `Roles` |
| `getDeclaredAnnotations()` | Chứa `Role` | Chứa `Roles` | Chứa `Roles` |

Bảng này xem xét annotation được khai báo **ngay trên class được tra cứu**, không xét superclass. Khi có kế thừa, các API không có `Declared` trên `Class` còn chịu quy tắc `@Inherited`; xem mục 7.

### Vì sao getAnnotation(Roles.class) không phải là ByType?

Khi gọi:

```java
Roles container = TwoRoles.class.getAnnotation(Roles.class);
Role[] parts = container == null ? new Role[0] : container.value();
```

bạn **chủ động đọc chính container** rồi lấy mảng của nó. Đó là một cách làm hợp lệ khi biết chính xác type `Roles` và container thực sự hiện diện. Tuy nhiên, cách làm này không bao quát trường hợp chỉ có `@Role` trực tiếp và không có `@Roles`. Ngược lại:

```java
Role[] all = TwoRoles.class.getAnnotationsByType(Role.class);
```

bao quát được cả trường hợp một annotation trực tiếp và nhiều annotation gián tiếp trong container. Điều kiện là `Role` được định nghĩa là repeatable với container hợp lệ và có retention runtime như mong muốn.

**Không phải mọi annotation chứa mảng annotation đều được tự động bung.** Một container tùy ý có `T[] value()` nhưng `T` **không khai báo `@Repeatable(Container.class)`** thì `getAnnotationsByType(T.class)` không tự coi container đó là một nguồn `T`. Mối quan hệ `@Repeatable` trong **định nghĩa annotation type** là yếu tố quyết định.

## 5. Ví dụ Java 17+: kiểm chứng trên class, container tường minh, kế thừa và field

Ví dụ hoàn chỉnh này trình bày những điểm khó nhất trong cùng một lần chạy:

- Một annotation được gắn trực tiếp.
- Hai annotation lặp được compiler biểu diễn qua container.
- Một container được ghi tường minh, kể cả container rỗng.
- Một class con nhận các annotation lặp từ superclass theo `@Inherited`.
- Một class con tự khai báo annotation mới, thay thế kết quả tra cứu theo kiểu trên superclass.
- Một field có hai annotation lặp; API `ByType` mở container ngay trên đối tượng `Field`.

Lưu toàn bộ chương trình dưới đây vào **`ContainerLookupDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.List;

@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Roles {
    Role[] value();
}

@Role("single")
class SingleRole {}

@Role("read")
@Role("write")
class RepeatedRole {}

@Roles({@Role("alpha"), @Role("beta")})
class ExplicitContainer {}

@Roles({})
class EmptyContainer {}

@Role("parent-a")
@Role("parent-b")
class ParentRole {}

class ChildWithoutRole extends ParentRole {}

@Role("child-only")
class ChildWithOwnRole extends ParentRole {}

class FieldHolder {
    @Role("encrypted")
    @Role("indexed")
    private String payload;
}

public class ContainerLookupDemo {
    static List<String> names(Role[] annotations) {
        return Arrays.stream(annotations).map(Role::value).toList();
    }

    public static void main(String[] args) throws NoSuchFieldException {
        System.out.println("single.get: "
                + SingleRole.class.getAnnotation(Role.class).value());
        System.out.println("single.byType: "
                + names(SingleRole.class.getAnnotationsByType(Role.class)));
        System.out.println("single.container: "
                + (SingleRole.class.getAnnotation(Roles.class) != null));

        System.out.println("repeated.get: "
                + RepeatedRole.class.getAnnotation(Role.class));
        System.out.println("repeated.byType: "
                + names(RepeatedRole.class.getAnnotationsByType(Role.class)));
        System.out.println("repeated.container: "
                + names(RepeatedRole.class.getAnnotation(Roles.class).value()));
        System.out.println("repeated.rawType: "
                + RepeatedRole.class.getDeclaredAnnotations()[0]
                    .annotationType().getSimpleName());

        System.out.println("explicit.byType: "
                + names(ExplicitContainer.class.getAnnotationsByType(Role.class)));
        System.out.println("empty.byType: "
                + names(EmptyContainer.class.getAnnotationsByType(Role.class)));
        System.out.println("empty.hasContainer: "
                + (EmptyContainer.class.getAnnotation(Roles.class) != null));

        System.out.println("child.associated: "
                + names(ChildWithoutRole.class.getAnnotationsByType(Role.class)));
        System.out.println("child.declared: "
                + names(ChildWithoutRole.class.getDeclaredAnnotationsByType(Role.class)));
        System.out.println("child.singular: "
                + ChildWithoutRole.class.getAnnotation(Role.class));
        System.out.println("childOwn.associated: "
                + names(ChildWithOwnRole.class.getAnnotationsByType(Role.class)));

        Field field = FieldHolder.class.getDeclaredField("payload");
        System.out.println("field.byType: "
                + names(field.getDeclaredAnnotationsByType(Role.class)));
        System.out.println("field.singular: "
                + field.getAnnotation(Role.class));
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**, ở thư mục có tệp:

```bash
javac --release 17 ContainerLookupDemo.java
java ContainerLookupDemo
```

**Stdout dự kiến, theo đúng thứ tự chương trình:**

```text
single.get: single
single.byType: [single]
single.container: false
repeated.get: null
repeated.byType: [read, write]
repeated.container: [read, write]
repeated.rawType: Roles
explicit.byType: [alpha, beta]
empty.byType: []
empty.hasContainer: true
child.associated: [parent-a, parent-b]
child.declared: []
child.singular: null
childOwn.associated: [child-only]
field.byType: [encrypted, indexed]
field.singular: null
```

Cách diễn giải kết quả:

1. `SingleRole` có đúng một `Role` trực tiếp: `getAnnotation(Role.class)` trả `Role` và `getAnnotationsByType(Role.class)` trả mảng `[single]`. Trong trường hợp này không có container `Roles`.
2. `RepeatedRole` có hai `Role`: qua reflection, hai thành phần hiện diện gián tiếp trong container `Roles`. Bởi vậy `getAnnotation(Role.class)` là `null` nhưng `ByType` trả `[read, write]`.
3. `getAnnotation(Roles.class)` tìm container, và `container.value()` cho ra hai phần tử theo thứ tự.
4. `getDeclaredAnnotations()[0]` trên `RepeatedRole` là annotation type `Roles` vì ở đây nó có một container runtime trên class; không nên dựa vào chỉ số `0` nếu có nhiều kiểu annotation khác cùng hiện diện.
5. `ExplicitContainer` dùng container tường minh; `getAnnotationsByType(Role.class)` vẫn nhìn xuyên để lấy `alpha` và `beta`.
6. `EmptyContainer` có **container nhưng không có phần tử `Role`**. `getAnnotationsByType(Role.class)` trả `[]` trong khi `getAnnotation(Roles.class)` khác `null`. Việc tìm thấy container không đồng nghĩa container chứa ít nhất một phần tử.
7. `ChildWithoutRole` không khai báo `Role` hay `Roles`; `@Inherited` trên cả hai type cho phép `getAnnotationsByType(Role.class)` thấy hai annotation ở superclass. `getDeclaredAnnotationsByType` trả mảng rỗng. `getAnnotation(Role.class)` vẫn không mở container ở superclass nên trả `null`.
8. `ChildWithOwnRole` khai báo một `Role` trực tiếp: `getAnnotationsByType(Role.class)` trả `[child-only]`, **không tự cộng** `parent-a`/`parent-b` vào kết quả.
9. `FieldHolder.payload` chứa hai `Role` gián tiếp qua container. `Field.getDeclaredAnnotationsByType(Role.class)` mở container; `Field.getAnnotation(Role.class)` không mở nên trả `null`. `@Inherited` chỉ có ý nghĩa kế thừa theo superclass với annotation **trên class**, không làm field annotation kế thừa tự động.

Toàn bộ ví dụ chỉ đọc metadata; nó không gọi constructor, không đọc giá trị `payload` và không cần `setAccessible(true)` để lấy annotation của private field.

## 6. Thứ tự khi container được bung

Khi khai báo:

```java
@Role("first")
@Role("second")
@Role("third")
class Workflow {}
```

`Workflow.class.getAnnotationsByType(Role.class)` cho các phần tử kiểu `Role` theo thứ tự `first`, `second`, `third`. Trong biểu diễn container, thứ tự đó tương ứng thứ tự các annotation thành phần trong mảng `value()`.

Với container tường minh:

```java
@Roles({
    @Role("third"),
    @Role("first"),
    @Role("second")
})
class ExplicitWorkflow {}
```

kết quả `getAnnotationsByType(Role.class)` theo thứ tự `third`, `first`, `second`. API `ByType` có thể bảo toàn thứ tự thành phần repeatable, nhưng **không làm Java tự thực thi lần lượt** những action tương ứng. Nếu thứ tự là ý nghĩa nghiệp vụ, code tiêu thụ metadata phải định nghĩa cách duyệt/sắp xếp.

Ngoài ra, đừng suy diễn **thứ tự giữa nhiều kiểu annotation khác nhau** từ `getAnnotations()` hoặc `getDeclaredAnnotations()`. Những API ấy không cung cấp một hợp đồng thứ tự tổng quát giữa các loại annotation. Khi cần lặp một type, lấy trực tiếp mảng `ByType(T.class)`.

## 7. @Inherited: khi nào ByType nhìn tới superclass?

`@Inherited` là meta-annotation đặc biệt dành cho **annotation trên khai báo class**. Nó không khiến các annotation trên method, field, constructor hoặc interface tự động kế thừa theo cùng cách.

Trong ví dụ đầy đủ, cả hai type đều có `@Inherited`:

```java
@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Roles {
    Role[] value();
}
```

Khi `Role` là repeatable và được đánh dấu `@Inherited`, container của nó phải được đánh dấu `@Inherited` phù hợp. Nếu không, khai báo cặp annotation có thể không hợp lệ ở thời điểm biên dịch.

Quy tắc hữu ích cho `Child.class.getAnnotationsByType(Role.class)`:

1. Nếu chính `Child` có `Role` trực tiếp hoặc có container `Roles` chứa `Role` gián tiếp, các annotation ở chính class đó quyết định kết quả.
2. Nếu chính `Child` không có `Role` trực tiếp/gián tiếp và type `Role` được đánh dấu `@Inherited`, API có thể tìm các annotation associated phù hợp từ superclass gần nhất theo quy tắc tìm kiếm.
3. `getDeclaredAnnotationsByType(Role.class)` **không** tra superclass, cho dù type có `@Inherited`.
4. Kết quả `getAnnotationsByType` không mặc định gộp tất cả phần tử ở class con và class cha. Muốn hợp nhất, cần code nghiệp vụ tự duyệt chuỗi superclass và xử lý trùng lặp/thứ tự.

**Tinh tế:** `Class.getAnnotation(Role.class)` trên class con cũng không được xem là API “mở container ở superclass”. Nó vẫn tìm `Role` theo quan hệ **present**, còn `getAnnotationsByType(Role.class)` dùng quan hệ **associated** và có thể tìm các phần tử gián tiếp trong `Roles` kế thừa.

Nếu annotation không có `@Inherited`, `getAnnotationsByType` và `getDeclaredAnnotationsByType` của một class con không tự thấy annotation được khai báo riêng ở superclass chỉ vì nó có cùng hệ phân cấp.

## 8. Những ranh giới của việc nhìn xuyên container

### 8.1. Chỉ mở container được khai báo qua @Repeatable

API `getAnnotationsByType(T.class)` không mở một annotation bất kỳ chỉ vì annotation ấy có element trả `T[]`. Kiểu `T` phải được đánh dấu bằng `@Repeatable(Container.class)` để runtime nhận biết mối quan hệ phù hợp.

Ví dụ minh họa:

```java
@interface Item {
    String name();
}

@interface ItemGroup {
    Item[] value();
}
```

Nếu `Item` **không** được khai báo `@Repeatable(ItemGroup.class)`, `getAnnotationsByType(Item.class)` không tự bung `ItemGroup`. Đoạn trên cũng chưa có `RUNTIME`, vì vậy muốn thực nghiệm reflection cần thêm retention phù hợp. Hai điều kiện này giải quyết **hai vấn đề khác nhau**: quan hệ container và khả năng giữ metadata đến runtime.

### 8.2. Retention phải cho phép runtime quan sát

`@Repeatable` không thay `@Retention(RUNTIME)`. Với annotation `SOURCE`, thông tin trên class/field thường không có trong class file. Với `CLASS`, metadata được lưu trong class file nhưng reflection không hiển thị theo các API đang bàn. Nếu muốn dùng `getAnnotationsByType` lúc chạy, thiết kế cả annotation lặp và container với retention `RUNTIME` phù hợp.

### 8.3. Không có dữ liệu là mảng rỗng, không phải null

`getAnnotationsByType(T.class)` và `getDeclaredAnnotationsByType(T.class)` trả **mảng**; khi không có phần tử phù hợp, mảng thường có độ dài `0`, không phải `null`. Ngược lại, `getAnnotation(T.class)` và `getDeclaredAnnotation(T.class)` có thể trả `null`.

Trong Java nên xử lý:

```java
Role[] roles = type.getAnnotationsByType(Role.class);
if (roles.length == 0) {
    System.out.println("No roles");
}
```

Đây là đoạn minh họa giả định biến `type` đã có kiểu `Class<?>` và annotation `Role` đã được định nghĩa.

### 8.4. Sự khác nhau giữa Declared và không Declared

`getDeclaredAnnotationsByType(T.class)` trả các annotation trực tiếp/gián tiếp được khai báo trên chính phần tử. `getAnnotationsByType(T.class)` có thể áp dụng `@Inherited` khi phần tử là `Class` và annotation thỏa điều kiện. Với `Field` hoặc `Method`, `@Inherited` không tạo ra cơ chế tra superclass tương đương cho metadata trên khai báo member.

Vì vậy, nếu muốn chỉ metadata của một class mà không tính kế thừa, dùng `getDeclaredAnnotationsByType`; nếu muốn theo đúng quy tắc kế thừa chuẩn dành cho annotation class, dùng `getAnnotationsByType`.

### 8.5. Container thực sự có thể xuất hiện qua API raw

`getDeclaredAnnotations()` và `getAnnotations()` không nên được xem là API tự bung từng repeatable annotation. Khi class có nhiều `@Role`, raw reflection có thể trả container `Roles` như một annotation riêng. Nếu code duyệt raw rồi kiểm tra `annotation.annotationType() == Role.class`, nó có thể bỏ sót dữ liệu.

Giải pháp thực tế là truy vấn trực tiếp `getDeclaredAnnotationsByType(Role.class)` hoặc `getAnnotationsByType(Role.class)` khi biết kiểu cần tìm.

### 8.6. TYPE_USE và những API khác

Repeatable annotation cũng có thể áp dụng ở vị trí sử dụng kiểu nếu `@Target` có `ElementType.TYPE_USE`. Nhưng muốn đọc annotation ở vị trí type-use, thường cần API `AnnotatedType` thích hợp (ví dụ `Field.getAnnotatedType()` hoặc `Method.getAnnotatedReturnType()`), không phải `Field.getAnnotation(...)` nếu metadata thực sự nằm trên vị trí sử dụng kiểu. Vấn đề **“đúng nơi đặt annotation”** và vấn đề **“mở container”** là hai bước độc lập.

## 9. Các lỗi và câu hỏi kiểm tra nhanh

| Hiện tượng | Vì sao? | Cách xử lý |
| --- | --- | --- |
| Source có hai `@Role` nhưng `getAnnotation(Role.class) == null` | Hai annotation hiện diện gián tiếp trong container | Dùng `getAnnotationsByType(Role.class)` |
| `getAnnotation(Roles.class)` thấy container, còn `getAnnotation(Role.class)` không thấy | Hai API truy vấn **hai type khác nhau**, API đơn lẻ không bung container | Dùng `Roles.value()` hoặc `ByType(Role.class)` |
| Một `@Role` trực tiếp nhưng `getAnnotation(Roles.class) == null` | Trường hợp đơn lẻ không nhất thiết được chứa trong container | Dùng `getAnnotationsByType(Role.class)` để bao quát |
| `getAnnotationsByType(Role.class)` trả `[]` nhưng container vẫn tồn tại | Container có mảng `value()` rỗng | Kiểm tra `Roles.value().length` và semantics của dữ liệu |
| `ByType` không mở một `Group` chứa `Role[]` | Không có quan hệ `@Repeatable(Group.class)` đúng | Thiết kế cặp annotation/container hợp lệ |
| `ByType` không thấy annotation ở runtime | Retention không phải `RUNTIME`, tìm nhầm member hoặc type | Xác minh định nghĩa, vị trí và cơ chế đọc |
| Class con không kế thừa role như kỳ vọng | Không có `@Inherited`, hoặc metadata đã hiện diện trên chính class con | Kiểm tra quy tắc `@Inherited` của repeatable/container |
| `getDeclaredAnnotationsByType` không thấy role trên class cha | API có `Declared` chỉ đọc khai báo hiện tại | Chuyển sang `getAnnotationsByType` nếu muốn tra cứu kế thừa |
| Code duyệt `getDeclaredAnnotations()` rồi ép mọi annotation thành `Role` | Raw array có thể chứa `Roles` | Dùng `getDeclaredAnnotationsByType(Role.class)` |
| Nghĩ thứ tự trả về bắt buộc là thứ tự thực thi | Metadata không tự chạy | Viết logic tiêu thụ và định nghĩa quy tắc xử lý |

Đối với thư viện có API annotation công khai, cần kiểm thử bằng ít nhất bốn cấu hình: **một annotation trực tiếp**, **nhiều annotation lặp**, **container tường minh** và **không có annotation**, cộng thêm **kế thừa** nếu type có `@Inherited`. Đây là những cấu hình thường làm lộ nhầm lẫn giữa `getAnnotation` và `getAnnotationsByType`.

## 10. Checklist chọn API đúng

Khi đọc metadata ở runtime:

1. Xác định chính xác **annotation type T** mà chương trình muốn đọc, và xem T có `@Repeatable(Container.class)` hay không.
2. Xác nhận annotation T và container có retention runtime phù hợp.
3. Lấy đúng phần tử reflection: `Class`, `Field`, `Method`, `Constructor` hoặc `AnnotatedType` tùy vị trí.
4. Nếu muốn **mọi annotation T**, kể cả trong container: chọn **`getAnnotationsByType(T.class)`**.
5. Nếu muốn chỉ các annotation T **khai báo trên đúng phần tử**, không tra superclass: chọn **`getDeclaredAnnotationsByType(T.class)`**.
6. Nếu cần chính metadata của **container**, truy vấn `getAnnotation(Container.class)` rồi đọc element của nó; không dùng container thay thế mặc định cho mọi trường hợp một annotation trực tiếp.
7. Với class và `@Inherited`, quyết định rõ có cần dữ liệu từ superclass hay không. Đừng nhầm hành vi tra cứu chuẩn với việc cộng dồn các giá trị nghiệp vụ.
8. Đừng phụ thuộc vào thứ tự của tất cả các loại annotation trong raw reflection array. Nếu thứ tự của **các thành phần T** quan trọng, duyệt chính mảng `ByType(T.class)` theo thứ tự được trả về.

**Kết luận:** Java “nhìn xuyên qua annotation chứa” khi chương trình dùng **`getAnnotationsByType(T.class)`** hoặc **`getDeclaredAnnotationsByType(T.class)`** đối với một **repeatable annotation type T** được định nghĩa hợp lệ và có metadata phù hợp để reflection nhìn thấy. Các API đơn lẻ `getAnnotation(T.class)` và `getDeclaredAnnotation(T.class)` **không tự mở container**; `getAnnotation(Container.class)` chỉ tìm container. Hiểu đúng sự khác nhau giữa trực tiếp, gián tiếp và kế thừa sẽ giúp tránh bỏ sót annotation lặp.
