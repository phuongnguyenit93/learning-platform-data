# JPMS và strong encapsulation trong Java Reflection

## 1. Bức tranh tổng thể: vì sao reflection vẫn bị giới hạn?

**JPMS (Java Platform Module System)**, xuất hiện từ Java 9, cho phép một ứng dụng tổ chức mã thành các **module có tên** (named module). Mỗi module khai báo những module khác mà nó cần đọc, những package công khai cho mã bên ngoài và những package cho phép truy cập sâu bằng reflection. Điều này bổ sung một ranh giới đóng gói ở cấp module bên cạnh `public`, `protected`, package-private và `private` của ngôn ngữ Java.

**Strong encapsulation (đóng gói chặt)** nghĩa là mã bên ngoài không thể mặc nhiên vượt qua ranh giới package của một named module chỉ vì nó có một `Class`, `Method`, `Field` hay `Constructor`. Đặc biệt, `setAccessible(true)` không còn là “chìa khóa vạn năng” để mở mọi thành viên private. Việc package có được **mở** cho module của bên gọi hay không quyết định khả năng truy cập sâu.

Bài học này tập trung vào tác động của JPMS đối với **Java Reflection**. Mục đích học là:

- Phân biệt `requires`, `exports` và `opens` đúng theo chức năng.
- Hiểu vì sao có thể **tìm thấy** phương thức private bằng `getDeclaredMethod()` nhưng **không gọi được**.
- Dự đoán `canAccess()`, `trySetAccessible()` và `setAccessible(true)` trong hai module khác nhau.
- Chạy một ví dụ có thể tái hiện trên Java 17+ và mở đúng một package khi thực sự cần.
- Đọc lỗi liên quan đến module, sửa ở đúng nơi và tránh mở toàn bộ nội bộ thư viện.

### Ba câu hỏi độc lập cần đặt ra

1. **Bên gọi có đọc được module chứa API không?** Quan hệ đọc module (readability) thường được khai báo bằng `requires` khi biên dịch mã tham chiếu trực tiếp kiểu của module khác.
2. **Package có xuất API công khai ra bên ngoài không?** `exports` cho phép sử dụng các kiểu public và thành viên public có thể truy cập theo quy tắc Java thông thường.
3. **Package có mở cho truy cập sâu bằng reflection không?** `opens` cho phép reflection phá qua kiểm tra truy cập Java trong phạm vi JPMS cấp quyền; quyền này thường dùng cho framework cần đọc constructor/field private.

Một module có thể trả lời “có” cho câu hỏi 1 và 2 nhưng “không” cho câu hỏi 3. Đó là lý do một lời gọi public chạy tốt trong khi một lời gọi private qua reflection bị từ chối.

## 2. Module và package: hai lớp đóng gói

Trước khi dùng JPMS, một thư viện thường đóng gói bằng `public`, `protected`, package-private và `private`. Với JPMS, package nằm trong một named module còn có chính sách được phép xuất/mở ra các module khác.

Ví dụ cấu trúc:

~~~text
com.example.library  (named module)
  ├── module-info.java
  └── com.example.library.api
        └── SecretBox.java

com.example.client   (named module)
  ├── module-info.java
  └── com.example.client
        └── Main.java
~~~

`module-info.java` của thư viện định nghĩa ranh giới module. Module khách muốn gọi `SecretBox` từ mã Java thông thường cần có khả năng đọc module thư viện **và** cần package chứa kiểu đó được xuất phù hợp. Khi muốn dùng reflection vào `private`, việc xuất package chưa đủ.

