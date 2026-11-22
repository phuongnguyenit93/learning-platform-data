# Chi phí đọc JAR, verification, linking và initialization trong Java ClassLoader

Khi một ứng dụng Java gặp **độ trễ ở lần gọi đầu tiên (cold path)**, nguyên nhân có thể nằm ở **tìm và đọc class từ JAR**, **nạp class**, **bytecode verification**, **linking/resolution**, **chạy static initializer**, hoặc ở **JIT compilation, nạp dependency, I/O và framework code** xảy ra sau đó. Đây là các khoản chi phí **khác nhau** về cơ chế, thời điểm và cách tối ưu.

**Điều quan trọng nhất:** Không được coi mọi thời gian ở `ClassLoader.loadClass(...)` là thời gian **đọc JAR**, và cũng không được coi mọi độ trễ khi gọi method đầu tiên là **verification**. Java cho phép JVM thực hiện một số bước linking/resolution **sớm hoặc muộn** miễn tuân thủ Java Language Specification (JLS) và Java Virtual Machine Specification (JVMS). Muốn chẩn đoán đúng cần hiểu ranh giới ngữ nghĩa, quan sát class loading/initialization và đo workload thực.

Bài học sử dụng **Java 17+**, phân biệt code chạy trên classpath, trong JAR và qua `URLClassLoader`. Với named modules/JPMS, JVM có thêm bước module resolution và quy tắc access, nhưng mô hình nền về load → link → initialize vẫn là điểm xuất phát.

## 1. Bản đồ vòng đời và điểm có thể phát sinh chi phí

```text
Lần đầu chương trình cần một class
          |
          v
[1] Chọn ClassLoader / delegation / tra class đã loaded
          |
          v
[2] Tìm bytecode của class
    - tìm entry trong JAR/directory/module
    - đọc bytes, có thể giải nén ZIP/JAR
    - có thể kiểm tra JAR signer/metadata
          |
          v
[3] Loading / tạo Class<?> và metadata của runtime type
          |
          v
[4] Linking
    ├── Verification: kiểm tra class/bytecode hợp lệ
    ├── Preparation: chuẩn bị storage, static mặc định
    └── Resolution: giải symbolic references (có thể lazy)
          |
          v
[5] Initialization khi JVM yêu cầu
    - khởi tạo superclass/những superinterfaces liên quan
    - chạy static field initializers và static blocks (<clinit>)
          |
          v
[6] Thực thi method/constructor
    - bytecode interpreter/JIT
    - I/O, network, DB, framework initialization nếu có
```

Sơ đồ chỉ giúp **phân loại hoạt động**, không khẳng định mỗi bước luôn diễn ra tuần tự, một lần và tách biệt được bằng một timer. Verification/preparation phải hoàn thành trước initialization, nhưng symbolic reference resolution được JVM phép thực hiện tại những thời điểm phù hợp, kể cả sau khi class đã initialized.

Một số hoạt động còn có thể xảy ra **đệ quy**: nạp class A dẫn tới nạp B, kiểm tra B, rồi nạp C; static initializer của A lại đọc config và mở mạng. Một phép đo “load A mất 200 ms” có thể bao gồm hành vi của nhiều dependencies/callbacks, không chỉ chính file `A.class`.

## 2. Các loại chi phí và cách nhìn đúng

| Giai đoạn | Công việc có thể phát sinh | Dấu hiệu thường thấy | Hiểu nhầm cần tránh |
|---|---|---|---|
| **Class lookup** | `findLoadedClass`, parent delegation, classpath/JAR/module search | Nhiều classpath entries, plugin loaders, lớp chưa có trong cache | “Mỗi `loadClass` đều đọc lại JAR” |
| **Đọc JAR/ZIP** | Mở archive, tìm central directory/entry, đọc/giải nén bytes | Cold filesystem/cache, archive lớn, nhiều class loads | “JAR càng lớn luôn càng chậm theo tỷ lệ thuận” |
| **JAR signature/metadata** | Xử lý manifest, signer/certificates theo cách loader/JAR verifier làm việc | Signed JAR, nhiều entries, security/package checks | “JAR signature verification = bytecode verification” |
| **Class definition** | Tạo runtime type, metadata, constant pool, quan hệ loader/module/package | Metaspace và class count tăng | “Gọi `Class.forName` luôn định nghĩa class mới” |
| **Bytecode verification** | Kiểm tra cấu trúc, type correctness, stack/control flow | `VerifyError` hoặc thời gian class linking | “Tắt verifier là tối ưu production nên làm” |
| **Preparation** | Tạo static fields mặc định, method tables/VM structures | Bắt đầu có metadata/static storage | “Preparation chạy `static {}`” |
| **Resolution** | Tra symbolic references tới class/field/method và kiểm tra hợp lệ | First-use latency, `NoSuchMethodError` khi liên kết | “Mọi reference đều resolve hết khi load” |
| **Initialization** | Chạy `<clinit>`, static field expressions, có thể I/O/locks | Log từ static block, first-use spike | “`loadClass` luôn chạy static block” |
| **JIT/runtime warmup** | Interpreter profiling, compilation, GC, caches | Sau nhiều lượt chạy nhanh hơn | “Lượt thứ hai nhanh hoàn toàn do class cache” |

Các giai đoạn có thể chồng lấn trong cùng một lần thực thi. Thông số microbenchmark đơn lẻ không đủ chia tuyệt đối tổng latency thành từng phần.

## 3. Chi phí tìm và đọc lớp từ JAR

### 3.1. JAR là định dạng ZIP có cấu trúc tra cứu

JAR chuẩn về cơ bản là ZIP archive với manifest/metadata và các entries, ví dụ:

```text
plugins/greeter.jar
├── META-INF/MANIFEST.MF
├── demo/Plugin.class
├── demo/settings.txt
└── demo/internal/Helper.class
```

Khi `URLClassLoader` tìm `demo.Plugin`, nó cần tìm resource entry `demo/Plugin.class` (hoặc theo chính sách nguồn phù hợp), mở/đọc bytes và định nghĩa class. Công việc có thể gồm:

1. Chọn **loader đang chịu trách nhiệm** và kiểm tra parent/đã nạp.
2. Tìm JAR/URL chứa class; có thể dò qua nhiều URLs khi class không có ở nguồn đầu.
3. Đọc thông tin ZIP central directory/entry metadata theo implementation.
4. Đọc dữ liệu entry; nếu ZIP entry dùng **DEFLATED** thì phải giải nén.
5. Áp dụng xử lý manifest, package sealing, signer/certificate khi liên quan.
6. Đưa bytecode vào cơ chế class definition/linking của JVM.

