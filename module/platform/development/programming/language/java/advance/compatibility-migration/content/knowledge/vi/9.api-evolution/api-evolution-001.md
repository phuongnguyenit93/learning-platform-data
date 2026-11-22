# Xác định API công khai, SPI và phần triển khai không cam kết ổn định

Khi nâng phiên bản Java hoặc thay đổi framework, một chương trình có thể ngừng hoạt động dù các class và method từng sử dụng vẫn được khai báo public. Nguyên nhân là **quyền truy cập của ngôn ngữ Java** và **cam kết tương thích của nhà cung cấp** không phải cùng một điều. Một thành phần có thể truy cập được nhưng chỉ phục vụ nội bộ; một interface public có thể được thiết kế cho plugin triển khai dưới dạng SPI; một API được tài liệu hóa có thể có chính sách deprecated hoặc thay đổi hành vi trong những giới hạn đã công bố.

Bài học thuộc chủ đề **Java Advance Compatibility Migration**, chương **Tiến hóa API**, giải thích cách xác định bề mặt hợp đồng giữa ứng dụng, JDK, framework và thư viện bên ngoài. Mục tiêu là biết đâu là **API công khai được hỗ trợ**, đâu là **Service Provider Interface (SPI)** dành cho người viết provider, và đâu là **chi tiết triển khai không cam kết ổn định** cần tránh phụ thuộc lâu dài.

## 1. Ba loại bề mặt thường gặp

### 1.1. API công khai được hỗ trợ

Application Programming Interface là tập hợp điểm tích hợp mà một nền tảng hoặc thư viện cung cấp cho consumer. Với Java, API bao gồm nhiều hơn chữ ký của method:

- Class, interface, enum, annotation và public constructor.
- Method, field, kiểu tham số, kiểu trả về và generic signature.
- Hợp đồng về null, exception, lỗi đầu vào và xử lý biên.
- Quy định về trạng thái, thời gian sống của object và thread-safety.
- Định dạng dữ liệu, serialization, encoding và thứ tự kết quả nếu có cam kết.
- Hành vi được định nghĩa bằng specification, API documentation hoặc hợp đồng phiên bản.

Ví dụ java.util.List là API Java SE được mô tả bằng tài liệu chính thức. Consumer có thể lập trình dựa vào các method được cam kết của List mà không cần biết phần triển khai sử dụng array, linked nodes hay cấu trúc khác.

Một API public được hỗ trợ không có nghĩa mọi hành vi đều bất biến. Nhà cung cấp vẫn có thể sửa lỗi, thay đổi tối ưu hóa, deprecate hoặc loại bỏ thành phần theo chính sách và vòng đời phát hành. Consumer cần tuân thủ những gì thực sự được đặc tả.

### 1.2. SPI dành cho provider

Service Provider Interface là hợp đồng để một bên thứ ba tạo implementation được framework hoặc nền tảng gọi lại.

Ví dụ:

- JDBC có cơ chế cho database driver tham gia hệ sinh thái.
- java.nio.file.spi.FileSystemProvider là điểm mở rộng cho filesystem provider.
- java.util.spi và java.text.spi chứa các điểm mở rộng của Java Platform.
- Một framework có thể công bố authentication provider, serializer, task plugin hoặc storage adapter.

Với API thông thường, ứng dụng **gọi** dịch vụ. Với SPI, ứng dụng hoặc plugin **triển khai** một giao diện và framework **gọi lại** implementation đó. Một SPI vẫn có thể là API public được hỗ trợ, nhưng hướng phụ thuộc và trách nhiệm tương thích khác nhau.

### 1.3. Implementation detail

Implementation detail là thành phần phục vụ cách thư viện được cài đặt, chưa được nhà cung cấp cam kết duy trì như điểm tích hợp bên ngoài:

- Class thuộc package internal hoặc impl.
- Cấu trúc dữ liệu private bị đọc bằng reflection.
- Compiler internals hoặc runtime internals.
- Class public chỉ được dùng giữa các module nội bộ.
- Resource tạm, cache format và đường dẫn riêng của implementation.
- Thứ tự duyệt hoặc timing không được contract bảo đảm.
- Kiểu exception cụ thể hay nội dung error message không được tài liệu hứa ổn định.

Một public class có thể là implementation detail. Việc compiler cho phép import class đó không có nghĩa nhà cung cấp phải giữ nó ở lần nâng cấp tiếp theo.

### 1.4. Bảng phân biệt nhanh

