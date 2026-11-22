# Annotation đánh dấu, một phần tử và nhiều phần tử

Khi đọc annotation, ta thường gặp ba cách viết:

```java
@Reviewed
@Label("billing")
@Audit(value = "create", priority = 3)
```

Chúng lần lượt biểu diễn một dấu đánh dấu, một giá trị viết ngắn gọn và các cặp tên–giá trị. Để dùng đúng, cần phân biệt **các phần tử được định nghĩa trong kiểu annotation** với **cú pháp sử dụng annotation tại một vị trí cụ thể**.

Một kiểu annotation có nhiều phần tử vẫn có thể dùng dạng một phần tử nếu đáp ứng quy tắc về `value` và giá trị mặc định. Khi mọi phần tử đều có mặc định, nó còn có thể được dùng với cú pháp đánh dấu.

## 1. Bức tranh chung

| Cách viết | Dạng cú pháp | Ý nghĩa |
| --- | --- | --- |
| `@Reviewed` | Đánh dấu (marker annotation) | Không ghi cặp tên–giá trị tại nơi sử dụng |
| `@Label("billing")` | Một phần tử (single-element annotation) | Cung cấp giá trị cho phần tử tên `value` |
| `@Label(value = "billing")` | Dạng đầy đủ (normal annotation) | Cung cấp rõ tên phần tử |
| `@Audit(value = "create", priority = 3)` | Dạng đầy đủ với nhiều phần tử | Cung cấp nhiều cặp tên–giá trị |
| `@Reviewed()` | Dạng đầy đủ với danh sách rỗng | Không ghi giá trị tường minh |

“Annotation nhiều phần tử” thường là cách nói về kiểu annotation có nhiều phần tử, hoặc một lần sử dụng cung cấp nhiều cặp tên–giá trị. Trong cú pháp Java, các cặp có tên nằm trong dạng annotation đầy đủ.

Mỗi phần tử được khai báo giống một phương thức không tham số trong `@interface`, chẳng hạn `String value();`. Dữ liệu đó mô tả chương trình; nó không phải phần thân xử lý chạy khi annotation được gắn.

## 2. Annotation đánh dấu: biểu diễn một đặc tính

Khai báo tối giản:

```java
@interface Reviewed {
}
```

Cách dùng minh họa:

```java
@Reviewed
class Invoice {
}
```

Chỉ sự có mặt của annotation đã cung cấp thông tin: lớp này được gắn nhãn `Reviewed`. Không có dữ liệu bổ sung như người duyệt hoặc thời điểm duyệt.

Mẫu này phù hợp khi thông tin thực sự chỉ là có/không. Tuy nhiên, tên annotation không tự tạo hành vi kiểm tra. Nếu đó là annotation do ứng dụng định nghĩa, phải có công cụ hoặc mã đọc nó để diễn giải nhãn.

Hai cách `@Reviewed` và `@Reviewed()` đều hợp lệ với kiểu không có phần tử như trên. Cách không có ngoặc thường thể hiện ý định đánh dấu gọn hơn.

## 3. Một phần tử: quy tắc đặc biệt của tên value

Khai báo:

```java
@interface Label {
    String value();
}
```

Hai cách sử dụng dưới đây tương đương:

```java
@Label("billing")
class BillingA {
}

@Label(value = "billing")
class BillingB {
}
```

Dạng `@Label("billing")` không phải phép truyền tham số theo vị trí tùy ý. Nó là cú pháp viết tắt dành riêng cho phần tử có tên **`value`**.

Nếu đổi tên phần tử thành `name`:

```java
@interface Named {
    String name();
}
```

thì phải ghi:

```java
@Named(name = "billing")
class BillingC {
}
```

`@Named("billing")` không hợp lệ chỉ vì kiểu annotation có đúng một phần tử. Tên `value`, không phải số lượng phần tử đơn thuần, quyết định việc bỏ `value =`.

Nếu một phần tử không có `default`, người sử dụng bắt buộc phải cung cấp giá trị. Với khai báo `Label` ở trên, `@Label` hoặc `@Label()` đều thiếu giá trị bắt buộc.

## 4. Nhiều phần tử và giá trị mặc định

Xét kiểu annotation:

```java
@interface Audit {
    String value() default "unspecified";
    int priority() default 1;
    String[] tags() default {};
}
```

Các cách dùng minh họa đều hợp lệ:

```java
@Audit(value = "create", priority = 3, tags = {"db", "write"})
class CreateTask {
}

@Audit("read")
class ReadTask {
}

@Audit
class DefaultTask {
}
```

