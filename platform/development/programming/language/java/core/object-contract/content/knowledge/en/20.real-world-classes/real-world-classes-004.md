# Class literal `Type.class` và so sánh với `getClass()` trong Java

## 1. Mục tiêu của bài học

Khi làm việc với một object trong Java, có ít nhất hai khái niệm kiểu cần phân biệt:

- **Kiểu ở khai báo/biểu thức** (*static type*): kiểu mà compiler biết khi phân tích mã, chẳng hạn biến `Animal animal` được khai báo là `Animal`.
- **Lớp thực tế ở runtime** (*runtime class*): lớp cụ thể của object mà biến đang tham chiếu, chẳng hạn object tạo bởi `new Dog()`.

Java cho phép một biến tham chiếu đến instance của lớp con hoặc lớp cài đặt interface. Do đó, kiểu khai báo **không nhất thiết** trùng lớp thực tế. Hai cách lấy đối tượng `Class` thể hiện hai câu hỏi khác nhau:

- `Animal.class`: đối tượng `Class<Animal>` đại diện cho kiểu `Animal` đã được nêu tường minh trong **mã nguồn**.
- `animal.getClass()`: đối tượng `Class<?>` đại diện cho **lớp thực tế** của instance mà `animal` đang trỏ tới, được xác định lúc chạy.

Trong phạm vi Java Core – Object Contract, hiểu khác biệt này giúp kiểm tra kiểu, sử dụng reflection và tránh nhầm lẫn khi thiết kế `equals()` của các lớp có kế thừa, proxy hoặc nhiều implementation.

Sau bài học, bạn có thể giải thích và áp dụng `Type.class`, `obj.getClass()`, `instanceof`, `Class.isInstance`, `Class.isAssignableFrom`; xử lý `null`; hiểu `Class` của primitive/array/interface; và chọn kiểu so sánh thích hợp với ý nghĩa nghiệp vụ.

## 2. `Type.class` thực sự là gì?

**Class literal** là biểu thức có cú pháp `TênKiểu.class`. Ví dụ:

```java
Class<String> stringType = String.class;
Class<Integer> boxedType = Integer.class;
Class<?> arrayType = String[].class;
Class<?> primitiveType = int.class;
Class<?> noValueType = void.class;
```

Đây là các câu lệnh minh họa đặt bên trong phương thức hoặc khối khởi tạo phù hợp, không phải file Java chạy độc lập.

Trong từng trường hợp, biểu thức trả về một object `java.lang.Class` đại diện cho kiểu đã nêu. Nó **không tạo instance** kiểu đó:

- `String.class` không tạo một `String` mới.
- `Dog.class` không gọi constructor `Dog`.
- `SomeInterface.class` đại diện cho interface, dù interface không thể được tạo bằng `new SomeInterface()`.
- `int.class` đại diện cho kiểu primitive `int`, không phải `Integer.class`.
- `String[].class` đại diện cho lớp runtime của mảng phần tử `String`, khác `String.class`.

Với một lớp thông thường được định nghĩa trong một class loader xác định, các lần lấy `T.class` đều trả về cùng một object `Class` cho chính định nghĩa đó. Nhưng **tên lớp giống nhau chưa chắc là cùng lớp runtime** nếu hai class loader khác nhau nạp hai định nghĩa: identity của lớp gắn với cả tên nhị phân và defining class loader.

`Class` là metadata đại diện cho một kiểu, không phải instance nghiệp vụ của kiểu đó. `String.class` là một đối tượng kiểu `Class<String>`, không phải một `String`.

### Class literal có chủ động khởi tạo lớp không?

Việc đánh giá class literal như `T.class` không tự kích hoạt **class initialization** của `T` chỉ vì tham chiếu literal đó. Khác biệt cần chú ý so với một số hành động chủ động khác như gọi static method/đọc static field không phải compile-time constant hay `Class.forName(String)` phiên bản một tham số, vốn thường yêu cầu tải và khởi tạo lớp.

