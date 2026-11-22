# Lớp mảng, kiểu phần tử và ClassLoader tương ứng trong Java

## 1. Vì sao mảng cũng có lớp runtime?

Một mảng Java là **đối tượng**. Khi chạy chương trình, mỗi đối tượng mảng có một lớp runtime riêng được JVM biểu diễn bằng `Class<?>`. Ví dụ `int[]`, `String[]`, `String[][]`, `plugin.Widget[]` đều có đối tượng `Class` tương ứng.

Điểm dễ gây nhầm là các lớp mảng **không có tệp `.class` riêng** như lớp thông thường. JVM tạo lớp mảng khi cần. Quan hệ với ClassLoader của lớp phần tử được quy định riêng:

- Nếu **kiểu phần tử là kiểu tham chiếu** (class, interface hoặc một kiểu mảng khác), lớp mảng được JVM tạo ra và gắn với **defining loader của kiểu phần tử đó**.
- Nếu **kiểu phần tử là primitive** (`int`, `boolean`, `byte`, v.v.), lớp mảng được JVM coi là do **bootstrap class loader** định nghĩa. `getClassLoader()` trả `null` để biểu diễn bootstrap.
- Với mảng nhiều chiều, xét **immediate component type**: thành phần trực tiếp của `Widget[][]` là `Widget[]`, rồi thành phần của `Widget[]` là `Widget`. Theo chuỗi này, defining loader của mảng nhiều chiều được xác định từ kiểu phần tử cơ sở.
- JVM không gọi `findClass("[Lplugin.Widget;")` của custom loader chỉ để đọc một tệp bytecode `Widget[].class`, vì **không có tệp như vậy** theo mô hình Java thông thường.

**Quy tắc nhớ:** *Lớp mảng của reference type đi theo defining loader của component type; lớp mảng primitive đi với bootstrap.* Đây là quy tắc về **định danh runtime**, không phải yêu cầu mảng phải được “định nghĩa” bằng `defineClass` như class file bình thường.

## 2. Phân biệt kiểu phần tử trực tiếp và kiểu phần tử cơ sở

Đối với mảng một chiều `T[]`, component type là `T`. Đối với `T[][]`, component type trực tiếp là `T[]`, còn kiểu phần tử cơ sở (base component type) là `T`.

| Kiểu biểu thức Java | Class runtime | `getComponentType()` | Kiểu phần tử cơ sở |
|---|---|---|---|
| `int[]` | `int[].class` | `int.class` | `int` |
| `String[]` | `String[].class` | `String.class` | `String` |
| `String[][]` | `String[][].class` | `String[].class` | `String` |
| `int[][][]` | `int[][][].class` | `int[][].class` | `int` |
| `Widget[][]` | `Widget[][].class` | `Widget[].class` | `Widget` |

`getComponentType()` trả `null` nếu gọi trên `Class` không biểu diễn một kiểu mảng, ví dụ `String.class`. Phương thức `Class.isArray()` cho biết lớp được hỏi có phải là array class.

Lưu ý rằng **kiểu mảng là kiểu tham chiếu**, kể cả `int[]`: biến mảng chứa tham chiếu tới một array object; chỉ **các phần tử bên trong** `int[]` mới là primitive. Vì thế `int[]` có thể gán cho `Object`, trong khi `int` bản thân nó không phải đối tượng.

### Ví dụ Java 17+ kiểm tra component type

Tạo file `ArrayComponentDemo.java`:

```java
public class ArrayComponentDemo {
    private static void describe(Class<?> type) {
        Class<?> component = type.getComponentType();
        System.out.println(type.getTypeName()
                + " | isArray=" + type.isArray()
                + " | component="
                + (component == null ? "<none>" : component.getTypeName()));
    }

    public static void main(String[] args) {
        describe(String.class);
        describe(String[].class);
        describe(String[][].class);
        describe(int[].class);
        describe(int[][][].class);
    }
}
```

Biên dịch và chạy:

```bash
javac ArrayComponentDemo.java
java ArrayComponentDemo
```

Stdout:

```text
java.lang.String | isArray=false | component=<none>
java.lang.String[] | isArray=true | component=java.lang.String
java.lang.String[][] | isArray=true | component=java.lang.String[]
int[] | isArray=true | component=int
int[][][] | isArray=true | component=int[][]
```

