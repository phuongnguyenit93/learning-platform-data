# Kiểm thử runtime annotation, repeatable và type-use annotation trong Java Reflection

Annotation trong Java là metadata gắn lên khai báo hoặc vị trí sử dụng kiểu. Khi viết công cụ dựa trên Reflection, chỉ thấy cú pháp `@Something` trong mã nguồn **không đủ** để kết luận ứng dụng sẽ đọc được annotation đó ở runtime. Kết quả còn phụ thuộc `@Retention`, `@Target`, việc annotation được lặp lại hay không, **vị trí** đặt annotation và API Reflection dùng để đọc.

Bài này hướng dẫn thiết kế phép kiểm thử tự động cho ba trường hợp dễ nhầm:

1. **Runtime annotation:** annotation có thật sự tồn tại ở runtime, và trên đúng phần tử dự kiến?
2. **Repeatable annotation:** khai báo nhiều lần có được truy xuất đầy đủ bằng `getAnnotationsByType`?
3. **Type-use annotation:** metadata gắn lên *vị trí sử dụng kiểu* (kiểu trả về, tham số kiểu, đối số generic, mảng…) có được tìm bằng nhóm API `AnnotatedType` thay vì chỉ đọc annotation của phần tử khai báo?

Ví dụ chạy trên **Java 17+**, không cần thư viện ngoài. Ngoài ra, bài phân biệt rõ các trường hợp cần dùng JUnit hoặc chạy kiểm thử trên chính artifact được đóng gói khi xây dựng công cụ thật.

## 1. Ba yếu tố quyết định annotation có đọc được hay không

Một annotation có thể có ba cấu hình liên quan:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {
    String value();
}
```

- **`@Retention`** quyết định annotation còn được lưu đến đâu.
- **`@Target`** quy định các vị trí hợp lệ để đặt annotation.
- **`@Repeatable`** cho phép khai báo nhiều instance của cùng annotation type trên một phần tử/vị trí hợp lệ, bằng một container annotation tương thích.

### Retention policy

| Chính sách | Compiler lưu giữ đến đâu? | Đọc bằng Core Reflection lúc chạy? |
|---|---|---|
| `RetentionPolicy.SOURCE` | Chỉ phục vụ mã nguồn, không có nghĩa vụ xuất hiện trong class file | Không |
| `RetentionPolicy.CLASS` | Lưu trong class file (mặc định khi không ghi `@Retention`), nhưng JVM không bắt buộc giữ để Reflection đọc | **Không** qua API runtime annotation chuẩn |
| `RetentionPolicy.RUNTIME` | Được giữ để JVM cung cấp qua Reflection | **Có**, khi metadata còn tồn tại và đọc tại đúng vị trí |

Một class file chứa annotation `CLASS` **không có nghĩa** `Class.getAnnotation(...)` phải trả về đối tượng annotation. Kiểm thử runtime phải dùng `@Retention(RUNTIME)` nếu framework cần đọc annotation khi chạy.

### Target

Ví dụ các target phổ biến:

- `ElementType.TYPE`: khai báo class, interface, enum, record hoặc một số dạng khai báo kiểu.
- `ElementType.METHOD`, `FIELD`, `CONSTRUCTOR`: phần tử khai báo tương ứng.
- `ElementType.PARAMETER`: **khai báo tham số** của method/constructor.
- `ElementType.TYPE_USE`: **vị trí sử dụng kiểu**, chẳng hạn `List<@Mark String>`, kiểu trả về, kiểu tham số, thành phần mảng, superclass được dùng.
- `ElementType.TYPE_PARAMETER`: khai báo tham số kiểu như `class Box<@Mark T>`.

**Khác nhau quan trọng:** annotation có `@Target(PARAMETER)` được đọc ở nhóm API annotation của parameter declaration, còn annotation có `@Target(TYPE_USE)` đặt trên *kiểu của tham số* cần đọc qua `getAnnotatedParameterTypes()`. Nếu annotation có nhiều target, hãy xét chính xác nơi nó xuất hiện và metadata được compiler ghi.

## 2. Kiểm thử runtime annotation: khai báo và đọc đúng vị trí

Với:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeInfo {
    String value();
}

@RuntimeInfo("active")
class Plugin {}
```

