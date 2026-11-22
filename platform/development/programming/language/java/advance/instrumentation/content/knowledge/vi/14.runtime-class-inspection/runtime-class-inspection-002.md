# `getInitiatedClasses` phản ánh bộ nạp khởi xướng, không chỉ bộ nạp định nghĩa

Khi phân tích class loading trong Java instrumentation, hai câu hỏi nghe có vẻ giống nhau nhưng thực chất khác nhau:

1. **Defining loader**: class thực sự được **định nghĩa** bởi class loader nào?
2. **Initiating loader**: JVM đã ghi nhận những class loader nào **khởi xướng việc nạp** class đó, có thể bằng cách ủy quyền cho loader khác?

`Instrumentation.getInitiatedClasses(ClassLoader loader)` trả lời câu hỏi thứ hai. Một class do **parent loader định nghĩa** vẫn có thể nằm trong kết quả của **child loader** khi child đã khởi xướng việc nạp/liên kết và parent thực hiện định nghĩa.

Điểm sai phổ biến là lấy `getInitiatedClasses(child).length` rồi gọi đó là “số class child định nghĩa”. Điều đó không đúng theo hợp đồng JVM.

Bài này thuộc phần **Khảo sát khi chạy** của Java Advance — instrumentation. Nội dung gồm hợp đồng API Java 17, định nghĩa trong JVMS §5.3, ví dụ agent Java 17+ có kiểm chứng thực tế, sự khác nhau với `getAllLoadedClasses`, bootstrap/array/hidden classes, cách đọc output và các lỗi phân tích thường gặp.

## 1. Phân biệt ba API quan trọng

Trong một method của Java agent, khi đã có biến `Instrumentation inst`, `ClassLoader loader` và `Class<?> clazz`, ta có thể gọi:

```java
Class<?>[] initiated = inst.getInitiatedClasses(loader);
ClassLoader defining = clazz.getClassLoader();
Class<?>[] allLoaded = inst.getAllLoadedClasses();
```

Đây chỉ là **ba dòng minh họa** dùng biến đã khai báo, chưa phải chương trình độc lập.

| API | Câu hỏi trả lời | Lưu ý |
|---|---|---|
| `getInitiatedClasses(loader)` | Loader này đã được JVM ghi nhận là *initiating loader* của những class nào? | Class trả về **không nhất thiết** do loader này định nghĩa |
| `clazz.getClassLoader()` | Runtime class này có **defining loader** nào? | `null` biểu diễn bootstrap loader |
| `getAllLoadedClasses()` | Hiện JVM có những class nào đã load? | Phạm vi toàn JVM, có cả hidden classes và array classes |

Ví dụ kết quả hoàn toàn hợp lệ:

```text
defining loader của demo.Model = parent
demo.Model có trong getInitiatedClasses(child) = true
```

Hai dòng trên không mâu thuẫn. Chúng mô tả **hai quan hệ khác nhau của cùng một đối tượng `Class<?>`**.

## 2. Hợp đồng `getInitiatedClasses(ClassLoader)` của JDK 17

Chữ ký đầy đủ:

```java
Class<?>[] getInitiatedClasses(ClassLoader loader);
```

Method này thuộc interface `java.lang.instrument.Instrumentation`, trong module `java.instrument`. Theo Javadoc Oracle JDK 17, nó trả array các class mà JVM **đã ghi nhận** `loader` là initiating loader; đây là những class có thể được tìm theo tên qua các cơ chế như `ClassLoader.loadClass`, `Class.forName` và **bytecode linkage**.

Các điểm cần nhớ:

- Tham số là **đối tượng loader**, không phải tên class hoặc tên module.
- **Truyền `null` hợp lệ**: nó truy vấn các class được ghi nhận với **bootstrap class loader**, không phải mặc nhiên báo `NullPointerException`.
- Kết quả là mảng `Class<?>[]`; mảng có thể rỗng.
- Tập class được trả **không phải danh sách mọi class có thể tải về sau** từ URLs, JAR, classpath hoặc module path của loader.
- API **không tự load tất cả class** để tạo danh sách.
- Các class **hidden** và array class có element type là hidden class/interface **không được trả** vì không thể tìm bằng tên qua loader.
- API **không cam kết thứ tự theo thời gian nạp class**. Không được coi vị trí trong array là trình tự các lần `loadClass` hoặc instruction liên kết.
- Mảng trả về là dữ liệu tại một **thời điểm khảo sát**; các class có thể tiếp tục được load ở thread khác.

Nếu muốn khảo sát mà không biến đổi bytecode, bạn **không cần** gọi `addTransformer` hay `retransformClasses`. Chỉ cần một `Instrumentation` instance hợp lệ từ Java agent.

### 2.1. Làm sao lấy `Instrumentation`?

Thông thường JVM truyền nó vào điểm vào của agent:

