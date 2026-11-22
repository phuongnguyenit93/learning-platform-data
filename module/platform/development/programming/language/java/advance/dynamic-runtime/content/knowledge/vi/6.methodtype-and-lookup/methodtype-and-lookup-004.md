# 6.4. Đọc và dựng JVM method descriptor với ngữ cảnh bộ nạp lớp

> **Bối cảnh:** Bài thuộc nhóm **6. MethodType và Lookup** của module **Java Advance – dynamic-runtime**. Mục tiêu là diễn giải chính xác *JVM method descriptor*, xây dựng và parse descriptor bằng API chuẩn Java 21, rồi xác định vai trò của **class loader** trong việc biến tên kiểu thành `Class<?>` thực tế. Các lab dùng JDK API công khai, chạy độc lập trên classpath.

## 1. Mục tiêu và kiến thức cần có

Sau khi học, bạn phải có khả năng:

1. Phân tích dạng `(parameters)return` của JVM method descriptor với primitive, object và array.
2. Phân biệt cú pháp JVM descriptor, Java source declaration, generic signature, `MethodType` và kiểu lời gọi của `MethodHandle`.
3. Dựng `MethodType` bằng `methodType(...)`, xuất descriptor bằng `toMethodDescriptorString()`, rồi đọc lại bằng `fromMethodDescriptorString(descriptor, loader)`.
4. Giải thích vì sao cần chọn class loader khi descriptor chứa `L...;` và vì sao **hai descriptor string bằng nhau** vẫn có thể tạo **MethodType không bằng nhau**.
5. Dùng `MethodHandles.Lookup` đúng cách cho static, virtual và constructor; hiểu vị trí receiver và return type.
6. Đọc `javap -s`, kiểm tra lỗi syntax/resolution/lookup/invocation theo từng pha.

Kiến thức nền: class/interface, static và instance methods, array, generics cơ bản, `Class<?>`, `ClassLoader`, `java.lang.invoke` và terminal. Không cần framework hay thư viện ngoài; các mã nguồn kiểm tra được bằng `javac --release 21`.

## 2. Phương pháp đọc JVM method descriptor

