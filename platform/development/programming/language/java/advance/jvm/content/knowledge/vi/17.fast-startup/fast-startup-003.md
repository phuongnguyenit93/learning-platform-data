# AppCDS, archive tĩnh và archive động trong HotSpot Java 17

**AppCDS (Application Class-Data Sharing)** là một cơ chế của HotSpot JVM giúp **tái sử dụng dữ liệu lớp đã được chuẩn bị ở định dạng phù hợp để nạp nhanh** qua một file **CDS archive**. Nó mở rộng ý tưởng **CDS (Class Data Sharing)** từ các lớp thư viện nền tảng sang cả các lớp mà ứng dụng/thư viện dùng. Với Java 17, có hai cách chính để tạo archive riêng cho ứng dụng:

- **Archive tĩnh (static archive):** chạy thử ứng dụng để thu thập danh sách lớp, sau đó dùng **`-Xshare:dump`**, `-XX:SharedClassListFile` và `-XX:SharedArchiveFile` để sinh archive.
- **Archive động (dynamic archive):** chạy ứng dụng có **`-XX:ArchiveClassesAtExit=<file.jsa>`**; lúc thoát, VM tạo một archive bổ sung phía trên **base archive**. Lần chạy tiếp theo chỉ định `-XX:SharedArchiveFile=<dynamic.jsa>` để sử dụng lại.

Mục tiêu của AppCDS là cải thiện **startup time** và có thể giảm **memory footprint** khi nhiều JVM processes dùng cùng archive; nó **không phải** công cụ biên dịch toàn bộ Java source sang native executable, không phải cache kết quả tính toán nghiệp vụ và không bảo đảm mọi class trong ứng dụng đều được archive.

Bài nằm trong chủ đề **Khởi động nhanh**, tập trung HotSpot/JDK **17**. Bạn sẽ hiểu bản chất class metadata, sự khác biệt của static/dynamic archive, cách tạo JAR để chạy thử, quy trình dump/use/verify, các ràng buộc về class path, JDK build, base archive, hiệu năng thực tế và những lỗi triển khai thường gặp. Các chương trình ví dụ dùng Java 17 với stdout xác định; thông điệp từ CDS logging **không được trình bày như stdout cố định**.

## 1. Tại sao class loading ảnh hưởng startup?

Khi khởi chạy ứng dụng Java, JVM cần tìm và nạp các lớp cần thiết; tùy trường hợp nó còn thực hiện những bước như đọc class files, giải mã cấu trúc class, verification, linking và initialization. Trong ứng dụng có nhiều dependencies, các thao tác với JAR files và metadata của hàng nghìn lớp có thể đóng góp đáng kể vào thời gian trước khi chức năng đầu tiên sẵn sàng phục vụ.

```text
Thông thường:
  JAR / JDK runtime image
      │
      ▼
  Tìm bytes cho class
      │
      ▼
  Load / verify / link theo cơ chế của JVM
      │
      ▼
  Runtime class metadata và execution

Với CDS/AppCDS (mô hình khái niệm):
  CDS archive đã chuẩn bị
      │ map các vùng dữ liệu phù hợp
      ▼
  Một phần metadata có thể được tái sử dụng nhanh hơn
      │
      ▼
  Runtime class vẫn phải tuân thủ Java semantics
```

CDS giảm một phần công việc khởi động nhờ dữ liệu có định dạng HotSpot dễ dùng và cơ chế **memory mapping**. Nó **không bỏ qua mọi bước của Java class life cycle**; những kiểm tra và hoạt động phải xảy ra khi runtime thực sự sử dụng lớp vẫn phải đảm bảo tính đúng đắn.

### 1.1. CDS khác AppCDS thế nào?

| Khái niệm | Nội dung chính | Mục đích |
| --- | --- | --- |
| **CDS mặc định** | Một bộ lớp nền tảng được JDK đóng gói sẵn hoặc đã tạo archive | Tăng tốc các JVM process kể cả khi chưa cấu hình ứng dụng |
| **AppCDS** | Mở rộng việc archive sang lớp ứng dụng và thư viện phù hợp | Giảm phần startup work riêng của ứng dụng |
| **Static CDS archive** | File được xây trong một bước dump rõ ràng, có thể dùng class list | Kiểm soát tập lớp được chuẩn bị |
| **Dynamic CDS archive** | File bổ sung được ghi vào cuối một lần chạy hoặc bằng hỗ trợ runtime | Ít bước hơn, dựa trên các lớp đã thực sự được nạp |
| **Base archive** | Archive được map trước, thường là default CDS archive của JDK | Là nền để dynamic archive tham chiếu |
| **Top-layer dynamic archive** | Chứa lớp bổ sung chưa có ở base archive | Mở rộng base mà không cần ghi lại toàn bộ lớp nền |

Trong Java 17, các thuật ngữ **static** và **dynamic** chủ yếu nói tới **cách/lớp archive được tạo, sử dụng và xếp chồng**. “Dynamic” không có nghĩa file archive tự động cập nhật liên tục mỗi khi class mới được load trong tất cả các lần chạy.

### 1.2. CDS archive không phải heap dump

File `.jsa` là một file lưu **dữ liệu phù hợp với cơ chế class data sharing của HotSpot**, không phải:

- `.hprof` heap dump chứa các Java objects đang sống.
- `.class` do `javac` sinh trực tiếp.
- JAR/WAR đóng gói toàn bộ bytecode và resources.
- Native executable như kết quả của một native-image build.
- JIT profile dump hoặc bộ mã máy đã C2 compile để tái dùng một cách phổ quát.

**Archive không thay thế JAR gốc.** Khi chạy, ứng dụng vẫn cần đúng class path/module path, tài nguyên, cấu hình và bytecode có thể được kiểm tra phù hợp theo quy tắc CDS.

## 2. Cơ chế memory mapping và tiết kiệm bộ nhớ

Khi JVM khởi động và chấp nhận một CDS archive, nó có thể **memory-map** các vùng dữ liệu đã chuẩn bị. Các phần read-only có thể được hệ điều hành chia sẻ dưới dạng physical pages giữa nhiều JVM processes trên cùng host.

```text
             CDS archive trên đĩa
                    │
          ┌─────────┼─────────┐
          │         │         │
          ▼         ▼         ▼
      JVM proc A  JVM proc B  JVM proc C
          │         │         │
          └── mapped read-only pages ──┘
                 có thể chia sẻ vật lý
```

**Hai lợi ích tiềm năng:**

1. **Startup:** giảm chi phí phải tự đọc/chuẩn bị lại một phần class metadata trong từng process.
2. **Footprint tổng:** nhiều JVM có thể sử dụng chung một số trang memory-mapped, giảm memory riêng của từng process khi so với việc mỗi process phải tự tạo dữ liệu tương tự.

Tuy vậy:

- **Không phải toàn bộ archive đều là các trang read-only chia sẻ hoàn hảo.**
- `RSS` của từng process có thể tính shared pages, nên **cộng RSS của nhiều JVM dễ đếm trùng**; dùng PSS/USS và OS-specific tools khi đánh giá tổng memory vật lý.
- Archive cũng chiếm dung lượng disk và có metadata overhead.
- Không có công thức bảo đảm “có 10 JVM thì giảm RAM đúng 10 lần”.
- Phần tiết kiệm phụ thuộc số lớp thực được share, lượng metadata, JDK, OS và startup behavior.

### 2.1. Tại sao không archive mọi class có sẵn?

