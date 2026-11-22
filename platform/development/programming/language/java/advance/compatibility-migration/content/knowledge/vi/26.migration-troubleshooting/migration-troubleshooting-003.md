# NoSuchMethodError, NoSuchFieldError và dependency không khớp

Trong quá trình **Java Advance Compatibility Migration**, một tình huống gây khó chịu là ứng dụng vẫn biên dịch thành công nhưng khi chạy trên JDK mới lại báo:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.codec.JsonWriter.write(java.lang.Object)'
```

Hoặc:

```text
java.lang.NoSuchFieldError: DEFAULT_TIMEOUT
```

Hai lỗi này thường là dấu hiệu **mã bytecode đang chạy không tìm thấy method hoặc field đúng với tham chiếu mà bytecode của caller đã được biên dịch để gọi**. Nguyên nhân phổ biến là một thư viện được dùng lúc biên dịch có API khác với bản thực sự được tải khi chạy: phiên bản trực tiếp và bắc cầu không đồng bộ, JAR cũ còn trong WAR, shaded artifact đóng gói sai, application server cung cấp bản khác, hoặc một lớp được tải bởi classloader không như dự kiến.

Điểm mấu chốt: **`NoSuchMethodError` và `NoSuchFieldError` là lỗi liên kết ở runtime, không phải tên gọi khác của compile error**. Không nên giải quyết bằng cách đổi JDK ngẫu nhiên, xóa cache rồi thử lại, hoặc ép một phiên bản dependency mà chưa xác định đúng class được tải, chữ ký nhị phân được caller yêu cầu và API mà runtime class thực sự cung cấp.

Bài học này trình bày cách đọc stack trace và JVM linkage, tái hiện lỗi bằng hai bản JAR, dùng `javap` để kiểm tra binary descriptors, tìm class trùng trong Maven/Gradle/WAR/fat JAR, phân biệt những họ lỗi liên quan, xử lý adapter/framework/JDK migration, xây quy trình chẩn đoán production và thiết lập CI gates để tránh lỗi tái diễn.

> **Phạm vi:** Ví dụ package, group/artifact và version trong bài được tạo để minh họa; không đại diện cho một dependency thực tế. Lệnh Maven/Gradle và JVM cần điều chỉnh theo bản build tool, JDK, hệ điều hành và cấu trúc project đang sử dụng.

## 1. Hai lỗi này thuộc nhóm nào?

### 1.1. LinkageError xuất hiện sau giai đoạn biên dịch

Java compiler biên dịch source dựa trên **API mà nó thấy trên compile classpath/module path**. File `.class` sinh ra lưu các tham chiếu biểu tượng (symbolic references) đến class, method và field, thay vì ghi sẵn địa chỉ bộ nhớ của mọi method.

Khi chạy, JVM tải class và giải quyết những tham chiếu đó theo các quy tắc của Java Virtual Machine Specification. Nếu class mục tiêu không cung cấp method/field như caller yêu cầu, quá trình linkage có thể ném một lỗi thuộc họ `LinkageError`.

Sơ đồ:

```text
              Compile time                         Runtime
          ------------------                  ------------------
          application source
                 |
                 v
         library-api-v1.jar
          method greet(String)
                 |
                 v
           javac -> App.class
                 |                          App.class
                 |                              |
                 +------------------------------+
                                                |
                                                v
                                        class loader chọn
                                        library-api-v2.jar
                                        chỉ có greet(Object)
                                                |
                                                v
                                         NoSuchMethodError
```

Trong ví dụ này, source ứng dụng không đổi. Khác biệt nằm ở **ABI của thư viện tại runtime**.

### 1.2. Vị trí trong hệ thống Throwable

```text
java.lang.Throwable
  |
  +-- java.lang.Error
        |
        +-- java.lang.LinkageError
              |
              +-- IncompatibleClassChangeError
              |     |
              |     +-- NoSuchMethodError
              |     +-- NoSuchFieldError
              |     +-- AbstractMethodError
              |     +-- IllegalAccessError
              |     +-- ...
              |
              +-- NoClassDefFoundError
              +-- UnsupportedClassVersionError
              +-- ...
```

Sơ đồ mô tả một số nhánh thường gặp, không liệt kê mọi subclass. Cả `NoSuchMethodError` lẫn `NoSuchFieldError` đều là `Error`, không phải checked exceptions.

Vì đây thường là lỗi bất tương thích nhị phân hoặc deployment, hướng xử lý chính là **sửa dependency/classloading/build artifact**, chứ không phải bọc mọi lời gọi bằng `try/catch (Error)` rồi tiếp tục chạy.

### 1.3. Tại sao lỗi có thể chỉ xuất hiện khi vào một endpoint?

Việc resolution những symbolic references có thể diễn ra ở các thời điểm khác nhau tùy JVM/linking và đường thực thi. Một service có thể startup thành công, trả healthcheck bình thường, nhưng lần đầu đi vào chức năng export mới gọi một method không còn tồn tại:

```text
Startup                     -> thành công
Healthcheck                 -> thành công
Login                       -> thành công
Export report               -> NoSuchMethodError
```

Không được xem startup smoke test là bằng chứng toàn bộ binary graph hợp lệ. Cần tests đi qua các nhánh tính năng thực tế, nhất là sau khi thay framework, serialization, ORM, logging hoặc HTTP libraries.

## 2. NoSuchMethodError nghĩa chính xác là gì?

### 2.1. JVM tìm method theo tham chiếu nhị phân

Khi bytecode của caller yêu cầu một method, tham chiếu liên quan không chỉ là tên đơn giản. Nó còn có descriptor mô tả kiểu tham số và kiểu trả về; loại reference và opcode gọi method cũng có ý nghĩa.

Ví dụ source:

```java
package demo.lib;

public final class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

Descriptor của method:

```text
greet(Ljava/lang/String;)Ljava/lang/String;
```

Nghĩa là:

- Tên method: `greet`.
- Một tham số kiểu `java.lang.String`.
- Trả về `java.lang.String`.

Nếu JAR ở runtime chỉ có `greet(Object)`, đó **không phải** method với descriptor mà caller đòi.

### 2.2. Thay đổi tham số là một binary break

Thư viện v1:

```java
public String greet(String name) {
    return "Hello " + name;
}
```

Thư viện v2:

```java
public String greet(CharSequence name) {
    return "Hello " + name;
}
```

Với source code được biên dịch lại, Java compiler có thể chấp nhận lời gọi truyền `String` vào method nhận `CharSequence`. Nhưng `App.class` cũ vẫn tham chiếu descriptor `(Ljava/lang/String;)Ljava/lang/String;`. Nếu thư viện v2 không giữ method cũ, runtime có thể báo `NoSuchMethodError`.

**Source compatibility sau khi biên dịch lại không đồng nghĩa binary compatibility của artifact đã tồn tại.**

### 2.3. Đổi kiểu trả về cũng có thể phá nhị phân

Trong Java source, return type không được dùng riêng để overload hai method cùng tên và cùng tham số. Nhưng ở JVM method descriptor, **return type là một phần của descriptor**.

Ví dụ một thư viện đổi:

```java
public String normalize(String input);
```

thành:

```java
public CharSequence normalize(String input);
```

Caller cũ yêu cầu:

```text
normalize(Ljava/lang/String;)Ljava/lang/String;
```

Nhưng runtime chỉ có:

```text
normalize(Ljava/lang/String;)Ljava/lang/CharSequence;
```

Một lần biên dịch lại có thể sửa tham chiếu; bản bytecode cũ thì không. Trong trường hợp overriding với covariant return, Java compiler có thể sinh **bridge method** để giữ các quan hệ dispatch tương ứng, nhưng không được mặc định mọi phép đổi return type đều có bridge giữ ABI.

### 2.4. Constructor cũng có thể gây NoSuchMethodError

Trong bytecode, constructor dùng tên đặc biệt `<init>`. Ví dụ:

```java
public Client(String endpoint, int timeout);
```

được tham chiếu theo descriptor:

```text
<init>(Ljava/lang/String;I)V
```

Nếu version mới chỉ còn constructor nhận `Duration` thay cho `int`, caller cũ có thể lỗi khi thực hiện `new Client(...)`.

