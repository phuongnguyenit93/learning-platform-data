# Cấu trúc header đối tượng và tác động đến kích thước đối tượng trong heap

## 1. Vì sao header của đối tượng ảnh hưởng đến bộ nhớ?

Mỗi đối tượng Java được HotSpot cấp phát trong heap đều cần một vùng metadata để JVM nhận biết lớp của đối tượng, quản lý trạng thái đồng bộ và hỗ trợ garbage collector. Vùng này được gọi là **object header**. Header tồn tại ngay cả khi đối tượng không có field nghiệp vụ nào.

Với ứng dụng tạo hàng triệu hoặc hàng trăm triệu đối tượng nhỏ, vài byte header trên mỗi đối tượng có thể cộng lại thành một phần đáng kể của heap. Ví dụ, một đồ thị object gồm node, wrapper, collection entry và DTO thường có rất nhiều đối tượng nhỏ; chi phí header và padding có thể lớn so với dữ liệu nghiệp vụ thực tế.

**Compact Object Headers (JEP 519)** trở thành tính năng chính thức trong **Java 25**. Trên HotSpot 64-bit, cơ chế này giảm object header từ **96 hoặc 128 bit xuống 64 bit** bằng cách mã hóa thông tin lớp trong compact header. Oracle ghi nhận mức giảm trung bình khoảng **4 byte cho mỗi đối tượng**; mức tiết kiệm thực tế phụ thuộc số lượng object, field, alignment và kiểu workload.

Bài **Cấu trúc header đối tượng và tác động đến kích thước đối tượng trong heap**, thuộc chương **Header đối tượng gọn** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào:

1. Các thành phần trong object header của HotSpot.
2. Cách compact header kết hợp thông tin mark và class pointer.
3. Vì sao giảm header có thể làm giảm heap footprint và áp lực GC.
4. Phân biệt header, field, array length, compressed references và padding.
5. Bật và xác minh tính năng trên JDK 25.
6. Đo object layout bằng JOL và so sánh workload có/không có compact header.
7. Nhận diện giới hạn số class và tác động khi nâng cấp JDK.

**Phạm vi:** đây là chi tiết triển khai của **HotSpot JVM 64-bit**, không phải một bảo đảm về object layout của Java Language Specification. JVM vendor, kiến trúc và phiên bản khác có thể tổ chức đối tượng khác nhau.

## 2. Trạng thái tính năng theo phiên bản JDK

Compact Object Headers đã trải qua các mốc sau:

| Phiên bản | Trạng thái | Điều cần nhớ |
| --- | --- | --- |
| **JDK 24 – JEP 450** | Experimental | Có thể thử nghiệm bằng cờ mở tính năng experimental và cờ compact header. |
| **JDK 25 – JEP 519** | Product feature, không còn experimental | Có thể bật bằng **-XX:+UseCompactObjectHeaders**; mặc định vẫn tắt trong JDK 25. |
| **JDK 26** | Tiếp tục hỗ trợ | Vẫn có thể chủ động bật theo cấu hình runtime. |
| **JDK 27 – JEP 534** | Enabled by default trong HotSpot | Compact headers được bật mặc định; có thể tắt tạm thời bằng **-XX:-UseCompactObjectHeaders** để A/B test hoặc xử lý regression. |

Đối với ứng dụng chạy đúng **JDK 25**, dùng:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Không cần thêm **-XX:+UnlockExperimentalVMOptions** khi dùng JDK 25. Cờ mở experimental chỉ thuộc giai đoạn JDK 24; tiếp tục sao chép lệnh cũ vào hướng dẫn Java 25 là không cần thiết.

Nếu ứng dụng đang chạy JDK 27, compact headers đã được bật mặc định. Khi kiểm tra tác động so với layout cũ, có thể chạy một tiến trình đối chứng bằng:

~~~bash
java -XX:-UseCompactObjectHeaders -jar app.jar
~~~

Điểm khác nhau giữa JDK 25 và JDK 27 rất quan trọng khi đọc cấu hình triển khai: **tính năng đã final trong Java 25 không đồng nghĩa nó được bật mặc định trong Java 25**.

