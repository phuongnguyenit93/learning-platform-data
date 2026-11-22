# Ngữ nghĩa `equals` của Java annotation: cùng kiểu và từng phần tử

Một annotation trong Java không được so sánh bằng vị trí nó được gắn, tên class được gắn hay chuỗi ký tự hiển thị của annotation. Theo hợp đồng của interface `java.lang.annotation.Annotation`, **hai đối tượng annotation bằng nhau về mặt logic (`equals` trả `true`) khi chúng thuộc cùng một annotation interface và mọi element tương ứng đều có giá trị bằng nhau theo quy tắc dành riêng cho kiểu của element đó**.

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Role {
    String value();
    int priority() default 1;
}

@Role("ADMIN")
class AdminPage {}

@Role(value = "ADMIN", priority = 1)
class AdminDashboard {}
```

Khi đọc hai annotation bằng reflection, `equals` trả `true`: cùng loại `Role`, cùng `value()` và cùng `priority()` (một bên dùng giá trị mặc định, bên kia ghi tường minh). Việc annotation xuất hiện trên **hai class khác nhau** không làm chúng khác nhau.

Ngược lại, nếu chỉ cần **một element** khác giá trị, `equals` sẽ trả `false`; annotation có cùng tên element và cùng giá trị nhưng thuộc **hai annotation interface khác nhau** cũng không bằng nhau.

## 1. Annotation là một kiểu interface có hợp đồng equals riêng

Khai báo annotation:

```java
@interface Config {
    String name();
    int retries() default 3;
}
```

định nghĩa một **annotation interface** tên `Config` có hai element `name()` và `retries()`. Khi dùng `@Config(name = "job")` trên class, `name()` nhận `"job"` và `retries()` nhận mặc định `3`.

Nếu `@Config` có `@Retention(RUNTIME)` và được gắn ở nơi Java reflection hỗ trợ, ta có thể lấy đối tượng annotation:

```java
Config config = SomeClass.class.getAnnotation(Config.class);
```

Biến `config` là một tham chiếu tới một đối tượng triển khai annotation interface `Config`. Java/JDK có thể dùng lớp triển khai nội bộ (thường dựa trên proxy), nhưng **chi tiết triển khai không phải căn cứ để so sánh**. API `Annotation` quy định `equals(Object)`, `hashCode()`, `toString()` và `annotationType()` cho các đối tượng này.

Điều cần nhớ:

- `==` hỏi hai tham chiếu có **cùng đối tượng** hay không.
- `equals(Object)` hỏi hai annotation có **cùng kiểu và cùng bộ giá trị element về mặt logic** hay không.
- `annotationType()` cho biết **annotation interface** chính xác của một đối tượng; `getClass()` có thể chỉ ra lớp triển khai nội bộ và không thay cho `annotationType()`.
- `hashCode()` phải tuân theo công thức đặc thù để các annotation bằng nhau có hash code bằng nhau.

Đừng dùng `==`, `System.identityHashCode`, `getClass()` hoặc `toString()` để tự định nghĩa sự tương đương giữa các annotation.

## 2. Quy tắc chính thức của Annotation.equals

Có thể diễn đạt hợp đồng trong Java SE 17 thành điều kiện logic:

```text
a.equals(b) == true
    khi và chỉ khi:
    1. b là đối tượng annotation thuộc cùng annotation interface với a;
    2. với mỗi element m của interface đó:
       giá trị a.m() bằng giá trị b.m() theo quy tắc của kiểu m.
```

So sánh là **theo từng element có tên và giá trị xác định**, không dựa vào thứ tự các cặp `name = value` được viết trong source.

Bảng quy tắc:

| Kiểu trả về của element | Quy tắc so sánh giá trị hai element |
|---|---|
| `boolean`, `byte`, `short`, `char`, `int`, `long` | Tương đương toán tử `==` cho hai giá trị nguyên thủy tương ứng |
| `float` | `Float.valueOf(x).equals(Float.valueOf(y))` |
| `double` | `Double.valueOf(x).equals(Double.valueOf(y))` |
| `String` | `x.equals(y)` |
| `Class` (ví dụ `Class<?>`, `Class<? extends X>`) | `x.equals(y)` |
| Enum | `x.equals(y)`; cùng hằng enum của cùng loại sẽ bằng |
| Annotation lồng nhau | `x.equals(y)` **đệ quy theo hợp đồng annotation** |
| Mảng một chiều kiểu element hợp lệ | Overload phù hợp của `Arrays.equals(x, y)` |

Đây là **quy tắc được Java API quy định**, không phải tùy chọn của một framework hay cách JDK tình cờ in annotation trong log.

### Khác kiểu annotation: dừng từ điều kiện đầu tiên

```java
@interface Primary {
    int value();
}

