# Chuyển tham chiếu theo quan hệ assignability trong Java Reflection

## 1. Mục tiêu

Khi gọi một phương thức hay constructor bằng Java Reflection, lập trình viên truyền đối số qua các API như `Method.invoke(...)` hoặc `Constructor.newInstance(...)`. Các API này nhận `Object` ở phía người gọi, nhưng **tham số thật** của phương thức đích có thể là `Animal`, `Serializable`, `Object[]`, một interface, hoặc một kiểu tham chiếu bất kỳ. JVM phải xác định đối tượng thực tế có thể được sử dụng tại vị trí tham số đó hay không.

Quy tắc cốt lõi của bài là **assignability**: một giá trị tham chiếu có thể đi vào nơi yêu cầu kiểu tham chiếu đích nếu đối tượng có kiểu runtime tương thích với kiểu đích theo quan hệ kế thừa/triển khai; `null` cũng hợp lệ cho tham số kiểu tham chiếu. Đây là cơ sở của **widening reference conversion** và kiểm tra đối số phản chiếu.

Sau bài này, bạn sẽ:

- Hiểu chính xác chiều kiểm tra `Target.class.isAssignableFrom(Source.class)`.
- Phân biệt chuyển tham chiếu mở rộng (*widening*), ép kiểu thu hẹp (*narrowing*) và chuyển đổi primitive.
- Áp dụng vào `Method.invoke`, `Constructor.newInstance` và `Field.set`.
- Xử lý interface, mảng, `null`, generic type erasure, class loader và ngoại lệ đúng cách.
- Tránh nhầm lẫn giữa đối số runtime của phương thức đích và mảng varargs `Object...` của chính API Reflection.

## 2. “Có thể gán” nghĩa là gì?

Giả sử có hệ kiểu:

```java
interface Pet {}

class Animal {}

class Dog extends Animal implements Pet {}

class Cat extends Animal {}
```

Đây là **các khai báo minh họa**, chưa phải chương trình độc lập.

Ở mã Java thông thường:

```java
Dog dog = new Dog();
Animal animal = dog; // Hợp lệ: Dog -> Animal
Pet pet = dog;       // Hợp lệ: Dog -> Pet
Object object = dog; // Hợp lệ: Dog -> Object
```

Khi truyền `dog` tới một phương thức khai báo `accept(Animal animal)`, không cần tạo bản sao đối tượng và cũng không cần thay đổi runtime class. Vẫn là **cùng một đối tượng `Dog`**, chỉ được sử dụng qua một kiểu tham chiếu rộng hơn.

Chiều ngược lại:

```java
Animal animal = new Animal();
// Dog dog = animal; // Lỗi biên dịch: không thể thu hẹp ngầm.
```

Một phép cast viết rõ `(Dog) animal` mới là yêu cầu kiểm tra thu hẹp tại runtime; với đối tượng có kiểu thực `Animal`, phép cast thất bại bằng `ClassCastException`. **Reflection không tự đoán, không tự downcast một đối tượng không tương thích và không tạo một `Dog` mới.**

Phân biệt ba ý:

| Tình huống | Có thể truyền vào tham số `Dog`? | Lý do |
| --- | --- | --- |
| Giá trị runtime là `new Dog()` | Có | Đối tượng đúng kiểu đích |
| Biến khai báo `Animal` nhưng đang trỏ tới `new Dog()` | Có, khi truyền qua Reflection | Kiểm tra đối số runtime thấy đối tượng thực sự là `Dog` |
| Giá trị runtime là `new Cat()` | Không | `Cat` không là subtype của `Dog` dù có cùng lớp cha `Animal` |
| `null` | Có | `null` hợp lệ với mọi tham số kiểu tham chiếu |
| Chuỗi `"Dog"` | Không | Không có phép chuyển chuỗi thành đối tượng `Dog` tự động |

