# CDS và chi phí nạp dữ liệu lớp khi khởi động JVM (Java 10+)

## 1. Mục tiêu bài học

Khi một ứng dụng Java khởi động, JVM cần tìm, đọc và xử lý thông tin của nhiều **class** trước khi chạy đầy đủ các thành phần nghiệp vụ. Với ứng dụng có nhiều thư viện, số lớp tham gia khởi động có thể từ hàng trăm đến hàng nghìn. Công việc đọc và phân tích các tệp `.class`, xây dựng metadata và chuẩn bị lớp có thể đóng góp đáng kể vào **startup time** và chi phí bộ nhớ.

**Class Data Sharing (CDS)** là cơ chế của HotSpot JVM giúp giảm một phần công việc đó: những dữ liệu lớp có thể chia sẻ được chuẩn bị trước và lưu trong một **shared archive**. Khi một JVM khác cần các lớp phù hợp, nó có thể ánh xạ (memory-map) thông tin đã chuẩn bị từ archive thay vì lặp lại toàn bộ một số bước xử lý class file.

**Application Class-Data Sharing (AppCDS)** mở rộng lợi ích này cho **các lớp ứng dụng và thư viện** ngoài lớp nền của JDK. AppCDS được giới thiệu với **JDK 10 — JEP 310**, và cơ chế CDS/AppCDS tiếp tục phát triển trong các JDK mới.

Sau bài học, bạn sẽ:
1. Hiểu **những chi phí nạp dữ liệu lớp** mà CDS/AppCDS có thể tiết kiệm.
2. Phân biệt **class loading**, **linking**, **initialization**, chạy **static initializer**, khởi tạo framework và **JIT compilation**.
3. Biết **CDS chứa gì, chia sẻ như thế nào**, và vì sao nó không phải cache cho toàn bộ heap hoặc mọi công việc khởi động.
4. Phân biệt **CDS nền** của JDK với **AppCDS** chứa lớp thuộc ứng dụng.
5. Tạo và sử dụng **dynamic CDS archive** bằng quy trình vẫn khả dụng trên **JDK 17+**, có ví dụ chạy độc lập.
6. Kiểm chứng có lớp được lấy từ archive bằng **JVM Unified Logging**.
7. Đo startup và memory footprint công bằng, không bịa số phần trăm tăng tốc.
8. Nắm ràng buộc về phiên bản JDK, classpath, JAR, runtime option và an toàn triển khai.
9. Biết quan hệ giữa AppCDS truyền thống và **AOT cache** xuất hiện trong JDK hiện đại.

**Special Note:** Bài chỉ trình bày những kiến thức **còn áp dụng hiện nay**. Các thao tác lịch sử của Java 10 được đặt trong bối cảnh phát triển công nghệ, không được xem là cách cấu hình duy nhất cho JDK mới. Bài tập sử dụng **Java 17+**, không cần preview.

## 2. Vì sao nạp lớp có chi phí trong lúc khởi động?

Để chạy ứng dụng, HotSpot JVM cần xử lý các lớp mà chương trình sử dụng. Một mô hình khái quát:

~~~text
Khởi động Java process
        │
        ▼
Khởi tạo JVM, bootstrap runtime
        │
        ▼
Tìm những lớp được yêu cầu
(JDK modules, application JARs, dependencies)
        │
        ▼
Đọc byte mã lớp và phân tích class-file
        │
        ▼
Xây dựng và xử lý metadata của lớp
        │
        ▼
Nạp, liên kết, xác minh/phân giải khi cần
        │
        ▼
Khởi tạo lớp khi được sử dụng tích cực
(thực thi các phần <clinit> cần thiết)
        │
        ▼
Chạy mã ứng dụng, khởi tạo framework,
JIT warmup, I/O, mạng, truy vấn dữ liệu...
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết JVM luôn thực hiện từng bước theo một thứ tự tuyến tính đơn giản: JVM có thể nạp lớp theo nhu cầu (*lazy loading*), phân giải một số thứ về sau và tối ưu theo implementation.

Có một số chi phí khác nhau cần phân biệt:

| Chi phí | Hoạt động thường gặp | CDS/AppCDS có thể tác động? |
| --- | --- | --- |
| Tìm lớp | Xác định nguồn lớp từ JDK image, JAR, module/classpath, class loader | Có thể giảm công việc cho lớp phù hợp trong archive |
| Đọc `.class` | Truy cập tệp/JAR, nạp byte dữ liệu lớp | Có thể tránh đọc/giải mã lại một phần nhờ archive |
| Phân tích class file | Chuyển định dạng class-file thành cấu trúc JVM nội bộ | **Đây là một trong những lợi ích chính** |
| Tạo metadata | Tạo cấu trúc mô tả class, method, field, symbol... | Có thể dùng dữ liệu đã lưu trong archive |
| Xác minh, liên kết, phân giải | Kiểm tra, chuẩn bị và kết nối tham chiếu | Tùy giai đoạn, JDK và loại cache; không mặc định bỏ hết |
| Chạy `static { ... }` | Khởi tạo lớp khi Java yêu cầu | **Không bị CDS cổ điển bỏ qua chỉ vì lớp đã nằm trong archive** |
| Tạo object nghiệp vụ | `new`, dependency injection, bean initialization | Không được tự động cache toàn bộ |
| Thực hiện I/O, SQL, HTTP | Kết nối tài nguyên, network, filesystem | Không được CDS giải quyết trực tiếp |
| JIT compilation và warmup | Biên dịch đường chạy nóng, profiling | Khác mục tiêu chính của CDS truyền thống |

**Ý nghĩa:** Nếu thời gian khởi động chủ yếu tiêu tốn vào đọc/phân tích metadata của hàng nghìn lớp, CDS có thể giúp. Nếu thời gian khởi động chủ yếu chờ cơ sở dữ liệu, tải tài nguyên mạng hoặc thực thi logic nghiệp vụ đắt đỏ, CDS sẽ không tự loại bỏ các chi phí ấy.

## 3. CDS làm gì với dữ liệu lớp?

Về mặt khái niệm, cơ chế hoạt động gồm **hai thời điểm**.

### 3.1. Thời điểm tạo archive

HotSpot JVM chuẩn bị một tập lớp đã chọn và ghi dữ liệu có thể chia sẻ vào **CDS archive** (thường dùng phần mở rộng `.jsa` với quy trình truyền thống). Thông tin trong archive đã được tổ chức theo cách JVM có thể sử dụng nhanh hơn so với việc đọc và phân tích lại class file từ đầu.