| Cơ chế | Mục đích chính | Cho phép truy cập thành viên private bằng reflection từ module khác? |
| --- | --- | --- |
| `requires com.example.library;` trong client | Client đọc được module thư viện theo quan hệ phụ thuộc | **Không** tự cấp quyền |
| `exports com.example.library.api;` trong library | Xuất API công khai của package cho các module đọc được | **Không** tự cấp quyền truy cập sâu |
| `exports com.example.library.api to com.example.client;` | Chỉ xuất API công khai cho module được nêu | **Không** tự cấp quyền truy cập sâu |
| `opens com.example.library.api;` | Mở package cho reflection từ các module khác | **Có thể**, khi các điều kiện reflection khác cũng thỏa mãn |
| `opens com.example.library.api to com.example.client;` | Mở cho reflection từ đúng module được nêu | **Có thể**, với client được nêu |
| `open module com.example.library { ... }` | Mở mọi package trong module cho reflection | Có thể, nhưng phạm vi rất rộng; không dùng `opens` riêng bên trong `open module` |
| Không `exports`, không `opens` | Giữ package nội bộ ở mức module | Client khác không có quyền sử dụng API thông thường hoặc truy cập sâu chỉ nhờ reflection |

**`opens` không thay thế `exports` khi mã Java muốn `import` kiểu public lúc biên dịch.** Ngược lại, **`exports` không thay thế `opens` khi framework cần đọc private field**. Một package có thể khai báo cả hai khi thực sự cần cả API thông thường và truy cập sâu.

Ngoài ra, khi khai báo `exports ... to ...` hay `opens ... to ...`, tên sau `to` là **tên module**, không phải tên package và cũng không phải tên lớp. Quyền được cấp theo package, không theo từng phương thức riêng lẻ.

## 3. “Tìm được” và “truy cập được” là hai bước khác nhau

Các API khám phá metadata không có cùng ý nghĩa với các API sử dụng thành viên:

| Thao tác | Bạn đang hỏi gì? | Kết quả cần hiểu |
| --- | --- | --- |
| `getDeclaredMethod("secret")` | Lớp này có tự khai báo phương thức tên `secret` không? | Có thể tìm thấy private method; không đồng nghĩa với được gọi |
| `getMethod("greet")` | Có phương thức public phù hợp theo quy tắc tra cứu của API không? | Có thể tìm thấy public method; quyền sử dụng còn phụ thuộc khả năng truy cập kiểu/package/module |
| `method.getModifiers()` | Khai báo phương thức chứa bit cờ nào? | Trả về metadata; không tự mở ranh giới truy cập |
| `method.canAccess(receiver)` | Với caller hiện tại và receiver này, kiểm tra truy cập có đang cho phép không? | Trả về `boolean`; dùng đúng receiver cho thành viên instance |
| `method.trySetAccessible()` | Có thể tắt kiểm tra quyền Java trên đối tượng reflection này không? | `true` khi yêu cầu thành công, `false` khi không thể do giới hạn truy cập như module |
| `method.setAccessible(true)` | Yêu cầu tắt kiểm tra quyền Java, hoặc báo lỗi | Có thể ném `InaccessibleObjectException` nếu JPMS không cho phép |
| `method.invoke(receiver)` | Thực sự gọi phương thức | Có thể ném `IllegalAccessException` nếu không có quyền; ngoại lệ do chính phương thức ném được bọc trong `InvocationTargetException` |

Ở mức truy cập ngôn ngữ Java, một public class trong exported package và một public member của nó có thể được client truy cập mà không cần `opens`. Nhưng private member của chính class đó vẫn bị giới hạn khi client dùng reflection.

Việc gọi thành công `trySetAccessible()` **không chỉnh sửa bytecode** hoặc chuyển modifier `private` thành `public`. `getModifiers()` vẫn phản ánh khai báo. Sự thay đổi chỉ liên quan đến việc bỏ kiểm tra truy cập khi sử dụng **đối tượng reflection cụ thể** trong phạm vi mà runtime cho phép.

### Những trường hợp có quyền suppress access

Theo hợp đồng của `AccessibleObject`, việc tắt kiểm tra có thể được cho phép trong một số trường hợp, chẳng hạn:

- Caller và kiểu khai báo thành viên thuộc **cùng module**.
- Thành viên public của public class nằm trong package được xuất phù hợp tới module của caller.
- Một số trường hợp `protected static` của public class trong exported package khi caller là subclass.
- Package của kiểu khai báo được **mở** cho module của caller; đây là trường hợp quan trọng nhất khi một framework ở module khác cần đọc/gọi private member.

Đây là các điều kiện quyền của API, không phải mẹo bypass; hãy dựa vào chính sách module của ứng dụng.

## 4. Ví dụ hoàn chỉnh Java 17+: hai module, một package chỉ được exports

Ví dụ có một module thư viện chứa phương thức public và private, một module khách gọi cả hai bằng reflection. **Mặc định, thư viện chỉ `exports` package; chưa `opens`.**

Tạo đúng các tệp sau từ một thư mục làm việc trống.

**Tệp `src/com.example.library/module-info.java`:**

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

**Tệp `src/com.example.library/com/example/library/api/SecretBox.java`:**

~~~java
package com.example.library.api;

public class SecretBox {
    public String greet() { return "hello"; }
    private String secret() { return "hidden"; }
}
~~~

**Tệp `src/com.example.client/module-info.java`:**

~~~java
module com.example.client {
    requires com.example.library;
}
~~~

**Tệp `src/com.example.client/com/example/client/Main.java`:**

~~~java
package com.example.client;

