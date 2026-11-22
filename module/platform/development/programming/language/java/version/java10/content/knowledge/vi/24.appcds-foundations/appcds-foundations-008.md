# Java 10 — Ảnh hưởng của JDK, kiến trúc và đầu vào ứng dụng đến kho chia sẻ AppCDS

## 1. Mục tiêu và phạm vi

**Application Class-Data Sharing (AppCDS)** cho phép JVM lưu một phần thông tin về những lớp Java đã được nạp vào **kho lưu trữ chia sẻ** (*shared archive*), để những lần khởi động ứng dụng tiếp theo có thể tái sử dụng dữ liệu lớp đã chuẩn bị sẵn. Tính năng này được mở rộng cho lớp ứng dụng ở **Java 10** thông qua **JEP 310 — Application Class-Data Sharing**. Cơ chế nền **Class Data Sharing (CDS)** đã có trước đó và vẫn được sử dụng trên các JDK hiện đại.

Một archive AppCDS **không phải JAR, không phải ảnh chụp bộ nhớ đầy đủ, cũng không phải artifact có thể sao chép tùy ý giữa mọi JVM**. Tính hợp lệ của nó phụ thuộc chủ yếu vào:

1. **JDK tạo và dùng archive**: phiên bản, build, bản phân phối/runtime image, những tùy chọn JVM ảnh hưởng cấu trúc dữ liệu;
2. **Hệ điều hành và kiến trúc CPU**: dạng nhị phân, kiến trúc, bố trí dữ liệu bộ nhớ, cấu hình máy ảo;
3. **Đầu vào của ứng dụng**: JAR/classpath/module path, danh sách lớp thực sự nạp, cách chạy ứng dụng và các tùy chọn can thiệp vào class loading/linking.

Ví dụ một archive được tạo với một build JDK trên Windows x64 và một bản `app.jar` cụ thể **không được xem như một file cache chung hợp lệ** để mang nguyên sang Linux ARM64 hoặc một JDK đã cập nhật. Tương tự, sửa JAR dù vẫn giữ tên và đường dẫn có thể làm archive không còn dùng được.

Bài học trả lời những câu hỏi thực tế:

- Tại sao **cùng bytecode Java** nhưng cache không thể dùng giữa hai bản JDK?
- JAR được cập nhật tại **cùng đường dẫn** có ảnh hưởng gì?
- Có phải chỉ cần `java -version` giống FEATURE là đủ?
- `-cp` và `--module-path` khác nhau về điều kiện tương thích ra sao?
- Tham số ứng dụng khác trong lần **training** có làm archive vô hiệu không, hay chỉ thay số lớp được ghi nhận?
- Làm sao nhận ra lớp đang được nạp từ archive thay vì từ JAR?
- Khi archive không hợp lệ, nên xử lý thế nào trong production?
- JDK 24+ có **AOT cache**; quan hệ giữa nó và AppCDS truyền thống là gì?

**Giới hạn thời đại:** chỉ hướng dẫn những cơ chế **vẫn áp dụng trên Java hiện đại**. Phân biệt rõ JDK 10 (mốc ra đời AppCDS), JDK 13+ (dynamic CDS archive), JDK 24+ (AOT cache) và JDK 25/27 (cải tiến giao diện vận hành). Không dùng cờ lịch sử `-XX:+UseAppCDS` làm quy trình chính cho JDK mới; luôn kiểm tra tài liệu **đúng bản JDK đang triển khai**.

## 2. CDS, AppCDS và AOT cache không hoàn toàn là một khái niệm

### 2.1. CDS cơ bản

Class Data Sharing cho phép JVM lưu một tập thông tin lớp đã được phân tích/chuẩn bị dưới định dạng JVM có thể ánh xạ nhanh hơn khi khởi động. Các trang bộ nhớ chỉ đọc có thể được dùng chung giữa nhiều tiến trình JVM trên cùng một máy, giúp:

- Giảm một phần thời gian nạp lớp và chuẩn bị metadata;
- Giảm footprint vật lý khi nhiều JVM cùng sử dụng những trang có thể chia sẻ;
- Có lợi đặc biệt với ứng dụng nhỏ hoặc dịch vụ khởi động nhiều lần.

**Không có cam kết** rằng mọi workload đều nhanh hơn hoặc mọi bộ nhớ sẽ giảm. Archive có chi phí dung lượng đĩa; độ lợi phụ thuộc số lớp, quy trình startup và cấu hình thực tế.

### 2.2. AppCDS từ Java 10

**JEP 310** mở rộng đối tượng được archive sang **các lớp của ứng dụng**, bên cạnh lớp nền tảng. Nhờ đó một ứng dụng có thể lưu metadata lớp ở các JAR dependency và lớp của chính nó, khi những lớp ấy được JVM hỗ trợ archiving và được nhận diện trong lúc tạo archive.

Tên `AppCDS` không nói rằng chương trình `main()`, mọi bean, kết nối cơ sở dữ liệu, static data, kết quả truy vấn và heap của ứng dụng đều được snapshot. Cơ chế chia sẻ **class data** có giới hạn rất cụ thể.

### 2.3. Những mốc vẫn quan trọng hiện nay

| Mốc JDK | Khả năng liên quan | Cách hiểu |
|---|---|---|
| Trước Java 10 | CDS cho những lớp nền tảng đã được hỗ trợ | AppCDS ứng dụng chưa theo phạm vi JEP 310 |
| **Java 10 — JEP 310** | **Application Class-Data Sharing** | Bắt đầu mở rộng chia sẻ cho lớp ứng dụng |
| **JDK 12 — JEP 341** | Default CDS archives | Nhiều bản phân phối JDK đi kèm archive mặc định, dùng tự động |
| **JDK 13 — JEP 350** | Dynamic CDS archives | Có thể tạo archive động dựa trên các lớp được nạp trong lần chạy thử |
| JDK 19+ | Cải tiến tự tạo/tái tạo dynamic archive ở các JDK hỗ trợ | `-XX:+AutoCreateSharedArchive` là lựa chọn được tài liệu JDK hiện đại mô tả |
| **JDK 24 — JEP 483** | Ahead-of-Time Class Loading & Linking | AOT cache mở rộng việc chuẩn bị class loading/linking |
| **JDK 25 — JEP 514/515** | Cú pháp tạo cache tiện hơn; AOT method profiling | Tối ưu quy trình tạo cache và thêm dữ liệu hỗ trợ warm-up |
| JDK 26 — JEP 516 | AOT object caching tương thích thêm với những GC khác | Không thể áp một quy tắc GC cũ cho mọi AOT cache về sau |
| JDK 27 | `-XX:AOTMode=required` là alias rõ nghĩa cho `on` | Hữu ích khi muốn fail-fast xác nhận AOT cache khả dụng |

Những mốc trên cho thấy **AppCDS không lỗi thời**, nhưng ở những dự án JDK 24–27, **AOT cache** là lựa chọn hiện đại cần cân nhắc cùng hoặc thay cho quy trình AppCDS thủ công. Cụ thể nên dùng gì phụ thuộc bản JDK, framework, workload và khả năng tương thích.

## 3. Tại sao kho chia sẻ gắn với JDK?

Archive chứa những dữ liệu đã được chuẩn bị ở định dạng mà một HotSpot JVM cụ thể hiểu. Đây **không phải định dạng trao đổi chuẩn độc lập phiên bản** như `.class` hoặc `.jar`.

Các yếu tố của JDK có thể ảnh hưởng:
- Bố cục metadata nội bộ của JVM;
- Tập lớp trong runtime image và module graph;
- Cách biểu diễn con trỏ, object headers, alignment và các tối ưu nội bộ;
- Cách JVM dựng/loading/linking lớp trong archive;
- Build cụ thể, các bản cập nhật runtime, vendor và cách đóng gói image.

Theo tài liệu lệnh `java` của Oracle, nội dung **CDS archive phụ thuộc từng JDK build**. Do đó, chỉ kiểm tra `Runtime.version().feature() == 21` là **không đủ** để khẳng định một archive được tạo với JDK 21.x build A dùng được trên 21.x build B.