Tuy nhiên, “không tự khởi tạo” không có nghĩa JVM không cần resolve/load thông tin kiểu để có đối tượng `Class`. **Loading, linking, initialization** là các giai đoạn khác nhau trong cơ chế JVM; không dùng class literal như một kỹ thuật cam kết “không đụng tới class loader”.

## 3. `obj.getClass()` lấy lớp thực tế như thế nào?

`getClass()` là phương thức `public final native Class<?> getClass()` của `java.lang.Object` về mặt API; mọi object Java đều có phương thức này và các subclass không thể override nó. Kiểu trả về chính xác trong khai báo generic của Java API có ràng buộc theo kiểu của receiver; khi sử dụng thực tế có thể viết `Class<?>` nếu chỉ cần metadata chung.

Ví dụ:

```java
class Animal {}
class Dog extends Animal {}

Animal animal = new Dog();
System.out.println(Animal.class == animal.getClass()); // false
System.out.println(Dog.class == animal.getClass());    // true
```

Đây là minh họa ở nơi cho phép khai báo class/các lệnh trong phương thức. **Kiểu khai báo** của biến `animal` là `Animal`. **Object đang được giữ** là một `Dog`. Lúc gọi `animal.getClass()`, JVM trả metadata của `Dog` vì đó là lớp thực tế của object.

Có thể dùng:

```java
Object any = "hello";
Class<?> runtimeType = any.getClass(); // String.class
```

Không cần cast `any` thành `String` để biết runtime class của object. Nhưng `getClass()` **cần một object khác null**. Nếu `any == null`, gọi `any.getClass()` sẽ ném `NullPointerException`. Ngược lại, `String.class` không cần bất kỳ biến instance nào nên vẫn đánh giá bình thường.

### So với `getClass().getName()`

- `obj.getClass()` trả đối tượng `Class` để kiểm tra identity/metadata.
- `obj.getClass().getName()` trả **chuỗi tên nhị phân** của lớp (với mảng có ký hiệu runtime đặc biệt).
- `obj.getClass().getSimpleName()` trả tên ngắn, có thể rỗng trong một số trường hợp, ví dụ các lớp vô danh.
- `obj.getClass().getCanonicalName()` có thể trả `null` cho các loại class không có canonical name.
- `obj.toString()` là cách object muốn biểu diễn chính nó, không đồng nghĩa luôn là tên lớp.

Khi muốn kiểm tra có đúng cùng lớp không, dùng **`Class` identity** (ví dụ `obj.getClass() == Dog.class`) thay vì so chuỗi tên simple name. Hai lớp ở package khác nhau có thể cùng `getSimpleName()`; hai class loader cũng có thể nạp các lớp trùng tên mà khác identity.

## 4. Bảng so sánh nhanh

| Tình huống | `Type.class` | `obj.getClass()` |
|---|---|---|
| Nguồn xác định | Tên kiểu ghi trong source | Instance thực tế tại runtime |
| Cần instance? | Không | Có, và khác `null` |
| Với biến kiểu cha chứa object lớp con | `Base.class` vẫn là `Base` | Trả `Derived.class` |
| Với interface | `Interface.class` hợp lệ | Instance trả lớp triển khai thực tế |
| Với primitive `int` | `int.class` hợp lệ | Primitive không phải object nên không gọi trực tiếp `getClass()` |
| Với boxed value `Integer` | `Integer.class` | `Integer.valueOf(1).getClass()` là `Integer.class` |
| Với array | `String[].class` | `new String[0].getClass()` là `String[].class` |
| Với biến `null` | `Type.class` vẫn hợp lệ | Gọi `getClass()` ném `NullPointerException` |
| Thay đổi theo object đang tham chiếu | Không | Có thể khác khi biến được gán instance lớp khác |

Một biến có static type `Object` không trở thành instance lớp `Object` chỉ vì nó được khai báo thế; `new String("x")` gán vào biến đó vẫn có runtime class `String`.