Thông báo của JVM thường thể hiện constructor signature, nhưng định dạng chính xác của lỗi phụ thuộc phiên bản runtime.

### 2.5. Overloading, autoboxing và varargs không tự vá ABI

Compiler có thể chọn một overload khác khi source được biên dịch lại. Nhưng bytecode đã được build lưu lời gọi chính xác.

Ví dụ:

```java
// v1
void send(Integer count);

// v2
void send(int count);
```

Hai descriptors khác nhau:

```text
(Ljava/lang/Integer;)V
(I)V
```

Autoboxing là một khả năng của compiler ở source-level, không phải phép thay method descriptor tùy ý khi JVM resolve bytecode cũ.

## 3. NoSuchFieldError nghĩa chính xác là gì?

### 3.1. Field reference gồm tên và field descriptor

Ví dụ thư viện v1:

```java
package demo.lib;

public final class RetryPolicy {
    public static int DEFAULT_RETRIES = 3;
}
```

Caller:

```java
int retries = RetryPolicy.DEFAULT_RETRIES;
```

Bytecode có thể chứa tham chiếu `getstatic` tới field:

```text
demo/lib/RetryPolicy.DEFAULT_RETRIES:I
```

`I` là descriptor của `int`.

Nếu thư viện v2 thay field thành:

```java
public static long DEFAULT_RETRIES = 3L;
```

thì field runtime có descriptor `J` (long), không còn field đúng tên và kiểu `I` như bytecode caller yêu cầu. Kết quả có thể là `NoSuchFieldError`.

### 3.2. Những thay đổi gây nguy cơ

- Xóa public/protected field mà caller đang tham chiếu.
- Đổi tên field.
- Đổi kiểu field từ `int` sang `long`, `String` sang kiểu khác.
- Di chuyển field sang một lớp không có cùng resolution behavior.
- Thay version thư viện khiến class runtime không có field được caller kỳ vọng.
- Bytecode enhancer hoặc shaded library làm xuất hiện một định nghĩa class khác.

Đừng kết luận chỉ cần nhìn field name. **Field descriptor phải khớp với tham chiếu nhị phân.**

### 3.3. Static/instance mismatch cần được phân biệt

Nếu field vẫn có cùng tên và kiểu nhưng bị đổi từ static thành instance, hoặc ngược lại, có thể xuất hiện lỗi `IncompatibleClassChangeError` liên quan đến cách truy cập field, thay vì một `NoSuchFieldError` đơn thuần.

Tương tự, thay method từ instance thành static có thể làm `invokevirtual` và `invokestatic` không tương thích. Vì vậy cần xem **cả field/method descriptor và bytecode opcode**, không phán đoán mọi sai khác ABI đều cho cùng một lỗi.

### 3.4. Biến hằng compile-time thường bị inline

Một bẫy chẩn đoán:

```java
public static final int MAX_ATTEMPTS = 3;
```

Nếu đây là một **constant variable** theo Java Language Specification, compiler có thể nhúng trực tiếp giá trị `3` vào bytecode của caller. Khi chạy, caller không nhất thiết còn truy cập field bằng `getstatic`.

Hệ quả:

- Xóa hoặc đổi giá trị field không nhất thiết gây `NoSuchFieldError` cho caller đã biên dịch.
- Caller cũ có thể vẫn dùng **giá trị cũ được inline**.
- Biên dịch lại caller sẽ đọc giá trị mới từ quá trình compile, khiến behavior đổi.
- Không được dựa vào việc “không có NoSuchFieldError” để kết luận ABI/data semantics đúng.

Ví dụ field không phải compile-time constant:

```java
public static final Integer MAX_ATTEMPTS =
    Integer.valueOf(3);
```

Reference field này thường cần truy cập runtime; loại thay đổi kiểu/xóa field có thể lộ rõ hơn. Với enum constants, quy tắc liên kết và serialization khác trường hằng primitive/String thông thường.

### 3.5. Đổi accessor field thành method không phải binary-compatible

Nếu v1 công bố:

```java
public static int DEFAULT_TIMEOUT = 30;
```

và v2 chỉ còn:

```java
public static int defaultTimeout() {
    return 30;
}
```

source caller phải đổi từ `Config.DEFAULT_TIMEOUT` sang `Config.defaultTimeout()`. Bytecode caller cũ vẫn tìm field; method mới không tự đáp ứng field reference.

Khi thiết kế public API dài hạn, thường nên tránh phơi field mutable để dễ thay implementation mà vẫn giữ method contract ổn định.

## 4. Minh họa tái hiện NoSuchMethodError bằng hai JAR

### 4.1. Cấu trúc demo

```text
demo/
  lib-v1/
    demo/lib/Greeter.java
  lib-v2/
    demo/lib/Greeter.java
  app/
    demo/app/Main.java
```

File v1:

```java
package demo.lib;

public final class Greeter {
    public String greet(String name) {
        return "v1: " + name;
    }
}
```

File v2:

```java
package demo.lib;

public final class Greeter {
    public String greet(CharSequence name) {
        return "v2: " + name;
    }
}
```

Caller:

```java
package demo.app;

import demo.lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(
            new Greeter().greet("Java")
        );
    }
}
```

### 4.2. Biên dịch caller với v1

Một chuỗi lệnh minh họa cho shell Unix-like:

```shell
mkdir -p build/lib-v1 build/lib-v2 build/app

javac -d build/lib-v1 \
  lib-v1/demo/lib/Greeter.java

jar --create --file build/lib-v1.jar \
  -C build/lib-v1 .

javac -cp build/lib-v1.jar \
  -d build/app app/demo/app/Main.java
```

Với JDK có `jar --create`, lệnh sinh JAR v1 và compile caller dựa trên API v1. Không cần chạy lại lệnh nếu project thật đã có build tool; đây là mô hình để hiểu cơ chế.

### 4.3. Chạy với JAR v1

```shell
java -cp "build/app:build/lib-v1.jar" demo.app.Main
```

Kết quả dự kiến:

```text
v1: Java
```

### 4.4. Biên dịch thư viện v2, không biên dịch lại caller

```shell
javac -d build/lib-v2 \
  lib-v2/demo/lib/Greeter.java

jar --create --file build/lib-v2.jar \
  -C build/lib-v2 .
```

Sau đó dùng `Main.class` đã biên dịch ở bước v1 nhưng đổi runtime JAR:

```shell
java -cp "build/app:build/lib-v2.jar" demo.app.Main
```

Runtime có thể báo lỗi kiểu:

```text
java.lang.NoSuchMethodError:
  'java.lang.String demo.lib.Greeter.greet(java.lang.String)'
```

Định dạng stack trace có thể khác theo JDK. Nguyên nhân là class `Main` vẫn chứa `Methodref` tới `greet(String):String`, trong khi runtime `Greeter` chỉ có `greet(CharSequence):String`.

### 4.5. Vì sao biên dịch lại caller có thể làm hết lỗi?

Nếu build lại `Main.java` với v2, compiler sẽ chọn method mới phù hợp source. Việc đó chứng minh **source có thể thích nghi**, không có nghĩa giữ được binary compatibility với tất cả callers chưa biên dịch lại.

Nếu một public library có nhiều consumers bên ngoài, bạn không thể dựa vào việc mọi consumer sẽ rebuild ngay lập tức để loại lỗi.

## 5. Minh họa tái hiện NoSuchFieldError

V1:

```java
package demo.lib;

public final class Limits {
    public static int MAX_PENDING = 100;
}
```

Caller v1:

```java
package demo.app;

import demo.lib.Limits;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Limits.MAX_PENDING);
    }
}
```

V2:

```java
package demo.lib;

public final class Limits {
    public static long MAX_PENDING = 100L;
}
```

Nếu chỉ thay JAR v1 bằng v2, giữ nguyên `Main.class` cũ, runtime có thể báo `NoSuchFieldError: MAX_PENDING`. Caller đã được biên dịch để đọc field descriptor `I` nhưng v2 chỉ có `J`.

Không dùng `static final int` với compile-time constant để minh họa trường hợp này: giá trị có thể bị inline và che hành vi đọc field tại runtime.

## 6. Phương pháp chẩn đoán: ba câu hỏi bắt buộc

Khi gặp một trong hai lỗi, hãy xác định lần lượt:

1. **Ai là caller?** Class/method trong stack trace đã được biên dịch để gọi symbol nào?
2. **JVM đã nạp implementation từ đâu?** Đường dẫn JAR, module, classloader hoặc deployment layer thực tế là gì?
3. **Class runtime thực sự công bố symbol nào?** Descriptor, access modifier và method/field kind có đúng không?

Sơ đồ quyết định:

```text
NoSuchMethodError / NoSuchFieldError
               |
               v
        Đọc full stack trace
               |
               v
      Xác định caller + symbol
               |
               v
        Tìm class thực tế
       mà JVM đã tải từ đâu
               |
               v
        javap caller + callee
               |
        +------+-------+
        |              |
        v              v
    ABI khác       ABI nhìn có vẻ đúng
        |              |
        v              v
  Sửa dependency   Kiểm tra classloader,
  hoặc giữ ABI     method kind, module,
                   generated/shaded classes
               |
               v
    Test đúng packaged artifact
               |
               v
      Pin graph + CI guard
```

Không bỏ qua bước kiểm tra class runtime. File nằm trong repository hoặc trong cache build chưa chắc là file mà JVM đích đã nạp.

## 7. Đọc stack trace đúng cách

### 7.1. Nhận diện symbol và frame đầu tiên hữu ích

Ví dụ:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
  'com.example.json.JsonNode
   com.example.json.JsonMapper.parse(java.lang.String)'
    at com.example.order.JsonAdapter.decode(JsonAdapter.java:48)
    at com.example.order.OrderService.load(OrderService.java:105)
    at com.example.order.Main.main(Main.java:18)
```

Có hai lớp cần phân biệt:

- `com.example.json.JsonMapper` là **class callee** được JVM tìm method.
- `com.example.order.JsonAdapter` là **caller** có bytecode phát sinh lời gọi thiếu method.

Line `JsonAdapter.java:48` là nơi nên bắt đầu điều tra. Không nhất thiết bug nằm trong source line đó; runtime dependency có thể khác thứ đã dùng khi build.

### 7.2. Wrapper exception có thể che LinkageError

Trong framework, lỗi có thể nằm sâu bên dưới:

```text
BeanCreationException
  caused by: InvocationTargetException
    caused by: NoSuchMethodError
```

Hãy đọc toàn bộ cause chain và lấy **linkage error gốc**. Những lỗi như `IllegalStateException` hoặc failure trong initialization chỉ là wrapper.

### 7.3. Ghi nhận môi trường khi xảy ra lỗi

Tối thiểu:

```text
Service:
Source commit:
Artifact checksum:
JDK vendor/full version:
Framework version:
Runtime module/classpath:
Container image digest:
First failing request/job:
Caller class:
Missing symbol:
Loaded JAR location:
Classloader:
```

Không ghi secret, token, password hoặc dữ liệu người dùng nhạy cảm vào hồ sơ chẩn đoán.

## 8. Dùng javap để xem method và field thực tế

### 8.1. Xem public API và descriptors

```shell
javap -classpath path/to/lib-v1.jar \
  -p -s demo.lib.Greeter
```

`-p` hiển thị cả members không public; `-s` in internal descriptors.

Kết quả minh họa:

```text
public java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
```

Thử với JAR v2:

```shell
javap -classpath path/to/lib-v2.jar \
  -p -s demo.lib.Greeter
```

Nếu chỉ còn:

```text
public java.lang.String greet(java.lang.CharSequence);
  descriptor: (Ljava/lang/CharSequence;)Ljava/lang/String;
```

đã tìm thấy mismatch trực tiếp.

### 8.2. Xem bytecode của caller

```shell
javap -classpath "path/to/app.jar:path/to/lib-v1.jar" \
  -c -v demo.app.Main
```

Tìm:

- `Methodref` hoặc `InterfaceMethodref` trong constant pool.
- Descriptor mà caller thực sự đòi.
- Opcode `invokevirtual`, `invokeinterface`, `invokestatic` hoặc `invokespecial`.
- Class/interface chứa symbol.

Với field, tìm `Fieldref` và opcode `getstatic`, `putstatic`, `getfield`, `putfield`.

Các phần này giúp phân biệt symbol **thực sự được bytecode dùng** với source code hiện tại (source trong checkout có thể đã thay đổi sau lần build artifact lỗi).

### 8.3. Bảng descriptor thường gặp

| Java type | JVM descriptor |
|---|---|
| `void` | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `Object` | `Ljava/lang/Object;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Ví dụ:

```text
Java:       long sum(int a, long b)
Descriptor: (IJ)J

Java:       void setNames(String[] names)
Descriptor: ([Ljava/lang/String;)V
```

`javap -s` hữu ích khi method overload, return type, array hoặc generic type khiến thông báo source-level dễ bị hiểu sai.

### 8.4. Generics và type erasure

Ví dụ `List<String>` và `List<Integer>` đều có erased JVM type `java.util.List`. Đừng kết luận khác generic arguments nhất thiết tạo một method descriptor mới.

Ngược lại, thay erased parameter type từ `List` sang `Collection` có thể đổi descriptor và phá ABI.

Sử dụng `javap -v` để xem `Signature` attribute, bridge methods và descriptors; **JVM linkage dựa vào descriptor và các quy tắc VM tương ứng**, không đơn giản dựa vào Java generic signature dạng source.

## 9. Xác định JAR thực sự được JVM nạp

### 9.1. JVM class loading log trên JDK 9+

Trên những JVM HotSpot/JDK có unified logging:

```shell
java -Xlog:class+load=info \
  -cp "app.jar:lib/*" \
  com.example.Main
```

Log có thể cho biết lớp nào được tải, nguồn file hoặc module. Tùy JDK và logger, nội dung chi tiết khác nhau.

Trong production, log class loading có thể rất lớn. Nên bật có mục tiêu hoặc trên staging với lưu lượng phù hợp, có cơ chế xoay log và xử lý dữ liệu nội bộ.

### 9.2. JDK 8 và verbose class loading

Một cách chẩn đoán truyền thống:

```shell
java -verbose:class \
  -cp "app.jar:lib/*" \
  com.example.Main
```

Cũng có thể dùng trên một số JDK mới, nhưng format output không nhất thiết giống nhau. Không viết parser quá phụ thuộc format log giữa các JDK.

### 9.3. Lấy CodeSource của class khi có thể

Trong môi trường đủ tin cậy, có thể log:

```java
import java.net.URL;
import java.security.CodeSource;

public final class ClassOrigin {
    public static String locationOf(Class<?> type) {
        if (type.getProtectionDomain() == null) {
            return "<no protection domain>";
        }

        CodeSource source =
            type.getProtectionDomain().getCodeSource();

        if (source == null) {
            return "<no code source>";
        }

        URL location = source.getLocation();

        return location == null
            ? "<unknown location>"
            : location.toExternalForm();
    }
}
```

Ví dụ gọi:

```java
System.out.println(
    ClassOrigin.locationOf(demo.lib.Greeter.class));
```

Không phải mọi class có `CodeSource`; classes do bootstrap loader, generated classes hoặc custom loaders có thể trả null hay địa chỉ không đầy đủ. Đối với container/fat JAR, URL còn có thể biểu diễn nested archive. Đây là tín hiệu, không phải nguồn sự thật duy nhất.

### 9.4. Liệt kê duplicate resources

Ở classpath:

```java
import java.net.URL;
import java.util.Enumeration;

Enumeration<URL> found =
    Thread.currentThread()
        .getContextClassLoader()
        .getResources("demo/lib/Greeter.class");

while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
```

Nếu thấy nhiều vị trí khác nhau cùng cung cấp `Greeter.class`, đây là dấu hiệu duplicate classes. Tuy nhiên, context classloader có thể khác loader thực sự đã tải callee, và JPMS/custom loading không nhất thiết hoạt động như classpath thuần. Hãy đối chiếu với `Greeter.class.getClassLoader()` và class-loading log.

### 9.5. Thận trọng khi in classpath trong production

Classpath có thể chứa đường dẫn nội bộ, user names hoặc mount paths. Với application secrets nằm trong JVM flags/system properties, không xuất toàn bộ command line cho người không được phép. Redact trước khi chia sẻ log cho vendor hoặc nơi công cộng.

## 10. Kiểm tra JAR, WAR, EAR và artifact cuối

