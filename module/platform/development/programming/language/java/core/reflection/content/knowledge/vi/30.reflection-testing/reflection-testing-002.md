# Kiểm thử declared member khác inherited member trong Java Reflection

## 1. Bài toán: một thành viên thuộc lớp nào?

Khi thiết kế bài kiểm thử cho công cụ dùng Reflection, cần phân biệt hai câu hỏi:

1. **Member có được khai báo trực tiếp trong lớp này không?** Đây là câu hỏi về *declared member*.
2. **Có thể tra cứu member `public` thông qua lớp này không?** Đây là câu hỏi về các thành viên công khai mà API Reflection nhìn thấy, có thể bao gồm member kế thừa.

Hai câu hỏi có kết quả khác nhau. Giả sử `Child extends Parent`, `Parent` khai báo `public void run()` và `Child` không override: `Child.class.getDeclaredMethod("run")` ném `NoSuchMethodException`; `Child.class.getMethod("run")` lại tìm được method do `Parent` khai báo.

Một bài test sai thường dùng `getDeclaredMethods()` để kiểm tra *toàn bộ API mà đối tượng Child có thể gọi*, rồi kết luận thiếu method kế thừa. Ngược lại, nếu dùng `getMethods()` để kiểm tra *các method do Child tự khai báo*, bài test lại có thể tính cả method từ superclass và interface.

Bài học hướng dẫn tạo fixture nhỏ, dùng assertion dương và âm, kiểm tra `getDeclaringClass()` và xử lý các trường hợp override, interface default/static method, field, constructor, overload, bridge/synthetic member. Tập trung vào **kiểm chứng metadata**, không đánh đồng việc tra cứu với quyền gọi phương thức private.

## 2. Các API Reflection cần đối chiếu

| Đối tượng | Declared tại lớp đang xét | Public nhìn thấy qua lớp |
| --- | --- | --- |
| Một method | `getDeclaredMethod(name, parameterTypes...)` | `getMethod(name, parameterTypes...)` |
| Danh sách method | `getDeclaredMethods()` | `getMethods()` |
| Một field | `getDeclaredField(name)` | `getField(name)` |
| Danh sách field | `getDeclaredFields()` | `getFields()` |
| Một constructor | `getDeclaredConstructor(parameterTypes...)` | `getConstructor(parameterTypes...)` |
| Danh sách constructor | `getDeclaredConstructors()` | `getConstructors()` |

Quy tắc quan trọng:

- Nhóm **`getDeclared*`** không đi lên superclass để lấy thành viên kế thừa. Nó trả metadata khai báo trong đúng lớp/interface hiện tại, kể cả non-public member. Có thể chứa bridge/synthetic member do compiler sinh.
- `getMethod(s)` và `getField(s)` chỉ trả **public member** theo phạm vi tra cứu của API, trong đó có thể có member được kế thừa. Chúng không phải danh sách mọi `protected` hoặc private member có trong cây kế thừa.
- Constructor **không được kế thừa**. Vì thế hai API constructor chỉ khác phạm vi truy cập public hay declared của **chính lớp đó**, không phải “constructor của cha và con”.
- Việc tìm được private member với `getDeclaredMethod` / `getDeclaredField` **không bảo đảm được quyền gọi/đọc**. `Method.invoke`, `Field.get` và `Constructor.newInstance` còn chịu kiểm tra truy cập, cùng ranh giới module khi có JPMS.
- API trả mảng như `getDeclaredMethods()` không cam kết thứ tự tương ứng với source code. Đừng assert phần tử tại index 0 là một method cố định.

### Ba khái niệm khác nhau

**Khai báo:** nơi member xuất hiện trong lớp/interface. `Method.getDeclaringClass()` hay `Field.getDeclaringClass()` giúp xác định.

**Kế thừa:** hành vi Java cho phép lớp con nhận từ kiểu cha theo các quy tắc override/hiding/access; một `private` method của cha không phải member được con kế thừa để override.

**Truy cập:** người gọi có quyền thực thi/read/write member hay không. Một member có thể có metadata nhưng không thể được truy cập theo ngữ cảnh gọi. Do đó test “tồn tại metadata” phải độc lập với test “gọi thành công”.

## 3. Fixture kiểm thử đủ nhỏ để nhìn ra nguyên nhân

