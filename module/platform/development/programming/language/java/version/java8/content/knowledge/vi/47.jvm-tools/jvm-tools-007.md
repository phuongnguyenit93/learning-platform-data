# javac -parameters và kiểm chứng metadata trên class file

## 1. Mục tiêu: giữ tên tham số để Java Reflection đọc được

Trong mã nguồn Java, một method có thể khai báo tham số với tên có ý nghĩa:

```java
public static String greet(String customerName, int retryCount) {
    return customerName + ":" + retryCount;
}
```

Tên `customerName` và `retryCount` hiển thị rõ ý nghĩa khi đọc source. Nhưng khi compile, JVM chủ yếu định danh method bằng tên method và **descriptor** chứa kiểu tham số/kiểu trả về. Tên tham số nguồn không tự động trở thành dữ liệu reflection trong mọi file `.class`.

Từ Java 8, `javac` có tùy chọn **`-parameters`** để ghi tên tham số hình thức vào metadata của class file. Khi class được biên dịch với tùy chọn này, Java Reflection có thể đọc lại tên thông qua `Executable.getParameters()` và `Parameter.getName()`.

Ví dụ:

```java
Method method = Service.class.getDeclaredMethod(
    "greet", String.class, int.class);

for (Parameter parameter : method.getParameters()) {
    System.out.println(parameter.getName()
        + " | present=" + parameter.isNamePresent());
}
```

Khi metadata có tên, kết quả có thể là `customerName | present=true` và `retryCount | present=true`. Nếu metadata không có tên, `getName()` thường trả tên tổng hợp như `arg0`, `arg1` và `isNamePresent()` trả `false`.

**Điểm cốt lõi:** `-parameters` ghi metadata về **formal method/constructor parameters** để reflection sử dụng. Nó không ghi toàn bộ tên biến local, không thay đổi chữ ký JVM và không tự bật một cơ chế logging hay framework nào.

## 2. Vì sao tên trong source có thể không còn trong class file?

Một khai báo Java:

```java
public void transfer(String sourceAccount, String targetAccount,
                     long amount) {
    // ...
}
```

được biên dịch thành method có tên, descriptor và bytecode. Descriptor chứa các kiểu tham số theo thứ tự, chẳng hạn:

```text
(Ljava/lang/String;Ljava/lang/String;J)V
```

Descriptor cho biết method nhận hai `String` và một `long`, trả về `void`. **Tên `sourceAccount`, `targetAccount` và `amount` không nằm trong descriptor này.**

Tên tham số có thể được ghi ở một class-file attribute riêng tên **`MethodParameters`**. Đây là metadata của method, được thêm vào định dạng class file từ Java 8. Tùy chọn `javac -parameters` yêu cầu compiler ghi thông tin tên tham số để reflection có thể truy vấn.

Có thể hình dung cấu trúc:

```text
Source code
  transfer(String sourceAccount, String targetAccount, long amount)
             |                  |                    |
             +------------------+--------------------+
                                |
                         javac -parameters
                                |
                                v
Class file (.class)
  Method descriptor: (String, String, long) -> void
  MethodParameters:
    sourceAccount
    targetAccount
    amount
                                |
                                v
Java Reflection
  Parameter.getName()
  Parameter.isNamePresent()
```

Nếu không có metadata tên, JVM vẫn gọi method bình thường. Method descriptor và bytecode vẫn đủ để thực thi; phần bị thiếu chỉ là thông tin tên để reflection đọc.

## 3. `-parameters` và `MethodParameters` attribute

### 3.1. Tùy chọn compiler

Cú pháp cơ bản:

```bash
javac -parameters MyClass.java
```

Tùy chọn `-parameters` yêu cầu `javac` tạo metadata cho reflection về các tham số của method/constructor trong các class được biên dịch. Đây là tùy chọn của Java compiler, có từ Java 8 và vẫn dùng được với JDK hiện hành.

Có thể kết hợp với output directory và encoding:

```bash
javac -parameters -encoding UTF-8 -d out src/com/example/Service.java
```

Tên tham số được ghi trong class file do lần biên dịch này tạo ra. Nếu class đã được compile từ trước mà thiếu metadata, chỉ chạy ứng dụng với JVM mới hơn hoặc compile riêng class gọi reflection sẽ **không bổ sung tên** vào class file cũ.

### 3.2. Attribute được ghi

Trong class file, tên tham số được lưu trong attribute `MethodParameters` gắn với method hoặc constructor. Công cụ `javap -v` có thể hiển thị attribute này.

Ví dụ rút gọn:

```text
public static java.lang.String greet(java.lang.String, int);
  descriptor: (Ljava/lang/String;I)Ljava/lang/String;
  flags: ACC_PUBLIC, ACC_STATIC
  MethodParameters:
    Name
    customerName
    retryCount
```

Bảng `MethodParameters` liệt kê tên theo thứ tự tham số của executable. Class-file format còn có cờ cho tham số như `final`, `synthetic` hoặc `mandated` khi áp dụng; reflection cung cấp API để xem các đặc tính tương ứng.

### 3.3. Chỉ tên parameter được ghi, không đổi tên method

`-parameters` không đổi:

- Tên method hoặc constructor.
- Thứ tự và kiểu tham số.
- Kiểu trả về.
- Quy tắc overload resolution.
- Bytecode thực thi method.
- Cách gọi method từ Java hoặc bytecode khác.

Nó bổ sung metadata để công cụ runtime có thể quan sát tên tham số. Vì vậy, một class có thể có descriptor giống hệt class trước đó nhưng reflection cho kết quả khác khi class mới được compile với `-parameters`.

## 4. `MethodParameters` khác debug information như thế nào?

Đây là chỗ dễ nhầm nhất. `javac` có nhiều tùy chọn liên quan tới thông tin debug:

- `-g`: sinh debugging information.
- `-g:lines`: thông tin số dòng.
- `-g:vars`: thông tin biến local.
- `-g:source`: thông tin tên source file.
- `-g:none`: không sinh debugging information.
- `-parameters`: sinh metadata tên tham số cho reflection.

Tên tham số trong `MethodParameters` **khác** tên biến trong `LocalVariableTable`. `LocalVariableTable` là debug attribute dùng để ánh xạ slot local variable sang tên và phạm vi bytecode; Java Reflection `Parameter.isNamePresent()` không dùng bảng local variable đó làm nguồn tên chính thức.

### 4.1. Có `-g` không có nghĩa `isNamePresent()` sẽ true

Một class có thể chứa debug information nhưng không có `MethodParameters`. Tùy compiler và công cụ build, `LocalVariableTable` có thể chứa một số tên tham số trong phạm vi method, nhưng đó không thay thế metadata được truy vấn qua API `Parameter`.

Nếu framework cần tên tham số qua Java Reflection, hãy compile class khai báo method bằng `-parameters` thay vì chỉ bật debug symbols.

### 4.2. `-g:none` vẫn có thể giữ `MethodParameters`

Hai tùy chọn điều khiển hai nhóm metadata khác nhau. Lệnh:

```bash
javac --release 8 -parameters -g:none -d out src/Service.java
```

vẫn có thể ghi `MethodParameters` trong khi loại bỏ debug information. Đây là một cách kiểm chứng rõ rằng reflection đọc tên từ metadata tham số chứ không dựa vào `LocalVariableTable`.

### 4.3. Khi nào cần debug information?

Debug symbols hữu ích cho debugger, stack trace mapping, profiler và công cụ phân tích. `-parameters` hữu ích cho reflection, dependency injection, argument binding và framework cần tên formal parameter.

Một project có thể cần cả hai:

```bash
javac -parameters -g -d out src/Service.java
```

Hoặc chỉ cần metadata tham số mà không cần đầy đủ debug symbols:

```bash
javac -parameters -g:none -d out src/Service.java
```

Lựa chọn phụ thuộc yêu cầu runtime/debugging và chính sách build của ứng dụng.

## 5. Java Reflection: `Executable.getParameters()`

Từ Java 8, `java.lang.reflect.Executable` là lớp cơ sở chung của `Method` và `Constructor`. Nó cung cấp:

```java
Parameter[] getParameters()
```

Mỗi phần tử `Parameter` đại diện một formal parameter của method hoặc constructor. API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `Executable.getParameters()` | Lấy mảng Parameter theo thứ tự khai báo |
| `Parameter.getName()` | Lấy tên được ghi trong class file, hoặc tên tổng hợp như arg0 |
| `Parameter.isNamePresent()` | Kiểm tra tên có thực sự được ghi trong metadata hay không |
| `Parameter.getType()` | Lấy kiểu raw của tham số |
| `Parameter.getParameterizedType()` | Lấy kiểu generic nếu có |
| `Parameter.getModifiers()` | Lấy modifier của tham số |
| `Parameter.isImplicit()` | Kiểm tra tham số implicit/mandated |
| `Parameter.isSynthetic()` | Kiểm tra tham số synthetic |
| `Parameter.getAnnotations()` | Lấy annotation runtime-visible trên tham số |

