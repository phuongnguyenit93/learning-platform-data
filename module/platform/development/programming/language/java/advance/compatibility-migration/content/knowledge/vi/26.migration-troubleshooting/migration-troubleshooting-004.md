# AbstractMethodError và IncompatibleClassChangeError

Trong **Java Advance Compatibility Migration**, một ứng dụng có thể **biên dịch thành công** nhưng khi chạy trên môi trường tích hợp hoặc production lại phát sinh `java.lang.AbstractMethodError` hoặc `java.lang.IncompatibleClassChangeError`. Những lỗi này thường xuất hiện khi mã đã được biên dịch dựa trên **một phiên bản hợp đồng nhị phân** của class/interface, nhưng JVM lại nạp một phiên bản khác khi thực thi.

Ví dụ, một module mới gọi phương thức vừa bổ sung vào interface, trong khi implementation cũ chưa được biên dịch lại; hoặc client cũ dùng bytecode gọi **instance method** nhưng phiên bản thư viện được deploy đã đổi phương thức đó thành **static**. Kết quả không nhất thiết biểu hiện dưới dạng compile error, vì từng artifact có thể đã được compile thành công ở các thời điểm khác nhau.

Đây là bài học thuộc chương **Chẩn đoán lỗi** của module **Java Advance Compatibility Migration**. Nội dung sẽ phân biệt chính xác hai lỗi, giải thích vì sao chúng nằm trong họ `LinkageError`, cách JVM resolve/chọn method, những kịch bản migration thực tế, các ví dụ biên dịch lệch phiên bản có thể tái hiện, quy trình tìm JAR/class thực tế được nạp, cách dùng `javap`, Gradle, Maven và các biện pháp phòng ngừa.

**Thông điệp cốt lõi:** đừng tự kết luận “JDK mới có lỗi” chỉ vì exception xuất hiện ngay sau nâng Java. Trước hết phải kiểm tra **ABI (Application Binary Interface)**, dependency graph, class loader và phiên bản runtime của mọi artifact tham gia lời gọi.

## 1. Hai lỗi là gì?

`AbstractMethodError` xuất hiện khi chương trình cố thực thi một phương thức cần có implementation cụ thể, nhưng theo method resolution/selection ở runtime **không tìm được implementation concrete phù hợp**. Một tình huống phổ biến là interface mới có thêm abstract method còn class implementation vẫn là binary cũ.

`IncompatibleClassChangeError` là lỗi cho biết một class hoặc member được JVM sử dụng theo cách **không còn phù hợp với dạng nhị phân thực tế**. Ví dụ client bytecode gọi một phương thức như instance method, nhưng class được nạp chỉ có phiên bản tương ứng là static method.

Quan hệ kế thừa:

~~~text
java.lang.Throwable
        |
        +-- java.lang.Error
                |
                +-- java.lang.LinkageError
                        |
                        +-- IncompatibleClassChangeError
                        |       |
                        |       +-- AbstractMethodError
                        |       +-- NoSuchMethodError
                        |       +-- NoSuchFieldError
                        |       +-- IllegalAccessError
                        |       +-- ...
                        |
                        +-- ClassFormatError
                        +-- VerifyError
                        +-- UnsupportedClassVersionError
                        +-- ...
~~~

Sơ đồ minh họa các nhánh liên quan trong hệ thống phân cấp. Điều quan trọng là **`AbstractMethodError` là một subclass của `IncompatibleClassChangeError`**, nên nếu chỉ nhìn một tên exception cấp cha mà không xem concrete subtype và stack trace thì rất dễ chẩn đoán sai.

### 1.1. Vì sao chúng là Error, không phải Exception?

Cả hai đều thuộc nhánh `Error`, thường cho thấy **môi trường runtime và những class files hiện có không khớp giả định liên kết** của mã đã biên dịch. Đây không phải lỗi validation input thông thường để ứng dụng bắt rồi tiếp tục xử lý.

Không nên chữa bằng:

~~~java
try {
    service.execute();
} catch (IncompatibleClassChangeError error) {
    // Bỏ qua để ứng dụng tiếp tục?
}
~~~

Việc nuốt lỗi có thể che một dependency conflict hệ thống. Hướng sửa là **đồng bộ hợp đồng nhị phân và artifacts**, trừ những trường hợp đặc biệt có thiết kế fallback rõ ràng và đã được kiểm thử.

## 2. Linkage trong vòng đời của class

Cần phân biệt bốn giai đoạn:

1. **Loading:** JVM/class loader tìm class bytes và tạo class representation.
2. **Linking:** bao gồm verification, preparation và resolution (resolution có thể thực hiện theo nhu cầu).
3. **Initialization:** chạy static initializers theo các quy tắc Java.
4. **Execution:** bytecode thực thi, trong đó các method invocation/field access có thể kích hoạt resolution hoặc selection.

Sơ đồ:

~~~text
Source A.java / B.java
          |
          | javac tại thời điểm T1
          v
       .class files
          |
          | JAR / WAR / runtime classpath tại T2
          v
   Class loader tìm class thực tế
          |
          v
   Verification / resolution
          |
          v
   Method / field invocation
          |
          +--> hợp đồng nhị phân phù hợp -> chạy
          |
          +--> thiếu method/field -> lỗi linkage tương ứng
          |
          +--> static/instance mismatch -> ICCE
          |
          +--> không có concrete implementation -> AME
~~~

Một ứng dụng có thể startup bình thường vì code path lỗi chưa được chạy. Chỉ khi request, scheduled job hoặc message xử lý đúng phương thức mới, JVM mới phát hiện xung đột.

### 2.1. Compile time và runtime không dùng cùng một classpath

Compiler có thể thấy `library-api-2.jar` khi biên dịch, còn production lại nạp `library-api-1.jar` hoặc implementation cũ. Vì mỗi artifact được build riêng, compiler không nhất thiết có cơ hội kiểm tra **tổ hợp class files cuối cùng**.

Đây là lý do các lỗi liên kết thường xuất hiện trong multi-module, plugin-based, application server hoặc microservice deployment environments.

## 3. ABI khác Java source API như thế nào?

**Source API** là những khai báo mà source code nhìn thấy: classes, methods, interfaces, generics, annotations và access modifiers.

**ABI** phản ánh những đặc tính nhị phân mà compiled code dựa vào, như:

- Fully qualified class name.
- Class hay interface.
- Tên method và **JVM method descriptor**.
- Tên field và field descriptor.
- Static/instance nature.
- Access flags và inheritance relationships.
- Bytecode instructions như `invokevirtual` hoặc `invokestatic`.
- Bridge methods do compiler tạo.
- Superclasses/superinterfaces và default methods.

Hai source files nhìn rất giống nhau nhưng **khác ABI** có thể làm client binary cũ không chạy được.

### 3.1. Method descriptor

Ví dụ:

~~~java
public String find(long id) {
    return "...";
}
~~~

JVM descriptor:

~~~text
(J)Ljava/lang/String;
~~~

- `J`: tham số `long`.
- `Ljava/lang/String;`: return type `String`.

Với:

~~~java
public Object find(long id) {
    return null;
}
~~~

descriptor là:

~~~text
(J)Ljava/lang/Object;
~~~

Do descriptor JVM chứa cả return type, một thay đổi return type có thể khiến binary cũ không còn tìm đúng symbolic reference, dù Java source nhìn giống lời gọi ban đầu.

### 3.2. Generic type erasure

Generics được erasure ở nhiều trường hợp, nên thay đổi generic arguments không nhất thiết làm JVM descriptor thay. Nhưng compiler có thể tạo **bridge methods** để giữ dispatch và binary compatibility khi dùng covariant returns hoặc generics. Vì vậy cần xem bytecode thật thay vì chỉ nhìn Java method signature đã được IDE format.

## 4. Phân biệt những lỗi liên quan

