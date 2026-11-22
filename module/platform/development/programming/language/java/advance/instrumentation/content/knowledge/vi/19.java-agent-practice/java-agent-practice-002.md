# Liệt kê lớp đã nạp cùng bộ nạp và khả năng sửa của từng lớp

## 1. Mục tiêu và đầu ra mong đợi

Trong thực nghiệm Java agent, một câu hỏi chẩn đoán cơ bản là: **JVM hiện đang giữ những lớp nào, mỗi lớp được định nghĩa bởi class loader nào, và lớp ấy có được JVM xem là có thể sửa qua redefinition hoặc retransformation không?** Ba lời gọi cần nắm là:

~~~java
Class<?>[] classes = inst.getAllLoadedClasses();
ClassLoader definingLoader = clazz.getClassLoader();
boolean modifiable = inst.isModifiableClass(clazz);
~~~

Đây là ba dòng **minh họa** đặt trong code đã có đối tượng `Instrumentation inst` và biến `Class<?> clazz`; bản chạy hoàn chỉnh ở phần sau.

Mục tiêu của bài **“Liệt kê lớp đã nạp cùng bộ nạp và khả năng sửa của từng lớp”**, thuộc nhóm **Thực nghiệm agent**, là tạo một Java agent thật trên Java 17+, có hai chế độ:

- `demo.app.`: vẫn lấy snapshot toàn JVM, nhưng chỉ **in** những class có tên bắt đầu bằng tiền tố này. Chế độ này nhỏ, dễ kiểm thử với output cụ thể.
- `all`: duyệt **toàn bộ snapshot `getAllLoadedClasses()`** và in **một dòng cho từng class**, bao gồm class name, defining class loader và `isModifiableClass`.

Ta còn dùng hai URLClassLoader khác nhau định nghĩa **cùng một binary class name** để thấy vì sao báo cáo chỉ dựa trên `Class.getName()` là chưa đủ.

**Giới hạn nhiệm vụ:** đây là hoạt động **đọc thông tin** của JVM. Agent không thêm transformer, không sửa class bytes, không gọi `redefineClasses` hay `retransformClasses`, và không cấp thêm quyền truy cập vào module. Việc in báo cáo vẫn tốn CPU, bộ nhớ và I/O nên cần kiểm soát ở production.

## 2. API chính thức Instrumentation.getAllLoadedClasses

Java SE 17 định nghĩa:

~~~java
Class<?>[] snapshot = inst.getAllLoadedClasses();
~~~

Theo Javadoc, API trả về mảng những lớp hiện đã được nạp trong JVM, gồm classes, interfaces, **hidden classes/interfaces** và **array classes of all types**. Mỗi phần tử là một đối tượng `Class<?>`, không phải tên class dạng text.

### 2.1. Nó là snapshot, không phải live list

Mảng được chụp tại một thời điểm. JVM có thể nạp thêm class hoặc unload một class loader sau đó. Đừng coi số lượng `snapshot.length` là bộ đếm toàn cục luôn đúng. Thậm chí việc chạy code sắp xếp, tạo formatter hoặc logging có thể khiến JVM nạp thêm class sau khi snapshot đã được tạo.

Không có cam kết về thứ tự phần tử. Nếu cần output dễ đọc, hãy **sắp xếp bản sao/danh sách lọc** theo tên và loader identity. Đừng suy ra class loading chronology từ thứ tự ban đầu trong mảng.

### 2.2. Những loại class dễ gây bất ngờ

| Loại | Tên có thể quan sát | Lưu ý |
|---|---|---|
| Class thường | `demo.app.Main` | Tên binary Java |
| Interface | `java.lang.Runnable` | Là Class object dù Java gọi là interface |
| Mảng primitive | `[I` | Tên runtime/descriptor, không phải `int[]` theo cách viết source |
| Mảng reference | `[Ljava.lang.String;` | Có thể có trong snapshot nếu đã load |
| Hidden class | Tên có thể chứa hậu tố JVM dạng `/0x...` | Không nhất thiết tìm lại bằng `Class.forName` thông thường |
| Proxy/lambda/generated | Tên do công cụ/JVM tạo | Số lượng phụ thuộc runtime và thời điểm |

Bảng chỉ giải thích loại, **không khẳng định mọi dòng này bắt buộc xuất hiện ở tất cả JVM**. Một điểm quan trọng là `getAllLoadedClasses` không giới hạn chỉ các lớp trong application classpath.

### 2.3. Không dùng Class.forName để quét lại mọi lớp

Ta đã có đối tượng `Class<?>` từ JVM; không cần dùng `Class.forName(c.getName())` để “xác minh”. Làm vậy có thể không tìm được hidden class, có thể kích hoạt class initialization hoặc kích hoạt thêm loading qua loader không phù hợp. Hãy lấy metadata trực tiếp từ `Class<?>` object.

## 3. Class.getClassLoader: bộ nạp nào đang được hỏi?

~~~java
ClassLoader loader = clazz.getClassLoader();
~~~

Hàm này cho biết **defining class loader** của class. Theo cơ chế JVM, tên class **một mình không đủ** để xác định duy nhất class identity: cùng binary name do **hai defining loaders khác nhau** tạo ra là hai classes khác nhau.

Các trường hợp báo cáo trong lab:

| Điều kiện | Nhãn ngắn | Giải thích |
|---|---|---|
| `loader == null` | `bootstrap` | Class do bootstrap loader định nghĩa |
| `loader == ClassLoader.getSystemClassLoader()` | `system` | Class do system class loader định nghĩa |
| `loader == ClassLoader.getPlatformClassLoader()` | `platform` | Class do platform class loader định nghĩa |
| Còn lại | `custom:<loader-type>@<identity-hash>` | Class loader khác, ví dụ URLClassLoader |

