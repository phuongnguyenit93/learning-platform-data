# Giữ hợp đồng API, không phụ thuộc cấu trúc nội bộ của JDK

Reflection cho phép chương trình Java xem thông tin về class, constructor, field, method, annotation và gọi thành phần theo cách động. Khả năng này hữu ích cho dependency injection, serialization, mapping, plugin, test framework và nhiều thư viện nền tảng. Nhưng **có thể nhìn thấy một thành phần bằng reflection không có nghĩa thành phần đó là API được hỗ trợ để ứng dụng phụ thuộc lâu dài**.

Java phân biệt API công khai được đặc tả với chi tiết triển khai nội bộ. Tên field, class implementation, thứ tự method, cấu trúc cây kế thừa hoặc private member của JDK có thể thay đổi giữa các phiên bản, vendor hay cách triển khai. Java Platform Module System (JPMS) còn đặt ranh giới rõ hơn giữa package được export cho truy cập thông thường và package được open cho deep reflection.

Với Java 17, nguyên tắc thực tế là: **thiết kế dựa trên hợp đồng API công khai; dùng reflection để khám phá hợp đồng được công bố; chỉ mở quyền truy cập sâu cho package ứng dụng thật sự cần; không biến cấu trúc nội bộ của JDK thành dependency của sản phẩm**.

## 1. API công khai và chi tiết triển khai là hai thứ khác nhau

Một API là hợp đồng mà nhà cung cấp công bố để người dùng gọi. Hợp đồng đó xác định các kiểu, phương thức, tham số, kết quả, ngoại lệ và hành vi được hỗ trợ. Chi tiết triển khai là cách thư viện thực hiện hợp đồng bên trong.

Ví dụ với collection:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
~~~

Ứng dụng phụ thuộc vào hợp đồng List: thêm phần tử, đọc phần tử, lấy kích thước. Nó không cần biết ArrayList lưu phần tử trong một mảng nội bộ tên elementData, capacity tăng theo công thức nào hoặc có field nào khác.

Thiết kế tốt:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
~~~

Thiết kế dễ vỡ:

~~~java
Field field = ArrayList.class.getDeclaredField("elementData");
field.setAccessible(true);
Object[] internalArray = (Object[]) field.get(names);
~~~

Đoạn thứ hai dựa vào một tên field riêng tư và cơ chế lưu trữ của một implementation cụ thể. Một JDK khác có thể đổi tên field, đổi cấu trúc, áp dụng module boundary hoặc thay đổi cách truy cập. Ứng dụng cũng có thể vô tình phụ thuộc vào chi tiết về capacity, layout và thời điểm cấp phát mà API List không hứa hẹn.

### Hợp đồng API gồm những gì?

Khi dùng một thư viện, cần phân biệt:

| Thành phần | Có thể là hợp đồng? | Cách đánh giá |
| --- | --- | --- |
| Kiểu public được tài liệu Java SE công bố | Có | Dựa vào Java API specification/Javadoc |
| Method public trong package được export | Thường có, nếu được tài liệu hỗ trợ | Kiểm tra module, tài liệu và chính sách tương thích |
| Annotation được thư viện công bố | Có thể có | Tuân thủ mục đích và retention/target của annotation |
| Interface/SPI được công bố | Có | Implement theo hợp đồng và quy tắc lifecycle |
| Private field/method của class JDK | Không | Chi tiết triển khai, không dựa vào |
| Tên class trong package nội bộ của JDK | Không phải API Java SE ổn định | Tránh phụ thuộc |
| Thứ tự trả về từ getDeclaredFields() | Không được bảo đảm | Không dùng làm thứ tự serialization hoặc logic |
| Field tổng hợp do compiler tạo | Không | Không giả định tồn tại hay tên cố định |
| Cách một collection/stream được tối ưu nội bộ | Không | Đo qua API được công bố, không đọc implementation |

Một thành phần có modifier public chưa chắc đã là API công khai có thể truy cập từ module khác. Nếu package không được export, module system có thể chặn truy cập thông thường. Và ngay cả khi reflection có thể quan sát tên của một class, điều đó cũng không tạo ra cam kết tương thích cho class đó.

## 2. Public Java API và JDK internals

Java SE công bố các API nền tảng như java.lang, java.util, java.time, java.net, java.nio.file và nhiều package khác. Những API này được mô tả trong Java SE specification/Javadoc. JDK cũng chứa các package phục vụ triển khai, công cụ hoặc nội bộ runtime.

Ví dụ, khi cần:

- Làm việc với file và thư mục: dùng java.nio.file.Path, Files, FileSystem.
- Làm việc với tiến trình: dùng ProcessBuilder và ProcessHandle.
- Làm việc với ngày giờ: dùng java.time.
- Gửi HTTP: dùng java.net.http.HttpClient.
- Làm việc với thread, memory pool và GC metrics ở mức quản trị được công bố: xem java.lang.management và ManagementFactory.
- Làm việc với socket: dùng java.net hoặc java.nio.channels.

