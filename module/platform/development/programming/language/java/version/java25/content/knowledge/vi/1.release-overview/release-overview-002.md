# Phân biệt tính năng chính thức, preview, incubator và experimental trong JDK 25

> **Chương:** Tổng quan Java 25  
> **Phạm vi:** `JAVA_VERSION_JAVA25` — học những thay đổi Java 25 **vẫn có ý nghĩa cho phát triển Java hiện đại**, gồm chương trình nguồn gọn, module import, flexible constructor bodies, `ScopedValue`, API dẫn xuất khóa, AOT cache và JFR. Bài này giải thích **trạng thái phát hành** để lựa chọn công nghệ đúng khi nâng cấp JDK.  
> **Nguyên tắc nội dung:** Tập trung kiến thức còn áp dụng tính đến **27/11/2026**. Không hướng dẫn sử dụng lại API/kiểu cú pháp preview cũ đã bị thay thế; những ví dụ preview được ghi rõ là **chỉ dành cho JDK 25** và cần đối chiếu API của JDK mục tiêu khi chuyển lên 26/27.

Java 25 phát hành ngày **16/09/2025**, thuộc dòng JDK được nhiều nhà cung cấp hỗ trợ dài hạn. Tuy nhiên, **một bản JDK được hỗ trợ dài hạn không có nghĩa mọi tính năng đi kèm đều đã chính thức**. Trong 18 JEP của JDK 25 có **12 thay đổi đã hoàn tất/chính thức**, **4 preview**, **1 incubator** và **1 experimental**. Một JEP có thể là API, cú pháp ngôn ngữ, cơ chế JVM, công cụ quan sát hoặc thay đổi loại bỏ nền tảng; không nên mặc định “JEP” đồng nghĩa “API mới để sử dụng”. Việc JEP được *integrated* vào JDK chỉ có nghĩa thay đổi đã vào bản phát hành, **không tự chứng minh nó là final**.

## 1. Bốn trạng thái nói lên điều gì?

| Trạng thái trong JDK 25 | Ý nghĩa | Cách sử dụng | Độ ổn định và quyết định triển khai |
|---|---|---|---|
| **Final / permanent (chính thức)** | Thiết kế đã được đưa vào chuẩn Java SE hoặc thành phần JDK/HotSpot chính thức tương ứng | Thường dùng trực tiếp **không cần** `--enable-preview`; một số cơ chế runtime cần **tùy chọn bật/tuning riêng** | Ưu tiên khi thiết kế mã sản phẩm lâu dài; vẫn phải test tương thích JDK, hệ điều hành và performance |
| **Preview** | Được đặc tả, triển khai đầy đủ để thu thập phản hồi nhưng **chưa cam kết giữ nguyên** ở phiên bản sau | `javac --enable-preview --release 25` và `java --enable-preview` khi dùng preview language/API của **JDK 25** | Thích hợp spike, bài lab và thử nghiệm có kiểm soát; phải kiểm tra thay đổi khi nâng JDK |
| **Incubator** | API/công cụ JDK đang trong giai đoạn thử nghiệm, thường phân phối qua module `jdk.incubator.*` | Với Vector API: `--add-modules jdk.incubator.vector` khi compile/chạy theo kiểu project | Không có cam kết API sẽ ổn định; có thể còn incubator trong nhiều kỳ phát hành |
| **Experimental** | Thường là khả năng JVM/JFR để đo kiểm, thu thập phản hồi hoặc nghiên cứu vận hành; có cơ chế bật riêng | Phụ thuộc từng tính năng. **JFR CPU-Time Profiling** trong JDK 25 cần bật sự kiện `jdk.CPUTimeSample` trên Linux | Không đánh đồng với preview; kiểm tra giới hạn nền tảng, chi phí đo và tính khả dụng trên runtime đang dùng |

**Phân biệt quan trọng:** `--enable-preview` **không** bật mọi tính năng “chưa final”. Nó dành cho các preview language/VM/API đúng release; incubating module dùng `--add-modules`; experimental JVM option thường có cách unlock/toggle riêng. Ngoại lệ cụ thể của **JEP 509** là một JFR event được đánh dấu experimental nhưng **không cần** `-XX:+UnlockExperimentalVMOptions` — chỉ cần bật event khi recording. Cũng không cần `--enable-preview` cho event này.

