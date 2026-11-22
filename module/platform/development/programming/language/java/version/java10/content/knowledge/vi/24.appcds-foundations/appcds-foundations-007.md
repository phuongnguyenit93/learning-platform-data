# Lựa chọn các lớp thực sự được ứng dụng sử dụng khi tạo AppCDS archive

*Chủ đề Java 10 — Nền tảng AppCDS (Application Class-Data Sharing). Trọng tâm: chọn đúng tập class được ứng dụng **nạp trong luồng chạy thực tế**, tránh đưa cả thư viện không dùng vào archive; tạo, đối chiếu và xác minh archive bằng cơ chế HotSpot còn được hỗ trợ trên Java 17+; đồng thời hiểu lựa chọn AOT mới trên JDK 24/25.*

## 1. Vấn đề và câu trả lời ngắn

Một ứng dụng Java có thể khai báo hàng trăm JAR, mỗi JAR chứa hàng nghìn lớp. Nhưng khi khởi động, ứng dụng có thể chỉ thực sự **nạp (load)** một phần nhỏ số lớp đó. AppCDS cho phép lưu thông tin lớp đã được JVM xử lý trước vào một archive để các lần chạy sau dùng lại nhanh hơn. Vì archive tiêu tốn dung lượng đĩa, RAM ánh xạ và công sức xây dựng, không nên cố đóng gói **mọi lớp xuất hiện trong dependency tree**.

**Nguyên tắc chọn:** quan sát **những lớp JVM nạp trong một hoặc nhiều lượt chạy đại diện**, ưu tiên những lớp cần cho đường khởi động và thao tác đầu tiên có tác động tới độ trễ. Không chọn chỉ theo tên package, số lượng JAR, tệp `.class` hoặc một danh sách dependency có mặt trên classpath.

Ví dụ ứng dụng có ba lớp:

- `demo.App` — entry point, chắc chắn chạy.
- `demo.HotService` — được gọi trong mỗi lần chạy thường.
- `demo.RareService` — chỉ được gọi khi có tham số `--rare`.

Khi chạy một lượt đại diện **không có `--rare`**, JVM nạp `App` và `HotService`; `RareService` không được tải trong lượt đó. Class list/archiving dựa trên lượt này có thể tập trung vào các lớp đã được quan sát. Khi một lần chạy sau cần `RareService`, chương trình vẫn có thể nạp nó **bình thường từ JAR**, dù lớp ấy không nằm trong archive.

**Lựa chọn lớp cho AppCDS là tối ưu hóa phạm vi được chia sẻ, không phải giới hạn những lớp ứng dụng được phép sử dụng.**

## 2. AppCDS là gì và liên hệ với Java 10

**CDS** (*Class-Data Sharing*) là kỹ thuật của HotSpot lưu trước dữ liệu đã xử lý của các class trong một archive `.jsa`. JVM có thể memory-map những vùng phù hợp của archive; nhiều tiến trình Java tương thích có thể chia sẻ phần metadata chỉ đọc của lớp. Điều này thường làm giảm việc đọc/diễn giải bytecode và các chi phí khởi tạo lớp liên quan lúc startup.

**AppCDS**, được giới thiệu cho ứng dụng trong Java 10 qua **JEP 310**, mở rộng phạm vi CDS từ những lớp cốt lõi sang lớp của ứng dụng và thư viện được nạp trong ngữ cảnh được hỗ trợ. Mục đích chính:

1. **Rút ngắn startup** khi ứng dụng cần nạp nhiều class.
2. **Giảm footprint có thể chia sẻ giữa tiến trình JVM**, đặc biệt khi chạy nhiều instance trên cùng host.
3. **Tái sử dụng dữ liệu class** đã chuẩn bị trong archive, thay vì mỗi JVM phải xử lý toàn bộ từ JAR vào đầu mỗi lần chạy.

AppCDS **không** lưu đối tượng ứng dụng bất kỳ, không tự giữ dữ liệu database của người dùng, không bảo đảm giảm thời gian chạy một thuật toán CPU-bound, và không phải thay thế cho JIT. Các tối ưu hóa AOT khác ở JDK hiện đại có thể làm nhiều hơn, nhưng bài này tập trung vào **chọn các lớp thực sự dùng** trong AppCDS.

Theo hướng dẫn `java` của JDK 25, dữ liệu class lưu trong archive có thể lớn khoảng **2–5 lần** so với dữ liệu class tương ứng trong JAR/JDK runtime image. Đây là lý do thực tế nên tránh đưa vô tội vạ mọi class không dùng vào archive. Con số này mô tả cách biểu diễn dữ liệu lớp, **không** có nghĩa kích thước tổng archive luôn bằng 2–5 lần toàn bộ JAR.

### 2.1. AppCDS vẫn áp dụng, nhưng bối cảnh JDK đã tiến hóa

- **Java 10:** JEP 310 đưa Application CDS vào HotSpot.
- **Java 13+:** JEP 350 hỗ trợ **dynamic CDS archive**, có thể ghi archive lúc ứng dụng thoát bằng `-XX:ArchiveClassesAtExit`; giảm nhu cầu tạo class list thủ công.
- **Java 17+:** cách tạo static/dynamic AppCDS archive và kiểm tra class sharing vẫn dùng được trên HotSpot thông dụng.
- **JDK 24:** JEP 483 đưa mô hình **AOT cache** cho việc nạp/liên kết class trước.
- **JDK 25:** JEP 514 đơn giản hóa thao tác tạo AOT cache và có thêm tối ưu hóa từ JEP 515. Với dự án mới đang triển khai JDK 25, nên **đánh giá AOT cache cùng AppCDS**, thay vì mặc định cách làm thủ công từ Java 10 luôn là lựa chọn tốt nhất.

Vì vậy, không nên hướng dẫn như thể Java 10 là JDK duy nhất có AppCDS hoặc các flag xưa đã lỗi thời vẫn bắt buộc. Phần dưới cung cấp **quy trình hiện còn hoạt động** trên Java 17+ và nêu cách tiếp cận AOT mới khi phù hợp.

## 3. “Thực sự được sử dụng” là gì? Phân biệt load, link, initialize, execute

Cần hiểu chính xác mức quan sát của cơ chế CDS.