Không truy cập các class private/internal chỉ vì chúng đang thực hiện đúng việc ứng dụng cần. API công khai thường cung cấp hành vi ổn định hơn, có tài liệu và có thể được thay thế bằng implementation khác.

### Vì sao package nội bộ không phải API để ứng dụng phụ thuộc?

Một JDK có thể chứa các package như jdk.internal.* hoặc các class implementation khác để thực hiện runtime. Chúng có thể:

- Đổi tên hoặc di chuyển package.
- Thay đổi cấu trúc class và field.
- Đổi thuật toán hoặc cách lưu trạng thái.
- Không được export từ module chứa chúng.
- Bị giới hạn truy cập reflection bởi module system.
- Biến mất hoặc thay đổi giữa các bản JDK và nhà cung cấp.

Nếu ứng dụng phụ thuộc vào một thành phần như vậy, việc nâng JDK có thể làm ứng dụng không biên dịch, không khởi động hoặc ném lỗi truy cập runtime. Đây là dấu hiệu thiết kế đang phụ thuộc implementation thay vì hợp đồng.

### sun.* và jdk.internal.* không phải lựa chọn thay thế API công khai

Tên package không tự nói hết mức hỗ trợ, nhưng ứng dụng không nên xem các package nội bộ là API Java SE. Một số package nội bộ lịch sử vẫn được giữ lại cho mục đích tương thích đặc biệt; sự tồn tại của chúng không có nghĩa ứng dụng mới nên phụ thuộc vào chúng.

Không nên chọn một class trong sun.* hoặc jdk.internal.* chỉ vì nó có method tiện lợi hơn API được công bố. Nếu cần chức năng chưa có API công khai, hãy đánh giá thư viện được hỗ trợ, thiết kế lại abstraction hoặc xác định rõ giới hạn triển khai; đừng giả định internal API là hợp đồng lâu dài.

## 3. Java Platform Module System và ranh giới truy cập

Từ Java 9, ứng dụng có thể tổ chức thành module. Mỗi module khai báo các module phụ thuộc và package được công bố trong module-info.java.

Ba khái niệm cần phân biệt:

- **Readability**: module có đọc được module khác hay không, thường qua requires.
- **Exports**: package được công bố cho truy cập thông thường tới public type/member.
- **Opens**: package cho phép deep reflection lúc runtime.

### exports cho truy cập thông thường

Module thư viện:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module ứng dụng:

~~~java
module com.example.application {
    requires com.example.domain;
}
~~~

Ứng dụng có thể import và gọi public type trong com.example.domain.api. Các package khác của module domain không tự động được công bố.

exports không có nghĩa mọi private field trong package đều có thể được reflection truy cập. Nó công bố public API theo quy tắc module, không mở toàn bộ implementation.

### opens cho deep reflection

Một framework có thể cần truy cập constructor hoặc field không public của class ứng dụng. Nếu module ứng dụng kiểm soát package đó, có thể mở đúng package cho đúng module framework:

~~~java
module com.example.application {
    requires com.example.framework;

    opens com.example.application.persistence
            to com.example.framework;
}
~~~

opens cho phép reflection sâu vào package ở runtime đối với module đích được chỉ định. Nó không thay thế exports để module khác import public type trong package như một API thông thường.

### Qualified exports và qualified opens

Có thể giới hạn bên nhận:

~~~java
module com.example.model {
    exports com.example.model.api
            to com.example.application;

    opens com.example.model.persistence
            to com.example.orm;
}
~~~

Trong ví dụ:

- com.example.application có thể truy cập public API trong package com.example.model.api.
- com.example.orm được phép deep reflection vào package persistence.
- Các module khác không nhận những quyền đó chỉ vì biết tên package.

Đây là cách thu hẹp quyền truy cập thay vì mở toàn bộ module.

### open module có phạm vi rộng

Khai báo:

~~~java
open module com.example.model {
    requires com.example.framework;
}
~~~

Mở tất cả package của module cho deep reflection. Nó không tự động export tất cả package cho truy cập Java thông thường. Chỉ dùng khi framework thực sự cần phạm vi rộng và module owner chấp nhận hợp đồng đó; nếu có thể, mở package cụ thể bằng opens p to m.

## 4. Strong encapsulation trong Java 17

Java 17 áp dụng strong encapsulation cho các thành phần nội bộ của JDK theo JEP 403. Những cơ chế truy cập nội bộ từng được nới lỏng trong các phiên bản chuyển tiếp không còn là nền tảng đáng tin cậy cho ứng dụng.

Trước module system, nhiều thư viện dùng reflection để truy cập private member của JDK. Từ Java 9, module boundary dần được áp dụng; Java 16 đặt mặc định strong encapsulation, và Java 17 tiếp tục đóng ranh giới này theo mặc định.

Hệ quả thực tế:

- Reflection vào private member của package JDK không được mở có thể thất bại.
- setAccessible(true) có thể ném InaccessibleObjectException.
- trySetAccessible() có thể trả về false.
- Thư viện cũ có thể chạy trên JDK trước đó nhưng lỗi khi nâng lên Java 17.
- Không nên xử lý lỗi bằng cách mở toàn bộ package nội bộ của JDK một cách vô điều kiện.

### --illegal-access không phải giải pháp cho Java 17

Trong các JDK chuyển tiếp, tùy chọn --illegal-access từng điều khiển chế độ tương thích truy cập reflection vào một số package nội bộ. Từ Java 17, tùy chọn này không còn khôi phục cơ chế nới lỏng đó; nó được giữ để tương thích khi khởi chạy và phát cảnh báo, nhưng không làm các package JDK đóng trở lại thành package có thể deep-reflect tùy ý.

Do đó, không nên thêm --illegal-access=permit vào script để mong ứng dụng cũ hoạt động trên Java 17.

### Vì sao nâng thư viện thường là hướng đúng?

Nếu framework ORM, serializer, dependency injection hoặc mocking library cố truy cập private member của JDK, lỗi thường nằm ở phiên bản thư viện chưa hỗ trợ strong encapsulation. Cách xử lý ưu tiên:

1. Nâng lên phiên bản thư viện hỗ trợ Java 17.
2. Dùng API extension/configuration được thư viện công bố.
3. Thay cách tích hợp để không cần đọc implementation JDK.
4. Chỉ dùng --add-opens cho package ứng dụng mà bạn sở hữu khi framework cần deep reflection và đã có lý do rõ ràng.

Mở package JDK bằng tùy chọn JVM có thể là biện pháp chuyển tiếp trong một hệ thống cũ đã được đánh giá, nhưng tạo ra phụ thuộc vào implementation và làm giảm tính đóng gói. Nó không biến API nội bộ thành hợp đồng ổn định.

## 5. Phân biệt exports, opens, --add-exports và --add-opens

Các khai báo module và tùy chọn launcher có mục đích khác nhau:

| Cơ chế | Thời điểm/phạm vi | Cho phép điều gì? |
| --- | --- | --- |
| exports p; | module-info.java | Truy cập thông thường đến public type/member trong package p từ module đọc module này |
| exports p to m; | module-info.java | Chỉ module m nhận quyền truy cập thông thường |
| opens p; | module-info.java | Deep reflection vào package p tại runtime từ các module khác |
| opens p to m; | module-info.java | Deep reflection vào package p cho module m |
| open module x {} | module-info.java | Mở tất cả package của module x cho deep reflection |
| --add-exports source/package=target | JVM/compiler launcher | Bổ sung export cho public type/member của package tới target module |
| --add-opens source/package=target | JVM runtime launcher | Mở package cho deep reflection tới target module |

--add-exports không tự cho phép truy cập private field. --add-opens cho phép deep reflection nhưng không phải cách để import public type từ package không export trong mã nguồn thông thường.

Ví dụ cú pháp:

~~~bash
java --add-exports source.module/internal.package=target.module ...
java --add-opens source.module/internal.package=target.module ...
~~~

Nếu ứng dụng chạy trên classpath, target thường có thể là ALL-UNNAMED:

~~~bash
java --add-opens source.module/internal.package=ALL-UNNAMED -jar app.jar
~~~

Đây là cú pháp minh họa cho việc cấu hình module. Không dùng tên module/package giả định trong sản phẩm; chỉ cấu hình package cụ thể sau khi xác định thư viện nào cần quyền và tại sao.

### Vì sao không nên mở rộng toàn bộ?

Một tùy chọn như:

~~~bash
java --add-opens java.base/java.util=ALL-UNNAMED -jar app.jar
~~~

có thể cho phép các thư viện trên classpath deep-reflect vào package java.util trong phạm vi runtime được mở. Nhưng ứng dụng đã tạo thêm dependency vào cấu trúc nội bộ của package này. JDK có thể thay đổi implementation và ứng dụng sẽ khó nâng cấp hơn.

Nếu một framework cần quyền này, hãy xác định chính xác class/field nào đang bị truy cập, kiểm tra phiên bản framework, tìm cấu hình được hỗ trợ và thu hẹp phạm vi mở. Không thêm nhiều --add-opens theo kiểu thử đến khi hết lỗi mà không ghi nhận chủ sở hữu và lý do.

## 6. Reflection có thể truy cập gì?

Reflection cung cấp API như:

- Class.getMethods() và getMethod(...): xem public method, bao gồm method kế thừa.
- Class.getDeclaredMethods() và getDeclaredMethod(...): xem method được khai báo trực tiếp trong class, kể cả non-public nếu có quyền quan sát metadata.
- Class.getFields() và getField(...): xem public field, bao gồm field kế thừa.
- Class.getDeclaredFields() và getDeclaredField(...): xem field khai báo trực tiếp.
- Class.getConstructors() và getDeclaredConstructors(): xem constructor public hoặc constructor được khai báo.
- Class.getAnnotations() và getDeclaredAnnotations(): đọc annotation theo các quy tắc kế thừa/khai báo.
- Method.invoke(...), Constructor.newInstance(...), Field.get(...) và Field.set(...): thực hiện thao tác reflection khi access check cho phép.

