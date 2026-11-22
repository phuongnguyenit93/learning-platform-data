# Parameter và getParameters: đọc metadata tham số bằng Java Reflection

## 1. Mục tiêu

Từ Java 8, Reflection API cung cấp `java.lang.reflect.Parameter` và `Executable.getParameters()` để mô tả **từng tham số hình thức** (*formal parameter*) của phương thức hoặc constructor. Tính năng này vẫn được dùng trên các JDK hiện đại và hữu ích cho logging, dependency injection, command mapping, serialization, binding request, tài liệu API và các công cụ kiểm tra contract. Điều quan trọng là: **thông tin tên tham số không tự nhiên luôn có trong file `.class`**; cần hiểu lựa chọn biên dịch `-parameters` và cách xác minh `isNamePresent()`.

Bài học tập trung vào chủ đề **Parameter và getParameters** trong nhóm *Metadata tham số*, bao gồm:

- Tìm phương thức/constructor bằng `Method` hoặc `Constructor` rồi lấy `Parameter[]`.
- Hiểu thứ tự tham số, `getName()`, `isNamePresent()`, và metadata ở classfile.
- Phân biệt `getType()`, `getParameterizedType()` và `getAnnotatedType()`, đặc biệt với generics và type-use annotations.
- Đọc annotation trên **declaration của parameter** bằng `getAnnotation()`; không nhầm với annotation nằm **trên kiểu**.
- Kiểm `isVarArgs()`, `isImplicit()`, `isSynthetic()`, modifier và tham số do compiler sinh trong một số cấu trúc.
- Biên dịch ví dụ hoàn chỉnh, đọc stdout xác định, kiểm tra trường hợp có và không có `-parameters`.
- Dùng metadata an toàn trên hệ thống có nhiều toolchain/dependency, tránh dựa vào tên `arg0` như dữ liệu nghiệp vụ.

API được bổ sung ở Java 8 nhưng **không lỗi thời**. Ví dụ chỉ dùng API Java 8-origin, có thể biên dịch với `javac --release 8` trên JDK còn được hỗ trợ. Với sản phẩm thực tế, hãy chọn release/JDK theo policy dự án; không cần cài một bản JDK cũ không còn bảo trì để học tính năng này.

## 2. Đối tượng `Parameter` là gì?

Xét phương thức:

~~~java
public String send(String recipient, int attempts) {
    return recipient + "/" + attempts;
}
~~~

Trong source, `recipient` và `attempts` là hai **formal parameters**. Khi đã load class, Reflection có thể trả danh sách đối tượng `Parameter` tương ứng. Mỗi `Parameter` giữ thông tin về một vị trí tham số của **một executable cụ thể**: tên nếu classfile có metadata phù hợp, kiểu, modifier, annotation, và mối liên hệ với method/constructor khai báo nó.

Sơ đồ:

~~~text
Class Api
  └── Method send(String, int)            -> java.lang.reflect.Method
        ├── Parameter[0]                  -> type String, name recipient (*)
        └── Parameter[1]                  -> type int, name attempts (*)

(*) Tên nguồn chỉ khả dụng qua getName() khi metadata tên thực sự được lưu
    trong classfile; nếu không có, getName() tạo tên arg0, arg1.
~~~

`Method` và `Constructor` đều kế thừa `java.lang.reflect.Executable`, là nơi định nghĩa `getParameters()` và `getParameterCount()`. Không có `Parameter` chung cho local variable tùy ý bên trong thân hàm: `getParameters()` làm việc với **tham số của executable**, không quét toàn bộ stack/local variable.

### Nơi bắt đầu truy xuất

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

Method method = Api.class.getDeclaredMethod(
    "send", String.class, int.class
);
Parameter[] parameters = method.getParameters();

System.out.println(parameters.length); // 2
~~~

Đây là đoạn minh họa: phải có class `Api` tương ứng. `getDeclaredMethod` chọn **đúng overload** bằng tên và các **kiểu tham số runtime** (`Class<?>`) theo thứ tự, không truyền tên source của tham số. Nếu `send(String)` và `send(String,int)` cùng tồn tại, `getDeclaredMethod("send", String.class, int.class)` chọn bản hai tham số.

- `getMethod(...)` tìm **public method** theo quy tắc Reflection bao gồm method kế thừa phù hợp.
- `getDeclaredMethod(...)` tìm method khai báo tại **class được chỉ định**, kể cả method không public; nó không tự tìm dọc mọi superclass.
- `getDeclaredConstructor(...)` tìm constructor khai báo trên class. Constructor **không được kế thừa**.
- `getParameters()` trả mảng theo **thứ tự tham số trong chữ ký executable** mà Reflection biểu diễn.
- `getParameterCount()` trả số tham số theo mô hình Reflection; với các constructor đặc biệt có tham số ẩn/được sinh, số lượng có thể khác điều lập trình viên tưởng từ mã nguồn.

