# Tham số synthetic, implicit và varargs trong metadata Java

## 1. Mục tiêu bài học

Khi nhìn vào một phương thức trong Java, ta thường chỉ thấy những tham số mà lập trình viên viết trong source code. Tuy nhiên, khi truy vấn bytecode hoặc sử dụng **Reflection API**, danh sách tham số của một method hoặc constructor có thể chứa thông tin mà bản nguồn không thể hiện trực tiếp. Java phân biệt **tham số tường minh**, **tham số được khai báo ngầm (implicit/mandated)**, **tham số synthetic** và **tham số varargs**.

Từ Java 8, `java.lang.reflect.Parameter` cung cấp các phương thức đặc biệt hữu ích:

- `Parameter.isImplicit()`: cho biết tham số được **khai báo ngầm theo ngôn ngữ Java** (*implicitly declared*).
- `Parameter.isSynthetic()`: cho biết tham số **do compiler tạo ra nhưng không được khai báo tường minh hoặc ngầm theo JLS**.
- `Parameter.isVarArgs()`: cho biết tham số đại diện cho **danh sách đối số biến độ dài** của một executable có khai báo varargs.

Ba cờ này **không phải ba cách gọi cùng một tính chất**. Một tham số varargs có thể là tham số nguồn hoàn toàn bình thường. Một constructor có tham số được thêm để truyền enclosing instance mà caller không viết trực tiếp vào danh sách đối số constructor. Và một số thành phần do compiler sinh có thể là synthetic thay vì implicit, tùy loại cấu trúc Java.

**Điểm thực hành quan trọng:** không dựa vào tên kiểu `arg0`, một dấu `...` trong `toString()`, hoặc một con số tham số đơn lẻ để kết luận tham số nào thật sự có trong source. Hãy dùng đúng API reflection, hiểu vai trò `MethodParameters` trong class file, kiểm tra cách biên dịch và phân biệt thông tin ở mức ngôn ngữ với chi tiết hạ xuống bytecode.

Bài viết giới thiệu các quy tắc còn được Java hiện đại hỗ trợ, tập trung Java 8 trở lên và trình bày ví dụ biên dịch/chạy trên JDK 17+.

## 2. Metadata tham số được truy cập bằng những API nào?

`java.lang.reflect.Executable` là lớp cha của `Method` và `Constructor`. Các API liên quan gồm:

```java
Executable executable = someMethodOrConstructor;

int parameterCount = executable.getParameterCount();
Parameter[] parameters = executable.getParameters();
Class<?>[] types = executable.getParameterTypes();

boolean executableVarArgs = executable.isVarArgs();
```

Đây là đoạn mã minh họa; `someMethodOrConstructor` phải là một giá trị `Method` hoặc `Constructor<?>` lấy từ reflection. Các API thực tế:

| API | Câu hỏi nó trả lời |
| --- | --- |
| `Executable.getParameterCount()` | Executable có bao nhiêu tham số trong mô hình reflection? |
| `Executable.getParameters()` | Mỗi tham số là một `Parameter` với tên, kiểu, modifier và annotation gì? |
| `Executable.getParameterTypes()` | Những kiểu tham số ở mức `Class<?>` theo thứ tự là gì? |
| `Executable.getGenericParameterTypes()` | Các kiểu khai báo tổng quát được thể hiện ra sao? |
| `Executable.isVarArgs()` | Executable có khai báo varargs không? |
| `Parameter.getType()` | Kiểu ở mức runtime của tham số là gì? |
| `Parameter.getParameterizedType()` | Kiểu tổng quát của tham số là gì, nếu có? |
| `Parameter.getName()` | Tên được reflection công bố cho tham số là gì? |
| `Parameter.isNamePresent()` | Tên trả về có phải tên được lưu trong metadata theo quy tắc API không? |
| `Parameter.isImplicit()` | Tham số này là implicit/mandated không? |
| `Parameter.isSynthetic()` | Tham số này là synthetic không? |
| `Parameter.isVarArgs()` | Đây có phải tham số varargs không? |
| `Parameter.getModifiers()` | Các cờ modifier của tham số theo reflection là gì? |

Đừng nhầm `Executable.isSynthetic()` (cờ synthetic của **method hoặc constructor**) với `Parameter.isSynthetic()` (cờ synthetic của **một tham số**). Cũng đừng nhầm `Method.isVarArgs()` với `Parameter.isVarArgs()`: chúng phản ánh hai cấp quan sát của cùng khai báo varargs.

### 2.1. Cùng một method có thể được nhìn ở các mức khác nhau

Xét:

```java
static String join(String prefix, String... parts) {
    return prefix + String.join(",", parts);
}
```

Ở mức source:

- `prefix` là tham số tường minh kiểu `String`.
- `parts` là tham số tường minh **varargs** kiểu `String...`.
- Caller có thể gọi với 0, 1 hoặc nhiều `String` ở phần cuối.

Ở mức reflection:

- `getParameterCount() == 2`.
- `getParameterTypes()[1] == String[].class`.
- `isVarArgs() == true` trên method.
- `getParameters()[1].isVarArgs() == true` trên tham số cuối.
- `getParameters()[0].isVarArgs() == false`.

