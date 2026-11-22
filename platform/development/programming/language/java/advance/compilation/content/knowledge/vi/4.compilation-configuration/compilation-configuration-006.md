# Phân biệt tùy chọn javac với tùy chọn JVM truyền qua -J

Khi biên dịch Java, có **hai tầng cấu hình** dễ bị nhầm lẫn:

- **Tầng trình biên dịch `javac`:** quyết định cách đọc và kiểm tra mã nguồn, tìm phụ thuộc, phát sinh tệp `.class` và lựa chọn phiên bản Java đích. Ví dụ: `-encoding UTF-8`, `-d out`, `--release 17`, `-classpath lib/*`, `-Xlint:all`.
- **Tầng JVM đang chạy chính trình biên dịch:** quyết định cấu hình tiến trình Java thực thi `javac`, chẳng hạn kích thước heap, thuộc tính hệ thống và một số tùy chọn chẩn đoán VM. Khi gọi `javac` qua chương trình launcher dòng lệnh, dùng **tiền tố `-J`** để chuyển một tùy chọn JVM xuống tầng này. Ví dụ: `-J-Xmx512m` hoặc `-J-Dlesson.mode=compile`.

Điểm quan trọng nhất: **JVM chạy trình biên dịch khác về vai trò với JVM sẽ chạy ứng dụng sau khi biên dịch**. `-J-Xmx512m` không tự làm ứng dụng Java sau này được chạy với heap 512 MiB. Tương tự, `--release 17` không thay đổi phiên bản JVM đang chạy `javac`.

Bài học áp dụng chủ yếu cho **lệnh `javac` trong JDK 17+**. Trong IDE, Gradle, Maven hoặc chương trình gọi Java Compiler API, cách thiết lập JVM có thể khác vì trình biên dịch không nhất thiết được khởi chạy bởi một tiến trình `javac` độc lập.

## 1. Sơ đồ đường đi của một lệnh biên dịch

```text
Shell / terminal
  |
  | javac -J-Xmx512m --release 17 -encoding UTF-8 -d out Sample.java
  |
  v
Launcher của javac
  |                                 
  |-- -J-Xmx512m ------------> JVM chạy trình biên dịch
  |                               | heap tối đa 512 MiB
  |                               v
  |                         Mã của javac
  |                               ^
  |-- --release 17 ---------------|
  |-- -encoding UTF-8 ------------| các tùy chọn của compiler
  |-- -d out ---------------------|
  |-- Sample.java ---------------|
                                  |
                                  v
                             out/Sample.class
                                  |
                                  | được chạy ở lệnh sau
                                  v
                         java -cp out Sample
                                  |
                                  v
                           JVM chạy ứng dụng
```

Mũi tên sơ đồ diễn giải **vai trò**, không phải chi tiết nội bộ bắt buộc của mọi implementation. Đặc tả công cụ `javac` của JDK định nghĩa `-Joption` là cách chuyển `option` cho hệ thống runtime Java ở phía compiler.

| Bạn muốn cấu hình | Viết ở đâu? | Ví dụ | Tác động chính |
| --- | --- | --- | --- |
| Thư mục đầu ra | Tùy chọn `javac` | `-d out` | Vị trí tạo class file |
| Phiên bản Java mục tiêu | Tùy chọn `javac` | `--release 17` | Ngôn ngữ, API nền tảng và định dạng class tương ứng |
| Mã hóa của file nguồn | Tùy chọn `javac` | `-encoding UTF-8` | Cách đọc ký tự trong `.java` |
| Cảnh báo của compiler | Tùy chọn `javac` | `-Xlint:deprecation` | Chẩn đoán khi biên dịch |
| Classpath dùng để biên dịch | Tùy chọn `javac` | `-cp libs/example.jar` | Tìm lớp/thư viện theo classpath |
| Heap tối đa của JVM chạy compiler | Tùy chọn JVM qua `-J` | `-J-Xmx512m` | Bộ nhớ heap của tiến trình biên dịch |
| Heap khởi đầu của JVM chạy compiler | Tùy chọn JVM qua `-J` | `-J-Xms128m` | Dung lượng heap khởi đầu của compiler JVM |
| System property cho compiler JVM | Tùy chọn JVM qua `-J` | `-J-Ddemo.mode=compile` | Thuộc tính hệ thống của tiến trình chạy compiler |
| Heap của ứng dụng sau khi build | Tùy chọn lệnh `java` lúc chạy | `java -Xmx512m -cp out Sample` | Heap của JVM chạy ứng dụng |