| Tiêu chí | API công khai | SPI | Implementation detail |
|---|---|---|---|
| Vai trò chính | Consumer gọi chức năng | Provider triển khai để framework gọi | Thành phần thư viện sử dụng nội bộ |
| Có thể là public? | Thường có | Thường có | Có thể có |
| Hợp đồng quan trọng | Tham số, kết quả, exception, behavior | Callback, lifecycle, discovery, concurrency | Thường không công bố |
| Bằng chứng | API docs, specification, support policy | SPI docs, provider guide, service metadata | Source, annotation internal, package và tài liệu |
| Rủi ro khi nâng | Thay chữ ký/hành vi | Provider không tương thích | Có thể biến mất hoặc đổi bất kỳ lúc nào |
| Cách xử lý | Theo release notes và migration guide | Test từ phía provider | Chuyển sang API/SPI được hỗ trợ |

## 2. Quyền truy cập public không phải cam kết ổn định

Xem thư viện giả định:

~~~java
package com.example.cache.internal;

public final class CacheTable {
    public static int nextCapacity(int current) {
        return current * 2;
    }
}
~~~

Class CacheTable là public, nên có thể truy cập trong một số cấu hình classpath hoặc module. Nhưng package internal cho thấy nhiều khả năng nó là chi tiết triển khai. Nếu ứng dụng gọi trực tiếp nextCapacity, việc thay chiến lược lưu cache ở phiên bản mới có thể làm ứng dụng lỗi compile hoặc runtime.

Thư viện nên công bố hợp đồng như:

~~~java
package com.example.cache.api;

public interface Cache<K, V> {
    V get(K key);
    void put(K key, V value);
}
~~~

Ứng dụng phụ thuộc vào Cache, còn thư viện có thể thay CacheTable mà không phá vỡ hợp đồng.

**Cần phân biệt ba câu hỏi:** Có truy cập được không? Nhà cung cấp có chủ đích cho bên ngoài sử dụng không? Nhà cung cấp cam kết duy trì theo chính sách nào? Chỉ câu đầu không đủ để xác định một API ổn định.

Một số thư viện để class public vì ràng buộc từ serializer, dependency injection hoặc kiến trúc module. Vì vậy, việc một kiểu là public cần được đối chiếu với documentation, annotation, release notes và support policy.

## 3. Nhận diện API được hỗ trợ của JDK

Với JDK, ưu tiên specification và API documentation chính thức cho phiên bản Java mục tiêu. Nhiều API tiêu chuẩn nằm trong java.util, java.time, java.net, java.nio, java.sql, java.security và các package được tài liệu hóa khác.

Không thể chỉ nhìn tiền tố package để đưa ra kết luận tuyệt đối. Ví dụ:

| Thành phần | Cách phân loại thực tế |
|---|---|
| java.util.List | API Java SE được tài liệu hóa |
| java.time.Instant | API Java SE được tài liệu hóa |
| java.sql.Connection | API được công bố; JDBC driver cung cấp implementation |
| java.nio.file.spi.FileSystemProvider | SPI được công bố |
| java.util.ServiceLoader | API phục vụ tìm và nạp provider |
| com.sun.source.tree.Tree | API compiler được tài liệu hóa trong jdk.compiler |
| com.sun.tools.javac.* | Các package compiler implementation, không nên mặc định là API ổn định |
| jdk.internal.misc.Unsafe | API nội bộ của JDK |
| sun.misc.Unsafe | Critical internal API trong jdk.unsupported, không mang cam kết như Java SE API |

Một tiền tố như com.sun không tự động biến mọi kiểu thành internal; một public class do JDK cung cấp cũng không tự động là API tiêu chuẩn. Hãy kiểm tra tài liệu của đúng module và đúng JDK release.

### 3.1. Trường hợp dùng JDK internal API

Ứng dụng hoặc dependency có thể dựa vào sun.misc.Unsafe, jdk.internal.*, compiler internals hoặc reflection vào field nội bộ. Các đường phụ thuộc đó dễ bị ảnh hưởng khi JVM thay cách quản lý bộ nhớ, module encapsulation hoặc cấu trúc class.

Nếu mã nguồn dùng API nội bộ để thao tác atomic field, hãy đánh giá VarHandle khi phù hợp. Nếu dùng các API bộ nhớ/native, hãy đánh giá những API công khai về Foreign Function & Memory trên phiên bản JDK đáp ứng yêu cầu. Đừng thay cơ học một method bằng method khác: memory ordering, ownership, alignment, lifetime và lỗi có thể khác nhau.

Nếu một thư viện thứ ba cần JDK internal API, ưu tiên nâng thư viện lên phiên bản được nhà cung cấp kiểm chứng trên JDK mục tiêu. Ứng dụng không nên tự vá implementation của thư viện nếu có đường nâng cấp được hỗ trợ.

## 4. JPMS: exports và opens cung cấp khả năng truy cập nào?

Java 9 giới thiệu Java Platform Module System. Một module descriptor có thể khai báo:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence to org.hibernate.orm.core;
    requires java.sql;
}
~~~

