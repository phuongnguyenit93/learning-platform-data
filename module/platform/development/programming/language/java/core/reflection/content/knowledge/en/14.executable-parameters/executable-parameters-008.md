# Annotation trên từng tham số của Method và Constructor trong Java Reflection

Khi dùng Java Reflection để kiểm tra **tham số của một phương thức hoặc constructor**, ta không chỉ biết số lượng, tên và kiểu dữ liệu; ta còn có thể đọc **annotation được gắn trên từng tham số**. Điều này rất quan trọng trong những framework dùng annotation để khai báo cách lấy dữ liệu đầu vào, kiểm tra hợp lệ, dependency injection, ánh xạ HTTP/JSON hoặc cấu hình cơ chế tạo object.

Ví dụ:

```java
public void createUser(@Named("username") String name,
                       @Positive int age) {
    // Logic xử lý.
}
```

Đây là **đoạn minh họa cú pháp**, trong đó `@Named` và `@Positive` là các annotation do ứng dụng hoặc thư viện định nghĩa, không phải annotation chuẩn sẵn có trong Java SE. Hai annotation tương ứng với **hai tham số khác nhau**. Runtime có thể đọc metadata này nếu kiểu annotation được định nghĩa với `@Retention(RetentionPolicy.RUNTIME)`.

Bài học tập trung vào cách Reflection xác định annotation **của từng parameter** trên `java.lang.reflect.Method` và `java.lang.reflect.Constructor`, cách dùng `Executable.getParameterAnnotations()` và `Parameter`, sự khác nhau giữa annotation trên **khai báo tham số** và **kiểu sử dụng (type-use)**, cùng các vấn đề `RUNTIME` retention, `-parameters`, repeatable annotation và synthetic/implicit parameters.

## 1. Các lớp Reflection liên quan

Một phương thức hoặc constructor là một **executable**. Java có lớp nền `java.lang.reflect.Executable`; hai lớp triển khai quan trọng là:

- `Method`: metadata của một phương thức.
- `Constructor<T>`: metadata của constructor.
- `Parameter`: metadata của **một tham số** trong một `Method` hoặc `Constructor`.
- `Annotation`: interface nền `java.lang.annotation.Annotation`, đại diện cho một annotation runtime.
- `AnnotatedType`: metadata annotation gắn vào **việc sử dụng kiểu** của một tham số, không đồng nhất với annotation gắn vào khai báo tham số.

Các API thường dùng:

| API | Trả về | Dùng khi nào |
|---|---|---|
| `executable.getParameterCount()` | `int` | Biết số tham số trong metadata của executable |
| `executable.getParameters()` | `Parameter[]` | Cần xử lý từng tham số cùng tên, kiểu và annotation |
| `executable.getParameterAnnotations()` | `Annotation[][]` | Cần danh sách annotation **theo chỉ số tham số** |
| `parameter.getAnnotations()` | `Annotation[]` | Đọc các annotation runtime được gắn trực tiếp lên một parameter |
| `parameter.getAnnotation(MyAnnotation.class)` | `MyAnnotation` hoặc `null` | Tìm một annotation cụ thể trên parameter |
| `parameter.isAnnotationPresent(MyAnnotation.class)` | `boolean` | Kiểm tra nhanh sự tồn tại của annotation |
| `parameter.getAnnotationsByType(MyAnnotation.class)` | `MyAnnotation[]` | Lấy cả annotation **repeatable** cùng loại |
| `parameter.getType()` | `Class<?>` | Xem kiểu khai báo sau type erasure |
| `parameter.getParameterizedType()` | `Type` | Xem thông tin generic type của parameter |
| `executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` | Đọc annotation `TYPE_USE` trên kiểu của từng parameter |

`Method` và `Constructor` có chung nhiều phương thức kể trên vì đều là `Executable`. Do đó, cách đọc annotation của tham số thường có thể tái sử dụng cho cả hai.

## 2. Khai báo annotation dành cho tham số

