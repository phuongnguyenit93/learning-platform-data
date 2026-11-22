# Heap option trong Java Runtime

Heap là vùng bộ nhớ runtime của JVM dùng để cấp phát các đối tượng và mảng Java. Garbage collector (GC) quản lý heap và thu hồi vùng nhớ của những đối tượng không còn được tham chiếu. Các heap option cho phép cấu hình kích thước ban đầu, giới hạn tối đa và cách JVM ước lượng dung lượng heap phù hợp với môi trường chạy.

Hai tùy chọn quan trọng nhất là **-Xms** và **-Xmx**. Chọn giá trị hợp lý giúp ứng dụng có đủ bộ nhớ, hạn chế việc mở rộng heap liên tục và tránh để JVM chiếm quá nhiều RAM của máy hoặc container.

## 1. Heap trong tổng thể bộ nhớ JVM

Heap không phải toàn bộ bộ nhớ mà tiến trình Java sử dụng. JVM còn cần các vùng nhớ ngoài heap:

| Vùng nhớ | Công dụng | Có được tính vào -Xmx không? |
|---|---|---|
| Java heap | Đối tượng và mảng Java thông thường | Có |
| Metaspace | Metadata của class và thông tin runtime liên quan | Không |
| Thread stack | Stack riêng của từng thread, gồm frame và biến cục bộ | Không |
| Direct/native memory | Bộ đệm ngoài heap, thư viện native và vùng nhớ do JVM quản lý | Không |
| Code cache | Mã máy do JIT compiler sinh ra | Không |

Do đó, đặt **-Xmx** bằng toàn bộ RAM máy hoặc giới hạn bộ nhớ container có thể khiến tiến trình vượt giới hạn tổng thể dù heap chưa đạt mức tối đa.

## 2. Hai heap option cơ bản

### 2.1. -Xms: heap ban đầu

**-Xms** đặt kích thước heap ban đầu mà JVM yêu cầu khi khởi chạy.

~~~powershell
java -Xms256m -jar app.jar
~~~

Ví dụ này yêu cầu heap ban đầu khoảng 256 MiB. Heap thực tế và dung lượng được commit còn phụ thuộc cách JVM quản lý bộ nhớ cùng giới hạn của runtime.

### 2.2. -Xmx: heap tối đa

**-Xmx** đặt giới hạn tối đa của Java heap.

~~~powershell
java -Xmx1g -jar app.jar
~~~

Lệnh trên đặt giới hạn heap tối đa khoảng 1 GiB. JVM không được mở rộng Java heap vượt quá giới hạn này. Nếu ứng dụng cần cấp phát thêm mà GC không thể thu hồi đủ bộ nhớ, JVM có thể ném lỗi **OutOfMemoryError: Java heap space**.

### 2.3. Kết hợp -Xms và -Xmx

Thông thường, đặt cả hai tùy chọn để kiểm soát heap ban đầu và giới hạn trên:

~~~powershell
java -Xms256m -Xmx1g -jar app.jar
~~~

Ý nghĩa:

- Heap ban đầu được yêu cầu là 256 MiB.
- Heap có thể tăng khi ứng dụng cần thêm bộ nhớ.
- Heap tối đa được giới hạn ở khoảng 1 GiB.

Nếu đặt hai giá trị bằng nhau:

~~~powershell
java -Xms1g -Xmx1g -jar app.jar
~~~

JVM được cấu hình với heap ban đầu và tối đa cùng mức 1 GiB. Cách này có thể hữu ích cho dịch vụ có tải ổn định, cần tránh thay đổi dung lượng heap trong lúc chạy. Tuy nhiên, heap lớn ngay từ đầu có thể làm tăng lượng bộ nhớ được commit và không phải lúc nào cũng phù hợp với ứng dụng nhỏ hoặc môi trường chạy nhiều instance.

Không có một cặp giá trị tối ưu cho mọi ứng dụng. Hãy đo mức sử dụng dưới tải thực tế trước khi chốt cấu hình.

## 3. Đơn vị và cú pháp kích thước

Các heap option nhận giá trị số kèm hậu tố đơn vị:

| Hậu tố | Ý nghĩa |
|---|---|
| k hoặc K | Kilobyte |
| m hoặc M | Megabyte |
| g hoặc G | Gigabyte |

Ví dụ:

~~~powershell
java -Xms512m -Xmx2g -jar app.jar
~~~

Có thể viết giá trị dưới dạng byte, nhưng hậu tố m và g thường dễ đọc hơn trong cấu hình triển khai. Hãy kiểm tra thông báo của JVM khi truyền giá trị không hợp lệ. Tránh nhầm giữa **-Xmx2g** và **-Xmx2m** vì chênh lệch đơn vị rất lớn.

## 4. Đặt heap option đúng vị trí trong lệnh java

Heap option là tùy chọn của JVM, vì vậy phải đặt trước phần chỉ định cách chạy ứng dụng như **-jar**, **-m** hoặc tên lớp chính.

Chạy executable JAR:

~~~powershell
java -Xms256m -Xmx1g -jar app.jar
~~~

Chạy lớp trên classpath:

~~~powershell
java -Xms256m -Xmx1g -cp "out;lib/*" com.example.Main
~~~

Chạy named module:

~~~powershell
java -Xms256m -Xmx1g --module-path mlib --module com.example.app/com.example.app.Main
~~~

Các heap option trong ví dụ được JVM xử lý trước khi ứng dụng bắt đầu. Những đối số đặt sau tên JAR, lớp chính hoặc module/lớp chính được truyền cho chương trình Java. Nếu đặt heap option vào vị trí đối số ứng dụng, chương trình có thể nhận nó trong args thay vì JVM áp dụng nó.

## 5. Chọn kích thước heap phù hợp

### 5.1. Đo trước khi tăng heap

Theo dõi ứng dụng trong các kịch bản đại diện:

- Khởi động và nạp dữ liệu ban đầu.
- Tải bình thường trong thời gian đủ dài.
- Tải cao hoặc nhiều request đồng thời.
- Các tác vụ tiêu thụ nhiều đối tượng như xử lý batch, tạo báo cáo hoặc đọc dữ liệu lớn.
- Thời điểm GC hoạt động mạnh và sau khi GC hoàn tất.

Nếu heap used tăng liên tục qua nhiều chu kỳ GC và không giảm về mức ổn định, hãy kiểm tra khả năng giữ tham chiếu ngoài ý muốn hoặc memory leak. Chỉ tăng **-Xmx** có thể trì hoãn lỗi mà không xử lý nguyên nhân.

### 5.2. Cân đối RAM cho toàn tiến trình

Tổng RAM cần cho một tiến trình Java thường lớn hơn heap tối đa. Ngoài heap, JVM cần metaspace, thread stack, direct buffer, code cache và các vùng nhớ native khác. Hệ điều hành cũng cần bộ nhớ cho tiến trình khác và cache.

Ví dụ, nếu container có giới hạn 2 GiB, không nên mặc định đặt **-Xmx2g**. Cần để lại khoảng trống cho native memory, thread stack, JVM và tiến trình phụ trợ nếu có. Giá trị cụ thể phải dựa trên phép đo của chính ứng dụng.

### 5.3. Khi nào nên đặt -Xms bằng -Xmx?

Đặt hai giá trị bằng nhau có thể phù hợp khi:

- Ứng dụng là dịch vụ dài hạn, tải tương đối ổn định.
- Đã đo được mức heap cần thiết.
- Máy/container có đủ RAM cho heap cùng phần bộ nhớ ngoài heap.
- Muốn giảm biến động do heap mở rộng trong quá trình chạy.

Giữ **-Xms** thấp hơn **-Xmx** có thể phù hợp khi ứng dụng có tải biến động, nhiều tiến trình cùng chia sẻ tài nguyên hoặc cần tránh yêu cầu heap lớn ngay lúc khởi động.

## 6. Cấu hình heap theo tỷ lệ RAM

Ngoài giá trị cố định, HotSpot JVM hỗ trợ các tùy chọn phần trăm để tính kích thước heap dựa trên lượng RAM mà JVM nhận diện được.