Ở đây dùng `Class.getTypeName()` vì biểu diễn thân thiện với người đọc. `Class.getName()` của array class lại dùng cú pháp **array descriptor**, xem mục kế tiếp.

## 3. Tên array class có dạng đặc biệt

`Class.getName()` không trả chuỗi `"java.lang.String[]"` cho mảng. Theo cách biểu diễn nhị phân trong JVM, nó dùng tiền tố `[` và ký hiệu kiểu thành phần.

| Biểu thức | `getName()` |
|---|---|
| `int[].class` | `[I` |
| `boolean[].class` | `[Z` |
| `byte[].class` | `[B` |
| `long[].class` | `[J` |
| `double[].class` | `[D` |
| `String[].class` | `[Ljava.lang.String;` |
| `String[][].class` | `[[Ljava.lang.String;` |
| `int[][].class` | `[[I` |

Các mã primitive trong descriptor là `Z` boolean, `B` byte, `C` char, `D` double, `F` float, `I` int, `J` long, `S` short. `L...;` biểu diễn tên binary của reference type, ví dụ `Ljava.lang.String;`. Mỗi dấu `[` thêm một chiều mảng. Đừng nhầm các chuỗi này với đường dẫn tệp hay tên lớp nguồn để truyền cho `ClassLoader.findClass`.

### Ví dụ in tên và loader

Tạo `ArrayNameDemo.java`:

```java
public class ArrayNameDemo {
    public static void main(String[] args) {
        System.out.println(int[].class.getName());
        System.out.println(String[].class.getName());
        System.out.println(String[][].class.getName());
        System.out.println(int[][].class.getName());
        System.out.println("int[] loader == null: "
                + (int[].class.getClassLoader() == null));
        System.out.println("String[] loader == null: "
                + (String[].class.getClassLoader() == null));
    }
}
```

Chạy:

```bash
javac ArrayNameDemo.java
java ArrayNameDemo
```

Stdout trên JVM Java SE chuẩn:

```text
[I
[Ljava.lang.String;
[[Ljava.lang.String;
[[I
int[] loader == null: true
String[] loader == null: true
```

Trong ví dụ, `String` là lớp nền tảng được bootstrap loader định nghĩa nên cả `String[]` cũng có defining loader tương ứng bootstrap. **Không phải mọi mảng reference type đều có `getClassLoader() == null`**: mảng chứa class do loader ứng dụng hoặc custom loader định nghĩa thường trả chính loader đó.

## 4. JVM tạo array class như thế nào?

Đối với class thông thường, loader có thể nhận bytecode rồi gọi `defineClass(...)` để định nghĩa một runtime class. Đối với **array class**, đặc tả JVMS `5.3.3` quy định JVM **tạo lớp mảng trực tiếp**.

Diễn giải khái niệm:

```text
Yêu cầu dùng array type T[]
            │
            ▼
Xác định component type T
            │
            ├── T là primitive
            │      └── array class do bootstrap định nghĩa
            │
            └── T là reference type
                   ├── T đã được định nghĩa bởi loader L
                   └── array class của T[] gắn với loader L
            │
            ▼
JVM có Class<?> cho array type T[]
            │
            ▼
new T[n] / Array.newInstance(T.class, n)
tạo array object theo lớp mảng tương ứng
```

Các câu trong sơ đồ là quan hệ **kiểu và định danh**, không nhất thiết là chuỗi gọi Java method thật. JVM có thể tạo/lưu array class theo nhu cầu, và dùng lại đối tượng `Class` đã có cho cùng kiểu mảng runtime.

Điểm quan trọng:

- `ClassLoader` hiện tại có thể **khởi xướng** việc yêu cầu một array class, nhưng **defining loader của array class** là loader của component reference type hoặc bootstrap nếu component là primitive.
- Không có bước Java API `defineClass` với bytes của `[L...;` trong cơ chế tạo array class chuẩn. Tự tạo file `[L...;.class` hay tự gọi `defineClass` với một tên mô tả mảng không phải cách hợp lệ để định nghĩa array type chuẩn.
- Hai lớp thành phần cùng binary name nhưng do defining loaders khác nhau tạo ra dẫn tới **hai array classes khác nhau**, ngay cả khi tên `Class.getName()` của hai mảng bằng nhau.
- Cùng runtime component class và cùng số chiều thì `T[]` được nhận diện như cùng một array class runtime; gọi `new T[1]` và `new T[10]` chỉ tạo **hai object**, không tạo hai định nghĩa lớp khác nhau.