`-Xlint` và `-Xmx` chỉ giống nhau ở ký tự đầu `-X`: **`-Xlint` do javac hiểu; `-Xmx` là tùy chọn JVM**. Không suy ra đối tượng nhận tham số từ tiền tố `-X` mà phải tra tài liệu của đúng công cụ.

## 2. Cú pháp chuẩn của -J

Dạng tổng quát:

```text
javac -J<tùy-chọn-JVM> <tùy-chọn-javac> <tệp-nguồn>
```

Các lệnh hợp lệ điển hình:

```bash
javac -J-Xmx512m -d out Sample.java
javac -J-Xms128m -J-Xmx512m --release 17 -d out Sample.java
javac -J-Dlesson.mode=compile -encoding UTF-8 -d out Sample.java
```

Trong ba lệnh trên, `Sample.java` là tên file giả định có thật trong thư mục hiện tại. Khi đưa một tùy chọn cho JVM, hãy **ghép sát `-J` với chính tùy chọn đó**, giữ nguyên dấu `-` của tùy chọn JVM:

- `-J-Xmx512m` = truyền `-Xmx512m` cho JVM của compiler.
- `-J-Xms128m` = truyền `-Xms128m` cho JVM của compiler.
- `-J-Dlesson.mode=compile` = truyền `-Dlesson.mode=compile` cho JVM của compiler.
- Nếu cần nhiều tùy chọn JVM, **lặp lại `-J` cho từng tùy chọn**.

Các dạng dễ sai:

```text
javac -Xmx512m Sample.java
javac -J -Xmx512m Sample.java
javac -J-Xmx 512m Sample.java
java -J-Xmx512m -cp out Sample
```

Giải thích:

1. `javac -Xmx512m` đưa `-Xmx512m` trực tiếp cho **compiler**, thường dẫn tới lỗi tùy chọn không hợp lệ; muốn điều chỉnh JVM của compiler thì dùng `-J-Xmx512m`.
2. `-J -Xmx512m` tách `-J` thành một argument riêng. Cú pháp được tài liệu hóa là **`-Joption`**, không có khoảng trắng giữa tiền tố và phần sau.
3. `-J-Xmx 512m` tách giá trị `512m` thành argument khác; kích thước heap phải là một phần của tùy chọn `-Xmx512m`.
4. Lệnh `java` trực tiếp nhận tùy chọn JVM `-Xmx512m`; **không thêm `-J` cho lệnh `java`**.

Khi giá trị có dấu cách, cách escape/quote phụ thuộc shell; tập trung xem argument thực tế shell chuyển cho chương trình. Với ví dụ heap `512m` hoặc property `key=value` không có dấu cách, không cần quote.

## 3. Ví dụ Java 17+ chạy độc lập: compiler property khác runtime property

Tạo tệp `ModeCheck.java` trong một thư mục học tập riêng:

```java
public class ModeCheck {
    public static void main(String[] args) {
        String mode = System.getProperty("lesson.mode", "unset");
        System.out.println("Mode: " + mode);
    }
}
```

Biên dịch và chạy theo thứ tự dưới đây (JDK 17+):

```bash
javac -encoding UTF-8 -J-Dlesson.mode=compile -J-Xmx512m -d out ModeCheck.java
java -cp out ModeCheck
java -Dlesson.mode=run -cp out ModeCheck
```

Trong môi trường bình thường **không có biến hay cấu hình bên ngoài tự đặt `lesson.mode`**, stdout của hai lệnh `java` lần lượt là:

```text
Mode: unset
Mode: run
```

Lệnh `javac` thành công thường **không in dòng nào**; hai dòng trên là output từ **hai lần chạy `java`**, không phải output của `javac`. Lệnh biên dịch tạo `out/ModeCheck.class`; `-d out` cho phép `javac` tạo thư mục đích nếu cần.

Tại sao lần chạy đầu in `unset`?