### 10.1. JAR bình thường

Liệt kê:

```shell
jar --list --file path/to/library.jar
```

Tìm class mục tiêu, manifest và version. `javap` trực tiếp trên bản JAR đó, không dùng bản trong local Maven/Gradle cache theo suy đoán.

### 10.2. Executable/fat JAR có nested dependencies

Một số frameworks đóng gói:

```text
application.jar
  BOOT-INF/classes/...
  BOOT-INF/lib/json-core-a.jar
  BOOT-INF/lib/json-core-b.jar
  META-INF/...
```

Nạp class không nhất thiết dùng classpath phẳng như IDE. Nếu fat JAR chứa bản cũ của `json-core`, đổi dependency trong `pom.xml` nhưng không build lại artifact sẽ không sửa được runtime.

Cần inspect `BOOT-INF/lib` hoặc layout tương ứng của framework, xác định exact nested JAR và checksum.

### 10.3. WAR/EAR và application server

Một server có thể cung cấp JAR ở:

```text
server/lib/
deployment/WEB-INF/lib/
deployment/WEB-INF/classes/
shared modules/
```

Classloader parent-first/child-first, server modules và deployment isolation quyết định class được chọn. Cùng file WAR có thể chạy trên embedded server nhưng lỗi ở server ngoài vì thư viện container cung cấp khác.

Hãy kiểm tra chính sách classloading của đúng server/version, không đoán mọi server đều ưu tiên JAR ứng dụng.

### 10.4. Shading và relocation

Một plugin shading có thể:

- Đổi package class nhưng bỏ sót metadata/service files.
- Đưa hai versions của cùng class vào fat JAR.
- Loại method khi minimize.
- Giữ compiled caller tham chiếu symbol cũ.
- Đóng một module không đúng version dự kiến.

Phải kiểm tra **post-shading artifact**. Một dependency tree sạch trước khi đóng gói không bảo đảm class trong JAR cuối sạch.

### 10.5. Multi-release JAR

MR-JAR có thể chứa:

```text
com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
META-INF/versions/21/com/example/Codec.class
```

JVM mới có thể nạp versioned class phù hợp khi manifest `Multi-Release: true` được dùng đúng. Nếu chỉ inspect base class hoặc một entry ngẫu nhiên, bạn có thể bỏ qua API thật được runtime chọn.

Với MR-JAR, đối chiếu JDK runtime version, manifest, class variants và tooling hỗ trợ `--multi-release` khi phân tích. Không gộp mọi entry thành một ABI không có ngữ cảnh phiên bản.

## 11. Maven: tìm dependency mediation và phiên bản được chọn

### 11.1. Dependency tree

```shell
./mvnw dependency:tree
```

Trong multi-module:

```shell
./mvnw -pl order-service dependency:tree
```

Dùng filters của Maven Dependency Plugin theo phiên bản đang được dùng để tập trung vào group/artifact nghi vấn; nếu cần reproducibility, pin plugin version trong build.

### 11.2. Maven nearest-definition

Giả sử:

```text
order-service
   |
   +-- web-client:2.0
   |      |
   |      +-- json-core:1.5
   |
   +-- report-sdk:3.0
          |
          +-- json-core:2.1
```

Maven thường dùng dependency mediation theo **nearest definition**; cùng độ sâu có thể chịu ảnh hưởng thứ tự dependency declaration, trừ khi `dependencyManagement` hoặc quy tắc khác xác định version. Vì vậy không được mặc định “Maven luôn lấy phiên bản cao nhất”.

Nếu caller được biên dịch để dùng method có ở `json-core:2.1` nhưng runtime chọn `1.5`, có thể xảy ra `NoSuchMethodError`.

### 11.3. Dùng dependencyManagement/BOM

Trong parent POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>json-core</artifactId>
            <version>2.1.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Ví dụ này giúp định hướng version khi dependency tham gia graph. Nó **không** chứng minh `2.1.0` tương thích với tất cả framework modules; cần dùng BOM/version matrix của framework nếu có và chạy tests.

### 11.4. Effective POM và profiles

```shell
./mvnw help:effective-pom
./mvnw help:active-profiles
```

Một profile có thể đổi dependency hoặc được kích hoạt theo JDK/OS. Khi migration, CI Java 21 có thể resolve graph khác CI Java 17 dù source code không đổi.

Lưu effective POM, active profiles và runtime dependency tree cho artifact release. Nếu chỉ đọc root `pom.xml`, có thể bỏ qua parent/configuration mà build thật sử dụng.

### 11.5. Exclusions có mục đích

Nếu một dependency kéo transitive JAR cũ:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>web-client</artifactId>
    <version>2.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>json-core</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Sau exclusion, phải có đường dependency khác cung cấp `json-core` phiên bản đúng. Exclusion có thể làm mất class cần thiết hoặc đẩy runtime sang một version mà `web-client` chưa hỗ trợ.

Không coi exclude là cách “giảm duplicate” vô hại; nó thay dependency graph và cần regression testing.

### 11.6. Maven Enforcer

Maven Enforcer Plugin có thể dùng quy tắc như `dependencyConvergence` và `requireUpperBoundDeps` để phát hiện một số phiên bản không thống nhất. Nhưng graph hội tụ về một version duy nhất vẫn có thể dùng ABI sai so với caller.

Do đó Enforcer là **prevention gate về dependency graph**, không thay thế runtime compatibility tests và API/binary diff.

## 12. Gradle: tìm version conflict và dependencyInsight

### 12.1. Runtime graph

```shell
./gradlew :order-service:dependencies \
  --configuration runtimeClasspath
```

Lệnh này hiển thị resolved graph trong phạm vi configuration. Khi xảy ra linkage error, **runtimeClasspath** thường quan trọng hơn danh sách `implementation` declarations.

### 12.2. Giải thích vì sao version được chọn

```shell
./gradlew :order-service:dependencyInsight \
  --dependency json-core \
  --configuration runtimeClasspath
```

`dependencyInsight` giúp tìm đường đi đến dependency, phiên bản được chọn và những reason/constraints liên quan theo Gradle version.

### 12.3. Cơ chế conflict resolution

Gradle có cơ chế chọn version theo dependency metadata, conflict resolution và constraints; trong nhiều tình huống xung đột compatible versions, Gradle ưu tiên version cao hơn. Nhưng `strictly`, `prefer`, `require`, platform, capabilities, variants và custom rules có thể thay kết quả.

Không copy lý luận “Maven nearest wins” sang Gradle. Phải xem actual resolved graph và lý do lựa chọn của build tool đang chạy.

### 12.4. Constraints và platforms

Ví dụ Groovy DSL:

```groovy
dependencies {
    implementation platform(
        'com.example:framework-bom:5.1.0'
    )

    constraints {
        implementation('com.example:json-core') {
            version {
                strictly('2.1.0')
            }
            because 'ABI tương thích đã được xác nhận'
        }
    }
}
```

Constraint có thể giúp fail rõ khi một dependency đòi version không tương thích. Nhưng đừng dùng `strictly` hoặc `force` để cưỡng ép một version chưa thử với framework đang dùng.

### 12.5. Dependency locking

Lockfile giúp giữ resolved versions ổn định qua các lần build. Nếu muốn sửa `NoSuchMethodError` do lệch version, hãy thay version declarations/constraints đúng theo compatibility matrix, cập nhật lock với quy trình chính thức và review diff.

**Không** sửa lockfile bằng tay rồi coi đó là bằng chứng đã tìm đúng JAR production. Cần xây lại application artifact và kiểm tra runtime classes.

### 12.6. Compile và runtime classpath khác nhau

Trong Gradle:

- `compileClasspath` và `runtimeClasspath` có thể resolve khác.
- `compileOnly` không tự trở thành runtime dependency.
- `runtimeOnly` không xuất hiện ở compile classpath.
- `api`/`implementation` thể hiện việc lộ types của library.
- Custom configurations hoặc plugins có thể thêm dependencies khác.

Một library được compile với `json-core:2.1` nhưng application runtime dùng `1.5` là tình huống linkage error điển hình. Điều cần sửa là publication/consumer graph chứ không chỉ source module đó.

## 13. So sánh compile-time và runtime dependency graphs

### 13.1. Cùng một dependency nhưng hai phiên bản