Mặc dù caller viết các phần tử rời rạc trong lời gọi biến độ dài, method ở mức runtime nhận **một mảng `String[]`** làm tham số cuối. Không có một `Parameter` mới được tạo cho từng đối số `"a"`, `"b"` trong mỗi lời gọi.

## 3. Synthetic parameter là gì?

Theo mô hình JLS, một tham số là **synthetic** khi nó được compiler phát sinh và **không tương ứng với một khai báo tham số tường minh hoặc khai báo ngầm theo ngôn ngữ nguồn**. Mục đích thường liên quan đến cách compiler biểu diễn các cấu trúc Java trong class file.

Ở reflection:

```java
boolean generatedImplementationDetail =
        parameter.isSynthetic();
```

Nếu `true`, tham số thuộc loại synthetic trong metadata mà API quan sát được. Nhưng bạn **không nên mặc định** rằng tất cả những tham số không nhìn thấy trong source đều synthetic.

### 3.1. Ví dụ thường gặp: tham số ẩn trong enum constructor

Ở source:

```java
enum Level {
    LOW, HIGH;

    Level() {
    }
}
```

Bạn không viết các tham số tên enum hoặc ordinal trong constructor. Khi biên dịch bằng các triển khai Java phổ biến, enum constructor trong bytecode có thêm thông tin nội bộ phục vụ cơ chế enum, thường thấy các tham số mang kiểu `String` và `int` cho tên/ordinal.

Các tham số bổ sung đó là **chi tiết biểu diễn của enum** chứ không phải hai tham số mà bạn được phép truyền khi khai báo enum constant. Chúng có thể được đánh dấu synthetic trong `MethodParameters`/reflection tùy compiler và metadata được phát ra.

**Không viết code nghiệp vụ giả định tên của chúng là `$enum$name` hay `$enum$ordinal`**, hoặc giả định mọi compiler/JDK có cùng bố cục bytecode. Nếu mục tiêu là lấy tên/ordinal của enum, dùng API chuẩn:

```java
Level value = Level.HIGH;
String name = value.name(); // "HIGH"
int ordinal = value.ordinal(); // 1
```

`Enum.name()` và `ordinal()` là API ngôn ngữ ổn định. Reflection lên tham số constructor không phải cách lấy metadata enum ở tầng nghiệp vụ.

### 3.2. Synthetic không đồng nghĩa private, bridge hoặc captured variable

Compiler có thể phát sinh synthetic **method**, **field**, **class** hoặc **parameter** tùy cấu trúc. Nhưng các thuật ngữ đó thuộc những phần tử khác nhau:

- **Synthetic method** có thể là implementation artifact được quan sát qua `Method.isSynthetic()`.
- **Bridge method** (thường có `Method.isBridge()`) hỗ trợ những trường hợp liên quan generic/override và type erasure.
- **Synthetic parameter** được hỏi bằng `Parameter.isSynthetic()`.
- **Field được sinh để giữ captured state hoặc enclosing instance** không tự đồng nghĩa có một synthetic parameter tương ứng trong mọi constructor.

Không suy luận từ việc một class có field synthetic rằng mọi parameter của class cũng synthetic; phải kiểm tra từng `Parameter`.

## 4. Implicit parameter là gì?

Một **implicit parameter** là tham số mà **đặc tả Java coi như được khai báo ngầm**, dù lập trình viên không trực tiếp viết nó trong danh sách tham số source. Trong mô hình class file, tham số kiểu này thường tương ứng với trạng thái **mandated** (`ACC_MANDATED`), khác với **synthetic** (`ACC_SYNTHETIC`).

```java
boolean languageDeclaredImplicitly =
        parameter.isImplicit();
```

Đó là ý nghĩa của `Parameter.isImplicit()`: không phải “bất kỳ điều gì được compiler sinh ra” mà là trường hợp được **quy tắc nguồn Java** công nhận.

### 4.1. Ví dụ điển hình: enclosing instance của non-static inner member class

Xét:

```java
class Outer {
    class Inner {
        private final String label;

        Inner(String label) {
            this.label = label;
        }
    }
}
```

Ở source, constructor `Inner(String label)` chỉ hiển thị một formal parameter `label`. Nhưng `Inner` là **non-static inner member class**, nên khi tạo:

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner("A");
```

một instance `Outer` phải được liên kết với `Inner`. Trong bytecode mà `javac` thông thường phát ra, constructor `Inner` có thêm tham số **đầu tiên** tương ứng với enclosing `Outer`, đứng trước tham số `String label`.

Khi dùng reflection:

```java
Constructor<?> constructor =
        Outer.Inner.class.getDeclaredConstructors()[0];

