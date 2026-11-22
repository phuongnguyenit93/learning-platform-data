# Chia sẻ dữ liệu chỉ đọc giữa nhiều tiến trình JVM với AppCDS

*Chủ đề cha: Nền tảng AppCDS (Java 10). Bài Knowledge này giải thích cơ chế Class Data Sharing (CDS) và Application Class-Data Sharing (AppCDS) giúp nhiều tiến trình JVM cùng ánh xạ những trang dữ liệu lớp có thể chia sẻ ở chế độ chỉ đọc, từ đó có thể giảm chi phí bộ nhớ và thời gian khởi động. Trọng tâm là **những gì được chia sẻ, những gì vẫn riêng cho từng process, cách thiết lập/kiểm chứng trên JDK hiện đại và những giới hạn thực tế**. Ví dụ hoàn chỉnh tương thích Java 17 trở lên.*

## 1. Tóm tắt cốt lõi

Khi bạn chạy hai ứng dụng Java bằng hai lệnh `java` riêng biệt, hệ điều hành tạo **hai tiến trình JVM**, mỗi tiến trình có không gian địa chỉ ảo và Java heap riêng. Bình thường, mỗi JVM phải xử lý công việc nạp và biểu diễn metadata của nhiều class mà ứng dụng sử dụng. Nếu các JVM cùng một host chạy một tập class tương thích, việc để mỗi tiến trình giữ bản riêng của mọi dữ liệu lớp có thể gây trùng lặp.

**CDS/AppCDS** xử lý một phần trùng lặp ấy bằng cách lưu dữ liệu lớp đã được chuẩn bị trong một **shared archive** (thường là tệp `.jsa`). Khi khởi động, các JVM có thể **memory-map** (ánh xạ bộ nhớ) archive. Những trang của archive có thể ánh xạ **chỉ đọc và dùng chung** sẽ được hệ điều hành dùng chung trong RAM giữa các tiến trình, thay vì tạo một bản sao riêng cho mỗi JVM.

Cấu trúc ý tưởng:

```text
                     MỘT HOST / MỘT HỆ ĐIỀU HÀNH

       archive AppCDS: app.jsa (lưu trên file system)
                           |
                    memory mapping
                           |
            +--------------+--------------+
            |                             |
       Tiến trình JVM A               Tiến trình JVM B
       +------------------+            +------------------+
       | Trang metadata   |            | Trang metadata   |
       | lớp chia sẻ (RO) |<-- OS ----->| lớp chia sẻ (RO) |
       | dùng cùng backing pages        | dùng cùng pages   |
       +------------------+            +------------------+
       | Java heap A      |            | Java heap B      |
       | static state A   |            | static state B   |
       | threads, stack A |            | threads, stack B |
       | writable data A  |            | writable data B  |
       +------------------+            +------------------+
```

Trong sơ đồ, `RO` là *read-only*. Đây là khái niệm về **trang bộ nhớ và metadata của HotSpot**, không phải một tính năng cho phép hai ứng dụng chia sẻ mọi đối tượng Java.

**Ba câu quan trọng:**

1. **Chia sẻ dữ liệu lớp đọc-only:** hệ điều hành có thể map cùng các trang của archive vào nhiều JVM trên cùng host.
2. **Không chia sẻ Java heap của ứng dụng:** biến `static` có thể thay đổi, dữ liệu phiên người dùng, cache trong heap, thread, stack và trạng thái xử lý vẫn thuộc từng tiến trình.
3. **Không đồng nghĩa giảm RAM chính xác bằng kích thước archive nhân số tiến trình:** chỉ những trang thực sự dùng chung mới tiết kiệm bộ nhớ vật lý tương ứng; các phần riêng, chi phí mapping và cách hệ điều hành báo cáo bộ nhớ còn ảnh hưởng.

## 2. Mục tiêu học tập

Sau bài học bạn có thể:

1. Giải thích sự khác biệt giữa CDS và AppCDS, kể cả bối cảnh JEP 310 trong Java 10.
2. Mô tả cách archive `.jsa` được memory-map và vì sao nhiều JVM có thể dùng chung trang read-only.
3. Phân biệt metadata của class đã archive với Java heap, biến `static`, đối tượng và GC state từng process.
4. Biết lý do AppCDS có thể giúp ứng dụng khởi động nhanh và giảm memory footprint khi chạy nhiều JVM.
5. Tạo một archive AppCDS động bằng `-XX:ArchiveClassesAtExit` trên JDK 17+, sau đó dùng lại với `-XX:SharedArchiveFile`.
6. Kiểm chứng lớp ứng dụng thực sự lấy từ shared archive bằng `-Xlog:class+load=info` thay vì chỉ thấy tệp `.jsa` tồn tại.
7. Chạy nhiều process với cùng archive và hiểu vì sao kết quả biến `static` của từng process khác với metadata chia sẻ.
8. Biết tạo static CDS archive khi cần, phân biệt đường đi class-list/dump với dynamic archive.
9. Nhận diện các giới hạn JDK build, classpath/JAR, module, class loader, cờ JVM và archive không tương thích.
10. Đọc các chỉ số RSS/PSS/private memory mà không khẳng định sai rằng mọi bản đồ bộ nhớ đều là RAM riêng.
11. Tổ chức triển khai archive read-only, kiểm soát quyền sửa, versioning và fallback khi nâng cấp ứng dụng.
12. Biết khi nào AppCDS **không** thể thay thế cache dùng chung, IPC hoặc chia sẻ dữ liệu nghiệp vụ.

## 3. CDS khác AppCDS ở điểm nào?

| Khái niệm | Vai trò | Phạm vi điển hình |
| --- | --- | --- |
| **CDS** — Class Data Sharing | Lưu và tái sử dụng dữ liệu lớp đã chuẩn bị | Các class nền tảng của runtime/JDK |
| **AppCDS** — Application Class-Data Sharing | Mở rộng CDS đến class của ứng dụng và thư viện đủ điều kiện | Class được tải từ ứng dụng, các JAR phụ thuộc |
| **Shared archive** | Tệp chứa dạng biểu diễn class mà JVM có thể tái sử dụng khi load | Thường có đuôi `.jsa` |
| **Memory mapping** | OS ánh xạ một vùng tệp vào không gian địa chỉ ảo của process | Các trang read-only có thể dùng chung |
| **Dynamic CDS archive** | Archive bổ sung có thể được tạo từ các class tải trong lúc ứng dụng chạy | Cơ chế `ArchiveClassesAtExit` |
| **Static CDS archive** | Archive được tạo bằng bước dump riêng | Cơ chế `-Xshare:dump` cùng class-list khi cần |

**Mốc lịch sử đúng:**

- CDS cho class nền tảng đã tồn tại trước Java 10.
- **JEP 310 — Application Class-Data Sharing**, nhắm đến **Java 10**, mở rộng cơ chế chia sẻ sang các class ứng dụng.
- **JDK 12** cung cấp default CDS archive đóng gói sẵn trong nhiều bản phân phối, giúp việc sử dụng CDS cho class nền tảng thường tự động.
- **JEP 350 — Dynamic CDS Archives**, được triển khai từ **JDK 13**, đơn giản hóa việc xây archive cho class ứng dụng bằng cách lưu khi process kết thúc.
- Trên JDK 17+ và nhiều JDK hiện đại, cả default CDS và AppCDS vẫn hữu ích. Không cần dùng những cờ thương mại/cấu hình được mô tả trong các hướng dẫn AppCDS rất cũ.

**Không nên nói toàn bộ AppCDS chỉ hoạt động đúng ở Java 10.** Đó là thời điểm JEP 310 ra mắt tính năng; cách tạo, phạm vi hỗ trợ và tối ưu tiếp tục được phát triển ở các phiên bản sau.

