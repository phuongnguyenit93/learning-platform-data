# Giữ tương thích cho bên triển khai SPI và plugin của bên thứ ba

Một nền tảng Java có thể duy trì đầy đủ API cho người gọi nhưng vẫn làm hỏng các plugin đã được khách hàng hoặc đối tác phát triển. Chỉ cần thêm một phương thức trừu tượng vào interface mở rộng, thay thời điểm gọi callback, đổi cơ chế tìm provider hoặc tăng mức Java tối thiểu là một plugin từng hoạt động tốt có thể không còn chạy được.

Trong chủ đề **Java Advance Compatibility Migration**, chương **Tiến hóa API**, việc giữ tương thích cho bên triển khai **Service Provider Interface (SPI)** và plugin của bên thứ ba là một bài toán về **hợp đồng mở rộng**, không đơn thuần là duy trì tên class và chữ ký method. Bài học trình bày cách xác định ai là bên thực thi SPI, cách tiến hóa giao diện an toàn, phân biệt tương thích nguồn và nhị phân, bảo toàn cơ chế discovery và vòng đời plugin, cùng chiến lược versioning, kiểm thử và phát hành nhằm giảm rủi ro khi nâng Java hoặc framework.

## 1. Vì sao SPI cần cách đánh giá riêng?

API và SPI đều có thể là những interface hoặc class public. Điểm khác nhau nằm ở **hướng phụ thuộc và quyền điều khiển**.

Với API thông thường:

~~~text
Ứng dụng bên ngoài
       |
       | gọi method
       v
API của nền tảng
       |
       v
Implementation của nền tảng
~~~

Với SPI:

~~~text
Nền tảng / plugin host
       |
       | khám phá, khởi tạo và callback
       v
SPI contract
       ^
       | implements / extends
       |
Plugin của bên thứ ba
~~~

Ở mô hình SPI, nhà phát triển plugin thường phải viết code phụ thuộc vào interface do nền tảng công bố. Đến runtime, chính nền tảng lựa chọn thời điểm khởi tạo và gọi implementation đó. Vì vậy một thay đổi nhỏ trong hợp đồng SPI có thể buộc **nhiều nhà cung cấp plugin độc lập** phải sửa và phát hành lại code.

Hãy phân biệt ba bên:

- **SPI owner:** nhóm duy trì interface và quy tắc mở rộng.
- **Plugin author/provider:** đối tác hoặc cộng đồng triển khai SPI.
- **Plugin host:** runtime/framework phát hiện, khởi tạo, gọi và quản lý provider.

Trong một sản phẩm, SPI owner và plugin host có thể cùng là một nhóm. Nhưng plugin author thường nằm ngoài chu kỳ phát hành của nhóm đó. Chính khoảng cách về nhịp phát hành làm khả năng tương thích ngược trở nên đặc biệt quan trọng.

### 1.1. Không phải mọi public interface đều là SPI

Một public interface mà ứng dụng chỉ nhận về để gọi method là API consumer. Một public interface mà bên thứ ba được yêu cầu triển khai có thể là SPI. Một interface trong package internal có thể không được hỗ trợ để triển khai từ bên ngoài, dù compiler cho phép.

Cần kiểm tra tài liệu chính thức: **Nền tảng có mời bên thứ ba triển khai interface hoặc subclass một class hay không?** Nếu không, không nên tự suy luận rằng mọi điểm có thể implements/extends đều được cam kết là extension point ổn định.

## 2. SPI tương thích gồm những hợp đồng nào?

Khi đánh giá một SPI, hãy tách ít nhất các lớp sau.

| Lớp hợp đồng | Điều bên triển khai cần biết | Ví dụ lỗi khi thay đổi |
|---|---|---|
| Source | Tên kiểu, method, generic, annotation, checked exception | Plugin cũ không biên dịch lại được |
| Binary | Descriptor JVM, class/interface hierarchy, visibility | NoSuchMethodError, AbstractMethodError, IncompatibleClassChangeError |
| Runtime/JDK | Class-file version, module access, dependency, bytecode API | UnsupportedClassVersionError, IllegalAccessError |
| Discovery | ServiceLoader, descriptor, module, plugin registry | Plugin tồn tại nhưng không được tìm thấy |
| Construction | Constructor, factory, dependency injection | Không tạo được provider |
| Lifecycle | init, start, invoke, stop, close, reload | Tài nguyên rò rỉ hoặc callback sai thời điểm |
| Behavior | Ý nghĩa kết quả, exception, retry, transaction | Plugin chạy nhưng cho kết quả sai |
| Concurrency | Thread-safety, reentrancy, thread context | Race condition, deadlock |
| Configuration | Property, metadata, environment, secret | Plugin không đọc được cấu hình |
| Operations | Log, metrics, lỗi, timeout, rollback | Host không cô lập được plugin lỗi |

**Giữ chữ ký method là điều cần thiết trong nhiều trường hợp, nhưng chưa đủ.** Một SPI không đổi mã nguồn vẫn có thể phá tương thích nếu host đổi thứ tự callback hoặc bắt đầu gọi provider đồng thời.

## 3. Xác định bề mặt SPI được hỗ trợ

Trước khi nâng phiên bản, cần lập danh mục extension point mà bên thứ ba thật sự sử dụng. Nguồn thông tin thường gồm:

- API/SPI reference và migration guide.
- Danh sách plugin chính thức và plugin cộng đồng.
- Module descriptor: exports, uses, provides.
- Cấu hình META-INF/services trên classpath.
- Plugin registry, manifest hoặc annotation do framework định nghĩa.
- Các class/plugin base đã được tài liệu là có thể subclass.
- Version compatibility matrix và các artifact đã công bố.
- Những extension được triển khai bởi đối tác nhưng không có source trong repository chính.

Một ví dụ phân loại:

~~~text
com.example.platform.api.Document
    -> public API: ứng dụng và provider sử dụng kiểu dữ liệu

com.example.platform.spi.DocumentImporter
    -> SPI: nhà cung cấp plugin được mời triển khai

com.example.platform.internal.ImporterDispatcher
    -> implementation detail: host dùng nội bộ

com.example.partner.csv.CsvImporter
    -> plugin của đối tác: implements DocumentImporter
