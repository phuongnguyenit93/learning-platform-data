# Chế độ `-Xshare:off` để tạo phép đo đối chứng khi vận hành AppCDS (Java 10+)

## 1. Mục tiêu và kết luận quan trọng nhất

**Application Class-Data Sharing (AppCDS)** là một khả năng của HotSpot JVM cho phép sử dụng những dữ liệu lớp đã được chuẩn bị trong một shared archive, giúp giảm một phần chi phí nạp lớp và có thể cải thiện thời gian khởi động hoặc mức tiêu thụ bộ nhớ của các JVM có cùng dữ liệu lớp. AppCDS được giới thiệu trong **JDK 10 qua JEP 310**; cơ chế CDS nền có từ trước và được tiếp tục cải tiến trong các JDK sau.

Nếu muốn biết CDS/AppCDS **thực sự đem lại lợi ích bao nhiêu**, trước hết phải có phép đo đối chứng. Tùy chọn:

~~~bash
java -Xshare:off -jar app.jar
~~~

được HotSpot dùng để **không sử dụng class data sharing** trong lần chạy đó. Đây là cấu hình đối chứng quan trọng, vì nó loại bỏ lợi ích của **cả shared archive nền của JDK lẫn AppCDS archive tùy chỉnh**.

**Nhưng:** `-Xshare:off` **không chỉ tắt riêng AppCDS**. Do đó, nếu lấy chênh lệch giữa một lần chạy `-Xshare:off` và một lần chạy với AppCDS rồi tuyên bố toàn bộ phần chênh là do *các lớp ứng dụng* được chia sẻ, bạn đã **gộp cả lợi ích của CDS nền**.

Để đánh giá rõ hơn, hãy phân biệt **ba cấu hình**:
1. **A — CDS OFF:** `-Xshare:off` để đo khi không dùng shared class data.
2. **B — CDS mặc định:** `-Xshare:auto` (hoặc để JVM dùng mặc định) nhưng **không chỉ định archive AppCDS riêng**.
3. **C — CDS + AppCDS:** dùng cùng JDK và cùng ứng dụng với **dynamic application archive** đã tạo và được xác nhận sử dụng.

Khi các điều kiện khác được giữ nhất quán:
- **A so với B** giúp nhận diện lợi ích của CDS nền.
- **B so với C** là so sánh phù hợp hơn để đánh giá phần đóng góp bổ sung của AppCDS.
- **A so với C** phản ánh lợi ích **kết hợp** của CDS nền và AppCDS; không được gán trọn chênh lệch này cho riêng ứng dụng.

Bài học thuộc nhóm **Vận hành AppCDS**, đi sâu vào cách dùng `-Xshare:off` cho benchmark thực tế, xác minh JVM đã tắt CDS, tránh các biến nhiễu và đọc đúng ý nghĩa số đo. Ví dụ chạy độc lập trên **JDK 17+**, đồng thời nêu rõ khác biệt với **AOT cache của những JDK hiện đại**.

## 2. CDS/AppCDS nhắm đến chi phí nào?

Một lần khởi động JVM bao gồm nhiều công việc:

~~~text
Tạo Java process
    │
    ▼
JVM bootstrap / runtime initialization
    │
    ▼
Tìm class, đọc class/JAR, parse và chuẩn bị metadata
    │
    ▼
Loading / linking / initialization khi cần
    │
    ▼
Khởi tạo framework, tạo object, I/O, network, database...
    │
    ▼
Ứng dụng đạt trạng thái sẵn sàng / trả request đầu tiên
~~~

Đây chỉ là **mô hình khái niệm**; trong thực tế các class có thể được nạp lười (*lazy loading*) và các bước chuẩn bị không nhất thiết tuyến tính như sơ đồ.

CDS/AppCDS hướng tới việc tận dụng **dữ liệu lớp đã chuẩn bị** từ archive. Những lớp có thể dùng archive không cần thực hiện lại toàn bộ một số công việc như đọc và phân tích class file, tạo một phần metadata theo cách thông thường.

Tuy nhiên, CDS truyền thống **không loại bỏ**:
- Việc khởi tạo lớp theo ngữ nghĩa Java; các `static initializer` cần chạy ở mỗi process vẫn chạy.
- Khởi tạo dependency injection, framework, configuration, các object nghiệp vụ.
- Network/database latency, đọc dữ liệu đầu vào của ứng dụng.
- JIT compilation hoặc quá trình warmup toàn bộ ứng dụng.
- Mọi thao tác nạp lớp, vì có thể có lớp không nằm trong archive hoặc không dùng được archive.

Vì vậy, một benchmark đáng tin phải đo **startup hoặc tài nguyên theo mốc nghiệp vụ**, thay vì cho rằng mọi chênh lệch đều đến từ một lớp cụ thể.

### Kích thước hiệu quả phụ thuộc workload

Nếu một CLI nhỏ chủ yếu chạy `main` trong thời gian rất ngắn, lợi ích CDS có thể đáng chú ý so với tổng runtime. Nếu một dịch vụ mất nhiều giây đợi database, phần tiết kiệm vài chục mili giây ở class loading có thể bị che khuất.

Không có một tỷ lệ phần trăm tăng tốc **được JDK bảo đảm** cho mọi ứng dụng. Chỉ báo cáo con số sau khi đo bằng các điều kiện thực tế.

## 3. Tùy chọn `-Xshare`: `off`, `auto`, `on`

Theo tài liệu `java` launcher của HotSpot, ba chế độ phổ biến là:

| Tùy chọn | Hành vi | Dùng khi nào |
| --- | --- | --- |
| `-Xshare:off` | **Không cố gắng sử dụng shared class data** | Phép đo đối chứng, chẩn đoán ảnh hưởng CDS |
| `-Xshare:auto` | Dùng archive nếu có thể, thường là mặc định | Chạy thông thường, đo trường hợp CDS mặc định |
| `-Xshare:on` | **Yêu cầu** archive được sử dụng; nếu không thể có thể thoát với lỗi | Kiểm thử tính hợp lệ/tương thích của archive |

