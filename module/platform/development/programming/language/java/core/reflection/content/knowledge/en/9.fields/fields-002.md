# getFields() khác getDeclaredFields() khi có kế thừa — Java Reflection

Khi đọc cấu trúc một lớp bằng Reflection, hai lời gọi `Class.getFields()` và `Class.getDeclaredFields()` đều trả về mảng `Field[]`, nhưng chúng trả lời **hai câu hỏi khác nhau**:

- **`getFields()`:** “Những trường `public` nào nằm trong phạm vi tra cứu thành viên công khai của lớp/interface này, bao gồm trường ở superclass và superinterface?”
- **`getDeclaredFields()`:** “Chính lớp/interface đang xét **khai báo trực tiếp** những trường nào, bất kể `public`, `protected`, package-private hay `private`?”

Vì vậy, `getDeclaredFields()` **không** phải phiên bản “đầy đủ hơn” của `getFields()` về kế thừa. Nó lấy được các trường không công khai *trong chính lớp*, nhưng **không tự duyệt trường của lớp cha**. Muốn phân tích toàn bộ chuỗi kế thừa, chương trình thường phải kết hợp `getDeclaredFields()` với `getSuperclass()`.

## 1. Bảng so sánh phạm vi tra cứu

| Tình huống | `SomeClass.class.getFields()` | `SomeClass.class.getDeclaredFields()` |
| --- | --- | --- |
| Trường `public` khai báo ngay ở `SomeClass` | Có | Có |
| Trường `private`, `protected`, package-private khai báo ngay tại `SomeClass` | Không | Có |
| Trường `public` ở superclass | Có | Không |
| Trường `private`, `protected`, package-private ở superclass | Không | Không |
| Hằng `public static final` khai báo ở interface mà lớp triển khai/kế thừa | Có trong phạm vi interface liên quan | Không nếu interface là nơi khai báo |
| Trường `static` | Có nếu `public` thuộc phạm vi tìm | Có nếu khai báo trực tiếp, bất kể mức truy cập |
| Trường tổng hợp (synthetic) do compiler sinh ra | Có thể xuất hiện nếu thỏa điều kiện `public`/phạm vi | Có thể xuất hiện nếu được khai báo trong bytecode của chính lớp |
| Thứ tự các phần tử trong mảng | Không được bảo đảm | Không được bảo đảm |

**Điểm quan trọng:** “Declared” là **nơi khai báo**, không có nghĩa là “chỉ các trường được phép truy cập”, và “Fields” không có nghĩa là “mọi trường”. Nếu lớp con không có trường `public` nào, `getFields()` vẫn có thể trả trường `public` từ lớp cha hoặc interface.

Tài liệu chuẩn Java 17:
- `Class.getFields()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getFields()
- `Class.getDeclaredFields()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredFields()

## 2. Cơ chế khi lớp con kế thừa lớp cha

Xét quan hệ:

```text
                 interface Labeled
                 + CATEGORY: String (public static final)
                         ^
                         | implements
class Base              |
+ name: String (public) |
+ version: int (public static)
+ level: int (protected)
+ token: long (private)
       ^                 |
       | extends         |
       +------ class Child
               + name: String (public, che Base.name)
               + active: boolean (public)
               + note: String (private)
```

Với `Child.class`:

- `getFields()` tìm các trường `public` của `Child`, những trường `public` từ `Base` và trường công khai của `Labeled`. Nó không lấy `Base.level`, `Base.token` hay `Child.note`.
- `getDeclaredFields()` chỉ lấy ba trường do `Child` khai báo: `name`, `active`, `note`. Nó không lấy `Base.name`, `Base.version` hoặc `Labeled.CATEGORY`.
- `Base.class.getDeclaredFields()` trả bốn trường riêng của `Base` ở mọi mức truy cập; nó không bị ảnh hưởng bởi việc `Child` có che tên trường hay không.

Ở đây có **field hiding**: `Child` cũng khai báo `name` nên tên trường đó che `Base.name` khi tham chiếu bằng cú pháp thông thường. Trong Reflection, mỗi đối tượng `Field` vẫn gắn với **lớp khai báo thật** (qua `getDeclaringClass()`). Do đó, một danh sách `getFields()` có thể chứa **nhiều `Field` trùng tên** nếu chúng thuộc các lớp khác nhau.

## 3. Ví dụ Java 17+ chạy độc lập và kết quả chính xác

Lưu đoạn sau vào tệp `FieldInheritanceDemo.java`. Các class phụ trợ là kiểu top-level cùng package, giúp ví dụ minh họa quan hệ kế thừa, không phụ thuộc vào các field riêng của enclosing class.