Class<?>[] parameterTypes = constructor.getParameterTypes();
```

Với class `Outer.Inner` nói trên, mô hình reflection của `javac` thường thấy:

```text
parameterTypes[0] = Outer
parameterTypes[1] = java.lang.String
```

Với metadata `MethodParameters` thích hợp, tham số `Outer` được xác định là **implicit/mandated** và `Parameter.isImplicit()` trả `true`. Đây là điểm khác biệt trực tiếp với những tham số synthetic của một số cấu trúc khác.

### 4.2. Vì sao phải cẩn thận với cờ và phiên bản compiler?

Reflection chỉ có thể báo cờ metadata mà class file cung cấp theo mô hình JVM/JDK. Nếu class file thiếu `MethodParameters` hoặc được tạo bởi compiler/transformer khác, việc lấy tên và phân loại parameter có thể không đầy đủ.

**Không nên viết kiểm thử portable kiểu: “tham số đầu tiên của mọi inner constructor luôn có tên `this$0` và `isImplicit()` luôn `true` trong mọi binary”**. Hãy xác định môi trường biên dịch, dùng `-parameters` khi cần metadata tên, và xử lý trường hợp thiếu cờ.

Về mặt cấu trúc ngôn ngữ, inner instance cần enclosing instance; về mặt quan sát reflection, các chi tiết tên/cờ có thể phụ thuộc class file cụ thể.

### 4.3. Khác với receiver parameter (`TypeName this`)

Java 8 còn có cú pháp *receiver parameter* như:

```java
class Document {
    void save(Document this, String name) {
        System.out.println(name);
    }
}
```

`Document this` là **vị trí cú pháp để gắn annotation vào receiver type**; nó không thêm formal parameter vào `Method.getParameters()` và không tăng arity.

Đừng đồng nhất nó với tham số enclosing instance mà compiler biểu diễn trong **constructor của inner class**. Một trường hợp chủ yếu là cú pháp metadata của receiver; trường hợp kia là tham số thực thi cần thiết để gắn đối tượng inner với outer.

## 5. Varargs là gì và vì sao không phải synthetic?

`varargs` (*variable arity*) cho phép một phương thức hoặc constructor được khai báo nhận số lượng đối số ở vị trí cuối một cách linh hoạt:

```java
static String format(String prefix, String... words) {
    return prefix + String.join("|", words);
}
```

Các lời gọi hợp lệ:

```java
format("X:");               // "X:"
format("X:", "a");          // "X:a"
format("X:", "a", "b");     // "X:a|b"
format("X:", new String[]{"c", "d"}); // "X:c|d"
```

Tham số `words` **được lập trình viên khai báo tường minh**. Việc nó là varargs **không làm nó synthetic hay implicit**.

Trong chữ ký runtime và reflection, `String... words` được biểu diễn bằng `String[]`. Cờ varargs ghi nhận cách method có thể được gọi theo *variable arity invocation*, chứ không làm thay đổi bản chất array parameter ở mức JVM.

### 5.1. Quy tắc khai báo varargs

Một tham số varargs phải là **tham số cuối** trong danh sách formal parameters:

```java
static void ok(String prefix, int... values) {
}

 // KHÔNG BIÊN DỊCH:
 // static void wrong(int... values, String suffix) {}
```

Một method không thể có hai varargs parameters liên tiếp. Cách viết `String...` chỉ dùng tại vị trí mà grammar cho phép, không thay cho `String[]` ở mọi chỗ.

### 5.2. `String[]` không tự biến thành varargs

So sánh:

```java
static void arrayOnly(String[] values) {
}

static void variable(String... values) {
}
```

Cả hai có cùng kiểu tham số runtime ở vị trí cuối, nhưng chỉ `variable` được khai báo varargs. Lời gọi `variable("a", "b")` hợp lệ; `arrayOnly("a", "b")` không phải lời gọi hợp lệ tương tự. Phải truyền mảng cho `arrayOnly`.

Không thể overload hai phương thức **cùng tên, cùng các tham số khác** mà chỉ khác `String[]` với `String...`; chúng có chữ ký nguồn thực chất trùng theo kiểu array. Đây là lý do flag `isVarArgs()` quan trọng khi bạn muốn biết cú pháp API đã được khai báo.

### 5.3. Hai cấp thông tin varargs trong reflection

```java
Method m = Demo.class.getDeclaredMethod(
        "format", String.class, String[].class);

