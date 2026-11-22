# Giới hạn thay đổi cấu trúc lớp khi định nghĩa lại

## 1. Khái niệm: thay mã thực thi khác với thay hình dạng của lớp

Java agent có thể dùng `Instrumentation.redefineClasses` để cung cấp định nghĩa mới cho một lớp đã được JVM nạp. Khả năng này hữu ích khi thay phần triển khai của phương thức trong lúc chương trình đang chạy.

Tuy nhiên, lớp đã nạp không còn là một tệp `.class` độc lập trên đĩa. Trong JVM đã có:

- Đối tượng `Class` đại diện cho lớp.
- Những đối tượng đã được tạo từ lớp đó.
- Các trường chứa trạng thái hiện tại.
- Những lớp khác đã liên kết tới trường và phương thức của nó.
- Những lời gọi phương thức có thể vẫn đang thực thi.

Vì vậy, cần phân biệt:

```text
Thay phần triển khai:
    cùng trường, cùng phương thức, cùng kiểu và hệ kế thừa
    nhưng thay các lệnh bên trong phương thức

Thay cấu trúc:
    thêm/xóa trường, thêm/xóa phương thức, đổi kiểu hoặc hệ kế thừa
```

Định nghĩa lại theo hợp đồng chuẩn của Java Instrumentation không phải cơ chế tùy ý đổi cấu trúc của mọi lớp đã nạp. **Một lớp có thể sửa được không đồng nghĩa mọi thay đổi đối với lớp đó đều được chấp nhận.**

API định nghĩa lại có từ Java 5 và vẫn được dùng trên JDK hiện đại. Bài đối chiếu hợp đồng JDK 26 và dùng mã nguồn JDK 17+ để thực hành. Các khả năng mở rộng riêng của một JVM/công cụ không được xem là bảo đảm của API chuẩn.

## 2. Cơ chế định nghĩa lại lớp đã nạp

Luồng tối giản:

```text
Lớp đã được nạp và có thể đã có đối tượng
    ↓
Agent đọc dữ liệu class file mới
    ↓
new ClassDefinition(lớp_đích, dữ_liệu_mới)
    ↓
Instrumentation.redefineClasses(...)
    ↓
Dữ liệu đi qua các transformer phù hợp, nếu có
    ↓
JVM kiểm tra tính hợp lệ và giới hạn thay đổi
    ├─ hợp lệ: cài định nghĩa mới
    └─ không hợp lệ: từ chối
```

`ClassDefinition` liên kết một đối tượng `Class<?>` cụ thể với mảng byte mới. Nó không tạo ra một lớp mới có tên khác và cũng không tự nạp lại cả ứng dụng.

Dữ liệu mới phải là class file hợp lệ, mang đúng tên lớp. Cùng tên nhưng thuộc bộ nạp lớp khác vẫn là một lớp khác trong JVM; cần xác định đúng đối tượng `Class`, không chỉ tìm một chuỗi tên trùng nhau.

Ba điều kiện phải được kiểm tra riêng:

| Điều kiện | Cách nhận biết |
| --- | --- |
| Agent/JVM có khả năng định nghĩa lại | Manifest khai báo phù hợp và `isRedefineClassesSupported()` trả `true` |
| Lớp cụ thể thuộc loại sửa được | `isModifiableClass(type)` trả `true` |
| Bản thay thế không vi phạm hợp đồng | So sánh cấu trúc, kiểm tra dữ liệu và để JVM xác minh |

Hai kiểm tra API đầu không chứng nhận bản class file bất kỳ sẽ được chấp nhận. Lớp mảng và lớp biểu diễn kiểu nguyên thủy không thuộc loại sửa được bằng cơ chế này.

Manifest của agent cần có:

```text
Can-Redefine-Classes: true
```

Thuộc tính này xin khả năng cần thiết; nó không tự gọi `redefineClasses` và không bỏ qua các giới hạn cấu trúc.

## 3. Những thay đổi nào được phép và bị giới hạn?

Theo hợp đồng chuẩn được đối chiếu trong bài, định nghĩa lại có thể thay thân phương thức, bảng hằng và các thuộc tính không bị cấm. Nó không cho phép các thay đổi cấu trúc sau:

| Thay đổi | Kết luận với lớp đã nạp |
| --- | --- |
| Thay phép tính hoặc câu lệnh bên trong một phương thức có sẵn | Có thể thực hiện nếu dữ liệu đầu ra hợp lệ và giữ các ràng buộc khác |
| Thêm biến cục bộ bên trong thân phương thức | Có thể thực hiện; biến cục bộ không phải trường của đối tượng |
| Thêm/xóa/đổi tên trường | Không được phép theo hợp đồng này |
| Đổi kiểu trường, ví dụ `int` thành `long` | Là thay đổi cấu trúc không được phép |
| Thêm/xóa/đổi tên phương thức | Không được phép |
| Đổi danh sách tham số hoặc kiểu trả về trong mô tả phương thức của JVM | Không được phép |
| Thêm một overload hoặc một constructor mới | Là thêm phương thức; không được phép |
| Đổi modifier, như từ instance sang `static`, hoặc thay quyền truy cập | Không được phép |
| Đổi lớp cha hoặc danh sách interface triển khai | Không được phép |
| Đổi các thuộc tính `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses` | Không được phép |

“Có thể thực hiện” không có nghĩa JVM sẽ chấp nhận mọi byte được trả về. Lệnh JVM phải đúng kiểu, tham chiếu phải hợp lệ và cấu trúc class file phải được kiểm tra thành công.

### 3.1. Biến cục bộ không phải trường

Thay thân phương thức từ:

```java
public int price(int amount) {
    return amount * 2;
}
```

thành:

```java
public int price(int amount) {
    int result = amount * 3;
    return result;
}
```

vẫn giữ tên, mô tả phương thức và các trường của lớp. `result` nằm trong phạm vi thực thi của phương thức; nó không làm mọi đối tượng cần thêm một trường.

Hai đoạn này chỉ minh họa thay đổi thân phương thức, không phải tệp Java độc lập.

Ngược lại, thêm:

```java
private int cachedResult;
```

là thêm trường. Đổi trường đó thành `private static` cũng không làm thao tác trở nên hợp lệ: trường tĩnh vẫn là một phần cấu trúc lớp.

### 3.2. Overload và constructor cũng thuộc cấu trúc

Nếu lớp ban đầu có `price(int)`, thêm `price(long)` là thêm một phương thức chứ không phải sửa thân phương thức cũ.

Constructor được biểu diễn bằng phương thức khởi tạo `<init>` trong class file. Có thể thay phần triển khai của constructor đã có nếu giữ đúng ràng buộc; không thể thêm tùy ý một overload constructor trong lần định nghĩa lại.

Bộ khởi tạo tĩnh được thể hiện bằng `<clinit>` khi lớp cần nó. Phải kiểm tra dữ liệu biên dịch thực tế: một thay đổi nguồn tưởng nhỏ có thể làm xuất hiện hoặc biến mất một phương thức đặc biệt.

### 3.3. Record, sealed class và lớp lồng nhau

Không chỉ danh sách trường/phương thức cần được giữ phù hợp:

- Thay thành phần record có thể kéo theo thay đổi trường, accessor, constructor và thuộc tính `Record`.
- Thay danh sách lớp con được phép của sealed class liên quan `PermittedSubclasses`.
- Thay cấu trúc các lớp lồng nhau có thể ảnh hưởng `NestHost`/`NestMembers`.

Đây là lý do không được kết luận “chỉ sửa vài dòng nguồn” đồng nghĩa “không đổi cấu trúc class file”.

## 4. Điều gì xảy ra với trạng thái và lời gọi đang chạy?

Định nghĩa mới không phải khởi động lại lớp hoặc tạo lại mọi đối tượng.

### Đối tượng đã có

Đối tượng cũ vẫn giữ giá trị trường hiện tại. Constructor của nó không tự được chạy lại. Khi gọi một phương thức mới sau khi định nghĩa lại thành công, đối tượng có thể dùng phần triển khai mới của phương thức đó.

Có thể hiểu giới hạn cấu trúc qua vấn đề này: nếu thêm một trường mới, công cụ sẽ phải giải quyết cách biểu diễn và giá trị của trường đó cho toàn bộ đối tượng cũ. API chuẩn không cung cấp một cơ chế tổng quát để tự di chuyển trạng thái theo mọi thay đổi như vậy.

### Trường tĩnh

Giá trị trường tĩnh được giữ nguyên. Định nghĩa lại không tự chạy lại bộ khởi tạo tĩnh.

Ví dụ, đổi khai báo nguồn từ `static int total = 10` thành `static int total = 900` không làm trường đang có giá trị 11 tự trở thành 900. Phần gán ban đầu được biên dịch thành mã khởi tạo; lớp đã khởi tạo không được tự khởi tạo lại chỉ vì có bản mã mới.

