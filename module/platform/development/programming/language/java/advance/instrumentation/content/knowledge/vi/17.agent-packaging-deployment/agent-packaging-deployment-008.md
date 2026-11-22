# Cấu hình -javaagent qua trình chạy hoặc JAVA_TOOL_OPTIONS với phạm vi rõ ràng

Khi đóng gói và triển khai Java agent, hai cách thường gặp để bật instrumentation ngay lúc JVM khởi động là đặt `-javaagent` **trực tiếp trong lệnh chạy Java** và cung cấp cùng tùy chọn qua biến môi trường **`JAVA_TOOL_OPTIONS`**. Cả hai có thể kích hoạt `premain` trước `main`, nhưng **phạm vi cấu hình** rất khác nhau: tùy chọn gắn vào lệnh chạy cụ thể chỉ phục vụ JVM được tạo bởi lệnh đó, còn biến môi trường có thể được **kế thừa** bởi những tiến trình và JVM con khác.

Điểm cần thiết kế không chỉ là “bật được agent” mà còn là **JVM nào phải có agent, JVM nào tuyệt đối không cần, và ai chịu trách nhiệm cung cấp JAR/đường dẫn/tùy chọn đó**. Một cấu hình môi trường quá rộng có thể khiến cả Gradle, Maven, lệnh quản trị hoặc JVM phụ vô tình chạy agent; một đường dẫn chỉ tồn tại trên máy developer có thể khiến tiến trình production không khởi động.

Bài này hướng dẫn cú pháp, phạm vi, ví dụ Java 17+ có thể chạy, shell/Windows/container/service, kiểm thử và vận hành an toàn. Chủ đề thuộc phần **Đóng gói và triển khai** của Java Advance – Instrumentation.

## 1. Cần phân biệt ba loại phạm vi

Từ "phạm vi" trong triển khai agent có ít nhất ba tầng:

1. **Phạm vi khởi động JVM:** process nào được đưa tùy chọn `-javaagent` lúc tạo JVM. Đây là nội dung chính của bài.
2. **Phạm vi biến đổi lớp:** sau khi đã nạp vào một JVM, transformer được phép xử lý những lớp/module/class loader nào. `-javaagent` tự nó không có cú pháp chọn package ứng dụng; agent phải tự lọc bằng cấu hình/allowlist.
3. **Phạm vi dữ liệu đo:** probe ghi sự kiện cho request, tenant, endpoint hay môi trường nào. Điều này thuộc logic của agent, không phải quyền hạn mà launcher tự suy ra.

Ví dụ: `JAVA_TOOL_OPTIONS` được khai báo cho đúng một container ứng dụng, nhưng transformer trong container đó quét mọi lớp và instrument cả thư viện; **phạm vi process hẹp không đồng nghĩa phạm vi bytecode hẹp**. Ngược lại, một agent lọc đúng package có thể vẫn khởi tạo ngoài ý muốn trong các tiến trình build nếu biến môi trường bị export quá rộng.

## 2. Cơ chế cơ bản của `-javaagent`

Cú pháp chuẩn:

```text
-javaagent:<agent-jar-path>[=<agent-options>]
```

Ở đây:
- `<agent-jar-path>` là đường dẫn tới **JAR agent** có manifest chính chứa `Premain-Class`.
- `<agent-options>` là **một chuỗi** truyền vào tham số `String agentArgs` của `premain`. Java Instrumentation **không định nghĩa chung** cú pháp key/value: agent tự phân tích chuỗi nếu cần.
- JVM nạp agent, gọi `public static void premain(String agentArgs, Instrumentation inst)` trước khi chạy `main` ứng dụng. Có chữ ký dự phòng một tham số theo đặc tả.
- Nếu JVM không thể mở JAR, không tải được lớp agent, thiếu chữ ký `premain` phù hợp hoặc `premain` ném lỗi không bắt, **startup agent thất bại và JVM hủy khởi động trước `main`**.
- Có thể dùng nhiều tùy chọn `-javaagent`; các `premain` được gọi theo thứ tự agent mà JVM nhận được. **Không mặc định hai agent tương tác an toàn**, nhất là cùng instrument một phương thức.

Ví dụ lệnh khởi động một JAR ứng dụng:

```bash
java -javaagent:/opt/agents/metrics-agent.jar=service=orders -jar /opt/apps/orders.jar
```

Tùy chọn JVM phải nằm **trước** main class hoặc `-jar`. Lệnh sau **không bật agent**, vì `-javaagent:...` ở phía sau app JAR có thể chỉ trở thành đối số của `main(String[] args)`:

```bash
# SAI nếu mục tiêu là cấu hình JVM:
java -jar /opt/apps/orders.jar -javaagent:/opt/agents/metrics-agent.jar
```

Một agent JAR không tự là một ứng dụng: cần `Premain-Class` cho startup agent, không nhầm với `Main-Class` của executable application JAR. `-javaagent` và `-jar` có vai trò khác nhau, có thể sử dụng đồng thời.