Reflection introspection không tự gọi `send`. Đọc `Parameter[]` là thao tác xem metadata; muốn thực thi method dùng `Method.invoke` với điều kiện truy cập và exception handling riêng.

## 3. Vì sao `-parameters` là bước bắt buộc khi cần tên gốc?

Khi biên dịch Java, compiler không nhất thiết giữ **tên nguồn của formal parameters** ở metadata mà Java Reflection dùng. Đối với `javac`, tùy chọn:

~~~text
javac -parameters -encoding UTF-8 ParameterMetadataDemo.java
~~~

yêu cầu lưu tên của các parameter thuộc method/constructor được biên dịch trong **classfile attribute `MethodParameters`**. Tên này được `Parameter.getName()` trả về và `Parameter.isNamePresent()` báo `true` khi metadata chứa tên.

Không có dữ liệu tên từ classfile, `Parameter.getName()` vẫn trả chuỗi tổng hợp theo vị trí:

~~~text
arg0
arg1
arg2
...
~~~

và `isNamePresent()` là `false` đối với các tham số tương ứng. Đừng đồng nhất chuỗi `arg0` với tên đã viết ở source.

### `getParameters()` vẫn hoạt động nếu không có `-parameters`

Đây là hiểu nhầm phổ biến. Không có `-parameters`:

- `getParameters().length` vẫn cho số tham số được Reflection mô tả.
- `getType()` vẫn trả được kiểu ở runtime.
- `getParameterizedType()` có thể trả generic type metadata nếu generic signature được lưu đúng theo classfile.
- Parameter annotations vẫn có thể đọc theo retention/target phù hợp.
- **Chỉ tên nguồn** không được đảm bảo; vì vậy phải kiểm `isNamePresent()` trước khi dùng tên làm key.

`isNamePresent()` không hỏi “chuỗi getName() có khác rỗng không?”. Nó kiểm tên được lưu theo `MethodParameters`. Một tên trông giống tên nguồn không nhất thiết là điều bảo đảm nghiệp vụ khi code bị obfuscate/transform.

### `-g` hoặc `-g:vars` không thay thế `-parameters`

`-g` dùng để tạo debug information như thông tin dòng hoặc local variable table. Debug metadata có mục đích khác `MethodParameters` và **không phải hợp đồng của `Executable.getParameters()`**. Một thư viện dựa vào `getName()` nên cấu hình trực tiếp `-parameters` cho **module chứa class khai báo method/constructor** cần introspection, thay vì tin rằng IDE/debug build đã đủ.

Nếu app A dùng reflection trên class được biên dịch trong thư viện B, chỉ bật `-parameters` ở A **không thể bổ sung tên cho file class B đã đóng gói**. Phải biên dịch và đóng gói chính B có metadata phù hợp.

## 4. Các API quan trọng của `Parameter`

| API | Trả về | Cần hiểu |
| --- | --- | --- |
| `getName()` | `String` | Tên từ classfile hoặc tên tổng hợp `argN` |
| `isNamePresent()` | `boolean` | Có tên formal parameter trong `MethodParameters` hay không |
| `getType()` | `Class<?>` | Kiểu runtime đã xóa generic arguments (*erasure*) |
| `getParameterizedType()` | `Type` | Thông tin generic type của tham số khi có |
| `getAnnotatedType()` | `AnnotatedType` | Cây kiểu và type-use annotations của tham số |
| `getAnnotation(SomeAnnotation.class)` | annotation hoặc `null` | Annotation ở **parameter declaration** có retention runtime |
| `getAnnotations()` / `getDeclaredAnnotations()` | mảng annotation | Annotations gắn vào parameter declaration |
| `getDeclaringExecutable()` | `Executable` | Method hoặc constructor đã khai báo parameter |
| `getModifiers()` | `int` | Cờ modifier của formal parameter, có thể phân tích bằng `Modifier` |
| `isVarArgs()` | `boolean` | Parameter có vai trò variable arity ở một varargs method/constructor |
| `isImplicit()` | `boolean` | Parameter được ngôn ngữ khai báo ngầm theo JLS |
| `isSynthetic()` | `boolean` | Parameter do compiler tạo, không được khai báo trực tiếp hoặc ngầm trong source theo JLS |

`Parameter` triển khai `AnnotatedElement`, nên có cả API lấy repeatable annotations theo type. **Không** có method `Parameter.getDefaultValue()` cho giá trị mặc định của một formal parameter: Java thông thường không có default argument values trong declaration method như một số ngôn ngữ khác.

### `getType()` và `getParameterizedType()` khác nhau thế nào?

Với:

~~~java
void accept(java.util.List<String> messages) {}
~~~

`getType()` trả `java.util.List.class`. `getParameterizedType()` có thể trả một `ParameterizedType` mô tả `java.util.List<java.lang.String>`. Đây là **metadata về generic signature**, không làm JVM tạo một class riêng cho `List<String>`. Tại runtime, generic type erasure vẫn áp dụng.