### Lời gọi phương thức đang thực thi

Khung thực thi đang chạy tiếp tục dùng bytecode cũ của phương thức. Các lời gọi mới dùng phiên bản mới sau khi định nghĩa lại.

Không nên hình dung JVM thay ngay những lệnh tiếp theo dưới chân một phương thức đang chạy. Cũng không nên suy luận một giao dịch nghiệp vụ đang dở sẽ được chuyển toàn bộ sang quy tắc mới một cách nguyên tử.

### Đối tượng được tạo sau đó

Một đối tượng mới được tạo bằng constructor thuộc định nghĩa mới sẽ chạy thân constructor mới. Vì phép gán giá trị ban đầu cho trường instance nằm trong constructor, đối tượng mới có thể nhận giá trị khởi tạo mới trong khi đối tượng cũ vẫn giữ trạng thái cũ.

Thí nghiệm dưới đây kiểm chứng trực tiếp sự khác biệt giữa trường instance và trường tĩnh.

## 5. Thí nghiệm: sửa thân phương thức thành công, thêm trường bị từ chối

Ta sẽ tạo ba bản của cùng lớp `demo.Counter`:

1. Bản v1 để ứng dụng nạp ban đầu.
2. Bản v2 giữ nguyên cấu trúc, sửa thông điệp và giá trị khởi tạo.
3. Bản không hợp lệ giữ phần lớn v2 nhưng thêm một trường.

Mỗi bản được biên dịch vào thư mục riêng. Không đặt cả ba bản trên classpath và không cố biên dịch chúng chung vào một thư mục.

### 5.1. Agent: src-agent/demo/RedefineAgent.java

```java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static void replace(Class<?> type, Path classFile) throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Redefinition is not supported");
        }
        if (!inst.isModifiableClass(type)) {
            throw new IllegalStateException("Class is not modifiable");
        }
        byte[] bytes = Files.readAllBytes(classFile);
        inst.redefineClasses(new ClassDefinition(type, bytes));
    }
}
```

Agent được khởi động bằng `-javaagent`; JVM truyền đối tượng `Instrumentation` vào `premain`. Phương thức `replace` dùng trong bài chỉ đọc class file rồi gửi yêu cầu định nghĩa lại.

`ClassDefinition` giữ tham chiếu tới mảng byte được truyền vào, không tự sao chép mảng. Ví dụ tạo một mảng riêng từ tệp và không sửa nó trong lúc yêu cầu đang được xử lý.

### 5.2. Bản ban đầu: src-v1/demo/Counter.java

```java
package demo;

public final class Counter {
    private static int total = 10;
    private int count = 1;

    public void increment() {
        count++;
        total++;
    }

    public String describe() {
        return "v1 count=" + count + " total=" + total;
    }
}
```

Sau một lần `increment()`, đối tượng có `count=2`, còn trường tĩnh `total=11`.

### 5.3. Bản giữ nguyên cấu trúc: src-v2/demo/Counter.java

```java
package demo;

public final class Counter {
    private static int total = 900;
    private int count = 70;

    public void increment() {
        count++;
        total++;
    }

    public String describe() {
        return "v2 count=" + count + " total=" + total;
    }
}
```

Bản này vẫn có cùng trường, cùng constructor không tham số, cùng `increment()`, cùng `describe()` và cùng modifier. Sự khác biệt nằm trong mã khởi tạo và thân phương thức.

Cả v1 lẫn v2 đều đã có bộ khởi tạo tĩnh vì khai báo trường tĩnh có giá trị ban đầu. Ta không thêm một `<clinit>` mới vào một lớp vốn chưa có nó.

### 5.4. Bản thêm trường: src-bad/demo/Counter.java

```java
package demo;

public final class Counter {
    private static int total = 900;
    private int count = 70;
    private long extra;

    public void increment() {
        count++;
        total++;
    }

    public String describe() {
        return "v2 count=" + count + " total=" + total;
    }
}
```

Trường `extra` không cần được sử dụng. Chỉ việc nó xuất hiện trong cấu trúc lớp đã đủ làm bản thay thế vi phạm giới hạn đang khảo sát.

### 5.5. Ứng dụng: src-app/demo/App.java

