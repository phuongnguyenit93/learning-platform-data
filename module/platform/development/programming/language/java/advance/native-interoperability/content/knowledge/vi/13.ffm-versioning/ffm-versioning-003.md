# FFM và phiên bản — Tùy chọn --enable-preview khi biên dịch và chạy mã FFM cho JDK 21

## 1. FFM trong JDK 21: vì sao cần preview?

**Foreign Function & Memory API (FFM)** cho phép chương trình Java truy cập bộ nhớ ngoài heap và tương tác với native functions. JDK 21 cung cấp các API FFM trong package `java.lang.foreign`, chẳng hạn `Arena`, `MemorySegment`, `ValueLayout`, `Linker`, `SymbolLookup` và `FunctionDescriptor`.

Ở **JDK 21**, FFM theo **JEP 442: Third Preview**. Preview API là một API có sẵn để lập trình viên thử nghiệm và gửi phản hồi, nhưng chưa được chốt thành API vĩnh viễn của Java SE ở phiên bản đó. Vì vậy, compiler và JVM **mặc định không cho phép sử dụng** FFM preview nếu không bật flag.

Đối với source dùng FFM của JDK 21:

```bash
# Dùng javac từ JDK 21 để biên dịch
javac --enable-preview --release 21 -d out PreviewMemoryDemo.java

# Dùng java từ JDK 21 để thực thi
java --enable-preview -cp out PreviewMemoryDemo
```

**Phải bật `--enable-preview` ở cả hai bước**. `javac` và `java` là hai tiến trình: flag dùng ở compiler không tự chuyển sang launcher. Nếu compile thành công nhưng chạy thiếu flag, JVM có thể báo `UnsupportedClassVersionError` và từ chối nạp preview class file.

```text
Java source dùng java.lang.foreign của JDK 21
                    │
                    ▼
   javac --enable-preview --release 21
                    │
                    ▼
       .class chứa preview bytecode
                    │
                    ▼
          java --enable-preview
                    │
                    ▼
          FFM program chạy
```

Điểm cần nhớ là: **`--enable-preview` dùng cho preview API, không đồng nghĩa `--enable-native-access` dùng cho restricted native operations**. Hai loại flag sẽ được phân biệt bằng các chương trình đã kiểm thử.

## 2. Ý nghĩa các tùy chọn trên command line

| Flag | Công cụ | Mục đích |
| --- | --- | --- |
| `--enable-preview` | `javac` 21 | Cho phép code dùng preview feature và preview API của chính JDK 21 |
| `--release 21` | `javac` 21 | Biên dịch theo ngôn ngữ và API của release 21 |
| `-source 21` | `javac` 21 | Cách chỉ định source level khác; có thể dùng với preview nhưng `--release` thường phù hợp hơn |
| `-d out` | `javac` | Thư mục đầu ra của bytecode |
| `--enable-preview` | `java` 21 | Cho phép JVM nạp và chạy class sử dụng preview của Java 21 |
| `-cp out` | `java` | Nơi tìm file `.class` |
| `--enable-native-access=ALL-UNNAMED` | `java` 21 | Cấp native access cho code trên classpath khi dùng restricted FFM operations |

`--enable-preview` trên compiler phải dùng với **release hiện tại của javac**. Ví dụ `javac 21 --enable-preview --release 20` **không hợp lệ**: nó không bật preview của Java 20. Muốn học đúng FFM Java 21, dùng `javac 21` và `--release 21`. Kiểm tra:

```bash
javac -version
java -version
```

Hai lệnh nên cùng trả phiên bản **21.x**. Không nên giả định IDE, terminal, Maven, Gradle và CI đều tự động dùng cùng một JDK.

Trong lệnh `java`, đặt `--enable-preview` **trước** tên main class. Nếu đặt sau class, chuỗi đó thường trở thành **program argument** của `main(String[] args)` thay vì VM option. `--release 21` là **tùy chọn biên dịch**, không phải tùy chọn chạy của JVM.

## 3. Ví dụ chạy được số 1: FFM memory, không cần C library

Đây là cách thử flag đơn giản nhất: thao tác memory ngoài heap với `Arena` và `MemorySegment` của JDK 21, không dùng linker hay thư viện native ngoài.

