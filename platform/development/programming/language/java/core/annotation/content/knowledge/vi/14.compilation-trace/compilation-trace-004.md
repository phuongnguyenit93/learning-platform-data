# `AnnotationDefault` và cách Java lưu giá trị mặc định của phần tử annotation

## 1. Từ từ khóa `default` đến dấu vết trong class file

Khi định nghĩa một loại annotation (`@interface`), Java cho phép một **phương thức phần tử** có giá trị mặc định bằng từ khóa `default`:

```java
@interface RetryPolicy {
    String name();
    int attempts() default 3;
    String[] labels() default {"normal"};
}
```

Trong ví dụ:

- `name()` **không có giá trị mặc định**: nơi sử dụng phải cung cấp `name = ...`.
- `attempts()` mặc định là số nguyên `3`.
- `labels()` mặc định là mảng chuỗi chứa một phần tử `"normal"`.

Một annotation sử dụng loại này có thể bỏ qua những phần tử đã khai báo mặc định:

```java
@RetryPolicy(name = "SEND_MAIL")
class MailTask {}
```

Khi chương trình đọc annotation bằng Reflection, `attempts()` trả về `3` và `labels()` trả về `{"normal"}`, dù hai giá trị này **không được viết tại chỗ sử dụng**.

Vậy compiler lưu mặc định ở đâu? Trong cấu trúc class file của JVM, mặc định được thể hiện qua một **thuộc tính có tên `AnnotationDefault`** gắn với mục `method_info` tương ứng với từng **phương thức phần tử** của loại annotation.

Đây là nội dung của bài: phân biệt cấu trúc lưu trữ mặc định với cách khai báo annotation và với hành vi đọc giá trị lúc chạy.

## 2. Mặc định nằm ở *khai báo loại annotation*, không phải ở mỗi nơi dùng

Xét hai nơi sử dụng:

```java
@RetryPolicy(name = "SEND_MAIL")
class MailTask {}

@RetryPolicy(name = "PROCESS_ORDER", attempts = 5)
class OrderTask {}
```

Hai class sử dụng **cùng loại annotation** nhưng khác nhau về giá trị:

| Phần tử | Mặc định trong loại `RetryPolicy` | `MailTask` | `OrderTask` |
| --- | --- | --- | --- |
| `name()` | Không có | `"SEND_MAIL"` (tường minh) | `"PROCESS_ORDER"` (tường minh) |
| `attempts()` | `3` | `3` (nhận từ mặc định) | `5` (tường minh) |
| `labels()` | `{"normal"}` | `{"normal"}` (nhận từ mặc định) | `{"normal"}` (nhận từ mặc định) |

**Lưu ý quan trọng:** nơi sử dụng annotation thường chỉ ghi những **cặp tên–giá trị được cung cấp tường minh**. Nó không cần sao chép mọi giá trị mặc định vào annotation trên mỗi class.

Khi đọc thông tin annotation, runtime kết hợp **giá trị tường minh ở vị trí sử dụng** với **mặc định lấy từ định nghĩa loại annotation**. Nếu có giá trị tường minh thì giá trị ấy được sử dụng; nếu không có thì lấy mặc định khi phần tử có `default`.

Nhờ tách hai chỗ lưu, một định nghĩa mặc định có thể phục vụ nhiều chỗ gắn annotation mà không cần lặp lại cùng metadata trong mỗi class file.

## 3. `AnnotationDefault` là thuộc tính nào trong đặc tả JVM?

Một class file JVM được tổ chức thành nhiều cấu trúc, trong đó mỗi phương thức có một mục `method_info` và có thể có các thuộc tính (`attributes`). Đối với **loại annotation**, từng phần tử có hình thức tương tự phương thức trừu tượng không tham số và không có thân phương thức.

Khi một phần tử có `default`, compiler tạo thuộc tính `AnnotationDefault` tương ứng trên `method_info` của chính phần tử đó. Theo cấu trúc trong JVM Specification, nội dung logic của thuộc tính này là một **`element_value` duy nhất**, biểu diễn giá trị mặc định.

Có thể hình dung (sơ đồ giải thích, không phải dump bytecode nguyên văn):

```text
RetryPolicy.class
  ├── annotation type RetryPolicy
  ├── method_info: name() : String
  │     └── không có AnnotationDefault
  ├── method_info: attempts() : int
  │     └── AnnotationDefault
  │           └── element_value = 3
  └── method_info: labels() : String[]
        └── AnnotationDefault
              └── element_value = {"normal"}
```

