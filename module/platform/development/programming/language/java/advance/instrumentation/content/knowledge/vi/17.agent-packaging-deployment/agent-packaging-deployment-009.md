# Kiểm tra nguồn gốc agent, nội dung JAR và phạm vi dữ liệu được thu thập

Một Java agent chạy cùng JVM với ứng dụng có thể quan sát quá trình nạp class, nhận bytecode qua `ClassFileTransformer`, cài logic vào method và, tùy quyền/capability, yêu cầu retransform hoặc redefine class. Đây là cơ chế rất hữu ích cho profiling, tracing và bảo mật, nhưng cũng khiến việc **triển khai một JAR không rõ nguồn gốc** trở thành rủi ro đáng kể.

Trước khi dùng `-javaagent`, không chỉ hỏi “JAR này có chạy được không?”, mà cần trả lời ba câu hỏi độc lập:

1. **Nguồn gốc**: Ai tạo ra đúng artifact này, từ mã nguồn/commit/build nào, qua kênh phân phối nào và có chứng cứ kiểm tra được không?
2. **Nội dung và quyền năng**: Trong JAR có những class, thư viện, tài nguyên, entry point, manifest capability, native component hoặc dependency nào? Nó có thể làm gì trong JVM?
3. **Dữ liệu thực sự thu thập/xử lý/gửi đi**: Agent quan sát class, method và event gì; có lấy argument/return value, headers, secrets, stack traces hay dữ liệu nghiệp vụ không; dữ liệu được gửi tới đâu, lưu bao lâu và ai xem được?

**Không được xem ba câu trả lời này là một.** SHA-256 giống bản phát hành công bố không tự chứng minh nhà phát hành đáng tin; chữ ký số hợp lệ không tự chứng minh hành vi an toàn; cấu hình `capture=false` cũng không chứng minh runtime không có đường thu thập khác. Bài này thuộc phần **Đóng gói và triển khai** của Java Advance — instrumentation, tập trung vào chuỗi kiểm soát trước và sau khi nạp agent.

Mục tiêu là thiết lập quy trình **kiểm tra trước khi thực thi**, thử nghiệm một agent Java 17+ do chính ta tạo ra, phân biệt bằng chứng mạnh/yếu và xây “data collection contract” đủ cụ thể để kiểm toán.

## 1. Vì sao Java agent phải được đánh giá như mã có quyền cao?

Một Java agent dùng startup mode có dạng:

```bash
java -javaagent:path/to/agent.jar=options -cp app-classes demo.Main
```

Đây là **cú pháp minh họa**; `path/to/agent.jar` và application class phải có thật khi sử dụng. JVM đọc manifest của agent JAR, tìm class khai báo bởi `Premain-Class`, rồi gọi `premain(...)` **trước** application `main`.

Với các runtime có hỗ trợ dynamic loading, agent còn có thể được nạp vào tiến trình đang chạy qua `Agent-Class`/`agentmain(...)`. Do đó phạm vi kiểm soát không kết thúc ở command-line startup: phải xem cả quyền nạp agent động, công cụ attach và chính sách của JVM.

Agent có thể:

- Đăng ký `ClassFileTransformer` để nhận `className`, loader/module, `ProtectionDomain`, `classfileBuffer` và các thông tin liên quan ở thời điểm transform.
- Tạo bytecode mới để chèn metric/tracing vào các method được chọn.
- Khi được hỗ trợ và có capability phù hợp, gọi `retransformClasses` hoặc `redefineClasses` để thay logic của class đã nạp trong giới hạn JVM.
- Thay đổi khả năng đọc/mở module bằng `Instrumentation.redefineModule` theo hợp đồng API.
- Bổ sung JAR helper vào bootstrap hoặc system loader search path.
- Gọi API Java thông thường: file, network, threads, process, environment, logging, reflection và các thư viện mà agent nạp được.

Điều quan trọng: **khả năng tiếp cận dữ liệu không đồng nghĩa đã thu thập dữ liệu**, nhưng bên kiểm toán không được chỉ dựa vào lời quảng cáo của agent để kết luận “không thể đọc dữ liệu đó”.

Ví dụ, callback này có thể nhận bytecode dù không thay đổi:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (!"demo/Work".equals(className)) {
        return null;
    }

    // Quyết định xử lý dữ liệu phải được kiểm toán tại đây.
    return null;
}
```

Đây là **trích đoạn phương thức** trong class triển khai `ClassFileTransformer`, không phải một agent runnable. Việc `return null` chỉ có nghĩa **không sửa bytes trong callback này**; nó không tự nói rằng agent không ghi log, không giữ lại bytes hoặc không truyền dữ liệu đi ở những nhánh khác.

Vì agent chạy trong cùng JVM/progress context của ứng dụng, một cấu hình giới hạn thu thập là **biện pháp bảo vệ có điều kiện**, không phải sandbox bảo mật độc lập.

## 2. Ba lớp bằng chứng: integrity, authenticity và provenance

| Bằng chứng | Xác nhận được điều gì | Không tự chứng minh điều gì |
|---|---|---|
| **SHA-256 digest** đối chiếu giá trị tham chiếu đáng tin | Bytes artifact hiện tại khớp một digest đã được công bố/xác thực | Người công bố digest có đáng tin hay không; agent có an toàn hay không |
| **JAR signature** được verify | Những JAR entries được ký không bị thay đổi trái với chữ ký; có thông tin signer/certificate | Signer có được tổ chức phê duyệt không; mọi entry đều được ký hay không; code không gây hại |
| **Trusted publisher/channel** | Artifact đến từ kênh phân phối/nhà phát hành đã được phê duyệt | Mã nguồn của phiên bản cụ thể có đúng với bytes không |
| **Build provenance/attestation** | Có bằng chứng về nơi, cách, commit/build pipeline tạo artifact, nếu được kiểm tra | Bản khai provenance là sự thật chỉ vì nó tồn tại; builder/signer nào cũng đáng tin |
| **SBOM/dependency inventory** | Liệt kê thành phần bên trong và dependency đã khai báo/được phát hiện | Không có dependency bị giấu hoặc không có lỗ hổng ở runtime |
| **Static review** | Nhận diện code path, APIs, resources và cấu hình có thể thấy được | Không có nhánh obfuscated, reflection, dynamic loading hoặc hành vi phụ thuộc môi trường |
| **Runtime egress/data audit** | Những luồng dữ liệu phát hiện được trong bài test | Mọi hành vi ở mọi input/config/production host đều giống nhau |

Một quy trình nghiêm túc cần **nhiều bằng chứng hỗ trợ nhau**, không chỉ một giá trị `sha256`.

### 2.1. Kiểm tra SHA-256 có điều kiện tin cậy

Ví dụ trên PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\dist\scope-agent.jar
```

Trên Linux/macOS có `sha256sum`:

```bash
sha256sum dist/scope-agent.jar
```

Lệnh tính digest của **JAR cụ thể trên disk**. Cần so sánh với giá trị SHA-256 của **đúng phiên bản** được cung cấp qua kênh có xác thực: release manifest được ký, bản kiểm kê artifact nội bộ đã được phê duyệt, hoặc một provenance/attestation đã được xác minh.

**Không hợp lệ** nếu lấy SHA-256 của một JAR lạ rồi lưu lại và tuyên bố “đã xác minh nguồn gốc” mà không có digest tham chiếu đáng tin. Điều đó chỉ chứng minh tính nhất quán của bản sao với **chính nó**.

Khi tải, sao chép, ký hoặc đóng gói lại JAR, bytes có thể thay đổi. Hash phải gắn với **artifact cuối cùng thực sự sẽ được chạy**, không phải file source, JAR trung gian hoặc một bản cache khác.