@interface Secondary {
    int value();
}

@Primary(7)
class A {}

@Secondary(7)
class B {}
```

Dù cả hai có element `value()` mang số `7`, hai đối tượng được phản chiếu từ `@Primary` và `@Secondary` **không bằng nhau** vì `Primary` và `Secondary` là các annotation interface khác nhau.

Ngay cả khi hai annotation interface có cùng tên ngắn trong **hai package khác nhau**, đó vẫn là hai loại Java khác nhau. Trong các tình huống class loader phức tạp, danh tính kiểu Java còn phụ thuộc vào class loader xác định loại đó; không thể quyết định equality từ tên hiển thị một mình.

## 3. Giá trị mặc định được tính đầy đủ vào phép so sánh

Annotation element có thể có `default`:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Job {
    String name();
    int attempts() default 3;
    String[] labels() default {};
}

@Job(name = "sync")
class JobA {}

@Job(name = "sync", attempts = 3, labels = {})
class JobB {}
```

Hai annotation có giá trị logic bằng nhau vì `JobA` nhận các giá trị mặc định, còn `JobB` khai báo chính những giá trị ấy tường minh.

Một yếu tố thường bị hiểu sai là **“không ghi element” không đồng nghĩa “thiếu một giá trị khi equals chạy”**. Nếu element có `default`, accessor của annotation trả giá trị mặc định; `equals` và `hashCode` cũng bao gồm element đó như các element khác.

Vì vậy:

- `@Job(name="sync")` bằng `@Job(name="sync", attempts=3, labels={})`.
- `@Job(name="sync", attempts=4)` **không** bằng hai annotation trên.
- `@Job(name="sync", labels={"x"})` **không** bằng annotation có mảng `labels()` rỗng.

Java không giữ một “cờ người viết đã ghi giá trị tường minh” như một phần của điều kiện `Annotation.equals`. Hai cách viết khác nhau nhưng giải ra cùng giá trị thì được xem là tương đương.

### Thứ tự các cặp element không tạo khác biệt

```java
@Job(name = "sync", attempts = 3, labels = {"ops"})
class OrderedA {}

@Job(labels = {"ops"}, attempts = 3, name = "sync")
class OrderedB {}
```

Hai trường hợp bằng nhau. Dù thứ tự liệt kê các cặp element trong source đổi, những **element có cùng tên** vẫn mang cùng giá trị.

Điều này **khác** với thứ tự các phần tử **bên trong một mảng**: phần 5 giải thích vì sao `{"a", "b"}` khác `{"b", "a"}`.

## 4. Primitive, float/double: chú ý NaN và dấu của số không

Với các element kiểu số nguyên, ký tự, boolean, nguyên tắc tương đương toán tử `==`. Nhưng Java có quy tắc riêng cho `float` và `double` để đáp ứng tính chất nhất quán của equality:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Rate {
    double value();
}

@Rate(0.0)
class PositiveZero {}

@Rate(-0.0)
class NegativeZero {}

@Rate(Double.NaN)
class NotANumberA {}

