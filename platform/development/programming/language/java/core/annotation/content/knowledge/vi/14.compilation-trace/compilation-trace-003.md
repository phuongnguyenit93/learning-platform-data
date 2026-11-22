# Thuộc tính annotation của tham số và kiểu sử dụng trong tệp .class Java

Sau khi Java biên dịch mã nguồn, annotation không đơn thuần được lưu như những dòng bắt đầu bằng ký tự `@`. Những annotation được giữ lại sẽ trở thành **metadata trong các thuộc tính (attributes) của tệp `.class`**. Với **tham số khai báo** và **vị trí sử dụng kiểu**, Java Virtual Machine Specification (JVMS) định nghĩa những nhóm thuộc tính khác nhau.

Chủ đề này giải thích cách đọc dấu vết biên dịch của:

- Annotation gắn trên **khai báo tham số** của method hoặc constructor, chẳng hạn `@RequestId String id` với annotation có `@Target(PARAMETER)`.
- Annotation gắn trên **kiểu của tham số** hoặc kiểu con bên trong, chẳng hạn `@NonNull String id` hay `List<@NonNull String>` với annotation có `@Target(TYPE_USE)`.
- Sự khác biệt giữa retention `RUNTIME`, `CLASS`, `SOURCE` khi xem bằng `javap -v` và bằng Java reflection.

Đây là kiến thức giúp trả lời hai câu hỏi dễ nhầm: *“Vì sao `javap` thấy annotation mà reflection không đọc được?”* và *“Vì sao gọi `Parameter.getAnnotation()` không thấy annotation nằm trên kiểu tham số?”*

## 1. Hai loại vị trí: khai báo tham số và sử dụng kiểu

Xét ví dụ minh họa:

```java
void register(
        @InputName("user-id")
        @TypeLabel("value-type") String userId,
        java.util.List<@TypeLabel("element-type") String> groups) {
    // Xử lý dữ liệu trong ứng dụng.
}
```

Đây **chưa phải chương trình độc lập**: cần định nghĩa hai annotation và đặt method trong một class.

Các vị trí ở đây khác nhau:

| Cú pháp | Đối tượng được annotate | `ElementType` cần có |
| --- | --- | --- |
| `@InputName("user-id")` trên tham số `userId` | Khai báo **formal parameter** | `PARAMETER` |
| `@TypeLabel("value-type") String` | Lần **sử dụng kiểu `String`** của tham số | `TYPE_USE` |
| `List<@TypeLabel("element-type") String>` | Đối số kiểu generic `String` lồng bên trong `List` | `TYPE_USE` |

**Tham số khai báo** là biến xuất hiện trong danh sách tham số của method hoặc constructor. **Kiểu sử dụng** là một vị trí dùng một kiểu Java, có thể nằm tại chính kiểu tham số, bên trong đối số generic, ở thành phần mảng, ở kiểu trả về, ở wildcard, v.v.

Vì một annotation chỉ có `@Target(PARAMETER)` không được phép dùng ở mọi vị trí `TYPE_USE`, bạn không thể tự lấy nó để đánh dấu `List<@InputName String>`. Ngược lại, một annotation chỉ có `TYPE_USE` không phải annotation khai báo tham số, dù cú pháp nhìn khá gần tên tham số.