Một archive bao gồm class metadata trong định dạng đã chuẩn bị, có thể lớn hơn dữ liệu bytecode trong JAR hoặc runtime image. Oracle lưu ý lưu trữ CDS classes ở định dạng tối ưu có thể tốn dung lượng nhiều lần so với class files gốc. Archive cả các lớp ứng dụng không bao giờ cần có thể lãng phí disk và thời gian build.

Vì vậy cần phân biệt **classes hiện diện trên classpath** với **classes thực sự được tải ở những code paths cần tối ưu**. Nếu chỉ chạy startup tối thiểu để tạo archive, những classes được nạp muộn bởi request đầu tiên có thể chưa nằm trong archive.

## 3. Default CDS archive của JDK 17

Các bản phân phối JDK hiện đại thường cung cấp một **default CDS archive** cùng JDK, thường là file `classes.jsa` trong thư mục runtime của HotSpot; Oracle java command documentation nêu các vị trí tương ứng tùy hệ điều hành.

```text
Linux/macOS, ví dụ:
  $JAVA_HOME/lib/server/classes.jsa

Windows, ví dụ:
  %JAVA_HOME%\bin\server\classes.jsa
```

**Đừng dùng đường dẫn ví dụ làm giả định bắt buộc cho mọi vendor/build.** Có bản phân phối đóng gói khác, đường dẫn có thể thay đổi và archive mặc định có thể vắng mặt.

Từ JDK 12, default CDS archive được đóng gói trong nhiều bản JDK phổ biến. Ở JDK 17, cơ chế này thường **đã bật theo chế độ tự động** khi JVM có archive thích hợp; bạn không cần tự chạy `-Xshare:dump` chỉ để dùng một default archive đã sẵn có.

### 3.1. Kiểm tra với các chế độ `-Xshare`

| Tùy chọn | Ý nghĩa | Dùng khi nào? |
| --- | --- | --- |
| `-Xshare:auto` | Cố dùng CDS nếu có thể; không bắt buộc thành công | Phù hợp chạy ứng dụng thông thường |
| `-Xshare:off` | Tắt sử dụng shared archive | Baseline so sánh hoặc thu thập class list |
| `-Xshare:on` | Yêu cầu CDS phải sử dụng được; không được thì JVM có thể lỗi khởi động | Chỉ dùng trong kiểm thử xác nhận archive |
| `-Xshare:dump` | Chế độ tạo static archive | Bước dump, không chạy main ứng dụng theo nghĩa thông thường |

**Cảnh báo:** Oracle khuyến nghị tránh dùng `-Xshare:on` trong production vì nó có thể khiến JVM không khởi động khi archive không tương thích hoặc cấu hình đổi. `auto` là hành vi thân thiện hơn đối với môi trường có điều kiện runtime khác nhau.

## 4. Static archive: quy trình thử chạy → class list → dump → reuse

**Static AppCDS archive** là file được sinh trong một **bước dump riêng biệt** dựa trên class list và những yếu tố đầu vào đã chuẩn bị.

```text
            appcds-demo.jar
                   │
          1. Trial application run
          -Xshare:off
          -XX:DumpLoadedClassList=app.classlist
                   │
                   ▼
             app.classlist
                   │
          2. Explicit static dump
          -Xshare:dump
          -XX:SharedClassListFile=app.classlist
          -XX:SharedArchiveFile=app-static.jsa
                   │
                   ▼
             app-static.jsa
                   │
          3. App runtime
          -XX:SharedArchiveFile=app-static.jsa
                   │
                   ▼
           startup có thể nhanh hơn
```

**Lợi thế:** quy trình có thể được đặt thành build/release step có đầu vào xác định, thuận tiện theo dõi class list, archive và các chính sách deployment.

**Chi phí:** phải có bước trial run tạo class list và bước dump riêng; có ràng buộc chặt chẽ hơn với class path/JAR files. Những lớp nạp ngoài đường thử có thể không được hưởng lợi.

### 4.1. `DumpLoadedClassList` làm gì?

Khi chạy với:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
  -cp appcds-demo.jar AppCdsDemo
```

JVM thực thi chương trình để thu thập **danh sách classes được nạp**. File `app.classlist` là input cho bước dump tiếp theo; nó **không phải archive chứa lớp đã tối ưu**.

Đừng thay ý nghĩa `-XX:DumpLoadedClassList` bằng “ghi mọi class file trong tất cả JAR” — danh sách phản ánh những classes được nạp trong lần trial run và điều kiện runtime, không phải toàn bộ classpath.

### 4.2. `SharedClassListFile` và `SharedArchiveFile`

Bước dump:

```bash
java -Xshare:dump \
  -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar
```

- `-Xshare:dump` yêu cầu VM tạo archive.
- `SharedClassListFile` đưa danh sách lớp đã quan sát vào bước dump.
- `SharedArchiveFile` đặt tên file archive đầu ra.
- `-cp appcds-demo.jar` xác định classpath phù hợp để dump.
- Đây **không** phải lệnh chạy `AppCdsDemo.main()` lần thứ hai; không cần main class ở cuối.

**Quan trọng Java 17:** Theo Oracle launcher documentation, khi làm static archive với application classes, **classpath tại giai đoạn minh họa này chỉ chứa JAR files**. Tránh dùng một folder `out/` hay `target/classes` có classes unpacked thay cho JAR; các lớp nằm trong non-empty directories trên classpath là nguồn lỗi/không được archive theo các ràng buộc CDS tương ứng.

### 4.3. `SharedArchiveFile` trong runtime

Để dùng static archive:

```bash
java -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Ứng dụng vẫn chạy `AppCdsDemo.main()` bình thường. Nếu archive hợp lệ và đủ điều kiện được dùng, một số class metadata được nạp từ shared archive thay vì mọi thứ lại được chuẩn bị từ nguồn gốc theo đường không CDS.

Không suy “thành công với exit code 0” đồng nghĩa 100% ứng dụng classes đã được share; phải bật logging và kiểm tra class sources.

## 5. Dynamic archive: ghi lớp bổ sung khi ứng dụng thoát

**Dynamic CDS archive** được giới thiệu để làm AppCDS dễ dùng hơn: chạy ứng dụng **một lần** với `-XX:ArchiveClassesAtExit=<file.jsa>`, HotSpot thu thập đủ thông tin cho archive từ các classes được tải trong quá trình chạy, rồi ghi **top-layer archive** khi ứng dụng kết thúc và thực hiện dump.

```text
              default base CDS archive
                       │
                       │ JVM chạy AppCdsDemo
                       ▼
       java -XX:ArchiveClassesAtExit=app-dynamic.jsa
                 -cp appcds-demo.jar AppCdsDemo
                       │
                 Runtime class loading
                       │
                 JVM shutdown / archive dump
                       ▼
                 app-dynamic.jsa
            (lớp bổ sung so với base archive)
                       │
                       ▼
         lần chạy kế tiếp -XX:SharedArchiveFile
                       │
                       ▼
                   Reuse base + top
```

Lệnh tạo:

```bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Lệnh dùng archive:

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Với default base archive, HotSpot có thể lấy thông tin nền từ header của dynamic archive để map lại base phù hợp, nên runtime không nhất thiết phải viết tường minh `base.jsa:app-dynamic.jsa`.

### 5.1. “Dynamic” có phải archive tự cập nhật trong lúc JVM đang chạy?

Không theo cách hiểu phổ thông đó. Với `ArchiveClassesAtExit`:

1. Trong lúc JVM chạy, nó nạp các classes theo workload.
2. Lúc kết thúc theo cơ chế dump được hỗ trợ, VM **tạo file archive**.
3. **Lần chạy sau** mới sử dụng file vừa tạo.

File không phải “một lớp caching được tự động rewrite sau mỗi lần nạp class” trong một tiến trình đang chạy. Nếu deployment thay classes/JARs, archive cũ có thể không còn dùng được và cần tái tạo.

### 5.2. Vì sao dynamic archive vẫn cần base?

JDK đã có nhiều lớp nền tảng ở default CDS archive. Dynamic archive **không cần sao chép lại toàn bộ các lớp ấy**, mà bổ sung lớp ứng dụng/thư viện chưa có trong base. Điều này tiết kiệm dung lượng và giúp quá trình tạo đơn giản hơn.

Nếu default base không có hoặc không tương thích với cấu hình muốn dump, lệnh dynamic dump có thể không thành công. Phải kiểm tra log chứ không coi mọi lỗi dynamic archive là “không có quyền ghi file”.

### 5.3. Lỗi dễ mắc: lệnh tạo archive và lệnh dùng archive khác nhau

| Tùy chọn | Pha | Kết quả |
| --- | --- | --- |
| `-XX:ArchiveClassesAtExit=app-dynamic.jsa` | Chạy mẫu/dump động | Yêu cầu **tạo** archive khi ứng dụng thoát |
| `-XX:SharedArchiveFile=app-dynamic.jsa` | Run tái sử dụng | Yêu cầu **dùng** archive đã có |
| `-XX:DumpLoadedClassList=app.classlist` | Trial run cho static | **Chỉ** tạo danh sách lớp |
| `-Xshare:dump` + `SharedClassListFile` | Static dump | Tạo **static archive** |
| `-Xshare:off` | Baseline | Tắt dùng archive |

Không dùng `ArchiveClassesAtExit` thay `SharedArchiveFile` rồi trông đợi startup nhanh ngay trong chính lần chạy đang tạo archive.

## 6. Hai lớp archive: static base và dynamic top

HotSpot Java 17 hỗ trợ một base archive và một top-layer dynamic archive khi cấu hình theo cơ chế ứng dụng. Oracle nêu dạng tổng quát:

```text
-XX:SharedArchiveFile=<static_archive>:<dynamic_archive>
```

**Trên Windows, dấu phân tách là chấm phẩy `;` thay vì dấu hai chấm `:`.** Đường dẫn trong option cần được quote phù hợp với shell nếu chứa space/ký tự đặc biệt.

Ví dụ POSIX, khi một base riêng tên `base.jsa` đã được xây:

```bash
# Tạo dynamic archive phía trên base tự tạo:
java -XX:SharedArchiveFile=base.jsa \
  -XX:ArchiveClassesAtExit=top.jsa \
  -cp appcds-demo.jar AppCdsDemo

# Sử dụng tường minh cả base và top:
java -XX:SharedArchiveFile=base.jsa:top.jsa \
  -cp appcds-demo.jar AppCdsDemo

# Nếu dynamic archive header lưu thông tin base thích hợp:
java -XX:SharedArchiveFile=top.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

**Thứ tự có ý nghĩa:** base được map trước, top bổ sung sau. Nhưng cần phân biệt “base archive” và “top archive” với “archive tĩnh/dynamic được tạo ở thời điểm nào”; hai cái tên mô tả **vai trò trong cấu trúc archive**, không phải một hệ thống hai tầng cache tùy ý hỗ trợ ghép vô hạn files.

### 6.1. Điều gì xảy ra nếu class ở cả hai tầng?

Dynamic archive chủ yếu chứa những classes chưa có trong base, vì mục tiêu tránh lặp class metadata không cần thiết. Không nên hình dung user tự hợp nhất hai file `.jsa` theo byte concatenation; **định dạng archives và metadata quan hệ giữa hai tầng thuộc VM**.

Nếu base archive thay bằng file không phù hợp, top có thể không được map; không cố giải quyết bằng cách copy/move tự do rồi bỏ qua dependency checks.

### 6.2. Cần khớp phiên bản JDK và build

CDS archives là **HotSpot VM implementation artifacts**, không phải Java SE portable serialization format. Chúng phụ thuộc vào JDK build, VM settings, class metadata layout và các thành phần khác. Đừng xây trên JDK 17.0.x của vendor A rồi mặc định dùng được trên JDK 17.0.y của vendor B; thậm chí cập nhật patch/build có thể yêu cầu tạo lại archive.

**Quy tắc deployment an toàn:** sinh archive bằng đúng JDK image/VM build sẽ dùng để chạy ứng dụng trong cùng release artifact. Khi nâng JDK, classpath hoặc application JAR, **tái tạo archives và verify**.

## 7. Java 17 lab: chương trình độc lập và JAR đúng để archive

Lưu file **`AppCdsDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public final class AppCdsDemo {
    static final class Formatter {
        String upper(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    static final class Counter {
        int lengthSum(List<String> inputs) {
            int sum = 0;
            for (String input : inputs) {
                sum += input.length();
            }
            return sum;
        }
    }

    public static void main(String[] args) {
        List<String> data = List.of("alpha", "beta", "gamma");
        Formatter formatter = new Formatter();
        Counter counter = new Counter();

        System.out.println("records=" + data.size());
        System.out.println("lengthSum=" + counter.lengthSum(data));
        System.out.println("first=" + formatter.upper(data.get(0)));
        System.out.println("done");
    }
}
```

**Compile và đóng gói trên JDK 17:**

```bash
mkdir -p out
javac --release 17 -d out AppCdsDemo.java
jar --create --file appcds-demo.jar --main-class AppCdsDemo -C out .
```

Lệnh trên dùng shell POSIX, tạo file JAR từ class files đã compile. `jar` là công cụ đi kèm JDK. Một file JAR có `Main-Class` manifest phù hợp có thể chạy bằng `java -jar appcds-demo.jar`, nhưng để đối chiếu cờ CDS ở bài này ta thống nhất **`-cp appcds-demo.jar AppCdsDemo`** ở mọi pha.

**Baseline không bật logging:**

```bash
java -cp appcds-demo.jar AppCdsDemo
```

**Stdout ứng dụng chính xác trên Java 17:**

```text
records=3
lengthSum=14
first=ALPHA
done
```

`"alpha"` dài 5, `"beta"` dài 4, `"gamma"` dài 5 nên `lengthSum=14`. `Locale.ROOT` giữ quy tắc biến đổi chữ hoa ổn định, tránh phụ thuộc locale của máy. `Formatter` và `Counter` là inner classes riêng, được đóng vào JAR cùng main class.

### 7.1. Tại sao phải tạo JAR thay vì chạy `java -cp out AppCdsDemo`?

Đối với **static AppCDS archive** trên JDK 17, Oracle java launcher documentation yêu cầu classpath trong ví dụ tạo archive chứa **chỉ JAR files**, không phải non-empty directories của application classes. Dùng một JAR thống nhất cho cả trial run, dump và runtime giúp:

- Khớp classpath nhất quán.
- Tránh sai lệch vị trí classes.
- Giảm rủi ro archive bị từ chối do classes nằm trong directory.
- Có artifact rõ ràng để đưa vào CI/CD.

Lệnh `java -cp out AppCdsDemo` vẫn là một cách chạy class file bình thường ngoài quy trình AppCDS lab, nhưng **không chọn làm đường dẫn chính trong bước dump** ở đây.

### 7.2. “Chương trình chạy ra đúng stdout” chưa chứng minh AppCDS hoạt động

Cả ba kiểu run sau có thể cho **cùng 4 dòng stdout ứng dụng**:

```bash
java -Xshare:off -cp appcds-demo.jar AppCdsDemo
java -cp appcds-demo.jar AppCdsDemo
java -XX:SharedArchiveFile=app-static.jsa -cp appcds-demo.jar AppCdsDemo
```

Dòng cuối yêu cầu `app-static.jsa` đã được tạo hợp lệ. Startup thời gian thực và class load sources có thể khác, nhưng **Java semantics không được thay đổi** vì archive. Phải bật CDS/class-load logging để xác minh archives.

## 8. Lab A — tạo và dùng static archive trong Java 17

**Bước 1 — Trial run thu thập class list:**

```bash
java -Xshare:off \
  -XX:DumpLoadedClassList=app.classlist \
  -cp appcds-demo.jar AppCdsDemo
```

Nếu thành công, ứng dụng in 4 dòng như baseline và VM tạo file `app.classlist`. Đừng kỳ vọng file class list là Java code hoặc binary `.jsa`.

**Bước 2 — Dump static archive:**

```bash
java -Xshare:dump \
  -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar
```

Đây là bước tạo `app-static.jsa`, thường in các log/diagnostics của HotSpot; **không in 4 dòng nghiệp vụ từ `AppCdsDemo.main()`** vì đây không phải một application execution bình thường.

**Bước 3 — Chạy lại với archive:**

```bash
java -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Dòng nghiệp vụ vẫn:

```text
records=3
lengthSum=14
first=ALPHA
done
```

**Bước 4 — Xác thực class được nạp từ archive:**

```bash
java -XX:SharedArchiveFile=app-static.jsa \
  -Xlog:cds=info,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Trong log HotSpot phù hợp, một class được nạp từ shared archive có thể báo nguồn tương đương **`source: shared objects file`**. Đó là chỉ dấu class đó có thể dùng dữ liệu CDS. Ngược lại, một class báo `source: file:/.../appcds-demo.jar` thường được nạp từ JAR ở lần ấy, không chứng minh toàn bộ archive thất bại.

**Không dùng một dòng log giả định làm bằng chứng** đã thấy `AppCdsDemo` chính xác từ CDS trong mọi môi trường. Hãy lọc theo tên class/GC/VM build và quan sát log thật.

### 8.1. Nếu class list ghi quá ít lớp?

Trial run chỉ nạp các classes mà chương trình thực sự động đến. Nếu một framework có lazy initialization, plugins, reflection hoặc các request paths chưa được chạy trong trial, class list có thể không chứa chúng.

Cần xây **warm-up scenario đủ đại diện**: khởi chạy components muốn tối ưu, thực hiện representative requests, sau đó shutdown sạch để dùng cùng artifact. Không giả định “mở app vài giây thì mọi class trong JAR đã được archive”.

### 8.2. Nếu archive tĩnh tạo thành công nhưng app không dùng?

Kiểm tra:

- Runtime có thật sự chỉ định `-XX:SharedArchiveFile=app-static.jsa` không?
- Có đang dùng JDK build đã tạo archive không?
- JAR có bị rebuild/thay đổi bytecode/timestamps liên quan checks không?
- Runtime `-cp` có đúng path và thứ tự so với dump không?
- Có options làm disable CDS, ví dụ `-Xshare:off`?
- Log `-Xlog:cds=debug` báo vì sao archive bị từ chối?
- Nếu lỗi do application classes ở non-empty directories, dùng packaged JAR thay vì exploded folder.

## 9. Lab B — tạo và dùng dynamic archive trong Java 17

Dynamic dump đơn giản hơn vì **không cần tạo class list trước**.

**Bước 1 — Chạy ứng dụng đồng thời yêu cầu dump khi thoát:**

```bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Program stdout:

```text
records=3
lengthSum=14
first=ALPHA
done
```

Sau khi JVM hoàn tất và dynamic dump thành công, file `app-dynamic.jsa` được tạo. Việc ghi archive ở cuối ứng dụng có thể làm **lần chạy tạo archive chậm hơn**, đặc biệt lúc shutdown; đây là công việc chuẩn bị cho những lần khởi động sau, **không phải một tối ưu làm chính lần dump chạy nhanh hơn**.

**Bước 2 — Chạy lại bằng dynamic archive:**

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Startup được phép dùng **default static base archive + dynamic top archive**. Ứng dụng phải có cùng semantics và stdout.

**Bước 3 — Kiểm chứng CDS/class loading:**

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:cds=info,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Đọc log để phân biệt lớp từ base/archive với những lớp còn được nạp trực tiếp từ JAR/runtime image. Một dynamic archive không nhất thiết chứa tất cả loaded classes; còn có điều kiện về loại class loader, archive eligibility và consistency checks.

### 9.1. Dynamic archive không nhất thiết ghi được khi ứng dụng chết bất thường

`ArchiveClassesAtExit` cần JVM thực hiện quá trình dump khi kết thúc phù hợp. Nếu process bị `SIGKILL`, crash native, container hard kill hoặc OS cắt tài nguyên, không bảo đảm archive được tạo đầy đủ.

Trong CI, **kiểm tra process exit code, file tồn tại, kích thước hợp lý và lần chạy lại có log chứng minh sử dụng được archive**. Đừng để pipeline chỉ làm `test -f app-dynamic.jsa` rồi tuyên bố đủ điều kiện production.

### 9.2. Dynamic archive không phải “không cần JAR nữa”

Dù archive đã có, runtime vẫn cần đúng JAR/classpath/resources. Archive không đóng gói arbitrary resources, service provider configuration, native libraries, network endpoints, TLS materials hoặc dữ liệu ứng dụng.

Nếu build lại `appcds-demo.jar` làm thay đổi binary, archive có thể bị từ chối; phải tái tạo archive khi packaging thay đổi.

## 10. Bảng so sánh static và dynamic archive

| Tiêu chí | Static archive | Dynamic archive |
| --- | --- | --- |
| Cách tạo chủ yếu | Trial run + tạo class list + `-Xshare:dump` | Một run với `-XX:ArchiveClassesAtExit` |
| File class list trung gian | **Có** theo quy trình phổ biến | **Không cần** |
| Có chạy main khi dump? | Bước trial run **có**, bước dump **không** | Run tạo archive **có** |
| Quan hệ với base | Có thể đóng vai trò archive chính/base | Thường là top-layer phía trên base |
| Số bước chuẩn bị | Nhiều hơn | Ít hơn |
| Nội dung classes | Dựa vào danh sách đã quan sát và eligibility | Những loaded classes eligible chưa có trong base |
| Dung lượng | Có thể lớn hơn vì nhiều dữ liệu nền | Thường gọn hơn vì chỉ ghi lớp bổ sung |
| Đối tượng dùng | Controlled release/build pipeline, cần custom base | Nhanh để enable AppCDS hoặc thu từ runtime |
| Khi runtime | `-XX:SharedArchiveFile=static.jsa` | `-XX:SharedArchiveFile=dynamic.jsa` hoặc `base:dynamic` |
| Hạn chế | Classpath/JDK/archive compatibility và các rules CDS | **Cũng** phụ thuộc base/JDK/classpath, exit/dump thành công |
| Có đảm bảo tất cả classes? | **Không** | **Không** |
| Có đảm bảo startup nhanh hơn? | **Không** | **Không** |

**Câu nhớ:** Static: **class list rồi dump**. Dynamic: **chạy app rồi dump lúc kết thúc**. Cả hai: **re-use qua `SharedArchiveFile`**, kết quả Java-level không đổi.

## 11. Lệnh `jcmd VM.cds` trong Java 17

Oracle JDK 17 launcher manual nêu có thể tạo CDS archive từ **JVM đang chạy** qua `jcmd <pid> VM.cds ...`, giảm việc phải thay startup script. Đây là kỹ thuật nâng cao hữu ích khi hệ thống phức tạp.

Mẫu lệnh, thay `<pid>` bằng PID thật:

```bash
# Tạo static CDS archive từ JVM đang chạy khi môi trường hỗ trợ:
jcmd <pid> VM.cds static_dump live-static.jsa