### 3.1. Source: `PreviewMemoryDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class PreviewMemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment number = arena.allocate(ValueLayout.JAVA_INT);
            number.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println("FFM value: " + number.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
```

- `Arena.ofConfined()` tạo arena có vòng đời hữu hạn và quyền sở hữu theo luồng.
- `arena.allocate(ValueLayout.JAVA_INT)` cấp phát memory tương thích layout của `int`.
- `set/get` ghi và đọc giá trị tại byte offset `0`.
- `try-with-resources` đóng arena khi kết thúc block, giúp giải phóng vùng nhớ của arena.

Ví dụ này chỉ dùng **foreign memory access** nên **không cần `--enable-native-access`**. Tuy nhiên các lớp FFM là preview API trong JDK 21, nên **vẫn cần `--enable-preview`**.

### 3.2. Compile và run

Tạo file `PreviewMemoryDemo.java` đúng như phần trên, rồi tại thư mục đó chạy bằng JDK 21:

```bash
mkdir -p out

javac --enable-preview --release 21 \
  -encoding UTF-8 \
  -d out \
  PreviewMemoryDemo.java

java --enable-preview -cp out PreviewMemoryDemo
```

**Stdout thực tế đã kiểm tra bằng OpenJDK 21:**

```text
FFM value: 42
```

`javac` có thể in một số dòng ghi chú `Note: ... uses preview features of Java SE 21` lên stderr. Đây là **thông báo bình thường**, không phải lỗi compile. Muốn thấy cảnh báo chi tiết theo vị trí, có thể dùng `-Xlint:preview`.

**Source-file mode** cũng chạy được trong JDK 21:

```bash
java --enable-preview --source 21 PreviewMemoryDemo.java
```

Lệnh trên biên dịch source trong bộ nhớ và thực thi luôn; stdout vẫn là `FFM value: 42`. Với dự án nhiều class, nên chọn quy trình hai bước hoặc build tool.

## 4. Ví dụ chạy được số 2: gọi hàm C bằng FFM

FFM không chỉ cấp phát memory mà còn cho phép Java tìm native symbol và tạo **downcall** tới hàm C. Khi gọi `strlen` trên **Linux x86-64**, ta cần phân biệt preview permission và native-access permission.

### 4.1. Source: `PreviewStrlenDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class PreviewStrlenDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        MemorySegment symbol = linker.defaultLookup().find("strlen").orElseThrow();

        MethodHandle strlen = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateUtf8String("hello FFM");
            long length = (long) strlen.invokeExact(cString);
            System.out.println("strlen: " + length);
        }
    }
}
```

`Linker.nativeLinker()` lấy linker theo ABI hiện tại, `defaultLookup()` tìm symbol `strlen`, `FunctionDescriptor` mô tả kiểu của native function, còn `downcallHandle` tạo method handle để Java gọi native code.

Trong **Linux 64-bit của ví dụ**, kiểu C `size_t` mà `strlen` trả về rộng 64 bit, phù hợp `ValueLayout.JAVA_LONG`. Trên ABI khác, nhất là 32-bit, phải sửa signature đúng C ABI thay vì giả định `size_t` luôn là `long` Java. `strlen` trả **độ dài byte trước byte NUL**, không phải số Unicode code points. Chuỗi ASCII `hello FFM` dài 9 byte.

### 4.2. Lệnh compile và runtime

```bash
javac --enable-preview --release 21 -d out PreviewStrlenDemo.java

java --enable-preview \
  --enable-native-access=ALL-UNNAMED \
  -cp out PreviewStrlenDemo
