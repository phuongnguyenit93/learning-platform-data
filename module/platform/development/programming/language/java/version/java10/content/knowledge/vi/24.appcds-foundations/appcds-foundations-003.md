# Kho dữ liệu lớp được ánh xạ vào bộ nhớ: cơ chế AppCDS trong Java 10 và JDK hiện đại

## 1. Bài học giải quyết vấn đề gì?

Khi một chương trình Java khởi động, JVM cần tìm và nạp nhiều lớp: lớp trong JDK, lớp thư viện và lớp của ứng dụng. Việc đọc JAR, phân tích bytecode và tạo những cấu trúc dữ liệu nội bộ cho lớp có thể làm tăng thời gian khởi động. Nếu cùng một ứng dụng chạy ở nhiều tiến trình JVM, một phần dữ liệu mô tả các lớp ấy thường có tính chất giống nhau.

**Class Data Sharing (CDS)** và **Application Class-Data Sharing (AppCDS)** cho phép HotSpot lưu trước **một phần dữ liệu lớp đã được xử lý** vào một **archive file**. Khi khởi động, JVM có thể **memory-map** các vùng phù hợp của archive vào không gian địa chỉ ảo của tiến trình. Những trang ánh xạ **chỉ đọc và có thể chia sẻ** có cơ hội dùng chung trang vật lý giữa nhiều JVM trên cùng máy, thay vì mỗi tiến trình phải tạo một bản metadata riêng.

**AppCDS** mở rộng CDS để lưu các lớp liên quan **ứng dụng** chứ không chỉ các lớp lõi JDK. Nó được giới thiệu trong **Java 10 qua JEP 310**. Cơ chế này vẫn có giá trị, đồng thời đã được mở rộng bởi **AOT cache** trên JDK hiện đại.

Nội dung trọng tâm: **“Kho dữ liệu lớp được ánh xạ vào bộ nhớ”** thuộc chủ đề **“Nền tảng AppCDS”**. Chúng ta giải thích đúng ba tầng:

1. **Đĩa:** archive chứa dữ liệu lớp đã chuẩn bị để tái sử dụng.
2. **Bộ nhớ ảo của từng JVM:** hệ điều hành ánh xạ các vùng archive vào address space của tiến trình.
3. **Bộ nhớ vật lý:** những trang file-backed phù hợp, thường là read-only, có thể được chia sẻ giữa các tiến trình.

Đây là tối ưu hóa triển khai của **HotSpot JVM**, không phải một đặc tính của ngôn ngữ Java bắt buộc mọi JVM trên mọi nền tảng phải hỗ trợ với cùng tùy chọn.

### Mục tiêu sau bài học

- Phân biệt CDS, AppCDS, archive mặc định, archive ứng dụng và AOT cache.
- Hiểu **memory-mapped class metadata** khác với heap object, JAR gốc và bytecode.
- Giải thích vì sao mapping có thể giảm startup và memory footprint, nhưng **không cam kết** mọi trang được chia sẻ hay mọi ứng dụng đều nhanh hơn.
- Thực hành bằng `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile` và các log `-Xlog:cds`, `-Xlog:class+load`.
- Hiểu classpath/JAR/JDK build, khả năng tương thích archive và lý do cần tạo lại sau khi thay đổi môi trường.
- Phân biệt `-Xshare:auto`, `-Xshare:on` và `-Xshare:off`.
- Biết trên JDK 24+ có AOT cache, và trên JDK 25+ quy trình tạo AOT cache được đơn giản hóa; không coi thao tác AppCDS đời đầu là lựa chọn duy nhất.
- Đo đạc, kiểm chứng và triển khai an toàn, đặc biệt với container và nhiều JVM.

## 2. CDS khác AppCDS như thế nào?

**CDS (Class Data Sharing)** là cơ chế chia sẻ dữ liệu lớp mà các JVM có thể tái sử dụng. Một số lớp dùng phổ biến có thể được đưa vào **archive mặc định đi kèm JDK**. Với các bản phân phối HotSpot hiện đại, CDS thường đã được bật sẵn ở chế độ tự động.

**AppCDS (Application Class-Data Sharing)** mở rộng khả năng tạo và sử dụng archive sang **lớp ứng dụng và thư viện**, trong phạm vi những lớp và class loaders được hỗ trợ.

| Khái niệm | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| **CDS** | Archive và dùng lại metadata của các lớp được hỗ trợ, đặc biệt lớp lõi JDK. | Có thể dùng archive mặc định mà không cần tự tạo. |
| **AppCDS** | Bao gồm thêm lớp ứng dụng và thư viện đủ điều kiện. | JEP 310, Java 10; không phải một ngôn ngữ lập trình mới. |
| **Static/base archive** | Archive nền, có thể là archive do JDK cung cấp hoặc tạo riêng. | Dùng làm cơ sở cho dữ liệu chia sẻ. |
| **Dynamic/top archive** | Archive bổ sung lớp được ghi nhận lúc chương trình chạy. | Thường tạo bằng `-XX:ArchiveClassesAtExit`. |
| **Memory mapping** | Ánh xạ vùng archive file thành vùng địa chỉ ảo của tiến trình JVM. | Cho phép dùng trang file-backed và chia sẻ read-only pages. |
| **AOT cache** | Container tối ưu hóa ahead-of-time mới hơn, xây trên những ý tưởng của CDS. | JDK 24+; có thể chứa thêm sản phẩm tối ưu hóa ngoài metadata CDS truyền thống. |

**Từ vựng:** Trong tài liệu JDK hiện nay, đôi khi “CDS” được dùng như tên chung bao gồm cả lớp ứng dụng; không nhất thiết mọi tài liệu đều phân biệt rạch ròi “CDS” và “AppCDS” như tên hai sản phẩm hoàn toàn tách biệt.

### 2.1. Mốc phiên bản cần phân biệt

- **Java 10:** JEP 310 bổ sung khả năng đưa lớp ứng dụng vào archive — AppCDS.
- **JDK 12:** Oracle JDK bắt đầu cung cấp archive CDS mặc định được đóng gói sẵn cùng bản phân phối, giúp phần lớn chương trình nhận lợi ích mà không cần tự dump.
- **Các JDK tiếp theo:** Công cụ tạo archive ứng dụng và hỗ trợ các lớp/file source được mở rộng; cách tạo dynamic archive bằng `-XX:ArchiveClassesAtExit` vẫn được hỗ trợ trong tài liệu JDK hiện đại.
- **JDK 24:** JEP 483 giới thiệu AOT class loading & linking và **AOT cache**, mở rộng khả năng chuẩn bị lớp trước khi ứng dụng chạy.
- **JDK 25:** JEP 514 đơn giản hóa quy trình tạo AOT cache, với `-XX:AOTCacheOutput` cho kịch bản thông dụng.

**Special Note về kiến thức hiện hành:** Bài sử dụng cú pháp và hành vi đang có trong tài liệu Java SE/JDK hiện đại. Không lấy những lệnh/cờ từng có trong tài liệu Java 10 làm mặc định triển khai hôm nay nếu đã có quy trình hiện đại hơn.

## 3. Thực chất archive lưu những gì?

Archive không đơn thuần là một bản sao nguyên xi của các file `.class` rồi nén thành JAR khác. JAR thường chứa **class-file bytes** và tài nguyên ứng dụng. Khi HotSpot dùng CDS/AppCDS, dữ liệu lớp đủ điều kiện được chuẩn bị dưới dạng tối ưu cho việc nạp và sử dụng của JVM.

