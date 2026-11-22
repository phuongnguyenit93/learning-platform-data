# Quy tắc phối hợp annotation lặp với annotation chứa trong Java

## 1. Hai loại annotation tham gia cơ chế lặp

Trong Java, một annotation bình thường không được xuất hiện nhiều lần tại cùng một vị trí khai báo hay cùng một ngữ cảnh sử dụng kiểu. Muốn viết nhiều annotation **cùng một kiểu** trên một thành phần, ta dùng cơ chế *repeatable annotation* có từ Java 8.

Cơ chế ấy cần hai annotation type phối hợp:

- **Annotation lặp (repeatable annotation):** kiểu mà lập trình viên muốn viết nhiều lần, ví dụ `@Role("READ")` và `@Role("WRITE")`.
- **Annotation chứa (containing/container annotation):** một annotation type riêng có element `value()` trả về **mảng một chiều của đúng kiểu annotation lặp**, ví dụ `Role[] value();` trong `@Roles`.

Ví dụ cơ bản:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Role("READ")
@Role("WRITE")
class AccountService {}
```

Ở đây `Role` là kiểu annotation lặp; `Roles` là kiểu chứa. Khi gặp hai `@Role` trên cùng class, compiler xử lý chúng như một **container annotation được khai báo ngầm** có `value` chứa các lần sử dụng `@Role` theo thứ tự xuất hiện.

Có thể hình dung kết quả logic:

```java
@Roles({
    @Role("READ"),
    @Role("WRITE")
})
class AccountService {}
```

Hai phiên bản trên tương đương cho mục đích lấy các `Role` theo cơ chế repeatable. Nhưng **cách viết nguồn và kết quả khi gọi từng API reflection cụ thể có thể khác giữa một annotation đơn lẻ và container**. Phần sau phân biệt rõ.

Cần nhớ: `@Repeatable` chỉ chỉ ra **kiểu container**. Nó không tự tạo kiểu `Roles`, và chỉ có tác dụng khi `Roles` đáp ứng toàn bộ các quy tắc hợp lệ của Java.

## 2. Quy tắc thứ nhất: container phải có `value()` trả về đúng `T[]`

Với annotation lặp tên `T` và container tên `TC`, element bắt buộc theo cấu trúc container là:

```java
T[] value();
```

Một định nghĩa đúng:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Alerts.class)
@interface Alert {
    String message();
}

@interface Alerts {
    Alert[] value();
}
```

Những khai báo container sau **cố ý sai**, hãy xem từng trường hợp riêng:

```java
// Sai: không có element value()
@interface WrongContainerA {
    Alert[] items();
}

// Sai: value() có kiểu Object[], không phải Alert[]
@interface WrongContainerB {
    Object[] value();
}

// Sai: value() trả một Alert thay vì Alert[]
@interface WrongContainerC {
    Alert value();
}

// Sai: mảng hai chiều không phải annotation element type hợp lệ
@interface WrongContainerD {
    Alert[][] value();
}
```

Ví dụ trên dùng `Alert` như một annotation type đã tồn tại; các `WrongContainer...` không được chọn bằng `@Repeatable` trong ví dụ đúng. Nếu đổi `@Repeatable(Alerts.class)` thành `@Repeatable(WrongContainerA.class)`, compiler sẽ phát hiện container không hợp lệ.

Một chi tiết dễ nhầm: `@Repeatable(Alerts.class)` nhận **class literal của annotation type chứa**, không nhận instance `@Alerts(...)` hay chuỗi tên `"Alerts"`.

Tên container thường là dạng số nhiều của tên annotation lặp (`Role`/`Roles`, `Tag`/`Tags`), nhưng đó chỉ là quy ước. Compiler dựa trên kiểu chính xác trong `@Repeatable(....class)` và kiểu trả về của `value()`.

## 3. Quy tắc thứ hai: element phụ của container phải có mặc định

