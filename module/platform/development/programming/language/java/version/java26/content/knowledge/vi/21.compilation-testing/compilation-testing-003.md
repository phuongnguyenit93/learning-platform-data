# Biên dịch ví dụ Java 26 chính thức riêng với preview Java 27

> **Mốc cập nhật: 27-11-2026.** JDK 26 và JDK 27 là hai release riêng. Mã dùng API/ngôn ngữ đã ổn định của Java 26 nên được biên dịch theo baseline Java 26 bằng `--release 26`. Mã dùng preview của Java 27 phải được biên dịch bằng compiler JDK 27 với `--enable-preview --release 27` và chạy bằng runtime JDK 27 có `--enable-preview`. Không trộn hai loại class vào cùng output hoặc artifact phát hành.

## 1. Mục tiêu và nguyên tắc

Một repository học Java 26 có thể chứa nhiều loại ví dụ:

- Ví dụ dùng API ổn định được bổ sung trong Java 26.
- Ví dụ dùng tính năng đã trở thành chính thức ở các release trước và vẫn hoạt động trong Java 26.
- Ví dụ thử nghiệm preview của Java 26.
- Ví dụ preview mới hoặc được preview lại trong Java 27.
- Ví dụ dùng incubator module, nếu module đó có trong JDK mục tiêu.

Các nhóm này có hợp đồng biên dịch và runtime khác nhau. Chỉ thêm cờ `--enable-preview` vào toàn bộ project không phải cách quản lý phù hợp: cờ này bật preview của đúng release JDK đang dùng, đồng thời khiến class file phụ thuộc release đó.

Sau bài này, bạn có thể:

- Phân biệt API/language feature ổn định, preview và incubator.
- Dùng `--release` để khóa cả ngôn ngữ, API nền tảng và bytecode target.
- Biên dịch ví dụ Java 26 ổn định bằng JDK 26 hoặc JDK 27.
- Biên dịch preview Java 27 bằng compiler JDK 27 và chạy với runtime JDK 27.
- Hiểu vì sao preview class file không phải artifact tương thích xuyên release.
- Tách source set, output directory, module và CI job.
- Kiểm tra JDK compiler/runtime thực tế, class-file version và lỗi cấu hình thường gặp.

## 2. Phân biệt ba trạng thái tính năng

| Trạng thái | Ý nghĩa | Cách biên dịch |
|---|---|---|
| Final / stable | Đã trở thành một phần chính thức của Java SE hoặc JDK API. | Không cần `--enable-preview`; chọn baseline bằng `--release`. |
| Preview | Đã hoàn thiện để lấy phản hồi nhưng chưa phải cam kết API/ngôn ngữ vĩnh viễn; có thể thay đổi, preview lại hoặc bị rút. | Dùng compiler của đúng release với `--enable-preview` và `--release` cùng số release; runtime cùng release cũng cần `--enable-preview`. |
| Incubator | API/module thử nghiệm được cung cấp trong một incubator module; module có thể thay đổi hoặc bị loại bỏ. | Ngoài việc chọn release, cần cấu hình module path/`--add-modules` theo tài liệu của module và runtime tương ứng. |

Preview và incubator không phải hai cách gọi cho cùng một trạng thái:

- Preview có thể là language feature, VM feature hoặc preview API trong namespace Java SE.
- Incubator thường được đóng gói trong một module riêng, chẳng hạn `jdk.incubator.*`; module phải được đưa vào graph của ứng dụng.
- Một release có thể có cả preview features và incubator modules.
- Một tính năng preview có thể trở thành stable trong release sau, nhưng mã preview cũ vẫn cần được biên dịch lại theo release mới.

Không dùng số JDK lớn hơn để suy ra một tính năng đã stable. Luôn kiểm tra release notes, JEP và API documentation của release đang nhắm tới.

## 3. Java 26 và Java 27: trạng thái ngôn ngữ cần biết