Ý nghĩa:

- exports cung cấp khả năng truy cập các public type của package cho những module phù hợp.
- opens cho phép reflective access ở phạm vi được chỉ định.
- requires xác định dependency giữa các module.

**Exported package không đồng nghĩa API ổn định vĩnh viễn.** Một nhà cung cấp có thể export package để các module của chính mình trao đổi. Có cả qualified export giới hạn consumer:

~~~java
module com.example.engine {
    exports com.example.engine.api;
    exports com.example.engine.bridge to com.example.engine.tools;
}
~~~

Package bridge được export có giới hạn, không có nghĩa mọi ứng dụng nên sử dụng nó.

Cũng cần phân biệt classpath và module path. Một ứng dụng chạy trên classpath truyền thống thường thuộc unnamed module. Khi chuyển sang module path, compiler/runtime có thể phát hiện vi phạm module readability hoặc package không được export. Một class public trong một module không được export có thể vẫn không truy cập được từ module khác.

### 4.1. Các cờ mở quyền truy cập không làm API ổn định hơn

Có thể gặp cấu hình như:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -jar app.jar
~~~

hoặc:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Các cờ trên phục vụ các nhu cầu truy cập khác nhau. Chúng có thể giúp một ứng dụng hoặc thư viện cũ vượt qua một rào cản trong giai đoạn chuyển tiếp, nhưng không tạo ra cam kết duy trì implementation detail.

Khi migration, hãy ghi nhận component cần cờ, package được mở, lý do, phạm vi rủi ro và phiên bản dependency dự kiến loại bỏ nhu cầu đó. Từ Java 17, strong encapsulation của JDK internals được siết theo JEP 403, nên một số lối truy cập cũ không còn hoạt động như trên JDK trước đó.

## 5. Nhận diện API và SPI của framework hoặc thư viện thứ ba

Với dependency bên ngoài, hãy xem:

- API reference và Javadoc được phát hành.
- Migration guide và release notes.
- Stability policy và lịch hỗ trợ của phiên bản.
- Package convention: api, spi, extension, internal, impl.
- Annotation như @Internal, @ApiStatus.Internal, @ApiStatus.Experimental hoặc annotation riêng của thư viện.
- Modul​e exports và qualified exports nếu thư viện dùng JPMS.
- Mẫu code chính thức và hướng dẫn viết extension/provider.

Ví dụ một thư viện có thể có cấu trúc:

~~~text
com.example.framework.api.RequestContext
com.example.framework.spi.RequestHandlerProvider
com.example.framework.internal.FastDispatcher
com.example.framework.impl.DefaultRequestContext
~~~

Tên package là tín hiệu ban đầu, không đủ để kết luận. Một class trong impl có thể được công bố để dùng làm implementation mặc định; một class trong api có thể được đánh dấu experimental hoặc deprecated. Phải đọc hợp đồng của đúng bản phát hành.

Các thẻ Javadoc @apiNote, @implSpec và @implNote giúp giải thích API contract và nghĩa vụ của implementation. Chúng không tự cam kết khả năng tương thích qua mọi phiên bản.

### 5.1. API do ứng dụng công bố cũng có thể làm lộ implementation

Xem một public method trả về kiểu internal:

~~~java
package com.example.api;

public class ReportService {
    public com.example.internal.RowBuffer loadRows() {
        throw new UnsupportedOperationException();
    }
}
~~~

Consumer phải tham chiếu RowBuffer để sử dụng method. Như vậy, một implementation detail đã rò rỉ vào public signature, làm khả năng đổi cấu trúc nội bộ bị hạn chế.

Một contract rõ ràng hơn là:

~~~java
package com.example.api;

import java.util.List;

public interface ReportService {
    List<ReportRow> loadRows();
}
~~~

Trong đó ReportRow cũng là kiểu public API được tài liệu hóa. Việc thiết kế bề mặt API cần xét đến return type, generic type, checked exception, annotation và kiểu kế thừa, không chỉ tên method.

## 6. SPI: hướng gọi ngược và hợp đồng vòng đời

API thường là thành phần mà ứng dụng chủ động gọi. SPI thường yêu cầu ứng dụng cung cấp một provider để framework khởi tạo và gọi lại.

~~~text
Ứng dụng sử dụng tính năng
            |
            v
         Public API
            |
            v
    Framework / Platform
            |
            v
         SPI contract
            ^
            |
     Provider implementation
~~~

Framework có thể quyết định số instance provider, thứ tự callback, thời điểm khởi tạo, thời điểm đóng, concurrency và cách xử lý exception. Do đó, việc một interface SPI không thay chữ ký không bảo đảm provider cũ tương thích về hành vi.

### 6.1. Ví dụ ServiceLoader

