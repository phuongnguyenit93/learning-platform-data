# Tạo và xác nhận sử dụng CDS archive bằng log nạp lớp

## 1. Kết quả cần đạt

**Class Data Sharing (CDS)** là tính năng của HotSpot giúp lưu dữ liệu các lớp Java đã được xử lý trước vào **archive** để JVM ở những lần chạy sau có thể **nạp một số lớp nhanh hơn** thay vì luôn đi lại toàn bộ đường đọc JAR và xử lý metadata như từ đầu. **Application CDS (AppCDS)** mở rộng khả năng đó tới những lớp ứng dụng/thư viện phù hợp.

Bài thực hành này hướng dẫn thực hiện trọn một chuỗi:

1. Tạo một Java application nhỏ và đóng thành **JAR** để đáp ứng các điều kiện CDS dễ kiểm chứng.
2. Chạy baseline không dùng CDS nhằm nhìn đường nạp lớp từ JAR.
3. Tạo **dynamic CDS archive** với `-XX:ArchiveClassesAtExit` rồi chạy lại.
4. Dùng **`-Xlog:class+load`** để xác minh **chính lớp của ứng dụng** được load từ **`shared objects file`**, không chỉ dựa vào sự tồn tại của file `.jsa`.
5. Tạo **static CDS archive** từ `DumpLoadedClassList` và `-Xshare:dump`, rồi xác minh tương tự.
6. Phân biệt chứng cứ **archive được map**, chứng cứ **class cụ thể được load từ archive**, và chứng cứ **startup thực sự nhanh hơn**.
7. Chẩn đoán archive không được dùng, không có lớp ứng dụng trong archive, classpath/JDK không khớp và các khác biệt ở JDK 25.

**Điểm quyết định:** File `cdslab.jsa` tồn tại **chưa chứng minh** HotSpot đã sử dụng nó. Muốn xác nhận một class cụ thể, phải đọc class-loading log trong **lần chạy sử dụng archive**, tìm tên class và nguồn `source: shared objects file` tương ứng.

### Phạm vi và phiên bản

Các ví dụ Java sử dụng **Java 17+** cùng HotSpot CDS truyền thống. Các lệnh static/dynamic CDS được tài liệu hóa trong **Oracle JDK 25 `java` manual** và có thể chạy trên nhiều bản OpenJDK HotSpot 17/21/25. Một ví dụ đã được kiểm tra với **OpenJDK 21**: chương trình in đúng hai dòng; dynamic archive và static archive đều làm `CdsHello`/`Greeting` được load từ `shared objects file`. Tên lớp, hai dòng output ứng dụng và loại đường load là những điều có thể kiểm tra; **thời gian startup, số class và kích thước archive không cố định**.

JDK 25 còn có **AOT cache** (`-XX:AOTCacheOutput`, `-XX:AOTCache`) theo JEP 483 và các cải tiến mới. AOT cache có thể làm được nhiều việc hơn CDS truyền thống. Bài này ưu tiên cách **tạo/xác nhận file `.jsa`** như đề bài, sau đó giới thiệu sự phân biệt với AOT.

## 2. Hiểu đúng CDS: chia sẻ dữ liệu lớp, không phải cache mọi thứ

Khi JVM load một class, runtime phải xử lý class-file bytes và metadata: loading, verification, linking và initialization khi được yêu cầu theo JVM semantics. Một số phần của class metadata phù hợp có thể được lưu dưới dạng **preprocessed** trong CDS archive rồi được mmap/map hiệu quả để các processes sử dụng.

~~~text
Không dùng CDS:
  JAR / runtime image
        |
        v
  Load class bytes + xử lý runtime metadata
        |
        v
  JVM tiếp tục chạy application

Dùng CDS khi tương thích:
  Archived class data (.jsa)
        |
        v
  Mapped shared archive regions
        |
        v
  Class loader lấy các archived classes phù hợp
        |
        v
  JVM tiếp tục chạy application
~~~

Những lợi ích tiềm năng:

- **Startup:** giảm công việc nạp một số classes.
- **Memory footprint:** một phần các pages archive được map có thể chia sẻ giữa nhiều JVM processes dùng cùng archive phù hợp.
- **Chi phí xử lý metadata:** giảm công việc lặp lại khi archive chứa đúng các classes app sử dụng.

**Không suy rằng:**

- CDS tự động **JIT compile sẵn mọi method**.
- Mọi class đều được load từ CDS.
- CDS bỏ toàn bộ class initialization, static initializers hoặc semantic checks.
- Có archive nghĩa startup chắc chắn nhanh hơn trong mọi workload.
- CDS sửa được chi phí network, database connection, dependency injection hay ứng dụng tự chạy trong `main`.
- Mỗi process dùng archive đều có identical startup time.

Oracle JDK 25 nêu archive chứa class data có thể chiếm **nhiều disk space hơn** class bytes trong JAR/JDK image vì được lưu ở dạng tối ưu để load nhanh. Chỉ nên archive những classes thực tế hữu ích với workload.

## 3. Default CDS, AppCDS, static và dynamic archive

| Khái niệm | Đối tượng | Cách tạo/dùng thường gặp |
| --- | --- | --- |
| **Default CDS archive** | Một tập classes nền tảng có sẵn trong JDK distribution | Thường tự động được dùng trên HotSpot hỗ trợ |
| **AppCDS** | Các classes của ứng dụng và libraries đủ điều kiện | Tạo archive từ một lượt training/demo thực tế |
| **Static archive** | Archive được tạo trước từ danh sách loaded classes | `DumpLoadedClassList` → `-Xshare:dump` |
| **Dynamic archive** | Archive bổ sung classes thu được trong lần chạy app | `-XX:ArchiveClassesAtExit=...` |
| **Base/top archive** | Dynamic archive bổ sung trên một base static archive | Default base + dynamic top; log có thể hiển thị `(top)` |
| **AOT cache JDK 25** | Container lưu AOT artifacts vượt quá phạm vi CDS truyền thống | `-XX:AOTCacheOutput=...` và `-XX:AOTCache=...` |

