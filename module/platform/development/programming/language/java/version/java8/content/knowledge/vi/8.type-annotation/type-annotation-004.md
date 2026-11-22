# Annotation trên kiểu trả về, tham số và `throws` trong Java

## 1. Hiểu đúng: annotation của khai báo và annotation của vị trí sử dụng kiểu

Java 8 mở rộng annotation để đặt metadata trên **nơi kiểu được sử dụng** (*type-use annotation*, thường gắn với JSR 308), không chỉ trên lớp, phương thức, field hoặc tham số như một **khai báo**. Khác biệt này đặc biệt đáng chú ý ở ba vị trí: **kiểu trả về**, **kiểu của tham số**, và **kiểu ngoại lệ trong mệnh đề `throws`**.

Ví dụ một method có thể mô tả ba vị trí kiểu riêng:

~~~java
// Mảnh mã minh họa, giả định @TypeMark có @Target(TYPE_USE):
public @TypeMark String read(
        @TypeMark String key
) throws @TypeMark java.io.IOException {
    return key;
}
~~~

Các annotation này nằm trên **kiểu** `String`, `String` và `IOException`, không mặc nhiên đồng nghĩa với “annotation của method”, “annotation của parameter declaration” hay “annotation dùng để xử lý ngoại lệ”.

Một khai báo annotation có thể giới hạn nơi sử dụng bằng `@Target`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface TypeMark {}
~~~

`ElementType.TYPE_USE` cho phép dùng `@TypeMark` trên các vị trí dùng kiểu, trong đó có return type, parameter type và exception type trong `throws`. Đây là tính năng đã có từ Java 8, vẫn được sử dụng trong Java hiện đại.

**Mục tiêu bài học:** đọc đúng vị trí annotation, thiết kế `@Target`/`@Retention` phù hợp, truy xuất chính xác metadata bằng reflection khi cần, đồng thời hiểu rõ annotation **không tự bảo đảm** null safety, kiểm chứng giá trị hay xử lý exception. Bài có các chương trình Java 17+ chạy độc lập; các đoạn minh họa thiếu ngữ cảnh sẽ được ghi rõ.

## 2. Ba nơi đặt type-use annotation trên chữ ký method

Giả sử định nghĩa:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Slot {
    String value();
}
~~~

Ví dụ chữ ký:

~~~java
// Mảnh mã minh họa, đặt trong class và import IOException:
public @Slot("return-type") String load(
        @Slot("parameter-type") String key
) throws @Slot("throws-type") java.io.IOException {
    return key;
}
~~~

| Vị trí | Cú pháp | Đối tượng được đánh dấu |
| --- | --- | --- |
| Kiểu trả về | `@Slot("return-type") String` | Lần sử dụng kiểu `String` làm return type |
| Kiểu tham số | `@Slot("parameter-type") String key` | Lần sử dụng kiểu `String` của parameter `key` |
| Kiểu trong `throws` | `throws @Slot("throws-type") IOException` | Lần sử dụng kiểu ngoại lệ `IOException` được khai báo |
| Cả method declaration | `@Target(METHOD)` và annotation trên method | Bản thân khai báo phương thức, không nhất thiết là kiểu trả về |
| Parameter declaration | `@Target(PARAMETER)` trước tham số | Bản thân khai báo tham số, không nhất thiết là kiểu của tham số |

Điều cần phân biệt là **vị trí cú pháp tương tự không bảo đảm cùng mục tiêu metadata**. Ví dụ `@Audit` trước tên kiểu trả về có thể là annotation của **method declaration** khi `@Audit` được giới hạn bằng `ElementType.METHOD`; còn `@Slot` giới hạn `TYPE_USE` là annotation của return type.

### Với `void` thì sao?

`void` không phải một kiểu giá trị có instance. Type-use annotation **không áp dụng cho `void` như return type** theo cách đặt `@Slot void`; không viết lời khuyên dùng `@NonNull void`. Nếu cần đánh dấu một **phương thức trả `void`** về mặt nghiệp vụ, hãy dùng annotation với `@Target(METHOD)` trên method declaration.

Ví dụ ý định đúng:

~~~java
@Target(ElementType.METHOD)
@interface Audited {}
~~~

~~~java
// Mảnh mã minh họa:
@Audited
public void refresh() { }
~~~

### Với kiểu nguyên thủy?

Một type-use annotation có thể gắn vào kiểu nguyên thủy như `int`:

~~~java
// Mảnh mã minh họa:
public @Slot("result-int") int count(
        @Slot("input-int") int value
) {
    return value;
}
~~~

Tuy nhiên, annotation tên `NonNull` trên `int` hầu như không có ý nghĩa về nullability, vì primitive `int` không chứa `null`. **Được phép về cú pháp** và **có ý nghĩa về hợp đồng** là hai câu hỏi riêng.

## 3. `@Target`: chọn đúng mục tiêu annotation

`@Target` là meta-annotation từ `java.lang.annotation`. Các hằng số liên quan trực tiếp gồm:

- `ElementType.TYPE_USE`: vị trí **sử dụng kiểu**, gồm return type, parameter type, exception type trong `throws`, type arguments, array component/dimension, cast, v.v. tùy ngữ cảnh cú pháp.
- `ElementType.METHOD`: **khai báo phương thức**. Annotation dành cho API, audit, mapping hoặc marker ở cấp method.
- `ElementType.PARAMETER`: **khai báo formal parameter**. Metadata cho framework binding, validation hoặc dependency injection trên tham số.
- `ElementType.TYPE_PARAMETER`: **khai báo type parameter** như `<T>`, không nên đánh đồng với kiểu đối số `String` trong `List<String>`.

Một annotation có thể có nhiều target:

~~~java
@Target({ElementType.PARAMETER, ElementType.TYPE_USE})
@interface CheckedValue {}
~~~

Tuy nhiên, điều đó có thể khiến việc hiểu annotation ở vị trí tham số khó hơn: cùng vị trí cú pháp có thể liên quan cả metadata ở cấp declaration và type-use. Khi muốn trình bày/test tách bạch, nên tạo **hai annotation khác nhau có target rõ ràng** rồi đọc bằng đúng API reflection.

### Tên annotation không quyết định target

Không có quy tắc Java mặc định rằng annotation tên `@NonNull` tự động là type-use annotation, hoặc annotation tên `@RequestParam` tự động là parameter declaration annotation. **Chính định nghĩa `@Target`** của từng loại annotation mới quyết định hợp lệ ở đâu. Nếu một annotation không khai báo `@Target`, không nên suy đoán nó có thể xuất hiện trên mọi type-use position: cần kiểm tra tập mục tiêu mà Java cho phép cho loại annotation đó.

### `@TYPE_USE` không phải từ khóa độc lập

Viết `@Target(ElementType.TYPE_USE)` trong **định nghĩa loại annotation**; khi sử dụng chỉ viết tên annotation như `@Slot`, không viết `@TYPE_USE String`. `TYPE_USE` là hằng enum của `ElementType`.

## 4. `@Retention`: annotation tồn tại đến thời điểm nào?

Khi định nghĩa annotation, `@Retention` chọn thời gian duy trì metadata:

| Policy | Ý nghĩa | Dùng reflection runtime đọc được? |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Chỉ có ở nguồn để công cụ/processor phân tích; không ghi vào class file | Không |
| `RetentionPolicy.CLASS` | Có thể lưu trong class file, không bắt buộc duy trì cho reflection runtime | Không qua Java reflection thông thường |
| `RetentionPolicy.RUNTIME` | Duy trì đến runtime | Có, tại vị trí và API reflection phù hợp |

Nếu không chỉ định `@Retention`, mặc định là `CLASS`. Khi muốn dùng `Method.getAnnotatedReturnType()`, `getAnnotatedParameterTypes()` và `getAnnotatedExceptionTypes()` để lấy giá trị annotation ở runtime, ví dụ tự tạo thường phải khai báo:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Role {
    String value();
}
~~~

**Không có phép màu validation:** `RUNTIME` làm metadata truy cập được bằng reflection; nó **không** tự kiểm tra `null`, không ép buộc ràng buộc trong JVM, và không tự chuyển ngoại lệ thành dạng khác. Hành vi kiểm tra phải đến từ mã ứng dụng, một annotation processor, static analyzer, framework hoặc cơ chế khác hiểu đúng annotation đó.

## 5. Ví dụ chạy độc lập 1: tách method, parameter và type-use annotation