Annotation là một kiểu được khai báo bằng `@interface`. Hai meta-annotation quan trọng nhất trong tình huống này là:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface Named {
    String value();
}
```

Đoạn code này có thể lưu thành **`Named.java`** và biên dịch độc lập nếu có JDK; đây là annotation mẫu, không phải chương trình có `main`.

- `@Target(ElementType.PARAMETER)` cho phép dùng `@Named` trên **khai báo tham số** của method, constructor (và các vị trí parameter phù hợp khác).
- `@Retention(RetentionPolicy.RUNTIME)` làm cho annotation được lưu lại và có thể được Reflection đọc lúc chạy.
- `String value();` là một **phần tử của annotation**. Nếu annotation được khai báo `@Named("id")`, gọi `named.value()` nhận chuỗi `"id"`.
- Nếu annotation không có `@Retention`, mặc định là **`RetentionPolicy.CLASS`**; class file có thể mang metadata nhưng core Reflection **không cung cấp annotation đó ở runtime**.

Ví dụ:

```java
public User(@Named("id") String id) {
    // Constructor của User.
}
```

Annotation trên parameter có thể đóng vai trò hướng dẫn framework đọc dữ liệu đầu vào. Tuy nhiên, Java **không tự động validate hoặc bind dữ liệu** chỉ vì parameter có `@Named`: framework/ứng dụng phải chủ động đọc và xử lý annotation.

### Ba mức retention

| Retention | Được ghi vào class file? | Core Reflection đọc annotation lúc runtime? |
|---|---|---|
| `SOURCE` | Không; compiler thường bỏ sau khi xử lý source | Không |
| `CLASS` | Có | Không, theo cơ chế runtime annotation Reflection chuẩn |
| `RUNTIME` | Có | Có, khi loại annotation và metadata có thể truy cập |

Nếu `parameter.getAnnotation(Named.class)` trả `null`, **chưa chắc** annotation đó không từng xuất hiện trong source: nó có thể có retention không phù hợp, nằm trên type-use chứ không phải parameter declaration, bị đặt vào parameter khác hoặc không tồn tại trong bytecode runtime.

## 3. `getParameterAnnotations()`: mảng hai chiều căn theo tham số

Ví dụ có method sau:

```java
public void submit(@Named("user") String username,
                   @Positive int count,
                   String note) {
}
```

Giả định `@Named` và `@Positive` đều là annotation runtime, có target `PARAMETER`. Khi tra cứu method:

```java
Method method = Example.class.getMethod(
        "submit", String.class, int.class, String.class);

Annotation[][] annotations = method.getParameterAnnotations();
```

Các đoạn trên là **minh họa**, `Example` và `Positive` phải được định nghĩa riêng, và code có import `java.lang.reflect.Method`, `java.lang.annotation.Annotation`. Mảng được tổ chức theo cấu trúc:

```text
annotations
  [0] -> annotation của username: @Named("user")
  [1] -> annotation của count:    @Positive
  [2] -> annotation của note:     (mảng rỗng)
```

Quy tắc quan trọng:

1. **Chiều ngoài** có một phần tử cho mỗi tham số theo thứ tự khai báo/chữ ký của executable. `annotations.length` tương ứng với `method.getParameterCount()`.
2. **Chiều trong** chứa annotation của **tham số ở chỉ số đó**. Một parameter có thể có không, một hoặc nhiều annotation.
3. Tham số không có annotation runtime được biểu diễn bằng **mảng annotation rỗng**, không phải bỏ hẳn phần tử ở chiều ngoài.
4. Với executable không có tham số, mảng ngoài có độ dài **`0`**.
5. Không dựa vào **thứ tự các annotation khác loại** trong mảng ở cùng một parameter để làm logic nghiệp vụ; hãy tìm theo annotation type. Đặc biệt, repeatable annotations có thể được lưu qua **container annotation**.

Mẫu duyệt đáng tin cậy:

```java
Annotation[][] matrix = method.getParameterAnnotations();
for (int index = 0; index < matrix.length; index++) {
    System.out.println("Parameter " + index
            + " has " + matrix[index].length + " runtime annotations");
}
```

Đây là đoạn minh họa đặt trong code đã có `method` cùng import `Annotation`. Nếu muốn đọc metadata ngoài annotation, ta lấy `Parameter[]` và ghép bằng **cùng chỉ số**.

## 4. `Parameter`: truy vấn từng tham số theo loại annotation

Thay vì tự duyệt mảng hai chiều, `Parameter` cung cấp API gần với việc xử lý từng parameter hơn:

```java
Parameter[] parameters = method.getParameters();

