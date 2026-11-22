# AppCDS mở rộng dữ liệu chia sẻ sang lớp ứng dụng

**Chủ đề:** Nền tảng AppCDS — Java 10 và các JDK hiện đại.

**Application Class-Data Sharing (AppCDS)** mở rộng cơ chế **Class Data Sharing (CDS)** của HotSpot: thay vì chủ yếu tái sử dụng dữ liệu lớp thuộc nền tảng Java, JVM còn có thể đặt **các lớp thực sự được ứng dụng và thư viện của nó sử dụng** vào một **shared class-data archive** (thường là tệp `.jsa`). Lần khởi động tiếp theo, JVM có thể ánh xạ dữ liệu lớp đã được chuẩn bị sẵn từ archive, giảm một phần công việc đọc/định dạng class và có thể giảm bộ nhớ vật lý dùng chung khi nhiều tiến trình JVM chạy trên cùng máy.

**JEP 310 — Application Class-Data Sharing** đưa AppCDS vào **Java 10**. Ý tưởng cốt lõi này vẫn có giá trị và các cơ chế CDS/AppCDS vẫn được tài liệu JDK hiện hành mô tả. Tuy nhiên, **các cờ mở khóa thương mại/AppCDS từng xuất hiện ở tài liệu Java 10 đã lỗi thời** và không được sử dụng trong hướng dẫn thực hành hôm nay. Thay vào đó, bài dùng các lệnh HotSpot đang được hỗ trợ như `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, `-XX:+AutoCreateSharedArchive` và `-Xlog:class+load`. Với JDK mới hơn, cũng cần biết **Ahead-of-Time (AOT) cache** — hướng tối ưu rộng hơn, xuất hiện từ JDK 24 và được cải tiến ở các release sau.

Bài giải thích chính xác **những gì được chia sẻ, những gì không được chia sẻ**, cách tạo và kiểm tra archive cho một JAR ứng dụng, khác biệt giữa static/dynamic/auto archive, các điều kiện tương thích và cách quyết định có nên dùng trong production. Các lệnh AppCDS minh họa đã được thử trên **JDK 24.0.2**, với chương trình biên dịch bằng `javac --release 10`.

## 1. CDS khác AppCDS ở đâu?

Khi chạy một ứng dụng Java thông thường, JVM phải tìm, đọc, kiểm tra, liên kết và sử dụng thông tin class. Ở các lần chạy khác nhau của cùng một ứng dụng, rất nhiều class giống nhau được tải lặp lại, nhất là class thư viện và class nằm trên đường khởi động quan trọng.

**CDS** cung cấp một archive chứa dữ liệu lớp đã chuẩn bị sẵn để JVM có thể tái sử dụng một phần công việc và ánh xạ các vùng metadata phù hợp. **AppCDS** đưa cơ chế đó đến **lớp của ứng dụng** chứ không chỉ các lớp thường dùng của JDK.

| Khía cạnh | CDS nền tảng | AppCDS |
| --- | --- | --- |
| Trọng tâm dữ liệu | Các class của JDK/runtime thường được dùng | **Bổ sung class ứng dụng và các thư viện ứng dụng sử dụng** |
| Nguồn class | Runtime image và nguồn được JVM cho phép | Có thể có JAR trên application class path, module path và các nguồn phù hợp theo hỗ trợ của JDK |
| Tác động mong đợi | Giảm công việc tải/chuẩn bị class JDK | Giảm thêm phần tải/chuẩn bị class ứng dụng |
| Mục tiêu hiệu năng | Startup và footprint | Startup và footprint, đặc biệt khi nhiều JVM cùng dùng archive |
| Bảo toàn ngữ nghĩa chương trình | Có | Có: archive là **tối ưu hóa khởi động**, không thay business logic |
| Thay thế cho Java heap hoặc database cache? | Không | **Không** |

Điểm quan trọng là **AppCDS mở rộng phạm vi class**, không thay đổi ngôn ngữ Java và không biến object thành dữ liệu dùng chung giữa các JVM.

### Bức tranh luồng xử lý

~~~text
               KHÔNG DÙNG ARCHIVE ỨNG DỤNG
demo.jar -> đọc .class -> JVM xử lý metadata -> chạy ứng dụng
                         (làm lại ở lần JVM kế tiếp)

               CÓ APP CDS ARCHIVE
lần tạo archive: demo.jar -> các class thực sự được tải -> demo.jsa
lần chạy sau:    demo.jsa -> JVM ánh xạ dữ liệu lớp đã lưu -> chạy ứng dụng
                       \-> các class không có trong archive vẫn tải bình thường
~~~

Sơ đồ này giản lược việc JVM xác minh tính tương thích, class loading và khởi tạo class. **Không phải mọi class, mọi bytecode hoặc mọi dữ liệu đều được dùng trực tiếp từ archive**. JVM chỉ sử dụng những entry thích hợp và tiếp tục cơ chế tải class bình thường cho các phần khác.

## 2. AppCDS thực sự chia sẻ cái gì?

Thông tin có thể được chia sẻ là **dữ liệu lớp đã được JVM chuẩn bị dưới dạng thích hợp**, thường gọi là **class metadata** và các cấu trúc chỉ đọc liên quan do HotSpot quản lý. Archive được lưu trên đĩa, rồi các trang bộ nhớ phù hợp được **memory-map** khi JVM chạy.

Điều này có hai ý nghĩa:

1. **Khởi động:** JVM có thể tránh một phần thao tác đọc, phân tích, xác minh/chuẩn bị metadata vốn phải làm lại khi lấy class từ JAR.
2. **Bộ nhớ:** một số trang archive chỉ đọc có thể được hệ điều hành dùng chung giữa nhiều JVM trên cùng host, thay vì mỗi tiến trình duy trì bản sao dữ liệu lớp riêng.

**Nhưng AppCDS không mặc định chia sẻ:**

- Đối tượng business mới được tạo bằng `new` ở runtime, như `Order`, `User`, `ArrayList` hoặc một cache riêng trong heap.
- Giá trị mutable của các static field ở từng tiến trình ứng dụng.
- Thread, socket, JDBC connection, transaction, HTTP session hoặc file handle.
- Kết quả trả về của một REST request hay dữ liệu đang lưu trong database.
- Toàn bộ native code đã được JIT biên dịch; **AppCDS truyền thống không đồng nghĩa với một AOT cache chứa các loại tối ưu khác**.
- Toàn bộ class có trong mọi dependency JAR: một archive lấy theo workload thường chỉ phản ánh các class đã được tải trong lần tạo archive và những class đủ điều kiện.

AppCDS giúp JVM **chuẩn bị phần cấu trúc class**, không thay trách nhiệm **chạy static initializer** hoặc xây dựng trạng thái runtime theo ngữ nghĩa Java khi từng tiến trình sử dụng class.

### Không được hiểu nhầm “shared” là chia sẻ đối tượng ứng dụng

Giả sử một class có static counter:

~~~java
private static int counter;
static {
    counter++;
}
~~~

Đây là **đoạn minh họa bên trong một class**. Mỗi lần khởi động một tiến trình JVM mới trong ví dụ sẽ chạy phần khởi tạo theo ngữ nghĩa Java, vì thế kết quả `counter==1` được quan sát **cả khi có và không có AppCDS**. Archive không tạo thành một vùng chia sẻ cho counter giữa các JVM. Nếu muốn các tiến trình chia sẻ trạng thái, cần cơ chế riêng như database, shared service hoặc IPC.

## 3. Phạm vi class mà AppCDS có thể hỗ trợ

AppCDS giải quyết nhu cầu nhiều ứng dụng hiện đại tải số lượng lớn class từ framework, thư viện và mã ứng dụng. Các nguồn thường gặp là:

- **Class của JDK** nằm trong runtime image (bootstrap/platform).
- **Class ứng dụng** trong một hoặc nhiều **JAR trên class path**.
- **Class thư viện** trong các JAR dependency đã được load trong lần quan sát workload.
- **Class của ứng dụng theo module path**, trong những cấu hình được JDK hiện hành hỗ trợ.
- **Class được class loader phù hợp nạp**, kể cả một số tình huống class loader tùy chỉnh khi cơ chế archive và điều kiện định danh class tương thích.

Phạm vi cụ thể phụ thuộc **phiên bản JDK, nguồn class, class loader, module configuration và cách archive được tạo**. Không được kết luận “mọi class do bất cứ class loader nào nạp đều sẽ ở archive”.

### Những điểm thường bị bỏ sót

**Class được load mới là ứng viên:** một thư viện chứa hàng nghìn class nhưng ứng dụng chỉ dùng vài chục class trong lần tạo archive thì không cần lưu toàn bộ thư viện. Workload không đại diện sẽ bỏ sót class ít được sử dụng; chúng vẫn có thể được load theo cách bình thường ở lần chạy sau.

**JAR quan trọng hơn thư mục `.class`:** với các workflow AppCDS được mô tả trong `java` command của JDK hiện hành, các class ứng dụng cần được đóng gói thành **JAR phù hợp**. Tài liệu còn nêu giới hạn với **thư mục không rỗng** trong class path hoặc module path khi tạo/sử dụng archive. Vì vậy demo của bài tạo `demo.jar`, không đơn thuần chạy `java -cp classes demo.DemoApp` rồi giả định chắc chắn các class được archive.

**Module path cần điều kiện riêng:** các archive/CDS configuration hiện hành hỗ trợ class từ modular JAR, nhưng không coi **exploded module directory** là nguồn tương đương. Khi dùng `--module-path`, phải giữ đúng ràng buộc và các tùy chọn module của runtime.

## 4. Các cách dùng AppCDS còn phù hợp hiện nay

| Cách tạo/dùng | Yêu cầu tối thiểu hoặc bối cảnh | Dùng khi nào |
| --- | --- | --- |
| **Static archive**: `-XX:DumpLoadedClassList` → `-Xshare:dump` | Cơ chế truyền thống vẫn được tài liệu JDK hiện hành hỗ trợ | Muốn kiểm soát class list và quá trình dump tường minh |
| **Dynamic archive**: `-XX:ArchiveClassesAtExit` → `-XX:SharedArchiveFile` | Dynamic CDS Archives được bổ sung từ **JDK 13** (JEP 350) | Muốn chạy workload một lần rồi lưu class đã tải lúc JVM thoát |
| **Auto-create dynamic archive**: `-XX:+AutoCreateSharedArchive` cùng `-XX:SharedArchiveFile` | Có từ **JDK 19** | Muốn dùng một lệnh ổn định cho lần đầu tạo và lần sau tái sử dụng archive |
| **AOT cache**: `-XX:AOTCacheOutput`/`-XX:AOTCache` | AOT cache từ **JDK 24**, cách tạo gọn hơn trong **JDK 25+** | Khi JDK mới hỗ trợ và muốn cân nhắc tối ưu rộng hơn CDS truyền thống |

**Lưu ý về lịch sử:** Java 10 có thể gặp tài liệu nhắc cờ `UnlockCommercialFeatures` hoặc `UseAppCDS`. Những cờ này **không phải hướng dẫn hiện hành**. Với JDK hiện đại, **không chép nguyên command Java 10 cũ rồi thêm các cờ đó**. Thay vào đó, dùng các lựa chọn được JDK đang triển khai hỗ trợ và kiểm tra tài liệu tương ứng.

Từ JDK 12, nhiều bản JDK phân phối kèm **default CDS archive**; ở JDK hiện đại cơ chế chia sẻ lớp nền tảng thường được bật mặc định nếu có thể. Vì thế “AppCDS có thể giảm startup” **không có nghĩa** mỗi ứng dụng bắt đầu từ trạng thái hoàn toàn không có CDS.

## 5. Ví dụ thực hành — Một ứng dụng nhỏ gồm ba class riêng

Để chứng minh **lớp do chúng ta viết** thực sự được tải từ archive, hãy sử dụng một ứng dụng nhỏ đóng gói thành JAR. Cấu trúc thư mục:

~~~text
project/
  src/
    demo/
      DemoApp.java
      GreetingService.java
      RuntimeState.java
  classes/            (được tạo khi biên dịch)
  demo.jar            (được tạo khi đóng gói)
  demo.jsa            (được tạo sau lần training dynamic)
~~~

Tất cả ba file đều trong package `demo`. Không cần Maven, Gradle hay thư viện bên ngoài.

### `src/demo/DemoApp.java`

~~~java
package demo;

public class DemoApp {
    public static void main(String[] args) {
        System.out.println("greeting=" +
                new GreetingService().greet("AppCDS"));
        System.out.println("loader=" +
                DemoApp.class.getClassLoader().getName());
        System.out.println("counter=" + RuntimeState.count());
    }
}
~~~

### `src/demo/GreetingService.java`

~~~java
package demo;

public final class GreetingService {
    public String greet(String text) {
        return "Hello, " + text;
    }
}
~~~

### `src/demo/RuntimeState.java`

~~~java
package demo;

public final class RuntimeState {
    private static int counter;

    static {
        counter++;
    }

    public static int count() {
        return counter;
    }
}
~~~

Ba class có những nhiệm vụ khác nhau:

- `DemoApp` là entry point, tự nó là một class của ứng dụng.
- `GreetingService` là service class do ứng dụng tạo, không thuộc Java standard library.
- `RuntimeState` có `static` state đơn giản để chứng minh mỗi tiến trình JVM vẫn có trạng thái khởi tạo riêng.

### Biên dịch và đóng JAR

Từ thư mục `project` có ba file `src/demo/*.java` đúng như trên, chạy:

~~~bash
mkdir classes
javac --release 10 -d classes src/demo/DemoApp.java src/demo/GreetingService.java src/demo/RuntimeState.java
jar --create --file demo.jar -C classes .
~~~

Lệnh được dùng trực tiếp với JDK có `javac` và `jar`; `mkdir classes` có thể bỏ qua nếu thư mục đã có sẵn. **`javac --release 10`** đảm bảo ví dụ Java dùng cú pháp/API công khai phù hợp với Java 10. Các cờ AppCDS bên dưới là **cờ của JDK runtime** và có mốc hỗ trợ riêng; không được suy ra từ `--release 10` rằng mọi flag tồn tại trên JDK 10.

### Chạy baseline, tắt CDS chỉ cho phép đo đối chứng

~~~bash
java -Xshare:off -cp demo.jar demo.DemoApp
~~~

**Stdout ứng dụng trên HotSpot JDK kiểm thử:**

~~~text
greeting=Hello, AppCDS
loader=app
counter=1
~~~

`loader=app` là tên class loader quan sát được trong HotSpot ở ví dụ. Không dựa vào tên này như một hợp đồng phổ quát cho mọi JVM vendor. `counter=1` sẽ tiếp tục xuất hiện ở mỗi tiến trình chạy mẫu này. `-Xshare:off` **không phải lựa chọn để chạy ứng dụng nhanh hơn**: nó tắt CDS nhằm tạo baseline đối chứng.

## 6. Dynamic AppCDS: tạo archive từ chính lần chạy ứng dụng

**Dynamic CDS archives** giúp giảm số bước thực hành. Kể từ **JDK 13**, `-XX:ArchiveClassesAtExit` cho phép JVM thu thập các class đủ điều kiện được tải trong một lần chạy và tạo archive khi JVM thoát theo cơ chế bình thường.

### Bước 1 — Training và ghi `demo.jsa`

~~~bash
java -XX:ArchiveClassesAtExit=demo.jsa -cp demo.jar demo.DemoApp
~~~

Ứng dụng vẫn chạy và in:

~~~text
greeting=Hello, AppCDS
loader=app
counter=1
~~~

Khi lần chạy hoàn tất thành công, JVM tạo `demo.jsa` trong thư mục hiện tại (với cấu hình và runtime đủ điều kiện). Trong thử nghiệm trên JDK 24.0.2, tệp archive đã được tạo thành công. Với một service dài hạn, cần một **training run có điểm kết thúc rõ ràng**; nếu quy trình bị kill bất thường, không thể mặc định archive sẽ luôn được sinh ra.

### Bước 2 — Khởi động lại, yêu cầu dùng archive

~~~bash
java -XX:SharedArchiveFile=demo.jsa -cp demo.jar demo.DemoApp
~~~

Ứng dụng vẫn in **ba dòng giống trước đó**. Đó là kết quả đúng về ngữ nghĩa, nhưng **chưa đủ chứng minh** JVM thực sự đã nạp class từ archive. Cần bật log class loading.

### Bước 3 — Kiểm tra chính class ứng dụng có nguồn `shared objects file`

~~~bash
java -Xlog:class+load=info:file=appcds-load.log:tags,level -XX:SharedArchiveFile=demo.jsa -cp demo.jar demo.DemoApp
~~~

Mở tệp `appcds-load.log`, tìm các dòng chứa `demo.DemoApp`, `demo.GreetingService`, `demo.RuntimeState`. Trên HotSpot JDK 24.0.2 đã kiểm thử, các dòng liên quan có dạng:

~~~text
[info][class,load] demo.DemoApp source: shared objects file (top)
[info][class,load] demo.GreetingService source: shared objects file (top)
[info][class,load] demo.RuntimeState source: shared objects file (top)
~~~

`(top)` cho biết class được lấy từ **tầng archive động** nằm trên base CDS archive trong cơ chế JVM thử nghiệm. Dùng chính dòng `source: shared objects file` để xác nhận class ứng dụng được archive; không lấy việc nhìn thấy `demo.jsa` hay thời gian chạy tình cờ nhanh hơn làm bằng chứng duy nhất.

**Không cần `-Xshare:on` trong production**. Tài liệu JDK hiện hành lưu ý cờ đó mang tính **fail-fast để thử nghiệm**: nếu archive không tương thích, JVM có thể kết thúc ngay. Với triển khai thông thường, cơ chế chia sẻ kiểu `auto` cho phép JVM tiếp tục chạy nếu không dùng được cache, dù có thể mất lợi ích hiệu năng.

## 7. Static AppCDS: tạo danh sách class rồi dump archive

Static archive là một workflow khác vẫn được JVM và tài liệu JDK hiện hành hỗ trợ. Điểm khác chủ yếu: bạn **ghi rõ class list từ một lần chạy**, rồi đưa list đó vào lệnh dump để tạo archive.

### Bước 1 — Lấy danh sách class thực tế được dùng

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=classes.lst -cp demo.jar demo.DemoApp
~~~

`classes.lst` ghi thông tin class được tải trong lần chạy. `-Xshare:off` được dùng để ghi nhận class list theo workflow static, không phải lệnh khuyến nghị chạy production.

### Bước 2 — Dump static archive

~~~bash
java -Xshare:dump -XX:SharedClassListFile=classes.lst -XX:SharedArchiveFile=static.jsa -cp demo.jar
~~~

Lệnh dump có thể in nhiều thông tin chẩn đoán và **không chạy `main` như một lần chạy ứng dụng thông thường**. JVM xử lý danh sách và tạo tệp `static.jsa` nếu các điều kiện tương thích được đáp ứng.

### Bước 3 — Chạy với static archive và xác minh

~~~bash
java -Xlog:class+load=info:file=static-load.log:tags,level -XX:SharedArchiveFile=static.jsa -cp demo.jar demo.DemoApp
~~~

**Stdout ứng dụng** vẫn là ba dòng về greeting, loader và counter. Khi đọc log, trên JDK 24.0.2 đã kiểm thử, ba class ứng dụng có nguồn:

~~~text
[info][class,load] demo.DemoApp source: shared objects file
[info][class,load] demo.GreetingService source: shared objects file
[info][class,load] demo.RuntimeState source: shared objects file
~~~

Khác biệt nhỏ ở chuỗi log giữa **static** và **dynamic** archive là chi tiết diagnostic, không làm thay đổi ý nghĩa chương trình. Cả hai đường thử nghiệm đều **chứng minh AppCDS đã mở rộng việc tái sử dụng đến chính các class `demo.*`**, thay vì chỉ xuất hiện ở các class `java.*`.

### Chọn static hay dynamic?

- **Dynamic** thích hợp khi cần triển khai đơn giản và muốn archive các class đã đi qua một training run.
- **Static** thích hợp khi muốn kiểm soát class list hoặc có quy trình tạo archive riêng.
- **Cả hai** đều phụ thuộc tính tương thích với JDK build, JAR và cấu hình classpath/module; không thể mang một tệp `.jsa` bất kỳ sang mọi JVM rồi kỳ vọng hoạt động.

## 8. Tạo và dùng archive bằng một lệnh trên JDK 19+

Một cải tiến còn hữu ích trong JDK hiện đại là **`-XX:+AutoCreateSharedArchive`** (từ JDK 19). Lần khởi động đầu nếu chưa có archive, JVM có thể tạo nó khi thoát; các lần sau dùng lại archive tương thích, đồng thời xử lý một số trường hợp cần tạo lại theo hợp đồng của cờ.

~~~bash
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=demo-auto.jsa -cp demo.jar demo.DemoApp
~~~

Gọi **cùng lệnh** một lần nữa để xem lợi ích tái sử dụng. Nếu muốn xác minh, thêm log:

~~~bash
java -Xlog:class+load=info:file=auto-load.log:tags,level -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=demo-auto.jsa -cp demo.jar demo.DemoApp
~~~

Trong thử nghiệm độc lập trên JDK 24.0.2 với một JAR nhỏ, lần đầu lệnh này **tạo archive**, lần sau log xác nhận class ứng dụng được load từ `shared objects file (top)`. Không nên cho nhiều tiến trình **đồng thời ghi cùng một archive**. Một tiến trình tạo archive riêng, sau đó triển khai tệp đọc-only cho các JVM khác là mô hình kiểm soát dễ hơn.

### Ví dụ riêng về một class tự động archive

Để thử cơ chế một lệnh mà không dùng ba class phía trên, có thể tạo tệp **`AutomaticApp.java`**:

~~~java
public class AutomaticApp {
    public static void main(String[] args) {
        System.out.println("ready=" +
                String.join(",", "A", "B"));
    }
}
~~~

Tạo và chạy với JDK 19+:

~~~bash
mkdir automatic-classes
javac --release 10 -d automatic-classes AutomaticApp.java
jar --create --file auto.jar -C automatic-classes .
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=auto.jsa -cp auto.jar AutomaticApp
java -Xlog:class+load=info:file=auto.log:tags,level -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=auto.jsa -cp auto.jar AutomaticApp
~~~

Stdout ở cả hai lượt:

~~~text
ready=A,B
~~~

Kết quả kiểm tra log trong lượt thứ hai:

~~~text
[info][class,load] AutomaticApp source: shared objects file (top)
~~~

**Ghi chú phiên bản:** `--release 10` chỉ là mức source/API biên dịch. `-XX:+AutoCreateSharedArchive` cần **JDK runtime 19+**; không đưa lệnh này vào script dành riêng cho một HotSpot Java 10 cũ.

## 9. Khi nào archive không thể dùng hoặc không đem lại lợi ích?

JVM sẽ xác minh archive có phù hợp với classpath, JDK và các điều kiện runtime. Những trường hợp thường làm archive bị từ chối, bị vô hiệu một phần hoặc không có class ứng dụng mong muốn:

| Tình huống | Vì sao ảnh hưởng AppCDS | Cách xử lý |
| --- | --- | --- |
| Dùng archive từ **JDK build khác** | Archive gắn với dữ liệu lớp/format và build JVM cụ thể | Tạo lại archive với **JDK thực tế dùng để chạy** |
| Thay nội dung `demo.jar` sau lúc tạo archive | Class có thể thay đổi, không còn khớp archive | Build và archive cùng artifact bất biến; tạo archive lại khi phát hành |
| Đường classpath lúc training khác đường lúc chạy | Các nguồn class không còn khớp điều kiện CDS | Duy trì classpath phù hợp; Javadoc cho phép cùng classpath hoặc có quan hệ prefix trong điều kiện được mô tả |
| Có thư mục class không rỗng ở nơi archive yêu cầu JAR | Hạn chế của workflow dump/archive | Đóng gói class thành JAR như demo |
| Module flags hoặc module graph khác | Có thể không dùng được archived module graph hoặc class | Giữ cấu hình module nhất quán và xem log |
| Class được load sau training nhưng không có trong archive | Không có entry để dùng lại | Mở rộng workload training; class đó vẫn có thể load bình thường |
| Dùng custom class loader/biến đổi bytecode | Định danh/lifecycle class có thể không phù hợp | Kiểm tra khả năng tương thích class loader/agent và log |
| Dùng `-Xshare:off` | JVM được yêu cầu **không dùng** shared class data | Bỏ cờ đó ở lượt chạy cần đo AppCDS |
| Dùng `-Xshare:on` với archive không tương thích | JVM có thể fail-fast ở startup | Chỉ dùng cho test; không áp đặt cho production |
| Archive có nhưng lợi ích nhỏ | Ít class tải trong critical path, overhead khác chiếm ưu thế | Đo startup/footprint, không ép tối ưu nếu không đáng |
| Mở nhiều JVM dùng cùng archive nhưng mỗi JVM vẫn cần heap lớn | Chỉ một phần dữ liệu class được chia sẻ | Không quảng cáo AppCDS là cơ chế giảm toàn bộ heap |

**Không phải cứ có `demo.jsa` là AppCDS đang hoạt động.** Dấu hiệu xác nhận hữu ích là log `class,load` cho chính class ứng dụng và nguồn `shared objects file`, cộng với phép đo hiệu năng có đối chứng.

### Ràng buộc về classpath/module path

Theo tài liệu `java` của JDK hiện hành:

- Class path dùng khi tạo archive cần **bằng hoặc là tiền tố thích hợp** của class path lúc chạy trong phạm vi ràng buộc mà JVM công bố.
- Một JAR bị chỉnh sửa sau lúc archive được tạo có thể làm archive không sử dụng được.
- Các tham số module như `--module-path`/`--module`/`--add-modules` cần được giữ nhất quán giữa lần tạo và lần chạy; đổi chúng có thể vô hiệu một phần hoặc toàn bộ lợi ích.
- Các lựa chọn `--patch-module`, `--upgrade-module-path` hoặc `--limit-modules` có thể khiến CDS bị vô hiệu theo tài liệu JDK25.
- Tài liệu phân biệt đường dẫn dùng trên Windows và Unix. Nếu tự chỉ định **hai archive** trong `-XX:SharedArchiveFile`, dấu phân cách là **`;` trên Windows** và **`:` trên Unix-like systems**. Với **một** archive `demo.jsa` như ví dụ, không cần phân cách.

Không dùng `-XX:SharedArchiveFile=base.jsa:dynamic.jsa` nguyên xi trên Windows: trong trường hợp cần hai archive, dùng `base.jsa;dynamic.jsa` theo cú pháp của launcher.

## 10. Những điều AppCDS không làm thay ứng dụng

### Không thay đổi thứ tự thực thi logic

Các phương thức `main`, constructor, class initialization, xử lý exception và request vẫn có ngữ nghĩa Java tương ứng. Trong demo, class `RuntimeState` tăng counter lên 1 mỗi lần JVM mới bắt đầu sử dụng nó. Archive chỉ giúp **tái sử dụng biểu diễn class**; nó không “chạy main trước” hay ghi nhớ kết quả của lần chạy trước.

### Không thay thế cache dữ liệu nghiệp vụ

Nếu ứng dụng muốn giữ truy vấn SQL, response HTTP hoặc các object domain qua nhiều lần khởi động, cần một cơ chế lưu trữ/cache tương ứng. AppCDS **không tạo một persistent Java heap** để lưu mọi instance.

### Không cam kết mọi JVM sẽ nhanh hơn

Hiệu quả phụ thuộc startup pattern, mức độ reuse class, tốc độ filesystem/page cache, CPU, bộ nhớ, GC, container và số process cùng chạy. Ứng dụng chạy lâu, dành phần lớn thời gian xử lý nghiệp vụ, có thể chỉ thấy lợi ích ở startup chứ không đáng kể về throughput.

### Không làm file JAR biến mất khỏi deployment

Archive phải được đối chiếu với code/classpath có thật; nó không phải bản phân phối thay cho JAR. Không xóa source JAR rồi chỉ chạy `.jsa`. Hãy triển khai archive **cùng đúng phiên bản ứng dụng/JDK** đã dùng để tạo nó.

### Không phải cơ chế bảo mật

Archive là artifact đầu vào của JVM và cần được bảo vệ khỏi sửa đổi trái phép; không đặt nó ở vị trí ai cũng có quyền ghi rồi coi đó là cache vô hại. Xây dựng, ký/xác thực artifact nếu môi trường cần và giới hạn quyền trên file archive là một phần của quy trình triển khai an toàn.

## 11. Đo lợi ích cho đúng: startup, footprint và số lớp thực sự được reuse

Một thử nghiệm nghiêm túc cần so sánh ít nhất:

1. **Baseline:** cùng ứng dụng, cùng JDK, cùng tham số, **không dùng CDS** (ví dụ `-Xshare:off`) hoặc baseline với default CDS **nhưng không có archive AppCDS riêng**, tùy mục tiêu.
2. **Default CDS:** nếu JDK tự có archive nền tảng, đo trạng thái mặc định như một baseline thực tế của sản phẩm.
3. **AppCDS:** cùng startup workload và artifact nhưng nạp archive ứng dụng đã tạo.
4. **Mức độ chia sẻ thực:** dùng `-Xlog:class+load=info` trong các lượt chẩn đoán để xác nhận class của ứng dụng từ archive.
5. **Chỉ số đo:** wall-clock startup đến mốc sẵn sàng thực tế, số lượng class load, CPU startup, footprint của một/many JVM, và độ ổn định.
6. **Lặp lại nhiều lần:** loại nhiễu từ cache đĩa, nhiệt CPU, background process và thứ tự chạy.
7. **Không lấy kích thước `.jsa` làm thước đo hiệu năng:** có archive lớn hơn không chứng minh app chạy nhanh hơn.

### Bộ lệnh đối chứng tối thiểu

~~~bash
java -Xshare:off -cp demo.jar demo.DemoApp
java -cp demo.jar demo.DemoApp
java -XX:SharedArchiveFile=demo.jsa -cp demo.jar demo.DemoApp
~~~

Bộ ba lệnh này giúp phân biệt **tắt toàn bộ CDS**, **default CDS** và **AppCDS riêng**. Không chạy một lần rồi kết luận phần trăm tối ưu; hãy đo lặp lại với công cụ tương ứng hệ điều hành. Lưu ý `-Xlog:class+load` cũng tạo overhead I/O, nên **không bật logging chi tiết trong các lượt đo startup chuẩn**.

**Tác động bộ nhớ:** một shared archive memory-mapped có thể xuất hiện trong không gian địa chỉ và một số chỉ số RSS/working set của từng tiến trình. Muốn đánh giá khả năng tiết kiệm giữa **nhiều JVM**, cần dùng phép đo phù hợp với trang bộ nhớ được chia sẻ, tránh cộng đơn giản RSS rồi kết luận mọi trang đã được nhân bản.

## 12. AppCDS và AOT cache hiện đại: liên hệ đúng, không đánh đồng

Ở các JDK mới, kiến thức về AppCDS vẫn hữu ích nhưng không nên dừng tại mô hình Java 10. **JDK 24** đưa vào **Ahead-of-Time Cache** theo JEP 483, mở rộng phạm vi các tối ưu có thể được chuẩn bị trước khởi động. JDK 25 thêm các cải tiến như cách tạo cache gọn hơn và cơ chế method profiling được chuẩn bị trước.

| Đặc điểm | AppCDS truyền thống | AOT cache của JDK mới |
| --- | --- | --- |
| Mục tiêu trung tâm | Tái sử dụng dữ liệu lớp/metadata qua `.jsa` | Chứa tập artifact tối ưu AOT rộng hơn, dựa trên cấu hình JDK |
| Mốc có ý nghĩa | AppCDS Java 10; dynamic archive JDK 13 | AOT cache từ JDK 24; nhiều cải tiến ở JDK 25+ |
| Ví dụ điều khiển | `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile` | `-XX:AOTCacheOutput`, `-XX:AOTCache` |
| Đầu ra điển hình | `demo.jsa` | `demo.aot` |
| Mức độ tương thích | Gắn với ứng dụng, JDK build và cấu hình | Cũng gắn với app, JDK, OS/CPU, cấu hình/training |
| Khuyến nghị | Tốt để hiểu/cải thiện AppCDS, vẫn có mặt trong JDK mới | **Nên cân nhắc khi chạy JDK hỗ trợ** nếu cần tối ưu startup/warm-up rộng hơn |

**Ví dụ cho JDK 25+** theo lệnh AOT cache hiện hành (không phải lệnh có thể chạy trên Java 10 hoặc JDK 24 không hỗ trợ chế độ một bước):

~~~bash
java -XX:AOTCacheOutput=demo.aot -cp demo.jar demo.DemoApp
java -XX:AOTCache=demo.aot -cp demo.jar demo.DemoApp
~~~

Đây là **minh họa workflow theo tài liệu JDK 25**, không phải phần được chạy trong bộ thử JDK 24. Với ứng dụng thực tế, cách chuẩn bị training workload, assembly và kiểm tra tính tương thích cache tùy phiên bản JDK. **Đừng gán ý nghĩa của AOT cache mới cho `demo.jsa` AppCDS truyền thống**: chúng là những cơ chế liên quan nhưng có phạm vi khác nhau.

Khi dùng JDK mới và triển khai mới, hãy đối chiếu tài liệu runtime đang dùng để quyết định giữa **default CDS**, **AppCDS động**, **auto-create archive** và **AOT cache**. Việc AppCDS đã có từ Java 10 không khiến tính năng trở thành không liên quan, nhưng cũng không có nghĩa workflow thủ công Java 10 là lựa chọn tối ưu duy nhất vào hiện tại.

## 13. Kịch bản triển khai sản phẩm

Một hệ thống có nhiều service Java có thể áp dụng quy trình:

1. **Cố định artifact**: chọn đúng build JDK và phiên bản JAR đã được kiểm thử. Tốt nhất dùng image immutable, cùng artifact để train và chạy.
2. **Xác định mục tiêu**: cần giảm thời gian khởi động, tối ưu footprint nhiều JVM, hay cải thiện warm-up? CDS/AppCDS phù hợp với hai mục tiêu đầu, trong khi AOT cache mới có thể phù hợp hơn cho mục tiêu rộng hơn.
3. **Đóng gói JAR phù hợp**: không dựa vào thư mục `.class` không rỗng như nguồn để dump archive.
4. **Training đại diện**: khởi động và đi qua các thành phần ứng dụng thường xuất hiện trong startup/đường xử lý thiết yếu trước khi JVM tạo archive.
5. **Tạo archive**: dùng dynamic hoặc static workflow theo JDK. Trong hệ thống có CI/CD, lưu archive như artifact đi kèm JAR/build tương ứng.
6. **Xác minh**: kiểm tra exit code, archive có thật, class ứng dụng load từ archive, và các startup test vẫn PASS.
7. **Đưa vào runtime**: đặt `-XX:SharedArchiveFile` trong lệnh chạy đúng build; không để nhiều JVM cùng cố dump vào một file chung.
8. **Giám sát sau deploy**: đo startup/footprint trước–sau, quan sát log fallback/compatibility và hành vi ứng dụng.
9. **Tạo lại khi đổi**: JDK build, JAR, classpath hoặc cấu hình module quan trọng đổi thì lập quy trình đánh giá/tạo lại archive.
10. **Có đường quay lui**: nếu archive không tương thích, ứng dụng vẫn có thể chạy bằng cách không sử dụng archive khi chính sách phù hợp; không ép `-Xshare:on` ở production.

### Với container

Tạo archive từ **đúng JDK image và JAR sẽ được deploy** là lựa chọn an toàn. Nếu image/runtime build thay đổi giữa các stage, kiểm tra lại archive. Đừng mặc định archive tạo từ JDK nhà phát triển trên Windows tương thích với runtime production chạy Linux. Hãy thử trên đúng hệ điều hành, kiến trúc và build mục tiêu.

Trong hệ thống mở rộng nhiều replica, chia sẻ các trang memory-mapped trên cùng host **có thể** giúp footprint, nhưng các container tách host không có nghĩa chúng tự chia sẻ cùng trang RAM. Ảnh hưởng thực tế phụ thuộc mô hình triển khai và cách đo.

## 14. Khắc phục lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Tạo `demo.jsa` được nhưng startup không cải thiện | Startup chủ yếu do network/DB, ít lớp được reuse hoặc số đo nhiễu | Xem class load log và profile startup |
| Class `demo.DemoApp` vẫn báo load từ JAR | Archive không được dùng hoặc class không đủ điều kiện | Kiểm tra `SharedArchiveFile`, log CDS, JDK/build/classpath |
| Archive không tồn tại sau lệnh `ArchiveClassesAtExit` | JVM không thoát bình thường, đường dẫn/quyền ghi, cờ không được hỗ trợ | Kiểm tra exit code, quyền, log, đúng JDK |
| Archive bị từ chối sau nâng JDK | Archive gắn với JDK build | Tạo lại từ JDK production mới |
| Archive bị từ chối sau khi cập nhật JAR | Classpath/JAR đã khác so với lúc tạo archive | Tạo lại theo artifact JAR mới |
| Dump từ thư mục `classes/` gặp hạn chế | AppCDS archive hỗ trợ các nguồn JAR với ràng buộc cụ thể | Đóng JAR và chạy với `-cp demo.jar` |
| Lỗi khi đặt `-Xshare:on` | Cờ yêu cầu archive bắt buộc khả dụng | Chỉ dùng kiểm thử; bỏ ở production |
| Một số class chia sẻ, một số không | Training chưa load tất cả hoặc class không đủ điều kiện | Mở rộng workload, xem log từng class |
| Dữ liệu static không giữ qua lần chạy | Static state nằm trong tiến trình JVM, không được chia sẻ như cache dữ liệu | Dùng storage/IPC khác nếu cần |
| Dùng mã từ bài Java 10 cũ bị báo unrecognized VM option | Một số cờ từng dùng đã obsolete/removed | Theo tài liệu JDK hiện tại, không sao chép cờ lịch sử |
| Tệp archive bị ghi bởi nhiều replica | Race/tranh chấp khi tạo archive | Tạo riêng một lần và phân phối artifact đọc-only |
| Startup nhanh hơn nhưng total memory không giảm | Memory-mapped pages và heap còn phụ thuộc workload/cách đo | Đo nhiều process và phân biệt shared/private memory |

**Công cụ chẩn đoán:** `-Xlog:class+load=info` là cách đơn giản để xem nguồn class; các tùy chọn log về CDS/AOT cụ thể phụ thuộc JDK. Không nên lọc log chỉ theo tên `java.*`: bài đang tìm bằng chứng **lớp `demo.*` của ứng dụng** đã dùng archive.

## 15. Các ngộ nhận cần tránh

**Ngộ nhận 1 — “AppCDS chỉ chứa class Java core.”** Đây chính là điều JEP 310 mở rộng: class ứng dụng và library class có thể được archive.

**Ngộ nhận 2 — “Shared nghĩa là hai JVM dùng chung static field và object.”** Sai. Archive chia sẻ dữ liệu class phù hợp; heap/mutable runtime state thuộc từng JVM.

**Ngộ nhận 3 — “Có `.jsa` là chắc chắn JVM load mọi class từ đó.”** Sai. Phải xét tương thích, cách tạo archive và class đủ điều kiện. Xác nhận bằng log.

**Ngộ nhận 4 — “AppCDS sẽ giúp tất cả ứng dụng nhanh hơn một tỷ lệ cố định.”** Sai. Lợi ích phụ thuộc workload, cấu hình, đo đạc và nhiều yếu tố nền tảng.

**Ngộ nhận 5 — “Dynamic archive tự lưu mọi class trong mọi JAR.”** Sai. Tập class phụ thuộc những class được tải và đủ điều kiện khi tạo archive.

**Ngộ nhận 6 — “Phải bật cờ mở khóa AppCDS thương mại của Java 10 ở JDK mới.”** Sai và lỗi thời. Không dùng những cờ Java 10 đã bị loại bỏ/obsolete trong script mới.

**Ngộ nhận 7 — “CDS hoạt động giống cache biên dịch mã máy JIT.”** Không đúng với AppCDS truyền thống; tối ưu AOT mới có phạm vi khác.

**Ngộ nhận 8 — “Một archive chạy trên mọi bản JDK, OS và mọi classpath.”** Không có bảo đảm như vậy. JDK build, JAR, classpath/module và môi trường phải tương thích.

**Ngộ nhận 9 — “Static archive đã bị xóa khỏi Java hiện nay.”** Không. Static workflow vẫn được mô tả trong tài liệu `java` mới, dù dynamic/auto/AOT cache thường tiện hơn cho nhu cầu khác nhau.

**Ngộ nhận 10 — “Muốn kiểm tra AppCDS thì phải bật `-Xshare:on` ở production.”** Không. `-Xshare:on` là chế độ kiểm thử yêu cầu cache; dùng log và cấu hình an toàn hơn cho vận hành.

## 16. Checklist kiểm thử

Một bài thực hành được coi là chứng minh **AppCDS mở rộng đến lớp ứng dụng** khi đáp ứng:

1. Code có ít nhất một **class do ứng dụng tạo**, ví dụ `demo.GreetingService`, không chỉ gọi `java.lang.String`.
2. Các class được biên dịch bằng JDK phù hợp, đóng trong **JAR** và chạy bình thường bằng `-cp demo.jar demo.DemoApp`.
3. Lệnh tạo archive hoàn thành với exit code thành công, có tệp `.jsa`.
4. Lệnh startup sau đó dùng `-XX:SharedArchiveFile=demo.jsa`.
5. **Log của chính `demo.DemoApp`/`demo.GreetingService`** có `source: shared objects file` (nếu có tầng top sẽ có `(top)`).
6. Stdout ứng dụng giống nhau giữa baseline và replay, chứng minh không thay business semantics.
7. Static state được khởi tạo theo tiến trình, không coi archive là shared heap.
8. Có nhánh kiểm tra khi archive thiếu/không tương thích, không đặt `-Xshare:on` vô điều kiện trong production.
9. Classpath/JAR, JDK build và cấu hình module giữa training và replay phù hợp.
10. Workload training có đi qua các class được đo, không chỉ load entry point.
11. Kết quả performance được đo nhiều lần trên cùng điều kiện, không dựa vào một con số ngẫu nhiên.
12. Với JDK 24/25+, đã cân nhắc **AOT cache** khi mục tiêu bao gồm nhiều loại tối ưu hơn AppCDS.
13. Không dùng cờ AppCDS/UnlockCommercialFeatures đã lỗi thời.
14. Archive được bảo vệ tránh sửa đổi trái phép và phát hành cùng artifact tương ứng.

## 17. Câu hỏi tự kiểm tra

1. CDS và AppCDS khác nhau chủ yếu ở **phạm vi class** nào?
2. Vì sao một class ứng dụng nằm trong `demo.jar` có thể được tải lại nhanh hơn khi dùng AppCDS?
3. AppCDS có tự chia sẻ các object `ArrayList`, static mutable field hoặc JDBC connection giữa hai JVM không?
4. `-XX:ArchiveClassesAtExit=demo.jsa` thực hiện khi nào? `-XX:SharedArchiveFile=demo.jsa` dùng vào thời điểm nào?
5. Vì sao phải đọc `-Xlog:class+load` chứ không chỉ nhìn sự tồn tại của file `.jsa`?
6. Dòng `demo.GreetingService source: shared objects file (top)` chứng minh điều gì?
7. Static archive khác dynamic archive ở bước chuẩn bị nào?
8. `-XX:+AutoCreateSharedArchive` có từ JDK mấy? Có dùng được trên chính Java 10 không?
9. Nếu thay JAR sau khi tạo archive, có thể mặc định tái sử dụng archive không?
10. Vì sao nên dùng JAR thay vì thư mục class rời rạc trong quy trình archive được hướng dẫn?
11. Khi hai JVM cùng dùng một archive, bộ nhớ nào có thể được chia sẻ và loại bộ nhớ nào vẫn riêng?
12. Vì sao không so một lần startup rồi khẳng định AppCDS giảm chính xác N phần trăm?
13. Với JDK mới hơn, AOT cache khác AppCDS truyền thống ở điểm nào?
14. `-Xshare:on` có nên là điều kiện mặc định trong production không?
15. Khi nâng JDK hoặc triển khai sang hệ điều hành/kiến trúc khác, điều gì phải được kiểm tra hoặc tạo lại?

**Đáp án:**

1. AppCDS cho phép archive thêm **class ứng dụng/thư viện**, ngoài các class nền tảng JDK.
2. JVM có thể tái sử dụng biểu diễn class đã chuẩn bị trong archive, giảm một phần thao tác load/prepare.
3. Không; heap và trạng thái mutable theo tiến trình không tự trở thành shared cache.
4. `ArchiveClassesAtExit` tạo archive khi JVM kết thúc thích hợp; `SharedArchiveFile` chỉ archive để dùng ở lần khởi động sau.
5. Tệp tồn tại chưa chứng minh class ứng dụng được load từ tệp hoặc archive tương thích.
6. Class ứng dụng đã được nạp từ archive động trong môi trường kiểm thử.
7. Static có bước ghi class list riêng rồi dump; dynamic tạo archive từ lần chạy đã tải class.
8. JDK 19; **không** có ở Java 10.
9. Không; thay đổi JAR là lý do quan trọng để đánh giá/tạo lại archive.
10. Workflow AppCDS hiện hành có các ràng buộc về nguồn JAR và non-empty directories.
11. Các phần metadata/trang archive chỉ đọc thích hợp có thể được memory-map dùng chung; heap/runtime state vẫn riêng.
12. Nhiều biến như disk cache, JIT, GC, CPU, workload và default CDS gây nhiễu; cần benchmark có đối chứng.
13. AOT cache có thể chứa nhiều loại artifact tối ưu hơn, không chỉ dữ liệu lớp theo mô hình AppCDS.
14. Không; đây là chế độ fail-fast phục vụ kiểm thử, không được khuyến nghị production.
15. Tính tương thích về JDK build, artifact, classpath, OS/CPU và cấu hình; tạo lại cache/archive khi cần.

## 18. Tham khảo nguồn hiện hành

- **OpenJDK — JEP 310, Application Class-Data Sharing (mốc Java 10):** https://openjdk.org/jeps/310
- **Oracle — `java` command, Application Class Data Sharing, static/dynamic/auto archives, hạn chế classpath và AOT cache (JDK 25):** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle — Java Virtual Machine Guide, Class Data Sharing và AppCDS (JDK 25):** https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html
- **Oracle — `java` command AppCDS trong JDK 10 (chỉ để hiểu mốc lịch sử, không dùng cờ obsolete):** https://docs.oracle.com/javase/10/tools/java.htm
- **OpenJDK — JEP 350, Dynamic CDS Archives (JDK 13):** https://openjdk.org/jeps/350
- **Oracle — JDK 19 Release Notes, Automatic Generation of the CDS Archive:** https://www.oracle.com/java/technologies/javase/19all-relnotes.html
- **OpenJDK — JEP 483, Ahead-of-Time Class Loading & Linking (JDK 24):** https://openjdk.org/jeps/483
- **OpenJDK — JEP 514, Ahead-of-Time Command-Line Ergonomics (JDK 25):** https://openjdk.org/jeps/514
- **OpenJDK — JEP 515, Ahead-of-Time Method Profiling (JDK 25):** https://openjdk.org/jeps/515
- **Dev.java — CDS và AppCDS trên HotSpot:** https://dev.java/learn/jvm/cps-appcds/

**Kết luận:** AppCDS từ **Java 10** làm cho **lớp ứng dụng** trở thành đối tượng có thể được đưa vào CDS archive, giúp JVM khởi động từ dữ liệu class được chuẩn bị sẵn và có khả năng chia sẻ metadata chỉ đọc giữa các tiến trình. Với JDK hiện đại, có thể tạo archive **static**, **dynamic** hoặc **auto-create**; xác minh phải dựa trên log class load của chính class ứng dụng, không chỉ dựa vào tệp `.jsa`. AppCDS **không chia sẻ object nghiệp vụ, không giữ static state qua lần chạy, không cam kết mọi workload nhanh hơn**, và không thay thế các tối ưu **AOT cache** mới. Hãy chọn cơ chế đúng JDK, giữ artifact/classpath phù hợp, kiểm thử startup thật và **không sử dụng cờ thương mại/AppCDS đã lỗi thời của Java 10**.