@Rate(Double.NaN)
class NotANumberB {}
```

Với các đối tượng `Rate` phản chiếu từ bốn class trên:

| So sánh | Kết quả |
|---|---|
| `@Rate(0.0)` và `@Rate(-0.0)` | `false` |
| `@Rate(Double.NaN)` và `@Rate(Double.NaN)` | `true` |
| `0.0 == -0.0` với phép so sánh primitive thông thường | `true` |
| `Double.NaN == Double.NaN` | `false` |

Vì sao? Hợp đồng `Annotation.equals` cho `double` gọi logic `Double.valueOf(x).equals(Double.valueOf(y))`, không dùng phép `==` trực tiếp. Tương tự, với `float` sử dụng `Float.valueOf(...).equals(...)`. Hai wrapper này phân biệt `+0.0` và `-0.0`, đồng thời coi các giá trị `NaN` là bằng nhau theo định nghĩa equality.

Đây là **ngoại lệ thiết yếu**, không nên áp dụng lại quy tắc `==` cho mọi primitive nếu tự triển khai đối tượng tương thích interface `Annotation`.

Các ký hiệu `Double.NaN` và `Float.NaN` là hằng thích hợp khi khai báo annotation element. Nếu muốn kiểm chứng, ví dụ hoàn chỉnh ở phần 7 kiểm tra cả hai trường hợp NaN và signed zero.

## 5. Mảng: Arrays.equals, không phải Object.equals

Annotation cho phép element kiểu **mảng một chiều** của các kiểu element hợp lệ:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Permissions {
    String[] roles();
}

@Permissions(roles = {"READ", "WRITE"})
class EndpointA {}

@Permissions(roles = {"READ", "WRITE"})
class EndpointB {}

@Permissions(roles = {"WRITE", "READ"})
class EndpointC {}
```

Hợp đồng annotation so sánh nội dung mảng với overload tương ứng của `Arrays.equals`:

- `EndpointA` và `EndpointB` tương đương vì các phần tử cùng số lượng, đúng vị trí và bằng nhau.
- `EndpointA` và `EndpointC` **khác nhau** vì thứ tự hai chuỗi đảo ngược.
- Mảng `{}` bằng một mảng `{}` khác, dù đó là hai đối tượng mảng riêng biệt.
- Một mảng `{"READ"}` khác `{"READ", "WRITE"}`.

**Đừng dùng `array1.equals(array2)` để tự mô phỏng `Annotation.equals`**. Mảng Java không override `Object.equals` để so sánh nội dung: hai mảng khác tham chiếu thường có `array1.equals(array2) == false` dù `Arrays.equals(array1, array2) == true`.

```java
import java.util.Arrays;

String[] left = {"READ", "WRITE"};
String[] right = {"READ", "WRITE"};

System.out.println(left.equals(right));           // false
System.out.println(Arrays.equals(left, right));    // true
```

Tương tự, với `int[]`, `double[]`, `Class<?>[]`, `enum[]` hoặc mảng annotation lồng nhau, hợp đồng sử dụng `Arrays.equals` **đúng overload**. Với mảng của annotation, phép so sánh từng phần tử lại gọi `equals` của annotation con, tạo ra cơ chế đệ quy.

Annotation element **không** được khai báo `String[][]` hoặc các mảng nhiều chiều tùy ý. Vì vậy đừng đề xuất dùng `Arrays.deepEquals` làm quy tắc chung cho annotation: đặc tả yêu cầu `Arrays.equals` phù hợp với mảng một chiều mà annotation hỗ trợ.

## 6. String, Class, enum, annotation lồng nhau

Các kiểu tham chiếu hợp lệ của annotation element được so sánh bằng `x.equals(y)`:

**String:** cùng dãy ký tự theo `String.equals`; không quan tâm hai literal đến từ nơi nào.

**Class:** so sánh class token. Ví dụ `String.class` bằng `String.class`, nhưng `String.class` không bằng `Integer.class`. Bên cạnh quan hệ kiểu, danh tính class token do cơ chế nạp lớp Java quyết định; không so sánh bằng `getSimpleName()`.

**Enum:** hằng enum cùng loại và cùng giá trị bằng nhau; tên hằng giống nhau ở **hai loại enum khác nhau** không biến chúng thành cùng một loại.

**Annotation lồng nhau:** phép so sánh tiếp tục áp dụng cùng bộ quy tắc cho các element của annotation con.

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String team();
}

@Retention(RetentionPolicy.RUNTIME)
@interface ServiceInfo {
    Class<?> type();
    Owner owner();
}

@ServiceInfo(type = String.class, owner = @Owner(team = "core"))
class ServiceA {}

@ServiceInfo(type = String.class, owner = @Owner(team = "core"))
class ServiceB {}

@ServiceInfo(type = String.class, owner = @Owner(team = "billing"))
class ServiceC {}
```

`ServiceA` bằng `ServiceB` theo `ServiceInfo.equals`. `ServiceC` khác vì `owner()` là một annotation `Owner` có `team()` không trùng. Về bản chất:

```text
ServiceInfo A vs ServiceInfo B
  cùng annotationType(ServiceInfo)
  type(): Class equals -> true
  owner(): Owner.equals -> true
     Owner.team(): String.equals -> true
  ==> ServiceInfo.equals -> true