for (Parameter parameter : parameters) {
    Named named = parameter.getAnnotation(Named.class);
    if (named != null) {
        System.out.println(named.value());
    }
}
```

Đây là ví dụ dùng kiểu `Named` tự định nghĩa và `Method method` đã có. Điểm mạnh là ta xử lý tên, kiểu và annotation của **một tham số** trong cùng một đối tượng.

- `getAnnotation(T.class)` trả một annotation phù hợp hoặc `null`.
- `isAnnotationPresent(T.class)` cho biết có annotation cùng loại theo API kiểm tra không.
- `getAnnotations()` trả các annotation runtime có trên parameter; với repeatable annotations, có thể thấy container thay vì từng annotation lặp.
- `getDeclaredAnnotations()` trên `Parameter` đọc annotation được khai báo trực tiếp. Parameter **không có cơ chế kế thừa annotation như lớp**; vì vậy không nên thiết kế logic dựa vào annotation parameter của superclass tự động truyền xuống.
- `getAnnotationsByType(T.class)` là cách thích hợp khi `T` có thể được đánh dấu `@Repeatable`.

Một annotation như `@Named("id")` là metadata runtime được đọc qua interface `Named`. Gọi `named.value()` để nhận giá trị annotation; không nhầm với việc **lấy giá trị của argument** được truyền vào lúc method thực sự chạy. Reflection metadata mô tả khai báo, không ghi lại argument từ một invocation cụ thể.

## 5. Ví dụ Java 17+ hoàn chỉnh: Method, Constructor, RUNTIME, TYPE_USE, Repeatable

Tạo một tệp **`ParameterAnnotationDemo.java`** với nội dung sau. Mọi annotation và class thử nghiệm đều được đặt trong một public outer class, nên không cần thư viện ngoài Java SE:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

public class ParameterAnnotationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Label {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @Repeatable(Tags.class)
    public @interface Tag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Tags {
        Tag[] value();
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.PARAMETER)
    public @interface CompileOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface NonNullType {}

    public static class Service {
        public Service(@Label("id") String id,
                       @Tag("create") @Tag("audit") int limit) {}

        public void send(@Label("to") @Tag("email") String recipient,
                         @CompileOnly String token,
                         @NonNullType String body) {}

        public void empty() {}
    }

    public static void main(String[] args) throws Exception {
        Method method = Service.class.getMethod(
                "send", String.class, String.class, String.class);
        Annotation[][] matrix = method.getParameterAnnotations();

        System.out.println("method parameters: "
                + method.getParameterCount());
        for (int i = 0; i < matrix.length; i++) {
            System.out.println("send[" + i + "] annotation count: "
                    + matrix[i].length);
        }

        Parameter[] params = method.getParameters();
        System.out.println("label: "
                + params[0].getAnnotation(Label.class).value());
        System.out.println("tag: "
                + params[0].getAnnotationsByType(Tag.class)[0].value());
        System.out.println("runtime CLASS annotation present: "
                + params[1].isAnnotationPresent(CompileOnly.class));

        System.out.println("type-use annotation on type: "
                + method.getAnnotatedParameterTypes()[2]
                        .isAnnotationPresent(NonNullType.class));
        System.out.println("type-use annotation on declaration: "
                + params[2].isAnnotationPresent(NonNullType.class));

        System.out.println("name present: "
                + params[0].isNamePresent());
        System.out.println("name: " + params[0].getName());

        Constructor<Service> constructor =
                Service.class.getConstructor(String.class, int.class);
        Parameter[] cp = constructor.getParameters();

        System.out.println("constructor label: "
                + cp[0].getAnnotation(Label.class).value());
        Tag[] tags = cp[1].getAnnotationsByType(Tag.class);
        System.out.println("constructor repeatable count: " + tags.length);
        for (Tag tag : tags) {
            System.out.println("constructor tag: " + tag.value());
        }
        System.out.println("constructor raw annotation count: "
                + constructor.getParameterAnnotations()[1].length);
        System.out.println("empty annotation slots: "
                + Service.class.getMethod("empty")
                        .getParameterAnnotations().length);
    }
}
```