Có thể lấy metadata về thành viên private mà không đồng nghĩa được phép đọc hoặc sửa chúng. **Khả năng liệt kê metadata và quyền truy cập thành viên là hai vấn đề riêng**.

### Public reflection không cần phá encapsulation

Ví dụ:

~~~java
import java.lang.reflect.Method;

public class PublicReflectionDemo {
    public static void main(String[] args) {
        for (Method method : String.class.getMethods()) {
            if (method.getName().equals("isBlank")) {
                System.out.println(method);
            }
        }
    }
}
~~~

String.isBlank() là public API được công bố. Reflection chỉ khám phá và hiển thị thông tin về method public; không cần setAccessible(true).

### getDeclaredMethods() không bảo đảm thứ tự

Không nên viết:

~~~java
Method first = SomeType.class.getDeclaredMethods()[0];
~~~

và giả định phần tử đầu tiên luôn là method mong muốn. Java không bảo đảm thứ tự của các method/field trả về từ những API reflection này. Hãy tìm bằng tên, tham số và kiểu trả về hoặc, tốt hơn, dùng annotation/interface được công bố để xác định vai trò.

Ngoài ra, reflection có thể hiển thị bridge method hoặc synthetic member do compiler tạo. Framework cần xử lý các cờ isBridge() và isSynthetic() nếu hợp đồng của nó đòi hỏi chỉ xử lý member do người viết khai báo.

### Field và method không phải mô hình dữ liệu công khai

Nếu framework serialize mọi field mà getDeclaredFields() trả về, nó đang biến cấu trúc nội bộ thành wire format. Khi đổi tên field, thêm cache hoặc đổi kiểu lưu trữ, JSON/schema có thể thay đổi ngoài ý muốn.

Hãy định nghĩa DTO, record component, getter hoặc annotation serialization được công bố làm hợp đồng dữ liệu. Không suy ra schema công khai từ tất cả field implementation.

## 7. Dùng canAccess, trySetAccessible và setAccessible đúng cách

AccessibleObject cung cấp các API kiểm soát access check:

- canAccess(object): kiểm tra thành viên có thể được truy cập với ngữ cảnh hiện tại hay không.
- trySetAccessible(): thử bỏ qua kiểm tra truy cập Java language access nếu module boundary cho phép; trả true nếu thành công, false nếu không.
- setAccessible(true): yêu cầu bỏ qua kiểm tra truy cập; có thể ném InaccessibleObjectException khi không thể mở quyền.
- setAccessible(false): khôi phục việc kiểm tra access thông thường.

Ví dụ kiểm tra trước:

~~~java
Field field = SomeType.class.getDeclaredField("value");

if (field.trySetAccessible()) {
    Object value = field.get(target);
} else {
    // Không được phép deep-reflect vào thành viên này.
}
~~~

Ví dụ trên chỉ minh họa cơ chế. Trong thiết kế ứng dụng, nếu value là private implementation field của JDK hoặc của thư viện ngoài, không nên coi trySetAccessible() thành công ở một môi trường là bảo đảm nó sẽ luôn thành công ở môi trường khác.

### setAccessible(true) không phải cách sửa mọi lỗi reflection

Nếu package thuộc module không mở cho module của caller, yêu cầu deep reflection có thể bị từ chối. Với thành viên của JDK, ứng dụng không kiểm soát module-info.java của module đó. Không nên cố ép quyền bằng nhiều cách khác nhau hoặc dùng internal API để vượt ranh giới.

Nếu class thuộc module của chính ứng dụng, hãy mở package cần thiết có giới hạn:

~~~java
module com.example.app {
    opens com.example.app.model to com.example.mapper;
}
~~~

Đây là khai báo module có chủ đích, dễ review và quản lý hơn một tập tùy chọn launcher rộng.

## 8. Dùng MethodHandles khi cần lời gọi động có kiểu rõ hơn

java.lang.invoke.MethodHandles cung cấp cơ chế tra cứu và gọi method/constructor/field bằng MethodHandle. Đây là API công khai cho các tình huống invocation động, thường có mô hình kiểu rõ hơn Method.invoke.

Ví dụ gọi public method:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandle length = MethodHandles.publicLookup()
        .findVirtual(
                String.class,
                "length",
                MethodType.methodType(int.class));

int result = (int) length.invokeExact("Java 17");
System.out.println(result);
~~~

findVirtual tìm method public theo tên và MethodType. invokeExact yêu cầu kiểu call-site phù hợp chính xác với kiểu method handle. Đây là một API công khai; ví dụ không cần truy cập private member của JDK.