boolean declaredVarArgs = m.isVarArgs();
Parameter[] ps = m.getParameters();
boolean lastVarArgs = ps[1].isVarArgs();
```

Trong khai báo `format(String, String...)`:

- `m.isVarArgs() == true`.
- `ps[0].isVarArgs() == false`.
- `ps[1].isVarArgs() == true`.
- `ps[1].getType() == String[].class`.

Nếu thay method bằng `arrayOnly(String[])`, cả `Method.isVarArgs()` và cờ `Parameter.isVarArgs()` đều false.

### 5.4. Lưu ý kiểu generic và heap pollution

Một varargs parameter có thể mang thành phần generic không reifiable, ví dụ `List<String>...`. Java có quy tắc cảnh báo và kiểm tra liên quan **heap pollution** vì thực thể runtime vẫn là array.

Ví dụ về thiết kế API:

```java
@SafeVarargs
static <T> java.util.List<T> concatenate(
        java.util.List<? extends T>... lists) {
    java.util.List<T> result = new java.util.ArrayList<>();
    for (java.util.List<? extends T> list : lists) {
        result.addAll(list);
    }
    return result;
}
```

Annotation `@SafeVarargs` là một cam kết của người viết phương thức rằng phần thân không thực hiện thao tác không an toàn đối với varargs array theo hợp đồng của annotation. Nó **không tự chứng minh** code an toàn. Quy tắc vị trí được phép dùng `@SafeVarargs` phụ thuộc Java source level và modifier; từ Java 9+, phương thức instance `private` cũng nằm trong các trường hợp được cho phép bên cạnh static/final/constructor.

Trong Java 8-compatible ví dụ trên, method là static nên phù hợp. Không gắn `@SafeVarargs` bừa bãi chỉ để tắt cảnh báo; luôn review mutation/escape của array.

## 6. Ba loại tham số: bảng so sánh

| Tính chất | Explicit formal parameter | Implicit/mandated parameter | Synthetic parameter | Varargs parameter |
| --- | --- | --- | --- | --- |
| Có được viết trực tiếp trong source parameter list? | Có | Không | Không | **Có** |
| Mục đích | Nhận đối số do API yêu cầu | Thể hiện tham số do JLS khai báo ngầm | Phục vụ biểu diễn do compiler sinh | Nhận phần đối số biến độ dài |
| API chính | `Parameter` với type/name/annotations | `isImplicit()` | `isSynthetic()` | `isVarArgs()` |
| Ví dụ điển hình | `String name` | Enclosing instance cho non-static inner constructor | Parameter phụ trong một số compiler-generated constructs | `String... items` |
| Thường có thể liên quan `MethodParameters`? | Có | Có; flag mandated | Có; flag synthetic | Có thể có tên; varargs flag nằm ở executable |
| Có bắt buộc đổi cách gọi Java thông thường? | Theo số tham số nguồn | Không thêm tham số người dùng tự viết | Không thêm tham số người dùng tự viết | Cho phép variable-arity invocation |
| Có thể kiểm tra qua reflection? | Có | Có nếu metadata cung cấp đủ | Có nếu metadata cung cấp đủ | Có theo executable varargs và parameter cuối |

Lưu ý: cột **varargs** không phải một “loại nguồn gốc” loại trừ ba cột kia. Nó là một **thuộc tính của tham số cuối của method/constructor khai báo variable arity**. Trong code Java thường gặp, varargs parameter là một formal parameter được viết tường minh.

Tương tự, “không ghi trong source” chưa đủ để quyết định synthetic hay implicit. Phải xét quy tắc JLS tương ứng và cờ metadata.

## 7. `-parameters`: khác biệt giữa tên tham số và cờ cấu trúc

Từ Java 8, `javac` hỗ trợ tùy chọn:

```bash
javac -parameters ParameterMetadataDemo.java
```

`-parameters` yêu cầu compiler lưu **tên của formal parameters** trong class file để reflection có thể lấy chúng qua `Parameter.getName()`, `isNamePresent()`. Class file dùng thuộc tính `MethodParameters` để biểu diễn thông tin này, bao gồm tên và các modifier/cờ như `ACC_SYNTHETIC`, `ACC_MANDATED` khi được phát ra.

### 7.1. Khi có `-parameters`

Cho method:

```java
static String greet(String user, int count) {
    return user + ":" + count;
}
```

Biên dịch bằng `javac -parameters`, reflection có thể thấy:

```text
Tên tham số: user, count
isNamePresent(): true, true
```

### 7.2. Khi không có `-parameters`

Nếu compiler không lưu tên tham số, `getName()` có thể trả tên tổng hợp của reflection như `arg0`, `arg1`, còn `isNamePresent()` là false. Các tên đó **không phải bằng chứng** người viết method đặt tên như vậy.

Ví dụ:

```java
Parameter[] ps = m.getParameters();