## 5. Mối quan hệ với defining loader và initiating loader

**Defining ClassLoader** là loader chịu trách nhiệm định nghĩa class runtime. **Initiating ClassLoader** là loader được JVM ghi nhận khởi xướng việc tải class theo tên; một loader con có thể ủy quyền cho parent và trở thành initiating loader của class do parent định nghĩa.

Đối với array class, quy tắc gắn defining loader với component type vẫn giữ nguyên. Ví dụ:

```text
AppLoader định nghĩa app.Customer
        │
        └── JVM tạo app.Customer[] → defining loader AppLoader

PluginLoader định nghĩa plugin.Widget
        │
        └── JVM tạo plugin.Widget[] → defining loader PluginLoader

Bootstrap định nghĩa java.lang.String
        │
        └── JVM tạo java.lang.String[] → defining loader bootstrap

Kiểu primitive int
        │
        └── JVM tạo int[] → defining loader bootstrap
```

Khi đánh giá `someArray.getClass().getClassLoader()`, kết quả là **defining loader của array class**. Nó không nhất thiết là loader của lớp chứa dòng lệnh đang được thực thi. Nếu một ứng dụng host sử dụng reflection để tạo mảng từ `Class<?>` mà plugin loader định nghĩa, array class tương ứng vẫn thuộc plugin loader.

Ví dụ:

```java
// Trích đoạn giải thích, không phải chương trình độc lập:
Class<?> elementClass = pluginLoader.loadClass("plugin.Widget");
Object array = java.lang.reflect.Array.newInstance(elementClass, 3);
Class<?> arrayClass = array.getClass();

boolean sameLoader =
        arrayClass.getClassLoader() == elementClass.getClassLoader();
```

Với `elementClass` là reference class, `sameLoader` bằng `true` theo quy tắc định nghĩa lớp mảng. Điều này đúng cả khi `array` được tạo từ code của host loader khác.

## 6. Ví dụ đầy đủ: hai custom loaders, một tên phần tử, hai kiểu mảng

Ví dụ này cố ý dùng **hai loader khác nhau** định nghĩa class cùng binary name `demo.Widget`. Kết quả cho thấy tên lớp mảng giống nhau vẫn không làm chúng thành cùng runtime type.

### 6.1. Tệp class thành phần

Trong thư mục làm việc riêng, tạo `Widget.java`:

```java
package demo;

public final class Widget {
    static {
        System.out.println("Widget initialized");
    }

    public Widget() {
    }
}
```

Chương trình host sẽ không import trực tiếp `demo.Widget`: host dùng reflection để tránh cho application loader nạp lớp plugin.

### 6.2. Tệp host

Tạo `ArrayLoaderDemo.java` cạnh `Widget.java`:

```java
import java.io.IOException;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ArrayLoaderDemo {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;
        private final String label;

        DirectoryLoader(Path root, ClassLoader parent, String label) {
            super(parent);
            this.root = root;
            this.label = label;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path classFile = root.resolve(
                    name.replace('.', '/') + ".class"
            );

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(classFile);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }

            System.out.println("define " + label + ": " + name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("plugin-classes");
        ClassLoader parent = ArrayLoaderDemo.class.getClassLoader();

        DirectoryLoader left = new DirectoryLoader(root, parent, "left");
        DirectoryLoader right = new DirectoryLoader(root, parent, "right");

        Class<?> leftElement = left.loadClass("demo.Widget");
        Class<?> rightElement = right.loadClass("demo.Widget");

        Class<?> leftArray = Array.newInstance(leftElement, 0).getClass();
        Class<?> rightArray = Array.newInstance(rightElement, 0).getClass();

        System.out.println("same element name: "
                + leftElement.getName().equals(rightElement.getName()));
        System.out.println("same element class: "
                + (leftElement == rightElement));
        System.out.println("same array name: "
                + leftArray.getName().equals(rightArray.getName()));
        System.out.println("same array class: "
                + (leftArray == rightArray));

        System.out.println("left array loader is left: "
                + (leftArray.getClassLoader() == left));
        System.out.println("right array loader is right: "
                + (rightArray.getClassLoader() == right));

        System.out.println("left array component is left element: "
                + (leftArray.getComponentType() == leftElement));
        System.out.println("descriptor lookup matches left array: "
                + (Class.forName("[Ldemo.Widget;", false, left) == leftArray));

        System.out.println("before making an element");
        Object instance = leftElement.getDeclaredConstructor().newInstance();
        System.out.println("left instance recognized: "
                + leftElement.isInstance(instance));
    }
}
```