Giả sử hệ thống báo cáo công bố interface:

~~~java
package com.example.report.spi;

public interface FormatterProvider {
    String id();
    String format(Report report);
}
~~~

Report ở đây là kiểu API của hệ thống, không phải implementation nội bộ. Một provider:

~~~java
package com.example.report.json;

public final class JsonFormatterProvider implements FormatterProvider {
    @Override
    public String id() {
        return "json";
    }

    @Override
    public String format(Report report) {
        return report.toJson();
    }
}
~~~

Framework tìm provider:

~~~java
ServiceLoader<FormatterProvider> loader =
        ServiceLoader.load(FormatterProvider.class);

for (FormatterProvider provider : loader) {
    System.out.println(provider.id());
}
~~~

Code minh họa không liệt kê đầy đủ import và các kiểu Report; trong dự án thực tế cần dùng đúng API và package.

### 6.2. Đăng ký service trên module path

Module công bố service type:

~~~java
module com.example.report {
    exports com.example.report.api;
    exports com.example.report.spi;
    uses com.example.report.spi.FormatterProvider;
}
~~~

Một provider module:

~~~java
module com.example.report.json {
    requires com.example.report;

    provides com.example.report.spi.FormatterProvider
        with com.example.report.json.JsonFormatterProvider;
}
~~~

Provider implementation không nhất thiết phải nằm trong exported package dành cho người dùng. ServiceLoader có thể dùng thông tin module để tìm provider theo service contract.

Nếu dùng classpath, cơ chế đăng ký phổ biến là file:

~~~text
META-INF/services/com.example.report.spi.FormatterProvider
~~~

Với nội dung tên class provider:

~~~text
com.example.report.json.JsonFormatterProvider
~~~

Khi đóng gói shaded JAR hoặc fat JAR, phải bảo đảm các META-INF/services descriptor được hợp nhất thay vì ghi đè. Provider có thể tồn tại trong JAR nhưng không được ServiceLoader khám phá nếu resource registration bị mất.

### 6.3. Những câu hỏi riêng cho SPI

Hãy kiểm tra hợp đồng provider:

1. Framework tạo instance bằng constructor, factory hay dependency injection?
2. Có thể có nhiều provider cùng hoạt động không?
3. Provider được lựa chọn dựa trên priority, tên hay thứ tự duyệt?
4. Callback có thể gọi song song từ nhiều thread không?
5. Có ràng buộc thread-safety hoặc reentrancy không?
6. Provider được phép giữ cache hoặc shared state không?
7. Khi nào initialize, flush, close và dispose?
8. Exception nào provider được phép ném; framework xử lý thế nào?
9. Có API version hay capability negotiation không?
10. Provider cần được đóng gói và khám phá bằng cơ chế nào?

Một provider compile thành công nhưng không được load, hoặc được load nhưng vi phạm lifecycle mới, vẫn là trường hợp SPI migration thất bại.

## 7. Phân biệt thay đổi API và thay đổi SPI

### 7.1. API được consumer gọi

Giả sử thư viện cung cấp:

~~~java
public interface SearchClient {
    List<Result> search(String query);
}
~~~

Phiên bản mới đổi thành:

~~~java
public interface SearchClient {
    List<Result> search(SearchRequest request);
}
~~~

Consumer dùng chữ ký cũ phải sửa mã. Consumer đã biên dịch từ trước có thể gặp linkage error khi chạy với thư viện mới nếu method cũ bị loại bỏ.

Khi thêm overload mới, mã nhị phân cũ có thể tiếp tục liên kết, nhưng mã nguồn biên dịch lại có thể xuất hiện overload ambiguity với null, lambda hoặc method reference. Vì vậy, source compatibility và binary compatibility phải được đánh giá riêng.

### 7.2. SPI do provider triển khai

Một SPI ban đầu:

~~~java
public interface FormatterProvider {
    String format(Object value);
}
~~~

Bản mới thêm abstract method:

~~~java
public interface FormatterProvider {
    String format(Object value);
    boolean supports(Class<?> type);
}
~~~

Provider cũ chưa có supports có thể không biên dịch lại được. Khi runtime gọi method mới trên một provider cũ, có thể xuất hiện AbstractMethodError.

Một hướng tiến hóa là default method:

~~~java
public interface FormatterProvider {
    String format(Object value);

    default boolean supports(Class<?> type) {
        return true;
    }
}
~~~

Tuy nhiên, default method không bảo đảm mọi provider đều đúng hành vi. Giá trị true có thể không phản ánh khả năng của provider, và default method có thể tương tác với cấu trúc kế thừa hiện có. Cần test với provider thực tế.

### 7.3. Implementation detail được thay thế