## 3. Cấu hình trực tiếp từ trình chạy: phạm vi một JVM rõ nhất

Với quyền sửa command hoặc startup script, lựa chọn dễ theo dõi là đặt agent trên đúng lệnh khởi động JVM cần đo.

### 3.1. Lệnh Java trực tiếp

```bash
java -javaagent:/opt/agents/metrics-agent.jar=service=orders -Xms256m -Xmx1g -jar /opt/apps/orders.jar
```

Hoặc chạy bằng classpath:

```bash
java -javaagent:/opt/agents/metrics-agent.jar=service=orders -cp /opt/apps/classes com.example.Main
```

**Phạm vi:** JVM mà chính lệnh `java` ấy tạo ra. Những lệnh Java chạy độc lập sau đó không tự nhận agent, trừ khi script hoặc process launcher cũng cấu hình cho chúng.

Ưu điểm: dễ đọc qua command, chủ động theo service, dễ thay đổi riêng cho staging/production và không vô tình áp dụng cho cả shell. Hạn chế: cần kiểm soát lệnh khởi động thực tế; nếu framework/service wrapper sinh command ẩn, phải cấu hình qua nơi wrapper hỗ trợ truyền JVM arguments.

### 3.2. Startup script có `exec`

Tệp `run-orders.sh`, minh họa trên Linux:

```sh
#!/bin/sh
set -eu

exec java \
  -javaagent:/opt/agents/metrics-agent.jar=service=orders \
  -Xmx1g \
  -jar /opt/apps/orders.jar
```

`exec` thay thế shell bằng tiến trình `java`; cách này thường phù hợp với quản lý tín hiệu trong container/service script. **Không** thêm `JAVA_TOOL_OPTIONS` toàn cục chỉ vì muốn cấu hình cho một service có lệnh chạy rõ ràng.

Nếu ứng dụng được tạo bởi Maven/Gradle, IDE, test runner, app server hoặc service wrapper, cần xác định **JVM nào đang chạy code**. JVM chạy Maven/Gradle có thể khác JVM fork để chạy test hoặc server; cấu hình sai nơi sẽ attach agent vào tool thay vì ứng dụng, hoặc vào cả hai.

### 3.3. Path và quoting

Tốt nhất dùng đường dẫn tuyệt đối, ổn định và **không chứa khoảng trắng** trong production. Nếu đường dẫn chứa khoảng trắng, shell phải truyền toàn bộ `-javaagent:<path>[=<options>]` thành **một đối số**; ví dụ:

```bash
java "-javaagent:/opt/my agents/metrics-agent.jar=service=orders" -jar /opt/apps/orders.jar
```

Dấu nháy trong ví dụ chỉ giúp **shell** gom đối số; JVM cuối cùng nhận một argument. Khi cùng tùy chọn được đặt trong `JAVA_TOOL_OPTIONS`, cú pháp tách token/quote do JVM xử lý **khác với shell**, nên giải pháp ít rủi ro nhất là dùng đường dẫn không chứa khoảng trắng, kiểm thử cách parse trên runtime mục tiêu. Tránh giả định mọi biến môi trường đều được shell expand lần thứ hai.

## 4. `JAVA_TOOL_OPTIONS`: phạm vi theo môi trường tiến trình

`JAVA_TOOL_OPTIONS` là biến môi trường JVM có thể đọc khi tạo máy ảo, được tài liệu Oracle mô tả tại thời điểm gọi **`JNI_CreateJavaVM`**. Giá trị của nó được thêm vào tập tùy chọn khởi tạo JVM và có thể chứa `-javaagent`. Vì vậy nó đặc biệt hữu ích khi lệnh Java nằm sâu trong script/wrapper hoặc một chương trình native tạo JVM qua JNI.

Ví dụ trên Linux/macOS:

```bash
JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=service=orders" \
  java -jar /opt/apps/orders.jar
```

Dạng này gán biến **cho đúng lệnh**; shell hiện tại không bị export thay đổi lâu dài. Tuy nhiên, nếu chính tiến trình Java đó sinh tiến trình con và tiến trình con kế thừa environment, một JVM con khác vẫn có thể đọc cùng biến này. Vì vậy phát biểu chặt chẽ là: **gắn environment cho cây tiến trình được tạo từ lệnh đó**, không phải một cam kết kỹ thuật rằng chỉ duy nhất một JVM sẽ thấy nó.

Nếu export trong shell:

```bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=scope=shell"

java -jar /opt/apps/orders.jar
java -version

unset JAVA_TOOL_OPTIONS
```

Mọi JVM được tạo từ môi trường shell ấy **trong khoảng biến còn được thiết lập**, kể cả lệnh `java -version` hoặc chương trình Java do script sinh ra, đều có thể cố tải agent. Trong HotSpot, thường có dòng `Picked up JAVA_TOOL_OPTIONS: ...` ở **stderr**. Dòng này là tín hiệu chẩn đoán, không phải API hay định dạng log được đảm bảo giống nhau ở mọi JVM.

### 4.1. Vì sao `JAVA_TOOL_OPTIONS` không giống shell script thêm `-javaagent`?