```

Annotation lồng nhau có thể chứa tiếp mảng hoặc annotation con; quy tắc vẫn áp dụng theo kiểu từng element. Nhưng mỗi nhánh cuối cùng phải dùng những kiểu giá trị mà JLS cho phép trong annotation element, không thể tự khai báo `Map<String, Object>` để chứa dữ liệu tùy ý rồi trông đợi hợp đồng `Annotation.equals` xử lý.

## 7. Ví dụ Java 17+ chạy được: kiểm tra toàn bộ hợp đồng

Tạo file duy nhất **`AnnotationEqualsDemo.java`**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

enum Stage { DEV, PROD }

@Retention(RetentionPolicy.RUNTIME)
@interface Details {
    String owner();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Policy {
    String name();
    int level() default 3;
    String[] roles() default {};
    Class<?> target() default String.class;
    Stage stage() default Stage.DEV;
    Details details() default @Details(owner = "team");
    double rate() default 0.0;
    double sample() default Double.NaN;
}

@Policy(name = "reader", roles = {"USER", "AUDITOR"})
class First {}

@Policy(
    sample = Double.NaN,
    rate = +0.0,
    details = @Details(owner = "team"),
    stage = Stage.DEV,
    target = String.class,
    roles = {"USER", "AUDITOR"},
    level = 3,
    name = "reader"
)
class SameValues {}

@Policy(name = "reader", roles = {"AUDITOR", "USER"})
class DifferentOrder {}

@Policy(name = "reader", roles = {"USER", "AUDITOR"}, rate = -0.0)
class NegativeZero {}

@Policy(name = "reader", roles = {"USER", "AUDITOR"},
        details = @Details(owner = "ops"))
class DifferentNested {}

@Retention(RetentionPolicy.RUNTIME)
@interface Label { int value(); }

@Retention(RetentionPolicy.RUNTIME)
@interface OtherLabel { int value(); }

@Label(7)
class Labeled {}

@OtherLabel(7)
class OtherLabeled {}

public class AnnotationEqualsDemo {
    public static void main(String[] args) {
        Policy a = First.class.getAnnotation(Policy.class);
        Policy b = SameValues.class.getAnnotation(Policy.class);
        Policy c = DifferentOrder.class.getAnnotation(Policy.class);
        Policy d = NegativeZero.class.getAnnotation(Policy.class);
        Policy e = DifferentNested.class.getAnnotation(Policy.class);

        System.out.println("same type and values: " + a.equals(b));
        System.out.println("same hashCode: " + (a.hashCode() == b.hashCode()));
        System.out.println("default values included: "
                + (a.level() == b.level()));
        System.out.println("array contents: "
                + Arrays.equals(a.roles(), b.roles()));
        System.out.println("array Object.equals: "
                + a.roles().equals(b.roles()));
        System.out.println("different array order: " + a.equals(c));
        System.out.println("plus zero vs minus zero: " + a.equals(d));
        System.out.println("different nested value: " + a.equals(e));
        System.out.println("nested annotation equals: "
                + a.details().equals(b.details()));
        System.out.println("NaN member equals: "
                + Double.valueOf(a.sample())
                        .equals(Double.valueOf(b.sample())));
        System.out.println("different annotation types: "
                + Labeled.class.getAnnotation(Label.class)
                    .equals(OtherLabeled.class.getAnnotation(
                            OtherLabel.class)));
        System.out.println("null equals: " + a.equals(null));
        System.out.println("annotationType: "
                + (a.annotationType() == Policy.class));
    }
}
```

Biên dịch và chạy với Java 17 (hoặc JDK mới hơn hỗ trợ `--release 17`):

```bash
javac --release 17 -Xlint:all AnnotationEqualsDemo.java
java AnnotationEqualsDemo
```

Kết quả chính xác:

```text
same type and values: true
same hashCode: true
default values included: true
array contents: true
array Object.equals: false
different array order: false
plus zero vs minus zero: false
different nested value: false
nested annotation equals: true
NaN member equals: true
different annotation types: false
null equals: false
annotationType: true
```

Chương trình này kiểm tra nhiều điểm cùng lúc:

1. **Hai class khác nhau, một giá trị annotation:** `First` và `SameValues` được gắn `Policy` với toàn bộ element có giá trị tương đương. Một bên dựa vào default, bên kia ghi tường minh và đổi thứ tự các cặp. `a.equals(b) == true`.
2. **`hashCode` tương thích:** vì `a.equals(b)` là true, hai mã băm phải bằng nhau.
3. **Mảng:** `Arrays.equals(a.roles(), b.roles())` là true; `a.roles().equals(b.roles())` là false vì đó là `Object.equals` của hai mảng được trả về. Thứ tự `roles` trong `DifferentOrder` khác nên `a.equals(c)` là false.
4. **Số thực:** `+0.0` và `-0.0` bị xem là khác theo `Double.equals`. `Double.NaN` ở hai phía lại được xem là cùng một giá trị.
5. **Annotation con:** hai `@Details(owner="team")` tương đương; khác `"ops"` làm cả `Policy` không tương đương.
6. **Hai interface khác nhau:** `@Label(7)` và `@OtherLabel(7)` khác nhau, bất kể cùng element `value()` là 7.
7. **So sánh với null:** `a.equals(null)` là false.
8. **Danh tính kiểu:** `a.annotationType() == Policy.class` trả true.

Vì code đã gắn `@Retention(RUNTIME)` cho cả các annotation cần đọc, reflection có thể truy xuất chúng. Không nên lấy kết quả `null` từ `getAnnotation(...)` của một annotation SOURCE/CLASS để suy ra về phép so sánh; khi không có đối tượng runtime thì chưa có hai annotation để gọi `equals`.

## 8. Đồng bộ equals với hashCode

Hợp đồng `Annotation.hashCode()` cũng được quy định cụ thể. Với một annotation có các element `m`, mã băm bằng tổng đóng góp của từng element, **bao gồm element nhận default**.

Công thức cho mỗi element:

```text
memberHash =
    (127 * memberName.hashCode()) XOR memberValueHash

annotationHash = tổng memberHash của mọi element
```

Trong đó `XOR` là phép XOR bit của số nguyên (`^` trong Java). Phép nhân/sum vận hành theo số nguyên `int` của Java.

`memberValueHash` được tính theo loại giá trị:

| Giá trị | Cách lấy hash |
|---|---|
| Primitive | Hash theo wrapper tương ứng: `Integer.valueOf(v).hashCode()`, `Float.valueOf(v).hashCode()`, v.v. |
| `String`, `Class`, enum, annotation con | `v.hashCode()` (annotation con tính tiếp theo quy tắc annotation) |
| Mảng | `Arrays.hashCode(v)` đúng overload |

Ví dụ minh họa cách tính từng member:

```java
import java.util.Arrays;

int namePart = (127 * "name".hashCode()) ^ "reader".hashCode();
int rolesPart = (127 * "roles".hashCode())
        ^ Arrays.hashCode(new String[]{"USER", "AUDITOR"});
```

Đây mới chỉ là hai đóng góp của annotation `Policy` trong ví dụ chạy được. Muốn tính **toàn bộ** mã băm, phải cộng thêm các element `level`, `target`, `stage`, `details`, `rate` và `sample`, kể cả khi chúng dùng giá trị `default`.

Hệ quả thực tế:

- Nếu `a.equals(b) == true` thì **bắt buộc** `a.hashCode() == b.hashCode()`.
- Hai annotation **có thể** có cùng hash code nhưng không bằng nhau (va chạm hash), nên không dùng mỗi `hashCode` để thay `equals`.
- Không thể bỏ qua array contents, default values hay nested annotation khi tính hash code của một đối tượng tuyên bố tương thích với interface `Annotation`.
- `Arrays.hashCode` đối với mảng phải phù hợp với phép `Arrays.equals` tương ứng; nếu chỉ dùng mã băm danh tính của mảng thì hợp đồng sẽ bị phá.

Trong `HashMap<Policy, Value>` hoặc `HashSet<Policy>`, logic `equals/hashCode` giải thích vì sao hai annotation từ **hai vị trí gắn khác nhau** có thể hành xử như một khóa tương đương. Có thể dùng annotation làm khóa nếu hợp lý với thiết kế, nhưng nên hiểu rõ phiên bản/định nghĩa annotation và phạm vi class loader ảnh hưởng tới danh tính kiểu.

## 9. equals không phụ thuộc vị trí gắn, nguồn viết hay định dạng