## 3. Object header truyền thống gồm những gì?

Trong HotSpot 64-bit, object header truyền thống có hai thành phần chính:

1. **Mark word:** vùng thông tin đa mục đích. Tùy trạng thái, nó hỗ trợ trạng thái lock/monitor, identity hash code, tuổi đối tượng và thông tin nội bộ phục vụ GC.
2. **Class pointer (Klass pointer):** tham chiếu tới metadata mô tả lớp thực tế của đối tượng. Metadata này nằm ngoài heap Java, trong vùng quản lý class metadata của HotSpot.

Khi dùng compressed class pointers, class pointer được biểu diễn bằng 32 bit; mark word vẫn là 64 bit. Vì vậy header truyền thống thường là **96 bit (12 byte)**. Nếu class pointer không được nén, header có thể là **128 bit (16 byte)**.

~~~text
HotSpot 64-bit, compressed class pointers:

+-------------------------------+
| Mark word                 64b |
+-------------------------------+
| Compressed class pointer  32b |
+-------------------------------+
| Tổng header               96b |
+-------------------------------+

HotSpot 64-bit, full class pointer:

+-------------------------------+
| Mark word                 64b |
+-------------------------------+
| Class pointer             64b |
+-------------------------------+
| Tổng header              128b |
+-------------------------------+
~~~

Đây là sơ đồ khái niệm để giải thích kích thước. Vị trí field, padding và phần mở rộng dành riêng cho array cần xét thêm theo loại đối tượng và cấu hình VM.

### Mark word không chỉ là lock flag

Tên **mark word** đôi khi khiến người mới nghĩ đây chỉ là một bit đánh dấu GC. Thực tế, HotSpot sử dụng vùng này cho nhiều mục đích nội bộ. Cách diễn giải các bit thay đổi theo trạng thái đối tượng, chẳng hạn chưa lock, đang lock, đã có identity hash hoặc đang ở trạng thái liên quan đến GC.

Ứng dụng không được đọc hoặc tự giải mã mark word. Những chi tiết này thuộc implementation của JVM và có thể thay đổi giữa các phiên bản.

## 4. Compact Object Header thay đổi cấu trúc như thế nào?

Compact Object Headers giảm header xuống **một word 64 bit** trên HotSpot 64-bit. Thông tin class pointer được mã hóa trong compact header cùng các thông tin mark cần thiết, thay vì chiếm thêm một word riêng bên cạnh mark word.

~~~text
Header truyền thống, compressed class pointer:

+-------------------------------+
| Mark word                 64b |
+-------------------------------+
| Compressed class pointer  32b |
+-------------------------------+
| Tổng                      96b |
+-------------------------------+

Compact Object Header:

+-------------------------------+
| Compact header             64b |
| - encoded class information  |
| - mark / lock / GC metadata  |
+-------------------------------+
| Tổng                      64b |
+-------------------------------+
~~~

Vì vậy, phần header giảm:

| Layout trước compact header | Compact header | Chênh lệch phần header |
| ---: | ---: | ---: |
| 96 bit (12 byte) | 64 bit (8 byte) | 32 bit (4 byte) |
| 128 bit (16 byte) | 64 bit (8 byte) | 64 bit (8 byte) |

Với cấu hình HotSpot thông dụng dùng compressed class pointers, mức giảm raw header là **4 byte**. Oracle mô tả mức giảm footprint trung bình khoảng 4 byte/object trong Java 25. Không nên lấy mức chênh lệch raw header rồi kết luận mọi đối tượng thực tế đều giảm đúng cùng số byte; padding và cấu trúc field có thể làm kết quả cuối khác nhau.

## 5. Vì sao JVM có thể gộp class pointer vào header?

JVM cần nhận diện lớp của một object để thực hiện kiểm tra kiểu, gọi method ảo, truy cập metadata và nhiều thao tác runtime khác. Compact Object Headers sử dụng cách biểu diễn class pointer được nén và đặt trong compact header.

Oracle ghi nhận giới hạn **4 triệu class khác nhau được load** khi compact headers được bật. Giới hạn này là một đánh đổi của cách mã hóa class information trong header nhỏ gọn.