Một shell script trực tiếp chỉ thêm tùy chọn vào **lệnh nó tạo**. Còn biến môi trường tồn tại trong **environment của tiến trình** và thường được truyền xuống tiến trình con theo quy tắc OS/launcher. Một lệnh như:

```bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=scope=global"
./start-all-services.sh
```

có thể làm nhiều Java process được script `start-all-services.sh` tạo ra cùng mang agent, kể cả service không nằm trong mục tiêu khảo sát. Nếu một JVM con không có đường dẫn `/opt/agents/metrics-agent.jar` tương ứng, startup có thể thất bại.

Trong môi trường đặc quyền hoặc một số cấu hình bảo mật, JVM có thể **không chấp nhận** hoặc **bỏ qua** `JAVA_TOOL_OPTIONS`. Vì vậy phải kiểm chứng trên runtime thực tế, không coi việc set biến là bằng chứng chắc chắn agent đã nạp.

### 4.2. Khi nào nên chọn biến môi trường?

Chọn `JAVA_TOOL_OPTIONS` khi:
- không thể chỉnh chính xác lệnh Java, nhưng có quyền cung cấp **environment cho đúng service/container**;
- hệ thống có wrapper/native launcher tạo JVM mà bạn cần cấu hình;
- muốn dùng một chính sách triển khai cấp process/container, có giới hạn rõ trong orchestrator;
- đã kiểm tra không có JVM phụ bị ảnh hưởng và JAR có thể được truy cập ở tất cả nơi có biến.

Không chọn biến global ở cấp máy hoặc toàn bộ phiên terminal khi chỉ muốn đo một ứng dụng. Đặc biệt tránh gán rộng trong file shell profile, environment toàn bộ node, CI runner hoặc base image được tái sử dụng bởi nhiều nhiệm vụ, nếu chưa chủ động chấp nhận phạm vi đó.

## 5. Bảng quyết định phạm vi triển khai

| Nơi cấu hình | JVM nào có thể nhận agent? | Khi phù hợp | Rủi ro phải kiểm soát |
| --- | --- | --- | --- |
| `java -javaagent:... -jar app.jar` | JVM do **lệnh đó** tạo | Một ứng dụng, command kiểm soát được | Command thực tế có thể khác command tưởng tượng |
| JVM arguments của launcher/service wrapper | JVM mà wrapper truyền arguments tới | Application server, test runner, run configuration | Đặt nhầm vào JVM của chính build tool hoặc bỏ sót fork |
| `JAVA_TOOL_OPTIONS=... java ...` cho một lệnh POSIX | JVM tạo từ lệnh và JVM con kế thừa env | Thử nghiệm nhanh, một run cụ thể | JVM con bị ảnh hưởng nếu được spawn |
| `export JAVA_TOOL_OPTIONS=...` trong shell | Các tiến trình/JVM tương lai có env kế thừa từ shell | Chỉ khi thật sự muốn phạm vi shell | Build tools, lệnh `java -version`, utility Java cũng nhận |
| `JAVA_TOOL_OPTIONS` trong môi trường của một service | Service JVM và process/JVM con kế thừa | Không sửa được `ExecStart` | Khởi động lại service mới có hiệu lực; JVM con bị ảnh hưởng |
| Env của **một container** | JVM trong container đó (và các tiến trình con) | Docker/Pod container đã cô lập | Phải có agent JAR trong filesystem container |
| Env được khai báo trên container của Pod | Container được chỉ định, không tự lan sang container khác | Kubernetes có workload nhiều container | Không tự có JAR; rollout/restart để áp dụng |
| Environment toàn node/CI runner | Nhiều tiến trình JVM, kể cả build/test | Chỉ khi cố ý áp dụng toàn bộ | Phạm vi quá rộng, dễ gây startup failure |

**Không có cách nào trong bảng tự giới hạn những class sẽ được instrument.** Sau khi agent được nạp, bộ lọc transformer/agent configuration quyết định lớp nào bị biến đổi.

## 6. Ví dụ Java 17+ chạy được: quan sát trực tiếp và qua môi trường

Thí nghiệm không dùng thư viện ngoài. Agent chỉ in `agentArgs` trong `premain` để kiểm chứng **JVM nào đã tải agent**. Ứng dụng in một dòng từ `main`. Ví dụ cố ý không biến đổi bytecode, vì mục tiêu là **cấu hình khởi động**.

Cấu trúc dự án:

```text
agent-scope-demo/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── ScopeAgent.java
│   └── demo/
│       └── Main.java
└── out/
```

### 6.1. Agent entry point

Tệp `src/agent/ScopeAgent.java`:

```java
package agent;

import java.lang.instrument.Instrumentation;

public final class ScopeAgent {
    private ScopeAgent() {}

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("agent: " + agentArgs);
    }
}
```

`Premain-Class` trỏ tới `agent.ScopeAgent`. `agentArgs` ở đây được in nguyên văn, không có parser tự động của JVM biến `source=direct` thành key/value. Trong agent sản xuất, parser và xác thực cấu hình phải do agent thực hiện, có kiểm soát và không ghi thông tin bí mật.

