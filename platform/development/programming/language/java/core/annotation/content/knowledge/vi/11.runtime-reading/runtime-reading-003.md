# Đọc annotation trên Parameter và tham số phương thức bằng Java Reflection

Khi một phương thức Java nhận tham số, annotation có thể được gắn **trên từng tham số** để mô tả metadata như tên tham số trong một giao thức, quy tắc validate, trạng thái bắt buộc/tùy chọn hoặc chỉ dẫn cho công cụ. Ở runtime, Java Reflection cung cấp `java.lang.reflect.Parameter` và các phương thức trên `Method` hoặc `Constructor` để lấy dữ liệu này.

Ví dụ ý tưởng:

```java
void checkout(@Input("ticketId") String id, @Input("count") int count) {
}
```

Với annotation `@Input` được khai báo đúng cách và có retention `RUNTIME`, bạn có thể hỏi Reflection: *tham số thứ nhất có `@Input` không, nếu có giá trị `value()` là gì?* Đây là thông tin **về tham số**, không phải giá trị thực tế của biến `id` hoặc `count` khi phương thức được gọi.

Bài học tập trung vào cách **đọc annotation trên parameter bằng Reflection**, liên hệ giữa `Method`/`Constructor` và `Parameter`, tính đúng đắn của `@Target(PARAMETER)` và `@Retention(RUNTIME)`, cách đọc annotation trên nhiều tham số, các trường hợp annotation lặp, và cách phân biệt annotation trên **khai báo tham số** với annotation trên **kiểu của tham số**.

## 1. Phân biệt parameter, argument và annotation

Ba khái niệm thường bị trộn lẫn:

- **Parameter (tham số hình thức):** biến được khai báo trong chữ ký phương thức, ví dụ `String id` trong `void pay(String id)`.
- **Argument (đối số):** giá trị được truyền tại một lần gọi cụ thể, ví dụ `pay("A123")` truyền chuỗi `"A123"`.
- **Parameter annotation:** metadata gắn vào **khai báo parameter**, ví dụ `@Input("ticketId") String id`.

Khi bạn dùng `Method.getParameters()`, bạn nhận các đối tượng `Parameter` mô tả **khai báo phương thức đã biên dịch**. Bạn **không** nhận các argument của lần gọi, cũng không đọc được giá trị biến local hiện tại.

Ví dụ:

```java
void pay(@Input("ticketId") String id) {
    // id là giá trị thực tế chỉ khi một lời gọi chạy vào đây.
}
```

`@Input("ticketId")` là metadata tĩnh gắn ở khai báo. Một chương trình có thể dùng nó để quyết định cách map dữ liệu request vào tham số, nhưng **việc mapping phải do code hoặc framework tự thực hiện**. Annotation không tự truyền argument và không tự validate dữ liệu.

## 2. Khai báo annotation cho parameter

Một loại annotation dùng để mô tả tham số thường có:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Input {
    String value();
}
```

Giải thích:

1. `@interface Input` định nghĩa annotation type `Input`.
2. `@Target(ElementType.PARAMETER)` cho phép gắn `Input` trên **khai báo tham số hình thức** của phương thức hoặc constructor, không phải tự động gắn ở mọi chỗ mang tên gần giống.
3. `@Retention(RetentionPolicy.RUNTIME)` giữ metadata để các API Reflection chuẩn có thể đọc nó khi chương trình chạy.
4. `String value()` khai báo một phần tử annotation. Khi viết `@Input("ticketId")`, Java dùng dạng rút gọn cho `@Input(value = "ticketId")`.

Nếu annotation chỉ có `@Target(PARAMETER)` nhưng **không khai báo `@Retention`**, retention mặc định là `CLASS`: compiler vẫn có thể ghi dữ liệu annotation vào class file nhưng API `Parameter.getAnnotation(Input.class)` **không đọc được**.

Tương tự, `@Retention(SOURCE)` không tạo metadata runtime có thể đọc qua Reflection. Với mục tiêu của bài học, ưu tiên `RUNTIME`.

Nếu một annotation định nghĩa `@Target(TYPE_USE)` thay vì `PARAMETER`, ý nghĩa và API đọc khác; mục 8 trình bày ranh giới quan trọng này.

## 3. Luồng đọc annotation từ một phương thức

Các bước tiêu chuẩn:

1. Xác định `Class<?>` sở hữu phương thức, ví dụ `Checkout.class`.
2. Lấy `Method` phù hợp với **tên và danh sách kiểu tham số**, ví dụ `getDeclaredMethod("confirm", String.class, int.class)`.
3. Gọi `Method.getParameters()` để nhận mảng `Parameter[]` theo thứ tự tham số trong chữ ký.
4. Trên mỗi `Parameter`, gọi `getAnnotation(Input.class)`, `getAnnotationsByType(...)` hoặc `isAnnotationPresent(...)`.
5. Nếu annotation tồn tại, đọc các phần tử của nó, chẳng hạn `annotation.value()`.

Sơ đồ:

```text
Checkout.class
     |
     +-- getDeclaredMethod("confirm", String.class, int.class)
               |
               v
             Method
               |
               +-- getParameters()
                         |
                         +-- Parameter[0] --> getAnnotation(Input.class)
                         |
                         +-- Parameter[1] --> getAnnotation(Input.class)
