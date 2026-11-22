# `AbstractMethodError` và `IncompatibleClassChangeError` trong Java: lỗi tương thích nhị phân và class loader

## 1. Hiểu đúng hai loại lỗi

`AbstractMethodError` và `IncompatibleClassChangeError` là các lỗi thuộc họ `LinkageError`. Chúng thường xuất hiện khi JVM đang chạy một tập hợp file `.class` **không còn tương thích với nhau về mặt binary**, ví dụ chương trình được biên dịch với API phiên bản A nhưng runtime lại nạp phiên bản B của API đó.

Cả hai có ý nghĩa rất thực tế ở ứng dụng dùng thư viện bên thứ ba, plugin, application server, class loader tự tạo, redeploy hoặc cơ chế hot reload: **biên dịch thành công không bảo đảm tất cả class được liên kết và gọi method thành công sau khi triển khai**.

Quan hệ kế thừa quan trọng:

```text
java.lang.Throwable
  └─ java.lang.Error
       └─ java.lang.LinkageError
            └─ java.lang.IncompatibleClassChangeError
                 ├─ java.lang.AbstractMethodError
                 ├─ java.lang.NoSuchMethodError
                 ├─ java.lang.NoSuchFieldError
                 ├─ java.lang.IllegalAccessError
                 └─ java.lang.InstantiationError
```

Lưu ý: các lớp cùng cấp trong cây không phải một lỗi duy nhất; mỗi loại cho manh mối chẩn đoán khác nhau. Chẳng hạn `NoSuchMethodError` cho biết một method được tham chiếu không thể được phân giải như mong đợi; `AbstractMethodError` liên quan **việc gọi** method mà runtime không tìm được implementation phù hợp; còn một `IncompatibleClassChangeError` trực tiếp có thể xuất hiện khi runtime nhận thấy method thực tế là instance trong khi bytecode đòi static.

| Đặc điểm | `AbstractMethodError` | `IncompatibleClassChangeError` trực tiếp |
|---|---|---|
| Bản chất | Cố gọi một method mà bước dispatch không tìm thấy implementation concrete hợp lệ | Thấy sự thay đổi cấu trúc lớp/method/field không tương thích với bytecode được biên dịch trước đó |
| Ví dụ đặc trưng | Xóa implementation `default` trên interface và thay bằng method abstract, trong khi implementation cũ chưa được biên dịch lại | Đổi method `static` thành instance nhưng caller cũ vẫn dùng `invokestatic` |
| Khi phát hiện | Có thể đến lúc method được gọi/resolved, không nhất thiết lúc ứng dụng khởi động | Có thể đến khi resolve/link hoặc khi instruction tương ứng chạy |
| Cách chữa căn bản | Tái biên dịch và phân phối **đồng bộ** contract, implementation, caller | Khôi phục binary contract hoặc cập nhật đồng bộ caller và thư viện runtime |

**Quan hệ cần nhớ:** `AbstractMethodError extends IncompatibleClassChangeError`. Vì vậy một đoạn `catch (IncompatibleClassChangeError e)` cũng bắt được `AbstractMethodError`, nhưng khi điều tra phải giữ nguyên **kiểu lỗi cụ thể**, full stack trace và thông tin class loader. Các lỗi này là `Error`, không phải checked exception; việc catch để “bỏ qua” thường khiến ứng dụng tiếp tục chạy trong trạng thái bất nhất.

## 2. Binary compatibility: vì sao compile pass mà runtime fail?

Một file `.class` không chứa toàn bộ mã nguồn của các lớp phụ thuộc. Nó chứa các **symbolic reference** (tên class/interface, tên method/field, descriptor kiểu), cùng bytecode gọi như `invokestatic`, `invokevirtual`, `invokeinterface` hoặc `invokespecial`. Tại runtime JVM phải resolve và thực thi những tham chiếu đó theo định nghĩa class **thực sự được nạp**.

