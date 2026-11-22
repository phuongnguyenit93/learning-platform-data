# Thiết kế metadata mở rộng mà vẫn dễ đọc với annotation lặp trong Java

**Repeatable annotation** (annotation lặp) là cơ chế Java cho phép đặt nhiều annotation **cùng một loại** lên cùng một vị trí khai báo hoặc vị trí sử dụng kiểu, miễn loại annotation đó được định nghĩa với `@Repeatable`. Tính năng có từ Java 8 và tiếp tục hữu ích trong Java hiện đại khi một thành phần cần khai báo nhiều cấu hình có cấu trúc giống nhau: nhiều quy tắc, nhãn, alias, quyền hoặc biến thể xuất dữ liệu.

Mục tiêu không phải “gắn thật nhiều annotation lên mọi nơi”. Một thiết kế metadata tốt phải thỏa đồng thời:

- **Dễ đọc tại nơi khai báo:** người đọc hiểu mỗi annotation có một ý nghĩa nhỏ, rõ ràng.
- **Dễ mở rộng:** thêm một cấu hình không phải đổi chữ ký Java method/class hoặc tạo một annotation mới cho từng biến thể.
- **Dễ xử lý:** công cụ ở compile time hoặc runtime truy xuất nhất quán một hoặc nhiều annotation.
- **Có hợp đồng ổn định:** tên trường, kiểu dữ liệu, giá trị mặc định, thứ tự, xử lý trùng lặp và phiên bản được quy định rõ.
- **Không giấu hành vi:** annotation là metadata. Parser, checker, framework hoặc application code mới quyết định và thực thi ý nghĩa nghiệp vụ.

Bài này lấy `@Repeatable` làm trọng tâm, kết hợp `@Target`, `@Retention`, container annotation, reflection, chiến lược tiến hóa metadata, validation và cách kiểm thử với **JDK 17+**. Chỉ các API và quy tắc còn áp dụng trong Java hiện đại được sử dụng.

## 1. Từ nhu cầu thực tế tới mô hình metadata

Giả sử một method xuất báo cáo có thể hỗ trợ nhiều biến thể: xuất JSON tối giản, xuất CSV cho bảng tính và xuất text cho console.

**Không nên tạo một thuộc tính Boolean cho mỗi lựa chọn**:

```java
// THIẾT KẾ KHÓ MỞ RỘNG — đoạn minh họa:
@interface ExportModes {
    boolean jsonCompact() default false;
    boolean csvTable() default false;
    boolean textAudit() default false;
    // Thêm định dạng mới lại phải mở rộng schema bằng một trường nữa.
}
```

Cách này gây ra nhiều câu hỏi: các cờ có thể cùng bật không? Có bao nhiêu tổ hợp? Định dạng mới thêm vào đâu? Một thuộc tính Boolean tự nó không mô tả tên cấu hình, quyền truy cập hay quy tắc sử dụng.

Một hướng tốt hơn là tạo **một annotation mô tả một biến thể**, rồi cho phép lặp:

```java
@Export(name = "compact", format = ExportFormat.JSON)
@Export(name = "spreadsheet", format = ExportFormat.CSV)
public void publish() {
    // Thực thi logic của ứng dụng.
}
```

Đây là **đoạn sử dụng minh họa**, phụ thuộc vào các loại `@Export` và `ExportFormat` sẽ được định nghĩa ở phần sau. Hai dòng metadata mô tả **hai cấu hình độc lập cùng schema**. Thêm biến thể thứ ba chỉ cần một dòng `@Export(...)` mới; không cần thêm method annotation khác tên hoặc sửa interface của method `publish()`.

Thiết kế này chỉ phù hợp khi **mỗi dòng annotation thật sự đại diện cho một phần tử cùng loại**. Nếu mọi thuộc tính luôn tạo thành **một cấu hình duy nhất**, hãy dùng một annotation đơn; nếu dữ liệu thường xuyên thay đổi theo môi trường, database hoặc người dùng, file cấu hình hay nguồn dữ liệu riêng có thể phù hợp hơn.

## 2. Cơ chế Java: annotation lặp và container annotation