# Tạo dynamic archive từ JVM đã bật recording khi startup:
jcmd <pid> VM.cds dynamic_dump live-dynamic.jsa
```

Để hỗ trợ **dynamic_dump** theo Oracle Java 17 documentation, JVM đích cần được khởi động với:

```bash
java -XX:+RecordDynamicDumpInfo \
  -cp appcds-demo.jar AppCdsDemo
```

Lưu ý: `AppCdsDemo` kết thúc rất nhanh nên **không phù hợp để bạn kịp lấy PID và chạy jcmd**. Ví dụ `jcmd` ở đây nhằm giải thích cú pháp cho một **service sống đủ lâu**, không cam kết bạn có thể attach vào demo ngắn.

### 11.1. `jcmd` cần điều kiện vận hành

Việc attach cần đúng process, quyền OS/owner, JDK tooling tương ứng, hỗ trợ của HotSpot và môi trường cho phép attach. Container security policies, disable-attach flag hoặc process kết thúc sớm có thể khiến lệnh không chạy được.

Không dùng `jcmd VM.cds dynamic_dump` như một lệnh Java source hoặc một API Java SE chuẩn trong ứng dụng. Đây là diagnostic command của HotSpot/JDK tools.

### 11.2. Chọn giữa dump-at-exit và `jcmd`

- Nếu kiểm soát script và có một đường warm-up + shutdown tự nhiên, `ArchiveClassesAtExit` thường đơn giản.
- Nếu app/server đang chạy với trạng thái đã warm-up và có thể attach hợp lệ, `jcmd` có thể lấy class data sau khi traffic đại diện diễn ra.
- Với static archive muốn kiểm soát, class list + explicit dump dễ đưa vào pipeline dạng deterministic steps.

Đừng gọi `jcmd` ở production dưới tải cao mà không đo resource impact/overhead và có chiến lược rollback.

## 12. Giới hạn classpath và module path trên Java 17

### 12.1. Non-empty directories trên classpath có vấn đề

Oracle Java 17 CDS documentation quy định các ràng buộc với `-classpath`/`-Xbootclasspath/a` và module path. Trong các quy trình AppCDS archive, **non-empty directories** là nguồn không tương thích; để archive application classes đáng tin, hãy **đóng gói dưới dạng JAR**.

Ví dụ **không khuyến nghị** dùng làm cách tạo static archive của bài:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
  -cp out AppCdsDemo
```

Lệnh này có thể chạy Java source đã biên dịch ở dạng exploded class files, nhưng không đáp ứng điều kiện “classpath chỉ chứa JARs” cho static AppCDS archive ở bước dump theo Oracle example.

**Đừng hiểu lệnh `java -cp out ...` là không bao giờ chạy:** nó chạy như một Java application bình thường. Hạn chế ở đây là **CDS archiving/sharing eligibility**, không phải Java launcher cấm thư mục.

### 12.2. Module path và modular JARs

Với `--module-path`, CDS hỗ trợ những trường hợp **modular JAR** phù hợp; exploded modules/non-empty directories trên module path có thể bị hạn chế theo Oracle docs.

Không suy việc ứng dụng chạy được ở module path đồng nghĩa lớp từ module đã chắc chắn được archive. Cần kiểm chứng thực tế trong logs và đảm bảo module configuration hợp lệ.

### 12.3. Phải nhất quán classpath lúc dump và lúc runtime

Theo Oracle JDK 17 launcher docs:

- **Classpath tại lúc tạo archive** phải **bằng hoặc là prefix của runtime classpath**, theo các quy tắc CDS tương ứng.
- Thứ tự các JAR có ý nghĩa trong việc phân giải classes.
- Nếu JAR files trên classpath hoặc module path bị **sửa đổi sau khi archive tạo**, archive không được sử dụng theo kiểm tra integrity/compatibility.
- Một số startup options như `--upgrade-module-path`, `--patch-module` và `--limit-modules` có thể khiến CDS bị disable.

Đừng chỉ so tổng số JAR hoặc thư mục: cần đúng nội dung, thứ tự/path và VM config phù hợp. Một đường dẫn symbolic link hoặc relative path thay đổi cũng có thể khiến deployment khó debug; dùng reproducible packaging/paths và verify.

### 12.4. Fat JAR, nested JAR và custom class loaders

Frameworks dùng executable/fat JAR và nested library JARs có **class loader behavior khác** với ví dụ `-cp appcds-demo.jar`. Việc hỗ trợ AppCDS cho classes do custom loaders nạp có các điều kiện/giới hạn riêng; không khẳng định “mọi lớp Spring Boot nested jar đều được archive tự động như classpath flat jar”.

Khi ứng dụng dùng custom class loader:

1. Kiểm tra JDK 17 và framework phiên bản thực tế.
2. Quan sát class loading sources bằng `-Xlog:class+load=info`.
3. Xác định classes nào đến từ archive, classes nào nạp từ loader path khác.
4. Chọn static/dynamic dump quy trình phù hợp với cách loader nhận bytecode và package artifacts.
5. Không dùng archive của một build rồi thay fat jar của build khác mà không tái tạo.

## 13. Archive compatibility: JDK, classpath, cấu hình JVM

CDS không phải một định dạng “write once, run anywhere” độc lập với JVM. Một archive có thể bị từ chối trong các trường hợp:

- JDK vendor/build/patch khác với nơi tạo archive.
- Classpath JARs được rebuild, sửa hoặc sắp xếp không tương thích.
- Application JAR đã đổi path/content sau dump.
- Dynamic top được tạo phía trên base archive không còn phù hợp.
- Một số VM options/GC/platform settings ảnh hưởng archive layout hoặc eligibility.
- Trình chạy đang dùng `-Xshare:off`.
- Runtime bị giới hạn filesystem permissions/memory mapping theo môi trường.
- Archive file bị thiếu, corrupt hoặc incomplete.
- Module configuration khác hoặc options disable CDS.

**Hệ quả thực tế:** tạo archive như một **artifact gắn với JDK image và application build**. Khi thay một trong hai, hãy regenerate + rerun validation, không tái dùng mù quáng file `.jsa` cũ.

### 13.1. Không nên tự sửa file `.jsa`

File archive có cấu trúc binary nội bộ của HotSpot, không phải text template. Không dùng text editor để đổi danh sách classes trong archive hoặc nối hai archives bằng `cat`. Muốn thay classes, hãy chạy lại dump với đầu vào đúng.

### 13.2. Nếu archive không hợp lệ thì JVM xử lý thế nào?

Hành vi phụ thuộc `-Xshare` mode, loại lỗi và HotSpot configuration:

- Với chế độ tự động, VM có thể bỏ qua archive không dùng được và tiếp tục chạy không CDS trong nhiều tình huống.
- Với `-Xshare:on`, việc không thể dùng archive thường được xem là lỗi khởi động.
- Nếu đang chạy chính bước dump tạo archive, lỗi có thể khiến lệnh dump thất bại và không tạo file đầy đủ.

