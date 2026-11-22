# Strong encapsulation và nguyên nhân phát sinh `InaccessibleObjectException`

Khi chuyển ứng dụng Java từ JDK cũ sang JDK mới, một lỗi thường gặp là `java.lang.reflect.InaccessibleObjectException`. Ứng dụng có thể vẫn biên dịch, nhưng khi chạy thì một thư viện JSON, ORM, dependency injection, proxy, test framework hoặc mã reflection nội bộ cố truy cập một field, constructor hay method không được phép. Lỗi có thể chỉ xuất hiện ở một luồng nghiệp vụ hoặc khi framework khởi tạo một kiểu dữ liệu nhất định.

Nguyên nhân phổ biến là **strong encapsulation** (đóng gói mạnh) trong Java Platform Module System (JPMS). Trước đây một số đoạn mã có thể dùng reflection để vượt qua mức truy cập Java đối với các lớp nội bộ JDK; trên JDK hiện đại, ranh giới module được áp dụng chặt hơn. Đặc biệt, một package **không được mở cho deep reflection** thì lời gọi `setAccessible(true)` có thể thất bại, cho dù ứng dụng nhìn thấy lớp đó hoặc package của nó được export.

Bài học này giải thích cơ chế dẫn đến lỗi, cách đọc stack trace, cách phân biệt `exports` và `opens`, cách chẩn đoán trong migration Java, cách sử dụng `--add-opens` có kiểm soát và cách thiết kế giải pháp lâu dài không dựa vào quyền truy cập nội bộ không ổn định.

## 1. Reflection thường làm gì?

Reflection cho phép chương trình xem metadata của class, field, method, constructor và trong những điều kiện cho phép, thực thi hoặc truy cập thành phần đó lúc runtime.

Ví dụ một lớp đơn giản:

~~~java
package com.example.model;

public class Customer {
    private final String customerId;

    public Customer(String customerId) {
        this.customerId = customerId;
    }

    public String getCustomerId() {
        return customerId;
    }
}
~~~

Code bình thường nên gọi API công khai:

~~~java
Customer customer = new Customer("C-42");
String id = customer.getCustomerId();
~~~

Nhưng một framework có thể tìm field `customerId` bằng reflection:

~~~java
import java.lang.reflect.Field;

Field field = Customer.class.getDeclaredField("customerId");
field.setAccessible(true);

String id = (String) field.get(customer);
~~~

`getDeclaredField` chỉ **tìm và trả về metadata** của field được khai báo; nó không tự cấp quyền đọc giá trị private. `setAccessible(true)` yêu cầu bỏ qua kiểm tra truy cập ngôn ngữ Java thông thường, trong phạm vi các ràng buộc mà runtime cho phép.

Trong một classpath ứng dụng thông thường, nhiều class của ứng dụng cùng thuộc unnamed module, nên deep reflection vào class của chính ứng dụng có thể vẫn hoạt động. Vấn đề trở nên rõ hơn khi mã dùng reflection đụng tới **class ở module khác**, đặc biệt package nội bộ trong những module JDK như `java.base`.

## 2. Strong encapsulation trong JPMS là gì?

JPMS được đưa vào Java 9. Nó tổ chức code thành các module có khai báo dependency và kiểm soát package nào được xuất ra để sử dụng hoặc mở cho reflection. Không chỉ mức truy cập `public`, `protected`, package-private và `private` quan trọng; **ranh giới module** cũng tham gia quyết định quyền truy cập.

Một module có thể chứa:

- **Exported package:** package được khai báo `exports` cho module khác dùng các public type và public/protected member theo quy tắc Java.
- **Opened package:** package được khai báo `opens` cho phép deep reflection theo quy tắc JPMS, kể cả việc yêu cầu truy cập member không public.
- **Concealed package:** package không được export hoặc open cho consumer tương ứng, nên không thể sử dụng như API công khai hoặc thực hiện deep reflection tùy ý.
- **Qualified export/open:** package chỉ export hoặc open cho những module được liệt kê, không cho mọi module.

Strong encapsulation là việc thực thi ranh giới này để code bên ngoài không mặc nhiên truy cập implementation detail của module, kể cả bằng `setAccessible(true)`.

Mục tiêu là giảm phụ thuộc vào API nội bộ, tăng khả năng bảo trì và bảo mật của JDK, đồng thời làm hợp đồng truy cập giữa các module rõ ràng hơn. Đây không phải một lỗi ngẫu nhiên của JVM: nhiều trường hợp bị chặn chính là kết quả của chính sách đóng gói đã được thiết kế.

## 3. `exports` không đồng nghĩa với `opens`

Hai từ khóa quan trọng trong `module-info.java` có phạm vi khác nhau:

| Khai báo | Truy cập mã nguồn thông thường | Deep reflection vào private member | Khi nào dùng |
|---|---|---|---|
| `exports p;` | Cho phép module khác truy cập public API của package `p` | Không tự cho phép | Công bố API Java để consumer compile và gọi |
| `opens p;` | Không tự cấp quyền compile-time tương đương `exports` | Cho phép reflection ở runtime theo quy tắc JPMS | Cho serializer/DI/ORM đọc hoặc ghi member qua reflection |
| `exports p to m;` | Chỉ export cho module `m` | Không tự cho phép | API dùng nội bộ giữa module đã chỉ định |
| `opens p to m;` | Không tự export cho mọi caller | Chỉ mở deep reflection cho module `m` | Mở tối thiểu cho framework cụ thể |
| Không khai báo | Không export/open mặc định | Không cho deep reflection từ module khác theo cơ chế thông thường | Giữ package làm implementation detail |

Ví dụ module ứng dụng:

~~~java
module com.example.customer {
    exports com.example.customer.api;

    // Chỉ module serializer được phép deep-reflect vào DTO.
    opens com.example.customer.dto to com.example.serializer;
}
~~~

Trong ví dụ, `com.example.serializer` là một module giả định. Với framework thật, phải dùng **đúng module name** của framework ở module path; tên artifact Maven không nhất thiết là module name.

Khai báo `exports` không có nghĩa public class bên trong có thể bị đọc private field bằng reflection. Một framework cần truy cập private field của package ở module khác thường cần package được `opens` hoặc cấu hình runtime có tác dụng tương đương.

### 3.1. Mở package và mở toàn bộ module

Ngoài `opens p;`, JPMS có cú pháp:

~~~java
open module com.example.customer {
    requires com.example.serializer;
}
~~~

`open module` mở tất cả các package của module cho deep reflection tại runtime. Đây là lựa chọn có phạm vi rộng và có thể làm mất lợi ích đóng gói. Khi có thể, ưu tiên `opens package to framework.module;` nhằm giới hạn quyền truy cập.

Một `open module` không đồng nghĩa với việc tất cả package đều tự trở thành API được export cho compile-time. Mục đích của open là truy cập phản chiếu, không phải thay thế hợp đồng API công khai.

## 4. `InaccessibleObjectException` được phát sinh khi nào?

`java.lang.reflect.InaccessibleObjectException` là một unchecked exception, thuộc nhánh `RuntimeException`, được giới thiệu từ Java 9. Nó thường xuất hiện khi chương trình yêu cầu tắt kiểm tra truy cập reflection nhưng runtime không thể cho phép yêu cầu đó.

Một trường hợp điển hình:

1. Framework hoặc ứng dụng tìm member qua `getDeclaredField`, `getDeclaredMethod` hoặc `getDeclaredConstructor`.
2. Code gọi `setAccessible(true)` hoặc API tương đương để truy cập sâu hơn.
3. Member nằm trong package của một module khác chưa mở cho module gọi.
4. JVM từ chối bật accessibility suppression và ném `InaccessibleObjectException`.

Lỗi có thể xuất hiện lúc framework khởi tạo serializer, ánh xạ entity, quét field, tạo proxy hoặc xử lý một object lần đầu. Nó không nhất thiết xuất hiện ngay khi ứng dụng khởi động.

Không phải mọi lời gọi reflection đều lỗi. Chẳng hạn, tìm và gọi một public method trong một public class ở package đã được export cho module gọi thường có thể hoạt động mà không cần mở package cho deep reflection. Lỗi chủ yếu liên quan đến phạm vi truy cập vượt quá quyền đã được cấp.

## 5. Ví dụ tối giản tái hiện lỗi trên JDK 17+