**Không có quy tắc “JAR 100 MB nghĩa là phải giải nén toàn bộ 100 MB khi cần một class”.** Loader thường truy cập entry phù hợp, và OS/JDK có caching. Mức độ I/O và decompress phụ thuộc implementation, compression, thứ tự tìm, cache và cách đóng gói.

### 3.2. Classpath dài không đồng nghĩa chậm tuyến tính với mỗi lần gọi

Classpath có nhiều JAR khiến việc **tìm class chưa biết ở JAR nào** có thể cần xem xét nhiều nguồn. Nhưng:

- JVM/loader duy trì kết quả đã load theo runtime class identity.
- ZIP index, file handles, archive reader và filesystem page cache có thể được tái sử dụng.
- Với parent delegation, một class nền tảng có thể được trả ngay từ parent mà **không cần quét plugin JAR**.
- Custom class loader có thể có cache/index/lookup policy khác `URLClassLoader`.
- Phần lớn ứng dụng chỉ nạp **một tập con** trong tổng class entries của mọi dependencies.

Vì vậy **số lượng JAR** và **tổng số bytes JAR** là chỉ báo cần khảo sát, không phải phép tính thời gian tin cậy.

### 3.3. Cold filesystem cache và warm cache

Đọc JAR lần đầu sau khi máy khởi động/deploy có thể chạm storage thật. Các lần sau có thể được phục vụ bởi **OS page cache**, cache ZIP/JAR của runtime hoặc filesystem cache. Ngược lại, disk/network filesystem chậm, antivirus/file scanning, storage cạnh tranh hoặc archive từ nguồn xa có thể khiến chi phí tăng mạnh.

Một phép so sánh trên **cùng JVM** còn chịu class-loader cache. Một phép so sánh trên **JVM mới** có thể vẫn tận dụng OS page cache. Vì vậy phải định nghĩa rõ “cold” là:

- JVM mới hay JVM đã chạy?
- Loader mới hay loader đang tái sử dụng?
- Process mới nhưng OS page cache còn nóng?
- JIT đã warm chưa?
- Framework/plugin đã khởi tạo chưa?
- JAR ở local SSD hay network mount?

Đừng gọi tất cả những trường hợp này chung là “cold start” rồi so sánh số đo.

### 3.4. JAR signing khác bytecode verification

Khi sử dụng **signed JAR**, JAR verification/signature processing có thể kiểm tra digest, signer metadata và certificate associations của entries tùy cách truy cập/loader. Công việc này khác với **JVM bytecode verification**, vốn xác minh cấu trúc class file và tính an toàn về kiểu, stack, branch, instruction.

| Hành động | Mục tiêu |
|---|---|
| Xác minh JAR entry/signature | Nội dung entry, signer metadata/chữ ký phù hợp với quy tắc JAR |
| Package signer consistency | Các classes trong **cùng runtime package/defining loader** có certificate set nhất quán |
| Bytecode verification | Instructions, type safety, stack/control flow/class file hợp lệ |
| Authorization/trust | Ứng dụng/tổ chức có quyết định tin cậy nguồn JAR không — là câu hỏi riêng |

**Không bỏ kiểm tra chữ ký hay bytecode safety chỉ để tăng tốc startup.** Các kiểm tra có mục tiêu khác nhau; tối ưu thực tế nên bắt đầu từ dependency scope, I/O và initialization code.

## 4. Loading: lấy bytecode và tạo runtime class

JLS `12.2 và JVMS `5.3 mô tả **loading**: tìm binary representation của class/interface và tạo runtime class tương ứng.

`ClassLoader.loadClass("demo.Plugin")` sử dụng **binary name**, không phải đường `demo/Plugin.class`. Parent-first implementation thông thường:

```text
loadClass(name)
  |
  +-- class đã được loaded/ghi nhận? -> trả Class<?>
  |
  +-- thử parent loader trước
  |       |
  |       +-- parent có class -> trả class của parent
  |
  +-- findClass(name) ở loader này
          |
          +-- tìm class bytes và defineClass(...)
```

Class identity:

```text
(binary name, defining loader)
```

Gọi `loadClass` lần nữa trên cùng loader đối với một class đã có thường trả lại cùng `Class<?>`; không lặp lại `defineClass`, bytecode verification và static initialization như đang nạp một runtime class mới.

**Nhưng chi phí repeat lookup không bằng 0.** Vẫn có method call, kiểm tra lookup/locking tùy loader, và tác động JIT/runtime. Loader custom có thể làm I/O/logic thừa trước khi cache lookup nếu code viết sai.

### Loader mới tạo “cold class” mới

Hai loader khác nhau có thể định nghĩa cùng binary name thành **hai runtime classes riêng**. Với plugin reload:

```text
LoaderV1 -> demo.Plugin (runtime class V1)
LoaderV2 -> demo.Plugin (runtime class V2)
```

V2 phải thực hiện các công việc load/link/init cho runtime type của nó theo những điều kiện tương ứng; không thể coi V2 “warm” chỉ vì V1 đã được nạp trước đó trong một defining loader khác. Một số caches cấp JVM/OS vẫn có thể giúp nhưng không thể dùng lại tất cả runtime type identity/state.

Tạo hàng trăm class loaders để “song song hóa startup” chưa chắc hiệu quả: có thêm class metadata, trùng dependencies, I/O contention, verification/initialization lặp lại và áp lực bộ nhớ.

## 5. Verification: JVM kiểm tra bytecode trước khi thực thi

Verification là một phần của **linking**. JVM kiểm tra class representation/bytecode có tuân thủ các quy tắc của Java Virtual Machine không, ví dụ:

- Class file đúng cấu trúc, constant pool và metadata hợp lệ.
- Instruction opcode và operand có định dạng hợp lệ.
- Branch targets nằm ở ranh giới instruction hợp lệ.
- Operand stack/local variables có types thích hợp trong các nhánh control flow.
- Method descriptor, return operation và một số quan hệ kiểu được kiểm tra.
- Các thông tin verification như `StackMapTable` có cấu trúc/ý nghĩa phù hợp khi cần.

**Chi phí verification** phụ thuộc kích thước/độ phức tạp code, số lượng methods/classes, dependency loading và các quyết định của JVM implementation. Nó không nhất thiết tỷ lệ với **dung lượng compressed JAR**.