```java
package agent;

import java.lang.instrument.Instrumentation;

public final class InspectAgent {
    public static void premain(String args, Instrumentation inst) {
        ClassLoader appLoader = ClassLoader.getSystemClassLoader();
        Class<?>[] snapshot = inst.getInitiatedClasses(appLoader);
        System.out.println("initiated count = " + snapshot.length);
    }
}
```

Đây là **class minh họa** chưa có manifest/launcher. Số đếm thay đổi tùy JVM, lúc class được resolve và các agent khác, nên không có stdout số cụ thể đáng tin cho mọi runtime.

Khi chạy với `-javaagent`, JAR phải có `Premain-Class: agent.InspectAgent`. Nếu dùng Attach API thì điểm vào là `agentmain`. `Instrumentation` không được tạo bằng một constructor public thông thường trong ứng dụng Java.

## 3. Theo Java Virtual Machine Specification: “define” và “initiate”

JVMS §5.3 mô tả hai hình thức nạp class:

- Nếu loader `L` **trực tiếp** tìm binary representation và khiến JVM định nghĩa class, `L` là **defining loader**.
- Nếu loader `L` **khởi xướng** việc nạp, trực tiếp hoặc **gián tiếp qua delegation**, `L` có thể được JVM ghi nhận là **initiating loader**.

Để định danh một runtime class `C`, ta có thể hình dung:

```text
<binaryName, definingLoader>
```

Ví dụ:

```text
<demo.Model, ParentLoader>
```

Hai loader có thể cùng initiate class này nhưng vẫn chỉ có **một runtime `Class<?>` object** với defining loader là `ParentLoader`.

### 3.1. Hình dung parent delegation

```text
                        ParentLoader
                           |
                    định nghĩa demo.Model
                           ^
                           |
                        ủy quyền
                           |
                        ChildLoader
                           |
                    định nghĩa demo.Entry
                           |
                           v
               Entry.invoke() gọi Model.value()
```

Khi JVM thực thi bytecode của `demo.Entry.invoke()`:

1. `Entry` đã được **ChildLoader** định nghĩa.
2. Bytecode của `Entry` tham chiếu `demo.Model`.
3. JVM cần resolve symbolic reference theo cơ chế class loading gắn với class `Entry`.
4. `ChildLoader` khởi xướng, ủy quyền cho `ParentLoader`.
5. `ParentLoader` định nghĩa (hoặc đã định nghĩa) `demo.Model`.
6. JVM ghi nhận quan hệ initiating thích hợp cho child và parent.

Sau sự kiện đó, có thể thấy:

| Runtime class | Defining loader | Initiating loaders được ghi nhận |
|---|---|---|
| `demo.Entry` | ChildLoader | ChildLoader |
| `demo.Model` | ParentLoader | ParentLoader **và** ChildLoader |

Đây là mô hình trung tâm của bài: **một class của parent xuất hiện trong initiated set của child** mà child **không** định nghĩa class.

### 3.2. Một defining loader, có thể nhiều initiating loaders

Nếu child ủy quyền cho parent, hai lời gọi:

```java
Class<?> a = parent.loadClass("demo.Model");
Class<?> b = child.loadClass("demo.Model");
System.out.println(a == b);
```

là **trích đoạn** trong bối cảnh `parent` và `child` đã tồn tại. Với parent-first delegation của ví dụ, kết quả là `true`: không có hai bản `demo.Model`.

Ngược lại, khi hai class loader **độc lập** tự định nghĩa cùng một binary name:

```text
<demo.Model, LoaderA> != <demo.Model, LoaderB>
```

Chúng là hai runtime types khác nhau. So `Class.getName()` đơn thuần không đủ; khi cần đúng identity phải so `Class<?>` bằng `==` và ghi defining loader.

### 3.3. Loader ở giữa chuỗi delegation không mặc nhiên đều là initiator

JVMS §5.3 còn nhấn mạnh một chi tiết:

```text
L1 (khởi xướng) -> Lmiddle -> L2 (định nghĩa)
```

Theo đặc tả, những loader **trung gian** giữa loader khởi xướng `L1` và loader định nghĩa `L2` **không tự động** được coi là initiating loaders của class đó. Một loader trung gian có thể có quan hệ initiating do **sự kiện khởi xướng khác**, nhưng không được suy ra điều này chỉ vì nó nằm trên parent chain.

Vì vậy `getInitiatedClasses(loader)` không phải phép lấy **tất cả class của loader và toàn bộ tổ tiên**. Nó phản ánh **quan hệ initiating đã được JVM ghi nhận**.

## 4. Ví dụ Java 17+ chạy được, có cả defining và initiating

Bài thực hành tạo một **startup Java agent** để có `Instrumentation`. Ta bố trí hai `URLClassLoader`:

- `parent`: nhìn thấy `out/model`, chứa `demo.Model`.
- `child`: nhìn thấy `out/child`, chứa `demo.Entry`, và có parent là `parent`.
- `Entry.invoke()` thực thi lệnh gọi tới `Model.value()`. Đây là đường **bytecode linkage** giúp child initiate Model.

Ngoài ra có một application launcher đơn giản để JVM chạy `main()` sau khi `premain` hoàn tất.

### 4.1. Cấu trúc thư mục

```text
initiated-demo/
├── src/
│   ├── demo/
│   │   └── Model.java
│   ├── child/
│   │   └── demo/
│   │       └── Entry.java
│   ├── probe/
│   │   └── Probe.java
│   └── App.java
├── agent.mf
├── out/
│   ├── model/
│   ├── child/
│   └── agent/
└── probe-agent.jar
```

`out` và `probe-agent.jar` là output, được tạo sau bước biên dịch/đóng JAR. **Không** đưa `out/model` hoặc `out/child` vào runtime `-cp`; chương trình sẽ tạo loader riêng cho chúng.

### 4.2. File `src/demo/Model.java`

```java
package demo;

public final class Model {
    public static String value() {
        return "ok";
    }
}
```

`Model` không phụ thuộc code khác của ứng dụng. Nó nằm trong thư mục mà **chỉ `parent` được cấp URL tìm kiếm**.

### 4.3. File `src/child/demo/Entry.java`

```java
package demo;

public final class Entry {
    public static String invoke() {
        return Model.value();
    }
}
```

Vì hai class cùng package name trong mã nguồn, `Entry` không cần dòng import `Model`. Lời gọi `Model.value()` trở thành **symbolic reference** trong bytecode của `Entry`. Khi JVM resolve nó từ `Entry` do child định nghĩa, parent có thể cung cấp `Model`.

`Model.value()` là `public static`, nên hai class thuộc **runtime packages khác nhau** (defining loaders khác nhau) vẫn có thể gọi hợp lệ; không dựa vào package-private access.

### 4.4. File `src/probe/Probe.java`

```java
package probe;

import java.lang.instrument.Instrumentation;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Probe {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        URL[] parentUrls = {
                Path.of("out", "model")
                        .toAbsolutePath().toUri().toURL()
        };
        URL[] childUrls = {
                Path.of("out", "child")
                        .toAbsolutePath().toUri().toURL()
        };

        try (URLClassLoader parent =
                     new URLClassLoader(parentUrls, null);
             URLClassLoader child =
                     new URLClassLoader(childUrls, parent)) {

            System.out.println("[agent] beforeChildModel="
                    + contains(inst.getInitiatedClasses(child),
                            "demo.Model"));

            Class<?> entry =
                    Class.forName("demo.Entry", true, child);

            System.out.println("[agent] entryDefinedChild="
                    + (entry.getClassLoader() == child));

            System.out.println("[agent] result="
                    + entry.getMethod("invoke").invoke(null));

            Class<?> model = parent.loadClass("demo.Model");

            System.out.println("[agent] modelDefinedParent="
                    + (model.getClassLoader() == parent));

            System.out.println("[agent] modelInitiatedChild="
                    + has(inst.getInitiatedClasses(child), model));

            System.out.println("[agent] modelInitiatedParent="
                    + has(inst.getInitiatedClasses(parent), model));

            System.out.println("[agent] modelFoundByChild="
                    + (child.loadClass("demo.Model") == model));

            System.out.println("[agent] modelDefinedChild="
                    + (model.getClassLoader() == child));
        }
    }

    private static boolean has(Class<?>[] classes, Class<?> wanted) {
        for (Class<?> c : classes) {
            if (c == wanted) {
                return true;
            }
        }
        return false;
    }

    private static boolean contains(Class<?>[] classes, String binaryName) {
        for (Class<?> c : classes) {
            if (c.getName().equals(binaryName)) {
                return true;
            }
        }
        return false;
    }
}
```

`Probe` là **file độc lập đầy đủ**. Nó không dùng ASM hay Byte Buddy. Helper `has` so sánh bằng **object identity** (`==`), tránh gộp nhầm hai class khác loader nhưng trùng tên. Helper `contains` dùng `getName()` chỉ vì nó đang hỏi “trước bước thử, class có **tên này** đã xuất hiện chưa?”.

### 4.5. Chi tiết quan trọng trong code

**Tạo hai loader:**

```java
new URLClassLoader(parentUrls, null);
new URLClassLoader(childUrls, parent);
```

Đối số thứ hai của constructor `URLClassLoader` là **parent loader**. Trong loader đầu, `null` đặt bootstrap làm parent ở tầng cơ chế tìm kiếm; trong loader thứ hai, parent là URLClassLoader vừa tạo. Parent chỉ thấy file trong `out/model`, child chỉ có URL tới `out/child`.