**Điểm đặc biệt của Reflection:** tham số của `invoke` được nhận dưới dạng `Object` nên mã nguồn gọi Reflection không có kiểm tra tĩnh như một lời gọi `accept(Dog)` thông thường. Khả năng tương thích của **giá trị thực** được kiểm tra khi Reflection chuẩn bị gọi phương thức đích.

## 3. `Class.isAssignableFrom`: chiều kiểm tra không được đảo

```java
boolean allowed = TargetType.class.isAssignableFrom(SourceType.class);
```

Phát biểu tương đương: “Một giá trị có kiểu `SourceType` có thể được đặt vào biến/tham số có kiểu `TargetType` hay không?” Với kiểu tham chiếu, kiểm tra dựa vào cùng kiểu, quan hệ superclass, interface được triển khai và một số quan hệ mảng.

Ví dụ:

```java
Animal.class.isAssignableFrom(Dog.class); // true
Pet.class.isAssignableFrom(Dog.class);    // true
Object.class.isAssignableFrom(Dog.class); // true
Dog.class.isAssignableFrom(Animal.class); // false
Dog.class.isAssignableFrom(Cat.class);    // false
Dog.class.isAssignableFrom(Dog.class);    // true
```

Đoạn này dùng những kiểu đã khai báo ở mục 2, mang tính minh họa.

### 3.1. Ba API rất dễ nhầm

| API | Câu hỏi thực tế | Lưu ý |
| --- | --- | --- |
| `targetType.isAssignableFrom(sourceType)` | Quan hệ giữa **hai `Class<?>`** có cho phép gán kiểu nguồn vào kiểu đích không? | `sourceType` phải khác `null`; truyền `null` làm phát sinh `NullPointerException`. |
| `targetType.isInstance(value)` | **Đối tượng runtime** này có phải instance của kiểu đích không? | Trả `false` khi `value == null`, dù `null` vẫn được truyền hợp lệ vào tham số tham chiếu. |
| `targetType.cast(value)` | Cast đối tượng theo kiểu `Class` tại runtime | Trả lại `null` nếu `value == null`; ném `ClassCastException` nếu đối tượng không tương thích. |

Vì thế, nếu muốn **kiểm tra một đối số trước khi gọi Reflection**, phép kiểm tra kiểu tham chiếu thường có dạng:

```java
static boolean acceptsReference(Class<?> targetType, Object value) {
    if (targetType.isPrimitive()) {
        throw new IllegalArgumentException("Cần tham số tham chiếu");
    }
    return value == null || targetType.isInstance(value);
}
```

Đây là **hàm minh họa**, không phải chương trình chạy độc lập. Nó xử lý `null` tường minh thay vì dùng mỗi `isInstance`. Cũng có thể lấy `value.getClass()` rồi gọi `targetType.isAssignableFrom(...)` khi `value` khác `null`.

Không được lấy kiểu khai báo của **biến Java phía gọi** để quyết định, vì Reflection nhận giá trị đối tượng thật. Ví dụ biến `Animal candidate = new Dog();` vẫn có runtime class là `Dog`.

### 3.2. Quan hệ primitive khác quan hệ tham chiếu

`Class.isAssignableFrom` đối với primitive đòi hỏi **cùng đúng kiểu primitive**:

```java
int.class.isAssignableFrom(int.class);   // true
long.class.isAssignableFrom(int.class);  // false
Object.class.isAssignableFrom(int.class);// false
```

Điều này không có nghĩa Reflection không hỗ trợ primitive widening trong mọi API: `Method.invoke` và `Constructor.newInstance` có thể **unbox wrapper** và áp dụng **widening primitive conversion** thích hợp cho tham số primitive. Đó là một cơ chế khác, cần học riêng. **Không dùng `isAssignableFrom` để mô phỏng toàn bộ quy tắc đối số primitive**.

Trong bài này, ta chỉ phân tích **chuyển kiểu tham chiếu** giữa object/array/interface và đối số `null`.

## 4. Assignability ở ba nơi sử dụng Reflection

### 4.1. `Method.invoke`

```java
Method method = Example.class.getDeclaredMethod("accept", Animal.class);
method.invoke(null, new Dog());
```