for (int i = 0; i < ps.length; i++) {
    System.out.println(ps[i].getName()
            + " / " + ps[i].isNamePresent());
}
```

Đừng viết framework phụ thuộc tên parameter trong source nếu build pipeline không bảo đảm chế độ phát metadata tương ứng.

### 7.3. `LocalVariableTable` không thay `MethodParameters`

Build ở chế độ debug có thể chứa `LocalVariableTable`. Nhưng `Parameter.isNamePresent()` dùng mô hình metadata được API thiết kế cho reflection, không phải thuật toán tự động dò `LocalVariableTable` để tái tạo tên khai báo.

**Đừng nhầm `-g` với `-parameters`**. Khi runtime framework cần tên tham số như `user`, `count`, hãy kiểm tra trực tiếp `isNamePresent()` và cấu hình compiler/build, thay vì suy luận từ việc chạy debug thành công.

### 7.4. Hạn chế của việc chuẩn hóa flags

`-parameters` rất hữu ích, nhưng không phải phép bảo đảm mọi binary từ compiler, bytecode transformer hoặc code generator đều cung cấp tất cả chi tiết như nhau. Các cờ `isImplicit()` và `isSynthetic()` dựa vào metadata/class-file construct tương ứng.

Vì vậy, code reflection robust nên:

1. Kiểm tra `isNamePresent()` trước khi dùng tên như một identifier nghiệp vụ.
2. Quan sát `isImplicit()`/`isSynthetic()` nhưng không tự gắn nhãn những tham số thiếu flag.
3. Dựa vào hợp đồng API công khai và signature khi có thể.
4. Viết tests trên artifact được build thật, không chỉ trên source.

## 8. Chương trình Java hoàn chỉnh kiểm chứng phản chiếu tham số

Tạo tệp **`ParameterMetadataDemo.java`**. Chương trình tương thích cú pháp/API từ Java 8 và chạy được bằng JDK 17+.

Ví dụ được thiết kế để chỉ in những chi tiết ổn định khi biên dịch với lệnh `-parameters` đã nêu. Nó cũng đối chiếu `String[]` với `String...` và cho thấy constructor của inner member class có thêm enclosing-instance parameter trong reflection.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;

public class ParameterMetadataDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Origin {
        String value();
    }

    static String join(@Origin("caller") String prefix,
                       String... items) {
        return prefix + String.join(",", items);
    }

    static String fixed(String[] items) {
        return Arrays.toString(items);
    }

    static class Outer {
        class Inner {
            private final String label;

            Inner(String label) {
                this.label = label;
            }

            String label() {
                return label;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Method join = ParameterMetadataDemo.class
                .getDeclaredMethod(
                        "join", String.class, String[].class);

        Parameter[] params = join.getParameters();

        System.out.println("Count: " + join.getParameterCount());
        System.out.println("Method varargs: " + join.isVarArgs());
        System.out.println("First varargs: " + params[0].isVarArgs());
        System.out.println("Last varargs: " + params[1].isVarArgs());
        System.out.println("Last array type: "
                + params[1].getType().getTypeName());
        System.out.println("Names present: "
                + params[0].isNamePresent() + ","
                + params[1].isNamePresent());
        System.out.println("Names: "
                + params[0].getName() + ","
                + params[1].getName());

        Origin origin = params[0].getAnnotation(Origin.class);
        System.out.println("Origin: " + origin.value());

        System.out.println("Join source call: "
                + join("P:", "a", "b"));
        System.out.println("Join reflective call: "
                + join.invoke(null, new Object[]{
                        "R:", new String[]{"c", "d"}
                }));

        Method fixed = ParameterMetadataDemo.class
                .getDeclaredMethod("fixed", String[].class);
        System.out.println("Fixed method varargs: "
                + fixed.isVarArgs());
        System.out.println("Fixed parameter varargs: "
                + fixed.getParameters()[0].isVarArgs());

        Constructor<?> innerConstructor =
                Outer.Inner.class.getDeclaredConstructors()[0];
        Parameter[] innerParameters =
                innerConstructor.getParameters();

        System.out.println("Inner parameter count: "
                + innerParameters.length);
        System.out.println("Inner first type: "
                + innerParameters[0].getType().getSimpleName());

        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner("demo");
        System.out.println("Inner label: " + inner.label());
    }
}
```

Biên dịch và chạy:

```bash
javac -parameters ParameterMetadataDemo.java
java ParameterMetadataDemo
```

**Stdout kỳ vọng khi dùng `javac -parameters` trên JDK 17+:**

```text
Count: 2
Method varargs: true
First varargs: false
Last varargs: true
Last array type: java.lang.String[]
Names present: true,true
Names: prefix,items
Origin: caller
Join source call: P:a,b
Join reflective call: R:c,d
Fixed method varargs: false
Fixed parameter varargs: false
Inner parameter count: 2
Inner first type: Outer
Inner label: demo
```

**Giải thích từng nhóm kết quả:**

1. `join(String prefix, String... items)` có **hai formal parameters**. `...` không làm sinh một số `Parameter` thay đổi theo số đối số caller.
2. `join.isVarArgs()` đúng vì khai báo cuối dùng `...`; `params[0]` không phải varargs, `params[1]` là varargs và kiểu runtime là `String[]`.
3. Với `-parameters`, hai tên `prefix`/`items` có thể được lưu và `isNamePresent()` trả true. Khi build không dùng tùy chọn này, không được kỳ vọng output tên giống vậy.
4. Annotation `@Origin("caller")` là annotation **trên formal parameter**. `Parameter.getAnnotation(Origin.class)` dùng để đọc nó vì annotation có `@Retention(RUNTIME)` và `@Target(PARAMETER)`.
5. `join("P:", "a", "b")` sử dụng cú pháp varargs thông thường. `Method.invoke(null, new Object[]{...})` nhận một mảng đối số cho lời gọi phản chiếu; đối số thứ hai của method đích vẫn là **một `String[]`**.
6. `fixed(String[])` chỉ nhận một array parameter bình thường, không khai báo variable arity. Vì vậy cả method `fixed` và parameter cuối của nó đều trả false cho `isVarArgs()`.
7. Constructor của `Outer.Inner` có một tham số enclosing `Outer` cộng tham số `String label` trong bytecode của `javac`; reflection thường báo hai parameter tương ứng.
8. Ở source, người dùng vẫn gọi `outer.new Inner("demo")`, không truyền `outer` như một đối số trong danh sách tham số constructor.

Để bài kiểm chứng không lệ thuộc tên nội bộ của tham số enclosing instance hoặc cách compiler gắn cờ cho enum, chương trình **không** in `innerParameters[0].getName()` hay `isImplicit()` của nó. Bạn có thể tự quan sát hai giá trị này trong môi trường build thực tế để học sâu hơn.

### 8.1. Cách kiểm tra `isImplicit()` và `isSynthetic()` có kiểm soát