Đoạn mã sau tìm private field tên `value` của `java.lang.String` rồi cố tắt kiểm tra truy cập. Đây chỉ là ví dụ chẩn đoán; không nên dựa vào cấu trúc nội bộ của String trong ứng dụng thực tế.

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");

        try {
            field.setAccessible(true);
            System.out.println("Reflective access granted");
        } catch (InaccessibleObjectException exception) {
            System.err.println("Deep reflection was denied:");
            exception.printStackTrace();
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac ReflectionProbe.java
java ReflectionProbe
~~~

Một thông báo điển hình có dạng:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final byte[] java.lang.String.value accessible:
  module java.base does not "opens java.lang" to unnamed module @...
~~~

Đây là **dạng lỗi minh họa**, không phải output bắt buộc giống tuyệt đối ở mọi JDK. Kiểu của field `String.value` là chi tiết implementation và đã thay đổi trong lịch sử Java; chính điều đó cũng cho thấy vì sao không nên phụ thuộc vào private field của JDK.

Điểm cần đọc là: **module `java.base` không mở package `java.lang` cho caller thuộc unnamed module**. Trước khi gọi `setAccessible(true)`, `getDeclaredField` có thể vẫn tìm thấy metadata của field; chính yêu cầu vượt ranh giới truy cập bị từ chối.

### 5.1. Trường hợp `trySetAccessible()`

Từ Java 9, `AccessibleObject.trySetAccessible()` cung cấp cách thử bật quyền truy cập và trả về `boolean`. Khi không thể cấp quyền do ranh giới module, nó thường trả về `false` thay vì ném `InaccessibleObjectException` như `setAccessible(true)`.

~~~java
Field field = String.class.getDeclaredField("value");

if (!field.trySetAccessible()) {
    System.out.println("Package is not open for deep reflection");
}
~~~

Không nên xem việc chuyển từ `setAccessible` sang `trySetAccessible` là cách vượt quyền. Nó chỉ cho phép code kiểm tra khả năng truy cập và chọn đường xử lý khác khi không được phép.

## 6. Cách đọc stack trace để tìm nguyên nhân chính xác

Ví dụ thông báo:

~~~text
Unable to make field private java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module @5e2de80c
~~~

Có thể tách thành những phần:

| Thành phần | Cách hiểu |
|---|---|
| `field private ... String.value` | Member mà framework muốn truy cập |
| `module java.base` | Module chứa member |
| `does not "opens java.lang"` | Package chưa được mở cho deep reflection |
| `unnamed module @...` | Caller nằm trên classpath, không phải một named module JPMS trong trường hợp này |
| Stack frame gần `setAccessible` | Thường cho biết framework/thư viện nào trực tiếp đưa ra yêu cầu |

Thông báo khác có thể ghi:

~~~text
module com.example.model does not "opens com.example.model.dto"
to module com.example.serializer
~~~

Ở đây nguồn không phải JDK: đó là **module của chính ứng dụng** chưa mở package DTO cho module serializer. Giải pháp bền vững có thể là chỉnh `module-info.java` của module ứng dụng hoặc đổi chiến lược serialize, thay vì thêm cờ mở `java.base`.

### 6.1. Tìm caller thực sự

Stack trace có thể đi qua nhiều lớp: service → mapper → thư viện reflection → `AccessibleObject`. Cần phân biệt:

- **Module sở hữu member bị từ chối:** thường xuất hiện trong thông báo lỗi.
- **Module của code yêu cầu truy cập:** có thể là framework, plugin hoặc application.
- **Dependency đem vào code reflection:** xác định từ stack trace, dependency graph hoặc class loading.
- **Đường nghiệp vụ kích hoạt lỗi:** batch, endpoint, startup scanner hoặc test cụ thể.

Không nên chỉ nhìn lớp đầu tiên trong stack trace và sửa nhầm API của ứng dụng. Việc nắm đúng **nguồn member** và **module cần quyền truy cập** quyết định hướng sửa.

## 7. Phân biệt với `IllegalAccessException`, `IllegalAccessError` và lỗi khác

Nhiều lỗi truy cập có tên gần nhau nhưng xảy ra ở những cơ chế khác nhau:

| Dấu hiệu | Bối cảnh điển hình | Hướng điều tra |
|---|---|---|
| `InaccessibleObjectException` | `setAccessible(true)` muốn bỏ qua access check nhưng module không mở package | Kiểm tra `opens`, `--add-opens`, member và framework |
| `IllegalAccessException` | Reflection `Field.get`, `Method.invoke` hoặc tương tự không có quyền truy cập cần thiết | Kiểm tra member visibility và accessible state |
| `IllegalAccessError` | JVM linkage/access check tại bytecode gặp truy cập không hợp lệ, như package không export cho caller | Kiểm tra classpath/module path và `exports` |
| `NoSuchFieldException` | Reflection tìm field không tồn tại với tên đã chỉ định | Kiểm tra tên member và khác biệt JDK/library |
| `NoSuchMethodException` | Reflection không tìm thấy method/constructor theo kiểu tham số | Kiểm tra signature, overload và version |
| `NoClassDefFoundError` | Một class được tham chiếu không thể tải/định nghĩa đúng lúc runtime | Kiểm tra dependency, Java version và class loading |

`IllegalAccessException` là checked exception; `InaccessibleObjectException` là unchecked exception. Một khối `catch (ReflectiveOperationException e)` không bắt `InaccessibleObjectException` vì exception này không thuộc nhánh đó.

Đừng coi mọi lỗi access là “chỉ cần --add-opens”. Nếu đang gọi API theo đường bytecode thông thường ở package không export, cần xem `--add-exports` hoặc thiết kế API công khai. Nếu member không tồn tại, mở package không tạo ra member đó.

## 8. Diễn tiến từ Java 9 đến Java 17 và về sau

Khi tìm nguyên nhân migration, cần biết strong encapsulation không xuất hiện bất ngờ trong một patch release:

### 8.1. Trước Java 9

Ứng dụng có thể dùng reflection với nhiều thành phần JDK theo các quy tắc truy cập lúc đó. Một số thư viện đã quen với việc đọc private field hoặc gọi method nội bộ. Những chỗ dựa vào implementation detail vẫn có rủi ro, dù trước đó chạy được.

### 8.2. Java 9: JPMS và giai đoạn chuyển tiếp

Java 9 bổ sung module boundary. Để giảm tác động tới hệ sinh thái, một số package JDK tồn tại từ JDK 8 được cho phép reflective access trong chế độ **relaxed strong encapsulation** đối với code từ classpath/unnamed module. Runtime có thể phát cảnh báo “illegal reflective access”.

Điều đó không có nghĩa mọi package nội bộ đều được mở, hoặc mọi named module đều có cùng quyền. Nhiều package mới hoặc bị đóng gói có thể bị từ chối ngay.

### 8.3. Java 16: chuyển mặc định sang strong encapsulation

JEP 396 làm strong encapsulation trở thành mặc định trong Java 16 đối với phần lớn internal API của JDK, với cơ chế chuyển tiếp có giới hạn qua một số tùy chọn trong giai đoạn đó. Những ứng dụng từng chỉ nhận warning trên JDK cũ có thể bắt đầu thất bại.

### 8.4. Java 17: không còn cơ chế nới lỏng toàn cục kiểu cũ

JEP 403 tiếp tục đóng gói mạnh những phần nội bộ JDK, loại bỏ khả năng dùng `--illegal-access` để khôi phục việc mở rộng toàn cục như giai đoạn trước. Tùy chọn này đã trở nên obsolete và không được dùng như giải pháp migration trên JDK 17 trở lên.

Các tùy chọn có phạm vi như `--add-opens` vẫn có thể được dùng trong những trường hợp cho phép để mở **một package cụ thể cho một target cụ thể**. Đây là biện pháp chuyển tiếp, không phải lời cam kết rằng private API sẽ ổn định.

### 8.5. Ngoại lệ đối với một số critical internal API

Một số API như `sun.misc.Unsafe` được duy trì qua module `jdk.unsupported` trong nhiều JDK hiện đại để hỗ trợ tương thích thư viện. Nhưng sự tồn tại của API trong một module đặc biệt không biến nó thành API Java SE được hỗ trợ ổn định. Cần xem tài liệu và chính sách cụ thể của phiên bản đích.

## 9. Classpath, module path và module gọi khác nhau thế nào?

Một ứng dụng có thể không có `module-info.java` nhưng vẫn chịu tác động bởi ranh giới module của JDK. Code trên **classpath** thường thuộc **unnamed module** và khi muốn deep-reflect vào một package trong `java.base`, package đó vẫn phải được mở cho unnamed module.

Với **module path**, code có thể nằm trong named module có tên riêng. Lúc đó thông báo lỗi chỉ rõ module gọi và có thể yêu cầu opening tới tên module đó, không phải `ALL-UNNAMED`.

Ví dụ một ứng dụng chạy trên classpath:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

Từ chối deep reflection vào `java.base/java.lang` có thể ghi `to unnamed module`.

Ví dụ một named module:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

Khi module `com.example.app` yêu cầu deep reflection vào package chưa mở, thông báo có thể ghi `to module com.example.app`.

Với thư viện tự động chuyển thành **automatic module** khi đặt trên module path, module name có thể được xác định từ metadata hoặc tên JAR. Không nên đoán tên module từ tọa độ Maven: có thể xem mô tả artifact với:

~~~bash
jar --describe-module --file dependency.jar
~~~

Tên module là thông tin cần thiết khi dùng qualified `opens` hoặc `--add-opens` có target cụ thể.

## 10. `--add-opens`: cấu hình tạm thời để kiểm chứng

Khi thật sự cần deep reflection, Java launcher có tùy chọn:

~~~text
--add-opens=<source-module>/<package>=<target-module>
~~~

Nó yêu cầu runtime mở package được chỉ định của source module cho target module, ngoài những gì được khai báo trong module descriptor. Khi target là code trên classpath, có thể dùng token `ALL-UNNAMED`.

Ví dụ với ReflectionProbe:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED ReflectionProbe
~~~

Lúc đó, `setAccessible(true)` trên field trong package được mở có thể thành công. **Điều này chỉ cho phép thử truy cập; nó không biến private field của String thành API ổn định.** Cấu trúc nội bộ vẫn có thể thay đổi giữa các JDK.

Khi caller là named module, sử dụng tên module:

~~~bash
java --add-opens=java.base/java.lang=com.example.app \
  --module-path mods \
  --module com.example.app/com.example.Main
~~~

Đây là ví dụ cú pháp. Chỉ định target thực tế xuất hiện trong thông báo lỗi. Không nên sao chép nguyên `com.example.app` hoặc `ALL-UNNAMED` nếu ứng dụng thực tế có cấu trúc module khác.

### 10.1. Sự khác nhau giữa `--add-opens` và `--add-exports`

| Tùy chọn | Mục tiêu | Có giải quyết private reflection không? |
|---|---|---|
| `--add-opens=module/package=target` | Mở package cho deep reflection ở runtime | Có thể, trong đúng phạm vi được mở |
| `--add-exports=module/package=target` | Cho phép target truy cập public type/member của package không export qua cơ chế module | Không tự cho quyền truy cập private member |

Ví dụ, khi ứng dụng gọi một public class trong package JDK không export trực tiếp qua bytecode, `--add-exports` có thể liên quan đến quá trình compile/runtime trong trường hợp cần thiết. Nhưng nếu reflection dùng `setAccessible(true)` trên field private, chỉ `--add-exports` thường không giải quyết được vấn đề.

Tương tự, `--add-opens` không có nghĩa compiler sẽ cho import mọi class ở package nội bộ: mục tiêu của nó là **runtime reflective access**.

### 10.2. Vì sao không nên thêm cờ một cách tràn lan?

Mỗi cờ `--add-opens` làm mở rộng quyền truy cập theo cấu hình, đồng thời tạo thêm ràng buộc vào cấu trúc module JDK:

- Package hoặc member có thể đổi tên hay bị xóa trong JDK sau.
- Biện pháp chỉ xử lý một quyền truy cập; còn lỗi khác vẫn có thể phát sinh.
- Cờ phải được duy trì ở test, batch, worker, service, container và production.
- Tên module/target có thể khác khi thư viện chuyển từ classpath sang module path.
- Nó có thể che khuất nhu cầu nâng cấp dependency hoặc sửa API.
- Mở rộng quyền truy cập vào implementation detail có thể làm tăng diện tích rủi ro bảo mật và bảo trì.

Nên coi `--add-opens` như **cầu nối migration** có owner, lý do, phạm vi và thời hạn đánh giá lại, không phải lựa chọn mặc định.

## 11. Cấu hình trong Gradle, test và môi trường triển khai

Khi lỗi chỉ xuất hiện trong unit/integration test, cần đưa VM argument vào JVM **chạy test**, không phải chỉ thêm nó vào compiler arguments.

Ví dụ Gradle Kotlin DSL:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

Nếu chạy ứng dụng qua `JavaExec`, task đó có thể cần cấu hình riêng:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

Hai ví dụ trên chỉ dành cho tình huống cần mở đúng package này. Với dự án thật, lấy source module/package và target từ stack trace, không thêm `java.base/java.lang` theo quán tính.

Một số điểm quan trọng:

- `JavaCompile`, Gradle daemon, test worker và JVM chạy ứng dụng có thể là các tiến trình khác nhau.
- `--add-opens` cần có hiệu lực trên **JVM phát sinh lỗi**.
- Nếu framework chạy trong container hoặc application server, cấu hình test local không tự chuyển tới deployment.
- Nếu có nhiều service hoặc nhiều entrypoint, phải kiểm tra từng launch configuration.
- Không đưa cờ vào artifact JAR rồi giả định mọi Java launcher sẽ áp dụng.
- Nếu dự án dùng module path, target của cờ có thể là named module thay vì `ALL-UNNAMED`.

### 11.1. Cấu hình trong container

Ví dụ khởi động ứng dụng qua Docker entrypoint:

~~~dockerfile
ENTRYPOINT [
  "java",
  "--add-opens=java.base/java.lang=ALL-UNNAMED",
  "-jar",
  "/app/app.jar"
]
~~~

Đây là minh họa cho một workaround; không nên dùng chung cho mọi ứng dụng. Khi triển khai thực tế, cần theo dõi image JDK, các VM arguments, phiên bản framework và kế hoạch xóa cờ sau khi đã nâng cấp dependency hoặc sửa thiết kế.

### 11.2. Vì sao local chạy được mà production lỗi?

Các môi trường có thể khác:

- Local dùng JDK 11 với cơ chế chuyển tiếp; production dùng JDK 17.
- Test chạy trên classpath, production chạy trên module path.
- Test có JVM argument, service launcher production thiếu.
- Artifact/shaded JAR khác nhau về dependency framework.
- Reflection chỉ được kích hoạt với một loại DTO hoặc plugin có trong production.
- Container dùng JDK distribution hoặc image khác baseline được kiểm thử.

Do đó, trước khi kết luận nguyên nhân là “lỗi Java 17”, hãy lưu phiên bản Java thực, command line JVM, danh sách dependency, module path và stack trace đầy đủ của tiến trình gặp sự cố.

## 12. Thay workaround bằng phương án ổn định hơn

Giải pháp lâu dài thường là **không truy cập private API của JDK** hoặc **mở package của chính ứng dụng có chủ đích cho framework cần thiết**.

### 12.1. Dùng API công khai thay cho private field JDK

Nếu code đang đọc `String.value` để lấy byte bên trong String, nên dùng API công khai và chọn encoding rõ ràng:

~~~java
import java.nio.charset.StandardCharsets;

String text = "xin chào";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

`getBytes` có ngữ nghĩa công khai và ổn định hơn so với phụ thuộc layout của private field. Cách thay này có thể tạo bản sao dữ liệu, nhưng tránh ràng buộc vào cấu trúc nội bộ và cần được đánh giá theo hiệu năng thực tế.

Tương tự, nên ưu tiên API `java.nio`, `java.time`, `java.util`, `java.lang.invoke` hoặc API được hỗ trợ khác khi chúng đáp ứng nhu cầu, thay vì dùng package `sun.*` hoặc `jdk.internal.*`.

### 12.2. Chuyển deep reflection thành API rõ ràng

Framework hoặc thư viện có thể được cấu hình để sử dụng:

- Constructor công khai với tham số rõ ràng.
- Getter/setter công khai hoặc package-level adapter được kiểm soát.
- DTO/record theo baseline Java phù hợp và API công khai của framework.
- Annotation hoặc metadata có mục đích rõ ràng thay vì tự quét mọi private field.
- Plugin/extension point chính thức thay vì truy cập implementation class.

Khi loại bỏ deep reflection, cần kiểm tra semantics cũ, ví dụ có còn hỗ trợ field private không có setter, final field, inheritance, proxy và dữ liệu lịch sử hay không.

### 12.3. Mở package thuộc module ứng dụng theo nguyên tắc tối thiểu

Nếu ứng dụng chủ động dùng framework cần reflection vào DTO của mình, có thể khai báo trong `module-info.java`:

~~~java
module com.example.customer {
    requires com.example.serializer;

    exports com.example.customer.api;
    opens com.example.customer.dto to com.example.serializer;
}
~~~

Đây là một quyết định hỗ trợ framework cụ thể chứ không phải mở JDK internal. Nếu serializer thay đổi module name hoặc dùng reflection từ module khác, cần điều chỉnh đúng target đã quan sát.

Nếu ứng dụng vẫn nằm trên classpath không có module-info, việc dùng `opens` trong module descriptor chưa phải một bước áp dụng được ngay. Lúc đó có thể sửa chiến lược serialization/DI, nâng cấp framework hoặc chuẩn bị modularization theo kế hoạch riêng.

### 12.4. Không nhầm MethodHandles với đường vượt JPMS

`MethodHandles.Lookup`, `MethodHandles.privateLookupIn` và `VarHandle` là API Java được hỗ trợ cho nhiều use case động. Tuy nhiên, chúng **không mặc nhiên vượt được ranh giới module**. Chẳng hạn, `privateLookupIn` đối với class trong module khác vẫn đòi các điều kiện quyền truy cập phù hợp, trong đó có package openness khi áp dụng.

Chuyển từ reflection sang method handle chỉ để tránh một lỗi `InaccessibleObjectException` mà không thay đổi quyền truy cập hoặc thiết kế API thường không giải quyết gốc rễ.

### 12.5. Nâng cấp dependency đang dùng reflection nội bộ

Khi lỗi xuất phát từ thư viện bên thứ ba, các bước thường phù hợp:

1. Xác định dependency và phiên bản thực tế trong stack trace/dependency graph.
2. Kiểm tra phiên bản thư viện mới có tuyên bố hỗ trợ JDK mục tiêu không.
3. Đọc migration guide hoặc issue liên quan tới strong encapsulation.
4. Nâng cấp hoặc thay thư viện khi có bản dùng API công khai.
5. Chạy test lại trên JDK, framework và dependency graph mục tiêu.
6. Chỉ giữ `--add-opens` nếu chưa có lựa chọn khả thi và đã quản lý rủi ro.

Không nên vội ghi đè cấu hình module của cả ứng dụng khi nguyên nhân thực tế là một bản framework đã cũ và có bản sửa được hỗ trợ.

## 13. Kiểm kê API nội bộ và đường reflection

`jdeps` là một công cụ được JDK cung cấp để phân tích dependency tĩnh. Tùy chọn `--jdk-internals` giúp tìm các tham chiếu trong bytecode tới những API nội bộ của JDK mà công cụ nhận diện:

~~~bash
jdeps --jdk-internals app.jar
~~~

Với dependency trên classpath:

~~~bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" \
  app.jar
~~~

Lệnh có thể giúp tìm lớp thư viện đang dùng API JDK nội bộ. Tuy nhiên, **jdeps không phát hiện đầy đủ reflection động bằng tên chuỗi** hoặc class được tải sau này. Ví dụ:

~~~java
Class<?> type = Class.forName("java.lang.String");
Field valueField = type.getDeclaredField("value");
valueField.setAccessible(true);
~~~

Tên class/field nằm trong string và đường truy cập xảy ra tại runtime. Không thể kết luận không có rủi ro chỉ vì `jdeps` không tìm thấy tham chiếu tĩnh tương ứng.

Cần kết hợp:

| Kỹ thuật | Vai trò |
|---|---|
| Stack trace `InaccessibleObjectException` | Nêu source module/package và target của yêu cầu bị từ chối |
| Dependency graph | Xác định phiên bản thư viện/framework tạo reflection |
| `jdeps --jdk-internals` | Tìm tham chiếu tĩnh tới API nội bộ được công cụ nhận diện |
| Source search | Tìm `setAccessible`, `trySetAccessible`, `Class.forName` và tên package nội bộ |
| Test trên JDK mục tiêu | Kích hoạt code path thực sự có reflection |
| Module metadata | Xem exports, opens, module names và module path |
| Runtime logs | Ghi lại JVM args, class loading và lỗi khi chạy trong môi trường đại diện |

Chú ý: tìm kiếm source có thể không phát hiện code nằm trong JAR dependency; quét binary và inventory dependency vẫn cần thiết.

## 14. Quy trình xử lý một sự cố thực tế

Có thể thực hiện theo trình tự sau để tránh thêm cờ JVM một cách tùy tiện.

### Bước 1: Thu thập toàn bộ thông báo lỗi

Giữ nguyên stack trace, phần `Caused by` và dòng có cụm `does not "opens"`. Ghi source module/package, caller module và member bị chặn.

### Bước 2: Xác định sự kiện và môi trường

Ghi request, job, startup action hoặc test đã kích hoạt lỗi. Xác nhận version JDK, vendor/build, Java launcher, OS, classpath/module path và JVM args.

### Bước 3: Tìm mã hoặc thư viện yêu cầu deep reflection

Đọc stack trace để tìm class gần lời gọi `setAccessible`. Xác định dependency, phiên bản và thành phần chịu trách nhiệm. Nếu là mã thuộc dự án, xem có thể thay bằng API công khai không.

### Bước 4: Phân loại package bị truy cập

Xác định package thuộc:

- JDK internal hoặc JDK implementation detail;
- Module ứng dụng do nhóm sở hữu;
- Thư viện/framework bên ngoài;
- Package được export nhưng chưa mở;
- Package hoàn toàn concealed.

Phân loại đúng giúp chọn giải pháp. Mở package ứng dụng cho serializer khác với truy cập private field của `java.lang.String`.

### Bước 5: Chọn biện pháp sửa gốc

Ưu tiên sửa code, API, dependency hoặc module descriptor. Nếu package thuộc module ứng dụng, có thể dùng qualified `opens`. Nếu là private JDK internal, tìm public API thay thế hoặc version thư viện mới.

### Bước 6: Dùng workaround hẹp nếu thật sự cần

Chỉ khi chưa thể sửa gốc, dùng `--add-opens=source.module/package=target.module` đúng từ lỗi. Tài liệu hóa vì sao cần, ai sở hữu, môi trường áp dụng và khi nào kiểm tra bỏ.

### Bước 7: Xác nhận bằng runtime test

Chạy lại cùng luồng thao tác trên JDK mục tiêu. Đánh giá cả khởi động, đường xử lý dữ liệu, serialization, proxy, integration test và luồng lỗi. Nếu cờ chỉ được thêm cho test, phải lặp lại trong môi trường thực sự triển khai.

### Bước 8: Lưu bằng chứng migration

Lưu command line JVM, version JDK, log lỗi trước, kết quả sau, dependency version, test report, phạm vi test và các exception chưa xử lý. Khi lỗi tái xuất hiện trên JDK mới hơn, hồ sơ này giúp phân biệt regression với dependency cũ.

## 15. Ví dụ điều tra framework JSON

Giả sử ứng dụng có DTO trong named module:

~~~java
package com.example.customer.dto;

public final class CustomerDto {
    private String id;

    public CustomerDto() {}

    public String getId() {
        return id;
    }
}
~~~

Một framework mapper có thể dùng reflection đọc/ghi private field `id`. Nếu package DTO không mở cho module của mapper, quá trình deserialize có thể thất bại với `InaccessibleObjectException`.

Có ba hướng:

**Hướng A — dùng public API:** cấu hình mapper để gọi public constructor/getter/setter hoặc các cơ chế hỗ trợ public của framework, tùy phiên bản và kiểu DTO.

**Hướng B — mở package có kiểm soát:** dùng `opens com.example.customer.dto to com.example.mapper;` trong module descriptor của ứng dụng khi đó là module thực sự yêu cầu reflective access.

**Hướng C — cập nhật framework hoặc chiến lược DTO:** nếu framework cũ cố reflective access không cần thiết, nâng cấp lên phiên bản tương thích JDK/JPMS, hoặc chuyển sang loại DTO mà framework xử lý bằng API công khai.

Mở `java.base/java.lang` không giải quyết việc package `com.example.customer.dto` không mở. Phải đọc **đúng package trong exception**, tránh đoán cờ theo ví dụ trên Internet.

## 16. Trường hợp Gradle/Maven/test framework dùng JDK nội bộ

Khi nâng Java, một plugin build hoặc test framework có thể chạy trên JDK khác với JDK chạy ứng dụng. Lỗi strong encapsulation có thể phát sinh ở:

- Gradle daemon hoặc Maven process;
- Worker JVM chạy test;
- Annotation processor hoặc code generator;
- Java agent/instrumentation;
- Ứng dụng runtime hoặc container;
- IDE plugin chạy trên JDK riêng.

Nếu lỗi đến từ daemon/build tool, JVM argument thêm vào test task sẽ không có tác dụng cho daemon. Ngược lại, cờ cấp cho daemon không bảo đảm được truyền tới forked test JVM.

Trước khi sửa, xác định **tiến trình JVM phát sinh lỗi** bằng log và công cụ build. Sau đó ưu tiên nâng phiên bản build tool/plugin tương thích JDK mục tiêu. Dùng cờ mở package chỉ khi cần cho một giai đoạn chuyển tiếp có quản lý.

Một thông báo `InaccessibleObjectException` do thư viện test cũ gây ra không đồng nghĩa Java business logic của ứng dụng sai. Nhưng nó vẫn là một rào cản migration cần giải quyết trong toolchain.

## 17. Rủi ro về bảo mật và ổn định khi mở quyền rộng

Strong encapsulation không phải cơ chế bảo vệ bí mật tuyệt đối giữa mọi code trong cùng một tiến trình; một hệ thống Java vẫn cần mô hình bảo mật toàn diện ở mức quyền vận hành, dependency và dữ liệu. Tuy nhiên, mở package bằng cờ rộng tạo thêm khả năng truy cập nội bộ cho các thành phần được target.

Vì thế:

- Chỉ mở **package cần thiết**, không mở hàng loạt các package JDK theo danh sách sao chép thiếu kiểm chứng.
- Hạn chế target ở **named module** cụ thể nếu có thể, thay vì `ALL-UNNAMED` cho mọi thành phần classpath.
- Đừng dùng quyền truy cập được mở như một API mới cho business logic.
- Rà soát dependency/agent chưa được tin cậy trước khi mở sâu các package nhạy cảm.
- Theo dõi lỗi sau khi nâng JDK; cấu trúc nội bộ có thể thay đổi ngay cả khi cờ vẫn được chấp nhận.
- Đặt owner và điều kiện loại bỏ workaround, tránh tích lũy cấu hình không còn cần thiết.

Tác động quan trọng nhất đối với migration là **khả năng bảo trì**: ứng dụng phụ thuộc private field/method của JDK sẽ chịu rủi ro khi JDK đổi implementation.

## 18. Những hiểu lầm thường gặp

**“Lớp public nên reflection vào private field luôn được.”** Public class có thể được sử dụng theo API công khai, nhưng không đồng nghĩa package đã mở cho deep reflection.

**“`exports` và `opens` giống nhau.”** `exports` hỗ trợ public API accessibility; `opens` phục vụ deep reflection. Chọn sai cơ chế sẽ không xử lý đúng lỗi.

**“Ứng dụng không có `module-info.java` thì không bị JPMS ảnh hưởng.”** Code trên classpath thuộc unnamed module và vẫn bị module boundary của JDK giới hạn khi truy cập nội bộ.

**“Thêm `--add-exports` sẽ sửa mọi `InaccessibleObjectException`.”** Với private reflection, vấn đề thường là thiếu `opens`. `--add-exports` không tự mở member private.

**“`--add-opens` giải quyết triệt để migration.”** Cờ có thể mở quyền trong một môi trường, nhưng không đảm bảo private member còn tồn tại hay giữ cùng kiểu/hành vi ở JDK kế tiếp.

**“Chuyển sang MethodHandles sẽ vượt giới hạn module.”** Các API method handle cũng tôn trọng điều kiện truy cập của module và không phải cửa hậu chung.

**“JDK 17 chỉ cần bật `--illegal-access=permit` như JDK cũ.”** Cơ chế nới lỏng toàn cục này không còn tác dụng khôi phục truy cập như thời kỳ chuyển tiếp trước JDK 17.

**“`jdeps` không thấy internal API thì chắc chắn không còn reflection trái phép.”** Reflection từ tên chuỗi, JNI, proxy động hoặc class tải thêm có thể nằm ngoài phạm vi phân tích tĩnh.

**“Mở `java.lang` giải quyết mọi lỗi serializer.”** Phải xác định source module/package thực sự từ thông báo, có thể lỗi nằm trong DTO module riêng.

**“Chỉ cần test startup.”** Reflection có thể được thực thi lần đầu khi request, batch, serializer hoặc plugin chạy; kiểm tra phải kích hoạt đúng đường lỗi.

## 19. Checklist khi nâng cấp Java có reflection

- [ ] Đã xác định JDK hiện tại, JDK mục tiêu, distribution, OS và tiến trình JVM gây lỗi.
- [ ] Đã lưu stack trace đầy đủ, bao gồm source module/package và target module.
- [ ] Đã biết framework/dependency hoặc mã dự án đang gọi `setAccessible`.
- [ ] Đã phân biệt access theo `exports` với deep reflection theo `opens`.
- [ ] Đã xác định caller nằm ở unnamed module hay named module.
- [ ] Đã kiểm tra API public thay thế hoặc phiên bản framework hỗ trợ JDK mới.
- [ ] Nếu package thuộc module ứng dụng, đã xem xét qualified `opens`.
- [ ] Nếu dùng `--add-opens` tạm thời, đã giới hạn source/target và ghi rõ owner.
- [ ] Đã xác nhận cờ được áp dụng đúng JVM gây lỗi, kể cả test và production nếu cần.
- [ ] Đã kiểm tra runtime code path kích hoạt serialization, ORM, proxy, plugin hoặc reflection.
- [ ] Đã kết hợp static analysis, dependency inventory và integration test.
- [ ] Đã lưu bằng chứng trước/sau, cảnh báo còn lại và kế hoạch loại bỏ workaround.

## Kết luận

`InaccessibleObjectException` thường xuất hiện vì code cố thực hiện **deep reflection qua ranh giới module không được mở**. Strong encapsulation trong JPMS, được áp dụng chặt hơn qua các phiên bản Java hiện đại, ngăn việc dùng `setAccessible(true)` để truy cập tùy ý member nội bộ JDK hoặc member thuộc package của module khác. Muốn xử lý đúng, phải đọc rõ source module, package, target module, member và framework liên quan; phân biệt `exports` với `opens`; kiểm tra code path phát sinh lỗi trong runtime thực tế.

`--add-opens` có thể giúp chuyển tiếp trong phạm vi hẹp, nhưng giải pháp bền vững là dùng API công khai, cập nhật dependency/framework, hoặc khai báo openness có chủ đích cho những package thuộc quyền quản lý. Kết hợp phân tích tĩnh với test trên JDK mục tiêu và lưu bằng chứng migration giúp hệ thống tiến lên JDK mới mà không hình thành thêm phụ thuộc dài hạn vào implementation detail.