Container **có thể có thêm element**, nhưng mọi element khác `value()` **đều phải khai báo `default`**.

Hợp lệ:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Permissions.class)
@interface Permission {
    String action();
}

@interface Permissions {
    Permission[] value();
    String source() default "policy";
    boolean verified() default false;
}
```

Nếu compiler tạo container ngầm khi thấy nhiều `@Permission`, nó không có chỗ để người dùng cung cấp `source` hoặc `verified`; các giá trị mặc định giúp container vẫn hình thành hợp lệ.

Sai:

```java
@interface InvalidPermissions {
    Permission[] value();
    String source(); // Sai khi được chọn làm container: thiếu default
}
```

`InvalidPermissions` tự nó có thể là một annotation type hợp lệ, nhưng **không đủ điều kiện làm container của `Permission`** nếu được ghi trong `@Repeatable(InvalidPermissions.class)`, bởi `source()` không có mặc định.

Nếu cần đưa giá trị riêng cho container, có thể sử dụng container **tường minh**:

```java
@Permissions(
    value = {
        @Permission(action = "READ"),
        @Permission(action = "WRITE")
    },
    source = "security-config",
    verified = true
)
class DocumentService {}
```

Phân biệt:

- Viết lặp `@Permission(...)`: compiler tạo container ngầm; các element phụ dùng `default`.
- Viết `@Permissions(...)`: lập trình viên chỉ định container và có thể truyền các element phụ theo cú pháp annotation thông thường.

Không nên thêm element phụ vào container nếu chúng không có ý nghĩa rõ ràng; chúng có thể gây khác biệt về metadata giữa cách viết lặp và container tường minh.

## 4. Quy tắc thứ ba: `@Retention` của container không được ngắn hơn annotation lặp

`@Retention` quyết định annotation được giữ đến giai đoạn nào. Thứ tự vòng đời theo mức giữ lại là:

```text
SOURCE  <  CLASS  <  RUNTIME
```

**Container phải được giữ ít nhất lâu bằng annotation lặp**.

| Retention của annotation lặp `T` | Retention hợp lệ của container `TC` |
|---|---|
| `SOURCE` | `SOURCE`, `CLASS`, `RUNTIME` |
| `CLASS` | `CLASS`, `RUNTIME` |
| `RUNTIME` | Chỉ `RUNTIME` |

Hợp lệ và thuận tiện cho reflection:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Labels {
    Label[] value();
}
```

