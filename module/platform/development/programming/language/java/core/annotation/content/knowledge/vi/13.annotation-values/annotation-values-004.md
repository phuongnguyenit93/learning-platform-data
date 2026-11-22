# Biểu diễn toString của annotation và giới hạn khi dùng làm định dạng lưu trữ trong Java

## 1. Vấn đề: toString() hiển thị được, nhưng có lưu trữ lâu dài được không?

Trong Java, một annotation được đọc tại runtime có thể được xem như một đối tượng triển khai giao diện `java.lang.annotation.Annotation`. Đối tượng đó hỗ trợ phương thức `toString()`:

```java
MyConfig config = SomeClass.class.getAnnotation(MyConfig.class);
System.out.println(config.toString());
```

Đoạn trên chỉ là **mẫu cách gọi** (giả định đã định nghĩa `MyConfig` và `SomeClass` có annotation tương ứng). Kết quả thường có vẻ giống một annotation viết trong source, chẳng hạn:

```text
@com.example.MyConfig(name="demo", enabled=true)
```

Tuy nhiên, **đây chỉ là ví dụ hình thức thường gặp, không phải định dạng đầu ra được Java bảo đảm**. Tài liệu chính thức của `Annotation.toString()` nêu rõ chi tiết cách biểu diễn là **implementation-dependent** (phụ thuộc implementation).

Vì vậy, cần phân biệt:

- **Hiển thị / debug / log:** `annotation.toString()` có ích khi người đọc muốn nhìn nhanh metadata.
- **Xử lý nghiệp vụ:** đọc trực tiếp các phần tử annotation bằng accessor có kiểu rõ ràng, ví dụ `config.name()`, `config.enabled()`.
- **Lưu trữ / trao đổi dữ liệu lâu dài:** chuyển các phần tử thành **một schema có phiên bản** và dùng bộ mã hóa/giải mã được quy định rõ; **không dùng `toString()` như JSON, dữ liệu cấu hình chuẩn hoặc khóa định danh bền vững**.

Giới hạn này thuộc **hợp đồng API**, không phụ thuộc việc một phiên bản OpenJDK nhất định in ra chuỗi trông có vẻ đều đặn.

## 2. Hợp đồng của java.lang.annotation.Annotation

Mọi annotation interface trong Java mở rộng `java.lang.annotation.Annotation` theo quy tắc ngôn ngữ. Những phương thức cần phân biệt gồm:

| Phương thức | Mục đích | Mức độ cam kết hữu ích |
| --- | --- | --- |
| `annotationType()` | Xác định annotation interface mà đối tượng biểu diễn | Trả về kiểu annotation, đáng tin cậy hơn `getClass()` của implementation |
| `equals(Object)` | So sánh hai annotation theo kiểu và giá trị các phần tử | Hợp đồng so sánh logic được đặc tả |
| `hashCode()` | Tạo mã băm nhất quán với `equals` theo quy tắc thành viên | Có quy tắc tính; không phải định dạng lưu trữ hoặc ID |
| `toString()` | Tạo chuỗi biểu diễn annotation | **Chi tiết biểu diễn phụ thuộc implementation** |
| Accessor của annotation, ví dụ `name()` | Lấy giá trị một phần tử được khai báo trong annotation interface | Giá trị có **kiểu Java được khai báo**, thích hợp để xử lý cấu trúc |

Tài liệu Java SE 17 mô tả `toString()` là trả về một string representation và coi một dạng như `@com.example.Name(first="Duke", middle="of", last="Java")` là **typical**, chứ không quy định tất cả JVM phải trả đúng chuỗi đó.

Một khác biệt nữa: **`annotation.annotationType()`** là cách chuẩn để biết annotation interface. Gọi `annotation.getClass()` thường trả về class triển khai do runtime tạo, có thể là proxy hoặc một implementation detail, không phải loại `@interface` cần đưa vào schema.

### 2.1. Vì sao có thể gọi toString() dù annotation chỉ là metadata?

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Audit {
    String value();
}