### 6.3. Biên dịch và chạy đúng classpath

Chạy bằng JDK 17+ ở thư mục có hai file `.java`:

```bash
mkdir plugin-classes
javac -d plugin-classes Widget.java
javac ArrayLoaderDemo.java
java -cp . ArrayLoaderDemo
```

Sau compile, cấu trúc có dạng:

```text
working-directory/
├── Widget.java
├── ArrayLoaderDemo.java
├── ArrayLoaderDemo.class
├── ArrayLoaderDemo$DirectoryLoader.class
└── plugin-classes/
    └── demo/
        └── Widget.class
```

**Không thêm `plugin-classes` vào classpath khi chạy host.** Nếu thêm, loader cha có thể tìm `demo.Widget` và cả hai custom loaders cùng ủy quyền thành công cho cha, làm mất tình huống so sánh hai defining loaders độc lập.

### 6.4. Kết quả và diễn giải

Stdout theo chương trình này:

```text
define left: demo.Widget
define right: demo.Widget
same element name: true
same element class: false
same array name: true
same array class: false
left array loader is left: true
right array loader is right: true
left array component is left element: true
descriptor lookup matches left array: true
before making an element
Widget initialized
left instance recognized: true
```

Giải thích:

1. Cả hai loader có cùng root chứa bytecode `demo.Widget`, nhưng **mỗi loader riêng** gọi `defineClass` cho bản riêng. Vì vậy hai đối tượng `Class<?>` của `demo.Widget` khác nhau.
2. `Array.newInstance(leftElement, 0)` yêu cầu JVM sử dụng array class có phần tử `leftElement`. `rightElement` tạo một array class **khác**. Độ dài 0 vẫn là một array object hợp lệ với array class xác định.
3. Tên cả hai class phần tử đều `demo.Widget`; tên cả hai array classes đều `[Ldemo.Widget;`, nhưng `leftArray != rightArray`.
4. `leftArray.getClassLoader() == left` và `rightArray.getClassLoader() == right` cho thấy **defining loader của array class đi theo component reference type**.
5. `Class.forName("[Ldemo.Widget;", false, left)` giải quyết descriptor của array type theo component type mà loader `left` nhận diện; nó trả cùng lớp mảng `leftArray` và **không yêu cầu init component class**.
6. Những thao tác load class, tạo mảng rỗng và tra descriptor không in `Widget initialized`. Dòng đó chỉ in khi tạo instance của `leftElement` bằng reflection, kích hoạt **initialization** của lớp phần tử bên trái.
7. Lớp `demo.Widget` của loader bên phải trong ví dụ vẫn chưa được khởi tạo. Nếu tạo instance của nó sau đó, static initializer của **runtime class khác** này có thể chạy riêng.

**Chú ý:** Vì loader trong ví dụ kế thừa thuật toán parent-first, kết quả hai lớp độc lập dựa trên điều kiện host classpath **không chứa** `demo.Widget`. Đây là điểm cần xác minh nếu thử trong IDE hoặc build tool vốn tự mở rộng classpath.

## 7. Array type khác nhau ảnh hưởng cast và kiểm tra kiểu

Mỗi array object mang class runtime gắn với component class. Do đó việc cast mảng phải dùng **đúng runtime component type**, không chỉ so trùng tên kiểu.

Ví dụ với hai class ở mục 6:

```java
// Trích đoạn để thêm bên trong main của ArrayLoaderDemo:
Object fromLeft = Array.newInstance(leftElement, 1);
Object fromRight = Array.newInstance(rightElement, 1);

System.out.println(leftArray.isInstance(fromLeft));   // true
System.out.println(leftArray.isInstance(fromRight));  // false

try {
    leftArray.cast(fromRight);
} catch (ClassCastException ex) {
    System.out.println("cross-loader array cast rejected");
}
```

Đây là **trích đoạn** của `main`, không phải một file độc lập. Nếu thêm sau phần setup, stdout bổ sung là:

```text
true
false
cross-loader array cast rejected
```

Cả hai object có cùng tên runtime descriptor (ví dụ `[Ldemo.Widget;` khi gọi `getClass().getName()`) nhưng cast vẫn thất bại vì component runtime classes khác nhau. Điều này là bản chất của **type identity** trong JVM, không phải lỗi do Java không so sánh đúng chuỗi class name.

### ArrayStoreException và mảng hiệp biến

Mảng của reference types là **covariant**: `String[]` có thể gán vào biến `Object[]`. JVM kiểm tra store tại runtime để bảo đảm phần tử mới tương thích với component class thực.

Tạo `ArrayStoreDemo.java`:

```java
public class ArrayStoreDemo {
    public static void main(String[] args) {
        Object[] values = new String[2];
        values[0] = "ok";

        System.out.println(values[0]);
        try {
            values[1] = 123;
        } catch (ArrayStoreException ex) {
            System.out.println("rejected incompatible element");
        }
    }
}
```

Chạy:

```bash
javac ArrayStoreDemo.java
java ArrayStoreDemo
```

Stdout:

```text
ok
rejected incompatible element
```

`values` có kiểu biến `Object[]` nhưng object thực là `String[]`. Khi gán một `Integer` (autobox từ `123`), array store check dựa trên component runtime `String` và ném `ArrayStoreException`.

Tương tự, nếu viết code bytecode hoặc reflection cố lưu instance do loader bên phải định nghĩa vào array có component do loader bên trái định nghĩa, JVM sẽ từ chối. Với `java.lang.reflect.Array.set`, lỗi đối với phần tử không phù hợp thường là `IllegalArgumentException` của API reflection; đừng mặc định mọi API đều ném cùng một lớp exception.

**Mảng primitive không hiệp biến theo cùng cách:** `int[]` là đối tượng và là `Object`, nhưng **không phải** `Object[]` vì phần tử trực tiếp là primitive `int`, không phải reference.

## 8. Mảng đa chiều và loader theo kiểu cơ sở

Với `plugin.Widget[][][]`:

```text
plugin.Widget[][][]
   component: plugin.Widget[][]
       component: plugin.Widget[]
           component: plugin.Widget
               defining loader = PluginLoader
```

JVM tạo các array classes tương ứng; mọi cấp mảng tham chiếu ở chuỗi này có defining loader của `plugin.Widget`. Ví dụ:

```java
// Trích đoạn trong main của ví dụ custom loader:
Class<?> oneDimension = Array.newInstance(leftElement, 0).getClass();
Class<?> twoDimensions =
        Array.newInstance(leftElement, 0, 0).getClass();

System.out.println(twoDimensions.getComponentType() == oneDimension);
System.out.println(twoDimensions.getClassLoader() == left);
```

Stdout bổ sung:

```text
true
true
```

`Array.newInstance(component, dimensions...)` tạo array object nhiều chiều có runtime array type phù hợp. Khi dùng nhiều chiều, component type **trực tiếp** không còn `leftElement` mà là array type bớt một chiều; vẫn giữ cùng defining loader theo chuỗi component.

Với `int[][]`, immediate component là `int[]` (một reference array type), nhưng `int[]` do bootstrap định nghĩa, nên `int[][]` cũng có defining loader bootstrap. Không nên áp quy tắc “mảng nhiều chiều là reference component nên loader là AppLoader” nếu component trực tiếp đó vốn là một array class của primitive.

## 9. Mảng có cần khởi tạo lớp phần tử không?

Một nhầm lẫn phổ biến là **tạo mảng `new T[n]` có nghĩa JVM chạy ngay `T.<clinit>`**. Điều đó không đúng. Theo JLS, tạo một mảng có component reference type không tự nó yêu cầu khởi tạo lớp T.

Tạo `ArrayInitializationDemo.java`:

```java
public class ArrayInitializationDemo {
    static final class Element {
        static {
            System.out.println("Element initialized");
        }

        static void ping() {
            System.out.println("Element.ping");
        }
    }

    public static void main(String[] args) {
        System.out.println("before array");
        Element[] elements = new Element[2];
        System.out.println("after array: " + elements.length);
        System.out.println("first element is null: "
                + (elements[0] == null));

        System.out.println("before active use");
        Element.ping();
    }
}
```

Biên dịch và chạy:

```bash
javac ArrayInitializationDemo.java
java ArrayInitializationDemo
```

Stdout:

```text
before array
after array: 2
first element is null: true
before active use
Element initialized
Element.ping
```

Tại `new Element[2]`, JVM tạo array object có hai phần tử reference ban đầu `null`; **không tạo hai instance của Element** và không chạy static initializer của Element. Khi gọi phương thức static `Element.ping()`, JVM cần khởi tạo Element rồi mới chạy thân phương thức.

Với `int[]`, không có class initialization của một “lớp int” theo nghĩa class Java: primitive không có `<clinit>`. Các phần tử số nguyên trong mảng mới có giá trị mặc định `0`.

### Loading, linking, initialization là những chuyện khác nhau

- Để biểu diễn một array type, JVM cần xác định component type và có thể phải **load** class thành phần.
- Việc tạo hoặc lấy `Class<?>` của array type **không tự yêu cầu initialization** của reference component class.
- Khi sau đó gọi static method, đọc static field không phải constant variable hoặc tạo **instance của component class**, JVM có thể phải khởi tạo lớp thành phần.
- Gọi `Class.forName("[Ldemo.Widget;", false, loader)` cho descriptor mảng dùng loader để nhận diện component type nhưng **không chạy `Widget.<clinit>`** theo yêu cầu `initialize=false`. Không nhầm `ClassLoader.loadClass("demo.Widget")` (binary name của lớp) với việc đưa trực tiếp descriptor mảng vào custom loader.

## 10. Type identity, package và class loader

Đối với **class hoặc interface thông thường**, danh tính runtime không chỉ dựa vào binary name mà còn dựa vào defining loader. Với **array class**, danh tính phụ thuộc vào array component runtime type cùng số chiều. Vì vậy:

```text
PluginLoader-1 định nghĩa sample.Item
    └── sample.Item[] ở PluginLoader-1

PluginLoader-2 định nghĩa sample.Item
    └── sample.Item[] ở PluginLoader-2
```

Hai array class có cùng descriptor `[Lsample.Item;` về mặt văn bản nhưng không có cùng `Class<?>` và không cast qua lại như cùng kiểu. Đối với package-private access, một class cùng tên package được định nghĩa bởi loader khác **không tự thuộc cùng runtime package** với class kia. Đây là một quan hệ khác của danh tính kiểu JVM; array class có tính truy cập dựa trên component type của nó, chứ không xóa rào cản giữa các loader.

Có thể kiểm tra với:

```java
Class<?> a = someArray.getClass();
Class<?> c = a.getComponentType();

System.out.println(a.getName());
System.out.println(a.getClassLoader());
System.out.println(c == expectedComponent);
```

Đây là trích đoạn chẩn đoán; các biến `someArray` và `expectedComponent` cần được cung cấp trong chương trình thực. **`getName()` chỉ là chuỗi mô tả**. Để xác nhận cùng runtime array type, dùng so sánh `Class<?>` hoặc `isInstance`/`isAssignableFrom` với đúng đối tượng `Class`.

## 11. Những thuộc tính chung của mọi array class

Dù có component khác nhau, các array classes tuân theo một số quy tắc chung:

1. Superclass trực tiếp của mọi array class là `java.lang.Object`.
2. Mọi array class đều triển khai `java.lang.Cloneable` và `java.io.Serializable`.
3. Độ dài array object được đọc qua `array.length`; không có thao tác đổi kích thước mảng đã tạo.
4. `clone()` trên mảng tạo **bản sao nông**: các phần tử reference bên trong vẫn trỏ đến những object tương ứng ban đầu.
5. Array object có component runtime type cố định; kiểm tra kiểu khi gán vào mảng reference bảo vệ tương thích kiểu phần tử.
6. JVM tạo array class, nên **không có constructor Java bình thường do bạn khai báo** cho `String[]` hay `Widget[]`.

Tạo `ArrayPropertiesDemo.java`:

```java
import java.io.Serializable;

public class ArrayPropertiesDemo {
    public static void main(String[] args) {
        int[] values = {1, 2};

        System.out.println("superclass: "
                + values.getClass().getSuperclass().getName());
        System.out.println("Cloneable: " + (values instanceof Cloneable));
        System.out.println("Serializable: "
                + (values instanceof Serializable));
        System.out.println("as Object: " + (values instanceof Object));

        int[] copy = values.clone();
        System.out.println("distinct object: " + (copy != values));
        System.out.println("same array class: "
                + (copy.getClass() == values.getClass()));
    }
}
```