```text
Compile time:
  order-service:1.0
     -> json-core:2.1  (có parse(String))

Runtime:
  order-service:1.0
     -> json-core:1.5  (không có parse(String))
```

Caller bytecode có:

```text
invokevirtual JsonMapper.parse(Ljava/lang/String;)LJsonNode;
```

Nhưng class runtime không có descriptor đó. Đây là minh họa thuần túy về cách lỗi xảy ra.

### 13.2. Build pipeline và deployment pipeline có thể dùng graph khác

Ví dụ CI build:

```text
mvn verify
  -> application.jar
  -> dependencies in target/lib
```

Nhưng deploy:

```text
application.jar
  + old shared/lib/json-core-1.5.jar
  + new target/lib/json-core-2.1.jar
```

Classpath ordering/classloader policy có thể chọn một trong hai. Fix source/`pom.xml` mà không thay deployment layout sẽ không giải quyết được.

### 13.3. Local cache khác runtime thực tế

Maven/Gradle cache có thể chứa nhiều JAR versions. Chỉ thấy `json-core-2.1.jar` trong local cache không có nghĩa đó là bản đang chạy.

Cần chứng cứ từ production class-loading origin, artifact checksum hoặc exact deployment image. Cache cleanup hữu ích để loại một số lỗi local, nhưng không thay root-cause investigation.

## 14. Các lỗi dễ nhầm và cách phân biệt

| Lỗi | Ý nghĩa thường gặp | Kiểm tra ưu tiên |
|---|---|---|
| `NoSuchMethodError` | Method descriptor caller cần không resolve được | `javap` caller/callee; JAR runtime |
| `NoSuchFieldError` | Field name+descriptor caller cần không resolve được | `Fieldref`, field descriptor, JAR runtime |
| `NoClassDefFoundError` | Class không thể được định nghĩa/tải đúng lúc cần, có thể class từng failed initialization | Thiếu JAR, classloader, cause chain |
| `ClassNotFoundException` | Hoạt động tìm class qua API có thể ném checked exception | Classpath/module path, dynamic load name |
| `IncompatibleClassChangeError` | Static/instance hoặc class/interface assumptions không còn đúng | Opcode, class kind, ABI |
| `AbstractMethodError` | Lời gọi method bị resolve nhưng runtime không có implementation cụ thể phù hợp | Interface evolution, implementation version |
| `IllegalAccessError` | JVM từ chối quyền truy cập member/class sau thay đổi visibility/module | Access flags, JPMS exports/opens |
| `UnsupportedClassVersionError` | Class-file version quá mới cho JVM | JVM runtime và class major |
| `NoSuchMethodException` | Reflection API không tìm thấy method theo criteria | Reflection lookup, visibility, parameters |
| `NoSuchFieldException` | Reflection API không tìm thấy field | Reflection lookup, inheritance, declared/public |

Không áp dụng một giải pháp “nâng dependency” cho mọi lỗi. Mỗi loại cho biết một giai đoạn thất bại khác nhau.

### 14.1. NoSuchMethodException không phải NoSuchMethodError

Reflection:

```java
Class<?> type = Class.forName("demo.lib.Greeter");
type.getDeclaredMethod("greet", String.class);
```

có thể ném `NoSuchMethodException`, một checked exception, nếu method không được tìm thấy theo quy tắc reflection.

Ngược lại, bytecode `invokevirtual` đã được compile trỏ tới method không resolve được có thể ném `NoSuchMethodError`. Cách điều tra liên quan nhưng không giống nhau.

### 14.2. IllegalAccessError và JPMS

Nếu method tồn tại và descriptor đúng, nhưng accessibility ở runtime không hợp lệ, lỗi có thể là `IllegalAccessError`. Với reflection trên JDK mới, `InaccessibleObjectException` còn có thể phát sinh do module strong encapsulation.

Đừng dùng `--add-opens` để chữa `NoSuchMethodError` khi method thực sự đã bị xóa. Mở module access không tạo lại binary method cũ.

### 14.3. AbstractMethodError khi thay interface

Một interface thêm abstract method mới, còn implementation class cũ chưa implement, có thể dẫn đến `AbstractMethodError` khi method được gọi trong một số tình huống binary evolution.

Không kết luận mọi interface addition đều phá binary compatibility ngay từ lúc load; cần xem cách caller invoke và implementation có method thực tế không.

## 15. Đặc thù khi nâng JDK 8 lên 17/21/25

### 15.1. JDK nâng cấp không tự tạo method bị mất

Một `NoSuchMethodError` trong thư viện bên thứ ba sau nâng JDK có thể do:

- Framework/BOM đổi dependency version.
- Gradle/Maven plugin mới chọn transitive graph khác.
- Application server thay thư viện cung cấp.
- Bytecode enhancer hoặc agent không tương thích.
- Runtime path hoặc classloader thay đổi.
- Class/API nội bộ của JDK bị thay đổi.

Đừng gán nguyên nhân trực tiếp cho JDK khi chưa xác định callee class nằm trong JDK hay trong third-party artifact.

### 15.2. Nếu callee là class của Java SE API

Nếu stack trace chỉ đến `java.*` hoặc `javax.*`/`jdk.*`, cần xác định:

- Method thuộc API công khai hay JDK internal API?
- Nó có tồn tại trong release Java thực tế không?
- Compiler dùng `--release` phù hợp chưa?
- Có dependency tự đóng JDK API class hoặc shadowing không?
- Framework/agent có dựa vào internal APIs không?
- Runtime thực tế là JDK mấy, của vendor nào?

Ví dụ biên dịch bằng JDK 21, chỉ đặt `-source 17 -target 17` có thể cho phép tham chiếu API Java 21 tùy cách cấu hình compiler/platform APIs, trong khi artifact chạy trên Java 17. Với `javac` hiện đại, `--release 17` là cách tốt hơn để giới hạn Java SE API tương ứng release 17.

### 15.3. JDK internals và API không bảo đảm ổn định

Một library cũ có thể gọi `sun.*` hoặc `jdk.internal.*` APIs không được cam kết như Java SE public API. Khi nâng JDK, class/method nội bộ có thể đổi hoặc bị chặn truy cập.

Khi đó, giải pháp dài hạn là cập nhật framework/agent/library lên bản hỗ trợ JDK đích hoặc chuyển sang API được hỗ trợ. Cờ `--add-exports`/`--add-opens` chỉ giải quyết một số vấn đề truy cập, không khôi phục method đã bị xóa.

### 15.4. Nâng compiler target và dependency cùng nhau

Một thư viện Java 21 bytecode (major 65) không thể chạy trên Java 17, dù code gọi method có cùng tên với một API ở Java 17. Ngược lại, thư viện Java 17 bytecode vẫn có thể dùng một dependency không tương thích binary khi app runtime chọn bản khác.

Cần kiểm tra cả:

1. Class-file level.
2. Java platform API level.
3. Dependency ABI.
4. Runtime behavior.

## 16. Framework migration và BOM mismatch

### 16.1. Tại sao lỗi hay xuất hiện sau nâng framework?

Framework thường công bố một bộ dependency versions được thử cùng nhau. Ví dụ một framework release line thay ORM/JSON/HTTP libraries. Nếu chỉ nâng framework core nhưng giữ một số starter/plugin cũ, runtime có thể chứa các module có kỳ vọng API khác nhau.

```text
framework-core:v5 -> calls codec.normalize(String)
adapter-plugin:v3 -> brings codec:v1
framework-bom:v5  -> expects codec:v2
```

Khi runtime chọn v1, core có thể ném `NoSuchMethodError`. Lời giải không phải ép “version mới nhất trên internet” mà là chọn bộ framework/plugin/BOM được hỗ trợ và kiểm thử.

### 16.2. Spring và hệ sinh thái module

Khi dùng Spring Framework/Boot/Data/Security/Cloud, cần đọc compatibility matrix của **đúng release lines**, không tự trộn các module “mới nhất”.

Nếu làm việc với WAR trên server ngoài, dependency được server cấp có thể khác executable JAR. Hãy xác định version của embedded/external server và Java/Jakarta namespace tương ứng.

### 16.3. Jakarta migration