Một tính năng **final** vẫn có thể phải **opt-in** để tránh thay đổi hành vi mặc định của JVM. Ví dụ Compact Object Headers (JEP 519) đã hoàn tất trong JDK 25 nhưng cần cấu hình JVM nếu muốn sử dụng trong dòng này; “final” nói về tình trạng của tính năng, không nói tính năng luôn bật sẵn.

## 2. Bản đồ 18 JEP của JDK 25

### 2.1. Nhóm chính thức / final

| JEP | Tính năng/thay đổi | Giá trị còn áp dụng | Ghi chú |
|---|---|---|---|
| **506** | **Scoped Values** | Truyền ngữ cảnh bất biến trong dynamic scope; hữu ích với virtual threads, luồng ứng dụng có tổ chức | API **final trong 25**, không còn là preview |
| **510** | **Key Derivation Function API** | `javax.crypto.KDF` và HKDF giúp sinh khóa từ key material theo chuẩn | API **final**, cần hiểu threat model và thuật toán trước khi dùng |
| **511** | **Module Import Declarations** | `import module java.base;` giúp import các package được module export | Cú pháp **final**; không đồng nghĩa thêm `requires` hoặc tăng quyền truy cập |
| **512** | **Compact Source Files and Instance Main Methods** | Viết chương trình nhỏ bằng `void main()`, `IO.println(...)` | **Final**; phù hợp mẫu lệnh, học tập, script nhỏ |
| **513** | **Flexible Constructor Bodies** | Kiểm tra/chuyển đổi tham số trước `super(...)` hoặc `this(...)` trong giới hạn ngôn ngữ | **Final**, giảm nhu cầu workaround cũ |
| **514** | **Ahead-of-Time Command-Line Ergonomics** | Đơn giản hóa quy trình tạo/sử dụng AOT cache | Cơ chế JVM chính thức; cấu hình phụ thuộc môi trường triển khai |
| **515** | **Ahead-of-Time Method Profiling** | Hỗ trợ giảm thời gian warmup bằng dữ liệu profiling đã thu trước | Không bảo đảm mọi ứng dụng đều nhanh hơn; phải đo startup và warmup |
| **518** | **JFR Cooperative Sampling** | Nâng độ ổn định khi lấy mẫu stack JFR | Cải thiện công cụ quan sát, không phải API nghiệp vụ mới |
| **519** | **Compact Object Headers** | Giảm overhead header object ở JVM phù hợp | Final nhưng cơ chế bật và mặc định tùy **phiên bản**; đo bộ nhớ/GC |
| **520** | **JFR Method Timing & Tracing** | Đo thời gian và đường gọi method bằng JFR với cấu hình chọn lọc | Không đồng nghĩa luôn ghi tất cả method; kiểm soát overhead |
| **521** | **Generational Shenandoah** | GC thế hệ của Shenandoah đã chính thức | Chỉ áp dụng ở bản JDK/nền tảng hỗ trợ; so throughput, pause, memory |
| **503** | **Remove the 32-bit x86 Port** | Thông tin tương thích để chọn runtime JDK 25 | Đây là **thay đổi loại bỏ nền tảng**, không phải một API nên học dùng |

**Chỉ có 11 mục đầu** là các cơ chế/chức năng nên cân nhắc học và áp dụng; JEP 503 cần biết để **tránh** lên kế hoạch triển khai JDK 25 trên port 32-bit x86 đã bị loại bỏ. Không hướng dẫn phát triển cho port cũ.

### 2.2. Nhóm preview, incubator, experimental

| JEP | Tính năng | Tình trạng **riêng tại JDK 25** | Cờ/điều kiện đặc trưng |
|---|---|---|---|
| **470** | PEM Encodings of Cryptographic Objects | **Preview lần đầu** | `--enable-preview` nếu compile/chạy API preview `PEMEncoder`/`PEMDecoder` |
| **502** | Stable Values | **Preview lần đầu** | `--enable-preview` với `java.lang.StableValue` |
| **505** | Structured Concurrency | **Fifth Preview** | `--enable-preview`; API `StructuredTaskScope` còn có thể thay đổi |
| **507** | Primitive Types in Patterns, `instanceof`, `switch` | **Third Preview** | `--enable-preview` cho cú pháp pattern primitive mới |
| **508** | Vector API | **Tenth Incubator** | `--add-modules jdk.incubator.vector`, không bắt buộc `--enable-preview` chỉ vì dùng Vector API |
| **509** | JFR CPU-Time Profiling | **Experimental** | Linux; bật `jdk.CPUTimeSample` trong JFR recording, không cần preview flag |

