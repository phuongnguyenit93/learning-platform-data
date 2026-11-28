# `getMethods()` và `getDeclaredMethods()`: xử lý tập kết quả mà không phụ thuộc thứ tự

## 1. Vấn đề: Reflection trả về mảng, nhưng không hứa thứ tự

Khi xây framework, bộ kiểm tra API, công cụ sinh tài liệu hoặc cơ chế plugin bằng Java Reflection, ta thường bắt đầu bằng hai lời gọi:

```java
Method[] publicMethods = type.getMethods();
Method[] declaredMethods = type.getDeclaredMethods();
```

Một lỗi dễ mắc là cho rằng phần tử đầu tiên là phương thức viết đầu tiên trong mã nguồn, các phương thức `public` luôn đứng trước `private`, hoặc kết quả sẽ giữ nguyên thứ tự khi thay JDK, compiler hay cách tải class.

**Hợp đồng API Java SE quy định rõ: các phần tử của cả hai mảng không được sắp xếp và không có thứ tự xác định.** Vì vậy:

- Không chọn `methods[0]` làm phương thức ưu tiên.
- Không viết test dựa trên vị trí phần tử hoặc thứ tự in ra mặc định.
- Không giả định thứ tự là thứ tự khai báo trong file `.java`.
- Không coi thứ tự quan sát được trên một JDK là cam kết cho các JDK khác.
- Nếu cần đầu ra dễ đọc và ổn định, **tự chọn tiêu chí sắp xếp**.
- Nếu chỉ cần xác nhận phương thức có tồn tại, **lọc, tra cứu trực tiếp hoặc so sánh theo tập hợp**.

Bài thuộc chương **Hợp đồng reflection** của mô-đun `JAVA_VERSION_JAVA18`. Java 18 có **JEP 416**, chuyển cách triển khai core reflection sang dựa trên method handles. Đó là thay đổi triển khai; không phải bảo đảm mới rằng mảng `Method[]` có thứ tự. Kiến thức về hợp đồng `Class.getMethods()` và `Class.getDeclaredMethods()` vẫn có giá trị trên các JDK hiện đại.

## 2. Hai API trả về những phương thức nào?

`Class<?>` cung cấp hai cách liệt kê phổ biến với phạm vi khác nhau:

| Đặc điểm | `getMethods()` | `getDeclaredMethods()` |
| --- | --- | --- |
| Mức truy cập | Các phương thức `public` | `public`, `protected`, package-private, `private` |
| Phương thức khai báo trực tiếp | Có, nếu thuộc tập public được chọn | Có, bất kể mức truy cập |
| Phương thức kế thừa từ superclass | Có, theo quy tắc chọn public member | Không |
| Phương thức từ superinterface | Có, theo quy tắc chọn public member | Không |
| Các phương thức của `Object` trên một class thông thường | Có thể có các phương thức public kế thừa | Không, trừ khi class tự khai báo/override |
| Bridge/synthetic method | Có thể có nếu nằm trong tập public được chọn | Có thể có, kể cả không có trong source |
| Constructor | Không | Không |
| Thứ tự kết quả | Không xác định | Không xác định |

Cả hai trả về `Method[]`. Chúng không giống nhau và **không phải** chỉ khác ở một bước lọc `Modifier.isPublic(...)`: `getMethods()` còn xem xét kế thừa, override và các quy tắc chọn phương thức public.

### 2.1. `getMethods()`: public methods của kiểu và các kiểu liên quan

`type.getMethods()` trả về tập các public member methods của class hoặc interface, bao gồm phương thức khai báo tại kiểu đó và những phương thức được kế thừa theo quy tắc của ngôn ngữ Java.

Nếu class `Child` extends `Parent` và implements `Named`, danh sách có thể chứa:

- Phương thức public khai báo bởi `Child`.
- Phương thức public kế thừa từ `Parent`.
- Phương thức public thích hợp từ `Named` hoặc superinterface.
- Các phương thức public kế thừa từ `Object`, như `toString`.

