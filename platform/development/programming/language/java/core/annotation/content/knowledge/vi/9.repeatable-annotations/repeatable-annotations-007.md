# Thứ tự phần tử và hành vi khi tra cứu annotation lặp trong Java

## 1. Vấn đề: cùng một annotation xuất hiện nhiều lần

Từ Java 8, Java hỗ trợ **repeatable annotation**: một annotation type được phép xuất hiện nhiều lần tại cùng một vị trí khai báo hoặc sử dụng kiểu. Ví dụ, một endpoint có nhiều quyền truy cập:

```java
@Role("READ")
@Role("WRITE")
@Role("AUDIT")
class DocumentService {}
```

Đoạn trên chỉ hợp lệ khi `Role` đã được định nghĩa là annotation **lặp được**, thông qua meta-annotation `@Repeatable` cùng một annotation **chứa** (*containing annotation type*, thường gọi *container*).

Người học cần phân biệt ba điều:

1. **Thứ tự:** các annotation `@Role` được khai báo theo thứ tự `READ`, `WRITE`, `AUDIT`. Khi lấy chúng bằng API dành cho annotation lặp, thứ tự được bảo toàn.
2. **Cách Java biểu diễn:** trong class file, nhiều annotation lặp cùng kiểu thường được biểu diễn gián tiếp bằng một annotation container chứa mảng các annotation thành phần.
3. **Cách tra cứu:** `getAnnotation(Role.class)` và `getAnnotationsByType(Role.class)` **không tương đương**. Khi nhiều `Role` được gom thành `Roles`, cách tra cứu đơn lẻ có thể trả `null` dù các annotation thực sự đang hiện diện gián tiếp.

“Thứ tự phần tử” trong bài này là **thứ tự các annotation lặp trong mảng kết quả** và các thành phần container. Nó không phải thứ tự chạy tác vụ tự động. Java chỉ lưu metadata; một framework muốn chạy `READ` trước `WRITE` phải tự định nghĩa và thực thi cách xử lý metadata theo thứ tự đó.

## 2. Khai báo đúng annotation lặp và container

Hai annotation type liên quan đến nhau thường được định nghĩa như sau (đoạn này là **khai báo hỗ trợ**, chưa có phương thức `main`):

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

Ý nghĩa:

- `Role` là **repeatable annotation type**. `@Repeatable(Roles.class)` chỉ định annotation chứa các lần sử dụng `Role`.
- `Roles` là **container annotation type**. Nó phải có phần tử tên đúng là `value()` và phần tử ấy phải trả về `Role[]`. Ví dụ trên không có phần tử nào khác; nếu có thì những phần tử bổ sung phải đáp ứng quy tắc mặc định bắt buộc của container.
- `@Retention(RUNTIME)` cho phép đọc `Role` và `Roles` bằng reflection. Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`; trong trường hợp đó, reflection thông thường không đọc được annotation trên class tại runtime.
- `@Target(TYPE)` giới hạn annotation cho các vị trí khai báo type hợp lệ. Container và annotation lặp phải có cấu hình target tương thích; không thể để container không áp dụng được ở vị trí mà annotation thành phần được phép lặp.
- Việc khai báo `@Repeatable` có thể được compiler kiểm tra chặt về sự tương thích giữa hai type, gồm retention và các meta-annotation liên quan. Không thể ghép tùy tiện một container không đúng kiểu.

Khi sử dụng:

```java
@Role("READ")
@Role("WRITE")
@Role("AUDIT")
class DocumentService {}
```

ta có thể hình dung dạng container tương đương về các giá trị `Role`:

```java
@Roles({
    @Role("READ"),
    @Role("WRITE"),
    @Role("AUDIT")
})
class DocumentService {}
```

**Lưu ý:** hai khối trên là **hai cách viết thay thế nhau để minh họa**, không cùng xuất hiện trên một khai báo `DocumentService` trong cùng chương trình. Hình thức nguồn khai báo lặp được compiler xử lý để biểu diễn các annotation thành phần thông qua container; việc dùng API tra cứu phù hợp quyết định có nhìn thấy các thành phần riêng lẻ hay không.

## 3. Bảo toàn thứ tự khi tra cứu annotation lặp

Giả sử một class khai báo:

```java
@Role("first")
@Role("second")
@Role("third")
class Pipeline {}
```

Với annotation `Role` có retention `RUNTIME`, kết quả:

```java
Role[] roles = Pipeline.class.getAnnotationsByType(Role.class);
```

là mảng có ba phần tử theo thứ tự khai báo:

| Chỉ số mảng | Giá trị `roles[index].value()` |
| --- | --- |
| `0` | `"first"` |
| `1` | `"second"` |
| `2` | `"third"` |

Quy tắc quan trọng: khi có nhiều annotation cùng kiểu **hiện diện gián tiếp thông qua container**, thứ tự trong mảng `value()` của container phản ánh thứ tự các annotation cùng kiểu ở nguồn. Các API `getDeclaredAnnotationsByType` và `getAnnotationsByType` đưa ra kết quả cùng kiểu theo thứ tự thích hợp đó.

Nếu tác giả viết container **tường minh**:

```java
@Roles({
    @Role("third"),
    @Role("first"),
    @Role("second")
})
class OtherPipeline {}
```

thì `getAnnotationsByType(Role.class)` nhận các phần tử theo thứ tự **`third` → `first` → `second`**, vì thứ tự mảng nằm trong container tường minh là như vậy.

Không nên suy luận rằng thứ tự **các kiểu annotation khác nhau** luôn được bảo đảm bởi `getAnnotations()` hoặc `getDeclaredAnnotations()`. Hai API này trả về mảng các annotation được tra cứu theo quy tắc tương ứng, nhưng thứ tự giữa các kiểu annotation không phải hợp đồng đáng dựa vào. Với tập annotation lặp cùng kiểu, dùng `getAnnotationsByType(Role.class)` rồi dựa vào thứ tự thành phần được trả về.

Một trường hợp tinh tế: các annotation `Role` có thể xuất hiện xen giữa annotation khác. Thứ tự riêng của các lần dùng `Role` vẫn được bảo toàn khi chúng được biểu diễn trong container, nhưng **vị trí container so với những annotation khác** không có nghĩa là phải xử lý chúng đan xen theo đúng thứ tự mọi dòng annotation ở nguồn.

## 4. Các API tra cứu: khác nhau ở điểm nào?

Reflection định nghĩa những API quan trọng trên `AnnotatedElement`. `Class`, `Method`, `Field`, `Constructor`, `Parameter` cùng một số kiểu phản chiếu khác cung cấp những API này (mức hỗ trợ cụ thể tùy đích).

| API | Cách hoạt động đối với repeatable annotation |
| --- | --- |
| `getAnnotation(Role.class)` | Tìm **một annotation `Role`** hiện diện trực tiếp hoặc theo quy tắc kế thừa áp dụng; không tự mở container để trả từng `Role` gián tiếp. Có thể trả `null` khi chỉ có `@Roles(...)`. |
| `getDeclaredAnnotation(Role.class)` | Chỉ tra cứu annotation `Role` **trực tiếp khai báo** trên phần tử, không áp dụng kế thừa; không mở container. |
| `getAnnotationsByType(Role.class)` | Tìm tất cả `Role` hiện diện **trực tiếp hoặc gián tiếp qua container**; với `Class` còn áp dụng quy tắc `@Inherited` phù hợp nếu không có annotation cùng kiểu ở class hiện tại. |
| `getDeclaredAnnotationsByType(Role.class)` | Tìm các `Role` trực tiếp/gián tiếp được **khai báo trên đúng phần tử**, không tra cứu superclass. |
| `getAnnotation(Roles.class)` | Tìm annotation container `Roles` (nếu nó hiện diện theo quy tắc thích hợp), rồi có thể gọi `value()` để lấy mảng `Role[]`. |
| `getAnnotations()` / `getDeclaredAnnotations()` | Liệt kê các annotation runtime tương ứng; thường nhìn thấy **container `Roles`** khi có nhiều `Role` lặp, thay vì từng `Role` được “bung” riêng. |

**Điểm dễ sai nhất:** `getAnnotation(Role.class) == null` không đủ để kết luận “không có `Role`” trên phần tử nếu `Role` là repeatable. Có thể tồn tại nhiều `Role` thông qua `Roles`. Nếu mục tiêu là thu thập đầy đủ các annotation lặp, hãy dùng **`getAnnotationsByType(Role.class)`** hoặc **`getDeclaredAnnotationsByType(Role.class)`**, tùy có cần xem kế thừa hay không.

Ví dụ so sánh:

- Trường hợp chỉ một `@Role("ADMIN")`: có thể có **`Role` trực tiếp**, nên `getAnnotation(Role.class)` trả về `Role` và `getAnnotationsByType(Role.class)` trả mảng một phần tử.
- Trường hợp nhiều `@Role`: compiler dùng **container `Roles`**, vì vậy `getAnnotation(Role.class)` thường trả `null`, còn `getAnnotationsByType(Role.class)` trả tất cả các thành phần.
- Trường hợp viết trực tiếp `@Roles({@Role("A"), @Role("B")})`: tương tự, `Role` nằm gián tiếp trong container, và API `ByType` trả đủ hai thành phần.
- `getAnnotation(Roles.class)` có thể trả container trong hai trường hợp sau, nhưng không nên buộc mọi consumer biết tên container nếu họ chỉ cần các giá trị `Role`. API `ByType` giúp bao quát cả trường hợp một annotation trực tiếp lẫn trường hợp nhiều annotation gián tiếp.

## 5. Ví dụ Java 17+ hoàn chỉnh: thứ tự, container và tra cứu kế thừa

Ví dụ này dùng cả hai dạng viết `@Role` lặp và `@Roles` tường minh, một annotation đơn lẻ, cùng superclass/subclass để kiểm chứng các API và thứ tự.

Lưu toàn bộ chương trình vào tệp **`RepeatableLookupDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.List;

