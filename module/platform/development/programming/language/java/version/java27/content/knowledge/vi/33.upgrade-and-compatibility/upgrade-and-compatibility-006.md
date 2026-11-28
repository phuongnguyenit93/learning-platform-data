# Xử lý strong encapsulation và loại bỏ phụ thuộc JDK internal API

## 1. Vấn đề khi chuyển ứng dụng sang Java 27

Một ứng dụng có thể chạy tốt trên JDK cũ nhưng thất bại khi chuyển sang Java 27, dù mã nghiệp vụ không thay đổi. Nguyên nhân thường không nằm ở cú pháp Java mà ở những **giả định về khả năng truy cập vào các thành phần bên trong JDK**: import class không được công bố, dùng reflection đọc trường private của lớp JDK, tạo đối tượng bằng cơ chế không hỗ trợ hoặc dựa vào cấu trúc runtime có thể thay đổi.

Các tình huống điển hình:

- Mã hoặc dependency import **jdk.internal.\*** hoặc những class **sun.\*** không thuộc API được hỗ trợ.
- Framework cũ gọi **setAccessible(true)** để truy cập **java.lang.String.value** hoặc trường private của lớp trong **java.base**.
- Thư viện dùng những phương thức truy cập bộ nhớ của **sun.misc.Unsafe**.
- Mã khởi động mang theo **--illegal-access=permit** từ bản cấu hình cũ.
- Reflection sửa **final** fields và gặp cảnh báo trên JDK 26/27.
- Plugin/agent dùng API không được export hoặc giả định rằng mở package đồng nghĩa có thể sửa mọi dữ liệu.
- Test chỉ chạy trên classpath, nhưng production chạy theo named modules với quyền truy cập khác nhau.

Mục tiêu của bài không phải tìm cách mở mọi package trong JVM. Mục tiêu là **phát hiện phụ thuộc vào API nội bộ, thay thế bằng API được hỗ trợ, giới hạn những ngoại lệ tạm thời và xác nhận tương thích trong môi trường thực tế**.

**Phạm vi:** chương **Nâng cấp và tương thích Java 27**, thuộc module **Java 27 và các kiến thức liên quan**. Theo yêu cầu chỉ dùng kiến thức còn áp dụng, các lựa chọn được khuyến nghị ở đây là API và công cụ hiện hành của Java 27. Những cơ chế cũ chỉ được nhắc đến để nhận diện và loại bỏ.

## 2. Strong encapsulation là gì?

**Strong encapsulation** là quy tắc đóng gói mạnh của hệ thống module Java (JPMS), giới hạn việc mã ở module khác truy cập các package và thành viên không được công khai theo hợp đồng module.

Trước khi modularization, nhiều thư viện đã dựa vào các class không công khai của JDK vì chúng tình cờ nằm trên classpath hoặc reflection từng được runtime nới lỏng. Những phụ thuộc như vậy tạo rủi ro về bảo mật, thay đổi implementation và khó nâng cấp.

Trong Java 27:

- **Public API của package được exports** có thể được dùng thông qua truy cập Java thông thường nếu quan hệ module cho phép.
- **Non-public members** không trở nên có thể truy cập chỉ vì một class là public.
- **Deep reflection** từ module bên ngoài cần package được **opens** tới module gọi, hoặc một quyền tương đương được cấp có chủ đích.
- Nhiều **JDK internal packages** không được export/open mặc định.
- Những API nội bộ đặc biệt trong **jdk.unsupported** có ngoại lệ lịch sử nhưng **không thành API ổn định** vì vẫn có thể bị thay đổi hoặc loại bỏ.

~~~mermaid
flowchart TD
    A["Module A sử dụng class trong Module B"] --> B{"Package B được exports cho A?"}
    B -->|"Có"| C["Truy cập public API theo Java visibility"]
    B -->|"Không"| D["Không thể import/truy cập trực tiếp"]
    C --> E{"Cần deep reflection vào private?"}
    E -->|"Không"| F["Dùng API public bình thường"]
    E -->|"Có"| G{"Package được opens cho A?"}
    G -->|"Có"| H["Reflection có thể được cho phép theo hợp đồng API"]
    G -->|"Không"| I["setAccessible bị từ chối"]
~~~

**Encapsulation khác authentication/authorization.** Việc package được opens không có nghĩa một module được người dùng cấp quyền nghiệp vụ, cũng không biến code bên ngoài thành an toàn. JPMS chủ yếu định nghĩa ranh giới liên kết và truy cập runtime, không phải một sandbox cho mã tùy ý.

## 3. Những mốc cần nhớ khi nâng cấp

| Mốc | Tác động còn quan trọng trong Java 27 |
|---|---|
| **JDK 9 – JEP 261** | JPMS, module descriptors, exports/opens và runtime image dạng module |
| **JDK 16 – JEP 396** | Strong encapsulation trở thành mặc định cho JDK internals, chuẩn bị chuyển đổi |
| **JDK 17 – JEP 403** | Strong encapsulation đối với các JDK internals, ngoại trừ một số API quan trọng được duy trì trong jdk.unsupported |
| **JDK 23 – JEP 471** | Memory-access methods của sun.misc.Unsafe bị deprecated for removal |
| **JDK 24 – JEP 498** | Khi dùng những phương thức đó, runtime bắt đầu cảnh báo theo chính sách |
| **JDK 26 – JEP 500** | Cảnh báo khi deep reflection sửa final fields không được bật quyền |
| **JDK 27** | Tiếp tục thực thi các ranh giới trên; cần chuẩn bị cho việc hạn chế mạnh hơn trong tương lai |

Các mốc này không có nghĩa **tất cả** class thuộc tiền tố **com.sun** hoặc **sun** đều đã bị xóa. Cần kiểm tra từng loại API và module.

**Quan trọng:** Tùy chọn **--illegal-access** từng cho phép nới lỏng truy cập trước đây **không còn hiệu lực** như một giải pháp trên Java 27. Không đưa nó vào hướng dẫn nâng cấp hoặc pipeline production mới.

## 4. Public API, JDK-specific API và internal API

Không nên đánh giá tính hỗ trợ chỉ từ prefix của tên package.

| Loại | Ví dụ | Chiến lược |
|---|---|---|
| Java SE public API | **java.util.Base64**, **java.lang.invoke.VarHandle**, **java.nio.file.Files** | Lựa chọn mặc định |
| Standard FFM API | **java.lang.foreign.MemorySegment**, **Arena** | Dùng cho ngoại bộ nhớ khi phù hợp |
| Documented JDK-specific API | **com.sun.net.httpserver** trong module **jdk.httpserver**, API JFR trong **jdk.jfr** | Có thể dùng theo hợp đồng hỗ trợ và mục tiêu triển khai |
| Internal, non-exported | **jdk.internal.misc**, **jdk.internal.reflect**, một số package **sun.\*** | Tránh phụ thuộc, tìm API thay thế |
| Unsupported legacy compatibility API | **sun.misc.Unsafe** trong **jdk.unsupported** | Lên kế hoạch loại bỏ, không tạo code mới phụ thuộc |

Không phải cứ một class có thể **Class.forName** hoặc tìm được trong **jrt:** là class ấy có hợp đồng public ổn định. **Khả năng tìm thấy class không đồng nghĩa khả năng truy cập hoặc được bảo đảm tương thích.**

Một số API JDK-specific vẫn được tài liệu hóa và export chính thức; không cần ép mọi thứ thành "chỉ java.* mới hợp lệ". Dùng **Javadoc công khai** và **module descriptor** để xác định tính hỗ trợ, thay vì một phép so tiền tố đơn giản.

## 5. Ranh giới JPMS: requires, exports và opens

Giả sử module **com.acme.catalog** chứa model và module **com.acme.inspector** cần đọc model.

~~~java
// src/com.acme.catalog/module-info.java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

~~~java
// src/com.acme.inspector/module-info.java
module com.acme.inspector {
    requires com.acme.catalog;
}
~~~

Ý nghĩa:

- **requires com.acme.catalog** tạo quan hệ đọc module catalog từ inspector.
- **exports com.acme.catalog.api** cho module khác truy cập public types và public members theo quy tắc Java.
- Không có export đối với **com.acme.catalog.internal**, nên module inspector không thể import public class thuộc package internal như API công khai.
- Việc **exports** không cấp quyền truy cập private fields qua deep reflection.

Nếu inspector cần truy cập private members của một **package do ứng dụng thực sự sở hữu**, có thể xem xét mở có chọn lọc:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;

    opens com.acme.catalog.model to com.acme.inspector;
}
~~~

**Qualified opens** chỉ mở package model cho module inspector, không mở cho mọi module. Đây là thiết kế có thể chấp nhận nếu framework cần serialization/binding và module sở hữu data model đã quyết định cho phép.

**Không thêm opens vào toàn bộ các package của ứng dụng chỉ vì framework báo lỗi ở một package.** Chỉ mở đúng phạm vi cần thiết hoặc ưu tiên public accessors/constructors nếu được.

## 6. exports không giống opens

| Nhu cầu | exports | opens |
|---|---|---|
| Module khác import public class | Có, với quan hệ module phù hợp | **Không**, chỉ opens không làm class trở thành compile-time API |
| Gọi public method bình thường | Có | Không tự cấp quyền compile-time access |
| Deep reflection vào private field/method | Không đủ | Có thể cho phép, theo các giới hạn khác |
| Định nghĩa trong module-info.java | **exports p;** hoặc **exports p to m;** | **opens p;** hoặc **opens p to m;** |
| Gán tạm bằng command-line | **--add-exports** | **--add-opens** |
| Mục đích điển hình | Public contract | Framework reflection/serialization có kiểm soát |

**open module** mở tất cả packages cho deep reflection theo hợp đồng JPMS; nó có phạm vi rộng hơn nhiều so với **opens p to m**. Không mặc định chuyển cả module thành **open module** khi chỉ một package cần xử lý.

Lưu ý: một package được opens vẫn có thể cần các điều kiện khác như tính hợp lệ của member, restrictions đối với final fields hoặc chính sách runtime mới. **opens không phải giấy phép bỏ qua mọi kiểm soát của JVM.**

## 7. Nhận diện lỗi do module encapsulation

Các nhóm lỗi thường gặp:

| Triệu chứng | Khả năng chính | Cần xác minh |
|---|---|---|
| **package ... is not visible** | Compile-time không có exports/reads phù hợp | Module descriptor, flags và dependencies |
| **InaccessibleObjectException: module ... does not "opens ..."** | Deep reflection bị chặn | Module nguồn/package/module gọi |
| **IllegalAccessException** khi get/invoke reflection | Quy tắc truy cập chưa thỏa | Member visibility, opens và API |
| **IllegalAccessError** ở runtime | Binary linking/access mismatch | JAR thực sự được nạp, exports và module path |
| **NoClassDefFoundError** | Thiếu dependency hoặc class lỗi initialization | Không đồng nhất với lỗi encapsulation |
| **ClassNotFoundException** | Không tìm được class theo loader/module | Classpath/module path |
| **NoSuchMethodError** | Mã và thư viện không tương thích nhị phân | Dependency graph, runtime artifact |
| Cảnh báo **sun.misc.Unsafe** | Thư viện vẫn dùng phương thức đang được chuẩn bị loại bỏ | Tìm caller, nâng cấp/thay thế |
| Cảnh báo sửa **final** | Reflection đang mutating final fields | Serializer/DI library, API final-field restrictions |

Không áp dụng **--add-opens** cho mọi lỗi nạp class. Nó không tải JAR bị thiếu, không tạo method đã bị xóa và không thay thế **--add-exports** khi mã muốn import một loại public trong package không được export.

## 8. Demo: setAccessible không thể tự bỏ ranh giới JDK

Đoạn mã sau minh họa một thao tác reflection cố gắng vào implementation detail của **java.lang.String**. Trường **value** ở đây là chi tiết triển khai của những JDK hiện hành; **không được sử dụng làm API trong ứng dụng thật**.

**Tệp StrongEncapsulationDemo.java:**

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class StrongEncapsulationDemo {
    public static void main(String[] args) throws Exception {
        Field internalField = String.class.getDeclaredField("value");

        System.out.println("Field: " + internalField.getName());
        System.out.println("Direct access permitted: "
            + internalField.canAccess("example"));

        System.out.println("trySetAccessible: "
            + internalField.trySetAccessible());

        try {
            internalField.setAccessible(true);
            System.out.println("Deep reflection was opened explicitly");
        } catch (InaccessibleObjectException denied) {
            System.out.println("Strong encapsulation blocks access");
        }
    }
}
~~~

Biên dịch/chạy trong JDK 27 theo cấu hình mặc định:

~~~bash
javac StrongEncapsulationDemo.java
java StrongEncapsulationDemo
~~~

Kết quả kỳ vọng trên HotSpot/JDK thông dụng:

~~~text
Field: value
Direct access permitted: false
trySetAccessible: false
Strong encapsulation blocks access
~~~

**Đây là demo phụ thuộc vào tên một private implementation field; không xem nó là một kiểm thử tương thích API lâu dài.** Nếu JDK thay đổi cấu trúc String, **getDeclaredField("value")** có thể ném **NoSuchFieldException**. Bài học chính là **không dựa vào implementation private của JDK**.

**AccessibleObject.trySetAccessible()** là API thân thiện hơn khi cần thử truy cập: nó trả **false** khi không thể bật quyền, trong khi **setAccessible(true)** có thể ném **InaccessibleObjectException**. Cả hai đều bị giới hạn bởi JPMS.

## 9. Phân biệt dùng reflection hợp lệ và lạm dụng reflection

Reflection **không bị cấm**. Reflection lên public API, hoặc truy cập có kiểm soát vào package do ứng dụng chủ động mở, vẫn là mô hình hợp lệ.

Những thực hành được ưu tiên:

- Dùng **public constructor, method và record accessors** thay vì đọc private fields trực tiếp.
- Nếu viết framework, công bố rõ package nào cần **opens**.
- Dùng annotation và metadata thuộc hợp đồng public thay vì dựa vào tên/sắp xếp fields nội bộ.
- Khi truy cập dữ liệu immutable, ưu tiên truyền qua constructor hoặc factory.
- Với plugin, dùng **ServiceLoader** hoặc SPI public thay vì quét private implementation classes tùy ý.
- Không xem **setAccessible(true)** thành bước bắt buộc cho mọi data binding.

Ví dụ public record không cần deep reflection để lấy giá trị:

~~~java
record Product(String sku, int stock) {}

Product item = new Product("PEN-01", 20);

System.out.println(item.sku());
System.out.println(item.stock());
~~~

Nếu thư viện ORM/serialization thật sự cần deep reflection, hãy đọc hướng dẫn phiên bản **đang bảo trì** và mở **package của ứng dụng** chính xác thay vì mở hàng loạt packages của **java.base**.

## 10. jdeps: bước kiểm tra tĩnh đầu tiên

**jdeps** là công cụ phân tích dependency do JDK cung cấp. Tùy chọn **--jdk-internals** (alias **-jdkinternals**) tìm các phụ thuộc class-level vào JDK internal APIs ở bytecode.

~~~bash
# Phân tích một JAR:
jdeps --jdk-internals app.jar

# Có thêm dependencies trên classpath:
jdeps --jdk-internals --class-path "libs/*" app.jar

# Theo cả dependency graph và multi-release JAR:
jdeps --jdk-internals --recursive --multi-release 27 --class-path "libs/*" app.jar
~~~

**Thay app.jar và libs bằng artifact thật của dự án khi thực thi**. Dấu **"libs/*"** giúp chuyển wildcard thành classpath entry phù hợp; cách xử lý trích dẫn còn phụ thuộc shell.

Kết quả có thể chỉ rõ class nào tham chiếu class/package nội bộ, JDK module liên quan và gợi ý API thay thế nếu công cụ có thông tin đó.

