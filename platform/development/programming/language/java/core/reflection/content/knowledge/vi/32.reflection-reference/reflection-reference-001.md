# Bảng so sánh `getX` và `getDeclaredX` trong Java Reflection

## 1. Hai nhóm API giải quyết hai câu hỏi khác nhau

Khi làm việc với `java.lang.Class<?>`, các lời gọi Reflection thường có hai “họ” tên gần giống nhau:

- **`getX(...)` / `getXs()`**: đối với **method, field, constructor và member class**, nhóm tương ứng thường tập trung vào **thành viên `public`**, đôi khi bao gồm thành viên `public` được **kế thừa**.
- **`getDeclaredX(...)` / `getDeclaredXs()`**: tìm những thành viên được **khai báo trực tiếp trong chính kiểu đang xét**, bao gồm `public`, `protected`, package-private và `private`; **không tự duyệt thành viên kế thừa**.

Hai chiều phân biệt quan trọng là:

1. **Visibility:** chỉ `public` hay mọi mức truy cập?
2. **Nguồn gốc:** thành viên được khai báo trực tiếp hay có thể kế thừa từ superclass/interface?

**Không có quy tắc “`getX` luôn duyệt inheritance” cho mọi loại thành viên.** Ví dụ constructor **không kế thừa** trong Java. Annotation có quy tắc kế thừa riêng theo `@Inherited`, không áp dụng y hệt method/field. Do đó, cần học **bảng theo từng loại `X`** thay vì áp một khẩu quyết cho tất cả API.

Mọi ví dụ trong bài dựa trên Java 17 trở lên. `getX` và `getDeclaredX` chỉ **trả về metadata hoặc thông tin kiểu**; không mặc nhiên cấp quyền gọi `private` member, không tự chạy method và không tự tạo instance.

## 2. Bảng tổng quát: các cặp API trên `Class<?>`

### 2.1. Phương thức — `Method`

| Nhu cầu | `getX` | `getDeclaredX` |
| --- | --- | --- |
| Lấy một method theo tên và danh sách kiểu tham số | `getMethod(String, Class<?>...)` | `getDeclaredMethod(String, Class<?>...)` |
| Lấy tập method | `getMethods()` | `getDeclaredMethods()` |
| Visibility | Chỉ method `public` | Mọi mức truy cập |
| Method kế thừa | Có thể bao gồm `public` method từ superclass và interface | Không; chỉ method khai báo trực tiếp |
| Private method ở class hiện tại | Không tìm thấy bằng `getMethod` | Có thể lấy metadata bằng `getDeclaredMethod` |
| Method `public` khai báo trực tiếp | Có | Có |
| Method `public` của `Object` | Thường xuất hiện trong `getMethods()` khi áp dụng cho class thông thường | Chỉ hiện nếu class đang xét trực tiếp khai báo/override nó |

Cả hai API dạng đơn đều xét **tên + kiểu tham số khai báo**, không truyền giá trị đối số. Ví dụ:

```java
Method one = type.getMethod("process", String.class);
Method two = type.getDeclaredMethod("process", String.class);
```

Đây là đoạn minh họa: phải có biến `Class<?> type` và import `java.lang.reflect.Method`. Không có tham số receiver trong lời gọi tìm metadata, mặc dù việc gọi instance method sau này cần một instance.

**Một điểm tinh tế:** `Class.getMethod(...)` có quy tắc tìm kiếm public member trong class/interface hierarchy, không phải “trả method ở superclass đầu tiên gặp được”. Nếu method bị override, API có thể chọn method phù hợp được khai báo ở subclass. Khi cần biết method do ai khai báo, dùng `method.getDeclaringClass()`. `getDeclaredMethod(...)` chỉ kiểm tra class/interface hiện tại.

### 2.2. Trường — `Field`

| Nhu cầu | `getX` | `getDeclaredX` |
| --- | --- | --- |
| Lấy một field theo tên | `getField(String)` | `getDeclaredField(String)` |
| Lấy tập field | `getFields()` | `getDeclaredFields()` |
| Visibility | Chỉ `public` | Mọi mức truy cập |
| Field từ superclass/interface | Có thể xuất hiện nếu `public` | Không tự lấy field kế thừa |
| Private field khai báo tại class hiện tại | Không | Có thể lấy metadata |
| Field `static` hoặc instance | Đều có thể được trả nếu phù hợp | Đều có thể được trả nếu phù hợp |

