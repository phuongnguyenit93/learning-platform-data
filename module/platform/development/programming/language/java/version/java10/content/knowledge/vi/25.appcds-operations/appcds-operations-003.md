# Chỉ định danh sách lớp bằng -XX:SharedClassListFile khi vận hành AppCDS

## 1. Mục tiêu và phạm vi

**Application Class-Data Sharing (AppCDS)** là khả năng của HotSpot JVM cho phép đưa metadata của những lớp được chọn, kể cả lớp ứng dụng và thư viện, vào một **CDS archive** để có thể dùng lại khi JVM khởi động. Nhờ đó, trong những workload phù hợp, chương trình có thể giảm một phần thời gian nạp lớp và chia sẻ các trang bộ nhớ chỉ đọc giữa nhiều tiến trình JVM.

Khi muốn tạo **static CDS/AppCDS archive** bằng quy trình thủ công, có hai thứ hoàn toàn khác nhau:

- **Class list**: tệp văn bản mô tả những lớp mà JVM sẽ cố gắng đưa vào archive khi dump.
- **CDS archive**: tệp nhị phân do JVM tạo, thường có đuôi `.jsa`, được JVM đọc ở những lần chạy sau.

Tùy chọn chính của bài:

~~~text
-XX:SharedClassListFile=<đường-dẫn-tệp-classlist>
~~~

Tùy chọn này **chỉ định tệp danh sách lớp dùng khi tạo static archive** với `-Xshare:dump`. Nó **không phải** đường dẫn chứa archive `.jsa`, cũng **không phải** tùy chọn dùng để chạy chương trình với archive đã tạo.

**Quy trình đầy đủ:**

~~~text
Ứng dụng JAR + workload đại diện
          |
          v
-XX:DumpLoadedClassList=app.classlist
          |
          v
app.classlist (danh sách lớp được quan sát)
          |
          v
-Xshare:dump
-XX:SharedClassListFile=app.classlist
-XX:SharedArchiveFile=app.jsa
          |
          v
app.jsa (archive nhị phân)
          |
          v
java -XX:SharedArchiveFile=app.jsa ... Main
          |
          v
Kiểm bằng -Xlog:class+load hoặc -Xlog:cds
~~~

**Mốc và trạng thái hiện nay:**

- **JDK 10** đưa AppCDS vào OpenJDK với JEP 310. Cách tạo archive tĩnh từ class list là một quy trình quan trọng của giai đoạn này.
- Trên **JDK 17, 25 và 26**, Java launcher vẫn mô tả `-XX:SharedClassListFile` và quy trình `-Xshare:dump`. Đây **không phải tùy chọn đã bị xóa**.
- Các JDK mới còn có **dynamic CDS** và **AOT cache**, giúp đơn giản hóa việc tạo dữ liệu chia sẻ hoặc mở rộng tối ưu hóa. Vì vậy **không nên nói quy trình class list là cách duy nhất hoặc luôn tốt nhất**.
- Bài chỉ sử dụng các API/tùy chọn còn áp dụng; không hướng dẫn dùng lại các cờ AppCDS thương mại hoặc cờ cũ đã bị loại khỏi quy trình hiện đại.

## 2. Hiểu đúng ba tệp: JAR, classlist và JSA

| Thành phần | Ví dụ | Nội dung | Tác dụng |
| --- | --- | --- | --- |
| JAR của ứng dụng | `app.jar` | Bytecode `.class` và tài nguyên ứng dụng | Nguồn lớp khi chạy hoặc khi tạo archive |
| Class list | `app.classlist` | Tệp văn bản do JVM tạo hoặc danh sách lớp phù hợp định dạng | Đầu vào cho `-XX:SharedClassListFile` khi dump |
| Archive | `app.jsa` | Dữ liệu chia sẻ do JVM tạo ở định dạng nhị phân | Đầu vào cho `-XX:SharedArchiveFile` ở lần chạy sau |

### Ba cờ dễ bị nhầm

~~~bash
# 1. Quan sát lớp đã nạp, xuất tệp danh sách:
java -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.AppCdsDemo

# 2. Chỉ định classlist làm đầu vào và tạo một archive:
java -Xshare:dump -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app.jsa -cp app.jar

# 3. Sử dụng archive đã tạo:
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.AppCdsDemo
~~~