~~~mermaid
flowchart TD
    A["Object reference"] --> B["Compact 64-bit header"]
    B --> C["Decode class information"]
    C --> D["HotSpot class metadata"]
    B --> E["Mark / lock / GC state"]
    D --> F["Type check và method dispatch"]
    E --> G["Locking, identity hash và GC"]
~~~

Giới hạn 4 triệu class thường rất cao với ứng dụng nghiệp vụ thông thường. Tuy vậy, cần xem xét kỹ nếu hệ thống:

- Tạo class động liên tục bằng bytecode generation.
- Chạy nhiều plugin hoặc nhiều class loader trong cùng JVM.
- Là application server chứa nhiều ứng dụng độc lập.
- Tạo proxy hoặc class runtime theo tenant/request.
- Có kiến trúc hot-deploy khiến class loader và số class tăng theo thời gian.

Nếu ứng dụng dự kiến vượt giới hạn này, compact headers không phù hợp với runtime đó. Hãy xác minh số lượng class được load trong môi trường thực tế trước khi bật.

## 6. Header, field, array length và padding là các phần khác nhau

Kích thước một object trong heap không chỉ bằng kích thước header. Có thể hình dung:

~~~text
Object size
    = object header
    + instance fields
    + alignment padding
~~~

Đối với array, còn có trường lưu **array length** và các yếu tố căn chỉnh phần tử:

~~~text
Array layout (khái niệm):

+-------------------------------+
| Object header                 |
+-------------------------------+
| Array length                  |
+-------------------------------+
| Padding nếu cần alignment     |
+-------------------------------+
| Element 0                     |
+-------------------------------+
| Element 1                     |
+-------------------------------+
| ...                           |
+-------------------------------+
~~~

Vì vậy, compact header không loại bỏ array length, không nén các field nghiệp vụ và không tự thay đổi kiểu dữ liệu của ứng dụng.

### Phân biệt compressed class pointers và compressed oops

Hai cơ chế thường bị nhầm:

| Cơ chế | Nén cái gì? | Vai trò |
| --- | --- | --- |
| **Compressed class pointers** | Tham chiếu tới class metadata của HotSpot. | Giảm phần class pointer trong header truyền thống. |
| **Compressed ordinary object pointers (compressed oops)** | Tham chiếu object Java được lưu trong field hoặc array. | Giảm kích thước các reference trong heap. |
| **Compact Object Headers** | Gộp thông tin class vào compact header 64 bit. | Giảm phần header của object. |

Compact headers không có nghĩa mọi reference trong ứng dụng đều chuyển sang 32 bit hoặc mọi object field đều nhỏ hơn. Hãy giữ các khái niệm này tách biệt khi đọc heap layout.

## 7. Alignment quyết định kích thước object cuối cùng

HotSpot căn chỉnh object theo cấu hình alignment. Trên cấu hình 64-bit thông dụng, object thường được căn chỉnh theo bội số **8 byte**, nhưng có thể thay đổi qua tùy chọn JVM như **-XX:ObjectAlignmentInBytes**.

Ví dụ minh họa:

~~~text
Một object có:
  Header          12 byte
  Field dữ liệu    4 byte
  ----------------------
  Raw size        16 byte

Nếu header còn 8 byte:
  Header           8 byte
  Field dữ liệu    4 byte
  ----------------------
  Raw size        12 byte
  Alignment       4 byte
  Allocated size  16 byte
~~~

Trong ví dụ này, raw layout nhỏ hơn nhưng kích thước cấp phát cuối cùng không đổi vì alignment. Với object khác, phần giảm header có thể làm object vượt xuống một bậc alignment nhỏ hơn và tiết kiệm nhiều hơn 4 byte; hoặc có thể bị padding hấp thụ.

Đây là lý do cần đo **instance size thực tế**, không chỉ lấy số bit header để ước tính heap của ứng dụng.

## 8. Tác động đến heap footprint và garbage collection

Khi mỗi object nhỏ hơn, cùng một lượng dữ liệu nghiệp vụ có thể nằm trong ít byte heap hơn. Những tác động có thể quan sát gồm:

- **Giảm live heap size:** tập object còn sống chiếm ít bộ nhớ hơn.
- **Tăng mật độ object:** nhiều object hơn có thể nằm trong cùng một vùng cache/memory page.
- **Giảm dữ liệu GC phải scan/copy:** một số workload có thể giảm công việc di chuyển hoặc quét object.
- **Giảm áp lực heap:** có thể giảm tần suất collection hoặc cho phép chạy nhiều instance hơn trên cùng tài nguyên.
- **Cải thiện locality:** các object nhỏ có thể được đặt gần nhau hơn, giảm cache miss trong một số đường truy cập.

Tuy nhiên, compact headers không thay đổi số lượng object mà ứng dụng tạo ra. Nếu ứng dụng giữ quá nhiều object, tạo vòng tham chiếu giữ bộ nhớ hoặc cache không có giới hạn, compact header không giải quyết nguyên nhân gốc của memory leak.

### Ước lượng sơ bộ

Nếu dùng mức tiết kiệm trung bình khoảng **4 byte/object** để ước tính:

| Số object sống | Mức giảm lý thuyết gần đúng |
| ---: | ---: |
| 10 triệu | 40 MB |
| 50 triệu | 200 MB |
| 100 triệu | 400 MB |

Đây là phép nhân sơ bộ theo mức trung bình do tài liệu Oracle nêu, không phải cam kết mức giảm heap của mọi ứng dụng. Kết quả thực tế phụ thuộc object distribution, array, field layout, alignment, GC và trạng thái heap.

## 9. Workload nào có thể hưởng lợi nhiều hơn?

Mức lợi ích thường lớn hơn khi ứng dụng có nhiều object nhỏ và thời gian sống đủ dài để chúng chiếm một phần đáng kể của live heap.

| Kiểu workload | Khả năng hưởng lợi | Lý do |
| --- | --- | --- |
| Đồ thị object nhiều node nhỏ | Cao hơn | Header chiếm tỷ lệ đáng kể so với field dữ liệu. |
| Collection chứa nhiều entry/wrapper | Cao hơn | Số lượng object lớn, mỗi object tiết kiệm một phần header. |
| Cache in-memory nhiều DTO nhỏ | Có thể cao | Nhiều object sống đồng thời trong heap. |
| Parser tạo nhiều object trung gian | Tùy thời gian sống | Có thể giảm footprint và lượng dữ liệu GC phải xử lý. |
| Ứng dụng chủ yếu dùng mảng primitive lớn | Thường thấp hơn | Phần dữ liệu array lớn hơn nhiều so với header. |
| Ứng dụng chỉ có ít object lớn | Thường thấp hơn | Số header nhỏ nên tổng tiết kiệm hạn chế. |

Không thể kết luận compact headers luôn tăng throughput. Một số workload có thể thấy cải thiện rõ về footprint hoặc GC, trong khi workload khác chỉ thay đổi rất ít. Phải đo trên ứng dụng thật với dữ liệu và cấu hình gần production.

## 10. Bật và xác minh compact headers trên JDK 25

### 10.1. Bật khi khởi chạy

JDK 25 đã coi đây là product feature. Bật bằng:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Chạy đối chứng với layout truyền thống:

~~~bash
java -XX:-UseCompactObjectHeaders -jar app.jar
~~~

Hai tiến trình phải chạy riêng vì layout được chọn lúc JVM khởi tạo. Không thể bật/tắt compact headers giữa chừng bằng một API Java trong cùng tiến trình.

### 10.2. Xem giá trị cờ JVM

~~~bash
java -XX:+UseCompactObjectHeaders -XX:+PrintFlagsFinal -version
~~~

Tìm dòng **UseCompactObjectHeaders** trong output để xác nhận giá trị và loại cờ. Trên Windows PowerShell có thể lọc:

~~~powershell
java -XX:+PrintFlagsFinal -version | Select-String UseCompactObjectHeaders
~~~

Trên Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version | grep UseCompactObjectHeaders
~~~

Đối với JVM đang chạy, có thể kiểm tra cờ qua:

~~~bash
jcmd <pid> VM.flags
~~~