### 2.2. Chữ ký JAR không thay thế chính sách tin cậy

Với một artifact đã được ký, có thể kiểm tra:

```bash
jarsigner -verify -strict -verbose -certs release-agent.jar
```

Đây là lệnh kiểm tra **một JAR có thật tên `release-agent.jar`**, không thuộc ví dụ demo. Đọc toàn bộ cảnh báo và exit code, kiểm tra **signer identity, trust chain, certificate validity, thuật toán và các entries unsigned**. Tùy chính sách, cần dùng truststore/alias được phê duyệt thay vì chỉ dựa vào certificate nhúng trong JAR.

`-strict` làm các cảnh báo nghiêm trọng ảnh hưởng exit code. Một số trường hợp: certificate self-signed, chain không xác nhận, thuật toán không phù hợp, hoặc JAR có **unsigned entries**. Dòng `jar verified` một mình chưa đủ để khẳng định “toàn bộ artifact đúng chính sách”.

**Ký JAR không khiến mọi JVM tự động từ chối `-javaagent` chưa ký.** Java Instrumentation specification đặt trách nhiệm đánh giá độ tin cậy của agent và nội dung JAR vào tay người triển khai/quản trị; việc enforce allowlist chữ ký/digest phải nằm trong quy trình deployment hoặc công cụ bảo vệ mà tổ chức thực sự kiểm soát.

### 2.3. Provenance phải được verify, không chỉ được đính kèm

Một bản provenance có ích khi xác định được:

```text
source repository/commit
        |
        v
CI workflow + trusted builder
        |
        v
build inputs / dependencies
        |
        v
signed build attestation + output digest
        |
        v
exact JAR được đưa lên môi trường chạy
```

Theo mô hình SLSA, build provenance mô tả **ở đâu, khi nào và bằng cách nào** artifact được tạo. Người nhận vẫn phải xác minh chữ ký của attestation, danh tính builder, source revision, expected build workflow và digest của subject trùng với JAR nhận được.

Một JSON tự viết có tên `provenance.json` nằm cạnh agent **chưa đủ**. Cần có chuỗi tin cậy giữa **source → build → artifact → deployment**.

## 3. Xem nội dung JAR **trước khi chạy bất kỳ agent code nào**

Đối với một JAR chưa được tin cậy: **không bắt đầu bằng** `java -javaagent:unknown.jar ...` để “xem nó in gì”. `premain` đã được thực thi **trước** application `main`, nên thời điểm đó có thể đã quá muộn để chặn side effects.

Thứ tự hợp lý:

1. Đặt JAR trong môi trường phân tích thích hợp, chưa cấp credential hoặc network không cần thiết.
2. Xác thực đường phân phối, version, digest và chứng cứ chữ ký/provenance.
3. Liệt kê entries, đọc manifest, phát hiện các class/nguồn động/nested artifacts.
4. Rà soát bytecode, dependency, các điểm vào, config defaults và luồng thu thập.
5. Duyệt/chốt policy dữ liệu và quyền triển khai.
6. **Chỉ sau khi đạt các gate phù hợp** mới chạy trên môi trường test cô lập.
7. So sánh output/egress/file writes thực tế với hợp đồng đã duyệt, rồi quyết định rollout.

Các lệnh đọc JAR:

```bash
jar --list --file release-agent.jar
```

Nếu cần xem cấu trúc bytecode của một class hiện diện trong artifact:

```bash
javap -classpath release-agent.jar -c -p com.example.Agent
```

Cả hai là **lệnh minh họa**, đòi JAR/class thật. `jar --list` liệt kê tên entries; `javap -c -p` cho disassembly và member declarations, **không tự khởi chạy `premain`**. Tuy nhiên disassembly không chứng minh được toàn bộ luồng hành vi, đặc biệt khi agent dùng reflection, native library hoặc tải component từ network.

Cẩn thận khi xử lý file không đáng tin: JAR dựa trên ZIP, có thể gây tiêu thụ tài nguyên lớn hoặc chứa đường dẫn nguy hiểm. Không giải nén tùy tiện vào thư mục nhạy cảm; nếu cần phân tích sâu, dùng môi trường cách ly và giới hạn dung lượng.

### 3.1. Những manifest keys phải đọc

| Manifest key | Ý nghĩa | Câu hỏi kiểm tra |
|---|---|---|
| `Premain-Class` | Startup agent entry point | Class có thật, chữ ký `premain` phù hợp không? |
| `Agent-Class` | Dynamic attach agent entry point | Có đường nạp agent sau startup cần kiểm soát không? |
| `Launcher-Agent-Class` | Agent được đóng cùng executable JAR | Có điểm vào phụ khi chạy `java -jar` không? |
| `Can-Retransform-Classes` | Xin khả năng retransform | Agent có cần capability này không? |
| `Can-Redefine-Classes` | Xin khả năng redefine | Có lý do phê duyệt việc thay method đã load không? |
| `Can-Set-Native-Method-Prefix` | Xin khả năng native prefix | Có thật sự cần? |
| `Boot-Class-Path` | Path bootstrap helper | Những JAR/đường dẫn bổ sung nào được nạp? |
| `Class-Path` | Class-path dependencies | Có dependency ẩn hoặc không nằm trong artifact chính không? |
| `Multi-Release` | JAR có lớp versioned | Có implementation khác nhau giữa các bản JDK không? |
| `Automatic-Module-Name` | Tên module tự động khi dùng module path | Có điều kiện/module visibility liên quan không? |

**Một capability header `true` nói về yêu cầu khả năng, không chứng minh code luôn sử dụng khả năng đó.** Ngược lại, header `false` không phải lời cam kết agent không gọi network/file APIs thông thường. Phải xem cả content và behavior.

### 3.2. Đừng chỉ nhìn `.class` ở gốc

Một JAR có thể chứa:

- `META-INF/services/...`: ServiceLoader provider declarations.
- `META-INF/versions/N/...`: implementation khác trong **multi-release JAR**.
- JAR lồng, file cấu hình, script hoặc resource.
- Native binaries như `.so`, `.dll`, `.dylib`, JNI libraries.
- Manifest `Class-Path` trỏ tới JAR ngoài artifact chính.
- Helper JAR trong `Boot-Class-Path` hoặc được agent append bằng `Instrumentation`.
- Các class obfuscated, dynamic proxies, bytecode được tạo lúc chạy.

Đối với **multi-release JAR**, kiểm tra cả base entries và versioned entries phù hợp với JDK thực tế. JAR File Specification nêu bootstrap loader không áp dụng multi-release behavior cho JAR được append vào bootstrap search path như một thư viện thông thường; đừng suy từ behavior ở application loader sang bootstrap.

Đối với **signed JAR**, lưu ý chữ ký thường liên quan đến từng entry; nếu có unsigned content được thêm vào sau khi ký, một phần entries cũ vẫn có thể có chữ ký hợp lệ. Vì vậy phải kiểm tra **coverage** và cảnh báo, không chỉ “JAR có `.RSA`/`.SF` trong `META-INF`”.

## 4. Kiểm tra các API và luồng hành vi đáng chú ý

Khi code review agent (hoặc so source với bytecode được phát hành), chú ý các nhóm sau:

| Nhóm | API/tín hiệu có thể gặp | Điều cần kết luận |
|---|---|---|
| Instrumentation | `addTransformer`, `retransformClasses`, `redefineClasses`, `redefineModule` | Chính xác những class nào được chạm tới? |
| Thông tin class | `getAllLoadedClasses`, `getInitiatedClasses`, `classfileBuffer` | Dữ liệu class names/bytecode có bị lưu hoặc gửi không? |
| Reflection/MethodHandle | `setAccessible`, `MethodHandles`, deep reflection | Có vượt phạm vi quan sát đã duyệt không? |
| Network | HTTP clients, sockets, gRPC, exporters | Host/port/protocol, TLS, credential và payload là gì? |
| File/system | `Files`, logging, environment, system properties | Có đọc/ghi thư mục nhạy cảm hoặc biến chứa secret không? |
| Threads/scheduling | Background workers, executors, timers | Có luồng chạy ngoài thời điểm hook không? |
| Dynamic loading | `URLClassLoader`, `ServiceLoader`, plugin loaders | Có code phụ tải sau lúc duyệt JAR không? |
| Native/exec | `System.loadLibrary`, JNI, `ProcessBuilder` | Có cần native/OS privileges không? |
| Helper injection | `Boot-Class-Path`, bootstrap/system append | Có thêm code vào loader tin cậy rộng hơn không? |

Một `grep` hoặc `javap` tìm các method names này **chỉ là bước đầu**. Agent có thể thực hiện hành vi tương đương qua abstraction hoặc dependency gián tiếp; không thấy một chuỗi literal cũng **không chứng minh không có hành vi**.

Nếu code đóng gói bị làm rối (obfuscation), không có source hoặc không thể kiểm tra dependency, đây là **khoảng trống bằng chứng** cần nêu rõ và xử lý theo chính sách rủi ro, thay vì tự đánh dấu PASS.

## 5. Định nghĩa phạm vi dữ liệu: “được nhìn thấy” khác “được thu thập”

Trong Java instrumentation có ít nhất bốn tầng:

```text
JVM/API cung cấp thông tin cho callback
                |
                v
Agent đọc hoặc tính toán từ thông tin đó
                |
                v
Agent lưu trong memory/buffer/log/file
                |
                v
Agent xuất ra network/exporter/collector
```

Cần đánh giá **từng tầng**. Ví dụ `classfileBuffer` đã được JVM truyền vào callback, nhưng agent chỉ so `className` và trả `null` thì không nhất thiết lưu bytes. Tuy vậy cùng JAR có thể có callback khác, debug mode hoặc background task gửi dữ liệu.

Một tuyên bố chung “agent chỉ thu thập metric” không đủ; phải nêu **từng trường**, điều kiện bật, loại dữ liệu, sink và retention.

### 5.1. Ma trận dữ liệu nên ghi trong bản duyệt

| Nhóm dữ liệu | Ví dụ | Mặc định khuyến nghị khi không cần |
|---|---|---|
| Method/class metadata | Binary name, descriptor, module, loader | Chỉ allowlist cần đo; tên code cũng có thể tiết lộ cấu trúc nội bộ |
| Thời gian/số đếm | Duration, invocation count, lỗi theo loại | Có thể giữ ở mức tổng hợp và nhãn ổn định |
| Argument values | Email, account ID, request payload, token | **Không thu thập** nếu không có yêu cầu chính đáng cụ thể |
| Return values | Đối tượng nghiệp vụ hoặc response body | **Không thu thập** mặc định |
| Exception details | Class name, message, cause, stack trace | Phân biệt tên loại lỗi với message/stack có thể chứa dữ liệu nhạy cảm |
| HTTP metadata | Route template, status, headers, cookies | Không ghi Authorization/Cookie hoặc raw URL query thiếu kiểm soát |
| SQL/database | Query template, bind variables, connection string | Không ghi bind values, credentials, full connection string |
| Secrets/process state | Environment, system properties, JVM args | Loại bỏ token/password/secret và dữ liệu không cần |
| Bytecode/raw class | `classfileBuffer`, constant pool, source names | Không xuất/ghi nguyên bytes nếu mục tiêu chỉ là timing |
| Heap/thread data | Heap dump, thread dumps, local values | Cần quyền, mục đích, retention và kiểm soát riêng |
| Trace context | Trace ID, span ID, baggage | Không mặc định coi mọi baggage là vô hại; kiểm soát field |
| User behavior | Endpoint/call patterns, tenant labels | Xem xét tính nhạy cảm và mục đích sử dụng dữ liệu tổng hợp |

Tối thiểu phải trả lời:

- **Chủ thể/mục đích:** Thu thập dữ liệu này để xử lý vấn đề gì?
- **Trigger:** Chỉ class/method trong allowlist hay mọi class trong VM?
- **Trường dữ liệu:** Tên field cụ thể, kiểu, nhãn, độ chi tiết và sampling.
- **Biên tập:** Drop/redact/mask/hash ở **đâu**? Trước khi log/spool/export hay sau đó?
- **Destination:** Endpoint, TLS, tổ chức nhận, khu vực lưu trữ, có bên thứ ba không?
- **Retention:** Memory queue, local file, server storage, backup; xóa sau bao lâu?
- **Access:** Ai có thể xem, export, sửa cấu hình hay bật debug?
- **Chứng cứ:** Source review, cấu hình runtime, packet/egress audit và mẫu telemetry sau lọc.

**Không nhầm masking với không thu thập.** Nếu raw secret đã bị ghi vào local file hoặc gửi tới collector trước khi được redaction, rủi ro đã xuất hiện dù dashboard cuối không hiển thị secret.

### 5.2. Thu thập ít nhất có thể và kiểm soát field tại nguồn

Với một agent đo hiệu năng, dữ liệu đủ dùng có thể là:

```text
methodId = "demo.Service.process()I"
outcome = "NORMAL"
durationNanos = 240000
```

Giá trị duration ở trên chỉ là **minh họa**, không phải kết quả đo từ ví dụ chạy ở phần 8. Không có `args`, `returnValue`, raw `Throwable.getMessage()`, HTTP body hay access token.

Khi cần lỗi, cân nhắc chỉ lấy **exception type** trước; message/stack trace là những trường khác có thể chứa tên file, user input, SQL, URL hoặc thông tin cá nhân. Kiểm toán cả labels của metric (tránh high-cardinality và dữ liệu cá nhân).

OWASP Logging Cheat Sheet và hướng dẫn OpenTelemetry về dữ liệu nhạy cảm đều nhấn mạnh nguyên tắc **data minimization**. Nếu dùng Collector, có thể bổ sung filter/attribute/redaction processors, nhưng chúng là **lớp phòng vệ bổ sung**, không hợp thức hóa việc agent thu thập dữ liệu không được phép ở nguồn.

## 6. Bản cam kết phạm vi thu thập phải kiểm chứng được

Một policy rõ ràng có thể quy định:

| Thuộc tính | Giá trị thử nghiệm |
|---|---|
| Mục đích | Chỉ quan sát class `demo.Work` được JVM nạp |
| Điểm vào agent | `agent.SafeAgent.premain` |
| Allowlist | **Chính xác** `demo/Work` |
| Chế độ mặc định | Không đăng ký transformer nếu option khác `allow-demo-work` |
| Data được in | Một string cố định `demo.Work` khi callback match |
| Data **không** ghi | `classfileBuffer`, argument/return, exception, headers, secrets, stack trace |
| Bytecode modification | Không; transformer trả `null` |
| Network/file output từ code agent demo | Không có trong logic được viết |
| Capability retransform | `false` trong manifest |
| Destination | `System.out` của JVM demo |
| Retention | Do nơi thu stdout của môi trường test quyết định, **không có TTL tự động từ agent** |

Đây là **policy của ví dụ mà ta kiểm soát source**, không phải lời bảo đảm cho một JAR bên ngoài không rõ nguồn gốc. Các thao tác `System.out` vẫn có thể được nền tảng logging thu lại và lưu ở nơi khác — nên phải phân tích cả downstream.

Không đủ nếu chỉ có một biến `captureArgs=false`: còn cần xem đường log lỗi/debug, sampling fallback, remote config, exporter, service provider và những trường tự động chèn bởi framework.