Java SE 26 không đưa thêm một ngôn ngữ feature mới thành final trong bảng tổng hợp ngôn ngữ. Tính năng ngôn ngữ mới nổi bật của release này là **Primitive Types in Patterns, `instanceof`, and `switch` — JEP 530, fourth preview**.

Java SE 27 tiếp tục preview tính năng này dưới **JEP 532, fifth preview**. Thiết kế có thể được tinh chỉnh giữa hai release. Vì thế:

- Ví dụ dùng cú pháp đã final trong Java 26 có thể biên dịch với `--release 26`.
- Ví dụ dùng primitive type patterns theo JEP 530 phải dùng JDK 26 với preview flags nếu muốn kiểm tra đúng preview của Java 26.
- Ví dụ dùng JEP 532 phải dùng JDK 27 với preview flags.
- Không lấy class file preview của JDK 26 rồi kỳ vọng JDK 27 chạy được chỉ vì tính năng cùng tên vẫn đang preview.

Một số tính năng từng preview trước đây đã trở thành stable, ví dụ module import declarations, compact source files/instance main methods và flexible constructor bodies trong Java 25. Chúng không cần `--enable-preview` khi biên dịch theo Java 26/27. Không nên tiếp tục bật preview chỉ vì một tính năng từng có giai đoạn preview trong lịch sử.

## 4. Vai trò của --release

`javac --release N` chọn đồng thời ba phần:

1. Quy tắc ngôn ngữ Java của release N.
2. Tập API Java SE/JDK được công bố cho release N.
3. Class-file target tương thích với release N.

Đây là lựa chọn nên dùng khi cần một artifact chạy trên một JDK tối thiểu cụ thể.

Ví dụ:

~~~text
javac --release 26 -d out/java26 src/java26/demo/UuidV7Example.java
~~~

Nếu lệnh chạy bằng compiler JDK 27, `--release 26` vẫn yêu cầu compiler kiểm tra code theo ngôn ngữ và API của Java 26. Điều này hữu ích khi build server đã cài JDK 27 nhưng ứng dụng vẫn phải hỗ trợ runtime JDK 26.

### 4.1. Vì sao không chỉ dùng -source và -target?

- `--source 26` chọn cú pháp/ngôn ngữ Java 26.
- `--target 26` chọn class-file target Java 26.
- Hai tùy chọn này riêng lẻ không bảo đảm compiler chỉ nhìn thấy API có trong Java 26.

Ví dụ code có thể biên dịch với JDK 27 vì gọi một API mới của JDK 27, dù class file được tạo ở target cũ. Khi chạy trên JDK 26, ứng dụng có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.

Với JDK 9 trở lên, ưu tiên:

~~~text
javac --release 26 ...
~~~

Không kết hợp `--release` với `--source` hoặc `--target`; javac từ chối tổ hợp này vì `--release` đã bao gồm các thiết lập đó.

### 4.2. Phạm vi của --release

`--release 26` không có nghĩa mọi thư viện bên ngoài cũng tương thích Java 26. Tùy chọn này kiểm tra API nền tảng Java/JDK; dependency bên ngoài vẫn phải được kiểm tra riêng:

- Phiên bản thư viện có hỗ trợ Java 26 không?
- Bytecode của dependency có chạy trên runtime mục tiêu không?
- Dependency có gọi API JDK mới hơn baseline không?
- Có annotation processor, compiler plugin hoặc agent yêu cầu JDK mới hơn không?

`--release` cũng không cho phép dùng các API nội bộ không được công bố cho release đã chọn.

## 5. Ví dụ Java 26 ổn định: UUIDv7

`UUID.ofEpochMillis(long)` là API Java SE có từ Java 26 (`Since: 26`). Đây là ví dụ ổn định để kiểm tra compiler có thực sự dùng API baseline Java 26 hay không.

Tạo file `src/java26/demo/UuidV7Example.java`:

~~~java
package demo;

import java.util.UUID;

