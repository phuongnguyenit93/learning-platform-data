# Ghi lại cấu hình thực tế để tái hiện một lần biên dịch Java

## 1. Vì sao “đã build bằng Java 17” chưa đủ?

Một lần biên dịch có thể thành công trên máy A nhưng lỗi trên máy B dù cả hai cùng có source trong một repository. Nguyên nhân thường nằm ở **cấu hình thực tế của compiler**: bản JDK được chọn, release mục tiêu, source path, classpath, annotation processors, encoding, biến môi trường hoặc các file `.class` tồn từ lần build trước.

Câu “dùng Java 17” còn mơ hồ: Java 17 có thể là JDK đang chạy `javac`, mức ngôn ngữ của `--source 17`, định dạng class file của `--target 17`, hoặc tập ngôn ngữ/API Java SE của `--release 17`. Các thông tin này không tương đương.

**Ghi lại cấu hình thực tế** nghĩa là lưu có kiểm chứng trình biên dịch nào đã chạy, nhận những đối số và input nào, trong môi trường nào, và đã tạo ra kết quả gì. Chỉ giữ script hoặc ảnh chụp dòng “BUILD SUCCESSFUL” chưa đủ: script có thể resolve dependencies thay đổi theo thời điểm, IDE/build tool chọn toolchain khác, hoặc task không thực sự chạy vì dùng cache.

Sau bài học, bạn sẽ biết:

1. Những yếu tố tối thiểu cần ghi để tái hiện `javac` trên Java 17+.
2. Cách thu thập chính xác nguồn, tùy chọn, dependencies, môi trường và output.
3. Cách thực hành một lần biên dịch có hồ sơ đủ rõ để replay.
4. Vì sao tái hiện kết quả/chẩn đoán và tạo artifact giống từng byte là hai mục tiêu khác nhau.
5. Cách điều tra những đầu vào ẩn trong Gradle/Maven/IDE và annotation processing.

## 2. Phải xác định mục tiêu tái hiện trước

| Mục tiêu | Cần chứng minh | Bằng chứng cần |
| --- | --- | --- |
| **Replay lời gọi compiler** | Chạy lại cùng compiler với cùng tập nguồn và cấu hình | JDK chính xác, working directory, options, source, classpath, processor, environment |
| **Replay lỗi hoặc hành vi** | Biên dịch lại ra lỗi hoặc chương trình thể hiện cùng hành vi | Dữ liệu trên, exit code, diagnostics, runtime/test script và kết quả |
| **Replay artifact byte-for-byte** | File `.class` hoặc JAR có nội dung giống chính xác | Khóa toàn bộ đầu vào ảnh hưởng output, build sạch, so SHA-256 từng artifact |

Hai file class có hash khác nhau có thể vẫn có ngữ nghĩa tương đương, chẳng hạn khác metadata debug hoặc cách compiler sinh bytecode. Hai file class có cùng hash cũng không bảo đảm chương trình chạy được nếu runtime classpath thiếu thư viện. Vì vậy cần ghi rõ mục tiêu của việc so sánh.

## 3. Cấu hình thực tế gồm những lớp thông tin nào?

### 3.1. Danh tính compiler và toolchain

Luôn ghi **đường dẫn executable** `javac`, phiên bản đầy đủ và bản phân phối JDK; khi điều tra khác biệt do compiler, cần cả build/vendor nếu có. Ghi cách toolchain được chọn từ `PATH`, `JAVA_HOME`, Gradle toolchain, Maven toolchains, IDE hoặc container. Ghi OS/kiến trúc khi chúng tác động đến native component, đường dẫn, filesystem hoặc các bước sinh mã.

```bash
javac -version
java -version
```

`javac -version` và `java -version` là kết quả của **hai executable đang được resolve** trong phiên shell. Đừng giả định chúng chắc chắn thuộc cùng JDK. Xác định vị trí trên Linux/macOS:

```bash
command -v javac
command -v java
```

Trong Windows PowerShell:

```powershell
(Get-Command javac).Source
(Get-Command java).Source
```

Nếu kết quả trỏ vào wrapper hoặc symlink, ghi tiếp đến JDK thực sự đứng sau wrapper khi cần replay chính xác. Có thể lưu thông tin file `release` của JDK hoặc metadata CI/toolchain để nhận diện bản build.