**Static/dynamic ở đây là cách tạo archive, không phải phân loại static/dynamic class trong Java.** Các files `.jsa` không chứa “đối tượng đang sống” để phục hồi mọi state của chương trình như một snapshot application.

Trong phần lớn HotSpot JDK builds, CDS default đã được bật nếu không dùng `-Xshare:off`. Nhưng **default archive chứa JDK/core classes không tự chứng minh class ứng dụng đã được lưu**. Để xác nhận AppCDS cần tìm nguồn của **`CdsHello` hoặc `Greeting`** — không chỉ `java.lang.Object` hay `java.lang.String`.

### Hai cấp bằng chứng

~~~text
Mức 1 — archive mapping:
  [info][cds] ... archive ... opened / mapped ...
  => archive được xét/mapped, nhưng class của app có thể vẫn load từ JAR

Mức 2 — app class source:
  [info][class,load] CdsHello source: shared objects file (top)
  => class CdsHello trong lần chạy này lấy từ shared archive
~~~

Mẫu log chỉ minh họa dạng chung; tiền tố timestamp, decorator và hậu tố `(top)` thay đổi theo VM/version/archive type.

## 4. Chuẩn bị: JDK, thư mục và cách đóng JAR

**Điều kiện đầu tiên:** có JDK 17+ trên PATH, dùng **cùng một JDK build** cho create và use archive khi muốn kết quả ổn định.

~~~bash
java -version
javac -version
jar --version
~~~

Tất cả lệnh trong phần thực hành chạy trong một **thư mục lab riêng**, không phải thư mục chứa artifacts production. Không cần cài Maven/Gradle hoặc tải third-party dependencies.

### Tạo file nguồn `CdsHello.java`

~~~java
public class CdsHello {
    public static void main(String[] args) {
        System.out.println("message=" + Greeting.message("CDS"));
        System.out.println("answer=" + Greeting.answer(40));
    }
}

class Greeting {
    static String message(String name) {
        return "Hello, " + name;
    }

    static int answer(int value) {
        return value + 2;
    }
}
~~~

Ở đây **một file Java** khai báo public class `CdsHello` và package-private class `Greeting`. `javac` tạo **hai class files**; khi chạy, class loader sẽ cần load cả hai.

**Stdout chính xác của application trong một lần chạy thành công không bật VM logs:**

~~~text
message=Hello, CDS
answer=42
~~~

Giải thích: `Greeting.message("CDS")` nối thành chuỗi `Hello, CDS`; `Greeting.answer(40)` trả 42. Cả hai thao tác không phụ thuộc timing/thread scheduling.

### Biên dịch, đóng JAR và chạy thử

**Linux/macOS shell:**

~~~bash
mkdir -p build
javac -d build CdsHello.java
jar --create --file cdslab.jar --main-class CdsHello -C build .
java -cp cdslab.jar CdsHello
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build | Out-Null
javac -d build CdsHello.java
jar --create --file cdslab.jar --main-class CdsHello -C build .
java -cp cdslab.jar CdsHello
~~~

`-C build .` yêu cầu công cụ `jar` đặt nội dung thư mục `build` vào root của JAR (gồm `CdsHello.class` và `Greeting.class`). `--main-class` ghi manifest entry nhưng ở đây có thể chạy bằng `-cp cdslab.jar CdsHello` để các lệnh tạo/dùng CDS luôn có classpath giống nhau.

**Vì sao đóng JAR thay vì chạy từ class directory?** Oracle JDK 25 CDS manual nêu khi tạo/dùng AppCDS, classpath/module path có các **restrictions đối với non-empty directories**. Dùng **một JAR** và một command line nhất quán tránh rất nhiều trường hợp “JVM có log CDS nhưng app class không archived”.

### Cảnh báo về classpath

Không đổi `-cp cdslab.jar` thành `-cp build` trong bước use và vẫn khẳng định archive tương thích. Với CDS truyền thống, **classpath của lúc tạo phải trùng hoặc là tiền tố của runtime classpath** theo điều kiện Oracle mô tả; class JAR đã bị thay đổi sau dump có thể làm archive không dùng được.

Một JAR mới đóng gói lại **có thể khiến metadata fingerprint/validation khác**. Để test archive mới, tránh biên dịch/đóng JAR lại giữa thời điểm tạo và dùng.

## 5. Baseline: log nạp lớp khi TẮT CDS

Để biết khác biệt, trước tiên chạy app **không dùng bất kỳ CDS archive** nào.

~~~bash
java -Xshare:off -Xlog:class+load=info:file=baseline-load.log -cp cdslab.jar CdsHello
~~~

Lệnh này đặt JVM option **trước** main class và chuyển **class-loading logs vào file** `baseline-load.log`; stdout trên terminal vẫn là:

~~~text
message=Hello, CDS
answer=42
~~~

Trong `baseline-load.log`, tìm `CdsHello` và `Greeting`.

**Linux/macOS:**

~~~bash
grep -E "CdsHello source:|Greeting source:" baseline-load.log
~~~

**Windows PowerShell:**

~~~powershell
Select-String -Path baseline-load.log -Pattern "CdsHello source:|Greeting source:"
~~~

**Dạng log mong đợi, không bắt buộc y hệt đường dẫn:**

~~~text
[info][class,load] CdsHello source: file:/.../cdslab.jar
[info][class,load] Greeting source: file:/.../cdslab.jar
~~~

Nếu chạy baseline với `-Xshare:off`, hai classes ứng dụng từ JAR sẽ **không có nguồn `shared objects file`**. Đường dẫn chính xác có thể là `file:/...` hoặc dạng file path khác tùy JDK/OS.

**Vì sao log nguồn lớp quan trọng?** Đây là chứng cứ về **class được load từ đâu ở runtime**, hữu ích hơn việc chỉ quan sát file archive tồn tại hay số class mà VM startup đã biết.

