# Executable và mô hình chung của method, constructor trong Java Reflection

## Mục tiêu học tập

Trong Java Reflection, **`java.lang.reflect.Executable`** là lớp trừu tượng mô hình hóa phần chung của **method** và **constructor**. Hai lớp con quen thuộc của nó là **`java.lang.reflect.Method`** và **`java.lang.reflect.Constructor<T>`**. API này đặc biệt hữu ích khi cần đọc **metadata của tham số**: số lượng, kiểu, tên, annotation, varargs, tham số synthetic/implicit và thông tin generic/annotated types.

`Executable` cùng hệ sinh thái `java.lang.reflect.Parameter` được giới thiệu từ Java 8; chúng **vẫn còn được dùng trong Java hiện đại** cho framework, dependency injection, routing, serialization, validation, công cụ phân tích API và test infrastructure. Java Reflection **không** tự bảo đảm rằng tên tham số luôn có mặt hoặc rằng mọi thành phần private có thể truy cập từ bất kỳ module nào.

Sau bài này, bạn có thể:

- Giải thích vì sao `Method` và `Constructor<?>` đều là `Executable`, nhưng **không hoàn toàn giống nhau**.
- Lấy metadata dùng chung: `getParameterCount()`, `getParameters()`, `getParameterTypes()`, `getGenericParameterTypes()`, `getAnnotatedParameterTypes()`, `getParameterAnnotations()`.
- Phân biệt **`Parameter` object** với **kiểu của parameter**, annotation trên declaration và annotation trên type use.
- Hiểu ý nghĩa của cờ biên dịch **`-parameters`** và `Parameter.isNamePresent()`.
- Kiểm tra `isVarArgs()`, `isSynthetic()`, `isImplicit()`, `getExceptionTypes()`, `getTypeParameters()`, `getAnnotatedReceiverType()`.
- Chọn đúng API khi cần gọi method (`Method.invoke`) hoặc khởi tạo đối tượng (`Constructor.newInstance`).
- Xử lý việc lookup, overload, erasure, checked exception và giới hạn accessibility của module.
- Chạy một ví dụ Java 17+ trọn vẹn với kết quả xác định và hiểu những lỗi thường gặp.

## 1. Mối quan hệ giữa Executable, Method và Constructor

Có thể hình dung kế thừa lớp như sau:

~~~text
java.lang.reflect.AccessibleObject
  └── java.lang.reflect.Executable  (abstract)
        ├── java.lang.reflect.Method
        └── java.lang.reflect.Constructor<T>
~~~

**`Executable` là abstraction để đọc đặc điểm chung**, không phải một lớp bạn khởi tạo bằng `new Executable()`. Nó đại diện những thành phần **khai báo hành vi có danh sách tham số**:

- `Method`: phương thức được khai báo trong một class/interface. Có tên, kiểu trả về và có thể được thực thi bằng `invoke`.
- `Constructor<T>`: constructor của một class. Dùng để tạo instance bằng `newInstance`; constructor **không có return type theo cú pháp khai báo Java** như method.
- `Executable`: API dùng chung về tham số, generic type parameters, exception declarations, varargs, annotations trên tham số/kiểu, modifier và declaring class.

Ví dụ method và constructor khác nhau:

~~~java
class Product {
    private final String code;

    Product(String code) {           // constructor
        this.code = code;
    }

    String code() {                  // method
        return code;
    }
}
~~~

Khi phản chiếu:

~~~java
Constructor<Product> ctor =
        Product.class.getDeclaredConstructor(String.class);

Method method =
        Product.class.getDeclaredMethod("code");
~~~

Cả `ctor` và `method` đều có thể được tham chiếu bằng biến `Executable`:

~~~java
Executable first = ctor;
Executable second = method;
~~~

Đây là **mã minh họa**, cần import `java.lang.reflect.*` và ngữ cảnh xử lý `NoSuchMethodException`. Bạn có thể áp dụng logic chung đọc tham số cho cả hai mà không cần tạo hai phương thức tiện ích gần giống nhau.

**Đừng nhầm `Executable` với `java.lang.Runnable` hay `java.util.concurrent.Executor`.** `Executable` là mô hình **reflection metadata** của method/constructor, không phải interface giao việc để một thread thực thi.

## 2. Các API chung quan trọng nhất

Dưới đây là nhóm phương thức đáng nhớ của `Executable`:

| API | Thông tin | Chú ý |
| --- | --- | --- |
| `getName()` | Tên executable | Constructor thường có tên biểu diễn class, không phải tên method do người viết đặt |
| `getDeclaringClass()` | Class/interface khai báo executable | Phân biệt declaring class với runtime class của đối tượng |
| `getModifiers()` | Bitmask modifier | Dùng `Modifier.isPublic(...)`, `Modifier.isStatic(...)`, ... |
| `getParameterCount()` | Số tham số ở cấp reflection | Có thể gồm các tham số implicit/synthetic trong trường hợp đặc biệt |
| `getParameters()` | Mảng `Parameter[]` theo thứ tự khai báo/reflection | Tên có thể thiếu nếu biên dịch không bật `-parameters` |
| `getParameterTypes()` | `Class<?>[]` sau erasure | Không giữ đầy đủ `List<String>` |
| `getGenericParameterTypes()` | `Type[]` | Giữ cấu trúc generic declaration khi có metadata tương ứng |
| `getAnnotatedParameterTypes()` | `AnnotatedType[]` | Cho annotation trên **kiểu** tham số |
| `getParameterAnnotations()` | `Annotation[][]` | Cho annotation trên **khai báo** tham số |
| `getTypeParameters()` | `TypeVariable<?>[]` | Generic type parameters được chính method/constructor khai báo |
| `getExceptionTypes()` | `Class<?>[]` | Kiểu exception khai báo trong `throws` theo erasure |
| `getGenericExceptionTypes()` | `Type[]` | Generic throws types khi áp dụng |
| `getAnnotatedExceptionTypes()` | `AnnotatedType[]` | Type annotations trên exception types |
| `isVarArgs()` | Có khai báo varargs hay không | Tham số cuối thường là một kiểu mảng ở reflection |
| `isSynthetic()` | Executable có do compiler sinh ra hay không | Không đồng nghĩa với tham số synthetic |
| `getAnnotatedReceiverType()` | Type use của receiver, nếu có | Có thể trả `null` tùy ngữ cảnh |
| `toGenericString()` | Biểu diễn khai báo có thông tin generic | Hữu ích khi debug, không nên parse thay vì dùng API cấu trúc |