**Đo thời điểm trước:**

```java
contains(inst.getInitiatedClasses(child), "demo.Model")
```

Ở fixture này, trước lời gọi có chủ đích từ `Entry`, child chưa initiate `Model`.

**Nạp class `Entry`:**

```java
Class.forName("demo.Entry", true, child);
```

Parent không có file `Entry`, nên child tìm và định nghĩa từ `out/child`. Lưu ý code không dùng `Entry.class` trong agent, vì điều đó dễ vô tình nhờ system loader thay vì child.

**Thực thi bytecode thuộc child:**

```java
entry.getMethod("invoke").invoke(null);
```

Trong `Entry.invoke()` có tham chiếu `Model.value()`; JVM resolve `Model` qua child -> parent. Đây là điểm then chốt mà một phép dò tên class đơn thuần không thay thế được.

**Kiểm tra hai quan hệ:**

```java
model.getClassLoader() == parent;
has(inst.getInitiatedClasses(child), model);
```

Hai biểu thức có thể đồng thời là `true`, cho thấy child initiate mà parent define.

### 4.6. File `src/App.java`

```java
public class App {
    public static void main(String[] args) {
        System.out.println("[app] done");
    }
}
```

`App` không import hoặc gọi `Model`, `Entry`, vì vậy không can thiệp vào trình tự nạp lớp mà agent đang khảo sát.

### 4.7. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: probe.Probe

```

`Premain-Class` trỏ đúng class agent. Giữ một dòng trống cuối main section của manifest. Vì agent **chỉ quan sát** chứ không retransform/redefine, không cần khai báo capability `Can-Retransform-Classes`.

### 4.8. Biên dịch và đóng JAR

Mở terminal tại thư mục `initiated-demo` và dùng **JDK 17+**:

```bash
mkdir out
mkdir out/model
mkdir out/child
mkdir out/agent
```

Chỉ cần tạo thư mục lần đầu. Biên dịch theo thứ tự:

```bash
javac --release 17 -encoding UTF-8 -d out/model src/demo/Model.java

javac --release 17 -encoding UTF-8 -cp out/model -d out/child src/child/demo/Entry.java

javac --release 17 -encoding UTF-8 -d out/agent src/probe/Probe.java src/App.java
```

**Vì sao compile-time `-cp out/model` ở lệnh thứ hai không phá thí nghiệm?** Compiler cần thấy `Model` để kiểm tra method `value()`, nhưng `.class` của `Entry` vẫn được lưu **riêng** ở `out/child`. Ở runtime, `Model` chỉ được cấp cho loader `parent`.

Tạo agent JAR:

```bash
jar --create --file probe-agent.jar --manifest agent.mf -C out/agent probe/Probe.class
```

Trong agent JAR chỉ cần `probe/Probe.class` cùng manifest. `App.class` được load từ `out/agent` khi JVM chạy application; không bắt buộc đóng vào agent JAR.

### 4.9. Chạy và đọc stdout

```bash
java -javaagent:probe-agent.jar -cp out/agent App
```

**Stdout thực nghiệm trên OpenJDK 24.0.2, source biên dịch với `javac --release 17`:**

```text
[agent] beforeChildModel=false
[agent] entryDefinedChild=true
[agent] result=ok
[agent] modelDefinedParent=true
[agent] modelInitiatedChild=true
[agent] modelInitiatedParent=true
[agent] modelFoundByChild=true
[agent] modelDefinedChild=false
[app] done
```

Đây là **chín dòng stdout** của fixture đã thử. Tùy JVM bạn có thể thấy thông tin VM bổ sung trên stderr; đừng gộp stderr diagnostic vào stdout chuẩn của ví dụ.

| Dòng | Giải thích |
|---|---|
| `beforeChildModel=false` | Chưa có bản ghi initiation của child cho Model tại snapshot ban đầu |
| `entryDefinedChild=true` | Child định nghĩa Entry |
| `result=ok` | Bytecode của Entry đã thực thi `Model.value()` |
| `modelDefinedParent=true` | Parent định nghĩa Model |
| `modelInitiatedChild=true` | **Child là initiating loader của chính class Model đó** |
| `modelInitiatedParent=true` | Parent cũng là initiating loader |
| `modelFoundByChild=true` | Child lookup trả cùng `Class<?>` mà parent định nghĩa |
| `modelDefinedChild=false` | Child **không** trực tiếp định nghĩa Model |
| `app done` | Launcher tiếp tục sau khi agent hoàn tất |

Kết luận thực nghiệm: **`modelInitiatedChild=true` trong khi `modelDefinedChild=false`**. Vì vậy **không thể** lấy danh sách `getInitiatedClasses(child)` để khẳng định mọi class trong đó là “class của child” theo nghĩa defining loader.

### 4.10. Vì sao dùng bytecode linkage thay vì chỉ gọi `child.loadClass`?

Một chi tiết khó là việc **gọi một Java method `loadClass` và nhận được `Class<?>`** không nhất thiết đồng nghĩa JVM đã ghi nhận một bản ghi initiating cho chính loader đó ngay lúc bạn kiểm tra.

Trong thử nghiệm phụ trên OpenJDK 24.0.2, nếu agent gọi `child.loadClass("demo.Model")` **trực tiếp** mà không có symbolic resolution thuộc class do child định nghĩa, loader con có thể **trả về** class của parent nhưng `getInitiatedClasses(child)` vẫn **không** chứa nó. Điều này phản ánh việc API được định nghĩa theo **bản ghi initiating loader ở JVM**, chứ không phải bộ đếm mọi lời gọi `loadClass` trong Java code.

Vì vậy demo chính dùng `Entry.invoke()` để tạo symbolic reference **bên trong class do child định nghĩa**, rồi quan sát trạng thái sau linkage. Không ngoại suy rằng mọi cách gọi `loadClass` ở mọi JVM đều phải cho output initiated-set giống nhau.

## 5. Bootstrap loader: truyền `null` là hợp lệ

Javadoc `Instrumentation.getInitiatedClasses` quy định:

```java
Class<?>[] fromBootstrap = inst.getInitiatedClasses(null);
```

Ở đây `null` **đại diện bootstrap class loader**. Không giống các method khác vốn từ chối null, API này chấp nhận null có chủ ý.

Ví dụ so sánh:

```java
Class<?>[] bootstrap = inst.getInitiatedClasses(null);
Class<?>[] system = inst.getInitiatedClasses(
        ClassLoader.getSystemClassLoader());