@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("read")
@Role("write")
@Role("audit")
class RepeatedService {}

@Roles({@Role("alpha"), @Role("beta")})
class ExplicitContainer {}

@Role("owner")
class SingleRole {}

@Role("parent-a")
@Role("parent-b")
class ParentService {}

class InheritingChild extends ParentService {}

@Role("child-only")
class OwnRoleChild extends ParentService {}

public class RepeatableLookupDemo {
    private static List<String> values(Role[] annotations) {
        return Arrays.stream(annotations).map(Role::value).toList();
    }

    public static void main(String[] args) {
        System.out.println("Repeated by type: "
                + values(RepeatedService.class.getAnnotationsByType(Role.class)));
        System.out.println("Repeated singular: "
                + RepeatedService.class.getAnnotation(Role.class));

        Roles container = RepeatedService.class.getAnnotation(Roles.class);
        System.out.println("Repeated container: " + values(container.value()));

        System.out.println("Repeated raw type: "
                + RepeatedService.class.getDeclaredAnnotations()[0]
                    .annotationType().getSimpleName());

        System.out.println("Explicit container: "
                + values(ExplicitContainer.class.getAnnotationsByType(Role.class)));

        System.out.println("Single by type: "
                + values(SingleRole.class.getAnnotationsByType(Role.class)));
        System.out.println("Single singular: "
                + SingleRole.class.getAnnotation(Role.class).value());

        System.out.println("Child inherited: "
                + values(InheritingChild.class.getAnnotationsByType(Role.class)));
        System.out.println("Child declared: "
                + values(InheritingChild.class.getDeclaredAnnotationsByType(Role.class)));
        System.out.println("Child own role: "
                + values(OwnRoleChild.class.getAnnotationsByType(Role.class)));
    }
}
```

Trong thư mục chứa tệp, dùng **JDK 17 trở lên**:

```bash
javac --release 17 RepeatableLookupDemo.java
java RepeatableLookupDemo
```

**Stdout mong đợi:**

```text
Repeated by type: [read, write, audit]
Repeated singular: null
Repeated container: [read, write, audit]
Repeated raw type: Roles
Explicit container: [alpha, beta]
Single by type: [owner]
Single singular: owner
Child inherited: [parent-a, parent-b]
Child declared: []
Child own role: [child-only]
```

Cách đọc các dòng:

1. Ba `@Role` trên `RepeatedService` xuất hiện theo đúng thứ tự `read`, `write`, `audit` trong mảng `getAnnotationsByType(Role.class)`.
2. `getAnnotation(Role.class)` trả `null` vì `RepeatedService` có các `Role` **hiện diện gián tiếp** trong container chứ không có một `Role` trực tiếp riêng.
3. `getAnnotation(Roles.class).value()` cho ba phần tử cùng thứ tự, chứng minh container lưu các annotation thành phần.
4. `getDeclaredAnnotations()[0].annotationType().getSimpleName()` in `Roles`: đối với `RepeatedService`, annotation được khai báo trực tiếp ở mức runtime là container.
5. `ExplicitContainer` viết container tường minh nên `ByType` cũng trả phần tử theo thứ tự `alpha`, `beta`.
6. `SingleRole` có một annotation trực tiếp; cả `getAnnotation` và `getAnnotationsByType` đều tìm thấy nó.
7. `InheritingChild` không tự khai báo `Role` hoặc `Roles`, nhưng `@Inherited` trên cả hai annotation types cho phép `getAnnotationsByType` nhìn thấy hai annotation từ `ParentService`. `getDeclaredAnnotationsByType` chỉ xem chính child, vì vậy trả `[]`.
8. `OwnRoleChild` khai báo `@Role("child-only")`. Giá trị trên child **không cộng dồn** với hai role ở superclass khi tra cứu `getAnnotationsByType`; mảng trả về chỉ có `child-only`.

Nếu đổi thứ tự ba dòng `@Role` ở `RepeatedService` rồi biên dịch lại, thứ tự ba chuỗi in ở hai dòng liên quan cũng đổi tương ứng.

## 6. Chi tiết quan trọng của @Inherited với annotation lặp

`@Inherited` chỉ liên quan đến cách tra cứu annotation trên **class declaration qua superclass**. Nó không khiến annotation trên interface tự động kế thừa xuống class triển khai, cũng không khiến annotation trên method được kế thừa theo cùng cách.

Với repeatable annotation, cần chú ý cả **annotation thành phần** và **container**:

```java
@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