## 6. Luồng A: tạo dynamic CDS archive (ít bước, dễ học)

### Bước A1. Chạy “training run” để tạo archive khi JVM thoát

~~~bash
java -XX:ArchiveClassesAtExit=cdslab-dynamic.jsa -cp cdslab.jar CdsHello
~~~

Output chương trình vẫn:

~~~text
message=Hello, CDS
answer=42
~~~

Khi process thoát bình thường, HotSpot có thể ghi **`cdslab-dynamic.jsa`** (dynamic/top archive) gồm các classes phù hợp mà ứng dụng đã load, trừ những classes đã nằm trong base archive. Dynamic archive cần một **base CDS archive** (mặc định JDK thường cung cấp). Nếu base không sẵn hoặc không load được, thao tác có thể thất bại; xem diagnostic logs.

**Không tự tạo archive bằng cách rename một file JAR thành `.jsa`.** Archive là format đặc thù của HotSpot/JDK build, không phải ZIP/JAR.

### Bước A2. Xác nhận file được tạo

**Linux/macOS:**

~~~bash
ls -lh cdslab-dynamic.jsa
~~~

**Windows PowerShell:**

~~~powershell
Get-Item .\cdslab-dynamic.jsa
~~~

File tồn tại và kích thước lớn hơn 0 nghĩa thao tác tạo có artifact, **nhưng vẫn chưa đủ chứng minh use**.

### Bước A3. Chạy lại và log class loading

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:class+load=info:file=dynamic-load.log -cp cdslab.jar CdsHello
~~~

Application stdout là hai dòng như trước. Mở log để tìm:

~~~bash
grep -E "CdsHello source:|Greeting source:" dynamic-load.log
~~~

Trong **PowerShell** dùng:

~~~powershell
Select-String -Path dynamic-load.log -Pattern "CdsHello source:|Greeting source:"
~~~

**Dạng log đã kiểm nghiệm trên OpenJDK 21:**

~~~text
[info][class,load] CdsHello source: shared objects file (top)
[info][class,load] Greeting source: shared objects file (top)
~~~

Phần timestamp/decorators đứng trước `[info]` tùy phiên bản. **`(top)`** thường chỉ top/dynamic archive; giá trị quan trọng nhất là cả **class ứng dụng** có `source: shared objects file`.

### Bước A4. Đọc cả CDS mapping log (tùy chọn)

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:cds=info:file=dynamic-cds.log -cp cdslab.jar CdsHello
~~~

Log CDS có thể nói file nào được mở, mapped/validated hay vì sao một archive bị từ chối. Tuy nhiên **chỉ mapping log không chứng minh `CdsHello` được archived**; phải đối chiếu `class+load` cho chính lớp cần kiểm tra.

### Bước A5. So sánh baseline và dynamic

| Bước chạy | Log nguồn lớp `CdsHello` | Kết luận |
| --- | --- | --- |
| `-Xshare:off` | Từ `cdslab.jar` | Không dùng CDS cho class ấy |
| `-XX:ArchiveClassesAtExit=...` | Training run tạo top archive ở exit | File được tạo, chưa xác nhận use |
| `-XX:SharedArchiveFile=cdslab-dynamic.jsa` | `shared objects file (top)` khi hợp lệ | **Đã xác nhận CDS dùng cho app class này** |

**Chú ý:** nếu app chạy đúng nhưng `CdsHello` vẫn có `source: file:/.../cdslab.jar`, không được nói “AppCDS đã hoạt động cho CdsHello”. Có thể chỉ default base CDS được dùng cho JDK classes, còn app class không được archived hoặc archive bị từ chối.

## 7. Luồng B: tạo static CDS archive (classlist + dump)

Static archive minh họa cách **xác định classes từ lần chạy thử**, rồi **tạo file `.jsa` ở bước riêng**.

### Bước B1. Ghi danh sách classes đã load

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=cdslab.classlist -cp cdslab.jar CdsHello
~~~

Câu lệnh chạy chương trình, quan sát class loading trong VM và ghi **`cdslab.classlist`**. Output ứng dụng vẫn hai dòng chuẩn.

Kiểm tra danh sách:

**Linux/macOS:**

~~~bash
grep -E "CdsHello|Greeting" cdslab.classlist
~~~

**Windows PowerShell:**

~~~powershell
Select-String -Path cdslab.classlist -Pattern "CdsHello|Greeting"
~~~

File có thể chứa nhiều core/library classes và directives; **không nên tự xóa mọi dòng lạ**, bởi định dạng classlist do VM ghi. Tên lớp ở classlist thường dùng JVM internal slash form đối với packaged classes (ví dụ `example/Hello`); ví dụ lab không có package nên tên đơn giản.

### Bước B2. Dump static archive

~~~bash
java -Xshare:dump -XX:SharedArchiveFile=cdslab-static.jsa -XX:SharedClassListFile=cdslab.classlist -cp cdslab.jar
~~~

**Quan trọng:**

- Đây là lệnh **dump archive**, **không phải chạy `main`** của ứng dụng.
- `-cp cdslab.jar` phải phù hợp đường cấu hình lúc training.
- Oracle JDK 25 mô tả khi dùng `-Xshare:dump`, JVM thường chạy interpreter-only để tạo output archive deterministic. Với dump rất lớn, có thể điều chỉnh `-Xmixed` nếu phiên bản hỗ trợ và không cần dump bit-for-bit deterministic.
- Nếu dump thất bại, đọc errors/`-Xlog:cds` và sửa nguyên nhân chứ không khẳng định `cdslab-static.jsa` hợp lệ từ một file còn sót.

Kiểm tra file:

~~~bash
ls -lh cdslab-static.jsa
~~~

Trên Windows PowerShell, dùng `Get-Item .\cdslab-static.jsa`.

### Bước B3. Chạy application với static archive