Với type variable `<T extends Number> void add(T amount)`, `getParameterizedType()` có thể cung cấp `TypeVariable` trong khi `getType()` phản ánh erasure tương ứng. Vì vậy không ép mọi giá trị `Type` thành `Class<?>`.

### `getAnnotatedType()` dùng để làm gì?

Ví dụ:

~~~java
import java.util.List;

void accept(List<@TypeMark("item") String> messages) {}
~~~

Nếu `@TypeMark` có `@Target(TYPE_USE)` và `@Retention(RUNTIME)`, `getAnnotatedType()` của parameter phản ánh type `List<...>`. Với `List<@TypeMark String>`, annotation ở **type argument `String`**, vì vậy cần:

1. Cast root `AnnotatedType` sang `AnnotatedParameterizedType` khi kiểu thực tế là parameterized type.
2. Lấy `getAnnotatedActualTypeArguments()[0]`.
3. Gọi `getAnnotation(TypeMark.class)` ở **node String**, không chỉ ở root `List`.

Mục 6 có chương trình chạy được minh họa đúng cách truy xuất.

## 5. Declaration annotation khác type-use annotation

Đây là điểm thường gây lỗi khi làm framework mapping. Java phân biệt nơi gắn annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@interface BindingName {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}
~~~

Khi viết:

~~~java
void process(
    @BindingName("customer") java.util.List<@TypeMark("element") String> users
) {}
~~~

- `@BindingName("customer")` là **parameter declaration annotation**. Đọc bằng `Parameter.getAnnotation(BindingName.class)` (nếu retention là `RUNTIME`).
- `@TypeMark("element")` là type-use annotation trên **String làm generic argument**. Đọc từ cây `Parameter.getAnnotatedType()` rồi đi xuống annotated type argument.
- Một type-use annotation nằm ngay ở root parameter type có thể được đọc qua `getAnnotatedType().getAnnotation(...)`, không mặc nhiên là một declaration annotation.
- Nếu annotation hỗ trợ nhiều targets, vị trí cú pháp và quy tắc của Java có thể dẫn đến nhiều diễn giải; hãy chọn `@Target` rõ và kiểm bằng reflection trên classfile thực tế.

Không dùng `Parameter.getAnnotations()` để tuyên bố “không có type annotations” vì mảng đó không quét mọi node trong `AnnotatedType`. Tương tự, `getParameterizedType()` không tự trả type-use annotation đầy đủ; bạn cần `getAnnotatedType()` nếu mục tiêu là metadata trên từng lần dùng kiểu.

**Retention quan trọng:** Với `@Retention(SOURCE)`, runtime reflection không thấy. Với `CLASS`, classfile có thể lưu metadata nhưng core reflection không expose như runtime-visible annotations. Với `RUNTIME` và một vị trí reflection hỗ trợ, metadata mới có thể được lấy qua `getAnnotation`/`AnnotatedType`.

## 6. Ví dụ Java hoàn chỉnh: `ParameterMetadataDemo.java`

Tạo **`ParameterMetadataDemo.java`** (UTF-8). Chương trình sử dụng Reflection trên method, constructor, varargs, declaration annotation và nested type-use annotation. Tất cả interface/annotation/class liên quan nằm trong cùng một public class nên chỉ cần một file.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public final class ParameterMetadataDemo {
    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface ParamLabel {
        String value();
    }

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface TypeMark {
        String value();
    }

    public static final class Api {
        public Api() {
        }

        public String send(
                @ParamLabel("destination") String destination,
                int retryCount) {
            return destination + "/" + retryCount;
        }

        public void batch(
                @ParamLabel("items")
                List<@TypeMark("element") String> items,
                String... tags) {
        }
    }

    public static void main(String[] args) throws Exception {
        Method send = Api.class.getDeclaredMethod(
            "send", String.class, int.class);

        System.out.println("send count: "
            + send.getParameterCount());

        for (Parameter p : send.getParameters()) {
            ParamLabel note = p.getAnnotation(ParamLabel.class);
            String label = note == null ? "-" : note.value();

            System.out.println("parameter: " + p.getName()
                + " / " + p.isNamePresent()
                + " / " + p.getType().getSimpleName()
                + " / " + label);
        }

        Method batch = Api.class.getDeclaredMethod(
            "batch", List.class, String[].class);
        Parameter[] bp = batch.getParameters();

        System.out.println("batch varargs: "
            + batch.isVarArgs() + "/"
            + bp[0].isVarArgs() + "/"
            + bp[1].isVarArgs());

        System.out.println("generic: "
            + bp[0].getParameterizedType().getTypeName());
        System.out.println("raw: "
            + bp[0].getType().getName());

        AnnotatedParameterizedType listType =
            (AnnotatedParameterizedType) bp[0].getAnnotatedType();
        AnnotatedType elementType =
            listType.getAnnotatedActualTypeArguments()[0];
        TypeMark elementMark =
            elementType.getAnnotation(TypeMark.class);

        System.out.println("type annotation: "
            + elementMark.value());

        Constructor<Api> ctor = Api.class.getDeclaredConstructor();
        System.out.println("constructor count: "
            + ctor.getParameters().length);
    }
}
~~~