Các API trên có từ Java 8. Không cần thư viện ngoài để đọc tên tham số.

### 5.1. Luôn kiểm tra `isNamePresent()` trước khi tin tên

```java
for (Parameter parameter : method.getParameters()) {
    if (parameter.isNamePresent()) {
        System.out.println("Declared name: " + parameter.getName());
    } else {
        System.out.println("Name metadata is absent");
    }
}
```

Không dùng `getName()` đơn lẻ rồi mặc định giá trị trả về là tên trong source. Nếu metadata không có, chuỗi `arg0` có thể chỉ là tên tổng hợp do reflection cung cấp theo vị trí.

### 5.2. Tên parameter không phải key để tìm method

`Class.getDeclaredMethod` tìm method theo tên method và các kiểu tham số:

```java
Method method = Service.class.getDeclaredMethod(
    "transfer", String.class, String.class, long.class);
```

Không truyền tên tham số vào `getDeclaredMethod`. Tên tham số chỉ có thể được đọc **sau khi đã tìm được executable**.

### 5.3. Dùng cho constructor

`Executable` bao gồm cả `Constructor`:

```java
Constructor<?> constructor =
    User.class.getDeclaredConstructor(String.class, int.class);

for (Parameter parameter : constructor.getParameters()) {
    System.out.println(parameter.getName()
        + ": " + parameter.isNamePresent());
}
```

Constructor cũng cần được compile với `-parameters` để tên khai báo có mặt trong metadata. Tùy loại class/constructor, có thể có thêm tham số implicit hoặc synthetic; framework nên kiểm tra các cờ thay vì mặc định mọi tham số đều là tham số nghiệp vụ được khai báo trực tiếp.

## 6. Ví dụ reflection hoàn chỉnh

Tạo file `ParameterMetadataDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterMetadataDemo {
    public static String greet(String customerName, int retryCount) {
        return customerName + ":" + retryCount;
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterMetadataDemo.class.getDeclaredMethod(
            "greet", String.class, int.class);

        for (Parameter parameter : method.getParameters()) {
            System.out.println(parameter.getName()
                + " | present=" + parameter.isNamePresent());
        }
    }
}
```

Chương trình không phụ thuộc framework, database hoặc file ngoài. Nó chỉ đọc metadata của method trong chính class được compile.

### 6.1. Compile có `-parameters`

```bash
javac --release 8 -parameters -g:none -encoding UTF-8 \
    -d out/with-parameters ParameterMetadataDemo.java

java -cp out/with-parameters ParameterMetadataDemo
```

Kết quả:

```text
customerName | present=true
retryCount | present=true
```

Tên reflection trùng với tên trong source vì compiler đã ghi metadata.

### 6.2. Compile không có `-parameters`

```bash
javac --release 8 -g:none -encoding UTF-8 \
    -d out/without-parameters ParameterMetadataDemo.java

java -cp out/without-parameters ParameterMetadataDemo
```

Kết quả:

```text
arg0 | present=false
arg1 | present=false
```

Method vẫn compile và chạy bình thường. Chỉ có tên tham số thật không được reflection đọc từ metadata.

### 6.3. Vì sao dùng hai thư mục output?

Không compile hai lần vào cùng một thư mục rồi để class file sau ghi đè class file trước. Hai output directory giúp giữ hai artifact độc lập để so sánh:

```text
out/
  with-parameters/
    ParameterMetadataDemo.class
  without-parameters/
    ParameterMetadataDemo.class
```

Khi chạy, `-cp` chọn đúng bản class muốn kiểm tra. Điều này tránh kết luận sai do classpath vô tình lấy class cũ.

## 7. Kiểm chứng trực tiếp bằng `javap -v -p`

Reflection xác nhận hành vi ở runtime. `javap` xác nhận metadata thực sự có trong bytecode.

### 7.1. Lệnh xem class file

```bash
javap -v -p -classpath out/with-parameters ParameterMetadataDemo
```

- `-v`: hiển thị thông tin verbose, bao gồm attributes.
- `-p`: hiển thị tất cả class members, kể cả private.
- `-classpath`: chỉ định nơi tìm class.
- `ParameterMetadataDemo`: tên class cần kiểm tra.

Trong output, tìm method `greet` và phần:

```text
public static java.lang.String greet(java.lang.String, int);
  descriptor: (Ljava/lang/String;I)Ljava/lang/String;
  flags: ACC_PUBLIC, ACC_STATIC
  MethodParameters:
    Name
    customerName
    retryCount
```

Tên hiển thị trong `MethodParameters` là bằng chứng compiler đã ghi tên tham số.