**Lưu ý production:** Oracle ghi rõ `-Xshare:on` chủ yếu dành cho **testing**, không nên dùng bừa làm mặc định production: một archive không phù hợp có thể khiến JVM **không khởi động được**. Với production, thường để `auto` hoặc cấu hình được khuyến nghị cho đúng phiên bản/distribution, và kiểm tra log để biết hiệu quả thực tế.

**`-Xshare:off` không phải một “chế độ máy chậm” giả lập.** Nó đơn giản loại bỏ việc sử dụng dữ liệu lớp đã chia sẻ. Nó không giảm CPU quota, không tắt JIT, không đổi GC, không giới hạn bộ nhớ và không mô phỏng điều kiện network chậm.

### Tại sao `-Xshare:off` khác với “không có archive ứng dụng”?

Một JDK hiện đại thường có **base CDS archive** chứa lớp lõi của JDK. Khi chạy:

~~~bash
java -jar app.jar
~~~

HotSpot có thể dùng **archive mặc định** dù bạn không truyền `-XX:SharedArchiveFile=...`.

Vì thế câu “chạy không có flag AppCDS” không có nghĩa là **CDS đã tắt**. Còn:

~~~bash
java -Xshare:off -jar app.jar
~~~

mới là cấu hình **CDS off** rõ ràng.

**Đừng gắn `-Xshare:off` vào lệnh tạo dynamic archive** kiểu `-XX:ArchiveClassesAtExit` để mong JVM vừa tắt chia sẻ vừa tạo archive động như bình thường. Hãy tạo archive ở lượt training riêng, rồi dùng `-Xshare:off` trong **lượt baseline** riêng. Mặc dù `-Xshare:off` có thể xuất hiện trong một số quy trình cũ để **thu danh sách class bằng `-XX:DumpLoadedClassList`**, đó là một bước thu dữ liệu khác với việc dùng archive trong runtime.

## 4. Phân biệt chính xác ba câu hỏi của benchmark

**Câu hỏi A: CDS nói chung có ích cho ứng dụng không?**  
So sánh **A = CDS off** với **B = CDS mặc định**, trong cùng môi trường. Chênh lệch có thể phản ánh phần lớp JDK nền cùng các cải tiến CDS được runtime tự sử dụng.

**Câu hỏi B: Archive của ứng dụng có thêm lợi ích không?**  
So sánh **B = CDS nền** với **C = CDS nền + AppCDS archive**. Đây là so sánh chính cho một nhóm đang cân nhắc triển khai archive ứng dụng.

**Câu hỏi C: Toàn bộ cơ chế chia sẻ đem lại bao nhiêu lợi ích so với không chia sẻ?**  
So sánh **A = off** với **C = AppCDS**; đây là **lợi ích tổng hợp**, không được tuyên bố chỉ là “AppCDS nhanh hơn X%” nếu không phân rã phạm vi.

| Phép so sánh | Diễn giải hợp lý | Điều không được kết luận |
| --- | --- | --- |
| A vs B | Ảnh hưởng của CDS mặc định | Chính xác lợi ích riêng của archive ứng dụng |
| B vs C | Ảnh hưởng tăng thêm của AppCDS, nếu C thật sự dùng app archive | CDS bị tắt hoàn toàn ở B |
| A vs C | Ảnh hưởng tổng của CDS nền + AppCDS | Mọi chênh lệch chỉ do các class của ứng dụng |
| A vs A (lặp nhiều lượt) | Độ nhiễu của baseline không CDS | Không có biến động do OS/JVM |
| B vs B (lặp nhiều lượt) | Độ nhiễu của CDS mặc định | Một lần chạy nhanh hơn là hiệu quả ổn định |

Để kết luận có căn cứ, không chỉ so **trung bình thời gian** mà còn xem **median, percentiles và độ phân tán** của các lượt chạy.

## 5. Một chương trình Java 17+ độc lập để thực hành

Chương trình này cố ý nhỏ, có một lớp lồng với **static initializer** để xác nhận rằng CDS/AppCDS chỉ tối ưu cách nạp **dữ liệu lớp**, không tự bỏ qua những tác dụng phụ khởi tạo lớp theo Java.

Tạo tệp **AppCdsBaselineDemo.java**:

~~~java
public class AppCdsBaselineDemo {

    static final class Calculator {
        static {
            System.out.println("Calculator initialized");
        }

        static int multiply(int left, int right) {
            return Math.multiplyExact(left, right);
        }
    }

    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println("result = " + Calculator.multiply(7, 3));
        System.out.println("Application ready");
    }
}
~~~

Đây là **chương trình hoàn chỉnh**. Nó chỉ sử dụng Java SE, không cần dependency bên ngoài.

### Biên dịch và đóng gói thành JAR

Chạy trong **thư mục thực hành mới** có tệp nguồn trên:

~~~bash
mkdir build
javac --release 17 -d build AppCdsBaselineDemo.java
jar --create --file=appcds-baseline.jar --main-class=AppCdsBaselineDemo -C build .
~~~

Phân tích:
- `javac --release 17` xác định ngôn ngữ, API và target class-file của Java 17.
- `-d build` đưa class files vào thư mục output.
- `jar --create` đưa **cả class chính lẫn nested class** vào `appcds-baseline.jar`.
- `--main-class=AppCdsBaselineDemo` cho phép chạy bằng `java -jar`.
- Dùng JAR cho bài AppCDS vì một số quy trình HotSpot CDS truyền thống có **giới hạn với classpath chứa thư mục class không rỗng**.

Lệnh `mkdir build` giả định thư mục `build` chưa tồn tại; nếu làm trong dự án có sẵn, chọn thư mục output riêng và tránh ghi đè dữ liệu khác.

### Chạy kiểm tra tính đúng đắn

~~~bash
java -jar appcds-baseline.jar
~~~

**Đầu ra từ mã ứng dụng, giống nhau ở cả ba chế độ A/B/C:**

~~~text
Application started
Calculator initialized
result = 21
Application ready
~~~

Dòng `Calculator initialized` xuất hiện khi `Calculator` lần đầu được dùng. Mỗi lần khởi động JVM độc lập đều cần thực hiện class initialization hợp lệ; CDS truyền thống **không lưu một lần thực thi static initializer để bỏ qua nó trong các lần chạy sau**.

