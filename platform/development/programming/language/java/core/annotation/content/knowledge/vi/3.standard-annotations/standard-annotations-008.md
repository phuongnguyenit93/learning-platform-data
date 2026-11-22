# `javax.annotation.processing.Generated`: nhận diện mã được sinh trong Java

Khi một công cụ sinh mã (*code generator*) tạo class, phương thức hoặc trường từ schema, cấu hình hay một mô hình khác, người đọc mã nguồn cần biết phần nào do công cụ tạo và phần nào do lập trình viên viết. Java cung cấp annotation chuẩn **`javax.annotation.processing.Generated`** để đánh dấu các khai báo có nguồn gốc từ quá trình sinh mã.

Annotation này xuất hiện từ Java 9, thuộc **module `java.compiler`** của JDK và có thể dùng trong Java 17/21 mà không cần thư viện bên thứ ba khi biên dịch ứng dụng thông thường. Nó mang metadata về **tên công cụ sinh mã**, ngày sinh mã và ghi chú, nhưng **không tự sinh mã, không khóa sửa file, không thay đổi hành vi chương trình**.

## 1. `@Generated` dùng để làm gì?

Giả sử một ứng dụng tạo class Java từ định nghĩa dữ liệu hoặc API specification. Nếu mở file kết quả, ta có thể thấy:

```java
import javax.annotation.processing.Generated;

@Generated("com.example.codegen.CustomerGenerator")
public final class CustomerDto {
    private final long id;

    public CustomerDto(long id) {
        this.id = id;
    }

    public long id() {
        return id;
    }
}
```

Dòng `@Generated("com.example.codegen.CustomerGenerator")` có nghĩa: **theo metadata do nơi tạo file cung cấp**, class `CustomerDto` là mã được sinh bởi công cụ mang tên `com.example.codegen.CustomerGenerator`. Giá trị này là chuỗi định danh; compiler không kiểm tra công cụ ấy có thực sự tồn tại hoặc đã chạy hay chưa.

Dấu đánh dấu hỗ trợ việc đọc và bảo trì dự án:

- Nhận ra vùng mã thường được tạo lại từ nguồn đầu vào, thay vì là nơi nên chỉnh sửa trực tiếp lâu dài.
- Phân biệt khai báo do công cụ tạo với khai báo do lập trình viên viết, kể cả khi chúng ở chung một file.
- Cho phép một số công cụ phân tích mã nguồn hoặc hệ thống sinh tài liệu nhận biết nguồn gốc mã, **nếu công cụ đó được lập trình hỗ trợ annotation này**.
- Cung cấp thông tin truy vết công cụ sinh mã khi nhiều generator cùng tham gia dự án.

**Điều cần phân biệt:** `@Generated` chỉ là nhãn metadata. Việc một IDE hiển thị nhãn, linter bỏ qua mã, công cụ coverage loại trừ hay build task tái sinh file đều phụ thuộc cấu hình và khả năng của từng công cụ. Java không áp dụng những chính sách ấy tự động.

## 2. Import đúng kiểu chuẩn

Dùng đúng tên đầy đủ:

```java
import javax.annotation.processing.Generated;
```

Ví dụ đơn giản:

```java
@Generated("com.example.codegen.EntityGenerator")
class GeneratedEntity {
}
```

Từ Java 9, `javax.annotation.processing.Generated` nằm trong module JDK **`java.compiler`**, thuộc package `javax.annotation.processing`. Dù tên package bắt đầu bằng `javax`, đây là API chuẩn vẫn tồn tại trong các JDK hiện đại như Java 17 và 21.

Không nhầm với:

| Tên | Phân biệt |
| --- | --- |
| `javax.annotation.processing.Generated` | API chuẩn từ Java 9, module `java.compiler`; là đối tượng của bài học này. |
| `javax.annotation.Generated` | Annotation lịch sử trong các API Java EE/JSR-250; không cùng package và không thể giả định luôn có trong JDK hiện đại. |
| `jakarta.annotation.Generated` | Annotation thuộc Jakarta Annotations, cần thư viện Jakarta tương ứng nếu dự án dùng nó. |
| `javax.annotation.processing.Processor` | Giao diện dùng để **viết annotation processor**; không phải annotation đánh dấu mã đã được tạo. |