Archive có thể được tạo:
- Khi xây dựng/phân phối JDK cho các lớp nền;
- Sau một lần chạy thử ứng dụng (*training run*) để ghi lại những lớp được dùng;
- Qua những cơ chế tạo archive thủ công hoặc tự động mà phiên bản JDK hỗ trợ.

### 3.2. Thời điểm chạy ứng dụng sau đó

Khi JVM mới khởi động và môi trường **tương thích với archive**, nó có thể **memory-map** archive rồi dùng lại thông tin lớp đã được lưu.

~~~text
Không tận dụng archive cho một lớp
    JAR/class bytes → đọc → parse → metadata → tiếp tục nạp

Có archive hợp lệ chứa lớp
    shared archive → ánh xạ metadata đã chuẩn bị → tiếp tục nạp
~~~

Việc dùng archive có thể giảm:
- Khối lượng đọc và phân tích class-file lặp lại;
- Một phần chi phí tạo metadata;
- Một phần vùng bộ nhớ native cho metadata trùng nhau giữa các JVM.

**Memory mapping** cho phép nhiều JVM trên cùng máy dùng chung những trang dữ liệu **read-only** của archive thông qua cơ chế quản lý bộ nhớ của hệ điều hành. Các JVM vẫn là **các process độc lập** với class initialization, heap và trạng thái ứng dụng của riêng chúng.

**Không cần sao chép toàn bộ archive vào heap Java**. Các vùng dữ liệu lớp chia sẻ thường nằm trong cơ chế bộ nhớ của VM và hệ điều hành, không phải một `HashMap` trong Java heap do ứng dụng trực tiếp quản lý.

### Một archive không phải “snapshot toàn bộ ứng dụng đã chạy”

CDS archive không phải bản chụp:
- Toàn bộ heap có các object nghiệp vụ đang sống;
- Kết nối database/socket;
- File descriptor;
- Thread hay kết quả HTTP;
- Trạng thái `static` mutable riêng của từng process;
- Mọi lớp có thể xuất hiện trong tương lai.

Dùng archive **không được thay đổi tính đúng đắn hoặc những tác dụng phụ cần thiết của chương trình**. Đặc biệt, `static initializer` không được xem là đã chạy xong trong mọi process chỉ vì metadata của class có trong CDS archive.

## 4. CDS nền và AppCDS khác nhau ở đâu?

| Nội dung | CDS nền | AppCDS |
| --- | --- | --- |
| Tập lớp mục tiêu | Chủ yếu lớp lõi/thư viện JDK | Mở rộng đến các lớp ứng dụng và dependency phù hợp |
| Nguồn dữ liệu | Archive được JDK cung cấp hoặc tạo theo cấu hình | Archive gắn với ứng dụng/classpath/module và workload huấn luyện |
| Mục tiêu | Giảm phần chi phí lớp nền thường xuất hiện trong nhiều ứng dụng | Giảm thêm chi phí startup khi ứng dụng dùng nhiều lớp riêng |
| Độ phụ thuộc deployment | Gắn chặt với JDK/VM phù hợp | Gắn với cả JDK và tập JAR/module ứng dụng |
| Cách kích hoạt trong JDK hiện đại | Thường sẵn có và bật mặc định | Tùy phiên bản và chiến lược archive/AOT của ứng dụng |
| Phù hợp nhiều JVM cùng host | Có | Có, nhất là khi nhiều JVM dùng chung tập lớp và archive hợp lệ |

**Mốc phát triển cần nhớ:**
- **CDS** có từ trước Java 10 và đã được cải tiến qua nhiều phiên bản.
- **JDK 10 / JEP 310:** đưa **Application Class-Data Sharing** vào HotSpot, mở rộng phạm vi từ các lớp nền sang lớp ứng dụng trên classpath.
- **JDK 12:** các bản phân phối Oracle JDK có **CDS archive mặc định được đóng gói sẵn** và thường sử dụng theo mặc định. Các JDK khác cũng có cơ chế CDS tương tự tùy distribution.
- **JDK 13:** thêm cách tạo **dynamic archive** bằng `-XX:ArchiveClassesAtExit`, làm việc học và triển khai AppCDS thuận tiện hơn quy trình thủ công class list.
- **JDK 24+:** xuất hiện **Ahead-of-Time (AOT) cache** hỗ trợ thêm khả năng tải/liên kết lớp trước khi chạy, xây dựng trên nền tảng CDS. Các JDK mới có công cụ AOT phong phú hơn và cần đọc tài liệu đúng phiên bản.
- **JDK 25+:** quy trình tạo AOT cache được đơn giản hóa; CDS/AppCDS truyền thống vẫn cần được hiểu khi đọc log và khi hệ thống sử dụng archive `.jsa`.

Không dùng một tài liệu Java 10 có option từng cần bật riêng như thể đó là lời khuyên tối ưu hóa duy nhất của JDK 25+. Bài tập dưới đây chọn **workflow dynamic CDS vẫn hiện hành trên JDK 17+** để minh họa bản chất của AppCDS.

## 5. CDS giảm những chi phí khởi động nào?

Hãy chia startup thành các phần ước lượng:

~~~text
Tổng startup (khái niệm)
  = JVM bootstrap
  + tìm/đọc/phân tích class
  + liên kết/khởi tạo class khi cần
  + khởi tạo thư viện/framework
  + tạo object + I/O + tác vụ ứng dụng
  + những chi phí khác
~~~

CDS chủ yếu nhắm tới **chi phí nạp và chuẩn bị dữ liệu lớp**; nếu phần này nhỏ so với tổng thời gian startup, tỷ lệ cải thiện tổng thể cũng có thể nhỏ.

### Mô hình tính minh họa, không phải số đo thực tế

Giả sử một startup theo **mô hình giả định** có:
- 120 ms xử lý metadata lớp có thể được archive giúp tối ưu;
- 280 ms khởi tạo ứng dụng, network, config và công việc khác;
- Tổng 400 ms.

Nếu cơ chế chia sẻ giúp tiết kiệm giả định **60 ms** của phần lớp:
- Startup mới trong mô hình: **340 ms**;
- Mức giảm thời gian toàn trình: **15%**.

Đây là **ví dụ số học để phân tích giới hạn**, không phải khẳng định JDK hay một ứng dụng nào đạt được 15%. Nếu ứng dụng thực tế dành phần lớn thời gian chờ mạng, lợi ích có thể thấp hơn; nếu bị chi phối bởi class loading, lợi ích có thể rõ hơn.