Trong ví dụ này, cả `Role` và `Roles` đều có `@Inherited`. Khi annotation lặp được đánh dấu `@Inherited`, Java yêu cầu container tương ứng cũng có `@Inherited` để hai type có quan hệ hợp lệ.

Đối với `Class.getAnnotationsByType(Role.class)`:

1. Nếu class con **trực tiếp** có một `Role` hoặc **gián tiếp** có các `Role` qua container, kết quả đến từ **class con**.
2. Chỉ khi class con **không có** `Role` theo hai cách trên và `Role` có `@Inherited`, API mới tìm từ superclass phù hợp.
3. Nếu class con không khai báo annotation riêng, thứ tự của các `Role` kế thừa phản ánh thứ tự có được từ superclass.
4. `getDeclaredAnnotationsByType(Role.class)` luôn giới hạn ở annotation khai báo trên chính class con, nên không bao gồm các phần tử kế thừa.

Sự khác biệt này tác động đến thiết kế cấu hình: nếu bạn muốn tập role của class con **cộng dồn** với superclass, không nên cho rằng `getAnnotationsByType` tự hợp nhất chúng. Bạn phải tự đọc chuỗi superclass và xác định quy tắc hợp nhất/ghi đè theo nghiệp vụ.

Cũng không nên nhầm hành vi “kế thừa container” với việc `getAnnotation(Role.class)` tự mở container. `getAnnotation` vẫn áp dụng ngữ nghĩa tìm annotation đơn lẻ; để lấy mọi thành phần repeatable, hãy ưu tiên `getAnnotationsByType`.

