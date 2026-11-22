# Tên tham số và tùy chọn biên dịch -parameters trong Java Reflection

## 1. Vấn đề: vì sao Method.getParameters() thường cho arg0, arg1?

Trong mã nguồn Java, tên tham số giúp con người hiểu ý nghĩa của API:

```java
public void greet(String recipient, int repeatCount) { }
```

Ta có thể dùng Reflection lấy kiểu, số lượng và thứ tự tham số của phương thức này kể cả khi biên dịch mặc định. Nhưng **tên `recipient` và `repeatCount` không nhất thiết được lưu trong class file theo cách Reflection đọc được**.

Khi trình biên dịch không lưu tên vào thuộc tính `MethodParameters`, `java.lang.reflect.Parameter.getName()` trả tên do Reflection **tự sinh** theo dạng `argN` (ví dụ `arg0`, `arg1`), còn `Parameter.isNamePresent()` trả `false`. Khi biên dịch với **`javac -parameters`**, trình biên dịch chuẩn sẽ lưu tên tham số của các method và constructor phù hợp để Reflection lấy lại:

```bash
javac -parameters Example.java
```

Khi class file chứa metadata tên hợp lệ, `getName()` trả tên theo metadata và `isNamePresent()` trả `true`. Đây là **tùy chọn lúc biên dịch source**, không phải tham số JVM truyền vào lệnh `java` khi chạy ứng dụng.

Những điểm cần phân biệt:

- **Tên nguồn** như `recipient` là dữ liệu mô tả, không tham gia kiểm tra chữ ký method ở JVM.
- **Kiểu và thứ tự** như `(String, int)` vẫn tồn tại trong method descriptor và vẫn đọc được qua `getParameterTypes()` dù thiếu tên.
- `-parameters` không tự làm thay đổi chữ ký JVM, thứ tự, kiểu tham số hay hành vi của phương thức; nó bổ sung metadata cần cho công cụ runtime.
- `getName()` **luôn trả một chuỗi tên** nếu metadata hợp lệ, kể cả tên giả `argN`. Muốn biết tên lấy từ class file hay được tổng hợp, kiểm tra **`isNamePresent()`**, không đoán theo nội dung chuỗi.

## 2. Các API cần dùng

Cả `Method` và `Constructor<?>` đều kế thừa `Executable`. API chung `Executable.getParameters()` trả mảng `Parameter[]` mô tả các formal parameter của executable.

| API | Ý nghĩa |
| --- | --- |
| `method.getParameters()` / `constructor.getParameters()` | Mảng `Parameter[]` theo đúng thứ tự formal parameter trong metadata executable |
| `executable.getParameterCount()` | Số formal parameters ở mức JVM/Reflection |
| `executable.getParameterTypes()` | Kiểu khai báo sau type erasure dưới dạng `Class<?>[]` |
| `executable.getGenericParameterTypes()` | Kiểu generic khai báo khi có dữ liệu signature thích hợp |
| `parameter.getName()` | Tên từ class file hoặc tên tổng hợp dạng `argN` |
| `parameter.isNamePresent()` | Có tên được lưu trong `MethodParameters` hay không |
| `parameter.getType()` | Kiểu khai báo ở runtime, ví dụ `String.class` hoặc `int.class` |
| `parameter.getParameterizedType()` | Kiểu tham số có thông tin generic theo chữ ký khai báo |
| `parameter.getDeclaringExecutable()` | `Method` hay `Constructor` sở hữu tham số |
| `parameter.isImplicit()` | Tham số được khai báo ngầm theo quy tắc Java |
| `parameter.isSynthetic()` | Tham số do compiler sinh, không được khai báo tường minh hay ngầm trong source |
| `parameter.isVarArgs()` | Tham số này là formal varargs hay không |

Các API `Parameter` và `Executable.getParameters()` đã có từ **Java 8**. Bài minh họa sử dụng cú pháp Java 17+ và các API đã ổn định từ lâu; không cần JDK 20 mới đọc được parameter names.

**Mấu chốt:** `getParameterTypes()` và `getParameterCount()` vẫn làm việc khi `isNamePresent() == false`. Không được nhầm thiếu *tên* với thiếu *tham số* hoặc mất thông tin *kiểu*.