Sai:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(BrokenLabels.class)
@interface BrokenLabel {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface BrokenLabels {
    BrokenLabel[] value();
}
```

Trong đoạn sai, annotation lặp cần tồn tại đến `RUNTIME` nhưng container chỉ có `CLASS`. Compiler từ chối vì khi lặp nhiều lần, các bản `BrokenLabel` được chứa bên trong `BrokenLabels` không thể được giữ đúng đến runtime thông qua container.

**Lưu ý mặc định:** Nếu không khai báo `@Retention`, Java dùng `RetentionPolicy.CLASS`. Chẳng hạn, cho `T` có retention `RUNTIME` nhưng bỏ `@Retention` trên `TC` là lỗi vì `TC` khi ấy mặc định `CLASS`.

Trong các thiết kế thực tế, dùng **cùng retention** cho cả hai thường đơn giản, dễ bảo trì và tránh lệch hành vi quan sát. Luật Java cho phép container giữ lâu hơn, nhưng điều đó không khiến mọi annotation ở mọi ngữ cảnh tự động hiển thị qua reflection nếu bản thân annotation lặp không có retention `RUNTIME`.

## 5. Quy tắc thứ tư: `@Target` phải tương thích, và vị trí lặp phải cho phép cả hai

`@Target` xác định nơi được dùng annotation. Đối với hai loại `T` và `TC`:

- Container `TC` không được cho phép những loại vị trí mà `T` không cho phép theo quy tắc tương thích của JLS (có các quan hệ bao hàm đặc biệt giữa `TYPE_USE`, `TYPE`, `TYPE_PARAMETER` và `ANNOTATION_TYPE`).
- **Muốn lặp `@T` tại một vị trí cụ thể, cả `T` và container `TC` đều phải áp dụng được ở vị trí ấy.**
- Container được phép **hẹp hơn** annotation lặp. Khi đó `@T` có thể được sử dụng **một lần** ở nhiều vị trí, nhưng chỉ được **lặp nhiều lần** ở những vị trí container cũng được phép xuất hiện.

Cấu hình thông dụng và dễ hiểu nhất: đặt cùng `@Target` trên cả hai.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Repeatable(RetryPolicies.class)
@interface RetryPolicy {
    int attempts();
}

@Target(ElementType.METHOD)
@interface RetryPolicies {
    RetryPolicy[] value();
}

class NetworkClient {
    @RetryPolicy(attempts = 2)
    @RetryPolicy(attempts = 3)
    void connect() {}
}
```

Ví dụ container hẹp hơn:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(AuditTags.class)
@interface AuditTag {
    String value();
}

@Target(ElementType.TYPE)
@interface AuditTags {
    AuditTag[] value();
}

@AuditTag("service")
@AuditTag("critical")
class PaymentService {
    @AuditTag("traced")
    void pay() {}
}
```

Trong đó:

- Hai `@AuditTag` trên `PaymentService` **hợp lệ**: `TYPE` nằm trong cả hai target.
- Một `@AuditTag` trên `pay()` **hợp lệ**: `METHOD` được `AuditTag` cho phép.
- Hai `@AuditTag` trên cùng `pay()` **sai**: container `AuditTags` không cho phép `METHOD`, nên compiler không thể tạo container ở method.

Ngược lại, đặt `@Target({TYPE, FIELD})` lên container khi annotation lặp chỉ có `@Target(TYPE)` sẽ bị từ chối ngay tại **định nghĩa** repeatable, vì container mở rộng vị trí vượt kiểu mà nó chứa.

Các quan hệ target đặc biệt trong JLS `9.6.3` cho phép vài dạng bao hàm, ví dụ annotation áp dụng cho `TYPE` cũng áp dụng ở khai báo annotation type; `TYPE_USE` bao quát nhiều ngữ cảnh kiểu. Khi gặp `TYPE_USE`/`TYPE_PARAMETER`, nên kiểm tra trực tiếp quy tắc JLS và viết thử mã ở **đúng vị trí** cần lặp, thay vì suy luận chỉ bằng tên enum.

Nếu mục tiêu là lặp trên mọi vị trí mà `T` cho phép, hãy thiết kế `@Target` của container tương ứng. Không có yêu cầu rằng hai tập target **phải hoàn toàn giống hệt nhau**.

## 6. Quy tắc thứ năm: `@Documented` và `@Inherited` phải đồng bộ theo một chiều

Java đặt thêm hai ràng buộc meta-annotation:

1. **Nếu annotation lặp `T` có `@Documented`, container `TC` cũng phải có `@Documented`.**
2. **Nếu annotation lặp `T` có `@Inherited`, container `TC` cũng phải có `@Inherited`.**

Ví dụ đúng:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Policies.class)
@interface Policy {
    String value();
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policies {
    Policy[] value();
}
```

Điều này bảo đảm container ngầm không làm mất tính chất tài liệu/kế thừa mà `Policy` công bố.

**Chiều ngược lại không bắt buộc:** Container có thể mang `@Documented` hoặc `@Inherited` trong khi annotation lặp không có. Tuy nhiên, chỉ nên thiết kế như vậy khi hiểu rõ tác động đến tài liệu và reflection, vì đặc tính có thể khác giữa annotation trực tiếp và container.

Ý nghĩa của hai meta-annotation:

- `@Documented` là tín hiệu để Javadoc ghi nhận annotation trong tài liệu API theo quy tắc tương ứng; nó không đổi retention.
- `@Inherited` tác động đến việc tra cứu annotation qua **superclass của class**, theo những API/điều kiện do Java quy định; nó không tự truyền annotation của method, field, interface hoặc package.
- Khi cần quan sát kế thừa bằng reflection, cần retention phù hợp, thường là `RUNTIME` cho cả `T` và `TC`.

Một cấu hình thiếu `@Inherited` trên container khi `T` có `@Inherited` sẽ bị compiler từ chối ngay trong định nghĩa `T`. Tương tự với `@Documented`.

## 7. Compiler phối hợp các lần lặp thành container thế nào?

Xét lại:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Checks.class)
@interface Check {
    String value();
}

