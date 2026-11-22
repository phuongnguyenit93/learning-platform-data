# Chỉ định kho chia sẻ AppCDS bằng `-XX:SharedArchiveFile` trong Java

## Mục tiêu bài học

**Class Data Sharing (CDS)** là khả năng của HotSpot JVM lưu metadata và dạng biểu diễn tối ưu của các class vào một **shared archive**; những JVM tương thích có thể ánh xạ (memory-map) dữ liệu này thay vì phải tải/biến đổi lại toàn bộ class như lần đầu. **Application Class Data Sharing (AppCDS)** mở rộng cơ chế tới các class của ứng dụng và thư viện, bên cạnh các class nền tảng.

Khi cần chỉ rõ **archive nào sẽ được JVM sử dụng**, tùy chọn trọng tâm là:

~~~text
-XX:SharedArchiveFile=<duong-dan-archive.jsa>
~~~

Trong các JDK hiện hành, tùy chọn này vẫn được hỗ trợ. Nó không phải lệnh “bật/tạo tự động mọi kho”, mà là **chỉ định đường dẫn archive CDS để JVM nạp hoặc, trong chế độ dump phù hợp, đường dẫn archive cần tạo**. Cách diễn giải phụ thuộc vào chế độ JVM và loại archive.

Bài học tập trung vào vận hành AppCDS bằng `-XX:SharedArchiveFile` và chỉ dùng kiến thức còn áp dụng trong Java hiện đại. Các ví dụ chính theo **JDK 17+**; một số cải tiến ở JDK mới hơn được phân biệt rõ để tránh dùng sai option trên bản JDK cũ.

Sau bài này, bạn sẽ:

- Phân biệt **default archive**, **static archive** và **dynamic archive**.
- Biết vị trí phải đặt `-XX:SharedArchiveFile` trong lệnh `java`.
- Tạo một dynamic archive qua `-XX:ArchiveClassesAtExit` và **nạp lại nó** ở lần chạy sau.
- Tạo một static archive khi có class list và classpath phù hợp.
- Chỉ định **hai tầng archive** và phân biệt dấu `:` trên Linux/macOS với `;` trên Windows.
- Hiểu `-Xshare:auto`, `-Xshare:on`, `-Xshare:off`, và cách xác minh archive thực sự được dùng.
- Xử lý các lỗi archive không tương thích, JAR/classpath thay đổi, quyền truy cập, nguy cơ bảo mật và đo hiệu năng.

## 1. CDS, AppCDS và archive `.jsa`

**CDS** cho phép một số dữ liệu class được JVM chuẩn bị sẵn, sau đó lưu trong tệp archive. Khi JVM tương thích khởi động, dữ liệu trong archive có thể được ánh xạ vào bộ nhớ, giảm một phần chi phí class loading và cho phép chia sẻ những trang bộ nhớ phù hợp giữa các tiến trình JVM.

**AppCDS** mở rộng phạm vi ngoài các class nền tảng để gồm các class của ứng dụng/thư viện mà JVM có thể lưu vào archive.

Trong nhiều bản phân phối JDK hiện đại, một **default CDS archive** đã được đi kèm và cơ chế CDS hoạt động mặc định khi điều kiện cho phép. Vì vậy không cần tạo archive riêng chỉ để dùng CDS cho các class JDK thông dụng.

Tệp `.jsa` là **quy ước đặt tên thường gặp** cho shared archive, không phải JAR. Nó không thể thay thế `app.jar`, không chứa nguồn Java theo cách một JAR thông thường chứa bytecode, và không thể được chạy bằng `java -jar app.jsa`.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| JAR của ứng dụng | Phân phối class và tài nguyên mà ứng dụng sử dụng | `app.jar` |
| Default CDS archive | Kho chia sẻ chứa các class nền tảng do JDK cung cấp | `classes.jsa` trong bản phân phối JDK |
| Static CDS archive | Kho được tạo trước, thường từ một class list xác định | `app-static.jsa` |
| Dynamic CDS archive | Kho được tạo từ class thực tế được load khi chạy, dùng trên base archive | `app-dynamic.jsa` |
| `-XX:SharedArchiveFile` | Chọn archive khi JVM khởi động hoặc đường dẫn dump ở chế độ tương ứng | `-XX:SharedArchiveFile=app-dynamic.jsa` |
| `-XX:ArchiveClassesAtExit` | Chỉ định đường dẫn **tạo dynamic archive khi ứng dụng thoát** | `-XX:ArchiveClassesAtExit=app-dynamic.jsa` |

Đừng nhầm `SharedArchiveFile` với `ArchiveClassesAtExit`: **tùy chọn thứ nhất chủ yếu chọn kho sử dụng; tùy chọn thứ hai tạo kho động sau một lần chạy**.

Các archive chứa dữ liệu **phụ thuộc JDK build, JVM và môi trường tương thích**, không phải một định dạng lưu trữ Java trung lập có thể dùng cho mọi JDK.

## 2. Cú pháp cốt lõi của `-XX:SharedArchiveFile`

Khi chỉ một archive cần được nạp:

~~~bash
java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Chú ý:

1. `-XX:SharedArchiveFile=...` là **VM option**, đặt **trước tên main class** hoặc trước `-jar`.
2. `app-dynamic.jsa` là đường dẫn archive đã được **tạo hợp lệ** trước đó.
3. `-cp app.jar` là **classpath chứa mã chạy**, không phải đường dẫn archive.
4. `ArchiveDemo` là tên class chứa `main(String[])`.
5. Chỉ ghi `-XX:SharedArchiveFile=...` không tự chứng minh JVM đã dùng archive, không bảo đảm mọi class nằm trong archive, và không tạo class list.

Ví dụ khi chạy JAR có Main-Class trong manifest:

~~~bash
java -XX:SharedArchiveFile=/opt/cds/app.jsa -jar /opt/app/app.jar
~~~

Lệnh trên minh họa cách **nạp** archive tại đường dẫn cố định. Để thành công, archive phải tương thích với JDK, JAR, classpath và các điều kiện có liên quan khi tạo archive.

### 2.1. Dùng đường dẫn tuyệt đối để tránh nhầm working directory

~~~bash
java -XX:SharedArchiveFile=/srv/myapp/cds/app.jsa -cp /srv/myapp/app.jar ArchiveDemo
~~~

Đường dẫn tương đối như `app-dynamic.jsa` được hiểu dựa trên **current working directory của tiến trình Java**. Trong IDE, terminal, service manager và container, thư mục này có thể khác nhau.

Nếu có dấu cách trong đường dẫn, đặt dấu nháy thích hợp cho shell. Với PowerShell:

~~~powershell
java "-XX:SharedArchiveFile=C:\ProgramData\My App\app.jsa" -cp "C:\Apps\My App\app.jar" ArchiveDemo
~~~

Đừng thêm dấu nháy vào **giá trị đường dẫn lưu trong bản thân archive**; shell xử lý việc nhóm một đối số, còn JVM nhận chuỗi option và đường dẫn.

### 2.2. Không đưa option ra sau main class

~~~bash
# ĐÚNG: JVM thấy option
java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo

# SAI VỀ VỊ TRÍ: đối số này đi vào main(String[] args)
java -cp app.jar ArchiveDemo -XX:SharedArchiveFile=app-dynamic.jsa
~~~

Ở lệnh thứ hai, `-XX:SharedArchiveFile` **không được JVM xử lý như một VM option**. Nó chỉ là đối số ứng dụng, nếu `main` không tự xử lý thì có thể bị bỏ qua một cách âm thầm.

## 3. AppCDS hiện đại có hai phương án tạo archive

Trên JDK 17+, hai quy trình phổ biến là:

**A. Dynamic archive — phù hợp khi bắt đầu với ứng dụng cụ thể.**

1. Chạy ứng dụng một lần với `-XX:ArchiveClassesAtExit=...`.
2. JVM ghi dynamic archive khi ứng dụng kết thúc bình thường, nếu điều kiện dump hợp lệ.
3. Ở lần khởi động sau, truyền `-XX:SharedArchiveFile=...` để nạp archive.
4. Kiểm tra log xem archive có được nạp và class nào đến từ vùng chia sẻ.

**B. Static archive — phù hợp khi muốn tạo từ một class list.**

1. Chạy ứng dụng để thu class list bằng `-XX:DumpLoadedClassList=...`.
2. Dùng `-Xshare:dump`, `-XX:SharedClassListFile=...` và `-XX:SharedArchiveFile=...` tạo archive.
3. Nạp archive trong quá trình chạy thật, sử dụng classpath tương thích.
4. Kiểm tra log và đo startup/footprint.

Lựa chọn dynamic thường giúp quy trình đơn giản hơn vì không cần thao tác tạo class list riêng. Static archive hữu ích khi quy trình build/deployment cần kiểm soát class list và việc dump, nhưng phải chú ý những hạn chế cụ thể của JDK.

## 4. Ví dụ ứng dụng Java 17+ dùng trong cả hai quy trình

Lưu chương trình sau thành **ArchiveDemo.java**:

~~~java
import java.util.List;

public class ArchiveDemo {
    public static void main(String[] args) {
        int sum = List.of(1, 2, 3, 4, 5)
                .stream()
                .mapToInt(Integer::intValue)
                .sum();

        System.out.println("AppCDS demo: sum=" + sum);
        System.out.println("Java 17+ supported: "
                + (Runtime.version().feature() >= 17));

        Service service = new Service();
        System.out.println(service.message());
    }

    static final class Service {
        String message() {
            return "Service ready";
        }
    }
}
~~~

Chương trình dùng API chuẩn và không phụ thuộc thời gian hiện tại hay charset mặc định. Biên dịch thành tệp class và đóng gói thành JAR:

~~~bash
mkdir classes
javac -d classes ArchiveDemo.java
jar --create --file app.jar -C classes .
java -cp app.jar ArchiveDemo
~~~

Đầu ra ứng dụng khi dùng Java 17+:

~~~text
AppCDS demo: sum=15
Java 17+ supported: true
Service ready
~~~

Các file `ArchiveDemo.class` và `ArchiveDemo$Service.class` được đưa vào JAR bởi `jar -C classes .`. Việc đóng gói class ứng dụng thành JAR tạo điều kiện dễ kiểm soát **classpath** cho quá trình dump và runtime; với AppCDS trên JDK 17, không nên dùng một thư mục class chưa đóng gói làm mục tiêu chính cho luồng static archive.

