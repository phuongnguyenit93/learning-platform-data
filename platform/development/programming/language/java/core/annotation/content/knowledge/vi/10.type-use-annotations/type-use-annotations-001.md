# Phân biệt annotation trên khai báo với annotation trên kiểu trong Java

Java cho phép dùng annotation để mô tả **một phần tử chương trình được khai báo** (*declaration*) hoặc **một vị trí mà kiểu được sử dụng** (*type use*). Cả hai cùng có cú pháp dấu **@**, nhưng metadata được gắn với hai đối tượng khác nhau. Vì thế, khi đọc annotation qua reflection hoặc khi thiết kế công cụ phân tích mã nguồn, phải xác định chính xác annotation được áp dụng vào **khai báo** hay **kiểu tại vị trí xuất hiện**.

Ví dụ:

~~~java
@FieldTag String name;
~~~

Nếu **FieldTag** được khai báo với **@Target(ElementType.FIELD)**, dấu này thuộc **khai báo field name**. Nếu được khai báo với **@Target(ElementType.TYPE_USE)**, dấu này thuộc **vị trí sử dụng kiểu String của field name**. Nếu FieldTag cho phép **cả FIELD và TYPE_USE**, dấu @ ở vị trí này có thể được coi là **cả declaration annotation lẫn type annotation** theo Java Language Specification (JLS §9.7.4).

Do đó, chỉ nhìn việc dấu @ nằm trước từ **String** là chưa đủ để xác định annotation áp dụng vào đâu; phải xem **@Target của annotation type**.

## 1. Khai báo (declaration) và sử dụng kiểu (type use) là gì?

**Khai báo** tạo hoặc định nghĩa một thực thể trong chương trình, chẳng hạn class, method, field, constructor, parameter hoặc type parameter:

~~~java
class Customer {
    String name;

    String displayName(String prefix) {
        return prefix + name;
    }
}
~~~

Trong đoạn trên:

- **class Customer** là khai báo class.
- **String name** là khai báo field **name**, đồng thời có một lần sử dụng kiểu **String** làm kiểu của field.
- **displayName(...)** là khai báo method, đồng thời **String** đầu tiên là kiểu trả về của method.
- **String prefix** là khai báo tham số **prefix**, đồng thời có một lần sử dụng kiểu String làm kiểu tham số.

Một vị trí cú pháp có thể vừa chứa khai báo, vừa chứa kiểu được sử dụng để định nghĩa khai báo đó. Đây chính là lý do annotation trên field, method return hoặc formal parameter dễ bị nhầm.

**Type use** không đòi hỏi tạo một khai báo mới. Ví dụ **String** trong **List<String>**, **Number** trong **T extends Number** hay **String** trong phép cast **(String) obj** đều là những nơi kiểu xuất hiện:

~~~java
java.util.List<String> names;
class Holder<T extends Number> {}
Object raw = "hello";
String text = (String) raw;
~~~

Annotation với target TYPE_USE có thể đặt ở những vị trí kiểu này mà annotation chỉ có target FIELD, METHOD hoặc PARAMETER không thể bao phủ.

## 2. @Target quyết định annotation áp dụng vào đâu

Ba khai báo dưới đây thể hiện ranh giới cơ bản:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldTag {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}

@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface BothTag {
    String value();
}
~~~

Khi sử dụng:

~~~java
class Account {
    @FieldTag("field declaration")
    @TypeTag("String type")
    String owner;

    @BothTag("field and type")
    String identifier;
}
~~~

Kết luận:

1. **FieldTag** chỉ áp dụng lên **khai báo field owner**.
2. **TypeTag** chỉ áp dụng lên **kiểu String** của field owner, tức một *type-use annotation*.
3. **BothTag** cho phép đồng thời **FIELD và TYPE_USE**. Với cú pháp trước kiểu field như trên, annotation có thể thuộc cả khai báo field identifier và vị trí kiểu String tương ứng.

**Cùng một vị trí viết không bắt buộc có cùng ý nghĩa.** Trình biên dịch kiểm tra tập target hợp lệ, sau đó biểu diễn metadata theo loại áp dụng được đặc tả.

Một annotation có thể có nhiều target:

~~~java
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.TYPE_USE
})
@interface TraceInfo {}
~~~