@interface Checks {
    Check[] value();
}

@Check("syntax")
@Check("semantic")
@Check("performance")
class Report {}
```

Tại vị trí khai báo `Report`, ba annotation cùng kiểu `Check` được compiler chuyển thành **một container ngầm** với ba phần tử ở `value()`. Thứ tự các lần sử dụng `@Check` được bảo toàn:

```java
@Checks({
    @Check("syntax"),
    @Check("semantic"),
    @Check("performance")
})
class Report {}
```

Hai đoạn trên biểu diễn cùng chuỗi giá trị lặp, nhưng chỉ là **hai cách viết thay thế**. Không đặt cả hai bộ khai báo trên cùng một class.

Các điểm quan trọng:

- Một lần dùng `@Check("syntax")` không cần tạo container ngầm chỉ vì `Check` được khai báo repeatable.
- Từ hai lần dùng trở lên tại cùng ngữ cảnh phù hợp, compiler sử dụng container ngầm.
- Các annotation kiểu khác có thể xen giữa những lần `@Check`; các `Check` vẫn tạo thành dãy trong thứ tự chúng xuất hiện.
- Không nên coi “annotation lặp” là việc JVM lưu nhiều annotation trực tiếp cùng kiểu mà reflection có thể luôn thấy bằng `getAnnotations()`. Định dạng/container và API truy vấn là những phần của cùng cơ chế.

Cơ chế lặp cũng áp dụng trong ngữ cảnh dùng kiểu khi target cho phép, chứ không chỉ ở class declaration. Phần trên dùng class cho dễ kiểm tra bằng reflection.

## 8. Viết container tường minh: có thể và có giới hạn

Ngoài cách viết lặp trực tiếp:

```java
@Check("syntax")
@Check("semantic")
class DirectRepeats {}
```

Lập trình viên có thể viết container tường minh:

```java
@Checks({
    @Check("syntax"),
    @Check("semantic")
})
class ExplicitContainer {}
```

Đây là cú pháp hợp lệ khi `Check` và `Checks` đã được định nghĩa theo quy tắc ở mục 7. Một số framework hoặc thư viện có thể tạo annotation container tường minh khi sinh source; lúc đọc cần xử lý cả hai kiểu biểu diễn.

### Phối hợp một `@T` và một `@TC`

Trường hợp sau **có thể hợp lệ**:

```java
@Check("fast")
@Checks({@Check("secure"), @Check("stable")})
class MixedAllowed {}
```

Nó gồm **một** annotation `Check` trực tiếp và **một** container `Checks` tường minh. Không cần tạo container ngầm vì `Check` chỉ xuất hiện một lần trực tiếp.

Tuy vậy, lối viết pha trộn này dễ khiến người đọc nhầm kết quả của `getAnnotation` với `getAnnotationsByType`. Trong code thông thường, nên chọn một kiểu trình bày nhất quán, trừ khi có mục đích cụ thể.

### Phối hợp hai `@T` với một `@TC` là lỗi

```java
// CỐ Ý SAI: 2 @Check trực tiếp + một @Checks tường minh
@Check("a")
@Check("b")
@Checks({@Check("c")})
class MixedInvalid {}
```

Vì hai `@Check` đã cần **container ngầm**, sự hiện diện của `@Checks` tường minh tại cùng vị trí gây xung đột. Java cấm trường hợp có nhiều annotation lặp `T` đồng thời có annotation container `TC` trên cùng ngữ cảnh.

Với cấu trúc container có khả năng lặp chính nó, JLS còn cấm kết hợp **một** `@T` trực tiếp với **nhiều** `@TC` tại cùng ngữ cảnh. Các trường hợp này là hạn chế của ngôn ngữ, không phải lỗi của một framework cụ thể.

Mẹo tránh mơ hồ: Nếu muốn danh sách `a, b, c`, viết:

```java
@Check("a")
@Check("b")
@Check("c")
class AllDirect {}
```

hoặc:

```java
@Checks({@Check("a"), @Check("b"), @Check("c")})
class AllContained {}
```

## 9. Chọn đúng API reflection để đọc annotation lặp

Nếu retention là `RUNTIME`, Java reflection cho phép tìm annotation trên class/method/field phù hợp. Với repeatable annotation, có hai nhóm API quan trọng:

- `getAnnotation(T.class)` và `getDeclaredAnnotation(T.class)`: tìm **một** annotation có kiểu `T` theo quy tắc trực tiếp/có mặt. Chúng **không tự bung container** thành nhiều `T`.
- `getAnnotationsByType(T.class)` và `getDeclaredAnnotationsByType(T.class)`: trả **mảng** các `T` được áp dụng trực tiếp hoặc **chứa gián tiếp trong container** theo quy tắc API. Đây là lựa chọn thường dùng để đọc repeatable annotation.

Khi có container ngầm do viết hai hay nhiều `@T`, `getAnnotation(T.class)` thường là `null` trên khai báo đó; `getAnnotationsByType(T.class)` trả về các `T` chứa trong container theo thứ tự.

Nếu muốn truy vấn **container chính nó**, gọi `getAnnotation(TC.class)`. Ở trường hợp chỉ có một `@T` trực tiếp, container thường không hiện diện, nên `getAnnotation(TC.class)` có thể là `null`.

`getDeclaredAnnotationsByType` tập trung vào annotation khai báo trên chính phần tử; `getAnnotationsByType` còn có hành vi kế thừa thích hợp khi annotation có `@Inherited` và phần tử được truy vấn là class. Đừng dùng `getAnnotation(T.class)` như một cách đếm annotation lặp.

### Ví dụ Java 17+ độc lập có thể chạy

Tạo file **`RepeatableContainerDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
    String source() default "declared";
}