## 7. Ví dụ Java 17+ hoàn chỉnh: xem JAR trước, rồi chạy agent có allowlist

Thực hành có bốn source files:

1. `agent.SafeAgent`: startup agent chỉ quan sát **class name** `demo/Work`, không sửa bytecode.
2. `demo.Work`: một class để tạo class-load callback.
3. `demo.DemoApp`: launcher nạp `Work` bằng `Class.forName`.
4. `audit.JarInspector`: công cụ **đọc manifest + tên JAR entries**, tính SHA-256 và phát hiện một số dấu hiệu cần rà soát; **không load/execute agent class**.

Quan trọng: **JAR trong ví dụ do chính bạn biên dịch từ source đang xem**. Quy trình cho JAR bên ngoài phải dừng ở bước duyệt nếu chưa đáp ứng provenance/approval. Đừng áp dụng lệnh `-javaagent` cho file không đáng tin chỉ để thử kết quả.

### 7.1. Cấu trúc thư mục

```text
agent-audit-demo/
├── src/
│   ├── agent/
│   │   └── SafeAgent.java
│   ├── demo/
│   │   ├── Work.java
│   │   └── DemoApp.java
│   └── audit/
│       └── JarInspector.java
├── agent.mf
├── out/                    (được tạo khi biên dịch)
│   ├── agent/
│   ├── app/
│   └── audit/
└── dist/
    └── scope-agent.jar     (được tạo khi đóng JAR)
```

### 7.2. `src/agent/SafeAgent.java`

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class SafeAgent {
    public static void premain(String options, Instrumentation inst) {
        if (!"allow-demo-work".equals(options)) {
            System.out.println("[agent] collection=off");
            return;
        }

        inst.addTransformer(new NameOnlyTransformer(), false);
        System.out.println("[agent] allowlist=demo/Work");
    }

    private static final class NameOnlyTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain, byte[] classfileBuffer) {

            if ("demo/Work".equals(className)) {
                System.out.println("[agent] observed=demo.Work");
            }
            return null;
        }
    }
}
```

Cách đọc đúng:

- `premain` là **điểm vào** khi JVM khởi động với `-javaagent`.
- Chỉ khi option đúng chuỗi `allow-demo-work`, agent mới đăng ký transformer.
- `ClassFileTransformer.transform` sẽ được JVM gọi cho các class được biến đổi qua cơ chế tương ứng sau khi transformer đăng ký. **Callback vẫn có thể nhận `classfileBuffer` của class khác**, dù implementation chỉ log khi `className` khớp.
- So chuỗi **chính xác** `"demo/Work"` (internal form dùng dấu `/`); không log các class khác.
- Output là một **class name đã allowlist**, không phải argument hoặc value của `Work.calculate`.
- `return null` giữ nguyên class bytes, **không sửa body** và không có helper class injected.
- Trên Java 17, overload `transform(Module, ...)` có thể override như ví dụ.
- `Can-Retransform-Classes: false` đồng nghĩa agent **không yêu cầu capability callback retransform**, không phải “không còn quyền đọc dữ liệu JVM nào”.

Lưu ý, đây là demo **chỉ quan sát class loading**, không phải method tracing. Muốn đo method argument/return thật phải chèn bytecode mới, từ đó phải mở thêm một cuộc review về dữ liệu được đọc.

### 7.3. `src/demo/Work.java`

```java
package demo;

public final class Work {
    public static int calculate(int number) {
        return number * 2;
    }
}
```

Class này chỉ làm mục tiêu để JVM có một lần nạp `demo.Work`. `calculate` không được gọi trong ví dụ, nên **không có method argument hay return value nào phát sinh từ lời gọi này**.

### 7.4. `src/demo/DemoApp.java`

```java
package demo;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] start");
        Class<?> type = Class.forName("demo.Work");
        System.out.println("[app] loaded=" + type.getSimpleName());
        System.out.println("[app] done");
    }
}
```

App chủ động gọi `Class.forName("demo.Work")` **sau** dòng `start` để tạo tình huống dễ quan sát. Mã App không có `Work.class` hay `new Work()` trước đó, tránh liên kết tới `Work` quá sớm trong ví dụ.

### 7.5. `src/audit/JarInspector.java`: kiểm tra manifest, entries và digest

```java
package audit;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Set;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class JarInspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: audit.JarInspector file.jar");
        }
        Path path = Path.of(args[0]);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var in = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            for (int n; (n = in.read(buffer)) != -1;) {
                digest.update(buffer, 0, n);
            }
        }
        String hex = HexFormat.of().formatHex(digest.digest());

        try (JarFile jar = new JarFile(path.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalArgumentException("Missing manifest");
            }
            Attributes attributes = manifest.getMainAttributes();
            String premain = attributes.getValue("Premain-Class");
            int files = 0, classes = 0, services = 0;
            int nestedJars = 0, nativeFiles = 0, versioned = 0, unsafe = 0;
            Set<String> names = new HashSet<>();

            Enumeration<JarEntry> entries = jar.entries();
            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                String name = entry.getName();
                files++;
                if (!names.add(name) || name.startsWith("/")
                        || name.contains("\\")
                        || Arrays.asList(name.split("/")).contains("..")) {
                    unsafe++;
                }
                if (name.endsWith(".class")) classes++;
                if (name.startsWith("META-INF/services/")) services++;
                if (name.endsWith(".jar")) nestedJars++;
                if (name.endsWith(".so") || name.endsWith(".dll")
                        || name.endsWith(".dylib")) nativeFiles++;
                if (name.startsWith("META-INF/versions/")) versioned++;
            }

            System.out.println("[inspect] premain=" + premain);
            System.out.println("[inspect] premainClassPresent=" +
                    (premain != null && jar.getJarEntry(
                            premain.replace('.', '/') + ".class") != null));
            System.out.println("[inspect] canRetransform=" +
                    attributes.getValue("Can-Retransform-Classes"));
            System.out.println("[inspect] bootClassPath=" +
                    attributes.getValue("Boot-Class-Path"));
            System.out.println("[inspect] files=" + files + " classes=" + classes);
            System.out.println("[inspect] services=" + services
                    + " nestedJars=" + nestedJars
                    + " nativeFiles=" + nativeFiles);
            System.out.println("[inspect] versioned=" + versioned
                    + " unsafeEntryNames=" + unsafe);
            System.out.println("[inspect] sha256Length=" + hex.length());
        }
    }
}
```

Giải thích cách sử dụng và **giới hạn** của inspector:

- `MessageDigest("SHA-256")` tính digest thật của file. Ví dụ chỉ in **độ dài chuỗi hex** để stdout không phụ thuộc timestamps/bytes của từng lần tạo JAR; khi cần kiểm tra digest thực phải in/lưu `hex` hoặc dùng `Get-FileHash`/`sha256sum`, rồi **đối chiếu giá trị đáng tin**.
- `JarFile` mở archive để xem `Manifest` và `JarEntry`; **không khởi tạo `SafeAgent`**, không gọi `premain`.
- `premainClassPresent` chỉ kiểm tra tên file class có tồn tại, **không xác minh** method signature hoặc bytecode an toàn.
- Bộ đếm `services`, `nestedJars`, `nativeFiles`, `versioned` đánh dấu một số nhóm entries cần review.
- `unsafeEntryNames` là kiểm tra **cơ bản**, không phải bộ quét path traversal hoàn chỉnh cho mọi platform hoặc một ZIP security scanner.
- Chưa kiểm tra chứng chỉ ký, chưa so digest với release đáng tin, chưa rà toàn bộ dependency, chưa chứng minh không có network I/O.
- Kiểm kê tên entry **không tương đương** kiểm tra behavior. Những thứ mang tính nhạy cảm hoặc bị che giấu có thể xuất hiện trong classfile code, config, strings hoặc component tải sau.

Vì vậy **không** dùng một output `unsafeEntryNames=0` để kết luận JAR đã an toàn. Nó chỉ nói không có dấu hiệu trong tập kiểm tra nhỏ của ví dụ.

### 7.6. `agent.mf`: manifest chủ ý không xin quyền retransform

```text
Manifest-Version: 1.0
Premain-Class: agent.SafeAgent
Can-Retransform-Classes: false

