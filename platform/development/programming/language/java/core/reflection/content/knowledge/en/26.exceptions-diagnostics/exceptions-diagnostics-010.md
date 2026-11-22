# `AnnotationTypeMismatchException` và `IncompleteAnnotationException` trong Java Reflection

## 1. Vấn đề: annotation hợp lệ lúc biên dịch nhưng không còn khớp lúc chạy

Hai ngoại lệ trong `java.lang.annotation` thường xuất hiện khi **annotation được ghi vào một class file theo định nghĩa cũ**, còn tại runtime JVM đang dùng **định nghĩa annotation mới** không tương thích. Class file mang annotation lưu tên và giá trị của các phần tử annotation; nó không tự được cập nhật khi thư viện định nghĩa annotation thay đổi.

Hãy phân biệt:

| Ngoại lệ | Điều kiện điển hình | Điều gì không còn khớp? |
| --- | --- | --- |
| `AnnotationTypeMismatchException` | Phần tử `value()` từng trả về `String`, phiên bản mới trả về `int` | **Kiểu giá trị cũ** khác kiểu phần tử trong định nghĩa hiện tại |
| `IncompleteAnnotationException` | Định nghĩa mới thêm phần tử bắt buộc `owner()` nhưng class file cũ chưa lưu giá trị | **Thiếu giá trị** cho phần tử không có `default` |

Cả hai đều là **`RuntimeException` (unchecked)**. Chúng có thể xảy ra trong chương trình có source code hiện tại trông hoàn toàn đúng, vì class file ứng dụng và thư viện trên runtime classpath/module path không được biên dịch cùng một hợp đồng annotation.

Trong Reflection, việc có `Class<?>` hoặc gọi `getAnnotation(...)` thành công **chưa bảo đảm đọc được mọi phần tử**: lỗi thường bộc lộ khi gọi trực tiếp `annotation.value()` / `annotation.owner()`. Thời điểm chi tiết có thể phụ thuộc cách API hoặc framework duyệt và xử lý annotation; không nên coi bước lấy annotation là bằng chứng dữ liệu đã hợp lệ.

Sau bài học, bạn có thể tái tạo cả hai lỗi, hiểu API chẩn đoán, phân biệt với các lỗi annotation khác, và sửa xung đột phiên bản một cách có kiểm chứng.

## 2. Nền tảng: annotation lưu gì trong class file?

Xét annotation dùng ở runtime:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface Info {
    String id();
}
~~~

~~~java
@Info(id = "A1")
public class Record {}
~~~

`@Retention(RetentionPolicy.RUNTIME)` giúp các API Reflection như `Class.getAnnotation(Info.class)` nhìn thấy annotation. Khi `Record.java` được biên dịch, giá trị `id = "A1"` trở thành một phần metadata trong `Record.class`.

Ở phiên bản hiện tại của annotation, mỗi phần tử được khai báo bằng **method không tham số** như `String id()`. `Info.class` được nạp theo classloader/module ở runtime, còn `Record.class` có metadata đã ghi từ lần biên dịch trước. Nếu triển khai chỉ cập nhật `Info.class` mà không biên dịch lại `Record.class`, hai nguồn có thể không thống nhất.

Các điểm quan trọng:

- Annotation có thể chứa các kiểu phần tử mà Java cho phép, ví dụ primitive, `String`, `Class`, enum, annotation và mảng một chiều của các kiểu hợp lệ. Không thể tùy tiện đổi `String` sang `int` rồi mong dữ liệu cũ tự chuyển kiểu.
- Một phần tử có thể khai báo `default`; khi class file không ghi giá trị tường minh cho phần tử đó, API annotation có thể dùng giá trị mặc định từ định nghĩa **hiện tại**.
- `RetentionPolicy.CLASS` được giữ trong class file nhưng không được các API Reflection runtime thông thường trả về như `RUNTIME`; `SOURCE` không lưu vào class file.
- Việc chỉ có một tệp `.java` đúng không xác nhận runtime đúng: phải xem phiên bản `.class` thật sự được nạp.

## 3. `AnnotationTypeMismatchException` — kiểu phần tử đã thay đổi

