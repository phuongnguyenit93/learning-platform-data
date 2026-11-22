# Kiểm thử tổng hợp trên JDK được hỗ trợ hiện hành

> Bài thực hành kiểm thử liên chức năng Java trên nhiều phiên bản JDK, sử dụng API Java còn được hỗ trợ, kiểm thử có thể chạy lại, báo cáo PASS/FAIL/SKIP trung thực và một ma trận tương thích rõ ràng. Mốc đối chiếu phiên bản: **05/11/2026**. Đây là bài thực hành, không phải tuyên bố chứng nhận cho một sản phẩm JDK hoặc một hệ điều hành cụ thể.

## 1. Vì sao cần kiểm thử tổng hợp trên JDK hiện hành?

Một chương trình Java có thể **biên dịch thành công** nhưng vẫn gặp lỗi khi chạy trên JDK khác vì hành vi thư viện, provider, trình phân tích XML, hệ quản lý module, driver JDBC, cấu hình locale, file encoding, chính sách bảo mật hoặc tác động của JIT/GC. Trong một module học tập có kiến thức từ Java 6, yêu cầu quan trọng là **giữ lại các API vẫn hiện hành**, nhưng kiểm nghiệm chúng trên **các JDK đang được nhà cung cấp hỗ trợ**, không lấy JDK 6/7/8 làm môi trường thực hành mặc định.

Bài này xây dựng một bộ kiểm thử nhỏ nhưng thực tế, kết hợp:

- `ArrayDeque` và hai ngữ nghĩa FIFO/LIFO.
- Unicode NFC và UTF-8, tránh phụ thuộc default charset.
- `ResourceBundle` và đường fallback locale không dùng default locale của máy.
- `ServiceLoader` có provider JAR/classpath resource thật.
- StAX `XMLStreamReader` và `XMLEventReader` với cấu hình không cho external XML resolution.
- JMX `ThreadMXBean` và platform MBeanServer.
- Executor và `ArrayBlockingQueue` có giới hạn, timeout và cleanup.
- `java.time` với một timezone offset explicit.
- NIO `Files` đọc/ghi UTF-8 trong thư mục tạm, có cleanup.
- `javax.tools.JavaCompiler` biên dịch source Java ngay trong chương trình rồi load/chạy class được sinh ra.
- Classfile magic/version (Java 17 → major version 61).
- JDBC `java.sql` API presence; tách riêng **integration test với database thật** vì cần driver, credentials và môi trường được cung cấp.
- Bài bổ sung **virtual threads Java 21+** và **Class-File API chuẩn Java 24+** để biết cách chia suite theo feature floor.

Đây là **smoke + integration-harness** cho API/JDK, không thay thế integration tests của service thật, performance tests, security audit hoặc migration testing với toàn bộ dependencies.

## 2. Những JDK nên xem xét tính đến 05/11/2026

Nguồn chính thức Oracle cập nhật **20/10/2026** xác nhận:

| Dòng Java | Tình trạng vào 05/11/2026 | Ứng dụng trong bài |
| --- | --- | --- |
| **JDK 27** | Feature release mới nhất, phát hành 15/09/2026; non-LTS | Runtime mục tiêu nếu chính sách doanh nghiệp chấp nhận chu kỳ cập nhật nhanh |
| **JDK 25** | Bản LTS mới nhất, GA 09/2025 | Mục tiêu ưu tiên cho deployment LTS mới |
| **JDK 21** | Bản LTS cũ hơn, vẫn trong thời hạn hỗ trợ thương mại của Oracle | Runtime mục tiêu khi project vẫn duy trì 21 |
| **JDK 17** | LTS cũ; Oracle Premier Support đã hết 09/2026, có Extended Support và chính sách từng vendor | Compatibility baseline **nếu** tổ chức thực sự có bản phân phối/patch được hỗ trợ |
| JDK 26 | Non-LTS, đã bị JDK 27 thay thế về dòng tính năng | Không chọn làm nhánh support mới |
| JDK 24 | Non-LTS, đã bị các release tiếp theo thay thế | Chỉ dùng làm máy kiểm thử cục bộ nếu đó là toolchain sẵn có, **không** coi như runtime production hiện hành |
| Java 6 | Runtime lịch sử, không phải target vận hành của bài | Chỉ là tên module học, **không** thiết lập CI trên JVM 6 |

**Quan trọng:** “Được hỗ trợ” là khẳng định về **bản phân phối JDK, nhà cung cấp, bản vá bảo mật, OS/CPU và gói hỗ trợ** — không chỉ là số phiên bản. LTS không tự đồng nghĩa “mọi build từ năm đầu release đều được vá” hoặc “license miễn phí vô thời hạn”. Kiểm Oracle/Temurin/Azul/Red Hat/Microsoft support policy và các bản patch mới nhất theo hợp đồng.

Theo Oracle roadmap: JDK 21 có Premier Support đến ít nhất **09/2028**, JDK 25 đến ít nhất **09/2030**. Với JDK 17, Premier đã hết **09/2026**, Extended Support được liệt kê đến ít nhất **09/2029** với điều kiện entitlement phù hợp. Oracle JDK 21 updates từ **10/2026** còn có những thay đổi về điều kiện licensing; không tự coi mọi dòng LTS có cùng license.

Để tránh lệ thuộc một câu số hiệu sẽ sớm lỗi thời, bài khuyến nghị CI **kiểm patch level hiện tại** khi chạy; ghi `java -version`, `javac -version` và nguồn JDK vào artifact. Với Java 27, Oracle công bố release notes cho GA tháng 09/2026 và các bản cập nhật tháng 10/2026.