Dùng vòng lặp sau (đoạn minh họa đặt trong `main` sau khi có `innerConstructor`):

```java
for (Parameter p : innerConstructor.getParameters()) {
    System.out.println(
            p.getType().getTypeName()
            + " | implicit=" + p.isImplicit()
            + " | synthetic=" + p.isSynthetic()
            + " | namePresent=" + p.isNamePresent());
}
```

Với một class file phát ra metadata `MethodParameters` phù hợp, enclosing-instance parameter thường được báo `implicit=true`, không phải `synthetic=true`. Nhưng đừng dùng một kết quả đơn lẻ từ một compiler/version để tuyên bố luật phản chiếu cho mọi Java binary.

### 8.2. Quan sát bytecode bằng `javap`

Sau khi biên dịch có `-parameters`:

```bash
javap -v 'ParameterMetadataDemo$Outer$Inner'
```

Trong PowerShell hoặc POSIX shell, dấu nháy đơn quanh tên class chứa `$` giúp tránh shell thay thế biến. Đầu ra dài và có thể khác về trình bày; hãy tìm thuộc tính `MethodParameters` và các cờ `mandated`/`synthetic` nếu xuất hiện. Đừng lưu toàn bộ output `javap -v` như một chuẩn snapshot bắt buộc giống nhau trên mọi JDK.

## 9. Trường hợp đặc biệt: record, enum, nested class và bridge

### 9.1. Record (Java 16+) có compact constructor

Trên Java 16+, record là tính năng ổn định. Ví dụ:

```java
record Point(int x, int y) {
    Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
```

Một **compact canonical constructor** không viết danh sách formal parameters theo cách constructor thường, nhưng JLS vẫn định nghĩa những tham số của record component. Reflection API có những quy tắc riêng đối với record compact constructor và mô hình formal parameters. Đừng suy đoán tất cả parameter của record là synthetic chỉ vì header compact constructor không liệt kê `(int x, int y)`.

**Lưu ý phiên bản:** ví dụ `record` này chỉ dùng cho source level Java 16+; chương trình `ParameterMetadataDemo.java` phía trên không dùng record, nên tương thích Java 8.

### 9.2. Enum constructor

Enum constructors là nơi hữu ích để quan sát metadata implementation, nhưng **không dùng để thiết kế API nhận tên/ordinal qua reflection**. Số lượng và cờ của những parameter compiler sinh không phải hợp đồng truyền đối số mà source Java cho phép bạn dùng trong khai báo enum constants.

Một kiểm thử tốt nên kiểm tra `Enum.name()` hoặc `ordinal()` cho hành vi cần thiết, thay vì assert chi tiết tên `$enum$name`.

### 9.3. Static nested class khác inner member class

`static nested class` không có enclosing instance theo cùng cách như non-static inner class:

```java
class Container {
    static class Nested {
        Nested(String text) {
        }
    }
}
```

Trong class `Nested` này, constructor thông thường nhận một `String` do source khai báo; không có nhu cầu một enclosing-instance parameter kiểu `Container` như `Outer.Inner`.

### 9.4. Local và anonymous classes

Compiler có thể tạo parameter hoặc trường phụ để lưu captured local variables, enclosing instances và thông tin khác trong local/anonymous classes. Chi tiết được biểu diễn như thế nào phụ thuộc cấu trúc Java cụ thể và compiler. Không đồng nhất tất cả các thứ bổ sung thành `implicit` hoặc khẳng định tên internal luôn giống nhau.

Khi cần metadata để framework xử lý, hãy cân nhắc sử dụng **API khai báo công khai** thay vì dựa vào constructor nội bộ của anonymous/local class.

### 9.5. Bridge methods không phải synthetic parameter

Với generic override, compiler có thể sinh bridge methods. `Method.isBridge()` cho biết một method có thuộc loại bridge không; `Method.isSynthetic()` cho biết một method synthetic không. Điều này **không** đồng nghĩa các parameter của bridge method đều trả `Parameter.isSynthetic() == true`.

Một reflection scanner nên phân loại method và parameter **riêng biệt**. Nếu chỉ muốn các API nguồn do lập trình viên khai báo, cần chính sách lọc phù hợp cho từng thành phần.

## 10. Reflection và invocation: varargs rất dễ hiểu nhầm

### 10.1. Cú pháp varargs ở Java source

Giả sử:

```java
static void log(String... messages) {
    System.out.println(messages.length);
}
```

Caller có thể viết:

```java
log();
log("a");
log("a", "b");
log(new String[]{"a", "b"});
```

Nhưng `Method.getParameterTypes()` vẫn trả **một phần tử `String[].class`**. `log` không có “0–N tham số” ở bytecode; nó có một array parameter, với cờ method varargs.

### 10.2. `Method.invoke` không nên được hiểu là tự mở varargs của method đích

`Method.invoke(Object receiver, Object... args)` bản thân là một phương thức varargs của Reflection API. Điều này dễ gây nhầm lẫn giữa **mảng đối số reflection** và **mảng tham số cuối của method đích**.

Ví dụ:

```java
Method m = Example.class.getDeclaredMethod(
        "log", String[].class);

// Truyền một đối số thực sự cho method đích:
// đối số ấy là một String[].
m.invoke(null, new Object[]{new String[]{"a", "b"}});
```