## 3. Chương trình Java hoàn chỉnh và kết quả trước/sau -parameters

Lưu toàn bộ mã vào tệp `ParameterNamesDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;

public class ParameterNamesDemo {
    public ParameterNamesDemo(String title, int level) {}

    public void greet(String recipient, int repeatCount) {}

    public static void main(String[] args) throws Exception {
        Method method = ParameterNamesDemo.class.getDeclaredMethod(
                "greet", String.class, int.class);
        Constructor<ParameterNamesDemo> ctor =
                ParameterNamesDemo.class.getConstructor(String.class, int.class);

        System.out.println("method:");
        for (Parameter p : method.getParameters()) {
            System.out.println(p.getName() + " | " + p.isNamePresent()
                    + " | " + p.getType().getSimpleName());
        }

        System.out.println("constructor:");
        for (Parameter p : ctor.getParameters()) {
            System.out.println(p.getName() + " | " + p.isNamePresent()
                    + " | " + p.getType().getSimpleName());
        }

        System.out.println("count = " + method.getParameterCount());
        System.out.println("parameter types = "
                + Arrays.toString(method.getParameterTypes()));
    }
}
```

**Thử nghiệm A: biên dịch không có `-parameters`.** Giả sử đang đứng tại thư mục chứa file nguồn:

```bash
javac --release 17 -g -d plain ParameterNamesDemo.java
java -cp plain ParameterNamesDemo
```

Stdout của chương trình (đã kiểm tra thực tế bằng JDK 24 khi biên dịch target Java 17):

```text
method:
arg0 | false | String
arg1 | false | int
constructor:
arg0 | false | String
arg1 | false | int
count = 2
parameter types = [class java.lang.String, int]
```

**Thử nghiệm B: biên dịch có `-parameters`.** Ghi class files sang **thư mục khác** để không bị file từ bước A làm nhiễu:

```bash
javac --release 17 -g -parameters -d named ParameterNamesDemo.java
java -cp named ParameterNamesDemo
```

Stdout chính xác:

```text
method:
recipient | true | String
repeatCount | true | int
constructor:
title | true | String
level | true | int
count = 2
parameter types = [class java.lang.String, int]
```

Thử nghiệm cho thấy:

1. **Cùng source**, cùng chữ ký và cùng kiểu tham số, nhưng metadata tên trong class file khác nhau khi thay đổi cờ compiler.
2. `-g` đã được bật trong **cả hai** lệnh biên dịch. Vì kết quả A vẫn là `arg0`/`arg1`, có thể thấy **`-g` không thay cho `-parameters`** để `Parameter.getName()` đọc tên thật.
3. Hai dòng `count` và `parameter types` **không đổi**. Java vẫn biết có hai tham số `String` và `int` ngay cả khi tên vắng mặt.
4. Constructor cũng thuộc nhóm executable; `getParameters()` trên constructor hưởng metadata tên tương tự method.
5. Các kết quả trong ví dụ được xác nhận trong môi trường thử nghiệm. Với chương trình khác, tên và mức độ có metadata phụ thuộc thực tế class file và compiler đã tạo nó.

**Chú ý classpath:** `java -cp plain ParameterNamesDemo` đọc chính `ParameterNamesDemo.class` trong `plain`, còn `java -cp named ...` đọc file đã biên dịch trong `named`. Nếu chạy từ classpath không đúng, bạn có thể tưởng cờ đã bật nhưng Reflection vẫn thấy bytecode cũ.

## 4. MethodParameters và LocalVariableTable: hai loại metadata khác nhau

Class file chứa **method descriptor** cho từng executable, đủ để JVM biết kiểu và thứ tự tham số. Tên tham số có thể được lưu thêm trong attribute **`MethodParameters`**. `javac -parameters` là cơ chế chuẩn yêu cầu javac lưu metadata cần thiết này.

Một thuộc tính khác là **`LocalVariableTable`** (LVT), dùng cho thông tin debug, thường có khi bật `-g` hoặc `-g:vars`. LVT mô tả local variables và tham số theo phạm vi bytecode/slot cho debugger hoặc công cụ đọc bytecode; **`Parameter.getName()` không dùng LVT làm nguồn tên dự phòng**. `Parameter.isNamePresent()` dựa trên sự có mặt của tên theo `MethodParameters`.

