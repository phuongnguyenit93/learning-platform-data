# 5.9 Thiết kế API công khai và mở quyền có chủ đích khi xây dựng thư viện động

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 5. Quyền truy cập

Một thư viện động thường cho phép ứng dụng **tìm, nạp, kết nối và gọi** các thành phần được triển khai riêng: plugin, service provider, adapter, bộ xử lý hoặc module mở rộng. Thiết kế đúng đòi hỏi phân biệt **hợp đồng nào được phép sử dụng từ bên ngoài** với **chi tiết triển khai nào chỉ thư viện được quản lý**.

Một nguyên tắc hữu ích: **công khai hợp đồng tối thiểu; chỉ cấp quyền truy cập bổ sung cho bên cần dùng, đúng loại quyền và đúng phạm vi**. Điều này bảo vệ khả năng thay thế implementation, giảm phụ thuộc vô ý giữa module, đồng thời giúp nâng cấp API mà không buộc consumer phải biết cấu trúc nội bộ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn phần nên thuộc **public API/SPI** và phần nên giữ ở **implementation nội bộ** khi thiết kế thư viện động.
2. Phân biệt các lớp kiểm soát quyền: modifier của Java (`public`, `protected`, package-private, `private`), package và class loader, cũng như **JPMS module readability / `exports` / `opens`**.
3. Hiểu trường hợp cần **normal access** (truy cập Java thông thường) khác **deep reflection** (truy cập phản chiếu vào thành viên không công khai).
4. Dùng `uses` / `provides` với `ServiceLoader` để host tiêu thụ SPI mà không phải export package chứa provider.
5. Thử một ví dụ Java 17+ có ba module độc lập; quan sát provider chạy được qua SPI nhưng direct reflection sang package nội bộ bị chặn.
6. Xác định khi nào dùng qualified `exports ... to`, qualified `opens ... to`, hoặc API tường minh thay cho mở quyền quá rộng; nhận diện các sai lầm tương thích và bảo mật.

## 2. Hai biên giới phải thiết kế trước khi viết code

### 2.1. Biên giới hợp đồng: bên ngoài được **phụ thuộc vào điều gì**?

**API công khai (Application Programming Interface)** là tập kiểu và hành vi mà caller được phép sử dụng: interface, class, factory method, DTO, lỗi hợp đồng, thread-safety, quy tắc lifecycle và tính tương thích phiên bản. **SPI (Service Provider Interface)** là hợp đồng dành cho phía *cung cấp triển khai*, chẳng hạn interface `TextPlugin` mà các plugin phải implement.

Một thiết kế thực tế thường chia:

| Thành phần | Có nên công khai? | Lý do |
| --- | --- | --- |
| `TextPlugin` interface ổn định | **Có**, nếu host/plugin độc lập cần compile với nó | Là hợp đồng tương tác |
| Kiểu dữ liệu đầu vào/đầu ra của `TextPlugin` | **Có**, nếu xuất hiện trong chữ ký công khai | Caller phải đọc và sử dụng được |
| Factory hoặc registry được thiết kế rõ | **Có thể** | Là điểm truy cập được hỗ trợ, tránh caller phải đoán tên class |
| `UpperTextPlugin` implementation cụ thể | **Thường không** | Cho phép đổi thuật toán, tên lớp, cấu trúc package |
| Cấu hình parser, cache, trường private, helper | **Không**, trừ khi có nhu cầu tích hợp thực sự | Tránh phụ thuộc vào chi tiết có thể thay đổi |
| Cổng phản chiếu (`opens`) cho framework xử lý dữ liệu | **Chỉ khi cần**, giới hạn package và module đích | Hỗ trợ cơ chế runtime không thể thực hiện chỉ qua hợp đồng bình thường |

**`public` trên một class không đồng nghĩa “đây là API cam kết hỗ trợ dài hạn”.** Trong Java, modifier `public` cho phép truy cập theo ngữ nghĩa ngôn ngữ, nhưng với **named module**, một class public trong package **không được export** vẫn không thể được mã ngoài module nhập/gọi trực tiếp như API bình thường.