@Audit("billing")
class Invoice {}
```

Một chương trình có thể đọc `Audit` thông qua:

```java
Audit audit = Invoice.class.getAnnotation(Audit.class);
System.out.println(audit.value());    // billing
System.out.println(audit.toString()); // Hình thức chuỗi phụ thuộc runtime
```

`@Retention(RUNTIME)` cần thiết vì không có retention tường minh thì annotation mặc định là `CLASS` và reflection Java thông thường sẽ không trả về đối tượng annotation này.

**Lưu ý:** `Annotation.toString()` nói đến **đối tượng annotation** mà API runtime trả về. Không phải mọi annotation xuất hiện trong source đều có đối tượng runtime để gọi phương thức này (chẳng hạn `@Override` có SOURCE retention).

## 3. Một biểu diễn toString điển hình có thể chứa những gì?

Giả sử có annotation sau:

```java
enum Mode {
    SAFE, FAST
}

@interface JobInfo {
    String id();
    Mode mode() default Mode.SAFE;
    String[] labels() default {};
}
```

Một lần sử dụng:

```java
@JobInfo(
    id = "batch=alpha, beta",
    mode = Mode.FAST,
    labels = {"night", "etl"}
)
class BatchJob {}
```

Chuỗi do `toString()` tạo có thể chứa tên kiểu annotation, tên các phần tử, giá trị chuỗi, enum, mảng và cả giá trị mặc định. Nhưng Java **không cam kết cú pháp chính xác của chuỗi đó**. Do đó, không được thiết kế parser chỉ dựa trên những điểm tưởng là hiển nhiên như:

- Chuỗi luôn bắt đầu bằng `@` theo đúng định dạng mình thấy ở một JDK.
- Tên annotation luôn được in dạng fully qualified hay tên ngắn.
- Các cặp `name=value` luôn theo thứ tự khai báo trong source.
- Mảng luôn dùng cùng một kiểu ngoặc, dấu phân cách và spacing.
- Chuỗi con có dấu phẩy, dấu bằng hoặc dấu ngoặc kép sẽ luôn được escape theo một quy tắc có thể đảo ngược.
- Các phần tử có default luôn được hiển thị hoặc luôn bị bỏ qua.
- Nested annotation, `Class` literal, enum và ký tự Unicode luôn dùng một quy tắc mà parser tự viết có thể dựa vào.
- Hai JVM, hai phiên bản JDK hoặc hai thư viện proxy annotation sẽ sinh cùng chuỗi từng ký tự.

Một vài điểm có thể trông ổn định trong thực nghiệm, nhưng **hợp đồng `Annotation.toString()` không định nghĩa một serialization grammar có thể dùng làm giao thức**. Mục tiêu chính của API này là cung cấp thông tin dễ đọc, không phải khôi phục lại object ban đầu.

### 3.1. Không nhầm toString() với cú pháp annotation trong source

Annotation trong Java source có cú pháp được Java Language Specification quy định. Còn `toString()` của annotation object là cách runtime chọn biểu diễn object đó.

Ngay cả khi đầu ra nhìn giống:

```text
@JobInfo(id="job-1", mode=FAST)
```

không thể kết luận string ấy là một Java expression hợp lệ để compiler parse, hoặc có đủ thông tin để tái tạo annotation type, các default và các kiểu phần tử.

Đặc biệt, Java không cung cấp API chuẩn kiểu `Annotation.parse(String)` hoặc `new Annotation(string)` để round-trip `toString()`. Annotation interface cũng không được khởi tạo bằng `new` như class thông thường.

## 4. Ví dụ Java 17+ chạy độc lập: toString để debug, accessor để lấy dữ liệu

Tạo file **AnnotationToStringDemo.java**. Chương trình sử dụng annotation có giá trị phức tạp, đọc metadata bằng reflection và **không phụ thuộc vào định dạng nội dung của `toString()`** khi tính toán các dòng output.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.List;

enum Mode {
    SAFE, FAST
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobInfo {
    String id();
    Mode mode() default Mode.SAFE;
    String[] labels() default {};
}

@JobInfo(
    id = "batch=alpha, beta",
    mode = Mode.FAST,
    labels = {"night", "etl"}
)
class JobOne {}

@JobInfo(
    id = "batch=alpha, beta",
    mode = Mode.FAST,
    labels = {"night", "etl"}
)
class JobTwo {}

record JobSnapshot(
        int schemaVersion,
        String annotationType,
        String id,
        String mode,
        List<String> labels) {}

public class AnnotationToStringDemo {
    private static JobSnapshot snapshot(JobInfo annotation) {
        return new JobSnapshot(
                1,
                annotation.annotationType().getName(),
                annotation.id(),
                annotation.mode().name(),
                List.copyOf(Arrays.asList(annotation.labels())));
    }

    public static void main(String[] args) {
        JobInfo first = JobOne.class.getAnnotation(JobInfo.class);
        JobInfo second = JobTwo.class.getAnnotation(JobInfo.class);

        String debugText = first.toString(); // Dùng để xem/log, không parse.
        JobSnapshot stored = snapshot(first); // Dữ liệu có cấu trúc.

        System.out.println("type=" + first.annotationType().getSimpleName());
        System.out.println("id=" + first.id());
        System.out.println("mode=" + first.mode().name());
        System.out.println("labels=" + String.join("|", first.labels()));
        System.out.println("equal=" + first.equals(second));
        System.out.println("snapshot version=" + stored.schemaVersion());
        System.out.println("snapshot labels=" + stored.labels().size());
        System.out.println("debug String=" + (debugText != null));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AnnotationToStringDemo.java
java AnnotationToStringDemo
```