Theo Java SE 17, ngoại lệ này biểu thị rằng chương trình cố đọc một **phần tử annotation mà kiểu đã thay đổi** sau khi annotation được biên dịch hoặc tuần tự hóa.

Ví dụ lịch sử:

~~~java
// Phiên bản v1, khi lớp sử dụng annotation được biên dịch
public @interface State {
    String value();
}
~~~

~~~java
@State("READY")
public class Stored {}
~~~

Phiên bản mới lại định nghĩa:

~~~java
// Phiên bản v2 đang có mặt khi chạy
public @interface State {
    int value();
}
~~~

Class file cũ của `Stored` vẫn mang giá trị dạng chuỗi `"READY"`, trong khi `State.value()` hiện yêu cầu `int`. Khi gọi `State.value()` trên annotation lấy từ `Stored.class`, runtime không thể trả về kiểu đã khai báo và có thể ném `AnnotationTypeMismatchException`.

### Dữ liệu chẩn đoán của ngoại lệ

~~~java
catch (AnnotationTypeMismatchException ex) {
    System.out.println(ex.element().getName());
    System.out.println(ex.element().getReturnType().getName());
    System.out.println(ex.foundType());
}
~~~

- `element()` trả về `java.lang.reflect.Method` đại diện **phần tử annotation trong định nghĩa hiện tại**. Dùng `getDeclaringClass()`, `getName()`, `getReturnType()` để kiểm tra method mong đợi.
- `foundType()` trả về mô tả kiểu của dữ liệu sai được tìm thấy; chuỗi **có định dạng không được đặc tả**, có thể kèm giá trị. Không parse chuỗi này như một API ổn định, và không dùng nó làm contract để kiểm tra tự động.
- `getMessage()` có ích cho log nhưng nội dung thông báo không phải định dạng để hệ thống khác phụ thuộc.
- Đây là lỗi **không tương thích metadata**, không phải `ClassCastException` thông thường do ứng dụng ép một `Object` sai kiểu.

## 4. `IncompleteAnnotationException` — thiếu phần tử bắt buộc mới

Ngoại lệ này xảy ra khi code đọc một **phần tử mới được thêm vào annotation interface sau khi nơi sử dụng đã được biên dịch**, nhưng class file cũ không chứa giá trị và phần tử mới **không có mặc định**.

Ví dụ:

~~~java
// v1
public @interface Metadata {
    String id();
}
~~~

~~~java
@Metadata(id = "X1")
public class Stored {}
~~~

Sau đó thư viện thay bằng:

~~~java
// v2
public @interface Metadata {
    String id();
    String owner(); // mới thêm, không có default
}
~~~

Khi gọi `metadata.id()`, dữ liệu `"X1"` vẫn hợp lệ. Khi gọi `metadata.owner()`, class file cũ không có `owner` và định nghĩa mới cũng không cung cấp `default` nên runtime ném `IncompleteAnnotationException`.

### Đọc thuộc tính chẩn đoán

~~~java
catch (IncompleteAnnotationException ex) {
    System.out.println(ex.annotationType().getName());
    System.out.println(ex.elementName());
}
~~~

- `annotationType()` trả về `Class<? extends Annotation>` của annotation có phần tử bị thiếu.
- `elementName()` trả về tên phần tử bị thiếu, ví dụ `owner`.
- Constructor `IncompleteAnnotationException(Class<? extends Annotation>, String)` có thể dùng trong code đặc biệt tự xây cơ chế annotation, nhưng trong thực hành thường bạn **bắt và chẩn đoán** lỗi do hệ thống đọc annotation phát hiện.
- Thêm phần tử với giá trị mặc định, ví dụ `String owner() default "UNKNOWN";`, thường giúp **class file cũ vẫn đọc được** phần tử đó mà không cần khai báo giá trị mới. Đây là lựa chọn thiết kế API cần cân nhắc, không giải quyết mọi kiểu thay đổi không tương thích khác.

## 5. Thực hành đầy đủ: tạo hai lỗi bằng hai phiên bản của cùng annotation

