# Kết hợp nhiều annotation trên một khai báo trong Java

## 1. Ý nghĩa và cú pháp cơ bản

Trong Java, **một khai báo có thể mang nhiều annotation khác loại cùng lúc**. Mỗi annotation bổ sung một thông tin hoặc yêu cầu riêng cho lớp, phương thức, trường, constructor, tham số… mà nó được phép áp dụng. Đây là cách phổ biến để gắn nhiều khía cạnh (ví dụ: mô tả API, phân quyền, kiểm thử, xử lý của framework) lên cùng một thành phần.

Cú pháp là viết lần lượt các annotation ngay trước khai báo. Có thể đặt mỗi annotation trên một dòng hoặc nhiều annotation trên cùng dòng:

```java
@Deprecated
@Override
public String toString() {
    return "example";
}
```

Ở đây cả hai annotation đều gắn lên **phương thức toString()**. **@Override** yêu cầu trình biên dịch kiểm tra phương thức có thực sự override/implement phương thức từ kiểu cha; **@Deprecated** đánh dấu phương thức không còn được khuyến khích sử dụng. Hai annotation có ý nghĩa khác nhau và cùng tồn tại trên một khai báo.

Cú pháp `@A @B` **không có nghĩa** A bọc B hoặc B chạy trước A. Với Java, chúng là các annotation riêng biệt cùng được liên kết với phần tử; hoạt động thực tế còn phụ thuộc trình biên dịch, annotation processor, thư viện hoặc framework đọc chúng.

## 2. Điều kiện để kết hợp hợp lệ

### 2.1. Mỗi annotation phải được phép đặt tại vị trí đó

Annotation tự khai báo có thể dùng meta-annotation **@Target** để xác định vị trí hợp lệ. Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface OnlyMethod {}

@Target({ElementType.METHOD, ElementType.CONSTRUCTOR})
@interface OnCallable {}

class Sample {
    @OnlyMethod
    @OnCallable
    void execute() {}

    @OnCallable
    Sample() {}
}
```

- Cả **@OnlyMethod** và **@OnCallable** đều cho phép METHOD nên đặt đồng thời lên execute() là hợp lệ.
- **@OnCallable** cũng cho phép CONSTRUCTOR nên có thể gắn lên constructor.
- Nếu gắn **@OnlyMethod** lên class, field hoặc constructor thì sẽ có **lỗi biên dịch**, vì vị trí đó không nằm trong @Target.

Một số giá trị thường gặp: **TYPE** (class, interface, enum, annotation type, record), **METHOD**, **FIELD**, **CONSTRUCTOR**, **PARAMETER**, **LOCAL_VARIABLE**, **ANNOTATION_TYPE**, **TYPE_PARAMETER**, **TYPE_USE** và **RECORD_COMPONENT**. Cần phân biệt annotation trên *khai báo* với annotation trên *kiểu được sử dụng*: chẳng hạn annotation cho METHOD chưa chắc dùng được trước một kiểu ở vị trí TYPE_USE.

Nếu một annotation không khai báo @Target, về cơ bản nó dùng được trên các vị trí khai báo được phép của annotation; điều đó không tự động biến nó thành annotation cho mọi vị trí TYPE_USE hoặc type parameter.

### 2.2. Khác loại và cùng loại là hai trường hợp khác nhau

Các annotation **khác loại** thường có thể đặt cạnh nhau, miễn mỗi cái hợp lệ tại phần tử đó:

```java
@Override
@Deprecated
public String toString() {
    return "legacy";
}
```

Trái lại, viết **hai lần cùng một loại** như `@Tag("fast")` và `@Tag("smoke")` trên cùng khai báo chỉ hợp lệ khi loại annotation đó được khai báo **@Repeatable** (xem mục 5). Không được nhầm “nhiều annotation khác loại” với “lặp lại một annotation”.

### 2.3. Annotation mang các mức lưu giữ khác nhau

**@Retention** quyết định thời điểm dữ liệu annotation được giữ lại:

| RetentionPolicy | Ý nghĩa | Đọc qua reflection lúc chạy? |
| --- | --- | --- |
| SOURCE | Dành cho xử lý tại source/compile, không giữ trong class file | Không |
| CLASS | Giữ trong class file, không mặc định cung cấp cho reflection runtime | Không |
| RUNTIME | Giữ trong class file và có thể đọc qua reflection lúc chạy | Có |

Kết hợp nhiều annotation **không làm thay đổi @Retention của từng cái**. Ví dụ, khi đặt **@Override** cùng một annotation tự định nghĩa có RUNTIME trên một phương thức, reflection có thể thấy annotation tự định nghĩa, nhưng không thấy @Override vì @Override chỉ có SOURCE retention.

## 3. Ví dụ Java 17+ hoàn chỉnh: hai annotation trên cùng phương thức

Tạo file **AnnotationCombinationDemo.java** với toàn bộ nội dung sau:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String path();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequireRole {
    String value();
}

public class AnnotationCombinationDemo {
    @Route(path = "/reports")
    @RequireRole("ADMIN")
    public String report() {
        return "Bao cao";
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = AnnotationCombinationDemo.class
                .getDeclaredMethod("report");

        Route route = method.getAnnotation(Route.class);
        RequireRole role = method.getAnnotation(RequireRole.class);

        System.out.println(route.path());
        System.out.println(role.value());
        System.out.println(new AnnotationCombinationDemo().report());
    }
}
```