| Tùy chọn biên dịch | Metadata trọng tâm | Tác động đối với `Parameter.getName()` |
| --- | --- | --- |
| Không truyền `-parameters` | Có method descriptor, có thể có một số debug metadata | Tên có thể không có; API sẽ sinh `argN` |
| `-g` / `-g:vars` | Thông tin debug, gồm LVT theo tùy chọn và khả năng method có code | Không bảo đảm tên thật qua core Reflection |
| `-parameters` | Lưu formal parameter names vào `MethodParameters` | Cho phép `isNamePresent() == true` và `getName()` trả tên đã lưu |
| `-g -parameters` | Vừa debug metadata vừa MethodParameters | Có thể phục vụ cả debugger và Reflection |

`-g` là công cụ phục vụ debug; `-parameters` phục vụ nhu cầu **runtime reflection trên tên tham số**. LVT không nhất thiết xuất hiện với abstract/interface methods không có code; `MethodParameters` có thể mô tả parameters của cả method không có phần body.

### Tự kiểm tra bằng javap

Trong ví dụ trên:

```bash
javap -v -p plain/ParameterNamesDemo.class
javap -v -p named/ParameterNamesDemo.class
```

Tìm các section `MethodParameters` ở output bản `named` và xem các tên `recipient`, `repeatCount`, `title`, `level`. Bản `plain` biên dịch không có `-parameters` trong thử nghiệm này không có các section tương ứng cho method/constructor ấy. Vì cả hai bản dùng `-g`, bạn vẫn có thể thấy thông tin debug trong `Code` và `LocalVariableTable` dù Reflection trả tên `argN` ở bản `plain`.

`javap -v` là công cụ hỗ trợ kiểm tra **bytecode thực sự đã build**; khi hành vi Reflection trái mong đợi, hãy kiểm tra file ở output/classpath đang được chạy, không chỉ kiểm tra source file.

## 5. Chi tiết hành vi của Parameter.getName và isNamePresent

### arg0 không phải bằng chứng duy nhất về thiếu metadata

Khi thiếu tên, Java Reflection đặt tên tổng hợp `argN` với `N` là chỉ số của tham số trong descriptor của executable. Tuy nhiên, trong source code hoàn toàn có thể **cố ý khai báo một tham số tên `arg0`** và biên dịch bằng `-parameters`. Do đó:

```java
String effectiveName = parameter.getName();
boolean reliableFromClassFile = parameter.isNamePresent();
```

Đây là đoạn minh họa, biến `parameter` cần là `java.lang.reflect.Parameter` lấy từ `getParameters()`. **Dùng `isNamePresent()` để kiểm tra nguồn tên**, không dùng `getName().startsWith("arg")` hoặc regex `arg[0-9]+`.

Kể cả khi tên có trong class file, không nên mặc định đó là “tên gốc” của mọi ngôn ngữ và quy trình build: công cụ bytecode, compiler ngôn ngữ khác, obfuscator và code generator có thể ghi hoặc đổi metadata. API cho biết **tên hiện có trong class file**, không chứng nhận lịch sử biên dịch.

### Class file có thể không mang tên đủ tin cậy

Khi xây framework cần ánh xạ argument theo tên, hãy có cách xử lý nếu `isNamePresent()` trả `false`. Chẳng hạn:

```java
static String requireName(Parameter parameter) {
    if (!parameter.isNamePresent()) {
        throw new IllegalStateException(
                "Thiếu tên tham số: hãy biên dịch module bằng -parameters");
    }
    return parameter.getName();
}
```

Đây là một phương thức Java hợp lệ có thể đặt trong class đang xử lý Reflection; các thông số khác của phương thức chưa được nêu, như chính sách fallback, tùy sản phẩm. Không dùng tên giả `arg0` để âm thầm map JSON key hoặc query parameter thành tên “arg0” nếu hợp đồng ứng dụng yêu cầu tên source cụ thể.

### Trường hợp tham số sinh ra khi biên dịch