Thí nghiệm dưới đây không cần sửa bytecode thủ công. Ta chủ động **biên dịch bản cũ vào một thư mục**, biên dịch **định nghĩa mới cùng chương trình đọc** vào thư mục khác, rồi ưu tiên class mới trên classpath. Điều này mô phỏng lỗi nâng phiên bản dependency nhưng quên biên dịch lại class từng dùng annotation.

Yêu cầu JDK 17+; lệnh dùng `javac --release 17` để cố định cú pháp/API Java 17.

### 5.1. Cấu trúc dự án

~~~text
annotation-compat-demo/
├── old/demo/
│   ├── State.java
│   ├── Metadata.java
│   └── Stored.java
├── current/demo/
│   ├── State.java
│   ├── Metadata.java
│   └── Reader.java
└── out/
    ├── old/
    └── new/
~~~

Các file trong `out` là **đầu ra** của `javac`, không phải file source. Tạo những thư mục này trước khi chạy lệnh biên dịch bên dưới.

### 5.2. Nguồn phiên bản cũ

File `old/demo/State.java`:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface State {
    String value();
}
~~~

File `old/demo/Metadata.java`:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface Metadata {
    String id();
}
~~~

File `old/demo/Stored.java`:

~~~java
package demo;

@State("READY")
@Metadata(id = "X1")
public class Stored {}
~~~

Ở lần biên dịch này, `Stored.class` lưu `State.value` dạng chuỗi và chỉ lưu `Metadata.id`; nó chưa từng biết phương thức `Metadata.owner()`.

### 5.3. Nguồn phiên bản mới

File `current/demo/State.java`:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface State {
    int value(); // v1 là String
}
~~~

File `current/demo/Metadata.java`:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface Metadata {
    String id();
    String owner(); // v1 chưa có; cố ý không khai báo default
}
~~~

File `current/demo/Reader.java`:

~~~java
package demo;

import java.lang.annotation.AnnotationTypeMismatchException;
import java.lang.annotation.IncompleteAnnotationException;

public class Reader {
    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> stored = Class.forName("demo.Stored");

        State state = stored.getAnnotation(State.class);
        Metadata metadata = stored.getAnnotation(Metadata.class);

        System.out.println("State present: " + (state != null));

        try {
            System.out.println("state=" + state.value());
        } catch (AnnotationTypeMismatchException ex) {
            System.out.println("Mismatch element: " + ex.element().getName());
        }

        System.out.println("id=" + metadata.id());

        try {
            System.out.println("owner=" + metadata.owner());
        } catch (IncompleteAnnotationException ex) {
            System.out.println("Missing element: " + ex.elementName());
            System.out.println("Annotation type: "
                    + ex.annotationType().getSimpleName());
        }
    }
}
~~~

Chương trình đọc cố ý dùng `Class.forName("demo.Stored")`: `Reader.java` **không cần compile-time dependency trực tiếp** lên `Stored.class` của bản cũ. Cả `State` và `Metadata` ở chương trình đọc đều là định nghĩa mới.

### 5.4. Biên dịch và chạy

Chạy lệnh trong thư mục `annotation-compat-demo`.

Trên Linux/macOS:

~~~bash
mkdir -p out/old out/new

javac --release 17 -d out/old \
  old/demo/State.java old/demo/Metadata.java old/demo/Stored.java

javac --release 17 -d out/new \
  current/demo/State.java current/demo/Metadata.java current/demo/Reader.java

java -cp "out/new:out/old" demo.Reader
~~~

Trên Windows PowerShell, dùng đường dẫn tương đương và dấu `;` làm dấu phân cách classpath:

~~~powershell
New-Item -ItemType Directory -Force out\old, out\new | Out-Null

javac --release 17 -d out\old old\demo\State.java old\demo\Metadata.java old\demo\Stored.java
javac --release 17 -d out\new current\demo\State.java current\demo\Metadata.java current\demo\Reader.java

java -cp "out\new;out\old" demo.Reader
~~~

**Thứ tự trong classpath rất quan trọng:** `out/new` đứng trước nên runtime dùng `demo.State` và `demo.Metadata` phiên bản mới; `demo.Stored` chỉ có trong `out/old`. Không cho `Stored.java` được biên dịch lại với hai annotation mới trong lúc chuẩn bị thí nghiệm, vì compiler lúc đó sẽ phát hiện khai báo `@State("READY")` sai kiểu và `@Metadata` thiếu `owner`.

