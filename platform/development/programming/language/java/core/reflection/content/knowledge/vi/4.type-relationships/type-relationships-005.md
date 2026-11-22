# Phân biệt quan hệ khai báo với kiểu thực tế của đối tượng trong Java Reflection

## 1. Vì sao cần phân biệt hai loại thông tin kiểu?

Trong Java, một biểu thức tham chiếu có **kiểu khai báo** (declared/static type) do mã nguồn xác định tại thời điểm biên dịch, còn đối tượng mà tham chiếu trỏ tới có **lớp thực tế khi chạy** (runtime class). Hai thông tin này có thể khác nhau nhưng phải tương thích về phép gán.

```java
Animal animal = new Dog();
```

Giả sử `Dog extends Animal`:

- `Animal` là kiểu khai báo của biến cục bộ `animal`. Trình biên dịch dùng kiểu này để kiểm tra lời gọi phương thức, truy cập thành viên và lựa chọn overload.
- `Dog` là lớp thực tế của đối tượng được tạo bởi `new Dog()`. `animal.getClass()` trả về đối tượng `Class` đại diện cho `Dog`.
- `Dog` phải là subtype phù hợp của `Animal` để phép gán hợp lệ. **Kiểu khai báo không tự đổi thành `Dog`** sau khi gán.
- Đối tượng chứa thông tin lớp thực tế của chính nó; nó không chứa thông tin rằng một biến cụ thể được khai báo là `Animal`. Nhiều biến có kiểu khai báo khác nhau có thể cùng tham chiếu đến một đối tượng.

**Bẫy phổ biến:** `animal.getClass()` **không** trả về `Animal.class` trong ví dụ trên. Nó trả về `Dog.class`. Reflection chuẩn trên `Object` không cung cấp một API để lấy kiểu khai báo của biến cục bộ `animal` từ tham chiếu đó.

## 2. Đọc đúng dữ liệu bằng Reflection

| Cần trả lời câu hỏi gì? | API / nguồn thông tin | Ý nghĩa |
| --- | --- | --- |
| Đối tượng này thực sự thuộc lớp nào? | `obj.getClass()` | Lớp khi chạy của đối tượng khác `null`. |
| Trường được **khai báo** nhận loại giá trị nào? | `Field.getType()` | `Class<?>` đại diện cho kiểu khai báo của trường; với generic là kiểu đã bị erasure. |
| Trường hiện đang chứa đối tượng lớp nào? | `Field.get(instance)` rồi `value.getClass()` | Phải đọc giá trị thực tế và kiểm tra `null`. |
| Phương thức khai báo kiểu trả về nào? | `Method.getReturnType()` | Kiểu trả về trong khai báo phương thức; không phải lớp của giá trị mà một lần gọi trả về. |
| Phương thức khai báo tham số loại nào? | `Method.getParameterTypes()` | Các kiểu tham số khai báo. Đối số thực tế có thể là instance của subtype. |
| Thành viên được khai báo ở lớp nào? | `Field.getDeclaringClass()`, `Method.getDeclaringClass()` | **Lớp sở hữu khai báo thành viên**, không phải kiểu của trường, đối số hay kết quả. |
| Một lớp khai báo extends/implements gì? | `Class.getSuperclass()`, `Class.getInterfaces()` | Quan hệ thừa kế được khai báo trên lớp đang xét. |
| Kiểu có thể nhận giá trị thuộc kiểu khác không? | `Target.class.isAssignableFrom(Source.class)` | Kiểm tra tương thích kiểu theo hướng `Source` → `Target`. |
| Đối tượng có là instance của một kiểu không? | `Target.class.isInstance(obj)` | Tương đương kiểm tra kiểu động như `obj instanceof Target` trong trường hợp kiểu tham chiếu. |

Tên `getDeclaredField()`, `getDeclaredFields()` và `getDeclaredMethod()` có nghĩa là chỉ tìm thành viên **được khai báo trực tiếp trong lớp được hỏi**, thay vì truy tìm thành viên kế thừa. Chữ “Declared” ở đây **không** có nghĩa là trả về kiểu khai báo của *biến tham chiếu* đến đối tượng.