@Role("read")
@Role("write")
class AccountService {}

@Role("read")
class CatalogService {}

@Roles({@Role("audit"), @Role("notify")})
class BatchService {}

public class RepeatableContainerDemo {
    private static void inspect(Class<?> type) {
        Role[] roles = type.getAnnotationsByType(Role.class);
        String[] names = Arrays.stream(roles)
                .map(Role::value)
                .toArray(String[]::new);

        System.out.println(type.getSimpleName() + ": "
                + Arrays.toString(names));
        System.out.println("direct="
                + (type.getAnnotation(Role.class) != null)
                + ", container="
                + (type.getAnnotation(Roles.class) != null));
    }

    public static void main(String[] args) {
        inspect(AccountService.class);
        inspect(CatalogService.class);
        inspect(BatchService.class);
    }
}
```

Biên dịch và chạy từ thư mục chứa file với JDK 17+:

```bash
javac RepeatableContainerDemo.java
java RepeatableContainerDemo
```

Stdout:

```text
AccountService: [read, write]
direct=false, container=true
CatalogService: [read]
direct=true, container=false
BatchService: [audit, notify]
direct=false, container=true
```

Giải thích:

1. Hai `@Role` trên `AccountService` được lưu qua container ngầm `Roles`. `getAnnotationsByType(Role.class)` bung container thành hai phần tử `Role`.
2. Một `@Role` trên `CatalogService` được khai báo trực tiếp. `getAnnotation(Role.class)` tìm thấy; container chưa cần xuất hiện.
3. `BatchService` dùng `@Roles` tường minh. API `getAnnotationsByType(Role.class)` vẫn trả các `Role` nằm trong `Roles.value()`.
4. Giá trị `source() default "declared"` hợp lệ vì mọi element phụ của container đều có mặc định.

Ví dụ dùng ba class khác nhau để so sánh rõ các trường hợp. Không có class nào đặt cả container tường minh và nhiều annotation lặp trực tiếp tại cùng vị trí.

## 10. Phân biệt “trực tiếp”, “chứa gián tiếp”, “có mặt” và “liên kết”

Khi đọc tài liệu Java reflection, nên nhận ra một số thuật ngữ chuyên môn:

- **Directly present (trực tiếp):** annotation kiểu `T` được khai báo trực tiếp tại phần tử đang xét.
- **Indirectly present (gián tiếp qua container):** một container `TC` trực tiếp chứa các `T` trong `value()`, và các `T` được nhìn nhận theo cơ chế repeatable.
- **Present/associated:** các thuật ngữ của Java reflection bao gồm quy tắc liên quan đến kế thừa trên class trong điều kiện nhất định.
- **Declared:** ưu tiên annotation tại chính khai báo, không dựa vào superclass như các API không có chữ `Declared`.

Trong thực tế, điều thường cần là **lấy tất cả giá trị repeatable** bằng `getAnnotationsByType`, sau đó xử lý mảng kết quả. Nếu chỉ dùng `getAnnotation`, code có thể hoạt động khi một `@T` nhưng “mất” dữ liệu khi thêm `@T` thứ hai vì compiler đã chuyển cách biểu diễn sang container.

Với class inheritance, `@Inherited` còn ảnh hưởng cách tra cứu: một subclass không khai báo annotation liên quan có thể được nhìn nhận là có annotation lặp từ superclass thông qua `getAnnotationsByType`. Nhưng khi subclass đã có nhóm annotation `T` trực tiếp hoặc trong container theo quy tắc API, không mặc nhiên cộng dồn vô điều kiện toàn bộ `T` của superclass vào kết quả. Nếu cần semantics “hợp nhất qua toàn bộ cây kế thừa”, phải viết logic nghiệp vụ riêng.

Việc kế thừa annotation ở đây không áp dụng tự động cho method override, interface implement hoặc package.

## 11. Những lỗi biên dịch phổ biến trong cặp `T` và `TC`

### 11.1. Chỉ viết `@Repeatable` nhưng không khai báo container

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}
// Sai: không tồn tại annotation type Tags
```