### 6.2. Ứng dụng đơn giản

Tệp `src/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app: " + String.join(",", args));
    }
}
```

Tệp `agent.mf` với dòng trống cuối file:

```text
Manifest-Version: 1.0
Premain-Class: agent.ScopeAgent

```

### 6.3. Biên dịch và đóng gói

Trên Linux/macOS, tạo thư mục output:

```bash
mkdir -p out
```

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Chạy ở thư mục dự án với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out src/agent/ScopeAgent.java src/demo/Main.java
jar --create --file scope-agent.jar --manifest agent.mf -C out agent
```

Chỉ lớp trong package `agent` được đóng vào JAR này; ứng dụng chạy từ `out`. Nếu đóng gói độc lập cho production, cần phối hợp version agent/app và bảo đảm mọi dependency của agent có thể được nạp.

### 6.4. Cách A: `-javaagent` trong command

```bash
java -javaagent:scope-agent.jar=source=direct -cp out demo.Main hello
```

**Stdout chính xác** trong thí nghiệm:

```text
agent: source=direct
app: hello
```

Vì JVM gọi `premain` trước `main`, dòng của agent xuất hiện trước dòng ứng dụng.

### 6.5. Cách B: `JAVA_TOOL_OPTIONS` cho một lệnh

Với shell POSIX, từ thư mục dự án, dùng đường dẫn tuyệt đối qua `$PWD`:

```bash
JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=source=env" \
  java -cp out demo.Main hello
```

Stdout phần chương trình:

```text
agent: source=env
app: hello
```

Trên OpenJDK/HotSpot đã kiểm thử, JVM còn in ở **stderr** một dòng kiểu:

```text
Picked up JAVA_TOOL_OPTIONS: -javaagent:/absolute/path/to/scope-agent.jar=source=env
```

`/absolute/path/to` là đường dẫn thực tế của máy chạy, không phải dòng chữ cố định do chương trình Java in ra. Không nhầm thông báo stderr này với stdout của thí nghiệm.

### 6.6. Cách C: không có agent

Bảo đảm shell không còn `JAVA_TOOL_OPTIONS` hoặc tùy chọn agent khác, sau đó chạy:

```bash
java -cp out demo.Main hello
```

Stdout:

```text
app: hello
```

Nếu vẫn thấy dòng `agent:`, cần kiểm tra các nguồn cấu hình khác: `JAVA_TOOL_OPTIONS` đang được kế thừa, `JDK_JAVA_OPTIONS` của launcher, JVM arguments trong wrapper hoặc agent khác.

### 6.7. Cách D: bật ở cả environment và command

**Không nên dùng trong vận hành trừ khi cố ý muốn nhiều agent.** Thí nghiệm này minh họa sự cộng dồn:

```bash
JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=source=env" \
  java -javaagent:scope-agent.jar=source=direct -cp out demo.Main hello
```

Trên OpenJDK 21.0.12.1 đã kiểm thử, stdout là:

```text
agent: source=env
agent: source=direct
app: hello
```

Điều này **không phải hai cấu hình gộp thành một agent**; trong ví dụ, cùng agent JAR được khởi chạy hai lần. Với một agent production cài hook, thread, exporter hay transformer, nạp hai lần có thể gây trùng instrumentation và số liệu. Trong môi trường có nhiều tool/launcher, luôn kiểm tra danh sách options cuối cùng và thứ tự các agent thay vì suy diễn từ một biến cấu hình riêng lẻ.

**Xác minh đã thực hiện:** Mã của ví dụ được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 21.0.12.1 ở bốn trường hợp trên; stdout tương ứng đúng như đã ghi. Đây là kiểm thử cho ví dụ, **không phải cam kết rằng mọi JVM sẽ in stderr giống HotSpot**.

## 7. Linux/macOS: đặt biến đúng một lệnh hay cả shell?

### 7.1. Một lần chạy, không làm bẩn shell

```bash
env JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=scope=one-run" \
  java -cp out demo.Main hello
```

Cú pháp `env NAME=value command` tạo environment cho command; sau khi lệnh kết thúc, shell gọi `env` không tự giữ biến. Nhưng như đã nêu, **process con do command tạo ra** vẫn có thể kế thừa môi trường.

### 7.2. `export` cho chuỗi lệnh, rồi `unset`

```bash
export JAVA_TOOL_OPTIONS="-javaagent:$PWD/scope-agent.jar=scope=session"

java -cp out demo.Main one
java -cp out demo.Main two

