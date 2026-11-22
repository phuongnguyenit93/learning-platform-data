# Giới hạn với primitive, void và array class khi khởi tạo và sinh mã (Java 15)

> **Mục tiêu:** Phân biệt những loại `Class<?>` mà Java dùng để mô tả **primitive**, `void`, **array** và **hidden class**; hiểu giới hạn của `MethodHandles.Lookup.defineHiddenClass` và `privateLookupIn`; biết cách **tạo array có phần tử thuộc hidden class** dù bản thân array class không bao giờ hidden. Nội dung thuộc mảng **Khởi tạo và sinh mã**, tập trung các cơ chế **vẫn đang áp dụng trên Java hiện đại**. Tất cả ví dụ chạy trên **Java 17+** và không cần bật preview hay dùng API legacy.

## 1. Một `Class<?>` không nhất thiết là một class file

`java.lang.Class` đại diện cho nhiều loại thực thể ở runtime: class/interface thông thường, primitive type, `void`, array class và hidden class. Nhưng API `Lookup.defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` (chuẩn hóa từ JDK 15 bằng JEP 371) chỉ định nghĩa được **non-array class/interface** từ **class-file bytes hợp lệ**.

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classFileBytes, true);

Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

Đoạn trên **không phải chương trình độc lập**. Nó giả định `lookup` có **full privilege access**, class file trong `classFileBytes` khai báo **cùng package với lookup class**, và bytes được JVM chấp nhận. `initialize=true` điều khiển việc khởi tạo class, **không tạo instance**.

Không thể đưa vào API này một primitive `int`, `boolean`, kiểu `void` hoặc bản thân `String[]` để “định nghĩa thành hidden class”. Các thực thể ấy có `Class<?>` mirrors nhưng không có một **non-array class file** riêng diễn tả chính chúng, như class `Generated.class`.

**Đừng nhầm:** Một hidden class vẫn **được phép có field/parameter/method return type** là primitive, array hoặc `void` ở các vị trí hợp lệ. Điều bị hạn chế là **loại thực thể được JVM định nghĩa từ bytes**, không phải mọi kiểu xuất hiện bên trong chữ ký của class đó.

## 2. Bốn phép kiểm tra type cần biết

- `Class.isPrimitive()`: kiểm tra primitive type **hoặc `void.class`**. Kết quả `void.class.isPrimitive() == true` là một chi tiết dễ bất ngờ.
- `Class.isArray()`: kiểm tra array class, bất kể element type là primitive hay reference.
- `Class.isHidden()`: kiểm tra **chính thực thể đang mô tả** có phải hidden class/interface không.
- `Class.getComponentType()`: trả `Class<?>` của component trực tiếp nếu đây là array class, còn non-array nhận `null`.

| Type mirror | Primitive? | Array? | Hidden? | Giải thích |
| --- | --- | --- | --- | --- |
| `int.class` | `true` | `false` | `false` | Primitive |
| `double.class` | `true` | `false` | `false` | Primitive |
| `void.class` | `true` | `false` | `false` | Void mirror, không có giá trị để lưu |
| `String.class` | `false` | `false` | `false` | Reference class bình thường |
| `int[].class` | `false` | `true` | `false` | Array class có component primitive |
| `String[].class` | `false` | `true` | `false` | Array class có component reference |
| `String[][].class` | `false` | `true` | `false` | Array nhiều chiều |
| `hiddenType` từ `defineHiddenClass` | `false` | `false` | `true` | Hidden class/interface |
| `hiddenType.arrayType()` | `false` | `true` | `false` | Array có element hidden |

**Hai kết luận cần ghi nhớ:** `int[].class` không phải primitive dù component là `int`; một array có **hidden element type** vẫn không phải hidden class. Do đó `arrayClass.isHidden()` không kiểm tra được liệu **component của array** có hidden hay không.

## 3. Primitive và void: không tạo được hidden primitive/void