Ở cấp class file, **method descriptor** chỉ mã hóa **thứ tự kiểu tham số khai báo** và **kiểu trả về** của method. Cú pháp theo JVMS `4.3.3:

```text
MethodDescriptor    := "(" { ParameterDescriptor } ")" ReturnDescriptor
ParameterDescriptor := FieldType
ReturnDescriptor    := FieldType | "V"
FieldType           := BaseType | ObjectType | ArrayType
BaseType            := B | C | D | F | I | J | S | Z
ObjectType          := "L" InternalClassName ";"
ArrayType           := "[" FieldType
```

Không có dấu phẩy, không có khoảng trắng giữa các parameter descriptors. Ký tự `)` đánh dấu hết tham số; phần còn lại là một return descriptor.

### 2.1. Mã kiểu nguyên thủy

| Descriptor | Kiểu Java | Ghi chú |
| --- | --- | --- |
| `B` | `byte` | primitive |
| `C` | `char` | primitive |
| `D` | `double` | chiếm hai đơn vị độ dài tham số |
| `F` | `float` | primitive |
| `I` | `int` | primitive |
| `J` | `long` | chiếm hai đơn vị độ dài tham số |
| `S` | `short` | primitive |
| `Z` | `boolean` | primitive |
| `V` | `void` | **chỉ hợp lệ ở return** |

**Đặc biệt:** `J` là `long`, còn `L...;` dùng cho reference class/interface; `V` không phải là một parameter type hợp lệ. Một descriptor như `(V)I` sẽ bị parser từ chối.

### 2.2. Reference class và binary/internal name

Kiểu `java.lang.String` trở thành `Ljava/lang/String;`. Dấu `L` bắt đầu object type, dấu `;` kết thúc, dấu `/` dùng trong *internal name* thay dấu chấm ngăn package. Với class lồng nhau:

```text
Outer.Inner        → LOuter$Inner;
com.acme.Outer.Inner → Lcom/acme/Outer$Inner;
```

Đây là quy tắc cho **binary name** của nested classes; không thay dấu `$` bằng `/`. `java.lang.String` có dấu chấm trong Java code nhưng không được dùng `Ljava.lang.String;` trong JVM descriptor.

### 2.3. Array type

Mỗi dấu `[` thêm một chiều mảng; phần sau cùng là descriptor của component:

| Kiểu Java | Descriptor |
| --- | --- |
| `int[]` | `[I` |
| `double[][]` | `[[D` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `Object[][][]` | `[[[Ljava/lang/Object;` |

Mảng là reference type dù component là primitive. `double[]` tính **một đơn vị** tham số; `double` primitive tính **hai**.

### 2.4. Dịch chuỗi thành method Java

Giả sử source có:

```java
// Đoạn method minh họa bên trong một class.
static java.util.List<String> transform(String[] words, int count) {
    return java.util.Arrays.asList(words)
            .subList(0, Math.min(count, words.length));
}
```

Method descriptor của nó:

```text
([Ljava/lang/String;I)Ljava/util/List;
```

Cách đọc: `(` mở tham số, `[Ljava/lang/String;` là `String[]`, `I` là `int`, `)` đóng tham số, `Ljava/util/List;` là return type `List` sau erasure.

Các thông tin **không nằm trong descriptor**: method name, parameter names, owner class, modifier `static`, generic argument `String` của `List<String>`, `throws`, annotation. JVM có metadata khác cho các chi tiết tương ứng; đừng nhét chúng vào chuỗi descriptor.

## 3. Bảng chuyển đổi và quy tắc giới hạn

| Java method declaration | JVM method descriptor |
| --- | --- |
| `void ping()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `boolean valid(byte[] input)` | `([B)Z` |
| `String join(String[] parts, int limit)` | `([Ljava/lang/String;I)Ljava/lang/String;` |
| `long[] convert(int[][] values)` | `([[I)[J` |
| `Object m(int i, double d, Thread t)` | `(IDLjava/lang/Thread;)Ljava/lang/Object;` |
| `List<String> transform(String[] words, int count)` | `([Ljava/lang/String;I)Ljava/util/List;` |

Theo JVMS, một descriptor phải phù hợp giới hạn tổng **255 đơn vị độ dài tham số**; `long`/`double` primitive chiếm hai đơn vị, các kiểu khác chiếm một. Trong trường hợp instance hoặc interface invocation, tính thêm một đơn vị cho receiver `this`. Vì vậy không thể coi 255 là số lượng tham số cố định cho mọi phương thức.

Descriptor của instance method **không ghi receiver `this`** trong cặp ngoặc. `static int add(int,int)` và `int add(int,int)` có chung descriptor `(II)I`; khi thực sự gọi instance method, JVM truyền receiver theo cơ chế invocation tương ứng. Nhưng `MethodHandle` cho virtual method lại thể hiện receiver trong **chữ ký handle** — một sự khác nhau sẽ thấy ở Lab 3.

## 4. `MethodType` và các cách tạo descriptor

`java.lang.invoke.MethodType` mô tả kiểu trả về và danh sách kiểu tham số bằng **các đối tượng `Class<?>` runtime**. Nó immutable; mọi phép sửa chữ ký tạo một `MethodType` mới. `MethodType.equals` so chính xác các kiểu tham số và return, không chỉ so chuỗi in ra.

| API Java 21 | Nhiệm vụ |
| --- | --- |
| `MethodType.methodType(returnClass, parameters...)` | Tạo từ `Class<?>` có sẵn, không parse tên lớp. |
| `MethodType.fromMethodDescriptorString(descriptor, loader)` | Parse chuỗi JVM descriptor và resolve class names qua loader được chỉ định. |
| `type.toMethodDescriptorString()` | Xuất JVM method descriptor. |
| `type.descriptorString()` | Tương đương với `toMethodDescriptorString()`. |
| `type.parameterCount()`, `parameterType(i)`, `parameterArray()` | Xem danh sách runtime parameter types. |
| `type.returnType()` | Xem runtime return type. |
| `type.changeReturnType(...)`, `insertParameterTypes(...)` | Dựng một kiểu mới từ kiểu cũ. |
| `type.toString()` | Dạng hiển thị dễ đọc, **không phải JVM descriptor**. |
| `MethodTypeDesc.ofDescriptor(descriptor)` | Tạo nominal descriptor trong `java.lang.constant` mà chưa resolve class runtime. |

`void.class` chỉ được dùng làm **return class**, không được làm tham số trong `MethodType`. Phép `MethodType.methodType(int.class, int.class, int.class)` mô tả `(II)I`. `toString()` của nó có thể hiển thị `(int,int)int`, vốn không phải chuỗi đưa vào `fromMethodDescriptorString`.

**Lựa chọn thực tế:** Nếu đang giữ đúng các `Class<?>` của plugin, có thể dựng `MethodType` trực tiếp; khi nhận một chuỗi descriptor từ class file/cấu hình, phải có class loader thích hợp để resolve. Nếu chỉ phân tích cú pháp, cân nhắc `MethodTypeDesc` trước khi tải class.

## 5. Lab 1 — round-trip, reflection và lỗi parse

Tạo file **`DescriptorRoundTripLab.java`**:

```java
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class DescriptorRoundTripLab {
    public static List<String> transform(String[] words, int count) {
        return Arrays.asList(words).subList(0, Math.min(count, words.length));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        MethodType type = MethodType.methodType(List.class, String[].class, int.class);
        String descriptor = type.toMethodDescriptorString();
        MethodType parsed = MethodType.fromMethodDescriptorString(
                descriptor, DescriptorRoundTripLab.class.getClassLoader());

        Method reflected = DescriptorRoundTripLab.class.getDeclaredMethod(
                "transform", String[].class, int.class);
        MethodType fromReflection = MethodType.methodType(
                reflected.getReturnType(), reflected.getParameterTypes());
        MethodTypeDesc nominal = MethodTypeDesc.ofDescriptor(descriptor);

        System.out.println("descriptor=" + descriptor);
        System.out.println("roundTrip=" + type.equals(parsed));
        System.out.println("fromReflection=" + fromReflection.toMethodDescriptorString());
        System.out.println("parameterCount=" + parsed.parameterCount());
        System.out.println("firstParameter=" + parsed.parameterType(0).getTypeName());
        System.out.println("returnType=" + parsed.returnType().getTypeName());
        System.out.println("nominal=" + nominal.descriptorString());

        try {
            MethodType.fromMethodDescriptorString(
                    "(V)I", DescriptorRoundTripLab.class.getClassLoader());
            System.out.println("invalid=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid=IllegalArgumentException");
        }

        MethodTypeDesc unresolved = MethodTypeDesc.ofDescriptor("(Lsample/missing/Absent;)V");
        System.out.println("nominalUnresolved=" + unresolved.descriptorString());
        try {
            MethodType.fromMethodDescriptorString(
                    unresolved.descriptorString(),
                    DescriptorRoundTripLab.class.getClassLoader());
            System.out.println("missing=unexpected");
        } catch (TypeNotPresentException expected) {
            System.out.println("missing=TypeNotPresentException");
        }
    }
}
```

Biên dịch/chạy trong thư mục chứa file bằng JDK tương thích Java 21:

```sh
javac --release 21 -Xlint:all DescriptorRoundTripLab.java
java DescriptorRoundTripLab
```

**Stdout:**

```text
descriptor=([Ljava/lang/String;I)Ljava/util/List;
roundTrip=true
fromReflection=([Ljava/lang/String;I)Ljava/util/List;
parameterCount=2
firstParameter=java.lang.String[]
returnType=java.util.List
nominal=([Ljava/lang/String;I)Ljava/util/List;
invalid=IllegalArgumentException
nominalUnresolved=(Lsample/missing/Absent;)V
missing=TypeNotPresentException
```

### 5.1. Giải thích chi tiết

- `methodType(List.class, String[].class, int.class)` nhận đúng return + tham số đã biết, không cần tự ghép dấu `[` và `L...;`.
- `toMethodDescriptorString()` tạo chuỗi mang cả kiểu array, primitive và reference; `fromMethodDescriptorString` dùng class loader để dựng lại `Class<?>` của `List` và `String[]`. Vì đều là kiểu JDK thông thường, hai `MethodType` bằng nhau.
- `getDeclaredMethod` tìm method tên `transform` với các kiểu tham số sau erasure; Reflection `getReturnType()` trả `List.class` thay vì một kiểu runtime `List<String>` độc lập.
- `MethodTypeDesc.ofDescriptor` tạo một **nominal descriptor** có thể biểu diễn tên lớp chưa tồn tại, vì chưa yêu cầu resolve tên này thành `Class<?>`.
- `(V)I` sai grammar vì `void` không thể là tham số, dẫn tới `IllegalArgumentException`.
- `(Lsample/missing/Absent;)V` đúng grammar, nhưng loader không tìm được class: `TypeNotPresentException`.

Ở cấp hệ thống, đó là ba pha khác nhau: **kiểm tra chuỗi**, **resolve kiểu**, rồi **tra cứu member cụ thể** (nếu cần). Thành công ở pha trước không bảo đảm pha sau.

### 5.2. Dùng `javap` làm chuẩn kiểm tra

```sh
javap -s -p DescriptorRoundTripLab
```

Trong output có method:

```text
public static java.util.List<java.lang.String> transform(java.lang.String[], int);
  descriptor: ([Ljava/lang/String;I)Ljava/util/List;
```

Lệnh còn in constructor, `main` và các thành viên khác; hai dòng trên là phần liên quan, không phải toàn bộ output. `javap -s` lấy thông tin từ bytecode đã biên dịch, giúp xác nhận khác biệt giữa generic source declaration và JVM method descriptor.

## 6. Tham số `ClassLoader` trong `fromMethodDescriptorString`

Khi gặp `Lcom/acme/PluginMessage;`, parser cần chuyển internal name thành **runtime class**. Java 21 Javadoc quy định `fromMethodDescriptorString(descriptor, loader)` resolve mọi tên reference class/interface bằng loader được truyền; nếu `loader` là `null`, API dùng **system class loader**. Đừng nhầm `null` là “chỉ bootstrap loader”.

### 6.1. Những điều loader thay đổi

1. Primitive `I`, `D`, `J`, `V` không cần resolve class ứng dụng.
2. Với JDK class như `java.lang.String`, application loader thường ủy quyền cho loader nền tảng để lấy cùng class.
3. Với plugin class, các loader có thể nhìn thấy tập class khác nhau, gây `TypeNotPresentException` nếu không tìm được.
4. Một class có cùng **binary name** có thể được định nghĩa bởi hai **defining loaders** khác nhau, trở thành hai kiểu runtime khác nhau.
5. Descriptor không ghi loader hay module layer. Vì thế **nội dung chuỗi không tự định danh duy nhất một kiểu runtime**.
6. Việc dựng `MethodType` từ descriptor có thể gây class loading nhưng **không yêu cầu class initialization** giống như gọi constructor hay thực thi static initializer; không tự biến chuỗi thành lời gọi method.
7. Parser không kiểm tra thay `Lookup` quyền truy cập member, method name hay kind static/virtual/constructor.

### 6.2. Defining loader và initiating loader

Loader được yêu cầu `loadClass` có thể **ủy quyền cho parent** và nhận về class do parent định nghĩa. Nó là ngữ cảnh **tra cứu/initiating loader**, còn *defining loader* mới tham gia danh tính kiểu cùng binary name. Hai loader khác nhau **không tự động** tạo hai `Class<?>` khác nhau nếu đều ủy quyền cùng một class. Lab dưới đây cố ý dùng loader tạo định nghĩa riêng của đúng một nested class để quan sát khác biệt rõ ràng.

### 6.3. Vì sao `MethodType.equals` không chỉ so descriptor text?

`MethodType` giữ từng `Class<?>` thực, còn descriptor giữ *tên* của các kiểu. Khi hai loader cùng định nghĩa `example.Message`:

```text
Descriptor text: (Lexample/Message;)V
                |                     |
          Loader A resolve       Loader B resolve
                |                     |
      Class(example.Message)  Class(example.Message)
         defined by A           defined by B
                \\                  /
           same descriptor string
              different Class<?> identities
                    |
            MethodType.equals == false
```

Nếu hệ thống plugin lấy descriptor string làm cache key xuyên các loader mà thiếu ngữ cảnh, nó có thể trả nhầm `MethodType`/`MethodHandle` của plugin khác. Với shared API hoặc SPI, nên đặt contract ở loader chung khi cần trao đổi object xuyên plugin; đảm bảo cache được phân vùng/invalidated theo lifecycle loader.

## 7. Lab 2 — cùng descriptor nhưng khác class loader

Tạo file **`LoaderContextLab.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodType;

public class LoaderContextLab {
    public static final class Payload {}

    private static final class CopyingLoader extends ClassLoader {
        private final String targetName;

        CopyingLoader(ClassLoader parent, String targetName) {
            super(parent);
            this.targetName = targetName;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null && name.equals(targetName)) {
                    String resource = name.replace('.', '/') + ".class";
                    try (InputStream in = getParent().getResourceAsStream(resource)) {
                        if (in == null) throw new ClassNotFoundException(name);
                        byte[] bytes = in.readAllBytes();
                        loaded = defineClass(name, bytes, 0, bytes.length);
                    } catch (IOException e) {
                        throw new ClassNotFoundException(name, e);
                    }
                }
                if (loaded == null) loaded = super.loadClass(name, false);
                if (resolve) resolveClass(loaded);
                return loaded;
            }
        }
    }

    public static void main(String[] args) {
        String binaryName = Payload.class.getName();
        String descriptor = "(L" + binaryName.replace('.', '/') + ";)V";
        ClassLoader application = LoaderContextLab.class.getClassLoader();
        ClassLoader isolated = new CopyingLoader(application, binaryName);

        MethodType first = MethodType.fromMethodDescriptorString(descriptor, application);
        MethodType second = MethodType.fromMethodDescriptorString(descriptor, isolated);

        System.out.println("descriptor=" + descriptor);
        System.out.println("sameText=" +
                first.toMethodDescriptorString().equals(second.toMethodDescriptorString()));
        System.out.println("sameClass=" +
                (first.parameterType(0) == second.parameterType(0)));
        System.out.println("sameMethodType=" + first.equals(second));
        System.out.println("childDefined=" +
                (second.parameterType(0).getClassLoader() == isolated));
    }
}
```

```sh
javac --release 21 -Xlint:all LoaderContextLab.java
java LoaderContextLab
```

**Stdout khi chạy trên classpath mặc định:**

```text
descriptor=(LLoaderContextLab$Payload;)V
sameText=true
sameClass=false
sameMethodType=false
childDefined=true
```

### 7.1. Chứng minh từng giá trị

- `Payload.class.getName()` tạo binary name `LoaderContextLab$Payload` (nằm trong default package); `replace('.', '/')` chuyển dấu chấm package thành dạng internal name nếu có.
- Với loader ứng dụng, descriptor được parse thành `MethodType` có parameter `Payload` do loader ứng dụng định nghĩa.
- Loader thử nghiệm `CopyingLoader` giữ riêng việc nạp đúng `targetName`: đọc bytes từ resource và gọi `defineClass`. Mọi class khác vẫn theo parent delegation qua `super.loadClass`.
- Vì hai `Class<?>` được định nghĩa bởi loader khác nhau, biểu thức `first.parameterType(0) == second.parameterType(0)` là `false`; do đó hai `MethodType` cũng không bằng nhau.
- Hai parameter classes vẫn có cùng binary name, nên `toMethodDescriptorString()` tạo **đúng cùng text**; đó là lý do `sameText=true`.
- `childDefined=true` xác nhận loader cô lập thực sự sở hữu class phía thứ hai.

**Phạm vi lab:** đây là trình nạp tối giản để minh họa class identity, không phải plugin loader production. Class loading tùy biến cần quan tâm package sealing, module boundaries, dependency resolution, bảo mật nguồn bytecode, lỗi khi nạp và vòng đời tài nguyên. Không thay toàn bộ delegation hoặc tự nạp lớp JDK chỉ để làm thí nghiệm.

### 7.2. Khi áp dụng cho plugin thật

Nếu plugin A sử dụng `com.acme.api.Message` của loader A và hệ thống chính resolve một class tên giống hệt qua loader B, Java có thể từ chối cast/lookup dù log chỉ hiện cùng tên. Cách sửa không phải đổi descriptor text: cần thống nhất **contract class identity**, chọn đúng loader và thiết kế đường chia sẻ API/SPI. Khi unload plugin, giải phóng handles và caches giữ `Class<?>` để loader có cơ hội được giải phóng.

## 8. Kết nối với `MethodHandles.Lookup`

Nhớ phân biệt:

- **Descriptor string:** mô tả shape, không chỉ rõ method name/owner hay loader.
- **`MethodType`:** chứa các `Class<?>` runtime cụ thể cho shape đã được resolve.
- **`MethodHandles.Lookup`:** kiểm tra quyền và thực hiện **member lookup** theo owner, name, kind và `MethodType`.
- **`MethodHandle.type()`:** chữ ký của **lời gọi handle** sau khi đã tìm/bind/adapt, có thể khác descriptor method được khai báo.

Dựng `MethodType` thành công chưa có nghĩa bạn tìm được method. `findStatic` phải nhắm static method; `findVirtual` phải nhắm method instance thích hợp; `findConstructor` phải nhắm constructor và dùng kiểu trả về `void` tại bước lookup.

### 8.1. Receiver của instance method

Cùng method có source:

```java
int add(int a, int b) { return a + b; }
```

JVM method descriptor của **khai báo** là `(II)I`. Khi gọi `lookup.findVirtual(Calculator.class, "add", MethodType.methodType(int.class,int.class,int.class))`, tham số `MethodType` truyền cho `findVirtual` **không bao gồm receiver**. Handle trả về lại có type:

```text
(LInvokeDescriptorLab$Calculator;II)I
```

Receiver được đặt ở vị trí đầu vì handle nhận đối tượng `Calculator` trước khi gọi `add`. Trong Lab 3, static handle cùng tham số/return có type `(II)I`, không có receiver.

### 8.2. Constructor có hai góc nhìn

Constructor trong class file là method đặc biệt tên `<init>`, có return descriptor `V`. Vì vậy constructor `Box(int)` có JVM descriptor `(I)V`. Khi gọi `Lookup.findConstructor(Box.class, MethodType.methodType(void.class,int.class))`, handle mới tạo **Box object**, nên `handle.type()` là `(I)LInvokeDescriptorLab$Box;`.

Cả hai cách nhìn đều đúng cho chức năng riêng: **descriptor của constructor `<init>`** và **chữ ký của constructor handle** là hai cấu trúc khác nhau. Không dùng return type `Box` khi truyền `MethodType` cho `findConstructor`.

## 9. Lab 3 — static, virtual và constructor

Tạo file **`InvokeDescriptorLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class InvokeDescriptorLab {
    static class Calculator {
        int add(int a, int b) { return a + b; }
        static int multiply(int a, int b) { return a * b; }
    }

    static class Box {
        final int id;
        Box(int id) { this.id = id; }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        ClassLoader loader = InvokeDescriptorLab.class.getClassLoader();

        MethodType declared = MethodType.fromMethodDescriptorString("(II)I", loader);
        MethodHandle staticHandle = lookup.findStatic(
                Calculator.class, "multiply", declared);
        MethodHandle virtualHandle = lookup.findVirtual(
                Calculator.class, "add", declared);

        MethodType constructorDescriptor =
                MethodType.fromMethodDescriptorString("(I)V", loader);
        MethodHandle constructor = lookup.findConstructor(Box.class, constructorDescriptor);

        int multiplied = (int) staticHandle.invokeExact(3, 4);
        int added = (int) virtualHandle.invokeExact(new Calculator(), 5, 6);
        Box box = (Box) constructor.invokeExact(9);

        System.out.println("declared=" + declared.toMethodDescriptorString());
        System.out.println("static=" + staticHandle.type().toMethodDescriptorString());
        System.out.println("virtual=" + virtualHandle.type().toMethodDescriptorString());
        System.out.println("constructorLookup=" + constructorDescriptor.toMethodDescriptorString());
        System.out.println("constructorHandle=" + constructor.type().toMethodDescriptorString());
        System.out.println("multiply=" + multiplied);
        System.out.println("add=" + added);
        System.out.println("box.id=" + box.id);
    }
}
```

```sh
javac --release 21 -Xlint:all InvokeDescriptorLab.java
java InvokeDescriptorLab
```

**Stdout:**

```text
declared=(II)I
static=(II)I
virtual=(LInvokeDescriptorLab$Calculator;II)I
constructorLookup=(I)V
constructorHandle=(I)LInvokeDescriptorLab$Box;
multiply=12
add=11
box.id=9
```

### 9.1. Diễn giải và kiểm tra kiểu call site

`declared` là cùng declared type cho hai method; `virtualHandle` thêm receiver `Calculator`, nhưng `staticHandle` giữ nguyên type. `constructorDescriptor` trả `void` theo JVM constructor declaration, còn `constructor.type()` trả `Box`.

`invokeExact` là lời gọi có yêu cầu **kiểu chính xác tại call site**. `(int) staticHandle.invokeExact(3,4)` chỉ rõ kiểu trả về `int`; `new Calculator()` truyền đúng receiver; `(Box) constructor.invokeExact(9)` chỉ rõ return type `Box`. Sai tham số, receiver hoặc kiểu trả về có thể gây `WrongMethodTypeException`.

Lab khai báo `throws Throwable` để tập trung vào `MethodHandle`; trong mã ứng dụng, nên phân tầng và xử lý ngoại lệ có chủ đích. Không suy diễn rằng mọi `MethodHandle` đều cần gọi bằng `invokeExact`: `invoke` có cơ chế chuyển đổi kiểu, nhưng hãy kiểm tra chữ ký và loại chuyển đổi cho phép.

## 10. JVM descriptor, generic signature và runtime identity

Xét một method generic:

```java
// Ví dụ khai báo, đặt trong class có import java.util.List.
public List<String> normalize(List<Integer> values) {
    return List.of();
}
```

JVM method descriptor của method này là:

```text
(Ljava/util/List;)Ljava/util/List;
```

Nó không phân biệt `List<Integer>` với `List<String>`, vì thông tin generic bị **type erasure** khỏi method descriptor. Generic `Signature` attribute trong class file vẫn có thể lưu các type arguments, được Reflection truy xuất qua `getGenericReturnType()`/`getGenericParameterTypes()`. Nhưng `MethodType` chỉ chứa `Class<?>`, nên hai generic instantiations không tạo hai method types khác nhau nếu cùng kiểu erased.

| Biểu diễn | Mục tiêu | Có mang loader identity? |
| --- | --- | --- |
| Method descriptor string | Ký hiệu kiểu tham số/return trong bytecode | **Không** |
| Generic `Signature` | Thông tin generic của khai báo nếu có | Không đủ để xác định runtime object type |
| `Class<?>` | Một kiểu runtime trong JVM | Có danh tính theo định nghĩa lớp/loader |
| `MethodType` | Danh sách `Class<?>` tham số/return | Có qua từng `Class<?>` |
| `MethodTypeDesc` | Mô tả danh nghĩa của method type | Chưa resolve class |
| `Lookup` | Ngữ cảnh quyền dùng để tìm member | Có ngữ cảnh class/module và lookup modes |

### 10.1. Nominal descriptor không đồng nghĩa resolved MethodType

`MethodTypeDesc.ofDescriptor("(Lplugin/Missing;)V")` chỉ cần chuỗi có cú pháp hợp lệ, không cần `plugin.Missing` tồn tại. Ngược lại, `MethodType.fromMethodDescriptorString(..., loader)` phải chuyển tên thành `Class<?>` thực và có thể gặp `TypeNotPresentException`.

`MethodTypeDesc.resolveConstantDesc(lookup)` là một cơ chế khác: resolve nominal descriptor theo ngữ cảnh quyền của `Lookup`, với kiểm tra class/module tương ứng và hợp đồng ngoại lệ riêng. Nó có thể thích hợp cho mô hình nominal constants; không dùng nó làm “bypass” kiểm tra access.

Java 21 Javadoc cũng nói `toMethodDescriptorString()` **không phải nghịch đảo tuyệt đối** của `fromMethodDescriptorString()`: dù descriptor là hợp lệ, dùng loader khác có thể nhận các `Class<?>` khác; một số kiểu không mô tả được danh nghĩa (chẳng hạn một số hidden classes) có thể sinh chuỗi không parse lại như descriptor hợp lệ thông thường.

## 11. Xác định đúng loại lỗi

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` cho `(V)I` | `void` nằm trong parameter list | Kiểm tra grammar: `V` chỉ dùng ở return. |
| `IllegalArgumentException` cho `(Ljava.lang.String;)V` | Tên lớp dùng dấu `.` thay `/` | Sửa thành `(Ljava/lang/String;)V`. |
| `TypeNotPresentException` | Reference class trong descriptor không tìm thấy bằng loader đã chọn | Kiểm tra binary/internal name, plugin loader, classpath/module path và cause. |
| `NoClassDefFoundError` / `LinkageError` | Class có thể tìm thấy nhưng dependency hoặc điều kiện linking không phù hợp | Tìm root cause, kiểm tra version, dependency và loader constraints. |
| `NoSuchMethodException` / `NoSuchMethodError` | Tìm sai tên, owner, static/virtual kind hoặc erased signature | Đối chiếu `javap -s`, method type, API lookup đúng. |
| `IllegalAccessException` | `Lookup` không có quyền vào member/package/module | Xem access modifiers, lookup modes, JPMS exports/opens; dùng API được cấp quyền. |
| `WrongMethodTypeException` | Call site của `invokeExact` không khớp `handle.type()` | In handle type, kiểm tra receiver và return cast. |
| Hai type có descriptor giống nhau nhưng không cast được | Defining loaders khác nhau | So sánh `Class<?>` bằng `==`, kiểm tra `getClassLoader()`, thống nhất shared contract. |
| Parse descriptor rồi không thấy static initializer in ra | Loading/resolve không phải initialization | Chỉ kiểm tra initialization bằng thao tác kích hoạt thích hợp, trên JVM mới. |
| Lấy `loader=null` mà resolve sai plugin | `null` nghĩa là dùng system loader trong API này | Truyền loader có chủ đích của plugin. |
| Xử lý constructor theo `(I)LBox;` | Nhầm JVM constructor descriptor với handle type | Parse `(I)V` khi tìm `<init>`, xem handle type sau `findConstructor`. |

**Quy trình điều tra:** Tách pha parse syntax → resolve reference types → chọn owner & method name → Lookup access → invocation type. Một lỗi ở giai đoạn sau không nên “chữa” bằng cách tự ý sửa descriptor ở giai đoạn trước.

## 12. Thiết kế an toàn khi nhận descriptor từ plugin/configuration

Một hệ thống có cấu hình method động nên dùng chuỗi thao tác minh bạch:

```text
Config/bytecode metadata
  |
  +--> kiểm tra cú pháp descriptor / giới hạn chiều dài
  |
  +--> chọn ClassLoader & module context đáng tin
  |
  +--> parse MethodType hoặc giữ MethodTypeDesc chưa resolve
  |
  +--> xác định owner Class, method name, invocation kind
  |
  +--> Lookup.findStatic/findVirtual/findConstructor theo quyền hợp lệ
  |
  +--> kiểm tra handle.type() và cách gọi phù hợp
  |
  +--> gọi và ghi lỗi theo từng pha
```

Đừng lấy chuỗi descriptor ngoài hệ thống làm lý do để **nạp/gọi bất kỳ class hoặc member nào**. Dùng allowlist, contract interface và policy phù hợp. `Lookup` cần làm việc theo mô hình module và access control thực tế; không tự cấp quyền bằng `setAccessible(true)` hoặc `--add-opens` khi chưa có lý do.

Một cache dùng key `(ownerName, methodName, descriptor)` có thể sai khi nhiều plugin dùng cùng tên class nhưng loader khác. Thiết kế key bao gồm runtime owner/type identity hoặc phân vùng theo loader; dọn cache, threads, method handles khi plugin unload để tránh giữ class loader không cần thiết.

### 12.1. Cách xem đúng bytecode mà không phỏng đoán

Dùng các lệnh:

```sh
javap -s -p DescriptorRoundTripLab
javap -c -p InvokeDescriptorLab
```

`-s` in các descriptor. `-c` hiển thị opcode bytecode và giúp phân biệt `invokestatic`, `invokevirtual`, `invokespecial`; tùy đoạn code compiler, có thể thấy `invokedynamic`. Không khẳng định những opcode đó trực tiếp tiết lộ mọi hành vi JIT runtime.

Ở code generic, compiler còn có thể sinh *bridge methods* có descriptor riêng để giữ polymorphism sau erasure. Khi tìm member trong bytecode hoặc Reflection, đừng mặc định chỉ có đúng một method trùng tên do source khai báo.

## 13. Bài tập thực hành có tiêu chí kết quả

**Bài 1 – Đọc descriptor bằng tay.** Giải mã `(JLjava/lang/String;)[D`, `([[I[Ljava/lang/Object;)V` và `()Ljava/util/Map;`. Nêu đúng số tham số, kiểu, thứ tự và return. Lời giải: `(long,String) → double[]`; `(int[][],Object[]) → void`; `() → Map` (ở dạng erased).

**Bài 2 – Cấu trúc array.** Viết `static long merge(byte[] data, double factor, String[][] names)`, đoán descriptor `([BD[[Ljava/lang/String;)J`, biên dịch và xác minh bằng `javap -s`. Giải thích tại sao `D` tính hai slots nhưng `[[Ljava/lang/String;` chỉ tính một.

**Bài 3 – Constructor.** Thêm `Box(String label, int id)` vào Lab 3, tra cứu với `(Ljava/lang/String;I)V` và in `handle.type().toMethodDescriptorString()`. Giải thích vì sao handle trả `Box` còn `<init>` trả `void`.

**Bài 4 – Cùng loader.** Trong Lab 2, truyền `application` cho cả hai lần `fromMethodDescriptorString` và dự đoán `sameClass=true`, `sameMethodType=true`. Sau đó cho loader cô lập ủy quyền thay vì define class riêng; giải thích vì sao hai loader object khác vẫn có thể resolve cùng class.

**Bài 5 – Syntax hay resolution?** Parse `(V)I` và `(Lno/such/Missing;)V`. Nêu hai exception khác nhau và lý do. Dùng `MethodTypeDesc.ofDescriptor` với trường hợp thứ hai để chỉ rõ cú pháp vẫn đúng.

**Bài 6 – MethodHandle receiver.** Từ Lab 3, in `declared`, `staticHandle.type()`, `virtualHandle.type()` và so tham số thứ 0 của virtual handle. Thử dùng sai receiver rồi giải thích lỗi; không giữ mã sai trong kết quả cuối.

**Bài 7 – Cache plugin.** Giả định hai plugin có cùng tên `com.acme.Message`, mô tả vì sao key là descriptor string không đủ; đề xuất cấu trúc key dựa trên runtime type identity và cách cache bị xóa khi plugin đóng.

**Tự đánh giá:** Bạn hoàn thành bài khi tự đọc được descriptor lồng array/reference, tạo được `MethodType` hai cách, chứng minh sự khác biệt giữa syntax/loader/lookup, và diễn giải chính xác toàn bộ stdout ba lab mà không dựa vào giả định “cùng tên class là cùng type”.

## 14. Tài liệu Java 21 gốc

- [JVMS 21 `4.3.2 – Field Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.2): primitive/object/array.
- [JVMS 21 `4.3.3 – Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3): tham số, return, giới hạn slots và `this`.
- [Java SE 21 – MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): factory, parser, descriptor methods và equality.
- [Java SE 21 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): tra cứu static/virtual/constructor có kiểm soát.
- [Java SE 21 – MethodTypeDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/MethodTypeDesc.html): nominal descriptor và cách resolve.
- [JDK 21 – javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): xem descriptor từ compiled class file.

**Ghi nhớ:** Descriptor là **hình dạng lời gọi bằng tên kiểu**. `MethodType` chứa **runtime Class objects**; class loader cho biết tên ấy được resolve thành lớp nào; `Lookup` xác định member nào có thể được liên kết với quyền hiện có. Phân biệt cả ba tầng để xây hệ thống dynamic runtime đúng đắn.