## 5. Khi nào cần `==`, `equals`, `instanceof` và `isAssignableFrom`?

Các phép kiểm tra dễ bị nhầm là đang trả lời cùng một câu hỏi, nhưng thực tế khác nhau.

### 5.1. So sánh chính xác hai đối tượng `Class`

```java
boolean exact = value.getClass() == Dog.class;
```

Điều này hỏi: **lớp runtime của `value` có đúng là `Dog` không?** Một instance của subclass `SpecialDog extends Dog` (nếu `Dog` không `final`) sẽ không vượt qua kiểm tra exact class của `Dog`.

`Class.equals` cũng so identity của object `Class`, nên `Dog.class.equals(value.getClass())` tương đương `Dog.class == value.getClass()` về ngữ nghĩa. `==` là lựa chọn quen thuộc vì đối tượng `Class` biểu diễn cùng một runtime class được tái sử dụng.

### 5.2. `instanceof` và `Class.isInstance` kiểm tra tương thích kiểu

```java
boolean compatible = value instanceof Dog;
boolean reflectiveCheck = Dog.class.isInstance(value);
```

Với `value` khác null, hai kiểm tra này đều đúng nếu object là `Dog` hoặc subclass của `Dog`. Với `null`, cả hai trả `false` (với `isInstance(null)` trả `false`). `instanceof` còn kiểm tra implementation của interface, không cần lấy `getClass()`.

Trong mã Java thông thường với kiểu được biết tĩnh, ưu tiên `instanceof` khi chỉ hỏi khả năng cast/kiểu tương thích. Dùng `Class.isInstance` khi đối tượng `Class<?>` đã được lấy động, chẳng hạn qua cấu hình/plugin.

### 5.3. `Class.isAssignableFrom` so **hai kiểu**, không cần object

```java
boolean canAssignDogToAnimal =
        Animal.class.isAssignableFrom(Dog.class); // true
boolean canAssignAnimalToDog =
        Dog.class.isAssignableFrom(Animal.class); // false
```

Đọc `A.class.isAssignableFrom(B.class)` là “một giá trị kiểu `B` có thể gán vào biến tham chiếu kiểu `A` theo quan hệ gán kiểu do Java quy định không?”. Với các lớp tham chiếu, interface và array, nó mô tả quan hệ kiểu runtime, gồm kế thừa/cài đặt interface.

**Hướng tham số rất dễ bị viết ngược:** `Animal.class.isAssignableFrom(Dog.class)` là `true`, còn ngược lại là `false`. Phương thức này không tự kiểm tra một object cụ thể vì đầu vào là một đối tượng `Class<?>`.

Lưu ý primitive `Class` không áp dụng boxing tự động khi kiểm tra assignability: `int.class.isAssignableFrom(Integer.class)` là `false`. Boxing là cơ chế của ngôn ngữ và lời gọi phương thức, không làm `int.class` và `Integer.class` trở thành cùng kiểu runtime.

### 5.4. Chọn công cụ đúng mục đích

| Câu hỏi | Công cụ |
|---|---|
| “Kiểu `Dog` được nêu trong source là kiểu nào?” | `Dog.class` |
| “Instance này thực chất thuộc lớp nào?” | `obj.getClass()` |
| “Instance này có thể xem/cast thành `Dog` không?” | `obj instanceof Dog` |
| “Kiểu chỉ biết lúc chạy có nhận instance này không?” | `selectedClass.isInstance(obj)` |
| “Định nghĩa lớp `Animal` có bao gồm một `Dog` không?” | `Animal.class.isAssignableFrom(Dog.class)` |
| “Hai instance có cùng lớp runtime chính xác không?” | `a.getClass() == b.getClass()` (sau khi kiểm tra null) |
| “Hai instance bằng nhau theo nghiệp vụ không?” | `a.equals(b)` theo contract của lớp; không thay bằng so `Class` |

## 6. Chương trình Java 17 chạy độc lập

Tạo tệp **`ClassLiteralDemo.java`**. Chương trình cố định dữ liệu và chỉ in những kết quả không phụ thuộc tên class ẩn hay hash runtime.