Nhưng nếu class override một phương thức, `getMethods()` áp dụng quy tắc chọn phương thức **most-specific** thay vì đơn giản nối mọi mảng từ cha và interface. Với phương thức cùng tên, parameter types và return type, một khai báo cụ thể hơn có thể thay thế khai báo từ kiểu cha trong tập kết quả.

### 2.2. `getDeclaredMethods()`: tất cả method được khai báo ngay tại kiểu

`type.getDeclaredMethods()` trả về các method khai báo bởi đúng class hoặc interface đó, gồm cả `private`, `protected` và package-private, nhưng **không** lấy phương thức kế thừa.

Đây là API hợp lý để khám phá các phương thức do bản thân một class khai báo, nhưng kết quả vẫn có thể chứa:

- Phương thức trình biên dịch tự tạo, chẳng hạn bridge methods.
- Phương thức synthetic do compiler sinh ra.
- Nhiều phương thức có cùng tên và cùng parameter types nhưng khác return type ở mức JVM.

Nó không trả về `<init>` (constructor) hoặc `<clinit>` (class initializer). Muốn liệt kê constructor, dùng `getDeclaredConstructors()`.

### 2.3. Trường hợp interface, array và primitive

Tài liệu Java SE 24 mô tả thêm:

- Với một **interface**, `getMethods()` không tự thêm các phương thức của `Object` nếu interface không khai báo hoặc kế thừa chúng từ superinterface.
- Với một **array class**, `getMethods()` gồm các public method kế thừa từ `Object`, nhưng không có phần tử đại diện cho `clone()`.
- Với **array, primitive hoặc `void`**, `getDeclaredMethods()` trả mảng rỗng.
- Không phương thức nào trong `getMethods()` mang tên `<init>` hoặc `<clinit>`.

Các trường hợp này cho thấy không thể viết một bộ lọc tổng quát dựa vào thứ tự hay số lượng method mà không hiểu loại `Class<?>` đang được phản chiếu.

## 3. Ví dụ hoàn chỉnh: một class có kế thừa, overload và nhiều mức truy cập

Tạo file `ReflectionOrderDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class ReflectionOrderDemo {

    interface Named {
        default String title() {
            return "Được đặt tên";
        }
    }

    static class Parent {
        public String inherited() {
            return "Từ Parent";
        }

        protected void parentProtected() {}
    }

    static class Child extends Parent implements Named {
        public void save(String value) {}
        public void save(int value) {}

        protected void validate() {}
        void packageOnly() {}
        private void secret() {}
    }

    static String signature(Method method) {
        String params = Arrays.stream(method.getParameterTypes())
                .map(Class::getTypeName)
                .collect(Collectors.joining(","));

        return method.getDeclaringClass().getName()
                + "#" + method.getName()
                + "(" + params + ")"
                + ":" + method.getReturnType().getTypeName();
    }

    static void printSorted(String title, Method[] methods) {
        System.out.println(title + " (" + methods.length + "):");
        Arrays.stream(methods)
                .sorted(Comparator.comparing(
                        ReflectionOrderDemo::signature))
                .map(ReflectionOrderDemo::signature)
                .forEach(System.out::println);
    }

    public static void main(String[] args) {
        printSorted("getMethods()",
                Child.class.getMethods());

        printSorted("getDeclaredMethods()",
                Child.class.getDeclaredMethods());
    }
}
```

Chạy bằng JDK hiện đại:

```bash
javac -encoding UTF-8 ReflectionOrderDemo.java
java ReflectionOrderDemo
```

**Lưu ý:** code chủ động sắp xếp **trước khi in**. Thứ tự hiển thị là do `Comparator` của chương trình tạo ra, **không** phải thứ tự mà Reflection API bảo đảm.

### 3.1. Phân tích tập `getMethods()`

Trong phần public methods của `Child`, hãy tìm theo tên và declaring class:

| Method quan sát được | Vì sao có mặt? |
| --- | --- |
| `Child.save(java.lang.String)` | Public method khai báo tại Child |
| `Child.save(int)` | Public overload thứ hai |
| `Parent.inherited()` | Public method kế thừa từ superclass |
| `Named.title()` | Default method được kế thừa từ interface |
| `Object.toString()` và các public Object methods khác | Kế thừa qua class hierarchy |

