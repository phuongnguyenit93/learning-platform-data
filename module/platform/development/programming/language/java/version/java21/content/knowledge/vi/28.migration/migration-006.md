# Rà soát reflection, annotation processing và bytecode generation

Khi nâng một ứng dụng lên Java 21, ba nhóm công nghệ cần được rà soát kỹ là reflection, annotation processing và bytecode generation. Chúng thường xuất hiện trong framework, thư viện dependency injection/serialization, ORM, mapper, compiler plugin, công cụ kiểm thử và agent quan sát runtime. Code ứng dụng có thể không gọi trực tiếp các API này nhưng vẫn bị ảnh hưởng khi một thư viện cố truy cập package nội bộ, chạy annotation processor hoặc phân tích class file được tạo bởi JDK mới.

Java 21 tiếp tục áp dụng strong encapsulation của Java Platform Module System (JPMS), có class-file version 65 và hỗ trợ các API annotation processing chuẩn. Cách nâng cấp an toàn là xác định rõ package nào cần mở cho reflection, khai báo annotation processor một cách tường minh trong build, cập nhật thư viện đọc/ghi bytecode để hiểu class file Java 21 và loại bỏ phụ thuộc vào API nội bộ của JDK.

## 1. Xác định phạm vi cần rà soát

Trước khi sửa code, lập danh sách các thành phần có sử dụng reflection hoặc sinh/đọc bytecode:

| Thành phần | Rủi ro khi nâng cấp | Nội dung cần kiểm tra |
|---|---|---|
| Framework DI và cấu hình | Truy cập constructor, field hoặc method private | Module access, package cần mở |
| JSON/XML serializer | Đọc/ghi field không public | Reflection access và module descriptor |
| ORM hoặc persistence framework | Tạo proxy, truy cập entity field | Phiên bản thư viện, reflection và bytecode |
| Annotation processor | Sinh source code trong compile | Processor path, JDK tương thích, source version |
| Compiler plugin | Dựa vào API nội bộ của javac | Thay bằng API được hỗ trợ hoặc nâng phiên bản |
| Bytecode generator | Phân tích hoặc sinh class file | Hỗ trợ class-file version 65 |
| Java agent/profiler | Transform hoặc redefine class | Instrumentation API, class loader và module |
| Test framework/mock library | Tạo proxy hoặc truy cập private member | Khả năng tương thích Java 21 và JPMS |

Rà soát cả code trực tiếp lẫn dependency. Một ứng dụng có thể không chứa dòng `setAccessible(true)` nào nhưng ORM hoặc serializer vẫn gọi reflection trên class của ứng dụng. Tương tự, annotation processor có thể chỉ chạy ở build time nhưng làm compilation thất bại sau khi thay JDK.

## 2. Strong encapsulation và reflection từ Java 17 trở đi

Java 21 tiếp tục áp dụng strong encapsulation đối với các package nội bộ của JDK. Từ JDK 17, cơ chế nới lỏng truy cập nội bộ trước đây không còn là cách tương thích được hỗ trợ. Vì vậy, code dựa vào reflection để truy cập private member hoặc package nội bộ của JDK có thể ném `InaccessibleObjectException`.

Ví dụ code cũ cố truy cập field nội bộ:

```java
Field field = SomeJdkClass.class.getDeclaredField("internalState");
field.setAccessible(true);
Object value = field.get(target);
```

Nếu package chứa field không được mở cho module của ứng dụng, `setAccessible(true)` có thể thất bại. Đây thường là dấu hiệu dependency đang dựa vào implementation detail của JDK.

Không nên xử lý bằng cách mở toàn bộ package của JDK hoặc dựa vào cờ tương thích đã lỗi thời. Hãy tìm API công khai thay thế, nâng thư viện hoặc chỉ mở đúng package của module ứng dụng khi deep reflection là yêu cầu hợp lệ.

### 2.1. Phân biệt exports và opens trong JPMS

Trong module descriptor, `exports` và `opens` phục vụ hai mục đích khác nhau:

| Khai báo | Mục đích | Trường hợp sử dụng |
|---|---|---|
| `exports package.name` | Cho module khác truy cập các kiểu public trong package theo quy tắc module | API public của module |
| `opens package.name` | Cho phép deep reflection vào các member không public ở runtime | Framework cần đọc/ghi field private |
| `opens package.name to module.name` | Chỉ mở package cho module được chỉ định | Giới hạn quyền reflection |
| `open module name` | Mở tất cả package của module cho deep reflection | Chỉ dùng khi toàn module thực sự cần |