Điều kiện equals **không hỏi**:

- Annotation được gắn trên class `A` hay class `B`.
- Một element có được viết tường minh hay dùng `default`.
- Thứ tự các cặp `key = value` trong source.
- Khoảng trắng, xuống dòng, cách trình bày ký tự annotation ở source.
- Thứ tự một công cụ hiển thị các element bằng `toString()`.
- Có bao nhiêu nơi khác trong chương trình dùng annotation cùng nội dung.

Ví dụ:

```java
@Role(value = "ADMIN", priority = 1)
class MenuOne {}

@Role(priority = 1, value = "ADMIN")
class MenuTwo {}
```

Nếu `Role` retention RUNTIME, hai giá trị được truy xuất từ `MenuOne` và `MenuTwo` là tương đương. Một công cụ đọc metadata cần so sánh ngữ nghĩa nên dùng `equals`, không nên làm string comparison dựa trên `annotation.toString()`.

`Annotation.toString()` được chuẩn hóa ở mức trả về **một biểu diễn chuỗi**, nhưng **chi tiết biểu diễn phụ thuộc implementation**. Nó hữu ích khi debug, không phải chuẩn serialization/định danh cho equality.

## 10. @Inherited và @Repeatable không thay hợp đồng equals

Các meta-annotation `@Inherited` và `@Repeatable` ảnh hưởng tới **cách khám phá annotation**, chứ không thay định nghĩa equals của một cặp đối tượng annotation đã được lấy ra.

### @Inherited: nguồn lấy annotation có thể khác nhau

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Capability {
    String value();
}

@Capability("read")
class Parent {}

class Child extends Parent {}
```

`Child.class.getAnnotation(Capability.class)` có thể trả một annotation **kế thừa** từ superclass vì `Capability` có `@Inherited`. Đối tượng này, khi so với `Parent.class.getAnnotation(Capability.class)`, vẫn tuân theo cùng quy tắc equals: cùng annotation interface, từng element bằng nhau.

Không được kết luận rằng mọi annotation ở method hay interface đều được `@Inherited` lan truyền: khả năng khám phá annotation theo superclass class có luật riêng, còn equality không dùng thông tin “annotation được kế thừa hay trực tiếp”.

### @Repeatable: nhiều đối tượng được lấy ra, so sánh từng đối tượng

```java
import java.lang.annotation.*;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("api")
@Tag("core")
class Endpoint {}
```

`Endpoint.class.getAnnotationsByType(Tag.class)` trả mảng các `Tag` tương ứng. Mỗi phần tử `Tag` vẫn so sánh theo `Annotation.equals`. Nếu so sánh hai annotation **container** `Tags`, element `value()` là mảng `Tag[]` và được so sánh qua `Arrays.equals`, vì vậy **thứ tự các Tag trong container có thể ảnh hưởng equality của container**.

`@Repeatable` không biến phép so sánh mảng thành so sánh tập hợp không thứ tự, và cũng không cho phép bỏ qua tên/kiểu của annotation container.

## 11. Khi nào không nên dùng một phép so sánh tự chế?

Những cách viết dưới đây dễ sai:

```java
// Sai về ngữ nghĩa: không phản ánh annotation value equality.
boolean same1 = (annotationA == annotationB);

// Không đáng tin để thay Annotation.equals:
boolean same2 = annotationA.toString().equals(annotationB.toString());

// Sai nếu xét array contents:
boolean same3 = annotationA.roles().equals(annotationB.roles());

// Chưa đủ: không thể dùng hashCode để quyết định luôn bằng nhau.
boolean same4 = annotationA.hashCode() == annotationB.hashCode();
```

Nếu cần so sánh **cùng một loại annotation đã truy xuất**, hãy dùng:

```java
boolean same = annotationA.equals(annotationB);
```

Nếu muốn biết **các khai báo có metadata giống nhau** ở một phạm vi lớn hơn, chẳng hạn cả bộ annotation trên hai method, bài toán lúc này khác: cần định nghĩa bộ lọc, loại annotation được quan tâm, sự kế thừa, repeated annotation, số lượng và quy tắc thứ tự. Không thể tự động thay thế bằng một lần `equals` của một annotation đơn lẻ.

Nếu viết một implementation của annotation interface bằng tay hoặc qua dynamic proxy, implementation đó phải thực hiện đúng **toàn bộ** hợp đồng `Annotation.equals/hashCode/annotationType` mới có thể tương tác nhất quán với annotation JDK trả về. Đừng mặc định mọi proxy tự chế đều đúng chỉ vì triển khai một interface mang tên `@interface`.

## 12. Các góc cạnh cần hiểu để tránh kết luận sai

### Chưa có runtime annotation thì chưa thể gọi equals

```java
@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {}

