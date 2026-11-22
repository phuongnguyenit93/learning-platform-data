# Kiểu nguyên thủy, void và giới hạn của loadClass

## 1. Vấn đề: tại sao có int.class nhưng không loadClass("int")?

Trong Java, **kiểu** và **class có thể được nạp từ bytecode** không phải cùng một tập hợp. Ngôn ngữ Java có tám kiểu nguyên thủy (*primitive types*): `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. JVM còn biểu diễn `void` cho trường hợp phương thức không trả giá trị. Trong khi đó, `java.lang.ClassLoader.loadClass(String)` được thiết kế để tìm class/interface theo **binary name**, ví dụ `java.lang.String` hoặc `com.example.Account`.

Do đó:

- `int.class`, `boolean.class` và `void.class` là các biểu thức Java hợp lệ, trả về đối tượng `Class<?>` đặc biệt do VM hỗ trợ.
- `ClassLoader.loadClass("int")` hoặc `Class.forName("int")` không phải API để nhận đại diện của primitive `int`.
- `ClassLoader.loadClass("void")` hoặc `Class.forName("void")` không phải API để nhận `void.class`.
- `Integer.class` là **wrapper class**, khác `int.class`; `Void.class` là wrapper/reference class, khác `void.class`.
- `int[]` là một **array reference type**: dù phần tử là primitive, bản thân mảng là object và có array class do JVM tạo khi cần.

Bài này làm rõ ngữ nghĩa đó, sự khác biệt giữa `ClassLoader.loadClass` và `Class.forName`, cũng như cách reflection và JVM descriptors biểu diễn primitive, `void` và mảng.

## 2. Tám primitive types và Class<?> đại diện

Các kiểu primitive có tên và descriptor như sau:

| Kiểu Java | JVM descriptor | Ví dụ giá trị |
|---|---|---|
| `boolean` | `Z` | `true` |
| `byte` | `B` | `(byte) 1` |
| `short` | `S` | `(short) 2` |
| `char` | `C` | `'A'` |
| `int` | `I` | `42` |
| `long` | `J` | `42L` |
| `float` | `F` | `3.5f` |
| `double` | `D` | `3.5d` |

Primitive value không phải một object có identity theo cách của reference type. Khi boxing, Java có thể biểu diễn một giá trị bằng một object wrapper như `Integer`, nhưng `Integer` và `int` là hai kiểu khác nhau.

Với reflection, `Class<?>` vẫn đại diện cho primitive types. Java API chuẩn cung cấp:

```java
Class<?> intType = int.class;
Class<?> longType = long.class;
Class<?> boolType = boolean.class;