Với kiểu này, phải kiểm tra vị trí cụ thể và đôi khi cả hai dạng metadata. Việc cho phép nhiều target chỉ quy định nơi đặt annotation; nó chưa tạo ra hành vi kiểm toán hoặc truy vết tự động.

## 3. So sánh các target declaration với TYPE_USE

| Target | Annotation trên gì? | Ví dụ |
| --- | --- | --- |
| **TYPE** | Khai báo class, interface, enum hoặc annotation type | **@EntityTag class Order {}** |
| **FIELD** | Khai báo field | **@FieldTag String name;** |
| **METHOD** | Khai báo method | **@MethodTag String getName() { ... }** |
| **PARAMETER** | Khai báo tham số method/constructor | **void send(@ArgTag String name)** |
| **CONSTRUCTOR** | Khai báo constructor | **@CtorTag Service() {}** |
| **TYPE_PARAMETER** | Khai báo tham số kiểu generic, ví dụ T trong class Box<T> | **class Box<@ParamTag T> {}** |
| **TYPE_USE** | Kiểu tại một vị trí sử dụng, ví dụ kiểu field, generic argument, return type, cast | **List<@TypeTag String>** |

Có hai điểm tinh tế trong JLS:

- **TYPE_USE cũng được phép tại khai báo type parameter** như **class Box<@TypeTag T>**, dù tên gọi là “type use”. Vì vậy TYPE_PARAMETER và TYPE_USE không phải hai tập vị trí hoàn toàn tách rời.
- **TYPE_USE còn cho phép chú thích khai báo kiểu** (ví dụ trên class). Vì vậy cần hiểu đúng quy tắc JLS cho khai báo type hoặc type parameter; không nên suy luận rằng TYPE_USE *chỉ* được dùng trước một type argument.

Bảng trên cho thấy mục đích của target, nhưng không có nghĩa mọi vị trí chương trình đều chỉ được phép nhận đúng một loại annotation. Cần xét các vùng giao nhau.

## 4. Cùng một dòng field: khai báo và kiểu được dùng