| Lỗi | Tình huống điển hình | Câu hỏi chẩn đoán |
|---|---|---|
| `AbstractMethodError` | Interface/abstract contract tồn tại nhưng runtime không tìm được implementation concrete phù hợp | Implementation JAR đã được cập nhật chưa? |
| `IncompatibleClassChangeError` (cụ thể ở superclass) | Invocation/field access không phù hợp static/instance hoặc conflict interface defaults | Dạng member/class có đổi không? |
| `NoSuchMethodError` | JVM không resolve được method theo tên/descriptor | Method binary signature có đổi hoặc runtime JAR sai không? |
| `NoSuchFieldError` | Field không còn theo tên/descriptor | Field đã bị đổi/xóa không? |
| `IllegalAccessError` | Member/class tồn tại nhưng access rules không cho phép | Visibility/module access có thay không? |
| `ClassNotFoundException` | Code yêu cầu loader tìm class nhưng không thấy | JAR hoặc classloader path có thiếu không? |
| `NoClassDefFoundError` | JVM không thể tìm/định nghĩa class phụ thuộc tại runtime | Class đã bị loại, đổi package hoặc init lỗi không? |
| `UnsupportedClassVersionError` | JVM quá cũ để nạp class-file major | JDK runtime có phù hợp bytecode target không? |
| `VerifyError` | Bytecode không đáp ứng verification constraints | Bytecode generation/transformation có vấn đề không? |
| `ClassCastException` | Runtime object không cast được | Classloader identity/inheritance có lệch không? |

Bảng dùng để định hướng. Phải đọc **exception subtype, message, caused-by chain, stack frames và class source** thay vì chỉ dựa vào một từ khóa.

**Lưu ý:** các lỗi `NoSuchMethodError`, `NoSuchFieldError` và `IllegalAccessError` cũng nằm dưới `IncompatibleClassChangeError` trong class hierarchy. Khi nói “ICCE thuần” ở bài này, ta chủ yếu đề cập **`IncompatibleClassChangeError` được ném trực tiếp** thay vì một subclass cụ thể.

## 5. AbstractMethodError xảy ra khi nào?

Một tình huống phổ biến:

~~~text
V1 contract:
  interface Job {
      void run();
  }

Implementation V1:
  class LegacyJob implements Job {
      public void run() { ... }
  }

V2 contract:
  interface Job {
      void run();
      void cancel();  <-- abstract method mới
  }

Runtime:
  Job V2 + LegacyJob class file V1
  client gọi job.cancel()
             |
             v
      AbstractMethodError
~~~

`LegacyJob.class` đã biên dịch hợp lệ ở thời điểm interface chỉ có `run()`. Khi chạy, JVM có thể nạp class cũ cùng interface mới, nhưng nó không có concrete implementation cho `cancel()`. Lỗi xảy ra khi client thực sự gọi method đó.

### 5.1. Không nhất thiết lỗi ngay khi class được load

Đừng mặc định rằng mỗi implementation cũ sẽ làm ứng dụng fail startup ngay. Nhiều lỗi compatibility chỉ phát sinh lúc method invocation, đặc biệt ở nhánh code hiếm.

Do đó, **startup smoke test không đủ** để chứng minh runtime dependency graph tương thích.

### 5.2. Interface thêm default method thì sao?

Nếu V2 bổ sung một **default method** có implementation:

~~~java
public interface Job {
    void run();

    default void cancel() {
        // Fallback implementation.
    }
}
~~~

implementation cũ có thể thừa kế default method và không cần implement thêm trong một số cấu trúc hợp lệ. Tuy nhiên, default methods còn có các quy tắc method selection và conflict; không phải mọi thay đổi từ abstract sang default đều an toàn trong mọi inheritance graph.

## 6. Ví dụ tái hiện AbstractMethodError bằng separate compilation

Mục tiêu ví dụ: **biên dịch implementation với API V1**, sau đó chỉ thay API lên V2 và biên dịch client mới. Không biên dịch lại implementation.

### 6.1. Cấu trúc file minh họa

~~~text
ame-demo/
├── v1/api/demo/api/Task.java
├── v1/impl/demo/impl/LegacyTask.java
├── v2/api/demo/api/Task.java
├── client/demo/client/Main.java
└── out/
    ├── v1-api/
    ├── impl/
    ├── v2-api/
    └── client/
~~~

### 6.2. API phiên bản V1

File `v1/api/demo/api/Task.java`:

~~~java
package demo.api;

public interface Task {
    void execute();
}
~~~

### 6.3. Implementation cũ

File `v1/impl/demo/impl/LegacyTask.java`:

~~~java
package demo.impl;

import demo.api.Task;

public final class LegacyTask implements Task {

    @Override
    public void execute() {
        System.out.println("Executed by legacy implementation");
    }
}
~~~

Implementation này hoàn toàn hợp lệ theo `Task` V1.

### 6.4. API phiên bản V2

File `v2/api/demo/api/Task.java`:

~~~java
package demo.api;

public interface Task {
    void execute();

    void cancel();
}
~~~

V2 bổ sung một abstract method `cancel()` không có default implementation.

### 6.5. Client được biên dịch theo V2

File `client/demo/client/Main.java`:

~~~java
package demo.client;

import demo.api.Task;
import demo.impl.LegacyTask;

public final class Main {

    public static void main(String[] args) {
        Task task = new LegacyTask();
        task.execute();
        task.cancel();
    }
}
~~~

### 6.6. Các lệnh biên dịch minh họa

Trên shell Unix/Linux/macOS:

~~~bash
mkdir -p out/v1-api out/impl out/v2-api out/client

javac --release 8 \
  -d out/v1-api \
  v1/api/demo/api/Task.java

javac --release 8 \
  -cp out/v1-api \
  -d out/impl \
  v1/impl/demo/impl/LegacyTask.java

javac --release 8 \
  -d out/v2-api \
  v2/api/demo/api/Task.java

javac --release 8 \
  -cp "out/v2-api:out/impl" \
  -d out/client \
  client/demo/client/Main.java
~~~

Tại thời điểm compile `LegacyTask`, compiler chỉ thấy `Task` V1. Tại thời điểm compile client, compiler thấy `Task` V2 và implementation binary cũ.

Chạy:

~~~bash
java -cp "out/client:out/impl:out/v2-api" \
  demo.client.Main
~~~

Trên Windows, separator classpath thông thường là dấu chấm phẩy `;`:

~~~powershell
java -cp "out/client;out/impl;out/v2-api" demo.client.Main
~~~

### 6.7. Kết quả kỳ vọng

Chương trình có thể in:

~~~text
Executed by legacy implementation
~~~

rồi ném exception thuộc dạng:

~~~text
java.lang.AbstractMethodError: Receiver class demo.impl.LegacyTask
does not define or inherit an implementation of the resolved method
'abstract void cancel()' of interface demo.api.Task
~~~

**Thông điệp lỗi chi tiết tùy Java runtime/version**, nên không yêu cầu nội dung message khớp từng ký tự. Điểm quan trọng là runtime chứa **V2 API + V1 implementation**, còn method được gọi chưa có concrete implementation.

Các lệnh trên là **hướng dẫn để người học tái hiện**, không phải kết quả test đã chạy trong bài soạn.

## 7. Sửa ví dụ AbstractMethodError theo đúng hợp đồng

Cách trực tiếp là biên dịch lại implementation theo V2:

~~~java
package demo.impl;

import demo.api.Task;

public final class LegacyTask implements Task {

    @Override
    public void execute() {
        System.out.println("Executed");
    }

    @Override
    public void cancel() {
        System.out.println("Cancelled");
    }
}
~~~

Sau đó bảo đảm artifact mới được đưa vào **runtime classpath** thay cho implementation cũ.

Những bước quan trọng:

1. Nâng source implementation hoặc chọn bản library đã hỗ trợ API V2.
2. Biên dịch implementation với API tương ứng.
3. Kiểm tra ABI method descriptor trong class file.
4. Đóng gói implementation mới.
5. Xác minh application/server nạp **đúng JAR mới**, không còn JAR cũ được ưu tiên.
6. Chạy test gọi `cancel()`, không chỉ kiểm tra startup.
7. Nếu nhiều services/plugins dùng implementation, nâng theo compatibility matrix.

### 7.1. Không chỉ thêm một method vào interface rồi kỳ vọng runtime tự sửa

JVM không có cơ chế tự viết method body cho implementation cũ chỉ vì interface mới yêu cầu. Nếu cần backward compatibility, có thể xem xét một default method có semantics phù hợp hoặc một adapter tương thích, nhưng quyết định này phải được review.

### 7.2. Mặc định triển khai không phải luôn phù hợp

Một `cancel()` default no-op có thể che tình trạng cancel không thực sự được hỗ trợ và làm hệ thống xử lý sai nghiệp vụ. Default method chỉ an toàn khi có hợp đồng rõ và tests.

## 8. Abstract superclass cũng có thể dẫn tới AbstractMethodError

Không phải AME chỉ đến từ interface.

Giả sử thư viện có một abstract superclass:

~~~java
public abstract class BaseProcessor {
    public abstract void process();
}
~~~

Một subclass binary cũ có thể dựa vào một dạng superclass contract khác ở thời điểm biên dịch. Nếu binary của superclass/child bị thay lệch nhau và một method call cuối cùng không tìm được implementation concrete hợp lệ, runtime có thể gặp `AbstractMethodError`.

Tùy cách thay API, compiler hoặc JVM có thể phát hiện ở giai đoạn khác. Cần phân tích **chữ ký, hierarchy và compiled bytecode**, không suy rằng mọi abstract superclass change chắc chắn ném cùng lỗi.

### 8.1. Vấn đề thường xuất hiện ở framework extension

Một thư viện có base classes như:

~~~java
public abstract class FrameworkAdapter {
    protected abstract Result handle(Input input);
}
~~~

Nếu framework version mới thêm/đổi abstract hooks trong khi plugin extension giữ binary cũ, một invocation có thể dẫn đến AME. Các plugin custom hoặc adapter của bên thứ ba là điểm cần rà khi nâng Spring, ORM, driver và application server.

## 9. ICCE khi đổi instance method thành static method

Một ví dụ thường gặp của `IncompatibleClassChangeError` trực tiếp là đổi **dạng invocation** của cùng method.

Phiên bản V1:

~~~java
package demo.lib;

public final class PingUtil {

    public String ping() {
        return "v1";
    }
}
~~~

Client compile với V1:

~~~java
package demo.client;

import demo.lib.PingUtil;

public final class Main {

    public static void main(String[] args) {
        System.out.println(new PingUtil().ping());
    }
}
~~~

Phiên bản V2 của library:

~~~java
package demo.lib;

public final class PingUtil {

    public static String ping() {
        return "v2";
    }
}
~~~

Source client cũ đã được compiler chuyển thành **instance method invocation**, nhưng runtime chỉ có method static với cùng binary name/descriptor.

### 9.1. Những gì JVM có thể thấy

Client V1 có thể chứa:

~~~text
invokevirtual demo/lib/PingUtil.ping:()Ljava/lang/String;
~~~

Nhưng runtime V2 method có flag `ACC_STATIC`. Method invocation instruction không tương thích với member được resolve, dẫn tới `IncompatibleClassChangeError`, thường có message dạng:

~~~text
java.lang.IncompatibleClassChangeError:
Expecting non-static method 'java.lang.String demo.lib.PingUtil.ping()'
~~~

Thông điệp cụ thể tùy JVM, release và bytecode compiler. Điều quan trọng là **`invokevirtual` đối lập với static method**.

## 10. Các lệnh tái hiện ICCE do static/instance mismatch

Giả sử cấu trúc:

~~~text
icce-demo/
├── v1/demo/lib/PingUtil.java
├── v2/demo/lib/PingUtil.java
├── client/demo/client/Main.java
└── out/
    ├── v1/
    ├── v2/
    └── client/
~~~

Biên dịch V1:

~~~bash
mkdir -p out/v1 out/v2 out/client

javac --release 8 \
  -d out/v1 \
  v1/demo/lib/PingUtil.java
~~~

Biên dịch client theo V1:

~~~bash
javac --release 8 \
  -cp out/v1 \
  -d out/client \
  client/demo/client/Main.java
~~~

Biên dịch library V2:

~~~bash
javac --release 8 \
  -d out/v2 \
  v2/demo/lib/PingUtil.java
~~~

Chạy **client V1** với **library V2**, không có V1 JAR ở runtime:

~~~bash
java -cp "out/client:out/v2" demo.client.Main
~~~

Kỳ vọng: `IncompatibleClassChangeError` vì bytecode của client gọi instance method mà implementation runtime đã đổi thành static.

**Không compile lại client với V2 trước khi tái hiện**: compiler có thể sửa invocation thành `invokestatic` hoặc báo lỗi source tùy cách gọi, khiến mất tình huống binary mismatch ban đầu.

## 11. Đổi static thành instance cũng có thể ném ICCE

Trường hợp ngược:

- Client cũ biên dịch với `public static void send()`.
- Runtime library đổi thành `public void send()`.
- Bytecode cũ còn lệnh `invokestatic`.
- JVM thấy target method thực tế không static.

Kết quả có thể là `IncompatibleClassChangeError`, thường có message tương đương “Expected static method”.

Đây là một **ABI breaking change**. Giữ cùng method name/parameter types trong Java source không đủ để giữ binary compatibility.

### 11.1. Fields cũng có static/instance mismatch

ICCE không giới hạn methods. Client binary có thể dùng:

- `getstatic`/`putstatic` với static field.
- `getfield`/`putfield` với instance field.

Nếu field được đổi từ static sang instance hoặc ngược lại giữa compile-time và runtime, JVM có thể ném `IncompatibleClassChangeError` khi truy cập.

### 11.2. Tránh sửa bằng cách ép JVM flags

`--add-opens` hoặc `--add-exports` liên quan module access, không biến một instance method thành static hay ngược lại. Thay flag không sửa được bytecode invocation instruction.

## 12. ICCE do xung đột interface default methods

Java 8 bổ sung default methods cho interfaces. Điều này giúp interface phát triển API, nhưng khi các interfaces khác nhau cùng bổ sung default method với **cùng signature**, một class binary cũ có thể rơi vào trạng thái ambiguous.

### 12.1. Tình huống separate compilation

Phiên bản V1:

~~~java
package demo.spi;

public interface Left {
}
~~~

~~~java
package demo.spi;

public interface Right {
}
~~~

Class được compile với V1:

~~~java
package demo.impl;

import demo.spi.Left;
import demo.spi.Right;

public final class Combined implements Left, Right {
}
~~~

Đến phiên bản V2, `Left` bổ sung:

~~~java
package demo.spi;

public interface Left {

    default String label() {
        return "left";
    }
}
~~~

Còn `Right` cũng bổ sung:

~~~java
package demo.spi;

public interface Right {

    default String label() {
        return "right";
    }
}
~~~

Client mới có thể gọi:

~~~java
Left component = new Combined();
System.out.println(component.label());
~~~

Nếu `Combined.class` vẫn là binary từ V1, class đó **không có method override để giải quyết conflict**. Khi method selection thấy hai default implementations cạnh tranh trong những điều kiện tương ứng, JVM có thể ném `IncompatibleClassChangeError`.

### 12.2. Vì sao compiler không chặn?

Nếu biên dịch lại source `Combined implements Left, Right` trực tiếp với hai interfaces V2, javac thường yêu cầu giải quyết conflict. Nhưng binary `Combined.class` V1 được sinh trước khi các default methods xuất hiện; nó có thể không được compiler mới kiểm tra lại trong lúc đóng gói.

Đây là ví dụ cho sự khác biệt giữa **source compilation consistency** và **runtime binary linkage**.

### 12.3. Cách xử lý

Một cách giải quyết là implement/override method trong `Combined`:

~~~java
public final class Combined implements Left, Right {

    @Override
    public String label() {
        return Left.super.label();
    }
}
~~~

Lúc này class đưa ra lựa chọn explicit. Cần compile lại theo API V2 và triển khai binary mới. Không tự quyết định dùng `Left.super.label()` nếu business semantics thực tế yêu cầu `Right` hoặc một implementation khác.

## 13. Interface chuyển thành class và ngược lại

Một library version có thể thay một public type từ `interface` sang `class` hoặc ngược lại. Mã biên dịch cũ có thể chứa assumptions về:

- `invokeinterface` so với `invokevirtual`.
- `implements` so với `extends`.
- Object construction.
- Inheritance và method resolution.

Tùy thay đổi cụ thể, JVM có thể báo `IncompatibleClassChangeError` hoặc một lỗi linkage khác. Đây thường là breaking change rất lớn ở cấp ABI.

### 13.1. Không sửa bằng cách đổi dependency jar một chiều

Nếu public type thay từ interface sang class, cần đồng bộ **tất cả implementations, adapters và client binaries**. Việc chỉ nâng API jar rồi để plugin implementations cũ hoạt động có thể tạo xung đột lan rộng.

## 14. Method resolution và method selection khác nhau

Đây là phần quan trọng để hiểu vì sao hai lỗi liên quan nhưng không giống nhau.

### 14.1. Resolution

JVM dùng symbolic reference từ constant pool của class đang gọi để xác định method/field theo class/interface name và descriptor. Nếu không tìm được method thích hợp, có thể ném `NoSuchMethodError` hoặc lỗi resolution tương ứng.