Tạo tệp **AnnotationPlacementDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class AnnotationPlacementDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Operation {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface ParameterInfo {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeInfo {
        String value();
    }

    static final class Handler {
        @Operation("api")
        public @TypeInfo("return") String handle(
                @ParameterInfo("request")
                @TypeInfo("argument") String text
        ) throws @TypeInfo("exception") IllegalArgumentException {
            return text == null ? "" : text.strip();
        }
    }

    public static void main(String[] args) throws Exception {
        Method method =
                Handler.class.getDeclaredMethod("handle", String.class);

        Operation operation = method.getAnnotation(Operation.class);
        ParameterInfo parameter = method
                .getParameters()[0]
                .getAnnotation(ParameterInfo.class);

        TypeInfo returnType = method
                .getAnnotatedReturnType()
                .getAnnotation(TypeInfo.class);

        TypeInfo argumentType = method
                .getAnnotatedParameterTypes()[0]
                .getAnnotation(TypeInfo.class);

        TypeInfo exceptionType = method
                .getAnnotatedExceptionTypes()[0]
                .getAnnotation(TypeInfo.class);

        System.out.println("method=" + operation.value());
        System.out.println("parameter=" + parameter.value());
        System.out.println("return=" + returnType.value());
        System.out.println("argument=" + argumentType.value());
        System.out.println("throws=" + exceptionType.value());
        System.out.println("result=" + new Handler().handle(" Java "));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac AnnotationPlacementDemo.java
java AnnotationPlacementDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
method=api
parameter=request
return=return
argument=argument
throws=exception
result=Java
~~~

### Vì sao lấy annotation theo hai đường khác nhau?

1. `method.getAnnotation(Operation.class)` đọc annotation **của method declaration**. `@Operation` có `@Target(METHOD)`.
2. `method.getParameters()[0].getAnnotation(ParameterInfo.class)` đọc annotation **của parameter declaration**. `@ParameterInfo` có `@Target(PARAMETER)`.
3. `method.getAnnotatedReturnType()` trả `AnnotatedType` cho **kiểu trả về**. `getAnnotation(TypeInfo.class)` trên đối tượng này đọc annotation `@TypeInfo("return")`.
4. `method.getAnnotatedParameterTypes()[0]` trả `AnnotatedType` cho **kiểu của tham số đầu tiên**, khác với đối tượng `Parameter` mô tả declaration.
5. `method.getAnnotatedExceptionTypes()[0]` trả `AnnotatedType` cho **kiểu ngoại lệ trong danh sách throws**.
6. `getDeclaredMethod("handle", String.class)` chọn method theo tên và **kiểu tham số sau erasure**. Annotation trên return type hoặc throws không làm thay đổi chữ ký tra cứu này.

Cả ba `@TypeInfo` đều là cùng một loại annotation nhưng nằm trên **ba vị trí sử dụng kiểu khác nhau**; mỗi vị trí giữ giá trị riêng.

### Tại sao `text.strip()` vẫn chạy được?

`String.strip()` có từ Java 11 và vẫn được dùng trong JDK 17+. Nó chuẩn hóa ký tự trắng theo `Character.isWhitespace`. Phần đánh dấu annotation không thay đổi tác vụ `strip()`; đó là logic được viết tường minh trong phương thức.

## 6. Những API reflection cần nhớ

Trong `java.lang.reflect.Method`:

~~~java
AnnotatedType returnType = method.getAnnotatedReturnType();

AnnotatedType[] parameterTypes =
        method.getAnnotatedParameterTypes();

AnnotatedType[] exceptionTypes =
        method.getAnnotatedExceptionTypes();
~~~

Đây là các mảnh mã minh họa cần import `java.lang.reflect.AnnotatedType` và có biến `method`. Ba API này phản ánh trực tiếp các vị trí **type-use** đang học. Các tên API này đã có trong Java 8.

| API | Ý nghĩa | Đừng nhầm với |
| --- | --- | --- |
| `Method.getAnnotatedReturnType()` | AnnotatedType của return type | `Method.getAnnotations()` trên method declaration |
| `Method.getAnnotatedParameterTypes()` | AnnotatedType theo từng parameter type | `Method.getParameterAnnotations()` cho annotation parameter declaration |
| `Method.getAnnotatedExceptionTypes()` | AnnotatedType theo từng declared exception type | `Method.getExceptionTypes()` chỉ trả Class của các exception |
| `Method.getGenericReturnType()` | `Type` của return type có thông tin generic | Không phải API lấy annotation TYPE_USE |
| `Method.getGenericParameterTypes()` | `Type[]` của parameter types | Không phải `AnnotatedType[]` |
| `Method.getGenericExceptionTypes()` | `Type[]` của throws types | Không chứa đầy đủ vị trí annotation |
| `Parameter.getAnnotatedType()` | AnnotatedType của một parameter | Khác với annotation trên bản thân declaration của `Parameter` |

Với `getAnnotatedReturnType()`, code nên kiểm tra annotation tồn tại hay không trước khi gọi `.value()`. Ví dụ chạy ở phần 5 biết trước phương thức đã mang từng annotation, nhưng một tiện ích reflection tổng quát không thể giả định mọi method đều có annotation ấy.

### Thứ tự tham số và throws

Mỗi phần tử trong mảng `getAnnotatedParameterTypes()` tương ứng **theo vị trí** với một parameter. `getAnnotatedExceptionTypes()` tương ứng các kiểu trong mệnh đề `throws` đã khai báo. Nếu method không khai báo exceptions, mảng exception types rỗng.

Không nên tự suy ra method *chỉ* có thể ném những loại exception liệt kê trong `throws`. Java cho phép runtime exception không được khai báo; một số lỗi từ code/library có thể xảy ra ngoài danh sách. Annotation trên throws type **không** phải một cơ chế bắt hoặc kiểm soát exception.

## 7. Annotation trên generic return type: hai tầng metadata

Khi return type là generic, annotation trên **kiểu bao** và trên **đối số kiểu** là hai vị trí độc lập:

~~~java
// Mảnh mã minh họa:
public @Role("container") java.util.List<
        @Role("element") String
> names() {
    return java.util.List.of("Java");
}
~~~

Mã ví dụ dùng `@Role` có `@Target(TYPE_USE)`. Ở đây:

- `@Role("container")` thuộc vị trí dùng kiểu `List<...>` **ở lớp ngoài cùng**.
- `@Role("element")` thuộc vị trí dùng kiểu `String` **làm type argument** của `List`.
- `Method.getAnnotatedReturnType()` cho metadata trên return type tổng thể.
- Để truy cập metadata của `String` bên trong, cần kiểm tra đối tượng là `AnnotatedParameterizedType`, rồi gọi `getAnnotatedActualTypeArguments()`.

Không dùng `getAnnotations()` trên method declaration để trông chờ nhìn thấy cả hai. Cũng không giả định đọc `method.getReturnType()` (`Class<?>`) là đủ, vì generic type argument và type-use annotation không được biểu diễn bằng cách đó.

## 8. Ví dụ chạy độc lập 2: generic return, parameter và throws

Tạo tệp **AnnotatedGenericDemo.java**:

~~~java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.util.List;

public class AnnotatedGenericDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Role {
        String value();
    }

    static final class Repository {
        public @Role("container") List<
                @Role("element") String
        > find(@Role("parameter") String key)
                throws @Role("exception") IOException {
            if (key == null) {
                throw new IOException("missing key");
            }
            return List.of(key.strip());
        }
    }

    static String label(AnnotatedType type) {
        Role role = type.getAnnotation(Role.class);
        return role == null ? "(none)" : role.value();
    }

    public static void main(String[] args) throws Exception {
        Method method =
                Repository.class.getDeclaredMethod("find", String.class);

        AnnotatedType result = method.getAnnotatedReturnType();
        AnnotatedParameterizedType generic =
                (AnnotatedParameterizedType) result;

        AnnotatedType element =
                generic.getAnnotatedActualTypeArguments()[0];

        System.out.println("container=" + label(result));
        System.out.println("element=" + label(element));
        System.out.println("parameter=" +
                label(method.getAnnotatedParameterTypes()[0]));
        System.out.println("throws=" +
                label(method.getAnnotatedExceptionTypes()[0]));

        System.out.println("data=" +
                new Repository().find(" Java ").get(0));
    }
}
~~~

Biên dịch và chạy trên JDK 17+ (`List.of` từ Java 9, `String.strip` từ Java 11):

~~~bash
javac AnnotatedGenericDemo.java
java AnnotatedGenericDemo
~~~

**Stdout chính xác:**

~~~text
container=container
element=element
parameter=parameter
throws=exception
data=Java
~~~

Ở đây `getAnnotatedReturnType()` trả đối tượng phù hợp với `AnnotatedParameterizedType` vì return type là `List<String>`. Ép kiểu hợp lệ trong đúng ví dụ này; với framework đọc những method có return type khác, hãy **kiểm tra `instanceof AnnotatedParameterizedType`** trước khi cast.

`List<@Role String>` không có nghĩa phần tử của `List` sẽ tự động được kiểm tra bởi `List.of`. Annotation ghi metadata trên **lần dùng kiểu**, còn logic ràng buộc phần tử cần công cụ hoặc chương trình hiểu hợp đồng đó.

### Một `throws` có thể có nhiều exception types

~~~java
// Mảnh mã minh họa:
void execute() throws @Role("io") IOException,
        @Role("state") IllegalStateException {
}
~~~

Đây là **hai vị trí type-use** trong danh sách `throws`. Phản chiếu `getAnnotatedExceptionTypes()` có các phần tử tương ứng; không có “một annotation throws chung” tự động áp lên toàn bộ danh sách. Nên gắn annotation tại từng kiểu mà hợp đồng cần mô tả.

## 9. Type-use annotation trên array và generic sâu hơn

Type-use annotation có thể đặt trên nhiều tầng của một type, không chỉ ở tên kiểu đầu tiên. Ví dụ cùng một chữ ký có thể gồm:

~~~java
// Mảnh mã minh họa:
java.util.Map<
        @Role("key") String,
        java.util.List<@Role("item") Integer>
> index;
~~~

`@Role("key")` nằm trên type argument `String`, còn `@Role("item")` nằm trên type argument `Integer` ở cấp lồng sâu hơn. Đây **không** phải hai annotation trên bản thân field declaration.

Khi dùng reflection, có thể đi theo cây `AnnotatedType`:

~~~text
AnnotatedType (Map<String,List<Integer>>)
  -> AnnotatedParameterizedType
       -> argument 0: AnnotatedType(String, Role=key)
       -> argument 1: AnnotatedParameterizedType(List<Integer>)
            -> argument 0: AnnotatedType(Integer, Role=item)
~~~

Với array, cú pháp Java còn cho phép annotation trên từng **mức array type** và trên element type. Ví dụ minh họa:

~~~java
// Mảnh mã minh họa, giả định @Role chỉ có TYPE_USE:
@Role("element") String @Role("array") [] values;
~~~

Cách đặt trước `String` và trước `[]` biểu diễn **hai vị trí khác nhau**. Khi cần đọc đầy đủ metadata array bằng reflection, phải xét `AnnotatedArrayType` và các component types, không chỉ dùng `getAnnotatedReturnType().getAnnotations()` ở lớp ngoài cùng.

**Thực hành:** nếu type phức tạp, vẽ cây kiểu trước rồi đánh dấu annotation trên từng node; giảm nguy cơ hiểu nhầm nó gắn với container, element hay array dimension nào.

## 10. Annotation trên kiểu ngoại lệ không làm thay đổi cơ chế `throws`

Ví dụ:

~~~java
// Mảnh mã minh họa:
public void save() throws @Role("retryable") IOException {
    throw new IOException("temporary failure");
}
~~~

Điều **đúng**:

- `throws IOException` là một phần khai báo checked-exception contract được compiler kiểm tra theo quy tắc Java.
- `@Role("retryable")` là type-use annotation trên vị trí sử dụng `IOException` trong `throws`.
- Nếu `@Role` có retention phù hợp, runtime tool có thể đọc annotation từ `getAnnotatedExceptionTypes()`.

Điều **không tự xảy ra**:

- Java không tự retry khi thấy chữ `retryable`.
- Java không tự chuyển IOException thành unchecked exception.
- `catch` không tự hiểu annotation này là một tiêu chuẩn phân loại exception.
- Annotation không bảo đảm exception đó thật sự sẽ xuất hiện, hoặc mọi lỗi khác đều bị loại bỏ.
- Không tự động thay đổi thứ tự `catch`, multi-catch hoặc cơ chế truyền exception của JVM.

Nếu muốn ứng dụng dùng metadata đó để xây chính sách retry, phải triển khai một **cơ chế riêng** có kiểm thử; chỉ ghi annotation lên kiểu ngoại lệ thì chưa đủ. Trong hệ thống thực tế, retry còn phụ thuộc tính idempotent, thời gian chờ, loại thao tác và nguyên nhân lỗi, không thể suy từ tên annotation một cách ngây thơ.

### Khai báo `throws` trên lambda và interface

Một lambda có target là `Function<T,R>` không thể để checked `IOException` chưa xử lý thoát ra từ SAM `apply` vì `Function.apply` không khai báo `throws IOException`. Việc thêm type-use annotation lên kiểu return/parameter/throws ở một method khác **không thay đổi** ràng buộc checked-exception của functional descriptor.

Khi một API callback có thể phát sinh checked exception, hãy chọn một interface có `throws` đúng hợp đồng hoặc xử lý lỗi có chủ đích. Không dùng annotation như một cách “qua mặt” compiler.

## 11. Annotation không phải type qualifier được Java tự kiểm chứng

Dù tên là `@NonNull`, `@Range`, `@ReadOnly` hay `@Secure`, Java compiler tiêu chuẩn không tự thêm mọi quy tắc kiểm tra tương ứng chỉ vì thấy một annotation tự tạo.

Ví dụ định nghĩa:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}
~~~

Và method:

~~~java
// Mảnh mã minh họa:
@NonNull String echo(@NonNull String value) {
    return value;
}
~~~

**Nếu chỉ có annotation tự định nghĩa này**, phương thức vẫn có thể được gọi bằng `null`, và vẫn có thể trả về `null`. Ngôn ngữ Java không tự ném exception hay kiểm tra hợp đồng `@NonNull` tại runtime chỉ vì annotation tồn tại.

Tương tự:

~~~java
// Mảnh mã minh họa, không có validator tự động:
@NonNull String result = null;
~~~

Lời gán trên không được Java tiêu chuẩn từ chối do chính annotation tự tạo ấy. Một công cụ static analysis hoặc type checker **hiểu loại annotation cụ thể** mới có thể cảnh báo/lỗi theo quy tắc đã cấu hình. Khi cần bảo vệ biên runtime, vẫn dùng các kiểm tra như `Objects.requireNonNull`, kiểm tra miền và xử lý lỗi thích hợp.

### Không có `@NonNull` chuẩn duy nhất do Java SE bắt buộc áp dụng

Các dự án có thể dùng những annotation khác nhau từ thư viện hoặc framework. Không nên giả định một `@NonNull` xuất hiện ở classpath là cùng hợp đồng với `@NonNull` của thư viện khác; `@Target`, `@Retention`, công cụ phân tích và cách xử lý null có thể khác nhau. Khi bảo trì mã, hãy kiểm tra **import và định nghĩa annotation thực tế**.

## 12. Ví dụ chạy độc lập 3: đánh dấu không đồng nghĩa với validation

Tạo tệp **TypeUseNotValidationDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Objects;

public class TypeUseNotValidationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface NonNull {}

    static final class UnsafeService {
        @NonNull String echo(@NonNull String text) {
            return text;
        }
    }

    static final class SafeService {
        @NonNull String echo(@NonNull String text) {
            return Objects.requireNonNull(text, "text");
        }
    }

    public static void main(String[] args) {
        UnsafeService unsafe = new UnsafeService();
        SafeService safe = new SafeService();

        System.out.println(unsafe.echo(null) == null);

        try {
            safe.echo(null);
        } catch (NullPointerException ex) {
            System.out.println("safe rejected null");
        }

        System.out.println(safe.echo("Java"));
    }
}
~~~