### 7.2. Kiểm tra bản compile không có flag

Chạy:

```bash
javap -v -p -classpath out/without-parameters ParameterMetadataDemo
```

Ở bản không có `-parameters`, method `greet` thường không có `MethodParameters` chứa các tên nguồn. Nếu compiler khác hoặc class được tạo bởi tool khác, hãy xem output thực tế thay vì chỉ giả định attribute luôn vắng mặt.

### 7.3. Kiểm tra riêng `MethodParameters` và `LocalVariableTable`

Với class compile bằng:

```bash
javac -parameters -g:none -d out/with-parameters ParameterMetadataDemo.java
```

`javap -v` vẫn hiển thị `MethodParameters` nhưng không có debug `LocalVariableTable` do `-g:none`. Đây là phép kiểm chứng tách biệt hai cơ chế.

Nếu compile với `-g:vars`, `javap -v` hoặc `javap -l` có thể hiển thị local variable debug information. Đừng nhầm attribute đó với `MethodParameters`.

### 7.4. Kiểm tra class nằm trong JAR

Có thể kiểm tra class trực tiếp từ JAR:

```bash
javap -v -p -classpath application.jar com.example.Service
```

Đảm bảo JAR là artifact thực sự được deploy. Nếu chỉ kiểm tra thư mục build nhưng package cuối cùng đã được shade, obfuscate, instrument hoặc transform, metadata trong artifact cuối có thể khác.

## 8. Class-file version và Java 8 compatibility

Java 8 sử dụng class-file major version **52**. Khi compile bằng JDK mới hơn với:

```bash
javac --release 8 -parameters -d out src/Service.java
```

compiler tạo bytecode tương thích Java 8, đồng thời ghi metadata tham số. `javap -v` hiển thị major version để xác minh target class file.

Cần phân biệt:

- `-parameters`: yêu cầu ghi tên tham số.
- `--release 8`: giới hạn platform APIs và target class-file version theo Java 8 khi dùng JDK 9+.
- `-source 8`/`-target 8`: cấu hình source/target cũ hơn, không cung cấp đầy đủ kiểm tra API platform như `--release`.
- `-g`/`-g:none`: điều khiển debug information.

### 8.1. Trên JDK 8 không có cờ `--release`

`--release` được thêm ở JDK 9. Nếu đang chạy trực tiếp JDK 8, dùng:

```bash
javac -parameters -encoding UTF-8 -d out src/Service.java
```

Không đưa `--release 8` vào lệnh chạy trên chính JDK 8; compiler sẽ báo tùy chọn không nhận diện. Tùy chọn `-parameters` có sẵn từ Java 8.

### 8.2. Compile bằng JDK mới nhưng runtime Java 8

Có thể compile bằng JDK mới với `--release 8` rồi chạy class trên Java 8, miễn source chỉ dùng APIs có trong Java 8 và không có bước bytecode transformation làm đổi artifact. Hãy xác minh class major version và thử trên runtime tối thiểu được hỗ trợ.

## 9. Cấu hình Maven

Nếu project dùng Maven Compiler Plugin, bật `parameters` trong cấu hình plugin. Ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>8</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

`parameters` yêu cầu compiler ghi tên tham số. `release` chọn API/bytecode Java 8 khi Maven chạy bằng JDK 9 trở lên. Hãy chọn phiên bản Maven Compiler Plugin còn được duy trì và phù hợp với Maven/JDK của project.

Nếu build bằng JDK 8, cấu hình source/target thay cho release:

```xml
<configuration>
    <source>1.8</source>
    <target>1.8</target>
    <parameters>true</parameters>
</configuration>
```

Cấu hình thực tế có thể đặt trong parent POM hoặc plugin management. Điều quan trọng là cấu hình phải áp dụng cho module chứa class cần reflection, không chỉ module ứng dụng gọi nó.

### 9.1. Kiểm tra effective configuration

Một property trong POM chưa chắc đã được áp dụng nếu profile, parent POM hoặc plugin configuration ghi đè. Hãy kiểm tra effective POM và log compile của module:

```bash
mvn help:effective-pom
mvn -pl service-module -am clean package
```

Sau đó dùng `javap` trên class trong output hoặc JAR của module. Compile thành công không tự chứng minh `MethodParameters` đã có.

## 10. Cấu hình Gradle

Với Gradle Groovy DSL, có thể thêm compiler argument vào các task Java compile:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Đặt cấu hình ở build script phù hợp để áp dụng cho các source set/module cần metadata. Nếu chỉ bật ở task `compileJava` của một module, những module khác có thể vẫn compile thiếu tên tham số.