Ví dụ, `Box.class.getDeclaredField("pet").getType()` lấy kiểu trường `pet` trong `Box`, còn `box.pet.getClass()` lấy lớp của đối tượng hiện đang nằm trong trường ấy.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu nguyên văn chương trình sau vào tệp `DeclaredVsRuntime.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.util.List;

public class DeclaredVsRuntime {
    public static class Animal {
        public String speak() {
            return "Animal";
        }
    }

    public static class Dog extends Animal {
        @Override
        public String speak() {
            return "Woof";
        }

        public void fetch() {}
    }

    public static class Box {
        public Animal pet = new Dog();
        public List<Animal> friends = List.of(new Dog());
    }

    public static void inspect(Animal input) {
        System.out.println("parameter actual = "
                + input.getClass().getSimpleName());
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Animal animal = new Dog();
        System.out.println("reference runtime = "
                + animal.getClass().getSimpleName());

        Box box = new Box();
        Field petField = Box.class.getDeclaredField("pet");
        Object petValue = petField.get(box);
        System.out.println("field declared = "
                + petField.getType().getSimpleName());
        System.out.println("field actual = "
                + petValue.getClass().getSimpleName());
        System.out.println("field owner = "
                + petField.getDeclaringClass().getSimpleName());

        Method speak = Animal.class.getDeclaredMethod("speak");
        System.out.println("method owner = "
                + speak.getDeclaringClass().getSimpleName());
        System.out.println("return declared = "
                + speak.getReturnType().getSimpleName());
        System.out.println("invoke result = " + speak.invoke(animal));

        Method inspect = DeclaredVsRuntime.class
                .getDeclaredMethod("inspect", Animal.class);
        System.out.println("parameter declared = "
                + inspect.getParameterTypes()[0].getSimpleName());
        inspect(animal);

        System.out.println("Animal accepts Dog = "
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog accepts Animal = "
                + Dog.class.isAssignableFrom(Animal.class));
        System.out.println("is Animal instance = "
                + Animal.class.isInstance(animal));

        Field friendsField = Box.class.getDeclaredField("friends");
        ParameterizedType genericType =
                (ParameterizedType) friendsField.getGenericType();
        System.out.println("generic argument is Animal = "
                + (genericType.getActualTypeArguments()[0] == Animal.class));
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac DeclaredVsRuntime.java
java DeclaredVsRuntime
```

Kết quả stdout:

```text
reference runtime = Dog
field declared = Animal
field actual = Dog
field owner = Box
method owner = Animal
return declared = String
invoke result = Woof
parameter declared = Animal
parameter actual = Dog
Animal accepts Dog = true
Dog accepts Animal = false
is Animal instance = true
generic argument is Animal = true
```

Giải thích các điểm mấu chốt:

1. `Animal animal = new Dog()` hợp lệ vì `Dog` kế thừa `Animal`. `getClass()` đọc lớp của đối tượng nên hiện `Dog`.
2. `petField.getType()` cố định ở `Animal.class` vì đó là kiểu khai báo trong `Box`; `petField.get(box)` hiện trả về một đối tượng `Dog`. Nếu mã khác gán một subtype khác vào `box.pet`, kiểu khai báo trường vẫn là `Animal`.
3. `petField.getDeclaringClass()` trả về `Box.class`: `Box` là nơi khai báo trường, **không phải** kiểu của giá trị trường.
4. `Animal.class.getDeclaredMethod("speak")` cho `Method` có chủ khai báo `Animal` và kiểu trả về khai báo `String`. Khi `speak.invoke(animal)` chạy, Java vẫn áp dụng **dynamic dispatch** cho instance method được override, nên thực thi `Dog.speak()` và cho `Woof`. `Method.invoke` không làm mất tính đa hình.
5. `inspect` khai báo tham số `Animal`; lần gọi này truyền đối tượng `Dog`. `getParameterTypes()` chỉ biết kiểu khai báo của tham số, trong khi `input.getClass()` thấy đối tượng thực tế.
6. `Animal.class.isAssignableFrom(Dog.class)` trả `true` theo hướng “biến `Animal` có thể nhận đối tượng `Dog`”. Đảo hai vế không tương đương.
7. `friendsField.getGenericType()` đọc thông tin `List<Animal>` được giữ trong metadata khai báo trường; việc ấy không chứng minh rằng mọi phần tử được thêm lúc chạy đều mang lớp `Animal` chính xác (phần tử có thể là `Dog`).