Chạy với JDK 17+ từ thư mục chứa tệp:

```bash
javac -parameters ParameterAnnotationDemo.java
java ParameterAnnotationDemo
```

**Stdout đã được đối chiếu khi biên dịch và chạy:**

```text
method parameters: 3
send[0] annotation count: 2
send[1] annotation count: 0
send[2] annotation count: 0
label: to
tag: email
runtime CLASS annotation present: false
type-use annotation on type: true
type-use annotation on declaration: false
name present: true
name: recipient
constructor label: id
constructor repeatable count: 2
constructor tag: create
constructor tag: audit
constructor raw annotation count: 1
empty annotation slots: 0
```

### Phân tích từng nhóm output

1. `send` có ba tham số. Ở `send[0]`, `@Label("to")` và `@Tag("email")` đều có `RUNTIME` retention và target `PARAMETER`, vì vậy `getParameterAnnotations()[0]` có **2 annotation**.
2. `send[1]` được đánh dấu `@CompileOnly`, nhưng annotation có retention `CLASS`, nên **không hiển thị bằng core Reflection**; mảng annotation runtime của tham số này rỗng.
3. `send[2]` có `@NonNullType` với target `TYPE_USE`. Nó được lưu trên **kiểu `String` được sử dụng ở tham số**, không được trả như parameter-declaration annotation. `getAnnotatedParameterTypes()[2]` nhìn thấy nó, trong khi `Parameter.isAnnotationPresent(NonNullType.class)` trả `false`.
4. `Label.value()` trả `to`, và `getAnnotationsByType(Tag.class)` trả annotation `Tag` để đọc `email`.
5. Chạy `javac -parameters` giữ **tên tham số ở mức Reflection**: `isNamePresent() == true`, `getName()` trả `recipient`. Nếu biên dịch **không có `-parameters`** trong trường hợp Java source thông thường này, `isNamePresent()` có thể là `false`, tên do Reflection suy ra có thể là `arg0`. Việc đọc các annotation runtime **không cần** `-parameters`.
6. Constructor `Service(String,int)` cũng có `Parameter[]`. Tham số đầu tiên chứa `@Label("id")`. Tham số thứ hai có hai `@Tag` lặp; `getAnnotationsByType(Tag.class)` trả **2** phần tử, còn `getParameterAnnotations()[1]` thông thường thấy **1 container annotation `@Tags`**.
7. Method `empty()` không tham số nên `getParameterAnnotations()` trả mảng ngoài độ dài `0`.

**Quan trọng:** ví dụ chỉ **đọc metadata**. Không có chỗ nào Java tự kích hoạt validate `@Label`, `@Tag` hoặc `@NonNullType`. Annotation type-use ở đây chỉ là nhãn tùy chỉnh; nó **không tự ngăn** truyền `null` vào tham số.

## 6. Annotation trên parameter khác annotation trên type-use

Java hỗ trợ hai kiểu vị trí có thể nhìn gần giống nhau trong source:

```java
void process(@Label("input") String value) {
}

void processType(@NonNullType String value) {
}
```

Cả hai dòng là đoạn minh họa được khai báo trong một class thích hợp, với `@Label` có target `PARAMETER`, `@NonNullType` có target `TYPE_USE`.

- `@Label` là **annotation của khai báo tham số**. Dùng `Parameter.getAnnotation(Label.class)` hoặc `Executable.getParameterAnnotations()`.
- `@NonNullType` là **annotation của việc sử dụng kiểu `String`**. Dùng `Executable.getAnnotatedParameterTypes()` rồi đọc `AnnotatedType`.
- Nếu một annotation type được phép target cả `PARAMETER` lẫn `TYPE_USE`, compiler có thể ghi metadata cho cả các ngữ cảnh phù hợp; không nên phỏng đoán bằng cách nhìn vị trí chữ `@` trong source. Hãy đọc `@Target` và kiểm tra API phù hợp.

