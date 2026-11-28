# Mục tiêu và trạng thái chính thức của Compact Object Headers trong JDK 25

## Mục tiêu bài học

Mỗi object Java trên heap đều có một **object header** do JVM quản lý. Header lưu metadata cần thiết để JVM nhận diện class, theo dõi trạng thái khóa, identity hash code và thông tin phục vụ garbage collector. Với ứng dụng tạo và giữ hàng triệu object nhỏ, phần metadata lặp lại trên từng object có thể chiếm một lượng heap đáng kể.

**Compact Object Headers** là thay đổi trong HotSpot JVM nhằm thu gọn header object trên kiến trúc 64-bit. Theo **JEP 519**, tính năng này được nâng từ experimental trong JDK 24 thành **product feature trong JDK 25**. Khi bật, layout compact giảm header điển hình từ 96 bit (12 byte) xuống 64 bit (8 byte), qua đó giảm heap footprint và có thể cải thiện locality của dữ liệu.

Bài **Mục tiêu và trạng thái chính thức của Compact Object Headers trong JDK 25** thuộc chương **Header đối tượng gọn** của module **JAVA_VERSION_JAVA25**. Bài học tập trung vào trạng thái chính thức của JDK 25, cách bật và xác minh, lợi ích có thể kỳ vọng, giới hạn tương thích và cách đánh giá trên workload thật.

Sau bài học, bạn có thể:

1. Giải thích object header chứa thông tin gì và vì sao header gọn có ích với heap nhiều object nhỏ.
2. Phân biệt layout header truyền thống với Compact Object Headers ở mức khái niệm.
3. Nêu chính xác trạng thái của tính năng trong JDK 24, JDK 25, JDK 26 và JDK 27.
4. Bật tính năng trong JDK 25 bằng JVM option hiện hành và xác minh trạng thái runtime.
5. Phân biệt kích thước header với kích thước tổng thể của object sau căn chỉnh bộ nhớ.
6. Nhận diện ứng dụng có khả năng hưởng lợi và những trường hợp lợi ích thấp.
7. Đánh giá rủi ro với agent, profiler, JVMCI, CDS và công cụ phụ thuộc layout nội bộ.
8. Lập kế hoạch benchmark và rollout có thể rollback.

> **Ghi chú phạm vi hiện hành:** JDK 25 đã chính thức hóa Compact Object Headers nhưng vẫn tắt mặc định. JDK 26 tiếp tục để tùy chọn này tắt mặc định. Từ JDK 27, HotSpot bật Compact Object Headers mặc định theo JEP 534. Bài học phân biệt các mốc này để không nhầm cú pháp thử nghiệm cũ với cách dùng hiện hành.

## 1. Vì sao mỗi object cần header?

JVM không chỉ cần biết các field mà chương trình khai báo. Khi quản lý một object, runtime còn phải biết object thuộc class nào, trạng thái đồng bộ ra sao và cách garbage collector xử lý object trong heap.

Ở mức khái niệm, header truyền thống chứa hai nhóm dữ liệu chính:

- **Mark word:** metadata thay đổi theo trạng thái object, chẳng hạn lock state, identity hash code, GC age và thông tin forwarding cần thiết khi di chuyển object.
- **Class pointer (klass pointer):** tham chiếu tới metadata của class mà object là instance.

Trong cấu hình HotSpot 64-bit thông dụng có compressed class pointers, header truyền thống thường có:

| Thành phần | Kích thước điển hình | Vai trò |
|---|---:|---|
| Mark word | 8 byte | Lock state, hash code, GC metadata |
| Compressed class pointer | 4 byte | Xác định metadata của class |
| **Tổng header** | **12 byte** | Chưa tính các field của object và phần padding |

Một object có thể chỉ chứa một vài field nhỏ nhưng vẫn phải mang header. Nếu một ứng dụng giữ hàng triệu object như node trong graph, entry trong map, DTO nhỏ, object trong cache hoặc cấu trúc cây, phần header lặp lại có thể chiếm đáng kể bộ nhớ.