Xét:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface AuditField {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NotBlankType {}

class Profile {
    @AuditField
    @NotBlankType String username;
}
~~~

Giả sử đã import **Retention**, **RetentionPolicy**, **Target**, **ElementType** từ **java.lang.annotation**:

- **@AuditField** mô tả chính field **username**.
- **@NotBlankType** mô tả **String** ở vị trí kiểu của field đó.
- Annotation trên kiểu String của **username** không tự trở thành annotation trên khai báo **java.lang.String**. Nếu một field khác cũng dùng String mà không gắn NotBlankType, nó không nhận annotation này.

Có thể dùng reflection đọc riêng:

~~~java
java.lang.reflect.Field field =
        Profile.class.getDeclaredField("username");

boolean declarationHasTag =
        field.isAnnotationPresent(AuditField.class);

boolean typeUseHasTag =
        field.getAnnotatedType()
                .isAnnotationPresent(NotBlankType.class);
~~~

Khi các annotation có retention **RUNTIME**, hai biến trên đều là **true**.

Sự phân chia API rất quan trọng:

- **Field.getAnnotation(...)** hoặc **Field.getDeclaredAnnotations()** truy vấn annotation trên **khai báo field**.
- **Field.getAnnotatedType()** trả về một **AnnotatedType** đại diện cho **vị trí sử dụng kiểu của field**. Có thể gọi **getAnnotation(...)** trên AnnotatedType để đọc annotation của vị trí đó.
- **Field.getType()** trả về Class đại diện cho kiểu field. **field.getType().getAnnotation(NotBlankType.class)** truy vấn khai báo của lớp String, nên không thể dùng để đọc annotation đã đặt ở type use của username.

Cần phân biệt **AnnotatedElement** (khai báo field) và **AnnotatedType** (vị trí sử dụng kiểu), dù cả hai có API **getAnnotation** giống nhau.

## 5. Method: annotation của method khác annotation trên kiểu trả về

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Endpoint {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ResponseType {}

class Controller {
    @Endpoint
    @ResponseType String getStatus() {
        return "OK";
    }
}
~~~

**@Endpoint** đánh dấu **khai báo method getStatus**. **@ResponseType** đánh dấu **String được dùng làm kiểu trả về**. Thí dụ reflection:

~~~java
java.lang.reflect.Method method =
        Controller.class.getDeclaredMethod("getStatus");

boolean onMethod = method.isAnnotationPresent(Endpoint.class);
boolean onReturnType =
        method.getAnnotatedReturnType()
                .isAnnotationPresent(ResponseType.class);
~~~

Nếu cả hai annotation dùng runtime retention, hai biến đều **true**.

Sự khác biệt có ích khi thiết kế API: metadata “endpoint này cần audit” gắn vào **method declaration**; metadata “giá trị trả về phải đạt một thuộc tính kiểu nào đó” gắn vào **return type use**. Cả hai có thể xuất hiện trước một kiểu trả về, nhưng ý nghĩa do target và công cụ diễn giải quy định.

Nếu annotation có cả METHOD và TYPE_USE, ở vị trí trước kiểu trả về nó có thể áp dụng cả hai. Khi đó công cụ đọc metadata cần kiểm tra cả **Method.getAnnotation(...)** và **Method.getAnnotatedReturnType().getAnnotation(...)**, tùy thông tin cần dùng.

## 6. Parameter: PARAMETER không giống TYPE_USE

Với tham số method:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface RequestArgument {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TrimmedType {}

class Handler {
    void handle(@RequestArgument @TrimmedType String input) {
    }
}
~~~

Ở đây:

- **@RequestArgument** áp dụng lên khai báo formal parameter **input**.
- **@TrimmedType** áp dụng lên **kiểu String** của tham số input.

Với reflection, đọc theo hai đường khác nhau:

~~~java
java.lang.reflect.Method method =
        Handler.class.getDeclaredMethod("handle", String.class);

boolean onParameter =
        method.getParameters()[0]
                .isAnnotationPresent(RequestArgument.class);

boolean onParameterType =
        method.getAnnotatedParameterTypes()[0]
                .isAnnotationPresent(TrimmedType.class);
~~~

Hai biểu thức đều cho **true** với runtime retention. Không cần ép kiểu String hay tìm metadata trên **String.class**.

**ElementType.PARAMETER** không phải **ElementType.TYPE_PARAMETER**. PARAMETER là đối tượng formal parameter như **String input**; TYPE_PARAMETER là type variable được khai báo trong generic như **<T>**. Phân biệt ba vị trí này:

~~~java
class Converter<@TypeTag T> {
    T convert(T input) {
        return input;
    }
}
~~~

Nếu TypeTag có target TYPE_USE, **@TypeTag T** ở **<T>** hợp lệ vì TYPE_USE cũng cho phép khai báo type parameter. Chữ **T** làm kiểu trả về của **convert** và kiểu của **input** là hai lần **sử dụng kiểu**, không tự nhận annotation đã gắn ở khai báo T. Annotation không tự lan từ một type variable declaration tới mọi occurrence của type variable đó.

## 7. Những type-use context thường gặp

Để nhận ra TYPE_USE, hãy chú ý vị trí của kiểu bên trong cấu trúc lớn hơn:

~~~java
import java.util.List;
import java.util.Map;

class Usage {
    List<@TypeTag String> names;

    Map<@TypeTag String, @TypeTag Integer> sizes;

    <T extends @TypeTag Number> void process(T input) {
        @TypeTag String label = input.toString();
        System.out.println(label);
    }

    Object raw = "sample";

    String cast() {
        return (@TypeTag String) raw;
    }

    @TypeTag String @TypeTag [] items;
}
~~~

Các vị trí:

- **List<@TypeTag String>**: metadata trên type argument String.
- **Map<@TypeTag String, @TypeTag Integer>**: mỗi type argument mang annotation riêng.
- **T extends @TypeTag Number**: metadata trên kiểu bound Number của generic T.
- **@TypeTag String label**: metadata trên kiểu String của local variable; annotation type-use có thể được lưu dưới dạng metadata của method trong class file, nhưng reflection chuẩn không cung cấp một API chung để đọc mọi annotation của biến cục bộ.
- **(@TypeTag String) raw**: metadata trên kiểu String được sử dụng trong cast.
- **@TypeTag String @TypeTag [] items**: annotation trước String áp dụng lên kiểu thành phần String; annotation trước dấu ngoặc vuông áp dụng lên một chiều của kiểu mảng. Chúng là những type paths khác nhau.

**Lưu ý về mảng:** vị trí annotation có ý nghĩa. Với mảng nhiều chiều, dấu @ trước cặp **[]** khác có thể chỉ chiều mảng khác nhau. Để hiểu metadata chuẩn xác, cần đối chiếu cấu trúc **AnnotatedArrayType** hoặc thông tin type path trong class file.

Một annotation chỉ có FIELD/METHOD/PARAMETER không được dùng ở tất cả các vị trí type argument, type bound hoặc cast nói trên. Type-use annotation khai báo với **@Target(TYPE_USE)** mới áp dụng rộng rãi cho những vị trí này.

## 8. Chương trình Java 17+ hoàn chỉnh: đọc đúng hai loại annotation

Tạo tệp duy nhất **src/demo/DeclarationVsTypeUseDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParameterMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface DualMark {
    String value();
}

class Example {
    @FieldMark("field")
    @TypeMark("field-type")
    String name = "Ada";

    List<@TypeMark("list-item") String> aliases = List.of("Ada");

    @DualMark("both")
    String identifier = "U-01";

    @MethodMark("method")
    @TypeMark("return-type")
    String echo(
            @ParameterMark("parameter")
            @TypeMark("parameter-type")
            String input) {
        return input;
    }
}

public class DeclarationVsTypeUseDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Field name = Example.class.getDeclaredField("name");
        System.out.println("field declaration="
                + name.getAnnotation(FieldMark.class).value());
        System.out.println("field type="
                + name.getAnnotatedType()
                        .getAnnotation(TypeMark.class).value());

        Field aliases = Example.class.getDeclaredField("aliases");
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) aliases.getAnnotatedType();
        System.out.println("list item type="
                + listType.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeMark.class).value());

        Field identifier = Example.class.getDeclaredField("identifier");
        System.out.println("dual declaration="
                + identifier.getAnnotation(DualMark.class).value());
        System.out.println("dual type="
                + identifier.getAnnotatedType()
                        .getAnnotation(DualMark.class).value());

        Method echo = Example.class.getDeclaredMethod(
                "echo", String.class);
        System.out.println("method declaration="
                + echo.getAnnotation(MethodMark.class).value());
        System.out.println("method return type="
                + echo.getAnnotatedReturnType()
                        .getAnnotation(TypeMark.class).value());
        System.out.println("parameter declaration="
                + echo.getParameters()[0]
                        .getAnnotation(ParameterMark.class).value());
        System.out.println("parameter type="
                + echo.getAnnotatedParameterTypes()[0]
                        .getAnnotation(TypeMark.class).value());
    }
}
~~~