Field **không override**, mà có thể bị **che khuất (*field hiding*)** trong subclass. Khi cả superclass và subclass có field cùng tên, các API lookup có chính sách chọn đối tượng `Field` riêng; không coi hai field khác declaring class là một. Dùng `field.getDeclaringClass()` để xác minh. Với công cụ mapping dữ liệu, nhiều khi cần tự duyệt hierarchy và xác định có chấp nhận field bị che khuất hay không.

`getDeclaredFields()` có thể trả field do compiler tạo (`isSynthetic()`), đặc biệt trong inner class hoặc những cấu trúc được biên dịch đặc biệt. Đây vẫn là metadata của class file; muốn liệt kê state nghiệp vụ thì đặt bộ lọc riêng.

### 2.3. Constructor — `Constructor<?>`

| Nhu cầu | `getX` | `getDeclaredX` |
| --- | --- | --- |
| Lấy một constructor theo danh sách kiểu tham số | `getConstructor(Class<?>...)` | `getDeclaredConstructor(Class<?>...)` |
| Lấy tập constructor | `getConstructors()` | `getDeclaredConstructors()` |
| Visibility | Chỉ `public` | Mọi mức truy cập |
| Kế thừa từ superclass | **Không** | **Không** |
| Private constructor của class hiện tại | Không | Có thể lấy metadata |
| Constructor `public` của chính class | Có | Có |

Constructor không có tên method do caller cung cấp; tên nguồn trùng tên class, còn Reflection chọn theo danh sách kiểu tham số. Constructor của superclass **không** được kế thừa xuống subclass.

Một class có thể có nhiều constructor overload. Nếu bạn truyền sai signature cho `getConstructor(...)` hoặc `getDeclaredConstructor(...)`, chương trình ném `NoSuchMethodException`, kể cả khi class thực sự có một constructor “trông tương tự”.

### 2.4. Member class/interface — `Class<?>[]`

| API | Ý nghĩa |
| --- | --- |
| `getClasses()` | Trả các class và interface **thành viên `public`** của kiểu; đối với class có thể bao gồm public member types được kế thừa |
| `getDeclaredClasses()` | Trả các class/interface **thành viên khai báo trực tiếp** trong kiểu, bất kể visibility |

Ví dụ, `Parent.PublicNested` có thể xuất hiện trong `Child.class.getClasses()` nếu `Child extends Parent`; `Child.PrivateNested` nằm trong `Child.class.getDeclaredClasses()` nhưng không xuất hiện trong `getClasses()` vì không public.

**Không nhầm `getDeclaredClasses()` với “mọi class được viết bên trong method”.** API này nhằm vào *member class/interface*, không liệt kê tùy ý tất cả local class/anonymous class có trong bytecode. Muốn tìm class bao quanh một nested/local/anonymous class đã biết, xem thêm `getDeclaringClass()`, `getEnclosingClass()`, `getEnclosingMethod()` và `getEnclosingConstructor()` — nhưng chúng không có một cặp `getDeclared...` tương ứng với cùng ý nghĩa.

### 2.5. Annotation — `AnnotatedElement` và `Class<?>`

| API | Nội dung trả về | Kế thừa |
| --- | --- | --- |
| `getAnnotation(A.class)` | Một annotation loại `A` được thấy theo quy tắc của `AnnotatedElement` | Với **class** và annotation mang `@Inherited`, có thể lấy từ superclass |
| `getDeclaredAnnotation(A.class)` | Một annotation loại `A` được **khai báo trực tiếp** | Không tìm từ superclass |
| `getAnnotations()` | Các annotation được xem là “present” | Với **class**, có thể gồm annotation `@Inherited` từ superclass |
| `getDeclaredAnnotations()` | Annotation trực tiếp trên element | Không kế thừa |
| `getAnnotationsByType(A.class)` | Các annotation loại `A` theo quy tắc repeatable và inheritance | Có thể xét inheritance trên class theo điều kiện `@Inherited` |
| `getDeclaredAnnotationsByType(A.class)` | Annotation loại `A` được khai báo trực tiếp hoặc chứa trong container repeatable khai báo trực tiếp | Không duyệt superclass |