```java
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.stream.Collectors;

public class FieldInheritanceDemo {
    private static String names(Field[] fields) {
        return Arrays.stream(fields)
                .map(f -> f.getDeclaringClass().getSimpleName()
                        + "." + f.getName())
                .sorted()
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        System.out.println("getFields=" + names(type.getFields()));
        System.out.println(
                "getDeclaredFields=" + names(type.getDeclaredFields()));
        System.out.println(
                "baseDeclared=" + names(Base.class.getDeclaredFields()));

        Field selectedName = type.getField("name");
        System.out.println("selectedName.owner="
                + selectedName.getDeclaringClass().getSimpleName());

        Field parentName = Base.class.getDeclaredField("name");
        Child child = new Child();
        System.out.println("parentName.value=" + parentName.get(child));
        System.out.println("childName.value=" + selectedName.get(child));

        long publicNameCount = Arrays.stream(type.getFields())
                .filter(f -> f.getName().equals("name"))
                .count();
        System.out.println("publicNameCount=" + publicNameCount);

        Field category = type.getField("CATEGORY");
        System.out.println("interfaceField.owner="
                + category.getDeclaringClass().getSimpleName());
        System.out.println("interfaceField.value=" + category.get(null));

        try {
            type.getDeclaredField("level");
        } catch (NoSuchFieldException e) {
            System.out.println("childDeclaredLevel=NoSuchFieldException");
        }

        System.out.println("parentProtected.exists="
                + Arrays.stream(type.getFields())
                        .anyMatch(f -> f.getName().equals("level")));
    }
}

interface Labeled {
    String CATEGORY = "tagged";
}

class Base {
    public String name = "base";
    public static int version = 1;
    protected int level = 2;
    private long token = 3;
}

class Child extends Base implements Labeled {
    public String name = "child";
    public boolean active = true;
    private String note = "private";
}
```

Lệnh biên dịch/chạy:

```bash
javac FieldInheritanceDemo.java
java FieldInheritanceDemo
```

Đầu ra (đã chủ động sắp xếp kết quả `Field[]` bằng `sorted()` để không dựa vào thứ tự Reflection trả về):

```text
getFields=Base.name, Base.version, Child.active, Child.name, Labeled.CATEGORY
getDeclaredFields=Child.active, Child.name, Child.note
baseDeclared=Base.level, Base.name, Base.token, Base.version
selectedName.owner=Child
parentName.value=base
childName.value=child
publicNameCount=2
interfaceField.owner=Labeled
interfaceField.value=tagged
childDeclaredLevel=NoSuchFieldException
parentProtected.exists=false
```

Giải thích những điểm dễ sai:

1. `getFields()` bao gồm hai trường `public` cùng tên `name`: `Base.name` và `Child.name`. Vì vậy, **không nên xây map chỉ với key là tên** nếu cần bảo toàn mọi trường trong cây kế thừa.
2. `getField("name")` trả trường `Child.name` do lớp đang xét tự khai báo `public`. Trong ví dụ này, `getDeclaringClass()` là `Child.class`.
3. Vẫn có thể lấy riêng `Base.name` bằng `Base.class.getDeclaredField("name")`. Khi đọc nó từ một đối tượng `Child`, giá trị là `"base"`; trường của `Child` có giá trị riêng `"child"`. Field hiding **không ghi đè cùng một ô nhớ** theo cơ chế đa hình của phương thức.
4. `Labeled.CATEGORY` là trường interface. Theo Java, trường khai báo trong interface mặc định là `public static final`, và `getField("CATEGORY")` có thể tìm thấy nó từ `Child.class`. Vì là `static`, lời gọi `Field.get(null)` đọc giá trị trường.
5. `Base.level` là `protected` và `Base.token` là `private`, nên không xuất hiện trong `Child.class.getFields()`; cả hai cũng không thuộc `Child.class.getDeclaredFields()`, vì được khai báo tại `Base`.

## 4. getField(name) và getDeclaredField(name) liên hệ thế nào?

Hai API dạng số ít có phạm vi tương tự:

| API | Điều kiện để tìm thấy | Không tìm thấy |
| --- | --- | --- |
| `getField(String name)` | Trường `public` có tên khớp, tìm theo quy tắc class/superinterface/superclass | `NoSuchFieldException` |
| `getDeclaredField(String name)` | Trường **khai báo trực tiếp** ở `Class` hiện tại, bất kỳ access modifier | `NoSuchFieldException` |

Ví dụ:

```java
Child.class.getField("active");           // Child.active, public
Child.class.getField("version");          // Base.version, public
Child.class.getField("CATEGORY");         // Labeled.CATEGORY, public
Child.class.getDeclaredField("note");     // Child.note, private
Base.class.getDeclaredField("level");     // Base.level, protected
Base.class.getDeclaredField("token");     // Base.token, private

// Hai lời gọi dưới đây ném NoSuchFieldException:
Child.class.getDeclaredField("version");  // Khai báo trong Base
Child.class.getField("level");            // Không phải public
```

Đây là đoạn **minh họa đặt trong ngữ cảnh có các class đã khai báo phía trên**, không phải chương trình chạy độc lập; các phương thức số ít cũng có thể yêu cầu xử lý `NoSuchFieldException`.

### Khi nhiều trường public trùng tên

`getField(name)` **không** trả toàn bộ các field trùng tên. Thuật toán tra cứu ưu tiên trường `public` khai báo ngay trong class/interface đang xét; nếu không có, nó tìm trong superinterface theo thứ tự khai báo rồi mới xét superclass. Kết quả là **một `Field`** theo thuật toán của JDK, không phải danh sách đầy đủ. Vì thế:

- Cần tra cứu một member public theo cách Java định nghĩa → dùng `getField("name")`.
- Cần xem **mọi** public field trong cây kế thừa, kể cả trường bị che tên → duyệt `getFields()` và xét `getDeclaringClass()`.
- Cần field cụ thể được khai báo ở superclass → gọi `SuperClass.class.getDeclaredField("name")` (hoặc duyệt hierarchy), không phụ thuộc vào việc lớp con cũng có trường cùng tên.

Đừng lấy phần tử đầu tiên từ mảng `getFields()` rồi cho rằng đó là trường lớp con. **Thứ tự các phần tử không được bảo đảm**; dùng `getField` với thuật toán tra cứu rõ ràng hoặc tự chọn bằng `getDeclaringClass()`.

## 5. Cách thu thập tất cả trường khai báo trong chuỗi superclass

Không có một lời gọi `getDeclaredFields()` duy nhất tự tìm tất cả trường non-public ở mọi lớp cha. Với trường hợp cần inspect toàn bộ state (ví dụ serializer hoặc công cụ debug), có thể duyệt `getSuperclass()`:

```java
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

public class HierarchyFieldsExample {
    static List<Field> declaredFieldsInClassHierarchy(Class<?> type) {
        List<Field> result = new ArrayList<>();
        for (Class<?> current = type;
             current != null;
             current = current.getSuperclass()) {
            for (Field field : current.getDeclaredFields()) {
                result.add(field);
            }
        }
        return result;
    }
}
```

Đây là **mã helper minh họa**, không có `main` để tự chạy. Với `Child.class` ở ví dụ trước, logic trên thu thập trường do `Child` khai báo rồi tới `Base` và `Object`; `Object` không có instance field khai báo cho ví dụ. Cách này giữ các trường trùng tên vì mỗi `Field` mang declaring class riêng.

**Giới hạn cần nhớ:**

- `getSuperclass()` chỉ duyệt **superclass chain**, không duyệt các superinterface. Nếu cần thêm trường interface, phải duyệt `getInterfaces()` và các superinterface một cách riêng biệt, đồng thời chống lặp theo identity khi đi qua đồ thị interface.
- Kết quả có thể gồm cả `static`, `final`, compiler-generated/synthetic field. Lọc theo nhu cầu thay vì mặc định mọi field đều là state instance.
- Thứ tự từng mảng `getDeclaredFields()` không được bảo đảm. Nếu cần kết quả tái lập được, hãy sắp xếp bằng khóa rõ ràng, thường gồm declaring class và tên; khi cần phân biệt chính xác hơn, thêm descriptor/type.
- `getDeclaredFields()` chỉ trả metadata. Việc đọc/ghi giá trị ở field non-public còn chịu quy tắc truy cập, giới hạn module và `AccessibleObject`.

### Ví dụ lọc trường instance hoặc synthetic

```java
for (Field field : declaredFieldsInClassHierarchy(Child.class)) {
    boolean isInstanceField = !java.lang.reflect.Modifier.isStatic(
            field.getModifiers());
    if (isInstanceField && !field.isSynthetic()) {
        // Xử lý metadata: tên, kiểu, lớp khai báo...
    }
}
```

Đây là đoạn minh họa được đặt cạnh helper `declaredFieldsInClassHierarchy`, không phải chương trình chạy độc lập. Bộ lọc trên không tự quyết định một trường có phù hợp serialize hay không; trong thực tế còn phải xem `transient`, annotation, visibility, quy tắc nghiệp vụ và trạng thái truy cập.

## 6. Trường interface, field hiding và trường được kế thừa

### Interface fields có thể xuất hiện dù lớp con không khai báo

