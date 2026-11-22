# `appendToBootstrapClassLoaderSearch` và `Boot-Class-Path`: đưa helper vào bootstrap class loader

Một Java agent thường phải chèn lời gọi tới **helper class** để đo thời gian, tạo trace, ghi metric hoặc chuyển sự kiện ra bộ thu thập. Nếu code được instrument thuộc lớp nền tảng của JDK, nó có thể được định nghĩa bởi **bootstrap class loader**, trong khi class của agent thường được **system class loader** định nghĩa. Helper chỉ có trong agent JAR chưa chắc được class đích nhìn thấy.

Hai công cụ của `java.lang.instrument` giải quyết trực tiếp vấn đề **bootstrap class lookup**:

1. **`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`**: agent chủ động thêm một JAR vào nơi bootstrap loader tìm class.
2. **Manifest `Boot-Class-Path`**: agent khai báo trước danh sách đường dẫn bổ sung trong main manifest của JAR, để JVM xử lý lúc agent bắt đầu.

Cả hai chỉ bổ sung **nơi tìm class**. Chúng **không tự instrument class**, không tự load tất cả class trong JAR, không thay một `Class<?>` đã được định nghĩa và không tự mở mọi quyền của Java Platform Module System (JPMS).

Bài này thuộc phần **Class loader và helper** của Java Advance — instrumentation. Mục tiêu là hiểu sự khác biệt giữa hai cơ chế, thiết kế bootstrap helper an toàn và tự chạy một ví dụ Java 17+ chứng minh **helper thật sự do bootstrap loader định nghĩa**.

## 1. Hiểu loader identity trước khi thêm helper

Trong Java, một class không chỉ được phân biệt bằng tên nhị phân: **defining class loader** cũng là thành phần quyết định runtime identity. Hai class có cùng tên nhưng được định nghĩa bởi loader khác nhau có thể là hai runtime types khác nhau.

Mô hình đơn giản:

```text
                  JVM
                   |
         +---------+----------+
         |                    |
  Bootstrap loader       System loader
         |                    |
  java.lang.String        Agent entry class
  java.base classes       Application trên -cp
  bootstrap helper        (tùy cách chạy)
         |                    |
         +---- liên kết -------+
               theo JVM rules
```

Java API thường biểu diễn bootstrap loader bằng **`null`**. Ví dụ:

```java
ClassLoader loader = someClass.getClassLoader();
System.out.println(loader == null ? "bootstrap" : loader.toString());
```

Đây là **trích đoạn bên trong method** có biến `someClass`. Kết quả `null` của `Class.getClassLoader()` nghĩa là class được định nghĩa bởi bootstrap loader; nó không có nghĩa class “không có loader”.

| Class | Defining loader thường gặp | Ghi chú |
|---|---|---|
| `java.lang.String` | Bootstrap | Class nền tảng |
| Agent class được chỉ định bởi `Premain-Class` | System | Agent JAR có loader/module riêng với bootstrap helper |
| App class trên `-cp` | System/application | Tùy môi trường và custom loader |
| Helper trong JAR do bootstrap tìm thấy | Bootstrap | Chỉ khi class thật sự được bootstrap định nghĩa |
| Class thuộc plugin/custom loader | Custom loader | Phải xem delegation và module access thực tế |

Một class trong JAR đã append **chưa chắc được load**. JVM chỉ định nghĩa class khi nó thật sự cần tìm class đó và đáp ứng điều kiện nạp/liên kết.

### 1.1. Vì sao một agent cần helper do bootstrap định nghĩa?

Giả sử transformer chèn bytecode:

```text
invokestatic com/example/agentbootstrap/BootstrapMarker.message:()Ljava/lang/String;
```

Đây là **một instruction minh họa**, không phải Java source độc lập. Khi method đích chạy, JVM phải resolve symbolic reference tới `BootstrapMarker`. Nếu class đích do bootstrap loader định nghĩa, nó không mặc nhiên tìm xuống các class của agent do system loader định nghĩa.

Đưa một **helper nhỏ** vào bootstrap search path có thể giúp nhiều class thuộc những loader ủy quyền lên bootstrap tìm thấy cùng helper. Nhưng phương thức này không đảm bảo mọi named module hoặc custom loader đều đọc/truy cập được helper; phần JPMS ở cuối bài giải thích thêm.

## 2. API `appendToBootstrapClassLoaderSearch(JarFile)` hoạt động ra sao?

Chữ ký:

```java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile)
```

Đây là instance method của `java.lang.instrument.Instrumentation`. Bạn nhận đối tượng `Instrumentation` từ JVM qua một điểm vào như:

```java
public static void premain(String agentArgs, Instrumentation inst)
```

hoặc:

```java
public static void agentmain(String agentArgs, Instrumentation inst)
```

Hai chữ ký ở trên là **minh họa điểm vào của agent**, chưa phải chương trình độc lập.

Một mẫu gọi đúng:

```java
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

// Đặt trong một agent class.
private static JarFile bootstrapJar;

public static void premain(String agentArgs, Instrumentation inst)
        throws Exception {
    Path helper = Path.of("dist", "boot-helper.jar")
            .toAbsolutePath().normalize();
    bootstrapJar = new JarFile(helper.toFile());
    inst.appendToBootstrapClassLoaderSearch(bootstrapJar);
}
```

