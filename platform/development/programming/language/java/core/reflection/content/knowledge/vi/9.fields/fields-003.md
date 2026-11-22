# Field hiding và nhiều field trùng tên trong phân cấp lớp Java

## 1. Field hiding là gì?

Trong Java, một lớp con có thể **khai báo field cùng tên** với field của lớp cha. Field ở lớp con *hide* (che khuất) field cùng tên của lớp cha khi tra cứu bằng cú pháp Java thông thường. Đây là **field hiding**, không phải ghi đè (*overriding*) như với phương thức instance.

```java
class Parent {
    public int count = 10;
}
class Child extends Parent {
    public String count = "ten";
}
```

Hai field `Parent.count` và `Child.count` cùng tồn tại, dù **cùng tên nhưng khác kiểu**. Cú pháp khai báo này hợp lệ vì chúng nằm trong **hai lớp khác nhau**. Ngược lại, khai báo hai field cùng tên ngay trong *một lớp* là lỗi biên dịch. Field ở lớp con có thể cùng hoặc khác kiểu; việc hiding cũng không phụ thuộc vào field là `static` hay instance.

Với một đối tượng `Child child = new Child()`:

- `child.count` được phân giải theo kiểu tĩnh `Child`, nên tham chiếu tới `Child.count` (giá trị `"ten"`).
- `((Parent) child).count` tham chiếu tới `Parent.count` (giá trị `10`).
- Việc ép kiểu **không tạo đối tượng mới**, mà khiến trình biên dịch chọn field theo kiểu của biểu thức truy cập.
- Trong phương thức của `Child`, có thể dùng `super.count` để truy cập field của `Parent`.

Do đó, một đối tượng con có thể chứa **nhiều vùng lưu trữ field khác nhau có cùng tên** trên chuỗi kế thừa. Field hiding không xóa field cha, không hợp nhất hai field và không tạo cơ chế dispatch động theo runtime class.

## 2. Reflection tra cứu field theo phạm vi nào?

| API | Có tìm field kế thừa? | Có gồm field không `public`? | Khi trùng tên |
| --- | --- | --- | --- |
| `type.getDeclaredField(name)` | Không | Có, nếu field khai báo trực tiếp trong `type` | Trả về đúng field của `type`; nếu lớp đó không khai báo, ném `NoSuchFieldException` |
| `type.getDeclaredFields()` | Không | Có, từ `public` đến `private` | Trả về tất cả field được khai báo trực tiếp, không có thứ tự đảm bảo |
| `type.getField(name)` | Có, chỉ member field `public` | Không | Chọn **một** field theo thuật toán tìm kiếm công khai của `Class` |
| `type.getFields()` | Có, gồm field `public` từ lớp cha và interface | Không | Có thể chứa **nhiều field cùng tên**, kể cả field bị hide; thứ tự không đảm bảo |

**Điểm quan trọng:** `getFields()` trả về một mảng các `Field`, không phải ánh xạ `name -> Field` duy nhất. Không được giả định tên là khóa không trùng hoặc phần tử đầu tiên là field cần dùng.

### Thuật toán `Class.getField("name")`

Với kiểu `C`, theo tài liệu `Class` của Java SE 17:

1. Nếu `C` **trực tiếp khai báo field `public`** với tên đó, trả về field ấy.
2. Nếu chưa tìm được, tra đệ quy từng **superinterface trực tiếp** của `C`, theo thứ tự interface đã khai báo.
3. Nếu vẫn chưa tìm được, tra đệ quy **superclass** của `C`; nếu không còn ứng viên, ném `NoSuchFieldException`.

Vì vậy, khi một lớp con có field `private` tên `marker` còn lớp cha có field `public` cũng tên `marker`, `Child.class.getField("marker")` có thể **trả field `public` của cha**: bước đầu bỏ qua field con không `public` và tiếp tục tìm kiếm. Đừng diễn giải `getField` đơn giản là luôn chọn field gần lớp con nhất bất kể modifier.