### 3.2. Toàn bộ tùy chọn javac được giải quyết thành giá trị thực

| Nhóm | Ví dụ | Tác động phải ghi |
| --- | --- | --- |
| Quy tắc ngôn ngữ, API, class target | `--release`, `--source`, `--target`, `--enable-preview` | Java source và API nào được chấp nhận, phiên bản class file |
| Cách đọc nguồn | `-encoding UTF-8` | Giải mã byte của source file |
| File được compile | Tên các `.java`, `@argfile`, source được tìm ngầm | Những khai báo nào nằm trong lần biên dịch |
| Tìm kiểu và module | `-cp`, `--source-path`, `--module-path`, `--module-source-path`, `--system` và các cờ module | Compiler có thể nhìn thấy dependency nào |
| Nơi ghi kết quả | `-d`, `-s`, `-h` | Class, generated sources và native headers được tạo ở đâu |
| Annotation processing | `-proc:*`, `-processor`, `--processor-path`, `--processor-module-path`, `-A...` | Processor nào chạy, với tham số và dependency nào |
| Metadata | `-g`, `-g:none`, `-g:lines,vars,source`, `-parameters` | Attributes trong class file |
| Diagnostics | `-Xlint`, `-Werror`, `-implicit` | Warning, điều kiện build fail và classfile cho nguồn ngầm |
| JVM/compiler khác | `-J...`, option không chuẩn khi sử dụng | Hành vi tùy runtime/compiler cụ thể |

**Ghi các đối số thực tế, không chỉ các đối số nhìn thấy trên một dòng lệnh.** `@argfile` có thể chứa các cờ bổ sung. `JDK_JAVAC_OPTIONS` có thể đưa đối số vào lời gọi `javac`. Một IDE hoặc build plugin cũng có thể thêm option khác với file cấu hình do lập trình viên viết.

Khi cần tương thích Java 17 từ compiler mới hơn, `--release 17` là cách rõ ràng để yêu cầu mức ngôn ngữ, class file và Java SE API của bản release đó, trong giới hạn mà JDK đang dùng hỗ trợ. `--release` không được kết hợp với `--source` hoặc `--target`. Việc khóa API nền tảng không khóa các thư viện bên thứ ba: vẫn phải ghi resolved dependency versions.

### 3.3. Đầu vào nguồn thực sự

Phải ghi danh sách file `.java`, nội dung của chúng tại thời điểm compiler đọc, và danh sách các file nguồn được sinh trước/during compilation. Commit Git là mốc hữu ích nhưng chưa bao phủ file chưa commit, generated sources hoặc file nằm ngoài repository.

Với mỗi file quan trọng, hãy tính SHA-256. Ví dụ Linux có `sha256sum`:

```bash
sha256sum src/demo/Main.java src/demo/Message.java
```

Trên Windows PowerShell:

```powershell
Get-FileHash src/demo/Main.java -Algorithm SHA256
Get-FileHash src/demo/Message.java -Algorithm SHA256
```

Lưu **hash thực nhận**; không dùng tên file như một bằng chứng rằng nội dung không đổi. Khi có nhiều nguồn, tạo danh mục với đường dẫn tương đối nhất quán và hash cho từng file. Nếu generator đọc template, schema, resource hoặc biến thời gian, cũng cần ghi những input đó khi chúng tác động đến mã được tạo.

### 3.4. Classpath, module path và binary dependencies

Ghi chính xác **thứ tự và nội dung** các entry trong `-cp`/`--class-path`, đường dẫn JAR/class directory đã resolve, các module trên `--module-path` và tùy chọn liên quan như `--add-reads`, `--add-exports` hoặc `--patch-module` nếu được dùng.

Tên `lib/common.jar` không đủ: một file cùng tên có thể mang byte khác. Ghi tọa độ dependency đã resolve, phiên bản và SHA-256 của từng JAR. Với class directory, ghi danh mục/hash các class files hoặc artifact đã đóng gói tương ứng. Classpath có thứ tự: nếu nhiều vị trí cung cấp cùng tên lớp, thứ tự có thể ảnh hưởng đến kiểu được compiler tìm thấy.

Lưu ý về hệ điều hành: separator của nhiều đường dẫn classpath là `;` trên Windows, `:` trên Linux/macOS. Một script copy nguyên chuỗi classpath giữa hai nền tảng có thể không tương đương.