**Lệnh biên dịch và chạy** trên JDK hiện đại có `javac` hỗ trợ target 8:

~~~text
javac --release 8 -parameters -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

Có thể biên dịch theo release JDK của dự án thay vì `8` nếu không có yêu cầu tương thích bytecode cũ; phần trọng tâm ở đây là **`-parameters`**. Khi biên dịch lại để so sánh có/không flag, hãy xóa hoặc ghi đè toàn bộ các `.class` của ví dụ một cách nhất quán để tránh trộn output cũ. Không thay đổi các file build của sản phẩm chỉ để làm bài thực hành.

**Stdout chính xác, 8 dòng khi có `-parameters`:**

~~~text
send count: 2
parameter: destination / true / String / destination
parameter: retryCount / true / int / -
batch varargs: true/false/true
generic: java.util.List<java.lang.String>
raw: java.util.List
type annotation: element
constructor count: 0
~~~

### Giải thích từng kết quả

1. `getParameterCount()` cho `send(String,int)` là **2**, đúng chữ ký source.
2. Tham số `destination` có tên được lưu do `-parameters`, nên `getName()` trả `destination` và `isNamePresent() == true`. `getType().getSimpleName()` là `String`. `@ParamLabel("destination")` có retention runtime nên `getAnnotation` đọc được nhãn.
3. `retryCount` cũng có tên từ classfile; kiểu primitive là `int` và không có `ParamLabel` nên nhãn là `-`.
4. `batch` được khai báo varargs: `Method.isVarArgs() == true`. Tham số `items` **không** là varargs, còn `tags` là parameter cuối cùng `String...` nên flags là `false/true`.
5. `getParameterizedType()` của `items` mô tả `java.util.List<java.lang.String>`; `getType()` trả raw class `java.util.List`.
6. `getAnnotatedType()` tại `items` là `AnnotatedParameterizedType`; annotated actual argument là `String` có `@TypeMark("element")`, vì vậy in `element`.
7. `Api()` là constructor không có formal parameters, nên mảng trả về có độ dài **0**.

Ví dụ này không dựa vào thứ tự iteration của collection, network hay thời gian, nên stdout là xác định với compiler/JDK thực thi đúng hợp đồng và flag đã nêu. Nó không chứng minh annotation tự áp đặt ràng buộc nghiệp vụ; annotation chỉ được đọc qua Reflection.

## 7. Thử nghiệm không bật `-parameters`

Chạy một lần build khác **không có `-parameters`**, bảo đảm biên dịch lại file `ParameterMetadataDemo.java` chứ không dùng classfile cũ:

~~~text
javac --release 8 -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

Với các method thông thường như `Api.send` trong chương trình, kỳ vọng sự khác biệt chính:

~~~text
send count: 2
parameter: arg0 / false / String / destination
parameter: arg1 / false / int / -
~~~

Đây chỉ là **ba dòng đầu** để minh họa sự thay đổi; các dòng còn lại của chương trình vẫn có thể giống lần chạy với `-parameters` vì generic signature, annotation retention và varargs metadata không phụ thuộc trực tiếp vào tên formal parameters.

**Phân tích:**

- `getParameters()` vẫn có hai phần tử; compiler không “xóa tham số”.
- `getName()` trả tên tổng hợp `arg0` và `arg1`; `isNamePresent()` trả false.
- Annotation `@ParamLabel("destination")` vẫn đọc được vì được khai báo `@Retention(RUNTIME)`, độc lập với `-parameters`.
- `getParameterizedType()` và `getAnnotatedType()` vẫn có thể phản ánh generic/type-use metadata bình thường vì thông tin này nằm ở cơ chế classfile khác.
- Không dùng tên `arg0`/`arg1` làm khóa JSON hoặc tên query parameter nếu application contract kỳ vọng tên source. Cần policy rõ khi metadata thiếu.

Có thể kiểm tra classfile bằng:

~~~text
javap -v -p 'ParameterMetadataDemo$Api'
~~~

Với shell hỗ trợ single-quote literal (Bash/PowerShell), câu lệnh trên giữ ký tự `$` trong tên nested class. Trên `cmd.exe`, dùng quy tắc quote tương ứng. Tìm phần `MethodParameters` của method `send`. Nó thể hiện tên parameter khi class đã được compile với `-parameters`. Đừng nhầm với `LocalVariableTable` từ debug info.

**Giới hạn:** Một số cấu trúc đặc biệt (ví dụ record constructors, enum hoặc class do compiler/tool tạo) có quy tắc và metadata khác; không suy luận tất cả executable của mọi compiler theo ví dụ hai method bình thường này. Kiểm từng class thực tế bằng `isNamePresent()`.