Các điểm cần nhớ:

1. Tên `AnnotationDefault` chỉ **thuộc tính của class file**, không phải một annotation mới mà ta viết dưới dạng `@AnnotationDefault` trong source.
2. Thuộc tính nằm trên **phần tử thuộc annotation type**, không phải tự động gắn riêng lên method nghiệp vụ hoặc class sử dụng annotation.
3. Nó mô tả một giá trị mặc định duy nhất cho **một phần tử**; loại annotation có nhiều phần tử default thì mỗi `method_info` liên quan có thuộc tính tương ứng.
4. Một phần tử **không có mặc định** sẽ không có thuộc tính `AnnotationDefault` chỉ để biểu diễn “không có”; Reflection biểu diễn sự vắng mặt ấy bằng `null` khi gọi `Method.getDefaultValue()`.

`AnnotationDefault` khác với `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations`. Hai tên sau mô tả **các chỗ gắn annotation** được ghi vào class file theo chính sách retention; còn `AnnotationDefault` mô tả **mặc định của phần tử trong định nghĩa annotation type**.

### Giá trị được biểu diễn ra sao?

Ở mức class file, `element_value` có mã đánh dấu kiểu (*tag*) và dữ liệu phù hợp. Các dạng giá trị hợp lệ của phần tử annotation gồm:

- Kiểu nguyên thủy như `int` và `boolean`.
- `String`.
- Hằng enum.
- Literal class như `String.class`, với kiểu phần tử `Class<?>` hoặc biến thể được phép.
- Annotation lồng nhau.
- Mảng một chiều của những dạng hợp lệ.

Ví dụ `int attempts() default 3;` có giá trị mặc định số nguyên; `String[] labels() default {"normal"};` là giá trị mảng chứa phần tử chuỗi. Không nên diễn giải `AnnotationDefault` như một đoạn mã Java chạy để tính giá trị: **không có biểu thức nghiệp vụ được chạy lúc truy vấn mặc định**.

Các phần tử annotation không thể dùng kiểu tùy ý như `List<String>` hoặc `Map<String, String>` làm kiểu trả về. Những hạn chế này gắn với yêu cầu biểu diễn metadata nhất quán trong định dạng class file.

## 4. Dùng `javap -v` để thấy `AnnotationDefault`

Trong JDK có công cụ `javap` đọc và trình bày thông tin trong class file. Sau khi biên dịch tệp chứa định nghĩa `RetryPolicy`, có thể chạy:

```bash
javap -v RetryPolicy
```

Từ output dài của `javap -v`, hãy tìm dòng **`AnnotationDefault:`** dưới thông tin các phương thức phần tử có mặc định. Cách biểu diễn có thể khác giữa các phiên bản JDK, nhưng bạn sẽ thấy giá trị mặc định gắn với các phần tử như `attempts` và `labels`.

Nếu kiểm tra class **sử dụng** annotation:

```bash
javap -v MailTask
```

Bạn sẽ tìm metadata của cách sử dụng `@RetryPolicy`. Trong một trường hợp được giữ đến runtime, có thể thấy mục `RuntimeVisibleAnnotations` trên `MailTask.class`. Ở nơi sử dụng `MailTask`, `name = "SEND_MAIL"` được ghi tường minh, còn `attempts = 3` và `labels = {"normal"}` thường **không được chép vào** metadata của `MailTask.class` vì chúng được cung cấp theo mặc định của `RetryPolicy`.

Đừng nhầm:

- **`javap -v RetryPolicy`:** quan sát **mặc định khai báo trong annotation type**, chứa `AnnotationDefault` của phương thức phần tử.
- **`javap -v MailTask`:** quan sát **giá trị gắn trên nơi sử dụng**, qua thông tin annotation của class.

Không nên dựa vào vị trí dòng, offset constant pool hay toàn bộ định dạng output `javap` khi dạy khái niệm: đó là cách công cụ trình bày dữ liệu, không phải cú pháp nguồn bắt buộc. Điều cần đối chiếu là **thuộc tính nào nằm ở class file nào, phục vụ thông tin gì**.

## 5. Ví dụ Java 17+ hoàn chỉnh: mặc định, ghi đè và Reflection

Tạo một tệp duy nhất **`AnnotationDefaultDemo.java`**. Ví dụ dùng API Java SE và chạy bằng JDK 17 trở lên.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RetryPolicy {
    String name();
    int attempts() default 3;
    String[] labels() default {"normal"};
    Class<?> handler() default Object.class;
}

