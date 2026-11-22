# Thứ tự `premain` trước `main` và trường hợp nhiều `-javaagent`

Một **startup Java agent** được nạp bằng tùy chọn JVM `-javaagent`. Điểm vào của nó là phương thức `premain`; JVM gọi `premain` **sau khi JVM khởi tạo nhưng trước khi gọi `main` của ứng dụng**. Khi có nhiều `-javaagent`, các phương thức `premain` được gọi **theo đúng thứ tự agent xuất hiện trên dòng lệnh**, và mỗi `premain` phải trả về để bước khởi động tiếp theo diễn ra.

Bài này tập trung vào trình tự khởi động, cách đóng gói và chạy nhiều startup agent, tác động của thứ tự, cách phân biệt thứ tự gọi `premain` với thứ tự xử lý `ClassFileTransformer`, và các lỗi phổ biến khi phối hợp agent.

## 1. Trình tự bảo đảm bởi `java.lang.instrument`

Lệnh có dạng:

```text
java [các tùy chọn JVM] \
     -javaagent:agent-a.jar[=optionsA] \
     -javaagent:agent-b.jar[=optionsB] \
     -cp <classpath> <fully-qualified-main-class> [application-args]
```

Sơ đồ vòng đời đối với hai agent khởi động thành công:

```text
Người dùng gọi java
    |
    v
JVM được khởi tạo
    |
    v
Nạp Agent A, gọi A.premain(optionsA, instrumentation)
    |
    | A.premain trả về bình thường
    v
Nạp Agent B, gọi B.premain(optionsB, instrumentation)
    |
    | B.premain trả về bình thường
    v
Gọi Application.main(String[] args)
    |
    v
Ứng dụng tiếp tục hoạt động
```

Ba cam kết cần tách bạch:

1. **`premain` chạy trước `main` của ứng dụng**, nhưng không phải trước *mọi hoạt động của JVM*. JVM đã khởi tạo, và một số lớp có thể đã được nạp khi `premain` bắt đầu.
2. **Nhiều `premain` chạy theo thứ tự các `-javaagent` trên dòng lệnh**; nếu A ở trước B, lần gọi `A.premain` phải trở về trước khi JVM gọi `B.premain` trong chuỗi khởi động này. JVM chỉ bắt đầu gọi `main` sau khi các startup agent khởi động thành công.
3. **Thứ tự hoàn tất công việc bất đồng bộ không được bảo đảm bởi quy tắc trên**: `premain` có thể tạo luồng nền, đăng ký callback hoặc đưa việc vào executor rồi trả về. Luồng/callback đó vẫn có thể chạy trong hoặc sau `main`.

Ví dụ, A khởi tạo cấu hình đồng bộ rồi trả về, B đọc cấu hình đó trong `premain` thì B thấy kết quả của A. Nhưng nếu A chỉ tạo thread để cập nhật cấu hình và lập tức trả về, B **không có bảo đảm** thread của A đã cập nhật xong.

> Ghi nhớ: thứ tự được đặc tả là **thứ tự lời gọi `premain` trên startup path**. Không suy diễn rằng toàn bộ tác vụ do agent tạo ra đều tuần tự mãi về sau.

## 2. Điều kiện để JVM nhận diện một startup agent

Mỗi agent phải được đóng gói trong JAR có manifest chứa thuộc tính `Premain-Class` trỏ tới tên đầy đủ của class làm entry point:

```text
Manifest-Version: 1.0
Premain-Class: demo.agents.AgentA

```

Trong class này, JVM ưu tiên chữ ký có hai tham số:

```java
public static void premain(String agentArgs,
                           java.lang.instrument.Instrumentation inst)
```

Nếu chữ ký trên không tồn tại, JVM thử chữ ký một tham số:

```java
public static void premain(String agentArgs)
```

Cả hai phải là `public static void`. Khi dùng dạng hai tham số, `Instrumentation` cung cấp API để đăng ký `ClassFileTransformer`, truy vấn các lớp đã nạp, retransform/redefine nếu khả năng được hỗ trợ, v.v. Tham số `agentArgs` là **một chuỗi tùy chọn của chính agent** sau dấu `=`, không phải mảng `String[] args` của ứng dụng.