Đặc biệt, class loader tìm bytes thành công **không bảo đảm** bytecode hợp lệ. JVM có thể ném:

- `ClassFormatError`: binary class file sai cấu trúc.
- `VerifyError`: bytecode không qua type/control-flow checks.
- `UnsupportedClassVersionError`: class-file version mới hơn runtime hỗ trợ.
- Các `LinkageError` khác nếu quan hệ runtime types/references không hợp lệ.

**Không dùng các tùy chọn tắt/né bytecode verification như một “tối ưu mặc định”.** Chúng có thể không được hỗ trợ hoặc có ngữ nghĩa thay đổi theo JDK, làm suy yếu invariant JVM. Nếu verification xuất hiện đáng kể trong profile, hãy đo lượng class/method mới được nạp và lý do codegen/transform pipeline sinh nhiều lớp.

## 6. Linking: preparation và resolution không phải initialization

**Linking** gồm verification, preparation và resolution của symbolic references. Nhưng resolution có thể thực hiện **eager hoặc lazy** theo JVM, không phải lúc nào cũng hoàn tất toàn bộ trước khi class được dùng.

### 6.1. Preparation

Preparation tạo storage cho static fields và đặt **giá trị mặc định**, đồng thời VM có thể chuẩn bị các cấu trúc nội bộ phục vụ method dispatch. Ví dụ:

```java
class State {
    static int count = compute();
    static Object cache = new Object();

    static int compute() { return 7; }
}
```

Đây là **snippet minh họa**, không có `main` riêng.

Theo mô hình JLS, preparation có trách nhiệm chuẩn bị static storage; assignment `count = compute()` và `new Object()` thuộc **initialization**, không phải preparation. JVM có quyền tối ưu/chuẩn bị thêm metadata, nhưng không được làm thay đổi Java observable semantics.

Một trường hợp đặc biệt là **constant variables** theo JLS (như `static final int LIMIT = 10;`): compiler/JVM có xử lý giá trị compile-time constant riêng. Không được suy diễn rằng mọi `static final` đều là constant variable; ví dụ `static final Integer BOXED = 10;` hoặc `static final String ID = fetch();` phải tính trong initialization.

### 6.2. Resolution

Bytecode có symbolic references đến:

- Class/interface khác.
- Field và method của class/interface khác.
- Method handles, dynamically-computed constants, invokedynamic call sites khi thích hợp.

Resolution thay/kiểm tra references symbolic để runtime có thể dùng chúng theo đúng types/access rules. Ví dụ class A có method gọi `helper.Missing.run()`; JVM có thể **chưa resolve** method/class liên quan cho đến đường code yêu cầu.

Sơ đồ:

```text
A loaded
  |
  +-- A symbolic reference -> B.method
          |
          +-- JVM có thể resolve trước hoặc tại lần dùng
          +-- kiểm tra B/lookup/access/descriptor
          +-- dùng kết quả resolve theo runtime implementation
```

**Sai lầm:** “Lời gọi `loadClass("A")` thành công thì mọi method/dependency của A chắc chắn usable”. Một số lỗi như `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` hoặc `NoClassDefFoundError` có thể chỉ xuất hiện khi code path cần reference ấy.

JLS `12.3 cho phép implementation linh hoạt về thời điểm resolution nhưng yêu cầu errors xuất hiện ở thời điểm chương trình có thể trực tiếp hoặc gián tiếp yêu cầu linkage.

### 6.3. Linking có thể phân tán qua thời gian

Một startup profiler không nên cố gắn toàn bộ **resolution cost** vào giai đoạn `Class.forName` đầu tiên. Một phần có thể phát sinh trong later invocations, reflection, lambda bootstrap hoặc dynamic linkage. Hãy đo cả **cold first request** và **steady-state** nếu mục tiêu là latency dịch vụ.

## 7. Initialization: nơi static code có thể làm startup cực chậm

Initialization thực thi **class variable initializers** và **static initializer blocks** theo quy tắc JLS `12.4. Đây là **code ứng dụng tùy ý**: có thể tạo cache, parse configuration, mở database connection, đọc JAR resources, khởi động thread hoặc chờ lock.

Ví dụ:

```java
public final class ExpensiveConfig {
    static final java.util.Map<String, String> SETTINGS = loadAll();

    private static java.util.Map<String, String> loadAll() {
        // Đọc file, parse JSON, tra môi trường, v.v.
        return java.util.Map.of("mode", "default");
    }
}
```

Snippet biên dịch được trong một file tên `ExpensiveConfig.java`, nhưng **không có `main`**; các comment mô tả công việc thực tế có thể phát sinh. Thời gian class initialization có thể lớn nếu `loadAll()` thực hiện I/O/network.

**Phân biệt quan trọng:**

- `loader.loadClass("demo.Plugin")` **không chủ động yêu cầu initialization** theo contract thông thường.
- `Class.forName("demo.Plugin", false, loader)` tìm và liên kết class theo contract, **không yêu cầu initialization**.
- `Class.forName("demo.Plugin", true, loader)` **yêu cầu initialization** nếu class chưa được initialized.
- Tạo instance của class hoặc gọi static method/ghi static field có thể kích hoạt initialization.
- Đọc **compile-time constant variable** qua tên class không nhất thiết kích hoạt initialization của declaring class.
- Lấy class literal `SomeClass.class` thường **không tự kích hoạt initialization** của class đó.
- Các đường reflection/method handles/initialization dependencies có quy tắc riêng; đọc JavaDoc/JLS cụ thể.

Không nên khẳng định `loadClass` chỉ làm I/O rồi “không link gì” — chỉ có thể khẳng định `loadClass` **không tự yêu cầu chạy `<clinit>`**.

### 7.1. Initialization chạy một lần trên mỗi runtime class

Trong một JVM, một runtime class cụ thể được initialized theo thủ tục JVM bảo đảm đồng bộ. Nếu hai threads cùng yêu cầu khởi tạo class chưa initialized, có thể có **thời gian chờ initialization lock**. Static initializer có I/O chậm hoặc lock/dependency cycle có thể khuếch đại latency và tạo deadlock ngoài ý muốn.

Tạo loader thế hệ mới cho cùng binary name tạo **runtime class mới** với initialization độc lập. Việc plugin reload nhiều lần có thể kích hoạt lại static setup/I/O/allocations trên mỗi thế hệ.

### 7.2. Failure có thể biến thành class unusable