Ví dụ module ứng dụng có API public và một package entity cần mở cho serializer:

```java
module com.example.application {
    exports com.example.api;

    opens com.example.domain
            to com.example.json;
}
```

Module `com.example.json` có thể deep-reflect vào package `com.example.domain`, còn các package khác vẫn được đóng theo mặc định của module.

Ưu tiên mở có mục tiêu bằng `opens package to module`. `open module` mở rộng quyền truy cập tới tất cả package, nên làm giảm tính đóng gói và chỉ nên dùng khi kiến trúc thực sự yêu cầu.

### 2.2. Dùng --add-opens như giải pháp tương thích có kiểm soát

Nếu chưa thể thay dependency ngay, có thể mở một package cụ thể ở runtime:

```bash
java \
  --add-opens com.example.application/com.example.domain=com.example.json \
  -jar application.jar
```

Với một ứng dụng chạy trên classpath (unnamed module), target có thể là `ALL-UNNAMED`:

```bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar application.jar
```

Cờ này chỉ mở package đã nêu cho module đích. Nó không biến API nội bộ thành API được hỗ trợ ổn định và không bảo đảm dependency sẽ tương thích với các JDK tương lai.

Khi dùng `--add-opens` để chuyển tiếp:

1. Ghi lại module nguồn, package và module đích.
2. Xác định thư viện nào cần quyền truy cập.
3. Tạo issue nâng cấp hoặc thay thế thư viện.
4. Thêm kiểm thử để xác nhận không còn cần cờ.
5. Xóa cờ sau khi dependency đã dùng API được hỗ trợ.

Không dùng `--illegal-access` như một giải pháp cho Java 21. Cơ chế này đã không còn mở lại quyền truy cập nội bộ từ JDK 17; dựa vào nó sẽ không sửa được lỗi strong encapsulation.

## 3. Dùng API reflection được hỗ trợ

Các API reflection chuẩn vẫn nằm trong `java.lang.reflect`. Khi cần kiểm tra khả năng truy cập, ưu tiên `canAccess` và `trySetAccessible` thay vì giả định rằng mọi member đều có thể mở.

Ví dụ:

```java
import java.lang.reflect.Field;

class User {
    private String email = "dev@example.com";
}

class ReflectionExample {
    static Object readEmail(User user) throws ReflectiveOperationException {
        Field field = User.class.getDeclaredField("email");

        if (!field.trySetAccessible()) {
            throw new IllegalAccessException(
                    "Module chưa mở package chứa User");
        }

        return field.get(user);
    }
}
```

`trySetAccessible()` trả về `false` nếu không thể bật quyền truy cập. Nó giúp code xử lý trường hợp module chưa mở một cách tường minh. Việc gọi thành công vẫn phụ thuộc vào quy tắc truy cập và module chứa class.

Với method hoặc constructor, cách kiểm tra tương tự:

```java
Method method = User.class.getDeclaredMethod("normalize");
if (!method.trySetAccessible()) {
    throw new IllegalAccessException("Không thể truy cập method");
}
method.invoke(user);
```

Không nên mở quyền truy cập private một cách mặc định cho mọi member. Nếu chỉ cần gọi API public, hãy dùng method public hoặc interface công khai; deep reflection chỉ nên dành cho framework hoặc thành phần thực sự cần nó.

### 3.1. Khi nào dùng MethodHandles?

`MethodHandles` và `VarHandle` là API được hỗ trợ cho các trường hợp cần lời gọi động hoặc truy cập biến có ngữ nghĩa rõ ràng. Chúng không phải cách lách module access: `MethodHandles.privateLookupIn` vẫn phải tuân thủ readability và package openness của JPMS.

Ví dụ lấy `VarHandle` cho một field private trong package đã mở:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Counter {
    private int value;
}