Chạy:

```bash
javac ArrayPropertiesDemo.java
java ArrayPropertiesDemo
```

Stdout:

```text
superclass: java.lang.Object
Cloneable: true
Serializable: true
as Object: true
distinct object: true
same array class: true
```

Một chỗ dễ nhầm: `new String[10]` không tạo 10 object `String`; nó tạo mảng có 10 ô tham chiếu ban đầu `null`. Tương tự, `new Widget[10]` không gọi 10 constructors của Widget.

## 12. Reflection và cách chọn đúng loader

Reflection tạo array từ đối tượng `Class<?>` giúp kiểm tra quy tắc loader mà không cần cast tĩnh sang tên class plugin:

```java
import java.lang.reflect.Array;

// Trích đoạn trong chương trình đã có componentClass:
Object instanceArray = Array.newInstance(componentClass, 5);
Class<?> arrayClass = instanceArray.getClass();

System.out.println(arrayClass.isArray());
System.out.println(arrayClass.getComponentType() == componentClass);
System.out.println(arrayClass.getClassLoader()
        == componentClass.getClassLoader());
```

Với `componentClass` là class/interface reference, cả ba biểu thức in `true`. Nếu `componentClass` là `int.class`, dòng so loader vẫn `true` vì `int.class.getClassLoader()` và `int[].class.getClassLoader()` đều là `null` trong API, biểu diễn primitive/bootstrap; nhưng không nên nói primitive `int` là class file do bootstrap nạp.

### Dùng Class.forName với descriptor của array type

API `Class.forName` có thể nhận **binary name** của class thông thường hoặc **tên descriptor của array class**, ví dụ:

```java
Class<?> one = Class.forName("[I");
Class<?> two = Class.forName("[Ljava.lang.String;");
Class<?> three = Class.forName("[[Ljava.lang.String;");

System.out.println(one == int[].class);
System.out.println(two == String[].class);
System.out.println(three == String[][].class);
```

Đây là trích đoạn hợp lệ khi đặt trong phương thức cho phép `throws ClassNotFoundException`; ba dòng `println` đều in `true` trên JVM Java SE chuẩn. Khi reference type là class plugin, hãy truyền **loader thích hợp** bằng overload ba tham số:

```java
// Trích đoạn: left là DirectoryLoader trong ArrayLoaderDemo
Class<?> arrayFromName =
        Class.forName("[Ldemo.Widget;", false, left);
```

Nếu truyền loader khác đã định nghĩa một `demo.Widget` riêng, bạn nhận array class của **component runtime class khác**, dù chuỗi descriptor giống nhau. Nếu đưa tên array descriptor cho `ClassLoader.loadClass(String)` của một custom loader, hành vi không phải cách portable để yêu cầu JVM tạo mảng; ưu tiên `Class.forName` hoặc `Array.newInstance` theo đúng mục đích.

## 13. Những lỗi chẩn đoán thường gặp

| Quan sát | Sai lầm dễ mắc | Giải thích đúng |
|---|---|---|
| `String[].class.getClassLoader() == null` | Mọi array class đều do bootstrap định nghĩa | String do bootstrap định nghĩa; mảng plugin reference type đi theo loader plugin |
| Hai array classes có cùng `getName()` | Hai mảng có cùng runtime type | Cần so component runtime class và defining loader; tên chữ không đủ |
| `Array.newInstance(widgetClass, 0)` thành công | Widget đã chạy static initializer | Tạo array không tự init class phần tử |
| `new Widget[3]` | JVM tạo ba Widget objects | JVM chỉ tạo ba ô tham chiếu mặc định null |
| Loader gọi `findClass("[L...;")` | Array class luôn có bytecode riêng trên ổ đĩa | JVM tạo array class trực tiếp; không có file array `.class` tương ứng |
| `int[]` là reference array object | Có thể cast thành `Object[]` | `int[]` là object nhưng component primitive, nên không phải `Object[]` |
| Hai loader nạp cùng file Widget.class | Kết quả vẫn cùng runtime class | Hai defining loaders riêng tạo hai component classes và hai array classes |
| `Class.forName("[Lplugin.Widget;", false, loader)` | Chắc chắn chạy Widget static initializer | Không yêu cầu initialization của Widget |
| `getComponentType()` của `Widget[][]` | Luôn trả `Widget.class` | Trả `Widget[].class`; cần lặp để đến kiểu cơ sở |