```java
package demo;

import java.nio.file.Path;

public final class App {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Expected v2 and invalid class files");
        }
        Counter counter = new Counter();
        counter.increment();
        Class<?> originalClass = counter.getClass();
        System.out.println("before: " + counter.describe());

        RedefineAgent.replace(Counter.class, Path.of(args[0]));
        System.out.println("same Class: "
                + (originalClass == counter.getClass()));
        System.out.println("existing: " + counter.describe());
        System.out.println("new: " + new Counter().describe());

        try {
            RedefineAgent.replace(Counter.class, Path.of(args[1]));
            System.out.println("unexpected: extra field accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("rejected: UnsupportedOperationException");
        }
        System.out.println("after rejected: " + counter.describe());
    }
}
```

Điểm nối trực tiếp giữa ứng dụng và agent chỉ phục vụ thí nghiệm để điều khiển thời điểm gọi API. Không có yêu cầu chung rằng ứng dụng dùng agent phải tham chiếu lớp agent trong mã nghiệp vụ.

### 5.6. Manifest

Tệp `MANIFEST.MF`:

```text
Manifest-Version: 1.0
Premain-Class: demo.RedefineAgent
Can-Redefine-Classes: true

```

Lưu dạng văn bản, có ký tự xuống dòng kết thúc và một dòng trống cuối tệp.

Cấu trúc đầu vào:

```text
src-agent/demo/RedefineAgent.java
src-v1/demo/Counter.java
src-v2/demo/Counter.java
src-bad/demo/Counter.java
src-app/demo/App.java
MANIFEST.MF
```

### 5.7. Biên dịch và đóng gói

Dùng JDK 17+ có `javac`, `jar`, `java` trên `PATH`. Từ thư mục thực hành chứa các thư mục nguồn và manifest, chạy trong PowerShell:

```powershell
javac --release 17 -d agent-classes src-agent/demo/RedefineAgent.java
javac --release 17 -d app-classes src-v1/demo/Counter.java
javac --release 17 -d v2-classes src-v2/demo/Counter.java
javac --release 17 -d bad-classes src-bad/demo/Counter.java
javac --release 17 -cp "agent-classes;app-classes" -d app-classes src-app/demo/App.java

jar --create --file redefine-agent.jar --manifest MANIFEST.MF -C agent-classes .
```

Chỉ tiếp tục nếu từng lệnh thành công. Dấu `;` trong classpath là dấu phân cách trên Windows. Nếu tự chuyển các lệnh sang Linux/macOS, classpath dùng `:`.

JAR agent chỉ chứa lớp agent. Lớp Counter ban đầu nằm trong `app-classes`; hai bản thay thế là các tệp được agent đọc, không phải các lớp được đặt lên classpath để JVM tự chọn.

### 5.8. Chạy

```powershell
java "-javaagent:redefine-agent.jar" -cp app-classes demo.App v2-classes/demo/Counter.class bad-classes/demo/Counter.class
```

Stdout đã kiểm tra bằng JDK 24.0.2, với dữ liệu lớp biên dịch bằng `--release 17`:

```text
before: v1 count=2 total=11
same Class: true
existing: v2 count=2 total=11
new: v2 count=70 total=11
rejected: UnsupportedOperationException
after rejected: v2 count=2 total=11
```

Thí nghiệm cần một JVM hỗ trợ định nghĩa lại và chấp nhận lớp đích là sửa được. Agent chủ động báo lỗi nếu không có khả năng đó, thay vì giả định mọi môi trường đều hỗ trợ.

## 6. Giải thích từng kết quả

### before: v1 count=2 total=11

Ứng dụng đã tạo đối tượng và gọi `increment()` trước khi thay mã. Do đó, ta đang kiểm tra lớp đã nạp và đối tượng thật đã có trạng thái, không phải biến đổi lần đầu trước khi định nghĩa lớp.

### same Class: true

Định nghĩa mới được cài cho chính lớp cũ. Không có một lớp khác cùng tên được tạo bởi bộ nạp mới rồi gán vào biến.

Thay tệp `.class` trên đĩa không tự tạo ra hiệu ứng này; chính lời gọi `redefineClasses` đã yêu cầu JVM cài mã mới.

### existing: v2 count=2 total=11

Đối tượng cũ vẫn giữ `count=2`, không bị gán lại thành 70. Trường tĩnh vẫn có giá trị 11, không bị gán lại thành 900.

Tuy nhiên, `describe()` là một lời gọi mới sau khi định nghĩa lại, nên chuỗi bắt đầu bằng `v2`.

### new: v2 count=70 total=11

Đối tượng mới chạy constructor mới và nhận giá trị instance ban đầu 70. Bộ khởi tạo tĩnh không được chạy lại, nên `total` vẫn là 11.