Khi đọc tài liệu hoặc mã được sinh, hãy xác định import thực tế. Hai annotation có cùng tên ngắn `Generated` nhưng khác package không phải là một kiểu Java.

Nếu ứng dụng dùng Java Platform Module System với một module *có tên* và muốn sử dụng kiểu trong `java.compiler`, có thể khai báo phụ thuộc trong `module-info.java`:

```java
module example.generated.app {
    requires java.compiler;
}
```

Với chương trình đơn giản biên dịch theo classpath bằng JDK, không cần tự tạo `module-info.java`.

## 3. Cú pháp và ba element của `@Generated`

Annotation có ba element:

| Element | Kiểu | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| `value()` | `String[]` | **Có** | Tên công cụ sinh mã, được quy ước là tên đầy đủ của generator. |
| `date()` | `String` | Không, mặc định `""` | Ngày/giờ nguồn được sinh, theo quy ước ISO 8601. |
| `comments()` | `String` | Không, mặc định `""` | Ghi chú bổ sung do công cụ sinh mã cung cấp. |

Cách dùng ngắn nhất:

```java
@Generated("com.example.codegen.DtoGenerator")
class OrderDto {
}
```

Mặc dù `value()` có kiểu `String[]`, Java cho phép truyền **một** giá trị `String` mà không cần dấu `{}`. Ví dụ trên tương đương:

```java
@Generated(value = {"com.example.codegen.DtoGenerator"})
class OrderDto {
}
```

Khi dùng nhiều element, viết các cặp tên–giá trị tường minh:

```java
@Generated(
    value = "com.example.codegen.DtoGenerator",
    date = "2026-01-15T09:30:00+07:00",
    comments = "Sinh từ lược đồ customer-v2"
)
class CustomerSchemaDto {
}
```

Nếu nhiều generator cùng được ghi nhận, `value` nhận nhiều chuỗi:

```java
@Generated(value = {
    "com.example.codegen.ModelGenerator",
    "com.example.codegen.MapperGenerator"
})
class SharedGeneratedType {
}
```

Việc có nhiều tên trong `value` không có nghĩa compiler tự thực thi các generator ấy. Đây chỉ là chuỗi do bên tạo mã cung cấp.

Với `date`, Javadoc của Java yêu cầu giá trị theo chuẩn **ISO 8601**. Dùng giá trị chính xác nếu generator thực sự có thời điểm sinh; có thể bỏ hẳn element khi không cần. Vì `date` chỉ có kiểu `String`, đừng hiểu `@Generated` là hệ thống tự cấp hoặc tự kiểm chứng timestamp.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy

Ví dụ sau minh họa việc một generator **có thể phát ra** mã Java mang `@Generated`. Để học cú pháp, ta viết tay phần mã mẫu; bản thân chương trình không triển khai generator.

Tạo đúng một file **`GeneratedMarkerDemo.java`**:

```java
import javax.annotation.processing.Generated;

@Generated(
    value = "com.example.codegen.CustomerGenerator",
    comments = "Example source generated from a model"
)
final class GeneratedCustomer {
    private final long id;

    GeneratedCustomer(long id) {
        this.id = id;
    }

    @Generated("com.example.codegen.CustomerGenerator")
    String label() {
        return "Customer#" + id;
    }
}

public class GeneratedMarkerDemo {
    public static void main(String[] args) {
        GeneratedCustomer customer = new GeneratedCustomer(42);

        System.out.println(customer.label());
        System.out.println(
            GeneratedCustomer.class.isAnnotationPresent(Generated.class)
        );
    }
}
```