**Quan trọng:** ví dụ chỉ kiểm tra **tính đúng đắn và dòng chảy thao tác**. Vì chương trình quá nhỏ, chênh lệch thời gian thực có thể bé hơn nhiễu hệ thống. Muốn kết luận hiệu năng phải dùng một ứng dụng đại diện và phép đo nhiều lượt.

## 6. Cấu hình A — `-Xshare:off` làm baseline

Chạy cùng JAR với tùy chọn tắt CDS:

~~~bash
java -Xshare:off -jar appcds-baseline.jar
~~~

**Stdout ứng dụng:**

~~~text
Application started
Calculator initialized
result = 21
Application ready
~~~

Ý nghĩa:
- JVM **không sử dụng shared class data** từ archive.
- Lớp vẫn được tải, xác minh/liên kết/khởi tạo theo Java/VM như bình thường.
- Lời gọi `Calculator.multiply(7, 3)` vẫn cho kết quả `21`.
- Không tắt JIT, garbage collector, class loading hay cơ chế Java module.

Phép đo A là baseline **“CDS không được sử dụng”**, không phải baseline “JVM không tối ưu gì”.

### Kiểm chứng A thật sự không dùng shared classes

Trên HotSpot hỗ trợ Unified Logging:

~~~bash
java -Xshare:off -Xlog:class+load=info -jar appcds-baseline.jar
~~~

Những dòng class loading sẽ được in ra thêm. **Đừng coi log là stdout cố định**; định dạng và số dòng thay đổi theo JDK, OS, distribution.

Để xác thực, xem nguồn nạp các lớp điển hình và bảo đảm chúng không được báo là nạp từ **`shared objects file`** khi CDS đã tắt. Các lớp `Calculator` và `AppCdsBaselineDemo` nên đến từ JAR ứng dụng trong case A.

Lệnh chẩn đoán khác:

~~~bash
java -Xshare:off -Xlog:cds=info -jar appcds-baseline.jar
~~~

Nhưng số lượng và nội dung các dòng `cds` ở chế độ off có thể khác nhau. **Đừng dựa vào đúng một chuỗi log do ví dụ tự dựng**; dùng kết hợp cấu hình launch, log về nguồn nạp class và tài liệu runtime.

**Không bật verbose class logging trong các lượt đo chính**, vì việc ghi hàng trăm/nghìn dòng cũng có thể làm chậm startup và làm biến dạng kết quả.

## 7. Cấu hình B — CDS mặc định, chưa dùng archive ứng dụng riêng

Chạy:

~~~bash
java -Xshare:auto -jar appcds-baseline.jar
~~~

Hoặc trên JDK có CDS bật mặc định:

~~~bash
java -jar appcds-baseline.jar
~~~

**Stdout ứng dụng:**

~~~text
Application started
Calculator initialized
result = 21
Application ready
~~~

Lúc này HotSpot **có thể sử dụng archive mặc định của JDK**. Phần dữ liệu lớp nền có thể được ánh xạ từ shared archive, nhưng lớp thuộc `appcds-baseline.jar` **không nhất thiết** nằm trong archive mặc định.

Nếu JDK bị lược bỏ default archive, hoặc có cờ/điều kiện ngăn CDS, chế độ `auto` có thể không dùng archive. Vì vậy:
- Đừng nói “B chắc chắn có sharing” nếu chưa kiểm chứng.
- Đừng nói “B là chế độ AppCDS đầy đủ”.
- Để phép so sánh A/B có ý nghĩa, cần xác minh B thật sự có CDS nền khả dụng.

### Kiểm tra lớp nền lấy từ archive

~~~bash
java -Xshare:auto -Xlog:class+load=info -jar appcds-baseline.jar
~~~

Trong các phiên bản HotSpot phù hợp, một số lớp nền có thể có log nguồn:

~~~text
source: shared objects file
~~~

Đây là **mẫu văn bản cần tìm trong log JVM**, không phải stdout ứng dụng. Một số VM/JDK có thể thêm thông tin vùng archive như `shared objects file (top)` hoặc có format log khác.

## 8. Cấu hình C — AppCDS với archive riêng

### 8.1. Tạo dynamic archive bằng lượt chạy training

Cách tạo dynamic archive được hỗ trợ trong **JDK 17+**:

~~~bash
java -XX:ArchiveClassesAtExit=appcds-baseline.jsa -jar appcds-baseline.jar
~~~

Lệnh này:
1. Khởi động **chương trình thật** trong một lần chạy huấn luyện.
2. Cho VM biết những lớp đã được sử dụng.
3. Yêu cầu HotSpot ghi một dynamic CDS archive `appcds-baseline.jsa` khi kết thúc nếu đủ điều kiện.

Dùng một **tên archive chưa được sử dụng** hoặc làm mới một cách có kiểm soát. Tránh dùng nhầm archive cũ của một JDK/JAR khác. Chỉ tiếp tục sang bước dùng archive sau khi quá trình training thành công và artifact mới hợp lệ.

**Trong bước tạo archive:**
- Không thêm `-Xshare:off` vào cùng lượt tạo dynamic archive theo mẫu này.
- Dùng đúng JDK, JAR và classpath/module setup sẽ dùng trong benchmark.
- Đảm bảo thư mục có quyền ghi archive.
- Nếu ứng dụng thật có nhiều đường chạy, training cần đại diện cho những phần bạn mong muốn tối ưu.
- Lưu ý chạy training có thể tạo tác dụng phụ nghiệp vụ (gửi email, gọi API, ghi DB...). Dùng môi trường huấn luyện an toàn.

**Stdout ứng dụng trong training** vẫn là bốn dòng giống mục 5, nhưng JVM có thể phát sinh diagnostic messages khác theo cấu hình và phiên bản. **Không dùng lượt tạo archive làm một mẫu startup runtime bình thường** trong phép so sánh A/B/C: nó có thêm công việc ghi archive ở cuối.

### 8.2. Dùng dynamic archive trong lần chạy tiếp theo

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=appcds-baseline.jsa -jar appcds-baseline.jar
~~~

Khi archive tương thích và được dùng, HotSpot có thể nạp **các lớp ứng dụng có trong archive** ngoài lớp nền. Lệnh này là cấu hình **C**.

**Stdout ứng dụng vẫn là:**