## 4. Dữ liệu gì thực sự được chia sẻ?

### 4.1. Metadata lớp: đối tượng của việc chia sẻ

Khi tải class, HotSpot xử lý bytecode, constant pool, cấu trúc lớp, quan hệ class và các metadata liên quan. Archive CDS/AppCDS chứa **một số dữ liệu lớp ở dạng JVM có thể tái sử dụng nhanh hơn** so với việc xử lý toàn bộ từ các JAR hay runtime image.

Các trang metadata đã archive đủ điều kiện có thể được ánh xạ từ **cùng tệp archive** vào không gian địa chỉ của nhiều JVM. Những trang read-only không cần copy riêng để các JVM chỉ *đọc* chúng.

Ví dụ có hai service Java sử dụng cùng các thư viện nền tảng và một JAR chung. Nếu cả hai có thể sử dụng **cùng archive tương thích**, hệ điều hành có cơ hội giữ phần metadata chỉ đọc được dùng chung trong RAM.

### 4.2. Không phải mọi byte archive đều bắt buộc được chia sẻ

Một JVM vẫn có dữ liệu phải ghi hoặc xây dựng riêng khi chạy. Một số vùng được map là read-only, một số metadata/state cần xử lý hoặc ghi có thể nằm trong vùng riêng, và trên một số hệ thống có thể có **copy-on-write** (COW).

Do đó, không khẳng định:

- “Toàn bộ archive `app.jsa` đều là một khối RAM duy nhất cho mọi JVM.”
- “Mọi class xuất hiện trong archive đều phải được load từ archive khi chạy.”
- “Mọi trang virtual memory được map đều đã nằm vật lý trong RAM.”
- “Có archive 20 MB thì chắc chắn tiết kiệm đúng 20 MB cho mỗi JVM tiếp theo.”

Hiệu quả phụ thuộc tập class thực sự được dùng, cách JVM map archive, chính sách OS, classpath, mức độ trùng lặp giữa các process và profile thực tế.

### 4.3. Không chia sẻ trạng thái application

Ngay cả khi **cùng metadata của một class** được lấy từ archive, mỗi process vẫn có:

- Java heap độc lập;
- các giá trị `static` có thể thay đổi của riêng process;
- class initialization và lifecycle của process;
- các Java thread, stack và cơ chế đồng bộ riêng;
- các object graph, request state, connection pool và cache nghiệp vụ riêng;
- GC metadata và tài nguyên runtime không được thiết kế để chia sẻ theo cách của AppCDS.

**Một `static Map`, `static AtomicInteger` hoặc `static List` không trở thành shared-memory data structure nhờ AppCDS.** Mỗi JVM có biến và dữ liệu riêng về mặt ngữ nghĩa Java; việc lớp có metadata được archive không cho phép process B nhìn thấy các thay đổi trong process A.

Đối với dữ liệu nghiệp vụ cần dùng chung, phải có một cơ chế khác như database, cache ngoài tiến trình, file/IPC được đồng bộ hóa hoặc service. AppCDS không thay thế Redis, hệ thống message queue hay cơ chế liên lạc liên tiến trình.

### 4.4. Không nhầm các tối ưu heap đặc biệt với chia sẻ heap ứng dụng

Một số bản HotSpot/GC còn có tối ưu **archived heap objects** và các thành phần chia sẻ liên quan tới CDS. Chúng có điều kiện hỗ trợ riêng và **không phải cơ chế biến toàn bộ Java heap của ứng dụng thành một heap chung giữa các JVM**.

Bản chất của chủ đề này là **các trang metadata lớp có thể chia sẻ ở chế độ chỉ đọc**. Đừng suy từ tên “shared” rằng có thể truyền object hoặc reference Java từ JVM này sang JVM khác.

## 5. Vì sao OS có thể chia sẻ trang read-only?

Một shared archive là một tệp trên file system. Khi process khởi động, JVM yêu cầu OS ánh xạ các phần của tệp đó vào không gian địa chỉ ảo.

Hình dung:

```text
Tệp archive trên đĩa: app.jsa
            |
            v
   Các trang file-backed trong page cache / physical memory
            |
    +-------+-------+
    |               |
JVM A virtual    JVM B virtual
address space    address space
    |               |
    +-------+-------+
            |
      Cùng backing pages (khi đủ điều kiện)
```

Các process **không cần có cùng địa chỉ ảo** cho trang để OS có thể dùng chung trang vật lý được hỗ trợ bởi cùng nội dung tệp. OS chịu trách nhiệm bảo vệ read-only, quản lý page cache và phân trang.

### 5.1. Vì sao read-only thuận lợi cho chia sẻ?

Khi nhiều process chỉ đọc cùng một trang:

- Không process nào cần sửa nội dung trang đó để phục vụ hoạt động riêng.
- OS có thể tham chiếu một trang vật lý cho nhiều không gian địa chỉ.
- Việc JVM tái sử dụng dữ liệu được chuẩn bị sẵn giảm công việc nạp/chuyển đổi class.

Nếu một vùng phải được sửa riêng, OS/JVM có thể cần bản ghi private hoặc COW, nên không còn chắc chắn tiết kiệm giống phần read-only.

**Lợi ích chia sẻ không đòi ứng dụng sử dụng API `MappedByteBuffer`.** JVM/HotSpot làm việc với archive ở tầng runtime; lập trình viên cấu hình archive bằng các tùy chọn `java`.

### 5.2. “Cùng host” là điều kiện quan trọng

Nếu JVM A chạy trên host 1 và JVM B chạy trên host 2, chúng **không cùng dùng một trang RAM vật lý** chỉ vì tham chiếu cùng một archive trên storage mạng. Mỗi host có bộ nhớ riêng.

Trong môi trường container, hai container có thể nằm trên cùng host và chia sẻ page cache khi các mapping thật sự cùng backing file/đối tượng trong OS. Tuy nhiên, image layers, cách mount, bản JDK, namespace và chính sách kernel có thể làm việc chia sẻ thực tế khác kỳ vọng.

**Không tuyên bố “các pod Kubernetes chia sẻ RAM qua AppCDS” một cách tuyệt đối**: còn phụ thuộc chúng có ở cùng node, archive có tương thích, có chung backing file đủ điều kiện và OS có tái sử dụng được các trang đó hay không.

## 6. Hai lợi ích chính: khởi động và footprint

### 6.1. Khởi động

Với các class đủ điều kiện, một phần công việc phân tích/thiết lập metadata có thể được hoàn thành trong bước xây archive thay vì lặp lại khi mỗi JVM khởi động. Khi JVM khởi động lại với archive hợp lệ, các class đó có thể load nhanh hơn từ shared archive.

Điều này thường hữu ích khi:

- một ứng dụng Java khởi động nhiều lần;
- nhiều process Java có classpath/thư viện chung;
- ứng dụng có số lượng class cần load đáng kể;
- hệ thống có nhiều phiên bản dịch vụ Java đồng thời trên cùng host;
- thời gian startup ảnh hưởng scale-out hay trải nghiệm CLI.

Không có bảo đảm mọi ứng dụng tăng tốc giống nhau. Thời gian startup còn gồm dependency injection, kết nối database, network, class initialization, JIT, cấu hình và logic business; AppCDS không tự loại bỏ những công việc đó.

### 6.2. Bộ nhớ

Nhiều JVM nếu dùng chung các trang read-only trong archive có thể làm giảm **tổng bộ nhớ vật lý bị giữ trùng lặp**. AppCDS có thể tiếp tục tiết kiệm footprint bằng cách không cần tạo mọi biểu diễn dữ liệu lớp private từ JAR.