```

Giữ dòng trống kết thúc main section. Manifest chỉ xin startup entry point, không cần `Agent-Class` vì demo không dùng dynamic attach và không cần bootstrap helper JAR.

Nếu agent thật cần capability `Can-Redefine-Classes`, `Can-Retransform-Classes`, `Can-Set-Native-Method-Prefix` hoặc `Boot-Class-Path`, mỗi thay đổi đó phải được **ghi lại trong hồ sơ duyệt** cùng lý do, không mặc định thêm tất cả giá trị `true`.

### 7.7. Biên dịch Java 17 và đóng gói

Từ thư mục `agent-audit-demo` đã chứa source files và `agent.mf`, tạo output directories:

```bash
mkdir out
mkdir out/agent
mkdir out/app
mkdir out/audit
mkdir dist
```

Chỉ cần tạo thư mục một lần. Dùng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out/agent src/agent/SafeAgent.java

javac --release 17 -encoding UTF-8 -d out/app src/demo/Work.java src/demo/DemoApp.java

javac --release 17 -encoding UTF-8 -d out/audit src/audit/JarInspector.java

jar --create --file dist/scope-agent.jar --manifest agent.mf -C out/agent .
```

`JarInspector` dùng `HexFormat`, API có sẵn trên Java 17, nên yêu cầu `javac --release 17` là chính xác. Đừng đưa `DemoApp` vào agent JAR; app và audit tool được giữ riêng để thấy đúng nhiệm vụ từng artifact.

Kết quả khi đóng gói thành công:

```text
dist/scope-agent.jar
out/agent/agent/SafeAgent.class
out/agent/agent/SafeAgent$NameOnlyTransformer.class
out/app/demo/Work.class
out/app/demo/DemoApp.class
out/audit/audit/JarInspector.class
```

Danh sách trên chỉ liệt kê các file đáng chú ý; còn có manifest/resource và các thư mục output khác.

### 7.8. Chạy **inspector trước**, chưa chạy agent

```bash
jar --list --file dist/scope-agent.jar

java -cp out/audit audit.JarInspector dist/scope-agent.jar
```

Stdout của **JarInspector** đã kiểm tra bằng OpenJDK 24.0.2, với source biên dịch `--release 17`:

```text
[inspect] premain=agent.SafeAgent
[inspect] premainClassPresent=true
[inspect] canRetransform=false
[inspect] bootClassPath=null
[inspect] files=3 classes=2
[inspect] services=0 nestedJars=0 nativeFiles=0
[inspect] versioned=0 unsafeEntryNames=0
[inspect] sha256Length=64
```

`files=3`: manifest và hai class files của agent (class chính + nested transformer). `classes=2`: hai class files. `bootClassPath=null`: header không tồn tại trong manifest, không phải JAR bị lỗi. `sha256Length=64` chỉ xác nhận cách trình bày digest SHA-256 dạng hex, **không xác nhận publisher**.

Đọc `jar --list` để xem **chính xác** các entry, không chỉ bộ đếm. Với một JAR lớn, còn phải xem `META-INF/services`, module descriptors, nested libs, native assets, `META-INF/versions`, cấu hình, resource và đường dẫn ngoài manifest.

### 7.9. Kiểm tra chữ ký của **JAR demo chưa ký**

```bash
jarsigner -verify -strict -verbose -certs dist/scope-agent.jar
```

Vì JAR vừa tạo **không được ký**, `jarsigner` trong phép thử đã báo:

```text
jar is unsigned.
```

Trên OpenJDK 24.0.2, lệnh với `-strict` kết thúc bằng mã `16` cho ví dụ này. Các môi trường/JDK khác có thể trình bày diagnostic khác; không dùng số `16` như một hằng “chữ ký không hợp lệ” cho mọi điều kiện.

**Đừng hiểu nhầm:** demo được phép chạy trong bài học vì ta **đã có source và tự biên dịch trong môi trường test**, không phải vì kiểm tra chữ ký đã PASS. Đối với artifact production, tổ chức phải quyết định từ trước chấp nhận những hình thức xác thực nào, ví dụ signer được tin cậy hoặc exact digest từ kênh release đã xác thực. Nếu chính sách đòi chữ ký, JAR demo chưa ký phải bị từ chối ở cổng triển khai thật.

### 7.10. Chỉ sau khi kiểm soát artifact: chạy agent ở chế độ bật

```bash
java -javaagent:dist/scope-agent.jar=allow-demo-work -cp out/app demo.DemoApp
```

Stdout được kiểm tra thực tế:

```text
[agent] allowlist=demo/Work
[app] start
[agent] observed=demo.Work
[app] loaded=Work
[app] done
```

Ý nghĩa:

- `premain` đăng ký transformer có allowlist trước application.
- App in `start`, sau đó chủ động yêu cầu nạp `demo.Work`.
- Transformer thấy tên class khớp và in một dòng đã định nghĩa trước.
- App xác nhận class đã load, rồi kết thúc.
- **Không có log argument, return value, exception message, HTTP body hoặc raw classfile bytes** trong logic demo.

Điểm cuối chỉ là **quan sát output của mã demo đã review**. Nó không cho phép suy luận rằng một agent khác chỉ in tên class sẽ không làm thêm điều gì ở nền.

### 7.11. Chạy agent ở chế độ tắt

```bash
java -javaagent:dist/scope-agent.jar=off -cp out/app demo.DemoApp
```

Stdout:

```text
[agent] collection=off
[app] start
[app] loaded=Work
[app] done
```

`premain` có chạy nhưng không đăng ký transformer, nên không có dòng `[agent] observed=...`. Bài học: **“collection=off” không đồng nghĩa “agent code không thực thi”**. Khi dùng `-javaagent`, JVM vẫn nạp agent class và gọi `premain`; code có thể làm những việc khác ngoài collector. Đây là lý do review entry point vẫn quan trọng.

### 7.12. Chạy ở môi trường cô lập có kiểm soát

Hai lệnh chạy ở mục 7.10–7.11 **chỉ áp dụng cho source/JAR do chính bạn tạo ra** trong ví dụ. Với artifact từ bên ngoài, trước khi chạy cần hoàn tất kiểm tra nguồn gốc, xác thực đúng bytes, rà soát code/dependencies, chính sách thu thập và phê duyệt.

Khi test agent bên ngoài có độ tin cậy chưa rõ, phải cân nhắc sandbox/process/container có network egress được giới hạn, không có production credentials, filesystem tối thiểu và dữ liệu tổng hợp không nhạy cảm. Container đơn thuần **không** là chứng minh tuyệt đối rằng agent không thể vượt boundary; phải cấu hình quyền/isolations thật sự.

## 8. Vì sao inspect JAR không đủ để biết dữ liệu xuất ra?

Một agent có thể cấu hình:

```text
captureArguments=false
captureReturnValue=false
captureExceptionMessage=false
```

nhưng vẫn có thể thu dữ liệu từ:

- `System.getenv`, `System.getProperties`, JVM arguments hoặc file cấu hình.
- HTTP headers, SQL bind variables, thread context, span baggage.
- Exception messages và stack traces do SDK tự động đính kèm.
- Một exporter tự bật debug logging hoặc local spool.
- Custom callback do remote config bật sau startup.
- Service provider hoặc thư viện nằm trong `Class-Path`/nested JAR.
- Một endpoint phụ dành cho diagnostics, crash report hoặc self-update.