```java
public class ClassLiteralDemo {
    static class Animal { }

    static class Dog extends Animal { }

    static class Cat extends Animal { }

    interface Tagged { }

    static final class TaggedDog extends Dog implements Tagged { }

    public static void main(String[] args) {
        Animal animal = new Dog();
        Object sameObject = animal;

        System.out.println("declared literal: "
                + Animal.class.getSimpleName());
        System.out.println("runtime class: "
                + animal.getClass().getSimpleName());
        System.out.println("base exact: "
                + (animal.getClass() == Animal.class));
        System.out.println("dog exact: "
                + (animal.getClass() == Dog.class));
        System.out.println("same Class object: "
                + (animal.getClass() == sameObject.getClass()));

        System.out.println("instanceof Animal: "
                + (animal instanceof Animal));
        System.out.println("instanceof Dog: "
                + (animal instanceof Dog));
        System.out.println("Animal.isInstance: "
                + Animal.class.isInstance(animal));
        System.out.println("Animal <- Dog: "
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Animal: "
                + Dog.class.isAssignableFrom(Animal.class));

        Animal tagged = new TaggedDog();
        System.out.println("subclass exact Dog: "
                + (tagged.getClass() == Dog.class));
        System.out.println("subclass instanceof Dog: "
                + (tagged instanceof Dog));
        System.out.println("tag interface: "
                + Tagged.class.isInstance(tagged));

        Object absent = null;
        System.out.println("null isInstance: "
                + Animal.class.isInstance(absent));
        System.out.println("null instanceof: "
                + (absent instanceof Animal));

        System.out.println("primitive name: " + int.class.getName());
        System.out.println("wrapper name: " + Integer.class.getName());
        System.out.println("primitive equals wrapper: "
                + int.class.equals(Integer.class));
        System.out.println("array exact: "
                + (new String[0].getClass() == String[].class));
        System.out.println("array as Object: "
                + Object.class.isAssignableFrom(String[].class));
        System.out.println("interface literal: "
                + Tagged.class.isInterface());
    }
}
```

Tại thư mục chứa tệp, dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 ClassLiteralDemo.java
java ClassLiteralDemo
```

Output:

```text
declared literal: Animal
runtime class: Dog
base exact: false
dog exact: true
same Class object: true
instanceof Animal: true
instanceof Dog: true
Animal.isInstance: true
Animal <- Dog: true
Dog <- Animal: false
subclass exact Dog: false
subclass instanceof Dog: true
tag interface: true
null isInstance: false
null instanceof: false
primitive name: int
wrapper name: java.lang.Integer
primitive equals wrapper: false
array exact: true
array as Object: true
interface literal: true
```

### Giải thích các nhóm kết quả

**Nhóm một — Kiểu khai báo khác lớp runtime.** Biến `animal` có kiểu khai báo `Animal`, còn instance được tạo từ `Dog`. Vì thế `Animal.class` vẫn là `Animal`, nhưng `animal.getClass()` là `Dog.class`. Hai biến `animal` và `sameObject` trỏ cùng object nên lấy về cùng đối tượng `Class`.

**Nhóm hai — Kế thừa và assignability.** `Dog extends Animal` nên Dog là một Animal; `instanceof Animal` đúng và `Animal.class.isAssignableFrom(Dog.class)` đúng. Chiều `Dog.class.isAssignableFrom(Animal.class)` sai: không phải mọi Animal đều là Dog.

**Nhóm ba — Lớp con tiếp theo.** `TaggedDog extends Dog` nên object đó tương thích với `Dog` nhưng runtime class chính xác là `TaggedDog`. Phép `tagged.getClass() == Dog.class` sai trong khi `tagged instanceof Dog` đúng. Nó cũng implements `Tagged` nên `Tagged.class.isInstance(tagged)` đúng.

**Nhóm bốn — Null.** `Class.isInstance(null)` và `null instanceof Animal` trả `false`. Nhưng `absent.getClass()` sẽ ném `NullPointerException` và không được gọi ở đây.

**Nhóm năm — Primitive, wrapper, array, interface.** `int.class` và `Integer.class` biểu diễn hai kiểu khác nhau; primitive không tự boxing khi được biểu diễn bằng đối tượng `Class`. Mảng `String[]` có runtime Class riêng, và một mảng là object nên có thể gán cho `Object`. `Tagged.class` đại diện cho interface, kể cả khi bản thân interface không thể được instantiate trực tiếp.

### Những kết luận không được rút ra

- `animal instanceof Animal` đúng **không** suy ra `animal.getClass() == Animal.class`.
- `animal.getClass() == Dog.class` đúng **không** có nghĩa ta cần ép kiểu trước khi gọi `getClass()`.
- `Dog.class.isAssignableFrom(Animal.class)` sai **không** có nghĩa không thể có một biến `Animal` chứa Dog.
- `Object.class.isAssignableFrom(String[].class)` đúng **không** có nghĩa `String[].class == Object.class`.
- Hai instance cùng runtime class **không tự động bằng nhau** theo `equals`; đó vẫn là trách nhiệm của lớp.

## 7. Hệ quả với `equals()`: class literal không quyết định thay chính sách bình đẳng

`Type.class` mô tả một kiểu nêu **cố định trong source**, còn `getClass()` mô tả lớp runtime của từng instance. Khi viết `equals(Object)`, hai cách kiểm tra sau thể hiện hai chính sách khác nhau:

```java
// Trong equals(Object) của một lớp Base:
if (other == null || getClass() != other.getClass()) return false;