```

**Stdout đã kiểm chứng trên OpenJDK 21/Linux x86-64:**

```text
strlen: 9
```

**Vai trò hai flag:**

- `--enable-preview` ở **javac và java** cho phép FFM preview API JDK 21.
- `--enable-native-access=ALL-UNNAMED` ở **java** cho phép các **restricted FFM native operations** đối với code trong unnamed module (classpath), và tránh warning khi tạo downcall.

Nếu chỉ dùng `--enable-preview` mà bỏ native-access flag, JDK 21 có thể **vẫn thực hiện downcall nhưng in cảnh báo** trên stderr, ví dụ:

```text
WARNING: A restricted method in java.lang.foreign.Linker has been called
WARNING: java.lang.foreign.Linker::downcallHandle has been called by the unnamed module
WARNING: Use --enable-native-access=ALL-UNNAMED to avoid a warning for this module
```

Đây là cảnh báo **quyền truy cập native**, không phải lỗi preview. Chính sách restricted native access ở các JDK mới có thể nghiêm ngặt hơn, nên không viết code dựa vào giả định “chỉ có warning”.

Nếu code thuộc **named module**, có thể cấp quyền cho tên module cụ thể, ví dụ `--enable-native-access=com.example.app`, thay vì mở quyền cho mọi code classpath. Không nên bật rộng nếu chỉ một module thật sự cần gọi native.

## 5. Bốn thí nghiệm lỗi thường gặp

### 5.1. Compile không bật preview

```bash
javac --release 21 -d out PreviewMemoryDemo.java
```

**Kết quả:** JDK 21 báo kiểu `Arena is a preview API and is disabled by default`, kèm gợi ý bật `--enable-preview`; `MemorySegment` và `ValueLayout` cũng là preview API. Thêm flag vào **javac** để sửa.

### 5.2. Compile thành công nhưng chạy thiếu flag

```bash
javac --enable-preview --release 21 -d out PreviewMemoryDemo.java
java -cp out PreviewMemoryDemo
```

**Kết quả thực tế trên JDK 21:** `UnsupportedClassVersionError` với thông báo:

```text
Preview features are not enabled for PreviewMemoryDemo
(class file version 65.65535).
Try running with '--enable-preview'
```

`major version 65` tương ứng Java 21 và `minor version 65535` là dấu hiệu preview bytecode. Có thể kiểm tra:

```bash
javap -verbose -classpath out PreviewMemoryDemo
```

Tìm hai dòng `major version: 65` và `minor version: 65535`. Chạy lại bằng `java --enable-preview -cp out PreviewMemoryDemo` trên JDK 21.

### 5.3. Compile preview của release không phải 21 bằng compiler JDK 21

```bash
javac --enable-preview --release 20 PreviewMemoryDemo.java
```

**Kết quả thực tế:** `error: invalid source release 20 with --enable-preview`, giải thích preview chỉ hỗ trợ release hiện tại 21 của compiler. Không thể dùng `--enable-preview` để yêu cầu JDK 21 bật preview của JDK 20.

### 5.4. Nhầm `--enable-native-access` với `--enable-preview`

- `java --enable-native-access=ALL-UNNAMED -cp out PreviewMemoryDemo` **không bật** preview.
- `java --enable-preview -cp out PreviewStrlenDemo` **bật** preview, nhưng có thể cảnh báo restricted call.
- `java --enable-preview --enable-native-access=ALL-UNNAMED -cp out PreviewStrlenDemo` bật **đúng cả hai**.

Nhớ rằng `--enable-native-access` không sửa được lỗi `javac` thiếu preview và cũng không sửa được bytecode chạy trên sai release.

## 6. Phân biệt FFM giữa các JDK

| Java release | Trạng thái của FFM | Lưu ý |
| --- | --- | --- |
| **JDK 17** | API thử nghiệm dưới **incubator module** `jdk.incubator.foreign` | Không thể copy nguyên source/flags của JDK 21 |
| **JDK 19** | First Preview — JEP 424 | FFM preview bước đầu |
| **JDK 20** | Second Preview — JEP 434 | Preview tiếp tục |
| **JDK 21** | **Third Preview — JEP 442** | **Cần `--enable-preview` lúc compile và run** |
| **JDK 22** | **Final — JEP 454** | Không cần `--enable-preview` **chỉ vì dùng FFM** |

Khi chuyển JDK 21 → JDK 22 hoặc mới hơn, **recompile và kiểm tra lại API**: preview APIs và preview bytecode không cam kết tương thích qua phiên bản. FFM ở JDK 22 là API finalized, nhưng các **restricted native operations** vẫn có quy tắc về `--enable-native-access`. Nếu dự án sử dụng preview feature **khác** trong JDK mới, flag `--enable-preview` vẫn có thể cần vì lý do khác.

Không dùng `--add-modules jdk.incubator.foreign` theo hướng dẫn JDK 17 cho source `java.lang.foreign` của JDK 21. Cũng không nhầm `--enable-preview` với `-h` tạo JNI header: ví dụ FFM không cần JNI header để gọi `strlen`.

## 7. Đưa các flag vào Maven, Gradle và IDE

### 7.1. Maven

Fragment `pom.xml` minh họa, giả định có **JDK 21** và plugin versions tương thích (dự án thực tế nên khóa phiên bản plugin để build tái lập):

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>21</release>
        <compilerArgs>
          <arg>--enable-preview</arg>
        </compilerArgs>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>--enable-preview --enable-native-access=ALL-UNNAMED</argLine>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Compiler plugin thêm preview vào **javac**. Surefire thêm preview và native access vào **JVM chạy unit tests**. Khi app chạy ngoài Surefire, launcher/deployment JVM vẫn cần flags riêng. Nếu project dùng JaCoCo hoặc plugin khác sửa `argLine`, phải ghép các options để không làm mất `-javaagent` hiện có. Với demo chỉ thao tác memory, có thể bỏ native-access flag.

### 7.2. Gradle Groovy DSL

Fragment `build.gradle`, giả định đã có Java plugin:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.compilerArgs += ['--enable-preview']
}
tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview', '--enable-native-access=ALL-UNNAMED'
}
tasks.withType(JavaExec).configureEach {
    jvmArgs '--enable-preview', '--enable-native-access=ALL-UNNAMED'
}
```