~~~bash
java -XX:SharedArchiveFile=cdslab-static.jsa -Xlog:class+load=info:file=static-load.log -cp cdslab.jar CdsHello
~~~

Chương trình in:

~~~text
message=Hello, CDS
answer=42
~~~

Tìm class source:

~~~bash
grep -E "CdsHello source:|Greeting source:" static-load.log
~~~

**Dạng output đã kiểm nghiệm trên OpenJDK 21:**

~~~text
[info][class,load] CdsHello source: shared objects file
[info][class,load] Greeting source: shared objects file
~~~

Với static archive, log có thể không có `(top)`. Oracle JDK 25 `java` manual dùng marker tương đương cho class trong static AppCDS: `source: shared objects file`.

### Bước B4. Phân biệt lệnh tạo và lệnh sử dụng

| Tác vụ | Cờ chính | Đầu ra |
| --- | --- | --- |
| Liệt kê loaded classes | `-XX:DumpLoadedClassList=...` | `.classlist` |
| Tạo static archive | `-Xshare:dump` + `SharedClassListFile` + `SharedArchiveFile` | `.jsa` |
| Tạo dynamic archive | `-XX:ArchiveClassesAtExit=...` | `.jsa` khi exit |
| Dùng archive | `-XX:SharedArchiveFile=...` | Ứng dụng chạy, có thể load classes từ archive |
| Chứng minh nguồn class | `-Xlog:class+load` | `source: shared objects file` cho class cụ thể |

**Không nhầm `-XX:DumpLoadedClassList` với `-XX:SharedClassListFile`**: cái đầu **ghi classlist trong trial run**, cái sau **đọc danh sách để dump archive**.

## 8. Tùy chọn `-Xshare` và chính sách khi archive không dùng được

HotSpot có các chế độ:

| Tùy chọn | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `-Xshare:off` | Không dùng CDS | Baseline/troubleshooting |
| `-Xshare:auto` | Sử dụng archive khi khả dụng, có thể fallback | Hành vi thân thiện hơn trong production |
| `-Xshare:on` | Yêu cầu sử dụng CDS; thất bại có thể làm JVM exit | **Chẩn đoán/test**, không khuyến nghị production |
| `-Xshare:dump` | Tạo static archive | Bước build archive, không chạy ứng dụng |

Oracle JVM Guide nói rõ **`-Xshare:on` dành cho testing**: khi archive không khả dụng do JDK/options thay đổi, nó có thể làm JVM **thoát ở startup** thay vì fallback. Vì vậy không bật nó mù quáng trong production chỉ vì mong startup nhanh.

### Test fail-fast có chủ đích

Khi đã tạo đúng archive và muốn xác minh archive thực sự dùng được, trong lab có thể chạy:

~~~bash
java -Xshare:on -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:cds=info -cp cdslab.jar CdsHello
~~~

Nếu JDK/flags/archive không phù hợp, JVM có thể báo lỗi và exit. Lệnh này **không thay thế log `class+load`** để xác nhận **lớp nào** đã được load từ archive. Dùng `-Xshare:auto` (hoặc default tùy bản JDK) trong môi trường ứng dụng thật khi ưu tiên fallback an toàn.

## 9. Phân biệt “archive mapped” và “class X được share”

Một pattern lỗi thường gặp:

~~~text
[info][cds] Opened archive ... ...
[info][class,load] java.lang.Object source: shared objects file
[info][class,load] CdsHello source: file:/.../cdslab.jar
~~~

**Kết luận đúng:** JVM có dùng CDS cho ít nhất một **JDK class**, nhưng **chưa xác nhận AppCDS cho `CdsHello`**. Có thể dynamic archive không có class đó hoặc không dùng được, trong khi default/base archive vẫn hoạt động.

Đối chứng đủ mạnh cho bài:

~~~text
(1) cdslab-dynamic.jsa tồn tại
(2) runtime command thực sự chỉ định cdslab-dynamic.jsa
(3) class+load log có:
    CdsHello source: shared objects file (top)
    Greeting source: shared objects file (top)
(4) application stdout đúng hai dòng
~~~

Đủ để nói **archive này đang cung cấp những app classes đó trong lần chạy đã quan sát**. Vẫn **chưa** đủ chứng minh lợi ích startup bằng một số ms cụ thể.

### `class+load` xuất log lúc nào?

`-Xlog:class+load=info` là **Unified Logging** cho class loading. Nếu đưa `:file=...`, log được ghi vào file; nếu bỏ output spec, logs thường đi tới output mặc định JVM.

Ví dụ hiện trực tiếp trong terminal:

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:class+load=info -cp cdslab.jar CdsHello
~~~

**Ở lần chạy này terminal output gồm cả class logs và hai dòng app**. Không được ghi một “stdout chính xác chỉ hai dòng” cho toàn process khi bật class logs ra console.

Khi dùng output-to-file như các bước ở trên, hai dòng application stdout vẫn riêng, còn `.log` chứa logs. Nhưng `stderr` vẫn có thể chứa warnings/errors ngoài class logs tùy JVM.

## 10. Công cụ lọc log trên Linux/macOS và Windows

### Linux/macOS: lọc bằng grep

~~~bash
grep -E "CdsHello source:|Greeting source:" dynamic-load.log
grep -E "shared objects file|source: file:" dynamic-load.log
grep -E "CdsHello source:|Greeting source:" static-load.log
~~~

### Windows PowerShell: lọc bằng Select-String

~~~powershell
Select-String -Path .\dynamic-load.log -Pattern "CdsHello source:|Greeting source:"
Select-String -Path .\static-load.log -Pattern "CdsHello source:|Greeting source:"
~~~

Để tìm tất cả class-load sources, có thể mở file log bằng editor có search thay vì in toàn bộ log ra console.

**Không dùng regex quá rộng kiểu chỉ tìm chữ “shared” rồi kết luận:** JDK core classes trong default archive sẽ gây false positive. Phải tìm **đúng class tên `CdsHello`/`Greeting`** hoặc class mục tiêu của ứng dụng thực.

