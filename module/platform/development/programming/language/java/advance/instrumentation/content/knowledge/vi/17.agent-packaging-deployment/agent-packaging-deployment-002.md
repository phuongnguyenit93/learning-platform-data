# Phụ thuộc của agent, xung đột phiên bản và cô lập tên lớp thư viện

> **Ngữ cảnh:** Java Advance → Instrumentation → **Đóng gói và triển khai**. Java agent được đưa vào JVM bằng `-javaagent` không mặc nhiên có class loader độc lập. Theo đặc tả `java.lang.instrument`, các class trong agent JAR được nạp bằng **system class loader**, thuộc **unnamed module của loader ấy**. Khi agent và ứng dụng cùng đóng gói một thư viện với **binary name giống nhau nhưng phiên bản API khác nhau**, runtime có thể chỉ định nghĩa một bản trong cùng loader. Kết quả là lỗi linkage hoặc hành vi sai khó tái hiện. Bài phân tích root cause, các lựa chọn đóng gói, cơ chế **shading và package relocation**, điểm mù của resource/SPI, và chiến lược kiểm chứng. Ví dụ Java 17+ và Maven Shade Plugin 3.6.2 đã được build/run trên OpenJDK 24.

## 1. Vì sao một dependency của agent có thể phá ứng dụng?

Java class identity là cặp **binary name + defining class loader**, không phải `JAR filename + class name`. Nếu hai JAR cùng có:

~~~text
org/example/codec/Codec.class
~~~

và cả hai bản đều được tra cứu bởi **cùng system class loader**, JVM không định nghĩa hai class cùng tên để agent dùng một bản và app dùng bản còn lại. Loader sẽ xác định một class identity cho binary name đó. Những caller đã được compile với API khác sẽ liên kết vào class đã được JVM định nghĩa tại runtime.

Ví dụ:

~~~text
                 JVM system class loader
                     /           \
  startup agent JAR /             \ application classpath JAR
  org.example.codec.Codec v1       org.example.codec.Codec v2
  có method agentOnly()            có method appOnly()
                     \            /
                      một binary name
                            |
                  một class được định nghĩa
                            |
              caller còn lại có thể thiếu API
~~~

**Không bảo đảm** trong mọi JVM/launcher rằng “agent luôn thắng” hay “app luôn thắng”. Việc load có thể phụ thuộc classpath search, agent startup, thời điểm resolution và class loader thực tế. Điều có thể dựa vào là: **trong cùng defining loader, hai bản class trùng binary name không tự thành hai phiên bản độc lập**.

Khác với trường hợp này, một plugin/container có thể dùng **hai custom class loaders** khác nhau để định nghĩa các class cùng binary name. Khi đó chúng là **hai class identities khác nhau**, và một object của loader A không tự cast sang class có cùng tên từ loader B. Vì vậy vẫn cần thiết kế ranh giới public API để các bên giao tiếp được.

### Những lỗi thực tế

| Triệu chứng | Nguyên nhân thường gặp | Bản chất |
|---|---|---|
| `NoSuchMethodError` | Caller compile với v1 nhưng runtime load v2 thiếu method/descriptor | Binary linkage error |
| `NoSuchFieldError` | Field bị đổi tên, bỏ hoặc đổi descriptor | Binary compatibility |
| `AbstractMethodError` | Interface/implementation thuộc các bản không tương thích | Linkage khi thực hiện call |
| `IncompatibleClassChangeError` | Static/instance, class/interface hoặc hierarchy đã đổi | Incompatible binary definitions |
| `ClassNotFoundException` | Loader được yêu cầu không tìm được class | Class lookup |
| `NoClassDefFoundError` | Dependency không được định nghĩa hoặc linkage/init trước đó thất bại | Loading/linkage tại runtime |
| `ClassCastException` giữa hai class tên giống hệt | Hai loaders định nghĩa hai type identities | Loader isolation không có shared API |
| `ServiceConfigurationError` | Service descriptor hỏng, provider path cũ hoặc class không tương thích | Resource metadata/SPI |
| `ExceptionInInitializerError` | Static initializer của lib ném exception | Runtime behavior/configuration |
| `SecurityException` với signed JAR | Signature metadata không còn khớp sau repackage | Artifact integrity |

`NoSuchMethodError` là một **Error** do liên kết nhị phân, khác `NoSuchMethodException` được reflection API ném. Việc catch `NoSuchMethodError` trong demo chỉ để ghi nhận xung đột; agent sản phẩm phải xử lý trạng thái lỗi rõ ràng và không giả vờ hoạt động bình thường khi library API đã không tương thích.

## 2. Phân loại dependency trước khi chọn cách đóng gói

Agent thường có ba lớp:

1. **Agent implementation:** entry point `premain`/`agentmain`, transformer, cấu hình, instrumentation orchestration.
2. **Dependency nội bộ:** bytecode library (ASM/Byte Buddy), serializer, config parser, internal logger/exporter, các utilities agent dùng.
3. **Bridge/shared API:** class/interface mà bytecode được instrument, application hoặc bootstrap-defined class cần tham chiếu trực tiếp.