**`null` không phải lỗi.** Bootstrap class loader không được biểu diễn bằng một Java `ClassLoader` object thông thường mà `Class.getClassLoader()` trả về.

Nhãn `system`/`platform` mô tả **vai trò trong JVM đó**, không bảo đảm class loader có class name cố định trên mọi vendor/JDK. Ở custom loader, dùng class name và `System.identityHashCode(loader)` để tăng khả năng phân biệt hai instances. Hash chỉ là **thông tin tham khảo trong một run**, có thể trùng hiếm gặp và không ổn định giữa các tiến trình; khi cần ID chắc chắn, map trực tiếp bằng **object identity** và quản lý vòng đời ID riêng.

### 3.1. Array classes được nạp bởi loader nào?

Với array type của reference class, defining loader gắn với component type theo quy tắc JVM; primitive array types được định nghĩa bởi bootstrap. Do đó, không được gộp mọi class có `getName().startsWith("[")` vào system loader.

### 3.2. getInitiatedClasses không có cùng ý nghĩa

`Instrumentation.getInitiatedClasses(loader)` trả các class mà loader được ghi nhận là **initiating loader**, tức có thể tìm thông qua `ClassLoader.loadClass`, `Class.forName` hoặc linkage. Với parent delegation, initiating loader không nhất thiết là **defining loader**. Theo Java SE 17, danh sách initiated còn không gồm hidden classes/interfaces theo cách getAllLoadedClasses có.

~~~java
Class<?>[] initiated =
        inst.getInitiatedClasses(
                ClassLoader.getSystemClassLoader());
~~~

Đây là một **ví dụ API phụ**. Nếu yêu cầu là “với mỗi class trong toàn JVM, ghi đúng loader định nghĩa nó”, cách đúng trong bài là `getAllLoadedClasses()` rồi `Class.getClassLoader()` cho **từng phần tử** — không lấy `getInitiatedClasses(system)` và ghi nhãn “system” cho tất cả.

## 4. isModifiableClass: khả năng sửa ở mức class

~~~java
boolean modifiable = inst.isModifiableClass(clazz);
~~~

API trả `true` nếu JVM xem class có thể sửa bằng `retransformClasses` hoặc `redefineClasses` xét **bản thân class**; trả `false` nếu class không modifiable.

Hai đối chứng được Javadoc Java SE 17 đảm bảo:

~~~java
inst.isModifiableClass(int.class);     // false
inst.isModifiableClass(int[].class);   // false
~~~

Class biểu diễn **kiểu nguyên thủy** và **kiểu mảng** luôn **không modifiable**. Với những classes khác, không đoán theo tên package: hãy gọi API thật.

### 4.1. Modifiable true chưa đủ để thực hiện sửa code

Javadoc nói rõ kết quả `isModifiableClass` **độc lập** với:

~~~java
inst.isRetransformClassesSupported();
inst.isRedefineClassesSupported();
~~~

Một class có thể `modifiable=true` trong báo cáo nhưng agent **không yêu cầu** `Can-Retransform-Classes` hoặc `Can-Redefine-Classes` qua manifest. Nếu muốn retransform thực sự, cần capability được JVM hỗ trợ, class modifiable, transformer phù hợp, class bytes hợp lệ và các quy tắc class schema.

Bởi vậy:

- `isModifiableClass(c) == false`: không dùng c làm đích retransform/redefine.
- `isModifiableClass(c) == true`: **điều kiện cần**, không phải lời hứa mọi thao tác sửa thành công.
- `isRetransformClassesSupported() == false`: ngay cả class báo modifiable true cũng không làm `retransformClasses` trở thành khả dụng.
- VM vẫn có thể từ chối thay đổi schema như thêm field/method hoặc đổi superclass trên HotSpot/JVM TI hiện hành.

Trong ví dụ chính, manifest **không** xin capability thay code nào vì bài chỉ quan sát. Do đó không lấy modifiable flag làm cơ sở để hô “đã patch thành công”.

### 4.2. Modifiable không phải permission của người sử dụng

Cờ này không phải ACL, không phải kiểm tra user có quyền sửa bytecode hay không, và không thay thế chính sách attach/OS/JVM. Nó mô tả một tính chất VM đối với class, còn thao tác cụ thể có nhiều điều kiện vận hành và kỹ thuật khác.

## 5. Kiến trúc demo

Cấu trúc:

~~~text
loaded-class-lab/
├── agent.mf
├── src/
│   ├── agent/demo/agent/LoadedClassAgent.java
│   └── app/demo/app/
│       ├── Main.java
│       └── Helper.java
└── out/
    ├── agent/
    ├── app/
    └── loaded-class-agent.jar
~~~

`LoadedClassAgent.premain` nhận đối tượng `Instrumentation` từ JVM và giữ lại một reference. `Main` tạo một instance của `Helper`, rồi gọi `LoadedClassAgent.dump(...)` để xuất snapshot **sau khi Main và Helper đã được nạp**.

~~~text
JVM khởi động -javaagent
          |
          v
Agent.premain -> Instrumentation được cấp -> agent:ready
          |
          v
Main.main
  |
  +-- new Helper().ping()     -> app:helper=ok
  |
  +-- LoadedClassAgent.dump("demo.app.")
       |
       +-- getAllLoadedClasses()
       +-- lọc/sort
       +-- mỗi Class: getName(), getClassLoader(), isModifiableClass()
       +-- in hai app classes và probe primitive/array
~~~

Việc `Main` import agent class chỉ nhằm có một trigger deterministic trong **lab**. Trong app sản phẩm, nên chọn trigger độc lập từ `agentmain`, JMX hoặc kênh quản trị được kiểm soát quyền, thay vì gắn business source với agent.