Ví dụ:

```text
Thời điểm build:
  Client.class  ──biên dịch dựa vào──> Library API v1

Thời điểm chạy:
  Client.class  ──JVM resolve tới───> Library API v2
                                       ^
                                       thay đổi method không tương thích
```

Nếu `Client.class` giữ opcode gọi static nhưng `Library` của v2 chỉ còn instance method cùng tên/descriptor, bytecode cũ không được tự sửa để chuyển thành cuộc gọi instance. Tương tự, nếu invocation kỳ vọng method đã có implementation mà runtime chỉ còn abstract method, JVM không thể tự phát minh phần thân còn thiếu.

**Source compatibility khác binary compatibility.** Chạy lại `javac` trên toàn bộ source đã cập nhật có thể phát hiện lỗi tại compile time; nhưng nếu chỉ thay JAR mà giữ class cũ, lỗi có thể lộ ra khi chạy production. Ngược lại, có thay đổi không tương thích ở source nhưng vẫn binary-compatible với caller đã biên dịch trước đó. Mức độ và loại lỗi tùy thay đổi cụ thể.

**Class loader là yếu tố quyết định:** một runtime class được xác định bởi **binary name + defining class loader**, không chỉ tên package/class. Parent delegation, thứ tự classpath, module path, fat JAR, ứng dụng plugin và các loader cô lập đều quyết định phiên bản class thực sự được chọn.

## 3. Thí nghiệm A — tái hiện `AbstractMethodError` với Java 17+

Trong v1, `Contract.message()` là `default` method, vì vậy `Provider` không cần tự triển khai. Caller cũ được biên dịch và gọi hợp lệ. Khi runtime thay `Contract` bằng v2 có method abstract, `Provider.class` từ v1 vẫn không có phần triển khai; lời gọi bị lỗi.

### Cấu trúc thí nghiệm

```text
ame/
  v1/
    src/demo/
      Contract.java
      Provider.java
      Runner.java
    classes/                 (do javac tạo)
  v2/
    src/demo/
      Contract.java
    classes/                 (do javac tạo)
```

File **`ame/v1/src/demo/Contract.java`**:

```java
package demo;

public interface Contract {
    default String message() {
        return "default-v1";
    }
}
```

File **`ame/v1/src/demo/Provider.java`**:

```java
package demo;

public class Provider implements Contract {
    // Hợp lệ ở v1 nhờ kế thừa default method.
}
```

File **`ame/v1/src/demo/Runner.java`**:

```java
package demo;

public class Runner {
    public static void main(String[] args) {
        Contract provider = new Provider();
        System.out.println(provider.message());
    }
}
```

File **`ame/v2/src/demo/Contract.java`**:

```java
package demo;

public interface Contract {
    String message(); // v2: không còn default implementation
}
```

Từ thư mục chứa `ame/`, thực hiện trên Unix/Linux/macOS (Bash):

```bash
mkdir -p ame/v1/classes ame/v2/classes

javac -d ame/v1/classes \
  ame/v1/src/demo/Contract.java \
  ame/v1/src/demo/Provider.java \
  ame/v1/src/demo/Runner.java

javac -d ame/v2/classes ame/v2/src/demo/Contract.java

# Baseline: toàn bộ lớp của v1.
java -cp ame/v1/classes demo.Runner

# Trộn contract v2 với Provider và Runner của v1.
java -cp ame/v2/classes:ame/v1/classes demo.Runner
```

Baseline in đúng:

```text
default-v1
```

Lệnh chạy hỗn hợp **kết thúc với lỗi**; phần đầu stack trace trên HotSpot JDK 17+ có dạng:

```text
Exception in thread "main" java.lang.AbstractMethodError: ...
    at demo.Runner.main(Runner.java:...)
```