~~~text
Application started
Calculator initialized
result = 21
Application ready
~~~

Sự khác nhau không nằm ở đáp án của chương trình mà nằm ở **chi phí nạp/chuẩn bị dữ liệu lớp**. Không được dùng output nghiệp vụ để suy ra trực tiếp archive đã thật sự được dùng.

### 8.3. Xác nhận class ứng dụng lấy từ shared archive

Chạy một lượt chẩn đoán **ngoài benchmark**:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=appcds-baseline.jsa -Xlog:class+load=info -jar appcds-baseline.jar
~~~

Tìm những class có tên:
- `AppCdsBaselineDemo`;
- `AppCdsBaselineDemo$Calculator`.

Nếu các lớp được lấy từ archive, Unified Logging trong các JDK phù hợp sẽ thể hiện nguồn như:

~~~text
source: shared objects file
~~~

Đây là **mẫu log**, không bảo đảm nguyên dòng log giống nhau giữa các JDK. Nếu chỉ thấy `java.lang.String` hoặc lớp JDK khác được chia sẻ, bạn **chưa chứng minh lớp ứng dụng có trong AppCDS archive**.

Có thể xem thêm:

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=appcds-baseline.jsa -jar appcds-baseline.jar
~~~

Những dòng log này giúp phát hiện archive không tương thích hoặc không được map. Dùng log để xác minh trạng thái **C thực sự có tác dụng**, rồi tắt log khi đo thời gian.

## 9. Đừng nhầm vị trí JVM option với argument của ứng dụng

Cờ JVM phải nằm **trước** `-jar` (hoặc trước main class theo cách gọi):

~~~bash
# ĐÚNG: -Xshare:off được truyền cho JVM.
java -Xshare:off -jar appcds-baseline.jar
~~~

Nhưng:

~~~bash
# SAI nếu muốn tắt CDS:
java -jar appcds-baseline.jar -Xshare:off
~~~

Ở lệnh thứ hai, sau khi xác định `-jar appcds-baseline.jar`, chuỗi `-Xshare:off` thường trở thành **argument của `main(String[] args)`**, không phải JVM option. Chương trình ví dụ không đọc `args` nên có thể vẫn in bốn dòng bình thường, khiến người dùng tưởng chế độ đã được kích hoạt.

**Bài học:** đừng chỉ nhìn chương trình “chạy được”. Hãy xác thực lệnh và nguồn nạp class khi kiểm tra trạng thái CDS.

### Không trộn cờ A và C

Đừng xây một lệnh benchmark với ý nghĩa mâu thuẫn như “vừa tắt CDS vừa yêu cầu sử dụng AppCDS archive”:

~~~bash
# Không dùng làm cấu hình C.
java -Xshare:off -XX:SharedArchiveFile=appcds-baseline.jsa -jar appcds-baseline.jar
~~~

Về mặt mục tiêu, `-Xshare:off` nói không sử dụng dữ liệu chia sẻ; chỉ định archive không khiến cấu hình ấy trở thành AppCDS. Tùy JDK, một số tổ hợp cờ có thể bị bỏ qua, cảnh báo hoặc từ chối; **đừng dựa vào hành vi ngoài hợp đồng mà hãy chọn cấu hình A/B/C tách biệt**.

## 10. Đo startup như thế nào để có thể tin kết quả?

### 10.1. Chọn một mốc “đã sẵn sàng”

Một CLI ngắn có thể đo **tổng thời gian process** từ khi bắt đầu đến khi thoát. Một dịch vụ server thường có mốc hữu ích hơn:
- Thời gian từ khi process được tạo đến khi báo **readiness**;
- Thời gian đến **request đầu tiên thành công**;
- Thời gian đến khi đăng ký service hoặc load cấu hình xong.

`System.nanoTime()` ở đầu `main()` **không bao phủ toàn bộ startup JVM**, vì nhiều lớp đã được nạp **trước khi `main` chạy**. Nếu muốn đo startup toàn process, dùng công cụ đo từ bên ngoài hoặc tracing thích hợp.

### 10.2. Một cặp lệnh đo tối giản trên Linux/macOS

Nếu có `/usr/bin/time`:

~~~bash
/usr/bin/time -p java -Xshare:off -jar appcds-baseline.jar
/usr/bin/time -p java -Xshare:auto -jar appcds-baseline.jar
/usr/bin/time -p java -Xshare:auto -XX:SharedArchiveFile=appcds-baseline.jsa -jar appcds-baseline.jar
~~~

Công cụ thời gian sẽ in `real`, `user`, `sys` theo khả năng hệ điều hành. **Không đưa ra stdout thời gian cố định**, vì phụ thuộc tốc độ máy, nhiệt độ, CPU load, OS page cache và nhiều yếu tố khác.

Trên Windows PowerShell, khi muốn một phép đo tương đương theo thời gian tường:

~~~powershell
Measure-Command { & java -Xshare:off -jar appcds-baseline.jar | Out-Null }
Measure-Command { & java -Xshare:auto -jar appcds-baseline.jar | Out-Null }
Measure-Command { & java -Xshare:auto -XX:SharedArchiveFile=appcds-baseline.jsa -jar appcds-baseline.jar | Out-Null }
~~~

Đây là **lệnh minh họa**. Đường dẫn `java` và thư mục làm việc phải giống nhau cho các lượt, và phần pipe cũng là một ít overhead cần giữ nhất quán.

**Không nên lấy ba kết quả đơn lẻ làm kết luận.** Các lệnh trên chỉ là cách kiểm tra ban đầu; benchmark nghiêm túc phải chạy nhiều lần.

### 10.3. Đo nhiều lượt, tránh thứ tự thiên lệch