## 6. Source Java agent đầy đủ

Tệp **`src/agent/demo/agent/LoadedClassAgent.java`**:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class LoadedClassAgent {
    private static volatile Instrumentation instrumentation;
    private LoadedClassAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent:ready");
    }

    public static void dump(String scope) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent");
        }

        Class<?>[] snapshot = inst.getAllLoadedClasses();
        boolean all = "all".equals(scope);

        List<Class<?>> selected = new ArrayList<>();
        for (Class<?> type : snapshot) {
            if (all || type.getName().startsWith(scope)) {
                selected.add(type);
            }
        }

        selected.sort(Comparator
                .comparing((Class<?> c) -> c.getName())
                .thenComparingInt(c ->
                        System.identityHashCode(c.getClassLoader())));

        System.out.println("snapshot:scope=" + scope);
        for (Class<?> type : selected) {
            ClassLoader loader = type.getClassLoader();
            System.out.println(
                    "loaded=" + type.getName()
                    + " | loader=" + describe(loader)
                    + " | modifiable="
                    + inst.isModifiableClass(type));
        }

        System.out.println("snapshot:selected=" + selected.size());
        System.out.println(
                "probe:int=" + inst.isModifiableClass(int.class));
        System.out.println(
                "probe:int-array=" + inst.isModifiableClass(int[].class));
        System.out.println("snapshot:end");
    }

    private static String describe(ClassLoader loader) {
        if (loader == null) return "bootstrap";
        if (loader == ClassLoader.getSystemClassLoader()) {
            return "system";
        }
        if (loader == ClassLoader.getPlatformClassLoader()) {
            return "platform";
        }
        return "custom:" + loader.getClass().getName()
                + "@"
                + Integer.toHexString(
                        System.identityHashCode(loader));
    }
}
~~~

Đây là mã **hoàn chỉnh, chạy được trên Java 17+**. Không cần OW2 ASM, Byte Buddy hoặc `jdk.internal.*` vì tác vụ **không thay bytes**.

### 6.1. Giải thích chi tiết

**`static volatile Instrumentation instrumentation`:** giữ đối tượng VM đã cấp qua `premain`. `volatile` bảo đảm khả năng nhìn thấy tham chiếu giữa các threads trong lab, nhưng không tạo một snapshot atomic đối với mọi class loading đang đồng thời diễn ra.

**`dump("demo.app.")`:** vẫn gọi `getAllLoadedClasses` với phạm vi **toàn JVM**, sau đó lọc các class có tên bắt đầu bằng `demo.app.` để giảm output. Không có overload của `getAllLoadedClasses` cho phép yêu cầu JVM chỉ quét một package.

**`dump("all")`:** bỏ điều kiện lọc theo tên, thêm tất cả phần tử mảng vào danh sách và in từng class. Đây là chế độ đầy đủ đáp ứng yêu cầu liệt kê mỗi class, nhưng có thể sinh rất nhiều dòng.

**`Comparator`:** sắp xếp theo `Class.getName()` rồi identity hash của loader để output dễ đọc. Việc sắp xếp bằng hash có thể không phân biệt tuyệt đối trong trường hợp collision và không ổn định giữa runs; đây là kỹ thuật trình diễn, không phải persistent ID system.

**`describe(loader)`:** phân biệt bootstrap/system/platform/custom. Với custom loader, in loại Java và hash identity; không chỉ in `loader.getClass().getName()` vì nhiều instances cùng loại loader có thể định nghĩa những classes trùng tên.

**`isModifiableClass(type)`:** được gọi **một lần trên từng class được hiển thị**; không suy khả năng sửa của class từ tên package hoặc loader.

**Các probe `int.class`/`int[].class`:** đối chứng hai trường hợp chắc chắn false, độc lập với việc primitive class có xuất hiện trong snapshot hay không.

### 6.2. Tại sao không có ClassFileTransformer?

Không cần. `Instrumentation` cung cấp `getAllLoadedClasses` trực tiếp, không cần hook class loading để biết các class đã được nạp trước đó. Thêm transformer chỉ để liệt kê snapshot làm bài khó hơn, có thể làm thay class loading order và tăng overhead.

### 6.3. Vì sao phải giữ bản ghi loader cho từng class?

Nếu chỉ in:

~~~text
demo.app.Helper=true
~~~

thì không thể biết class do loader nào định nghĩa. Nếu hai loaders độc lập cùng load tên `demo.isolated.Widget`, hai records sẽ có cùng tên và có thể cùng modifiable flag, nhưng **không phải một Class object**. Bởi vậy dòng báo cáo bắt buộc có **loader identity/role**.

## 7. Ứng dụng Java dùng để kiểm chứng

Tệp **`src/app/demo/app/Helper.java`**:

~~~java
package demo.app;

public final class Helper {
    public String ping() {
        return "ok";
    }
}
~~~

Tệp **`src/app/demo/app/Main.java`**:

~~~java
package demo.app;

import demo.agent.LoadedClassAgent;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app:start");
        System.out.println(
                "app:helper=" + new Helper().ping());
        System.out.println("app:before-snapshot");

        LoadedClassAgent.dump(
                args.length == 0 ? "demo.app." : args[0]);

        System.out.println("app:end");
    }
}
~~~

`Main` cố tình tạo `Helper` trước khi chụp snapshot; nó cũng đã được JVM nạp để chạy entry point. Vì thế khi filter `demo.app.`, ta mong đợi **Main** và **Helper**.