### 3.1. Phân biệt bytecode compatibility với archive compatibility

Đây là hai câu hỏi khác nhau:

**Câu hỏi A — bytecode chạy được không?**

Một file `.class` biên dịch với `javac --release 17` thường có thể chạy trên JDK tương thích từ Java 17 trở lên nếu API/dependency đúng. `.class` có định dạng được đặc tả và các quy tắc tương thích của Java.

**Câu hỏi B — có tái sử dụng được archive hay không?**

Một `app.jsa` được tạo với một JVM cụ thể lưu **trạng thái tối ưu hóa nội bộ**, nên có điều kiện ràng buộc chặt hơn nhiều. Có thể **chương trình vẫn chạy bình thường** sau đổi JDK nhưng archive không còn được dùng.

Ví dụ:

```text
app.jar  --compile target Java 17-->  chạy trên JDK 24, 25, 27 tùy tính tương thích
app.jsa  --tạo bởi JDK build X------>  KHÔNG mặc định dùng được với JDK build Y
```

Việc đặt `app.jar` và `app.jsa` cùng thư mục **không** làm hai artifact có cùng quy tắc tương thích.

### 3.2. Patch JDK cũng là thay đổi cần xét

Khi cập nhật JDK vì bản vá bảo mật:
- Ứng dụng `app.jar` có thể không phải biên dịch lại;
- Archive AppCDS/AOT cũ có thể bị JVM từ chối;
- Cần **xây lại hoặc tự động tái tạo cache** theo cơ chế được JDK hỗ trợ;
- Triển khai phải ưu tiên patch bảo mật, **không giữ một JDK cũ chỉ để cache tiếp tục hoạt động**.

Không chép archive từ một JDK installation sang JDK khác chỉ vì chúng cùng tên release `17` hoặc `21`. Với container, pin **JDK image digest/build**, không chỉ pin một tag như `jdk:21` có thể di chuyển đến một build mới.

### 3.3. Một runtime image tùy biến cũng là đầu vào

Ứng dụng dùng `jlink` có thể tạo runtime image chứa tập module khác với JDK đầy đủ. Điều này ảnh hưởng môi trường lớp/module và cách JVM nạp chúng. Hãy tạo và xác thực cache cùng **runtime image đích**, không giả định cache sinh bằng JDK đầy đủ chắc chắn hợp lệ cho một image được cắt gọn.

Tương tự, không mặc định chuyển cache giữa những distribution JDK khác vendor/VM implementation hoặc giữa build với cấu hình nội bộ khác nhau là an toàn; dùng chính bản runtime production để tạo và kiểm thử.

## 4. Ảnh hưởng của kiến trúc CPU và hệ điều hành

CDS/AppCDS là **artifact VM-specific**, không phải một file JAR thuần Java. Không chuyển thẳng archive giữa:

- Linux x86-64 và Linux AArch64;
- Windows x64 và Linux x64;
- macOS ARM64 và Linux ARM64;
- JVM 32-bit với JVM 64-bit;
- Hai JVM khác nhau về các ràng buộc layout/VM options mà archive yêu cầu.

Theo JDK 24+ AOT cache guide, cache gắn với **một application, một JDK release và một OS/CPU architecture cụ thể**. Nếu một trong các yếu tố này đổi, **phải tái tạo AOT cache**.

### 4.1. “CPU Java bytecode portable” không suy ra “archive portable”

Java source/bytecode cung cấp mức di động của chương trình. JVM vẫn cần dùng những cấu trúc dữ liệu machine-specific; archive được JVM tạo nhằm **tối ưu chính JVM đó**. Vì vậy:

```text
Bytecode portable:    Java class/JAR
Archive không portable tùy ý:  AppCDS .jsa / AOT .aot
```

Đừng đưa `.jsa` vào một artifact chung rồi tái sử dụng xuyên Linux/Windows/macOS hoặc x64/ARM64.

### 4.2. Container multi-architecture

Trong pipeline tạo Docker/OCI image cho nhiều kiến trúc:
- Image Linux x64 cần cache được tạo/kiểm chứng với JDK Linux x64 tương ứng;
- Image Linux ARM64 cần cache được tạo/kiểm chứng với JDK Linux ARM64 tương ứng;
- Build trên máy phát triển Windows không sinh ra một archive portable cho container Linux chỉ vì `app.jar` giống hệt;
- Nếu hệ thống build dùng giả lập/QEMU, vẫn cần kiểm tra đúng **kiến trúc và JDK runtime đích**; đừng suy từ máy host.

**Thực hành phù hợp:** tạo cache ở build stage có cùng runtime/JDK/architecture với image production cuối cùng, hoặc tạo lại qua cơ chế hỗ trợ khi triển khai. Nên lưu cache **bên trong artifact image tương ứng**, không dùng một kho cache xuyên kiến trúc không có key phù hợp.

### 4.3. Có phải mọi tùy chọn GC đều luôn làm cache không hợp lệ?

**Không nên đưa ra quy tắc tuyệt đối như vậy.** Khả năng dùng archive có thể phụ thuộc một số JVM options ảnh hưởng layout hoặc class linking; nhưng những tối ưu mới, ví dụ JEP 516 trong JDK 26, còn mở rộng AOT object caching cho nhiều GC.

Do đó, không khẳng định “bắt buộc G1” hay “đổi bất kỳ GC nào sẽ làm mọi archive vô hiệu” trên mọi JDK. Thay vào đó:
1. Đọc tài liệu phiên bản JDK cụ thể;
2. Ghi nhận các flags quan trọng khi tạo cache;
3. Dùng log của VM để xác nhận archive/cache thực sự được chấp nhận;
4. Chạy test trên cấu hình GC/heap giống production khi những flags đó ảnh hưởng tối ưu.

## 5. Ảnh hưởng của classpath — thứ tự, đường dẫn và nội dung JAR

Đối với **CDS/AppCDS archive truyền thống**, classpath là một phần quan trọng của môi trường tạo cache.

Tài liệu `java` ở các JDK hiện đại quy định:
- **Classpath ở lúc tạo archive** phải giống hoặc là **tiền tố (*prefix*)** của classpath khi chạy;
- Các JAR mà archive phụ thuộc phải không bị thay đổi sau khi tạo archive;
- Những entry là **thư mục không rỗng** trên classpath không được hỗ trợ để tạo/sử dụng archive theo quy tắc CDS tương ứng;
- Đối với module path, có các quy tắc **khác** classpath (không yêu cầu prefix), nhưng JAR module bị thay đổi cũng làm archive không hợp lệ.

**Cẩn thận:** Những giới hạn này nói về **CDS/AppCDS**, không phải quy tắc bình thường của lệnh `java -cp`. Java bình thường hoàn toàn có thể nạp `.class` từ một thư mục; chỉ là **không được suy** CDS có thể archive toàn bộ thư mục như JAR hợp lệ.

### 5.1. Classpath là một danh sách có thứ tự

Ví dụ:

```text
Training classpath:  lib/core.jar ; lib/service.jar
Production:          lib/core.jar ; lib/service.jar ; lib/optional.jar
```

Với quy tắc CDS truyền thống, classpath training có thể là prefix của runtime classpath. Các lớp từ phần mới bổ sung có thể phải nạp bình thường.

Ngược lại:

```text
Training:  lib/core.jar ; lib/service.jar
Runtime:   lib/service.jar ; lib/core.jar
```

**Không phải cùng một classpath theo thứ tự**, dù tập tên file giống nhau. JVM class loading cũng có thể chọn class khác nếu hai JAR chứa những class trùng tên. Vì vậy đừng coi classpath là một `Set<String>` rồi sort lại tùy ý.

**Hệ điều hành khác nhau dùng dấu phân cách khác nhau:** trên Windows classpath thường dùng `;`, trên Linux/macOS dùng `:`. Với ví dụ chỉ có **một JAR**, dùng `-cp app.jar` để tránh phụ thuộc dấu phân cách.