Kết quả thực tế được đối chiếu bằng `javac --release 17`, chạy trên JDK 21:

~~~text
State present: true
Mismatch element: value
id=X1
Missing element: owner
Annotation type: Metadata
~~~

Giải thích từng dòng:

1. `getAnnotation(State.class)` vẫn tìm thấy annotation trên `Stored.class`.
2. `state.value()` yêu cầu `int` nhưng class file lưu chuỗi; exception được bắt và `element().getName()` cho `value`.
3. `metadata.id()` vẫn trả `X1`, vì phần tử này không thay đổi.
4. `metadata.owner()` không có giá trị lưu trong class file và cũng không có default; `elementName()` cho `owner`, `annotationType()` cho `Metadata`.

Kết quả trên là **một tình huống tái hiện lỗi xác định**, không phải khẳng định rằng mọi thao tác lấy annotation trên mọi class file không tương thích đều sẽ hoàn tất trước khi ném lỗi. Annotation hỏng cấu trúc hoặc dependency thiếu có thể thất bại theo đường đi khác.

## 6. Thử sửa lỗi `IncompleteAnnotationException` bằng `default`

Ở file `current/demo/Metadata.java`, đổi thành:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface Metadata {
    String id();
    String owner() default "UNKNOWN";
}
~~~

Chỉ biên dịch lại bản **current** (`out/new`); vẫn giữ nguyên `Stored.class` từ `out/old`. Lúc này `metadata.owner()` có thể dùng giá trị mặc định `UNKNOWN` từ định nghĩa hiện tại. Output phần metadata chuyển từ:

~~~text
Missing element: owner
Annotation type: Metadata
~~~

sang:

~~~text
owner=UNKNOWN
~~~

**Chú ý:** `AnnotationTypeMismatchException` ở `State.value()` **vẫn tồn tại**, vì kiểu giá trị lưu cũ chưa tương thích với kiểu mới. Default chỉ xử lý phần tử *vắng mặt*, không tự chuyển kiểu cho phần tử đã lưu sai.

Một hướng sửa đầy đủ hơn là chuẩn hóa các phiên bản dependency và **biên dịch lại tất cả mã dùng annotation** với contract mới. Khi đó compiler phát hiện `@State("READY")` không còn hợp lệ với `int value()` và `@Metadata(id = "X1")` thiếu `owner` (nếu không có default), buộc người duy trì cập nhật source tương ứng.

## 7. Vì sao lỗi lại xuất hiện trong Reflection hoặc framework?

Nhiều thư viện dùng annotation để cấu hình mapping, validation, dependency injection, test, serialization hoặc các bộ xử lý plugin. Một framework có thể:

1. Quét class bằng `Class<?>` hoặc `AnnotatedElement`.
2. Lấy annotation bằng `getAnnotation`, `getDeclaredAnnotation` hay `getAnnotationsByType`.
3. Đọc phần tử annotation để quyết định hành vi, chẳng hạn `annotation.value()`.
4. Phát hiện dữ liệu class file cũ không phù hợp với hợp đồng annotation mới.

Để chẩn đoán đúng, trước hết xác định **method nào đã được gọi**, trên **annotation type nào**, bằng **classloader nào** và từ **artifact/version nào**. Có thể ghi thông tin có cơ sở như:

~~~java
Class<?> inspected = Class.forName("demo.Stored");
System.out.println(inspected.getName());
System.out.println(inspected.getClassLoader());

Class<?> annotationType = demo.State.class;
System.out.println(annotationType.getName());
System.out.println(annotationType.getClassLoader());
~~~

Đây là **fragment chẩn đoán**; trong ứng dụng thực tế cần thay tên `demo.Stored` và `demo.State` theo loại annotation đang gặp. Tránh log toàn bộ annotation bằng `toString()` như phương pháp chẩn đoán duy nhất: việc tạo biểu diễn chuỗi có thể đọc nhiều phần tử và chạm vào dữ liệu đang lỗi.