**Tại thời điểm bài viết (11/2026), JDK 27 đã phát hành.** Khi xây dựng project mới trên JDK 27, những nhóm đang thử nghiệm cần đọc **JEP của JDK 27** thay vì sao chép code JDK 25: primitive patterns tiếp tục preview, Structured Concurrency tiếp tục preview, Vector API tiếp tục incubator và PEM vẫn preview; khái niệm `StableValue` của JDK 25 đã tiến hóa thành **Lazy Constants** trong các bản sau. Cách phân loại **trong JDK 25** không được viết lại theo trạng thái JDK 27: đây là hai mốc khác nhau.

## 3. Tính năng final: dùng thế nào trong mã Java 25?

### 3.1. `ScopedValue` (JEP 506) — final, không cần preview

`ScopedValue` cho phép truyền một giá trị bất biến về mặt binding trong phạm vi một lời gọi, rất hữu ích khi một hàm cần đọc thông tin ngữ cảnh nhưng không muốn truyền tham số xuyên nhiều lớp. Khác `ThreadLocal`, binding có scope rõ ràng và tự hết khi lời gọi kết thúc.

```java
public class RequestContextDemo {
    private static final ScopedValue<String> TRACE_LABEL =
            ScopedValue.newInstance();

    static void handle() {
        System.out.println("context=" + TRACE_LABEL.get());
    }

    public static void main(String[] args) {
        ScopedValue.where(TRACE_LABEL, "request-demo")
                .run(RequestContextDemo::handle);
    }
}
```

Chạy với JDK 25:

```bash
javac --release 25 RequestContextDemo.java
java RequestContextDemo
```

Không dùng `--enable-preview`. `ScopedValue` phù hợp với **truyền ngữ cảnh một chiều** trong dynamic scope; không thay thế mọi use case `ThreadLocal` có trạng thái cần cập nhật. Với child threads, cách kế thừa context phụ thuộc cơ chế concurrency thực sự sử dụng; không tự giả định mọi `Thread` hoặc executor kế thừa binding.

### 3.2. Compact source files, instance `main` và `IO` (JEP 512)

File `Hello.java` có thể chỉ cần:

```java
void main() {
    IO.println("Hello from Java 25");
}
```

Chạy:

```bash
java Hello.java
```

Đây là cú pháp **final** của JDK 25. `IO.println` nằm trong `java.lang.IO` của JDK 25; không cần kiểu viết cũ từ các bản preview trước. Có thể dùng nó cho ví dụ học tập, tiện ích dòng lệnh và kiểm tra nhanh. Dự án lớn vẫn nên tổ chức class/package/module có tên rõ ràng thay vì dùng compact source file cho mọi thành phần ứng dụng.

### 3.3. Module import declarations (JEP 511)

Ví dụ file `ModuleImportDemo.java`:

```java
import module java.base;

public class ModuleImportDemo {
    public static void main(String[] args) {
        var names = List.of("Ada", "Duke", "Lin");
        names.stream().map(String::toUpperCase)
                .forEach(System.out::println);
    }
}
```

`import module java.base;` cho phép dùng `List` và `Stream` từ các package được `java.base` export mà không cần từng import package/class. Đó là **tiện ích mã nguồn**, không thay `module-info.java`, không cấp quyền truy cập package private và có thể gây va chạm tên class khi import nhiều module. Khi bị ambiguous, thêm explicit single-type import.

### 3.4. Flexible constructor bodies (JEP 513)

Trong Java 25, có thể kiểm tra tham số **trước** lời gọi constructor cha:

```java
class BaseAccount {
    BaseAccount(String id) {
        System.out.println("Created " + id);
    }
}

class Account extends BaseAccount {
    Account(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        super(id.trim());
    }
}
```