Mã này không tự truy vấn trạng thái CDS (Java SE không có một phương thức `System.out.println(isAppCdsEnabled())` phổ thông). Để xác nhận archive đang được dùng, cần **đọc log của JVM** chứ không nhìn riêng ba dòng stdout.

**Phân biệt kiểm thử:** Đây là ví dụ Java chuẩn có đầu ra xác định theo code. Các lệnh tạo/nạp archive là lệnh quản trị JVM; khả năng dùng chúng và nội dung log phụ thuộc JDK/VM và môi trường. Không giả định một terminal bất kỳ có archive đã tạo sẵn.

## 5. Quy trình 1: tạo và nạp dynamic archive bằng `SharedArchiveFile`

### Bước 1 — chạy một lần để tạo archive

~~~bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Trong lần chạy này:

- Ứng dụng vẫn thực thi phương thức `main` như bình thường.
- JVM theo dõi những class phù hợp đã được nạp và khi kết thúc sẽ cố tạo `app-dynamic.jsa`.
- Dynamic archive **dựa trên một base archive**. Nếu không chỉ định base riêng, JDK thường dùng **default CDS archive** đi kèm làm tầng nền.
- Phải có quyền ghi vào vị trí archive và đủ không gian lưu trữ.
- Việc tệp được tạo thành công còn phụ thuộc quá trình kết thúc và các điều kiện hỗ trợ của JDK; không nên chỉ dựa vào exit code của ứng dụng để tuyên bố tệp đã hoàn thành.

Lệnh `ArchiveClassesAtExit` là **lệnh tạo archive động**, không phải lệnh khai báo một đường dẫn sẽ dùng trong mọi lần chạy tiếp theo. Sau khi hoàn thành, cần cấu hình đường dẫn khi start thực tế.

### Bước 2 — chạy tiếp bằng archive đã tạo

~~~bash
java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Đây là trọng tâm bài: `-XX:SharedArchiveFile` yêu cầu JVM dùng **archive được chỉ định**, thay vì chỉ dùng archive mặc định khi có thể.

### Bước 3 — xem log CDS

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Để xem nguồn nạp từng class:

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Log có thể có thông tin liên quan đến các lớp đến từ **shared objects file**. Không đưa một bản log đầy đủ vào tài liệu như thể nó cố định: địa chỉ vùng nhớ, đường dẫn, số lượng class, format dòng và thứ tự nạp có thể đổi theo phiên bản JDK, hệ điều hành và tập class ứng dụng dùng.

**Cách đọc:** chỉ khi log xác nhận archive được mở và các class phù hợp được load từ shared archive, bạn mới có bằng chứng AppCDS đang thực sự được sử dụng. **Một tệp `.jsa` tồn tại** hoặc **chương trình in đúng stdout** chưa đủ.

### Khi dynamic dump tạo một kho nhỏ

Dynamic archive thường chỉ cần chứa các class **không nằm trong base archive**, giúp giảm trùng lặp dữ liệu. Một chương trình rất nhỏ có thể tải nhiều class chuẩn đã có trong base và chỉ tạo ít dữ liệu mới; dung lượng archive hay số class được thêm không nhất thiết tỷ lệ với kích thước mã nguồn.

Nếu ứng dụng dùng reflection, framework hoặc plugin chỉ kích hoạt class ở những nhánh ít gặp, cần **chạy một kịch bản đại diện** trong lần dump. Archive không thể giúp giảm chi phí cho những class chưa từng được phát hiện và lưu đủ điều kiện trong lần tạo đó.

## 6. Quy trình 2: tạo static archive bằng `-Xshare:dump`

Static archive kết hợp với `-XX:SharedArchiveFile` bằng các bước rõ ràng.

### Bước 1 — ghi lại danh sách class đã tải

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar ArchiveDemo
~~~

Trong quy trình này, `app.classlist` là **file văn bản chứa class list** do JVM tạo; nó **không phải** một archive `.jsa`.

Lưu ý khi tạo static archive theo hướng dẫn JDK 17: classpath cung cấp cho quá trình dump nên gồm **JAR**. Không dựa vào một thư mục chứa class đã biên dịch như `classes/` để minh họa workflow này.

### Bước 2 — tạo shared archive tĩnh

~~~bash
java -Xshare:dump -XX:SharedArchiveFile=app-static.jsa -XX:SharedClassListFile=app.classlist -cp app.jar
~~~

Ở đây:

- `-Xshare:dump` chuyển JVM sang **chế độ tạo static archive**, không chạy `ArchiveDemo.main`.
- `-XX:SharedClassListFile` chỉ ra **class list**.
- `-XX:SharedArchiveFile=app-static.jsa` chỉ ra **archive được ghi ra**.
- `-cp app.jar` giúp JVM định vị các class ứng dụng trong quá trình dump.

Đây là lý do câu “`SharedArchiveFile` chỉ dùng để nạp archive” **chưa đầy đủ**: trong chế độ `-Xshare:dump`, chính tùy chọn này xác định **đích ghi archive tĩnh**.

### Bước 3 — nạp static archive ở runtime

~~~bash
java -XX:SharedArchiveFile=app-static.jsa -cp app.jar ArchiveDemo
~~~

Để quan sát class loading:

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app-static.jsa -cp app.jar ArchiveDemo
~~~

Đường dẫn `app.jar` lúc tạo archive và lúc chạy nên tương ứng với nhau về nội dung/classpath theo điều kiện của JDK. Đừng thay JAR rồi giữ lại archive cũ như thể nó tự phản ánh mã mới.