`JavaCompile` điều khiển compile, `Test` điều khiển test JVM và `JavaExec` điều khiển Java execution task. Khi chạy `java -jar` trực tiếp sau build, phải đưa JVM options vào chính lệnh chạy đó.

### 7.3. IDE, CI/CD

- Chọn **JDK 21** cho Project SDK, compile toolchain và run JVM.
- Bật preview tại **compiler options** và **VM options** của Run/Debug; không đặt `--enable-preview` vào program arguments sau main class.
- Test runner có JVM options riêng; nếu Maven/Gradle test thất bại dù terminal chạy được, kiểm tra task đó.
- Native-downcall code cần thêm native-access VM flag cho module tương ứng, không dùng flag này thay preview.
- In `javac -version` và `java -version` trong log CI để xác nhận JDK thực sự đang chạy.

## 8. An toàn và giới hạn của preview mode

`--enable-preview` **không biến foreign memory thành an toàn tuyệt đối**. FFM có hợp đồng về thời gian sống, luồng và C ABI:

- `Arena.ofConfined()` chỉ nên được truy cập bởi luồng sở hữu; segment không còn hợp lệ sau khi arena đóng.
- `FunctionDescriptor` phải đúng layout và native ABI; sai kiểu return/argument hay pointer lifetime có thể gây crash JVM.
- `--enable-native-access=ALL-UNNAMED` cấp quyền rộng cho mọi code classpath; modular application nên chỉ cấp cho các named modules thực sự cần.
- `strlen` trả độ dài **byte** C string, không giống `String.length()` và không phù hợp để đo số ký tự Unicode tùy ý.
- Cảnh báo restricted FFM method khi không bật native-access trong JDK 21 **không** phải lời hứa hành vi tương tự ở các Java release sau.

## 9. Checklist ngắn và câu hỏi tự luyện

**Checklist trước khi chạy FFM JDK 21:** xác định JDK 21 ở cả `java`/`javac`; compile bằng `--enable-preview --release 21`; run bằng `--enable-preview` trước main class; cấp `--enable-native-access` khi dùng restricted methods; xác nhận classpath và ABI; cấu hình riêng compiler/test/main JVM trong IDE/Maven/Gradle; không dùng preview bytecode JDK 21 như binary portable tới JDK 22+.

**Câu hỏi:**

1. Vì sao `--enable-preview` cần xuất hiện ở cả compile và runtime của JDK 21?
2. `--release 21` dùng cho `javac` hay `java`, và vì sao không dùng `--release 20` với `javac 21 --enable-preview`?
3. Tại sao `PreviewMemoryDemo` không cần native-access flag nhưng `PreviewStrlenDemo` nên có flag này?
4. Khi thiếu runtime preview, lỗi `UnsupportedClassVersionError` của class file `65.65535` muốn nói điều gì?
5. Khi chuyển sang JDK 22, vì sao không cần preview flag **chỉ để dùng FFM**, nhưng vẫn phải xem lại restricted native access?
6. Nếu Maven compile thành công nhưng Surefire test thất bại vì preview, flag còn thiếu ở bước nào?

**Ghi nhớ:** Với **FFM JDK 21**, lệnh đúng là **`javac --enable-preview --release 21`** và **`java --enable-preview`**. `--enable-native-access=...` là một **lựa chọn runtime khác**, dành cho restricted native operations, không thay cho preview. JDK 21 FFM là **Third Preview (JEP 442)**; JDK 22 FFM trở thành **final API (JEP 454)**.

### Tài liệu chính thức

- [Oracle — FFM API, JDK 21](https://docs.oracle.com/en/java/javase/21/core/foreign-function-and-memory-api.html).
- [Oracle — Preview Language and VM Features, JDK 21](https://docs.oracle.com/en/java/javase/21/language/preview-language-and-vm-features.html).
- [Oracle — javac, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [Oracle — java launcher, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [OpenJDK — JEP 442](https://openjdk.org/jeps/442).
- [OpenJDK — JEP 454](https://openjdk.org/jeps/454).
