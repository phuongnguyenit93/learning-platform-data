# TYPE_USE trên kiểu trường, tham số và giá trị trả về trong Java

## 1. `TYPE_USE` mô tả vị trí *sử dụng kiểu*

Trong Java, một annotation có thể được gắn lên **khai báo** của một field, phương thức hoặc tham số; từ Java 8, annotation còn có thể được gắn lên **kiểu được sử dụng** tại nhiều vị trí trong mã. Để định nghĩa loại annotation cho các vị trí ấy, dùng `ElementType.TYPE_USE` trong `@Target`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface TypeHint {
    String value();
}
```

Với loại annotation này, các ví dụ sau đều là cách gắn lên **kiểu**:

```java
// Những đoạn này chỉ minh họa vị trí, không tạo thành tệp chạy độc lập.
class Example {
    private @TypeHint("field-type") String name;

    public @TypeHint("return-type") String normalize(
            @TypeHint("parameter-type") String input) {
        return input.strip();
    }
}
```

- `@TypeHint("field-type") String` đánh dấu **kiểu của field `name`**.
- `@TypeHint("parameter-type") String` đánh dấu **kiểu của tham số `input`**.
- `@TypeHint("return-type") String` đánh dấu **kiểu trả về `String`** của phương thức `normalize`.

**Điểm mấu chốt:** `TYPE_USE` liên quan đến **vị trí xuất hiện của kiểu trong source code**, không phải thao tác “gắn annotation lên mọi đối tượng có kiểu đó”. Metadata không tự gắn với từng đối tượng `String` được tạo lúc chạy; nó được mô tả tại vị trí khai báo/sử dụng kiểu trong chương trình.

Những vị trí trên khác với việc gắn annotation trực tiếp lên **field declaration**, **parameter declaration** hoặc **method declaration**. Dù cú pháp có thể trông rất gần nhau, Java phân biệt các vị trí đó và cung cấp API Reflection tương ứng.

## 2. Ba trường hợp trọng tâm

### 2.1 Kiểu của trường (field type)

Ví dụ:

```java
class Account {
    private @TypeHint("account-id") String id;
}
```

Ở đây `id` là trường; `String` là kiểu của trường. Annotation đứng tại vị trí kiểu, nên một bên xử lý có thể biết rằng **kiểu của trường `id`** mang metadata `"account-id"`.

Cách lấy metadata với Reflection (với annotation có retention `RUNTIME`):

```java
Field field = Account.class.getDeclaredField("id");
AnnotatedType annotatedType = field.getAnnotatedType();
TypeHint hint = annotatedType.getAnnotation(TypeHint.class);
```

`Field.getAnnotatedType()` trả về một đối tượng `AnnotatedType` mô tả **kiểu đã khai báo của field**, bao gồm annotation ở vị trí sử dụng kiểu. `Field.getDeclaredAnnotation(TypeHint.class)` lại hỏi về **annotation trực tiếp trên khai báo field**; nếu loại `TypeHint` chỉ có `@Target(TYPE_USE)`, đó không phải cách đúng để truy vấn annotation trên kiểu.

### 2.2 Kiểu của tham số (parameter type)

Ví dụ:

```java
class AccountService {
    void find(@TypeHint("account-id") String id) {}
}
```

`@TypeHint` nằm trên kiểu `String` của tham số `id`. Có thể đọc các kiểu tham số theo thứ tự bằng:

```java
Method method = AccountService.class.getDeclaredMethod("find", String.class);
AnnotatedType[] parameterTypes = method.getAnnotatedParameterTypes();
TypeHint hint = parameterTypes[0].getAnnotation(TypeHint.class);
```

Mảng `getAnnotatedParameterTypes()` tương ứng với các tham số hình thức của phương thức. Ở ví dụ trên chỉ có một tham số nên phần tử `[0]` biểu diễn kiểu `String` đã được đánh dấu.

Đừng nhầm API này với `Method.getParameterAnnotations()`, vốn đọc annotation trên **khai báo tham số**. Một loại annotation có `@Target(PARAMETER)` chuyên dành cho khai báo tham số, trong khi `@Target(TYPE_USE)` chuyên dành cho các vị trí dùng kiểu. Một annotation được khai báo cho phép nhiều `ElementType` có thể có quy tắc áp dụng ở cả hai nhóm; khi đọc cần xác định rõ metadata mình thực sự muốn.

### 2.3 Kiểu trả về (return type)

Ví dụ:

```java
class AccountService {
    public @TypeHint("result-type") String getName() {
        return "Lan";
    }
}
```

Đây là annotation **trên kiểu `String` được trả về**, không phải annotation đánh dấu phương thức `getName` theo nghĩa `ElementType.METHOD`.

Reflection truy vấn đúng vị trí:

```java
Method method = AccountService.class.getDeclaredMethod("getName");
AnnotatedType returnType = method.getAnnotatedReturnType();
TypeHint hint = returnType.getAnnotation(TypeHint.class);
```

Nếu chỉ truy vấn `method.getAnnotation(TypeHint.class)`, bạn đang hỏi metadata của **khai báo phương thức**. Annotation ở return type nằm trong `getAnnotatedReturnType()`.

**Một phương thức có thể cùng lúc có metadata ở nhiều vị trí**: trên chính declaration của phương thức, trên kiểu trả về, trên khai báo từng tham số và trên kiểu của từng tham số. Consumer phải chọn đúng API tương ứng.

## 3. So sánh `TYPE_USE` với `FIELD`, `PARAMETER`, `METHOD`

| `ElementType` | Đánh dấu cái gì? | Ví dụ khái niệm | API Reflection trọng tâm |
| --- | --- | --- | --- |
| `FIELD` | Khai báo trường | `@FieldTag private String id;` | `Field.getAnnotation(...)` |
| `TYPE_USE` trên field | Kiểu được dùng để khai báo trường | `private @TypeTag String id;` | `Field.getAnnotatedType()` |
| `PARAMETER` | Khai báo tham số | `void save(@ParamTag String id)` | `Parameter.getAnnotation(...)` hoặc `Method.getParameterAnnotations()` |
| `TYPE_USE` trên tham số | Kiểu của tham số | `void save(@TypeTag String id)` | `Method.getAnnotatedParameterTypes()` |
| `METHOD` | Khai báo phương thức | `@MethodTag String load()` | `Method.getAnnotation(...)` |
| `TYPE_USE` trên return | Kiểu trả về của phương thức | `@TypeTag String load()` | `Method.getAnnotatedReturnType()` |

Ví dụ của bảng dùng các tên annotation giả định `FieldTag`, `ParamTag`, `MethodTag`, `TypeTag`; cần khai báo các loại tương ứng trước khi biên dịch.

Có hai điều cần lưu ý:

1. **Đích `@Target` giới hạn vị trí hợp lệ**. Chỉ cho phép `FIELD` không có nghĩa được phép gắn annotation vào type argument như `List<@Tag String>`; muốn gắn tại đó cần `TYPE_USE`.
2. **Vị trí mã nguồn nhìn giống nhau không đồng nghĩa metadata nằm trong cùng một nơi khi Reflection đọc**. Đặc biệt trước kiểu của tham số hoặc trước kiểu trả về, một annotation có thể thuộc ngữ cảnh declaration hay type use tùy vào loại annotation được khai báo hỗ trợ. Hãy thiết kế và truy vấn đúng loại metadata.

### Ví dụ chú thích trên declaration và kiểu ở cạnh nhau

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface SensitiveField {}

@Target(ElementType.TYPE_USE)
@interface NonNullHint {}

class Customer {
    @SensitiveField
    private @NonNullHint String email;
}
```