Đây là cú pháp đã final. Các lệnh đặt trước `super(...)` phải tuân thủ giới hạn ngữ nghĩa của ngôn ngữ, chẳng hạn không được tùy tiện truy cập instance state `this` trước khi superclass constructor được gọi. Với code sản xuất, vẫn cân nhắc tạo factory/builder khi khởi tạo trở nên phức tạp.

### 3.5. Key Derivation Function API (JEP 510)

JDK 25 cung cấp API `javax.crypto.KDF` chính thức. Sử dụng với HKDF giúp suy ra khóa mục đích cụ thể từ nguồn key material có entropy đủ mạnh. Mẫu API minh họa (các biến `initialKeyMaterial`, `salt` và `info` phải được chuẩn bị theo thiết kế giao thức):

```java
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;
import java.security.spec.AlgorithmParameterSpec;

// Ví dụ nằm bên trong method, với các biến đầu vào đã được chuẩn bị:
KDF hkdf = KDF.getInstance("HKDF-SHA256");
AlgorithmParameterSpec params = HKDFParameterSpec.ofExtract()
        .addIKM(initialKeyMaterial)
        .addSalt(salt)
        .thenExpand(info, 32);
SecretKey aesKey = hkdf.deriveKey("AES", params);
```

API là **final** trong 25, không cần `--enable-preview`. Đừng tự chọn HKDF chỉ vì nó mới: lựa chọn thuật toán, ngữ cảnh `info`, độ dài khóa, key rotation và quản lý secret phải theo giao thức bảo mật đang sử dụng. **HKDF không phải hàm băm mật khẩu** để lưu mật khẩu người dùng.

### 3.6. AOT cache, JFR và GC: final không đồng nghĩa tự kích hoạt

JEP 514/515 giúp quy trình **AOT cache và profile** dễ dùng hơn để cải thiện startup/warmup. Chúng là khả năng JDK/HotSpot để **đo và tối ưu khởi động**, không thay thế AOT compilation hay tạo native executable. Khi đánh giá, cần đo cả startup time, warmup latency, throughput sau warmup, kích thước cache và khả năng tái sử dụng cache sau thay đổi classpath.

JEP 518/520 mở rộng công cụ Java Flight Recorder để quan sát sampling và method timing/tracing. Đây là các khả năng JFR đã được tích hợp chính thức; muốn có dữ liệu hữu ích vẫn cần cấu hình recording/events và đọc kết quả bằng `jfr` hoặc JDK Mission Control. Không bật truy vết từng method diện rộng trên production nếu chưa xác định overhead.

JEP 519/521 là thay đổi HotSpot GC/object layout. Khi chọn Compact Object Headers hoặc Generational Shenandoah, cần kiểm tra JVM flags/giá trị mặc định **của đúng bản JDK**; đừng lấy ví dụ flag của JDK 24 experimental rồi áp vào JDK 25 đã final hoặc JDK 27 có mặc định khác. Đo với workload thực tế trước khi thay đổi GC ở production.

## 4. Preview: áp dụng cờ ở cả compile và runtime

JEP preview của JDK 25 gồm:

- **JEP 470:** `PEMEncoder` và `PEMDecoder` — thử API thống nhất để chuyển đổi certificate, key và các đối tượng mật mã với PEM.
- **JEP 502:** `StableValue` — cấu trúc lưu dữ liệu khởi tạo một lần, cho phép JVM tối ưu như giá trị ổn định.
- **JEP 505:** `StructuredTaskScope` — tổ chức vòng đời các nhiệm vụ đồng thời, hủy và xử lý lỗi theo scope; trong JDK 25 đây vẫn là **fifth preview**.
- **JEP 507:** hỗ trợ primitive types trong pattern/`instanceof`/`switch`; JDK 25 là **third preview**.

Các API/cú pháp này không được coi là final chỉ vì đã xuất hiện ở một JDK phát hành chính thức. Ví dụ ngắn **riêng cho JDK 25**:

```java
// StablePreview25.java — JEP 502, preview API của JDK 25
public class StablePreview25 {
    public static void main(String[] args) {
        StableValue<String> value = StableValue.of();
        System.out.println(value.orElseSet(() -> "initialized once"));
    }
}
```

Biên dịch và chạy bằng **javac/java từ JDK 25**:

```bash
javac --release 25 --enable-preview StablePreview25.java
java --enable-preview StablePreview25
```

Nếu bỏ `--enable-preview`, compiler báo preview API không được bật; nếu compile đã bật nhưng runtime không bật, chương trình sử dụng preview có thể không chạy được. Không dùng `--release 21` hoặc `--release 24` để bật preview của JDK 25: compiler chỉ cho preview theo **release hiện hành**.

**Điểm cần chú ý tính thời sự:** `StableValue` của JDK 25 không nên được bê nguyên sang bản Java mới. Ở JDK 26/27, hướng thiết kế tiếp tục dưới tên **Lazy Constants** và API thay đổi. Vì vậy, ví dụ trên dùng để hiểu *preview lifecycle* trong 25; không là công thức lập trình lâu dài cho JDK 27. Khi muốn áp dụng cấu trúc lazy constant trong sản phẩm, hãy đọc đặc tả của JDK đích hoặc tiếp tục dùng các cơ chế `final`/khởi tạo an toàn hiện có nếu chưa muốn chấp nhận rủi ro preview.

### 4.1. Ví dụ Maven nếu dự án **cố ý** thử preview

Với `maven-compiler-plugin` và một project có `maven.compiler.release=25`, bật ở compiler:

```xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <compilerArgs>
                    <arg>--enable-preview</arg>
                </compilerArgs>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <argLine>--enable-preview</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Mẫu trên là **đoạn cấu hình tích hợp**, không phải `pom.xml` độc lập. Khi chạy ứng dụng ngoài test bằng `java -jar`, `spring-boot:run` hoặc container, truyền `--enable-preview` tới **JVM chạy ứng dụng** bằng cơ chế đúng cho launcher/plugin. Không mặc định rằng compiler flag được mang sang mọi process runtime.

### 4.2. Những điều preview không cam kết

- API có thể đổi tên, đổi signature, đổi package, tiếp tục preview hoặc bị loại trong bản sau.
- Thư viện được biên dịch phụ thuộc preview của **JDK 25** có thể phải **biên dịch lại** khi chuyển sang release khác.
- Việc build chạy với preview không đảm bảo công cụ phân tích mã, IDE, test runner và server runtime đã hỗ trợ.
- Vì vậy cần tài liệu hóa nơi sử dụng preview, giới hạn phạm vi ảnh hưởng, test khi nâng JDK và cách chuyển sang API final khi có.

## 5. Incubator: Vector API khác preview thế nào?

**JEP 508** là **Vector API (Tenth Incubator)** của JDK 25, nằm trong module **`jdk.incubator.vector`**. Mục tiêu là mô tả phép tính SIMD trên vector dữ liệu với kiểu API độc lập mức độ phần cứng. Compiler/JVM có thể sinh chỉ thị vector hiệu quả trên CPU phù hợp.

### 5.1. Ví dụ khai báo module

```java
// Vector25.java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class Vector25 {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void main(String[] args) {
        float[] input = new float[SPECIES.length()];
        float[] output = new float[input.length];

        for (int i = 0; i < input.length; i++) {
            input[i] = i + 1;
        }

        FloatVector vector = FloatVector.fromArray(SPECIES, input, 0);
        vector.mul(2.0f).intoArray(output, 0);
        System.out.println(java.util.Arrays.toString(output));
    }
}
```

Dùng JDK 25:

```bash
javac --add-modules jdk.incubator.vector Vector25.java
java --add-modules jdk.incubator.vector Vector25
```

Không cần `--enable-preview` **chỉ để sử dụng** Vector API. Có thể xuất hiện cảnh báo “using incubating module”, vì incubator có trạng thái thử nghiệm của API. Sau khi đổi JDK, cần kiểm tra module incubator còn tồn tại và API có thay đổi không. Tính đến JDK 27, Vector API vẫn ở vòng **12th incubator**, chưa phải final.

Dùng Vector API chỉ khi profile chỉ ra đoạn tính toán có thể vectorize và benchmark trên đúng CPU cần triển khai. Đối với code business thông thường, **đừng** thay mọi vòng lặp bằng vector; phụ thuộc vào incubator làm tăng chi phí nâng JDK.

## 6. Experimental: JFR CPU-Time Profiling (JEP 509)

JEP 509 thêm **CPU-time profiling** cho JFR trên **Linux**, sử dụng sự kiện `jdk.CPUTimeSample` để lấy mẫu CPU time, bao gồm cả trường hợp Java thread chạy trong native code. Đây là cơ chế phục vụ chẩn đoán hiệu năng, không phải API nghiệp vụ.

Đặc điểm cần nhớ:

1. Trong JDK 25, `jdk.CPUTimeSample` là **experimental JFR event** và **tắt theo mặc định**.
2. Nó chỉ được hỗ trợ trên **Linux** ở JDK 25; không hứa áp dụng cho mọi hệ điều hành/JVM vendor.
3. Không sử dụng `--enable-preview` hoặc `--add-modules jdk.incubator.vector` để bật JFR event.
4. Với riêng JEP 509, **không cần** `-XX:+UnlockExperimentalVMOptions`; chỉ bật event trong recording.
5. Đọc kết quả bằng `jfr print`, `jfr view` hoặc JDK Mission Control và đối chiếu với các số liệu CPU khác.

Ví dụ chạy ứng dụng `CpuWorkload` **trên Linux JDK 25**, với recording 30 giây:

```bash
java '-XX:StartFlightRecording=jdk.CPUTimeSample#enabled=true,duration=30s,filename=cpu-time.jfr' CpuWorkload
jfr view cpu-time-hot-methods cpu-time.jfr
```

`CpuWorkload` đại diện cho chương trình đã biên dịch và chạy đủ thời gian tạo sample. Nếu thoát trước 30 giây, cần cấu hình lưu recording phù hợp hoặc dùng lệnh `jcmd` khi tiến trình đang hoạt động. Có thể dùng `jfr print --events jdk.CPUTimeSample cpu-time.jfr` để xem từng event. Kết quả còn phụ thuộc JDK build, tải và quyền truy cập của tiến trình.

**Experimental không đồng nghĩa “có thể dùng như tính năng production ổn định”.** Hãy đo overhead, so sánh dữ liệu giữa nhiều lần chạy và kiểm tra hỗ trợ từ nhà cung cấp runtime trước khi đưa event vào quy trình giám sát lâu dài. Ngược lại, các cải tiến JFR **JEP 518** và **JEP 520** đã hoàn tất trong 25; chúng không cần gắn nhãn experimental chỉ vì cùng thuộc mảng JFR.

## 7. Bảng chọn cờ và hành vi lỗi

| Mục đích | Compile JDK 25 | Run JDK 25 | Điều không nên làm |
|---|---|---|---|
| `ScopedValue`, module import, compact source, flexible constructors, `KDF` | `javac --release 25` (hoặc chạy source file) | `java ...` | Thêm preview flag không cần thiết rồi hiểu lầm final feature là preview |
| Stable Values, Structured Concurrency, PEM API, primitive pattern **preview** | `javac --release 25 --enable-preview ...` | `java --enable-preview ...` | Bật chỉ một phía hoặc lấy preview code 25 để chạy JDK 27 |
| Vector API incubator | `javac --add-modules jdk.incubator.vector ...` | `java --add-modules jdk.incubator.vector ...` | Cho rằng Vector API đã final hoặc chỉ cần `--enable-preview` |
| JFR CPU-Time Profiling experimental | Compile ứng dụng như bình thường | Cấu hình `jdk.CPUTimeSample#enabled=true` trong JFR trên Linux | Dùng preview flag hoặc giả định mọi experimental event cần unlock JVM |
| AOT cache / Compact Headers / Generational Shenandoah | Compile code bình thường | JVM/cache/GC option phù hợp từng JDK/build | Nhầm “final” với “tính năng đã bật mặc định” |