| Khái niệm | Ví dụ | Liên quan tới AppCDS |
| --- | --- | --- |
| Class **có mặt** trong JAR | `RareService.class` được đóng gói trong `app.jar` | Chưa chứng minh nó được nạp |
| Class **được load** | JVM tạo mô tả cho `HotService` khi cần | Là tín hiệu quan trọng khi thu thập class list/training |
| Class **được link/verify** | JVM thực hiện các bước theo quy tắc linkage | CDS có thể lưu dữ liệu phục vụ việc sử dụng lại ở JVM tương thích |
| Class **được initialize** | Thực hiện static initializer theo luật Java | Không đồng nghĩa mỗi class load đều đã chạy static initializer |
| Method **được execute** | `HotService.message()` chạy trong request | Thường làm class liên quan được load, nhưng load không đòi hỏi mọi method phải chạy |
| Class **được archive thành công** | Log nạp cho thấy `source: shared objects file` | Cần kiểm chứng riêng; không phải mọi class được load đều chắc chắn đủ điều kiện archive |

Một class được JVM **nạp** có thể chưa từng được sử dụng theo nghĩa business feature thật sự, ví dụ framework chủ động quét class, reflection hoặc service discovery. Ngược lại, một class không được nạp trong training vẫn có thể cần trong một nhánh chạy hiếm ở production.

**Tiêu chí lựa chọn không phải “đã chạy một method nào chưa?”** mà là “lớp đó có được JVM load trong workload mục tiêu, đủ điều kiện archiving và hữu ích cho đường startup hoặc early workload không?”. Các class đủ điều kiện cuối cùng còn chịu ràng buộc HotSpot, class loader, JAR, module và cấu hình runtime.

### 3.1. Classpath không phải danh sách class đã load

Ví dụ:

~~~text
app.jar
  demo/App.class
  demo/HotService.class
  demo/RareService.class

Lần chạy thông thường:
  demo.App            loaded
  demo.HotService     loaded
  demo.RareService    not loaded
~~~

Các class có mặt trên classpath là **ứng viên**; JVM không bắt buộc mở và xử lý tất cả `.class` trong JAR lúc khởi động. Việc tự đọc `jar tf app.jar` rồi đem mọi class vào class list tạo ra công sức và dung lượng không cần thiết, đồng thời không phản ánh workload.

### 3.2. Class list là bằng chứng từ một run, không phải sự thật của mọi run

Nếu chạy:

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.App
~~~

lượt chạy này phản ánh **đường code và điều kiện được kích hoạt khi đó**. Nó không tự kích hoạt mọi nhánh trong hệ thống. Nếu cần tối ưu hóa startup REST endpoint hoặc job cụ thể, phải chọn training workload phù hợp với thực tế.

**Đừng hiểu lầm:** class list được sinh có thể chứa cả lớp chuẩn JDK và những lớp thư viện được nạp; nó **không chỉ chứa class do nhóm phát triển viết**, và một dòng class list không tự bảo đảm JVM sẽ archive class ấy thành công.

## 4. Mục tiêu chọn lớp phải xuất phát từ workload

Một AppCDS archive tốt cần phục vụ **mục tiêu vận hành**, không phải “archive càng nhiều class càng tốt”.

### 4.1. Ứng dụng CLI hoặc serverless startup ngắn

Ưu tiên những lớp được nạp từ:

- Entry point và phần cấu hình cơ bản.
- Các lớp framework bắt buộc để bắt đầu xử lý tác vụ.
- Phần khởi tạo DI/serialization/HTTP client cần thiết.
- Những đường code có mặt trong **lệnh chạy tiêu biểu**.

Không cần ép tải các provider/format chưa dùng chỉ vì chúng có mặt trong dependency.

### 4.2. Dịch vụ HTTP server dài hạn

Định nghĩa mục tiêu rõ: giảm **thời gian tiến trình sẵn sàng nhận request**, giảm **độ trễ request đầu tiên**, hay tối ưu **nhiều JVM cùng host**?

Training có thể cần đi qua:

1. Startup thực với cùng các cờ JVM, classpath/module path và profile cấu hình mục tiêu.
2. Khởi tạo phần framework/container.
3. Readiness/health check đúng với hệ thống.
4. Một vài request **đại diện, an toàn và không ghi dữ liệu thật** để nạp serialization/validation/provider hay các lớp sẽ cần ở request đầu tiên.
5. Shutdown sạch để kết thúc việc ghi archive động nếu dùng `ArchiveClassesAtExit`.

Không nên tạo hàng loạt request business nguy hiểm chỉ để nạp thêm class; có thể dùng test fixture, database giả lập, staging dữ liệu vô hại và mã hóa giới hạn workload.

### 4.3. Ứng dụng nhiều tính năng tùy chọn

Nếu một tính năng chỉ được chạy bởi một phần nhỏ người dùng hoặc không nằm trong đường khởi động cần tối ưu, lớp của nó **không nhất thiết phải xuất hiện trong archive mặc định**. Tuy nhiên, nếu tính năng hiếm lại có SLA “first-use latency” rất quan trọng, có thể tạo profile archive riêng hoặc đưa scenario ấy vào training **sau khi đo trade-off**.

Với kiến trúc plug-in, các class được nạp qua class loader đặc biệt phải được kiểm tra về **điều kiện archive của implementation đang dùng**, không giả định cứ load qua reflection/custom loader là tất cả được chia sẻ.

## 5. Ví dụ tối thiểu: class được dùng thường xuyên và class chỉ dùng theo nhánh

Tạo file `src/demo/App.java` với toàn bộ code sau:

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        HotService hot = new HotService();
        System.out.println("HOT=" + hot.message());

        if (args.length > 0 && args[0].equals("--rare")) {
            RareService rare = new RareService();
            System.out.println("RARE=" + rare.message());
        }
    }
}

final class HotService {
    String message() {
        return "ready";
    }
}

final class RareService {
    String message() {
        return "optional";
    }
}
~~~

Đây là **một file Java đầy đủ**, hợp lệ với Java 17. `HotService` và `RareService` là hai class package-private được khai báo trong cùng source file với `App`; compiler vẫn tạo ba file `.class` riêng.

Tạo cây thư mục và đóng gói JAR. Ví dụ trên bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p src/demo out
# Lưu nội dung Java ở trên vào src/demo/App.java
javac --release 17 -d out src/demo/App.java
jar --create --file app.jar --main-class demo.App -C out .
~~~

Trên PowerShell Windows, có thể tạo `src\demo`/`out` bằng `New-Item -ItemType Directory` rồi chạy hai lệnh `javac` và `jar` giống cách trên. Đây là bước **build thông thường**: có thể dùng pipeline Maven/Gradle trong dự án thật, miễn là kết quả JAR và classpath đáp ứng các ràng buộc CDS.