Nếu static initializer ném exception, JVM có thể ném `ExceptionInInitializerError` ở lần đầu. Runtime class bị ghi nhận ở **erroneous state**, và các lần sử dụng tiếp theo có thể ném `NoClassDefFoundError` với thông tin initialization thất bại. Không “retry” thành công chỉ bằng cách gọi `Class.forName` lại trên **cùng runtime class/defining loader**.

Với plugin cần retry logic, hãy tách I/O hoặc network initialization sang lifecycle method có quản lý trạng thái và error handling rõ, không giấu tất cả trong `static {}`.

## 8. Demo Java 17+: nạp từ JAR và quan sát load so với initialize

Demo tạo:

- Một class `demo.Plugin` nằm **chỉ trong plugin.jar**, không nằm trên runtime classpath của host.
- Một resource `demo/settings.txt` trong cùng JAR.
- Một `URLClassLoader` tạo ở host.
- Các bước đọc JAR resource, load class, `Class.forName(..., false, loader)` rồi yêu cầu initialize.

**Mục đích:** Minh họa **thứ tự quan sát được** bằng stdout và chứng minh `<clinit>` không chạy ngay khi loader trả `Class<?>`. Ví dụ này **không cố gán thời gian mỗi bước chính xác**.

### 8.1. Cấu trúc thư mục

```text
phase-demo/
├── src/
│   ├── plugin/demo/Plugin.java
│   └── host/host/PhaseProbe.java
├── out/
│   ├── plugin/demo/settings.txt
│   └── host/
└── plugin.jar
```

### 8.2. Code plugin

Tệp **`src/plugin/demo/Plugin.java`**:

```java
package demo;

public final class Plugin {
    static {
        System.out.println("PLUGIN <clinit>");
    }

    public static String greet() {
        return "hello";
    }
}
```

Chuỗi `PLUGIN <clinit>` là **dòng do static block của ứng dụng in**, không phải VM log. Chúng ta dùng nó để nhận diện lúc initialization code được thực thi.

### 8.3. Code host

Tệp **`src/host/host/PhaseProbe.java`**:

```java
package host;

import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class PhaseProbe {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of(args[0]).toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {jar},
                PhaseProbe.class.getClassLoader())) {

            System.out.println("loader created");

            try (InputStream in = loader.getResourceAsStream(
                    "demo/settings.txt")) {
                if (in == null) {
                    throw new IllegalStateException(
                            "missing resource");
                }
                System.out.println("resource: "
                        + new String(in.readAllBytes(),
                                StandardCharsets.UTF_8).trim());
            }

            Class<?> type = loader.loadClass("demo.Plugin");

            System.out.println("loaded by child: "
                    + (type.getClassLoader() == loader));
            System.out.println("after loadClass");

            System.out.println("forName(false) same: "
                    + (Class.forName(
                            "demo.Plugin", false, loader) == type));
            System.out.println("before initialization request");

            Class.forName("demo.Plugin", true, loader);

            System.out.println("after initialization request");
            System.out.println("call: "
                    + type.getMethod("greet").invoke(null));

            System.out.println("cached type: "
                    + (loader.loadClass("demo.Plugin") == type));
        }
    }
}
```

**Giải thích cơ chế:**

1. Tạo `URLClassLoader` chưa có nghĩa đã nạp `demo.Plugin` hoặc đọc toàn bộ JAR.
2. `getResourceAsStream("demo/settings.txt")` đọc một resource trong JAR mà không cần initialize `demo.Plugin`.
3. `loadClass("demo.Plugin")` tìm và nạp class, nhưng không yêu cầu chạy static block của `Plugin`.
4. `Class.forName(..., false, loader)` trả cùng runtime class, vẫn không chạy `<clinit>`.
5. `Class.forName(..., true, loader)` yêu cầu initialization, và static block in dòng `PLUGIN <clinit>`.
6. Gọi `greet` sau đó dùng class đã initialized; lookup cuối trả đúng cùng đối tượng `Class<?>`.
7. `try-with-resources` đóng loader/file handles khi scope kết thúc; không phải class unload ngay lập tức.

### 8.4. Build/run trên Linux, macOS hoặc Git Bash

Từ thư mục `phase-demo`:

```bash
mkdir -p out/plugin/demo out/host

javac --release 17 -d out/plugin \
  src/plugin/demo/Plugin.java

javac --release 17 -d out/host \
  src/host/host/PhaseProbe.java

printf 'mode=fast\n' > out/plugin/demo/settings.txt

jar --create --file plugin.jar -C out/plugin .

java -cp out/host host.PhaseProbe plugin.jar
```

**Không thêm `plugin.jar` vào `-cp` của host**, vì mục đích là để `URLClassLoader` con **thực sự định nghĩa plugin class**. `Path.of(args[0]).toUri().toURL()` chuyển đường JAR từ command argument thành URL để loader mở.

### 8.5. Build/run trên PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/plugin/demo, out/host | Out-Null

javac --release 17 -d out/plugin src/plugin/demo/Plugin.java
javac --release 17 -d out/host src/host/host/PhaseProbe.java

[System.IO.File]::WriteAllText(
    "out/plugin/demo/settings.txt",
    "mode=fast",
    [System.Text.UTF8Encoding]::new($false))

jar --create --file plugin.jar -C out/plugin .

java -cp out/host host.PhaseProbe plugin.jar
```

### 8.6. Kết quả đã kiểm chứng

Ví dụ được **biên dịch với `javac --release 17`** và chạy thành công trên **OpenJDK 24**; stdout chính xác:

```text
loader created
resource: mode=fast
loaded by child: true
after loadClass
forName(false) same: true
before initialization request
PLUGIN <clinit>
after initialization request
call: hello
cached type: true
```

Kết quả cho thấy:

- `loaded by child: true` xác nhận defining loader plugin không phải host loader.
- Dòng `PLUGIN <clinit>` chỉ xuất hiện **sau** `before initialization request` và **trước** `after initialization request`.
- Không có `PLUGIN <clinit>` mới khi gọi static method hay tra lại class, vì runtime class đã initialized.
- Việc `loader.getResourceAsStream` tìm đúng entry **không chứng minh** bytecode plugin đã được verify/initialized ngay lúc đọc resource.

**Không suy luận quá mức:** Stdout không tiết lộ chính xác thời điểm JVM verify từng method hay resolve từng reference. JLS cho phép thời điểm linking linh hoạt, vì vậy muốn khảo sát chi tiết phải dùng JVM logging/profiler.

## 9. Quan sát class load, verification và initialization bằng JVM logging

Trên HotSpot/OpenJDK Java 17+, **unified logging** giúp quan sát các sự kiện class loading/initialization. Có thể chạy lại demo với:

```bash
java '-Xlog:class+load=info,class+init=info' \
  -cp out/host host.PhaseProbe plugin.jar