Đây là sự khác biệt quan trọng: “không chạy lại khởi tạo” nói về tác động của chính thao tác định nghĩa lại đối với lớp/đối tượng đã tồn tại. Nó không ngăn một lời gọi constructor mới thực thi mã khởi tạo instance thuộc phiên bản mới.

### rejected: UnsupportedOperationException

Bản thêm trường bị JVM của thí nghiệm từ chối. Mã chỉ in tên kiểu ngoại lệ, không phụ thuộc vào thông điệp lỗi cụ thể của một bản JDK.

Không nhầm với `UnmodifiableClassException`: lớp đích có thể là lớp sửa được, nhưng **loại thay đổi được yêu cầu** lại không được hỗ trợ. Ngoài thay đổi cấu trúc, thiếu khả năng định nghĩa lại cũng có thể dẫn tới `UnsupportedOperationException`; cần đọc ngữ cảnh và kiểm tra điều kiện thay vì kết luận từ riêng tên ngoại lệ.

### after rejected: v2 count=2 total=11

Yêu cầu thêm trường không thay thế thành công định nghĩa lớp. Lớp vẫn sử dụng bản v2 đã cài trước đó.

Điều này không tự hoàn tác lần định nghĩa lại thành công trước đó về v1. Một lần yêu cầu bị từ chối chỉ không cài bản mới của chính yêu cầu đó.

## 7. Kiểm tra cấu trúc trước khi gửi yêu cầu

Chỉ so sánh mã nguồn hoặc số dòng thay đổi là chưa đủ. Có thể xem trường, phương thức và mô tả kiểu trong dữ liệu đã biên dịch:

```powershell
javap -p -s app-classes/demo/Counter.class
javap -p -s v2-classes/demo/Counter.class
javap -p -s bad-classes/demo/Counter.class
```

Đây là các lệnh kiểm tra, không sửa tệp.

Kết quả của bản không hợp lệ có thêm phần:

```text
private long extra;
  descriptor: J
```

`javap -p` hiển thị cả thành viên private; `-s` hiển thị mô tả kiểu của JVM. Nếu chỉ nhìn các phương thức public, ta có thể bỏ sót chính thay đổi làm JVM từ chối.

Bản v1 và v2 trong ví dụ có cùng các trường và mô tả phương thức. Có thể dùng thêm `javap -v` để xem thuộc tính chi tiết; không coi việc danh sách thành viên giống nhau là chứng nhận đầy đủ cho mọi thay đổi hợp lệ.

### Vì sao lambda hoặc mã được sinh thêm có thể gây bất ngờ?

Một lambda mới, lớp ẩn danh mới hoặc công cụ sinh mã có thể làm bộ biên dịch tạo thêm phương thức/thành viên hoặc thay thuộc tính liên quan. Không phải mọi sửa đổi lambda đều bị từ chối; phải kiểm tra class file thực tế và đối chiếu với định nghĩa đã cài.

Tương tự, đổi kiểu trả về theo quy tắc kiểu con trong mã Java có thể kéo theo thay đổi mô tả phương thức hoặc phương thức cầu nối. Việc mã nguồn vẫn biên dịch được không chứng minh nó phù hợp cho định nghĩa lại.

## 8. Phân biệt với các cơ chế gần giống

| Cơ chế | Lớp đã có định nghĩa trong JVM chưa? | Điều cần nhớ |
| --- | --- | --- |
| Biến đổi lúc nạp lần đầu | Chưa được định nghĩa ở thời điểm dữ liệu đi qua transformer | Có thể chọn cấu trúc ban đầu trong phạm vi JVM chấp nhận |
| `redefineClasses` | Đã có | Cung cấp dữ liệu thay thế, chịu giới hạn của lớp đã nạp |
| `retransformClasses` | Đã có | Yêu cầu chạy lại quy trình biến đổi, cũng chịu giới hạn cấu trúc tương ứng |
| Nạp bằng một bộ nạp lớp mới | Tạo danh tính lớp khác | Không tự biến các đối tượng cũ thành đối tượng của lớp mới |
| Khởi động lại ứng dụng | Tạo lại quá trình nạp và khởi tạo | Có thể triển khai thay đổi cấu trúc cùng cách khởi tạo/di chuyển trạng thái phù hợp |

Không dùng `retransformClasses` để lách giới hạn thêm trường hoặc đổi lớp cha. Đường lấy dữ liệu đầu vào khác nhau không làm giới hạn cấu trúc biến mất.