`Executable.getParameters()` mô tả các tham số tồn tại ở mức executable runtime. Một số construct Java, như inner-class constructor không static hoặc compiler-generated code, có thể xuất hiện tham số ẩn/implicit/synthetic trong bytecode, làm danh sách khác với cách đọc thoáng qua source.

Các API `Parameter.isImplicit()`, `isSynthetic()`, `getModifiers()` giúp giải thích metadata tương ứng, **nếu class file cung cấp các dấu hiệu cần thiết**. Đừng cố đồng nhất số tham số source với số tham số runtime trong mọi trường hợp.

Nếu cần tìm **tên một tham số của một method xác định**, nên tra cứu method với exact signature (`getDeclaredMethod("name", types...)`) rồi duyệt `getParameters()`. Đối với constructor, tra `getDeclaredConstructor(types...)` theo descriptor thực tế. Với class file bị biến đổi không hợp lệ, reflection có thể phát sinh lỗi về metadata tham số (ví dụ `MalformedParametersException`); không suy rằng compiler bình thường luôn tạo metadata lỗi.

## 6. Cách ứng dụng -parameters trong build thực tế

### Biên dịch trực tiếp bằng javac

Với JDK 17 trở lên và cấu trúc ví dụ đơn giản:

```bash
javac -parameters -d out src/com/example/App.java
java -cp out com.example.App
```

Đây là mẫu lệnh: đường dẫn `src/com/example/App.java` và fully-qualified name `com.example.App` phải khớp source/project thực tế. Trong hệ thống nhiều module, **mỗi module cần metadata tên** phải được biên dịch với tùy chọn phù hợp. Không phải chỉ bật `-parameters` ở ứng dụng chính là khiến các JAR phụ thuộc sẵn có tự có tên.

Nếu cần vừa target Java 17 vừa lưu tên:

```bash
javac --release 17 -parameters -d out ParameterNamesDemo.java
```

`--release 17` điều khiển API/language/class-file target, còn `-parameters` điều khiển lưu metadata tên. Hai cờ phục vụ mục đích khác nhau và có thể dùng cùng nhau.

### Maven

Trong `pom.xml`, dùng cấu hình của Maven Compiler Plugin:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>17</release>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Đây là **đoạn cấu hình để lồng trong `<project>` của POM**, không phải toàn bộ `pom.xml` độc lập. Với build cần tái lập, nên khai báo phiên bản plugin thích hợp với môi trường trong project. Sau khi cập nhật, thực hiện compile lại toàn bộ module có liên quan và chạy kiểm thử kiểm tra `isNamePresent()`.

### Gradle (Groovy DSL)

Trong `build.gradle` của Java project, có thể thêm:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Đây là đoạn cấu hình trong Gradle Groovy DSL; với Kotlin DSL (`build.gradle.kts`), có cú pháp khác. Kết hợp toolchain hoặc `options.release` để đặt target Java riêng. Quan trọng là tác vụ `JavaCompile` thực sự chạy với `-parameters` và mọi module/JAR đang được kiểm tra đã được build mới.

Nếu một library được phát hành bởi bên thứ ba, cờ của **dự án tiêu thụ library** không làm thay đổi class file của dependency ấy. Cần library build với metadata, hoặc framework dùng cơ chế ánh xạ khác như annotation có tên tường minh.

## 7. Ứng dụng thực tế: framework ánh xạ theo tên tham số

Tên tham số phản chiếu đặc biệt có ích khi framework ánh xạ dữ liệu theo **tên**, ví dụ constructor injection, binding tham số HTTP, named SQL parameter mapping hoặc serializing/deserializing vào constructor. Nếu thiết kế dựa trên `getName()`:

1. Tra cứu `Method` hoặc `Constructor<?>` đã biết đúng.
2. Lấy `Parameter[]` và kiểm tra `isNamePresent()` cho các tham số cần dùng.
3. Nếu thiếu metadata, báo lỗi build/config rõ ràng hoặc dùng nguồn tên khác có hợp đồng tường minh (ví dụ annotation).
4. Dùng `getType()`/`getParameterizedType()` để kiểm tra và chuyển đổi **giá trị**; tên đơn thuần không bảo đảm type safety.
5. Duy trì đúng thứ tự `Object[]` khi gọi `Constructor.newInstance(...)` hoặc `Method.invoke(receiver, args)`. Những API gọi method/constructor dùng **thứ tự đối số**, không tự reorder theo tên.