- `-J-Dlesson.mode=compile` đặt system property **trong JVM chạy `javac`**.
- Mã `ModeCheck.main` **chưa được chạy** trong bước `javac`; giá trị property đó không được ghi tự động vào class file.
- Khi chạy `java -cp out ModeCheck`, một JVM ứng dụng mới được khởi động; nếu không cấu hình property, lời gọi `getProperty(..., "unset")` trả về giá trị mặc định `unset`.
- Chỉ khi chạy `java -Dlesson.mode=run -cp out ModeCheck`, JVM ứng dụng mới có property `lesson.mode=run`.

Đây là **phép thử ranh giới giữa compiler JVM và application JVM**. Nó cho thấy việc cấp thuộc tính khi biên dịch không tự cấp thuộc tính lúc chạy; bản thân output của ứng dụng không phải công cụ đo cấu hình heap của compiler JVM.

### So sánh hai lệnh heap

```bash
javac -J-Xmx512m -d out ModeCheck.java
java -Xmx512m -cp out ModeCheck
```

Ở dòng thứ nhất, `512m` là giới hạn heap của **compiler JVM**. Ở dòng thứ hai, nó là giới hạn heap của **application JVM**. Con số bằng nhau chỉ là trùng hợp do ta chọn, và giới hạn heap **không đồng nghĩa** tiến trình chắc chắn sử dụng chính xác 512 MiB RAM thực hoặc 512 MiB tổng bộ nhớ của process.

Nếu cần chỉ định cả hai, hãy cấu hình **hai lệnh** (hoặc hai phần tương ứng trong build/deployment). Không có tùy chọn nào tự động truyền thiết lập của lệnh trước sang JVM ở lệnh sau.

## 4. Tùy chọn javac: khi nào cần dùng trực tiếp?

Các tham số sau điều khiển **công việc biên dịch**, không cần `-J`:

### -d: nơi tạo class file

```bash
javac -d out ModeCheck.java
```

`out` là **thư mục đầu ra** cho class file. Với lớp trong package, `javac` bố trí các thư mục con theo tên package. `-J-d out` không phải cách sử dụng hợp lệ của `-d`: tiền tố `-J` sẽ chuyển nội dung thành tùy chọn cho JVM, vốn không hiểu chỉ thị output của compiler theo cách đó.

### -encoding: mã hóa nguồn

```bash
javac -encoding UTF-8 -d out ModeCheck.java
```

Tùy chọn này bảo đảm trình biên dịch đọc `.java` theo UTF-8. Đừng nhầm với `-J-Dfile.encoding=UTF-8`: thuộc tính JVM có thể ảnh hưởng đến môi trường thực thi của compiler, nhưng **`-encoding UTF-8` là cấu hình rõ ràng, đúng mục đích cho đầu vào mã nguồn** và ít nhập nhằng hơn.

### --release: phiên bản mục tiêu

```bash
javac --release 17 -d out ModeCheck.java
```

Tùy chọn này ràng buộc mức ngôn ngữ, API chuẩn sẵn có và định dạng class file của bản Java được chỉ định. Với JDK hỗ trợ `--release 17`, đây là cách đúng để tạo class file nhắm đến Java 17. Nó **không khởi chạy JVM Java 17** để biên dịch và không có tác dụng tăng/giảm heap.

Ví dụ:

```bash
javac -J-Xmx512m --release 17 -encoding UTF-8 -d out ModeCheck.java
```

Lệnh này gồm **hai nhóm tham số độc lập**: `-J-Xmx512m` dành cho bộ nhớ compiler JVM; `--release 17`, `-encoding UTF-8` và `-d out` dành cho hoạt động biên dịch.

### -cp / --class-path: thư viện để biên dịch

```bash
javac -cp libs/example.jar -d out ModeCheck.java
```

`libs/example.jar` ở đây chỉ minh họa **đường dẫn tới một JAR thực sự tồn tại** trong dự án. `-cp` chọn những lớp/thư viện mà `javac` dùng khi giải quyết tham chiếu trong mã nguồn. Nó **không cấu hình classpath khởi chạy chính compiler implementation**; JDK còn có các module/cơ chế riêng chứa trình biên dịch. Nếu muốn đổi classpath dùng khi chạy `ModeCheck`, đặt `-cp` trên lệnh `java` sau khi build.

### -Xlint: cảnh báo của compiler

```bash
javac -Xlint:deprecation -d out ModeCheck.java
javac -Xlint:all -d out ModeCheck.java
```