Biên dịch/chạy JDK 17+ (phần cú pháp chính vẫn có từ Java 8):

~~~bash
javac TypeUseNotValidationDemo.java
java TypeUseNotValidationDemo
~~~

**Stdout chính xác:**

~~~text
true
safe rejected null
Java
~~~

Điểm quan trọng: cả hai method đều có **cùng metadata `@NonNull` trên return type và parameter type**, nhưng chỉ `SafeService.echo` thực sự kiểm tra null bằng code. Annotation này không là cơ chế bảo mật, validation hay bảo đảm null-safety độc lập.

Với dự án dùng annotation processor/type checker đã cấu hình, kết quả *có thể có thêm cảnh báo hoặc lỗi phân tích tĩnh*. Ví dụ nói về hành vi của **Java tiêu chuẩn với annotation tự tạo** và không giả định framework nào đã tích hợp.

## 13. Chọn target phù hợp với trường hợp sử dụng

### 13.1. Metadata ở cấp method declaration

Nếu bạn cần gắn operation ID, authorization requirement, endpoint route hoặc một cờ audit cho **toàn bộ method**, hãy định nghĩa annotation với `@Target(ElementType.METHOD)` và đọc bằng `method.getAnnotation(...)`.

~~~java
@Target(ElementType.METHOD)
@interface Audited {}
~~~