Tuy nhiên, **heap của hai JVM vẫn riêng**. Nếu một dịch vụ giữ cache Java 500 MB trong heap, AppCDS không tự gộp hai cache của hai process thành một cache 500 MB.

### 6.3. Khi lợi ích có thể rất nhỏ

- Chỉ chạy một process Java; phần lợi ích từ chia sẻ giữa nhiều process không xuất hiện, dù startup vẫn có thể được cải thiện.
- Ứng dụng load rất ít class hoặc hầu hết thời gian khởi động chờ dịch vụ ngoài.
- Các process dùng JDK/classpath khác nhau và không sử dụng được một archive chung.
- Archive có ít class thực sự được load trong các kịch bản quan trọng.
- Vấn đề bộ nhớ chính nằm ở heap dữ liệu nghiệp vụ, chứ không phải class metadata.

**Benchmark trước và sau** là cần thiết. Không ghi một tỷ lệ phần trăm cải thiện cố định cho mọi workload.

## 7. Cách dùng AppCDS trên JDK 17+ theo quy trình đơn giản

Trên JDK hiện đại, **dynamic CDS archive** thường là đường học dễ hiểu vì không cần tạo class-list thủ công.

Quy trình:

1. Biên dịch một ứng dụng nhỏ.
2. Đóng gói thành **JAR**, để class ứng dụng nằm trong nguồn có thể archive.
3. Chạy thử ứng dụng với `-XX:ArchiveClassesAtExit=app.jsa`.
4. JVM ghi dynamic archive khi ứng dụng kết thúc thành công theo quy trình dump.
5. Ở những lần chạy tiếp theo, truyền `-XX:SharedArchiveFile=app.jsa`.
6. Dùng log tải class để xác nhận các class thực sự đến từ shared archive.

Lưu ý: archive không phải Java source code hay một JAR mới. `app.jsa` không được thêm vào `-cp` như một thư viện; JVM đọc nó bằng cờ **`SharedArchiveFile`**.

### 7.1. Ví dụ hoàn chỉnh: `AppCdsDemo.java`

Tạo file **`AppCdsDemo.java`**:

```java
public final class AppCdsDemo {
    // Mỗi tiến trình JVM có giá trị static có thể thay đổi riêng.
    private static int visits;

    static final class Helper {
        static String message() {
            return "application classes loaded";
        }
    }

    public static void main(String[] args) throws Exception {
        visits++;

        System.out.println("visits=" + visits);
        System.out.println("message=" + Helper.message());

        // Dùng khi muốn giữ hai JVM cùng tồn tại để quan sát.
        if (args.length > 0 && args[0].equals("hold")) {
            System.out.println(
                    "pid=" + ProcessHandle.current().pid());
            Thread.sleep(30_000);
        }
    }
}
```

Nếu chạy không có đối số `hold`, stdout chính xác:

```text
visits=1
message=application classes loaded
```

`ProcessHandle.current().pid()` chỉ được in khi có đối số `hold`. PID là số do hệ điều hành gán, **không có giá trị cố định**; `Thread.sleep(30_000)` chỉ giữ process tồn tại thêm 30 giây để người học có thể quan sát hai JVM chạy đồng thời.

**Vì sao có lớp `Helper`?** Ví dụ dùng class ứng dụng và một nested class thật, để khi kiểm tra log CDS có thể xem rõ `AppCdsDemo` và `AppCdsDemo$Helper`. Một chuỗi text trong Helper không phải bằng chứng về chia sẻ Java object; bằng chứng AppCDS đến từ log nguồn class của JVM.

### 7.2. Biên dịch và đóng gói JAR

Tại thư mục demo chỉ chứa source của bài:

```bash
mkdir classes
javac --release 17 -d classes AppCdsDemo.java
jar --create --file app.jar --main-class AppCdsDemo -C classes .
```

Giải thích:

- `javac --release 17` tạo bytecode nhắm tới Java 17; trên JDK 17+ có hỗ trợ option này.
- `-d classes` đặt file `.class` vào thư mục build.
- `jar --create ... -C classes .` đóng gói tất cả class, gồm nested class.
- `--main-class AppCdsDemo` ghi Main-Class vào manifest; ở đây vẫn sẽ gọi class tường minh cho dễ nhìn.
- Archive cho ứng dụng được tạo dựa trên những class load từ **JAR**, không nên đem một thư mục `classes/` làm classpath demo rồi cho rằng mọi AppCDS operation hỗ trợ archive class trong thư mục không rỗng giống JAR.

Nếu dùng Windows PowerShell hoặc Command Prompt, các công cụ `javac` và `jar` cũng có các option tương ứng; bảo đảm chúng cùng một JDK với lệnh `java` được dùng trong ví dụ.

### 7.3. Tạo dynamic archive sau một lần chạy

```bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar AppCdsDemo
```

Stdout từ **ứng dụng**:

```text
visits=1
message=application classes loaded
```

Nếu môi trường đủ điều kiện và bước dump thành công, tệp `app.jsa` được tạo khi JVM thoát. Archive chứa thông tin về các class đủ điều kiện được tải trong lần chạy thử mà chưa có trong base archive.

**Không sử dụng `-Xshare:off` ở bước tạo dynamic archive**: loại archive này cần một base CDS archive được nạp. Trên JDK 17 tiêu chuẩn, default base archive thường đã có và CDS được bật khi có thể sử dụng.

Lệnh trên đã được kiểm chứng trên JDK hiện đại: có tạo `app.jsa` và khi dùng lại thì `AppCdsDemo` và `Helper` được báo cáo là đến từ shared archive.

### 7.4. Chạy lại ứng dụng từ cùng archive

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsDemo
```

Stdout ứng dụng:

```text
visits=1
message=application classes loaded
```

Dù class có thể load từ archive, `visits` vẫn tăng từ trạng thái riêng của **process mới**. Nó không nhớ giá trị biến `static` từ process trước.

### 7.5. Kiểm chứng class thực sự được load từ archive

Chạy:

```bash
java -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar AppCdsDemo
```

Log đầy đủ có thể rất dài vì JVM tải nhiều class. Hãy tìm các dòng liên quan tên `AppCdsDemo`; với JDK được kiểm thử, phần thông tin quan trọng có dạng:

```text
[...][info][class,load] AppCdsDemo source: shared objects file (top)
[...][info][class,load] AppCdsDemo$Helper source: shared objects file (top)
```

Dấu `[...]` chỉ thời gian/timestamp được lược bớt **để minh họa format log**, không phải stdout nguyên văn cố định; phần `shared objects file (top)` là dấu hiệu class đến từ lớp dynamic archive.

Trong một số trường hợp, log có thể ghi `source: shared objects file` mà không có `(top)`, nhất là với archive loại static/base. Không cố so khớp toàn bộ dòng vì timestamp và format log có thể khác giữa phiên bản JDK.

**Kiểm tra đúng là tìm nguồn tải class ứng dụng từ shared objects**, không phải chỉ thấy file archive xuất hiện trên đĩa hoặc thấy JVM start nhanh hơn trong một lần chạy may mắn.

### 7.6. Vì sao cần chạy đúng JAR/classpath như lúc tạo archive?

Archive chứa dữ liệu class gắn với cách class được nạp và tính tương thích của môi trường. Nếu bạn thay JAR, đổi classpath không tương thích, thay JDK build hoặc thay một số option JVM, có thể không dùng lại được archive hoặc các class đó không được chia sẻ.

Khi thay đổi deployment artifact, **xây lại và kiểm chứng archive** là quy trình an toàn. Đừng coi `app.jsa` là một file cache nội dung chung có thể mang nguyên xi qua mọi bản JDK/vendor/architecture.

## 8. Nhiều JVM dùng cùng một archive: minh họa trực quan

Sau khi đã tạo `app.jsa`, mở **hai cửa sổ terminal** trên cùng host, cùng thư mục demo và dùng cùng bản `java`/`app.jar`/`app.jsa`.

**Terminal A:**

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsDemo hold
```