### Vì sao phải tạo class list?

Static dump cần biết tập class muốn lưu. Việc thu thập `DumpLoadedClassList` trong một lần chạy thực tế giúp bao gồm những class ứng dụng và thư viện được tải bởi kịch bản đó; nhưng **không chứng minh** tất cả class của mọi tính năng đã được lưu. Nếu hành vi khởi động của ứng dụng thay đổi, tập class đã tải có thể khác.

Với ứng dụng phức tạp, classpath và cách nạp class (class loaders, modules, agents, instrumentation) có thể ảnh hưởng khả năng chia sẻ; cần kiểm tra hướng dẫn theo đúng JDK và thử với ứng dụng thật.

## 7. Dùng một hoặc hai archive: static base và dynamic top

Trong JDK 17+ có mô hình **tối đa hai tầng archive**: một static archive làm **base**, và một dynamic archive bổ sung bên trên.

Dạng tổng quát trên **Linux/macOS**:

~~~bash
java -XX:SharedArchiveFile=base.jsa:app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Trên **Windows**, dấu phân cách giữa hai archive là **dấu chấm phẩy** `;`, không phải dấu hai chấm:

~~~powershell
java "-XX:SharedArchiveFile=base.jsa;app-dynamic.jsa" -cp app.jar ArchiveDemo
~~~

Đây là sự khác biệt dễ gây nhầm khi chuyển startup command giữa các hệ điều hành. Ví dụ `C:\cds\base.jsa;C:\cds\app-dynamic.jsa` chứa dấu `:` của ổ đĩa Windows nhưng **dấu phân cách giữa hai archive vẫn là `;`**.

### 7.1. Thứ tự các tầng quan trọng

- **Base** thường là static archive, chứa các class nền.
- **Top** là dynamic archive, chứa những class bổ sung.
- Dynamic archive được tạo dựa trên **một base cụ thể**, nên không thể tùy tiện thay base bằng archive khác mà vẫn mong tương thích.

Quy trình ví dụ:

~~~bash
java -XX:SharedArchiveFile=base.jsa -XX:ArchiveClassesAtExit=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Sau đó chạy trên Linux/macOS:

~~~bash
java -XX:SharedArchiveFile=base.jsa:app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Trên Windows:

~~~powershell
java "-XX:SharedArchiveFile=base.jsa;app-dynamic.jsa" -cp app.jar ArchiveDemo
~~~

Giả định `base.jsa` là một **base archive hợp lệ đã được chuẩn bị**, không phải tên tệp có sẵn mặc định. Bài ví dụ ở mục 5 không cần chuẩn bị base riêng, bởi nó dùng **default CDS archive**.

### 7.2. Vì sao có thể nêu chỉ dynamic archive?

Dynamic archive có thể ghi lại thông tin về base archive dùng khi tạo. Do đó, với một dynamic archive hợp lệ đã tạo trên base thích hợp, trong nhiều trường hợp chỉ cần:

~~~bash
java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

JVM đọc metadata của archive để tìm base tương ứng. Nếu dynamic archive đã tạo từ **default CDS archive** của JDK, runtime phù hợp có thể tự dùng default base theo đường dẫn của chính JDK đó.

Không suy ra rằng bạn có thể di chuyển dynamic archive sang bất cứ máy/JDK nào và mọi base tự được tìm thấy. Nếu dùng **custom base**, đường dẫn và tính tương thích của base vẫn là một yêu cầu vận hành.

## 8. `-Xshare:auto`, `-Xshare:on` và `-Xshare:off`

`-XX:SharedArchiveFile` **chọn archive**; `-Xshare` điều khiển **chính sách sử dụng CDS**.

| Tùy chọn | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `-Xshare:auto` | Thử dùng CDS khi môi trường cho phép | Hành vi mặc định/phù hợp với đa số ứng dụng khi không yêu cầu cưỡng chế |
| `-Xshare:on` | Yêu cầu CDS bắt buộc; JVM có thể thoát với lỗi nếu không thể dùng | **Kiểm thử/diagnostics**, không nên ép trong production |
| `-Xshare:off` | Không dùng CDS | Đo baseline, loại trừ vấn đề CDS khi debug |
| Không truyền `-Xshare` | Thường dựa trên hành vi mặc định của JVM hiện hành | Đa số lần chạy production |

Oracle cảnh báo `-Xshare:on` **chỉ dành cho kiểm thử**: archive có thể không nạp được vì thay đổi tham số VM hoặc JDK; với chế độ cưỡng chế, JVM có thể **dừng ngay khi khởi động**. Không dùng `-Xshare:on` như một cách tăng tốc mặc định trong sản xuất.

Ví dụ đo baseline không dùng CDS:

~~~bash
java -Xshare:off -cp app.jar ArchiveDemo
~~~

Ví dụ chế độ dùng CDS khi phù hợp:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Ví dụ **chỉ dùng cho QA** để phát hiện cấu hình không thể chia sẻ:

~~~bash
java -Xshare:on -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Nếu archive không tồn tại/không tương thích, `-Xshare:on` giúp làm rõ lỗi bằng **kết quả khởi chạy thất bại**; không dự đoán chính xác câu chữ thông báo lỗi hoặc exit code trên mọi JDK. Với `-Xshare:auto`, tùy loại lỗi và chính sách runtime JVM có thể chạy mà không dùng archive; **luôn đối chiếu log và trạng thái thật**, đừng mặc định chắc chắn có fallback cho mọi tình huống sai cấu hình.