`@SensitiveField` đánh dấu **khai báo field `email`**, còn `@NonNullHint` đánh dấu **kiểu `String` của field**. Đây là đoạn mã hoàn chỉnh về mặt khai báo, nhưng không có `main` và không nhằm thực thi một chương trình độc lập.

Một annotation có tên `NonNullHint` **không tự khiến `String` cấm giá trị `null`**. Java không áp dụng kiểm tra nullability chỉ vì có annotation tùy chỉnh. Muốn kiểm tra, cần annotation processor, static analyzer, validation framework hoặc logic runtime được thiết kế để hiểu marker ấy.

## 4. Ví dụ Java 17+ hoàn chỉnh: truy vấn type annotation

Tạo tệp **`TypeUseLocationsDemo.java`**. Chương trình minh họa ba vị trí chính và cả một vị trí type argument trong generic; các annotation có retention `RUNTIME` để Reflection đọc được.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface TypeMark {
    String value();
}

class DocumentStore {
    private @TypeMark("field-type") String id;

    private List<@TypeMark("generic-argument") String> labels;

    public @TypeMark("return-type") String find(
            @TypeMark("parameter-type") String key) {
        return key;
    }
}

public class TypeUseLocationsDemo {
    private static void printMark(String label, AnnotatedType type) {
        TypeMark mark = type.getAnnotation(TypeMark.class);
        System.out.println(label + ": "
                + (mark == null ? "(none)" : mark.value()));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field idField = DocumentStore.class.getDeclaredField("id");
        printMark("Field type", idField.getAnnotatedType());

        Method find = DocumentStore.class
                .getDeclaredMethod("find", String.class);
        printMark("Parameter type",
                find.getAnnotatedParameterTypes()[0]);
        printMark("Return type",
                find.getAnnotatedReturnType());

        Field labelsField = DocumentStore.class
                .getDeclaredField("labels");
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) labelsField.getAnnotatedType();
        printMark("Generic argument",
                listType.getAnnotatedActualTypeArguments()[0]);