Từ thư mục chứa **src**:

~~~bash
javac -encoding UTF-8 -d out src/demo/DeclarationVsTypeUseDemo.java
java -cp out demo.DeclarationVsTypeUseDemo
~~~

**Stdout mong đợi:**

~~~text
field declaration=field
field type=field-type
list item type=list-item
dual declaration=both
dual type=both
method declaration=method
method return type=return-type
parameter declaration=parameter
parameter type=parameter-type
~~~

**Phân tích:**

1. **name.getAnnotation(FieldMark.class)** đọc metadata trên khai báo field **name**. **name.getAnnotatedType().getAnnotation(TypeMark.class)** đọc metadata trên **kiểu String** của chính field đó.
2. **aliases.getAnnotatedType()** đại diện cho **List<String>**; ép sang **AnnotatedParameterizedType** cho phép lấy annotation nằm trên **String** bên trong List, khác với annotation trên kiểu List bên ngoài.
3. **identifier** có DualMark với cả FIELD và TYPE_USE. Vì annotation này được viết trước kiểu String ở khai báo field, cả **Field.getAnnotation(DualMark.class)** và **Field.getAnnotatedType().getAnnotation(DualMark.class)** tìm được DualMark. Đây là trường hợp **một lần viết annotation thuộc hai dạng** theo target.
4. **echo.getAnnotation(MethodMark.class)** đọc annotation trên khai báo method; **echo.getAnnotatedReturnType()** đọc annotation trên kiểu String được dùng làm return type.
5. **getParameters()[0]** trả về đối tượng Parameter, dùng để đọc annotation trên formal parameter declaration; **getAnnotatedParameterTypes()[0]** cho biết annotation ở vị trí kiểu String của tham số.
6. Tất cả các annotation trong ví dụ dùng **@Retention(RUNTIME)**. Nếu thiếu runtime retention, không thể mong chờ các API reflection trên trả về metadata tương ứng.