`validate()`, `packageOnly()` và `secret()` không nằm trong tập `getMethods()` vì chúng không public. `parentProtected()` cũng không nằm trong tập này vì là protected.

Số lượng public methods có thể thay đổi khi kiểu cha hoặc API của JDK thay đổi. **Đừng dùng giá trị `methods.length` cố định làm phép kiểm tra nghiệp vụ** cho tất cả các bản JDK.

### 3.2. Phân tích tập `getDeclaredMethods()`

`Child.class.getDeclaredMethods()` chứa những phương thức khai báo trực tiếp tại `Child`, ví dụ:

- `save(String)`.
- `save(int)`.
- `validate()`.
- `packageOnly()`.
- `secret()`.

Nó không chứa `Parent.inherited()` hoặc `Named.title()` vì những phương thức này không được khai báo tại `Child`. Nó cũng không chứa các phương thức `Object` không được `Child` tự khai báo.

Nếu compiler tạo thêm bridge hoặc synthetic method trong một ví dụ khác, tập declared có thể lớn hơn số phương thức nhìn thấy trong mã nguồn.

### 3.3. `getDeclaringClass()` không nhất thiết là kiểu đang quét

Khi gọi `Child.class.getMethods()`, một `Method` được trả về có thể báo:

```java
method.getDeclaringClass() == Parent.class
```

hoặc:

```java
method.getDeclaringClass() == Named.class
```

Điều đó là bình thường: `getDeclaringClass()` nói method **được khai báo ở đâu**, không phải `Class<?>` nào đã được dùng để bắt đầu tra cứu.

## 4. Không dựa vào `methods[0]` hoặc vòng lặp gốc

Một lỗi thiết kế điển hình:

```java
Method target = Child.class.getDeclaredMethods()[0];
```

Đây là lựa chọn **không có hợp đồng**. Ngay cả nếu trên máy phát triển nó luôn trỏ tới `save(String)`, API không cam kết kết quả sẽ duy trì như vậy.

Tương tự, viết:

```java
for (Method method : type.getMethods()) {
    register(method);
}
```

có thể làm thứ tự đăng ký handler, thứ tự sinh tài liệu hoặc thứ tự kết quả test phụ thuộc mảng phản chiếu. Nếu framework xử lý nhiều handler trùng route hoặc trùng tên, thứ tự ngẫu nhiên còn có thể che giấu xung đột.

Hướng xử lý tùy mục tiêu:

| Mục tiêu | Cách xử lý |
| --- | --- |
| Tìm một public method với tên và parameter types cụ thể | `getMethod(name, parameterTypes...)` |
| Tìm một method được khai báo trực tiếp, bất kể access level | `getDeclaredMethod(name, parameterTypes...)` |
| Xác nhận method có tồn tại | Kiểm tra theo thuộc tính; không cần sort |
| So sánh hai kết quả reflection độc lập về thứ tự | Dùng `Set<Method>` hoặc tập descriptor có định nghĩa rõ |
| In tài liệu/manifest/diagnostic ổn định | Sort theo key tường minh |
| Chọn handler ưu tiên | Dùng annotation priority hoặc quy tắc nghiệp vụ tường minh; không dùng vị trí trong mảng |
| Lọc phương thức nguồn công khai | Filter public và cân nhắc bridge/synthetic |

## 5. Truy xuất đúng overload bằng tên và parameter types

Khi biết rõ phương thức cần dùng, hãy tra cứu trực tiếp:

```java
Method byString = Child.class.getMethod(
        "save", String.class);

Method byInt = Child.class.getMethod(
        "save", int.class);

Method privateMethod = Child.class.getDeclaredMethod(
        "secret");
```

Các API này không buộc ứng dụng phải đoán phần tử ở vị trí nào trong mảng. `getMethod` tìm public member method, kể cả phương thức được kế thừa phù hợp. `getDeclaredMethod` chỉ tìm trong class/interface đang xét, nhưng có thể trả về method non-public.

Chú ý:

- `getMethod("save", String.class)` khác `getMethod("save", int.class)`.
- Nếu cần `inherited()`, `Child.class.getMethod("inherited")` có thể tìm thấy.
- `Child.class.getDeclaredMethod("inherited")` sẽ báo `NoSuchMethodException` vì method đó được khai báo ở Parent.
- `Child.class.getMethod("secret")` sẽ báo `NoSuchMethodException` vì secret không public.
- Nếu bytecode chứa nhiều method cùng tên và parameter types nhưng return type khác nhau, `getDeclaredMethod` không có tham số lọc return type. Khi đó, cần liệt kê và lọc `getReturnType()` theo yêu cầu.

**Tìm thấy method không đồng nghĩa có quyền gọi method.** Việc thực thi qua `Method.invoke` vẫn chịu kiểm tra quyền truy cập theo class, package và module.

## 6. Sắp xếp để hiển thị ổn định

Khi cần tạo report hoặc danh sách phương thức dễ diff, hãy sort bằng một key có ý nghĩa, chẳng hạn:

```text
declaring-class#method-name(param-type-1,param-type-2):return-type
```

Ví dụ:

```text
example.Child#save(int):void
example.Child#save(java.lang.String):void
example.Parent#inherited():java.lang.String
```

Key nên chứa:

1. `getDeclaringClass()` — phân biệt method cùng tên khai báo ở các class/interface.
2. `getName()` — tên method.
3. `getParameterTypes()` — loại từng tham số, **đúng thứ tự khai báo**.
4. `getReturnType()` — phân biệt trường hợp có cùng tên và parameter types nhưng return type khác nhau ở mức JVM.

Sắp xếp mẫu:

```java
Comparator<Method> bySignature =
        Comparator.comparing(
                ReflectionOrderDemo::signature);

Method[] methods = Child.class.getDeclaredMethods();

Arrays.stream(methods)
        .sorted(bySignature)
        .forEach(m ->
                System.out.println(
                        ReflectionOrderDemo.signature(m)));
```

### 6.1. Key hiển thị khác identity runtime

Key chuỗi trên phù hợp để in tài liệu cho một tập class đã xác định. Nhưng tên class **không chứa class loader identity**. Hai class khác nhau được nạp bởi hai loader khác nhau có thể có cùng binary name; khi ấy, hai `Method` khác nhau cũng có thể sinh cùng key chuỗi.

Nếu mục tiêu là so sánh đối tượng reflection trong cùng JVM, dùng `Method.equals` hoặc cấu trúc dựa trên `Class<?>` thay vì coi chuỗi descriptor là identity toàn cục.

Với artifact cần so sánh giữa nhiều lần chạy, hãy xác định chính xác đầu vào: phiên bản JDK, compiler, classpath/module path, class loaders và cấu hình plugin. Sort chỉ giúp trình bày xác định, **không** khiến tập phương thức của các phiên bản khác nhau tự động giống nhau.

### 6.2. Không dùng `toString()` làm hợp đồng ID máy đọc

`Method.toString()` và `toGenericString()` hữu ích cho chẩn đoán. Tuy nhiên, nếu tạo key để hệ thống khác phân tích hoặc so sánh, nên dùng các thuộc tính reflection tường minh. `toGenericString()` còn đưa thông tin generic và throws clause vào chuỗi hiển thị, vốn không phải toàn bộ tiêu chí nhận dạng một JVM method.

## 7. So sánh tập kết quả mà không dùng thứ tự

### 7.1. Dùng `Set<Method>` khi quan tâm chính các method

`Method.equals` được định nghĩa dựa trên declaring class, tên method, formal parameter types và return type. Do đó, có thể so sánh hai lần liệt kê cùng một class trong cùng môi trường bằng tập hợp:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

Set<Method> first = new HashSet<>(
        Arrays.asList(Child.class.getDeclaredMethods()));

Set<Method> second = new HashSet<>(
        Arrays.asList(Child.class.getDeclaredMethods()));