        System.out.println("Field declaration: "
                + idField.isAnnotationPresent(TypeMark.class));
        System.out.println("Method declaration: "
                + find.isAnnotationPresent(TypeMark.class));
    }
}
```

Biên dịch/chạy bằng JDK 17+ trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 TypeUseLocationsDemo.java
java TypeUseLocationsDemo
```

Stdout:

```text
Field type: field-type
Parameter type: parameter-type
Return type: return-type
Generic argument: generic-argument
Field declaration: false
Method declaration: false
```

### Phân tích từng dòng

- `idField.getAnnotatedType()` đọc `@TypeMark("field-type")` ở **kiểu field**.
- `find.getAnnotatedParameterTypes()[0]` đọc `@TypeMark("parameter-type")` ở **kiểu tham số thứ nhất**.
- `find.getAnnotatedReturnType()` đọc `@TypeMark("return-type")` ở **kiểu trả về**.
- `labelsField.getAnnotatedType()` mô tả kiểu `List<String>`. Vì đây là một parameterized type, có thể ép về `AnnotatedParameterizedType` rồi lấy `getAnnotatedActualTypeArguments()[0]`: đây là phần tử kiểu `String` bên trong `List<...>`.
- `idField.isAnnotationPresent(TypeMark.class)` bằng `false` vì loại `TypeMark` **chỉ nhắm `TYPE_USE`**, không nhắm declaration `FIELD`.
- `find.isAnnotationPresent(TypeMark.class)` bằng `false` vì annotation trên **return type** không phải annotation trên **method declaration**.

Không có trường hợp nào trong ví dụ làm cho `find` được gọi; ta chỉ đọc thông tin kiểu. Hai field không cần được khởi tạo vì code không truy xuất **giá trị field**. Consumer của ví dụ là các lời gọi Reflection trong `main`, không phải một framework tự thực thi.