unset JAVA_TOOL_OPTIONS
```

Cả hai Java process đều có khả năng nạp agent. Nếu chỉ định bật cho một process, dùng dạng một lệnh hoặc cấu hình trực tiếp sẽ ít rủi ro hơn.

### 7.3. Tránh đặt vĩnh viễn vào shell profile

Một dòng `export JAVA_TOOL_OPTIONS=...` trong `.bashrc`, `.profile` hoặc thiết lập môi trường toàn máy có thể lan đến script build, ứng dụng không liên quan và công cụ quản trị. Nếu agent JAR được thay thế/xóa hoặc path không hợp lệ, nhiều Java command có thể cùng hỏng ngay khi khởi động. Đối với production, đưa cấu hình vào nơi quản lý của **workload sở hữu agent**.

## 8. Windows PowerShell: đặt trong session và hoàn nguyên

Trong PowerShell, đặt biến cho environment của **tiến trình PowerShell hiện tại**; những tiến trình con được tạo sau đó sẽ kế thừa trừ khi có cấu hình khác:

```powershell
$env:JAVA_TOOL_OPTIONS = "-javaagent:C:\agents\scope-agent.jar=scope=local"
java -cp out demo.Main hello
Remove-Item Env:\JAVA_TOOL_OPTIONS
```

Nếu environment trước đó đã có giá trị, dùng `Remove-Item` có thể vô tình xóa cấu hình của người dùng. Để thử nghiệm có thể hoàn nguyên:

```powershell
$previous = $env:JAVA_TOOL_OPTIONS
try {
    $env:JAVA_TOOL_OPTIONS = "-javaagent:C:\agents\scope-agent.jar=scope=test"
    java -cp out demo.Main hello
}
finally {
    if ($null -eq $previous) {
        Remove-Item Env:\JAVA_TOOL_OPTIONS -ErrorAction SilentlyContinue
    }
    else {
        $env:JAVA_TOOL_OPTIONS = $previous
    }
}
```

Cả hai đoạn yêu cầu agent JAR tồn tại ở `C:\agents\scope-agent.jar`. Đường dẫn `C:\agents\... ` chỉ là ví dụ triển khai, **không phải đường dẫn mà ví dụ biên dịch ở mục 6 tự tạo ra**. Khi vừa build bằng `jar` trong thư mục hiện tại, có thể dùng đường dẫn tuyệt đối tương ứng, nhưng nên tránh khoảng trắng trong path để giảm lỗi phân tích tùy chọn.

Đừng chỉnh environment toàn hệ thống bằng registry hoặc thay đổi permanent machine-level settings chỉ để thử agent trên một service.

## 9. Docker/container: môi trường của từng container

Ví dụ chỉ mang tính cấu hình, giả sử container image đã có `/opt/agents/metrics-agent.jar` và ứng dụng ở `/app/app.jar`.

**Cách A: để command của container bật agent**

```dockerfile
FROM eclipse-temurin:21-jre
COPY app.jar /app/app.jar
COPY metrics-agent.jar /opt/agents/metrics-agent.jar
ENTRYPOINT ["java", "-javaagent:/opt/agents/metrics-agent.jar=scope=api", "-jar", "/app/app.jar"]
```

Ở cách này, một lần chạy container sẽ tạo JVM có agent trực tiếp trong command. File Dockerfile là **ví dụ minh họa**, cần có `app.jar` và `metrics-agent.jar` tương ứng trong build context.

**Cách B: image giữ nguyên ENTRYPOINT, chỉ container cần đo mới nhận biến**

```bash
docker run --rm \
  -e JAVA_TOOL_OPTIONS="-javaagent:/opt/agents/metrics-agent.jar=scope=api" \
  my-java-api:1.0
```

Giả sử `my-java-api:1.0` đã chứa agent JAR ở đường dẫn đó. Nếu không, cần đóng gói JAR trong image hoặc mount volume thích hợp. Dùng môi trường riêng cho container cần quan sát giúp tránh biến agent thành chính sách vô tình của toàn host.

**Lưu ý:** nếu image chứa nhiều Java command trong cùng container, mọi JVM kế thừa `JAVA_TOOL_OPTIONS` có thể khởi động agent. Một container không đồng nghĩa một JVM duy nhất. Cũng không nên đưa `ENV JAVA_TOOL_OPTIONS=...` vào base image được dùng để build hoặc chạy nhiều service nếu chưa quyết định rõ phạm vi ảnh hưởng.

## 10. Kubernetes: khai báo cho container cụ thể

Ví dụ fragment của một Kubernetes Deployment, **không phải manifest độc lập**:

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          image: example/api:1.0
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-javaagent:/opt/agents/metrics-agent.jar=scope=api"
```

Kubernetes cung cấp biến môi trường vào **container `api`** được khai báo ở đây. Container khác trong cùng Pod không tự nhận biến này, trừ khi cũng được cấu hình. File `metrics-agent.jar` phải đã có trong image `example/api:1.0`, hoặc được cấp vào filesystem container bằng cơ chế volume/init container thích hợp.

Để giới hạn rollout:
- Khai báo agent chỉ trên workload/pod template cần quan sát, không dùng một biến toàn cluster nếu không có yêu cầu.
- Dùng image/JAR version bất biến, có checksum/nguồn gốc rõ ràng.
- Thử trước trên một replica/canary; theo dõi startup, readiness, lỗi liên kết và overhead.
- Khi sửa env của Pod template, cần rollout tạo **Pod/JVM mới**; JVM đang chạy không đột nhiên đọc lại `JAVA_TOOL_OPTIONS`.
- Nếu agent xảy ra lỗi startup, pod có thể lặp crash/restart; phải có phương án quay lại cấu hình hoặc image trước.