Phần mô tả chi tiết của JVM, số dòng và cách in stack trace có thể thay đổi tùy bản JDK. Phần không đổi trong tình huống này là **loại lỗi** `java.lang.AbstractMethodError`. Ví dụ đã được kiểm tra trên JDK 21: receiver `demo.Provider` không định nghĩa hay thừa hưởng implementation cho `demo.Contract.message()` bản abstract.

Tại sao bytecode cũ chạy được đến dòng gọi?

1. `Runner.class` cũ có lời gọi tới `demo.Contract.message:()Ljava/lang/String;`.
2. Runtime nạp `Contract` từ `ame/v2/classes` vì đường dẫn này đứng **trước** `ame/v1/classes`.
3. `Provider.class` cũ không tự cài `message()`; lúc compile nó dựa vào `default` của interface v1.
4. Với interface v2, không còn implementation concrete phù hợp để dispatch. JVM ném `AbstractMethodError` khi thực hiện cuộc gọi.

Nếu compile lại `Provider.java` v1 theo `Contract` v2, `javac` sẽ bắt việc thiếu triển khai, trừ khi code được sửa hoặc khai báo class abstract. Điều đó giải thích vì sao lỗi có thể “chỉ xảy ra ở runtime” với binary trộn phiên bản.

**Không kết luận tất cả thay đổi method sang abstract đều trông giống nhau.** Tình huống trên có điểm quan trọng là caller/implementation được biên dịch độc lập với contract mới. Thay đổi từ concrete sang abstract trong superclass cũng có thể tạo `AbstractMethodError` theo JLS `13.4.16`.

## 4. Thí nghiệm B — tái hiện `IncompatibleClassChangeError` khi static đổi thành instance

Ở v1, bytecode của caller dùng `invokestatic`. Ở v2, method cùng tên/descriptor đã là instance method, nên instruction cũ không còn hợp lệ với method mới.

### Cấu trúc

```text
icce/
  v1/
    src/demo/
      Library.java
      Client.java
    classes/
  v2/
    src/demo/
      Library.java
    classes/
```

File **`icce/v1/src/demo/Library.java`**:

```java
package demo;

public class Library {
    public static String mode() {
        return "static-v1";
    }
}
```

File **`icce/v1/src/demo/Client.java`**:

```java
package demo;

public class Client {
    public static void main(String[] args) {
        System.out.println(Library.mode());
    }
}
```

File **`icce/v2/src/demo/Library.java`**:

```java
package demo;

public class Library {
    public String mode() {
        return "instance-v2";
    }
}
```

Biên dịch và chạy (Bash):

```bash
mkdir -p icce/v1/classes icce/v2/classes

javac -d icce/v1/classes \
  icce/v1/src/demo/Library.java \
  icce/v1/src/demo/Client.java

javac -d icce/v2/classes icce/v2/src/demo/Library.java

java -cp icce/v1/classes demo.Client
java -cp icce/v2/classes:icce/v1/classes demo.Client
```

Baseline in đúng:

```text
static-v1
```

Lệnh thứ hai lỗi (HotSpot JDK 17+, phần message có thể thay đổi):

```text
Exception in thread "main" java.lang.IncompatibleClassChangeError: Expected static method ...
    at demo.Client.main(Client.java:...)
```

Thử phân tích bytecode được lưu trong caller v1:

```bash
javap -classpath icce/v1/classes -c demo.Client
```

Trong phương thức `main` sẽ có instruction `invokestatic` gọi `demo/Library.mode:()Ljava/lang/String;`. Đây là bằng chứng caller cũ **đã mã hóa kiểu gọi static**; chỉ sửa mã nguồn của `Library` rồi thay JAR ở runtime sẽ không biến bytecode caller thành lời gọi instance.

Với Windows PowerShell/cmd, khi classpath có hai thư mục, đổi dấu `:` thành dấu `;` và đặt cả classpath trong dấu nháy nếu cần, ví dụ:

```powershell
java -cp "icce/v2/classes;icce/v1/classes" demo.Client
```