Phân tích:

| Cách dùng | value | priority | tags |
| --- | --- | --- | --- |
| `@Audit(value = "create", priority = 3, tags = {"db", "write"})` | `"create"` | `3` | `{"db", "write"}` |
| `@Audit("read")` | `"read"` | `1` | Mảng rỗng |
| `@Audit` | `"unspecified"` | `1` | Mảng rỗng |

Đây là hai điểm dễ bỏ sót:

- Dạng một phần tử vẫn hợp lệ khi kiểu có nhiều phần tử, miễn là có phần tử tên `value` và mọi phần tử còn lại đều có mặc định.
- Dạng đánh dấu không bắt buộc kiểu phải hoàn toàn không có phần tử; nó dùng được nếu không còn phần tử bắt buộc nào cần cung cấp.

Nếu `priority` được khai báo là `int priority();` không có mặc định, `@Audit("read")` sẽ thiếu giá trị bắt buộc. Khi ấy cần dạng đầy đủ, chẳng hạn `@Audit(value = "read", priority = 1)`.

### Không trộn dạng viết tắt với cặp có tên

Muốn đặt cả `value` và một phần tử khác, hãy ghi tên cho tất cả:

```java
@Audit(value = "create", priority = 3)
class CorrectTask {
}

// Không hợp lệ:
// @Audit("create", priority = 3)
```

Trong dạng có tên, thứ tự các cặp không phải cơ chế truyền đối số theo vị trí. Có thể đổi thành `@Audit(priority = 3, value = "create")` mà các giá trị tương ứng vẫn giữ nguyên. Chọn thứ tự nhất quán để dễ đọc.

## 5. Phần tử kiểu mảng

Với:

```java
@interface Roles {
    String[] value();
}
```

có thể viết:

```java
@Roles({"reader", "writer"})
class MultiRole {
}

@Roles("reader")
class OneRole {
}

@Roles({})
class NoRoles {
}
```

Khi cung cấp đúng một phần tử cho giá trị mảng, Java cho phép bỏ ngoặc nhọn bao mảng. `@Roles("reader")` vẫn cung cấp một `String[]` dài 1; nó không đổi kiểu phần tử annotation thành `String`.

Trong dạng đầy đủ, ý tưởng tương tự: `@Roles(value = "reader")` tương ứng mảng một phần tử.

Dấu ngoặc nhọn rỗng `{}` diễn đạt mảng rỗng. Đây không phải `null`; giá trị phần tử annotation không được là `null`.

Không dùng biểu thức `new String[] {...}` thay cho cú pháp mảng của annotation. Giá trị annotation tuân theo quy tắc riêng về biểu thức và kiểu được phép, không phải mọi biểu thức khởi tạo đối tượng thông thường.

## 6. Chương trình hoàn chỉnh

Ví dụ dùng Java 17+ và reflection chỉ để quan sát các giá trị đã cung cấp. `RUNTIME` và `TYPE` trong khai báo giúp các annotation của ví dụ được đọc trên lớp lúc chạy.

Lưu thành `AnnotationFormsDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class AnnotationFormsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Reviewed {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Label {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Audit {
        String value() default "unspecified";
        int priority() default 1;
        String[] tags() default {};
    }

    @Reviewed
    static final class CheckedTask {
    }

    @Label("billing")
    static final class BillingTask {
    }

    @Audit(value = "create", priority = 3, tags = {"db", "write"})
    static final class CreateTask {
    }

    @Audit("read")
    static final class ReadTask {
    }

    @Audit
    static final class DefaultTask {
    }

    static void printAudit(Class<?> type) {
        Audit audit = type.getAnnotation(Audit.class);
        if (audit == null) {
            throw new IllegalArgumentException("Audit annotation is required");
        }
        System.out.println(type.getSimpleName() + ": "
                + audit.value() + ", priority=" + audit.priority()
                + ", tags=" + Arrays.toString(audit.tags()));
    }

    public static void main(String[] args) {
        System.out.println("reviewed: "
                + CheckedTask.class.isAnnotationPresent(Reviewed.class));
        Label label = BillingTask.class.getAnnotation(Label.class);
        System.out.println("label: " + label.value());

        printAudit(CreateTask.class);
        printAudit(ReadTask.class);
        printAudit(DefaultTask.class);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 AnnotationFormsDemo.java
java AnnotationFormsDemo
```

Stdout:

```text
reviewed: true
label: billing
CreateTask: create, priority=3, tags=[db, write]
ReadTask: read, priority=1, tags=[]
DefaultTask: unspecified, priority=1, tags=[]
```