**Terminal B** (khởi chạy khi A còn hoạt động):

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsDemo hold
```

Mỗi process in ít nhất:

```text
visits=1
message=application classes loaded
pid=<PID của tiến trình>
```

Dòng `pid=...` trong khối trên là **mô tả định dạng**, không phải số literal; PID thực tế do OS cấp và khác giữa các lần chạy.

Quan sát:

- Cả hai process có thể sử dụng **cùng archive** cho metadata lớp.
- Cả hai đều in `visits=1`. Biến static được khởi tạo/tăng riêng ở từng JVM; việc share class metadata không chia sẻ biến đếm giữa các process.
- Hai PID khác nhau chứng tỏ đây là hai tiến trình riêng biệt.
- Nếu cần xác nhận hai process thực sự load class từ archive, thêm `-Xlog:class+load=info` vào cả hai lệnh và tìm tên class có `source: shared objects file`.

**Không thể chứng minh số trang vật lý dùng chung chỉ từ stdout `visits=1` hoặc từ hai PID.** Để đo memory sharing thật, dùng công cụ OS như `smaps`/PSS trên Linux hoặc công cụ map memory phù hợp hệ điều hành. Demo này chứng minh sự **tách biệt Java state** và quy trình **hai JVM cùng cấu hình dùng một archive**; log CDS xác minh thực tế tải class.

### 8.1. Tại sao không dùng biến `static` làm kênh liên lạc?

`static` có nghĩa mỗi class có một state tĩnh trong ngữ cảnh class loading của **một JVM**. Nó không có nghĩa “biến toàn cục chung cho mọi JVM trên máy”.

Muốn tăng một bộ đếm chung cho hai tiến trình, phải dùng một backend/IPC được đồng bộ và có hợp đồng concurrency rõ. Ví dụ `AtomicInteger` chỉ an toàn cho đồng bộ các thread truy cập **cùng đối tượng trong một process**, không làm hai process khác nhau có một bộ đếm chung.

### 8.2. Không nên nhầm class metadata với mã bytecode đang chạy

Archive có thể giúp tái sử dụng dữ liệu lớp để load nhanh hơn; nó không làm hai tiến trình thực thi cùng một stack frame, cùng thread hay cùng trạng thái của JIT compilation. Mỗi JVM vẫn có môi trường thực thi riêng, có thể có trình biên dịch JIT, garbage collector và các cấu trúc runtime private.

**Mục tiêu AppCDS là tối ưu class data, không phải xây shared heap hoặc distributed runtime.**

## 9. Lựa chọn khác: tạo static archive từ danh sách class

Dynamic archive thường tiện cho JDK 17+, nhưng **static CDS archive** vẫn được hỗ trợ và hữu ích khi muốn kiểm soát workflow build.

Từ `app.jar` đã tạo ở mục 7, chạy ba bước:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar AppCdsDemo

java -Xshare:dump -XX:SharedArchiveFile=app-static.jsa -XX:SharedClassListFile=app.classlist -cp app.jar

java -XX:SharedArchiveFile=app-static.jsa -cp app.jar AppCdsDemo
```

Ý nghĩa:

1. Chạy thử ứng dụng và ghi tên các class đã load vào `app.classlist`.
2. JVM dùng danh sách đó để tạo `app-static.jsa` ở bước dump riêng.
3. Chạy lại ứng dụng với static archive.

Các lệnh đã được thử thành công bằng một JDK hiện đại; log `-Xlog:class+load=info` sau đó báo các class của ví dụ có `source: shared objects file`.

**Chỉ dùng `-Xshare:off` cho bước thu class-list trong quy trình này**, không dùng nó cho bước **đọc** archive và không dùng với dynamic `ArchiveClassesAtExit`.

### 9.1. Static và dynamic khác nhau thế nào?

| Tiêu chí | Static archive | Dynamic archive |
| --- | --- | --- |
| Cách tạo phổ biến | `DumpLoadedClassList` rồi `-Xshare:dump` | `-XX:ArchiveClassesAtExit` ở lần chạy thử |
| Có cần một bước dump riêng? | Có | Không, dump ở lúc process thoát |
| Có base archive? | Bản static thường là base archive cho chính nó | Dynamic archive được xây trên một base CDS archive |
| Dùng lại như thế nào? | `-XX:SharedArchiveFile=app-static.jsa` | `-XX:SharedArchiveFile=app.jsa` |
| Có thể cùng nhiều JVM dùng? | Có, nếu tương thích | Có, nếu tương thích |
| Điều quan trọng | Class-list và classpath/JAR đúng | Một lượt chạy đại diện và base archive tương thích |

Các tên “static/dynamic” mô tả **cách tạo và mối quan hệ archive**, không có nghĩa archive dynamic cứ tự cập nhật nội dung trong khi nhiều process đang sử dụng nó. Khi chạy với `SharedArchiveFile`, JVM sử dụng dữ liệu archive đã được tạo, không ghi kết quả biến static vào archive.

## 10. Điều kiện để nhiều JVM dùng được cùng archive

### 10.1. Phiên bản JDK và triển khai tương thích

Archive là dữ liệu dành cho một triển khai/phiên bản JVM cụ thể. Khi thay JDK build, cập nhật bảo mật, chuyển vendor hoặc chuyển kiến trúc CPU, không nên giả định file `.jsa` trước đó vẫn dùng được.

Một cách triển khai an toàn:

1. Versioning archive cùng artifact và runtime image.
2. Xây archive bằng runtime dự kiến sử dụng.
3. Chạy bài smoke test kiểm chứng log class loading.
4. Nếu nâng JDK hoặc rebuild JAR, tái tạo archive.
5. Giữ fallback khi archive không còn tương thích.

Không commit một `.jsa` duy nhất rồi hứa dùng được mãi trên mọi Windows, Linux và mọi bản Java.

### 10.2. Classpath, module path và nguồn class

Các class đưa vào archive phải đủ điều kiện của CDS implementation. Với ứng dụng đóng gói classpath, **JAR** là đơn vị phù hợp; các quy tắc CDS về classpath/module-path nghiêm ngặt hơn class loading bình thường.

Trong tài liệu JDK 17, các hạn chế đáng nhớ:

- Classpath và module path dùng cho archiving không được chứa **thư mục không rỗng** trong những ngữ cảnh CDS được mô tả.
- Với archive tương ứng, classpath khi chạy phải phù hợp classpath lúc tạo archive; tài liệu có quy tắc prefix với static archive.
- Nếu JAR đã dùng khi tạo archive bị thay đổi, archive có thể bị từ chối hoặc lớp không thể sử dụng từ archive.
- Một số tùy chọn module như `--patch-module`, `--upgrade-module-path`, `--limit-modules` có thể làm CDS không được sử dụng.

**Đừng tự suy từ một sample JAR chạy đúng rằng mọi custom class loader, exploded module hay cơ chế hot reload đều tự archive được.** Hỗ trợ class loaders đã mở rộng trong AppCDS, nhưng các class đủ điều kiện và ràng buộc mapping phụ thuộc runtime thực tế.

### 10.3. File archive phải được truy cập được

Nhiều process cần đọc được cùng archive; quyền OS, đường dẫn, filesystem mount và file owner phải phù hợp. Nếu archive nằm trên storage không sẵn sàng, bị xóa, hỏng hoặc bị sửa, JVM có thể không dùng được.