Ví dụ helper đọc tên có yêu cầu metadata:

```java
import java.lang.reflect.Executable;
import java.lang.reflect.Parameter;
import java.util.ArrayList;
import java.util.List;

public final class ParameterNames {
    private ParameterNames() {}

    public static List<String> requiredNames(Executable executable) {
        List<String> names = new ArrayList<>();
        for (Parameter p : executable.getParameters()) {
            if (!p.isNamePresent()) {
                throw new IllegalStateException(
                        "Missing MethodParameters name: " + executable);
            }
            names.add(p.getName());
        }
        return List.copyOf(names);
    }
}
```

Đây là class Java 17+ hợp lệ để tái sử dụng; nó không có `main`. Nếu thiếu tên của bất kỳ tham số nào, nó báo lỗi thay vì silently coi `argN` là một tên business hợp lệ. Một sản phẩm có thể thay chiến lược này bằng annotation hoặc schema tên tường minh, nhưng cần quyết định rõ.

### API không yêu cầu tên thì không cần -parameters

Không phải mọi code dùng Reflection đều phải bật `-parameters`. Ví dụ:

```java
Method method = type.getDeclaredMethod(
        "greet", String.class, int.class);
Object result = method.invoke(target, "Mai", 2);
```

Đây là mảnh code: khi đã có `type` và `target` phù hợp cùng quyền truy cập, việc tìm/call method dựa trên **tên method và kiểu/thứ tự tham số**, không cần tên từng tham số `recipient` và `repeatCount`. Nếu code chỉ làm invocation theo signature hoặc kiểm tra parameter types, thêm `-parameters` có thể không mang lợi ích chức năng.

## 8. Phân biệt tham số, annotation, generic và các metadata khác

`-parameters` tác động **tên** tham số; các thông tin khác có cơ chế class-file riêng:

- `Parameter.getType()` đọc kiểu sau erasure theo descriptor; không phụ thuộc `-parameters`.
- `Parameter.getParameterizedType()` đọc thông tin generic khi có `Signature` thích hợp, chẳng hạn `List<String>`. Bật `-parameters` **không chống được type erasure** và không khiến runtime biết generic type argument của mọi object.
- `Parameter.getAnnotations()` và `getAnnotation(...)` đọc runtime-visible parameter annotations theo cơ chế giữ annotation (`@Retention(RUNTIME)`). `-parameters` không biến mọi annotation `SOURCE`/`CLASS` thành runtime annotation.
- `Parameter.isVarArgs()` liên quan varargs của executable, không được suy ra từ tên tham số. Một formal `String... args` có runtime type `String[]`.
- `Parameter.getDeclaringExecutable()` chỉ đến owner `Method`/`Constructor`, không phải object argument mà một lần gọi nhận được.
- `Executable.getParameterCount()` báo số formal parameters ở mức runtime; debug flags không làm thay đổi method descriptor.
- `java.lang.reflect.AccessFlag` là API được thêm từ JDK 20 phục vụ flags khác; **đọc tên tham số và `-parameters` đã tồn tại từ Java 8**.

Tên tham số được đọc từ class file không bảo đảm là tên ổn định xuyên bản release của thư viện. Nếu người dùng bên ngoài phụ thuộc vào tên để binding thì việc đổi tên source rồi build lại với `-parameters` có thể làm thay đổi behavior framework, dù method descriptor và JVM binary signature vẫn y hệt.