Chỉ dùng đường dẫn tách biệt để minh họa; trong dự án thật, cùng tên class có thể nằm ở hai JAR, các thư mục generated class hoặc các class loader khác nhau.

## 5. Điều gì diễn ra bên trong JVM và class loader?

Các bước khái quát:

1. **Loading:** class loader cung cấp bytes định nghĩa lớp theo tên và cơ chế delegation. Với nhiều URL/JAR, thứ tự tìm kiếm ở một loader có thể ảnh hưởng phiên bản được nạp.
2. **Linking:** verification và resolution bảo đảm tham chiếu symbolic của bytecode có thể kết nối với định nghĩa runtime. Resolution có thể được thực hiện muộn, nên lỗi đôi khi chỉ xuất hiện khi chạy tới nhánh code nhất định.
3. **Method invocation/dispatch:** `invokestatic`, `invokevirtual`, `invokeinterface`, `invokespecial` có yêu cầu khác nhau. Nếu loại method hoặc kết quả dispatch không hợp lệ, JVM báo lỗi liên kết thích hợp.
4. **Không tái nạp âm thầm class cùng tên:** một loader thông thường không “thay bytes của class đã define” chỉ vì JAR trên disk đã đổi. Plugin frameworks/restart loaders có thể tạo **loader mới**, mang theo phiên bản class mới, trong khi loader cũ vẫn giữ định nghĩa cũ.

Trong app server hoặc plugin container, riêng câu hỏi “trong disk có đúng JAR chưa?” là chưa đủ; cần biết **class nào do loader nào định nghĩa**, parent loader có chiếm quyền nạp trước hay không và quá trình xây dựng artifact đã gói những dependency nào.

Một ví dụ khó nhận ra:

```text
Bootstrap / platform loader
   └── Application loader → API v1
           └── Plugin loader → implementation v2
```

Nếu plugin loader delegate API lên parent, plugin thực tế có thể dùng **API v1** dù trong thư mục plugin có bản v2. Trong thiết kế ngược lại, caller của parent có thể resolve implementation của lớp với contract khác mong đợi. Lỗi thực tế có thể là `AbstractMethodError`, `IncompatibleClassChangeError`, `ClassCastException`, `NoClassDefFoundError` hoặc một `LinkageError` khác, tùy ràng buộc type và opcode; **không quy mọi lỗi class loader về hai exception trong bài**.

Đặc biệt: hai loader độc lập cùng định nghĩa `demo.Contract` tạo ra **hai runtime type khác nhau**. Việc cast instance qua ranh giới loader có thể ném `ClassCastException`, không nhất thiết là `IncompatibleClassChangeError`. Những trường hợp loader constraint violation có thể được báo `LinkageError`. Cần đọc **đúng exception class và stack trace**.

## 6. Các kiểu thay đổi binary thường gây lỗi liên quan

| Thay đổi giữa build và runtime | Triệu chứng có thể gặp | Gợi ý |
|---|---|---|
| Concrete/default implementation không còn, method trở thành abstract | `AbstractMethodError` khi gọi implementation cũ | So interface/superclass và bản implementation ở runtime |
| Method `static` ↔ instance | `IncompatibleClassChangeError` | So opcode invoke và modifier method thực được nạp |
| Field `static` ↔ instance | `IncompatibleClassChangeError` khi truy cập field bằng opcode cũ | So `getstatic/putstatic` với `getfield/putfield` |
| Method bị xóa hoặc thay tên/descriptor/return type khiến symbolic reference cũ không resolve được | `NoSuchMethodError` (một subclass của `IncompatibleClassChangeError`) | So chữ ký JVM descriptor, không chỉ tên method |
| Field bị xóa/đổi descriptor | `NoSuchFieldError` | Kiểm tra signature field thực ở class runtime |
| Truy cập member bị thay đổi sang không còn hợp lệ | `IllegalAccessError` | Kiểm tra Java access, module/package và runtime class |
| Đổi interface thành class hoặc ngược lại | Có thể `IncompatibleClassChangeError` | Kiểm tra runtime loại reference và bytecode liên quan |
| Hai loader cùng nạp class cùng tên nhưng khác identity | Có thể `ClassCastException` hoặc lỗi ràng buộc loader khác | In defining loader, trace class load, kiểm tra parent delegation |