Để một annotation lặp hợp lệ, nó cần được đánh dấu `@Repeatable` và trỏ đến **container annotation type**.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum ExportFormat {
    JSON, CSV, TEXT
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Exports.class)
@interface Export {
    String name();
    ExportFormat format();
    boolean enabled() default true;
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface Exports {
    Export[] value();
}
```

Đây là **nhóm khai báo minh họa**, chưa có `main`. Những điểm cần nhớ:

1. `@Repeatable(Exports.class)` trên `Export` khai báo **loại container**.
2. `Exports` bắt buộc có phần tử tên chính xác là `value()` và kiểu trả về **`Export[]`**.
3. Những phần tử khác của container, nếu có, phải có giá trị mặc định theo yêu cầu JLS; trong API thực tế nên tránh thêm trường không cần thiết vào container.
4. `@Target` và `@Retention` của container phải tương thích với annotation lặp theo các quy tắc ngôn ngữ.
5. `@Repeatable` không làm annotation tự thực thi; một consumer phải đọc metadata để áp dụng quy tắc.

Khi viết hai `@Export` liền nhau, compiler sử dụng mô hình **container annotation** để biểu diễn nhiều phần tử cùng loại ở vị trí đó. Người viết application code vẫn nhìn thấy hai dòng `@Export` rõ nghĩa thay vì phải tự viết một mảng dài trong source.

### Cú pháp lặp và cú pháp container

Dạng dễ đọc, được ưu tiên tại call site:

```java
@Export(name = "compact", format = ExportFormat.JSON)
@Export(name = "spreadsheet", format = ExportFormat.CSV)
void publish() {}
```

Có thể khai báo container trực tiếp khi đó là điều API cho phép:

```java
@Exports({
    @Export(name = "compact", format = ExportFormat.JSON),
    @Export(name = "spreadsheet", format = ExportFormat.CSV)
})
void publish() {}
```

Cả hai là **đoạn khai báo minh họa** đặt trong class. Dạng lặp thường gần với ngôn ngữ nghiệp vụ hơn: mỗi cấu hình là một đơn vị nhỏ, thuận tiện thêm/xóa/review từng dòng. Dạng container phù hợp hơn khi người dùng cần hiển thị tính “nhóm” trong một API cũ hoặc khi tương tác với công cụ có quy ước riêng.

**Không nên khai báo đồng thời cả container và các annotation lặp tương ứng ở cùng một vị trí.** Java kiểm tra những tổ hợp annotation trực tiếp/container bị xung đột theo luật repeatable annotations. Chọn **một** phong cách tại mỗi declaration.

## 3. Metadata schema nhỏ, dễ đọc và tự mô tả

Một annotation tốt thường giống **bản ghi dữ liệu bất biến được khai báo tại source**, chứ không giống một lớp có nghiệp vụ phức tạp. Thiết kế `@Export` ở trên dùng:

| Thành phần | Kiểu | Ý nghĩa | Quyết định thiết kế |
| --- | --- | --- | --- |
| `name()` | `String` | Định danh một cấu hình xuất | Bắt buộc, vì mỗi entry cần tên riêng |
| `format()` | `ExportFormat` | Loại xuất dữ liệu | Enum hạn chế typo và giúp IDE gợi ý |
| `enabled()` | `boolean` | Cho phép tạm giữ một entry nhưng tắt xử lý | Có default `true`, không phải giá trị nhận ngẫu nhiên |
| `Exports.value()` | `Export[]` | Container chứa các entry | Hạ tầng repeatable; không phải schema nghiệp vụ thứ hai |

Với metadata phức tạp hơn, có thể bổ sung các thuộc tính có tên và semantics rõ ràng, ví dụ `description() default ""` hoặc `priority() default 0`. Nhưng phải hỏi: trường này có được consumer dùng thực tế không? Nếu không, đừng thêm chỉ để “phòng hờ”.

### Chọn tên thuộc tính đúng mức độ rõ ràng

```java
// KHÓ HIỂU:
@Export(name = "main", format = ExportFormat.JSON, enabled = true)

// RÕ HƠN khi tên biểu đạt chính xác vai trò:
@Export(name = "customer-summary", format = ExportFormat.JSON)
```

Các dòng là minh họa. Nếu `enabled=true` vốn là mặc định có tài liệu rõ ràng, không cần lặp lại ở mọi nơi. Tuy nhiên, khi cần người đọc nhận ra một cấu hình đã bị vô hiệu hóa vì lý do triển khai, `enabled = false` là thông tin quan trọng và nên giữ tường minh.

Không nên dùng những tên như `a()`, `b()`, `data()` khi ý nghĩa không hiển nhiên. Nếu cùng một annotation có đến hàng chục trường tùy chọn mâu thuẫn nhau, có thể metadata đang chứa nhiều khái niệm nghiệp vụ khác nhau; hãy tách thành những loại annotation có trách nhiệm rõ ràng.

### Khi nào nên dùng value() thay vì tên trường?

Java cho phép viết shorthand cho phần tử tên `value`:

```java
@interface Alias {
    String value();
}

// Khi annotation type được khai báo target/retention phù hợp:
@Alias("customer-id")
```

Đây là **ví dụ cú pháp minh họa**. Nếu annotation lặp chỉ có một giá trị hiển nhiên như alias, `@Alias("customer-id")` rất gọn. Nhưng với annotation có nhiều thuộc tính, `@Export("main", ...)` không thể thay toàn bộ thuộc tính bằng shorthand; nên dùng tên rõ như `name = ...`, `format = ...`.

**Quy tắc thực hành:** dùng `value()` khi annotation thật sự chỉ mô tả một giá trị chính dễ hiểu. Với metadata gồm nhiều trường độc lập, đặt tên tường minh giúp review và mở rộng tốt hơn.

## 4. Giá trị hợp lệ của annotation không giống object tùy ý

Một phần tử của annotation type trong Java chỉ có thể có những loại hợp lệ, chẳng hạn kiểu primitive, `String`, `Class`, enum, annotation type hoặc mảng một chiều của các loại đó. Không thể khai báo `List<String>`, `Map<String,Object>`, generic type parameter hay dữ liệu tính toán tùy ý làm loại phần tử annotation.

```java
@interface Labels {
    String[] value() default {};
}

@interface ConverterType {
    Class<?> value();
}
```

Đây là **khai báo minh họa**. `String[]` và `Class<?>` đều là lựa chọn hỗ trợ; giá trị tại nơi dùng annotation phải đáp ứng yêu cầu *compile-time constants*/class literals/enum constants/annotation values tương ứng.

Ví dụ **không hợp lệ**:

```java
// SAI: List không phải kiểu phần tử annotation hợp lệ.
// @interface Invalid {
//     java.util.List<String> names();
// }

// SAI: biểu thức annotation không nhận một method invocation runtime.
// @SomeTag(value = System.getenv("PROFILE"))
```

Khi metadata thay đổi theo deploy environment, tài khoản hoặc dữ liệu thời gian thực, nên chuyển phần thay đổi đó sang **configuration/runtime data** thay vì cố nén vào annotation.

### Enum hay String?

- Dùng **enum** nếu tập giá trị nhỏ, ổn định, thuộc hệ thống kiểu do code quản lý; ví dụ `JSON`, `CSV`, `TEXT`.
- Dùng **String** nếu tên là định danh do người dùng đặt, có namespace, có khả năng được mở rộng bởi plugin ngoài hoặc cần tương thích với chuẩn chuỗi.
- Nếu dùng `String`, hãy **validate**: không rỗng, trùng nhau không, chữ hoa/thường có phân biệt không, ký tự được phép và quy tắc namespace.

`@Export(name = "compact", format = ExportFormat.JSON)` sử dụng cả hai: enum diễn đạt **định dạng**, string diễn đạt **tên entry**. Không nên biến mọi thứ thành string chỉ để tránh định nghĩa enum khi metadata quan trọng và có phạm vi giá trị hữu hạn.

## 5. Chọn retention và target theo consumer thực tế

Với annotation lặp, cần xác định **ai sẽ đọc metadata** và **ở giai đoạn nào**.

| Consumer | Retention thường phù hợp | Ví dụ |
| --- | --- | --- |
| Static analyzer / compiler plugin xử lý source | `SOURCE` | Kiểm tra trùng alias tại compile time |
| Công cụ đọc hoặc biến đổi compiled class files | `CLASS` | Phân tích metadata trong bytecode |
| Reflection / framework ở runtime | `RUNTIME` | Tìm các cấu hình xuất tại khi khởi động |
| Không có công cụ nào đọc | Chưa cần annotation | Metadata vô tác dụng nếu không có consumer |

Nếu bỏ `@Retention`, mặc định là `RetentionPolicy.CLASS`; vì vậy **đừng** định nghĩa `@Repeatable` xong rồi mong `getAnnotationsByType` đọc được trong runtime nếu không thiết lập `RUNTIME`.

### Target của container phải phù hợp

Nếu `Export` cho phép annotation lên method, container `Exports` cũng phải cho phép vị trí đó. Với API mà annotation lặp được phép trên method và type, hãy xác định target chung có đúng ý định hay không:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Aliases.class)
@interface Alias {
    String value();
}

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@interface Aliases {
    Alias[] value();
}
```

Đây là **ví dụ khai báo minh họa** cho annotation alias, riêng biệt với `@Export` ở trên. Nó chỉ cho phép vị trí `TYPE` và `METHOD`; không tự áp dụng cho `PARAMETER`, `FIELD` hoặc `TYPE_USE`. Hãy tránh mở rộng target vô lý, vì metadata đặt ở vị trí không có consumer thường gây hiểu nhầm.

**Lưu ý quy tắc ngôn ngữ:** retention của container phải **ít nhất cũng giữ được metadata đến giai đoạn mà annotation lặp yêu cầu**. Nếu annotation lặp là `RUNTIME` mà container là `CLASS`, định nghĩa không hợp lệ. Quy tắc áp dụng về `@Target`, `@Documented` và `@Inherited` cũng cần được đối chiếu giữa loại lặp và container.

### @Documented và @Inherited có phải lựa chọn mặc định?

`@Documented` khiến annotation được xem xét trong tài liệu do Javadoc tạo; dùng nó khi metadata là một phần hợp đồng công khai đáng hiển thị. Nếu đặt `@Documented` trên annotation lặp, container phải đáp ứng điều kiện tương ứng của Java.

`@Inherited` **chỉ có ý nghĩa đối với inheritance của annotation trên class**, không làm annotation trên method, field, package hoặc interface tự động truyền xuống theo mọi cách. Nếu một repeatable annotation type được gắn `@Inherited`, container của nó cũng phải tuân thủ các ràng buộc tương ứng.

Không nên thêm `@Inherited` chỉ vì muốn “mở rộng cho linh hoạt”. Đặc biệt, inheritance của metadata nhiều entry có các quy tắc rõ về việc **thay thế** ở class con, không có phép “gộp tất cả config ở mọi ancestor” mặc định.

## 6. Reflection: đọc từng annotation lặp đúng API

Với annotation lặp có retention `RUNTIME`, cách phổ biến để đọc metadata là:

```java
Method method = ReportService.class.getDeclaredMethod("publish");
Export[] entries = method.getAnnotationsByType(Export.class);

for (Export entry : entries) {
    System.out.println(entry.name() + ":" + entry.format());
}
```

Đây là **mảnh minh họa**, cần `java.lang.reflect.Method`, class `ReportService` và definitions `Export` ở phần trước. Điểm quan trọng là dùng **`getAnnotationsByType(Export.class)`**, không dùng `getAnnotation(Export.class)` rồi giả sử luôn có đúng một entry.

Khi một annotation lặp được xuất hiện nhiều lần, compiler biểu diễn chúng qua container annotation. **`getAnnotationsByType` nhận biết container và trả các entry lặp** thành một mảng, khiến code tiêu thụ metadata nhất quán giữa trường hợp 1 entry và nhiều entry.

### So sánh bốn nhóm API phản chiếu

| API | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `getAnnotation(Export.class)` | Hỏi một annotation kiểu `Export` trực tiếp hiện diện/được trả theo quy tắc `getAnnotation` | Chủ yếu với annotation không lặp; có thể `null` khi chỉ có container |
| `getAnnotationsByType(Export.class)` | Trả những annotation `Export` *associated* theo luật reflection, gồm expanded container và có thể inheritance trên class | **Mặc định nên dùng** khi đọc annotation lặp |
| `getDeclaredAnnotationsByType(Export.class)` | Trả annotation lặp khai báo tại chính phần tử, không thừa kế từ superclass | Khi cần metadata local-only |
| `getDeclaredAnnotation(Exports.class)` | Hỏi container trực tiếp nếu nó hiện diện | Dùng khi thật sự cần xem container/raw representation |

Không nên suy ra từ `getAnnotations().length` rằng đó là số entry cấu hình. Vì compiler có thể biểu diễn nhiều annotation cùng loại trong **một container**, số declaration annotation objects phản chiếu ở cấp element không đồng nghĩa số entry logic.

Trong ví dụ có **hai `@Export`**, lệnh `getAnnotation(Export.class)` có thể trả `null` vì phần tử đang mang container chứ không mang một `Export` trực tiếp. `getAnnotationsByType(Export.class)` trả **hai** entry, đúng với điều code nghiệp vụ cần.

### Sự khác biệt giữa getAnnotationsByType và getDeclaredAnnotationsByType

Với annotation trên **method** như `@Export`, `@Inherited` không áp dụng, nên hai API thường cho cùng tập annotation trên chính method được phản chiếu. Với annotation trên **class** mà loại annotation được đánh dấu `@Inherited`, `getAnnotationsByType` có thể lấy từ superclass nếu class hiện tại không có declaration tương ứng; bản `getDeclared...` chỉ lấy local.

Vì vậy, khi xây công cụ framework, phải ghi rõ việc **có cho phép kế thừa metadata hay không**. Đừng tùy tiện chuyển giữa hai API rồi khiến runtime rules thay đổi.

## 7. Metadata là dữ liệu khai báo, không phải logic thực thi

`@Export(name="compact", format=JSON)` không tự tạo tệp JSON, không gọi method `publish` và không tự tạo bản ghi cấu hình. **Code consumer** phải định nghĩa quy tắc:

1. Quét method hoặc class nào?
2. Truy xuất annotation qua reflection hay compile-time model?
3. Loại bỏ cấu hình `enabled=false` hay vẫn hiển thị trong tài liệu?
4. Validate tên trống/trùng và các cặp trường không hợp lệ thế nào?
5. Nếu trùng `name`, báo lỗi, bỏ qua hay override?
6. Thứ tự thực thi có quan trọng không; nếu có, xác định ở đâu?
7. Sau khi hợp lệ, biến metadata thành cấu hình runtime hoặc registry nào?

Ví dụ một consumer có thể dùng:

```java
for (Export export : method.getAnnotationsByType(Export.class)) {
    if (!export.enabled()) {
        continue;
    }
    register(export.name(), export.format());
}
```

Đây chỉ là **minh họa thuật toán**: `register` là phương thức do ứng dụng định nghĩa, không phải API JDK. Nếu không có consumer, annotation vẫn chỉ tồn tại như metadata và không mang hiệu ứng nghiệp vụ.

**Quy tắc thiết kế:** tài liệu của annotation phải mô tả **consumer nào** sẽ đọc và **ngữ nghĩa của từng phần tử**. `@Repeatable` chỉ cho phép biểu diễn nhiều entry; nó không tự đưa ra chính sách xử lý chúng.

## 8. Xác định tính duy nhất, thứ tự và xung đột

Metadata mở rộng dễ trở thành gánh nặng nếu mỗi team hiểu khác nhau về duplicate và precedence.

### Chọn khóa định danh rõ ràng

Ví dụ `@Export` quy định `name` là khóa duy nhất trong phạm vi **một method**. Khi quét annotation, validate:

```java
Set<String> seen = new HashSet<>();

for (Export entry : method.getAnnotationsByType(Export.class)) {
    String key = entry.name().trim();
    if (key.isEmpty()) {
        throw new IllegalArgumentException("Export name is blank");
    }
    if (!seen.add(key)) {
        throw new IllegalArgumentException("Duplicate export: " + key);
    }
}
```

Đây là **mảnh code minh họa**, cần `java.util.Set`/`HashSet`, `Method` và annotation ở trên. Chuẩn hóa bằng `trim()` là chính sách tùy ứng dụng: nếu dùng `trim` để kiểm tra thì cũng phải thống nhất có dùng giá trị đã trim làm key không. Không nên để hệ thống lúc nhận tên có khoảng trắng, lúc so sánh lại bỏ khoảng trắng mà không có quy tắc.

### Thứ tự có mang ý nghĩa không?

Thứ tự viết các annotation lặp được bảo toàn trong cách chứa các entry theo quy tắc của Java đối với repeated annotations; nhưng API nghiệp vụ **không nên lạm dụng thứ tự source** làm ưu tiên nếu người dùng cần nhìn thấy quy tắc rõ ràng.

Nếu thứ tự là một phần yêu cầu nghiệp vụ, cân nhắc khai báo:

```java
@interface OrderedStep {
    String name();
    int order();
}
```

Đây là **annotation minh họa**. Với metadata ở nhiều module hoặc plugin, nên định nghĩa comparator rõ, chẳng hạn ưu tiên `order` rồi `name`, và quy định cách xử lý trùng `order`. Nếu thứ tự **không** quan trọng, hãy nói rằng các entries là một tập cấu hình logic và tránh phụ thuộc thứ tự reflection trong chương trình.

### Không tự động “last one wins” nếu không có hợp đồng

Hai dòng dưới đây có thể là cấu hình sai:

```java
@Export(name = "compact", format = ExportFormat.JSON)
@Export(name = "compact", format = ExportFormat.CSV)
void publish() {}
```

Đây là **minh họa khai báo**, Java có thể chấp nhận vì @Repeatable cho phép nhiều entry cùng loại. Nhưng **nghiệp vụ** có thể không cho hai cấu hình cùng `name`. Đừng âm thầm lấy entry cuối khiến lỗi cấu hình bị che giấu. Thông thường nên **fail fast** với thông báo chỉ rõ method và khóa trùng.

### Các quy tắc tổng hợp cần công khai

Khi có metadata thừa kế, quét nhiều class hoặc nhiều module, cần phân biệt:

- **Trùng entry trong cùng một declaration:** thông thường là lỗi.
- **Trùng key giữa hai declaration khác nhau:** tùy namespace ứng dụng; có thể hợp lệ hoặc không.
- **Override metadata ở subclass:** quy tắc kế thừa của Java reflection khác với chính sách merge của framework.
- **Trùng key sau khi normalize:** phải được validate giống trùng trực tiếp.

Hãy viết test cho những trường hợp này trước khi dùng metadata để quyết định hành vi thật.

## 9. Mở rộng schema mà không phá vỡ người dùng

Annotation type là một loại API. Khi đã có nhiều class dùng `@Export`, việc sửa schema phải coi là thay đổi hợp đồng.

### Thêm trường mới nên có default hợp lý

Phiên bản đầu:

```java
@interface Export {
    String name();
    ExportFormat format();
}
```

Khi muốn thêm mô tả:

```java
@interface Export {
    String name();
    ExportFormat format();
    String description() default "";
}
```

Đây là **hai phiên bản minh họa độc lập**, không định nghĩa đồng thời trong một file. Trường mới có default `""` giúp các source usages cũ không phải thêm `description` ngay. Nhưng cần nhớ: default phải có nghĩa ổn định; nếu `""` gây nhập nhằng giữa “không có mô tả” và “mô tả rỗng có chủ ý”, hãy viết rõ trong contract.

**Lưu ý:** mặc dù thêm phần tử có default giúp tương thích tốt hơn, mọi thay đổi public API vẫn phải kiểm tra các consumer và binary cũ. Thêm phần tử **bắt buộc** không có default có thể khiến mã source cũ không biên dịch khi rebuild hoặc dẫn tới lỗi truy cập giá trị annotation từ compiled artifact cũ.

### Không lạm dụng cờ “dự phòng”

Thêm liên tục các trường `mode2`, `legacyFormat`, `enabledForPartner`, `specialCase` dễ biến một annotation thành bộ cấu hình hỗn hợp. Thay vì vậy:

1. Định nghĩa mô hình domain rõ (`Export` là một biến thể xuất dữ liệu).
2. Dùng enum/annotation lồng khi thực sự là cấu trúc con ổn định.
3. Với dữ liệu thay đổi thường xuyên, trỏ tới **tên profile** bên ngoài thay vì đóng cứng toàn bộ dữ liệu vào annotation.
4. Giữ số trường bắt buộc thấp nhưng không hy sinh thông tin cần thiết.
5. Viết migration guide nếu đổi tên hoặc thay nghĩa trường.

### Đổi default cũng là thay đổi hành vi

Nếu `enabled() default true` đã được người dùng dựa vào, đổi sang `false` có thể thay đổi cách consumer xử lý **mọi entry không ghi rõ enabled** khi chạy phiên bản annotation library mới. “Code không đổi” không đồng nghĩa “behavior không đổi”.

Vì vậy, default cần **được xem như public contract**: ghi rõ trong Javadoc, test và chính sách phiên bản.

## 10. Reflection, compile-time processor và công cụ bytecode: chọn một nguồn sự thật

Khi chọn cách đọc metadata, cần xác định retention và thời điểm sử dụng.

### Runtime reflection

Nếu ứng dụng cần quét annotation khi khởi động, dùng `@Retention(RUNTIME)` và các API như `getAnnotationsByType`. Reflection thuận tiện cho registry dựa trên classpath/modulepath nhưng phải kiểm soát phạm vi quét, quyền truy cập và quy tắc xử lý lỗi.

**Không** quét toàn bộ classpath theo giả định JDK cung cấp API tự động liệt kê mọi class đang tồn tại. Java core reflection yêu cầu đã có `Class<?>` hoặc `AnnotatedElement` để hỏi annotation; việc *discover classes* là bài toán riêng của ứng dụng/framework.

### Compile-time annotation processing

Một annotation processor có thể phân tích các declaration trước khi chạy, báo lỗi trùng key và tạo registry/metadata lúc build. Các package chuẩn `javax.annotation.processing` và `javax.lang.model` vẫn tồn tại trong Java SE hiện đại. Với annotation lặp, cần hiểu annotation/container được mô hình hóa như thế nào và kiểm tra đúng các vị trí mục tiêu.

```java
// PSEUDOCODE minh họa chiến lược của processor:
// 1) Tìm các method có metadata Export hoặc Exports.
// 2) Lấy và chuẩn hóa các entry lặp.
// 3) Validate tên, format, duplicate, quyền truy cập.
// 4) Phát diagnostic tại vị trí source phù hợp.
// 5) Sinh registry nếu thật sự cần.
```

Đoạn trên **không phải API code có thể biên dịch**. Tùy compiler model và processor, có thể phải xem container annotation hoặc annotation mirrors thay vì giả sử API truy vấn mọi annotation lặp tự động phẳng hóa giống reflection.

### Phân tích bytecode

Nếu metadata cần tồn tại trong compiled dependencies nhưng không cần runtime reflection, `RetentionPolicy.CLASS` có thể đủ cho công cụ đọc class file. Với `SOURCE`, thông tin không được giữ lại ở binary. Các công cụ đọc bytecode phải hiểu annotation attributes của class file; không nên dùng Java reflection như một bộ đọc mọi metadata có retention `CLASS`.

### Tránh duy trì ba logic parser trái nhau

Nếu cùng một annotation được processor, runtime library và tool phân tích class file đọc, cần một **contract thống nhất** cho các yếu tố: duplicate, default, enum values, normalization và versioning. Có thể chia sẻ đặc tả/test fixtures; tránh mỗi tool tự diễn giải `@Export` theo một cách khác.

## 11. Metadata lặp với @Inherited: quy tắc không phải phép cộng dồn

Thừa kế metadata là đề tài dễ sai khi thiết kế annotation có thể lặp trên class.

Ví dụ annotation loại class:

```java
import java.lang.annotation.*;

@Inherited
@Repeatable(Labels.class)
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}

@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface Labels {
    Label[] value();
}
```

Đây là **khai báo minh họa**. Cả loại lặp `Label` và container `Labels` đều có `@Inherited`, phù hợp các ràng buộc khi muốn inheritance.

```java
@Label("base-a")
@Label("base-b")
class Base {}

class Child extends Base {}

@Label("child")
class SpecializedChild extends Base {}
```

Đây là **minh họa** dùng các annotation ở trên. Ở cấp class:

- `Child.class.getAnnotationsByType(Label.class)` có thể lấy hai labels từ `Base` vì `Child` không khai báo `Label`/container tương ứng, và `Label` là `@Inherited`.
- `SpecializedChild.class.getAnnotationsByType(Label.class)` cho **metadata khai báo ở child** thay vì tự động gộp các labels ở `Base`. Đối với repeatable annotation, luật truy xuất *associated annotations* không định nghĩa phép cộng dồn tùy ý qua class hierarchy.
- `getDeclaredAnnotationsByType(Label.class)` chỉ phản ánh metadata khai báo trực tiếp ở class đang xét.

**Đừng nhầm** `@Inherited` với inheritance của interface: annotation trên interface không được tự truyền qua class `implements` nó chỉ vì có `@Inherited`. `@Inherited` cũng không làm annotation của method cha “tự bám vào method override” trong class con.

Nếu yêu cầu nghiệp vụ là **merge tất cả labels từ mọi lớp cha**, framework phải tự đi qua superclass chain, quyết định thứ tự, precedence và deduplication. Java reflection không tự định nghĩa một phép merge chung cho metadata domain của bạn.

## 12. Sự tương tác giữa annotation lặp và type-use annotation

`@Repeatable` là một tính chất của annotation type, còn `@Target(TYPE_USE)` cho phép nó xuất hiện trên **vị trí dùng kiểu**. Có thể kết hợp hai khái niệm khi thật sự cần nhiều nhãn trên một type argument hoặc type component.

```java
import java.lang.annotation.*;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Qualifiers.class)
@interface Qualifier {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Qualifiers {
    Qualifier[] value();
}

class Sample {
    java.util.List<
            @Qualifier("public")
            @Qualifier("normalized")
            String> names;
}
```

Đây là **khai báo minh họa**, không phải chương trình chạy. Vì annotation nằm trên **`String` trong type argument**, muốn lấy chúng bằng reflection cần dùng `AnnotatedParameterizedType` và `AnnotatedType`:

```java
java.lang.reflect.Field field =
        Sample.class.getDeclaredField("names");

java.lang.reflect.AnnotatedParameterizedType type =
        (java.lang.reflect.AnnotatedParameterizedType)
                field.getAnnotatedType();

Qualifier[] qualifiers = type.getAnnotatedActualTypeArguments()[0]
        .getAnnotationsByType(Qualifier.class);
```

Đoạn minh họa cần xử lý `NoSuchFieldException`. Không nên gọi `field.getAnnotationsByType(Qualifier.class)` rồi kết luận không có metadata: đó là API hỏi **field declaration**, trong khi annotation nằm trên **type argument**.

**Lựa chọn thiết kế:** chỉ cho phép `TYPE_USE` khi metadata thực sự mô tả *kiểu tại vị trí sử dụng* (ví dụ qualifier phục vụ static analysis). Nếu một annotation mô tả chính method hoặc endpoint, `METHOD` thường rõ nghĩa hơn; đừng mở target lên toàn bộ vị trí chỉ vì “có thể mở rộng”.

## 13. Cách tổ chức code để reviewer đọc nhanh

Một guideline cho metadata lặp trong source:

```java
@Export(name = "summary", format = ExportFormat.JSON)
@Export(name = "table", format = ExportFormat.CSV)
public void publishReport() {
    // ...
}
```

Đây là minh họa. Người review thấy nhanh **hai entry** và **hai tên**. Nếu annotation có nhiều tham số:

```java
@Export(
        name = "summary",
        format = ExportFormat.JSON,
        enabled = true
)
@Export(
        name = "archive",
        format = ExportFormat.CSV,
        enabled = false
)
public void publishReport() {
    // ...
}
```

Cách xuống dòng giúp đọc khi đủ dài, nhưng **đừng khai báo `enabled=true` ở mọi nơi** nếu đã là default rõ ràng và việc viết ra làm nhiễu trọng tâm. Nên đặt các annotations lặp gần nhau, dùng thứ tự ổn định khi sort source, không trộn lẫn các loại annotation không liên quan giữa các entries.

Khi annotation chỉ có một String chính và được lặp nhiều lần:

```java
@Alias("customer-id")
@Alias("client-id")
@Alias("account-id")
String id;
```

Đây là minh họa, cần loại `Alias` được định nghĩa `@Repeatable`, target `FIELD` và container thích hợp. Việc đọc dễ hơn một chuỗi duy nhất `"customer-id, client-id, account-id"` vì dữ liệu có cấu trúc, không cần tự split dấu phẩy và xử lý escaping.

### Tránh “annotation jungle”

Khi một method có hàng chục annotation lặp chứa policy thay đổi liên tục, metadata có thể **đang sai vị trí thiết kế**. Cân nhắc:

- Một named policy profile: `@PolicyProfile("customer-export-v2")`, để dữ liệu lớn nằm trong cấu hình ngoài.
- Một object cấu hình hoặc builder, nếu có validation/conditional logic cần runtime.
- Một bảng dữ liệu/versioned schema nếu người dùng không biên dịch lại app mỗi khi sửa policy.

Không nên giữ toàn bộ danh sách quyền truy cập, route hoặc luật tài chính dưới dạng source annotation chỉ để tạo vẻ khai báo.

## 14. Chương trình Java 17+ hoàn chỉnh: annotation lặp có validation và reflection

Ví dụ độc lập này minh họa cách định nghĩa **metadata có thể mở rộng nhưng dễ đọc**. Một method có hai cấu hình `@Export`. Runtime đọc entries bằng `getAnnotationsByType`, kiểm tra tên duy nhất, nhận enum format, bỏ qua cấu hình disabled khi đếm active, và phân biệt container với annotation đơn.

Tệp **RepeatableMetadataDemo.java**:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.HashSet;
import java.util.Set;

public class RepeatableMetadataDemo {