Dòng `LoadedClassAgent.dump` tạo **compile-time dependency** giữa app mẫu và agent, được biên dịch nhờ `-cp out/agent`. Khi chạy `-javaagent`, JDK đưa agent classes vào system class loader search path theo hợp đồng Java agent, và Main có thể tìm thấy agent class. Không chạy bản Main này như ứng dụng độc lập không có agent JAR: nó cố gọi `LoadedClassAgent` và có thể bị `NoClassDefFoundError` hoặc `IllegalStateException` tùy classpath. Đây là **giới hạn có chủ đích của test harness**, không phải production architecture.

## 8. Manifest, biên dịch và đóng gói

Tệp **`agent.mf`** phải có nội dung:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.LoadedClassAgent

~~~

Giữ newline cuối và build lại JAR mỗi khi đổi manifest. `Premain-Class` là **binary name** có dấu chấm, không phải internal JVM name có slash.

Tạo output directories:

~~~bash
mkdir -p out/agent out/app
~~~

Nếu dùng Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

Biên dịch và tạo agent JAR bằng JDK 17+:

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/LoadedClassAgent.java

javac --release 17 -cp out/agent -d out/app src/app/demo/app/Main.java src/app/demo/app/Helper.java

jar --create --file out/loaded-class-agent.jar --manifest agent.mf -C out/agent .
~~~

Giải thích:

1. `javac --release 17` tạo classfile target Java 17 (major version 61), không dùng API Java mới hơn.
2. `out/agent` chứa class `demo.agent.LoadedClassAgent`.
3. `-cp out/agent` ở lệnh compile app để compiler resolve import của Main.
4. `out/app` chứa hai app classes, **không** cần đóng chúng vào agent JAR.
5. Lệnh `jar` ghi manifest và agent classes; sau đó phải kiểm tra **artifact cuối**.

Kiểm tra JAR:

~~~bash
jar --list --file out/loaded-class-agent.jar
jdeps --jdk-internals out/loaded-class-agent.jar
~~~

Trong danh sách `jar --list` cần có `META-INF/MANIFEST.MF` và `demo/agent/LoadedClassAgent.class`. `jdeps --jdk-internals` không nên báo phụ thuộc JDK internal APIs vì source chỉ dùng API công khai. Nếu thiếu `Premain-Class` trong JAR thực, JVM sẽ báo lỗi trước khi app main được gọi; sửa file manifest nguồn mà không rebuild JAR không giải quyết được.

**Không cần `Can-Retransform-Classes: true` hay `Can-Redefine-Classes: true`** trong manifest bài này, vì không thực hiện retransform/redefine, chỉ gọi API quan sát. Đây cũng là cơ hội học sự khác biệt giữa cờ `isModifiableClass` và capabilities toàn agent.

## 9. Chế độ lọc: output exact đã kiểm thử

Chạy:

~~~bash
java -Xverify:all -javaagent:out/loaded-class-agent.jar -cp out/app demo.app.Main
~~~

**Stdout đo được từ bài test thực tế trên JDK 24.0.2 (bytecode biên dịch `--release 17`):**

~~~text
agent:ready
app:start
app:helper=ok
app:before-snapshot
snapshot:scope=demo.app.
loaded=demo.app.Helper | loader=system | modifiable=true
loaded=demo.app.Main | loader=system | modifiable=true
snapshot:selected=2
probe:int=false
probe:int-array=false
snapshot:end
app:end
~~~

Cách đọc:

- `agent:ready`: `premain` nhận và lưu `Instrumentation` trước app main.
- `app:helper=ok`: Helper đã được dùng trước khi snapshot.
- `snapshot:scope=demo.app.`: chương trình **lọc phần hiển thị**, không nói JVM chỉ có hai lớp.
- `loaded=demo.app.Helper` và `loaded=demo.app.Main`: hai Class objects được loader `system` định nghĩa trong test.
- `modifiable=true`: VM báo hai class này có khả năng sửa xét theo từng class; không đồng nghĩa agent đã xin capability thực hiện sửa.
- `snapshot:selected=2`: số phần tử **sau lọc**, không phải tổng số loaded classes của JVM.
- `probe:int=false` và `probe:int-array=false`: kết quả đúng theo hợp đồng Java SE 17.
- `app:end`: chương trình tiếp tục chạy sau khi in snapshot.

### 9.1. Những gì không nên kiểm thử bằng exact-match

Ở máy khác, số lượng loaded classes có thể thay đổi. Nếu app mở rộng thêm class có package `demo.app.`, `snapshot:selected` không còn 2. Nếu system class loader được tùy chỉnh, nhãn/hành vi có thể thay đổi. Vì thế stdout trên là **kết quả chính xác của lab cô lập đã chạy**, không phải chuẩn duy nhất cho mọi runtime.

### 9.2. Vì sao chương trình không hiển thị mã nguồn hay bytecode?

`getAllLoadedClasses` trả `Class<?>` objects để quan sát **metadata runtime**. Nó không cấp classfile bytes, không cho biết body method đã được instrument hay chưa, và không tự đo số invocation. Muốn xem class bytes hoặc đo method execution cần API/thiết kế khác, không nằm trong mục tiêu bài này.

## 10. Chế độ all: liệt kê từng class của toàn JVM

Lệnh:

~~~bash
java -Xverify:all -javaagent:out/loaded-class-agent.jar -cp out/app demo.app.Main all
~~~

Vì `scope` bằng `all`, đoạn code:

~~~java
boolean all = "all".equals(scope);

for (Class<?> type : snapshot) {
    if (all || type.getName().startsWith(scope)) {
        selected.add(type);
    }
}
~~~

thêm **mọi phần tử `getAllLoadedClasses()`** vào danh sách, sau đó ghi:

~~~text
loaded=class.name | loader=defining-loader | modifiable=true-or-false
~~~