Nếu framework gọi accessor qua `java.lang.reflect.Method.invoke(...)`, ngoại lệ phát sinh trong method có thể được bọc bằng **`InvocationTargetException`**. Khi đó cần xem `getCause()` để tìm `AnnotationTypeMismatchException` hoặc `IncompleteAnnotationException` thực sự. Gọi trực tiếp `annotation.value()` như ví dụ ở trên có thể nhận ngoại lệ unchecked trực tiếp.

## 8. Phân biệt với các ngoại lệ và lỗi gần giống

| Loại | Tình huống thường gặp | Dấu hiệu quan trọng |
| --- | --- | --- |
| `AnnotationTypeMismatchException` | Giá trị annotation lưu trong class file không còn khớp kiểu phần tử hiện tại | `element()` và `foundType()` |
| `IncompleteAnnotationException` | Phần tử mới không có giá trị được lưu và không có default | `annotationType()` và `elementName()` |
| `EnumConstantNotPresentException` | Giá trị enum trong annotation trỏ tới hằng không còn tồn tại | `enumType()` và `constantName()` |
| `TypeNotPresentException` | Không giải quyết được tên một kiểu, có thể khi đọc phần tử annotation kiểu `Class<?>` | `typeName()` và `getCause()` |
| `AnnotationFormatError` | Class file có metadata annotation sai định dạng hoặc không hợp lệ theo parser | Là **`Error`**, cần kiểm tra class file/tool sinh bytecode |
| `ClassCastException` | Ép object sai kiểu trong ứng dụng hoặc interceptor | Không mặc nhiên đồng nghĩa metadata annotation đã đổi |
| `InvocationTargetException` | Reflection `Method.invoke` bọc lỗi mà method được gọi ném | Kiểm tra `getCause()` trước khi kết luận |

Đừng bắt chung `RuntimeException` rồi bỏ qua annotation lỗi: framework có thể tiếp tục chạy với cấu hình thiếu hoặc sai. Trong một pipeline build, nên coi mismatch là lỗi tương thích phiên bản cần sửa. Việc bắt riêng các exception thường thích hợp ở lớp log/chẩn đoán hoặc nơi có hành vi fallback được xác định rõ.

## 9. Các bước khắc phục một cách có hệ thống

### 9.1. Xác nhận chính xác annotation đang được dùng

Từ stack trace và exception:

- `AnnotationTypeMismatchException.element()`: xác định tên phần tử, lớp khai báo và kiểu trả về hiện tại.
- `AnnotationTypeMismatchException.foundType()`: dùng như dữ liệu phụ để gợi ý kiểu cũ, không parse cứng cấu trúc chuỗi.
- `IncompleteAnnotationException.annotationType()` và `elementName()`: xác định type và phần tử mới bắt buộc.

Sau đó so sánh API annotation giữa **bản compile** và **bản runtime**, xem release notes hoặc thay đổi mã nguồn thật sự. Nếu annotation do bên thứ ba cung cấp, cần kiểm tra toàn bộ cây dependency.

### 9.2. Kiểm tra class file và classpath/module path

Dùng công cụ JDK:

~~~bash
javap -v -p -classpath out/old demo.Stored
javap -p -classpath out/new demo.State
javap -p -classpath out/new demo.Metadata
~~~

`javap -v` có thể hiển thị metadata annotation và tên phần tử ghi trong `RuntimeVisibleAnnotations`. Các lệnh trên minh họa thư mục của bài thực hành; trong hệ thống thực tế, thay bằng đường dẫn tới JAR/lớp đang chạy.

Kiểm tra **nhiều phiên bản JAR của cùng thư viện**, thứ tự classpath, classloader tùy biến, module path và các build artifact cũ. Tên package/class giống nhau không có nghĩa bytecode hoặc loader đang dùng giống nhau.

### 9.3. Chọn phương án sửa đúng với contract

- **Lỗi type mismatch:** khôi phục kiểu cũ để tương thích hoặc sửa source sử dụng annotation theo kiểu mới rồi **clean build và triển khai đồng bộ**.
- **Lỗi incomplete:** cập nhật mọi vị trí sử dụng annotation để cung cấp phần tử mới, hoặc thêm `default` khi giá trị mặc định có ý nghĩa hợp lý và bảo đảm tương thích.
- **Thư viện nhiều module:** đồng bộ version của annotation API với module đã biên dịch sử dụng nó; không trộn class cũ và class mới sau một lần nâng cấp.
- **Code generator và bytecode tool:** kiểm tra pipeline sinh mã, vì công cụ có thể ghi annotation payload thiếu/sai ngay cả khi source Java thông thường không cho phép.