### Log markers theo JVM/JDK

Các dòng class logging có thể có:

- timestamp `[0.024s]`;
- tags `[info][class,load]`;
- tên lớp với dot notation;
- `source: shared objects file`, có hoặc không `(top)`;
- path đến JAR hoặc module image;
- các thông tin khác khi bật mức `debug`/`trace`.

**Không dùng exact timestamp hay vị trí ký tự làm assertion bền vững.** So marker nguồn class sau khi xác định đúng class/JVM phiên bản.

## 11. Log `-Xlog:cds` để chẩn đoán mapping và fallback

Một câu lệnh hữu ích:

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:cds=info:file=cds-check.log -Xlog:class+load=info:file=class-check.log -cp cdslab.jar CdsHello
~~~

Trong HotSpot Unified Logging, các cờ `-Xlog` tương ứng có thể dùng để chỉ các bộ tag/output khác nhau; xác nhận bằng `java -Xlog:help` trên JDK hiện tại. Nếu format hoặc tùy chọn log bị từ chối, ưu tiên chạy **mỗi log trong một process test riêng** với options đơn giản như những ví dụ các bước trước.

`cds-check.log` có thể giúp phát hiện:

- Lý do archive không mở được;
- Archive/base mismatch;
- Validation/JAR path issues;
- Layout/mapping memory issues;
- Vì sao archived class metadata bị vô hiệu hóa;
- Một số flags/module options làm CDS không tương thích.

`class-check.log` chỉ rõ **classes nào nạp từ nguồn nào**.

**Không đánh đồng `source: shared objects file` với `source: jrt:/...`**. JRT module image có thể là nguồn ordinary class loading khi CDS bị tắt; nó không phải marker dùng archived class data.

## 12. Điều kiện tương thích của AppCDS archive

Oracle JDK 25 `java` manual có restrictions đáng nhớ:

1. **Classpath và module path:** CDS có các giới hạn với **non-empty directories**; hướng lab dùng **JAR** và `-cp cdslab.jar` để tránh.
2. **Classpath consistency:** classpath lúc dump phải là chính nó hoặc một prefix của classpath runtime trong các trường hợp hỗ trợ.
3. **JAR modification:** Nếu JAR trong classpath/module path thay đổi sau khi dump, archive có thể không được load.
4. **JDK build:** archive là **build-specific**; tạo bằng JDK này rồi đổi JDK runtime khác có thể không tương thích.
5. **Modules:** những tùy chọn như `--module-path`, `--module`, `--add-modules` và `--enable-native-access` cần nhất quán theo documented conditions.
6. **Một số module flags:** `--upgrade-module-path`, `--patch-module` hoặc `--limit-modules` có thể vô hiệu hóa CDS theo Oracle JDK 25.
7. **Custom class loaders:** khả năng archive/reuse class còn phụ thuộc loader behavior và phần HotSpot support; không mặc định mọi generated/dynamic class đều share được.
8. **VM flags/diagnostics:** GC/compiler/JVMTI hoặc other runtime flags có thể ảnh hưởng archive mapping/compatibility tùy version.
9. **File access/security:** archive phải readable, có đường dẫn đúng và không bị thay đổi trái phép.

**Cảnh báo an toàn:** CDS archives chứa dữ liệu dùng bởi JVM runtime. Chỉ dùng archives từ build/training pipeline tin cậy, với file permissions ngăn sửa trái phép. Oracle nêu `-XX:+VerifySharedSpaces` để kiểm tra integrity bằng CRC32 chống corruption vô ý, **không phải giải pháp bảo mật toàn diện chống kẻ tấn công sửa file**.

### Ví dụ điều kiện bị phá

~~~text
Tạo:
  java -XX:ArchiveClassesAtExit=cdslab-dynamic.jsa -cp cdslab.jar CdsHello

Sau đó:
  javac -d build CdsHello.java
  jar --create --file cdslab.jar --main-class CdsHello -C build .
  (đóng lại JAR giữa hai lần)

Dùng:
  java -XX:SharedArchiveFile=cdslab-dynamic.jsa -cp cdslab.jar CdsHello

Khả năng:
  archive mismatch/rejected hoặc app class không loaded từ archive
~~~

**Không đảm bảo** mọi JAR repack đều luôn fail, nhưng coi archive phải **recreate** sau khi thay đổi binary/JAR là chính sách đúng cho deployment đáng tin.

## 13. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Khả năng nguyên nhân | Bước kiểm tra |
| --- | --- | --- |
| Không thấy file `.jsa` | Training process không exit thành công; flag/path sai | Kiểm tra exit code, stderr và `-Xlog:cds` |
| Archive tồn tại nhưng app class từ JAR | Không chứa app class hoặc archive không được dùng | `class+load` đúng tên app class và `-Xlog:cds` |
| Chỉ `java.lang.Object` có shared source | Default CDS đã dùng, chưa chắc AppCDS | Tìm `CdsHello`/`Greeting` |
| Lỗi `Unrecognized VM option` | JVM không hỗ trợ flag/JDK sai | `java -version`, docs theo bản, VM vendor |
| “base archive not loaded” khi dump dynamic | Default/base CDS không khả dụng | Thử default archive, kiểm tra `-Xshare:off` không được bật |
| Static dump không tạo output app | Bình thường: `-Xshare:dump` chỉ dump, không chạy main | Kiểm tra file archive/log và bước runtime sau |
| Không thấy class trong classlist | Trial run không load class đó | Điều chỉnh training workload, rồi dump lại |
| CDS không dùng khi classpath là directory | CDS restrictions đối với non-empty directories | Đóng JAR, giữ classpath nhất quán |
| Mới thay JAR/version JDK | Incompatible archive | Recreate archive trên đúng deployment build |
| Chỉ chạy với `-Xshare:on` và VM exit | Strict mode fail fast | Đọc log; dùng `auto` trong production phù hợp |
| Log ghi `jrt:/...` thay vì shared | Class load bình thường từ runtime image | Kiểm tra archive/source của đúng class |
| Startup không nhanh hơn rõ | Workload nhỏ, class loading không chi phối, system noise | Benchmark nhiều process starts, đo đúng metric |
| File `.jsa` shared giữa các pods nhưng lỗi ở vài nodes | JDK/OS/architecture/flags khác | Đối chiếu build/container image và runtime configuration |
| Có `source: shared objects file (top)` nhưng output sai | Lỗi app khác; CDS không thay semantic correctness | Kiểm tra program logic, classpath và logs |

