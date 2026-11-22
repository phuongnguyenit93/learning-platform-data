# Ảnh hưởng của thay đổi giá trị mặc định đến annotation đã biên dịch trong Java

Một đặc điểm dễ gây bất ngờ của annotation trong Java là: **thay đổi `default` của một annotation element có thể làm thay đổi giá trị đọc được từ một class đã biên dịch từ trước**, dù không biên dịch lại class đó.

Điều này xảy ra khi nơi sử dụng annotation **không khai báo tường minh** giá trị cho phần tử đang xét. Nếu nơi sử dụng đã khai báo giá trị tường minh, giá trị ấy được lưu trong metadata của class sử dụng và không bị thay thế bởi `default` mới.

Java Language Specification (JLS) §9.6.2 quy định rõ: giá trị mặc định không được biên dịch vào từng nơi sử dụng annotation; chúng được áp dụng động lúc annotation được đọc. Do đó một thay đổi nhỏ trong kiểu annotation có thể thay đổi hành vi của code, framework hoặc công cụ xử lý metadata đã được biên dịch trước đó.

## 1. Phân biệt giá trị tường minh và giá trị mặc định

Xét kiểu annotation:

~~~java
package demo;

public @interface Dispatch {
    String channel() default "standard";
    int retries() default 1;
}
~~~

Hai cách dùng khác nhau:

~~~java
@Dispatch
class Unspecified {
}

@Dispatch(channel = "priority")
class Explicit {
}
~~~

- **Unspecified** không khai báo `channel` hoặc `retries`. Khi đọc annotation, cả hai phần tử được cung cấp từ giá trị mặc định của kiểu Dispatch đang được sử dụng.
- **Explicit** khai báo **channel = "priority"** nhưng không khai báo `retries`. Vì thế `channel` có giá trị tường minh "priority"; `retries` vẫn lấy từ `default`.
- Cú pháp **@Dispatch** hoàn toàn hợp lệ vì cả hai phần tử của Dispatch đều có giá trị mặc định.

Nếu cập nhật khai báo thành:

~~~java
public @interface Dispatch {
    String channel() default "balanced";
    int retries() default 3;
}
~~~

thì một chương trình đọc metadata theo phiên bản Dispatch mới có thể quan sát:

| Class được gắn annotation | `channel()` với Dispatch v1 | `channel()` với Dispatch v2 | `retries()` v1 → v2 |
| --- | --- | --- | --- |
| **Unspecified** dùng `@Dispatch` | `standard` | `balanced` | `1` → `3` |
| **Explicit** dùng `@Dispatch(channel = "priority")` | `priority` | `priority` | `1` → `3` |

Kết quả trên không đòi hỏi biên dịch lại **Unspecified** hoặc **Explicit**, miễn là khi chạy chương trình sử dụng đúng phiên bản mới của kiểu **demo.Dispatch** và giữ nguyên các class còn lại.

## 2. Vì sao class đã biên dịch vẫn nhận default mới?

Cần phân biệt hai phần metadata nằm ở **hai tệp class khác nhau**:

**Kiểu annotation — `Dispatch.class`:** khai báo danh sách các phần tử, kiểu trả về và giá trị mặc định tương ứng. Trong định dạng class file của JVM, giá trị mặc định của mỗi phần tử annotation có thể được ghi ở thuộc tính **AnnotationDefault** trên phương thức tương ứng.

**Class sử dụng — `Unspecified.class`, `Explicit.class`:** ghi nhận annotation được sử dụng và các cặp tên–giá trị **đã chỉ định tường minh**. Với retention thích hợp, những cặp này nằm trong metadata annotation của tệp class. Trình biên dịch không cần sao chép mặc định của `channel()` hay `retries()` vào mỗi nơi sử dụng.

Hình dung quá trình đọc:

~~~text
                    Dispatch.class
                 ┌──────────────────────────┐
                 │ channel default=balanced │
                 │ retries default=3        │
                 └─────────────┬────────────┘
                               │
             khi đọc một phần tử chưa có giá trị tường minh
                               │
  Unspecified.class            ▼              Explicit.class
  ┌────────────────┐    Giá trị được đọc      ┌──────────────────────────┐
  │ @Dispatch      │    từ metadata          │ @Dispatch(channel=       │
  │ (không truyền) │                          │   "priority")            │
  └────────────────┘                          └──────────────────────────┘
  channel=balanced                            channel=priority
  retries=3                                   retries=3