## 9. Xác minh archive có thực sự được dùng

Đừng xác nhận thành công chỉ dựa trên việc:

- Tệp `app-dynamic.jsa` tồn tại.
- Lệnh `java` in ra đúng dòng `AppCDS demo: sum=15`.
- Flag `-XX:SharedArchiveFile` có xuất hiện trong startup script.
- Log chỉ nói CDS được bật trong cấu hình mà không cho thấy archive được nạp phù hợp.

**Bằng chứng tốt hơn** là log JVM về CDS và class loading.

### 9.1. Logging ở mức tổng quan

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

`-Xlog:cds=info` dùng **Unified JVM Logging**. Tùy JDK, log cho biết archive file, vùng dữ liệu và hoạt động mapping hoặc nguyên nhân từ chối.

### 9.2. Logging class loading

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo
~~~

Các bản JDK có thể in những dòng class loading chứa dạng:

~~~text
[class,load] ... source: shared objects file
~~~

Đây là **mẫu nhận diện**, không phải stdout đầy đủ có định dạng tuyệt đối. Không phải mọi class được load đều phải hiện là đến từ shared archive, vì chỉ một số class đủ điều kiện hoặc được lưu trong lần dump.

### 9.3. Đối chiếu với cùng ứng dụng khi tắt CDS

~~~bash
java -Xshare:off -Xlog:class+load=info -cp app.jar ArchiveDemo
~~~

Khi tắt CDS, các class không được nạp từ shared archive, dù chức năng nghiệp vụ và kết quả của `main` vẫn phải đúng. Việc so hai lần chạy giúp tách **tác động CDS** khỏi **đầu ra chức năng**.

Khi log quá nhiều, lọc theo class ứng dụng hoặc tag `cds`; đừng gửi toàn bộ log class load vào telemetry production mặc định vì nó tăng I/O và kích thước log.

## 10. Điều kiện tương thích bắt buộc lưu ý

Archive CDS không phải một bộ đệm có thể sử dụng xuyên mọi môi trường. Điều kiện tạo/nạp có thể chịu ảnh hưởng của:

| Yếu tố | Tác động | Cách vận hành |
| --- | --- | --- |
| **JDK build/runtime** | Archive có thể không được chấp nhận khi đổi JDK build | Xem archive như artifact gắn với runtime cụ thể; tạo lại khi nâng JDK |
| **Kiến trúc và JVM** | Dữ liệu chia sẻ phụ thuộc implementation/nền tảng | Không copy tùy ý giữa OS/CPU/JVM khác nhau |
| **Classpath/JAR** | Classpath lúc dump và lúc chạy phải tương thích | Duy trì classpath ổn định, tái tạo archive sau khi nâng JAR |
| **JAR đã thay đổi** | Các class đã lưu có thể không khớp | Cập nhật archive cùng phiên bản ứng dụng |
| **Module/classpath options** | Một số option vô hiệu CDS hoặc hạn chế class được lưu | Đọc ràng buộc của JDK mục tiêu |
| **Base archive** | Dynamic top phụ thuộc base đã dùng khi tạo | Phát hành base/top nhất quán |
| **Quyền tệp/thư mục** | JVM phải đọc archive ở runtime, ghi được ở dump | Thiết lập ownership và permission hợp lý |
| **Ảnh container** | Path, JDK/JAR hoặc filesystem có thể đổi giữa các image | Tạo archive trong image/build phù hợp, kiểm tra đường dẫn sau deploy |

Đặc biệt, hướng dẫn `java` của JDK 17 nêu một số hạn chế:

- **Không** dùng classpath/module path chứa thư mục **không rỗng** theo cách không được CDS hỗ trợ trong quy trình được mô tả.
- Khi tạo static archive cho ứng dụng, classpath nên dùng **JAR**.
- Classpath runtime phải bằng hoặc có tiền tố là classpath lúc dump theo các quy tắc của JDK.
- JAR trong classpath hoặc module path bị thay đổi sau dump có thể khiến archive không được nạp.
- Một số option như `--upgrade-module-path`, `--patch-module`, `--limit-modules` làm CDS không hoạt động trong những trường hợp được JDK 17 mô tả.

**Không biến các hạn chế JDK 17 thành khẳng định bất biến cho mọi JDK tương lai**: các phiên bản mới có thể điều chỉnh quy tắc. Luôn dùng tài liệu đúng **JDK thực tế** để quyết định flag, classpath và khả năng nạp archive.

### Tránh classpath wildcard thay đổi ngoài ý muốn

~~~bash
java -cp "lib/*" ArchiveDemo
~~~

Wildcard có thể được launcher mở rộng thành tập JAR theo thứ tự không cố định. Nếu quá trình dump và runtime nhìn thấy bộ JAR hoặc thứ tự khác nhau, archive có thể bị từ chối hoặc không mang lợi ích như mong đợi.

Để AppCDS đáng tin trong sản xuất, nên cố định **artifact JAR/classpath** theo phiên bản phát hành và đồng bộ với archive.

## 11. Tình huống container và triển khai nhiều tiến trình