```

`Method` biểu diễn một khai báo method, còn `Parameter` biểu diễn một vị trí tham số của `Method` đó. `Parameter` cũng triển khai `AnnotatedElement` nên có các API quen thuộc như `getAnnotation`, `getDeclaredAnnotations`, `getAnnotationsByType` và `isAnnotationPresent`.

### 3.1. getMethod và getDeclaredMethod khác nhau

- `getMethod(name, parameterTypes...)` tìm **public method** thích hợp trên lớp, gồm các public method được thừa kế theo quy tắc Reflection.
- `getDeclaredMethod(name, parameterTypes...)` tìm method **được khai báo trực tiếp trên lớp đó**, kể cả method private, nhưng không tự tìm method kế thừa.
- Cả hai đều cần **đúng tên và kiểu tham số**; overload không được phân biệt bằng tên biến hoặc annotation.
- Khi chỉ có tên mà không biết chữ ký, có thể duyệt `getDeclaredMethods()` rồi lọc, nhưng phải tự xử lý các overload và synthetic/bridge methods nếu có.

Ví dụ `getDeclaredMethod("confirm", String.class, int.class, String[].class)` tìm đúng một phương thức có ba tham số được mô tả trong ví dụ đầy đủ ở mục 4.

## 4. Ví dụ Java 17+ đầy đủ: đọc nhiều annotation trên các parameter

Tạo file **`ParameterAnnotationDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Bind {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface OptionalArg {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Sanitized {
}

class Checkout {
    public void confirm(
            @Bind("ticket") String ticket,
            @Bind("count") @OptionalArg int count,
            @Bind("coupon") String... coupons) {
    }

    public void prepare(@Sanitized String code) {
    }
}

public class ParameterAnnotationDemo {
    public static void main(String[] args) throws Exception {
        Method confirm = Checkout.class.getDeclaredMethod(
                "confirm", String.class, int.class, String[].class);

        for (Parameter parameter : confirm.getParameters()) {
            Bind bind = parameter.getAnnotation(Bind.class);
            System.out.println(parameter.getType().getSimpleName()
                    + " | " + bind.value()
                    + " | optional=" + parameter.isAnnotationPresent(OptionalArg.class)
                    + " | varargs=" + parameter.isVarArgs());
        }

        System.out.println("annotation rows="
                + confirm.getParameterAnnotations().length);

        Method prepare = Checkout.class.getDeclaredMethod("prepare", String.class);
        Parameter code = prepare.getParameters()[0];

        System.out.println("parameter marker="
                + code.isAnnotationPresent(Sanitized.class));
        System.out.println("type-use marker="
                + code.getAnnotatedType().isAnnotationPresent(Sanitized.class));
    }
}
```

Biên dịch bằng JDK 17 trở lên và bật `-parameters` để compiler lưu **tên tham số khai báo** (không bắt buộc để đọc annotation):

```bash
javac --release 17 -parameters ParameterAnnotationDemo.java
java ParameterAnnotationDemo
```

Stdout chính xác:

```text
String | ticket | optional=false | varargs=false
int | count | optional=true | varargs=false
String[] | coupon | optional=false | varargs=true
annotation rows=3
parameter marker=false
type-use marker=true
```

### 4.1. Vì sao kết quả đúng như vậy?

- `confirm` có ba tham số được khai báo lần lượt là `String`, `int` và `String...`. Trong Reflection, varargs `String...` có kiểu `String[]`, nên tên kiểu đơn giản là `String[]`.
- Cả ba tham số được gắn `@Bind`; gọi `getAnnotation(Bind.class)` lấy đúng `value()` lần lượt `"ticket"`, `"count"`, `"coupon"`.
- Chỉ tham số `count` có `@OptionalArg`, nên `isAnnotationPresent(OptionalArg.class)` chỉ `true` ở tham số thứ hai.
- `Parameter.isVarArgs()` chỉ đúng cho tham số varargs thực tế cuối cùng trong khai báo `confirm`.
- `Method.getParameterAnnotations()` trả cấu trúc có một hàng cho từng tham số; mảng ngoài có độ dài `3`.
- `@Sanitized` chỉ có target `TYPE_USE`, nên không thuộc nhóm annotation trên **declaration parameter**. `Parameter.isAnnotationPresent(Sanitized.class)` trả `false`.
- `Parameter.getAnnotatedType()` trả `AnnotatedType` cho **kiểu tham số**; ở đó `@Sanitized` hiện diện, nên dòng cuối trả `true`.

Đoạn này **không gọi `confirm(...)` hoặc `prepare(...)`**. Toàn bộ output là do chương trình chủ động đọc metadata từ định nghĩa phương thức, không phải kết quả chạy logic nghiệp vụ của hai phương thức đó.

**Kiểm tra thực nghiệm:** chương trình trên đã được biên dịch với `javac --release 17 -parameters` và chạy thành công, cho đúng sáu dòng stdout được liệt kê.

## 5. API quan trọng trên Parameter

`java.lang.reflect.Parameter` được đưa vào Java 8 và vẫn là API chuẩn ở Java 17+.

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `parameter.getAnnotation(Input.class)` | Lấy một annotation loại `Input` nếu hiện diện theo quy tắc API | Có thể trả `null` |
| `parameter.isAnnotationPresent(Input.class)` | Có annotation loại `Input` được Reflection nhìn thấy không? | Không đọc giá trị annotation |
| `parameter.getAnnotations()` | Mảng annotation hiện diện trên parameter | Không tự bảo đảm mở container repeatable |
| `parameter.getDeclaredAnnotations()` | Các annotation được khai báo trực tiếp trên parameter | Với parameter, không có cơ chế kế thừa annotation của class theo kiểu `@Inherited` |
| `parameter.getAnnotationsByType(Input.class)` | Mảng các annotation của loại này, gồm trường hợp repeatable khi phù hợp | Dễ dùng nếu `Input` có thể lặp |
| `parameter.getDeclaredAnnotationsByType(Input.class)` | Các annotation loại đó được khai báo trực tiếp hoặc gián tiếp qua container | Dùng khi muốn rõ phạm vi declared |
| `parameter.getType()` | Kiểu tham số dưới dạng `Class<?>` sau erasure, ví dụ `String[].class` | Chưa chứa chi tiết generic |
| `parameter.getParameterizedType()` | `Type` có thể mang thông tin generic, ví dụ `List<String>` | Khác với giá trị annotation |
| `parameter.getAnnotatedType()` | `AnnotatedType` mô tả kiểu của tham số và type-use annotations | Không thay thế API đọc declaration annotation |
| `parameter.getName()` | Tên parameter từ metadata hoặc tên tổng hợp khi thiếu thông tin | Phụ thuộc cờ biên dịch và nguồn bytecode |
| `parameter.isNamePresent()` | Tên parameter thật có được lưu trong class file không? | Nên kiểm tra trước khi dựa vào `getName()` |
| `parameter.isVarArgs()` | Tham số có phải varargs không | Chỉ một vị trí hợp lệ trong danh sách |
| `parameter.getDeclaringExecutable()` | `Method` hoặc `Constructor` sở hữu parameter | Trả `Executable` |

**Cảnh báo `null`:** không được viết `parameter.getAnnotation(Input.class).value()` nếu chưa chắc annotation tồn tại. Khi không có annotation phù hợp hoặc retention không phải `RUNTIME`, `getAnnotation` thường trả `null`.

Cách an toàn:

```java
Input input = parameter.getAnnotation(Input.class);
if (input != null) {
    System.out.println(input.value());
}
```

Đoạn này là **snippet** dùng trong vòng lặp có biến `parameter`, không phải file chạy riêng.

## 6. Đọc qua Method.getParameterAnnotations()

Ngoài `Parameter[]`, Reflection còn hỗ trợ API cũ:

```java
Annotation[][] annotations = method.getParameterAnnotations();
```

`java.lang.annotation.Annotation[][]` là **mảng hai chiều**:

- `annotations[i]` là mảng annotation gắn trên tham số thứ `i`.
- `annotations[i][j]` là annotation thứ `j` của tham số `i`.
- Mảng trong có thể rỗng nếu tham số đó không có annotation runtime-visible được API trả về.

Ví dụ với `confirm` ở mục 4 (nhớ import `java.lang.annotation.Annotation`):

```java
Annotation[][] matrix = confirm.getParameterAnnotations();
Parameter[] parameters = confirm.getParameters();

for (int i = 0; i < parameters.length; i++) {
    System.out.println(
            i + ": " + parameters[i].getType().getSimpleName()
                    + ", annotation count=" + matrix[i].length);
}
```

Dự kiến kết quả trong ví dụ này:

```text
0: String, annotation count=1
1: int, annotation count=2
2: String[], annotation count=1
```

`@Sanitized` ở phương thức `prepare` là annotation trên kiểu sử dụng, nên **không tự xuất hiện trong mảng declaration annotations** trả bởi `getParameterAnnotations()`.

### 6.1. Nên ưu tiên API nào?

Nếu cần thao tác với từng tham số như một đối tượng, dùng:

```java
for (Parameter p : method.getParameters()) {
    Bind bind = p.getAnnotation(Bind.class);
}
```

Nếu đang làm việc với một thư viện cũ hoặc API trả annotation matrix, dùng `method.getParameterAnnotations()` và ánh xạ theo **vị trí**.

Không nên cố suy ra tham số từ tên annotation hoặc index không kiểm tra. Dù annotation matrix được thiết kế để tương ứng với tham số trong biểu diễn method, các trường hợp executable đặc biệt có **tham số ngầm/synthetic** hoặc thông tin được compiler sinh thêm có thể làm việc phân tích phức tạp hơn. Khi xây framework tổng quát xử lý constructor, enum, inner class, hãy kiểm tra metadata `Parameter`, bytecode cụ thể và cách compiler biểu diễn chúng, thay vì giả định mọi constructor đều giống method source bình thường.

## 7. Parameter name và annotation là hai loại metadata độc lập

Nhiều người thấy `Parameter.getName()` trả `arg0`, `arg1` rồi cho rằng không đọc được annotation. Đây là **hai vấn đề khác nhau**.

### 7.1. Không bật -parameters

Ví dụ:

```bash
javac --release 17 ParameterAnnotationDemo.java
```

Trong bytecode do `javac` tạo mà không bật lưu metadata tên tham số, `isNamePresent()` thường trả `false`, còn `getName()` trả tên tổng hợp như `arg0`, `arg1`. Điều này **không làm mất annotation `@Bind` có retention `RUNTIME`**.

### 7.2. Bật -parameters

```bash
javac --release 17 -parameters ParameterAnnotationDemo.java
```

Compiler lưu tên parameter vào metadata phù hợp trong class file. Khi đó, với những tham số được lưu tên, `parameter.isNamePresent()` trả `true`, `getName()` có thể trả `ticket`, `count`, `coupons` theo tên source.

**Vì sao quan trọng?**

Nếu viết một mini-framework tự ánh xạ dữ liệu theo tên Java parameter, cần đảm bảo build bật `-parameters` hoặc dùng metadata khác đáng tin cậy. Trong ví dụ này, dùng `@Bind("ticket")` cho tên mapping **không phụ thuộc** vào việc parameter trong Java có tên `ticket` hay `arg0`.

Chữ ký `getDeclaredMethod(...)` cũng dùng **kiểu tham số**, không dùng tên tham số. Hai overload `confirm(String)` và `confirm(int)` cần được phân biệt bằng `String.class` và `int.class`, chứ không phải `@Bind` hay biến `ticket`.

## 8. Phân biệt ElementType.PARAMETER và ElementType.TYPE_USE

Đây là chỗ quan trọng nhất khi đọc annotation trên tham số theo hai nghĩa khác nhau.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface FromRequest {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface CleanType {}

class Api {
    void accept(@FromRequest @CleanType String name) {}
}
```

`@FromRequest` gắn lên **parameter declaration**. `@CleanType` gắn lên **type use `String`**.

Cùng xuất hiện trên một dòng source nhưng cách đọc khác nhau:

```java
Method m = Api.class.getDeclaredMethod("accept", String.class);
Parameter p = m.getParameters()[0];

boolean fromRequest =
        p.isAnnotationPresent(FromRequest.class);

boolean cleanType =
        p.getAnnotatedType().isAnnotationPresent(CleanType.class);
```

Kết quả của hai boolean trong ngữ cảnh khai báo này đều là `true`, nhưng đi theo **hai API và hai loại metadata khác nhau**.

| Vị trí annotation | @Target | API phù hợp |
| --- | --- | --- |
| Trên khai báo tham số | `ElementType.PARAMETER` | `Parameter.getAnnotation`, `Parameter.getAnnotationsByType` |
| Trên kiểu được dùng làm tham số | `ElementType.TYPE_USE` | `Parameter.getAnnotatedType()` rồi gọi API annotation trên `AnnotatedType` |
| Trên tham số có nested generic/type argument | `ElementType.TYPE_USE` ở vị trí type argument | Dùng các subtype `AnnotatedParameterizedType`, `AnnotatedArrayType`… để đi sâu theo cấu trúc kiểu |

Ví dụ với generic:

```java
void names(java.util.List<@CleanType String> values) {}
```

`@CleanType` ở đây gắn trên type argument `String` của `List<String>`, không phải `Parameter` như một declaration annotation. Đọc nested annotation loại này có thể cần:

```java
AnnotatedType type = p.getAnnotatedType();
if (type instanceof AnnotatedParameterizedType apt) {
    AnnotatedType argumentType = apt.getAnnotatedActualTypeArguments()[0];
    boolean marked = argumentType.isAnnotationPresent(CleanType.class);
}
```

Snippet giả định `p` là `Parameter` của `values` và đã import `AnnotatedType`, `AnnotatedParameterizedType`; đây là **mã minh họa ngữ cảnh**, không phải file độc lập.

Một annotation type cũng có thể khai báo cả hai target `{PARAMETER, TYPE_USE}`. Khi đó cần cẩn trọng với **vị trí annotation và ngữ nghĩa áp dụng theo JLS**, không dùng một truy vấn đơn làm đại diện cho mọi trường hợp.

## 9. Đọc annotation repeatable trên parameter

Java cho phép một annotation lặp nhiều lần ở cùng một parameter khi được khai báo bằng `@Repeatable` với container hợp lệ.

Ví dụ độc lập trong file **`RepeatableParameterDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Tags {
    Tag[] value();
}

class Handler {
    public void handle(@Tag("required") @Tag("visible") String input) {}
}

public class RepeatableParameterDemo {
    public static void main(String[] args) throws Exception {
        Method method = Handler.class.getDeclaredMethod("handle", String.class);
        Parameter parameter = method.getParameters()[0];

        Tag[] tags = parameter.getAnnotationsByType(Tag.class);
        System.out.println(tags.length);
        for (Tag tag : tags) {
            System.out.println(tag.value());
        }

        System.out.println(parameter.getAnnotation(Tag.class));
        System.out.println(parameter.getAnnotation(Tags.class).value().length);
    }
}
```

Chạy:

```bash
javac --release 17 RepeatableParameterDemo.java
java RepeatableParameterDemo
```

Stdout:

```text
2
required
visible
null
2
```

**Điểm đáng chú ý:** `getAnnotationsByType(Tag.class)` **mở container hợp lệ** và trả hai `Tag`. Truy vấn `getAnnotation(Tag.class)` là dạng lấy một annotation trực tiếp; trong tình huống lặp này nó trả `null` vì bytecode thể hiện container `Tags`. Có thể đọc container bằng `getAnnotation(Tags.class)` và lấy `value().length` bằng `2`.

Khi thiết kế hệ thống xử lý nhiều metadata cùng loại trên một tham số, ưu tiên `getAnnotationsByType`. Không cần tự phân tích mảng annotation của container nếu API này đáp ứng yêu cầu.

Ví dụ đã được biên dịch và chạy với `javac --release 17`; output được đối chiếu trực tiếp.

## 10. Annotation trên Constructor Parameter

`java.lang.reflect.Constructor` và `Method` cùng kế thừa `Executable`. Vì vậy cả hai cung cấp `getParameters()` và `getParameterAnnotations()`.

Ví dụ:

```java
class Ticket {
    Ticket(@Bind("code") String code, @Bind("quantity") int quantity) {
    }
}
```

Để đọc:

```java
Constructor<Ticket> ctor =
        Ticket.class.getDeclaredConstructor(String.class, int.class);

for (Parameter parameter : ctor.getParameters()) {
    Bind bind = parameter.getAnnotation(Bind.class);
    System.out.println(bind == null ? "(none)" : bind.value());
}
```

Đoạn đọc trên cần `import java.lang.reflect.Constructor;` và `import java.lang.reflect.Parameter;`; dùng annotation `Bind` đã khai báo ở mục 4.

Stdout dự kiến:

```text
code
quantity
```

**Không cần tạo đối tượng `Ticket`** để đọc annotation trên constructor parameter. Reflection đang xem metadata khai báo trên constructor.

Đối với non-static inner class, enum constructor hoặc constructor mà compiler thêm synthetic/mandated parameters, danh sách parameter phản ánh biểu diễn JVM và có thể phức tạp hơn source bạn viết. Khi xây logic tổng quát để ánh xạ tham số, dùng thông tin `isSynthetic()`, `isImplicit()`, `getDeclaringExecutable()` khi thích hợp và kiểm tra compiler/version thực tế thay vì áp đặt mọi constructor đều là các tham số explicit trong source.

## 11. Annotation có tự được kế thừa ở method parameter không?

Không. Đừng suy diễn rằng `@Inherited` áp dụng cho parameter annotation của method được override.

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Key {}

class Base {
    void check(@Key String value) {}
}

class Derived extends Base {
    @Override
    void check(String value) {}
}
```

Nếu lấy `Method` khai báo trực tiếp bởi `Derived` và xem `getParameters()[0].isAnnotationPresent(Key.class)`, kết quả là `false`. Annotation ở parameter của phương thức `Base.check` không tự được sao chép sang parameter của `Derived.check`.

`@Inherited` (nếu khai báo trên annotation type) có phạm vi quy tắc riêng đối với một số annotation trên **class**, không phải “truyền” annotation từ parameter của phương thức bị ghi đè xuống phương thức mới.

Một framework có thể **chủ động tra class/interface cha và gộp metadata theo quy tắc riêng**, nhưng đó là logic framework, **không phải hành vi mặc định của `Parameter.getAnnotation`**.

## 12. Khi nào Reflection trả null hoặc mảng rỗng?

Những lỗi thực tế thường gặp:

### 12.1. Retention không phải RUNTIME

```java
@Target(ElementType.PARAMETER)
@interface SourceHint {}
```

Không khai báo `@Retention` nghĩa là `CLASS`. Annotation có thể có trong class file nhưng không được `Parameter.getAnnotation(SourceHint.class)` trả về. Sửa bằng cách khai báo `@Retention(RetentionPolicy.RUNTIME)` nếu cần đọc qua Reflection.

### 12.2. Đọc nhầm method hoặc overload

`getDeclaredMethod("send", String.class)` không giống `getDeclaredMethod("send", int.class)`. Cả hai có thể hợp lệ nếu tồn tại overload, nhưng annotation được gắn trên **một declaration cụ thể**. Cần đối chiếu chữ ký và kiểu tham số chính xác.

### 12.3. Nhầm target declaration với target type-use

Nếu annotation chỉ có `TYPE_USE`, gọi `parameter.getAnnotation(...)` sẽ không đọc được vị trí type-use. Dùng `getAnnotatedType` và truy cập đúng cấu trúc kiểu.

### 12.4. Dùng API đơn lẻ cho repeatable annotation

Nếu nhiều annotation cùng loại được chứa trong container, `getAnnotation(Repeated.class)` có thể là `null` dù `getAnnotationsByType(Repeated.class)` có phần tử. Dùng API theo loại khi cần một tập các annotation lặp.

### 12.5. Ngộ nhận -parameters điều khiển annotation

Không có `-parameters` khiến tên tham số có thể không sẵn, **nhưng không có nghĩa annotation `RUNTIME` không được lưu**. Hãy tách lỗi thiếu tên parameter khỏi lỗi annotation không hiện ra.

### 12.6. Phương thức có metadata tại superclass nhưng code lấy subclass

Method parameter annotation **không tự thừa kế** khi override. Cần tìm đúng `Method` và, nếu đặc tả framework yêu cầu, chủ động định nghĩa cách tra cứu các phương thức liên quan.

## 13. Một số lưu ý khi xây mapper/validator dựa trên annotation

Ví dụ ứng dụng: bạn định tự xây một binder đọc `@Bind("ticket")` để map một request vào tham số method. Trước khi thực hiện:

1. **Phân biệt metadata và dữ liệu:** `@Bind("ticket")` chỉ khai báo tên mapping. Giá trị `ticket` đến từ request riêng biệt, phải được parse và kiểm tra.
2. **Cẩn trọng với `null`:** một parameter có thể không có `@Bind`; ứng dụng cần chính sách bỏ qua, lỗi cấu hình hoặc fallback minh bạch.
3. **Không tin đầu vào chỉ vì có annotation:** metadata không tự thực hiện validate. Quy tắc xác thực, phân quyền và chuyển kiểu cần code cụ thể.
4. **Xác định phạm vi được phép Reflection:** `getDeclaredMethod` có thể tìm cả non-public method. Việc tìm thấy metadata không đồng nghĩa được quyền gọi method đó trong mọi module/môi trường.
5. **Tính đến overload/generics:** lấy method qua chữ ký chính xác; Reflection trả kiểu sau erasure ở `getType()` và thông tin generic qua `getParameterizedType()`.
6. **Tránh phụ thuộc tên biến Java nếu build không bật `-parameters`:** dùng giá trị annotation hoặc hợp đồng mapping khác rõ ràng.
7. **Xử lý varargs:** Java Reflection coi tham số `String...` có kiểu `String[]`; code binder cần chủ động chuyển input sang kiểu mảng thích hợp.

Đối với Spring/Jakarta hoặc các framework khác, có thể có thêm annotation đặc thù và thuật toán tổng hợp metadata. Những ví dụ bài này sử dụng **Java core Reflection**, không dựa vào framework.

## 14. Bài tập tự kiểm tra

### Bài 1 — Nhận diện vị trí

Đoạn sau có bao nhiêu parameter declaration annotations `@Field`?

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Field {
    String value();
}

class Api {
    void save(@Field("id") String id, int version, @Field("active") boolean active) {}
}
```

**Gợi ý:** `save` có ba `Parameter`. Tham số 0 và 2 có `@Field`; tham số 1 không có. Nếu duyệt `getParameters()` và gọi `getAnnotation(Field.class)`, cần kiểm tra `null` ở index 1.

### Bài 2 — Reflection và tên tham số

Nếu biên dịch không có `-parameters`, tại sao `Parameter.getName()` có thể là `arg0` nhưng `parameter.getAnnotation(Field.class).value()` vẫn trả `"id"`?

**Đáp án:** metadata lưu tên tham số và metadata annotation là hai thứ riêng. Retention `RUNTIME` quyết định sự sẵn có của annotation qua Reflection; `-parameters` quyết định lưu tên khai báo để Reflection truy cập.

### Bài 3 — Method hay constructor?

Chọn API phù hợp để đọc annotation trên parameter của `new Ticket("A", 2)`. Bạn sẽ gọi `getDeclaredMethod` hay `getDeclaredConstructor`?

**Đáp án:** lấy `Constructor` bằng `Ticket.class.getDeclaredConstructor(String.class, int.class)`, sau đó dùng `getParameters()` giống `Method`.

### Bài 4 — TYPE_USE khác PARAMETER

Với:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Trusted {}

class Api {
    void accept(@Trusted String value) {}
}
```

Tại sao `parameter.isAnnotationPresent(Trusted.class)` không trả `true` nhưng `parameter.getAnnotatedType().isAnnotationPresent(Trusted.class)` có thể trả `true`?

**Đáp án:** annotation này áp dụng lên kiểu `String` được dùng trong declaration, không phải annotation khai báo trên parameter. Phải đọc bằng `AnnotatedType`.

### Bài 5 — Annotation lặp

Với một tham số có `@Tag("required") @Tag("visible")` theo khai báo ở mục 9, nên dùng `getAnnotation(Tag.class)` hay `getAnnotationsByType(Tag.class)` nếu cần **toàn bộ** tag?

**Đáp án:** `getAnnotationsByType(Tag.class)`, vì nó xử lý đúng repeated annotation container và trả mảng các `Tag`.

### Bài 6 — Thừa kế method

`Base.check(@Key String value)` được override thành `Derived.check(String value)`. Nếu nhìn vào `Parameter` của method override ở `Derived`, có tự thấy `@Key` không?

**Đáp án:** không. Metadata declaration của parameter thuộc **phương thức cụ thể**, không tự kế thừa từ phương thức bị ghi đè.

## 15. Checklist khi đọc annotation trên tham số

Trước khi debug `null` hoặc một mảng annotation rỗng, hãy kiểm tra:

1. Annotation type có `@Target(ElementType.PARAMETER)` nếu định dùng cho **parameter declaration** chưa?
2. Có `@Retention(RetentionPolicy.RUNTIME)` để Java Reflection đọc khi chạy chưa?
3. Bạn có lấy đúng `Method` hoặc `Constructor` bằng chữ ký và kiểu tham số không?
4. Bạn có duyệt đúng phần tử của `Parameter[]` (vị trí 0, 1, 2…) không?
5. Bạn đã kiểm tra `null` trước khi gọi các phần tử như `annotation.value()` chưa?
6. Nếu annotation lặp được, bạn có sử dụng `getAnnotationsByType` thay vì chỉ `getAnnotation` không?
7. Annotation nằm trên **parameter declaration** hay trên **type-use**, và bạn đã chọn đúng `Parameter` hoặc `AnnotatedType` chưa?
8. Bạn có nhầm lỗi tên parameter (`-parameters`) với khả năng đọc annotation không?
9. Nếu phương thức được override hoặc constructor có tham số ngầm, bạn đã xem đúng declaration và metadata JVM chưa?
10. Bạn đã xác minh bằng một chương trình Java nhỏ có stdout rõ ràng trước khi gắn vào framework chưa?

**Kết luận:** `Method.getParameters()` và `Constructor.getParameters()` cho phép truy cập từng `Parameter`; từ đó có thể đọc runtime-visible declaration annotations bằng `getAnnotation` hoặc `getAnnotationsByType`. `Method.getParameterAnnotations()` là lựa chọn ma trận theo vị trí. Với type-use annotations, dùng `getAnnotatedType()`. Retention, target, chữ ký phương thức và cách đọc repeatable annotation là bốn yếu tố quyết định liệu metadata được trả về có đúng như bạn kỳ vọng hay không.