# `Premain-Class` và hai chữ ký hợp lệ của `premain`

Khi khởi động một ứng dụng Java với tùy chọn `-javaagent`, JVM cần biết **lớp nào là điểm vào của agent** và **phương thức nào trong lớp đó phải được gọi trước `main` của ứng dụng**. Hai việc này có hợp đồng rõ ràng:

- Thuộc tính `Premain-Class` trong **main section của manifest** thuộc JAR agent chỉ ra *tên nhị phân* của lớp agent.
- Lớp agent cung cấp một trong **hai chữ ký `public static void premain` hợp lệ**. JVM ưu tiên chữ ký nhận `Instrumentation`; chỉ khi không có chữ ký này, JVM mới thử chữ ký nhận `String`.

Đây là cơ chế khởi động agent (*startup agent*) trong Java instrumentation. `Premain-Class` không chứa đường dẫn đến `.java`, cũng không biến `main` thông thường thành `premain`.

## 1. Bức tranh khi JVM khởi động với `-javaagent`

Cú pháp:

```bash
java -javaagent:<duong-dan-agent.jar>[=<agent-options>] -cp <classpath> <TenLopMain>
```

Các dấu `<...>` ở trên là ký hiệu cần thay bằng giá trị thực, không phải lệnh để chạy nguyên văn. Ví dụ chạy được ở các phần sau dùng tên JAR và tên lớp cụ thể.

Luồng chính:

```text
java -javaagent:agent-two.jar=mode=demo -cp out demo.App
             |
             v
JVM mở agent-two.jar
             |
             v
Đọc META-INF/MANIFEST.MF
             |
             v
Tìm Premain-Class: demo.AgentTwo
             |
             v
Nạp demo.AgentTwo, tìm premain theo thứ tự ưu tiên
             |
             +-- premain(String, Instrumentation) có? --> gọi chữ ký này
             |
             +-- không có? --> tìm premain(String) --> gọi nếu hợp lệ
             |
             v
premain thực hiện khởi tạo và trả về
             |
             v
Ứng dụng chạy demo.App.main(String[])
```

JVM đã trải qua giai đoạn khởi tạo cần thiết trước khi gọi `premain`, vì vậy không nên hiểu rằng *chưa hề có lớp Java nào được nạp* tại thời điểm agent bắt đầu. Bảo đảm quan trọng là `premain` của startup agent chạy **trước `main` của ứng dụng**; nếu cần theo dõi lớp, agent thường đăng ký transformer ngay trong `premain`.

> **Quy tắc phân vai:** manifest chọn **lớp agent**; chữ ký `premain` chọn **cách JVM gọi điểm vào**; `Instrumentation` cung cấp **API để agent đăng ký và quản lý instrumentation**. Việc sửa bytecode cụ thể, nếu có, thuộc về transformer và logic của agent.

## 2. `Premain-Class` là gì?

Trong một JAR chuẩn, manifest nằm ở:

```text
META-INF/MANIFEST.MF
```

Một manifest tối thiểu cho agent tên `demo.AgentTwo`:

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentTwo

```

Các chi tiết cần hiểu chính xác:

1. Tên thuộc tính là **`Premain-Class`**; giá trị `demo.AgentTwo` là *binary name* của lớp, bao gồm package, dùng dấu chấm (`.`).
2. Không viết `demo/AgentTwo.class`, `src/demo/AgentTwo.java`, `AgentTwo.java` hay `demo.AgentTwo.class` vào giá trị này.
3. Thuộc tính phải nằm trong **main section** ở đầu manifest. Một header đặt sau mục `Name: ...` của một entry riêng không có tác dụng xác định startup agent.
4. File manifest dùng cú pháp `Name: value`, có ký tự xuống dòng; để tránh lỗi khi tự viết file, kết thúc phần main bằng một dòng trống như ví dụ.
5. Class tương ứng phải thực sự có trong JAR agent hoặc có thể được nạp thông qua cơ chế class loading phù hợp. Trong ví dụ học tập, ta đóng `demo/AgentTwo.class` ngay vào JAR.
6. Chỉ đưa JAR vào `-cp` **không** làm JVM tự gọi `premain`; tùy chọn `-javaagent` mới kích hoạt cơ chế startup-agent tương ứng.

Manifest của JAR ứng dụng có thể dùng `Main-Class`, nhưng nó trả lời câu hỏi *chạy ứng dụng nào*. `Premain-Class` trả lời câu hỏi *khởi động agent nào*. Hai thuộc tính phục vụ hai điểm vào khác nhau.

## 3. Hai chữ ký `premain` được đặc tả hỗ trợ

### 3.1. Chữ ký hai tham số: lựa chọn ưu tiên

```java
public static void premain(String agentArgs, Instrumentation inst)
```

Để dùng chữ ký trên trong lớp Java, import:

```java
import java.lang.instrument.Instrumentation;
```

- `public`: JVM có thể gọi phương thức như điểm vào theo hợp đồng.
- `static`: JVM không cần tạo một instance agent để gọi.
- `void`: phương thức không trả giá trị.
- `premain`: **đúng tên, đúng chữ hoa/chữ thường**.
- `String agentArgs`: chuỗi tùy chọn được truyền qua phần sau dấu `=` của `-javaagent`.
- `Instrumentation inst`: đối tượng do JVM đưa cho agent để thao tác với API instrumentation.

Ví dụ về việc dùng `Instrumentation`:

```java
public static void premain(String agentArgs, Instrumentation inst) {
    System.out.println("Agent started: " + agentArgs);
    System.out.println("Can retransform: "
            + inst.isRetransformClassesSupported());
}
```

Đây là **đoạn method minh họa**, chưa phải file class độc lập. Giá trị `isRetransformClassesSupported()` tùy khả năng JVM và cấu hình agent; không được tự giả định luôn `true`. Khi muốn gọi `inst.addTransformer(...)` hay các API khác, dạng hai tham số là lựa chọn trực tiếp và rõ ràng nhất.

### 3.2. Chữ ký một tham số: phương án fallback hợp lệ

```java
public static void premain(String agentArgs)
```

Dạng này vẫn được JVM hỗ trợ chính thức. Nó có thể làm việc khởi tạo như đọc cấu hình, chuẩn bị logging hoặc kết nối dịch vụ phụ trợ; tuy nhiên nó **không nhận đối tượng `Instrumentation` trực tiếp qua tham số**.

Ví dụ method minh họa:

```java
public static void premain(String agentArgs) {
    System.out.println("Starting agent with: " + agentArgs);
}
```

Việc không nhận `Instrumentation` trong chữ ký một tham số **không** có nghĩa JVM không hỗ trợ instrumentation. Nó chỉ có nghĩa method đó không được truyền reference `Instrumentation` qua điểm vào này.

### 3.3. Nếu agent khai báo cả hai thì sao?

Quy tắc tìm phương thức theo thứ tự:

1. JVM thử `public static void premain(String, Instrumentation)` trước.
2. **Chỉ khi không có phương thức phù hợp ở bước 1**, JVM mới thử `public static void premain(String)`.
3. Không có chữ ký hợp lệ: agent không khởi động thành công; với startup agent, JVM hủy khởi động ứng dụng.
4. Có cả hai chữ ký: **chỉ chữ ký hai tham số được gọi** cho lần khởi động đó; JVM không gọi nối tiếp cả hai.

Đây là quy tắc chọn overload của cơ chế agent, không phải hành vi “Java tự gọi mọi overload cùng tên”. Danh sách chữ ký không cho phép tráo thứ tự tham số hoặc thay kiểu tham số bằng kiểu gần giống.

| Khai báo trong lớp agent | Hợp lệ với `-javaagent`? | Kết quả |
|---|---|---|
| `public static void premain(String, Instrumentation)` | Có | Được ưu tiên gọi |
| `public static void premain(String)` | Có | Được gọi nếu không có dạng hai tham số |
| Cả hai dạng trên | Có | Chỉ gọi dạng hai tham số |
| `public void premain(String, Instrumentation)` | Không | Thiếu `static` |
| `private static void premain(String, Instrumentation)` | Không | Thiếu `public` |
| `public static int premain(String, Instrumentation)` | Không | Kiểu trả về sai |
| `public static void premain(Instrumentation, String)` | Không | Sai thứ tự tham số |
| `public static void premain(String[] args)` | Không | `String[]` khác `String` |
| `public static void preMain(String, Instrumentation)` | Không | Sai tên phương thức |

Bảng này xét **từng chữ ký riêng lẻ**; nếu một lớp có cả method sai lẫn một method đúng, JVM vẫn có thể chọn method đúng.

## 4. Ví dụ hoàn chỉnh Java 17+: chạy cả hai chữ ký và chứng minh thứ tự ưu tiên

Ta tạo một ứng dụng `demo.App` và ba lớp agent:

- `demo.AgentTwo`: chỉ có chữ ký hai tham số.
- `demo.AgentOne`: chỉ có chữ ký một tham số.
- `demo.AgentBoth`: có cả hai, in ra chữ ký thực sự được chọn.

Ví dụ chỉ dùng JDK, **không cần Maven, Gradle hay thư viện ngoài**. Mỗi JAR agent dùng manifest riêng, giúp nhìn thấy rõ `Premain-Class` trỏ tới lớp nào.

Cấu trúc thư mục cần tạo:

```text
premain-example/
├── src/
│   └── demo/
│       ├── App.java
│       ├── AgentTwo.java
│       ├── AgentOne.java
│       └── AgentBoth.java
└── manifests/
    ├── two.mf
    ├── one.mf
    └── both.mf