Không khẳng định mọi lỗi CDS đều silently fallback; **đọc exit code và `-Xlog:cds` của run thực tế**.

## 14. Verify archive thay vì đoán từ tên file

Chạy:

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:cds=info,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Các dấu hiệu cần tìm (tùy bản HotSpot):

- Log cho thấy archive tương ứng được mở/map thành công.
- Thông tin một hoặc nhiều classes được load từ **shared objects file**.
- Không có diagnostic thông báo archive bị bỏ qua hoặc invalid.
- Java program in chính xác 4 dòng nghiệp vụ như baseline.
- Exit code 0 và không có `LinkageError`/lỗi truy cập resources liên quan.

### 14.1. Ba tình huống và cách diễn giải

| Log quan sát | Có thể kết luận | Chưa được kết luận |
| --- | --- | --- |
| `class+load` cho một JDK class `source: shared objects file` | Có một lớp nền đã được share | Toàn bộ application classes nằm trong AppCDS |
| `class+load` cho `AppCdsDemo` `source: shared objects file` | Lớp ứng dụng ấy thực sự nạp từ archive trong run này | Mọi lớp trong mọi dependencies đều đã được archive |
| Log báo archive không tương thích hoặc bỏ qua | Run không sử dụng được archive như kỳ vọng | Java program phải sai logic hoặc chậm bao nhiêu ms |
| `-Xshare:off` và class load từ JAR | Chế độ so sánh không dùng CDS | Chứng minh archive không có giá trị trên mode khác |

### 14.2. Đường đọc log theo `GC ID` có liên quan không?

GC logs như `-Xlog:gc*=info` **không phải công cụ xác minh CDS trực tiếp**. CDS tập trung vào **class loading/startup metadata**; muốn biết classes có dùng archive, xem tags `cds` và `class+load`. GC metrics có thể hữu ích để so memory/overall performance, nhưng không thay thông tin nguồn nạp lớp.

### 14.3. `-Xlog:cds=debug` khi cần chi tiết

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:cds=debug,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Debug logs có thể chứa thông tin layout/mapping/checks; output khác giữa JDK builds. Trên production, giới hạn logging volume. Không ghi nguyên một bộ debug log làm “kết quả tất định” của demo vì timestamps, addresses, số classes và VM choices khác nhau.

## 15. Đo hiệu năng AppCDS đúng cách

**AppCDS là tối ưu cho startup và footprint**, không phải bằng chứng chương trình nghiệp vụ chạy nhanh hơn mọi tác vụ.

### 15.1. Định nghĩa start-up metric

Có ít nhất ba cách thường dùng:

- **Process launch → first application log:** dễ đo nhưng có thể chưa bao gồm tất cả khởi tạo.
- **Process launch → HTTP server ready:** phù hợp service thực, cần readiness probe đáng tin.
- **Process launch → first successful business response:** bao gồm lần chạm đầu tới những lazy paths và upstream dependencies.

Phải dùng **cùng định nghĩa** khi so `-Xshare:off`, default CDS và AppCDS. Nếu chạy demo đơn giản, có thể đo wall time command process, nhưng application quá nhanh khiến OS/JIT/terminal noise lớn so với chênh lệch AppCDS.

### 15.2. Ba cấu hình so sánh

```bash
# Baseline hoàn toàn không dùng CDS:
java -Xshare:off -cp appcds-demo.jar AppCdsDemo

# Dùng default CDS khi có thể:
java -Xshare:auto -cp appcds-demo.jar AppCdsDemo

# Dùng custom dynamic archive:
java -Xshare:auto \
  -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

**Chỉ so tốc độ sau khi xác minh archive thứ ba thực sự được dùng.** Nếu custom archive không được dùng và JVM fallback, bạn đang so hai cấu hình CDS mặc định, không phải AppCDS.

Có thể thêm static archive vào bài đo như cấu hình thứ tư. Cố định JDK image, classpath, heap/GC settings, workload, host và warm-up page cache tương đương.

### 15.3. Warm OS page cache có thể ảnh hưởng kết quả

Một lệnh chạy lần đầu có thể đọc JARs/archive từ storage chưa cached; những lần chạy sau có page cache ấm. Nếu luôn chạy “no CDS” trước và “AppCDS” sau, kết quả có thể thiên lệch vì hệ điều hành đã cache file.

Nên xen kẽ thứ tự test runs, chạy nhiều lần, báo **median/p95/min/max**, cùng tình trạng resource contention. Chỉ ghi nhận lợi ích có thể lặp lại trên phần cứng và deployment mục tiêu.

### 15.4. Phân biệt startup time với throughput

Một web app khởi động nhanh hơn 200 ms chưa chắc throughput req/s cao hơn sau warm-up. JIT compilation, database latency, lock contention và GC behavior quyết định steady-state throughput.

Không tuyên bố AppCDS giúp C2 bỏ profiling, inline tất cả methods hoặc thay toàn bộ JIT compilation. AppCDS chủ yếu tái sử dụng class-related metadata; JIT code/compilation vẫn vận hành theo các cơ chế riêng.

### 15.5. Đo footprint nhiều JVM processes

Để đo memory benefit khi triển khai nhiều JVM instances:

1. Chạy cùng một app/JDK image ở nhiều processes trên cùng host.
2. So các cấu hình no-CDS, default-CDS, AppCDS.
3. Thu thập **PSS/USS** hoặc memory counters phân biệt shared/private pages nếu OS hỗ trợ.
4. Đo cả CPU/startup và memory sau readiness, tránh so ở các thời điểm lifecycle khác nhau.
5. Không cộng RSS mù quáng và diễn giải thành tổng physical RAM used.
6. Đưa cả disk footprint của `.jsa` vào vận hành nếu có nhiều versions.

Ở container/kubernetes, mỗi pod có namespace/storage/mount khác nhau; khả năng cùng dùng shared pages phụ thuộc việc archive có được map từ cùng page-cache-backed file/bối cảnh host hay không. Không tự suy mọi pod đều chia physical pages giống nhau.

## 16. Tích hợp AppCDS vào build và triển khai

Một workflow thực tế:

```text
1. Chọn JDK 17 image/vm build chuẩn
           │
           ▼
2. Build immutable application JARs
           │
           ▼
3. Run representative startup/warm-up paths
           │
           ▼
4A. Static: class list → Xshare:dump
4B. Dynamic: ArchiveClassesAtExit / runtime dump
           │
           ▼
5. Verify archive under SAME JDK + jars + classpath
           │
           ▼
6. Package JDK + app jars + CDS archive together
           │
           ▼
7. Deployment smoke test with -Xlog:cds / class+load
           │
           ▼
8. Measure startup/readiness, PSS/USS, rollback behavior
           │
           ▼