Compiler cần phân giải được `Tags.class` và kiểm tra nó thực sự là containing annotation type hợp lệ. Cần khai báo `@interface Tags { Tag[] value(); }` hoặc tham chiếu đúng tên.

### 11.2. Container trả về sai kiểu

```java
import java.lang.annotation.Repeatable;

@Repeatable(Items.class)
@interface Item {
    String value();
}

@interface Items {
    String[] value(); // Sai: phải là Item[]
}
```

`String[]` là kiểu element annotation hợp lệ nói chung, nhưng **không** là kiểu `value()` đúng cho container của `Item`.

### 11.3. Container có element phụ bắt buộc

```java
import java.lang.annotation.Repeatable;

@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    Flag[] value();
    String owner(); // Sai: container thêm element không default
}
```

Sửa thành `String owner() default "unknown";` nếu thực sự cần element đó, hoặc bỏ element phụ.

### 11.4. Mismatch `@Retention`

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Events.class)
@interface Event {
    String value();
}

@Retention(RetentionPolicy.SOURCE)
@interface Events {
    Event[] value();
}
```

Sai: container `SOURCE` ngắn hơn annotation lặp `RUNTIME`.

### 11.5. Container mở rộng `@Target`

```java
import java.lang.annotation.*;

@Target(ElementType.METHOD)
@Repeatable(Marks.class)
@interface Mark {
    String value();
}