// Phương án khác, chỉ khi domain cho phép lớp con tham gia equality:
if (!(other instanceof Base that)) return false;
```

Đây là **hai đoạn thay thế**, không dùng đồng thời; chúng giả định đang ở trong lớp `Base` và phần còn lại của `equals` phải so các trường xác định giá trị. Cách đầu chỉ cho hai instance **cùng lớp runtime** đi tiếp. Cách thứ hai nhận cả subclass, nên các lớp trong hệ kế thừa phải thống nhất tiêu chí bình đẳng: nếu `base.equals(sub)` đúng nhưng `sub.equals(base)` sai thì đã vi phạm **đối xứng**. Dù chọn cách nào, `equals` vẫn phải phản xạ, đối xứng, bắc cầu, nhất quán và tương thích với `hashCode`.

Không thay máy móc `getClass() == other.getClass()` bằng `other.getClass() == Base.class`: class literal `Base.class` luôn cố định, trong khi `getClass()` của `this` có thể là subclass nếu phương thức được kế thừa. Với value object `final` hoặc record, rủi ro phát sinh từ subclass thường giảm; với entity/proxy runtime, kiểm tra lớp chính xác có thể loại một đối tượng đại diện cùng bản ghi. Hãy chọn chính sách equality theo mô hình và hợp đồng framework đang dùng.

Điểm cần nhớ trong bài **class literal** là `Base.class` và `obj.getClass()` không tự thay thế cho nhau. Chúng chỉ cung cấp thông tin kiểu; bản thân chúng không quyết định hai đối tượng có **cùng giá trị nghiệp vụ** hay không.

## 8. Primitive, mảng, interface, enum và record

### Primitive và `void`

`int.class` là Class của primitive `int`; `Integer.class` là Class của lớp wrapper. Hai object này khác nhau. `void.class` cũng là class literal hợp lệ đại diện kiểu `void`. Không có instance Java thông thường của `int` hoặc `void` để gọi `getClass()` trực tiếp.

Trong các API reflection, có thể dùng `Class.isPrimitive()` để kiểm tra `int.class.isPrimitive()==true`, trong khi `Integer.class.isPrimitive()==false`. `void.class.isPrimitive()` cũng được xem là primitive theo API `Class`.

### Array

`new String[0].getClass() == String[].class` là đúng. Độ dài mảng không làm thay đổi runtime class. Mảng primitive và mảng wrapper là hai kiểu khác nhau: `int[].class != Integer[].class`. Mảng `String[]` và `Object[]` cũng là các đối tượng `Class` khác nhau, dù `Object[].class.isAssignableFrom(String[].class)` đúng do covariance của mảng tham chiếu.

Mảng còn implements `Cloneable` và `java.io.Serializable`. `Object.class.isAssignableFrom(int[].class)` trả đúng, vì mảng primitive vẫn là object. Nhưng `int.class.isAssignableFrom(Integer.class)` vẫn sai.

### Interface

`Runnable.class` đại diện một interface. Một object có thể implements `Runnable` nhưng `obj.getClass()` trả lớp triển khai, không trả `Runnable.class`. Nếu muốn hỏi object có triển khai interface không, dùng `obj instanceof Runnable` hoặc `Runnable.class.isInstance(obj)`.

### Enum

`DayOfWeek.MONDAY.getClass()` trả runtime class của object enum. Với enum có **constant-specific class body** (mỗi hằng có phần thân riêng), runtime class có thể là một subclass đặc biệt, còn `getDeclaringClass()` trả enum type khai báo hằng; vì vậy không mặc định lấy `constant.getClass() == MyEnum.class` trong mọi kiểu khai báo enum. Với enum thông thường không có constant-specific class body, hai kết quả thường trùng.

### Record

Một record là lớp `final`, nên với một instance record được tạo bình thường, `recordInstance.getClass() == RecordType.class`. Nó vẫn là object Java, kế thừa `Object.getClass` và được kiểm tra bằng `instanceof` như các kiểu tham chiếu khác. Việc record được compiler sinh `equals`/`hashCode` dựa trên components **không phải** là do Java tự so một chuỗi tên lớp.

### Anonymous class và lambda

Một anonymous class có runtime class riêng, nên `new Runnable() { public void run() {} }.getClass()` không phải `Runnable.class`. Lambda cũng có runtime implementation class do JVM tạo; không dựa vào tên, số thứ tự, tính ổn định hoặc đường dẫn class này như API công khai. Nếu chỉ cần biết object có thực hiện interface nào, dùng `instanceof` hoặc `Class.isInstance`.

## 9. Class loader và sự khác biệt giữa tên lớp với identity

`Class.getName()` có thể cho cùng một chuỗi từ hai lớp được nạp bằng hai defining class loader khác nhau, nhưng hai runtime class đó **không phải cùng kiểu**. Điều này quan trọng trong plugin system, application server, modular runtime và các hệ thống có class loader cô lập.

Đừng suy luận:

```java
left.getClass().getName().equals(right.getClass().getName())
```

là đủ để hai object có cùng runtime class. Đây là đoạn biểu thức minh họa với `left`/`right` không null, không phải chương trình độc lập. Phép so đúng Class identity khi cần exact class là:

```java
left.getClass() == right.getClass()
```

Lưu ý: equality của entity/value object là chuyện khác; cùng class runtime cũng không đủ để kết luận hai object cùng giá trị hay cùng danh tính nghiệp vụ.

### So với `Class.forName`

`Type.class` sử dụng tên kiểu biết ở compile time. `Class.forName("mypackage.Type")` tra cứu kiểu bằng chuỗi runtime qua cơ chế nạp lớp; phiên bản một tham số có thể khởi tạo lớp. Nếu cần điều khiển, có overload `Class.forName(name, initialize, loader)`, cho phép lựa chọn việc khởi tạo và loader.

Chỉ dùng `Class.forName` khi thực sự cần tên động, chẳng hạn đọc cấu hình, và xử lý `ClassNotFoundException` hoặc vấn đề visibility/security phù hợp. Khi đã biết kiểu tại compile time, class literal rõ ràng và type-safe hơn.

## 10. Generics: `Class<T>` và giới hạn của `getClass()`

`Class<String>` mang generic type parameter biểu thị nó đại diện cho `String`, hỗ trợ các API reflection có typing tốt hơn. `Class<?>` là kiểu an toàn khi chỉ biết một lớp bất kỳ.

```java
Class<String> stringClass = String.class;
Class<?> runtimeClass = "text".getClass();