Nhóm 2 thường là **ứng viên relocation**. Nhóm 3 **không thể relocate vô điều kiện**, vì hai bên phải thống nhất **binary name và class identity** nếu cần giao tiếp qua một interface, cast hoặc method descriptor.

Một BOM, Maven `dependencyManagement` hay Gradle version catalog chỉ giúp build có dependency graph kiểm soát được. Nó **không cô lập runtime namespace** giữa agent và app nếu cùng system loader. Transitive dependencies cũng có thể tạo xung đột; agent dùng lib X kéo theo Y v1, app dùng Y v2, dù cả hai không import Y trực tiếp.

### Bốn câu hỏi thiết kế

- Những class nào thực sự phải có mặt **khi agent chạy**, không chỉ tại compile time?
- Library nào nên riêng tư với agent, và API nào **bắt buộc chia sẻ**?
- Những tên class/package có được nhúng trong `META-INF/services`, JSON/XML, `Class.forName`, resource bundles hoặc reflection strings không?
- Transformed target class nằm ở system, bootstrap hay custom loader; liệu nó có resolve được helper sau khi instrumentation?

## 3. Thin JAR, fat JAR, shading, relocation và classloader isolation

| Phương án | Làm được gì | Điều còn thiếu |
|---|---|---|
| Thin agent JAR | Agent JAR chỉ có implementation, dependency ở path ngoài | Phụ thuộc runtime classpath và bản library của app |
| Fat/uber JAR | Gộp classes/resources của nhiều dependencies vào một JAR | **Không mặc nhiên đổi binary names**, vẫn có thể conflict |
| Shading + relocation | Gộp dependency rồi **chuyển package/binary names**, sửa bytecode references | Chưa chắc sửa mọi resource, reflection string, JNI hoặc helper visibility |
| Custom classloader isolation | Định nghĩa lib riêng ở loader khác | Cần xử lý parent/child delegation, class identity, target helper và JPMS |
| Bootstrap helper JAR riêng | Bridge tối thiểu cho bootstrap-defined target | Không nên bundle toàn bộ agent dependencies vào bootstrap |
| Giảm dependencies | Bớt surface conflict, size và CVEs | Không thay thế những chức năng thực sự cần |

**Fat JAR khác relocated JAR.** Nếu output JAR vẫn chứa `org/apache/commons/lang3/StringUtils.class`, một application có Commons Lang cùng FQCN vẫn có thể va chạm. Với Maven Shade relocation:

~~~text
org/apache/commons/lang3/StringUtils.class
             |
             v
demo/agent/shadow/org/apache/commons/lang3/StringUtils.class
~~~

Shader còn phải sửa các **class references** liên quan trong bytecode của agent để nó tìm tên đã relocate. **Chỉ rename JAR entry mà không rewrite references** sẽ dẫn tới lỗi class lookup/linkage mới.

Nên đặt private package dưới prefix do agent sở hữu, ví dụ `com.company.product.agent.v1.shaded.*`. Hai agent khác nhau cùng dùng prefix `shadow.*` vẫn có thể va nhau. **Không relocate `java.*` hoặc public API mà ứng dụng cần dùng chung**.

## 4. Thực hành Java 17+: hai bản cùng FQCN và hậu quả

Đây là lab **không cần Maven**, giúp nhìn thấy một class cùng tên do hai JAR mang vào JVM.

- Agent lib v1: `org.example.codec.Codec.agentOnly()`.
- App lib v2: `org.example.codec.Codec.appOnly()`.
- Hai bản đều có `owner()` để hiển thị bản đang được nạp.
- Trường hợp sửa: agent dùng class **`demo.agent.shadow.codec.Codec`** thay vì tên gốc. Đây là **mô phỏng kết quả relocation bằng source khác package**, chưa dùng plugin Shade; mục 5 mới dùng plugin thật.

### 4.1 Cấu trúc thư mục

~~~text
agent-dependency-lab/
├── bad-manifest.mf
├── good-manifest.mf
├── src/
│   ├── agent-lib/org/example/codec/Codec.java
│   ├── app-lib/org/example/codec/Codec.java
│   ├── agent/demo/agent/CollisionAgent.java
│   ├── app/demo/app/Main.java
│   ├── private-lib/demo/agent/shadow/codec/Codec.java
│   └── agent-relocated/demo/agent/PrivateAgent.java
└── out/
    ├── agent-lib/
    ├── app-lib/
    ├── agent/
    ├── app/
    ├── private-lib/
    ├── relocated-agent/
    ├── bad-agent.jar
    ├── good-agent.jar
    └── app-lib.jar
~~~

Chạy từ thư mục gốc `agent-dependency-lab`; cần JDK 17+ với `javac`, `jar` và `java`.

### 4.2 Agent lib v1

File `src/agent-lib/org/example/codec/Codec.java`:

~~~java
package org.example.codec;

public final class Codec {
    private Codec() {}

    public static String owner() { return "AGENT_V1"; }

    public static String agentOnly() { return "AGENT_OK"; }
}
~~~

### 4.3 App lib v2

File `src/app-lib/org/example/codec/Codec.java`:

~~~java
package org.example.codec;

public final class Codec {
    private Codec() {}

    public static String owner() { return "APP_V2"; }

    public static String appOnly() { return "APP_OK"; }
}
~~~

**Hai classes trùng binary name**: phải compile ở hai output dirs riêng. Không compile cả hai cùng lúc trong một invocation `javac`.

### 4.4 Agent chưa relocate

File `src/agent/demo/agent/CollisionAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import org.example.codec.Codec;

public final class CollisionAgent {
    private CollisionAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("[AGENT] libOwner=" + Codec.owner());
        try {
            System.out.println("[AGENT] agentApi=" + Codec.agentOnly());
        } catch (NoSuchMethodError e) {
            // Chỉ dành cho bài học: không abort JVM để quan sát conflict.
            System.out.println("[AGENT] agentApi=MISSING");
        }
    }
}
~~~

Agent được **biên dịch** với v1. Bytecode đòi method `Codec.agentOnly()`, nhưng runtime có thể đã định nghĩa `Codec` v2. Khi ấy JVM ném `NoSuchMethodError` vì method không tồn tại trên class đã được load.

### 4.5 Ứng dụng compile với v2

File `src/app/demo/app/Main.java`:

~~~java
package demo.app;

import org.example.codec.Codec;

public final class Main {
    public static void main(String[] args) {
        System.out.println("[APP] libOwner=" + Codec.owner());
        try {
            System.out.println("[APP] appApi=" + Codec.appOnly());
        } catch (NoSuchMethodError e) {
            System.out.println("[APP] appApi=MISSING");
        }
    }
}
~~~

### 4.6 Agent sử dụng namespace private

File `src/private-lib/demo/agent/shadow/codec/Codec.java`:

~~~java
package demo.agent.shadow.codec;

public final class Codec {
    private Codec() {}

    public static String owner() { return "AGENT_PRIVATE_V1"; }

    public static String agentOnly() { return "AGENT_OK"; }
}
~~~

File `src/agent-relocated/demo/agent/PrivateAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import demo.agent.shadow.codec.Codec;

public final class PrivateAgent {
    private PrivateAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("[AGENT] privateLib=" + Codec.owner());
        System.out.println("[AGENT] agentApi=" + Codec.agentOnly());
    }
}
~~~

Hai binary names `demo.agent.shadow.codec.Codec` và `org.example.codec.Codec` khác nhau; chúng có thể cùng tồn tại trong system loader mà không tranh tên.

### 4.7 Manifest cho hai agent

`bad-manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CollisionAgent

~~~

`good-manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PrivateAgent

~~~

Manifest phải có newline cuối cùng và dòng trống sau main attributes. Bài không cần `Agent-Class` hay retransformation capability.

### 4.8 Build macOS/Linux

~~~bash
mkdir -p out/agent-lib out/app-lib out/agent out/app out/private-lib out/relocated-agent

javac --release 17 -d out/agent-lib src/agent-lib/org/example/codec/Codec.java
javac --release 17 -cp out/agent-lib -d out/agent src/agent/demo/agent/CollisionAgent.java
javac --release 17 -d out/app-lib src/app-lib/org/example/codec/Codec.java
javac --release 17 -cp out/app-lib -d out/app src/app/demo/app/Main.java
javac --release 17 -d out/private-lib src/private-lib/demo/agent/shadow/codec/Codec.java
javac --release 17 -cp out/private-lib -d out/relocated-agent src/agent-relocated/demo/agent/PrivateAgent.java

jar --create --file out/bad-agent.jar --manifest bad-manifest.mf -C out/agent . -C out/agent-lib .
jar --create --file out/good-agent.jar --manifest good-manifest.mf -C out/relocated-agent . -C out/private-lib .
jar --create --file out/app-lib.jar -C out/app-lib .
~~~

Build Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent-lib, out/app-lib, out/agent, out/app, out/private-lib, out/relocated-agent | Out-Null

javac --release 17 -d out/agent-lib src/agent-lib/org/example/codec/Codec.java
javac --release 17 -cp out/agent-lib -d out/agent src/agent/demo/agent/CollisionAgent.java
javac --release 17 -d out/app-lib src/app-lib/org/example/codec/Codec.java
javac --release 17 -cp out/app-lib -d out/app src/app/demo/app/Main.java
javac --release 17 -d out/private-lib src/private-lib/demo/agent/shadow/codec/Codec.java
javac --release 17 -cp out/private-lib -d out/relocated-agent src/agent-relocated/demo/agent/PrivateAgent.java