**Không hiểu --jdk-internals là chương trình sửa code tự động.** Nó cung cấp bằng chứng, cần developer hoặc chủ sở hữu thư viện quyết định cách loại bỏ phụ thuộc.

## 11. Giới hạn của phân tích tĩnh

**jdeps** chủ yếu phân tích những liên kết được thể hiện trong class files. Nó có thể **bỏ sót**:

- String ghép động đưa vào **Class.forName**.
- Reflection truy cập fields/methods bằng tên chuỗi.
- Class được tạo bằng bytecode generation trong runtime.
- Logic được tải bằng ServiceLoader, plugin loader hoặc một agent ở thời điểm chạy.
- Các nhánh chỉ chạy khi bật tính năng/OS/JVM option nhất định.
- JNI/native code gọi APIs ngoài bề mặt Java bytecode.
- Truy cập final fields có được qua reflection mà không có tham chiếu tĩnh đến API nội bộ cụ thể.

Vì vậy, cần phối hợp:

~~~mermaid
flowchart LR
    A["Inventory artifact + Java version"] --> B["jdeps --jdk-internals"]
    A --> C["Compile warnings / code review"]
    A --> D["Runtime tests với Java 27"]
    D --> E["Reflection errors + JDK warnings"]
    B --> F["Backlog thay thế"]
    C --> F
    E --> F
    F --> G["Remove workaround + regression tests"]
~~~

Để tìm reflection động, chạy **integration tests trên Java 27** và các luồng nghiệp vụ thật; đừng chỉ tin rằng jdeps không in kết quả là đã sạch hoàn toàn.

## 12. Kiểm tra artifact multi-release và transitive dependencies