### Lookup và quyền truy cập

Các lookup phổ biến:

- MethodHandles.lookup() tạo Lookup với quyền gắn với class gọi lookup.
- MethodHandles.publicLookup() chỉ có quyền public theo phạm vi của nó.
- MethodHandles.privateLookupIn(targetClass, lookup) yêu cầu điều kiện module access phù hợp để tạo lookup có quyền riêng tư cho target class.

privateLookupIn không phải lối tắt bỏ qua JPMS. Module caller phải đọc module target và package target phải được mở cho module caller theo quy tắc module system. Nếu package không mở, thao tác có thể ném IllegalAccessException.

### VarHandle cho truy cập biến có kiểu

VarHandle là API công khai từ Java 9 để truy cập biến với các chế độ memory ordering và atomic operation được định nghĩa. Khi cần thao tác với field của class do ứng dụng sở hữu, có thể cân nhắc VarHandle thay vì dùng reflection field thuần.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleDemo {
    static final class Counter {
        private volatile int value;
        private static final VarHandle VALUE;

        static {
            try {
                VALUE = MethodHandles.lookup()
                        .findVarHandle(Counter.class, "value", int.class);
            } catch (NoSuchFieldException | IllegalAccessException ex) {
                throw new ExceptionInInitializerError(ex);
            }
        }

        void set(int newValue) {
            VALUE.set(this, newValue);
        }

        int get() {
            return (int) VALUE.get(this);
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.set(10);
        int current = counter.get();
        System.out.println(current);
    }
}
~~~

Lookup được tạo bên trong Counter nên có quyền truy cập private field của chính class đó. Nếu chuyển lookup sang module/package khác, phải tuân thủ quyền truy cập và opens/exports tương ứng. VarHandle không phải giấy phép đọc private field tùy ý của JDK.

## 9. Thiết kế extension point bằng interface và ServiceLoader

Một lý do phổ biến khiến lập trình viên dùng reflection là muốn tìm implementation theo tên class hoặc tự tạo plugin. Java đã có cách công khai cho nhiều trường hợp như vậy: interface/SPI và ServiceLoader.

Định nghĩa hợp đồng:

~~~java
package com.example.spi;

public interface GreetingProvider {
    String language();
    String greet(String name);
}
~~~

Implementation:

~~~java
package com.example.english;

import com.example.spi.GreetingProvider;

public final class EnglishGreetingProvider
        implements GreetingProvider {

    public String language() {
        return "en";
    }

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Với ứng dụng trên classpath, provider có thể được đăng ký qua file:

~~~text
META-INF/services/com.example.spi.GreetingProvider
~~~

Nội dung file là tên class provider đầy đủ:

~~~text
com.example.english.EnglishGreetingProvider
~~~

Ứng dụng tìm implementation:

~~~java
ServiceLoader<GreetingProvider> providers =
        ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.greet("Lan"));
}
~~~

Với named module, khai báo service trong module-info.java:

~~~java
module com.example.english {
    requires com.example.spi;
    provides com.example.spi.GreetingProvider
            with com.example.english.EnglishGreetingProvider;
}
~~~

Module sử dụng service khai báo:

~~~java
module com.example.application {
    requires com.example.spi;
    uses com.example.spi.GreetingProvider;
}
~~~

ServiceLoader giúp ứng dụng phụ thuộc vào interface và service contract, không phụ thuộc tên class implementation hoặc cấu trúc nội bộ của provider.

## 10. Reflection theo hợp đồng của class ứng dụng

Reflection vẫn hữu ích khi làm việc với class do ứng dụng hoặc framework kiểm soát. Điểm quan trọng là khám phá những gì được công bố rõ ràng: interface, annotation, constructor được hỗ trợ, record component hoặc method có quy ước ổn định.

### Dùng annotation thay vì suy luận từ tên field

Ví dụ annotation đánh dấu method cần gọi:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface OnStart {}
~~~

Framework có thể tìm method được đánh dấu:

~~~java
for (Method method : component.getClass().getMethods()) {
    if (method.isAnnotationPresent(OnStart.class)) {
        if (method.getParameterCount() != 0
                || method.getReturnType() != void.class) {
            throw new IllegalArgumentException(
                    "@OnStart method must have no arguments and return void");
        }
        method.invoke(component);
    }
}
~~~

Hợp đồng ở đây là annotation OnStart cùng quy tắc chữ ký method. Framework không cần đoán method nào là callback từ tên startInternal, thứ tự khai báo hay field riêng.

Nếu framework cần gọi method không public, hãy quyết định rõ đây có phải hợp đồng hỗ trợ hay không. Có thể yêu cầu method public, hoặc yêu cầu module ứng dụng mở package chứa component cho framework. Đừng âm thầm gọi private method chỉ vì reflection cho phép trong một cấu hình cụ thể.

### Dùng record component khi kiểu dữ liệu là record