**Quy tắc `@Inherited` không áp dụng cho annotation trên method, field, constructor hoặc interface theo kiểu kế thừa class.** Ví dụ subclass override một method thì annotation của method ở superclass không tự động xuất hiện như annotation được “thừa kế” trên method mới. Framework muốn chính sách đó phải tự duyệt method hierarchy.

Với repeatable annotation (`@Repeatable`), các API `ByType` còn hiểu annotation chứa trong **container annotation**; vì vậy không thể đơn giản thay thế `getAnnotationsByType` bằng một `getAnnotation` đơn lẻ.

**Tóm lại:** Cặp “declared” trong annotation có nghĩa **trực tiếp trên element**, nhưng “không declared” không đồng nghĩa “mọi annotation của mọi ancestor”.

## 3. Những nhóm API không có cặp `getDeclaredX` tương ứng

Không phải tên API nào bắt đầu `get` cũng có overload/họ `getDeclared`. Chẳng hạn:

- `getSuperclass()` và `getGenericSuperclass()`: lấy superclass của kiểu; không có `getDeclaredSuperclass()`.
- `getInterfaces()` và `getGenericInterfaces()`: mô tả các interface được khai báo trực tiếp trong danh sách `implements`/`extends` của kiểu đang xét; không phải API “mọi interface kế thừa theo cây” và không có `getDeclaredInterfaces()`.
- `getTypeParameters()`: generic type variables khai báo tại class; không có `getDeclaredTypeParameters()`.
- `getEnclosingClass()`, `getEnclosingMethod()`, `getEnclosingConstructor()`: mô tả ngữ cảnh lexical enclosing cho một kiểu khi có; không có cặp declared trực tiếp.
- `getDeclaringClass()`: phân biệt thành viên nested type và lớp khai báo; không giống `getEnclosingClass()` trong mọi trường hợp.
- `getRecordComponents()`: trả record component metadata cho record (Java 16+), hoặc `null` nếu không phải record; không có `getDeclaredRecordComponents()`.

**Không tự chế API có tên `getDeclaredX` bằng quy tắc đặt tên.** Tra cứu đúng API hiện hữu trên `Class` hoặc `AnnotatedElement`. Bài này tập trung vào các nhóm Reflection truy vấn thành viên và annotation, không phải mọi method trong JDK.

## 4. Ví dụ Java 17+ hoàn chỉnh: so sánh các kết quả

Ví dụ dùng subclass có inherited public method/field, private method/field/constructor, nested class public kế thừa và nested class private. Nó cũng chứng minh khác biệt annotation `@Inherited`.