### Dọn file cũ để tránh đọc nhầm

Khi làm lại thí nghiệm, **không ghi đè ngẫu nhiên archive đã được process khác dùng**. Hãy tạo lab directory riêng hoặc đổi tên archive/trace logs; xóa file cũ chỉ khi xác định chắc chúng thuộc lab.

Trong automation, một file archive tạo từ JDK build không đúng có thể còn trên disk; một đường dẫn `SharedArchiveFile` đã được dùng không có nghĩa nó đang mapped. **Luôn kiểm tra class source log ở runtime**.

## 14. Khi tạo dynamic archive từ runtime đang chạy

Oracle JDK 25 tài liệu hóa các lựa chọn với `jcmd VM.cds` cho JVM **đang chạy**:

~~~text
jcmd <pid> VM.cds static_dump my_static_archive.jsa
jcmd <pid> VM.cds dynamic_dump my_dynamic_archive.jsa
~~~

Đây là **các lệnh mẫu**, thay `<pid>` bằng PID của JVM được phép thao tác; không copy thẳng dấu angle brackets khi chạy shell.

Theo tài liệu JDK 25, muốn gọi `VM.cds dynamic_dump` thì target JVM phải được khởi động với `-XX:+RecordDynamicDumpInfo`. `jcmd` có thêm điều kiện permissions/attach và tác động vận hành, nên không dùng vào process production chưa có quyền/quy trình phù hợp.

### Khi nào dùng `jcmd VM.cds`?

- App có startup script phức tạp, khó thêm flag training sớm.
- Muốn dump một snapshot classes đã load sau một traffic/workflow có đại diện.
- Muốn tránh xây classlist/dump ngoài application lifecycle theo cách thủ công.

**Không thay bước xác nhận cuối:** dù archive được tạo qua `jcmd`, vẫn phải **restart/new JVM với `-XX:SharedArchiveFile`**, sau đó đọc `class+load` cho class mục tiêu.

## 15. `-XX:+AutoCreateSharedArchive` trên HotSpot hiện đại

Oracle JDK 25 còn mô tả cách tiện lợi:

~~~bash
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=cdslab-auto.jsa -cp cdslab.jar CdsHello
~~~

Trong những phiên bản có tính năng này, nếu file chưa tồn tại thì VM có thể tạo dynamic archive ở exit. Lần chạy sau với **cùng command line** có thể dùng archive đã tạo khi tương thích.

Ưu điểm: tránh phải nhớ riêng training run và runtime command. Nhưng:

- Chính sách **recreate/replace** archive phụ thuộc version của JDK đã tạo nó; Oracle JDK 25 phân biệt archives trước và sau JDK 19.
- File archive vẫn có build/version compatibility constraints.
- Cần kiểm tra `CdsHello source: shared objects file` trong **lần chạy tiếp theo**, không chỉ lần đầu tạo.
- Dùng `-Xlog:cds` nếu archive không dùng được.

Tính năng này không phải yêu cầu của Java language, không có trên mọi vendor/JDK; với người học, luồng dynamic 2-step ở phần 6 dễ lý giải hơn.

## 16. Static vs dynamic: chọn cách nào?

| Tiêu chí | Static (`-Xshare:dump`) | Dynamic (`ArchiveClassesAtExit`) |
| --- | --- | --- |
| Bước training | Ghi `.classlist` | Chạy app để record classes và dump ở exit |
| Bước dump | Tách riêng, có `-Xshare:dump` | Thường ngay khi JVM exit |
| Base archive | Có thể tạo static riêng | Cần base static archive phù hợp |
| Độ phức tạp lệnh | Nhiều bước hơn | Ít bước hơn |
| Kích thước | Có thể bao gồm nhiều classes hơn | Thường nhỏ hơn vì không lặp classes đã trong base |
| Optimizations | Có thể hỗ trợ một số tối ưu đầy đủ hơn | Một số optimizations ít hơn static |
| Xác minh use | `SharedArchiveFile` + `class+load` | Như static, có thể thấy `(top)` |
| Khi thuận tiện | Build pipeline/classlist có kiểm soát | Trial run của app rồi dùng lại |
| Đối chứng học tập | Rõ separation trial/dump/run | Rõ archive-at-exit/run |

Theo Oracle JDK 25, **dynamic archive tuy tiện lợi nhưng hỗ trợ ít tối ưu hơn static archive** trong một số tình huống; với những tối ưu đầy đủ hơn ở JDK 25, hãy cân nhắc **AOT cache**.

## 17. CDS so với AOT Cache ở JDK 25

JDK 24/25 hỗ trợ **Ahead-of-Time Cache** (`.aot`), được giới thiệu qua **JEP 483** và mở rộng thêm AOT method profiling trên JDK 25 (**JEP 515**). AOT cache có thể lưu artifacts **bên cạnh** class data để cải thiện startup và warmup.

Phân biệt:

- **`cdslab-dynamic.jsa` / `cdslab-static.jsa`:** CDS archive truyền thống.
- **`cdslab.aot`:** AOT cache từ JDK 24+ theo các tùy chọn riêng, có thể bao gồm additional artifacts.
- `-XX:SharedArchiveFile` dùng cho CDS; `-XX:AOTCache` dùng cho AOT cache.
- `-Xlog:class+load` vẫn hữu ích để biết nguồn class; `-Xlog:aot` cung cấp những thông tin riêng khi xử lý AOT cache.