### 14.2. Selection

Với các invocation có dynamic dispatch, JVM còn phải chọn implementation thực tế dựa vào receiver class, inheritance và interface defaults.

Ví dụ:

~~~java
interface Service {
    void run();
}

final class LegacyService implements Service {
    @Override
    public void run() { }
}
~~~

Nếu library API thay đổi giữa các lần biên dịch, symbolic reference có thể resolve tới `Service.run()` nhưng concrete receiver tại runtime lại không có implementation phù hợp cho một method mới. Khi đó `AbstractMethodError` có thể xuất hiện **ở bước dispatch/selection**.

### 14.3. Không mọi invocation đều dynamic dispatch

- `invokestatic`: gọi static method.
- `invokevirtual`: thường gọi instance method qua class hierarchy với dispatch.
- `invokeinterface`: gọi interface method qua receiver implementation.
- `invokespecial`: dùng cho một số lời gọi constructor, private method và special superclass/interface invocations.

Lỗi cụ thể phụ thuộc instruction và các quy tắc JVMS. Không nên tự suy tất cả lỗi liên kết đều do `invokevirtual`.

## 15. Nhìn bytecode invocation bằng javap

`javap` là công cụ hữu ích để phân biệt compiled client **đã kỳ vọng lời gọi nào**.

Ví dụ:

~~~bash
javap -classpath client.jar -c -p \
  com.example.client.OrderClient
~~~

Có thể thấy:

~~~text
invokeinterface #18 // InterfaceMethod com/example/api/Service.cancel:()V
~~~

hoặc:

~~~text
invokevirtual #22 // Method com/example/lib/PingUtil.ping:()Ljava/lang/String;
~~~

hoặc:

~~~text
invokestatic #22 // Method com/example/lib/PingUtil.ping:()Ljava/lang/String;
~~~

Các số `#18` và `#22` chỉ là chỉ mục constant pool trong một output minh họa. Khi chẩn đoán, chú ý **opcode, owner, method name và descriptor**.

### 15.1. Xem method signatures

~~~bash
javap -classpath implementation.jar -s -p \
  com.example.impl.LegacyService
~~~

`-s` hiển thị internal type signatures/descriptors. `-p` hiển thị cả private members.

### 15.2. Xem method flags

~~~bash
javap -classpath implementation.jar -verbose \
  com.example.impl.LegacyService
~~~

Tìm những flag như `ACC_PUBLIC`, `ACC_STATIC`, `ACC_ABSTRACT` và `ACC_BRIDGE`.

Không chỉ nhìn source đang mở trong IDE: source có thể là version mới, trong khi production JVM nạp class từ một artifact cũ khác.

## 16. Mô hình điều tra một stack trace

Ví dụ giả định:

~~~text
java.lang.AbstractMethodError:
Receiver class com.example.vendor.LegacyAdapter
does not define or inherit an implementation of
'abstract void com.example.spi.Service.stop()'
    at com.example.app.Worker.shutdown(Worker.java:84)
    at com.example.app.Main.main(Main.java:20)
~~~

Đọc theo thứ tự:

1. **Concrete error:** `AbstractMethodError`.
2. **Receiver:** `com.example.vendor.LegacyAdapter`.
3. **Method contract:** `Service.stop()V`.
4. **Call site:** `Worker.shutdown`.
5. **Runtime API:** method hiện được khai báo ở đâu?
6. **Implementation artifact:** `LegacyAdapter.class` lấy từ JAR nào?
7. **Compile-time API:** implementation được build với SPI version nào?
8. **Deployment:** có plugin/server library hoặc classloader ưu tiên bản cũ không?

Câu hỏi đúng thường không phải “làm sao catch lỗi này?” mà là **“mã gọi, hợp đồng API và receiver implementation đang đến từ những binary version nào?”**

## 17. Xác định JAR chứa class đang được nạp

Một dependency graph có thể cho biết version được resolve lúc build, nhưng external container hoặc plugin loader có thể nạp một JAR khác.

### 17.1. Class loading log trên JDK hiện đại

Ví dụ:

~~~bash
java -Xlog:class+load=info \
  -cp "app.jar:lib/*" \
  com.example.Main
~~~

Tùy JDK và launcher, logs có thể cho biết class được load từ archive/source nào. Với Java 8, cơ chế logging khác (ví dụ `-verbose:class`); cần dùng flags phù hợp runtime.

### 17.2. In vị trí CodeSource trong môi trường test

Có thể viết diagnostic code:

~~~java
public static String codeSourceOf(Class<?> type) {
    var domain = type.getProtectionDomain();

    if (domain == null || domain.getCodeSource() == null) {
        return "<unknown>";
    }

    var location = domain.getCodeSource().getLocation();

    return location == null ? "<unknown>" : location.toString();
}
~~~

Ví dụ dùng `var` nên yêu cầu Java 10+. Có thể dùng khai báo tường minh nếu cần Java 8.

**Giới hạn:** CodeSource có thể phản ánh container/launcher/nested JAR theo cách riêng, và không phải lúc nào cũng chứa URL dễ đọc. Đừng dùng nó làm nguồn chứng cứ duy nhất.

### 17.3. Không log đường dẫn và metadata nhạy cảm bừa bãi

Chỉ bật các diagnostics cần thiết trong môi trường được kiểm soát; class loading logs có thể rất lớn và lộ thông tin đường dẫn hệ thống. Khi lấy logs production phải tuân theo chính sách bảo mật.

## 18. Gradle: điều tra dependency resolution

Trong một Gradle Java project, các lệnh tham khảo:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Trong multi-module:

~~~bash
./gradlew :orders-service:dependencies \
  --configuration runtimeClasspath
~~~

Để xem vì sao một version được chọn:

~~~bash
./gradlew :orders-service:dependencyInsight \
  --dependency example-spi \
  --configuration runtimeClasspath
~~~

Các task/configurations phụ thuộc project và Gradle plugin đang dùng.

### 18.1. Compile và runtime graph khác nhau

Ví dụ:

~~~text
compileClasspath:
  com.example:service-spi:2.0

runtimeClasspath:
  com.example:service-spi:2.0
  com.example:legacy-service-impl:1.0
~~~

SPI mới nhưng implementation cũ là một ứng viên gây AME. Trong một application server, runtime còn có server-provided libraries ngoài graph này.

### 18.2. Không force dependency version tùy tiện

Override một transitive JAR lên version cao hơn có thể giải quyết một conflict nhưng tạo conflict ABI với library cha. Nên theo BOM/compatibility matrix của framework khi có, nâng tổ hợp thư viện tương thích rồi chạy integration tests.

### 18.3. Dependency locking

Dependency locks hoặc version constraints có thể giúp tái hiện resolved graph. Chúng không tự chứng minh binary compatibility, nhưng giúp so sánh chính xác trước/sau migration.

## 19. Maven: xem dependency tree và effective POM

Các lệnh tham khảo:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.example:service-spi
mvn help:effective-pom
~~~

Khi dùng Maven parent/BOM, `help:effective-pom` giúp thấy version management và plugin configuration đã hợp nhất.

Tùy phiên bản Maven Dependency Plugin, có thể dùng:

~~~bash
mvn dependency:tree -Dverbose
~~~

Hãy dựa vào output thực tế và resolved artifacts, vì chi tiết omitted/conflict nodes có thể khác theo plugin version.

### 19.1. Tình huống Maven gần đúng

~~~text
app
 +-- com.example:new-client:3.0
 |    +-- com.example:service-spi:2.0
 +-- com.example:legacy-adapter:1.0
      +-- com.example:service-spi:1.0 (omitted/mediated)
~~~

Maven chọn `service-spi:2.0` nhưng `legacy-adapter:1.0` có thể được biên dịch theo SPI cũ. Đây là ví dụ giả định; phải kiểm tra binary thực tế để biết incompatibility nào sẽ xảy ra.

### 19.2. Dependency exclusion không phải giải pháp tổng quát

Loại SPI JAR cũ là đúng nếu runtime chỉ cần một API version, nhưng nó **không tự tạo implementation còn thiếu** trong `legacy-adapter:1.0`. Nếu adapter phải cập nhật, cần chọn bản adapter tương thích hoặc rebuild.

## 20. Framework migration và các extension points

Các framework cung cấp interfaces/abstract classes mà plugin hoặc ứng dụng triển khai:

- Spring lifecycle và custom extension APIs.
- Hibernate interceptors, custom types, dialects.
- Servlet Filters/Listeners.
- JDBC drivers và Service Provider Interfaces.
- Serialization modules.
- Logging backends/appenders.
- Bytecode agents và instrumentation frameworks.
- Custom test runners.
- Application server modules.
- Internal SDKs/plugin contracts.

Khi framework lên major mới, implementation compile với contract cũ có thể gặp AME/ICCE nếu vẫn bị nạp.

### 20.1. Spring Boot 2 → 3

Chuyển Spring Framework 5 sang 6 và Java EE `javax.*` sang Jakarta `jakarta.*` có thể tạo:

- Missing classes/`NoClassDefFoundError` nếu còn thư viện cũ.
- `NoSuchMethodError` nếu API method đã đổi.
- `AbstractMethodError` nếu extension implementation không đáp ứng contract mới.
- `IncompatibleClassChangeError` khi binary hierarchy/member flags không còn khớp.
- Bean initialization errors do mix versions.

Không quy mọi lỗi cho Jakarta chỉ vì upgrade Boot. Phải xem concrete exception và class source.

### 20.2. Hibernate 5 → 6

Custom UserType, Dialect hoặc interceptor classes từ Hibernate 5 có thể cần sửa theo API mới. Nếu old adapter binary được dùng cùng Hibernate 6, có thể gặp linkage errors. Phải nâng toàn bộ extension và xác minh SQL/query behavior, không chỉ add method cho hết AME.

### 20.3. Servlet 4 → Jakarta Servlet 6

`javax.servlet.Filter` và `jakarta.servlet.Filter` là **hai types khác nhau**. Việc không thấy class thường dẫn đến `ClassNotFoundException` hoặc `NoClassDefFoundError` chứ không nhất thiết AME/ICCE. Đây là ví dụ cho nguyên tắc **không gán một loại lỗi chung cho mọi compatibility issue**.

## 21. Không phải JDK upgrade trực tiếp gây AME/ICCE

Nâng Java 11 → 17 hoặc Java 17 → 21 có thể kéo theo:

- Nâng Gradle/Maven plugins.
- Nâng các thư viện hỗ trợ class-file version mới.
- Nâng Spring/ORM/HTTP client.
- Cập nhật Java agent, code generator, testing framework.
- Đổi container image hoặc application server.
- Đổi cách đóng gói, shading hoặc module path.

Những thay đổi **gián tiếp** đó có thể làm dependency ABI mismatch lộ ra.

### 21.1. Một code path chạy khác sau nâng JDK

Ứng dụng có thể dùng `Runtime.version()`, service loading, MRJAR hoặc reflection để chọn implementation mới trên JDK mới. Khi đó, cùng JAR nhưng runtime mới có thể gọi vào code path chưa được test, khiến linkage error xuất hiện.

Điều tra nên so:

- JDK runtime version.
- Artifact checksums.
- Classloader/launcher.
- Multi-release JAR variants.
- Runtime dependencies.
- Code path và class được nạp.

### 21.2. Một JAR checksum không đổi vẫn có thể chọn class khác

Với **multi-release JAR**, class ở `META-INF/versions/17` có thể được dùng trên Java 17, còn Java 11 dùng base/overlay 11. Nếu một variant có ABI hoặc implementation lỗi, vấn đề chỉ xuất hiện ở một JDK.

Không kết luận từ việc cùng artifact version rằng runtime đang chạy đúng cùng class bytes.

## 22. Multi-release JAR trong chẩn đoán

Ví dụ:

~~~text
library.jar
  com/example/Service.class
  META-INF/versions/11/com/example/Service.class
  META-INF/versions/17/com/example/Service.class
~~~

Nếu Java 17 chọn bản versioned khác, cần kiểm tra:

1. Manifest có `Multi-Release: true`.
2. Class-file major của mỗi variant.
3. Method descriptor và static/abstract flags của base và overlay.
4. Public/protected API consistency.
5. Loader có MRJAR-aware không.
6. Client compile-time view khác runtime view không.
7. `jar --validate` có báo structural/API inconsistency không.
8. Các test có chạy **packaged JAR** thay vì class directories không.

Một MRJAR sai có thể gây `NoSuchMethodError`/AME/ICCE khi runtime mới chọn class khác. Đây là một khả năng cần điều tra, không phải mặc định nguyên nhân của mọi lỗi sau nâng Java.

## 23. Class loader và ứng dụng plugin-based

Java type identity bao gồm **tên class và defining class loader**. Một application server hoặc plugin engine có thể dùng nhiều class loaders.

~~~text
Bootstrap/platform loader
          |
          v
Container/common loader
          |
          +-- shared-api.jar
          |
          v
Application/webapp/plugin loader
          |
          +-- implementation.jar
          +-- another-api.jar
~~~

Nếu parent loader chọn API version A còn child loader chọn implementation compile với version B, có thể phát sinh lỗi liên kết hoặc loader constraint violation.

### 23.1. Dấu hiệu

- Local standalone application chạy được, WAR deploy trên server lỗi.
- Plugin load theo thứ tự thay đổi gây kết quả khác.
- Một class xuất hiện trong hai JARs hoặc server/common classpath.
- Exception chỉ xảy ra sau hot redeploy.
- Message `loader constraint violation` hoặc xung đột class identity.
- CodeSource cho thấy class được lấy từ nơi khác dự kiến.

### 23.2. Không nhét JAR tùy tiện vào server lib

Thêm một version framework API vào container-shared libraries có thể làm nhiều WAR cùng nạp version đó, trong khi từng WAR cần version riêng. Những dependencies do server cung cấp phải được quản lý theo support matrix của application server.

### 23.3. Tách API ổn định và plugin implementation

Nếu thiết kế plugin architecture, nên có:

- Một SPI artifact/version contract rõ.
- Plugin implementations được compile/test với SPI version hỗ trợ.
- Classloader policy nhất quán.
- Version negotiation hoặc reject plugin không tương thích.
- Plugin API compatibility tests trước khi load vào production.

## 24. Java agents, proxies và generated bytecode

Một số lỗi sau nâng JDK có thể liên quan code được sinh hoặc biến đổi:

- Byte Buddy/Mockito inline mocking.
- AOP proxies.
- Hibernate bytecode enhancement.
- JDK dynamic proxies.
- Java agents/APM instrumentation.
- Compiler/annotation processor generated classes.
- Runtime code generation (CGLIB-like tools).
- Shading/obfuscation.

Các công cụ này có thể tạo classes hoặc method stubs theo API version được nhìn thấy. Nếu runtime method contract khác hoặc bytecode transformation không giữ ABI, lỗi liên kết có thể xuất hiện.

### 24.1. Phân biệt parser lỗi với linkage lỗi

Một agent không hiểu class-file major version mới thường ném lỗi như `Unsupported class file major version N` hoặc `IllegalClassFormatException`. Đó không nhất thiết là AME/ICCE.

Nếu agent vẫn transform class nhưng tạo invocation/dispatch sai, có thể gặp linkage error. Cần xem **full stack trace và bytecode sau transformation** khi điều tra chuyên sâu.

### 24.2. Không tự ép ASM/Byte Buddy version khi chưa rõ owner

Nhiều thư viện shade bytecode parser riêng. Thêm một ASM version mới vào application classpath có thể không thay parser agent đang dùng. Nâng chính component sở hữu agent/transformer theo release hỗ trợ JDK mục tiêu thường đáng tin hơn.

## 25. ServiceLoader và SPI implementation

`ServiceLoader` nạp implementation của interfaces theo service registration metadata. Nếu interface SPI được mở rộng nhưng providers cũ còn nằm trong classpath/module path, có thể xảy ra:

~~~text
SPI v2
   |
   +-- NewProvider v2 -> đầy đủ methods
   |
   +-- LegacyProvider v1 -> thiếu method mới
                              |
                              v
                        AbstractMethodError
                              khi method được gọi
~~~

Quy trình kiểm tra:

1. Xác định service interface được dùng ở runtime.
2. Liệt kê providers và artifact chứa chúng.
3. Kiểm tra `META-INF/services` hoặc `module-info.java` `provides` declarations.
4. Xác định provider thực sự được chọn.
5. Xem provider binary đã compile theo SPI version nào.
6. Nâng/rebuild provider hoặc loại provider không tương thích.
7. Test provider selection và thực thi tất cả methods quan trọng.