AppCDS có ích khi một hệ thống khởi động nhiều JVM cùng phiên bản ứng dụng, hoặc khi muốn tối ưu startup của dịch vụ Java. Vài nguyên tắc thực tế:

1. **Tạo archive ở giai đoạn build hoặc chuẩn bị rollout** với JDK và JAR giống môi trường chạy.
2. Đặt archive ở một đường dẫn **chỉ đọc** đối với tiến trình ứng dụng production nếu không cần tạo trong runtime.
3. Đảm bảo nhiều instance cùng nhìn thấy archive phù hợp với runtime của chúng.
4. Giữ startup command tường minh, ví dụ:
   ~~~bash
   java -XX:SharedArchiveFile=/opt/app/cds/app.jsa -cp /opt/app/app.jar ArchiveDemo
   ~~~
5. Khi nâng JDK hoặc JAR, phát hành archive mới cùng version, tránh sửa nội dung file archive đang được dùng.
6. Đo startup và bộ nhớ trước/sau; không xem “có archive” là bảo đảm cải thiện mọi workload.

Khi dùng container image, một shared archive gắn với **JDK build cụ thể** trong image. Nếu deployment chuyển sang một JDK update khác nhưng vẫn mount archive cũ từ volume dùng chung, JVM có thể không nạp được. Hãy version hóa archive theo JDK/ứng dụng hoặc tạo lại như một phần quy trình phát hành.

**Tạo dynamic archive ở cuối đời container** bằng `ArchiveClassesAtExit` có thể khó hữu ích khi filesystem container ephemeral, tiến trình bị kill đột ngột hoặc không có quyền ghi. Với deployment ổn định, ưu tiên chuẩn bị archive theo quy trình kiểm soát thay vì kỳ vọng mọi pod mới tự có archive từ lần chạy đầu.

## 12. Cách đo hiệu năng đúng

AppCDS được thiết kế để cải thiện **startup time** và có thể giảm **footprint** chia sẻ giữa các JVM. Nhưng mức lợi ích thực tế phụ thuộc ứng dụng, kích thước classpath, số lượng class tải, OS page cache, bộ nhớ, JDK và phương án đóng gói.

Một phép đo tối thiểu:

| Trường hợp | Lệnh | Mục đích |
| --- | --- | --- |
| Không CDS | `java -Xshare:off -cp app.jar ArchiveDemo` | Baseline |
| CDS mặc định | `java -Xshare:auto -cp app.jar ArchiveDemo` | Hiệu quả archive JDK có sẵn |
| AppCDS cụ thể | `java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo` | Hiệu quả archive ứng dụng |
| AppCDS + log | `java -Xlog:cds=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveDemo` | Xác nhận tải archive, không dùng làm phép đo chính |

Nên:

- Chạy nhiều lần, phân biệt **cold filesystem cache** với **warm cache**, giữ cùng JDK/JVM options.
- Đo thời điểm tiến trình đạt mốc **application ready** nếu mục tiêu là startup service, không chỉ đo thời gian chạy một hàm `main`.
- Với bộ nhớ, chú ý RSS/PSS và **trang được chia sẻ giữa tiến trình**, không chỉ một số `heap used`.
- Không bật log `class+load=info` khi benchmark chính, vì ghi log có overhead.
- Dùng cùng dữ liệu, cùng đường dẫn JAR và cùng điều kiện I/O cho các nhóm.
- Kiểm tra archive thực sự được nạp trước khi diễn giải khác biệt benchmark.

Một archive có thể chiếm thêm dung lượng đĩa và tạo thêm chi phí build/deploy; hiệu năng không phải lúc nào cũng tăng rõ. Giữ quyết định sử dụng AppCDS dựa trên số đo của **ứng dụng thật**, không dựa vào ví dụ toy.

## 13. Xử lý lỗi và câu hỏi thường gặp

### Lỗi: không tìm thấy archive

Nguyên nhân: đường dẫn tương đối bị hiểu theo working directory khác; file chưa được tạo; mount/volume không tồn tại.

Cách xử lý: xác nhận file ở đúng nơi, đủ quyền đọc, thư mục chạy thực tế; dùng đường dẫn tuyệt đối khi cần. **Không** tự tạo một file rỗng có đuôi `.jsa` để “chữa” lỗi.

### Lỗi: archive tạo bằng JDK khác

Nguyên nhân: archive chứa dữ liệu gắn với build của JVM. Dùng archive đã tạo bởi một JDK khác, kể cả khi chỉ đổi bản update, có thể khiến nạp thất bại.

Cách xử lý: tạo lại archive trên JDK/ứng dụng hiện được triển khai; không sửa byte của archive hoặc đổi tên để che lỗi.

### Lỗi: JAR/classpath thay đổi

Nguyên nhân: đường dẫn classpath, các JAR hoặc nội dung của JAR khác thời điểm dump; các ràng buộc của CDS không còn thỏa.

Cách xử lý: xây archive như artifact của đúng phiên bản ứng dụng và kiểm chứng startup command thống nhất. Không áp dụng lại archive cũ một cách vô điều kiện.

### Lỗi: không tìm được base cho dynamic archive

Nguyên nhân: dynamic archive tham chiếu base không còn tương thích hoặc không thể truy cập.

Cách xử lý: tái tạo dynamic archive từ base hợp lệ, kiểm soát di chuyển/đổi đường dẫn base; với custom base, có thể chỉ định đồng thời cả hai archive đúng dấu phân cách hệ điều hành.