## 7. Thứ tự annotation lặp có phải thứ tự thực thi không?

**Không mặc định.** Java bảo toàn thứ tự các thành phần để chương trình đọc metadata, nhưng bản thân annotation không thực thi code. Ví dụ:

```java
@Rule(step = 2, name = "verify")
@Rule(step = 1, name = "load")
class ImportWorkflow {}
```

Nếu `Rule` là repeatable và một thư viện đọc bằng `getAnnotationsByType(Rule.class)`, thứ tự mảng theo vị trí khai báo sẽ là `verify` rồi `load`. Tuy nhiên, nếu người xây dựng thư viện muốn chạy theo thuộc tính `step`, họ phải **chủ động sắp xếp theo `step`**, khi đó thứ tự xử lý có thể là `load` rồi `verify`. Hai chính sách này khác nhau; không có quy tắc Java buộc mọi framework chạy annotation theo thứ tự văn bản.

Khi thứ tự **mang ý nghĩa nghiệp vụ**, cần thiết kế rõ:

- Nếu muốn giữ thứ tự khai báo: dùng `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType`, duyệt mảng theo chỉ số tăng dần và ghi tài liệu rằng thứ tự nguồn là thứ tự xử lý.
- Nếu muốn có thứ tự bất biến trước việc người khác di chuyển dòng annotation: thêm element tường minh như `int priority()` hay `int order()` và sắp xếp bằng comparator theo hợp đồng.
- Nếu phải xử lý nhiều loại annotation khác nhau đan xen nhau, đừng dựa vào thứ tự mảng của `getDeclaredAnnotations()` để tái tạo thứ tự dòng nguồn giữa các kiểu. Cần một biểu diễn metadata thống nhất hoặc logic xử lý riêng.
- Nếu có annotation kế thừa từ superclass, quy định rõ **kế thừa thay thế**, **cộng dồn** hay **ưu tiên class con**. `getAnnotationsByType` có quy tắc riêng của Java, không mặc định đáp ứng mọi chính sách ứng dụng.

## 8. Các lỗi và bẫy phổ biến

### 8.1. Chỉ gọi getAnnotation cho annotation lặp

```java
Role role = RepeatedService.class.getAnnotation(Role.class);
```

Trong ví dụ có nhiều `@Role`, `role` là `null`. Việc gọi `role.value()` ngay lập tức sẽ gây `NullPointerException`. Sửa bằng:

```java
Role[] roles = RepeatedService.class.getAnnotationsByType(Role.class);
for (Role role : roles) {
    System.out.println(role.value());
}
```

Các đoạn trong mục này là mã minh họa, sử dụng những type đã được định nghĩa ở chương trình đầy đủ.

### 8.2. Quên retention runtime

`@Repeatable` không tự đặt `@Retention(RUNTIME)`. Nếu `Role` và `Roles` được định nghĩa mặc định với retention `CLASS`, Java reflection không cung cấp các annotation đó qua những API runtime đang thảo luận. Với công cụ chỉ hoạt động ở compile time hay phân tích bytecode, có thể dùng retention khác, nhưng phải chọn đúng cơ chế đọc.

### 8.3. Container khai báo sai element

```java
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    String[] value(); // Sai: phải là Role[]
}
```

Đây là ví dụ **cố ý sai**, `javac` không chấp nhận container vì phần tử `value()` không trả về mảng annotation thành phần `Role[]`. Ngoài kiểu mảng này, compiler còn kiểm tra khả năng áp dụng, retention và các thuộc tính liên quan của cặp annotation/container.