Java 17 có API Class.getRecordComponents():

~~~java
record UserView(long id, String name) {}

for (RecordComponent component
        : UserView.class.getRecordComponents()) {
    System.out.println(component.getName());
    System.out.println(component.getType().getName());
}
~~~

Record component là một phần của hợp đồng record được công bố. Nếu một framework hỗ trợ record, dùng record component/accessor để ánh xạ dữ liệu thay vì đọc field nội bộ tùy tiện.

### Không giả định mọi class có constructor không tham số

Framework cũ thường giả định mọi class có constructor không tham số và setter cho từng field. Thiết kế hiện đại có thể dùng constructor injection, factory, builder hoặc record canonical constructor. Framework nên hỗ trợ hợp đồng tạo object được công bố thay vì ép class phải mô phỏng một cấu trúc nội bộ.

## 11. Vì sao dựa vào tên field, thứ tự và class implementation dễ vỡ?

Một số dạng phụ thuộc thường gặp:

### Phụ thuộc tên field

~~~java
Field field = SomeJdkClass.class.getDeclaredField("internalState");
~~~

Tên field có thể đổi mà không vi phạm public API. Việc reflection tìm thấy field hôm nay không tạo ra cam kết cho JDK tiếp theo.

### Phụ thuộc thứ tự field/method

~~~java
Field[] fields = SomeType.class.getDeclaredFields();
serialize(fields[0]);
~~~

Thứ tự trả về không được bảo đảm. Nếu thứ tự serialization quan trọng, dùng schema/annotation/order metadata được định nghĩa rõ.

### Phụ thuộc tên implementation class

~~~java
if (value.getClass().getName().contains("ImmutableCollections")) {
    // ...
}
~~~

JDK có thể thay đổi class implementation mà vẫn giữ đúng hành vi List, Set hoặc Map. Hãy kiểm tra contract bằng API như instanceof, method được công bố hoặc thao tác theo interface.

### Phụ thuộc private state để tối ưu

Đọc capacity, lock, cache hoặc cấu trúc node nội bộ có thể làm tối ưu hóa chỉ đúng với một bản JDK. Nếu cần hiệu năng, hãy benchmark qua API công khai, profiling và chọn cấu trúc dữ liệu phù hợp. Không lấy một private field làm chỉ số vận hành.

## 12. API công khai thay thế cho các nhu cầu thường gặp

| Nhu cầu | API công khai nên xem xét | Tránh phụ thuộc |
| --- | --- | --- |
| Đọc/ghi file, metadata file | Path, Files, BasicFileAttributes | Field nội bộ của file provider |
| Theo dõi tiến trình | ProcessHandle, ProcessHandle.Info | Class process nội bộ của JDK |
| Lấy thời gian | Instant, Clock, ZonedDateTime | Clock/private runtime state |
| Gửi HTTP | HttpClient, HttpRequest, HttpResponse | HTTP client implementation nội bộ |
| Quản trị JVM, memory pool, thread | ManagementFactory, java.lang.management | Private field của VM implementation |
| Tạo plugin | Interface/SPI, ServiceLoader | Quét classpath rồi đoán implementation |
| Xử lý cấu hình | API cấu hình được công bố, record/DTO | Reflection vào field private của framework |
| Truy cập member động trong code do mình quản lý | Reflection/MethodHandles theo contract và module access | Dùng internal JDK class để né access check |
| Đọc thông tin record | getRecordComponents() và accessor | Giả định field layout của compiler |
| Thông tin network | NetworkInterface, InetAddress | Private network implementation class |

Nếu không có API công khai đáp ứng nhu cầu, hãy phân biệt rõ chức năng đó là yêu cầu ứng dụng hay chỉ là một tối ưu phụ. Với yêu cầu quan trọng, cân nhắc thư viện có hợp đồng hỗ trợ hoặc thiết kế abstraction để thay thế được. Đừng xây sản phẩm dựa trên một private detail chỉ vì nó có thể được truy cập trong một bản JDK.

## 13. Công cụ phát hiện phụ thuộc vào JDK internals

JDK cung cấp công cụ jdeps để phân tích phụ thuộc ở mức class/package/module. Tùy chọn --jdk-internals giúp phát hiện các phụ thuộc vào internal APIs của JDK trong class hoặc JAR.

Ví dụ:

~~~bash
jdeps --jdk-internals application.jar
~~~

Có thể phân tích cả thư viện phụ thuộc hoặc classpath theo cách phù hợp với cấu trúc build:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

Kết quả giúp xác định class nào phụ thuộc package nội bộ và gợi ý API thay thế trong một số trường hợp. Đây là phân tích tĩnh; nó không phát hiện mọi trường hợp reflection dựa trên tên class/field được tạo động từ cấu hình hoặc chuỗi runtime.

### Tìm kiếm reflection theo chuỗi trong code

Ngoài jdeps, có thể tìm các mẫu đáng xem xét trong source:

- Class.forName("...")
- getDeclaredField(...)
- getDeclaredMethod(...)
- setAccessible(true)
- trySetAccessible()
- MethodHandles.privateLookupIn(...)
- sun.* hoặc jdk.internal.*

Không phải mọi lần dùng reflection đều là lỗi. Mục tiêu là phân loại:

1. Reflection trên API public/annotation/interface được công bố.
2. Reflection vào class do ứng dụng sở hữu và có module opens rõ ràng.
3. Reflection vào private implementation của thư viện ngoài.
4. Reflection vào internal JDK package/member.

Hai nhóm đầu có thể là thiết kế hợp lệ. Hai nhóm sau cần xem xét nâng thư viện, thay API hoặc loại bỏ dependency.

### Kiểm tra khi nâng JDK

Trong CI, nên có một job chạy trên JDK 17 đúng như môi trường mục tiêu, và một bước phân tích dependency với jdeps --jdk-internals cho artifact quan trọng. Test integration nên xác nhận framework serialization, ORM, DI và instrumentation không dựa vào quyền truy cập nội bộ ngoài dự kiến.

jdeps không chứng minh ứng dụng không có mọi dependency runtime. Nó là một công cụ hỗ trợ; cần kết hợp source review, test và kiểm soát dependency.

## 14. Di chuyển thư viện cũ lên Java 17

Khi nâng từ JDK cũ lên Java 17, có thể xuất hiện:

- InaccessibleObjectException khi thư viện gọi setAccessible(true).
- IllegalAccessException khi MethodHandles không có quyền truy cập.
- NoSuchFieldException hoặc NoSuchMethodException do thư viện phụ thuộc tên member nội bộ đã thay đổi.
- ClassNotFoundException hoặc NoClassDefFoundError khi class nội bộ không còn tồn tại hoặc module không được đọc.
- Cảnh báo về internal API khi compile hoặc chạy.

Quy trình xử lý:

1. Đọc stack trace để xác định thư viện và package bị truy cập.
2. Xác định đó là JDK internal hay package thuộc ứng dụng/thư viện.
3. Tra phiên bản thư viện có hỗ trợ Java 17 và nâng cấp.
4. Tìm cấu hình/extension point chính thức để thay thế deep reflection.
5. Nếu package thuộc module của ứng dụng, mở đúng package cho đúng module framework khi thật sự cần.
6. Nếu buộc phải dùng launcher option trong thời gian chuyển tiếp, giới hạn package và target module, ghi rõ lý do, chủ sở hữu và thời hạn loại bỏ.
7. Chạy test trên Java 17 và phân tích dependency với jdeps.

Không thêm hàng loạt --add-opens chỉ để che lỗi khởi động. Làm vậy có thể khiến hệ thống chạy lại trước mắt nhưng giữ nguyên dependency dễ vỡ và tạo gánh nặng khi nâng JDK tiếp theo.

## 15. Bảo mật và ranh giới tin cậy khi dùng reflection

Reflection có thể gọi method, tạo object và đọc dữ liệu theo quyền mà chương trình được cấp. Vì thế, không nên dùng class name, method name hoặc constructor do input không tin cậy cung cấp rồi thực thi trực tiếp.

Ví dụ thiết kế nguy hiểm:

~~~java
Class<?> type = Class.forName(userSuppliedClassName);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Nếu không có allowlist và kiểm soát kiểu, input có thể chọn implementation không mong muốn hoặc kích hoạt class initialization/constructor có tác dụng phụ. Reflection không phải sandbox.

Thiết kế an toàn hơn:

- Định nghĩa interface mà plugin phải triển khai.
- Đăng ký provider bằng ServiceLoader hoặc registry được kiểm soát.
- Chỉ cho phép implementation trong allowlist/cấu hình đáng tin cậy.
- Kiểm tra type và quyền trước khi tạo object.
- Không mở package rộng hơn yêu cầu.
- Không để input bên ngoài quyết định tùy ý method private nào được gọi.

Không dùng setAccessible(true) để vượt qua ranh giới module hoặc ranh giới tin cậy như một cơ chế phân quyền. Access control của Java và authorization nghiệp vụ là hai lớp khác nhau.

## 16. Ví dụ module: export API và open package cho framework

Giả sử có hai module:

~~~text
com.example.app
    com.example.app.api
    com.example.app.persistence

com.example.mapper
~~~

Module ứng dụng:

~~~java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.persistence to com.example.mapper;
}
~~~

Module mapper:

~~~java
module com.example.mapper {
    requires com.example.app;
}
~~~

Public API được export cho các module cần gọi. Package persistence được mở riêng cho mapper để framework có thể deep-reflect lúc runtime. Các package khác vẫn được đóng.

Ví dụ này phù hợp khi persistence object là phần nội bộ của ứng dụng và mapper thực sự cần truy cập constructor/field không public. Nếu mapper hỗ trợ constructor mapping hoặc record component qua public API, có thể không cần opens.