## 2. Compact Object Headers thay đổi điều gì?

Compact Object Headers tổ chức lại metadata để lưu class pointer đã nén cùng các thông tin của mark word trong một header 64-bit trên HotSpot 64-bit.

~~~mermaid
flowchart TB
    subgraph OLD["Header truyền thống — ví dụ 64-bit với compressed class pointers"]
        A1["Mark word<br/>64 bit"]
        A2["Compressed class pointer<br/>32 bit"]
        A1 --> A2
    end
    subgraph NEW["Compact Object Header"]
        B1["Một header 64-bit<br/>Class metadata + hash + GC/lock bits"]
    end
    OLD -->|"JEP 519"| NEW
~~~

So sánh ở mức kích thước header:

| Layout | Header điển hình trên HotSpot 64-bit | Ghi chú |
|---|---:|---|
| Truyền thống với compressed class pointers | 96 bit / 12 byte | Mark word 64 bit + class pointer nén 32 bit |
| Truyền thống không nén class pointer | Có thể 128 bit / 16 byte | Phụ thuộc cấu hình JVM |
| Compact Object Headers | 64 bit / 8 byte | Gói metadata vào một header nhỏ hơn |

Đây là thay đổi **layout nội bộ của HotSpot**. Java source code, public Java API và bytecode không cần thay đổi chỉ vì bật tính năng này. Một class vẫn được khai báo, tạo instance, đồng bộ và thu gom rác theo ngữ nghĩa Java thông thường.

### 2.1. Những thông tin vẫn cần được biểu diễn

Header compact vẫn phải cung cấp thông tin để JVM:

- Nhận diện class của object.
- Lưu identity hash code khi được yêu cầu.
- Theo dõi trạng thái khóa và trạng thái monitor cần thiết.
- Lưu thông tin tuổi object phục vụ GC.
- Hỗ trợ các trạng thái nội bộ cần cho quá trình di chuyển object.

Compact không loại bỏ những metadata đó. JVM thay đổi cách mã hóa và sắp xếp bit để đưa chúng vào một cấu trúc nhỏ hơn.

### 2.2. Vì sao không thể coi header là một cấu trúc Java thông thường?

Object header không phải field do lập trình viên khai báo. Bạn không thể truy cập header bằng getter, reflection thông thường hay một API Java SE tiêu chuẩn. Layout cụ thể thuộc về implementation của JVM và có thể thay đổi giữa:

- HotSpot và các JVM implementation khác.
- Phiên bản JDK.
- Kiến trúc CPU.
- Tùy chọn JVM và cấu hình runtime.

Vì vậy, không viết ứng dụng phụ thuộc vào offset hoặc cách mã hóa bit cụ thể của header. Công cụ cần đọc layout phải tương thích với đúng JVM đang chạy.

## 3. Trạng thái chính thức qua các phiên bản

Đây là phần cần nhớ nhất khi làm việc với JDK hiện hành:

| Phiên bản | Trạng thái | Cách sử dụng |
|---|---|---|
| **JDK 24 — JEP 450** | Experimental | Cần bật experimental VM options trước khi bật tính năng |
| **JDK 25 — JEP 519** | **Product feature, tắt mặc định** | Bật bằng `-XX:+UseCompactObjectHeaders` |
| **JDK 26** | Product feature, tiếp tục tắt mặc định | Bật tường minh bằng `-XX:+UseCompactObjectHeaders` |
| **JDK 27 — JEP 534** | **Bật mặc định** | Không cần thêm option để sử dụng layout compact |

JEP 519 là bước chuyển từ experimental sang product feature. Điều này có nghĩa tính năng đã được tích hợp như một tùy chọn HotSpot được hỗ trợ chính thức, không còn cần cờ mở khóa experimental.

JEP 534 trong JDK 27 chuyển sang bật mặc định. Nếu cần điều tra tương thích trên JDK 27, release notes vẫn ghi nhận có thể tạm tắt bằng `-XX:-UseCompactObjectHeaders`; tùy chọn tắt này được dự kiến deprecate và loại bỏ trong một phiên bản tương lai.