### 5.2. Wildcard classpath và thứ tự dependency

`-cp "lib/*"` được Java launcher mở rộng thành danh sách JAR, nhưng **thứ tự JAR từ wildcard không được bảo đảm như một sorted dependency lockfile**. Nếu thứ tự thay đổi giữa training và production, kết quả classpath thực tế có thể khác.

Để triển khai chắc chắn:
- Dùng cơ chế launcher/framework có danh sách classpath xác định;
- Giữ nguyên dependency versions và thứ tự;
- Tái tạo cache khi thay dependency graph;
- Kiểm tra log classpath/CDS chứ không chỉ nhìn một wildcard giống nhau.

### 5.3. JAR đổi byte nhưng giữ tên file?

**Có thể làm archive bị vô hiệu.** JVM không chỉ kiểm tra chuỗi đường dẫn: nó kiểm tra tính phù hợp của nguồn lớp, bao gồm dữ liệu file JAR. Một JAR mới cùng tên `app.jar` và cùng vị trí `/app/app.jar` **không tự tương thích** với cache cũ.

Trong thử nghiệm thực tế với OpenJDK 24:
1. Tạo `app.jsa` từ `app.jar` chứa class trả chuỗi `V1`;
2. Tạo lại `app.jar` tại **cùng đường dẫn** nhưng class trả `V2_NEW`;
3. Chạy với `-Xshare:auto` và archive cũ;
4. JVM cảnh báo JAR không còn là file đã dùng lúc tạo archive, timestamp/size thay đổi;
5. Dynamic archive không được sử dụng; ứng dụng vẫn có thể chạy từ JAR mới.

Vì vậy cache phải gắn với **nội dung ứng dụng**, không chỉ với tên file, timestamp được ghi ở pipeline, hoặc nhãn bản release không thay đổi.

### 5.4. JAR chỉ đổi metadata có đáng quan tâm?

Cũng phải xem là **thay đổi artifact**. Chẳng hạn build tool đóng gói lại JAR, thay timestamps, manifest hoặc nội dung ZIP dù bytecode chủ yếu giống nhau; không được giả định JVM sẽ bỏ qua sự khác biệt.

**Quy tắc release:** bất cứ khi nào rebuild/replace JAR, dependency hoặc classpath, hãy **coi archive cũ cần được kiểm tra và thường phải tạo lại**, trừ khi cơ chế và JDK cụ thể bảo đảm trường hợp đó.

## 6. Module path và các launch options cũng là đầu vào

Với Java Platform Module System, cấu hình chạy có thể gồm:

```text
--module-path
--module
--add-modules
--enable-native-access
```

Tài liệu JDK 25/27 nêu rằng những giá trị liên quan tới module **nên nhất quán** giữa lúc tạo và lúc dùng CDS archive. Nếu lệch, archive có thể bị **vô hiệu một phần hoặc toàn bộ**; với những tối ưu AOT-linking cụ thể, những khác biệt còn có thể khiến archive không dùng được.

- **Module path không có cùng quy tắc prefix với classpath**, nhưng JAR module bị sửa sau khi tạo archive có thể làm cache vô hiệu.
- CDS hiện đại hỗ trợ **modular JAR**, không phải mọi exploded module tree.
- Một số options như `--upgrade-module-path`, `--patch-module`, `--limit-modules` làm CDS không khả dụng theo tài liệu `java`.
- Một số options `--add-modules` hoặc option làm thay đổi module graph có thể ảnh hưởng các archived optimization.

Không chuyển nguyên một bảng điều kiện của JDK 17 sang JDK 27 rồi coi là hợp đồng bất biến. Khi đang dùng AOT class linking, cần đọc **đúng tài liệu AOT của JDK hiện tại** vì các ràng buộc có thể chặt hơn traditional CDS.

### 6.1. `-jar` và `-cp`

`java -jar app.jar` và `java -cp app.jar demo.App` không phải hai chuỗi lệnh hoàn toàn tương đương về cách launcher xác định entry point và classpath; `-jar` sử dụng manifest và quy tắc classpath của nó.

Khi tạo cache:
- Dùng **cùng cách launch** với production;
- Ghi lại main class / main module / fat-JAR/extracted layout;
- Không thay `-jar` sang `-cp` hoặc đổi working directory mà bỏ qua kiểm tra;
- Với Spring Boot, Quarkus và các launcher tùy biến, xem hướng dẫn CDS/AOT riêng của framework vì class loader và layout JAR có thể ảnh hưởng mức độ share.

**Một archive không thay thế artifact ứng dụng.** Bạn vẫn phải mang theo những JAR, class files, modules, resources và config thật mà chương trình cần.

## 7. Input của ứng dụng ảnh hưởng những lớp nào được ghi vào cache

Đây là khái niệm **khác** với điều kiện tương thích nhị phân.

Trong **training run**, JVM nhìn thấy **những lớp thực sự được nạp**, không tự động lưu mọi class của tất cả dependency. Thông thường chỉ những lớp được sử dụng và đủ điều kiện mới được chọn để archive.

Ví dụ luồng:

```text
app.jar
  |
  +-- main() ----> CommonService             [được nạp trong mọi lần chạy]
  |
  +-- nếu args[0] == "REPORT"
          |
          +--> ReportService                 [chỉ nạp khi chạy nhánh REPORT]
          +--> PdfFormatter                  [chỉ nạp khi chạy nhánh REPORT]
```

Nếu training luôn dùng input không kích hoạt `REPORT`, các lớp chỉ đi qua nhánh đó có thể **không nằm trong dynamic archive**. Chạy production với `REPORT` không có nghĩa chương trình mất chức năng: JVM vẫn có thể nạp lớp còn thiếu **theo cách thông thường**.

### 7.1. Thay args không luôn làm archive “invalid”

Cần phân biệt:

**Trường hợp A — runtime input chỉ đổi code path:**
- JAR, classpath, module graph và options tương thích không đổi;
- Một tham số lệnh chọn nhánh khác;
- Archive có thể vẫn tương thích, nhưng tỉ lệ lớp được share thấp hơn nếu training không đại diện.

**Trường hợp B — input làm đổi classpath/module/class definition:**
- Tham số dẫn đến thêm JAR, đổi plugin folder, thay class loader, javaagent biến đổi bytecode;
- Đây có thể là **thay đổi điều kiện tương thích hoặc làm các class bị bỏ qua**;
- Phải xác minh bằng log và chạy thử với input thật.

Không khẳng định “chỉ cần args khác là archive vô hiệu”. Không khẳng định ngược lại “args không bao giờ ảnh hưởng CDS”. Điều quan trọng là **input có làm thay nội dung/class loading environment hay chỉ làm thay những lớp được đi qua**.

### 7.2. Training cần mang tính đại diện

Đối với một service lớn, training nên đi qua các tuyến thường xuyên:
- Khởi động DI/container và các subsystem sử dụng thật;
- Tạo một số request mô phỏng những API quan trọng;
- Nạp các service xuất hiện trong đường đi startup quan trọng;
- Đi qua các đường code phản ánh config production hợp lý.

Đừng buộc training gọi **mọi** code path hoặc mọi dependency chỉ để archive nhiều lớp nhất. Archive có chi phí bộ nhớ/đĩa và có thể chỉ mang lại lợi ích cho những lớp thực sự nạp sớm. Nên đo hiệu quả startup/warmup để chọn kịch bản training.

### 7.3. Dữ liệu môi trường và feature flags

Môi trường có thể ảnh hưởng số lớp được nạp:
- `-Dapp.mode=...` hoặc biến môi trường lựa chọn plugin;
- Profile Spring, Quarkus hay framework khác;
- Config quyết định driver JDBC hoặc client HTTP;
- Class path được tạo động theo `plugins/`;
- Agent và instrumentation.