### 2.2. Biên giới kỹ thuật: bên ngoài **có thể truy cập bằng cơ chế nào**?

Xem hệ thống quyền như nhiều điều kiện cần kết hợp:

- **Modifier của type/member:** `public`, `protected`, package-private, `private` quy định mức truy cập cơ bản.
- **Package:** các type cùng package có đặc quyền package-level, nhưng trong hệ module không thể coi tên package là cơ chế chia sẻ tùy ý giữa các module.
- **Module readability:** module caller phải đọc được module chứa API khi compile/gọi theo cách thông thường (`requires` và module graph).
- **Export:** package phải được export tới caller để caller truy cập công khai theo ngữ nghĩa Java giữa các module.
- **Open:** package được mở cho deep reflection vào các thành viên không public bằng các API Reflection/Method Handles tương ứng.
- **Class loader/layer:** class có phải được tìm thấy, module có được resolve và danh tính kiểu có khớp nhau không.
- **Hợp đồng/ủy quyền ứng dụng:** quyền gọi ở mức Java không tự bảo đảm caller được phép thực hiện một nghiệp vụ hoặc thao tác dữ liệu nhạy cảm.

Quyền của **compiler**, **JVM runtime**, **Reflection** và **chính sách nghiệp vụ** liên quan nhưng không phải cùng một thứ.

## 3. `exports`, `opens`, `uses` và `provides` khác nhau thế nào?

| Khai báo trong `module-info.java` | Cho phép gì? | Điều không nên suy diễn |
| --- | --- | --- |
| `requires com.example.spi;` | Module hiện tại đọc phụ thuộc cần thiết | Không tự export API của module bị require |
| `exports com.example.api;` | Cho mọi module đọc được module này truy cập các type/member phù hợp Java visibility trong package | Không mở private fields/methods cho deep reflection từ module ngoài |
| `exports com.example.api to com.example.friend;` | Chỉ xuất package cho module được nêu | Không cấp quyền cho các module khác |
| `opens com.example.model;` | Cho deep reflection ở runtime vào package đó từ các module khác | **Không** cho phép mã ở module khác import package này lúc compile nếu package chưa được export |
| `opens com.example.model to com.example.mapper;` | Mở một package cho **module cụ thể** thực hiện deep reflection | Không làm mọi module được cùng quyền |
| `uses com.example.spi.TextPlugin;` | Tuyên bố module **tiêu thụ service** bằng `ServiceLoader` | Không lựa chọn hoặc tự cung cấp implementation |
| `provides com.example.spi.TextPlugin with com.example.impl.UpperTextPlugin;` | Công bố provider của service trong module hiện tại | **Không cần** export package chứa implementation để `ServiceLoader` sử dụng |

**`exports`** và **`opens`** có mục đích khác nhau:

- `exports` dành cho **API ở mức ngôn ngữ Java**, để caller import kiểu public, compile và gọi trực tiếp.
- `opens` dành cho **khám phá/truy cập phản chiếu sâu ở runtime**. Các API như `Field.trySetAccessible()` hay `MethodHandles.privateLookupIn(...)` cần đáp ứng các điều kiện tương ứng, không tự vượt rào module.
- Package **chỉ `opens`** chưa được export cho việc import/truy cập trực tiếp ở compile time. Một package được `exports` cũng không mặc nhiên cho phép Reflection truy cập mọi private member từ module ngoài.
- `open module ...` mở **mọi package** của module cho deep reflection; thường rộng hơn cần thiết cho một thư viện động.

**Lưu ý về kiểm tra ở runtime:** `Module.isExported(pkg, otherModule)` có xét package được **open** như có quyền export ở runtime trong một số trường hợp. Không dùng kết quả của API kiểm tra runtime này thay cho việc đọc `module-info.java` để quyết định liệu một package có phải **public compile-time API** hay không.