Sự khác nhau giữa các entry point:

| Cơ chế khởi động | Manifest liên quan | Entry point |
| --- | --- | --- |
| `java -javaagent:agent.jar` lúc khởi động JVM | `Premain-Class` | `premain(...)` |
| Attach agent vào JVM đang chạy (khi JVM hỗ trợ) | `Agent-Class` | `agentmain(...)` |
| Agent đóng gói trong executable application JAR theo cơ chế launcher | `Launcher-Agent-Class` | `agentmain(...)` theo đặc tả cơ chế đó |
| Ứng dụng bình thường | `Main-Class` (nếu chạy bằng `-jar`) hoặc main class trên command line | `main(String[] args)` |

**`Premain-Class` khác `Main-Class`**. Đưa class có `main` vào JAR agent mà thiếu `Premain-Class` không khiến nó tự trở thành agent. Với `-javaagent`, JVM không gọi `agentmain` ngay cả khi JAR có khai báo cả `Premain-Class` và `Agent-Class`.

## 3. Thực hành: hai agent xác nhận thứ tự bằng trạng thái chung

Ví dụ chạy được với **JDK 17+**. Ta dùng ba class Java và hai manifest. Các agent chỉ ghi một dòng và cập nhật system property để minh họa thời điểm gọi; không sửa bytecode nên kết quả dễ kiểm chứng.

Cấu trúc thư mục:

```text
example/
├── src/
│   └── demo/
│       └── agents/
│           ├── AgentA.java
│           ├── AgentB.java
│           └── MainApp.java
├── agent-a.mf
└── agent-b.mf
```

### 3.1. `src/demo/agents/AgentA.java`

```java
package demo.agents;

import java.lang.instrument.Instrumentation;

public final class AgentA {
    private static final String KEY = "demo.agent.order";

    private AgentA() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        String previous = System.getProperty(KEY, "");
        System.out.println("[AgentA] premain args=" + agentArgs
                + ", before=" + (previous.isEmpty() ? "<empty>" : previous));

        String next = previous.isEmpty() ? "A" : previous + " -> A";
        System.setProperty(KEY, next);
    }
}
```

Đây là một startup agent hợp lệ vì class có phương thức `public static void premain(String, Instrumentation)`. Tham số `inst` chưa được sử dụng vì bài đang kiểm tra **thời điểm và thứ tự**, không triển khai transformer. System property chỉ là cách quan sát đơn giản vì các agent và ứng dụng cùng nằm trong **một tiến trình JVM**.

### 3.2. `src/demo/agents/AgentB.java`

```java
package demo.agents;

import java.lang.instrument.Instrumentation;

public final class AgentB {
    private static final String KEY = "demo.agent.order";

    private AgentB() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        String previous = System.getProperty(KEY, "");
        System.out.println("[AgentB] premain args=" + agentArgs
                + ", before=" + (previous.isEmpty() ? "<empty>" : previous));

        String next = previous.isEmpty() ? "B" : previous + " -> B";
        System.setProperty(KEY, next);
    }
}
```

Agent B đọc giá trị đã tồn tại trước khi cập nhật. Do đó thứ tự A rồi B tạo chuỗi `A -> B`; nếu đổi thứ tự, ta sẽ thấy `B -> A`.

### 3.3. `src/demo/agents/MainApp.java`

```java
package demo.agents;

public final class MainApp {
    private MainApp() {
    }

    public static void main(String[] args) {
        String order = System.getProperty("demo.agent.order", "<empty>");
        System.out.println("[MainApp] main sees=" + order);
    }
}
```

Ứng dụng không import `AgentA` hay `AgentB`. Vì vậy các phương thức `premain` không phải do `main` tự gọi. JVM chọn và gọi agent từ các tùy chọn `-javaagent`.

### 3.4. Hai manifest riêng, đúng `Premain-Class`

Nội dung `agent-a.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agents.AgentA

```

Nội dung `agent-b.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agents.AgentB

```

Giữ **dòng mới ở cuối mỗi manifest**; để một dòng trống sau `Premain-Class` như trên là cách dễ kiểm tra. Không dùng giá trị `demo/agents/AgentA` vì manifest yêu cầu tên class nhị phân với dấu chấm.