public class UuidV7Example {
    public static void main(String[] args) {
        long epochMillis = System.currentTimeMillis();
        UUID id = UUID.ofEpochMillis(epochMillis);

        System.out.println("UUID: " + id);
        System.out.println("Version: " + id.version());
    }
}
~~~

### 5.1. Biên dịch bằng JDK 26

Trong PowerShell:

~~~powershell
$JDK26 = "C:\Java\jdk-26"
& "$JDK26\bin\javac.exe" --release 26 -d out\java26 src\java26\demo\UuidV7Example.java
& "$JDK26\bin\java.exe" -cp out\java26 demo.UuidV7Example
~~~

### 5.2. Biên dịch bằng JDK 27 nhưng giữ baseline Java 26

Đây là trường hợp thường gặp trên CI có JDK mới hơn runtime production:

~~~powershell
$JDK27 = "C:\Java\jdk-27"
& "$JDK27\bin\javac.exe" --release 26 -d out\java26 src\java26\demo\UuidV7Example.java
~~~

Có thể chạy output này bằng Java 26 hoặc Java 27:

~~~powershell
& "$JDK26\bin\java.exe" -cp out\java26 demo.UuidV7Example
& "$JDK27\bin\java.exe" -cp out\java26 demo.UuidV7Example
~~~

Cả hai runtime đều có API `UUID.ofEpochMillis()` và hiểu class-file target Java 26.

### 5.3. Kiểm tra compiler đã chặn API mới hơn

Nếu source gọi một method chỉ có từ Java 27, biên dịch với `--release 26` phải thất bại khi method đó không tồn tại trong API Java 26. Đây là kiểm tra có chủ đích: lỗi compile giúp phát hiện code vô tình phụ thuộc JDK mới hơn baseline.

Không xóa `--release` chỉ để làm cho compilation pass. Hãy quyết định rõ runtime tối thiểu mà ứng dụng phải hỗ trợ rồi điều chỉnh baseline hoặc thay API cho phù hợp.

## 6. Ví dụ preview Java 27: primitive type patterns

JDK 27 tiếp tục preview primitive types trong pattern matching theo JEP 532. Ví dụ dưới đây dùng primitive `double` làm selector của `switch`, và dùng primitive type pattern trong các case có guard.

Tạo file `src/preview27/demo/PrimitivePatternPreview.java`:

~~~java
package demo;

public class PrimitivePatternPreview {
    static String doubleToRating(double rating) {
        return switch (rating) {
            case 0d -> "0 stars";
            case double d when d > 0d && d < 2.5d ->
                    d + " is not good";
            case double d when d >= 2.5d && d < 5d ->
                    d + " is better";
            case 5d -> "5 stars";
            default -> "Invalid rating";
        };
    }

    public static void main(String[] args) {
        System.out.println(doubleToRating(0d));
        System.out.println(doubleToRating(1.5d));
        System.out.println(doubleToRating(4d));
        System.out.println(doubleToRating(5d));
    }
}
~~~

Cú pháp `case double d when ...` thuộc preview của Java 27 trong ví dụ này. Không xóa cờ preview chỉ vì source code trông giống cú pháp Java thông thường.

### 6.1. Biên dịch preview bằng compiler JDK 27

~~~powershell
$JDK27 = "C:\Java\jdk-27"
& "$JDK27\bin\javac.exe" --enable-preview --release 27 -d out\preview27 src\preview27\demo\PrimitivePatternPreview.java
~~~

Dùng đúng `javac` từ JDK 27. Tùy chọn `--enable-preview` chỉ bật preview của release compiler đang cung cấp; nó không có nghĩa “bật tất cả preview của mọi JDK”.

### 6.2. Chạy bằng runtime JDK 27

~~~powershell
& "$JDK27\bin\java.exe" --enable-preview -cp out\preview27 demo.PrimitivePatternPreview
~~~

Phải bật preview cả khi biên dịch lẫn khi chạy. Chỉ bật ở compile time không đủ.

### 6.3. Không dùng compiler JDK 27 để giả lập preview Java 26

Tổ hợp sau không phải cách biên dịch preview Java 26:

~~~text
javac-from-jdk-27 --enable-preview --release 26 ...
~~~

`--enable-preview` gắn với preview của compiler release hiện tại. Nếu cần thử preview JEP 530 của Java 26, dùng `javac` JDK 26 và `java` JDK 26:

~~~powershell
$JDK26 = "C:\Java\jdk-26"
& "$JDK26\bin\javac.exe" --enable-preview --release 26 -d out\preview26 src\preview26\demo\PrimitivePatternPreview.java
& "$JDK26\bin\java.exe" --enable-preview -cp out\preview26 demo.PrimitivePatternPreview
~~~

Đây là một bài thử riêng với ngôn ngữ preview của Java 26. Khi muốn thử lần preview thứ năm của Java 27, hãy biên dịch source theo JDK 27 và kiểm tra lại những thay đổi trong JEP 532.

## 7. Quy tắc tương thích class file

Class file chứa major version và minor version. Mỗi release Java có một major version:

| Java SE | Class-file major version |
|---|---:|
| Java 25 | 69 |
| Java 26 | 70 |
| Java 27 | 71 |

Class file ổn định được biên dịch theo Java 26 thường có version `70.0`. Class file dùng preview Java 27 có version `71.65535`.

Giá trị minor version `65535` đánh dấu class file phụ thuộc preview features của release đó. JVM kiểm tra cả hai phần:

- Runtime phải là đúng release đã định nghĩa preview feature.
- Runtime phải được khởi chạy với `--enable-preview`.

Một class preview Java 27 không thể chạy trên JDK 26 vì major version cao hơn runtime hỗ trợ. Nó cũng không thể mang sang JDK 28 rồi bật preview để chạy; preview class file bị gắn với release đã tạo ra nó.

### 7.1. Dùng javap để kiểm tra

~~~powershell
& "$JDK27\bin\javap.exe" -verbose -classpath out\java26 demo.UuidV7Example | Select-String "major version|minor version"
& "$JDK27\bin\javap.exe" -verbose -classpath out\preview27 demo.PrimitivePatternPreview | Select-String "major version|minor version"
~~~

Kết quả mong đợi:

| Artifact | Major | Minor | Có phụ thuộc preview? |
|---|---:|---:|---|
| `out/java26` | 70 | 0 | Không |
| `out/preview27` | 71 | 65535 | Có, preview Java 27 |

Nếu output không như mong đợi, kiểm tra lại compiler được gọi, `--release`, source set và thư mục output.

## 8. Tách source và output ngay từ đầu

Một cấu trúc đơn giản:

~~~text
project/
  src/
    java26/
      demo/
        UuidV7Example.java
    preview26/
      demo/
        PrimitivePatternPreview.java
    preview27/
      demo/
        PrimitivePatternPreview.java
  out/
    java26/
    preview26/
    preview27/
~~~

Mỗi source set có compiler/runtime và output riêng:

| Source set | Compiler | Compile options | Runtime | Output |
|---|---|---|---|---|
| `java26` | JDK 26 hoặc 27 | `--release 26` | JDK 26+ | `out/java26` |
| `preview26` | JDK 26 | `--enable-preview --release 26` | JDK 26 + `--enable-preview` | `out/preview26` |
| `preview27` | JDK 27 | `--enable-preview --release 27` | JDK 27 + `--enable-preview` | `out/preview27` |

Không compile tất cả source vào cùng một `out/classes`. Điều đó dễ khiến class preview bị đưa vào JAR stable, test task không có cờ runtime hoặc artifact phát hành vô tình phụ thuộc JDK 27.

Nếu preview example cần dùng class stable Java 26, có thể đặt `out/java26` trên classpath khi compile/run preview module. Chiều ngược lại, không để code stable phụ thuộc class preview.

## 9. Kiểm tra đúng JDK đang được sử dụng

Máy phát triển có thể cài nhiều JDK. Lệnh `java` và `javac` được tìm qua `PATH`, nên compiler và runtime có thể không cùng version.