Về mặt khái niệm, JVM thường thực hiện:

~~~text
Không có archive phù hợp:

application.jar / modules
          |
          v
 tìm và đọc class bytes
          |
          v
 kiểm tra + phân tích định dạng lớp
          |
          v
 tạo metadata/cấu trúc nội bộ
          |
          v
 thực hiện chương trình

Có archive phù hợp:

       app.jsa / CDS archive
                 |
                 v
    OS ánh xạ các vùng file phù hợp
                 |
                 v
      JVM dùng class metadata đã chuẩn bị
                 |
                 v
           thực hiện chương trình
~~~

Trong thực tế, HotSpot vẫn thực hiện **những kiểm tra và thao tác runtime cần thiết**; archive không cho phép bỏ qua toàn bộ cơ chế an toàn hay tất cả các bước nạp lớp. Những lớp không có trong archive, không còn phù hợp hoặc không đủ điều kiện vẫn có thể được nạp theo đường thông thường.

### 3.1. Archive không phải một “JAR thay thế”

JAR gốc vẫn quan trọng:

- Nó xác định các lớp/tài nguyên thuộc ứng dụng và là đầu vào cho classpath/module path.
- Archive chỉ chứa **những phần được chọn và tối ưu hóa** cho một cấu hình xác định.
- Tài nguyên ngoài lớp, service files và nội dung ứng dụng khác không tự biến thành “memory-mapped class metadata” chỉ vì AppCDS được bật.
- Nếu JAR thay đổi sau khi tạo archive, các kiểm tra nhất quán có thể khiến archive bị từ chối hoặc chỉ dùng một phần trong những trường hợp được quy định.

**Không** xóa JAR ứng dụng sau khi tạo archive với suy nghĩ `app.jsa` là executable độc lập.

### 3.2. Không phải mọi class đều được archive

Phạm vi lớp được ghi/đọc phụ thuộc JDK, provider, classloader, module/class path và điều kiện hỗ trợ. Một lần chạy huấn luyện chỉ kích hoạt **một tập lớp nhất định**; những lớp chỉ sử dụng ở nhánh code hiếm gặp có thể không có trong archive.

Ví dụ, chạy thử chỉ endpoint health check có thể chưa kích hoạt lớp xử lý báo cáo, kết nối dữ liệu hoặc serialization. Khi production gọi các nhánh đó, JVM sẽ cần nạp những lớp bổ sung bình thường.

Vì vậy, việc chọn **workload huấn luyện đại diện** là quan trọng. Không thể suy ra “tất cả class của ứng dụng đã được archive” chỉ vì đã tạo được một file `.jsa`.

## 4. “Memory-mapped” nghĩa là gì?

**Memory mapping** là kỹ thuật của hệ điều hành cho phép ánh xạ nội dung một file hoặc vùng file vào **không gian địa chỉ ảo** của tiến trình. Thay vì ứng dụng tự gọi `read` để sao chép toàn bộ file vào một `byte[]` rồi giữ trong Java heap, runtime có thể để hệ điều hành quản lý việc ánh xạ các trang file vào tiến trình.

Sơ đồ:

~~~text
                 ĐĨA / HỆ THỐNG TỆP
            +--------------------------+
            | shared / app CDS archive |
            |  metadata lớp A, B, C... |
            +-------------+------------+
                          |
                       file mapping
                          |
               +----------+-----------+
               |                      |
           JVM process 1          JVM process 2
        Virtual address space  Virtual address space
        +------------------+   +------------------+
        | read-only pages  |   | read-only pages  |
        | from archive     |   | from archive     |
        +--------+---------+   +--------+---------+
                 |                      |
                 +----------+-----------+
                            |
                    PHYSICAL MEMORY
            +-----------------------------+
            | Các file-backed pages       |
            | có thể được dùng chung      |
            +-----------------------------+

     Mỗi JVM vẫn có Java heap, thread, stack và state riêng.
~~~

Đây là sơ đồ **khái niệm**, không phải cam kết mọi vùng archive của mọi JVM đều trỏ tới đúng một trang vật lý. Cơ chế ánh xạ, quyền truy cập, tái định vị, cache và tính chia sẻ thực tế phụ thuộc HotSpot/OS/JDK.

### 4.1. “Ánh xạ” không có nghĩa đã nạp toàn bộ file vào RAM

File được memory-map có thể xuất hiện trong **không gian địa chỉ ảo** của tiến trình, nhưng điều đó **không chứng minh** mọi trang của file đang thường trú trong RAM.

Hệ điều hành có thể:

1. Thiết lập vùng ánh xạ trong address space.
2. Nạp trang cần thiết khi JVM thực sự truy cập (page fault).
3. Tái sử dụng những trang file-backed đã có trong bộ nhớ đệm.
4. Thu hồi một số trang sạch khi thiếu bộ nhớ và nạp lại khi cần.

Vì thế **kích thước archive trên đĩa**, **kích thước vùng mapped trong virtual memory**, **RSS** và **bộ nhớ vật lý được dùng duy nhất** là những đại lượng khác nhau.

### 4.2. Vì sao các trang chỉ đọc có thể chia sẻ?

Các trang dữ liệu lớp được lưu ở dạng chỉ đọc và **không cần sửa riêng theo từng tiến trình** là ứng viên tốt để dùng chung physical pages của hệ điều hành.

Khi hai JVM cùng ánh xạ một archive tương thích:

- Mỗi JVM có **bảng ánh xạ địa chỉ ảo riêng**.
- Những địa chỉ ảo có thể khác nhau do bố cục address space và cơ chế bảo mật.
- Hệ điều hành có thể cho nhiều mapping cùng tham chiếu tới **một trang vật lý file-backed**.
- Nhờ không sao chép mọi metadata giống nhau thành bản riêng, tổng physical footprint có thể giảm.

**Không suy ra** rằng mỗi trang của archive chắc chắn chia sẻ được. Một số vùng cần sửa, relocation hoặc cấu trúc runtime có thể được xử lý riêng theo tiến trình; kết quả thực tế phụ thuộc bản JVM và OS.

### 4.3. Read-only, writable và copy-on-write

Nội dung archive có thể có những vùng với quyền truy cập khác nhau. Tài liệu CDS nhấn mạnh lợi ích từ **read-only shared metadata**. Nếu một trang cần writable semantics riêng cho từng JVM, cơ chế copy-on-write hoặc vùng dữ liệu riêng có thể khiến trang đó **không còn chia sẻ vật lý** theo cách của read-only mapping.

Vì vậy, lời giải thích đúng là:

> AppCDS cho phép **những phần metadata phù hợp** được memory-map và chia sẻ, chứ không làm **toàn bộ bộ nhớ của các JVM** trở thành vùng chung.

Không nên viết “một file 50 MiB được map vào ba JVM thì tổng RAM chỉ đúng 50 MiB” như một phép tính tuyệt đối. Heap riêng, runtime state và số trang thực sự chia sẻ vẫn ảnh hưởng.

## 5. AppCDS không chia sẻ Java heap của ứng dụng

Một nhầm lẫn quan trọng: **chia sẻ metadata lớp** khác với **chia sẻ các đối tượng ứng dụng**.

Xét:

~~~java
static final class Counter {
    static int total = 0;
}