## 8. Constructor và `Executable.getParameters()`

`getParameters()` dùng được cho cả method và constructor vì cả hai đều là `Executable`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

class Order {
    final String code;

    Order(String code) {
        this.code = code;
    }
}

// Trong một method:
Constructor<Order> ctor = Order.class.getDeclaredConstructor(String.class);
Parameter[] ctorParams = ctor.getParameters();
// ctorParams.length == 1
~~~

Đoạn trên chỉ là **mã minh họa**; `Order` không phải file độc lập có `main`. Nếu được biên dịch với `-parameters`, có thể đọc tên `code` từ constructor này khi classfile chứa metadata như dự kiến.

Đừng giả định compiler hoặc framework có thể gọi `getParameters()` trên mọi constructor rồi thấy đúng **danh sách chữ ký source**. Với class không static lồng bên trong class khác, constructor của inner class thường cần **đối tượng outer** và binary signature có thể chứa tham số bổ sung. Enum constructor và các trường hợp compiler-generated khác có parameter/metadata riêng. Khi viết reflection mapper, phải xử lý các loại này thay vì giả định mọi `Parameter[]` chỉ gồm tham số user ghi trực tiếp.

### Phân biệt `getDeclaredConstructors()` và `getDeclaredConstructor(...)`

~~~java
java.lang.reflect.Constructor<?>[] all =
    SomeType.class.getDeclaredConstructors();
~~~

Một class có thể có nhiều overload constructor; inspect từng constructor và parameter riêng, tránh lấy phần tử thứ nhất rồi kết luận “constructor mặc định”. Thứ tự mảng reflection của các member **không phải thứ tự source đảm bảo**. Nếu cần constructor cụ thể, chọn theo signature; nếu cần duyệt, sort theo một tiêu chí rõ và không dựa vào index ngẫu nhiên.

Nếu class không có constructor zero-argument, gọi `getDeclaredConstructor()` sẽ ném `NoSuchMethodException`; flag `-parameters` không thay đổi việc constructor đó tồn tại hay không.

## 9. `isVarArgs()` và kiểu `String...`

Trong Java, một method varargs dùng dấu `...` ở formal parameter cuối cùng:

~~~java
void log(String level, String... messages) {
}
~~~

Ở reflection:

- `getParameters()` có **hai** phần tử, không phải một phần tử cho mỗi argument được truyền tại runtime.
- `getType()` của parameter `messages` là `String[].class`, vì varargs dựa trên array ở runtime.
- `Method.isVarArgs()` trả `true`; `Parameter.isVarArgs()` trả `true` cho parameter biểu diễn variable argument list (tham số cuối).
- `getName()` của `messages` vẫn cần metadata tên như các parameter khác.

~~~java
// Trong một method đã có Method m trỏ đúng tới log:
for (java.lang.reflect.Parameter p : m.getParameters()) {
    System.out.println(p.getType().getTypeName()
        + " / " + p.isVarArgs());
}
~~~

Khi kiểm overload bằng `getDeclaredMethod("log", String.class, String[].class)`, hãy dùng **`String[].class`**, không có một `String...class` riêng. Nếu dùng `Method.invoke` cho varargs, còn có quy tắc đóng gói argument mảng khi qua API varargs của reflection; đó là câu chuyện invocation riêng, không đổi mô hình `Parameter`.

**Điểm thiết kế:** Việc một framework nhìn thấy array parameter không cho phép tự suy ra đây là `varargs`; phải xem metadata `isVarArgs()`. Ngược lại, nếu cần kiểm dữ liệu thực tế của từng phần tử, phải kiểm nội dung mảng do caller truyền, không chỉ metadata kiểu.

## 10. `isImplicit()` và `isSynthetic()`: tránh suy đoán

Hai method này dễ bị nhầm với “tên bị thiếu” hoặc “compiler tối ưu”:

- `isImplicit()`: parameter được **khai báo ngầm theo quy tắc của ngôn ngữ Java**, không có declarator nguồn bình thường cho parameter đó.
- `isSynthetic()`: parameter là **cấu trúc do compiler tạo**, không được khai báo trực tiếp hoặc ngầm trong source theo cách JLS mô tả.
- `isNamePresent()`: **hoàn toàn khác** — chỉ hỏi tên parameter có trong metadata classfile không.
- `isVarArgs()`: hỏi về vai trò variable-arity, không liên quan trực tiếp hai cờ trên.

Ví dụ các constructor của non-static inner class có thể có enclosing-instance parameter ở binary-level; enum constructor có thông tin tham số do ngôn ngữ/compiler cần phục vụ cơ chế enum. Các cờ/metadata cụ thể phụ thuộc tình huống, compiler và classfile. **Không dùng quy tắc cứng “bỏ Parameter[0] nếu tên arg0”**: đó có thể là tham số nghiệp vụ bình thường bị thiếu metadata tên.

Một cách quan sát có ích:

~~~java
// Code fragment trong một công cụ inspection:
for (java.lang.reflect.Parameter p : executable.getParameters()) {
    System.out.println(p.getName()
        + " | namePresent=" + p.isNamePresent()
        + " | implicit=" + p.isImplicit()
        + " | synthetic=" + p.isSynthetic()
        + " | varargs=" + p.isVarArgs());
}
~~~

Với một API phục vụ binding, thiết kế rule dựa vào **cấu trúc executable**, type, annotation, các flag đã được xác nhận, và compiler versions được hỗ trợ. Đừng đoán theo `argN`. Nếu cần phân biệt source-level và bytecode-level signature của generated class, thêm unit test với bản compiler/build thực tế.

### `getModifiers()` không phải cách duy nhất biết parameter

`Parameter.getModifiers()` cho bit mask modifier theo mô hình Reflection. Có thể dùng `java.lang.reflect.Modifier` để phân tích modifier được hỗ trợ, nhưng không nên suy ra annotation hoặc name presence chỉ từ mask này. `final` trên parameter source có thể được phản ánh khi metadata thích hợp; việc field/method có modifier `final` là vấn đề khác.

## 11. Tên tham số và generic/type-use annotations khi dùng framework

Các framework dùng reflection có thể muốn ánh xạ:

~~~text
Request field name -> formal parameter -> converter -> value -> method invocation
~~~

Nếu tên formal parameter là một phần API contract, bạn cần chính sách rõ ràng:

1. Bật `-parameters` cho các module chứa endpoint, constructor dependency-injection hoặc method cần map theo tên.
2. Tại startup/test, kiểm `Parameter.isNamePresent()` và fail sớm hoặc fallback sang annotation **tường minh** (ví dụ annotation binding của framework thực sự đang dùng).
3. Không giả định framework/library tự đọc `getName()` trong mọi trường hợp; kiểm tài liệu version đang hỗ trợ vì có công cụ dùng index/annotation khác.
4. Nếu qua obfuscator, bytecode optimizer, shading/relocation hoặc code generator, xác minh `MethodParameters` có được giữ và tên có thay đổi hay không.
5. Với deployment nhiều module, kiểm artifact **đã đóng gói và chạy thật**, không chỉ class trong IDE.
6. Không dùng tên tham số từ reflection làm căn cứ **phân quyền** hoặc validation dữ liệu đầu vào. Đây là metadata giúp binding, không phải bằng chứng dữ liệu an toàn.

Khi annotation hỗ trợ binding như `@ParamLabel` ở ví dụ chính, hãy phân biệt nhãn tường minh này với tên Java source: `getAnnotation(ParamLabel.class).value()` có thể độc lập với `getName()`, và một framework có thể chọn ưu tiên annotation để đảm bảo contract ổn định khi refactor tên source. Điều đó cần được ghi thành rule và test, không đoán.

### Tên source không phải API ổn định mặc định

Đổi tên `recipient` thành `target` trong source rồi recompile có thể **không** làm thay đổi JVM method descriptor `(Ljava/lang/String;I)Ljava/lang/String;`, nhưng làm thay đổi thông tin tên nếu build lưu `MethodParameters`. Một application bind theo tên có thể hỏng **hành vi** dù binary method vẫn tồn tại. Khi đổi tên parameter của public API, review các client/framework có đọc metadata hay không.

## 12. Kiểm thử đảm bảo metadata có mặt trong bản build

Để test ổn định, tách thành hai thư mục output khác nhau để tránh classfile cũ:

~~~text
metadata-test/
  sources/ParameterMetadataDemo.java
  with-names/
  without-names/
~~~

Tại thư mục `metadata-test`:

~~~text
javac --release 8 -parameters -encoding UTF-8 -d with-names sources/ParameterMetadataDemo.java
java -cp with-names ParameterMetadataDemo

javac --release 8 -encoding UTF-8 -d without-names sources/ParameterMetadataDemo.java
java -cp without-names ParameterMetadataDemo
~~~

Trên Windows và Unix, ví dụ `-cp` một thư mục không có classpath separator nên cú pháp giống nhau. Hãy tạo trước thư mục output nếu môi trường/compiler cần. Các package/nested classes do `javac` sinh được lưu trong cùng output tương ứng, không trộn hai lần build.

**Tiêu chí kiểm thử dương (`with-names`):** `send.getParameters()[0].isNamePresent()` phải true, `getName()` là `destination`. **Tiêu chí âm (`without-names`):** đối với method thường trong ví dụ, `isNamePresent()` phải false và `getName()` là `arg0`. Trong cả hai lần, assert length, kiểu và annotation được lấy là chính xác.

Đối với project có nhiều toolchains, có thể tích hợp kiểm tra vào JUnit đang được duy trì, nhưng test **phải chạy trên class đã build** bằng cấu hình packaging dự kiến, không build lại fixture âm bằng một task vô tình thêm `-parameters`.

