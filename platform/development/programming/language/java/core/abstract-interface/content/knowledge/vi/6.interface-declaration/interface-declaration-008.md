# Phân biệt interface thông thường với annotation interface trong Java

## 1. Hai kiểu interface, hai mục đích

`interface` thông thường công bố **hợp đồng hành vi**. Class có thể `implements` nó, biến có thể giữ tham chiếu đến đối tượng triển khai, và chương trình gọi method qua kiểu interface.

`@interface` là cú pháp khai báo một **annotation type** (annotation interface). Nó định nghĩa metadata có cấu trúc để gắn vào class, method, field hoặc vị trí khác; compiler, annotation processor, framework hay code Reflection có thể đọc metadata đó. `@interface` không phải dấu `@` gắn trước một interface đã tồn tại.

| Tiêu chí | Interface thông thường | Annotation interface |
| --- | --- | --- |
| Khai báo | `interface Exporter { ... }` | `@interface ExportInfo { ... }` |
| Mục đích | Hợp đồng hành vi và đa hình | Khuôn mẫu metadata |
| Thành viên chính | Abstract, default, static, private methods; constants | Elements không tham số, có thể có giá trị mặc định |
| Sử dụng | `class C implements Exporter` | `@ExportInfo(owner = "Team")` |
| Cách đọc | Gọi method trên đối tượng | Đọc metadata bằng Reflection hoặc công cụ biên dịch |
| Quan hệ kiểu | Có thể `extends` và được class `implements` | Không khai báo `extends` tùy ý; quan hệ với `java.lang.annotation.Annotation` được quy định bởi Java |

## 2. Annotation elements không phải method thông thường

Ví dụ khai báo annotation:

```java
@interface JobInfo {
    String owner();
    int priority() default 3;
    String[] tags() default {};
}
```

`owner`, `priority` và `tags` là **annotation elements**. Chúng không nhận tham số, không có thân method và kiểu trả về bị giới hạn. Các kiểu hợp lệ gồm primitive, `String`, `Class`, enum, annotation type và mảng một chiều của những kiểu đó. `void`, `Object`, `List<String>`, mảng nhiều chiều và element có tham số đều không hợp lệ.

Element không có giá trị mặc định là bắt buộc khi sử dụng annotation. Element có `default` có thể được bỏ qua. Từ khóa `default` ở đây cung cấp **giá trị metadata mặc định**, không phải code của default method.

```java
@JobInfo(owner = "Team A", tags = {"batch", "demo"})
final class ImportJob {}
```

`priority` nhận giá trị 3 vì annotation không cung cấp giá trị khác. Nếu annotation chỉ có element tên `value`, có thể dùng cú pháp rút gọn như `@Role("admin")` thay cho `@Role(value = "admin")`.

## 3. Target và retention

Hai meta-annotation thường gặp:

- `@Target` quy định những vị trí mà annotation được phép gắn, chẳng hạn `TYPE` cho khai báo kiểu hoặc `METHOD` cho phương thức.
- `@Retention` quy định annotation được giữ đến giai đoạn nào: `SOURCE` chỉ phục vụ mã nguồn/biên dịch; `CLASS` được lưu trong class file; `RUNTIME` cho phép Reflection đọc lúc chạy.

Nếu không khai báo `@Retention`, mặc định là `CLASS`. Muốn đọc annotation lúc runtime, hãy khai báo `@Retention(RetentionPolicy.RUNTIME)`. Annotation có retention SOURCE vẫn có thể được annotation processor đọc trong bước biên dịch.

Các meta-annotation khác gồm `@Documented`, `@Inherited` và `@Repeatable`. `@Inherited` áp dụng cho truy vấn annotation trên superclass theo quy tắc Java; nó không tự truyền annotation qua interface hay method override.

## 4. Ví dụ Java 17: hành vi và metadata cùng tồn tại

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

interface Executable {
    void execute();

    default String category() {
        return "task";
    }
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobInfo {
    String owner();
    int priority() default 3;
}

@JobInfo(owner = "Team A")
final class ImportJob implements Executable {
    @Override
    public void execute() {
        System.out.println("importing");
    }
}

public class Main {
    public static void main(String[] args) {
        Executable job = new ImportJob();
        job.execute();
        JobInfo info = ImportJob.class.getAnnotation(JobInfo.class);
        System.out.println(info.owner());
        System.out.println(info.priority());
        System.out.println(Executable.class.isAnnotation());
        System.out.println(JobInfo.class.isAnnotation());
    }
}
```

Kết quả:

```text
importing
Team A
3
false
true
```

`ImportJob implements Executable` tạo quan hệ hợp đồng hành vi. `@JobInfo(owner = "Team A")` gắn metadata lên class; nó không tự thêm method `execute`, không làm class implements annotation và không tự thực hiện hành vi nghiệp vụ. Annotation có tác dụng gì phụ thuộc vào compiler, processor, framework hoặc code đọc nó.

## 5. Lỗi thường gặp

- Dùng `@interface` khi muốn mọi implementation cung cấp một method: dùng interface thông thường.
- Khai báo element kiểu `List<String>` hoặc có tham số: annotation elements bị giới hạn kiểu và phải không có tham số.
- Bỏ qua element bắt buộc: cung cấp giá trị khi gắn annotation hoặc đặt default phù hợp.
- Mong annotation tự bảo vệ, validate hay khởi tạo service: cần code hoặc framework chủ động xử lý metadata.
- Quên `RUNTIME` rồi mong `getAnnotation` đọc được metadata: retention mặc định là CLASS.
- Nhầm `@Deprecated interface OldApi` (interface thường được gắn annotation) với `@interface Marker` (khai báo annotation type).

**Tự kiểm tra:** Nếu một class được gắn `@RequiresPermission("write")`, việc đó tự động chặn người dùng không có quyền gọi method không? Không; annotation chỉ cung cấp metadata. Cần cơ chế kiểm tra thực sự để thực thi chính sách.