Thay **<pid>** bằng process ID của ứng dụng. Hãy xác minh đúng executable và JDK vendor; không suy ra trạng thái chỉ từ file cấu hình deploy.

### 10.3. Chú ý khi chạy trên JDK 27

JDK 27 bật compact headers mặc định theo **JEP 534**. Vì vậy:

- Trên JDK 25: dùng **-XX:+UseCompactObjectHeaders** để bật; mặc định là tắt.
- Trên JDK 27: mặc định đã bật; chỉ cần **-XX:-UseCompactObjectHeaders** khi cần đối chứng hoặc fallback.

Nếu một tài liệu Java 25 hướng dẫn luôn phải thêm cờ bật, hãy hiểu đó là hướng dẫn cho runtime Java 25; không áp dụng nguyên xi cho runtime JDK 27.

## 11. Đo object layout bằng Java Object Layout (JOL)

**Java Object Layout (JOL)** là công cụ của OpenJDK Code Tools dùng để quan sát layout object trong JVM đang chạy. JOL không phải API Java SE và không được tích hợp sẵn trong JDK; thêm thư viện **jol-core** vào project kiểm thử hoặc chạy công cụ riêng.

Ví dụ:

~~~java
import org.openjdk.jol.info.ClassLayout;
import org.openjdk.jol.vm.VM;

public final class ObjectLayoutDemo {

    static final class Node {
        int id;
        Object next;
        long value;
    }

    public static void main(String[] args) {
        System.out.println(VM.current().details());

        Node node = new Node();
        System.out.println(
                ClassLayout.parseInstance(node).toPrintable());
    }
}
~~~

Chạy chương trình trong hai JVM riêng:

~~~bash
# Layout truyền thống trên JDK 25
java -XX:-UseCompactObjectHeaders -cp "app.jar;jol-core.jar" ObjectLayoutDemo

# Compact header trên JDK 25
java -XX:+UseCompactObjectHeaders -cp "app.jar;jol-core.jar" ObjectLayoutDemo
~~~

Trên Linux/macOS, dấu phân tách classpath là dấu hai chấm:

~~~bash
java -XX:+UseCompactObjectHeaders -cp "app.jar:jol-core.jar" ObjectLayoutDemo
~~~

Quan sát phần **object header**, offset của field và **instance size**. Kết quả chính xác phụ thuộc JDK build, architecture, object alignment và compressed references.

### Đo cả object graph

Khi cần ước lượng footprint của một đồ thị object:

~~~java
import org.openjdk.jol.info.GraphLayout;

Object root = buildSampleGraph();
System.out.println(GraphLayout.parseInstance(root).toFootprint());
System.out.println(
        "Graph size = " + GraphLayout.parseInstance(root).totalSize());
~~~

GraphLayout đi theo các reference có thể quan sát để tính footprint của object graph. Nó không bao gồm toàn bộ chi phí ngoài heap như metaspace, code cache, thread stack hoặc native allocation; cũng không thay thế heap dump của một ứng dụng production.

**Lưu ý:** JOL có thể cần quyền truy cập nội bộ hoặc phát cảnh báo tùy JDK. Dùng JOL trong môi trường kiểm thử, cập nhật phiên bản công cụ phù hợp với JDK và không dùng kết quả từ một phiên bản JVM để khẳng định layout của JVM vendor khác.

## 12. Đo tác động trên ứng dụng thật

Một phép đo có ý nghĩa cần tách hai câu hỏi:

1. **Mỗi object nhỏ hơn bao nhiêu?** Dùng JOL để quan sát layout của các class tiêu biểu.
2. **Ứng dụng tiết kiệm được bao nhiêu?** Dùng cùng workload và đo heap footprint, GC, throughput, latency và CPU.

### Ma trận A/B tối thiểu

| Biến thể | JVM option | Mục tiêu |
| --- | --- | --- |
| A – Baseline | **-XX:-UseCompactObjectHeaders** | Layout truyền thống. |
| B – Compact | **-XX:+UseCompactObjectHeaders** | Đánh giá compact headers. |

Giữ nhất quán:

- Cùng JDK vendor, phiên bản và patch build.
- Cùng OS, CPU và giới hạn container.
- Cùng heap size, GC, object alignment và các JVM option khác.
- Cùng artifact, dependency và cấu hình ứng dụng.
- Cùng dữ liệu đầu vào, số request và phân bố workload.
- Chạy từng biến thể trong process mới; không tái sử dụng JVM đã warm-up.

### Chỉ số nên ghi

| Chỉ số | Công cụ/nguồn | Ý nghĩa |
| --- | --- | --- |
| Shallow size của class tiêu biểu | JOL ClassLayout | Xác nhận header và instance size. |
| Footprint của object graph mẫu | JOL GraphLayout | Ước lượng mức tiết kiệm trên một cấu trúc dữ liệu cụ thể. |
| Heap used/committed | JMX, jcmd hoặc JFR | So sánh bộ nhớ heap trong cùng trạng thái workload. |
| Số object và byte theo class | Heap histogram/heap dump | Xác định class nào chiếm nhiều footprint. |
| GC count và pause | GC log hoặc JFR | Xem tác động lên collection. |
| Throughput và latency p95/p99 | Load test/metrics | Kiểm tra hiệu năng ứng dụng. |
| CPU và process RSS | Công cụ hệ điều hành | Kiểm tra tác động ngoài heap và chi phí tổng thể. |

### Ví dụ quy trình kiểm thử

1. Tạo một bộ dữ liệu cố định với số lượng object và phân bố field gần production.
2. Khởi động JVM A với compact headers tắt; đợi workload đạt trạng thái ổn định.
3. Ghi heap histogram, heap usage, GC count/pause và throughput/latency.
4. Dừng JVM A; khởi động JVM B với compact headers bật và cùng cấu hình.
5. Chạy lại chính xác workload và thời lượng đo.
6. Lặp lại vài lần, đổi thứ tự A/B để giảm ảnh hưởng môi trường.
7. So sánh cả object size, heap footprint và chỉ số ứng dụng.

Không kết luận chỉ từ **RSS** hoặc chỉ từ một lần GC. RSS còn bao gồm native memory, thread stack, metaspace và các vùng khác; heap usage lại không phản ánh toàn bộ process memory. Hai nhóm chỉ số cần được đọc cùng nhau.

## 13. Giới hạn, tương thích và các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| JVM báo không nhận diện cờ | Runtime quá cũ hoặc JVM vendor không hỗ trợ cờ HotSpot. | Kiểm tra **java -version**, **java -XX:+PrintFlagsFinal -version** và tài liệu vendor. |
| JDK 25 không bật compact headers dù đã cài JDK mới | Cờ mặc định của Java 25 là tắt. | Khởi chạy với **-XX:+UseCompactObjectHeaders**. |
| JDK 27 có compact headers dù không đặt cờ | Đây là mặc định theo JEP 534. | Kiểm tra **VM.flags**; dùng **-XX:-UseCompactObjectHeaders** để đối chứng. |
| Không thể dùng compact headers do quá nhiều class | Ứng dụng vượt giới hạn khoảng 4 triệu class được load. | Theo dõi class loading/class count và xem lại kiến trúc class loader. |
| JOL báo layout khác dự kiến | JDK, alignment, compressed references hoặc VM khác nhau. | In **VM.current().details()** và so sánh cùng môi trường. |
| Heap giảm ít hơn dự đoán | Nhiều object lớn/array, padding hấp thụ phần tiết kiệm hoặc số object sống thấp. | Phân tích class histogram và object size thực tế. |
| Heap giảm nhưng RSS gần như không đổi | Process memory còn có metaspace, native memory, code cache và stack. | Đo heap và native/process memory riêng. |
| Throughput thay đổi theo hướng xấu | Workload nhạy với layout, lock, GC hoặc kiến trúc cụ thể. | Benchmark lặp lại và đối chiếu JFR/GC log; thử tắt cờ để xác nhận. |
| Agent hoặc công cụ native không hoạt động | Tool giả định layout HotSpot cũ hoặc dùng chi tiết nội bộ. | Cập nhật agent/tool; kiểm thử với compact headers bật. |

### Giới hạn quan trọng: số class được load