Đây là **mã minh họa**, giả định `Example.accept(Animal)` là static, đã import `java.lang.reflect.Method` và các kiểu `Animal`, `Dog` có sẵn. Đối số `new Dog()` phù hợp với tham số khai báo `Animal`; Reflection thực hiện lời gọi.

Nếu truyền đối tượng `new Object()` vào tham số `Animal` thì đối số không hợp lệ: `Method.invoke` ném `IllegalArgumentException` **trước khi chạy thân phương thức đích**. Không có chuyển đổi tự động `Object` thành `Animal`.

Nếu một phương thức đích **tự ném ngoại lệ sau khi được gọi**, `Method.invoke` thường bao ngoại lệ đó trong `InvocationTargetException`; đừng nhầm với `IllegalArgumentException` do **không khớp đối số** tại bước chuẩn bị gọi.

### 4.2. `Constructor.newInstance`

```java
Constructor<Example> constructor =
        Example.class.getDeclaredConstructor(Animal.class);
Example instance = constructor.newInstance(new Dog());
```

Đoạn này minh họa, giả sử `Example` có constructor thích hợp và đã import `java.lang.reflect.Constructor`. Quy tắc tương thích đối số tương tự lời gọi method: `Dog` có thể đáp ứng `Animal`; một đối tượng không tương thích sẽ bị từ chối.

Lưu ý: `getDeclaredConstructor(...)` tìm constructor bằng **kiểu tham số khai báo chính xác**. Nó không tìm constructor theo quan hệ assignability:

```java
// Nếu lớp chỉ có constructor Example(Animal), truy vấn dưới đây
// không tìm được constructor Example(Dog):
// Example.class.getDeclaredConstructor(Dog.class);
```

**Tra cứu thành viên** và **kiểm tra đối số lúc invoke** là hai giai đoạn tách biệt.

### 4.3. `Field.set`

```java
Field field = Example.class.getDeclaredField("animal");
field.setAccessible(true);
field.set(example, new Dog());
```

Đây là đoạn minh họa với field khai báo `Animal animal` trong object `example`. `Field.set` kiểm tra rằng đối tượng gán hợp lệ với **kiểu field**. Nếu field là `Animal`, nhận `Dog` hoặc `Cat`, nhưng từ chối `String` bằng `IllegalArgumentException`.

`setAccessible(true)` chỉ giải quyết một phần quyền truy cập; nó **không làm kiểu của field thành `Object`**. Ngoài ra, field `final` hoặc ranh giới module có thể mang ràng buộc riêng về khả năng sửa, độc lập với assignability. Đừng dùng `Field.set` như một lối tắt để ép kiểu không hợp lệ.

## 5. Chương trình Java 17+ hoàn chỉnh và kết quả chính xác