```

PowerShell (một dòng):

```powershell
java "-Xlog:class+load=info,class+init=info" -cp out/host host.PhaseProbe plugin.jar
```

Lệnh đã được kiểm tra trên OpenJDK 24; log JVM chứa các dòng tương tự:

```text
[...][info][class,load] demo.Plugin source: file:/.../plugin.jar
[...][info][class,init] Start class verification for: demo.Plugin
[...][info][class,init] End class verification for: demo.Plugin
[...][info][class,init] ... Initializing 'demo/Plugin' ... by thread "main"
```

Các dấu `[...]` và đường `file:/.../plugin.jar` là **ký hiệu rút gọn**: timestamp, địa chỉ, thread, vị trí JAR và thứ tự log phụ thuộc JVM, OS, tùy chọn logging và những classes khác nạp trong lúc chạy. Đây là **dạng log minh họa từ phép kiểm thử**, không phải stdout cố định để assert.

Khi cần ít log hơn, ghi ra file rồi lọc theo tên class:

```bash
java '-Xlog:class+load=info,class+init=info:file=classes.log' \
  -cp out/host host.PhaseProbe plugin.jar
```

Tùy JVM vendor/phiên bản, tag và mức độ chi tiết có thể khác. Kiểm tra những log tags JVM hỗ trợ bằng:

```bash
java -Xlog:help
```

**Logging cũng tiêu tốn thời gian.** Không đo startup latency production rồi kết luận “bật verbose logs khiến verification chậm N%” nếu chưa tách overhead ghi log và I/O của chính công cụ đo.

### 9.1. Log không phải stopwatch cho từng bước

`[class,load]` báo sự kiện lớp được nạp theo mức logging, nhưng không trực tiếp cho phép trừ timestamp và khẳng định phần chênh lệch là **I/O JAR thuần túy**. Khoảng giữa `class,load` và `class,init` còn có scheduling, other class loading, linking, application code, safepoints hoặc tool overhead.

`-Xlog:class+init` cho nhiều sự kiện về verification/initialization nhưng **không biến mọi hoạt động linking thành một biểu đồ nhân quả đầy đủ**. Cần công cụ kết hợp nếu mục tiêu là truy tìm bottleneck trong môi trường thực.

## 10. Tại sao phép đo một lần với System.nanoTime dễ gây nhầm?

Một đoạn code có thể đo wall-clock elapsed (thực chất là elapsed monotonic time) của một thao tác:

```java
long t0 = System.nanoTime();
Class<?> type = loader.loadClass("demo.Plugin");
long elapsedNs = System.nanoTime() - t0;

System.out.println("loadClass elapsed ns: " + elapsedNs);
```

Đây là **snippet minh họa trong method** với biến `loader` đã có; không phải ứng dụng độc lập. Số in ra **thay đổi mỗi lần chạy** và không đại diện cho “chi phí chỉ đọc bytes của plugin.jar”.

Tại sao?

- `loadClass` có thể ủy quyền parent, tìm JAR, nạp dependencies và thực hiện một phần linking theo JVM.
- Scheduling, GC, OS page cache, CPU frequency scaling và I/O cạnh tranh thay đổi elapsed time.
- `System.nanoTime` đo thời gian trải qua giữa hai thời điểm, **không gán nhãn nguyên nhân**.
- Đo lần đầu và lần thứ hai trên **cùng loader** là so sánh **class chưa nạp** với **class đã nạp**, hai workload khác nhau.
- Nếu đo nhiều lần trên một loader và cùng binary name, thường bạn chỉ benchmark cached lookup.
- Nếu tạo loader mới mỗi vòng, bạn lại thêm chi phí tạo loader, archive handling, GC/metaspace và class generation; có thể bị nhiễu bởi pressure mới.

### Phép đo đầu-cuối vẫn hữu ích khi xác định đúng mục tiêu

Ví dụ bạn muốn biết **người dùng chờ bao lâu đến khi plugin sẵn sàng**. Hãy đo đúng pipeline:

```text
start request
   -> tạo loader
   -> load provider
   -> verify/link theo JVM
   -> initialize/instantiate
   -> đọc config
   -> start plugin
   -> ready