### 10.1. Kiểm tra task thực tế

Xem task compile của module cần kiểm tra:

```bash
./gradlew :service:clean :service:compileJava --info
```

Sau đó tìm class trong `build/classes` và chạy `javap -v -p`. Nếu project dùng toolchain, annotation processor hoặc task custom, xác nhận compiler thực tế là compiler đã nhận `-parameters`.

### 10.2. Không dựa vào cấu hình IDE riêng lẻ

IDE có thể compile để chạy/debug với cấu hình khác build CI. Nếu local reflection đọc được tên nhưng artifact CI không có, hãy so sánh compiler arguments và class file của hai đường build. Cấu hình cần được lưu trong build script/version control để tái lập.

## 11. Build nhiều module và thư viện dependency

`-parameters` phải được áp dụng cho **class khai báo method/constructor** mà runtime muốn introspect.

Ví dụ:

- `api-model.jar` chứa `User(String displayName)`.
- `application.jar` dùng reflection đọc constructor của `User`.

Nếu chỉ compile `application.jar` với `-parameters` nhưng `api-model.jar` đã build từ trước không có metadata, reflection vẫn không lấy được `displayName` từ class cũ. Cần build lại module chứa `User` và phát hành artifact có metadata.

### 11.1. Dependency bên thứ ba

Không thể thêm tên tham số vào một dependency đã compile chỉ bằng cách truyền `-parameters` cho project hiện tại. Hãy kiểm tra JAR dependency bằng `javap`. Nếu thiếu, các lựa chọn phụ thuộc quyền kiểm soát thư viện: nâng cấp bản có metadata, yêu cầu vendor cung cấp artifact phù hợp, dùng annotation/cấu hình explicit hoặc tránh phụ thuộc vào tên reflection.

Không tự suy đoán tên từ thứ tự tham số nếu framework cần contract ổn định.

### 11.2. Kiểm tra tất cả module có executable cần introspection

Trong multi-module build, lập danh sách các module chứa:

- Constructor dùng cho binding/injection.
- Method endpoint hoặc handler được framework introspect.
- DTO/record-like class được framework tạo object bằng reflection.
- Library public API mà consumer dựa vào tên tham số.

Bật flag cho đúng các module đó và xác minh artifact sau cùng. Không cần bật tùy tiện cho mọi dependency ngoài quyền kiểm soát.

## 12. Framework có thể dùng parameter names như thế nào?

Khi tên tham số có mặt, framework có thể dùng chúng cho các tính năng reflection-based:

- Bind tên query/path/request parameters vào method arguments.
- Tạo constructor argument mapping.
- Đặt tên tham số trong dependency injection hoặc expression binding.
- Hiển thị thông tin method trong diagnostics, tracing hoặc schema generation.
- Liên kết annotation metadata với từng tham số.

Hành vi cụ thể phụ thuộc framework, phiên bản, annotation và cấu hình. Không phải mọi framework đều tự động dùng parameter names; nhiều framework yêu cầu annotation tường minh hoặc fallback khác.

### 12.1. Tên tham số có thể trở thành contract runtime

Trước khi bật `-parameters`, một framework có thể yêu cầu annotation như `@RequestParam("customerId")`. Sau khi có metadata, framework có thể hỗ trợ suy ra tên nếu annotation không chỉ rõ giá trị. Khi đó, đổi tên parameter trong source có thể thay đổi hành vi binding dù JVM descriptor không đổi.

Với API công khai, nếu tên có ý nghĩa contract, cân nhắc khai báo rõ qua annotation/schema thay vì phụ thuộc ngầm vào tên source.

### 12.2. Annotation trên parameter là metadata khác

`-parameters` không tự thêm annotation. Parameter annotations được ghi qua các class-file attributes riêng và phụ thuộc retention/target của annotation. Có thể đọc chúng qua `Parameter.getAnnotations()`; việc bật tên không thay đổi quy tắc retention.

### 12.3. Không phải mọi parameter đều là tham số nghiệp vụ

Constructor/compiler có thể có tham số implicit, mandated hoặc synthetic trong một số cấu trúc ngôn ngữ. Framework tổng quát nên kiểm tra `Parameter.isImplicit()`, `Parameter.isSynthetic()`, modifier và metadata liên quan trước khi coi từng phần tử là input do caller khai báo trực tiếp.

## 13. Tham số, local variable, field và generic type