### Thử phân loại tình huống

- IDE báo `StableValue is a preview API and is disabled by default`: đang dùng API **preview**, cần JDK 25 và flag đúng nếu tiếp tục thử nghiệm. Không sửa bằng cách import một `StableValue` từ package ngoài không liên quan.
- Compiler báo `package jdk.incubator.vector is not visible`: cần **`--add-modules jdk.incubator.vector`** và xác nhận JDK hiện tại còn module đó.
- `ScopedValue` code final cần `--enable-preview` mới compile được: kiểm tra bạn có thực dùng **JDK 25** và đang gọi **API signature của 25** không; không mặc định copy mã fourth preview từ JDK 24.
- Không có event `jdk.CPUTimeSample`: kiểm tra đang chạy Linux, đã bật event trong JFR và có recording đủ dài. Không suy luận `--enable-preview` sẽ sửa vấn đề.
- Trên JDK 27, `StableValue` không còn tên/sơ đồ như JDK 25: xem **Lazy Constants của JDK 27**, không sửa bằng cách ép `--release 25 --enable-preview` trên compiler mới.

## 8. Tính năng nào nên đưa vào sản phẩm?

Giả sử nhóm phát triển ứng dụng Java đã có CI và chuẩn bị từ Java 21/25 tiến lên các JDK mới.