**Qualified directive** (dạng có `to`) dùng **tên module đích**, không phải tên package hoặc tên class. Với thư viện trên classpath (unnamed module), những điều kiện JPMS dành cho **named modules** ở trên không áp dụng theo cùng cách; nếu cần kiểm soát ranh giới chặt, phải thực sự triển khai module named phù hợp, không chỉ thêm tài liệu mô tả ý định.

## 4. Bài thực hành Java 17+: SPI công khai, provider nội bộ

Ta xây ba named modules:

- **`com.example.dynamic.spi`**: chứa hợp đồng `TextPlugin` mà mọi consumer cần biết, export duy nhất package API.
- **`com.example.dynamic.plugin`**: cung cấp một implementation tên `UpperTextPlugin`, **không export và không open** package implementation.
- **`com.example.dynamic.host`**: sử dụng `ServiceLoader`, chỉ `requires` module SPI và khai báo `uses` service; không compile với implementation cụ thể.

### 4.1. Cấu trúc thư mục

Tạo các tệp theo đường dẫn sau, tính từ một thư mục dự án trống:

~~~text
src/
├── com.example.dynamic.spi/
│   ├── module-info.java
│   └── com/example/dynamic/spi/TextPlugin.java
├── com.example.dynamic.plugin/
│   ├── module-info.java
│   └── com/example/dynamic/plugin/internal/UpperTextPlugin.java
└── com.example.dynamic.host/
    ├── module-info.java
    └── com/example/dynamic/host/Main.java
~~~

Tên thư mục đầu tiên sau `src/` là **tên module**, phù hợp với chế độ `--module-source-path src`. Các lớp bên trong tuân theo đường dẫn package Java.

### 4.2. Module SPI: chỉ export hợp đồng

**`src/com.example.dynamic.spi/module-info.java`**

~~~java
module com.example.dynamic.spi {
    exports com.example.dynamic.spi;
}
~~~

**`src/com.example.dynamic.spi/com/example/dynamic/spi/TextPlugin.java`**

~~~java
package com.example.dynamic.spi;

public interface TextPlugin {
    String id();
    String transform(String input);
}
~~~

Caller cần cả `id()` và `transform(String)`. Kiểu input/output ở đây chỉ là `String`, không làm lộ class implementation. Bản API phức tạp hơn nên định nghĩa quy tắc lỗi, null, state/thread-safety và phiên bản ở cùng nơi công bố SPI.

### 4.3. Module provider: công bố **service**, giữ kín package implementation

**`src/com.example.dynamic.plugin/module-info.java`**

~~~java
module com.example.dynamic.plugin {
    requires com.example.dynamic.spi;
    provides com.example.dynamic.spi.TextPlugin
            with com.example.dynamic.plugin.internal.UpperTextPlugin;
}
~~~

**`src/com.example.dynamic.plugin/com/example/dynamic/plugin/internal/UpperTextPlugin.java`**

~~~java
package com.example.dynamic.plugin.internal;

import com.example.dynamic.spi.TextPlugin;
import java.util.Locale;