public static void main(String[] args) {
    Counter.total++;
    System.out.println(Counter.total);
}
~~~

Nếu chạy trong **hai JVM độc lập**, mỗi tiến trình vẫn có state riêng. Mỗi JVM có thể in `1` ở lần chạy đầu, chứ AppCDS không biến `Counter.total` thành một biến toàn cục chia sẻ giữa hai tiến trình.

Dù metadata của lớp `Counter` đủ điều kiện được lưu trong archive:

- Java heap của JVM A **không được hợp nhất** với heap của JVM B.
- `static` fields không tự trở thành bộ nhớ chia sẻ cho mọi tiến trình.
- Class initialization vẫn có ngữ nghĩa **riêng đối với tiến trình/runtime** theo hợp đồng JVM.
- Những đối tượng mới tạo bằng `new` không tự được chia sẻ chỉ vì lớp của chúng nằm trong archive.
- Thread, stack, socket, JDBC connection và các biến môi trường là trạng thái runtime cần quản lý riêng.

**Cảnh báo:** Những cơ chế tối ưu AOT hiện đại có thể cache một số đối tượng heap với quy tắc riêng. Điều đó **không** biến CDS/AppCDS truyền thống thành một **shared mutable Java heap** giữa các JVM.

### 5.1. Thế metadata lớp là gì?

Metadata là thông tin JVM cần để biểu diễn và xử lý lớp: cấu trúc kiểu, quan hệ kế thừa, phương thức, trường, liên kết tới các thành phần runtime và những cấu trúc được triển khai trong HotSpot.

Cách lưu cụ thể của HotSpot có thể thay đổi giữa các bản JDK. Không nên buộc bài học vào một layout nội bộ cố định, địa chỉ con trỏ cố định hoặc danh sách field private chưa được Java SE bảo đảm.

Điều cần hiểu ở cấp ứng dụng là: **CDS/AppCDS chuẩn bị dữ liệu về lớp để giảm công việc khởi động**, không làm thay đổi giao diện của `Class<?>` hay hợp đồng đối tượng Java.

## 6. Quá trình tạo và sử dụng một archive

Một vòng đời điển hình:

~~~text
[BUILD]
compile classes, package immutable JAR
           |
           v
[TRAIN / ARCHIVE CREATION]
khởi chạy ứng dụng với workload đại diện
HotSpot ghi nhận những lớp đủ điều kiện
           |
           v
[ARCHIVE FILE]
       app.jsa
           |
           v
[DEPLOY / STARTUP]
HotSpot xác thực archive với JDK + application
           |
     +-----+------+
     |            |
  Phù hợp     Không phù hợp
     |            |
  Map và dùng   Bỏ qua / từ chối
  được archive  tùy chế độ/config
     |            |
     +-----+------+
           |
           v
 ứng dụng có hành vi nghiệp vụ bình thường
~~~

Các bước trên mô tả **dynamic AppCDS** ở mức tổng quan. Ngày nay còn nhiều hình thức như tạo static archive, `jcmd VM.cds`, `-XX:+AutoCreateSharedArchive` và AOT cache. Không phải mọi phương thức đều cần cùng một chuỗi lệnh.

### 6.1. Base archive và dynamic archive

**Base/static archive** có thể chứa những lớp JDK được dùng phổ biến. **Dynamic/top archive** bổ sung lớp thư viện/ứng dụng được quan sát khi chạy, dựa vào base archive phù hợp.

Một lệnh thông dụng:

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar SharedMetadataDemo
~~~

Trong cấu hình hỗ trợ, HotSpot tạo **dynamic archive** khi JVM kết thúc bình thường. Archive này ghi nhận các lớp đủ điều kiện **chưa được lưu trong base archive**. Nếu không chỉ định base archive riêng, JVM có thể dùng archive mặc định của JDK làm nền.

Khi chạy lại:

~~~bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar SharedMetadataDemo
~~~

Với dynamic archive, JDK có thể biết và tự tham chiếu tới base archive tương ứng, nên ví dụ không cần liệt kê hai file. Trên môi trường dùng nhiều archive tường minh, cú pháp `base:top` được tài liệu JDK mô tả; **Windows sử dụng dấu `;` thay cho `:`** khi liệt kê hai archive.

### 6.2. Tạo archive không làm thay đổi logic chương trình

Dù lần đầu chạy để huấn luyện hay chạy sử dụng archive, chương trình vẫn phải cho cùng **kết quả nghiệp vụ** với đầu vào giống nhau. Archive là tối ưu hóa, không phải một cách cho phép cache giá trị mutable của ứng dụng rồi bỏ qua logic trong những lần chạy sau.

Nếu output của ứng dụng đổi chỉ vì bật AppCDS, cần điều tra:

- Có benchmark nào dựa vào timing/thread scheduling không?
- Có dùng thông tin class loader hoặc internal behavior làm logic nghiệp vụ không?
- Có khác nhau về phiên bản JAR, JVM flags hoặc input giữa hai lần chạy không?
- Có sai sót do side effects, shared external services hay dữ liệu không ổn định không?

**Không** thiết kế code đòi archive nhất định phải được dùng để tính đúng kết quả.

## 7. Chương trình Java 17+ hoàn chỉnh, đã chạy kiểm chứng trên JDK 24

Mục tiêu của demo:

1. Compile ứng dụng nhỏ gồm lớp chính và lớp lồng nhau.
2. Gói các file class vào **JAR**.
3. Chạy bình thường.
4. Tạo một **dynamic AppCDS archive**.
5. Chạy lại với archive và ghi log nạp lớp.
6. Xác nhận lớp ứng dụng có thể được nạp từ vùng archive.
7. Chạy với `-Xshare:off` để thấy **output nghiệp vụ vẫn giống**.

### 7.1. Mã nguồn `SharedMetadataDemo.java`

~~~java
import java.util.List;

public class SharedMetadataDemo {
    static final class Greeting {
        static String text() {
            return "AppCDS";
        }
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(2, 3, 5);
        int sum = values.stream().mapToInt(Integer::intValue).sum();

        System.out.println("message=" + Greeting.text());
        System.out.println("sum=" + sum);
        System.out.println("items=" + values.size());
    }
}
~~~

**Stdout của mỗi lần chạy thành công:**

~~~text
message=AppCDS
sum=10
items=3
~~~

Cùng một kết quả ở chế độ bình thường, khi dùng archive và khi tắt CDS. Chúng ta chỉ xem **log nạp lớp** để phân biệt đường xử lý nội bộ, không dùng stdout ứng dụng làm bằng chứng lớp đã được map.

### 7.2. Biên dịch và tạo JAR

Trên Linux/macOS, chạy trong thư mục chứa file:

~~~bash
mkdir -p classes
javac -encoding UTF-8 -d classes SharedMetadataDemo.java
jar --create --file app.jar -C classes .
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory classes -Force | Out-Null
javac -encoding UTF-8 -d classes SharedMetadataDemo.java
jar --create --file app.jar -C classes .
~~~

Dùng `-d classes` để ghi class files vào thư mục build, sau đó `jar` đóng gói đúng các class. **Bước chạy AppCDS lấy class từ JAR**, không dùng đường dẫn tới thư mục `classes` làm classpath.

### 7.3. Chạy bình thường

~~~bash
java -cp app.jar SharedMetadataDemo
~~~

Stdout:

~~~text
message=AppCDS
sum=10
items=3
~~~