## 17. Checklist thiết kế trước khi dùng deep reflection

Trước khi gọi setAccessible, trySetAccessible hoặc privateLookupIn, hãy xác định:

1. Thành viên này có thuộc API công khai được tài liệu hỗ trợ không?
2. Có interface, annotation, accessor, factory hoặc SPI thay thế không?
3. Class/package có thuộc module mà nhóm ứng dụng kiểm soát không?
4. Module đích có thật sự cần deep reflection hay chỉ cần public API?
5. Có thể dùng qualified opens thay vì mở cả module không?
6. Nếu target là JDK internal, có API Java SE hoặc JDK được tài liệu hỗ trợ đáp ứng không?
7. Nếu đây là thư viện bên ngoài, có phiên bản hỗ trợ Java 17 không?
8. Hành vi có được kiểm thử trên JDK/vendor mục tiêu không?
9. Có công cụ CI để phát hiện dependency vào JDK internals không?
10. Có tài liệu về lý do, phạm vi và kế hoạch bỏ workaround không?

Không phải mọi framework đều có thể hoạt động mà không cần reflection sâu. Điều cần giữ là quyền truy cập phải có chủ đích, đúng package, đúng module và nằm trong hợp đồng mà ứng dụng có thể kiểm soát.

## 18. Các sai lầm thường gặp

| Sai lầm | Vì sao dễ vỡ | Cách làm phù hợp |
| --- | --- | --- |
| Đọc private field của JDK để lấy trạng thái | Field là implementation detail | Tìm API công khai cung cấp thông tin cần thiết |
| Dựa vào tên class implementation của collection | JDK có thể đổi class nội bộ | Dùng interface và hành vi được công bố |
| Dựa vào thứ tự getDeclaredFields() | Thứ tự không được bảo đảm | Dùng tên, annotation hoặc schema rõ ràng |
| Gọi setAccessible(true) trên mọi field | JPMS có thể chặn deep reflection | Chỉ mở package ứng dụng cần thiết hoặc dùng public API |
| Dùng --illegal-access=permit trên Java 17 | Tùy chọn không còn khôi phục cơ chế truy cập cũ | Nâng thư viện và bỏ internal dependency |
| Thêm nhiều --add-opens cho java.base | Mở implementation JDK rộng và khó nâng cấp | Xác định thư viện, thu hẹp quyền hoặc thay API |
| Nghĩ exports cho phép truy cập private | Export và open có mục đích khác nhau | Dùng opens có giới hạn khi cần deep reflection |
| Nghĩ opens cho phép import public type | Opens chỉ phục vụ deep reflection runtime | Dùng exports cho truy cập thông thường |
| Dùng reflection để tạo plugin từ class name tùy ý | Input có thể chọn implementation ngoài dự kiến | Interface, ServiceLoader và allowlist |
| Dùng private implementation để tối ưu | Phụ thuộc vào cấu trúc một JDK cụ thể | Benchmark qua API công khai |
| Cho rằng jdeps phát hiện mọi reflection động | Tên có thể được tạo từ dữ liệu runtime | Kết hợp phân tích tĩnh, source review và test |
| Mở cả module cho framework dù chỉ cần một package | Quyền sâu rộng hơn mức cần thiết | Qualified opens package to module |

## 19. Nguyên tắc thực hành

Khi viết code reflection và truy cập trên Java 17:

1. Dựa trên public API được tài liệu hỗ trợ, interface, annotation và SPI.
2. Không phụ thuộc tên field, method, class implementation hoặc thứ tự thành viên nội bộ của JDK.
3. Phân biệt module readability, exports và opens.
4. Dùng reflection công khai để khám phá hợp đồng; chỉ deep-reflect vào package ứng dụng khi có lý do và quyền module rõ ràng.
5. Dùng MethodHandles/VarHandle khi mô hình invocation hoặc truy cập biến động cần kiểu và semantics rõ hơn.
6. Dùng ServiceLoader hoặc registry thay vì tự dò class implementation để xây plugin.
7. Với lỗi Java 17 strong encapsulation, ưu tiên nâng thư viện và loại bỏ internal dependency.
8. Chỉ dùng --add-exports/--add-opens như biện pháp có phạm vi rõ ràng, không coi đó là hợp đồng API.
9. Dùng jdeps --jdk-internals và test trên JDK mục tiêu để phát hiện phụ thuộc không được hỗ trợ.

Reflection là công cụ mạnh, nhưng ranh giới API mới quyết định ứng dụng có thể nâng cấp an toàn hay không. Khi code phụ thuộc vào hành vi được công bố thay vì cấu trúc nội bộ, ứng dụng có thể thay JDK, đổi implementation và nâng thư viện mà ít bị ảnh hưởng bởi những thay đổi bên trong runtime.

## Tài liệu tham khảo Java 17

- [Java Language Specification, Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html)
- [AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Class reflection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