Một JAR dạng **multi-release** có thể chứa code riêng theo phiên bản JDK dưới **META-INF/versions/**. Chỉ quét base classes có thể bỏ sót đường mã JDK 27 sử dụng.

~~~bash
jdeps --multi-release 27 --jdk-internals application.jar
~~~

**--multi-release 27** yêu cầu công cụ chọn bề mặt bytecode tương ứng khi xử lý multi-release JAR, thay vì giả định một bản bytecode duy nhất.

Ngoài artifact chính, hãy xem:

1. Dependencies trực tiếp.
2. Dependencies gián tiếp/transitive.
3. Test/runtime-only dependencies.
4. Plugin, build tool, annotation processors và Java agents.
5. JAR do nền tảng đóng gói thêm trong container.
6. Những bản thư viện khác nhau giữa dev, staging và production.

Nếu lỗi nằm trong dependency và project không kiểm soát source code, **ưu tiên nâng cấp hoặc thay thế thư viện** trước khi tạo một bản fork. Gắn vấn đề với **artifact coordinate, version, caller và API nội bộ** để theo dõi có trách nhiệm.

## 13. --add-exports: mở public types của package không export

Tùy chọn tạm **--add-exports** có cú pháp:

~~~text
--add-exports=<source-module>/<package>=<target-module>[,<target-module>...]
~~~

Ví dụ một thư viện cũ trên classpath truy cập public class trong JDK internal package:

~~~bash
java --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED -cp "app.jar" com.acme.Main
~~~

Ở đây **ALL-UNNAMED** có nghĩa tất cả unnamed modules, thường tương ứng code chạy trên classpath. Nếu caller là named module, có thể chỉ định tên module cụ thể thay cho ALL-UNNAMED.

**--add-exports**:

- Cho phép truy cập bình thường tới **public types/public members** trong package được chỉ định, khi các điều kiện module khác được đáp ứng.
- Không biến private fields thành public.
- Không bảo đảm internal API giữ nguyên giữa các bản JDK.
- Không phải hướng nâng cấp lâu dài.

Có thể cần cấu hình cả **javac và java** nếu source trực tiếp import API nội bộ. **--release** và việc export internal system packages có những ràng buộc riêng; không giả định có thể kết hợp mọi tùy chọn mà không gặp lỗi. Nếu code mới cần add-exports để biên dịch, nên xem lại thiết kế.

## 14. --add-opens: cho phép deep reflection theo package

Tùy chọn **--add-opens** có cú pháp:

~~~text
--add-opens=<source-module>/<package>=<target-module>[,<target-module>...]
~~~

Một cách mở tạm cụ thể vào package **java.lang** cho code chạy trên classpath:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -cp app.jar com.acme.Main
~~~

Trong demo mục 8, chạy với:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED StrongEncapsulationDemo
~~~

Có thể khiến **trySetAccessible()** thành công với trường private đang được demo trên implementation hiện tại.

Tuy nhiên, **đây là minh họa rủi ro**, không phải cấu hình được khuyến nghị. Nó mở rộng quyền deep reflection đối với package lõi cho **mọi** unnamed module, có thể bao gồm nhiều thư viện không liên quan.

Nếu caller thuộc named module, ưu tiên chỉ định module đích:

~~~bash
java --add-opens=java.base/java.lang=com.acme.legacy.adapter --module-path mods --module com.acme.app/com.acme.Main
~~~

Tên module ở trên chỉ là ví dụ; cần xác minh đúng module gọi reflection và module đó có thực sự được resolve.

**Không dùng --add-opens để sửa lỗi compile-time import package internal.** Nó chủ yếu tác động đến runtime reflective access; **--add-exports** và thiết kế public API là chủ đề khác.

## 15. Workaround phải có giới hạn và ngày loại bỏ

Khi bị chặn bởi dependency chưa có bản tương thích, một workaround có thể được chấp nhận tạm thời nếu có hồ sơ:

| Trường theo dõi | Giá trị cần ghi |
|---|---|
| Lỗi thực tế | Exception/warning và stack trace gốc |
| Source package | Ví dụ **java.base/java.lang** |
| Module/caller cần quyền | Tên named module hoặc ALL-UNNAMED |
| Dependency phát sinh | Library/agent và phiên bản chính xác |
| Cờ tạm | **--add-opens** hoặc **--add-exports** đúng phạm vi |
| Rủi ro | Mở reflection hoặc dùng API không được hỗ trợ |
| Chủ sở hữu | Team/vendor chịu trách nhiệm thay thế |
| Điều kiện xóa | Bản dependency tương thích + test qua |
| Hạn xử lý | Mốc phát hành/sprint do team định nghĩa |

**Tránh** các bộ JVM options sao chép trên Internet mở hàng chục JDK packages mà không ai biết cái nào còn cần. Điều đó che lỗi nâng cấp, làm tăng bề mặt truy cập và khiến phiên bản Java sau khó bảo trì hơn.

Một cách kiểm tra cần thiết: **thử xóa từng workaround trong staging** sau khi nâng cấp dependency, chạy integration tests và ghi nhận các cờ không còn tác dụng để loại khỏi cấu hình.

## 16. Sửa lỗi theo caller, không theo package một cách mù quáng

Ví dụ thông điệp:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module java.base does not "opens java.lang" to unnamed module @...
~~~

Cách đọc:

1. **module java.base** là module sở hữu member.
2. **java.lang** là package chưa mở cho caller.
3. **unnamed module** cho biết caller đang nằm trong một unnamed module.
4. Phần stack trace cho biết **class/thư viện nào thực sự gọi setAccessible**.
5. Không mặc định class đó là code của ứng dụng; có thể là framework/serializer/agent.

Đường xử lý ưu tiên:

1. Tìm chính xác JAR/phiên bản caller.
2. Tra bản tương thích mới của dependency.
3. Loại bỏ logic phản chiếu private JDK nếu do ứng dụng sở hữu.
4. Nếu chưa nâng cấp được, cân nhắc **--add-opens** có phạm vi hẹp để duy trì dịch vụ.
5. Đưa việc loại bỏ flag vào backlog và chạy lại CI sau nâng cấp.

**Thêm --add-opens cho một package không bảo đảm mọi reflection khác hoạt động.** Framework có thể còn cố mở nhiều packages khác hoặc dùng một kỹ thuật đã bị hạn chế bởi quy tắc riêng.

## 17. Mapping API nội bộ sang API được hỗ trợ

| Phụ thuộc/cách làm cũ | Phương án hiện hành | Điều kiện cần chú ý |
|---|---|---|
| **sun.misc.BASE64Encoder/Decoder** | **java.util.Base64** | Chọn basic, URL-safe hoặc MIME theo giao thức |
| **sun.misc.Unsafe** cho atomic field operations | **VarHandle**, **AtomicInteger/Long/Reference**, concurrent collections | Kiểm tra memory ordering và tính nguyên tử |
| **Unsafe** cho off-heap memory | **java.lang.foreign.MemorySegment, Arena** | Lifetime, bounds, confinement, native restrictions |
| **Unsafe** cho byte buffers | **ByteBuffer** / **MemorySegment** | Dung lượng, byte order, lifecycle |
| **sun.misc.Cleaner** | **java.lang.ref.Cleaner** hoặc AutoCloseable | Cleaner không thay thế close tường minh |
| **sun.misc.Signal** / OS-specific hooks | **Runtime.addShutdownHook** nếu phù hợp; OS/service manager | Không có bản thay thế portable 1:1 cho mọi tín hiệu |
| Private String/ArrayList implementation fields | Public methods, collections, arrays, streams | Không giả định cấu trúc nội bộ |
| **jdk.internal.reflect** để gọi method/constructor | **Reflection public API**, **MethodHandles** và public constructors | Không bypass private members trái phép |
| Internal crypto/security implementation | **java.security**, **javax.crypto**, chuẩn X.509 APIs; thư viện được bảo trì | Phân biệt chức năng xử lý chứng chỉ/cấp chứng chỉ |
| Internal network/file implementation | **java.net.http.HttpClient**, **java.net**, **java.nio.file** | Xác định đúng giao thức và quyền |
| Internal Unicode/charset helper | **java.nio.charset**, **java.text.Normalizer** | Ngữ nghĩa khác nhau, cần test Unicode |
| Internal serialization shortcuts | Public constructors/factories, serialization framework hiện hành | Không tự bypass bất biến của object |

**Không có phép thay thế một-một cho mọi API nội bộ**. Một số kỹ thuật như cấp phát instance không qua constructor từng phá các bất biến của chương trình; việc không có public replacement là một tín hiệu cần sửa mô hình tạo object, không phải buộc JDK cung cấp cách lách tương đương.

## 18. Ví dụ thay sun.misc.BASE64Encoder bằng Base64

API hỗ trợ từ Java 8 và vẫn phù hợp Java 27:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64MigrationDemo {
    public static void main(String[] args) {
        byte[] original = "Xin chào".getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder()
            .encodeToString(original);

        byte[] decoded = Base64.getDecoder()
            .decode(encoded);

        System.out.println(encoded);
        System.out.println(
            new String(decoded, StandardCharsets.UTF_8)
        );
    }
}
~~~

**Phân biệt các biến thể:**

- **Base64.getEncoder/getDecoder** cho basic alphabet.
- **getUrlEncoder/getUrlDecoder** cho URL/file-safe alphabet.
- **getMimeEncoder/getMimeDecoder** cho MIME formatting.

Không giả định mọi chuỗi Base64 từ hệ thống cũ dùng cùng alphabet, cách xuống dòng hoặc padding. Khi thay mã hóa, cần có **test vectors** và thử tương thích hai chiều với dữ liệu/đối tác hiện hữu.

## 19. VarHandle thay thế thao tác trên trường có tính nguyên tử

Nhiều thư viện cũ dùng Unsafe để đọc/ghi volatile hoặc thực hiện compare-and-set. Java cung cấp API chính thức **VarHandle** trong **java.lang.invoke**; khi chỉ cần counter, **AtomicInteger** còn đơn giản hơn.

**Tệp VarHandleMigrationDemo.java:**

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleMigrationDemo {
    static final class Counter {
        volatile int value;
    }

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class
            );
        } catch (ReflectiveOperationException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        VALUE.setVolatile(counter, 10);

        int previous = (int) VALUE.getAndAdd(counter, 5);

        System.out.println(previous);                    // 10
        System.out.println((int) VALUE.getVolatile(counter)); // 15

        boolean changed = VALUE.compareAndSet(counter, 15, 20);

        System.out.println(changed); // true
        System.out.println((int) VALUE.getVolatile(counter)); // 20
    }
}
~~~

Ví dụ tìm VarHandle của **chính lớp do ứng dụng sở hữu** và thao tác hợp lệ với lookup có quyền truy cập tương ứng. Đây là cách sử dụng được hỗ trợ, **không** phải một đường vòng để đọc private field của String trong java.base.

**VarHandle hỗ trợ nhiều memory access modes** như plain/opaque/acquire/release/volatile/atomic, nhưng không nên đổi cơ học một lệnh Unsafe thành một lệnh VarHandle bất kỳ. Cần đối chiếu **memory ordering, CAS semantics, field type và các điều kiện thread safety**.

Nếu chỉ muốn bộ đếm đồng thời:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
System.out.println(counter.get()); // 1
~~~

## 20. FFM API thay thế phần truy cập bộ nhớ native phù hợp

**Foreign Function and Memory API** là API chính thức từ **JDK 22** (JEP 454), nằm trong **java.lang.foreign**. Nó cung cấp mô hình quản lý vòng đời vùng nhớ ngoài heap, memory layouts, bounds và thao tác dữ liệu có kiểu.

**Tệp MemorySegmentMigrationDemo.java:**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class MemorySegmentMigrationDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(
                ValueLayout.JAVA_INT
            );

            segment.set(ValueLayout.JAVA_INT, 0, 42);

            int value = segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println(value); // 42
        }
    }
}
~~~

**Ưu điểm so với tự thao tác địa chỉ Unsafe:**

- Có phạm vi sống rõ ràng do **Arena** quản lý.
- Có kiểm tra bounds/lifetime và điều kiện truy cập.
- Biểu diễn cách đọc/ghi theo **ValueLayout**.
- Có thể dùng các API hỗ trợ cho native interop khi cần.

**Không suy ra mọi lời gọi FFM đều yêu cầu bật native access.** Những **restricted methods** có yêu cầu riêng, đặc biệt các thao tác liên quan liên kết tới native code hoặc địa chỉ nguy hiểm. Nếu ứng dụng sử dụng restricted APIs, cần thiết kế quyền **--enable-native-access** riêng, theo module cụ thể và hướng dẫn Java 27.

FFM không tự làm cho native code an toàn tuyệt đối. Khi gọi thư viện native, vẫn cần xét ABI, memory lifecycle, threading, OS permissions và kiểm thử trên platform đích.

## 21. Không dùng Cleaner thay cho đóng tài nguyên đúng lúc

Một số code cũ dùng **sun.misc.Cleaner** hoặc phụ thuộc vào cơ chế cleanup không rõ vòng đời. Java cung cấp **java.lang.ref.Cleaner**, nhưng các tác vụ dọn dẹp dựa trên reachability **không bảo đảm được thực hiện ngay hoặc luôn thực hiện trước khi tiến trình kết thúc**.

Với tài nguyên do ứng dụng sở hữu, ưu tiên **AutoCloseable và try-with-resources**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class ResourceLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("config.txt");

        try (InputStream input = Files.newInputStream(file)) {
            byte[] firstBytes = input.readNBytes(64);
            System.out.println("Read bytes: " + firstBytes.length);
        }
    }
}
~~~

Ví dụ chỉ chạy khi **config.txt** tồn tại; nó minh họa vòng đời resource, không phải phương án thực hiện file cleanup qua GC.

Nếu thư viện thực sự cần dọn dẹp dự phòng, **Cleaner** có thể là lớp bổ sung. **Không dùng Cleaner thay thế việc đóng native memory, socket, file hoặc database connection** khi chương trình biết thời điểm không còn cần chúng.

## 22. Không dùng JDK internal certificate implementation

Các thư viện cũ đôi khi truy cập package như **sun.security.x509** để đọc hoặc tạo cấu trúc chứng chỉ. Cần tách hai bài toán:

**Đọc/kiểm tra chứng chỉ X.509** có API công khai:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public class CertificateReadDemo {
    public static void main(String[] args) throws Exception {
        Path certificatePath = Path.of("server-cert.pem");

        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(certificatePath)) {
            X509Certificate certificate =
                (X509Certificate) factory.generateCertificate(input);

            certificate.checkValidity();
            System.out.println(certificate.getSubjectX500Principal());
        }
    }
}
~~~

Đây là ví dụ chỉ minh họa **đọc và kiểm tra thời hạn**. **checkValidity() không tự kiểm tra chuỗi tin cậy, chữ ký đến trust anchor, hostname, revocation hoặc chính sách PKI**; những vấn đề đó đòi hỏi logic xác thực chứng chỉ phù hợp như PKIX, TLS implementation hoặc thư viện có hợp đồng rõ.

**Tạo và ký chứng chỉ** là bài toán khác. Không giả định Java SE có một API public tương đương trực tiếp mọi constructor nội bộ trong **sun.security.x509**. Sử dụng công cụ PKI có hỗ trợ hoặc thư viện được bảo trì và đánh giá an toàn theo nhu cầu.

Không thêm **--add-exports java.base/sun.security.x509=...** làm chiến lược lâu dài để giữ logic phát hành chứng chỉ tùy biến.

## 23. MethodHandles giúp thay reflection nào?

**MethodHandles** và **MethodHandles.Lookup** là API Java chính thức phục vụ những thao tác gọi method/truy cập variable có kiểu và hợp đồng liên kết rõ ràng. Nó thường phù hợp cho framework, adapter hoặc công cụ dynamic invocation.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class MethodHandleDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle upper = MethodHandles.publicLookup()
            .findVirtual(
                String.class,
                "toUpperCase",
                MethodType.methodType(String.class)
            );

        String result = (String) upper.invokeExact("java");
        System.out.println(result);
    }
}
~~~

Ví dụ chỉ tìm **public method**. Phương thức **privateLookupIn** có thể tạo lookup với quyền thích hợp vào một lớp thuộc package đã được mở, nhưng **nó vẫn phải tuân theo các quy tắc JPMS**. Không coi MethodHandles là cách tự động bypass strong encapsulation.

**Nên dùng MethodHandles khi có nhu cầu dynamic invocation thực sự** và đã đánh giá độ phức tạp. Nếu chỉ cần gọi một public API tại compile time, Java method call thông thường thường dễ đọc và bảo trì hơn.

## 24. Ví dụ named modules và qualified opens hoàn chỉnh

Tạo hai named modules thuộc quyền sở hữu ứng dụng. Module domain exports public API; chỉ cho module reader đọc sâu package model khi cần.

~~~text
src/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/model/Customer.java
└── com.acme.reader/
    ├── module-info.java
    └── com/acme/reader/Main.java
~~~

**src/com.acme.domain/module-info.java:**

~~~java
module com.acme.domain {
    exports com.acme.domain.model;

    // Chỉ mở model cho module có tên này.
    opens com.acme.domain.model to com.acme.reader;
}
~~~

**src/com.acme.domain/com/acme/domain/model/Customer.java:**

~~~java
package com.acme.domain.model;

public final class Customer {
    private final String demoMemo;

    public Customer(String demoMemo) {
        this.demoMemo = demoMemo;
    }

    public String publicView() {
        return "customer";
    }
}
~~~

**src/com.acme.reader/module-info.java:**

~~~java
module com.acme.reader {
    requires com.acme.domain;
}
~~~

**src/com.acme.reader/com/acme/reader/Main.java:**

~~~java
package com.acme.reader;

import java.lang.reflect.Field;
import com.acme.domain.model.Customer;

public final class Main {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("demo-only");

        // Dùng public API: không cần deep reflection.
        System.out.println(customer.publicView());

        // Chỉ minh họa một access do module domain CHỦ ĐỘNG cho phép.
        Field field = Customer.class.getDeclaredField("demoMemo");
        field.setAccessible(true);
        System.out.println(field.get(customer));
    }
}
~~~

Biên dịch/chạy trên terminal có JDK 27:

~~~bash
javac --module-source-path src -d mods src/com.acme.domain/module-info.java src/com.acme.domain/com/acme/domain/model/Customer.java src/com.acme.reader/module-info.java src/com.acme.reader/com/acme/reader/Main.java

java --module-path mods --module com.acme.reader/com.acme.reader.Main
~~~

Đầu ra:

~~~text
customer
demo-only
~~~

**Bỏ dòng opens** trong module domain, biên dịch/chạy lại và thao tác **setAccessible(true)** sẽ bị chặn, trong khi **publicView()** vẫn truy cập được do exports.

Đây là bài tập để thấy tác dụng của **qualified opens** trong code do chính ứng dụng kiểm soát; **không khuyến nghị truy cập dữ liệu nhạy cảm bằng reflection nếu đã có public contract**.

Nếu không muốn mở package, phương án sạch hơn là tạo **public accessor** hoặc dữ liệu DTO dành riêng cho module reader, rồi xóa phần reflection.

## 25. Sửa final fields qua deep reflection là vấn đề riêng

Từ **JDK 26**, JDK bắt đầu cảnh báo khi code dùng deep reflection để **mutate final instance fields** mà module gọi không được bật quyền phù hợp. Quy tắc này tiếp tục quan trọng trong **Java 27**.

**Một package đã opens không tự bảo đảm sửa final field không có cảnh báo.**

Để điều tra thư viện hoặc serializer còn sửa final fields, Java cung cấp tùy chọn:

~~~bash
# Khuyến nghị cho môi trường thử nghiệm tương thích tương lai.
java --illegal-final-field-mutation=deny -jar application.jar
~~~

Khi không được cấp quyền, việc thử sửa final field qua reflective mutation sẽ bị từ chối theo chính sách và API tương ứng, ví dụ một lời gọi **Field.set** có thể ném **IllegalAccessException**.

Đối với trường hợp chưa thể thay thế ngay, launcher có tùy chọn có kiểm soát:

~~~bash
# Chỉ bật cho một module thực sự cần khả năng này.
java --enable-final-field-mutation=com.acme.serialization --module-path mods --module com.acme.app/com.acme.Main
~~~

Với code trên classpath:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED -jar application.jar
~~~

**Đây là quyền tạm, không phải hướng thiết kế khuyến nghị.** Package có final field vẫn cần thỏa các điều kiện mở/truy cập tương ứng. Không cấp quyền cho mọi unnamed module chỉ vì một thư viện cũ cần sửa một field.

Tùy chọn **--illegal-final-field-mutation** có các chế độ như **allow, warn, debug, deny**; trong Java 27 **warn** là mặc định và khả năng **deny** mặc định được dự kiến trong một bản JDK tương lai. Mục tiêu nâng cấp là thay serializer/DI mapper hoặc contract object để không phụ thuộc việc sửa final field trái với bất biến của ngôn ngữ.

## 26. JDK 27 và lộ trình loại bỏ sun.misc.Unsafe

Không nên nói rằng **sun.misc.Unsafe đã hoàn toàn biến mất trong Java 27**. Một phần API lịch sử vẫn được cung cấp qua **jdk.unsupported**, nhưng nhiều phương thức truy cập bộ nhớ đã **deprecated for removal** và có cảnh báo runtime từ JDK 24.

Để phát hiện code còn gọi các phương thức bị cảnh báo, có thể chạy trên môi trường thử nghiệm:

~~~bash
java --sun-misc-unsafe-memory-access=debug -jar application.jar
~~~

Chế độ **debug** có thể in warning kèm stack trace để xác định caller. Với phép thử readiness khắt khe hơn:

~~~bash
java --sun-misc-unsafe-memory-access=deny -jar application.jar
~~~

Trong chế độ **deny**, các lời gọi memory-access thuộc nhóm bị hạn chế sẽ ném **UnsupportedOperationException** theo hợp đồng launcher.

| Chế độ | Ý nghĩa |
|---|---|
| **allow** | Cho phép những thao tác liên quan mà không phát cảnh báo |
| **warn** | Cho phép và cảnh báo giới hạn theo chính sách |
| **debug** | Cho phép, phát cảnh báo và stack trace để chẩn đoán |
| **deny** | Từ chối các phương thức memory-access bị áp dụng hạn chế |

**Không bật allow để kết luận thư viện tương thích.** Nó chỉ che triệu chứng của một API đang hướng tới loại bỏ, không chứng minh mã sẽ hoạt động trên JDK sau.

Kế hoạch tốt hơn: tìm bản framework/agent mới, chuyển sang VarHandle/Atomic classes hoặc FFM, kiểm thử memory ordering và thêm regression tests.

## 27. Native access là một ranh giới độc lập

Ngoài strong encapsulation, các API liên quan tới **JNI** và những **restricted FFM methods** có **native access restrictions** trong Java hiện đại.

Một số đường code có thể yêu cầu chỉ định:

~~~bash
java --enable-native-access=com.acme.nativebridge --module-path mods --module com.acme.app/com.acme.Main
~~~

Để phát hiện code chưa công bố quyền native access trong thử nghiệm:

~~~bash
java --illegal-native-access=deny -jar application.jar
~~~

Với code chạy trên classpath, có thể bật quyền bằng **--enable-native-access=ALL-UNNAMED**, nhưng phạm vi rộng hơn. Nên tách module có yêu cầu native riêng khi có thể.

**Phân biệt rõ ba quyền:**

| Cơ chế | Điều nó điều chỉnh |
|---|---|
| **--add-opens** | Deep reflection qua ranh giới package/module |
| **--enable-final-field-mutation** | Cho phép module nhất định mutate final fields theo quy tắc riêng |
| **--enable-native-access** | Cho phép restricted native access của module |

Không dùng một flag để kỳ vọng sửa được hai loại hạn chế còn lại. Khi một thư viện vừa reflection vừa gọi JNI, có thể phải giải quyết hai vấn đề độc lập, và ưu tiên **nâng cấp thư viện** hơn việc mở toàn hệ thống.

## 28. Một số giả định JDK cũ không nên giữ lại

Khi gỡ phụ thuộc internal APIs, hãy rà những giả định từng gắn với JDK cũ:

- **Class loader hệ thống là URLClassLoader**: không còn là giả định hợp lệ ở JDK hiện đại.
- **JDK có rt.jar** chứa tất cả core classes: runtime image dùng modular image và **jrt:**.
- Có thể tìm class bằng cách duyệt **lib/ext** hay **java.ext.dirs**: extension mechanism đã bị loại bỏ.
- Mọi package trong **java.base** đều có thể reflection tới private members.
- Có thể cast mọi class loader sang một loại implementation nội bộ.
- File class tồn tại thì module sẽ tự động resolved và export package đó.
- **--illegal-access=permit** tự khôi phục quyền truy cập như trước JDK 17.
- Có thể dùng Security Manager như sandbox cho plugin: trong **JDK 24+ Security Manager đã bị vô hiệu hóa vĩnh viễn**.
- Dữ liệu **final** có thể được sửa qua reflection mà không có ràng buộc hoặc cảnh báo.

Thay vì tái tạo những cơ chế cũ, dùng **ClassLoader public API**, JPMS, module resolution, **ServiceLoader**, public SPI và security boundaries ở hệ điều hành/process.

## 29. Đọc module descriptor và cấu hình hiện tại

Trước khi thêm flags, cần xác định **module nguồn, package và module caller**. Một số công cụ hỗ trợ:

~~~bash
# Thông tin module JDK:
java --describe-module java.base

# Thông tin một module cụ thể:
java --describe-module java.sql

# Liệt kê module có trong JDK:
java --list-modules

# Phân tích module requirements và references:
jdeps --list-deps application.jar

# Kiểm tra công cụ jdeps theo phiên bản cài đặt:
jdeps --help
~~~

Các lệnh dùng artifact placeholder và có thể cần **--module-path** hoặc classpath phù hợp với ứng dụng.

**Đừng mặc định quan hệ module reads/exports là nguyên nhân duy nhất.** Một class có thể không được tìm do JAR thiếu, package có thể bị split giữa modules hoặc provider chưa được đăng ký. Cần phân biệt lỗi configuration với lỗi encapsulation thực sự.

**module-info.class** và manifest của JAR có thể chứa dữ liệu hỗ trợ để hiểu module; tuy nhiên file instruction của assignment này chỉ cho phép đọc các file bài được giao, nên bài hướng dẫn công cụ ở mức giáo dục, không chạy chúng trên repository hiện tại.

## 30. Nâng cấp thư viện: xác định dependency thực sự được nạp

Một thông báo lỗi có thể chỉ ra class của dependency, nhưng việc sửa version trong build file chưa chắc đã đổi runtime artifact.

Các câu hỏi cần trả lời:

1. JAR thực sự được chọn ở runtime là bản nào?
2. Có dependency transitively kéo bản cũ không?
3. Có version conflict giữa build/test/runtime configurations không?
4. Ứng dụng có Java agent, plugin hoặc driver đóng gói riêng không?
5. Docker image và môi trường triển khai có giữ một JAR cũ không?
6. Một library mới có yêu cầu nâng các library liên quan hoặc cả framework không?

Ví dụ các lệnh cần chạy **trong dự án do team sở hữu, không phải trong assignment worker**:

~~~bash
# Ví dụ dự án Gradle đã có wrapper.
./gradlew dependencies --configuration runtimeClasspath

# Nếu nghi một module cụ thể:
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

Các tên configuration có thể khác giữa project và build tool. Với Maven, dùng cơ chế dependency tree/effective dependency management tương ứng.

**Không giả định một bản framework mới nhất luôn là câu trả lời đúng**: cần chọn bản tương thích với JDK 27, platform hiện hành, plugin, test engines và build tool của dự án, sau đó kiểm tra release notes.

## 31. Chuẩn bị test matrix cho Java 27

Nâng cấp JDK là một thay đổi nền tảng. Bộ kiểm thử tối thiểu nên bao phủ:

| Kiểm thử | Mục tiêu |
|---|---|
| **Compile tests** | Không import internal API, code phù hợp source/target |
| **Unit tests** | Hành vi nghiệp vụ, boundary values |
| **Integration tests** | Serialization, ORM, DI, reflection, proxies, database driver |
| **Module-path tests** | Named-module reads/exports/opens và ServiceLoader |
| **Classpath tests** | Legacy unnamed-module behavior nếu vẫn sử dụng |
| **Startup tests** | Spring/app server/agent startup và static initialization |
| **Runtime smoke tests** | Các API/JAR thật được nạp |
| **JDK diagnostics** | jdeps results, runtime warning, exception traces |
| **Native access tests** | JNI/FFM restricted calls và quyền module |
| **Performance tests** | Startup, throughput, p95/p99, GC, memory |
| **Security tests** | Không mở những package/module không cần thiết |

Đặc biệt với lỗi reflection, unit test thuần túy có thể không tạo object mapping đúng schema thật hoặc không kích hoạt proxy code path. Cần integration test có **workflow thực sự dùng reflection**.

Nếu ứng dụng chạy với **custom runtime image jlink**, còn phải kiểm tra những modules được include, services/provides và cấu hình runtime; một lỗi thiếu module khác với lỗi deep reflection.

## 32. Compile với public API surface được lựa chọn

**javac --release** giúp kiểm tra source language level, classfile target và bề mặt API được hỗ trợ theo release được chọn. Ví dụ khi xây cho JDK 27:

~~~bash
javac --release 27 -d out src/com/acme/Main.java
~~~

Câu lệnh chỉ minh họa; phải thay file source bằng code thật khi áp dụng.

Nếu project cần chạy trên một JDK cũ hơn Java 27, chọn **--release của bản thấp nhất hỗ trợ** và kiểm tra runtime test tương ứng. **Việc biên dịch bằng JDK 27 không tự làm bytecode chạy được trên JDK 21**.

**Không dùng --add-exports như một cách mặc định để code mới biên dịch.** Những vấn đề về internal system packages có thể mâu thuẫn với mục tiêu của **--release**: thay API cần thiết kế lại hoặc chọn target được hỗ trợ.

Tương thích **source**, **binary** và **behavior** là ba lớp khác nhau; compile thành công chưa chứng minh runtime sẽ không lỗi vì reflection, module access hoặc sự khác biệt hành vi.

## 33. Các cổng kiểm soát trong CI

Một pipeline migration có thể gồm:

~~~mermaid
flowchart TD
    A["Source + locked dependencies"] --> B["Compile / --release"]
    B --> C["jdeps --jdk-internals"]
    C --> D["Unit + integration tests"]
    D --> E["Runtime test Java 27"]
    E --> F["Native / final / Unsafe strict-mode checks"]
    F --> G["Review temporary flags"]
    G --> H["Artifact và deployment approval"]
~~~

Các nguyên tắc:

- **Không chỉ kiểm tra exit code của jdeps rồi kết luận không có internal API**. Hãy giữ và xem báo cáo dependency; thiết kế rule CI theo dữ liệu thật công cụ cung cấp.
- Các mode **deny** dành cho readiness testing có thể cố ý làm hệ thống lỗi; chạy chúng trong môi trường thử nghiệm, không bật đột ngột ở production.
- Log các warnings/stack traces cùng bản build để xác định thư viện chịu trách nhiệm.
- Giữ danh sách cờ **--add-opens/--add-exports** được phép và phát hiện cờ mới xuất hiện không có lý do.
- Phân biệt kiểm tra **JDK vendor/version**, không chỉ đọc con số Java từ compiler.
- Chạy tests trong điều kiện tương đồng với production: classpath/module path, Java agent, container và JVM options.

**Kết quả mong muốn:** với mỗi cảnh báo hoặc dependency internal, team biết cách tái hiện, người chịu trách nhiệm, phương án thay thế và điều kiện gỡ bỏ workaround.

## 34. Security trade-offs của việc mở package

Những cờ JVM mở package có thể giúp khôi phục dịch vụ nhưng đồng thời **làm suy yếu một ranh giới đóng gói**.

Rủi ro gồm:

- Mã ngoài được phép nhìn hoặc thao tác với private state vốn không thuộc API.
- Thư viện có thể phụ thuộc hơn vào implementation details không ổn định.
- Một cờ **ALL-UNNAMED** có thể cấp khả năng truy cập cho nhiều JAR không liên quan.
- Cấu hình giữa local, CI và production khác nhau dẫn tới lỗi bất ngờ.
- Khi JDK tăng cường integrity constraints (như final mutation), cờ opens cũ không còn đủ.
- Việc theo dõi lỗ hổng hay đổi dependency khó hơn nếu toàn bộ internal access được xem như bình thường.

**Giảm rủi ro:**

1. Dùng qualified opens trong **module-info** của code do bạn sở hữu.
2. Nếu buộc dùng launch flags, chỉ định đúng package và target module khi có thể.
3. Không mở package lõi chỉ để bỏ qua một phép kiểm tra thất bại không rõ nguyên nhân.
4. Ghi nhận owner, thời hạn và version phụ thuộc.
5. Xóa workaround ngay sau khi có bản thư viện tương thích.
6. Ưu tiên public APIs, validation và process/OS boundaries cho các bài toán bảo mật.

**JPMS không thay quyền hệ điều hành.** Một library không được bạn tin cậy không nên được chạy trong cùng process với quyền cao rồi kỳ vọng module encapsulation sẽ sandbox toàn bộ hành vi của nó.

## 35. Một kịch bản migration từ Java cũ sang Java 27

Giả sử ứng dụng thương mại điện tử có ba triệu chứng:

- Framework serialization báo **InaccessibleObjectException** với java.base/java.lang.
- Thư viện cache dùng **sun.misc.Unsafe** và phát runtime warning.
- Một serializer cũ cố sửa **final field**.

**Giai đoạn 1 — Inventory và baseline**

~~~text
JDK cũ / JDK 27:
  source version, binary target, dependencies,
  java agents, containers, flags, test coverage.
~~~

Chạy jdeps, kiểm tra runtime logs và nhận diện artifact chính xác.

**Giai đoạn 2 — Thay đổi có mục đích**

- Nâng framework serializer lên bản có đường code hợp lệ với Java 27.
- Thay cache library hoặc adapter sử dụng Unsafe bằng bản hỗ trợ VarHandle.
- Chuyển DTO deserialization sang constructor/record factory thay vì sửa final field.
- Nếu một component nội bộ cần đọc metadata, bổ sung **public accessor** hoặc qualified opens đúng package thuộc quyền sở hữu ứng dụng.

**Giai đoạn 3 — Cầu nối tạm (nếu bắt buộc)**

Giữ một flag mở đúng package cụ thể để hệ thống tiếp tục hoạt động trong lúc chờ vendor sửa. Có ticket và kiểm thử hành vi khi gỡ flag. Không triển khai bộ add-opens rộng không được giải thích.

**Giai đoạn 4 — Readiness tests**

- Chạy Java 27 với cấu hình ứng dụng thực tế.
- Chạy test với **--sun-misc-unsafe-memory-access=deny**.
- Chạy test với **--illegal-final-field-mutation=deny**.
- Nếu có native libraries, chạy test tương ứng với **--illegal-native-access=deny**.
- Kiểm tra kết quả của jdeps và các luồng reflection có data thật.

**Giai đoạn 5 — Vận hành**

So sánh startup, latency, GC, resource consumption và error rates trước/sau. Xác nhận không còn cờ mở package không có owner, và tài liệu deployment phản ánh JDK mới.

## 36. Cách đọc một số lỗi nâng cấp điển hình

| Lỗi hoặc cảnh báo | Phân tích đúng | Bước ưu tiên |
|---|---|---|
| **does not export p to m** | Public type trong p chưa được export | API/module contract, thay internal API |
| **does not opens p to m** | Deep reflection vào p bị chặn | Nâng framework, public accessors, qualified opens |
| **InaccessibleObjectException** | setAccessible vi phạm JPMS | Xác định caller và package |
| **IllegalAccessError** | Binary linkage không có quyền phù hợp | Kiểm tra exports, reads và binary/runtime artifacts |
| **ClassNotFoundException** | Loader không tìm được class | Kiểm tra classpath, module path, artifact |
| **NoClassDefFoundError** | Class thiếu hoặc initialization lỗi | Tìm root cause, không chỉ thêm opens |
| **NoSuchMethodError** | Binary API mismatch | Đồng bộ dependencies/JDK versions |
| **UnsupportedClassVersionError** | Target bytecode mới hơn runtime | Dùng JDK phù hợp/điều chỉnh --release |
| Warning về **sun.misc.Unsafe** | Unsupported memory operation còn chạy | Tìm caller, nâng/thay API |
| Warning về **final field mutation** | Serializer/ORM cố sửa final | Constructor/factory hoặc bản thư viện mới |
| **IllegalCallerException** trong native mode deny | Module thiếu quyền restricted native access | Đánh giá FFM/JNI và quyền có phạm vi |
| **UnsupportedOperationException** với Unsafe deny | Dùng memory-access method bị chặn | Thay bằng VarHandle/FFM |

Không bỏ qua **stack trace đầu tiên**: trong một phiên khởi tạo lỗi, exception về sau có thể chỉ là hậu quả của nguyên nhân đầu tiên.

## 37. Bài tập 1: phân loại các trường hợp

Hãy quyết định chọn **thay API**, **exports**, **opens** hay **sửa dependency**, kèm lý do:

1. Code ứng dụng gọi **sun.misc.BASE64Encoder**.
2. Thư viện cũ cố đọc private field của String.
3. Module domain muốn cho module report gọi public class trong package api.
4. Framework cần reflection vào private field của entity do domain sở hữu.
5. Đội dự án dùng **sun.misc.Unsafe.getAndAddInt**.
6. Java agent sửa final field của một DTO để khởi tạo.
7. Có **NoClassDefFoundError** sau khi đổi JDK mà không xuất hiện lỗi opens.
8. Một JAR plugin chỉ được đọc thông qua ServiceLoader theo interface công khai.

**Hướng tự đánh giá:** với câu 1 và 5, tìm API thay thế ổn định; câu 2 và 6, cập nhật library và mô hình đối tượng; câu 3, dùng exports; câu 4, cân nhắc public accessor hoặc qualified opens; câu 7 phải điều tra dependency/initialization; câu 8 kiểm tra service descriptors và module resolution, không thêm quyền vô cớ.

## 38. Bài tập 2: chẩn đoán bằng jdeps

Trên **một project mẫu được phép thao tác**:

1. Xây artifact theo quy trình sẵn có của project.
2. Chạy **jdeps --jdk-internals** lên JAR chính.
3. Chạy lại với **--class-path** chứa dependencies và **--multi-release** khi cần.
4. Phân loại kết quả thành **code do team sở hữu** và **code do bên thứ ba sở hữu**.
5. Đối chiếu từng package nội bộ với API public thay thế.
6. Lập danh sách những trường hợp jdeps không thể thấy như reflection bằng chuỗi.
7. Chạy integration test trên Java 27 và so sánh với findings của jdeps.

**Không sửa file khác trong bài tập khi đang thực thi assignment worker.** Những lệnh đó dành cho người học trong môi trường thực hành riêng.

## 39. Bài tập 3: thử module encapsulation

Với ví dụ hai modules ở mục 24:

1. Chạy khi package model được **opens ... to com.acme.reader**.
2. Bỏ opens và biên dịch/chạy lại.
3. Quan sát **InaccessibleObjectException** và public method vẫn hoạt động.
4. Thêm public accessor cho dữ liệu cần đọc, xóa hoàn toàn deep reflection.
5. Bỏ opens lần nữa và xác minh ứng dụng vẫn chạy.
6. Giải thích vì sao chỉ dùng **exports** không mở private fields.

Nếu muốn thử command-line workaround, hãy làm trong demo có phạm vi kiểm soát, **không** mang cờ thử nghiệm đó vào production vô điều kiện.

## 40. Bài tập 4: kiểm tra final field và native restrictions

Trong một ứng dụng mẫu hoặc thư viện thử nghiệm:

- Xem thư viện có mutate final fields bằng reflection không; dùng **--illegal-final-field-mutation=deny** để kiểm tra readiness.
- Với FFM API, phân biệt thao tác MemorySegment an toàn thông thường với việc gọi **restricted native methods**.
- Nếu có JNI hoặc FFM restricted access, chạy kiểm thử với **--illegal-native-access=deny** và cấp quyền chọn lọc khi thật sự cần.
- Nếu dùng legacy Unsafe, xác định caller bằng **--sun-misc-unsafe-memory-access=debug** rồi thử **deny** ở môi trường test.
- Nêu chính xác các quyền nào không được giải quyết chỉ bằng **--add-opens**.

Mục đích là tìm đường code phải sửa, không phải phát triển thêm một phụ thuộc vào quyền đặc biệt.

## 41. Checklist trước khi chuyển production sang Java 27

- [ ] Đã xác định phiên bản Java mục tiêu, vendors và deployment environments.
- [ ] Biết rõ nguồn build artifacts và runtime dependencies đang được sử dụng.
- [ ] Đã chạy **jdeps --jdk-internals** trên những JAR liên quan.
- [ ] Đã xét multi-release JAR, plugin, agent và transitive dependencies.
- [ ] Đã kiểm tra các đường đi reflection động không hiện trong jdeps.
- [ ] Đã phân biệt Java SE public, documented JDK-specific và internal APIs.
- [ ] Không có code mới import JDK internal package.
- [ ] Đã thay legacy Base64 bằng **java.util.Base64**.
- [ ] Đã đánh giá VarHandle/Atomic classes cho atomic operations và FFM cho native memory.
- [ ] Không sử dụng **--illegal-access** như một giải pháp tương thích.
- [ ] Biết chính xác khi nào cần **exports** và khi nào cần **opens**.
- [ ] Ưu tiên public accessor/factory trước khi thêm deep reflection.
- [ ] Nếu tạm dùng **--add-exports/--add-opens**, mọi flag có caller, owner và hạn xử lý.
- [ ] Không sử dụng bộ cờ ALL-UNNAMED rộng chỉ vì copy từ Internet.
- [ ] Không coi opens là quyền sửa final fields không giới hạn.
- [ ] Đã kiểm tra final field mutation warnings và hành vi **deny** trong test.
- [ ] Đã kiểm tra memory-access methods của **sun.misc.Unsafe**, bao gồm cảnh báo/deny.
- [ ] Đã kiểm tra native access riêng nếu dùng JNI/FFM restricted operations.
- [ ] Đã rà module descriptors và lớp startup/service discovery.
- [ ] Đã chạy unit, integration, reflection, serialization, module-path và smoke tests.
- [ ] Đã đối chiếu source/binary/runtime compatibility, không chỉ compile success.
- [ ] Đã đo startup/performance/memory và so baseline có cùng workload.
- [ ] Đã rà private data và security implications của opens/exports.
- [ ] Có rollback plan, release notes và cơ chế phát hiện lỗi sau triển khai.
- [ ] Đã loại bỏ những cờ workaround không còn cần thiết.
- [ ] Không xây sandbox mới dựa trên Security Manager đã bị vô hiệu hóa.

**Kết luận:** Nâng cấp Java 27 thành công không có nghĩa "mở đủ package để chương trình hết lỗi". Strong encapsulation là hợp đồng kỹ thuật nhằm giữ implementation details bên trong JDK. Cách nâng cấp bền vững là **dùng API được hỗ trợ, cập nhật thư viện, phân quyền module rõ, kiểm tra runtime và loại bỏ workaround có kế hoạch**. Những flags như **--add-opens** hoặc **--add-exports** chỉ là biện pháp có phạm vi và thời hạn, không phải API công khai được bảo đảm dài hạn.

## Tài liệu tham khảo

- [Oracle JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/index.html): hướng dẫn nâng cấp Java 27 và các thay đổi tương thích.
- [Oracle JDK 27 — Migrating from JDK 8 to Later Releases](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): strong encapsulation, --add-opens/--add-exports, Unsafe, native access và final fields.
- [Oracle JDK 27 — Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html): quét JDK internal dependencies bằng jdeps, giới hạn của phân tích tĩnh.
- [Oracle JDK 27 — Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html): cảnh báo và quyền mutate final instance fields.
- [Oracle JDK 27 — java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): --add-opens, --add-exports, --enable-final-field-mutation, --enable-native-access và những chế độ deny.
- [Oracle JDK 27 — jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): --jdk-internals, --multi-release, classpath/module path.
- [Java SE 27 — AccessibleObject](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): canAccess, trySetAccessible, setAccessible và ranh giới JPMS.
- [Java SE 27 — VarHandle](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html): các memory access modes được hỗ trợ.
- [Java SE 27 — MemorySegment](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html), [Arena](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): foreign memory và vòng đời vùng nhớ.
- [Java SE 27 — Base64](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Base64.html): basic, URL-safe và MIME variants.
- [Java SE 27 — MethodHandles](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup và reflective invocation.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module system, exports/opens và migration flags.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation.
- [JEP 471 — Deprecate the Memory-Access Methods in sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471): lý do thay thế Unsafe.
- [JEP 498 — Warn upon Use of Memory-Access Methods in sun.misc.Unsafe](https://openjdk.org/jeps/498): cảnh báo và chế độ warn/debug/deny.
- [JEP 500 — Prepare to Make final Mean Final](https://openjdk.org/jeps/500): integrity by default và hạn chế mutate final fields.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API chính thức.