Mở terminal tại thư mục chứa file và chạy bằng Java 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 GeneratedMarkerDemo.java
java GeneratedMarkerDemo
```

**Kết quả `stdout`:**

```text
Customer#42
false
```

Vì sao dòng thứ hai là `false`?

1. `@Generated` xuất hiện trong **mã nguồn** của `GeneratedCustomer` và phương thức `label`.
2. Annotation chuẩn này có `@Retention(RetentionPolicy.SOURCE)`: thông tin được bỏ đi khi compiler tạo class file.
3. `Class.isAnnotationPresent(Generated.class)` kiểm tra annotation có sẵn cho reflection **ở runtime**. Vì `@Generated` không được giữ đến runtime, kết quả là `false`.

Dòng `Customer#42` vẫn in bình thường. Marker không ngăn constructor, phương thức hay logic Java vận hành.

Lưu ý: lệnh `javac` ở đây biên dịch file đã có; không hề gọi `CustomerGenerator`. Tên trong `value` có thể là một chuỗi bất kỳ, nhưng nên ghi chính xác tên generator thực tế để metadata có ích.

## 5. `@Target` và `@Retention`: đánh dấu ở đâu, tồn tại đến lúc nào?

Trong Java 21, khai báo chuẩn của `Generated` có các meta-annotation tương đương:

```java
@java.lang.annotation.Documented
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.SOURCE
)
@java.lang.annotation.Target({
    java.lang.annotation.ElementType.PACKAGE,
    java.lang.annotation.ElementType.TYPE,
    java.lang.annotation.ElementType.METHOD,
    java.lang.annotation.ElementType.CONSTRUCTOR,
    java.lang.annotation.ElementType.FIELD,
    java.lang.annotation.ElementType.LOCAL_VARIABLE,
    java.lang.annotation.ElementType.PARAMETER
})
```

Đây là **đoạn trích minh họa metadata** của annotation chuẩn, không phải toàn bộ mã khai báo lại `@Generated`.

Một số ví dụ dùng trên các vị trí hợp lệ (minh họa riêng, không cần `main`):

```java
import javax.annotation.processing.Generated;

@Generated("com.example.codegen.TypeGenerator")
class GeneratedService {
    @Generated("com.example.codegen.FieldGenerator")
    private String name;

    @Generated("com.example.codegen.ConstructorGenerator")
    GeneratedService(String name) {
        this.name = name;
    }

    @Generated("com.example.codegen.MethodGenerator")
    String getName(
        @Generated("com.example.codegen.ParameterGenerator")
        String prefix
    ) {
        @Generated("com.example.codegen.LocalGenerator")
        String result = prefix + name;
        return result;
    }
}
```

`@Target` còn cho phép đánh dấu package, chẳng hạn trong file `package-info.java`. Tùy cấu trúc mã, không cần gắn annotation lên mọi thành phần con: hãy đánh dấu ở mức đủ rõ để giải thích phần code do generator sở hữu.

**Điểm quan trọng về retention:** `RetentionPolicy.SOURCE` khác `CLASS` và `RUNTIME`. Sau khi biên dịch, annotation này **không nằm trong metadata annotation của `.class`**. Do đó:

- Reflection runtime không thể lấy `@Generated` từ class, method hoặc field.
- Thư viện chỉ phân tích bytecode sau biên dịch không thể dựa riêng vào sự tồn tại của `javax.annotation.processing.Generated` trong class file.
- Công cụ phân tích **mã nguồn** hoặc annotation processor đọc nguồn trong quá trình biên dịch có thể xử lý dấu đánh dấu nếu được cấu hình và hỗ trợ.
- `@Documented` chỉ biểu thị annotation phù hợp để đưa vào tài liệu API khi công cụ tài liệu xử lý nó; không làm thay đổi `SOURCE` thành `RUNTIME`.

Đừng viết một `if` kiểm tra `@Generated` qua reflection rồi kỳ vọng phát hiện file sinh mã. Nếu cần dấu hiệu runtime, phải thiết kế metadata khác có retention `RUNTIME` phù hợp.

## 6. Khi nào generator nên gắn `@Generated`?