Ở bước này, một JDK hiện đại vẫn có thể dùng **CDS archive mặc định** cho các lớp JDK. “Chạy bình thường” không đồng nghĩa “tắt hoàn toàn CDS”.

### 7.4. Tạo dynamic archive

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar SharedMetadataDemo
~~~

Chương trình in cùng ba dòng. Khi kết thúc bình thường, JVM tạo `app.jsa` trong thư mục làm việc, nếu môi trường/classpath/JDK hỗ trợ và không có lỗi I/O. Nếu gặp thông báo lỗi, đọc log để biết archive có được tạo và những lớp nào đủ điều kiện.

**Đã kiểm chứng:** Trên JDK 24 với JAR chứa lớp của demo, lệnh tạo được file archive và trả exit code 0.

### 7.5. Chạy với archive và ghi log nạp lớp

~~~bash
java -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info:file=classload.log -cp app.jar SharedMetadataDemo
~~~

Ứng dụng vẫn in:

~~~text
message=AppCDS
sum=10
items=3
~~~

Để tìm log lớp ứng dụng trên Linux/macOS:

~~~bash
grep SharedMetadataDemo classload.log
~~~

Trên Windows PowerShell:

~~~powershell
Select-String -Path classload.log -Pattern SharedMetadataDemo
~~~

**Trích log đã quan sát trên JDK 24:**

~~~text
[class,load] SharedMetadataDemo source: shared objects file (top)
[class,load] SharedMetadataDemo$Greeting source: shared objects file (top)
~~~

Bản log thực còn chứa timestamp, level và nhiều lớp khác. Định dạng thời gian, thứ tự dòng, tập lớp và nội dung chi tiết có thể thay đổi theo JDK; phần trích chỉ cho thấy **bằng chứng lớp demo được nạp từ top shared archive**. Không buộc unit test bình thường phải khớp nguyên văn các dòng log đó.

### 7.6. Tắt CDS để đối chiếu hành vi

~~~bash
java -Xshare:off -cp app.jar SharedMetadataDemo
~~~

Stdout vẫn là ba dòng đã biết. Cờ `-Xshare:off` chỉ dùng **làm baseline/kiểm chứng**, không phải khuyến nghị vô hiệu hóa CDS trong production nếu ứng dụng có lợi từ nó.

**Kết quả kiểm chứng đầy đủ trên JDK 24:**

| Bước | Kết quả |
| --- | --- |
| `javac` compile | Thành công. |
| `jar` package | Thành công. |
| Chạy bình thường | Đúng ba dòng stdout. |
| `-XX:ArchiveClassesAtExit=app.jsa` | Exit code 0; archive tồn tại. |
| Chạy `-XX:SharedArchiveFile=app.jsa` | Đúng ba dòng stdout. |
| `-Xlog:class+load` | Lớp chính và lớp `Greeting` ghi `source: shared objects file (top)`. |
| Chạy `-Xshare:off` | Đúng ba dòng stdout. |

**Giới hạn:** Lệnh và kết quả được xác minh trên **HotSpot JDK 24**. Trên JDK khác, tùy chọn, định dạng log, điều kiện archive và lựa chọn AOT/CDS có thể khác. Ví dụ được viết bằng Java 17+ và không yêu cầu lập trình API nội bộ HotSpot.

## 8. Archive được memory-map lúc khởi động như thế nào?

Mô tả thực thi ở mức khái niệm:

1. JVM nhận đường dẫn archive (hoặc dùng archive mặc định).
2. HotSpot kiểm tra **file và metadata tương thích** với cấu hình JDK, ứng dụng, classpath/module path cùng những VM options liên quan.
3. HotSpot thiết lập vùng memory mapping thích hợp trong **virtual address space** của JVM.
4. Hệ điều hành quản lý truy cập các trang file-backed; những trang read-only phù hợp có thể chia sẻ giữa nhiều process.
5. Khi cần lớp đã được archive và đủ điều kiện dùng lại, HotSpot có thể dùng dữ liệu đã được chuẩn bị thay vì thực hiện toàn bộ công việc nạp thông thường.
6. Những lớp chưa lưu, không phù hợp hoặc không được hỗ trợ đi qua cơ chế nạp bình thường.

**Không** hiểu đây là một quy trình của `java.nio.MappedByteBuffer` do code ứng dụng phải tự gọi. Memory mapping của CDS diễn ra trong **JVM/native runtime**, ứng dụng Java bình thường không cần mở `FileChannel.map` để kích hoạt CDS.

### 8.1. Giới hạn: JVM có thể chọn đường khác

Memory mapping có thể không dùng được vì:

- Archive không tồn tại, không đọc được hoặc được tạo bằng build JDK không phù hợp.
- JAR/module bị thay đổi so với lúc tạo archive.
- Classpath/module path hoặc VM options không nhất quán với lúc archive creation.
- OS/CPU architecture hoặc đặc tính runtime không tương thích.
- Lớp không đủ điều kiện hoặc có hành vi classloading khác với lần ghi nhận.
- Ánh xạ tại địa chỉ dự kiến không khả thi; HotSpot có thể xử lý/tái định vị hoặc fallback tùy JDK.

Với chế độ tự động thông thường, JVM có thể **bỏ qua** archive không phù hợp và tiếp tục khởi động theo đường không dùng archive. Với chế độ kiểm tra nghiêm ngặt, có thể thoát khi không dùng được; không nhầm hai chính sách này.

### 8.2. ASLR và việc chia sẻ metadata

Các hệ điều hành hiện đại dùng **Address Space Layout Randomization (ASLR)** và mỗi process có address space độc lập. Vì vậy không được giả định một page trong archive sẽ có cùng **địa chỉ ảo** trong hai JVM.

HotSpot có cơ chế hỗ trợ relocation/address mapping ở những phiên bản được hỗ trợ; nhưng chi phí, vùng được chia sẻ và hiệu quả còn phụ thuộc cách runtime xử lý dữ liệu chứa tham chiếu địa chỉ. Mô hình đúng là **chia sẻ physical file-backed pages khi có thể**, không phải “hai JVM dùng cùng một con trỏ Java”.

### 8.3. Memory mapping và caching ở hệ điều hành

Khi nhiều JVM cùng map archive trên một host, file-backed pages có thể nằm trong **page cache**. Một JVM khởi động sau có thể hưởng lợi khi trang đã hiện diện trong RAM, nhưng nếu trang chưa resident, OS vẫn phải đọc từ storage.

**Không** nói memory mapping làm hoàn toàn biến mất I/O đĩa, hay tất cả khởi động đều có tốc độ như nhau. Cold start, warm start, dung lượng RAM, page cache, filesystem và workload có thể tạo kết quả khác nhau.

## 9. Vì sao AppCDS có thể làm startup nhanh hơn?

Giảm startup time có thể đến từ:

- Ít công việc đọc/giải mã/class metadata preparation cho các lớp đủ điều kiện.
- Tránh lặp lại một phần phân tích lớp đã thực hiện lúc archive creation.
- Truy cập metadata tối ưu từ vùng mapped thay vì khởi dựng toàn bộ từ JAR/runtime image.
- Tái sử dụng những trang dữ liệu lớp đã được OS page-cache khi nhiều JVM chạy cùng ứng dụng.

Nhưng một ứng dụng không chỉ làm class loading lúc khởi động. Nó còn có thể:

- Kết nối cơ sở dữ liệu, DNS, network.
- Khởi tạo dependency injection/container.
- Đọc cấu hình và secrets.
- Khởi tạo thread pools, TLS, native libraries.
- Thực hiện JIT compilation và các bước warmup khác.

Nếu thời gian khởi động chủ yếu nằm ở network hay dependency injection, AppCDS **không thể đảm bảo** mức tăng tốc lớn. Hiệu quả phải **đo bằng benchmark** trên môi trường và workload thực.

### 9.1. Archive file trên đĩa có thể lớn hơn class bytes

Tài liệu launcher JDK lưu ý archive chứa dữ liệu lớp ở dạng tối ưu của VM; **dung lượng archive có thể lớn hơn tổng các class-file bytes trong JAR**. Đây là sự đánh đổi: chấp nhận artifact đã chuẩn bị ở đĩa để giảm công việc khởi động và có cơ hội chia sẻ các trang runtime.

**Không** kỳ vọng “có AppCDS thì app.jar nhỏ hơn” hoặc “file archive tự làm giảm kích thước deployment” — thường bạn cần giữ cả JAR và archive, tăng số artifact phải triển khai.

### 9.2. Memory footprint giảm theo tập lớp và số tiến trình

Một process đơn lẻ có thể tiết kiệm thời gian/metadata private memory nhờ CDS. Lợi ích chia sẻ trang càng đáng quan tâm khi **nhiều JVM tương tự cùng chạy trên một host** và có thể cùng dùng một archive hợp lệ.

Không suy từ số JVM để tính tiết kiệm tuyến tính tuyệt đối: một số trang vẫn private; Java heap, native allocations, JIT code cache và thread stacks thuộc từng process.

## 10. Tại sao số đo RAM đôi khi dễ gây hiểu lầm?

Có ít nhất bốn đại lượng cần phân biệt:

| Đại lượng | Ý nghĩa | Cạm bẫy khi đánh giá CDS |
| --- | --- | --- |
| **Archive file size** | Byte của file `.jsa` trên đĩa. | Không phải số RAM đã tiết kiệm. |
| **Virtual memory / address space** | Vùng địa chỉ ánh xạ, có thể lớn. | Mapping không có nghĩa tất cả trang đã nạp vào RAM. |
| **RSS** | Các trang resident được process nhìn thấy. | Shared pages có thể được tính trong RSS của **mỗi** process. |
| **PSS** | Proportional Set Size, phân bổ trọng số trang chia sẻ cho từng process (trên OS hỗ trợ). | Hữu ích hơn để hiểu chia sẻ nhưng vẫn tùy OS và công cụ. |
| **Private memory / heap** | Phần RAM riêng và Java heap của process. | CDS không hợp nhất toàn bộ private allocations. |
| **Startup latency** | Thời gian ứng dụng đạt trạng thái sẵn sàng. | Phụ thuộc cả filesystem, classloading lẫn I/O khác. |

Giả sử hai JVM cùng dùng một trang 4 KiB đã resident:

- Trong báo cáo RSS, trang đó **có thể được tính cho cả hai JVM** vì cả hai đều map.
- Về bộ nhớ vật lý, trang file-backed thực tế **có thể chỉ tồn tại một bản**.
- Nếu cộng RSS của hai JVM mà không xét shared pages, bạn có thể **đếm hai lần**.
- Trên Linux, PSS của mỗi process thường phản ánh phần chia sẻ của trang đó tốt hơn.

**Không** lấy việc RSS không giảm rõ để kết luận chắc chắn CDS không chia sẻ trang; cần xem các chỉ số phù hợp và điều kiện chạy.

### 10.1. Cách đo đúng

Một thí nghiệm có giá trị nên:

1. Cố định **cùng build JDK**, cùng JAR, cấu hình, input, CPU/memory giới hạn và OS.
2. Có baseline **không dùng CDS** khi cần: `-Xshare:off`.
3. Có một lượt **dùng archive mặc định**.
4. Có một lượt **dùng archive ứng dụng**.
5. Dùng công cụ quan sát classloading/CDS để xác nhận archive thực sự được áp dụng.
6. Chạy nhiều lượt, phân biệt cold/warm caches, tính median hoặc percentile.
7. Đo **startup time** tới trạng thái sẵn sàng có định nghĩa, không chỉ đo thời gian JVM bắt đầu.
8. Nếu đo footprint nhiều tiến trình, xem shared/private mappings hoặc chỉ số OS phù hợp.
9. Tách kết quả về **startup**, **warmup**, **throughput** và **memory footprint**.

Với container, hãy dùng metric tài nguyên ở cấp container/cgroup đúng ngữ nghĩa. Không coi memory usage của một JVM là tổng mức tiêu thụ vật lý độc nhất của tất cả container trên host nếu có shared file pages.

### 10.2. Dùng log để xác nhận archive có được sử dụng

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp app.jar SharedMetadataDemo
~~~

Log `cds` giúp biết quá trình kiểm tra và mapping archive; nội dung chi tiết thay đổi giữa JDK. Nếu muốn biết một lớp cụ thể đến từ đâu:

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa -cp app.jar SharedMetadataDemo
~~~

Tìm những dòng class load có `source: shared objects file` hoặc `source: shared objects file (top)` trên các HotSpot hỗ trợ. **Đừng** coi việc file `app.jsa` tồn tại là bằng chứng chắc chắn mọi class đã được nạp từ archive.

## 11. Điều kiện tương thích: archive không phải artifact portable tùy ý

CDS archives thường gắn chặt với **bản JDK**, nội dung ứng dụng và những chi tiết VM/OS liên quan. Không tự sao chép archive từ mọi máy hoặc JDK sang mọi môi trường rồi mặc định tái sử dụng được.

Các điều kiện cần kiểm soát:

| Yếu tố | Vì sao ảnh hưởng? | Thực hành |
| --- | --- | --- |
| **JDK build/release** | Bố cục metadata và cấu trúc runtime có thể khác. | Tạo lại archive khi đổi JDK build theo tài liệu. |
| **JAR/classpath** | Lớp phải khớp nội dung lúc archive tạo. | Giữ artifact immutable, tạo cache theo release. |
| **Module path / module options** | Có thể ảnh hưởng tập lớp và module graph. | Dùng options nhất quán giữa train và run. |
| **OS/CPU architecture** | Native layout và cơ chế mapping có thể khác. | Tạo archive trên môi trường deployment tương thích. |
| **VM flags / agent** | Một số cờ/JVMTI agent thay đổi cách classes được nạp/biến đổi. | Xác minh tương thích; kiểm tra log/fallback. |
| **Class loaders** | Không phải mọi loader/hành vi nạp đều đủ điều kiện. | Quan sát class-load logs; không suy từ class name. |
| **File permissions** | JVM cần đọc file archive; quyền ghi tùy môi trường tạo archive. | Cung cấp đúng quyền, bảo vệ artifact. |

**Chú ý với classpath:** tài liệu launcher hiện đại nêu các giới hạn khi archive creation, đặc biệt classpath/module path chứa **non-empty directories**. Ví dụ thực hành gói các class vào **JAR** để tránh dựa vào hành vi ngoài phạm vi hỗ trợ. Classpath dùng khi tạo archive cần tương thích với lúc chạy, các JAR liên quan phải không đổi.

### 11.1. Vì sao không ghi đè archive đang dùng tùy tiện?