Nên phát hành archive như **artifact bất biến**, đặt quyền ghi hạn chế, không để ứng dụng runtime sửa ngẫu nhiên khi các process đang chạy. Nếu cần tạo archive mới, hãy xây và kiểm tra riêng, rồi chuyển deployment đến file mới đúng phiên bản.

### 10.4. Không có bảo đảm chia sẻ giữa hai host

Cùng path `/opt/app/app.jsa` không phải bằng chứng hai process ở cùng host hoặc cùng backing file. Với cluster/container, từng node có thể dùng image layer khác, trang OS và file khác.

Mục tiêu giảm tổng RAM của *một node* nên được đo ở node đó. Mục tiêu giảm RAM toàn cluster phải tổng hợp các phép đo thực tế, không nhân một tỷ lệ tiết kiệm kỳ vọng lên số pod.

## 11. Làm sao chứng minh thực sự đang dùng AppCDS?

### 11.1. Kiểm chứng theo ba mức

| Mức | Dữ liệu quan sát | Kết luận hợp lệ |
| --- | --- | --- |
| A: archive có tồn tại | `app.jsa` có trong file system | Chỉ chứng minh đã có file archive |
| B: JVM đã nạp archive | Log `-Xlog:cds=info` | JVM đã thử/nạp các vùng archive, tùy log cụ thể |
| C: class của ứng dụng load từ archive | `-Xlog:class+load=info` ghi `AppCdsDemo source: shared objects file` | Class tương ứng thật sự dùng class data từ archive |

**Mức C là bằng chứng có giá trị hơn** khi mục tiêu là tối ưu class ứng dụng. Một default archive có thể được nạp cho class JDK, nhưng class ứng dụng bạn quan tâm vẫn được load từ JAR nếu AppCDS archive không có hoặc không tương thích.

### 11.2. Hai tùy chọn log hữu ích

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsDemo

java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsDemo
```

Dòng log và timestamp không phải API ổn định cho mọi JDK; dùng chúng như công cụ chẩn đoán. Với production, không nhất thiết bật `class+load=info` liên tục vì lượng log có thể lớn; bật khi thử nghiệm, rollout, hoặc debug theo chính sách quan sát của hệ thống.

### 11.3. Nếu không có dòng `shared objects file` cho class ứng dụng

Kiểm tra:

1. Archive có được tạo thành công hay không?
2. Ứng dụng được chạy từ JAR phù hợp không?
3. Có dùng đúng `-XX:SharedArchiveFile` không?
4. JDK build và archive có cùng runtime tương thích không?
5. Classpath/runtime image có khác lúc tạo không?
6. JAR đã được rebuild hoặc cập nhật?
7. Có tùy chọn JVM/module cản CDS?
8. Class thực sự được load trong lần profiling/dump và lần chạy kiểm chứng?
9. Có custom class loader/hành vi nạp class không đủ điều kiện?
10. Log `cds` có cảnh báo archive hoặc fallback không?

Đừng kết luận “AppCDS hoạt động” chỉ dựa trên việc `java` không ném exception hoặc startup dường như nhanh hơn 30 ms trong một lần chạy.

## 12. Ý nghĩa của các tùy chọn JVM phổ biến

| Tùy chọn | Vai trò | Lưu ý |
| --- | --- | --- |
| `-Xshare:off` | Vô hiệu hóa CDS archive | Dùng so sánh/diagnostic, không phải cách tận dụng sharing |
| `-Xshare:auto` | Dùng archive khi có thể | Cách linh hoạt, phù hợp fallback trong nhiều trường hợp |
| `-Xshare:on` | Yêu cầu CDS hoạt động; lỗi nếu không thể | Theo Oracle, chủ yếu **dùng thử nghiệm**, không khuyến nghị production |
| `-XX:ArchiveClassesAtExit=app.jsa` | Tạo dynamic archive khi ứng dụng thoát | Cần base archive; chỉ class đủ điều kiện mới được lưu |
| `-XX:SharedArchiveFile=app.jsa` | Chỉ định archive sẽ sử dụng khi chạy | Có thể là static hoặc dynamic archive |
| `-XX:DumpLoadedClassList=app.classlist` | Thu class-list khi chạy ứng dụng | Bước profiling cho static archive |
| `-XX:SharedClassListFile=app.classlist` | Chỉ định class-list để dump | Dùng với `-Xshare:dump` |
| `-Xshare:dump` | Tạo static archive trong bước riêng | Không phải lệnh chạy business app bình thường |
| `-Xlog:cds=info` | Log về CDS mapping/initialization | Hữu ích khi debug |
| `-Xlog:class+load=info` | Log nguồn tải class | Tìm `shared objects file` cho class ứng dụng |

**Không đưa `-Xshare:on` làm mặc định production** chỉ để ép chạy “luôn phải có AppCDS”. Trên một máy khác JDK hoặc một lần rollout archive sai, JVM có thể không khởi động. Khi không có yêu cầu hard-fail đặc biệt, cơ chế fallback và giám sát sẽ an toàn hơn.

### 12.1. Dynamic archive có base archive

Một dynamic archive bổ sung các class so với base archive (thường là default CDS archive của JDK). Khi tạo bằng `ArchiveClassesAtExit`, JVM cần base archive được load.

Trường hợp source/JDK không có base archive hoặc cờ cấu hình đã vô hiệu hóa CDS, thao tác tạo dynamic archive có thể thất bại. Hãy đọc thông báo JVM và dùng workflow phù hợp runtime, không cố sửa bằng `-Xshare:off`.

Khi dùng một dynamic archive làm `SharedArchiveFile`, JVM có thể tìm base archive dựa trên metadata của dynamic archive; vẫn cần bản base tương thích. Nếu tự chỉ định cả static và dynamic archive, các hướng dẫn có thể có **ký tự phân cách khác nhau giữa nền tảng** (ví dụ `:` trên Linux/macOS và `;` trên Windows). Ví dụ căn bản ở trên chỉ cần một `app.jsa`, tránh phức tạp này.

## 13. Đo RAM chia sẻ như thế nào cho đúng?

### 13.1. RSS không tự cho biết tổng RAM vật lý riêng

**RSS (Resident Set Size)** là số trang đang resident được tính cho một process; nó thường bao gồm cả các trang shared mà process đó map.

Giả sử hai JVM cùng map một nhóm trang shared 20 MiB:

```text
JVM A RSS: có thể tính 20 MiB các trang shared
JVM B RSS: có thể tính 20 MiB các trang shared
Tổng RSS hai process: có thể tính cùng các trang shared hai lần
RAM vật lý thực cho chính nhóm trang ấy: không nhất thiết là 40 MiB
```

Các số trên là **minh họa nguyên lý đếm**, không phải kết quả đo thực tế của AppCDS.

Nếu chỉ cộng RSS của nhiều JVM, bạn có thể đánh giá quá cao tổng footprint vật lý vì những trang file-backed shared bị tính lặp.

### 13.2. PSS và phân tách shared/private

Trên Linux, `/proc/<pid>/smaps` và `/proc/<pid>/smaps_rollup` có thể cung cấp các giá trị như:

- **PSS (Proportional Set Size):** phần kích thước trang chia sẻ được chia tỷ lệ cho các process đang dùng, thường hữu ích khi so tổng footprint.
- **Shared_Clean:** các trang shared sạch, điển hình gồm file-backed read-only pages.
- **Private_Clean/Private_Dirty:** những trang gắn với process riêng, tùy cách hệ điều hành phân loại.
- **RSS:** tổng kích thước resident theo cách báo cáo của process.

Có thể dùng:

```bash
cat /proc/<pid>/smaps_rollup
```

Lệnh là ví dụ Linux; `<pid>` là PID thực tế. Không thể chạy literal dấu `<...>` như thể đó là một đường dẫn tồn tại. Bạn cũng có thể dùng `pmap`, `smem` hoặc profiler/OS tools khác tùy hệ thống.

**Để so nhiều JVM**, đo các process đồng thời khi cùng tải một workload, so baseline với CDS off và trường hợp AppCDS on, và xét tổng PSS/private footprint của nhóm process thay vì chỉ nhìn một con số RSS.

### 13.3. Không phải công cụ nào cũng báo giống nhau

Windows, Linux và macOS có cách báo working set, committed memory, mapped files và resident pages khác nhau. Một công cụ Windows có thể báo address space mapped tăng dù RAM vật lý thực dùng bởi nhiều JVM giảm. Vì thế cần định nghĩa **chỉ số chính** trước khi kết luận.

Các biến số cần giữ tương đương trong benchmark:

- cùng bản JDK, OS, GC, heap flags;
- cùng JAR và classpath;
- cùng workload và thời điểm đo;
- cùng số process chạy đồng thời;
- cùng điều kiện cache file system ở mức có thể kiểm soát;
- cùng cách chờ ứng dụng ổn định;
- cùng khái niệm footprint (PSS, private dirty, working set, v.v.).

Không tuyên bố “AppCDS giảm 50% RAM” nếu số đo chỉ là tổng RSS, hoặc chạy hai kịch bản với số process khác nhau.

## 14. Một benchmark có ý nghĩa

Nếu muốn đánh giá tính năng trong dự án:

1. Chọn ứng dụng có nhiều class và nhiều process triển khai tương tự.
2. Tạo archive bằng JDK/JAR dự kiến dùng.
3. Xác nhận class ứng dụng được load từ archive bằng `-Xlog:class+load=info`.
4. Định nghĩa baseline bằng cách chạy không dùng archive, có thể dùng `-Xshare:off` cho kiểm thử chẩn đoán.
5. Chạy N process cùng workload bằng archive tương thích, giữ các process tồn tại khi đo.
6. Đo **thời gian startup** và **footprint** bằng công cụ phù hợp OS.
7. So sánh median hoặc phân phối nhiều lượt chạy; không lấy duy nhất một lần chạy nóng/lạnh.
8. Ghi rõ JDK vendor/build, flags, file system, classpath và số process.
9. Nếu kết quả không đạt kỳ vọng, kiểm tra phần class được archived và bottleneck thực tế trước khi thay cơ chế.
10. Trong môi trường thật, theo dõi startup errors và khả năng fallback khi cập nhật runtime.

**Không dùng `Thread.sleep` trong demo như cách benchmark startup.** Nó chỉ giữ process đủ lâu để người học mở công cụ OS. Tính thời gian startup phải đặt tại ranh giới đo có ý nghĩa, không cộng trừ 30 giây ngủ tùy ý.

## 15. Tính read-only có ý nghĩa gì về an toàn và bảo mật?

Archive được JVM đọc như một artifact chứa dữ liệu lớp đã được chuẩn bị. Việc map các trang **chỉ đọc** giúp ngăn process sửa các trang được chia sẻ đó theo cơ chế memory protection của OS. Nhưng read-only mapping **không có nghĩa tệp archive trên đĩa tự động không thể bị người khác sửa**.

Những nguyên tắc vận hành:

- Bảo đảm `.jsa` được tạo từ **JDK, JAR và nguồn build đáng tin cậy**.
- Đặt quyền file/ownership để process chạy ứng dụng có thể **đọc** nhưng không tự ý **ghi đè** artifact dùng chung.
- Khi rollout phiên bản mới, tạo archive mới và cập nhật đường dẫn theo release, tránh sửa file archive cũ đang được sử dụng.
- Không cho người dùng không tin cậy thay đổi `-XX:SharedArchiveFile` hoặc nội dung tệp archive mà production JVM sẽ tải.
- Kiểm soát nguồn image/container và chuỗi phát hành artifact như với các tệp runtime khác.
- Không nhầm “read-only metadata” với cơ chế cô lập bảo mật giữa các process, cũng không biến archive thành cách truyền secret giữa process.

Một số JVM cung cấp `-XX:+VerifySharedSpaces` cho kiểm tra checksum/CRC nhằm phát hiện **hỏng dữ liệu vô ý** khi đọc archive. Checksum này **không phải chữ ký mật mã** và không được trình bày như phương án bảo vệ trước tác nhân cố ý giả mạo archive. Bảo mật artifact cần quyền file và quy trình build/deploy đáng tin cậy.

### 15.1. Archive bất biến giúp rollout dễ kiểm soát

Một cách đặt tên:

```text
releases/
  version-A/
    app.jar
    app.jsa
  version-B/
    app.jar
    app.jsa