Chúng ta cần một lớp cha, một lớp con và một interface:

~~~text
Work (interface)
 ├── defaultWork()      // default instance method
 └── utility()          // static interface method

Base
 ├── public visible()
 ├── public replace()   // sẽ bị override
 ├── protected protectedBase()
 ├── private privateBase()
 └── public int baseCount

Child extends Base implements Work
 ├── public local()
 ├── public replace()   // override
 ├── public int ownCount
 ├── private int hidden
 ├── public Child()
 └── private Child(int)
~~~

Fixture có cả trường hợp **thành công** và **thất bại có chủ ý**. Chẳng hạn, test không chỉ xác nhận `getMethod("visible")` thành công mà còn yêu cầu `getDeclaredMethod("visible")` thất bại. Nếu cả hai phép kiểm tra đều thành công, khả năng cao đã vô tình khai báo lại `visible` trong Child hoặc test đang chọn nhầm lớp.

Các assertion cốt lõi:

- `Child.class.getMethod("visible")` có `getDeclaringClass() == Base.class`.
- `Child.class.getMethod("replace")` có `getDeclaringClass() == Child.class`, vì Child khai báo override.
- `Base.class.getDeclaredMethod("privateBase")` tìm được metadata; `Child.class.getDeclaredMethod("privateBase")` không tìm được.
- `Child.class.getMethod("defaultWork")` lấy được default method của `Work`; `Child.class.getMethod("utility")` không tìm được static interface method.
- `Child.class.getField("baseCount")` lấy được public field của Base; `Child.class.getDeclaredField("baseCount")` thất bại.
- `Child.class.getDeclaredConstructor(int.class)` tìm được private constructor; `Child.class.getConstructor(int.class)` thì không.
- Danh sách trả về từ `getDeclaredMethods`/`getMethods` chỉ được đối chiếu theo **tên/tập thuộc tính có chủ đích**, không theo thứ tự phần tử.

## 4. Chương trình Java 17+ chạy độc lập và tự kiểm chứng