Một kiểm thử cần xác nhận cả **hiện diện** lẫn **giá trị**:

```java
RuntimeInfo info = Plugin.class.getAnnotation(RuntimeInfo.class);
if (info == null || !info.value().equals("active")) {
    throw new AssertionError("Missing or incorrect runtime annotation");
}
```

Đây là hai mảnh mã minh họa có thể được đặt cùng một chương trình Java thích hợp. Những câu lệnh chỉ kiểm tra `info != null` không phát hiện trường hợp annotation còn tồn tại nhưng các thuộc tính quan trọng bị sai. Nếu annotation tạo contract cho plugin, hãy kiểm tra cả method/class đích, thuộc tính bắt buộc và cách framework ánh xạ chúng thành hành vi.

Các API thường gặp:

| API | Trả về | Lưu ý |
|---|---|---|
| `Class.getAnnotation(A.class)` | Một annotation thuộc loại `A` hoặc `null` | Có xét annotation được kế thừa trên class khi `A` có `@Inherited` theo quy tắc API |
| `Class.getDeclaredAnnotation(A.class)` | Annotation được khai báo trực tiếp hoặc `null` | Không lấy annotation chỉ do kế thừa |
| `isAnnotationPresent(A.class)` | Boolean | Phản ánh ngữ nghĩa hiện diện của API; không trả giá trị annotation |
| `getAnnotations()` | Các annotation hiện diện theo quy tắc kế thừa | Không tự “bung” mọi container repeatable |
| `getDeclaredAnnotations()` | Annotation trực tiếp | Có thể chứa container annotation của repeatable |
| `Method.getAnnotation(A.class)` | Annotation method | Khác với annotation gắn trên **kiểu trả về** |

`@Inherited` áp dụng cho kế thừa annotation ở **khai báo class**, không tự áp dụng cho method, interface hoặc annotation type-use. Dù có `@Inherited`, một method override cũng không tự “thừa kế” method annotation bằng quy tắc đó; framework muốn tìm từ superclass/interface phải tự định nghĩa thuật toán.

## 3. Repeatable annotation: “nhìn thấy container” không phải đã đọc hết

Repeatable annotation phải có một container phù hợp:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("fast")
@Label("safe")
class Handler {}
```

Compiler biểu diễn các `@Label` lặp lại thông qua container `@Labels` (với nhiều annotation cùng loại tại một vị trí). Vì thế:

- `Handler.class.getAnnotationsByType(Label.class)` lấy đủ **hai** `Label`, theo thứ tự có thể quan sát từ khai báo.
- `Handler.class.getAnnotation(Label.class)` trong trường hợp chỉ có hai `Label` được chứa gián tiếp thường trả `null`, vì API này **không tự mở container**.
- `Handler.class.getAnnotation(Labels.class)` cho thấy container được lưu tại runtime.
- `getDeclaredAnnotationsByType(Label.class)` là lựa chọn tốt khi muốn **chỉ** đọc annotation liên quan trực tiếp đến class đang kiểm tra.

Các ràng buộc quan trọng của container:

1. Container có một element `value()` trả về mảng kiểu annotation lặp lại (ví dụ `Label[]`).
2. `@Retention` và `@Target` của container phải tương thích với annotation lặp lại theo luật Java; không thể tùy tiện chọn container có retention ngắn hơn.
3. Nếu muốn truy xuất repeatable annotation ở runtime, cả repeatable type và container phải được thiết kế/đóng gói phù hợp để Reflection thấy được.
4. Nếu cần kế thừa repeatable class annotation, kiểm tra riêng cả repeatable type và container liên quan đến `@Inherited`. Đừng dùng kiểm thử trên một class đơn lẻ để suy ra hành vi của subclass.
5. Không dùng `getAnnotation(Label.class)` làm phép thử duy nhất cho repeatable; dùng `getAnnotationsByType(Label.class)` hoặc `getDeclaredAnnotationsByType(Label.class)`.

**Chú ý:** API `getAnnotationsByType` hỗ trợ cả trường hợp chỉ một annotation và trường hợp container gián tiếp. Nó phù hợp hơn khi một annotation type được định nghĩa là repeatable. Đừng hard-code tên container trong ứng dụng nếu API by-type đã giải quyết đúng nhu cầu.

## 4. Type-use annotation: đọc qua AnnotatedType

Xét:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeHint {
    String value();
}
```