Lưu mã sau vào file **`AssignabilityDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

public class AssignabilityDemo {
    interface Pet { String sound(); }
    static class Animal {}

    static final class Dog extends Animal implements Pet {
        public String sound() { return "woof"; }
    }

    static final class Cat extends Animal {}

    static final class Receiver {
        private Animal stored;

        Receiver(Animal animal) {
            System.out.println("constructor=" + animal.getClass().getSimpleName());
        }

        static void describe(Animal animal) {
            System.out.println("method=" + animal.getClass().getSimpleName());
        }

        static void speak(Pet pet) {
            System.out.println("interface=" + pet.sound());
        }

        static void describeNullable(Animal animal) {
            System.out.println("null=" + (animal == null));
        }

        static void array(Object[] objects) {
            System.out.println("array=" + objects.getClass().getSimpleName());
        }

        static void requireDog(Dog dog) {
            System.out.println("dog=" + dog.sound());
        }

        static void generic(List<String> values) {
            System.out.println("generic-size=" + values.size());
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Animal<-Dog="
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Pet<-Dog="
                + Pet.class.isAssignableFrom(Dog.class));
        System.out.println("Dog<-Animal="
                + Dog.class.isAssignableFrom(Animal.class));
        System.out.println("Object[]<-String[]="
                + Object[].class.isAssignableFrom(String[].class));
        System.out.println("String[]<-Object[]="
                + String[].class.isAssignableFrom(Object[].class));
        System.out.println("Object<-int="
                + Object.class.isAssignableFrom(int.class));
        System.out.println("Animal.isInstance(null)="
                + Animal.class.isInstance(null));

        Constructor<Receiver> constructor =
                Receiver.class.getDeclaredConstructor(Animal.class);
        Receiver receiver = constructor.newInstance(new Dog());

        Method describe = Receiver.class.getDeclaredMethod(
                "describe", Animal.class);
        describe.invoke(null, new Dog());

        Method speak = Receiver.class.getDeclaredMethod("speak", Pet.class);
        speak.invoke(null, new Dog());

        Method nullable = Receiver.class.getDeclaredMethod(
                "describeNullable", Animal.class);
        nullable.invoke(null, new Object[] { null });

        Method array = Receiver.class.getDeclaredMethod("array", Object[].class);
        array.invoke(null, (Object) new String[] { "a", "b" });

        Field stored = Receiver.class.getDeclaredField("stored");
        stored.setAccessible(true);
        stored.set(receiver, new Dog());
        System.out.println("field="
                + stored.get(receiver).getClass().getSimpleName());

        try {
            Method onlyDog = Receiver.class.getDeclaredMethod(
                    "requireDog", Dog.class);
            onlyDog.invoke(null, new Cat());
        } catch (IllegalArgumentException exception) {
            System.out.println("wrong-argument="
                    + exception.getClass().getSimpleName());
        }

        try {
            stored.set(receiver, "not an Animal");
        } catch (IllegalArgumentException exception) {
            System.out.println("wrong-field="
                    + exception.getClass().getSimpleName());
        }

        Method generic = Receiver.class.getDeclaredMethod(
                "generic", List.class);
        generic.invoke(null, List.of(10, 20));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 AssignabilityDemo.java
java AssignabilityDemo
```

**Stdout đã được kiểm chứng bằng JDK 21 với `--release 17`:**

```text
Animal<-Dog=true
Pet<-Dog=true
Dog<-Animal=false
Object[]<-String[]=true
String[]<-Object[]=false
Object<-int=false
Animal.isInstance(null)=false
constructor=Dog
method=Dog
interface=woof
null=true
array=String[]
field=Dog
wrong-argument=IllegalArgumentException
wrong-field=IllegalArgumentException
generic-size=2
```

### 5.1. Diễn giải các kết quả

- `Animal<-Dog=true` và `Pet<-Dog=true` cho thấy một object `Dog` có thể phục vụ cả tham số lớp cha và tham số interface mà nó triển khai.
- `Dog<-Animal=false` cho thấy hướng ngược lại không được phép khi chỉ biết **kiểu `Animal`**. Tuy nhiên, giá trị runtime thực tế là `Dog` vẫn có thể đi vào tham số `Dog` khi truyền qua Reflection.
- `Object[]<-String[]=true` cho thấy **array covariance** đối với kiểu phần tử tham chiếu.
- `Animal.isInstance(null)=false` không mâu thuẫn với `null=true`: API `isInstance` nhận xét về một **instance**, còn `null` được phép vào **tham số tham chiếu**.
- Constructor và hai lời gọi method đều nhận `Dog` tương thích với `Animal`/`Pet`; không cần tự chuyển đối tượng thành lớp khác.
- `Field.set` nhận `Dog` khi field khai báo kiểu `Animal`. Với `String`, nó từ chối bằng `IllegalArgumentException`.
- Method `requireDog(Dog)` không nhận được `Cat`, dù `Cat` cũng là `Animal`.
- `generic-size=2` cố ý chứng minh giới hạn type erasure, được giải thích ở phần 7.

## 6. Ba tình huống dễ bỏ sót: `null`, interface và mảng

### 6.1. Đối số `null`