~~~java
// Mảnh mã minh họa:
@Audited
public String read(String id) {
    return id;
}
~~~

`@Audited` không tự kiểm tra vai trò người dùng; framework hay mã thực thi mới đảm nhận chức năng đó. Và nếu chỉ dùng `@Target(METHOD)`, nó không phải annotation gắn với kiểu `String` trả về.

### 13.2. Metadata ở cấp parameter declaration

Nếu bạn cần chỉ định tên tham số trong request binding hoặc quy tắc cấu hình ở cấp formal parameter, `@Target(PARAMETER)` mô tả **tham số được khai báo**:

~~~java
@Target(ElementType.PARAMETER)
@interface RequestField {
    String value();
}
~~~

~~~java
// Mảnh mã minh họa:
public String load(@RequestField("id") String input) {
    return input;
}
~~~

`@RequestField("id")` ở đây là metadata declaration của `input`; nó không phải TYPE_USE annotation trên mọi chỗ `String` xuất hiện. Framework có thể hỗ trợ annotation theo hợp đồng riêng, không phải Java tự ràng buộc đối số theo tên `id`.

### 13.3. Metadata dành cho type checker

Nếu mục tiêu là diễn đạt nullability hoặc tính bất biến của **một vị trí sử dụng kiểu**, nhất là khi type xuất hiện ở return, parameter, generic element hoặc throws type, `TYPE_USE` phù hợp về cấu trúc. Nhưng annotation type-use chỉ có giá trị thực tế khi có **quy ước + công cụ** hiểu semantics. Với nullability, cần nhất quán giữa thư viện và công cụ phân tích.

