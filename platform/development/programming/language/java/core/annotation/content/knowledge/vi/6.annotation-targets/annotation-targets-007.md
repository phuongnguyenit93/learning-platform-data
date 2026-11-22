# RECORD_COMPONENT và quy tắc lan truyền annotation của record trong Java

## 1. Một record component có thể liên quan đến nhiều vị trí annotation

Từ Java 16, `record` là dạng class chuyên biểu diễn một nhóm dữ liệu cố định. Trong Java 17+, khai báo sau có một **record component** tên `name`:

```java
record Person(String name) {}
```

Record component xuất hiện ở **header** của record, trong cặp ngoặc của `record Person(...)`. Nó là một thành phần của mô hình ngôn ngữ riêng, chứ không đơn giản là cú pháp viết tắt của field.

Với ví dụ trên, Java cũng có các khai báo liên quan:

- **Component** `name`: mô tả thành phần dữ liệu của record, truy xuất qua `Class.getRecordComponents()`.
- **Component field** `private final String name`: do compiler khai báo ngầm.
- **Accessor** `public String name()`: được khai báo ngầm nếu lập trình viên không viết thủ công.
- **Canonical constructor** `Person(String name)`: có tham số tương ứng với mỗi component, do compiler khai báo ngầm hoặc lập trình viên khai báo tường minh.

Đây là những vị trí khác nhau. Khi viết `@Mark String name` trong record header, annotation có thể xuất hiện ở **một hoặc nhiều vị trí liên quan** theo `@Target` của annotation đó.

Ví dụ:

```java
record Person(@SomeAnnotation String name) {}
```

Không thể mặc định rằng `@SomeAnnotation` chỉ gắn vào component, hoặc chắc chắn xuất hiện trên cả field, accessor và constructor parameter. Điều đó phụ thuộc **`ElementType` nào được phép** và **thành viên được khai báo ngầm hay tường minh**.

## 2. `ElementType.RECORD_COMPONENT` là gì?

`java.lang.annotation.ElementType.RECORD_COMPONENT` là enum constant chỉ **record component declaration**. Muốn annotation hiện diện trực tiếp trên record component, khai báo `@Target(ElementType.RECORD_COMPONENT)` hoặc bao gồm giá trị này trong danh sách target:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentInfo {
    String value();
}

record Customer(@ComponentInfo("customer-id") String id) {}
```

Khi đọc bằng reflection:

```java
var component = Customer.class.getRecordComponents()[0];
ComponentInfo info = component.getAnnotation(ComponentInfo.class);
System.out.println(info.value()); // customer-id
```

Đoạn reflection này **phụ thuộc vào hai điều kiện**:

1. `@Target(RECORD_COMPONENT)` cho phép annotation được ghi trên bản thân record component.
2. `@Retention(RUNTIME)` cho phép API reflection đọc annotation lúc chạy.

`@Target` trả lời **được phép gắn ở đâu**; `@Retention` trả lời **metadata được giữ đến giai đoạn nào**. Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`; annotation vẫn có thể được compiler ghi vào class file nhưng không hiện qua các API reflection nêu trên.

**Chú ý:** `RECORD_COMPONENT` không phải tên của mọi field được tạo ra từ record. `ElementType.FIELD`, `METHOD`, `PARAMETER`, `TYPE_USE` vẫn có ý nghĩa riêng.

## 3. Bảng quy tắc lan truyền annotation

Giả sử có `record Example(@A String value) {}` và `@A` được khai báo `@Retention(RUNTIME)`. Tùy tập target, Java xử lý như sau:

| `ElementType` được phép | Annotation xuất hiện ở đâu? | Cách quan sát |
|---|---|---|
| `RECORD_COMPONENT` | Chính record component | `RecordComponent.getAnnotation(A.class)` |
| `FIELD` | Component field được khai báo ngầm | `getDeclaredField("value").getAnnotation(A.class)` |
| `METHOD` | **Accessor được khai báo ngầm** `value()` | `getMethod("value").getAnnotation(A.class)` |
| `PARAMETER` | Parameter **suy ra** của canonical constructor ngầm hoặc compact constructor | `getDeclaredConstructor(String.class).getParameters()[0].getAnnotation(A.class)` |
| `TYPE_USE` | Các vị trí sử dụng kiểu tương ứng: kiểu component, kiểu field, kiểu trả về của accessor ngầm, kiểu parameter suy ra | `getAnnotatedType()` tại đúng vị trí |

Một annotation có thể khai báo **nhiều target**; cùng annotation ở header sẽ có mặt ở nhiều nơi **khi các quy tắc cho phép**. Ví dụ:

```java
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
@interface AuditName {
    String value();
}

record User(@AuditName("user-name") String name) {}
```

Trong record đơn giản `User`, `@AuditName` có thể được reflection tìm thấy trên record component, component field, accessor ngầm và parameter của canonical constructor ngầm. Đây là **quy tắc lan truyền ở thời điểm compiler xử lý record declaration**; không phải runtime tự động sao chép annotation sau khi class đã được tải.

Nếu annotation chỉ có `@Target(FIELD)`, đặt nó trên record header vẫn có thể hợp lệ vì khai báo đó tương ứng với component field nhận annotation. Tuy nhiên, `RecordComponent.getAnnotation(...)` **không** thấy annotation chỉ áp dụng cho `FIELD`. Cần truy vấn đúng field. Tương tự, annotation chỉ áp dụng cho `METHOD` hoặc `PARAMETER` không tự nhiên trở thành annotation trực tiếp của `RecordComponent`.

### 3.1. Vì sao compiler có cơ chế lan truyền?

Record header là nguồn khai báo các thành phần của record. Từ đó compiler suy ra field, accessor và canonical constructor phù hợp. Một annotation có thể định nghĩa ngữ nghĩa cho nhiều vị trí; ví dụ một thư viện cần đánh dấu cả field và accessor. Cơ chế lan truyền cho phép **đặt annotation tại header một lần** nếu target và dạng khai báo cụ thể đáp ứng quy tắc.

Điều này không có nghĩa tất cả annotation đều được sao chép. Java cố ý chọn các vị trí dựa trên `@Target`; các khai báo do người lập trình viết tường minh có ngoại lệ cần hiểu kỹ ở phần sau.

## 4. Ví dụ hoàn chỉnh Java 17+: quan sát từng vị trí bằng reflection

Tạo file **Main.java** với nội dung sau. Ví dụ sử dụng nhiều annotation độc lập để phân biệt rõ từng đích áp dụng:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Track {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParamOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {}

record Entry(
        @Track("id")
        @ComponentOnly
        @FieldOnly
        @MethodOnly
        @ParamOnly
        @TypeTag String id
) {}

record CustomAccessor(@Track("id") String id) {
    public String id() {
        return id;
    }
}

record CompactCtor(@Track("id") String id) {
    public CompactCtor {
        if (id == null) {
            throw new IllegalArgumentException();
        }
    }
}

record ExplicitCtor(@Track("id") String id) {
    public ExplicitCtor(String id) {
        this.id = id;
    }
}

public class Main {
    public static void main(String[] args) throws Exception {
        RecordComponent component = Entry.class.getRecordComponents()[0];

        System.out.println("recordTrack="
                + component.isAnnotationPresent(Track.class));
        System.out.println("componentOnly="
                + component.isAnnotationPresent(ComponentOnly.class));
        System.out.println("fieldOnlyOnComponent="
                + component.isAnnotationPresent(FieldOnly.class));
        System.out.println("fieldOnlyOnField="
                + Entry.class.getDeclaredField("id")
                        .isAnnotationPresent(FieldOnly.class));
        System.out.println("methodOnlyOnAccessor="
                + Entry.class.getMethod("id")
                        .isAnnotationPresent(MethodOnly.class));
        System.out.println("paramOnlyOnCtor="
                + Entry.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].isAnnotationPresent(ParamOnly.class));

        System.out.println("typeUseOnComponentType="
                + component.getAnnotatedType().isAnnotationPresent(TypeTag.class));
        System.out.println("typeUseOnFieldType="
                + Entry.class.getDeclaredField("id")
                        .getAnnotatedType().isAnnotationPresent(TypeTag.class));
        System.out.println("typeUseOnAccessorReturn="
                + Entry.class.getMethod("id")
                        .getAnnotatedReturnType().isAnnotationPresent(TypeTag.class));
        System.out.println("typeUseOnParameterType="
                + Entry.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].getAnnotatedType()
                        .isAnnotationPresent(TypeTag.class));

        System.out.println("customAccessorTrack="
                + CustomAccessor.class.getMethod("id")
                        .isAnnotationPresent(Track.class));
        System.out.println("compactCtorParamTrack="
                + CompactCtor.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].isAnnotationPresent(Track.class));
        System.out.println("explicitCtorParamTrack="
                + ExplicitCtor.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].isAnnotationPresent(Track.class));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Đầu ra chính xác trên Java 17+:

```text
recordTrack=true
componentOnly=true
fieldOnlyOnComponent=false
fieldOnlyOnField=true
methodOnlyOnAccessor=true
paramOnlyOnCtor=true
typeUseOnComponentType=true
typeUseOnFieldType=true
typeUseOnAccessorReturn=true
typeUseOnParameterType=true
customAccessorTrack=false
compactCtorParamTrack=true
explicitCtorParamTrack=false
```

**Cách đọc kết quả:**

- `recordTrack=true`: `Track` có `RECORD_COMPONENT`, nên hiện trên component.
- `componentOnly=true`: `ComponentOnly` gắn trực tiếp vào component.
- `fieldOnlyOnComponent=false`, trong khi `fieldOnlyOnField=true`: một annotation có target `FIELD` **không** biến thành annotation trực tiếp trên `RecordComponent`.
- `methodOnlyOnAccessor=true`: accessor ngầm `id()` mang annotation cho phép `METHOD`.
- `paramOnlyOnCtor=true`: parameter suy ra của canonical constructor ngầm mang annotation cho phép `PARAMETER`.
- Bốn dòng `typeUse...` cho thấy `TYPE_USE` liên quan đến **kiểu tại từng vị trí**, không phải annotation declaration ở tất cả nơi.
- Ba dòng cuối minh họa **ngoại lệ của member/constructor được khai báo tường minh**. Các ngoại lệ này là phần quan trọng của quy tắc, không phải lỗi reflection.

Mã dùng `@Retention(RUNTIME)` để kết quả quan sát được bằng reflection. Việc lan truyền từ header vào các khai báo liên quan xảy ra trong quá trình biên dịch, không phụ thuộc vào việc có chạy reflection hay không.

## 5. Ngoại lệ 1: accessor viết tường minh không tự nhận annotation

Mỗi component có một accessor trùng tên, không có tham số. Nếu không viết method, compiler khai báo accessor ngầm và lan truyền những annotation phù hợp với `METHOD` hoặc `TYPE_USE`.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Readable {}