Cần phân biệt **phạm vi container env**, **phạm vi JVM start** và **phạm vi class mà agent instrument**. Đây là ba quyết định riêng.

## 11. Service manager, build tool và launcher lồng nhau

### 11.1. Service manager

Ví dụ fragment systemd trên Linux, với JAR thật sự tồn tại ở path tương ứng:

```ini
[Service]
Environment="JAVA_TOOL_OPTIONS=-javaagent:/opt/agents/metrics-agent.jar=scope=orders"
ExecStart=/usr/bin/java -jar /opt/apps/orders.jar
```

Tùy chọn đặt trong environment của service thay vì export toàn máy. Nếu service có tiến trình con Java kế thừa environment, chúng cũng có thể chịu ảnh hưởng. Sau khi chỉnh unit cấu hình, cần nạp lại cấu hình service manager (khi cần) và **restart service** để tạo JVM mới; chỉ sửa file unit không thay đổi một JVM đã chạy.

Có thể chọn đặt `-javaagent` trực tiếp trong `ExecStart` nếu đây là một Java service có command ổn định; cách đó có phạm vi rõ hơn biến environment nếu service tạo Java subprocess.

### 11.2. Maven/Gradle và test runner

Một lệnh như `mvn test` có thể tạo JVM để chạy Maven và thêm JVM test fork. `gradle test` cũng có JVM daemon/launcher và worker/test process tùy cấu hình. Do đó:

- Nếu mục tiêu là **test JVM**, hãy dùng cấu hình JVM arguments của test runner/fork (ví dụ Maven Surefire `argLine`, Gradle `Test.jvmArgs`) phù hợp project.
- Nếu mục tiêu là **ứng dụng chạy bởi plugin**, hãy dùng JVM arguments của task `JavaExec`/plugin chạy ứng dụng, không vội gán env global cho Gradle/Maven.
- Nếu dùng `JAVA_TOOL_OPTIONS` ở cấp shell của build job, có thể tác động cả JVM của công cụ build lẫn JVM fork nếu môi trường được kế thừa.
- Khi tool cũng gắn Java agent khác (coverage/profiler), phải phối hợp thứ tự và cách kết hợp arguments; không vô tình ghi đè cấu hình agent của công cụ.

Ví dụ cấu hình Gradle Groovy DSL, chỉ có ý nghĩa khi project đã có task JavaExec tên `run` (chẳng hạn plugin `application`):

```groovy
tasks.named('run', JavaExec) {
    jvmArgs '-javaagent:/opt/agents/metrics-agent.jar=scope=app-run'
}
```

Đây là **đoạn cấu hình task, không phải chương trình độc lập**. Nó đặt tùy chọn cho JVM mà task `run` khởi tạo, không cần dùng `JAVA_TOOL_OPTIONS` ở daemon Gradle.

### 11.3. Trình chạy từ JNI

Khi một launcher native tạo JVM qua JNI Invocation API, người vận hành đôi khi không có cơ hội sửa command `java` vì không hề có lệnh `java` hiển thị. Theo tài liệu Oracle, `JAVA_TOOL_OPTIONS` được xem xét ở `JNI_CreateJavaVM`, nên có thể giải quyết trường hợp này khi implementation cho phép. Nhưng nó **không thể thay thế những lựa chọn chỉ do Java launcher phân tích**, chẳng hạn kiểu chọn launcher VM trong một số nền tảng.

**Đừng nhầm `JAVA_TOOL_OPTIONS` với `JDK_JAVA_OPTIONS`.** Trên các JDK hỗ trợ, `JDK_JAVA_OPTIONS` được Java **launcher** đọc và thêm vào command-line arguments của launcher; còn `JAVA_TOOL_OPTIONS` được xét lúc tạo JVM. `JDK_JAVA_OPTIONS` không tự động giúp một ứng dụng native tự tạo JVM qua JNI, vì ứng dụng đó có thể không dùng Java launcher.

## 12. Trường hợp cả command và env cùng có agent

Sự kết hợp có thể xảy ra do:
- image có `ENTRYPOINT ["java", "-javaagent:..."]`;
- hệ thống triển khai lại đặt `JAVA_TOOL_OPTIONS=-javaagent:...`;
- một launcher hoặc framework đưa thêm agent của nó;
- `JDK_JAVA_OPTIONS` cũng chứa tùy chọn agent.

Không nên nói đơn giản “command-line ghi đè environment”. Với **các `-javaagent`**, đó không phải cặp giá trị cấu hình một khóa để chọn một trong hai; JVM có thể **khởi chạy nhiều agent**. Trên HotSpot trong ví dụ mục 6, agent từ `JAVA_TOOL_OPTIONS` chạy trước agent được ghi trực tiếp, nhưng đừng mặc định thứ tự y hệt trên mọi chuỗi wrapper và JVM configuration khác. Điều cần bảo đảm là **tập agent thực tế** và các `premain` được gọi đúng mong đợi.