### Lỗi: `-Xshare:on` làm ứng dụng không khởi động

Đây có thể là **hành vi có chủ ý của chế độ cưỡng chế** khi không sử dụng được CDS. Đừng xử lý bằng cách chuyển mọi dịch vụ production sang `-Xshare:on`; nên dùng `-Xshare:auto` hoặc chính sách mặc định theo tài liệu JVM và log để chẩn đoán.

### Lỗi: archive có rồi nhưng không thấy hiệu năng tốt hơn

Có thể chỉ lưu các class ít ảnh hưởng startup; ứng dụng nặng về network, database, JIT hoặc initialization khác; điều kiện warm/cold cache chưa được kiểm soát; hoặc archive không thực sự được nạp.

Cách xử lý: xem log, kiểm tra kịch bản tạo class list/dynamic dump, đo lại startup với workload đại diện và baseline rõ ràng.

### Lỗi: class của ứng dụng không xuất hiện trong log shared archive

Không phải mọi class đều được lưu/chia sẻ. Có thể class chưa được load lúc dump, nằm ở classpath không được hỗ trợ, hoặc có ràng buộc class loader/agent. Xem `-Xlog:class+load=info` và thông tin CDS theo JDK, không kết luận archive hoàn toàn không hoạt động chỉ từ một class chưa được chia sẻ.

## 14. Bảo mật archive và độ tin cậy

Shared archive là artifact được JVM đọc ở giai đoạn quan trọng của quá trình khởi động. Không được coi nó là bộ nhớ đệm vô hại và cho phép người dùng không đáng tin chỉnh sửa.

- Chỉ nhận archive từ **nguồn build/deploy đáng tin cậy**.
- Thiết lập quyền đọc/ghi phù hợp; tiến trình service thường không cần có quyền **ghi sửa archive đã phát hành**.
- Kiểm tra checksum/chữ ký tại tầng phát hành khi có yêu cầu supply-chain security.
- Không dựa vào `-XX:+VerifySharedSpaces` như cơ chế bảo mật mật mã: tùy chọn này thực hiện kiểm tra toàn vẹn kiểu **CRC32**, hữu ích cho phát hiện hỏng dữ liệu tình cờ, không chứng minh người tạo archive đáng tin.
- Nếu archive không hợp lệ, không cố ép JVM sử dụng để “giữ hiệu năng”; ưu tiên tính đúng đắn, khả năng khởi động và vận hành ổn định.

Khi archive được dùng chung giữa nhiều JVM, đừng thay thế tệp đang hoạt động một cách tùy tiện. Phát hành archive mới với tên/đường dẫn version hóa và chuyển startup script trong một lần triển khai có kiểm soát.

## 15. Tính năng ở JDK mới hơn: không nhầm với hướng dẫn Java 17

Cơ chế `-XX:SharedArchiveFile` vẫn có trong tài liệu `java` của **JDK 25**. Các JDK mới cũng có tiện ích mới liên quan tới cache/tối ưu khởi động:

- Trên JDK có hỗ trợ `-XX:+AutoCreateSharedArchive`, có thể dùng cùng `-XX:SharedArchiveFile=...` để tạo/nạp dynamic archive tự động theo điều kiện tương ứng. **Không đưa flag này vào ví dụ JDK 17**, bởi nó không phải option được tài liệu Java 17 mô tả cho workflow chuẩn.
- JDK mới có các cơ chế **AOT cache** riêng, với khả năng và mục tiêu khác nhau. Cần chọn theo tài liệu **đúng phiên bản JDK**; không suy đoán rằng mọi archive CDS và AOT cache đều có định dạng hoặc cờ khởi động giống nhau.

Một ví dụ theo tài liệu JDK 25 (chỉ dùng nếu JDK hiện tại hỗ trợ):

~~~bash
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=app-auto.jsa -cp app.jar ArchiveDemo
~~~

Theo mô tả của JDK 25, nếu archive phù hợp đã có thì JVM dùng nó; nếu chưa có, JVM có thể tạo khi ứng dụng thoát; khi JDK build đổi, chính sách tái tạo còn có điều kiện về phiên bản archive trước đó. Không đem lời mô tả này áp đặt cho JDK 17.

**Kết luận cho bài Java 10:** lựa chọn ổn định, hiện hành và có ví dụ rõ ràng trên Java 17+ vẫn là **`-XX:SharedArchiveFile` để nạp archive được tạo trước**, kết hợp dynamic dump (`ArchiveClassesAtExit`) hoặc static dump (`-Xshare:dump`) theo nhu cầu.

## 16. Bài tập tự kiểm tra

### Bài 1 — xác định đúng option

Chọn lệnh nạp một dynamic archive đã tạo hợp lệ:

~~~bash
# A
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar ArchiveDemo

# B
java -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveDemo

# C
java -cp app.jar ArchiveDemo -XX:SharedArchiveFile=app.jsa
~~~

**Đáp án: B.** A là chế độ **tạo** archive khi thoát, C đặt option sau main class nên chỉ là đối số của ứng dụng.

### Bài 2 — static dump cần gì?

~~~bash
java -Xshare:dump -XX:SharedClassListFile=app.classlist -XX:SharedArchiveFile=app-static.jsa -cp app.jar
~~~

Hỏi: `app.classlist` và `app-static.jsa` khác nhau thế nào?