```

Mỗi cặp `app.jar`/`app.jsa` được phát hành và kiểm thử cùng một runtime image thích hợp. Nếu rollback, chuyển lại cả JAR/runtime/archive tương ứng. Không chỉ thay JAR mà cố dùng lại archive tạo cho JAR trước.

Đây là **một mẫu tổ chức deployment**, không phải định dạng thư mục bắt buộc của Java.

## 16. Ứng dụng container và nhiều bản sao JVM

Trong hệ thống dùng container hoặc container orchestration:

- Tích hợp bước tạo archive vào pipeline build/deploy khi cần.
- Gắn archive với image/version runtime và JAR tương ứng.
- Xác minh archive có thể được đọc bởi user chạy container.
- Không tạo lại archive một cách cạnh tranh khi nhiều replica cùng đọc một path và một process khác đang ghi vào chính file ấy.
- Chú ý nhiều JVM có thể nằm trên các node khác nhau: không giả định có chia sẻ RAM vật lý xuyên node.
- Kiểm tra môi trường runtime thực sự của từng container, không suy từ tên image hoặc hostname.
- Đo memory footprint theo process/node dưới cách tính memory accounting của hệ điều hành và container runtime.
- Nếu ứng dụng hoặc JDK thay đổi, archive phải được tạo/kiểm chứng lại.

**Lợi ích không chỉ có khi nhiều process:** một tiến trình đơn vẫn có thể tải class nhanh từ archive. Nhưng chủ đề **chia sẻ read-only giữa nhiều JVM** chỉ tạo lợi ích cộng hưởng nếu các process **có thể dùng chung backing pages trên cùng host**.

### 16.1. “Cùng file path” chưa phải bằng chứng chia sẻ cùng page

Hai container có thể đều thấy `/app/app.jsa` nhưng file đó nằm trong hai filesystem layers khác nhau. Đường dẫn giống nhau **không chứng minh** chúng cùng backing file OS. Tương tự, hai JAR có cùng tên nhưng khác bytes hoặc JDK không tương thích có thể khiến archive bị từ chối.

Để đo mức chia sẻ thật, quan sát mapping, backing file identity và số liệu memory của host thay vì chỉ nhìn tên tệp.

## 17. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| Không có `app.jsa` sau profiling | Dump lỗi, thiếu base archive, path không ghi được, process không thoát bình thường | Đọc stderr/exit code, kiểm tra điều kiện tạo archive |
| JVM báo archive không khớp JDK | File tạo với runtime/build khác | Tạo lại archive bằng JDK của deployment |
| JVM báo JAR bị thay đổi | JAR không còn khớp với bản archived | Build lại archive gắn với JAR mới |
| `AppCdsDemo` không có `source: shared objects file` | Class không archived/không đủ điều kiện, classpath thay đổi | Đọc log cds/class+load và kiểm tra workflow |
| Sử dụng `-Xshare:off` khi muốn đọc archive | CDS bị tắt theo chính cờ | Bỏ cờ hoặc bật `-Xshare:auto` khi phù hợp |
| Dùng `-Xshare:on` làm production lỗi khởi động | Cờ yêu cầu archive nhất thiết dùng được | Dùng cơ chế fallback và monitoring hợp lý |
| Chạy app từ class directory mà archive không thu class | Hạn chế classpath/CDS trên JDK đang dùng | Đóng gói JAR, dùng classpath tương thích |
| Startup không nhanh đáng kể | Bottleneck không thuộc class loading hoặc profile archiving thiếu class | Benchmark/trace class load và workflow |
| Tổng RSS không giảm như mong đợi | RSS có thể đếm lặp shared pages hoặc heap chiếm phần lớn | Đo PSS/private memory, định nghĩa metric |
| Hai JVM vẫn có `static` khác nhau | Đây là thiết kế đúng: state process riêng | Dùng cache/IPC/backend nếu cần dữ liệu chung |
| Archive báo lỗi permission | Process không được đọc tệp hoặc thư mục | Sửa quyền và deployment ownership |
| Archive được chia trên network filesystem | Không đồng nghĩa chia RAM giữa máy khác nhau | Quan sát ở đúng host/node |
| Process đang chạy nhưng archive bị sửa | Quy trình artifact không bất biến | Rollout archive mới theo phiên bản riêng |
| Log class load quá lớn | Bật diagnostic chi tiết liên tục | Chỉ bật khi cần và thu log có chọn lọc |

### 17.1. Những thứ không nên làm để “chữa lỗi” AppCDS

- Không sửa nội dung nhị phân `.jsa` bằng editor.
- Không chép ngẫu nhiên archive từ JDK khác rồi bật `-Xshare:on` cho production.
- Không dùng `static synchronized` rồi tưởng hai JVM đồng bộ với nhau.
- Không nhầm `java -Xshare:dump` với thao tác chạy ứng dụng hoặc khởi tạo database.
- Không đặt `app.jsa` vào classpath như một JAR.
- Không coi class có mặt trong archive là class chắc chắn được sử dụng ở mọi request.
- Không “tối ưu” bằng cách biến mọi object thành `static`; đó là bài toán khác và có thể gây tăng heap.
- Không dùng memory-map read-only làm cơ chế phân quyền dữ liệu nghiệp vụ giữa các tenant.
- Không thay đổi JDK/JAR khi vẫn kỳ vọng archive cũ hoàn toàn tương thích.

## 18. So sánh AppCDS với các cơ chế chia sẻ khác

| Cơ chế | Dữ liệu chia sẻ | Ranh giới tiến trình | Dùng cho |
| --- | --- | --- | --- |
| **AppCDS** | Một số class metadata/archived class data read-only | Có thể map cùng backing pages giữa JVM | Startup, giảm footprint từ class metadata |
| **`static` field** | State của class trong một JVM | Không vượt process | Cache/biến chung giữa các instance trong **một JVM** khi thiết kế cho phép |
| **`SharedMemory`/mmap do ứng dụng dùng** | Dữ liệu định dạng do ứng dụng quản lý | Có thể vượt process trên cùng host | IPC, shared buffers nếu có đồng bộ/format an toàn |
| **Database/Redis** | Dữ liệu nghiệp vụ hoặc cache từ xa | Vượt process và thường vượt host | State chung, phối hợp service |
| **Message queue** | Thông điệp/sự kiện | Vượt process/host | Giao tiếp không đồng bộ |
| **Java heap / GC** | Object graph của process | Private theo JVM | Bộ nhớ runtime ứng dụng |

Không có API Java chuẩn tên `SharedMemory` trong bảng với ý nghĩa một lớp bắt buộc được dùng; đó là **nhãn khái niệm** cho các giải pháp shared-memory, không phải câu lệnh `new SharedMemory()` cần biên dịch. Nếu dùng `FileChannel.map`/`MappedByteBuffer`, ứng dụng phải tự xác định file format, consistency, lock, synchronization và lifetime; việc đó **khác hoàn toàn** map archive nội bộ của HotSpot.

## 19. Bài tập tự kiểm tra có đáp án

### Bài 1 — Điều gì được dùng chung?

Hai JVM chạy cùng `app.jar`, dùng một archive AppCDS tương thích. Chúng có thể chia sẻ gì?

**Đáp án:** có thể chia sẻ các **trang metadata read-only** thuộc archive được OS ánh xạ. Hai Java heap và state runtime thay đổi vẫn tách biệt. Không có bảo đảm mọi byte trong archive đều dùng chung vật lý.

### Bài 2 — Biến `static`

`AppCdsDemo` ở hai process đều in `visits=1`. Tại sao không in `1` rồi `2`?

**Đáp án:** mỗi JVM có một instance state tĩnh của class theo ngữ nghĩa riêng, dù class metadata có thể được đọc từ archive chung. `static` không vượt qua ranh giới process.

### Bài 3 — Có archive nhưng không có tác dụng?

Bạn thấy `app.jsa` tồn tại. Điều đó đủ chứng minh `AppCdsDemo` được load từ archive chưa?

**Đáp án:** chưa. Cần log `-Xlog:class+load=info` cho `AppCdsDemo`, tìm `source: shared objects file` hoặc thông tin tương đương, và xem lỗi/fallback của CDS.

### Bài 4 — JAR thay đổi

Archive được tạo từ `app.jar` phiên bản A. Bạn thay bằng JAR bản B mà không tạo lại archive. Có thể tin sharing vẫn hoạt động?

**Đáp án:** không. Classpath/JAR là yếu tố tương thích; JVM có thể từ chối archive hoặc bỏ qua các lớp không khớp. Nên xây lại archive cùng bản JDK và JAR mới.

### Bài 5 — Cách tạo dynamic archive

JDK 17+, bạn có `app.jar` và ứng dụng load đủ class trong một lượt chạy. Lệnh tạo archive là gì?

**Đáp án:**

```bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar AppCdsDemo
```

Archive được tạo khi JVM kết thúc trong điều kiện dump phù hợp. Cần base archive hợp lệ; không thêm `-Xshare:off`.

### Bài 6 — Cách dùng lại

**Đáp án:**

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsDemo
```