@SourceMarker
class Item {}
```

`Item.class.getAnnotation(SourceMarker.class)` trả `null`, bởi lần sử dụng SOURCE không được lưu để reflection đọc. Không nên viết `getAnnotation(...).equals(...)` nếu kết quả truy xuất có thể `null`; sẽ phát sinh `NullPointerException`. Kiểm tra trước hoặc dùng `Objects.equals` khi cần so sánh khả năng thiếu metadata.

Lưu ý `Objects.equals(a, b)` có thể coi **hai giá trị null là bằng nhau**, nhưng đó là hợp đồng của `Objects.equals` đối với việc **không tìm thấy annotation**, **không phải** hai instance annotation hiện diện có cùng nội dung.

### Annotation interface mới khác type cũ dù cùng element

```java
@Retention(RetentionPolicy.RUNTIME)
@interface OldConfig { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@interface NewConfig { String value(); }
```

`@OldConfig("x")` không bằng `@NewConfig("x")`. Một hệ thống migration có thể chủ động định nghĩa **tương đương nghiệp vụ** giữa hai loại, nhưng đó không phải `Annotation.equals` chuẩn.

### Những thay đổi định nghĩa annotation có thể ảnh hưởng so sánh

Nếu annotation interface được thay đổi bằng cách thêm một element có `default`, các đối tượng annotation tương ứng ở phiên bản mới sẽ có thêm element khi xét equality/hash. Khi làm việc với thư viện đã compile, thay đổi định nghĩa annotation có thể kéo theo các vấn đề tương thích binary/khả năng truy xuất element. Đừng dùng hash code của annotation như một định danh bền vững giữa phiên bản thư viện, JDK hay môi trường nạp lớp.

### ClassLoader và class token

Nếu một class được nạp bởi class loader khác, dù có cùng tên nhị phân, chúng có thể là **hai loại Java khác nhau**. Vì annotation equality kiểm tra đúng annotation interface và sử dụng `Class.equals` cho các element `Class`, tên hiển thị giống nhau **không bảo đảm** hai annotation bằng nhau.

### Mảng không phải tập hợp

Nếu ứng dụng muốn coi `{"READ","WRITE"}` và `{"WRITE","READ"}` là tương đương **về nghiệp vụ**, nó phải tự chuẩn hóa/canonicalize giá trị hoặc thiết kế một hàm riêng. `Annotation.equals` luôn tuân theo `Arrays.equals`, có xét vị trí phần tử.

## 13. Quy trình debug annotation không bằng nhau

Khi hai annotation nhìn có vẻ giống nhưng `equals` là `false`, hãy đi theo thứ tự:

1. **Kiểm tra chính xác annotation type:** so sánh `a.annotationType()` và `b.annotationType()`; đừng so class triển khai hay tên ngắn.
2. **Liệt kê tất cả element của annotation interface** qua `annotationType().getDeclaredMethods()`. Không bỏ qua element có `default`.
3. **Đọc từng giá trị accessor:** primitive, chuỗi, class token, enum, annotation lồng nhau hay mảng? Một element khác đã đủ khiến equality false.
4. **Đối với mảng, dùng `Arrays.equals`:** so kích thước, giá trị ở từng chỉ số, và thứ tự.
5. **Đối với float/double:** kiểm tra `NaN`, `+0.0` và `-0.0`; đừng dùng mỗi phép `==` để giải thích.
6. **Đối với annotation con:** so recursively từng element.
7. **Đối chiếu default và phiên bản library:** cùng cách viết source chưa chắc cùng runtime metadata nếu interface/giá trị default đã đổi; kiểm tra environment tương ứng.
8. **Kiểm tra cách lấy dữ liệu:** `getAnnotation`, `getDeclaredAnnotation` và `getAnnotationsByType` có các quy tắc khám phá khác nhau. Việc lấy đúng đối tượng là bước độc lập với việc so sánh.

Nếu mục đích là kiểm thử code, hãy assert cả trường hợp bằng nhau và trường hợp khác nhau: khác annotation type, khác một primitive, khác array order, khác nested value, khác signed zero. Việc kiểm thử bằng ví dụ đơn giản `String` mà bỏ qua mảng/default có thể che lỗi triển khai equals tự chế.

## 14. Bài tập tự kiểm tra

### Bài 1: Cùng giá trị, cách ghi khác nhau

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Task {
    String name();
    int priority() default 5;
}

@Task(name = "sync")
class Alpha {}

@Task(priority = 5, name = "sync")
class Beta {}
```

Hai annotation `Task` phản chiếu từ `Alpha` và `Beta` có bằng nhau không?

**Đáp án:** có, vì `priority()` trả cùng giá trị `5` và `name()` trả cùng chuỗi `"sync"`. Thứ tự viết cặp element và việc có ghi default tường minh không quan trọng.

### Bài 2: Thứ tự mảng

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Paths { String[] value(); }

@Paths({"a", "b"})
class A {}

@Paths({"b", "a"})
class B {}
```

**Đáp án:** không bằng nhau. Mảng được so bằng `Arrays.equals`, thứ tự phần tử có ý nghĩa.

### Bài 3: Hai loại annotation nhưng cùng tên element

```java
@interface Command { String value(); }
@interface Action { String value(); }
```

Có thể coi `@Command("run")` bằng `@Action("run")` theo `Annotation.equals` không?

**Đáp án:** không. Phải cùng annotation interface trước khi xét giá trị element.

### Bài 4: Mảng mới tạo

Hai annotation có `int[] numbers()` và mỗi annotation trả về một mảng riêng có nội dung `{1, 2, 3}`. Chúng có thể bằng nhau không?

**Đáp án:** có. Hợp đồng annotation dùng `Arrays.equals(int[], int[])`, không dùng danh tính tham chiếu mảng.

### Bài 5: float/double

Hãy dự đoán equality của `@Rate(+0.0)` với `@Rate(-0.0)`; và của hai `@Rate(Double.NaN)`.

**Đáp án:** cặp signed zero không bằng nhau; cặp NaN bằng nhau, theo `Double.equals` được dùng bởi `Annotation.equals`.

### Bài 6: Annotation lồng nhau

Hai `@ServiceInfo` có cùng `type()` và hai `Owner` cùng `team()`. Chúng có bằng nhau không nếu được gắn vào hai class khác nhau?

**Đáp án:** có, nếu không còn element nào khác giá trị. Annotation con được so đệ quy; nơi gắn không tham gia điều kiện equals.

### Bài 7: Hash code

Nếu `a.equals(b) == true`, có bắt buộc `a.hashCode() == b.hashCode()` không? Nếu chỉ biết hash code bằng nhau, có khẳng định equals true được không?

**Đáp án:** chiều đầu bắt buộc; chiều ngược lại không, vì các giá trị khác nhau có thể va chạm hash.

### Bài 8: Nguyên nhân một assert thất bại

`assert firstAnnotation.toString().equals(secondAnnotation.toString())` có phải là cách kiểm tra chuẩn của annotation equality không?

**Đáp án:** không. Biểu diễn chuỗi phụ thuộc implementation. Dùng `firstAnnotation.equals(secondAnnotation)`, với hai đối tượng đã được đọc và kiểm tra tồn tại.

## 15. Tổng kết và tài liệu đối chiếu

**Quy tắc ngắn gọn cần nhớ:** `Annotation.equals` xét **cùng annotation interface + equality của từng element**; element mảng so bằng `Arrays.equals`, annotation lồng nhau so đệ quy, default được tính đầy đủ, float/double tuân theo `Float.equals`/`Double.equals` thay vì `==` thông thường. `hashCode` phải tương ứng, nhưng `toString`, `==` và vị trí gắn annotation không thay thế được equals.

Tài liệu chính thức:

- [Java SE 17 API — `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): hợp đồng chi tiết `equals`, `hashCode`, `toString` và `annotationType`.
- [Java SE 17 API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): các overload của `Arrays.equals` và `Arrays.hashCode`.
- [JLS Java SE 17 — `9.6 Annotation Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): kiểu element, giá trị mặc định, metadata và meta-annotations.
- [Java SE 17 API — `java.lang.Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): cách `Double.equals` phân biệt signed zero và xử lý NaN.