| Khái niệm | Ví dụ | Cách lấy thông tin |
| --- | --- | --- |
| Method parameter | `find(String customerId)` | `Executable.getParameters()` |
| Constructor parameter | `User(String displayName)` | `Constructor.getParameters()` |
| Local variable | `String normalized = ...` | Debug info/tooling; không phải Parameter API |
| Field | `private String displayName;` | `Class.getDeclaredFields()` |
| Method name | `find` | `Method.getName()` |
| Parameter type | `String customerId` | `Parameter.getType()` |
| Generic parameter type | `List<String> ids` | `Parameter.getParameterizedType()` |

`-parameters` chỉ nhắm tới tên formal parameters. Nó không biến tên local variable thành API reflection phổ quát, cũng không ghi giá trị biến tại runtime.

### 13.1. Parameter name và parameter type là hai việc riêng

Ngay cả khi không có `MethodParameters`, reflection vẫn biết kiểu và số lượng tham số từ descriptor:

```java
for (Parameter parameter : method.getParameters()) {
    System.out.println(parameter.getType().getName());
}
```

Vì vậy, thiếu tên không có nghĩa reflection không thể tìm method hoặc gọi method. Framework vẫn có thể làm việc bằng thứ tự, kiểu, annotation hoặc cấu hình explicit.

### 13.2. Generic signature cũng độc lập

Một parameter có thể có kiểu generic như `List<String>`. Generic Signature attribute và MethodParameters là hai loại metadata khác nhau. `-parameters` không thay thế thông tin generic; nếu framework cần kiểu generic, dùng `getParameterizedType()` và bảo đảm compiler giữ generic signature như bình thường.

## 14. Class transformation, shading, obfuscation và artifact cuối

Trong pipeline build, class file có thể được xử lý sau `javac`:

- Bytecode enhancement hoặc instrumentation.
- Shading/relocation khi đóng gói JAR.
- Shrinking và obfuscation.
- Weaving hoặc code generation.
- Repackaging trong plugin/build task.

Các bước này có thể giữ, sửa hoặc loại bỏ metadata tùy công cụ và cấu hình. Nếu ứng dụng dựa vào tên tham số ở runtime, kiểm tra **artifact sau bước cuối**, không chỉ thư mục output ngay sau compile.

### 14.1. Obfuscation có thể làm thay đổi tên quan sát được

Một công cụ obfuscation có thể đổi tên thành phần chương trình và metadata tương ứng. Nếu runtime framework dựa vào tên parameter gốc, cần xem quy tắc giữ metadata/tên của công cụ. Không giả định tên source luôn tồn tại nguyên vẹn trong bản đã obfuscate.

### 14.2. Kiểm tra JAR đúng phiên bản được deploy

Một quy trình tốt:

1. Build artifact từ commit/configuration dự kiến.
2. Xác định class thực tế trong JAR.
3. Chạy `javap -v -p -classpath app.jar com.example.Service`.
4. Xác nhận `MethodParameters` có tên cần thiết.
5. Chạy integration test reflection trên đúng artifact.
6. Lặp lại sau bước shrink/obfuscate nếu pipeline có bước đó.

Nếu local build có metadata nhưng production artifact thiếu, lỗi nằm ở sự khác biệt pipeline/artifact chứ không phải ở `Parameter.getName()`.

## 15. Kiểm tra tự động trong test

Có thể thêm test để ngăn cấu hình build vô tình mất metadata:

```java
Method method = Service.class.getDeclaredMethod(
    "transfer", String.class, long.class);

Parameter[] parameters = method.getParameters();

assertTrue(parameters[0].isNamePresent());
assertEquals("sourceAccount", parameters[0].getName());

assertTrue(parameters[1].isNamePresent());
assertEquals("amount", parameters[1].getName());
```

Đây là snippet test, cần `Service` có method tương ứng và JUnit/assertion framework được import. Test phải chạy trên artifact/class output đã compile theo cấu hình thật.

### 15.1. Test chính xác tên cần thiết

Chỉ kiểm tra `isNamePresent()` có thể chưa đủ. Nếu framework phụ thuộc vào tên cụ thể, hãy assert cả giá trị `getName()`. Như vậy khi ai đó đổi tên parameter, test sẽ báo rõ contract runtime đã thay đổi.

### 15.2. Test module producer

Đặt test ở module chứa class khai báo tham số, hoặc test consumer trên JAR module đã publish. Nếu chỉ test một method trong module app nhưng class dependency thiếu metadata, test có thể không phát hiện vấn đề ở đúng dependency.

### 15.3. Test artifact đóng gói

Nếu Maven/Gradle tạo JAR khác thư mục class output, thêm một integration test chạy với JAR cuối hoặc một bước CI gọi `javap` để kiểm tra. Mục tiêu là kiểm tra đúng thứ được deploy.