Các primitive types gồm `boolean`, `byte`, `short`, `char`, `int`, `long`, `float` và `double`. Chúng có ngữ nghĩa được JVM xác định trực tiếp. `int.class` là đối tượng mô tả primitive, **không phải một class file `int.class`** mà chúng ta tự sinh rồi gọi `defineHiddenClass`.

`void.class` cũng là một mirror để diễn đạt **method không trả giá trị**. Java không cho phép:

~~~java
// Các dòng sau là cú pháp sai, chỉ minh họa điều KHÔNG được viết:
// void result;
// void[] values = new void[3];
// Object x = new void();
~~~

Trong khi:

~~~java
Class<?> noResult = void.class;
System.out.println(noResult.isPrimitive()); // true
~~~

là Java hợp lệ. **`isPrimitive() == true` không có nghĩa `void` có thể lưu instance hoặc làm array element**.

`java.lang.Void` là **một reference class** khác với `void.class`. `Void[]` là array type về mặt cú pháp; `void[]` không tồn tại. Không lấy sự tương tự tên gọi làm căn cứ cho bộ sinh bytecode hoặc phản chiếu.

## 4. JVM tạo array class theo component type

Với:

~~~java
int[] numbers = new int[2];
String[] names = new String[2];
~~~

JVM tạo/nhận diện array classes từ **component types**. Cơ chế này khác việc nạp một class file có tên `SomeClass.class`. `Class<?>` của `int[]` hay `String[]` tồn tại ở runtime, nhưng bản thân array class **không có một class-file độc lập** để `Lookup.defineHiddenClass` định nghĩa.

Javadoc `Class` nói rõ: một hidden class/interface **không bao giờ là array class**, nhưng **có thể làm element type của array**. Vì vậy:

- Cần **class mới**? Sinh class-file bytes của **non-array class/interface** rồi dùng `defineHiddenClass` với lookup hợp lệ.
- Cần **array mới**? Dùng `new T[n]` khi `T` viết được trong source, hoặc `java.lang.reflect.Array.newInstance(componentClass, n)` khi biết type qua `Class<?>` lúc runtime.
- Chỉ cần **Class của array type**? Dùng `componentClass.arrayType()` (API ổn định từ Java 12).
- Đừng chế bytes từ tên `[I` hoặc `[Ljava/lang/String;` rồi kỳ vọng `defineHiddenClass` tạo ra array class.

`defineHiddenClass` nhận **`byte[]`**, không có overload chấp nhận `Class<?>` như `String[].class`. Dù có bytes hợp lệ cho một class tự viết có **field kiểu `String[]`**, thực thể được định nghĩa vẫn là **class tự viết**, không phải bản thân kiểu `String[]`.

## 5. Tạo array có component là hidden class

Giả sử đã có:

~~~java
Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

Vì hidden class không có binary name bình thường để tham chiếu trong Java source ở nơi khác, không thể đơn giản viết `new HiddenType[2]` với một tên `HiddenType` chưa được khai báo. Dùng reflection:

~~~java
Object array = java.lang.reflect.Array.newInstance(hiddenType, 2);
Class<?> arrayType = array.getClass();

System.out.println(arrayType.isArray()); // true
System.out.println(arrayType.isHidden()); // false
System.out.println(arrayType.getComponentType() == hiddenType); // true
System.out.println(arrayType.getComponentType().isHidden()); // true
~~~

**Không mâu thuẫn:** hidden class thực sự có `isHidden() == true`, còn array class được JVM tạo từ nó có `isHidden() == false`. Hai đối tượng `Class<?>` đang mô tả **hai type khác nhau**.

`Class.arrayType()` cho cùng array type mirror:

~~~java
Class<?> arrayType = hiddenType.arrayType();
~~~

Với cùng `hiddenType`, `Array.newInstance(hiddenType, 2).getClass() == hiddenType.arrayType()`. `arrayType()` **không tạo object array**, mà chỉ trả `Class<?>` của array type.