`null` tương thích với **mọi kiểu tham chiếu**, kể cả `String`, interface, array và class do người dùng khai báo. Nó **không thể truyền vào tham số primitive** `int` hay `boolean` theo cơ chế invoke chuẩn.

Đối với `Method.invoke`, bản thân signature của API là `invoke(Object obj, Object... args)`. Để tránh nhập nhằng giữa một đối số `null` và mảng tham số varargs `null`, hãy truyền rõ:

```java
method.invoke(targetObject, new Object[] { null });
```

Đây là mã minh họa: `method` có **đúng một tham số kiểu tham chiếu**, còn `targetObject` là receiver hợp lệ; nếu method static, target có thể là `null`. Nếu truyền mảng đối số `null` trực tiếp vào varargs của API, Reflection có thể hiểu là **không có mảng chứa đối số**, dẫn đến sai số lượng tham số. Khai báo `new Object[]{null}` làm ý định rõ ràng.

### 6.2. Interface và nhiều nhánh kế thừa

Một lớp có thể implement nhiều interface. Vì thế một object có thể assignable tới nhiều kiểu đích **không có quan hệ lớp cha/con trực tiếp với nhau**. Ví dụ `Dog implements Pet`: kiểm tra `Pet.class.isAssignableFrom(Dog.class)` trả `true`.

Với `Class<?>`, sử dụng quan hệ subtype/runtime type. Tránh so sánh chuỗi `getSimpleName()` hoặc giả định chỉ cần nhìn `getSuperclass()`; đường đi hợp lệ có thể xuất phát từ **interface**.

### 6.3. Array covariance và kiểm tra phần tử lúc ghi

Với mảng phần tử tham chiếu, `String[]` là subtype của `Object[]`, nên:

```java
Object[] values = new String[1];
values[0] = "ok";  // hợp lệ
// values[0] = 42; // biên dịch được nhưng runtime ném ArrayStoreException
```

Đây là mã minh họa. Mảng **vẫn là `String[]` thật ở runtime**, nên JVM kiểm tra mỗi thao tác lưu phần tử. Ghi một `Integer` vào mảng `String[]` gây `ArrayStoreException` dù biến có kiểu `Object[]`.

**Mảng primitive khác:** `int[]` là subtype của `Object`, `Cloneable` và `java.io.Serializable`, nhưng **không phải** subtype của `Object[]` (vì phần tử `int` không phải tham chiếu). Tức là:

```java
Object.class.isAssignableFrom(int[].class);      // true
Object[].class.isAssignableFrom(int[].class);    // false
```

## 7. Generic type erasure: assignability không kiểm tra `T`

Java generic phần lớn bị xóa tham số kiểu ở runtime (*type erasure*). Ví dụ phương thức:

```java
static void generic(List<String> values) {
    System.out.println(values.size());
}
```

Đây là đoạn cắt từ chương trình `AssignabilityDemo`. Kiểu tham số thô ở runtime của phương thức này là **`List.class`**, nên lệnh:

```java
Method m = Receiver.class.getDeclaredMethod("generic", List.class);
m.invoke(null, List.of(10, 20));
```

được Reflection chấp nhận, dù danh sách giá trị chứa `Integer`. Ở ví dụ này, method chỉ gọi `size()` nên in `generic-size=2` mà không truy cập phần tử dưới giả định `String`.

**Hậu quả quan trọng:**

- `List.class.isAssignableFrom(ArrayList.class)` có thể trả `true`, nhưng `Class<?>` không mang thông tin `List<String>` hay `List<Integer>` để kiểm tra từng phần tử.
- `Method.getParameterTypes()` cho kiểu raw `Class<?>`; `Method.getGenericParameterTypes()` có thể cho metadata `ParameterizedType` mô tả khai báo `List<String>`.
- Metadata generic **không tự biến thành kiểm tra runtime đầy đủ** cho từng phần tử trong lời gọi Reflection.
- Nếu thân method đọc phần tử dưới dạng `String`, phép cast do compiler chèn có thể ném `ClassCastException` **bên trong** method. Khi gọi qua Reflection, ngoại lệ đó thường bị bọc bởi `InvocationTargetException`.