Các quy tắc:

- Tham số phải là **`JarFile`**, không phải `String`, `Path`, URL hay thư mục.
- JAR cần chứa các class/resource mà **bootstrap loader** được phép tìm để phục vụ instrumentation.
- Khi cơ chế tìm kiếm có sẵn của bootstrap loader không tìm thấy class, nó mới xét các JAR đã được append.
- Có thể gọi nhiều lần: JVM tìm những JAR bổ sung **theo thứ tự các lần gọi append**.
- Không được suy ra rằng một JAR đến sau sẽ **ghi đè** một class đã được bootstrap định nghĩa hoặc đã tìm được trước đó.
- `jarfile == null` khiến method ném `NullPointerException`.
- Ví dụ giữ `JarFile` trong static field để không đóng file ngay sau khi append. Cần quản lý resource phù hợp với vòng đời agent/JVM thực tế.

Việc gọi `new JarFile(...)` có thể ném `IOException` nếu file không tồn tại, không có quyền đọc hoặc không phải JAR hợp lệ. Đây là lỗi **của agent code**, không phải lỗi tự động được bỏ qua như một số manifest path sai.

### 2.1. Nên append trước khi class đích cần helper

JVM có hợp đồng về **failed symbolic reference resolution**: một symbolic reference đã được resolve thất bại có thể tiếp tục thất bại theo cùng quy tắc nếu dùng lại, dù sau đó search path đã thay đổi.

```text
Target class A đã được nạp
         |
         v
A tham chiếu bootstrap helper H
         |
         v
Resolve H thất bại
         |
         v
Agent append JAR có H
         |
         v
Không thể mặc định kết luận
cùng symbolic reference trong A được phục hồi
```

Vì vậy nên **cấu hình helper sớm**, trước khi instrumented code thực thi lần đầu. Khi attach động vào JVM đang chạy, đặc biệt cẩn thận với class đã nạp và các reference đã thất bại trước đó.

### 2.2. Bootstrap append không phải cách thay class JDK có sẵn

Nếu bootstrap loader vốn đã định nghĩa hoặc tìm được một class từ runtime image, append JAR mới **không thay định nghĩa class đó**. Muốn chỉnh method bytecode của class đã nạp phải xét `ClassFileTransformer`, `retransformClasses`/`redefineClasses` và các giới hạn riêng.

## 3. Manifest `Boot-Class-Path`: khai báo bootstrap JAR khi khởi động agent

Một agent JAR có thể chứa main manifest như sau:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.BootstrapAgent
Boot-Class-Path: boot-helper.jar

```

Từng header có trách nhiệm khác nhau:

- `Premain-Class`: tên nhị phân của **agent class** có `premain(...)`, cần khi dùng `-javaagent`.
- `Boot-Class-Path`: **danh sách nơi bootstrap loader tìm helper classes**, optional.
- `Agent-Class`: nếu muốn hỗ trợ dynamic attach, nó chọn class có `agentmain(...)`; không thay thế `Boot-Class-Path`.
- `Class-Path`: header theo JAR File Specification, **không đồng nghĩa** `Boot-Class-Path`.

Điểm quan trọng nhất: **relative `Boot-Class-Path` được resolve tương đối với absolute path của agent JAR**, không phải thư mục hiện hành của lệnh `java`.

Ví dụ:

```text
project/
└── dist/
    ├── agent-manifest.jar
    └── boot-helper.jar