### Array nhiều chiều

~~~java
Class<?> oneDim = hiddenType.arrayType();
Class<?> twoDim = oneDim.arrayType();

System.out.println(oneDim.isArray()); // true
System.out.println(twoDim.isHidden()); // false
System.out.println(twoDim.getComponentType() == oneDim); // true
System.out.println(twoDim.getComponentType().getComponentType()
        == hiddenType); // true
~~~

Đây là đoạn **trong method đã có hiddenType**. `getComponentType()` chỉ đi **một mức**: với mảng hai chiều nó trả về mảng một chiều, không trực tiếp trả element type cuối.

## 6. Ví dụ Java 17+ hoàn chỉnh: từ class bytes đến hidden array

Ví dụ dùng **hai source files**, không cần thư viện sinh bytecode ngoài JDK:

~~~text
demo/
  generation/
    Generated.java
    HiddenKindDemo.java
~~~

### `demo/generation/Generated.java`

~~~java
package demo.generation;

public class Generated {
    private final int number;

    public Generated(int number) {
        this.number = number;
    }

    public int value() {
        return number;
    }
}
~~~

Class này có **constructor và method dùng primitive `int`**, nhưng bản thân nó là một **reference class** có class-file hợp lệ, nên được phép định nghĩa thành hidden class khi đủ quyền và đúng package.

### `demo/generation/HiddenKindDemo.java`

~~~java
package demo.generation;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenKindDemo {
    static String checkPrivateLookup(Class<?> type, MethodHandles.Lookup source) {
        try {
            MethodHandles.privateLookupIn(type, source);
            return "OK";
        } catch (IllegalArgumentException e) {
            return "IllegalArgumentException";
        } catch (IllegalAccessException e) {
            return "IllegalAccessException";
        }
    }

    static String tryArray(Class<?> component) {
        try {
            return String.valueOf(Array.newInstance(component, 2)
                    .getClass().isArray());
        } catch (IllegalArgumentException e) {
            return "IllegalArgumentException";
        }
    }

    public static void main(String[] args) throws Throwable {
        Class<?> primitive = int.class;
        Class<?> nothing = void.class;
        Class<?> primitiveArray = int[].class;
        Class<?> referenceArray = String[].class;

        System.out.println("intPrimitive=" + primitive.isPrimitive());
        System.out.println("voidPrimitive=" + nothing.isPrimitive());
        System.out.println("voidName=" + nothing.getName());
        System.out.println("intHidden=" + primitive.isHidden());
        System.out.println("voidHidden=" + nothing.isHidden());
        System.out.println("intArrayHidden=" + primitiveArray.isHidden());
        System.out.println("stringArrayHidden=" + referenceArray.isHidden());
        System.out.println("arrayIsPrimitive=" + primitiveArray.isPrimitive());
        System.out.println("primitiveArrayType="
                + (primitive.arrayType() == primitiveArray));
        System.out.println("intArrayComponent="
                + (primitiveArray.getComponentType() == primitive));
        System.out.println("voidArray=" + tryArray(nothing));

        MethodHandles.Lookup source = MethodHandles.lookup();
        System.out.println("privateInt="
                + checkPrivateLookup(primitive, source));
        System.out.println("privateVoid="
                + checkPrivateLookup(nothing, source));
        System.out.println("privateArray="
                + checkPrivateLookup(referenceArray, source));

        byte[] bytes = Files.readAllBytes(
                Path.of("out/demo/generation/Generated.class"));
        MethodHandles.Lookup hiddenLookup =
                source.defineHiddenClass(bytes, true);
        Class<?> hiddenType = hiddenLookup.lookupClass();
        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(void.class, int.class));
        MethodHandle value = hiddenLookup.findVirtual(
                hiddenType, "value", MethodType.methodType(int.class));
        Object instance = (Object) constructor.invoke(17);

        System.out.println("hiddenIsHidden=" + hiddenType.isHidden());
        System.out.println("instanceIsHidden=" + instance.getClass().isHidden());
        System.out.println("methodValue=" + (int) value.invoke(instance));

        Object array = Array.newInstance(hiddenType, 2);
        Array.set(array, 0, instance);
        Class<?> arrayType = array.getClass();
        System.out.println("hiddenArrayIsArray=" + arrayType.isArray());
        System.out.println("hiddenArrayIsHidden=" + arrayType.isHidden());
        System.out.println("componentIsHidden="
                + arrayType.getComponentType().isHidden());
        System.out.println("componentMatches="
                + (arrayType.getComponentType() == hiddenType));
        System.out.println("hiddenArrayTypeMatches="
                + (arrayType == hiddenType.arrayType()));
        System.out.println("arrayFirstValue="
                + (int) value.invoke(Array.get(array, 0)));
        System.out.println("hiddenNominal="
                + hiddenType.describeConstable().isPresent());
        System.out.println("hiddenArrayNominal="
                + arrayType.describeConstable().isPresent());
        System.out.println("arrayOfArrayIsHidden="
                + arrayType.arrayType().isHidden());
    }
}
~~~