```

Đó là một **end-to-end latency metric**, có giá trị cho người dùng. Nhưng đừng gọi nó “thời gian verification” chỉ vì method `Class.forName(...)` xuất hiện trong call stack.

### Phân loại ít nhất ba phép đo

| Loại đo | Cách tổ chức | Trả lời câu hỏi |
|---|---|---|
| **Cold startup** | JVM process mới, workload/OS cache/flags được ghi nhận | Khởi động dịch vụ/plugin mất bao lâu? |
| **First use** | Một JVM đang chạy; class/module/provider lần đầu được sử dụng | Request đầu tiên chịu chi phí gì? |
| **Steady state** | Nhiều request sau warmup, JVM/JIT đã ổn định tương đối | Độ trễ thông thường sau nạp lớp là bao nhiêu? |

Cả ba cần xem **p50, p95/p99, variance**, không chỉ một lần đo. Với benchmark micro-level Java, dùng **JMH** khi phù hợp để tổ chức warmup, forks và đo lặp lại; vẫn phải thiết kế state để không vô tình đo cùng class đã được load hoặc dùng OS cache không tương ứng scenario cần khảo sát.

## 11. Đo và tìm bottleneck bằng công cụ phù hợp

### 11.1. Unified logging và Java Flight Recorder

Bộ công cụ hữu ích trên nhiều HotSpot/JDK:

- **`-Xlog:class+load=info`**: tìm class nào đang nạp, từ nguồn nào; quan sát nhiều loads.
- **`-Xlog:class+init=info`**: theo dõi sự kiện liên quan initialization và, tùy release, verification.
- **Java Flight Recorder (JFR)**: phân tích hoạt động JVM trong giai đoạn startup/first request; quan sát class-loading events, CPU samples, allocation/GC, I/O khi events/config được bật phù hợp.
- **`jcmd <pid> VM.classloader_stats`**: thống kê class-loader footprint khi JVM hỗ trợ.
- **Async profiler / sampling profiler**: xem CPU stacks/thời gian trong ZIP, verifier, linker, reflection, class initialization hoặc chính app code.
- **I/O/file diagnostics**: file opens, bytes read, page faults, storage latency; công cụ cụ thể phụ thuộc OS.

Không phải mọi event đều bật mặc định hoặc có mặt trên mọi vendor/JDK. Phải kiểm tra cấu hình JFR và logging trước khi kết luận một event “không xảy ra” chỉ vì trace không ghi nhận.

### 11.2. Đọc stack profile theo nhóm nguyên nhân

| Stack/signals thấy nhiều | Giả thuyết cần kiểm tra |
|---|---|
| ZIP/JAR reading, `JarFile`, filesystem read | Nhiều JAR opens/class bytes/resource reads; cache/storage |
| `ClassLoader.loadClass`, custom `findClass`, URL search | Lookup policy, parent delegation, scanning, custom overhead |
| Class verification/linking VM code | Số class/method/code generation hoặc resolution |
| Class initialization routines, `<clinit>` | Static initializer làm CPU/I/O/locks |
| Reflection, service provider discovery | Framework scanning, class/link/init, provider constructors |
| JIT compilation threads | Warmup/code generation khác class loading |
| GC/safepoint pressure | Allocation/metadata churn, plugin loader generations |
| DB/network client connect | Application initialization code, không phải JAR I/O |

**Tìm root cause rồi mới tối ưu.** Nếu 95% startup delay nằm trong một static block mở mạng, việc chuyển DEFLATE sang STORED cho JAR có thể ít hiệu quả hơn nhiều so với tách I/O ra khỏi `<clinit>`.

## 12. Tối ưu đọc JAR/class loading đúng mục tiêu

### 12.1. Giảm số class thực sự phải load lúc startup

- Tránh scan và initialize mọi plugin khi người dùng chỉ cần một số ít.
- Với SPI, tránh iterate/instantiate toàn bộ providers sớm nếu yêu cầu chưa dùng.
- Hoãn load optional features tới lúc cần (có state machine và error handling).
- Kiểm tra framework annotation/reflection scanning, auto-configuration và dependency discovery.
- Giảm plugin reload/loader creation không cần thiết; tái sử dụng loader trong vòng đời hợp lệ.

**Lưu ý:** “lazy hơn” có thể giảm startup nhưng **chuyển độ trễ sang first request**. Cần quyết định ngân sách latency ở đâu thay vì coi lazy là thắng tuyệt đối.

### 12.2. Đóng gói và classpath hợp lý

- Loại bỏ dependencies thật sự không dùng, đặc biệt JARs bị framework scan hoặc mở trong startup path.
- Giảm split/duplicate classes và package conflicts.
- Đặt những resources/classes thường đi cùng nhau trong deployment dễ truy cập.
- Với plugin loader, giới hạn URLs đúng nhóm plugin thay vì đưa hàng trăm unrelated JARs vào mọi loader.
- Tránh mở/đóng cùng archive không cần thiết trong vòng lặp nghiệp vụ.
- Kiểm tra compression level nếu profiling cho thấy inflate/decompress thật sự đáng kể; phải đo tradeoff kích thước file, I/O và CPU.

**Không có quy tắc “nén JAR ít nhất luôn nhanh nhất”**: giảm nén tiết kiệm CPU giải nén nhưng tăng bytes phải đọc, ảnh hưởng I/O/cache. Trên network filesystem, tradeoff có thể đảo ngược. Cũng không có quy tắc mọi ứng dụng đều chạy nhanh nhất khi đóng thành một fat JAR — nested JAR loaders, scanning/indexing và framework behavior có thể khác classpath thường.

### 12.3. Không tự xây custom ClassLoader cho mục tiêu nhỏ

`URLClassLoader` và system/module loaders đã triển khai nhiều tối ưu/ràng buộc cần thiết. Custom loader chỉ nên dùng khi có yêu cầu như:

- Nguồn class bytes không phải JAR/directory thông thường.
- Namespace/dependency isolation riêng thật sự cần.
- Bytecode transformation/loading policy có chủ đích.
- Plugin lifecycle/domain khác loader hiện tại.

Một loader tự viết đọc toàn bộ JAR trên mỗi `findClass` hoặc không lưu trạng thái có thể biến class lookup thành bottleneck nghiêm trọng. Nhưng **không tự cache `Class<?>` sai quy tắc hoặc bỏ parent delegation/linking** để “tăng tốc”: dễ gây `LinkageError` và class identity mismatch.

### 12.4. CDS và AppCDS

**Class Data Sharing (CDS)** trên HotSpot có thể giúp giảm chi phí khởi động, tăng khả năng chia sẻ class metadata và giảm memory footprint cho những class/loader/archive configurations được hỗ trợ. **Application CDS (AppCDS)** mở rộng khả năng chia sẻ tới một số application classes.

Có thể đọc Java launcher docs/HotSpot CDS docs và kiểm tra:

```bash
java -Xshare:auto -version
```

Đây là lệnh minh họa lựa chọn chia sẻ dữ liệu khi có archive thích hợp; **không đo một mình** để suy ra ứng dụng đã tăng tốc bao nhiêu. Có thể dùng unified logging liên quan CDS để xác nhận runtime có dùng shared archive không.

Giới hạn quan trọng:

- CDS **không** làm `static {}` chứa network call trở thành miễn phí.
- CDS không bảo đảm mọi class từ **custom class loaders** hoặc plugins được share đúng như bootstrap/platform/application loader classes.
- Chia sẻ class metadata và chia sẻ **runtime static state/plugin instances** là hai việc khác nhau.
- Lợi ích phụ thuộc archive, JDK, classpath/module path, deployment và workload thực tế.

Đừng tuyên bố “bật CDS bỏ hoàn toàn verification, linking và initialization của mọi class”. Cần đo theo cấu hình hỗ trợ và xác minh hoạt động thực.

## 13. Tối ưu initialization thay vì làm JVM phải “lười kiểm tra”

Một class có static initializer phức tạp:

```java
final class ExpensiveStart {
    static final Map<String, String> CONFIG = readRemoteConfig();

    static Map<String, String> readRemoteConfig() {
        // I/O đồng bộ ở lần sử dụng class đầu tiên.
        throw new UnsupportedOperationException(
                "Illustrative only");
    }
}
```

Đây là **đoạn minh họa không độc lập**, cần `import java.util.Map;`. Lệnh ném exception ở đây nhằm nhấn mạnh tính nguy hiểm của I/O/lỗi trong static initialization, **không phải mẫu áp dụng**.

Vấn đề:

- Lần active use đầu tiên có thể chịu chi phí network và timeout.
- Các threads khác chờ initialization cùng runtime class.
- Nếu initialization lỗi, class có thể ở erroneous state, khó retry.
- Reload loader generation có thể khởi chạy lại toàn bộ công việc.

Thay thế thường tốt hơn: **lifecycle rõ ràng**.

```java
public final class PluginService {
    private volatile Config config;

