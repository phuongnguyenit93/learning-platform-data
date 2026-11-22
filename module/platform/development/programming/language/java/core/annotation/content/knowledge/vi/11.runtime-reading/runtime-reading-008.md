# Phân biệt Type và AnnotatedType khi đọc siêu dữ liệu kiểu trong Java Core

Trong Java Reflection, **`java.lang.reflect.Type` mô tả cấu trúc một kiểu** (ví dụ `List<String>`, `T` hoặc `? extends Number`), còn **`java.lang.reflect.AnnotatedType` gắn cấu trúc kiểu đó với những annotation nằm trên chính *vị trí sử dụng kiểu* (type use)**. Khi đọc các annotation dùng `@Target(TYPE_USE)`, chỉ dùng `Type` thường chưa đủ: bạn phải bắt đầu từ một API trả về `AnnotatedType` rồi đi đúng nhánh trong cây kiểu.

Bài học tập trung vào trường hợp đọc metadata lúc chạy, giả sử các annotation liên quan có `@Retention(RUNTIME)`. Đây là cơ chế của Java Core, độc lập với framework.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

- Giải thích rạch ròi thông tin mà `Type` và `AnnotatedType` biểu diễn.
- Nhận biết các dạng cấu trúc `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`.
- Dùng đúng cặp API `getGenericType()` / `getAnnotatedType()` trên field, `getGenericReturnType()` / `getAnnotatedReturnType()` trên method, và `getBounds()` / `getAnnotatedBounds()` trên tham số kiểu.
- Đọc annotation trên kiểu ngoài, đối số kiểu lồng, generic upper bound và wildcard upper/lower bounds.
- Phân biệt annotation trên **khai báo field/method/class** với annotation trên **kiểu được sử dụng** trong khai báo.
- Hiểu vì sao `getType()` của `AnnotatedType` không tự đưa annotation vào `Type`, và vì sao type erasure không ngăn Reflection đọc metadata generic đã lưu.
- Tự chạy ví dụ Java 17+ và dự đoán đầu ra của Reflection.

## 2. Bắt đầu từ câu hỏi: bạn muốn đọc cấu trúc kiểu hay annotation trên kiểu?

Xét một khai báo:

~~~java
List<@Mark("item") String> names;
~~~

Giả sử `@Mark` là annotation có target `TYPE_USE` và retention `RUNTIME`.

Có ít nhất ba tầng thông tin khác nhau:

1. Field tên `names` là **một khai báo field**.
2. Kiểu của field là `List<String>`, trong đó `List` là kiểu generic và `String` là type argument.
3. Annotation `@Mark("item")` gắn lên **lần sử dụng kiểu `String` làm type argument** trong `List<String>`.

API `Field.getGenericType()` cung cấp tầng 2 — cấu trúc kiểu. API `Field.getAnnotatedType()` cung cấp đường đi để đọc tầng 3. Nếu annotation được gắn ở chính field declaration với target `FIELD`, bạn đọc qua `Field.getAnnotation(...)`: đó là một nơi khác.

Ví dụ có cả hai loại annotation:

~~~java
@FieldTag
List<@Mark("item") String> names;
~~~

`@FieldTag` (nếu target `FIELD`) mô tả field; `@Mark` (target `TYPE_USE`) mô tả type argument `String`. Chúng không tự thay thế nhau; một field có thể chứa cả declaration metadata và type-use metadata.

## 3. `Type`: mô hình cấu trúc generic, chưa phải nơi lấy annotation

`Type` là interface trong package `java.lang.reflect`. Nó giúp mô tả kiểu Java được phản chiếu, bao gồm kiểu có generic arguments. Những implementation/nhánh quan trọng:

| Dạng `Type` | Ví dụ nguồn | Ý nghĩa |
| --- | --- | --- |
| `Class<?>` | `String`, `int[]`, hoặc một raw class | Kiểu lớp, interface, primitive hay array được biểu diễn bằng `Class` khi phù hợp |
| `ParameterizedType` | `List<String>` | Kiểu generic với các type arguments thực tế |
| `TypeVariable<?>` | `T` trong `class Box<T>` | Tham số kiểu được khai báo bởi class, method hoặc constructor |
| `WildcardType` | `? extends Number` hoặc `? super Integer` | Wildcard với upper/lower bounds |
| `GenericArrayType` | `T[]` hay `List<String>[]` | Kiểu mảng mà thành phần cần mô tả bằng một generic type |