## 16. Lỗi thường gặp và cách sửa

1. **Bật `-parameters` ở module gọi reflection, không phải module khai báo method.** Metadata nằm trong class được compile; bật flag ở caller không bổ sung cho dependency.
2. **Nghĩ `-g` tương đương `-parameters`.** Debug info và MethodParameters là hai metadata khác nhau.
3. **Dùng `Parameter.getName()` mà không kiểm tra `isNamePresent()`.** Có thể nhận `arg0` tổng hợp; hãy kiểm tra trước khi tin.
4. **Cho rằng descriptor chứa tên tham số.** Descriptor chứa kiểu; tên nằm trong attribute riêng.
5. **Compile lại source consumer nhưng không rebuild library producer.** JAR dependency vẫn thiếu metadata.
6. **Chỉ bật flag trong IDE.** CI hoặc production build có thể dùng cấu hình khác; lưu trong build script.
7. **Kiểm tra class output cũ.** Build incremental có thể giữ artifact trước; clean build và xem đúng classpath.
8. **Compile hai bản vào cùng output folder.** Bản sau ghi đè bản trước; dùng thư mục riêng để so sánh.
9. **Nhầm local variable name với parameter name.** `LocalVariableTable` không phải `MethodParameters`; kiểm tra attribute đúng.
10. **Dùng `javap` thiếu `-v`.** Có thể không thấy chi tiết attribute; dùng `javap -v -p`.
11. **Kiểm tra JAR khác JAR đang deploy.** Xác minh đường dẫn artifact, version và classpath runtime.
12. **Giả định mọi compiler có cùng option.** `-parameters` là option của javac; compiler khác cần kiểm tra tài liệu riêng.
13. **Quên constructor parameters.** Nếu framework introspect constructor, class khai báo constructor cũng phải có metadata.
14. **Coi parameter name là một phần JVM method descriptor.** Đổi tên parameter không đổi descriptor, nhưng có thể đổi behavior framework reflection-based.
15. **Dùng tên parameter làm API contract không có kiểm soát.** Nếu contract cần ổn định, cân nhắc annotation/config explicit.
16. **Quên obfuscator/shrinker.** Kiểm tra metadata trong artifact cuối và cấu hình giữ thông tin cần thiết.
17. **Giả định mọi framework tự dùng tên tham số.** Còn phụ thuộc framework version, annotation và configuration.
18. **Dùng tên `arg0` như tên thật.** `isNamePresent()` false nghĩa là không có metadata tên.
19. **Bỏ qua cờ synthetic/implicit.** Framework tổng quát cần nhận biết parameter compiler-generated.
20. **Chỉ kiểm tra compile thành công.** Compile không chứng minh class file có MethodParameters; dùng javap và reflection test.
21. **Dùng `--release` trên chính JDK 8.** Tùy chọn này chỉ có từ JDK 9; JDK 8 dùng `-parameters` trực tiếp.
22. **Nghĩ `-parameters` ghi giá trị parameter.** Nó chỉ ghi metadata tên/cờ, không ghi giá trị runtime.
23. **Nghĩ có tên parameter là có thể tìm method theo tên parameter.** `getDeclaredMethod` vẫn tìm bằng method name và kiểu tham số.
24. **Quên kiểm tra tất cả compile tasks.** Test sources, generated source hoặc module riêng có thể dùng task compiler khác.
25. **Dựa vào một lần chạy local.** Kiểm tra CI artifact và runtime production tương ứng.

## 17. Checklist triển khai

- [ ] Xác định method/constructor nào cần tên qua reflection.
- [ ] Xác định module/JAR chứa class khai báo executable.
- [ ] Bật `-parameters` trong compiler thực tế.
- [ ] Nếu dùng Java 8, xác nhận compiler có hỗ trợ flag; javac Java 8 đã có.
- [ ] Nếu dùng JDK mới compile target Java 8, đặt `--release 8` khi phù hợp.
- [ ] Phân biệt `MethodParameters` với `LocalVariableTable`.
- [ ] Dùng `Executable.getParameters()` và `Parameter.isNamePresent()`.
- [ ] Chỉ tin `getName()` là tên source khi `isNamePresent()` true.
- [ ] Kiểm tra `javap -v -p` trên class/JAR thật.
- [ ] Kiểm tra major version nếu yêu cầu Java 8 runtime.
- [ ] Bật flag trong Maven/Gradle configuration có version control.
- [ ] Áp dụng cho producer module, không chỉ consumer.
- [ ] Kiểm tra artifact sau shading, instrumentation, shrinking hoặc obfuscation.
- [ ] Thêm reflection test cho những tên parameter là contract.
- [ ] Dùng annotation/config explicit nếu framework/API cần tên ổn định.
- [ ] Không dựa vào parameter names cho security authorization hoặc trust boundary.