Không phải mọi thay đổi của property đều là **lý do máy ảo từ chối archive**. Nhưng nếu property làm đổi **class definitions, module graph hoặc lớp thực sự dùng**, kết quả tái sử dụng có thể khác. Ghi lại các thiết lập quyết định hành vi trong cấu hình training và production.

## 8. Class loaders, instrumentation và lớp tạo động

Những tính năng như reflection, dependency injection, service discovery, dynamic proxy, `javaagent`, bytecode transformation và custom class loader có thể ảnh hưởng đến việc JVM nhìn thấy lớp nào và có thể archive lớp đó hay không.

Điều cần nói chính xác:
- **Không** phải mọi reflective class đều không được share;
- **Không** phải mọi custom class loader đều bị AppCDS cấm;
- Nhưng **không được cam kết** mọi class từ mọi loader/agent đều trở thành class được share.

Những trường hợp cần kiểm chứng thêm:
1. Class được sinh runtime bằng cơ chế dynamic generation;
2. Agent biến đổi bytecode giữa training và production;
3. Class definition cùng tên nhưng nạp từ nguồn JAR/loader khác;
4. Library dùng nested/fat JAR hoặc classloader riêng có đường dẫn khác;
5. Chương trình sửa classpath hoặc module resolution giữa hai lần.

Với một ứng dụng framework, trước hết xác định framework có hỗ trợ CDS/AOT với packaging mode nào; ưu tiên plugin build và quy trình AOT chính thức của framework, tránh tự đoán cách archive class từ nested JAR.

### 8.1. “Đã load JAR” chưa đủ để chứng minh class được archive

Một class xuất hiện trong log `-Xlog:class+load` có thể có nguồn:
- `shared objects file` hoặc `shared objects file (top)`: được nạp từ archive tương ứng;
- Một JAR path bình thường: class đang được nạp từ file JAR;
- Runtime image/module: lớp nền tảng được nạp theo các cơ chế của JDK.

Để kiểm chứng đúng AppCDS, cần xem **nguồn class load ở lần chạy production**, không chỉ thấy lần training đã mở file archive.

## 9. Chương trình minh họa đầy đủ: tạo JAR và dynamic AppCDS archive

Ví dụ này dùng **JDK 17+**, đã được kiểm chứng trên **OpenJDK 24.0.2 (Windows x64)**. Chúng ta chọn JDK mới vì cách tạo **dynamic CDS archive** vẫn còn được hỗ trợ và dễ dùng hơn quy trình lớp danh sách lịch sử từ JDK 10.

Lưu mã vào **`src/demo/CdsDemo.java`**:

```java
package demo;

import java.nio.charset.StandardCharsets;

public class CdsDemo {
    public static void main(String[] args) {
        Helper helper = new Helper();

        System.out.println("message=" + helper.message());
        System.out.println("feature=" + Runtime.version().feature());
        System.out.println("args=" + args.length);
    }
}

final class Helper {
    String message() {
        return new String(
                "CDS_OK".getBytes(StandardCharsets.US_ASCII),
                StandardCharsets.US_ASCII);
    }
}
```

Đây là **chương trình Java độc lập**, không có dependency bên ngoài JDK. Hai lớp `demo.CdsDemo` và `demo.Helper` được tạo từ cùng tệp nguồn. `Helper` được nạp khi chạy, tạo tình huống dễ quan sát với AppCDS.

### 9.1. Bước build ứng dụng thành JAR

Trên Linux/macOS, tại thư mục dự án:

```bash
mkdir -p classes
javac --release 17 -encoding UTF-8 -d classes src/demo/CdsDemo.java
jar --create --file app.jar -C classes .
```