### Khai báo hai annotation minh họa

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputName {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeLabel {
    String value();
}
```

Đây là các định nghĩa hợp lệ có thể đặt trong cùng package. Chúng chỉ mô tả metadata; không tự kiểm tra giá trị chuỗi hay thực thi validation.

**Một điều cần nhớ:** khi một annotation được khai báo cho **cả** `PARAMETER` và `TYPE_USE`, một vị trí cú pháp trên tham số có thể mang ý nghĩa cho cả khai báo lẫn kiểu sử dụng theo các quy tắc *applicability* của Java. Để dễ quan sát dấu vết biên dịch, ví dụ chính trong bài chủ động dùng **những annotation type riêng** cho hai loại target.

## 2. Bốn thuộc tính .class quan trọng nhất

Trong `.class`, JVM dành một nhóm attribute cho annotation trên khai báo formal parameter và nhóm khác cho annotation trên type-use:

| Attribute của class file | Nội dung | Retention | Vị trí thông thường |
| --- | --- | --- | --- |
| `RuntimeVisibleParameterAnnotations` | Annotation khai báo **tham số method/constructor** | `RUNTIME` | Trong `method_info` |
| `RuntimeInvisibleParameterAnnotations` | Annotation khai báo tham số không được reflection thông thường thấy | `CLASS` | Trong `method_info` |
| `RuntimeVisibleTypeAnnotations` | Annotation trên các **type uses** và một số type-parameter declarations | `RUNTIME` | Trong các cấu trúc thích hợp: `ClassFile`, `field_info`, `method_info` hoặc `Code` |
| `RuntimeInvisibleTypeAnnotations` | Type-use annotation được lưu trong bytecode nhưng không mở cho reflection thông thường | `CLASS` | Các vị trí tương ứng ở trên |

JVMS 17 mô tả chúng lần lượt tại **§4.7.18, §4.7.19, §4.7.20 và §4.7.21**.

Tên **Visible** và **Invisible** ở đây liên quan tới **runtime reflection thông thường**, không có nghĩa attribute bị ẩn khỏi `javap`. Cả hai nhóm đều có thể xem được qua công cụ phân tích class file.

Annotation với `RetentionPolicy.SOURCE` thông thường chỉ được trình biên dịch/công cụ xử lý ở mã nguồn và **không được ghi vào các runtime annotation attributes** nói trên.

### Đừng nhầm với các attribute khác

- `RuntimeVisibleAnnotations` / `RuntimeInvisibleAnnotations` (§4.7.16–17) lưu annotation **trên khai báo** class, field, method hoặc thành phần tương ứng — không phải cách riêng để định vị annotation của formal parameter.
- `AnnotationDefault` (§4.7.22) lưu **giá trị mặc định của element của một annotation type**, chẳng hạn `int retries() default 2;`; nó không nói về default value của tham số method thông thường.
- `MethodParameters` (§4.7.24) lưu thông tin về **tên và cờ của formal parameters** khi được biên dịch thích hợp, ví dụ bằng `javac -parameters`. Nó **khác** `RuntimeVisibleParameterAnnotations`.
- `Signature` (§4.7.9) chứa generic signature như `List<String>` trong những trường hợp cần thiết. Nó cho biết cấu trúc kiểu generic, còn `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` gắn metadata vào **vị trí trong cấu trúc đó**.

Một method có thể có nhiều attribute trên cùng `method_info`; mỗi attribute có mục đích riêng. Vì vậy, kiểm tra một attribute đơn lẻ không phải lúc nào cũng đủ để hiểu toàn bộ metadata.

## 3. ParameterAnnotations lưu thông tin như thế nào?

Đối với một method có formal parameter annotation, các attribute `RuntimeVisibleParameterAnnotations` hoặc `RuntimeInvisibleParameterAnnotations` chứa thông tin theo **tham số**.

Ở mức mô hình đơn giản, nội dung gồm:

```text
method_info
  RuntimeVisibleParameterAnnotations
    num_parameters
    parameter_annotations[0]
      annotation(s) của formal parameter thứ nhất
    parameter_annotations[1]
      annotation(s) của formal parameter thứ hai
    ...
```

Thông số và thứ tự ánh xạ tới descriptor được JVMS quy định. Bạn không cần tự parse bytecode để dùng annotation thông thường; các API như `Executable.getParameterAnnotations()` và `Parameter.getAnnotation(...)` thực hiện việc đọc metadata runtime phù hợp.

Một ví dụ với hai tham số:

```java
void transfer(
        @InputName("source") String from,
        @InputName("destination") String to) {
    // Chuyển dữ liệu.
}
```

Trong bytecode, `InputName` là annotation **của từng formal parameter**, không phải annotation gắn lên chính method `transfer`. Gọi `method.getAnnotation(InputName.class)` không lấy được những annotation đó; cần chọn tham số trước.

### Cảnh báo về tham số do compiler tạo

Một số constructor, inner class, enum hoặc mã biên dịch khác có thể chứa tham số synthetic/mandated hoặc các chi tiết mapping không hiển nhiên từ cú pháp nguồn. Khi viết công cụ xử lý bytecode, **không nên suy đoán rằng chỉ số tham số ở source luôn tương đương máy móc với mọi vị trí trong descriptor của mọi loại executable**. Hãy theo JVMS, Java reflection API và các cờ metadata phù hợp cho trường hợp thực tế.

Ví dụ chính bên dưới dùng **một method instance thông thường, một formal parameter**, để phép đối chiếu dễ quan sát.

## 4. TypeAnnotations lưu thông tin vị trí bằng target và đường đi kiểu

Khác với declaration annotations, type-use annotations cần xác định **annotation thuộc vị trí nào trong cây kiểu**.

Cấu trúc type annotation trong JVMS có hai thông tin cốt lõi:

1. **`target_type` / `target_info`:** loại vị trí được annotate, chẳng hạn kiểu tham số method, kiểu trả về method, thành phần kiểu field, cast, local-variable type, v.v.
2. **`type_path`:** đường đi sâu vào cấu trúc kiểu: thành phần mảng, kiểu lồng, bound của wildcard hoặc đối số kiểu generic.

Ví dụ một tham số:

```java
void accept(
        @TypeLabel("list") java.util.List<@TypeLabel("item") String> values) {
}
```

Đây là method **minh họa**, cần type annotation `TypeLabel` có `TYPE_USE`.

Trong kiểu tham số `List<String>`:

- Annotation `"list"` nằm **trên kiểu ngoài** của formal parameter.
- Annotation `"item"` nằm trên **type argument thứ 0** là `String`.

Khi xem bằng `javap -v`, đầu mục type annotation liên quan có thể được mô tả theo cách như:

```text
METHOD_FORMAL_PARAMETER, param_index=0
METHOD_FORMAL_PARAMETER, param_index=0, location=[TYPE_ARGUMENT(0)]
```

Đây là **các nhãn ý nghĩa điển hình**, không phải bản chép nguyên vẹn toàn bộ bytecode của một class. Chỉ số `param_index=0` xác định formal parameter đầu tiên. `location=[TYPE_ARGUMENT(0)]` cho biết đường đi tới type argument đầu tiên.

Với các vị trí khác, JVMS cũng dùng những loại đường đi như `ARRAY`, `INNER_TYPE`, `WILDCARD_BOUND` hoặc `TYPE_ARGUMENT`, tùy cấu trúc. Đường đi này cần thiết để phân biệt `List<@Label String>` với `@Label List<String>`.

### Vì sao type annotation có thể nằm trong Code?

Type annotations không chỉ xuất hiện ở chữ ký method/field. Ví dụ trong thân method có những **type uses** ở biểu thức, phép ép kiểu hoặc biến cục bộ theo quy tắc ngôn ngữ. JVMS cho phép `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` hiện diện trong `Code` attribute đối với các vị trí thuộc method body.

**Lưu ý phạm vi reflection:** không phải mọi type annotation được lưu trong `Code` đều có API reflection chuẩn để đọc từ đối tượng runtime theo từng local variable, biểu thức hoặc offset bytecode. `javap -v` và các công cụ phân tích class file phù hợp hữu ích hơn cho một số trường hợp như vậy.

## 5. Retention: SOURCE, CLASS và RUNTIME khác nhau thế nào?

`@Retention` chỉ định thời gian giữ lại annotation:

| Retention | Dấu vết sau biên dịch | Java reflection thông thường |
| --- | --- | --- |
| `SOURCE` | Không được lưu vào class file như runtime annotation attribute | Không đọc được |
| `CLASS` | Được lưu dưới dạng **RuntimeInvisible...** ở attribute phù hợp | Không đọc được theo cơ chế chuẩn |
| `RUNTIME` | Được lưu dưới dạng **RuntimeVisible...** ở attribute phù hợp | Có thể đọc bằng API reflection phù hợp |

Nếu **không ghi `@Retention`**, Java dùng mặc định `RetentionPolicy.CLASS`. Vì vậy, annotation có thể hiện ra khi chạy `javap -v` nhưng `getAnnotation()` trả về `null`.

Đây là sự khác biệt **có chủ đích trong mô hình JVM**, không phải lỗi ngẫu nhiên của reflection.

Cả target lẫn retention phải phù hợp:

- Annotation khai báo tham số: `@Target(PARAMETER)`; nếu `RUNTIME` thì được lưu theo nhóm visible parameter annotations.
- Annotation trên kiểu tham số hoặc đối số generic: `@Target(TYPE_USE)`; nếu `RUNTIME` thì dùng nhóm visible type annotations.
- Cùng một annotation type có thể cho phép nhiều target; lúc đó hãy xác định chính xác **vị trí mà nó thực sự được áp dụng** khi đọc metadata.

Một annotation có retention RUNTIME **không đảm bảo mọi `getAnnotation()` đều thấy nó**. Bạn còn phải gọi API trên **đúng `AnnotatedElement` hoặc `AnnotatedType`**.

## 6. Ví dụ Java 17+ độc lập: bốn class-file attributes cùng lúc

Tạo đúng một tệp **`ParameterTraceDemo.java`** với toàn bộ code dưới đây. Ví dụ đã được biên dịch và chạy bằng `javac` và `java`, đồng thời được kiểm tra bằng `javap -v`.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface ParamRuntime {
    String value();
}

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.CLASS)
@interface ParamClass {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface TypeRuntime {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.CLASS)
@interface TypeClass {
    String value();
}

class Service {
    public void accept(
            @ParamRuntime("declaration")
            @ParamClass("stored-in-class")
            @TypeRuntime("list-type")
            @TypeClass("hidden-type")
            List<@TypeRuntime("element-type") String> values) {
        System.out.println(values.size());
    }
}

public class ParameterTraceDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Method method = Service.class.getDeclaredMethod("accept", List.class);
        Parameter parameter = method.getParameters()[0];

        System.out.println("parameter=" +
                parameter.getAnnotation(ParamRuntime.class).value());

        System.out.println("class-parameter-visible=" +
                (parameter.getAnnotation(ParamClass.class) != null));

        AnnotatedParameterizedType type = (AnnotatedParameterizedType)
                parameter.getAnnotatedType();

        System.out.println("type=" +
                type.getAnnotation(TypeRuntime.class).value());

        System.out.println("element=" +
                type.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeRuntime.class).value());

        System.out.println("class-type-visible=" +
                (type.getAnnotation(TypeClass.class) != null));

        System.out.println("parameter-name=" + parameter.getName());
    }
}
```

Chạy từ thư mục chứa tệp, với JDK 17 trở lên:

```bash
javac -parameters -encoding UTF-8 ParameterTraceDemo.java
java ParameterTraceDemo
```

**Stdout chính xác** (khi biên dịch với cờ `-parameters` như trên):

```text
parameter=declaration
class-parameter-visible=false
type=list-type
element=element-type
class-type-visible=false
parameter-name=values
```

Phân tích từng dòng:

1. `parameter=declaration`: `@ParamRuntime` thuộc `PARAMETER` và retention `RUNTIME`, nên đọc được bằng `Parameter.getAnnotation()`.
2. `class-parameter-visible=false`: `@ParamClass` vẫn được biên dịch vào bytecode (CLASS retention), nhưng không được Java reflection thông thường hiển thị.
3. `type=list-type`: `@TypeRuntime("list-type")` thuộc vị trí **dùng kiểu `List<...>`** của formal parameter. Phải đọc `Parameter.getAnnotatedType()` thay vì chỉ đọc annotation trực tiếp trên `Parameter`.
4. `element=element-type`: `@TypeRuntime("element-type")` nằm trên đối số kiểu `String`. Phải đi sâu bằng `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.
5. `class-type-visible=false`: `@TypeClass` nằm trong nhóm type annotations với retention CLASS, vì vậy không được lấy bằng reflection runtime thông thường.
6. `parameter-name=values`: tên `values` được giữ khi sử dụng `-parameters`. Nó thuộc metadata tên tham số, **không phải** nội dung các parameter/type annotations.

Tất cả annotation type ở ví dụ này chỉ là marker có một element `String value()`. JVM không biến chúng thành quy tắc xử lý tham số. `Service.accept()` được khai báo nhưng không gọi trong `main`; dòng `System.out.println(values.size())` trong thân method **không xuất hiện** ở stdout trên.

### Mở dấu vết .class bằng javap -v

Sau khi `javac` thành công, chạy:

```bash
javap -v -p Service
```

Lệnh này là bước **xem chi tiết class file**, không phải chạy `main`. Trong phần method `accept(java.util.List<java.lang.String>)` hoặc chữ ký/descriptor tương ứng, tìm bốn attribute:

```text
RuntimeVisibleTypeAnnotations
RuntimeInvisibleTypeAnnotations
RuntimeVisibleParameterAnnotations
RuntimeInvisibleParameterAnnotations
```

Bốn tên trên là **những đầu mục cần tìm**, không phải toàn bộ output nguyên văn của `javap`: thứ tự, constant-pool index, số dòng và cách trình bày chi tiết có thể thay đổi giữa các bản JDK.

Khi thử trên mã ví dụ, các vị trí type-use tương ứng được hiển thị theo ý nghĩa:

```text
METHOD_FORMAL_PARAMETER, param_index=0
METHOD_FORMAL_PARAMETER, param_index=0, location=[TYPE_ARGUMENT(0)]
```

- Visible parameter annotation chứa `ParamRuntime("declaration")`.
- Invisible parameter annotation chứa `ParamClass("stored-in-class")`.
- Visible type annotations chứa `TypeRuntime("list-type")` và `TypeRuntime("element-type")`, với đường đi type argument phù hợp.
- Invisible type annotation chứa `TypeClass("hidden-type")`.
- `MethodParameters` có thể hiện tên `values` do dùng `-parameters`.

Dù hai invisible attributes có dữ liệu, reflection ở phần trước trả `false` đúng như thiết kế. **Không nên cho rằng reflection sai chỉ vì `javap` nhìn thấy một attribute.**

### Thử xóa cờ -parameters

Chạy lại `javac -encoding UTF-8 ParameterTraceDemo.java` **không có** `-parameters` rồi chạy `java ParameterTraceDemo` ở môi trường biên dịch thông thường:

- Tên `parameter.getName()` thường thành `arg0` (nếu compiler không lưu tên tham số theo cơ chế tương đương).
- Những annotation theo target và retention vẫn được lưu/đọc theo quy tắc cũ.

Muốn thử nghiệm sạch, hãy xóa các tệp `.class` do chính ví dụ tạo ra trước khi biên dịch lại nếu trình biên dịch hoặc môi trường của bạn không ghi đè như mong đợi. **`-parameters` không phải điều kiện để annotation `@Target(PARAMETER)` được lưu.**

## 7. Chọn đúng reflection API

Các nhóm API đọc dữ liệu khác nhau:

| Câu hỏi | API chính | Đối tượng metadata |
| --- | --- | --- |
| Annotation trực tiếp của formal parameter đầu tiên | `method.getParameters()[0].getAnnotation(A.class)` | `Parameter` |
| Toàn bộ annotation khai báo cho các tham số | `method.getParameterAnnotations()` | `Annotation[][]` |
| Annotation trên kiểu của tham số | `method.getParameters()[0].getAnnotatedType()` | `AnnotatedType` |
| Các annotated types của toàn bộ tham số | `method.getAnnotatedParameterTypes()` | `AnnotatedType[]` |
| Annotation trên `String` trong `List<String>` | Cast phù hợp sang `AnnotatedParameterizedType`, rồi `getAnnotatedActualTypeArguments()[0]` | Annotated type argument |
| Annotation trên kiểu trả về của method | `method.getAnnotatedReturnType()` | Annotated return type |
| Tên khai báo của tham số khi metadata khả dụng | `Parameter.getName()` và `isNamePresent()` | `MethodParameters`/parameter name |

Hai câu hỏi khác nhau:

```java
// Giả định method và annotation type từ ví dụ chính.
Parameter p = method.getParameters()[0];

p.getAnnotation(ParamRuntime.class);  // Annotation trên declaration.
p.getAnnotatedType()
 .getAnnotation(TypeRuntime.class);     // Annotation trên vị trí kiểu List.
```

Đây là **đoạn minh họa API**; `method` phải tồn tại như trong chương trình đầy đủ. Annotation trên `String` ở bên trong `List<String>` còn sâu hơn một cấp, nên cần `AnnotatedParameterizedType`.

Reflection thường chỉ thấy annotation retention RUNTIME và còn phụ thuộc loại annotated element; nó không phải công cụ tổng quát để liệt kê mọi attribute trong class file. Khi audit bytecode, hãy dùng `javap -v` hoặc thư viện phân tích bytecode phù hợp.

## 8. Các trường hợp biên dịch cần phân biệt

### A. Declaration annotation trên method không phải trên formal parameter

```java
// Giả sử @MethodLabel có target METHOD,
// @ParamLabel có target PARAMETER.
@MethodLabel
void process(@ParamLabel String input) {}
```

Hai annotation ở hai vị trí khác nhau:

- `@MethodLabel` là declaration annotation trên method: có thể được lưu qua `RuntimeVisibleAnnotations` / `RuntimeInvisibleAnnotations` tùy retention.
- `@ParamLabel` là declaration annotation trên formal parameter: có thể được lưu qua `RuntimeVisibleParameterAnnotations` / `RuntimeInvisibleParameterAnnotations`.

Nếu dùng `method.getAnnotation(ParamLabel.class)`, bạn đang hỏi sai phần tử. Hãy đọc `Parameter` tương ứng.

### B. Type-use annotation trên generic argument khác với trên kiểu ngoài

```java
// Giả sử @TypeLabel có @Target(TYPE_USE).
void execute(java.util.List<@TypeLabel("item") String> values) {}
```

Annotation nằm trên đối số kiểu generic `String`. Reflection cần chọn kiểu tham số `List<...>` trước rồi đi vào type argument. Bytecode cần `type_path` để ghi chính xác chỗ `String` trong cây kiểu.

### C. Constructor parameter cũng là formal parameter

```java
class Customer {
    Customer(@InputName("customer-id") String id) {
        // Minh họa: annotation được đặt trên constructor parameter.
    }
}
```

Đoạn này giả sử `InputName` đã được khai báo. Constructor trong class file cũng được mô tả bằng một `method_info` (tên bytecode đặc biệt là `<init>`). Do đó, nhóm **ParameterAnnotations** tương ứng vẫn áp dụng được. Trong reflection, hãy lấy `Constructor<?>` rồi gọi `getParameters()` hoặc `getParameterAnnotations()`.

### D. SOURCE retention không hiện trong các attribute ấy

Nếu thay `@Retention(RUNTIME)` bằng `@Retention(SOURCE)` đối với một annotation thử nghiệm, `javac` có thể xử lý nó trong lúc biên dịch, nhưng class file không lưu runtime annotation attribute cho chính annotation đó. Đừng kết luận annotation “chưa từng có trong source” chỉ từ việc không thấy tên trong `javap -v`.

### E. Không suy ra hành vi nghiệp vụ từ cấu trúc class file

Một annotation tên `@Validated` hay `@NonNull` không tự khiến bytecode có thêm nhánh `if` kiểm tra dữ liệu, trừ khi annotation processor, compiler plugin hoặc runtime framework thực sự xử lý annotation và sinh/thực thi logic ấy.

**Attribute lưu metadata; consumer diễn giải metadata.** Hai quá trình hoàn toàn khác nhau.

## 9. Quy trình thực hành để chẩn đoán annotation bị “mất”

Khi thấy reflection trả `null`, hãy kiểm tra theo thứ tự:

1. **Xem @Target.** Annotation đó dành cho `PARAMETER` hay `TYPE_USE`? Nếu khai báo nhiều target, kiểm tra vị trí áp dụng thực tế.
2. **Xem @Retention.** `RUNTIME` mới là lựa chọn dành cho reflection thông thường. `CLASS` có thể nhìn thấy qua class file nhưng không qua reflection chuẩn.
3. **Đọc đúng API.** Dùng `Parameter.getAnnotation()` cho declaration; dùng `getAnnotatedType()` và duyệt type tree cho type use.
4. **Đảm bảo đang xem đúng class đã biên dịch.** Kiểm tra classpath, module path, version JDK, tên class và tệp `.class` thực tế. Class cũ có thể che bản mới.
5. **Chạy javap -v.** Xác định tên attribute, target, parameter index và type path. Không chỉ dựa vào một đoạn ngắn từ source.
6. **Đối chiếu phần tử trong descriptor.** Đặc biệt cẩn thận với constructor synthetic parameters, nested classes, enum/record hoặc những trường hợp trình biên dịch bổ sung metadata.
7. **Chỉ sau đó kiểm tra framework.** Có thể framework chỉ đọc declaration annotations, bỏ qua type-use annotations, hoặc tự áp dụng quy tắc kế thừa/meta-annotation ngoài Java reflection cơ bản.

Với những annotation trên generic phức tạp, ví dụ `List<@TypeLabel String>`, thông tin đúng vị trí thường quan trọng hơn việc thấy một annotation cùng tên xuất hiện đâu đó trong output `javap`.

## 10. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có annotation trước tên tham số là PARAMETER annotation” | Cần xét `@Target` và vị trí: annotation có thể áp dụng cho **kiểu tham số** |
| “RuntimeInvisible nghĩa là javap không đọc được” | `javap -v` vẫn có thể hiển thị attribute; chỉ không có qua reflection chuẩn |
| “CLASS retention giống SOURCE retention” | `CLASS` được lưu ở class file; `SOURCE` không được lưu trong các annotation attributes runtime |
| “-parameters cần cho Parameter.getAnnotation” | `-parameters` chủ yếu giữ tên và thông tin formal parameter trong metadata `MethodParameters` |
| “getParameterAnnotations thấy List<@A String>” | Cần đi sâu qua `AnnotatedParameterizedType` |
| “RuntimeVisibleAnnotations chính là attribute parameter” | Formal parameter declaration có nhóm `...ParameterAnnotations` riêng |
| “TypeAnnotations chỉ nằm ở method_info” | Cũng có thể nằm ở `ClassFile`, `field_info` hoặc `Code` khi thích hợp |
| “Một type annotation trên List tức là đã annotate String bên trong” | List và type argument String có hai vị trí riêng, cần đường đi type `type_path` |
| “Một annotation custom tự tạo kiểm tra dữ liệu” | Chỉ consumer có hiểu annotation mới thực thi kiểm tra/hành vi |

## 11. Bài tập tự kiểm tra

**Câu 1.** Một annotation có `@Target(PARAMETER)` và `@Retention(RUNTIME)` gắn trên tham số method. Tên attribute thuộc nhóm nào?

**Đáp án:** `RuntimeVisibleParameterAnnotations` ở `method_info`.

**Câu 2.** Nếu thay retention trên annotation đó thành `CLASS`, attribute sẽ thuộc nhóm nào và reflection đọc được không?

**Đáp án:** `RuntimeInvisibleParameterAnnotations`; reflection thông thường không trả annotation này.

**Câu 3.** Với `List<@Mark String> values`, annotation nằm trong loại attribute nào nếu `Mark` chỉ cho phép `TYPE_USE` và retention `RUNTIME`?

**Đáp án:** `RuntimeVisibleTypeAnnotations`, với target tương ứng kiểu formal parameter và đường đi tới type argument.

**Câu 4.** Với `List<@Mark String>`, `Parameter.getAnnotation(Mark.class)` có phải API đủ để xem annotation trên `String` không?

**Đáp án:** Không. Cần `getAnnotatedType()`, cast phù hợp sang `AnnotatedParameterizedType`, rồi lấy type argument.

**Câu 5.** Vì sao `javap -v` cho thấy `RuntimeInvisibleTypeAnnotations` mà `getAnnotatedType().getAnnotation()` trả `null`?

**Đáp án:** Vì retention `CLASS` được lưu cho công cụ xử lý class file nhưng không hiển thị qua reflection runtime chuẩn.

**Câu 6.** `-parameters` có phải “bật annotation trên parameter” không?

**Đáp án:** Không. Nó giữ tên/metadata formal parameter như `values` để reflection có thể đọc tên; cơ chế lưu annotation là các attributes riêng.

**Câu 7.** Với `List<@Mark String>`, `type_path` có ích gì?

**Đáp án:** Xác định annotation nằm ở **type argument bên trong**, không phải ở kiểu `List` ngoài cùng.

## Tài liệu tham khảo

- [JVMS 17, §4.7.18 — RuntimeVisibleParameterAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.18).
- [JVMS 17, §4.7.19 — RuntimeInvisibleParameterAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.19).
- [JVMS 17, §4.7.20 — RuntimeVisibleTypeAnnotations và type_path](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.20).
- [JVMS 17, §4.7.21 — RuntimeInvisibleTypeAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.21).
- [Java SE 17 API — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html).
- [Java SE 17 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).

**Ghi nhớ:** Khi truy tìm dấu vết annotation trong bytecode, hãy xác định **đối tượng được annotate (parameter declaration hay type-use)**, **retention (SOURCE/CLASS/RUNTIME)** và **vị trí trong cây kiểu**. Ba yếu tố đó quyết định class-file attribute chứa metadata và cách công cụ/reflection tiếp cận được metadata.