Lưu ý `getParameterTypes()`, `getGenericParameterTypes()` và `getAnnotatedParameterTypes()` cùng quan sát danh sách tham số nhưng trả **ba cấp độ thông tin khác nhau**. Chọn đúng loại theo mục tiêu.

### Kiểu tham số qua erasure

Ví dụ:

~~~java
class Service {
    void save(java.util.List<String> records) {
    }
}
~~~

Với `Service.save`:

- `getParameterTypes()[0]` là `java.util.List.class`.
- `getGenericParameterTypes()[0]` có thể là `ParameterizedType` thể hiện `List<String>`.
- `getAnnotatedParameterTypes()[0]` là node `AnnotatedType` mô tả type use của `List<String>`, bao gồm các annotation trên kiểu và các type arguments được khai báo nếu có.

Không nên lấy `getParameterTypes()[0]` rồi kỳ vọng nó là một đối tượng đặc biệt đại diện `List<String>`; **type erasure** là thuộc tính nền tảng của Java generics.

## 3. Cách lấy Executable từ Class

Điểm khởi đầu thường là `Class<?>`. Bạn có thể tìm method hoặc constructor bằng tên/chữ ký:

~~~java
Method method =
        Service.class.getDeclaredMethod(
                "save", java.util.List.class);
~~~

Constructor:

~~~java
Constructor<Service> ctor =
        Service.class.getDeclaredConstructor();
~~~

Đây là ví dụ khi `Service` có constructor không tham số có thể tìm được. `getDeclaredMethod` và `getDeclaredConstructor` tìm thành phần **khai báo trực tiếp** trên class, bao gồm thành phần private (nhưng việc **invoke** vẫn chịu kiểm tra truy cập). Chúng không duyệt toàn bộ inherited methods theo cùng cách với `getMethod`.

Phân biệt:

| API của `Class` | Đối tượng trả về | Phạm vi tra cứu chủ yếu |
| --- | --- | --- |
| `getMethod(name, types...)` | `Method` | Public method, kể cả thành phần kế thừa được API tra cứu |
| `getDeclaredMethod(name, types...)` | `Method` | Method được khai báo trực tiếp, bất kể modifier |
| `getMethods()` | `Method[]` | Những public methods được API liệt kê |
| `getDeclaredMethods()` | `Method[]` | Các method khai báo trực tiếp |
| `getConstructor(types...)` | `Constructor<T>` | Public constructor của class |
| `getDeclaredConstructor(types...)` | `Constructor<T>` | Constructor khai báo trực tiếp, bất kể modifier |
| `getConstructors()` | `Constructor<?>[]` | Public constructors |
| `getDeclaredConstructors()` | `Constructor<?>[]` | Constructors khai báo trực tiếp |

**Không dựa vào thứ tự** `getDeclaredMethods()` hoặc `getDeclaredConstructors()` để suy luận method “đầu tiên” là method bạn muốn. Với overload, chọn đúng **tên và kiểu tham số**, hoặc lọc theo contract rõ ràng.

### Lookup dùng kiểu erasure, không dùng generic type arguments

Giả sử method:

~~~java
static <T extends Number> T identity(T value) {
    return value;
}
~~~

Khi tra cứu bằng reflection:

~~~java
Method m = Example.class.getDeclaredMethod(
        "identity", Number.class);
~~~

`T extends Number` có **erasure là `Number`**, nên parameter của reflective lookup là `Number.class`, không phải `Integer.class` hay một `Class<T>` tưởng tượng.

Với varargs:

~~~java
void join(String... parts) {
}
~~~

kiểu tham số phản chiếu là **`String[].class`**:

~~~java
Method m = Example.class.getDeclaredMethod(
        "join", String[].class);
~~~

Với một phương thức có overload, nhập sai `Class<?>` trong `getDeclaredMethod` thường tạo `NoSuchMethodException`, không có “overload resolution runtime như code Java thông thường” tự lựa chọn phương thức gần nhất cho bạn.

## 4. Parameter: mô hình một tham số phản chiếu

`Executable.getParameters()` trả một mảng các `java.lang.reflect.Parameter`:

~~~java
Executable executable = method;
Parameter[] parameters = executable.getParameters();
~~~

Mỗi `Parameter` cho biết:

| API `Parameter` | Ý nghĩa |
| --- | --- |
| `getName()` | Tên tham số được lưu hoặc tên tổng hợp nếu thiếu metadata |
| `isNamePresent()` | Metadata tên thực sự có trong class file theo cơ chế tương ứng hay không |
| `getType()` | Class của kiểu tham số sau erasure |
| `getParameterizedType()` | `Type` giữ thông tin generic |
| `getAnnotatedType()` | `AnnotatedType` của kiểu tham số |
| `getAnnotations()` / `getAnnotation(...)` | Annotation trên khai báo tham số |
| `getModifiers()` | Các modifier của tham số ở cấp reflection |
| `isVarArgs()` | Tham số có phải phần tử varargs cuối cùng hay không |
| `isImplicit()` | Tham số implicit theo cơ chế ngôn ngữ/compiler |
| `isSynthetic()` | Tham số do compiler tạo và được đánh dấu synthetic |
| `getDeclaringExecutable()` | `Executable` sở hữu tham số |