Chuyển từ `javax.*` sang `jakarta.*` thường làm thay đổi binary class names, dẫn đến `ClassNotFoundException`/`NoClassDefFoundError` hoặc method signature mismatch khi các thư viện trộn hai thế hệ API.

Đừng mặc định mọi lỗi trong quá trình Jakarta migration sẽ là `NoSuchMethodError`. Hãy xem class/method descriptors và data/API compatibility thực tế.

### 16.4. Logging binding và bridge libraries

Một ứng dụng có thể giữ nhiều bindings/bridges hoặc plugin logging khác version với logging API. Linkage errors có thể xảy ra khi logger caller được compile against API mới nhưng runtime chọn JAR cũ.

Tách các module:

- Logging API.
- Logging implementation.
- Bridges/adapters.
- Framework logging starter.
- Application-server-provided bindings.

Sau đó đối chiếu graph và bản thực sự được classloader tải.

### 16.5. Jackson, Hibernate và Netty như nhóm cần chú ý

Các thư viện serialization, ORM và network thường có nhiều artifacts cùng một hệ sinh thái. Nếu core module và companion module quá khác version, có thể lộ lỗi linkage ở code path ít dùng.

Không cần ép mọi module có version string giống hệt nếu vendor công bố bộ tương thích khác; nên ưu tiên BOM hoặc ma trận chính thức của đúng framework và thực hiện regression tests.

## 17. Java record, enum, sealed class và API binary

### 17.1. Record accessor thay đổi

Ví dụ Java 17 record:

```java
public record Customer(String name, long id) {
}
```

Record có accessor `name():String` và `id():long`. Nếu phiên bản mới đổi component `name` sang `CharSequence`, accessor descriptor thay đổi. Caller cũ đã compile gọi `name():String` có thể gặp `NoSuchMethodError` khi runtime chỉ có accessor mới.

Cần đánh giá record evolution như API/serialization contract, không coi việc giữ cùng record name là đủ.

### 17.2. Enum constants và field references

Enum constants được biểu diễn như static fields của enum type. Xóa hoặc đổi tên enum constant có thể làm code cũ sử dụng `getstatic` tới field không còn tồn tại và dẫn đến `NoSuchFieldError`.

Với dữ liệu serialized/JSON chứa enum name, còn có vấn đề protocol compatibility. Giải pháp nên gồm versioning và mapping/unknown-value policy thay vì chỉ biên dịch lại.

### 17.3. Sealed classes và pattern matching

Chuyển type hierarchy sang sealed có thể thay đổi tập implementations được phép và behavior của exhaustive switch ở các phiên bản Java mới. Không phải mọi lỗi sẽ là `NoSuchMethodError`, nhưng binary/API compatibility cần xem xét cùng migration.

### 17.4. Kotlin/Groovy/Scala và generated code

Những JVM languages khác có compiler conventions, bridges, default methods và binary metadata khác Java source thuần. Khi nâng compiler plugin hoặc library, code Java cũ có thể gọi symbol không còn ở runtime.

Hãy xem **bytecode descriptors thật** bằng `javap`, không suy từ source-level API của Kotlin/Groovy/Scala. Generated bytecode bởi annotation processor/AOP cũng cần được kiểm tra sau build.

## 18. Bytecode generation và instrumentation

### 18.1. Byte Buddy, ASM, Javassist, proxies

Frameworks có thể sinh class lúc runtime, tạo subclass hoặc instrument bytecode. Nếu chúng dựa vào version method không còn tồn tại, lỗi có thể lộ trong generated class thay vì source project.

Điều tra:

- Stack trace có generated/proxy class names không?
- Agent/transformer versions là gì?
- Chúng có hỗ trợ class-file version JDK đích không?
- Proxy được sinh từ interface version nào?
- Có cache generated classes từ quá trình build trước không?
- Lỗi xảy ra khi load class, gọi method hay reflect method?

### 18.2. Cẩn thận với bridge methods

Java compiler có thể sinh bridge/synthetic methods để giữ polymorphism sau type erasure hoặc covariant return. Một transformer/minimizer loại những bridge methods vì tưởng là “không dùng” có thể gây lỗi linkage.

Dùng:

```shell
javap -classpath path/to/library.jar \
  -p -s -v com.example.SomeClass
```

Tìm flags `ACC_BRIDGE` và `ACC_SYNTHETIC` khi thích hợp. Không tự xóa generated methods khỏi artifact mà chưa biết compatibility requirements.

### 18.3. Annotation processor và Lombok

Một phần method/field của thư viện có thể được sinh ở compile-time bởi Lombok/processor. Nếu IDE và CI dùng processor versions khác nhau, bytecode artifacts có thể khác ngay cả khi source trông giống nhau.

Cần kiểm tra compiled class trong JAR được publish, không chỉ annotation hay generated source dự kiến.

### 18.4. Agent khác version với JVM

Một APM agent hoặc mocking agent không hỗ trợ JDK mới có thể instrument class sai hoặc gọi API đã đổi. Khi chẩn đoán, test ứng dụng với/không với agent trong môi trường được kiểm soát và đối chiếu agent compatibility matrix.

Không nên tắt agent production vĩnh viễn chỉ để che lỗi; cần upgrade hoặc chọn cấu hình được hỗ trợ.

## 19. Classloader isolation, plugin architecture và application server

### 19.1. Cùng tên class không đồng nghĩa cùng class

Trong JVM, identity của class phụ thuộc cả tên nhị phân và **defining classloader**. Hai loaders có thể tải hai định nghĩa cùng tên `com.example.json.JsonMapper` từ hai JARs.

```text
Parent loader
  -> json-core:v1

Child plugin loader
  -> json-core:v2

Caller from plugin -> expects API v2
Runtime binding -> may resolve v1 or v2
depending on loader delegation/isolation
```

Nếu plugin được biên dịch với v2 nhưng runtime class được chọn từ parent v1, `NoSuchMethodError` có thể xuất hiện.

### 19.2. Parent-first và child-first

Không có một quy tắc phổ quát cho mọi framework:

- Một số container ưu tiên parent JAR.
- Một số plugin systems dùng child-first.
- OSGi/modules có mô hình import/export khác.
- JPMS dùng resolution/readability và module layers.
- Spring Boot executable JAR dùng launcher/classloader layout riêng.

Cần đọc cấu hình classloader của runtime đang dùng và lấy chứng cứ class origin.

### 19.3. Duplicate API class trong plugin JAR

Nếu host và plugin đóng hai bản interface giống tên nhưng khác loader, có thể gặp `ClassCastException` hoặc linkage errors khác. Một plugin tốt nên dùng API contract do host chia sẻ, không tùy tiện shade/đóng lại API class cùng identity logic.

### 19.4. Hot reload/redeploy

Một số application servers giữ shared classloaders hoặc cache qua redeploy. Thay WAR nhưng shared library version cũ vẫn nằm trong process có thể gây lỗi.

Đừng chỉ copy JAR mới và cho rằng runtime đã tải nó. Xác nhận deployment lifecycle, classloader state, process restart requirement và log class loading thực tế.

## 20. JPMS: module path cũng có thể lệch version

### 20.1. Module resolution

Khi ứng dụng dùng `module-info.java`, JVM/module system giải quyết named modules theo module path. Một module graph hợp lệ về readability vẫn có thể chứa module version có API khác với lúc compile.

Cần xác định:

- Module name và version metadata.
- Module path được launcher dùng.
- `requires` của callers.
- `exports`/`opens` của callees.
- Module layer/custom loader.
- Artifact thực tế được resolve.

### 20.2. Lỗi module khác lỗi thiếu method

Module không được tìm thấy có thể gây `FindException` trong giai đoạn resolution. Quyền truy cập không hợp lệ có thể gây `IllegalAccessError` hoặc reflection-related exception.

Nếu module tải được nhưng method descriptor không còn, `NoSuchMethodError` vẫn là một khả năng. Không dùng `--add-reads`/`--add-opens` như giải pháp chung cho symbol không tồn tại.

### 20.3. Automatic modules và split packages

Legacy JAR đưa lên module path có thể trở thành automatic module; split packages hoặc tên module xung đột làm resolution khác classpath. Trong migration JDK 8 lên 17+, cần kiểm tra cả cơ chế packaging và module graph, không chỉ đổi `-cp` thành `--module-path`.