    enum ExportFormat {
        JSON, CSV, TEXT
    }

    @Documented
    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    @Repeatable(Exports.class)
    @interface Export {
        String name();
        ExportFormat format();
        boolean enabled() default true;
    }

    @Documented
    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Exports {
        Export[] value();
    }

    static class ReportService {
        @Export(name = "compact", format = ExportFormat.JSON)
        @Export(name = "table", format = ExportFormat.CSV,
                enabled = false)
        public void publish() {
            // Application code decides how to publish.
        }

        @Export(name = "audit", format = ExportFormat.TEXT)
        public void audit() {
            // A method with just one export entry.
        }
    }

    static void inspect(Method method) {
        Export[] entries = method.getAnnotationsByType(Export.class);
        Set<String> usedNames = new HashSet<>();
        int enabledCount = 0;

        for (Export entry : entries) {
            String key = entry.name();
            if (key.isBlank() || !key.equals(key.strip())) {
                throw new IllegalArgumentException(
                        "Invalid export name: " + key);
            }
            if (!usedNames.add(key)) {
                throw new IllegalArgumentException(
                        "Duplicate export name: " + key);
            }

            System.out.println(entry.name() + "|"
                    + entry.format() + "|" + entry.enabled());

            if (entry.enabled()) {
                enabledCount++;
            }
        }

        System.out.println("entries=" + entries.length
                + ", enabled=" + enabledCount);
    }