public final class UpperTextPlugin implements TextPlugin {
    public UpperTextPlugin() { }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

Lớp provider là `public` với public no-arg constructor, đáp ứng dạng provider được `ServiceLoader` hỗ trợ. Nhưng **package `com.example.dynamic.plugin.internal` không được export**. Client không cần import `UpperTextPlugin`; hệ module và `ServiceLoader` dùng khai báo `provides` để lấy provider.

### 4.4. Module host: tiêu thụ service, không phụ thuộc provider

**`src/com.example.dynamic.host/module-info.java`**

~~~java
module com.example.dynamic.host {
    requires com.example.dynamic.spi;
    uses com.example.dynamic.spi.TextPlugin;
}
~~~

**`src/com.example.dynamic.host/com/example/dynamic/host/Main.java`**

~~~java
package com.example.dynamic.host;

import com.example.dynamic.spi.TextPlugin;
import java.lang.reflect.Constructor;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) throws Exception {
        int count = 0;

        // 1. Gọi qua hợp đồng SPI; host không import provider.
        for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
            count++;
            System.out.println(plugin.id() + ":" + plugin.transform("java"));
        }
        System.out.println("providers=" + count);

        // 2. Thử truy cập reflection trực tiếp vào implementation.
        Class<?> impl = Class.forName(
                "com.example.dynamic.plugin.internal.UpperTextPlugin");
        Constructor<?> constructor = impl.getDeclaredConstructor();

        System.out.println("exported=" + impl.getModule().isExported(
                impl.getPackageName(), Main.class.getModule()));
        System.out.println("opened=" + impl.getModule().isOpen(
                impl.getPackageName(), Main.class.getModule()));
        System.out.println("tryAccessible=" + constructor.trySetAccessible());

        try {
            constructor.newInstance();
            System.out.println("directReflection=allowed");
        } catch (IllegalAccessException expected) {
            System.out.println("directReflection=blocked");
        }
    }
}
~~~

Đây là **một chương trình nhiều module độc lập có thể biên dịch/chạy** khi lưu đủ sáu file. Dùng `Class.forName` ở phần sau chỉ để quan sát ranh giới quyền. API này có thể lấy được `Class<?>` cho một class đã có ở runtime, nhưng việc có đối tượng `Class` **không đồng nghĩa** có quyền gọi constructor của class đó.

### 4.5. Biên dịch và chạy

Từ thư mục chứa `src/`, dùng **JDK 17 trở lên**:

**PowerShell (Windows):**

~~~powershell
$files = Get-ChildItem src -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName
javac --release 17 --module-source-path src -d out $files
java --module-path out --module com.example.dynamic.host/com.example.dynamic.host.Main
~~~

**Bash (Linux/macOS):**

~~~bash
javac --release 17 --module-source-path src -d out $(find src -name '*.java')
java --module-path out --module com.example.dynamic.host/com.example.dynamic.host.Main
~~~

Kết quả với đúng ba module trên:

~~~text
upper:JAVA
providers=1
exported=false
opened=false
tryAccessible=false
directReflection=blocked
~~~

**Giải thích từng quan sát:**

1. `ServiceLoader` định vị provider trong môi trường module path được resolve, rồi gọi `transform("java")` qua `TextPlugin`. Kết quả `upper:JAVA` xác nhận hợp đồng SPI đủ để sử dụng triển khai động.
2. `providers=1` trong dự án ví dụ vì chỉ có một provider. Trong ứng dụng thật, tập provider phụ thuộc module graph/layer và các artifact được triển khai; không giả định thứ tự provider chung là ổn định giữa mọi môi trường.
3. `exported=false` và `opened=false` cho module host vì provider không khai báo `exports` hay `opens` package implementation.
4. `tryAccessible=false` cho thấy host không thể tự mở quyền constructor từ module khác khi package không được export/open phù hợp.
5. `directReflection=blocked` là hành vi mong đợi. Hệ thống vẫn chạy thành công qua SPI, nên **không cần mở package implementation chỉ để dùng `ServiceLoader`**.

Kết quả này đã được kiểm chứng bằng `javac --release 17` và `java --module-path` với các nguồn đúng như trình bày.

### 4.6. Thử thay đổi quyền có chủ đích

Giả sử có **yêu cầu tích hợp được phê duyệt**: module host thực sự cần tạo instance qua Reflection để phục vụ một cơ chế ngoài `ServiceLoader`. Khi đó, **chỉ trong phạm vi thí nghiệm**, sửa **`src/com.example.dynamic.plugin/module-info.java`** thành:

~~~java
module com.example.dynamic.plugin {
    requires com.example.dynamic.spi;
    provides com.example.dynamic.spi.TextPlugin
            with com.example.dynamic.plugin.internal.UpperTextPlugin;