```

Trong manifest của `dist/agent-manifest.jar`:

```text
Boot-Class-Path: boot-helper.jar
```

thì JVM sử dụng `dist/boot-helper.jar` khi giải đường dẫn tương đối, kể cả khi tiến trình khởi động ở nơi khác.

### 3.1. Đúng cú pháp đường dẫn

Theo đặc tả package `java.lang.instrument` Java 17:

- Danh sách đường dẫn có thể gồm **nhiều entry**, tách bởi **một hoặc nhiều dấu cách**.
- Mỗi path có cú pháp **path component của hierarchical URI**.
- Path bắt đầu bằng `/` được coi là absolute; trường hợp khác là relative theo agent JAR.
- Những đường dẫn được tìm **theo thứ tự được liệt kê**.
- Các đường dẫn malformed hoặc không tồn tại có thể bị **bỏ qua**.
- Nếu agent được khởi động **sau khi JVM đã chạy**, path **không đại diện cho JAR file** sẽ bị bỏ qua.
- `Boot-Class-Path` là optional; thiếu header này không khiến một agent hợp lệ tự động thất bại.

Ví dụ hai helper:

```text
Boot-Class-Path: boot-helper.jar monitoring-helper.jar
```

Để tránh nhầm dấu cách dùng làm separator và cú pháp URI, bài thực hành đặt tên file đơn giản, không có khoảng trắng. Nếu cần đường dẫn OS phức tạp, hãy xác minh cách encode tương thích JDK và kiểm tra manifest thực tế, không chỉ ghép chuỗi theo trực giác.

### 3.2. Vì sao lỗi manifest thường khó phát hiện?

Giả sử manifest có:

```text
Boot-Class-Path: boot-hepler.jar
```

trong khi JAR thực tế tên `boot-helper.jar`. Vì path không tồn tại có thể bị bỏ qua, agent vẫn có thể bắt đầu và chỉ thất bại khi `Class.forName` hay bytecode đích thật sự cần helper.

Do đó phải kiểm tra **cả hai**: header ở manifest cuối cùng bên trong agent JAR và file helper ở nơi JVM sẽ tìm.

## 4. So sánh API và manifest

| Khía cạnh | `appendToBootstrapClassLoaderSearch` | `Boot-Class-Path` |
|---|---|---|
| Nơi cấu hình | Java code của agent | Main manifest của agent JAR |
| Input | Một `JarFile` | Một hay nhiều path dạng URI path |
| Thời điểm | Khi agent **gọi method** | Khi JVM xử lý manifest lúc khởi động agent |
| Đường dẫn relative | Do code chọn cách giải quyết (`Path`, working dir...) | Relative theo **agent JAR** |
| Nhiều JAR | Gọi nhiều lần; theo thứ tự gọi | Danh sách path; theo thứ tự liệt kê |
| File không tồn tại | `JarFile` có thể ném exception | Path có thể bị bỏ qua |
| Đòi `Instrumentation` trong code? | Có | Không bắt buộc chỉ để khai báo |
| Dùng trong `agentmain`? | Có, nếu runtime cho phép dynamic agent | Có, với giới hạn entry không phải JAR ở thời điểm attach |
| Tự load mọi class? | Không | Không |
| Tự instrument class? | Không | Không |
| Thay class đã load? | Không | Không |

Nên chọn **manifest** nếu helper JAR được đóng gói cố định bên cạnh agent và muốn ít code. Nên chọn **API** nếu đường dẫn helper do cấu hình lúc chạy quyết định. Chỉ đưa helper vào bootstrap khi **loader visibility thực sự yêu cầu**, tránh sử dụng như một “classpath toàn năng”.

## 5. Ví dụ Java 17+ hoàn chỉnh: cùng một helper, hai cách thêm vào bootstrap

Ví dụ có ba nhóm class:

- Một helper được đóng gói **riêng** trong `boot-helper.jar`.
- Một agent có hai mode `api` và `manifest`.
- Một application gọi trực tiếp method của helper.

Điểm then chốt: khi **chạy**, `-cp` của application chỉ gồm `out/app`, **không** có helper JAR. Bootstrap helper trở nên khả dụng nhờ agent. Ví dụ đã được chạy trên **OpenJDK 21**, biên dịch bằng `javac --release 17`.

### 5.1. Cấu trúc thư mục

```text
bootstrap-helper-demo/
├── src/
│   ├── helper/com/example/agentbootstrap/BootstrapMarker.java
│   ├── agent/com/example/agent/BootstrapAgent.java
│   └── app/demo/App.java
├── manifests/
│   ├── api.mf
│   └── manifest.mf
├── out/             (được tạo khi biên dịch)
│   ├── helper/
│   ├── agent/
│   └── app/
└── dist/            (ba JAR được tạo)
    ├── boot-helper.jar
    ├── agent-api.jar
    └── agent-manifest.jar
```

Tạo các source file và hai manifest đúng theo đường dẫn trên. Trong ví dụ, tên package `com.example.agentbootstrap` là namespace helper riêng, không trùng package ứng dụng hay JDK.

### 5.2. `src/helper/com/example/agentbootstrap/BootstrapMarker.java`

```java
package com.example.agentbootstrap;

public final class BootstrapMarker {
    private BootstrapMarker() {}

    public static String message() {
        return "bootstrap-ok";
    }
}
```

Helper rất nhỏ: chỉ gọi API từ `java.lang` (bootstrap có thể thấy). Nó **không import** agent class hoặc application class. Đây là nguyên tắc quan trọng: một bootstrap-defined helper không được giả định có thể liên kết tùy ý tới class do system/custom loader định nghĩa.

### 5.3. `src/agent/com/example/agent/BootstrapAgent.java`

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class BootstrapAgent {
    private static JarFile bootstrapJar;

    private BootstrapAgent() {}

    public static void premain(String agentArgs, Instrumentation inst)
            throws Exception {
        String mode;

        if (agentArgs != null && agentArgs.startsWith("api=")) {
            mode = "api";

            Path jarPath = Path.of(agentArgs.substring(4))
                    .toAbsolutePath()
                    .normalize();
            bootstrapJar = new JarFile(jarPath.toFile());

            // API mode: mở rộng bootstrap search path.
            inst.appendToBootstrapClassLoaderSearch(bootstrapJar);

        } else if ("manifest".equals(agentArgs)) {
            mode = "manifest";

            // JVM đã xử lý Boot-Class-Path trong manifest.
            // Không gọi append tại đây.
        } else {
            throw new IllegalArgumentException(
                    "Expected api=<jar> or manifest");
        }

        // loader null là yêu cầu bootstrap loader.
        Class<?> marker = Class.forName(
                "com.example.agentbootstrap.BootstrapMarker",
                true,
                null);

        Object response = marker.getMethod("message").invoke(null);

        System.out.println("[agent] mode=" + mode);
        System.out.println("[agent] loader=" +
                (marker.getClassLoader() == null ? "bootstrap" : "other"));
        System.out.println("[agent] message=" + response);
    }
}
```