Kết quả cho thấy các phần tử không ghi tường minh vẫn có giá trị mặc định khi đọc. `@Audit("read")` dùng dạng một phần tử dù `Audit` có ba phần tử; `@Audit` dùng dạng đánh dấu vì cả ba đều có mặc định.

Không có tác vụ nghiệp vụ nào tự được chạy trong ví dụ. Reflection chỉ đọc dữ liệu và phương thức `printAudit` chủ động in chúng.

## 7. Giới hạn giá trị cần biết khi sử dụng

Trong các ví dụ chuỗi và số ở bài này, giá trị annotation phải là giá trị hợp lệ theo quy tắc annotation, chẳng hạn hằng tại thời điểm biên dịch:

```java
static final String DOMAIN = "billing";

// Có thể dùng DOMAIN làm giá trị annotation trong ngữ cảnh khai báo phù hợp.
```

Không thể thay giá trị bằng một lời gọi tùy ý như `loadDomain()` hoặc biến trạng thái thay đổi lúc chạy.

Các phần tử annotation có thể dùng một tập kiểu được Java cho phép, gồm kiểu nguyên thủy, `String`, `Class`, enum, kiểu annotation khác và mảng một chiều tương ứng. Không thể khai báo một phần tử tùy ý kiểu `List<String>` rồi kỳ vọng nó hoạt động như một tham số phương thức thông thường.

Bài này tập trung vào các dạng sử dụng. Khi thiết kế kiểu annotation, cần chọn tên phần tử, kiểu và mặc định có ý nghĩa rõ ràng để cú pháp ngắn không làm mất thông tin quan trọng.

## 8. Lỗi thường gặp

| Nhầm lẫn | Cách sửa |
| --- | --- |
| Có một phần tử tên `name` nên được bỏ `name =` | Chỉ phần tử tên `value` có quy tắc viết tắt này |
| Kiểu có nhiều phần tử thì không bao giờ dùng được dạng một phần tử | Kiểm tra `value` và mặc định của các phần tử còn lại |
| `@Audit` luôn có nghĩa kiểu annotation không có dữ liệu | Các phần tử có thể nhận giá trị mặc định |
| Ghi `@Audit("x", priority = 2)` | Dùng `@Audit(value = "x", priority = 2)` |
| Bỏ một phần tử không có mặc định | Cung cấp giá trị bắt buộc |
| Giá trị mảng một phần tử phải luôn có ngoặc nhọn | Có thể bỏ ngoặc nhọn cho một phần tử theo cú pháp annotation |
| Dùng `null` để biểu diễn không có nhãn | Chọn mặc định hoặc mô hình dữ liệu hợp lệ khác |
| Ghi cùng tên phần tử hai lần | Mỗi phần tử chỉ được cung cấp một lần trong một lần sử dụng annotation |

Trước khi sửa một lỗi biên dịch, hãy mở khai báo `@interface` và xem tên, kiểu, mặc định của từng phần tử. Đếm số giá trị nhìn thấy ở nơi sử dụng chưa đủ để xác định annotation có hợp lệ hay không.

## 9. Thực hành

1. Đổi `@Label("billing")` thành `@Label(value = "billing")`; stdout có đổi không?
2. Đổi thứ tự các cặp trong annotation của `CreateTask`; giá trị có đổi không?
3. Đổi `tags = {"db", "write"}` thành `tags = "db"`; mảng còn bao nhiêu phần tử?
4. Bỏ mặc định của `priority`; những lớp nào trong chương trình gốc thiếu giá trị bắt buộc?
5. Viết `@Audit()` thay `@Audit` trên `DefaultTask` khi vẫn giữ đầy đủ mặc định.

Đáp án:

1. Không; hai cách cung cấp cùng phần tử `value`.
2. Không; cặp tên–giá trị không phụ thuộc thứ tự vị trí.
3. Một phần tử, nên phần in ra là `tags=[db]`.
4. `ReadTask` và `DefaultTask`; `CreateTask` đã cung cấp `priority`.
5. Vẫn hợp lệ và đọc được các giá trị mặc định như cũ.

Mỗi lần thực hành nên bắt đầu từ bản gốc để thay đổi này không ảnh hưởng kết quả của thí nghiệm khác.

## Tài liệu đối chiếu

Xem [JLS 21 §9.7.1 — Normal Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.1), [§9.7.2 — Marker Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.2), [§9.7.3 — Single-Element Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.3) và [§9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.1).