### 6.1. InitialRAMPercentage

**-XX:InitialRAMPercentage** đặt tỷ lệ phần trăm bộ nhớ khả dụng mà JVM dùng để tính heap ban đầu.

~~~powershell
java -XX:InitialRAMPercentage=10 -jar app.jar
~~~

Giá trị là phần trăm, ví dụ 10 nghĩa là 10%. Đây là cơ chế tính heap ban đầu theo môi trường; nó không phải dung lượng byte cố định.

### 6.2. MaxRAMPercentage

**-XX:MaxRAMPercentage** đặt tỷ lệ phần trăm bộ nhớ khả dụng mà JVM dùng để tính heap tối đa.

~~~powershell
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Tùy chọn này hữu ích khi chạy cùng một ứng dụng trên các máy hoặc container có giới hạn RAM khác nhau. Hãy cân nhắc phần bộ nhớ ngoài heap và các tiến trình cùng chia sẻ giới hạn trước khi chọn tỷ lệ.

Có thể kết hợp hai tùy chọn:

~~~powershell
java -XX:InitialRAMPercentage=20 -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Khi dùng các tùy chọn phần trăm, JVM vẫn áp dụng các giới hạn và chính sách bộ nhớ của runtime. Nếu đồng thời đặt **-Xms** hoặc **-Xmx**, giá trị cố định có thể chi phối giới hạn tương ứng; tránh cấu hình chồng chéo khó hiểu. Hãy kiểm tra flags hiệu lực thay vì đoán JVM đã chọn giá trị nào.

### 6.3. Chạy trong container

Các bản JDK hiện đại có hỗ trợ nhận diện giới hạn bộ nhớ container trên những nền tảng được hỗ trợ. JVM có thể dùng giới hạn đó khi tính heap và áp dụng các mặc định về tài nguyên.

Cần xác minh runtime và môi trường thực tế:

- Kiểm tra phiên bản JDK và hệ điều hành.
- Xác nhận JVM nhận diện đúng giới hạn container.
- Kiểm tra giới hạn bộ nhớ do nền tảng điều phối đặt ra.
- Theo dõi RSS và mức sử dụng bộ nhớ tổng thể, không chỉ heap used.
- Chừa khoảng trống cho native memory và tiến trình phụ trợ trong cùng giới hạn.

Không giả định **-XX:MaxRAMPercentage** luôn tính trên toàn bộ RAM vật lý của máy chủ; JVM sử dụng lượng bộ nhớ mà nó nhận diện là khả dụng.

## 7. Heap option và các vùng nhớ khác

Một số lỗi thiếu bộ nhớ không xuất phát từ Java heap. Phân biệt các vùng nhớ giúp chọn đúng tùy chọn và công cụ chẩn đoán.

| Vấn đề | Vùng nhớ liên quan | Hướng kiểm tra |
|---|---|---|
| OutOfMemoryError: Java heap space | Java heap | Xem heap dump, object retention, GC và -Xmx |
| OutOfMemoryError: Metaspace | Metaspace | Kiểm tra class loading, classloader leak và metadata |
| unable to create native thread | Tài nguyên thread/native memory hoặc giới hạn OS | Kiểm tra số thread, -Xss, giới hạn tiến trình và RAM |
| Direct buffer memory | Bộ nhớ direct buffer ngoài heap | Kiểm tra việc cấp phát/giải phóng buffer và -XX:MaxDirectMemorySize |
| Tiến trình bị hệ điều hành/container kill | Tổng bộ nhớ tiến trình hoặc giới hạn hệ thống | Xem RSS, container limit, native memory và log hệ điều hành |

**-Xss** đặt kích thước stack cho mỗi thread; đây không phải heap option. **-XX:MaxMetaspaceSize** giới hạn metaspace, còn **-XX:MaxDirectMemorySize** giới hạn dung lượng direct buffer mà JVM cho phép. Không tăng các giới hạn này để xử lý một lỗi heap nếu chưa xác định đúng vùng nhớ gây lỗi.

## 8. Kiểm tra heap trong lúc ứng dụng chạy