Cơ chế code:

1. JVM gọi `premain` trước application `main`.
2. Nếu `agentArgs` bắt đầu bằng `api=`, agent đọc phần đường dẫn phía sau, dùng `Path` đổi thành absolute path, mở JAR và gọi `appendToBootstrapClassLoaderSearch`.
3. Nếu `agentArgs == "manifest"`, agent không mở helper JAR bằng API; bootstrap search path được cấu hình qua manifest.
4. Sau khi cấu hình, `Class.forName("...", true, null)` **yêu cầu bootstrap loader** load helper.
5. `marker.getClassLoader() == null` chứng minh class đã được định nghĩa bởi bootstrap.
6. Reflection gọi `message()` để kiểm tra helper chạy thật, không chỉ “có file trong JAR”.
7. Trong nhánh API, giữ `JarFile` trong static field, không đóng ngay sau khi append.
8. Không có `ClassFileTransformer` trong ví dụ vì bài đang kiểm tra **lookup/linkage của helper**, không phải thao tác viết lại bytecode.

Dùng reflection ở đây còn giúp tránh để agent vô tình thực hiện một tham chiếu liên kết tới helper **trước** lúc gọi append, một điều có thể làm bài kiểm thử khó hiểu khi kiểm tra failed resolution.

### 5.4. `src/app/demo/App.java`

```java
package demo;

import com.example.agentbootstrap.BootstrapMarker;

public final class App {
    private App() {}

    public static void main(String[] args) {
        System.out.println("[app] helper=" + BootstrapMarker.message());
    }
}
```

Ứng dụng **import helper tại compile time** nhưng sẽ **không** có helper trên **runtime application classpath**. Bootstrap loader tìm helper từ agent bootstrap path; application loader có thể ủy quyền lookup cho bootstrap.

Nếu thử chạy app với `-cp out/app` **không có agent**, cú pháp source vẫn hợp lệ nhưng helper không có ở runtime và có thể xảy ra `NoClassDefFoundError`. Đó là lý do bài thực hành phải có một trong hai agent.

### 5.5. Hai manifest

`manifests/api.mf`:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.BootstrapAgent

```

`manifests/manifest.mf`:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.BootstrapAgent
Boot-Class-Path: boot-helper.jar

```

Dòng trống cuối manifest kết thúc main section. Tên `Premain-Class` là **binary name** của agent class. Trong manifest mode, `boot-helper.jar` được tìm tương đối với vị trí `agent-manifest.jar`.

### 5.6. Biên dịch và tạo JAR

Mở terminal tại `bootstrap-helper-demo`, sử dụng JDK 17+:

```bash
mkdir out
mkdir out/helper
mkdir out/agent
mkdir out/app
mkdir dist
```

Thư mục chỉ cần được tạo một lần. Sau đó:

```bash
javac --release 17 -encoding UTF-8 -d out/helper src/helper/com/example/agentbootstrap/BootstrapMarker.java

javac --release 17 -encoding UTF-8 -d out/agent src/agent/com/example/agent/BootstrapAgent.java

javac --release 17 -encoding UTF-8 -cp out/helper -d out/app src/app/demo/App.java
```

Lệnh thứ ba cần `-cp out/helper` **để biên dịch App** vì App import `BootstrapMarker`. **Đừng nhầm** compiler classpath này với classpath chạy ứng dụng.

Đóng ba JAR:

```bash
jar --create --file dist/boot-helper.jar -C out/helper .

jar --create --file dist/agent-api.jar --manifest manifests/api.mf -C out/agent .

jar --create --file dist/agent-manifest.jar --manifest manifests/manifest.mf -C out/agent .
```

Mỗi `-C dir .` đóng nội dung của `dir` theo đúng cấu trúc package tại gốc JAR.

Kiểm tra:

```bash
jar --list --file dist/boot-helper.jar
jar --list --file dist/agent-api.jar
jar --list --file dist/agent-manifest.jar
```

Bạn cần thấy:

```text
boot-helper.jar:
  com/example/agentbootstrap/BootstrapMarker.class

agent-api.jar / agent-manifest.jar:
  META-INF/MANIFEST.MF
  com/example/agent/BootstrapAgent.class
```

Danh sách trên là **trích lược các entry cần kiểm tra**, không phải toàn bộ output của `jar --list` (archive còn có các mục thư mục).

### 5.7. Chạy mode A: gọi API append từ `premain`

```bash
java -javaagent:dist/agent-api.jar=api=dist/boot-helper.jar -cp out/app demo.App
```

JVM đưa nguyên chuỗi `api=dist/boot-helper.jar` vào `agentArgs` của `premain`. Agent parse theo tiền tố `api=`, mở helper JAR và append trước khi nạp helper.

**Stdout của chương trình, không tính diagnostic của JVM trên stderr:**

```text
[agent] mode=api
[agent] loader=bootstrap
[agent] message=bootstrap-ok
[app] helper=bootstrap-ok
```