if (!first.equals(second)) {
    throw new AssertionError(
            "Hai tập declared methods không khớp");
}
```

Trong cùng tiến trình và với cùng class đã tải, hai tập phản ánh cùng metadata mặc dù mảng có thể được trả về theo thứ tự không xác định. `Set.equals` so sánh thành viên, không phụ thuộc thứ tự lặp.

Đừng so sánh toàn bộ tập `getMethods()` của một class trên nhiều phiên bản JDK bằng một snapshot bất biến nếu không kiểm soát cả API kế thừa từ `Object` và các thư viện phụ thuộc: phiên bản mới có thể thêm hoặc thay đổi public methods.

### 7.2. So sánh theo các tính chất được yêu cầu

Test nghiệp vụ thường nên xác minh **những phương thức thiết yếu phải tồn tại**, thay vì snapshot tất cả phương thức.

```java
import java.lang.reflect.Method;
import java.util.Arrays;

static boolean contains(
        Method[] methods,
        Class<?> declaringClass,
        String name,
        Class<?>... params) {

    return Arrays.stream(methods).anyMatch(method ->
            method.getDeclaringClass() == declaringClass
            && method.getName().equals(name)
            && Arrays.equals(
                    method.getParameterTypes(), params));
}
```

Hàm này kiểm tra declaring class, name và parameter types. Nó phù hợp với những assertion minh họa dưới đây. Nếu cần phân biệt bytecode methods có cùng name/params nhưng return type khác, bổ sung `method.getReturnType()` vào điều kiện.

Ví dụ kỳ vọng:

```java
Method[] publicMethods = Child.class.getMethods();
Method[] declared = Child.class.getDeclaredMethods();

if (!contains(publicMethods, Parent.class, "inherited")) {
    throw new AssertionError("Thiếu inherited()");
}

if (!contains(publicMethods, Named.class, "title")) {
    throw new AssertionError("Thiếu default method title()");
}

if (!contains(declared, Child.class, "secret")) {
    throw new AssertionError("Thiếu declared private method");
}

if (contains(declared, Parent.class, "inherited")) {
    throw new AssertionError(
            "Declared methods không được gồm phương thức kế thừa");
}
```

Các assertion này không dựa vào thứ tự của `Method[]`, không giả định số lượng phương thức kế thừa từ `Object` và không cần biết compiler liệt kê overload theo cách nào.

### 7.3. Cẩn thận với `Set<String>` chỉ chứa tên method

Ví dụ sau **làm mất thông tin overload**:

```java
Set<String> names = Arrays.stream(
        Child.class.getDeclaredMethods())
        .map(Method::getName)
        .collect(java.util.stream.Collectors.toSet());
```

Hai method `save(String)` và `save(int)` sẽ cùng bị gộp thành một tên `save`. Tương tự, gộp theo tên và parameter types nhưng bỏ return type có thể mất thông tin về bridge methods.

Nếu chỉ cần biết class có phương thức tên `save` thì cách trên đủ. Nếu cần kiểm kê API, cần key chi tiết hơn hoặc giữ nguyên các đối tượng `Method`.

## 8. Bridge method và synthetic method: một lý do không tin thứ tự hay số lượng

Compiler Java có thể thêm các method không hiện ra như khai báo độc lập trong source code. Hai API reflection có thể trả về chúng, đặc biệt `getDeclaredMethods()`.

Xét ví dụ generics:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public class BridgeDemo {

    interface Source<T> {
        T load();
    }

    static class TextSource implements Source<String> {
        @Override
        public String load() {
            return "Xin chào";
        }
    }

    public static void main(String[] args) {
        Arrays.stream(TextSource.class.getDeclaredMethods())
                .filter(m -> m.getName().equals("load"))
                .sorted(Comparator.comparing(
                        m -> m.getReturnType().getTypeName()))
                .forEach(m -> System.out.println(
                        "return=" + m.getReturnType().getTypeName()
                        + ", bridge=" + m.isBridge()
                        + ", synthetic=" + m.isSynthetic()));
    }
}
```

Với `javac`, compiler thường sinh một bridge method `Object load()` bên cạnh `String load()` để nối hành vi override của generic interface sau type erasure. Vì vậy, reflection có thể thấy hai `Method` tên `load` không có parameter nhưng khác return type.

Ví dụ kết quả thường thấy:

```text
return=java.lang.Object, bridge=true, synthetic=true
return=java.lang.String, bridge=false, synthetic=false
```