Lưu ý: bảng mô tả **những triệu chứng điển hình**, không cam kết mọi phiên bản JVM hay mọi tập hợp binary sẽ phát sinh đúng một lỗi duy nhất. JVM có thể phát hiện một vi phạm khác sớm hơn, phụ thuộc instruction đầu tiên thực thi và cách resolve tham chiếu.

## 7. Quy trình điều tra lỗi trong ứng dụng thực tế

### Bước 1 — ghi nguyên nhân quan sát được, không đoán từ một dòng stack trace

Lưu đầy đủ:
- **Exception class đầy đủ**, message, dòng `Caused by` (nếu có) và stack trace của thread liên quan.
- Tên method, class/interface, descriptor nếu có, bản JDK và vị trí caller.
- Phiên bản API mà **caller được build cùng** và phiên bản API mà JVM thực tế đang nạp.
- Thời điểm triển khai: lỗi chỉ xuất hiện sau cập nhật JAR, hot reload, restart, redeploy hoặc thay classpath?

Stack trace thường chỉ tới **lệnh gọi gây lỗi**, không nhất thiết chỉ tới file JAR **chứa định nghĩa runtime không tương thích**.

### Bước 2 — xác nhận đường nạp class bằng runtime evidence

Nếu chủ động chỉnh được chương trình, đặt chỗ kiểm tra tại phần code chắc chắn còn chạy được:

```java
import java.net.URL;

public final class ClassOrigin {
    public static void describe(Class<?> type) {
        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());
        var domain = type.getProtectionDomain();
        var source = domain == null ? null : domain.getCodeSource();
        URL location = source == null ? null : source.getLocation();
        System.out.println("Code source: " + location);
    }
}
```

Đây là **utility minh họa** để gọi `ClassOrigin.describe(SomeClass.class)` từ một chương trình khác, không có `main` độc lập. `getClassLoader()` có thể trả `null` đối với lớp do bootstrap loader nạp. `CodeSource` cũng có thể `null`; framework/shading/nested JAR có thể khiến location không đơn giản là một file trên disk. Vì vậy, dùng log JVM và build metadata để đối chiếu khi output không đủ rõ.

Có thể bật log khi khởi động ứng dụng HotSpot JDK 17:

```bash
java -Xlog:class+load=info -cp app-classes:lib/* com.example.Main
```

Đường dẫn/classpath là **mẫu minh họa**; thay bằng đường chạy thực tế. Đọc các dòng liên quan đến class gặp lỗi để biết JVM đã nạp định nghĩa từ đâu. Với JDK 17, lệnh `java -verbose:class ...` cũng hữu ích. Nếu dùng module path hoặc class loader tùy biến, ghi thêm loader identity khi có thể; nhiều JAR cùng version string không bảo đảm là cùng class bytes.

### Bước 3 — kiểm tra binary signature và instruction

Chạy `javap` trên **artifact đang triển khai** và trên **artifact mà caller được biên dịch với**:

```bash
javap -classpath path/to/api-v1.jar -p -s com.example.Library
javap -classpath path/to/api-v2.jar -p -s com.example.Library
javap -classpath path/to/app-classes -c -p com.example.Client
```

Những gì cần đối chiếu:

- Class hay interface; superclass và các interface được implements.
- `abstract` / `default` / `static` / `final` và access modifiers.
- Tên method và **descriptor**, ví dụ `()Ljava/lang/String;` khác `()V`.
- Opcode của caller: `invokestatic`, `invokevirtual`, `invokeinterface`; opcode access field tương ứng.
- Method concrete mà implementation kế thừa thực sự có tồn tại trong contract runtime hay không.