jar --create --file out/bad-agent.jar --manifest bad-manifest.mf -C out/agent . -C out/agent-lib .
jar --create --file out/good-agent.jar --manifest good-manifest.mf -C out/relocated-agent . -C out/private-lib .
jar --create --file out/app-lib.jar -C out/app-lib .
~~~

Ghi nhớ: `jar -C out/agent . -C out/agent-lib .` **gộp classes**, chưa đổi package. “Bad” và “good” được đóng vào hai agent JAR độc lập. Ứng dụng ở `out/app` và thư viện v2 trong `out/app-lib.jar`.

### 4.9 Chạy ba kịch bản

**Baseline, không agent**, Bash:

~~~bash
java -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

Stdout:

~~~text
[APP] libOwner=APP_V2
[APP] appApi=APP_OK
~~~

**Có xung đột**, Bash:

~~~bash
java -javaagent:out/bad-agent.jar -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java "-javaagent:out/bad-agent.jar" -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

**Stdout được kiểm chứng trên OpenJDK 24 của lab:**

~~~text
[AGENT] libOwner=APP_V2
[AGENT] agentApi=MISSING
[APP] libOwner=APP_V2
[APP] appApi=APP_OK
~~~

Ở lần chạy này JVM định nghĩa `org.example.codec.Codec` từ version của app. Agent thiếu `agentOnly()`. Một launcher/timing khác có thể nạp v1, khi đó **app** sẽ thiếu `appOnly()`. Đây là vấn đề của **shared binary name**, không phải “app version luôn có ưu tiên cao hơn agent”.

**Sau cô lập tên lớp**, Bash:

~~~bash
java -javaagent:out/good-agent.jar -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java "-javaagent:out/good-agent.jar" -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

Stdout đã kiểm chứng:

~~~text
[AGENT] privateLib=AGENT_PRIVATE_V1
[AGENT] agentApi=AGENT_OK
[APP] libOwner=APP_V2
[APP] appApi=APP_OK
~~~

Agent có namespace riêng và app vẫn dùng v2. Sự tồn tại đồng thời này **không chứng minh tự động an toàn cho ServiceLoader, resources hay cross-loader helpers**, chỉ chứng minh không còn duplicate class name ở trường hợp này.

### 4.10 Kiểm tra JAR entries

~~~bash
jar --list --file out/bad-agent.jar
jar --list --file out/good-agent.jar
jar --list --file out/app-lib.jar
~~~

`bad-agent.jar` và `app-lib.jar` đều có `org/example/codec/Codec.class`; `good-agent.jar` chứa `demo/agent/shadow/codec/Codec.class`. Kiểm tra output JAR **sau đóng gói** thay vì chỉ kiểm tra `src`.

## 5. Thực hành Maven Shade: relocation dependency thật

Để tránh việc tự sao chép và đổi package nguồn thư viện, dùng **Apache Maven Shade Plugin**. Bài này dùng dependency thật `org.apache.commons:commons-lang3:3.14.0`, build Shade Plugin `3.6.2` rồi chạy agent JAR thành công trên OpenJDK 24.

Mục tiêu relocation:

~~~text
org/apache/commons/lang3/StringUtils.class
     -> demo/agent/shadow/org/apache/commons/lang3/StringUtils.class
~~~

Đây chỉ là lựa chọn thư viện để minh họa kỹ thuật. Một agent nhỏ không cần thêm Commons Lang nếu JDK đã có API đủ dùng.

### 5.1 Dự án

~~~text
shaded-agent/
├── pom.xml
└── src/main/java/
    ├── demo/agent/ShadedAgent.java
    └── demo/app/SimpleMain.java
~~~

