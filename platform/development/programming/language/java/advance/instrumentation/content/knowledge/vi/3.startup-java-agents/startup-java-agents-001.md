# Đóng gói agent JAR và cấu trúc META-INF/MANIFEST.MF

## 1. Mục tiêu của bài

Trong Java Instrumentation, **startup agent** là mã được JVM nạp khi khởi động thông qua tham số **\`-javaagent\`**. Agent thường cài đặt các hook đo đạc, đăng ký **ClassFileTransformer** hoặc khởi tạo telemetry trước khi ứng dụng thực thi hàm **\`main\`**.

Bài này tập trung vào **đóng gói và khai báo điểm vào** cho startup agent: tạo tệp JAR đúng cấu trúc, viết **\`META-INF/MANIFEST.MF\`**, xây dựng bằng công cụ JDK/Gradle, chạy với **\`-javaagent\`**, kiểm tra hiện vật và nhận diện lỗi khởi động. Bài không yêu cầu triển khai bytecode rewriting; một agent hợp lệ có thể chỉ ghi log trong **\`premain\`** để chứng minh quá trình nạp thành công.

Sau khi học, bạn có thể:

1. Giải thích vì sao một tệp JAR có class agent vẫn **chưa đủ** nếu thiếu thuộc tính manifest đúng.
2. Phân biệt **\`Premain-Class\`**, **\`Main-Class\`**, **\`Agent-Class\`** và **\`Launcher-Agent-Class\`**.
3. Tự biên dịch và đóng gói một agent JAR có thể chạy trên Java 17+.
4. Kiểm tra entry trong JAR, nội dung manifest và thứ tự gọi **\`premain\`** trước **\`main\`**.
5. Xử lý lỗi do sai tên lớp, sai đường dẫn, manifest hỏng, phụ thuộc thiếu hoặc cờ capability không phù hợp.

## 2. JVM tìm startup agent như thế nào?

Ví dụ lệnh:

~~~bash
java -javaagent:out/startup-agent.jar=lab -cp out/app demo.app.HelloApp
~~~

Diễn giải các thành phần:

- **\`-javaagent:out/startup-agent.jar\`**: yêu cầu JVM nạp JAR chứa agent khi khởi động.
- **\`=lab\`**: chuỗi tùy chọn của agent; JVM chuyển nguyên chuỗi **\`lab\`** cho **\`premain\`**, không tự phân tích các cặp key/value bên trong.
- **\`-cp out/app\`**: classpath chứa lớp chính của ứng dụng.
- **\`demo.app.HelloApp\`**: lớp có **\`public static void main(String[] args)\`** của ứng dụng.

Trình tự khái niệm:

~~~text
java launcher
   |
   v
JVM nhận -javaagent:path[=options]
   |
   v
Mở agent JAR, đọc META-INF/MANIFEST.MF
   |
   v
Tra thuộc tính Premain-Class -> nạp lớp agent
   |
   v
Gọi public static void premain(...) của agent
   |
   +--> agent có thể đăng ký transformer / khởi tạo telemetry
   |
   v
premain trả về bình thường
   |
   v
Gọi main(...) của ứng dụng
~~~

Theo đặc tả **\`java.lang.instrument\`**, khi dùng **\`-javaagent\`**, manifest **phải có \`Premain-Class\`** trong *main section*. JVM ưu tiên chữ ký:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

Nếu lớp không có chữ ký hai tham số, JVM thử:

~~~java
public static void premain(String agentArgs)
~~~

Cả hai đều cần **\`public static\`** và trả về **\`void\`**. Kiểu **\`Instrumentation\`** thuộc gói **\`java.lang.instrument\`**. Nên dùng chữ ký hai tham số khi cần API biến đổi/retransform class. **\`premain\`** hoàn thành thành công thì JVM tiếp tục chạy **\`main\`**; không tìm thấy lớp/phương thức hợp lệ hoặc **\`premain\`** ném ngoại lệ không được xử lý thì JVM dừng quá trình khởi động ứng dụng.

## 3. Một agent JAR hợp lệ trông như thế nào?

JAR là tệp ZIP có quy ước cấu trúc. Ví dụ:

~~~text
startup-agent.jar
├── META-INF/
│   └── MANIFEST.MF
└── demo/
    └── agent/
        └── StartupAgent.class
~~~

Bên trong JAR, đường dẫn **\`demo/agent/StartupAgent.class\`** phải tương ứng với **\`package demo.agent;\`** và tên lớp **\`StartupAgent\`**. Tuy nhiên, giá trị của **\`Premain-Class\`** là **tên nhị phân đầy đủ của lớp Java**:

~~~text
Premain-Class: demo.agent.StartupAgent
~~~

Không dùng các giá trị sai như:

~~~text
Premain-Class: demo/agent/StartupAgent.class
Premain-Class: StartupAgent.java
Premain-Class: out/agent/demo/agent/StartupAgent.class
~~~

### 3.1. Nội dung main manifest tối thiểu

Một tệp nguồn **\`agent.mf\`** có thể chứa:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent

~~~

Trong đoạn trên, **dòng trống ở cuối** kết thúc *main section*. Khi dùng công cụ **\`jar\`** với tệp manifest bên ngoài, hãy bảo đảm có ký tự xuống dòng cuối tệp; thiếu newline có thể khiến dòng cuối bị bỏ qua. Tệp manifest được lưu trong JAR tại đường dẫn **\`META-INF/MANIFEST.MF\`**; khi đóng gói bằng **\`jar --manifest\`**, JDK tạo entry này cho bạn.

Một cấu hình rõ ràng hơn cho agent mẫu:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent
Can-Redefine-Classes: false
Can-Retransform-Classes: false

~~~

Hai dòng **\`Can-...\`** ở đây không bắt buộc: nếu vắng mặt, giá trị mặc định là **\`false\`**. Đừng bật **\`true\`** khi ví dụ chưa thực sự cần capability đó.

### 3.2. Quy tắc cú pháp MANIFEST.MF

- Mỗi thuộc tính là một dòng **\`Tên-Thuộc-Tính: giá trị\`**, có dấu **\`:\`** rồi một dấu cách.
- **\`Manifest-Version: 1.0\`** phải nằm đầu main section; tệp manifest có thể có các section theo từng JAR entry nhưng **\`Premain-Class\`** của startup agent phải ở **main section**.
- Một **dòng trống** phân tách các section. Nếu đặt **\`Premain-Class\`** sau một dòng trống ở vị trí sai, nó có thể không còn là thuộc tính chính.
- Mỗi dòng vật lý có giới hạn **72 byte UTF-8**, không phải 72 ký tự Unicode. Giá trị dài được nối tiếp bằng dòng mới bắt đầu bằng **một dấu cách**; công cụ tạo manifest đáng tin cậy giúp tránh cắt sai byte.
- Tên thuộc tính trong một section không được lặp lại. Nội dung dùng UTF-8; tránh sinh BOM và ký tự điều khiển bất thường.
- Manifest không phải JSON, YAML hoặc file **\`.properties\`** thuần; không viết **\`Premain-Class=...\`** hay thụt đầu dòng tùy ý.

**Chú ý:** Không cần tự tạo thư mục **\`META-INF\`** ở thư mục nguồn cho ví dụ dùng **\`jar --manifest\`**. Công cụ sẽ đưa manifest vào đường dẫn chuẩn trong JAR.

## 4. Thực hành hoàn chỉnh trên Java 17+

Ta sẽ tạo **hai hiện vật riêng**: JAR của agent và class ứng dụng. Mã nguồn được thiết kế để người học tự chạy, không dùng thư viện ngoài.

### 4.1. Cây thư mục

Tạo cấu trúc:

~~~text
agent-jar-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── java/
│   │       └── demo/
│   │           └── agent/
│   │               └── StartupAgent.java
│   └── app/
│       └── java/
│           └── demo/
│               └── app/
│                   └── HelloApp.java
└── out/                 # Tạo trong bước build
    ├── agent/
    ├── app/
    └── startup-agent.jar
~~~

Các tệp nằm dưới **\`src\`** là mã của bài thực hành; **\`out\`** chứa sản phẩm biên dịch và JAR. Thư mục **\`out\`** chưa cần tồn tại lúc bắt đầu.

### 4.2. Mã startup agent

Tệp **\`src/agent/java/demo/agent/StartupAgent.java\`**:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    private StartupAgent() {}

    public static void premain(String agentArgs,
                               Instrumentation instrumentation) {
        System.out.println("agent-premain: " + agentArgs);
        System.out.println(
            "instrumentation-ready: " + (instrumentation != null)
        );
    }
}
~~~

**Giải thích:** **\`premain\`** là entry point được JVM gọi do **\`Premain-Class\`**, không phải do **\`Main-Class\`**. Tham số **\`instrumentation\`** là đối tượng JVM cung cấp để agent thực hiện instrument class. Ví dụ chỉ xác minh nó đã được truyền vào; **chưa đăng ký \`ClassFileTransformer\`** và chưa sửa bytecode nào. Constructor private không cản trở JVM gọi phương thức tĩnh **\`premain\`**.

### 4.3. Mã ứng dụng cần chạy

Tệp **\`src/app/java/demo/app/HelloApp.java\`**:

~~~java
package demo.app;

public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("app-main");
    }
}
~~~

Ứng dụng này không biết tới mã agent. Nó không cần import **\`StartupAgent\`** và không gọi **\`premain\`** trực tiếp.

### 4.4. Viết tệp agent.mf

Tệp **\`agent.mf\`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent
Can-Redefine-Classes: false
Can-Retransform-Classes: false

~~~

Lưu tệp dưới dạng UTF-8 và giữ **newline ở cuối**. Dòng trống cuối được minh họa để kết thúc main section. Tên lớp phải đúng cả package lẫn class như mã nguồn ở bước 4.2.

### 4.5. Tạo thư mục build

Trong shell Bash/Linux/macOS, tại thư mục **\`agent-jar-lab\`**:

~~~bash
mkdir -p out/agent out/app
~~~

Trong PowerShell/Windows, dùng lệnh tương đương:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

### 4.6. Biên dịch và tạo JAR

Các lệnh JDK sau dùng được ở Bash hoặc PowerShell, miễn là terminal đang ở thư mục gốc bài thực hành:

~~~bash
javac --release 17 -d out/agent src/agent/java/demo/agent/StartupAgent.java
javac --release 17 -d out/app src/app/java/demo/app/HelloApp.java
jar --create --file out/startup-agent.jar --manifest agent.mf -C out/agent .
~~~

Phân tích lệnh:

- **\`javac --release 17\`** biên dịch theo API/ngôn ngữ mục tiêu Java 17; sử dụng JDK 17 trở lên hỗ trợ tùy chọn này.
- **\`-d out/agent\`** lưu **\`StartupAgent.class\`** vào **\`out/agent/demo/agent/\`**; **\`-d out/app\`** làm tương tự cho ứng dụng.
- **\`jar --create\`** tạo archive mới; **\`--file\`** đặt đường dẫn JAR kết quả.
- **\`--manifest agent.mf\`** hợp nhất các thuộc tính khai báo vào manifest của JAR.
- **\`-C out/agent .\`** chuyển sang thư mục class của agent khi thêm nội dung; vì vậy class vào JAR ở **\`demo/agent/StartupAgent.class\`** thay vì có tiền tố sai **\`out/agent/\`**.
- Chỉ các class bên dưới **\`out/agent\`** được đưa vào agent JAR; class ứng dụng nằm ở **\`out/app\`** để chạy bằng **\`-cp\`**.

Tùy chọn ngắn tương đương có thể là **\`jar cfm out/startup-agent.jar agent.mf -C out/agent .\`**. Với cú pháp ngắn, **thứ tự \`f\` và \`m\` quyết định thứ tự hai đối số**; dùng phiên bản dài để dễ đọc và tránh nhầm.

### 4.7. Chạy ứng dụng với startup agent

~~~bash
java -javaagent:out/startup-agent.jar=lab -cp out/app demo.app.HelloApp
~~~

Stdout của ví dụ:

~~~text
agent-premain: lab
instrumentation-ready: true
app-main
~~~

Kết quả chứng minh ba điều: JVM đã đọc **\`Premain-Class\`** và gọi đúng lớp; chuỗi **\`lab\`** đi vào **\`agentArgs\`**; **\`premain\`** chạy trước **\`main\`** của ứng dụng. Nó **chưa** chứng minh có phương thức nào bị chèn bytecode.

So sánh khi không dùng agent:

~~~bash
java -cp out/app demo.app.HelloApp
~~~

Stdout chỉ còn:

~~~text
app-main
~~~

## 5. Kiểm tra JAR và manifest sau khi build

Không nên kết luận agent đã đóng gói đúng chỉ vì thấy tệp **\`.jar\`** được tạo.

### 5.1. Liệt kê entry thực tế

~~~bash
jar --list --file out/startup-agent.jar
~~~

Với JDK và lệnh build ở trên, các entry quan trọng bao gồm:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/agent/
demo/agent/StartupAgent.class
~~~

Danh sách phải có cả **\`META-INF/MANIFEST.MF\`** và **\`demo/agent/StartupAgent.class\`**. Một JAR chỉ chứa file source **\`.java\`**, hoặc class nằm sai đường dẫn package, không đáp ứng yêu cầu của ví dụ.

### 5.2. Đọc thuộc tính chính bằng API Java

Tạo **\`InspectJar.java\`** tại gốc thư mục bài thực hành:

~~~java
import java.util.jar.JarFile;

public class InspectJar {
    public static void main(String[] args) throws Exception {
        try (JarFile jar = new JarFile(args[0])) {
            var attrs = jar.getManifest().getMainAttributes();
            System.out.println(
                "Premain-Class=" + attrs.getValue("Premain-Class")
            );
            System.out.println(
                "class-present=" +
                (jar.getEntry("demo/agent/StartupAgent.class") != null)
            );
        }
    }
}
~~~

Chạy bằng source-file launcher của Java 17+:

~~~bash
java InspectJar.java out/startup-agent.jar
~~~

Stdout:

~~~text
Premain-Class=demo.agent.StartupAgent
class-present=true
~~~

Dùng **\`JarFile.getManifest().getMainAttributes()\`** giúp đọc **manifest đã được đóng gói thật**, tránh nhầm giữa **\`agent.mf\`** ở thư mục nguồn với **\`META-INF/MANIFEST.MF\`** trong sản phẩm cuối. Nếu **\`getManifest()\`** trả về **\`null\`**, JAR không có manifest để đọc; ví dụ này sẽ lỗi và cần kiểm tra lại quá trình build.

### 5.3. Ba lớp bằng chứng cần cùng khớp

| Cần xác nhận | Cách kiểm tra | Kết quả đúng trong ví dụ |
|---|---|---|
| Manifest hiện diện trong JAR | **\`jar --list\`** | Có **\`META-INF/MANIFEST.MF\`** |
| Điểm vào ánh xạ đúng lớp | **\`InspectJar\`** | **\`Premain-Class=demo.agent.StartupAgent\`**, class-present=true |
| JVM gọi agent trước ứng dụng | Chạy với **\`-javaagent\`** | **\`agent-premain\`** xuất trước **\`app-main\`** |

Đây là phép kiểm chứng đơn giản nhưng có giá trị: nếu chỉ xem file manifest ở source, bạn có thể bỏ qua trường hợp build tool tạo JAR bằng manifest khác.

## 6. Các thuộc tính manifest liên quan tới Java agent

| Thuộc tính | Khi nào dùng | Ý nghĩa và lưu ý |
|---|---|---|
| **\`Manifest-Version\`** | Bản manifest thông thường | Mở đầu main section, ví dụ **\`1.0\`** |
| **\`Premain-Class\`** | **Bắt buộc cho \`-javaagent\`** | Tên đầy đủ của class định nghĩa **\`premain\`** |
| **\`Agent-Class\`** | Agent gắn vào JVM đang chạy, nếu VM hỗ trợ | Tên class định nghĩa **\`agentmain\`**; không thay **\`Premain-Class\`** cho **\`-javaagent\`** |
| **\`Launcher-Agent-Class\`** | Agent đóng chung với executable JAR, nếu launcher hỗ trợ | Launcher gọi **\`agentmain\`** trước **\`main\`**; đây là cơ chế riêng |
| **\`Main-Class\`** | JAR ứng dụng chạy bằng **\`java -jar\`** | Chỉ định **\`main\`**, không làm JAR trở thành startup agent |
| **\`Can-Redefine-Classes\`** | Agent cần **\`Instrumentation.redefineClasses\`** | Boolean; mặc định **\`false\`**; còn phụ thuộc VM có hỗ trợ |
| **\`Can-Retransform-Classes\`** | Agent cần **\`Instrumentation.retransformClasses\`** | Boolean; mặc định **\`false\`**; chỉ bật khi thật sự sử dụng |
| **\`Can-Set-Native-Method-Prefix\`** | Trường hợp rất đặc thù liên quan native method prefix | Boolean; mặc định **\`false\`** |
| **\`Boot-Class-Path\`** | Cần cung cấp class cho bootstrap loader | Tùy chọn, ảnh hưởng nạp lớp ở mức thấp; tránh thêm nếu không có yêu cầu |
| **\`Class-Path\`** | Khai báo JAR phụ thuộc theo quy tắc JAR manifest | Các URL tương đối được diễn giải theo ngữ cảnh JAR; phải đóng gói/triển khai thư viện tương ứng |

**Cờ capability không phải một thao tác instrumentation.** Ví dụ **\`Can-Retransform-Classes: true\`** chỉ yêu cầu khả năng retransform; nó không tự biến đổi class. Trong mã agent, có thể hỏi **\`instrumentation.isRetransformClassesSupported()\`** trước khi gọi API. Một capability còn chịu điều kiện của JVM triển khai, và thao tác redefine/retransform có giới hạn riêng.

Cũng không nên thêm **\`Can-Redefine-Classes: true\`** hoặc **\`Boot-Class-Path\`** chỉ để "cho chắc". Bộ thuộc tính nên phản ánh đúng việc agent sẽ thực hiện.

## 7. Phân biệt entry point theo cách khởi chạy

Ba trường hợp sau dùng khái niệm "agent" nhưng không đồng nghĩa:

~~~text
A) JVM startup với -javaagent
   agent.jar + Premain-Class --> premain(...)
   app classes               --> main(...)

B) Attach agent vào JVM đang chạy (nếu được hỗ trợ)
   agent.jar + Agent-Class   --> agentmain(...)

C) Executable JAR chứa launcher agent (nếu được hỗ trợ)
   app.jar + Launcher-Agent-Class --> agentmain(...)
   app.jar + Main-Class           --> main(...)
~~~

- Với **\`java -javaagent:agent.jar ...\`**, JVM đọc **\`Premain-Class\`**; có khai báo **\`Agent-Class\`** cũng không khiến JVM gọi **\`agentmain\`** trong đường khởi chạy này.
- Với cách gắn agent sau khi JVM chạy, **\`Agent-Class\`** và **\`agentmain\`** mới là cặp tương ứng. Cơ chế attach còn phụ thuộc phiên bản JVM, cấu hình và quyền, không phải nội dung bài đóng gói startup này.
- Với executable JAR có **\`Launcher-Agent-Class\`**, Java launcher sử dụng **\`agentmain\`** cho agent đóng chung; dù diễn ra trước **\`main\`**, vẫn không phải cơ chế **\`-javaagent\`**.
- Một JAR có thể chứa nhiều thuộc tính liên quan nếu thực sự hỗ trợ nhiều cách chạy, nhưng **mỗi cách chạy đọc thuộc tính phù hợp với nó**.

Từ đó suy ra một lỗi rất phổ biến: **thêm \`Main-Class: demo.agent.StartupAgent\` không thay thế \`Premain-Class\`**. Class có **\`premain\`** nhưng thiếu thuộc tính startup vẫn không được nạp qua **\`-javaagent\`** như mong đợi.

## 8. Tích hợp đóng gói vào Gradle

Với một project Gradle dùng plugin **\`java\`**, đặt class agent ở **\`src/main/java/demo/agent/StartupAgent.java\`**. Ví dụ **\`build.gradle\`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar') {
    manifest {
        attributes(
            'Premain-Class': 'demo.agent.StartupAgent',
            'Can-Redefine-Classes': 'false',
            'Can-Retransform-Classes': 'false'
        )
    }
}
~~~

Chạy ở project có Gradle Wrapper:

~~~bash
./gradlew jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat jar
~~~

Thông thường sản phẩm nằm trong **\`build/libs/\`** với tên theo project và version. Kiểm tra bằng **\`jar --list\`** và **\`InspectJar\`** như mục 5, rồi khởi chạy bằng đường dẫn JAR thực tế.

### Điều Gradle không tự làm

Task **\`jar\`** mặc định đóng gói output của source set đã cấu hình và manifest được khai báo, nhưng **không tự nhét toàn bộ JAR phụ thuộc từ \`implementation\` vào bên trong**. Nếu agent dùng thư viện bổ sung, hãy thiết kế cách phân phối dependency rõ ràng (ví dụ JAR phụ thuộc đi kèm và đường nạp phù hợp, hoặc *shaded/fat JAR* khi cần), đồng thời kiểm tra thực tế bằng chạy agent.

Nếu chọn shaded JAR, phải xử lý xung đột resource/**\`META-INF\`**, chữ ký JAR gốc và relocation phù hợp. Chỉ có một manifest đúng là **chưa đủ** nếu JVM không nạp được class thư viện mà **\`StartupAgent\`** sử dụng.

Không nên trộn **\`Main-Class\`** của ứng dụng vào agent JAR chỉ để chạy thử, trừ khi sản phẩm thực sự được thiết kế là executable application kiêm agent và đã xác định rõ cả hai entry point. Ví dụ ở mục 4 tách hai JAR/classpath để dễ kiểm tra trách nhiệm.

## 9. Vấn đề class loading và dependency khi đóng gói

Startup agent chạy trong **cùng JVM** với ứng dụng, không phải một process độc lập. Việc dùng class loader và mã agent có thể tác động tới quá trình khởi động hoặc hành vi của ứng dụng:

1. **Tên package và đường dẫn class:** Manifest chỉ cung cấp tên lớp; JVM vẫn phải tìm được bytecode ở đúng entry trong JAR. Đừng nén cả thư mục **\`out/agent\`** thành tiền tố path bên trong archive.
2. **Phụ thuộc bên ngoài:** Nếu class agent tham chiếu helper class nhưng JAR/helper không có trong nơi JVM tìm kiếm, lúc khởi động có thể gặp **\`ClassNotFoundException\`** hoặc **\`NoClassDefFoundError\`**.
3. **\`Class-Path\` manifest:** Đây là thuộc tính khai báo đường dẫn tới các JAR bổ sung theo đặc tả JAR. Nếu dùng, các đường dẫn tương đối phải khớp bố cục phân phối (ví dụ **\`libs/helper.jar\`** bên cạnh agent); đừng mặc định **\`-cp\`** của ứng dụng luôn giải quyết mọi dependency của agent.
4. **Bootstrap classes:** Đường nạp của bootstrap loader khác đường nạp ứng dụng. **\`Boot-Class-Path\`** và việc append JAR vào bootstrap search path là chủ đề nâng cao; khai báo sai có thể gây xung đột, ảnh hưởng rộng.
5. **Tương thích:** Class agent và thư viện của nó phải tương thích với Java runtime đích. Ví dụ biên dịch **\`--release 17\`** giúp tránh phát sinh class file đòi runtime mới hơn Java 17.
6. **Mã chạy trong \`premain\`:** Không nên chạy tác vụ dài, phụ thuộc service chưa sẵn sàng hoặc ném lỗi chưa xử lý. Nếu agent lỗi, **ứng dụng có thể không khởi động**.

Khi phân phối cho nhiều môi trường, hãy dùng hiện vật JAR đã kiểm thử, xác định rõ version và dependency, đánh giá nguồn tin cậy của agent vì agent có khả năng can thiệp bytecode và hành vi của JVM.

## 10. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| JVM báo thiếu **\`Premain-Class\`** hoặc không khởi động với **\`-javaagent\`** | JAR đóng gói mặc định nhưng không nhập manifest của agent | Kiểm tra **manifest bên trong JAR**, build lại với **\`--manifest\`** |
| JVM không tải được agent class | Giá trị **\`Premain-Class\`** không đúng tên package/class; class entry sai | So sánh **\`demo.agent.StartupAgent\`** với **\`demo/agent/StartupAgent.class\`** |
| JVM báo không tìm thấy **\`premain\`** phù hợp | Phương thức sai tên, không **\`public static\`**, sai tham số hoặc sai kiểu trả về | Dùng một trong hai chữ ký ở mục 2 |
| Tên lớp đúng nhưng startup lỗi khi load | Thiếu class dependency, bản Java không tương thích hoặc lỗi static initializer | Kiểm tra stack trace, dependency, **\`javap\`**/**\`jar --list\`**, JDK chạy |
| JVM dừng sau log trong **\`premain\`** | Agent ném exception/error chưa được xử lý | Đọc nguyên nhân gốc; giữ khởi tạo agent gọn, báo lỗi hữu ích |
| Chỉ thấy **\`app-main\`**, không thấy **\`agent-premain\`** | Ứng dụng được chạy không có **\`-javaagent\`** hoặc lệnh đặt sai vị trí | Đặt **\`-javaagent\`** trong nhóm JVM options **trước** tên main class hoặc **\`-jar\`** |
| **\`Can-Retransform-Classes\`** được khai báo nhưng API không khả dụng | JVM không hỗ trợ hoặc manifest/build không thực sự khai báo đúng | Xem **\`isRetransformClassesSupported()\`**, manifest đóng gói và giới hạn VM |
| Manifest có **\`Premain-Class\`** trong source nhưng không thấy trong JAR | Cấu hình build ghi đè/nhập sai manifest, dòng cuối không có newline, section sai | Dùng **\`InspectJar\`**, kiểm tra build task và định dạng **\`agent.mf\`** |
| Chạy **\`java -jar startup-agent.jar\`** báo thiếu main | Agent JAR không có **\`Main-Class\`** và không nhằm chạy như ứng dụng | Dùng **\`java -javaagent:... -cp ...\`**; phân biệt hai cơ chế |

### 10.1. Vị trí JVM option rất quan trọng

Đúng:

~~~bash
java -javaagent:out/startup-agent.jar=lab -cp out/app demo.app.HelloApp
~~~

Cũng là JVM option hợp lệ nếu chạy một executable application JAR:

~~~bash
java -javaagent:out/startup-agent.jar=lab -jar my-app.jar
~~~

Ngược lại, các chuỗi đặt **sau** tên main class hoặc **sau \`-jar my-app.jar\`** thường được chuyển thành **tham số của ứng dụng**, không còn được Java launcher hiểu là tùy chọn bật agent:

~~~text
java -jar my-app.jar -javaagent:out/startup-agent.jar
                         ^ đối số ứng dụng, không bật agent
~~~

### 10.2. Không nhầm việc đặt tên tệp

- **\`agent.mf\`** là tệp văn bản đầu vào bạn tạo ở thư mục project.
- **\`META-INF/MANIFEST.MF\`** là entry manifest chuẩn ở **bên trong JAR đã build**.
- **\`startup-agent.jar\`** là tệp ZIP/JAR đóng gói được chuyển cho **\`-javaagent\`**.
- **\`demo.agent.StartupAgent\`** là tên class Java dùng trong giá trị thuộc tính **\`Premain-Class\`**.
- **\`demo/agent/StartupAgent.class\`** là đường dẫn entry bytecode trong JAR.

Năm chuỗi này liên quan với nhau nhưng **không thể dùng thay thế**.

## 11. Bài tập luyện tập và tự kiểm tra

### Bài tập A — sửa tên agent không làm hỏng manifest

Đổi package từ **\`demo.agent\`** thành **\`lab.instrument\`** và chuyển file thành **\`src/agent/java/lab/instrument/StartupAgent.java\`**. Sau đó cập nhật **\`Premain-Class: lab.instrument.StartupAgent\`** và build lại. Kiểm tra **\`lab/instrument/StartupAgent.class\`** trong JAR. Nếu chỉ sửa source mà không sửa manifest, giải thích tại sao JVM không tìm thấy lớp.

### Bài tập B — truyền cấu hình

Chạy:

~~~bash
java -javaagent:out/startup-agent.jar=mode=debug,tag=demo -cp out/app demo.app.HelloApp
~~~

Quan sát dòng log agent: chuỗi được truyền nguyên dạng **\`mode=debug,tag=demo\`**. Hãy tự viết parser của agent nếu muốn tách **\`mode\`** và **\`tag\`**; JVM không tự tạo Map cho tham số này.

### Bài tập C — chỉ rõ giới hạn capability

Trong **\`premain\`**, thử in:

~~~java
System.out.println(
    "retransform-supported: " +
    instrumentation.isRetransformClassesSupported()
);
~~~

So sánh khi manifest có/không có **\`Can-Retransform-Classes: true\`** trên JVM thí nghiệm. Không suy diễn rằng mọi JVM đều hỗ trợ; API phản ánh khả năng thực tế đã được thương lượng khi agent khởi động. Với bài hiện tại, không cần gọi **\`retransformClasses\`**.

### Câu hỏi tự đánh giá

**1. Có cần \`Main-Class\` trong agent JAR chạy bằng \`-javaagent\` không?**  
Không. Cần **\`Premain-Class\`**; **\`Main-Class\`** phục vụ **\`java -jar\`** cho ứng dụng.

**2. Vì sao Java class có \`premain\` chưa đủ?**  
Vì launcher cần biết **class nào chứa phương thức** qua main manifest của agent JAR.

**3. \`Premain-Class: demo/agent/StartupAgent.class\` có đúng không?**  
Không. Phải ghi tên class đầy đủ theo Java: **\`demo.agent.StartupAgent\`**.

**4. Bật \`Can-Retransform-Classes: true\` có tự động sửa class không?**  
Không. Đây là khai báo khả năng cần thiết, còn agent phải gọi API tương ứng và tuân theo khả năng VM.

**5. Cách nào chứng minh manifest thật sự vào JAR?**  
Dùng **\`jar --list\`** để xác nhận entry và **\`JarFile.getManifest()\`** để đọc thuộc tính đã đóng gói; sau đó chạy với **\`-javaagent\`**.

**6. Nếu stdout có \`agent-premain\` trước \`app-main\`, đã chứng minh bytecode được biến đổi chưa?**  
Chưa. Chỉ chứng minh agent được nạp và **\`premain\`** chạy thành công.

## 12. Kết luận và tài liệu chuẩn

Một startup agent dùng **\`-javaagent\`** phải có **JAR hợp lệ**, **class \`premain\` hợp lệ** và **\`Premain-Class\` trong \`META-INF/MANIFEST.MF\`** trỏ đúng tên class. Đóng gói xong phải kiểm tra **nội dung của JAR thực tế** và xác nhận **JVM gọi \`premain\` trước \`main\`**. Chỉ sau đó mới thêm transformer, metrics hoặc các tính năng instrumentation phức tạp hơn.

Tài liệu chính thức:

- [Java SE 17 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): quy định **\`-javaagent\`**, chữ ký **\`premain\`**, các mục manifest và khả năng JVM.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): cú pháp manifest, section, continuation line, giới hạn byte và thuộc tính **\`Main-Class\`**/**\`Class-Path\`**.
- [JDK jar command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo và kiểm tra JAR với **\`--manifest\`**, **\`-C\`**, **\`--list\`**.