### Bài thử bổ sung chỉ dành cho JDK 25 hỗ trợ

~~~bash
java -XX:AOTCacheOutput=cdslab.aot -cp cdslab.jar CdsHello
java -XX:AOTCache=cdslab.aot -Xlog:aot=info -Xlog:class+load=info:file=aot-load.log -cp cdslab.jar CdsHello
~~~

Theo Oracle JDK 25 `java` manual, `AOTCacheOutput` có thể thực hiện training và khởi chạy assembly VM bổ sung để tạo file cache. Chính sách và tính tương thích có các điều kiện **application/JDK/OS/CPU**; không dùng câu lệnh JDK 25 này như một ví dụ bảo đảm chạy được ở Java 17.

**Mục tiêu chính bài học vẫn là CDS `.jsa`.** Không trộn hai loại artifact rồi nói `.aot` và `.jsa` tương đương, hoặc áp danh sách flags AOT cho tất cả Java versions.

## 18. Vì sao classload log chưa chứng minh startup nhanh hơn?

**Chứng cứ correctness:** `CdsHello source: shared objects file` chứng minh class cụ thể lấy từ archive.

**Chứng cứ performance:** phải **đo thời gian startup** qua nhiều lần chạy/processes với cùng workload, JVM build, CPU load và memory conditions. Điều này độc lập với correctness.

Ví dụ thí nghiệm:

~~~bash
java -Xshare:off -cp cdslab.jar CdsHello
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -cp cdslab.jar CdsHello
~~~

Không thể chỉ nhìn hai lần output rồi kết luận giảm bao nhiêu ms. Với app nhỏ này, process startup, JVM initialization, JIT/class loading, filesystem cache và scheduler noise có thể lớn hơn phần lợi ích của riêng AppCDS.

### Quy trình đo đáng tin hơn

1. Giữ **cùng JDK build, flags không liên quan và JAR**.
2. Chạy nhiều **process starts** độc lập ở hai modes: baseline không CDS và AppCDS.
3. Đo wall-clock/process-start-to-ready metric phù hợp với sản phẩm, không chỉ thời gian trong `main`.
4. Tránh bật verbose logs trong những lần đo chính, vì logging thêm overhead.
5. Với server, dùng readiness/first request latency trên workload đại diện; không chỉ đo `System.nanoTime` trong `main`.
6. Ghi median, P95, variation, CPU/load và memory footprint.
7. Xác minh trước bằng class-source logs rằng AppCDS thực sự hoạt động, sau đó mới benchmark.

**Một cải thiện nhỏ hoặc không rõ rệt trên `CdsHello` không phủ nhận CDS:** ví dụ cực nhỏ không đại diện cho ứng dụng có hàng nghìn classes. Ngược lại, archive mapped không bảo đảm startup production cải thiện nếu bottleneck là I/O/network hoặc application initialization.

## 19. Những hiểu nhầm thường gặp

| Phát biểu sai | Cách hiểu đúng |
| --- | --- |
| “Có file `.jsa` là JVM đã dùng.” | File tồn tại chỉ chứng minh có artifact; cần runtime `class+load`/`cds`. |
| “Thấy `java.lang.Object` từ shared là app archived.” | Chỉ có thể là default JDK CDS; kiểm tra app class. |
| “App class loaded từ `cdslab.jar` chứng minh AppCDS.” | Ngược lại, đó là dấu hiệu class này **không** load từ archive ở lần đó. |
| “Dynamic archive và static archive được tạo bằng cùng lệnh.” | Dynamic `ArchiveClassesAtExit`, static classlist + `Xshare:dump`. |
| “`DumpLoadedClassList` tạo `.jsa`.” | Nó tạo classlist, không phải archive. |
| “`Xshare:dump` chạy `main` của application.” | Nó dump archive, không phải chạy app. |
| “CDS luôn cache JIT machine code.” | CDS truyền thống tập trung class data; JDK 25 AOT cache có phạm vi khác. |
| “CDS làm bỏ mọi class initialization.” | Không, phải giữ Java semantics của init/linking. |
| “Mọi classpath directory đều được AppCDS hỗ trợ.” | Có restrictions với non-empty directories. |
| “Đổi JDK nhưng reuse `.jsa` chắc chắn ổn.” | Archives phụ thuộc bản/build; recreate khi thay deployment. |
| “Tạo rồi repack JAR không ảnh hưởng.” | Modified JAR có thể invalidate archive. |
| “Đổi classpath thứ tự tùy ý không ảnh hưởng.” | CDS yêu cầu path consistency. |
| “`-Xshare:on` an toàn hơn `auto` cho production.” | `on` là strict/testing, có thể exit nếu archive lỗi. |
| “`-Xshare:off` chỉ tắt AppCDS, vẫn giữ base CDS.” | `off` tắt class sharing trong lần chạy đó. |
| “`source: shared objects file (top)` là JAR path.” | Là marker dynamic top archive trong HotSpot class-load log. |
| “Log nào có chữ shared đều đủ.” | Phải xem đúng class được kiểm chứng. |
| “Archived class lúc nào cũng nhanh hơn mọi loading path.” | Lợi ích phụ thuộc workload và môi trường. |
| “CDS hỗ trợ bất kỳ custom loader/generated class.” | Eligibility theo HotSpot/loader/version. |
| “AOT cache của JDK 25 chính là file `.jsa`.” | AOT dùng artifact/options riêng, có optimizations bổ sung. |
| “Startup nhanh hơn một lần chạy đủ làm kết luận.” | Phải đo nhiều lần và cùng điều kiện. |

## 20. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** CDS là gì?  
**Đáp án:** HotSpot chia sẻ dữ liệu classes đã được xử lý trước trong archive để giảm một phần chi phí class loading và có thể giảm memory footprint giữa JVM processes.