Kiểm tra hai luồng chạy:

~~~bash
java -cp app.jar demo.App
java -cp app.jar demo.App --rare
~~~

Stdout chính xác:

~~~text
# Run không có --rare:
HOT=ready

# Run có --rare:
HOT=ready
RARE=optional
~~~

Hai trường hợp dùng **cùng JAR**. Nhưng `RareService` chỉ cần được nạp trong lần thứ hai. Đây là cơ sở trực quan cho quy tắc: **một class có sẵn trong JAR không nhất thiết đã được sử dụng trong run dùng làm training**.

## 6. Quy trình AppCDS tĩnh: thu thập những class đã nạp rồi tạo archive

Đây là quy trình được tài liệu `java` của JDK 17/25 tiếp tục hỗ trợ cho HotSpot. Nó giúp nhìn thấy rõ cách chọn class theo run đại diện.

### Bước 1 — Thu thập class list

~~~bash
java -Xshare:off \
  -XX:DumpLoadedClassList=app.classlist \
  -cp app.jar demo.App
~~~

Lệnh viết theo cú pháp shell bash với dấu `\` nối dòng. Trên PowerShell, viết thành một dòng để tránh khác biệt nối dòng:

~~~powershell
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.App
~~~

Kết quả của chương trình:

~~~text
HOT=ready
~~~

Ý nghĩa các tùy chọn:

| Option | Tác dụng |
| --- | --- |
| `-Xshare:off` | Tắt sử dụng archive trong lượt thu thập; đây là cách minh họa được hướng dẫn `java` dùng để lấy danh sách load |
| `-XX:DumpLoadedClassList=app.classlist` | Ghi danh sách class JVM nạp trong lượt chạy |
| `-cp app.jar` | Cho JVM biết ứng dụng nằm trong JAR nào |
| `demo.App` | Chạy entry point để tạo luồng load thực tế |

**Quan sát thật khi kiểm thử JDK 24:**

~~~text
app.classlist chứa demo/App:          true
app.classlist chứa demo/HotService:   true
app.classlist chứa demo/RareService:  false
~~~

Class list còn chứa rất nhiều class của Java runtime: trong một lượt kiểm thử cụ thể có **1.358 dòng**. **Con số này phụ thuộc JDK và workload**, không phải chuẩn bắt buộc của Java.

Điều quan trọng không phải số dòng tuyệt đối mà là: class thuộc **nhánh hot** đã xuất hiện, class thuộc **nhánh rare không kích hoạt** chưa xuất hiện.

### Bước 2 — Sinh static archive từ class list

~~~bash
java -Xshare:dump \
  -XX:SharedArchiveFile=app-static.jsa \
  -XX:SharedClassListFile=app.classlist \
  -cp app.jar
~~~

PowerShell một dòng:

~~~powershell
java -Xshare:dump -XX:SharedArchiveFile=app-static.jsa -XX:SharedClassListFile=app.classlist -cp app.jar
~~~

Giải thích:

- `-Xshare:dump` yêu cầu HotSpot tạo CDS archive.
- `-XX:SharedClassListFile` cung cấp class list được ghi trong training.
- `-XX:SharedArchiveFile` chỉ định file archive đích.
- `-cp app.jar` cung cấp classpath tương thích với các class cần archive.

**Quan trọng:** classpath dùng để tạo archive tĩnh theo hướng dẫn này cần gồm **JAR**, không dùng thư mục `out` đầy class như một phần classpath không rỗng. Trong thử nghiệm, archive được tạo thành công từ `app.jar`.

Quá trình dump có thể thực hiện xử lý/lưu thông tin class để các lần JVM sau nạp được nhanh hơn. **Không khẳng định mỗi class trong class list đều chắc chắn được lưu**: HotSpot có thể bỏ một số lớp do ràng buộc kỹ thuật hoặc không phù hợp.

### Bước 3 — Chạy lại với archive

~~~bash
java -Xshare:on \
  -XX:SharedArchiveFile=app-static.jsa \
  -cp app.jar demo.App
~~~

Stdout ứng dụng:

~~~text
HOT=ready
~~~

`-Xshare:on` dùng ở **bài kiểm thử** để yêu cầu sharing hoạt động; nếu archive không sử dụng được, JVM sẽ báo lỗi thay vì âm thầm fallback. Ở môi trường production, cần cân nhắc tùy chọn/chế độ khởi động của HotSpot và chính sách fallback phù hợp, không mặc định tất cả triển khai có cùng mức hỗ trợ cho mọi flag `-X`/`-XX`.

### Bước 4 — Kiểm chứng class thực sự được chia sẻ

~~~bash
java -Xshare:on \
  -XX:SharedArchiveFile=app-static.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App
~~~

Tìm bản ghi tương ứng trong log:

~~~text
demo.HotService source: shared objects file
~~~

Đoạn trên là **phần ý nghĩa của log**, không phải toàn bộ một dòng log với timestamp/tag. Nếu thấy `source: shared objects file` cho class cụ thể, đó là bằng chứng class đang được nạp từ CDS archive trong run ấy.

Với chương trình mẫu, kết quả thực nghiệm:

~~~text
HotService được ghi vào class list: true
HotService được nạp từ archive:     true
RareService nạp trong run thường:   false
~~~

### Bước 5 — Chạy nhánh hiếm với cùng archive

~~~bash
java -Xshare:on \
  -XX:SharedArchiveFile=app-static.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App --rare
~~~

Stdout:

~~~text
HOT=ready
RARE=optional
~~~

JDK 24 kiểm thử cho thấy `demo.RareService` **được nạp trong run này** nhưng **không lấy từ shared objects file**. Ứng dụng vẫn chạy đúng vì HotSpot lấy class chưa có trong archive từ JAR theo đường class loading thông thường.

**Kết luận thực hành:** AppCDS không đòi bạn tạo một archive chứa mọi class có thể được gọi. Nếu một class chưa có trong archive, chương trình có thể nạp nó bình thường. Tuy nhiên, nếu class ấy xuất hiện trong startup workload quan trọng về latency, việc chưa archive có thể làm mất cơ hội tối ưu cho đường đó.

## 7. Quy trình AppCDS động: chọn class được load tại lúc chạy

Từ JDK 13 (JEP 350), dynamic CDS giúp giảm số bước: cho ứng dụng chạy một lượt training và tạo archive khi JVM thoát.

~~~bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa \
  -cp app.jar demo.App
~~~

Trên PowerShell:

~~~powershell
java -XX:ArchiveClassesAtExit=app-dynamic.jsa -cp app.jar demo.App
~~~

Sau khi JVM **kết thúc bình thường**, archive động có thể được ghi ra:

~~~text
app-dynamic.jsa
~~~

Sau đó chạy:

~~~bash
java -Xshare:on \
  -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App
~~~

Trong ví dụ đã kiểm thử, `HotService` được nạp từ `shared objects file` và chương trình in:

~~~text
HOT=ready
~~~

Archive động chủ yếu lưu phần class **không có sẵn trong base CDS archive**. Nó thường nhỏ hơn một static archive có chứa nhiều thông tin lớp cơ sở. **Không được xem kích thước archive động nhỏ là bảo đảm ứng dụng chạy nhanh hơn archive tĩnh**: phương pháp cần được đo.

Ở môi trường thử nghiệm cụ thể:

| Phần được tạo | Kết quả |
| --- | --- |
| Static archive từ class list | Có file `app-static.jsa` |
| Dynamic archive từ training run | Có file `app-dynamic.jsa` |
| `demo.HotService` từ static archive | Có |
| `demo.HotService` từ dynamic archive | Có |
| `demo.RareService` trong run thường | Không được load |
| `demo.RareService` trong run `--rare` | Load thành công từ đường không chia sẻ |

Một snapshot về file size trong thử nghiệm là **10.092.544 byte** cho static archive và **262.144 byte** cho dynamic archive. Đây chỉ là kết quả cụ thể trên JDK/OS/workload đó; **không phải** mức dung lượng chuẩn hoặc con số dùng để dự đoán production.

### 7.1. Khi nào chọn static class list?

Dùng static workflow khi cần:

- Kiểm toán **chính xác một class list** đã thu thập và lưu như artifact build.
- Hiểu tại sao một class được/không được chọn.
- Kết hợp training từ những scenario có kiểm soát và chạy dump tái lập.
- Điều chỉnh tập class có chủ đích và so sánh sự thay đổi với build khác.

### 7.2. Khi nào chọn dynamic archive?

Dùng dynamic workflow khi:

- Muốn tránh bước tạo và quản lý class list thủ công.
- Có thể chạy một **training workload thực tế** đến lúc JVM thoát.
- Cần tạo overlay archive trên default CDS archive trong quy trình build/deploy.
- Đang dùng HotSpot phiên bản hỗ trợ chức năng này và tương thích với JAR/config runtime.

Không có nghĩa dynamic archive tự biết mọi class sẽ xuất hiện trong production: **nó cũng dựa vào những class được load ở training**.

## 8. Lựa chọn class bằng các scenario đại diện

Một training workload nên **đại diện cho đường code bạn muốn tối ưu**. Không nhất thiết phải thực thi mọi tính năng nghiệp vụ.

### 8.1. Mức khởi động tối thiểu

Chỉ khởi chạy ứng dụng, khởi tạo framework và thoát. Cách này chọn lớp phục vụ bootstrap. Nó phù hợp khi mục tiêu là giảm startup của CLI ngắn hoặc thời gian chuẩn bị JVM.

Rủi ro: trong server, các lớp như serializer hoặc controller handler có thể được load **muộn, ở request đầu tiên**, nên lượt training chỉ boot sẽ bỏ sót các class ảnh hưởng “first request latency”.

### 8.2. Mức khởi động + các request đầu tiên

Đưa vào một số endpoint hoặc tác vụ representative:

~~~text
boot application
  -> dependency injection initialization
  -> HTTP/router ready
  -> health/readiness endpoint
  -> một request điển hình /orders/{id}
  -> serialization thành JSON
  -> graceful shutdown
~~~

Không gọi endpoint gây thanh toán, xóa dữ liệu hoặc thay đổi trạng thái production chỉ để nạp class. Dùng environment staging/training và test fixtures.

Ưu điểm: capture thêm class thực sự cần ngay sau startup. Nhược điểm: archive có thể lớn hơn, phải bảo trì khi API/feature set đổi.

### 8.3. Mức đa scenario

Nếu cần nhiều đường code có SLA rõ, có thể thiết kế nhiều **profile training riêng** hoặc một kịch bản kết hợp, tùy tính năng của HotSpot và ngân sách lưu archive. Đo runtime startup và first-use latency cho từng lựa chọn.

Không tự chỉnh class list bằng cách hợp nhất dòng từ nhiều classloader/run mà không tuân thủ grammar/ID/source metadata của file class list: class list có thể chứa thông tin phụ trợ cho archived classes. Cách an toàn là dùng công cụ chính thức, quá trình build hoặc một training run có các scenario cần thiết.

### 8.4. Mức tải đầy mọi class — thường không cần

Đừng đi qua toàn bộ classpath rồi gọi `Class.forName(...)` cho từng lớp chỉ để chúng xuất hiện trong list:

- Có thể kích hoạt side effect hoặc class initialization ngoài ý muốn.
- Có thể chạm vào class yêu cầu môi trường/vùng dữ liệu chưa sẵn sàng.
- Kích thước archive tăng mà startup không được cải thiện.
- Framework/plugin có thể có class không phù hợp để archive.
- Có thể làm mất sự khác biệt giữa **lớp cần cho workload thật** và **lớp chỉ tồn tại trong dependency**.

`Class.forName` mặc định có thể kích hoạt class initialization, nên càng không phù hợp như một “scanner vô hại” để ép tải mọi class.

## 9. Lập danh sách lớp theo số liệu đo thay vì dự đoán

Khi đánh giá một candidate class, nên hỏi:

| Câu hỏi | Gợi ý đánh giá |
| --- | --- |
| Class có được nạp trong run đại diện không? | `DumpLoadedClassList`, `-Xlog:class+load=info` |
| Class nằm ở startup/early requests hay ở nhánh hiếm? | Tracing kịch bản, profiling startup |
| Class đủ điều kiện/được archive thật chưa? | Log class load `shared objects file`, log CDS |
| Lớp đến từ JAR/module nào? | Class loader và source trong log |
| Đưa thêm class có làm archive lớn quá không? | So file size và số class thực tế có ích |
| Chạy với archive có rút ngắn startup không? | Benchmark A/B nhiều lượt |
| Có giảm footprint khi nhiều JVM chạy cùng host không? | Đo PSS/RSS và shared pages phù hợp OS |
| Classpath/JAR/JDK có thay đổi thường xuyên không? | Chính sách rebuild archive |
| Dữ liệu production có nhánh nào không xuất hiện trong training? | Kế hoạch fallback và đo first-use latency |

Không nên dùng số dòng `app.classlist` làm KPI duy nhất. Nó có thể gồm nhiều class JDK core và class chỉ được load do framework. KPI cần gắn với mục tiêu startup/footprint thực tế.

### 9.1. Cách kiểm tra `classlist`

Nội dung class list không chỉ gồm tên package bình thường; class names dùng dấu `/`:

~~~text
demo/App
demo/HotService
~~~

Lọc bằng công cụ text của hệ điều hành:

~~~bash
grep 'demo/' app.classlist
~~~

Hoặc PowerShell:

~~~powershell
Select-String -Path app.classlist -Pattern 'demo/'
~~~

**Lưu ý:** Các ví dụ output ở đây chỉ là lớp ứng dụng. Class list thực có thể chứa hàng nghìn dòng gồm thông tin class chuẩn và metadata khác. Chỉ lọc xem danh sách, **không** tự xóa mọi dòng khác trước khi dump nếu chưa hiểu format/quan hệ.

### 9.2. Cách xác minh archive được nạp

~~~bash
java -XX:SharedArchiveFile=app-static.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App
~~~

Tìm class quan tâm:

~~~text
demo.HotService source: shared objects file
~~~

Một dòng chỉ có `demo.HotService source: file:/.../app.jar` (hoặc nguồn JAR tương đương) **không** chứng minh class đang được share. Nó cho thấy class được load bình thường từ JAR.

Có thể thêm:

~~~bash
java -Xlog:cds=info \
  -XX:SharedArchiveFile=app-static.jsa \
  -cp app.jar demo.App
~~~

Đây là log hỗ trợ chẩn đoán CDS; xem log phù hợp bản JDK. Đừng dựa vào một câu log nguyên văn bất biến giữa mọi HotSpot release.

## 10. Giới hạn và điều kiện tương thích của archive

Dù class đã được load ở training, việc tái sử dụng AppCDS archive còn bị ràng buộc bởi môi trường.

### 10.1. Cùng JDK build và kiến trúc tương thích

CDS archive có dữ liệu nội bộ của JVM. Một archive được tạo bởi **JDK build cụ thể** không phải file portable giữa mọi vendor/version/OS/CPU. Khi nâng JDK hoặc đổi runtime image, thông thường phải **tạo lại archive bằng đúng môi trường đích**.

Không phát hành `app.jsa` cùng một lần rồi tái sử dụng vô hạn cho mọi phiên bản Java và nền tảng. Trong container, nên tạo archive trong image/build chain phù hợp với runtime mà image sẽ chạy.

### 10.2. JAR/classpath phải phù hợp

Tài liệu `java` hiện hành có các ràng buộc cho classpath/module path và JAR content:

- Với AppCDS static/dynamic dùng các workflow minh họa, classpath/module path không nên chứa những **thư mục class không rỗng** không được hỗ trợ để archive.
- Dùng JAR đã đóng gói ổn định; ví dụ `-cp app.jar` thay vì `-cp out`.
- Classpath khi tạo archive phải phù hợp với lúc chạy; theo hướng dẫn JDK 25, classpath ở lúc tạo archive cần là **cùng hoặc là prefix** của classpath runtime trong các trường hợp được cho phép.
- JAR bị sửa sau khi archive tạo có thể khiến archive không thể nạp. Đừng chỉ nhìn file name giống nhau rồi kết luận nội dung vẫn phù hợp.
- Module path và custom classloader có ràng buộc khác; hãy kiểm tra Javadoc/launch documentation của JDK đang sử dụng.

**Kiểm tra an toàn:** chạy thử với `-Xshare:on` trong CI cho runtime cấu hình đó; nếu archive không dùng được, sửa quy trình build/training thay vì giả định JVM đã sử dụng nó.

### 10.3. Không dựa vào archive có sẵn để che thiếu dependency

Một class nằm trong archive không có nghĩa ứng dụng có thể bỏ JAR chứa nó khỏi artifact triển khai. CDS không phải cơ chế publish class độc lập hay thay thế dependency declaration/classpath. Giữ classpath đúng với ứng dụng.

### 10.4. Bảo vệ tính toàn vẹn artifact

Archive cũng là một artifact của triển khai. Hãy xây nó từ code/JDK đáng tin, kiểm soát quyền ghi và chống thay đổi trái phép. HotSpot có tùy chọn kiểm tra integrity như `-XX:+VerifySharedSpaces` trong một số bối cảnh; nhưng kiểm tra checksum **không thay thế** xác thực nguồn build, quyền truy cập file và cơ chế cung ứng phần mềm an toàn.

## 11. Lựa chọn archive tĩnh và archive động: ưu/nhược

| Tiêu chí | Static AppCDS | Dynamic AppCDS |
| --- | --- | --- |
| Cách chọn class | Thu thập class list qua run đại diện | JVM ghi những class phù hợp đã load khi run training |
| Công đoạn chính | Classlist → archive → runtime | Training/exit tạo archive → runtime |
| Kiểm tra danh sách ứng viên | Rất rõ vì có `.classlist` | Cần dựa vào log/tracing nếu muốn danh sách chi tiết |
| Phụ thuộc default CDS base archive | Có thể tạo static archive riêng | Dynamic thường là top-layer trên base archive |
| Dung lượng | Có thể bao gồm nhiều class base | Thường gọn hơn do không lưu lặp class base |
| Mức tùy biến | Phù hợp quy trình build cần class list rõ | Phù hợp workflow ít thao tác hơn |
| Rủi ro thiếu nhánh | Vẫn có nếu training không đại diện | Vẫn có nếu training không đại diện |
| Cách kiểm chứng | `-Xlog:class+load=info`, `-Xshare:on` | Tương tự |
| Nền tảng | HotSpot hỗ trợ trên JDK hiện đại | JDK 13+ HotSpot |

Trong một ứng dụng mới trên JDK 25, có thể cân nhắc **AOT cache** như một lựa chọn ưu tiên để đạt tối ưu hóa nạp/liên kết class sâu hơn. Nó **không xóa bài học quan trọng**: archive/cache vẫn cần một workload training thể hiện những class và đường code thật sự được sử dụng.

## 12. Bối cảnh hiện đại: AOT cache của JDK 24/25

Vì Special Note yêu cầu chỉ lấy kiến thức còn áp dụng, cần đặt AppCDS trong bối cảnh JDK mới:

- JDK 24 đưa **Ahead-of-Time Class Loading & Linking** qua JEP 483. AOT cache có thể lưu những class đã nạp và liên kết dựa trên training.
- JDK 25 đưa **Ahead-of-Time Command-Line Ergonomics** qua JEP 514: tạo AOT cache bằng một lệnh ở những runtime hỗ trợ, thay vì người dùng tự điều phối nhiều bước.
- Các tối ưu hóa khác như **Ahead-of-Time Method Profiling** (JEP 515) hướng tới cải thiện warmup. Đây là phạm vi rộng hơn AppCDS tĩnh truyền thống.

Ví dụ **trên JDK 25+ hỗ trợ tùy chọn tương ứng**, sau khi đóng gói `app.jar`:

~~~bash
java -XX:AOTCacheOutput=app.aot -cp app.jar demo.App
java -XX:AOTCache=app.aot -cp app.jar demo.App
~~~

Lệnh đầu dùng run của ứng dụng làm training và tạo cache `app.aot` theo mô hình JDK 25. Lệnh thứ hai sử dụng cache. **Hai lệnh này không được khai báo là chạy được trên Java 17**, vì chức năng AOT cache kiểu mới chưa có trong JDK 17. Chương trình Java dùng trong bài vẫn biên dịch `--release 17`, còn các JVM flags phụ thuộc **JDK chạy**.

Khi lựa chọn AppCDS hay AOT cache, cần đo thực tế:

- Startup latency.
- Warmup/first-response latency.
- Dung lượng archive/cache.
- RAM footprint (đặc biệt khi nhiều JVM dùng chung).
- Khả năng tái lập cache sau đổi JDK/image.
- Sự tương thích với classpath/module path và các đặc tính ứng dụng.

**Không trộn** một archive `.jsa` của AppCDS với file `.aot` rồi giả định hai cơ chế dùng cùng một flag. Chọn workflow rõ theo JDK triển khai.

## 13. Cách benchmark có ích cho việc chọn class

Chỉ thấy log “shared objects file” **chưa chứng minh** startup đã nhanh hơn đáng kể. Một benchmark phù hợp nên:

1. Định nghĩa endpoint/tác vụ và tiêu chí kết thúc (ví dụ “HTTP ready” hoặc “hoàn thành command”).
2. Dùng **cùng JDK, cùng JAR, cùng môi trường, cùng tài nguyên CPU/RAM**.
3. Chạy nhiều lượt có và không có archive/cache; không lấy một run đơn lẻ làm kết luận.
4. Kiểm soát warm/cold OS file cache nếu mục tiêu có xét tới.
5. Tách thời gian JVM bootstrap, framework start, kết nối DB/network và request đầu tiên khi có thể.
6. So median/p50, p95 và độ biến thiên, không chỉ so trung bình.
7. Với footprint, đo phù hợp OS, ví dụ thông tin shared pages/PSS khi có nhiều JVM đồng thời.
8. So cả **kích thước archive** và **mức cải thiện**, tránh chấp nhận archive rất lớn để đổi lấy mức lợi không đáng kể.
9. Chạy lại sau thay đổi dependency, JDK, image container hoặc classpath.

Ví dụ ý tưởng khảo sát:

~~~text
Profile A: chỉ startup
  archive size = nhỏ hơn
  startup time = đo từ nhiều lần
  first request = có thể chậm hơn vì một số class chưa archive

Profile B: startup + first request
  archive size = có thể lớn hơn
  startup time = cần đo
  first request = có thể nhanh hơn

Profile C: tải mọi tính năng
  archive size = có thể rất lớn
  lợi ích = chưa chắc vượt A/B
~~~

Không có profile nào “luôn tốt nhất” nếu chưa có workload và số đo. Mục đích của việc **lựa chọn các lớp thật sự dùng** là tìm một điểm cân bằng hợp lý theo sản phẩm.

## 14. Debug khi AppCDS không cho kết quả mong đợi

### 14.1. Class có trong JAR nhưng không trong class list

**Khả năng:** đường code tương ứng không được kích hoạt ở training, class chỉ load theo request/reflection/plugin, hoặc điều kiện khởi động khác.

**Cách xử lý:** tái hiện workload dự kiến trên môi trường training an toàn; bật `-Xlog:class+load=info`, tìm class, xem nó được load lúc nào. Không tự chép tên tất cả class vào list như cách thay thế điều tra.

### 14.2. Có trong class list nhưng không load từ archive

**Khả năng:** class không đủ điều kiện được archive, lỗi path/JAR, classloader không tương thích, archive chưa có class ấy, mismatch JDK/build hoặc chưa thật sự dùng archive.

**Cách xử lý:** xem log CDS và class-load, xác minh command-line, build JDK, JAR content, classpath/module path. Nếu cần, dùng `-Xshare:on` trong CI/test để phát hiện archive bị bỏ qua; không tự khẳng định chỉ cần classlist chứa tên là đủ.

### 14.3. Chạy với archive bị từ chối

**Khả năng:** JDK build khác, JAR thay đổi, path không phù hợp, cấu hình JVM khác ràng buộc khi dump.

**Cách xử lý:** xem thông báo lỗi cụ thể; tạo lại archive từ chính artifact/runtime sẽ triển khai, giữ các đường dẫn/config theo giới hạn JDK đã chọn.

### 14.4. Có sharing nhưng startup không cải thiện

**Khả năng:** ứng dụng quá nhỏ, startup bị chi phối bởi I/O mạng/DB, JVM khác đang sử dụng default CDS đủ tốt, lớp archive không nằm trên critical path, hay kích thước archive làm I/O lớn hơn.

**Cách xử lý:** benchmark profiler có tiêu chí rõ. Có thể giảm/tăng phạm vi training tùy điểm nghẽn; không mặc định AppCDS luôn thắng.

### 14.5. Classloader hoặc instrumentation biến đổi bytecode

Một số framework, agent, reflection, bytecode generation, dynamic proxy hoặc custom class loader có hành vi nạp/biến đổi class đặc biệt. Chúng có thể giới hạn lớp được archive hoặc làm runtime khác với training. Với những trường hợp ấy:

- Giữ cấu hình agent/instrumentation tương thích giữa train và run.
- Kiểm tra class thực sự share, không chỉ tên.
- Không dựa vào archive làm cơ chế thực thi bắt buộc của ứng dụng.
- Ưu tiên tài liệu tương thích của framework/JDK cho loại class loader cụ thể.

## 15. Các sai lầm cần tránh

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Có mặt trong `app.jar` nghĩa là đã sử dụng.” | Class có thể chưa từng được load trong run. |
| “Archive cả dependency tree thì luôn nhanh nhất.” | Archive lớn và những class không dùng có thể tạo chi phí không có lợi ích. |
| “`DumpLoadedClassList` chỉ chứa class do ta viết.” | Nó có thể chứa JDK và thư viện khác. |
| “Có dòng trong class list nghĩa là class đã được archive.” | Cần xem quy tắc eligibility và log shared class khi runtime. |
| “Chỉ những method thực thi mới tạo class load.” | JVM có thể load class vì linkage, reflection hoặc framework. |
| “Class chưa được archive sẽ không chạy.” | JVM có thể nạp bình thường từ JAR khi cần. |
| “Một training run bao trùm mọi request.” | Chỉ phản ánh những đường code đã đi qua. |
| “Buộc tải mọi lớp bằng `Class.forName` là vô hại.” | Có thể kích hoạt initialization và side effect, làm archive phình to. |
| “Archive classlist có thể tạo trực tiếp từ `jar tf`.” | JAR inventory không phải danh sách class thực sự loaded/eligible. |
| “AppCDS chỉ tối ưu lớp của JDK.” | AppCDS mở rộng sang lớp ứng dụng/thư viện đủ điều kiện. |
| “Tạo static archive buộc phải để class trong thư mục `out`.” | Với workflow CDS này, dùng JAR ổn định; classpath directory không rỗng bị hạn chế. |
| “`-Xshare:on` luôn phải dùng ở production.” | Nó hữu ích cho test strict; lựa chọn production phụ thuộc chính sách fallback và HotSpot. |
| “Kích thước `.jsa` nhỏ chứng minh startup nhanh.” | Phải đo startup/first request/memory thực tế. |
| “Dùng lại archive qua bất kỳ JDK build nào.” | Archive liên quan runtime/JDK build; thường cần tái tạo. |
| “JAR thay đổi nhưng tên giống nhau nên archive vẫn hợp lệ.” | Nội dung JAR và cấu hình classpath phải tương thích. |
| “Dynamic archive tự tìm mọi lớp có thể chạy.” | Nó dựa trên loaded classes của training run. |
| “AppCDS ghi heap object hoặc lưu state DB.” | AppCDS lưu dữ liệu class theo cơ chế HotSpot, không lưu business state tùy ý. |
| “AOT cache JDK 25 giống hệt `.jsa` AppCDS.” | Là workflow/khả năng khác, có những tối ưu hóa rộng hơn. |
| “Cứ thấy `HOT=ready` nghĩa là class đã shared.” | Output ứng dụng chỉ chứng minh correctness; cần log `source: shared objects file`. |
| “Dùng flag deprecated `-XX:+UseAppCDS` mới bật sharing.” | Trên JDK hiện đại flag này đã obsolete; dùng workflow `-XX:SharedArchiveFile` tương ứng. |

## 16. Bài tập thực hành có đáp án

### Bài 1 — Có class nhưng không load

`app.jar` có `App`, `HotService` và `RareService`. Training chỉ chạy `demo.App` không có `--rare`. Lớp nào thuộc nhánh hot?

**Đáp án:** `App` và `HotService`. `RareService` có trong JAR nhưng không được load trong run mẫu, nên không bắt buộc có trong class list đó.

### Bài 2 — Tại sao vẫn chạy được?

Sau khi tạo archive không chứa `RareService`, bạn chạy `demo.App --rare` và kết quả là `RARE=optional`.

**Đáp án:** Class loading vẫn hoạt động bình thường. Khi không tìm được class phù hợp trong archive, JVM có thể nạp class từ JAR theo cơ chế thông thường.

### Bài 3 — Xác minh class share bằng gì?

Một run in đúng `HOT=ready`. Có đủ kết luận `HotService` đã lấy từ archive không?

**Đáp án:** Chưa. Cần bật `-Xlog:class+load=info`, kiểm tra log nguồn `demo.HotService source: shared objects file`.

### Bài 4 — Vì sao không archive mọi class?

**Đáp án:** Archive có overhead, class không dùng không giúp startup critical path. Tập class thực sự cần trong run đại diện thường nhỏ hơn toàn bộ dependency tree.

### Bài 5 — Static workflow gồm mấy giai đoạn?

**Đáp án:** Thu class list bằng training (`DumpLoadedClassList`) → dump archive (`-Xshare:dump` với `SharedClassListFile`) → chạy lại với `SharedArchiveFile` và xác minh.

### Bài 6 — Dynamic workflow được hỗ trợ từ bao giờ?

**Đáp án:** Từ JDK 13 qua JEP 350. `-XX:ArchiveClassesAtExit=app-dynamic.jsa` có thể tạo dynamic archive khi JVM thoát; sau đó dùng `-XX:SharedArchiveFile=app-dynamic.jsa`.

### Bài 7 — Tại sao `.classlist` có nhiều lớp hơn code bạn viết?

**Đáp án:** JVM cũng load class chuẩn của Java runtime và các thư viện/framework. Class list dựa vào những gì JVM quan sát, không chỉ những class trong package ứng dụng.

### Bài 8 — HTTP server tối ưu request đầu tiên

Training chỉ đi tới “server ready”. Request đầu tiên vẫn chậm vì nạp serializer. Làm gì?

**Đáp án:** Nếu SLA yêu cầu, thêm request đại diện an toàn vào training rồi đo lại. Không nhất thiết ép load toàn bộ class của hệ thống.

### Bài 9 — Archive tạo với JDK khác

Archive được sinh bằng một JDK build nhưng runtime container đã nâng sang build khác. Dùng lại có ổn không?

**Đáp án:** Không được mặc định tương thích. Tạo lại archive bằng runtime/JDK build tương ứng, xác minh bằng log/strict test.

### Bài 10 — Class nằm trong list nhưng không shared

**Đáp án:** Có nhiều khả năng: class không eligible, jar/classpath mismatch, loader/instrumentation, archive runtime bị bỏ qua. Điều tra log CDS/class load và cấu hình build; class list là **ứng viên**, không phải chứng nhận sharing.

### Bài 11 — Archive động nhỏ hơn archive tĩnh

Đo thấy dynamic 262.144 byte và static 10.092.544 byte. Có thể kết luận dynamic luôn nhanh hơn không?

**Đáp án:** Không. Những số đó của một môi trường minh họa; dynamic thường chỉ lưu lớp bổ sung so với base archive. Hiệu năng phải đo trong workload thật.

### Bài 12 — JDK 25 nên dùng gì?

Ứng dụng mới chạy JDK 25, cần tối ưu startup. Có nên mặc định dùng duy nhất quy trình Java 10 không?

**Đáp án:** Không. AppCDS vẫn có thể dùng, nhưng nên đánh giá **AOT cache** của JDK 24/25 (JEP 483, JEP 514), đo kết quả và chọn workflow phù hợp với hệ thống.

### Bài 13 — Có thể bỏ JAR khi đã có archive?

**Đáp án:** Không. Archive không phải một bộ thay thế dependency chuẩn. Giữ artifact và classpath tương thích, vì app có thể còn cần tải nhiều class khác bình thường.

### Bài 14 — Tối ưu hóa trong multi-user service

Có nên thay đổi classpath/CDS archive động khác nhau cho mỗi request người dùng không?

**Đáp án:** Không nên. Archive gắn với tiến trình/runtime và deployment workflow. Chọn profile đại diện cho một deployment, không thay đổi toàn JVM tùy user giữa request.

### Bài 15 — `Class.forName` với mọi tên trong JAR

Bạn viết một vòng quét tất cả class và gọi `Class.forName(className)` khi training. Đây có phải cách tốt nhất?

**Đáp án:** Không. Có thể kích hoạt initialization/side effect, tải cả lớp không cần, làm phình archive và thất bại ở những class cần môi trường khác. Ưu tiên chạy **đường sử dụng thực**.

### Bài 16 — Đo hiệu năng

Tại sao cần đo nhiều lượt, không chỉ chạy `java -Xshare:on` một lần?

**Đáp án:** Startup chịu ảnh hưởng OS file cache, CPU load, JIT, container/filesystem, network và nhiều yếu tố khác. Dùng baseline và số liệu lặp lại với môi trường/cấu hình tương đương để kết luận.

## 17. Checklist triển khai AppCDS hướng vào lớp thực sự dùng

- [ ] Đã xác định mục tiêu startup, first-request hay memory sharing chưa?
- [ ] Training workload có đi qua đường code **thật sự quan trọng** chưa?
- [ ] Có phân biệt class có mặt trong JAR với class load trong run chưa?
- [ ] Có tránh ép tải class không dùng chỉ vì muốn archive đầy hơn không?
- [ ] Nếu dùng static workflow, có tạo `classlist` bằng `DumpLoadedClassList` từ run đại diện không?
- [ ] Classpath ở các bước tạo list/dump/runtime có tương thích, JAR không bị thay đổi không?
- [ ] Có hiểu class list chứa class JDK và framework, không chỉ application class không?
- [ ] Có kiểm tra class thực sự được chia sẻ bằng `-Xlog:class+load=info` không?
- [ ] Có dùng `-Xshare:on` trong test/CI khi cần phát hiện archive không dùng được không?
- [ ] Có chính sách class không được archive vẫn được JVM load từ JAR bình thường không?
- [ ] Nếu dùng dynamic workflow, training có thoát bình thường để ghi archive không?
- [ ] Có kiểm tra JDK build, OS/CPU architecture và runtime image phù hợp không?
- [ ] Có tái tạo archive sau khi JDK/JAR/dependency/container thay đổi không?
- [ ] Có phân tích lớp loaded do reflection, agent, plugin, custom loader khi relevant không?
- [ ] Có tránh dùng `Class.forName` quét và initialize tất cả class không?
- [ ] Có kiểm soát quyền ghi archive và nguồn build đáng tin cậy không?
- [ ] Có benchmark nhiều lượt với/không archive theo cùng workload không?
- [ ] Có đánh giá archive size và hiệu quả startup thay vì tối đa hóa số class không?
- [ ] Có xem xét first-request latency của những lớp chỉ load khi request đến không?
- [ ] Nếu dùng JDK 25+, đã xem xét AOT cache mới và đo so sánh với AppCDS chưa?
- [ ] Có tránh các flag CDS obsolete từ các hướng dẫn rất cũ không?
- [ ] Có giữ tài liệu về kịch bản training và điều kiện tái tạo archive trong pipeline triển khai không?

## 18. Tài liệu chính thức còn hiệu lực

- [JDK 25 `java` launcher — Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing): phân tích vì sao chỉ archive class thực sự dùng, static/dynamic archive, cách tạo và xác minh bằng `class+load`, các ràng buộc classpath.
- [JDK 17 `java` launcher — Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#application-class-data-sharing): quy trình `DumpLoadedClassList`, `SharedClassListFile`, `SharedArchiveFile`, `ArchiveClassesAtExit` áp dụng trên Java 17.
- [JEP 310 — Application Class-Data Sharing (Java 10)](https://openjdk.org/jeps/310): bối cảnh AppCDS mở rộng CDS sang lớp ứng dụng.
- [JEP 350 — Dynamic CDS Archives (Java 13)](https://openjdk.org/jeps/350): tạo dynamic CDS archive khi ứng dụng thoát.
- [JEP 483 — Ahead-of-Time Class Loading & Linking (JDK 24)](https://openjdk.org/jeps/483): bước phát triển cho AOT class loading/linking.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics (JDK 25)](https://openjdk.org/jeps/514): workflow `-XX:AOTCacheOutput` và `-XX:AOTCache`.
- [JEP 515 — Ahead-of-Time Method Profiling (JDK 25)](https://openjdk.org/jeps/515): tối ưu hóa warmup bổ sung trên JDK mới.
- [JDK 25 `java` launcher — Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#ahead-of-time-cache): cú pháp lệnh mới, điều kiện tương thích và vòng đời cache.
- [JDK 25 `java` launcher — Restrictions on Class Path and Module Path](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#restrictions-on-class-path-and-module-path): giới hạn JAR/classpath/module path khi dùng CDS archive.

**Kết luận:** Để chọn các lớp **thực sự được ứng dụng sử dụng**, hãy chạy một **training workload đại diện**, thu thập lớp đã load hoặc tạo dynamic archive, rồi xác minh lớp quan trọng đang được nạp từ shared archive trong runtime thật. Không đưa mọi class của các JAR vào archive chỉ vì chúng tồn tại. Class không được archive vẫn có thể load từ JAR bình thường; tối ưu hóa phải được đo theo startup, first-request và footprint. Trên JDK 25+, nên đánh giá thêm AOT cache hiện đại, nhưng nguyên tắc chọn theo workload thực tế vẫn là trọng tâm.