### 8.4. Dùng getDeclaredAnnotations rồi ép kiểu thành Role

Khi nhiều `@Role` bị gom vào `@Roles`, phần tử trả bởi `getDeclaredAnnotations()` có thể là một **`Roles`**, không phải `Role`. Ép kiểu trực tiếp sai có thể gây `ClassCastException`. Hãy dùng `getDeclaredAnnotationsByType(Role.class)` để đọc đúng các thành phần.

### 8.5. Lẫn lộn thứ tự annotation và thứ tự các element

Ví dụ container `@Roles({@Role("A"), @Role("B")})` có **hai phần tử mảng** với thứ tự quan trọng. Trong một annotation riêng, các cặp gán element như `@Config(name = "A", level = 2)` và `@Config(level = 2, name = "A")` biểu diễn cùng những giá trị đã gán; Java không gán ý nghĩa chạy lần lượt theo thứ tự viết các cặp thuộc tính đó.

### 8.6. Cho rằng superclass và subclass luôn cộng dồn

Nếu class cha có `@Role("base")` mà class con có `@Role("child")`, `getAnnotationsByType(Role.class)` trên class con ưu tiên annotation hiện diện ở class con. Nó không tự trả `[base, child]`. Muốn hành vi hợp nhất, hãy xác định một quy tắc riêng và duyệt kế thừa tường minh.

### 8.7. Tưởng annotation chỉ xuất hiện một lần khi có container

Container có một **giá trị mảng** bao gồm nhiều annotation thành phần; việc reflection trên container cho thấy một annotation không có nghĩa dữ liệu thành phần đã mất. API `ByType` cung cấp cách nhìn phù hợp để đọc đúng nhiều giá trị.

## 9. Cách kiểm tra bằng javap và reflection

Bạn có thể dùng công cụ JDK kiểm tra bytecode sau khi biên dịch ví dụ:

```bash
javap -v RepeatedService
```

Đối với định nghĩa retention `RUNTIME`, phần metadata annotation trên class file sẽ có thông tin về container `Roles` và các `Role` thành phần theo thứ tự trong mảng. Các dòng chi tiết của `javap -v` có thể khác nhau theo phiên bản JDK nên không đưa stdout cố định cho lệnh này. Khi chỉ cần giá trị runtime theo đúng kiểu và thứ tự, ví dụ `getAnnotationsByType` ở trên là cách thử trực tiếp và rõ hơn.

Để kiểm tra một thư viện thật:

1. Đọc định nghĩa annotation lặp: `@Repeatable(Container.class)`, `@Retention`, `@Target`, `@Inherited` nếu có.
2. Tạo fixture đơn lẻ, nhiều annotation, container tường minh; thử `getAnnotation` và `getAnnotationsByType` trên từng fixture.
3. Thử thứ tự khai báo khác nhau và xác nhận mảng `ByType` giữ đúng thứ tự đó.
4. Nếu hỗ trợ kế thừa, kiểm tra class con không khai báo annotation và class con có khai báo annotation riêng.
5. Nếu metadata quyết định thứ tự nghiệp vụ, xác nhận code tiêu thụ dùng đúng **thứ tự mảng** hoặc sắp xếp bằng element `order` đúng như hợp đồng.

**Ghi nhớ:** Với annotation lặp, thứ tự các thành phần cùng kiểu được bảo toàn trong container và mảng tra cứu. `getAnnotation(T.class)` chỉ xử lý kiểu đơn lẻ và có thể trả `null` khi các `T` nằm gián tiếp trong container; **`getAnnotationsByType(T.class)`** là API chính để thu thập đầy đủ các giá trị. Quy tắc `@Inherited` tác động đến việc có tra superclass hay không; còn thứ tự xử lý nghiệp vụ là quyết định của code tiêu thụ annotation.