| Nhu cầu | Lựa chọn nên ưu tiên | Điều kiện quyết định |
|---|---|---|
| Chương trình nhỏ, ví dụ đào tạo, công cụ kiểm tra nhanh | Compact source files / `IO` final | Dùng JDK 25+; không ép vào kiến trúc dự án lớn |
| Truyền ngữ cảnh read-only trong call scope | `ScopedValue` final | Kiểm tra propagation semantics khi dùng nhiều thread |
| Rút ngắn import cho chương trình/bài thực hành | Module import final | Tránh import quá rộng gây ambiguous trong code lớn |
| Khởi tạo object với validation trước constructor cha | Flexible constructor bodies final | Giữ nguyên bất biến và tránh truy cập instance state quá sớm |
| Dẫn xuất khóa cho giao thức hiện đại | KDF API final | Có threat model, kiểm tra key material, salt/info, thuật toán |
| Đánh giá hiệu năng khởi động | AOT cache/profiling final | Đo với đúng classpath/workload; có chiến lược invalidate cache |
| Chẩn đoán CPU/method runtime | JFR final features 518/520 | Có recording policy và giới hạn overhead |
| Xử lý dữ liệu SIMD cực lớn | Vector API incubator trong thử nghiệm | Benchmark chứng minh lợi ích, chấp nhận nguy cơ sửa API |
| Thử nghiệm mô hình structured concurrency/lazy constants | Preview trong nhánh thử nghiệm | Sẵn sàng thay đổi theo JDK 26/27 |
| Xem CPU-time samples trên Linux | JFR 509 experimental | Dùng công cụ chẩn đoán có kiểm soát, xác minh hỗ trợ vendor |

Hãy ưu tiên **final APIs** cho mã bảo trì nhiều năm. Preview/incubator/experimental vẫn hữu ích để học và đánh giá lộ trình; sự tồn tại của chúng giúp nhóm chuẩn bị sớm, nhưng **không phải cam kết** về API hay kết quả benchmark.

## 9. Checklist nâng cấp JDK 25 và giữ tính hiện thời

1. **Xác nhận JDK thật sự được sử dụng:** `java -version`, `javac -version`, cấu hình IDE, Maven/Gradle toolchain, Docker base image và CI runner.
2. **Chốt JDK đích:** Nếu project chọn 25 thì dùng bảng trạng thái **JDK 25**; nếu chuyển lên JDK 27 thì đọc tài liệu **JDK 27** cho mọi preview/incubator. Một nhánh code dùng preview của 25 không phải artifact “portable” giữa các đời JDK.
3. **Kiểm tra classfile/tooling:** Java 25 xuất class file **major version 69**; nâng plugin build, bytecode scanner, code coverage, profiler và test tools nếu chúng chưa đọc được classfile mới.
4. **Phân loại dependencies và cờ:** xác định phần nào dùng `--enable-preview`, `--add-modules`, experimental JFR event hoặc HotSpot option. Không để các flags của môi trường dev vô tình rơi rụng ở runtime/container.
5. **Đánh giá lợi ích thật:** chạy test chức năng và bảo mật, đo startup/AOT warmup, hiệu năng GC, memory footprint, JFR overhead với workload có kiểm soát. Không suy ra cải thiện từ tên JEP.
6. **Làm rõ nền tảng:** JDK 25 đã loại bỏ port 32-bit x86; kiểm tra OS, kiến trúc CPU và hỗ trợ vendor khi chuyển JDK.
7. **Quản lý thử nghiệm:** giới hạn preview/incubator/experimental trong module/nhánh thử nghiệm và có test biên dịch **khi nâng JDK**. Nếu muốn dùng production, tạo quyết định kỹ thuật với rủi ro tương thích và rollback.
8. **Đối chiếu trạng thái mới:** tính đến **27/11/2026**, JDK 27 đã GA. Đặc biệt **JEP 502 Stable Values** ở 25 đã phát triển thành **Lazy Constants**; không dùng tài liệu API cũ cho version mới.