9. Rebuild archive whenever JDK/app packaging changes
```

### 16.1. Khi chọn static archive?

Static phù hợp khi:

- Có bước build/release được kiểm soát chặt và có thể chạy trial app.
- Muốn dùng class list như một artifact điều tra classes được load.
- Muốn chủ động đưa archive vào image trước production.
- Cần custom static base archive để phục vụ một quy trình layer khác.
- Có đủ thời gian CI để dump và verify.

Không nên coi static là mặc định nhanh hơn dynamic trong mọi app; phải benchmark. Những optimization differences cụ thể phụ thuộc JDK/collector/build.

### 16.2. Khi chọn dynamic archive?

Dynamic phù hợp khi:

- Muốn thử AppCDS nhanh mà không cần class-list step.
- Ứng dụng có warm-up path chạy tự nhiên trước shutdown.
- Muốn lưu loaded-class set của một run đại diện.
- Muốn top-layer archive bổ sung lớp riêng trên default base.
- Có thể xác minh archive-at-exit được ghi hoàn chỉnh và runtime map lại thành công.

Nếu app luôn bị kill đột ngột ở cuối workload (ví dụ container forced SIGKILL), `ArchiveClassesAtExit` không phải phương pháp chắc chắn để nhận một archive hoàn chỉnh. Chạy dedicated **archive-generation job** với graceful JVM exit.

### 16.3. Thay JDK patch version thì sao?

Khi JDK image/VM build đổi, archive có thể không tương thích. Đặt pipeline rule: **đổi JDK ⇒ recreate archive ⇒ smoke test**. Không đem một archive build trên local Windows machine chạy trên Linux server rồi mặc định nó dùng được.

### 16.4. Không dùng archive do nguồn không tin cậy tạo

Archive là binary data mà JVM dùng trong startup. Dù JVM có compatibility checks, chỉ nên sử dụng archive được tạo và phân phối qua pipeline tin cậy; không tải ngẫu nhiên `.jsa` từ bên thứ ba và buộc `-Xshare:on`. Kiểm soát permissions, artifact digests, supply-chain provenance và reproducibility như các deployment binaries khác.

## 17. Những nhầm lẫn phổ biến

1. **“AppCDS là trình biên dịch source Java thành native binary.”** Sai; nó chia sẻ metadata lớp cho HotSpot.
2. **“JAR không còn cần thiết sau khi tạo archive.”** Sai; classpath/resources và bytecode phải khớp.
3. **“CDS và AppCDS là hai hệ hoàn toàn không liên quan.”** Sai; AppCDS mở rộng CDS sang app classes.
4. **“Dynamic archive có thể tự ghi lại mọi lần một class mới được load.”** Không phải ý nghĩa của `ArchiveClassesAtExit`.
5. **“Static archive là Java `static` field snapshot.”** Sai; tên static ở đây mô tả vai trò/tạo archive.
6. **“Dynamic archive ghi giá trị hiện tại của objects trên heap khi shutdown.”** Sai; không phải heap dump.
7. **“`DumpLoadedClassList` trực tiếp tạo file `.jsa`.”** Sai; tạo class-list input cho dump.
8. **“`-Xshare:dump` chạy `main()` như bình thường.”** Sai; đây là chế độ tạo archive.
9. **“`ArchiveClassesAtExit` tăng tốc chính lần chạy tạo archive.”** Không đảm bảo; chính lần dump thường tốn thêm việc.
10. **“`SharedArchiveFile` chỉ dùng được cho static archive.”** Sai; dynamic cũng được hỗ trợ.
11. **“Để dùng dynamic top bắt buộc luôn phải viết đường dẫn default base tường minh.”** Sai; dynamic header có thể tham chiếu base.
12. **“Windows và Linux đều phân tách `base:top` bằng dấu `:`.”** Sai; Windows dùng `;`.
13. **“Có thể ghép hàng chục `.jsa` thành nhiều tầng tùy ý trong Java 17.”** Sai; không phải hệ layer tự do.
14. **“AppCDS archive luôn portable giữa mọi JDK 17 vendors.”** Sai; build/VM compatibility quan trọng.
15. **“Cứ tên file giống nhau thì JAR vẫn phù hợp dù đã rebuild.”** Sai; content/path checks có thể loại archive.
16. **“Thấy startup stdout đúng nghĩa AppCDS được dùng.”** Sai; cần class-load/CDS logs.
17. **“Một lớp nền như `java.lang.String` đến từ shared archive chứng minh mọi app classes đều shared.”** Sai.
18. **“Ứng dụng dùng CDS sẽ bỏ qua JIT và GC.”** Sai; đây là cơ chế khác.
19. **“Tất cả classes trong mọi dependency được archive ngay cả khi không load.”** Sai; trial/profile được dùng để chọn classes.
20. **“`-Xshare:on` luôn nên bật trong production.”** Sai; mode strict có thể chặn startup khi archive invalid.
21. **“Thêm `-Xshare:off` làm AppCDS hiệu quả hơn.”** Sai; nó tắt sử dụng shared archive.
22. **“ClassPath có non-empty directories không bao giờ ảnh hưởng AppCDS.”** Sai; JDK 17 có hạn chế.
23. **“Java source `new` tạo class metadata mới cho mỗi object.”** Sai; class metadata liên quan lớp, object instances là khái niệm khác.
24. **“Giảm thời gian startup nghĩa RAM process giảm tỷ lệ bằng nhau.”** Sai; hai metrics cần đo riêng.
25. **“Mỗi JVM process có RSS 1 GiB thì 10 process bắt buộc dùng 10 GiB physical RAM.”** Sai; RSS có shared pages.
26. **“Dynamic archive chỉ hoạt động nếu ứng dụng chạy ít nhất 10 phút.”** Sai; phụ thuộc loaded-class set/exit dump, không có threshold phút cố định.
27. **“Bước static dump không cần ứng dụng JAR đúng.”** Sai; classpath là input quan trọng.
28. **“`jcmd VM.cds dynamic_dump` tự hoạt động cho mọi PID.”** Sai; cần VM build/flags/attach permissions.
29. **“AppCDS thay thế readiness/liveness probes.”** Sai; startup optimization không đảm bảo health.
30. **“Nếu không thấy lợi ích benchmark một lần, tính năng chắc chắn vô ích.”** Sai; phải đo nhiều runs và đúng startup metric.
31. **“`-Xlog:gc*` là cách chính xác nhất để biết class có load từ archive.”** Sai; `cds` và `class+load` thích hợp hơn.
32. **“Mọi custom class loaders được archive như system loader không có ràng buộc.”** Sai; eligibility phụ thuộc cơ chế loader và JDK.
33. **“Default CDS archive = full AppCDS archive của mọi Java app trên máy.”** Sai; nó chủ yếu chứa lớp nền phổ biến.
34. **“Build archive trên JDK 21 rồi sử dụng nguyên trên JDK 17.”** Sai; không portable.
35. **“Chỉ cần copy một file `.jsa` sang production, bỏ JAR và JDK version.”** Sai; cần runtime dependencies/compatibility.
36. **“Memory mapping nghĩa mỗi class dùng chung cả mutable static fields và application data giữa JVM processes.”** Sai; mutable states của từng process phải tách biệt về semantics.
37. **“CDS archive là chỗ lưu secret/config application.”** Sai; không phải mục đích, và không nên biến archive thành vật mang dữ liệu nhạy cảm.
38. **“Static archive luôn to gấp 2 và chậm hơn dynamic đúng 2 lần.”** Sai; kích thước và hiệu năng tùy tập classes/dữ liệu.

## 18. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** AppCDS khác CDS mặc định chủ yếu ở đâu?

**Đáp án:** AppCDS có thể archive lớp ứng dụng/thư viện đủ điều kiện ngoài lớp nền tảng; đều nhằm giảm startup/memory footprint nhờ class data sharing.

**Câu 2.** Có phải file `.jsa` chứa toàn bộ object heap state tại lúc JVM thoát?

**Đáp án:** Không. Đó là CDS archive cho class-related data, không phải heap dump.

**Câu 3.** Quy trình static gồm mấy pha?

**Đáp án:** Thông thường **trial run tạo class list → explicit `-Xshare:dump` sinh static archive → runtime dùng archive**.

**Câu 4.** `-XX:DumpLoadedClassList=app.classlist` tạo ra loại file gì?

**Đáp án:** Danh sách classes được load trong trial run, **không phải `.jsa` archive**.

**Câu 5.** Dynamic archive tạo bằng flag nào trên Java 17?

**Đáp án:** `-XX:ArchiveClassesAtExit=app-dynamic.jsa` trong lần chạy ứng dụng, cần dump thành công khi JVM kết thúc.

**Câu 6.** Muốn dùng lại dynamic archive thì dùng flag nào?

**Đáp án:** `-XX:SharedArchiveFile=app-dynamic.jsa`, với JVM/base/classpath tương thích.

**Câu 7.** Vì sao dynamic archive có thể nhỏ hơn static archive?

**Đáp án:** Nó thường chỉ lưu classes bổ sung so với base archive, tránh lặp metadata đã có ở default static base.

**Câu 8.** `java -Xshare:on` có phù hợp production mặc định không?

**Đáp án:** Không khuyến nghị; mode strict có thể khiến JVM thất bại khởi động khi archive không thể dùng. `auto` thường linh hoạt hơn.

**Câu 9.** Lệnh `-XX:SharedArchiveFile=base.jsa:top.jsa` viết thế nào trên Windows?

**Đáp án:** Dùng `-XX:SharedArchiveFile=base.jsa;top.jsa`, đồng thời quote option/path nếu shell cần.

**Câu 10.** `AppCdsDemo` in `lengthSum` bao nhiêu?

**Đáp án:** **14**, vì `"alpha"` dài 5, `"beta"` dài 4, `"gamma"` dài 5.

**Câu 11.** Tại sao nên dùng JAR trong lab thay vì thư mục `out/`?

**Đáp án:** Các ràng buộc Java 17 AppCDS classpath, đặc biệt static archive creation, yêu cầu packages từ JARs và loại non-empty directories trong những tình huống tương ứng.

**Câu 12.** Nếu JVM stdout giống nhau với và không AppCDS, có nghĩa archive không giúp ích?

**Đáp án:** Không. Archive là tối ưu nội bộ, Java semantics/stdout **phải giống**. Hiệu năng cần đo và việc sử dụng cần kiểm chứng từ class loading/CDS logs.

**Câu 13.** Khi cập nhật Java 17.0.x patch, nên làm gì với archive?

**Đáp án:** Regenerate và verify bằng runtime JDK mới; archive phụ thuộc build/VM compatibility.

**Câu 14.** Class load log báo `source: shared objects file` cho một class. Điều đó nói gì?

**Đáp án:** Class ấy được nạp từ shared archive trong run đó; chưa chứng minh toàn bộ app classes đều shared.

**Câu 15.** Ứng dụng chạy lần đầu với `ArchiveClassesAtExit` nhưng process bị `SIGKILL`. Có chắc file archive đầy đủ không?

**Đáp án:** Không. Việc tạo archive ở cuối JVM cần đường kết thúc/dump phù hợp, phải check artifact và startup use.

**Câu 16.** Vì sao cần warm-up đại diện khi tạo AppCDS?

**Đáp án:** Vì archive từ loaded classes của một lần chạy; những lazy paths không được thực hiện có thể chưa nạp các classes cần tối ưu.

**Câu 17.** Có thể dùng một archive JDK của Linux amd64 trên Windows arm64 không?

**Đáp án:** Không nên giả định; HotSpot binary layout/VM build/platform khác, archive không portable.

**Câu 18.** `-Xlog:cds=info,class+load=info` để làm gì?

**Đáp án:** Xem archive mapping/acceptance và nguồn nạp từng class; không chỉ xem Java program exit status.

## 19. Checklist vận hành gợi ý

- [ ] Ghi rõ **JDK vendor/build, OS/architecture**, `java -version`.
- [ ] Đóng gói ứng dụng/dependencies dưới **JARs ổn định**, không thay file sau dump.
- [ ] Quyết định **static class-list/dump** hay **dynamic dump-at-exit** theo quy trình.
- [ ] Với static: tạo `app.classlist` từ **representative trial run**.
- [ ] Với static: tạo `app-static.jsa` bằng `-Xshare:dump` và `SharedClassListFile`.
- [ ] Với dynamic: xác nhận JVM **thoát và dump thành công**.
- [ ] Nếu có custom base: lưu đúng dependency của dynamic top vào packaging.
- [ ] Khi runtime: dùng `-XX:SharedArchiveFile` và `-Xshare:auto` phù hợp.
- [ ] Kiểm chứng một số **application classes** có log nguồn `shared objects file`.
- [ ] So output nghiệp vụ và readiness của app với baseline.
- [ ] Đo startup metric bằng nhiều runs, xen kẽ test order, kiểm soát OS page cache.
- [ ] Nếu đo memory: phân biệt **PSS/USS/shared pages** với RSS cộng thô.
- [ ] Regenerate archive khi **JDK/JAR/classpath/module settings** thay đổi.
- [ ] Chuẩn bị rollback khi archive bị từ chối, đặc biệt tránh `-Xshare:on` ngoài thử nghiệm.
- [ ] Bảo vệ `.jsa` như deployment artifact, không nhận binary từ nguồn không tin cậy.

## 20. Tổng kết nhanh

```text
                   JAVA 17 APP STARTUP
                         │
                default CDS archive
                         │
             ┌───────────┴───────────┐
             │                       │
        STATIC AppCDS            DYNAMIC AppCDS
             │                       │
     trial run: class list       app run với
             │                   ArchiveClassesAtExit
      Xshare:dump                  │
             │                  exit/dump
      app-static.jsa                │
             │                app-dynamic.jsa
             │                  (base + top)
             └───────────┬───────────┘
                         │
                  RUN với SharedArchiveFile
                         │
                 -Xlog:cds,class+load
                         │
              VERIFY classes đến từ archive
                         │
            MEASURE startup và footprint
                         │
         Không đổi Java semantics hay bỏ JAR/JDK.