### 3.5. Biên dịch và đóng gói bằng công cụ JDK

Mở terminal tại thư mục `example/`. Tạo thư mục `out` một lần (ví dụ `mkdir out`), rồi chạy:

```bash
javac --release 17 -d out src/demo/agents/AgentA.java src/demo/agents/AgentB.java src/demo/agents/MainApp.java

jar --create --file agent-a.jar --manifest agent-a.mf -C out demo/agents/AgentA.class
jar --create --file agent-b.jar --manifest agent-b.mf -C out demo/agents/AgentB.class
```

Dấu `-d out` đặt class đã biên dịch vào đường dẫn package, thí dụ `out/demo/agents/AgentA.class`. Mỗi agent JAR chứa class được chỉ ra trong manifest của nó; ứng dụng chạy bằng `-cp out`. Các lệnh trên chạy được với JDK 17+ trên shell có `javac` và `jar` trong `PATH`. Trên PowerShell cũng có thể dùng `New-Item -ItemType Directory -Force out` để tạo `out`.

Kiểm tra danh sách tệp trong JAR:

```bash
jar --list --file agent-a.jar
jar --list --file agent-b.jar
```

Để kiểm tra manifest, mở mục `META-INF/MANIFEST.MF` bằng công cụ đọc ZIP/JAR và xác nhận `Premain-Class` trỏ đúng class. Không đủ nếu chỉ thấy JAR có tên “agent”.

## 4. Chạy A trước B: output chính xác

```bash
java -javaagent:agent-a.jar=left -javaagent:agent-b.jar=right -cp out demo.agents.MainApp
```

Với môi trường thử nghiệm không đặt sẵn system property `demo.agent.order`, stdout là:

```text
[AgentA] premain args=left, before=<empty>
[AgentB] premain args=right, before=A
[MainApp] main sees=A -> B
```

Phân tích theo đúng thứ tự:

1. JVM đọc agent JAR đầu tiên, nạp `demo.agents.AgentA` và gọi `AgentA.premain("left", inst)`.
2. A thấy property chưa có, in `<empty>`, đặt property thành `A` rồi **trả về**.
3. JVM gọi `AgentB.premain("right", inst)`. B nhìn thấy `A`, đặt lại thành `A -> B` rồi trả về.
4. JVM gọi `MainApp.main(...)`. Ứng dụng đọc được `A -> B` nên in dòng cuối.

Mỗi lần chạy lệnh `java` là một tiến trình JVM mới. System property do agent cập nhật ở lần chạy trước không tự tồn tại ở tiến trình Java sau.

## 5. Đảo vị trí trên command line: B trước A

Chỉ đổi thứ tự hai tham số JVM `-javaagent`:

```bash
java -javaagent:agent-b.jar=right -javaagent:agent-a.jar=left -cp out demo.agents.MainApp
```

Stdout:

```text
[AgentB] premain args=right, before=<empty>
[AgentA] premain args=left, before=B
[MainApp] main sees=B -> A
```

Không có cơ chế tự động sắp xếp agent theo **tên class, tên JAR, thứ tự tạo JAR hoặc classpath**. Thứ tự `premain` được xác định bởi thứ tự tùy chọn `-javaagent` trên dòng lệnh. Nếu một hệ thống khởi động Java gián tiếp bằng script, Gradle task, container entrypoint hoặc cấu hình IDE, cần kiểm tra **dòng lệnh JVM cuối cùng** mà hệ thống thực sự dùng.

### 5.1. Nạp cùng JAR hai lần

Đặc tả cho phép xuất hiện nhiều `-javaagent` với **cùng đường dẫn JAR**. Thử:

```bash
java -javaagent:agent-a.jar=once -javaagent:agent-a.jar=twice -cp out demo.agents.MainApp
```

Stdout:

```text
[AgentA] premain args=once, before=<empty>
[AgentA] premain args=twice, before=A
[MainApp] main sees=A -> A
```

Nghĩa là **không được mặc định mỗi agent JAR chỉ nhận một lần gọi `premain` trên một câu lệnh khởi động**. Với agent thật, gọi lặp có thể đăng ký transformer/callback nhiều lần và làm lặp tác dụng phụ; ứng dụng cần quy định rõ cách xử lý, chẳng hạn từ chối cấu hình lặp hoặc thiết kế khởi tạo idempotent.