```

### 4.1. Ứng dụng chính: `src/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("[app] main started");
    }
}
```

Ứng dụng này không tham chiếu đến agent. Ta sẽ kích hoạt agent bằng JVM option khi chạy, nên cơ chế startup agent độc lập với nội dung `App.main`.

### 4.2. Agent hai tham số: `src/demo/AgentTwo.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentTwo {
    private AgentTwo() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[two] args=" + agentArgs);
        System.out.println("[two] instrumentation=" + (inst != null));
    }
}
```

Method hai tham số cho thấy JVM truyền cả chuỗi options và đối tượng `Instrumentation`. In `inst != null` tránh phụ thuộc vào những khả năng tùy JVM; đây là kiểm tra điểm vào chứ chưa thực hiện bytecode transformation.

### 4.3. Agent một tham số: `src/demo/AgentOne.java`

```java
package demo;

public final class AgentOne {
    private AgentOne() {
    }

    public static void premain(String agentArgs) {
        System.out.println("[one] args=" + agentArgs);
    }
}
```

Khi manifest trỏ tới `demo.AgentOne`, JVM không tìm được chữ ký hai tham số và dùng dạng một tham số. Đây là fallback **hợp lệ**, không phải lỗi.

### 4.4. Agent khai báo cả hai: `src/demo/AgentBoth.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentBoth {
    private AgentBoth() {
    }

    public static void premain(String agentArgs) {
        System.out.println("[both] selected one-argument premain");
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[both] selected two-argument premain");
    }
}
```

Cố ý đặt method một tham số **ở trên** trong source để kiểm tra: thứ tự khai báo trong file `.java` không quyết định cách JVM chọn chữ ký. JVM vẫn ưu tiên method hai tham số.

### 4.5. Tạo ba file manifest

**`manifests/two.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentTwo

```

**`manifests/one.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentOne

```

**`manifests/both.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentBoth

```

Lưu các file dưới dạng văn bản thuần, giữ ký tự xuống dòng cuối file. Dòng trống sau `Premain-Class` trong từng ví dụ dùng để kết thúc main section. `jar --manifest` đưa nội dung này vào `META-INF/MANIFEST.MF` của JAR tương ứng.

### 4.6. Biên dịch và đóng ba JAR

Mở terminal trong thư mục `premain-example`, dùng JDK 17+ (có `javac`, `jar`, `java`).

Các lệnh dưới đây không dùng wildcard, nên có thể nhập lần lượt trong Bash, PowerShell hoặc cmd:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/demo/App.java src/demo/AgentTwo.java src/demo/AgentOne.java src/demo/AgentBoth.java

jar --create --file agent-two.jar --manifest manifests/two.mf -C out demo/AgentTwo.class
jar --create --file agent-one.jar --manifest manifests/one.mf -C out demo/AgentOne.class
jar --create --file agent-both.jar --manifest manifests/both.mf -C out demo/AgentBoth.class
```

- `javac --release 17` tạo class files tương thích mức Java 17.
- `-d out` đặt class file theo package, ví dụ `out/demo/AgentTwo.class`.
- `jar --create` đóng agent vào JAR; `--manifest` nhập đúng header `Premain-Class`.
- `-C out demo/AgentTwo.class` lưu entry `demo/AgentTwo.class` **tại gốc archive**, không lưu tiền tố thư mục `out/`.
- `out` là thư mục output mới của ví dụ; không cần sửa classpath hệ thống.

Để xem các entry của agent JAR:

```bash
jar --list --file agent-two.jar
```

Trong danh sách phải có `META-INF/MANIFEST.MF` và `demo/AgentTwo.class`. Có thể đọc manifest bằng công cụ giải nén hoặc Java API để chắc chắn tên `Premain-Class` chính xác; chỉ nhìn thấy `.class` trong JAR chưa đủ chứng minh có header đúng.

### 4.7. Chạy và so sánh stdout

**Trường hợp A: không có agent**

```bash
java -cp out demo.App
```

Stdout:

```text
[app] main started
```

**Trường hợp B: agent có hai tham số**

```bash
java -javaagent:agent-two.jar=mode=demo -cp out demo.App
```

Stdout:

```text
[two] args=mode=demo
[two] instrumentation=true
[app] main started
```

Chú ý `mode=demo` được giữ nguyên thành **một `String`**; JVM không tự chuyển nó thành một `Map` cấu hình.

**Trường hợp C: agent chỉ có một tham số**

```bash
java -javaagent:agent-one.jar=hello -cp out demo.App
```

Stdout:

```text
[one] args=hello
[app] main started
```

**Trường hợp D: agent có cả hai overload**

```bash
java -javaagent:agent-both.jar=check -cp out demo.App
```

Stdout:

```text
[both] selected two-argument premain
[app] main started
```

Không có dòng `selected one-argument premain`: JVM **không** gọi cả hai và cũng không chọn dựa theo thứ tự xuất hiện trong source.

**Trường hợp E: nhiều startup agents trên cùng lệnh Java**

```bash
java -javaagent:agent-one.jar=first -javaagent:agent-two.jar=second -cp out demo.App
```

Stdout:

```text
[one] args=first
[two] args=second
[two] instrumentation=true
[app] main started
```

Khi `-javaagent` xuất hiện nhiều lần, các `premain` được gọi theo **thứ tự agent trong dòng lệnh**, trước `main` của ứng dụng. Việc nhiều agent cùng thực hiện instrumentation có thể gây tương tác ở các bài nâng cao; ví dụ này chỉ minh họa thứ tự khởi tạo.

## 5. Vì sao các chữ ký này giống và khác `main(String[] args)`?

| Điểm so sánh | `main` ứng dụng | `premain` của startup agent |
|---|---|---|
| Điểm vào được chọn qua | Tên lớp chạy trong lệnh `java`, hoặc `Main-Class` với `java -jar` | `Premain-Class` trong JAR được truyền qua `-javaagent` |
| Chữ ký thông dụng | `public static void main(String[] args)` | Một trong hai chữ ký `premain` đã nêu |
| Tham số lệnh | Thường là mảng các tham số ứng dụng | `agentArgs` là **một chuỗi** tùy chọn của agent |
| Đối tượng `Instrumentation` | Không phải tham số của `main` | Được truyền cho chữ ký `premain(String, Instrumentation)` |
| Thời điểm | Sau startup agent | Trước `main` ứng dụng |
| Nhiệm vụ | Logic ứng dụng | Khởi tạo việc quan sát/biến đổi chương trình nếu được cấu hình |

Chẳng hạn:

```bash
java -javaagent:agent-one.jar=agent-mode=trace -cp out demo.App app-mode=prod
```

Agent nhận một `String` có nội dung `agent-mode=trace`; ứng dụng nhận một phần tử trong `String[] args` với nội dung `app-mode=prod`. Hai nguồn tham số tách biệt, không nên dùng `main(String[])` để thay `premain(String)`.

Nếu cần nhiều option cho agent, ví dụ:

```bash
java -javaagent:agent-one.jar=mode=trace,level=debug -cp out demo.App
```

Agent nhận chuỗi nguyên vẹn `mode=trace,level=debug`. **Agent phải tự thiết kế và xử lý cú pháp phân tách**, xác thực giá trị, default và lỗi nhập liệu; JVM không tự hiểu `level=debug`.

## 6. `Premain-Class`, `Agent-Class`, `Launcher-Agent-Class`: đừng dùng nhầm

Java có các cơ chế khởi động agent khác nhau. Mỗi thuộc tính manifest định tuyến tới một điểm vào khác nhau:

| Manifest attribute | Cách kích hoạt | Method được tìm |
|---|---|---|
| `Premain-Class` | `java -javaagent:agent.jar ...` khi JVM khởi động | `premain(...)` |
| `Agent-Class` | Cơ chế attach/load agent vào JVM đã chạy (nếu được runtime hỗ trợ) | `agentmain(...)` |
| `Launcher-Agent-Class` | Cơ chế agent đóng trong executable JAR được launcher hỗ trợ | `agentmain(...)` |
| `Main-Class` | Entry point ứng dụng `java -jar app.jar` | `main(...)` |

Đặc biệt, `Launcher-Agent-Class` dù chạy agent trước application `main` vẫn sử dụng `agentmain` theo đặc tả, **không phải** `premain`. Đây là nguồn nhầm lẫn khi chỉ dựa vào chữ “trước `main`”.

Một agent JAR có thể khai báo cả `Premain-Class` và `Agent-Class` nếu hỗ trợ cả hai cách khởi động. Khi chạy với `-javaagent`, JVM dùng `Premain-Class` và bỏ qua `Agent-Class` để chọn startup entry point. Các cờ như `Can-Retransform-Classes` / `Can-Redefine-Classes` liên quan tới năng lực instrumentation, **không thay thế** cho `Premain-Class` và **không tạo ra** method `premain` hợp lệ.

## 7. Những điều `premain` cần làm và giới hạn thực tế

Một `premain` thường:

1. Nhận và kiểm tra options của riêng agent.
2. Khởi tạo cấu hình và thành phần hỗ trợ trước khi ứng dụng chạy.
3. Nếu dùng chữ ký hai tham số, đăng ký `ClassFileTransformer` qua `Instrumentation.addTransformer(...)` khi cần.
4. Thực hiện setup cần thiết khác rồi **trả về** để JVM tiếp tục gọi `main`.

Điều **không tự xảy ra** chỉ vì có `Premain-Class` và `premain`:

- Không có bảo đảm bytecode đã thay đổi: ví dụ trên chỉ in log; không đăng ký transformer.
- Không có transformer được tạo tự động: cần code đăng ký và logic `transform` thực sự.
- Không có bảo đảm mọi lớp của ứng dụng đều chưa được load trước `premain`.
- Không có cơ chế tự gọi `premain` nếu ứng dụng chỉ import lớp agent.
- Không có cam kết agent được phép redefine/retransform mọi lớp: cần kiểm tra khả năng và giới hạn JVM riêng.

`premain` được JVM gọi rất sớm trong vòng đời khởi động và có thể tạo thread hoặc gọi API như code Java thông thường. Tuy nhiên agent cần tránh treo, chờ điều kiện phụ thuộc ứng dụng chưa khởi động hoặc gây exception không kiểm soát: nếu startup agent không khởi tạo được hoặc `premain` ném exception chưa bắt, JVM sẽ hủy quá trình khởi động thay vì chạy tiếp `main`.

Ví dụ về xử lý option mang tính minh họa, không độc lập chạy được vì chỉ là một method:

```java
public static void premain(String agentArgs, Instrumentation inst) {
    if (agentArgs == null || agentArgs.isBlank()) {
        System.err.println("Agent requires mode=<value>");
        return;
    }

    // Thực hiện khởi tạo/đăng ký transformer sau khi xác thực options.
}
```

Ở đây `return` là lựa chọn chính sách của agent: bỏ qua chức năng khởi tạo thêm rồi cho JVM tiếp tục. Nếu agent có lỗi cấu hình nghiêm trọng, có thể cần phát tín hiệu thất bại thay vì im lặng chạy ứng dụng; phải quyết định theo yêu cầu của hệ thống đang instrument.

## 8. Chẩn đoán khi `premain` không được gọi hoặc khởi động thất bại

| Hiện tượng | Cần kiểm tra |
|---|---|
| Ứng dụng chạy nhưng không thấy log agent | Có thật sử dụng `-javaagent:<jarpath>` không? Có trỏ tới JAR đúng không? |
| JVM báo thiếu `Premain-Class` | Header có trong **main section** của `META-INF/MANIFEST.MF` không? Có vô tình chỉ khai báo `Main-Class` hoặc `Agent-Class` không? |
| JVM không tìm được agent class | Tên binary `demo.AgentTwo` có đúng package? JAR có `demo/AgentTwo.class` không? |
| JVM không tìm được phương thức `premain` | Có đúng `public static void`, đúng kiểu và thứ tự tham số, đúng tên chữ thường `premain` không? |
| Đã có hai overload nhưng chỉ thấy log một method | Đây là hành vi chuẩn: ưu tiên chữ ký hai tham số |
| Thấy lỗi `NoClassDefFoundError` lúc startup | Kiểm tra các dependency và khả năng class loader của agent nhìn thấy chúng; đóng gói dependency khi cần |
| `premain` ném exception, `main` không chạy | Xem stack trace và xử lý nguyên nhân trong agent; startup agent thất bại có thể khiến JVM abort |
| Log agent xuất hiện nhưng ứng dụng không bị sửa hành vi | Đang chỉ khởi tạo/ghi log, hay đã đăng ký transformer và trả bytes mới hợp lệ? |