### Một bài tập tổng kết

Cho các trường hợp sau và trả lời **trạng thái trong JDK 25**, cờ cần thiết và quyết định triển khai:

| Trường hợp | Phân loại đúng trong 25 | Hành động |
|---|---|---|
| Dùng `ScopedValue.where(...).run(...)` để truyền context | Final | Chạy bình thường với JDK 25, test phạm vi binding |
| Dùng `PEMEncoder` trong một prototype công cụ cấp chứng chỉ | Preview | Bật preview compile/runtime; kiểm tra API khi nâng JDK |
| Tối ưu phép cộng mảng bằng `FloatVector` | Incubator | Thêm module incubator khi compile/run, benchmark |
| Lấy mẫu CPU-time với `jdk.CPUTimeSample` trên Linux | Experimental | Bật JFR event cho recording, đánh giá overhead |
| Viết `void main() { IO.println("Hi"); }` | Final | Chạy file nguồn bằng JDK 25, không cần preview |
| Bật Compact Object Headers để giảm overhead | Final nhưng phụ thuộc cấu hình JVM | Đo performance, bật/tuning theo đúng JDK 25 |
| Copy code `StableValue` của 25 sang JDK 27 | Không được xem là API final/ổn định | Đọc thiết kế Lazy Constants ở JDK 27, cập nhật code |

**Đạt yêu cầu khi:** người học giải thích được **tình trạng của tính năng**, **cờ kích hoạt**, **rủi ro khi đổi JDK** và **khi nào nên áp dụng**. Không học thuộc “cứ feature mới là preview” hoặc “cứ JDK LTS là tất cả final”.

## 10. Nguồn chính thức để tra cứu

Ưu tiên tài liệu **khóa theo đúng phiên bản** và thông báo phát hành; tránh sử dụng blog mô tả bản preview cũ như một API còn nguyên vẹn:

1. [JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html) — danh sách JEP và trạng thái của **JDK 25**, phát hành 16/09/2025.
2. [Java SE 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html) — ngôn ngữ, thư viện, JFR, nâng cấp runtime và removal.
3. [Java SE 25 — Preview Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html) — cách bật `--enable-preview` và giới hạn tương thích phiên bản.
4. [Java SE 25 — API Preview List](https://docs.oracle.com/en/java/javase/25/docs/api/preview-list.html) — xác nhận `StableValue`, `StructuredTaskScope` và PEM API là preview.
5. [Java SE 25 — Compact Source Files](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html), [Module Imports](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html) — cú pháp **final**.
6. [Java SE 25 — ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html) — cú pháp và semantics **final**.
7. [JEP 510 / Java 25 Security Enhancements](https://inside.java/2025/09/24/jdk25-security-enhancements/) — KDF final và PEM preview.
8. [What's new for JFR in JDK 25](https://inside.java/2025/06/03/new-jfr-jdk25/) — JFR CPU-time experimental, JFR method timing/tracing.
9. [Java SE 27 — Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) và [Significant Changes JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — đối chiếu tình trạng hiện thời của preview/incubator khi nâng quá JDK 25.
10. [JEP Index của OpenJDK](https://openjdk.org/jeps/0) và [JDK 25 Project](https://openjdk.org/projects/jdk/25/) — danh sách JEP gốc để kiểm tra lịch sử tiến hóa.

**Nguyên tắc cuối:** khi mô tả Java 25, luôn phân loại **theo trạng thái của chính JDK 25**; khi thiết kế code hôm nay, quyết định dựa trên **JDK thực sự định chạy**. Những gì đã final trong 25 là nền tảng tốt cho code hiện đại; những gì còn preview/incubator/experimental là các lựa chọn thử nghiệm cần bảo vệ bằng flags, tests và chiến lược nâng cấp.