Oracle Java 25 nêu giới hạn **4 triệu class khác nhau được load** khi dùng compact headers. Đây là điều kiện cần kiểm tra với ứng dụng có class generation hoặc class loader phức tạp. Đừng nhầm số lượng class trong source repository với số class runtime thực sự load.

### Không dựa vào object header như API

Java không định nghĩa offset header, kích thước header hay thứ tự field của mọi JVM. Không nên:

- Đọc mark word bằng Unsafe hoặc JNI như một hợp đồng ổn định.
- Giả định field đầu tiên luôn nằm ở một offset cố định.
- Viết agent phụ thuộc layout nội bộ mà không kiểm tra từng JDK.
- Dùng kích thước object đo trên HotSpot để suy ra kích thước trên GraalVM Native Image hoặc JVM khác.

Các API Java như **synchronized**, **System.identityHashCode(...)**, **Object.getClass()** và semantics của reference vẫn hoạt động theo hợp đồng Java. JVM tự quản lý việc biểu diễn lock state, identity hash và class metadata.

## 14. Tác động khi nâng cấp JDK và triển khai production

Khi chuyển từ Java 24 lên Java 25, thay đổi quan trọng là compact headers chuyển từ experimental thành product feature. Ứng dụng cần kiểm tra lại:

- Cờ **-XX:+UseCompactObjectHeaders** có được bật có chủ đích hay không.
- Startup scripts, container entrypoint và JVM options trong deployment.
- Số class được load, đặc biệt với plugin/proxy/dynamic class generation.
- JOL/agent/native tooling có tương thích layout mới không.
- Heap footprint, GC và latency dưới workload đại diện.

Khi chuyển tiếp từ Java 25 lên Java 27, cần chú ý compact headers trở thành mặc định. Nếu trước đó ứng dụng chạy JDK 25 mà không bật cờ, sau nâng cấp JDK 27 layout có thể thay đổi dù startup command không đổi. Đây là lý do nên kiểm tra hiệu năng và tương thích low-level tooling trong mỗi lần nâng JDK.

### Chiến lược rollout

1. **Local/staging:** bật compact headers, chạy test chức năng và đo JOL.
2. **Performance test:** so sánh A/B cùng JDK build, GC, heap và workload.
3. **Canary:** triển khai một phần traffic, theo dõi heap, GC, CPU, latency và lỗi.
4. **Mở rộng:** tăng dần tỷ lệ nếu số liệu ổn định.
5. **Fallback:** giữ cách tắt cờ cho JDK 25/26; với JDK 27 có thể dùng **-XX:-UseCompactObjectHeaders** để quay về layout cũ trong lúc điều tra.

Không cần sửa source code thông thường chỉ để dùng compact headers. Công việc chính nằm ở cấu hình JVM, xác minh môi trường và đo hiệu năng.

## 15. Bài tập thực hành

### Bài A — Vẽ layout của một object

Tạo class có một int, một long và một reference. Dùng JOL để in layout khi compact headers tắt và bật trên JDK 25. Ghi header size, field offset, instance size và padding.

**Đạt:** giải thích được phần header giảm nhưng kích thước cuối cùng còn phụ thuộc field và alignment.

### Bài B — So sánh object nhỏ và array

Tạo một object nhỏ, một object có nhiều field và các array byte/int/reference. Dùng JOL đo layout. So sánh phần tiết kiệm tương đối giữa từng loại.

**Đạt:** không nhầm array length với object header và không giả định mọi object tiết kiệm đúng 4 byte.

### Bài C — Ước lượng heap footprint

Tạo một object graph gồm nhiều node nhỏ. Dùng GraphLayout đo footprint với hai chế độ. Tính mức chênh lệch và so với ước lượng 4 byte/object.

**Đạt:** ghi rõ GraphLayout chỉ đo object graph được duyệt, không bao gồm native memory và metaspace.

### Bài D — Kiểm tra class loading

Quan sát số class được load trong ứng dụng có proxy hoặc plugin. Đánh giá mức độ an toàn so với giới hạn 4 triệu class của compact headers.

**Đạt:** phân biệt class trong source với class runtime đã được load.

