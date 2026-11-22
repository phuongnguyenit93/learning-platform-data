# Kiểm thử metadata có và không có `-parameters` trong Java Reflection

## 1. Vì sao cần kiểm thử hai kiểu build?

Khi biên dịch Java, tên tham số trong mã nguồn như `firstName` và `repeat` **không bắt buộc** phải tồn tại trong class file ở dạng mà Java Reflection đọc được. Tùy chọn `javac -parameters` yêu cầu compiler lưu tên và modifiers của tham số cho **method và constructor** vào thuộc tính `MethodParameters` trong bytecode. Nếu bỏ tùy chọn này, chương trình vẫn gọi method bình thường và reflection vẫn biết **số lượng, thứ tự, kiểu tham số**; thứ thường không còn là **tên tham số gốc**.

Điều đó có ảnh hưởng tới các framework dùng reflection để map query/path/body parameters, bind constructor arguments, đọc tên tham số trong validation, dependency injection, CLI command mapping hoặc sinh tài liệu API. Một test chỉ chạy với build có `-parameters` có thể che giấu lỗi cấu hình build ở môi trường khác.

**Mục tiêu bài học:** tạo hai artifact từ **cùng source** (một có `-parameters`, một không), đọc bằng `Executable.getParameters()`, xác nhận cả `getName()` và `isNamePresent()`, dùng `javap -v` đối chiếu class file và thiết kế test bắt lỗi phụ thuộc ngầm vào tên tham số.

## 2. Metadata nào được giữ, metadata nào thay đổi?

Xét phương thức Java:

~~~java
// Trích đoạn từ class Sample; không phải chương trình độc lập.
public String greet(String firstName, int repeat) {
    return firstName.repeat(repeat);
}
~~~

Với JDK hỗ trợ tham số chuẩn Java 8+:

| Truy vấn reflection | Có `-parameters` | Không có `-parameters` (class javac thông thường) |
| --- | --- | --- |
| `method.getParameterCount()` | `2` | `2` |
| `method.getParameterTypes()` | `String.class`, `int.class` | Y hệt |
| `method.getParameters()[0].getName()` | `"firstName"` | Tên thay thế thường là `"arg0"` |
| `method.getParameters()[1].getName()` | `"repeat"` | Tên thay thế thường là `"arg1"` |
| `Parameter.isNamePresent()` | `true` | `false` |
| `method.invoke(target, "Hi", 2)` | Chạy theo kiểu và thứ tự đối số | Hoạt động tương tự |
| Annotation/thông tin kiểu có nguồn metadata riêng | Không do `-parameters` quyết định | Không do `-parameters` quyết định |

Điểm quan trọng: **`getName()` luôn có thể trả một String**, kể cả khi tên nguồn không được ghi vào bytecode. Vì vậy:

- `getName() != null` **không chứng minh** có tên tham số thật.
- `getName().equals("arg0")` **không phải** phép xác định metadata vắng mặt: `arg0` cũng có thể là tên do lập trình viên đặt trong source.
- Phép kiểm tra đúng mục đích là `parameter.isNamePresent()` trước khi phụ thuộc vào `parameter.getName()` để bind dữ liệu.

`Executable` là lớp cha chung của `Method` và `Constructor`; cả hai hỗ trợ `getParameters()`. Tùy chọn `-parameters` không chỉ liên quan đến method.

## 3. Thí nghiệm Java 17+: biên dịch hai biến thể từ một source

### 3.1. Cấu trúc thư mục

Tạo một thư mục thử nghiệm mới với hai file mã nguồn và ba thư mục output:

~~~text
parameter-lab/
├── src/
│   ├── demo/
│   │   └── Sample.java
│   └── probe/
│       └── ParameterMetadataProbe.java
├── without/
├── with/
└── probe/
~~~

Hai thư mục `without` và `with` chứa **hai bản khác nhau của cùng class `demo.Sample`**. Thư mục `probe` chứa chương trình đọc metadata. Không cần đặt các file `.class` lên cùng classpath cùng lúc: làm vậy khiến classpath order quyết định bản được load và làm kết quả test khó tin.

**File `src/demo/Sample.java`:**

~~~java
package demo;

public final class Sample {
    private final String label;

    public Sample(String label) {
        this.label = label;
    }

    public String greet(String firstName, int repeat) {
        return firstName.repeat(repeat) + label;
    }
}
~~~

Ở đây có **constructor** với một tham số `label` và **instance method** `greet` với hai tham số `firstName`, `repeat`. Class sử dụng `String.repeat(int)` có từ Java 11; biên dịch target Java 17 sẽ hợp lệ.