record AutoAccessor(@Readable String name) {}
```

Ở đây `AutoAccessor.name()` được khai báo **ngầm**. Với retention runtime, `getMethod("name").isAnnotationPresent(Readable.class)` cho `true`.

Ngược lại:

```java
record ManualAccessor(@Readable String name) {
    public String name() {
        return name;
    }
}
```

Vì `name()` do lập trình viên khai báo **tường minh**, annotation của record component **không lan truyền** sang declaration của accessor này. Nếu cần metadata trên accessor, phải đánh dấu nó **ngay tại method**:

```java
record ManualAccessorFixed(@Readable String name) {
    @Readable
    public String name() {
        return name;
    }
}
```

Hai annotation trong ví dụ cuối nằm ở hai vị trí có vai trò khác nhau: annotation ở header là nguồn metadata của component và vị trí được phép tương ứng; annotation trên method là metadata của accessor viết tường minh.

**Lưu ý về `TYPE_USE`:** quy tắc cho accessor tường minh cũng áp dụng khi cần annotation trên **kiểu trả về** của accessor. Không suy ra kiểu trả về của method viết thủ công chắc chắn có cùng type-use annotation với kiểu record component trong header. Cần khai báo annotation tại vị trí type-use thích hợp của method đó.

## 6. Ngoại lệ 2: canonical constructor khai báo đầy đủ

Record có **canonical constructor** nhận một tham số cho mỗi component theo đúng tên và kiểu tương ứng. Nếu compiler tự sinh constructor, parameter được suy ra từ header, mang annotation có target `PARAMETER` hoặc `TYPE_USE` phù hợp.

Tuy nhiên, với **normal canonical constructor** được viết đầy đủ, lập trình viên khai báo parameter của constructor và tự quyết định annotation trên parameter đó:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Input {}

record AutoCtor(@Input String name) {}

record ManualCtor(@Input String name) {
    public ManualCtor(String name) {
        this.name = name;
    }
}
```

- `AutoCtor`: parameter của canonical constructor ngầm có `@Input`.
- `ManualCtor`: parameter `String name` trong constructor viết đầy đủ **không tự nhận** `@Input` từ header.

Nếu cần annotation trên parameter viết đầy đủ, đặt nó ngay trên parameter:

```java
record ManualCtorFixed(@Input String name) {
    public ManualCtorFixed(@Input String name) {
        this.name = name;
    }
}
```

Điều này vẫn đúng nếu annotation ở header có thêm `RECORD_COMPONENT`, `FIELD` và `METHOD`: `@Target` cho phép nhiều nơi nhưng **không loại bỏ ngoại lệ của normal canonical constructor khai báo tường minh**. Việc viết annotation trên constructor parameter cũng không tự cập nhật ngược trở lại record component.

### 6.1. Trường hợp đặc biệt: compact constructor

Compact constructor có cú pháp:

```java
record Compact(@Input String name) {
    public Compact {
        if (name == null) {
            throw new IllegalArgumentException("name");
        }
    }
}
```

Phần `public Compact { ... }` **không khai báo danh sách parameter**. Compiler suy ra parameter từ record header, nên annotation `@Input` có target `PARAMETER` **vẫn được lan truyền** đến parameter của compact canonical constructor. Đó là lý do ví dụ hoàn chỉnh cho `compactCtorParamTrack=true` nhưng `explicitCtorParamTrack=false`.

Compact constructor cũng không yêu cầu tự gán field trong body; sau khi body hoàn thành bình thường, compiler gán các component field từ parameter tương ứng. Trong ví dụ trên, body chỉ kiểm tra `name`.

## 7. `TYPE_USE` khác gì `RECORD_COMPONENT`?

`ElementType.RECORD_COMPONENT` nhắm vào **khai báo component**. `ElementType.TYPE_USE` nhắm vào **vị trí dùng kiểu**, ví dụ kiểu `String` trong `record R(String value)`, kiểu field, kiểu trả về của accessor hoặc kiểu parameter được suy ra.

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NotEmptyType {}

record Message(@NotEmptyType String text) {}
```

Để đọc annotation trên **kiểu** của component:

```java
boolean found = Message.class.getRecordComponents()[0]
        .getAnnotatedType()
        .isAnnotationPresent(NotEmptyType.class);
```

Nếu `NotEmptyType` chỉ có `TYPE_USE`, `getAnnotation(NotEmptyType.class)` gọi **trực tiếp trên RecordComponent declaration** không nhất thiết có giá trị; ví dụ được thử nghiệm cho `false` ở declaration khi chỉ có target `TYPE_USE`, trong khi `getAnnotatedType()` cho `true`.

Với annotation có target `TYPE_USE`, việc xem những annotation trên type-use của các phần liên quan phải dùng đúng API tương ứng:

```java
// Những dòng riêng lẻ minh họa API reflection, không phải Main.java độc lập:
Message.class.getDeclaredField("text").getAnnotatedType();
Message.class.getMethod("text").getAnnotatedReturnType();
Message.class.getDeclaredConstructor(String.class)
        .getParameters()[0].getAnnotatedType();