Trong plugin/app server, việc dùng `javap` trên local JAR là **chẩn đoán bản dựng**, chưa thay cho việc chứng minh JVM đã chọn JAR đó. Dùng class-loading log và loader identity để nối bằng chứng.

### Bước 4 — xác minh cây phụ thuộc và nội dung gói triển khai

Đối chiếu Maven/Gradle dependency resolution với **runtime artifact**, vì dependency declaration chưa chắc là class bytes được đóng gói:

- Gradle: `./gradlew dependencies --configuration runtimeClasspath`, `./gradlew dependencyInsight --dependency ten-thu-vien --configuration runtimeClasspath` (cần chọn đúng module/configuration).
- Maven: `mvn dependency:tree` và cấu hình scope/shading/assembly tương ứng.
- Với Spring Boot executable JAR, kiểm tra thư viện trong `BOOT-INF/lib`; với app server, kiểm tra các thư mục thư viện chung và module deployment; với plugin, kiểm tra các JAR mà parent/child loader nhìn thấy.
- So version của API, SPI, provider, adapter, generated proxies và caller. Cảnh giác dependency transitively kéo bản cũ, cùng một API bị gói nhiều lần, hoặc deploy thay từng JAR trong khi JVM vẫn chạy bản cũ.

### Bước 5 — sửa nhất quán và kiểm tra hồi quy

Cách xử lý đúng là **khôi phục binary contract nhất quán** giữa các module: chọn phiên bản API và implementation tương thích; build lại caller/provider bị ảnh hưởng; bảo đảm runtime nhận đúng bộ class bytes; rồi tạo lại class loader hoặc restart process khi cần để loại bỏ class cũ đã load.

Không sửa bằng cách catch `AbstractMethodError` rồi gọi đại một method khác, đổi classpath “cho tới khi chạy”, hoặc thêm `System.gc()`. Garbage collection không sửa được bytecode tham chiếu sai, cũng không biến method abstract thành concrete. `Class.forName` chỉ nạp/khởi tạo class theo cách gọi và có thể giúp phát hiện một số vấn đề sớm; nó **không** tự giải quyết binary incompatibility.

Nếu phải duy trì nhiều phiên bản plugin, thiết kế API boundary ổn định, adapter rõ ràng, quy tắc version và parent delegation nhất quán. Xác minh cả test tích hợp **sử dụng đúng bộ JAR ở runtime**, không chỉ compile test với một tập dependency khác.

## 8. Ví dụ phân biệt lỗi và những kết luận sai

**Sai:** “`AbstractMethodError` là do quên override method abstract, chỉ cần sửa code để compiler bắt.”  
**Đúng:** Với source biên dịch sạch, compiler thường phát hiện thiếu implementation. Khi runtime kết hợp các `.class` biên dịch từ **những phiên bản contract khác nhau**, thiếu implementation có thể chỉ lộ ra ở dispatch.

**Sai:** “`IncompatibleClassChangeError` chắc chắn có hai JAR trùng tên trên classpath.”  
**Đúng:** Trùng JAR chỉ là một nguyên nhân khả dĩ. Một JAR duy nhất nhưng sai phiên bản so với caller đã biên dịch cũng gây lỗi; class loader còn có thể nạp từ directory, module hoặc nguồn bytecode khác.

**Sai:** “Cứ xóa cache Gradle/Maven là hết.”  
**Đúng:** Cache bị hỏng là giả thuyết chỉ nên kiểm tra khi có bằng chứng. Gốc rễ thường là binary version mismatch; kiểm chứng dependency graph, artifact nội dung và nguồn class JVM nạp.