### 3.1. Không dùng cú pháp experimental cũ cho JDK 25

Trong JDK 24, tính năng ở trạng thái experimental. Cú pháp lịch sử là:

~~~bash
# Chỉ để nhận diện cú pháp ở giai đoạn JDK 24 experimental.
# Không dùng làm cấu hình hướng dẫn cho JDK 25 trở lên.
java -XX:+UnlockExperimentalVMOptions -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Với JDK 25, cú pháp hiện hành là:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Không cần `-XX:+UnlockExperimentalVMOptions`. Cờ mở khóa đó không còn là yêu cầu để sử dụng Compact Object Headers trong JDK 25.

## 4. Bật Compact Object Headers trong JDK 25

JDK 25 mặc định tắt layout compact. Để bật trong một lần chạy:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

Nếu chạy class trực tiếp:

~~~bash
java -XX:+UseCompactObjectHeaders -cp app.jar com.example.Main
~~~

Nếu chạy trong container, đặt option vào JVM arguments của process thực tế. Ví dụ Docker ENTRYPOINT:

~~~dockerfile
ENTRYPOINT [
  "java",
  "-XX:+UseCompactObjectHeaders",
  "-jar",
  "/application/app.jar"
]
~~~

Với Kubernetes, có thể đặt trong `command`/`args`, biến cấu hình JVM của image hoặc cơ chế startup script của nền tảng. Cần xác nhận option thực sự được truyền tới process Java, không chỉ được khai báo trong một file cấu hình chưa được dùng.

### 4.1. Tắt để so sánh baseline trên JDK 25

Vì JDK 25 tắt mặc định, baseline không cần option bật:

~~~bash
java -jar app.jar
~~~

Có thể chỉ định rõ trạng thái tắt khi muốn so sánh hai lần chạy:

~~~bash
java -XX:-UseCompactObjectHeaders -jar app.jar
~~~

Dùng cùng một JDK build, cùng ứng dụng, heap, GC, CPU quota và workload. Không thay đổi đồng thời nhiều tùy chọn JVM khác.

### 4.2. Xác minh flag có hiệu lực

Dùng `PrintFlagsFinal` để kiểm tra giá trị JVM đã chọn:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Trên Linux/macOS, lọc kết quả:

~~~bash
java -XX:+PrintFlagsFinal -version | grep UseCompactObjectHeaders
~~~

Trên PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version | Select-String UseCompactObjectHeaders
~~~

Khi chạy JDK 25 không truyền option bật, giá trị mặc định là `false`. Khi thêm `-XX:+UseCompactObjectHeaders`, giá trị phải là `true` và output thường ghi nguồn thiết lập là command line.

Ví dụ kiểm tra khi bật:

~~~bash
java -XX:+UseCompactObjectHeaders -XX:+PrintFlagsFinal -version
~~~

Không chỉ kiểm tra biến môi trường hoặc Dockerfile. Hãy kiểm tra **JVM process đang chạy**, vì launcher, script hoặc cấu hình nền tảng có thể thay đổi arguments cuối cùng.

### 4.3. Phân biệt flag product với API Java

`UseCompactObjectHeaders` là **HotSpot VM option**, không phải API trong `java.lang` hay một tính năng cú pháp Java. Do đó:

- Không cần thay đổi source code để bật.
- Không cần thêm dependency Maven/Gradle.
- Không có annotation hoặc method Java để chuyển layout.
- Cần kiểm tra đúng JVM implementation và phiên bản có hỗ trợ flag.
- Không giả định mọi vendor JVM đều có cùng tùy chọn hoặc cùng layout nội bộ.

## 5. Tính năng ảnh hưởng đến kích thước object như thế nào?

Header là một phần của object, không phải toàn bộ object. Tổng kích thước còn phụ thuộc:

- Các field primitive và reference.
- Field layout do JVM sắp xếp.
- Metadata bổ sung của array như chiều dài.
- Object alignment và padding.
- Cấu hình compressed references.
- Kiến trúc và implementation của JVM.

Ví dụ minh họa với một object nhỏ:

~~~java
public final class Coordinate {
    private int x;
    private int y;
}
~~~

Với layout truyền thống, header điển hình 12 byte cộng 8 byte field cho hai số nguyên. Với compact header, phần header giảm còn 8 byte. Tuy nhiên, tổng kích thước object cuối cùng được căn chỉnh theo quy tắc của JVM; không thể kết luận mọi object đều giảm đúng 4 byte.

Một số object có thể tiết kiệm nhiều hơn hoặc ít hơn sau khi tính padding. Có object mà phần giảm của header được hấp thụ bởi alignment nên tổng kích thước quan sát được không thay đổi. Vì thế, khi đánh giá ứng dụng, hãy đo **tổng heap footprint và live set**, không chỉ nhân số lượng object với 4 byte.

### 5.1. Khi nào lợi ích dễ nhận thấy?

Lợi ích thường đáng chú ý hơn khi heap có rất nhiều object nhỏ:

- Entry của `HashMap` và các node trong collection.
- Object đại diện cho node của graph hoặc cây.
- DTO, record và domain object nhỏ được giữ lâu.
- Object trong cache và session store.
- Object trung gian của parser, compiler hoặc xử lý dữ liệu.
- Các cấu trúc có số lượng object lớn so với lượng dữ liệu primitive/reference trong mỗi object.

Nếu ứng dụng chủ yếu giữ một vài mảng primitive lớn, byte buffer hoặc dữ liệu off-heap, object header có thể chỉ chiếm phần nhỏ của tổng bộ nhớ.

### 5.2. Không đồng nhất giảm header với giảm heap theo cùng tỷ lệ

Giả sử header giảm từ 12 byte xuống 8 byte trong một cấu hình thông dụng. Đó là giảm 4 byte ở **phần header**, không có nghĩa toàn bộ heap giảm 33%.

Nếu object có payload 100 byte, giảm 4 byte là tỷ lệ nhỏ. Nếu object gần như chỉ có header và vài field, tác động tương đối có thể lớn hơn. Ngoài ra, alignment có thể làm số byte tiết kiệm thực tế khác nhau.

Không sử dụng một tỷ lệ benchmark từ ứng dụng khác như cam kết cho dịch vụ của mình. Tác động phụ thuộc object count, object shape, heap occupancy, GC, workload và nền tảng.

## 6. Ảnh hưởng tới GC, cache locality và hiệu năng

Khi cùng một tập object chiếm ít byte heap hơn, ứng dụng có thể nhận được một số lợi ích:

1. **Heap footprint thấp hơn:** cùng dữ liệu sống có thể cần ít dung lượng heap hơn.
2. **Deployment density tốt hơn:** workload có thể cần ít memory hơn trong container hoặc máy chủ.
3. **GC pressure có thể giảm:** nếu live heap nhỏ hơn, collector có thể xử lý ít byte dữ liệu hơn trong một số tình huống.
4. **Data locality có thể tốt hơn:** nhiều object có thể nằm gần nhau hơn trong cùng vùng bộ nhớ/cache line.
5. **Throughput/latency có thể cải thiện:** tùy workload và chi phí xử lý layout mới.

Đây là các khả năng, không phải bảo đảm. Compact header cũng thay đổi cách JVM mã hóa và truy cập một số metadata; một workload cụ thể có thể không cải thiện hoặc có trade-off hiệu năng. Đo trên ứng dụng thực tế là điều kiện trước khi rollout.

### 6.1. Compact Object Headers không phải garbage collector

Tính năng này thay đổi layout header của object trong HotSpot. Nó không thay thế G1, Parallel, ZGC, Shenandoah hoặc chính sách GC khác. Việc chọn collector vẫn là quyết định riêng dựa trên throughput, pause time, CPU, memory và đặc điểm workload.

Không dùng `UseCompactObjectHeaders` như một cách thay đổi collector. Khi benchmark, giữ GC giống nhau giữa baseline và compact để tách ảnh hưởng của header khỏi ảnh hưởng của collector.

### 6.2. Không phải mọi workload đều hưởng lợi như nhau