### 3.5. Môi trường và đầu vào ẩn

Các thông tin cần xét:

- **Working directory** ở đúng thời điểm chạy compiler. Đường dẫn tương đối trên command line và bên trong `@argfile` được giải quyết từ working directory.
- `JAVA_HOME`, `PATH`, `CLASSPATH`, `JDK_JAVAC_OPTIONS`; các tùy chọn JVM/launcher và biến như `JAVA_TOOL_OPTIONS` nếu thực sự áp dụng.
- Encoding mặc định khi không dùng `-encoding`; locale có thể ảnh hưởng thông điệp chẩn đoán; đặc điểm filesystem có thể ảnh hưởng đường dẫn/symlink/case.
- Phiên bản và cấu hình processor, compiler plugin, build tool, daemon, task cache và CI.
- Những file hay dữ liệu bên ngoài mà generator hoặc processor đọc; thời gian/ngẫu nhiên nếu ảnh hưởng output.

Không cần dump bừa mọi biến môi trường. Cần **đủ các biến có thể ảnh hưởng lần compile này** và lưu vào nơi phù hợp; không công khai mật khẩu, token hoặc nội dung nhạy cảm chỉ vì muốn debug.

### 3.6. Kết quả lần gọi

Lưu **exit code**, stdout/stderr, diagnostics, đường dẫn output, danh sách và hash artifacts. Khi cần tái hiện cảnh báo, ghi cả `-Xlint`/`-Werror` và bản JDK; câu chữ, vị trí và định dạng thông báo compiler có thể thay đổi giữa phiên bản hoặc locale.

Quan trọng: `-d out` không đồng nghĩa dọn sạch `out` trước compile. Một lỗi có thể để lại file `.class` cũ hoặc một phần output. Muốn chứng minh artifact do *lần này* sinh ra, hãy build trong thư mục output sạch hoặc ghi trạng thái trước/sau thật rõ.

## 4. Ví dụ runnable: khóa một lần compile Java 17

Dùng hai file nguồn trong dự án không có `module-info.java` và không có dependency bên ngoài:

```text
replay-demo/
├── config/
│   └── javac.args
└── src/
    └── demo/
        ├── Message.java
        └── Main.java
```

File `src/demo/Message.java`:

```java
package demo;

public final class Message {
    private Message() {
    }

    public static String hello(String name) {
        return "Hello, " + name + "!";
    }
}
```

File `src/demo/Main.java`:

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.hello("Linh"));
    }
}
```

File `config/javac.args` chứa **đúng những dòng** sau:

```text
--release
17
-encoding
UTF-8
-proc:none
-g:lines,vars,source
-parameters
-d
build/classes
src/demo/Message.java
src/demo/Main.java
```

Trong `replay-demo`, chạy:

```bash
javac @config/javac.args
java -cp build/classes demo.Main
```

Đầu ra xác định của chương trình:

```text
Hello, Linh!
```

`javac` thường không in gì khi biên dịch thành công. Output dự kiến:

```text
build/classes/
└── demo/
    ├── Main.class
    └── Message.class