`-Xlint:deprecation` yêu cầu compiler cảnh báo về việc dùng API đã bị deprecated; `-Xlint:all` bật nhóm cảnh báo mà `javac` hỗ trợ. Với `ModeCheck.java` ví dụ, không có lời gọi deprecated nên có thể **không có output cảnh báo**. Không lẫn nó với `-J-Xlog:...` (một dạng cấu hình logging của JVM trên JDK hỗ trợ).

### Cách xem các tùy chọn đúng nguồn

```bash
javac --help
javac -X
java --help
java -X
```

`javac --help` hiển thị các tùy chọn compiler thông thường; `javac -X` cung cấp các tùy chọn compiler nâng cao. Trong khi đó `java --help` hoặc `java -X` mô tả tùy chọn phía Java launcher/JVM. Không lấy tên tùy chọn từ một trang hướng dẫn của JVM rồi truyền thẳng vào `javac` khi chưa kiểm tra có cần `-J` hay không.

## 5. Tùy chọn JVM truyền qua -J: khi nào thực sự hữu ích?

### Tăng hoặc điều chỉnh heap để biên dịch

```bash
javac -J-Xms128m -J-Xmx1g -d out LargeSource.java
```

`-Xms128m` là thiết lập heap khởi đầu; `-Xmx1g` là giới hạn heap tối đa. Mục đích có thể là giải quyết thiếu heap trong một tiến trình `javac` lớn, chạy annotation processor tiêu tốn bộ nhớ hoặc tạo môi trường đo đạc ổn định hơn. Chúng **không** điều chỉnh kích thước của tệp `.class` hay làm mã nguồn hợp lệ hơn.

Đây là cú pháp mẫu; `LargeSource.java` phải là tệp thật nếu muốn chạy. Không mặc định tăng heap sẽ sửa mọi `OutOfMemoryError`: phải xác định lỗi xảy ra ở JVM compiler, daemon build, annotation processor, JVM ứng dụng hay hệ thống ngoài heap trước.

### Đặt system property cho tiến trình compiler

```bash
javac -J-Dbuild.profile=experiment -d out ModeCheck.java
```

JVM đang chạy compiler có property `build.profile=experiment`. Điều này có thể ảnh hưởng đến mã Java **thực thi trong compiler JVM**, chẳng hạn một annotation processor thực sự đọc `System.getProperty("build.profile")`; nó không biến chuỗi `experiment` thành hằng số trong mọi class file được biên dịch.

Nếu một thư viện build/processor đọc một property khác, dùng tên property mà chính thư viện ấy tài liệu hóa. `-D` tùy ý không có công dụng nếu không có mã sử dụng nó.

### Ghi log hoặc chẩn đoán JVM compiler

Ví dụ trên HotSpot và JDK hỗ trợ unified logging:

```bash
javac -J-Xlog:gc=info -J-Xmx512m -d out ModeCheck.java
```

Tùy chọn `-Xlog:gc=info` được gửi đến **JVM chạy compiler**. Tùy hoạt động GC, JVM và cấu hình, có thể có hoặc không có dòng log; nội dung, timestamp và nơi ghi log không phải output cố định của bài thực hành. Nó **không bật GC logging** khi chạy `java -cp out ModeCheck` sau đó.

Các tùy chọn `-X` và `-XX` nâng cao có thể phụ thuộc implementation/version JVM. Chỉ áp dụng lựa chọn được JVM đang dùng hỗ trợ, xem `java -X` và tài liệu phiên bản tương ứng. Cảnh báo hoặc lỗi “Unrecognized VM option” thường xuất hiện trước khi mã nguồn được biên dịch.

### Vì sao không phải lúc nào cũng cần -J?

Các dự án nhỏ biên dịch bình thường với cấu hình JVM mặc định. `-J` chủ yếu hữu ích khi thực sự phải cấu hình **tiến trình biên dịch**: heap, property cho processor/plugin hoặc chẩn đoán VM. Sử dụng nó như thao tác “tối ưu hiệu năng chung” khi không có số liệu có thể khiến cấu hình rối và khó tái lập giữa máy phát triển, IDE và CI.

## 6. Chứng minh property của compiler JVM bằng annotation processor (nâng cao)