Lưu thành **`DeclaredVsPublicDemo.java`**:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class DeclaredVsPublicDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @interface Tag {
        String value();
    }

    @Tag("from-parent")
    public static class Parent {
        public int inheritedField = 1;
        private int parentPrivateField = 2;

        public Parent() {}

        public void inheritedCall() {}

        private void parentPrivateCall() {}

        public static class PublicNested {}
    }

    public static class Child extends Parent {
        private String secret = "hidden";

        public Child() {}

        private Child(int code) {
            this.secret = "id-" + code;
        }

        public String local() {
            return "local";
        }

        private void hidden() {}

        private static class PrivateNested {}
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        System.out.println("method inherited public="
                + (type.getMethod("inheritedCall")
                        .getDeclaringClass() == Parent.class));
        System.out.println("method inherited declared absent="
                + hasNoDeclaredMethod(type, "inheritedCall"));
        System.out.println("method private declared="
                + (type.getDeclaredMethod("hidden")
                        .getDeclaringClass() == Child.class));
        System.out.println("method private public absent="
                + hasNoPublicMethod(type, "hidden"));

        System.out.println("field inherited public="
                + (type.getField("inheritedField")
                        .getDeclaringClass() == Parent.class));
        System.out.println("field inherited declared absent="
                + hasNoDeclaredField(type, "inheritedField"));
        System.out.println("field private declared="
                + (type.getDeclaredField("secret")
                        .getDeclaringClass() == Child.class));
        System.out.println("field private public absent="
                + hasNoPublicField(type, "secret"));

        System.out.println("constructor public count="
                + type.getConstructors().length);
        System.out.println("constructor declared count="
                + type.getDeclaredConstructors().length);
        System.out.println("constructor private declared="
                + Modifier.isPrivate(
                        type.getDeclaredConstructor(int.class)
                                .getModifiers()));

        System.out.println("nested inherited public="
                + Arrays.asList(type.getClasses())
                        .contains(Parent.PublicNested.class));
        System.out.println("nested own private declared="
                + Arrays.asList(type.getDeclaredClasses())
                        .contains(Child.PrivateNested.class));

        System.out.println("annotation inherited="
                + (type.getAnnotation(Tag.class) != null));
        System.out.println("annotation declared absent="
                + (type.getDeclaredAnnotation(Tag.class) == null));

        String declaredNames =
                Arrays.stream(type.getDeclaredMethods())
                        .filter(m -> !m.isSynthetic() && !m.isBridge())
                        .map(Method::getName)
                        .sorted()
                        .collect(Collectors.joining(","));
        System.out.println("declared method names=" + declaredNames);
    }

    private static boolean hasNoDeclaredMethod(
            Class<?> type, String name) {
        try {
            type.getDeclaredMethod(name);
            return false;
        } catch (NoSuchMethodException e) {
            return true;
        }
    }

    private static boolean hasNoPublicMethod(
            Class<?> type, String name) {
        try {
            type.getMethod(name);
            return false;
        } catch (NoSuchMethodException e) {
            return true;
        }
    }

    private static boolean hasNoDeclaredField(
            Class<?> type, String name) {
        try {
            type.getDeclaredField(name);
            return false;
        } catch (NoSuchFieldException e) {
            return true;
        }
    }

    private static boolean hasNoPublicField(
            Class<?> type, String name) {
        try {
            type.getField(name);
            return false;
        } catch (NoSuchFieldException e) {
            return true;
        }
    }
}
```

### Biên dịch và chạy

```bash
javac DeclaredVsPublicDemo.java
java DeclaredVsPublicDemo
```

Kết quả dự kiến trên JDK 17:

```text
method inherited public=true
method inherited declared absent=true
method private declared=true
method private public absent=true
field inherited public=true
field inherited declared absent=true
field private declared=true
field private public absent=true
constructor public count=1
constructor declared count=2
constructor private declared=true
nested inherited public=true
nested own private declared=true
annotation inherited=true
annotation declared absent=true
declared method names=hidden,local
```

**Lưu ý kỹ thuật về ví dụ:** `getDeclaredMethods()` của `Child` chỉ gồm hai method `hidden` và `local` vì các method helper `hasNo...` nằm trong **outer class `DeclaredVsPublicDemo`**, không thuộc `Child`. `Child` là nested class thành viên; không khai báo method do compiler sinh trong ví dụ trên với `javac` JDK 17. Dòng `sorted()` loại sự phụ thuộc vào thứ tự trả về của Reflection.

### Phân tích từng nhóm kết quả

- `Child.class.getMethod("inheritedCall")` tìm public method từ `Parent`; `getDeclaringClass()` là `Parent.class`. Nhưng `Child.class.getDeclaredMethod("inheritedCall")` ném `NoSuchMethodException` vì `Child` không khai báo method này.
- `Child.class.getDeclaredMethod("hidden")` tìm được private method của `Child`. `Child.class.getMethod("hidden")` không tìm được vì nó không public.
- `getField("inheritedField")` nhìn thấy public field từ `Parent`; `getDeclaredField("inheritedField")` không nhìn thấy nó. Ngược lại, `getDeclaredField("secret")` tìm được private field của `Child`, còn `getField("secret")` không.
- `Child` có một constructor `public` và một constructor `private` nên `getConstructors().length == 1`, `getDeclaredConstructors().length == 2`. Không constructor nào của `Parent` được kế thừa.
- `Child.class.getClasses()` tìm được `Parent.PublicNested`; `Child.class.getDeclaredClasses()` tìm được `Child.PrivateNested` dù nested class này private.
- `@Tag` được khai báo trực tiếp trên `Parent` và mang `@Inherited`; `Child.class.getAnnotation(Tag.class)` trả annotation được kế thừa theo quy tắc class, còn `getDeclaredAnnotation(Tag.class)` là `null`.
- Các phép thử báo “absent=true” thực sự bắt đúng `NoSuchMethodException` hoặc `NoSuchFieldException`. Chúng không che giấu lỗi khác bằng `catch (Exception ignored)`.

## 5. Đọc bảng kết quả đúng cách: không trộn “metadata có tồn tại” với “có quyền gọi”

`getDeclaredMethod("hidden")` thành công **không** có nghĩa mã ở mọi nơi đều được phép gọi private method ấy.

Ví dụ minh họa, đặt trong một method có `throws ReflectiveOperationException` và các instance phù hợp:

```java
Method hidden = Child.class.getDeclaredMethod("hidden");
// hidden.invoke(child) có thể bị từ chối truy cập tùy caller.
```

Cần xét:

- **Java visibility**: `public`, `protected`, package-private, `private` và mối quan hệ giữa caller/target.
- **Java Platform Module System (JPMS)**: package đã `exports` cho public API hay `opens` cho deep reflection, module caller có thể đọc module target không?
- **`AccessibleObject`**: `canAccess(receiver)`, `trySetAccessible()` hoặc `setAccessible(true)` có thể kiểm tra/thay đổi khả năng suppress access, nhưng có giới hạn JPMS.
- **Method handle**: `MethodHandles.Lookup` và `privateLookupIn` có quy tắc quyền riêng; việc có `Method` không tự cấp quyền tạo handle.
- **Đối tượng đích và tham số**: receiver đúng kiểu, số lượng/kiểu đối số, constructor gọi được; metadata hợp lệ không làm thao tác đích chắc chắn thành công.

**`getDeclared...` không có nghĩa “bỏ qua `private`”**. Nó có nghĩa API truy vấn không giới hạn vào public member; quyền truy cập thực thi là bước tiếp theo.

Một kiểu ở package không exported vẫn có thể bộc lộ metadata cho một số API, nhưng điều đó không chứng minh code ở module khác gọi được `public` member của kiểu đó. Đừng dùng `Modifier.isPublic(...)` làm kết luận cuối cùng về quyền xuyên module.

## 6. Cách chọn `getMethods()` hay `getDeclaredMethods()` cho từng công cụ

### 6.1. Tạo danh sách API public mà caller được phép sử dụng

Khi muốn liệt kê API public của một class, `getMethods()` thường là điểm xuất phát phù hợp hơn `getDeclaredMethods()` vì nó có thể nhận cả method public từ superclass/interface. Tuy nhiên:

- Kết quả có thể chứa method từ `Object` như `toString`, `hashCode`, `getClass`.
- Kết quả có thể có method static, method overload, bridge hoặc synthetic.
- Public metadata không bảo đảm caller từ module khác có quyền tương ứng.
- Nếu ứng dụng chỉ muốn operation được đánh dấu annotation, phải áp dụng thêm filter riêng.

Ví dụ minh họa: lọc method công khai không static, không synthetic/bridge rồi sắp xếp:

```java
List<Method> methods = Arrays.stream(type.getMethods())
        .filter(m -> !Modifier.isStatic(m.getModifiers()))
        .filter(m -> !m.isSynthetic() && !m.isBridge())
        .sorted(Comparator.comparing(Method::getName))
        .toList();