```

Record có thể có type phức tạp, chẳng hạn `List<@NotEmptyType String>`. Khi ấy annotation nhắm vào **đối số kiểu String**; để kiểm tra cần duyệt cây `AnnotatedType` và các `AnnotatedParameterizedType`, không chỉ hỏi annotation của outer type `List`.

Quan trọng: Java cho phép **nhiều lớp annotation khác nhau** trên cùng một component: declaration annotation gắn vào component và type-use annotation gắn vào kiểu của component. Hãy phân tích đúng lớp metadata đang cần.

## 8. Annotation propagation không đồng nghĩa với validation tự hoạt động

Giả sử một thư viện định nghĩa annotation phục vụ validation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.PARAMETER
})
@interface Required {}

record Request(@Required String token) {}
```

Java sẽ lưu annotation ở những declaration được phép tương ứng với record. **Nhưng annotation tự nó không kiểm tra `token != null`**. Quy tắc lan truyền chỉ mô tả metadata; muốn validation có hiệu lực phải có code hay framework chủ động đọc annotation và thực thi kiểm tra.

Ngoài ra, framework đọc **field annotation** không đồng nghĩa nó đọc **record-component annotation**. Ví dụ:

- Code dùng `RecordComponent.getAnnotation(Required.class)` quan sát target `RECORD_COMPONENT`.
- Code dùng `Field.getAnnotation(Required.class)` quan sát target `FIELD` trên component field.
- Code dùng `Parameter.getAnnotation(Required.class)` quan sát parameter của constructor có annotation; với constructor khai báo đầy đủ, cần kiểm tra annotation đã được khai báo lại chưa.
- Code dùng `Method.getAnnotation(Required.class)` cần `METHOD` trong target và accessor phù hợp hoặc annotation ghi trực tiếp trên accessor tường minh.

Nếu một thư viện quét nhiều vị trí, cùng annotation có thể xuất hiện ở nhiều chỗ; thư viện tự chịu trách nhiệm tránh xử lý lặp khi điều đó không phù hợp. Đừng suy ra annotation tự chạy chỉ vì `@Target` chứa nhiều nơi.

## 9. Các lỗi dễ gặp khi làm việc với annotation trên record

### 9.1. Chỉ khai báo `@Target(RECORD_COMPONENT)` rồi mong thấy annotation trên field

```java
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentTag {}

record Item(@ComponentTag String id) {}
```

`ComponentTag` chỉ nhắm vào component. Nếu logic đang dùng `getDeclaredField("id").getAnnotation(ComponentTag.class)`, việc không tìm thấy annotation là **đúng hợp đồng**. Muốn nó xuất hiện trên field, annotation type phải cho phép `FIELD`; đồng thời cần retention phù hợp nếu muốn quan sát qua reflection.

### 9.2. Chỉ nhìn `RecordComponent.getAnnotations()` rồi kết luận mọi annotation đã mất

Một annotation có `@Target(FIELD)` hoặc `@Target(TYPE_USE)` có thể hợp lệ trên record header, nhưng nó được quan sát ở field hoặc annotated type tương ứng. Các API `getAnnotations()` của mỗi đối tượng reflection chỉ phản ánh **đúng vị trí** của đối tượng đó.

### 9.3. Tưởng `@Retention(RUNTIME)` gây ra sự lan truyền

Retention cho biết annotation có được lưu để dùng tại runtime hay không. Lan truyền từ record header vào các khai báo liên quan được quy định bởi Java language/compiler. Retention **không thay** target và **không khiến accessor/constructor được viết tường minh tự nhận annotation**.

