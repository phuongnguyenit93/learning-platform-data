# ClassDefinition và redefineClasses khi được hỗ trợ

Khi một lớp đã được JVM nạp, việc ghi đè tệp `.class` trên đĩa không tự thay mã mà ứng dụng đang chạy. `Instrumentation.redefineClasses(...)` là cơ chế yêu cầu JVM cập nhật định nghĩa của lớp đã có bằng dữ liệu class file mới.

`ClassDefinition` ghép **đúng đối tượng `Class<?>` cần cập nhật** với **byte của bản định nghĩa mới**. Nó không tạo một lớp có danh tính khác và không tạo lại các đối tượng đang tồn tại.

## 1. Hiểu yêu cầu thay lớp

Tình huống học tập: một đối tượng đã được tạo bằng lớp `Counter`. Ta muốn sửa nội dung phương thức `describe()` nhưng giữ giá trị trường của đối tượng đó.

```text
Class<Counter> đã nạp + byte Counter phiên bản mới
                      |
                      v
             new ClassDefinition(...)
                      |
                      v
          Instrumentation.redefineClasses(...)
                      |
                      v
      Lời gọi phương thức tiếp theo dùng mã mới
      Đối tượng và trạng thái đã có được giữ lại
```

Phân biệt ba thao tác:

| Thao tác | Bạn cung cấp gì? | Mục đích |
| --- | --- | --- |
| Định nghĩa lớp lần đầu | Byte để bộ nạp định nghĩa lớp | Tạo lớp trong JVM |
| `redefineClasses` | `ClassDefinition` chứa lớp đã nạp và byte thay thế | Cập nhật định nghĩa lớp đó |
| `retransformClasses` | Các `Class<?>` đã nạp | Yêu cầu chạy lại cơ chế biến đổi theo hợp đồng retransformation |

Bài này thực hành trường hợp thứ hai: chủ động cung cấp một bản class file đã biên dịch. Không dùng một bộ nạp mới để tạo bản sao của `Counter`, và không cần cơ chế gắn agent vào JVM đang chạy.

## 2. ClassDefinition chỉ mô tả một cặp lớp–byte

Cách tạo yêu cầu:

```java
ClassDefinition definition = new ClassDefinition(targetClass, replacementBytes);
```

Hai phương thức đọc lại:

```java
Class<?> target = definition.getDefinitionClass();
byte[] bytes = definition.getDefinitionClassFile();
```

Các dòng trên là đoạn minh họa khi đã có biến đầu vào.

Tạo `ClassDefinition` chưa gọi JVM thay lớp. Constructor giữ tham chiếu đến mảng đầu vào, không sao chép mảng. Vì vậy, không để luồng khác sửa byte trong lúc đang sử dụng yêu cầu; có thể chủ động truyền bản sao nếu cần tách quyền sở hữu dữ liệu.

`targetClass` phải là lớp thực sự muốn cập nhật. Trong ứng dụng có nhiều bộ nạp, hai lớp cùng tên có thể là hai kiểu khác nhau: chỉ tên đầy đủ chưa đủ để chọn đúng đích. Dữ liệu thay thế phải mô tả đúng tên lớp đích, phiên bản class file tương thích và cấu trúc hợp lệ.

Xem [API ClassDefinition](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html).

## 3. “Khi được hỗ trợ” có ba lớp kiểm tra

### 3.1. Agent yêu cầu khả năng redefine

Manifest của agent:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.RedefineAgent
Can-Redefine-Classes: true

