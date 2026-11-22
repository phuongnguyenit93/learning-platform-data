# Tính tương thích của đường dẫn lớp và tệp ứng dụng khi vận hành AppCDS

## 1. Vì sao archive tồn tại mà ứng dụng không dùng được?

**AppCDS (Application Class-Data Sharing)**, được giới thiệu trong **Java 10 qua JEP 310**, cho phép HotSpot lưu dữ liệu đã xử lý của những lớp ứng dụng vào CDS archive để tái sử dụng ở các lần chạy sau. Một tình huống dễ gây nhầm lẫn:

```text
Lúc tạo archive:
    java ... -cp app.jar:lib/a.jar ...

Lúc chạy:
    java ... -cp lib/a.jar:app.jar ...
```

Cùng hai JAR, cùng tên lớp, cùng dòng lệnh ứng dụng, nhưng **thứ tự classpath đã khác**. JVM có thể bỏ qua archive, và ứng dụng vẫn chạy nếu `-Xshare:auto` cho phép fallback. Một tình huống khác: classpath không đổi nhưng `app.jar` đã bị build lại; file `.jsa` cũ không còn phù hợp với bytecode ứng dụng hiện tại.

Đây không phải lỗi cú pháp Java: đó là **cơ chế bảo vệ tính nhất quán của archived classes**. JVM không được lấy metadata lớp từ một JAR cũ rồi áp lên lớp mang cùng tên nhưng được chọn theo classpath/JAR mới.

Bài này giải thích đầy đủ:

- **Quy tắc classpath tại dump và runtime**: giống nhau hoặc có quan hệ *prefix*.
- **JAR identity/integrity**: sửa, đóng gói lại, thay dependency hay thay file nhưng giữ tên vẫn có thể làm archive vô hiệu.
- **Thư mục không rỗng và modular JARs**: giới hạn khi tạo/lưu lớp.
- **Module path**: không có cùng prefix rule, nhưng có các ràng buộc khác.
- **JDK build, working directory, container image, launcher flags**: vì sao cùng câu lệnh viết trên giấy chưa chứng minh tương thích.
- **Kiểm thử chạy được**: tạo archive, thêm JAR ở cuối, đổi thứ tự JAR, cập nhật ứng dụng và đọc log nạp lớp.
- **Vận hành hiện đại**: static AppCDS còn hiệu lực trong JDK hiện hành; dynamic CDS/AOT là lựa chọn khác, không nên nhầm quy tắc của từng cơ chế.

**Phạm vi:** tập trung vào tính tương thích của **static CDS archive** được tạo bằng `-Xshare:dump`. Nội dung thực hành dùng **JDK 17+** và đã thử với **OpenJDK 24.0.2**; không khuyên triển khai JDK 10 đã cũ làm production chỉ để học AppCDS.

## 2. Các thành phần thực sự tham gia

Một quy trình AppCDS tĩnh tối thiểu gồm:

```text
app.jar chứa demo.Hello
      |
      | java -Xshare:off
      | -XX:DumpLoadedClassList=app.classlist
      v
app.classlist
      |
      | java -Xshare:dump
      | -XX:SharedClassListFile=app.classlist
      | -XX:SharedArchiveFile=app.jsa
      | -cp app.jar
      v
app.jsa (static archive)
      |
      | java -XX:SharedArchiveFile=app.jsa
      | -cp app.jar demo.Hello
      v
JVM tìm class, xác minh phù hợp rồi mới dùng archived metadata
```

| Thành phần | Vai trò |
| --- | --- |
| `app.jar` | File ứng dụng chứa bytecode, manifest và có thể có resources |
| `lib/a.jar` | Dependency trên classpath, cũng có thể chứa lớp archived |
| `app.classlist` | Danh sách lớp nạp trong lần chạy profile, dùng làm đầu vào của dump |
| `app.jsa` | Archive chứa dữ liệu lớp được chuẩn bị sẵn |
| `-cp` / `-classpath` | Danh sách vị trí JVM tìm lớp theo thứ tự |
| `--module-path` | Danh sách nguồn module theo Java Platform Module System |
| `-XX:SharedArchiveFile` | Đường dẫn archive được tạo hoặc sử dụng |
| `-Xlog:class+load=info` | Log nguồn lớp, giúp xác nhận lớp mục tiêu có dùng archive |
| `-Xlog:cds=info` | Log hoạt động/chẩn đoán CDS |

**File `.jsa` không phải file JAR thay thế.** Ứng dụng vẫn cần các JAR thực tế và classpath đúng. Một archive có thể chứa nhiều metadata đã chuẩn bị nhưng không thể thay cho toàn bộ nguồn bytecode và resources khi application cần.

### 2.1. CDS không đơn thuần là cache theo tên class