    opens com.example.dynamic.plugin.internal to com.example.dynamic.host;
}
~~~

Biên dịch lại tất cả và chạy. `opens ... to com.example.dynamic.host` cho host quyền truy cập phản chiếu sâu vào package đó. `constructor.trySetAccessible()` có thể trả `true` và lời gọi `newInstance()` có thể thành công nếu không vướng điều kiện khác. **Không nên chọn thiết kế này cho ví dụ plugin thông thường**, bởi `ServiceLoader` đã xử lý khởi tạo qua SPI mà không cần cấp thêm quyền.

Lưu ý: `opens` được tính như một dạng quyền truy cập public ở runtime khi kiểm tra `Module.isExported(package, module)`; do đó không diễn giải đơn giản biến `exported` của demo như cấu hình `exports` thuần túy sau khi đã thêm `opens`.

## 5. Mở đúng quyền cho đúng loại tích hợp

### 5.1. Ưu tiên API/SPI và factory khi chỉ cần gọi chức năng

Nếu ứng dụng bên ngoài chỉ cần gọi hành vi, cung cấp public interface, public factory hoặc registry có contract ổn định. Với nhiều provider độc lập, `ServiceLoader` hoặc registry rõ ràng cho phép discovery mà không phải export từng implementation package.

Với dự án modular, cấu hình `uses` ở consumer, `provides` ở provider. Một service provider trong named module có thể nằm trong package không export; đây là khả năng đóng gói quan trọng. Provider cần thỏa quy tắc của `ServiceLoader` về kiểu, constructor hoặc provider method thích hợp.

**Không thiết kế API yêu cầu caller dùng `Class.forName("...internal...")` và ép kiểu ngược đến implementation class.** Điều đó biến tên package và class nội bộ thành một phần hợp đồng không chính thức, khiến refactor và nâng cấp khó dự đoán.

### 5.2. Dùng `exports` khi consumer cần compile với public type

Ví dụ một mô-đun `com.example.library` công khai package `com.example.library.api`:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Đoạn là **module descriptor minh họa**, không phải file bổ sung cần dùng để chạy ví dụ mục 4. Chỉ export package có surface mà consumer được phép phụ thuộc; tránh export `internal`, `impl`, `generated` chỉ để sửa lỗi compile. Muốn giới hạn cho module bạn kiểm soát:

~~~java
module com.example.library {
    exports com.example.library.internalbridge to com.example.friend;
}
~~~

`exports ... to` là **qualified export**. Nó giúp thu hẹp các consumer được phép truy cập công khai, nhưng vẫn có quan hệ coupling với tên module friend; theo dõi khi đổi tên hoặc tách module.

### 5.3. Dùng `opens` khi framework thực sự cần deep reflection

Một serializer, mapper, ORM hoặc công cụ dependency injection có thể cần gọi constructor không public, đọc/ghi fields hoặc inspect các member bằng Reflection. Nếu không thiết kế được đường dùng API công khai phù hợp và yêu cầu này có căn cứ, mở **package dữ liệu/config cụ thể** cho **framework module cụ thể**:

~~~java
module com.example.library {
    requires com.example.mapper;
    opens com.example.library.dto to com.example.mapper;
}
~~~

Đây là ví dụ chính sách module, **không phải chương trình biên dịch độc lập**: nó giả định các module và package được đặt đúng tên trong dự án thực. Không nên mở một package chứa bí mật hay toàn bộ implementation chỉ vì framework báo lỗi truy cập; trước tiên xác minh member, package, module caller và kiểu Reflection thật sự cần.

Nếu framework chạy trong **unnamed module** (classpath), vấn đề qualified `opens ... to` không thể giải quyết bằng cách ghi một package name thay vì module name; cần thiết kế packaging/launch phù hợp. Cờ runtime `--add-opens` đôi khi hữu ích trong **migration/diagnostic** nhưng làm quyền phụ thuộc lệnh khởi chạy:

~~~text
--add-opens com.example.library/com.example.library.dto=ALL-UNNAMED
~~~

Đây là **fragment JVM option** để minh họa, không phải một lệnh shell hoàn chỉnh. Chỉ dùng có kiểm soát; đừng coi việc mở rộng sang mọi unnamed module là mô hình API lâu dài.

### 5.4. `setAccessible(true)` và `MethodHandles` không phải chìa khóa vạn năng

Khi member không thuộc phạm vi được phép, `Field.setAccessible(true)` hoặc `Constructor.setAccessible(true)` có thể ném `InaccessibleObjectException`; `trySetAccessible()` có thể trả `false`. `MethodHandles.privateLookupIn` cũng chịu quy tắc truy cập module và không tự vượt giới hạn của package không open.

**`public` member + `public` class + `exports`** hỗ trợ truy cập public thông thường, nhưng không có nghĩa gọi private field được. **`opens`** cho Reflection trong package được mở quyền sâu hơn ở runtime, nhưng không phải “cấp toàn quyền hành chính” cho plugin và cũng không bảo đảm dependency bên ngoài đủ để chạy.

## 6. Tính tương thích của public API trong thư viện động

Khi một host và plugin được biên dịch ở thời điểm khác nhau, **thay đổi API** có thể chỉ lộ lỗi khi nạp/liên kết/gọi:

| Thay đổi | Rủi ro | Cách thiết kế |
| --- | --- | --- |
| Đổi package, module, tên public type | Consumer không tìm thấy kiểu, lỗi biên dịch hoặc runtime linkage | Duy trì tên contract; thay đổi lớn có kế hoạch migration/version |
| Đổi tên, tham số hoặc return type của method SPI | Provider/host cũ không tương thích; có thể gặp `NoSuchMethodError`/`AbstractMethodError` | Thiết kế evolution strategy, kiểm thử với plugin phiên bản trước |
| Thêm abstract method vào interface mà provider cũ phải triển khai | Consumer mới gọi method trên provider cũ có thể gặp `AbstractMethodError` | Xem xét default method có semantics rõ hoặc SPI phiên bản mới |
| Thêm default method | Thường giảm yêu cầu sửa provider nhưng vẫn có thể gây conflict/hành vi không mong muốn | Kiểm thử đa phiên bản; không coi mọi default method đều an toàn |
| Đưa private implementation type vào chữ ký public API | Consumer bị lệ thuộc vào type không thể truy cập hoặc ABI khó thay đổi | Dùng DTO/interface công khai thuộc package được export |
| Export thêm package hoặc mở thêm deep reflection | Mở rộng bề mặt phụ thuộc và quyền; khó thu hẹp về sau | Chỉ thêm sau khi có use case và chủ thể tiêu thụ rõ ràng |
| Đổi provider implementation mà giữ nguyên SPI | Thông thường consumer qua SPI không phải sửa mã | Giữ semantics, ID/provider selection, lifecycle và lỗi như contract |

Phân biệt **source compatibility**, **binary compatibility** và **behavioral compatibility**. Một thay đổi có thể biên dịch được nhưng làm plugin chạy sai về nghiệp vụ; ngược lại, đổi tên parameter thông thường không đổi method descriptor JVM nhưng có thể làm hỏng binding theo tên mà framework đặt lên trên Reflection.

Nếu public API trả về kiểu từ module khác, xem xét khai báo `requires transitive` **khi consumer cần đọc kiểu đó trong public signature**. Đừng thêm `transitive` cho mọi dependency nội bộ vì vô tình làm rộng đồ thị phụ thuộc công khai.

Thiết lập version hợp đồng, test host với provider cũ/mới, đo lỗi thực thi theo từng module và có fallback khi không tìm thấy provider. Đây là phần của thiết kế thư viện động, không chỉ là lựa chọn keyword `public`.

## 7. Security và độ tin cậy: quyền truy cập không thay thế cô lập