`getAnnotatedParameterTypes()` trả mảng `AnnotatedType[]`, tương ứng theo thứ tự với các parameter types. Điều này hữu ích khi mô tả các kiểu có annotation gắn sâu:

```java
void store(java.util.List<@NonNullType String> names) {
}
```

Đây là **đoạn minh họa** về annotation trên **generic type argument**, không phải annotation của parameter declaration. Để đọc `@NonNullType` ở `String` bên trong `List`, có thể xem `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` sau khi xác định `AnnotatedType` bên ngoài là `AnnotatedParameterizedType`.

Phân biệt với annotation chỉ có target `PARAMETER`: các API `Parameter.getAnnotations()` không tự “đào sâu” vào annotation trên generic type arguments, các lớp phần tử của mảng hoặc annotated wildcard.

## 7. Repeatable annotation: tại sao số đếm có thể khác?

Giả sử annotation được đánh dấu:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@Repeatable(Tags.class)
public @interface Tag {
    String value();
}
```

và khai báo container tương ứng:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface Tags {
    Tag[] value();
}
```

Hai đoạn là khai báo minh họa; cần đặt trong file/class phù hợp và import `java.lang.annotation.*`. Khi sử dụng:

```java
public void authorize(@Tag("reader") @Tag("writer") String user) {
}
```

Java compiler có thể lưu hai `@Tag` thông qua container `@Tags`. Vì thế:

- `parameter.getAnnotationsByType(Tag.class)` trả **hai `Tag`**, phù hợp cho việc xử lý annotation repeatable.
- `parameter.getAnnotation(Tag.class)` **không nên** được giả định sẽ trả một trong hai `Tag` khi chúng được lưu dưới dạng container; có thể trả `null`.
- `parameter.getAnnotations()` và `getParameterAnnotations()` có thể phản ánh **container annotation** `Tags` thay vì hai `Tag` riêng lẻ. Số phần tử thô trong mảng khác với số annotation `Tag` thực tế về mặt lặp.

Ví dụ hoàn chỉnh ở mục 5 xác nhận `getAnnotationsByType(Tag.class).length == 2` trong khi số annotation thô trên cùng constructor parameter là `1`. Đừng dùng `getAnnotations().length` để khẳng định “chỉ có một tag” mà không hiểu cấu trúc repeatable annotation.

## 8. Tên tham số và annotation là hai loại metadata độc lập

Hai API thường xuất hiện cạnh nhau:

```java
Parameter parameter = method.getParameters()[0];
String name = parameter.getName();
Annotation[] annotations = parameter.getAnnotations();
```

Đây là đoạn minh họa trong code có `Method method` tương ứng và import `Parameter`, `Annotation`. Nhưng có khác biệt quan trọng:

- Tên tham số thông thường được compiler giữ lại cho Reflection nhờ tùy chọn **`javac -parameters`**, để `Parameter.isNamePresent()` trả `true` và `getName()` phản ánh tên đã biên dịch.
- Annotation muốn có mặt trong core Reflection cần **`@Retention(RUNTIME)`** và đúng target; `-parameters` không làm cho annotation retention `CLASS` xuất hiện ở runtime.
- Một framework dùng annotation như `@Named("userId")` có thể hoạt động dù method parameter ở runtime chỉ có tên `arg0`, vì nó đọc phần tử annotation `value()`, không phụ thuộc vào `getName()`.
- Ngược lại, code sử dụng tên tham số để bind mà không kiểm tra `isNamePresent()` có thể xử lý sai nếu class được build không có `-parameters`.

Khuyến nghị: khi cần bind theo tên, ưu tiên annotation tường minh nếu thiết kế API yêu cầu tính ổn định trước thay đổi compiler flags; nếu dùng tên thực của parameter, hãy quy định và kiểm tra rõ `-parameters` trong quy trình build.

## 9. Method, Constructor và các tham số do compiler tạo

Thông thường, mảng `Parameter[]` và annotation matrix được căn theo thứ tự của parameter types trong executable:

```java
Executable executable = /* Method hoặc Constructor được truyền vào */;
Parameter[] parameters = executable.getParameters();
Annotation[][] annotations = executable.getParameterAnnotations();

for (int i = 0; i < parameters.length; i++) {
    System.out.println(i + ": " + parameters[i].getType().getTypeName()
            + ", annotations=" + annotations[i].length);
}
```

