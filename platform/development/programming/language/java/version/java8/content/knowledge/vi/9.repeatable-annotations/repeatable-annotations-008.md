# Kiểm thử một, nhiều hoặc không có annotation lặp trong Java

**Repeatable annotation** (*annotation lặp*) là tính năng của Java 8 cho phép một phần tử được gắn nhiều annotation cùng kiểu. Với những metadata như nhiều vai trò, nhiều rule hoặc nhiều cấu hình áp dụng trên một class hay method, repeatable annotation tránh việc mỗi nơi sử dụng phải tự khai báo mảng annotation.

Khi kiểm thử, cần phân biệt ba trạng thái cơ bản: **không có annotation**, **một annotation**, **nhiều annotation**. Nhưng còn những trường hợp rất dễ bỏ sót: container annotation được viết tường minh, container rỗng, annotation kế thừa từ superclass, và method override không kế thừa annotation như class.

Bài này tập trung vào **cách viết và kiểm chứng test** cho các trường hợp ấy. Các cơ chế nêu ở đây vẫn còn áp dụng trong Java hiện đại; chương trình độc lập dùng **JDK 17+** và được kiểm chứng bằng việc biên dịch/chạy thực tế.

## 1. Vì sao chỉ kiểm thử một annotation là chưa đủ?

Giả sử chương trình gắn metadata lên các lớp:

~~~java
class NoRole {}

@Role("reader")
class OneRole {}

@Role("reader")
@Role("writer")
class TwoRoles {}
~~~

Đây là **mã minh họa chưa độc lập**: cần định nghĩa `@Role`, `@Roles` và các meta-annotations đúng như phần 2.

Một đoạn code đọc metadata bằng:

~~~java
Role role = SomeClass.class.getAnnotation(Role.class);
~~~

có thể hoạt động khi class có **một** `@Role`, nhưng không trả đủ thông tin khi class có **hai** `@Role`: compiler có thể lưu hai annotation ấy trong **container `@Roles`**. `getAnnotation(Role.class)` không tự bóc container, nên thường trả `null` cho trường hợp nhiều annotation.

Nếu code chỉ được test với `@Role("reader")`, lỗi này sẽ qua mặt bộ test. Với repeatable annotation, phải có test **0, 1 và nhiều**, rồi xác minh **số lượng, giá trị và API reflection được dùng**.

## 2. Định nghĩa đúng repeatable annotation và container

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Roles.class)
@Inherited
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Inherited
@interface Roles {
    Role[] value();
}
~~~

Đây là hai **khai báo kiểu minh họa**. Trong chương trình runnable ở phần 9, chúng được khai báo nested bên trong một class để dễ chạy trong một tệp.

| Thành phần | Vai trò |
| --- | --- |
| `@Repeatable(Roles.class)` | Khai báo `Role` được lặp và container là `Roles` |
| `@interface Roles` | Khai báo annotation dùng chứa các `Role` |
| `Role[] value()` | Phương thức bắt buộc có kiểu trả về đúng mảng của annotation lặp |
| `@Retention(RUNTIME)` | Để reflection ở runtime đọc metadata |
| `@Target(TYPE, METHOD)` | Annotation được gắn lên type declarations và method declarations |
| `@Inherited` | Có thể kế thừa annotation theo quan hệ **superclass** khi truy vấn class |