Đã kiểm tra chạy được trên OpenJDK 21 với bytecode biên dịch theo Java 17.

### 5.8. Chạy mode B: dùng `Boot-Class-Path` trong manifest

```bash
java -javaagent:dist/agent-manifest.jar=manifest -cp out/app demo.App
```

**Stdout:**

```text
[agent] mode=manifest
[agent] loader=bootstrap
[agent] message=bootstrap-ok
[app] helper=bootstrap-ok
```

Agent **không** gọi `appendToBootstrapClassLoaderSearch` trong nhánh này. JVM đọc `Boot-Class-Path: boot-helper.jar` từ manifest và bổ sung nơi tìm helper.

### 5.9. Tại sao hai kết quả trùng nhau?

| Điều cần chứng minh | API mode | Manifest mode |
|---|---|---|
| Helper nằm trên runtime `-cp`? | Không | Không |
| Cơ chế đưa helper vào bootstrap search | Gọi API | Manifest |
| Helper được bootstrap định nghĩa? | Có (`getClassLoader()==null`) | Có |
| Helper method chạy được? | Có | Có |
| App gọi được helper? | Có | Có |
| Agent `premain` trước App `main`? | Có | Có |

Một số build HotSpot có thể ghi **CDS/Class Data Sharing warning** trên `stderr` khi bootstrap search path bị mở rộng. Thông báo đó **khác với stdout** ở trên và không tự chứng minh phép append thất bại.

**Đây là ví dụ runtime đúng cho câu hỏi:** “Làm sao một class ứng dụng có thể liên kết tới helper không nằm trên runtime `-cp` nhưng do bootstrap loader định nghĩa?”

## 6. Điều gì xảy ra khi helper có dependency không thuộc bootstrap?

Package specification của `java.lang.instrument` khuyến cáo: **supporting classes do bootstrap loader định nghĩa phải chỉ liên kết tới các class có thể được bootstrap định nghĩa**. Không có bảo đảm bootstrap loader nhìn thấy mọi platform class hoặc class ứng dụng.

Ví dụ **không nên** viết bootstrap helper trực tiếp gọi:

```java
// Minh họa một dependency nguy hiểm trong bootstrap helper:
com.mycompany.application.ApplicationContext.current();
```

Nếu `ApplicationContext` chỉ do application/system/custom loader định nghĩa, bootstrap loader có thể **không tìm được** class đó và phát sinh `NoClassDefFoundError`.

Các giải pháp thiết kế thay thế:

- Giữ helper tối giản, chỉ dùng class bootstrap có thể load.
- Tạo một interface/bridge nhỏ, đặt luồng chuyển tiếp tới agent service ở nơi loader/module thích hợp.
- Tránh để helper phụ thuộc logging framework nặng, DI container, agent implementation hoặc class app.
- Khi cần chia sẻ trạng thái, kiểm tra kỹ loader identity, module boundaries, khả năng GC của classloader và reentrancy.

**Không giải quyết mọi lỗi phụ thuộc bằng cách append toàn bộ thư viện của agent lên bootstrap.** Cách đó tăng nguy cơ xung đột và các lỗi liên kết rất khó điều tra.

## 7. Nguy cơ trùng class và `IllegalAccessError`

Javadoc của `appendToBootstrapClassLoaderSearch` cảnh báo trường hợp một class loader `L` có parent là bootstrap loader, trong khi class `C` của `L` tham chiếu một class hỗ trợ không public như `C$1`. Nếu JAR bootstrap vô tình chứa class `C$1` trùng tên, việc ủy quyền có thể khiến nó được bootstrap định nghĩa, tạo **runtime package/class identity khác** và có thể gây `IllegalAccessError`.

Đây là lý do chọn **package bootstrap helper thật độc nhất**. Đừng đặt các class bổ sung trong package vốn được ứng dụng hoặc thư viện khác dùng. Đừng đóng những class không liên quan vào helper JAR.

Ví dụ package tốt trong một sản phẩm thực tế có thể là:

```text
com.company.product.instrumentation.bootstrap.v1
```

Tên trên là **gợi ý quy ước**, không phải yêu cầu của JVM. Cần thay bằng namespace do tổ chức sở hữu và kiểm toán collision trước khi phát hành.

Một vài lưu ý:

- Cùng tên nhị phân nhưng khác defining loader có thể gây `ClassCastException` khi cast, không phải là một type chung.
- Cùng package text nhưng khác defining loader chưa chắc được coi là cùng runtime package.
- Không thể suy luận “helper chạy trong bootstrap thì luôn có nhiều quyền hơn” để bỏ qua Java visibility hoặc JPMS.
- Helper class đang load không được tự động thay bằng phiên bản mới chỉ vì bạn append thêm một JAR khác chứa cùng tên.

## 8. JPMS: loader visibility không thay module readability

Từ Java 9, ngoài classloader còn có **module**. Helper từ JAR bootstrap thường nằm trong **unnamed module của bootstrap loader**. Trong khi đó, nhiều class nền tảng có thể nằm trong **named module** như `java.base`.

Ví dụ bên trong agent:

```java
Class<?> helper = Class.forName(
        "com.example.agentbootstrap.BootstrapMarker", true, null);
Module module = helper.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
```

Đây là **đoạn minh họa**, cần bối cảnh phù hợp. Với helper trong ví dụ, module thường là unnamed; `isNamed()` trả `false`, `getName()` trả `null`.

### 8.1. Bootstrap class không tự động nhìn thấy mọi application class

Một helper được bootstrap loader định nghĩa **không có khả năng tự load xuống** những class chỉ thuộc system/custom loader. Bootstrap thường là parent trong mô hình delegation; parent không đi xuống tìm mọi class của child.

### 8.2. Named module vẫn có kiểm tra đọc module

Nếu một class trong named module được instrument để gọi helper thuộc bootstrap unnamed module, JVM có thể cần **readability edge** hoặc cấu hình truy cập thích hợp. `appendToBootstrapClassLoaderSearch` và `Boot-Class-Path` không tự:

- Tạo tất cả module read edges.
- Mở mọi `exports`/`opens`.
- Gọi `Instrumentation.redefineModule`.
- Cấp quyền reflection hoặc native access tùy ý.

Nếu thực sự cần sửa graph của module, có thể nghiên cứu `Instrumentation.redefineModule(...)` và quyền liên quan, rồi test tại module cụ thể. Không nên tự thêm các read edges rộng khắp khi chưa hiểu phạm vi agent.

### 8.3. Custom loader có thể có mô hình tìm kiếm khác

Nhiều class loader dùng parent-first delegation, nhưng một số plugin/container loader có chính sách riêng. Với ứng dụng có custom loader hoặc module layer, kiểm tra **class đích thực sự resolve helper thế nào** thay vì chỉ nhìn `Boot-Class-Path` đã được cấu hình.

## 9. Khi nạp agent sau JVM startup (`agentmain`)

Nếu JVM hỗ trợ dynamic attach, một agent JAR có thể khai báo:

```text
Manifest-Version: 1.0
Agent-Class: com.example.agent.DynamicBootstrapAgent
Boot-Class-Path: boot-helper.jar

```

Đây là **manifest minh họa**; class `DynamicBootstrapAgent` phải tồn tại và định nghĩa chữ ký `agentmain` hợp lệ. Ví dụ runnable ở phần 5 là **startup agent** dùng `Premain-Class`, không phải dynamic agent.

Khi chạy muộn:

1. JVM phải cho phép cơ chế attach/dynamic agent loading.
2. Agent được nạp qua `Agent-Class` và `agentmain`, không qua `Premain-Class`/`premain`.
3. `Boot-Class-Path` vẫn là manifest attribute của agent, nhưng **path không đại diện cho JAR file bị bỏ qua** khi agent bắt đầu sau startup.
4. Trong `agentmain(String, Instrumentation)`, agent cũng có thể gọi `appendToBootstrapClassLoaderSearch(new JarFile(...))` nếu môi trường cho phép.
5. Việc thêm helper muộn **không tự sửa symbolic references đã thất bại**, không retransform mọi class cũ, không thay class đã nạp.
6. Nếu class đích đã được nạp và cần chèn lời gọi mới, còn cần thiết kế **retransformation/redefinition** theo capability và giới hạn JVM.
7. Trên JDK 21+, JEP 451 đưa ra các cảnh báo/chính sách liên quan tới **dynamic agent loading**; đây là vấn đề khác với `Boot-Class-Path` và bootstrap helper lookup.

Không nhầm “khai báo Boot-Class-Path là JVM sẽ tự attach agent”: hai cơ chế có nhiệm vụ khác nhau.

## 10. Phân biệt với `appendToSystemClassLoaderSearch`

`Instrumentation` còn có method:

```java
inst.appendToSystemClassLoaderSearch(jar);
```

Đây là **đoạn minh họa** với biến `inst`, `jar` có sẵn; nó thêm JAR vào nơi **system loader** tìm class, không phải nơi bootstrap loader tìm class.

| Tiêu chí | Bootstrap append | System append |
|---|---|---|
| Loader mở rộng | Bootstrap | System |
| Helper `getClassLoader()` | Có thể `null` khi bootstrap định nghĩa | Thường là system loader khi system định nghĩa |
| Use case | Helper được class nền tảng/instrumented code cần | Helper/app dependency ở tầng system |
| Rủi ro | Trùng package/class trong bootstrap, dependency khó nhìn thấy | Trùng tên và custom system loader constraints |
| Có thay method body class đích? | Không | Không |

Nếu cấu hình custom system loader, method `appendToSystemClassLoaderSearch` còn yêu cầu loader thực hiện hợp đồng `appendToClassPathForInstrumentation`. Không nên coi hai API tương đương rồi thay thế qua lại khi gặp lỗi.

## 11. Troubleshooting: nhìn đúng loại lỗi