Lệnh dùng `jar` đi kèm JDK, không cần Maven/Gradle. Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force classes | Out-Null
javac --release 17 -encoding UTF-8 -d classes src/demo/CdsDemo.java
jar --create --file app.jar -C classes .
```

**Lưu ý:** đây là thao tác tạo **JAR input**. Lúc này chưa có `app.jsa`. `javac --release 17` quyết định target bytecode/API; nó **không** khiến archive tạo sau đó tự tương thích với mọi JDK từ 17 trở lên.

### 9.2. Bước tạo dynamic archive

```bash
java -Xshare:auto -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.CdsDemo
```

Chạy ứng dụng với cùng classpath bạn định dùng về sau. Khi JVM kết thúc bình thường và archive được tạo thành công, bạn sẽ có file `app.jsa`.

**Stdout trên JDK 24 đã kiểm thử:**

```text
message=CDS_OK
feature=24
args=0
```

Dòng `feature=24` phụ thuộc **JDK đang chạy**. Nếu chạy trên JDK 17, 21, 25 hay 27 thì số feature sẽ tương ứng runtime đó; **đừng hard-code số 24 vào test được dùng cho mọi môi trường**.

Để xác nhận archive đã tạo, kiểm tra file tồn tại và kích thước khác 0. Trong thử nghiệm OpenJDK 24.0.2 ở một môi trường Windows x64, file được tạo với dung lượng **262.144 byte**; con số đó **không phải kích thước chuẩn**, sẽ khác theo ứng dụng/JDK.

### 9.3. Bước tái sử dụng archive

```bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar demo.CdsDemo extra
```

**Stdout trên JDK 24 đã kiểm thử:**

```text
message=CDS_OK
feature=24
args=1
```

Ở lần này `args=1` vì có thêm đối số `extra`. Việc thêm đối số đơn giản **không** ngăn chương trình tận dụng archive nếu các điều kiện tương thích vẫn đúng.

### 9.4. Chứng minh lớp đã nạp từ archive

Để kiểm tra, chạy:

```bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar demo.CdsDemo
```

Kết quả chứa rất nhiều dòng class load. Trong thử nghiệm OpenJDK 24.0.2, các dòng liên quan là:

```text
demo.CdsDemo source: shared objects file (top)
demo.Helper source: shared objects file (top)
message=CDS_OK
feature=24
args=0
```

Đây là **trích đoạn đã rút gọn**, bỏ prefix timestamps/log formatting và những lớp JDK không liên quan. Nó chứng minh **các lớp ứng dụng được nạp từ dynamic archive** trong lần chạy thử.

Nếu log thay vì vậy cho `demo.CdsDemo source: file:/.../app.jar`, lớp đang nạp từ file JAR. Điều này không nhất thiết là lỗi chương trình, nhưng cần tìm nguyên nhân archive không được áp dụng.

### 9.5. Phân biệt log và stdout

Tùy chọn `-Xlog:class+load=info` có thể ghi thêm hàng trăm dòng diagnostic. Không so sánh toàn bộ output với ba dòng ví dụ `message/feature/args` khi đang bật logging. Dùng `grep`, `Select-String` hoặc công cụ log để chỉ xem những class liên quan.

## 10. Thí nghiệm quan trọng: JAR thay đổi sau khi tạo archive

Đây là tình huống điển hình của câu hỏi **“đầu vào ứng dụng ảnh hưởng archive ra sao?”**.

### 10.1. Thao tác

1. Dùng chương trình ở mục 9, tạo `app.jar` chứa `Helper.message()` trả `"CDS_OK"`.
2. Dùng `-XX:ArchiveClassesAtExit=app.jsa` để tạo dynamic archive.
3. Giữ nguyên đường dẫn và tên `app.jar`, nhưng đổi mã nguồn `Helper.message()` để trả một chuỗi khác, ví dụ `"CDS_CHANGED"`.
4. Biên dịch và **tạo lại JAR** tại chính đường dẫn cũ.
5. Chạy `-Xshare:auto -XX:SharedArchiveFile=app.jsa` với JAR mới, bật `-Xlog:cds=info`.

Lệnh minh họa sau khi đã rebuild JAR:

```bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:cds=info -cp app.jar demo.CdsDemo
```

**Không** sửa archive bằng hex editor hoặc chép bytecode vào chính `.jsa`. Đó là artifact của JVM cần được tạo lại bằng công cụ phù hợp.

### 10.2. Kết quả đã quan sát

Trên OpenJDK 24.0.2, thí nghiệm với class đổi từ `V1` sang `V2_NEW` trong JAR cùng đường dẫn đã cho những tín hiệu:

```text
This file is not the one used while building the shared archive file: ...app.jar
... app.jar timestamp has changed.
... app.jar size has changed.
Unable to use shared archive. The top archive failed to load: ...app.jsa
```

Đây là **trích đoạn log**, không phải toàn bộ dòng/timestamps. Trạng thái exit của ứng dụng trong chế độ `-Xshare:auto` vẫn là **0**; chương trình chạy tiếp và nạp class mới từ JAR thay vì archive động đã lỗi.

Điểm chính:

- JVM phát hiện **JAR input khác**;
- **Dynamic top archive** không còn tái sử dụng được;
- JVM vẫn có thể sử dụng **default/base CDS archive** cho lớp nền tảng;
- `-Xshare:auto` cho phép fallback và không làm hoạt động nghiệp vụ thất bại chỉ vì top archive bị từ chối;
- Muốn lấy lại lợi ích AppCDS cho JAR mới, phải **tạo lại archive**.

### 10.3. Đừng kết luận sai từ một kết quả exit code 0

Một ứng dụng có thể khởi động thành công trong cả hai tình huống:
1. Dynamic AppCDS được dùng;
2. Dynamic AppCDS bị bỏ qua và lớp được load từ JAR.

Cả hai có thể in **cùng kết quả nghiệp vụ**. Vì vậy, **test chức năng PASS không chứng minh cache được sử dụng**. Phải kiểm tra log/class load hoặc metrics startup.

## 11. Archive không dùng được: hiểu `-Xshare:auto` và `-Xshare:on`

Các tùy chọn CDS phổ biến:

| Tùy chọn | Ý nghĩa | Dùng khi nào |
|---|---|---|
| `-Xshare:auto` | Thử dùng CDS khi có thể, fallback nếu không khả dụng | Hợp lý cho production cần tính sẵn sàng |
| `-Xshare:off` | Tắt CDS để so sánh/điều tra | Benchmark baseline hoặc debug |
| `-Xshare:on` | Yêu cầu dùng CDS; nếu không thể có thể thoát lỗi | **Chỉ QA/debug**, không nên mặc định dùng production |

Tài liệu JDK hiện đại lưu ý `-Xshare:on` có thể làm JVM thoát khi archive không hợp lệ, ví dụ đổi JDK hoặc classpath. Với ứng dụng cần **chạy đúng trước, tối ưu sau**, `-Xshare:auto` có ý nghĩa hơn.

### 11.1. Không che cảnh báo vì fallback chạy được

Nếu production thường xuyên bỏ qua archive:
- Ứng dụng vẫn có thể đúng về chức năng;
- Startup/footprint có thể xấu đi so với dự kiến;
- Quá trình tạo cache trong CI/CD có thể đang sai;
- Cache được publish nhưng không khớp JDK/JAR ở runtime.

Vì vậy, theo dõi tỷ lệ cache reuse và log cảnh báo sau deployment. Không biến fallback thành tình trạng kéo dài mà không có metrics.

### 11.2. Các bước kiểm tra

```bash
java -version
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp app.jar demo.CdsDemo
```

Với JDK hỗ trợ, thêm `-Xlog:class+load=info` để xem lớp ứng dụng có nguồn `shared objects file (top)` hay không.

Nếu log báo mismatch, hãy kiểm tra:
1. Có đúng JDK build/distribution/runtime image không?
2. Có đúng OS và CPU architecture không?
3. Có thay `app.jar` hay dependency JAR không?
4. Có đổi thứ tự/giá trị classpath hoặc launch mode không?
5. Có thay module options hoặc agent/VM options ảnh hưởng linking không?
6. Archive đã được tạo bởi cách và JDK nào?
7. Những class mong đợi có xuất hiện trong training path không?

**Đừng sửa cache bằng tay** hoặc vô hiệu hóa các validation của JVM để cưỡng bức dùng một archive không tương thích.

## 12. JDK 24+ — AOT cache là bước phát triển tiếp theo

Từ JDK 24, **JEP 483** giới thiệu AOT cache, cho phép lưu thêm các artifact tối ưu liên quan **class loading và linking**. Đây là một bước phát triển từ nền tảng CDS/AppCDS, không phải bằng chứng rằng bytecode/JAR đã trở thành archive dùng chung vô điều kiện.

Một AOT cache ràng buộc theo:
- **Application**: biểu diễn bởi `-classpath`, `-jar` hoặc `--module-path` và những thành phần liên quan;
- **JDK release/build thích hợp**;
- **OS và CPU architecture**;
- **Những tùy chọn/cấu hình cần nhất quán** giữa các giai đoạn training, assembly và production.

Nếu những yếu tố này đổi, cần **tạo lại AOT cache**.

### 12.1. Ba giai đoạn

```text
1. Training
   Ứng dụng chạy với workload đại diện
   -> tạo dữ liệu thống kê/config

2. Assembly
   JVM dùng config để tạo AOT cache
   -> file .aot

3. Production
   JVM dùng AOT cache để tăng tốc
   -> ứng dụng vẫn có JAR/runtime input thật
```

Đây là luồng AOT, không giống việc tạo một native executable độc lập. File `.aot` không thay `java`, không thay `app.jar` và không phải container image hoàn chỉnh.

### 12.2. Lệnh JDK 24 được kiểm chứng

Với cùng `app.jar` và class `demo.CdsDemo` ở mục 9, có thể dùng:

```bash
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar demo.CdsDemo

java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar demo.CdsDemo