### CDS có tăng tốc mọi lượt gọi method không?

Không có bảo đảm như vậy. CDS truyền thống nhắm tới startup và metadata. Trong một chương trình chạy lâu, sau khi hệ thống đã khởi động và JIT tối ưu, **throughput ổn định** có thể gần như không đổi.

Đừng đánh đồng:
- **Startup time:** từ khi bắt đầu process đến mốc “ready”.
- **Warmup time:** thời gian tiến tới hiệu suất ổn định khi JVM profiling/JIT.
- **Steady-state throughput:** năng suất khi hệ thống đã ổn định.
- **First request latency:** độ trễ yêu cầu đầu tiên, có thể gồm lazy initialization.
- **Footprint:** dung lượng bộ nhớ được hạch toán, không chỉ mỗi Java heap.

CDS giúp một số phần của **startup** và **native footprint**; các mục khác cần benchmark và có thể cần tối ưu riêng.

## 6. Shared metadata, native memory và sự khác biệt với Java heap

Tại sao CDS có thể tiết kiệm bộ nhớ khi chạy nhiều JVM?

Khi không chia sẻ, mỗi JVM phải có những cấu trúc metadata riêng để biểu diễn các lớp giống nhau. Khi cùng dùng archive, những trang **read-only** tương thích có thể được **chia sẻ vật lý qua OS page mapping**. Vì vậy, nhiều process có thể tránh nhân bản một phần metadata.

Cần phân biệt:

| Thuật ngữ | Liên quan | Điều không nên hiểu nhầm |
| --- | --- | --- |
| **Java heap** | Object và mảng do chương trình tạo | CDS không chia sẻ toàn bộ heap giữa các process |
| **Metaspace / VM metadata** | Thông tin lớp/phương thức và dữ liệu VM | Một phần dữ liệu lớp phù hợp có thể được chuẩn bị/chia sẻ |
| **Shared archive** | Tệp chứa dữ liệu có thể map vào tiến trình | Không tương đương JAR, không là database ứng dụng |
| **RSS (resident set size)** | Các trang resident được tính cho mỗi process | Các trang share có thể xuất hiện trong RSS của nhiều process, không nên cộng RSS rồi coi là RAM vật lý duy nhất |
| **PSS (proportional set size)** | Chia tỷ lệ các trang share khi hạch toán | Hữu ích hơn để xem tổng footprint khi có nhiều JVM trên nền tảng hỗ trợ |
| **Heap committed/used** | Bộ nhớ heap do GC quản lý | Không phải thước đo toàn bộ phần CDS tiết kiệm |

Nếu một công cụ hệ điều hành báo RSS của từng JVM không giảm như dự kiến, **không vội kết luận CDS vô dụng**: memory-mapped shared pages, page cache và quy ước tính bộ nhớ có thể làm số liệu khó diễn giải.

Để đánh giá nhiều JVM chạy song song, cần quan sát đúng các chỉ số **private/shared memory** và tổng memory footprint của hệ thống.

## 7. Chương trình Java 17+ độc lập để minh họa CDS/AppCDS

Ta tạo một chương trình nhỏ, có một lớp lồng bên trong và **static initializer có side effect**. Điều này cho thấy: dùng archive có thể giúp nạp class metadata, **nhưng không được bỏ qua hành vi khởi tạo lớp cần thiết của ứng dụng**.

Tạo tệp **CdsStartupDemo.java**:

~~~java
public class CdsStartupDemo {

    static final class PriceCalculator {
        static {
            System.out.println("PriceCalculator initialized");
        }