Với method:

```java
public @TypeHint("return") List<@TypeHint("element") String> names(
        @TypeHint("parameter-type") String input) {
    return List.of(input);
}
```

Đây là **mảnh mã minh họa**: method cần được đặt trong class cùng với import `java.util.List` và định nghĩa `TypeHint` ở trên.

Có ít nhất ba vị trí metadata khác nhau:

- `@TypeHint("return")` gắn trên **kiểu trả về** là `List<String>`.
- `@TypeHint("element")` gắn trên **đối số kiểu generic** `String` nằm trong `List<...>`.
- `@TypeHint("parameter-type")` gắn trên **kiểu của tham số** `String`.

Để đọc đúng:

```java
Method m = SomeClass.class.getDeclaredMethod("names", String.class);

AnnotatedType result = m.getAnnotatedReturnType();
TypeHint onReturn = result.getAnnotation(TypeHint.class);

AnnotatedParameterizedType generic =
        (AnnotatedParameterizedType) result;
TypeHint onElement = generic.getAnnotatedActualTypeArguments()[0]
        .getAnnotation(TypeHint.class);

TypeHint onParameter = m.getAnnotatedParameterTypes()[0]
        .getAnnotation(TypeHint.class);
```

Đoạn này giả định `SomeClass` khai báo method phù hợp. Thao tác `getAnnotatedActualTypeArguments()` đi sâu vào cấu trúc generic. Nếu runtime type không phải `AnnotatedParameterizedType`, cần kiểm tra bằng `instanceof` thay vì cast tùy tiện.

**Các nhầm lẫn thường gặp:**

- `m.getAnnotation(TypeHint.class)` tìm annotation gắn trên **khai báo method**, không tìm annotation gắn trên **kiểu trả về**.
- `m.getParameterAnnotations()[0]` đọc annotation khai báo parameter. Với `TypeHint` chỉ có target `TYPE_USE`, ở ví dụ trên danh sách declaration annotation của parameter có thể rỗng — đây là hành vi đúng.
- `m.getReturnType()` chỉ trả về `Class<?>` của kiểu trả về (ví dụ `List.class`); nó không cung cấp vị trí annotation của `List<@TypeHint String>`.
- `m.getGenericReturnType()` trả biểu diễn kiểu generic, nhưng để lấy **type-use annotation**, cần cấu trúc `AnnotatedType` tương ứng.

Một số API bổ sung khi xây công cụ đọc metadata chuyên sâu:

| Vị trí cần kiểm tra | API phù hợp |
|---|---|
| Kiểu của field | `Field.getAnnotatedType()` |
| Kiểu trả về method | `Method.getAnnotatedReturnType()` |
| Kiểu tham số method | `Method.getAnnotatedParameterTypes()` |
| Kiểu exception được khai báo | `Method.getAnnotatedExceptionTypes()` |
| Kiểu superclass/interface được dùng | `Class.getAnnotatedSuperclass()` / `getAnnotatedInterfaces()` |
| Đối số kiểu generic | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` |
| Thành phần mảng | `AnnotatedArrayType.getAnnotatedGenericComponentType()` |
| Biên của wildcard hoặc type variable | `AnnotatedWildcardType` / `AnnotatedTypeVariable` cùng API bound tương ứng |

Với `String @TypeHint []` và `@TypeHint String[]`, annotation có thể được đặt ở **các cấp kiểu khác nhau**. Không nên gom mọi annotation type-use thành một danh sách phẳng rồi mất vị trí. Kiểm thử phải đi sâu vào đúng nhánh `AnnotatedType`.

## 5. Chương trình Java 17+ kiểm thử cả ba trường hợp

Ví dụ dưới đây chạy độc lập và **không dùng `assert` của Java**, bởi `assert` thường bị tắt khi không chạy với `-ea`. Hàm `check` luôn ném `AssertionError` nếu kết quả Reflection sai.

Lưu thành **`AnnotationInspectionDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.List;