### Debug thực tế với plugin

Khi gặp `ClassCastException` hoặc lỗi tương thích API liên quan đến mảng trong hệ plugin/container:

1. In `array.getClass().getName()` để nhìn descriptor và số chiều.
2. In `array.getClass().getClassLoader()` để biết defining loader của array class.
3. Lặp `getComponentType()` để xác định component trực tiếp và component cơ sở; ở mỗi cấp xem `getClassLoader()`.
4. Ở hai phía giao tiếp host/plugin, so sánh **`Class<?>` bằng `==`**, không chỉ chuỗi tên.
5. Kiểm tra liệu cả hai loaders có vô tình định nghĩa lại cùng class API chung hay không. Parent-first cho các API chia sẻ giúp cùng sử dụng một runtime component type.
6. Nếu cần plugin class riêng mà array phải chuyển qua API chung, thiết kế boundary dùng `Object[]`, interface chung do parent định nghĩa hoặc dữ liệu trung gian một cách có kiểm tra kiểu; đừng ép cast mảng giữa hai plugin class khác defining loader.
7. Phân biệt lỗi **array store**, lỗi **cast**, lỗi **load/define class** và lỗi **initialization** để chọn phương án sửa đúng.

## 14. Câu hỏi tự kiểm tra

1. **Ai tạo lớp `Widget[]`?** JVM tạo trực tiếp; nó không đọc một file `Widget[].class`.
2. **`Widget` do loader L định nghĩa thì `Widget[]` có defining loader nào?** L.
3. **`int[]` có `getClassLoader()` là gì?** `null`, biểu diễn bootstrap đối với array class primitive.
4. **Component type của `String[][]` là gì?** `String[].class`; kiểu cơ sở là `String.class`.
5. **Hai lớp `p.Widget` cùng tên do L1 và L2 định nghĩa, `p.Widget[]` của chúng có cùng `Class<?>` không?** Không.
6. **Tên `Class.getName()` của hai mảng `p.Widget[]` ở hai loader có thể giống nhau không?** Có, cùng chuỗi `[Lp.Widget;` nhưng type identity khác.
7. **`new Widget[5]` có gọi constructor Widget 5 lần không?** Không; phần tử reference ban đầu là `null`.
8. **Tạo `Widget[]` có buộc chạy `Widget.<clinit>` không?** Không; thao tác tạo mảng tự nó không yêu cầu khởi tạo Widget.
9. **`int[]` có thể gán cho `Object` không? Có thể cast thành `Object[]` không?** Có thể gán cho `Object`; không thể cast thành `Object[]`.
10. **Khi biết `Class<?>` của component plugin, nên tạo mảng bằng gì?** `Array.newInstance(componentClass, length)`; JVM chọn array type đúng runtime component.
11. **`String[].class.getSuperclass()` là gì?** `Object.class`; array class đồng thời triển khai `Cloneable` và `Serializable`.
12. **Muốn biết chính xác mảng từ plugin loader nào, có đủ dùng `array.getClass().getName()` không?** Không; cần so đối tượng `Class` và xem `getClassLoader()`.

## Tài liệu chuẩn

- [Java Virtual Machine Specification — `5.3.3` Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.3): JVM tạo array classes và chọn defining loader từ component type.
- [Java Virtual Machine Specification — `5.3` Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): defining loader, initiating loader và runtime identity.
- [Java Language Specification — `10` Arrays](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html): kiểu mảng, thành phần, hiệp biến, kiểu runtime và array creation.
- [Java Language Specification — `12.4` Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): phân biệt array creation với active use cần class initialization.
- [Java SE 21 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isArray`, `getComponentType`, `getName`, `getTypeName`, `getClassLoader`.
- [Java SE 21 API — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Array.html): tạo array bằng reflection từ component `Class<?>`.

Khi làm việc với classloader và mảng, hãy xét đồng thời **kiểu phần tử thực ở runtime**, **số chiều mảng** và **defining loader của kiểu phần tử**. Ba thông tin này quyết định array type thực sự; **tên chuỗi của kiểu thôi chưa đủ**.