```

**Ghi nhớ:** **AppCDS** mở rộng CDS sang classes ứng dụng để giảm startup work và có thể chia sẻ class metadata giữa nhiều JVMs. **Static archive** được tạo từ **class list + explicit dump**, còn **dynamic archive** được tạo **khi JVM thoát** sau một runtime run và dùng một **base archive**. Trong Java 17, các cờ chính là `DumpLoadedClassList`, `SharedClassListFile`, `-Xshare:dump`, `ArchiveClassesAtExit`, `SharedArchiveFile` và `-Xlog:cds,class+load`. Đúng quy trình phải **kiểm chứng archive được nạp**, giữ **JDK/JAR/classpath tương thích** và **benchmark có kiểm soát**. Archive không phải heap dump, không thay JAR, không cache JIT native code và không đảm bảo mọi lớp/ứng dụng đều khởi động nhanh hơn.

### Tài liệu tham khảo chính thức

- [Oracle JDK 17 — `java` command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): flags, static/dynamic archive workflows, two-archive layering, classpath restrictions, diagnostic logging.
- [Oracle Java SE 17 — Class Data Sharing, JVM Guide](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): cơ chế CDS, AppCDS, dynamic archive, memory sharing và default behavior.
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/other-tools/cds-appcds/): lab workflow, static/dynamic tradeoffs và giới hạn JDK versions.
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): kiến trúc mở rộng CDS đến application classes.
- [JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive đóng gói với JDK 12+.
- [JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): archive từ loaded classes khi JVM exit, dynamic top layer.
- [JDK 17 — `jcmd` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): runtime diagnostic commands, trong đó có `VM.cds` nếu build hỗ trợ.