Trong PowerShell:

~~~powershell
where.exe java
where.exe javac
java -version
javac -version
~~~

Các lệnh trên cho biết executable được tìm thấy qua `PATH`, nhưng build script nên dùng toolchain hoặc đường dẫn JDK rõ ràng. Ví dụ:

~~~powershell
$JDK26 = "C:\Java\jdk-26"
$JDK27 = "C:\Java\jdk-27"
& "$JDK26\bin\java.exe" -version
& "$JDK26\bin\javac.exe" -version
& "$JDK27\bin\java.exe" -version
& "$JDK27\bin\javac.exe" -version
~~~

Kiểm tra cả compiler lẫn runtime. Không suy luận phiên bản `javac` từ `java -version`, hoặc ngược lại.

## 10. Quy trình build bằng Maven

Nên đặt ví dụ Java 26 stable và preview Java 27 ở hai Maven module độc lập, ví dụ:

~~~text
examples/
  java26-stable/
    pom.xml
    src/main/java/...
  java27-preview/
    pom.xml
    src/main/java/...
~~~

### 10.1. Module stable Java 26

Cấu hình Maven Compiler Plugin để đặt release 26:

~~~xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Build bằng JDK 26 hoặc JDK 27 đều được, miễn compiler plugin sử dụng compiler tương ứng và target release là 26:

~~~text
mvn -f examples/java26-stable/pom.xml clean verify
~~~

### 10.2. Module preview Java 27

Module preview phải dùng JDK 27 toolchain. Compiler configuration cần:

~~~xml
<configuration>
    <release>27</release>
    <compilerArgs>
        <arg>--enable-preview</arg>
    </compilerArgs>
</configuration>
~~~

Test runtime cũng cần bật preview. Ví dụ với Maven Surefire:

~~~xml
<configuration>
    <argLine>--enable-preview</argLine>
</configuration>
~~~

Cấu hình trên là phần option minh họa; đặt vào đúng `maven-compiler-plugin` và `maven-surefire-plugin` của module. Hãy dùng phiên bản plugin đang hỗ trợ JDK 27 và cấu hình toolchain để Maven không âm thầm dùng một JDK khác.

~~~text
mvn -f examples/java27-preview/pom.xml clean verify
~~~

Không đưa `--enable-preview` vào cấu hình parent POM dùng chung cho module stable. Nếu parent bắt buộc truyền cờ preview cho tất cả module, module stable cũng trở thành phụ thuộc preview không cần thiết.

## 11. Quy trình build bằng Gradle

Hai Gradle subproject giúp tách toolchain, compiler options và test runtime.

### 11.1. Project stable Java 26

Ví dụ Kotlin DSL trong `java26-stable/build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(27))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(26)
}
~~~

Có thể dùng toolchain 26 thay vì 27. Trường hợp dùng JDK 27 compiler nhưng release 26 giúp kiểm tra API compatibility với Java 26.

### 11.2. Project preview Java 27

Ví dụ `java27-preview/build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(27))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
~~~

Trong project preview, cả compile task lẫn test/run task đều phải bật preview. Nếu chỉ cấu hình `JavaCompile`, code có thể compile thành công nhưng test thất bại lúc JVM nạp class.

Cấu hình trên chỉ áp dụng cho project preview. Giữ module stable ở baseline 26 và không thêm preview flag toàn cục vào mọi task.

## 12. Kiểm thử âm để xác nhận ranh giới

Một pipeline tốt không chỉ kiểm tra lệnh đúng chạy thành công mà còn kiểm tra các lệnh sai bị từ chối.