### Lệnh biên dịch/chạy

Ở **thư mục chứa `demo`**:

~~~bash
javac --release 17 -encoding UTF-8 -d out demo/generation/Generated.java demo/generation/HiddenKindDemo.java
java -cp out demo.generation.HiddenKindDemo
~~~

`-d out` đưa `Generated.class` vào đúng đường dẫn chương trình đọc. Đây là Java 17 ổn định; không cần preview, reflection hack hay JDK internal API.

**Stdout đã kiểm chứng:**

~~~text
intPrimitive=true
voidPrimitive=true
voidName=void
intHidden=false
voidHidden=false
intArrayHidden=false
stringArrayHidden=false
arrayIsPrimitive=false
primitiveArrayType=true
intArrayComponent=true
voidArray=IllegalArgumentException
privateInt=IllegalArgumentException
privateVoid=IllegalArgumentException
privateArray=IllegalArgumentException
hiddenIsHidden=true
instanceIsHidden=true
methodValue=17
hiddenArrayIsArray=true
hiddenArrayIsHidden=false
componentIsHidden=true
componentMatches=true
hiddenArrayTypeMatches=true
arrayFirstValue=17
hiddenNominal=false
hiddenArrayNominal=false
arrayOfArrayIsHidden=false
~~~

### Giải thích nhóm kết quả

**Primitive và void:** `voidPrimitive=true` không có nghĩa `void` dùng được làm một array element. `int[].class.isPrimitive()` là `false`, vì array là reference type.

**Không phải hidden:** Primitive, void và array classes đều báo `isHidden=false`. `privateLookupIn` từ chối primitive/void/array targets bằng `IllegalArgumentException`, được kiểm chứng ở ba dòng `privateInt/privateVoid/privateArray`.

**Hidden class thực sự:** `Generated.class` được đọc thành bytes của non-array reference class, đúng package với `HiddenKindDemo`. `defineHiddenClass` tạo hidden class, `hiddenType.isHidden=true`; instance của nó cũng có class hidden và method trả `17`.

**Array của hidden:** `Array.newInstance(hiddenType, 2)` hợp lệ. Array **không hidden**, nhưng component chính là hidden class. Có thể dùng `Array.set` gán instance đúng kiểu, `Array.get` đọc instance rồi gọi `MethodHandle`.

**Nominal descriptor:** Hidden class và array có hidden component đều báo `describeConstable().isPresent()==false`. Chúng có runtime identity thật nhưng **không có tên/descriptor danh nghĩa** như một class thông thường để tra cứu lại.

## 7. `privateLookupIn` yêu cầu proper class, không phải primitive/void/array

