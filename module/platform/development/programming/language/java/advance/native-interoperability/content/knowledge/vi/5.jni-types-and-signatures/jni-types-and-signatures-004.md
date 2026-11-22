# Đọc bộ mô tả kiểu cho lớp, mảng và phương thức trong JNI

## 1. Tại sao cần đọc bộ mô tả kiểu?

**Bộ mô tả kiểu (type descriptor)** là chuỗi ký tự theo cú pháp của Java Virtual Machine (JVM), được ghi trong `.class` để biểu diễn kiểu trường và kiểu phương thức. JNI (Java Native Interface) sử dụng cùng quy ước, thường gọi là **type signature**, khi tìm trường hoặc phương thức Java từ mã C/C++.

Ví dụ:

- `int` → `I`.
- `java.lang.String` → `Ljava/lang/String;`.
- `int[][]` → `[[I`.
- `long calculate(int count, String name, int[] values)` → `(ILjava/lang/String;[I)J`.

Descriptor là chuỗi rất ngắn nhưng phải **khớp chính xác**: thiếu dấu `;`, sai một ký tự kiểu hoặc sai số chiều mảng có thể khiến `GetFieldID` hoặc `GetMethodID` tìm không thấy thành phần. Nội dung này thuộc phần **Kiểu và chữ ký JNI**: hiểu cách đọc, tự tạo, kiểm tra và dùng các descriptor trong lời gọi JNI.

Phân biệt các cách viết của cùng kiểu:

| Biểu diễn | Ví dụ với `String` | Mục đích |
| --- | --- | --- |
| Tên Java source | `java.lang.String` | Viết mã Java |
| Internal name | `java/lang/String` | Gọi `FindClass` cho lớp thông thường và biểu diễn tên lớp trong bytecode |
| Type/field descriptor | `Ljava/lang/String;` | Mô tả kiểu đối tượng trong trường, tham số, kết quả trả về |
| Method descriptor | `(I)Ljava/lang/String;` | Phương thức nhận `int` và trả `String` |

Descriptor không chứa tên tham số, không chứa code Java hay địa chỉ thư viện native. Trong JNI, tên trường/phương thức và chuỗi `sig` là **hai đối số riêng**.

## 2. Bảng các kiểu nguyên thủy

Với primitive type, descriptor là một ký tự duy nhất:

| Kiểu Java | Descriptor | Kiểu C trong JNI |
| --- | --- | --- |
| `boolean` | `Z` | `jboolean` |
| `byte` | `B` | `jbyte` |
| `char` | `C` | `jchar` |
| `short` | `S` | `jshort` |
| `int` | `I` | `jint` |
| `long` | `J` | `jlong` |
| `float` | `F` | `jfloat` |
| `double` | `D` | `jdouble` |
| `void` | `V` | `void` |

Cần nhớ:

- `J` mới là descriptor của `long`; `L` mở đầu **kiểu lớp/interface**.
- `B` là `byte`, còn `Z` là `boolean`.
- `V` được phép làm **kiểu trả về phương thức** nhưng không phải kiểu trường hoặc tham số phương thức. `void[]` hay `(V)I` không hợp lệ.
- `jint`, `jstring` là **kiểu trong mã C JNI**, không phải cú pháp JVM descriptor. Viết `I` cho `int`, `Ljava/lang/String;` cho `String`.
- `char` Java được mã hóa theo đơn vị UTF-16 16 bit; ký tự `C` trong descriptor chỉ biểu diễn **kiểu**, không mô tả cách encode một chuỗi.

Ví dụ: trường `private int age;` dùng `I`, trường `long id;` dùng `J`; phương thức `void reset()` dùng `()V`.

## 3. Đọc bộ mô tả cho lớp và interface: `L...;`

Một kiểu object có dạng:

```text
L<tên-lớp-dạng-internal-name>;
```

Cách giải mã:

1. `L` mở đầu kiểu tham chiếu.
2. Đọc tên lớp/interface đến dấu `;`.
3. Chuyển dấu `/` trong tên lớp thành dấu `.` phân cách package để trở lại cách đọc trong Java.
4. Dấu `;` là **ký tự kết thúc bắt buộc**.

| Java | Descriptor |
| --- | --- |
| `String` | `Ljava/lang/String;` |
| `Object` | `Ljava/lang/Object;` |
| `java.util.List` | `Ljava/util/List;` |
| `java.util.Map` | `Ljava/util/Map;` |
| `java.io.IOException` | `Ljava/io/IOException;` |
| `com.example.model.Order` | `Lcom/example/model/Order;` |

Chẳng hạn, `Ljava/util/Map;` là **một** descriptor object, không phải ba kiểu `L`, `java/util/Map` và `;`. Vì vậy trong method descriptor, chuỗi `(Ljava/lang/String;I)V` có hai tham số: `String` và `int`.

### 3.1. Lớp lồng nhau và ký tự `$`

Mã:

```java
package demo;

public class Outer {
    public static class Inner {
    }
}
```

Có descriptor cho `Outer.Inner` là:

```text
Ldemo/Outer$Inner;
```

Dấu `/` phân cách package, còn `$` xuất hiện trong **binary name** của lớp lồng nhau. Không đổi dấu `$` thành `/` hoặc `.`. Một số lớp local/anonymous có tên do trình biên dịch tạo (`$1`, `$1Local`,...); tốt nhất là xem `javap` hay `Class.descriptorString()` để biết chính xác.

### 3.2. `FindClass` khác cách viết trong descriptor

JNI `FindClass` khi nhận **tên lớp thông thường** dùng **internal name**, không có ký tự `L` và `;`:

```c
// Trong hàm JNI có JNIEnv *env hợp lệ:
jclass stringClass = (*env)->FindClass(env, "java/lang/String");
```

Nếu đang tìm **kiểu mảng**, `FindClass` nhận dạng **array type signature**, chẳng hạn `"[I"` hoặc `"[Ljava/lang/String;"`. Còn `GetFieldID` / `GetMethodID` vẫn cần descriptor chuẩn như `"Ljava/lang/String;"` khi tham chiếu đến một kiểu `String`.

Các lệnh JNI còn phụ thuộc class loader đang dùng. Descriptor đúng không bảo đảm tìm được lớp nếu loader không có quyền hoặc không nhìn thấy lớp đó.

## 4. Đọc bộ mô tả của mảng

Mỗi chiều mảng được thể hiện bằng **một dấu `[` đứng trước descriptor của kiểu phần tử**:

```text
[FieldType
[[FieldType
[[[FieldType
```

| Kiểu Java | Descriptor |
| --- | --- |
| `int[]` | `[I` |
| `int[][]` | `[[I` |
| `long[][][]` | `[[[J` |
| `boolean[]` | `[Z` |
| `double[][]` | `[[D` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `Object[][][]` | `[[[Ljava/lang/Object;` |
| `java.util.List[]` | `[Ljava/util/List;` |

Ví dụ đọc `[[Ljava/lang/String;`: hai dấu `[` cho biết **hai chiều**; phần còn lại `Ljava/lang/String;` là kiểu phần tử `String`, suy ra `String[][]`. Với `[[D`, kiểu phần tử `D` là `double`, suy ra `double[][]`.

Không thêm `L` trước primitive array: `[I` đúng cho `int[]`, còn `L[I;` sai. Mảng là **kiểu tham chiếu** trong Java kể cả khi phần tử là primitive. JVMS cho phép descriptor mảng nhiều nhất **255 chiều**, nhưng dự án thực tế hiếm khi cần hơn vài chiều.

### 4.1. `Class.getName()` và `descriptorString()` có thể khác

Với `String[][].class`:

```java
System.out.println(String[][].class.getTypeName());
System.out.println(String[][].class.getName());
System.out.println(String[][].class.descriptorString());
```

Đầu ra:

```text
java.lang.String[][]
[[Ljava.lang.String;
[[Ljava/lang/String;
```