**`@Repeatable` không cho phép container tùy ý.** JLS `9.6.3 quy định container phải có `value()` trả đúng `Role[]`; mọi element khác của container phải có default value; retention và target phải tương thích; nếu repeatable annotation có `@Inherited` thì container cũng cần `@Inherited`.

Trong bộ ví dụ này, `Role` và `Roles` cùng `@Target({TYPE,METHOD})`, cùng `@Retention(RUNTIME)` và cùng `@Inherited`, nên quan hệ repeatable/containing hợp lệ, dễ hiểu.

### Vì sao cần `RUNTIME`?

Khi chỉ đặt `@Retention(SOURCE)`, annotation không có mặt để reflection runtime đọc; với `CLASS` nó có trong class file nhưng không được phản ánh bằng các API reflection runtime thông thường. Bởi vậy một test gọi `Class.getAnnotationsByType(...)` phải dùng metadata phù hợp với `RetentionPolicy.RUNTIME`. Nếu mục tiêu là test compile-time annotation processor thì chọn retention theo mục tiêu khác; đừng kết luận “không có annotation” chỉ vì dùng sai giai đoạn.

## 3. Chọn đúng reflection API

`java.lang.reflect.AnnotatedElement` cung cấp các phương thức từ Java 8 có ý nghĩa khác nhau:

| API | Trả về | Điểm quan trọng |
| --- | --- | --- |
| `getAnnotation(Role.class)` | Một `Role` hoặc `null` | Không tự bóc container có nhiều `Role`; có thể xét `@Inherited` trên class |
| `getDeclaredAnnotation(Role.class)` | Một `Role` hoặc `null` | Chỉ xét annotation trực tiếp trên phần tử |
| `getAnnotationsByType(Role.class)` | `Role[]` | Bóc container và hỗ trợ annotation **associated**; có thể xét kế thừa trên class |
| `getDeclaredAnnotationsByType(Role.class)` | `Role[]` | Bóc container nhưng bỏ qua annotation inherited |
| `getAnnotation(Roles.class)` | Một container hoặc `null` | Có thể tìm container theo quy tắc present/inherited |
| `getDeclaredAnnotation(Roles.class)` | Một container hoặc `null` | Chỉ container được khai báo tại phần tử |

**Khi cần tất cả repeatable annotations**, ưu tiên `getAnnotationsByType(Role.class)` hoặc `getDeclaredAnnotationsByType(Role.class)`. Chọn loại **Declared** nếu API chỉ xử lý metadata trên declaration hiện tại; chọn loại không Declared nếu hợp đồng thật sự muốn tính inheritance theo `@Inherited`.

Khi không có annotation đúng kiểu, `getAnnotationsByType` trả **mảng độ dài 0**, không trả `null`. Vì vậy nên viết:

~~~java
Role[] roles = SomeClass.class.getAnnotationsByType(Role.class);
if (roles.length == 0) {
    // Không có Role nào associated với class này.
}
~~~

Đoạn code là **minh họa** dùng class và annotation đã khai báo; mục đích là hướng dẫn kiểm tra rỗng, không phải ứng dụng độc lập.

## 4. Trạng thái không có annotation (zero)

~~~java
static class NoRole {}
~~~

Kiểm thử:

~~~java
Role[] roles = NoRole.class.getAnnotationsByType(Role.class);
if (roles.length != 0) {
    throw new AssertionError("Expected zero Role annotations");
}
~~~

Trong trường hợp không có annotation lẫn container:
- `getAnnotationsByType(Role.class).length == 0`.
- `getDeclaredAnnotationsByType(Role.class).length == 0`.
- `getAnnotation(Role.class) == null`.
- `getAnnotation(Roles.class) == null`.

Chỉ kiểm tra `roles != null` **không đủ**, vì phương thức trả một mảng hợp lệ ngay cả khi mảng rỗng. Không truy cập `roles[0]` trước khi kiểm tra `length`, nếu không sẽ gặp `ArrayIndexOutOfBoundsException`.

### Một tình huống zero khác: có container nhưng mảng rỗng

~~~java
@Roles({})
static class EmptyContainer {}
~~~

`EmptyContainer.class.getAnnotationsByType(Role.class).length` vẫn bằng 0, nhưng `getAnnotation(Roles.class)` trả container không `null`. Nếu hệ thống chỉ xử lý danh sách quyền, hai tình huống `NoRole` và `EmptyContainer` có thể cùng nghĩa **không có role**. Nếu muốn phân biệt **không hề cấu hình** với **đã cấu hình danh sách rỗng**, phải test thêm sự hiện diện của container.

Đây là một edge case có giá trị hơn kiểm tra chỉ riêng `count == 0`.

## 5. Trạng thái một annotation (one)

~~~java
@Role("reader")
static class OneRole {}
~~~

Kiểm tra cả số lượng và nội dung:

~~~java
Role[] roles = OneRole.class.getAnnotationsByType(Role.class);
if (roles.length != 1 || !"reader".equals(roles[0].value())) {
    throw new AssertionError("Expected exactly reader");
}
~~~

Với một `@Role` khai báo trực tiếp, `getAnnotation(Role.class)` thường trả đúng annotation và `getDeclaredAnnotation(Role.class)` cũng tìm thấy. Không cần container để biểu diễn một annotation trong nguồn ví dụ này.

**Nên assert chính xác `length == 1`, không chỉ `length > 0`.** Nếu một người vô tình gắn thêm `@Role("admin")`, test `length > 0` vẫn pass mặc dù business contract có thể sai.

Nếu test cần giá trị khác ngoài `value()`, ví dụ qualifier `scope()`, `priority()`, cũng cần assert từng element có ý nghĩa. Annotation khác kiểu không nên bị tính lẫn vào số lượng `Role`.

## 6. Trạng thái nhiều annotation (multiple)

~~~java
@Role("reader")
@Role("writer")
static class TwoRoles {}
~~~

Kiểm thử:

~~~java
Role[] roles = TwoRoles.class.getAnnotationsByType(Role.class);
if (roles.length != 2) {
    throw new AssertionError("Expected two roles");
}
if (!"reader".equals(roles[0].value())
        || !"writer".equals(roles[1].value())) {
    throw new AssertionError("Wrong role sequence");
}
~~~

Trong ví dụ:

- `getAnnotationsByType(Role.class)` cho mảng hai phần tử.
- `getDeclaredAnnotationsByType(Role.class)` cũng trả hai, vì Role được gắn trên chính `TwoRoles`.
- `getDeclaredAnnotation(Role.class)` thường là `null`: container hiện diện thay cho annotation Role trực tiếp.
- `getDeclaredAnnotation(Roles.class)` trả container thực sự.

Tính năng repeatable cho phép viết hai lần `@Role`; compiler có thể biểu diễn chúng tương ứng bằng:

~~~java
@Roles({@Role("reader"), @Role("writer")})
static class ExplicitContainer {}
~~~

Test `ExplicitContainer` và `TwoRoles` cùng dùng `getAnnotationsByType(Role.class)`: cả hai phải nhận đủ hai annotation dù cách khai báo nguồn khác nhau.

### Có nên assert thứ tự?

`AnnotatedElement.getAnnotationsByType` quy định cách hình thành thứ tự các annotation lặp trực tiếp/gián tiếp trên cùng phần tử, theo vị trí tương ứng trong nguồn/container. Vì vậy bộ test ví dụ kiểm tra `reader` trước `writer`.

Nếu nghiệp vụ coi roles như một tập không thứ tự, test nên chuyển thành tập rồi so sánh đầy đủ, tránh đưa giả định thứ tự không có ý nghĩa nghiệp vụ vào test. Đừng suy luận rằng **mọi annotation khác kiểu** sẽ được reflection trả theo thứ tự source.

## 7. Phân biệt annotation inherited và declared

`@Inherited` chỉ liên quan **annotation trên class qua superclass**. Nó không làm annotation trên method cha được tự động gắn lên method override của lớp con.

Ví dụ:

~~~java
@Role("base")
@Role("trace")
static class Parent {
    @Role("method-base")
    public void run() {}
}

static class Child extends Parent {
    @Override public void run() {}
}

@Role("local")
static class ChildOwn extends Parent {}
~~~

Vì `Role` và `Roles` đều có `@Inherited`:

~~~java
Role[] all = Child.class.getAnnotationsByType(Role.class);
Role[] own = Child.class.getDeclaredAnnotationsByType(Role.class);
System.out.println(all.length); // 2 (base, trace)
System.out.println(own.length); // 0
~~~

**Nguyên tắc kế thừa:** `getAnnotationsByType` xem xét superclass khi class hiện tại không có annotation kiểu đó associated tại chỗ và annotation type cho phép inherited. Không mặc định cộng tất cả annotation của mọi tầng class hierarchy.

Vì `ChildOwn` có một Role trực tiếp `"local"` nên:

~~~java
Role[] roles = ChildOwn.class.getAnnotationsByType(Role.class);
// roles.length == 1, roles[0].value().equals("local")
~~~

Không phải ba vai trò `local + base + trace`. Nếu nghiệp vụ muốn **merge roles của cả hierarchy**, cần viết thuật toán riêng và định nghĩa quy tắc precedence/duplicate rõ ràng. `@Inherited` mặc định không phải phép hợp tập hợp vai trò.

### Annotation trên method override

~~~java
Method parentMethod = Parent.class.getDeclaredMethod("run");
Method childMethod = Child.class.getDeclaredMethod("run");

System.out.println(parentMethod.getAnnotationsByType(Role.class).length); // 1
System.out.println(childMethod.getAnnotationsByType(Role.class).length);  // 0
~~~

Dù `Child.run()` override `Parent.run()`, annotation trên method của `Parent` không tự xuất hiện trên method override của `Child`.

Khi đọc method metadata, lưu ý `getMethod` có thể trả một method **được kế thừa** từ superclass nếu không override; khác với việc một method override của subclass kế thừa annotation. `getDeclaredMethod` chọn declaration tại class chỉ định, nên rất hữu ích để test đúng hành vi trên **method được khai báo tại chỗ**.

## 8. Test matrix 0 / 1 / nhiều và các tình huống phụ

| Fixture | Số Role từ `getAnnotationsByType` | `getDeclaredAnnotation(Role)` | `getDeclaredAnnotation(Roles)` |
| --- | ---: | --- | --- |
| `NoRole` | 0 | `null` | `null` |
| `OneRole` | 1 (`reader`) | Có | `null` |
| `TwoRoles` | 2 (`reader,writer`) | `null` | Có |
| `ExplicitContainer` | 2 (`ops,audit`) | `null` | Có |
| `EmptyContainer` | 0 | `null` | Có |
| `Child` (inherited) | 2 (`base,trace`) | `null` | `null` (không declared) |
| `ChildOwn` | 1 (`local`) | Có | `null` |
| `Methods.zero()` | 0 | `null` | `null` |
| `Methods.one()` | 1 (`read`) | Có | `null` |
| `Methods.many()` | 2 (`read,write`) | `null` | Có |
| `Parent.run()` | 1 (`method-base`) | Có | `null` |
| `Child.run()` | 0 | `null` | `null` |

Bảng được kiểm chứng trên đúng cấu hình `@Role`/`@Roles` trong chương trình hoàn chỉnh. Nếu sửa retention, `@Inherited`, target hoặc dùng một loại annotation khác, **kỳ vọng test phải được xác định lại** theo JLS và Javadoc.

## 9. Chương trình Java 17 độc lập: 12 assertions và stdout

Chương trình dưới đây tạo annotation repeatable, dữ liệu kiểm thử, và một hàm `expect`. Hàm này **ném `AssertionError` nếu có sai khác** về nội dung hoặc cách annotation/container hiện diện. Nó không chỉ in thông tin cho người đọc.

Lưu thành **RepeatableAnnotationCases.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.stream.*;

public class RepeatableAnnotationCases {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Repeatable(Roles.class)
    @Inherited
    public @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Inherited
    public @interface Roles {
        Role[] value();
    }

    static class NoRole {}

    @Role("reader")
    static class OneRole {}

    @Role("reader")
    @Role("writer")
    static class TwoRoles {}

    @Roles({@Role("ops"), @Role("audit")})
    static class ExplicitContainer {}

    @Roles({})
    static class EmptyContainer {}

    @Role("base")
    @Role("trace")
    static class Parent {
        @Role("method-base")
        public void run() {}
    }

    static class Child extends Parent {
        @Override public void run() {}
    }

    @Role("local")
    static class ChildOwn extends Parent {}

    static class Methods {
        public void zero() {}

        @Role("read")
        public void one() {}

        @Role("read")
        @Role("write")
        public void many() {}
    }

    static String roles(AnnotatedElement element) {
        return Arrays.stream(element.getAnnotationsByType(Role.class))
                .map(Role::value)
                .collect(Collectors.joining(","));
    }

    static void expect(String label, AnnotatedElement element, String expected,
                       boolean directRole, boolean directContainer) {
        String actual = roles(element);
        if (!actual.equals(expected)
                || (element.getDeclaredAnnotation(Role.class) != null) != directRole
                || (element.getDeclaredAnnotation(Roles.class) != null) != directContainer) {
            throw new AssertionError(label + ": got " + actual);
        }
        System.out.printf("%s count=%d values=[%s] directRole=%s container=%s%n",
                label, element.getAnnotationsByType(Role.class).length,
                actual, directRole, directContainer);
    }

    public static void main(String[] args) throws NoSuchMethodException {
        expect("none", NoRole.class, "", false, false);
        expect("one", OneRole.class, "reader", true, false);
        expect("two", TwoRoles.class, "reader,writer", false, true);
        expect("explicit", ExplicitContainer.class, "ops,audit", false, true);
        expect("emptyContainer", EmptyContainer.class, "", false, true);

        if (Child.class.getDeclaredAnnotationsByType(Role.class).length != 0) {
            throw new AssertionError("Child should have no declared roles");
        }
        expect("inherited", Child.class, "base,trace", false, false);
        expect("localOverrides", ChildOwn.class, "local", true, false);

        expect("methodZero", Methods.class.getDeclaredMethod("zero"), "", false, false);
        expect("methodOne", Methods.class.getDeclaredMethod("one"), "read", true, false);
        expect("methodTwo", Methods.class.getDeclaredMethod("many"), "read,write", false, true);
        expect("baseMethod", Parent.class.getDeclaredMethod("run"), "method-base", true, false);
        expect("overrideMethod", Child.class.getDeclaredMethod("run"), "", false, false);

        System.out.println("allChecks=PASS");
    }
}
~~~

Lệnh chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 RepeatableAnnotationCases.java
java RepeatableAnnotationCases
~~~

Stdout **đã biên dịch và chạy thực tế**:

~~~text
none count=0 values=[] directRole=false container=false
one count=1 values=[reader] directRole=true container=false
two count=2 values=[reader,writer] directRole=false container=true
explicit count=2 values=[ops,audit] directRole=false container=true
emptyContainer count=0 values=[] directRole=false container=true
inherited count=2 values=[base,trace] directRole=false container=false
localOverrides count=1 values=[local] directRole=true container=false
methodZero count=0 values=[] directRole=false container=false
methodOne count=1 values=[read] directRole=true container=false
methodTwo count=2 values=[read,write] directRole=false container=true
baseMethod count=1 values=[method-base] directRole=true container=false
overrideMethod count=0 values=[] directRole=false container=false
allChecks=PASS
~~~

### Giải thích output

- **`none`** không có `Role` hay `Roles`.
- **`one`** có `@Role` khai báo trực tiếp và không có container.
- **`two`** chứa hai `Role` gián tiếp qua `Roles`; vì vậy `directRole=false` nhưng `container=true`.
- **`explicit`** cho cùng cơ chế đọc với container viết trực tiếp.
- **`emptyContainer`** có count 0 nhưng container hiện diện; khác `none`.
- **`inherited`** thấy hai annotation từ `Parent`, dù chúng không được `declared` trên `Child`.
- **`localOverrides`** chỉ có `local`, không tự cộng thêm role từ `Parent`.
- **`methodZero` / `methodOne` / `methodTwo`** xác nhận cả ba trạng thái ở cấp method.
- **`baseMethod` / `overrideMethod`** chứng minh `@Inherited` không tự sao chép method annotation.
- **`allChecks=PASS`** chỉ xuất hiện khi mọi assertion đều vượt qua. Nếu sai, chương trình báo `AssertionError` và không tới dòng cuối.

Lưu ý hàm `expect` in các boolean kỳ vọng `directRole`/`directContainer` **sau khi đã xác minh chúng đúng** bằng `getDeclaredAnnotation(...)`. Vì thế output không phải lời khẳng định suông; nó đến sau một điều kiện kiểm tra.

## 10. Dùng JUnit Jupiter khi dự án có hệ thống test

Khi dự án dùng **JUnit 5 (JUnit Jupiter)**, nên tách các trường hợp zero/one/multiple thành test cases nhỏ để báo lỗi rõ. JUnit **không nằm trong JDK chuẩn**, vì vậy ví dụ sau **cần dependencies và test runner** của Maven/Gradle/IDE; nó không phải đoạn đã được chạy trong bộ `javac` độc lập ở phần 9.

Giả sử class `RepeatableAnnotationCases` nằm trong source/test scope có thể truy cập:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Arrays;

class RepeatableRoleTest {
    @Test
    void none() {
        var values = RepeatableAnnotationCases.NoRole.class
                .getAnnotationsByType(RepeatableAnnotationCases.Role.class);
        assertEquals(0, values.length);
    }

    @Test
    void one() {
        var values = RepeatableAnnotationCases.OneRole.class
                .getAnnotationsByType(RepeatableAnnotationCases.Role.class);
        assertEquals(1, values.length);
        assertEquals("reader", values[0].value());
    }

    @Test
    void two() {
        var values = RepeatableAnnotationCases.TwoRoles.class
                .getAnnotationsByType(RepeatableAnnotationCases.Role.class);
        assertArrayEquals(new String[]{"reader", "writer"},
                Arrays.stream(values)
                      .map(RepeatableAnnotationCases.Role::value)
                      .toArray(String[]::new));
    }
}
~~~

`var` trong test là cú pháp **Java 10+**. Nếu dự án target Java 8, thay `var` bằng `RepeatableAnnotationCases.Role[]`; bản thân tính năng repeatable annotations và các phương thức `getAnnotationsByType` đã có từ Java 8.

Tùy nhu cầu, bổ sung test riêng cho:
- `@Roles({})` so với class không có annotation.
- Class con không có local annotation nhưng kế thừa `@Inherited`.
- Class con có một local annotation che danh sách từ cha.
- Method override không thừa hưởng method annotation.
- Container được khai báo tường minh.

### Test metadata không phải test hành vi framework

JUnit `@Test` chỉ cho biết method nào là unit test để test engine thực thi. Nó không chứng minh framework của ứng dụng đã đọc `@Role` đúng hay đã áp dụng chính sách quyền tương ứng. Với hệ thống bảo mật, cần thêm **integration tests** bảo đảm framework sử dụng kết quả reflection đúng ngữ nghĩa nghiệp vụ, không chỉ xác minh annotation hiện diện.

## 11. Positive compile test và negative compile test

**Positive test**: source hợp lệ có hai `@Role`, được `javac` chấp nhận khi annotation type và container đúng:

~~~java
@Role("read")
@Role("write")
class GoodRoles {}
~~~

**Negative test 1:** một annotation chưa được đánh dấu `@Repeatable` không được dùng nhiều lần ở cùng vị trí:

~~~java
// SAI CỐ Ý: ví dụ để kiểm tra compiler báo lỗi.
@interface Flag {
    String value();
}

@Flag("a")
@Flag("b")
class InvalidFlags {}
~~~

**Negative test 2:** container trả sai kiểu `value()`:

~~~java
// SAI CỐ Ý: value() phải trả SpecialRole[], không phải String[].
@java.lang.annotation.Repeatable(BadContainer.class)
@interface SpecialRole {}

@interface BadContainer {
    String[] value();
}
~~~

Hai đoạn negative test **không được ghép vào tệp runnable**. Để kiểm thử compiler một cách có hệ thống, biên dịch mỗi fixture riêng rồi assert exit code khác 0 và loại lỗi phù hợp. Không phụ thuộc vào lời diagnostic cụ thể từng chữ, vì thông báo compiler có thể thay đổi giữa phiên bản Java.

**Compilation test khác reflection test:** compile test xác minh **tính hợp lệ cú pháp và metadata contract**, còn reflection test xác minh **API của ứng dụng đọc được bao nhiêu annotation và nội dung nào ở runtime**.

## 12. Lưu ý về vị trí annotation và phản chiếu

`@Target` quyết định một annotation được phép gắn ở đâu; trong ví dụ `Role` hỗ trợ `ElementType.TYPE` và `ElementType.METHOD`.

| Muốn gắn annotation ở đâu? | Target cần có | Cách truy cập reflection thông thường |
| --- | --- | --- |
| Class/interface declaration | `TYPE` | `Class<?>.getAnnotationsByType(...)` |
| Method declaration | `METHOD` | Lấy `Method`, gọi `getAnnotationsByType(...)` |
| Field declaration | `FIELD` | Lấy `Field` và đọc annotations |
| Parameter declaration | `PARAMETER` | Lấy `Parameter` hoặc API annotation của parameters |
| Một type use, như generic argument | `TYPE_USE` | Dùng `AnnotatedType` và subtype phù hợp |

**Không được** copy `@Role` từ ví dụ lên field hoặc parameter rồi kết luận Java bị lỗi repeatable annotation; trong ví dụ, target của `Role` **không bao gồm** FIELD/PARAMETER.

Khi dùng `TYPE_USE`, annotation đặt trên một *use of a type* có thể phải truy vấn `AnnotatedType`, chứ không phải các API declaration annotation của `Class`/`Field` trực tiếp. Đây là vấn đề của **vị trí metadata**, không phải số lượng repeatable.

Phản chiếu method overload cũng cần đúng chữ ký:

~~~java
Method method = Service.class.getDeclaredMethod("send", String.class);
~~~

Đây là đoạn minh họa trong phương thức, giả sử `Service` có method `send(String)`. `getDeclaredMethod("send")` không chọn được method có tham số String. Test phải chọn đúng `Method` trước khi hỏi nó có annotation hay không.

## 13. Chọn between `get...` và `getDeclared...` theo hợp đồng

Một câu hỏi quản trị metadata rất quan trọng: **“Gán role trên lớp cha có tự áp dụng cho lớp con không?”**

Nếu policy cho phép inherited roles, dùng `getAnnotationsByType(Role.class)` và ghi rõ mô hình kế thừa. Nhưng nhớ `@Inherited` chỉ tự tìm lên superclass khi class con chưa có annotation liên quan; **nó không merge tự động** toàn bộ danh sách hai tầng.

Nếu policy không cho inherited roles, `getDeclaredAnnotationsByType(Role.class)` rõ nghĩa hơn.

Nếu policy muốn gộp quyền từ nhiều tầng:
1. Duyệt `getSuperclass()` từ class hiện tại đến giới hạn mong muốn.
2. Ở mỗi tầng, dùng `getDeclaredAnnotationsByType(Role.class)` để tránh tự động nhận inherited lặp lại.
3. Xác định chiến lược **union, override, deny precedence và duplicates** trước khi gộp.
4. Viết test cho lớp cha có nhiều role, lớp con không role, lớp con có role trùng/khác và case container rỗng.

Không có một lựa chọn mặc định đúng cho mọi framework. Chính sách quyền/role là **quy tắc nghiệp vụ**, không nên suy ra máy móc từ `@Inherited`.

## 14. Những lỗi phổ biến khi kiểm thử annotation lặp

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| Chỉ test `@Role("reader")` | Không phát hiện code bỏ container khi có nhiều | Test 0, 1 và 2+ Role |
| Đọc bằng `getAnnotation(Role.class)` | Nhiều Role có thể bị coi là không có | Dùng `getAnnotationsByType(Role.class)` |
| Kiểm tra mảng chỉ bằng `!= null` | Mảng rỗng vẫn khác null | Assert `length` |
| Truy cập `roles[0]` khi zero | `ArrayIndexOutOfBoundsException` | Kiểm tra số lượng trước |
| Chỉ so sánh length | Bỏ qua giá trị Role bị sai | Assert value/sequence hoặc set |
| Nhầm `@Roles({})` với không có container | Mất thông tin đã cấu hình rỗng | Kiểm tra container riêng |
| Cho rằng `@Inherited` áp dụng mọi annotation | Method override không tự kế thừa | Test class và Method khác nhau |
| Cho rằng child luôn gộp roles từ cha | `getAnnotationsByType` không có logic union đa tầng | Định nghĩa merge policy riêng nếu cần |
| Retention `SOURCE` rồi dùng runtime reflection | Metadata không còn để đọc | Dùng `RUNTIME` cho reflection test |
| Container không có `Role[] value()` | `@Repeatable` không hợp lệ | Tuân thủ JLS |
| Container target/retention không tương thích | Có thể báo compile error | Đồng bộ meta-annotations đúng quy tắc |
| Dùng `getDeclaredAnnotation(Role.class)` trên nhiều Role rồi tưởng không có | Container che các Role trực tiếp | Dùng `getDeclaredAnnotationsByType` |
| So sánh annotation khác kiểu dựa thứ tự nguồn | Không có thứ tự chung đáng dựa | Chỉ test thứ tự repeatable khi có hợp đồng |
| Dùng `assert` Java mà không `-ea` | JVM có thể bỏ qua assertion | Dùng `AssertionError` tường minh hoặc JUnit |
| Test chỉ in output | Chương trình vẫn có exit code 0 nếu dữ liệu sai | Có assertions và kiểm tra CI |
| Trộn negative compile snippets vào runnable demo | Demo không biên dịch | Cô lập fixture cố ý sai |
| Dựa vào `getMethod` để kiểm tra method được khai báo tại chỗ | Có thể lấy inherited Method từ superclass | Dùng `getDeclaredMethod` cho declaration local |
| Giả định annotation tự áp quyền truy cập | Annotation chỉ là metadata | Framework phải đọc và thực thi policy đúng |

## 15. Checklist cho test suite

1. Annotation type được đánh dấu `@Repeatable(Container.class)` chưa?
2. Container có `value()` đúng kiểu `T[]` không?
3. `RetentionPolicy.RUNTIME` có cần thiết cho bài test reflection không?
4. Test zero annotation có assert mảng rỗng và không có container chưa?
5. Test exactly one có assert count 1 **và giá trị** chưa?
6. Test multiple có assert count và mọi giá trị chưa?
7. Test explicit container và empty container có cần cho ứng dụng không?
8. Đã phân biệt `getAnnotation` và `getAnnotationsByType` chưa?
9. Đã phân biệt `getAnnotationsByType` và `getDeclaredAnnotationsByType` chưa?
10. Nếu có `@Inherited`, test class con không local role và có local role chưa?
11. Test method override không tự nhận method annotation chưa?
12. Có kiểm tra target METHOD/TYPE/FIELD/PARAMETER đúng theo `@Target` không?
13. Assertion có làm build thất bại khi kết quả sai không?
14. Source intentionally noncompiling có được cô lập thành negative test không?
15. CI có chạy test trên JDK được hỗ trợ và xử lý lỗi test bằng exit code không?

## 16. Bài tập thực hành

1. Tạo `@Tag` repeatable và `@Tags` container. Gắn 0, 1, 3 tag lên ba class; dùng `getAnnotationsByType(Tag.class)` để assert số lượng.
2. Với class có ba tag, so sánh `getAnnotation(Tag.class)` và `getAnnotation(Tags.class)`. Vì sao đọc một annotation khác đọc toàn bộ?
3. Gắn `@Tags({})` lên class; phân biệt với class hoàn toàn không annotate bằng cách kiểm tra container.
4. Gắn hai annotation lên class cha, cho class con kế thừa, rồi kiểm tra `getAnnotationsByType` và `getDeclaredAnnotationsByType`.
5. Gắn một annotation `local` lên class con; giải thích vì sao `getAnnotationsByType` không tự trả thêm các Role từ cha.
6. Gắn `@Role` lên method ở class cha; override method trong con không annotate; kiểm chứng phản chiếu hai method khác nhau.
7. Viết một test có `AssertionError` cố ý khi kỳ vọng 3 role trên `TwoRoles`, kiểm tra exit code.
8. Với role metadata không có thứ tự nghiệp vụ, viết test so sánh `Set<String>` thay vì mảng có thứ tự.
9. Viết container sai kiểu `value()` và xác minh compiler từ chối trong một negative compilation test riêng.
10. Mở rộng target sang `FIELD` và kiểm tra hai `@Role` trên một field qua `Field.getAnnotationsByType`.
11. Tách ba unit tests JUnit cho 0, 1 và nhiều Role; xác định dependency JUnit Jupiter và JDK minimum.
12. Giải thích vì sao `@Retention(RUNTIME)` làm metadata đọc được nhưng không tự thực thi logic quyền truy cập.

## 17. Tài liệu chuẩn còn áp dụng

- [Java Language Specification — `9.6.3 Repeatable Annotation Types](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.6.3)
- [Java Language Specification — `9.7.5 Multiple Annotations of the Same Type](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.7.5)
- [Java SE 17 — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html)
- [Java SE 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 17 — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html)
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html)
- [JUnit 5 User Guide — Writing Tests and Assertions](https://junit.org/junit5/docs/current/user-guide/)

**Kết luận:** Với repeatable annotations, hãy test **zero / one / multiple** bằng `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType`, kiểm tra cả số lượng và nội dung. Thêm các test **container tường minh, container rỗng, inheritance trên class và method override** để tránh lỗi khó phát hiện. **Test thành công với một annotation không chứng minh ứng dụng xử lý đúng nhiều annotation** — chỉ bộ test có các trạng thái khác nhau và assertions rõ mới bảo vệ được hợp đồng của API.