Nếu bỏ `@Retention(RetentionPolicy.RUNTIME)`, mặc định retention của annotation tự định nghĩa là `CLASS`; dữ liệu annotation trên các kiểu không còn được phản ánh qua các API Reflection runtime thường dùng. Vì vậy `RUNTIME` ở đây là điều kiện cần để minh họa cách truy xuất metadata tại runtime.

## 5. Type annotation trên kiểu field khác giá trị bên trong field

Một type-use annotation không phải một đối tượng “dính theo” dữ liệu runtime. Xem ví dụ:

```java
class Inventory {
    @TypeMark("part-code")
    String codeA;

    String codeB;
}
```

Hai field đều có kiểu Java là `String`; annotation mô tả **cách sử dụng kiểu ở khai báo `codeA`**, không định nghĩa một class `String` hoàn toàn mới. Cùng một giá trị `String` có thể được gán vào cả hai field (nếu code khác cho phép), và không tự phát sinh lỗi chỉ vì marker này.

Ví dụ đầy đủ ở mục 4 cho phép người đọc thấy metadata theo **từng field và method signature**: `@TypeMark("field-type")` thuộc cách dùng `String` ở `DocumentStore.id`, trong khi `@TypeMark("parameter-type")` thuộc kiểu của tham số `key` tại chữ ký method `find`.

Nếu bạn cần luật kiểu “`email` không được null”, hãy quyết định rõ bên xử lý nào áp dụng luật đó. Ví dụ, static analysis có thể cảnh báo tại compile-time, còn runtime validation sẽ cần code được gọi trước lúc dùng dữ liệu. Java SE không tự áp đặt ý nghĩa `NonNullHint` từ tên marker.

## 6. Trường hợp generic: `List<@TypeMark String>`

`TYPE_USE` không chỉ dùng ở ba vị trí bên ngoài. Nó cũng có thể mô tả một **thành phần kiểu nằm sâu trong biểu thức kiểu**:

```java
import java.util.List;

class Report {
    List<@TypeMark("item-type") String> items;
}
```

Ở đây `List` là **kiểu container bên ngoài**; `String` là **type argument**. Annotation gắn vào `String` bên trong dấu `<...>`, không phải tự động lên `List` hoặc field `items`.

Vì vậy:

- `field.getAnnotatedType()` trả về thông tin của kiểu field `List<String>` ở mức ngoài.
- Sau khi kiểm tra đối tượng có kiểu `AnnotatedParameterizedType`, dùng `getAnnotatedActualTypeArguments()` để lấy các kiểu đối số kèm annotation.
- Đối tượng `AnnotatedType` của đối số `String` có thể trả về `@TypeMark("item-type")` qua `getAnnotation(TypeMark.class)`.

Bên xử lý metadata trong generic cần **đi đúng cấu trúc kiểu**. Nếu chỉ kiểm tra `field.getAnnotation(TypeMark.class)`, nó sẽ bỏ qua thông tin sâu bên trong type argument.

Tương tự, với kiểu mảng, vị trí annotation trước tên kiểu thành phần và annotation trên từng mức mảng có thể khác nhau. Hãy dùng `AnnotatedArrayType` và `getAnnotatedGenericComponentType()` khi cần quan sát cấu trúc đó; bài này tập trung vào field, parameter và return type.

## 7. `TYPE_USE` khác `TYPE` và `TYPE_PARAMETER`

| Đích | Ý nghĩa trọng tâm | Ví dụ |
| --- | --- | --- |
| `ElementType.TYPE` | Gắn lên khai báo class, interface, enum, annotation type hoặc record | `@EntityLike class Order {}` |
| `ElementType.TYPE_USE` | Gắn ở vị trí sử dụng kiểu | `@TypeMark("x") String id;`, `List<@TypeMark("x") String>` |
| `ElementType.TYPE_PARAMETER` | Gắn trên **khai báo** tham số kiểu | `class Box<@ParameterTag T> {}` |

Các ví dụ trong bảng mang tính minh họa và cần định nghĩa các loại annotation tương ứng.