Do đó kiểm tra phải đi từ **source → config → runtime behavior → destination**.

Ví dụ một agent chỉ gửi:

```text
duration_ms=12
route=/orders/{id}
status=200
```

vẫn cần đánh giá liệu `route` có đúng là **template** (`/orders/{id}`) hay đôi khi được thay bằng URL thực chứa order ID, email hoặc access token. Một nhãn metric có thể trở thành dữ liệu nhạy cảm nếu cấu hình không kiểm soát.

### 8.1. Thử nghiệm egress và file writes

Trong môi trường được phép kiểm tra, có thể:

1. Chạy application với và không với agent dưới **cùng workload/synthetic inputs**.
2. Ghi các kết nối outbound/destination và thời điểm tạo kết nối.
3. Quan sát DNS, TLS destination metadata, proxy/exporter config và disk spool/log locations.
4. Thu **payload giả lập, không chứa dữ liệu thật** tại collector test được kiểm soát.
5. Tìm các field bị cấm trong **toàn bộ chuỗi**: stdout, log files, temp directories, retry queues, collector attributes, storage/backend.
6. Bật/tắt các feature flags/debug modes có trong tài liệu, không chỉ test cấu hình mặc định.
7. So sánh runtime egress với allowlist endpoint và mục đích thu thập.
8. Kiểm tra hành vi khi exporter lỗi, timeout, offline và retry: dữ liệu có bị ghi xuống disk không?
9. Kiểm tra retention, RBAC và cơ chế xóa ở collector/backend.
10. Cố định kết quả test với **digest artifact và config version** đang chạy.

**Giới hạn của phép thử:** network/payload audit tại một workload chỉ phản ánh những đường code đã được kích hoạt. Nó cần đi cùng static review, dependency inventory, provenance và policy enforcement, không thay thế chúng.

## 9. Kiểm tra điểm vào, loader và phụ thuộc sau startup

Đối với một agent `-javaagent`, phải tìm được `Premain-Class` trong main manifest và method `public static void premain(String, Instrumentation)` hoặc `public static void premain(String)` phù hợp. Khi agent attach động, `Agent-Class` cần `agentmain`.

Không tự giả định toàn bộ code bắt đầu và kết thúc trong method đó:

- `premain` có thể tạo background threads.
- Agent có thể đăng ký transformer callback cho các class load về sau.
- `Class-Path` và `Boot-Class-Path` có thể kéo helper/dependencies ngoài agent JAR.
- Agent có thể sử dụng `Instrumentation.appendToBootstrapClassLoaderSearch`.
- Thêm `ServiceLoader` providers có thể làm code phụ được khởi tạo muộn.
- Một số code nằm trong resource/nested JAR hoặc được tải động.
- Constructor/static initializer của agent/helper có thể có side effects trước khi bật collector.
- Khi attach, `agentmain` có thể hoạt động theo nhánh khác với startup `premain`.

**Tuyên bố “đã đọc `Premain-Class`” không bằng “đã rà hết code có thể chạy”.** Cần rà cả initialization, dependencies và lifecycle (start, reconfigure, stop, attach, detach/rollback nếu hỗ trợ).

### 9.1. Kiểm tra đúng classloader và module

Agent classes thường được system loader định nghĩa; helper có thể được đưa lên bootstrap loader. Thay đổi này không tự làm mọi module read/open. Khi agent chèn lời gọi tới helper, phải kiểm tra:

- Helper JAR đã được duyệt cùng digest hay chưa?
- Có class/package name trùng app/JDK class hay không?
- Bootstrap helper có phụ thuộc một class chỉ do system/custom loader định nghĩa không?
- Có cần `Instrumentation.redefineModule` hoặc module read edges không?
- Tên method/helper có nằm trong allowlist bytecode modifications không?

Rủi ro supply chain có thể nằm ở **JAR phụ**, không chỉ file đứng sau `-javaagent:`. Báo cáo provenance nên bao phủ **transitive dependency closure** thích hợp.

## 10. Cách quản lý cấu hình thu thập một cách có thể kiểm toán

Một control plane an toàn nên phân biệt:

- **Artifact policy**: agent version/digest/signer nào được phép chạy?
- **Instrumentation policy**: class/method nào được phép transform hoặc retransform?
- **Capture policy**: signal và trường nào có thể thu?
- **Transport policy**: dữ liệu nào được phép gửi tới endpoint nào?
- **Retention/access policy**: ai xem và dữ liệu tồn tại bao lâu?

Khi điều chỉnh động, cần lưu **config version** với event để phân biệt dữ liệu tạo bởi cấu hình cũ và mới. Một invocation bắt đầu trước khi đổi filter có thể kết thúc sau đó; nếu chọn per-invocation semantics, phải chốt filter/sampling/sink nhất quán thay vì đọc nhiều phiên bản trong entry/exit.

Không trao quyền remote config để lén đổi từ `metadata-only` sang `capture-args` nếu chưa có phê duyệt tương ứng. Với cấu hình rủi ro cao, nên có server-side policy gate không cho phép bật field bị cấm chỉ bằng một API điều khiển tiện lợi.

### 10.1. Tắt thu thập không đồng nghĩa bỏ toàn bộ code

Ví dụ của bài có mode `off`: `premain` vẫn chạy nhưng không đăng ký transformer. Với agent production đã chèn hook vào class, tắt `enabled` thường chỉ làm **hook bỏ qua ghi event**; `removeTransformer` cũng không tự khôi phục bytecode đã cài trên class đã load.

Nếu quy định yêu cầu không có dữ liệu tiếp tục được xuất sau khi tắt, phải xử lý **in-flight invocations**, queues, disk spool và exporters còn hoạt động. Một biến `enabled=false` đơn lẻ không tự xóa các buffer đã chứa dữ liệu trước đó.

### 10.2. Fail closed với dữ liệu nhạy cảm

Nếu cấu hình chưa hợp lệ, không tìm được allowlist, exporter thiếu xác thực hoặc không có sự đồng ý/phê duyệt cần thiết:

- Không tự chuyển sang `captureAll=true`.
- Không bật debug để log raw payload nhằm “dễ sửa lỗi”.
- Không chuyển dữ liệu sang endpoint dự phòng chưa được phê duyệt.
- Không làm lộ secret trong exception/log của chính agent.
- Ghi một lỗi cấu hình ở mức tối thiểu, không kèm credential.
- Quyết định fail-closed startup hoặc disabled telemetry theo chính sách triển khai.

Việc từ chối thu thập khi không có policy hợp lệ thường an toàn hơn việc rơi vào chế độ thu thập rộng nhất.

## 11. Kiểm tra lỗ hổng và licensing của dependency

Đừng chỉ rà class được ghi trong `Premain-Class`. Agent thường đóng:

- ASM/Byte Buddy và bytecode tooling.
- HTTP/gRPC exporters.
- JSON/serialization libraries.
- Logging frameworks.
- Compression/native libraries.
- SDKs để config, plugins hoặc autodiscovery.

Cần có **dependency inventory hoặc SBOM** gắn với artifact build, kiểm tra phiên bản, giấy phép và lỗ hổng theo chính sách, đồng thời đối chiếu với JAR thực tế. Nếu có shading/fat JAR, tên package đã được relocate có thể làm việc nhận diện dependency chỉ theo đường dẫn `.class` khó hơn.

Một dependency scan sạch **không chứng minh** agent không đọc/tiết lộ dữ liệu. Nó chỉ trả lời một lớp câu hỏi về thành phần/phiên bản và các vấn đề đã biết.