Stdout:

```text
type=JobInfo
id=batch=alpha, beta
mode=FAST
labels=night|etl
equal=true
snapshot version=1
snapshot labels=2
debug String=true
```

### 4.1. Giải thích kết quả

1. `getAnnotation(JobInfo.class)` hoạt động vì `JobInfo` có `@Retention(RUNTIME)` và được gắn trên class.
2. `annotationType().getSimpleName()` trả về `JobInfo`, không phụ thuộc class proxy mà runtime có thể dùng để triển khai annotation.
3. `id()` trả về đúng giá trị `"batch=alpha, beta"`. Dấu bằng và dấu phẩy **là dữ liệu**, không được tách bằng `String.split(",")` khi đọc annotation.
4. `mode()` trả về enum `Mode.FAST`; `name()` cho tên hằng rõ ràng `FAST`.
5. `labels()` trả mảng string; `String.join("|", ...)` được dùng **chỉ để hiển thị dòng ví dụ**. Dữ liệu có cấu trúc thực sự được giữ dưới dạng `List<String>`.
6. Hai class có cùng annotation type và cùng giá trị tất cả phần tử, nên `first.equals(second)` trả `true` theo hợp đồng `Annotation.equals`.
7. `JobSnapshot` giữ các thành phần đã được chọn và một `schemaVersion`; bản thân một record vẫn là **đối tượng trong bộ nhớ**, **không tự định nghĩa wire format**. Muốn lưu trữ lâu dài còn phải tuần tự hóa record theo schema được kiểm soát.
8. `toString()` được gọi để tạo `debugText`, nhưng code không phân tích nội dung text đó và không đặt kỳ vọng cố định về trật tự hay cách in các phần tử. Dòng cuối chỉ kiểm tra string đã được tạo trong môi trường chạy ví dụ.

Để xem hình thức thực tế trên JDK đang dùng, có thể **thêm** một dòng trong `main`:

```java
System.out.println(debugText);
```

Đây là phép thử quan sát. **Kết quả dòng bổ sung không được coi là định dạng output ổn định** và vì thế không được đưa vào stdout chính xác ở trên.

### 4.2. Tại sao không lấy getClass() của annotation?

Khi muốn ghi kiểu annotation trong dữ liệu có cấu trúc:

```java
String stableTypeName = first.annotationType().getName();
```

`annotationType()` trả về annotation interface mà metadata mô tả. Trong khi đó:

```java
String implementationName = first.getClass().getName();
```

có thể cho tên lớp thực thi do JVM hoặc thư viện sử dụng; đây **không phải** định danh kiểu annotation nên đưa vào schema.

Ngay cả tên annotation interface cũng cần được xem như **tên kiểu theo phiên bản phần mềm**: đổi package, rename annotation, module hoặc xóa class có thể ảnh hưởng việc đọc dữ liệu đã lưu. Một schema bền vững nên quy định tên logic và chiến lược migration thay vì mặc định rằng tên class không bao giờ đổi.