Những tiến trình đang chạy có thể đã **memory-map** archive file. Chính sách triển khai tốt là tạo archive mới từ release/JDK mới, sau đó trỏ **các JVM mới** tới artifact đó, thay vì tùy tiện sửa byte của một archive đang được dùng.

Điều này vừa bảo vệ tính nhất quán, vừa giảm nguy cơ file thay đổi giữa bước validation và mapping. Trong môi trường vận hành, nên dùng artifact path/version rõ ràng và chiến lược rollout/rollback có kiểm soát.

### 11.2. Archive phải là artifact đáng tin

Tệp archive có dữ liệu nội bộ mà JVM đọc hoặc ánh xạ. **Không tải archive không tin cậy từ Internet rồi dùng với JVM production**.

Thực hành:

- Tạo trong CI/CD hoặc môi trường build được kiểm soát.
- Phân quyền để tiến trình không tin cậy không thể sửa archive.
- Giữ version/build provenance cùng các JAR tương ứng.
- Dùng quy trình artifact integrity/signature của hệ thống khi cần bảo đảm nguồn gốc.
- Coi archive như một phần của **supply chain** ứng dụng, không phải một file cache vô hại.

Một số cờ kiểm tra checksums có thể phát hiện **hỏng dữ liệu không chủ ý**; checksum như CRC32 **không phải chữ ký mật mã**, không thay xác minh nguồn gốc và quyền truy cập.

## 12. `-Xshare:on`, `auto`, `off` và fallback

| Chế độ | Hành vi khái quát | Dùng khi |
| --- | --- | --- |
| `-Xshare:auto` | Cho phép dùng CDS khi phù hợp, thường tiếp tục bình thường khi không áp dụng được. | Kịch bản production điển hình; nhiều JDK bật CDS mặc định. |
| `-Xshare:on` | Buộc CDS; có thể khiến JVM thoát nếu không dùng được archive. | **Kiểm thử/diagnostics**, không nên là mặc định production. |
| `-Xshare:off` | Không dùng CDS archives. | Baseline benchmark, tìm nguyên nhân lỗi, so sánh. |

Oracle JDK hiện đại cảnh báo `-Xshare:on` có thể làm startup thất bại nếu archive hoặc VM options không tương thích; vì thế **không khuyến nghị dùng trong production**.

Mấu chốt: CDS là **tối ưu hóa**. Ứng dụng nên vẫn chạy đúng khi archive không được dùng, miễn môi trường JVM và chương trình nói chung hợp lệ.

Nếu cần CI xác thực lớp cụ thể đã dùng archive, có thể dùng log hoặc chế độ diagnostics cho test có kiểm soát. Đừng áp chính sách “không có archive thì dịch vụ không chạy” cho mọi môi trường chỉ để kiếm lợi hiệu năng nhỏ.

## 13. AppCDS trên Java hiện đại: AOT cache không phải là kiến thức đã lỗi thời

Cơ chế memory-mapped class metadata của CDS vẫn còn liên quan trong các HotSpot hiện đại. Tuy nhiên, nếu đang tối ưu **ứng dụng mới** trên JDK 24/25/26, cần biết tiến hóa của AOT.

### 13.1. JDK 24 — AOT class loading and linking

**JEP 483** giới thiệu **Ahead-of-Time Class Loading & Linking**. AOT cache có thể chứa thêm trạng thái **lớp được nạp và liên kết trước**, bên cạnh ý tưởng lưu metadata class. Điều này nhằm giảm chi phí **startup và warmup** mà AppCDS truyền thống không giải quyết toàn diện.

AOT cache cũng có ràng buộc về **JDK, ứng dụng, OS/CPU, VM options và độ nhất quán giữa lúc huấn luyện với lúc chạy**. Không mặc định archive CDS truyền thống và AOT cache có định dạng hoặc cách sử dụng như nhau.

### 13.2. JDK 25+ — tạo AOT cache dễ hơn

Theo **JEP 514**, có một cách tạo AOT cache cho trường hợp phổ biến:

~~~bash
# Ví dụ cú pháp dành cho HotSpot JDK 25+:
java -XX:AOTCacheOutput=app.aot -cp app.jar SharedMetadataDemo

# Chạy những lần tiếp theo với cache:
java -XX:AOTCache=app.aot -cp app.jar SharedMetadataDemo
~~~

Đây là **mẫu cho JDK 25+**, **không** phải lệnh đã được kiểm chứng bằng máy JDK 24 của ví dụ ở phần 7. Vùng cache là `app.aot`, **không phải cùng ý nghĩa với `app.jsa`** do `-XX:ArchiveClassesAtExit` tạo ra.

Các workload thực tế (ví dụ ứng dụng Spring Boot lớn) cần **training run đại diện** và có thể phải điều chỉnh packaging/startup options; tham khảo tài liệu framework để dùng đúng cách.

### 13.3. Cái gì vẫn đúng khi chuyển sang AOT cache?

- Chuẩn bị dữ liệu lớp trước khi khởi động vẫn có thể giúp giảm startup.
- OS/JVM vẫn cần **đọc, map hoặc khôi phục** các artifact AOT theo format phù hợp.
- Tính tương thích JDK/application vẫn quan trọng.
- Dữ liệu runtime mutable của ứng dụng vẫn không trở thành shared mutable Java heap giữa mọi JVM.
- Không suy ra mọi thứ được memory-map chỉ bởi từ “cache”: một số artifact có thể được **khôi phục/khởi tạo theo cách khác** tùy tính năng và JDK.
- Phải đo trên workload thực, không lấy benchmark của JDK khác làm cam kết.

Từ JDK 25+, một số framework khuyến nghị **AOT cache** thay cho quy trình CDS thủ công trong trường hợp hỗ trợ. AppCDS và cú pháp CDS vẫn có trong tài liệu launcher hiện đại, nhưng việc lựa chọn nên dựa trên **runtime, framework và mục tiêu vận hành**.

### 13.4. Không gộp metadata lớp và cached heap objects làm một

AOT cache có thể chứa các thành phần tối ưu hóa khác như dữ liệu liên quan class loading/linking, object state hoặc thông tin phục vụ warmup theo bản JDK. Đặc biệt trong những JDK mới, cách biểu diễn một số cached heap objects có thể khác cơ chế memory-map read-only class metadata.

Vì thế **không tuyên bố** “mọi đối tượng được AOT cache lưu đều được map read-only và chia sẻ giữa nhiều JVM”. Những khẳng định về loại artifact và cơ chế chia sẻ phải dựa vào **JEP và JavaDoc đúng phiên bản**.

## 14. AppCDS trong container và quy trình build/deploy

Một mô hình triển khai thường gặp:

~~~text
Build image / CI
      |
      |-- compile + package application JAR
      |-- tạo archive phù hợp với image/runtime
      |-- giữ archive/JAR với quyền đọc phù hợp
      v
Container image immutable
      |
      +--> JVM process A (mở archive)
      |
      +--> JVM process B (mở cùng archive nếu cùng host/mount)
      |
      +--> JVM process C (mở cùng archive nếu cùng host/mount)
~~~

**Hiệu quả chia sẻ physical pages** phụ thuộc các tiến trình có thực sự dùng cùng file-backed data trên **cùng host** hay không và cơ chế kernel/filesystem. Hai container trên hai máy khác nhau **không thể cùng chia sẻ RAM vật lý** dù chúng dùng image giống nhau.