Quy trình cơ bản:
1. Cố định **JDK build/vendor, JAR và dependency, đường dẫn, classpath/module path**.
2. Dùng các JVM options khác **giống nhau** ở cả A/B/C, ví dụ heap limit, GC và logging. Chỉ thay biến được khảo sát.
3. **Không đo lượt training/dump archive** như một lượt startup C.
4. Chạy **nhiều lượt**, mỗi lượt tạo JVM process mới; không xem nhiều lần gọi method trong cùng một process là nhiều mẫu startup.
5. Thử thứ tự A/B/C thay đổi hoặc luân phiên để giảm việc C luôn được hưởng OS page cache nóng hơn A.
6. Theo dõi **thời gian tường**, median, percentile 90/95 và độ phân tán. Có thể đo cả CPU time, nhưng không dùng CPU time thay cho startup-to-ready.
7. Tránh class loading verbose log, profiling nặng và `-XX:+PrintCompilation` trong lượt đo chính nếu chúng không hiện diện ở mọi cấu hình.
8. Cố định CPU quota/container limits; tránh backup, antivirus scan và công việc nền không kiểm soát.
9. Đảm bảo chương trình cho **kết quả đúng giống nhau** và đạt cùng mốc readiness.
10. Khi nhiều JVM chạy trên cùng host, đo memory shared/private/PSS nếu công cụ hỗ trợ, không chỉ tổng RSS.
11. Ghi kèm **version JDK, OS, kiến trúc CPU, cách tạo archive**, ngày đo và config đầy đủ.
12. Không suy luận một lần nhanh hơn là tác động riêng của CDS nếu các lượt đo có nhiễu lớn hơn chênh lệch.

### Bảng ghi kết quả đề xuất

| Lần đo | Cấu hình | Java build | JAR hash/version | Startup-to-ready (ms) | Ghi chú |
| --- | --- | --- | --- | ---: | --- |
| 1 | A — `-Xshare:off` | Giữ cố định | Giữ cố định | Số đo thực tế | Cold/warm cache |
| 2 | B — CDS nền | Giữ cố định | Giữ cố định | Số đo thực tế | Xác minh archive nền |
| 3 | C — AppCDS | Giữ cố định | Giữ cố định | Số đo thực tế | Xác minh app classes |
| ... | Lặp lại, đảo thứ tự | Giữ cố định | Giữ cố định | Số đo thực tế | Thống kê sau nhiều lượt |

**Đây là mẫu bảng để tự điền**, không chứa kết quả benchmark được bịa ra.

## 11. Cách tính chênh lệch startup mà không thổi phồng kết quả

Giả sử **một tập số liệu giả định chỉ để giải thích công thức**, không phải thực nghiệm:

| Nhánh | Median startup giả định |
| --- | ---: |
| A: CDS off | 500 ms |
| B: CDS mặc định | 450 ms |
| C: CDS + AppCDS | 420 ms |

Khi đó:

- Lợi ích của CDS nền so với off: `(500-450)/500 = 10%` giảm thời gian so với **A**.
- Lợi ích tăng thêm của AppCDS so với CDS nền: `(450-420)/450 ≈ 6,67%` giảm so với **B**.
- Lợi ích tổng từ off đến AppCDS: `(500-420)/500 = 16%` giảm so với **A**.

**Không cộng 10% với 6,67% và coi bằng 16,67% lợi ích tổng**, vì phần trăm dùng các mẫu số khác nhau.

Cũng cần phân biệt **giảm thời gian** với **tăng tốc độ**:
- Giảm thời gian từ 500 xuống 420 ms: `16%`.
- Hệ số tăng tốc `500/420 ≈ 1,19 lần`.

**Nhắc lại:** ba con số 500/450/420 ms hoàn toàn là **minh họa số học**, không được ghi vào báo cáo như kết quả đo CDS thực.

## 12. Đối chứng về bộ nhớ: RSS, PSS và shared pages

CDS/AppCDS không chỉ có tác động startup; nó còn có thể làm giảm mức nhân bản **metadata đọc-only** giữa các JVM có cùng archive.

Nhưng đo bộ nhớ cần tinh tế:

| Chỉ số | Ý nghĩa | Rủi ro diễn giải |
| --- | --- | --- |
| Java heap used/committed | Bộ nhớ heap object và GC | Không bao gồm toàn bộ VM metadata/shared archive |
| RSS | Những trang vật lý resident được tính cho một process | Trang shared có thể xuất hiện trong RSS của **nhiều process** |
| PSS | Chia phần trang shared theo tỷ lệ dùng chung | Hữu ích hơn khi đo tổng footprint của nhiều process |
| Private dirty / USS | Bộ nhớ riêng của process | Giúp thấy phần không được chia sẻ |
| Native memory statistics | Metaspace, VM structures... | Cần công cụ và cách hạch toán đúng phiên bản |
| Mapped archive bytes | Phần tệp archive được map | Không đồng nghĩa tất cả trang đã resident, hoặc toàn bộ RAM bị chiếm riêng |

Nếu có ba JVM cùng map một vùng read-only, mỗi JVM có thể tính vùng đó trong RSS. Cộng cả ba RSS **không bằng** số trang vật lý duy nhất đang dùng.

Để đánh giá bộ nhớ:
1. So sánh **A/B/C** với cùng số instance, cùng workload, cùng heap/GC configuration.
2. Xem PSS, private/shared pages hoặc metric tương đương nếu có.
3. Đo ở cùng trạng thái khởi động/ready và sau cùng lượng công việc đại diện.
4. Không kết luận về bộ nhớ chỉ từ kích thước tệp `.jsa` trên đĩa.
5. Phân biệt footprint khi **một JVM** và khi **nhiều JVM cùng host**: CDS có thể có lợi ích chia sẻ rõ hơn ở trường hợp nhiều JVM.

`-Xshare:off` là baseline hợp lý để quan sát “không dùng shared class metadata”; nhưng mọi sự thay đổi về **heap objects, GC và JIT** vẫn cần được kiểm soát trong thử nghiệm.

## 13. Điều kiện để phép đo C thực sự dùng AppCDS

Một archive tên `appcds-baseline.jsa` tồn tại **không đồng nghĩa JVM chắc chắn dùng nó**.

Những nguyên nhân làm archive không dùng được hoặc không bao phủ lớp mong muốn:
- **JDK build/version** khác so với lúc tạo archive.
- JAR đã bị thay, classpath hoặc module-related options không tương thích.
- Không có quyền đọc archive hoặc tệp archive bị hỏng.
- Một số VM flags/xung đột module options vô hiệu hóa CDS.
- Lớp không được nạp trong lần training hoặc không đủ điều kiện archive.
- Các class loader/framework/plugin sinh class động không tạo ra cùng điều kiện như lúc training.

