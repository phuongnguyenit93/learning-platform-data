# Kiểm thử ma trận `@Target` và `@Retention` trong Java

## 1. Vì sao cần kiểm thử theo ma trận?

Khi xây dựng annotation tùy chỉnh, hai meta-annotation quyết định những đặc tính độc lập:

- **`@Target`** trả lời: annotation được **đặt ở những vị trí Java nào**? Compiler kiểm tra điều này ngay khi biên dịch.
- **`@Retention`** trả lời: thông tin annotation được **giữ đến giai đoạn nào**? Nó ảnh hưởng tới mã nguồn, dữ liệu trong `.class` và khả năng đọc bằng Reflection.

Một annotation đúng vị trí vẫn có thể “biến mất” khi chạy chương trình nếu retention không phải `RUNTIME`. Ngược lại, một annotation dùng `RUNTIME` vẫn **không thể biên dịch** khi gắn sai `@Target`.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {
}
~~~

`@Traced` được phép trên khai báo method và có thể đọc bằng Reflection sau biên dịch. Nhưng:

~~~java
// Mã SAI, chỉ minh họa negative test:
// @Traced
// class WrongPlace {}
~~~

sẽ bị compiler từ chối. **`RUNTIME` không mở rộng các vị trí hợp lệ của `METHOD`.**

Để kiểm thử đáng tin cậy, không nên chỉ viết một đoạn chạy thành công. Cần có một **ma trận dương/âm** theo `ElementType`, một **ma trận ba retention policies**, và ba phương pháp kiểm chứng:

1. **Compile-time:** dùng `javac` xác nhận mẫu hợp lệ biên dịch thành công, mẫu sai vị trí bị từ chối.
2. **Class-file level:** dùng `javap -v` xác nhận metadata thực sự được lưu hoặc loại bỏ.
3. **Runtime:** dùng Reflection để xác nhận những annotation cần thiết được đọc đúng API.

Đây là cách tách biệt lỗi **khai báo target**, lỗi **retention** và lỗi **đọc metadata sai API**.

## 2. Ma trận `ElementType` trong Java 17

Java SE 17 có **12 hằng `ElementType`**. Mỗi hằng có loại vị trí sử dụng tiêu biểu và các phép thử khác nhau.

| `ElementType` | Vị trí thử hợp lệ (positive test) | Vị trí sai cần thử (negative test) |
| --- | --- | --- |
| `TYPE` | `@A class C {}`, interface, enum, record | Phần tử type argument như `List<@A String>` nếu chỉ hỗ trợ `TYPE` |
| `FIELD` | `@A String field;` | `@A void method() {}` |
| `METHOD` | `@A void execute() {}` | `@A class C {}` |
| `PARAMETER` | `void run(@A String value) {}` | `@A String field;` |
| `CONSTRUCTOR` | `@A C() {}` | `@A void method() {}` |
| `LOCAL_VARIABLE` | `@A int n = 1;` trong method | Field hoặc method declaration |
| `ANNOTATION_TYPE` | `@A @interface Flag {}` | Class thông thường |
| `PACKAGE` | Annotation đặt trước `package ...;` trong `package-info.java` | Class declaration |
| `TYPE_PARAMETER` | `class Box<@A T> {}` | Type argument `List<@A String>` nếu chỉ hỗ trợ `TYPE_PARAMETER` |
| `TYPE_USE` | `List<@A String>`, kiểu field, cast, array component... | Các **declaration-only** contexts không thuộc phạm vi `TYPE_USE`, ví dụ annotation của package |
| `MODULE` | Trước `module ... {}` trong `module-info.java` | Class declaration |
| `RECORD_COMPONENT` | `record Item(@A String id) {}` | Field thường nếu chỉ hỗ trợ `RECORD_COMPONENT` |

**Đây là bảng lập kế hoạch kiểm thử**, chưa phải mã nguồn chung một file: `@A` là ký hiệu thay thế cho annotation type tương ứng, và mỗi negative test được biên dịch **riêng**, không trộn với các ví dụ hợp lệ.

### 2.1. Hai ngoại lệ quan trọng về `TYPE_USE`

`TYPE` nghĩa là **khai báo kiểu** như class/interface, không phải mọi nơi có tên `String`. `TYPE_USE` nghĩa là **một lần sử dụng kiểu**, ví dụ kiểu làm type argument của generic.