        static int total(int unitPrice, int quantity) {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    public static void main(String[] args) {
        System.out.println("Application ready");
        int total = PriceCalculator.total(7, 3);
        System.out.println("total = " + total);
    }
}
~~~

Mẫu này chạy trên **JDK 17+** và không cần thư viện ngoài.

### 7.1. Biên dịch và đóng gói thành JAR

Trong thư mục chỉ chứa tệp nguồn của ví dụ, chạy:

~~~bash
mkdir build
javac --release 17 -d build CdsStartupDemo.java
jar --create --file=demo.jar --main-class=CdsStartupDemo -C build .
~~~

Cách dùng `-d build` tạo các class file trong thư mục tạm; lệnh `jar` đưa chúng vào **`demo.jar`** và khai báo `Main-Class` trong manifest.

**Vì sao đóng gói JAR?** Với quy trình CDS/AppCDS truyền thống, các lớp ứng dụng được chọn để archive thường cần nguồn JAR thích hợp, và **classpath có thư mục chứa class file không rỗng** có thể làm mất khả năng sử dụng archive của các lớp đó. Hãy ưu tiên JAR thay vì chạy trực tiếp `-cp build` khi làm bài thực hành AppCDS này.

Lệnh `mkdir build` được dùng trong thư mục mới để tránh đụng đến một thư mục `build` đã tồn tại của dự án khác. Trong dự án thật, dùng output path của build tool.

### 7.2. Chạy bình thường

~~~bash
java -jar demo.jar
~~~

**Đầu ra chương trình chính xác:**

~~~text
Application ready
PriceCalculator initialized
total = 21
~~~

Giải thích:
1. `main` in `Application ready`.
2. Lời gọi đầu tiên đến `PriceCalculator.total` là một thao tác yêu cầu khởi tạo lớp `PriceCalculator`.
3. `static { ... }` chạy và in `PriceCalculator initialized`.
4. `Math.multiplyExact(7,3)` trả `21`.

**Điểm quan trọng:** dòng `PriceCalculator initialized` cần xuất hiện **trong mỗi lần chạy process riêng biệt**. Việc một bản archive có metadata của `PriceCalculator` không biến `static` initialization thành kết quả dùng chung giữa các process.

## 8. Tạo dynamic CDS archive bằng `ArchiveClassesAtExit` (JDK 17+)

Quy trình đơn giản và vẫn có trong JDK hiện đại:

~~~text
Bước 1: Chạy thử ứng dụng bằng JAR
        │
        ▼
JVM quan sát những class được nạp trong lần chạy
        │
        ▼
Khi thoát bình thường, ghi dynamic archive phù hợp
        │
        ▼
Bước 2: Chạy lại cùng ứng dụng với archive
        │
        ▼
JVM có thể sử dụng metadata lớp từ archive
~~~

Tại thư mục của `demo.jar`, tạo archive tên `demo.jsa`:

~~~bash
java -XX:ArchiveClassesAtExit=demo.jsa -jar demo.jar
~~~

Đây là lệnh **chạy thật** chương trình rồi yêu cầu JVM ghi dynamic archive lúc kết thúc. Ngoài ba dòng của ứng dụng, JVM có thể phát sinh cảnh báo/log theo phiên bản, môi trường, cờ runtime và tình trạng archive.

**Yêu cầu:** 
- Chạy trên HotSpot JVM có hỗ trợ flag này (ví dụ JDK 17, 21 hoặc một JDK hiện đại phù hợp).
- Nguồn lớp ứng dụng đặt trong JAR thích hợp.
- Không đưa `-Xshare:off` vào lệnh tạo dynamic archive — đó là tùy chọn tắt CDS.
- Thực hiện với cùng tập JAR và cùng cấu hình launch mà bạn định dùng khi chạy lại.
- Thư mục được phép ghi `demo.jsa`, và **không tái sử dụng tên archive cũ không phù hợp** từ một lần build/JDK khác.

Nếu lệnh tạo archive thất bại, **không coi bước tiếp theo là đã có archive hợp lệ**. Xem stderr/log và điều kiện môi trường; không tự bỏ qua cảnh báo nghiêm trọng.

### 8.1. Chạy lại với archive

~~~bash
java -XX:SharedArchiveFile=demo.jsa -jar demo.jar
~~~

Với archive và classpath tương thích, HotSpot có thể dùng lại các lớp được lưu trong dynamic archive.

**Đầu ra từ mã ứng dụng vẫn là:**

~~~text
Application ready
PriceCalculator initialized
total = 21
~~~

Có thể có thêm **JVM diagnostic messages** nếu bật cờ logging hoặc cấu hình runtime có cảnh báo. Nội dung nghiệp vụ không đổi; việc có dùng CDS không phải phép thay đổi kết quả `main`.

### 8.2. Cách bảo đảm JAR không đổi

Với chương trình này, việc thay `demo.jar` **sau khi tạo archive** có thể khiến các lớp trong archive không còn dùng được. Nếu biên dịch lại hoặc cập nhật dependency:
- Xem archive cũ là **artifact gắn với bản ứng dụng cũ**.
- Tạo lại archive khi đổi JAR hoặc JDK cần thiết.
- Dùng một quy trình build/deploy tạo JAR trước, tạo archive sau, rồi deploy **cặp artifact tương thích**.
- Không phụ thuộc vào tên tệp giống nhau để khẳng định nội dung JAR không thay đổi.

Trong các ứng dụng lớn, có thể cần huấn luyện với những đường chạy đại diện để nhiều lớp quan trọng được nạp và có cơ hội được archive.

## 9. Kiểm tra xem có sử dụng shared archive không

**Chương trình chạy thành công không có nghĩa AppCDS chắc chắn đang được dùng.** HotSpot có thể không sử dụng một archive không tương thích hoặc chưa bao phủ lớp bạn mong muốn.

### 9.1. Unified Logging cho CDS

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=demo.jsa -jar demo.jar
~~~

Dùng để quan sát quá trình kiểm tra, map archive hoặc các sự kiện liên quan CDS. **Dòng log cụ thể phụ thuộc JDK/VM**, nên không đưa một bảng stdout tưởng tượng cho cờ này.

### 9.2. Theo dõi nguồn nạp lớp

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=demo.jsa -jar demo.jar
~~~

Trong log class loading, với những lớp thực sự lấy từ shared archive, có thể thấy phần nguồn có dạng:

~~~text
source: shared objects file
~~~

Một số JDK có thể bổ sung chú thích như vùng **base/top** hoặc các thông tin khác. Hãy tìm các lớp cụ thể như `CdsStartupDemo` và `CdsStartupDemo$PriceCalculator`, thay vì chỉ thấy lớp `java.lang.Object` rồi kết luận **mọi lớp ứng dụng** đã được archive.

**Chú ý:** các dòng JVM log **không phải stdout cố định của chương trình mẫu**. Cờ `-Xlog:class+load=info` có thể in rất nhiều dòng, ảnh hưởng thời gian đo startup. Dùng logging để **chẩn đoán**, rồi tắt logging khi benchmark hiệu năng.

### 9.3. Phân biệt ba trạng thái

| Trạng thái | Ý nghĩa |
| --- | --- |
| Không dùng CDS | Ví dụ chạy với `-Xshare:off` |
| Dùng CDS mặc định của JDK | Có thể dùng lớp nền, **chưa chắc đã dùng lớp ứng dụng** |
| Dùng AppCDS archive tùy chỉnh | Có cơ hội dùng thêm các lớp ứng dụng phù hợp đã archive |

**Kiểm tra bằng log nguồn nạp lớp**, không chỉ bằng câu “JVM đã bật CDS”.

## 10. So sánh thử nghiệm `-Xshare:off`, CDS mặc định và AppCDS

Để hiểu sự khác biệt, dùng **ba cấu hình**:

~~~bash
# A. Tắt CDS hoàn toàn (đối chứng kỹ thuật)
java -Xshare:off -jar demo.jar

# B. Sử dụng cơ chế CDS mặc định của JDK
java -jar demo.jar

# C. Sử dụng dynamic archive của ứng dụng
java -XX:SharedArchiveFile=demo.jsa -jar demo.jar
~~~

**Cả ba nên cho cùng kết quả nghiệp vụ:**

~~~text
Application ready
PriceCalculator initialized
total = 21
~~~

Nhưng chi phí nạp lớp **có thể khác**. Sự khác biệt không được quyết định từ stdout; cần đo độc lập.

### Tại sao cần ba cấu hình?

Nếu chỉ so sánh **tắt mọi CDS** với **AppCDS**, phần cải thiện quan sát được có thể đến từ:
- CDS của các lớp nền JDK;
- AppCDS của lớp ứng dụng;
- Sự kết hợp hai phần.

Để đánh giá **lợi ích riêng của AppCDS**, cấu hình **B (CDS nền bật)** so với **C (CDS nền + archive ứng dụng)** thường có giá trị hơn. A hữu ích như đối chứng toàn hệ thống nhưng **không tách riêng đóng góp AppCDS**.

### Không dùng `-Xshare:on` làm mặc định production

Các chế độ quan trọng:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-Xshare:off` | Tắt CDS, phục vụ so sánh/chẩn đoán |
| `-Xshare:auto` | Sử dụng CDS khi có thể; là hành vi mặc định phổ biến của JDK hiện đại |
| `-Xshare:on` | Yêu cầu bắt buộc dùng archive; **có thể khiến JVM dừng nếu archive không sử dụng được** |

**Oracle khuyến cáo `-Xshare:on` cho mục đích kiểm thử**, không làm cờ mặc định production, vì khi archive không hợp lệ hoặc không tương thích, VM có thể thoát ở giai đoạn khởi động. Với production, dùng mặc định hoặc `-Xshare:auto` theo hướng dẫn của JDK cụ thể, theo dõi cảnh báo và có quy trình tái tạo archive.

## 11. Đo startup đúng thay vì dự đoán lợi ích

### 11.1. Chọn mốc thời gian có ý nghĩa

Với **CLI ngắn**, có thể đo tổng thời gian từ gọi launcher đến process thoát. Với **dịch vụ web**, thường quan tâm:
- Thời gian từ khi process được tạo đến khi ứng dụng báo **ready**;
- Thời gian đến **request đầu tiên thành công**;
- Mốc readiness trong orchestrator/container;
- Bộ nhớ khi có nhiều instance cùng hoạt động.

CDS có thể giúp **startup-to-ready**, nhưng không tự giảm độ trễ phụ thuộc network/database trong mọi tình huống.

### 11.2. Quy trình benchmark khuyến nghị

1. Dùng **cùng một JDK build, cùng JAR, cùng classpath/module path** cho các lượt so sánh.
2. Tạo archive **trước** khi đo, không tính thời gian training/dump vào mỗi lần startup runtime (trừ khi bài toán triển khai thực sự yêu cầu).
3. Thử **A/B/C** với cùng biến môi trường, JVM options, GC, heap và workload.
4. Chạy nhiều lần; ghi **median, percentiles và biến thiên** thay vì chọn một lần đẹp nhất.
5. Tách tác động của **OS page cache**, CPU frequency scaling, tải nền và container resource limits.
6. Không bật verbose class logging trong lượt benchmark chính, vì log có thể tự làm chậm quá trình khởi động.
7. Đo **từ bên ngoài process** nếu quan tâm startup toàn trình; đồng hồ bắt đầu ở đầu `main` sẽ bỏ qua đáng kể công việc trước đó.
8. Với ứng dụng framework, training phải đi qua đường khởi động và tính năng đại diện; các lớp chỉ được lazy-load trong request sau có thể không vào archive.
9. Kiểm tra từ log rằng archive được sử dụng, nhưng thực hiện việc xác thực **tách khỏi lượt đo thời gian**.
10. Khi so sánh memory footprint nhiều JVM, đo **PSS/private pages hoặc số liệu tương đương**, không chỉ cộng RSS.

### Ví dụ đo thời gian bằng công cụ hệ điều hành

Với shell có lệnh `/usr/bin/time`:

~~~bash
/usr/bin/time -p java -jar demo.jar
/usr/bin/time -p java -XX:SharedArchiveFile=demo.jsa -jar demo.jar
~~~

Các số `real`, `user`, `sys` là **dữ liệu đo trên máy đang chạy**, không có một stdout hiệu năng chuẩn. Ở hệ điều hành khác, dùng công cụ đo tương đương (ví dụ PowerShell `Measure-Command`) với cùng quy trình.

**Quan trọng:** chương trình ví dụ quá nhỏ nên nhiễu đo có thể lấn át lợi ích. Không nên suy từ 1–2 lượt chạy của lớp `PriceCalculator` rằng mọi ứng dụng Spring Boot, server hoặc CLI sẽ đạt cùng tỷ lệ cải thiện.

## 12. Class loading, linking và initialization: CDS không xóa hết ba giai đoạn

Java định nghĩa các khái niệm chính:
- **Loading:** tìm và tạo representation của class hoặc interface từ nguồn dữ liệu.
- **Linking:** gồm xác minh, chuẩn bị và phân giải, với một phần xử lý có thể xảy ra theo nhu cầu.
- **Initialization:** thực thi các bước khởi tạo lớp khi những điều kiện được Java quy định xảy ra; có thể bao gồm `static { ... }` và khởi tạo static fields không phải hằng số compile-time.

CDS truyền thống **có thể rút ngắn** một số thao tác loading/metadata nhưng **không được dùng làm lý do để bỏ qua ngữ nghĩa initialization**.

Xét trong bài thực hành:

~~~java
static final class PriceCalculator {
    static {
        System.out.println("PriceCalculator initialized");
    }

    static int total(int unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
~~~

Đây là đoạn minh họa, không phải tệp độc lập.

Dù `PriceCalculator` có thể được lấy từ archive khi chạy, việc gọi `PriceCalculator.total(...)` lần đầu vẫn phải tuân thủ **semantics khởi tạo lớp**. Archive không phải một lần chạy `static initializer` thay cho tất cả lần chạy tiếp theo.

### Phân biệt với AOT class loading/linking

Bắt đầu ở **JDK 24 (JEP 483)**, AOT cache cho phép lưu **trạng thái lớp đã nạp và liên kết** ở mức sâu hơn so với CDS truyền thống. Đây là một bước phát triển mới hơn, không nên mô tả CDS Java 10 như thể nó đã có đầy đủ mọi tối ưu hóa AOT sau này.

Ngay cả AOT cache hiện đại cũng có **quy tắc tương thích/huấn luyện** và không tự cho phép bỏ qua những tác dụng phụ nghiệp vụ cần thiết của chương trình. Khi nghiên cứu JDK 24/25/26+, hãy xem tài liệu AOT đúng phiên bản thay vì ngoại suy từ các flag Java 10.

## 13. Những điều AppCDS không tự giải quyết

### 13.1. Không bỏ qua khởi tạo dependency injection/framework

Spring, Jakarta EE, logging, serialization, ORM và các framework khác có thể phải:
- Đọc configuration;
- Quét annotation và phản chiếu;
- Tạo bean/object graph;
- Mở connection pool;
- Đọc metadata cơ sở dữ liệu;
- Khởi tạo cache nghiệp vụ.

AppCDS có thể giảm một phần chi phí nạp lớp, nhưng **không tự biến toàn bộ framework initialization thành kết quả có sẵn từ archive**. Một bản JDK mới với AOT cache hoặc framework AOT có thể bổ sung tối ưu khác; cần phân biệt chúng với AppCDS cơ bản.

### 13.2. Không tự làm JIT warmup biến mất

HotSpot JVM có thể cần thu thập profiling và biên dịch mã nóng khi ứng dụng hoạt động. CDS truyền thống không phải bản cache tổng quát cho **mọi machine code JIT đã biên dịch**.

Các cải tiến JDK mới có thể lưu thêm dạng AOT khác; hãy đánh giá **startup và warmup riêng**.

### 13.3. Không tự chia sẻ object nghiệp vụ trong heap

Một Java object như `new Customer(...)` được tạo ở process A không trở thành cùng object dùng được ở process B vì cả hai có cùng archive. Sự chia sẻ chính liên quan dữ liệu lớp/VM phù hợp, không phải chia sẻ mutable application heap.

### 13.4. Không nhất thiết mang lợi ích lớn cho mọi ứng dụng

Một CLI sử dụng ít lớp có thể cải thiện phần khởi động JDK; một dịch vụ lớn có nhiều lớp có thể tận dụng AppCDS tốt hơn; nhưng mức tăng thực **phải đo** theo workload.

### 13.5. Không thay thế cấu hình đúng phiên bản hoặc bảo mật

CDS archive được xây cho một tổ hợp JDK, JAR/classpath và các điều kiện runtime. Không dùng archive cũ như cách “chạy mã mới bằng class metadata cũ”. Các cơ chế tương thích phải được JVM kiểm tra và ứng dụng cần một quy trình build/deploy nhất quán.

## 14. Điều kiện tương thích và giới hạn triển khai

Một archive CDS/AppCDS **không phải artifact Java phổ quát chạy được trên mọi phiên bản JDK**.

### 14.1. Gắn với JDK build và môi trường

Khi đổi:
- JDK distribution/build/patch;
- Kiến trúc hoặc điều kiện của VM;
- Các cờ VM ảnh hưởng tới cấu trúc dữ liệu;
- Artifact JAR, classpath hoặc module path;

archive có thể **không dùng được, bị vô hiệu một phần, hoặc phải tạo lại**. Không thiết kế pipeline chỉ dựa vào “cùng feature number 17” để quyết định archive chắc chắn tương thích.

**Thực hành:** luôn tạo archive trong môi trường **phù hợp deployment**, và có cơ chế tái tạo nó khi thay ứng dụng hoặc JDK.

### 14.2. JAR và classpath nhất quán

Trong quy trình CDS/AppCDS truyền thống với classpath:
- Nguồn lớp ứng dụng để archive nên là **JAR**, không phải các thư mục class đã giải nén.
- Classpath dùng khi tạo archive phải phù hợp với classpath runtime theo hợp đồng của HotSpot.
- Thay đổi JAR sau khi tạo archive có thể làm các lớp trong archive **không còn được sử dụng**.
- Module path, VM options và các mô hình class loader tùy biến có thể tạo thêm điều kiện.

**Không có nghĩa mọi custom class loader đều không bao giờ hỗ trợ CDS**; khả năng hỗ trợ đã được mở rộng theo phiên bản JDK, nhưng từng kiểu class loader/đường nạp lớp cần xem hướng dẫn đúng runtime.

### 14.3. Archive cần được bảo vệ

CDS archive chứa dữ liệu nội bộ để JVM tiêu thụ và có quan hệ chặt chẽ với phiên bản VM. Chỉ tạo, phân phối và nạp archive từ **nguồn đáng tin cậy**:
- Giới hạn quyền ghi vào archive trong production;
- Không cho đầu vào không tin cậy tùy ý chọn tệp `.jsa` để JVM nạp;
- Tách build artifact với thư mục người dùng có thể chỉnh sửa;
- Không coi một checksum không có cơ chế xác thực mạnh là bằng chứng về nguồn gốc an toàn.

Lệnh `-XX:+VerifySharedSpaces` có thể dùng để kiểm tra một dạng tính toàn vẹn dữ liệu archive theo tài liệu JVM, nhưng **không thay thế xác thực provenance hoặc chính sách quyền truy cập**.

### 14.4. Training workload quyết định tập lớp được lưu

Nếu bạn tạo archive khi ứng dụng chỉ chạy một nhánh “hello”, những lớp chỉ tải ở request ít gặp có thể không được ghi vào archive. Vì vậy:
1. Chọn workload huấn luyện đại diện cho **đường khởi động và tác vụ đầu tiên**.
2. Chạy đầy đủ những thành phần hợp pháp cần tối ưu.
3. Không đưa tác vụ production có tác dụng phụ nguy hiểm vào môi trường training thật.
4. Kiểm tra archive có các lớp quan trọng, bằng log hoặc công cụ diagnostic.
5. Tái tạo sau khi đổi code/dependency.

Archive chứa **những lớp có thể archive theo giới hạn VM**, không phải mọi lớp từng hiện diện trong tất cả các đường chạy.

## 15. AppCDS truyền thống và AOT cache trên JDK mới

CDS và AppCDS vẫn là **kiến thức nền cần thiết**, nhưng nếu mục tiêu của dự án là **tối ưu startup trên JDK 24+**, nên biết một cơ chế mới hơn: **Ahead-of-Time (AOT) cache**.

| Nền tảng | Khái niệm quan trọng | Lưu ý |
| --- | --- | --- |
| Java 10 | AppCDS (JEP 310) mở rộng archive đến application classes | Mốc lịch sử để hiểu bản chất |
| Java 17/21 | CDS nền + dynamic AppCDS archives, các tùy chọn `ArchiveClassesAtExit`, `SharedArchiveFile` | Workflow trong mục 8 có thể áp dụng |
| Java 24 | AOT class loading/linking (JEP 483) | Cache có khả năng lưu trạng thái loaded/linked sâu hơn |
| Java 25+ | Quy trình tạo AOT cache thuận tiện hơn (JEP 514) và các tối ưu tiếp theo | Cần dùng tài liệu đúng phiên bản |

Trên **JDK 25+**, một workflow AOT được tài liệu hỗ trợ là:

~~~bash
java -XX:AOTCacheOutput=demo.aot -jar demo.jar
java -XX:AOTCache=demo.aot -jar demo.jar
~~~

**Đây là ví dụ cho JDK 25+**, không phải cú pháp dành cho JDK 17. Tùy JDK mới hơn, thông số cụ thể và điều kiện tạo cache có thể thay đổi; hãy xem **`java` launcher manual** của phiên bản đang triển khai.

**Đừng đồng nhất hai tệp:**
- `demo.jsa`: archive CDS/AppCDS truyền thống;
- `demo.aot`: artifact **AOT cache** theo cơ chế JDK mới.

Đối với dự án đang chạy JDK 17 hoặc 21, cách dùng dynamic AppCDS truyền thống vẫn là chủ đề thực tế và hợp lệ. Đối với dự án JDK 25+, AOT cache có thể cho lợi ích rộng hơn, nhưng **vẫn cần benchmark** và kiểm tra tính tương thích.

## 16. Các lỗi/hiểu lầm phổ biến

### Lỗi 1 — “CDS lưu luôn toàn bộ object và trạng thái ứng dụng”

Sai. CDS chủ yếu chia sẻ **dữ liệu lớp/metadata phù hợp của VM**. Object nghiệp vụ, socket, thread và trạng thái mutable của process không tự biến thành tài nguyên chung.

### Lỗi 2 — “Có CDS thì Java không cần class loading nữa”

Sai. JVM vẫn phải có **ngữ nghĩa loading/linking/initialization** theo Java. CDS giảm một phần **chi phí** cho những lớp có thể lấy từ archive, không làm mọi thao tác mất hẳn.

### Lỗi 3 — “Các `static {}` đã chạy lúc tạo archive, nên lúc chạy lại không cần”

Sai với CDS truyền thống. Khởi tạo lớp vẫn tuân theo quy tắc Java; chương trình mẫu cho thấy `PriceCalculator initialized` phải xuất hiện ở mỗi process.

### Lỗi 4 — “Bật CDS mặc định đồng nghĩa mọi class ứng dụng nằm trong archive”

Sai. CDS nền của JDK và AppCDS cho application classes là hai phạm vi khác nhau. Cần tạo archive phù hợp và xác minh bằng log nguồn nạp lớp.

### Lỗi 5 — “`-Xshare:on` luôn là cờ tốt nhất cho production”

Không. Theo tài liệu Oracle, `-Xshare:on` có thể làm JVM **dừng khởi động** nếu archive không hợp lệ; nó chủ yếu phục vụ kiểm thử. Dùng chế độ cho phép fallback phù hợp trong môi trường production.

### Lỗi 6 — “Có thể dùng archive tạo từ mọi JDK và mọi phiên bản JAR”

Sai. Archive phụ thuộc môi trường JVM và tập lớp. Khi JDK/JAR/classpath thay đổi, cần kiểm tra tương thích và thường tạo lại.

### Lỗi 7 — “Cứ chạy bằng thư mục `build/classes` là có AppCDS giống JAR”

Không thể giả định với quy trình archive truyền thống. Hướng dẫn AppCDS của JDK có giới hạn đối với **non-empty directories** trong classpath/module path. Bài thực hành dùng **JAR** để tránh lỗi này.

### Lỗi 8 — “Có file `.jsa` nghĩa là JVM đang dùng nó”

Sai. Archive có thể bị từ chối hoặc bỏ qua. Cần xem `-Xlog:cds`, `-Xlog:class+load` và đối chiếu lớp cụ thể.

### Lỗi 9 — “Một lần đo nhanh hơn 10% chứng minh AppCDS luôn nhanh hơn 10%”

Sai. Phải đo nhiều lượt, kiểm soát nhiễu và so sánh CDS nền với AppCDS. Tỷ lệ cải thiện phụ thuộc ứng dụng, JDK, OS và workload.

### Lỗi 10 — “RSS cao nghĩa là CDS không tiết kiệm RAM”

Không nhất thiết. Các trang memory-mapped dùng chung có thể tính vào RSS của nhiều process. Khi có nhiều JVM, nên quan sát PSS/private/shared pages.

### Lỗi 11 — “AppCDS tăng throughput và giảm JIT warmup giống một native image”

Không có bảo đảm. CDS truyền thống nhắm tới startup và metadata; AOT cache trên JDK mới có phạm vi tối ưu mở rộng. Chúng không đồng nghĩa native compilation toàn bộ ứng dụng.

### Lỗi 12 — “Đo thời gian trong `main` là đủ cho startup toàn trình”

Không. Khi `main` bắt đầu, JVM đã trải qua nhiều thao tác khởi động và nạp lớp. Muốn đo process startup-to-ready, đo từ bên ngoài hoặc từ công cụ runtime thích hợp.

### Lỗi 13 — “Training càng dài thì archive chắc chắn càng tốt”

Không hẳn. Archive chỉ nên bao phủ những lớp có ích; tập lớn không phù hợp có thể tăng chi phí lưu trữ/deploy. Cần đo và xác định những lớp thực sự ảnh hưởng startup.

### Lỗi 14 — “Nên bỏ qua CDS vì JDK đã có AOT cache”

Không. CDS là nền tảng của nhiều cải tiến và vẫn hiện diện trong hệ sinh thái JDK. Trên JDK 25+, AOT cache có thể là lựa chọn tốt hơn cho một số mục tiêu, nhưng code/config hiện hữu vẫn cần hiểu cơ chế CDS.

### Lỗi 15 — “CDS là tiêu chuẩn bảo đảm mọi JVM vendor hỗ trợ mọi `-XX` flag”

Không. Các tùy chọn như `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, `-Xlog:cds` thuộc hệ sinh thái HotSpot và cần kiểm tra JDK/runtime cụ thể. Không tự tuyên bố mọi implementation Java SE đều có cùng flag.

## 17. Checklist áp dụng AppCDS đúng cách

1. **Dùng JDK phù hợp:** kiểm tra `java --version`, distribution và flags được hỗ trợ.
2. **Có JAR của ứng dụng:** đóng gói những lớp/dependency dùng cho training.
3. **Xác định đối chứng:** đo chế độ CDS off, CDS nền và AppCDS riêng rẽ.
4. **Chọn training workload đại diện:** làm cho những lớp quan trọng thực sự được tải.
5. **Tạo archive trong môi trường hợp lệ:** đủ quyền ghi và không có lỗi nghiêm trọng.
6. **Không thay JAR/JDK tùy ý sau khi dump:** archive là artifact phụ thuộc phiên bản.
7. **Kiểm chứng việc sử dụng archive:** log `class+load` và `cds` ở một lượt chẩn đoán riêng.
8. **Kiểm tra tính đúng đắn:** stdout/hành vi nghiệp vụ phải giữ nguyên, kể cả static initialization.
9. **Đo startup nhiều lượt:** median/percentiles, readiness và first request khi phù hợp.
10. **Đo bộ nhớ đúng chỉ số:** private/shared pages, PSS nếu có nhiều JVM.
11. **Không dùng `-Xshare:on` tùy tiện trong production:** chuẩn bị phương án fallback/tái tạo archive.
12. **Giữ archive an toàn:** chỉ nạp từ nguồn tin cậy, giới hạn quyền sửa tệp.
13. **Tái tạo khi đổi build:** đưa archive vào quy trình CI/CD có versioning thích hợp.
14. **Xem xét AOT cache khi dùng JDK 25+:** không giới hạn tư duy tối ưu vào flag của thời Java 10.
15. **Không báo cáo số tăng tốc khi chưa đo:** CDS chỉ là một yếu tố trong tổng chi phí khởi động.

## 18. Câu hỏi tự kiểm tra

**Câu 1. CDS là gì?**

**Đáp án:** *Class Data Sharing* là cơ chế HotSpot dùng shared archive để lưu dữ liệu lớp đã chuẩn bị, giúp giảm một phần chi phí nạp lớp và chia sẻ metadata read-only giữa các JVM tương thích.

**Câu 2. AppCDS khác CDS nền ở điểm nào?**

**Đáp án:** AppCDS mở rộng phạm vi chia sẻ sang những lớp ứng dụng/dependency phù hợp, không chỉ lớp lõi của JDK.

**Câu 3. AppCDS được giới thiệu ở JDK nào?**

**Đáp án:** **JDK 10**, qua **JEP 310**. Các cách tạo archive và AOT đã được mở rộng trong JDK về sau.

**Câu 4. Tại sao CDS có thể cải thiện startup?**

**Đáp án:** Vì JVM có thể dùng dữ liệu lớp đã chuẩn bị trong archive, tránh lặp lại một phần thao tác đọc/phân tích class file và tạo metadata.

**Câu 5. Có phải class có trong archive thì `static {}` chỉ chạy một lần cho mọi JVM?**

**Đáp án:** Không. Mỗi process vẫn phải thực hiện khởi tạo lớp theo ngữ nghĩa Java.

**Câu 6. AppCDS có tự chia sẻ toàn bộ heap giữa hai JVM không?**

**Đáp án:** Không. Chủ yếu chia sẻ các vùng metadata/read-only phù hợp qua OS memory mapping.

**Câu 7. Trên JDK 17+, cờ nào có thể dùng tạo dynamic CDS archive sau lần chạy thử?**

**Đáp án:** `-XX:ArchiveClassesAtExit=demo.jsa` khi chạy JAR phù hợp.

**Câu 8. Cờ nào yêu cầu JVM sử dụng một archive đã tạo?**

**Đáp án:** `-XX:SharedArchiveFile=demo.jsa`, theo điều kiện tương thích của HotSpot.

**Câu 9. Làm sao kiểm tra một lớp được lấy từ archive thay vì đọc từ JAR?**

**Đáp án:** Xem log `-Xlog:class+load=info`, tìm lớp đó cùng phần nguồn chứa `shared objects file`; có thể xem thêm `-Xlog:cds=info`.

**Câu 10. Vì sao không nên dùng `-Xshare:on` cho production một cách mặc định?**

**Đáp án:** Khi archive không dùng được, cờ này có thể làm JVM thoát khi startup; Oracle khuyến cáo chủ yếu cho kiểm thử.

**Câu 11. Nếu so sánh AppCDS với `-Xshare:off` thì có đánh giá đúng lợi ích riêng của AppCDS không?**

**Đáp án:** Chưa chắc. Vì bạn đồng thời loại bỏ lợi ích CDS nền. Để tách đóng góp AppCDS, so sánh CDS mặc định và CDS có archive ứng dụng.

**Câu 12. Tại sao không nên đo startup chỉ từ đầu `main`?**

**Đáp án:** Nhiều công việc khởi động JVM và nạp class diễn ra **trước** lúc `main` chạy. Hãy đo từ bên ngoài process hoặc mốc readiness thực.

**Câu 13. Vì sao archive có thể không dùng được sau khi cập nhật JDK hoặc JAR?**

**Đáp án:** Dữ liệu archive được tạo cho một tổ hợp cụ thể của JDK, VM options và các class artifacts. Thay đổi có thể làm mất tương thích.

**Câu 14. CDS có bảo đảm giảm 20% startup cho mọi ứng dụng không?**

**Đáp án:** Không. Mức lợi ích tùy tỉ trọng chi phí nạp lớp và điều kiện thực tế. Cần benchmark nhiều lượt, không dùng phần trăm giả định làm kết luận đo đạc.

**Câu 15. JDK 24/25 đã bổ sung điều gì vượt CDS truyền thống?**

**Đáp án:** AOT cache, bắt đầu với **JEP 483** để lưu trạng thái lớp đã nạp và liên kết sâu hơn; JDK 25 cải thiện quy trình tạo và các tối ưu liên quan. Tùy chọn/giới hạn cần kiểm tra theo đúng phiên bản.

## 19. Ghi nhớ cuối bài

1. **CDS chia sẻ dữ liệu lớp đã chuẩn bị**, giảm một phần chi phí startup và metadata giữa các JVM tương thích.
2. **AppCDS (Java 10, JEP 310)** đưa lợi ích sang các lớp ứng dụng/dependency, không chỉ JDK core classes.
3. **Dữ liệu lớp không phải trạng thái chương trình**: class initialization, object creation, framework startup, I/O và JIT vẫn có các chi phí/semantics riêng.
4. Từ **JDK 12**, CDS nền thường sẵn có; **JDK 13+** có dynamic archive thông qua `ArchiveClassesAtExit`, dùng được cho bài tập **JDK 17+**.
5. **Xác minh bằng log**, không suy đoán chỉ vì có `.jsa` hoặc chương trình chạy bình thường.
6. **Đo đúng phần muốn cải thiện**: so sánh CDS mặc định với AppCDS, kiểm soát JAR/JDK, benchmark nhiều lần.
7. **Không coi RSS riêng lẻ là RAM bị nhân bản**, vì có read-only shared pages; dùng số liệu shared/private/PSS phù hợp.
8. **Archive gắn với JDK và artifact**, phải bảo vệ quyền truy cập và tái tạo khi môi trường thay đổi.
9. **JDK 24/25+ mở rộng hướng tối ưu với AOT cache**; hiểu CDS là nền tảng, và dùng workflow tối ưu đúng JDK đang triển khai.

**Tài liệu tham khảo chính thức, còn áp dụng:**
- [Oracle Java SE 17 — `java` command, Application Class Data Sharing, dynamic archive](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#application-class-data-sharing).
- [Oracle Java SE 25 — `java` command, AppCDS và AOT cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing).
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html).
- [OpenJDK — JEP 310: Application Class-Data Sharing](https://openjdk.org/jeps/310).
- [OpenJDK — JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483).
- [OpenJDK — JEP 514: Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514).
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/cps-appcds/).