Một framework có thể thay class nội bộ FastDispatcher bằng implementation khác nhưng vẫn giữ nguyên public API. Consumer sử dụng API có thể hoạt động bình thường. Consumer đã import FastDispatcher, ép kiểu về class đó hoặc reflection vào field private có thể thất bại ngay cả khi bản nâng cấp là hợp lệ theo support policy.

Đó là lý do cần audit ranh giới API/SPI và code triển khai trước khi nâng phiên bản.

## 8. Phân tích các mức tương thích khác nhau

| Mức tương thích | Câu hỏi cần trả lời |
|---|---|
| Source | Mã nguồn consumer/provider cũ có compile với version mới không? |
| Binary | Bytecode đã biên dịch có link và chạy với library mới không? |
| Behavioral | Kết quả và side effect có còn đúng theo hợp đồng không? |
| SPI | Provider có được discovery, khởi tạo và gọi đúng lifecycle không? |
| Runtime | Artifact có chạy được trên JVM mục tiêu không? |
| Operational | Logs, metrics, startup, shutdown và rollback có hoạt động không? |

Một ví dụ về behavioral compatibility là thứ tự duyệt HashMap. API không bảo đảm iteration order, nên một ứng dụng dựa vào thứ tự tình cờ của phiên bản JDK hiện tại đang phụ thuộc implementation detail. Khi thứ tự thay đổi, lỗi nằm ở kỳ vọng của ứng dụng, dù interface vẫn đúng hợp đồng.

Nếu nghiệp vụ cần thứ tự, hãy dùng một collection có hợp đồng rõ như LinkedHashMap cho insertion order, hoặc sort kết quả dựa vào Comparator.

Một ví dụ khác là assert nguyên văn exception message. Trừ khi documentation cam kết thông điệp, việc thay đổi wording trong bản vá thường không phải breaking change của API.

## 9. Dấu hiệu đang phụ thuộc implementation detail

Khi kiểm kê mã nguồn, chú ý các tín hiệu:

- Import jdk.internal hoặc sun.*.
- Import com.sun.tools.javac thay vì API compiler được công bố.
- Import package internal, impl hoặc private của framework.
- Gọi setAccessible(true), getDeclaredField hoặc getDeclaredMethod lên lớp của JDK/framework.
- Gọi Class.forName với tên implementation cụ thể.
- Ép kiểu từ public interface sang concrete implementation.
- Kế thừa class không được tài liệu là extension point.
- Đọc resource, cache, temporary file hoặc metadata nội bộ.
- Dựa vào timing, iteration order hoặc error message không được cam kết.
- Yêu cầu --add-opens hay --add-exports để vượt qua encapsulation.
- Dùng API được đánh dấu @Internal hoặc @Experimental mà chưa đánh giá rủi ro.
- Public method của ứng dụng làm lộ internal type trong signature.

Đây là danh sách tín hiệu điều tra. Một package có tên impl đôi khi chứa default implementation được nhà cung cấp chính thức hỗ trợ. Ngược lại, một API nằm trong package dễ nhìn có thể được đánh dấu experimental. Đừng tự động kết luận chỉ dựa vào tên.

## 10. Công cụ nhận diện và kiểm tra

### 10.1. jdeps

Công cụ jdeps của JDK có thể phân tích dependency của JAR và phát hiện một số API nội bộ của JDK:

~~~bash
jdeps --jdk-internals app.jar
~~~

Với dependency trên classpath:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

Nếu phân tích multi-release JAR, có thể chỉ định target release:

~~~bash
jdeps --multi-release 21 --jdk-internals app.jar
~~~

Kết quả chỉ ra đường tham chiếu tĩnh tới JDK internals. Nó không chắc tìm được mọi đường reflection, tên class xây dựng động, plugin nạp khi chạy hoặc dependency thiếu khỏi classpath phân tích. Không có cảnh báo từ jdeps không đủ chứng minh ứng dụng hoàn toàn không phụ thuộc nội bộ.

### 10.2. jdeprscan

Công cụ jdeprscan giúp phát hiện việc sử dụng API Java SE đã deprecated:

~~~bash
jdeprscan --release 21 app.jar
~~~

Để xem API được đánh dấu for-removal:

~~~bash
jdeprscan --for-removal --release 21 app.jar
~~~

Deprecated API khác internal API. Một API được hỗ trợ có thể được deprecate và có hướng thay thế công khai; internal API có thể chưa từng được công bố là ổn định.

### 10.3. javap và jar

Xem public member trong class file:

~~~bash
javap -public -classpath library.jar com.example.api.SearchClient
~~~

Xem class metadata:

~~~bash
javap -verbose -classpath library.jar com.example.api.SearchClient
~~~

Xem module declaration của JAR khi có:

~~~bash
jar --describe-module --file library.jar
~~~