Ví dụ `ModeCheck` phía trên chứng minh tính độc lập giữa **property trong lúc biên dịch** và **property khi chạy ứng dụng**. Nếu muốn **quan sát trực tiếp** property được đưa qua `-J` *trong JVM compiler*, có thể viết một annotation processor nhỏ. Phần này dành cho người muốn kiểm chứng bằng code thực thi trong compiler; không cần để sử dụng các tùy chọn thông thường.

Tạo file `CompilerPropertyProbe.java`:

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CompilerPropertyProbe extends AbstractProcessor {
    private boolean reported;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (!reported) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Compiler property: " +
                            System.getProperty("lesson.mode", "unset"));
            reported = true;
        }
        return false;
    }
}
```

Class này không có `main` vì nó là processor được **`javac` gọi trong lúc biên dịch**. `@SupportedAnnotationTypes("*")` cho phép processor được kích hoạt cho các annotation type phù hợp; với `-processor` chỉ định tường minh, processor sẽ được gọi qua các vòng xử lý khi biên dịch tệp ví dụ. Tài liệu của annotation processing quy định cách phát hiện và thực thi processor.

Biên dịch processor trước, sau đó dùng nó để biên dịch `ModeCheck.java`, vẫn với JDK hỗ trợ Java 17:

```bash
javac --release 17 -d processor-out CompilerPropertyProbe.java
javac --release 17 -J-Dlesson.mode=compile \
  -processorpath processor-out \
  -processor CompilerPropertyProbe \
  -d out ModeCheck.java