@RetryPolicy(name = "SEND_MAIL")
class MailTask {}

@RetryPolicy(
    name = "PROCESS_ORDER",
    attempts = 5,
    labels = {"urgent", "paid"},
    handler = String.class
)
class OrderTask {}

public class AnnotationDefaultDemo {
    private static void inspect(Class<?> type) {
        RetryPolicy info = type.getAnnotation(RetryPolicy.class);

        if (info == null) {
            System.out.println(type.getSimpleName() + ": no policy");
            return;
        }

        System.out.println(type.getSimpleName()
                + ": name=" + info.name()
                + ", attempts=" + info.attempts()
                + ", labels=" + Arrays.toString(info.labels())
                + ", handler=" + info.handler().getSimpleName());
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        inspect(MailTask.class);
        inspect(OrderTask.class);

        Method name = RetryPolicy.class.getDeclaredMethod("name");
        Method attempts = RetryPolicy.class.getDeclaredMethod("attempts");
        Method labels = RetryPolicy.class.getDeclaredMethod("labels");
        Method handler = RetryPolicy.class.getDeclaredMethod("handler");

        System.out.println("Default name: "
                + (name.getDefaultValue() == null ? "(none)" : "unexpected"));
        System.out.println("Default attempts: "
                + attempts.getDefaultValue());
        System.out.println("Default labels: "
                + Arrays.toString((String[]) labels.getDefaultValue()));
        System.out.println("Default handler: "
                + ((Class<?>) handler.getDefaultValue()).getSimpleName());
    }
}
```

Biên dịch và chạy ở thư mục chứa tệp:

```bash
javac -encoding UTF-8 AnnotationDefaultDemo.java
java AnnotationDefaultDemo
```

**Stdout kỳ vọng, đúng thứ tự:**

```text
MailTask: name=SEND_MAIL, attempts=3, labels=[normal], handler=Object
OrderTask: name=PROCESS_ORDER, attempts=5, labels=[urgent, paid], handler=String
Default name: (none)
Default attempts: 3
Default labels: [normal]
Default handler: Object
```

Tiếp tục quan sát bytecode sau khi đã biên dịch thành công:

```bash
javap -v RetryPolicy
javap -v MailTask
javap -v OrderTask
```

Chương trình trên có một `public class AnnotationDefaultDemo` và tên tệp tương ứng, các kiểu còn lại không phải `public`, nên có thể đặt cùng trong một tệp. Không cần chương trình phụ hoặc classpath ngoài JDK.

### Giải thích các dòng quan sát được

**`MailTask`:** chỉ cung cấp `name = "SEND_MAIL"`. Khi gọi `info.attempts()`, `info.labels()` và `info.handler()`, runtime cung cấp các giá trị default trong `RetryPolicy`: `3`, `{"normal"}` và `Object.class`. `Arrays.toString` biểu diễn mảng là `[normal]`, còn `Object.class.getSimpleName()` là `Object`.

**`OrderTask`:** nơi sử dụng chỉ định tường minh cả bốn phần tử; lời gọi phần tử trả về `5`, `{"urgent", "paid"}`, và `String.class` tương ứng. Những giá trị này **ghi đè** giá trị mặc định ở vị trí sử dụng, nhưng **không sửa định nghĩa default** của loại `RetryPolicy`.

**`name.getDefaultValue()`:** đối tượng `Method` này mô tả `name()` trong `RetryPolicy`. Vì phần tử không có `default`, API trả `null`, và chương trình in `(none)`. `name()` vẫn có giá trị thực tế ở từng nơi sử dụng, bởi compiler yêu cầu người viết cung cấp nó.

**`attempts.getDefaultValue()`:** luôn đọc mặc định `3` trong khai báo loại annotation, kể cả khi `OrderTask` chỉ định `attempts = 5`. `getDefaultValue()` **không đọc dữ liệu từ một nơi sử dụng cụ thể**.

**`labels.getDefaultValue()`:** trả giá trị mảng được biểu diễn dưới dạng một đối tượng `String[]`, nên có thể ép kiểu rồi gọi `Arrays.toString(...)`.

**`handler.getDefaultValue()`:** trả một `Class<?>` đại diện cho `Object.class`, không tự khởi tạo `Object` hay một handler nghiệp vụ.

## 6. Hai câu hỏi Reflection khác nhau

Khi có một đối tượng `Class<?>` của class nghiệp vụ đã gắn `@RetryPolicy`, ta truy vấn **giá trị thực tế tại nơi sử dụng**:

```java
RetryPolicy policy = MailTask.class.getAnnotation(RetryPolicy.class);
int actualAttempts = policy.attempts(); // 3 do lấy mặc định
```

Khi có đối tượng `Method` mô tả **phương thức phần tử trên loại annotation**, ta truy vấn **mặc định do tác giả khai báo**:

```java
Method element = RetryPolicy.class.getDeclaredMethod("attempts");
Object declaredDefault = element.getDefaultValue(); // Integer chứa 3
```

Bảng phân biệt:

| Câu hỏi | Lời gọi | Dữ liệu trả về |
| --- | --- | --- |
| `MailTask` có `@RetryPolicy` không? | `MailTask.class.getAnnotation(RetryPolicy.class)` | Đối tượng `RetryPolicy` hoặc `null` |
| Giá trị `attempts` thực tế trên `MailTask` là gì? | `policy.attempts()` | `int` (ở đây là `3`) |
| Giá trị mặc định được định nghĩa cho `attempts` là gì? | `element.getDefaultValue()` | `Object` đóng gói giá trị, ở đây là `Integer(3)` |
| `name` có default không? | `nameMethod.getDefaultValue()` | `null` nếu không khai báo mặc định |
| Tên/kiểu các phần tử được khai báo là gì? | `RetryPolicy.class.getDeclaredMethods()` | Mảng `Method[]` đại diện các phần tử |

Ở mức thiết kế framework, việc đọc `getDefaultValue()` thường hữu ích cho công cụ phân tích hợp đồng annotation. Với nghiệp vụ thông thường, nếu đã có một đối tượng annotation cụ thể, hãy gọi **phương thức phần tử trực tiếp** như `policy.attempts()`: runtime đã giải quyết giá trị tường minh hoặc default cho bạn.

**Giới hạn quan trọng:** một giá trị thực tế bằng default (ví dụ `3`) không cho biết chắc tác giả **bỏ qua phần tử** hay đã ghi tường minh `attempts = 3`. Hai cách có thể trả cùng giá trị qua Reflection. Muốn biết chính xác cú pháp tại source phải kiểm tra source/metadata tường minh bằng công cụ phù hợp, không suy từ một con số trả về.

## 7. Giá trị mặc định được đánh giá vào lúc nào?

Giá trị mặc định annotation **không được tính toán linh hoạt mỗi lần đọc** bằng một thân phương thức Java. Java chỉ cho phép những giá trị hợp lệ theo quy tắc compile-time cho các phần tử, như literal, constant expression phù hợp, hằng enum, class literal, annotation lồng nhau và mảng một chiều của chúng.

Ví dụ hợp lệ:

```java
@interface ReportOptions {
    int retryCount() default 2;
    String title() default "daily";
    Class<?> formatter() default String.class;
    String[] sections() default {"summary", "details"};
}
```

Những dạng không hợp lệ được minh họa bên dưới — **chỉ để nhận biết lỗi biên dịch, không thêm vào tệp chạy**:

```java
// KHÔNG HỢP LỆ: giá trị default không được gọi phương thức
// để tính dữ liệu runtime như dưới đây.
@interface BadTimestamp {
    String value() default java.time.Instant.now().toString();
}