## 4. Kiểu khai báo quyết định gì, kiểu thực tế quyết định gì?

### Truy cập thành viên và overload được xét tại thời điểm biên dịch

```java
Animal a = new Dog();
a.speak();   // Hợp lệ: speak được khai báo trong Animal.
// a.fetch(); // Lỗi biên dịch: Animal không khai báo fetch.
```

Dù đối tượng là `Dog`, tên phương thức `fetch` không xuất hiện trên kiểu tĩnh `Animal`. Muốn gọi chức năng riêng của subtype, kiểm tra kiểu động trước rồi dùng biến đã thu hẹp kiểu:

```java
if (a instanceof Dog dog) {
    dog.fetch();
}
```

Overloading (`choose(Animal)` và `choose(Dog)`) được chọn chủ yếu bằng kiểu của biểu thức truyền vào tại thời điểm biên dịch; overriding (`Animal.speak()` được `Dog` ghi đè) được chọn động theo lớp đối tượng khi chạy. Vì vậy, không thể dùng `obj.getClass()` để suy ra Java đã chọn overload nào từ cú pháp lời gọi ban đầu.

### Gọi phương thức override tuân theo kiểu thực tế

Với `Animal a = new Dog()`, biểu thức `a.speak()` sử dụng khai báo nhìn thấy qua `Animal` nhưng hành vi của `Dog`. Trong Reflection, nếu có `Method` của instance method trên lớp cha, `method.invoke(a)` cũng dispatch tới implementation override phù hợp (trừ các trường hợp có quy tắc riêng như `static`, `private`; `Method.invoke` không thể làm override những phương thức không được override).

### Một trường có kiểu khai báo ổn định nhưng giá trị thay đổi

`Field.getType()` chỉ phản ánh signature của trường, không phụ thuộc instance cụ thể. Một trường `Animal pet` có thể lần lượt chứa `new Dog()`, subtype `Cat`, hoặc `null`. Dùng `Field.get(obj)` để lấy **giá trị tại thời điểm đọc**; nếu không phải `null` mới gọi `getClass()` được. Với trường `static`, `Field.get(null)` là cách đọc hợp lệ nếu quyền truy cập cho phép; `null` trong trường hợp này là tham số `get`, không phải lớp động của giá trị.

## 5. Kiểm tra quan hệ kiểu mà không đảo chiều

`Class.isAssignableFrom` có hướng đặc biệt dễ nhầm:

```java
boolean canStoreDogInAnimal = Animal.class.isAssignableFrom(Dog.class); // true
boolean canStoreAnimalInDog = Dog.class.isAssignableFrom(Animal.class); // false
```

Cách đọc: `Target.class.isAssignableFrom(Source.class)` nghĩa là **tham chiếu kiểu Target có thể được gán một giá trị kiểu Source** theo các quy tắc tương thích kiểu của API. Điều này hữu ích khi framework muốn xác nhận một class implementation có đáp ứng một interface/superclass hay không.

Khi đã có **đối tượng** thay vì cặp `Class`, dùng `Target.class.isInstance(value)` để kiểm tra (trả `false` với `null`). Nếu cần cast qua Reflection, `Target.class.cast(value)` tạo tham chiếu đã kiểm tra kiểu, ném `ClassCastException` nếu giá trị không tương thích. Trong Java thông thường, `instanceof` và pattern matching thường rõ ràng hơn:

```java
Object candidate = new Dog();
if (candidate instanceof Animal animal) {
    System.out.println(animal.speak()); // Woof
}
```

`getSuperclass()` và `getInterfaces()` mô tả **quan hệ trực tiếp được khai báo** của một lớp, không nhất thiết liệt kê toàn bộ tổ tiên/transitive interfaces. Muốn hỏi khả năng gán và hiện thực interface qua nhiều cấp, `isAssignableFrom` thường phù hợp hơn việc duyệt mỗi cấp thủ công.

## 6. Các trường hợp dễ gây nhầm

**`null` không có lớp thực tế để phản chiếu.** Một biến `Animal a = null` vẫn có kiểu khai báo `Animal` trong mã nguồn, nhưng `a.getClass()` ném `NullPointerException`. Luôn kiểm tra giá trị trước khi hỏi lớp runtime.