```

Có dòng trống cuối tệp. `Can-Redefine-Classes` không thay cho `Premain-Class`: hai thuộc tính có vai trò khác nhau.

### 3.2. Kiểm tra khả năng của JVM và agent hiện tại

```java
boolean supported = inst.isRedefineClassesSupported();
```

Không xem việc đã thêm thuộc tính manifest là bằng chứng đủ rằng mọi JVM đều thực hiện được.

### 3.3. Kiểm tra lớp cụ thể

```java
boolean modifiable = inst.isModifiableClass(targetClass);
```

Hai câu hỏi khác nhau: môi trường có hỗ trợ thao tác không, và lớp này có thể sửa được không? Kết quả `true` của cả hai vẫn chưa bảo đảm **mọi bản byte mới** đều hợp lệ. JVM còn kiểm tra giới hạn thay đổi và dữ liệu lớp.

Ví dụ thực hành sẽ dừng có thông báo khi một khả năng không có, thay vì mặc định thao tác chắc chắn thành công. Hợp đồng các kiểm tra nằm trong [Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).

## 4. Ví dụ hoàn chỉnh: cập nhật phương thức, giữ đối tượng cũ

Ví dụ dùng JDK 17+ và một agent khởi động bằng `-javaagent`. Ứng dụng gọi một cầu nối nhỏ của agent để gửi yêu cầu thay lớp tại thời điểm xác định, sau khi đã tạo đối tượng.

### 4.1. Bố trí tệp

```text
redefine-demo/
├── agent.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   └── RedefineAgent.java
│       └── app/
│           ├── Counter.java
│           └── Main.java
└── replacement-src/
    └── demo/
        └── app/
            └── Counter.java
```

Hai bản `Counter` có cùng tên lớp đầy đủ và được biên dịch riêng.

### 4.2. Agent giữ Instrumentation và kiểm tra điều kiện

Tệp `src/demo/agent/RedefineAgent.java`:

```java
package demo.agent;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
    }

    public static boolean replace(Class<?> target, byte[] replacement) throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        boolean supported = inst.isRedefineClassesSupported();
        System.out.println("supported=" + supported);
        if (!supported) {
            System.out.println("skip=unsupported");
            return false;
        }
        boolean modifiable = inst.isModifiableClass(target);
        System.out.println("modifiable=" + modifiable);
        if (!modifiable) {
            System.out.println("skip=unmodifiable");
            return false;
        }
        inst.redefineClasses(new ClassDefinition(target, replacement));
        return true;
    }
}
```

`premain` chỉ lưu đối tượng `Instrumentation` do JVM cấp. Phương thức `replace` là cầu nối riêng của ví dụ; nó không phải API chuẩn Java.

Nếu agent chưa khởi động, mã báo rõ thiếu `-javaagent`. Nếu môi trường hoặc lớp không hỗ trợ, mã trả `false`. Nếu dữ liệu thay thế có lỗi, ví dụ để lỗi truyền ra để người học nhìn thấy nguyên nhân, không in thông báo thành công giả.

### 4.3. Lớp ban đầu

Tệp `src/demo/app/Counter.java`:

```java
package demo.app;

public class Counter {
    private int value;
    private static int starts;

    static {
        starts++;
        System.out.println("counter.init");
    }

    public Counter(int value) {
        this.value = value;
    }

    public String describe() {
        return "V1:" + value + ":" + starts;
    }
}
```

`value` là trạng thái của từng đối tượng. `starts` là trạng thái tĩnh dùng để quan sát số lần khởi tạo lớp trong thí nghiệm.

### 4.4. Bản lớp thay thế

Tệp `replacement-src/demo/app/Counter.java`:

```java
package demo.app;

public class Counter {
    private int value;
    private static int starts;

    static {
        starts++;
        System.out.println("counter.init");
    }

    public Counter(int value) {
        this.value = value;
    }

    public String describe() {
        return "V2:" + value + ":" + starts;
    }
}
```

Giữ nguyên tên lớp, các trường, constructor và chữ ký phương thức. Chỉ phần thân `describe()` đổi tiền tố trả về từ `V1:` thành `V2:`.

### 4.5. Ứng dụng điều khiển thí nghiệm

Tệp `src/demo/app/Main.java`:

```java
package demo.app;