Dòng trên là **mẫu định dạng**, không phải một log chính xác từ JVM. Output thực tế có thể rất dài; không nên hiển thị toàn bộ ở bài viết.

Để lưu file khi chạy trong lab với Bash:

~~~bash
java -Xverify:all -javaagent:out/loaded-class-agent.jar -cp out/app demo.app.Main all > loaded-classes.txt
~~~

Với PowerShell:

~~~powershell
java -Xverify:all -javaagent:out/loaded-class-agent.jar -cp out/app demo.app.Main all | Out-File -Encoding utf8 loaded-classes.txt
~~~

### 10.1. Kết quả thí nghiệm thực tế

Trong một lần chạy Java 17-target agent trên JDK 24.0.2:

- `snapshot:scope=all` đã xuất hiện.
- Có **1.282** dòng class trong selected snapshot.
- Có nhiều records với `loader=bootstrap`.
- Có cả hidden class records và array class records.
- Có **167** dòng `modifiable=false` trong lần chạy đó.
- Cả `demo.app.Helper` và `demo.app.Main` vẫn nằm trong output, đều `loader=system | modifiable=true`.

Các con số **1.282** và **167** chỉ là phép đo của **một run** trên **một JVM**; class loading phụ thuộc JDK/version/options/timing và các library đang được sử dụng. **Không assert những số này ở CI trên một runtime khác**. Hãy assert các tính chất ổn định: có output cho từng class trong snapshot, bootstrap loader được xử lý, primitive/array probes false và những class app mà test đã chủ động nạp có mặt.

### 10.2. Kiểm tra output count theo đúng run

Trong source, vòng lặp hiển thị mỗi `Class<?>` được chọn bằng **một dòng** `loaded=...`, sau đó in `snapshot:selected=<size>`. Có thể lọc các dòng bắt đầu `loaded=` rồi đếm trong chính output file. Cần bỏ qua các log khác như `agent:ready` hoặc `app:start`.

Nếu class-loading logging được in từ nhiều threads/agents cùng lúc vào stdout, việc parse sẽ phức tạp hơn. Production tool nên ghi report có cấu trúc và thời điểm/correlation ID riêng thay vì trộn tất cả vào stdout service.

## 11. Thực nghiệm thứ hai: hai defining loaders, một tên class

Một cái bẫy: từ `getAllLoadedClasses` thấy hai dòng cùng tên `demo.isolated.Widget`, rồi nghĩ đó là duplicate vô nghĩa. Thực ra, cặp **(binary name, defining class loader)** tạo class identity trong JVM.

Ta cố ý định nghĩa một lớp `Widget` từ **hai `URLClassLoader` instances riêng**.

Tệp **`src/plugin/demo/isolated/Widget.java`**:

~~~java
package demo.isolated;

public final class Widget {
    public String id() {
        return "widget";
    }
}
~~~

Biên dịch vào thư mục **riêng**:

~~~bash
mkdir -p out/plugin
javac --release 17 -d out/plugin src/plugin/demo/isolated/Widget.java
~~~

Không thêm `out/plugin` vào runtime application classpath. Hai URLClassLoader sẽ đọc cùng `Widget.class` từ đường dẫn này.

Tệp **`src/app/demo/app/LoaderMain.java`**:

~~~java
package demo.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import demo.agent.LoadedClassAgent;

public final class LoaderMain {
    public static void main(String[] args) throws Exception {
        URL root = Path.of("out/plugin")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader first =
                     new URLClassLoader(new URL[] {root}, null);
             URLClassLoader second =
                     new URLClassLoader(new URL[] {root}, null)) {

            Class<?> a = Class.forName(
                    "demo.isolated.Widget", false, first);

            Class<?> b = Class.forName(
                    "demo.isolated.Widget", false, second);

            System.out.println(
                    "same-name=" + a.getName().equals(b.getName()));

            System.out.println("same-class=" + (a == b));

            LoadedClassAgent.dump("demo.isolated.");
        }
    }
}
~~~

Parent `null` của hai URLClassLoader trong lab giúp chúng **không ủy quyền việc định nghĩa `Widget` cho application loader**, trong khi bootstrap classes vẫn sẵn có. Đây là test isolation, không phải mẫu xây plugin production mặc định.

Compile, chạy:

~~~bash
javac --release 17 -cp out/agent -d out/app src/app/demo/app/LoaderMain.java

java -Xverify:all -javaagent:out/loaded-class-agent.jar -cp out/app demo.app.LoaderMain
~~~

**Hai dòng behavior đã được kiểm chứng trên JDK 24.0.2:**

~~~text
same-name=true
same-class=false
~~~

Trong snapshot sau đó, `demo.isolated.Widget` có **hai records với custom URLClassLoader identity hashes khác nhau**, và mỗi class báo `modifiable=true` trong JVM thử nghiệm. Nếu bạn thấy đúng hai dòng `loaded=demo.isolated.Widget` và `snapshot:selected=2`, đây là kết quả mong muốn.

Không assert exact identity hashes: chúng thay đổi giữa runs và có thể khác giữa JDK vendors. Nếu hai records có cùng class name nhưng loaders khác nhau, đó là **hai Class objects**. Đừng tạo một `Map<String, Boolean>` chỉ dùng tên class làm key cho toàn JVM vì nó sẽ gộp nhầm hai classes này.

### 11.1. Không giữ references mạnh vô hạn

Khi giữ lâu các `Class<?>`/`ClassLoader` objects trong agent static fields, class unloading có thể bị cản trở. Với snapshot chẩn đoán, sau khi in hoặc ghi dữ liệu cần thiết hãy giải phóng references; nếu xây long-term metrics, dùng loader IDs và lifecycle policies phù hợp, cân nhắc weak references thay vì cache mạnh vô hạn.