`MethodHandles.privateLookupIn(targetClass, caller)` tạo lookup có private access khi target là **proper class** và các điều kiện quyền/module cho phép. Theo Javadoc hiện hành, nếu target là **primitive, void hoặc array class**, phương thức ném **`IllegalArgumentException`**:

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();

// Mỗi lời gọi sau ném IllegalArgumentException:
MethodHandles.privateLookupIn(int.class, caller);
MethodHandles.privateLookupIn(void.class, caller);
MethodHandles.privateLookupIn(String[].class, caller);
~~~

Đây là **mã minh họa**, không chạy ba lời gọi liên tiếp mà không có try/catch vì lời gọi đầu sẽ ném exception. Chương trình mục 6 bắt lỗi từng trường hợp để chứng minh kết quả.

**Đừng cố sửa loại target bằng `--add-opens` hoặc modifier `public`.** Module opens/lookup modes có ý nghĩa với **proper reference class**; chúng không biến `int`, `void` hoặc array class thành target có class body để nhận lookup.

Ngược lại, nếu target là class hợp lệ nhưng caller thiếu quyền hoặc module không cho phép, `privateLookupIn` có thể ném **`IllegalAccessException`** — lỗi khác hoàn toàn. Ngay cả sau khi có một lookup, `Lookup.defineHiddenClass` vẫn yêu cầu **full privilege access** và class-file package **trùng với lookup class**.

## 8. `void` là return type, không phải parameter hay array element

`MethodType` mô tả chữ ký method handles:

~~~java
MethodType valid =
        MethodType.methodType(void.class, int.class, int[].class);

System.out.println(valid.toMethodDescriptorString()); // (I[I)V
~~~

`(I[I)V` mô tả một method nhận `int` và `int[]`, trả `void`. Ở đây `void.class` **được phép làm return type**.

Nhưng một phương thức không thể có **tham số void**:

~~~java
try {
    MethodType.methodType(int.class, void.class);
} catch (IllegalArgumentException expected) {
    // void không thể làm parameter type.
}
~~~

Trong phần tạo hidden class của ví dụ:

~~~java
hiddenLookup.findConstructor(
        hiddenType, MethodType.methodType(void.class, int.class));
~~~

`void.class` nằm ở **MethodType dùng để tìm constructor** vì bytecode constructor không có return type bình thường. Constructor method handle **được tìm thấy** thực tế có return type là `hiddenType`, cho phép `invoke(17)` tạo instance. Không nhầm `void` trong mô tả constructor với một object kiểu void.

## 9. Hai API về array có ngoại lệ khác nhau với void

**`java.lang.reflect.Array.newInstance(...)`** tạo object array mới. **`Class.arrayType()`** trả `Class<?>` của một array type mà không tạo instance.

| Lời gọi | Kết quả |
| --- | --- |
| `Array.newInstance(int.class, 2)` | Tạo array `int[]` có 2 phần tử |
| `Array.newInstance(hiddenType, 2)` | Tạo array với element hidden |
| `Array.newInstance(void.class, 2)` | Ném **`IllegalArgumentException`** |
| `int.class.arrayType()` | Trả `int[].class` |
| `hiddenType.arrayType()` | Trả `Class<?>` của array có element hidden |
| `void.class.arrayType()` | Ném **`UnsupportedOperationException`** |

**Không gom hai lỗi thành một:** `void.class.arrayType()` không ném trực tiếp `IllegalArgumentException` theo hợp đồng của nó, dù cách triển khai JDK có thể dùng nguyên nhân sâu hơn liên quan đến reflection. **`Class.arrayType()` ném `UnsupportedOperationException`** cho component `void` hoặc array type vượt **255 chiều**.

### Ví dụ thứ hai độc lập: `TypesCheck.java`

~~~java
import java.lang.invoke.MethodType;