| Kiểu workload | Khả năng hưởng lợi | Lý do |
|---|---|---|
| Nhiều object nhỏ, sống lâu | Có thể cao | Header chiếm tỷ lệ lớn hơn trong live set |
| Map/graph/cache nhiều node | Có thể cao | Số lượng object lớn |
| Nhiều object wrapper hoặc DTO nhỏ | Có thể đáng kể | Chi phí header lặp lại nhiều lần |
| Chủ yếu mảng primitive lớn | Thường thấp hơn | Payload mảng chiếm phần lớn |
| Direct buffer/off-heap | Thấp | Bộ nhớ chính nằm ngoài heap object |
| Một vài object rất lớn | Thường thấp | Header nhỏ so với payload |

## 7. Những giới hạn và điều kiện tương thích

Compact Object Headers là thay đổi trong implementation của HotSpot. Khi bật, cần quan tâm tới:

- **Kiến trúc:** tính năng nhắm tới JVM 64-bit; không suy rộng sang 32-bit.
- **Compressed class pointers:** layout compact sử dụng class pointer được nén; không cấu hình JVM theo cách vô hiệu hóa điều kiện cần này.
- **Số lượng class:** encoding class pointer compact có không gian biểu diễn hữu hạn. Ứng dụng nạp số lượng class cực lớn cần kiểm tra điều kiện thực tế và giới hạn của JVM.
- **JVMCI/compiler:** các thành phần compiler tích hợp sâu với JVM cần hỗ trợ layout mới.
- **Native agent/profiler:** công cụ đọc trực tiếp object header hoặc dựa vào offset nội bộ phải tương thích.
- **CDS archive:** archive cần được tạo cho cấu hình header tương ứng.
- **Vendor/runtime:** không giả định mọi JVM có cùng flag và layout.

### 7.1. Tránh phụ thuộc vào object header trong code ứng dụng

Không sử dụng:

- Offset nội bộ của mark word hoặc klass pointer.
- `Unsafe` để đọc/ghi bit header dựa trên giả định layout.
- JNI/JVMTI agent giả định object header luôn có kích thước cố định.
- Serializer hoặc profiler truy cập trực tiếp layout object mà không hỗ trợ phiên bản JVM đang chạy.

Các API Java thông thường không cần thay đổi. Rủi ro chủ yếu nằm ở code native, agent, công cụ chẩn đoán hoặc thư viện phụ thuộc vào chi tiết nội bộ của VM.

### 7.2. Lưu ý về compressed class pointer option

Tùy chọn `UseCompressedClassPointers` đã bị deprecated trong JDK 25 và bị loại bỏ trong JDK 27. Không dùng `-XX:-UseCompressedClassPointers` như cách điều chỉnh Compact Object Headers hoặc làm cấu hình khuyến nghị cho ứng dụng mới.

JDK 27 luôn dùng compressed class pointers trong object. Khi nâng cấp, loại bỏ option cũ khỏi script và JVM arguments theo hướng dẫn của release notes.

## 8. CDS và custom runtime image

JDK 25 cung cấp các CDS archive riêng để hỗ trợ cấu hình compact headers. Với custom runtime image tạo bằng `jlink`, Oracle ghi chú cần tạo archive tương ứng sau khi tạo image.

Ví dụ với custom image:

~~~bash
<image>/bin/java -XX:+UseCompactObjectHeaders -Xshare:dump
~~~

Lệnh này tạo archive `classes_coh.jsa` cho cấu hình Compact Object Headers. Nếu ứng dụng có cấu hình đặc biệt dùng compressed ordinary object pointers khác mặc định, hãy đọc release notes và tạo archive phù hợp; không thay đổi các pointer options chỉ để thử tính năng.

CDS archive phải khớp cấu hình JVM. Nếu thay đổi layout object header giữa lúc tạo archive và chạy ứng dụng, JVM có thể không dùng archive như mong đợi. Hãy kiểm tra log CDS và giữ cấu hình tạo archive nhất quán với runtime.

## 9. Cách đo layout object