- **Không tin plugin tùy ý:** `ClassLoader` và module `exports`/`opens` là cơ chế nạp kiểu và kiểm soát truy cập Java, **không tạo sandbox bảo mật** hay ngăn plugin dùng mọi khả năng mà tiến trình có quyền. Mã plugin có thể chạy trong constructor, initializer và method.
- **Phân quyền theo chức năng:** thay vì cho plugin toàn bộ context/credential, cấp cho nó interface có quyền rõ ràng, chỉ expose đúng capability cần dùng. Nếu cần thực thi mã không tin cậy, cân nhắc cách ly bằng process và giới hạn quyền hệ điều hành.
- **Giữ dữ liệu nội bộ ở phạm vi hẹp:** đừng export/opens package chứa implementation hoặc dữ liệu nhạy cảm chỉ để khắc phục lỗi Reflection. Với immutable DTO và factory public, nhiều tích hợp không cần deep reflection.
- **Không cấp quyền vì tiện debug:** `--add-opens` hoặc `open module` có thể làm ứng dụng chạy ngay nhưng tăng coupling với internal details; nêu rõ lý do, phạm vi, chủ thể và thời hạn sử dụng khi áp dụng.
- **Tôn trọng loader/layer:** class cùng binary name nhưng do defining class loader khác nhau có thể là các kiểu khác nhau. Không dùng tên class string làm bằng chứng class tương thích với SPI của host.
- **Đóng gói đúng artifact:** trong ví dụ, module provider phải thực sự có mặt trên module path và được resolve bởi module system. Một `provides` viết trong source không tự đưa JAR thiếu vào môi trường runtime.

**Quy tắc quyết định:** cần *gọi chức năng* → contract public/SPI; cần *compile với type* → export package API; cần *đọc private state bằng Reflection* → mở package tối thiểu cho module cụ thể, khi thật sự bắt buộc; cần *chạy code không tin cậy* → xem xét cô lập tiến trình và quyền hệ điều hành.

## 8. Chẩn đoán lỗi truy cập trong ứng dụng thực tế

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Compile báo `package ... is not visible` hoặc `does not export` | `requires`, `exports`, chính xác package/API được public, module path |
| `IllegalAccessError` tại runtime | Version/class file/module graph có khác build-time? Public type có còn export? |
| `IllegalAccessException` khi gọi constructor/method qua Reflection | Modifier Java, package export/open, calling module, constructor/method thực sự |
| `InaccessibleObjectException` khi `setAccessible(true)` | Target package có `opens` tới caller chưa? Có đang lạm dụng deep reflection không? |
| `trySetAccessible() == false` | Quyền open/export không đủ theo loại member; thử đường API/SPI được hỗ trợ |
| `ServiceConfigurationError` / không thấy provider | `uses`/`provides`, provider class/constructor, module resolution, service descriptor classpath, packaging |
| `ClassCastException` dù tên interface giống nhau | Host và plugin có đang nạp hai bản sao SPI từ class loader khác nhau? |
| `NoClassDefFoundError` / `NoSuchMethodError` | Classpath/module path, dependency version, public ABI của host/provider không khớp |
| `IllegalCallerException` khi `ServiceLoader.load` trong named module | Module gọi đã khai báo `uses` phù hợp? |

**Thứ tự debug gợi ý:** xác định tên class/module thực tế (`clazz.getModule()`), package, module caller, module có được resolve/đọc không, package được `exports` hay `opens` cho ai, loại member cần gọi, version artifact đang chạy, rồi mới quyết định sửa `module-info.java`. Dùng `Module.isOpen(pkg, callerModule)` để kiểm tra phạm vi mở Reflection; nhớ rằng `isExported` ở runtime có ngữ nghĩa rộng hơn từ khóa `exports` trong descriptor khi package được open.

## 9. Những hiểu lầm cần tránh