**Lưu ý để chương trình chạy được:** Chỉ class **DeclarationVsTypeUseDemo** là public trong tệp; các annotation và class phụ là top-level type có phạm vi package. Dòng import **List** dùng API **List.of** có từ Java 9, vì vậy chạy với Java 17+ phù hợp. **ReflectiveOperationException** bao phủ các lỗi truy vấn member có thể xảy ra tại compile time; những member được dùng trong ví dụ đều tồn tại nên chương trình in đúng các dòng trên.

## 9. Annotation tồn tại trong class file ở đâu?

Khi annotation có retention phù hợp, thông tin được mã hóa trong class file nhưng **đường lưu và đường đọc khác nhau**.

**Declaration annotation** gắn lên class, field, method hoặc parameter có thể nằm trong các thuộc tính annotation tương ứng của class file, chẳng hạn **RuntimeVisibleAnnotations** đối với class/field/method hay **RuntimeVisibleParameterAnnotations** đối với formal parameter.

**Type annotation** ghi thêm metadata xác định **đích type use** và **đường đi đến phần kiểu được chú thích** (*type path*), trong các thuộc tính như **RuntimeVisibleTypeAnnotations**. Ví dụ annotation trên **List<@TypeMark String>** cần chỉ rõ annotation thuộc **String** là type argument thứ nhất, không phải List bên ngoài.

Với ví dụ Java đã biên dịch, thử:

~~~bash
javap -v -p out/demo/Example.class
~~~

Trong đầu ra, có thể tìm những vị trí metadata liên quan:

- **FieldMark** trong metadata của **field declaration**.
- **TypeMark** trong metadata **type annotation** trên field type hoặc type argument.
- **DualMark** có thể xuất hiện trong cả annotation của khai báo field và annotation của type use vì @Target cho phép cả hai.
- **MethodMark** trên method declaration; **TypeMark** trên kiểu return hoặc kiểu parameter; **ParameterMark** trên formal parameter declaration.

Không phụ thuộc vào số constant pool hoặc chỉ số cụ thể do **javap** hiển thị: chúng có thể khác giữa phiên bản compiler. Mục đích là thấy metadata **được mã hóa theo những loại đích khác nhau**.

Với **@Retention(SOURCE)**, annotation không tồn tại trong class file sau biên dịch. Với **@Retention(CLASS)**, nó có thể được ghi vào metadata không hiện diện qua reflection runtime. Ví dụ này chọn **RUNTIME** để có thể quan sát cả hai qua API chuẩn.

## 10. Vị trí chồng lấp và ngoại lệ cần nhớ

### 10.1. Một annotation có thể là cả declaration và type annotation

JLS §9.7.4 nêu ví dụ kiểu field **@Foo int f**: nếu Foo áp dụng cho FIELD thì @Foo thuộc khai báo **f**; nếu Foo áp dụng cho TYPE_USE thì @Foo thuộc kiểu **int**; nếu Foo có cả hai target thì **cả hai nhận annotation**.

Tương tự, vùng cú pháp đặt annotation ngay trước kiểu trả về method, kiểu formal parameter, kiểu field, kiểu local variable hoặc record component có thể vừa là vị trí modifier của khai báo vừa là nơi xuất hiện kiểu. Phạm vi đích hợp lệ của annotation mới quyết định metadata được hiểu như thế nào. Vì vậy một annotation khai báo nhiều target có thể xuất hiện ở hơn một dạng trong cùng một vị trí.

Không nên suy luận từ khoảng trắng hoặc việc annotation viết cùng dòng hay khác dòng: **@Target** và cấu trúc cú pháp mới là yếu tố quyết định.

### 10.2. TYPE_PARAMETER, TYPE_USE và khai báo generic

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface GenericName {}

@Target(ElementType.TYPE_USE)
@interface TypePolicy {}