Đây là mô tả output minh họa theo cách compiler tạo bridge, không phải cam kết thứ tự gốc hoặc số lượng compiler-generated methods ở mọi công cụ biên dịch.

### 8.1. Vì sao return type phải nằm trong key?

Tài liệu `getDeclaredMethods()` quy định rằng nếu class có nhiều method cùng tên và parameter types nhưng return types khác nhau, nó trả một `Method` cho **mỗi** method tương ứng.

Ở Java source thông thường, không thể overload chỉ bằng return type. Nhưng bytecode, bridge methods và covariant return vẫn có thể tạo tập reflection như vậy. Vì thế:

- Không dùng `Map<String, Method>` chỉ keyed theo method name để giữ một inventory đầy đủ.
- Không dùng chỉ tên và parameter types để phân biệt toàn bộ JVM method metadata.
- Nếu cần giữ tất cả, dùng `Method` hoặc key gồm return type.
- Nếu muốn biểu diễn API source-level, đặt quy tắc lọc bridge/synthetic rõ ràng.

### 8.2. Có nên loại `isBridge()` và `isSynthetic()`?

Tùy mục tiêu:

| Mục tiêu | Xử lý bridge/synthetic |
| --- | --- |
| Kiểm kê JVM metadata chính xác | Giữ lại |
| So khớp JVM method descriptors | Giữ lại và phân biệt return type |
| Sinh tài liệu hướng tới người dùng từ public source API | Có thể lọc bridge/synthetic theo chính sách |
| Viết framework proxy, serializer, method interceptor | Cần hiểu vai trò bridge; không lọc vô điều kiện |
| Sinh API manifest cần so diff | Ghi rõ chính sách lọc, compiler và môi trường |

Ví dụ khi muốn liệt kê các phương thức public được khai báo trong class và loại phương thức compiler-generated:

```java
import java.lang.reflect.Modifier;

var publicSourceCandidates = Arrays.stream(
        Child.class.getDeclaredMethods())
        .filter(m -> Modifier.isPublic(m.getModifiers()))
        .filter(m -> !m.isBridge() && !m.isSynthetic())
        .sorted(Comparator.comparing(
                ReflectionOrderDemo::signature))
        .toList();
```

Đây là **tập ứng viên** cho API source-level, không phải bảo đảm rằng nó đúng bằng mọi khai báo người lập trình viết trong source. Một số công cụ/compiler có thể tạo thêm cấu trúc khác; chính sách thực tế cần phù hợp với loại metadata ứng dụng muốn mô hình hóa.

## 9. Sắp xếp không giải quyết xung đột nghiệp vụ

Giả sử một framework quét tất cả method có annotation `@Handler` và đăng ký mỗi method vào một route. Nếu hai method cùng khai báo route `/users` thì việc sort theo tên chỉ khiến thứ tự đăng ký dự đoán được; nó không giải quyết xung đột route.

Hướng đúng:

1. Lọc method theo annotation và mức truy cập được chấp nhận.
2. Chuẩn hóa route và method HTTP theo quy tắc framework.
3. Nhóm các handler có cùng khóa route.
4. Nếu một khóa có nhiều handler không được phép đồng tồn tại, **báo lỗi rõ ràng**.
5. Nếu business rule có ưu tiên, đọc priority từ cấu hình/annotation.
6. Sort cuối cùng để xuất log hoặc tài liệu tái lập được.

Ví dụ mẫu logic:

```java
var handlers = Arrays.stream(Child.class.getDeclaredMethods())
        .filter(m -> Modifier.isPublic(m.getModifiers()))
        .filter(m -> !m.isSynthetic() && !m.isBridge())
        .sorted(Comparator.comparing(
                ReflectionOrderDemo::signature))
        .toList();
```

Danh sách có thứ tự minh bạch cho bước duyệt; **không** có nghĩa method đầu tiên là method có priority cao nhất. Muốn thứ tự xử lý theo nghiệp vụ, phải đưa tiêu chí nghiệp vụ vào comparator hoặc validation của hệ thống.

## 10. Reflection và quyền truy cập: liệt kê không có nghĩa được gọi