Chạy tại thư mục chứa file bằng JDK 17 trở lên:

```bash
javac AnnotationCombinationDemo.java
java AnnotationCombinationDemo
```

Kết quả stdout chính xác:

```text
/reports
ADMIN
Bao cao
```

**Phân tích từng bước:**

1. **@Route** mô tả đường dẫn logic cho report(); **@RequireRole** mô tả vai trò được yêu cầu. Hai annotation đều có @Target(METHOD), nên có thể cùng đặt lên report().
2. **@Retention(RUNTIME)** ở mỗi annotation giúp lớp Method đọc được chúng khi chạy.
3. **getDeclaredMethod("report")** tìm đối tượng Method tương ứng; **getAnnotation(Route.class)** và **getAnnotation(RequireRole.class)** đọc hai metadata riêng biệt từ cùng Method.
4. Lệnh gọi trực tiếp **report()** vẫn trả về chuỗi “Bao cao”. Chỉ gắn **@Route** hoặc **@RequireRole** **không tự tạo HTTP endpoint, không tự kiểm tra ADMIN và không tự chặn lời gọi**. Muốn có hành vi đó cần code hoặc framework đọc metadata rồi thực thi quy tắc tương ứng.

Lưu ý: các annotation **Route** và **RequireRole** trong ví dụ là hai kiểu tự định nghĩa của bài học, không phải annotation có sẵn của Spring.

## 4. Kết hợp các annotation có sẵn và annotation của framework

Ví dụ quen thuộc nhất ở Java Core là đặt **@Override** cùng **@Deprecated** trên một phương thức:

```java
class Parent {
    public String name() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    @Deprecated(since = "17")
    public String name() {
        return "child";
    }
}
```

**@Override** được kiểm tra ở bước biên dịch, còn **@Deprecated** đánh dấu API bị deprecated, để các công cụ/trình biên dịch có thể đưa ra cảnh báo khi mã khác sử dụng phương thức. Việc đặt hai annotation không khiến phương thức được gọi hai lần hoặc khiến @Deprecated can thiệp vào cơ chế override.

Trong hệ sinh thái Spring hoặc Jakarta Validation, cũng thường thấy một khai báo có nhiều annotation mang nhiều vai trò. Chẳng hạn một phương thức có thể đồng thời được đánh dấu bằng annotation ánh xạ request và annotation kiểm soát quyền truy cập, **nếu cả hai hợp lệ tại METHOD và các thành phần xử lý tương ứng đã được cấu hình**. Cách các framework tổng hợp điều kiện, chọn proxy, xác định thứ tự interceptor và xử lý xung đột là **quy tắc của framework**, không phải do thứ tự viết annotation trong mã nguồn Java.

## 5. Phân biệt với @Repeatable: lặp cùng một loại annotation

Nếu cần gắn *nhiều giá trị của cùng một kiểu annotation* vào một khai báo, hãy khai báo kiểu đó là **@Repeatable** cùng một annotation container. Ví dụ dưới đây là phần mã minh họa có thể đặt vào một file Java cùng các import thích hợp:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Tags {
    Tag[] value();
}

class TaggedTask {
    @Tag("fast")
    @Tag("smoke")
    void execute() {}
}
```

Ở đây **@Tag("fast")** và **@Tag("smoke")** là **hai lần sử dụng cùng một loại Tag**, được phép bởi **@Repeatable(Tags.class)**. Container **Tags** chứa mảng Tag; container phải đáp ứng các ràng buộc về target và retention tương thích với annotation lặp.

Với **RUNTIME retention**, có thể lấy toàn bộ Tag bằng **method.getAnnotationsByType(Tag.class)**. Khi dùng annotation lặp, nên ưu tiên **getAnnotationsByType** thay vì giả định **getAnnotation(Tag.class)** sẽ luôn trả về các Tag đã lặp: các annotation lặp thường được biểu diễn thông qua container ở dạng khai báo/runtime metadata.

Ngược lại, việc gắn **@Route** và **@RequireRole** trong mục 3 **không đòi hỏi @Repeatable** vì chúng là hai kiểu annotation khác nhau.

## 6. Thứ tự, vị trí và phạm vi tác dụng

- **Thứ tự khai báo:** Viết @Route trước @RequireRole hoặc ngược lại không quy định thứ tự thực thi. Không suy ra thứ tự xử lý từ vị trí xuất hiện trong source hoặc từ thứ tự mà reflection trả về trong mảng annotation.
- **Chính xác một phần tử:** Những annotation viết ngay trước phương thức sẽ gắn vào phương thức đó, không tự lan sang mọi tham số hoặc mọi phương thức của lớp. Muốn chú thích tham số, đặt annotation ở **khai báo tham số**, và kiểu annotation phải cho phép PARAMETER.
- **Tương thích target:** Nếu một annotation chỉ dùng cho TYPE còn annotation khác chỉ cho METHOD, không thể đặt cả hai trên một METHOD rồi mong Java tự áp dụng cái TYPE lên lớp bao quanh.
- **Tương thích framework:** Java có thể cho phép nhiều annotation cùng xuất hiện về cú pháp, nhưng một framework cụ thể có thể bổ sung điều kiện, ưu tiên, thành phần xử lý hoặc báo xung đột. Cần đọc hợp đồng API của annotation được dùng.
- **Retention độc lập:** Một annotation chạy được qua annotation processor tại compile time không nhất thiết còn hiện diện để reflection đọc tại runtime. Phải xem định nghĩa @Retention của từng annotation.
- **Không tự có hành vi:** Annotation là metadata theo cơ chế Java; các tác động như validation, transaction, security, routing hoặc logging cần trình biên dịch, công cụ hay runtime/framework xử lý. Chỉ viết nhiều annotation không tạo ra cơ chế xử lý mới.

Một khai báo có thể mang cả meta-annotation khi chính nó **định nghĩa một annotation**, ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@interface Audited {}
```