Đặc biệt, trong tình huống **interface và superclass đều cung cấp field công khai cùng tên**, việc tra superinterface diễn ra **trước** superclass khi lớp hiện tại không trực tiếp khai báo field `public` phù hợp.

## 3. Ví dụ Java 17+ chạy được: ba field `value` trên một đối tượng

Lưu nguyên chương trình dưới tên **`FieldHidingDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class FieldHidingDemo {
    public static class Root {
        public int value = 10;
        public String marker = "root";
    }

    public static class Mid extends Root {
        public String value = "mid";
        private String marker = "mid-private";
    }

    public static class Leaf extends Mid {
        public long value = 30L;
    }

    public interface First {
        int LIMIT = 100;
    }

    public interface Second {
        int LIMIT = 200;
    }

    public static class Settings implements First, Second {
    }

    public static void main(String[] args) throws Exception {
        Leaf leaf = new Leaf();

        System.out.println("Leaf expression: " + leaf.value);
        System.out.println("Mid expression: " + ((Mid) leaf).value);
        System.out.println("Root expression: " + ((Root) leaf).value);

        Field selected = Leaf.class.getField("value");
        System.out.println("getField(value): "
                + selected.getDeclaringClass().getSimpleName());

        for (Class<?> c = Leaf.class; c != Object.class; c = c.getSuperclass()) {
            Field f = c.getDeclaredField("value");
            System.out.println(c.getSimpleName() + ".value = " + f.get(leaf)
                    + " (" + f.getType().getSimpleName() + ")");
        }

        String[] valueOwners = Arrays.stream(Leaf.class.getFields())
                .filter(f -> f.getName().equals("value"))
                .map(f -> f.getDeclaringClass().getSimpleName())
                .sorted()
                .toArray(String[]::new);
        System.out.println("getFields(value) owners: "
                + String.join(", ", valueOwners));

        Field marker = Leaf.class.getField("marker");
        System.out.println("getField(marker): "
                + marker.getDeclaringClass().getSimpleName()
                + "=" + marker.get(leaf));

        System.out.println("Mid marker private: " + Modifier.isPrivate(
                Mid.class.getDeclaredField("marker").getModifiers()));

        String[] limitOwners = Arrays.stream(Settings.class.getFields())
                .filter(f -> f.getName().equals("LIMIT"))
                .map(f -> f.getDeclaringClass().getSimpleName())
                .sorted()
                .toArray(String[]::new);
        System.out.println("getFields(LIMIT) owners: "
                + String.join(", ", limitOwners));
        System.out.println("getField(LIMIT): "
                + Settings.class.getField("LIMIT")
                        .getDeclaringClass().getSimpleName());
        System.out.println("First.LIMIT via reflection: "
                + First.class.getField("LIMIT").getInt(null));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac FieldHidingDemo.java
java FieldHidingDemo
```

Stdout (đã kiểm chứng thứ tự dòng và giá trị trên Java):

```text
Leaf expression: 30
Mid expression: mid
Root expression: 10
getField(value): Leaf
Leaf.value = 30 (long)
Mid.value = mid (String)
Root.value = 10 (int)
getFields(value) owners: Leaf, Mid, Root
getField(marker): Root=root
Mid marker private: true
getFields(LIMIT) owners: First, Second
getField(LIMIT): First
First.LIMIT via reflection: 100
```

Các kết quả cần phân biệt:

1. **Cú pháp Java phân giải theo kiểu tĩnh:** `leaf.value`, `((Mid) leaf).value` và `((Root) leaf).value` đều truy cập cùng một đối tượng nhưng tới **ba field độc lập**.
2. **`getField("value")` trả đúng một `Field`:** `Leaf.value` là field `public` khai báo trực tiếp trên lớp đang tra cứu nên được chọn trước.
3. **`getDeclaredField("value")` theo từng lớp:** Khi gọi riêng trên `Leaf.class`, `Mid.class`, `Root.class`, ta lấy được chính xác cả ba field. `Field.get(leaf)` sử dụng field của **declaring class** đã chọn, không tự chuyển sang field của `Leaf`.
4. **`getFields()` có nhiều tên `value`:** mảng chứa cả ba field công khai dù bị hide. Code chủ động `sorted()` theo tên lớp để stdout ổn định; API không cam kết thứ tự trả về.
5. **`getField("marker")` vẫn tìm tới `Root`:** `Mid.marker` là `private` và được tìm thấy bằng `Mid.class.getDeclaredField("marker")`; còn `getField` tìm trường `public` kế thừa của `Root`.
6. **Hai interface khai báo `LIMIT`:** `Settings.class.getFields()` chứa `First.LIMIT` lẫn `Second.LIMIT`. `getField("LIMIT")` chọn `First` vì `First` là superinterface đầu tiên trong khai báo `implements First, Second`. Để lấy đúng một hằng, hãy truy cập `First.class.getField("LIMIT")` hoặc `Second.class.getField("LIMIT")`.

Cả `Root`, `Mid` và `Leaf` trong ví dụ đều là lớp `public static` lồng trong `FieldHidingDemo` để có thể chạy độc lập từ một tệp và tránh các chi tiết quyền truy cập lớp không liên quan.

## 4. Tại sao `Field.get()` không tự đọc field của lớp con?

Đối tượng `Field` đại diện cho **một khai báo cụ thể**. Ba thông tin đặc biệt hữu ích là:

- `field.getName()`: tên đơn của field, ví dụ `"value"`.
- `field.getDeclaringClass()`: lớp/interface **thực sự khai báo**, ví dụ `Root.class`.
- `field.getType()`: kiểu khai báo, ví dụ `int.class`, `String.class`, `long.class`.

Ví dụ, `Root.class.getDeclaredField("value").get(leaf)` đọc slot `Root.value` của đối tượng `leaf`, cho kết quả `Integer` mang giá trị `10` (phương thức `Field.get` boxing giá trị primitive trong kết quả `Object`). `Leaf.class.getDeclaredField("value").get(leaf)` đọc slot `Leaf.value`, cho `Long` giá trị `30`.

Đối tượng truyền vào `Field.get(receiver)` cho field instance phải thuộc lớp khai báo field hoặc lớp con phù hợp. Với field `static`, truyền `null` là hợp lệ. `Field` không thực hiện **virtual dispatch** như lời gọi phương thức instance được override.

Do đó, để định danh một field trong dữ liệu Reflection, **không chỉ lưu `name`**. Hãy giữ ít nhất `declaringClass` và `name`; kiểm tra thêm `type` và `modifiers` khi xử lý schema hoặc ánh xạ dữ liệu.

## 5. Cách thu thập *tất cả* field trùng tên trong chuỗi kế thừa

Khi muốn lấy field ở **mọi cấp lớp**, kể cả `private` và `protected`, duyệt lần lượt `getSuperclass()` và gọi `getDeclaredField(name)` trên từng cấp:

```java
// Đoạn hàm dùng trong một lớp Java; không phải chương trình độc lập.
static java.util.List<java.lang.reflect.Field> findAllInClassHierarchy(
        Class<?> start, String name) {
    java.util.List<java.lang.reflect.Field> result =
            new java.util.ArrayList<>();

    for (Class<?> c = start; c != null; c = c.getSuperclass()) {
        try {
            result.add(c.getDeclaredField(name));
        } catch (NoSuchFieldException ignored) {
            // Cấp lớp này không khai báo field; vẫn duyệt tiếp superclass.
        }
    }
    return result; // Từ lớp đang xét tới các superclass.
}
```

Ví dụ dùng `findAllInClassHierarchy(Leaf.class, "value")` sẽ cho ba `Field` khai báo ở `Leaf`, `Mid`, `Root`, theo thứ tự đó. Hàm này **chỉ duyệt class và superclass**, không đệ quy các interface; nếu cần tất cả hằng/field từ interface, phải khảo sát riêng `getInterfaces()` (bao gồm cả interface cha nếu cần) hoặc chọn `getFields()` khi chỉ quan tâm `public`.

Một số lưu ý triển khai:

- Không dùng `getDeclaredFields()` của một lớp con rồi kỳ vọng có field của lớp cha.
- Nếu cần hiển thị danh sách, tự sắp xếp theo **cấp lớp** hoặc `declaringClass + name` vì thứ tự trong mảng `getFields()`/`getDeclaredFields()` không được đảm bảo.
- Không dùng `Map<String, Field>` nếu cần giữ mọi field trùng tên: field sau có thể ghi đè field trước. Dùng `List<Field>` hoặc một khóa có `declaringClass`.
- Khi mapping serialization/ORM/custom injection, phải đặt quy tắc rõ ràng: chọn field khai báo gần nhất, chọn field ở lớp cụ thể, hay báo lỗi nếu nhiều field cùng tên. Không coi việc mảng tình cờ trả về field nào trước là hợp đồng API.
- Với field không công khai, **tra cứu metadata** khác với **quyền đọc/ghi**: `getDeclaredField` có thể thành công nhưng `Field.get`/`set` vẫn phải tuân thủ access check; `trySetAccessible()` cũng chịu giới hạn module `opens`.

## 6. Field hiding khác method overriding

| Tiêu chí | Field cùng tên trong cha/con | Method instance được override |
| --- | --- | --- |
| Quan hệ | Hiding giữa các khai báo field | Overriding nếu đáp ứng quy tắc chữ ký |
| Cách chọn qua cú pháp Java | Theo kiểu tĩnh của biểu thức chứa field | Dispatch động theo lớp runtime của đối tượng |
| Dùng cast về cha | Chọn field khai báo/tồn tại theo kiểu cha | Vẫn gọi override của con nếu method thực sự được override |
| Reflection | `Field` trỏ đến một khai báo; `Field.get` đọc khai báo đó | `Method.invoke` của method instance có thể thực thi override tương ứng |
| Khác kiểu / `static` | Field con có thể khác kiểu, và hiding không phân biệt static/instance | Method có điều kiện override và quy tắc static hiding riêng |

```java
// Mảnh mã minh họa; đặt trong một chương trình Java thích hợp.
class A {
    int number = 1;
    String describe() { return "A"; }
}
class B extends A {
    int number = 2;
    @Override String describe() { return "B"; }
}
// A ref = new B();
// ref.number     -> 1 (field A)
// ref.describe() -> "B" (method override ở B)
```

Không suy luận từ method dispatch rằng một `Field` được lấy ở cha sẽ tự tham chiếu tới field cùng tên trong con.

## 7. Các trường hợp dễ nhầm

### 7.1. Field `private` ở lớp con và field `public` ở lớp cha

Lớp con có thể khai báo field `private` cùng tên với field `public` ở lớp cha. `getDeclaredField` trên lớp con tìm field `private`; `getField` trên lớp con có thể đi tiếp đến field `public` ở cha như ví dụ `marker`. Việc `getField` tìm được một field công khai **không có nghĩa** lớp con không có field khác cùng tên.

### 7.2. Hai interface có hằng cùng tên

Các field khai báo trong interface mặc định là `public static final`. Nếu lớp implement `First` và `Second` cùng có `LIMIT`, biểu thức không đủ điều kiện như `Settings.LIMIT` có thể **mơ hồ ở bước biên dịch**. Reflection `Settings.class.getField("LIMIT")` lại được định nghĩa theo thuật toán tra cứu của `Class` và trong ví dụ chọn `First`. Đây là hai quy tắc khác nhau; tốt nhất định danh rõ `First.LIMIT` hoặc `Second.LIMIT`.

### 7.3. Field cùng tên nhưng khác kiểu

`int value`, `String value`, `long value` ở ba cấp lớp là ba khai báo độc lập. Trong phạm vi **một lớp**, Java không cho overload field theo kiểu như overload method. Khi đọc qua Reflection, dùng `getType()` trước khi ép kiểu giá trị trả về từ `Field.get()`.

### 7.4. Field static và instance