## 12. Những điều kết quả modifiable không chứng minh

Một dòng:

~~~text
loaded=demo.app.Main | loader=system | modifiable=true
~~~

**không** chứng minh:

1. Transformer đã được đăng ký.
2. `Can-Retransform-Classes` hoặc `Can-Redefine-Classes` được bật.
3. VM cho phép thay toàn bộ schema của class.
4. Class đã từng được redefine hoặc retransform.
5. Agent có quyền can thiệp vào mọi module hoặc classloader.
6. Bytecode được cài sẽ hợp lệ và business behavior được giữ nguyên.
7. Người dùng hoặc tool có quyền attach vào một JVM khác.
8. Không có class cùng binary name tại custom loader khác.

Nếu muốn **sửa thật**, trước hết hỏi:

~~~java
boolean classIsModifiable =
        inst.isModifiableClass(clazz);
boolean canRetransform =
        inst.isRetransformClassesSupported();
boolean canRedefine =
        inst.isRedefineClassesSupported();
~~~

Đây chỉ là **trích đoạn kiểm tra điều kiện**. Sau đó vẫn phải xem schema restrictions, transformer code, bytecode verification, helper visibility, thread safety và cả deployment policy. Đừng dùng output của bài snapshot làm kết quả “agent đã sửa thành công”.

## 13. Snapshot khác gì class loading events?

`getAllLoadedClasses()` là ảnh chụp hiện trạng tại thời điểm gọi. Nó không nêu **thời gian class được load**, không cho biết **ai yêu cầu load**, không đo memory footprint của tất cả instances và không thể đếm số lần method được gọi.

| Mục tiêu | Công cụ phù hợp hơn |
|---|---|
| Danh sách mọi class hiện đang load | `getAllLoadedClasses()` |
| Defining loader của từng class | `Class.getClassLoader()` |
| Class có thể retransform/redefine xét theo VM? | `isModifiableClass(clazz)` |
| Class nào vừa được định nghĩa? | `ClassFileTransformer`, JFR/ClassLoading event hoặc logging JVM |
| Thời gian thực thi mỗi method | Bytecode probes/profiler/JFR phù hợp |
| Class nào được một loader bắt đầu nạp? | `getInitiatedClasses(loader)` theo đúng nghĩa initiating |
| Class nào được nạp trước khi agent startup? | Snapshot đã load; không kỳ vọng transformer tự replay |
| Class loader có bị leak? | Snapshot theo thời gian + heap/jcmd/JFR/class unloading analysis |

Không suy từ **một** snapshot rằng một class đã leak. Class unloading và GC phụ thuộc reference graph, threads, caches và thời gian. Việc chạy tool chẩn đoán cũng có thể làm nạp class mới.

## 14. Cách mở rộng thành agentmain để quan sát JVM đang chạy

Bài chính chọn `premain` để tránh phức tạp về dynamic attach. Nhưng trong ứng dụng thật, nhu cầu thường là **liệt kê classes sau khi JVM đã chạy lâu**. Nếu JVM cho phép agent loading sau startup, có thể bổ sung entry point:

~~~java
public static void agentmain(
        String options, Instrumentation inst) {

    instrumentation = inst;
    System.out.println("agent:attached");

    dump(options == null || options.isBlank()
            ? "all" : options);
}
~~~

**Đây là đoạn mở rộng minh họa**, phải đặt vào class `LoadedClassAgent` và khai báo `Agent-Class` trong JAR manifest trước khi sử dụng. Nó **không thuộc phần test startup-agent ở mục 9**.

Những điều cần xác minh:

- JVM và vendor có hỗ trợ dynamic attach hay không.
- OS/container permissions, PID ownership và các flags/chính sách tải agent động.
- JDK 21+ có cảnh báo/khuyến nghị riêng liên quan dynamic agent loading; kiểm tra runtime đích.
- `agentmain` không được in vô hạn hàng chục nghìn records vào stdout JVM production.
- Nếu operator yêu cầu `all`, cân nhắc giới hạn số records, redaction và nơi lưu log bảo mật.
- Dynamic attach thành công không có nghĩa lớp nào cũng modifiable; vẫn hỏi từng `Class<?>`.

**Điểm mạnh của snapshot:** nó bao gồm classes đã nạp **trước lúc agent attach**, không phụ thuộc việc transformer từng quan sát lớp đó ở load-time.

## 15. Giảm rủi ro khi liệt kê một JVM lớn

### 15.1. Chi phí CPU, heap và logging

Lệnh `getAllLoadedClasses` tạo mảng class references; code demo còn tạo `ArrayList`, sort và in mỗi record. Trong JVM nhiều class loaders hoặc framework generate rất nhiều classes, việc này có thể tiêu tốn CPU/heap và gây log flooding.

- Nên lọc sớm theo tên/module/loader trên snapshot để giảm **danh sách in**.
- Không gọi `Class.forName` để “xác minh” từng phần tử.
- Không lưu snapshot vào static map sống vô hạn.
- Không gọi network/database từ vòng lặp nếu đây là công cụ chẩn đoán nóng.
- Không chạy `all` lặp vô hạn mà không có rate limit.
- Không ghi raw classfile bytes, secrets hoặc đường dẫn nhạy cảm vào logs công khai.
- Không tự động gọi `System.gc()` để “chuẩn hóa” snapshot; nó không bảo đảm class unloading.

### 15.2. Bảo mật thông tin classpath

Danh sách class/module names, loại class loaders và tên plugin có thể làm lộ kiến trúc của hệ thống. Chỉ thu thập và chia sẻ với người có thẩm quyền, có chính sách lưu/truy cập output rõ ràng.

### 15.3. Kết quả thay đổi giữa những lần chạy