Các dấu `\` nối dòng trong khối trên theo cú pháp shell POSIX. Với PowerShell/Windows CMD, nên đặt **mỗi lệnh trên một dòng** như ví dụ runnable ở mục 9, hoặc dùng cú pháp nối dòng riêng của shell. Không gõ dấu `\` cuối dòng một cách máy móc vào PowerShell.

Phân biệt vai trò:

- `-XX:DumpLoadedClassList=...`: **xuất** classlist từ một lần chạy có nạp lớp.
- `-XX:SharedClassListFile=...`: **đọc** classlist để tạo static archive.
- `-XX:SharedArchiveFile=...`: **chỉ định archive** khi tạo hoặc nạp.
- `-Xshare:dump`: bảo JVM **tạo archive**; không phải chạy `main` theo cách thông thường.
- `-Xshare:auto`: sử dụng archive khi khả dụng, phù hợp chế độ fallback trong sản xuất.
- `-Xshare:on`: yêu cầu dùng CDS; nếu không đáp ứng được có thể dừng JVM, chủ yếu phục vụ kiểm thử/chẩn đoán.
- `-Xshare:off`: tắt CDS, đôi khi dùng ở lượt thu classlist hoặc làm baseline đo.

Không có thao tác nào trong ba bước trên **đổi mã nguồn Java thành classlist**. Tệp classlist phải phản ánh **những lớp thực sự đã được tải** trong một lần chạy phù hợp.

## 3. Vai trò chính xác của -XX:SharedClassListFile

Cú pháp:

~~~text
-XX:SharedClassListFile=<file_name>
~~~

JDK tool specification mô tả đây là **tệp văn bản chứa tên các lớp sẽ được đưa vào CDS archive**. Trong dạng tên lớp đơn giản, dùng dấu gạch chéo `/` để phân tách package thay cho dấu chấm `.`.

Ví dụ tối giản:

~~~text
java/lang/Object
java/lang/String
demo/AppCdsDemo
~~~

Đây chỉ là **minh họa định dạng tên lớp đơn giản**. Không nên coi ba dòng đó là classlist hoàn chỉnh và luôn đủ để dump một ứng dụng thực.

Lý do: khi sử dụng `-XX:DumpLoadedClassList`, JVM có thể tạo các bản ghi bổ sung về **nguồn của lớp, ID, loại loader, quan hệ phụ thuộc** hoặc thông tin cần thiết để nhận diện lớp ứng dụng trong các trường hợp phức tạp. Nội dung classlist sinh tự động có thể dài và thay đổi theo JDK/provider class loader.

**Thực hành được khuyến nghị cho quy trình static AppCDS thủ công:** để **chính JVM tạo classlist từ một lượt chạy đại diện**, sau đó cung cấp **nguyên tệp được tạo** cho `-XX:SharedClassListFile`. Không biên tập bằng cách đoán các dòng `id:`/`super:` của file do JVM sinh, và không dùng parser tự viết để xóa những bản ghi lạ.

### Classlist không phải một file .class hoặc file JAR

Sai:

~~~bash
# Sai: classlist không phải chính app.jar.
java -Xshare:dump -XX:SharedClassListFile=app.jar \
  -XX:SharedArchiveFile=app.jsa -cp app.jar
~~~

Tệp đầu vào của `SharedClassListFile` phải ở **định dạng classlist**, không phải byte của JAR. Tương tự, không đưa `app.classlist` vào `-XX:SharedArchiveFile` khi chạy; lựa chọn archive yêu cầu tệp do JVM dump ra.

### Classlist chọn những lớp có khả năng được archive

Danh sách lớp là **đầu vào cho quá trình dump**, không phải cam kết mọi dòng chắc chắn sẽ được sử dụng để load từ archive tại runtime. Các lớp còn phải đáp ứng điều kiện của CDS, môi trường/class path tương thích và những giới hạn của class loader/JVM.

Ứng dụng vẫn cần **JAR và các thư viện** vào classpath ở những lần chạy sau. Archive **không thay thế** toàn bộ JAR hoặc classpath bằng một tệp tự chứa kiểu executable.

### Không dùng classlist như cơ chế bảo mật

Tên lớp có thể tiết lộ cấu trúc package và sự phụ thuộc của ứng dụng. Classlist và archive cần quyền đọc/ghi phù hợp; không coi archive là mã hóa bảo mật. Không để bên không tin cậy thay thế archive mà JVM sẽ nạp. Với tệp quan trọng, cấu hình phân quyền và quy trình build/deploy đáng tin là quan trọng hơn một giả định về định dạng nhị phân.

## 4. Thu classlist: workload đại diện quan trọng hơn danh sách “tất cả”

Để thu classlist từ một ứng dụng đã đóng gói JAR, Oracle Java launcher hiện hành có ví dụ kiểu:

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.AppCdsDemo
~~~

Ý nghĩa:

1. JVM bắt đầu ứng dụng với `app.jar` trong classpath.
2. Ứng dụng thực thi một **workload đại diện** và làm JVM tải các lớp thực sự cần dùng.
3. Khi chương trình kết thúc, VM ghi thông tin lớp đã tải vào `app.classlist`.
4. Tệp classlist có thể dùng ở bước tạo static archive.

`-Xshare:off` trong lượt này làm rõ việc thu lớp không phụ thuộc việc đã có một archive custom; nó cũng phù hợp ví dụ chính thức. Điều này không có nghĩa mọi ứng dụng bắt buộc tắt CDS trong mọi phép đo sau đó.

### Chỉ thu những lớp của lệnh main có đủ không?

Không nhất thiết. Nếu ứng dụng thật dùng:

- Servlet/web framework, dependency injection;
- lazy initialization;
- JDBC và một hoặc nhiều database drivers;
- cơ chế tạo proxy, reflection, ServiceLoader;
- nhiều luồng công việc hoặc request path khác nhau,

thì một lượt chạy chỉ in `"hello"` sẽ không tải các lớp được kích hoạt khi xử lý request thật. Archive tạo ra từ classlist đó vẫn **có thể dùng**, nhưng phạm vi tối ưu hóa có thể nhỏ hơn mong đợi.

Hãy thiết kế lượt thu classlist giống một **warm-up/training workload**: khởi tạo những module thật, chạy những tác vụ phổ biến, chạm vào các mã đường đi đại diện, rồi kết thúc bình thường.

**Không bắt mọi nhánh hiếm cần xuất hiện bằng mọi giá.** CDS archive có chi phí đĩa/bộ nhớ ánh xạ; những lớp rất ít dùng có thể không đáng được archive. Đo hiệu quả bằng dữ liệu thật.

### Kiểm tra tệp được thu

Sau bước thu, xác minh tệp `app.classlist` **thực sự đã được tạo** và không phải file rỗng. Có thể mở để quan sát tên lớp:

~~~text
java/lang/Object
java/lang/String
demo/AppCdsDemo
demo/AppCdsDemo$Message
...
~~~

Khối trên là **mẫu minh họa**, không phải stdout/classlist chính xác của mọi phiên bản JDK. Bản thực có thể có nhiều dòng dữ liệu khác và số lớp thay đổi theo build, module, môi trường và chính workload.

Để kiểm bằng terminal, có thể xem số byte/kích thước file hoặc tìm tên `demo/AppCdsDemo` trong file đã tạo. Không assert “classlist phải đúng 1.314 dòng”; JDK hoặc phụ thuộc khác có thể thay đổi số lớp.

## 5. Tạo static archive: SharedClassListFile + SharedArchiveFile

Khi đã có classlist và JAR:

~~~bash
java -Xshare:dump -XX:SharedClassListFile=app.classlist -XX:SharedArchiveFile=app.jsa -cp app.jar
~~~

Đây là bước **tạo archive**. Không thêm tên main class vào cuối và không nhầm đây là lượt chạy xử lý dữ liệu nghiệp vụ.

Cách đọc lệnh:

| Thành phần | Vai trò |
| --- | --- |
| `java` | Java launcher của đúng JDK |
| `-Xshare:dump` | Yêu cầu VM tạo static CDS archive |
| `-XX:SharedClassListFile=app.classlist` | Nguồn danh sách lớp |
| `-XX:SharedArchiveFile=app.jsa` | Đích archive nhị phân |
| `-cp app.jar` | Class path để tìm/kiểm lớp ứng dụng khi dump |

Theo Java launcher của JDK 17/25/26, với quy trình **static AppCDS dump**, classpath được chỉ định bằng `-cp` nên bao gồm **JAR**; không dùng thư mục lớp biên dịch `out` hoặc `target/classes` làm classpath cho lệnh dump classlist-based.

### Tại sao cần classpath ở bước dump?

`app.classlist` chứa **tên và thông tin liên quan** đến lớp được quan sát, nhưng VM vẫn cần tìm bytecode trong runtime image hoặc JAR tương ứng để phân tích/tạo archive. Nếu classpath khác so với khi thu lớp, VM có thể không tìm được một số lớp, hoặc archive có cấu hình không phù hợp cho lần chạy sau.

**Mẫu nhất quán:**

~~~text
Thu:  -cp app.jar  -> app.classlist
Dump: -cp app.jar  -> app.jsa
Chạy: -cp app.jar  -> dùng app.jsa
~~~

Nếu có nhiều JAR, hãy giữ thứ tự/cấu hình classpath phù hợp giữa các bước. Trong môi trường thực, dependency JAR có thể cần được liệt kê theo cùng thứ tự hoặc được quản lý bằng launcher script ổn định.

### Không dùng thư mục biên dịch làm classpath cho static AppCDS

Ví dụ dễ mắc:

~~~bash
# Chạy mã bytecode từ thư mục có thể hợp lệ cho Java thường,
# nhưng không phải mô hình classpath JAR của bước static dump.
java -cp out demo.AppCdsDemo

# Tránh ghép cách này cho quy trình static AppCDS.
java -Xshare:dump -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app.jsa -cp out
~~~

Cách sửa: **đóng gói JAR trước**, rồi dùng chính JAR ấy ở tất cả những bước thu/dump/run. Nếu dùng module path, JDK cũng có quy định riêng đối với modular JAR và exploded module; hãy tham khảo mục `Restrictions on Class Path and Module Path` của Java launcher.

### Một file classlist có tái dùng cho tất cả build không?

Không nên giả định. Khi mã nguồn/bytecode, thư viện, tập JAR, module graph hoặc phiên bản JDK thay đổi, nên **thu lại classlist và tạo lại archive**, hoặc ít nhất kiểm tra nghiêm túc tính tương thích theo tool specification.

Tệp `.jsa` thường ràng buộc với **JDK build, OS/kiến trúc, cấu hình VM và classpath**. Không lấy `app.jsa` từ môi trường khác rồi khẳng định có thể dùng an toàn ở mọi nơi.

## 6. Dùng archive ở runtime: KHÔNG cần truyền SharedClassListFile

Sau khi dump thành công:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar demo.AppCdsDemo
~~~

Điều khác với bước dump:

- Có **tên main class** vì đây là lượt chạy ứng dụng.
- Dùng `-XX:SharedArchiveFile=app.jsa` để chọn archive đã tạo.
- **Không cần `-XX:SharedClassListFile`** ở runtime: JVM sử dụng file `.jsa`, không đọc lại classlist để quyết định mỗi lần load lớp.
- `-Xshare:auto` để JVM cố gắng dùng archive và fallback khi không dùng được trong tình huống được hỗ trợ.

**Đừng viết:**

~~~bash
# Sai vai trò: lấy classlist làm archive runtime.
java -XX:SharedArchiveFile=app.classlist -cp app.jar demo.AppCdsDemo
~~~

Ngay cả khi file có cùng tên, `SharedArchiveFile` vẫn yêu cầu **CDS archive**, không phải tệp tên lớp.

### -Xshare:auto và -Xshare:on khác nhau

| Tùy chọn | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| `-Xshare:auto` | Dùng archive khi thích hợp; có thể fallback | Thường phù hợp production |
| `-Xshare:on` | Buộc CDS hoạt động; nếu không hoạt động được có thể kết thúc JVM | Chẩn đoán, kiểm thử fail-fast |
| `-Xshare:off` | Không dùng CDS | Tạo baseline, cô lập nguyên nhân |
| `-Xshare:dump` | Tạo static archive | Chỉ trong quy trình dump |

Tài liệu Oracle hiện hành lưu ý `-Xshare:on` **chỉ phục vụ thử nghiệm** vì một archive có thể không dùng được khi cấu hình JVM/JDK thay đổi. Dùng `-Xshare:on` cho hệ production mà không kiểm soát compatibility có nguy cơ làm ứng dụng không khởi động được.

### Archive được nạp không có nghĩa mọi lớp đều từ archive

Có thể một archive phù hợp và được VM dùng, nhưng một số lớp của ứng dụng vẫn được nạp bình thường từ JAR do không được archive, classloader khác, thay đổi classpath hoặc giới hạn nội bộ của VM.

Vì vậy, đừng kiểm mỗi trạng thái “ứng dụng chạy bình thường” rồi kết luận **tất cả lớp** được chia sẻ. Cần quan sát log tải lớp cụ thể.

## 7. Xác minh AppCDS thực sự sử dụng archive

Java HotSpot hỗ trợ unified logging. Lệnh phù hợp:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar demo.AppCdsDemo
~~~

Trong output log, nếu lớp được nạp từ archive, JDK có thể hiển thị nguồn đại loại:

~~~text
[info][class,load] demo.AppCdsDemo source: shared objects file
~~~

Dòng này là **mẫu rút gọn minh họa**. Log thật thường chứa timestamp, uptime, decorations và nhiều lớp khác. Không lấy nguyên chuỗi trên làm stdout chính xác không đổi giữa các JDK.

**Cách kiểm có giá trị:**

1. Chạy lệnh bật `-Xlog:class+load=info`.
2. Tìm `demo.AppCdsDemo` hoặc lớp `demo.AppCdsDemo$Message`.
3. Quan sát `source: shared objects file` đối với lớp bạn quan tâm.
4. Nếu thay vào đó thấy JAR, cần xem archive có chứa lớp đó và cấu hình tạo/nạp có khớp không.
5. Kiểm tra thông báo CDS bằng `-Xlog:cds=info` khi cần biết archive có được map thành công và vì sao bị từ chối.

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:cds=info -cp app.jar demo.AppCdsDemo
~~~

Không dựa vào một dòng `Hello, AppCDS` của ứng dụng để kết luận archive được sử dụng. Kết quả nghiệp vụ **phải giống** giữa chạy có và không có CDS; khác biệt chủ yếu là cách nạp dữ liệu lớp và đặc điểm hiệu năng.

### Nếu cần so sánh hiệu năng

Đo nhiều lần khởi động trong điều kiện gần giống nhau:

- Cùng JDK vendor/build, cùng jar và dependency.
- Cùng thông số JVM, máy, tài nguyên CPU/bộ nhớ và workload.
- Tách lượt warm-up của OS file cache khỏi kết quả đo.
- Đo cả startup latency và RSS/footprint theo quy trình đo thống nhất.
- Có baseline `-Xshare:off` và nhánh dùng archive.
- Không hứa trước tỉ lệ tăng tốc chung cho mọi ứng dụng.

`AppCDS` là một **tối ưu hóa**; hiệu quả thực phụ thuộc số lớp được archive, I/O, kích thước ứng dụng, tải hệ thống và JVM.

## 8. Chương trình Java 17+ đầy đủ: tạo JAR rồi dùng classlist

Chương trình dưới đây cố ý nhỏ và không phụ thuộc framework. Mục tiêu chính là kiểm chứng **vai trò và thứ tự các tùy chọn JVM**, không cố tạo nhiều lớp chỉ để khoe số lượng. Đường dẫn ví dụ chỉ sử dụng file trong một **thư mục thử nghiệm mới**, không trỏ tới tệp quan trọng.

### 8.1. Mã nguồn Java

Lưu file đúng tên **`AppCdsDemo.java`**, với nội dung:

~~~java
package demo;

public final class AppCdsDemo {

    private AppCdsDemo() {
    }

    private static final class Message {
        private Message() {
        }

        static String build(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        String greeting = Message.build("AppCDS");
        int result = Integer.sum(2, 3);

        System.out.println(greeting);
        System.out.println("Sum=" + result);
    }
}
~~~

Mã chạy được trên Java 17 trở lên. `Message` là lớp lồng nhau, có file class riêng `demo/AppCdsDemo$Message.class` khi biên dịch. Lệnh gọi `Message.build(...)` giúp lớp ấy được thực thi/nạp trong lượt thu classlist.

### 8.2. Biên dịch và đóng gói JAR

Trong **thư mục mới** chỉ chứa `AppCdsDemo.java`:

~~~bash
javac --release 17 -encoding UTF-8 -d . AppCdsDemo.java
jar --create --file app.jar -C . demo
~~~

Giải thích:

- `javac --release 17` tạo class file tương thích mức Java 17 với API Java 17.
- `-d .` ghi output vào cấu trúc package dưới thư mục hiện tại, ví dụ `demo/AppCdsDemo.class`.
- `jar --create --file app.jar -C . demo` đóng gói thư mục `demo` vào JAR. Không đóng gói file source hoặc classlist vào JAR.
- Các lệnh sử dụng JDK tools `javac` và `jar` của cùng bộ công cụ được cài.

**Thử chạy Java bình thường:**

~~~bash
java -cp app.jar demo.AppCdsDemo
~~~

**Stdout chính xác của chương trình ứng dụng:**

~~~text
Hello, AppCDS
Sum=5
~~~

Đoạn output trên chỉ là output của **chương trình Java**, không phải những thông báo HotSpot trong quá trình dump hoặc logging.

### 8.3. Thu danh sách lớp

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.AppCdsDemo
~~~

Kết quả dự kiến:

- Ứng dụng vẫn in hai dòng `Hello, AppCDS` / `Sum=5`.
- JVM tạo tệp `app.classlist` chứa danh sách lớp được nạp trong lượt chạy.
- Số dòng/tên lớp cụ thể phụ thuộc JVM và môi trường; **không có “stdout classlist chính xác” chung**.
- Classlist chứa cả lớp nền tảng và lớp ứng dụng được quan sát, nên không chỉ có `demo/AppCdsDemo`.

### 8.4. Tạo archive từ classlist — bước trọng tâm

~~~bash
java -Xshare:dump -XX:SharedClassListFile=app.classlist -XX:SharedArchiveFile=app.jsa -cp app.jar
~~~

Lệnh trên đọc `app.classlist` do bước trước tạo; JVM tạo `app.jsa` nếu môi trường và cấu hình tương thích. Bước này **không gọi main()** như khi ứng dụng chạy bình thường.

Nếu dump thất bại, đừng chuyển sang lệnh run rồi giả định file `app.jsa` mới đã được tạo. Hãy kiểm exit code và thông báo thực tế, cùng quyền ghi và classpath.

### 8.5. Chạy với archive

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar demo.AppCdsDemo
~~~

Nếu chương trình chạy thành công, stdout ứng dụng vẫn là:

~~~text
Hello, AppCDS
Sum=5
~~~

Chạy có archive **không được làm đổi dữ liệu đầu ra**. Tuy nhiên riêng hai dòng trên **không chứng minh** class từ archive đã được dùng; cần xem logging.

### 8.6. Bật log để kiểm từng lớp

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar demo.AppCdsDemo
~~~

Log có thể chứa hàng trăm dòng nên hãy tìm lớp `demo.AppCdsDemo` và trường `source`. Nếu lớp đã được chia sẻ, nguồn của nó sẽ được trình bày là từ shared objects file. Dữ liệu còn phụ thuộc runtime, vì vậy **không ghi một log dump/loader giả làm stdout cố định**.

### 8.7. Chạy đối chứng khi tắt CDS

~~~bash
java -Xshare:off -cp app.jar demo.AppCdsDemo
~~~

Kết quả nghiệp vụ vẫn giống nhau. Dùng cách này để đo baseline hoặc cô lập lỗi khi so với lần nạp archive.

### Tóm tắt năm lệnh

| Bước | Lệnh chính | File tạo/đọc |
| --- | --- | --- |
| 1. Compile/JAR | `javac`, `jar` | `app.jar` |
| 2. Trial run | `-XX:DumpLoadedClassList=app.classlist` | **Tạo** classlist |
| 3. Static dump | `-XX:SharedClassListFile=app.classlist` + `-Xshare:dump` | **Đọc** classlist, **tạo** JSA |
| 4. Runtime | `-XX:SharedArchiveFile=app.jsa` | **Đọc** JSA |
| 5. Verify | `-Xlog:class+load=info` | In log nguồn lớp |

Không bỏ qua bước tạo JAR và không dùng `java -cp .` ở thời điểm dump. Mẫu trên được thiết kế để các lệnh có thể chạy liên tục trong cùng một thư mục sạch trên JDK 17+ sử dụng HotSpot với CDS.

## 9. Những điều kiện tương thích khi dump và chạy

### 9.1. Phiên bản JDK và kiến trúc

CDS archive là tệp nhị phân chứa biểu diễn nội bộ của class metadata. Nó **không** là một artifact portable như JAR bytecode. Khi thay:

- Phiên bản/build JDK;
- Vendor hoặc cấu trúc runtime image;
- OS/CPU architecture;
- Những tùy chọn VM làm thay đổi biểu diễn class metadata;
- Bộ JAR, module hoặc cách ứng dụng nạp lớp,

archive có thể không còn hợp lệ hoặc một số lớp không được dùng từ archive.

Khi triển khai, cách vững chắc là **tạo archive bằng JDK và cấu hình sát với môi trường chạy**. Trong container, nên gắn archive với đúng image/tag/digest và được tạo trong quy trình build/release phù hợp; không copy `.jsa` giữa những image JDK khác mà chưa kiểm tra.

### 9.2. Classpath, JAR và module path

Tài liệu JDK 17/26 lưu ý static AppCDS archive được tạo từ classpath JAR; **non-empty directories** trong classpath/module path có các hạn chế. Không giả định mọi dạng exploded classes/module đều được archive giống JAR.

Nếu có nhiều JAR:

~~~text
app.jar
lib/dependency-a.jar
lib/dependency-b.jar
~~~

cần classpath phù hợp cho cả ba giai đoạn. Ở Linux/macOS thường dùng dấu hai chấm `:` phân cách danh sách classpath; Windows thường dùng dấu chấm phẩy `;`. Đừng viết một lệnh classpath nhiều JAR với dấu phân cách của Unix rồi yêu cầu chạy nguyên trên Windows.

Sử dụng một build tool/launcher có thể giúp đóng gói classpath nhất quán. Tuy nhiên nếu build tool chạy từ thư mục class (`target/classes`) thay vì JAR, hãy bảo đảm **trường hợp static dump** tuân thủ yêu cầu đường dẫn classpath của HotSpot.

### 9.3. Khác class loader

AppCDS hỗ trợ nhiều loại class loader theo các điều kiện HotSpot quy định, nhưng những lớp nạp động/proxy/tái định nghĩa qua agent, loader tự tạo hoặc instrument bytecode có thể không đáp ứng tất cả điều kiện archive/khả năng tái sử dụng.

Đừng tự giả định một lớp đã có trong classlist chắc chắn được archive và được JVM load từ archive. Đọc thông báo dump và `-Xlog:class+load` để phân biệt:

- Lớp có tên trong classlist.
- Lớp đủ điều kiện để được ghi vào archive.
- Lớp thực sự được load từ archive ở runtime.

Đây là **ba sự kiện khác nhau**.

### 9.4. Các tùy chọn làm CDS không khả dụng

Một số tùy chọn, chẳng hạn `--upgrade-module-path`, `--patch-module` và `--limit-modules`, có thể khiến CDS bị tắt hoặc gây lỗi khi tạo archive theo Java launcher specification. Khi gặp lỗi, hãy kiểm cấu hình JVM thực thay vì chỉ kiểm tệp `.jsa` có tồn tại.

Nếu `-Xshare:auto` cho phép fallback, ứng dụng có thể vẫn chạy nên việc **chạy thành công không tương đương tối ưu hóa đã kích hoạt**. Muốn bắt lỗi tương thích trong môi trường kiểm thử, có thể dùng `-Xshare:on` để xem thông báo fail-fast, nhưng không mặc định dùng trong production.

### 9.5. Quyền và tính toàn vẹn file

Quy trình cần quyền:

- Đọc `app.jar` và thư viện phụ thuộc.
- Ghi `app.classlist` trong lượt thu.
- Đọc classlist và ghi `app.jsa` khi dump.
- Đọc archive khi chạy.

Không dùng quyền admin/superuser như điều kiện chung; chỉ cần quyền file hợp lệ. Archive chia sẻ giữa các JVM phải được bảo vệ khỏi thay đổi trái phép. HotSpot cung cấp một số cơ chế kiểm tra integrity, nhưng không thay thế policy quyền file và chuỗi cung ứng phần mềm tin cậy.

## 10. Các phương pháp hiện đại khác — biết để chọn đúng

`-XX:SharedClassListFile` vẫn được hỗ trợ, nhưng không phải mọi dự án Java hiện nay phải trải qua quy trình classlist thủ công.

### 10.1. Dynamic CDS bằng ArchiveClassesAtExit

Java launcher hỗ trợ một cách tạo archive động qua một lượt chạy ứng dụng:

~~~bash
java -XX:ArchiveClassesAtExit=dynamic.jsa -cp app.jar demo.AppCdsDemo
~~~

Khi ứng dụng kết thúc bình thường, JVM có thể tạo **dynamic archive** chứa lớp được nạp trong quá trình chạy, dựa trên một static archive nền tương thích. Lúc dùng:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=dynamic.jsa -cp app.jar demo.AppCdsDemo
~~~

Trong luồng này, **không cần chủ động tạo và truyền `app.classlist`**. Đây là lựa chọn giảm một bước cho nhiều trường hợp. Tuy nhiên, dynamic archive có giới hạn/tối ưu hóa khác static archive; hãy đo hiệu quả và xem cấu hình JVM.

Đừng dùng cùng lúc mọi cờ dump/ArchiveClassesAtExit rồi giả định chúng tạo cùng một loại artifact. Mỗi chế độ có mục tiêu riêng, cách truyền option riêng và những ràng buộc khác nhau.

### 10.2. Tạo CDS bằng jcmd

JDK hiện đại có thể dùng diagnostic command `jcmd ... VM.cds` để tạo archive từ một JVM đang chạy, giúp không phải sửa launcher cho từng lượt thu dữ liệu. Cú pháp cụ thể phụ thuộc lệnh `VM.cds` của JDK đang cài; xem hướng dẫn Java launcher chính thức.

Ví dụ minh họa:

~~~bash
jcmd <pid> VM.cds static_dump app.jsa
~~~

Đây là lệnh **thao tác với process đã chạy**; `<pid>` phải được thay bằng PID thực. Nó không làm `SharedClassListFile` trở nên sai, chỉ cung cấp một đường đi khác cho tác vụ tạo archive.

### 10.3. Ahead-of-Time (AOT) cache trong JDK mới

JDK 24 giới thiệu **AOT cache** để tập hợp các artifact tối ưu hóa Ahead-of-Time. Tài liệu Java launcher JDK 25/26 mô tả các cờ `-XX:AOTMode`, `-XX:AOTCache`, `-XX:AOTCacheOutput` và `-XX:AOTConfiguration` cho các pha training/assembly/production.

AOT cache có thể chứa nhiều artifact hơn một CDS archive cổ điển, và có những điều kiện tương thích riêng về JDK, OS/CPU, ứng dụng, classpath/module path và VM options.

**Điểm cần hiểu trong chủ đề này:**

- Static CDS thủ công dùng `SharedClassListFile` vẫn có giá trị khi cần kiểm soát danh sách lớp.
- Dynamic CDS và AOT cache có thể giảm nhu cầu tạo classlist bằng tay hoặc mở rộng tối ưu hóa.
- Không dùng các cờ AOT mới trên Java 17, vì chúng chưa tồn tại ở target đó.
- Không mô tả `SharedClassListFile` là flag đã deprecated hoặc bị xóa chỉ vì JDK mới có AOT cache.
- Khi triển khai trên JDK 24+, có thể đánh giá cả phương án AOT theo tài liệu **đúng phiên bản JDK** và workload.

### 10.4. Các cờ cũ không còn là hướng dẫn hiện đại

Từ JDK 11, `-XX:+UseAppCDS` đã **obsolete**: AppCDS không còn yêu cầu bật riêng bằng cờ đó. Không copy những hướng dẫn Java 10 cũ yêu cầu `-XX:+UnlockCommercialFeatures` hoặc `-XX:+UseAppCDS` và áp dụng nguyên xi vào JDK 17/25/26.

Thay vào đó, dùng các option **vẫn hiện diện** trong Java launcher specification, gồm `-XX:DumpLoadedClassList`, `-XX:SharedClassListFile`, `-XX:SharedArchiveFile`, `-Xshare:dump` theo quy trình static thủ công.

## 11. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| Dùng `-XX:SharedClassListFile=app.jar` | Nhầm JAR với danh sách lớp | Dùng classlist được JVM tạo từ `DumpLoadedClassList` |
| Dùng `-XX:SharedArchiveFile=app.classlist` | Nhầm tệp văn bản với archive nhị phân | Dùng `app.jsa` đã dump thành công |
| Không có `app.classlist` | Chưa chạy trial run, thiếu quyền ghi, đường dẫn sai | Chạy bước thu trước, kiểm sự tồn tại/quyền của tệp |
| Classlist chứa ít lớp ứng dụng | Workload thử không nạp đủ lớp quan trọng | Thu với luồng khởi động và tác vụ đại diện |
| Lệnh dump dùng `-cp out` | Classpath là thư mục biên dịch, vi phạm ràng buộc static AppCDS | Đóng gói và dùng JAR |
| Classpath thu/dump/run không khớp | JAR/library thứ tự/đường dẫn thay đổi | Giữ cấu hình nhất quán, tạo archive lại |
| Chỉ định classlist ở runtime rồi mong JVM dùng archive | `SharedClassListFile` không chọn archive lúc chạy | Dùng `SharedArchiveFile` |
| Mở file JSA từ JDK khác mà vẫn chạy | Archive không portable giữa nhiều môi trường | Tạo lại bằng JDK/config phù hợp |
| Dùng `-Xshare:on` trong production | Chế độ này có thể dừng JVM nếu archive không dùng được | Ưu tiên `-Xshare:auto`; dùng on để test |
| Chương trình vẫn chạy dù CDS không dùng | `auto` có thể fallback | Xem `-Xlog:cds` và `-Xlog:class+load` |
| Thấy tệp archive tồn tại rồi kết luận mọi lớp đều được dùng | Classlist/archived/loaded là ba trạng thái khác | Kiểm log các lớp cần quan tâm |
| Tái dùng classlist cũ sau khi đổi dependency | Danh sách có thể lỗi thời hoặc không còn tương thích | Thu/dump lại, đo lại |
| Sửa tay dòng `id:` trong classlist do JVM sinh | Có thể phá thông tin loader/dependency | Dùng file nguyên bản do JVM tạo |
| Dùng `UseAppCDS`/`UnlockCommercialFeatures` từ tài liệu cũ | Không phải quy trình hiện đại còn cần thiết | Theo hướng dẫn Java launcher JDK đang chạy |
| Cho rằng dynamic archive và static archive là cùng một thứ | Cách tạo, base archive và mức tối ưu hóa khác nhau | Chọn đúng cơ chế và test riêng |
| Dùng JAR ứng dụng nhưng thiếu dependency ở runtime | Archive không thể thay thư viện bị thiếu | Phải cung cấp đầy đủ classpath |
| So benchmark khi bật log class loading rất nhiều | Unified logging gây I/O, sai độ trễ thực | Tắt log benchmark; chỉ bật khi chẩn đoán |
| Lưu archive vào thư mục công khai cho sửa | Nguy cơ bị sửa/thay thế artifact | Bảo vệ quyền ghi, kiểm build/deployment |
| Lấy một mức tăng tốc ví dụ làm SLA | Kết quả tùy workload và JDK | Đo bằng số liệu trong môi trường mục tiêu |

## 12. Checklist thực hành khi đưa AppCDS vào hệ thống

### Checklist build/training

1. Xác định ứng dụng thực sự chạy trên **HotSpot JDK có CDS/AppCDS** và phiên bản JDK cụ thể.
2. Đóng gói ứng dụng và các dependency cần thiết thành **JAR**, không dùng exploded class directory ở bước static dump.
3. Chạy workload đại diện với `-XX:DumpLoadedClassList=...`.
4. Kiểm classlist tồn tại, có lớp ứng dụng cần quan tâm và không lỗi/thiếu thông tin.
5. Tạo archive bằng `-Xshare:dump` + `-XX:SharedClassListFile=...` + `-XX:SharedArchiveFile=...`.
6. Đảm bảo classpath ở ba giai đoạn tương thích, đúng đường dẫn và thứ tự JAR.
7. Kiểm exit code và file archive được tạo thành công; không dùng file cũ nếu dump thất bại.
8. Gắn archive với đúng JDK/runtime image/container và cấu hình triển khai.
9. Giữ quyền đọc/ghi an toàn, quản lý artifact qua quy trình build/release.
10. Khi thay JDK hoặc JAR, có chiến lược tạo lại archive thay vì mù quáng dùng lại.

### Checklist runtime/QA

1. Chạy ứng dụng với `-XX:SharedArchiveFile=app.jsa`, **không cần** truyền classlist ở runtime.
2. Ưu tiên `-Xshare:auto` để không gây dừng startup ngoài ý muốn vì incompatibility.
3. Dùng `-Xlog:class+load=info` để xác minh một số lớp được load từ shared archive.
4. Dùng `-Xlog:cds=info` để chẩn đoán việc map archive và những lý do bị từ chối.
5. So kết quả nghiệp vụ của ứng dụng trước/sau khi có archive; kết quả phải tương đương.
6. Benchmark không bật class-load logging; đo startup time và memory footprint nhiều lượt.
7. Kiểm các luồng tác vụ/khởi động đại diện, không chỉ ứng dụng Hello World.
8. Khi nâng version JDK hoặc dependency, kiểm compatibility và thu/dump lại.
9. Nếu dùng custom loader, bytecode instrumentation hoặc module options đặc thù, theo dõi các giới hạn CDS.
10. Trên JDK hiện đại hơn, cân nhắc dynamic CDS/AOT cache, nhưng không nhầm chúng với static dump.

### Tự kiểm tra kiến thức

**Câu 1.** Tệp `app.classlist` và `app.jsa` có cùng mục đích không?

**Đáp án:** Không. Classlist là dữ liệu text mô tả các lớp cần archive; JSA là archive nhị phân do JVM tạo và nạp ở runtime.

**Câu 2.** Tùy chọn nào dùng để tạo classlist từ một lượt chạy ứng dụng?

**Đáp án:** `-XX:DumpLoadedClassList=app.classlist`.

**Câu 3.** Tùy chọn nào chỉ định classlist đầu vào cho một lần `-Xshare:dump`?

**Đáp án:** `-XX:SharedClassListFile=app.classlist`.

**Câu 4.** Có cần chỉ định `SharedClassListFile` khi chạy ứng dụng đã có `app.jsa` không?

**Đáp án:** Không. Để nạp archive sử dụng `-XX:SharedArchiveFile=app.jsa`.

**Câu 5.** Có thể dùng `-cp target/classes` khi tạo static archive theo ví dụ classlist-based không?

**Đáp án:** Không nên. Tài liệu JDK yêu cầu classpath phục vụ static dump chỉ chứa JAR tương ứng; hãy đóng gói và giữ classpath đồng nhất.

**Câu 6.** `-Xshare:on` và `-Xshare:auto` khác nhau như thế nào?

**Đáp án:** `on` yêu cầu CDS hoạt động, có thể khiến JVM thoát khi archive không dùng được; `auto` cho phép JVM dùng archive khi có thể và fallback thích hợp.

**Câu 7.** Nếu chương trình in đúng `Hello, AppCDS` thì có chứng minh lớp ứng dụng được tải từ shared archive không?

**Đáp án:** Không. Muốn biết lớp nào đến từ archive cần dùng logging như `-Xlog:class+load=info`.

**Câu 8.** Classlist do JVM tạo chứa dòng `id:` lạ, có nên xóa để cho đẹp không?

**Đáp án:** Không. Tệp có thể chứa dữ liệu cần thiết cho loader/dependency; giữ nguyên trừ khi có tài liệu format và lý do chỉnh sửa rõ ràng.

**Câu 9.** Đổi JDK build hoặc bộ JAR sau khi tạo archive có sao không?

**Đáp án:** Có thể làm archive không còn phù hợp. Cần kiểm lại và thường tạo lại archive trong pipeline phù hợp.

**Câu 10.** Nếu JDK mới có AOT cache thì `-XX:SharedClassListFile` đã bị xóa chưa?

**Đáp án:** Chưa. Java launcher JDK 25/26 vẫn mô tả static CDS dump từ classlist; AOT cache là một lựa chọn khác với tập tối ưu hóa rộng hơn.

**Câu 11.** Chương trình có bắt buộc mang theo JAR khi sử dụng archive JSA không?

**Đáp án:** Có, phải cung cấp bytecode/phụ thuộc theo classpath/module path mà cấu hình runtime yêu cầu. Archive không tự thay thế toàn bộ JAR.

**Câu 12.** Muốn giảm số bước tạo archive, có thể chọn phương án nào vẫn được hỗ trợ?

**Đáp án:** `-XX:ArchiveClassesAtExit=...` để tạo dynamic CDS archive từ một lần chạy hoặc các cách mới hơn như `jcmd VM.cds`/AOT cache phù hợp với JDK và ứng dụng.

## 13. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — The java Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#application-class-data-sharing): đặc tả `-XX:SharedClassListFile`, `-XX:DumpLoadedClassList`, `-Xshare:dump`, `-XX:SharedArchiveFile`, runtime/logging và các cách tạo archive hiện đại.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): ví dụ ba bước static AppCDS còn được hỗ trợ cùng danh sách hạn chế classpath/module path.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): xác nhận các cú pháp dùng trong demo tương thích với Java 17.
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): vì sao CDS giảm chi phí tải lớp và chia sẻ metadata; cảnh báo `-Xshare:on` dành cho test.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): bối cảnh AppCDS được đưa vào OpenJDK từ JDK 10.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): cách tạo archive động được đưa vào sau quy trình static cổ điển.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): phương pháp AOT cache của JDK mới, không đồng nhất với thao tác `SharedClassListFile`.
- [Oracle Java SE 17 — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): đóng gói các file `.class` thành JAR.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): biên dịch nguồn Java 17 và thiết lập `--release`.

**Kết luận:** `-XX:SharedClassListFile=app.classlist` chỉ định **danh sách lớp đầu vào khi tạo static AppCDS archive**. Luồng đúng là **chạy thử → DumpLoadedClassList → SharedClassListFile + Xshare:dump → SharedArchiveFile để chạy → kiểm bằng unified logging**. Cờ này vẫn được hỗ trợ trong JDK hiện đại, nhưng không nhất thiết là phương án thuận tiện nhất khi dynamic CDS hoặc AOT cache đáp ứng được mục tiêu.