Các API cơ bản:

~~~java
Type type = SomeClass.class
        .getDeclaredField("names")
        .getGenericType();

System.out.println(type.getTypeName());
~~~

Đây chỉ là đoạn minh họa: `SomeClass` phải tồn tại, còn import `java.lang.reflect.Type` cần được cung cấp. Nếu field là `List<String>`, `getTypeName()` thông thường biểu diễn `java.util.List<java.lang.String>`.

Điều **`Type` không cung cấp trực tiếp** là `getAnnotation(Mark.class)`; interface `Type` không mở rộng `AnnotatedElement`. Mặc dù một đối tượng cụ thể như `Class` hay `TypeVariable` cũng có các API annotation vì những interface/class đó triển khai thêm hợp đồng khác, việc gọi annotation API trên `Class` hay `TypeVariable` không mặc định có nghĩa đang đọc **annotation tại một type-use position**.

Ví dụ `Box.class.getAnnotation(...)` đọc metadata khai báo trên class; `TypeVariable.getAnnotation(...)` đọc annotation trên khai báo tham số kiểu. Đây đều không tương đương với đọc annotation trên một type argument nằm sâu trong `List<...>`.

## 4. `AnnotatedType`: kiểu tại vị trí sử dụng cùng metadata TYPE_USE

`AnnotatedType` cũng nằm trong `java.lang.reflect`, nhưng nó mở rộng `AnnotatedElement`; vì vậy có thể gọi các phương thức:

- `getAnnotation(Tag.class)` hoặc `getDeclaredAnnotation(Tag.class)` để lấy annotation tại **đúng vị trí kiểu hiện tại**.
- `getAnnotations()`, `getDeclaredAnnotations()` để lấy các annotation tại vị trí này.
- `getType()` để lấy `Type` nền tảng của vị trí kiểu đó.

Ví dụ:

~~~java
AnnotatedType annotated = SomeClass.class
        .getDeclaredField("names")
        .getAnnotatedType();

Type underlying = annotated.getType();
Mark here = annotated.getAnnotation(Mark.class);
~~~

Nếu `names` được khai báo `List<@Mark("item") String>` thì biến `here` tại **kiểu ngoài `List`** có thể là `null`, bởi `@Mark` nằm ở **type argument bên trong**, không nằm trên `List`. Muốn đọc được phải đi sâu vào cấu trúc.

Các subtype quan trọng:

| Interface mở rộng `AnnotatedType` | Dùng khi nào? | API đưa tới phần con |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `List<...>`, `Map<...>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | Kiểu mảng | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `? extends X`, `? super Y` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | Một lần dùng tham số kiểu, ví dụ `T` | `getAnnotatedBounds()` |
| `AnnotatedType` thông thường | Kiểu không có cấu trúc con đặc biệt | `getType()` và annotation API |

**Nguyên tắc quan trọng:** Mỗi `AnnotatedType` chỉ đại diện cho một **vị trí** trong cấu trúc kiểu. Annotation trên `List`, `String` bên trong `List`, wildcard `?` và bound của wildcard là các vị trí khác nhau. Để đọc chính xác, duyệt đúng cây `AnnotatedType`.

## 5. So sánh bằng bảng API Reflection

| Nơi bắt đầu | API chỉ lấy cấu trúc `Type` | API giữ annotation tại type-use position |
| --- | --- | --- |
| `Field` | `getGenericType()` | `getAnnotatedType()` |
| `Method` trả về giá trị | `getGenericReturnType()` | `getAnnotatedReturnType()` |
| `Method` tham số | `getGenericParameterTypes()` | `getAnnotatedParameterTypes()` |
| `Executable` `throws` | `getGenericExceptionTypes()` | `getAnnotatedExceptionTypes()` |
| `Constructor` tham số | `getGenericParameterTypes()` | `getAnnotatedParameterTypes()` |
| `Class` và superclass | `getGenericSuperclass()` | `getAnnotatedSuperclass()` |
| `Class` và interfaces | `getGenericInterfaces()` | `getAnnotatedInterfaces()` |
| `TypeVariable<?>` và bounds | `getBounds()` | `getAnnotatedBounds()` |
| `ParameterizedType` và arguments | `getActualTypeArguments()` | Dùng `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` trên vị trí đã được lấy qua API annotated |

Chú ý: `ParameterizedType` không có phương thức `getAnnotatedActualTypeArguments()`. Bạn phải có đối tượng thuộc `AnnotatedParameterizedType`; ví dụ, lấy nó từ `Field.getAnnotatedType()` nếu khai báo field là một parameterized type. Không phải mọi `AnnotatedType` đều có thể ép kiểu thành `AnnotatedParameterizedType`.

Khi chỉ cần biết field là `List<String>`, `getGenericType()` thường đủ. Khi cần biết annotation trên kiểu `List` hoặc `String`, chọn `getAnnotatedType()`.

## 6. Ví dụ Java 17+ chạy độc lập: Type, AnnotatedType và các nhánh lồng

Tạo file **`TypeVsAnnotatedTypeDemo.java`**, không đặt `package` để biên dịch đơn giản. Toàn bộ chương trình sau nằm trong một file; chỉ class chứa `main` là `public`.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

class Catalog<T extends @Mark("bound") Number> {
    @Mark("outer")
    List<@Mark("item") String> names;

    List<? extends @Mark("upper") Number> sources;

    List<? super @Mark("lower") Integer> sinks;

    @Mark("return")
    List<@Mark("resultItem") String> find() {
        return List.of("ok");
    }
}

public class TypeVsAnnotatedTypeDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Field field = Catalog.class.getDeclaredField("names");
        Type rawType = field.getGenericType();
        AnnotatedParameterizedType decorated =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        System.out.println("generic=" + rawType.getTypeName());
        System.out.println("outer="
                + decorated.getAnnotation(Mark.class).value());
        System.out.println("argument="
                + decorated.getAnnotatedActualTypeArguments()[0]
                           .getAnnotation(Mark.class).value());

        System.out.println("fieldAnnotations="
                + field.getAnnotations().length);

        TypeVariable<?> variable = Catalog.class.getTypeParameters()[0];
        System.out.println("bound=" + variable.getAnnotatedBounds()[0]
                .getAnnotation(Mark.class).value());

        for (String name : List.of("sources", "sinks")) {
            Field wildcardField = Catalog.class.getDeclaredField(name);
            AnnotatedParameterizedType listType =
                    (AnnotatedParameterizedType)
                    wildcardField.getAnnotatedType();
            AnnotatedWildcardType wildcard =
                    (AnnotatedWildcardType)
                    listType.getAnnotatedActualTypeArguments()[0];

            if (name.equals("sources")) {
                System.out.println("upper="
                        + wildcard.getAnnotatedUpperBounds()[0]
                                  .getAnnotation(Mark.class).value());
            } else {
                System.out.println("lower="
                        + wildcard.getAnnotatedLowerBounds()[0]
                                  .getAnnotation(Mark.class).value());
            }
        }

        Method method = Catalog.class.getDeclaredMethod("find");
        AnnotatedType returnType = method.getAnnotatedReturnType();
        System.out.println("return="
                + returnType.getAnnotation(Mark.class).value());

        AnnotatedParameterizedType listReturn =
                (AnnotatedParameterizedType) returnType;
        System.out.println("returnArg="
                + listReturn.getAnnotatedActualTypeArguments()[0]
                            .getAnnotation(Mark.class).value());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TypeVsAnnotatedTypeDemo.java
java TypeVsAnnotatedTypeDemo
~~~

**Stdout chính xác:**

~~~text
generic=java.util.List<java.lang.String>
outer=outer
argument=item
fieldAnnotations=0
bound=bound
upper=upper
lower=lower
return=return
returnArg=resultItem
~~~

### Từng dòng kết quả đến từ đâu?

1. `Field.getGenericType()` trả kiểu `List<String>`, nên `getTypeName()` hiển thị `java.util.List<java.lang.String>`. Giá trị này không cho bạn biết các chuỗi `"outer"` và `"item"`.
2. `field.getAnnotatedType()` trả một `AnnotatedParameterizedType`. `getAnnotation(Mark.class)` trên **kiểu ngoài `List`** đọc được `"outer"`.
3. `getAnnotatedActualTypeArguments()[0]` đi xuống kiểu `String` bên trong `List`; trên vị trí đó đọc được `"item"`.
4. `field.getAnnotations().length` bằng `0` vì `Mark` chỉ có target `TYPE_USE`, tức các annotation đang mô tả **cách dùng kiểu**, không được gắn thành field declaration annotation kiểu `FIELD`. Nếu annotation type có đồng thời nhiều target và được dùng trong ngữ cảnh đủ điều kiện, cần xét chính xác các target/annotation được khai báo.
5. `Catalog.class.getTypeParameters()[0]` lấy tham số kiểu `T`; `getAnnotatedBounds()[0]` trỏ tới type-use `Number` trong `T extends @Mark("bound") Number` nên được `"bound"`.
6. `sources` chứa wildcard `? extends @Mark("upper") Number`; `AnnotatedWildcardType.getAnnotatedUpperBounds()[0]` đọc được `"upper"`.
7. `sinks` chứa wildcard `? super @Mark("lower") Integer`; `getAnnotatedLowerBounds()[0]` đọc được `"lower"`.
8. `find()` trả về kiểu ngoài `@Mark("return") List<...>`, đọc được `"return"` trên `getAnnotatedReturnType()`.
9. Bên trong kiểu trả về, type argument `String` có `@Mark("resultItem")`, đọc qua `getAnnotatedActualTypeArguments()[0]`.

Chương trình không gọi `Catalog.find()`; nó chỉ đọc siêu dữ liệu trên method declaration và type-use positions. `@Mark` không tự chạy kiểm tra hoặc thay đổi kết quả của method.

## 7. Đi sâu vào những vị trí quan trọng

### 7.1. Kiểu ngoài và type argument nằm trong kiểu ngoài

Xét:

~~~java
@Mark("outer")
List<@Mark("item") String> names;
~~~

Có một cây nhỏ:

~~~text
AnnotatedParameterizedType: List<String>
    |
    +-- annotation trên List: @Mark("outer")
    |
    +-- AnnotatedType cho type argument String
            |
            +-- @Mark("item")
~~~

`getAnnotatedType()` từ field đi vào nút ngoài. Nếu chỉ lấy `getAnnotation(Mark.class)` tại nút ngoài, bạn không thể suy ra rằng đã đọc hết mọi annotation nằm trong nested type arguments. Cần duyệt từng đối số kiểu, rồi tiếp tục đi sâu nếu đối số cũng là parameterized type hay array.

Ví dụ `Map<@Mark("key") String, List<@Mark("value") Integer>>` có nhiều nhánh hơn: đối số thứ nhất là `String` được đánh dấu, đối số thứ hai là `List<Integer>`; muốn lấy `"value"` phải đi từ annotated outer `Map` tới argument thứ hai (`List`), rồi tới argument của `List` (`Integer`).

### 7.2. Wildcard và bounds

Các cấu trúc:

~~~java
List<? extends @Mark("upper") Number> sources;
List<? super @Mark("lower") Integer> sinks;
~~~

`List<...>` có một type argument là wildcard. Wildcard có thể giới hạn trên (`extends`) hoặc dưới (`super`). API phù hợp:

~~~java
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
        ((AnnotatedParameterizedType) someField.getAnnotatedType())
                .getAnnotatedActualTypeArguments()[0];

AnnotatedType[] upperBounds = wildcard.getAnnotatedUpperBounds();
AnnotatedType[] lowerBounds = wildcard.getAnnotatedLowerBounds();
~~~

Đây là đoạn minh họa sử dụng biến `someField` do mã gọi cung cấp, không phải chương trình chạy độc lập. Với `? extends @Mark("upper") Number`, đọc vị trí `upperBounds[0]`. Với `? super @Mark("lower") Integer`, đọc `lowerBounds[0]`. Khi `?` không có bound tường minh, upper bound hiệu lực là `Object`; đừng mặc định mọi nhánh đều có annotation.

Có thể đánh dấu **chính type-use wildcard** (nơi cho phép theo cú pháp Java) và **kiểu bound**; đây là các điểm khác nhau trong cây annotated types. Hãy xác định annotation nằm ngay trước token nào, và duyệt tới đúng điểm đó.

### 7.3. Type variables: declaration khác use

Khai báo:

~~~java
class Holder<@ParamTag T extends @Mark("bound") Number> {}
~~~

Giả sử `@ParamTag` có target `TYPE_PARAMETER` và retention `RUNTIME`. Khi đó:

- `Holder.class.getTypeParameters()[0].getAnnotation(ParamTag.class)` đọc trên **khai báo tham số kiểu `T`**.
- `Holder.class.getTypeParameters()[0].getAnnotatedBounds()[0].getAnnotation(Mark.class)` đọc trên **kiểu `Number` dùng làm bound**.
- Một nơi dùng `T` trong `T value;` có thể được đánh dấu bằng annotation `TYPE_USE` khác; metadata ở lần dùng đó không tự xuất hiện trên khai báo `T`.

`TypeVariable` có khả năng đọc annotation trên khai báo vì bản thân nó là một `AnnotatedElement`. Điều này **không biến mọi đối tượng `Type` thành `AnnotatedType`**. Nếu bạn muốn đọc annotation tại một lần dùng type variable trong field hoặc method, hãy xuất phát từ API annotated của phần tử chứa lần dùng đó rồi xét `AnnotatedTypeVariable` tương ứng.

### 7.4. Kiểu mảng có thể có nhiều vị trí annotation

Với mảng, số chiều là một phần của cấu trúc kiểu. `AnnotatedArrayType` cho phép bạn đi từ mảng ngoài vào component type bằng `getAnnotatedGenericComponentType()`.

Ví dụ minh họa cú pháp:

~~~java
@Mark("element") String @Mark("dimension") [] values;
~~~

`@Mark("element")` nằm trên kiểu thành phần `String`, còn `@Mark("dimension")` nằm ở vị trí chiều mảng. Việc gọi annotation API trên annotated outer array rồi đi xuống component type có thể trả metadata khác nhau. Không nên coi `String[]` là một lá đơn khi đọc type-use annotations.

Với mảng nhiều chiều, có thể có nhiều điểm đặt annotation tương ứng từng chiều; cần đi theo chuỗi `AnnotatedArrayType`. Nếu chỉ cần biết kiểu array là `String[]`, `getGenericType()` vẫn có thể đủ, nhưng nó không cung cấp đường đi đọc từng type-use annotation.

### 7.5. Method return và parameters

Một method có thể có annotation trên kiểu trả về và từng kiểu tham số:

~~~java
@Mark("result") String convert(@Mark("argument") String text) {
    return text;
}
~~~

Đây là method minh họa trong class đã có annotation type `Mark`. Để đọc:

~~~java
Method method = SomeClass.class.getDeclaredMethod(
        "convert", String.class);

AnnotatedType result = method.getAnnotatedReturnType();
AnnotatedType firstParam = method.getAnnotatedParameterTypes()[0];
~~~

Nếu chỉ cần cấu trúc, dùng `getGenericReturnType()` và `getGenericParameterTypes()` tương ứng. Một `Parameter` cũng cung cấp `getAnnotatedType()`. Nếu cần annotation declaration trên **tham số** có target `PARAMETER`, lại dùng `Parameter.getAnnotation(...)`; nó khác với annotation `TYPE_USE` trên chính **kiểu** của tham số.

## 8. Đừng nhầm `AnnotatedType` với `AnnotatedElement` của declaration

Một nhầm lẫn rất phổ biến là “đối tượng Reflection nào cũng có `getAnnotation` thì nó đang hỏi về cùng metadata”. Không đúng.

| Đối tượng đang hỏi | `getAnnotation(Tag.class)` đang đọc trên |
| --- | --- |
| `Class<?>` | Khai báo class/interface (với ngữ nghĩa inheritance của class khi thích hợp) |
| `Method` | Khai báo method |
| `Field` | Khai báo field |
| `Parameter` | Khai báo tham số |
| `TypeVariable<?>` | Khai báo tham số kiểu |
| `AnnotatedType` | **Một vị trí dùng kiểu** |

Ví dụ, `Field.getAnnotation(Mark.class)` và `Field.getAnnotatedType().getAnnotation(Mark.class)` có thể cho kết quả khác nhau. Trong ví dụ chính, kết quả đầu không có annotation `Mark` trên declaration field; kết quả sau tìm `@Mark("outer")` trên kiểu `List`.

Annotation type có thể có nhiều target, ví dụ `@Target({FIELD, TYPE_USE})`. Khi đó vị trí trong cú pháp Java có thể áp dụng cho nhiều ngữ cảnh, và compiler có quy tắc lưu metadata vào những target thích hợp. Để tránh suy diễn từ dấu `@`, hãy kiểm tra khai báo target, cấu trúc Java và API mà bạn dùng để đọc.

**Quan trọng:** `@Retention(RUNTIME)` là điều kiện quan trọng để Reflection đọc type-use metadata. Nếu không khai báo `@Retention`, mặc định là `CLASS`: thông tin có thể nằm trong file `.class` nhưng không được phơi ra qua Reflection runtime tiêu chuẩn.

## 9. Type erasure có làm mất hết thông tin này không?

Java generics dùng *type erasure* để tạo những chữ ký runtime tương thích với mô hình JVM. Ví dụ, một `List<String>` khi thao tác bằng code runtime không được coi như một “reified object” mang toàn bộ type argument `String` trong mỗi instance.

Tuy nhiên, class file có thể giữ **Signature attribute** và annotation attributes trên các **khai báo**, nên Reflection vẫn có thể đọc cấu trúc generic của field, method return, superclass hoặc generic bounds mà compiler lưu lại.

Vì vậy hai câu sau có thể đồng thời đúng:

- Một object `new ArrayList<String>()` không tự bộc lộ toàn bộ type argument `String` chỉ bằng `object.getClass()`.
- Một field khai báo `List<@Mark String> names;` có thể để Reflection đọc được `List<String>` và annotation trên type argument `String` qua `Field.getAnnotatedType()`.

**Nội dung metadata phụ thuộc vị trí khai báo và bytecode đã được biên dịch**, không thể kỳ vọng `getClass()` của một object bất kỳ luôn phục hồi mọi generic type argument được dùng ở nơi tạo object. Annotation `TYPE_USE` cũng không tự buộc JVM thực thi validation.

## 10. Kiểm chứng metadata trong bytecode bằng `javap`

Sau khi biên dịch ví dụ chính:

~~~bash
javap -v Catalog
~~~

Với retention `RUNTIME`, Java compiler có thể ghi metadata ở những thuộc tính như `RuntimeVisibleTypeAnnotations` trên field, method và phần khai báo generic. Kết quả `javap -v` có thể nêu target/type path khác nhau: kiểu ngoài `List`, type argument `String`, bound `Number`, bound của wildcard và annotated return type.

Những chi tiết hiển thị như chỉ số constant pool, bytecode offset hoặc ký hiệu target path có thể khác giữa các phiên bản toolchain. Điều cần kiểm tra là **các annotation nằm ở đúng vị trí type-use**. Không nên chép cứng output dài của `javap` vào ví dụ nếu môi trường đang dùng khác.

`javap` là công cụ xem metadata bytecode; Reflection dùng API Java để truy vấn những metadata mà runtime hỗ trợ. `Type` và `AnnotatedType` là hai góc nhìn khác nhau lên cấu trúc/annotation được lưu, không phải một API có thể tùy ý ép kiểu qua lại.

## 11. Cách chọn API khi làm việc thực tế

Bắt đầu từ **đối tượng khai báo** rồi chuyển sang phần cấu trúc cần đọc:

1. Nếu có một `Field`, quyết định bạn muốn đọc **annotation gắn trên field** hay **annotation của kiểu field**. Dùng `field.getAnnotation(...)` cho trường hợp thứ nhất; `field.getAnnotatedType()` cho trường hợp thứ hai.
2. Nếu có `Method`, dùng `method.getAnnotatedReturnType()` hoặc `method.getAnnotatedParameterTypes()` cho annotation tại vị trí type use. Dùng `method.getAnnotation(...)` khi annotation gắn vào declaration method.
3. Nếu có `Class<?>`, dùng `getAnnotatedSuperclass()` hoặc `getAnnotatedInterfaces()` khi cần annotations trên kiểu cha/interface đã khai báo; dùng `getAnnotation(...)` cho annotation declaration trên class.
4. Nếu có `TypeVariable<?>`, dùng `getAnnotation(...)` để đọc trên khai báo type parameter, `getAnnotatedBounds()` để đọc trên bound của type parameter.
5. Nếu annotated type là parameterized, array hoặc wildcard, đi sâu bằng interface chuyên biệt phù hợp. Kiểm tra kiểu runtime của đối tượng annotated trước khi cast để tránh `ClassCastException`.
6. Khi annotation có thể vắng mặt, kiểm tra `null`; khi collection của annotated children có thể rỗng, kiểm tra độ dài trước khi lấy index.

Cách viết chung cho trường hợp field là parameterized type:

~~~java
AnnotatedType type = field.getAnnotatedType();

if (type instanceof AnnotatedParameterizedType parameterized) {
    for (AnnotatedType argument :
            parameterized.getAnnotatedActualTypeArguments()) {
        Mark annotation = argument.getAnnotation(Mark.class);
        if (annotation != null) {
            System.out.println(annotation.value());
        }
    }
}
~~~

Đoạn trên là **mẫu minh họa trong ngữ cảnh đã có biến `field` và annotation `Mark`**; nó không tự chạy độc lập. Java 17 hỗ trợ cú pháp `instanceof` pattern variable. Nếu `field` chứa một array hoặc kiểu không parameterized, nhánh xử lý không chạy — điều này an toàn hơn việc ép kiểu vô điều kiện.

## 12. Sai lầm thường gặp

**1. Dùng `Type.getAnnotation(...)`.** `Type` không khai báo method này. Nếu cần type-use annotations, bắt đầu từ `AnnotatedType` nhận qua API annotated phù hợp.

**2. Chỉ lấy `getGenericType()` rồi kết luận không có annotation.** API trả `Type` chỉ cho cấu trúc; annotation trên type arguments vẫn có thể được giữ trong class file và đọc qua `getAnnotatedType()`.

**3. Đọc annotation trên kiểu ngoài khi nó nằm ở type argument.** `List<@Mark String>` có annotation trên `String`. Muốn đọc phải gọi `getAnnotatedActualTypeArguments()[0]` từ `AnnotatedParameterizedType`.

**4. Đọc `Field.getAnnotation(...)` khi annotation có target `TYPE_USE`.** Đây là truy vấn declaration metadata, không phải type-use metadata. Chọn `field.getAnnotatedType()` để đọc các annotation trên kiểu.

**5. Ép mọi `AnnotatedType` thành `AnnotatedParameterizedType`.** Nếu kiểu thực tế là class đơn, array hoặc wildcard, cast có thể sai. Dùng `instanceof` hoặc xác định cấu trúc trước.

**6. Bỏ qua nested type path.** Với `Map<String, List<@Mark Integer>>`, phải đi vào argument thứ hai của `Map`, rồi argument thứ nhất của `List` mới tới `Integer`. Không có quy tắc tự lan truyền annotation lên các node cha.

**7. Dùng `TypeVariable.getAnnotation(...)` để đọc annotation trên bound.** API đó đọc annotation tại khai báo `T`, còn annotation sau `extends` nằm trên type use của bound. Dùng `getAnnotatedBounds()`.

**8. Nhầm bound của wildcard với bound của type variable.** `? extends Number` được đọc qua `AnnotatedWildcardType`; `T extends Number` dùng `TypeVariable.getAnnotatedBounds()`. Hai cú pháp và đường đi Reflection khác nhau.

**9. Cho rằng Java sẽ dùng annotation để ép kiểu/validate.** Annotation không tự sửa type erasure, kiểm tra null, chặn giá trị hay tạo runtime behavior. Cần bộ xử lý hiểu annotation mới có logic bổ sung.

**10. Quên `@Retention(RUNTIME)`.** Annotation có target `TYPE_USE` nhưng retention mặc định `CLASS` vẫn không thể được đọc qua Reflection runtime tiêu chuẩn.

**11. Tưởng generic type arguments luôn khôi phục được từ instance.** Những thông tin đó chỉ có thể phản chiếu ở các khai báo/kiểu nơi compiler lưu metadata; `object.getClass()` không lưu đầy đủ mọi type argument được dùng để tạo object.

**12. Nhầm `@Target(TYPE_USE)` với `@Target(TYPE)`.** `TYPE` nhắm khai báo class/interface/enum/annotation type; `TYPE_USE` nhắm các chỗ dùng kiểu. Phải khai báo target đúng mục đích.

## 13. Bài tập tự luyện

1. **Cấu trúc:** Khai báo `List<String> names;`. Dùng `Field.getType()`, `Field.getGenericType()` và `Field.getAnnotatedType().getType()`; đối chiếu phần thông tin mỗi API cho biết.
2. **Annotation type argument:** Đổi thành `List<@Mark("element") String>`. Dự đoán `getAnnotation(Mark.class)` trên field declaration, annotated outer type và annotated argument.
3. **Nested generics:** Thử `Map<@Mark("key") String, List<@Mark("nested") Integer>>`. Dùng `AnnotatedParameterizedType` nhiều lần để đọc hai annotation ở đúng type arguments.
4. **Wildcard:** Tạo field `List<? extends @Mark("limit") Number>`. Dùng `AnnotatedWildcardType.getAnnotatedUpperBounds()`, sau đó đổi sang `? super @Mark("floor") Integer` và dùng lower bounds.
5. **Type variable:** Tạo `class NumberBox<T extends @Mark("number") Number>`. Dùng `getTypeParameters()[0].getAnnotatedBounds()[0]`, so sánh với `getBounds()[0]`.
6. **Khai báo và type use:** Tạo một annotation target `FIELD` khác `Mark` target `TYPE_USE`; gắn cả hai lên một field. Đọc riêng qua `Field.getAnnotation` và `Field.getAnnotatedType`.
7. **Kiểu mảng:** Tạo field với `String @Mark("array") []`. Duyệt `AnnotatedArrayType` tới component type, quan sát chính xác chỗ annotation được trả về.
8. **Method:** Tạo method trả `List<@Mark("output") String>` và nhận `List<@Mark("input") Integer>`; so sánh `getGenericReturnType`/`getAnnotatedReturnType` và `getGenericParameterTypes`/`getAnnotatedParameterTypes`.
9. **Erasure:** Tạo `new ArrayList<String>()` và in `getClass()`, sau đó so với metadata trên field khai báo `List<String>` để thấy không thể suy ra mọi type arguments từ runtime object.
10. **Bytecode:** Chạy `javap -v Catalog`. Tìm các annotation type-use và vị trí bound/type argument; đối chiếu với từng dòng stdout của chương trình chính.

## 14. Checklist ghi nhớ

- **`Type`**: kiểu gì, cấu trúc generic ra sao; API chủ yếu như `getTypeName()`, `ParameterizedType.getActualTypeArguments()`, `TypeVariable.getBounds()`.
- **`AnnotatedType`**: type-use position nào và annotation gắn lên chính vị trí đó; có `getType()` cùng annotation API.
- **`Field.getGenericType()`** và **`Field.getAnnotatedType()`** trả hai góc nhìn khác nhau về cùng kiểu field.
- **`AnnotatedParameterizedType`**: đi vào annotated type arguments.
- **`AnnotatedWildcardType`**: đi vào annotated upper/lower bounds của wildcard.
- **`AnnotatedArrayType`**: đi vào annotated component type của array.
- **`TypeVariable.getAnnotatedBounds()`**: đọc annotation trên các bounds của một tham số kiểu.
- **`Method.getAnnotatedReturnType()`** và **`getAnnotatedParameterTypes()`**: đọc tại chỗ dùng kiểu trong chữ ký method.
- **`@Retention(RUNTIME)`** và **`@Target(TYPE_USE)`** là hai lựa chọn quan trọng để annotation trên kiểu có thể được truy vấn bằng Reflection lúc chạy.
- Annotation gắn vào **declaration** và annotation gắn vào **type use** cần được phân biệt bằng vị trí cú pháp và API đọc phù hợp.

Hiểu đúng hai interface này giúp phân tích metadata generics một cách chính xác, nhất là khi làm việc với thư viện validation, static analysis hoặc những framework xử lý annotation sâu trong cấu trúc kiểu.

### Tham khảo

- [Java SE 17 — Type](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html).
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [Java SE 17 — AnnotatedWildcardType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html).
- [Java SE 17 — TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java Language Specification 17 — `9.7.4, Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).