~~~

Sơ đồ này là minh họa ý nghĩa metadata, không phải biểu diễn chính xác bytecode từng byte.

Các điểm quan trọng:

1. **Không có giá trị tường minh** ở nơi sử dụng thì `default` được phân giải khi đọc annotation.
2. **Đã có giá trị tường minh** thì giá trị đó được dùng; sửa default không ghi đè metadata tường minh.
3. Thay đổi `default` làm thay đổi tệp class của **kiểu annotation**, chứ không tự chỉnh sửa bytecode của các class đã gắn nó.
4. Ứng dụng phải thực sự dùng **định nghĩa annotation mới** ở môi trường chạy. Chỉ sửa mã nguồn nhưng vẫn chạy với tệp Dispatch.class cũ thì kết quả không đổi.
5. Với reflection, cần retention **RUNTIME** để đọc annotation trên class qua `Class.getAnnotation(...)`. Quy tắc về `default` không phải là hành vi riêng của reflection; nó được đặc tả trong ngôn ngữ Java cho lúc annotation được đọc.

**Phân biệt với interface default method:** Cú pháp `String channel() default "balanced";` trong annotation khai báo **giá trị mặc định của element**. Nó không phải Java 8 **default method** có phần thân trong interface thông thường.

## 3. Thí nghiệm Java 17+: chạy class cũ với annotation type mới

Thí nghiệm này gồm **hai lượt biên dịch**. Lượt đầu biên dịch tất cả source theo phiên bản v1. Lượt thứ hai chỉ biên dịch lại **Dispatch.java** theo phiên bản v2. Giữ nguyên các tệp `Unspecified.class`, `Explicit.class` và `Main.class` để chứng minh sự thay đổi phát sinh khi đọc annotation.

Tạo cấu trúc:

~~~text
src/
└── demo/
    ├── Dispatch.java
    ├── Unspecified.java
    ├── Explicit.java
    └── Main.java
~~~

### Bước 1 — Phiên bản v1