### 14.1. Archive và container image

- Tạo archive với **runtime JDK khớp** image production.
- Nếu dùng multi-stage build, cẩn thận không tạo archive trên JDK/OS/architecture khác với runtime cuối.
- Giữ application JAR và archive cùng lifecycle release.
- Không sửa JAR hoặc thư viện sau bước tạo archive.
- Kiểm tra file path/permissions và log trong image thật.
- Khi update JDK hoặc JAR, tạo lại archive/cache.
- Không mặc định shared memory sẽ xuất hiện trong mọi cấu hình overlay filesystem/mount giống nhau.

### 14.2. Khác biệt giữa nhiều JVM và một JVM nhiều thread

CDS/AppCDS có mục tiêu đặc biệt đáng chú ý khi **nhiều JVM processes** dùng những lớp giống nhau. Nếu một ứng dụng chạy 100 threads **bên trong một JVM**, các threads vốn đã dùng chung nhiều cấu trúc runtime của chính JVM đó; AppCDS không phải cơ chế làm chúng chia sẻ class metadata lần đầu tiên.

Không nhầm vấn đề **nhiều process** với **nhiều thread**.

## 15. Các ngộ nhận phổ biến

| Ngộ nhận | Vì sao không chính xác | Cách hiểu đúng |
| --- | --- | --- |
| “AppCDS là một file JAR thứ hai.” | Archive lưu dữ liệu lớp dạng tối ưu của VM. | JAR gốc và archive có vai trò khác nhau. |
| “JVM đọc toàn bộ archive vào Java heap.” | CDS dùng memory mapping/native runtime; không phải mảng byte trong heap ứng dụng. | Phân biệt virtual mapping và Java heap. |
| “Có memory mapping nghĩa là tất cả byte đã ở RAM.” | Trang có thể được nạp theo nhu cầu. | Phân biệt mapped address space với resident pages. |
| “Mọi trang archive đều được chia sẻ giữa các JVM.” | Có những trang/vùng riêng hoặc không thể chia sẻ. | Nói rõ **phần read-only phù hợp** có thể chia sẻ. |
| “AppCDS làm static fields trở thành biến toàn cục liên tiến trình.” | Mỗi JVM vẫn có state/class initialization riêng. | Metadata lớp khác mutable state. |
| “AppCDS chia sẻ tất cả Java heap objects.” | Đó không phải hợp đồng CDS truyền thống. | Heap riêng; AOT object caching là cơ chế khác. |
| “Chỉ cần thấy app.jsa là chương trình đã dùng archive.” | Archive có thể không tương thích và bị bỏ qua. | Xác minh `-Xlog:cds`/`class+load`. |
| “CDS luôn tiết kiệm đúng kích thước archive nhân số JVM.” | RSS/PSS/shared mappings/private heap khác nhau. | Đo bằng metric đúng ngữ nghĩa. |
| “Có AppCDS thì không cần JAR.” | Classpath/bytecode resources vẫn thuộc ứng dụng. | Triển khai JAR và archive theo đúng hợp đồng. |
| “Tạo archive bằng JVM A rồi dùng với bất kỳ JVM B.” | Nội dung gắn với JDK build/application/platform. | Tạo lại khi thay đổi môi trường. |
| “Training chạy một endpoint đã archive tất cả classes.” | Chỉ ghi lớp được kích hoạt và đủ điều kiện. | Dùng workload huấn luyện đại diện. |
| “Bật `-Xshare:on` là nên làm ở production.” | Nó có thể fail startup khi archive không dùng được. | Dùng chế độ tự động, `on` chỉ diagnostics. |
| “`-Xshare:off` làm tăng performance.” | Tắt một tối ưu; đôi khi hữu ích để đo baseline. | Bật/tắt có số liệu thực nghiệm. |
| “AOT cache JDK 25 là cùng định dạng với AppCDS .jsa.” | Cache chứa phạm vi tối ưu hóa rộng hơn. | Dùng đúng flags và docs của JDK. |
| “JDK 24+ AOT cache không liên quan đến CDS.” | AOT được phát triển trên nền các tối ưu class sharing, nhưng phạm vi đã mở rộng. | Phân biệt cơ chế kế thừa và tính năng mới. |
| “Một trang shared được tính đúng một lần trong tổng RSS các process.” | Mỗi RSS có thể tính cùng trang. | Xem PSS/shared/private metrics. |
| “Một file archive từ nguồn bất kỳ là an toàn.” | Runtime đọc dữ liệu nội bộ từ artifact đó. | Chỉ dùng archive tin cậy và kiểm soát integrity. |
| “Nếu stdout giống nhau tức class đã được nạp từ archive.” | Kết quả nghiệp vụ phải giống dù bật/tắt. | Kiểm tra class-load/ CDS logs để biết đường nạp. |

## 16. Bài tập và đáp án

### Câu 1 — Memory mapping là gì?

Một JVM “map” AppCDS archive vào bộ nhớ. Có nhất thiết toàn bộ archive đã nằm trong RAM không?

**Đáp án:** Không. Mapping thiết lập vùng **virtual address space**; trang được nạp và quản lý theo cơ chế OS. “Mapped” khác với “resident”. Cũng không có nghĩa toàn bộ archive nằm trong **Java heap**.

### Câu 2 — Hai tiến trình JVM

Hai JVM chạy cùng ứng dụng, dùng cùng archive. Cái gì có thể chia sẻ?

**Đáp án:** Những **trang metadata read-only file-backed** đủ điều kiện có thể được chia sẻ. Mỗi JVM vẫn có heap, stacks, threads và mutable state riêng. Không có một `static int` duy nhất cho cả hai process.

### Câu 3 — Class trong archive có phải bytecode JAR nguyên bản?

**Đáp án:** Không đơn thuần. CDS archive lưu dữ liệu lớp ở định dạng tối ưu cho HotSpot. JAR vẫn chứa lớp/tài nguyên ứng dụng và là một phần của cấu hình chạy.

### Câu 4 — Đánh giá hiệu năng

Một app có 200 ms startup, trong đó 180 ms chờ kết nối database. Có chắc AppCDS giảm hơn 50% startup không?

**Đáp án:** Không. CDS chủ yếu tối ưu đường nạp/xử lý lớp; kết nối DB không tự biến mất. Phải benchmark trong điều kiện tương đương để biết hiệu quả thật.

### Câu 5 — File `app.jsa` tồn tại

Điều đó đủ chứng minh lớp `Greeting` được nạp từ archive không?

**Đáp án:** Không. Cần chạy với archive phù hợp và xem log `-Xlog:class+load`; ví dụ JDK 24 trong bài xuất hiện `SharedMetadataDemo$Greeting source: shared objects file (top)`.

### Câu 6 — `-Xshare:on` và `auto`

Tại sao không khuyến nghị buộc `-Xshare:on` ở production?

**Đáp án:** `on` có thể khiến JVM thoát nếu CDS không khả dụng do archive/options không tương thích. `auto` ưu tiên chạy ứng dụng đúng và dùng CDS khi có thể.

### Câu 7 — RSS của hai JVM

Hai process cùng map một trang chỉ đọc. Vì sao cộng RSS có thể đếm hai lần RAM?

**Đáp án:** RSS của mỗi process có thể chứa **cùng một shared resident page**. Để phân tích memory-sharing tốt hơn, dùng công cụ và metric như PSS trên OS có hỗ trợ.