~~~

Tên package là tín hiệu hữu ích nhưng không thay thế tài liệu. Một class trong package spi chưa chắc là điểm mở rộng được hỗ trợ ở mọi phiên bản; một base class trong package api có thể chỉ dành cho việc gọi, không dành cho kế thừa.

### 3.1. Tìm dependency mà plugin đang có

Cần xác định:

1. Plugin được biên dịch theo phiên bản SPI nào?
2. Plugin chạy trên JVM nào?
3. Host đang tải phiên bản SPI nào?
4. Plugin có đóng gói một bản copy của SPI hay không?
5. Plugin có sử dụng thêm implementation class nội bộ không?
6. Có dependency bắc cầu hoặc Java agent ảnh hưởng đến class loading không?

Nếu plugin đóng gói nhầm API của host vào JAR của mình, có thể xảy ra xung đột type identity: hai class trùng tên đầy đủ nhưng được nạp bởi hai classloader khác nhau không nhất thiết là cùng một kiểu đối với JVM. Cần xác định rõ dependency nào được host cung cấp và dependency nào thuộc về plugin.

## 4. Source, binary và behavioral compatibility của SPI

Ba mức tương thích này phải được đánh giá riêng.

### 4.1. Source compatibility

Một provider trước đây triển khai:

~~~java
package com.example.platform.spi;

public interface Importer {
    String id();
    String importText(byte[] source);
}
~~~

Provider cũ:

~~~java
public final class CsvImporter implements Importer {
    @Override
    public String id() {
        return "csv";
    }