**Sai:** “Lỗi xảy ra khi Spring tạo bean thì chắc là lỗi dependency injection.”  
**Đúng:** Framework có thể là nơi kích hoạt lần gọi method đầu tiên. Hãy đọc nguyên nhân sâu trong stack trace, phân biệt lỗi linkage với lỗi cấu hình bean.

**Sai:** “Hai `Class<?>` có cùng `getName()` thì là cùng kiểu.”  
**Đúng:** Kiểm tra `==` và defining loader; cùng tên nhưng khác loader có thể là hai runtime class khác nhau.

**Sai:** “Chỉ cần restart mà không cần biết nguyên nhân.”  
**Đúng:** Restart có thể khiến loader mới đọc đúng artifact và tạm giải quyết tình trạng redeploy dở dang, nhưng nếu deployment vẫn chứa tập bytecode không tương thích thì lỗi sẽ tái diễn.

## 9. Checklist chẩn đoán nhanh

1. Exception thực tế là `AbstractMethodError`, `IncompatibleClassChangeError` trực tiếp hay subclass khác (`NoSuchMethodError`, `IllegalAccessError`...)?
2. Caller được build với phiên bản API nào? Runtime thực tế nạp `Class<?>` nào, từ loader và code source nào?
3. Có thay đổi `default/concrete → abstract`, `static ↔ instance`, method descriptor, class/interface, superclass hoặc implementation không?
4. `javap -c` của caller chứa opcode gì? `javap -p -s` của class runtime cho biết method/field nào?
5. Có nhiều bản API/plugin, shared library, parent delegation, shaded JAR, app-server library hoặc hot-reload loader cũ không?
6. Đã build/deploy lại **toàn bộ các binary liên quan** và chạy integration test với cùng dependency set như production chưa?

## 10. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `Provider` trong thí nghiệm A biên dịch hợp lệ với v1 nhưng ném `AbstractMethodError` khi chạy với interface v2?  
**Đáp án:** v1 có `default` implementation; v2 chỉ có abstract declaration. `Provider.class` cũ không tự triển khai `message()` và không được biên dịch lại.

**Câu 2:** Trong thí nghiệm B, vì sao runtime không tự gọi `new Library().mode()` thay cho `Library.mode()`?  
**Đáp án:** `Client.class` chứa `invokestatic` theo contract v1; JVM không tự viết lại chương trình, khởi tạo đối tượng, rồi thay instruction cho phù hợp v2.

**Câu 3:** `AbstractMethodError` có thuộc họ `IncompatibleClassChangeError` không?  
**Đáp án:** Có. Nó là subclass trực tiếp của `IncompatibleClassChangeError`, và cả hai thuộc `LinkageError`.

**Câu 4:** Thấy hai class cùng tên `com.example.Api` từ hai loader, có thể khẳng định sẽ ném `AbstractMethodError` không?  
**Đáp án:** Không. Cần biết tham chiếu/loader constraints và instruction cụ thể; có thể là hai runtime type hợp lệ tách biệt, hoặc phát sinh `ClassCastException`/lỗi linkage khác.

**Câu 5:** Ba bằng chứng quan trọng nhất khi debug là gì?  
**Đáp án:** (i) full exception class/stack trace tại vị trí gọi; (ii) phiên bản và loader/code source của class runtime; (iii) signature/modifier + bytecode opcode và bộ artifact mà caller thực sự được build với.

## Tài liệu chuẩn

- [Java SE 17 — `AbstractMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractMethodError.html): định nghĩa lỗi, thuộc họ `IncompatibleClassChangeError`.
- [Java SE 17 — `IncompatibleClassChangeError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IncompatibleClassChangeError.html): lỗi do thay đổi class definition không tương thích.
- [JLS 17, Chương 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): đặc biệt `13.4.16` về concrete-to-abstract và `13.4.18` về static/instance method.
- [JVMS 17, Chương 6 — JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): `invokestatic`, `invokeinterface` và các instruction khác để giải thích bytecode caller.