Khi có CVE, cần phân biệt “thư viện có phiên bản bị ảnh hưởng” với “đường code dễ bị khai thác trong cấu hình này”. Không được mặc định vô hại chỉ vì agent chạy bên trong JVM. Hãy đánh giá reachability, exposure và có kế hoạch cập nhật/rollback.

## 12. Nhìn nhận chính xác kết quả kiểm thử

| Quan sát | Có thể kết luận | Không được kết luận |
|---|---|---|
| SHA-256 khớp digest từ nguồn đã xác thực | File đang xét khớp bytes tham chiếu | Mã an toàn hoặc không thu thập bí mật |
| `jarsigner -verify` không báo lỗi | Chữ ký các entries liên quan hợp lệ theo công cụ/policy đã dùng | Toàn bộ artifact đã được tổ chức cấp phép |
| `Premain-Class` tồn tại | Có entry point được khai báo | Method signature và code an toàn đã được kiểm tra |
| `files=3 classes=2` trong ví dụ | Nội dung demo đúng cấu trúc kỳ vọng | JAR lớn khác cũng chỉ có ba file |
| `unsafeEntryNames=0` | Không có dấu hiệu trong heuristic rất nhỏ của inspector | Không có ZIP/path/security problem |
| Agent in `collection=off` | Code demo không đăng ký transformer trong nhánh đó | Agent chưa thực thi bất kỳ instruction nào |
| Không thấy network ở một lần test | Không quan sát được egress trong workload đó | Agent không có mọi đường exfiltration khác |
| Không thấy field nhạy cảm ở collector | Pipeline test không phát hiện field đó tại nơi xem | Raw field chưa từng bị ghi ở log/queue trước redaction |
| Agent `return null` từ transformer | Callback không thay bytes | Callback không đọc/lưu dữ liệu |
| Runtime error-free | Chương trình đã chạy trong điều kiện thử | Agent được phép dùng trên production data |

Bảng này giúp tránh việc “có một tín hiệu PASS” rồi đóng cả ba câu hỏi **nguồn gốc — nội dung — dữ liệu** thành một kết luận không được chứng minh.

## 13. Quy trình phê duyệt trước triển khai production

Một cổng triển khai có thể áp dụng thứ tự:

### Gate A — Artifact và nguồn gốc

1. Xác định publisher và kênh phát hành đã được phê duyệt.
2. Cố định version, release tag, source commit và build identifier.
3. Thu thập provenance/attestation/SBOM khi được yêu cầu.
4. Xác minh attestation signer/build identity và artifact subject digest.
5. Tính SHA-256 JAR **sẽ chạy**, đối chiếu trusted digest.
6. Nếu policy yêu cầu JAR signature, kiểm tra `jarsigner -verify -strict -verbose -certs`, trust chain và unsigned entries.
7. Lưu kết quả kiểm tra vào hồ sơ có người duyệt; không chấp nhận đường dẫn “latest.jar” thay đổi không kiểm soát.

### Gate B — Nội dung và quyền năng

1. Liệt kê JAR entries; kiểm tra manifest entry points/capabilities.
2. Phân tích class/dependency/nested JAR/services/native components/multi-release.
3. Rà code paths trong `premain`, `agentmain`, static initializers và background tasks.
4. Kiểm tra `Class-Path`, `Boot-Class-Path` và helper JARs riêng biệt.
5. Đánh giá transformer filters, class loaders/modules và quyền retransform/redefine.
6. Kiểm tra dependency vulnerabilities/licensing theo chính sách.
7. Xác nhận không có source/code path chưa thể giải trình hoặc lập exception được phê duyệt.

### Gate C — Data collection/egress

1. Chốt class/method allowlist và signals cần thiết.
2. Liệt kê chính xác field được thu, field bị cấm, sampling và privacy classification.
3. Rà các nhánh debug/errors/exception stacks/correlation labels.
4. Chỉ định destination, TLS/auth, region, storage, retention và chủ thể có quyền truy cập.
5. Kiểm thử với **synthetic data**, kết hợp nguồn log, network egress, disk writes và collector payload.
6. Đảm bảo masking/drop áp dụng **trước** những bước giữ/gửi raw field không được phép.
7. Kiểm tra kill switch, remote config policy, rollback và cách xóa data tồn đọng.

### Gate D — Rollout và theo dõi

1. Thử nghiệm trên JVM/application versions mục tiêu, tránh JDK mismatch.
2. Canary rollout với phạm vi nhỏ, đo overhead, allocation, GC, class loading errors và latency.
3. So sánh egress/data fields với baseline và config đã phê duyệt.
4. Ghi artifact digest, agent options, helper JAR digests, policy version ở hệ thống cấu hình.
5. Theo dõi thay đổi quyền/destination/telemetry schema; từ chối phát hành không qua approval.
6. Chuẩn bị rollback (thường cần restart khi không thể bảo đảm bytecode đã cài được gỡ hoàn toàn).
7. Rà định kỳ vì exporter config, policy, endpoint, dependencies và threat model thay đổi theo thời gian.

## 14. Hồ sơ kiểm toán nên ghi những gì?

Một mục kiểm toán có thể chứa:

| Trường | Ví dụ ghi nhận |
|---|---|
| Artifact | Tên, phiên bản, vị trí phát hành đã xác thực |
| SHA-256 | **Digest thực tế** từ artifact cuối, so với nguồn tham chiếu |
| Publisher/signer | Danh tính được xác minh, chứng chỉ/trust policy |
| Build | Source commit, CI build run, build provenance digest |
| SBOM | Version/digest của SBOM và trạng thái dependency review |
| Manifest | `Premain-Class`, `Agent-Class`, `Boot-Class-Path`, `Can-*` |
| Runtime | JDK version, JVM flags, attach policy |
| Instrumentation allowlist | Class/method/loader/module được phép |
| Data fields | Danh sách được phép/không được phép, mục đích |
| Export | Hostname/region, TLS/auth, local spool |
| Retention | TTL, backup retention, deletion process |
| Test evidence | Static scan, jarsigner, egress, sampled payload, test result |
| Review decision | Người duyệt, ngày, rủi ro tồn đọng, điều kiện sử dụng |
| Rollback | Quy trình gỡ, kiểm tra sau gỡ, owner |

Không chép **secret hoặc raw payload nhạy cảm** vào chính hồ sơ kiểm toán. Hồ sơ chứng minh policy và kết quả kiểm tra, không phải nơi nhân bản dữ liệu cần bảo vệ.

Mỗi khi thay JAR, helper JAR, signer, config thu thập, endpoint hoặc feature flag có ảnh hưởng privacy, phải đánh giá lại phần liên quan và cập nhật evidence.

## 15. Một số tình huống cần từ chối hoặc dừng phát hành

**Tình huống A — Digest chỉ do bên gửi JAR cung cấp cùng một kênh không xác thực.** Chưa có nguồn tin cậy độc lập. Không gắn nhãn `provenance verified` chỉ vì digest khớp.

**Tình huống B — JAR có chữ ký nhưng một file `.class` mới là unsigned.** Phải xem coverage và chính sách; không chấp nhận chỉ dựa vào file `.SF` tồn tại.

**Tình huống C — Manifest có `Boot-Class-Path` tới helper ngoài release đã duyệt.** Cần kiểm tra cả helper JAR và nguồn gốc/permissions của nó, không chỉ agent JAR chính.

**Tình huống D — Agent công bố chỉ đo duration nhưng debug mode gửi HTTP request body.** Data scope vượt chính sách; không phát hành với khả năng bật chế độ này nếu không có kiểm soát và phê duyệt.

**Tình huống E — Collector che field nhạy cảm nhưng raw field đã được ghi vào local spool.** Redaction đang đặt quá muộn; cần thay đổi pipeline để ngăn thu giữ/sent raw data ngay từ sớm.