## 21. Cách chữa lỗi bền vững

### 21.1. Khôi phục binary API cũ khi duy trì library

Nếu bạn là người phát hành library và đã lỡ đổi method signature, một cách giữ ABI là giữ overload cũ:

```java
public final class Greeter {
    // API mới:
    public String greet(CharSequence name) {
        return "Hello " + name;
    }

    // Compatibility method cho caller cũ:
    @Deprecated
    public String greet(String name) {
        return greet((CharSequence) name);
    }
}
```

Caller cũ tìm thấy `greet(String):String`; caller mới có thể dùng API hiện đại. Method này phải thực sự tồn tại trong JAR runtime và duy trì behavior phù hợp.

Nếu method cũ có một return descriptor đã bị đổi, có thể cần giữ một adapter API hoặc major version riêng, không thể luôn thêm overload chỉ khác return type trong Java source.

### 21.2. Chọn đúng dependency version cho runtime

Nếu caller dùng API v2, còn runtime cung cấp v1, có hai hướng:

- Nâng runtime library lên version tương thích với caller và toàn framework.
- Giữ runtime v1 rồi compile/release lại caller thích hợp nếu v1 là version bắt buộc.

Không sửa bằng cách chọn version cao nhất ngẫu nhiên. Cần xem binary compatibility, security, Java minimum level và support matrix của ecosystem.

### 21.3. Rebuild tất cả dependent modules khi cần

Trong một monorepo, nếu API thay đổi một cách có chủ đích, cần rebuild downstream modules against version mới, kiểm tra complete binary graph và đóng gói lại.

Nhưng đối với published library có external consumers, rebuild nội bộ không đủ. Có thể phải giữ binary-compatible methods hoặc phát hành major release migration.

### 21.4. Loại duplicate JAR khỏi deployment

Nếu runtime có cùng class trong nhiều JAR, phải tìm nguyên nhân:

- App bundle chứa hai phiên bản.
- Server shared libraries lấn WAR libs.
- Shadow plugin đóng cả bản cũ và mới.
- Container layer còn artifact cũ.
- Plugin đóng lại thư viện chung.

Loại/cách ly bản không đúng theo thiết kế và test đúng deployment layout sau sửa.

### 21.5. Sửa classloader policy chỉ khi hiểu phạm vi

Đổi sang child-first có thể làm một plugin dùng được v2 nhưng phá những API chung với host hoặc gây class identity conflicts. Thay đổi delegation là một quyết định kiến trúc có ảnh hưởng lớn; chỉ thực hiện khi đã xác định hợp đồng chia sẻ và test các plugin khác.

## 22. Không nên làm gì khi xử lý sự cố

**Không bắt `NoSuchMethodError` rồi tiếp tục business flow như không có gì.** Đây là dấu hiệu deployment/ABI không nhất quán; có thể khiến dữ liệu ghi dở dang hoặc ứng dụng lỗi ở code path khác.

**Không chỉ xóa Maven/Gradle cache và kết luận xong.** Cache có thể là một yếu tố nhưng phải chứng minh JAR thực tế thay đổi và vì sao.

**Không đổi JDK version tùy ý.** JDK mới không tự khôi phục một method đã bị thư viện loại bỏ.

**Không ép version bằng force/strictly mà chưa xem caller requirement.** Một version có thể phù hợp một module nhưng phá module khác.

**Không chỉ kiểm tra source declarations.** JVM chạy bytecode và artifact thực tế; source ở checkout có thể không trùng release.

**Không chỉ chạy unit tests với compile classpath.** App production có thể có runtime-only dependency, WAR libs, nested JAR và agents khác.

**Không dùng `--add-opens` để tạo method/field đã mất.** Module access khác symbolic resolution.

**Không mặc định cùng version string là cùng artifact bytes.** Repository mutable hoặc cache bị nhiễm có thể làm same coordinates khác checksum.

**Không bỏ qua stack trace đầu tiên.** Wrapper errors sau đó có thể là hệ quả, không phải nguyên nhân.

## 23. Quy trình xử lý production incident

### Bước 1: Giữ bằng chứng

Lưu full stack trace và cause chain. Ghi service version, source commit, image digest, JDK vendor/full version, deployment platform, thời điểm lỗi, request/job type và các changes gần đây.

### Bước 2: Xác định phạm vi

Lỗi xuất hiện ở:

- Mọi request hay chỉ feature cụ thể?
- Một pod/VM hay toàn fleet?
- Chỉ Java 21 hay cả Java 17?
- Chỉ khi bật APM agent?
- Chỉ WAR trên external server?
- Chỉ bản canary sau đổi dependency?

Phân nhóm giúp khoanh vùng version/environment thay vì tìm từng source file ngẫu nhiên.

### Bước 3: Tìm missing symbol

Đọc message `NoSuchMethodError` hoặc `NoSuchFieldError`, ghi class, name và descriptor dự kiến nếu có. Xác định caller frame ngay nơi lỗi phát sinh.

### Bước 4: Tìm JAR runtime

Dùng class-loading logs, `CodeSource`, runtime bundle inspection hoặc server classloader diagnostics. Không dùng local cache như bằng chứng duy nhất.

### Bước 5: So sánh bytecode

Dùng `javap -p -s -v` trên caller và callee; xác định chính xác missing descriptor/opcode/field kind.

### Bước 6: Phân tích dependency resolution

Kiểm tra Maven `dependency:tree` hoặc Gradle `dependencies`/`dependencyInsight`, cùng BOM, plugin versions và runtime deployment graph.

### Bước 7: Quyết định containment

Nếu sự cố ảnh hưởng production, cân nhắc rollback về một **tổ hợp artifact + dependencies + runtime đã được kiểm thử**, hoặc tắt feature có kiểm soát. Không đổi một JAR đơn lẻ trên hệ thống đang chạy mà chưa biết dependency coupling.

### Bước 8: Sửa nguyên nhân

Cập nhật dependency/BOM, giữ compatibility method/field, sửa packaging, thay classloader policy có kiểm chứng hoặc sửa build pipeline tùy root cause.

### Bước 9: Kiểm chứng

Test trên JDK, OS, classloader, agents và final deployment artifact giống production. Chạy cả chức năng từng lỗi và regression/contract tests liên quan.

### Bước 10: Ngăn tái diễn

Pin graph, thêm binary/API checks, log artifact provenance và chặn duplicates/mismatched variants trong CI.

## 24. Ma trận các trường hợp cụ thể

| Triệu chứng | Dấu hiệu | Điểm kiểm tra đầu tiên |
|---|---|---|
| Lỗi sau thêm thư viện mới | Transitive version thay đổi | Resolved runtime dependency tree |
| Lỗi chỉ trên application server | Shared libs/classloader khác | Server libs và class origin |
| Lỗi chỉ trong fat JAR | Nested/shaded libs sai | Artifact sau packaging |
| Lỗi sau nâng Spring/ORM | BOM/release train không đồng bộ | Framework compatibility matrix |
| Lỗi sau nâng JDK | Plugin/agent/framework internal API thay đổi | Callee origin và JDK-specific calls |
| Lỗi chỉ khi gọi endpoint | Lazy method resolution | Caller bytecode và integration path |
| Lỗi trên pod canary | Image/version mismatch | Image digest và exact JAR checksums |
| `NoSuchFieldError` với enum | Constant bị xóa/đổi tên | Enum binary fields và schema |
| Lỗi mất sau rebuild toàn bộ | ABI v1 caller còn sót | Build/release provenance và stale artifacts |
| Lỗi chỉ sau hot reload | Old classloader/JAR | Redeploy process state |
| Lỗi sau shading/minimize | Bridge hoặc method bị bỏ | Final JAR disassembly |
| Lỗi chỉ trên một JDK | MR-JAR class variant | `META-INF/versions` và runtime selection |

## 25. CI gates để tránh NoSuchMethodError và NoSuchFieldError

### 25.1. Pin dependency graph

- Dùng BOM/platform/dependencyManagement cho framework family.
- Không dùng dynamic versions trong release path nếu không có locking/quy trình kiểm soát.
- Commit Gradle lockfile khi dùng dependency locking.
- Review dependency diff cho mọi PR nâng framework/JDK.
- Xác minh repository artifact integrity khi cần.
- Không publish mutable release JAR cùng coordinates.