Nạp lớp mới qua bộ nạp khác là một thiết kế riêng. Đối tượng của hai lớp cùng tên nhưng khác bộ nạp không tự tương thích kiểu với nhau. Cần thiết kế ranh giới giao tiếp và vòng đời đối tượng, không chỉ thay tên một thư mục classpath.

Một agent muốn bổ sung dữ liệu phụ cho đối tượng đã tồn tại có thể cần cấu trúc hỗ trợ bên ngoài lớp đích thay vì thêm trường trực tiếp. Khi đó phải xử lý rõ vòng đời, bộ nhớ, đồng thời và cách xác định đối tượng; đó không phải “thêm trường miễn phí” bằng API.

## 9. Tính nguyên tử và các giới hạn cần hiểu đúng

`redefineClasses` nhận nhiều `ClassDefinition` để có thể cài một nhóm thay đổi liên quan. Nếu lời gọi thất bại theo hợp đồng, không có lớp nào trong nhóm được cài định nghĩa mới từ lần yêu cầu đó.

Nhưng không nên mở rộng bảo đảm này thành một giao dịch nghiệp vụ tổng quát:

- Một lần định nghĩa lại đã thành công trước đó vẫn tồn tại.
- Tác dụng phụ mà mã agent/transformer đã chủ động thực hiện không tự được hoàn tác như một giao dịch cơ sở dữ liệu.
- Các đối tượng, cache, tài nguyên ngoài JVM hoặc cấu hình ứng dụng không được tự di chuyển sang mô hình dữ liệu mới.
- Các lời gọi cũ đang chạy vẫn có thể hoàn tất bằng bytecode cũ.

Vì vậy, ngay cả khi chỉ đổi thân phương thức, vẫn phải đánh giá sự tương thích giữa mã mới và trạng thái đã tồn tại. Ví dụ, mã mới giả định một trường không bao giờ bằng `null` có thể sai đối với đối tượng được tạo bởi constructor cũ.

Trường `static final` và hằng được biên dịch nội tuyến còn có đặc điểm riêng về nơi giá trị được sử dụng. Không dựa vào định nghĩa lại một lớp để mặc nhiên cập nhật mọi bản sao hằng đã được mã khác biên dịch vào.

## 10. Bài tập tự kiểm chứng

1. Bỏ trường `extra` khỏi bản không hợp lệ và đổi tiền tố `v2` thành `v3`. Biên dịch lại vào `bad-classes`. Lần yêu cầu thứ hai không còn là thử nghiệm thêm trường; hãy quan sát xem bản thay thế mới có được cài không. Không giữ kỳ vọng cũ rằng dòng “rejected” luôn phải xuất hiện.
2. Giữ nguyên trường nhưng đổi `count` từ `int` thành `long`. Vì sao đây là thay đổi cấu trúc dù tên trường không đổi?
3. Thêm một constructor có tham số vào bản thay thế. Dùng `javap -p -s` để xác định phương thức mới và mô tả tham số của nó.
4. Trong v2, chỉ đổi phép tính của `increment()`, giữ nguyên chữ ký. Sau khi định nghĩa lại, gọi nó trên đối tượng cũ và dự đoán cách mã mới tác động vào trạng thái cũ.
5. Giải thích vì sao `isModifiableClass(Counter.class)==true` không chứng minh phiên bản thêm trường sẽ được chấp nhận.
6. Nêu sự khác biệt giữa đối tượng cũ có `count=2` và đối tượng mới có `count=70` trong kết quả. Không dùng câu trả lời chung “mọi thứ đều được nạp lại”.

Điều cần nắm là **định nghĩa lại thay phần mã của chính lớp đã nạp trong những ràng buộc cụ thể; nó không tự thay toàn bộ cấu trúc, tái tạo đối tượng hay khởi tạo lại trạng thái**. Muốn đổi cấu trúc, cần chọn một phương án triển khai và quản lý trạng thái phù hợp với phạm vi thay đổi.

## Tài liệu đối chiếu

- [Instrumentation trên JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, điều kiện hỗ trợ, trạng thái và ngoại lệ.
- [JVM TI — RedefineClasses](https://docs.oracle.com/en/java/javase/26/docs/specs/jvmti.html#RedefineClasses): giới hạn đổi trường/phương thức/modifier/hệ kế thừa và các thuộc tính bị cấm.
- [ClassDefinition](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cách liên kết lớp đích với dữ liệu class file.
- [UnmodifiableClassException](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): trường hợp lớp không thuộc loại sửa được.