Các công cụ này cung cấp bằng chứng kỹ thuật về access và bytecode. Chúng không tự cho biết nhà cung cấp cam kết duy trì API trong bao lâu.

### 10.4. So sánh API qua các version

Những công cụ như Revapi hoặc japicmp có thể phát hiện thay đổi chữ ký class/method/field, superclass, interface và visibility giữa hai bản phát hành. Nên cấu hình để so sánh đúng bề mặt công khai được hỗ trợ.

Nếu đem mọi package internal vào báo cáo và coi mọi thay đổi là breaking change, kết quả sẽ nhiều nhiễu. Nếu chỉ so sánh bytecode, có thể bỏ sót thay đổi về exception, lifecycle, serialization hoặc semantics của SPI.

### 10.5. Tìm usage trong repository

Có thể tìm nhanh bằng ripgrep:

~~~bash
rg -n "jdk[.]internal|sun[.]misc|com[.]sun[.]tools[.]javac" src
~~~

Tìm reflection:

~~~bash
rg -n "setAccessible|getDeclaredField|getDeclaredMethod|Class[.]forName" src
~~~

Tìm import theo package convention:

~~~bash
rg -n "import .*([.]internal[.]|[.]impl[.])" src
~~~

Ripgrep chỉ là tìm kiếm văn bản, nên có thể bỏ sót generated source, bytecode của dependency hoặc class name được tạo động. Hãy đối chiếu cả compile/runtime dependency và cấu hình deployment.

## 11. Xác định phiên bản dependency thực tế

Trước khi kết luận framework thay API, phải biết phiên bản dependency nào thực sự được resolve, bao gồm transitive dependency.

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Truy nguyên một module bằng Gradle:

~~~bash
./gradlew dependencyInsight --dependency some-library --configuration runtimeClasspath
~~~

Kết quả graph có thể bị ảnh hưởng bởi BOM, parent POM, Gradle platform, constraint, resolution rule và profile. Phiên bản thực tế đôi khi khác phiên bản hiển thị trong một khai báo được tìm thấy qua search.

Ngoài dependency compile/runtime, cần tính đến annotation processor, Java agent, plugin, driver được nạp động, native library và các provider discovery resources. Những thành phần này cũng có thể phụ thuộc implementation detail mà source chính không import.

## 12. Ví dụ thay JDK internal API bằng API công khai