**Câu 2.** Vì sao đóng ứng dụng thành JAR trong thí nghiệm?  
**Đáp án:** Để dùng classpath phù hợp với AppCDS restrictions, dễ tạo archive và tái lập runtime path.

**Câu 3.** Lệnh tạo dynamic archive là gì?  
**Đáp án:** `java -XX:ArchiveClassesAtExit=cdslab-dynamic.jsa -cp cdslab.jar CdsHello`.

**Câu 4.** Lệnh nào xác nhận class load source?  
**Đáp án:** Run với `-XX:SharedArchiveFile=...` và `-Xlog:class+load=info`, tìm `CdsHello source: shared objects file`.

**Câu 5.** Vì sao `java.lang.Object source: shared objects file` chưa chứng minh AppCDS?  
**Đáp án:** Đó có thể là JDK default archive; phải kiểm tra chính app classes.

**Câu 6.** Static CDS cần hai bước nào trước khi dùng?  
**Đáp án:** `DumpLoadedClassList` để ghi danh sách classes rồi `-Xshare:dump` cùng `SharedClassListFile` để tạo archive.

**Câu 7.** `-Xshare:dump` có in `message=Hello, CDS` không?  
**Đáp án:** Không, đó là bước dump, không chạy `main`. Hai dòng output thuộc các app training/use runs.

**Câu 8.** Nếu file `.jsa` tồn tại nhưng `CdsHello` vẫn `source: file:/...jar` thì sao?  
**Đáp án:** Không được tuyên bố class này dùng AppCDS; kiểm tra CDS logs/compatibility/contents.

**Câu 9.** Vì sao thay JAR sau khi archive được tạo là nguy hiểm?  
**Đáp án:** Classpath/JAR consistency validation có thể làm archive invalid; cần recreate theo build mới.

**Câu 10.** Dùng `-Xshare:on` cho production có rủi ro gì?  
**Đáp án:** Strict mode có thể khiến JVM exit nếu archive không dùng được; Oracle hướng dẫn nó cho testing.

**Câu 11.** Khi nào dùng `jcmd VM.cds`?  
**Đáp án:** Khi muốn dump từ process JVM đang chạy, với quyền attach và điều kiện flags thích hợp.

**Câu 12.** `shared objects file (top)` thường gợi ý điều gì?  
**Đáp án:** Class được load từ top/dynamic archive trên base archive trong phiên bản HotSpot tương ứng.

**Câu 13.** JDK 25 `AOTCacheOutput` có giống `ArchiveClassesAtExit` không?  
**Đáp án:** Không. AOT cache là container cho thêm optimizations, dùng file/options riêng.

**Câu 14.** Log xác nhận archived class có đủ kết luận startup giảm 20% không?  
**Đáp án:** Không. Cần benchmark end-to-end startup với nhiều runs và conditions kiểm soát.

## 21. Checklist thực hành

- [ ] `java -version` dùng đúng JDK HotSpot 17+ trong tất cả bước.
- [ ] `CdsHello.java` biên dịch thành hai class files và đóng vào `cdslab.jar`.
- [ ] Baseline `-Xshare:off` load `CdsHello` từ JAR.
- [ ] Dynamic training run tạo `cdslab-dynamic.jsa`.
- [ ] Runtime run dùng `-XX:SharedArchiveFile=cdslab-dynamic.jsa`.
- [ ] `dynamic-load.log` có **`CdsHello source: shared objects file`** và **`Greeting source: shared objects file`**.
- [ ] Static trial run tạo `cdslab.classlist` có `CdsHello` và `Greeting`.
- [ ] `-Xshare:dump` tạo `cdslab-static.jsa`.
- [ ] `static-load.log` có shared source của đúng app classes.
- [ ] Tất cả lần chạy app thành công cho `message=Hello, CDS` / `answer=42`.
- [ ] JDK/JAR/classpath/options không đổi giữa create và use.
- [ ] Nếu cần chứng minh performance, đo startup nhiều lần **không bật verbose logs** trong measurement.

Checklist này chứng minh **quy trình tạo + sử dụng + quan sát**, tránh nhầm một file archive đã xuất hiện với một tối ưu thật đang được áp dụng.

## 22. Tài liệu chính thức

- [Oracle JDK 25 — `java` Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `SharedArchiveFile`, `DumpLoadedClassList`, `SharedClassListFile`, `ArchiveClassesAtExit`, `Xshare:dump`, `AutoCreateSharedArchive`, `jcmd VM.cds`, classpath restrictions và ví dụ log `source: shared objects file`.
- [Oracle JDK 25 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/25/vm/index.html): **Class Data Sharing**; giải thích `-Xshare:off`, `-Xshare:on`, `-Xshare:auto`, khi strict mode dành cho test.
- [Oracle JDK 25 — `java` Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): `-Xlog:class+load` và `-Xlog:cds` để quan sát.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): đưa archived application classes vào AppCDS.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): archive được tạo khi application thoát, dựa trên base archive.
- [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): bối cảnh default CDS archive trong JDK.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache và cách training/assembly/use.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): AOT method profiles trong JDK 25, mở rộng khái niệm warmup.
- [Oracle JDK 25 — `jcmd` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.cds` options để dump từ JVM process phù hợp.
- [OpenJDK — `java` Application Launcher Guide](https://dev.java/learn/jvm/tools/core/java/): giải thích dynamic CDS archive và cách sử dụng base/top files.

**Kết luận:** Để chứng minh đã tận dụng **CDS/AppCDS**, cần đủ **(1) file archive tạo thành công, (2) process thực sự khởi chạy với archive tương thích, (3) `-Xlog:class+load` xác nhận chính class ứng dụng lấy từ `shared objects file`**. Dynamic CDS thường đơn giản qua `ArchiveClassesAtExit`; static CDS đi qua `DumpLoadedClassList` và `-Xshare:dump`. Thời gian startup nhanh hơn là **một khẳng định cần benchmark riêng**, không phải điều tự động được chứng minh từ log nạp lớp.