Số classes và identity hashes có thể đổi khi thay JDK build/vendor, flags, app dependencies, class loading timing hoặc thread scheduling. Hãy so sánh theo các invariants thiết yếu: có target classes mong muốn, loader role/identity nhất quán trong **cùng run**, và không nhầm classes với instances.

## 16. Các lỗi hay gặp

| Hiện tượng | Nguyên nhân/kiểm tra |
|---|---|
| JVM không thấy `Premain-Class` | Manifest trong JAR cuối sai, chưa rebuild hoặc sai binary class name |
| `NoClassDefFoundError` cho `LoadedClassAgent` | App mẫu gọi agent class nhưng JVM không nạp agent JAR/search path như mong đợi |
| `snapshot:scope=demo.app.` không thấy Helper | Có tạo Helper trước snapshot không? Class dùng đúng package/loader không? |
| In `loader=null` rồi coi là lỗi | Null chính là bootstrap defining loader |
| Hai bản ghi cùng tên | Kiểm tra có hai defining class loader identities khác nhau |
| `modifiable=false` cho `int[].class` | Hành vi chuẩn, array classes không modifiable |
| `modifiable=true` nhưng retransform lỗi | Global capability/manifest, VM support, schema và class eligibility |
| `getInitiatedClasses(system)` khác danh sách toàn JVM | Hai APIs có mục đích khác nhau; initiated không phải defining |
| `snapshot:selected` khác giữa runs | Snapshot timing/JDK version/app classloading thay đổi |
| `all` quá nhiều dòng | Dùng filter hoặc redirect output sang file bảo mật |
| Custom loader hash khác | Identity hash không persistent |
| Duplicate class name bị gộp trong map | Đừng dùng duy nhất tên làm class identity |
| Giữ cache snapshot lâu khiến class không unload | Strong references tới Class/loader có thể ngăn unloading |
| JVM báo `UnsupportedClassVersionError` | Compile thiếu `--release 17` hoặc runtime quá cũ |
| Class thấy trong snapshot nhưng không gọi method được | Loading không bảo đảm linkage/invocation mọi code path |
| `Class.forName(name)` không tìm ra hidden class | Hidden class không được khám phá như class thông thường |

### 16.1. Không suy luận loader từ package name

Không giả định tất cả `java.*` đều bootstrap và tất cả `com.example.*` đều system. Plugin, module layer, generated classes hoặc custom class loader có thể phá vỡ quy tắc đoán này. **Gọi `clazz.getClassLoader()` trên đúng Class object**.

### 16.2. Không nhầm array class và primitive class

Một class mảng `int[].class` và kiểu primitive `int.class` không modifiable, nhưng tên runtime/display khác nhau; việc `getAllLoadedClasses` có thể liệt kê các array classes không đồng nghĩa mọi primitive type cũng sẽ xuất hiện như một element có cùng kiểu tên. Bài dùng probes để kiểm tra chắc chắn.

### 16.3. Không xem loader hash là unique key tuyệt đối

`System.identityHashCode` có thể bị collision. Nếu công cụ cần bảng ID chính xác cho hai loader instances trong cùng snapshot, nên dùng `IdentityHashMap<ClassLoader, Integer>` và cấp IDs riêng, không map theo `ClassLoader.getClass().getName()`.

## 17. Bài tập thực hành và đáp án

### A. Ghi đủ ba thông tin cho từng class

Với từng `Class<?> c`, lấy name, defining loader và modifiable như thế nào?

**Đáp án:** `c.getName()`; `c.getClassLoader()` (xử lý null bootstrap); `inst.isModifiableClass(c)`.

### B. Tại sao getAllLoadedClasses không tự sort?

Tài liệu không bảo đảm thứ tự; muốn báo cáo dễ đọc phải tự sort và giữ loader identity làm tie breaker. **Không suy từ vị trí trong mảng là class được load sớm/muộn.**

### C. Tạo 100 Helper instances

Tạo 100 đối tượng `new Helper()` trong cùng class loader. Có 100 bản ghi `demo.app.Helper` không? **Không**. Snapshot chứa class identities, không chứa object instances.

### D. Thêm String[].class vào probe

Dự đoán `isModifiableClass(String[].class)`. **Đáp án:** false vì array class.

### E. Hai URLClassLoader cùng tên Widget

Tại sao `a.getName().equals(b.getName())` true nhưng `a == b` false? **Đáp án:** hai defining class loaders khác nhau tạo hai class identities độc lập.

### F. So getInitiatedClasses và getAllLoadedClasses

Có thể dùng `getInitiatedClasses(system)` để ghi rằng tất cả returned classes đều do system loader define không? **Không.** Initiating loader và defining loader khác nhau khi parent delegation.

### G. Modifiable true và capability false

Một lớp báo `modifiable=true` nhưng agent không có `Can-Retransform-Classes: true`. Có gọi `retransformClasses` chắc chắn được không? **Không**, phải kiểm tra global capability; cần thêm class eligibility và bytes hợp lệ.

### H. Thêm column Module

Bổ sung `c.getModule().getName()` vào report nhưng xử lý unnamed module `getName() == null`. Nó có thay thế loader identity không? **Không**.

### I. Cảnh báo về cache

Nếu giữ `Class<?>[]` trong một static field của agent suốt nhiều ngày, hệ quả có thể là gì? **Strong references có thể giữ classes/classloaders reachable**, làm khó class unloading.

### J. Dự đoán full output

Chạy `all` trên hai JVM/JDK versions khác nhau. Tại sao số dòng khác? **Vì snapshot timing, class loading graph, generated/hidden classes và runtime vendor/configuration khác nhau.**

### Câu hỏi nhanh