## 9. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân/kiểm tra |
| --- | --- |
| `getName()` là `arg0`, `isNamePresent()` là `false` | Class file đang chạy không có tên trong `MethodParameters`; biên dịch lại module thực sự cần dùng bằng `-parameters` |
| Đã bật `-g` mà tên vẫn `arg0` | `LocalVariableTable` không phải nguồn của `Parameter.getName()`; bật `-parameters` |
| Đã bật `-parameters` nhưng vẫn false | Có thể chạy bytecode cũ, nhầm classpath/module, dependency chưa rebuild, hoặc bytecode đã bị công cụ khác biến đổi |
| Bật `-parameters` ở ứng dụng nhưng thư viện vẫn false | Thư viện JAR có class file riêng; cần metadata từ phía thư viện |
| Dùng `java -parameters ...` | Sai vị trí: đây là tùy chọn của **javac**, không phải runtime switch của launcher `java` |
| Truy vấn `getMethod("f", String.class)` sai | Tìm kiếm dùng formal parameter types; tên tham số không ảnh hưởng overload lookup |
| Reflection trả nhiều tham số hơn hình dung từ source | Có thể là implicit/synthetic parameters; kiểm tra signature, flags và construct Java tương ứng |
| Thấy `getName()` giống `arg0` nhưng `isNamePresent()` true | Có thể tên đã được biên dịch thật là `arg0`; luôn tin `isNamePresent()` thay vì pattern chuỗi |
| Tên có mặt nhưng binding vẫn sai | Kiểm tra tên annotation/schema, tên bị đổi sau obfuscation, type conversion và thứ tự gắn giá trị; `-parameters` chỉ lo metadata tên |

Cách chẩn đoán nhanh:

```bash
javap -v -p path/to/YourClass.class
```

Tìm `MethodParameters` của method/constructor thực tế đang gặp lỗi. Nếu có nhiều bản class trên classpath, trước hết xác minh ứng dụng thực sự nạp file/JAR nào. Với build tool, thực hiện clean/rebuild phù hợp để loại stale bytecode rồi chạy test dựa trên `isNamePresent()`.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Biên dịch `void f(String city)` bằng `javac -g`, không có `-parameters`, `Parameter.getName()` có bắt buộc là `city` không? **Không**. Trong trường hợp thông thường của javac, tên tổng hợp sẽ là `arg0` và `isNamePresent()` là `false`.

**Câu 2.** Bật `-parameters` có đổi `getParameterTypes()` hoặc thứ tự formal parameters không? **Không**. Chỉ bổ sung metadata tên; method descriptor không thay đổi bởi riêng cờ này.

**Câu 3.** Tại sao không kiểm tra `p.getName().startsWith("arg")` để biết thiếu metadata? Vì tên nguồn **có thể thật sự là `arg0`**; `p.isNamePresent()` mới là kiểm tra chuẩn.

**Câu 4.** Muốn tham số constructor xuất hiện tên gốc trong Reflection thì chỉ bật `-parameters` ở file có `main` là đủ? **Không**. Phải biên dịch **chính class khai báo constructor** với metadata, trừ các trường hợp đặc thù khác do compiler/class-file specification đảm bảo.

**Câu 5.** Đã có `Method m` có hai tham số. Khi biên dịch không có `-parameters`, `m.getParameterCount()` có thể vẫn là 2 không? **Có**. Kiểu/số lượng dựa vào descriptor, không vào tên.

**Câu 6.** `-parameters` có làm `@Retention(SOURCE)` annotation trên parameter đọc được bằng Reflection không? **Không**. Retention annotation có cơ chế riêng.

**Câu 7.** Framework gọi `Method.invoke` cần tên `recipient` để sắp xếp thứ tự args không? **Không, nếu nó đã biết thứ tự tham số từ schema/metadata**. Invocation nhận arguments theo vị trí; tên chỉ cần khi nguồn dữ liệu bên ngoài phải map theo tên.

**Câu 8.** Có thể xem metadata lưu tên bằng công cụ nào trong JDK? **`javap -v -p`** trên đúng class file đã build, tìm section `MethodParameters`.

## 11. Tài liệu chính thức

- [Oracle Java SE 17 — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): `getName()`, `isNamePresent()`, `getType()`, `getParameterizedType()`.
- [Oracle Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html): `getParameters()`, `getParameterCount()`, `getParameterTypes()`.
- [Oracle Java SE 17 — javac options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): mô tả `-parameters`, `-g`, `--release`.
- [Java Virtual Machine Specification 17 — `MethodParameters` attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.24): class-file representation.
- [Java Virtual Machine Specification 17 — `LocalVariableTable` attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.13): debug metadata.