Một luồng sinh mã thường có dạng:

```text
Schema / cấu hình / mô hình API
            |
            v
   Code generator đọc đầu vào
            |
            v
Sinh file .java với @Generated(...)
            |
            v
       javac biên dịch
            |
            v
        File .class
```

Ví dụ một generator nhận mô hình `Customer` rồi viết ra `CustomerDto.java`. Generator nên tạo cả dòng:

```java
@Generated(
    value = "com.example.codegen.CustomerGenerator",
    comments = "Input: customer-schema"
)
```

trước khai báo class, để người đọc biết nơi phát sinh mã. Mối liên hệ này **do generator quyết định**: `javac` không tự thêm annotation cho mọi đoạn mã được công cụ tạo ra.

Một số tình huống phù hợp gồm class DTO tạo từ schema, proxy hoặc adapter do build tool phát ra, source client được tạo từ OpenAPI, mapper hoặc code hỗ trợ sinh bởi annotation processor. Tuy nhiên, mỗi công cụ có chính sách riêng; không nên khẳng định tất cả sẽ gắn annotation này.

Khi chỉ **một vài khai báo** trong file được sinh, đánh dấu đúng khai báo đó có thể giúp phân biệt với phần viết tay. Thực tế nhiều dự án tổ chức mã nguồn sinh tự động trong thư mục riêng, nhưng `@Generated` vẫn giúp nhận biết rõ xuất xứ ở cấp mã.

## 7. Tránh hiểu sai về build, kiểm thử và độ bao phủ

`@Generated` mang thông tin nguồn gốc; Java không gán cho nó ý nghĩa quản trị tự động.

| Kỳ vọng sai | Thực tế |
| --- | --- |
| Thêm `@Generated` thì Java tự sinh DTO hoặc client | Annotation không chứa bộ sinh mã; cần generator hoặc annotation processor riêng. |
| `@Generated` khiến class không thể chỉnh sửa | File vẫn có thể được chỉnh sửa; generator có thể ghi đè file nếu được chạy lại. |
| `@Generated` khiến compiler bỏ qua kiểm tra lỗi | Mã Java được sinh vẫn phải biên dịch hợp lệ như mã thông thường. |
| `@Generated` tự loại mã khỏi unit test hoặc coverage | Phụ thuộc công cụ và cấu hình; `SOURCE` không tồn tại trong bytecode để công cụ hậu biên dịch trực tiếp đọc annotation đó. |
| Dùng reflection để tìm class có `@Generated` | Không được: annotation này có retention `SOURCE`. |
| Có annotation tức là mã chắc chắn được công cụ sinh | Java không xác minh tính xác thực của metadata này. |
| Gắn tên generator thì Java tự kiểm tra class generator tồn tại | `value` là chuỗi `String[]`, không phải tham chiếu `Class<?>`. |

Ví dụ, nếu muốn báo cáo coverage bỏ qua mã sinh, hãy đọc hướng dẫn cụ thể của công cụ coverage hoặc cấu hình nguồn sinh. Không dựa vào riêng marker `@Generated` để khẳng định coverage sẽ thay đổi. Với công cụ chỉ nhìn class file, cần đặc biệt nhớ giới hạn `SOURCE`.

## 8. Lưu ý khi tạo mã ổn định và dễ bảo trì

- **Ưu tiên tên generator đầy đủ** trong `value`, ví dụ `"com.example.codegen.DtoGenerator"`, thay vì chuỗi mơ hồ như `"tool"`; đây cũng là quy ước Javadoc nêu.
- **Cân nhắc `date`:** nếu mỗi lần generate đều ghi timestamp mới dù mã không đổi, Git diff có thể nhiễu. `date` có giá trị mặc định `""`; bỏ qua khi không có nhu cầu truy vết thời điểm.
- **Ghi `comments` có ích và không nhạy cảm**, ví dụ tên schema hoặc phiên bản template, thay vì chèn secret, token hay thông tin nội bộ không cần thiết.
- **Sửa nguồn sinh hoặc template khi muốn thay đổi lâu dài.** Một file được tạo lại từ đầu có thể xóa mất chỉnh sửa tay trong file output.
- **Đánh dấu đúng phạm vi mã sinh.** Có thể gắn lên class hoặc một phương thức riêng; tránh gắn nhầm lên phần do lập trình viên chủ động duy trì.
- **Giữ mã nguồn sinh có thể biên dịch độc lập theo yêu cầu dự án.** `@Generated` không làm cho import sai hay method sai chữ ký trở nên hợp lệ.