Tuy nhiên, theo JLS, `@Target(TYPE_USE)` cũng cho phép một số vị trí **khai báo class/interface** và **khai báo type parameter**. Vì vậy không được làm negative test kiểu “`@A class C {}` với `@Target(TYPE_USE)` chắc chắn bị lỗi”; giả định đó sai.

Để kiểm thử `TYPE_USE` chắc chắn, dùng một kiểu nằm **bên trong generic**:

~~~java
import java.util.List;

class Example {
    List<@A String> names;
}
~~~

Nếu `@A` có `@Target(TYPE_USE)`, vị trí trên hợp lệ. Nếu nó **chỉ** có `@Target(FIELD)`, vị trí type argument đó không hợp lệ.

### 2.2. `TYPE_PARAMETER` khác `PARAMETER`

`PARAMETER` áp dụng cho tham số hình thức của method/constructor, còn `TYPE_PARAMETER` áp dụng cho biến kiểu generic như `T`. Một `T` trong `class Box<T>` **không** phải tham số của một lời gọi phương thức.

Dùng hai test khác nhau:

~~~java
class GenericBox<@A T> {
}

class Service {
    void send(@A String message) {
    }
}
~~~

Mỗi fragment cần định nghĩa `@A` với target tương ứng. Đừng dùng một annotation `@Target(PARAMETER)` để đánh dấu `T` rồi coi lỗi compile là lỗi Java generics.

### 2.3. Record component và propagation

`RECORD_COMPONENT` là target riêng từ Java 16. Một record component có liên hệ tới field, accessor và constructor parameter được tạo ra, nhưng annotation đặt trên component **không mặc nhiên có mặt ở mọi khai báo liên quan**.

Khi test record, nên kiểm tra trực tiếp qua:

~~~java
recordClass.getRecordComponents()[0]
           .isAnnotationPresent(YourAnnotation.class);
~~~

Đây là fragment dùng một `Class<?> recordClass` và annotation type `YourAnnotation` đã khai báo, **không phải chương trình độc lập**. Nếu cần kiểm tra propagation sang field/accessor/parameter, phải thiết lập `@Target` tương ứng và kiểm thử riêng quy tắc JLS.

## 3. Ma trận `@Retention`: ba giai đoạn quan sát

`java.lang.annotation.RetentionPolicy` định nghĩa ba chính sách:

| Chính sách | Trong source/annotation processing | Trong class file sau `javac` | Reflection runtime chuẩn |
| --- | --- | --- | --- |
| `SOURCE` | Có thể được processor xử lý lúc biên dịch | Không giữ ở nơi sử dụng | Không nhìn thấy |
| `CLASS` | Có thể được processor xử lý | Giữ dưới metadata không dành cho runtime reflection | Không nhìn thấy |
| `RUNTIME` | Có thể được processor xử lý | Giữ dưới metadata có thể đọc tại runtime | Có thể nhìn thấy bằng API đúng |

Một annotation type **không khai báo `@Retention`** có retention mặc định là **`CLASS`**, không phải `RUNTIME`.

Ví dụ:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeMark {}

@Target(ElementType.TYPE)
@interface DefaultMark {} // Retention mặc định: CLASS.
~~~

Tất cả các định nghĩa trên đều hợp lệ. Nếu bốn annotation này cùng đặt trên một class, `javac` phải chấp nhận về **target**, nhưng chúng có **retention khác nhau**.

### 3.1. Quan sát ở `.class` bằng `javap -v`

Với annotation được gắn trực tiếp trên một class và `javac` Java 17:

- `SOURCE`: không có thông tin lần sử dụng annotation đó trong class file.
- `CLASS`: thường nằm dưới thuộc tính `RuntimeInvisibleAnnotations`.
- `RUNTIME`: thường nằm dưới thuộc tính `RuntimeVisibleAnnotations`.

`DefaultMark` cũng thuộc nhóm `CLASS` vì không có `@Retention`.

Tên các thuộc tính trên là **tên trong class-file format**, không phải API Java giúp runtime Reflection đọc `CLASS`. Một công cụ bytecode chuyên dụng vẫn có thể đọc `RuntimeInvisibleAnnotations` từ file, nhưng `Class.getAnnotation()` không được dùng để đọc nhóm này.

### 3.2. Đọc Runtime Reflection: dùng đúng đường

Tại runtime:

~~~java
type.getAnnotation(RuntimeMark.class);
type.isAnnotationPresent(RuntimeMark.class);
~~~

có thể thấy annotation RUNTIME trên type, nhưng:

~~~java
type.getAnnotation(SourceMark.class); // null
type.getAnnotation(ClassMark.class);  // null
~~~

không nhìn thấy SOURCE hoặc CLASS. Hai dòng là fragment với biến `Class<?> type`.

**Không có `RUNTIME` không có nghĩa annotation không từng được compiler nhìn thấy.** Annotation processors thường hoạt động trên source trước khi compiler bỏ retention SOURCE, nên đây là hai bước kiểm thử độc lập.

## 4. Số lượng testcase: không chỉ nhân máy móc 12 × 3

Có **12 target types × 3 retention policies = 36 cặp khái niệm**, nhưng không nhất thiết phải viết 36 file thử khác nhau cho một module nhỏ.

Thiết kế hợp lý theo **test partitioning**:

1. Một positive test cho mỗi loại target, được compile bằng `javac`.
2. Một negative test đặt cùng annotation vào một **ngữ cảnh chắc chắn không được phép**.
3. Với một target hỗ trợ Reflection dễ kiểm chứng như `TYPE`, chạy đủ `SOURCE`, `CLASS`, `RUNTIME` và **retention mặc định**.
4. Dùng thêm test runtime cho `FIELD`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, `TYPE_USE`, `TYPE_PARAMETER`, `RECORD_COMPONENT`.
5. Dùng test class-file-level cho `CLASS` và đặc biệt cho những metadata **không có runtime Reflection API tổng quát**, chẳng hạn annotation trên local variable declaration.
6. Với `PACKAGE`, `MODULE`, dùng các file cấu trúc riêng thay vì ép vào một file Java có `main`.

Mục tiêu không phải tạo số lượng test lớn nhất mà là **bao phủ những ranh giới ngữ nghĩa dễ sai**.

## 5. Chương trình Java 17 đầy đủ kiểm tra nhiều target và retention

Tạo một file duy nhất tên **`AnnotationMatrixDemo.java`**. Chương trình chạy độc lập, không cần thư viện ngoài JDK.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeMark {}

@Target(ElementType.TYPE)
@interface DefaultMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.CONSTRUCTOR)
@interface ConstructorMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeUseMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.LOCAL_VARIABLE)
@interface LocalMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface RecordComponentMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface AnnotationTypeMark {}

@AnnotationTypeMark
@interface MetaAnnotated {}

@SourceMark
@ClassMark
@RuntimeMark
@DefaultMark
class MatrixSample<@TypeParameterMark T> {
    @FieldMark
    private @TypeUseMark String name = "ok";

    private List<@TypeUseMark String> tags = List.of("a");

    @ConstructorMark
    MatrixSample() {}

    @MethodMark
    void execute(@ParameterMark String input) {
        @LocalMark int attempts = 1;
        if (attempts < 0) {
            throw new AssertionError(input);
        }
    }
}

record MatrixRecord(@RecordComponentMark String id) {}

public class AnnotationMatrixDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = MatrixSample.class;
        Field name = type.getDeclaredField("name");
        Field tags = type.getDeclaredField("tags");
        Method execute = type.getDeclaredMethod("execute", String.class);

        AnnotatedParameterizedType tagType =
                (AnnotatedParameterizedType) tags.getAnnotatedType();

        System.out.println("SOURCE visible: "
                + type.isAnnotationPresent(SourceMark.class));
        System.out.println("CLASS visible: "
                + type.isAnnotationPresent(ClassMark.class));
        System.out.println("RUNTIME visible: "
                + type.isAnnotationPresent(RuntimeMark.class));
        System.out.println("DEFAULT visible: "
                + type.isAnnotationPresent(DefaultMark.class));

        System.out.println("FIELD declaration: "
                + name.isAnnotationPresent(FieldMark.class));
        System.out.println("FIELD type use: "
                + name.getAnnotatedType()
                      .isAnnotationPresent(TypeUseMark.class));
        System.out.println("GENERIC type argument: "
                + tagType.getAnnotatedActualTypeArguments()[0]
                         .isAnnotationPresent(TypeUseMark.class));

        System.out.println("METHOD declaration: "
                + execute.isAnnotationPresent(MethodMark.class));
        System.out.println("PARAMETER declaration: "
                + execute.getParameters()[0]
                         .isAnnotationPresent(ParameterMark.class));
        System.out.println("CONSTRUCTOR declaration: "
                + type.getDeclaredConstructor()
                      .isAnnotationPresent(ConstructorMark.class));
        System.out.println("TYPE_PARAMETER declaration: "
                + type.getTypeParameters()[0]
                      .isAnnotationPresent(TypeParameterMark.class));
        System.out.println("RECORD_COMPONENT declaration: "
                + MatrixRecord.class.getRecordComponents()[0]
                      .isAnnotationPresent(RecordComponentMark.class));
        System.out.println("ANNOTATION_TYPE declaration: "
                + MetaAnnotated.class
                      .isAnnotationPresent(AnnotationTypeMark.class));
    }
}
~~~