    public void start(Config loaded) {
        if (loaded == null) {
            throw new IllegalArgumentException("config required");
        }
        config = loaded;
    }

    public String mode() {
        Config c = config;
        if (c == null) {
            throw new IllegalStateException("not started");
        }
        return c.mode();
    }

    public record Config(String mode) {}
}
```

Đây là class có thể biên dịch trong `PluginService.java` trên Java 17+, **không có `main`**. Nó cho phép host quyết định **khi nào đọc config**, đặt timeout/retry và đánh dấu plugin sẵn sàng. `volatile` chỉ phục vụ visibility của reference trong ví dụ; production lifecycle đa bước cần synchronization/state machine thích hợp.

**Đánh đổi:** Initialization tường minh không làm tổng công việc biến mất; nó giúp di chuyển, đo, retry và quản lý công việc theo đúng lifecycle. Đừng chỉ chuyển code sang constructor rồi tuyên bố đã tối ưu nếu startup vẫn phải tạo toàn bộ objects ngay lập tức.

### Lazy holder cho dữ liệu nội bộ thuần CPU

Nếu muốn lazy khởi tạo một cấu trúc bất biến khi thật sự dùng:

```java
public final class LookupTable {
    private LookupTable() {}

    private static final class Holder {
        static final java.util.Map<String, Integer> TABLE =
                java.util.Map.of("a", 1, "b", 2);
    }

    public static int get(String key) {
        return Holder.TABLE.getOrDefault(key, -1);
    }
}
```

Đây là utility class có thể biên dịch trong `LookupTable.java`. `Holder` được initialized khi đường code sử dụng trường `Holder.TABLE` theo quy tắc active use; thường tránh làm công việc đó khi chỉ nạp outer class.

Tuy vậy **không** đặt network I/O có khả năng thất bại lâu dài vào lazy holder mà không có cơ chế retry/timeout: failure vẫn là class initialization failure của `Holder`.

## 14. JIT warmup và initialization là hai hiện tượng khác nhau

Đôi khi sau 1.000 request, method chạy nhanh hơn đáng kể. Có thể là:

- JVM đã nạp những classes chưa được dùng trước đó.
- Class initialization hoàn tất.
- OS/JAR caches nóng.
- JIT compiler có đủ profiling data để compile/optimize methods.
- Heap caches/application data structures đã được tạo.
- Network/DB connection pools đã sẵn sàng.

Một lời gọi method lần thứ 1 có thể trả chậm vì `<clinit>`; lời gọi lần thứ 1000 nhanh vì JIT compilation. Hai việc đều thuộc “warmup” theo ngôn ngữ đời thường nhưng cần **phân biệt khi profiling**.

JIT cũng có chi phí CPU/compilation threads và code cache; đó **không phải verification**. Nếu muốn đo thời gian Java business method ở steady state, hãy dùng công cụ benchmark/profiler theo đúng mục đích, tránh benchmark class loading lẫn vào algorithm performance.

## 15. Ảnh hưởng của JPMS, ServiceLoader và plugin architecture

### Named module và module graph

JPMS có module resolution, readability, exports/opens và service provider declarations. Những hoạt động này có thể ảnh hưởng startup/discovery:

- Việc resolve module configuration xảy ra khi launcher hoặc `ModuleLayer` được thiết lập theo contract.
- Class load/link/init vẫn áp dụng cho classes trong named modules.
- `ModuleLayer.defineModulesWithOneLoader` và `defineModulesWithManyLoaders` tạo những loader mappings khác nhau, ảnh hưởng số runtime namespaces.
- Class-loader cache và resource access còn phụ thuộc module membership/encapsulation.

Không quy toàn bộ thời gian module resolution thành “JAR read”. Module configuration và runtime class linking có mục tiêu/chi phí khác nhau.

### ServiceLoader

`ServiceLoader.load(Service.class)` dùng **thread context class loader** theo Java SE 17 API; overload nhận loader tường minh dùng loader đó. Providers được phát hiện/khởi tạo **lazy** theo cơ chế của `ServiceLoader`; duyệt toàn bộ provider instances có thể khởi chạy:

```text
descriptor/module discovery
    -> provider class loading
    -> verification/linking
    -> initialization
    -> provider constructor/factory
    -> application initialization