1. **“Có `public class` thì module nào cũng import được.”** Sai trong JPMS: package chứa class còn phải được export thích hợp và module caller cần đọc module cung cấp API.
2. **“Muốn `ServiceLoader` chạy phải export class provider.”** Sai: module provider có thể `provides` một public implementation trong package không export; ví dụ thực hành đã chứng minh điều đó.
3. **“`exports` cho phép đọc private field bằng Reflection.”** Sai: public API access khác deep reflection.
4. **“`opens` cho phép gọi mọi internal class từ source.”** Sai: opens phục vụ runtime reflective access; compile-time import cần exports.
5. **“`setAccessible(true)` luôn vượt qua giới hạn module.”** Sai: từ Java 9+ cơ chế strong encapsulation có quy tắc chặn truy cập nếu package không mở phù hợp.
6. **“Không tìm thấy plugin là do quyền Reflection.”** Có thể sai: hãy xác minh service descriptor, module resolution, loader/layer, provider hợp lệ trước.
7. **“Class loader hoặc module chặn được mã độc khi đã chạy.”** Sai: chúng không phải sandbox OS; cùng tiến trình còn chia sẻ nhiều capability.
8. **“Đã public API thì mọi thay đổi đều tương thích.”** Sai: chữ ký, semantics, visibility, lifecycle và binary compatibility đều phải được kiểm thử.

## 10. Bài tập vận dụng

**Bài 1 — Xác định bề mặt API:** Với thư viện gồm `TextPlugin`, `UpperTextPlugin`, `CacheManager`, `PluginRegistry`, `InternalParser`, hãy đề xuất module descriptor chỉ export những package mà consumer cần compile với. Giải thích vì sao implementation không nên xuất hiện trong public signature.

**Bài 2 — Quyền Reflection:** Giữ nguyên ví dụ mục 4, thay module provider bằng qualified `opens ... to com.example.dynamic.host`. Dự đoán `tryAccessible()` và `newInstance()`, chạy để kiểm chứng. Giải thích vì sao việc đó không làm package tự động thành public compile-time API.

**Bài 3 — Bỏ Reflection không cần thiết:** Xóa toàn bộ phần `Class.forName`/constructor trong `Main`, chỉ giữ `ServiceLoader` và gọi `TextPlugin`. Biên dịch/chạy lại và so sánh. Hãy giải thích vì sao client ít phụ thuộc vào implementation hơn.

**Bài 4 — Thay đổi contract:** Thêm một abstract method mới vào `TextPlugin`, giữ provider nhị phân cũ. Phân tích khả năng lỗi source và runtime. Đề xuất default method có semantics hợp lệ hoặc version SPI mới; không giả định thêm method luôn tương thích.

**Bài 5 — Chọn cơ chế:** Với ba yêu cầu “plugin chỉ được chạy transform”, “mapper cần đọc private field của DTO”, “đối tác bên ngoài cần import type DTO”, hãy chỉ ra khi nào dùng public SPI, qualified `opens`, hoặc `exports`; giải thích giới hạn của từng lựa chọn.

## Tóm lược kiến thức cốt lõi

Thiết kế thư viện động có chất lượng bắt đầu bằng **hợp đồng nhỏ và ổn định**, cho host truy cập qua **API/SPI công khai**, giữ kín implementation và chỉ cho Reflection những quyền tối thiểu thực sự cần. `exports` phục vụ khả năng dùng kiểu public giữa named modules; `opens` mở deep reflection ở runtime; `uses`/`provides` hỗ trợ discovery qua `ServiceLoader` mà không phải export implementation. Những quyền này là ranh giới kỹ thuật có thể kiểm tra và thử nghiệm, nhưng vẫn phải đi kèm quản lý phiên bản, dependency và mô hình tin cậy phù hợp.

## Tài liệu tham khảo

- [Java Language Specification 17 — `7.7` Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Java SE 17 API — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 API — `java.lang.reflect.AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java SE 17 API — `java.lang.invoke.MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [JDK 17 `javac` Documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