Nếu generator được viết dưới dạng annotation processor, các API như `javax.annotation.processing.Processor`, `ProcessingEnvironment` và `Filer` giúp đọc đầu vào rồi tạo source file. **Chính code generator** quyết định có viết thêm `@Generated` vào source đầu ra hay không. Việc sử dụng annotation này và việc **xây dựng annotation processor** là hai công việc khác nhau.

## 9. Lỗi cú pháp thường gặp

### Thiếu element `value`

Không hợp lệ:

```java
@Generated(date = "2026-01-15T09:30:00+07:00")
class WrongGeneratedMarker {
}
```

`value` **bắt buộc**, nên phải có ít nhất một tên generator:

```java
@Generated(
    value = "com.example.codegen.DtoGenerator",
    date = "2026-01-15T09:30:00+07:00"
)
class CorrectGeneratedMarker {
}
```

### Nhầm phần tử `comments` thành `comment`

`comments` là tên element đúng, có **s** ở cuối:

```java
@Generated(
    value = "com.example.codegen.DtoGenerator",
    comments = "Generated from a schema"
)
class WithComment {
}
```

Viết `comment = "..."` sẽ bị từ chối vì annotation chuẩn không có element tên `comment`.

### Truyền sai kiểu

`value()` là `String[]`, `date()` và `comments()` là `String`; các đoạn sau sai kiểu:

```java
@Generated(123)                         // Sai: value cần String/String[]
@Generated(value = String.class)        // Sai: không nhận Class
@Generated(value = "Generator", date = 2026) // Sai: date cần String
```

Đây là những dòng minh họa lỗi riêng biệt, không phải chương trình đầy đủ để biên dịch.

### Nhầm package khi chuyển Java phiên bản

Nếu gặp lỗi `package javax.annotation does not exist` do dùng `import javax.annotation.Generated`, trước hết hãy xác định dự án cần **annotation nào**. Với mục đích đánh dấu mã sinh theo JDK Java 17+, đổi đúng import sang `javax.annotation.processing.Generated` khi công cụ/dự án cho phép. Nếu công cụ phát sinh mã yêu cầu một annotation khác, hãy kiểm tra cấu hình hoặc dependency phù hợp; không thay package bừa vì chúng là các kiểu khác nhau.

## 10. Tự kiểm tra

1. `@Generated("com.example.codegen.ApiGenerator")` thiếu dấu `{}` có hợp lệ không? **Có**: một chuỗi được dùng làm phần tử đơn của `String[] value`.
2. Có thể gọi `CustomerDto.class.getAnnotation(Generated.class)` để đọc tên generator ở runtime không? **Không**: retention là `SOURCE`, kết quả không tìm thấy annotation này.
3. `@Generated(value = "Generator", comments = "v1")` có hợp lệ về mặt cú pháp không? **Có**; dù nên dùng tên đầy đủ của generator để metadata rõ nghĩa.
4. `@Generated(comments = "from OpenAPI")` có biên dịch được không? **Không**: thiếu `value`.
5. Có nhất thiết phải sử dụng `date` và `comments`? **Không**: cả hai mặc định chuỗi rỗng.

Tài liệu tham khảo chính thức: [Java SE 21 — `javax.annotation.processing.Generated`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Generated.html). Phần khai báo chuẩn ghi rõ `@Documented`, `@Retention(SOURCE)`, `@Target`, các element và thời điểm API được giới thiệu.