Có thể kiểm tra chữ ký biên dịch trong ví dụ bằng:

```bash
javap -p -classpath out demo.AgentBoth
```

Trong khai báo class được `javap` hiển thị phải có cả method nhận `String` và method nhận `String, java.lang.instrument.Instrumentation`. `javap` là bước nhìn lại bytecode/chữ ký trong class file; nó **không** chứng minh JVM đã chọn method nào khi chạy. Để chứng minh lựa chọn thực tế, dùng stdout ở mục 4.7.

Lưu ý thêm về cách đóng gói: nếu JAR agent dùng thư viện bên ngoài, class của thư viện phải có thể được agent class loader tìm thấy. Có thể đóng dependency vào agent JAR bằng công cụ build phù hợp. Ví dụ ở đây không dùng thư viện ngoài nên không phát sinh yêu cầu này.

## 9. Tình huống tự kiểm tra

**Câu 1.** Manifest ghi `Premain-Class: demo.AgentBoth`, trong lớp có cả hai chữ ký. JVM gọi method nào?

**Đáp án:** `premain(String, Instrumentation)`; chữ ký một tham số là fallback và không được gọi.

**Câu 2.** Một lớp có `public static void premain(String[] args)` và `public static void main(String[] args)`. Đây có phải startup agent hợp lệ không?

**Đáp án:** Không, vì `String[]` không phải `String` trong một trong hai chữ ký `premain` bắt buộc; `main` không thay thế được.

**Câu 3.** Vì sao `Premain-Class: demo/AgentTwo.class` không phải cách khai báo đúng?

**Đáp án:** Giá trị phải là tên lớp dạng nhị phân `demo.AgentTwo`, không phải đường dẫn archive có dấu `/` và đuôi `.class`.

**Câu 4.** Có `Premain-Class` và method `premain` hợp lệ nhưng chạy `java -cp agent-two.jar demo.App`. JVM có tự kích hoạt agent không?

**Đáp án:** Không. Phải dùng con đường startup agent, ví dụ `-javaagent:agent-two.jar`.

**Câu 5.** Một agent cần `Instrumentation.addTransformer(...)`, nên chọn chữ ký nào?

**Đáp án:** Dạng `premain(String agentArgs, Instrumentation inst)` để nhận `Instrumentation` trực tiếp từ JVM.

**Câu 6.** Dùng hai tùy chọn `-javaagent` liên tiếp, JVM gọi `main` sau agent nào?

**Đáp án:** Sau khi các `premain` startup tương ứng đã được gọi theo thứ tự khai báo và hoàn tất thành công, JVM mới gọi application `main`.

## 10. Những điểm cần giữ chắc

- `Premain-Class` là header của **agent JAR manifest**, mang **binary name** của lớp chứa `premain`, không phải tên file hay tên method.
- Chỉ có hai chữ ký entry point startup agent được đặc tả: `public static void premain(String, Instrumentation)` và `public static void premain(String)`.
- JVM **ưu tiên chữ ký hai tham số**, fallback sang một tham số; cả hai tồn tại không có nghĩa cả hai cùng chạy.
- `agentArgs` là **một `String` options riêng của agent**; `Instrumentation` chỉ được truyền vào chữ ký hai tham số.
- `premain` được gọi trước application `main`; lỗi khởi tạo agent hoặc exception chưa xử lý có thể ngăn ứng dụng bắt đầu.
- Một agent được gọi thành công chưa chắc đã làm bytecode khác đi. Khởi động agent và cài đặt phép biến đổi là hai bước riêng.

## Tài liệu đối chiếu

- Oracle Java 17 — [Package `java.lang.instrument`: Starting an Agent from the Command-Line Interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- Oracle Java 17 — [Interface `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- Oracle Java 21 — [JAR File Specification: manifest, main attributes](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html)