Cách phòng:
1. Chọn **một chủ sở hữu cấu hình** cho từng workload: command/startup script hoặc môi trường workload.
2. Kiểm tra `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và flags do service wrapper/tool cung cấp.
3. Đảm bảo không vô tình chỉ định cùng agent hai lần.
4. Nếu chủ ý dùng nhiều agent, chạy kiểm thử tương tác trên đúng Java version: thứ tự transformer, thứ tự callback, lớp helper và tác động hiệu năng.
5. Cấu hình agent cần idempotent khi có thể; nhưng không nên dựa vào idempotence để che lỗi triển khai trùng.

## 13. Thay đổi, tắt agent và rollback

`-javaagent` là tùy chọn **khởi động JVM**; `JAVA_TOOL_OPTIONS` được đọc khi JVM được tạo. Vì vậy:

- Bỏ `-javaagent` khỏi command rồi **khởi động một JVM mới** để có process mới không tải agent đó.
- Xóa `JAVA_TOOL_OPTIONS` của một shell/service/container rồi tạo process mới; JVM **đang chạy** không tự gỡ agent hoặc bytecode đã transform.
- Không dùng `unset JAVA_TOOL_OPTIONS` trong shell để kết luận tất cả JVM cũ đã ngừng đo; đó chỉ thay đổi môi trường cho lần khởi động sau.
- Java Instrumentation có cơ chế **dynamic attach/agentmain** trên một số JVM, nhưng đó là một đường triển khai **khác** với startup `premain` được bàn ở đây; không coi attach là hành vi của `JAVA_TOOL_OPTIONS`.
- Nếu agent tự hỗ trợ soft-off/hard-off, cần đánh giá cách nó gỡ probe bằng retransformation và những class đã được biến đổi, không suy từ việc đổi JVM option.

Kế hoạch rollback production tối thiểu: giữ một cấu hình/image trước agent, biết cách khởi động lại workload, có canary, quan sát startup failure và đảm bảo agent JAR có thể được thu hồi mà không làm hỏng deployment.

## 14. Bảo mật và kiểm soát cấu hình

`-javaagent` mang ý nghĩa đặc quyền cao: agent thực thi mã Java trong cùng tiến trình JVM với ứng dụng, có thể quan sát/chỉnh bytecode và ảnh hưởng tính ổn định. Vì vậy:

- Chỉ tải agent JAR từ nguồn đáng tin, chốt phiên bản, kiểm tra checksum/signature khi phù hợp.
- Quy định chính xác team/workload nào được sửa JVM arguments hoặc `JAVA_TOOL_OPTIONS`; tránh cấu hình môi trường toàn node khi không cần.
- Agent JAR phải có quyền đọc cho user chạy JVM, không cho phép ứng dụng không tin cậy thay thế JAR.
- Không đặt token, mật khẩu, khoá riêng vào chuỗi agent options nếu có thể: command line, environment và log startup có thể lộ thông tin. Dùng cơ chế bí mật và quyền truy cập phù hợp theo thiết kế của agent.
- Chọn path được quản lý, ít bất ngờ; tránh wildcard hoặc phụ thuộc vào current working directory của service.
- Kiểm tra tương thích JDK, JPMS, class loader, yêu cầu Java Instrumentation capability và tác động lên startup, memory, CPU.
- Agent startup lỗi có thể **ngăn ứng dụng khởi động**; trước rollout phải kiểm thử trường hợp thiếu JAR, JAR sai manifest và config sai.
- Khi ghi telemetry xác nhận `premain`, chỉ ghi thông tin không nhạy cảm: trạng thái bật, phiên bản agent, tên service đã được duyệt, không dump nguyên chuỗi bí mật.

## 15. Chẩn đoán cấu hình không có hiệu lực

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| `premain` không chạy khi dùng command | `-javaagent` có ở **trước** main class/`-jar` không? Agent JAR và `Premain-Class` hợp lệ không? |
| Lệnh chạy báo không tìm thấy agent JAR | Đường dẫn có tồn tại **bên trong filesystem của process/container** không? Quyền đọc và working directory? |
| App không khởi động sau khi bật agent | Đọc stderr và exception startup, phiên bản JDK, lỗi trong `premain`, dependency của agent |
| `JAVA_TOOL_OPTIONS` được set nhưng không có `premain` | Environment có thực sự vào process tạo JVM không? JVM có hỗ trợ và không chặn biến không? Có dùng JNI hay launcher khác? |
| `java -version` cũng chạy agent | Biến môi trường có phạm vi shell/system quá rộng |
| Maven/Gradle bị agent làm chậm hoặc lỗi | `JAVA_TOOL_OPTIONS` bị kế thừa bởi JVM build tool thay vì chỉ test/app JVM |
| Mỗi event có vẻ đo hai lần | Command và env cùng chứa agent; hai agent/transformer cùng chèn probe |
| Set env mới nhưng app cũ không thay đổi | App/JVM đang chạy cần được khởi động lại; env chỉ được đọc khi khởi tạo JVM |
| Container báo thiếu JAR | JAR chưa được COPY/mount đúng path trong **container**, dù host có file |
| Có `premain` nhưng không có probe | Kiểm tra cấu hình allowlist/transformer, module/loader visibility, loại class được instrument và hook runtime |
| Agent chỉ chạy trên vài Pod | Pod template, canary, rollout, env từng container, image và version giữa replica |

**Cách xác minh gọn nhất:** cho agent in/tạo một chỉ báo khởi động an toàn, kiểm tra log có `premain` và build/version; sau đó xác minh đúng process/Pod/service mới nhận agent. Dòng `Picked up JAVA_TOOL_OPTIONS` của HotSpot ở stderr chỉ là tín hiệu hữu ích; nó **không** chứng minh transformer đã instrument đúng lớp hay probe đã tạo được dữ liệu.

Lệnh `jcmd <pid> VM.command_line` có thể giúp xem một phần command-line/VM arguments của một JVM HotSpot đang chạy nếu đủ quyền, nhưng **không luôn chứng minh được nguồn gốc** của mọi option (CLI, env, wrapper). Không cần lấy toàn bộ môi trường có thể chứa secret chỉ để chẩn đoán phạm vi agent.

## 16. Checklist trước khi triển khai

- [ ] Xác định **đúng JVM**: application, server process, worker/test fork hay launcher nhúng JNI?
- [ ] Chọn đúng nơi cấu hình: startup command, JVM arguments của wrapper hoặc `JAVA_TOOL_OPTIONS` của workload.
- [ ] Biết process/JVM con có thể **kế thừa biến** hay không.
- [ ] Có agent JAR đáng tin, đúng phiên bản, đúng `Premain-Class` và đường dẫn tuyệt đối có thể đọc trong runtime.
- [ ] Biết chính xác chuỗi `agentArgs`, không chứa bí mật và được agent validate.
- [ ] Không cấu hình trùng `-javaagent` giữa command, env, wrapper hoặc `JDK_JAVA_OPTIONS` ngoài chủ ý.
- [ ] Lọc class/module/loader ở agent để phạm vi instrumentation đúng mục tiêu.
- [ ] Thử startup thành công và lỗi (thiếu JAR, config sai), kiểm tra stderr và dấu hiệu `premain`.
- [ ] Có đánh giá overhead, class loading, canary, rollback và kế hoạch khởi động lại.
- [ ] Có tài liệu xác định ai sở hữu cấu hình và cách tắt cho những JVM được tạo **sau** khi thay đổi.

## 17. Câu hỏi tự kiểm tra

1. Vì sao `java -jar app.jar -javaagent:agent.jar` không tương đương `java -javaagent:agent.jar -jar app.jar`?
2. Khi export `JAVA_TOOL_OPTIONS` ở shell rồi chạy Maven và ứng dụng Java, JVM nào có thể nhận agent?
3. Vì sao dùng biến môi trường cho một lệnh **vẫn** có thể ảnh hưởng JVM con được tiến trình ấy sinh ra?
4. Điều gì khác giữa `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS` khi launcher native gọi `JNI_CreateJavaVM`?
5. Nếu container có `JAVA_TOOL_OPTIONS=-javaagent:/opt/agent/agent.jar` mà không có file JAR đó, điều gì xảy ra ở startup?
6. Vì sao khai báo `JAVA_TOOL_OPTIONS` trong `containers[].env` cho `api` không tự áp dụng cho sidecar trong cùng Pod?
7. Khi cả env và command cùng chỉ định một agent JAR, bạn kỳ vọng bao nhiêu lần `premain` có thể được gọi?
8. Có thể sửa `JAVA_TOOL_OPTIONS` của shell để làm agent đang chạy trong JVM ngừng hoạt động ngay không? Vì sao?
9. Khác nhau giữa phạm vi **JVM được bật agent** và phạm vi **class được transformer biến đổi** là gì?
10. Khi thấy log `Picked up JAVA_TOOL_OPTIONS`, cần kiểm tra thêm điều gì để kết luận probe thực sự hoạt động?

## 18. Tài liệu chính thức

- [Java SE 21 — `java.lang.instrument`, phần *Starting an Agent from the Command-Line Interface*](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent:<jarpath>[=<options>]`, `premain`, manifest và lỗi khởi động.
- [Java SE 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): vị trí tùy chọn JVM, `-jar`, `-javaagent` và `JDK_JAVA_OPTIONS`.
- [Oracle JDK Troubleshooting Guide — `JAVA_TOOL_OPTIONS` environment variable](https://docs.oracle.com/javase/8/docs/technotes/guides/troubleshoot/envvars002.html): biến được áp dụng khi `JNI_CreateJavaVM` được gọi, ứng dụng nhúng và lưu ý bảo mật.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API agent nhận qua `premain` hoặc `agentmain`, cơ chế instrumentation.