`Parameter` là **metadata object**, không phải giá trị tham số được truyền trong một lần thực thi method. Reflection cho phép đọc **khai báo**; nó không tự giữ lịch sử những giá trị đã từng được caller truyền vào method.

### Thứ tự các tham số

Các phần tử trong `getParameters()` tương ứng với danh sách tham số mà reflection nhìn thấy ở executable. Phần lớn methods thông thường phản ánh đúng danh sách trong source. Tuy nhiên, compiler có thể tạo tham số **implicit/synthetic** ở một số loại constructor hoặc cấu trúc ngôn ngữ, nên đừng áp đặt rằng mọi tham số đều được tác giả viết tường minh.

Đặc biệt khi viết framework hỗ trợ nhiều dạng class, hãy kiểm tra `isImplicit()`, `isSynthetic()`, tên, modifier và cách compiler đã sinh class file. Không quyết định hành vi chỉ dựa vào chỉ số `0` nếu constructor còn có tham số compiler-generated.

## 5. Tên tham số: vì sao cần javac -parameters?

Ví dụ source code:

~~~java
public void register(String username, int retries) {
}
~~~

Nếu muốn reflection lấy được tên **`username`** và **`retries`**, biên dịch bằng:

~~~bash
javac -parameters --release 17 Sample.java
~~~

Cờ `-parameters` yêu cầu javac ghi metadata tên tham số vào class file để `Parameter` có thể đọc khi chạy.

Khi đọc:

~~~java
for (Parameter p : method.getParameters()) {
    System.out.println(p.getName() + " / " + p.isNamePresent());
}
~~~

Với build đã giữ metadata tên, tên phản chiếu có thể là `username` và `retries`, đồng thời `isNamePresent()` là `true` cho các tham số tương ứng.

Nếu **không** có metadata tên, reflection có thể trả tên do runtime tổng hợp như `arg0`, `arg1` và `isNamePresent()` là `false`. Những tên tổng hợp này không phải API contract để xác định quy tắc nghiệp vụ.

**Cần phân biệt:**
- `-parameters` lưu tên tham số cho reflection.
- Thông tin debug như `-g` không thay thế `MethodParameters` metadata mà `Parameter.isNamePresent()` dùng. Đừng coi tên hiện trong IDE/debugger là bảo đảm tên cũng hiện qua API reflection.
- Cờ `-parameters` phải được cấu hình **ở build thật**, bao gồm Maven/Gradle hoặc trình biên dịch dùng trên CI, không chỉ ở một lệnh chạy thử tại máy phát triển.
- Nếu class được tạo bởi compiler khác, bytecode transformer hay code generation, cần kiểm tra metadata sau build; không mặc định trạng thái giống javac.

### Tên tham số không phải quy tắc xác thực

Có tên `username` không khiến Java tự yêu cầu dữ liệu phải là username hợp lệ; `retries` không tự kiểm tra lớn hơn 0. Tên tham số chỉ là **metadata**, còn validation phụ thuộc logic hoặc framework xử lý nó.

Một API có thể chọn dựa vào annotation hoặc cấu hình rõ ràng thay vì tên tham số nếu cần ổn định trước việc refactor/obfuscation. Việc đổi tên `username` có thể làm hệ thống dựa vào tên bị ảnh hưởng, nên cần tài liệu hóa contract.

## 6. Ví dụ đơn giản: cùng một bộ đọc metadata cho Method và Constructor

Thay vì hai hàm độc lập:

~~~java
static void inspectMethod(Method method) {
    System.out.println(method.getParameterCount());
}

static void inspectConstructor(Constructor<?> constructor) {
    System.out.println(constructor.getParameterCount());
}
~~~

có thể dùng **một** hàm nhận `Executable`:

~~~java
static void inspect(Executable executable) {
    System.out.println(executable.getName());
    for (Parameter parameter : executable.getParameters()) {
        System.out.println(parameter.getType().getTypeName());
    }
}
~~~

Gọi:

~~~java
inspect(SomeClass.class.getDeclaredMethod("run", String.class));
inspect(SomeClass.class.getDeclaredConstructor(String.class));
~~~

Các đoạn trên là **mã minh họa giả định `SomeClass` có đúng hai thành phần**, cần import và xử lý `NoSuchMethodException`. Ý chính là **polymorphism ở tầng reflection**: caller có thể đưa `Method` hoặc `Constructor<?>` và code dùng chung vẫn hoạt động.

### Khi nào phải quay về lớp con cụ thể?

`Executable` không cung cấp một thao tác chung tên `execute` để thay thế hai cơ chế khác nhau. Khi muốn gọi:

~~~java
Object result = method.invoke(receiver, args);
~~~

khi muốn tạo đối tượng:

~~~java
Object instance = constructor.newInstance(args);
~~~

Hai API này **thuộc hai lớp con khác nhau**. Nếu code nhận một `Executable` bất kỳ và cần thực thi, nó phải phân biệt `instanceof Method` và `instanceof Constructor<?>`, kiểm tra quyền truy cập và xử lý exception theo đúng trường hợp.

## 7. Annotation trên declaration khác annotation trên type use