Tạo tệp **`DeclaredInheritedDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class DeclaredInheritedDemo {
    public interface Work {
        default String defaultWork() {
            return "default";
        }

        static String utility() {
            return "utility";
        }
    }

    public static class Base {
        public int baseCount = 10;
        protected int protectedCount = 20;
        private int privateCount = 30;

        public String visible() {
            return "base";
        }

        public String replace() {
            return "base version";
        }

        protected void protectedBase() {}
        private void privateBase() {}
    }

    public static class Child extends Base implements Work {
        public int ownCount = 40;
        private int hidden;

        public Child() {}

        private Child(int value) {
            ownCount = value;
        }

        public String local() {
            return "child";
        }

        @Override
        public String replace() {
            return "child version";
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static boolean declaredMethod(Class<?> type, String name) {
        try {
            type.getDeclaredMethod(name);
            return true;
        } catch (NoSuchMethodException ex) {
            return false;
        }
    }

    static boolean publicMethod(Class<?> type, String name) {
        try {
            type.getMethod(name);
            return true;
        } catch (NoSuchMethodException ex) {
            return false;
        }
    }

    static boolean declaredField(Class<?> type, String name) {
        try {
            type.getDeclaredField(name);
            return true;
        } catch (NoSuchFieldException ex) {
            return false;
        }
    }

    static boolean publicField(Class<?> type, String name) {
        try {
            type.getField(name);
            return true;
        } catch (NoSuchFieldException ex) {
            return false;
        }
    }

    static Set<String> methodNames(Method[] methods) {
        return Arrays.stream(methods)
                .map(Method::getName)
                .collect(Collectors.toCollection(TreeSet::new));
    }

    public static void main(String[] args) throws Exception {
        Class<Child> childType = Child.class;

        check(!declaredMethod(childType, "visible"),
                "Child must not declare inherited visible()");
        Method inherited = childType.getMethod("visible");
        check(inherited.getDeclaringClass() == Base.class,
                "visible() belongs to Base");
        check(inherited.invoke(new Child()).equals("base"),
                "inherited invocation");

        check(declaredMethod(childType, "replace"),
                "Child declares override");
        Method override = childType.getMethod("replace");
        check(override.getDeclaringClass() == Child.class,
                "replace() belongs to Child");

        check(declaredMethod(Base.class, "privateBase"),
                "Base declares private method");
        check(!declaredMethod(childType, "privateBase"),
                "Child does not declare Base private method");
        check(!publicMethod(childType, "privateBase"),
                "private method is not public");
        check(declaredMethod(Base.class, "protectedBase"),
                "Base declares protected method");
        check(!publicMethod(childType, "protectedBase"),
                "protected method is not public");

        Method defaultMethod = childType.getMethod("defaultWork");
        check(defaultMethod.getDeclaringClass() == Work.class,
                "default method declared in Work");
        check(!declaredMethod(childType, "defaultWork"),
                "Child does not declare default method");
        check(!publicMethod(childType, "utility"),
                "static interface method not inherited");
        check(publicMethod(Work.class, "utility"),
                "Work owns static method");

        Field base = childType.getField("baseCount");
        check(base.getDeclaringClass() == Base.class,
                "baseCount declared by Base");
        check(!declaredField(childType, "baseCount"),
                "Child does not declare baseCount");
        check(declaredField(childType, "hidden"),
                "Child declares private hidden");
        check(!publicField(childType, "hidden"),
                "private hidden is not public");
        check(!publicField(childType, "protectedCount"),
                "protected field is not public");

        Constructor<Child> noArgs = childType.getConstructor();
        Constructor<Child> privateCtor =
                childType.getDeclaredConstructor(int.class);
        check(noArgs.getDeclaringClass() == Child.class
                        && privateCtor.getDeclaringClass() == Child.class,
                "both constructors belong to Child");
        check(childType.getConstructors().length == 1,
                "one public constructor");
        check(childType.getDeclaredConstructors().length == 2,
                "two declared constructors");

        Set<String> declared = methodNames(
                childType.getDeclaredMethods());
        Set<String> visible = methodNames(childType.getMethods());
        check(declared.contains("local")
                        && declared.contains("replace")
                        && !declared.contains("visible"),
                "declared method set");
        check(visible.contains("visible")
                        && visible.contains("defaultWork")
                        && visible.contains("local"),
                "public method set");

        System.out.println("declared visible: "
                + declaredMethod(childType, "visible"));
        System.out.println("public visible: "
                + publicMethod(childType, "visible"));
        System.out.println("visible owner: "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("override owner: "
                + override.getDeclaringClass().getSimpleName());
        System.out.println("default owner: "
                + defaultMethod.getDeclaringClass().getSimpleName());
        System.out.println("interface static inherited: "
                + publicMethod(childType, "utility"));
        System.out.println("base field owner: "
                + base.getDeclaringClass().getSimpleName());
        System.out.println("local private public: "
                + publicField(childType, "hidden"));
        System.out.println("public constructors: "
                + childType.getConstructors().length);
        System.out.println("declared constructors: "
                + childType.getDeclaredConstructors().length);
        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac DeclaredInheritedDemo.java
java DeclaredInheritedDemo
~~~

Kết quả:

~~~text
declared visible: false
public visible: true
visible owner: Base
override owner: Child
default owner: Work
interface static inherited: false
base field owner: Base
local private public: false
public constructors: 1
declared constructors: 2
PASS
~~~

Chương trình tự ném `AssertionError` khi một điều kiện không đạt, vì vậy các kiểm tra vẫn hoạt động khi chạy Java **không bật `-ea`**. Điều này khác với câu lệnh `assert` thông thường của Java, vốn mặc định bị vô hiệu hóa.

**Không cần gọi `setAccessible(true)`:** chúng ta xác minh metadata private member được khai báo ở đâu, không thử vượt qua kiểm tra quyền truy cập.

## 5. Đọc kết quả: declared, inherited, override và interface

### 5.1. `getDeclaredMethod` khác `getMethod`

~~~java
Child.class.getMethod("visible");         // tìm được method Base
Child.class.getDeclaredMethod("visible"); // ném NoSuchMethodException
~~~

Đoạn trên chỉ minh họa khác biệt; lời gọi thứ hai cần được đặt trong `try/catch` hoặc phương thức `throws NoSuchMethodException` khi sử dụng độc lập.

`getDeclaredMethod` đọc từ **đúng Class của Child**. Vì `visible` chỉ được khai báo ở Base nên không tìm được. `getMethod` có phạm vi public method nên tìm thấy method kế thừa. Dùng:

~~~java
Method member = Child.class.getMethod("visible");
boolean fromBase = member.getDeclaringClass() == Base.class;
~~~

Đối với method không được Child override, `getDeclaringClass()` cho biết **nơi method được khai báo**, không phải runtime class của instance được truyền vào `invoke`.

### 5.2. Override: phương thức được khai báo lại tại Child

`Child` ghi đè `replace()` nên cả `Child.class.getDeclaredMethod("replace")` và `Child.class.getMethod("replace")` đều tìm được bản khai báo của Child. Nếu dùng `Method.invoke(new Child())`, dynamic dispatch theo receiver vẫn quan trọng; để chứng minh metadata đang chọn *bản nào*, dùng `getDeclaringClass()`.

Không đánh đồng “method thuộc quan hệ kế thừa” với “method metadata do cha khai báo”. Một override thực sự là **declaration mới tại Child** với quan hệ override tới method ở cha.

### 5.3. Protected và private không nằm trong public lookup

`Base.class.getDeclaredMethod("protectedBase")` và `Base.class.getDeclaredMethod("privateBase")` tìm được metadata, còn `Child.class.getMethod(...)` cho hai tên đó thất bại.

**Protected member có thể được kế thừa** theo quy tắc Java, nhưng không vì thế trở thành public. Private member của Base không được Child kế thừa/override theo cách của instance method public/protected. Nếu công cụ cần khảo sát tất cả declared members trong hệ phân cấp, phải tự duyệt qua từng `Class<?>` của superclass rồi dùng `getDeclaredMethods()` trên đúng lớp.

### 5.4. Interface default khác interface static

Method `defaultWork()` thuộc interface `Work` và được Child kế thừa dưới dạng hành vi default. Khi không override, `Child.class.getMethod("defaultWork").getDeclaringClass()` là `Work.class`.

`Work.utility()` là static method của interface, **không được Child kế thừa**: `Child.class.getMethod("utility")` thất bại, còn `Work.class.getMethod("utility")` tìm được. Đây là test quan trọng để tránh suy luận rằng mọi method public của interface đều xuất hiện trong API public của lớp triển khai.

### 5.5. Field: declared ở Child, inherited từ Base

`Child.class.getField("baseCount")` tìm public field thuộc Base, nhưng `Child.class.getDeclaredField("baseCount")` không tìm được. Ngược lại, `Child.class.getDeclaredField("hidden")` tìm private field của Child, còn `Child.class.getField("hidden")` thất bại vì đó không phải public field.

Một field **không override đa hình như instance method**. Nếu Child khai báo field cùng tên `baseCount`, nó tạo một field khác **hide** field của Base. Kiểm tra nguồn khai báo qua `Field.getDeclaringClass()` thay vì chỉ dùng `getName()`.

### 5.6. Constructor không bao giờ kế thừa

Constructor của Base không tự trở thành constructor của Child. `Child.class.getDeclaredConstructors()` chỉ nói về constructor khai báo trong Child; `getConstructors()` trả các constructor public của Child.

Với fixture của bài, Child khai báo một constructor public không tham số và một constructor private nhận `int`. Vì vậy `getConstructors().length == 1`, `getDeclaredConstructors().length == 2`. Những assertion về **số lượng constructor này** hợp lý vì fixture nhỏ và hoàn toàn do test kiểm soát.

## 6. Chọn đúng overload bằng danh sách kiểu tham số

Một tên method có thể có nhiều overload:

~~~java
class Example {
    public void parse(String text) {}
    public void parse(int value) {}
}
~~~

Hai overload đều tên `parse`; vì vậy kiểm tra `getDeclaredMethods()` rồi so sánh duy nhất `getName()` là chưa đủ.

~~~java
Method parseString =
        Example.class.getDeclaredMethod("parse", String.class);
Method parseNumber =
        Example.class.getDeclaredMethod("parse", int.class);
~~~

*Các fragment giả định có import `java.lang.reflect.Method` và xử lý `NoSuchMethodException`.*

Danh sách kiểu tham số **có thứ tự**: `f(int, String)` khác `f(String, int)`. Nếu xây khóa để so sánh toàn bộ danh sách method, có thể dùng `name + ordered parameterTypes + returnType + declaringClass`. Với bytecode chứa bridge/covariant return, return type cũng có thể cần để phân biệt metadata dù việc overload bằng mỗi return type không hợp lệ trong Java source.

Lưu ý `getDeclaredMethod(name, parameterTypes)` không nhận kiểu trả về. Nó hoạt động theo hợp đồng tra cứu của Reflection, không phải API chọn một method theo tùy ý mọi đặc tính trong class file.

## 7. Không kiểm thử theo thứ tự mảng do Reflection trả về

Các API `getDeclaredMethods()`, `getMethods()`, `getDeclaredFields()` và `getDeclaredConstructors()` **không cam kết thứ tự** thành viên. Những test sau dễ sai:

~~~java
// Sai vì phụ thuộc thứ tự không được API cam kết:
// boolean firstIsLocal = Child.class.getDeclaredMethods()[0]
//         .getName().equals("local");
~~~

Thay bằng:

~~~java
Set<String> names = Arrays.stream(Child.class.getDeclaredMethods())
        .map(Method::getName)
        .collect(Collectors.toSet());

boolean hasLocal = names.contains("local");
~~~

*Fragment cần import `Set`, `Arrays`, `Method`, `Collectors`; lớp `Child` lấy từ ví dụ chính.*

Nếu cần chứng minh nhiều overload khác nhau, thay `Set<String>` tên method bằng một tập khóa có danh sách kiểu tham số được chuẩn hóa. Việc chỉ nhìn tên phù hợp với bài kiểm tra **sự hiện diện sơ bộ**, nhưng không phù hợp để xác thực một chữ ký cụ thể.

**Synthetic/bridge member:** compiler có thể tạo method phụ để duy trì dispatch của generic/covariant return. `Method.isBridge()` và `Method.isSynthetic()` giúp nhận diện. Nếu mục tiêu là API gần với source, công cụ có thể chọn lọc; nếu mục tiêu là phân tích bytecode, phải giữ chúng. Đừng kiểm thử “đúng N method” ở những tình huống có thể chứa bridge nếu chưa định nghĩa cách đếm.

## 8. Case JUnit 5 hoặc test framework: kiểm cả thành công và thất bại

Nếu dự án đã dùng JUnit 5, có thể diễn đạt điều kiện theo cách sau:

~~~java
// Fragment đặt trong lớp test có import org.junit.jupiter.api.Test,
// import static org.junit.jupiter.api.Assertions.*;

@Test
void inheritedPublicMethodIsNotDeclaredInChild() throws Exception {
    assertThrows(NoSuchMethodException.class,
            () -> Child.class.getDeclaredMethod("visible"));

    Method inherited = Child.class.getMethod("visible");
    assertEquals(Base.class, inherited.getDeclaringClass());
}

@Test
void overrideIsDeclaredInChild() throws Exception {
    Method overridden = Child.class.getDeclaredMethod("replace");
    assertEquals(Child.class, overridden.getDeclaringClass());
}
~~~

Đây là **JUnit fragment**, không phải một chương trình độc lập: cần dependency `org.junit.jupiter:junit-jupiter` và các lớp `Child`, `Base` của fixture. Các phép kiểm tra như vậy có tín hiệu rõ hơn so với test chỉ xem method count.

Khi dùng Java thuần, ví dụ mục 4 đã làm cùng việc bằng `check(...)` và `try/catch` trong helper. Chọn một phong cách thống nhất với hạ tầng kiểm thử của dự án.

## 9. Các tình huống đặc biệt trong hệ phân cấp

**Nhiều cấp superclass:** `Child.class.getDeclaredMethods()` không cộng tất cả declared methods của Parent, Grandparent. Nếu muốn một danh sách chi tiết toàn bộ hệ phân cấp, tự duyệt `getSuperclass()` và giữ `getDeclaringClass()` để phân biệt các khai báo.

**Interface kế thừa interface:** `SubInterface.class.getMethod(...)` có thể tìm method public từ `SuperInterface`. Nhưng `getDeclaredMethod(...)` trên SubInterface chỉ tìm method trực tiếp khai báo ở SubInterface.

**Field hiding:** Parent và Child có thể có field public cùng tên. Khi phân tích toàn bộ metadata, hai field thuộc hai owner khác nhau. `getField(name)` chọn theo quy tắc tra cứu, không giúp liệt kê mọi field bị hide trong cây lớp.

**Method overload:** method khác nhau theo tên và danh sách tham số, không chỉ tên. Dùng đúng thứ tự `Class<?>... parameterTypes`.

**Generic bridge:** một generic superclass và một subclass override bằng kiểu cụ thể có thể sinh bridge method. Việc dùng `getDeclaredMethods()` để đếm source methods cần một chính sách loại hoặc giữ bridge/synthetic.

**Interface static:** static method khai báo ở interface không truyền thành member của class triển khai; khác với default instance method.

**Quyền module:** method có thể nằm trong metadata mà không được invoke/đọc do Java access checks; phân biệt lookup thành công với sử dụng thành công.

## 10. Checklist thiết kế bài kiểm thử

| Trường hợp | Assertion nên có |
| --- | --- |
| Own public method | Declared lookup có; public lookup có; owner là Child |
| Inherited public method | Declared lookup không; public lookup có; owner là Base |
| Override | Declared lookup có; owner là Child |
| Parent private method | Parent declared lookup có; Child public/declared lookup không |
| Parent protected method | Parent declared lookup có; Child public lookup không |
| Interface default method | Child public lookup có; nếu chưa override thì Child declared lookup không |
| Interface static method | Interface public lookup có; Child public lookup không |
| Child private field | Child declared lookup có; public lookup không |
| Inherited public field | Child public lookup có; Child declared lookup không; owner là Base |
| Constructor private | Declared constructor có; public constructor không |
| Constructor của cha | Không được kế thừa thành constructor của con |
| Hai overload cùng tên | Kiểm danh sách kiểu tham số đúng thứ tự |
| Danh sách metadata | Không assert theo index; dùng set/key và policy synthetic/bridge |

Để báo lỗi rõ khi test thất bại, mỗi assertion nên ghi cả tên member và kỳ vọng. Ví dụ “Child must not declare visible()” cụ thể hơn “reflection failed”. Đồng thời, dùng fixture nhỏ để thay đổi test có nguyên nhân dễ nhận ra.

## 11. Tự kiểm tra

Giả sử `Child extends Base` và Base khai báo `public void start()`, Child không override:

1. `Child.class.getDeclaredMethod("start")` cho kết quả gì? **`NoSuchMethodException`.**
2. `Child.class.getMethod("start")` có tìm được không? **Có**, vì đây là public method kế thừa.
3. `getDeclaringClass()` của method đó là gì? **`Base.class`.**
4. Nếu Child override `start()`, `getDeclaredMethod("start")` có thành công không? **Có**, vì Child đã khai báo method mới.
5. Nếu Base có `private void secret()`, có tìm được bằng `Child.class.getDeclaredMethod("secret")` không? **Không**; cần tra trên `Base.class`.
6. `Child.class.getConstructors()` có trả các constructor public của Base không? **Không**.
7. Nếu interface có `static void util()`, lớp implements có tự kế thừa method này không? **Không**.
8. Có thể suy ra thứ tự khai báo từ index của `getDeclaredMethods()` không? **Không**.
9. Với hai overload `f(int)` và `f(String)`, một key chỉ có tên `f` có đủ không? **Không**.
10. Vì sao trong ví dụ dùng `check` thay vì Java `assert`? **Vì `assert` bị tắt khi không bật `-ea`, còn `check` vẫn kiểm tra.**

## 12. Kết luận

**Declared** mô tả nơi member được khai báo; **inherited/public lookup** mô tả phạm vi tra cứu member theo Java Reflection. Với method và field, hãy đối chiếu `getDeclared*` và `get*`, dùng `getDeclaringClass()` để xác nhận owner, kiểm thử cả trường hợp tìm được lẫn `NoSuchMethodException`/`NoSuchFieldException`. Constructor không được kế thừa. Interface default/static, override, field hiding, overload và bridge/synthetic method cần xem đúng ngữ nghĩa. Một test đáng tin không dựa vào thứ tự mảng hoặc số lượng method tổng quát; nó chứng minh chính xác quan hệ giữa kiểu, member và quyền truy cập.

Tài liệu tham khảo:

- [Java SE 21 — `Class`, các API `getMethod` / `getDeclaredMethod` / field / constructor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 21 — `Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 21 — `Constructor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html)
- [Java Language Specification SE 21 — Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html)