Không chỉ đổi service registration name mà bỏ qua ABI của provider.

## 26. Default methods và binary compatibility trong thiết kế API

Khi thiết kế interface SPI, thêm một abstract method có thể là **rủi ro đối với implementations đã phát hành**.

### 26.1. Thêm abstract method

~~~java
public interface Decoder {
    String decode(byte[] bytes);

    // V2:
    void reset();
}
~~~

Các implementations cũ không có `reset` và có nguy cơ AME khi method mới được gọi.

### 26.2. Thêm default method

~~~java
public interface Decoder {
    String decode(byte[] bytes);

    default void reset() {
        // Implementation tương thích nếu semantics cho phép.
    }
}
~~~

Default có thể giảm yêu cầu recompile, nhưng:

- Có thể tạo conflict với default của interface khác.
- Có thể làm thay method selection.
- Một default no-op có thể sai nghiệp vụ.
- Không phải mọi contract đều có fallback hợp lý.

### 26.3. Thêm interface mới để mở rộng capability

Một lựa chọn là tách capability:

~~~java
public interface Decoder {
    String decode(byte[] bytes);
}

public interface ResettableDecoder extends Decoder {
    void reset();
}
~~~

Consumer có thể kiểm tra hoặc yêu cầu `ResettableDecoder` khi feature thật sự cần. Đây là một cách thiết kế tránh phá SPI cũ trong một số hoàn cảnh, nhưng cần xác định behavior nếu implementation không hỗ trợ capability.

## 27. Nhận diện class/method thực tế qua jars

Khi đã biết fully qualified class name:

~~~bash
jar tf legacy-adapter.jar
~~~

Tìm file:

~~~text
com/example/vendor/LegacyAdapter.class
~~~

Kiểm tra methods:

~~~bash
javap -classpath legacy-adapter.jar -s -p \
  com.example.vendor.LegacyAdapter
~~~

Nếu method không có ở class, chưa đủ kết luận AME vì implementation có thể được thừa kế từ superclass hoặc default interface. Cần xem cả hierarchy, interfaces và method descriptors.

### 27.1. Không chỉ dựa vào decompiled Java source

Decompiler có thể hiển thị gần giống Java nhưng che một số bridge/synthetic methods hoặc details về JVM invocation. Với linkage errors, `javap -verbose`/`-c` thường cho bằng chứng sát binary hơn.

### 27.2. JAR có nhiều bản class

Một fat JAR, WAR hoặc multi-release JAR có thể chứa nhiều physical entries cho một logical class. Phải biết class loader **đã nạp entry nào**, chứ không chỉ tìm thấy class name đâu đó trong archive.

## 28. Bridge methods, covariant returns và generics

Compiler có thể tạo bridge methods để duy trì polymorphism khi generics bị type erasure hoặc khi subclass sử dụng covariant return.

Ví dụ:

~~~java
interface Supplier<T> {
    T get();
}

final class StringSupplier implements Supplier<String> {

    @Override
    public String get() {
        return "value";
    }
}
~~~

Compiler có thể phát sinh bridge method tương ứng dạng `Object get()` để đáp ứng binary method contract sau erasure.

### 28.1. Lỗi khi binary bị biến đổi

Nếu một bytecode optimizer/shader hoặc code generator xử lý không đúng bridge methods, client binary cũ có thể không tìm đúng target hoặc dispatch không như kỳ vọng. Lỗi có thể là `NoSuchMethodError`, AME hoặc một dạng linkage khác tùy binary thực tế.

### 28.2. Kiểm tra bridge flags

~~~bash
javap -classpath library.jar -p -verbose \
  com.example.StringSupplier
~~~

Tìm `ACC_BRIDGE` và `ACC_SYNTHETIC`, cùng các method descriptors.

Không kết luận bridge mất chỉ vì decompiled source không hiển thị nó. Phải kiểm tra class file.

## 29. Khi nào chỉ cần compile lại?

**Recompile** có thể giải quyết lỗi khi source của implementation vẫn hợp lệ theo API mới hoặc chỉ cần tạo lại bytecode/bridge methods phù hợp.

Nhưng không phải lúc nào cũng đủ:

- Interface mới có thêm abstract method mà implementation chưa viết -> compile sẽ báo thiếu implementation, cần sửa source.
- Method đổi từ instance sang static -> consumer source/semantics có thể cần sửa.
- Framework major upgrade thay API, SQL hoặc security behavior -> cần migration và tests.
- Public interface đổi thành class -> có thể cần redesign extension.
- Một library của bên thứ ba không có source hoặc đã EOL -> chọn bản replacement hoặc fork được bảo trì.
- Runtimes chứa nhiều JARs cũ/new -> phải sửa packaging/dependency selection.

**Không sửa đơn thuần bằng recompile mà bỏ qua contract behavior**. Code chạy được chưa chắc tiếp tục đúng nghiệp vụ.

## 30. Biện pháp xử lý theo nguyên nhân

| Nguyên nhân | Cách sửa chính | Không nên |
|---|---|---|
| Implementation cũ thiếu abstract method | Nâng/rebuild implementation theo SPI mới | Catch `AbstractMethodError` rồi bỏ qua |
| Instance ↔ static method change | Đồng bộ client và library ABI | Thêm `--add-opens` |
| Hai interface defaults xung đột | Override method rõ trong implementing class | Chọn behavior ngẫu nhiên |
| Trộn framework versions | Dùng BOM/compatible release set | Override từng transitive JAR tùy tiện |
| JAR cũ ở server classpath | Sửa classloader/deployment ownership | Copy thêm JAR trùng bản |
| Plugin dùng SPI cũ | Nâng plugin, version negotiation | Cho plugin chạy đến khi lỗi mới lộ |
| Multi-release JAR variant lỗi | Sửa versioned class và packaging | Chỉ test base class |
| Java agent sinh bytecode sai | Nâng agent, kiểm tra transformation | Bỏ toàn bộ tests lâu dài |
| Generated client/stub sai version | Regenerate từ schema/tool phù hợp | Chỉnh tay generated files |
| Runtime JVM thấp hơn target | Nâng runtime hoặc hạ target hợp lệ | Dùng flags mở module |

Nếu một hệ thống cần workaround tạm, ghi rõ owner, rủi ro, phạm vi, thời hạn và cách loại bỏ. Đừng biến một runtime conflict thành phụ thuộc lâu dài vào classpath order ngẫu nhiên.

## 31. Quy trình chẩn đoán theo thứ tự ưu tiên

### Bước 1: Thu thập exception đầy đủ

Lưu:

- Exact exception class.
- Message nguyên văn.
- Stack trace và caused-by chain.
- Thread/request/job gây lỗi.
- JDK version và container version.
- Commit, artifact checksum, thời điểm deploy.

### Bước 2: Tìm owner method/field

Dựa trên message và bytecode:

- Class/interface chứa symbolic reference.
- Method name và descriptor.
- Receiver runtime class.
- Có static/instance mismatch không?
- Có multiple default methods không?

### Bước 3: Xác định binary thực sự được load

Dùng class loading logs/CodeSource, container classpath và JAR inspection.

### Bước 4: So compile graph với runtime graph

Kiểm tra direct/transitive dependency versions, BOMs, conflicts, shaded/nested JARs, server/shared libraries.

### Bước 5: So API và implementation ABIs

Dùng `javap -s -p -c -verbose` để xem method signature, flags, opcodes và inheritance.

### Bước 6: Tạo minimal reproduction

Tách một client và hai versions API/implementation, hoặc hai interface defaults. Reproduce giúp xác nhận nguyên nhân, không chỉ dựa vào phỏng đoán từ stack trace.

### Bước 7: Sửa tại nguồn

Đồng bộ versions/recompile implementation/regenerate output/đổi API theo hướng hỗ trợ chính thức.

### Bước 8: Kiểm tra runtime thực

Chạy đúng packaged artifact trên JDK/container đích và bài test kích hoạt code path trước đây lỗi.

### Bước 9: Kiểm tra regression

Bao gồm integration, security, serialization, performance, failover và plugin discovery nếu liên quan.

### Bước 10: Ghi nhận và ngăn tái diễn

Pin versions, thêm compatibility tests và CI gates, xóa workaround tạm và cập nhật runbook.

## 32. Minimal reproduction hiệu quả thế nào?

Một reproduction nên giữ **đúng những thành phần tạo mismatch** và loại bỏ yếu tố không liên quan.

Ví dụ AME chỉ cần:

~~~text
api-v1 Task.class
impl-v1 LegacyTask.class (compile với api-v1)
api-v2 Task.class (thêm cancel)
client-v2 Main.class (compile với api-v2)
runtime: client-v2 + impl-v1 + api-v2
~~~

Khi reproduction còn lỗi, nguyên nhân có khả năng nằm ở versioning/ABI hơn là Spring configuration hay network.

### 32.1. Đừng vô tình compile lại mọi thứ

Nếu cùng một Gradle task compile lại implementation cũ theo API V2, javac có thể chặn source không đáp ứng contract. Điều đó làm reproduction thất bại **ở compile time**, không còn tái hiện runtime AME.

Muốn hiểu binary compatibility, phải giữ artifact binary đã được build ở version cũ.

### 32.2. Dùng đúng binary runtime

Trường hợp production lỗi có thể đến từ một plugin JAR cũ. Reproduction dùng source được biên dịch lại theo compiler mới có thể không lặp lỗi. Hãy dùng bản binary thực tế nếu việc chia sẻ và kiểm thử cho phép.

## 33. Test gì để ngăn AbstractMethodError?

### 33.1. Interface implementation compatibility tests

Nếu một SPI có nhiều implementations:

- Load tất cả implementations được hỗ trợ.
- Gọi các methods trong hợp đồng mới.
- Chạy tests với **API version đúng target**.
- Nếu plugin là artifact riêng, test plugin binary với runtime host mới.
- Ghi rõ unsupported plugin versions và từ chối load sớm nếu có thể.

### 33.2. Contract test ví dụ

~~~java
interface CancelableTask {
    void execute();
    void cancel();
}
~~~

Một contract test có thể kiểm tra:

~~~java
void assertCancelable(CancelableTask task) {
    task.execute();
    task.cancel();
}
~~~

Đoạn code biểu thị ý tưởng; việc gọi `cancel()` có thể cần test fixture, setup/cleanup hoặc assertions cụ thể về state.

### 33.3. Không chỉ instantiate class

Khởi tạo provider không nhất thiết gọi mọi interface method. Test phải thực sự kích hoạt các methods đã thêm hoặc những dynamic dispatch paths có nguy cơ.

## 34. Test gì để ngăn IncompatibleClassChangeError?

Các trường hợp đáng đưa vào regression:

- Client binary cũ chạy cùng library mới.
- Client mới chạy cùng library cũ nếu đó là rollout scenario được hỗ trợ.
- Interface default methods trong các inheritance graphs thực tế.
- Reflection/MethodHandle/method references phù hợp.
- Generated/proxy classes dùng static/instance invocations.
- Plugin loader và service discovery.
- Multi-release JAR variants.
- External WAR/application server deployment.

Nếu public API đổi instance ↔ static, cần quyết định **có hỗ trợ binary cũ không**; nếu không, phải đảm bảo mọi consumer được rebuild/deploy đồng bộ trước khi đưa library mới vào runtime.

## 35. CI binary compatibility gates

Một dự án thư viện có public API cần cơ chế phát hiện ABI-breaking changes trước khi phát hành.

Các kỹ thuật có thể gồm:

- So public class/method/field signatures giữa releases.
- So method descriptors và static flags.
- So inheritance/interface relationships.
- Dùng binary compatibility checker phù hợp với Java ecosystem.
- Compile consumer fixtures với bản cũ, chạy chúng với bản mới.
- Test service implementations/plugin binaries.
- Test shading/fat JAR/WAR artifact cuối.
- Chạy ma trận JDK mục tiêu và module/classpath modes.

### 35.1. Không chỉ dùng semantic version

SemVer có thể hỗ trợ communication về compatibility, nhưng một version số **không tự chứng minh binary-compatible**. Cần evidence và support matrix.

### 35.2. Dependency locking giúp tái lập, không xác thực ABI

Một lockfile giữ nguyên versions của dependency graph, nhưng nếu implementation JAR vốn không tương thích với API, lỗi vẫn tồn tại. Locks giúp biết chắc đã chạy trên **tổ hợp nào**, còn compatibility tests xác định tổ hợp đó hoạt động ra sao.

## 36. Tổ hợp kiểm thử theo JDK và classpath

Ví dụ dự án chuyển Java 11 → 17:

| Hạng mục | Java 11 | Java 17 | Bằng chứng |
|---|---|---|---|
| Compile sources | Theo support policy | PASS/FAIL | Build logs |
| App startup | PASS/FAIL | PASS/FAIL | Startup logs |
| API/implementation ABI | PASS/FAIL | PASS/FAIL | ABI report |
| SPI implementations | PASS/FAIL | PASS/FAIL | Contract tests |
| Client binary compatibility | PASS/FAIL | PASS/FAIL | Old/new client tests |
| Runtime dependency graph | Reviewed | Reviewed | Lockfile/tree |
| Plugin loading | PASS/FAIL | PASS/FAIL | Plugin tests |
| Framework integration | PASS/FAIL | PASS/FAIL | Integration tests |
| MRJAR class selection | Nếu áp dụng | Nếu áp dụng | Variant tests |
| Packaged deployment | PASS/FAIL | PASS/FAIL | JAR/WAR/container logs |
| Security/serialization | PASS/FAIL | PASS/FAIL | Contract fixtures |

Các ô `PASS/FAIL` là placeholder, không phải kết quả đã chạy. Nếu dự án ngừng hỗ trợ Java 11, vẫn hữu ích giữ baseline trước nâng để phân biệt regression, nhưng không cần duy trì một release test matrix vô hạn.

## 37. JVM module system và accessibility

Trong Java 9+, JPMS có thể làm code cũ truy cập internal packages thất bại. Lỗi phổ biến liên quan:

- `IllegalAccessError`.
- `InaccessibleObjectException` khi deep reflection.
- `NoClassDefFoundError` nếu dependency module/class không hiện diện.

Những lỗi này **không đồng nghĩa AME hoặc ICCE trực tiếp**, dù một số subtype có quan hệ class hierarchy với ICCE.

### 37.1. Khi nào dùng --add-opens?

`--add-opens` có thể cấp quyền deep reflective access theo cách cụ thể, nhưng không tạo concrete method body và không sửa static/instance mismatch. Một lỗi `AbstractMethodError` không được chữa bằng mở package module.

### 37.2. Khi nào dùng --add-exports?

`--add-exports` ảnh hưởng module exports/access, không biến method descriptor hoặc class/interface nature. Nếu binary ABI đã đổi, cần đồng bộ library và client.

## 38. Hot redeploy, caching và lỗi chỉ trên production

Trong application server hoặc plugin system:

- Container có thể giữ shared JAR phiên bản cũ.
- WAR mới được deploy nhưng exploded directory còn file cũ.
- Class loaders khác nhau dùng artifacts khác.
- Một service node chưa được nâng.
- Rolling update tạo giai đoạn chạy cả client/host versions.
- Generated classes/proxies được cache theo classloader.
- MRJAR variant khác nhau theo Java runtime node.

### 38.1. Cần ghi version từng node

Nếu lỗi chỉ ở node B, hãy đối chiếu:

~~~text
Node A:
  JDK 17
  app checksum X
  SPI 2.0
  implementation 2.0

Node B:
  JDK 17
  app checksum X
  SPI 2.0
  implementation 1.0  <-- ứng viên mismatch
~~~

Đây là ví dụ giả định. Trong thực tế phải thu thập checksums, resolved libraries, class loading evidence và deployment logs.

### 38.2. Restart đôi khi chỉ che lỗi

Restart có thể làm process nạp thư viện đúng do classpath tạm thay đổi, nhưng nếu artifact deployment vẫn không nhất quán, lỗi có thể tái diễn. Cần sửa packaging/dependency ownership để duy trì giải pháp.

## 39. Những sai lầm chẩn đoán thường gặp

### 39.1. Bắt Error rồi bỏ qua

AME/ICCE thường là dấu hiệu runtime bị lệch binary contracts. Catch để tránh crash mà không sửa nguồn có thể tạo dữ liệu không nhất quán và che rủi ro.

### 39.2. Coi JDK là thủ phạm duy nhất

JDK upgrade thường đi cùng framework/library/tool updates. Trước tiên xác định JAR class thực tế được nạp.

### 39.3. Chỉ đọc compileClasspath

Runtime, test, WAR/server classpaths có thể khác. Một library cũ được container inject không xuất hiện ở Gradle compile classpath.