    public static void main(String[] args) throws Exception {
        Method publish =
                ReportService.class.getDeclaredMethod("publish");

        Export[] repeated = publish.getAnnotationsByType(Export.class);
        Exports container =
                publish.getDeclaredAnnotation(Exports.class);

        System.out.println("repeated=" + repeated.length);
        System.out.println("container=" +
                (container == null ? 0 : container.value().length));
        System.out.println("singleDirect=" +
                (publish.getDeclaredAnnotation(Export.class) != null));

        inspect(publish);

        Method audit =
                ReportService.class.getDeclaredMethod("audit");

        System.out.println("auditDirect=" +
                (audit.getDeclaredAnnotation(Export.class) != null));
        inspect(audit);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RepeatableMetadataDemo.java
java RepeatableMetadataDemo
```

**Stdout chính xác:**

```text
repeated=2
container=2
singleDirect=false
compact|JSON|true
table|CSV|false
entries=2, enabled=1
auditDirect=true
audit|TEXT|true
entries=1, enabled=1
```

**Giải thích kết quả:**

1. `getAnnotationsByType(Export.class)` trả **2** entry khi method `publish` khai báo hai `@Export`.
2. `getDeclaredAnnotation(Exports.class)` cho thấy container tương ứng cũng có hai phần tử.
3. `getDeclaredAnnotation(Export.class)` trả `null` cho method `publish`, vì trường hợp lặp được chứa gián tiếp; `singleDirect=false`.
4. Mỗi entry in đúng tên, enum format và cờ `enabled`. Giá trị mặc định `true` được dùng cho `compact`.
5. `enabledCount` bằng **1** vì `table` được khai báo `enabled=false`. Ví dụ **vẫn in metadata của entry disabled**, rồi mới tính số active: đây là chính sách minh bạch hơn là “giấu mất” entry.
6. Method `audit` chỉ có một `@Export` trực tiếp, nên `auditDirect=true` và `getAnnotationsByType` vẫn trả một phần tử. Consumer dùng **cùng một API** cho cả một và nhiều annotation.

Ví dụ dùng đúng các meta-annotations còn được hỗ trợ, không cần framework, database hoặc thao tác I/O ngoài. Nó cũng không tự thực thi method `publish()`: trình quét metadata chỉ quan sát cấu hình; hành vi export thực tế phải được viết riêng trong application logic.

## 15. Kiểm thử metadata như một phần của public API

Không nên dừng tại việc “compile được”. Một annotation library trưởng thành cần test cho ít nhất những khía cạnh sau:

| Nhóm test | Ví dụ | Điều cần xác nhận |
| --- | --- | --- |
| Không có entry | Method không có `@Export` | `getAnnotationsByType` trả mảng rỗng |
| Một entry | Chỉ `@Export("...")` hoặc named fields | Một phần tử, target hợp lệ |
| Nhiều entry | Hai hoặc ba `@Export` | API đúng trả đủ các entry |
| Container trực tiếp | `@Exports({...})` | Consumer vẫn thu được logical entries |
| Default | Không ghi `enabled` | Giá trị default đúng |
| Trùng khóa | Hai entry cùng `name` | Consumer báo lỗi rõ |
| Khóa rỗng | `name=""` hoặc toàn whitespace | Validation bắt lỗi |
| Enum value | Mỗi `ExportFormat` được hỗ trợ | Consumer xử lý đúng |
| Retention | Runtime reflection trên compiled class | Metadata còn tồn tại |
| Target | Gắn vào nơi không được phép | Compiler báo lỗi |
| Kế thừa | Class annotations có/không `@Inherited` | Đúng precedence/merge policy |
| Tương thích | Consumer build với version cũ/mới | Không vô tình đổi default hoặc mất dữ liệu |

### Test cả nguồn lẫn compiled artifact

Với annotation lặp `RUNTIME`, test reflection trên class thực sự đã compile. Nếu dùng `CLASS` cho bytecode processor, test công cụ đọc class file. Nếu dùng `SOURCE` cho annotation processor, test code generation hoặc diagnostic ngay tại compile time.

**Một kiểu test duy nhất không chứng minh mọi giai đoạn.** Test runtime không cho biết annotation processor có nhận đầy đủ type-use metadata hay không; test processor không bảo đảm reflection runtime đọc được nếu retention không đúng.

### Validation sớm và thông báo lỗi tốt

Khi phát hiện duplicate, hãy báo:

- Tên annotation và tên field làm khóa;
- Class/method chứa metadata;
- Các giá trị bị xung đột;
- Nguyên tắc xử lý: “không được khai báo hai export cùng tên”;
- Gợi ý sửa: đổi tên hoặc xóa entry trùng.

Nếu có thể validate trong build, lỗi sẽ được phát hiện sớm hơn runtime. Nhưng xây annotation processor chỉ để xử lý một trường hợp đơn giản chưa chắc đáng công sức; cân nhắc quy mô và độ ổn định của API.

## 16. Những anti-pattern dễ làm metadata khó bảo trì

### Anti-pattern 1 — Một annotation chứa mọi định dạng

```java
@interface OutputOptions {
    boolean csv() default false;
    boolean json() default false;
    boolean xml() default false;
    boolean includeHeader() default false;
    boolean encrypt() default false;
    boolean email() default false;
}
```

Đây là thiết kế **minh họa không nên bắt chước**. Nó trộn định dạng, chính sách header, bảo mật và kênh phân phối vào một tập cờ không rõ quan hệ, khiến số tổ hợp tăng nhanh. Tách khái niệm theo trách nhiệm; dùng annotation lặp cho một loại entry nhất quán.

### Anti-pattern 2 — Đóng gói dữ liệu thành chuỗi cần tự parse

```java
// KHÓ ĐỌC, dễ lỗi escaping:
@Options("compact:JSON;table:CSV;archive:TEXT")
```

Đây là **minh họa** với annotation `@Options` chưa định nghĩa. Một string DSL khiến compiler không kiểm tra enum, khó refactor và dễ hỏng khi giá trị chứa dấu phân tách. Nên dùng structured annotation elements nếu dữ liệu nhỏ và tĩnh.

### Anti-pattern 3 — Trộn mã thực thi vào kỳ vọng metadata

```java
@Export(name = "audit", format = ExportFormat.TEXT)
// Java không tự gọi method này chỉ vì nó có annotation.
void doSomething() {}
```

Đây là minh họa. Annotation không chứa body thực thi; application cần một consumer hoặc framework rõ ràng. Không ghi hướng dẫn kiểu “gắn annotation thì tự động chạy” nếu chưa mô tả framework và lifecycle.

### Anti-pattern 4 — Không đồng bộ @Retention của container

Một annotation lặp cần reflection runtime nhưng container chỉ `CLASS` là thiết kế sai và có thể bị compiler từ chối theo điều kiện của `@Repeatable`. Xác định chính xác policy cho cả hai; unit test có hai hoặc nhiều annotations trực tiếp để bảo đảm container hoạt động.

### Anti-pattern 5 — Chỉ dùng getAnnotation

Đoạn này dễ bỏ sót metadata khi có nhiều entries:

```java
Export export = method.getAnnotation(Export.class);
// Có thể null khi hai Export được chứa trong Exports.
```

Đây là minh họa. Thay bằng `Export[] exports = method.getAnnotationsByType(Export.class);` để đọc trường hợp repeatable đúng ý định.

### Anti-pattern 6 — Để metadata kế thừa mơ hồ

Không mặc định `@Inherited` gộp tất cả thông tin ở superclass/interface. Đối với cấu hình có tính chồng lớp, phải mô tả một thuật toán rõ ràng. Nếu chỉ muốn lấy metadata ở declaration đang xét, dùng `getDeclaredAnnotationsByType`.

### Anti-pattern 7 — Mọi thứ đều optional

Annotation có quá nhiều `default ""`, `default 0`, `default false` dễ chấp nhận entry vô nghĩa và khiến consumer phải đoán. Những thuộc tính **bắt buộc về mặt domain** nên là phần tử không default; các thuộc tính thực sự tùy chọn mới nên có default được đặc tả rõ.

### Anti-pattern 8 — Không xử lý xung đột

`@Repeatable` cho phép nhiều annotation cùng loại, nhưng **không** định nghĩa duplicate nghiệp vụ. Nếu hai entry cùng khóa nhưng khác format, silent override có thể gây kết quả sai. Validate sớm, fail fast và viết thông báo có ngữ cảnh.

### Anti-pattern 9 — Thay đổi tên hoặc nghĩa thuộc tính mà không có migration

Một lần refactor tên từ `format` sang `type` có thể làm hàng trăm source usages phải thay đổi. Với binary đã compile, thay đổi annotation element còn phức tạp hơn. Thiết kế schema kỹ ngay từ đầu, thêm trường có default hợp lý khi cần, có migration và test người dùng thực.

### Anti-pattern 10 — Lạm dụng annotation để lưu dữ liệu runtime động

Danh sách export thay đổi theo quyền từng người dùng, thời điểm hoặc cấu hình môi trường thường không nên biên dịch cứng vào source. Dùng annotation để mô tả **khả năng tĩnh**, rồi dùng runtime configuration để quyết định **cái gì bật cho ai**.

## 17. Quy trình thiết kế một annotation lặp có thể mở rộng

Trước khi định nghĩa một loại annotation mới, làm tuần tự:

1. **Mô tả một entry bằng câu tiếng Việt rõ ràng.** Ví dụ: “một Export khai báo một biến thể xuất báo cáo”.
2. **Xác nhận cần lặp.** Nếu có thể có 0, 1, nhiều entry cùng schema tại một declaration, `@Repeatable` đáng cân nhắc.
3. **Quy định phạm vi áp dụng.** Chỉ class, method, field, parameter hay type use? Chọn `@Target` nhỏ nhất đủ dùng.
4. **Quy định người đọc.** Build tool, annotation processor, bytecode processor, runtime reflection hay framework?
5. **Chọn retention theo người đọc.** Đồng bộ annotation lặp và container.
6. **Chọn khóa định danh.** Tên entry có bắt buộc duy nhất không? Có phân biệt hoa/thường không?
7. **Thiết kế các phần tử.** Tên rõ nghĩa, kiểu hợp lệ, enum khi tập giá trị ổn định; tránh trạng thái bất khả thi.
8. **Chọn default có hợp đồng.** Chỉ default thứ thật sự tùy chọn; không dùng default vô nghĩa để né validation.
9. **Chọn tên container gợi nghĩa.** `Export`/`Exports` hoặc `Alias`/`Aliases`, với `value(): T[]` và meta-annotations tương thích.
10. **Định nghĩa thứ tự và trùng lặp.** Nếu thứ tự có nghĩa thì ghi metadata thứ tự tường minh; nếu trùng thì báo lỗi hoặc có quy tắc rõ.
11. **Xây consumer dùng API by-type.** Đừng giả định annotation luôn chỉ xuất hiện một lần.
12. **Kiểm thử một/nhiều/không có annotation.** Thêm test retention, target, default, duplicate và inheritance nếu có.
13. **Chuẩn bị chiến lược versioning.** Metadata là public contract, không đổi nghĩa ngầm khi phát hành phiên bản mới.
14. **Đánh giá mức độ phức tạp.** Nếu metadata quá dài hoặc quá động, chuyển sang model/config phù hợp thay vì tiếp tục thêm annotation.

## 18. Bài tập thực hành

**Bài 1 — định nghĩa Repeatable.** Tạo `@Alias(value)` có thể lặp trên một field. Định nghĩa container `@Aliases` với `Alias[] value()` và đặt `@Target(FIELD)`, `@Retention(RUNTIME)` tương thích cho cả hai. Gắn ba alias lên một field và dùng `Field.getAnnotationsByType(Alias.class)` để đọc.

**Bài 2 — một annotation và nhiều annotation.** Có hai method: method thứ nhất chỉ có một `@Alias`, method thứ hai có hai `@Alias`. So sánh kết quả `getAnnotation(Alias.class)` và `getAnnotationsByType(Alias.class)`. **Gợi ý:** by-type là API ổn định cho cả hai trường hợp; container ảnh hưởng đến cách metadata hiện diện trực tiếp.

**Bài 3 — validation.** Bổ sung kiểm tra alias không rỗng, không chỉ chứa whitespace và không trùng sau một quy tắc normalize mà bạn công bố rõ. Nếu trùng, ném `IllegalArgumentException` ghi tên field và alias.

**Bài 4 — retention.** Thay `RUNTIME` thành `CLASS` cho cả annotation lặp và container, biên dịch rồi thử reflection. **Đáp án định hướng:** metadata có thể được giữ trong class file nhưng Java core reflection không trả các annotations đó. Không nhầm “không thấy ở reflection” với “không được lưu trong binary”.

**Bài 5 — thay đổi schema.** Có `@Export(name,format)` đang được dùng ở nhiều nơi. Thêm trường `description` mà không buộc sửa mọi call site. **Gợi ý:** `String description() default "";`, đồng thời ghi rõ nghĩa của default trong Javadoc.

**Bài 6 — source readability.** So sánh `@Options("a:X;b:Y")` với hai `@Option(name="a",type=X)`/`@Option(name="b",type=Y)`. Phân tích về compiler checking, escaping, hỗ trợ IDE và chi phí mở rộng schema.

**Bài 7 — inherited annotations.** Thiết kế class annotation `@Label` repeatable và `@Inherited`, triển khai container tương thích. Dự đoán `getAnnotationsByType(Label.class)` trên class con không khai báo annotation và trên class con có nhãn riêng. **Đáp án định hướng:** không có mặc định gộp tất cả labels cha/con; phải kiểm tra luật associated annotation và chọn chính sách merge của framework nếu cần.

**Bài 8 — miền dữ liệu hay metadata?** Danh sách 500 quyền thay đổi hàng ngày theo từng khách hàng có nên viết dưới dạng 500 `@Permission` lặp trên một method không? **Gợi ý:** thường không; annotation lặp thích hợp metadata tĩnh với số entry vừa phải, còn quyền runtime động cần kho cấu hình/dữ liệu và chính sách bảo mật riêng.

## 19. Ghi nhớ nhanh

- `@Repeatable(Container.class)` cho phép **một annotation type xuất hiện nhiều lần** ở cùng vị trí hợp lệ.
- Container cần phần tử `value()` có kiểu **mảng của annotation lặp** và phải có các meta-annotations tương thích.
- **Đọc bằng `getAnnotationsByType(T.class)`** khi cần danh sách entry logic; đừng dùng một `getAnnotation` cho toàn bộ tập.
- **`@Retention` và `@Target` là một phần thiết kế API**, không phải chi tiết tùy ý. Nếu cần reflection, dùng `RUNTIME` và target đúng vị trí.
- **Annotation không tự có hành vi**; phải có consumer/validator/framework cụ thể để áp dụng metadata.
- Mỗi entry nên **nhỏ, có khóa rõ, tên trường dễ hiểu, kiểu chặt và default có nghĩa**.
- Duplicate và thứ tự là quyết định của **domain**, không tự được giải quyết bởi `@Repeatable`.
- `@Inherited` không có nghĩa tự gộp metadata trên mọi class/interface/method.
- **Mở rộng schema an toàn:** thêm trường có default hợp lý khi cần, kiểm thử source/binary consumers, tài liệu hóa versioning.
- Khi dữ liệu quá động hoặc quá nhiều, **đừng cố dùng annotation như một database cấu hình**.

### Tài liệu chính thức

- [JLS `9.6.3 — Repeatable Annotation Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.3)
- [JLS `9.7.5 — Multiple Annotations of the Same Type](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.5)
- [Java SE 25 — Repeatable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Repeatable.html)
- [Java SE 25 — AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 25 — Retention](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html)
- [Java SE 25 — Target](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html)
- [Java SE 25 — Inherited](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Inherited.html)