Đây là đoạn minh họa, không phải một chương trình độc lập. Nếu không có metadata parameter names, việc duyệt theo **index** vẫn hoạt động.

Tuy nhiên, một số constructor đặc biệt có **parameter bổ sung ở bytecode**:

- Constructor của một **non-static inner class** có thể nhận tham chiếu tới instance của enclosing class.
- Constructor của **enum** có tham số nội bộ do compiler/JVM sử dụng, ngoài những tham số hiển thị trong khai báo source.
- Compiler có thể sinh tham số **synthetic** hoặc đánh dấu tham số **implicit/mandated**, tùy construct và compiler.

Vì vậy, khi viết framework tổng quát, không nên suy rằng parameter thứ 0 trong mọi constructor luôn tương ứng với tham số đầu tiên do lập trình viên trực tiếp viết. Có thể kiểm tra `Parameter.isSynthetic()`, `Parameter.isImplicit()` và metadata compiler khi cần; đồng thời đối chiếu `Executable.getParameterTypes()`, `getParameters()` và annotation array theo **cùng executable**.

Trong trường hợp constructor do compiler sinh đặc biệt, metadata về annotation/parameter đôi khi cần xử lý thận trọng theo bytecode thực tế và phiên bản compiler. Đừng dùng tên `arg0` hoặc số parameter giả định thay cho việc kiểm tra reflection metadata.

### Overriding không tự kế thừa annotation của tham số

Nếu interface hoặc superclass khai báo một method với parameter annotation, method override ở subclass **không tự động nhận** annotation của parameter cũ. `@Inherited` của Java chỉ áp dụng cho một số **class-level annotations**, không truyền parameter annotations qua override.

Ví dụ:

```java
interface Handler {
    void handle(@Label("command") String command);
}

class HandlerImpl implements Handler {
    @Override
    public void handle(String command) {
    }
}
```

Đây là đoạn minh họa với `Label` runtime annotation thích hợp. Nếu tra cứu parameter annotations trên `HandlerImpl.handle(String)`, không được mặc định nhìn thấy `@Label("command")` của `Handler.handle(String)`. Một framework muốn kế thừa quy ước annotation từ interface phải **tự xác định method tương ứng và đọc metadata từ interface**.

Đây là điểm khác biệt quan trọng giữa “method cùng chữ ký ở nhiều cấp type” và “annotation thực sự gắn vào parameter của Method cụ thể được trả về từ Reflection”.

## 10. Tra cứu đúng method/constructor trước khi đọc annotation

Trước khi lấy annotations, cần chọn đúng executable:

```java
Method m = Service.class.getMethod(
        "send", String.class, String.class, String.class);

Constructor<Service> c =
        Service.class.getConstructor(String.class, int.class);
```

Đây là hai lệnh minh họa trùng với class ví dụ ở mục 5. `getMethod(name, parameterTypes)` tra cứu public method theo tên + **chữ ký kiểu tham số**; `getConstructor(parameterTypes)` tra cứu constructor public. Nếu cần metadata của private executable, dùng `getDeclaredMethod` hoặc `getDeclaredConstructor`.

Lưu ý:

1. Annotation **không tham gia phân biệt overload**. Hai method không thể được overload chỉ vì annotation trên parameter khác nhau; điều quan trọng là tên method và dãy parameter types theo Java.
2. `int.class` và `Integer.class` là **hai kiểu chữ ký khác nhau**. Khi lookup, Java Reflection không tự chọn overload theo boxing của argument runtime.
3. Varargs parameter `String... names` xuất hiện trong reflection parameter types như kiểu **`String[]`**.
4. Generic parameter như `List<String>` thường có erased runtime type `List.class`; muốn metadata generic dùng `getGenericParameterTypes()` hoặc `Parameter.getParameterizedType()`.
5. Tìm được metadata executable không có nghĩa có thể **invoke** nó. Access checks, module encapsulation và tham số truyền vào vẫn có thể ảnh hưởng việc gọi. Đọc annotation thông thường không yêu cầu thực thi executable.