Nếu chương trình đòi hỏi xác minh phần tử, phải có kiểm tra nghiệp vụ/runtime thích hợp; `isAssignableFrom` trên mỗi raw `Class<?>` không đủ.

## 8. Class loader và danh tính kiểu

Assignability kiểm tra **đối tượng `Class<?>` runtime thật**, không đơn thuần chuỗi tên lớp. Hai kiểu có cùng binary name do **hai class loader khác nhau định nghĩa** không tự động là một kiểu hoặc subtype của nhau.

Ví dụ lý thuyết: plugin A và plugin B đều nạp một định nghĩa `com.example.PluginData` nhưng qua các class loader độc lập. Nếu class ở B không có quan hệ kế thừa hợp lệ với class ở A, thì:

```text
typeFromA.getName().equals(typeFromB.getName()) -> true
typeFromA.isAssignableFrom(typeFromB)           -> false
```

Đây là **kịch bản minh họa**, không phải chương trình đầy đủ để dựng hai class loader. Trong framework plugin, app server hoặc môi trường hot reload, kiểm tra tên class là chưa đủ. Hãy xem cả `getClassLoader()`, nguồn nạp kiểu và các loader delegation boundaries.

## 9. Bài tập tự kiểm tra

1. Thêm `interface Trainable {}` rồi để `Dog implements Pet, Trainable`. Dự đoán `Trainable.class.isAssignableFrom(Dog.class)` và thử lời gọi method nhận `Trainable`.
2. Giữ biến `Animal value = new Dog();`, gọi method đích nhận `Dog` bằng Reflection. Giải thích tại sao **runtime value** phù hợp dù static type của biến là `Animal`.
3. Gọi `Receiver.array(Object[])` bằng `String[]` rồi so sánh ba cách: ép `(Object)`, bọc `new Object[]{...}` và truyền array trực tiếp.
4. Đổi `generic(List<String>)` để đọc `values.get(0)` vào biến `String`; thử truyền `List.of(10)` qua Reflection và quan sát `InvocationTargetException.getCause()`.
5. Tạo field khai báo `Pet` rồi thử `Field.set` với `new Dog()`, `new Cat()` và `null`. Dự đoán hành vi theo assignability.
6. Tự giải thích tại sao `Object.class.isAssignableFrom(int.class)` là `false` nhưng `Object.class.isAssignableFrom(Integer.class)` là `true`.

## 10. Checklist trước khi gọi Reflection

- Xác định **formal parameter type** bằng `getParameterTypes()` hoặc `Field.getType()`.
- Với giá trị khác `null`, kiểm tra `targetType.isInstance(value)` hoặc `targetType.isAssignableFrom(value.getClass())` **khi target là reference type**.
- Với `null`, xác nhận tham số đích là kiểu tham chiếu và đóng gói `Object[]` đúng số lượng.
- Không tự thêm downcast, parse, conversion primitive hoặc generic verification vào phạm vi **reference assignability**.
- Với một đối số là array, kiểm tra cách Java đóng gói `Object...` của `invoke`.
- Khi có lỗi, phân biệt **tra cứu thành viên**, **quyền truy cập**, **sai đối số**, và **ngoại lệ do thân method**.
- Trong môi trường plugin/multi-class-loader, dựa vào danh tính `Class<?>` thật thay vì chuỗi tên.

**Ghi nhớ:** Chuyển tham chiếu qua Reflection dựa trên **kiểu runtime thực sự** và quan hệ **assignability** với kiểu tham số/field đích. `Target.class.isAssignableFrom(Source.class)` là câu hỏi về hai kiểu; `Target.class.isInstance(value)` là câu hỏi về một giá trị khác `null`. Nếu kiểm tra đúng chiều, xử lý `null` rõ ràng và phân biệt tầng varargs của `Method.invoke`, bạn có thể chẩn đoán hầu hết lỗi chuyển tham chiếu trong Reflection.