```

Đây là đoạn trong một agent method có `inst`; hai mảng **không bắt buộc bằng nhau**. Một class như `java.lang.String` do bootstrap định nghĩa, nhưng system/child loaders vẫn có thể initiate các references tới nó.

`Class.getClassLoader()` cũng có quy ước `null` cho class do bootstrap định nghĩa:

```java
boolean stringDefinedByBootstrap =
        String.class.getClassLoader() == null;
```

Đừng thay `getInitiatedClasses(null)` bằng `getInitiatedClasses(ClassLoader.getSystemClassLoader())` chỉ vì hai nhóm có thể có nhiều phần tử chung.

## 6. Khác biệt với `getAllLoadedClasses`

`Instrumentation.getAllLoadedClasses()` trả mảng class đang load trong JVM. Nó phù hợp cho **runtime inventory**, không phải riêng quan hệ của một initiating loader.

```java
Class<?>[] all = inst.getAllLoadedClasses();
Class<?>[] initiatedByChild = inst.getInitiatedClasses(child);
```

Hai array có thể chứa phần tử giống nhau, nhưng **không thể coi chúng là hai phiên bản với cùng phạm vi**.

| Đặc điểm | `getAllLoadedClasses()` | `getInitiatedClasses(loader)` |
|---|---|---|
| Scope | Toàn JVM | Một initiating loader |
| Tham số | Không | Một `ClassLoader` hoặc `null` |
| Phản ánh class do parent define nhưng child initiate | Có thể có | Có thể có khi truy vấn child |
| Hidden classes/interfaces | Có, theo Javadoc Java 17 | Không |
| Array classes | Bao gồm các array classes mọi loại | Có thể bao gồm các array tìm được theo tên; loại trừ hidden-element arrays |
| Tương đương danh sách file trong JAR? | Không | Không |
| Có thứ tự thời gian sự kiện? | Không được bảo đảm | Không được bảo đảm |
| Dùng để kết luận defining loader? | Phải lọc `getClassLoader()` | **Không** chỉ dựa vào membership |

Nếu cần **những class thực sự được loader định nghĩa**, hãy lọc **`Class.getClassLoader()`**, nhưng nhớ `getInitiatedClasses` không bao gồm hidden classes nên lọc nó sẽ **không** cho inventory đầy đủ mọi class đặc biệt.

### 6.1. Thống kê `defined here` và `initiated elsewhere`

Một cách diễn giải rõ ràng:

```java
Class<?>[] classes = inst.getInitiatedClasses(loader);

long definedHere = java.util.Arrays.stream(classes)
        .filter(c -> c.getClassLoader() == loader)
        .count();

long initiatedButDefinedElsewhere =
        java.util.Arrays.stream(classes)
                .filter(c -> c.getClassLoader() != loader)
                .count();