```

Giải thích cấu hình:

1. `--release 17` chọn mức ngôn ngữ, class file và API Java SE 17.
2. `-encoding UTF-8` xác định encoding nguồn.
3. `-proc:none` tắt annotation processing để giảm đầu vào ẩn cho bài thực hành; dự án thực tế cần processor thì phải bật và ghi đầy đủ processor.
4. `-g:lines,vars,source` yêu cầu các loại thông tin debug tương ứng. `-parameters` lưu tên tham số cho reflection.
5. `-d build/classes` chọn nơi sinh class file. JDK hiện đại tạo các thư mục output cần thiết nếu chúng chưa tồn tại.
6. Hai file nguồn được chỉ định tường minh nên không cần phụ thuộc vào hành vi tìm file nguồn ngầm.
7. `build/classes` là classpath root khi chạy `demo.Main`; không chạy `java -cp build/classes Main` vì lớp có package `demo`.

File `config/javac.args` được tìm qua đường dẫn ghi sau `@`, nhưng **các đường dẫn bên trong file đó được tính tương đối từ working directory lúc chạy `javac`**, không phải từ thư mục `config`. Vì vậy thay working directory mà không cập nhật đường dẫn có thể khiến replay thất bại.

## 5. Thu thập bản ghi thực tế cho ví dụ

Từ `replay-demo`, lấy bối cảnh và input hashes trước compile. Ví dụ trên Linux có `sha256sum`:

```bash
pwd
command -v javac
command -v java
javac -version
java -version
sha256sum config/javac.args src/demo/Main.java src/demo/Message.java
javac @config/javac.args
sha256sum build/classes/demo/Main.class build/classes/demo/Message.class
java -cp build/classes demo.Main
```

Trên Windows PowerShell:

```powershell
(Get-Location).Path
(Get-Command javac).Source
(Get-Command java).Source
javac -version
java -version
Get-FileHash config/javac.args -Algorithm SHA256
Get-FileHash src/demo/Main.java -Algorithm SHA256
Get-FileHash src/demo/Message.java -Algorithm SHA256
javac '@config/javac.args'
Get-FileHash build/classes/demo/Main.class -Algorithm SHA256
Get-FileHash build/classes/demo/Message.class -Algorithm SHA256
java -cp build/classes demo.Main
```

Các lệnh này minh họa việc **thu thập dữ liệu**, chưa tự động lưu một hồ sơ bền vững; hãy chuyển kết quả thực nhận vào log/artifact của build. Nếu `javac` thất bại, ghi lại mã thoát và diagnostics; dừng thao tác dùng output như một kết quả build mới, vì class cũ có thể còn trong thư mục.

Một hồ sơ có cấu trúc nên lưu:

| Trường | Điều phải điền từ lần chạy |
| --- | --- |
| Mục tiêu | Replay compiler invocation, lỗi/hành vi, hoặc artifact byte-for-byte |
| Toolchain | Đường dẫn và identity `javac`, JDK vendor/version/build |
| Runtime | Đường dẫn và phiên bản `java` dùng khi kiểm thử |
| CWD | Đường dẫn tuyệt đối đến thư mục `replay-demo` |
| Invocation | `javac @config/javac.args` kèm nội dung đầy đủ và hash của argfile |
| Compiler options | `--release 17`, `-encoding UTF-8`, `-proc:none`, `-g:lines,vars,source`, `-parameters`, `-d build/classes` |
| Inputs | Hai file `src/demo/*.java` cùng SHA-256, revision source |
| Dependencies | Java SE API thuộc release 17; không có JAR ngoài nền tảng trong ví dụ |
| Processors | Tắt bằng `-proc:none` |
| Environment | CWD, OS, `PATH`, `JAVA_HOME`, `JDK_JAVAC_OPTIONS` cùng biến liên quan |
| Output state | `build/classes` có được dọn trước compile không |
| Kết quả | Exit code, stdout/stderr, hashes của `Main.class`/`Message.class` |
| Runtime check | `java -cp build/classes demo.Main` in `Hello, Linh!` |

Khi cần kiểm tra lại trong nhiều tháng, lưu bản ghi và checksum cùng phiên bản nguồn/artifact ở nơi có tính bất biến. Dấu thời gian bản ghi giúp truy vết nhưng không thay cho checksums.

## 6. Sự khác nhau giữa cấu hình dự định và cấu hình đã thực sự áp dụng

Hãy phân biệt ba lớp:

```text
Cấu hình khai báo (build.gradle / pom.xml / IDE settings)
    ↓ resolution: toolchain, dependency, source sets, plugins, environment
Cấu hình compiler được task sử dụng (options, sources, classpath, processors)
    ↓ javac invocation/API call hoặc compile task dùng cache
Kết quả thực tế (exit code, diagnostics, .class, generated files)
```

Một file build có thể ghi “Java 17” nhưng Gradle chạy bằng JDK 21 và chọn compiler JDK 21 với `--release 17`. Điều đó **có thể hoàn toàn hợp lệ**, nhưng câu “compiler JDK 17” khi ấy là sai. Maven/IDE cũng có cơ chế chọn compiler khác runtime của IDE hoặc ứng dụng. Muốn replay, ghi phiên bản toolchain **đã resolve**, không chỉ giá trị mong muốn.

Ví dụ Gradle Groovy (đây là **cấu hình build**, không phải mã Java runnable):

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.compilerArgs.add('-parameters')
}
```

Ví dụ này thể hiện JDK compiler được chọn qua toolchain 21, output hướng đến Java 17. Nó **không** tự khóa bản patch/vendor JDK được resolve, dependency JAR, annotation processor hay generated sources. Nếu dùng Gradle/Maven, nên ghi thêm version wrapper/plugin, task thực thi, lockfile hoặc dependency verification, effective compile options và artifact cache information.

**Không phải build tool nào cũng chạy một executable `javac` ngoài tiến trình.** Có thể compiler được gọi bằng Java Compiler API hoặc qua daemon. Đừng tự chế một câu lệnh shell rồi gọi đó là “exact invocation” nếu thực tế tool dùng API; hãy ghi arguments/options, compile tool instance và input theo cách mà hệ thống build cung cấp. Nếu task nhận output từ cache, cần lưu cache key/provenance; không được nói compiler vừa chạy chỉ vì task báo thành công.

## 7. Annotation processing: nguồn biến thiên khó thấy

Annotation processors là chương trình Java chạy trong môi trường compiler. Chúng có thể sinh source, class, resource và diagnostics dựa trên annotations, cấu hình processor, classpath, thời gian, template hoặc file ngoài. Ghi:

- Processor class/version và hashes của JAR chứa processor cùng dependencies.
- `-processor`, `-proc:none`/`-proc:only`/`-proc:full`, `--processor-path`, `--processor-module-path`, `-Akey=value` theo cấu hình thực tế.
- Generated source/class/resource directories và input mà processor đọc.
- Java runtime chạy processor và những biến môi trường có thể tác động.

Đừng suy ra processor chắc chắn đã chạy chỉ vì mã có annotation. Hành vi processor discovery mặc định có thể khác theo JDK/version hoặc build tool. Đặt cấu hình rõ ràng và xác minh log khi cần. `javac` có các tùy chọn chẩn đoán như `-XprintRounds` và `-XprintProcessorInfo` giúp xem hoạt động annotation processing trên toolchain cụ thể.

Nếu muốn tái hiện một lần compile có code generation, không nên đặt `-proc:none` chỉ để “làm build dễ chạy”: điều đó thay đổi bài toán. Tùy chọn này chỉ phù hợp ví dụ không dùng processor ở trên.

## 8. Đầu vào môi trường dễ bị bỏ sót

**`JDK_JAVAC_OPTIONS`:** có thể được thêm vào danh sách compiler arguments; chỉ copy lời gọi `javac @config/javac.args` không bảo đảm nhận đúng cùng options ở máy khác. Ghi giá trị hoặc bảo đảm nó được kiểm soát.

**`CLASSPATH`:** nếu không truyền classpath qua CLI, `javac` có thể dùng biến môi trường này, hoặc current directory nếu nó không được đặt. Khi biên dịch ứng dụng classpath thông thường và không đặt source path, compiler cũng có thể tra nguồn trên user classpath.

**`-d` không tự bổ sung output directory vào compile classpath của dự án không module.** Nếu file đã được biên dịch nằm ở `build/classes` và lần compile mới cần dùng nó, hãy đặt `-cp build/classes` rõ ràng, thay vì suy đoán `-d build/classes` có tác dụng đó.

**Đường dẫn tương đối và hệ điều hành:** thay đổi CWD, sự khác biệt chữ hoa/thường của filesystem hoặc separator classpath có thể làm một lệnh không còn tương đương.

**Generated inputs và phụ thuộc động:** một generator nhúng thời gian/ngẫu nhiên vào source hoặc dependencies có phiên bản SNAPSHOT/dynamic có thể tạo đầu ra khác dù file cấu hình cùng tên. Muốn replay cần lưu byte thực tế hoặc có cơ chế resolve bất biến.

**Bảo mật log:** bản ghi compiler có thể chứa đường dẫn nội bộ, token trong processor options hoặc environment. Lưu thông tin nhạy cảm trong hệ thống bảo vệ phù hợp; bản log chia sẻ công khai chỉ chứa dữ liệu đã được xử lý an toàn và cần nêu rõ những phần bị ẩn khi replay yêu cầu quyền truy cập tương ứng.

## 9. Rebuild sạch và so sánh artifact

Nếu muốn chứng minh hai lần compile sinh class files giống từng byte, phải kiểm soát cả trạng thái output trước mỗi lần. Với ví dụ, hãy chạy hai lần độc lập trong thư mục output sạch; hash file class mới sinh, đối chiếu theo đường dẫn tương đối.

Nếu hash khác, dùng:

```bash
javap -v -classpath build/classes demo.Main
```

`javap -v` hiển thị thông tin class file, constant pool, methods, attributes. Nó giúp tìm khác biệt về debug/parameter metadata và bytecode nhưng không thay thế bản ghi compiler/toolchain. **Một thay đổi hash không nhất thiết là lỗi ngữ nghĩa; một lần compile thành công cũng không bảo đảm tất cả artifact byte-for-byte đồng nhất giữa compiler khác nhau.**

Với JAR còn có bước đóng gói, thứ tự entries, timestamps, manifest và thông tin ký. Tái hiện `.class` và tái hiện JAR là hai yêu cầu liên quan nhưng khác nhau. Đừng kết luận JAR reproducible chỉ vì các class files giống hệt.

Nếu build thất bại, thư mục output có thể chứa class từ lần trước hoặc các file từng được tạo trước khi lỗi xuất hiện. Kiểm tra **exit code** và logs; không chạy file output cũ rồi báo rằng compiler vừa tạo nó thành công.

## 10. Replay lỗi cụ thể: cách điều tra có kiểm soát

Giả sử CI báo `cannot find symbol` nhưng laptop build thành công. Một quy trình điều tra tốt:

1. Lấy log của CI cùng compiler path/version, release, options, cwd, source list, dependency graph, processor configuration và exit code.
2. Cố định commit cộng mọi thay đổi chưa commit, generated sources, JAR hashes và môi trường liên quan.
3. Tái dựng compile ở output sạch, đúng toolchain và options; dùng argfile để tránh sai sót do command line quá dài.
4. Nếu lỗi không xuất hiện, so sánh **đầu vào thực tế** trước khi sửa source: khác release, thứ tự classpath, JAR, file nguồn, processor, environment hay cache.
5. Thay từng yếu tố một để tìm nguyên nhân. Khi lỗi lặp lại, lưu minimal reproducer và hồ sơ đã khóa.

Ví dụ CI dùng `--release 17`, máy local dùng compiler JDK 21 mà không khóa release. Code gọi một API Java SE mới hơn 17 có thể compile trên local nhưng bị từ chối trên CI. Nguyên nhân ở mức API/release, không nhất thiết ở source khác nhau.

Trường hợp khác: cả hai đều dùng `--release 17` nhưng một dependency JAR thay đổi hoặc classpath ordering khác. Hãy kiểm tra resolved dependency list và hashes thay vì chỉ nhìn compiler version.

## 11. Các kết luận sai phổ biến

| Kết luận thiếu cơ sở | Cách kiểm chứng đúng |
| --- | --- |
| “Cả hai dùng Java 17 nên config giống nhau.” | So JDK vendor/build, `--release`/`--source`/`--target` và toàn bộ options |
| “Có `pom.xml` hoặc `build.gradle` là đủ.” | Kiểm tra effective task/compiler options, toolchain, resolved deps, generated sources |
| “Giữ Git commit là giữ mọi source input.” | Kiểm tra uncommitted files, generated source, source ngoài repository và hashes |
| “`@args` lưu hết cấu hình.” | Lưu nội dung argfile, cwd và `JDK_JAVAC_OPTIONS`/wrapper options |
| “Tên JAR và version đủ chứng minh dependency giống nhau.” | Đối chiếu JAR byte hash và classpath/module path có thứ tự |
| “`javac -d out` là build sạch.” | Ghi hoặc kiểm soát trạng thái output trước compile |
| “Thấy `Main.class` sau compile lỗi nghĩa là compile đã thành công.” | Xem exit code, log và artifact tạo mới từ output sạch |
| “Hai file class khác hash nghĩa là Java chạy khác.” | Đối chiếu metadata, bytecode bằng `javap -v` và test chức năng |
| “Task Gradle thành công nghĩa là `javac` đã chạy.” | Kiểm tra task execution/cache evidence và compiler invocation |
| “`--release 17` tự khóa mọi thư viện.” | Khóa riêng JAR/third-party dependency và processor paths |

## 12. Checklist để bàn giao một hồ sơ compile

- [ ] Xác định yêu cầu replay: lệnh, chẩn đoán/hành vi hay artifact byte-for-byte.
- [ ] Ghi đường dẫn `javac`, JDK vendor/version/build và runtime dùng để test.
- [ ] Ghi cwd, OS, cách resolve toolchain và các biến môi trường có ảnh hưởng.
- [ ] Lưu toàn bộ compiler arguments thực tế; giữ nguyên nội dung/hash của `@argfile` nếu dùng.
- [ ] Ghi rõ release/encoding/preview/debug/parameter/warning/processor options.
- [ ] Liệt kê và hash từng source thực tế; chốt commit, uncommitted changes và generated source.
- [ ] Liệt kê resolved binary dependencies, classpath/module path theo thứ tự và checksums.
- [ ] Ghi annotation processors, processor dependencies/options và generated outputs nếu có.
- [ ] Ghi trạng thái output trước compile, exit code, stdout/stderr và danh mục/hash output sau compile.
- [ ] Với replay hành vi, lưu lệnh `java`, runtime classpath và output/test logs.
- [ ] Lưu hồ sơ cùng artifact ở nơi kiểm soát quyền truy cập; không công bố secrets.
- [ ] Chạy lại trong môi trường độc lập và so sánh theo mức tái hiện đã đề ra.

## 13. Bài tập tự kiểm tra và đáp án

**Bài 1.** Hai máy cùng dùng JDK 21; máy A chạy `javac --release 17`, máy B không có release option. Có cùng cấu hình compile không?

**Đáp án:** Không. Máy A bị ràng buộc mức Java SE 17, còn máy B có thể dùng cú pháp/API mới hơn theo mặc định JDK 21. Cần ghi cả JDK compiler và release target.

**Bài 2.** Chạy `javac @config/javac.args` từ thư mục khác rồi lỗi không tìm thấy `src/demo/Main.java`. Vì sao?

**Đáp án:** Đường dẫn file được ghi bên trong argfile được tính tương đối từ working directory của lời gọi `javac`, không từ `config`.

**Bài 3.** Hai file `Main.class` có SHA-256 khác nhau, nhưng chương trình đều in `Hello, Linh!`. Điều này chứng minh gì?

**Đáp án:** Class files không giống byte-for-byte; chưa chứng minh ngữ nghĩa khác nhau. Cần kiểm tra compiler, flags, debug metadata, processors và `javap -v` nếu muốn giải thích.

**Bài 4.** Một CI log chứa `BUILD SUCCESSFUL` nhưng không có task compile chạy do cache hit. Có thể gọi đây là “lần compiler thực sự được gọi” không?

**Đáp án:** Không. Phải ghi nguồn gốc cache/artifact và chứng cứ task execution. Nếu cần replay compile, chạy lại compiler thật với inputs tương ứng.

**Bài 5.** Sau một lần compile thất bại, trong `build/classes` vẫn có `demo/Main.class`. Điều gì còn thiếu để khẳng định class được tạo bởi lần này?

**Đáp án:** Bằng chứng output sạch trước compile, exit code, diagnostics và danh mục/hash artifact sau lần build được kiểm soát.

## 14. Tài liệu tham khảo

- **Oracle JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — `--release`, `-encoding`, `-d`, `-g`, `-parameters`, processor, classpath và argument files.
- **dev.java — Javac, the Compiler:** https://dev.java/learn/jvm/tools/core/javac/ — mô tả compiler, implicit source files, `JDK_JAVAC_OPTIONS`.
- **Java SE 21 Language Specification:** https://docs.oracle.com/javase/specs/jls/se21/html/ — ngữ nghĩa ngôn ngữ, compile-time errors.
- **Java SE 21 Virtual Machine Specification:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — định dạng class file và các ràng buộc JVM.
- **Gradle Toolchains:** https://docs.gradle.org/current/userguide/toolchains.html — chọn JDK thực tế cho compile task.

**Thông điệp thực hành:** một hồ sơ tái hiện có giá trị phải trả lời được *compiler nào chạy, nó nhận những byte đầu vào và tùy chọn nào, trong môi trường nào, và đã tạo ra kết quả nào*. Khi đã khóa những dữ liệu đó, sự khác biệt giữa các lần build mới có cơ sở để điều tra.