public class AnnotationInspectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface RuntimeInfo { String value(); }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface BuildOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Repeatable(Labels.class)
    @interface Label { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Labels { Label[] value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeHint { String value(); }

    @RuntimeInfo("present")
    @BuildOnly
    @Label("a")
    @Label("b")
    static class Example {
        public @TypeHint("return") List<@TypeHint("element") String> names(
                @TypeHint("parameter") String value) {
            return List.of(value);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Example.class;
        RuntimeInfo info = type.getAnnotation(RuntimeInfo.class);
        check(info != null && info.value().equals("present"), "runtime info");
        check(type.getAnnotation(BuildOnly.class) == null, "CLASS retention");
        Label[] labels = type.getAnnotationsByType(Label.class);
        check(labels.length == 2, "repeatable labels");
        check(type.getAnnotation(Label.class) == null, "indirectly present label");
        check(type.getAnnotation(Labels.class) != null, "container");
        Method method = type.getDeclaredMethod("names", String.class);
        AnnotatedType resultType = method.getAnnotatedReturnType();
        TypeHint resultHint = resultType.getAnnotation(TypeHint.class);
        AnnotatedType elementType =
                ((AnnotatedParameterizedType) resultType)
                        .getAnnotatedActualTypeArguments()[0];
        TypeHint elementHint = elementType.getAnnotation(TypeHint.class);
        TypeHint parameterHint = method.getAnnotatedParameterTypes()[0]
                .getAnnotation(TypeHint.class);
        check(resultHint != null && resultHint.value().equals("return"), "return type");
        check(elementHint != null && elementHint.value().equals("element"), "generic element");
        check(parameterHint != null && parameterHint.value().equals("parameter"), "parameter type");
        check(method.getParameterAnnotations()[0].length == 0,
                "TYPE_USE is not declaration PARAMETER");

        System.out.println("runtime class annotation = " + info.value());
        System.out.println("CLASS retention visible = "
                + (type.getAnnotation(BuildOnly.class) != null));
        System.out.println("repeatable values = "
                + labels[0].value() + ", " + labels[1].value());
        System.out.println("container present = "
                + (type.getAnnotation(Labels.class) != null));
        System.out.println("return type = " + resultHint.value());
        System.out.println("type argument = " + elementHint.value());
        System.out.println("parameter type = " + parameterHint.value());
        System.out.println("parameter declaration annotations = "
                + method.getParameterAnnotations()[0].length);
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 AnnotationInspectionDemo.java
java AnnotationInspectionDemo
```

**Stdout thực tế của ví dụ:**

```text
runtime class annotation = present
CLASS retention visible = false
repeatable values = a, b
container present = true
return type = return
type argument = element
parameter type = parameter
parameter declaration annotations = 0
ALL CHECKS PASSED
```

Mã đã được kiểm chứng bằng `javac --release 17` trên JDK mới hơn và chạy thành công với thứ tự stdout trên.

### Đọc kết quả theo từng trường hợp

1. `RuntimeInfo` có `RetentionPolicy.RUNTIME` nên `getAnnotation(RuntimeInfo.class)` trả về instance với giá trị `present`.
2. `BuildOnly` chỉ có `RetentionPolicy.CLASS` nên `getAnnotation(BuildOnly.class)` trả `null` dù annotation có trong mã nguồn.
3. Hai `@Label` cùng gắn trên class được gom vào container `@Labels`. Vì vậy `getAnnotationsByType(Label.class)` trả hai instance, còn `getAnnotation(Label.class)` trả `null` ở trường hợp lặp này.
4. `getAnnotatedReturnType()` tìm `return` trên kiểu trả về; `AnnotatedParameterizedType` tìm `element` trên `String` là đối số generic.
5. `getAnnotatedParameterTypes()[0]` đọc `parameter` trên **kiểu** tham số. `getParameterAnnotations()[0]` rỗng vì annotation được khai báo chỉ cho `TYPE_USE`.
6. Dòng `ALL CHECKS PASSED` chỉ xuất hiện sau khi mọi điều kiện bắt buộc đều đúng. Nếu đổi retention/target, xóa container hoặc dùng sai API, kiểm thử sẽ thất bại hoặc compiler từ chối định nghĩa không hợp lệ.

## 6. Biến phép kiểm thử thành bộ test tự động

Trong hệ thống có CI, không chỉ kiểm tra stdout. Hãy chuyển các điều kiện `check(...)` thành những assertion của JUnit 5 (JUnit Jupiter), chạy cùng artifact và dependencies mà ứng dụng thực sự sử dụng.

Ví dụ minh họa một test method trong class kiểm thử:

```java
@Test
void repeatableAnnotationsAreVisible() {
    Label[] labels = Example.class.getAnnotationsByType(Label.class);
    assertEquals(2, labels.length);
    assertEquals("a", labels[0].value());
    assertEquals("b", labels[1].value());
}
```

Đoạn trên **không phải chương trình độc lập**: giả định có import `org.junit.jupiter.api.Test`, static import `org.junit.jupiter.api.Assertions.assertEquals` và định nghĩa `Example`/`Label` phù hợp trong phạm vi truy cập. Với JUnit, test thất bại khi annotation mất hoặc giá trị khác. Dùng test tương tự cho `getAnnotatedReturnType()`, `getAnnotatedParameterTypes()` và việc `CLASS` annotation **không** được truy xuất bằng Reflection.

### Những kiểm tra có giá trị cao

- **Retention:** `RUNTIME` hiện diện; `CLASS` và `SOURCE` không có trong API runtime.
- **Target và vị trí:** class/method/field/parameter declaration/type-use được đọc bằng API tương ứng.
- **Repeatable:** số lượng, giá trị, container, phân biệt `getAnnotation` và `getAnnotationsByType`.
- **Declared vs inherited:** kiểm thử trên class con với `@Inherited`; không suy hành vi của interface hoặc method.
- **Nested types:** `List<@A String>`, `Map<@A String, @B Integer>`, array, wildcard, bounds — kiểm tra đúng nhánh `AnnotatedType`.
- **Thứ tự và tính xác định:** nếu hệ thống phụ thuộc thứ tự annotation được lặp lại, viết test với các giá trị phân biệt, không chỉ đếm số lượng.
- **Khả năng đóng gói:** lặp lại test trên JAR/module/artifact sau shading, shrinking hoặc obfuscation nếu có; annotation và phần tử cần thiết có thể bị đổi/loại bỏ bởi công cụ build.

### Test âm tính rất quan trọng

Đừng chỉ khẳng định “tìm thấy”. Hãy khẳng định những thứ **không được xem là hợp lệ**:

```java
if (Example.class.getAnnotation(BuildOnly.class) != null) {
    throw new AssertionError("CLASS annotation unexpectedly visible");
}
if (Example.class.getAnnotation(Label.class) != null) {
    throw new AssertionError("Expected repeatable container lookup semantics");
}
```

Đây là đoạn kiểm tra minh họa trong cùng phạm vi ví dụ trước. Nó bảo vệ khỏi giả định sai về retention và repeatable lookup. Không nên dựa vào behavior đặc thù của một IDE hoặc việc nhìn thấy annotation trong decompiler để kết luận `Class.getAnnotation` sẽ trả giá trị.

## 7. Kế thừa annotation và cấu trúc type-use phức tạp

### `@Inherited` không thay thế test discovery riêng

Với class annotation đánh dấu `@Inherited`, `Sub.class.getAnnotationsByType(...)` có thể nhìn thấy annotation từ superclass theo quy tắc hiện diện/kế thừa của API, còn `getDeclaredAnnotationsByType(...)` chỉ lấy annotation trên chính `Sub`. Nếu `Sub` khai báo annotation cùng repeatable type, kết quả cũng chịu quy tắc che khuất và liên kết với container, không nên mặc định nối mọi annotation superclass và subclass thành một danh sách chung.

Đừng áp dụng `@Inherited` cho annotation trên interface hoặc method rồi kỳ vọng Reflection tự kết hợp metadata theo cây kế thừa. Với các framework có cơ chế merge annotation riêng, test cả **Core Reflection behavior** lẫn **framework discovery behavior**, vì chúng có thể khác nhau.

### `AnnotatedType` là cây, không phải chuỗi tên

Nếu một công cụ validator đọc:

```java
List<@TypeHint("item") String>
```

metadata nằm ở **đối số generic**; nếu đọc mỗi `List.class.getAnnotations()` sẽ không thấy annotation trên `String`. Với nested generic:

```java
Map<String, List<@TypeHint("leaf") Integer>>
```

phải duyệt `AnnotatedParameterizedType` theo từng cấp, đi đến đối số thứ hai của `Map` rồi đối số đầu tiên của `List`. Các đoạn trên là **kiểu minh họa**, không phải khai báo Java đầy đủ. Nếu cấu trúc là wildcard, mảng hoặc type variable, cần dùng subtype của `AnnotatedType` tương ứng. Bộ kiểm thử nên tạo fixture riêng cho mỗi hình dạng mà công cụ hỗ trợ và khẳng định annotation tại từng vị trí.

## 8. Lỗi thường gặp và hướng sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `getAnnotation(A.class) == null` | Retention không phải RUNTIME, sai target/vị trí, annotation bị mất trong artifact | Xem định nghĩa `@Retention`; chọn đúng element và API |
| Có hai annotation nhưng `getAnnotation(A.class)` trả null | Repeatable được chứa gián tiếp trong container | Gọi `getAnnotationsByType(A.class)` |
| `getParameterAnnotations()` rỗng nhưng mã nguồn có `@A String` | Annotation chỉ dùng cho `TYPE_USE` | Gọi `getAnnotatedParameterTypes()` |
| Không tìm thấy annotation ở `List<@A String>` | Đọc type declaration hoặc return type gốc, chưa đi sâu generic | Dùng `AnnotatedParameterizedType` |
| Test thấy annotation ở superclass nhưng không ở subclass | Dùng API declared hoặc sai giả định về `@Inherited` | Tách test present/declared/inherited |
| Annotation có trong source nhưng runtime build không có | Shrinker/obfuscator loại metadata hoặc định nghĩa annotation | Test trên artifact phát hành; cấu hình keep rules phù hợp |
| `ClassCastException` khi cast `AnnotatedType` | Kiểu thực tế không phải parameterized type | Kiểm tra `instanceof` rồi duyệt theo hình dạng |
| Giá trị annotation khác kỳ vọng | Sai default/member values hoặc dùng sai type/vị trí | Assert cả giá trị, không chỉ `isAnnotationPresent` |
| Kết quả thay đổi khi dùng framework | Framework có thuật toán merge/search khác Core Reflection | Viết test độc lập cho cả Reflection và framework |

Cần phân biệt *annotation không xuất hiện* với *không đọc được class/method* do class loading hoặc access/module issue. `getDeclaredMethods()` có thể ném lỗi linkage nếu dependency cần thiết vắng mặt; đó không phải bằng chứng annotation bị thiếu.

## 9. Checklist chất lượng cho công cụ đọc annotation

Trước khi phát hành một annotation scanner/validator, nên xác minh:

1. Annotation type có `RUNTIME` retention khi runtime discovery là yêu cầu.
2. Target cho phép đúng element và vị trí sử dụng kiểu.
3. Repeatable annotation có container hợp lệ, và scanner dùng by-type API.
4. Scanner phân biệt direct, declared và inherited metadata.
5. Scanner đi đúng cấu trúc `AnnotatedType` cho generic, mảng, bounds, wildcard.
6. Không suy ra annotation ở method declaration từ annotation ở return type hoặc ngược lại.
7. Test cả trường hợp hiện diện, vắng mặt, sai giá trị, sai cấu trúc và class/container metadata bị mất.
8. CI chạy trên JDK và artifact phù hợp môi trường triển khai; nếu có transformer/shrinker thì chạy cả bản đã biến đổi.
9. Không lấy thứ tự của `getDeclaredMethods()` hoặc `getDeclaredAnnotations()` làm API contract nếu thứ tự đó không được bảo đảm.
10. Báo lỗi có thông tin class, method, vị trí kiểu và annotation name, để developer biết chính xác fixture nào không đúng.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Annotation khai báo `@Retention(CLASS)` có thể xuất hiện trong class file. Vì sao `getAnnotation` không lấy được?

Vì `CLASS` retention không yêu cầu annotation được giữ cho Core Reflection lúc chạy; muốn API runtime thấy nó phải dùng `RUNTIME`.

**Câu 2.** Hai lần `@Label` ở cùng class có thể trả `null` khi gọi `getAnnotation(Label.class)`. Có nghĩa chúng đã mất?

Không. Chúng có thể được đại diện gián tiếp bằng container. Dùng `getAnnotationsByType(Label.class)` để lấy đầy đủ.

**Câu 3.** `getParameterAnnotations()` và `getAnnotatedParameterTypes()` có giống nhau?

Không. API đầu đọc annotation của khai báo tham số; API sau đọc annotation trên **kiểu tham số**.

**Câu 4.** Muốn đọc `@A` trong `List<@A String>` thì gọi `List.class.getAnnotation(A.class)` được không?

Không. `@A` ở **type argument String** tại vị trí dùng kiểu, không trên khai báo `java.util.List`. Phải duyệt `AnnotatedParameterizedType`.

**Câu 5.** Vì sao cần kiểm thử repeatable annotation và type-use trên artifact đã đóng gói?

Vì shrinker/obfuscation, classpath, module hoặc transform bytecode có thể ảnh hưởng thành viên và metadata runtime; test source/debug chưa chắc phản ánh môi trường phát hành.

## Tài liệu tham khảo

- Java SE 17 API: [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html), [`Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html), [`Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html).
- Java SE 17 API: [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html), [`AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [`AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- Java Language Specification §9.6–§9.7: annotation types, repeatable annotations, applicability; §9.6.4.2–§9.6.4.3: retention và target; §9.6.4.3 và các quy tắc liên quan đến repeatable/container theo phiên bản JLS.

**Ghi nhớ:** Muốn kiểm thử annotation bằng Reflection, luôn hỏi **“annotation có RUNTIME retention không, được đặt tại loại vị trí nào, và có phải repeatable hay type-use không?”**. Câu trả lời xác định API đúng: `getAnnotation` cho metadata trực tiếp thông thường, `getAnnotationsByType` cho repeatable, và cây `AnnotatedType` cho annotation trên vị trí sử dụng kiểu.