Có thể dùng **Java Object Layout (JOL)** để quan sát layout object trên JVM đang chạy. JOL là công cụ độc lập, không phải API Java SE hay công cụ mặc định bắt buộc của JDK.

Ví dụ class cần quan sát:

~~~java
package com.example.memory;

public final class Customer {
    private long id;
    private int tier;
    private boolean active;
    private String name;
}
~~~

Ví dụ dùng JOL API:

~~~java
package com.example.memory;

import org.openjdk.jol.info.ClassLayout;

public final class ObjectLayoutDemo {

    public static void main(String[] args) {
        System.out.println(
                ClassLayout.parseClass(Customer.class).toPrintable()
        );
    }
}
~~~

Chạy cùng chương trình hai lần với cùng JDK:

~~~bash
# Baseline: JDK 25 mặc định tắt Compact Object Headers.
java -cp "app.jar:jol-core.jar" com.example.memory.ObjectLayoutDemo

# Thử layout compact.
java -XX:+UseCompactObjectHeaders \
     -cp "app.jar:jol-core.jar" \
     com.example.memory.ObjectLayoutDemo
~~~

Ví dụ dùng dấu phân cách classpath của Linux/macOS. Trên Windows, dùng dấu chấm phẩy. Cần bảo đảm `Customer` và JOL nằm trong classpath thực tế.

Kết quả JOL cho biết layout mà JVM quan sát được trong process cụ thể. Đây là bằng chứng ở mức class/object layout, chưa thay thế benchmark heap toàn ứng dụng.

## 10. Benchmark trước và sau khi bật

Để xác định lợi ích, chạy hai cấu hình:

~~~bash
# Baseline trên JDK 25.
java -Xms2g -Xmx2g -jar app.jar
~~~

~~~bash
# Compact Object Headers trên JDK 25.
java -Xms2g -Xmx2g \
     -XX:+UseCompactObjectHeaders \
     -jar app.jar
~~~

Giữ cố định:

- JDK vendor, version và build.
- OS, CPU architecture và container limits.
- Heap size, GC, JVM options khác.
- Application artifact và dependency.
- Dataset, số request, concurrency và thời gian warm-up.
- Các external services và cấu hình kết nối.

Đo các chỉ số:

| Chỉ số | Vì sao cần đo |
|---|---|
| Live heap sau workload ổn định | Xác định dữ liệu sống chiếm bao nhiêu heap |
| Heap occupancy và GC frequency | Quan sát áp lực bộ nhớ và collector |
| Allocation rate | Kiểm tra thay đổi có ảnh hưởng workload tạo object không |
| CPU utilization | Xác định chi phí runtime tổng thể |
| Throughput | Đo lượng công việc hoàn thành |
| p50/p95/p99 latency | Phát hiện ảnh hưởng tới tail latency |
| RSS/container memory | Xác định tác động tới giới hạn memory của container |
| Object layout với JOL | Kiểm tra header và field packing của class mẫu |

Không chỉ so sánh `Runtime.freeMemory()` ngay sau startup. Số liệu tức thời chịu ảnh hưởng của allocation, GC và heap expansion. Hãy chạy workload đại diện đủ lâu và so sánh nhiều lần.

### 10.1. Đọc kết quả benchmark

Giả sử kết quả thử nghiệm:

| Chỉ số | Baseline | Compact | Diễn giải |
|---|---:|---:|---|
| Live heap | 1,4 GB | 1,25 GB | Live set giảm trong workload này |
| GC count/10 phút | 14 | 12 | Có thể do heap pressure thấp hơn |
| CPU | 62% | 59% | Có cải thiện trong cấu hình thử |
| p95 | 120 ms | 116 ms | Cần xác nhận qua nhiều lần chạy |

Các con số chỉ là dữ liệu minh họa, không phải kết quả cam kết của JEP 519. Nếu heap giảm nhưng p99 tăng, cần điều tra nguyên nhân thay vì chỉ nhìn mức tiết kiệm memory.

### 10.2. Khi nào nên bật trong production?

Cân nhắc bật trên JDK 25 sau khi:

1. Kiểm tra vendor/runtime hỗ trợ.
2. Xác nhận agent, profiler, native library và framework tương thích.
3. Benchmark staging bằng workload gần production.
4. Kiểm tra CDS archive nếu dùng custom runtime image.
5. Canary một phần traffic hoặc một nhóm instance.
6. Theo dõi heap, GC, CPU, throughput, p95/p99 và restart.
7. Mở rộng rollout khi các chỉ số đạt ngưỡng đã thống nhất.

Không bật đồng loạt chỉ vì header nhỏ hơn. Cần có bằng chứng từ workload của ứng dụng.

## 11. Khác biệt khi nâng cấp lên JDK 27

Trong JDK 27, Compact Object Headers đã bật mặc định theo **JEP 534**. Vì vậy, khi chuyển từ JDK 25/26 lên JDK 27, ứng dụng có thể chuyển từ layout truyền thống sang compact mà không thêm JVM flag.

Bảng kiểm khi nâng cấp:

| Hạng mục | JDK 25 | JDK 26 | JDK 27 |
|---|---|---|---|
| Trạng thái COH | Product feature | Product feature | Default layout |
| Mặc định | Tắt | Tắt | Bật |
| Bật tường minh | `-XX:+UseCompactObjectHeaders` | `-XX:+UseCompactObjectHeaders` | Không cần |
| Tắt tạm thời | `-XX:-UseCompactObjectHeaders` | `-XX:-UseCompactObjectHeaders` | Có thể dùng opt-out, dự kiến deprecated/removal |
| `UseCompressedClassPointers` | Deprecated | Deprecated | Removed/obsolete |

Khi nâng JDK, cần test ứng dụng với layout mặc định mới. Đặc biệt chú ý các agent hoặc thư viện native có thể dựa vào object layout nội bộ.

### 11.1. Không dùng opt-out như cấu hình lâu dài

JDK 27 cho phép tạm thời tắt Compact Object Headers bằng:

~~~bash
java -XX:-UseCompactObjectHeaders -jar app.jar
~~~

Đây là công cụ chẩn đoán hoặc tương thích tạm thời khi cần cô lập regression. Oracle ghi nhận tùy chọn này được dự kiến deprecate và loại bỏ trong tương lai. Không xây chiến lược vận hành lâu dài dựa vào việc tắt tính năng mặc định mới.

### 11.2. Bỏ option đã deprecated/removed

Không giữ cấu hình cũ:

~~~text
-XX:-UseCompressedClassPointers
~~~

Tùy chọn này bị deprecated trong JDK 25 và bị loại bỏ trong JDK 27. Hãy rà soát:

- Dockerfile và entrypoint.
- Kubernetes Deployment/StatefulSet.
- Script khởi chạy JVM.
- Helm values và ConfigMap.
- Biến môi trường `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS`.
- Cấu hình CI/CD và service manager.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Flag không được nhận diện | JVM vendor/version không hỗ trợ option | Xác minh `java -version` và HotSpot implementation |
| JDK 25 vẫn hiện `false` | Chưa truyền `-XX:+UseCompactObjectHeaders` vào JVM thực tế | Kiểm tra command line và `PrintFlagsFinal` |
| JVM không dùng CDS archive | Archive được tạo với layout khác | Tạo archive phù hợp bằng đúng runtime image và option |
| JOL không cho thấy header như mong đợi | Chạy nhầm JDK hoặc process chưa bật option | Xác minh JVM flags trong chính process chạy JOL |
| Heap không giảm đáng kể | Workload ít object nhỏ hoặc payload chiếm phần lớn | Phân tích object count, live set và object shape |
| p95/p99 xấu đi | Layout mới làm thay đổi đặc tính runtime hoặc biến động workload | Lặp benchmark, kiểm tra CPU/GC và agent |
| Native agent gặp lỗi | Agent phụ thuộc object layout nội bộ | Cập nhật agent hoặc xác nhận hỗ trợ Compact Object Headers |
| JVMCI/compiler không tương thích | Compiler tích hợp chưa hỗ trợ layout | Kiểm tra tài liệu vendor và cấu hình runtime |
| JDK 27 có kết quả khác JDK 25 | JDK 27 bật compact mặc định và có thay đổi runtime khác | So sánh flag thực tế và tách ảnh hưởng phiên bản |
| Script báo option deprecated | Còn dùng `UseCompressedClassPointers` | Gỡ option đã deprecated/removed khỏi cấu hình |