**Generics bị type erasure.** Trường `List<Animal> friends` có `Field.getType() == List.class`. `Field.getGenericType()` có thể cho `ParameterizedType` mang tham số `Animal` từ chữ ký khai báo. Nhưng `friends.getClass()` là lớp implementation của danh sách; nó không cung cấp `List<Animal>` hay lớp runtime chính xác của từng phần tử. Kiểu phần tử chỉ có thể kiểm tra trên từng phần tử hiện có, nếu khác `null`. `getGenericType()` không phải máy “giải” mọi type argument thực tế từ instance.

**Primitive khác object.** Với trường `int count`, `Field.getType() == int.class`. Khi gọi `Field.get(instance)`, Reflection boxing kết quả thành `Integer`; gọi `getClass()` trên giá trị boxing thấy `Integer.class`, không phải `int.class`. `int.class` không có instance của kiểu nguyên thủy để gọi `getClass()`.

**Mảng và interface.** `Object o = new String[2]` có `o.getClass() == String[].class`. Dù mảng `String[]` có thể được gán vào `Object[]` (array covariance), khi gán phần tử không tương thích vào mảng thật Java ném `ArrayStoreException`. Quan hệ assignability và lớp runtime của mảng đều phải được xét.

**Proxy và lớp được sinh động.** Nếu một đối tượng là dynamic proxy, `getClass()` trả về lớp proxy được tạo lúc chạy, thay vì interface mà tham chiếu được khai báo. Kiểm tra nó có triển khai interface không bằng `SomeInterface.class.isInstance(proxy)` hoặc `isAssignableFrom`; không so tên lớp proxy với tên interface.

**Metadata lớp không đồng nghĩa metadata biến.** `Class<?> runtimeClass = value.getClass()` chỉ mang `Class` của đối tượng. Reflection tiêu chuẩn chủ yếu tra cấu trúc class, field, method, constructor; không có `getDeclaredType()` trên `Object` để hỏi kiểu nguồn của từng tham chiếu cục bộ. Có thể dùng `Field`, `Method` hoặc `Parameter` để đọc khai báo **thành viên tương ứng**, khi đã biết phần tử chương trình cần xem xét.

**Quyền truy cập vẫn áp dụng.** `getDeclaredField` có thể tìm thấy trường `private`, nhưng `Field.get` hoặc `Method.invoke` có thể ném `IllegalAccessException` nếu chưa được phép truy cập. Java modules có thể giới hạn deep reflection; việc biết lớp runtime không tự cấp quyền mở thành viên nội bộ.

## 7. Cách chọn API trong bài toán thực tế

Khi xử lý một đối tượng trong framework, đi từ câu hỏi cụ thể:

1. **Hợp đồng API**: cần biết property, tham số hay kiểu trả về đã *khai báo*? Đọc `Field.getType()`, `Method.getParameterTypes()`, `Method.getReturnType()`, và `getGenericType()`/`getGenericReturnType()` khi cần metadata generic. Đây là nền tảng để validate schema, binding và lựa chọn converter.
2. **Giá trị ở thời điểm chạy**: cần biết object hiện tại là lớp nào? Đọc `value.getClass()` sau kiểm tra `null`. Đừng dùng nó thay cho signature được khai báo.
3. **Tính tương thích**: cần hỏi class implementation có thể gán cho kiểu API hay không? Dùng `targetType.isAssignableFrom(candidateType)`; nếu đã có value, dùng `targetType.isInstance(value)`.
4. **Hành vi đa hình**: cần gọi instance method đã override? Dùng lời gọi Java thường hoặc `Method.invoke` khi thực sự cần reflection; class thực tế quyết định implementation được dispatch.
5. **Nguồn khai báo thành viên**: cần biết một `Field`/`Method` thuộc lớp nào? Dùng `getDeclaringClass()`, không suy diễn từ `getType()` hay `getClass()` của giá trị.

**Tự kiểm tra:** với khai báo `Number n = Integer.valueOf(7)`, kiểu biến là `Number`, `n.getClass()` là `Integer.class`, và `Number.class.isAssignableFrom(Integer.class)` là `true`. Nếu đổi `n` thành `null`, kiểu khai báo vẫn là `Number` nhưng không có đối tượng runtime để gọi `getClass()`. Đây là phép phân biệt cần giữ nhất quán khi đọc và viết mã Reflection.