Tương thích runtime/JAR quyết định archive có thể dùng được hay không.

### Bài 7 — JVM khác host

Hai process trên hai máy khác nhau cùng đọc file `app.jsa` trên storage mạng. Chúng có thể chia sẻ **cùng một trang RAM vật lý** không?

**Đáp án:** không, vì RAM vật lý của hai host khác nhau. Mỗi host có thể áp cơ chế chia sẻ trong nội bộ host đối với các process cùng host.

### Bài 8 — Chỉ nhìn tổng RSS

Bạn cộng RSS của 10 JVM, nhận 5 GB. Có chắc chúng đang chiếm đúng 5 GB RAM vật lý riêng?

**Đáp án:** không. RSS có thể đếm nhiều lần cùng trang shared read-only. Dùng PSS/private memory hoặc OS-specific metrics thích hợp để phân tích.

### Bài 9 — `-Xshare:on`

Nếu archive không tương thích, `-Xshare:on` sẽ có hành vi gì?

**Đáp án:** JVM có thể báo lỗi và thoát vì cờ yêu cầu CDS thành công. Oracle lưu ý cờ này dành cho thử nghiệm/diagnostic, không nên coi là cấu hình mặc định production.

### Bài 10 — `-Xshare:off`

Dùng `-Xshare:off` khi chạy `AppCdsDemo` có giúp tận dụng archive?