// KHÔNG HỢP LỆ: kiểu trả về List không phải kiểu phần tử annotation.
@interface BadList {
    java.util.List<String> names() default {};
}
```

Phần tử không được có tham số, không khai báo type parameter, không có mệnh đề `throws`; default chỉ ghi giá trị metadata. Nếu muốn nạp cài đặt động từ database hoặc môi trường, hãy để **consumer** xử lý dữ liệu ngoài annotation thay vì cố đưa biểu thức runtime vào `default`.

## 8. Mặc định và tính tương thích nhị phân

Vì mặc định được lưu ở **khai báo loại annotation**, thay đổi giá trị mặc định trong thư viện có thể thay đổi **giá trị đọc được** trên mã sử dụng đã biên dịch trước đó nếu nơi sử dụng **không chỉ định phần tử tường minh**.

Ví dụ logic:

```java
// Phiên bản thư viện ban đầu:
@interface CacheRule {
    int ttlSeconds() default 60;
}

// Một nơi sử dụng:
@CacheRule
class ProductCache {}
```

Nếu thư viện sau đó thay mặc định `ttlSeconds() default 120` và ứng dụng được chạy với **bản class file loại annotation mới**, mã sử dụng `@CacheRule` có thể nhận `120` từ lời gọi `ttlSeconds()` mà không cần viết `ttlSeconds = 120` ở mỗi nơi sử dụng. Cần bảo đảm tập class thực tế được tải tương thích và đúng phiên bản, tránh lẫn JAR cũ/mới.

Ngược lại, nơi sử dụng chỉ định tường minh `@CacheRule(ttlSeconds = 30)` có giá trị `30` riêng, không đổi theo mặc định mới.

Một khả năng khác là thêm phần tử mới **có giá trị mặc định** vào một annotation type đã phát hành; điều này thường giúp các nơi sử dụng cũ tiếp tục có giá trị phần tử mới khi đọc. Nếu thêm phần tử **bắt buộc không có default**, các chỗ sử dụng chưa cung cấp giá trị có thể gặp vấn đề biên dịch và khi kết hợp phiên bản nhị phân không tương thích có thể gặp lỗi runtime như `IncompleteAnnotationException` khi truy cập phần tử thiếu.

**Nguyên tắc thiết kế API:** coi thay đổi default là thay đổi **hành vi cấu hình** của một annotation đã công bố, không phải chỉnh sửa chỉ để trang trí mã nguồn. Khi dùng annotation để điều khiển nghiệp vụ, cần ghi lại tác động tới những nơi không chỉ định giá trị tường minh và kiểm thử tích hợp theo phiên bản.

## 9. `AnnotationDefault`, `@Retention` và sự hiện diện ở runtime

Cả ba khái niệm có liên quan nhưng không đồng nhất:

1. **`AnnotationDefault`:** class-file attribute trên phần tử thuộc loại annotation, mô tả giá trị mặc định đã khai báo.
2. **`@Retention`:** meta-annotation quyết định cách sử dụng annotation được lưu đến `SOURCE`, `CLASS` hay `RUNTIME`.
3. **`getAnnotation(...)`:** API Reflection dùng để lấy annotation trên một thành phần đã biết, chỉ nhìn thấy những annotation phù hợp được giữ đến runtime.

Chẳng hạn, khai báo:

```java
// Minh họa một annotation với retention SOURCE.
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.SOURCE
)
@interface CompileHint {
    int limit() default 10;
}
```

Ở môi trường biên dịch chuẩn, default `10` là một phần của định nghĩa loại annotation và có thể được biểu diễn qua `AnnotationDefault` trong file `CompileHint.class`. Nhưng những **nơi gắn `@CompileHint` trên các class khác** sẽ bị compiler bỏ khỏi metadata runtime vì retention `SOURCE`.

Không được suy “annotation có default nên Reflection luôn đọc được nơi sử dụng” hoặc “retention `SOURCE` thì loại annotation hoàn toàn không có class file”. Loại annotation là một khai báo Java riêng, có thể được biên dịch thành class file; chính sách retention điều chỉnh **sự tồn tại của annotation tại nơi gắn**, không quyết định có hay không một định nghĩa loại annotation trong dự án.

Nếu muốn đọc đối tượng annotation trên class bằng Reflection, cần `@Retention(RUNTIME)` và metadata đã gắn đúng vị trí. Nếu muốn đọc mặc định **của phương thức phần tử**, chọn `Method` thuộc annotation type và gọi `getDefaultValue()`. Đây là hai thao tác khác nhau.

## 10. Những lỗi thường gặp

1. **Nhầm `AnnotationDefault` với cú pháp `@AnnotationDefault`.** `AnnotationDefault` là tên một class-file attribute; mã Java khai báo default bằng từ khóa `default` bên trong `@interface`.
2. **Tưởng mỗi class sử dụng annotation đều lưu bản sao default.** Nơi dùng thường chỉ cần lưu các cặp được chỉ định tường minh; default thuộc định nghĩa annotation type.
3. **Gọi `getDefaultValue()` trên `Method` của phương thức nghiệp vụ.** Phải lấy `Method` mô tả **phần tử của annotation type**, ví dụ `RetryPolicy.class.getDeclaredMethod("attempts")`.
4. **Tưởng `getDefaultValue()` trả giá trị thực tế của một chỗ sử dụng.** Nó trả giá trị khai báo mặc định. Đọc thực tế bằng đối tượng annotation và gọi `policy.attempts()`.
5. **Quên phần tử không có default.** `getDefaultValue()` trả `null`; đây không phải giá trị hợp lệ để gán cho phần tử annotation tại nơi sử dụng.
6. **Hiểu sai retention.** `AnnotationDefault` có thể hiện diện ở file của loại annotation dù annotation được đặt retention `SOURCE`; các cách sử dụng annotation là dữ liệu khác.
7. **Nhầm `default` của annotation với `default method` của interface.** Phần tử annotation chỉ khai báo giá trị mặc định metadata; không có thân method để chạy mã.
8. **Tưởng thay đổi default không ảnh hưởng mã đã biên dịch.** Nếu nơi sử dụng bỏ qua phần tử, giá trị lúc đọc có thể phụ thuộc định nghĩa annotation type hiện hành.
9. **Dựa vào `javap -v` để suy rằng application đã tải đúng phiên bản class.** Output của file được kiểm tra và class thực sự được class loader nạp có thể khác nếu classpath/module path chứa nhiều phiên bản.
10. **Không xử lý lỗi khi metadata/nhị phân bị lệch phiên bản.** Các lỗi như `IncompleteAnnotationException`, `TypeNotPresentException` hoặc `EnumConstantNotPresentException` có thể xảy ra ở tình huống tương ứng; cần quản lý phiên bản và kiểm thử.

## 11. Bài tập tự kiểm tra

**Bài 1.** `int attempts() default 3;` được biên dịch. `AnnotationDefault` nằm trong class file nào và trên cấu trúc gì?

**Đáp án:** Trong file `RetryPolicy.class` của **loại annotation**, gắn vào mục `method_info` mô tả phần tử `attempts()`, không phải mặc nhiên ở từng class sử dụng annotation.

**Bài 2.** Một class được gắn `@RetryPolicy(name = "X")`. Vì sao `info.attempts()` trả `3` dù không có `attempts = 3` tại nơi gắn?

**Đáp án:** Runtime áp dụng mặc định khai báo trên loại annotation khi phần tử không được cung cấp tường minh.

**Bài 3.** Sự khác biệt giữa `info.attempts()` và `RetryPolicy.class.getDeclaredMethod("attempts").getDefaultValue()` là gì?

**Đáp án:** Lời gọi đầu đọc giá trị **tại chỗ sử dụng** (bao gồm override nếu có), trả `int`. Lời gọi sau đọc **default tại định nghĩa phần tử**, trả `Object` (ở đây đóng gói `Integer`).

**Bài 4.** Vì sao `name.getDefaultValue()` trả `null` nhưng `info.name()` vẫn có thể trả một chuỗi?

**Đáp án:** `name()` không có default, nên người sử dụng annotation phải cung cấp một giá trị tường minh, ví dụ `name = "SEND_MAIL"`.

**Bài 5.** Công cụ nào của JDK cho phép quan sát thuộc tính `AnnotationDefault` và metadata annotation trong `.class`?

**Đáp án:** `javap -v RetryPolicy` để xem định nghĩa phần tử và `javap -v MailTask` để đối chiếu cách sử dụng.

**Bài 6.** Thay default từ `3` sang `8` có làm giá trị `@RetryPolicy(name = "X", attempts = 5)` đổi không?

**Đáp án:** Không đối với phần tử `attempts` tại chỗ sử dụng ấy, vì đã gán tường minh `5`.

**Bài 7.** `@Retention(SOURCE)` có cấm compiler phát sinh `AnnotationDefault` cho các phần tử trong định nghĩa annotation type không?

**Đáp án:** Không. `SOURCE` quy định thời gian lưu **nơi gắn annotation**, không phải xóa phần định nghĩa default trong annotation type.

**Bài 8.** `int ttl() default loadConfig();` có hợp lệ không nếu `loadConfig()` là phương thức đọc tệp?

**Đáp án:** Không. Giá trị default của phần tử annotation phải thuộc dạng được Java chấp nhận tại compile-time; không được tính động bằng lời gọi tùy ý.

**Ghi nhớ:** **`AnnotationDefault` là dấu vết bytecode của giá trị mặc định thuộc *khai báo phần tử của annotation type*.** Giá trị ghi tường minh thuộc *nơi sử dụng annotation*. Reflection lấy giá trị thực tế qua phương thức phần tử, còn `Method.getDefaultValue()` đọc default của định nghĩa; hai thao tác liên quan nhưng không thể thay thế nhau.