class HandleExample {
    static VarHandle counterValue() throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
                Counter.class,
                MethodHandles.lookup()
        );

        return lookup.findVarHandle(
                Counter.class,
                "value",
                int.class
        );
    }
}
```

Nếu `Counter` nằm trong named module khác với module của lookup, module đích phải mở package tương ứng cho module gọi `privateLookupIn`. Nếu không, việc tạo private lookup có thể thất bại với lỗi truy cập. Khi hai class thuộc cùng module, không cần thêm một chỉ thị `opens` chỉ vì lời gọi này.

Dùng `MethodHandles` khi cần biểu diễn lời gọi hoặc truy cập field dưới dạng handle, cần hiệu năng phù hợp sau khi đo hoặc cần các thao tác như atomic access với `VarHandle`. Không thay toàn bộ reflection bằng MethodHandles chỉ vì nghĩ rằng chúng bỏ qua JPMS.

## 4. Rà soát reflection trong framework và dependency

Framework thường cần reflection để tạo object, inject dependency, ánh xạ JSON hoặc quản lý entity. Khi nâng lên Java 21, kiểm tra:

- Phiên bản framework có công bố hỗ trợ Java 21 không.
- Framework có dùng package nội bộ của JDK hay không.
- Có cần `--add-opens` hoặc `--add-exports` nào trong script khởi chạy không.
- Package của model/entity có cần `opens` trong module descriptor không.
- Reflection có giả định constructor mặc định hoặc field cụ thể tồn tại không.
- Test trên classpath có che giấu lỗi xuất hiện khi chạy bằng named module không.

Nếu ứng dụng dùng classpath, các class thường thuộc unnamed module. Điều này có thể làm một số kiểm thử module access khác với cấu hình triển khai bằng named module. Nếu production dùng JPMS, hãy có ít nhất một integration test chạy theo module path thực tế.

Tạo danh sách các cờ mở module đang được sử dụng:

```bash
# Ví dụ: tìm các cờ trong script hoặc cấu hình triển khai
rg -- '--add-opens|--add-exports|--illegal-access' .
```

Kết quả cần được phân loại theo mục đích. Cờ `--illegal-access` là dấu hiệu cấu hình cũ cần loại bỏ; `--add-opens` và `--add-exports` cần có owner và lý do cụ thể.

## 5. Annotation processing trong Java 21

Annotation processing là cơ chế chạy processor trong quá trình biên dịch để đọc annotation và có thể sinh source file, resource hoặc mã hỗ trợ. API chuẩn nằm trong module `java.compiler`, chủ yếu ở package `javax.annotation.processing`, `javax.lang.model` và `javax.tools`.

Các processor thường được dùng để sinh mapper, metamodel, builder, adapter hoặc mã đăng ký. Chúng chạy trong môi trường build, không phải cơ chế reflection lúc ứng dụng đang chạy.

Một processor tiêu biểu:

```java
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("com.example.GenerateAdapter")
@SupportedSourceVersion(SourceVersion.RELEASE_21)
public class AdapterProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (TypeElement annotation : annotations) {
            for (Element element : roundEnv.getElementsAnnotatedWith(annotation)) {
                // Phân tích element và tích lũy dữ liệu cần sinh source.
            }
        }

        return false;
    }
}
```

Processor có thể được phát hiện qua cơ chế service provider hoặc được chỉ định trực tiếp bằng tùy chọn compiler. Khi nâng JDK, cần kiểm tra cả API mà processor sử dụng lẫn cách build tìm và chạy processor.

### 5.1. Khai báo processor tường minh trong build

Để build có tính tái lập và tương thích với các JDK mới, hãy cấu hình processor riêng khỏi compile classpath của ứng dụng. Với `javac`, có thể dùng:

```bash
javac --release 21 \
  --processor-path build/annotation-processors:build/processor-deps \
  -processor com.example.AdapterProcessor \
  -d build/classes \
  src/main/java/com/example/Customer.java
```

Trên Windows, dấu phân tách các phần tử classpath/processor path là dấu chấm phẩy thay vì dấu hai chấm. Trong Maven hoặc Gradle, dùng cấu hình annotation processor chuyên biệt của build tool và khóa phiên bản processor cùng các dependency của nó.

Nếu processor được đóng gói dưới dạng named module, có thể sử dụng `--processor-module-path`. Không đưa processor vào runtime classpath chỉ vì compiler cần nó; tách processor dependency giúp tránh kéo công cụ build vào ứng dụng production.

### 5.2. Lưu ý thay đổi mặc định javac từ JDK 23

Trên JDK 21, javac có thể tự dò processor trên classpath theo hành vi mặc định nếu tìm thấy processor. Từ JDK 23, việc chạy annotation processing cần được yêu cầu rõ ràng, chẳng hạn bằng cách chỉ định processor, processor path/module path hoặc chế độ `-proc:only`/`-proc:full`.

Do đó, build đang chạy được trên JDK 21 nhờ tự động phát hiện processor có thể không sinh mã khi chuyển sang JDK mới hơn nếu không khai báo processor rõ ràng.

Để build tường minh:

```bash
javac --release 21 \
  -proc:full \
  --processor-path build/annotation-processors \
  -processor com.example.AdapterProcessor \
  -d build/classes \
  src/main/java/com/example/Customer.java