```

Cú pháp xuống dòng bằng `\` ở cuối dòng áp dụng cho **Bash/zsh**. Trong PowerShell hoặc cmd, viết lệnh `javac` thứ hai **trên một dòng**, không dùng `\` làm ký hiệu nối dòng:

```text
javac --release 17 -J-Dlesson.mode=compile -processorpath processor-out -processor CompilerPropertyProbe -d out ModeCheck.java
```

Trong môi trường đơn giản, chẩn đoán processor gồm dòng:

```text
Note: Compiler property: compile
```

Đây là **diagnostic note do compiler phát ra**, không phải stdout của chương trình `ModeCheck`. Lời gọi `System.getProperty` trong `CompilerPropertyProbe.process` chạy **ngay trong JVM đang chạy compiler** (với `javac` dòng lệnh ở ví dụ), nên nhìn thấy property do `-J-Dlesson.mode=compile` đặt. Nếu bỏ `-J-Dlesson.mode=compile` và không có cấu hình ngoài, note sẽ hiển thị `unset`.

Thử chạy ứng dụng vừa biên dịch:

```bash
java -cp out ModeCheck
```

Stdout vẫn là:

```text
Mode: unset
```

Điều này tách rõ ba lớp: **mã của processor** chạy trong JVM compiler; **bytecode của `ModeCheck`** được phát sinh để lưu; và **`ModeCheck.main`** chạy ở JVM ứng dụng sau đó.

Để tránh cảnh báo nguồn, ví dụ processor dùng `SourceVersion.RELEASE_17` và lệnh biên dịch ứng dụng cũng chỉ định `--release 17`. Khi chuyển sang release mới, cần đánh giá khả năng hỗ trợ source version phù hợp; không ép mọi processor cũ tự động hỗ trợ tất cả release mới.

## 7. Lệnh java -Xmx và javac -J-Xmx khác nhau ra sao?

Giả sử bạn muốn biên dịch bằng heap 1 GiB rồi chạy ứng dụng với heap 256 MiB. Hai lệnh thích hợp là:

```bash
javac -J-Xmx1g -d out ModeCheck.java
java -Xmx256m -cp out ModeCheck
```

| Câu hỏi | Lệnh `javac -J-Xmx1g` | Lệnh `java -Xmx256m` |
| --- | --- | --- |
| Process được cấu hình | Process biên dịch | Process ứng dụng |
| Heap tối đa | 1 GiB cho compiler JVM | 256 MiB cho application JVM |
| Có tạo class file? | Có, nếu biên dịch hợp lệ | Không (chạy class đã có) |
| Có chạy `main` của ứng dụng? | Không | Có |
| Có tự lưu cấu hình heap vào class file? | Không | Không |
| Mục tiêu thường gặp | Biên dịch/processor cần bộ nhớ | Ứng dụng cần giới hạn bộ nhớ khi chạy |

Thao tác `javac -J-Xmx1g` sẽ vô ích nếu lỗi thiếu bộ nhớ xảy ra **khi chạy ứng dụng**; ngược lại, `java -Xmx1g` không làm compiler JVM đã kết thúc được mở rộng heap.

Có thể cấu hình cả hai với các mức khác nhau, vì chúng là **hai process với vòng đời độc lập**. Trên một số công cụ build, cả quá trình biên dịch có thể nằm trong daemon đang chạy thay vì process `javac` riêng; phần sau giải thích điểm này.

## 8. Khi javac được gọi qua API, Gradle, Maven hoặc IDE

Cú pháp `-J...` được định nghĩa cho **launcher của `javac` dòng lệnh**. Java có những API như `javax.tools.JavaCompiler` và `java.util.spi.ToolProvider` cho phép chạy compiler **bên trong một JVM đã có**.

Ví dụ về nguyên tắc, không phải chương trình Java độc lập:

```java
javax.tools.JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();
// compiler.run(...) sử dụng compiler trong JVM đang chạy chương trình gọi.
```

Đoạn trên chỉ minh họa API, chưa tạo tệp nguồn/đích hay gọi `run`; không dùng nó để thử chạy độc lập. Khi compiler được nhúng trong **JVM của công cụ chủ**, các tùy chọn heap và `-D` thường phải cấu hình khi **khởi động JVM chủ**. Không thể giả định một chuỗi `-J-Xmx...` đưa vào danh sách tùy chọn `JavaCompiler` sẽ hoạt động như lệnh `javac`.

Cũng không thể suy từ `java -version` ở terminal rằng IDE hay build tool đang dùng JVM đó. Các trường hợp cần phân biệt:

- **Chạy `javac` bằng terminal:** `javac -J-Xmx...` có nghĩa rõ ràng theo tài liệu launcher.
- **Compiler chạy trong JVM build tool:** heap của JVM build tool có thể là nguồn giới hạn; phải xem cấu hình dành cho chính tiến trình ấy.
- **Build tool fork process compiler:** công cụ build có thể cung cấp trường cấu hình JVM arguments cho process compiler; tên thiết lập và cách truyền phụ thuộc công cụ, không mặc định giống nguyên văn chuỗi dòng lệnh `-J-Xmx...`.
- **IDE:** compiler có thể chạy trong process/daemon riêng. Cấu hình JDK của project, build process memory và runtime application là các phần có thể tách biệt.

Ví dụ với Gradle: JVM chạy Gradle Daemon, Java toolchain được chọn để biên dịch và JVM dùng khi chạy/test có thể khác nhau. Việc tăng `org.gradle.jvmargs` điều chỉnh daemon Gradle theo cấu hình tương ứng, **không mặc nhiên** đồng nghĩa mọi tác vụ biên dịch forked hoặc JVM ứng dụng sẽ nhận cùng heap. Với Maven cũng cần kiểm tra plugin/compiler mode và cấu hình JVM của process thực tế.

**Quy tắc thực hành:** xác định **process nào đang phát sinh lỗi** rồi dùng cấu hình mà process đó hỗ trợ. Tên `javac` trong log build không đủ để kết luận launcher độc lập có nhận `-J` hay compiler được gọi trong process đang chạy.

## 9. Hai cơ chế liên quan dễ nhầm: @argument-file và JDK_JAVAC_OPTIONS

### @argument-file

`javac` hỗ trợ đưa nhiều tùy chọn/tên file nguồn vào argument file, chẳng hạn `compile.args` có nội dung:

```text
--release
17
-encoding
UTF-8
-d
out
ModeCheck.java
```

Sau đó:

```bash
javac @compile.args
```

Tuy nhiên, theo tài liệu `javac`, **các tùy chọn `-J` không được hỗ trợ bên trong argument file** vì chúng phải được xử lý bởi launcher trước phần đọc argument file của compiler. Cách đúng khi cần cả hai là đặt `-J` **ngoài file**:

```bash
javac -J-Xmx512m @compile.args
```

Đừng chuyển `-J-Xmx512m` vào `compile.args` rồi trông đợi nó tương đương. Tính chất này rất quan trọng khi tự tạo script build dài.

### JDK_JAVAC_OPTIONS

Với các JDK hiện đại, biến môi trường `JDK_JAVAC_OPTIONS` có thể cung cấp những đối số mặc định được thêm vào đầu danh sách đối số của `javac` theo quy tắc tách/quote tài liệu hóa. Nó khác `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và `JAVA_HOME`; mỗi biến có phạm vi áp dụng riêng, không nên giả định chúng hoán đổi được.