Tên `demo.Hello` có thể xuất hiện trong nhiều JAR. Nếu đổi thứ tự classpath, classloader có thể chọn một `demo.Hello` khác. Ngay cả khi hiện tại chỉ một JAR chứa lớp, JVM vẫn cần kiểm tra tính nhất quán với cấu hình lúc dump.

Vì thế, “class name bằng nhau” **không đủ**; source JAR, vị trí, thứ tự, classloader, JVM build và một số launcher options đều có thể ảnh hưởng khả năng tận dụng archive.

### 2.2. Vai trò của `-Xshare:dump`

`-Xshare:dump` là chế độ **tạo archive**, không chạy `main(String[] args)`. Lệnh:

```bash
java -Xshare:dump -XX:SharedClassListFile=app.classlist \
     -XX:SharedArchiveFile=app.jsa -cp app.jar
```

ghi `app.jsa` theo những lớp/classpath phù hợp. Sau đó dùng archive ở một lệnh **khác**:

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.Hello
```

Không vì thấy một file `app.jsa` tồn tại mà kết luận JVM đã dùng nó trong lần chạy sau. Phải kiểm tra nguồn lớp ở log.

## 3. Quy tắc quan trọng nhất: classpath tạo archive phải là tiền tố của classpath chạy

Tài liệu `java` của JDK hiện hành nêu:

> Class path khi tạo archive phải giống hoặc là một prefix của class path khi chạy.

**Prefix** ở đây là quan hệ giữa hai **danh sách có thứ tự**, không phải quan hệ giữa hai tập hợp JAR bất kỳ.

### 3.1. Giữ nguyên thứ tự: phù hợp

```text
DUMP: app.jar:lib/a.jar
RUN : app.jar:lib/a.jar
```

Đây là trường hợp cơ bản. Nếu JAR không đổi và các điều kiện khác phù hợp, lớp đã archived có thể được dùng.

### 3.2. Nối thêm JAR ở cuối: có thể phù hợp

```text
DUMP: app.jar:lib/a.jar
RUN : app.jar:lib/a.jar:lib/b.jar
```

Hai phần tử đầu của runtime classpath vẫn đúng prefix của lúc dump. AppCDS có thể tiếp tục dùng archived classes thuộc các JAR đã có trong prefix. **JAR `b.jar` mới nối thêm không tự được đưa vào archive cũ.**

Điều kiện prefix **cần thiết nhưng chưa đủ**: JDK build, nội dung JAR, module options và classloader vẫn phải tương thích.

### 3.3. Thêm JAR vào đầu hoặc đảo thứ tự: không còn prefix

```text
DUMP: app.jar:lib/a.jar
RUN : lib/b.jar:app.jar:lib/a.jar
```

`app.jar` không còn nằm ở đầu danh sách. Tương tự:

```text
DUMP: app.jar:lib/a.jar
RUN : lib/a.jar:app.jar
```

Hai danh sách chứa cùng hai JAR nhưng **khác thứ tự**. Không xem một phép so sánh “các tên JAR sau khi sort giống nhau” là phép xác minh tương thích AppCDS.

Trong thử nghiệm ở phần 9, chỉ thêm `extra.jar` vào **đầu** classpath khiến lớp `demo.Hello` không còn được nạp từ archive. Dùng `-Xshare:on` trong phép thử đó làm JVM thoát lỗi với dấu hiệu `shared class paths mismatch`.

### 3.4. Separator khác nhau theo hệ điều hành

```text
POSIX (Linux/macOS):  app.jar:lib/a.jar:lib/b.jar
Windows:              app.jar;lib\a.jar;lib\b.jar
```

Dấu `:` và `;` là separator classpath tương ứng. **Không copy nguyên classpath POSIX sang Windows** rồi kỳ vọng JVM hiểu giống nhau.

Ngoài separator, file paths, encoding của script, volume mounts và ký tự đặc biệt trong tên thư mục cũng ảnh hưởng launcher. Trong pipeline đa nền tảng, dựng classpath theo OS mục tiêu và kiểm tra command được JVM nhận.

### 3.5. Wildcard classpath cần thận trọng

Classpath như `lib/*` rất tiện, nhưng thứ tự JAR được mở rộng từ wildcard có thể không phải thứ tự cố định mà ứng dụng cho rằng sẽ xuất hiện ở mọi lần chạy.

Khi muốn tạo archive tái lập được:

- chốt dependency versions;
- tạo **danh sách JAR cụ thể theo thứ tự ổn định**;
- dùng cùng danh sách ở bước thu classlist, dump và run;
- nếu thay đổi tập JAR hoặc thứ tự, kiểm thử lại và thường nên dump lại;
- khi điều tra lỗi, bật log `-Xlog:class+path=info` hoặc `-Xlog:cds=info`.

Đừng dựa vào `lib/*` khi cần chứng minh chính xác thứ tự nguồn lớp mà archive đã gắn với, trừ khi launcher/build tool đã bảo đảm và bạn đã xác minh hành vi trên runtime thực tế.

## 4. JAR bị sửa sau khi dump: không thể coi archive vẫn còn hợp lệ

Một nguyên tắc độc lập với thứ tự classpath:

**Tài liệu JDK nêu archive không thể được nạp nếu JAR trong classpath hoặc module path bị sửa sau khi archive được tạo.**

Ví dụ:

```text
Lúc dump:
  app.jar -> demo.Hello in "app=V1"

Sau khi build lại:
  app.jar -> demo.Hello in "app=V2"

Lúc chạy:
  vẫn -cp app.jar, vẫn dùng app.jsa cũ
```

Classpath string không đổi, nhưng nội dung được chương trình mong đợi đã đổi. JVM không được lấy archived metadata V1 thay cho code V2.

### 4.1. Những thay đổi có thể làm archive không phù hợp

- Biên dịch lại class trong `app.jar`.
- Cập nhật một thư viện `lib/a.jar` lên version mới.
- Đóng gói lại JAR nhưng giữ nguyên tên tệp.
- Thêm/bỏ resource, thay manifest hoặc metadata của JAR đã tham gia dump.
- Thay đường dẫn symlink tới một release JAR khác.
- Thay binary bằng bản có cùng version label nhưng build khác.
- Copy/repack trong CI làm timestamp hoặc file identity khác điều kiện JVM đã ghi nhận.

HotSpot có thể phát hiện mismatch qua thông tin JAR như timestamp và size. **Không cố chỉnh lại timestamp để né kiểm tra**, bởi tính đúng đắn của bytecode và class nguồn quan trọng hơn việc ép archive được chấp nhận.

### 4.2. Timestamp không phải chính sách xác minh toàn vẹn duy nhất

Trong phép thử đã thực hiện, sau khi tạo `app.jsa`, sửa `Hello.java` thành V2 và cập nhật JAR khiến log báo:

```text
hello.jar timestamp has changed.
Unable to use shared archive.
```

Đó là **một thông báo của JDK thử nghiệm**, không phải lời hứa mọi lỗi file đều có cùng chuỗi chữ đó. Có runtime kiểm tra thêm các đặc điểm khác và thay đổi cơ chế nội bộ theo phiên bản.

Để bảo vệ artifact ở góc độ CI, có thể lưu SHA-256, SBOM và provenance của JAR; tuy nhiên **checksum do pipeline quản lý không thay thế kiểm tra archive thực tế của JVM**.

### 4.3. JAR resources vẫn cần thiết

Static CDS archive chủ yếu lưu dữ liệu lớp đã chuẩn bị. Nó **không phải nơi lưu thay thế mọi tài nguyên ứng dụng** như:

- `META-INF/services`;
- file properties, YAML/JSON trong JAR;
- assets giao diện;
- templates hoặc resource bundles;
- cấu hình runtime ngoài JAR.

Dù lớp đã được archived, ứng dụng vẫn có thể cần truy cập JAR/resource thực tế. Không xóa `app.jar` hoặc toàn bộ `lib/` sau bước dump.

## 5. Đường dẫn tương đối, working directory và việc di chuyển artifact

Ví dụ:

```bash
java -cp hello.jar demo.Hello
```

`hello.jar` là đường dẫn tương đối với **thư mục làm việc của tiến trình**. Nếu tạo archive tại `/opt/app` nhưng chạy ở `/tmp`, chuỗi `hello.jar` có thể trỏ tới tệp khác hoặc không trỏ tới đâu.

Những thay đổi thường xuất hiện khi deploy:

- Docker `WORKDIR` thay đổi.
- systemd service dùng `WorkingDirectory` khác.
- Kubernetes mount một volume vào vị trí mới.
- Release directory dùng symlink tới phiên bản mới.
- Gradle/Maven hoặc launcher script dựng classpath với đường dẫn khác.
- Một phần dependencies được copy sang thư mục mới, dù file name vẫn giống.

**Giải pháp:** ghi nhận đường dẫn classpath đã được giải quyết thực tế, giữ cấu trúc triển khai nhất quán, và xác minh archive trong **runtime image cuối cùng**.

Đường dẫn tuyệt đối có thể giảm nhập nhằng nhưng **không** chứng minh JAR chưa thay đổi. Đường dẫn tương đối không tự sai nếu working directory được kiểm soát và JVM chấp nhận các điều kiện archive. Đừng viết quy tắc tuyệt đối kiểu “mọi classpath phải là absolute path”; quy tắc thật cần kiểm tra là **nguồn lớp và quan hệ classpath hợp lệ theo JDK đang chạy**.

## 6. Giới hạn non-empty directories và cách đóng gói ứng dụng

Tài liệu launcher hiện hành liệt kê các restrictions:

- Classpath liên quan CDS không thể chứa **non-empty directories** trong những trường hợp bị hạn chế.
- Với workflow static AppCDS thu classlist để archiving các lớp ứng dụng, hướng dẫn nêu classpath **chỉ chứa JAR files**.
- `-Xbootclasspath/a` cũng chịu các giới hạn liên quan tới thư mục không rỗng.
- Module path dùng cho archive hỗ trợ **modular JAR files**, không hỗ trợ **exploded modules**.

Ví dụ nên làm:

```bash
javac --release 17 -d classes src/demo/Hello.java
jar --create --file hello.jar -C classes .
java -Xshare:off -XX:DumpLoadedClassList=hello.classlist \
     -cp hello.jar demo.Hello
```

**Đừng mặc nhiên thay `-cp hello.jar` bằng `-cp classes/`** rồi mong lớp trong thư mục build được static archived như lớp trong JAR. Quy tắc chi tiết của non-empty directories có thể thay đổi theo JDK/cấu hình, nhưng mô hình **JAR ổn định** là lựa chọn an toàn cho bài thực hành.

Một thư mục trống không nhất thiết dẫn tới cùng lỗi như thư mục có class files; tránh phát biểu “mọi directory trong mọi tình huống đều làm HotSpot crash”. Với nhu cầu thực tế, xem Javadoc/JDK launcher và kiểm chứng archive bằng log.

### 6.1. Tại sao build tool gây rủi ro?

Trong IDE, thư mục `build/classes` hoặc `target/classes` liên tục thay đổi khi developer biên dịch. Static archive phù hợp hơn với **artifact đóng gói cuối cùng**, sau khi danh sách dependencies đã chốt.

Một pipeline đáng tin nên đi theo thứ tự:

```text
compile -> package JARs -> freeze artifacts
        -> trial run/classlist -> static dump
        -> smoke test -> publish artifact bundle
```

Không đóng gói lại JAR **sau** khi tạo archive trừ khi bạn cũng tạo lại archive tương ứng.

## 7. Classpath khác với module path

JDK hỗ trợ Java Platform Module System từ Java 9. Khi ứng dụng dùng `--module-path` và `--module`, cần phân biệt:

| Điều kiện | Classpath | Module path |
| --- | --- | --- |
| Quy tắc prefix khi dump/run | **Có**: giống hoặc là prefix | **Không áp dụng cùng prefix requirement** |
| JAR bị sửa sau dump | Có thể làm archive không hợp lệ | Cũng có thể làm archive không hợp lệ |
| Nguồn dạng thư mục không rỗng/exploded | Có restriction theo CDS workflow | **Exploded modules không được archived** |
| Thay đổi nguồn lớp/module | Có thể làm lớp được nạp từ nơi khác | Có thể làm archived class không còn được dùng |
| Cần xem launcher options | Có | Có, đặc biệt các module-related options |

**Không nói** rằng vì module path không có prefix rule thì tùy ý đổi mọi module JAR sau dump. Một JAR đã bị sửa vẫn là vấn đề. Nếu một module JAR bị loại hoặc class cùng tên được resolve từ nguồn khác, những archived classes tương ứng có thể không được dùng.

### 7.1. Một số module-related options

Tài liệu JDK hiện hành liệt kê những options có thể làm việc với CDS như:

```text
--module-path
--module
--add-modules
--enable-native-access
```

Khi có sử dụng, **giữ các giá trị tương ứng nhất quán giữa tạo và chạy archive** theo yêu cầu JVM; mismatch có thể làm mất một phần hoặc toàn bộ lợi ích CDS.

Những options như `--patch-module`, `--upgrade-module-path` và `--limit-modules` có thể vô hiệu hóa CDS hoặc khiến dump thất bại theo phiên bản/cấu hình. Không sử dụng chúng như “cách chữa” một classpath mismatch mà không hiểu tác động.

### 7.2. Class loaders của framework

Các framework có thể tạo custom classloader, nested JAR layout hoặc cơ chế khởi chạy không giống `java -cp app.jar Main`. Một classpath prefix hợp lệ **không bảo đảm mọi class đều được archived**.

Khi dùng Spring hoặc framework tương tự, nên xem hướng dẫn CDS/AOT chính thức của framework và kiểm tra **những class mục tiêu** bằng log. Đừng áp dụng máy móc ví dụ JAR đơn giản cho một application launcher khác mà không thử nghiệm.

## 8. `-jar`, classpath và biến môi trường

Hai cách chạy:

```bash
java -cp app.jar com.example.Main
java -jar app.jar
```

có thể chạy cùng một ứng dụng khi manifest cho phép, nhưng cách chọn main class và classpath không hoàn toàn giống nhau. Với `-jar`, manifest `Main-Class` và có thể `Class-Path` ảnh hưởng đường nạp lớp; classpath khai báo bằng `-cp` không được dùng theo cách thông thường.

**Không đổi chế độ launcher sau khi tạo archive** rồi mặc định vẫn tương thích. Nếu production chạy `java -jar app.jar`, hãy thiết kế quy trình tạo/dùng archive theo startup command thực tế và kiểm chứng bằng log.

Ngoài ra, `CLASSPATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, plugin agent và script khởi động có thể thêm/sửa options mà developer không thấy trên command mẫu. Hãy ghi nhận cấu hình thật ở hai giai đoạn, nhưng **không log secrets** hoặc toàn bộ environment public.

## 9. Bài thực hành Java 17+ đã kiểm thử

Bài thực hành dùng hai JAR để làm rõ **giữ nguyên – nối ở cuối – nối ở đầu – sửa JAR**. Chạy trên **Windows PowerShell** hoặc POSIX shell bằng các biến thể classpath được hướng dẫn. Lệnh tạo archive và mã Java đã được thử với JDK 24.0.2.

### 9.1. Tạo class của ứng dụng và class phụ

Tạo cấu trúc:

```text
src/
  demo/Hello.java
  extra/Extra.java
```

Nội dung file **`src/demo/Hello.java`**:

```java
package demo;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("app=V1");
    }
}
```

Nội dung file **`src/extra/Extra.java`**:

```java
package extra;

public final class Extra {
    public static int answer() {
        return 42;
    }
}
```

`Extra` không được `Hello` gọi; nó chỉ dùng để đóng một JAR phụ nhằm thử thứ tự classpath.

### 9.2. Biên dịch và tạo hai JAR

Từ thư mục chứa `src`:

```bash
mkdir -p classes extraClasses
javac --release 17 -encoding UTF-8 -d classes src/demo/Hello.java
javac --release 17 -encoding UTF-8 -d extraClasses src/extra/Extra.java
jar --create --file hello.jar -C classes .
jar --create --file extra.jar -C extraClasses .
```

Trên PowerShell, thay `mkdir -p` bằng:

```powershell
New-Item -ItemType Directory -Force -Path classes,extraClasses
```

Bốn lệnh `javac`/`jar` giữ nguyên. Kiểm tra JAR bằng:

```bash
jar --list --file hello.jar
jar --list --file extra.jar
```

`hello.jar` chứa `demo/Hello.class`; `extra.jar` chứa `extra/Extra.class`.

### 9.3. Thu classlist bằng JAR đúng nguồn

```bash
java -Xshare:off -XX:DumpLoadedClassList=hello.classlist \
     -cp hello.jar demo.Hello
```

Stdout:

```text
app=V1
```

`hello.classlist` được tạo và chứa tên `demo/Hello`. Tùy chọn `-Xshare:off` giúp thu danh sách lớp của workload không tận dụng CDS archive đã có.

### 9.4. Tạo static archive

```bash
java -Xshare:dump \
     -XX:SharedClassListFile=hello.classlist \
     -XX:SharedArchiveFile=hello.jsa \
     -cp hello.jar
```

Lệnh này tạo `hello.jsa`, **không chạy `main()`**, nên không có stdout `app=V1` từ ứng dụng. Kiểm tra exit code bằng 0 và file `hello.jsa` tồn tại, có kích thước lớn hơn 0.

### 9.5. Trường hợp A: classpath giữ nguyên

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -Xlog:class+load=info \
     -cp hello.jar demo.Hello
```

Trong rất nhiều dòng log, tìm:

```text
demo.Hello source: shared objects file
app=V1
```

Đây là **trích đoạn hai dòng có ý nghĩa**, không phải toàn bộ stdout: log thật có timestamp và thêm nhiều lớp hệ thống. Trên JDK thử nghiệm, lớp `demo.Hello` thật sự được nạp từ archive.

### 9.6. Trường hợp B: thêm JAR cuối classpath

Trên Windows PowerShell/CMD:

```powershell
java -XX:SharedArchiveFile=hello.jsa '-Xlog:class+load=info' -cp 'hello.jar;extra.jar' demo.Hello
```

Trên Linux/macOS (POSIX shell):

```bash
java -XX:SharedArchiveFile=hello.jsa -Xlog:class+load=info \
     -cp 'hello.jar:extra.jar' demo.Hello
```

JDK thử nghiệm vẫn ghi:

```text
demo.Hello source: shared objects file
app=V1
```

Vì classpath lúc dump `hello.jar` vẫn là **prefix** của classpath runtime.

### 9.7. Trường hợp C: đảo thứ tự, đưa JAR mới lên đầu

Trên Windows:

```powershell
java -XX:SharedArchiveFile=hello.jsa '-Xlog:class+load=info' -cp 'extra.jar;hello.jar' demo.Hello
```

Trên POSIX:

```bash
java -XX:SharedArchiveFile=hello.jsa -Xlog:class+load=info \
     -cp 'extra.jar:hello.jar' demo.Hello
```

Trong phép thử, ứng dụng vẫn in `app=V1` nhưng **không có** dấu hiệu `demo.Hello source: shared objects file`. Nó đã chạy theo cách thông thường thay vì dùng archived class của `Hello`.

Để chứng minh mismatch bằng chế độ **chẩn đoán**, chạy trên Windows:

```powershell
java -Xshare:on -XX:SharedArchiveFile=hello.jsa '-Xlog:cds=info' -cp 'extra.jar;hello.jar' demo.Hello
```

JDK được thử nghiệm thoát với exit code khác 0 và chứa các dòng:

```text
shared class paths mismatch
Unable to use shared archive.
```

**Không đưa `-Xshare:on` vào production chỉ để bắt buộc tối ưu**: điều này có thể khiến service không khởi động khi archive không phù hợp.

### 9.8. Trường hợp D: sửa chính JAR sau khi tạo archive

Thay nội dung file **`src/demo/Hello.java`** bằng:

```java
package demo;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("app=V2");
    }
}
```

Sau đó chạy:

```bash
javac --release 17 -encoding UTF-8 -d classes src/demo/Hello.java
jar --update --file hello.jar -C classes .
java -XX:SharedArchiveFile=hello.jsa -cp hello.jar demo.Hello
```

Ở chế độ mặc định trên JDK thử nghiệm, chương trình in:

```text
app=V2
```

JVM không dùng archived metadata của file V1 cho một JAR đã thay đổi. Nếu thêm `-Xshare:on`, JVM báo lỗi và thoát; log của lần thử có câu `hello.jar timestamp has changed`.

**Sau khi sửa JAR, hãy tạo lại classlist và `hello.jsa`**, rồi xác minh log lớp lần nữa. Đừng sửa timestamp để cố dùng lại archive.

### 9.9. Kết luận của bài thực hành

| Thay đổi sau dump | App có thể chạy bình thường? | Archived `demo.Hello` trong phép thử |
| --- | --- | --- |
| Giữ nguyên `hello.jar` | Có | Có |
| Nối `extra.jar` ở cuối | Có | Có |
| Thêm `extra.jar` ở đầu | Có với `-Xshare:auto` | Không |
| Sửa `hello.jar` thành V2 | Có với `-Xshare:auto` | Archive cũ không còn phù hợp |
| Dùng `-Xshare:on` khi archive mismatch | Không | JVM thoát lỗi |

**Đây là kết quả quan sát trên JDK 24.0.2**, không phải lời hứa mọi JDK sẽ in đúng từng thông điệp hoặc runtime log timestamp. Quy tắc tương thích mang tính tổng quát được nêu trong tài liệu Java launcher hiện hành.

## 10. Chẩn đoán AppCDS không hoạt động

### 10.1. Kiểm tra JVM

```bash
java --version
javac -version
```

Kiểm tra JDK thực tế trong container, không chỉ bản JDK trên máy host. CDS archive có thể gắn với **JDK build cụ thể**: nâng JDK patch release hoặc đổi runtime image có thể khiến archive không phù hợp.

### 10.2. Kiểm tra classpath và JAR

- Danh sách có theo đúng thứ tự không?
- Có phần tử mới được **chèn vào giữa hoặc đầu** không?
- JAR đã bị sửa/copy/repack sau dump không?
- Relative paths có được giải quyết từ cùng working directory không?
- Có wildcard, symlink, `-jar` hoặc manifest `Class-Path` đổi cách tìm lớp không?
- Có custom classloader khiến lớp được load từ nguồn khác không?
- Có module-related options khác so với lúc dump không?

### 10.3. Kiểm tra nguồn lớp

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -Xlog:class+load=info -cp hello.jar demo.Hello
```

Tìm đúng `demo.Hello` và nguồn `shared objects file`. Nếu chỉ thấy `file:/.../hello.jar` thì lớp đó đang được lấy từ JAR, không phải shared archive.

### 10.4. Bật log CDS và classpath

```bash
java -XX:SharedArchiveFile=hello.jsa -Xlog:cds=info \
     -cp hello.jar demo.Hello
```

Khi JVM gợi ý, có thể dùng `-Xlog:class+path=info`. Tránh so toàn bộ log từng ký tự; chỉ trích xuất các sự kiện quan trọng như `shared class paths mismatch`, `timestamp has changed`, không thể map archive hoặc class chưa đủ điều kiện share.

### 10.5. Phân biệt fallback với lỗi vận hành

| Chế độ | Archive hợp lệ | Archive không tương thích | Khuyến nghị |
| --- | --- | --- | --- |
| `-Xshare:auto` | Dùng CDS khi có thể | Có thể fallback | Phù hợp với production cần khả năng khởi động |
| `-Xshare:on` | Bắt buộc CDS | Thường JVM thoát lỗi | Chỉ dùng để test/diagnostics |
| `-Xshare:off` | Không dùng CDS | Không áp dụng | Dùng làm baseline khi so hiệu năng/training |

Một application in stdout đúng **không chứng minh** archive đã dùng. Ngược lại, một JVM thoát vì `-Xshare:on` không tự chứng minh code ứng dụng sai; có thể chỉ archive không phù hợp.

## 11. Vận hành nhất quán trong CI/CD

Hãy coi những thành phần sau là một **artifact bundle**:

```text
runtime/JDK build hoặc container digest
app.jar
lib/*.jar (theo thứ tự đã chốt)
app.jsa
script/startup arguments
build metadata
```

Một quy trình nên có:

1. Build ứng dụng và khóa dependency versions.
2. Ghi rõ vendor/JDK build, OS/CPU và cấu hình JVM.
3. Đóng gói JAR **trước khi** thu classlist.
4. Chạy workload đại diện tạo classlist.
5. Tạo static archive trên môi trường tương thích với runtime cuối.
6. Chạy smoke test **trên image thật**, xác nhận lớp quan trọng lấy từ `shared objects file`.
7. Lưu checksum/provenance của JAR cùng archive.
8. Rebuild và kiểm thử archive sau khi nâng JDK, base image, classpath, launcher hoặc dependency JAR.
9. Đo startup/footprint theo workload để biết tối ưu có đáng chi phí build/lưu archive không.

### 11.1. Không biến archive thành rủi ro availability

Nếu AppCDS là tối ưu tùy chọn, production nên có chính sách fallback phù hợp thay vì luôn bật `-Xshare:on`. Có thể dùng `on` trong pipeline **kiểm thử bắt buộc archive** rồi chạy production ở `auto`.

### 11.2. Bảo vệ file archive và source JAR

Đặt archive/JAR trong vùng có quyền phù hợp, chỉ deploy từ nguồn đã kiểm chứng, không cho bên không tin cậy tự chỉnh tệp. Một file `.jsa` đã bị can thiệp có thể gây lỗi nạp lớp; bảo vệ nó như một artifact trong chuỗi cung ứng phần mềm. Tùy chọn kiểm tra CRC32 không thay thế chữ ký mật mã/SBOM/provenance.

### 11.3. Kiểm thử hiệu năng đúng cách

Archive hợp lệ không có nghĩa startup tự động nhanh hơn một tỷ lệ cố định. Kết quả phụ thuộc:

- số lớp được share;
- startup workload và class loading profile;
- disk I/O, page cache, container memory;
- framework initialization, DB/network connections, JIT;
- độ phủ classlist và việc JVM thật sự dùng archive.

So nhiều lần đo ở cấu hình tương đương, phân biệt cold/warm startup. Đừng chỉ đo một lượt rồi kết luận AppCDS là nguyên nhân duy nhất.

## 12. Những hiểu nhầm thường gặp

**1. “Classpath chứa cùng các JAR là đủ.”**  
Sai. Với static archive, **thứ tự** có ý nghĩa và dump classpath phải giống/prefix của runtime classpath.

**2. “Thêm JAR ở cuối và ở đầu là tương đương.”**  
Sai. Nối cuối có thể giữ prefix; nối đầu phá prefix.

**3. “JAR vẫn cùng tên nên archive không thể bị invalidated.”**  
Sai. File có thể đã bị build lại, cập nhật manifest/resources hoặc thay metadata.

**4. “Archive tồn tại thì app đang dùng archive.”**  
Sai. Phải xác minh class load log cho class ứng dụng, không chỉ check file size.

**5. “Archive thay thế được JAR.”**  
Sai. JAR và các resources/dependencies vẫn cần thiết.

**6. “`-Xshare:on` làm AppCDS an toàn hơn trên production.”**  
Sai. Khi mismatch, JVM có thể không khởi động. `on` dùng cho test.

**7. “Mọi thư mục classpath đều được archived như JAR.”**  
Sai với static workflow đang hướng dẫn. Nonempty directories có restrictions; ưu tiên đóng JAR.

**8. “Module path cũng phải prefix giống classpath.”**  
Sai. Hai cấu hình có quy tắc khác, nhưng module JAR vẫn phải tương thích.

**9. “`-jar` và `-cp` không làm khác môi trường class loading.”**  
Sai. Manifest/launcher có thể thay đổi nguồn lớp.

**10. “Archive do JDK 17 tạo dùng cho JDK 27 nếu JAR không đổi.”**  
Không được bảo đảm. Archive phụ thuộc JDK build và cơ chế CDS của runtime.

**11. “Hash JAR giống là đủ, không cần chạy thử archive.”**  
Sai. JDK options, đường dẫn và environment cũng ảnh hưởng.

**12. “Một lớp không được share chứng tỏ CDS hoàn toàn tắt.”**  
Không nhất thiết. CDS có thể load một số lớp từ archive và lớp khác từ JAR; cần xem log theo class và tình trạng archive.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Dump với `-cp a.jar:b.jar`, chạy với `-cp a.jar:b.jar:c.jar` trên Linux có giữ prefix không?  
**Đáp án:** Có, nếu hai phần tử đầu không đổi và các điều kiện khác tương thích.

**Câu 2.** Dump với `-cp a.jar:b.jar`, chạy với `-cp b.jar:a.jar` có hợp lệ theo prefix rule không?  
**Đáp án:** Không; cùng tập JAR không đồng nghĩa cùng danh sách có thứ tự.

**Câu 3.** Vì sao sửa `a.jar` nhưng giữ nguyên đường dẫn cũng làm archive không dùng được?  
**Đáp án:** Dữ liệu lớp được archive theo artifact trước đó; JDK phải từ chối mismatch thay vì nạp metadata cũ cho class mới.

**Câu 4.** Nếu một ứng dụng vẫn in `app=V1`, đã đủ chứng minh `demo.Hello` nằm trong shared archive chưa?  
**Đáp án:** Chưa; chương trình có thể chạy bằng class loader bình thường. Kiểm tra `-Xlog:class+load=info`.

**Câu 5.** Trong module path, có áp dụng prefix rule của classpath không?  
**Đáp án:** Không. Module path không có cùng prefix requirement, nhưng JAR/source/options vẫn phải tương thích.

**Câu 6.** Tại sao cần cẩn trọng với `lib/*`?  
**Đáp án:** Thứ tự JAR thực tế có thể khác và phá tính tương thích của archive.

**Câu 7.** `-Xshare:on` khác `-Xshare:auto` khi archive không hợp lệ thế nào?  
**Đáp án:** `auto` thường fallback; `on` yêu cầu CDS và có thể làm JVM thoát.

**Câu 8.** Có thể tạo archive với `-cp classes/` và mặc định mọi class trong thư mục nonempty được archive không?  
**Đáp án:** Không. Static AppCDS có những giới hạn classpath; nên đóng gói JAR đúng quy trình.

**Câu 9.** Khi thay Docker base image cập nhật JDK, cần làm gì với `app.jsa`?  
**Đáp án:** Tái tạo và kiểm thử trên đúng JDK/runtime image mới; không mặc định archive cũ dùng được.

**Câu 10.** Trong phép thử, vì sao thêm `extra.jar` ở cuối không làm mất sharing của `demo.Hello`?  
**Đáp án:** Dump classpath `hello.jar` vẫn là prefix của runtime classpath `hello.jar;extra.jar`.

## 14. Ghi nhớ

1. **Tính tương thích classpath là ràng buộc của static AppCDS**, không đơn giản là tên lớp giống nhau.
2. **Dump classpath phải giống hoặc là prefix của runtime classpath**. Nối cuối có thể hợp lệ; thêm đầu/đảo thứ tự có thể làm archive không dùng được.
3. **JAR trong classpath/module path bị sửa sau dump làm archive không còn phù hợp.**
4. **Không dùng nonempty class directories** như nguồn static archived classes thay cho JAR trong workflow tiêu chuẩn; module path có restrictions riêng cho modular JAR.
5. **Module path không có cùng prefix requirement**; tuy nhiên launcher/module options và JAR vẫn phải nhất quán.
6. **`-Xshare:auto` có thể fallback, `-Xshare:on` chỉ dành cho test**. Không đánh đổi availability chỉ vì tối ưu khởi động.
7. **Log `demo.Hello source: shared objects file`** mới là bằng chứng trực tiếp lớp cụ thể được nạp từ archive.
8. **Rebuild archive khi đổi JDK build, JAR, classpath hoặc môi trường triển khai**, rồi smoke test bằng application thật.
9. Static AppCDS có từ **Java 10/JEP 310** và còn áp dụng hiện nay; với JDK mới có thể đánh giá dynamic CDS/AOT cache như các lựa chọn bổ sung.

## Tài liệu tham khảo chính thức còn áp dụng

- OpenJDK **JEP 310 — Application Class-Data Sharing** (Java 10): https://openjdk.org/jeps/310
- Oracle **Java SE 27 — The java Command**, các phần *Using CDS Archives*, *Creating a Static CDS Archive File*, *Restrictions on Class Path and Module Path*: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- Oracle **Java SE 25 — Class Data Sharing** (cảnh báo `-Xshare:on` chỉ dành cho kiểm thử): https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html
- Dev.java — **CDS and AppCDS in HotSpot**: https://dev.java/learn/jvm/cps-appcds/
- Dev.java — **Java Application Launcher** (module-path restrictions): https://dev.java/learn/jvm/tools/core/java/
- Spring Framework — **Class Data Sharing (CDS)** (tương thích classpath/JAR timestamp, diagnostics): https://docs.spring.io/spring-framework/reference/integration/cds.html
- OpenJDK **JEP 483 — Ahead-of-Time Class Loading & Linking** (bối cảnh AOT hiện đại): https://openjdk.org/jeps/483