@Target({ElementType.METHOD, ElementType.FIELD})
@interface Marks {
    Mark[] value();
}
```

Sai: container cho phép `FIELD` nhưng annotation `Mark` không áp dụng được cho `FIELD`. Sửa target container thành `METHOD` nếu chỉ lặp ở method.

### 11.6. Thiếu `@Documented` hoặc `@Inherited` tương ứng

Khi `T` có `@Documented` mà `TC` không có, hoặc `T` có `@Inherited` mà `TC` không có, Java từ chối định nghĩa cặp này. Sửa bằng cách đặt meta-annotation tương ứng trên container, nếu đó là chủ đích của `T`.

### 11.7. Dùng hai annotation trực tiếp và container tường minh

```java
// Với Item và Items đã được khai báo đúng:
@Item("a")
@Item("b")
@Items({@Item("c")})
class InvalidMix {}
```

Sai do vừa cần một container ngầm cho hai `@Item`, vừa có container `@Items` tường minh. Gộp tất cả phần tử vào cách viết lặp hoặc một container tường minh.

### 11.8. Dùng sai API đọc

Đoạn logic sau thường không đáp ứng mục tiêu lấy **tất cả** annotation lặp:

```java
Role role = AccountService.class.getAnnotation(Role.class);
```

Khi `AccountService` có hai `@Role`, `role` sẽ là `null` vì các `Role` được chứa trong `@Roles`. Sửa bằng:

```java
Role[] roles = AccountService.class.getAnnotationsByType(Role.class);
```

Hai đoạn chỉ là ví dụ đối chiếu và dùng các kiểu đã khai báo trong mục 9.

## 12. Cách thiết kế cặp annotation lặp và container dễ bảo trì

Một quy trình thực tế:

1. Đặt tên ý nghĩa cho **`T`** ở dạng số ít, ví dụ `@Route` hoặc `@Permission`, và tên **`TC`** ở dạng tập hợp như `@Routes` hoặc `@Permissions`.
2. Định nghĩa các element trên `T` trước, bảo đảm từng phần tử là kiểu annotation hợp lệ.
3. Trong `TC`, tạo chính xác `T[] value();`.
4. Nếu `TC` có element phụ, cung cấp `default` cho tất cả chúng.
5. Dùng `@Repeatable(TC.class)` trên `T`.
6. Quyết định retention dựa trên bên tiêu thụ metadata; thường đặt cùng retention trên `T` và `TC`.
7. Quyết định target dựa trên vị trí cần **lặp**, thường đặt cùng `@Target` trên cả hai; nếu container hẹp hơn, ghi rõ các vị trí chỉ dùng được một lần.
8. Nếu `T` có `@Documented` hoặc `@Inherited`, đặt các annotation ấy trên `TC`.
9. Nếu ứng dụng dùng runtime reflection, đọc mảng bằng `getAnnotationsByType(T.class)`.
10. Kiểm tra cả trường hợp một `@T`, nhiều `@T`, `@TC` tường minh, và các trường hợp mix không hợp lệ.

Trong API công khai, thay đổi kiểu container, return type `value()`, retention hay target có thể làm mã khách hàng không biên dịch hoặc làm framework đọc metadata khác trước. Cần kiểm tra tương thích khi nâng phiên bản thư viện.

Dù container có thêm metadata phụ, hãy tránh để người dùng phải suy đoán cách kết hợp giá trị giữa container và từng annotation con. Nếu cần semantics cộng dồn, ưu tiên biểu diễn rõ ràng và tài liệu hóa quy tắc consumer.

## 13. Bài tập áp dụng

Giả sử có khai báo:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Rules.class)
@interface Rule {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Rules {
    Rule[] value();
    String source() default "manual";
}
```

Xác định tình huống nào đúng:

1. Một `@Rule("read")` trên class.
2. Hai `@Rule("read")` và `@Rule("write")` trên cùng class.
3. Một `@Rule("read")` trên method.
4. Hai `@Rule("read")` và `@Rule("write")` trên cùng method.
5. `@Rules({@Rule("read"), @Rule("write")})` trên class.
6. Một `@Rule("read")` cùng một `@Rules({@Rule("write")})` trên class.
7. Hai `@Rule` cùng một `@Rules` trên class.
8. Nếu đổi `@Retention` của `Rules` thành `SOURCE`, cặp annotation còn hợp lệ không?
9. Nếu đổi `Rules.value()` thành `String[] value()`, cặp annotation còn hợp lệ không?
10. Khi hai `@Rule` trên class, `getAnnotation(Rule.class)` có đủ để đọc cả hai không?

Đáp án:

1. **Đúng:** `Rule` áp dụng ở `TYPE`.
2. **Đúng:** `Rule` và `Rules` đều áp dụng ở `TYPE`, compiler tạo container ngầm.
3. **Đúng:** `Rule` áp dụng ở `METHOD` và chỉ xuất hiện một lần.
4. **Sai:** `Rules` không áp dụng ở `METHOD`, nên không thể chứa hai `@Rule` tại method.
5. **Đúng:** container tường minh hợp lệ ở `TYPE`.
6. **Đúng:** một `@Rule` trực tiếp và một `@Rules` tường minh có thể cùng tồn tại.
7. **Sai:** hai `@Rule` trực tiếp cần container ngầm, xung đột với container tường minh.
8. **Không:** `SOURCE` ngắn hơn `RUNTIME` của `Rule`.
9. **Không:** container cần `Rule[] value()`, không phải `String[]`.
10. **Không:** dùng `getAnnotationsByType(Rule.class)` để lấy đủ các phần tử lặp.

## 14. Checklist cuối bài

- Annotation lặp `T` có `@Repeatable(TC.class)`, trong đó `TC` tồn tại và là một annotation type hợp lệ.
- Container `TC` khai báo chính xác `T[] value();`.
- Mọi element khác `value()` trong container đều có `default`.
- Retention container **không ngắn hơn** retention của `T`; không quên mặc định `CLASS` khi thiếu `@Retention`.
- Target container nằm trong phạm vi tương thích với target `T`; muốn lặp tại một vị trí thì **cả hai** đều phải áp dụng được tại đó.
- Nếu `T` có `@Documented` hoặc `@Inherited`, `TC` cũng phải có meta-annotation tương ứng.
- Hai hay nhiều `@T` tại cùng vị trí tạo **container ngầm**, giữ thứ tự các `T`.
- Một `@T` trực tiếp có thể đứng cùng một `@TC` tường minh, nhưng không đặt **nhiều `@T`** cùng một `@TC` tại cùng ngữ cảnh.
- Để đọc toàn bộ annotation lặp lúc chạy, chọn `getAnnotationsByType(T.class)` và retention `RUNTIME` phù hợp.
- `getAnnotation(T.class)` không bung container, nên có thể trả `null` khi `T` xuất hiện lặp.
- Không suy luận `@Inherited` là tự hợp nhất mọi annotation của mọi superclass, hoặc áp dụng cho method/interface/package.
- Đã biên dịch kiểm tra cả **định nghĩa hai annotation type** lẫn từng tình huống sử dụng thực tế.

Tài liệu Java SE 17 để đối chiếu những quy tắc chi tiết: *Java Language Specification*, mục **9.6.3 — Repeatable Annotation Interfaces** và **9.7.5 — Multiple Annotations of the Same Interface**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html

Hiểu rõ hợp đồng giữa annotation lặp và annotation chứa giúp tránh lỗi ngay tại `@Repeatable`, kiểm soát được nơi có thể lặp, giữ được metadata qua các giai đoạn biên dịch/chạy và lựa chọn API reflection lấy đủ giá trị.