Chữ `TYPE` trong `TYPE_USE` không có nghĩa chỉ gắn lên **khai báo class**; nó nói đến *type contexts* như kiểu field, tham số, return, cast, generic type argument và một số ngữ cảnh khác được Java cho phép. Hơn nữa, `TYPE_USE` cũng áp dụng tại các vị trí khai báo kiểu/tham số kiểu nhất định theo quy tắc ngôn ngữ; điều này không biến nó thành đồng nghĩa với `TYPE` hoặc `TYPE_PARAMETER` trong mọi tình huống. Luôn xác định vị trí cụ thể mà bạn muốn hỗ trợ.

Nếu chỉ muốn annotation được viết trên class declaration, `@Target(TYPE)` diễn đạt ý định trực tiếp hơn. Nếu muốn chú thích **kiểu return** của method, `@Target(TYPE_USE)` là đích phù hợp. Nếu muốn đánh dấu chính method declaration, chọn `@Target(METHOD)`.

## 8. Annotation dùng ở type context: compiler, runtime và công cụ kiểm tra

Việc một annotation có thể xuất hiện trên `String` hoặc `List<String>` không đồng nghĩa compiler luôn biết ý nghĩa của nó. Có ba bước riêng:

1. **Java kiểm tra cú pháp và vị trí**: `@Target(TYPE_USE)` cho phép các vị trí type-use hợp lệ, compiler kiểm tra các phần tử metadata đúng kiểu.
2. **Chính sách lưu giữ**: `@Retention(SOURCE)` cho phép processor/analyzer làm việc ở compile-time; `CLASS` giữ metadata trong bytecode nhưng Reflection thông thường không xem được; `RUNTIME` cho phép các API Reflection hỗ trợ annotated types truy xuất được.
3. **Bên xử lý diễn giải ý nghĩa**: một static checker có thể hiểu `@NonNull`, thư viện serialization có thể đọc type annotations hoặc framework có thể định tuyến xử lý riêng. Nếu không có bên tiêu thụ, annotation chỉ còn là metadata.

Một số annotation trong các thư viện validation/nullability có tên gần giống nhau nhưng khác nhau về `@Target`, `@Retention` và cơ chế xử lý. Không nên dựa vào tên `NonNull`/ `Nullable` để suy rằng annotation chắc chắn áp dụng ở type use hoặc chắc chắn được Java kiểm tra.

### Một lưu ý về Reflection

API `getAnnotatedType()` và các API liên quan biểu diễn annotation nằm ở **type use**. Các API `getAnnotations()` trực tiếp trên `Class`, `Method`, `Field` hay `Parameter` có mục đích khác; chúng không phải cơ chế mặc định để duyệt toàn bộ cây kiểu lồng nhau.

Nếu metadata nằm trong `Map<@A String, List<@B Item>>`, consumer cần truy cập kiểu generic và đi vào các đối số type tương ứng để đọc đầy đủ. Đọc “annotation của declaration” và đọc “annotation của type tree” là hai thao tác độc lập.

## 9. Những lỗi phổ biến

**Lỗi 1: Xem `@Target(TYPE_USE)` như một cách đổi hệ thống kiểu Java.** Annotation không tự tạo kiểu mới và không khiến compiler mặc định cấm null. Cần có bên xử lý hiểu metadata.

**Lỗi 2: Lấy `Field.getAnnotation` để đọc annotation chỉ gắn ở field type.** Chọn `Field.getAnnotatedType()`, rồi đọc từ `AnnotatedType`.

**Lỗi 3: Lấy `Method.getAnnotation` để đọc annotation return type.** Chọn `Method.getAnnotatedReturnType()`.

**Lỗi 4: Lấy `Method.getParameterAnnotations()` để đọc annotation trên type argument của một tham số generic.** Cần `getAnnotatedParameterTypes()` và đi tiếp vào cấu trúc annotated type nếu cần.