### 9.4. Khi refactor accessor hoặc constructor, không kiểm tra lại nơi annotation xuất hiện

Thay accessor ngầm bằng accessor tường minh có thể khiến annotation target `METHOD` không còn hiện trên accessor. Thay canonical constructor ngầm bằng normal canonical constructor viết đầy đủ có thể khiến annotation target `PARAMETER` không còn hiện trên parameter. Cần xét lại metadata tại nơi framework đọc nó, và ghi annotation tường minh khi cần.

### 9.5. Nhầm với `@Inherited`

`@Inherited` liên quan tới việc một **class-level annotation** được truy vấn qua chuỗi superclass theo quy tắc của nó. Record component không phải cơ chế kế thừa class; `@Inherited` không phải giải pháp để lan truyền metadata từ component tới field, method hoặc parameter.

### 9.6. Đặt annotation có target không phù hợp

`@Target(ElementType.TYPE)` chỉ dùng cho khai báo kiểu như class/interface/record **cả khối**, không tự cho phép đặt annotation đó trước **tên component**. Tương tự, không có `@Target(RECORD_COMPONENT)` hay một target liên quan phù hợp thì không nên giả định annotation có thể đặt trên header. Compiler sẽ kiểm tra đích áp dụng hợp lệ.

## 10. Checklist khi thiết kế và sử dụng annotation cho record

1. **Xác định đúng đối tượng cần đọc metadata.** Đọc `RecordComponent`, `Field`, `Method`, `Parameter` hay `AnnotatedType`? Mỗi loại khác nhau.
2. **Khai báo `@Target` theo nhu cầu thực tế.** Chỉ `RECORD_COMPONENT` nếu đúng là metadata component; thêm `FIELD`, `METHOD`, `PARAMETER` hoặc `TYPE_USE` nếu consumer thật sự cần.
3. **Chọn retention đúng.** Nếu reflection lúc chạy đọc annotation, dùng `RUNTIME`; nếu chỉ cần cho build-time processing, xem xét `SOURCE` hoặc `CLASS` tương ứng.
4. **Kiểm tra thành viên viết tường minh.** Accessor tự viết và normal canonical constructor tự viết không nhận toàn bộ annotation từ header như thành viên suy ra.
5. **Kiểm tra compact constructor.** Parameter của compact constructor được suy ra nên metadata target `PARAMETER` phù hợp có thể được lan truyền.
6. **Viết thử bằng reflection hoặc test annotation processor** tại chính bề mặt mà code tiêu thụ. Không chỉ nhìn cú pháp `record` mà suy luận.
7. **Tránh xử lý lặp.** Nếu cùng annotation xuất hiện ở nhiều nơi, consumer phải xác định rõ ngữ nghĩa và thứ tự ưu tiên.

## 11. Tài liệu chuẩn và kết luận

- [Java SE 17 JLS §8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): component trong header và mối liên hệ với các thành viên record.
- [Java SE 17 JLS §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): component field, accessor ngầm, ngoại lệ accessor khai báo tường minh.
- [Java SE 17 JLS §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): constructor ngầm, normal canonical constructor, compact constructor và danh sách parameter suy ra.
- [Java SE 17 JLS §9.6.4.1 — `@Target`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): các ngữ cảnh declaration/type mà annotation được phép dùng.
- [Java SE 17 API — `RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): cách đọc annotation và annotated type của component qua reflection.

**Điểm cần nhớ:** `RECORD_COMPONENT` là một đích áp dụng riêng. Annotation đặt ở record header có thể lan truyền sang **field, accessor ngầm, parameter suy ra của canonical constructor và các type-use** nếu `@Target` cho phép. **Accessor viết tường minh** và **normal canonical constructor khai báo đầy đủ** cần metadata riêng tại những vị trí tương ứng. Đọc annotation đúng nơi và kiểm tra đúng retention mới biết thông tin nào thật sự tồn tại trong chương trình.