Một số codebase cũ sử dụng các tiện ích Base64 nội bộ thay vì API Java SE. Từ Java 8, java.util.Base64 cung cấp API công khai cho việc mã hóa/giải mã Base64.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class TokenCodec {
    public static String encode(String input) {
        byte[] bytes = input.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public static String decode(String input) {
        byte[] bytes = Base64.getDecoder().decode(input);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

Khi thay implementation cũ, phải xác nhận:

- Basic Base64, URL-safe Base64 hay MIME?
- Có xuống dòng và padding không?
- Đầu vào là UTF-8 hay dữ liệu binary?
- Invalid input được xử lý ra sao?
- Định dạng đã được lưu hoặc trao đổi qua API có thay đổi không?

Code mới dùng API được hỗ trợ nhưng có thể làm đổi dữ liệu trên wire nếu chọn không đúng variant. Việc sửa internal dependency phải bảo toàn hợp đồng nghiệp vụ, không chỉ làm compile thành công.

## 13. Ví dụ chuyển từ implementation class sang extension point

Giả sử ứng dụng phụ thuộc class nội bộ của framework:

~~~java
import com.example.framework.internal.DefaultRetryPolicy;

public class JobRunner {
    private final DefaultRetryPolicy policy =
            new DefaultRetryPolicy();
}
~~~

Framework không cam kết constructor và hành vi của DefaultRetryPolicy. Khi nâng version, class có thể thay đổi hoặc biến mất.

Nếu framework công bố contract:

~~~java
package com.example.framework.api;

public interface RetryPolicy {
    boolean shouldRetry(int attempt, Throwable failure);
}
~~~

và một factory được hỗ trợ, ứng dụng có thể phụ thuộc vào RetryPolicy thay vì class triển khai cụ thể.

~~~java
RetryPolicy policy = RetryPolicies.exponentialBackoff(3);
~~~

Tên factory chỉ dùng minh họa; khi sửa dự án thực tế phải tham chiếu chính xác API được tài liệu của framework công bố.

Sau khi chuyển, cần kiểm tra số lần retry, backoff, jitter, lỗi có thể retry và idempotency của side effect. Một API thay thế có thể đúng cú pháp nhưng khác behavior.

## 14. API preview, incubator và experimental

Không phải mọi API mới trong JDK đều có trạng thái ổn định như Java SE API final.

### 14.1. Preview

Một tính năng preview có thể yêu cầu tùy chọn compiler và runtime:

~~~bash
javac --enable-preview --release 21 Example.java
java --enable-preview Example
~~~

Cú pháp bật preview chỉ minh họa cơ chế; tính năng nào preview phụ thuộc đúng release đang dùng. Preview feature có thể thay đổi hoặc bị loại trước khi thành final.

### 14.2. Incubator

Một module incubator trong JDK dùng để thử nghiệm API và lấy phản hồi. Dù được phân phối cùng JDK, API đó có thể thay đổi đáng kể khi tiến hóa. Một số phiên bản từng dùng các module mang tên jdk.incubator.*.

### 14.3. Experimental trong framework

Một library có thể đánh dấu API là experimental, unstable hoặc incubating. Nếu sản phẩm cần dùng tính năng đó, nên ghi rõ lý do, version đã kiểm thử, owner theo dõi release notes và kế hoạch chuyển đổi khi API thay đổi.

Không nhất thiết cấm mọi API experimental, nhưng không nên vô tình coi nó là hợp đồng ổn định nhiều năm.

## 15. Lập ma trận rủi ro trước migration

| Thành phần | Phân loại | Bằng chứng | Hành động gợi ý |
|---|---|---|---|
| Java SE documented API | Public API | Java API docs | Kiểm tra deprecation và chạy test |
| Framework documented API | Public API | Javadoc, migration guide | Nâng theo policy của vendor |
| Plugin/provider interface | SPI | SPI guide, callback contract | Test discovery, lifecycle, concurrency |
| Framework internal package | Implementation | Tài liệu, annotation, source | Thay bằng API hoặc extension point |
| JDK internals | Implementation | jdeps, docs | Nâng dependency hoặc thay API |
| Deep reflection | Coupling nội bộ | Source và runtime flags | Loại bỏ hoặc thay cách tích hợp |
| Preview/incubator | Chưa final | JDK docs, JEP | Chấp nhận rủi ro có chủ đích |
| Deprecated for removal | API có rủi ro loại bỏ | API docs | Lập kế hoạch thay thế |

Mức độ ưu tiên còn phụ thuộc vào độ quan trọng của luồng nghiệp vụ, số consumer, mức độ thường xuyên nâng phiên bản và khả năng rollback.

Một thư viện chỉ dùng internal class trong test có thể có tác động khác với một production service gọi internal API ở đường xử lý chính.

## 16. Kiểm thử hợp đồng từ hai phía

### 16.1. Với API consumer

Kiểm thử theo tài liệu hợp đồng:

- Giá trị đầu vào, đầu ra và boundary case.
- Null, empty, timezone, encoding, locale nếu liên quan.
- Exception được tài liệu quy định.
- Thread-safety và idempotency.
- Serialization, định dạng dữ liệu và tính tương thích consumer.
- Hành vi version mới trên runtime mục tiêu.

Không nên viết test khóa chặt chi tiết nội bộ như cấu trúc cache, exception message hoặc iteration order khi API không cam kết chúng.

### 16.2. Với SPI provider

Kiểm thử như một plugin độc lập:

1. Đóng gói provider đúng dạng classpath/module path.
2. Đăng ký ServiceLoader hoặc cơ chế framework yêu cầu.
3. Cho framework tự khám phá provider.
4. Khởi tạo và gọi các callback chính.
5. Kiểm tra exception, retry, shutdown và cleanup.
6. Kiểm tra concurrency và reentrancy nếu contract yêu cầu.
7. Kiểm tra nhiều provider cùng tồn tại.
8. Chạy với version JDK/framework đích.

Source-compatible không có nghĩa provider được nạp thành công. Một shaded JAR mất META-INF/services có thể khiến framework không tìm thấy provider dù source compile bình thường.

### 16.3. Với module boundary

Nếu dùng JPMS, hãy chạy test trên module path thực tế. Test trên classpath có thể bỏ qua vấn đề exports, opens, service binding và readability. Nếu cần mở quyền truy cập tạm thời, ghi lại flag và điều kiện loại bỏ.

## 17. Quy trình xác định và xử lý điểm phụ thuộc

### Bước 1 — Kiểm kê các hợp đồng

Tách danh sách:

- API JDK/framework mà ứng dụng gọi.
- API public mà ứng dụng công bố cho module khác.
- SPI mà ứng dụng triển khai.
- SPI mà ứng dụng công bố cho bên thứ ba.
- Implementation class và reflection đang được sử dụng.

### Bước 2 — Xác nhận nguồn hỗ trợ

Với từng điểm tích hợp, tìm documentation, annotation, module exports, release notes và compatibility policy. Nếu chưa có bằng chứng, đánh dấu **chưa xác minh**, thay vì mặc định ổn định.

### Bước 3 — Gắn rủi ro vào đường chạy thực tế

Xem sử dụng ở compile, runtime, test, plugin, annotation processor và agent. Không phải mọi import đều có ảnh hưởng giống nhau; những chỗ dùng ở đường chạy production thường cần ưu tiên hơn.

### Bước 4 — Chọn phương án

Có thể giữ API đang được hỗ trợ; nâng provider khi SPI đổi; chuyển từ concrete implementation sang facade/factory; thay thư viện đã bỏ hỗ trợ; tạo adapter bảo vệ consumer; loại bỏ reflection không cần thiết; hoặc giữ JVM flag tạm thời với hạn và owner rõ ràng.

### Bước 5 — Xác minh theo loại hợp đồng

- API: compile, binary linkage và behavior.
- SPI: discovery, callback, lifecycle và thread-safety.
- Public library: source/binary compatibility với consumer.
- Internal dependency: xác nhận đường phụ thuộc đã được gỡ bỏ.
- JPMS: module path, exports, opens và service wiring.

### Bước 6 — Ghi lại quyết định

Có thể dùng biểu mẫu:

~~~text
MODULE
  Name:
  Current JDK / target JDK:
  Framework and dependency versions:
  Runtime / packaging:

INTEGRATION SURFACE
  Package and type:
  Consumer or provider:
  API / SPI / implementation detail:
  Source or artifact location:

CONTRACT EVIDENCE
  Documentation and version:
  Module exports / opens:
  Stability annotation:
  Deprecation status:
  Vendor support policy:

MIGRATION RISK
  Source compatibility:
  Binary compatibility:
  Behavioral compatibility:
  SPI lifecycle and discovery:
  Reflection or native access:

DECISION
  Keep / replace / adapt / defer:
  Supported replacement:
  Owner and milestone:

VALIDATION
  Build:
  API compatibility test:
  SPI integration test:
  Runtime test:
  Rollback:
~~~

Một bản ghi có giá trị phải cho phép reviewer truy ngược từ dependency cụ thể đến bằng chứng hợp đồng, rủi ro và cách xác nhận sau migration.

## 18. Các hiểu lầm phổ biến

**“Public class chắc chắn là API được hỗ trợ.”** Không đúng. Public là access control. Cần xem tài liệu và support policy.

**“Package được export thì nhà cung cấp phải giữ mãi.”** Không đúng. JPMS điều khiển quyền truy cập; version policy xác định cam kết tương thích.

**“SPI chỉ là interface Java.”** Chưa đủ. Provider còn phải đáp ứng discovery, lifecycle, callback, thread-safety và quy tắc về lỗi.

**“Build thành công nghĩa là provider tương thích.”** Không đúng. Provider có thể không được load, không có constructor phù hợp, hoặc lỗi khi framework callback.

**“jdeps không báo internals thì ứng dụng an toàn.”** Chưa đủ. Reflection, dynamic loading và binary dependency có thể không được phân tích đầy đủ.

**“Thêm --add-opens là giải quyết xong.”** Cờ chỉ mở quyền truy cập trong một số trường hợp. Nó không biến implementation detail thành API được hỗ trợ.

**“Deprecated là sẽ bị xóa ngay bản kế tiếp.”** Không nhất thiết. Cần đọc trạng thái deprecation, for-removal và release notes của phiên bản cụ thể.

**“Thay API nội bộ bằng API mới luôn giữ nguyên hành vi.”** Chưa chắc. Cần kiểm tra định dạng dữ liệu, exception, concurrency và các side effect quan trọng.

## 19. Ghi nhớ khi chốt kế hoạch migration

Trước khi nâng JDK hoặc framework, hãy trả lời:

1. Thành phần này là API consumer gọi, SPI provider triển khai hay implementation detail?
2. Bằng chứng nào cho biết nhà cung cấp thực sự hỗ trợ nó?
3. Package có được export không, và nếu có, ở phạm vi nào?
4. Có annotation internal, experimental, deprecated hoặc for-removal không?
5. Có reflection, native access hoặc class name nội bộ được hard-code không?
6. Thay đổi nào có thể làm hỏng source, binary linkage, behavior hay SPI lifecycle?
7. Có API/SPI thay thế được nhà cung cấp công bố không?
8. Những test nào chứng minh consumer và provider hoạt động trên phiên bản đích?

Khi ranh giới API, SPI và implementation được nhận diện và ghi lại rõ ràng, migration không còn phụ thuộc vào phỏng đoán từ tên class hay việc compile thành công. Nhóm phát triển có thể ưu tiên loại bỏ những đường phụ thuộc không ổn định, sử dụng extension point phù hợp và bảo vệ các hợp đồng thực sự quan trọng bằng kiểm thử trên JDK và framework mục tiêu.