Mọi field khai báo trong interface là `public static final`. Nếu `Child implements Labeled`, `Child.class.getFields()` bao gồm `Labeled.CATEGORY` theo phạm vi thành viên công khai. Tuy nhiên, `Child.class.getDeclaredFields()` **không** bao gồm field đó. `Labeled.class.getDeclaredFields()` mới trả field này với `getDeclaringClass() == Labeled.class`.

Nếu nhiều interface khai báo trường cùng tên, tra cứu `getField(name)` tuân theo thứ tự superinterface của thuật toán API; đừng lấy đó làm phép phát hiện “không có xung đột” của toàn bộ cây interface. Khi cần kiểm toán, duyệt `getFields()` cùng declaring class.

### Field hiding khác method overriding

Trường trong Java **không override** theo dispatch động như instance method. Nếu `Base` và `Child` cùng khai báo `public String name`, đó là **hai trường riêng**. `Field.get(child)` đọc trường mà chính đối tượng `Field` biểu diễn, dù receiver thực tế là instance của `Child`. Do đó một `Field` trỏ tới `Base.name` đọc giá trị `Base.name`.

Để phân biệt các field trùng tên, dùng `field.getDeclaringClass()`, `field.getType()`, `field.getModifiers()`. Tên đơn thuần không đủ định danh field khi có hiding.

### “Inherited” và phạm vi Reflection

Trong Java Language Specification, một field có bị che hay không được kế thừa như thế nào là khái niệm ngữ nghĩa ngôn ngữ. `Class.getFields()` mô tả phạm vi **public field của class, superclass và superinterface** và có thể cho thấy cả field bị che tên. Vì thế đừng suy diễn rằng “chỉ có thể gọi được `obj.name` một cách đơn giản” đồng nghĩa với “Reflection chỉ tìm thấy một Field tên `name`”.

## 7. Truy cập giá trị và giới hạn Java module

Tìm thấy `Field` không có nghĩa là đọc hoặc sửa giá trị được. Chẳng hạn `Base.class.getDeclaredField("token")` trả metadata của trường `private`, nhưng `field.get(object)` vẫn kiểm tra quyền truy cập và có thể ném `IllegalAccessException`. Khi cần deep reflection, `trySetAccessible()` hoặc `setAccessible(true)` chỉ có thể bật cơ chế bỏ qua kiểm tra nếu quy tắc truy cập và module cho phép. Package của named module không mở có thể chặn thao tác với `InaccessibleObjectException` hoặc làm `trySetAccessible()` trả `false`.

Đối với field `final`, đừng mặc định bật accessible flag là ghi được hoặc việc ghi luôn an toàn. Một số final field như `static final`, field final của record hoặc hidden class không thể ghi qua Reflection; việc sửa các final field khác cũng có giới hạn về tính nhất quán và tối ưu hóa.

Các công cụ cần duyệt field nên tách rõ hai giai đoạn: **thu thập metadata** bằng `getFields`/`getDeclaredFields` trước, sau đó **xác định quyền truy cập thực tế** nếu cần đọc/ghi.

## 8. Lỗi phổ biến và cách lựa chọn API

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `getDeclaredFields()` lấy mọi field kể cả trong superclass | Chỉ lấy field do chính class/interface khai báo |
| `getFields()` lấy mọi field trong cây kế thừa | Chỉ lấy field `public` trong phạm vi class/superclass/superinterface |
| `getFields()` không trả field bị che tên | Có thể trả nhiều `Field` cùng tên nhưng khác declaring class |
| `getFields()[0]` luôn là field của lớp con | Thứ tự các phần tử không được bảo đảm |
| `getField("name")` và `getDeclaredField("name")` tương đương | Một API tra cứu public member, một API tra cứu khai báo trực tiếp bất kể visibility |
| `getDeclaredField` của lớp con tìm được private field lớp cha | Phải lấy `Class` lớp cha hoặc duyệt superclass |
| Có `Field` tức là có quyền `get`/`set` | Metadata và quyền truy cập là hai bước khác nhau |
| Mọi trường interface được sao chép thành field khai báo của class triển khai | Interface field giữ declaring class là interface |

**Quy tắc chọn nhanh:** cần tập field **public của lớp cùng kế thừa/interface** thì dùng `getFields()`; cần tập field **khai báo ngay trong một class bất kể mức truy cập** thì dùng `getDeclaredFields()`; cần cả field `private` hoặc `protected` ở các superclass thì **tự duyệt hierarchy và gọi `getDeclaredFields()` trên từng lớp**. Khi có tên trùng, luôn gắn field với `getDeclaringClass()` để tránh nhầm.