    @Override
    public String importText(byte[] source) {
        return new String(source, java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Nếu SPI mới thêm một abstract method:

~~~java
public interface Importer {
    String id();
    String importText(byte[] source);

    boolean supportsStreaming();
}
~~~

thì CsvImporter phải triển khai method mới để biên dịch lại, trừ khi nó là abstract class hoặc có điều kiện kế thừa đặc biệt. Đây là một thay đổi **source-incompatible** đối với provider.

### 4.2. Binary compatibility

Khi chỉ thay JAR SPI/host mà không biên dịch lại plugin, JVM có thể nạp provider cũ. Tuy nhiên, nếu host gọi supportsStreaming trên implementation không có method tương ứng, có thể xuất hiện AbstractMethodError.

Điều đó cho thấy:

- Một thay đổi có thể cho phép class cũ được load nhưng vẫn lỗi khi callback mới được gọi.
- Không nên lấy việc plugin được khởi tạo thành công làm bằng chứng binary compatibility đầy đủ.
- Cần thực sự gọi những đường callback mà host mới sẽ sử dụng.

Một thay đổi khác như đổi method từ instance sang static, thay interface thành class, thay visibility hoặc đổi descriptor có thể gây các lỗi linkage khác.

### 4.3. Behavioral compatibility

Giả sử giao diện vẫn giữ method importText nhưng host trước đây gọi một lần cho mỗi tài liệu; phiên bản mới chia dữ liệu thành nhiều chunk và gọi method nhiều lần. Provider có thể không còn xử lý đúng, dù class, chữ ký và bytecode vẫn hợp lệ.

Tương tự, nếu host bắt đầu gọi callback từ nhiều thread, một provider giữ state mutable không đồng bộ có thể gặp race condition. Hợp đồng SPI phải chỉ rõ có hay không có guarantee về thread confinement.

Một cách đặt câu hỏi hữu ích:

> Plugin cũ có tiếp tục được khám phá, khởi tạo, nhận callback đúng ngữ nghĩa và giải phóng tài nguyên đúng cách trên host mới không?

Đây là tiêu chuẩn chặt chẽ hơn nhiều so với “biên dịch thành công”.

## 5. Tiến hóa interface SPI bằng default method

Đối với Java 8 trở lên, default method có thể cung cấp implementation mặc định cho method mới.

~~~java
package com.example.platform.spi;

public interface Importer {
    String id();
    String importText(byte[] source);

    default int priority() {
        return 0;
    }
}
~~~

Provider cũ không phải bổ sung priority khi biên dịch lại. Với provider đã biên dịch theo SPI cũ, host mới có thể gọi default implementation trong nhiều trường hợp tương thích thông thường.

### 5.1. Khi nào default method là lựa chọn hợp lý?

- Có thể xác định hành vi mặc định chính xác và an toàn.
- Provider cũ thực sự có thể tiếp tục hoạt động nếu không biết capability mới.
- Method mới không buộc plugin phải quản lý state hoặc lifecycle mới.
- Giá trị mặc định không tạo ra thay đổi không mong muốn đối với selection order hoặc bảo mật.
- Không có xung đột kế thừa method đáng kể.

Trong ví dụ priority, mặc định 0 giúp giữ nhóm provider cũ ở mức ưu tiên cơ sở. Nhưng nếu host dùng priority để chọn một plugin duy nhất, cần thiết kế tie-breaking ổn định. Không được giả định thứ tự enumeration của ServiceLoader là hợp đồng lựa chọn khi tài liệu chưa cam kết.

### 5.2. Default method không tự động bảo đảm tương thích

Có những rủi ro:

- Một implementation đã có method cùng tên nhưng ý nghĩa khác.
- Nhiều interface cha cùng cung cấp default method xung đột.
- Giá trị mặc định làm thay đổi behavior không đúng với plugin cũ.
- Host mới dựa vào chức năng mà default implementation không thể thực hiện chính xác.
- Method mới làm rò rỉ kiểu không có trên baseline JDK cũ.

Không nên thêm default method chỉ để làm lỗi compile biến mất nếu hợp đồng thực tế đòi hỏi mọi provider phải cung cấp implementation có ý nghĩa.

### 5.3. Capability có thể được kiểm tra bằng opt-in

Một SPI cũ có thể giữ nguyên, còn chức năng mới được đưa vào interface phụ:

~~~java
public interface Importer {
    String id();
    String importText(byte[] source);
}

public interface StreamingImporter extends Importer {
    void start();
    void accept(byte[] chunk);
    String finish();
}
~~~

Host kiểm tra capability:

~~~java
if (importer instanceof StreamingImporter) {
    StreamingImporter streaming = (StreamingImporter) importer;
    streaming.start();
    // Gọi accept(...) cho từng chunk theo contract
    String result = streaming.finish();
} else {
    // Giữ luồng importText(...) của provider cũ
}
~~~

Cách này tránh ép mọi provider cũ phải triển khai streaming. Đổi lại, host cần quản lý hai đường thực thi và quy tắc fallback rõ ràng.

## 6. Dùng versioned SPI thay vì phá hợp đồng cũ

Khi một tính năng yêu cầu thay đổi semantics hoặc lifecycle lớn, nên cân nhắc tạo SPI mới thay vì sửa mạnh một interface đang được nhiều plugin triển khai.

Ví dụ:

~~~java
public interface ExporterV1 {
    byte[] export(Document document);
}

public interface ExporterV2 {
    void begin(ExportContext context);
    void write(DocumentChunk chunk);
    void end();
}
~~~

Host có thể duy trì adapter từ V1 sang V2:

~~~java
public final class LegacyExporterAdapter {
    private final ExporterV1 legacy;

    public LegacyExporterAdapter(ExporterV1 legacy) {
        this.legacy = legacy;
    }

    public byte[] export(Document document) {
        return legacy.export(document);
    }
}
~~~

Adapter ở trên minh họa việc giữ đường gọi V1; để hỗ trợ V2 đầy đủ, cần thiết kế cách tổng hợp chunk, quản lý buffering và lifecycle phù hợp. Không phải mọi thay đổi streaming đều có thể chuyển đổi an toàn từ một API trả về byte array.

### 6.1. Chiến lược song song

Trong một giai đoạn chuyển tiếp:

1. Host vẫn đăng ký và nạp provider V1.
2. Host cũng khám phá provider V2.
3. Hai provider type có registry hoặc service descriptor riêng.
4. Log/metrics cho biết plugin nào còn chạy V1.
5. Documentation nêu mốc ngừng nhận V1 trong tương lai.
6. Chỉ loại bỏ V1 ở một release được thông báo trước, theo support policy.

Điều quan trọng là host phải thật sự chạy test với plugin V1 đã phát hành, không chỉ với source V1 được biên dịch lại bằng thư viện mới.

### 6.2. Semantic versioning là tín hiệu, không phải phép bảo đảm

Một chính sách có thể quy định:

- Patch: sửa lỗi không làm thay đổi contract đã công bố.
- Minor: bổ sung API/SPI theo cách tương thích ngược.
- Major: có thể thay đổi hợp đồng không tương thích.

Tuy nhiên, cách dùng version thực tế khác nhau giữa nhà cung cấp. Không thể suy luận plugin chắc chắn tương thích chỉ vì version tăng một số nhỏ. Cần đọc tài liệu chính sách và thực hiện kiểm thử compatibility.

## 7. Giữ nguyên đường tìm provider: ServiceLoader

Java ServiceLoader là cơ chế tiêu biểu để host tìm implementation của một service type.

Giả sử API đã được công bố:

~~~java
package com.example.codec.spi;

public interface TextCodec {
    String id();
    byte[] encode(String text);
    String decode(byte[] data);
}
~~~

Một plugin:

~~~java
package com.example.codec.utf8;

import com.example.codec.spi.TextCodec;
import java.nio.charset.StandardCharsets;

public final class Utf8Codec implements TextCodec {
    public Utf8Codec() {
    }

    @Override
    public String id() {
        return "utf8";
    }

    @Override
    public byte[] encode(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    public String decode(byte[] data) {
        return new String(data, StandardCharsets.UTF_8);
    }
}
~~~

Host:

~~~java
import com.example.codec.spi.TextCodec;
import java.util.ServiceLoader;

ServiceLoader<TextCodec> providers = ServiceLoader.load(TextCodec.class);

for (TextCodec codec : providers) {
    System.out.println(codec.id());
}
~~~

Đây là ví dụ mã nguồn ở cấp ứng dụng; khi triển khai thực tế cần cấu trúc package, module và đường nạp class nhất quán.

### 7.1. Đăng ký qua classpath

Với JAR truyền thống, plugin khai báo resource:

~~~text
META-INF/services/com.example.codec.spi.TextCodec
~~~

Nội dung:

~~~text
com.example.codec.utf8.Utf8Codec
~~~

Tên file phải là tên đầy đủ của service type. Nội dung phải là tên provider theo cơ chế registration của classpath. Một lỗi chính tả hoặc resource bị mất trong packaging đủ khiến provider không được khám phá.

Khi dùng shading hoặc fat JAR, nhiều dependency có thể chứa cùng đường META-INF/services. Build cần hợp nhất descriptor theo quy định của công cụ đóng gói thay vì chỉ giữ một file.

### 7.2. Đăng ký qua module path

Service type được đặt trong một module API:

~~~java
module com.example.codec.api {
    exports com.example.codec.spi;
}
~~~

Provider module:

~~~java
module com.example.codec.utf8 {
    requires com.example.codec.api;
    provides com.example.codec.spi.TextCodec
        with com.example.codec.utf8.Utf8Codec;
}
~~~

Host module:

~~~java
module com.example.codec.host {
    requires com.example.codec.api;
    uses com.example.codec.spi.TextCodec;
}
~~~

Những khai báo này cho phép module system biết mối quan hệ service. Provider implementation không nhất thiết phải export package riêng để host gọi trực tiếp. Nền tảng có cơ chế tạo provider từ khai báo provides phù hợp.

Khi chuyển từ classpath sang module path, cần kiểm tra riêng:

- Module được resolve vào layer đang dùng hay chưa.
- Host có khai báo uses phù hợp không.
- Provider có khai báo provides chính xác không.
- Constructor/factory phù hợp với quy tắc ServiceLoader trong mô hình triển khai không.
- Package nào được export và package nào chỉ cần reflective access.
- Host dùng đúng classloader hoặc ModuleLayer để tìm provider không.

### 7.3. Những thay đổi discovery có thể phá plugin

Một số thay đổi có rủi ro:

- Đổi tên package hoặc tên đầy đủ của service interface.
- Đổi cơ chế registration mà không hỗ trợ đường cũ.
- Thay classloader dùng để tìm provider.
- Chuyển sang module path nhưng không migrate service descriptor hoặc provides.
- Thay cơ chế lọc hoặc selection provider.
- Đổi requirement về constructor, factory hoặc metadata.
- Không hợp nhất resource khi đóng gói lại.
- Ngầm yêu cầu plugin ký số hoặc cấu hình mới mà không có lộ trình.

Nếu cần đổi discovery, host nên hỗ trợ song song cơ chế cũ trong thời gian chuyển tiếp, hoặc phát hành adapter/upgrade tooling cùng hướng dẫn rõ ràng.

## 8. Classloader isolation và type identity

Nhiều hệ thống plugin dùng classloader riêng để cô lập dependency của từng plugin. Đây là điểm dễ phát sinh lỗi trong Java migration.

~~~text
Bootstrap / Platform classes
             |
             v
      Host classloader
      - SPI interface
      - Host API
             |
       +-----+------+
       |            |
       v            v
Plugin A loader  Plugin B loader
- A classes      - B classes
- A libraries    - B libraries
~~~

Nếu mỗi plugin đóng gói một bản copy của service interface thay vì dùng cùng interface do host nạp, có thể xảy ra tình trạng:

~~~text
com.example.spi.Importer loaded by HostLoader
!=
com.example.spi.Importer loaded by PluginLoader
~~~

Hai class trùng tên nhưng được nạp bởi các classloader khác nhau có thể không tương thích kiểu. Kết quả có thể là ClassCastException, ServiceConfigurationError hoặc lỗi khi host kiểm tra instanceof.

### 8.1. Quy tắc phân chia dependency

Thường nên xác định rõ:

- **Host-provided:** SPI API, các kiểu contract được chia sẻ.
- **Plugin-private:** dependency riêng, implementation và tài nguyên của plugin.
- **Shared approved libraries:** chỉ những thư viện được công bố là dùng chung.
- **Forbidden bundled libraries:** những class không được phép đóng gói trùng với host API.

Với Maven có thể dùng scope provided cho phần host cung cấp trong trường hợp phù hợp. Với Gradle có thể dùng compileOnly, nhưng packaging thực tế vẫn phải được kiểm tra. Hai cấu hình này chỉ giúp biểu diễn dependency khi build, không tự chứng minh plugin classloader được bố trí đúng.

### 8.2. Cẩn trọng với context classloader

Một số framework và ServiceLoader sử dụng thread context classloader tùy lời gọi API và cơ chế khởi tạo. Nếu plugin system đổi thread hoặc classloader, provider discovery có thể thay đổi.

Khi nâng host/JDK, cần xác nhận:

- Classloader nào nạp SPI.
- Classloader nào nạp provider.
- Có dùng thread context classloader không.
- Task async có giữ đúng context cần thiết không.
- Provider có được unload/reload theo lifecycle không.
- Có cache static hoặc thread-local giữ classloader cũ gây memory leak không.

Không nên coi thành công trên một classloader phẳng ở local là bằng chứng plugin system với isolation hoạt động trong production.

## 9. Giữ baseline Java và artifact compatibility cho plugin

Plugin được triển khai ngoài tổ chức có thể được build ở các JDK khác nhau. Host nâng JDK không có nghĩa mọi plugin cần được biên dịch lại ngay, nhưng phải duy trì khả năng load class file và API mà plugin sử dụng.

### 9.1. Phân biệt các phiên bản

Với plugin, cần ghi nhận:

| Thành phần | Câu hỏi |
|---|---|
| Build JDK | Plugin author dùng JDK nào để chạy Maven/Gradle? |
| Compiler/toolchain | javac thực tế đến từ JDK nào? |
| Release target | Bytecode và Java platform API tối thiểu là phiên bản nào? |
| Plugin SPI version | Plugin biên dịch với hợp đồng SPI nào? |
| Host runtime | Plugin thực sự chạy trên JVM nào? |
| Host-supported versions | Host cam kết nhận những phiên bản SPI nào? |

Ví dụ một plugin build bằng JDK 21 nhưng dùng release target Java 17 có thể tương thích với runtime Java 17 khi tất cả dependency và API cũng tương thích. Plugin được build cho Java 21 sẽ không chạy trên JVM Java 17 chỉ bằng cách thay version của host SPI.

### 9.2. Major class-file version

Một số mốc thường dùng:

| Java | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Nếu class-file version của plugin cao hơn runtime hỗ trợ, host có thể gặp UnsupportedClassVersionError.

Có thể xem class file cụ thể:

~~~bash
javap -verbose -classpath plugin.jar com.example.plugin.MyProvider
~~~

Nhưng kiểm tra một class chưa đủ: plugin có thể chứa nhiều JAR, generated classes hoặc Multi-Release JAR. Cũng cần kiểm tra API baseline, native dependency và thư viện bên thứ ba.

### 9.3. Cấu hình compile release

Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Cấu hình trên minh họa việc dùng compiler mới hơn nhưng vẫn tạo artifact theo Java 17. Trong hệ thống thật cần kiểm tra version Gradle/Maven, plugin, annotation processor và dependency có đáp ứng release target không.

Nếu host hỗ trợ plugin ở nhiều JDK, phải chạy test matrix trên đúng những runtime đã công bố, không chỉ compile với --release.

## 10. Thay đổi lifecycle: rủi ro thường lớn hơn thay chữ ký

Một SPI có thể giữ nguyên mọi method nhưng đổi thời điểm hoặc cách gọi.

Ví dụ:

~~~java
public interface Plugin {
    void initialize(PluginContext context);
    void start();
    void stop();
}
~~~

Hợp đồng cần mô tả trình tự:

~~~text
DISCOVERED
     |
     v
CONSTRUCTED
     |
     v
INITIALIZED
     |
     v
STARTED -----> CALLBACKS
     |              |
     |              v
     |           STOPPING
     v              |
STOPPED <------------+
     |
     v
RELEASED
~~~

Đây là sơ đồ minh họa. Hệ thống thật phải xác định các transition hợp lệ, cách xử lý failure và trạng thái khi restart.

Các câu hỏi quan trọng:

- initialize có được gọi chính xác một lần không?
- Callback có thể xảy ra trước start không?
- stop có thể được gọi sau khi initialize thất bại không?
- start/stop có idempotent không?
- Có thể tạo lại một plugin instance sau khi stop không?
- Host có thể chạy đồng thời nhiều instance không?
- Context được phép dùng sau stop không?
- Shutdown có deadline hay timeout không?

Nếu host mới bắt đầu gọi callback đồng thời, plugin cũ không thread-safe có thể hỏng. Nếu host đổi từ một instance toàn hệ thống sang một instance mỗi request, việc quản lý cache hoặc connection pool cũng có thể thay đổi.

### 10.1. Không thay đổi exception handling một cách âm thầm

SPI nên quy định callback có thể ném exception gì và host phản ứng thế nào:

- Bỏ qua plugin và tiếp tục?
- Vô hiệu hóa plugin trong phiên chạy?
- Retry?
- Rollback transaction?
- Fail-fast toàn bộ ứng dụng?
- Ghi log và trả lỗi cho consumer?

Ví dụ, host trước đây bắt exception và bỏ qua provider lỗi; phiên bản mới fail toàn bộ request có thể làm plugin cũ gây gián đoạn hệ thống lớn hơn. Mọi thay đổi failure policy cần được tài liệu hóa và kiểm thử.

### 10.2. Thread-safety và reentrancy

Cần ghi rõ:

- Một provider có thể bị gọi trên nhiều thread cùng lúc không?
- Một callback có thể gọi lại host API và dẫn đến callback lồng nhau không?
- Có thread-affinity, transaction context hoặc security context không?
- Host có giữ lock khi gọi plugin không?
- Plugin có được phép block hoặc thực hiện I/O không?

Khi dùng virtual threads hoặc đổi executor, không nên suy luận rằng contract threading vẫn như cũ. Đặc biệt cần xem các plugin sử dụng ThreadLocal, synchronized block, callback order hoặc thư viện phụ thuộc vào thread identity.

## 11. Hợp đồng dữ liệu, lỗi và hành vi của plugin

SPI thường truyền những kiểu dữ liệu do host định nghĩa. Khi các kiểu này tiến hóa, plugin có thể bị ảnh hưởng dù service interface không thay đổi.

### 11.1. DTO và dữ liệu đầu vào

Ví dụ:

~~~java
public interface PaymentPlugin {
    Decision evaluate(PaymentContext context);
}
~~~

Nếu PaymentContext bắt đầu trả null ở trường mà trước đây luôn khác null, plugin có thể lỗi NullPointerException. Nếu Decision được thêm một enum constant mới, code dùng switch statement không có default có thể không xử lý đầy đủ.

Cần tài liệu hóa:

- Nullability.
- Tính bất biến/mutable của DTO.
- Ownership và thời gian sống của dữ liệu.
- Định dạng thời gian và timezone.
- Encoding.
- Enum extensibility.
- Version của schema/serialization.
- Mức độ tương thích của error code.

### 11.2. Kiểm soát hành vi mặc định

Khi thêm một capability mới, cách xử lý an toàn thường là:

- Capability mới ở trạng thái opt-in.
- Provider cũ đi theo đường xử lý cũ.
- Host có thể phát hiện provider chưa hỗ trợ.
- Fallback không vi phạm bảo mật hoặc tính đúng đắn.
- Có log/metrics để biết tỷ lệ provider dùng đường cũ.

Không nên mặc định cho phép một provider cũ làm thao tác mới nếu chưa có hợp đồng bảo đảm. Trong nghiệp vụ bảo mật hoặc thanh toán, fallback sai có thể nguy hiểm hơn lỗi hiển thị rõ ràng.

### 11.3. Contract test quan trọng hơn kiểm tra class có tồn tại

Một test SPI nên mô phỏng đúng input mà host mới sẽ gửi, kỳ vọng về output, exception, timeout, transaction và cleanup. Plugin cần được kiểm thử như một artifact độc lập đã phát hành, thay vì luôn được biên dịch cùng host mới.

## 12. Version negotiation và capability discovery

Một số nền tảng plugin cần khai báo version hoặc capability rõ ràng để quyết định có nạp plugin hay không.

Ví dụ metadata minh họa:

~~~text
plugin.id=com.example.csv-importer
plugin.version=2.4.1
spi.min=1
spi.max=2
requires.java=17
capabilities=batch-import,csv
~~~

Đây là format minh họa do host tự định nghĩa, **không phải chuẩn metadata có sẵn của Java ServiceLoader**.

Host có thể dùng metadata để:

1. Từ chối plugin không hỗ trợ SPI mà host yêu cầu.
2. Chọn adapter V1/V2.
3. Chặn plugin cần Java runtime cao hơn.
4. Kiểm tra quyền/capability trước khi chạy.
5. Hiển thị lỗi tương thích rõ ràng cho operator.
6. Ghi metrics theo version và capability.

### 12.1. Tương thích theo khoảng phiên bản

Cần tránh chỉ so sánh chuỗi version bằng toán tử từ điển. Hãy dùng quy tắc version hợp lệ của hệ thống và khai báo rõ major/minor/patch hoặc schema version.

Ví dụ bảng hỗ trợ:

| Host version | SPI được hỗ trợ | Plugin đã được kiểm thử |
|---|---|---|
| Host 3 | SPI 1, SPI 2 | Provider V1 và V2 |
| Host 4 | SPI 2 | Provider V2 |
| Host 5 | SPI 2, SPI 3 | Provider V2 và V3 |

Bảng trên chỉ là thiết kế minh họa. Trong hệ thống thật phải công bố chính sách tương thích, mốc deprecation và những tổ hợp đã được kiểm chứng.

Một plugin tự tuyên bố hỗ trợ version không đủ bảo đảm hoạt động; host vẫn cần test tính năng và kiểm tra dependency/classloader.

## 13. Quy trình thay đổi SPI có kiểm soát

Một lần nâng SPI nên được xem như một change-management process.

### Bước 1 — Lập danh mục plugin hiện hữu

Ghi nhận:

- Plugin do công ty phát triển.
- Plugin bên thứ ba, mã nguồn mở hoặc đối tác.
- Plugin khách hàng tự xây dựng.
- Phiên bản plugin và SPI đang được sử dụng.
- Phiên bản Java/OS được hỗ trợ.
- Plugin có source hay chỉ có binary artifact.
- Chủ sở hữu và khả năng cập nhật plugin.

Đừng cho rằng mọi plugin đều nằm trong cùng một repository hoặc được build lại cùng host.

### Bước 2 — Viết ra hợp đồng hiện tại

Tài liệu hóa service type, method, constructor/factory, discovery, lifecycle, error semantics, threading, security và configuration. Phân biệt phần đã cam kết với implementation detail chưa được công bố.

### Bước 3 — Phân loại thay đổi dự kiến

| Dạng thay đổi | Rủi ro | Cách tiếp cận |
|---|---|---|
| Thêm optional capability | Thường có thể làm tương thích | Default method hoặc interface mở rộng |
| Thêm abstract method | Provider cũ có thể lỗi compile/callback | Cân nhắc default, adapter hoặc SPI V2 |
| Xóa/đổi tên method | Source/binary break | Giữ bridge hoặc phiên bản hóa |
| Đổi parameter/return type | Binary descriptor có thể đổi | API/SPI mới hoặc adapter |
| Đổi callback timing | Behavioral break | Giữ behavior cũ hoặc opt-in |
| Đổi discovery | Plugin không được tìm thấy | Hỗ trợ song song registration cũ |
| Nâng Java baseline | Plugin hoặc host không chạy trên runtime cũ | Công bố matrix và kiểm thử |
| Đổi classloader | Type identity và resource visibility | Xác minh đóng gói host/plugin |
| Thêm yêu cầu bảo mật | Provider có thể mất quyền | Capability negotiation và thông báo chuyển đổi |

Không nên áp dụng một chiến thuật cho mọi thay đổi. Cần đánh giá liệu có thể giữ fallback đúng và an toàn hay phải công bố breaking release.

### Bước 4 — Chọn cách triển khai

Các lựa chọn phổ biến:

- Giữ nguyên SPI cũ, thêm interface mới.
- Thêm default method với semantics được tài liệu hóa.
- Tạo adapter để host mới hỗ trợ provider cũ.
- Duy trì hai service registry trong giai đoạn chuyển tiếp.
- Thêm capability/version metadata.
- Phát hành SDK hoặc test kit cho plugin author.
- Thay đổi major version và công bố migration guide khi không thể giữ tương thích.

### Bước 5 — Cập nhật tài liệu và ví dụ

Documentation nên bao gồm:

- SPI được hỗ trợ theo host version.
- Java runtime tối thiểu.
- Cách compile plugin và cách khai báo dependency.
- Cách đăng ký provider.
- Threading/lifecycle/error contract.
- Chức năng optional và cách khai báo capability.
- Những điểm sẽ deprecated và thời điểm loại bỏ.
- Ví dụ migrate một plugin thật từ V1 sang V2.
- Cách kiểm tra tương thích trước khi phát hành.

### Bước 6 — Giữ một cửa sổ tương thích

Nếu sản phẩm cần hỗ trợ plugin bên thứ ba, nên có giai đoạn host chấp nhận cả provider cũ và mới khi khả thi. Khi sắp loại bỏ V1, cần cảnh báo sớm, log deprecation và cung cấp đường nâng rõ ràng.

## 14. Kiểm thử tương thích SPI bằng artifact cũ

Một sai lầm phổ biến là chỉ checkout source plugin cũ rồi compile bằng SPI mới. Cách đó giúp phát hiện source compatibility nhưng có thể che mất binary compatibility và packaging thực tế.

Nên lưu một **corpus plugin fixture**:

~~~text
fixtures/
  plugin-v1-built-with-java-17.jar
  plugin-v1-with-service-descriptor.jar
  plugin-v2-modular.jar
  plugin-with-private-dependencies.jar
  plugin-using-context-classloader.jar
  plugin-with-lifecycle-state.jar
~~~

Tên file chỉ minh họa. Fixture thực tế nên là artifact được kiểm chứng, lưu kèm version SDK, checksum và cách build.

### 14.1. Tạo compatibility test matrix

Ví dụ:

| Host | Provider artifact | Runtime | Kiểm thử |
|---|---|---|---|
| Host mới | Plugin V1 đã build từ trước | JDK đích | Load, callback và shutdown |
| Host mới | Plugin V1 biên dịch lại | JDK đích | Source compatibility |
| Host mới | Plugin V2 | JDK đích | Capability mới |
| Host cũ | Plugin V2 nếu được cam kết | JDK cũ được hỗ trợ | Backward compatibility |
| Host mới | Plugin từ classloader riêng | JDK đích | Type identity, isolation |
| Host mới | Plugin modular | Module path | uses/provides và access |

Phải phân biệt **host mới chạy plugin cũ** (backward compatibility) với **host cũ chạy plugin mới** (forward compatibility). Nhiều sản phẩm chỉ cam kết chiều đầu.

### 14.2. Test nào cần chạy?

- **Discovery:** ServiceLoader hoặc registry tìm đúng provider.
- **Instantiation:** Constructor/factory được gọi đúng.
- **Type contract:** Interface được nạp từ đúng classloader.
- **Callbacks:** Mọi callback mà host sử dụng đều được chạy.
- **Semantics:** Kết quả và lỗi đúng theo hợp đồng.
- **Lifecycle:** initialize, start, stop, cleanup và failure path.
- **Concurrency:** Những tình huống đa thread nếu hợp đồng cho phép.
- **Dependencies:** Không có missing class, version conflict hay incompatible bytecode.
- **JPMS:** exports, opens, uses, provides trên module path thực tế.
- **Operations:** Log, metrics, isolation, timeout, rollback.

Test cần bao gồm đường lỗi, không chỉ happy path. Một provider có thể hoạt động khi xử lý tài liệu hợp lệ nhưng rò rỉ thread hoặc connection khi exception xảy ra.

### 14.3. Bộ test kit cho nhà phát triển plugin

Nền tảng có thể cung cấp một Plugin Compatibility Test Kit để đối tác chạy trước khi phát hành:

~~~text
plugin-test-kit
  -> verify metadata
  -> load provider
  -> validate service discovery
  -> execute contract cases
  -> exercise lifecycle
  -> inspect runtime dependencies
  -> report supported host/SPI versions
~~~

Test kit nên cung cấp thông báo lỗi có ý nghĩa và ghi rõ phiên bản test kit, host và JVM. Một plugin vượt qua test kit vẫn cần integration test theo use case thật, nhưng nó giảm chi phí phát hiện sớm những lỗi hợp đồng phổ biến.

## 15. Kiểm tra API/binary compatibility bằng công cụ

Những công cụ sau hỗ trợ điều tra. Chúng không tự thay thế kiểm thử hành vi SPI.

### 15.1. javap

Xem bề mặt public của interface trong artifact:

~~~bash
javap -public -classpath spi-api.jar com.example.platform.spi.Importer
~~~

Xem thêm descriptor và metadata:

~~~bash
javap -verbose -classpath spi-api.jar com.example.platform.spi.Importer
~~~

Giúp phát hiện method signature và class-file version của artifact thực tế.

### 15.2. jdeps

Kiểm tra phụ thuộc và usage JDK internal APIs:

~~~bash
jdeps --jdk-internals plugin.jar
~~~

Với các dependency liên quan, bổ sung classpath/ module path cho phù hợp. jdeps phân tích tĩnh, có thể không thấy reflection, dynamic loading và mọi plugin được nạp runtime.

### 15.3. API diff

Revapi hoặc japicmp có thể so sánh các bản spi-api.jar để tìm thay đổi:

- Class/interface bị xóa.
- Method bị xóa hoặc đổi descriptor.
- Access modifier.
- Supertype/interface.
- Annotation và một số metadata.
- Những thay đổi có nguy cơ source/binary incompatibility.

Tuy nhiên, một API diff “không có breaking change” không chứng minh lifecycle hay behavioral compatibility. Mọi thay đổi SPI phải được kiểm chứng bằng provider thực tế.

### 15.4. Build dependency graph

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Chú ý version của spi-api thực sự được resolve, dependency do host cung cấp, dependency do plugin đóng gói và các artifact của provider.

## 16. Plugin lỗi: cô lập và khả năng rollback

Khi host bắt đầu nạp plugin không tương thích, cần có hành vi vận hành rõ ràng:

- Không che giấu lỗi linkage bằng cách bắt mọi Throwable rồi tiếp tục tùy tiện.
- Ghi log plugin ID, version, SPI version và nguyên nhân.
- Không làm lộ secret hoặc dữ liệu người dùng trong diagnostic.
- Cho phép disable plugin nếu chức năng không bắt buộc.
- Có health status hoặc alert khi provider không được nạp.
- Không để một plugin lỗi khiến toàn bộ host không hoạt động nếu kiến trúc có thể cô lập an toàn.
- Có phương án quay lại host/runtime/plugin artifact trước đó.

Quyết định fail-fast hay skip plugin cần phụ thuộc tính chất nghiệp vụ. Plugin bảo mật bắt buộc có thể cần chặn khởi động nếu thiếu; plugin xuất báo cáo tùy chọn có thể bị tạm vô hiệu hóa với thông báo rõ ràng. Không nên silently skip provider thuộc đường xử lý quan trọng.

### 16.1. Rollback không chỉ là quay lại JAR

Nếu SPI mới làm thay đổi định dạng dữ liệu, schema hoặc cấu hình plugin, host cũ có thể không đọc được trạng thái đã ghi. Kế hoạch rollback cần xét:

- Phiên bản database/schema.
- Metadata plugin.
- Cache hoặc serialized state.
- Các message đã gửi.
- Job đang xử lý dang dở.
- Tài nguyên native hoặc external service.
- Service registry và classloader state.

Trong nhiều trường hợp, rollback cần đảm bảo format tương thích hai chiều hoặc có kế hoạch khôi phục dữ liệu, không chỉ đổi image container.

## 17. Hướng dẫn phát hành dành cho nhà cung cấp SPI

Một dự án nền tảng nên đặt ra quy tắc cụ thể để giảm breaking changes ngoài ý muốn.

**Thiết kế SPI tối thiểu:** Chỉ công bố những callback thật sự cần. Tránh buộc provider kế thừa base class nội bộ hoặc truy cập private state của host.

**Ưu tiên composition:** Dùng interface nhỏ, DTO được tài liệu hóa và capability opt-in thay vì một interface khổng lồ liên tục thêm method.

**Tài liệu hóa chiều phụ thuộc:** Ghi rõ host cung cấp artifact nào, plugin phải đóng gói artifact nào và version range được hỗ trợ.

**Không lạm dụng default method:** Chỉ thêm khi fallback đủ đúng, an toàn và kiểm thử được.

**Quản lý lifecycle rõ ràng:** Đặc tả thời điểm gọi, concurrency, deadline, lỗi, shutdown và cách tái sử dụng instance.

**Công bố roadmap:** Deprecate, duy trì adapter, cảnh báo và chỉ loại bỏ ở mốc phù hợp chính sách hỗ trợ.

**Tự động kiểm thử ngược:** CI chạy plugin fixture đã biên dịch từ các SPI cũ mà sản phẩm cam kết hỗ trợ.

**Theo dõi plugin thực tế:** Có thể thống kê version/capability được sử dụng nếu phù hợp quyền riêng tư và chính sách tổ chức, để biết khi nào có thể ngừng đường legacy.

## 18. Ví dụ lộ trình nâng SPI V1 lên V2

Giả sử nền tảng có plugin nhập dữ liệu từ file. SPI V1 cung cấp:

~~~java
public interface FileImporter {
    String format();
    Object importFile(byte[] content);
}
~~~

Nhu cầu mới là xử lý dữ liệu lớn theo luồng, có hủy và tiến trình.

Một kế hoạch không gây breaking change ngay có thể là:

### Giai đoạn A — Giữ V1

Host vẫn nhận plugin V1. Tài liệu chỉ ra những giới hạn về bộ nhớ và kích thước file, không thay đổi method hiện có.

### Giai đoạn B — Đưa V2 vào

Bổ sung StreamingFileImporter với callback và lifecycle được công bố. Host kiểm tra plugin có triển khai V2 hay không và chạy đường mới khi phù hợp.

~~~java
public interface StreamingFileImporter {
    String format();
    void begin(ImportContext context);
    void accept(byte[] chunk);
    Object finish();
    void cancel();
}
~~~

ImportContext là kiểu contract của nền tảng. Trong hệ thống thật phải định nghĩa rõ ownership, threading, exception, backpressure và cleanup.

### Giai đoạn C — Hỗ trợ cả hai

- V1 tiếp tục nhận byte[] như trước.
- V2 được gọi theo cơ chế streaming.
- Host ghi log và metrics xác định version plugin.
- Test kit kiểm thử song song provider V1/V2.
- Host đưa cảnh báo nếu V1 xử lý file vượt giới hạn tài nguyên.

### Giai đoạn D — Công bố mốc loại bỏ V1

Khi chính sách cho phép loại bỏ V1, phát hành migration guide, ví dụ source và tool kiểm tra. Chỉ chuyển sang phiên bản host không hỗ trợ V1 sau khi đã thông báo, đánh giá hệ sinh thái và chấp nhận kế hoạch hỗ trợ.

Một số hệ thống có thể giữ V1 lâu dài nếu chi phí adapter thấp. Không nhất thiết phải loại bỏ mọi SPI cũ chỉ vì có SPI mới.

## 19. Mẫu hồ sơ tương thích cho plugin

Dùng bản ghi sau khi chuẩn bị migration:

~~~text
HOST
  Host name/version:
  Current JDK:
  Target JDK:
  Runtime classpath or module path:
  Plugin loader model:

SPI CONTRACT
  Service interface:
  Current SPI version:
  Target SPI version:
  Public DTOs:
  Discovery mechanism:
  Construction contract:
  Lifecycle callbacks:
  Concurrency contract:
  Error and timeout policy:

PLUGIN INVENTORY
  Plugin ID:
  Vendor/owner:
  Plugin version:
  Build release:
  SPI version compiled against:
  Bundled/shared dependencies:
  Source available?:
  Deployment criticality:

CHANGE ASSESSMENT
  Added/removed/changed methods:
  Default methods:
  DTO/schema changes:
  Capability flags:
  JPMS and classloader changes:
  Behavioral differences:
  Support/deprecation policy:

VALIDATION
  Old plugin binary on new host:
  Recompile old plugin:
  Service discovery:
  Callback/lifecycle tests:
  Concurrency/error tests:
  Runtime integration:
  Packaging and shading:
  Rollback test:

DECISION
  Compatible / requires adapter / breaking:
  Workaround and expiry:
  Required partner action:
  Owner:
  Release milestone:
~~~

Bản ghi tốt phải chỉ ra được **phiên bản plugin nào đã được thử trên host nào**, không chỉ ghi chung “plugin supported”.

## 20. Những hiểu lầm thường gặp

### “Interface vẫn còn nên plugin chắc chắn chạy được”

Không đúng. Host có thể gọi method mới, đổi lifecycle hoặc không còn khám phá provider theo registration cũ.

### “Chỉ cần compile lại plugin là đủ”

Không đủ. Cần test plugin binary cũ để xác minh backward compatibility; compile lại có thể che lỗi tương thích với artifact đã phát hành.

### “Default method giải quyết mọi thay đổi”

Không đúng. Nó chỉ phù hợp khi fallback có semantics đúng. Với tính năng bắt buộc, cách an toàn hơn có thể là SPI mới hoặc capability opt-in.

### “ServiceLoader sẽ tự tìm tất cả plugin”

Không phải lúc nào. Discovery phụ thuộc classpath/module path, service descriptor, uses/provides, classloader hoặc ModuleLayer. Packaging sai có thể làm provider biến mất.

### “Plugin dùng cùng tên class là cùng một type”

Sai trong hệ thống có nhiều classloader. Type identity của JVM còn phụ thuộc classloader định nghĩa class.

### “Chỉ cần giữ cùng Java source level”

Không đủ. Plugin còn có dependency, bytecode release, API Java sử dụng, module access, agent và runtime behavior.

### “Có thể loại bỏ SPI cũ trong minor release mà không ảnh hưởng ai”

Không nên giả định như vậy. Mức cam kết phiên bản phải dựa trên chính sách đã công bố và danh mục plugin hiện hữu, không chỉ trên số version.

### “Plugin lỗi thì bỏ qua để host tiếp tục”

Tùy nghiệp vụ. Với plugin bắt buộc cho bảo mật hoặc thanh toán, bỏ qua có thể nguy hiểm hơn fail-fast. Phải có failure policy rõ ràng.

## 21. Tổng kết

Giữ tương thích cho bên triển khai SPI và plugin của bên thứ ba đòi hỏi tư duy theo **hợp đồng hai chiều**. Nhà cung cấp nền tảng phải giữ ổn định những gì đã công bố để plugin triển khai; plugin author phải tuân theo quy tắc callback, discovery, lifecycle và runtime mà host hỗ trợ.

Một chiến lược bền vững gồm những nguyên tắc:

1. **Xác định đúng SPI:** phân biệt API người dùng gọi, extension point người ngoài triển khai và implementation detail.
2. **Không chỉ kiểm tra compile:** đánh giá source, binary, behavioral, lifecycle, discovery, JPMS và classloader compatibility.
3. **Tiến hóa có lối chuyển tiếp:** ưu tiên default method hợp lý, interface mở rộng, adapter hoặc versioned SPI khi cần.
4. **Bảo vệ plugin đã phát hành:** chạy fixture binary cũ trên host/JDK mới, không chỉ compile lại source.
5. **Quản lý ecosystem:** version matrix, capability negotiation, metadata, documentation, test kit và deprecation timeline.
6. **Triển khai và rollback được:** theo dõi plugin lỗi, có failure policy rõ ràng và giữ phương án quay lại an toàn.

Khi các điều kiện này được kiểm chứng bằng artifact thực tế và contract tests, nền tảng có thể tiến hóa Java API mà không buộc toàn bộ hệ sinh thái plugin bên ngoài phải nâng cấp đồng thời hoặc chịu những thay đổi bất ngờ.