`getDeclaredMethods()` cho phép quan sát metadata của các method `private` hoặc package-private; điều này không tự cấp quyền gọi chúng.

Trên JDK hiện đại có Java Platform Module System (JPMS):

- Lời gọi `Method.invoke(...)` vẫn kiểm tra access.
- `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu package của module không mở cho caller.
- `trySetAccessible()` trả `false` khi không thể bật quyền truy cập.
- `getMethods()` trả public methods, nhưng caller còn cần quyền truy cập vào declaring class và package thích hợp.

Ví dụ đọc thông tin mà không phá encapsulation:

```java
for (Method method : Child.class.getDeclaredMethods()) {
    System.out.println(
            method.getName() + " / "
            + java.lang.reflect.Modifier.toString(
                    method.getModifiers()));
}
```

Framework nên ưu tiên contract public/exported rõ ràng hoặc các package được chủ module mở có chủ đích. Đừng coi `setAccessible(true)` hay tùy chọn khởi động phá encapsulation là giải pháp mặc định cho việc quét API.

## 11. Ảnh hưởng của JEP 416 từ Java 18

**JEP 416 — Reimplement Core Reflection with Method Handles** thay đổi cách core reflection được triển khai từ Java 18 để giảm chi phí duy trì giữa hai hệ thống `java.lang.reflect` và `java.lang.invoke`.

Đối với người dùng các API được tài liệu hóa, trọng tâm là:

- `getMethods()` vẫn trả public member methods theo hợp đồng Java.
- `getDeclaredMethods()` vẫn trả declared methods theo hợp đồng Java.
- Không API nào cam kết thứ tự kết quả.
- Code dựa trên **nội bộ không được tài liệu hóa** của reflection có thể không tương thích khi triển khai thay đổi.
- Code dựa trên `Method`, modifiers, declaring class, parameter/return types và các quy tắc chính thức sẽ bền vững hơn qua JDK mới.

Không nên sử dụng hack với nội bộ cũ của core reflection hoặc tham số workaround dành cho giai đoạn chuyển đổi JEP 416. Bài tập trung vào **hợp đồng public API còn áp dụng hiện nay**.

## 12. Checklist kiểm tra code reflection

Khi review một đoạn code dùng `getMethods()` hoặc `getDeclaredMethods()`, hãy tự hỏi:

| Câu hỏi | Dấu hiệu tốt |
| --- | --- |
| Có dùng `methods[0]` để chọn hành vi không? | Không; tra cứu/filter bằng tiêu chí rõ ràng |
| Có so sánh trực tiếp `Method[]` theo vị trí không? | Không; dùng Set hoặc comparator riêng khi thích hợp |
| Có phân biệt declared và inherited không? | Có; chọn đúng API |
| Có kiểm tra access level không? | Có; dùng `Modifier` khi cần |
| Có nhận diện overload không? | Có; xét parameter types |
| Có nhận diện bridge/synthetic không? | Có chính sách phù hợp |
| Có xét return type khi lập descriptor JVM không? | Có |
| Có nhầm `getDeclaringClass()` với class đang quét không? | Không |
| Có dựa vào số lượng public Object methods cố định không? | Không |
| Có snapshot output reflection qua nhiều JDK mà thiếu kiểm soát không? | Không |
| Có kiểm tra module access trước khi invoke không? | Có |
| Có dùng thứ tự reflection để quyết định priority không? | Không; business rule tường minh |

### Những nhận định sai hay gặp

- **“Reflection giữ thứ tự khai báo trong source.”** API không hứa điều đó.
- **“`getMethods()` bằng `getDeclaredMethods()` lọc public.”** Sai vì phạm vi kế thừa và quy tắc most-specific khác nhau.
- **“Hai method cùng tên là trùng nhau.”** Có thể là overload.
- **“Tên + parameter types luôn xác định duy nhất mọi `Method` được trả về.”** Bridge và JVM return types có thể phá giả định.
- **“`getDeclaredMethods()` chỉ chứa method nhìn thấy trong source.”** Có thể có bridge/synthetic methods.
- **“Sort xong thì framework có priority đúng.”** Sort chỉ tạo thứ tự, không tự xác lập nghiệp vụ.
- **“Lấy được Method private thì invoke được.”** Quyền truy cập vẫn chịu kiểm tra.

## 13. Bài tập tự kiểm tra

**Bài 1.** Vì sao không nên chọn `getDeclaredMethods()[0]` để lấy method đầu tiên viết trong source?

*Đáp án:* `getDeclaredMethods()` không bảo đảm thứ tự kết quả; vị trí 0 không mang nghĩa thứ tự khai báo hoặc mức ưu tiên.

**Bài 2.** Muốn liệt kê public method được kế thừa từ superclass và interface, chọn API nào?

*Đáp án:* `getMethods()`. Nó trả public member methods theo các quy tắc kế thừa và chọn most-specific.

**Bài 3.** `getDeclaredMethods()` có trả về private method của class không? Có trả method public từ superclass mà class không override không?

*Đáp án:* Có private method được khai báo tại class. Không có method chỉ được kế thừa từ superclass.

**Bài 4.** Muốn phân biệt `save(String)` với `save(int)` nên dùng điều gì?

*Đáp án:* Kiểm tra `getParameterTypes()` hoặc gọi `getMethod("save", String.class)` / `getMethod("save", int.class)`.

**Bài 5.** Vì sao key chỉ gồm tên và parameter types có thể thiếu thông tin khi kiểm kê toàn bộ JVM methods?

*Đáp án:* Class file có thể chứa nhiều method cùng tên và parameter types nhưng khác return type, thường gặp trong bridge methods. Key đầy đủ cần thêm return type và declaring class khi phù hợp.

**Bài 6.** Muốn so sánh hai mảng `Method[]` mà không phụ thuộc thứ tự, có thể dùng gì?

*Đáp án:* Chuyển thành `Set<Method>` rồi so sánh tập hợp, hoặc chuẩn hóa thành một danh sách descriptor rồi sort trước khi so sánh. Chọn cách nào tùy yêu cầu giữ tất cả metadata và cách xác định identity.

**Bài 7.** Nếu framework phát hiện hai handler cùng route, có nên chọn handler xuất hiện đầu tiên sau khi sort tên method không?

*Đáp án:* Không. Cần phát hiện conflict và báo lỗi hoặc dùng quy tắc priority nghiệp vụ đã công bố; thứ tự chữ cái không phải priority.

**Bài 8.** JEP 416 của Java 18 có làm `getMethods()` trả theo thứ tự ổn định không?

*Đáp án:* Không. JEP 416 là thay đổi triển khai core reflection; hợp đồng API vẫn không bảo đảm thứ tự.

## 14. Ghi nhớ

`getMethods()` trả các public member methods, bao gồm phương thức khai báo trực tiếp và được kế thừa theo quy tắc Java. `getDeclaredMethods()` trả mọi phương thức khai báo tại chính kiểu đó, kể cả non-public, nhưng không bao gồm phương thức kế thừa. Cả hai mảng `Method[]` **không có thứ tự được bảo đảm**.

Hãy tra cứu bằng tên/parameter types khi biết method đích, dùng `Set<Method>` khi cần so sánh không phụ thuộc thứ tự, và sort theo key chứa declaring class, method name, parameters, return type khi cần báo cáo ổn định. Lưu ý bridge/synthetic methods, access control và khác biệt giữa thứ tự hiển thị với quy tắc nghiệp vụ.

Java 18 thay đổi triển khai reflection qua JEP 416, nhưng nguyên tắc này vẫn đúng trên JDK hiện đại: **phụ thuộc hợp đồng public API, không phụ thuộc thứ tự quan sát được hoặc chi tiết nội bộ triển khai**.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 24 — Class: getMethods(), getDeclaredMethods(), getMethod(), getDeclaredMethod()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Class.html).
- [Oracle Java SE 24 — Method: declaring class, parameter types, return type, equals, isBridge, isSynthetic](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/reflect/Method.html).
- [Oracle Java SE 24 — Modifier](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/reflect/Modifier.html).
- [Oracle Java SE 24 — AccessibleObject: access rules và trySetAccessible](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