Nếu C rơi về chế độ không dùng archive, so sánh B với C có thể không phản ánh lợi ích AppCDS, dù hai lệnh nhìn “đúng cú pháp”.

### Chế độ `auto` và tính tương thích

`-Xshare:auto` cho phép chia sẻ **khi có thể**, không phải cam kết sẽ luôn dùng archive. Khi cần xác thực, hãy kiểm tra log `-Xlog:cds`, `-Xlog:class+load` trên lượt chẩn đoán riêng. Nếu muốn *fail fast* để kiểm tra trong môi trường thử nghiệm, chế độ `on` có thể hữu ích nhưng cần hiểu nguy cơ JVM không khởi động khi archive không dùng được.

### Đổi JDK hoặc JAR sau training

Lúc thay đổi application artifact hoặc runtime, nên tạo lại archive. Đừng dùng “tên file `.jsa` vẫn như cũ” làm bằng chứng nó tương thích.

Một quy trình triển khai hợp lý:
- Build và đóng gói **JAR chính thức**.
- Tạo archive từ JDK/container image dùng trong deployment.
- Giữ **cặp JAR + archive** cùng phiên bản trong release artifact.
- Sau khi nâng JDK hoặc đổi dependency, tạo lại archive rồi kiểm tra.
- Chỉ dùng archive từ nguồn tin cậy, bảo vệ quyền ghi và tính toàn vẹn.

## 14. Giới hạn của `-Xshare:off` trong JDK mới có AOT cache

Từ JDK 24, HotSpot có thêm các cơ chế **Ahead-of-Time (AOT) cache** mở rộng những tối ưu được chuẩn bị trước khi ứng dụng chạy. JDK 25 bổ sung lựa chọn command-line thuận tiện hơn cho quy trình AOT. Đây là tiến hóa của JVM, không phải nguyên trạng AppCDS ở Java 10.

Vì vậy, trước khi benchmark trên JDK 24/25+ cần xác định **đối tượng muốn tắt/so sánh**:
- **CDS truyền thống**, điều khiển bằng `-Xshare:off`/`auto`.
- **AOT cache** được chọn qua những tùy chọn `-XX:AOTCache`, `-XX:AOTMode` theo phiên bản.
- Những tối ưu khác vẫn hoạt động, như JIT/GC, vốn **không bị tắt** bởi `-Xshare:off`.

Trên JDK hỗ trợ chế độ AOT mới, một cấu hình thử nghiệm liên quan có thể là:

~~~bash
java -XX:AOTMode=off -jar appcds-baseline.jar
~~~

**Cờ này thuộc các JDK mới có `AOTMode` (ví dụ JDK 25); không dùng trên JDK 17.** Theo tài liệu JDK 25, `AOTMode=off` nghĩa là **không sử dụng AOT cache**. Nó được dùng khi câu hỏi benchmark là về các cải tiến AOT cache hiện đại, không tự thay thế nguyên tắc A/B/C của AppCDS ở JDK 17.

**Không trộn tùy tiện cờ AOT mới với `-Xshare:off` và archive `.jsa` cũ** rồi giả định mọi combination có ngữ nghĩa giống nhau. Hãy đọc tài liệu launcher của **đúng JDK build**; với JDK 25, AOT mode mặc định và các trường hợp fallback khác với logic sử dụng một dynamic CDS archive truyền thống.

### Cách thiết kế benchmark khi ứng dụng chuyển sang AOT cache

Cần nêu rõ:
1. Tính năng và artifact đang đo: **base CDS archive**, **AppCDS `.jsa`**, hay **AOT cache `.aot`**.
2. Nhánh đối chứng không dùng cache nào theo **đúng contract của runtime**.
3. Nhánh có cache đã **load thành công** và đã được xác minh bằng log phù hợp (ví dụ `-Xlog:aot` trên HotSpot mới).
4. Training/assembly được chạy tách khỏi lượt đo runtime, trừ khi chính quy trình tạo cache là đối tượng đo.
5. Application JAR, JDK, OS/CPU và những JVM flags có tính tương thích phải nhất quán.

**Thông điệp xuyên suốt:** một baseline có tên “OFF” phải thực sự tắt đúng **thành phần bạn muốn khảo sát** và không được âm thầm thay đổi biến khác.

## 15. Những điều `-Xshare:off` không làm

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Tắt CDS nghĩa là JVM không nạp class nữa” | JVM vẫn nạp/lien kết/khởi tạo lớp đúng ngữ nghĩa Java; chỉ không dùng class data sharing |
| “Tắt CDS cũng tắt JIT” | Sai; **`-Xint`** liên quan chế độ interpreted-only, không phải `-Xshare:off` |
| “Tắt CDS cũng tắt GC” | Sai; GC hoạt động theo cấu hình JVM bình thường |
| “Tắt CDS làm chương trình trả kết quả khác” | Không được làm thay đổi tính đúng đắn; nếu thấy khác, cần điều tra bug hoặc yếu tố khác |
| “Tắt CDS loại bỏ mọi cache của OS/JVM” | Sai; OS page cache, buffer, JIT và nhiều cache khác vẫn tồn tại |
| “Tắt CDS đo được chi phí riêng của AppCDS” | Không chính xác nếu so trực tiếp với C; A còn tắt cả CDS nền |
| “Không truyền `SharedArchiveFile` thì CDS đã off” | Sai; JDK thường có base CDS archive |
| “Mọi Java SE VM phải hỗ trợ `-Xshare`” | Không; đây là tùy chọn HotSpot/JVM-specific, cần kiểm tra bản phân phối |
| “Chạy `-Xshare:on` càng tốt cho production” | Không; có nguy cơ fail khi archive không dùng được |
| “`-Xshare:off` làm JVM giống hoàn toàn JVM của JDK cũ” | Không; chỉ thay một lựa chọn chia sẻ dữ liệu lớp, các tối ưu JDK khác vẫn có |

Một lỗi thường gặp nữa là vô tình đặt JVM option **sau** `-jar`, khiến `main` nhận nó như argument; lúc đó phép đối chứng không còn hợp lệ.

## 16. Những lỗi thường gặp khi benchmark AppCDS