- `getTypeName()` là tên dễ đọc.
- `getName()` cho class mảng có dạng gần với descriptor nhưng tên lớp thành phần dùng dấu `.`.
- `descriptorString()` cho descriptor JVM đúng với dấu `/`.

Khi cần ký hiệu JNI, `Class.descriptorString()` tránh nhầm lẫn hơn việc copy `Class.getName()` rồi tự xử lý chuỗi.

## 5. Đọc bộ mô tả phương thức: `(tham-số)trả-về`

Ngữ pháp chuẩn:

```text
(<descriptor-của-các-tham-số-viết-liền-nhau>)<descriptor-trả-về>
```

Dấu `(` mở và `)` đóng các tham số. **Không có dấu phẩy hoặc khoảng trắng** giữa các descriptor. Phần trả về là **một** field type hoặc `V`.

| Khai báo Java | Method descriptor |
| --- | --- |
| `void reset()` | `()V` |
| `int sum(int x, int y)` | `(II)I` |
| `boolean check(String s)` | `(Ljava/lang/String;)Z` |
| `long f(int n, String s, int[] arr)` | `(ILjava/lang/String;[I)J` |
| `String join(String[] parts, int limit)` | `([Ljava/lang/String;I)Ljava/lang/String;` |
| `void scan(int[][] matrix, boolean enabled)` | `([[IZ)V` |
| `double[] transform(double[][] values)` | `([[D)[D` |
| `List<String> findAll()` | `()Ljava/util/List;` |

Đọc chuỗi `(ILjava/lang/String;[I)J` từng bước:

1. `(`: bắt đầu tham số.
2. `I`: tham số 1 là `int`.
3. `Ljava/lang/String;`: tham số 2 là `String`.
4. `[I`: tham số 3 là `int[]`.
5. `)`: hết danh sách tham số.
6. `J`: kiểu trả về là `long`.

Suy ra chữ ký tương đương `long f(int, String, int[])`.

### 5.1. Những gì method descriptor không biểu diễn

Chuỗi descriptor **không chứa**:

- Tên phương thức (`f`, `reset`...), tên biến/tham số, tên ngoại lệ trong `throws`.
- Modifier như `public`, `private`, `static`, `final`, `synchronized`.
- Tham chiếu `this` ngầm của instance method.
- Các tham số C/JNI ẩn `JNIEnv *` và `jobject`/`jclass`.
- Kiểu generic đầy đủ (`List<String>`, `T`, wildcard) sau khi đã erasure.

**Kiểu trả về là một phần của descriptor.** Phải truyền đúng `(I)I` hay `(I)J` theo phương thức thực, dù Java source không cho phép overload chỉ khác kiểu trả về. Phần descriptor nhận diện kiểu tham số **theo đúng thứ tự**.

### 5.2. Constructor, static method và overload

Constructor Java:

```java
class Person {
    public Person(String name, int age) {}
    public static int parse(String s) {
        return Integer.parseInt(s);
    }
}
```

Trong JVM:

- Constructor có tên đặc biệt `<init>`, descriptor `(Ljava/lang/String;I)V`. Constructor không trả `LPerson;`.
- Static method `parse` có descriptor `(Ljava/lang/String;)I`. Không thêm tham số `Class`.
- Hai overload `sum(int,int)` và `sum(int)` khác nhau ở phần `(II)...` và `(I)...`.

Trong JNI, lấy constructor hoặc phương thức instance bằng `GetMethodID`; lấy phương thức static bằng `GetStaticMethodID`. Các hàm này yêu cầu cả **tên** và **descriptor**, không thể thay thế nhau chỉ bằng việc thay chuỗi signature.

Lớp còn có phương thức khởi tạo đặc biệt `<clinit>` ở mức bytecode (`()V`) khi cần, nhưng đó không phải constructor dùng với `GetMethodID`.

### 5.3. Varargs và generic erasure

Varargs Java là mảng tại mức descriptor:

```java
void print(String... words);
```

Descriptor: `([Ljava/lang/String;)V`, không có ký hiệu `...`.