Nguồn:
- [Oracle Java SE Support Roadmap, 20/10/2026](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/)
- [Oracle JDK 27 Release Notes, 15/09/2026](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Oracle JDK 27 Consolidated Updates](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- [Oracle note on JDK 21 licensing, 14/08/2026](https://blogs.oracle.com/java/jdk-21-approaches-end-of-permissive-license)

## 3. Phân loại đúng các mức tương thích

Một báo cáo “PASS Java 25” còn quá mơ hồ. Phân biệt:

| Mức | Bạn phải kiểm gì? | Ví dụ |
| --- | --- | --- |
| **Source compatibility** | Source có biên dịch trên toolchain/API target không? | `javac --release 17 ...` |
| **Binary compatibility** | Class files đã build có được runtime đích load/link không? | `java -cp out JdkIntegratedSuite` trên JDK 17/21/25/27 |
| **Behavioral compatibility** | Semantics vẫn đúng, stdout/assertions/exception cases khớp? | FIFO, locale, StAX/JMX, ServiceLoader |
| **Environmental compatibility** | OS, filesystem, timezone, locale, providers, classpath, modules, permissions | StAX provider, UTF-8, temp directory |
| **Integration compatibility** | Framework, database/driver, network, JMX agent, JDBC transaction hoạt động không? | PostgreSQL/MySQL testcontainers hoặc DB test |
| **Performance/regression** | Throughput/latency/memory/GC so với baseline thật | Benchmark/JFR theo workload |
| **Security/support** | Patch level, license, vulnerability policy, agent/TLS access | Supported JDK build, SBOM, CVE process |

`javac --release 17` chỉ khẳng định compiler target **cú pháp/API public của 17** và xuất classfile version phù hợp. Nó **không chứng minh** runtime Java 17/21/25/27 thực sự đã chạy và không chứng minh hệ sinh thái JDBC/drivers/containers tương thích.

### 3.1. Vì sao dùng baseline Java 17?

Các API trong bộ kiểm thử chính đều có trên Java 17. Chọn `--release 17` tạo **một binary artifact** có thể thử trên nhiều runtimes tương thích. Vì thế câu hỏi cốt lõi là “source/binary Java 17 còn hoạt động chính xác trên JDK LTS và feature release đang dùng không?”

Nếu project đã chính thức yêu cầu Java 21+ hoặc Java 25+, hãy thay baseline build target theo chính sách của project. Chọn version cao nhất hiện có **không** tự làm chương trình tốt hơn; điều quan trọng là chỉ dùng features hợp lệ và test runtime thật.

### 3.2. Build JDK khác runtime JDK

~~~text
Build machine:
  javac --release 17  ---> class files major 61
                                    |
        +---------------------------+----------------------+
        |                           |                      |
   Runtime JDK 17              Runtime JDK 21         Runtime JDK 25 / 27
   Java 17 API behavior        Java 21 behavior       LTS / latest behavior
        |                           |                      |
        +----------- RUN SAME INTEGRATION TESTS ----------+
                                    |
                         report independently per JDK
~~~

**Không** copy source và build lại bằng target release 27 rồi mong chạy class trên 17. Mỗi lần build ra class major version cao hơn không được JVM cũ nhận (ví dụ `UnsupportedClassVersionError`). Ngược lại, binary target 17 thường được runtime mới hơn chấp nhận theo backward-compatibility model, nhưng **vẫn phải test semantic/integration**.

## 4. Nguyên tắc của một bộ kiểm thử tái lập được

1. **Không phụ thuộc default locale**. Dùng `Locale.forLanguageTag("vi-VN")` và ResourceBundle Control rõ ràng.
2. **Không phụ thuộc system timezone**. Dùng `Instant.parse(...)` và `ZoneOffset.ofHours(7)`.
3. **Không phụ thuộc default charset**. Dùng `StandardCharsets.UTF_8` khi mã hóa, file I/O.
4. **Không phụ thuộc thời gian thực**. Không gọi `LocalDateTime.now()` để so output cố định.
5. **Không phụ thuộc vào network/DB** trừ một lớp integration test được cấu hình rõ ràng.
6. **Có timeout** khi dùng future/executor để không tạo CI job treo vô hạn.
7. **Dọn file tạm** trong `finally`, không ghi vào repository.
8. **Chạy trong JDK đầy đủ** có module `jdk.compiler` khi test `ToolProvider`; JRE tùy biến thiếu compiler phải được đánh giá riêng.
9. **Không chèn null** vào `ArrayDeque`/`ArrayBlockingQueue`; không nhầm các queue này là thread-safe giống nhau.
10. **Chặn external XML resolution**, không dùng tải DTD/schema qua Internet trong smoke test.
11. **Báo FAIL rõ ràng** và trả process exit code khác 0 nếu test fail; không chỉ in “OK” rồi thoát 0.
12. **SKIP có lý do rõ ràng**, không tự biến việc không có DB thật thành “JDBC integration PASS”.
13. **Giữ riêng test theo version floor**: Java 17 baseline, Java 21 virtual thread, Java 24+ Class-File API.
14. **Chạy cùng binary trên nhiều runtime thực**; không lấy một lần chạy trên JDK 24 làm bằng chứng đã test JDK 25/27.
15. **Không phụ thuộc internal JDK APIs** như `sun.misc.*` hoặc `com.sun.tools.javac.*` khi có public API tương ứng.

## 5. Cấu trúc dự án ví dụ

Tạo thư mục riêng cho bài thực hành (không đặt vào repository production nếu chưa qua review):

~~~text
jdk-integrated-lab/
├── JdkIntegratedSuite.java
├── GreetingProvider.java
├── FriendlyGreetingProvider.java
├── Messages.properties
├── Messages_vi.properties
├── META-INF/
│   └── services/
│       └── GreetingProvider
├── VirtualThreadProbe.java
├── ClassFileApiProbe.java
├── Target.java
└── out/                         (tạo bởi lệnh build, không commit)
~~~

Chỉ bộ **Java 17 baseline** cần ba source files `JdkIntegratedSuite`, `GreetingProvider`, `FriendlyGreetingProvider` và ba resources (hai bundles + một SPI service registration).

**Hai probes bổ sung** dành cho Java 21+ và Java 24+. Không đưa chúng vào lệnh `javac --release 17` vì các API dùng trong chúng chưa có ở Java 17.

### 5.1. `GreetingProvider.java`

~~~java
public interface GreetingProvider {
    String greet();
}
~~~

### 5.2. `FriendlyGreetingProvider.java`

~~~java
public final class FriendlyGreetingProvider
        implements GreetingProvider {

    public FriendlyGreetingProvider() {}

    public String greet() {
        return "hello";
    }
}
~~~

Provider có public no-arg constructor để `ServiceLoader` khởi tạo trong classpath-style service loading. Khi triển khai thành **named module**, có thể dùng module descriptor `uses/provides` thay vì chỉ dựa vào classpath service resource; đây là khác biệt deployment, không phải API lỗi thời.

### 5.3. `META-INF/services/GreetingProvider`

~~~text
FriendlyGreetingProvider
~~~

Tên file phải trùng **binary name của service interface**; nội dung file chứa **binary name của provider implementation**. Với demo các classes ở default package nên dùng tên đơn giản; trong ứng dụng thật đặt package rõ ràng như `com.example.spi.GreetingProvider` và `com.example.spi.FriendlyGreetingProvider`.

Để tài nguyên không bị bỏ sót khi build, file service config phải có mặt **trên runtime classpath** ở đúng path `META-INF/services/GreetingProvider`.

### 5.4. `Messages.properties`

~~~properties
title=Default title
rootOnly=Root fallback
~~~

### 5.5. `Messages_vi.properties`

~~~properties
title=Vietnamese title
~~~

Test yêu cầu `Locale.forLanguageTag("vi-VN")` nên Java tìm bundle `Messages_vi` khi `Messages_vi_VN` không tồn tại; `rootOnly` fallback về base bundle. Dùng `ResourceBundle.Control.getNoFallbackControl(...)` để tránh fallback sang **default locale của máy** khi candidate chain không tìm được. Đây là code classpath; named module với customized Control có một số hạn chế cần xem JavaDoc.

Không dùng chuỗi tiếng Việt Unicode trong resources này để output không bị phụ thuộc encoding của công cụ copy shell. Mục Unicode được kiểm riêng bằng bytes UTF-8 và Normalizer. Khi dự án thực sử dụng tiếng Việt, hãy lưu properties bằng UTF-8, thử non-ASCII và phân biệt default behavior của `PropertyResourceBundle` theo JDK/provider.

## 6. Bộ kiểm thử tích hợp chính: `JdkIntegratedSuite.java`

Source dưới đây là **chương trình hoàn chỉnh**, không phải pseudocode. Nó dùng Java 17 public APIs, output chỉ gồm các nhãn ASCII ổn định, không cần Internet/DB. Nó có:

- `Case` functional interface cho mỗi test.
- `run(number,label,test)` bắt exception/assertion và đánh dấu PASS/FAIL.
- `main` chạy **13 tests**, rồi ghi rõ một **SKIP** cho live JDBC integration.
- Cuối chương trình, khi có `failed > 0`, ném `AssertionError` để quy trình CI nhận non-zero exit.
- Mỗi test tách biệt, tránh phụ thuộc vào thứ tự trạng thái của test khác.
- Không dùng external dependencies.

### 6.1. Source đầy đủ

~~~java
import java.io.DataInputStream;
import java.io.InputStream;
import java.io.StringReader;
import java.lang.management.ManagementFactory;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.Queue;
import java.util.ResourceBundle;
import java.util.ServiceLoader;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.management.ObjectName;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import javax.xml.namespace.QName;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLEventReader;

public final class JdkIntegratedSuite {
    @FunctionalInterface
    interface Case {
        void check() throws Exception;
    }

    private static int passed;
    private static int failed;

    private static final String XML =
        "<root xmlns='urn:demo'>"
        + "<item code='A'>2</item><item code='B'>5</item>"
        + "<other xmlns='urn:else'><item code='C'>99</item></other>"
        + "</root>";

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static void run(int number, String label, Case test) {
        try {
            test.check();
            passed++;
            System.out.printf("PASS %02d - %s%n", number, label);
        } catch (Exception | AssertionError ex) {
            failed++;
            System.out.printf("FAIL %02d - %s: %s%n",
                    number, label, ex.getClass().getSimpleName());
            ex.printStackTrace(System.err);
        }
    }

    private static void deque() {
        Queue<String> fifo = new ArrayDeque<>();
        fifo.offer("A");
        fifo.offer("B");
        require("A".equals(fifo.peek()) && fifo.size() == 2,
                "FIFO peek must not remove");
        require("A".equals(fifo.poll())
                && "B".equals(fifo.poll())
                && fifo.poll() == null, "FIFO order");

        Deque<Integer> lifo = new ArrayDeque<>();
        lifo.push(1);
        lifo.push(2);
        require(lifo.pop() == 2 && lifo.pop() == 1,
                "LIFO order");
    }

    private static void unicode() {
        String decomposed = "e\u0301";
        String composed = "\u00e9";
        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        require(normalized.equals(composed), "NFC");

        byte[] bytes = composed.getBytes(StandardCharsets.UTF_8);
        require(new String(bytes, StandardCharsets.UTF_8)
                .equals(composed), "UTF-8 roundtrip");
    }

    private static void bundle() {
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        ResourceBundle rb = ResourceBundle.getBundle(
                "Messages",
                Locale.forLanguageTag("vi-VN"),
                ClassLoader.getSystemClassLoader(),
                control);
        require("Vietnamese title".equals(
                rb.getString("title")), "vi bundle");
        require("Root fallback".equals(
                rb.getString("rootOnly")), "root fallback");
    }

    private static void serviceLoader() {
        List<GreetingProvider> plugins = ServiceLoader
                .load(GreetingProvider.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();
        require(plugins.size() == 1
                && "hello".equals(plugins.get(0).greet()),
                "SPI provider");
    }

    private static XMLInputFactory secureFactory() {
        XMLInputFactory factory =
                XMLInputFactory.newFactory();
        factory.setProperty(
                XMLInputFactory.SUPPORT_DTD,
                Boolean.FALSE);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
                Boolean.FALSE);
        factory.setXMLResolver(
                (publicID, systemID, baseURI, namespace) -> {
                    throw new javax.xml.stream.XMLStreamException(
                            "External XML resolution disabled");
                });
        return factory;
    }

    private static void xmlCursor() throws Exception {
        XMLStreamReader r = secureFactory()
                .createXMLStreamReader(
                        new StringReader(XML));
        int count = 0;
        int total = 0;
        try {
            while (r.hasNext()) {
                if (r.next() ==
                        XMLStreamConstants.START_ELEMENT
                        && new QName("urn:demo", "item")
                                .equals(r.getName())) {
                    String code =
                            r.getAttributeValue(null, "code");
                    require("A".equals(code) || "B".equals(code),
                            "XML id");
                    total += Integer.parseInt(r.getElementText());
                    count++;
                }
            }
        } finally {
            r.close();
        }
        require(count == 2 && total == 7,
                "StAX cursor sum");
    }

    private static void xmlEvents() throws Exception {
        XMLEventReader r = secureFactory()
                .createXMLEventReader(
                        new StringReader(XML));
        List<Integer> values = new ArrayList<>();
        try {
            while (r.hasNext()) {
                var e = r.nextEvent();
                if (e.isStartElement()
                        && new QName("urn:demo", "item")
                                .equals(
                                        e.asStartElement().getName())) {
                    values.add(Integer.parseInt(
                            r.getElementText()));
                }
            }
        } finally {
            r.close();
        }
        require(values.equals(List.of(2, 5)),
                "StAX event values");
    }

    private static void jmx() throws Exception {
        require(ManagementFactory.getThreadMXBean()
                .getThreadCount() >= 1, "thread count");
        require(ManagementFactory
                .getPlatformMBeanServer()
                .isRegistered(
                        new ObjectName("java.lang:type=Threading")),
                "Threading MXBean registration");
    }

    private static void concurrency() throws Exception {
        ArrayBlockingQueue<Integer> jobs =
                new ArrayBlockingQueue<>(2);
        require(jobs.offer(10) && jobs.offer(20),
                "two slots");
        require(!jobs.offer(30), "bounded offer");

        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        try {
            Future<Integer> result =
                    executor.submit(
                            () -> jobs.take() + jobs.take());
            require(result.get(3, TimeUnit.SECONDS) == 30,
                    "consumer result");
        } finally {
            executor.shutdownNow();
            require(executor.awaitTermination(
                    3, TimeUnit.SECONDS),
                    "executor shutdown");
        }
    }

    private static void dateTime() {
        Instant utc = Instant.parse(
                "2026-11-05T06:00:00Z");
        OffsetDateTime plusSeven =
                utc.atOffset(ZoneOffset.ofHours(7));
        require("2026-11-05T13:00:00+07:00"
                .equals(
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME
                                .format(plusSeven)),
                "fixed offset date/time");
    }

    private static void nio() throws Exception {
        Path path = Files.createTempFile(
                "jdk379-", ".txt");
        try {
            String sample = "Hello \u00e9";
            Files.writeString(
                    path, sample, StandardCharsets.UTF_8);
            require(sample.equals(
                    Files.readString(
                            path, StandardCharsets.UTF_8)),
                    "NIO UTF-8");
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static void compiler() throws Exception {
        var javac = ToolProvider.getSystemJavaCompiler();
        require(javac != null, "JDK compiler required");
        Path dir = Files.createTempDirectory(
                "jdk379-compile-");
        try {
            JavaFileObject source = new SimpleJavaFileObject(
                    URI.create(
                            "string:///GeneratedCheck.java"),
                    JavaFileObject.Kind.SOURCE) {
                @Override
                public CharSequence getCharContent(
                        boolean ignoreEncodingErrors) {
                    return "public class GeneratedCheck { "
                            + "public static int value() { "
                            + "return 42; } }";
                }
            };

            var diagnostics =
                    new DiagnosticCollector<JavaFileObject>();
            try (StandardJavaFileManager fm =
                    javac.getStandardFileManager(
                            diagnostics,
                            Locale.ROOT,
                            StandardCharsets.UTF_8)) {
                var options = List.of(
                        "--release", "17",
                        "-d", dir.toString());
                Boolean okay = javac.getTask(
                        null, fm, diagnostics,
                        options, null,
                        List.of(source)).call();
                require(Boolean.TRUE.equals(okay),
                        "compiler diagnostics: "
                        + diagnostics.getDiagnostics());
            }

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{dir.toUri().toURL()},
                    null)) {
                Class<?> type = Class.forName(
                        "GeneratedCheck", true, loader);
                Object result = type.getMethod("value")
                        .invoke(null);
                require(Integer.valueOf(42).equals(result),
                        "generated code executed");
            }
        } finally {
            try (var walk = Files.walk(dir)) {
                for (Path p : walk.sorted(
                        java.util.Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }

    private static void classfile() throws Exception {
        try (InputStream raw = JdkIntegratedSuite.class
                .getResourceAsStream(
                        "JdkIntegratedSuite.class")) {
            require(raw != null, "classfile resource");
            DataInputStream in = new DataInputStream(raw);
            require(in.readInt() == 0xCAFEBABE,
                    "classfile magic");
            in.readUnsignedShort(); // Minor version.
            require(in.readUnsignedShort() == 61,
                    "--release 17 must generate major 61");
            require(Runtime.version().feature() >= 17,
                    "requires JDK 17+ runtime");
        }
    }

    private static void jdbcApi() throws Exception {
        require(java.sql.Connection.class
                .getMethod("createSQLXML")
                .getReturnType()
                == java.sql.SQLXML.class,
                "JDBC SQLXML API");
        require(java.sql.DriverManager
                .getDrivers() != null,
                "JDBC DriverManager");
    }

    public static void main(String[] args) {
        run(1, "ArrayDeque FIFO/LIFO",
                JdkIntegratedSuite::deque);
        run(2, "Unicode NFC + UTF-8",
                JdkIntegratedSuite::unicode);
        run(3, "ResourceBundle locale fallback",
                JdkIntegratedSuite::bundle);
        run(4, "ServiceLoader SPI",
                JdkIntegratedSuite::serviceLoader);
        run(5, "StAX secure cursor",
                JdkIntegratedSuite::xmlCursor);
        run(6, "StAX secure event reader",
                JdkIntegratedSuite::xmlEvents);
        run(7, "JMX ThreadMXBean",
                JdkIntegratedSuite::jmx);
        run(8, "Bounded concurrency + shutdown",
                JdkIntegratedSuite::concurrency);
        run(9, "java.time explicit offset",
                JdkIntegratedSuite::dateTime);
        run(10, "NIO temporary UTF-8 roundtrip",
                JdkIntegratedSuite::nio);
        run(11, "JavaCompiler API compile and execute",
                JdkIntegratedSuite::compiler);
        run(12, "Classfile target release 17",
                JdkIntegratedSuite::classfile);
        run(13, "JDBC API presence only",
                JdkIntegratedSuite::jdbcApi);

        System.out.println(
                "SKIP 14 - Live JDBC integration (no driver/DB supplied)");
        System.out.printf(
                "RESULT: PASS=%d FAIL=%d SKIP=1%n",
                passed, failed);

        if (failed > 0) {
            throw new AssertionError(
                    "Integration checks failed");
        }
    }
}
~~~

### 6.2. Giải thích 13 kiểm tra và vì sao chúng có giá trị

| Test | Nhóm Java | Điều được xác nhận | Điều **chưa** xác nhận |
| --- | --- | --- | --- |
| 01 | Collections | `Queue.offer/poll/peek` FIFO; `Deque.push/pop` LIFO | Đa luồng với ArrayDeque |
| 02 | Unicode/Charset | NFC “e + combining accent” thành “é”; UTF-8 roundtrip | Mọi ngôn ngữ/font/collation |
| 03 | ResourceBundle | Lookup `vi-VN → vi → root`, không fallback default locale | Cấu hình named modules mọi app |
| 04 | ServiceLoader | Đọc đúng `META-INF/services` và khởi tạo provider | Multi-module/plugin deployment thực |
| 05 | StAX cursor | Namespace QName, unprefixed attr, text totals 2+5, config external resolver deny | Mọi provider XML, mọi payload không tin cậy |
| 06 | StAX events | Event reader cùng input trả values [2,5] | Streaming tài liệu nhiều GB |
| 07 | JMX | `ThreadMXBean` và `java.lang:type=Threading` registered | Remote JMX, authentication/TLS |
| 08 | Concurrency | Bounded queue full reject; consumer `Future.get` có timeout, pool shutdown | Stress/race/load test |
| 09 | java.time | Mapping Instant sang offset +07 ổn định | IANA TZDB chính sách theo quốc gia |
| 10 | NIO | UTF-8 temp file write/read và xóa | Filesystem permissions doanh nghiệp |
| 11 | Compiler API | JavaCompiler được lấy từ JDK, compile `--release 17`, load/invoke class | Annotation processors ngoài, module layouts |
| 12 | Classfile | Magic CAFEBABE và Java17 major 61 | Bytecode verification sâu và dependencies ngoài |
| 13 | JDBC API | `Connection.createSQLXML` signature và DriverManager API có mặt | DB connection/SQL/transaction/driver |
| SKIP 14 | Live JDBC | Không có môi trường DB được cung cấp | **Không tự coi là PASS** |

Test 05 và 06 gọi `XMLInputFactory.newFactory()`; provider có thể tùy JDK/module/classpath. Bài thiết lập ``SUPPORT_DTD=false`, ``IS_SUPPORTING_EXTERNAL_ENTITIES=false` và một `XMLResolver` từ chối truy cập external resources. Parser không thực hiện network trong test. Với untrusted XML production cần thêm giới hạn kích thước/depth/time, schema policy và kiểm cấu hình provider cụ thể.

**Lưu ý về `ResourceBundle.Control`:** Ví dụ chạy trên **classpath/unnamed module**. Đối với các application packaged dưới dạng named module, hãy theo module-aware resource lookup SPI và JavaDoc; không giả định Control override hoạt động giống hệt mọi module setup.

### 6.3. Vì sao JavaCompiler test tạo thư mục tạm?

`JavaCompiler` cần output class files để `URLClassLoader` load và thực thi. Trong test:

1. Tạo `SimpleJavaFileObject` chứa source `GeneratedCheck` trong memory.
2. Gọi `ToolProvider.getSystemJavaCompiler()`.
3. Compile với `--release 17` và `-d temp`.
4. Tạo `URLClassLoader` chỉ trỏ vào temp, load `GeneratedCheck`.
5. Invoke `GeneratedCheck.value()` qua reflection và kiểm trả 42.
6. Đóng `StandardJavaFileManager` và class loader.
7. Xóa files/dir trong `finally`.

Không ghi output vào repository. Nếu chạy trên **runtime image bị lược bỏ `jdk.compiler`**, test 11 sẽ FAIL; điều đó phản ánh JDK toolchain requirement của **harness**, không nhất thiết là lỗi business runtime. Có thể tách test compiler khỏi runtime smoke nếu muốn kiểm image được build bằng `jlink` không có compiler.

### 6.4. Vì sao không tự cài JDBC driver trong smoke test?

`java.sql` là API, còn một kết nối DB thật đòi driver/provider, database đang chạy, schema, credentials và network. `DriverManager.getDrivers()` trả một enumeration (có thể **rỗng**); test 13 chỉ xác nhận API presence. Đừng tự mở kết nối giả hay dùng mock rồi ghi báo cáo “JDBC integration PASS”.

Nếu dự án có DB test, thêm riêng test 14 với dữ liệu cô lập, giao dịch rollback, schema setup/teardown, kiểm timeouts và vendor-specific SQL states. Không đưa credentials/URL thực vào source hoặc log.

## 7. Biên dịch và chạy Java 17 baseline

### 7.1. Linux/macOS (POSIX shell)

Đang đứng trong thư mục chứa source/resources ở mục 5:

~~~sh
mkdir -p out/META-INF/services
javac --release 17 -encoding UTF-8 -d out \
  JdkIntegratedSuite.java GreetingProvider.java FriendlyGreetingProvider.java

cp META-INF/services/GreetingProvider out/META-INF/services/GreetingProvider
cp Messages.properties Messages_vi.properties out/

java -cp out JdkIntegratedSuite
~~~

**Lưu ý:** `\` ở cuối dòng là continuation của shell POSIX. Không copy nguyên dòng này vào PowerShell rồi mong `\` có tác dụng continuation.

### 7.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null

javac --release 17 -encoding UTF-8 -d out JdkIntegratedSuite.java GreetingProvider.java FriendlyGreetingProvider.java

Copy-Item META-INF/services/GreetingProvider out/META-INF/services/GreetingProvider
Copy-Item Messages.properties out/
Copy-Item Messages_vi.properties out/

java -cp out JdkIntegratedSuite
~~~

Nếu `javac` thất bại, **dừng ngay** trước bước chạy. Trong CI, đừng tiếp tục dùng stale `out` từ build lần trước. Trước build có thể xóa/thay hẳn output directory của **job workspace riêng** theo build system an toàn; đừng xóa thư mục không xác định.

### 7.3. Kết quả đã chạy thực tế

Trên môi trường kiểm thử, `javac 24.0.2` biên dịch thành công với `--release 17`. Runtime test là **Zulu OpenJDK 24.0.2**, tức một **toolchain local được cài sẵn**, **không phải** bản JDK production hiện hành được khuyến nghị tại mốc tháng 11/2026.

**Stdout chính xác của baseline — 15 dòng:**

~~~text
PASS 01 - ArrayDeque FIFO/LIFO
PASS 02 - Unicode NFC + UTF-8
PASS 03 - ResourceBundle locale fallback
PASS 04 - ServiceLoader SPI
PASS 05 - StAX secure cursor
PASS 06 - StAX secure event reader
PASS 07 - JMX ThreadMXBean
PASS 08 - Bounded concurrency + shutdown
PASS 09 - java.time explicit offset
PASS 10 - NIO temporary UTF-8 roundtrip
PASS 11 - JavaCompiler API compile and execute
PASS 12 - Classfile target release 17
PASS 13 - JDBC API presence only
SKIP 14 - Live JDBC integration (no driver/DB supplied)
RESULT: PASS=13 FAIL=0 SKIP=1
~~~

**Đây là kết quả thật của một lần chạy trên JDK 24.0.2.** Không được diễn giải thành “JDK 17, 21, 25 và 27 đều đã PASS”; muốn kết luận như vậy phải chạy từng runtime thật và lưu evidence tương ứng.

### 7.4. Exit status là một phần của test contract

Khi một testcase FAIL, runner:

- In `FAIL NN - ...` cùng loại exception.
- In stack trace sang `System.err` để biết nguyên nhân.
- Tăng `failed`.
- Sau khi các tests khác hoàn tất, in summary.
- Ném `AssertionError` nếu `failed > 0`, khiến process thoát khác 0.

Nếu test chỉ in “FAIL” nhưng exit 0, nhiều CI có thể đánh dấu pipeline thành công sai. Đây là lý do cuối `main` có check `failed > 0` thay vì dựa vào stdout.

**Cần cải thiện khi production hóa:** Runner ví dụ luôn có một dòng SKIP cho JDBC; với JUnit/TestNG hoặc test runner doanh nghiệp, dùng native skip/assumption reporting và machine-readable XML/JSON thay vì tự parse text. Không che các skips quan trọng bằng cách chỉ báo PASS count.

## 8. Kiểm thử trên *từng runtime thật* của ma trận

Đặt một `out` đã build bằng toolchain có `--release 17` và đủ resource files. Sau đó dùng **đường dẫn tuyệt đối** đến binary `java` của từng JDK đích. Không dựa vào PATH toàn hệ thống nếu nhiều JDK cài cùng máy.

Ví dụ POSIX (đổi paths theo cài đặt thực tế):

~~~sh
/path/to/jdk-17/bin/java -version
/path/to/jdk-17/bin/java -cp out JdkIntegratedSuite

/path/to/jdk-21/bin/java -version
/path/to/jdk-21/bin/java -cp out JdkIntegratedSuite

/path/to/jdk-25/bin/java -version
/path/to/jdk-25/bin/java -cp out JdkIntegratedSuite

/path/to/jdk-27/bin/java -version
/path/to/jdk-27/bin/java -cp out JdkIntegratedSuite
~~~

Những paths ở đây là **placeholders**; không phải đường dẫn thực trên máy. Dùng JDK có patch updates mới nhất, xác minh OS/CPU và support entitlement của project.

Trên Windows PowerShell, cách chạy theo đường dẫn đầy đủ:

~~~powershell
& "C:\path\to\jdk-25\bin\java.exe" -version
& "C:\path\to\jdk-25\bin\java.exe" -cp out JdkIntegratedSuite
~~~

`C:\path\to\jdk-25` là **placeholder** phải được thay. Nếu chạy nhiều JDK, **không** chỉ đổi mỗi `JAVA_HOME` mà quên binary trên `PATH`: dùng fully qualified executable, kiểm output `-version` của chính executable vừa chạy.

### 8.1. Ma trận evidence — không tự điền PASS

| Target thực | Build target | Cần chạy ở đâu? | Kết quả đã có từ lượt thử này? |
| --- | --- | --- | --- |
| JDK 17 còn vendor support | Classfile 61, `--release 17` | JDK 17 runtime thật | **Chưa chạy** |
| JDK 21 LTS | Classfile 61 | JDK 21 runtime thật | **Chưa chạy** |
| JDK 25 LTS | Classfile 61 | JDK 25 runtime thật | **Chưa chạy** |
| JDK 27 latest feature | Classfile 61 | JDK 27 runtime thật | **Chưa chạy** |
| JDK 24.0.2 cục bộ | Classfile 61 | Zulu OpenJDK 24.0.2 | **13 PASS / 1 SKIP / 0 FAIL** |
| JDK 26 non-LTS | Không ưu tiên | Đã bị feature release mới thay thế | **Không phải target đề xuất** |

**Cách ghi kết quả tốt:** Mỗi dòng nên có vendor, `java -version` đầy đủ, OS/arch, timestamp, commit ID, classpath dependency versions, testcase pass/fail/skip và log/path evidence. Không gán “Supported: PASS” chỉ bằng việc `java -version` in đúng số.

### 8.2. “Build once, test many” và “recompile on each JDK”

Cả hai chiến lược đều hữu ích, nhưng kiểm mục tiêu khác nhau.

**Build once:** Một artifact biên dịch bằng `javac --release 17`, chạy nguyên bản trên JDK 17/21/25/27. Kiểm **binary + behavioral** compatibility.

**Recompile per JDK:** Build source trên từng JDK bằng `--release 17` (nếu compiler đó hỗ trợ release target) rồi chạy. Kiểm thêm **compiler behavior**, build plugins, annotation processors và toolchain compatibility.

Một release của `javac` chỉ hỗ trợ một tập `--release` nhất định; xem `javac --help` của compiler thực. Đừng mặc nhiên mọi compiler mới cho phép mọi target lịch sử. Với các targets JDK17/21/25/27 hiện nói đến, có thể thiết kế build JDK25 làm “canonical Java17 artifact” và test cùng artifact trên từng runtime.

### 8.3. Phân biệt classfile major version và runtime feature version

- Java 17 classfile major = **61**.
- Java 21 classfile major = **65**.
- Java 24 classfile major = **68**.
- Java 25 classfile major = **69**.
- Java 27 classfile major = **71**.

Kiểm major 61 trong baseline khẳng định class đã được compile target Java17; nó **không nói** runtime đang chạy phải là Java17. Chính `Runtime.version().feature()` hoặc `java -version` cho biết runtime. Các numbers ở đây dùng để phân biệt classfile target, không phải chọn dependency bằng so sánh số tùy tiện.

## 9. Bài bổ sung: Java 21+ virtual threads

**Virtual threads** là feature chính thức từ Java 21 và có thể được kiểm trên JDK21/25/27. Chúng **không** tồn tại trong Java17, nên phải tách code thành một source file và build target `--release 21`, không gộp vào `JdkIntegratedSuite`.

### 9.1. `VirtualThreadProbe.java` — source độc lập

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class VirtualThreadProbe {
    public static void main(String[] args)
            throws Exception {
        Thread one = Thread.ofVirtual()
                .name("probe-one")
                .start(() -> {
                    if (!Thread.currentThread().isVirtual()) {
                        throw new AssertionError(
                                "Expected virtual thread");
                    }
                });
        one.join();
        if (!one.isVirtual() || one.isAlive()) {
            throw new AssertionError(
                    "Virtual thread did not terminate");
        }
        System.out.println(
                "PASS - Java 21 virtual thread starts and joins");

        ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor();
        try {
            Future<Integer> left = executor.submit(() -> {
                if (!Thread.currentThread().isVirtual()) {
                    throw new AssertionError(
                            "Expected virtual executor task");
                }
                return 19;
            });
            Future<Integer> right =
                    executor.submit(() -> 23);
            if (left.get(3, TimeUnit.SECONDS)
                    + right.get(3, TimeUnit.SECONDS) != 42) {
                throw new AssertionError(
                        "Unexpected executor results");
            }
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(
                    3, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "Executor failed to terminate");
            }
        }
        System.out.println(
                "PASS - Java 21 virtual executor computes 42");
        System.out.println("RESULT: JAVA21_PROBE_PASS");
    }
}
~~~

### 9.2. Compile và chạy

~~~sh
javac --release 21 VirtualThreadProbe.java
java VirtualThreadProbe
~~~

**Đã biên dịch bằng `javac --release 21` và chạy trên JDK 24.0.2. Stdout chính xác:**

~~~text
PASS - Java 21 virtual thread starts and joins
PASS - Java 21 virtual executor computes 42
RESULT: JAVA21_PROBE_PASS
~~~

Không suy ra 3 dòng này đã chạy trên JDK 21, 25 hay 27. Để xác minh các runtime hiện hành, chạy binary Java21 này bằng **mỗi JDK21/25/27 thật**.

Đây là smoke test chức năng API tạo virtual thread và executor, **không** đo throughput/GC, không chứng minh virtual-thread pinning-free cho ứng dụng bất kỳ, và không test structured concurrency preview.

## 10. Bài bổ sung: Class-File API từ Java 24, dùng trên JDK 25/27

Java 24 (JEP 484) đưa `java.lang.classfile` trở thành **API chuẩn**. Feature vẫn hiện hành trên JDK25/27. Đây là lựa chọn public API để đọc/biến đổi classfile; không cần `jdk.internal.*` hoặc `--enable-preview` đối với phần API đã final.

Chúng ta chỉ parse classfile Java17 đã tạo và kiểm:

- majorVersion đúng 61.
- thisClass internal name đúng `Target`.

### 10.1. `Target.java`

~~~java
public final class Target {
    public static int answer() {
        return 42;
    }
}
~~~

### 10.2. `ClassFileApiProbe.java`

~~~java
import java.lang.classfile.ClassFile;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassFileApiProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Provide .class path");
        }
        var model = ClassFile.of().parse(
                Files.readAllBytes(Path.of(args[0])));
        if (model.majorVersion() != 61) {
            throw new AssertionError(
                    "Expected Java 17 classfile major 61");
        }
        if (!"Target".equals(
                model.thisClass().asInternalName())) {
            throw new AssertionError(
                    "Unexpected class name");
        }
        System.out.println(
                "PASS - Standard Class-File API parses major 61");
        System.out.println(
                "PASS - Class name is Target");
        System.out.println(
                "RESULT: CLASSFILE_PROBE_PASS");
    }
}
~~~

### 10.3. Cách chạy

Từ thư mục chứa hai files, trên môi trường POSIX:

~~~sh
javac --release 17 Target.java
javac --release 24 ClassFileApiProbe.java
java ClassFileApiProbe Target.class
~~~

Trên JDK25 hoặc 27, có thể dùng `--release 24` để kiểm compatibility với Class-File API chuẩn từ Java24, nếu compiler bản đó chấp nhận target 24. Trên JDK17/21, class chứa `java.lang.classfile` **không thể compile/run**, nên ghi `SKIP_NOT_APPLICABLE` thay vì FAIL cho feature ngoài phạm vi runtime.

**Đã compile `--release 24` và chạy trên JDK24.0.2, stdout chính xác:**

~~~text
PASS - Standard Class-File API parses major 61
PASS - Class name is Target
RESULT: CLASSFILE_PROBE_PASS
~~~

Lưu ý `ClassFileApiProbe.class` target 24 **không chạy** trên JDK21 hoặc JDK17. Nếu muốn bảo đảm nó hoạt động trên JDK25/27, vẫn phải chạy trên runtimes đó và ghi lại output thật. Test này xác nhận public API đã final trên JDK24; không giả định classfile transformation/redefinition tùy ý đều hợp lệ.

## 11. Một ma trận CI đáng tin cậy nên có gì?

### 11.1. Các chiều nên chạy độc lập

| Trục | Giá trị đề xuất | Vì sao |
| --- | --- | --- |
| JDK runtime | 21 LTS, 25 LTS, 27 latest; 17 nếu còn entitlement/support | Không gộp version khác nhau |
| JDK vendor | Vendor chính của production; thêm vendor dự phòng nếu được dùng | Runtime implementation/patch level |
| OS | Linux production, Windows development nếu project có Windows | Paths, charsets, filesystem, native components |
| CPU | x64/arm64 nếu deploy cả hai | Native libs, image compatibility |
| Build target | `--release 17` baseline, feature probes `21` và `24` | Chặn vô tình dùng API version quá mới |
| XML provider | Runtime default và provider thật nếu override | StAX configuration/semantics |
| Database | DB engine/version thực + JDBC driver version | Tránh JDBC “API-only PASS” giả |
| Agent/instrumentation | Agent startup test trong JVM riêng nếu project dùng | Vòng đời premain/retransform/JPMS |
| Security | JDK patch currency, TLS/cert chain | Avoid old builds |
| Performance | Tải đại diện, warmup, metrics theo SLO | Behavior pass chưa đủ |

**Không** ép Cartesian product khổng lồ nếu chi phí quá cao. Xếp ưu tiên: các runtimes đang deploy × production OS × driver/provider chính. Feature release JDK27 có thể ở nhánh canary/nighly, LTS25 là mục tiêu production chính khi được phê duyệt. Không tuyên bố rằng JDK27 nên dùng production trong mọi tổ chức; điều đó tùy support policy và release cadence.

### 11.2. Gating và trạng thái chính xác

Nên dùng các trạng thái:

- `PASS`: kiểm thật đã chạy, asserts qua, exit code 0.
- `FAIL`: test chạy và assertion/execution fail.
- `SKIP_NOT_APPLICABLE`: API chỉ tồn tại ở version cao hơn, ví dụ VirtualThreadProbe không chạy Java17.
- `SKIP_ENVIRONMENT`: cần DB/driver/test fixtures chưa có.
- `BLOCKED`: không lấy được JDK image, credentials, OS runner hoặc source artifact.
- `NOT_RUN`: chưa thực thi, không được chấm PASS.

Đặc biệt phân biệt:

~~~text
Source compiled on JDK24 with --release17   => SOURCE_COMPATIBLE_17
Binary executed on installed JDK24          => RUNTIME_BEHAVIOR_PASS_JDK24
No actual JDK25/JDK27 test run              => NOT_RUN_JDK25/27
No DB driver/DB endpoint                    => SKIP_ENVIRONMENT_JDBC
~~~

Không gán một “JDK25-compatible” badge nếu mới chỉ đạt compile `--release 17` nhưng chưa chạy tests trên runtime25.

### 11.3. CI workflow logic ở mức pseudocode

~~~text
Stage 1 - validate baseline:
  verify manifest/resources
  compile with --release 17
  assert classfile major 61
  static check no JDK internal APIs

Stage 2 - supported runtime matrix:
  for each configured/supported JDK runtime:
    record java -version, vendor, OS, CPU, patch
    run JdkIntegratedSuite (same baseline artifact)
    record exit code/stdout/stderr
    assert 13 base tests PASS (or surface real provider differences)
    retain SKIP real JDBC until a test DB is supplied

Stage 3 - version-specific probes:
  if JDK >= 21: compile/run VirtualThreadProbe
  else: SKIP_NOT_APPLICABLE
  if JDK >= 24: compile/run ClassFileApiProbe
  else: SKIP_NOT_APPLICABLE

Stage 4 - integration resources:
  run DB transaction/isolation/SQLXML tests if driver+DB ready
  run agent/JMX remote integration if project explicitly uses them

Stage 5 - QA and release decision:
  do not turn FAIL into PASS
  classify skips / blockers
  compare logs against baseline
  gate release on required targets, not just one green job
~~~

Đây là **pseudocode pipeline**, không phải CI config đã thực thi. Nếu dùng Maven Surefire/JUnit/TestNG, tích hợp native per-test reports, assumptions và JUnit XML thay vì phải viết runner text trong mọi project.

### 11.4. Luôn lưu phiên bản chạy thật

Trên từng runner, ghi:

~~~sh
java -version
javac -version
java -XshowSettings:properties -version
~~~

`java -XshowSettings:properties` có thể xuất **system properties nhạy cảm về đường dẫn, máy, user settings**. Chỉ lưu trong protected CI logs, redact nếu cần; không đăng công khai toàn bộ output. Ngoài ra ghi `git rev-parse HEAD` khi đã được phép chạy trong repository của project. Bài này không yêu cầu thao tác repository, do đó không chạy Git ở đây.

### 11.5. Kiểm công cụ/compiler có đang cùng JDK không?

Trên máy nhiều JDK:

~~~text
java -version       -> 25.0.x
javac -version      -> 21.0.x
~~~

là dấu hiệu PATH/JAVA_HOME không đồng nhất, có thể khiến build và runtime test bị diễn giải sai. Dùng absolute binaries hoặc toolchains configuration để đảm bảo provenance. Không dựa vào câu “máy có Java25” nếu `java` thực chất trỏ sang Java21.

## 12. Điều gì có thể khác nhau giữa các JDK dù API vẫn tồn tại?

### 12.1. Locale/ResourceBundle

Fallback/candidate lookup có quy tắc của ResourceBundle, nhưng default locale, locale providers/CLDR data và nội dung bản dịch có thể cập nhật. Vì vậy test **logic fallback** bằng bundle do project kiểm soát, không assert những tên tháng/tên quốc gia cụ thể trên mọi release nếu không cần. Khi kết quả hiển thị cho người dùng thật, test với locale/zone và dữ liệu CLDR của các JDK thực.

### 12.2. XML parser provider

`XMLInputFactory.newFactory()` chọn provider theo JAXP/ServiceLoader rules; deployment thêm XML parser dependency có thể làm provider khác. Verify properties chống DTD/external entities **thực sự có hiệu lực**, không chỉ assume test pass trên một JVM. Không cho untrusted XML phát sinh SSRF/XXE hay entity expansion không giới hạn.

### 12.3. JMX

`ManagementFactory.getThreadMXBean()` là platform JMX API hiện hành. Nhưng runtime image lược module `java.management`, security policy của container, MBeanServer instrumentation và virtual threads có thể thay đổi điều quan sát. Test trong bộ chỉ xác nhận **platform Threading MBean đăng ký và thread count dương**, không giả mạo việc đã kiểm `findDeadlockedThreads` hoặc remote JMX. Khi dùng virtual threads, `ThreadMXBean` có phạm vi giám sát platform threads; đừng coi nó là công cụ phát hiện mọi virtual-thread liveness issue.

### 12.4. JDBC drivers và SQLXML

`java.sql.Connection.createSQLXML` là method public từ lâu vẫn được hỗ trợ, nhưng **driver-specific implementation** có thể thiếu tính năng hoặc có behavior riêng. Để kiểm SQLXML/JDBC thật cần:

- Supported driver release tương thích runtime.
- Database engine/version, test schema, quyền cần thiết.
- Connection lifecycle và pool.
- PreparedStatements, ResultSet, transaction commit/rollback.
- SQLState/vendor errors, network timeouts, cancellation.
- Test Unicode SQL data/SQLXML nếu project sử dụng.
- Cleanup và bảo mật connection strings/secrets.

Không lấy một dynamic proxy/mock JDBC làm bằng chứng driver thật đã chạy thành công.

### 12.5. ServiceLoader/module path

Resource file `META-INF/services` hoạt động trong classpath test, nhưng **named modules** có provider configuration bằng `module-info.java`/`provides ... with ...`. Khi nâng cấp packaging sang module path, cần integration test riêng. Một lần chạy thành công trên classpath không bảo đảm module deployment thành công.

### 12.6. Bytecode/compiler và removed APIs

`--release` giúp ngăn source tham chiếu public APIs không có ở target. Nhưng nó không test hết bytecode transformation, reflection vào internals, framework instrumentation hoặc native integrations. Kiểm `jdeps --jdk-internals`, migration notes và framework compatibility; **không dùng flags `--add-opens` để che mọi lỗi lâu dài** nếu có giải pháp public API được hỗ trợ.

### 12.7. Encoding và thời gian

NIO `Files.readString/writeString` ở bộ test có `StandardCharsets.UTF_8` nên không phụ thuộc default charset. Date/time dùng fixed `Instant` và `ZoneOffset` nên không phụ thuộc timezone local. Ở production với `ZoneId` như Asia/Ho_Chi_Minh, IANA tzdb cập nhật có thể làm lịch sử/chính sách một số quốc gia khác thay đổi; test thực tế theo domain requirements thay vì hardcode mọi `ZonedDateTime` expected trong tương lai.

## 13. Bổ sung kiểm thử nếu dự án dùng Java agent hoặc nâng cấp module

Trong một học trình Java có Instrumentation, ClassFileTransformer và MXBean, baseline test chỉ kiểm những phần nhẹ và ổn định. Khi service thực sự dùng Java agent:

1. Tạo JVM con riêng với `-javaagent` được phê duyệt.
2. Đóng gói đúng `Premain-Class`; kiểm agent runs trước main.
3. Giới hạn transformer theo class internal name/loader/module.
4. Kiểm `isRetransformClassesSupported()` và `isModifiableClass()` trước retransform.
5. Biên dịch/test classfile bằng API chuẩn trên Java24+ hoặc thư viện bytecode được hỗ trợ trên version thấp hơn.
6. Không sửa `classfileBuffer` tại chỗ; không phụ thuộc JDK internal ASM.
7. Xác minh observed method behavior thực tế thay vì chỉ log transformer callback.
8. Kiểm cleanup, removal không tự rollback và class-loader recursion failures.
9. Kiểm compatibility với những agents khác (APM/coverage/mock), JDK module boundaries.
10. Không dynamic attach vào JVM không thuộc quyền quản lý; kể từ JDK21, chính sách dynamic agent loading đang được siết theo JEP451.

Bài chính không chạy agent vào process ngoài, không sửa JDK cài đặt, không mở remote JMX hay gửi bytecode sang server khác. Chỉ triển khai những tests có quyền truy cập và dữ liệu được phê duyệt.

## 14. Regression test cho lỗi “chỉ xuất hiện trên JDK mới”

Khi một bước FAIL trên JDK 27 nhưng PASS trên JDK25, không tự kết luận “JDK27 có bug”. Thu thập bằng chứng:

1. Có chạy **cùng commit, dependencies, config, test data** không?
2. `java -version`/vendor/patch/OS/CPU đã xác nhận đúng chưa?
3. Test có phụ thuộc default locale/timezone/charset/clock hoặc hash iteration order không?
4. Có JDK 27 release note/CSR về compatibility thay đổi semantics không?
5. Framework/driver bytecode version có hỗ trợ 27 không?
6. Có phản xạ vào internals hoặc sử dụng API deprecated bị xóa không?
7. Test có race/flaky timing không? Đã dùng latches/timeouts và cleanup chưa?
8. Lỗi xảy ra khi compile, load/link, initialization hay runtime behavior?
9. Stacktrace có `UnsupportedClassVersionError`, `IllegalAccessError`, `ServiceConfigurationError`, `FactoryConfigurationError` hoặc `SQLFeatureNotSupportedException` không?
10. Có thể tái hiện bằng một isolated reproducer như bài này không?

**Mục tiêu:** phân loại root cause thay vì vội bật flags không hiểu rõ hoặc bỏ test. Nếu lỗi do business code, sửa code; do dependency, nâng cấp dependency phiên bản được hỗ trợ; do JDK regression, tạo minimal reproducible case với version/flags và báo bug cho vendor.

## 15. Ma trận lỗi phổ biến

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Coi JDK cài sẵn 24 là production target hiện hành tháng 11/2026 | JDK24 non-LTS đã bị thay thế | Chạy 25 LTS/27 latest hoặc JDK đang được vendor hỗ trợ |
| Báo JDK25 PASS sau khi chỉ compile `--release 17` | Chưa chạy runtime25 | Thực thi binary trên JDK25 thật |
| Không ghi JDK vendor/patch | Lỗi và CVE phụ thuộc build | Ghi provenance |
| JDK21 được gọi “latest LTS” trong 2026 | JDK25 mới là latest LTS | Cập nhật roadmap |
| Coi mọi JDK17 build vẫn đang được Oracle Premier hỗ trợ | Premier kết thúc 09/2026 | Kiểm Extended Support/vendor entitlement |
| Mọi test chạy trên default locale/zone | Output không ổn định giữa machines | Locale/offset explicit |
| Dùng default charset cho files | Lỗi encoding khác OS | UTF-8 explicit |
| Dùng `Thread.sleep` tùy ý làm test concurrent | Timing flaky | Future timeout/latches |
| Không shutdown executor | CI treo/leak threads | finally shutdown/await |
| Bỏ `META-INF/services` trong artifact | ServiceLoader không tìm provider | Test packaging |
| Đặt `Messages.properties` ngoài classpath | MissingResourceException | Copy resources vào runtime output |
| Mong StAX tự chống XXE | Provider config khác nhau | Deny DTD/entities + resolver + budgets |
| Khẳng định JDBC PASS vì DriverManager có mặt | Chưa thử driver/DB | SKIP hoặc integration test thật |
| Cho rằng kiểm JMX thread count là kiểm deadlock | Coverage không đủ | Test riêng ThreadMXBean deadlock |
| Dùng virtual thread source ở `--release 17` | API chưa tồn tại | Tách Java21 probe |
| Dùng Class-File API ở JDK17 | API chuẩn chỉ từ 24 | Tách Java24+ probe |
| Chạy class major68 trên JVM21 | `UnsupportedClassVersionError` | Target đúng release |
| Lạm dụng internal JDK packages | Runtime mới dễ làm vỡ | Public API hoặc lib được hỗ trợ |
| Giấu SKIP trong tổng PASS | Báo cáo sai | SKIP reason rõ ràng |
| Chỉ kiểm stdout, không kiểm exit code | CI có thể xanh dù fail | Assert nonzero exit khi failed |
| So sánh performance từ một lần chạy | JIT/GC nhiễu | Benchmark/JFR đúng cách |
| Đưa JDBC secrets vào logs | Rò rỉ thông tin | Secret manager/redaction |
| Gộp test suite với app production startup | Làm chậm hoặc thay state hệ thống | Chạy harness riêng |
| Không dọn temp files | CI đầy disk và test phụ thuộc lần trước | finally cleanup |
| Tự sửa spreadsheet/progress khi làm bài | Vượt phạm vi học liệu | Chỉ viết đúng vùng được giao |

## 16. Những bài tập mở rộng

### Bài 1 — chạy một binary trên nhiều runtime

Build với `--release 17`. Chạy trên JDK21,25,27 theo paths thực và ghi table:

| JDK | Vendor/build | PASS | FAIL | SKIP | Runtime evidence |
| --- | --- | --- | --- | --- | --- |
| 21 | Điền sau chạy | Không tự điền | | | |
| 25 | Điền sau chạy | Không tự điền | | | |
| 27 | Điền sau chạy | Không tự điền | | | |

**Yêu cầu nộp:** Command lines, exit codes, logs, screenshot/report nếu phù hợp. Không copy kết quả JDK24 sang những dòng chưa chạy.

### Bài 2 — cố tình tạo một test FAIL

Tạm sửa assertion FIFO thành đòi `"B"` ở đầu sau khi offer A rồi B, compile/run và quan sát `FAIL 01 ...`, summary có FAIL và exit nonzero. Sau đó hoàn nguyên code. Bài này xác nhận harness thực sự phát hiện bug, không chỉ in cố định “PASS”.

### Bài 3 — mất resource SPI

Bỏ file `out/META-INF/services/GreetingProvider` trong bản build thử nghiệm cô lập. Chạy lại và quan sát test 04 FAIL. Phục hồi resource. Cách này thể hiện **classpath resources là một phần của artifact**, không chỉ Java source.

### Bài 4 — ResourceBundle fallback

Xóa `Messages_vi.properties` rồi dự đoán kết quả lookup: nếu chỉ còn base bundle, `title` sẽ là `Default title` thay vì `Vietnamese title`, nên assertion hiện tại FAIL. Giải thích khác biệt giữa **locale candidate fallback** và **fallback tới default system locale**.

### Bài 5 — XML namespace

Đổi item trong namespace khác thành `urn:demo` nhưng giữ code `C` và content 99. Lúc này cursor test tìm thêm một item, dẫn tới FAIL. Giải thích vì sao dùng `QName` tốt hơn chỉ so localName nếu dữ liệu có nhiều namespace.

### Bài 6 — NIO và encoding

Thêm text non-ASCII tiếng Việt vào `sample` rồi kiểm roundtrip trên Windows/Linux. Đừng dùng `new String(bytes)` thiếu charset trong assertion; dùng `StandardCharsets.UTF_8` rõ ràng.

### Bài 7 — concurrent boundedness

Trong `ArrayBlockingQueue<>(2)`, offer 2 values thành công và offer thứ ba false trước consumer. Dùng `take` trong consumer và `Future.get(timeout)`. Giải thích vì sao cách này kiểm tính bounded của **concurrent queue** nhưng chưa test race hay throughput.

### Bài 8 — JavaCompiler API

Thay Java source sinh động thành method `value()` trả 99, sửa assertion tương ứng. Thử đưa syntax lỗi và quan sát diagnostics; giữ test dir cleanup. Mở rộng tạo nhiều JavaFileObjects khi project có dependencies.

### Bài 9 — optional modern features

Dùng runtime21+ chạy `VirtualThreadProbe`. Dùng runtime25/27 chạy `ClassFileApiProbe` (compile target24). Đối với Java17, ghi `SKIP_NOT_APPLICABLE` chứ không coi inability to compile virtual threads là regression của Java17.

### Bài 10 — JDBC integration thực

Nếu có một test database được cấp phép, thiết kế test transactional:

- Nhận connection URL/user/password **từ secret manager hoặc environment protected**.
- Driver phải hỗ trợ DB engine/runtime.
- Tạo schema/table test cô lập.
- Dùng PreparedStatement với parameters, không ghép dữ liệu người dùng vào SQL.
- Commit/rollback theo contract.
- Verify ResultSet mapping, encoding và SQLXML nếu có driver capability.
- Đóng Connection/Statement/ResultSet đúng thứ tự try-with-resources.
- Cleanup test rows/schema kể cả khi fail.
- Ghi driver version và DB version vào logs nhưng redact secrets.
- Không chạy DDL destructive trên production database.

Bài này **không** có database supplied nên không giả lập kết quả.

## 17. Câu hỏi tự kiểm tra

**1. JDK mới nhất tháng 11/2026 là phiên bản nào?** JDK 27 feature release, GA 15/09/2026.

**2. LTS mới nhất là phiên bản nào?** JDK 25 LTS.

**3. JDK 21 có còn thuộc dòng hỗ trợ không?** Có, tùy vendor và cập nhật; Oracle Premier đến ít nhất 09/2028.

**4. JDK 17 có tự động còn Oracle Premier Support sau 09/2026 không?** Không. Phải xem Extended Support/vendor entitlement.

**5. Chạy test trên JDK24 có được ghi JDK25 PASS không?** Không.

**6. `javac --release 17` chứng minh điều gì?** Biên dịch theo language/public API Java17 và tạo classfile tương ứng.

**7. `--release 17` có giống `--target 17` đơn lẻ không?** Không; `--release` còn giới hạn API được phép dùng theo target release.

**8. Java17 classfile major version là gì?** 61.

**9. Có thể lấy JDK25 compiler tạo classfile major69 rồi chạy trên JVM17 không?** Không, JVM17 không nhận classfile version cao như vậy.

**10. Java27 mới nhất có tự động dùng được mọi framework cũ không?** Không; cần test compatibility với dependencies.

**11. Vì sao test dùng `Locale.forLanguageTag` và no-default-fallback Control?** Để kết quả không phụ thuộc locale máy.

**12. Vì sao tách StAX cursor và event tests?** Chúng có hai API/cách tiêu thụ events khác nhau; phát hiện regression/provider issue có thể khác.

**13. Vì sao không nên bật external entities khi parse untrusted XML?** Rủi ro XXE/SSRF/đọc dữ liệu không được phép; cần secure config và resource limits.

**14. ServiceLoader provider cần gì trên classpath?** Provider class và service configuration file ở `META-INF/services/<binary-interface-name>`.

**15. Test JavaCompiler cần JDK hay có thể chạy trên mọi custom runtime image?** Nó cần module/compiler APIs của JDK; custom image không có compiler có thể FAIL.

**16. Test JDBC API presence có chứng minh SQLXML provider hoạt động thật?** Không.

**17. Khi thiếu DB thật nên báo gì?** `SKIP_ENVIRONMENT` với lý do, không phải PASS.

**18. Vì sao có timeout trong `Future.get`?** Để kiểm soát khả năng CI bị chờ mãi.

**19. Vì sao `ExecutorService` phải shutdown trong finally?** Tránh rò rỉ threads và JVM không thoát.

**20. Khi một test FAIL nhưng process exit 0, có rủi ro gì?** CI có thể đánh dấu xanh sai.

**21. `VirtualThreadProbe` build target nào?** Java 21.

**22. `ClassFileApiProbe` build target nào?** Java 24+, API chuẩn từ 24.

**23. Java21 chạy được ClassFileApiProbe đã build major68 không?** Không.

**24. Vì sao test UTF-8 roundtrip và NFC riêng?** Encoding và Unicode normalization là hai vấn đề khác nhau.

**25. Vì sao không dùng `System.currentTimeMillis` làm giá trị expected?** Kết quả phụ thuộc thời gian thực, dễ flaky.

**26. Một test dùng stacktrace/JMX/diagnostics có thể rò dữ liệu không?** Có; quản lý retention và protected logs.

**27. Tại sao nên capture vendor, OS và architecture?** Giúp phân biệt dependency/runtime/environment-specific regressions.

**28. Có nên dùng `--add-opens` vô điều kiện khi nâng JDK?** Không; ưu tiên sửa code/lib theo public APIs.

**29. Khi một test chỉ chạy trên JDK21+ có nên đánh FAIL trên JDK17?** Không, nếu feature không thuộc contract Java17, ghi SKIP_NOT_APPLICABLE.

**30. Ý nghĩa của bản ghi PASS đúng?** Test đã thực thi trong môi trường được nêu, asserts qua, exit code phù hợp, logs có thể truy vết.

## 18. Checklist hoàn tất kiểm thử tổng hợp

- [ ] Xác nhận **đúng JDK vendor/build/version**; cập nhật bản vá mới.
- [ ] Xác nhận JDK version còn thuộc **support policy** của tổ chức.
- [ ] Xác nhận compiler target bằng `--release` và classfile major.
- [ ] Kiểm resource files đi kèm artifact (properties, META-INF/services).
- [ ] Test FIFO/LIFO, Unicode/UTF8, locale fallback, StAX cursor/event, JMX.
- [ ] Test concurrency có boundedness, timeout và shutdown.
- [ ] Test JavaCompiler dynamic compile nếu application yêu cầu compiler capability.
- [ ] Test NIO và cleanup.
- [ ] Không gán JDBC integration PASS nếu thiếu DB.
- [ ] Phân nhóm baseline, Java21 feature probe và Java24+ Class-File probe.
- [ ] Chạy artifact trên **mỗi runtime** trong support matrix, không chỉ compile.
- [ ] Lưu stdout, stderr, exit code và provenance.
- [ ] Phân loại PASS/FAIL/SKIP/NOT_RUN chính xác.
- [ ] Bổ sung tests DB/agent/module path khi ứng dụng thật có dùng.
- [ ] Không dùng internal/deprecated APIs nếu có public replacements.
- [ ] Đánh giá compatibility ngoài API: library/framework/driver, security/TLS, performance.
- [ ] Không hardcode default locale/zone/charset khi output phải deterministic.
- [ ] Không để credentials/dumps/diagnostic paths rò qua logs.
- [ ] Đánh dấu release gate rõ cho các supported JDK quan trọng.

## 19. Kết luận

**Kiểm thử tổng hợp trên JDK được hỗ trợ hiện hành** không chỉ là chạy `java -version` hoặc compile một source file. Một kết quả đáng tin cần phân biệt **build target**, **runtime thực**, **public API**, **hành vi**, **external providers**, **DB/agent integrations** và **quyền được support/nhận security updates**.

Tại **05/11/2026**, JDK27 là feature release mới nhất và JDK25 là LTS mới nhất; JDK21 vẫn là LTS đang được duy trì, JDK17 chỉ nên là mục tiêu nếu vẫn có supported/vendor entitlement thích hợp. JDK24/26 không phải những dòng feature-release production mới nên nhắm tới. Bộ ví dụ đã được kiểm ở **Zulu JDK24.0.2 toolchain** như một local validation: baseline Java17 có **13 PASS, 0 FAIL, 1 SKIP**; Java21 virtual thread probe và Java24 Class-File API probe cũng đã biên dịch/chạy trên cùng runtime. **JDK17/21/25/27 chưa chạy trong môi trường kiểm thử này** và cần chạy thật để kết luận support matrix.

Bài học cốt lõi: **đánh giá đúng điều đã kiểm và chưa kiểm**; một bài smoke test không được biến thành tuyên bố tương thích production toàn hệ thống.

### Tài liệu chính thức nên tra cứu khi vận hành

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — phiên bản LTS, feature releases, timeline và điều kiện support.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/) — JDK bản mới và các bản cập nhật.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — những thay đổi tương thích phiên bản hiện hành.
- [Oracle javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — `--release`, `-encoding`, `-d` và API cross-compilation.
- [Oracle Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/index.html) — Java SE API mới nhất.
- [Oracle Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/index.html) — API bản LTS mới nhất.
- [Oracle Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/index.html) — API LTS, virtual threads.
- [Oracle Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/index.html) — Java17 baseline.
- [Oracle Java SE 27 ArrayDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html) — FIFO/LIFO/deque.
- [Oracle Java SE 27 ResourceBundle](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ResourceBundle.html) — locale bundles và fallback.
- [Oracle Java SE 27 ServiceLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ServiceLoader.html) — SPI resource/module providers.
- [Oracle Java SE 27 XMLInputFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html) — StAX XML parser configuration.
- [Oracle Java SE 27 ThreadMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ThreadMXBean.html) — platform thread management.
- [Oracle Java SE 27 JavaCompiler](https://docs.oracle.com/en/java/javase/27/docs/api/java.compiler/javax/tools/JavaCompiler.html) — dynamic compiler tests.
- [Oracle Java SE 27 JDBC Connection](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html) — `SQLXML` và JDBC integration semantics.
- [Oracle Java SE 27 Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — virtual threads concepts.
- [OpenJDK JEP 484 — Class-File API](https://openjdk.org/jeps/484) — API chuẩn từ Java24.