## 5. Tại sao không dùng toString() để lưu file, database hay gửi qua API?

### 5.1. Không có ngữ pháp (grammar) chuẩn để parse ngược

Giả sử một chương trình ghi thẳng:

```java
String saved = first.toString();
// Ghi saved vào DB hoặc file cấu hình...
```

Lần sau muốn đọc lại, bạn sẽ phải tự giải bài toán tách tên annotation, trường, giá trị, dấu phân cách và kiểu dữ liệu. Nhưng Java SE **không cam kết** định dạng cho các thành phần đó trong `Annotation.toString()`.

Viết kiểu:

```java
// Phản ví dụ: không sử dụng làm parser annotation.
String[] pieces = saved.split(",");
```

sẽ không đáng tin ngay cả với `id = "batch=alpha, beta"`, chưa nói tới nested annotation, array, chuỗi có dấu ngoặc và ký tự escape.

### 5.2. Không có hợp đồng round-trip

Một định dạng lưu trữ cần ít nhất hai hướng rõ ràng:

```text
Giá trị có cấu trúc --> mã hóa --> dữ liệu lưu trữ
Giá trị có cấu trúc <-- giải mã <-- dữ liệu lưu trữ
```

Với `Annotation.toString()`, Java không cung cấp bộ parser/decoder tiêu chuẩn đảm bảo:

```text
parse(annotation.toString()) == annotation
```

Thậm chí một annotation object không thể được tạo bằng constructor thông thường, nên việc muốn tái tạo metadata phải quyết định biểu diễn thành một **kiểu dữ liệu riêng** hay tái tạo khai báo annotation trong bytecode/source, hai bài toán hoàn toàn khác nhau.

### 5.3. Định dạng có thể thay đổi mà nghiệp vụ không thay đổi

Hai annotation object có cùng giá trị logic có thể được biểu diễn bằng các chuỗi khác nhau bởi implementation khác nhau. Định dạng của chuỗi không được API bảo đảm ổn định qua thay đổi phiên bản JDK, runtime hoặc proxy implementation.

Vì vậy, **không nên** dùng `annotation.toString()` để:

- Tạo cache key bền vững hoặc fingerprint của cấu hình.
- Kiểm tra equality của annotation trong nghiệp vụ.
- Lưu dữ liệu làm chứng cứ duy nhất có thể tái dựng chính xác sau nhiều năm.
- Ký số, checksum hoặc tạo hash để trao đổi liên hệ thống.
- Dùng làm cấu trúc phân quyền, chính sách bảo mật, audit record chuẩn hóa.
- Đối chiếu thay đổi cấu hình bằng so sánh chuỗi từng ký tự.

Có thể **ghi vào log để chẩn đoán**, nhưng khi dùng cho audit hoặc truy vết cần truy vấn lâu dài, nên lưu thêm các trường định danh và giá trị đã được cấu trúc hóa.

### 5.4. Các loại giá trị của annotation có thể phức tạp

Phần tử annotation có thể có kiểu:

- Primitive hoặc `String`.
- `Class` (ví dụ `String.class`), cần quy ước cách ghi tên kiểu.
- Enum, cần quy ước tên loại enum và tên hằng.
- Một annotation khác, tức annotation lồng nhau.
- Mảng một chiều của các kiểu hợp lệ bên trên.

Nếu tự parse một chuỗi debug, người viết phải tự giải quyết cả escape, recursion, array boundaries, ký tự Unicode, tính tương thích của class name, default values và versioning. Đây là trách nhiệm của một serialization format thực sự, **không phải của `toString()`**.

## 6. Cách lưu trữ phù hợp: định nghĩa schema rõ ràng

Muốn lưu annotation metadata, bước đầu tiên là **đọc từng phần tử bằng accessor có kiểu**, sau đó ánh xạ vào một DTO/record/schema do ứng dụng quản lý.

Với `JobInfo` trong ví dụ mục 4, một JSON document **minh họa cấu trúc có kiểm soát** là:

```json
{
  "schemaVersion": 1,
  "annotationType": "JobInfo",
  "id": "batch=alpha, beta",
  "mode": "FAST",
  "labels": ["night", "etl"]
}
```

Đây không phải kết quả của `JobInfo.toString()`. Đây là **ví dụ một schema do ứng dụng chọn**, trong đó:

- `schemaVersion` giúp bộ đọc biết cách diễn giải và nâng cấp dữ liệu.
- `annotationType` chứa tên định danh theo quy ước; ví dụ dùng annotation ở default package nên tên là `JobInfo`. Trong ứng dụng thực tế nên quy định tên logic hoặc tên type rõ ràng.
- `id` là string nguyên vẹn; dấu bằng và dấu phẩy thuộc giá trị.
- `mode` là một enum được chuyển thành tên hằng `FAST`, không dựa vào `toString()` của toàn annotation.
- `labels` là mảng JSON, giữ nguyên ranh giới giữa các giá trị.

**Quan trọng:** JSON cũng cần được tạo và đọc bằng **thư viện serialization** hoặc implementation được kiểm thử, có xử lý escaping và validation. Không nên tự nối chuỗi kiểu `"{\"id\":\"" + id + "\"}"` cho dữ liệu thực tế vì dấu ngoặc kép, backslash và ký tự điều khiển dễ làm hỏng JSON.

### 6.1. Các quy tắc cần chốt khi xây serializer

1. **Tên trường và kiểu trường:** ví dụ `schemaVersion` là số nguyên, `labels` là mảng string, `mode` là tên enum.
2. **Tính bắt buộc và default:** lưu tất cả giá trị hiệu lực, hoặc lưu sự vắng mặt với ý nghĩa được schema định nghĩa. Không tùy tiện phụ thuộc việc `toString()` hiện hay bỏ default.
3. **Thứ tự:** nếu cần canonical representation hoặc chữ ký số, chuẩn hóa thứ tự field và mọi cấu trúc mà thứ tự có ý nghĩa; serializer mặc định không tự bảo đảm canonical JSON.
4. **Kiểu lồng nhau:** định nghĩa cấu trúc đệ quy cho annotation-valued elements và các mảng; không cắt nested annotation bằng dấu phẩy.
5. **Class và enum:** quy định cách serialize `Class<?>`, nested class, module/package, enum type và enum constant; xác định trường hợp rename/missing type.
6. **Phiên bản và migration:** dữ liệu lưu lâu có thể cần đọc bằng phiên bản ứng dụng khác, kể cả sau khi annotation thêm phần tử hoặc đổi default.
7. **Kiểm thử round-trip:** tạo bộ kiểm thử gồm string có dấu phẩy, dấu bằng, dấu ngoặc kép, xuống dòng, Unicode, array rỗng, nested values và default values.
8. **An toàn dữ liệu:** kiểm tra dữ liệu khi deserialize; không nạp class hoặc chạy logic từ type name tùy ý nhận qua API mà không có chính sách cho phép.

### 6.2. Đừng thay toString bằng một toString khác

Bản `record JobSnapshot` trong ví dụ giúp **tách dữ liệu có cấu trúc ra khỏi annotation proxy**. Nhưng `JobSnapshot.toString()` do Java tự sinh cũng chỉ là cách trình bày object, **không nên dùng làm định dạng lưu trữ**.

Trình tự đúng là:

```text
Runtime annotation
    |
    | đọc phần tử: id(), mode(), labels(), annotationType()
    v
DTO / record / schema có kiểm tra dữ liệu
    |
    | serializer có hợp đồng phiên bản và escaping
    v
JSON / CBOR / Protobuf / định dạng lưu trữ được lựa chọn
```

Không nên tự xây một parser riêng chỉ vì `toString()` của một bản JDK trông giống JSON hoặc giống annotation syntax.

## 7. equals() và hashCode(): có thay thế định dạng lưu trữ được không?

**Không.** Nhưng chúng khác `toString()` ở chỗ **có hợp đồng so sánh logic được đặc tả**.

Với annotation của Java:

- `equals` trả `true` nếu hai annotation cùng annotation type và các phần tử tương ứng có giá trị bằng nhau theo quy tắc type; mảng so sánh **theo từng phần tử**, không so sánh identity của array.
- `hashCode` được định nghĩa từ tên và giá trị của mọi phần tử, kể cả default values. Nó được thiết kế để nhất quán với `equals`.
- `toString` trả văn bản phục vụ biểu diễn, **chi tiết không được cố định**.

Do đó:

```java
// Trong ngữ cảnh đã khai báo JobOne, JobTwo và JobInfo:
JobInfo a = JobOne.class.getAnnotation(JobInfo.class);
JobInfo b = JobTwo.class.getAnnotation(JobInfo.class);

boolean same = a.equals(b); // true: cùng type và cùng các element values
```

So sánh trực tiếp `a.toString().equals(b.toString())` không phải thay thế đúng cho hợp đồng equality. Dù một JVM cụ thể có thể cho hai chuỗi giống nhau, điều đó không tạo thành cam kết dùng để kiểm tra logic.

Tương tự, **hash code không phải định danh duy nhất**: hai giá trị khác nhau có thể trùng hash do miền giá trị `int` hữu hạn. `hashCode` không phải checksum mật mã, không đủ để xác thực dữ liệu, và không phải cơ chế serialization.

## 8. Ứng dụng thực tế: log, cấu hình và đối chiếu

### 8.1. Log nội bộ

Dùng `annotation.toString()` để đọc nhanh:

```java
logger.debug("Annotation metadata: {}", annotation);
```

Đây là ví dụ với một logging framework hỗ trợ cú pháp placeholder; **không phải code Java SE độc lập**. Nội dung log có thể khác nhau giữa môi trường, nên không nên viết parser vận hành quan trọng dựa vào chi tiết text từ `toString()`.

Nếu cần tìm kiếm có cấu trúc, nên log rõ `annotationType`, `id`, `mode` và các field quan trọng, theo API logging đang sử dụng.

### 8.2. Lưu cấu hình

Nếu một công cụ phát hành phiên bản cấu hình, hãy đọc annotation, chuyển thành DTO, validate, serialize theo schema. Khi đọc từ kho lưu trữ, tái tạo **DTO cấu hình**, không giả định tạo lại đối tượng annotation gốc từ `toString()`.

Nếu code nghiệp vụ chỉ cần các giá trị `id`, `mode`, `labels`, làm việc với DTO có thể ít phụ thuộc Java reflection hơn so với cố dựng runtime proxy annotation.

### 8.3. Cache và tính ổn định

Cache trong một tiến trình có thể dùng object hoặc khóa miền nghiệp vụ được thiết kế, nhưng nếu khóa cần tồn tại sau nâng cấp runtime, cần **canonical structured encoding** hoặc một khóa có schema độc lập. Không dùng chuỗi `toString()` làm khóa bền vững.

Nếu dữ liệu cần ký số hoặc đối chiếu byte-for-byte giữa hệ thống, phải quy định encoding, thứ tự field, normalization, phiên bản và thuật toán ký; Java `Annotation.toString()` không cam kết những điều này.

## 9. Các lỗi và hiểu lầm phổ biến

**Lỗi 1 — Xem output của một JDK là đặc tả chuẩn.** Hình thức của `toString()` là implementation-dependent. Quan sát được dấu ngoặc, dấu phẩy hay thứ tự field ở một nơi không có nghĩa API bắt buộc mọi implementation phải dùng.

**Lỗi 2 — Parse bằng split(",") hoặc split("=" ).** Dấu phân cách có thể nằm ngay trong string value hoặc nested annotation/array. Đọc accessor thay vì phân tích string debug.

**Lỗi 3 — Nghĩ mọi annotation trong source đều có toString runtime.** Annotation SOURCE hoặc CLASS retention không được reflection trả về theo cách của RUNTIME.

**Lỗi 4 — Gọi getClass() và lưu tên proxy implementation.** Dùng `annotationType()` để xác định annotation interface; `getClass()` là chi tiết implementation.

**Lỗi 5 — Đối chiếu annotation theo toString.** Dùng `equals` cho so sánh logic; dùng schema canonical riêng cho so sánh liên hệ thống.

**Lỗi 6 — Coi hashCode là UUID hoặc hash mật mã.** `hashCode` không duy nhất và không phục vụ bảo mật hoặc lưu trữ bền vững.