public class TypesCheck {
    public static void main(String[] args) {
        MethodType valid =
                MethodType.methodType(void.class, int.class, int[].class);
        System.out.println("signature=" + valid.toMethodDescriptorString());

        try {
            MethodType.methodType(int.class, void.class);
            System.out.println("voidParameter=UNEXPECTED");
        } catch (IllegalArgumentException expected) {
            System.out.println("voidParameter=IllegalArgumentException");
        }

        try {
            void.class.arrayType();
            System.out.println("voidArrayType=UNEXPECTED");
        } catch (UnsupportedOperationException expected) {
            System.out.println("voidArrayType=UnsupportedOperationException");
        }

        System.out.println("charArrayHidden=" + char[].class.isHidden());
        System.out.println("nestedArraysAreArrays="
                + (String[][].class.isArray()
                && String[][].class.getComponentType().isArray()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 TypesCheck.java
java TypesCheck
~~~

**Stdout đã xác minh:**

~~~text
signature=(I[I)V
voidParameter=IllegalArgumentException
voidArrayType=UnsupportedOperationException
charArrayHidden=false
nestedArraysAreArrays=true
~~~

Điều này làm rõ rằng **`void` hợp lệ ở return type nhưng không hợp lệ ở array element và parameter type**. `char[]` và `String[][]` là các array classes bình thường, không hidden.

## 10. `Class.describeConstable()`: array không hidden nhưng vẫn không nominal

Hidden class có runtime name **không phải binary name** thường. `Class.forName` không thể tái dựng nó bằng tên runtime. `Class.describeConstable()` cho hidden class trả `Optional.empty()`.

Với array của hidden class, kết quả cũng **trống**:

~~~java
Class<?> hidden = hiddenLookup.lookupClass();
Class<?> hiddenArray = hidden.arrayType();

System.out.println(hidden.describeConstable().isPresent());      // false
System.out.println(hiddenArray.describeConstable().isPresent()); // false
~~~

Lý do: danh tính array phụ thuộc **element type**. Dù bản thân array `isHidden=false`, element hidden không có nominal descriptor bình thường, nên array ấy cũng không có nominal descriptor có thể tái dựng.

Javadoc `Class.descriptorString()` có thể trả **chuỗi mô tả** hidden class hoặc array của nó, nhưng khi element hidden, chuỗi đó **không phải type descriptor danh nghĩa hợp lệ** cho việc `ClassDesc.ofDescriptor` tái tạo class. Đừng lưu tên hoặc descriptor runtime làm ID để nạp lại sau khi mất `Class<?>`.

Nếu framework cần dùng generated class về sau, giữ `Class<?>`, `MethodHandles.Lookup`, instance hoặc `MethodHandle` trong thời gian phù hợp. Nếu cần public API có tên ổn định, dùng **interface/class thông thường** làm điểm tương tác, với hidden implementation nằm phía sau.

## 11. Phân biệt class identity khi sinh nhiều lần

Hai lần `defineHiddenClass` từ **cùng class-file bytes** vẫn tạo **hai class identities khác nhau**:

~~~java
Class<?> first = lookup.defineHiddenClass(bytes, true).lookupClass();
Class<?> second = lookup.defineHiddenClass(bytes, true).lookupClass();

System.out.println(first == second); // false
System.out.println(first.arrayType() == second.arrayType()); // false
~~~

Đây là **mã minh họa trong method**, với `lookup` đủ quyền và `bytes` đúng package. Vì `first` và `second` là hai component classes khác nhau, **array classes của chúng cũng khác nhau**.

Instance của hidden class thứ nhất không tự trở thành instance của hidden class thứ hai dù method/fields giống nhau. `Array.set` vào array có component không tương thích có thể thất bại theo các quy tắc assignability của reflection.

Khi framework muốn giữ nhiều generated instances có cấu trúc hành vi chung, một **interface có tên bình thường** hoặc `List<Interface>` với type contract rõ sẽ phù hợp hơn là cố gộp vào mảng của một hidden class cụ thể.

## 12. Quy trình thiết kế code generator theo loại input

~~~text
Nhận yêu cầu tạo kiểu/giá trị
  |
  +-- Primitive hoặc void?
  |     -> Chỉ mô tả type trong chữ ký/field ở vị trí hợp lệ
  |     -> Không cố định nghĩa hidden primitive/void
  |
  +-- Array?
  |     -> Phân loại component; từ chối void
  |     -> Array.newInstance(component, count) để tạo object
  |     -> component.arrayType() nếu chỉ cần array Class
  |     -> Không truyền array descriptor cho defineHiddenClass
  |
  +-- Proper non-array class/interface?
        -> Sinh classfile bytes có package phù hợp
        -> Lấy Lookup đủ full privilege access
        -> defineHiddenClass(bytes, initialize, options)
        -> Giữ Class/Lookup/MethodHandle khi còn sử dụng
        -> Nếu cần mảng của hidden, tạo bằng Array.newInstance
~~~

**Cần kiểm tra thêm khi đi nhánh sinh class:** Đúng loại nonarray class/interface chưa đủ. Classfile phải hợp lệ, target JDK hỗ trợ classfile version, package trong bytes phải đúng với lookup class, quyền lookup đầy đủ và các điều kiện module/access cũng phải tuân thủ JVM. `ClassOption.NESTMATE` hay `STRONG` không có tác dụng biến primitive, void hoặc array class thành hidden class.

**An toàn:** Hidden class không phải sandbox. Chỉ định nghĩa bytecode do thành phần đáng tin tạo hoặc kiểm soát; không cho plugin bên ngoài sử dụng lookup đặc quyền một cách tùy tiện.

## 13. Những nhầm lẫn thường gặp

1. **“Có `Class<?>` nghĩa là có classfile bytes cho type đó.”** Sai với primitive, void và array class.
2. **“`void.class.isPrimitive() == false`.”** Sai: kết quả là `true` theo API.
3. **“`int[].class.isPrimitive() == true` vì element là int.”** Sai: array là reference type.
4. **“Array-of-hidden cũng có `isHidden() == true`.”** Sai: bản thân array luôn không hidden; kiểm tra component.
5. **“Không tạo được mảng chứa hidden instances.”** Sai: `Array.newInstance(hiddenType, n)` hợp lệ.
6. **“`Lookup.defineHiddenClass` nhận `String[].class`.”** Sai: signature nhận classfile `byte[]` cho nonarray class/interface.
7. **“Chỉ cần đổi tên bytes thành descriptor array là tạo array hidden.”** Sai: JVM tạo array classes theo component type, không qua class-file generator như vậy.
8. **“`void[]` giống `new int[0]`.”** Sai: một cái không có type hợp lệ; cái kia là array rỗng có component `int`.
9. **“Cả hai API tạo array với void đều ném `IllegalArgumentException`.”** Sai: `void.class.arrayType()` ném `UnsupportedOperationException`.
10. **“`privateLookupIn(int.class, ...)` được nếu thêm `--add-opens`.”** Sai: target primitive/void/array bị từ chối về loại type.
11. **“Hidden class không thể chứa primitive fields.”** Sai: `Generated` có field/constructor/method dùng `int` và được định nghĩa thành hidden.
12. **“`Class.arrayType()` đã tạo một array object.”** Sai: chỉ trả type mirror; phải dùng `Array.newInstance` để có object.
13. **“`Class.getComponentType()` trên array nhiều chiều cho element cuối.”** Sai: trả component trực tiếp; cần lặp.
14. **“`void.class` là `Void.class`.”** Sai: `void` và wrapper `java.lang.Void` là hai thực thể khác nhau.
15. **“`isHidden=false` nghĩa là array có nominal descriptor.”** Sai với array có element hidden.
16. **“Sinh từ cùng bytes thì các hidden classes interchangeable.”** Sai: mỗi lần define cho class identity riêng.

## 14. Bài tập và tiêu chí đạt

**Bài 1 — Nhận diện type.** Lập bảng ba cờ `isPrimitive`, `isArray`, `isHidden` với `int.class`, `void.class`, `int[].class` và `String.class`. **Đạt** khi hiểu vì sao `void` là primitive theo API nhưng không dùng làm element.

**Bài 2 — Sinh hidden class có primitive.** Chạy hai tệp của mục 6. **Đạt** khi thấy `hiddenIsHidden=true`, `instanceIsHidden=true`, `methodValue=17`; giải thích việc một class có field `int` không hề là hidden primitive.

**Bài 3 — Array chứa hidden.** Gọi `Array.newInstance(hiddenType, 2)` và lấy `getComponentType()`. **Đạt** khi thấy array không hidden nhưng component hidden; dùng `Array.get/set` đúng type.

**Bài 4 — `privateLookupIn` invalid target.** Dùng `int.class`, `void.class`, `String[].class`. **Đạt** khi từng trường hợp ném `IllegalArgumentException` và biết đây không phải vấn đề thiếu `opens`.

**Bài 5 — MethodType void.** Tạo `MethodType.methodType(void.class, int.class, int[].class)` và thử `void.class` làm parameter. **Đạt** khi descriptor là `(I[I)V` và việc có parameter void bị từ chối.

**Bài 6 — Hai API array.** So sánh `Array.newInstance(void.class, 2)` và `void.class.arrayType()`. **Đạt** khi biết hai loại exception là `IllegalArgumentException` và `UnsupportedOperationException` tương ứng.

**Bài 7 — Array nhiều chiều.** Tạo `hiddenType.arrayType().arrayType()`. **Đạt** khi biết cần `getComponentType()` hai lần mới tới hidden element.

**Bài 8 — Identity.** Định nghĩa hai hidden classes từ cùng bytes, rồi lấy array types của chúng. **Đạt** khi giải thích vì sao cả class và array types đều khác identity.

**Bài 9 — Nominal form.** Kiểm tra `describeConstable()` với hidden class và array có element hidden. **Đạt** khi cả hai trả empty và hiểu không thể dùng tên để nạp lại như class thường.

**Bài 10 — Kiến trúc generator.** Thiết kế hàm nhận `Class<?>` để quyết định tạo class hay array. **Đạt** khi không nhầm primitive/void/array với nonarray classfile, không dùng API reflection ngoài phạm vi, và xác định package/quyền lookup đúng.

## 15. Tài liệu chính thức còn hiệu lực

- [JEP 371 — Hidden Classes (Java 15)](https://openjdk.org/jeps/371): mục đích, mô hình và khả năng định nghĩa hidden classes.
- [Oracle Java SE 25 — Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `isPrimitive`, `isArray`, `isHidden`, `getComponentType`, `arrayType`, `describeConstable`, *Hidden Classes*.
- [Oracle Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, yêu cầu nonarray classfile, package và quyền lookup.
- [Oracle Java SE 25 — MethodHandles](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html): `privateLookupIn`, điều kiện target proper class và bảo vệ module.
- [Oracle Java SE 25 — Array](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Array.html): `newInstance`, `get` và `set`.
- [Oracle Java SE 25 — MethodType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html): return/parameter types và JVM method descriptors.
- [JVM Specification `5.3.3 — Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.3): array class được JVM tạo theo component type.

**Ghi nhớ:** Hidden class chỉ có thể là **non-array class/interface** được định nghĩa từ class-file bytes hợp lệ; không thể định nghĩa primitive, `void` hoặc array class theo cách ấy. **Array có element type là hidden class vẫn hoàn toàn hợp lệ**, nhưng bản thân array có `isHidden() == false`. Chọn đúng API dựa vào loại `Class<?>`, xác định đúng vai trò của `void` và kiểm chứng ngoại lệ, component type, class identity ở runtime.
