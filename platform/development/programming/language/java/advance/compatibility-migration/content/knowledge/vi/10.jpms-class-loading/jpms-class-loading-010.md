# Nâng cấp JDK mà chưa chuyển toàn bộ ứng dụng sang JPMS

Nâng JDK và chuyển ứng dụng sang Java Platform Module System (JPMS) là **hai công việc liên quan nhưng không bắt buộc phải thực hiện đồng thời**. Từ Java 9, JDK có hệ thống module, file `module-info.java` và cơ chế đóng gói mạnh hơn. Tuy nhiên, phần lớn ứng dụng Java truyền thống vẫn có thể được biên dịch, đóng gói và chạy bằng **classpath** như trước, không cần ngay lập tức biến tất cả JAR thành *named module*.

Điều đó không có nghĩa nâng JDK sẽ không ảnh hưởng ứng dụng chưa modularize. Các thư viện cũ có thể truy cập JDK internal API, sử dụng reflection vào package bị đóng, phụ thuộc vào API đã bị gỡ khỏi JDK hoặc bị ảnh hưởng bởi cách JDK nạp lớp. Vì thế, cách tiếp cận hợp lý là **giữ kiến trúc classpath khi cần, nhưng chủ động xử lý các thay đổi do JDK và JPMS tạo ra**.

Bài này hướng dẫn cách nhận diện ranh giới giữa nâng cấp runtime và modularization, cách chạy ứng dụng legacy trên classpath, những lỗi có thể phát sinh và quy trình kiểm chứng trước khi quyết định có cần chuyển sang JPMS đầy đủ hay không.

## 1. JPMS không đồng nghĩa mọi ứng dụng phải có module-info.java

JPMS xuất hiện từ Java 9 với mục tiêu tổ chức ứng dụng thành các module có tên, khai báo dependency rõ ràng, kiểm soát package được export hoặc open và cho phép xây runtime image có tập module phù hợp.

Một module được khai báo rõ có thể chứa descriptor:

~~~java
module com.example.orders {
    requires java.sql;

    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Ở đây:

- `module com.example.orders` đặt tên module.
- `requires java.sql` khai báo phụ thuộc có thể đọc.
- `exports` cho phép module khác truy cập public types thuộc package được export.
- `opens` cho phép deep reflection vào package được mở theo quy tắc JPMS.

Nếu ứng dụng hiện tại chưa có `module-info.java`, ta **không bắt buộc** phải thêm file này chỉ vì muốn chuyển từ JDK 8 sang JDK 11, 17 hoặc 21. Ứng dụng vẫn có thể dùng classpath:

~~~bash
java -cp "app.jar:lib/*" com.example.orders.Main
~~~

Ví dụ lệnh sử dụng dấu `:` ngăn cách classpath theo quy tắc Linux/macOS. Trên Windows dùng dấu `;`:

~~~powershell
java -cp "app.jar;lib/*" com.example.orders.Main
~~~

Lưu ý cú pháp wildcard `lib/*` là khả năng của Java launcher để chọn JAR trực tiếp trong thư mục; nó không tự duyệt đệ quy mọi thư mục con. Cách đóng gói executable/fat JAR của framework có thể dùng cơ chế launcher riêng, vì vậy cần chạy đúng hình thức artifact của dự án.

Điểm cốt lõi: **làm việc trên classpath vẫn là một chế độ chạy được hỗ trợ của Java hiện đại**. Điều cần kiểm chứng là toàn bộ runtime và dependency của ứng dụng có tương thích với JDK mới hay không.

## 2. Phân biệt classpath, module path và các loại module

Khi dùng JDK có JPMS, đường dẫn chứa thư viện không còn là một khái niệm duy nhất. Cần phân biệt cách JVM thấy các JAR.

| Khái niệm | Ý nghĩa | Đặc điểm |
|---|---|---|
| Classpath | Danh sách class directory/JAR theo cơ chế Java truyền thống | Không cần `module-info.java`; các lớp thuộc unnamed module của class loader tương ứng |
| Unnamed module | Module không tên chứa các lớp được nạp từ classpath của một class loader | Không có descriptor khai báo `requires`, `exports` hoặc `opens` |
| Module path | Vị trí chứa các module được JPMS dùng để resolution | Dùng với `--module-path` hoặc `-p` |
| Explicit named module | Module có descriptor `module-info.class` | Có tên, dependency, exports/opens và quy tắc readability |
| Automatic module | JAR không có descriptor nhưng đặt trên module path | JVM đặt tên module theo metadata/tên JAR và áp dụng cơ chế automatic module |
| JDK system module | Các module nền tảng và module đi kèm runtime | Ví dụ `java.base`, `java.sql`, `java.xml`, `java.net.http` |

Một JAR legacy đặt trên **classpath** không tự trở thành automatic module. Nếu đưa cùng JAR sang **module path**, nó có thể trở thành automatic module nếu không có descriptor. Vì vậy, di chuyển thư viện từ `-cp` sang `--module-path` là thay đổi hành vi quan trọng, không phải chỉ thay tên tham số.

### 2.1. Unnamed module và khả năng truy cập

Các lớp trong classpath thuộc unnamed module gắn với class loader đang nạp chúng. Với mã trên classpath, nhiều quy tắc truy cập giữa các lớp ứng dụng vẫn giống cơ chế Java truyền thống. Ứng dụng không cần khai báo `requires` cho từng JAR trên classpath.

Tuy nhiên, quyền truy cập vào **named JDK modules** vẫn chịu sự đóng gói của JPMS. Unnamed module có khả năng đọc các module được resolve, nhưng **đọc được module không đồng nghĩa được truy cập mọi package**. Chỉ package được export cho bên gọi mới truy cập public types hợp lệ; deep reflection còn cần package được open.

### 2.2. Automatic module không phải giải pháp mặc định

Automatic module giúp bridge một số thư viện legacy khi xây modular application. Nhưng nó có thêm hệ quả:

- Tên module có thể phụ thuộc vào `Automatic-Module-Name` hoặc tên JAR.
- Các vấn đề split package có thể xuất hiện khi nhiều module chứa cùng một package.
- Module graph và package visibility có thể thay đổi.
- Một named module không thể tùy tiện phụ thuộc vào classpath như mã legacy.

Nếu mục tiêu trước mắt chỉ là **nâng JDK an toàn**, đừng chuyển toàn bộ dependency lên module path một cách máy móc. Giữ classpath sẽ giảm số biến thay đổi trong cùng một đợt migration.

## 3. Mục tiêu thực tế của nâng JDK chưa modularize

Giả sử hệ thống có kiến trúc:

~~~text
Order Application
  ├── app.jar
  ├── lib/spring-*.jar
  ├── lib/jackson-*.jar
  ├── lib/database-driver.jar
  └── lib/internal-common.jar

Runtime hiện tại: JDK 8
Runtime dự kiến: JDK 17
Ứng dụng chưa có module-info.java
~~~

Mục tiêu của giai đoạn đầu có thể là:

1. Ứng dụng build được bằng compiler và công cụ build tương thích JDK mới.
2. Artifact cuối cùng dùng đúng API và class-file target được lựa chọn.
3. Runtime mới nạp được các lớp và dependency.
4. Application context, reflection, serializer, ORM và driver hoạt động đúng.
5. Các luồng nghiệp vụ chính và dữ liệu giữ nguyên ý nghĩa.
6. Không phát sinh lỗi do JDK module encapsulation hoặc API bị gỡ bỏ.
7. Hệ thống đáp ứng yêu cầu vận hành cơ bản trên JDK mới.

**Chưa có `module-info.java` không phải lỗi** nếu sản phẩm không có yêu cầu module hóa. Việc tách JPMS thành một initiative riêng giúp giảm phạm vi thay đổi và làm rõ nguyên nhân khi có sự cố.

Mặt khác, nếu dự án đã dùng native image, plugin framework hoặc runtime đóng gói đặc thù thì cần đánh giá thêm theo cách hoạt động riêng của các công cụ đó. Classpath mode không tự giải quyết mọi tương thích hệ sinh thái.

## 4. Những thay đổi do JDK mới vẫn ảnh hưởng classpath

Một ứng dụng không dùng named module vẫn có thể gặp thay đổi đáng kể khi nâng JDK.

### 4.1. Encapsulation của JDK internals

Các package nội bộ JDK như một số package thuộc `sun.*` hoặc `com.sun.*` không phải API Java SE được bảo đảm ổn định. JPMS làm rõ ranh giới giữa module và package được export; nhiều truy cập vốn được thư viện legacy thực hiện có thể không còn được phép.

Ví dụ một thư viện dùng reflection để truy cập field private của `java.lang.String`. Dù thư viện nằm trên classpath, package `java.lang` của module `java.base` không mặc nhiên open cho deep reflection từ unnamed module trên Java mới.

### 4.2. Một số module/API trước đây có sẵn đã bị loại bỏ

Khi chuyển từ JDK 8 lên JDK 11 hoặc mới hơn, nhiều dự án vướng vào các công nghệ Java EE/CORBA từng đi kèm JDK 8. Ví dụ JAXB, JAX-WS và các API liên quan không còn nằm sẵn trong JDK 11 theo cách cũ. Ứng dụng có thể gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` nếu không bổ sung dependency tương ứng.

Các thay đổi hệ sinh thái khác gồm JavaFX không còn được phân phối như thành phần mặc định của OpenJDK từ Java 11, và Nashorn JavaScript engine bị loại bỏ trong JDK 15. Không phải tất cả ứng dụng đều sử dụng những thành phần đó; cần kiểm kê dependency thực tế.

### 4.3. Framework và thư viện cũng thay đổi

Nâng JDK có thể yêu cầu nâng framework, ORM, servlet container, bytecode manipulation library, compiler plugin hoặc agent. Khi nâng thư viện, dù chưa modularize, ứng dụng vẫn có thể đổi API, namespace annotation, cấu hình hoặc hành vi serialization.

Đừng quy mọi lỗi xuất hiện sau nâng JDK cho JPMS. Nên phân loại lỗi thành: class-file version, API bị gỡ, reflection access, dependency conflict, class loader, framework behavior và cấu hình runtime.

## 5. Strong encapsulation: lỗi phổ biến dù vẫn chạy classpath

### 5.1. Reflection bình thường và deep reflection

Reflection được ứng dụng dùng trong rất nhiều việc: dependency injection, ORM, serializer, proxy, bean introspection và kiểm thử. **Không phải mọi reflection đều bị JPMS chặn.**

Ví dụ, một lớp `com.example.orders.Order` nằm trong cùng classpath vẫn có thể được framework trên classpath phân tích qua các API reflection phù hợp. Trở ngại nổi bật xuất hiện khi thư viện cố truy cập **thành viên không public thuộc package trong named module không open**, đặc biệt các package nội bộ hoặc nền tảng JDK.

Ví dụ minh họa:

~~~java
import java.lang.reflect.Field;

public class DeepReflectionExample {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");
        value.setAccessible(true);
    }
}
~~~

Trên các JDK có strong encapsulation, thao tác `setAccessible(true)` vào `java.lang.String` từ unnamed module có thể ném `InaccessibleObjectException`, với thông báo module `java.base` không open package `java.lang` cho caller. Đây là ví dụ cho ranh giới reflection; ứng dụng không nên dựa vào layout private của `String`.

### 5.2. Các lỗi liên quan cần phân biệt

| Lỗi/hiện tượng | Ý nghĩa thường gặp |
|---|---|
| `InaccessibleObjectException` | Deep reflection bị cấm bởi ranh giới module hoặc quyền truy cập |
| `IllegalAccessException` | Reflection không được phép truy cập thành viên trong hoàn cảnh cụ thể |
| `IllegalAccessError` | Liên kết bytecode vi phạm quyền truy cập ở runtime |
| `NoSuchFieldError`, `NoSuchMethodError` | Chữ ký/field/method runtime không khớp thứ mã đã biên dịch |
| `ClassNotFoundException` | Cơ chế tìm lớp không tìm thấy lớp được yêu cầu |
| `NoClassDefFoundError` | JVM không thể sử dụng lớp cần thiết, có thể do dependency thiếu hoặc lỗi khởi tạo trước đó |
| `UnsupportedClassVersionError` | JVM không hỗ trợ class-file version được nạp |

Thông báo có tên module, package và cụm từ “does not open” là gợi ý mạnh về deep reflection. Thông báo “does not export” thường liên quan khả năng truy cập package. Đọc stack trace từ nguyên nhân gốc thay vì chỉ nhìn exception được framework bọc bên ngoài.

### 5.3. Mốc JDK 9 đến JDK 17

Các release đầu của JPMS có cơ chế nới lỏng truy cập phản chiếu tới một số JDK internals để hỗ trợ migration, thường có cảnh báo illegal reflective access. Qua các phiên bản, chính sách được siết lại; từ JDK 17, strong encapsulation của JDK internals được thực thi rộng hơn theo JEP 403, ngoại trừ những bề mặt được hỗ trợ hoặc mở rõ.

Không nên dựa vào `--illegal-access=permit` như giải pháp bền vững: tùy chọn này không còn tác dụng nới lỏng truy cập trên JDK 17 trở đi. Hãy tìm thư viện hoặc cấu hình mới thay thế, và chỉ dùng những override cụ thể khi có lý do rõ.

## 6. Dùng --add-opens và --add-exports đúng ngữ cảnh

Khi thư viện cũ chưa có bản cập nhật, JVM cung cấp các tùy chọn để mở ranh giới module có chọn lọc. Đây là **biện pháp tương thích có kiểm soát**, không phải bước bắt buộc của mọi ứng dụng legacy.

### 6.1. --add-opens cho deep reflection

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "app.jar:lib/*" \
     com.example.orders.Main
~~~

Ý nghĩa:

- `java.base` là tên module nguồn.
- `java.lang` là package được mở.
- `ALL-UNNAMED` cho phép mọi unnamed module thực hiện deep reflection vào package này theo cơ chế reflective access của JVM.

Tùy chọn này rộng hơn mức mà nhiều ứng dụng thực sự cần. Không nên thêm nó một cách mặc định vào mọi JVM. Chỉ dùng khi có stack trace cho thấy thư viện cần truy cập cụ thể, sau khi đã cân nhắc nâng thư viện hoặc sửa mã.

### 6.2. --add-exports cho truy cập API không được export

Ví dụ minh họa một trường hợp phụ thuộc JDK internal API:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
     -cp "app.jar:lib/*" \
     com.example.orders.Main
~~~

`--add-exports` mở quyền truy cập public types trong một package của named module cho target được chỉ định. Nó **không tương đương** `--add-opens` để truy cập private members bằng deep reflection.

Nếu một thư viện cần `--add-exports` tới `sun.nio.ch`, nên coi đây là dấu hiệu kỹ thuật cần được loại bỏ về lâu dài. API nội bộ có thể biến mất hoặc thay đổi dù quyền truy cập đã được mở.

### 6.3. Phân biệt các tùy chọn

| Tùy chọn | Mục đích | Khi cân nhắc |
|---|---|---|
| `--add-opens` | Cho phép deep reflection vào package của module | Framework/thư viện cần reflective access cụ thể |
| `--add-exports` | Export package đến module/unnamed module mục tiêu | Có dependency tới public type thuộc package không export |
| `--add-modules` | Bổ sung root module vào quá trình resolution | Một module tồn tại nhưng chưa được resolve mặc định |
| `--add-reads` | Bổ sung cạnh readability giữa module | Trường hợp bridge với module graph phức tạp |
| `--module-path` / `-p` | Khai báo đường dẫn module | Chạy named/automatic modules |
| `--class-path` / `-cp` | Khai báo đường dẫn classpath | Chạy ứng dụng legacy hoặc classpath-based |

Không sử dụng `--add-modules` để “khôi phục” module đã **bị gỡ khỏi JDK**. Nếu JAXB/JAX-WS không còn được JDK cung cấp, cần thêm dependency phù hợp, không thể chỉ thêm một tên module không tồn tại.

Khi dùng các flag này, lưu chúng trong cấu hình môi trường/launch script và test đầy đủ. Không để một máy developer có flag thủ công trong IDE trong khi CI và production không có.

## 7. Classpath và module path có những giới hạn khác nhau

### 7.1. Không chuyển tất cả JAR sang module path cùng lúc

Khi đưa một JAR legacy từ classpath lên module path, nó không còn đơn giản là một JAR trong unnamed module. Nếu không có `module-info.class`, nó thường trở thành automatic module. Việc thay đổi placement này có thể làm lộ lỗi:

- Hai module chứa package trùng nhau (*split package*).
- Một module cần dependency không được resolve.
- Tên automatic module thay đổi theo tên JAR.
- Một named module cố truy cập lớp trong unnamed module không nằm trong module graph thông thường.
- Java agent hoặc class loader framework có logic tìm lớp gắn với classpath.

Nếu JDK upgrade đã đủ phức tạp, tốt nhất giữ classpath ổn định, xử lý hết lỗi runtime trước rồi mới thử modularization.

### 7.2. Split package và duplicate class

Classpath có thể chứa nhiều JAR với package giống nhau và JVM thường chọn lớp theo cơ chế class-loader search order, gây các lỗi khó đoán nhưng không nhất thiết lỗi ngay khi khởi động. JPMS áp dụng thêm các ràng buộc package ở module graph, làm lỗi split package xuất hiện rõ khi chuyển sang module path.

Đừng cho rằng “classpath build xanh” nghĩa dependency sạch. Cần kiểm tra các lớp trùng, version xung đột và thư viện bị shade hoặc repackage. Đây là rủi ro vốn có của classpath, không phải chỉ của JPMS.

### 7.3. Module readability không giống class visibility

Một module cần **readability** để đọc module khác, và package được tham chiếu phải **export** phù hợp để truy cập public API. Đối với reflection vào thành viên không public, package còn phải **open** cho caller.

Ví dụ module:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.internal to com.fasterxml.jackson.databind;
}
~~~

Ví dụ chỉ minh họa khi thư viện đã được modularize và target module đúng tên. Nếu toàn bộ ứng dụng còn trên classpath thì không cần tự tạo descriptor trên chỉ để khai báo `exports`. Các điểm khác nhau về module visibility sẽ quan trọng khi một phần dự án dần chuyển sang named modules.

## 8. Java module bị loại bỏ: thêm dependency thay vì cố gọi module cũ

Một tình huống phổ biến trong migration là mã dùng JAXB:

~~~java
import javax.xml.bind.JAXBContext;

public final class XmlSupport {
    public static JAXBContext create() throws Exception {
        return JAXBContext.newInstance(OrderXml.class);
    }
}
~~~

Với JDK 8, các API JAXB từng có sẵn trong JDK. Từ JDK 11, các Java EE/CORBA modules được gỡ khỏi JDK, nên source không còn tự compile nếu không thêm thư viện tương ứng.

Hướng xử lý:

1. Xác định API/implementation mà ứng dụng đang dùng.
2. Thêm dependency tương thích với framework và JDK mục tiêu.
3. Kiểm tra namespace `javax.xml.bind` hoặc `jakarta.xml.bind` theo phiên bản thư viện/framework.
4. Đảm bảo runtime có implementation/service provider cần thiết, không chỉ API JAR.
5. Chạy thử marshal/unmarshal thực tế.
6. Ghi nhận dependency được đóng gói hoặc do application server cung cấp.

Không tự động thay mọi import `javax.*` thành `jakarta.*`. Đó là thay đổi API có liên quan đến phiên bản thư viện và framework, không phải quy tắc đổi tên áp dụng cho mọi package `javax` trong JDK. Chẳng hạn các API Java SE như `javax.net` hoặc `javax.crypto` không trở thành Jakarta chỉ vì nâng JDK.

Một số thành phần khác như Nashorn hay JavaFX cũng cần phương án riêng nếu ứng dụng phụ thuộc vào chúng. Việc chạy classpath không ngăn được API bị gỡ khỏi runtime.

## 9. ServiceLoader và plugin architecture khi chưa dùng JPMS

Nhiều hệ thống dùng Java SPI:

~~~java
package com.example.spi;

public interface PaymentProvider {
    String name();
}
~~~

Một provider:

~~~java
package com.example.card;

import com.example.spi.PaymentProvider;

public final class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }
}
~~~

Trong mô hình classpath, provider thường được khai báo bằng file:

~~~text
META-INF/services/com.example.spi.PaymentProvider
~~~

Nội dung:

~~~text
com.example.card.CardPaymentProvider
~~~

Ứng dụng có thể nạp:

~~~java
ServiceLoader<PaymentProvider> loader =
        ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : loader) {
    System.out.println(provider.name());
}
~~~

Cơ chế này vẫn hữu ích trên classpath sau khi nâng JDK. Khi chưa chuyển sang named modules, không bắt buộc khai báo `uses` hoặc `provides ... with` trong `module-info.java`.

Tuy nhiên, service loading có thể gặp lỗi nếu:

- Resource `META-INF/services` bị mất khi tạo fat JAR.
- Plugin JAR không có trên runtime classpath.
- Class loader dùng để tìm provider không nhìn thấy JAR.
- Một plugin phụ thuộc JDK internal API hoặc library đã thay đổi.
- Thư viện được chuyển sang module path nhưng cấu hình SPI chưa tương thích.

Khi chuyển provider sang named module thực sự, cơ chế `provides ... with` và `uses` trở nên quan trọng. Đây là một phạm vi riêng cần test, không nhất thiết phải làm trong cùng release nâng JDK.

## 10. Context class loader, application server và framework

Hệ thống Java không phải lúc nào cũng chỉ có một class loader. Servlet container, application server, plugin host, testing framework và nhiều công cụ khác sử dụng hierarchy hoặc class loader riêng để cô lập ứng dụng.

Một số vấn đề dễ xuất hiện trong migration:

- `Class.forName(...)` dùng class loader không nhìn thấy dependency.
- Thread context class loader (TCCL) khác với loader đã nạp mã gọi.
- Serializer hoặc SPI plugin được nạp qua TCCL và thiếu resource.
- Cùng một class có nhiều bản sao do class loader khác nhau nạp, dẫn đến `ClassCastException`.
- Container cung cấp một thư viện runtime khác với phiên bản build.
- Java agent biến đổi bytecode nhưng agent chưa hỗ trợ class-file version JDK mới.

Ví dụ:

~~~java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

Class<?> providerType =
        Class.forName("com.example.card.CardPaymentProvider",
                      true,
                      contextLoader);
~~~

Đây là ví dụ cho thấy một lookup bị phụ thuộc vào class loader; không phải lời khuyên dùng reflection để thay `ServiceLoader`. Khi framework có cấu trúc plugin riêng, hãy theo hợp đồng của framework đó.

Không cần modularize ứng dụng để sửa lỗi TCCL hoặc dependency resolution. Cần hiểu cơ chế class loading đang sử dụng và kiểm chứng cả cấu hình đóng gói lẫn runtime thực tế.

## 11. Build ứng dụng không modularize bằng Gradle

Ứng dụng Java truyền thống có thể giữ `src/main/java` như cũ, không tạo `module-info.java`. Trong Gradle, chọn JDK toolchain và Java release mục tiêu phù hợp:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

application {
    mainClass = 'com.example.orders.Main'
}
~~~

Ý nghĩa:

- Toolchain chọn compiler/JDK cho các task hỗ trợ Java toolchain.
- `options.release = 17` giới hạn source syntax, class-file target và Java SE API đích của mã được biên dịch.
- Không có `module-info.java`, nên ứng dụng vẫn sử dụng mô hình classpath.
- `mainClass` xác định entry point, không biến ứng dụng thành named module.

Với code chạy JDK 17, Gradle wrapper và plugin phiên bản đang dùng phải hỗ trợ JDK 17. Cần kiểm tra JDK của Gradle daemon, compiler toolchain và runtime test; các giá trị có thể khác nhau tùy cấu hình.

Một thư viện có class file yêu cầu Java 21 vẫn có thể khiến ứng dụng chạy trên Java 17 lỗi dù `options.release = 17`; tùy chọn này không tự ép các dependency bên ngoài xuống class-file target 17.

### 11.1. Kiểm tra dependency graph

Các lệnh tham khảo:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Đặc biệt kiểm tra các thư viện reflection, ORM, bytecode, logging, servlet, XML, serialization và database driver. Nếu khác biệt giữa compile và runtime classpath, cần sửa dependency configuration trước khi quy lỗi cho JPMS.

## 12. Build bằng Maven vẫn có thể dùng classpath

Với Maven, cấu hình compiler release nhưng không bắt buộc viết module descriptor:

~~~xml
<project>
    <!-- Các phần cấu hình project khác được lược bỏ -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

Đây là đoạn cấu hình minh họa, không phải một `pom.xml` hoàn chỉnh. Maven Compiler Plugin và JDK compiler cần hỗ trợ lựa chọn release tương ứng.

Nếu sử dụng plugin test, packaging, shading, bytecode weaving hoặc code generation, phải kiểm tra khả năng tương thích của từng plugin với JDK mục tiêu. Ví dụ, một plugin test runner quá cũ có thể làm test không được phát hiện hoặc thất bại khi khởi động forked JVM; đó là lỗi toolchain chứ không nhất thiết do module system.

Khi build output là executable JAR hoặc WAR, kiểm tra deployment runtime thực tế và cách dependencies được cung cấp. `java -jar` có cơ chế chọn entry point và classpath khác với việc chạy `java -cp ... Main` tùy manifest/launcher; đừng đổi hình thức chạy đồng thời với nâng JDK nếu không cần thiết.

## 13. Dùng jdeps để khảo sát trước khi quyết định modularization

`jdeps` là công cụ phân tích dependency tĩnh hữu ích khi khảo sát hệ thống Java. Nó giúp phát hiện phụ thuộc giữa package/module và một số truy cập vào JDK internal APIs.

Ví dụ:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu muốn phân tích cả library dependency:

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

Để quan sát dependency ở mức module Java:

~~~bash
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Các tùy chọn cần được dùng theo định dạng artifact thực tế. Nếu JAR sử dụng multi-release structure, có thể cần `--multi-release` với release phù hợp để phân tích phần class tương ứng.

Điều quan trọng là hiểu giới hạn:

- `jdeps` không phát hiện đầy đủ class name được tạo động từ string.
- Reflection không có tham chiếu tĩnh có thể bị bỏ sót.
- Resource/config, service provider, JNI/native dependency không được mô hình hóa đầy đủ.
- Phân tích trên một JAR đơn lẻ không chứng minh toàn bộ runtime classpath đúng.
- Output phân tích không thay thế integration tests trên JDK mục tiêu.

Nếu `jdeps` chỉ ra `JDK internal API`, hãy xác định thư viện nào sử dụng, tìm API thay thế và phiên bản dependency mới thay vì thêm `--add-exports` hàng loạt.

### 13.1. Một số công cụ hỗ trợ khác

| Công cụ/lệnh | Mục đích |
|---|---|
| `java -version` | Kiểm tra JVM thực sự đang chạy |
| `javac -version` | Kiểm tra compiler khi cần |
| `java --list-modules` | Liệt kê các module mà runtime cung cấp |
| `jar --describe-module --file lib.jar` | Xem thông tin module của JAR khi phù hợp |
| `javap -verbose SomeClass` | Quan sát major version của class file |
| `jdeprscan app.jar` | Tìm một số API đã deprecated trong bytecode |
| `jdeps --jdk-internals app.jar` | Phân tích một số phụ thuộc JDK internal APIs |

Đừng coi `java --list-modules` là danh sách module đang được resolve cho ứng dụng. Đó là thông tin về các module hiện có trong runtime image, còn module resolution của một lần chạy phụ thuộc entry point và tham số.

## 14. Lập kế hoạch nâng JDK theo giai đoạn, không ép modularize

Một phương án thực tế nên giảm số biến thay đổi trong mỗi bước.

### Giai đoạn A — Chụp baseline

Ghi lại:

- JDK vendor/version và JVM flags.
- Mã nguồn, commit, compiler release và class-file target.
- Gradle/Maven wrapper, plugin versions và dependency graph.
- Cấu trúc artifact, classpath và deployment command.
- Chức năng quan trọng, thời gian khởi động, latency và resource metrics.
- Các cảnh báo illegal reflective access hoặc JDK internal API nếu hiện có.

Nếu đang dùng JDK 8, không thể lấy “warning JPMS” từ runtime cũ vì JPMS chưa xuất hiện. Hãy dùng phân tích tĩnh, dependency release notes và thử chạy trên JDK mới để nhận diện vấn đề.

### Giai đoạn B — Nâng build tool và dependency cần thiết

Trước hoặc cùng lúc với JDK migration, xác định phiên bản framework, test runner, bytecode library, annotation processor và driver hỗ trợ runtime mới. Với thư viện đã lỗi thời, ưu tiên bản cập nhật có tương thích chính thức.

Cần ghi rõ khi nào update dependency làm thay đổi hành vi ứng dụng, không nhầm mọi regression thành tác động trực tiếp của JDK.

### Giai đoạn C — Chạy bằng classpath trên JDK mới

Giữ mô hình chạy:

~~~bash
java -cp "app.jar:lib/*" com.example.orders.Main
~~~

Kiểm tra startup, health, framework initialization, các luồng nghiệp vụ, serialization, database, message broker và external services. Nếu đang dùng Spring Boot hoặc launcher đặc thù, giữ đúng launcher của artifact thay vì thay đổi sang câu lệnh classpath trên chỉ để “thử JPMS”.

### Giai đoạn D — Xử lý lỗi theo nhóm

Với mỗi lỗi, xác định nó phát sinh do:

1. API/class đã bị gỡ khỏi JDK.
2. Reflection bị chặn.
3. Bytecode quá mới so với JVM.
4. Thư viện không tương thích hoặc dependency conflict.
5. Class loader, service provider hoặc resource.
6. Build/test plugin không hỗ trợ JDK.
7. Thay đổi cấu hình và semantics của framework/JDK.

Ưu tiên giải pháp tương thích lâu dài: nâng thư viện, đổi API nội bộ sang public API, bổ sung dependency còn thiếu. Chỉ dùng JVM module overrides có chọn lọc nếu chưa thể xử lý dứt điểm.

### Giai đoạn E — Xác minh ổn định

Chạy unit tests, integration tests, smoke tests và workload tương đương baseline. Đọc error logs, GC/resource metrics, kiểm tra memory leak, connection pools và startup. Không chỉ xem exit code của build.

### Giai đoạn F — Xem xét JPMS riêng

Khi runtime mới đã ổn định, đánh giá lợi ích thực tế của named modules: API boundaries, strong encapsulation ở mức ứng dụng, plugin architecture, `jlink` hoặc yêu cầu triển khai. Chỉ modularize nếu lợi ích và chi phí hợp lý.

## 15. Ví dụ chẩn đoán: ba sự cố dễ bị nhầm với nhau

### Trường hợp 1: InaccessibleObjectException

Log:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Hướng điều tra: thư viện nào đang deep reflect vào `java.lang`? Version đó có hỗ trợ JDK mới không? Có thể đổi thư viện hoặc dùng public API không? Nếu chưa, một `--add-opens` đúng package có thể là workaround tạm thời, phải ghi log rủi ro và hướng loại bỏ.

### Trường hợp 2: ClassNotFoundException với JAXB

Log rút gọn:

~~~text
java.lang.ClassNotFoundException: javax.xml.bind.JAXBContext
~~~

Hướng điều tra: ứng dụng có phụ thuộc JAXB vốn được JDK 8 cung cấp không? Trên JDK 11+, cần API và implementation dependency tương ứng. `--add-opens` không tạo ra class đã thiếu. Cũng không dùng `--add-modules java.xml.bind` nếu module đó đã bị loại bỏ khỏi JDK hiện tại.

### Trường hợp 3: UnsupportedClassVersionError

Log:

~~~text
java.lang.UnsupportedClassVersionError:
class file version 65.0; runtime recognizes versions up to 61.0
~~~

Đây là class file Java 21 đang được nạp bởi Java 17. Hướng điều tra: artifact hoặc dependency nào được biên dịch với target 21; runtime production có đúng JDK mục tiêu không; có cần hạ compiler target hoặc nâng runtime không. Đây không phải lỗi JPMS package visibility.

## 16. Bảng quyết định dùng flag, đổi dependency hay modularize

| Quan sát | Hành động ưu tiên | Điều không nên làm |
|---|---|---|
| Framework cũ gọi `sun.*` | Nâng framework hoặc thay public API | Thêm `--add-exports` cho tất cả package |
| Lỗi deep reflection vào JDK | Nâng thư viện, hạn chế reflection; workaround `--add-opens` đúng phạm vi nếu cần | Mở toàn bộ module vô điều kiện |
| JAXB/JAX-WS biến mất | Bổ sung API/implementation dependency tương thích | Dùng `--add-modules` cho module không còn tồn tại |
| Bytecode mới hơn runtime | Đồng bộ target/toolchain/runtime/dependency | Đổi package access flags |
| Lỗi service provider | Kiểm tra `META-INF/services`, TCCL, packaging | Bắt buộc tạo module-info.java |
| Split package trên module path | Giữ classpath trong giai đoạn đầu, sau đó chỉnh dependency/package khi modularize | Đưa mọi JAR lên module path cùng lúc |
| Cần đóng gói modular runtime | Phân tích module graph và nghiên cứu `jlink` riêng | Giả định mọi fat JAR đều là module |
| Không có lỗi module sau nâng JDK | Giữ kiến trúc hiện tại nếu đáp ứng yêu cầu | Modularize chỉ vì JDK mới hỗ trợ JPMS |

Các JVM flags vẫn là thay đổi đáng kể với deployment. Nếu dùng, ghi rõ lý do, nguồn lỗi, nơi cấu hình, môi trường áp dụng và điều kiện gỡ bỏ. Các flag truyền vào JVM trong CI, IDE, container, launcher và production cần đồng nhất.

## 17. Kiểm thử tương thích khi chưa có module-info.java

Một ma trận kiểm thử có thể theo dõi độc lập những lớp bằng chứng:

| Lớp kiểm tra | Câu hỏi | Bằng chứng |
|---|---|---|
| Build tool | Gradle/Maven và plugin hỗ trợ JDK mới? | Build logs và tool version |
| Compiler | Source và API target đúng? | `--release`, compile report |
| Bytecode | Class/JAR phù hợp runtime? | `javap`, dependency metadata |
| Startup | Runtime nạp và khởi tạo ứng dụng? | Startup log, health check |
| Reflection | Framework/ORM/serializer hoạt động? | Integration tests, không có inaccessible access |
| Class loading | SPI/plugin/resources tìm thấy? | ServiceLoader tests, package/dependency report |
| Chức năng | Đầu ra và dữ liệu có giữ semantics? | Test cases, đối soát dữ liệu |
| Hiệu năng | Có regression đáng kể? | Latency, throughput, CPU, memory baseline |
| Deployment | Image/script dùng đúng JDK và flags? | Deployment manifest, `java -version` |

Nếu chạy ứng dụng trên nhiều JDK trong thời gian chuyển tiếp, kiểm tra từng JDK được công bố hỗ trợ. Việc một ứng dụng build bằng JDK mới không chứng minh nó chạy trên mọi JDK cũ, trừ khi source, bytecode, Java SE API và dependencies đều phù hợp.

Cũng cần xác minh test đang chạy trên đúng JVM mục tiêu. Gradle toolchain compile và test launcher có thể là những JVM khác nhau khi cấu hình không đồng nhất.

## 18. Những giới hạn của cách “cứ giữ classpath”

Giữ classpath giúp giảm công việc modularization, nhưng không tự động giải quyết những vấn đề sau:

- Dependency conflict và duplicate classes.
- Class loader leak, classpath ordering và resource collision.
- Quyền reflection vào JDK internals.
- API bị gỡ hoặc đổi semantics.
- Plugin/test runner không hỗ trợ Java mới.
- Việc tạo runtime image tối ưu theo module graph.
- Khả năng khai báo strong encapsulation giữa các package ứng dụng.

Nếu có nhu cầu kiểm soát dependency và public API chặt chẽ ở cấp module, named modules là một lựa chọn kiến trúc đáng cân nhắc. Nhưng một migration an toàn có thể hoàn thành giai đoạn **nâng JDK** trước rồi mới lên kế hoạch **chuyển sang JPMS** sau.

Nếu ứng dụng chỉ dùng classpath và một vài thư viện cần module overrides, hãy xác minh runtime của từng service thay vì áp một tập flags chung lên toàn hệ thống. Điều này giúp giảm bề mặt mở quyền và dễ truy vết.

## 19. Khi nào nên lên kế hoạch chuyển sang JPMS đầy đủ?

Modularization có thể đem lại lợi ích khi hệ thống:

- Muốn có dependency graph và API boundaries rõ ràng.
- Có thư viện nội bộ cần công bố interface ổn định.
- Có nhu cầu đóng gói custom runtime image thông qua hệ module.
- Được thiết kế mới theo hướng module boundary.
- Có đội ngũ đủ khả năng xử lý module path, split package và dependency tương thích.

Chi phí thực tế gồm:

- Tạo và duy trì `module-info.java` cho các module.
- Xác định `requires`, `exports`, `opens` và `uses/provides`.
- Xử lý dependency chưa modularize hoặc automatic module name không ổn định.
- Xử lý split package và package private access giữa module.
- Kiểm tra reflection, serializer, DI, ORM, service loader và test framework.
- Điều chỉnh packaging, IDE, CI và deployment commands.

Nếu team quyết định modularize, nên làm theo từng module có ranh giới rõ, kiểm tra test suite, và chỉ thay đổi một phần kiến trúc trong mỗi giai đoạn. Không phải tất cả library và application service đều cần thành named module ngay lập tức.

## 20. Mẫu nhật ký migration không chuyển JPMS

Một báo cáo ngắn có thể ghi:

~~~yaml
system: orders-service
before:
  jdk: "8"
  launchMode: classpath
  namedApplicationModules: false
after:
  jdk: "17"
  launchMode: classpath
  namedApplicationModules: false
build:
  compilerRelease: 17
  dependencyReview: completed
compatibility:
  jdkInternalsScan: completed
  removedApisReview: completed
  reflectiveAccessTests: completed
  startupTests: passed
  businessFlows: passed
  performanceBaselineCompared: true
temporaryJvmOverrides: []
decision:
  jpmsMigration: deferred
  rationale: "JDK migration completed separately; no current module boundary requirement"
~~~

Đây là **mẫu cấu trúc**, không phải dữ liệu kiểm thử có thật. Những giá trị `passed` hoặc `completed` chỉ được ghi khi nhóm đã thực sự thực hiện bước tương ứng. Nếu cần workaround `--add-opens`, hãy ghi package, nguyên nhân, phạm vi môi trường và ticket loại bỏ trong `temporaryJvmOverrides`.

## 21. Nguyên tắc kết luận

- Nâng JDK và chuyển toàn bộ ứng dụng sang JPMS không phải cùng một công việc.
- Ứng dụng truyền thống vẫn có thể chạy trên classpath sau Java 9 mà không cần `module-info.java`.
- Classpath code nằm trong unnamed module nhưng vẫn phải tuân theo ranh giới package của JDK named modules.
- `--add-opens` hỗ trợ deep reflection; `--add-exports` hỗ trợ truy cập public API trong package không export. Không dùng chúng bừa bãi hoặc xem là giải pháp lâu dài.
- API/JDK module đã bị gỡ không thể hồi phục chỉ bằng module flags; cần dependency hoặc cơ chế thay thế.
- Không nên vô tình chuyển JAR từ classpath sang module path trong cùng bước nâng JDK nếu không có kế hoạch xử lý module graph.
- Class loader, ServiceLoader, reflection và dependency vẫn phải được kiểm thử trên runtime mục tiêu.
- `jdeps` và các công cụ tĩnh rất hữu ích nhưng không thay thế được startup/integration test.
- Có thể tách roadmap thành hai mốc: **runtime upgrade trước**, **modularization sau** nếu có nhu cầu thực tế.

Một đợt Java Compatibility Migration có thể thành công mà ứng dụng vẫn chưa sử dụng named modules. Mục tiêu của giai đoạn nâng JDK là bảo đảm mã nguồn, dependency, bytecode, framework và hành vi runtime tương thích với JDK mới. Khi phạm vi này được ổn định và có bằng chứng kiểm thử đầy đủ, nhóm có thể quyết định có chuyển toàn bộ hoặc một phần ứng dụng sang JPMS hay tiếp tục vận hành bằng classpath theo yêu cầu sản phẩm.