## 13. Bài thực hành tổng hợp

Bạn có một dịch vụ Java quản lý danh mục sản phẩm với nhiều object nhỏ: `Product`, `Category`, `Price`, `InventoryEntry` và các node trong cache. Heap live set tăng cao khi tải dữ liệu lớn.

Thực hiện:

1. Ghi nhận JDK vendor/version, OS và CPU architecture.
2. Xác minh trạng thái `UseCompactObjectHeaders` bằng `PrintFlagsFinal`.
3. Dùng JOL quan sát layout của một số class đại diện.
4. Chạy baseline trên JDK 25 không bật compact header.
5. Bật `-XX:+UseCompactObjectHeaders` và chạy cùng workload.
6. Đo live heap, GC count, CPU, throughput và p95/p99.
7. Thử một workload nhiều object nhỏ và một workload chủ yếu là mảng primitive lớn.
8. So sánh sự khác nhau để xác định loại dữ liệu nào hưởng lợi.
9. Kiểm tra các agent/profiler và CDS archive nếu ứng dụng sử dụng chúng.
10. Viết kế hoạch canary và rollback cho production.
11. Chạy lại kiểm thử trên JDK 27 để xác minh layout mặc định và loại bỏ các JVM option đã deprecated.

**Sản phẩm nghiệm thu:** bảng JOL trước/sau, lệnh JVM, kết quả benchmark, báo cáo compatibility và quyết định bật/tạm hoãn theo dữ liệu thực tế.

## 14. Checklist áp dụng hiện đại

- Dùng JDK 25 trở lên và xác nhận HotSpot hỗ trợ Compact Object Headers.
- Trong JDK 25/26, bật bằng `-XX:+UseCompactObjectHeaders` nếu muốn sử dụng.
- Không thêm `-XX:+UnlockExperimentalVMOptions` cho JDK 25 trở lên.
- Nhận biết JDK 27 bật Compact Object Headers mặc định.
- Không phụ thuộc `UseCompressedClassPointers`; option này đã deprecated và bị loại bỏ ở JDK 27.
- Đánh giá object count và live heap trước khi kỳ vọng tiết kiệm bộ nhớ.
- Dùng JOL để kiểm tra layout, benchmark để kiểm tra lợi ích ứng dụng.
- Kiểm tra agent, profiler, JVMCI/compiler và native integration.
- Tạo CDS archive tương ứng nếu dùng custom `jlink` runtime image.
- Đo throughput và tail latency cùng với heap/GC.
- Rollout có kiểm soát và giữ khả năng rollback trong giai đoạn đánh giá.
- Không dùng kết quả benchmark của hệ thống khác làm cam kết hiệu năng.

## Tài liệu tham khảo chính thức

- [JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519): chuyển Compact Object Headers thành product feature trong JDK 25.
- [JEP 450 — Compact Object Headers (Experimental)](https://openjdk.org/jeps/450): lịch sử thiết kế và giai đoạn experimental trong JDK 24.
- [Oracle JDK 25 Release Notes — UseCompactObjectHeaders Is a Product Option](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): flag, trạng thái mặc định và CDS archives.
- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận tính năng được nâng thành product feature.
- [Oracle JDK 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): xác nhận option tiếp tục tắt mặc định trong JDK 26.
- [JEP 534 — Compact Object Headers by Default](https://openjdk.org/jeps/534): bật compact header mặc định trong JDK 27.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): trạng thái default-on và lộ trình loại bỏ option tắt.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp JVM option trong JDK 25.
- [Java Object Layout (JOL)](https://openjdk.org/projects/code-tools/jol/): công cụ quan sát layout object của JVM.