### Câu 8 — Thay JAR sau khi training

Bạn sửa `app.jar` nhưng giữ `app.jsa` cũ. Có nên mặc định archive vẫn hoạt động?

**Đáp án:** Không. CDS kiểm tra tính tương thích của lớp/classpath/JAR. Cần tạo lại archive tương ứng với release mới và xác minh log khi deploy.

### Câu 9 — Khác host

Hai container chạy cùng image trên hai host khác nhau có chia sẻ vật lý cùng một RAM archive không?

**Đáp án:** Không. Mỗi host có RAM/kernel riêng. Chúng có thể dùng những file archive có nội dung giống nhau nhưng không dùng chung trang vật lý giữa hai máy.

### Câu 10 — Dynamic archive

`-XX:ArchiveClassesAtExit=app.jsa` dùng để làm gì?

**Đáp án:** Tạo dynamic archive từ những lớp đủ điều kiện đã được sử dụng trong một lần chạy; archive được ghi khi JVM kết thúc bình thường. Lần chạy sau có thể dùng `-XX:SharedArchiveFile=app.jsa` với cấu hình tương thích.

### Câu 11 — AOT cache hiện đại

Có nên viết hướng dẫn cho JDK 25+ mà chỉ biết cách tạo AppCDS .jsa của Java 10 không?

**Đáp án:** Không. CDS vẫn còn được hỗ trợ, nhưng JDK 24 thêm AOT cache và JDK 25 đơn giản hóa workflow qua `-XX:AOTCacheOutput`. Hãy đánh giá tài liệu/runtime/framework hiện tại và chọn giải pháp phù hợp.

### Câu 12 — Mutable Java heap

AOT cache có thể lưu một số object artifacts; có thể kết luận tất cả objects dùng chung giữa JVM và mọi ghi object đều được chia sẻ?

**Đáp án:** Không. Mô hình Java heap của mỗi process vẫn riêng và cách lưu/khôi phục AOT artifacts phụ thuộc bản JDK. Không nhầm AOT object caching với chia sẻ mutable heap xuyên tiến trình.

### Câu 13 — Archive không đáng tin

Vì sao không tải một archive từ nguồn lạ rồi chạy với JVM production?

**Đáp án:** Archive có dữ liệu VM nội bộ và được runtime dùng trong quá trình khởi động. Nên tạo từ JDK/JAR đáng tin và bảo vệ quyền ghi, integrity và provenance.

### Câu 14 — Lớp không được kích hoạt lúc train

Một endpoint chỉ dùng ở production không xuất hiện trong training run; chương trình có bị “thiếu class” chỉ vì archive không có lớp đó không?

**Đáp án:** Không do bản thân sự thiếu vắng trong archive. JVM vẫn có thể tải lớp từ nguồn thông thường khi cần, nếu classpath và chương trình hợp lệ. Nhưng lợi ích startup của lớp đó có thể không đạt được.

## 17. Checklist vận hành AppCDS/AOT

- [ ] Tôi hiểu CDS/AppCDS là **tối ưu hóa dữ liệu lớp**, không phải một heap chung.
- [ ] Tôi biết AppCDS được bổ sung trong Java 10, JEP 310.
- [ ] Tôi không nhầm class archive với JAR chứa bytecode hoặc các tài nguyên của app.
- [ ] Tôi phân biệt archive file bytes, virtual mapping, RSS, PSS và physical sharing.
- [ ] Tôi không hứa mọi trang archive đều resident hoặc đều shareable.
- [ ] Tôi hiểu mọi JVM có state/heap/static fields riêng.
- [ ] Tôi tạo archive theo **JDK build, JAR và môi trường** phù hợp với deployment.
- [ ] Tôi dùng JAR/classpath/module path nhất quán giữa training và runtime.
- [ ] Tôi không tự tin rằng archive chứa mọi lớp chỉ từ việc file tồn tại.
- [ ] Tôi đã nhìn `-Xlog:cds` và `-Xlog:class+load` để xác minh lớp cần thiết lấy từ archive.
- [ ] Tôi không dùng `-Xshare:on` như chế độ production mặc định.
- [ ] Tôi giữ nguyên kết quả nghiệp vụ khi bật/tắt CDS.
- [ ] Tôi bảo vệ archive như artifact được tin cậy, có provenance và quyền truy cập phù hợp.
- [ ] Tôi không ghi đè byte của archive đang dùng tùy tiện.
- [ ] Tôi đo startup và footprint bằng workload đại diện, nhiều lần, cùng điều kiện.
- [ ] Tôi nhớ startup còn phụ thuộc DB/network/framework/JIT chứ không chỉ classloading.
- [ ] Với container, tôi phân biệt sharing trên **cùng host** với các host khác nhau.
- [ ] Tôi biết JDK 24 có AOT cache, JDK 25 có `-XX:AOTCacheOutput` và quy trình mới.
- [ ] Tôi kiểm tra tính tương thích AOT/CDS với JDK, framework và VM flags của dự án.
- [ ] Tôi không mô tả AOT cache như một bản sao y hệt AppCDS .jsa hay tuyên bố mọi AOT object memory-mapped.
- [ ] Khi cập nhật JDK/JAR, tôi tạo lại cache cần thiết và xác nhận bằng logs/benchmark.

## 18. Tài liệu tham khảo chính thức còn áp dụng

1. [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): giới thiệu AppCDS trong Java 10, cho phép đưa các lớp ứng dụng vào shared archive.
2. [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): memory-mapped read-only JVM metadata, chia sẻ giữa processes, giảm startup/footprint và cảnh báo `-Xshare:on`.
3. [Oracle Java SE 25 — The java Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): archive mặc định, static/dynamic archives, `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, classpath restrictions và các tùy chọn.
4. [Dev.java — Java Launcher: Dynamic CDS archive](https://dev.java/learn/jvm/tools/core/java/): cách tạo dynamic archive khi ứng dụng kết thúc và sử dụng trong các lần chạy sau.
5. [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): lịch sử chuyển sang archive CDS mặc định đóng gói sẵn từ JDK 12.
6. [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): tạo dynamic archive dựa trên lớp ứng dụng được nạp.
7. [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): tiến hóa từ CDS sang AOT cache trên JDK 24.
8. [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): đơn giản hóa AOT cache workflow trên JDK 25.
9. [Inside Java — AOT Cache Optimizations (2026)](https://inside.java/2026/01/09/run-aot-cache/): hướng dẫn các bước tạo và sử dụng cache trên JDK mới.
10. [Oracle Java SE 25 — Java Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các tag `cds` và `class+load` để chẩn đoán quá trình nạp lớp/áp dụng archive.

**Kết luận:** AppCDS (Java 10, JEP 310) cho phép lưu một phần dữ liệu lớp ứng dụng vào **archive** ở dạng đã chuẩn bị. Khi HotSpot khởi động, những vùng phù hợp được **memory-map** để giảm công việc nạp lớp và có thể chia sẻ **các trang metadata read-only** giữa JVM processes trên cùng host. Điều đó **không** làm Java heap hoặc static fields trở thành chung, không bảo đảm mọi trang đều resident, và không tự làm mọi ứng dụng nhanh hơn. Với Java mới, tiếp tục hiểu cơ chế CDS nhưng cũng cần đánh giá **AOT cache JDK 24+ và workflow JDK 25+**, cùng các ràng buộc JDK/JAR/platform/security trước khi triển khai.