### Kiểm tra bằng `javap` và CI

~~~text
javap -v -p 'ParameterMetadataDemo$Api'
~~~

`javap` cho phép xem `MethodParameters` trong classfile. CI có thể chạy kiểm tra cơ chế này trên artifact public; tuy nhiên sự có mặt của attribute **không đủ** nếu tên bị đổi bởi post-processing. Nên kết hợp assert bằng reflection và một contract test thực tế để chứng minh framework vẫn nhận tên đúng.

Một bảng test nên có:

| Tình huống | Kỳ vọng |
| --- | --- |
| Build với `-parameters` | `isNamePresent() == true` cho parameter thông thường |
| Build không flag | `getName()` có thể là `arg0`, `isNamePresent() == false` |
| Method overload | `getDeclaredMethod` chọn đúng signature/arity |
| Generic parameter `List<String>` | `getType()==List.class`; `getParameterizedType()` giữ thông tin generic nếu signature có |
| Type-use annotation ở `String` trong `List` | `getAnnotatedType()` và annotated type argument đọc được |
| Declaration annotation ở parameter | `Parameter.getAnnotation(...)` đọc được nếu RUNTIME |
| Varargs method | `Method.isVarArgs()` và `Parameter.isVarArgs()` khớp |
| Constructor đặc biệt | Không suy đoán index/ẩn; kiểm thực trên compiler mục tiêu |
| Obfuscated/packaged artifact | Kiểm tên và annotation còn đúng sau đóng gói |

**Regression canary:** Một test cố tình compile fixture thiếu `-parameters` rồi xác nhận `isNamePresent()==false` giúp phân biệt flag thực sự gây khác biệt; một test tích cực trên artifact deploy giúp phát hiện build plugin bỏ mất flag.

### Maven, Gradle và các công cụ hiện đại

Dùng cơ chế compiler configuration chính thức của phiên bản Maven/Gradle hiện được dự án hỗ trợ để truyền `-parameters` vào **JavaCompile task**/compiler. Không ghi chú một cấu hình cụ thể như “luôn đúng cho mọi phiên bản” khi project chưa xác định toolchain. Với nhiều source sets, annotation processors hoặc modules, kiểm từng task tạo class được reflection sử dụng.

Các framework có annotation explicit cho binding có thể không phụ thuộc tên parameter; khi đó không nhất thiết phải bật flag cho **mọi** module. Quyết định phải dựa vào contract triển khai và test metadata thực tế.

## 13. Những lỗi phổ biến

### Lỗi 1: `getParameters()` không trả tên source

**Triệu chứng:** `getName()` là `arg0`. **Nguyên nhân thường gặp:** classfile thiếu tên formal parameter. **Cách xử lý:** bật `-parameters` cho module khai báo executable, clean rebuild và kiểm `isNamePresent()`/`javap` trên artifact thật.

### Lỗi 2: Dùng `-g:vars` nhưng vẫn thấy `argN`

Debug info và `MethodParameters` là hai nguồn metadata khác nhau. Dùng `-parameters` khi muốn hợp đồng Reflection về tên. Không dựa vào debug flags như một cơ chế thay thế.

### Lỗi 3: Chỉ tìm `Method`, bỏ qua `Constructor`

Nhiều dependency injection/serialization frameworks chọn constructor. Nếu API cần hỗ trợ constructor binding, phải inspect `getDeclaredConstructors()` hoặc signature constructor cụ thể, rồi lấy `getParameters()` của từng constructor.

### Lỗi 4: Đọc nhầm annotation trên type từ `Parameter.getAnnotations()`

Annotation trong `List<@TypeMark String>` nằm ở nested type argument. Dùng `getAnnotatedType()` và `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` thay vì tìm mọi annotation ở root declaration.

### Lỗi 5: Cast mọi `getParameterizedType()` thành `Class`

Khi parameter có generics, `Type` có thể là `ParameterizedType` hoặc `TypeVariable`, `GenericArrayType`, `WildcardType` ở các vị trí thích hợp. Kiểm loại trước khi cast, dùng `getType()` nếu chỉ cần raw class.

### Lỗi 6: Nghĩ `String...` không phải array

Varargs được biểu diễn bằng array runtime; `getDeclaredMethod` dùng `String[].class`, `Parameter.isVarArgs()` cho biết vị trí variable argument list. Đừng dựng class literal không tồn tại như `String...class`.

### Lỗi 7: Đoán implicit/synthetic theo index hoặc `argN`

Một constructor đặc biệt có thể chứa tham số do ngôn ngữ/compiler thêm. Phải kiểm flags và bytecode thực tế thay vì bỏ bừa tham số đầu. Tên thiếu metadata và parameter do compiler sinh là **hai chuyện khác nhau**.

### Lỗi 8: Gắn logic bảo mật vào tên parameter