**Tình huống F — Agent được cấp quyền remote config mà không kiểm soát ai có thể bật capture arguments.** Cần policy gate, RBAC/audit trail và kiểm tra cấu hình động.

**Tình huống G — `Can-Retransform-Classes: true` dù use case chỉ cần load-time observation.** Chưa chắc độc hại, nhưng tăng capability được xin mà chưa có lý do; cần giải trình và hạn chế phù hợp.

**Tình huống H — Không thể xác định nơi agent gửi dữ liệu.** Không được suy “không có egress”. Cần review code/dependency + egress test hoặc không chấp nhận trong môi trường nhạy cảm.

**Tình huống I — JAR dùng `Multi-Release: true`, nhưng chỉ bản base được review.** Cần kiểm tra các implementation có thể được runtime JDK mục tiêu chọn.

**Tình huống J — Agent tải code hoặc config từ remote sau khi đã được phê duyệt.** Cần kiểm soát nguồn, integrity, quyền và trạng thái cập nhật; approval JAR lúc đầu không tự bao phủ code tải về sau.

## 16. Bài tập tự kiểm tra

**Câu 1.** Hash SHA-256 của file tải về bằng hash trên một trang không xác thực do chính người gửi kiểm soát. Đã xác thực publisher chưa?

**Đáp án:** Chưa. Phải xác thực nguồn digest/release và nguồn gốc artifact; hash khớp chỉ xác nhận tương ứng bytes với digest đó.

**Câu 2.** JAR ký hợp lệ nhưng chứa exporter tự động gửi argument values. Có được suy agent phù hợp policy “metadata-only” không?

**Đáp án:** Không. Chữ ký không chứng minh behavior hoặc data scope. Phải rà config và đường thu thập/egress.

**Câu 3.** `Can-Retransform-Classes: false` có làm agent không thể dùng network APIs không?

**Đáp án:** Không. Header chỉ liên quan capability retransform, không hạn chế HTTP, file hay logging APIs.

**Câu 4.** `return null` trong `ClassFileTransformer.transform` có nghĩa agent không nhìn thấy bytes không?

**Đáp án:** Không. Callback có thể đã nhận `classfileBuffer`; `return null` chỉ giữ nguyên định nghĩa bytes đối với phép biến đổi đó.

**Câu 5.** Vì sao phải kiểm tra `Boot-Class-Path` khi review supply chain?

**Đáp án:** Nó có thể đưa thêm helper JAR vào bootstrap search path, chứa code không nằm trong JAR chính và có dependency/loader implications.

**Câu 6.** `jarsigner` nói `jar is unsigned` trên JAR tự tạo trong demo. Đây là chữ ký đã PASS hay FAIL?

**Đáp án:** Không có chữ ký để verify. Demo có thể dùng trong môi trường thử do ta kiểm soát; production phải áp dụng policy xác thực được phê duyệt, có thể yêu cầu signed artifact.

**Câu 7.** Cách nào giúp chứng minh data field “Authorization” không được lưu trước khi xuất?

**Đáp án:** Kiểm tra source/config của điểm thu, local log/spool, queue, collector stages và payload synthetic; đặt drop/redaction trước nơi giữ hoặc gửi raw field không được phép.

**Câu 8.** Nếu agent chỉ in `observed=demo.Work`, có thể kết luận từ stdout rằng nó không có network side effects ở mọi workload không?

**Đáp án:** Không. Stdout của một phép thử không kiểm chứng mọi background task hoặc code branch. Phải kết hợp static review và runtime egress monitoring.

**Câu 9.** Một JAR có thêm `META-INF/versions/21/...` nhưng test chạy JDK 17. Có cần review versioned class không?

**Đáp án:** Có khi artifact dự kiến dùng trên JDK 21 hoặc mới hơn; JDK 17 không sử dụng cùng bản implementation. Kiểm tra theo ma trận JVM triển khai.

**Câu 10.** Tại sao `JarInspector` báo `unsafeEntryNames=0` chưa chứng minh JAR an toàn?

**Đáp án:** Chỉ có heuristic nhỏ về tên entry, không phân tích đầy đủ ZIP/bytecode/behavior/trust/signature/data egress.

**Câu 11.** Nếu cấu hình tắt collection, `premain` có còn được gọi không?

**Đáp án:** Có khi đã chạy `-javaagent`. Mode `off` trong demo vẫn in `[agent] collection=off`; việc không đăng ký transformer chỉ giới hạn phần logic demo đó.

**Câu 12.** `jarsigner -verify -strict` có thể báo severe warning ngay khi một số entries không được ký không?

**Đáp án:** Có. Phải xem toàn bộ entries, chứng chỉ/trust, warning và exit code theo policy; không chỉ một câu kết luận.

**Câu 13.** Data thu từ agent có thể trở thành nhạy cảm nếu chỉ gồm class/method names không?

**Đáp án:** Có thể. Tên class/method, package, endpoint patterns có thể tiết lộ kiến trúc nội bộ hoặc hành vi nghiệp vụ, nên vẫn cần mục đích và allowlist.

**Câu 14.** Khi thay exporter endpoint sau deploy nhưng JAR không đổi, có phải review data scope lại không?

**Đáp án:** Có. Destination/retention/access và nơi nhận dữ liệu là thành phần của hợp đồng dữ liệu, không chỉ mã JAR.

## 17. Tổng kết

- Kiểm tra agent cần ba luồng song song: **nguồn gốc artifact**, **nội dung/quyền năng của JAR** và **dữ liệu thực tế được thu thập/xử lý/gửi**.
- **SHA-256** cần một digest tham chiếu đáng tin; **JAR signature** cần kiểm tra coverage, signer và trust; **provenance** phải được verify chứ không chỉ được đính kèm.
- Đọc `Premain-Class`, `Agent-Class`, `Can-*`, `Class-Path`, `Boot-Class-Path`, `Multi-Release`, resources, dependencies và các đường thực thi phụ **trước khi chạy agent**.
- Classfile transformer có thể **nhận thông tin nhạy cảm** ngay cả khi trả `null` và không biến đổi bytes. Phải tách “có quyền đọc” khỏi “đã lưu/xuất dữ liệu”.
- Áp dụng **allowlist, data minimization, kiểm soát exporter, retention và quyền truy cập**; rà cả stdout, file spool, retry queues và remote config.
- Ví dụ Java 17+ cung cấp **công cụ kiểm tra tĩnh JAR**, sau đó mới chạy một startup agent do chính mình tạo, thu một class name được allowlist và không sửa bytecode.
- Đầu ra của một lệnh hay một phép thử **không đủ** để kết luận toàn bộ agent an toàn. Cần kiểm chứng từng điều kiện phát hành và ghi evidence rõ ràng.

## Tài liệu tham khảo

- Oracle JDK 17 — [`java.lang.instrument`: agent startup, dynamic loading, trách nhiệm xác minh agent và manifest attributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- Oracle JDK 17 — [`Instrumentation` API và các capability như `retransformClasses`, `redefineModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle JDK 17 — [`ClassFileTransformer` API và hợp đồng `return null`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- Oracle JDK 17 — [JAR File Specification: manifest, signed JAR, multi-release JAR](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html).
- Oracle JDK 17 — [`jarsigner` manual: `-verify`, `-strict`, certificate checks, unsigned entries](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html).
- SLSA — [Build provenance specification và các thông tin cần xác minh](https://slsa.dev/spec/v1.2/provenance).
- OWASP — [Logging Cheat Sheet: dữ liệu nhạy cảm và những trường nên tránh ghi trực tiếp](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- OpenTelemetry — [Handling sensitive data: minimization, redaction, filtering](https://opentelemetry.io/docs/security/handling-sensitive-data/).