| Quan sát | Nguyên nhân cần xem |
|---|---|
| `new JarFile` ném IOException | Đường dẫn, quyền đọc, JAR không tồn tại hoặc hỏng |
| `Boot-Class-Path` có nhưng helper không load | File không nằm cạnh agent JAR theo relative path, typo hoặc entry `.class` sai |
| `Class.forName(name, true, null)` ném `ClassNotFoundException` | Bootstrap chưa tìm được class hoặc class entry không có |
| App ném `NoClassDefFoundError` | Helper/dependency không resolve được từ loader liên quan; có thể đã thất bại từ trước |
| `helper.getClassLoader() != null` | Helper có thể được loader khác định nghĩa; runtime classpath có trùng class? |
| `IllegalAccessError` | Package-private, loader identity hoặc module access |
| `ClassCastException` dù tên class giống | Cùng tên nhưng khác defining loader |
| Append thành công nhưng method instrumented vẫn lỗi | Cần xét module read edges, dependency, loader delegation, thời điểm resolve |
| Manifest path chỉ là thư mục trong dynamic attach | Entry không phải JAR có thể bị bỏ qua |
| Có diagnostic CDS trên stderr | Không đồng nghĩa append thất bại; kiểm tra helper loader và kết quả gọi |
| Thêm JAR nhưng class đang chạy không đổi | Append không phải retransform/redefine |
| Khi chạy từ working directory khác bị lỗi | API code đang dùng path relative theo cwd; manifest relative theo agent JAR |

Một quy trình debug thực tế:

1. Kiểm tra **agent JAR** và **helper JAR** trên filesystem mà JVM đang nhìn thấy.
2. Đọc `META-INF/MANIFEST.MF` trong agent JAR cuối cùng (không chỉ file `.mf` dùng để đóng gói).
3. Xem `jar --list --file dist/boot-helper.jar`; entry của `BootstrapMarker.class` phải đúng package.
4. Với API mode, log đường dẫn helper đã được chuẩn hóa và xác nhận mở `JarFile` thành công.
5. Đảm bảo append/manifest được xử lý **trước khi** class đích resolve helper.
6. Chủ động `Class.forName(helperBinaryName, true, null)` để thử bootstrap lookup.
7. Kiểm tra `Class.getClassLoader() == null` và gọi một method đơn giản.
8. Nếu bootstrap load được nhưng instrumented class vẫn không gọi được, xem module readability/access và parent delegation.
9. Nếu từng có failed resolution, không coi append muộn là phép sửa chắc chắn.
10. Với agent production, kiểm tra thêm collision, helper dependencies, JDK version và độ an toàn của nguồn JAR.

## 12. Lỗi thiết kế thường gặp

### 12.1. Đưa cả agent framework lên bootstrap

Một agent có thể phụ thuộc hàng chục thư viện. Đưa tất cả lên bootstrap sẽ làm namespace bootstrap lớn, tăng nguy cơ va chạm và dependency từ helper lên class loader thấp hơn. **Chỉ đóng helper tối thiểu** vào JAR bootstrap.

### 12.2. Dùng manifest `Class-Path` thay `Boot-Class-Path`

Hai header có nghĩa khác nhau. `Class-Path` không tự tạo bootstrap search entries theo hợp đồng agent. Nếu muốn bootstrap helper, dùng `Boot-Class-Path` hoặc API append.

### 12.3. Lầm tưởng `Boot-Class-Path` tương đối với working directory

Sai. `Boot-Class-Path` relative **theo vị trí absolute của agent JAR**. Chỉ đường dẫn `Path.of(...)` tự viết trong API mode mới có thể phụ thuộc working directory.

### 12.4. Gọi helper trước khi append

Nếu code đã cố resolve helper và thất bại, JVM có thể ghi nhận failed symbolic resolution. Hãy append **trước** mọi đường liên kết cần helper.

### 12.5. Không xác minh defining loader

Chỉ vì class có thể được `Class.forName` tìm thấy bằng system loader không chứng minh nó do bootstrap định nghĩa. Dùng `Class.forName(name, true, null)` và `getClassLoader() == null` cho phép kiểm tra cụ thể hơn.

### 12.6. Dùng bootstrap helper để gọi class ứng dụng

Bootstrap helper không tự tìm xuống custom/system loader. Thiết kế bridge và class/module accessibility đúng; không dựa vào việc agent có quyền instrumentation như một tấm vé truy cập mọi class.

### 12.7. Xem append như cách nâng cấp JAR đã chạy

Append path không làm JVM bỏ các class definitions hiện hữu. Muốn thay method body class đã nạp cần cơ chế riêng; muốn thay cấu trúc class có thể phải dùng class loader mới hoặc khởi động lại theo kiến trúc phù hợp.

### 12.8. Không phân biệt lỗi agent với VM diagnostic

Warning về CDS có thể xuất hiện trên stderr khi bootstrap path thay đổi, ngay cả khi agent chạy đúng. Đối chiếu kết quả helper và exception thực sự trước khi kết luận lỗi.

## 13. Câu hỏi tự kiểm tra

**1.** `appendToBootstrapClassLoaderSearch` nhận tham số loại gì?

**Đáp án:** `java.util.jar.JarFile`; không phải `Path` hoặc `String`.

**2.** `Boot-Class-Path: boot-helper.jar` được giải relative theo đâu?

**Đáp án:** Vị trí **agent JAR**, không phải working directory.

**3.** Có `Boot-Class-Path` là JVM tự chạy `BootstrapMarker.message()` không?