```

Đây là **trích đoạn** có `inst`, `loader`. `definedHere` là số phần tử **trong initiated set này** mà defining loader cũng bằng loader được hỏi. `initiatedButDefinedElsewhere` phản ánh những class do parent/bootstrap/loader khác định nghĩa.

Không coi tổng hai nhóm này là số lượng class của JAR, số lượng class mà JVM có thể nạp, hoặc tổng object của ứng dụng. Một class có thể xuất hiện trong **nhiều initiated sets**, nên cộng số lượng các loader sẽ dẫn đến **double counting** nếu đang đếm distinct class objects.

## 7. Array classes: lớp mảng có defining loader theo component type

Array class không có `.class` file thông thường để `URLClassLoader` đọc; nó được JVM tạo theo quy tắc §5.3.3.

- Array có **reference component type**: defining loader bằng defining loader của component type.
- Array có **primitive component type**: defining loader được coi là bootstrap.
- JVM cũng có thể ghi nhận initiating loader cho array class khi một loader khởi xướng quá trình tạo/resolve nó.

Ví dụ:

```java
System.out.println(String[].class.getClassLoader() == null);
System.out.println(int[].class.getClassLoader() == null);
```

Đây có thể đặt trong một `main`; với JVM thông thường, cả hai dòng là `true`. `String` và `String[]` được gắn với bootstrap; primitive array `int[]` cũng được gắn với bootstrap.

Nếu `demo.Model` được parent định nghĩa, thì array type của nó cũng có defining loader dựa theo `Model`. Tuy nhiên **đừng suy rằng array type đã nằm trong initiated set của child chỉ vì `Model` đã ở đó**: cần xem array có thực sự được JVM tạo/resolve trong context tương ứng hay chưa.

## 8. Hidden classes: giới hạn cố ý của danh sách initiating

Javadoc Oracle Java 17 cho biết `getInitiatedClasses` **không** bao gồm:

- Hidden classes và hidden interfaces.
- Array classes có hidden class/interface làm element type.

Chúng không được tìm bằng tên qua loader theo cách thông thường. Vì vậy một công cụ diagnostic muốn thấy **mọi class hiện đang tồn tại** có thể cần `getAllLoadedClasses()` hoặc JVMTI/JFR theo phạm vi và mục tiêu cụ thể.

Đừng diễn giải “hidden class không nằm trong `getInitiatedClasses(loader)`” thành “JVM không có class đó” hoặc “loader không liên quan gì tới nó”. Đây là **giới hạn theo định nghĩa API**.

## 9. Module không thay thế khái niệm loader

Từ Java 9, cùng một runtime class còn thuộc một `java.lang.Module`:

```java
ClassLoader defining = clazz.getClassLoader();
Module runtimeModule = clazz.getModule();
```

Đây là đoạn minh họa với biến `clazz`. Cần giữ ba thuộc tính riêng:

1. **Defining loader:** ai tạo runtime class.
2. **Initiating loader(s):** ai đã được JVM ghi nhận khởi xướng nạp class.
3. **Runtime module:** class thuộc module nào.

`getInitiatedClasses(child)` chứa một class **không** có nghĩa class đó nằm trong unnamed module của child. Với demo, `demo.Model` thuộc module do defining loader parent quản lý, trong khi `demo.Entry` thuộc module của child.

Java access control còn xét module readability, `exports` và `opens` riêng. Không sử dụng initiating membership để suy ra quyền reflection hoặc quyền link tới non-exported package.

## 10. Snapshot không phải event stream

Đối chiếu trước và sau một lời gọi có ích:

```text
T0: child chưa initiate demo.Model
T1: JVM resolve Model từ Entry.invoke()
T2: child đã initiate demo.Model
```

Nhưng đây không phải timeline class loading tự động. `getInitiatedClasses` không trả timestamp, stack trace, nguyên nhân, thread ID hay thứ tự phần tử theo thời gian.

Trong JVM nhiều thread, các class khác có thể được load giữa hai lần gọi; class unloading cũng có thể làm kết quả quan sát về sau thay đổi. Nếu cần timeline thật sự, hãy dùng JFR/JVMTI class-loading events hoặc cơ chế logging/instrumentation thích hợp, rồi kết hợp kết quả snapshot để phân tích.

### 10.1. Thiết kế bảng diagnostic đúng

Nếu UI hiển thị class initiated bởi loader child, nên tách các trường:

| Trường | Ví dụ |
|---|---|
| Class binary name | `demo.Model` |
| Initiating loader được truy vấn | ChildLoader |
| Defining loader thực tế | ParentLoader |
| Module | Unnamed module của ParentLoader |
| Có phải defining == initiating? | `false` |
| Observation time | Thời điểm snapshot do công cụ ghi |
| Class identity | `Class<?>` reference/identifier ổn định trong phép đo |

Nếu nhãn UI chỉ ghi “Classes owned by ChildLoader” cho toàn bộ kết quả `getInitiatedClasses(child)`, nó có thể gây sai lệch điều tra memory leak, classloader retention và dependency graph.

## 11. Khi debugging class loaders, không suy từ một chỉ số đơn lẻ

Các triệu chứng thường gặp:

| Quan sát | Giải thích / hướng kiểm tra |
|---|---|
| Class của parent xuất hiện trong child initiated list | Có thể do child khởi xướng và delegate đúng quy tắc |
| `getInitiatedClasses(child)` không chứa một class tồn tại trên parent | Child chưa được JVM ghi nhận initiate; không đủ chứng minh parent không thể load |
| Hai loader initiated cùng một `Class<?>` | Không có nghĩa JVM tạo hai runtime class objects |
| Hai class có cùng `getName()` nhưng `== false` | Có thể do defining loader khác nhau |
| `ClassNotFoundException` | Loader không tìm được class theo đường được hỏi |
| `NoClassDefFoundError` khi method chạy | Symbolic reference hoặc dependency không resolve được |
| `LinkageError` | Có thể liên quan loading constraints, liên kết hoặc class identity |
| `ClassCastException` với tên class giống nhau | Khả năng tồn tại hai runtime types khác defining loaders |
| Số initiated giảm/tăng giữa snapshots | Class loading/unloading và thời điểm quan sát khác nhau; đừng suy sự kiện từ số đếm |
| Thấy bootstrap-defined class trong child initiated set | Không mâu thuẫn: defining loader khác initiating loader |

Để điều tra kỹ, ghi lại:

- Tên class và **`Class<?>` identity**.
- `Class.getClassLoader()` và loader đang được hỏi bằng `getInitiatedClasses`.
- Loader parent/delegation chain thực tế.
- Module và runtime package nếu lỗi access.
- Class loading time/stack evidence nếu có.
- JVM/JDK version và các agent đang bật.
- Các exception gốc, stack trace và class loader context.

**Đừng** dùng `getInitiatedClasses` để kết luận loader leak chỉ vì số lượng class được initiate lớn. Parent-delegated classes có thể làm số này lớn mà không phải child đang định nghĩa hoặc giữ độc quyền các class đó.

## 12. Nhầm lẫn thường gặp và cách sửa

### Nhầm lẫn 1 — “Initiated nghĩa là tự gọi `defineClass`”

Không đúng. Initiation có thể đi qua delegation và được loader khác định nghĩa.

### Nhầm lẫn 2 — “Một class chỉ có một initiating loader”

Không đúng. Một runtime class có một **defining loader** nhưng JVM có thể ghi nhận **nhiều initiating loaders**.

### Nhầm lẫn 3 — “Parent luôn chứa mọi initiated class của child”

Không được suy ra như vậy. Cần xét defining loader, delegation path thực tế và quy tắc ghi nhận initiating của JVMS. Các loader trung gian cũng không tự động có bản ghi.

### Nhầm lẫn 4 — “Có thể nạp từ classpath thì phải nằm trong initiated set”

Không đúng. Loader có thể có quyền tìm file `.class` nhưng JVM chưa từng khởi xướng load class đó.

### Nhầm lẫn 5 — “Mọi lời gọi Java `loadClass()` đều tăng initiating set”

Không nên giả định. Thí nghiệm phụ trên OpenJDK 24.0.2 cho thấy direct `loadClass` từ agent và JVM bytecode linkage từ class do child định nghĩa có thể cho initiated-set observations khác nhau.

### Nhầm lẫn 6 — “Mảng `getInitiatedClasses` có thứ tự thời gian”

Không có cam kết đó; đừng dùng index của mảng làm timestamp.

### Nhầm lẫn 7 — “`getInitiatedClasses(null)` tương đương system loader”

Sai. `null` có nghĩa **bootstrap loader**.

### Nhầm lẫn 8 — “Hidden classes chắc chắn xuất hiện trong initiated set”

Sai. Javadoc Java 17 loại trừ hidden classes/interfaces và arrays có hidden element.

### Nhầm lẫn 9 — “Tổng các initiated array lengths là tổng class duy nhất”

Sai vì một class có thể được initiate bởi nhiều loader, dẫn tới double count.

### Nhầm lẫn 10 — “Defining loader thay đổi sau khi child initiate”

Không. Một class object được gắn với defining loader. Delegation không viết lại defining identity.

## 13. Bài tập kiểm tra kiến thức

**1.** `demo.Model` được parent định nghĩa, child initiate bằng delegation. Nó có thể nằm trong `getInitiatedClasses(child)` không?

**Đáp án:** Có. Đó là mục tiêu của API.

**2.** `model.getClassLoader() == parent` và `getInitiatedClasses(child)` chứa `model` có thể đồng thời đúng không?

**Đáp án:** Có. Defining và initiating là hai quan hệ khác nhau.

**3.** Muốn biết ai thực sự định nghĩa `Class<?> clazz`, dùng method nào?

**Đáp án:** `clazz.getClassLoader()`; `null` đại diện bootstrap loader.

**4.** Muốn lấy inventory class toàn JVM, dùng method nào?

**Đáp án:** `Instrumentation.getAllLoadedClasses()`; không đồng nhất nó với initiated set.

**5.** Truyền `null` vào `getInitiatedClasses` có ý nghĩa gì?

**Đáp án:** Truy vấn các class có bootstrap loader là initiating loader.

**6.** Vì sao `Entry.invoke()` được dùng để tạo bằng chứng mạnh về initiating?

**Đáp án:** Vì có symbolic reference tới `demo.Model` trong bytecode của `Entry` do child định nghĩa; JVM phải thực hiện class resolution ở context này.

**7.** Vì sao `modelFoundByChild=true` không chứng minh child define class?

**Đáp án:** Child có thể ủy quyền cho parent và nhận cùng `Class<?>` do parent định nghĩa.

**8.** Nếu hai loader độc lập cùng định nghĩa `demo.Model`, so hai `getName()` có đủ để biết chúng là một type không?

**Đáp án:** Không. Phải xem defining loaders hoặc so `Class<?>` identity.

**9.** `getInitiatedClasses` có chứa hidden classes không?

**Đáp án:** Không, theo Java 17 API.

**10.** Loader ở giữa delegation chain có tự động được ghi nhận initiating không?

**Đáp án:** Không mặc nhiên. JVMS nêu rõ các loader trung gian không tự động là initiating chỉ vì ở trên đường ủy quyền.

**11.** Có được cộng initiated counts của parent và child làm số class duy nhất không?

**Đáp án:** Không. Một `Class<?>` có thể nằm trong nhiều initiated sets.

**12.** Class có trên filesystem nhưng chưa từng được JVM yêu cầu load/resolve, initiated set có chắc chứa nó không?

**Đáp án:** Không; classpath availability khác initiating record.

## 14. Checklist triển khai công cụ khảo sát

| Kiểm tra | Ý nghĩa |
|---|---|
| Dùng `Instrumentation` từ `premain`/`agentmain` | API hợp lệ, không cần transformer |
| Ghi binary name **và** class identity | Không gộp sai các class trùng tên |
| Ghi defining loader qua `getClassLoader()` | Tránh gọi initiated list là “owned classes” |
| Ghi initiating loader được truy vấn | Biết bảng đang nói về loader nào |
| Hỗ trợ `null` cho bootstrap | Không báo lỗi sai |
| Xem parent delegation và actual linkage | Giải thích vì sao child initiate class của parent |
| Không tự thêm mọi intermediate loader | Tuân thủ JVMS §5.3 |
| Không dùng initiated count làm class count | Tránh double count |
| Kết hợp `getAllLoadedClasses` khi cần inventory | Nhìn toàn JVM |
| Lưu ý hidden/array exclusions | Biết phạm vi API |
| Không giả định thứ tự array là thời gian | Tránh suy luận timeline sai |
| Kiểm chứng bằng thí nghiệm classloader rõ ràng | Tránh lỗi do system loader vô tình nhìn thấy class |
| Không coi mỗi lời gọi `loadClass` là JVM initiating event | Giữ phân biệt giữa Java call và VM record |

## 15. Kết luận

- `getInitiatedClasses(loader)` trả về class mà JVM đã **ghi nhận loader là initiating**, không phải chỉ những class **do loader định nghĩa**.
- Defining loader của `Class<?>` được biết qua `clazz.getClassLoader()`. Một class có **một defining loader** nhưng có thể có **nhiều initiating loaders**.
- Với parent delegation, **child có thể initiate `demo.Model` dù parent định nghĩa class này**.
- Thí nghiệm đã chứng minh `modelInitiatedChild=true` đồng thời `modelDefinedChild=false` bằng **JVM bytecode linkage**.
- `getInitiatedClasses(null)` quan sát bootstrap loader; `getAllLoadedClasses()` cung cấp inventory rộng hơn và bao gồm hidden classes.
- Initiating set không phải danh sách JAR/classpath, không phải timeline và không có cùng ý nghĩa với module ownership.
- Để phân tích runtime chính xác, luôn đối chiếu **class identity, defining loader, initiating loader, module và thời điểm khảo sát**.

## Tài liệu tham khảo chính thức

- Oracle JDK 17 — [`Instrumentation.getInitiatedClasses` và `getAllLoadedClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java SE 17 — [JVMS §5.3: Creation and Loading, defining/initiating loaders](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3).
- Oracle Java SE 17 — [JVMS §5.3.2: Loading Using a User-defined Class Loader](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.2).
- Oracle Java SE 17 — [JVMS §5.3.3: Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.3).
- Oracle Java SE 17 — [JVMS §5.3.4: Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4).
- Oracle JDK 17 — [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html).
- Oracle JDK 17 — [`Class.getClassLoader()` và `Class.getModule()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- Oracle JDK 17 — [Java agent package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