java -XX:AOTMode=auto -XX:AOTCache=app.aot -cp app.jar demo.CdsDemo
```

**Đây là ví dụ cú pháp JDK 24**. Trong thử nghiệm OpenJDK 24.0.2 với một JAR nhỏ:
- Lượt `record` chạy ứng dụng và tạo file `app.aotconfig`, exit 0;
- Lượt `create` tạo `app.aot`, exit 0;
- Lượt production chạy chương trình, exit 0.

Đừng hard-code dung lượng `.aot` hoặc prefix log cho mọi JDK; những số này phụ thuộc runtime và workload.

### 12.3. JDK 25+ có workflow thuận tiện hơn

**JEP 514** ở JDK 25 đơn giản hóa một số tình huống bằng `-XX:AOTCacheOutput=...`: khi training, JVM có thể khởi chạy giai đoạn assembly phù hợp mà không yêu cầu người vận hành tự gõ hai lệnh record/create như ví dụ JDK 24.

Ví dụ theo tài liệu JDK 25/27:

```bash
java -XX:AOTCacheOutput=app.aot -cp app.jar demo.CdsDemo
java -XX:AOTCache=app.aot -cp app.jar demo.CdsDemo
```

Đây là **mẫu JDK 25+**, không chạy trên Java 10/17/21. Cách xử lý chế độ `auto`, `record`, `create`, `on/required` thay đổi theo phiên bản; dùng tài liệu của **JDK bạn triển khai** làm nguồn chính thức.

**JDK 27** bổ sung `-XX:AOTMode=required` như alias có tên rõ nghĩa hơn cho `-XX:AOTMode=on`. Chế độ này phù hợp **QA fail-fast** khi bạn chủ ý yêu cầu archive; đối với production cần fallback, chế độ `auto` thường phù hợp hơn.

### 12.4. Không trộn khuyến nghị của JDK 24, 25, 27

- **Java 10:** AppCDS là JEP 310, nên hiểu nguyên lý và lịch sử, nhưng không copy nguyên mọi flag từ tài liệu cũ sang mới.
- **Java 17/21:** dynamic CDS với `ArchiveClassesAtExit` / `SharedArchiveFile` là cách thực hành hữu ích.
- **Java 24:** AOT cache đã có qua JEP 483, record/create/production.
- **Java 25+:** JEP 514 hỗ trợ tạo cache dễ hơn; những tối ưu khác như method profiling có thể bổ sung.
- **Java 27:** `AOTMode=required` giúp mô tả chính sách bắt buộc rõ hơn.

Không dùng `-Xlog:aot` như một tùy chọn chẩn đoán **được cam kết có mặt trên mọi JDK 24**: thử nghiệm OpenJDK 24.0.2 cho thấy JVM cảnh báo tag `aot` chưa được nhận diện. Trên JDK 24, `-Xlog:cds=info` là lựa chọn đã kiểm chứng cho dữ liệu liên quan CDS/AOT; trên JDK 25/27, dùng tag và options được man page bản đó mô tả.

## 13. Một bảng điều kiện tương thích để ra quyết định

| Thay đổi giữa tạo và chạy | Traditional CDS/AppCDS | AOT cache JDK 24+ | Hành động hợp lý |
|---|---|---|---|
| Cập nhật JDK build | Archive gắn với JDK build, có thể không hợp lệ | Phải tái tạo cho JDK tương thích | Build cache mới theo JDK production |
| Đổi vendor/JDK image | Không mặc nhiên tương thích | Không mặc nhiên tương thích | Tạo lại, kiểm chứng trên image đích |
| Windows x64 → Linux x64 | Không được mặc định portable | OS khác: tạo lại | Build trên OS/arch đích |
| Linux x64 → Linux ARM64 | Không được mặc định portable | CPU arch khác: tạo lại | Cache riêng mỗi architecture |
| Rebuild `app.jar` cùng tên | Có thể bị JVM từ chối | App identity thay đổi, cần tạo lại | Cache theo digest ứng dụng |
| Đổi dependency JAR | Có thể vô hiệu archive hoặc làm lớp không dùng được | Phải xem là ứng dụng mới | Tạo lại/verify |
| Đổi thứ tự classpath | Có thể phá quy tắc prefix/tính nhất quán | Có thể không tương thích | Giữ launcher/classpath cố định |
| Bổ sung JAR cuối classpath | Có thể phù hợp với prefix rule, nhưng lớp bổ sung không nhất thiết được archive | Không suy tương thích tự động | Test đầy đủ, thường tạo lại AOT |
| Đổi module graph | Có thể vô hiệu một phần/toàn bộ | Có thể phá AOT-linked graph | Kiểm tra options và tái tạo |
| Đổi args chỉ chọn nhánh code | Không nhất thiết làm archive invalid; thay class coverage | Có thể thay hiệu quả training | Training workload đại diện, test reuse |
| Đổi `-javaagent`/instrumentation | Có thể ảnh hưởng class definitions/optimization | Có thể không tương thích | Kiểm chứng thực tế và tạo lại khi cần |
| Thay thông số tài nguyên như heap | Phụ thuộc những flags cụ thể và phiên bản | Phụ thuộc cấu hình tương thích | Đọc log, đừng suy quy tắc tuyệt đối |
| File archive bị thiếu/quyền truy cập sai | Không thể dùng archive đó | Không thể load cache | Fallback, báo cảnh báo và sửa pipeline |

**Đọc bảng như hướng dẫn kiểm tra**, không phải danh sách đảm bảo chính xác mọi điều kiện ở mọi JDK. Mức độ vô hiệu hóa có thể là **toàn bộ archive, một phần archived graph, hoặc chỉ một số lớp không được share**. Log từ VM là nguồn quyết định cho phiên bản đang chạy.

## 14. Thiết kế cache key trong CI/CD

Khi tạo kho AppCDS/AOT ở pipeline, cần tránh **cache collision** giữa build khác nhau. Một cache key triển khai có thể dùng những thành phần như:

```text
cache-key-inputs:
  jdk_image_digest
  jdk_vendor_and_build
  os_and_cpu_architecture
  application_jar_digest
  dependency_jar_digests_in_order
  launch_mode_and_classpath_or_modulepath
  jvm_options_affecting_class_loading
  training_recipe_version
```

Đây là **mô tả thiết kế cache key cho pipeline**, **không** phải thuật toán hash nội bộ của HotSpot hay một YAML cấu hình đã được JVM đọc.

### 14.1. Vì sao dùng digest thay vì chỉ tên/version?

Tên file `app.jar` có thể không đổi qua nhiều lần deploy; `tag:latest` cũng có thể trỏ đến image mới. Dùng digest giúp phát hiện **nội dung artifact thay đổi** mà không phụ thuộc tên.

Ví dụ:
- `SHA-256` của từng JAR ứng dụng/dependency;
- Digest immutable của container image JDK;
- ID build và version JVM thực sự;
- Kiến trúc đích (ví dụ `linux/amd64`, `linux/arm64`);
- Phiên bản quy trình training.

Không phải mọi input phải thành một trường trong chuỗi hash nếu tổ chức đã có provenance/manifest tương đương; mục tiêu là **không tái dùng cache nhầm môi trường**.

### 14.2. Lưu cache cùng release artifact

Pipeline đáng tin cậy:

```text
Source commit
   |
   v
Compile/Package -----> app.jar + dependency lock
   |
   v
Select exact JDK image, OS/arch and startup configuration
   |
   v
Run representative training -> create archive
   |
   v
Verify archive reuse with EXACT packaged app
   |
   v
Publish {app.jar, dependencies, JDK image reference, archive, metadata}
   |
   v