boolean same = int.class == Integer.TYPE;  // true
boolean wrapper = int.class == Integer.class; // false
```

`Integer.TYPE` là trường `public static final Class<Integer> TYPE`? **Không nên suy ra kiểu generic cụ thể của trường đó**; điều cần dùng là giá trị `Class<?>` đại diện `int`. Java API định nghĩa trường `TYPE` trong wrapper để trả về đối tượng `Class` của primitive tương ứng.

### Vì sao Class có thể đại diện primitive?

`Class` là API phản chiếu của JVM; nó không chỉ đại diện class/interface được nạp từ file `.class`. JVM có các object `Class` dựng sẵn cho tám primitive và `void`. Các object này **không được tạo từ những file có tên `int.class`, `boolean.class`, `void.class` trên class path**.

Điều này giải thích được cả hai sự thật cùng lúc:

```java
System.out.println(int.class.isPrimitive()); // true
System.out.println(int.class.getClassLoader()); // null
```

Trong API `Class.getClassLoader()`, primitive và `void` trả `null`. Đó **không phải bằng chứng có bootstrap loader đã đọc một file int.class**. Giá trị `null` còn có ý nghĩa biểu diễn bootstrap loader đối với các class thực sự được bootstrap định nghĩa như `java.lang.String` trên JDK thông thường. Cùng kết quả API có thể tương ứng các cơ chế hình thành type khác nhau.

## 3. void đặc biệt như thế nào?

`void` là kiểu đặc biệt biểu thị không có giá trị trả về. Nó có thể xuất hiện trong khai báo method:

```java
public static void log(String message) {
    System.out.println(message);
}
```

Nhưng không thể viết `void value;`, `new void[3]` hoặc dùng `void` làm tham số method trong Java source.

JDK vẫn cung cấp:

```java
Class<?> voidType = void.class;
Class<?> viaWrapper = Void.TYPE;
System.out.println(voidType == viaWrapper); // true
System.out.println(void.class.isPrimitive()); // true
```

Theo Java `Class.isPrimitive()`, có **chín đối tượng `Class` dựng sẵn** cho tám primitive và `void`; cả chín đều trả `true` với `isPrimitive()`. Điều đó **không có nghĩa** một biến có thể chứa giá trị `void` như chứa `int`.

Phân biệt:

| Biểu thức | Đại diện cho |
|---|---|
| `void.class` | Kiểu return đặc biệt `void` |
| `Void.TYPE` | Cùng đối tượng `Class` với `void.class` |
| `Void.class` | Reference class `java.lang.Void` |
| `int.class` | Primitive `int` |
| `Integer.class` | Reference class `java.lang.Integer` |

Wrapper `Void` tồn tại trong thư viện chuẩn. `ClassLoader.loadClass("java.lang.Void")` có thể tìm class đó, nhưng đây **không phải** cách lấy `void.class`.

## 4. Giới hạn thực sự của ClassLoader.loadClass(String)

Theo Java SE 17 API, `ClassLoader.loadClass(String)` nhận **binary name của class/interface**, không phải mã descriptor của JVM và không phải Java source expression bất kỳ.

Ví dụ hợp lệ:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> s = loader.loadClass("java.lang.String");
Class<?> list = loader.loadClass("java.util.ArrayList");
```

Bảng sau dễ nhớ:

| Chuỗi truyền vào | Có phải tên class/interface phù hợp? | Ghi chú |
|---|---|---|
| `java.lang.String` | Có | Binary name của class |
| `java.util.Map$Entry` | Có | Binary name của nested interface |
| `com.example.Service` | Có nếu class đó tồn tại và loader thấy được | Tìm qua loader được chọn |
| `int` | Không | Primitive type, không có ordinary class file tên này |
| `void` | Không | Kiểu return đặc biệt |
| `I` | Không | JVM descriptor của `int` |
| `Ljava/lang/String;` | Không | JVM field descriptor của class |
| `java/lang/String` | Không | Internal name, không phải binary name |
| `[I` | Không thuộc binary-name contract của `loadClass` | Dùng `Class.forName("[I")` hoặc `int[].class` cho mảng |

`loadClass(name)` tương đương `loadClass(name, false)`. Với implementation mặc định, class loader kiểm tra class đã được nạp, thử nhờ parent (hoặc bootstrap nếu parent là `null`), rồi tới `findClass`. Custom loader có thể override lookup, nhưng không làm primitive biến thành ordinary class file.

### Khi loadClass thất bại

Nếu class không nằm trong nguồn tìm kiếm mà loader nhìn thấy, kết quả thông thường là `ClassNotFoundException`:

```java
try {
    loader.loadClass("int");
} catch (ClassNotFoundException ex) {
    System.out.println("Không có class int để load");
}
```

Đây là **đoạn minh họa** cần có biến `loader` trong scope. Nếu muốn chương trình hoàn chỉnh, dùng ví dụ ở phần 7.

Lỗi trên không cho thấy JVM thiếu kiểu `int`. Muốn lấy `Class<?>` của primitive, dùng `int.class` hoặc `Integer.TYPE`.

## 5. Class.forName và các tên mảng: ngoại lệ cần nắm

`Class.forName("java.lang.String")` là cách thường dùng để lấy `Class<?>` từ binary name của một class. Nhưng `Class.forName("int")`, `Class.forName("void")` không biến các từ khóa Java thành type tokens; các lời gọi đó sẽ ném `ClassNotFoundException` trên JDK tiêu chuẩn.

`Class.forName` còn hỗ trợ **tên mảng** theo cú pháp đặc biệt:

```java
Class<?> primitiveArray = Class.forName("[I");
Class<?> referenceArray =
        Class.forName("[Ljava.lang.String;");
```

Kết quả:

- `primitiveArray == int[].class` là `true`.
- `referenceArray == String[].class` là `true`.
- `Class.forName("[[I")` lấy `int[][].class`.
- `Class.forName("[Ljava.lang.String;")` dùng **dấu chấm** trong tên element class.
- `Class.forName("[Ljava/lang/String;")` không phải cú pháp chuẩn để tra cứu mảng tham chiếu này qua `Class.forName`.

Lý do là các array class có **cách đặt tên runtime** riêng mà `Class.getName()` cũng sử dụng. Với ordinary class/interface, `Class.forName` vẫn dùng binary name.

### So sánh Class.forName và loadClass

| API | Trường hợp class thường | Primitive/void | Mảng |
|---|---|---|---|
| `SomeType.class` | Dùng khi biết kiểu ở compile time | `int.class`, `void.class` hợp lệ | `int[].class`, `String[].class` hợp lệ |
| `Class.forName(name)` | Nhận binary name | Không diễn giải `"int"`, `"void"` | Nhận tên mảng như `"[I"`, `"[Ljava.lang.String;"` |
| `ClassLoader.loadClass(name)` | Nhận binary name class/interface | Không có ordinary class file primitive/void | Không dùng array descriptor như hợp đồng API chuẩn |
| `Array.newInstance(component, n)` | Không để load class thường | Có thể dùng primitive component như `int.class` | Tạo array object, array class được runtime cung cấp |

`Class.forName(name, initialize, loader)` còn cho phép chọn cờ initialization và loader dùng để lookup. `initialize=false` **không** biến primitive-name lookup thành hợp lệ; `loader=null` thường chỉ bootstrap lookup đối với class.

## 6. Mảng primitive là object, không phải primitive

Một trong những điểm quan trọng nhất:

```java
int count = 3;        // primitive value
int[] values = new int[3]; // reference tới array object
```

Mảng `int[]` là **reference type** và là object của JVM. Có thể chứng minh:

```java
System.out.println(int.class.isPrimitive());     // true
System.out.println(int[].class.isPrimitive());   // false
System.out.println(int[].class.isArray());       // true
System.out.println(values instanceof Object);   // true
System.out.println(int[].class.getComponentType() == int.class); // true
```

Đoạn mã trên cần biến `values` được khai báo như ví dụ. Nếu cần tạo mảng bằng reflection:

```java
Object array = java.lang.reflect.Array.newInstance(int.class, 3);
System.out.println(array.getClass() == int[].class); // true
```

Không có mảng `void[]`. `Array.newInstance(void.class, 3)` không được phép và ném `IllegalArgumentException`.

### Ai tạo array class?

Java API `ClassLoader` quy định **array classes được runtime tạo khi cần**, thay vì loader tạo từ dữ liệu bytecode của một ordinary class file. `Class.getClassLoader()` của array class tương ứng với loader của **element type** nếu là reference type; nếu element type là primitive thì kết quả là `null`.

Ví dụ:

- `String[].class.getClassLoader()` thường trả `null` trên JDK 17, vì `String` được bootstrap định nghĩa.
- `int[].class.getClassLoader()` trả `null`, nhưng không có nghĩa bootstrap đã đọc `[I.class`.
- Nếu `plugin.Message` do loader P định nghĩa, array class `plugin.Message[]` tương ứng có loader theo element class đó. Hai plugin loaders định nghĩa hai `plugin.Message` riêng có thể dẫn tới hai array types khác nhau.
- `int[][]` vẫn là reference type, có tên dạng `[[I` và component type trực tiếp `int[]`.

## 7. Ví dụ Java 17 đầy đủ: phân biệt primitive, void, array và loader

Tạo file **`PrimitiveAndLoaderDemo.java`**:

```java
public class PrimitiveAndLoaderDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader app = PrimitiveAndLoaderDemo.class.getClassLoader();

        System.out.println("int primitive: " + int.class.isPrimitive());
        System.out.println("void primitive: " + void.class.isPrimitive());
        System.out.println("Integer primitive: "
                + Integer.class.isPrimitive());
        System.out.println("int equals TYPE: "
                + (int.class == Integer.TYPE));
        System.out.println("void equals TYPE: "
                + (void.class == Void.TYPE));

        System.out.println("int loader null: "
                + (int.class.getClassLoader() == null));
        System.out.println("void loader null: "
                + (void.class.getClassLoader() == null));

        System.out.println("int descriptor: "
                + int.class.descriptorString());
        System.out.println("void descriptor: "
                + void.class.descriptorString());

        System.out.println("int[] array: " + int[].class.isArray());
        System.out.println("int[] primitive: "
                + int[].class.isPrimitive());
        System.out.println("int[] loader null: "
                + (int[].class.getClassLoader() == null));
        System.out.println("int[] component is int: "
                + (int[].class.getComponentType() == int.class));

        System.out.println("Find [I: "
                + (Class.forName("[I") == int[].class));
        System.out.println("Find String[]: "
                + (Class.forName("[Ljava.lang.String;")
                        == String[].class));

        try {
            Class.forName("int");
            System.out.println("Unexpected forName success");
        } catch (ClassNotFoundException expected) {
            System.out.println("forName(int): not found");
        }

        try {
            app.loadClass("void");
            System.out.println("Unexpected loadClass success");
        } catch (ClassNotFoundException expected) {
            System.out.println("loadClass(void): not found");
        }

        System.out.println("String class by loader: "
                + (app.loadClass("java.lang.String") == String.class));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên trên class path thông thường:

```bash
javac PrimitiveAndLoaderDemo.java
java PrimitiveAndLoaderDemo
```

Stdout trên JDK 17 chuẩn:

```text
int primitive: true
void primitive: true
Integer primitive: false
int equals TYPE: true
void equals TYPE: true
int loader null: true
void loader null: true
int descriptor: I
void descriptor: V
int[] array: true
int[] primitive: false
int[] loader null: true
int[] component is int: true
Find [I: true
Find String[]: true
forName(int): not found
loadClass(void): not found
String class by loader: true
```

**Cách đọc kết quả:**

1. `int.class` và `void.class` được VM hỗ trợ, còn `Integer.class` là reference class.
2. `int.class == Integer.TYPE` và `void.class == Void.TYPE` đều đúng.
3. `getClassLoader() == null` đối với primitive và `void` không nói rằng có một class file tương ứng đã được bootstrap tìm đọc.
4. `int[]` là array reference type, nhận `Class<?>` của riêng nó.
5. `Class.forName("[I")` và `Class.forName("[Ljava.lang.String;")` hợp lệ do tên mảng theo API.
6. Lookup `"int"` và `"void"` bằng API tìm class theo binary name không cho ra primitive/void tokens.

Nếu dùng custom system class loader với chính sách không chuẩn, một vài phép lookup có thể hoạt động khác. Đoạn mẫu chủ ý sử dụng cách chạy mặc định trên JDK 17.

## 8. JVM descriptor khác Class.getName như thế nào?

Bytecode dùng **field descriptor** và **method descriptor** để biểu diễn kiểu. Với Java SE 17, `Class.descriptorString()` là cách lấy descriptor của một kiểu từ đối tượng `Class<?>`.

| Kiểu | `Class.getName()` | `Class.descriptorString()` |
|---|---|---|
| `int` | `int` | `I` |
| `long` | `long` | `J` |
| `boolean` | `boolean` | `Z` |
| `void` | `void` | `V` |
| `String` | `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` | `[I` |
| `int[][]` | `[[I` | `[[I` |
| `String[]` | `[Ljava.lang.String;` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava.lang.String;` | `[[Ljava/lang/String;` |

Trong field descriptor, `I` biểu diễn `int`. `V` chỉ hợp lệ làm **method return type**, không phải field type hoặc method parameter type. Một method:

```java
public static void print(int count, String[] labels) {
}
```

có descriptor:

```text
(I[Ljava/lang/String;)V
```

Phần trong `(...)` có một tham số `int` và một tham số `String[]`; `V` sau `)` biểu diễn không có giá trị trả về.

### Phân biệt ba cách viết tên String

- `java.lang.String`: binary name thường dùng với `loadClass`.
- `java/lang/String`: internal name trong metadata JVM.
- `Ljava/lang/String;`: field descriptor của reference type `String`.

Không truyền `Ljava/lang/String;` vào `loadClass` rồi kỳ vọng Java tự hiểu thành `java.lang.String`.

## 9. Ví dụ Java 17: phản chiếu method void mà không dùng loadClass("void")

Tạo file **`VoidMethodDemo.java`**:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class VoidMethodDemo {
    public static void ping(int count) {
    }

    public static void main(String[] args) throws Exception {
        Method method = VoidMethodDemo.class.getDeclaredMethod(
                "ping", int.class);

        System.out.println("Return type is void: "
                + (method.getReturnType() == void.class));

        MethodType type = MethodType.methodType(
                method.getReturnType(), method.getParameterTypes());

        System.out.println("Method descriptor: "
                + type.descriptorString());
    }
}
```

Chạy:

```bash
javac VoidMethodDemo.java
java VoidMethodDemo
```

Stdout:

```text
Return type is void: true
Method descriptor: (I)V
```

Ví dụ cho thấy reflection lấy kiểu trả về `void` bằng `void.class`; `MethodType` biểu diễn được `void` trong vị trí **return**. Không phải có một ordinary class `void` được nạp bằng `ClassLoader.loadClass`.

## 10. Những giới hạn khác của loadClass cần nhớ

### Không tạo instance

`loader.loadClass("com.example.Service")` trả về `Class<?>`; không tự chạy constructor để tạo một `Service` instance. Phải dùng một cơ chế tạo đối tượng phù hợp mới có instance.

### Không mặc định khởi tạo class

`ClassLoader.loadClass(String)` tương đương `loadClass(name, false)`, tức không yêu cầu resolution bằng cờ `resolve=true` và cũng **không yêu cầu class initialization như active use**. Loading, linking, initialization là các mốc khác nhau. `Class.forName(name)` overload một tham số thông thường yêu cầu initialization cho class được tìm.

### Không bỏ qua visibility hoặc module boundaries

Loader không nhìn thấy class/module cần thiết có thể thất bại `ClassNotFoundException`. Lấy `Class<?>` không chứng minh method, constructor hoặc field của class đó truy cập được từ mọi nơi; access checks và JPMS vẫn áp dụng.

### Không biến wrapper thành primitive

`loadClass("java.lang.Integer")` trả về wrapper `Integer.class`, không trả `int.class`. Boxing/unboxing là quy tắc của ngôn ngữ và runtime, không phải “dịch tên” trong class loader.

### Không quyết định mọi giai đoạn linking

Một class có thể được tìm nhưng sau đó lỗi resolution, preparation hoặc initialization khi được dùng, ví dụ thiếu dependency, `NoClassDefFoundError`, `ExceptionInInitializerError`, `LinkageError`. `loadClass` thành công chưa đảm bảo toàn bộ hành vi ứng dụng thành công.

### Không tạo array class từ file .class

Array classes do runtime tạo. Dùng `int[].class`, `Class.forName("[I")` hoặc `Array.newInstance(int.class, length)`; không tự suy rằng tồn tại file `[I.class` hoặc rằng `loadClass("[I")` là contract để truy cập mảng.

## 11. Những lỗi phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Có `int.class` tức có file `int.class`.” | Primitive Class objects do VM tạo sẵn, không cần bytecode class file thông thường. |
| “`Class.forName("void")` phải bằng `Void.class`.” | `Void.class` là wrapper reference class; `void.class` và `Void.TYPE` mới là đại diện cho void. |
| “`int.class` và `Integer.class` là cùng kiểu.” | Một primitive, một reference wrapper; `==` là false. |
| “`void.class.isPrimitive()` chắc phải false.” | API tính cả void trong chín primitive-related Class objects; kết quả true. |
| “`int[]` là primitive vì element là int.” | Array là reference type; `int[].class.isPrimitive()` là false. |
| “Mọi `getClassLoader() == null` chứng minh bootstrap đã đọc class file.” | Primitive/void và primitive arrays cũng trả null theo quy tắc API nhưng không có ordinary class file tương ứng. |
| “`loadClass("[I")` là API chuẩn nạp array.” | `loadClass` nhận binary name class/interface; dùng `Class.forName("[I")` để truy cập array class theo cú pháp được hỗ trợ. |
| “`loadClass` thành công đã gọi static initializer.” | Loading và initialization là hai việc khác nhau. |
| “JVM descriptor `Ljava/lang/String;` là binary name.” | Binary name của class đó là `java.lang.String`. |
| “Có thể khai báo `void[]` hoặc `void` parameter.” | Void chỉ dùng đúng ngữ cảnh method return và API type token, không là array component hay parameter type. |

## 12. Bài tập tự kiểm tra

**Câu 1.** `int.class` tồn tại, nhưng vì sao `ClassLoader.loadClass("int")` không phải cách hợp lệ để truy cập nó?

**Đáp án:** Primitive `int` không phải class/interface có bytecode `.class` để loader tìm theo binary name. `int.class` là đối tượng Class đặc biệt của VM; có thể dùng `Integer.TYPE`.

**Câu 2.** `void.class.isPrimitive()` in gì? Có thể tạo `new void[3]` không?

**Đáp án:** In `true` theo `Class.isPrimitive()`. Không, `void[]` không phải array type hợp lệ.

**Câu 3.** `Integer.TYPE == Integer.class` có đúng không?

**Đáp án:** Không. `Integer.TYPE == int.class` là true; `Integer.class` là wrapper reference class.

**Câu 4.** `Class.forName("[I")` trả kiểu gì? `Class.forName("int")` có trả cùng kiểu đó không?

**Đáp án:** `Class.forName("[I")` trả `int[].class`. `Class.forName("int")` tìm không được primitive theo binary-name lookup.

**Câu 5.** `String[].class.getName()` và `String[].class.descriptorString()` khác nhau chỗ nào?

**Đáp án:** Cái thứ nhất là `[Ljava.lang.String;` với dấu chấm; cái thứ hai là `[Ljava/lang/String;` với dấu gạch chéo trong internal name.

**Câu 6.** Khi `int[].class.getClassLoader() == null`, có thể kết luận một file `[I.class` nằm trong bootstrap class path không?

**Đáp án:** Không. Array class được runtime tạo; primitive array có null loader theo quy tắc JVM/API.

**Câu 7.** Descriptor của method `void notify(int count, String[] names)` là gì?

**Đáp án:** `(I[Ljava/lang/String;)V`. `I` cho `int`, `[Ljava/lang/String;` cho `String[]` và `V` là kiểu trả về `void`.

**Câu 8.** Vì sao `ClassLoader.loadClass("java.lang.Integer")` không thay thế được `int.class`?

**Đáp án:** Nó lấy định nghĩa của wrapper class `Integer`, vốn là một reference type khác với primitive `int`.

## 13. Ghi nhớ và tài liệu tham khảo

- **Tám primitive + void** có `Class<?>` đặc biệt do VM tạo; không có binary-name class files tương ứng để nạp qua `loadClass("int")` hoặc `loadClass("void")`.
- **Array** là reference type dù element primitive. Array classes do runtime tạo; `int[]` khác `int`.
- **ClassLoader.loadClass(String)** tìm class/interface bằng binary name và chịu loader visibility; không tự tạo instance hoặc yêu cầu initialization.
- **Class.forName** hỗ trợ ordinary class binary names và tên array như `[I`, `[Ljava.lang.String;`, nhưng không diễn giải primitive token như `"int"`.
- **Descriptor** của primitive `int` là `I`, của `void` ở method return là `V`; khác Java source spelling và binary name.

Nguồn chính thức:

1. [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isPrimitive`, `getName`, `getClassLoader`, `forName`, `descriptorString`.
2. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, cách JVM tạo array classes.
3. [Java SE 17 — Void](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Void.html): `Void.TYPE` và wrapper class.
4. [JVMS 17 — Types and Values](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): primitive, reference và array types.
5. [JVMS 17 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): field/method descriptor, cú pháp primitive/void.