Tên source có thể thay khi refactor hoặc qua obfuscation. Không dùng `getName()` làm xác thực data, phân quyền hay validate. Sử dụng annotation/hợp đồng binding riêng và kiểm dữ liệu runtime thật.

### Lỗi 9: Compile lại sai module

Bật `-parameters` chỉ cho app trong khi method nằm trong một dependency jar đã compile không có flag sẽ không thay đổi `Parameter` của dependency. Kiểm nơi **class gốc được build**, không chỉ nơi chạy reflection.

### Lỗi 10: So sánh thông báo reflection như hợp đồng cross-JDK

`Parameter.toString()` thuận tiện để debug nhưng không nên dùng làm serialization protocol hay khóa nghiệp vụ. Dùng từng API có nghĩa rõ như `getType()`, `getName()` cùng `isNamePresent()`; lưu contract ổn định do ứng dụng định nghĩa.

## 14. Bài tập có đáp án định hướng

**Bài 1 — Hai kiểu biên dịch:** Chạy ví dụ mục 6 với và không có `-parameters`. Ghi lại `getName()`/`isNamePresent()` của `destination`; dự kiến **destination/true** và **arg0/false** đối với method thường.

**Bài 2 — Constructor:** Tạo `class Ticket { Ticket(String code,int quantity) {} }`. Dùng `getDeclaredConstructor(String.class,int.class).getParameters()` và in số tham số. Đáp án: **2**; tên source chỉ hiện nếu classfile lưu tên phù hợp.

**Bài 3 — Overloading:** Thêm `void send(String)` cạnh `send(String,int)`. Dùng `getDeclaredMethod` để lấy chính xác mỗi overload và kiểm `getParameterCount()` là **1** và **2**.

**Bài 4 — Generic:** Tạo method nhận `List<String> names`. So sánh `getType().getName()` (**java.util.List**) với `getParameterizedType().getTypeName()` (**java.util.List<java.lang.String>**) trong build javac có generic signature.

**Bài 5 — Declaration và type-use:** Đặt `@ParamLabel("input")` ở parameter declaration và `@TypeMark("leaf")` trong `List<@TypeMark String>`. Đọc hai annotation bằng hai đường reflection đúng; giải thích vì sao vị trí khác nhau.

**Bài 6 — Varargs:** Viết `void log(int level, String... messages)`. Dùng reflection kiểm `getParameterCount()==2`; parameter `messages` có `getType()==String[].class` và `isVarArgs()==true`.

**Bài 7 — Tên giả:** Nếu `isNamePresent()==false`, viết một mapper phải fail fast với diagnostic rõ hoặc dùng annotation binding tường minh. Không gửi tên `arg0` ra public API một cách ngầm định.

**Bài 8 — Inner/enum:** Tạo non-static inner class và enum có constructor. Dùng `getDeclaredConstructors()`/`getParameters()` để quan sát các tham số đặc biệt và flags. So sánh trên compiler mà dự án hỗ trợ; tránh áp đặt kỳ vọng index cứng.

**Bài 9 — CI matrix:** Thiết kế hai output directories với/không flag và test assertions. Thêm bước kiểm packaged artifact sau obfuscation/shading. Nêu vì sao `javac -g` không đáp ứng cùng yêu cầu.

**Bài 10 — Review framework:** Một endpoint cần bind tên `customerId` vào tham số method. Kiểm metadata `isNamePresent()`, khả năng refactor/obfuscation, annotation framework và test migration khi đổi tên parameter.

**Tiêu chí đạt:** Bạn lấy được `Parameter[]` từ method/constructor, biết phân biệt tên source và `argN`, hiểu đúng tác dụng `-parameters`, đọc generic/type-use/declaration metadata qua API phù hợp, xử lý varargs và các tham số compiler-generated thận trọng, và chạy chương trình `ParameterMetadataDemo.java` khớp tám dòng stdout khi dùng đúng flags.

## 15. Tài liệu chính thức

- Java SE API `java.lang.reflect.Parameter` (JDK hiện đại): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Parameter.html
- Java SE API `java.lang.reflect.Executable`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Executable.html
- Java SE API `java.lang.reflect.Method` và `Constructor`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/package-summary.html
- Java SE API `AnnotatedType`/`AnnotatedParameterizedType`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html
- `javac` option `-parameters` (JDK 17 tài liệu chính thức, semantics vẫn áp dụng): https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- JVM Specification, `4.7.24 MethodParameters attribute: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.24
- Java Language Specification, `8.4.1 Formal Parameters: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1

**Ghi nhớ:** `Executable.getParameters()` luôn bắt đầu từ **chữ ký executable**, không phải từ bản source mà công cụ có thể truy xuất lại. Khi muốn tên thật, hãy **biên dịch class khai báo method/constructor bằng `-parameters`**, xác minh `isNamePresent()`, và dùng `Parameter`/`AnnotatedType` đúng tầng để đọc metadata. Không nhầm metadata hữu ích với cơ chế kiểm tra dữ liệu hoặc bảo mật tự động.