**Tệp `src/demo/Dispatch.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Dispatch {
    String channel() default "standard";
    int retries() default 1;
}
~~~

**Tệp `src/demo/Unspecified.java`:**

~~~java
package demo;

@Dispatch
public class Unspecified {
}
~~~

**Tệp `src/demo/Explicit.java`:**

~~~java
package demo;

@Dispatch(channel = "priority")
public class Explicit {
}
~~~

**Tệp `src/demo/Main.java`:**

~~~java
package demo;

import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws NoSuchMethodException {
        Method method = Dispatch.class.getMethod("channel");
        System.out.println("annotation default=" + method.getDefaultValue());

        printConfig(Unspecified.class);
        printConfig(Explicit.class);
    }

    private static void printConfig(Class<?> type) {
        Dispatch annotation = type.getAnnotation(Dispatch.class);
        if (annotation == null) {
            System.out.println(type.getSimpleName() + ": missing @Dispatch");
            return;
        }

        System.out.println(type.getSimpleName()
                + ": channel=" + annotation.channel()
                + ", retries=" + annotation.retries());
    }
}
~~~

Trong thư mục chứa **src**, biên dịch cả bốn tệp một lần:

~~~bash
javac -encoding UTF-8 -d out src/demo/Dispatch.java src/demo/Unspecified.java src/demo/Explicit.java src/demo/Main.java
java -cp out demo.Main
~~~

**Stdout lần chạy v1:**

~~~text
annotation default=standard
Unspecified: channel=standard, retries=1
Explicit: channel=priority, retries=1
~~~

Dòng đầu tiên đến từ **Method.getDefaultValue()**, đọc `default` khai báo trên phần tử `channel()` của kiểu Dispatch. Hai dòng sau đến từ annotation gắn trên từng class.

### Bước 2 — Chỉ thay đổi annotation type thành v2

Giữ nguyên tên package, tên kiểu, danh sách element, kiểu trả về và **@Retention/@Target**. Trong tệp **src/demo/Dispatch.java**, chỉ sửa hai giá trị:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Dispatch {
    String channel() default "balanced";
    int retries() default 3;
}
~~~

Đoạn trên là **phần khai báo đã sửa**, giữ nguyên dòng `package demo;` và bốn import của tệp ở bước 1. Không thay đổi ba tệp source còn lại.

Biên dịch **chỉ một tệp Dispatch.java** vào cùng thư mục `out` rồi chạy lại:

~~~bash
javac -encoding UTF-8 -d out src/demo/Dispatch.java
java -cp out demo.Main
~~~

**Stdout lần chạy v2:**

~~~text
annotation default=balanced
Unspecified: channel=balanced, retries=3
Explicit: channel=priority, retries=3
~~~

Điểm kiểm chứng:

- **Main.class**, **Unspecified.class**, **Explicit.class** vẫn là binary của lượt biên dịch v1.
- Chỉ **Dispatch.class** đã được cập nhật. Khi tạo một tiến trình JVM mới và đọc annotation, `Unspecified` nhận giá trị mặc định v2.
- `Explicit.channel()` vẫn là "priority" vì giá trị đó được khai báo tường minh khi biên dịch Explicit.class.
- `Explicit.retries()` đổi từ 1 thành 3 vì nó chưa từng được khai báo tường minh.
- **getDefaultValue()** đọc giá trị mặc định hiện có của phương thức annotation, độc lập với giá trị được cung cấp tại nơi sử dụng.

Nếu đóng gói ứng dụng thành nhiều JAR hoặc module, nguyên tắc vẫn tương tự: binary của nơi sử dụng annotation và binary định nghĩa kiểu annotation có thể được xây dựng ở hai thời điểm khác nhau. Cần biết tệp class phiên bản nào được nạp thực tế trong tiến trình chạy; classpath, module path và class loader quyết định điều đó.

### Kiểm tra class file bằng javap

Sau lần biên dịch v2, chạy:

~~~bash
javap -v -p out/demo/Dispatch.class
javap -v -p out/demo/Unspecified.class
javap -v -p out/demo/Explicit.class
~~~

Tìm các phần liên quan trong đầu ra dài của `javap`:

- **Dispatch.class:** các phần tử `channel()` và `retries()` có thông tin **AnnotationDefault** tương ứng "balanced" và 3.
- **Unspecified.class:** metadata về `demo.Dispatch` tồn tại nhưng không chứa cặp **channel = ...** hay **retries = ...** tường minh.
- **Explicit.class:** metadata có cặp **channel = "priority"**, nhưng không có cặp `retries = ...` tường minh.

Không cần phụ thuộc vào số thứ tự constant-pool hoặc cách `javap` in chỉ số, vì chúng có thể khác theo trình biên dịch/bản JDK. Điều cần xác minh là **cặp element-value tường minh nằm ở nơi sử dụng**, trong khi **giá trị mặc định nằm ở kiểu annotation**.

## 4. Điều gì xảy ra khi một phần tử đã được truyền tường minh?

Nếu lớp được biên dịch như sau:

~~~java
@Dispatch(channel = "manual", retries = 7)
class FullyExplicit {}
~~~

thì thay `default "standard"` thành `default "balanced"`, hoặc thay `default 1` thành `default 3`, **không làm thay đổi hai giá trị quan sát được** trên binary đã biên dịch của FullyExplicit. Cả "manual" và 7 đã được chỉ định tường minh.

Trường hợp hỗn hợp:

~~~java
@Dispatch(channel = "priority")
class PartlyExplicit {}
~~~

chỉ `channel` được chốt bằng giá trị tường minh. `retries` vẫn phụ thuộc vào khai báo default của phiên bản Dispatch đang được dùng.

Phạm vi ảnh hưởng do đó là **theo từng annotation element**, không phải theo cả annotation. Một annotation vừa có thể chứa một element-value đã ghi trong class file, vừa dựa vào default động cho một element khác.

## 5. Đổi default có làm mất tương thích nhị phân không?

Cần tách hai khái niệm:

**Tương thích nhị phân (*binary compatibility*):** binary đã biên dịch vẫn có thể được JVM liên kết và chạy với định nghĩa kiểu mới trong phạm vi thay đổi được cho phép.

**Tương thích hành vi (*behavioral compatibility*):** chương trình hoặc framework vẫn quan sát cùng giá trị và đưa ra cùng quyết định nghiệp vụ.

Khi **chỉ đổi giá trị `default`**, giữ nguyên tên/kiểu/phương thức của các annotation element, binary của class sử dụng có thể tiếp tục chạy mà không phải biên dịch lại. **Nhưng hành vi có thể thay đổi** khi code đọc element vốn đã bỏ trống.

Ví dụ:

~~~java
@interface Feature {
    boolean enabled() default false;
}
~~~

Giả sử một framework bật chức năng khi đọc thấy `enabled() == true`. Đổi default thành **true** khiến các class cũ chỉ viết **@Feature** có thể bị bật chức năng, mặc dù không có thay đổi nào trong source hay binary của các class ấy.

Điều này có thể tác động đến:

- **Feature flags:** các class cũ bắt đầu được xem như đã bật tính năng.
- **Validation:** thay đổi giá trị mặc định của một ngưỡng có thể khiến cùng một dữ liệu bị chấp nhận hoặc bị từ chối khác trước.
- **Retry, timeout, cache:** thay đổi tham số mặc định làm thay đổi số lần thử, thời gian chờ hoặc thời hạn lưu cache mà không sửa class sử dụng.
- **Security-sensitive metadata:** đổi mặc định như `required`, `allowAnonymous` hoặc `roles` có thể đổi chính sách nếu framework đọc và diễn giải các phần tử đó.

Các ví dụ trên nói về **hành vi của thành phần tiêu thụ annotation**. Java không tự bật feature, retry hay áp quyền chỉ vì annotation xuất hiện.

## 6. Khi thêm phần tử mới hoặc bỏ default

Hai thay đổi liên quan cần được đánh giá riêng với việc **chỉ đổi giá trị mặc định**.

### Thêm element mới và có default

Từ:

~~~java
@interface Audit {
    String category() default "general";
}
~~~

sang:

~~~java
@interface Audit {
    String category() default "general";
    boolean required() default false;
}
~~~

Một class đã biên dịch trước đây với **@Audit** không có cặp `required = ...` trong metadata. Với phiên bản Audit mới, khi đọc **required()** trên annotation ấy, giá trị mặc định **false** được sử dụng.

Điều này giúp mở rộng cấu trúc annotation mà không đòi hỏi mọi nơi sử dụng cũ phải truyền phần tử mới. Dù vậy, việc thêm trường với default vẫn có thể làm thay đổi logic của framework nếu framework bắt đầu diễn giải trường mới.

### Thêm phần tử bắt buộc hoặc xóa default cũ

Từ:

~~~java
@interface Audit {
    String category() default "general";
}
~~~

sang:

~~~java
@interface Audit {
    String category();
}
~~~

Với mã nguồn mới dùng **@Audit** mà không khai báo category, trình biên dịch báo thiếu phần tử bắt buộc. Với **class cũ đã biên dịch** lúc category còn default, có thể vẫn đọc được đối tượng annotation qua reflection, nhưng khi gọi **category()** mà không có element-value đã ghi và không còn default, Java reflection có thể ném **java.lang.annotation.IncompleteAnnotationException**.

Đây là ví dụ rõ vì sao **JVM vẫn liên kết binary được** chưa đủ để bảo đảm an toàn ở runtime. Tùy thay đổi khác như đổi kiểu, xóa phương thức hoặc thay enum được tham chiếu, lỗi quan sát được có thể khác; không nên đánh đồng mọi thay đổi API annotation với việc đổi giá trị `default`.

## 7. Kiểm tra default qua reflection và giới hạn của phép kiểm tra

Với annotation type có retention **RUNTIME**, hai API hay dùng có chức năng khác nhau:

~~~java
Dispatch annotation = Unspecified.class.getAnnotation(Dispatch.class);
String effectiveChannel = annotation.channel();

Object declaredDefault =
        Dispatch.class.getMethod("channel").getDefaultValue();
~~~

- **annotation.channel():** lấy giá trị hiệu lực trên **một nơi sử dụng**. Đó có thể là giá trị tường minh hoặc giá trị mặc định hiện hành.
- **Method.getDefaultValue():** lấy giá trị mặc định khai báo trên **chính annotation element**, bất kể một class cụ thể truyền giá trị tường minh ra sao. Nếu element không khai báo default thì kết quả là **null**.
- Với element nguyên thủy như **int retries()**, **getDefaultValue()** trả về giá trị đóng hộp, chẳng hạn **Integer**, thay vì primitive.

**Không được suy luận rằng hai kết quả luôn bằng nhau.** Ở thí nghiệm v2, `Dispatch.channel()` trên Explicit cho "priority", còn `getDefaultValue()` của phương thức channel cho "balanced".

Một API phản chiếu giá trị hiệu lực không nhất thiết cho biết trực tiếp element-value đó được viết tường minh trong mã nguồn hay được lấp từ default. Để kiểm tra chính xác sự khác biệt ở mức binary, có thể dùng `javap -v` hoặc công cụ đọc class-file metadata. Java reflection thông thường phục vụ đọc giá trị hiệu lực hơn là khôi phục cú pháp nguồn.

Cũng cần phân biệt **retention**:

- **RUNTIME:** annotation có thể truy xuất qua reflection ở runtime; ví dụ thí nghiệm sử dụng loại này.
- **CLASS:** annotation được ghi trong class file nhưng thông thường không truy cập qua reflection tại runtime.
- **SOURCE:** annotation không được giữ lại trong class file sau biên dịch.

Quy tắc về default ở JLS gắn với lúc đọc annotation, nhưng khả năng quan sát bằng API cụ thể còn phụ thuộc retention và thành phần xử lý metadata. Không dùng kết quả `getAnnotation(...) == null` từ annotation retention CLASS/SOURCE để kết luận rằng giá trị default đã được đóng băng vào binary.

## 8. Các lỗi suy luận thường gặp

| Nhận định hoặc cách làm | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Mỗi nơi dùng annotation đều chứa bản sao default lúc biên dịch.” | Không đúng cơ chế class file | Default nằm trong định nghĩa annotation type và được áp dụng lúc đọc |
| “Đổi default bắt buộc biên dịch lại mọi class sử dụng.” | Không đúng với trường hợp chỉ đổi giá trị default | Class cũ có thể nhận default mới qua định nghĩa annotation mới |
| “Không biên dịch lại nên chắc chắn hành vi không đổi.” | Lẫn binary compatibility và behavioral compatibility | Phải kiểm tra những element bị bỏ trống và thành phần tiêu thụ |
| “Sửa default sẽ ghi đè giá trị đã chỉ định trong @Annotation.” | Bỏ qua cặp giá trị tường minh | Giá trị tường minh được ưu tiên cho chính element đó |
| “Chỉ cần cập nhật source annotation là đủ.” | JVM vẫn có thể tải annotation class cũ | Xác minh đúng binary/version/classpath hoặc module path khi chạy |
| “Annotation tự thi hành thay đổi default.” | Annotation chứa metadata | Cần code/framework/công cụ đọc rồi hành động dựa trên metadata |
| “Xóa default trên element cũ vẫn an toàn tuyệt đối.” | Class cũ có thể thiếu element-value và reflection gặp lỗi | Đánh giá khả năng ném IncompleteAnnotationException |
| “getDefaultValue() trả về giá trị đã khai báo trên class sử dụng.” | Nhầm nơi đọc | getDefaultValue() đọc default trên phương thức của annotation type |

## 9. Quy trình đánh giá khi thay đổi annotation default trong thư viện

Nếu một annotation là API công khai của thư viện/framework, nên đánh giá thay đổi theo thứ tự:

1. **Xác định element thay đổi.** Ghi lại tên, kiểu, default cũ và mới; kiểm tra chỉ đổi default hay còn sửa chữ ký/phần tử.
2. **Tìm nơi sử dụng bỏ trống element đó.** Những vị trí như **@Dispatch** và **@Dispatch(channel = "priority")** không ghi tường minh mọi phần tử. Mỗi element bỏ trống là nơi có thể nhận giá trị mới.
3. **Xác định người tiêu thụ metadata.** Annotation processor, reflection, thư viện quét class hay framework sẽ quyết định ảnh hưởng thực tế của giá trị mới.
4. **Thử nghiệm trộn binary cũ với annotation type mới.** Giữ nguyên class consumer đã biên dịch và cập nhật riêng annotation library, giống thí nghiệm v1/v2.
5. **Kiểm tra chính sách ngược.** Nếu default biểu diễn ngưỡng bảo mật, tùy chọn bật/tắt hoặc hành vi nhạy cảm, đánh giá việc đổi giá trị như một thay đổi chức năng cần thông báo rõ.
6. **Làm rõ ý đồ ở những nơi phải ổn định.** Nơi sử dụng muốn cố định hành vi có thể khai báo element tường minh, ví dụ **@Dispatch(retries = 1)**, thay vì phụ thuộc default có thể tiến hóa.
7. **Kiểm tra phiên bản thực sự được nạp.** Với hệ thống nhiều dependency hay class loader, test phải phản ánh tập binary được triển khai thực tế.

Nếu một default mới được đưa ra vì muốn thay đổi hành vi trong phiên bản mới của framework, hãy mô tả thay đổi hành vi trong tài liệu phát hành. Không dựa riêng vào việc chương trình còn biên dịch hoặc khởi động được để coi thay đổi là an toàn.

## 10. Bài tập tự kiểm tra

Cho phiên bản v1:

~~~java
@interface Schedule {
    int interval() default 10;
    String unit() default "seconds";
}

@Schedule
class A {}

@Schedule(interval = 5)
class B {}

@Schedule(interval = 5, unit = "minutes")
class C {}
~~~

Giả sử các class A, B, C đã biên dịch, sau đó chỉ phiên bản `Schedule.class` được cập nhật thành:

~~~java
@interface Schedule {
    int interval() default 20;
    String unit() default "minutes";
}
~~~

Các giá trị hiệu lực khi đọc annotation bằng phiên bản mới là:

| Class | `interval()` | `unit()` | Giải thích |
| --- | ---: | --- | --- |
| **A** | 20 | minutes | Không truyền tường minh phần tử nào |
| **B** | 5 | minutes | interval tường minh; unit dùng default mới |
| **C** | 5 | minutes | Cả hai phần tử tường minh, giữ nguyên giá trị cũ |

**Câu hỏi:** Nếu thay **default 20** thành **default 30**, class nào có thể quan sát interval khác đi khi đọc lại bằng bản Schedule mới? **Chỉ A**, vì B và C đã chỉ định **interval = 5** tường minh.

**Câu hỏi:** Nếu xóa `default` khỏi `unit()` mà vẫn chạy binary cũ, class nào có nguy cơ lỗi khi gọi `unit()`? **A và B** vì thiếu element-value `unit` tường minh; **C** vẫn chứa giá trị `unit = "minutes"` của nó.

**Câu hỏi:** Vì sao `javap` hữu ích ở đây? Vì có thể kiểm tra cặp element-value đã được ghi tường minh tại nơi sử dụng và default trên kiểu annotation, thay vì suy luận từ việc source có vẻ không đổi.

## 11. Tài liệu chuẩn để đối chiếu

- **Java Language Specification §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se22/html/jls-9.html#jls-9.6.2 — quy định default áp dụng động khi annotation được đọc và có thể ảnh hưởng binary đã biên dịch.
- **Java Language Specification §13.5.8 — Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se22/html/jls-13.html#jls-13.5.8 — phân biệt tương thích liên kết binary với tác động của việc thay đổi annotation lên API phản chiếu.
- **Java SE 17 — Method.getDefaultValue():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue() — trả về giá trị mặc định khai báo trên element hoặc null nếu không có.

Điểm cần ghi nhớ khi thiết kế annotation: **default là một phần của hợp đồng kiểu annotation được diễn giải lúc đọc**, không phải một giá trị cố định được sao chép vào từng class đã sử dụng annotation. Vì vậy, thay đổi `default` phải được đánh giá cả ở mức tương thích nhị phân lẫn hành vi thực tế, nhất là khi nhiều phiên bản thư viện và ứng dụng được triển khai độc lập.