Ví dụ minh họa trên Bash:

```bash
export JDK_JAVAC_OPTIONS="--release 17 -encoding UTF-8"
javac -d out ModeCheck.java
```

Khi chẩn đoán một lệnh `javac` có behavior bất ngờ, hãy kiểm tra biến này cùng cấu hình build. Đặc biệt, nếu nghi ngờ mục tiêu release bị thay đổi âm thầm, việc một biến mặc định đang cung cấp `--release` có thể giải thích kết quả. Với cấu hình dự án có khả năng tái lập, nên ghi tùy chọn quan trọng rõ ràng trong build/toolchain thay vì chỉ dựa vào môi trường cá nhân.

Không nhầm `JDK_JAVAC_OPTIONS` với cú pháp `-J`: biến môi trường nói về **nguồn cung cấp đối số cho launcher javac**, còn `-J` nói về **đối tượng nhận một tùy chọn JVM**.

## 10. Lỗi thường gặp và cách xác định nguyên nhân

| Biểu hiện | Nguyên nhân có thể | Việc nên kiểm tra |
| --- | --- | --- |
| `invalid flag: -Xmx512m` | Đưa option JVM trực tiếp cho javac | Đổi thành `javac -J-Xmx512m ...` |
| JVM báo `Unrecognized VM option` | Option sau `-J` không được JVM compiler hỗ trợ | Kiểm tra JDK/vendor/version và tài liệu `java` tương ứng |
| Compile bị `OutOfMemoryError: Java heap space` | JVM thực sự chạy compiler/processor thiếu heap | Xác định process và thử cấu hình heap đúng process; đo memory |
| Chạy ứng dụng thiếu heap dù compile có `-J-Xmx1g` | `-J` chỉ áp dụng cho compiler JVM | Cấu hình `java -Xmx...` hoặc runtime của ứng dụng |
| `-J-Dflag=value` nhưng `main` không thấy property | Property được đặt ở compiler JVM | Cấp `-Dflag=value` cho lệnh `java` khi chạy |
| `-J-Xmx...` nằm trong `@args` không hoạt động | Argument file không hỗ trợ `-J` | Đặt `-J` trên command line |
| `--release 17` vẫn chạy trên JDK mới | Nhầm target release với runtime chạy compiler | Xem `javac -version`, class file target và runtime thực |
| Compiler từ IDE/Gradle không nhận `-J` | Có thể dùng API hoặc fork với cấu hình riêng | Kiểm tra compiler invocation mode và JVM args của công cụ |
| Lệnh `javac` báo lỗi dù option đúng | Mã nguồn, classpath, đường dẫn hoặc cấu hình khác có lỗi | Đọc diagnostic cụ thể trước khi chỉnh heap |
| Output compiler có log GC ngoài dự kiến | Có thể do `-J-Xlog:...` hoặc JVM options từ môi trường | Kiểm tra arguments và biến môi trường của compiler JVM |

Một sai lầm phổ biến là gộp tất cả thành “JVM của Java”. Khi debug hãy ghi đầy đủ **JVM của compiler**, **JVM của tool build** (nếu có), **JVM của test/application** và **phiên bản bytecode mục tiêu**; các thành phần có thể độc lập.

## 11. Checklist thực hành và bài tập

### Checklist một lệnh javac có -J

1. Chạy `javac -version` để xác nhận bản compiler định dùng.
2. Xác định **nhiệm vụ cần giải**: đầu ra, encoding, warnings, target release hay heap/property JVM.
3. Xếp từng tùy chọn vào đúng tầng trước khi chạy.
4. Viết `-J-Xmx...`, `-J-D...` liền dấu, lặp lại `-J` nếu có nhiều JVM options.
5. Đặt `--release`, `-d`, `-encoding`, `-cp`, `-Xlint` như các **tùy chọn của compiler**.
6. Biên dịch một tệp nguồn thực; xác minh class file và kết quả exit code.
7. Chạy chương trình bằng lệnh `java` riêng, với JVM options dành cho **ứng dụng** nếu cần.
8. Nếu chạy qua IDE/Gradle/Maven, xác định compiler có được fork hay không và cấu hình JVM của process thực sự.