### Bài E — Benchmark ứng dụng

Chạy cùng một workload ở hai JVM riêng: compact headers tắt và bật. Thu heap, GC, CPU, throughput và latency p95/p99. Lặp lại vài lần.

**Đạt:** kết luận dựa trên nhiều chỉ số và cùng điều kiện đo, không suy ra hiệu năng từ kích thước một object.

### Bài F — Kiểm tra khi nâng cấp

Chạy ứng dụng bằng JDK 25 không đặt cờ, JDK 25 bật cờ và JDK 27 mặc định. Xác minh giá trị flag trong mỗi tiến trình, ghi lại khác biệt startup command và kết quả layout.

**Đạt:** giải thích được JEP 519 trong Java 25 và JEP 534 trong JDK 27.

## 16. Câu hỏi tự kiểm tra

1. Object header của HotSpot dùng để quản lý những thông tin nào?
2. Vì sao header truyền thống trên HotSpot 64-bit có thể là 96 hoặc 128 bit?
3. Compact Object Headers đưa header về kích thước nào?
4. Compact header mã hóa class information ở đâu?
5. Vì sao mức giảm raw header không luôn bằng mức giảm kích thước cấp phát thực tế?
6. Array length có bị loại bỏ khi bật compact headers không?
7. Compressed oops khác compressed class pointers như thế nào?
8. Giới hạn 4 triệu class có ý nghĩa gì với hệ thống plugin hoặc class generation?
9. Cờ bật compact headers trên JDK 25 là gì? Có cần UnlockExperimentalVMOptions không?
10. Vì sao JDK 27 có thể dùng compact headers dù startup command không có cờ bật?
11. Khi nào object graph nhiều node nhỏ có thể hưởng lợi rõ hơn một ứng dụng chủ yếu dùng primitive array?
12. Vì sao cần kết hợp JOL, heap histogram, GC log và benchmark ứng dụng?
13. Compact headers có thay đổi semantics của synchronized hoặc identity hash code không?
14. Vì sao không nên viết code phụ thuộc offset header nội bộ của HotSpot?

## 17. Tài liệu tham khảo chính thức

- [JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519): tính năng product trong Java 25 và mục tiêu giảm header.
- [JEP 450 — Compact Object Headers (Experimental)](https://openjdk.org/jeps/450): lịch sử giai đoạn thử nghiệm trong JDK 24; chỉ dùng để hiểu quá trình phát triển.
- [Oracle Java 25 — Compact Object Headers](https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html): kích thước header 96/128 bit xuống 64 bit, cờ bật và giới hạn 4 triệu class.
- [The java Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): trạng thái mặc định và tùy chọn **-XX:+UseCompactObjectHeaders**.
- [Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận JEP 519 là product feature trong Java 25.
- [JEP 534 — Compact Object Headers by Default](https://openjdk.org/jeps/534): thay đổi mặc định ở JDK 27.
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): xác nhận compact headers được bật mặc định trong JDK 27.
- [Performance Improvements in JDK 27 — Inside Java](https://inside.java/2026/09/28/performance-update-jdk27/): số liệu đo và lưu ý lợi ích phụ thuộc object distribution, alignment và workload.
- [Java Object Layout (JOL)](https://github.com/openjdk/jol): công cụ quan sát object layout và footprint trên JVM thực tế.

**Ghi chú tính hiện hành:** JEP 519 là tính năng Java 25 đã hoàn thiện, không còn experimental. Trên JDK 25, compact headers vẫn mặc định tắt và được bật bằng **-XX:+UseCompactObjectHeaders**; trên JDK 27, chúng mặc định bật theo JEP 534. Luôn đo layout và hiệu năng trên đúng JDK vendor, architecture và workload triển khai.

**Kết quả cần nộp:** sơ đồ object header truyền thống và compact header, output JOL của ít nhất hai class, bảng so sánh heap footprint ở hai chế độ, số class runtime được load, kết quả benchmark và ghi chú tương thích khi nâng cấp JDK. Kết quả cần chứng minh bạn hiểu mối liên hệ giữa header, field, alignment và kích thước object thực tế trong heap.