1. API lấy danh sách loaded classes? — `getAllLoadedClasses()`.
2. API lấy defining loader của một class? — `Class.getClassLoader()`.
3. Loader null có ý nghĩa gì? — Bootstrap.
4. API hỏi khả năng sửa của từng class? — `isModifiableClass(clazz)`.
5. Primitive/array class modifiable không? — Không.
6. Modifiable true đồng nghĩa capability redefine bật không? — Không.
7. Hai classes cùng tên có thể khác nhau không? — Có, khi defining loaders khác.
8. Snapshot có chứa hidden classes không? — Có theo Java SE 17.
9. `getInitiatedClasses` có đồng nghĩa defining loader không? — Không.
10. Liệt kê snapshot có sửa bytecode không? — Không.
11. Có nên match cứng tổng loaded classes ở CI không? — Không.
12. Có thể dùng `Class.forName` để tìm mọi hidden class từ tên không? — Không.
13. Một snapshot có tự cập nhật khi JVM load thêm class không? — Không.
14. Đầu ra `all` có thể lớn không? — Có, cần giới hạn/redirect.
15. Agent từ `premain` có thể chụp các classes đã load trước khi nó chạy không? — Có, API snapshot lấy những classes JVM đang load tại thời điểm gọi.

## 18. Checklist QA và triển khai

### Kiểm thử kỹ thuật

- [ ] Đã biên dịch agent bằng `javac --release 17`.
- [ ] JAR thực có `Premain-Class: demo.agent.LoadedClassAgent`.
- [ ] `-javaagent` có mặt trong command line chạy app.
- [ ] `premain` nhận `Instrumentation` và in `agent:ready`.
- [ ] `Main` đã nạp `Helper` trước khi gọi `dump`.
- [ ] `getAllLoadedClasses` được gọi đúng một lần tại thời điểm snapshot.
- [ ] Mỗi class được chọn có name, **defining loader**, `modifiable`.
- [ ] Đã xử lý `ClassLoader == null` thành bootstrap.
- [ ] Chế độ filtered in đúng app classes và hai probes false.
- [ ] Chế độ `all` thật sự in toàn bộ snapshot, không chỉ một sample.
- [ ] Các con số tổng không bị hardcode vào logic hoặc expected stdout cross-JVM.
- [ ] Thử hai URLClassLoader độc lập cho cùng một binary class name.
- [ ] Không gọi API sửa bytecode trong bài read-only này.
- [ ] Chạy với `-Xverify:all` và kiểm tra process exit 0.

### Trước khi áp dụng production

- [ ] Có quyền sử dụng agent/attach trên JVM đích.
- [ ] Giới hạn người được xem class inventory/report.
- [ ] Giới hạn số dòng logs, heap retention và tần suất snapshot.
- [ ] Không dùng `Class.forName` để quét lại mọi loaded class.
- [ ] Không lưu references mạnh `Class<?>`/ClassLoader vô hạn.
- [ ] Không gộp class identities theo tên đơn thuần.
- [ ] Chỉ dùng identity hash làm thông tin chẩn đoán tạm thời.
- [ ] Nếu muốn thật sự retransform/redefine, kiểm tra riêng capabilities/VM support/schema.
- [ ] Kiểm tra JVM version/vendor và loader/module topology thực tế.
- [ ] Dọn file inventory đúng retention/security policy.

## 19. Tổng kết và tài liệu tham khảo

Bài thực nghiệm **“Liệt kê lớp đã nạp cùng bộ nạp và khả năng sửa của từng lớp”** có lõi rất nhỏ:

~~~java
for (Class<?> c : inst.getAllLoadedClasses()) {
    ClassLoader loader = c.getClassLoader();
    boolean modifiable = inst.isModifiableClass(c);
    // Ghi tên c.getName(), loader và modifiable.
}
~~~

Từ ba lời gọi ấy, hiểu đúng semantics mới là trọng tâm:

- `getAllLoadedClasses` là snapshot toàn JVM, gồm hidden và array classes, không có thứ tự ổn định.
- `getClassLoader` trả **defining loader**, không phải nhất thiết initiating loader. Null nghĩa bootstrap.
- `isModifiableClass` là câu trả lời **theo từng class**, không phải trạng thái agent đã có retransform/redefine capability hay chưa. Primitive/array classes không modifiable.
- Class identity phụ thuộc **tên và loader**, nên hai classes cùng tên từ hai URLClassLoaders là hai classes khác nhau.

Bộ lab đã được biên dịch thành **Java 17 target**, chạy trên **JDK 24.0.2 với `-Xverify:all`**: filtered output có `demo.app.Helper` và `demo.app.Main` với `loader=system | modifiable=true`, các probes primitive/array false; mode `all` hiển thị cả bootstrap, hidden, array và nonmodifiable classes; phép thử hai URLClassLoaders xác nhận same-name true, same-class false. **Giữ nguyên tinh thần read-only của phép kiểm tra** trước khi mở rộng sang instrumentation thực sự.

Tài liệu chuẩn:

- [Java SE 17 — Instrumentation.getAllLoadedClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getAllLoadedClasses()): snapshot loaded classes, hidden classes/interfaces, array classes.
- [Java SE 17 — Instrumentation.isModifiableClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#isModifiableClass(java.lang.Class)): primitive/array restrictions và capability independence.
- [Java SE 17 — Instrumentation.getInitiatedClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getInitiatedClasses(java.lang.ClassLoader)): initiating loader và hidden-class khác biệt.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, manifest semantics.
- [Java SE 17 — Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()): defining loader và bootstrap null.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): system/platform/custom loaders.
- [JVMS 17 — Loading, Linking, Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity và defining loader.
- [JVM TI 17 — IsModifiableClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#IsModifiableClass): native API tương ứng để đào sâu.