```

Vì thế một framework chạy `for (Service s : ServiceLoader.load(Service.class))` trong startup có thể chịu nhiều giai đoạn cùng lúc. Khi tính latency, hãy phân biệt **khởi tạo đối tượng ServiceLoader** với **duyệt và thực sự instantiate providers**.

### Per-plugin loader vs shared loader

- **Mỗi plugin một loader** có thể cách ly dependencies và vòng đời, nhưng có thể nạp/verify/initialize những class private giống nhau nhiều lần qua nhiều defining loaders.
- **Một loader chung** có thể chia sẻ classes/static state và giảm trùng metadata, nhưng gây version conflicts hoặc không cho các plugins hot-reload độc lập bằng class identity mới.
- Cả hai cần giữ **shared SPI/DTO contracts** ở loader chung thích hợp nếu host và plugins trao đổi typed objects.
- Nhiều loader generations chưa được cleanup có thể làm tăng metaspace và GC pressure, ảnh hưởng hiệu năng lâu dài.

Đừng chuyển sang shared loader chỉ để giảm startup mà không kiểm tra class identity, dependency versioning và lifecycle.

## 16. Lỗi thường gặp và cách phân loại

### A. `ClassNotFoundException`

Loader được chọn không tìm thấy binary class name. Kiểm tra classpath/JAR URL, parent delegation, TCCL và custom loader resource mapping. Đây thường là **vấn đề lookup**, không chứng minh “verification quá chậm”.

### B. `NoClassDefFoundError`

Có thể do dependency cần thiết không hiện diện khi JVM resolve, binary name mismatch hoặc class đã rơi vào trạng thái **initialization thất bại**. Đọc đầy đủ cause/message và biết class nào lỗi đầu tiên.

### C. `ClassFormatError` / `VerifyError`

Class-file bytes sai format hoặc bytecode verification thất bại. Đừng “fix” bằng cách tắt verifier để startup nhanh hơn. Kiểm tra transformer/code generator, class-file version và nguyên nhân sai bytecode.

### D. `NoSuchMethodError` / `NoSuchFieldError`

Symbolic reference không resolve như bytecode kỳ vọng, thường do runtime dependency version mismatch. Lỗi có thể xuất hiện **lúc method path lần đầu thực sự chạy**, không nhất thiết lúc load class ban đầu.

### E. `ExceptionInInitializerError`

Static initializer ném exception. Class có thể ở erroneous state; retry trên cùng defining loader thường thất bại. Đưa I/O/logic dễ thất bại khỏi `static {}` nếu cần retry/lifecycle.

### F. `SecurityException` khi class loading

Có thể là JAR package sealing, signer/certificate set inconsistency hoặc namespace `java.*` bị cấm. Đây là class loading constraints, **không nhất thiết do SecurityManager**.

### G. `OutOfMemoryError: Metaspace`

Nhiều loader generations/classes/metadata có thể tăng memory pressure. Kiểm tra classloader retention, TCCL, reflection caches, `ServiceLoader` instances, thread pools và GC/unloading behavior. Không chỉ tăng `MaxMetaspaceSize` để che classloader leak.

## 17. Quy trình tối ưu hiệu năng có thể áp dụng ngay

1. **Xác định chỉ số mục tiêu:** process startup đến ready, latency first request hay steady-state throughput/p99.
2. **Chốt môi trường:** Java vendor/version, CPU, storage, OS, heap/metaspace, GC, CDS, JAR packaging, container CPU quota.
3. **Phân biệt cold/warm:** JVM mới, OS cache, loader generation và JIT state.
4. **Ghi class-load/class-init logs** một lần để tìm classes và nguồn JAR liên quan; nhớ đo riêng overhead logging.
5. **Thu JFR/CPU/I/O profile** đúng đoạn slow path, không chỉ tổng milliseconds.
6. **Tách giai đoạn ứng dụng:** module/plugin discovery, class load, provider instantiation, config I/O, framework startup, readiness.
7. **Tối ưu đúng nguyên nhân:** giảm scan/unused deps, giảm loader churn, lazy optional features, cải thiện filesystem access, thay static I/O bằng lifecycle có quản lý.
8. **Giữ invariant và security:** không bỏ JVM verification, không lách signer/sealing/module checks.
9. **Benchmark lại** nhiều runs/forks, theo p50/p95/p99 và class/memory footprint; so sánh trên workload tương đương.
10. **Kiểm thử chức năng** dưới cả cold/warm/parallel startup, nhất là thread-safety, dependency failures và plugin reload.

Đừng đo trên một JVM đã nạp tất cả classes rồi kết luận “đọc JAR không đáng kể” cho startup mới. Cũng đừng đo một JVM mới duy nhất có background antivirus đang quét file rồi kết luận mọi users sẽ chậm như vậy.

## 18. Câu hỏi tự kiểm tra

**1. Gọi `loader.loadClass("demo.Plugin")` có nhất thiết chạy `static {}` không?** Không. Method không tự yêu cầu initialization theo hợp đồng thông thường.

**2. `Class.forName("demo.Plugin", false, loader)` khác overload `true` ở điểm nào?** `false` không yêu cầu initialize class; `true` yêu cầu initialization nếu chưa thực hiện.

**3. `Preparation` có chạy `static int n = expensive()` không?** Không. Preparation đặt default static values; static initializer expression được thực thi trong initialization.

**4. JVM có bắt buộc resolve tất cả symbolic references ngay lúc linking ban đầu không?** Không. Có thể eager/lazy theo yêu cầu chuẩn.

**5. Mỗi lần gọi `loadClass` có đọc lại class bytes từ JAR không?** Không nhất thiết; class đã nạp có thể được trả từ loader cache.

**6. Đọc `settings.txt` từ JAR có tự khởi tạo `Plugin` cùng JAR không?** Không. Resource lookup không đồng nghĩa class initialization.

**7. Vì sao class-file verification khác JAR signature verification?** Một bên kiểm tra bytecode/type safety; bên kia liên quan metadata/chữ ký/tính toàn vẹn của JAR entry.

**8. `Class.forName(..., true, ...)` mất 300 ms có nghĩa verifier mất 300 ms?** Không. Thời gian có thể gồm loading/linking, dependencies và application static initializer.

**9. `NoSuchMethodError` chỉ xuất hiện ngay lúc `loadClass` sao?** Không. Symbolic resolution có thể được trì hoãn tới điểm dùng liên quan.

**10. CDS có làm network I/O trong `<clinit>` biến mất không?** Không. CDS có thể tối ưu một số khía cạnh class metadata/load path nhưng không tự bỏ application initialization code.

**11. Vì sao tạo loader mới cho mỗi request có thể gây chi phí lớn?** Mỗi loader tạo namespace riêng, có thể làm lặp class definition/link/init, metadata và archive work.

**12. Cách so sánh đúng cold startup và steady state?** Định nghĩa riêng test conditions, đo nhiều lần/forks, ghi OS/JIT/cache state và profile bottleneck.

## 19. Tài liệu chính thức

- **Java Language Specification Java SE 17, Chapter 12 — Execution:** loading (`12.2), linking (`12.3), initialization (`12.4), timing và lazy resolution: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **Java Virtual Machine Specification Java SE 17, Chapter 5 — Loading, Linking, and Initializing:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **Java SE 17 `ClassLoader` API:** delegation, `loadClass`, `findClass` và class loading rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 `Class.forName` API:** tham số `initialize`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 `URLClassLoader`:** nạp từ URLs/JARs và resource lookup: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **Java SE 17 JAR File Specification:** manifest, entry structure, signed JAR và package metadata: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- **Java SE 17 `java` launcher reference:** `-Xlog`, `-Xshare` và JVM options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Java SE 17 `ServiceLoader` API:** provider loading/discovery: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **OpenJDK JEP 310 — Application Class-Data Sharing:** https://openjdk.org/jeps/310

**Ghi nhớ:** Tìm bytecode trong JAR, JVM verification, linking/resolution và chạy `<clinit>` là những **chi phí có nguồn gốc khác nhau**. `loadClass` không đồng nghĩa `initialize`, `getResourceAsStream` không đồng nghĩa nạp lớp, và resolution có thể lazy. Để tối ưu hiệu quả, phải **đo đúng giai đoạn, xác định cold/warm và cải thiện bottleneck thực**, không đánh đổi tính đúng đắn hoặc an toàn của JVM để lấy những con số startup tưởng như nhanh hơn.