**File `src/probe/ParameterMetadataProbe.java`:**

~~~java
package probe;

import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class ParameterMetadataProbe {
    static void inspect(String tag, Executable executable) {
        Parameter[] parameters = executable.getParameters();
        for (int i = 0; i < parameters.length; i++) {
            Parameter p = parameters[i];
            System.out.printf("%s[%d]: name=%s, present=%s, type=%s%n",
                    tag, i, p.getName(), p.isNamePresent(),
                    p.getType().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> sample = Class.forName("demo.Sample");

        Constructor<?> ctor =
                sample.getDeclaredConstructor(String.class);

        Method greet = sample.getDeclaredMethod(
                "greet", String.class, int.class);

        inspect("constructor", ctor);
        inspect("greet", greet);
    }
}
~~~

Chương trình `ParameterMetadataProbe` tìm **đúng một constructor và một method**, rồi in tên, trạng thái metadata tên tham số và kiểu tham số. Cả hai file Java trên là chương trình/lớp biên dịch được, không dựa vào thư viện ngoài JDK.

### 3.2. Biên dịch với và không với `-parameters`

Đứng tại `parameter-lab/`, tạo trước `without`, `with`, `probe` nếu chúng chưa tồn tại. Trên Linux/macOS (bash):

~~~bash
mkdir -p without with probe

# Build A: có debug local variable info (-g) nhưng KHÔNG có -parameters.
javac --release 17 -g -d without src/demo/Sample.java

# Build B: có -parameters nhưng KHÔNG có debug info (-g:none).
javac --release 17 -parameters -g:none -d with src/demo/Sample.java

# Probe được biên dịch độc lập, không cần import demo.Sample.
javac --release 17 -d probe src/probe/ParameterMetadataProbe.java

echo '=== WITHOUT -parameters (with -g) ==='
java -cp probe:without probe.ParameterMetadataProbe

echo '=== WITH -parameters (without -g) ==='
java -cp probe:with probe.ParameterMetadataProbe
~~~

**Trên Windows PowerShell:** tạo thư mục bằng `New-Item -ItemType Directory -Force without,with,probe` (hoặc tạo sẵn trong Explorer); dấu phân tách classpath của Java trên Windows là **dấu chấm phẩy**, nên hai lệnh chạy tương ứng:

~~~powershell
java -cp 'probe;without' probe.ParameterMetadataProbe
java -cp 'probe;with' probe.ParameterMetadataProbe
~~~

Các lệnh `javac --release 17 ...` giống nhau trên Windows và Unix. Không biên dịch `Sample.java` đè vào cùng output directory rồi kiểm tra vì rất dễ chạy nhầm biến thể. Mỗi lệnh `java` tạo một JVM mới, tránh việc `demo.Sample` đã được class loader tải từ biến thể trước.

### 3.3. Output chính xác

Khi chạy hai lệnh `java` như trên:

~~~text
=== WITHOUT -parameters (with -g) ===
constructor[0]: name=arg0, present=false, type=String
greet[0]: name=arg0, present=false, type=String
greet[1]: name=arg1, present=false, type=int
=== WITH -parameters (without -g) ===
constructor[0]: name=label, present=true, type=String
greet[0]: name=firstName, present=true, type=String
greet[1]: name=repeat, present=true, type=int
~~~

Output sử dụng các dòng `echo` để ngăn cách hai run. Nếu chỉ chạy `java`, mỗi run in ba dòng của constructor/method mà không in tiêu đề phân cách.

**Giải thích:** `getDeclaredConstructor(String.class)` và `getDeclaredMethod("greet", String.class, int.class)` tìm được thành viên trong cả hai build. Khác biệt xuất hiện khi `getParameters()` cung cấp `Parameter` và `getName()`/ `isNamePresent()` kiểm tra thông tin tên. Cả hai build giữ nguyên thứ tự và kiểu `String, int`. Đó chính là ranh giới: **metadata về tên khác metadata về signature và invocation**.

## 4. `-parameters` khác `-g` như thế nào?

Hai cờ phục vụ mục đích khác nhau:

| Cờ `javac` | Class file chủ yếu nhận được | Reflection chuẩn quan sát thế nào? |
| --- | --- | --- |
| `-parameters` | Thuộc tính **`MethodParameters`** cho thông tin tham số method/constructor | `Parameter.getName()`, `isNamePresent()`, và một số metadata modifiers |
| `-g` | Thông tin debug gồm line number, source file, local variables | **Không tự tạo** tên thật cho `Parameter.getName()` |
| `-g:none` | Không tạo debug information thông thường | **Không xóa `MethodParameters`** nếu build có `-parameters` |
| Không chỉ định `-parameters` | `javac` thông thường không lưu tên tham số nguồn qua `MethodParameters` | Tên giả định `arg0`, `arg1`, ... và `isNamePresent() == false` trong ví dụ |

Thông tin debug `LocalVariableTable`, khi có, nằm trong thuộc tính của `Code` và phục vụ công cụ debug/bytecode. Nó **không phải** cùng thuộc tính với `MethodParameters`; core reflection **không dùng LocalVariableTable như đường fallback công khai** để khôi phục tên tham số cho `Parameter.getName()`. Một thư viện ngoài có thể chủ động đọc debug bytecode để khôi phục thông tin trong vài trường hợp, nhưng không được đồng nhất hành vi đó với core Java Reflection.

**Thí nghiệm cố ý kiểm soát hai biến:**

- Build **without**: `-g` có debug info, **không có `-parameters`** → `isNamePresent() = false`.
- Build **with**: `-parameters -g:none` **không có debug info**, nhưng có `MethodParameters` → `isNamePresent() = true`.

Như vậy, kết quả kiểm thử không thể bị giải thích nhầm rằng tên tham số đến từ cờ debug.

### 4.1. Kiểm tra trực tiếp bytecode với javap

Chạy:

~~~bash
javap -v -p -classpath without demo.Sample
javap -v -p -classpath with demo.Sample
~~~

Trong output của bản **with**, tìm thuộc tính dạng:

~~~text
MethodParameters:
  Name                           Flags
  firstName
  repeat
~~~

Đây là **trích đoạn minh họa từ phần method greet** (cách căn cột của `javap` có thể khác theo JDK), không phải toàn bộ output của chương trình. Constructor cũng có một `MethodParameters` chứa `label`.

Bản **without** có thể có `LocalVariableTable` vì được build với `-g`, nhưng **không có khối `MethodParameters` cho các method tương ứng**. Với bản **with**, có `MethodParameters` dù biên dịch `-g:none`. Có thể dùng `javap -l` để xem line/local-variable debug info riêng.

**Lưu ý:** `javap` hiển thị cả constant pool và nhiều thuộc tính; đừng chỉ search một chuỗi `firstName` trong toàn output rồi kết luận tên parameter đã sẵn cho reflection. Hãy kiểm tra **đúng thuộc tính `MethodParameters`** của method/constructor tương ứng.

## 5. Viết test tự động để phát hiện build thiếu metadata

Thay vì chỉ nhìn stdout, hãy thêm assert vào test chuyên biệt cho **artifact thật sự dùng khi deploy**. Ví dụ utility JUnit không được dùng ở đây để tránh phải thêm dependency; sau đây là một class Java 17 độc lập có `main` và assert bằng `AssertionError`:

**File `src/probe/ParameterMetadataAssertions.java`:**

~~~java
package probe;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;

public final class ParameterMetadataAssertions {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("demo.Sample");
        Method method =
                type.getDeclaredMethod("greet", String.class, int.class);

        Parameter[] params = method.getParameters();

        if (params.length != 2) {
            throw new AssertionError("Unexpected parameter count");
        }

        String[] sourceNames = {"firstName", "repeat"};

        for (int i = 0; i < params.length; i++) {
            if (!params[i].isNamePresent()) {
                throw new AssertionError(
                        "Missing -parameters at index " + i);
            }
            if (!sourceNames[i].equals(params[i].getName())) {
                throw new AssertionError(
                        "Unexpected parameter name at index " + i);
            }
        }

        System.out.println("parameter metadata present: "
                + Arrays.toString(sourceNames));
    }
}
~~~

Biên dịch class kiểm tra này vào `probe` (vẫn cùng thư mục project):

~~~bash
javac --release 17 -d probe src/probe/ParameterMetadataAssertions.java
java -cp probe:with probe.ParameterMetadataAssertions
~~~

Lệnh cuối dự kiến in:

~~~text
parameter metadata present: [firstName, repeat]
~~~

Nếu thay `with` bằng `without`, chương trình phải **thất bại** bằng `AssertionError` với thông báo chứa `Missing -parameters at index 0`. Không nên ghi cả stack trace vào golden output vì số dòng/source line thay đổi khi chỉnh mã.

Với dự án thật, hãy kiểm tra **JAR hoặc class output do pipeline CI/deploy tạo**, không chỉ một bản bạn biên dịch thủ công. Test có thể chạy ở CI để chặn lỗi cờ biên dịch bị mất khi cập nhật Maven/Gradle/IDE.

### 5.1. Tại sao cần kiểm tra cả tên và `isNamePresent()`?

Test chỉ so `getName()` với `"firstName"` có thể bắt lỗi trong ví dụ này, nhưng không phân biệt tốt các trường hợp tên `arg0` là tên nguồn thực tế. Test chỉ so `isNamePresent()` cũng chưa bảo đảm tên mong muốn được giữ sau refactor. Vì vậy:

1. Nếu yêu cầu “có tên nguồn”, assert `isNamePresent()`.
2. Nếu contract binding bắt buộc tên cụ thể, assert thêm `getName()` có giá trị đã định.
3. Nếu thực tế chỉ cần signature/annotation định danh rõ, **không nên** đặt thêm dependency không cần thiết vào tên tham số nguồn.

### 5.2. Ma trận test thiết thực

| Ca kiểm thử | Điều cần xác minh | Ý nghĩa |
| --- | --- | --- |
| Build thiếu `-parameters` | `isNamePresent() == false` trong class javac thông thường | Hiểu hành vi degrade/fail rõ ràng |
| Build có `-parameters` | `true` và tên như source | Pipeline lưu đúng metadata |
| `-g` nhưng thiếu `-parameters` | Core reflection vẫn không đọc được tên nguồn | Không nhầm debug info với MethodParameters |
| `-parameters -g:none` | Tên vẫn đọc được | Độc lập với debug info |
| Constructor | `Constructor.getParameters()` tương tự method | Framework constructor injection/binding hoạt động |
| Method overload | Lookup đúng bằng cả tên + danh sách `Class<?>[]` | Không kiểm nhầm overload |
| Artifact đóng gói cuối | Kiểm tra class trong JAR/container thực | Không bị lệch giữa IDE, test và production |
| Class do tool sinh | Kiểm tra `isImplicit()`, `isSynthetic()`, names | Không suy luận tên tham số nguồn cho tham số ẩn/sinh |

## 6. Cấu hình project và nguồn phát sinh khác biệt

### 6.1. Maven

Với dự án Maven dùng `maven-compiler-plugin`, có thể cấu hình thuộc tính compiler parameters:

~~~xml
<!-- Trích đoạn trong pom.xml, không phải một pom.xml độc lập. -->
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Hoặc cấu hình plugin cụ thể:

~~~xml
<!-- Trích đoạn cấu hình bên trong <plugins>, không phải pom.xml độc lập. -->
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <parameters>true</parameters>
  </configuration>
</plugin>
~~~

Phiên bản plugin/JDK và các profile build cần được đồng bộ trong dự án. Sau khi thay cờ, thực hiện **clean compilation** và kiểm thử artifact thực, vì file `.class` cũ có thể còn trong thư mục output.

### 6.2. Gradle

Với Gradle Java plugin, cấu hình tasks kiểu `JavaCompile` trong **Groovy DSL**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Đây là một đoạn cấu hình trong `build.gradle`, không phải file Java chạy được. Trong multi-module build, kiểm tra module thực sự tạo các class cần reflection, kể cả module chứa DTO hoặc constructor được framework sử dụng. Với build Kotlin/Scala hoặc code generator, cờ của `javac` không đủ để suy ra metadata của các class do compiler khác tạo; kiểm tra **class file cuối** mới là bằng chứng.

### 6.3. IDE, annotation processor, generator và tối ưu bytecode

- Compile trong IDE có thể dùng cấu hình khác với CI, kể cả khi cùng source.
- Annotation processor/code generator tạo class riêng; cách compiler/generator ghi `MethodParameters` cần được xác minh riêng.
- Obfuscator/shrinker/bytecode transformer có thể thay hoặc loại bỏ thông tin tên; thêm `-parameters` lúc javac chưa đủ nếu pipeline sau đó biến đổi class file.
- Constructor của **inner class, enum, record** và method **synthetic/bridge** có thể có tham số compiler tạo ra hoặc quy tắc metadata riêng. Không áp dụng máy móc kết luận `arg0`/tên nguồn từ fixture đơn giản cho mọi thành viên; kiểm tra `Parameter.isImplicit()`, `isSynthetic()`, `getModifiers()`, và method `isSynthetic()`/`isBridge()` khi có liên quan.

## 7. Các giới hạn của tên tham số trong runtime

### 7.1. `-parameters` không bảo đảm API binding luôn đúng

Tên tham số có thể bị đổi khi refactor source trong khi signature JVM vẫn giống hệt. Nếu ứng dụng dựa vào tên `firstName` để bind request field, việc đổi thành `name` mà không cập nhật contract có thể làm hỏng API ở runtime dù Java compile thành công.

Một số framework hỗ trợ annotation ghi tên tường minh (ví dụ annotation của framework định nghĩa tên path/query field). Khi hệ thống yêu cầu API contract ổn định, **tên explicit đã được review** thường bền hơn suy đoán tên nguồn. Nhưng đừng tự giả định framework luôn bỏ qua `-parameters` khi có annotation: đọc contract của phiên bản framework đang dùng.

### 7.2. Method có annotation và generics

- `Method.getParameterAnnotations()` và `Parameter.getAnnotations()` dựa trên metadata annotation, **không phải chỉ dựa vào `MethodParameters`**.
- `Executable.getGenericParameterTypes()` dựa vào generic Signature metadata (nếu có) và có thể bị chi phối bởi type erasure và quá trình phân giải Type riêng.
- `getParameterTypes()` đọc kiểu tham số runtime từ method descriptor, nên vẫn biết `String, int` dù tên nguồn không hiện diện.
- Tên biến cục bộ bên trong thân method không được bổ sung bởi `-parameters`: nó không phải tùy chọn “giữ tất cả tên biến” cho reflection.

### 7.3. Trường hợp dữ liệu metadata không hợp lệ

`Executable.getParameters()` có thể ném `java.lang.reflect.MalformedParametersException` khi thuộc tính `MethodParameters` trong class file không hợp lệ. Trường hợp này khác với **không có** tên tham số: với class javac thông thường không có `-parameters`, reflection tạo tên giả định và đặt `isNamePresent() = false`, chứ không coi việc thiếu thuộc tính là bytecode hỏng.

Trên hệ thống có plugin hoặc class do công cụ ngoài sinh ra, phân biệt:

1. **Không có MethodParameters:** thông thường trả tên giả định; nghiệp vụ cần tên thật phải từ chối hoặc có fallback tường minh.
2. **Có MethodParameters hợp lệ:** kiểm tra tên/thứ tự/kind theo yêu cầu.
3. **MethodParameters hỏng:** xử lý như lỗi artifact/build pipeline; không cố sửa bằng việc đoán tên từ `arg0`.

## 8. Checklist kiểm thử và lỗi thường gặp

**Checklist cho test hoặc CI:**

1. Lấy **cùng một source**; build ra hai thư mục/JAR hoàn toàn riêng.
2. Tạo build A có `-g` nhưng **không có `-parameters`**, build B có `-parameters -g:none`.
3. Không đưa cả hai bản của **cùng fully-qualified class name** vào một classpath ở cùng JVM; dùng hai lần chạy hoặc class loader cách ly có kiểm soát.
4. Đọc ít nhất một method và một constructor với `getParameters()`.
5. Assert **`isNamePresent()` và `getName()`**; vẫn kiểm tra `getParameterTypes()` và `getParameterCount()` để thấy signature không bị mất.
6. Xem `javap -v -p`: so sánh đúng `MethodParameters` với debug `LocalVariableTable`.
7. Trên CI, test artifact cuối cùng với flags/plugin và JDK version dùng ở deploy; sau khi thay flags thì clean build.
8. Với framework binding, test cả request theo tên contract và case thiếu metadata, thay vì chỉ kiểm tra một method mẫu.
9. Tránh dựa vào tên fake `arg0` như API contract; đối với record/inner/synthetic constructors cần kiểm tra hành vi riêng.
10. Khi thay đổi tên tham số, test hồi quy contract dữ liệu và documentation, không chỉ test compile.

**Tự kiểm tra:**

- Vì sao `-g` không đủ để `Parameter.isNamePresent()` trả true?
- Vì sao `Parameter.getName()` có kết quả `arg0` không chứng minh tên này có trong source?
- Tại sao hai class `demo.Sample` giống tên nhưng khác flag biên dịch không nên nằm chung một classpath để chạy test?
- Điều gì khác nhau giữa `LocalVariableTable` và `MethodParameters`?
- Vì sao một framework bind theo tên có thể hỏng sau khi đổi tên tham số mà chữ ký method vẫn không đổi?
- Nếu thấy `MalformedParametersException`, cần điều tra điều gì thay vì chỉ thêm `-parameters`?

### Tài liệu tham khảo

- Oracle JDK 21 — `javac` options, `-parameters`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 — `Parameter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html
- Oracle Java SE 21 — `Executable`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html
- Oracle Java SE 21 — `MalformedParametersException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/MalformedParametersException.html
- JVM Specification Java SE 21 — MethodParameters: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.24