import demo.agent.RedefineAgent;
import java.nio.file.Files;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) throws Exception {
        Counter existing = new Counter(7);
        Class<?> identity = existing.getClass();
        System.out.println("before=" + existing.describe());
        byte[] replacement = Files.readAllBytes(Path.of(args[0]));
        if (RedefineAgent.replace(Counter.class, replacement)) {
            System.out.println("after=" + existing.describe());
            System.out.println("same.class=" + (identity == existing.getClass()));
            System.out.println("new=" + new Counter(9).describe());
        }
    }
}
```

Ứng dụng nhận một đối số: đường dẫn đến class file thay thế. Nó gọi `describe()` trên **cùng đối tượng `existing`** trước và sau thao tác.

### 4.6. Biên dịch, đóng gói và chạy

Lưu các tệp UTF-8 không BOM. Mở PowerShell tại `redefine-demo`, dùng JDK có `javac`, `jar`, `java` trong `PATH`.

```powershell
New-Item -ItemType Directory -Force out/agent, out/app, out/replacement, dist | Out-Null

javac --release 17 -d out/agent src/demo/agent/RedefineAgent.java
javac --release 17 -cp out/agent -d out/app src/demo/app/Counter.java src/demo/app/Main.java
javac --release 17 -d out/replacement replacement-src/demo/app/Counter.java

jar --create --file dist/redefine-agent.jar --manifest agent.mf -C out/agent .

java '-javaagent:dist/redefine-agent.jar' -cp 'out/app;dist/redefine-agent.jar' demo.app.Main out/replacement/demo/app/Counter.class
```

Chỉ tiếp tục sau khi từng lệnh thành công. Dấu `;` trong classpath là cú pháp Windows; trên Linux/macOS dùng `:`.

Bản thay thế nằm ở `out/replacement`, không nằm trong classpath ứng dụng. Ứng dụng đọc nó như dữ liệu, nên không vô tình nạp ngay bản `V2` thay cho bản gốc. `Main` phụ thuộc cầu nối agent, vì vậy cần classpath tương ứng khi biên dịch và chạy.

Stdout quan sát được trên OpenJDK 24.0.2:

```text
counter.init
before=V1:7:1
supported=true
modifiable=true
after=V2:7:1
same.class=true
new=V2:9:1
```

Mã đã được biên dịch với `--release 17`. Kết quả trên mô tả môi trường hỗ trợ thao tác, không cam kết mọi JVM đều in hai dòng khả năng bằng `true`.

Đọc từng bằng chứng:

- `before=V1:7:1`: đối tượng và lớp đã được sử dụng trước khi thay.
- `after=V2:7:1`: mã phương thức đổi nhưng giá trị đối tượng cũ vẫn là `7`.
- `same.class=true`: tham chiếu `Class` được giữ lại vẫn khớp.
- Chỉ có một dòng `counter.init`; `starts` vẫn là `1`.
- Đối tượng mới nhận giá trị `9` và cũng dùng phương thức `V2`.

### 4.7. Kiểm tra nhánh thiếu khả năng

Tạo thêm `no-capability.mf` với nội dung:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.RedefineAgent

```

Đóng gói riêng và chạy một JVM mới, chỉ có agent này:

```powershell
jar --create --file dist/no-capability-agent.jar --manifest no-capability.mf -C out/agent .

java '-javaagent:dist/no-capability-agent.jar' -cp 'out/app;dist/no-capability-agent.jar' demo.app.Main out/replacement/demo/app/Counter.class
```

Stdout đã kiểm chứng trên cùng môi trường:

```text
counter.init
before=V1:7:1
supported=false
skip=unsupported
```

Đây là nhánh xử lý có chủ đích. Ứng dụng không gọi `redefineClasses` sau khi biết khả năng cần dùng không có.

## 5. Giới hạn thay đổi phải hiểu đúng

Trong hợp đồng chuẩn hiện hành, thay phần thân phương thức là mục tiêu phù hợp. Không dùng `redefineClasses` như một phép thay đổi tùy ý cấu trúc đối tượng.

| Thay đổi dự định | Đánh giá theo hợp đồng chuẩn |
| --- | --- |
| Đổi nội dung tính toán hoặc chuỗi trong phương thức | Có thể thực hiện nếu dữ liệu hợp lệ |
| Thêm, xóa hoặc đổi tên trường/phương thức | Không được phép |
| Đổi chữ ký phương thức, bộ sửa đổi hoặc quan hệ kế thừa | Không được phép |
| Đổi các thuộc tính cấu trúc như `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses` | Không được phép |