`Method.invoke` ở đây nhận một mảng `Object[]` chứa **đúng một** phần tử là `String[]`. Đây là cách rõ ràng tránh làm phẳng array ngoài ý muốn. Phương thức đích vẫn có một formal parameter kiểu `String[]`.

Đừng assume rằng vì `m.isVarArgs() == true`, bạn có thể gọi `m.invoke(null, "a", "b")` để Java reflection tự gom chúng thành `String[]`. Reflection API áp dụng hợp đồng `invoke` riêng, không tự động thay thế mọi hành vi overload resolution/varargs invocation của compiler tại call site.

### 10.3. `null` trong varargs là tình huống dễ tạo lỗi

`log((String[]) null)` có thể truyền **một array null** và làm `messages.length` ném `NullPointerException`. Ngược lại `log((String) null)` truyền một phần tử null trong array được tạo cho varargs. Cú pháp cast ảnh hưởng cách compiler hiểu lời gọi.

Tương tự:

```java
static int count(String... args) {
    return args.length;
}
```

- `count()` trả 0.
- `count("x")` trả 1.
- `count(new String[]{"x", "y"})` trả 2.
- `count((String[]) null)` ném `NullPointerException` khi dereference `args.length`.

**Không coi varargs là một cơ chế null-safe**. Nếu API cần hỗ trợ đầu vào null, hãy viết hợp đồng kiểm tra rõ ràng.

## 11. Lỗi thường gặp khi đọc metadata

| Hiểu nhầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `isImplicit()` và `isSynthetic()` là đồng nghĩa | Một loại khai báo ngầm theo JLS, một loại compiler artifact | Xét hai cờ độc lập và quy tắc ngôn ngữ |
| Mọi parameter không thấy ở source đều synthetic | Enclosing-instance parameter của inner constructor là ví dụ có thể mandated | Kiểm tra `isImplicit()` và kiểu cấu trúc |
| Tham số `String...` là synthetic | Người lập trình tự khai báo nó | `isVarArgs()` mới nói về variable arity |
| `getParameterCount()` bằng số đối số của mọi lời gọi varargs | Varargs dùng array cuối, số lời gọi có thể khác | Phân biệt formal parameter count và số actual arguments |
| `String[]` đồng nghĩa `String...` | Cùng runtime array type nhưng khác cờ varargs source | Kiểm tra `Executable.isVarArgs()` |
| `arg0` chắc là tên trong source | Thiếu metadata tên có thể dẫn đến tên do reflection đặt | Kiểm tra `Parameter.isNamePresent()` |
| `-g` đủ để reflection biết tên parameter | Debug info khác `MethodParameters` | Bật `javac -parameters` khi cần |
| Một method synthetic nghĩa mọi tham số synthetic | Method và parameter có metadata riêng | Dùng `Method.isSynthetic()` và `Parameter.isSynthetic()` riêng |
| Constructor inner class có cùng tham số reflection như source | Có thể có enclosing-instance parameter | Đọc `Constructor.getParameters()`, hiểu loại class |
| `Method.invoke` luôn tự gom varargs của method đích | Invocation reflection có quy tắc truyền array argument riêng | Truyền một `String[]` đúng vị trí |
| Có thể biết tên parameter enum nội bộ trên mọi JDK | Tên/compiler representation không phải API nghiệp vụ | Dùng `Enum.name()`, `ordinal()` |
| `@SafeVarargs` tự chứng minh an toàn | Đây là cam kết về thao tác với varargs array | Review implementation và tests |
| Generic parameter types luôn có cùng số phần tử với raw types | Reflection có ngoại lệ mô hình hóa với implicit/synthetic | Hiểu tài liệu `getGenericParameterTypes()` |
| Receiver parameter `TypeName this` làm tăng tham số method | Receiver parameter là vị trí annotation, không phải formal parameter | Không cộng vào `Method.getParameterCount()` |

## 12. Quy trình viết công cụ reflection an toàn

Nếu xây dựng framework hoặc công cụ sinh metadata, đừng lọc mọi tham số “trông lạ” bằng một điều kiện duy nhất.

**Bước 1 — xác định mục đích:** bạn muốn **danh sách tham số nguồn** phục vụ giao diện người dùng, hay **chữ ký runtime** để invoke đúng constructor/method?

**Bước 2 — lấy đúng executable:** chỉ định `Method` hoặc `Constructor<?>` theo tên/kiểu, tránh dựa vào thứ tự tùy tiện từ `getDeclaredMethods()` hoặc `getDeclaredConstructors()` khi có overload.

**Bước 3 — lấy raw metadata:**

```java
Parameter[] parameters = executable.getParameters();

for (Parameter parameter : parameters) {
    System.out.println(
            "type=" + parameter.getType().getTypeName()
            + ", namePresent=" + parameter.isNamePresent()
            + ", implicit=" + parameter.isImplicit()
            + ", synthetic=" + parameter.isSynthetic()
            + ", varargs=" + parameter.isVarArgs());
}
```