## 18. Câu hỏi ôn luyện và lời giải

**1. `javac -parameters` làm gì?**  
Yêu cầu compiler ghi metadata tên formal parameters vào class file để Java Reflection đọc được.

**2. Metadata được lưu trong attribute nào?**  
`MethodParameters`.

**3. Tính năng này có từ Java nào?**  
Java 8.

**4. API reflection nào trả về các parameter?**  
`Executable.getParameters()`, dùng được với `Method` và `Constructor`.

**5. Làm sao biết tên parameter thực sự có trong class file?**  
Gọi `Parameter.isNamePresent()`; hoặc kiểm tra `MethodParameters` bằng `javap -v -p`.

**6. Không có metadata thì `getName()` có thể trả gì?**  
Tên tổng hợp như `arg0`, `arg1`; `isNamePresent()` trả false.

**7. `-g` có thay thế `-parameters` không?**  
Không. Debug attributes và MethodParameters phục vụ mục đích khác nhau.

**8. `-g:none` có loại bỏ MethodParameters không?**  
Không. Hai tùy chọn độc lập; có thể compile với `-parameters -g:none` và reflection vẫn thấy tên.

**9. `-parameters` có thay đổi method descriptor không?**  
Không. Descriptor vẫn chứa tên method và kiểu tham số/kiểu trả về theo class-file rules; tên tham số được ghi trong attribute riêng.

**10. Compile caller với flag có sửa dependency class không?**  
Không. Phải compile lại class khai báo method/constructor.

**11. `javap` cần option nào để xem attribute?**  
`javap -v -p`.

**12. Vì sao cần hai output directory khi so sánh?**  
Để hai bản class không ghi đè nhau và có thể chạy/kiểm tra độc lập.

**13. `--release 8` có chạy trên javac JDK 8 không?**  
Không. `--release` được thêm từ JDK 9; JDK 8 dùng `javac -parameters`.

**14. Tên parameter có phải contract JVM không?**  
Không phải phần descriptor/linkage, nhưng có thể trở thành contract quan sát được với framework dùng reflection.

**15. `Parameter.getType()` có hoạt động khi thiếu tên không?**  
Có. Kiểu tham số được xác định từ method descriptor, độc lập với tên.

**16. `-parameters` có ghi tên local variables không?**  
Không. Local variable debug info là cơ chế riêng.

**17. `MethodParameters` có áp dụng cho constructor không?**  
Có. Constructor cũng là `Executable` và có formal parameters.

**18. Framework có luôn tự dùng tên parameter không?**  
Không. Hành vi tùy framework, version, annotation và cấu hình.

**19. Nếu class bị obfuscate thì tên reflection có chắc còn nguyên không?**  
Không. Kiểm tra cấu hình transformation và artifact cuối.

**20. Cách xác minh đáng tin cho CI?**  
Compile theo build configuration, chạy reflection test và/hoặc kiểm tra `MethodParameters` bằng `javap` trên artifact được đóng gói.

## 19. Tài liệu chính thức và công cụ

- [`javac` — Java SE 25 compiler command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn `-parameters`, `-g`, `-g:none`, `--release` và cách gọi compiler.
- [`javap` — Java SE 25 disassembler](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): tùy chọn `-v`, `-p` và đọc class file.
- [`java.lang.reflect.Parameter` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html): `getName`, `isNamePresent`, modifiers, synthetic/implicit và parameter annotations.
- [`java.lang.reflect.Executable` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Executable.html): API chung của Method và Constructor, bao gồm `getParameters()`.
- [`Parameter` — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/lang/reflect/Parameter.html): xác nhận reflection parameter API đã có từ Java 8.
- [JVMS `4.7.24 — MethodParameters Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.24): cấu trúc class-file attribute và parameter flags.
- [Maven Compiler Plugin — parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html#parameters): cấu hình plugin để sinh metadata parameter.
- [Gradle JavaCompile](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html): compiler arguments cho task Java compile.

**Nguyên tắc cuối:** nếu runtime cần đọc tên formal parameters, hãy compile **class khai báo method/constructor** với `javac -parameters`, rồi xác minh `MethodParameters` trong class file bằng `javap -v -p` và kiểm tra `Parameter.isNamePresent()`. Debug symbols `-g` hữu ích cho debugger nhưng không thay thế metadata reflection này.