**Không** giải quyết bằng việc đổi tên exception, ép kiểu kết quả, hoặc dùng `setAccessible(true)`. Đây là lỗi **hợp đồng dữ liệu annotation tại runtime**, không phải thiếu quyền đọc private member.

## 10. Thiết kế annotation để giảm rủi ro nâng cấp

Khi công bố một annotation dùng chung cho nhiều module/JAR:

1. Xem **tên và kiểu của element** như hợp đồng API và hợp đồng binary metadata. Đổi kiểu trả về, xóa/đổi tên element là thay đổi cần đánh giá ảnh hưởng.
2. Cân nhắc **`default` cho element mới** nếu có giá trị mặc định hợp lý. Đừng gán default tùy tiện nếu thiếu cấu hình có thể gây hành vi nguy hiểm hoặc âm thầm sai.
3. Thử nghiệm với **consumer artifact đã biên dịch bằng bản trước**: chạy bằng annotation API mới để phát hiện lỗi tương thích, ngoài kiểm tra compile source mới.
4. Với thay đổi breaking, sử dụng lộ trình nâng version, migration guide và dependency constraints/BOM để tránh trộn nhiều phiên bản.
5. Khi dùng Reflection, ghi log có ngữ cảnh (annotation type, element, origin artifact), rồi báo rõ lỗi tương thích; không dựa vào output `toString()` của annotation.
6. Nếu giá trị cần cấu trúc phức tạp và thay đổi thường xuyên, cân nhắc mô hình metadata có schema/version rõ ràng thay vì đẩy mọi cấu hình vào annotation.

## 11. Tự kiểm tra

1. Class `Stored` được biên dịch với `@State("READY")` khi `State.value()` trả `String`. Runtime đổi `value()` thành `int` nhưng không biên dịch lại `Stored`. Lỗi nào? **`AnnotationTypeMismatchException` khi đọc phần tử không khớp.**
2. Một element `owner()` được thêm mà không có `default`; class file cũ không chứa nó. Lỗi nào? **`IncompleteAnnotationException` khi truy cập `owner()`.**
3. Thêm `default "UNKNOWN"` cho `owner()` giúp trường hợp nào? **Phần tử bị thiếu**; không sửa dữ liệu sai kiểu đã tồn tại.
4. Vì sao `getAnnotation(...) != null` chưa chứng minh hợp đồng đúng? Vì lỗi có thể phát sinh **khi đọc element** của annotation đã được lấy.
5. Khi bắt `AnnotationTypeMismatchException`, API nào cho biết method có vấn đề? **`element()`**, trả về `Method`.
6. Với `IncompleteAnnotationException`, lấy annotation type và tên phần tử bị thiếu ở đâu? **`annotationType()`** và **`elementName()`**.
7. Tại sao source hiện tại compile được vẫn có lỗi runtime? Vì JVM có thể đang nạp **class file consumer cũ** cùng **annotation API mới**, hoặc dependency/classloader không đồng bộ.
8. `foundType()` có an toàn để viết parser phụ thuộc format không? **Không**; API không đặc tả định dạng chuỗi.

## 12. Tài liệu Java 17

- [Oracle Java 17 — AnnotationTypeMismatchException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/AnnotationTypeMismatchException.html)
- [Oracle Java 17 — IncompleteAnnotationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/IncompleteAnnotationException.html)
- [Oracle Java 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Oracle Java 17 — RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)

**Ghi nhớ:** `AnnotationTypeMismatchException` báo **giá trị cũ sai kiểu theo element hiện tại**; `IncompleteAnnotationException` báo **element bắt buộc mới bị thiếu**. Cả hai thường là triệu chứng class file và định nghĩa annotation khác phiên bản. Muốn sửa tận gốc, tìm class/JAR thực tế JVM đang nạp, đối chiếu API giữa các bản và đồng bộ lại cách biên dịch/triển khai.