**Bước 4 — xác định chính sách lọc:** có thể bỏ implicit/synthetic khi hiển thị cho người dùng theo ý nghĩa source-level, nhưng nếu chuẩn bị gọi `Constructor.newInstance(...)` thì việc bỏ chúng khỏi argument list thật có thể làm lời gọi thất bại.

**Bước 5 — xử lý varargs ở đúng tầng:** ở tầng Java source, nhận 0–N actual elements; ở tầng reflection, cung cấp array final parameter đúng kiểu.

**Bước 6 — bảo đảm metadata tên:** nếu framework dùng parameter name để mapping JSON, route hoặc dependency injection, kiểm tra build thật có `-parameters` và `isNamePresent()`; nếu không, dùng mapping/annotation tường minh thay vì đoán tên.

**Bước 7 — kiểm tra behavior trên artifact build cuối:** một bước bytecode weaving, shading hoặc code generation có thể thay đổi metadata. Không chỉ kiểm tra source rồi tin rằng class file triển khai giống hệt.

### 12.1. Cẩn thận với `Constructor.getGenericParameterTypes()`

Một chi tiết phản chiếu thường bị bỏ sót: `getGenericParameterTypes()` có thể trả số lượng/type khác với `getParameterTypes()` ở các constructor có implicit/synthetic parameters, vì việc mô hình hóa chữ ký generic và class-file metadata có ngoại lệ riêng. Oracle Javadoc có lưu ý rõ vấn đề này.

Vì vậy, **không nối hai mảng bằng chỉ số rồi mặc định luôn tương ứng một-một trong mọi constructor**, nhất là inner class, local/anonymous class hoặc những trường hợp compiler-generated. Hãy đọc hợp đồng API, kiểm tra tham số cụ thể và xử lý mismatch có chủ đích.

### 12.2. Tên tham số không phải dữ liệu bảo mật

`Parameter.getName()`, tên synthetic hoặc mandated dùng để mô tả code; chúng không tự xác thực dữ liệu đầu vào. Nếu framework dùng tên để bind request hoặc config, cần kiểm tra dữ liệu, quyền truy cập và thông báo lỗi như với mọi input khác.

## 13. Câu hỏi tự kiểm tra

1. `Parameter.isImplicit()` khác `Parameter.isSynthetic()` ở tiêu chí khai báo nguồn thế nào?
2. Với `void send(String... values)`, kiểu parameter trong reflection là gì? `getParameterCount()` bằng bao nhiêu?
3. Vì sao `void send(String[] values)` có cùng runtime parameter type nhưng không nhất thiết có cùng `isVarArgs()`?
4. Tại sao constructor của non-static inner member class có thể thấy thêm enclosing-instance parameter trong reflection?
5. Nếu compiler không lưu tên tham số, `getName()` có thể trả `arg0` mà không phản ánh tên nguồn bằng cách nào?
6. `javac -parameters` liên quan gì đến thuộc tính `MethodParameters`?
7. Vì sao không nên giả định tên/cờ của tham số enum constructor giống nhau ở mọi compiler?
8. `Method.isSynthetic()` và `Parameter.isSynthetic()` đang hỏi hai phần tử nào?
9. Khi gọi `Method.invoke` cho method nhận `String...`, vì sao cần hiểu cả mảng `Object[]` chứa invocation arguments và mảng `String[]` là final formal parameter?
10. Một tham số source varargs có nhất thiết là implicit hay synthetic không?
11. Khi dùng `getGenericParameterTypes()` trên inner constructor, vì sao phải kiểm tra kỹ độ dài mảng kết quả?
12. Vì sao chỉ có annotation `@SafeVarargs` không đủ để chứng minh implementation của một generic varargs method an toàn?

**Kết luận:** metadata về parameter phải được đọc theo **hai trục**. Trục thứ nhất là **nguồn gốc tham số** — tường minh, implicit/mandated hoặc synthetic. Trục thứ hai là **cách sử dụng lời gọi**, chẳng hạn tham số cuối có được khai báo varargs hay không. `Parameter.isImplicit()`, `isSynthetic()` và `isVarArgs()` trả lời những câu hỏi khác nhau. Hiểu thêm `-parameters`, `MethodParameters` và đặc điểm constructor giúp bạn xây dựng công cụ reflection chính xác, tránh phụ thuộc vào những tên/chi tiết compiler không phải hợp đồng Java ổn định.

## Tài liệu chuẩn

- Java SE 25 API, **`java.lang.reflect.Parameter`** (mô tả `isImplicit`, `isSynthetic`, `isVarArgs`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html
- Java SE 25 API, **`java.lang.reflect.Executable`** (tham số, varargs, metadata): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Executable.html
- Java SE 25 API, **`java.lang.reflect.Constructor`** (implicit enclosing instance, reflective invocation và generic-parameter caveat): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html
- Java Language Specification (Java SE 25), **`13.1 The Form of a Binary**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.1
- Java Virtual Machine Specification (Java SE 25), **`4.7.24 MethodParameters Attribute**: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.24
- Oracle Java tutorials, **Obtaining Names of Method Parameters** (các ví dụ synthetic/implicit cốt lõi; đối chiếu với API spec hiện hành ở trên): https://docs.oracle.com/javase/tutorial/reflect/member/methodparameterreflection.html