```

Nếu build không dùng annotation processing, có thể tắt rõ ràng bằng `-proc:none`. Tránh phụ thuộc vào việc compiler tình cờ tìm thấy processor nào đó trên compile classpath.

Đây là khác biệt giữa **source/target release** và **hành vi của compiler**: `--release 21` đặt ngôn ngữ, bytecode và API Java mục tiêu, nhưng không khôi phục mặc định dò processor của một JDK khác.

## 6. Rà soát processor và code được sinh

Khi nâng processor lên Java 21, kiểm tra các khía cạnh sau:

- Processor có hỗ trợ source model Java 21 và annotation mới trong codebase không.
- Processor có khai báo `@SupportedSourceVersion` phù hợp không.
- Có sử dụng API nội bộ `com.sun.tools.javac.*` hoặc class của compiler implementation không.
- Có ghi file trực tiếp vào thư mục build thay vì dùng `Filer` không.
- Có xử lý đúng nhiều processing round không.
- Có tạo tên file ổn định và tránh sinh trùng file giữa các round không.
- Processor có phụ thuộc vào thứ tự xử lý annotation hoặc thứ tự duyệt element không được bảo đảm không.
- Generated source có compile được với `--release 21` không.

Dùng `Filer` để tạo source hoặc resource thay vì tự ghi file vào thư mục build:

```java
import java.io.IOException;
import java.io.Writer;
import javax.tools.JavaFileObject;