### 8.1. Dùng Runtime trong Java

Java API cung cấp thông tin heap cơ bản qua Runtime:

~~~java
public class HeapInfo {
    private static double toMiB(long bytes) {
        return bytes / (1024.0 * 1024.0);
    }

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.printf("maxMemory  = %.1f MiB%n", toMiB(runtime.maxMemory()));
        System.out.printf("totalMemory= %.1f MiB%n", toMiB(runtime.totalMemory()));
        System.out.printf("freeMemory = %.1f MiB%n", toMiB(runtime.freeMemory()));
        System.out.printf("used in committed heap = %.1f MiB%n",
                toMiB(runtime.totalMemory() - runtime.freeMemory()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~powershell
javac HeapInfo.java
java -Xms64m -Xmx256m HeapInfo
~~~

Các giá trị có ý nghĩa:

- maxMemory(): giới hạn heap tối đa JVM báo cho ứng dụng.
- totalMemory(): dung lượng heap hiện đang được JVM commit.
- freeMemory(): phần còn trống trong vùng heap đã commit.
- totalMemory() - freeMemory(): ước lượng phần đã sử dụng trong vùng heap đã commit tại thời điểm đọc.

Các số liệu thay đổi theo thời gian và hoạt động của GC. totalMemory() không nhất thiết luôn bằng maxMemory(), vì JVM có thể commit heap theo nhu cầu.

### 8.2. Dùng jcmd để kiểm tra tiến trình

**jcmd** đi kèm JDK và có thể gửi lệnh chẩn đoán tới một JVM đang chạy mà người dùng có quyền truy cập.

Liệt kê tiến trình Java:

~~~powershell
jcmd -l
~~~

Xem flags hiệu lực của một tiến trình:

~~~powershell
jcmd <pid> VM.flags
~~~

Xem thông tin heap:

~~~powershell
jcmd <pid> GC.heap_info
~~~

Thay <pid> bằng process ID thực tế. Có thể xem thêm các lệnh được tiến trình hỗ trợ bằng:

~~~powershell
jcmd <pid> help
~~~

Không chạy lệnh chẩn đoán tùy tiện trên production nếu chưa đánh giá tác động; một số thao tác như histogram hoặc heap dump có thể tốn CPU, I/O và thời gian tạm dừng.

### 8.3. Xem GC log

Từ Java 9 trở lên, unified logging có thể ghi hoạt động GC bằng **-Xlog**:

~~~powershell
java -Xms256m -Xmx1g -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

GC log giúp quan sát thời điểm thu gom rác, dung lượng heap trước/sau GC, thời gian pause và các sự kiện liên quan. Dùng log cùng số liệu tải ứng dụng để xác định heap có quá nhỏ, có áp lực cấp phát lớn hay có dấu hiệu giữ đối tượng lâu bất thường.

### 8.4. Tạo heap dump khi hết bộ nhớ

Có thể yêu cầu JVM tạo heap dump khi gặp OutOfMemoryError:

~~~powershell
java -Xmx1g -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./heapdump.hprof -jar app.jar
~~~

Heap dump có thể chứa dữ liệu nhạy cảm trong bộ nhớ ứng dụng. Hãy bảo vệ file dump, giới hạn quyền truy cập và bảo đảm đĩa còn đủ dung lượng. Phân tích dump bằng công cụ phù hợp để tìm đối tượng chiếm nhiều bộ nhớ và chuỗi tham chiếu giữ chúng sống.

## 9. Garbage collector và heap sizing

Heap được garbage collector quản lý. Heap option đặt giới hạn dung lượng; garbage collector quyết định cách thu hồi và tổ chức vùng nhớ trong giới hạn đó.

Một số collector phổ biến trong HotSpot:

- G1 GC: collector tổng quát, chia heap thành các region và cân bằng throughput với mục tiêu pause.
- Parallel GC: ưu tiên throughput bằng cách dùng nhiều thread cho các giai đoạn GC.
- ZGC: collector có mục tiêu pause ngắn, phù hợp một số ứng dụng heap lớn và yêu cầu độ trễ thấp.
- Serial GC: collector đơn giản, thường phù hợp ứng dụng nhỏ hoặc môi trường tài nguyên hạn chế.

Có thể chỉ định collector, ví dụ:

~~~powershell
java -XX:+UseG1GC -Xms512m -Xmx2g -jar app.jar
~~~

Không nên đổi collector chỉ vì gặp OutOfMemoryError. Trước hết hãy xác định heap có đủ không, đối tượng có được giữ ngoài ý muốn không, và GC log thể hiện áp lực gì. Thay collector có thể thay đổi đặc tính độ trễ, throughput và mức dùng RAM.

Với G1, **-XX:MaxGCPauseMillis** là mục tiêu pause mềm để collector cân nhắc khi lập kế hoạch; đây không phải cam kết rằng mọi lần pause đều ngắn hơn giá trị đó. Heap quá nhỏ so với tải vẫn có thể gây GC thường xuyên dù đã đặt mục tiêu pause.

## 10. Lỗi phổ biến khi cấu hình heap

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Invalid initial heap size hoặc lỗi option | Giá trị -Xms sai cú pháp hoặc đơn vị | Kiểm tra hậu tố k, m, g và cách viết số |
| Initial heap size set to a larger value than the maximum heap size | -Xms lớn hơn -Xmx | Đặt heap ban đầu nhỏ hơn hoặc bằng heap tối đa |
| OutOfMemoryError: Java heap space | Heap tối đa không đủ, tải cấp phát lớn hoặc giữ tham chiếu không cần thiết | Phân tích heap dump và GC log; tăng -Xmx chỉ sau khi đo và kiểm tra RAM |
| GC overhead limit exceeded | JVM dành quá nhiều thời gian cho GC nhưng thu hồi được rất ít heap | Tìm object retention, workload bất thường hoặc heap quá nhỏ |
| OutOfMemoryError: Metaspace | Quá nhiều class metadata hoặc classloader không được giải phóng | Phân tích class loading và classloader lifecycle; đánh giá metaspace limit |
| Container bị kill dù heap chưa đầy | Tổng RAM gồm native memory vượt giới hạn | Kiểm tra RSS, direct memory, metaspace, thread stack và container limit |
| Không thấy hiệu lực của heap option | Đặt option sau -jar/-m hoặc chạy nhầm Java executable | Đặt option trước phần chạy ứng dụng; kiểm tra java -version và VM.flags |
| Ứng dụng khởi động chậm sau khi đặt heap quá lớn | Heap ban đầu lớn hoặc cấu hình không phù hợp | Đo startup và cân nhắc giảm -Xms |

## 11. Checklist trước khi triển khai heap option

- [ ] Xác định phiên bản Java và đúng executable java đang chạy.
- [ ] Đo heap used, heap committed và mức tăng trưởng trong tải đại diện.
- [ ] Chọn -Xms theo nhu cầu khởi động và tải ban đầu.
- [ ] Chọn -Xmx đủ cho workload nhưng chừa RAM cho native memory và hệ điều hành.
- [ ] Đặt heap option trước -jar, -m hoặc tên lớp chính.
- [ ] Nếu dùng percentage options, xác minh JVM nhận diện đúng RAM hoặc container limit.
- [ ] Bật GC log khi cần phân tích áp lực GC.
- [ ] Có kế hoạch tạo và bảo vệ heap dump khi gặp OutOfMemoryError.
- [ ] Kiểm thử cấu hình dưới tải bình thường, tải cao và lúc khởi động.
- [ ] Theo dõi cả heap và tổng bộ nhớ tiến trình sau khi triển khai.

Heap option là công cụ điều chỉnh dung lượng Java heap, chủ yếu qua -Xms và -Xmx. Hãy chọn chúng dựa trên số liệu sử dụng thực tế và giới hạn RAM của môi trường. Khi lỗi thiếu bộ nhớ xuất hiện, xác định đúng vùng nhớ và phân tích nguyên nhân trước khi tăng giới hạn; heap chỉ là một phần trong tổng bộ nhớ của tiến trình JVM.