Những giới hạn này được mô tả trong [JVM TI RedefineClasses](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html#RedefineClasses). Không suy ra rằng một JVM mở rộng hoặc công cụ riêng có thể đổi cấu trúc thì mọi môi trường Java đều hỗ trợ như vậy.

Việc thay lớp không chạy lại khối khởi tạo tĩnh, không đặt lại trường tĩnh và không xây dựng lại đối tượng cũ. Nếu một lời gọi phương thức đang có khung thực thi hoạt động, nó tiếp tục chạy mã phiên bản cũ; lời gọi mới dùng phiên bản mới. Xem [quy tắc trạng thái sau redefine](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)).

Vì vậy, cập nhật phương thức không tự chuyển đổi dữ liệu cũ sang một mô hình trạng thái khác. Trong ví dụ, các lời gọi trước và sau được thực hiện tuần tự, nên không có khung `describe()` cũ đang hoạt động khi thay lớp.

## 6. Nhiều lớp, transformer và lỗi

Có thể gửi một tập lớp trong cùng lời gọi:

```java
inst.redefineClasses(
    new ClassDefinition(classA, bytesA),
    new ClassDefinition(classB, bytesB)
);
```

Đây là đoạn minh họa với các biến đã được chuẩn bị. Không thay bằng hai lời gọi riêng nếu yêu cầu cần cả tập được kiểm tra và cập nhật cùng nhau. Nếu thao tác thất bại, không lớp nào trong tập được cài định nghĩa mới. Điều này không có nghĩa các thao tác khác của chương trình, chẳng hạn ghi tệp trước đó, được hoàn tác.

Nếu đã đăng ký transformer, yêu cầu redefine vẫn có thể đi qua chuỗi biến đổi. Byte cuối cùng được JVM kiểm tra có thể là kết quả sau chuỗi đó. Ví dụ hiện tại không đăng ký transformer để cô lập vai trò của `ClassDefinition`.

Các lỗi thường gặp:

| Lỗi | Cần kiểm tra |
| --- | --- |
| `UnsupportedOperationException` | Thiếu khả năng redefine hoặc yêu cầu thay đổi cấu trúc không hỗ trợ |
| `UnmodifiableClassException` | Lớp cụ thể không sửa được |
| `ClassFormatError` | Dữ liệu không phải class file hợp lệ |
| `NoClassDefFoundError` do tên không khớp | Byte đang mô tả lớp khác với lớp đích |
| `UnsupportedClassVersionError` | Bản thay thế được biên dịch cho Java mới hơn JVM chạy |

Danh sách là các trường hợp tiêu biểu, không phải toàn bộ khả năng lỗi; xem [hợp đồng redefineClasses và các lỗi](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)). Các lớp lỗi kết thúc bằng `Error` không được bắt bằng `catch (Exception e)`.

Một quy trình dễ kiểm tra là: chọn đúng `Class` → đọc đúng byte → kiểm tra khả năng và lớp → gửi yêu cầu → chỉ xác nhận thành công sau khi lời gọi trả về bình thường.

## 7. Tự thực hành

1. Đổi tiền tố bản thay thế thành `V3:`, biên dịch lại riêng bản thay thế rồi chạy một JVM mới.
2. Thêm một trường vào bản thay thế và quan sát yêu cầu bị từ chối; giải thích vì sao hai phép kiểm tra khả năng không bảo đảm bản byte đó hợp lệ.
3. Chuyển nhầm bản thay thế vào classpath trước bản gốc: vì sao thí nghiệm không còn chứng minh việc cập nhật từ `V1`?
4. Giải thích vì sao `after` giữ `7`, đối tượng mới có `9`, và cả hai đều thấy `starts=1`.

Điểm cốt lõi cần giữ: `ClassDefinition` mô tả bản cập nhật của một lớp đã có; `redefineClasses` yêu cầu JVM áp dụng bản cập nhật trong giới hạn hỗ trợ, đồng thời giữ danh tính lớp và trạng thái đang tồn tại.