`src/main/java/demo/agent/ShadedAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import org.apache.commons.lang3.StringUtils;

public final class ShadedAgent {
    private ShadedAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("[AGENT] shadedStringUtils="
                + StringUtils.isBlank("  "));
    }
}
~~~

Source **vẫn import package gốc** để compile với Maven dependency. Shade Plugin viết lại class references và class entries trong **artifact đầu ra**.

`src/main/java/demo/app/SimpleMain.java`:

~~~java
package demo.app;

public final class SimpleMain {
    public static void main(String[] args) {
        System.out.println("[APP] main");
    }
}
~~~

### 5.2 `pom.xml` đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo.agent</groupId>
  <artifactId>shaded-agent</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.14.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.2</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <relocations>
                <relocation>
                  <pattern>org.apache.commons.lang3</pattern>
                  <shadedPattern>demo.agent.shadow.org.apache.commons.lang3</shadedPattern>
                </relocation>
              </relocations>
              <filters>
                <filter>
                  <artifact>*:*</artifact>
                  <excludes>
                    <exclude>META-INF/*.SF</exclude>
                    <exclude>META-INF/*.DSA</exclude>
                    <exclude>META-INF/*.RSA</exclude>
                  </excludes>
                </filter>
              </filters>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.agent.ShadedAgent</Premain-Class>
                  </manifestEntries>
                </transformer>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Ý nghĩa:**

- `maven.compiler.release=17` kiểm soát source/API/bytecode target của **project**, nhưng vẫn phải kiểm tra bytecode của **dependencies**.
- Plugin chạy goal `shade` trong phase `package`, xây **uber JAR**.
- `relocations` chuyển Commons Lang sang namespace của agent, đồng thời sửa bytecode references được plugin hỗ trợ.
- `ManifestResourceTransformer` bảo đảm `META-INF/MANIFEST.MF` của output có `Premain-Class`.
- `ServicesResourceTransformer` merge/relocate descriptors trong `META-INF/services`, nếu có; ví dụ Commons Lang này **không nhằm kiểm chứng SPI**.
- Filter chữ ký `META-INF/*.SF`, `*.DSA`, `*.RSA` loại metadata chữ ký cũ vốn có thể không hợp lệ sau khi repackaging. Nếu cần integrity signatures phải **ký lại artifact đầu ra**, đồng thời giữ license/NOTICE.
- `createDependencyReducedPom=false` dùng cho lab. Khi publish phải tự xem POM metadata và dependency exposure.
- Không bật `minimizeJar` để tránh xóa classes được nạp qua reflection/SPI mà static analysis không thấy.

### 5.3 Build và chạy

Trong thư mục gốc `shaded-agent`, Bash:

~~~bash
mvn -B -q -DskipTests package
jar --list --file target/shaded-agent-1.0.0.jar
java -javaagent:target/shaded-agent-1.0.0.jar -cp target/shaded-agent-1.0.0.jar demo.app.SimpleMain
~~~

PowerShell:

~~~powershell
mvn -B -q -DskipTests package
jar --list --file target/shaded-agent-1.0.0.jar
java "-javaagent:target/shaded-agent-1.0.0.jar" -cp target/shaded-agent-1.0.0.jar demo.app.SimpleMain
~~~

**Stdout đã kiểm chứng:**

~~~text
[AGENT] shadedStringUtils=true
[APP] main
~~~

Trong final JAR, các entries được kiểm chứng gồm:

~~~text
META-INF/MANIFEST.MF
demo/agent/shadow/org/apache/commons/lang3/StringUtils.class
demo/agent/shadow/org/apache/commons/lang3/RandomStringUtils.class
~~~

Đây là **các dòng tiêu biểu** từ listing, không phải toàn bộ listing. Không nên còn bản class ở đường dẫn gốc `org/apache/commons/lang3/StringUtils.class` nếu relocation bao phủ đúng package. Khi agent chạy được, chứng tỏ bytecode sau shading dùng được API thư viện trong namespace mới.

**Không nên relocate entry point** `demo.agent.ShadedAgent` nếu manifest vẫn trỏ vào tên gốc. Nếu agent cần public classes dùng chung với app, xác định rõ class identity trước khi quyết định đưa chúng vào `relocations`.

### 5.4 Nếu dùng Gradle Shadow

GradleUp Shadow hỗ trợ tương tự qua task `shadowJar` và `relocate`. Mảnh **Kotlin DSL minh họa** khi plugin Shadow đã được cấu hình đúng phiên bản:

~~~kotlin
tasks.named<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar>("shadowJar") {
    relocate(
        "org.apache.commons.lang3",
        "demo.agent.shadow.org.apache.commons.lang3"
    )
    manifest {
        attributes["Premain-Class"] = "demo.agent.ShadedAgent"
    }
}
~~~

Snippet này **chưa được chạy thử trong bài**. Các bản hiện đại dùng plugin ID `com.gradleup.shadow`; cần khai `plugins`, dependencies, Java toolchain và kiểm tra API/import task type đúng phiên bản Shadow. Đừng coi một mảnh script này là toàn bộ build file. Tài liệu chính thức nêu thêm tùy chọn rewrite string constants; hãy đánh giá cẩn thận khi library dùng reflection.

## 6. Những điểm Shade có thể bỏ sót

Đổi class binary names không đồng nghĩa mọi metadata đều được cập nhật.

### `META-INF/services` và `ServiceLoader`

Một Java SPI có thể có resource:

~~~text
META-INF/services/org.example.spi.CodecProvider
  org.example.codec.impl.DefaultCodecProvider
~~~

Nếu provider class được relocate mà file descriptor giữ tên cũ, `ServiceLoader.load(...)` có thể không tìm được implementation hoặc ném `ServiceConfigurationError`. `ServicesResourceTransformer` của Maven Shade hỗ trợ merge và đổi tên service/provider descriptors. **Nhưng** cần test đúng SPI trên **final shaded JAR**, vì một framework có custom metadata riêng không nhất thiết dùng `META-INF/services`.

Với SPI interface dùng chung với app, cân nhắc **giữ nguyên interface public** và chỉ relocate implementation phù hợp; nếu cả hai phía sử dụng hai interfaces bị relocate khác nhau thì không thể cast hoặc triển khai đúng shared API.

### Reflection và strings

Ví dụ:

~~~java
Class.forName("org.example.codec.impl.DefaultCodecProvider");
~~~

Một số shading tools có thể rewrite string constants, nhưng không bảo đảm rewrite mọi value sinh động từ env/config, JSON/XML, URLs, hoặc chuỗi ghép lúc chạy. Sau relocation, kiểm tra:

- `Class.forName(...)` và `MethodHandles` dùng tên class cố định hoặc động.
- Resource bundles, `getResource(...)`, `ServiceLoader`, custom plugins.
- Config YAML/JSON/XML chứa FQCN; registry của serializers/deserializers.
- Java serialization có thể mang tên class, và data compatibility cần xử lý riêng.
- Framework metadata như Log4j plugin cache, Spring factories, config merging.

Không chỉ search code imports; hãy thực hiện **integration test trên JAR cuối cùng** với các nhánh khởi tạo hiếm.

### Multi-release JAR và module descriptor

Một dependency có thể có `META-INF/versions/9/...`, `META-INF/versions/17/...` hoặc class files phiên bản JDK cao hơn. Shading phải bảo toàn class structure/version-specific variants và manifest metadata đúng. Đồng thời, `module-info.class` hoặc `Automatic-Module-Name` có thể không còn phản ánh artifact mới sau khi merge/rewrite.

Agent JAR chạy bằng `-javaagent` thông thường nằm trong **unnamed module của system loader**, nhưng target application có thể dùng **named modules**. Relocation không tự open/exports packages của named modules, không tạo thêm class loader, và không thay class file target version của dependency. Build `--release 17` với dependency cần Java 21 vẫn có thể gặp `UnsupportedClassVersionError` trên runtime Java 17.

### JNI/native assets và signed JAR

Nếu thư viện có `.dll`, `.so`, `.dylib` hoặc JNI symbol names gắn với package, đổi Java class names không tự đổi native library/symbols. Phải test native linkage riêng.

Nếu gộp signed JAR, old `META-INF/*.SF`/`*.RSA`/`*.DSA` có thể không còn hợp lệ sau khi bytes thay đổi. Ví dụ Maven filters loại signature metadata cũ là **kỹ thuật packaging**, không phải thay thế cho supply-chain verification. Bảo toàn licenses/NOTICE, kiểm tra checksum/signatures và ký lại output khi quy trình yêu cầu.

### `minimizeJar` và reflective classes

Minimizer có thể loại bỏ classes mà static analysis không thấy, trong khi agent load qua `ServiceLoader`, reflection, generated bytecode hoặc plugin discovery.

~~~text
Lúc build: Class không có direct reference -> bị xóa
Lúc chạy:  Class.forName(providerFromConfig) -> ClassNotFoundException
~~~

Không bật `minimizeJar` theo phản xạ. Chỉ tối ưu sau khi có test đầy đủ các feature paths, SPI và dynamic class loading; nếu cần thì giữ các packages/classes tương ứng bằng explicit filters.

## 7. Relocation không thay thế classloader/helper design

Transformer có thể nhận class do **bootstrap**, **system** hoặc **custom loader** định nghĩa. Tham số `loader` của callback mô tả **target class loader**, không mặc định bằng loader của Java agent.

~~~text
Java agent implementation (system loader)
   ├── transformer + shaded ASM/codec (system)
   │
   ├── instrument application target (system)
   ├── instrument plugin target (custom loader)
   └── instrument java.base target (bootstrap loader)
                      |
           code injected gọi helper system-only?
                      |
           bootstrap không tìm ngược xuống system
                      |
              NoClassDefFoundError
~~~

Dù helper đã relocated thành `demo.agent.shadow.Helper`, bootstrap loader vẫn **không tự nhìn thấy** class chỉ được system loader nạp. Cần thiết kế bridge:

~~~text
agent-implementation.jar          system loader
  premain/agentmain
  transformer, shaded internals
  exporter/configuration

bootstrap-bridge.jar              bootstrap loader search
  API rất nhỏ, package độc nhất
  không link ngược implementation chỉ có ở system
~~~

Java Instrumentation có `appendToBootstrapClassLoaderSearch(new JarFile(...))` và `Boot-Class-Path`. Không đưa nguyên fat agent JAR vào bootstrap search chỉ để “dễ nhìn thấy” vì có thể làm ô nhiễm core lookup namespace. Bootstrap helper nên tối thiểu và chỉ link với classes bootstrap-resolvable.

Với custom/child-first classloaders, loader của app có thể có class naming/visibility khác. Nếu cần dùng helper được instrument, hãy test ngay trên loader của target; không dùng `Class.forName(targetName)` bừa trong transformer vì có thể recursive load hoặc gây `LinkageError`.

### Module access độc lập với relocation

Một class được system loader định nghĩa thường ở unnamed module của loader, nhưng class của named module cũng có thể được system loader định nghĩa. **Loader visibility, module readability, exports và opens là các điều kiện khác nhau**. Thay package name bằng shading không tự cấp quyền deep reflection vào private member của named module. Nếu cần, dùng cơ chế JPMS hợp lệ và giới hạn quyền.

## 8. Chẩn đoán đúng class đã được JVM load

### In runtime identity và origin

Mảnh code minh họa trong agent/app đã có reference tới class:

~~~java
Class<?> type = org.example.codec.Codec.class;
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
var pd = type.getProtectionDomain();
var origin = (pd == null || pd.getCodeSource() == null)
        ? null : pd.getCodeSource().getLocation();
System.out.println("origin=" + origin);
~~~

`CodeSource` có thể `null` với bootstrap hoặc custom loader; không dùng riêng nó làm bằng chứng tuyệt đối. Nhưng nó hữu ích khi tìm JAR đã định nghĩa một class cụ thể.

### JVM class-loading log

HotSpot hỗ trợ:

~~~bash
java -Xlog:class+load=info -javaagent:out/bad-agent.jar -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java "-Xlog:class+load=info" "-javaagent:out/bad-agent.jar" -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

Output rất dài; tìm `org.example.codec.Codec` và đường `source: ...` để xem runtime load bản nào. Không bật logging cấp này vô hạn trong production nếu chưa tính overhead/log size.

### Maven dependency tree và JAR listing

~~~bash
mvn dependency:tree
jar --list --file target/shaded-agent-1.0.0.jar
~~~

`dependency:tree` cho biết graph được Maven resolve trong **project đang build**, không chứng minh JVM đã load class từ đâu khi ghép cùng application hoặc các agents khác. `jar --list` xác minh artifact thực, nhưng chỉ có class trong JAR không có nghĩa nó đã được JVM dùng. Cần kết hợp compile graph, artifact listing và runtime class-loading evidence.

### Quy trình điều tra `NoSuchMethodError`

1. Đọc đầy đủ **owner class, method name và descriptor** ở stacktrace.
2. Xác minh classloader, module và source của owner class **ở runtime**.
3. So API compile và API runtime qua `javap -public -classpath ... <binaryName>` (thay tên class/path thật).
4. Xem direct + transitive dependencies của agent, app, nhiều agents.
5. Chọn dependency nào phải relocate, dependency nào là shared public API.
6. Build final shaded agent, test startup, classloading, reflection, SPI và methods cần dùng.
7. Nếu lỗi chuyển sang `NoClassDefFoundError` sau relocation, kiểm tra helper loader và resource path; không chỉ đổi prefix một lần nữa.

## 9. Nhiều agents và các giới hạn thực tế

JVM có thể chạy:

~~~bash
java -javaagent:agentA.jar -javaagent:agentB.jar -cp app.jar demo.app.Main
~~~

Các `premain` được gọi theo thứ tự xuất hiện của `-javaagent`, nhưng class loading/transformer ordering phụ thuộc đăng ký, capability và nhóm transformers. Thứ tự trên command line **không phải một chiến lược version pin** cho các thư viện cùng tên trong system loader.

Nếu agent A/B cùng bundle `org.example.codec.Codec` từ hai bản, chúng có thể conflict. Nếu cùng relocate vào **một prefix chung** như `shaded.codec`, chúng lại conflict dưới tên mới. Dùng prefix riêng có ownership:

~~~text
com.company.agentA.shaded.codec.Codec
com.vendor.agentB.shaded.codec.Codec
~~~

Nếu agents cần **cùng public tracing API**, hãy thống nhất contract và class identity thay vì relocate API ở hai phía rồi mong cast/interop tự hoạt động. Đừng để transformed app bytecode gọi implementation private dependency từ một agent thứ ba mà không có stability guarantee.

Kiểm thử tối thiểu: agent A, agent B, A+B và B+A khi có tương tác, app dùng dependency v1/v2, app classpath/named modules, target bootstrap/custom loader nếu có. Bật diagnostics có kiểm soát để so class origins và classfile transformations.

## 10. Bảng lỗi phổ biến

| Thiết kế/niềm tin sai | Hậu quả | Cách xử lý |
|---|---|---|
| Fat JAR đồng nghĩa isolation | Trùng classes cùng FQCN | Shade + relocate dependency nội bộ |
| App/agent luôn ưu tiên một bản xác định | Lỗi chỉ xảy ra theo môi trường | Không dựa vào load order |
| Chỉ cần BOM version pin | Runtime system loader vẫn chung namespace | Test artifact với application dependency khác |
| Relocate mọi public API | Phá class identity và interoperability | Giữ boundary API nhất quán |
| Maven Shade tự sửa mọi SPI/XML | Provider/config chưa merge | Resource transformers + runtime SPI tests |
| ServiceLoader descriptors vẫn dùng FQCN cũ | `ServiceConfigurationError` | Rewrite descriptors, test final JAR |
| Reflection bằng class strings luôn được rewrite | Config động không đi qua shader | Integration tests + explicit mappings |
| Bật `minimizeJar` ngay | Xóa các provider dùng bằng reflection | Disable/allowlist trước khi có coverage |
| Đưa toàn agent JAR lên bootstrap | Bẩn loader namespace, link ngược bị lỗi | Bootstrap helper tối thiểu |
| Shading Java code tự sửa native JNI | JNI exports vẫn theo ký hiệu gốc | Native linkage tests riêng |
| Signed JAR metadata gốc vẫn hợp lệ | Verification/security errors | Filter cũ, giữ licenses và ký lại khi cần |
| Test classpath IDE là đủ | Final uber JAR khác nhiều so với dev | Smoke test `-javaagent:final.jar` |
| Có đúng class trong JAR tức JVM đã dùng nó | Runtime load source có thể khác | Class-loader logs/CodeSource |
| Classfile version phụ thuộc project `--release 17` | Transitive lib có thể cần Java mới hơn | Kiểm tra compatibility mọi classes |

## 11. Checklist phát hành

- [ ] Liệt kê dependencies trực tiếp, transitive, licenses, versions và CVE exposure.
- [ ] Phân loại internal implementation vs shared API/bridge.
- [ ] Relocate các internal packages có khả năng trùng, dùng prefix riêng với ownership rõ.
- [ ] Không relocate JDK packages hay vô tình đổi shared API binary identity.
- [ ] Kiểm tra đúng `Premain-Class`/`Agent-Class`, module/class loader placement và manifest.
- [ ] Kiểm tra JAR entries sau shading: classes gốc không còn ngoài ý muốn, classes mới có mặt.
- [ ] Test SPI/services, reflection, resource bundles, generated code, serialization và JNI nếu dùng.
- [ ] Test multi-release JAR và classfile version trên JDK thấp nhất hỗ trợ.
- [ ] Quản lý signatures/NOTICE/license và reproducible build/artifact hash.
- [ ] Tránh minimize khi chưa có integration coverage đủ cho reflective providers.
- [ ] Smoke-test final JAR với app v1/v2, nhiều agents, named/custom/bootstrap loaders khi liên quan.
- [ ] Ghi diagnostics class origin/loader và kết quả tự kiểm tra startup có giới hạn.
- [ ] Không swallow linkage errors rồi cho rằng agent hoạt động thành công.
- [ ] Đo overhead/GC/memory sau khi thêm shaded dependencies.
- [ ] Có chế độ tắt/fallback an toàn và rollback artifact khi rollout gặp lỗi.

## 12. Câu hỏi tự kiểm tra

1. **Class identity dựa trên gì?** Binary name và defining class loader.
2. **Gộp dependency vào agent JAR có cô lập namespace không?** Không, nếu class names không được đổi.
3. **Tại sao agent compile v1 vẫn thấy v2?** Cùng runtime loader có thể đã định nghĩa một class cùng FQCN từ app.
4. **`NoSuchMethodError` khác `NoSuchMethodException`?** Runtime linkage error vs reflective lookup exception.
5. **Relocation khác rename JAR entry thế nào?** Shader phải sửa cả bytecode references/metadata phù hợp.
6. **Nên relocate public API mà app cần cast không?** Thường không, vì phá class identity.
7. **SPI cần kiểm tra gì?** `META-INF/services` và provider names sau merge/relocate.
8. **Maven Shade `ManifestResourceTransformer` dùng để làm gì?** Ghi manifest entry như `Premain-Class` trong final JAR.
9. **Vì sao `minimizeJar` rủi ro?** Reflection/providers có thể không xuất hiện trong static reference graph.
10. **Relocation giải quyết `NoClassDefFoundError` của bootstrap target gọi system helper không?** Không; cần helper loader placement.
11. **Hai agents cùng relocate vào prefix giống nhau có cô lập không?** Không; vẫn tên class trùng.
12. **Dependency tree chứng minh runtime class source?** Không; cần xem loader/CodeSource/class-load logs.
13. **Shading có tự tương thích Java 17 nếu dependency cần JDK 21?** Không.
14. **Maven Shade plugin được test thật trong bài không?** Có, với Commons Lang 3.14.0, output JAR chạy được.
15. **Cách xác định kết quả cô lập an toàn hơn chỉ nhìn build success?** Inspect artifact, chạy trên final jar với app có dependency version khác và test SPI/reflection.

## 13. Tài liệu chính thức

- [Java SE 21 — Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent classes, system class loader, unnamed module, manifest.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): classloader search và transform APIs.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, system loader, class identity.
- [Maven Shade — Usage](https://maven.apache.org/plugins/maven-shade-plugin/usage.html): uber JAR và plugin lifecycle.
- [Maven Shade — Relocating Classes](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html): rewrite classes/package names.
- [Maven Shade — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html): manifest và services merging.
- [Maven Shade — Selecting Contents](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html): filters, signature entries và minimize.
- [GradleUp Shadow — Relocation](https://gradleup.com/shadow/configuration/relocation/): Gradle namespace rewriting.
- [Java SE 21 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): SPI resource contract và errors.
- [Java SE 21 — `NoSuchMethodError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NoSuchMethodError.html): binary linkage errors.