**Đáp án:** Không. Header bổ sung nơi tìm class; phải có yêu cầu load và lời gọi method mới chạy.

**4.** Điều gì chứng minh helper được bootstrap loader định nghĩa?

**Đáp án:** `BootstrapMarker.class.getClassLoader() == null`, hoặc dùng `Class.forName(name, true, null)` rồi kiểm tra defining loader.

**5.** Vì sao ví dụ `App` compile với `-cp out/helper` nhưng runtime chỉ dùng `-cp out/app`?

**Đáp án:** Compiler cần biết kiểu helper khi compile. Runtime helper được bootstrap search path cung cấp qua agent.

**6.** Append JAR sau một failed symbolic resolution có đảm bảo cùng reference được sửa không?

**Đáp án:** Không. JVM có quy tắc đối với failed resolution; nên append trước khi target cần helper.

**7.** Bootstrap helper có thể import mọi class do system loader định nghĩa không?

**Đáp án:** Không. Helper phải link tới những class bootstrap loader có thể thấy; không tự tìm xuống classloader con.

**8.** Có nên đưa cả Byte Buddy/ASM, logging và application libraries lên bootstrap để “tránh ClassNotFoundException” không?

**Đáp án:** Không. Điều đó tăng nguy cơ namespace collision và dependency errors. Chỉ đưa helper cần thiết.

**9.** `Boot-Class-Path` có dùng cùng `Agent-Class` cho dynamic attach không?

**Đáp án:** Có nếu runtime hỗ trợ dynamic agent; nhưng đường dẫn không đại diện JAR bị bỏ qua khi khởi động muộn.

**10.** `appendToSystemClassLoaderSearch` và `appendToBootstrapClassLoaderSearch` giống nhau không?

**Đáp án:** Không. Chúng mở rộng **hai loader khác nhau**.

**11.** Chỉnh `Boot-Class-Path` có tự cấp module read edges cho mọi named module không?

**Đáp án:** Không. JPMS access/readability là trách nhiệm khác, có thể cần `Instrumentation.redefineModule` theo đúng hợp đồng.

**12.** Nếu agent in warning CDS trên stderr nhưng các dòng `loader=bootstrap` và `helper=bootstrap-ok` xuất hiện, có thể kết luận bootstrap helper load thất bại không?

**Đáp án:** Không. Trong ví dụ, helper đã được bootstrap định nghĩa và gọi thành công; warning VM không đồng nghĩa lỗi.

## 14. Checklist khi phát hành agent có bootstrap helper

| Kiểm tra | Kỳ vọng |
|---|---|
| Namespace helper | Riêng, không đụng JDK/application |
| Nội dung helper JAR | Chỉ các class và resources thật sự cần |
| Dependency của helper | Chỉ dùng class bootstrap nhìn thấy |
| Path API | Có thể mở bằng `new JarFile(...)` và có đường dẫn rõ ràng |
| Path manifest | Relative theo agent JAR, đúng tên file và cú pháp |
| Manifest thực tế | Được kiểm tra từ JAR cuối cùng |
| Timing | Helper sẵn sàng trước lúc target resolve |
| Loader identity | `getClassLoader() == null` cho helper bootstrap |
| JPMS | Kiểm tra module readability/access với named module |
| Dynamic attach | Runtime cho phép, JAR entries phù hợp |
| No shadowing | Không trùng binary name với class đang có |
| Java version | Đã thử trên các bản JDK mục tiêu |
| Resource lifetime | JAR không bị đóng quá sớm |
| Runtime classpath test | Không “vô tình” đưa helper vào `-cp` làm sai thí nghiệm |
| Observability | Log rõ agent mode, helper lookup và lỗi cụ thể |

## 15. Tổng kết

- **`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`**: agent mở JAR và chủ động append vào bootstrap search path.
- **`Boot-Class-Path`**: JVM lấy danh sách path từ **main manifest của agent JAR**; path relative theo agent JAR.
- Cả hai **chỉ làm helper class có thể được bootstrap tìm thấy**, không tự instrument, không tự load tất cả class và không thay class đã nạp.
- Helper do bootstrap định nghĩa có `Class.getClassLoader() == null`, nhưng vẫn cần xử lý **JPMS visibility** và dependency hợp lệ.
- Nên giữ bootstrap helper **tối thiểu**, package riêng, và thêm path **trước** khi class đích cố resolve helper.
- Ví dụ Java 17+ đã cho cùng kết quả qua API mode và manifest mode, với helper **không có trên runtime application classpath**.

## Tài liệu tham khảo chính thức

- Oracle Java 17 — [`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java 17 — [`java.lang.instrument`: agent class loading và `Boot-Class-Path` manifest attribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- Oracle Java 17 — [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html).
- Oracle Java 17 — [`Class.getClassLoader()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()).
- Oracle Java 17 — [`Instrumentation.redefineModule` và các instrumentation APIs](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java 17 — [Java Virtual Machine Specification — resolution and failed resolution (§5.4.3)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3).
- Oracle Java 17 — [JAR File Specification — manifest format](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html).
- OpenJDK — [JEP 451: Dynamic Agent Loading (JDK 21)](https://openjdk.org/jeps/451).