class Cache<@GenericName @TypePolicy K> {
    @TypePolicy K key;
}
~~~

- **@GenericName** chỉ áp dụng lên **khai báo type parameter K**.
- **@TypePolicy** có TYPE_USE nên cũng hợp lệ ở khai báo K; TYPE_USE được định nghĩa bao gồm khai báo type parameter.
- **@TypePolicy K key** gắn lên lần sử dụng K làm kiểu field, không gắn lên một khai báo type parameter khác.
- **GenericName** không thể thay TypePolicy trên kiểu field hay type argument vì nó không có TYPE_USE.

Một annotation ở khai báo K không tự lan tới toàn bộ các chỗ sử dụng K. Nếu một thư viện muốn truyền quy tắc từ generic declaration sang type argument, cần công cụ có ngữ nghĩa phù hợp.

### 10.3. TYPE_USE và khai báo class

Theo định nghĩa trong **ElementType** và JLS, TYPE_USE bao gồm các ngữ cảnh khai báo kiểu. Một annotation chỉ có TYPE_USE vẫn có thể viết trên khai báo class. Vì thế không thể kết luận cứ viết **@A class Service** thì A nhất thiết phải có **@Target(TYPE)**: TYPE_USE cũng là target phù hợp cho khai báo kiểu theo ngôn ngữ Java.

Tuy nhiên, điều này không có nghĩa mọi type annotation trên những nơi sử dụng **Service** đều nằm trên chính khai báo **Service**. Annotation viết tại **List<@A Service>** gắn vào **vị trí Service được dùng làm generic argument**, không tự sửa metadata của class Service.

## 11. Khi thiết kế annotation, nên chọn target nào?

Một số hướng chọn:

- Nếu annotation đánh dấu **field để serialize, map cột, audit hoặc chặn ghi**, và ý nghĩa thuộc **field được khai báo**, target **FIELD** thường rõ mục đích hơn.
- Nếu annotation đánh dấu **endpoint, callback hoặc method cần logging**, ý nghĩa thuộc **method declaration**, target **METHOD** thường phù hợp.
- Nếu annotation mô tả **cách ràng buộc một formal parameter** (ví dụ từ HTTP request), dùng target **PARAMETER** khi chính tham số là đối tượng metadata.
- Nếu annotation diễn đạt **thuộc tính của kiểu ở từng vị trí sử dụng** (ví dụ non-null, tainted, immutable), chọn **TYPE_USE** để hỗ trợ generic argument, field type, return type, cast, bound và các vị trí khác.
- Nếu annotation thực sự cần biểu thị cả declaration lẫn type use, khai báo cả hai target và kiểm tra chiến lược đọc metadata. Đặc biệt với class/method/field, quyết định này có thể khiến cùng một annotation xuất hiện trong hai nhóm metadata.

Ví dụ:

~~~java
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Example {
    java.util.List<@NonNull String> names;
}
~~~

Annotation trên **String** ở đây là hợp lệ. Nhưng **@NonNull** tự định nghĩa không làm compiler Java tiêu chuẩn tự loại trừ mọi phép gán null. Nó là metadata; cần type checker, annotation processor hoặc framework có quy tắc riêng để biến metadata thành cảnh báo hoặc kiểm tra. Đây là điểm chung của cả declaration và type-use annotation.

## 12. Lỗi thường gặp và cách kiểm tra