**Lỗi 5: Nghĩ `FIELD`, `PARAMETER`, `METHOD` tương đương `TYPE_USE`.** Những đích này mô tả các loại declaration, còn `TYPE_USE` nói tới các vị trí xuất hiện kiểu.

**Lỗi 6: Quên retention khi kiểm tra runtime.** Annotation tự định nghĩa mặc định `CLASS`; muốn Reflection runtime đọc được thì cần `RUNTIME`.

**Lỗi 7: Nghĩ gắn annotation vào `List<@Mark String>` là đánh dấu trực tiếp field `List`.** Marker nằm trên đối số kiểu `String`, nên consumer phải duyệt `AnnotatedParameterizedType`.

**Lỗi 8: Bỏ qua `@Target` của loại annotation thực tế.** Annotation được một framework cho phép trên method declaration chưa chắc được phép đặt trên kiểu return, dù nhìn trong source rất gần nhau.

## 10. Bài tập tự kiểm tra

**Câu 1.** Với `@Target(TYPE_USE) @interface Mark {}`, biểu thức `private @Mark String name;` đánh dấu gì?

Đáp án: **Kiểu `String` tại vị trí field `name`**, không tự động đánh dấu mọi giá trị `String` trong chương trình.

**Câu 2.** Một annotation chỉ có `@Target(METHOD)` có thể đặt trên `List<@Mark String>` không?

Đáp án: **Không.** Đó là type argument, cần annotation hỗ trợ `TYPE_USE`.

**Câu 3.** Bạn gắn `@TypeMark` lên kiểu trả về của `load()`. Dùng `method.getAnnotation(TypeMark.class)` có chắc tìm được nó không?

Đáp án: **Không.** Với annotation chỉ hỗ trợ `TYPE_USE`, hãy dùng `method.getAnnotatedReturnType().getAnnotation(TypeMark.class)`.

**Câu 4.** `@TypeMark` trên kiểu tham số đầu tiên của method được truy xuất qua API nào?

Đáp án: `method.getAnnotatedParameterTypes()[0]` rồi đọc annotation trên đối tượng `AnnotatedType` đó.

**Câu 5.** Với `List<@TypeMark("element") String>`, tại sao truy cập trực tiếp `field.getAnnotatedType().getAnnotation(TypeMark.class)` thường không thấy `"element"`?

Đáp án: Vì marker ở **type argument `String`**, không ở kiểu ngoài `List`. Phải dùng `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.

**Câu 6.** Có thể dùng `@Target(TYPE_USE)` kết hợp `@Retention(SOURCE)` không?

Đáp án: **Có.** Target nói annotation được phép gắn ở đâu, retention nói metadata tồn tại đến giai đoạn nào. Khi là `SOURCE`, static analyzer/processor có thể đọc ở compile-time nhưng runtime Reflection không nhìn thấy.

**Câu 7.** Gắn `@NonNullHint` chỉ có `TYPE_USE` lên `String` có khiến `String name = null;` chắc chắn bị javac từ chối không?

Đáp án: **Không.** Annotation tự định nghĩa không tự có cơ chế kiểm tra null; cần công cụ hoặc processor thực sự hiểu và áp dụng quy tắc.

**Câu 8.** Vì sao chương trình `TypeUseLocationsDemo` in `Field declaration: false` nhưng lại in `Field type: field-type`?

Đáp án: Vì hai API hỏi hai vị trí metadata **khác nhau**: declaration `FIELD` và type use của `String`.

Điểm cần nhớ: **`TYPE_USE` đánh dấu vị trí sử dụng kiểu**, còn annotation gắn trên chính declaration dùng những đích như `FIELD`, `PARAMETER`, `METHOD`. Để đọc type annotation bằng Reflection, hãy lấy `AnnotatedType` tại đúng vị trí field, tham số hoặc kiểu trả về; với generic/array, tiếp tục đi vào cây kiểu nếu metadata nằm ở cấp sâu hơn.