### 39.4. Chỉ so method name

Method descriptor, static flags, inheritance, bridge methods và opcode quan trọng. Cùng tên method không bảo đảm ABI giống.

### 39.5. Không thử code path mới

Startup test không gọi method mới được thêm vào interface, nên AME có thể chỉ xuất hiện ở production.

### 39.6. Force transitive dependency lên mới nhất

Có thể tạo ABI mismatch với thư viện cha. Ưu tiên compatibility matrix và nâng theo nhóm.

### 39.7. Dựa vào source thay vì binary

Production có thể load JAR cũ. Dùng `javap` và classloader logs để kiểm tra class file thật.

### 39.8. Nhầm classloader constraint với lỗi method thiếu

Một số lỗi có message về loader constraint, duplicate class hoặc type identity khác. Phải xem exact error subtype và resolution context.

### 39.9. Tắt bytecode instrumentation thay vì sửa

Nếu lỗi chỉ xảy ra khi agent bật, cần điều tra agent và bytecode transformation. Tắt coverage/monitoring có thể chỉ che vấn đề ở pipeline.

### 39.10. Chỉ rebuild application mà không rebuild plugin

Nếu plugin implementation do vendor/đội khác phát hành, application rebuild không sửa plugin binary cũ. Cần version/compatibility management.

## 40. Mẫu incident report cho AME/ICCE

~~~yaml
linkageIncident:
  application: "orders-service"
  error:
    class: "java.lang.AbstractMethodError"
    message: "paste-exact-runtime-message"
    callSite: "com.example.orders.Worker.shutdown"
    methodOwner: "com.example.spi.Service"
    methodDescriptor: "()V"
    receiverClass: "com.example.vendor.LegacyAdapter"
  environment:
    jdk: "record-exact-version"
    runtimeContainer: "record-version"
    artifactChecksum: "record-checksum"
  linkage:
    compileApiVersion: "unknown"
    runtimeApiVersion: "unknown"
    implementationVersion: "unknown"
    classLoader: "unknown"
    jarSource: "unknown"
  investigation:
    stackTraceCaptured: false
    dependencyGraphCompared: false
    javapDescriptorsCompared: false
    runtimeClassSourceVerified: false
    minimalReproductionCreated: false
  remediation:
    action: "upgrade-or-rebuild-implementation"
    owner: "application-team"
    rollbackPlan: "pending"
  validation:
    failingPathRetested: false
    integrationPassed: false
    packagedRuntimeVerified: false
  status: "under-investigation"
~~~

Đây là **mẫu** có values giả định, không phải kết quả xử lý incident thực tế. Với lỗi ICCE static/instance, thay các fields bằng opcode, static flags và method owner phù hợp.

## 41. Checklist dành cho người chẩn đoán

- [ ] Đã xác nhận concrete error type là AME, ICCE trực tiếp hay một subclass khác.
- [ ] Đã lưu nguyên văn message/stack trace/JDK/container/version.
- [ ] Đã xác định failing method/field owner và descriptor.
- [ ] Đã biết receiver class runtime, nếu invocation có receiver.
- [ ] Đã phân biệt method missing, abstract implementation missing và static/instance mismatch.
- [ ] Đã xem default interface method conflicts nếu inheritance graph liên quan.
- [ ] Đã kiểm tra class/interface nature và binary hierarchy.
- [ ] Đã so source API với class files thực tế bằng `javap`.
- [ ] Đã kiểm tra bridge methods/covariant returns nếu liên quan.
- [ ] Đã xác định JAR/nested JAR/container library thực sự nạp class.
- [ ] Đã xem cả compileClasspath, runtimeClasspath và testRuntimeClasspath.
- [ ] Đã xem Maven/Gradle BOM, transitive mediation và overrides.
- [ ] Đã kiểm tra plugin/API/server-provided artifacts.
- [ ] Đã xem multi-release JAR variant theo JDK đang chạy nếu có.
- [ ] Đã kiểm tra Java agents/generated bytecode nếu stack trace liên quan.
- [ ] Đã tạo reproduction giữ nguyên binary version cũ khi cần.
- [ ] Đã chọn bản implementation/API tương thích hoặc rebuild đầy đủ.
- [ ] Đã chạy failing code path trên packaged runtime thật.
- [ ] Đã có contract/integration/rollout/rollback tests phù hợp.
- [ ] Đã ghi lại nguyên nhân và thêm gate để không tái diễn.

Checklist là hướng dẫn thực hành, **không phải bằng chứng một dự án cụ thể đã thực hiện đầy đủ các bước**.

## 42. Tóm tắt phân biệt nhanh

| Câu hỏi | AbstractMethodError | IncompatibleClassChangeError trực tiếp |
|---|---|---|
| Có phải linkage-related? | Có | Có |
| Quan hệ inheritance | Subclass của ICCE | Subclass của LinkageError |
| Dấu hiệu phổ biến | Receiver thiếu concrete implementation | Static/instance mismatch hoặc ambiguous defaults |
| Có thể compile pass trước đó? | Có | Có |
| Có thể xuất hiện chỉ lúc method được gọi? | Có | Có |
| Root cause điển hình | New interface/abstract contract + old implementation | Client bytecode expectation khác actual member/class nature |
| Bằng chứng hữu ích | Interface method + receiver class + hierarchy | Invocation opcode + flags + runtime class |
| Sửa gốc | Nâng/rebuild implementation hoặc adapter đúng contract | Đồng bộ ABI của client/library, sửa default conflict |
| Có dùng --add-opens để sửa không? | Không | Không |
| Có nên catch Error rồi bỏ qua? | Không | Không |

**Đặc biệt:** khi exception hiển thị `java.lang.AbstractMethodError` thì nó đồng thời **là một IncompatibleClassChangeError về mặt type hierarchy**, nhưng nội dung chẩn đoán cụ thể phải dựa trên subtype AME. Không nên phân biệt hai lỗi như hai nhánh hoàn toàn độc lập.

## 43. Nguyên tắc tổng kết

- **`AbstractMethodError` là subclass của `IncompatibleClassChangeError`**, cả hai đều là `LinkageError`/`Error`, không phải business exceptions.
- **AME thường báo thiếu implementation concrete tại method invocation**, ví dụ API thêm abstract method nhưng implementation binary cũ chưa đáp ứng.
- **ICCE trực tiếp thường phản ánh mismatch dạng binary**, như instance ↔ static method/field hoặc xung đột interface default methods.
- **Các lỗi liên quan như `NoSuchMethodError`, `IllegalAccessError` và `NoSuchFieldError` là những trường hợp riêng** cần chẩn đoán theo subtype và message.
- **Compiler pass không bảo đảm runtime linkage** khi client, API và implementations được compile/deploy từ những phiên bản khác nhau.
- **Method descriptors, invocation opcodes, static/abstract flags và class hierarchy** quan trọng hơn tên method nhìn từ source.
- **Dùng `javap` để xem binary thực tế, class loading logs để biết nguồn class và dependency graph để tìm mismatch**; không chỉ nhìn source/IDE.
- **Nâng JDK thường làm lỗi ABI có sẵn lộ ra qua framework/dependency/plugin updates**, không nhất thiết do JVM mới sai.
- **Classpath, custom classloader, external WAR/server libraries và multi-release JARs** có thể tạo tổ hợp runtime khác build.
- **Thêm default method có thể giảm rủi ro từ interface abstract mới nhưng cũng có thể tạo conflict**, nên vẫn cần test.
- **Rebuild đúng implementation, chọn compatibility set và test packaged runtime** là hướng khắc phục ưu tiên, không catch lỗi để bỏ qua.
- **Đưa binary compatibility checks, SPI contract tests và cross-version tests vào CI** giúp phát hiện lỗi trước production.
- **Rolling upgrades và rollback phải xét cả API implementations và plugin artifacts**, không chỉ application jar.

Trong **Java Advance Compatibility Migration**, chẩn đoán `AbstractMethodError` và `IncompatibleClassChangeError` hiệu quả bắt đầu bằng câu hỏi **“class file mà caller đã biên dịch kỳ vọng gì, và JVM thực tế đã nạp implementation nào?”**. Khi truy vết đúng API version, method descriptor, classloader và runtime artifact, phần lớn các lỗi liên kết tưởng như khó hiểu trở thành những bất nhất nhị phân có thể tái hiện, sửa ở nguồn và ngăn tái diễn bằng quy trình build/test có kiểm soát.