Deploy on matching runtime and monitor fallback logs
```

Nếu đổi JAR sau khi đã tạo cache, phải quay lại bước tạo cache. **Không ký/publish một archive** rồi tiếp tục rebuild JAR mà giữ nguyên cache.

### 14.3. Không gộp tất cả architecture vào một cache file

Một registry có thể chứa nhiều artifact riêng, nhưng key phải phân biệt OS/CPU và runtime build. Trên OCI multi-platform image, tạo cache cho mỗi image variant thay vì “một archive dùng chung ở tất cả layer”.

Cũng không nên để nhiều tiến trình ghi đè đồng thời cùng một `.jsa` hoặc `.aot` trong thư mục shared volume mà không có điều phối. Với pipeline production, tạo cache hoàn chỉnh rồi **publish atomically** hoặc sử dụng cơ chế runtime được tài liệu mô tả.

## 15. QA trước khi đưa archive vào production

Có ba tầng test cần tách rời:

### 15.1. Kiểm thử chức năng

Chạy ứng dụng khi **tắt CDS**:

```bash
java -Xshare:off -cp app.jar demo.CdsDemo
```

Chạy cùng ứng dụng khi **bật archive**:

```bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar demo.CdsDemo
```

So sánh kết quả nghiệp vụ. Trong demo, `message=CDS_OK` phải giống nhau. Các dòng metadata như `feature` phụ thuộc runtime; test nên biết đó là giá trị môi trường.

### 15.2. Kiểm thử archive có được dùng

Chạy:

```bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa -cp app.jar demo.CdsDemo
```

Tìm những lớp mục tiêu và dòng `source: shared objects file (top)`. Có thể bổ sung `-Xlog:cds=info` để xem cảnh báo tương thích.

**Không dùng** thành công của `java -version` hay sự tồn tại của file `.jsa` làm bằng chứng duy nhất. Archive có thể tồn tại nhưng không được nạp.

### 15.3. Kiểm thử khi cache không tương thích

Tạo một tình huống test riêng:
- Rebuild JAR, đổi một class rồi chạy với archive cũ;
- Hoặc sử dụng một JDK/runtime không khớp trong môi trường thí nghiệm;
- Quan sát `-Xshare:auto` fallback và chương trình vẫn hoạt động;
- Kiểm tra production monitoring có **báo cache miss**.

Không thử nghiệm phá archive trên dữ liệu production thật. Nên tạo workspace tạm có thể xóa.

Với AOT JDK 27, có thể dùng chế độ yêu cầu cache `-XX:AOTMode=required` ở **giai đoạn QA** để fail-fast nếu cache không khả dụng. Đối với các bản hỗ trợ `-XX:AOTMode=on`, ý nghĩa fail-fast tương tự; chọn flag theo đúng phiên bản runtime và tài liệu.

## 16. Đo hiệu quả thật, không chỉ đo dung lượng archive

AppCDS/AOT cache là tối ưu hóa. Nếu chỉ thấy file `app.jsa` vài MB hoặc vài chục MB, **chưa thể kết luận ứng dụng sẽ nhanh hơn**.

Nên đo:
- **Cold start** và **warm start** qua nhiều lần lặp;
- Thời gian đến khi service nhận request đầu tiên/health check ready;
- `p50`, `p95` của startup latency trong môi trường tương tự;
- Memory footprint thực tế của nhiều JVM cùng chạy (ưu tiên chỉ số vật lý phù hợp như PSS trên Linux khi cần);
- Dung lượng `.jsa`/`.aot` và chi phí tạo cache;
- Tỷ lệ lớp được load từ archive;
- Tỉ lệ cache hợp lệ sau rollout JDK/app mới.

**Không chỉ nhìn RSS của một JVM** rồi khẳng định memory sharing “không có tác dụng” vì mapped pages có thể được phản ánh khác trong các công cụ đo. Cần hiểu chỉ số và đo thực tế cho nhiều tiến trình.

### 16.1. Thiết kế benchmark công bằng

Để so sánh:
1. Dùng cùng JDK/OS/arch và cùng build ứng dụng;
2. Giữ nguyên GC/heap/flags nếu không phải biến đang thử;
3. Kiểm tra cache thật sự được dùng ở nhánh test bật;
4. Chạy đủ số lần để giảm nhiễu từ hệ điều hành, filesystem cache, JIT và container;
5. Đo một chỉ số có ý nghĩa với người dùng, ví dụ thời gian đến ready hoặc request đầu tiên.

**Không tạo cache bằng một JAR rồi đo ứng dụng bằng JAR khác**. Kết quả có thể chỉ phản ánh đường fallback.

### 16.2. Không archive mọi class bằng mọi giá

Dữ liệu archived có thể chiếm dung lượng lớn hơn dạng class nén trong JAR. Training càng rộng không luôn càng tốt. Cần đo trade-off giữa startup improvement, disk/memory footprint và công sức vận hành cache.

## 17. Sự khác nhau giữa cache hợp lệ, cache hữu dụng và cache an toàn

Ba khái niệm:

- **Hợp lệ:** JVM chấp nhận archive, không vi phạm điều kiện compatibility.
- **Hữu dụng:** workload thực sự dùng được nhiều lớp đã archive và có lợi ích startup/memory.
- **An toàn vận hành:** cache được tạo từ artifact tin cậy, không che bản cập nhật bảo mật, có chính sách fallback và provenance.

Một archive có thể **hợp lệ nhưng ít hữu dụng** nếu training không đi qua các lớp chính. Nó cũng có thể **không hợp lệ nhưng ứng dụng vẫn an toàn về chức năng** nếu `-Xshare:auto` fallback đúng.

Cache nên được coi là **derived artifact**. Đừng dùng nó làm nguồn sự thật duy nhất của code đã triển khai; nguồn chính vẫn là JDK/runtime image và ứng dụng/JAR/dependencies đã được phê duyệt.

### 17.1. Tính toàn vẹn và supply chain

Archive có thể chứa dữ liệu nội bộ JVM và thông tin liên quan lớp. Không tải và dùng một file cache không rõ nguồn chỉ vì tên file giống ứng dụng của bạn.

Nên:
- Tạo archive từ artifact được CI/CD xác minh;
- Giữ metadata về JDK, kiến trúc, JAR digest;
- Giới hạn quyền sửa archive trong production;
- Không để người dùng không tin cậy điều khiển đường dẫn/nguồn cache;
- Tái tạo cache sau khi vá JDK hoặc dependency, thay vì cố giữ cache từ build cũ.

## 18. Các hiểu nhầm phổ biến

| Hiểu nhầm | Điều đúng |
|---|---|
| “CDS chỉ tồn tại ở Java 10.” | CDS có trước; **AppCDS** được mở rộng ở Java 10 và vẫn dùng hiện nay. |
| “File JAR chạy trên JDK mới thì archive cũng chạy được.” | Bytecode compatibility **khác** archive compatibility. |
| “Chỉ cần `java -version` cùng major là đủ.” | Archive có thể gắn với **từng JDK build/runtime image**. |
| “Có thể copy `.jsa` từ Windows x64 sang Linux ARM64.” | Không coi archive là portable; tạo theo OS/CPU runtime đích. |
| “Đổi nội dung JAR nhưng giữ tên `app.jar` vẫn an toàn.” | JVM có thể từ chối archive do JAR khác. |
| “`-cp a.jar;b.jar` và `-cp b.jar;a.jar` giống nhau.” | Classpath có thứ tự; điều kiện archive và class loading có thể khác. |
| “Cứ đưa thư mục `classes/` vào classpath là AppCDS archive mọi lớp bên trong.” | Traditional CDS có giới hạn non-empty directories; dùng JAR được hỗ trợ. |
| “Module path cũng có yêu cầu prefix giống classpath.” | Không: module path có quy tắc riêng. |
| “Args khác trong training làm mọi archive invalid.” | Không nhất thiết. Nó có thể đổi **coverage** mà không đổi tương thích. |
| “Training một lần nạp mọi lớp trong tất cả dependency JAR.” | Không. Lớp cần thực sự được load và đủ điều kiện. |
| “Mọi `javaagent` đều hoàn toàn vô hại với CDS.” | Instrumentation có thể làm khác class definition/optimization; phải test. |
| “Ứng dụng chạy exit 0 chứng minh archive đã được dùng.” | Không. `-Xshare:auto` có thể fallback. |
| “`-Xshare:on` nên dùng production để ép tối ưu.” | Có thể khiến JVM không khởi động; thường để debug/QA. |
| “`-Xshare:auto` không dùng AppCDS thì mất luôn mọi CDS.” | Dynamic top archive có thể bị bỏ qua nhưng base/default archive vẫn có thể được dùng. |
| “AOT cache là native executable thay JAR.” | Không. Nó là dữ liệu tối ưu hóa bổ sung, cần runtime và application. |
| “JDK 24 và JDK 27 dùng đúng cùng cú pháp AOT.” | Không nên suy; JDK 25 có JEP 514, JDK 27 có `AOTMode=required`. |
| “AOT cache chỉ hợp lệ với G1 ở mọi JDK tương lai.” | Không. Khả năng GC thay đổi, JDK 26 có JEP 516. |
| “File archive càng lớn luôn càng tốt.” | Không. Chi phí đĩa, thời gian tạo và hiệu quả cần đo. |
| “Archive là backup đủ của ứng dụng.” | Không. Phải triển khai JAR/modules/resources/config thật. |
| “Dùng một cache cho mọi node/container không cần phân biệt bản build.” | Cần key theo runtime, OS/CPU và application inputs. |

## 19. Checklist code review và release engineering

- [ ] Có phân biệt **CDS**, **AppCDS** và **AOT cache** theo JDK cụ thể?
- [ ] JDK/runtime image dùng tạo archive có đúng với image production (build/digest) không?
- [ ] OS và CPU architecture có khớp không?
- [ ] JAR/dependency digests có được cố định và kiểm tra trước khi publish?
- [ ] Classpath có giữ đúng thứ tự/đường dẫn và quy tắc prefix khi áp dụng không?
- [ ] Dùng modular JAR thay vì exploded module directory ở những trường hợp CDS yêu cầu?
- [ ] `--module-path`, `--module`, `--add-modules` và các startup flags có nhất quán?
- [ ] Các agent/classloader/plugin có thể thay class definitions hay classpath không?
- [ ] Training workload có đi qua các nhánh startup quan trọng không?
- [ ] Đã phân biệt thay **args** với thay **classpath/class definitions**?
- [ ] Có chạy lại archive generation sau khi rebuild JAR hoặc patch JDK không?
- [ ] Đã xác minh ứng dụng chạy giống nhau ở `-Xshare:off` và chế độ dùng archive?
- [ ] Đã kiểm tra `-Xlog:cds` và/hoặc nguồn class load để chứng minh archive được dùng?
- [ ] Production dùng fallback phù hợp thay vì fail-fast một cách không chủ đích?
- [ ] Alert/metrics có phát hiện cache bị bỏ qua sau rollout không?
- [ ] Có tránh biến `.jsa/.aot` thành artifact toàn kiến trúc hoặc nguồn sự thật duy nhất?
- [ ] Có giới hạn quyền ghi, bảo đảm provenance của cache và kiểm soát cache key?
- [ ] Benchmark có so cùng JDK/app và ghi nhận start latency có ý nghĩa?

Một nhận xét review có cơ sở:

> “Archive được build từ `app.jar` trước bước repackaging. Sau đó pipeline lại tạo JAR ở cùng tên file. JVM có thể coi JAR không còn tương thích với archive. Hãy generate archive **sau lần đóng gói cuối cùng** và kiểm tra reuse với chính artifact sẽ phát hành.”

Một nhận xét khác:

> “Pipeline publish một `app.jsa` chung cho `linux/amd64` và `linux/arm64`. Archive không portable qua kiến trúc; cần cache riêng theo mỗi runtime image/architecture.”

Đừng đề xuất:

> “Tắt cảnh báo bằng cách ép `-Xshare:on` trong production; có cache là chắc chắn nhanh.”

Cưỡng bức dùng archive không tương thích có thể làm JVM không khởi động.

## 20. Câu hỏi ôn tập có đáp án

**Câu 1.** AppCDS ra đời trong Java mấy?

**Đáp án:** Java 10, JEP 310. Cơ chế CDS nền tảng có trước đó.

**Câu 2.** Một `app.jar` biên dịch target Java 17 chạy trên JDK 24 có nghĩa file `app.jsa` tạo bởi JDK 17 cũng dùng được trên JDK 24 không?

**Đáp án:** Không. Bytecode/JAR compatibility và archive compatibility khác nhau. Archive ràng buộc với JDK tạo ra nó.

**Câu 3.** Hai JDK có cùng FEATURE nhưng khác build có thể dùng chung archive không?

**Đáp án:** Không được mặc định. Tài liệu nêu archive phụ thuộc JDK build; nên tạo lại và xác minh.

**Câu 4.** AppCDS archive trên Windows x64 có thể copy nguyên sang Linux ARM64 không?

**Đáp án:** Không nên. OS/architecture khác; cần tạo archive trên runtime đích.

**Câu 5.** Sửa class trong `app.jar` nhưng giữ cùng đường dẫn có thể làm gì?

**Đáp án:** JVM có thể từ chối dynamic archive do JAR đã thay đổi, rồi dùng đường load bình thường ở chế độ fallback.

**Câu 6.** Tại sao classpath order quan trọng?

**Đáp án:** Thứ tự ảnh hưởng class resolution và là một phần điều kiện tương thích CDS; cùng tập JAR nhưng thứ tự khác không mặc định tương đương.

**Câu 7.** Quy tắc prefix của classpath có áp dụng y nguyên cho module path không?

**Đáp án:** Không. Module path có quy tắc khác, nhưng JAR module thay đổi vẫn có thể vô hiệu archive.

**Câu 8.** Training chỉ chạy nhánh BASE, production chạy REPORT. Archive có buộc invalid không?

**Đáp án:** Không chỉ vì args khác. Cache có thể vẫn dùng nhưng những lớp chỉ được tải trong nhánh REPORT có thể không nằm trong archive.

**Câu 9.** Có thể dùng `-Xlog:class+load=info` để xác minh gì?

**Đáp án:** Nguồn nạp lớp, ví dụ `source: shared objects file (top)` cho class trong dynamic archive.

**Câu 10.** `-Xshare:auto` khác `-Xshare:on` ở điểm quan trọng nào?

**Đáp án:** Auto có thể fallback nếu không dùng được CDS; on có thể khiến JVM thoát khi không thỏa điều kiện. Production thường ưu tiên tính sẵn sàng.

**Câu 11.** Nếu chương trình in đúng stdout, có biết archive được dùng không?

**Đáp án:** Không. Cần kiểm tra log và nguồn class load.

**Câu 12.** JDK 24 bổ sung công nghệ liên quan gì?

**Đáp án:** JEP 483 AOT Class Loading & Linking và AOT cache, mở rộng cơ chế chuẩn bị lớp.

**Câu 13.** JDK 25 và JDK 27 khác gì ở một số tùy chọn AOT?

**Đáp án:** JDK 25 có JEP 514 để đơn giản hóa tạo cache; JDK 27 bổ sung `-XX:AOTMode=required` cho cách diễn đạt yêu cầu fail-fast.

**Câu 14.** Tại sao cache key nên chứa JDK image digest và JAR digest?

**Đáp án:** Vì tên tag và tên file có thể không đổi dù nội dung runtime hoặc ứng dụng đã thay đổi.

**Câu 15.** AOT cache có thay hoàn toàn JAR của ứng dụng không?

**Đáp án:** Không. Nó là artifact tối ưu hóa phụ thuộc ứng dụng/JDK/OS/CPU.

**Câu 16.** Có nên trì hoãn security patch JDK để giữ archive cũ còn dùng được không?

**Đáp án:** Không. Cập nhật JDK và tái tạo cache tương ứng.

**Câu 17.** Một non-empty directory trên classpath bình thường có hợp lệ không? Có mặc nhiên hợp lệ cho traditional CDS archive không?

**Đáp án:** Java launcher bình thường có thể dùng directory, nhưng traditional CDS có các hạn chế riêng khi tạo/nhận archive.

**Câu 18.** Nếu archive lớn nhưng không giảm thời gian startup, vấn đề có thể là gì?

**Đáp án:** Training không đại diện, lớp chưa được reuse, startup bottleneck nằm nơi khác, chi phí archive hoặc điều kiện tương thích không phù hợp. Cần đo và xem log.

## 21. Tài liệu chính thức và nguồn cập nhật

- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): mốc Java 10 mở rộng CDS cho ứng dụng.
- [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): archive mặc định từ JDK 12 trong các distribution tương ứng.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): cơ chế archive động từ JDK 13.
- [Oracle JDK 21 — The java Command: Application Class Data Sharing](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): giới hạn classpath/module path, `ArchiveClassesAtExit`, `SharedArchiveFile`, `AutoCreateSharedArchive`.
- [Oracle JDK 27 — The java Command: Application Class Data Sharing & Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): quy tắc compatibility hiện đại, AOT modes và logging.
- [Oracle JDK 27 — Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): `-XX:AOTMode=required` và các thay đổi JVM ảnh hưởng cấu hình.
- [Oracle Java SE 26 — Class Data Sharing Guide](https://docs.oracle.com/en/java/javase/26/vm/class-data-sharing.html): cơ chế CDS/AppCDS còn được hỗ trợ.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache từ JDK 24.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): quy trình CLI thuận tiện hơn từ JDK 25.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): mở rộng thông tin AOT cho warm-up.
- [OpenJDK JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): bối cảnh JDK 26 để tránh áp dụng hạn chế GC cũ cho mọi đời cache.
- [Dev.java — The java Command: Application Class Data Sharing](https://dev.java/learn/jvm/tools/core/java/): giải thích class locations và giới hạn CDS.

**Ghi nhớ:** **AppCDS archive là cache phụ thuộc môi trường, không phải artifact Java portable**. Tính hợp lệ gắn với **JDK/build, OS/CPU và JAR/classpath/module path**. Đầu vào ứng dụng còn quyết định **những lớp nào thực sự được training và ghi vào cache**. Khi đổi JDK, kiến trúc hoặc bản build ứng dụng, hãy tạo lại hoặc kiểm tra rõ cơ chế tái tạo cache; dùng log để xác nhận, giữ fallback production phù hợp và không nhầm cache với JAR hay bản phát hành gốc.