System.out.println(stringClass == runtimeClass); // true
```

Đoạn này nằm trong phương thức. Một số biểu thức so sánh trực tiếp giữa `Class<...>` có kiểu generic không tương thích có thể gây lỗi biên dịch do kiểm tra type; khi API cần làm việc với các Class không biết trước, lưu chúng dưới dạng `Class<?>` và dùng `Class.equals` hoặc các API phản chiếu được định kiểu.

**Type erasure** vẫn tồn tại: `List<String>` và `List<Integer>` đều có runtime class của cùng một kiểu triển khai như `ArrayList` khi cùng được tạo từ `new ArrayList<>()`. Không có `List<String>.class` vì class literal không nhận một kiểu tham số hóa. Việc gọi `list.getClass()` không thể cho biết chắc từng phần tử của list là String.

Do đó, `getClass()` là nguồn của **runtime class** chứ không phải toàn bộ thông tin generic source type. Nếu cần generic declaration metadata, những API reflection như `getGenericSuperclass()`/`getGenericInterfaces()` có giới hạn và chỉ phản ánh cấu trúc khai báo; chúng không khôi phục mọi generic argument đã bị xóa ở runtime.

## 11. Cạm bẫy và cách khắc phục

| Lỗi thường gặp | Vì sao sai | Cách đúng |
|---|---|---|
| `animal.getClass() == Animal.class` để hỏi có phải Animal không | Subclass bị loại vì runtime class khác | `animal instanceof Animal` hoặc `Animal.class.isInstance(animal)` |
| Gọi `obj.getClass()` khi `obj` có thể null | Ném `NullPointerException` | Kiểm tra null hoặc dùng `X.class.isInstance(obj)` |
| Dùng `getSimpleName()` để kiểm tra identity | Các lớp khác package/loader có thể cùng tên ngắn | So `Class` identity trực tiếp |
| Dùng `int.class == Integer.class` như thử boxing | Primitive và wrapper khác loại | Phân biệt primitive type với wrapper; đừng suy từ boxing |
| Viết `Dog.class.isAssignableFrom(Animal.class)` để kiểm tra Dog là Animal | Đảo chiều quan hệ gán | `Animal.class.isAssignableFrom(Dog.class)` |
| Tưởng `getClass()` trả kiểu khai báo của biến | Nó trả lớp của object runtime | Dùng class literal khi muốn kiểu cố định ở source |
| Dùng `getClass()` quá chặt trong equality của entity dùng ORM proxy | Proxy có thể là subclass runtime | Theo quy tắc equality/proxy của ORM thực tế |
| Chấp nhận subclass bằng `instanceof` nhưng subclass thay đổi equality | Có thể phá đối xứng/bắc cầu | Thiết kế hợp đồng cho hierarchy hoặc dùng value object `final` |
| Dùng `getName()` làm identity lớp | Class loader khác nhau có thể định nghĩa cùng tên | So object `Class`, cân nhắc defining class loader |
| Nghĩ `getClass()` khôi phục `List<String>` | Generic erasure | Thiết kế type token hoặc metadata khác khi cần |
| Gắn tên runtime class của lambda/proxy vào business logic | Tên/lớp tổng hợp là chi tiết triển khai | So interface/hợp đồng API, không suy từ tên tự sinh |

## 12. Bài tập thực hành

### Bài 1 — Kế thừa và runtime class

Tạo `Animal` và `Dog extends Animal`. Gán `Animal x = new Dog()`, rồi dự đoán:
- `x.getClass() == Animal.class` → `false`.
- `x.getClass() == Dog.class` → `true`.
- `x instanceof Animal` → `true`.
- `Animal.class.isAssignableFrom(Dog.class)` → `true`.
- `Dog.class.isAssignableFrom(Animal.class)` → `false`.

Giải thích bằng static type và runtime class, không chỉ học thuộc kết quả.

### Bài 2 — Kiểu interface và nhiều implementation

Tạo `interface Payment`, hai lớp `CardPayment` và `CashPayment` implements `Payment`. Dùng biến `Payment payment` lần lượt trỏ vào từng object. `Payment.class` luôn đại diện interface; `payment.getClass()` lần lượt trả các implementation tương ứng; `payment instanceof Payment` luôn đúng với object khác null.

### Bài 3 — Null và API động

Cho `Object maybeNull = null`. So kết quả `maybeNull instanceof String`, `String.class.isInstance(maybeNull)`, và thử `maybeNull.getClass()` trong một `try/catch`. Hai phép đầu trả `false`, phép cuối ném `NullPointerException`. Giải thích tại sao class literal không cần instance.

### Bài 4 — Equals cho value object

Tạo class `final` có hai trường bất biến `code` và `version`. Viết `equals` kiểm tra `this==other`, kiểu exact và hai trường; `hashCode` dùng cùng trường. Tạo hai instance riêng cùng giá trị, xác nhận chúng bằng nhau và hash bằng nhau. Sau đó giải thích vì sao `getClass()` trong lớp `final` không gặp vấn đề subclass.

### Bài 5 — Array và primitive

So `int.class` với `Integer.class`, `int[].class` với `Integer[].class`, `String[].class` với `Object[].class`. Kiểm tra thêm `Object[].class.isAssignableFrom(String[].class)` và `Object.class.isAssignableFrom(int[].class)`, rồi giải thích array covariance và array là object.

### Bài 6 — So sánh khi dùng proxy

Giả lập `ProxyEntity extends Entity` với `Entity normal = new Entity(...)` và `Entity proxy = new ProxyEntity(...)`. So `normal.getClass() == proxy.getClass()` và `proxy instanceof Entity`. Nêu tại sao phép so exact class có thể không phù hợp cho ORM proxy, và phải thống nhất chính sách equality trước khi dùng entity làm khóa collection.

### Bài 7 — Class loader

Tìm hiểu ứng dụng plugin nạp cùng fully qualified class name qua hai class loader riêng. Giải thích vì sao `getName()` có thể trùng nhưng đối tượng `Class` khác nhau; tại sao cast chéo giữa hai runtime class không nhất thiết thành công dù tên giống nhau. Không cần tự viết custom class loader để hiểu định nghĩa.

## 13. Checklist áp dụng trong dự án

- Đã phân biệt static type trong source và runtime class của instance.
- Dùng `Type.class` khi muốn metadata của kiểu xác định từ mã nguồn.
- Dùng `getClass()` khi thật sự cần lớp cụ thể runtime và object khác null.
- Dùng `instanceof`/`Class.isInstance` khi muốn chấp nhận subclass hoặc interface implementation.
- Dùng `Class.isAssignableFrom` đúng chiều khi so quan hệ giữa hai kiểu.
- Không đánh đồng primitive Class và wrapper Class; biết array/interface có Class riêng.
- Không dựa trên `getSimpleName()` hoặc tên lambda/proxy tự sinh để định danh kiểu.
- Khi dùng `getClass()` trong `equals`, đã rà soát kế thừa, đối xứng, proxy và quan hệ nghiệp vụ.
- Khi dùng reflection/generics, hiểu `Class<?>` và giới hạn của type erasure.
- Đã chạy ví dụ `ClassLiteralDemo.java` và có thể giải thích từng dòng output.

**Điểm ghi nhớ:** `Type.class` mô tả **kiểu được nêu tường minh** trong chương trình, còn `obj.getClass()` mô tả **lớp thực tế của object tại runtime**. Phép so exact class khác phép kiểm tra tương thích theo kế thừa. Chọn đúng phép kiểm tra là một phần quan trọng của việc thiết kế Object Contract rõ ràng, an toàn và dễ duy trì.