void generateAdapter() throws IOException {
    JavaFileObject generated = processingEnv.getFiler()
            .createSourceFile("com.example.generated.CustomerAdapter");

    try (Writer writer = generated.openWriter()) {
        writer.write("""
                package com.example.generated;

                public final class CustomerAdapter {
                    private CustomerAdapter() {}
                }
                """);
    }
}
```

`Filer` cho compiler biết file nào được tạo trong processing round và giúp phát hiện trường hợp processor cố tạo lại cùng một file. Nếu processor cần tổng hợp thông tin từ nhiều type, hãy tích lũy dữ liệu theo round và chỉ sinh file khi đã có đủ input.

### 6.1. Không phụ thuộc API nội bộ của javac

Các package như `com.sun.tools.javac.*` là implementation detail của compiler, không phải API ổn định cho processor. Code phụ thuộc chúng có thể hỏng khi đổi JDK hoặc phiên bản compiler.

Ưu tiên các API được hỗ trợ:

- `javax.annotation.processing` cho vòng đời processor.
- `javax.lang.model` để đọc element, type và annotation.
- `javax.tools` và `Filer` để làm việc với source/resource.
- `com.sun.source.tree` và `com.sun.source.util` khi cần compiler tree API được công bố trong module `jdk.compiler`, sau khi kiểm tra phạm vi API và module tương ứng.

Nếu processor hiện tại phụ thuộc sâu vào javac internals, hãy nâng thư viện hoặc chuyển sang API compiler được hỗ trợ trước khi đổi JDK. Không thêm hàng loạt `--add-exports` tới package nội bộ javac để giữ processor cũ hoạt động lâu dài.

## 7. Java 21 và class-file version 65

Java 21 sử dụng class-file major version **65**. Công cụ đọc, phân tích, sửa đổi hoặc sinh bytecode phải hiểu phiên bản class file này và các cấu trúc mà Java 21 sử dụng.

Có thể kiểm tra class file bằng `javap`:

```bash
javap -verbose -classpath build/classes com.example.Customer
```

Trong phần đầu output, tìm:

```text
major version: 65
```

Nếu bytecode tool cũ chỉ hiểu class file của JDK trước đó, nó có thể báo lỗi kiểu “unsupported class file major version 65”, bỏ qua attribute hoặc tạo bytecode không hợp lệ.

Cần rà soát tất cả thành phần xử lý class file, không chỉ compiler:

- Bytecode generator hoặc proxy generator.
- Code coverage và mocking library.
- Static analyzer và obfuscator.
- Framework tạo subclass/runtime proxy.
- Agent dùng `ClassFileTransformer`.
- Build plugin phân tích bytecode dependency.
- Công cụ đóng gói hoặc tối ưu class file.

Nâng phiên bản thư viện tới bản công bố hỗ trợ Java 21, sau đó kiểm thử cả việc đọc class file lẫn việc sinh và nạp class được tạo.

## 8. Cập nhật bytecode library và generator

Các thư viện như ASM hoặc Byte Buddy cung cấp API để đọc và sinh bytecode. Khi nâng lên Java 21:

1. Kiểm tra release note của phiên bản thư viện đang dùng để xác nhận hỗ trợ class-file version 65.
2. Cập nhật plugin hoặc framework đang mang theo bản bytecode library cũ.
3. Tránh ép một dependency mới dùng lại bản ASM cũ qua dependency mediation.
4. Kiểm tra code generator có xử lý đúng record, sealed class, nest-based access và các attribute class file mà ứng dụng sử dụng.
5. Chạy test load class được sinh bằng đúng class loader và module của production.
6. Nếu có agent, kiểm tra cả transformation và retransformation trên class của JDK 21.

Không chỉ kiểm tra compile thành công. Một generator có thể tạo class file mà compiler không trực tiếp nhìn thấy; lỗi chỉ xuất hiện lúc JVM định nghĩa class hoặc khi framework truy cập member được sinh.

### 8.1. Kiểm tra tương thích ở cả hai chiều

Một công cụ bytecode có thể cần:

- **Đọc class file Java 21:** parser phải nhận major version 65 và hiểu các constant pool entry/attribute liên quan.
- **Sinh class file Java 21:** writer phải phát ra class file hợp lệ với version và stack map frame phù hợp.
- **Giữ metadata:** annotation, generic signature, record component, nest host/member, permitted subclasses và debug information không bị mất ngoài ý muốn.
- **Tương thích runtime:** class được sinh phải nạp và liên kết được trên JDK mục tiêu.

Nếu thư viện chỉ đọc class file nhưng không ghi, hoặc chỉ ghi một tập con bytecode, cần kiểm tra rõ giới hạn đó. Không giả định “hỗ trợ Java 21” đồng nghĩa hỗ trợ mọi thao tác transformation.

## 9. Chú ý preview class file

Nếu ứng dụng dùng preview feature của Java 21, compiler cần `--enable-preview --release 21`, và runtime Java 21 cũng phải được khởi chạy với `--enable-preview`.

Class file được tạo từ preview feature có minor version đặc biệt và gắn với release tương ứng. Không nên dùng class file preview làm artifact lâu dài để chạy trên JDK khác release. Với thư viện hoặc bytecode generator, tránh phát sinh preview class file nếu sản phẩm không có chính sách triển khai cố định cùng JDK release.

Nếu không cần preview feature, hãy build với `--release 21` mà không bật `--enable-preview`. Điều này giúp artifact dễ triển khai và kiểm thử trên các runtime tương thích Java 21 hơn.

## 10. Dùng --release 21 đúng mục đích

Khi dùng JDK mới hơn để build ứng dụng nhắm Java 21, ưu tiên:

```bash
javac --release 21 -d build/classes @sources.txt
```

`--release 21` kết hợp source level, target class-file version và tập API Java SE được phép sử dụng cho release 21. Nó giúp phát hiện code vô tình gọi API chỉ xuất hiện ở JDK mới hơn.

Không nên chỉ dùng:

```bash
javac -source 21 -target 21 ...
```

Cặp tùy chọn này không tự giới hạn đầy đủ API platform theo Java 21 như `--release`. Khi dùng JDK 21 trực tiếp, vẫn có thể build bình thường, nhưng `--release` đặc biệt hữu ích khi build trên JDK mới hơn để tạo artifact Java 21.

Lưu ý `--release 21` không kiểm tra bytecode của mọi dependency bên thứ ba và không đảm bảo annotation processor tương thích. Cần kiểm tra riêng processor, plugin và bytecode tool chạy trong môi trường build.

## 11. Rà soát Java agent và Instrumentation

Một số công cụ sinh hoặc sửa bytecode thông qua `java.lang.instrument`, ví dụ profiler, coverage agent, tracing agent hoặc công cụ mock. Khi nâng lên Java 21, xác minh:

- Agent có hỗ trợ class-file version 65 không.
- `ClassFileTransformer` xử lý class loader và module khác nhau đúng cách không.
- Transformation có giữ các attribute cần thiết không.
- Agent có hoạt động với class được load sớm và class được load động không.
- Retransformation/redefinition có tuân thủ giới hạn của JVM không.
- Cấu hình khởi động có dùng `-javaagent` đúng manifest và thứ tự agent không.

Java 21 phát cảnh báo trong một số trường hợp dynamic loading agent nhằm chuẩn bị siết hành vi này trong các release tương lai. Nếu hệ thống cần agent, ưu tiên cấu hình agent ngay khi JVM khởi động bằng `-javaagent` khi có thể và kiểm tra hướng dẫn của JDK runtime triển khai. Không dựa vào cơ chế attach động như một giả định không đổi giữa mọi phiên bản.

## 12. Công cụ hỗ trợ rà soát migration

Một số công cụ có thể phát hiện dependency vào API nội bộ hoặc API đã deprecated:

### 12.1. jdeps

`jdeps` phân tích dependency ở cấp class/package và có thể chỉ ra tham chiếu tới JDK internal API:

```bash
jdeps --jdk-internals --multi-release 21 application.jar
```

Kết quả giúp tìm tham chiếu bytecode trực tiếp tới API nội bộ. Tuy nhiên, `jdeps` không thể phát hiện mọi truy cập reflection được tạo từ tên class/field dạng chuỗi, JNI hoặc hành vi động trong runtime. Cần kết hợp tìm kiếm source, log và integration test.

### 12.2. jdeprscan

`jdeprscan` giúp rà soát việc sử dụng API đã deprecated trong class hoặc JAR:

```bash
jdeprscan --release 21 application.jar
```

Deprecated không đồng nghĩa API đã bị xóa, nhưng kết quả giúp lập kế hoạch thay thế trước khi nâng JDK tiếp theo. Kiểm tra release note và API docs để biết mức độ, phiên bản deprecated và hướng thay thế.

### 12.3. Kiểm tra bytecode và module

```bash
javap -verbose -classpath application.jar com.example.Customer
jar --describe-module --file application.jar
```

`javap` giúp xác nhận class-file version và cấu trúc class; `jar --describe-module` giúp xem module descriptor hoặc trạng thái automatic module. Kết quả này hữu ích khi điều tra lỗi reflection hoặc module resolution.

## 13. Quy trình migration thực tế

Có thể thực hiện theo thứ tự sau:

1. **Lập inventory:** tìm reflection, annotation processor, compiler plugin, bytecode library và agent trong source lẫn dependency.
2. **Quét JDK internals:** chạy `jdeps --jdk-internals`, tìm các cờ `--add-opens`/`--add-exports` và kiểm tra log `InaccessibleObjectException`.
3. **Nâng dependency:** chọn phiên bản framework, processor và bytecode tool công bố hỗ trợ Java 21.
4. **Sửa module access:** dùng API công khai; khai báo `opens` có mục tiêu cho package của ứng dụng khi deep reflection là yêu cầu thực.
5. **Làm rõ annotation processing:** cấu hình processor path/module path và chỉ định processor; bảo đảm build mới hơn JDK 21 vẫn chạy processor theo cấu hình tường minh.
6. **Kiểm tra generated source:** build sạch, xác minh file được sinh đúng, không trùng và compile với `--release 21`.
7. **Kiểm tra bytecode:** xác nhận major version 65 và thử đọc/sinh/nạp class trên JDK 21.
8. **Kiểm thử module và class loader:** chạy integration test theo cấu hình gần production, gồm named module nếu ứng dụng sử dụng JPMS.
9. **Kiểm thử runtime agent:** kiểm tra transformation, startup flags và khả năng tương thích của agent.
10. **Loại bỏ workaround:** xóa cờ mở module hoặc phụ thuộc nội bộ không còn cần thiết sau khi dependency được nâng cấp.

## 14. Ma trận kiểm thử sau migration

| Khu vực | Test cần chạy | Điều kiện đạt |
|---|---|---|
| Reflection public API | Tạo object, gọi method và đọc property | Không phát sinh lỗi truy cập |
| Deep reflection | Serializer/ORM truy cập package đã mở | Chỉ package được phép mới truy cập thành công |
| JPMS | Khởi chạy bằng module path | Module resolve và access đúng thiết kế |
| Annotation processor | Build sạch với processor path rõ ràng | Processor được chạy và generated source đầy đủ |
| JDK mới hơn | Build cùng cấu hình processor trên JDK mới hơn | Không phụ thuộc tự động scan processor |
| Bytecode parser | Đọc class file major 65 | Không lỗi unsupported version hoặc mất metadata |
| Bytecode generator | Sinh class và nạp bằng JVM Java 21 | Class verify, link và thực thi thành công |
| Agent | Chạy với `-javaagent` trên JDK 21 | Transformer không làm hỏng class |
| Dependency scan | Chạy jdeps/jdeprscan | Các cảnh báo được phân loại và có kế hoạch xử lý |

Test trên JDK 21 là bắt buộc nếu Java 21 là runtime mục tiêu. Nếu build cũng cần hỗ trợ JDK mới hơn, thêm job build trên JDK đó để phát hiện thay đổi hành vi compiler, đặc biệt với annotation processing.

## 15. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi `setAccessible(true)` trên package không mở | Strong encapsulation của JPMS | Dùng API công khai hoặc mở đúng package ứng dụng |
| Thêm `--add-opens` cho toàn bộ JDK | Che giấu dependency vào implementation detail | Chỉ mở package cụ thể như workaround có thời hạn |
| Dùng `--illegal-access` | Cơ chế này không còn khôi phục truy cập nội bộ từ JDK 17 | Xóa cờ và sửa dependency |
| Processor chạy trên JDK 21 nhưng mất trên JDK 23+ | Dựa vào automatic discovery mặc định cũ | Khai báo processor/path hoặc `-proc:full` rõ ràng |
| Processor dùng `com.sun.tools.javac.*` | Phụ thuộc implementation nội bộ | Chuyển sang annotation processing/language model API được hỗ trợ |
| Bytecode tool báo major version 65 không hỗ trợ | Parser/generator chưa hiểu class file Java 21 | Nâng bytecode library và plugin |
| Chỉ dùng `-source 21 -target 21` khi build bằng JDK mới | API platform không được giới hạn đầy đủ | Dùng `--release 21` |
| Chỉ test trên classpath trong khi production dùng module path | Không phát hiện lỗi module access | Thêm integration test chạy named module |
| Agent chỉ được attach động sau startup | Hành vi dynamic loading thay đổi theo JDK và có cảnh báo | Ưu tiên cấu hình `-javaagent` lúc khởi động |

## 16. Nguyên tắc áp dụng khi nâng cấp lên Java 21

Khi rà soát reflection, annotation processing và bytecode generation, hãy tập trung vào tính ổn định của API và khả năng tái lập build:

1. Dùng reflection chuẩn và chỉ mở package ứng dụng thật sự cần deep access.
2. Thay truy cập JDK internals bằng API công khai được hỗ trợ.
3. Khai báo annotation processor và dependency build một cách tường minh.
4. Không dựa vào automatic processor discovery vì hành vi javac đã thay đổi ở JDK mới hơn.
5. Nâng parser/generator/agent để hỗ trợ class-file version 65.
6. Dùng `--release 21` khi build artifact nhắm Java 21 trên JDK mới hơn.
7. Kiểm thử cả classpath lẫn module path nếu ứng dụng hỗ trợ hai cách triển khai.
8. Xóa dần workaround `--add-opens` và các tham chiếu internal API sau khi đã nâng dependency.
9. Kiểm tra lại khi đổi JDK vendor, build hoặc major version; không giả định hành vi compiler và module luôn giống nhau.

Một migration hoàn chỉnh không chỉ dừng ở việc ứng dụng khởi động được trên Java 21. Các framework phải truy cập đúng package, processor phải sinh mã ổn định, bytecode tool phải đọc và tạo class hợp lệ, còn build phải tái lập được trên JDK mục tiêu và các JDK mới hơn mà dự án hỗ trợ.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Java Platform Module System](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [Oracle Java SE 21 — AccessibleObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Oracle Java SE 21 — MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Oracle Java SE 21 — Annotation Processing](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html)
- [Oracle Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle Java SE 23 — javac](https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html)
- [Oracle Java SE 21 — jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [Oracle Java SE 21 — jdeprscan](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html)
- [Java Virtual Machine Specification, Java SE 21 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