Đây là một phân biệt rất quan trọng của Java Reflection hiện đại. Xem hai annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface NamedInput {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TaggedType {
    String value();
}
~~~

Một method có thể viết:

~~~java
void send(
        @NamedInput("request")
        @TaggedType("non-empty-text") String payload) {
}
~~~

`@NamedInput` nằm ở **parameter declaration**. `@TaggedType` nằm ở **type use `String`**. Hai loại metadata có thể được đọc qua các API khác nhau.

~~~java
Parameter parameter = method.getParameters()[0];

NamedInput name = parameter.getAnnotation(NamedInput.class);
TaggedType tag = parameter.getAnnotatedType()
                          .getAnnotation(TaggedType.class);
~~~

Tương đương ở cấp `Executable`:

~~~java
java.lang.annotation.Annotation[][] declarations =
        executable.getParameterAnnotations();

AnnotatedType[] annotatedTypes =
        executable.getAnnotatedParameterTypes();
~~~

**Không giả định** annotation target `TYPE_USE` sẽ xuất hiện khi gọi `parameter.getAnnotation(...)` trên parameter declaration, hoặc annotation target `PARAMETER` sẽ xuất hiện trong `getAnnotatedType()`. Nếu framework hỗ trợ cả hai, nó cần đọc đúng vị trí.

### @Retention quyết định khả năng đọc runtime

Nếu annotation cần được lấy qua `getAnnotation(...)` lúc chạy, nó thường phải có:

~~~java
@Retention(RetentionPolicy.RUNTIME)
~~~

Mặc định retention là `CLASS` nếu không khai báo. `CLASS` không bảo đảm annotation xuất hiện qua reflection runtime chuẩn. `RUNTIME` cho phép đọc metadata nhưng **không tự chạy validation**.

Ví dụ một marker `@NonNull` chỉ được định nghĩa bằng `@Target(TYPE_USE)` không tự khiến javac cấm null; cần checker hoặc logic thực thi hợp đồng.

## 8. Kiểu tham số: raw, generic, annotated

Giả sử:

~~~java
class Handler {
    void process(
            java.util.List<@TaggedType("item") String> names) {
    }
}
~~~

Với method `process`:

~~~java
Executable executable =
        Handler.class.getDeclaredMethod(
                "process", java.util.List.class);
~~~

Ba góc nhìn:

**1. Kiểu Class sau erasure**

~~~java
Class<?> raw =
        executable.getParameterTypes()[0];

// raw == java.util.List.class
~~~

**2. Kiểu generic**

~~~java
java.lang.reflect.Type type =
        executable.getGenericParameterTypes()[0];

// type có thể là ParameterizedType cho List<String>
~~~

**3. Kiểu có type annotations**

~~~java
AnnotatedType annotated =
        executable.getAnnotatedParameterTypes()[0];
~~~

Nếu muốn đọc metadata bên trong `List<@TaggedType String>`, khi annotated type là `AnnotatedParameterizedType`:

~~~java
java.lang.reflect.AnnotatedParameterizedType listType =
        (java.lang.reflect.AnnotatedParameterizedType) annotated;

AnnotatedType element =
        listType.getAnnotatedActualTypeArguments()[0];
~~~

`element.getAnnotation(TaggedType.class)` lấy annotation ở **kiểu String** bên trong danh sách. Đây là lý do `AnnotatedType` không thể bị thay thế bằng `Class<?>` trong mọi tool.

## 9. Generic method và type parameters của Executable

`Executable.getTypeParameters()` trả về các **type parameters do chính method hoặc constructor khai báo**, chứ không mặc nhiên gồm mọi type parameter của class bao ngoài.

Ví dụ:

~~~java
class Tools {
    static <T extends Number> T identity(T value) {
        return value;
    }
}
~~~

Reflection:

~~~java
Method identity =
        Tools.class.getDeclaredMethod(
                "identity", Number.class);

java.lang.reflect.TypeVariable<?>[] vars =
        identity.getTypeParameters();
~~~

`vars.length` là `1` và `vars[0].getName()` là `"T"`. `getParameterTypes()[0]` là `Number.class` do erasure của `T extends Number`.

Nếu class `Box<T>` có method không khai báo generic type parameters riêng, `method.getTypeParameters()` có thể rỗng dù method dùng type variable `T` của class. Khi cần type parameters của **class**, hãy đọc `Box.class.getTypeParameters()`.

### Generic exception types

Generic methods có thể khai báo type variables trong throws clause khi phù hợp các giới hạn của Java. `getGenericExceptionTypes()` giữ cấu trúc `Type`, còn `getExceptionTypes()` đưa về `Class<?>` sau erasure. Nếu có annotation trên exception types, `getAnnotatedExceptionTypes()` cho truy cập type-use metadata.

**Tài liệu hóa** khác biệt này quan trọng nếu framework cần công bố generic API signatures thay vì chỉ xử lý runtime classes.

## 10. Varargs: vẫn là array trong metadata

Ví dụ:

~~~java
public String combine(String... parts) {
    return String.join("|", parts);
}
~~~

Trong source, caller có thể gọi `combine("a", "b")`, nhưng ở reflection:

- `Executable.isVarArgs()` trả `true`.
- `getParameterTypes()` chứa một kiểu tham số cuối là `String[].class`.
- `getParameters()[lastIndex].isVarArgs()` cho biết tham số cuối ấy có là varargs parameter không.

Để lookup:

~~~java
Method combine =
        Example.class.getDeclaredMethod(
                "combine", String[].class);
~~~

Đừng viết `getDeclaredMethod("combine", String.class)` chỉ vì lúc gọi thường truyền một chuỗi. Phản chiếu dùng **chữ ký của phương thức sau biên dịch**.

### Gọi varargs method qua Method.invoke

`Method.invoke(Object receiver, Object... args)` bản thân nó có `Object... args`. Vì thế, để truyền một **mảng String như một đối số duy nhất của phương thức đích**, có thể viết:

~~~java
Object result = combine.invoke(
        receiver, (Object) new String[]{"a", "b"});
~~~

Đây là **mã minh họa** với `combine` là `Method` và `receiver` là đối tượng phù hợp. Cast mảng thành `Object` giúp phân biệt mảng cần truyền làm **một argument** cho target method với varargs của chính `Method.invoke`.

**Đừng coi reflective invoke là một overload resolver tự xử lý mọi varargs giống syntax Java bình thường**. Reflection dựa trên method đã được tìm và argument array; việc truyền sai hình dạng có thể gây `IllegalArgumentException`.

## 11. Tham số implicit và synthetic

Đây là lý do một tool cần đọc metadata cẩn thận thay vì luôn tin rằng `getParameterCount()` bằng số tên tham số hiển thị trong source.

- **Implicit parameter**: tham số được đưa vào trong mô hình method/constructor bởi cấu trúc ngôn ngữ, không nhất thiết được viết trong source như một formal parameter bình thường.
- **Synthetic parameter**: tham số do compiler tạo, đánh dấu bằng thông tin synthetic.
- `Parameter.isImplicit()`, `Parameter.isSynthetic()` được cung cấp để công cụ có thể phân biệt khi metadata thích hợp.

Các tình huống như **constructor của non-static inner class**, enum constructor hoặc lớp được compiler sinh ra có thể mang tham số không tương ứng 1-1 với danh sách source thông thường.

Điểm thực tế:

1. Với constructor của **inner class không static**, compiler có thể phải truyền enclosing instance.
2. Với **static nested class**, thường không có enclosing-instance argument như non-static inner class.
3. Với **record**, tham số constructor có các quy tắc tên/modifier/metadata riêng từ các bản Java hỗ trợ records; cần kiểm tra API/bytecode cụ thể, không mặc định mọi constructor giống class thường.
4. Các compiler, code generators và bytecode enhancers có thể thêm method/parameter synthetic.
5. Nếu tool phụ thuộc vào **tên hoặc tính implicit/synthetic**, kiểm tra `isNamePresent()`, `isImplicit()`, `isSynthetic()` trên build thực tế.

Không dùng ví dụ này để khuyến khích sửa bytecode theo giả định thủ công. Mục tiêu là đọc đúng dữ liệu thật do reflection báo về.

## 12. Return type: điểm khác biệt giữa Method và Constructor

`Method` có các API riêng:

~~~java
Class<?> returnType = method.getReturnType();
java.lang.reflect.Type genericResult =
        method.getGenericReturnType();
~~~

`getReturnType()` trả `void.class` với method trả `void`; `getGenericReturnType()` phục vụ generic result types.

Constructor **không** có return type theo cú pháp khai báo của Java, vì nhiệm vụ của nó là khởi tạo instance. Khi muốn nhận instance từ reflection:

~~~java
Object instance = constructor.newInstance(arguments);
~~~

Không viết `constructor.getReturnType()` như cách gọi `Method.getReturnType()` vì đây **không** là API chung mà `Executable` cho phép.

`Executable` có các API annotated-type chung (ví dụ `getAnnotatedReturnType()`), nhưng **đừng vì có một phương thức tên chung mà suy ra constructor có return type khai báo như method**. Khi viết công cụ xử lý return-value contract, thường cần phân biệt `Method` và `Constructor<?>` theo ý nghĩa thực tế.

### getAnnotatedReceiverType

`Executable.getAnnotatedReceiverType()` cho phép truy vấn type-use metadata của **receiver** khi có receiver phù hợp. Trong nhiều static methods, kết quả có thể là `null` vì không có receiver instance.

Đây là góc cạnh hữu ích cho static analyzers. Không nhầm receiver type với **tham số đầu tiên thông thường** và không tự giả định mọi method đều có receiver annotation. Khi code cần xử lý receiver metadata, phải kiểm tra `null`.

## 13. Modifier, declaring class và tên executable

`Executable.getModifiers()` trả bitmask. Dùng `java.lang.reflect.Modifier` để diễn giải:

~~~java
int flags = executable.getModifiers();

boolean isPublic = Modifier.isPublic(flags);
boolean isStatic = Modifier.isStatic(flags);
~~~

Các phương thức này không phải validation của nghiệp vụ. Modifier chỉ cho biết thuộc tính của declaration theo ngôn ngữ/bytecode.

`getDeclaringClass()` trả class/interface sở hữu declaration:

~~~java
Class<?> owner = executable.getDeclaringClass();
~~~

Nếu bạn lấy một inherited public method qua reflection trên lớp con, **declaring class có thể là superclass/interface**. Không mặc định owner luôn là class bạn gọi `getMethod(...)` trên đó.

Đối với `getName()`:
- `Method.getName()` là tên method, như `"save"`.
- `Constructor.getName()` mô tả tên của declaring class theo hợp đồng reflection, không phải method tên `"<init>"` dùng như một public Java source identifier.

**Không parse `toString()` / `toGenericString()` để lấy parameter names, modifiers hay generic types.** Các API cấu trúc riêng ít lỗi hơn và rõ ràng hơn.

## 14. Chương trình Java 17+ hoàn chỉnh: cùng API cho method và constructor

Tạo tệp **`ExecutableMetadataDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Parameter;

public class ExecutableMetadataDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Label {
        String value();
    }

    static final class Order {
        private final String customer;
        private final int quantity;

        public Order(@Label("buyer") String customer, int quantity) {
            this.customer = customer;
            this.quantity = quantity;
        }

        public String summarize(
                @Label("prefix") String prefix,
                int multiplier) {
            return prefix + customer + ":" + (quantity * multiplier);
        }

        public static <T extends Number> T identity(T value) {
            return value;
        }

        public String join(String... parts) {
            return String.join("|", parts);
        }
    }

    static void inspect(Executable executable) {
        String kind = executable instanceof Constructor<?>
                ? "constructor" : "method";
        System.out.println("kind=" + kind);
        System.out.println("parameters=" +
                executable.getParameterCount());

        for (Parameter p : executable.getParameters()) {
            Label label = p.getAnnotation(Label.class);
            String labelValue =
                    label == null ? "-" : label.value();

            System.out.println("param=" + p.getName()
                    + ":" + p.getType().getSimpleName()
                    + ":named=" + p.isNamePresent()
                    + ":label=" + labelValue);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Constructor<Order> constructor =
                Order.class.getDeclaredConstructor(
                        String.class, int.class);

        Method summarize =
                Order.class.getDeclaredMethod(
                        "summarize", String.class, int.class);

        Method identity =
                Order.class.getDeclaredMethod(
                        "identity", Number.class);

        Method join =
                Order.class.getDeclaredMethod(
                        "join", String[].class);

        inspect(constructor);
        inspect(summarize);

        System.out.println("return=" +
                summarize.getReturnType().getSimpleName());

        System.out.println("generic-parameter=" +
                identity.getTypeParameters()[0].getName());

        System.out.println("erased-parameter=" +
                identity.getParameterTypes()[0].getSimpleName());

        System.out.println("static=" +
                Modifier.isStatic(identity.getModifiers()));

        System.out.println("varargs=" + join.isVarArgs());

        System.out.println("last-varargs=" +
                join.getParameters()[0].isVarArgs());

        Order order = constructor.newInstance("Lan", 3);
        Object result = summarize.invoke(
                order, "order=", 2);

        System.out.println("invoke=" + result);
    }
}
~~~

Biên dịch bằng JDK 17 hoặc bản mới hơn có hỗ trợ `--release 17` và **bật lưu tên tham số**:

~~~bash
javac --release 17 -parameters ExecutableMetadataDemo.java
java ExecutableMetadataDemo
~~~

**Stdout chính xác khi biên dịch với `-parameters`:**

~~~text
kind=constructor
parameters=2
param=customer:String:named=true:label=buyer
param=quantity:int:named=true:label=-
kind=method
parameters=2
param=prefix:String:named=true:label=prefix
param=multiplier:int:named=true:label=-
return=String
generic-parameter=T
erased-parameter=Number
static=true
varargs=true
last-varargs=true
invoke=order=Lan:6
~~~

### Kiểm tra vì sao ví dụ biên dịch/chạy đúng

1. `Order` là **static nested class**, nên constructor được khai báo `Order(String,int)` và có thể lookup bằng đúng hai `Class<?>`; không có enclosing-instance argument bắt buộc như non-static inner class.
2. `@Label` có `RUNTIME` retention và `PARAMETER` target, vì vậy `Parameter.getAnnotation(Label.class)` trả marker ở hai tham số được đánh dấu.
3. `-parameters` làm compiler ghi tên `customer`, `quantity`, `prefix`, `multiplier`; `isNamePresent()` là `true` khi metadata tên được giữ.
4. `summarize(String,int)` trả `String`, nên `getReturnType().getSimpleName()` là `String`.
5. `identity` khai báo type parameter `<T extends Number>`; `getTypeParameters()[0].getName()` là `T`. Khi dùng `getDeclaredMethod`, tham số bị erasure thành `Number.class`.
6. `Modifier.isStatic(...)` trả `true` cho `identity`.
7. `join(String... parts)` là varargs; reflection thấy một tham số mảng `String[]`. `join.isVarArgs()` và `getParameters()[0].isVarArgs()` đều `true`.
8. `constructor.newInstance("Lan", 3)` tạo `Order`; `summarize.invoke(order, "order=", 2)` tạo chuỗi `"order=Lan:6"`.
9. `main` khai báo `throws ReflectiveOperationException`, là superclass của các checked exceptions reflection phù hợp trong đoạn code (`NoSuchMethodException`, `InstantiationException`, `IllegalAccessException`, `InvocationTargetException`). `summarize` và constructor ở đây **không khai báo thêm checked exception nghiệp vụ** cần xử lý.

**Lưu ý:** Nếu bạn bỏ `-parameters` khi biên dịch, phần in **tên tham số** và `named` sẽ đổi theo metadata thực có; ví dụ không còn cam kết stdout bên trên. Dùng đúng lệnh biên dịch đã nêu khi muốn so sánh nguyên văn.

### Bài học từ ví dụ

`inspect(Executable executable)` dùng chung cho constructor và method, nhưng phần thực thi vẫn tách:

- `constructor.newInstance(...)` tạo object.
- `summarize.invoke(...)` gọi method đã tìm trên instance đó.

Khi cần introspection, `Executable` giảm mã lặp; khi cần gọi cụ thể, phải dùng đúng loại `Method` hoặc `Constructor<?>`.

## 15. Invocation và xử lý ngoại lệ

Method invocation:

~~~java
Object value = method.invoke(receiver, arguments);
~~~

Constructor invocation:

~~~java
Object created = constructor.newInstance(arguments);
~~~

Hai thao tác đều chịu kiểm tra kiểu, quyền truy cập và exception. Một số lỗi thường gặp:

| Tình huống | Ngoại lệ / ý nghĩa |
| --- | --- |
| Không tìm đúng chữ ký | `NoSuchMethodException` tại lookup |
| Không được phép truy cập | `IllegalAccessException` trong những trường hợp tương ứng |
| Truyền sai số lượng/kiểu argument | `IllegalArgumentException` |
| Method/constructor được gọi ném exception | Có thể được bọc trong `InvocationTargetException` |
| Constructor thuộc abstract class | Không thể tạo instance kiểu abstract; `InstantiationException` có thể phát sinh trong trường hợp phù hợp |
| Cố mở truy cập thành phần bị module hạn chế | Có thể gặp `InaccessibleObjectException` hoặc không thể mở accessibility |

**Quan trọng:** `InvocationTargetException` mang exception của code **bên trong method/constructor đang được gọi**. Một lệnh gọi thành công về mặt reflection có thể vẫn thất bại vì logic được gọi ném exception. Khi debug, kiểm tra `getCause()` của wrapper thay vì chỉ log tên `InvocationTargetException`.

### Cẩn trọng với accessible members và Java modules

Kể từ Java 9, JPMS (Java Platform Module System) tạo thêm quy tắc đóng gói mạnh cho modules. Việc dùng `setAccessible(true)` hoặc `trySetAccessible()` không phải giấy phép vượt mọi ranh giới module. Truy cập sâu vào các thành phần non-public của thư viện/JDK có thể bị từ chối nếu package không được mở thích hợp.

Trong framework hiện đại, nên:
- Ưu tiên public API khi có thể.
- Tránh dựa vào internal JDK APIs.
- Nếu cần reflection sâu, hiểu `exports`/`opens` của module chứa package liên quan.
- Hạn chế dùng các command-line flags mở toàn bộ modules mà không có lý do rõ ràng và biện pháp kiểm soát.
- Dùng `MethodHandles` khi phù hợp kiến trúc/performance, nhưng vẫn tôn trọng quy tắc access control.

Reflection cần quản lý quyền truy cập như một phần của API design, không phải một cơ chế mặc định bỏ kiểm tra bảo mật của Java.

## 16. Executable metadata trong framework thực tế

### A. Router / dependency injection

Một framework cần:
1. Tìm constructor phù hợp.
2. Đọc `Parameter[]` của constructor.
3. Kiểm tra annotation như `@Named`, `@Qualifier` trên **declarations**.
4. Đọc kiểu/generic type của tham số để xác định dependency.
5. Xác định chính sách khi tên param không có do thiếu `-parameters`.
6. Tạo instance bằng một cơ chế invocation phù hợp, xử lý lỗi có ngữ cảnh.

`Executable` giúp framework sử dụng một pipeline đọc tham số chung cho cả constructor injection và method injection, nhưng việc **resolve dependency** là hành vi của framework, không tự có trong JDK.

### B. HTTP endpoint / RPC

Một hệ thống có thể đọc metadata method parameters để ánh xạ route/query/body. Cần phân biệt:
- Tên tham số source (có thể thiếu).
- Annotation `@PathVariable`/`@RequestParam` của một framework cụ thể.
- Type argument như `List<Order>`.
- Validation annotation có được runtime processor xử lý không.

Không tự suy rằng một annotation giống tên trong framework khác sẽ có cùng ý nghĩa; package, version và contract của thư viện mới quyết định điều đó.

### C. Công cụ tài liệu hóa API

Một doc generator có thể in:
- `getDeclaringClass()`, `getName()`.
- Kiểu generic/annotation của tham số.
- Modifier và exceptions.
- Sự khác nhau giữa methods và constructors.
- Tên tham số nếu đã lưu.

Nếu chỉ in `toGenericString()` rồi dùng regex parse lại để tìm kiểu, bạn đã bỏ qua những API cấu trúc Java cung cấp.

### D. Unit tests cho metadata

Một test có thể xác nhận `-parameters` được bật:

~~~java
Method method =
        Service.class.getDeclaredMethod(
                "execute", String.class);

Parameter p = method.getParameters()[0];

if (!p.isNamePresent()) {
    throw new AssertionError(
            "Compile with -parameters");
}
~~~

Đây là **mã minh họa**: cần `Service.execute(String)` và xử lý lookup exception trong test. Nếu một framework phụ thuộc vào tên thật, test trên artifact/build thật giúp phát hiện sai cấu hình sớm.

## 17. Những hiểu nhầm dễ gây lỗi

1. **“Executable có phương thức invoke chung.”** Không; dùng `Method.invoke` hoặc `Constructor.newInstance`.
2. **“Method và constructor giống hệt nhau vì cùng kế thừa Executable.”** Chúng có metadata chung, nhưng khác ý nghĩa, lookup và invocation.
3. **“getParameterTypes trả đầy đủ generic.”** Không; nó trả `Class<?>[]` sau erasure. Xem `getGenericParameterTypes()` khi cần.
4. **“Reflection luôn thấy tên tham số trong source.”** Không; phụ thuộc class file metadata, thường cần `javac -parameters`.
5. **“Có debug symbols thì isNamePresent phải true.”** Không; debug local variable tables không thay thế `MethodParameters` metadata.
6. **“Parameter là đối số runtime.”** Không; nó mô tả khai báo, không giữ giá trị đã truyền trong lời gọi.
7. **“getParameterCount luôn bằng số tham số nhìn thấy trong source.”** Không tuyệt đối; có implicit/synthetic parameters ở một số trường hợp.
8. **“Constructor non-static inner class không có tham số bổ sung.”** Có thể cần enclosing-instance argument.
9. **“Method varargs nhận mỗi phần tử reflection như một tham số riêng.”** Không; tham số varargs biểu diễn thành mảng trong signature.
10. **“getDeclaredMethod(..., String.class) tìm được method nhận List<String>.”** Không; lookup dùng `List.class` cho generic List parameter.
11. **“Annotation trên kiểu tham số và annotation trên declaration là một.”** Không; API đọc khác nhau.
12. **“@Retention(RUNTIME) tự chạy validation.”** Không; nó chỉ giữ metadata cho runtime đọc.
13. **“setAccessible(true) vượt được mọi module boundary.”** Không; JPMS có ràng buộc truy cập.
14. **“getDeclaredMethods có thứ tự như source.”** Không có bảo đảm sắp xếp như vậy.
15. **“Đọc Method.getReturnType trực tiếp trên Executable.”** Không; `getReturnType()` là API của `Method`.
16. **“getTypeParameters() của method luôn bao gồm type parameters của class.”** Không; hai tập khai báo khác nhau.
17. **“Lỗi trong method được invoke đi ra nguyên dạng.”** Có thể bị bọc trong `InvocationTargetException`.
18. **“Reflection tự kiểm tra nghiệp vụ dựa vào tên, annotation.”** Không; cần validation/checker/framework đã được triển khai.

## 18. Bài tập thực hành

**Bài 1 — Cùng một hàm inspect.** Tạo class `Account` có constructor `Account(String id)` và method `void rename(String label)`. Dùng một phương thức `inspect(Executable e)` in số tham số và kiểu tham số của cả hai.

**Bài 2 — So sánh ba góc nhìn.** Viết method `void accept(List<String> values)`; từ reflection, dùng `getParameterTypes()`, `getGenericParameterTypes()` và `getAnnotatedParameterTypes()`. Giải thích vì sao cái đầu chỉ thấy `List.class`.

**Bài 3 — Tên tham số.** Biên dịch cùng một class có method `void send(String address, int retries)` một lần với `-parameters` và một lần không có. Quan sát `getName()` và `isNamePresent()`; vì sao code production không nên dựa vào tên `arg0`?

**Bài 4 — Annotation vị trí.** Tự định nghĩa `@Target(PARAMETER)` và `@Target(TYPE_USE)`. Đặt cả hai trên một tham số, rồi đọc lần lượt qua `Parameter.getAnnotation` và `Parameter.getAnnotatedType().getAnnotation`.

**Bài 5 — Generic method.** Viết `static <T extends Number> T pass(T value)`. Vì sao `getDeclaredMethod("pass", Integer.class)` không tìm được chữ ký này, trong khi `Number.class` lại thích hợp?

**Bài 6 — Varargs.** Với `String join(String... pieces)`, chỉ rõ kiểu `Class<?>` cần dùng trong reflective lookup và cách gọi `Method.invoke` truyền một mảng chuỗi làm đối số duy nhất.

**Bài 7 — Reflection invocation.** Dùng `Constructor.newInstance` để tạo instance, sau đó dùng `Method.invoke` gọi một method công khai. Bắt đúng exception cần thiết và giải thích vai trò của `InvocationTargetException.getCause()`.

**Bài 8 — Implicit/synthetic.** Phân biệt class lồng `static` và non-static inner class về enclosing instance. Giải thích vì sao công cụ đọc constructor metadata phải xem `Parameter.isImplicit()`/`isSynthetic()` và không chỉ đếm tham số source.

**Bài 9 — Overload.** Một class có `process(String)` và `process(Object)`. Bạn sẽ dùng `getDeclaredMethod` như thế nào để chọn đúng một signature? Vì sao chỉ truyền tên method là không đủ?

**Bài 10 — Modules.** Nếu `setAccessible(true)` thất bại trên thành phần private của một module khác, điều gì cần kiểm tra trong `module-info.java`? Vì sao không nên bật mở toàn bộ module như giải pháp mặc định?

## 19. Checklist dùng Executable an toàn trong hệ thống hiện đại

Khi phát triển thư viện/framework dùng Reflection:

1. **Chọn đúng phạm vi lookup**: public inherited hay declared members.
2. **Định danh signature rõ ràng**: tên + kiểu tham số sau erasure.
3. **Dùng Executable cho metadata chung**, phân biệt Method/Constructor khi invoke.
4. **Không giả định thứ tự phản chiếu** của danh sách methods/constructors.
5. **Kiểm tra metadata tên** bằng `isNamePresent()`; cấu hình `-parameters` ở build nếu cần.
6. **Đọc kiểu theo mục đích**: `Class<?>` vs `Type` vs `AnnotatedType`.
7. **Đọc annotation đúng vị trí**: parameter declaration vs type use.
8. **Xem implicit/synthetic/varargs** khi mapping tham số phức tạp.
9. **Không coi tên/annotation là validation tự động**.
10. **Kiểm tra access rules** của visibility và JPMS modules.
11. **Xử lý lỗi được gọi** qua `InvocationTargetException` và cause.
12. **Test trên artifact thực tế** của build, nhất là metadata do compiler/plugin sinh ra.
13. **Tránh phụ thuộc internal JDK APIs** hoặc giả định có thể phá đóng gói.
14. **Ghi nhận giới hạn của generics erasure**, không suy type arguments của từng instance chỉ từ `getClass()`.

## 20. Tổng kết

- `Executable` là **lớp trừu tượng chung cho `Method` và `Constructor<T>`** trong Java Reflection, dùng để truy cập metadata về tham số và những đặc điểm chung của executable.
- `getParameters()` trả `Parameter[]`; `Parameter` cho biết tên, kiểu, annotation, varargs, trạng thái implicit/synthetic và declaring executable.
- **Tên tham số chỉ đáng tin khi metadata được lưu**, thường bằng `javac -parameters`; `isNamePresent()` là bước kiểm tra cần thiết.
- **`getParameterTypes()` khác `getGenericParameterTypes()` và `getAnnotatedParameterTypes()`**, tương ứng raw/erased, generic, annotated type.
- `Method.invoke` và `Constructor.newInstance` là **hai cách thực thi khác nhau**; `Executable` không hợp nhất chúng thành một lệnh gọi chung.
- Reflection có thể ném lỗi lookup, access, invocation và module access; cần xử lý đúng bối cảnh.
- Đọc metadata **không tự thực thi validation** và không vượt qua type erasure.
- API này xuất hiện từ Java 8 và **vẫn được áp dụng trong Java 17+ và các bản Java hiện hành**; khi kết hợp tính năng hiện đại như JPMS hay records, nên đối chiếu Javadoc/JLS theo JDK mục tiêu.

## 21. Tài liệu chuẩn

1. Java SE 17 API, **Executable**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
2. Java SE 17 API, **Parameter**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html
3. Java SE 17 API, **Method**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
4. Java SE 17 API, **Constructor**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
5. Java SE 17 API, **Type** và **AnnotatedType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html
6. Java SE 17 API, **Modifier**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html
7. Java SE 17 API, **InvocationTargetException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html
8. Java SE 17 API, **InaccessibleObjectException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
9. JDK 17, **javac -parameters**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
10. Java Language Specification, **`8.4 Method Declarations và `8.8 Constructor Declarations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html

Khi dùng metadata tham số để tạo public contract trong framework, hãy xác minh annotation target/retention, cách compiler tạo class file, cờ `-parameters` và module access trên chính JDK được dự án sử dụng. Đó là các yếu tố quyết định một hệ thống Reflection có thể vận hành ổn định, không phải số lượng API mà code gọi được.