### Bài tập 1: Phân loại tùy chọn

Cho lệnh:

```bash
javac -J-Xms128m -J-Xmx768m -encoding UTF-8 \
  --release 17 -Xlint:deprecation -d out ModeCheck.java
```

Ở Bash/zsh, `\` nối dòng; Windows PowerShell/cmd nên viết thành một dòng. Hãy tự phân loại:

- **Compiler JVM:** `-J-Xms128m`, `-J-Xmx768m`.
- **Compiler:** `-encoding UTF-8`, `--release 17`, `-Xlint:deprecation`, `-d out` và đầu vào `ModeCheck.java`.
- **Application JVM:** chưa được cấu hình trong lệnh này vì ứng dụng chưa chạy.

### Bài tập 2: Sửa lệnh sai

Người học viết:

```text
javac -Xmx1g --release 17 ModeCheck.java
java -J-Xmx256m ModeCheck
```

Sửa thành:

```bash
javac -J-Xmx1g --release 17 -d out ModeCheck.java
java -Xmx256m -cp out ModeCheck
```

Ở lệnh đầu, `-J-Xmx1g` thuộc compiler JVM. Ở lệnh sau, `-Xmx256m` thuộc application JVM. Thêm `-d out` và `-cp out` để lệnh chạy tìm đúng class file.

### Bài tập 3: Thử nghiệm system property

1. Chạy `javac -J-Dlesson.mode=compile -d out ModeCheck.java`.
2. Chạy `java -cp out ModeCheck` và quan sát `Mode: unset` nếu không có cấu hình property bên ngoài.
3. Chạy `java -Dlesson.mode=run -cp out ModeCheck` và quan sát `Mode: run`.
4. Giải thích tại sao property của compiler không xuất hiện trong JVM ứng dụng.
5. Nếu muốn đo chính property của compiler JVM, dùng `CompilerPropertyProbe` ở phần nâng cao và giải thích vì sao processor thấy `compile`.

### Bài tập 4: Chẩn đoán build thiếu bộ nhớ

Một pipeline báo `OutOfMemoryError` khi **compilation**. Đừng lập tức sửa `java -Xmx` của service. Hãy xác minh compilation chạy ở process nào: `javac` độc lập, Gradle Daemon, forked compiler hay annotation processor. Sau đó chọn đúng nơi đặt JVM arguments, kiểm tra log và số liệu heap, rồi chạy lại cùng điều kiện để xác nhận.

## 12. Ghi nhớ và tài liệu tra cứu

- **`javac` options** như `--release`, `-d`, `-encoding`, `-cp` và `-Xlint` mô tả **việc biên dịch**.
- **`-Joption`** gửi **option của JVM** đến runtime đang chạy **`javac` dòng lệnh**, ví dụ `-J-Xmx512m` hoặc `-J-Dname=value`.
- **`java -Xmx...`** cấu hình **JVM chạy chương trình**; không cần và không được dùng `-J` ở lệnh `java`.
- **`-J` không được đặt trong `@argfile`**, và không thể giả định trình biên dịch gọi trong JVM đã có qua API tiếp nhận cùng cơ chế `-J`.
- **Tăng heap compiler không làm chương trình sau biên dịch có nhiều heap hơn**, còn `--release` thay đổi target của compiler chứ không chọn JVM compiler.

Tài liệu chính thống để đối chiếu với phiên bản đang sử dụng:

1. [Oracle JDK 21 — The javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-Joption`, `--release`, `-d`, `-encoding`, `-Xlint`, `@argument-file` và `JDK_JAVAC_OPTIONS`.
2. [Oracle JDK 21 — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-D` và các tùy chọn VM nâng cao.
3. [Java SE 17 — Java Compiler API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): dùng compiler thông qua API trong một JVM đang chạy.

Khi gặp một tùy chọn chưa rõ, hỏi **“Ai nhận đối số này: javac hay JVM nào?”** rồi kiểm tra hướng dẫn của đúng phiên bản công cụ trước khi thêm nó vào lệnh build.