## 11. Ứng dụng thực tế: annotation-driven validation và binding

Giả sử một framework muốn đọc annotation `@Label` để biết tên trường JSON hoặc tên HTTP parameter:

```java
Method endpoint = Controller.class.getMethod(
        "handle", String.class, int.class);
Parameter[] params = endpoint.getParameters();

for (int i = 0; i < params.length; i++) {
    Label label = params[i].getAnnotation(Label.class);
    if (label == null) {
        continue;
    }
    String externalName = label.value();
    Class<?> targetType = params[i].getType();

    // Ánh xạ externalName -> dữ liệu đầu vào -> chuyển đổi kiểu targetType,
    // sau đó kiểm tra điều kiện nghiệp vụ trước khi Method.invoke.
}
```

Đây là **đoạn minh họa thiết kế**, giả định có `Controller` với public method phù hợp và annotation `Label`. Không phải chương trình chạy độc lập. Framework thực tế cần bổ sung xử lý kiểu, field missing/null, số lượng argument, security, validate và exception.

Quy trình hợp lý:

1. Tra cứu chính xác `Method` hoặc `Constructor`.
2. Lấy `Parameter[]` theo thứ tự executable.
3. Với mỗi parameter, lấy annotation có `RUNTIME` retention mà framework hiểu, hoặc type-use annotations khi đúng mục tiêu.
4. Đọc thành phần của annotation (`value()`, `required()`, ... nếu annotation đó định nghĩa) để xây dựng quy tắc bind/validate.
5. Chuyển dữ liệu ngoài thành kiểu Java phù hợp với `getType()`/`getParameterizedType()`.
6. Kiểm tra lỗi và quyền truy cập; cuối cùng mới gọi `Method.invoke` hoặc `Constructor.newInstance` nếu cần.

**Không có bước nào Java tự thực thi annotation giúp bạn.** Ví dụ `@Positive` do người học tự định nghĩa không tự ngăn một số âm được truyền vào method. Với Bean Validation như Jakarta Validation, các thư viện chuyên dụng cung cấp engine và quy tắc; core Reflection chỉ là một phần cơ chế khám phá metadata.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra hoặc hướng giải quyết |
|---|---|---|
| `parameter.getAnnotation(MyAnno.class)` là `null` | Annotation không có `RUNTIME` retention | Kiểm tra khai báo `@Retention(RUNTIME)`; build lại class |
| `getParameterAnnotations()[i]` rỗng nhưng source có annotation | Annotation là `TYPE_USE`, `CLASS`/`SOURCE` hoặc không đúng parameter được đọc | Dùng `getAnnotatedParameterTypes()` nếu là `TYPE_USE`; xem retention |
| `getAnnotations().length` bằng 1 dù source ghi hai annotation cùng loại | Repeatable annotations được lưu qua container | Dùng `getAnnotationsByType(Tag.class)` |
| `Parameter.getName()` là `arg0` | Không có metadata tên param runtime | Biên dịch với `javac -parameters`, kiểm tra `isNamePresent()` |
| `getMethod(...)` ném `NoSuchMethodException` | Tên, số lượng hoặc kiểu param lookup không đúng; method không public | Kiểm tra đúng overload và visibility; cân nhắc `getDeclaredMethod` |
| Annotation có ở interface nhưng không thấy trên override class | Parameter annotation không tự kế thừa qua override | Framework cần đọc annotation từ method ở interface/supertype |
| Duyệt annotations theo tên param rồi bị lệch | Tên param không đáng tin nếu không có `-parameters` hoặc có compiler-generated params | Ưu tiên chỉ số kết hợp `getParameters()` từ cùng executable |
| Code dùng `getAnnotation(...).value()` gây `NullPointerException` | Không có annotation runtime đúng loại | Kiểm tra khác `null` hoặc dùng `isAnnotationPresent` |
| Annotation được đọc nhưng không có validation nào chạy | Reflection chỉ đọc metadata; không cung cấp validation engine | Viết logic xử lý hoặc tích hợp framework chuyên dụng |
| Lỗi khi đọc phần tử của annotation runtime bất thường | Annotation type hoặc class metadata thay đổi, type không hiện diện, giá trị không phù hợp | Kiểm tra runtime classpath/module và compatibility; một số API có thể ném lỗi như `TypeNotPresentException`, `AnnotationTypeMismatchException` hoặc `IncompleteAnnotationException` |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Method có ba tham số nhưng chỉ tham số thứ hai gắn `@Label` runtime. `getParameterAnnotations()` có bao nhiêu phần tử chiều ngoài?