### Lỗi 1 — Chỉ có hai nhánh `off` và `AppCDS`

Nếu không có nhánh **B — CDS mặc định**, bạn không tách được phần tiết kiệm từ JDK base archive. Thêm B để báo cáo đúng mức đóng góp của archive ứng dụng.

### Lỗi 2 — Không xác minh C thực sự dùng archive

Nếu archive không tương thích hoặc các lớp mong muốn chưa nằm trong archive, “chế độ C” có thể không phản ánh AppCDS như dự định. Hãy xác minh nguồn class bằng log.

### Lỗi 3 — Dùng lần training làm một mẫu hiệu năng C

Training với `ArchiveClassesAtExit` thêm công việc thu thập/dump archive, nên không đại diện cho runtime **đọc** archive ở những lần chạy tiếp theo.

### Lỗi 4 — Mỗi nhánh sử dụng JDK hoặc JAR khác

Khi JDK build, classpath, dependency hoặc flags khác nhau, kết luận “CDS giúp X ms” không còn cô lập được nguyên nhân. Cố định artifact và cấu hình, trừ cờ liên quan CDS.

### Lỗi 5 — Đo duy nhất một lần

Startup bị ảnh hưởng bởi JIT/OS page cache, frequency scaling, CPU quota, I/O và load nền. Cần nhiều lượt, thay đổi thứ tự và dùng số liệu phân phối.

### Lỗi 6 — In log quá nhiều trong lượt benchmark

`-Xlog:class+load=info` có thể làm chậm process. Bật log ở lượt chẩn đoán, tắt khi đo.

### Lỗi 7 — Đo chỉ trong `main`

Phần JVM bootstrap và class loading trước `main` đã diễn ra. Muốn đo startup toàn trình, dùng công cụ từ bên ngoài hoặc mốc readiness/launcher.

### Lỗi 8 — Nhầm giảm thời gian với tăng throughput

Startup-to-ready giảm không tự chứng minh throughput ổn định tăng. Cần benchmark workload sau warmup riêng.

### Lỗi 9 — Tính tổng RSS của nhiều JVM như RAM vật lý riêng

Shared archive pages có thể tính vào RSS từng process. PSS/shared-private memory sẽ phù hợp hơn khi muốn đo chia sẻ bộ nhớ.

### Lỗi 10 — Dùng archive cũ với JDK/JAR mới

Archive phụ thuộc build và classpath. Tái tạo archive khi đổi JDK, JAR, dependency hoặc điều kiện runtime quan trọng.

### Lỗi 11 — Kết luận có CDS chỉ vì `-Xshare:auto` có mặt

`auto` nghĩa là **dùng khi có thể**, không bảo đảm thực sự dùng. Xem log và xác nhận tình trạng archive.

### Lỗi 12 — Đặt `-Xshare:off` sau tên JAR

Lúc đó cờ có thể chỉ là `args` cho `main`, làm benchmark tưởng tắt CDS nhưng thực tế không thay cấu hình JVM.

### Lỗi 13 — Xem mọi tối ưu AOT mới là AppCDS cũ

Trên JDK 24/25+, AOT cache có cơ chế và flags riêng. Chọn baseline theo cache muốn đo, không trộn tùy tiện.

### Lỗi 14 — Báo một tỷ lệ hiệu năng không có môi trường và sai số

Một báo cáo “tăng 20%” thiếu JDK, OS, CPU, JAR, số lần chạy, độ phân tán và định nghĩa startup là **không đủ khả năng tái lập**.

## 17. Mẫu quy trình thực tế cho nhóm vận hành

Một quy trình triển khai/đo đạc có thể có những bước sau.

**Bước 1 — Cố định artifact và runtime.**  
Xác nhận `java --version`, phiên bản JAR, CPU/OS và các JVM options. Nếu dùng container, cố định image digest hoặc bản phát hành tương đương.

**Bước 2 — Xác định mốc đo.**  
Với CLI: thời gian process từ launch tới exit. Với web service: readiness hoặc first successful response. Không hoán đổi các mốc mà không ghi rõ.

**Bước 3 — Tạo archive.**  
Chạy training `ArchiveClassesAtExit` một lần trong môi trường an toàn, dùng JAR/runtime phù hợp.

**Bước 4 — Xác thực archive.**  
Bật `-Xlog:cds` và `-Xlog:class+load` ở một lượt riêng; kiểm tra class ứng dụng trong shared archive.

**Bước 5 — Đo A/B/C.**  
Chạy ba cấu hình với mọi tùy chọn khác giữ nguyên. Luân phiên thứ tự, lặp đủ số lượt, ghi dữ liệu thô.

**Bước 6 — Phân tích.**  
Tính median, percentiles, chênh lệch tuyệt đối (ms) và tương đối (%), ghi rõ baseline làm mẫu số. Có thể bổ sung đo PSS/private pages khi cần.

**Bước 7 — Xác nhận tính đúng đắn.**  
Ứng dụng phải hoàn thành cùng tác vụ, cùng bộ test và cho kết quả nghiệp vụ tương đương ở cả ba nhánh.

**Bước 8 — Quyết định vận hành.**  
Nếu B gần C, archive ứng dụng có thể không mang thêm lợi ích đáng kể trong workload ấy. Nếu C tốt hơn B ổn định và overhead training/deploy chấp nhận được, có thể xem xét triển khai AppCDS. Không quyết định chỉ từ số liệu một lượt.

**Bước 9 — Tái kiểm tra sau thay đổi.**  
Khi JDK, JAR, dependency hoặc startup path thay đổi, tái tạo archive và benchmark lại.

**Bước 10 — Giữ khả năng fallback.**  
Production nên có chiến lược an toàn khi archive không hợp lệ, tránh làm ứng dụng dừng khởi động vì cờ yêu cầu sharing bắt buộc.

## 18. Tự kiểm tra kiến thức

**Câu 1.** `-Xshare:off` làm gì?

**Đáp án:** Yêu cầu HotSpot **không cố sử dụng shared class data**, tức tắt CDS trong lần chạy ấy. JVM vẫn chạy chương trình bình thường.

**Câu 2.** `-Xshare:off` có chỉ tắt archive ứng dụng mà vẫn giữ CDS nền không?