Với:

```java
java.util.List<String> names;
java.util.List<Integer> list();
```

Field descriptor của `names` là `Ljava/util/List;` và method descriptor của `list()` là `()Ljava/util/List;`. Generic type arguments không nằm trong descriptor này. Thông tin generic có thể được lưu trong thuộc tính **`Signature`** của class file, là định dạng khác. Vì vậy không đưa `Ljava/util/List<Ljava/lang/String;>;` vào `GetFieldID`.

Với `<T extends Number> T echo(T value)`, erasure của `T` là `Number`, nên descriptor là `(Ljava/lang/Number;)Ljava/lang/Number;`. Một số bridge/synthetic methods do compiler tạo ra có descriptor riêng: hãy kiểm tra bytecode thật thay vì tự đoán.

## 6. Giải mã một descriptor phức tạp

Xét chuỗi:

```text
([[ILjava/lang/String;J)[[Ljava/lang/Object;
```

Thứ tự đọc:

1. `(` mở danh sách tham số.
2. `[[I` → tham số thứ nhất `int[][]`.
3. `Ljava/lang/String;` → tham số thứ hai `String`; phải đọc đến `;`.
4. `J` → tham số thứ ba `long`.
5. `)` đóng danh sách.
6. `[[Ljava/lang/Object;` → trả về `Object[][]`.

Chữ ký Java tương ứng (tên phương thức chỉ để minh họa):

```java
Object[][] process(int[][] matrix, String label, long version);
```

So sánh:

- `([[I)V`: **một** tham số kiểu `int[][]`, trả `void`.
- `([I[I)V`: **hai** tham số đều kiểu `int[]`, trả `void`.
- `(II)I`: hai `int` liền nhau không có dấu phẩy.
- `(Ljava/lang/String;I)V`: `String` và `int`, trả `void`.

**Mẹo:** khi gặp `L`, đọc liên tục đến `;`; khi gặp `[`, đếm chiều rồi giải mã kiểu kế tiếp; khi gặp `(`, giải từng tham số đến `)` rồi đọc đúng một kiểu trả về. `V` chỉ hợp lệ ở vị trí kiểu trả về.

## 7. Ví dụ Java 17+ chạy được: in descriptor và kiểm tra bằng reflection

Ta có thể đọc descriptor mà **không cần nạp thư viện C**. JDK 17 cung cấp `Class.descriptorString()` cho lớp/primitive/mảng và `MethodType.toMethodDescriptorString()` cho phương thức. Dùng reflection để đối chiếu với một phương thức Java thực.