Hiding của field không đòi hỏi cả hai field đều là `static` hoặc đều là instance. Một lớp con có thể khai báo field trùng tên với field `static` của cha. Truy cập field `static` qua Reflection bằng `get(null)`; với field instance, truyền đối tượng phù hợp. Tên giống nhau không biến field thành polymorphic.

### 7.5. Có metadata nhưng không đọc được giá trị

`getDeclaredField` có thể tìm được field `private` nhưng `get(receiver)` không truy cập được từ caller ngoài phạm vi hợp lệ và ném `IllegalAccessException`. Trong named modules, deep reflection còn bị giới hạn bởi `opens`; `setAccessible(true)` có thể ném `InaccessibleObjectException`, còn `trySetAccessible()` có thể trả `false`. Không dùng thao tác mở quyền như điều kiện mặc định khi chỉ cần liệt kê metadata.

## 8. Các lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Leaf.class.getDeclaredField("marker")` ném `NoSuchFieldException` | `marker` chỉ được khai báo tại `Mid` và `Root`; `getDeclaredField` không tìm lớp cha | Duyệt `getSuperclass()` và gọi `getDeclaredField` trên từng cấp |
| `getFields()` xuất hiện nhiều `value` | Các field `public` bị hide vẫn tồn tại | Dùng `getDeclaringClass()` để phân biệt |
| `getField("marker")` trả `Root.marker` thay vì `Mid.marker` | `Mid.marker` là `private`; `getField` chỉ lấy field `public` | Dùng `Mid.class.getDeclaredField("marker")` khi cần đúng field đã khai báo |
| Đọc `Root.value` từ đối tượng `Leaf` nhưng nhận `10` thay vì `30` | `Field` gắn với khai báo của `Root`, không dispatch động | Chọn `Leaf.class.getDeclaredField("value")` nếu cần field con |
| Mất một field khi đưa danh sách vào `Map<String, Field>` | Khóa trùng nhau và bị ghi đè | Dùng danh sách hoặc khóa gồm declaring class |
| `getField("LIMIT")` chọn interface không mong muốn | Thuật toán tra interface trực tiếp theo thứ tự khai báo | Dùng `First.class.getField("LIMIT")` / `Second.class.getField("LIMIT")` |
| Bị `IllegalAccessException` khi `Field.get` | Có metadata nhưng caller chưa được phép sử dụng | Kiểm tra modifier, receiver, module và quyền truy cập |
| Dựa vào thứ tự `getFields()` | API không bảo đảm sắp xếp | Sắp xếp hoặc xác định lớp khai báo tường minh |

## 9. Tự kiểm tra

1. `class Base { public int x; }` và `class Derived extends Base { public String x; }`: `Derived.class.getFields()` có thể chứa mấy field tên `x`? **Hai**: `Derived.x` và `Base.x`.
2. `Derived.class.getDeclaredField("x")` trả field nào? **`Derived.x`**, vì API chỉ xét field khai báo trực tiếp.
3. `Base.class.getDeclaredField("x").get(derived)` đọc field nào? **`Base.x`** trên cùng đối tượng `derived`.
4. Nếu `Derived` không khai báo `public x`, còn `Base` khai báo `public x`, `Derived.class.getField("x")` có thể trả field nào? **`Base.x`**, sau khi duyệt các thành phần theo thuật toán `getField`.
5. Vì sao `Map<String, Field>` không đủ biểu diễn field trong phân cấp? Vì nhiều khai báo khác nhau chia sẻ cùng tên và có thể bị ghi đè trong map.

**Ghi nhớ:** Field hiding thay đổi cách **tên field được phân giải**, không loại bỏ field của cha. Khi Reflection gặp nhiều field cùng tên, hãy xem `getDeclaringClass()` và dùng đúng API cho phạm vi cần tìm. `Field` định danh một khai báo cụ thể, vì thế `Field.get()` đọc chính khai báo đó.

Nguồn tra cứu: [Java Language Specification §8.3 (Field Declarations)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3), [Java SE 17 Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Dev.java — Reading and Writing Fields](https://dev.java/learn/api/reflection-method-handles/reflection/fields/).