import com.example.library.api.SecretBox;
import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws Exception {
        SecretBox box = new SecretBox();
        Class<?> type = box.getClass();

        System.out.println("public call: " + box.greet());
        Method greet = type.getMethod("greet");
        System.out.println("public reflection: " + greet.invoke(box));

        Method secret = type.getDeclaredMethod("secret");
        System.out.println("declared: " + secret.getName());
        System.out.println("trySetAccessible: " + secret.trySetAccessible());
        try {
            System.out.println("invoke secret: " + secret.invoke(box));
        } catch (IllegalAccessException ex) {
            System.out.println("invoke blocked: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Biên dịch** từ thư mục chứa `src/` (cần JDK 17 trở lên):

~~~bash
javac --release 17 --module-source-path src -d out -m com.example.library,com.example.client
~~~

Tham số `--module-source-path src` xác định cây mã nguồn theo tên module; `-m` chỉ các module cần biên dịch, và `-d out` tạo các thư mục `out/com.example.library`, `out/com.example.client`. Lệnh này dùng được ở command prompt/PowerShell nếu đang ở đúng thư mục làm việc có `src`.

**Chạy** module client:

~~~bash
java --module-path out -m com.example.client/com.example.client.Main
~~~

**Stdout đã được xác minh bằng cách biên dịch `--release 17` và chạy trên JDK 21:**

~~~text
public call: hello
public reflection: hello
declared: secret
trySetAccessible: false
invoke blocked: IllegalAccessException
~~~

**Vì sao từng dòng xảy ra?**

1. `requires com.example.library` và `exports com.example.library.api` cho phép client biên dịch/làm việc bình thường với `SecretBox`, gọi public `greet()`.
2. `getMethod("greet")` trả về public method; `invoke` được phép qua exported API.
3. `getDeclaredMethod("secret")` vẫn tìm thấy private method và in được tên phương thức. Việc tìm metadata không cần mở package theo cùng cách như truy cập sâu.
4. `trySetAccessible()` trả `false` vì `com.example.library.api` chưa mở cho `com.example.client`.
5. Khi gọi `invoke`, kiểm tra quyền vẫn có hiệu lực; `IllegalAccessException` được bắt và in dưới dạng tên ngoại lệ.

Kết quả trên là hành vi của ví dụ cụ thể với hai **named module** trên module path. Khi chạy mã trên classpath/unnamed module hoặc thay chính sách `opens`, kết quả có thể khác; không khái quát rằng mọi lời gọi private reflection đều thất bại.

## 5. Mở đúng package cho reflection

Có hai cách mở package phù hợp với ví dụ: sửa khai báo module ở mã nguồn thư viện hoặc cấu hình lúc chạy khi bạn có quyền vận hành ứng dụng.

### Cách A — khai báo `opens ... to ...` trong thư viện

Thay nội dung `src/com.example.library/module-info.java` bằng:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.api to com.example.client;
}
~~~

Biên dịch lại và chạy bằng **hai lệnh không đổi** ở phần 4. Giờ stdout là:

~~~text
public call: hello
public reflection: hello
declared: secret
trySetAccessible: true
invoke secret: hidden
~~~

`exports` phục vụ lời gọi public và `import`; `opens ... to com.example.client` cho phép module khách truy cập sâu vào package này bằng reflection. Quyền mở áp dụng cho toàn package được nêu, nên cần cân nhắc trước khi cấp.

### Cách B — thêm `--add-opens` khi chạy

Giữ `module-info.java` ban đầu (chỉ `exports`) và chạy bằng lệnh:

~~~bash
java --module-path out --add-opens com.example.library/com.example.library.api=com.example.client -m com.example.client/com.example.client.Main
~~~

**Sau khi biên dịch với phiên bản chỉ `exports` ở phần 4**, stdout trùng với trường hợp đã mở ở cách A:

~~~text
public call: hello
public reflection: hello
declared: secret
trySetAccessible: true
invoke secret: hidden
~~~

Cú pháp là `--add-opens <module-nguồn>/<package>=<module-đích>`. Trong trường hợp thư viện cần mở cho chương trình classpath (unnamed modules), đích thường là `ALL-UNNAMED`; ví dụ `--add-opens com.example.library/com.example.library.api=ALL-UNNAMED`.

Hãy phân biệt:

- `--add-opens`: mở package cho truy cập sâu bằng reflection ở runtime.
- `--add-exports`: bổ sung quyền nhìn thấy API public của package, không tự cấp quyền đọc private field/method bằng reflection.
- `--add-reads`: bổ sung quan hệ đọc giữa module, không tự cấp `exports` hoặc `opens`.

Các cờ này thay đổi ranh giới runtime theo cấu hình triển khai; chúng không thay đổi các modifier trong class file và không sửa `module-info.java` đã biên dịch. Nếu muốn chính sách lâu dài có thể kiểm soát ở nguồn, hãy ưu tiên thiết kế khai báo module có chủ đích.

## 6. Strong encapsulation đối với JDK nội bộ và thư viện cũ

JPMS không chỉ áp dụng cho module do chính ứng dụng viết. Các package nội bộ của **JDK** cũng được đóng gói trong các named module như `java.base`.

Các mốc lịch sử cần phân biệt:

- **Java 9:** đưa JPMS vào Java; để hỗ trợ chuyển đổi từ ứng dụng cũ, JDK từng có cơ chế nới lỏng truy cập đối với một số package nội bộ.
- **Java 16:** JEP 396 đưa đóng gói chặt các phần nội bộ JDK thành mặc định, vẫn có cơ chế chuyển đổi tạm thời.
- **Java 17:** JEP 403 đóng gói chặt các package nội bộ JDK theo mặc định và khiến lựa chọn `--illegal-access` cũ không còn hiệu lực để mở rộng truy cập. Một số API đặc biệt như `sun.misc.Unsafe` thuộc `jdk.unsupported` có ngoại lệ/chính sách riêng; đừng từ đó suy ra mọi API nội bộ đều được mở.

Một ứng dụng vốn chạy trên JDK 8 có thể bị lỗi sau khi nâng lên JDK 17 nếu framework hay thư viện dùng `setAccessible(true)` để truy cập trường/phương thức private trong package JDK không mở. Cách xử lý bền vững là nâng cấp framework, dùng API Java được hỗ trợ hoặc thay chiến lược truy cập. Nếu có một nhu cầu tương thích chưa thể bỏ ngay, `--add-opens` có mục tiêu có thể giúp chuyển tiếp.

Ví dụ cờ mở `java.lang` của `java.base` cho tất cả unnamed modules:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar example.Main
~~~

Đây là **ví dụ cú pháp cấu hình**, không phải một chương trình chạy độc lập: `app.jar` và `example.Main` đại diện cho ứng dụng thực tế. Không thêm cờ này khi chưa có bằng chứng rằng ứng dụng cần truy cập sâu `java.lang`. Việc mở package nội bộ có thể làm giảm khả năng kiểm soát đóng gói và tăng phụ thuộc vào chi tiết triển khai của JDK.

### Vì sao classpath và module path cho kết quả khác nhau?

| Cách nạp ứng dụng/thư viện | Trạng thái JPMS liên quan |
| --- | --- |
| Các class từ classpath | Thuộc **unnamed module** của class loader liên quan; package của unnamed module được xuất và mở rộng rãi theo hợp đồng module |
| JAR thường đặt trên module path, không có `module-info.class` | Có thể trở thành **automatic module** với tên module được xác định theo JAR; các package của automatic module được xuất/mở rộng rãi để tương thích |
| Named module có `module-info.java` tường minh | Chính sách `requires`, `exports`, `opens` do tác giả xác định; package không tự mở chỉ vì có reflection |
| Các module JDK | Có quy định `exports`/`opens` riêng; việc code ứng dụng nằm trên classpath không tự mở các package JDK bị đóng gói chặt |

Vì vậy, trường hợp một thư viện riêng chạy tốt trên classpath **không chứng minh** rằng truy cập sâu sẽ thành công khi thư viện được chuyển sang named module tường minh. Chiều ngược lại cũng đúng: cần biết module nào khai báo thành viên và module nào gọi reflection trước khi chẩn đoán.

## 7. Kiểm tra module và chính sách mở tại runtime

Để chẩn đoán lỗi, có thể hỏi đối tượng `Module`:

~~~java
Module library = com.example.library.api.SecretBox.class.getModule();
Module client = com.example.client.Main.class.getModule();

String pkg = "com.example.library.api";
System.out.println(library.getName());
System.out.println(client.canRead(library));
System.out.println(library.isExported(pkg, client));
System.out.println(library.isOpen(pkg, client));
~~~

Đây là **đoạn mã minh họa chẩn đoán** đặt trong ngữ cảnh có thể tham chiếu hai lớp, không phải một file Java độc lập. Với module descriptors ở phần 4, lần lượt thu được:

~~~text
com.example.library
true
true
false
~~~

Khi khai báo `opens com.example.library.api to com.example.client;`, dòng cuối thành `true`. Nếu đặt mã này trong một lớp khác, giá trị `canRead`, `isExported`, `isOpen` phải được hiểu theo hai module cụ thể đang kiểm tra.

- `Class#getModule()`: xác định module thật sự chứa class được nạp.
- `Module#isNamed()`: giúp phân biệt named module và unnamed module.
- `Module#canRead(other)`: xem quan hệ đọc thực tế; điều này không tự chứng minh quyền gọi private member.
- `Module#isExported(packageName, target)`: xem package có được xuất cho module đích không.
- `Module#isOpen(packageName, target)`: xem package có được mở cho module đích không.

Đối với các framework dựa vào reflection, **quyền truy cập được xét theo module của mã thực sự gọi API reflection**, thường là module framework, không nhất thiết là module của ứng dụng cuối cùng. Vì vậy, `opens ... to` phải nêu đúng module nhận quyền, ví dụ module framework cần truy cập các trường private của model.

## 8. Phân biệt ngoại lệ thường gặp

| Lỗi / kết quả | Thường xuất hiện khi nào? | Hướng kiểm tra |
| --- | --- | --- |
| `NoSuchMethodException` | `getMethod`/`getDeclaredMethod` không tìm được chữ ký yêu cầu | Kiểm tra tên, kiểu tham số, public-vs-declared và lớp thực sự khai báo |
| `IllegalAccessException` | `invoke`, `Field.get/set` hoặc `Constructor.newInstance` không được phép truy cập | Kiểm tra modifier, lớp gọi, package, `exports`/`opens` và trạng thái accessible |
| `InaccessibleObjectException` | `setAccessible(true)` yêu cầu bỏ kiểm tra nhưng JPMS không cho phép | Xem thông báo lỗi chỉ rõ module/package nguồn và module đích; chỉnh quyền mở có mục tiêu |
| `trySetAccessible() == false` | Không thể bật truy cập sâu trong ngữ cảnh hiện tại | Kiểm tra module đích thực sự và `opens`; ưu tiên API công khai |
| `InvocationTargetException` | Chính phương thức được gọi ném ngoại lệ | Kiểm tra `getCause()`; đây là lỗi của code được gọi, không mặc nhiên là lỗi JPMS |
| Lỗi biên dịch “package ... is not visible” | Mã nhập kiểu từ package không được exported tới module của caller hoặc thiếu khả năng đọc phù hợp | Kiểm tra `requires` và `exports`; chỉ mở package bằng `opens` không đủ cho `import` thông thường |

Ví dụ thông báo `InaccessibleObjectException` có thể nói module A “does not opens package X to module B”. Khi đó sửa module **A** để mở package **X** cho module **B** (hoặc cấu hình `--add-opens A/X=B` nếu phù hợp). Không suy ra rằng chỉ cần thêm `requires A` trong B.

Lưu ý `trySetAccessible()` không phải đảm bảo không bao giờ ném ngoại lệ trong mọi môi trường: các kiểm tra bảo mật hoặc việc dùng API sai có thể có kết quả riêng. Trong ví dụ phần 4, nó trả về `false` do giới hạn JPMS.

## 9. Cách thiết kế hệ thống có reflection mà vẫn giữ đóng gói

**Ưu tiên thứ tự sau khi thiết kế thư viện hoặc framework:**

1. **Công khai đúng API cần dùng.** Khi caller chỉ cần một hành vi, chọn một public method/interface thích hợp thay vì lấy private field bằng reflection.
2. **Tách API public khỏi implementation nội bộ.** Chỉ `exports` các package chứa hợp đồng chính thức. Không xuất toàn bộ package implementation chỉ để đáp ứng một đoạn mã tiện dụng.
3. **Mở đúng package cho đúng framework cần truy cập sâu.** Với một thư viện có quyền sửa `module-info.java`, có thể dùng `opens com.example.model to framework.module;`. Tên này chỉ mang tính ví dụ; phải thay bằng tên module thực tế.
4. **Theo dõi quyền được cấp.** Khi dùng `--add-opens` cho việc chuyển đổi, lưu lý do, phiên bản thư viện, phần cấu hình triển khai và kế hoạch thay thế. Tránh `ALL-UNNAMED` hoặc `open module` khi đã biết tên module cụ thể của bên cần quyền.
5. **Kiểm tra trên chính kiểu triển khai mục tiêu.** Kiểm thử module path nếu sản phẩm triển khai bằng named module; thử cả các ca package mở và đóng để phát hiện giả định ngầm từ classpath.

Trong hệ sinh thái framework, một thư viện có thể hỗ trợ API công khai ở package `api` qua `exports`, còn dữ liệu model dùng để deserialize/inject ở package `model` qua `opens` có mục tiêu. Ranh giới này vừa cho phép framework thực hiện công việc vừa hạn chế phần API triển khai bị ràng buộc vào mã bên ngoài.

### Những sai lầm dễ lặp lại

- **“`setAccessible(true)` luôn ép được private.”** Sai khi named module không cho phép suppress access.
- **“`exports` và `opens` là như nhau.”** `exports` dành cho truy cập API thông thường; `opens` phục vụ reflection truy cập sâu.
- **“Tìm được bằng `getDeclaredField` là có thể `get` hoặc `set`.”** Metadata khác với thao tác lên đối tượng.
- **“Thư viện hoạt động trên classpath thì chắc chắn hoạt động y nguyên trên module path.”** Quyền của unnamed/automatic module khác named module khai báo tường minh.
- **“Mở mọi package để nhanh hết lỗi.”** Cách này bỏ qua giới hạn đóng gói và thường che giấu vấn đề phiên bản hoặc thiết kế API.
- **“Có `requires` thì private reflection tự được phép.”** `requires` là quan hệ đọc module, không phải quyền mở package.
- **“`--illegal-access=permit` sửa được lỗi JDK 17.”** Tùy chọn cũ không còn có tác dụng nới truy cập JDK internals trên Java 17.

## 10. Thực hành và câu hỏi kiểm tra

**Bài tập 1 — Xuất public nhưng không mở private.** Giữ `exports com.example.library.api;` và bỏ mọi `opens`. Dự đoán kết quả hai lời gọi `greet.invoke(box)` và `secret.trySetAccessible()`.

**Đáp án:** Lời gọi public thành công, còn `trySetAccessible()` trả `false` trong ví dụ hai named module. Khám phá được private member không đủ để vượt ranh giới mở package.

**Bài tập 2 — `opens` nhưng không `exports`.** Sửa module library chỉ còn `opens com.example.library.api to com.example.client;`. Giữ nguyên mã client có dòng `import com.example.library.api.SecretBox;`. Dự đoán kết quả biên dịch.

**Đáp án:** Mã client không được phép tham chiếu trực tiếp public type từ package không exported, nên biên dịch thất bại; `opens` không thay `exports`. Nếu muốn client gọi `SecretBox` qua API Java bình thường và cũng dùng private reflection, cần cấp cả hai quyền phù hợp.

**Bài tập 3 — Quyền mở có đích.** `opens com.example.library.api to com.example.client;` được khai báo. Module thứ ba `com.example.other` cũng muốn gọi private member. Module thứ ba được quyền tương tự không?

**Đáp án:** Không tự động; quyền mở được cấp cho đúng `com.example.client`, trừ khi có chính sách mở khác hoặc cấu hình runtime bổ sung.

**Bài tập 4 — Chuyển từ classpath sang module path.** Một thư viện phụ thuộc vào private field reflection, chạy ổn trước khi được chuyển thành named module tường minh; sau đó `trySetAccessible()` trả `false`. Bạn cần kiểm tra gì?

**Đáp án:** Xác định module của class khai báo field, module của code thực sự gọi reflection và package chứa field; kiểm tra `isOpen(package, callerModule)`. Ưu tiên API được hỗ trợ hoặc khai báo `opens ... to ...` chính xác.

**Bài tập 5 — Phân loại lỗi.** `getDeclaredMethod("secret")` thành công; `setAccessible(true)` ném `InaccessibleObjectException`. Nên sửa tên phương thức hay ranh giới module?

**Đáp án:** Việc tìm metadata đã thành công, vì vậy kiểm tra ranh giới mở package và chính sách JPMS; đổi tên phương thức không giải quyết nguyên nhân.

## 11. Ghi nhớ

JPMS bổ sung ranh giới cấp module để kiểm soát package được **đọc**, **xuất API công khai** và **mở cho reflection**. Với Java Reflection, cần tách ba việc: *tìm thành viên*, *đọc modifier*, *thực sự truy cập*. `getDeclared...` có thể nhìn thấy khai báo private, nhưng `trySetAccessible()` chỉ thành công khi quyền module cho phép. Trong thiết kế lâu dài, hãy giữ `exports` cho API chính thức và chỉ `opens` những package thực sự cần truy cập sâu, ưu tiên mở cho một module được chỉ định.