| Ca kiểm thử | Lệnh/điều kiện | Kết quả mong đợi |
|---|---|---|
| Stable Java 26 | JDK 27 `javac --release 26` | Compile thành công nếu source chỉ dùng API Java 26 trở xuống. |
| Gọi API chỉ có ở Java 27 | JDK 27 `javac --release 26` | Compile error vì API không có trong baseline 26. |
| Preview Java 27 thiếu cờ compile | JDK 27 `javac --release 27` | Compile error khi source dùng preview feature. |
| Preview Java 27 đúng cờ | JDK 27 `javac --enable-preview --release 27` | Compile thành công. |
| Preview class chạy không bật preview | JDK 27 `java` | JVM từ chối nạp class preview. |
| Preview class chạy đúng runtime | JDK 27 `java --enable-preview` | Có thể chạy nếu class và dependencies hợp lệ. |
| Preview Java 27 trên JDK 26 | JDK 26 runtime | `UnsupportedClassVersionError`. |
| Preview Java 26 trên JDK 27 | JDK 27 runtime | Không tương thích release preview; phải biên dịch lại source theo preview JDK 27. |
| Stable Java 26 trên JDK 27 | JDK 27 runtime | Chạy được nếu không phụ thuộc API ngoài baseline. |
| Stable Java 26 trên JDK 26 | JDK 26 runtime | Chạy được nếu dependency cũng tương thích. |

### 12.1. Các lỗi thường gặp

**`error: preview features are not enabled`**

Source đang dùng preview nhưng compiler không được bật `--enable-preview`. Kiểm tra release và compiler trước khi thêm cờ.

**`--enable-preview must be used with either -source or --release`**

Cần chỉ định source/release tương ứng. Với JDK 27, dùng `--enable-preview --release 27`.

**`invalid source release: 27` hoặc release không được hỗ trợ**

Compiler đang chạy không phải JDK 27 hoặc release đó không được compiler hỗ trợ. Kiểm tra đường dẫn `javac` và toolchain.

**`class file has wrong version` / `UnsupportedClassVersionError`**

Runtime quá cũ so với class-file major version, hoặc preview class được chạy ở release không đúng. Kiểm tra bằng `javap -verbose` và chọn đúng runtime.

**`NoSuchMethodError` hoặc `NoClassDefFoundError` khi chạy Java 26**

Có thể đã compile bằng API JDK 27 mà không khóa `--release 26`, hoặc dependency yêu cầu API mới hơn runtime. Compile lại theo release đúng và kiểm tra dependency.

**Test compile pass nhưng test runtime fail**

Build chỉ bật preview cho compiler. Thêm `--enable-preview` cho test JVM/JavaExec task của module preview.

**Stable JAR chạy được trên máy dev nhưng lỗi ở production**

Máy dev có thể chạy JDK 27 trong khi production là JDK 26; compiler không khóa API baseline hoặc JAR vô tình chứa class preview. Kiểm tra release, dependency và nội dung artifact.

## 13. Checklist cho CI/CD

- [ ] Ghi rõ JDK compiler và runtime cho từng source set.
- [ ] Stable Java 26 dùng `--release 26`.
- [ ] Preview Java 27 dùng JDK 27 compiler với `--enable-preview --release 27`.
- [ ] Preview Java 27 runtime cũng dùng JDK 27 với `--enable-preview`.
- [ ] Preview Java 26 (nếu còn kiểm tra) dùng riêng JDK 26 và `--release 26`.
- [ ] Tách output directory và artifact stable/preview.
- [ ] Không đưa class preview vào JAR production stable.
- [ ] Không dùng `--source`/`--target` thay cho `--release` khi cần khóa API.
- [ ] Kiểm tra `java -version` và `javac -version` từ toolchain thực tế.
- [ ] Kiểm tra class-file major/minor bằng `javap -verbose`.
- [ ] Test negative cases cho preview flags và runtime sai release.
- [ ] Kiểm tra dependency, annotation processor và plugin có tương thích runtime mục tiêu.
- [ ] Recompile preview source theo release mới khi JEP được preview lại.
- [ ] Không bật preview toàn cục cho module stable.
- [ ] Lưu log build có compiler version, release flag và runtime version.

## 14. Bài tập thực hành