**Đáp án:** Ba phần tử. Parameter thứ nhất và thứ ba tương ứng mảng annotation rỗng; phần tử thứ hai chứa annotation.

**Câu 2.** Khai báo `@Target(PARAMETER)` nhưng không ghi `@Retention`. Reflection có chắc đọc được annotation này không?

**Đáp án:** Không. Retention mặc định là `CLASS`; core Reflection không hiển thị nó như runtime annotation. Muốn đọc bằng `Parameter.getAnnotation` cần `RetentionPolicy.RUNTIME`.

**Câu 3.** Tại sao `javac -parameters` không làm `@CompileOnly` trong ví dụ hiển thị?

**Đáp án:** `-parameters` lưu metadata **tên tham số**. `@CompileOnly` có retention `CLASS`, nên không được trả về trong runtime annotation APIs; đây là hai cơ chế khác nhau.

**Câu 4.** `@NonNullType` có target `TYPE_USE` được gắn trước `String body`. API nào phù hợp để đọc?

**Đáp án:** `method.getAnnotatedParameterTypes()[index]`, sau đó `AnnotatedType.getAnnotation(NonNullType.class)` hoặc `isAnnotationPresent`. Không mặc định nó là parameter-declaration annotation.

**Câu 5.** Một parameter có `@Tag("a") @Tag("b")`. Để lấy tất cả tag nên dùng gì?

**Đáp án:** `parameter.getAnnotationsByType(Tag.class)`, vì `Tag` là repeatable; đừng dùng `getAnnotation(Tag.class)` để mong lấy ngẫu nhiên một tag.

**Câu 6.** Interface khai báo parameter `@Label("id")`, còn class implement override method mà không ghi lại annotation. Class implement có tự nhận annotation đó khi gọi Reflection không?

**Đáp án:** Không. Parameter annotations không tự kế thừa khi method được override. Framework phải tìm method của interface và đọc metadata ở đó nếu muốn áp dụng quy tắc từ interface.

**Câu 7.** Constructor có thể tra cứu annotation parameter giống method không?

**Đáp án:** Có. `Method` và `Constructor` đều kế thừa `Executable`, nên có `getParameters()`, `getParameterAnnotations()`, `getAnnotatedParameterTypes()`; cần lưu ý implicit/synthetic parameters trong một số constructor đặc biệt.

## Tài liệu chuẩn để tra cứu

- Java SE API: `java.lang.reflect.Executable` — `getParameters`, `getParameterCount`, `getParameterAnnotations`, `getAnnotatedParameterTypes`.
- Java SE API: `java.lang.reflect.Parameter` — `getName`, `isNamePresent`, `getType`, `getParameterizedType`, `getAnnotationsByType`, `isSynthetic`, `isImplicit`.
- Java SE API: `java.lang.reflect.AnnotatedType`, `AnnotatedParameterizedType`.
- Java SE API: `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, `ElementType`, `Repeatable`.
- Java Language Specification: phần về annotation types, type annotations, method/constructor parameters; Java Virtual Machine Specification: runtime-visible parameter/type annotations.
- Công cụ `javac`: tùy chọn `-parameters` để lưu tên tham số được Reflection sử dụng.

**Ghi nhớ:** Annotation trên từng tham số được đọc qua **`Executable.getParameterAnnotations()`** hoặc **`Parameter.getAnnotation(s)`**, căn theo đúng parameter index. Chỉ annotation có **`RUNTIME` retention** mới hiện qua core Reflection; annotation `TYPE_USE` được đọc qua **`AnnotatedType`**; annotation lặp nên lấy bằng **`getAnnotationsByType`**. Tên tham số có cần `-parameters` hay không là vấn đề khác với việc giữ annotation, và việc có annotation **không tự chạy validation**.