### 5.2. Không có agent

```bash
java -cp out demo.agents.MainApp
```

Stdout:

```text
[MainApp] main sees=<empty>
```

Dòng này xác nhận class ứng dụng chạy độc lập; các dòng `[AgentA]`/`[AgentB]` chỉ xuất hiện khi JVM được truyền startup agent tương ứng.

## 6. Vai trò của `agentArgs`, các JVM option và tham số `main`

So sánh:

```bash
java -javaagent:agent-a.jar=mode=debug -cp out demo.agents.MainApp hello
```

- Chuỗi `"mode=debug"` là toàn bộ `agentArgs` nhận bởi `AgentA.premain`.
- Từ `"hello"` là phần tử `args[0]` của `MainApp.main` (ứng dụng ví dụ không in nó).
- Chính agent có trách nhiệm phân tích cú pháp chuỗi `agentArgs` nếu dùng nhiều cặp key/value; Java không tự chuyển `mode=debug` thành `Map`.
- Một `-javaagent:...` khác có chuỗi options của riêng nó. Options của A không mặc nhiên được gửi cho B.
- Các cờ JVM như `-javaagent` cần được đặt **trước tên main class** hoặc trước `-jar app.jar`. Đặt `-javaagent:agent.jar` phía sau tên main class chỉ khiến nó thành một argument của ứng dụng thay vì kích hoạt agent.

Nếu chạy ứng dụng dưới dạng executable JAR:

```bash
java -javaagent:agent-a.jar=left -javaagent:agent-b.jar=right -jar application.jar
```

`application.jar` cần có `Main-Class` riêng; `agent-a.jar` và `agent-b.jar` cần `Premain-Class`. Việc sử dụng `-jar` không đảo thứ tự startup agents.

## 7. Khi nhiều agent thật đăng ký `ClassFileTransformer`

Ví dụ trên mới chứng minh thời điểm `premain`. Một agent giám sát hoặc đo coverage thường dùng `Instrumentation.addTransformer(...)` trong `premain` để đăng ký bộ biến đổi bytecode. Cần phân biệt **thứ tự đăng ký transformer** với **thứ tự gọi `premain`**.

Giả sử A và B cùng đăng ký transformer bình thường ngay trong `premain`:

```java
// Đoạn mã minh họa bên trong premain, không phải class độc lập.
inst.addTransformer(transformerA);  // A đăng ký trong A.premain
inst.addTransformer(transformerB);  // B đăng ký trong B.premain
```

Trên thực tế hai dòng này nằm **trong hai agent khác nhau**, không phải một nơi duy nhất như cách viết rút gọn trên. Khi cả hai transformer đã được đăng ký và một lớp mới chuẩn bị được định nghĩa, JVM có thể lần lượt chuyển bytes qua các transformer. Trong cùng **nhóm khả năng retransformation**, transformer được gọi theo **thứ tự đăng ký**; bytes của bước trước là đầu vào của bước sau nếu bước trước trả về mảng bytes mới.

Tuy nhiên, Java định nghĩa **các nhóm thứ tự** khi áp dụng transformers:

1. Java transformers **không hỗ trợ retransformation**;
2. Native transformers không hỗ trợ retransformation;
3. Java transformers **hỗ trợ retransformation**;
4. Native transformers hỗ trợ retransformation.

Trong mỗi nhóm, thứ tự đăng ký được giữ. Vì vậy, **không được khẳng định tuyệt đối “Agent A nằm trước Agent B thì mọi transform của A luôn chạy trước mọi transform của B”**. Nếu A đăng ký transformer có thể retransform còn B đăng ký transformer không thể retransform, thứ tự nhóm khác thứ tự hai lệnh `premain`.

Ví dụ sau chỉ để mô tả logic, **không phải output thực của trình biên dịch hay mã transformer độc lập**:

```text
premain A: đăng ký transformer A (retransform-capable)
premain B: đăng ký transformer B (retransform-incapable)

Một lớp mới được nạp sau đó:
    B.transform(bytesGoc) -> bytesB
    A.transform(bytesB)   -> bytesA
```