| Hiểu sai hoặc lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| “Dấu @ trước String chắc chắn là FIELD annotation.” | Vị trí này cũng là một type use | Xem @Target của kiểu annotation |
| “TYPE_USE chỉ dùng trong generic argument.” | TYPE_USE bao phủ nhiều ngữ cảnh, kể cả return, bound, cast, array | Đối chiếu JLS §4.11 |
| Gắn annotation chỉ có FIELD vào **List<@A String>** | Generic argument không phải field declaration | Dùng TYPE_USE |
| Gắn annotation chỉ có METHOD lên **@A String** bên trong generic | Đây không phải method declaration | Dùng TYPE_USE |
| Dùng **field.getAnnotation(TypeMark.class)** để đọc annotation trên type use | Đọc sai đối tượng reflection | Dùng **field.getAnnotatedType()** |
| Dùng **field.getType().getAnnotation(TypeMark.class)** | Đang đọc khai báo class của kiểu, không phải vị trí sử dụng | Dùng **AnnotatedType** của field |
| Dùng **method.getAnnotation(...)** để đọc annotation trên kiểu trả về | Method object đại diện declaration | Dùng **method.getAnnotatedReturnType()** |
| Nhầm PARAMETER và TYPE_PARAMETER | Formal parameter khác generic type variable | Dùng PARAMETER với tham số method, TYPE_PARAMETER với khai báo T |
| Annotation không có RUNTIME mà chờ reflection trả về | Retention CLASS/SOURCE không hỗ trợ truy vấn runtime thông thường | Khai báo **@Retention(RUNTIME)** nếu thật sự cần |
| Annotation TYPE_USE được gắn trước class khiến tưởng annotation tự có trên mọi nơi dùng class | Metadata thuộc từng vị trí áp dụng cụ thể | Truy vấn đúng declaration hoặc AnnotatedType |
| Mong annotation tùy chỉnh tự ép compiler kiểm tra non-null | Java không tự diễn giải ngữ nghĩa nghiệp vụ của annotation | Tích hợp công cụ phân tích/logic xử lý |

## 13. Bài tập tự kiểm tra

**Bài 1.** Với một kiểu annotation **@Target(FIELD)**, những câu nào hợp lệ?

~~~java
class Product {
    @FieldMark("ok") String sku; // hợp lệ: khai báo field
    // java.util.List<@FieldMark("x") String> ids; // sai: type argument
}
~~~

Giải thích: annotation FIELD thuộc khai báo sku; **String** trong List là type-use context và không được target FIELD cho phép.

**Bài 2.** Với một kiểu annotation chỉ có **@Target(TYPE_USE)**, có thể dùng trong **List<@A String>** và **@A String field** không? **Có**: trường hợp đầu chú thích generic argument, trường hợp sau chú thích kiểu String của field.

**Bài 3.** Với **@Target({FIELD, TYPE_USE})**, khi viết **@A String field**, việc gọi **Field.getAnnotation(A.class)** và **Field.getAnnotatedType().getAnnotation(A.class)** có thể cùng tìm thấy A không? **Có**, nếu A được giữ đến runtime và đặt ở vị trí như mô tả. Đây là vùng chồng lấp mà JLS §9.7.4 quy định.

**Bài 4.** Trong **void handle(@ParameterMark("p") @TypeMark("t") String input)**, truy vấn nào đọc ParameterMark? **Method.getParameters()[0].getAnnotation(ParameterMark.class)**. Truy vấn nào đọc TypeMark? **Method.getAnnotatedParameterTypes()[0].getAnnotation(TypeMark.class)**.

**Bài 5.** Nếu định nghĩa **@Target(TYPE_USE)** cho annotation NonNull và chỉ viết **@NonNull String name**, Java có tự động cấm gán null không? **Không**. Target quy định vị trí hợp lệ, còn ngữ nghĩa non-null phải do công cụ hoặc mã xử lý bổ sung đảm nhiệm.

## 14. Nguồn Java chính thức

- **JLS Java 17 §9.7.4 — Where Annotations May Appear:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4 — nêu trực tiếp quy tắc phân biệt declaration annotation, type annotation và khả năng cùng một vị trí thuộc cả hai.
- **JLS Java 17 §4.11 — Where Types Are Used:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11 — liệt kê các type context được Java chấp nhận.
- **Java SE 17 — ElementType:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html — định nghĩa FIELD, METHOD, PARAMETER, TYPE_PARAMETER, TYPE_USE và các đích khác.
- **Java SE 17 — Field.getAnnotatedType():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getAnnotatedType() — API đọc vị trí kiểu của field.
- **Java SE 17 — Method, AnnotatedType và AnnotatedParameterizedType:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html

Khi phân tích một annotation ở bất kỳ dòng Java nào, trước tiên hãy xác định **đối tượng được khai báo**, **kiểu được sử dụng tại dòng đó**, rồi kiểm tra **@Target**. Nếu cần đọc metadata lúc runtime, chọn đúng **reflection API** cho khai báo hoặc cho **AnnotatedType**. Việc đặt dấu @ giống nhau không có nghĩa metadata được lưu và truy xuất cùng một cách.