Tạo tệp **`DescriptorLab.java`** trong một thư mục trống, không khai báo `package`:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class DescriptorLab {
    private int[] counts = {1, 2};
    private String title = "demo";

    public DescriptorLab() {
    }

    public long compute(int n, String text, int[][] matrix) {
        return n + text.length() + matrix.length;
    }

    public void tags(String... labels) {
        this.title = String.join(",", labels);
    }

    public static final class Item {
    }

    public static Item[] build(String[][] words, long version) {
        return new Item[words.length];
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        System.out.println("int: " + int.class.descriptorString());
        System.out.println("long: " + long.class.descriptorString());
        System.out.println("void: " + void.class.descriptorString());
        System.out.println("String: " + String.class.descriptorString());
        System.out.println("int[][]: " + int[][].class.descriptorString());
        System.out.println("String[][]: " + String[][].class.descriptorString());
        System.out.println("Item[]: " + Item[].class.descriptorString());

        MethodType compute = MethodType.methodType(
                long.class, int.class, String.class, int[][].class
        );
        System.out.println("compute: " + compute.toMethodDescriptorString());

        MethodType build = MethodType.methodType(
                Item[].class, String[][].class, long.class
        );
        System.out.println("build: " + build.toMethodDescriptorString());

        MethodType tags = MethodType.methodType(void.class, String[].class);
        System.out.println("tags: " + tags.toMethodDescriptorString());

        Method actual = DescriptorLab.class.getDeclaredMethod(
                "compute", int.class, String.class, int[][].class
        );
        MethodType reflected = MethodType.methodType(
                actual.getReturnType(), actual.getParameterTypes()
        );
        System.out.println("reflection: " + reflected.toMethodDescriptorString());

        MethodType parsed = MethodType.fromMethodDescriptorString(
                "(ILjava/lang/String;[[I)J",
                DescriptorLab.class.getClassLoader()
        );
        System.out.println(
                "parsed third parameter: " + parsed.parameterType(2).getTypeName()
        );
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DescriptorLab.java
java DescriptorLab
```

**Stdout chính xác:**

```text
int: I
long: J
void: V
String: Ljava/lang/String;
int[][]: [[I
String[][]: [[Ljava/lang/String;
Item[]: [LDescriptorLab$Item;
compute: (ILjava/lang/String;[[I)J
build: ([[Ljava/lang/String;J)[LDescriptorLab$Item;
tags: ([Ljava/lang/String;)V
reflection: (ILjava/lang/String;[[I)J
parsed third parameter: int[][]
```

Giải thích điểm đáng chú ý:

- `int.class.descriptorString()` trả `I`; `String.class.descriptorString()` trả `Ljava/lang/String;`; mảng thêm `[` cho mỗi chiều.
- Lớp lồng nhau `Item` có internal name `DescriptorLab$Item`, nên `Item[]` có descriptor `[LDescriptorLab$Item;`.
- `MethodType.methodType(returnType, argTypes...)` mô tả đúng tham số và kiểu trả về; `toMethodDescriptorString()` tạo chuỗi method descriptor.
- `getDeclaredMethod(...)` lấy phương thức `compute` thật. Kết quả từ reflection khớp kết quả tự tạo vì cùng chữ ký.
- `MethodType.fromMethodDescriptorString(...)` phân giải chuỗi về `MethodType` với class loader cho trước; `parameterType(2)` là tham số thứ ba (`int[][]`).

### 7.1. Đọc trực tiếp file `.class` bằng `javap -s`

Sau khi `javac` thành công, chạy:

```bash
javap -s -p DescriptorLab
```

`-s` in descriptor nội bộ, `-p` hiển thị cả member private. Trích các dòng liên quan (trình tự/chi tiết khác có thể còn xuất hiện):

```text
private int[] counts;
  descriptor: [I

private java.lang.String title;
  descriptor: Ljava/lang/String;

public DescriptorLab();
  descriptor: ()V

public long compute(int, java.lang.String, int[][]);
  descriptor: (ILjava/lang/String;[[I)J

public void tags(java.lang.String...);
  descriptor: ([Ljava/lang/String;)V

public static DescriptorLab$Item[] build(java.lang.String[][], long);
  descriptor: ([[Ljava/lang/String;J)[LDescriptorLab$Item;
```

Đối chiếu mỗi khai báo Java với dòng `descriptor:`. Trong dự án JNI thực tế, hãy chạy `javap -s -p` trên **class file thực sự đóng gói** để tránh lệch do version, overload, generics hoặc compiler-generated methods. `javap -v -p` cho thêm thông tin constant pool, generic `Signature` và cờ bridge/synthetic.

## 8. Khi áp dụng trong các hàm JNI

Các chữ ký JNI API (dạng C để hiểu ý nghĩa) gồm:

```c
jclass FindClass(JNIEnv *env, const char *name);

jfieldID GetFieldID(JNIEnv *env, jclass clazz,
                    const char *name, const char *sig);

jmethodID GetMethodID(JNIEnv *env, jclass clazz,
                      const char *name, const char *sig);

jfieldID GetStaticFieldID(JNIEnv *env, jclass clazz,
                          const char *name, const char *sig);

jmethodID GetStaticMethodID(JNIEnv *env, jclass clazz,
                            const char *name, const char *sig);
```

Đây là **khai báo API minh họa**, không phải file C biên dịch độc lập. Trong JNI code C, lời gọi thực tế qua `JNIEnv`, ví dụ `(*env)->GetMethodID(env, ...)`. Field ID tra cứu **field descriptor**; method ID tra cứu **method descriptor đầy đủ**.

Dựa trên `DescriptorLab` ở phần 7, đây là **đoạn code minh họa bên trong một hàm JNI trả `void` đã có `JNIEnv *env` hợp lệ**, không phải chương trình native độc lập:

```c
jclass cls = (*env)->FindClass(env, "DescriptorLab");
if (cls == NULL) {
    return;
}

jfieldID field = (*env)->GetFieldID(env, cls, "counts", "[I");
if (field == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jmethodID method = (*env)->GetMethodID(
        env, cls, "compute", "(ILjava/lang/String;[[I)J");
if (method == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jmethodID ctor = (*env)->GetMethodID(
        env, cls, "<init>", "()V");
if (ctor == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jmethodID factory = (*env)->GetStaticMethodID(
        env, cls, "build",
        "([[Ljava/lang/String;J)[LDescriptorLab$Item;");
if (factory == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

(*env)->DeleteLocalRef(env, cls);
```

Phần code này chỉ minh họa **tra cứu ID**. Muốn gọi method, phải có object/đối số và sử dụng `CallLongMethod`, `CallStaticObjectMethod`... thích hợp; các quy tắc tài nguyên, reference và exception JNI vẫn áp dụng.

So sánh những chuỗi gần giống nhưng dùng ở vị trí khác:

```c
(*env)->FindClass(env, "java/lang/String");         // Tên lớp
(*env)->FindClass(env, "[Ljava/lang/String;");      // Kiểu mảng
(*env)->GetFieldID(env, cls, "title",
                   "Ljava/lang/String;");          // Descriptor của field
```

- `FindClass` nhận tên lớp **dạng internal** hoặc array signature.
- `GetFieldID` nhận **tên field** và **một field descriptor**.
- `GetMethodID` nhận **tên method** và **một method descriptor** gồm cả kiểu trả về.
- `GetStaticFieldID` / `GetStaticMethodID` dùng cho static, còn các hàm không có chữ `Static` dùng cho instance.
- Giá trị `NULL` phải được kiểm tra; một số thất bại có exception Java đang chờ. Không dùng ID null, không gọi tiếp API trái quy tắc xử lý exception, và không tự ý xóa exception.

### 8.1. Vì sao không viết descriptor theo kiểu C?

Ví dụ hàm JNI phía C có `JNIEnv *env`, `jobject receiver` và `jint n`. Nhưng descriptor cho phương thức Java `int inc(int n)` vẫn chỉ là `(I)I`. Hai đối số ẩn đầu tiên trong chữ ký hàm C không phải tham số mà người gọi Java truyền, nên chúng không xuất hiện trong descriptor Java.

Descriptor cũng **không phải tên symbol JNI** được xuất từ thư viện native. Tên ký hiệu C theo quy ước JNI (hoặc `RegisterNatives`) thuộc cơ chế liên kết riêng. `javac -h` giúp tạo header đúng khi triển khai phương thức native.

## 9. Các lỗi phổ biến khi đọc type descriptor

| Viết sai | Nguyên nhân | Viết đúng |
| --- | --- | --- |
| `Ljava.lang.String;` | Dùng dấu `.` trong internal name | `Ljava/lang/String;` |
| `java/lang/String` trong `GetFieldID` | Thiếu `L` và `;` | `Ljava/lang/String;` |
| `L` cho `long` | Nhầm object prefix với primitive | `J` |
| `[I` cho `int[][]` | Thiếu một chiều mảng | `[[I` |
| `L[java/lang/String;` | Sai vị trí dấu `[` | `[Ljava/lang/String;` |
| `(V)I` | `void` không hợp lệ làm tham số | `()I` nếu không có tham số |
| `(I)` | Thiếu phần kiểu trả về | `(I)V`, `(I)I`,... tùy khai báo |
| `sum(II)I` truyền nguyên vào `sig` | Tên method phải truyền riêng | `name="sum"` và `sig="(II)I"` |
| `(jint)jint` | Dùng kiểu JNI C thay cho descriptor Java | `(I)I` |
| `Ljava/util/List<Ljava/lang/String;>;` cho JNI field | Nhầm generic `Signature` với field descriptor | `Ljava/util/List;` |
| `(Ljava/lang/String;...)V` | Varargs ở mức JVM là array | `([Ljava/lang/String;)V` |
| `FindClass(env,"Ljava/lang/String;")` | Nhầm descriptor với tên lớp `FindClass` | `FindClass(env,"java/lang/String")` |

Các lỗi khác tuy không sai cú pháp descriptor:

- **Sai static/instance**: cần dùng đúng `GetMethodID` hay `GetStaticMethodID`.
- **Sai kiểu trả về hoặc overload**: descriptor khác dù tên giống nhau.
- **Class loader khác nhau**: hai lớp cùng tên nhưng do loader khác nhau tải là hai kiểu runtime khác nhau. Chuỗi descriptor không tự xác định loader.
- **Sai phiên bản class file**: mã Java nguồn vừa thay đổi nhưng native code vẫn giữ descriptor từ phiên bản cũ.
- **Không xử lý exception** khi JNI lookup trả `NULL`.
- **Nhầm `NoSuchMethodError` với `UnsatisfiedLinkError`**: `GetMethodID` tra cứu method Java có thể gây `NoSuchMethodError` khi chữ ký sai, trong khi `UnsatisfiedLinkError` liên quan nạp/liên kết native library hoặc native method.

## 10. Bài tập tự kiểm tra

Hãy giải mã các chuỗi sau trước khi xem cột đáp án:

| Descriptor | Kiểu/chữ ký Java tương đương |
| --- | --- |
| `[Z` | `boolean[]` |
| `[[[J` | `long[][][]` |
| `Ljava/util/Map$Entry;` | `java.util.Map.Entry` |
| `([[D)V` | `void f(double[][])` |
| `([Ljava/lang/String;I)Z` | `boolean f(String[], int)` |
| `()Ljava/lang/String;` | `String f()` |
| `(Ljava/lang/Object;[I)[Ljava/lang/String;` | `String[] f(Object, int[])` |
| `([[ILjava/util/List;)V` | `void f(int[][], List)` |

Chữ `f` ở đáp án là tên phương thức **giả định** để diễn đạt, vì chuỗi descriptor không lưu tên phương thức. Cách tự tạo descriptor: lấy từng kiểu primitive hoặc `L...;`, thêm `[` cho từng chiều mảng, ghép các tham số trong `(...)`, rồi ghép kiểu trả về.

## 11. Checklist dùng trong công việc JNI

1. Đọc **class file đang chạy**, dùng `javap -s -p` để xác nhận chữ ký.
2. Primitive là một ký tự `B C D F I J S Z`; `V` chỉ cho kiểu trả về.
3. Lớp/interface dùng `Linternal/name;`, nested class dùng dấu `$` trong binary name.
4. Mảng thêm `[` cho từng chiều, theo sau là descriptor phần tử.
5. Phương thức dùng `(tham-số-theo-thứ-tự)trả-về`, không có tên hay dấu phẩy.
6. Với varargs dùng mảng, với generics dùng kiểu sau erasure, constructor dùng `<init>` và trả `V`.
7. Phân biệt `FindClass` (internal name hoặc array signature) với `GetFieldID`/`GetMethodID` (descriptor).
8. Kiểm tra instance/static, class loader, thông báo JNI và `NULL`/exception trước khi dùng ID.

## Tài liệu chuẩn để tra cứu

- [Java Virtual Machine Specification 17 — Field Descriptors (`4.3.2)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.2).
- [Java Virtual Machine Specification 17 — Method Descriptors (`4.3.3)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3).
- [JNI Specification 17 — Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html).
- [JNI Specification 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Oracle JDK 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [Oracle JDK 17 — Class.descriptorString()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#descriptorString()) và [MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).