1. Tạo project stable Java 26 và thêm ví dụ `UUID.ofEpochMillis()`.
2. Biên dịch bằng JDK 26 với `--release 26`, sau đó chạy bằng JDK 26.
3. Dùng JDK 27 compiler biên dịch cùng source với `--release 26`.
4. Chạy class stable được tạo bởi JDK 27 compiler trên JDK 26.
5. Dùng `javap -verbose` xác nhận class-file major version 70 và minor version 0.
6. Tạo project preview Java 27 với JEP 532 primitive patterns.
7. Biên dịch bằng JDK 27 với `--enable-preview --release 27`.
8. Chạy trên JDK 27 với `--enable-preview`.
9. Thử chạy preview class mà không bật cờ; ghi lại lỗi.
10. Thử chạy preview class trên JDK 26; giải thích lỗi version.
11. Dùng `javap -verbose` xác nhận class-file major 71 và minor 65535.
12. Tạo một source gọi API Java 27 rồi thử compile với `--release 26`; giải thích vì sao compiler phải từ chối.
13. Tạo source preview Java 26 riêng và biên dịch bằng JDK 26; so sánh với source preview Java 27.
14. Cấu hình hai Maven module hoặc Gradle subproject với toolchain và runtime flags độc lập.
15. Tạo CI job stable và preview riêng; đảm bảo artifact preview không được publish cùng artifact stable.

Bảng ghi kết quả:

| Artifact | Compiler | Compile flags | Runtime | Runtime flags | Kết quả |
|---|---|---|---|---|---|
| Java 26 stable | JDK 26 | `--release 26` | JDK 26 | Không | |
| Java 26 stable | JDK 27 | `--release 26` | JDK 26 | Không | |
| Java 26 stable | JDK 27 | `--release 26` | JDK 27 | Không | |
| Java 27 preview | JDK 27 | `--enable-preview --release 27` | JDK 27 | `--enable-preview` | |
| Java 27 preview | JDK 27 | `--enable-preview --release 27` | JDK 27 | Không | Phải bị từ chối |
| Java 27 preview | JDK 27 | `--enable-preview --release 27` | JDK 26 | `--enable-preview` | Phải bị từ chối |

## 15. Quy tắc chọn cấu hình

| Mục tiêu | Cấu hình nên chọn |
|---|---|
| Thư viện/ứng dụng production hỗ trợ Java 26 | `javac --release 26`, không bật preview. |
| Chạy source Java 26 bằng JDK 27 | `javac` JDK 27 + `--release 26`; runtime Java 26 hoặc mới hơn. |
| Thử JEP 530 preview Java 26 | Compiler và runtime JDK 26; bật preview ở cả hai. |
| Thử JEP 532 preview Java 27 | Compiler và runtime JDK 27; bật preview ở cả hai. |
| Dùng incubator module | Theo module name, module path và `--add-modules` của đúng JDK; tách khỏi artifact stable. |
| Nâng preview sang release tiếp theo | Đọc JEP mới, cập nhật source nếu cần, biên dịch lại bằng JDK mới và chạy test mới. |

Preview là công cụ thử nghiệm và phản hồi thiết kế. Nếu ứng dụng production cần một hành vi lâu dài, ưu tiên API/language feature đã final. Khi phải thử preview, cô lập module và artifact, ghim toolchain/runtime đúng release, đồng thời có kế hoạch loại bỏ hoặc chuyển đổi khi feature thay đổi.

## Tài liệu tham khảo chính thức

- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Preview Features — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [Java Language Changes Summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-summary.html)
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [Primitive Types in Patterns, instanceof, and switch — JEP 530 / Java SE 26](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [Primitive Types in Patterns, instanceof, and switch — JEP 532 / Java SE 27](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html)
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [UUID API — Java SE 26, UUID.ofEpochMillis (Since 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html)
- [JVM Specification — Java SE 27, Preview class-file restrictions and version numbers](https://download.java.net/java/early_access/jdk27/docs/specs/jvms/jvms-1.html)
- [JEP 12: Preview Language and VM Features](https://openjdk.org/jeps/12)