**Đáp án:** Không. Nó tắt cả việc dùng CDS nền và AppCDS, nên là baseline **không chia sẻ dữ liệu lớp**.

**Câu 3.** Vì sao so sánh A = off với C = AppCDS chưa cho biết chính xác lợi ích riêng của AppCDS?

**Đáp án:** Vì C có thể dùng cả base CDS và app archive, còn A tắt cả hai. Cần thêm B = CDS nền để tách phần tăng thêm của app archive.

**Câu 4.** Chế độ nào phù hợp hơn để chạy ứng dụng thật khi archive có thể không dùng được?

**Đáp án:** `-Xshare:auto` hoặc mặc định tương ứng của HotSpot, vì dùng sharing khi có thể; không lạm dụng `-Xshare:on` trong production.

**Câu 5.** Có thể dùng `-Xshare:on` để kiểm tra archive không?

**Đáp án:** Có, cho mục đích thử nghiệm/diagnostic. Nhưng nếu archive không dùng được thì JVM có thể thoát khi khởi động, nên không dùng làm mặc định production.

**Câu 6.** Sau khi bật `-Xshare:off`, class vẫn được khởi tạo và `static initializer` vẫn chạy chứ?

**Đáp án:** Có. CDS là tối ưu dữ liệu lớp; việc tắt nó không làm mất semantics Java.

**Câu 7.** Lệnh nào tạo dynamic AppCDS archive theo cách dùng được trên JDK 17+?

**Đáp án:** `java -XX:ArchiveClassesAtExit=appcds-baseline.jsa -jar appcds-baseline.jar` với JAR và runtime phù hợp.

**Câu 8.** Làm sao kiểm tra lớp ứng dụng được lấy từ shared archive?

**Đáp án:** Bật `-Xlog:class+load=info` ở một lượt chẩn đoán, tìm class cụ thể cùng nguồn nạp shared archive; xem thêm `-Xlog:cds=info`.

**Câu 9.** Vì sao không nên đo startup với class logging verbose bật?

**Đáp án:** Logging thêm I/O và chi phí xử lý, có thể làm sai lệch thời gian mà bạn muốn đo.

**Câu 10.** Vì sao không nên xem RSS của từng JVM là tổng bộ nhớ vật lý duy nhất khi dùng CDS?

**Đáp án:** Các trang shared read-only có thể được tính vào RSS của nhiều process. Cần chỉ số PSS/private/shared khi có thể.

**Câu 11.** Nếu output chương trình giống nhau ở cả ba nhánh, có thể kết luận C chắc chắn dùng AppCDS không?

**Đáp án:** Không. Output nghiệp vụ chỉ chứng minh một phần tính đúng đắn; phải xác minh nguồn nạp class/log CDS.

**Câu 12.** Nếu benchmark trên JDK 25 có AOT cache mới, có nên coi `-Xshare:off` và `-XX:AOTMode=off` là hai chuỗi tên đồng nghĩa tuyệt đối không?

**Đáp án:** Không. Chúng thuộc các cơ chế/nhánh điều khiển khác nhau. Chọn và xác minh baseline theo chính tính năng muốn khảo sát, đối chiếu tài liệu JDK mục tiêu.

**Câu 13.** Lợi ích tổng từ A=500 ms đến C=420 ms là giảm bao nhiêu thời gian theo tỷ lệ?

**Đáp án:** `(500-420)/500 = 16%` giảm thời gian so với A. Đây là ví dụ số học, không phải benchmark thực.

**Câu 14.** Nếu C không nhanh hơn B một cách ổn định sau nhiều lần đo, nên kết luận gì?

**Đáp án:** Với workload/JDK/điều kiện đã đo, lợi ích tăng thêm của archive ứng dụng **chưa được chứng minh rõ**, không nên tự gán hiệu quả.

**Câu 15.** Nếu không thêm `-Xshare:off` vào lệnh `java -jar app.jar`, có phải đó là baseline không CDS không?

**Đáp án:** Không. JDK hiện đại có thể sử dụng **base CDS archive mặc định** ngay cả khi không chỉ định archive tùy chỉnh.

## 19. Ghi nhớ cuối bài

1. **`-Xshare:off` là công tắc tắt CDS trên HotSpot**, rất hữu ích để tạo **baseline không dùng shared class data**.
2. Nó tắt **cả CDS nền và AppCDS**, không riêng archive ứng dụng.
3. Muốn đánh giá phần tăng thêm của AppCDS, nên có đủ **A (off), B (CDS nền), C (CDS + AppCDS)**.
4. Dùng **`ArchiveClassesAtExit`** trong lượt training tách riêng, **`SharedArchiveFile`** trong lượt chạy C; không tính training vào startup runtime.
5. Xác minh trạng thái bằng **`-Xlog:class+load`** và **`-Xlog:cds`**, không chỉ nhìn sự tồn tại của `.jsa`.
6. Đo **nhiều lượt**, giữ JDK/JAR/workload/VM flags nhất quán, thay đổi thứ tự để hạn chế nhiễu.
7. Phân biệt **startup, throughput và memory footprint**; CDS không tự loại bỏ static initialization, I/O, JIT hoặc GC.
8. Khi đo RAM có nhiều JVM, chú ý **shared pages/PSS**, không chỉ RSS.
9. **`-Xshare:on` chủ yếu để thử nghiệm**, có thể làm startup thất bại; production nên có chiến lược fallback phù hợp.
10. JDK 24/25+ có **AOT cache**; chọn cờ đối chứng theo tính năng hiện đại cụ thể, không áp dụng máy móc toàn bộ cách đo Java 10.
11. Chỉ báo cáo **số tăng tốc thực tế có nguồn đo**, không dùng các con số minh họa làm kết luận triển khai.

**Tài liệu tham khảo chính thức và còn áp dụng:**
- [Oracle Java SE 17 — `java` launcher, `-Xshare` modes và AppCDS](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html).
- [Oracle Java SE 25 — `java` launcher, CDS archive và AOT modes](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [OpenJDK — JEP 310: Application Class-Data Sharing](https://openjdk.org/jeps/310).
- [OpenJDK — JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483).
- [OpenJDK — JEP 514: Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514).