Chạy từ thư mục chứa file, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 AnnotationMatrixDemo.java
java AnnotationMatrixDemo
~~~

**Stdout chính xác:**

~~~text
SOURCE visible: false
CLASS visible: false
RUNTIME visible: true
DEFAULT visible: false
FIELD declaration: true
FIELD type use: true
GENERIC type argument: true
METHOD declaration: true
PARAMETER declaration: true
CONSTRUCTOR declaration: true
TYPE_PARAMETER declaration: true
RECORD_COMPONENT declaration: true
ANNOTATION_TYPE declaration: true
~~~

### 5.1. Tại sao các dòng đầu có false/true như vậy?

`MatrixSample` mang bốn annotation `SourceMark`, `ClassMark`, `RuntimeMark`, `DefaultMark` đều có target `TYPE`, nên chúng **cùng vượt qua compile-time target check**.

Tuy nhiên, Reflection ở runtime chỉ thấy `RuntimeMark`. `SourceMark` đã bị loại vì `SOURCE`; `ClassMark` được giữ trong class file nhưng không dành cho Reflection; `DefaultMark` có retention mặc định `CLASS`, nên cũng không hiện qua `Class.isAnnotationPresent`.

Kết quả này **không nói** `SourceMark` “không tồn tại”; nó vẫn là annotation type có thể được compiler và annotation processor nhận biết.

### 5.2. Phân biệt field declaration và field type

`MatrixSample.name` có hai annotation với hai target khác nhau:

~~~java
@FieldMark
private @TypeUseMark String name = "ok";
~~~

`FieldMark` thuộc **khai báo field**, đọc qua `Field.isAnnotationPresent(FieldMark.class)`.

`TypeUseMark` thuộc **kiểu `String` của field**, đọc qua `Field.getAnnotatedType().isAnnotationPresent(TypeUseMark.class)`.

Nếu test chỉ gọi `Field.getAnnotation(TypeUseMark.class)`, bạn đang thử **sai API** và có thể kết luận nhầm rằng retention RUNTIME không hoạt động. Kết quả âm khi đọc sai vị trí **không phải bằng chứng** compiler làm mất annotation.

### 5.3. Kiểm thử generic type argument

`List<@TypeUseMark String>` đặt annotation trên **type argument `String`**, không phải khai báo field `tags`. Đó là lý do ví dụ dùng `AnnotatedParameterizedType` và lấy `getAnnotatedActualTypeArguments()[0]`.

Nếu annotation chỉ có `TYPE_PARAMETER`, nó phù hợp với khai báo `<T>` của `MatrixSample`, nhưng **không hợp lệ** tại `List<@A String>` khi `String` là type argument.

### 5.4. Kiểm thử record và annotation type

`MatrixRecord` dùng `RECORD_COMPONENT`, đọc bằng `Class.getRecordComponents()`. Đừng chỉ kiểm tra synthetic/implicit field hoặc accessor của record rồi cho rằng đó là test trực tiếp của record component.

`@AnnotationTypeMark` nằm trên khai báo `@interface MetaAnnotated`, đúng target `ANNOTATION_TYPE`. Nó không tự đánh dấu các class mang `@MetaAnnotated`.

### 5.5. Tại sao `LOCAL_VARIABLE` không có dòng runtime?

`@LocalMark` hợp lệ trên khai báo biến cục bộ `attempts` nên chương trình **biên dịch thành công**. Nhưng Reflection chuẩn không có `LocalVariable.getAnnotation()` để duyệt annotation trên mọi biến local trong bytecode.

Ngay cả khi `@LocalMark` dùng `RUNTIME`, không nên viết assertion “runtime reflection phải nhìn thấy LocalMark trên local variable”. **Target hợp lệ** và **API có thể truy cập tại runtime** không đồng nghĩa. Type-use annotation trên kiểu trong local variable là cơ chế khác, có quy tắc lưu trong class file riêng.

## 6. Kiểm thử retention bằng `javap -v`

Sau khi biên dịch chương trình ở phần 5, chạy:

~~~bash
javap -v MatrixSample
~~~

Tìm các thuộc tính được sinh cho annotation gắn trực tiếp trên **class MatrixSample**:

- `RuntimeVisibleAnnotations`: bao gồm `RuntimeMark`.
- `RuntimeInvisibleAnnotations`: bao gồm `ClassMark` và `DefaultMark`.
- `SourceMark`: **không được giữ** làm annotation trên class trong `MatrixSample.class`.

Những phần tử như `TypeUseMark` còn có thể xuất hiện trong `RuntimeVisibleTypeAnnotations`, vì đó là **type-use metadata**, không phải annotation declaration trên class. Class-file format phân biệt nhiều thuộc tính; khi kiểm tra phải tìm đúng **phần tử được chú thích** và đúng **vị trí metadata**.

### Tại sao `javap` và Reflection cần kiểm thử tách biệt?

- `javap -v` là công cụ **kiểm tra thông tin class-file**, giúp phát hiện annotation được giữ trong bytecode dù Reflection không đọc nó.
- Reflection chỉ đưa những annotation đã được giữ tới runtime thông qua **API thích hợp**.
- Một annotation `CLASS` xuất hiện trong `RuntimeInvisibleAnnotations` là kết quả **đúng**, không phải compiler lỗi vì Reflection trả `null`.
- Với `SOURCE`, Reflection trả `null` là đúng; việc không có metadata ở nơi sử dụng trong `.class` cũng đúng.

Không nên ghép việc test `SOURCE` với runtime-only reflection rồi kỳ vọng kết quả dương.

## 7. Negative tests: cố ý tạo mã sai target

Negative tests phải được **biên dịch riêng** và kỳ vọng `javac` trả mã thoát khác 0. Không trộn vào `AnnotationMatrixDemo.java`, vì như vậy sẽ khiến positive tests cũng không thể chạy.

Sau khi biên dịch file ở phần 5, tạo từng file dưới đây trong cùng thư mục. Các annotation types trong demo đều package-private ở **unnamed package**, nên đoạn test cùng thư mục/package có thể tham chiếu chúng.

### 7.1. Sai target `METHOD` trên class

Tệp **`WrongClass.java`**:

~~~java
@MethodMark
class WrongClass {
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 -cp . WrongClass.java
~~~

**Kỳ vọng:** biên dịch **thất bại** vì `MethodMark` chỉ hỗ trợ `ElementType.METHOD`, không phải class declaration.

### 7.2. Sai target `FIELD` trên type argument

Tệp **`WrongTypeArgument.java`**:

~~~java
import java.util.List;

class WrongTypeArgument {
    List<@FieldMark String> values;
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 -cp . WrongTypeArgument.java
~~~

**Kỳ vọng:** thất bại, vì `@FieldMark` thuộc field declaration, không phải kiểu `String` ở type argument.

### 7.3. Sai `PARAMETER` trên type parameter

Tệp **`WrongTypeParameter.java`**:

~~~java
class WrongTypeParameter<@ParameterMark T> {
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 -cp . WrongTypeParameter.java
~~~

**Kỳ vọng:** thất bại vì `T` là **type parameter**, không phải formal parameter. `@TypeParameterMark T` mới là bài test đúng.

### 7.4. Sai `METHOD` trên constructor

Tệp **`WrongConstructor.java`**:

~~~java
class WrongConstructor {
    @MethodMark
    WrongConstructor() {
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 -cp . WrongConstructor.java
~~~

**Kỳ vọng:** thất bại vì constructor declaration cần `ElementType.CONSTRUCTOR`, không phải `METHOD`.

### Cách viết test tự động

Có thể dùng JUnit, Gradle compile-testing hoặc `JavaCompiler` API của JDK để kiểm tra **mã thoát biên dịch** và category của diagnostic. Với một bài kiểm thử đơn giản, điều bắt buộc không phải so khớp đúng **toàn bộ thông báo lỗi** (vì wording có thể khác giữa JDK releases và locale), mà là:

- Positive sample: **exit code = 0**.
- Negative sample: **exit code khác 0**.
- Lỗi đến từ target không hợp lệ, **không phải** do file thiếu annotation definition, sai classpath, sai Java source level hay typo không liên quan.

Nếu dùng shell script, nên biên dịch các negative snippets **từng file** và assert riêng, để một lỗi không che những testcase khác.

## 8. Test `PACKAGE` và `MODULE` cần cấu trúc file đặc biệt

Hai target này không nên nhét vào một class có `main`, vì cú pháp Java yêu cầu nơi khai báo khác.

### `ElementType.PACKAGE`

Một dự án có thể có hai tệp riêng trong `src/demo/api/`:

**`PackageTag.java`**:

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackageTag {
}
~~~

**`package-info.java`**:

~~~java
@PackageTag
package demo.api;
~~~

Đây là **fragment dự án nhiều tệp**, không phải phần của `AnnotationMatrixDemo.java`. Trong cùng package, `@PackageTag` được dùng mà không cần import. Nếu chỉ gắn `@PackageTag` trên class bình thường sẽ xảy ra lỗi target.

Biên dịch từ thư mục chứa `src`:

~~~bash
javac -encoding UTF-8 -d out src/demo/api/PackageTag.java src/demo/api/package-info.java
~~~

Khi retention là `RUNTIME`, có thể dùng `Package.getPackage` trong ngữ cảnh thích hợp hoặc `SomeClass.class.getPackage().isAnnotationPresent(PackageTag.class)` khi đã có class ở package đó. Để tránh phụ thuộc vào package chưa có class nào được nạp, bài test nên đưa thêm một class public vào package rồi lấy `Class.getPackage()` của nó.

### `ElementType.MODULE`

Annotation trên module phải nằm tại khai báo `module` trong **`module-info.java`** của Java Platform Module System.

Ví dụ hình thức, **không phải chương trình một file độc lập**:

~~~java
@demo.api.ModuleTag
module demo.application {
}
~~~

`demo.api.ModuleTag` phải có `@Target(ElementType.MODULE)` và hiện diện hợp lệ trong module graph; project phải có bố cục module và compiler options phù hợp. Mục tiêu của testcase là xác nhận **module declaration** được chú thích đúng target và kiểm tra metadata theo retention qua API module/class-file thích hợp. Dùng `@ModuleTag` trực tiếp trên class là negative test.

Đối với package/module, nên thiết kế **fixture project** thay vì cố đặt tất cả ví dụ vào file chính. Kiểm thử mô-đun có thể cần `--module-source-path`, `--module-path` hoặc lệnh compile nhiều module khác với test classpath thông thường.

## 9. Test annotation processing với retention `SOURCE`

Ma trận `SOURCE/CLASS/RUNTIME` chưa hoàn chỉnh nếu chỉ kiểm tra `javap` và Reflection. Nhiều annotation được thiết kế **chỉ dành cho annotation processor**.

Ví dụ marker:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateBuilder {
}
~~~

Một processor có thể lấy những `TypeElement` đã được gắn `@GenerateBuilder` trong compilation thông qua:

~~~java
roundEnv.getElementsAnnotatedWith(GenerateBuilder.class)
~~~

Đây là **fragment trong processor**, không phải đoạn chạy độc lập. Một integration test tốt:

1. Biên dịch và kích hoạt processor thật (qua `-processor` hoặc service).
2. Compile một class mang `@GenerateBuilder`, khẳng định processor báo diagnostic hợp lệ hoặc sinh file mong đợi.
3. Kiểm tra file được sinh tồn tại và compile thành công.
4. Kiểm tra Reflection runtime **không thấy `@GenerateBuilder`** trên class ban đầu, đúng retention `SOURCE`.

Nếu compiler không nạp processor, test “SOURCE annotation có được xử lý không” bị sai setup. **Retention SOURCE không phải nguyên nhân khiến processor không chạy**; nguyên nhân có thể là processorpath, registration, source level hoặc annotation type support.

## 10. Ma trận kiểm thử theo lớp và trường hợp

| Case | Đầu vào | Compile | Class file / Reflection |
| --- | --- | --- | --- |
| T1 | `@Target(METHOD)` trên method | Thành công | Nếu RUNTIME: `Method.isAnnotationPresent` true |
| T2 | `@Target(METHOD)` trên class | Thất bại | Không chạy Reflection |
| T3 | `@Target(FIELD)` trên type argument | Thất bại | Không chạy Reflection |
| T4 | `@Target(TYPE_USE)` trên `List<@A String>` | Thành công | Đọc qua `AnnotatedParameterizedType` khi RUNTIME |
| T5 | `@Target(TYPE_PARAMETER)` trên khai báo `T` | Thành công | Đọc qua `TypeVariable` khi RUNTIME |
| T6 | `@Target(RECORD_COMPONENT)` trên header record | Thành công | Đọc qua `RecordComponent` khi RUNTIME |
| R1 | `SOURCE` trên class | Thành công | Không có annotation use trong class file; Reflection false |
| R2 | `CLASS` trên class | Thành công | RuntimeInvisibleAnnotations; Reflection false |
| R3 | `RUNTIME` trên class | Thành công | RuntimeVisibleAnnotations; Reflection true |
| R4 | Không khai báo `@Retention` | Thành công | Mặc định CLASS; Reflection false |
| L1 | `@Target(LOCAL_VARIABLE)` trên local | Thành công | Không có API Reflection tổng quát cho declaration của local |
| P1 | `@Target(PACKAGE)` trên `package-info.java` | Thành công | Kiểm tra package metadata theo retention |
| M1 | `@Target(MODULE)` trên `module-info.java` | Thành công | Kiểm tra module metadata theo retention |

Đối với target phức tạp và `TYPE_USE`, cần bổ sung các case `RUNTIME` trên type annotations trong bytecode. Đừng suy luận mỗi `@Retention(RUNTIME)` đều phải được đọc qua **cùng một** `getAnnotation()` đặt trên `Class`: vị trí metadata quyết định API Reflection phù hợp.

## 11. Những lỗi thường gặp khi viết bộ test

**Lỗi 1 — chỉ test annotation hợp lệ, không test sai target.** Compiler có thể chấp nhận mọi code trong bộ test mà vẫn chưa xác nhận annotation bị giới hạn như thiết kế. Hãy dùng negative compile tests.

**Lỗi 2 — viết negative code chung với demo chạy được.** Một negative snippet có chủ ý sẽ làm cả dự án không thể biên dịch. Phải tách file/fixture hoặc test harness.

**Lỗi 3 — thấy `CLASS` không đọc được bằng Reflection rồi báo lỗi retention.** Đó là hành vi đúng. Kiểm tra bằng `javap -v` hoặc class-file reader.

**Lỗi 4 — giả định không khai báo `@Retention` thì mặc định RUNTIME.** Java mặc định CLASS.

**Lỗi 5 — nhầm `TYPE` với `TYPE_USE`.** `List<@A String>` là type argument; chỉ `TYPE` không đủ.

**Lỗi 6 — coi `TYPE_PARAMETER` và `PARAMETER` như nhau.** Generic `T` khác method/constructor parameter.

**Lỗi 7 — kiểm thử `@Target(TYPE_USE)` bằng một negative test trên class declaration.** Có những vị trí declaration được `TYPE_USE` cho phép; cần chọn ngữ cảnh thực sự ngoài phạm vi.

**Lỗi 8 — dùng `Field.getAnnotation` để kết luận một type-use annotation bị mất.** Phải đọc qua `Field.getAnnotatedType()`.

**Lỗi 9 — dùng `RUNTIME` trên local variable và mong tìm bằng Reflection thông thường.** Runtime retention không tạo API Reflection mới cho local declarations.

**Lỗi 10 — đồng nhất record component annotation với annotation trên accessor/field.** Test qua `RecordComponent`; nếu muốn kiểm tra propagation, test độc lập.

**Lỗi 11 — chỉ so khớp nguyên văn compiler error message.** Thông báo/locale có thể khác; kiểm tra mã thoát, mã lỗi nếu framework hỗ trợ, và đúng ngữ cảnh.

**Lỗi 12 — negative test thất bại do setup, nhưng vẫn được tính là PASS.** Phải xác định lỗi thật đến từ **target**; sai classpath hay thiếu source không chứng minh annotation giới hạn đúng.

**Lỗi 13 — bỏ qua processor discovery khi test SOURCE.** Annotation processor chỉ chạy khi compiler kích hoạt nó; test setup cần chỉ rõ `-processor` hoặc registration.

**Lỗi 14 — một test phụ thuộc thứ tự chạy Reflection hoặc thứ tự danh sách `getDeclaredMethods()`.** Nên truy vấn theo tên hoặc sort key rõ ràng; không dựa vào iteration order.

## 12. Checklist thiết kế test suite

Một bộ test ma trận vững nên có:

1. **Inventory target:** liệt kê các `ElementType` mà annotation type hỗ trợ và những vị trí cố tình không hỗ trợ.
2. **Positive compile tests:** ít nhất một ví dụ hợp lệ cho mỗi target liên quan.
3. **Negative compile tests:** ít nhất một ví dụ sai đúng bản chất target.
4. **Retention test:** SOURCE, CLASS, RUNTIME và trường hợp không khai báo `@Retention`.
5. **Class-file inspection:** phân biệt `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations` và `RuntimeVisibleTypeAnnotations` khi cần.
6. **Reflection path:** dùng `Class`, `Field`, `Method`, `Parameter`, `AnnotatedType`, `TypeVariable`, `RecordComponent` đúng ngữ cảnh.
7. **Special contexts:** package-info, module-info, record component, generic type argument và local declaration.
8. **Processor setup:** nếu SOURCE được tiêu thụ bởi annotation processor, xác nhận processor đã chạy và tạo kết quả.
9. **Java version:** xác định rõ JDK 17+; module, record, type-use có lịch sử phiên bản khác nhau.
10. **Negative-test isolation:** không cho một file cố tình sai phá positive suite.
11. **Stable assertions:** so boolean, exit status, loại metadata; tránh phụ thuộc message compiler chính xác.
12. **CI matrix:** khi cần, lặp lại trên các JDK và compiler/build tools dự án thật sự hỗ trợ.

## 13. Bài tập tự kiểm tra

**Câu 1.** `@Target(METHOD)` và `@Retention(RUNTIME)` có cho phép gắn annotation lên class không?  
**Đáp án:** Không. Target sai gây compile error dù retention là RUNTIME.

**Câu 2.** `@Retention(CLASS)` trên class, `javap -v` có thể thấy metadata nhưng `Class.isAnnotationPresent` trả false. Có phải lỗi?  
**Đáp án:** Không. CLASS metadata không được runtime Reflection công khai.

**Câu 3.** Nếu không ghi `@Retention`, mặc định là gì?  
**Đáp án:** `RetentionPolicy.CLASS`.

**Câu 4.** `List<@A String>` là test cho `TYPE`, `TYPE_USE` hay `TYPE_PARAMETER`?  
**Đáp án:** `TYPE_USE` vì `String` là một **type argument**.

**Câu 5.** `class C<@A T>` thử vị trí nào?  
**Đáp án:** Khai báo **type parameter** `T`; target `TYPE_PARAMETER` thích hợp, và `TYPE_USE` cũng có các vị trí này theo JLS.

**Câu 6.** Vì sao không thể dựa vào Reflection để test mọi trường hợp `LOCAL_VARIABLE`?  
**Đáp án:** Reflection chuẩn không cung cấp API tổng quát để truy vấn annotation trên các local variable declarations.

**Câu 7.** `getAnnotation` trên `Field` trả false, nhưng `getAnnotatedType` trả true cho cùng tên annotation type. Điều này có thể xảy ra không?  
**Đáp án:** Có, nếu annotation nằm ở **type-use context** của field, không phải field declaration.

**Câu 8.** Khi negative compilation thất bại do thiếu classpath của annotation type, có được coi đó là PASS của phép thử target không?  
**Đáp án:** Không. Phải xác định lỗi cụ thể do annotation được đặt sai vị trí.

**Bài thực hành:** Biên dịch và chạy `AnnotationMatrixDemo.java`, sau đó chạy `javap -v MatrixSample` để tìm RuntimeVisible và RuntimeInvisible metadata. Tạo riêng bốn negative files ở phần 7, xác nhận mọi file biên dịch thất bại vì sai target. Cuối cùng thêm một annotation `@Target(TYPE_USE)` ở kiểu phần tử mảng và tự thiết kế một test Reflection `AnnotatedArrayType`; phân biệt annotation trên thành phần mảng với annotation trên chính kiểu mảng theo vị trí cú pháp.

## 14. Tài liệu chính thức Java SE 17

- [JLS §9.6.4.1 — `@Target`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): quy tắc áp dụng annotation.
- [JLS §9.6.4.2 — `@Retention`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2): quy tắc retention.
- [JLS §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): declaration/type contexts.
- [Java SE 17 — `ElementType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html): đủ các target enum constants.
- [Java SE 17 — `RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): SOURCE, CLASS, RUNTIME.
- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): Reflection contract của annotations.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): công cụ xem class-file metadata.

**Kết luận:** Kiểm thử `@Target` và `@Retention` cần ba góc nhìn **compiler, class file, runtime Reflection**. Hãy chứng minh cả trường hợp hợp lệ lẫn sai target; phân biệt metadata không được giữ với metadata có mặt trong `.class` nhưng không hiển thị ở runtime; và luôn đọc annotation bằng API phù hợp với **nơi nó được gắn**.