**Đáp án:** không, cờ tắt CDS. Nó có thể dùng để tạo baseline so sánh hoặc thu class-list cho static workflow, nhưng không được dùng để chứng minh class đang chia sẻ.

### Bài 11 — Có thể chia sẻ cache Java không?

Hai worker JVM muốn dùng cùng một `static Map<String, Object>`. AppCDS có thay backend cache chung được không?

**Đáp án:** không. `static Map` nằm trong bộ nhớ quản lý riêng của mỗi JVM. Muốn state chung phải có IPC/database/cache service hoặc giải pháp shared-memory do ứng dụng thiết kế.

### Bài 12 — Container

Hai container thấy đường dẫn `/app/app.jsa`. Đã chắc chia sẻ RAM vật lý cho archive chưa?

**Đáp án:** chưa. Cần kiểm tra cùng host/node, backing file, JDK compatibility, thực tế mapping và các chỉ số memory của OS. Path giống nhau là chưa đủ.

### Bài 13 — Static archive

Tại sao static workflow có `DumpLoadedClassList` và `-Xshare:dump`?

**Đáp án:** bước đầu thu tập class dùng bởi ứng dụng; bước tiếp theo tạo archive với class list đó. Dynamic `ArchiveClassesAtExit` gộp việc ghi archive vào lúc kết thúc một lượt chạy, đơn giản hơn cho nhiều ứng dụng.

### Bài 14 — Archive và phiên bản Java

`AppCDS` là tính năng ra mắt trong Java 10. Trên JDK 17 có cần quay về Java 10 hay dùng những cờ triển khai thương mại cũ để tạo archive không?

**Đáp án:** không. Sử dụng các tùy chọn CDS/AppCDS của JDK hiện tại như ví dụ. Java 10 là mốc JEP 310, không phải giới hạn duy nhất của tính năng.

### Bài 15 — Ưu tiên tối ưu

Ứng dụng giữ 8 GB dữ liệu nghiệp vụ trong heap; AppCDS đã giảm nhiều metadata class, nhưng footprint tổng vẫn lớn. Có mâu thuẫn không?

**Đáp án:** không. AppCDS tối ưu dữ liệu lớp và startup, không tự tối ưu toàn bộ object graph. Cần đo và tối ưu heap/cache/đối tượng theo bottleneck thực tế.

### Bài 16 — Read-only và bảo mật

Archive map read-only đã đủ ngăn người khác sửa file `.jsa` trên đĩa chưa?

**Đáp án:** chưa. Memory mapping read-only chỉ là thuộc tính truy cập của trang trong process; cần quyền file, build provenance và deployment policy riêng để bảo vệ archive trên storage.

### Bài 17 — Lợi ích khi chỉ có một process

Chỉ một JVM dùng archive. AppCDS có vô ích hoàn toàn không?

**Đáp án:** không. Nó vẫn có thể giảm thời gian startup nhờ dữ liệu lớp được chuẩn bị sẵn. Phần tiết kiệm thêm do **nhiều JVM chia sẻ cùng backing pages** mới không xuất hiện ở trường hợp chỉ một process.

### Bài 18 — Dòng log quan trọng

`AppCdsDemo source: shared objects file (top)` cho biết điều gì?

**Đáp án:** khi JVM load class AppCdsDemo, nó lấy class data từ shared archive lớp trên (dynamic/top) trong runtime đã kiểm thử; đây là bằng chứng mạnh hơn việc archive file chỉ tồn tại.

## 20. Checklist trước khi triển khai AppCDS

1. Đã hiểu mục tiêu của AppCDS là **class metadata/startup**, không phải Java heap chung?
2. Có nhiều JVM chạy trên cùng host dùng nhiều class chung không?
3. Những JVM có dùng **archive tương thích** từ một bản JDK/JAR đủ gần nhau không?
4. Có tạo ứng dụng dưới dạng **JAR** phù hợp workflow archive không?
5. Có đủ class được tải trong lần training/dump không?
6. Có dùng `ArchiveClassesAtExit` trên JDK hiện đại khi thích hợp không?
7. Có base archive hợp lệ khi tạo dynamic archive không?
8. Có tránh `-Xshare:off` trong lượt chạy cần sử dụng CDS không?
9. Có dùng `SharedArchiveFile` và kiểm tra lỗi startup không?
10. Có xác nhận class ứng dụng thực sự có `source: shared objects file` không?
11. Có hiểu `-Xshare:on` không nên áp mặc định production không?
12. Có rebuild archive khi cập nhật JDK/JAR/classpath không?
13. Có kiểm soát JDK vendor/build và kiến trúc runtime không?
14. Có phân biệt static vs dynamic archive và quan hệ base/top không?
15. Có bảo đảm `.jsa` được đọc từ nguồn đáng tin, quyền ghi hạn chế không?
16. Có tránh sửa file archive đang được sử dụng bởi nhiều process không?
17. Có hiểu `static` và heap vẫn riêng giữa các JVM không?
18. Nếu cần dữ liệu chung, đã chọn database/IPC/cache ngoài tiến trình chưa?
19. Có đo startup nhiều lần với cùng workload thay vì một lần không?
20. Có đo footprint theo PSS/private/shared thay vì chỉ tổng RSS không?
21. Có phân biệt chia sẻ **cùng host** và nhiều node/container không?
22. Có tránh suy “tệp archive 20 MB => tiết kiệm 20 MB mỗi process” không?
23. Có dùng log CDS đúng lúc và không gây quá tải log production không?
24. Có chuẩn bị fallback và monitoring nếu archive không tương thích không?
25. Có kiểm thử cơ chế rollout/rollback của JAR, JDK và archive như một bộ không?
26. Có ghi rõ các giới hạn provider/classloader/module path cho ứng dụng thực không?
27. Có test vừa đường đi bình thường vừa trường hợp không nạp được archive không?
28. Có tránh đưa số liệu cải thiện cố định mà chưa benchmark trên target host không?

## 21. Tổng kết

**AppCDS mở rộng CDS đến dữ liệu lớp ứng dụng và có thể giúp nhiều tiến trình JVM trên cùng host chia sẻ các trang metadata chỉ đọc đã được ánh xạ từ shared archive.** Hệ điều hành quản lý sự chia sẻ page-backed này; mỗi JVM vẫn giữ heap, static state, threads và các tài nguyên runtime của riêng mình.

Java 10 giới thiệu AppCDS qua JEP 310. Trên JDK hiện đại, dynamic archive có thể được tạo bằng `-XX:ArchiveClassesAtExit` và dùng lại bằng `-XX:SharedArchiveFile`; static archive vẫn được hỗ trợ bằng class-list và `-Xshare:dump`. Muốn xác minh lớp ứng dụng thật sự dùng archive, xem log `-Xlog:class+load=info` với `source: shared objects file`.

Lợi ích gồm **khởi động nhanh hơn và giảm mức trùng lặp metadata giữa các JVM tương thích**. Mức tiết kiệm thực tế phụ thuộc cùng host, backing pages, JDK/JAR, workload và cách đo. AppCDS **không** biến Java heap thành bộ nhớ chia sẻ chung hoặc thay thế cơ chế trao đổi dữ liệu liên tiến trình. Hãy tạo archive từ artifact đáng tin, triển khai bất biến theo phiên bản, xác minh bằng log, đo đúng RAM shared/private và luôn có phương án vận hành khi archive không dùng được.

### Tài liệu tham khảo chính thức

- [JEP 310: Application Class-Data Sharing](https://openjdk.org/jeps/310)
- [JEP 350: Dynamic CDS Archives](https://openjdk.org/jeps/350)
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html)
- [Oracle Java SE 17 — The java Command / Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html)
- [Oracle Java SE 25 — java Command / CDS and AOT](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)