**Đáp án:** `app.classlist` là **danh sách class làm đầu vào**, còn `app-static.jsa` là **archive được JVM tạo** ở chế độ `-Xshare:dump`.

### Bài 3 — Windows dùng dấu nào?

Cần nạp base `base.jsa` và dynamic `top.jsa` trên Windows PowerShell.

**Đáp án:**

~~~powershell
java "-XX:SharedArchiveFile=base.jsa;top.jsa" -cp app.jar ArchiveDemo
~~~

Dấu `;` phân cách hai archive. Trên Linux/macOS, dùng `base.jsa:top.jsa`.

### Bài 4 — thiếu archive khi `-Xshare:on`

Một service chạy với `-Xshare:on` và archive bị thay bởi bản không tương thích. Có thể chỉ trông chờ JVM tự bỏ qua archive và luôn khởi động không?

**Đáp án:** Không. `-Xshare:on` yêu cầu CDS; nếu không thể sử dụng, JVM có thể báo lỗi và dừng. Dùng để kiểm thử/diagnostics, không phải chế độ cưỡng chế an toàn cho production.

### Bài 5 — kiểm tra thành công

Một lệnh in đúng:

~~~text
AppCDS demo: sum=15
Java 17+ supported: true
Service ready
~~~

Có đủ bằng chứng rằng AppCDS được bật và một class ứng dụng đã được dùng từ archive không?

**Đáp án:** Không. Đây là stdout chức năng; phải kiểm tra **CDS logging** và class-loading log hoặc phép đo phù hợp. Ứng dụng có thể in y như vậy khi CDS bị tắt.

### Bài 6 — đổi JDK hoặc JAR

Archive được dump khi build image chứa JDK A và `app.jar` phiên bản X. Sau deploy, image chạy JDK B và `app.jar` phiên bản Y nhưng vẫn dùng archive cũ. Điều gì cần làm?

**Đáp án:** Xem archive là **artifact phụ thuộc JDK và ứng dụng**, tạo/kiểm chứng lại cho image mới. Không bảo đảm dữ liệu class cũ còn hợp lệ dù hai JDK cùng feature version.

### Bài 7 — tập class chưa được load

Trong lần dynamic dump, một màn hình quản trị chỉ mở sau khi người dùng đăng nhập, nên các class của màn hình đó chưa được tải. Có thể khẳng định toàn bộ class màn hình quản trị đã nằm trong `app-dynamic.jsa` không?

**Đáp án:** Không. Dynamic dump dựa trên class đã load và đủ điều kiện trong lần chạy tạo archive. Muốn mở rộng tập class, cần kịch bản tải class đại diện hoặc một cách chuẩn bị archive được hỗ trợ.

## 17. Ghi nhớ nhanh và nguồn tài liệu chuẩn

- **`-XX:SharedArchiveFile=<path>`** chọn đường dẫn CDS archive; trong chế độ static dump còn chỉ định **đích ghi**.
- **Dynamic**: lần chuẩn bị dùng `-XX:ArchiveClassesAtExit=...`, lần chạy sau dùng `-XX:SharedArchiveFile=...`.
- **Static**: `DumpLoadedClassList` → `-Xshare:dump` với `SharedClassListFile` và `SharedArchiveFile` → chạy với `SharedArchiveFile`.
- Nếu có hai tầng: **base static + top dynamic**. Dùng `:` trên Linux/macOS, `;` trên Windows.
- **`-Xshare:auto`** cho phép dùng CDS khi phù hợp; **`-Xshare:on`** dành cho kiểm thử cưỡng chế; **`-Xshare:off`** cho baseline/debug.
- Xác minh bằng `-Xlog:cds=info` và `-Xlog:class+load=info` thay vì chỉ nhìn sự tồn tại của file.
- Archive gắn với **JDK build, JAR/classpath và môi trường tương thích**; thay chúng cần kiểm chứng hoặc tạo lại.
- Tính năng mới như `AutoCreateSharedArchive` phải được dùng theo **JDK thực tế**, không tự thêm vào lệnh Java 17.
- AppCDS là **tối ưu vận hành**, không phải cơ chế bảo mật, không thay thế JAR và không cam kết startup nhanh hơn trong mọi ứng dụng.

Nguồn chính thức và đang được duy trì:

1. [Java SE 17 — The java Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#application-class-data-sharing): cú pháp `SharedArchiveFile`, static/dynamic dump, classpath, logging.
2. [Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): mục tiêu CDS, các chế độ `-Xshare`.
3. [Java SE 25 — The java Command, AppCDS/AutoCreateSharedArchive](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing): API/option còn tồn tại, cải tiến theo phiên bản JDK mới.
4. [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): nền tảng AppCDS.
5. [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): nền tảng dynamic archive.
6. [dev.java — Java launcher, Dynamic CDS archive](https://dev.java/learn/jvm/tools/core/java/): hướng dẫn workflow từ trang học Java chính thức.

**Kết luận:** `-XX:SharedArchiveFile` là cách chỉ định **đúng kho AppCDS/CDS JVM sẽ dùng**. Để vận hành thành công, không chỉ cung cấp tên file: cần **tạo archive đúng phương pháp, giữ JDK/JAR/classpath tương thích, đặt option trước main class, kiểm tra log khi chạy và kiểm soát vòng đời archive khi triển khai**.