### 25.2. API/binary compatibility checks cho library

Dùng công cụ như `japicmp`, `Revapi` hoặc giải pháp tương đương để so API/ABI giữa bản đang phát hành và bản ứng viên.

Cần hiểu phạm vi tool: nó giúp phát hiện thay đổi public/protected API, method descriptors, field types và một số signature changes, nhưng không thay thế runtime tests, reflection contract hoặc protocol compatibility.

### 25.3. Test compile/runtime classpath

Một job có thể so resolved graph của compile/runtime và kiểm tra sự khác biệt có chủ đích. Đặc biệt chú ý:

- `compileOnly`/`provided`.
- Optional dependencies.
- Test-only libraries.
- Application-server-provided JARs.
- Plugin classpath.
- Shaded/nested JARs.
- OS/JDK conditional dependencies.

Không yêu cầu hai graphs giống hệt vì một số dependency chỉ cần runtime, nhưng phải chứng minh mọi runtime caller nhận đúng ABI.

### 25.4. Quét duplicate classes

Có thể dùng build plugins hoặc script được quản lý để phát hiện cùng một binary class name trong nhiều runtime JARs. Duplicate classes không luôn là lỗi nếu có isolation hợp lệ, nhưng phải được xem xét thay vì bỏ qua.

Báo cáo nên chỉ rõ:

```text
Class:
  com.example.json.JsonMapper

Origins:
  json-core-1.5.jar
  json-core-2.1.jar

Expected loader:
  application runtime loader

Decision:
  select one compatible JAR or isolate intentionally
```

### 25.5. Test artifact cuối

Trước release, chạy:

```text
Compile -> Test -> Package -> Inspect artifact
                         |
                         v
                Run packaged release
                         |
                         v
                 Integration tests
                         |
                         v
                Staging / canary
```

Một test chỉ chạy trong Maven/Gradle trước packaging không bảo đảm WAR/uber JAR/container image dùng đúng JAR khi deploy.

### 25.6. Test minimum và target JDK

Nếu library cam kết hỗ trợ Java 17 và Java 21:

- Compiler tạo class-file target phù hợp.
- Runtime graph dùng dependency versions hỗ trợ Java 17.
- Chạy tests trên Java 17 thực tế.
- Chạy tests trên Java 21 thực tế.
- Kiểm tra agent, native, framework và MR-JAR variants nếu có.

Không coi ứng dụng chạy trên Java 21 là bằng chứng tương thích Java 17.

## 26. Bài tập thực hành

### Bài tập 1: Method bị đổi tham số

Một library v1 công bố:

```java
public String render(String value);
```

v2 chỉ còn:

```java
public String render(CharSequence value);
```

Caller cũ đã biên dịch với v1.

Hãy nêu descriptor v1/v2, giải thích `NoSuchMethodError`, thử `javap` và đề xuất sửa ABI phù hợp nếu phải hỗ trợ binary consumers cũ.

### Bài tập 2: Field bị đổi kiểu

Một library v1 công bố:

```java
public static int TIMEOUT = 30;
```

v2 đổi sang:

```java
public static long TIMEOUT = 30;
```

Hãy mô tả field descriptors, opcode đọc static field và lý do caller cũ có thể gặp `NoSuchFieldError`.

So sánh với trường hợp:

```java
public static final int TIMEOUT = 30;
```

và giải thích constant inlining khiến lỗi có thể không xuất hiện nhưng giá trị sử dụng vẫn cũ.

### Bài tập 3: Maven conflict

```text
app
  +-- A -> codec:1.0
  +-- B -> codec:2.0
```

Caller trong B cần method chỉ có ở 2.0. Hãy dùng dependency tree và dependencyManagement để phân tích. Không được chọn một phiên bản cho đến khi xác nhận A/B binary compatibility.

### Bài tập 4: Gradle runtime graph

Một project compile với `codec:2.0` nhưng runtimeClasspath chọn `codec:1.0` do một custom resolution rule.

Hãy mô tả lệnh `dependencyInsight`, cách đọc selection reason và kiểm chứng bằng `javap` trên actual JAR.

### Bài tập 5: WAR chạy khác executable JAR

Ứng dụng chạy được khi dùng embedded server nhưng `NoSuchMethodError` trên application server ngoài. Hãy lập trình tự thu thập:

- Version ứng dụng và server.
- WAR contents.
- Shared server libraries.
- Parent-first/child-first policy.
- Class origin.
- Runtime method descriptor.

### Bài tập 6: MR-JAR

Một class có base implementation và variant dưới `META-INF/versions/21`. Lỗi chỉ xuất hiện trên Java 21. Hãy xác định phiên bản class được chọn, manifest và symbol trong variant, rồi giải thích vì sao xem base class là chưa đủ.

### Bài tập 7: Thiết kế CI prevention

Hãy thiết kế pipeline có dependency lock/BOM, API binary diff, duplicate-class scan, artifact inspection và runtime integration tests. Nêu loại lỗi mỗi gate có thể phát hiện và những loại lỗi nó không thể chứng minh.

## 27. Checklist chẩn đoán nhanh

### Thu thập chứng cứ

- [ ] Có full exception message và cause chain.
- [ ] Xác định caller, callee, method/field và descriptor.
- [ ] Ghi đúng JDK vendor/version và deployment artifact digest.
- [ ] Biết lỗi chỉ xuất hiện ở đường chức năng nào.
- [ ] Có class-loading source hoặc runtime JAR location.
- [ ] Có thông tin classloader/module path nếu cần.
- [ ] Không chia sẻ secrets trong diagnostic logs.

### Phân tích bytecode

- [ ] Dùng `javap -p -s` trên đúng runtime class.
- [ ] Dùng `javap -c -v` để xem caller references/opcodes.
- [ ] Kiểm tra return type và argument descriptors.
- [ ] Kiểm tra static/instance kind và access flags.
- [ ] Kiểm tra synthetic/bridge methods nếu liên quan.
- [ ] Kiểm tra enum/record/MR-JAR đặc thù khi áp dụng.
- [ ] Phân biệt compiled source hiện tại với bytecode deployed.

### Dependency và packaging

- [ ] Maven/Gradle runtime dependency graph được xác minh.
- [ ] BOM/platform/plugin versions đúng release line.
- [ ] Compile/runtime classpaths khác nhau có lý do rõ.
- [ ] Không còn JAR cũ/duplicate class ngoài ý muốn.
- [ ] Đã inspect WAR/fat/nested/shaded artifact cuối.
- [ ] Đã xem application server shared libs/classloader policy.
- [ ] Đã xác định agents/native/plugin dependencies khi dùng.

### Khắc phục và phòng ngừa

- [ ] Chọn version/ABI được support thay vì nâng ngẫu nhiên.
- [ ] Rebuild callers hoặc giữ compatibility API khi phù hợp.
- [ ] Chạy integration tests trên đúng runtime JDK.
- [ ] Dùng binary/API checker cho published libraries.
- [ ] Pin dependency graph và review version diffs.
- [ ] Có canary/rollback với immutable artifacts.
- [ ] Bổ sung test cho đúng code path từng gây lỗi.

## Kết luận

`NoSuchMethodError` và `NoSuchFieldError` là hai dấu hiệu điển hình của **binary linkage mismatch**: bytecode caller đang yêu cầu một method hoặc field không tồn tại với **đúng tên và descriptor** trong class runtime được JVM chọn. Chúng có thể xuất hiện sau nâng JDK/framework không phải vì compiler tự nhiên sai, mà vì dependency resolution, classloading, bytecode generation hoặc packaging đã khiến **API lúc biên dịch và API lúc chạy lệch nhau**.

Cách giải quyết hiệu quả nhất là đi từ bằng chứng: đọc full stack trace, xác định caller và symbolic reference, tìm đúng JAR/module/classloader, so descriptor bằng `javap`, phân tích Maven/Gradle graph và kiểm tra artifact cuối. Sau đó chọn version tương thích hoặc khôi phục binary API cũ, chạy tests trên JDK/deployment target và đặt CI gates cho dependency, ABI, duplicate classes và release provenance. Làm đúng chuỗi này giúp Java Advance Compatibility Migration tránh những lỗi chỉ bùng phát khi một tính năng thực sự được gọi trong production.