Ở đây **@Retention** và **@Target** cùng áp dụng cho khai báo **@interface Audited** để cấu hình *loại annotation*; chúng không có nghĩa mọi phương thức gắn @Audited đều trở thành một phương thức có @Retention hoặc @Target.

## 7. Lỗi thường gặp và cách kiểm tra

**Lỗi 1 — Annotation không đúng @Target.** Một annotation chỉ cho FIELD lại được gắn lên class hoặc method. Trình biên dịch báo annotation không áp dụng được cho phần tử đó. Hãy mở định nghĩa @Target, rồi chuyển annotation đến đúng vị trí hoặc điều chỉnh khai báo annotation nếu chính bạn sở hữu kiểu đó.

**Lỗi 2 — Viết cùng annotation hai lần khi chưa @Repeatable.** Hai dòng @Tag khác giá trị vẫn là cùng loại; sửa bằng @Repeatable và container hợp lệ nếu thực sự cần đa giá trị. Nếu hai khía cạnh độc lập, thường nên dùng hai kiểu annotation có ý nghĩa riêng.

**Lỗi 3 — Mong reflection thấy annotation SOURCE/CLASS.** Cần RUNTIME retention để dùng các API reflection phổ biến như getAnnotation/getAnnotationsByType lúc chạy. Không cố suy từ việc annotation xuất hiện trong mã nguồn rằng reflection chắc chắn đọc được.

**Lỗi 4 — Nghĩ rằng thứ tự dòng quyết định ưu tiên.** @A rồi @B không tương đương “chạy A trước B”; muốn biết thứ tự, phải kiểm tra công cụ/framework đang xử lý annotation và cấu hình liên quan.

**Lỗi 5 — Tưởng mọi annotation cùng METHOD đều tương thích về nghiệp vụ.** Kiểm tra tài liệu của từng annotation, các precondition và cơ chế xử lý. Ví dụ hai cơ chế AOP khác nhau có thể cùng hợp lệ về Java nhưng chịu thứ tự interceptor riêng.

**Lỗi 6 — Lầm annotation với lời gọi hàm.** Ví dụ mục 3 chỉ cho phép code chủ động đọc metadata. Không có router hay lớp bảo mật nào được Java Core tạo tự động.

**Lỗi 7 — Thiếu import hoặc trùng tên annotation.** Hai thư viện có thể cùng định nghĩa tên ngắn như @Transactional. Hãy kiểm tra đúng package được import; nếu cần, dùng tên đầy đủ để tránh nhầm API hay hành vi.

## 8. Bài tập củng cố

1. Thêm annotation tự định nghĩa **@Audit(event = "READ_REPORT")** vào phương thức report() ở mục 3. Đặt **@Target(METHOD)** và **@Retention(RUNTIME)**, rồi dùng reflection in ra event. Kết quả nên có thêm một dòng READ_REPORT mà kết quả của ba dòng hiện có không đổi.
2. Đổi @Target của **@RequireRole** thành **ElementType.TYPE** và thử biên dịch. Giải thích vì sao Java từ chối việc giữ @RequireRole trên report(), rồi thử chuyển nó sang khai báo lớp để quan sát sự khác biệt về vị trí.
3. Với ví dụ @Repeatable, thử đổi thành annotation Tag không có @Repeatable và giữ hai lần @Tag trên execute(). Xác định lỗi biên dịch và lý do Java phân biệt lặp cùng loại với kết hợp các loại annotation khác nhau.

**Điểm cần nắm:** Muốn đặt nhiều annotation lên cùng một khai báo, phải xác định đúng **phần tử được chú thích**, bảo đảm **@Target của từng annotation cho phép phần tử đó**, hiểu **@Retention** của từng loại và đọc tài liệu của cơ chế xử lý chúng. Chỉ khi lặp **cùng một loại** mới cần xét **@Repeatable**.