```

Đoạn này cần `Class<?> type` cùng imports `List`, `Method`, `Arrays`, `Modifier`, `Comparator`; chỉ là snippet, không phải chương trình độc lập. Sorting theo tên giúp thứ tự hiển thị, nhưng **không tạo khóa duy nhất cho overloaded methods**.

### 6.2. Kiểm tra chi tiết cấu trúc một class

Khi viết serializer, ORM, debugger hoặc công cụ phân tích bytecode, `getDeclaredFields()`/`getDeclaredMethods()` có thể phù hợp hơn vì cho biết thành viên khai báo thực sự trong class. Nếu cần đi qua superclass, phải tự duyệt:

```java
for (Class<?> current = type;
        current != null;
        current = current.getSuperclass()) {
    for (Field field : current.getDeclaredFields()) {
        // Phân tích field thuộc riêng current.
        // Không ngầm giả định công cụ có quyền Field.get/set.
    }
}
```

Đây là snippet minh họa, cần có biến `Class<?> type` và import `Field`. Với interface, việc duyệt qua `getInterfaces()` cần một nhánh riêng (class superclass loop không tự tổng hợp interface hierarchy).

Nếu muốn bỏ qua các field không phải trạng thái instance, kiểm tra `Modifier.isStatic(field.getModifiers())`. Nếu muốn chỉ giữ field đọc/ghi được, phải xét `final` và quyền truy cập. **Không coi mọi member declared là member phù hợp với nghiệp vụ**.

### 6.3. Chọn constructor cho dependency injection

`getDeclaredConstructors()` có thể hữu ích để phát hiện constructor non-public hoặc được đánh dấu annotation, nhưng **không nên gọi constructor đầu tiên trong mảng**: thứ tự không bảo đảm, và quyền truy cập vẫn phải được kiểm tra. `getConstructors()` chỉ phù hợp nếu DI framework dự kiến dùng constructor public.

Ví dụ, các constructor của record, enum, non-static inner class và class có constructor compiler sinh có những đặc điểm riêng; cần dùng signature thật từ Reflection, không suy từ tên hiển thị.

### 6.4. Tạo schema từ annotation

Với class-level annotation mang `@Inherited`, `getAnnotation` hoặc `getAnnotationsByType` có thể hợp lý nếu framework có chủ ý nhận metadata từ superclass. Nếu công cụ chỉ muốn annotation khai báo **trên chính class**, dùng `getDeclaredAnnotation` / `getDeclaredAnnotationsByType`.

Đừng quên method/field annotations **không tự kế thừa theo `@Inherited`**. Nếu policy yêu cầu tìm annotation trên overridden method, hãy làm rõ quy tắc tự duyệt superclasses/interfaces, resolve method signature và cách xử lý xung đột.

## 7. Các lỗi thường gặp

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Dùng `getDeclaredMethod` rồi mong tìm inherited method | Declared chỉ kiểm tra kiểu hiện tại | Dùng `getMethod` nếu cần public method kế thừa, hoặc tự duyệt hierarchy |
| Dùng `getMethod` để tìm private method | `getMethod` chỉ public | `getDeclaredMethod` để lấy metadata, sau đó kiểm tra access hợp lệ |
| Dùng `getDeclaredFields` rồi nghĩ đã có mọi field của superclass | Không tự duyệt superclass | Lặp `getSuperclass()` và dùng `getDeclaredFields()` cho từng kiểu |
| Mong `getConstructors` trả constructor superclass | Constructor không kế thừa | Chỉ truy vấn constructor của class cần tạo |
| Lấy `getDeclaredClasses` rồi mong thấy mọi local/anonymous class trong method | API trả member classes/interfaces trực tiếp | Phân biệt member/nested/local/anonymous và các API enclosing |
| Nghĩ `getAnnotation` và `getDeclaredAnnotation` luôn giống nhau | Class annotation `@Inherited` có thể kế thừa | Chọn policy inheritance rõ ràng |
| Nghĩ annotation `@Inherited` truyền xuống overridden method | `@Inherited` không áp dụng như vậy cho method | Tự duyệt method hierarchy nếu cần |
| Bỏ qua `NoSuchMethodException`/`NoSuchFieldException` | Sai tên/chữ ký khiến lookup thất bại | Bắt lỗi đúng loại, ghi tên và tham số đã tìm |
| Tưởng `getDeclared...` giúp gọi private member xuyên module | Lookup metadata không cấp quyền thực thi | Xử lý `opens`/`Lookup`/access thay vì vượt rào |
| Phụ thuộc `getMethods()[0]` hay `getDeclaredFields()[0]` | Thứ tự mảng không được bảo đảm | Sắp xếp với comparator/key có chủ đích |
| Chỉ dùng method name làm khóa | Overload có thể trùng tên | Dùng tên + kiểu tham số, và nếu cần cả declaring class/loader |
| Gọi Reflection trên `null` instance hoặc sai receiver | Metadata lookup hợp lệ nhưng invoke/field access sai | Kiểm tra receiver và đối số trước khi thực thi |

**Ghi nhớ về exception:** Các lời gọi đơn `getMethod`, `getDeclaredMethod`, `getConstructor` và `getDeclaredConstructor` có thể ném `NoSuchMethodException`; các lời gọi đơn `getField` / `getDeclaredField` có thể ném `NoSuchFieldException`. API trả **mảng** khi không có kết quả thường trả mảng rỗng, không ném “NoSuchX” chỉ vì danh sách không có thành viên. Ngoài ra vẫn có thể có lỗi khác liên quan đến nạp kiểu, bảo mật hoặc môi trường runtime.

## 8. Checklist tra cứu Reflection chính xác

1. **Chọn loại dữ liệu:** method, field, constructor, member class hay annotation?
2. **Xác định visibility cần tìm:** public API hay cả member non-public?
3. **Xác định scope:** chỉ khai báo trực tiếp, hay có xét superclass/interface?
4. **Đọc bảng API tương ứng:** đừng áp quy tắc inheritance của method cho constructor/annotation.
5. **Tìm đúng chữ ký:** method và constructor dựa trên danh sách kiểu tham số; với overload, tên thôi chưa đủ.
6. **Xác minh declaring class:** dùng `getDeclaringClass()` của `Method`/`Field`/`Constructor` để không nhầm nguồn gốc.
7. **Đặt chính sách lọc:** static, bridge, synthetic, abstract, final, annotation và khả năng thực thi tùy mục tiêu.
8. **Kiểm tra access riêng:** class visibility, JPMS `exports`/`opens`, caller, receiver, `trySetAccessible` khi có lý do hợp lệ.
9. **Sắp xếp kết quả:** nếu cần hiển thị ổn định hoặc so sánh snapshot qua các lần chạy.
10. **Chỉ cache khi đúng key và lifecycle:** `Class<?>` phản ánh class loader identity; tránh map chỉ dựa trên tên class nếu có nhiều loader.

### Câu hỏi tự kiểm tra

1. `Child.class.getMethod("run")` có thể tìm method public của superclass, còn `Child.class.getDeclaredMethod("run")` thì sao nếu `Child` không override?
2. Vì sao `getDeclaredConstructor()` có thể tìm private constructor nhưng `getConstructor()` không?
3. `getClasses()` và `getDeclaredClasses()` khác nhau ở visibility và inheritance thế nào?
4. Vì sao `Child.class.getAnnotation(Tag.class)` có thể khác `getDeclaredAnnotation(Tag.class)` khi `Tag` mang `@Inherited`?
5. `getDeclaredFields()` có bao gồm field của superclass không? Nếu không, cách duyệt toàn bộ hierarchy là gì?
6. Dùng `getDeclaredMethod("hidden")` thành công có đảm bảo `Method.invoke` từ module khác thành công không?
7. Vì sao nên tự sort kết quả của `getDeclaredMethods()` và kiểm tra `Method.isBridge()` trong công cụ tạo API?
8. Vì sao không thể tự suy luận rằng mọi API `getX` trong Java đều có bản `getDeclaredX`?

**Kết luận:** Đối với method/field/member class, `getX` thường là đường tra cứu **public** và có thể bao gồm member **kế thừa**; `getDeclaredX` là đường tra cứu **khai báo trực tiếp với mọi visibility**. Constructor **không kế thừa**; annotation theo quy tắc `@Inherited` và repeatable riêng. Hãy chọn API theo **loại thành viên + visibility + scope + quyền thực thi**, thay vì chỉ dựa vào tiền tố `Declared`.