Khi gọi `retransformClasses(...)` trên lớp đã nạp, các transformer không hỗ trợ retransformation không được gọi lại; JVM tái sử dụng tác động trước đó theo quy tắc API, còn những transformer có hỗ trợ sẽ được gọi lại. Khả năng retransformation phải được JVM hỗ trợ và agent có thể cần manifest `Can-Retransform-Classes: true`. **Thứ tự `premain` vẫn như command line** trong mọi trường hợp này.

### 7.1. Thứ tự khởi động không bảo đảm can thiệp được mọi lớp

Nếu Agent A chủ động load lớp `com.example.Service` bên trong `A.premain`, rồi Agent B mới đăng ký transformer cho `com.example.Service` ở `B.premain`, transformer của B không tự quay ngược thời gian để thấy lần định nghĩa ban đầu của lớp đó. Việc xử lý lớp đã tải đòi hỏi khả năng và lời gọi thích hợp (chẳng hạn retransformation nếu được hỗ trợ, lớp có thể sửa đổi và thay đổi hợp lệ).

Kể cả agent đầu tiên cũng có thể chạy sau khi một số lớp JDK hoặc lớp hỗ trợ quá trình khởi động đã được tải. Vì vậy “`premain` trước `main`” **không tương đương** với “transformer thấy 100% các class từng được load trong JVM”.

### 7.2. Hai agent biến đổi cùng một class

Hai công cụ tracing, coverage, profiling hoặc APM có thể cùng instrument một method. Kết quả phụ thuộc vào phép biến đổi, thứ tự trong nhóm và khả năng tương thích bytecode. Các vấn đề hay gặp:

- Transformer thứ hai không hiểu bytecode đã được transformer thứ nhất thay đổi.
- Hai agent cùng tạo field/method phụ trợ với tên trùng nhau.
- Agent khởi tạo quá sớm/đăng ký quá muộn so với lớp cần theo dõi.
- Transformer không idempotent, tạo mã lồng thêm khi chạy lại.
- Agent khác tự nạp nhiều class hoặc tạo thread trong `premain`, làm phát sinh sự kiện class loading xen giữa các lần đăng ký.
- Thay đổi thứ tự agent làm thay đổi hành vi, dù cả hai vẫn có `premain` hợp lệ.

Khi đánh giá hai agent cần kiểm tra **từng agent một, rồi chạy chung cả hai thứ tự**, trên cùng phiên bản JDK và phiên bản agent. Không có bảo đảm mọi cặp agent bất kỳ đều tương thích.

## 8. Nếu một `premain` thất bại thì sao?

Startup agent khác với code ứng dụng có thể tự bắt lỗi và tiếp tục. Theo đặc tả Java 17, nếu không thể khởi động agent (JAR sai, `Premain-Class` không hợp lệ, class không tải được, thiếu `premain` thích hợp) hoặc `premain` ném **exception không được bắt**, JVM **hủy khởi động**. Application `main` không được gọi.

Ví dụ có ba agent A, B, C:

```text
java -javaagent:a.jar -javaagent:b.jar -javaagent:c.jar -cp out demo.Main

A.premain --> trả về
B.premain --> ném exception không được bắt
JVM abort
C.premain --> không được gọi tiếp
Application.main --> không được gọi
```

Sơ đồ này minh họa kết quả của lỗi trong B theo quy tắc startup, không phải log cụ thể của JVM. Thông điệp lỗi và stack trace phụ thuộc runtime.

Một số vấn đề khác không làm thay đổi quy tắc thứ tự nhưng cần phân biệt:

| Vấn đề | Kết quả hoặc hướng chẩn đoán |
| --- | --- |
| Agent có `main` nhưng thiếu `Premain-Class` | JVM không nhận ra startup agent hợp lệ. |
| Manifest trỏ tên class không tồn tại trong JAR/không tải được | Agent không khởi động; JVM dừng trước ứng dụng. |
| Class agent có `premain` không `public` hoặc sai chữ ký | Không tìm được entry point phù hợp cho startup agent. |
| `premain` ném lỗi không bắt | JVM abort trước `main`. |
| `premain` không bao giờ trả về | Chuỗi startup bị giữ tại agent; `main` không được gọi tới khi agent trả về. |
| Agent tạo thread bất đồng bộ và trả về | Thread có thể chạy song song với các agent sau hoặc với `main`. |
| Agent đăng ký transformer sau khi lớp mục tiêu được nạp | Không bắt được lần tải trước đó chỉ nhờ đăng ký; cần khả năng xử lý lại phù hợp. |
| Agent yêu cầu retransform nhưng JVM/cấu hình không hỗ trợ | `addTransformer(..., true)` có thể báo `UnsupportedOperationException`; kiểm tra `isRetransformClassesSupported()` và manifest. |
| Hai agent cùng thay đổi kết quả/class metadata | Kiểm tra thứ tự transformer và tương thích bytecode; không suy luận trực tiếp từ thứ tự in log của `premain`. |

Có thể **bắt và xử lý lỗi dự kiến trong `premain`**, nhưng agent phải tự quyết định liệu tiếp tục ứng dụng mà thiếu instrumentation có hợp lệ hay không. Không nên chỉ “nuốt” mọi exception rồi thông báo agent hoạt động bình thường.

## 9. Quy trình kiểm tra một ứng dụng có nhiều agent

Một quy trình gọn để điều tra lỗi thứ tự:

1. **Ghi đúng câu lệnh JVM thực tế** gồm mọi `-javaagent`, JAR path, chuỗi options và main class/`-jar`. Nếu launcher/script/IDE/container tự thêm tham số, xác minh cấu hình cuối cùng.
2. **Kiểm tra manifest của từng JAR** và class theo `Premain-Class`. Xác nhận method `public static premain` có chữ ký hợp lệ.
3. **Log tối thiểu ngay đầu và cuối `premain`** (tên agent, tham số đã lọc bí mật, thứ tự, thread nếu hữu ích). Thông điệp ở đầu mà không thấy thông điệp cuối gợi ý agent treo/lỗi trước khi trở về.
4. **Chạy từng agent đơn lẻ**, sau đó chạy cả hai và đổi thứ tự. Với lỗi liên quan bytecode, kiểm tra class cần biến đổi đã được load trước lúc đăng ký chưa.
5. **Tách lỗi startup khỏi lỗi transform/runtime**. JVM dừng trước `main` có thể là lỗi khởi động agent; exception khi class lần đầu nạp sau `main` thường cần kiểm tra transformer và class loading.
6. **Kiểm tra các khả năng optional** bằng `Instrumentation.isRetransformClassesSupported()`, `isRedefineClassesSupported()` nếu agent dựa vào chúng; chỉ yêu cầu khả năng manifest khi cần.
7. **Xác nhận đường về bình thường**: với agent đồng bộ, mỗi `premain` cần hoàn tất phần khởi tạo quan trọng trước khi trả về; với tác vụ nền, cung cấp cơ chế phối hợp rõ ràng nếu agent sau hoặc ứng dụng cần kết quả của nó.

Đối với cấu hình production, nên có cách quan sát agent nào đã khởi tạo thành công, phiên bản của từng agent và các tùy chọn thực tế, nhưng không in token hay secret từ `agentArgs` vào log.

## 10. Các ngộ nhận cần tránh

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “`premain` chạy trước cả JVM.” | JVM khởi tạo trước, rồi gọi `premain` trước application `main`. |
| “Agent chỉ chạy khi `main` gọi vào class agent.” | `-javaagent` và `Premain-Class` làm JVM chủ động gọi `premain`. |
| “Agent B có tên đứng trước theo alphabet sẽ chạy trước A.” | Chỉ thứ tự các option `-javaagent` quyết định thứ tự `premain`. |
| “Chỉ cho phép một `-javaagent`.” | Có thể truyền nhiều, kể cả cùng một JAR nhiều lần. |
| “Hai agent cùng dòng lệnh chạy `premain` song song.” | Các lời gọi `premain` thuộc chuỗi startup theo thứ tự; tác vụ do agent tự tạo có thể chạy song song. |
| “Mọi transformer của A phải chạy trước B vì A `premain` trước.” | Transformer có nhóm retransformation/nativity và quy tắc đăng ký riêng. |
| “`premain` đứng trước `main` nên chắc chắn thấy mọi class.” | Một số class đã được load trước hoặc trong lúc khởi động agent. |
| “Thiếu `premain` thì JVM bỏ qua agent để chạy app.” | Startup agent thất bại có thể làm JVM abort. |
| “`agentArgs` bằng `main(String[] args)`.” | Một bên là chuỗi options riêng cho agent; bên kia là mảng tham số của ứng dụng. |
| “`agentmain` và `premain` chỉ khác tên.” | Hai entry point phục vụ các cơ chế khởi động khác nhau, với xử lý lỗi khác nhau. |