**Lỗi 7 — Cho rằng @Retention(RUNTIME) tự cung cấp serializer.** Retention cho phép reflection đọc metadata ở vị trí phù hợp, nhưng không định nghĩa JSON schema, decoder hay migration.

**Lỗi 8 — Lưu record.toString() thay vì annotation.toString().** Vấn đề không mất đi: string biểu diễn object không tự trở thành wire format bền vững.

**Lỗi 9 — Bỏ qua array và nested annotation.** Cần mô hình rõ ràng cho mảng, annotation lồng nhau, enum, class literal, ký tự đặc biệt và giá trị mặc định.

**Lỗi 10 — Tin Java tự giữ nguyên thứ tự viết trong source khi render.** Thứ tự cặp phần tử trong `toString()` không phải định dạng canonical được API hứa hẹn.

**Lỗi 11 — Lưu chỉ chuỗi toString mà không có version.** Khi schema annotation thay đổi, dữ liệu cũ sẽ khó hoặc không thể diễn giải đáng tin. Hãy định nghĩa version và quy tắc migration.

**Lỗi 12 — Đưa toString vào chữ ký số.** Không có canonical encoding bảo đảm; ngay cả thay đổi không liên quan đến metadata logic cũng có thể làm chuỗi khác và phá kiểm tra chữ ký.

## 10. Bài tập tự kiểm tra

1. Chạy `AnnotationToStringDemo.java`. Thêm `System.out.println(first.toString())` trong `main`, sau đó ghi nhận hình thức thực tế trên JDK của bạn. **Không** sửa test để phụ thuộc chuỗi đó.
2. Đổi giá trị `id` thành một chuỗi chứa dấu bằng, dấu phẩy, dấu ngoặc kép và ký tự xuống dòng. Chứng minh vì sao `split(",")` không thể được xem là parser an toàn.
3. Thêm phần tử `int retries() default 3;` vào `JobInfo`. Cập nhật `JobSnapshot` và JSON schema một cách chủ động; giải thích vì sao không nên phụ thuộc việc `toString()` có in default mới hay không.
4. Thêm một annotation lồng nhau `@Policy(level = 2)` làm phần tử trong `JobInfo`. Đề xuất JSON object lồng nhau với field type rõ ràng thay vì phân tích dấu ngoặc trong `toString()`.
5. Thay đổi `JobOne` để có label khác `JobTwo`; dự đoán kết quả `equals` và trình bày vì sao `hashCode` vẫn không trở thành ID duy nhất.
6. Viết test cho serializer của `JobSnapshot`: serialize rồi deserialize và so sánh từng field. Đảm bảo labels giữ đúng số phần tử và thứ tự.
7. Giả sử đổi tên enum `FAST` thành `QUICK`. Thiết kế một migration từ `schemaVersion=1` sang phiên bản kế tiếp để dữ liệu cũ vẫn đọc được.
8. Phân loại các nhu cầu “in log để debug”, “tìm trong database”, “ký cấu hình”, “hiển thị nhanh trên console”. Nêu trường hợp nào có thể dùng `toString()` và trường hợp nào cần schema có cấu trúc.

## 11. Tài liệu tham khảo chuẩn

- [Annotation interface — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): hợp đồng `annotationType()`, `equals()`, `hashCode()` và giới hạn **implementation-dependent** của `toString()`.
- [RetentionPolicy — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): ý nghĩa SOURCE, CLASS, RUNTIME.
- [AnnotatedElement — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): cách đọc runtime annotations ở các phần tử hỗ trợ.
- [Java Language Specification §9.6 — Annotation Interfaces (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): quy tắc khai báo annotation và kiểu giá trị phần tử.

**Kết luận:** `Annotation.toString()` hữu ích để **hiển thị và debug**, nhưng không phải một serialization format chuẩn. Đừng parse, ký số hay persist chuỗi đó như hợp đồng dữ liệu. Muốn lưu trữ đáng tin, hãy **đọc các accessor có kiểu của annotation, chuyển sang DTO/schema có phiên bản, serialize bằng định dạng được đặc tả và kiểm thử round-trip**.