Một annotation có thể đồng thời có `TYPE_USE` và target declaration tương ứng nếu thiết kế framework yêu cầu, nhưng cần tài liệu hóa ý nghĩa ở mỗi vị trí và test bằng reflection/công cụ thực tế để tránh hiểu nhầm.

## 14. Trường hợp biên khi dùng reflection

### 14.1. Annotation không có ở vị trí đọc

~~~java
TypeInfo info = method.getAnnotatedReturnType()
        .getAnnotation(TypeInfo.class);
~~~

`info` có thể **null**, ví dụ method không gắn `@TypeInfo` lên return type, hoặc annotation không có retention runtime. Đừng gọi `info.value()` nếu chưa kiểm tra. Một helper an toàn:

~~~java
// Mảnh mã minh họa:
static String nameOrNone(java.lang.reflect.AnnotatedType type) {
    TypeInfo info = type.getAnnotation(TypeInfo.class);
    return info == null ? "(none)" : info.value();
}
~~~

### 14.2. Annotation ở generic element chứ không phải outer type

`List<@Role("element") String>` có type-use annotation **trên argument** chứ không phải trên chính outer `List`. `getAnnotatedReturnType().getAnnotation(Role.class)` có thể trả null dù phần tử kiểu `String` được đánh dấu. Cần đi xuống `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.

### 14.3. Annotation ở array component hoặc dimension

Với `String @Role []` và `@Role String[]`, vị trí type-use có thể khác nhau. Nếu chỉ đọc outer annotations và bỏ qua `AnnotatedArrayType.getAnnotatedGenericComponentType()`, có thể mất metadata ở tầng component. Test với ví dụ thật, không đoán vị trí chỉ từ tên annotation.

### 14.4. `getDeclaredMethod` phải tìm đúng method

Các phương thức overload cùng tên nhưng khác kiểu tham số sau erasure có thể có annotations khác nhau. Một lời gọi reflection chỉ theo tên mà không đối chiếu tham số là không đủ. `getDeclaredMethod("find", String.class)` chọn method có một đối số `String`, không chọn phiên bản nhận `Integer`.

Khi làm việc với generic methods/bridge methods, synthetic methods và các API kế thừa, cần xác định đúng đối tượng `Method` và hợp đồng của framework. Không nên lấy annotation từ một method rồi mặc định nó được sao chép sang mọi overload/override.

### 14.5. Annotation không tự kế thừa qua override

`@Inherited` chỉ có tác dụng đặc thù với annotation trên **class declaration**, không phải cơ chế tổng quát kế thừa annotation của method, parameter hay mọi type-use qua override. Nếu một class override method, đừng mặc định runtime reflection trên method mới sẽ cho cùng annotation type-use của method cha. Nếu framework cần chính sách kế thừa metadata, phải thiết kế cách tìm kiếm ở các khai báo có liên quan.

### 14.6. Retention không biến annotation thành cấu trúc dữ liệu bền vững cho mọi công cụ

`RUNTIME` thích hợp cho ứng dụng dùng reflection, nhưng nếu annotation chỉ phục vụ compile-time checker, có thể không cần retention runtime. Chọn policy theo người **tiêu thụ metadata**, không mặc định mọi annotation đều phải `RUNTIME`.

## 15. `throws` annotation và ranh giới checked/unchecked exception

Một method có thể khai báo:

~~~java
// Mảnh mã minh họa:
void download() throws @Role("network") java.io.IOException,
        @Role("interrupted") InterruptedException {
    // ...
}
~~~

`IOException` và `InterruptedException` là checked exceptions thông thường. Metadata trên từng **type-use trong throws** không loại bỏ nghĩa vụ xử lý hoặc khai báo ngoại lệ theo quy tắc Java.

Ngược lại, `IllegalArgumentException` là unchecked exception; có thể được khai báo trong `throws`, thậm chí được annotate type-use, nhưng caller không bị buộc phải catch nó chỉ bởi mệnh đề đó:

~~~java
// Mảnh mã minh họa:
void validate() throws @Role("bad-input") IllegalArgumentException {
    throw new IllegalArgumentException("invalid");
}
~~~

Annotation trên `IllegalArgumentException` không chuyển unchecked exception thành checked. **Bản chất của lớp exception** và quy tắc Java quyết định yêu cầu xử lý, không phải chữ `Role`.

### `throws` không thể annotate mọi luồng lỗi từ method

Vì `throws` liệt kê *declared exception types*, những lỗi runtime không được liệt kê không có một vị trí tương ứng trong mảng `getAnnotatedExceptionTypes()`. Việc chỉ nhìn vào metadata `throws` để xây danh sách “mọi lỗi có thể xảy ra” là không chính xác.

Trong code ứng dụng, nên kết hợp hợp đồng exception, validation của input và xử lý tài nguyên (chẳng hạn try-with-resources) phù hợp. Annotation bổ sung thông tin, không thay thế các kỹ thuật này.

## 16. Sai lầm hay gặp

| Ngộ nhận / lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `@Target(METHOD)` và `@Target(TYPE_USE)` là cùng một chuyện | Một cái đánh dấu declaration, một cái đánh dấu type position | Chọn target theo metadata cần mô tả |
| Đặt annotation trước return type là luôn annotate method | Vị trí cú pháp có thể biểu diễn TYPE_USE | Xem định nghĩa `@Target`, dùng đúng reflection API |
| Tham số đã có annotation thì type của nó chắc chắn được annotate | PARAMETER và TYPE_USE là hai target khác | Dùng `Parameter.getAnnotation` vs `getAnnotatedParameterTypes` |
| `throws @Role IOException` làm chương trình tự retry | Annotation không thực thi chính sách retry | Thiết kế retry riêng có kiểm thử |
| Annotation `@NonNull` tự chặn null | Java không tự hiểu semantics tùy ý của annotation | Cấu hình checker và/hoặc kiểm tra runtime |
| Quên `@Retention(RUNTIME)` nhưng muốn reflection thấy | CLASS/SOURCE không phơi ra theo runtime reflection thông thường | Dùng retention đúng nhu cầu |
| `getReturnType()` phản ánh toàn bộ annotation generic | Chỉ trả `Class` raw return | Dùng `AnnotatedType` và đi qua generic nodes |
| Coi `List<@Role String>` giống `@Role List<String>` | Vị trí outer type khác element type | Phân biệt lớp bao và type argument |
| Không kiểm tra null từ `getAnnotation` | Có thể NPE khi annotation vắng mặt | Kiểm tra null hoặc helper |
| Giả định annotation method được tự sao chép khi override | Không có quy tắc kế thừa chung | Xem đúng method declaration và chính sách framework |
| Dùng `@Role` trên `void` như giá trị nullable | `void` không có object return | Dùng METHOD annotation khi muốn đánh dấu method |
| Không phân biệt checked/unchecked exception | Annotation trong throws không quyết định loại exception | Dựa vào exception hierarchy và hợp đồng thực tế |

## 17. Bài tập thực hành

**Bài 1 — Phân loại vị trí.** Cho một annotation `@Mark` có `@Target(TYPE_USE)`. Hãy đánh dấu return type, parameter type và hai exception types trong `throws` của phương thức `read(String)`. Giải thích có bao nhiêu vị trí type-use khác nhau và vì sao không phải một annotation chung của method.

**Bài 2 — Declaration vs type-use.** Định nghĩa `@Trace` với `@Target(METHOD)`, `@ParamName` với `@Target(PARAMETER)`, `@ValidatedType` với `@Target(TYPE_USE)`. Đặt cả ba đúng chỗ ở một phương thức. Dùng reflection đọc ba annotation ở ba đường tương ứng.

**Bài 3 — Retention.** Đổi `@Retention(RUNTIME)` của `@Role` sang `SOURCE`, rồi xem khi đọc reflection bằng `getAnnotatedReturnType().getAnnotation(Role.class)` có trả về object hay null. Giải thích vì sao điều đó không nói rằng annotation “không tồn tại trong source”.

**Bài 4 — Generic metadata.** Viết phương thức trả `Map<@Role("key") String, List<@Role("value") Integer>>` và dùng `AnnotatedParameterizedType` đi xuống đúng hai type arguments. Nêu trường hợp phải cast/kiểm tra type nào để tiếp cận annotation sâu bên trong.

**Bài 5 — Annotation không bảo đảm null.** Viết một phương thức nhận `@NonNull String` nhưng trả lại đối số mà không kiểm tra. Thử truyền `null` trên Java tiêu chuẩn với annotation tự tạo. Sau đó dùng `Objects.requireNonNull` và so sánh hành vi.

**Bài 6 — Annotated throws.** Định nghĩa method `load()` có `throws @Role("io") IOException, @Role("state") IllegalStateException`, sau đó in các `Role` bằng `getAnnotatedExceptionTypes()`. So sánh với `getExceptionTypes()` và giải thích vì sao không thể suy ra toàn bộ runtime exceptions chỉ bằng metadata throws.

**Bài 7 — Thiết kế hợp đồng.** Một API trả `List<String>`, nhận user ID và có thể ném `IOException`. Xác định yêu cầu nào nên là annotation ở cấp method, yêu cầu nào nên ở return type/element type/parameter type/throws type, và phần nào phải được ứng dụng hoặc type checker thực thi. Viết test với đầu vào null, danh sách rỗng, exception thật và metadata reflection.

## 18. Checklist trước khi dùng type-use annotation trong dự án

- **Mục tiêu:** metadata gắn với *method/parameter declaration* hay *vị trí sử dụng kiểu*?
- **Target:** đã khai báo `TYPE_USE`, `METHOD` hoặc `PARAMETER` đúng nhu cầu chưa?
- **Retention:** runtime reflection có cần không? Đã dùng `RUNTIME` đúng nơi chưa?
- **Return:** annotation nằm trên outer return type hay type argument bên trong?
- **Parameter:** có đang đọc `getAnnotatedParameterTypes()` khi thực sự cần type annotation không?
- **Throws:** đã annotate từng exception type riêng và đọc `getAnnotatedExceptionTypes()` đúng chưa?
- **Semantics:** có công cụ hiểu annotation không, hay chỉ có metadata?
- **Nullability:** có ràng buộc runtime hoặc static checker thực sự thay vì chỉ đặt tên `@NonNull` không?
- **Version:** các ví dụ Java 17+ có dùng API như `String.strip`/ `List.of` đúng mức tương thích dự án không?
- **Testing:** đã thử annotation vắng mặt, retention không phải RUNTIME, generic nested types và overload/override khi cần chưa?

## 19. Tóm tắt

- `@Target(ElementType.TYPE_USE)` cho phép gắn annotation lên **kiểu được sử dụng**: kiểu trả về, kiểu của tham số và từng kiểu ngoại lệ trong `throws`. Đây là khả năng từ Java 8 và vẫn được sử dụng hiện nay.
- Phải phân biệt **declaration annotation** (`METHOD`, `PARAMETER`) với **type-use annotation** (`TYPE_USE`). Chúng có thể gần nhau trong cú pháp nhưng được đọc bằng những API reflection khác nhau.
- Với retention runtime, dùng `Method.getAnnotatedReturnType()`, `getAnnotatedParameterTypes()`, `getAnnotatedExceptionTypes()`. Với generic type arguments và arrays, đi sâu vào cây `AnnotatedType` bằng các subtype thích hợp.
- Annotation **không tự** kiểm tra null, validate giá trị hay xử lý ngoại lệ. Hợp đồng chỉ có tác dụng thực tế khi code, framework hoặc tool hiểu nó và thực thi/kiểm chứng.
- Thiết kế annotation bền vững bắt đầu từ mục tiêu rõ ràng, vị trí đặt đúng, retention phù hợp, và các test cả compile-time lẫn runtime.