## 11. Tự kiểm tra

**Câu 1.** Với lệnh `java -javaagent:b.jar -javaagent:a.jar -cp out demo.Main`, phương thức nào chạy trước?

**Đáp án:** `B.premain`, sau đó `A.premain`, rồi mới tới `Main.main`, nếu cả hai startup agent khởi động thành công và trả về.

**Câu 2.** Agent A tạo thread rồi trả về. Agent B cần dữ liệu do thread đó sinh ra. Chỉ dựa vào thứ tự `-javaagent:a.jar -javaagent:b.jar` có đủ không?

**Đáp án:** Không. Thứ tự gọi `premain` không đợi thread nền của A hoàn tất. Phải thêm phối hợp đồng bộ phù hợp hoặc thực hiện phần khởi tạo bắt buộc ngay trong `premain` của A.

**Câu 3.** A đăng ký Java transformer retransform-capable, B đăng ký Java transformer retransform-incapable. A có `premain` trước. Khi tải một lớp mới, transformer nào thuộc nhóm được gọi trước?

**Đáp án:** Nhóm retransform-incapable (transformer B) được ưu tiên trước nhóm retransform-capable (transformer A). Đây là quy tắc `ClassFileTransformer`, khác thứ tự gọi `premain`.

**Câu 4.** Nếu cả A và B có `premain` chạy thành công, nhưng `MainApp.main` không xuất hiện trong log, có thể kết luận JVM đã bỏ qua `main` vì có nhiều `-javaagent` không?

**Đáp án:** Không. Nhiều agent là hợp lệ. Cần kiểm tra agent sau có đang treo hoặc abort, cách launcher khởi chạy, exception trong quá trình tải main class, stdout/stderr và việc chương trình tự thoát.

**Câu 5.** Lệnh `java -cp out demo.agents.MainApp -javaagent:agent-a.jar` có gọi `AgentA.premain` không?

**Đáp án:** Không. `-javaagent:agent-a.jar` đứng **sau** tên main class nên được truyền như argument ứng dụng. Đưa option này về trước tên main class.

## 12. Tóm tắt và tài liệu chuẩn

- Startup agent được nhận diện bằng `-javaagent:jar[=options]` và manifest `Premain-Class`.
- JVM gọi `premain` **sau khi khởi tạo JVM, trước `main`**; nhiều `premain` được gọi theo **thứ tự `-javaagent`**.
- Mỗi `premain` phải trả về bình thường để chuỗi startup tiếp tục; lỗi khởi động hoặc exception không được bắt làm JVM abort.
- Thứ tự gọi `premain` không bảo đảm thứ tự kết thúc thread bất đồng bộ, cũng không tự động xác định toàn bộ thứ tự `ClassFileTransformer`.
- Với nhiều agent, cần xem **cả cấu hình launcher, thời điểm load class, thứ tự/khả năng transformer và tương tác giữa các biến đổi bytecode**.

Nguồn chuẩn để đối chiếu:

1. **Java SE 17 API — `java.lang.instrument` package specification**: cú pháp `-javaagent`, `Premain-Class`, thứ tự nhiều `premain`, chữ ký và lỗi startup: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
2. **Java SE 17 API — `Instrumentation`**: `addTransformer`, `retransformClasses`, kiểm tra khả năng: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
3. **Java SE 17 API — `ClassFileTransformer`**: nhóm/thứ tự gọi transformer: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. **JDK 17 — lệnh `java`**: vị trí các JVM options, `-javaagent`, `-cp` và `-jar`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html