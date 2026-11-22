# Java 10 – Nền tảng AppCDS: Giới hạn và chi phí lưu trữ của kho AppCDS

> **Phạm vi:** Java 10 → **Nền tảng AppCDS** → **Giới hạn và chi phí lưu trữ của kho AppCDS**. AppCDS (*Application Class-Data Sharing*) được đưa vào OpenJDK qua **JEP 310 (JDK 10)**, mở rộng cơ chế CDS để có thể lưu dữ liệu lớp của ứng dụng vào một archive dùng lại. Bài học tập trung vào **giới hạn kỹ thuật, dung lượng đĩa, bộ nhớ được ánh xạ/chia sẻ, chi phí tạo/duy trì archive và cách đo hiệu quả thực tế**. Lệnh demo sử dụng **JDK 17+**, bao gồm dynamic CDS archive có từ JDK 13; không yêu cầu chạy lại JDK 10 hay bật các cờ thương mại/lỗi thời của bản phát hành cũ.

## 1. Kết quả học tập và kết luận quan trọng

Sau bài học, bạn có thể:

1. Phân biệt **JAR/classfile**, **CDS/AppCDS archive (`.jsa`)**, **JDK default CDS archive**, **dynamic archive bổ sung** và **bộ nhớ của tiến trình JVM**.
2. Giải thích vì sao kho AppCDS sử dụng thêm **dung lượng lưu trữ vật lý**, dù mục tiêu là giảm chi phí nạp lớp và có thể giảm bộ nhớ chung của nhiều JVM.
3. Đọc đúng nhận định trong tài liệu Oracle: **dữ liệu lớp được lưu theo định dạng archive tối ưu có thể lớn khoảng 2–5 lần dữ liệu lớp trong JAR/JDK runtime image**. Đây **không** phải hệ số cố định áp vào toàn bộ kích thước ứng dụng hay một cam kết tỷ lệ cho mọi file `.jsa`.
4. Hiểu vai trò của **memory mapping**, các trang **read-only được chia sẻ**, và khác biệt giữa **RSS**, **PSS**, **virtual memory**, **file-backed page cache** và **heap**.
5. Xác định lúc nào một archive chung được nhiều tiến trình dùng lại có lợi hơn lưu nhiều bản archive riêng.
6. Nhận diện ràng buộc về **JDK build**, **JAR/classpath/module-path**, runtime options, class loaders và các phiên bản archive.
7. Phân biệt **static archive** với **dynamic archive** và quan hệ **base + top**, bao gồm giới hạn số archive được JVM dùng.
8. Ước tính chi phí tạo archive, warm-up/test workload, CPU/I/O, thời gian CI, kích thước container image và số bản lưu giữ để rollback.
9. Phân tích trường hợp lớp **không được đưa vào archive**, archive bị bỏ qua/không nạp được hoặc không tạo ra cải thiện.
10. Chạy demo Java 17+ đóng gói thành JAR, tạo archive động, sử dụng lại archive, đo byte trên đĩa và kiểm tra log chứng minh lớp được tải từ archive.
11. Thiết kế benchmark công bằng, phân biệt cold/warm file-system cache và không suy hiệu quả từ một lần đo startup.
12. Đưa ra quyết định **giữ AppCDS, thu hẹp tập lớp, tạo lại hay tắt tùy biến AppCDS** dựa trên số liệu.

**Nguyên tắc chính:** AppCDS là cách **đánh đổi công sức chuẩn bị và dung lượng file để giảm việc nạp/chuyển đổi metadata ở lúc JVM khởi động**. Archive không thay thế JAR; nó cũng **không phải** bản chụp toàn bộ heap của ứng dụng. Tối ưu hợp lý khi chi phí tạo/lưu/duy trì archive thấp hơn lợi ích đo được về startup và bộ nhớ trong workload thực.

## 2. CDS và AppCDS lưu trữ những gì?

Một ứng dụng Java thông thường có JAR chứa `.class` (bytecode và metadata trong định dạng classfile), resources và dependencies. Khi khởi động, JVM đọc lớp, kiểm tra/liên kết và tạo cấu trúc phục vụ thực thi. Với **CDS**, JVM có thể lưu sẵn một phần thông tin lớp đã được xử lý vào archive ở định dạng thuận tiện hơn cho JVM rồi **memory-map** archive trong những lần chạy phù hợp.

**AppCDS** mở rộng cơ chế này từ các lớp lõi sang các lớp từ ứng dụng/thư viện, khi chúng đáp ứng các điều kiện archive/load của JVM.

~~~text
Các tập tin ứng dụng / runtime
┌──────────────────────┐     ┌──────────────────────────────┐
│ app.jar, lib/*.jar    │     │ JDK runtime image (modules)  │
│ classfiles, resources │     │ default classes.jsa (CDS)    │
└──────────┬───────────┘     └──────────────┬───────────────┘
           │                                │
           │ chạy workload đại diện         │ base archive
           v                                v
    Tạo AppCDS archive              ┌──────────────────┐
    (các lớp đủ điều kiện)  ────────>│ app.jsa (top)    │
                                    └────────┬─────────┘
                                             │
                                    lần khởi động sau
                                             v
                             N JVM map cùng file phù hợp
                             ↓             ↓             ↓
                           JVM A         JVM B         JVM C
~~~

Đây là sơ đồ **khái niệm**. Trong môi trường cụ thể, một JVM có thể dùng một static archive hoặc cặp **static + dynamic**; với JDK hiện đại, archive động có thể tham chiếu base archive của JDK. Không được xóa base tùy ý nếu archive top còn phụ thuộc nó.

### 2.1. Nội dung archive không giống nguyên vẹn nội dung JAR

- JAR thường là một file ZIP chứa các `.class` và resources dưới dạng được nén.
- CDS archive lưu **dữ liệu lớp đã được JVM tối ưu để truy cập/nạp nhanh**, cùng metadata phụ trợ, cấu trúc ánh xạ và alignment.
- Nội dung có thể phản ánh một số dữ liệu JVM có thể archive, nhưng **không phải snapshot tự động của object nghiệp vụ**, connection pool, các session, cache ứng dụng hoặc mọi Java object.
- Một class được load trong trial run **không tự bảo đảm** nó sẽ đủ điều kiện để được lưu rồi nạp lại từ archive trong mọi cấu hình.
- Archives là artifact **phụ trợ** cho class loading; ứng dụng vẫn cần JAR/module và các resources cần thiết khi thực thi.

### 2.2. Vì sao chuyện lưu trữ lại là một chủ đề riêng?

Tạo archive đồng nghĩa xuất hiện một hay nhiều file mới trên disk/container layer. Nếu ứng dụng có nhiều version, nhiều JDK build và nhiều chế độ chạy, chi phí tăng theo số artifact **khác nhau thực sự phải giữ**, không đơn thuần theo số JVM process. Ngược lại, nếu nhiều JVM đọc **cùng một archive file** và OS cho phép chia sẻ file-backed pages, tổng lượng RAM vật lý cho phần read-only có thể giảm so với tải riêng từng bản metadata.

## 3. Chi phí lưu trữ trên đĩa: thứ cần đo đầu tiên

Tài liệu Java launcher của Oracle cho biết: **dữ liệu lớp trong CDS archive thường lớn khoảng 2–5 lần dữ liệu lớp tương ứng trong JAR hoặc JDK runtime image**, do archive dùng biểu diễn đã được tối ưu cho load, thay vì biểu diễn nén. Vì thế Oracle khuyên archive **các lớp ứng dụng thực sự dùng**, thường chỉ là một phần của thư viện lớn.

Điều này **không có nghĩa**:

- `archive_size = 2 × total_jar_size` luôn đúng;
- cứ có JAR 100 MiB thì AppCDS buộc phải chiếm 200–500 MiB;
- toàn bộ assets, ảnh, cấu hình, file tĩnh trong JAR đều bị nhân 2–5;
- archive dynamic luôn nhỏ hơn mọi archive static với mọi tập lớp và mọi JDK;
- kích thước file `.jsa` chính là RAM JVM phải cấp phát riêng;
- bất kỳ kho AppCDS nào lớn hơn JAR đều đang hoạt động sai.

### 3.1. Những thành phần làm file `.jsa` tăng kích thước

1. **Số class đủ điều kiện được archive:** class càng nhiều, dữ liệu archive có xu hướng nhiều.
2. **Độ phức tạp metadata:** cấu trúc của các lớp/constant pools/loader context có thể làm chi phí trên mỗi class khác nhau.
3. **Biểu diễn dành cho JVM:** không tối ưu theo tiêu chí nén như ZIP/JAR.
4. **Alignment và bookkeeping:** archive có metadata về regions/offsets/relocation/validation, nên với ví dụ rất nhỏ, overhead cố định có thể tương đối lớn.
5. **Base vs top:** archive dynamic thông thường chỉ chứa những gì cần bổ sung lên base archive hiện có, tránh lưu lại tất cả lớp trong base.
6. **JDK build và options:** cùng code nhưng JDK khác version/build hoặc cấu hình khác có thể tạo archive khác.
7. **Phạm vi warm-up:** nếu thử chạy mọi feature, có thể archive nhiều lớp hơn một workload thực sự cần khi startup.
8. **Ảnh hưởng framework:** container DI, proxy, reflection và classloaders tạo thêm các lớp; một phần có thể không được archive theo cách bạn kỳ vọng.

### 3.2. Đo file thật, không đoán từ tên

Trên Linux/macOS:

~~~bash
ls -lh app.jar app.jsa
du -h app.jar app.jsa
stat -c '%n %s bytes' app.jar app.jsa  # GNU stat; tùy OS
~~~

Trên Windows PowerShell:

~~~powershell
Get-Item .\app.jar, .\app.jsa |
    Select-Object Name, Length
~~~

Cột `Length` là kích thước logic theo byte của file. `du` đo số khối lưu trữ được filesystem cấp phát, có thể khác `Length` khi filesystem có sparse files, compression, deduplication hoặc đặc thù tầng lưu trữ. Nếu artifact nằm trong container image, kiểm thêm dung lượng **image layers** và phân phối trên từng node.

Một **archive vài trăm KiB cho JAR demo vài KiB** là điều có thể gặp do alignment và class metadata phụ, nhưng đây không phải tỷ lệ dự báo cho dịch vụ thực. Trong một lần kiểm thử của bài trên JDK 24, JAR ví dụ khoảng **3.145 byte**, archive động khoảng **393.216 byte**: **đây chỉ là một quan sát cho bản thử rất nhỏ**, không phải output cố định hay một quy tắc chung.

## 4. Mô hình tính chi phí lưu trữ theo số phiên bản

Hãy tách chi phí **một artifact** và chi phí **phân phối/giữ nhiều bản**.

Ký hiệu:

- `S_base`: kích thước archive CDS cơ sở đóng trong một JDK image/build.
- `S_top(i,j)`: kích thước AppCDS top archive cho ứng dụng version `i` chạy cùng JDK build `j`.
- `S_jar(i)`: dữ liệu JAR/resources của ứng dụng version `i`.
- `R`: số phiên bản rollback được giữ.
- `N`: số node/container host phải lưu artifact.
- `U`: phần dữ liệu có thể được các instance/node dùng chung, phụ thuộc storage/image-layer setup.

Một cách **lập bảng kế toán**, không phải công thức physical disk universal:

~~~text
Lưu một bản trên một host:
  app.jar + các dependency JAR + app.jsa + (JDK base nếu host cần chứa riêng)

Giữ R versions cùng JDK build:
  tổng ~= Σ(v=1..R) [JARs(v) + topArchive(v)]
           + sharedJdkImageAndBase + metadata/temporary files

N hosts không dùng storage chung:
  tổng fleet ~= Σ(host) [artifact bytes thực sự lưu trên host]

Có image-layer cache/dedup/shared volume:
  tổng thực tế phụ thuộc layer reuse, retention, inode/content sharing
~~~

**Không nhân `N_processes × app.jsa_size`** khi các process cùng dùng một file archive bất biến trên một host. Nhưng nếu mỗi pod tự tạo file trong writable layer của riêng nó hoặc nếu mỗi version có archive riêng, có thể tốn nhiều bản copy thật. Ngược lại, shared base image layer có thể giảm số byte trùng mà mỗi host phải giữ, nhưng **không bảo đảm** toàn bộ fleet chỉ giữ đúng một bản vật lý.

### 4.1. Ví dụ minh họa kế toán storage

Giả sử mỗi top archive của một version chiếm **40 MiB**, môi trường giữ **5 version** cho rollback:

~~~text
5 × 40 MiB = 200 MiB
~~~

Đây là **200 MiB logical top-archive bytes cho một bộ lưu giữ năm bản**, chưa tính JARs, base JDK, file tạm, image layers, bản sao trên node khác hoặc filesystem compression. Nếu có 20 host và mỗi host thực sự phải giữ đủ 5 bản không chia sẻ storage, logical top-archive allocation có thể đạt `20 × 200 MiB = 4.000 MiB`. Đây chỉ là **bài toán giả định để lập ngân sách**, không phải benchmark của Java.

Trong production, phải đo:

- Byte của image sau build;
- Byte thực tế trong container registry và trên từng node nếu có thể;
- Retention policy của rollout/rollback;
- Có duplicate archive vì khác JDK patch/vendor/architecture không;
- Số lần rebuild và chi phí lưu trữ file tạm trong CI.

## 5. Dung lượng archive không bằng mức tiêu thụ heap

AppCDS dựa chủ yếu vào **memory mapping** dữ liệu class, với phần read-only có thể được **chia sẻ giữa nhiều JVM** khi chúng ánh xạ cùng underlying file và có cấu hình phù hợp. Điều này khác với việc mỗi JVM tải lại metadata class từ JAR theo đường thông thường.

**Đừng đánh đồng:**

| Chỉ số | Ý nghĩa | Có thể suy bằng kích thước `.jsa` không? |
| --- | --- | --- |
| File size/`Length` | Byte logic lưu trên disk | **Có**, đo file trực tiếp |
| Allocated disk blocks | Block thực sự dùng trên filesystem | Phải dùng tool filesystem |
| VIRT/VSZ | Không gian địa chỉ ảo đã reserve/map | **Không** phải RAM vật lý |
| RSS | Resident pages được map trong tiến trình | Có thể **đếm trùng shared pages** giữa process |
| PSS (Linux) | Chia phần trang shared theo số process dùng | Hữu ích hơn RSS khi phân bổ chi phí RAM chung |
| Private Dirty / USS | Trang private của tiến trình | Liên quan đến phần không thể chia sẻ |
| File-backed page cache | Trang file đã vào memory để đọc | Có thể được nhiều process dùng; không bằng Java heap |
| Java heap | Object memory do GC quản lý | Không bằng toàn bộ native memory/metadata |
| Metaspace | Bộ nhớ metadata lớp ở runtime | Có thể giảm một phần nhờ CDS, không phải toàn bộ biến mất |

### 5.1. Vì sao RSS có thể gây hiểu lầm?

Giả sử có 4 JVM cùng map một số trang read-only của cùng file archive. Mỗi process có thể thể hiện các trang ấy trong RSS. **Cộng RSS của bốn process** có thể đếm cùng trang shared nhiều lần. PSS trên Linux phân bổ phần shared pages cho mỗi process, phản ánh tốt hơn tổng footprint.

Ví dụ khái niệm:

~~~text
Một tập trang shared dùng 12 MiB RAM vật lý
4 process cùng map các trang đó
RSS mỗi process có thể tính 12 MiB shared
Tổng shared RSS báo cáo có thể là 48 MiB
PSS mỗi process có thể nhận ~3 MiB cho phần shared
Tổng PSS phần ấy ~12 MiB
~~~

Đây là **minh họa toán học giản lược**, không phải đo một JVM thật. Trong thực tế mỗi process còn heap, stack, JIT code cache, metadata private, native libraries và các mapped regions khác. Một số trang archive có thể trở thành private do copy-on-write hoặc không được dùng; không tuyên bố toàn bộ file archive đều ở RSS hay được share 100%.

### 5.2. `mmap` không có nghĩa toàn bộ `.jsa` luôn ở RAM

Mapping một file lớn không nhất thiết đưa ngay mọi trang vào physical RAM. JVM/OS có thể fault-in các trang được chạm, cache/reclaim chúng theo điều kiện, và các option có thể ảnh hưởng cách mapping. Vì vậy:

- File 100 MiB không đồng nghĩa JVM mất ngay 100 MiB heap.
- Không thể xem `VIRT tăng 100 MiB` là bằng chứng RAM tăng đúng 100 MiB.
- Không thể thấy `RSS của mỗi JVM tăng` rồi kết luận AppCDS **không chia sẻ** trang.
- Cần đo RSS/PSS/private resident, cgroup memory, page faults, startup và workload cùng lúc.
- Docker/Kubernetes memory metrics có cách tính shared/file cache riêng; phải xác định đúng metric và áp dụng nhất quán giữa phương án.

### 5.3. Một JVM duy nhất có thể hưởng lợi về startup nhưng ít lợi ích chia sẻ RAM

Nếu chỉ có **một** JVM duy nhất và thời gian sống rất dài, lợi ích chia sẻ metadata giữa tiến trình có thể không lớn. Tuy nhiên vẫn có thể giảm một phần class loading và cải thiện startup. Nếu khởi động một lần rồi chạy nhiều tháng, chi phí build/archive/deploy phải được cân nhắc với **mức độ quan trọng của startup**; không mặc định AppCDS luôn có ROI tốt.

## 6. Trường hợp nhiều JVM: lợi ích chia sẻ có điều kiện

Đặc điểm giúp AppCDS đáng quan tâm:

- Nhiều tiến trình JVM **cùng build JDK** và cùng ứng dụng artifact phù hợp.
- Startup diễn ra thường xuyên: scale out/in, serverless-like instances, jobs, test workers, rolling deployments.
- Nhiều lớp/framework được tải ở giai đoạn khởi động.
- Các tiến trình map được **cùng underlying archive** và OS hỗ trợ chia sẻ file-backed pages.
- Dung lượng archive và chi phí tạo lại chấp nhận được.

Trường hợp lợi ích nhỏ hoặc bị vô hiệu:

- Mỗi instance có classpath khác/nhúng JAR build riêng;
- Mỗi process tạo archive riêng trong filesystem tạm;
- Container images rất khác nhau, không tái sử dụng layer;
- Archive không tương thích JDK build mới và thường bị bỏ qua;
- Ứng dụng chủ yếu bị giới hạn bởi database/network/remote service lúc khởi động;
- Nhiều lớp được sinh/tải động, không archive được theo đường cần thiết;
- Service chỉ chạy một instance lâu dài và startup không phải KPI.

**Bẫy:** “Có 100 pod” không tự đồng nghĩa “100 pod share mọi trang AppCDS”. Cơ chế chia sẻ là ở cấp **file-backed memory mapping trên hệ điều hành và backing storage tương ứng**, không tự điều phối RAM giữa các host Kubernetes khác nhau.

## 7. Giới hạn tương thích với bản dựng JDK

Một giới hạn thực tế lớn của AppCDS: archive gắn chặt với môi trường JVM đã tạo nó. Tài liệu Oracle nhấn mạnh nội dung archive **specific to each JDK build**. Thay JDK version, patch, vendor hoặc một số VM options có thể khiến archive không còn được dùng đúng.

### 7.1. Những gì phải được xác nhận khi tái sử dụng archive

1. **JDK runtime thực tế** và JDK đã dùng lúc dump có tương thích theo quy tắc của JVM đó không.
2. **Kiến trúc/ABI/VM configuration** có phù hợp không.
3. **Classpath** của chương trình có thỏa điều kiện giống hoặc prefix so với lúc tạo archive không.
4. Các **JAR** trong classpath/module path có thay đổi kể từ lúc dump không.
5. **Module-related options** có khớp điều kiện archive không.
6. **Base archive** mà dynamic/top archive phụ thuộc còn tồn tại và đúng bản không.
7. Quyền đọc file và tính toàn vẹn của archive có đảm bảo không.
8. Log JVM có cho biết archive thực sự được map và app classes được load từ archive không.

Ví dụ failure mode:

~~~text
Ngày A: build JDK 17.0.x, app.jar v1, app-v1.jsa
Ngày B: đổi app.jar sang v2 nhưng vẫn dùng app-v1.jsa
Ngày C: đổi image sang JDK khác build nhưng chưa tái tạo archive
~~~

Trong tình huống này, không được **mặc định** archive còn hợp lệ. Tùy startup flag và loại mismatch, JVM có thể bỏ archive hoặc startup thất bại. Kết quả phải xác minh bằng logs và test; không chỉ thấy file tồn tại là đủ.

### 7.2. Không dùng `-Xshare:on` như policy production

Tài liệu Oracle quy định:

- `-Xshare:auto`: cho phép dùng shared archive khi có thể (chế độ phổ biến/mặc định).
- `-Xshare:off`: tắt CDS, hữu ích làm đối chứng trong test.
- `-Xshare:on`: **cưỡng chế** dùng CDS; nếu archive không dùng được có thể làm VM lỗi/thoát khi khởi động. Oracle ghi rõ đây là cờ cho **thử nghiệm**, không khuyến nghị cho môi trường production.

**Không** cấu hình `-Xshare:on` trên tất cả môi trường production chỉ để “bắt buộc tối ưu”. Startup ổn định quan trọng hơn việc một archive được dùng trong mọi tình huống. Dùng log/metric để biết khi nào tính năng không được áp và lập cơ chế tái tạo artifact phù hợp.

## 8. Giới hạn classpath, module path và class loaders

Theo tài liệu `java` của các JDK hiện đại, AppCDS có những điều kiện cần nhớ:

- Classpath và module-path phục vụ archiving **không nên chứa non-empty directories** theo các ràng buộc được tài liệu nêu; cách demo tin cậy là đóng gói thành **JAR**.
- Với `--module-path`, tài liệu chỉ hỗ trợ **modular JARs**; exploded modules không phải định dạng chung được archive trong workflow được mô tả.
- Classpath ở runtime phải **giống hoặc có prefix** như classpath dùng lúc tạo archive (theo quy tắc được tài liệu nêu cho dạng archive này).
- JAR trong classpath/module-path **không được sửa đổi** sau khi archive được tạo, nếu muốn dùng archive theo hợp đồng.
- Một số module flags hoặc thay đổi cách nạp module có thể làm CDS bị tắt, vô hiệu một phần optimizations, hoặc khiến archive không dùng được.
- Custom class loaders có thể được AppCDS hỗ trợ **theo điều kiện và implementation**, nhưng không có bảo đảm mọi class do mọi loader tạo/tải đều được archive. Dynamic proxies, generated classes, runtime transformations và bytecode agents cần kiểm tra thực tế.

### 8.1. Tại sao `java -cp classes Main` không phải demo AppCDS tốt?

~~~bash
javac -d classes AppCdsStorageDemo.java
java -cp classes AppCdsStorageDemo
~~~

Cách này hợp lệ để **chạy Java bình thường**, nhưng không phải workflow tối ưu để đo AppCDS cho application classes: ứng dụng đang nằm trong **non-empty directory**. Để thử archive một cách có kiểm soát, hãy đóng thành JAR:

~~~bash
jar --create --file app.jar -C classes .
java -cp app.jar AppCdsStorageDemo
~~~

**Không kết luận** “Java không chạy được class từ directory khi bật CDS”: các ràng buộc liên quan đến archiving và mức độ áp dụng CDS. Một số JVM có thể bỏ qua app classes không đủ điều kiện mà vẫn sử dụng default CDS cho JDK core classes.

### 8.2. Làm sao biết lớp ứng dụng thực sự được archive?

Không đủ chỉ nhìn thấy log kiểu:

~~~text
java.lang.Object source: shared objects file
~~~

Lớp lõi của JDK có thể đến từ **default CDS archive** ngay khi app-specific archive không được dùng. Muốn chứng minh AppCDS, tìm **class do ứng dụng định nghĩa**, ví dụ:

~~~text
AppCdsStorageDemo$Report source: shared objects file (top)
~~~

Đây là ví dụ rút gọn từ log thử trên JDK hiện có; chi tiết output, nhãn `(top)` và timestamps có thể khác tùy JDK/version. Nếu không thấy application class trong archive, hãy phân tích nguyên nhân thay vì khẳng định rằng mọi lớp đều được tối ưu.

## 9. Static archive và dynamic archive: khác nhau về chi phí

### 9.1. Static workflow (di sản tính năng Java 10, vẫn được hỗ trợ)

Một static AppCDS archive có thể được dựng từ **class list** qua các thao tác được JDK hiện đại hỗ trợ:

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar AppCdsStorageDemo

java -Xshare:dump \
     -XX:SharedClassListFile=app.classlist \
     -XX:SharedArchiveFile=app-static.jsa \
     -cp app.jar
~~~

Đây là ví dụ **POSIX shell** chia dòng bằng `\`, giả định file `app.jar` đã được đóng gói đúng và đang dùng HotSpot/JDK hỗ trợ các flags. Trên PowerShell, nên viết mỗi lệnh một dòng hoặc dùng cú pháp nối dòng của PowerShell, không sao chép `\` shell sang PowerShell nguyên xi.

Chi phí:

1. Chạy workload thu class list (thường tạo file trung gian).
2. Tạo archive static và xác minh.
3. Lưu archive và dependencies đúng version.
4. Tạo lại khi ứng dụng/JDK/điều kiện liên quan thay đổi.

Một static dump có thể cho phép các optimizations khác với dynamic dump, nhưng chi phí và khả năng hoạt động cần đo trên JDK thực tế. Không mặc định static archive luôn nhỏ hơn hoặc luôn nhanh hơn dynamic archive.

### 9.2. Dynamic archive, có từ Java 13, phù hợp demo hiện đại

Một cách thường dùng trên JDK 17+:

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar AppCdsStorageDemo

java -XX:SharedArchiveFile=app.jsa \
     -cp app.jar AppCdsStorageDemo
~~~

Lần đầu **chạy ứng dụng và tạo archive khi JVM thoát**; lần sau dùng archive đó. Không cần bước xuất class list thủ công như quy trình static. **Đây không phải chức năng xuất hiện ngay ở Java 10**: JEP 350 phát triển Dynamic CDS Archives từ Java 13. Bài học dùng API hiện đại có liên quan tới nền tảng AppCDS Java 10, đúng yêu cầu tránh hướng dẫn lỗi thời.

Lợi ích storage của dynamic top:

- Có thể tái sử dụng **default base CDS archive** đã có trong JDK.
- Dynamic archive thường chỉ bổ sung các lớp không nằm sẵn trong base, tránh lưu lại toàn bộ base.
- Oracle mô tả dynamic archives thường dùng **ít disk hơn** so với static tương đương trong trường hợp phù hợp, vì không chứa lại các lớp đã có trong static base.

Giới hạn:

- Dynamic archive phụ thuộc base archive. Thay đúng JDK build/base làm top có thể không dùng được.
- Tạo archive khi process **thoát theo cách cho phép dump**; crash/kill/hard termination có thể không tạo file.
- Warm-up chỉ đi qua một phần ứng dụng sẽ có tập lớp ít hơn.
- Không được dùng một file đầu ra duy nhất cho nhiều job dump đồng thời mà không điều phối; có thể ghi đè/race/file không hợp lệ.
- Nếu container không có writable path khi cần dump, quy trình tạo archive có thể thất bại.
- Top dynamic vẫn chiếm disk; không tự giải phóng vì process sử dụng đã kết thúc.

### 9.3. Base + top: giới hạn thường gặp trong JVM hiện đại

Theo Oracle JDK 25, JVM có thể dùng tối đa **hai archive** trong mô hình CDS được mô tả:

~~~text
base static archive  +  top dynamic archive
        │                        │
  classes.jsa (JDK)          app.jsa (application)
~~~

Khi chỉ định một **dynamic archive** qua `-XX:SharedArchiveFile=app.jsa`, JVM có thể dùng thông tin lưu trong top để tìm đúng base archive.

Khi chỉ định rõ cả hai trong một option:

~~~text
-XX:SharedArchiveFile=base.jsa:app.jsa   (POSIX)
-XX:SharedArchiveFile=base.jsa;app.jsa   (Windows)
~~~

Dấu phân cách hai path **khác theo OS**. Không ghép bằng dấu `:` nguyên xi trên Windows. Ví dụ Java 17+ của bài chỉ truyền **một top archive path** để tránh khác biệt này.

Không kết luận “hai archive” đồng nghĩa có thể xếp tùy ý một chuỗi vô hạn các top archives của nhiều ứng dụng lên nhau. Với nhiều ứng dụng, thường có top archive riêng theo ứng dụng/version, cùng base phù hợp.

## 10. Tạo archive đúng workload: chọn lớp để tránh lãng phí disk

AppCDS mang lại nhiều giá trị khi ứng dụng thật sự **tải và dùng** những lớp trong archive ở thời điểm quan trọng, đặc biệt startup. Do đó, chọn representative workload quan trọng hơn cố gắng archive mọi class tồn tại trong các thư viện.

### 10.1. Phạm vi quá hẹp

Nếu trial run chỉ chạy `main` và thoát ngay, nhiều classes được load khi framework khởi tạo HTTP server, ORM, security hoặc message consumer sẽ không có trong top archive. Kết quả là archive nhỏ nhưng ít cải thiện startup thật.

### 10.2. Phạm vi quá rộng

Nếu trial run kích hoạt tất cả feature flags, job hiếm, admin endpoints hoặc integration paths không chạy ở startup bình thường, archive có thể chứa nhiều dữ liệu ít được dùng. Điều này làm tăng:

- Disk bytes của archive và image;
- Thời gian tạo/warm-up;
- Khả năng chịu tác động khi thay JAR/module dependencies;
- Chi phí phân phối và retention qua nhiều versions.

**Không nên archive “toàn bộ mọi class từ mọi JAR” chỉ vì nhìn thấy thư viện trong dependency tree.** Một library lớn có thể chứa hàng nghìn class nhưng chỉ vài chục class được dùng ở startup.

### 10.3. Workload nên phản ánh chu kỳ deploy

Một kịch bản dump có thể:

1. Khởi động app với cấu hình không gây tác động business;
2. Khởi tạo các modules và endpoints thường dùng;
3. Gửi một tập request giả lập đại diện, nếu mục tiêu là cải thiện đường nạp các lớp ấy;
4. Đảm bảo không tạo dữ liệu thật hoặc gọi external service không được phép;
5. Thoát có kiểm soát để dynamic dump ghi archive;
6. Khởi chạy lại bằng archive, kiểm log lớp và benchmark.

Chú ý: Nếu mục tiêu đo **startup** mà warm-up tải quá nhiều lớp chỉ xuất hiện rất muộn, chi phí archive có thể tăng mà lợi ích startup ít. Chọn tập lớp dựa trên **mục tiêu đo**, không dựa vào con số “archive càng lớn càng tốt”.

## 11. Chương trình Java 17+ đã được thử trên HotSpot JVM hiện có

Ví dụ sau tạo một chương trình Java nhỏ với record và hai lớp ứng dụng. Chương trình **không phụ thuộc vào AppCDS APIs**; việc có archive hay không do **Java launcher** quyết định. Điều này giúp so sánh output cùng workload.

Lưu file đúng tên **`AppCdsStorageDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public final class AppCdsStorageDemo {
    record Event(String service, int cost) {}

    static final class Report {
        static int totalCost(List<Event> events) {
            return events.stream().mapToInt(Event::cost).sum();
        }
    }

    public static void main(String[] args) {
        var events = List.of(
                new Event("auth", 2),
                new Event("catalog", 5),
                new Event("search", 3));
        System.out.println("events=" + events.size());
        System.out.println("total-cost=" + Report.totalCost(events));
        System.out.println("services=" +
                events.stream().map(Event::service)
                        .collect(Collectors.joining(",")));
        System.out.println("first-service=" + events.get(0).service());
        System.out.println("same-result-with-cds=true");
    }
}
~~~

**Chú ý về dòng cuối:** `same-result-with-cds=true` ở đây là một **nhãn minh họa cố định** để làm output dễ đối chiếu, không phải Java tự kiểm tra CDS. Bằng chứng thật về archive phải lấy từ **log CDS/class loading** và việc stdout hai lần chạy bằng nhau, không lấy từ nhãn này.

Biên dịch, đóng JAR và chạy (POSIX shell):

~~~bash
mkdir -p classes
javac --release 17 -encoding UTF-8 -d classes AppCdsStorageDemo.java
jar --create --file app.jar -C classes .

# Lần thử đối chứng không dùng CDS:
java -Xshare:off -cp app.jar AppCdsStorageDemo

# Lần chạy tạo dynamic archive; ghi file app.jsa ở lúc thoát:
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar AppCdsStorageDemo

# Lần chạy dùng lại app.jsa:
java -XX:SharedArchiveFile=app.jsa \
     -cp app.jar AppCdsStorageDemo
~~~

Trên Windows PowerShell (có JDK 17+ trong PATH):

~~~powershell
New-Item -ItemType Directory -Force -Path .\classes | Out-Null
javac --release 17 -encoding UTF-8 -d .\classes .\AppCdsStorageDemo.java
jar --create --file app.jar -C .\classes .

java -Xshare:off -cp app.jar AppCdsStorageDemo
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar AppCdsStorageDemo
java -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsStorageDemo

Get-Item .\app.jar, .\app.jsa | Select-Object Name, Length
~~~

Chạy trong **thư mục thử nghiệm riêng**, không ghi file archive vào thư mục cài đặt JDK hoặc đường dẫn chứa artifact quan trọng. Các lệnh giả định chỉ có một process dump và file `app.jsa` có thể được tạo mới; nếu chạy lại, hãy quản lý file versioned/cleanup bằng quy trình riêng thay vì ghi đè archive đang phục vụ.

### 11.1. Stdout của chương trình

**Các dòng stdout sau đã được kiểm thử khi không dùng CDS, khi tạo archive và khi chạy lại từ archive trên JDK hiện có**:

~~~text
events=3
total-cost=10
services=auth,catalog,search
first-service=auth
same-result-with-cds=true
~~~

Tính đúng đắn nghiệp vụ phải **không đổi** giữa các lần chạy. AppCDS tối ưu đường tải dữ liệu lớp chứ không thay kết quả tính toán của chương trình.

### 11.2. Kiểm tra archive có được tạo

Sau lần dump, chạy:

~~~bash
ls -lh app.jar app.jsa
~~~

hoặc PowerShell:

~~~powershell
Get-Item .\app.jar, .\app.jsa |
    Select-Object Name, Length
~~~

Trong một lần chạy thử trên JDK 24 tại môi trường kiểm chứng, file JAR khoảng **3.145 byte** và dynamic archive **393.216 byte**. **Số này không được khẳng định là output chính xác cho mọi lần biên dịch/JDK, không dùng để dự đoán chi phí của ứng dụng khác.** Đây chỉ là bằng chứng thực nghiệm rằng archive nhỏ có thể có overhead dung lượng đáng kể.

### 11.3. Chứng minh archive được nạp bằng logs

~~~bash
java -Xlog:cds=info -Xlog:class+load=info \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar AppCdsStorageDemo
~~~

Trong log đã kiểm chứng trên JDK hiện có có thông tin tương đương:

~~~text
[info][cds] Mapped dynamic region ...
[info][class,load] AppCdsStorageDemo$Report source: shared objects file (top)
~~~

Đây là **trích các dòng tiêu biểu, không phải toàn bộ log hay chuỗi timestamp nguyên văn**. Thứ tự, tags, vùng được map và cách viết nguồn class có thể khác theo phiên bản JDK. Lệnh `-Xlog:class+load=info` tạo nhiều dòng, chỉ bật trong kiểm thử/diagnostics hoặc lọc log phù hợp.

Để kiểm tra trên Linux:

~~~bash
java -Xlog:cds=info -Xlog:class+load=info \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar AppCdsStorageDemo 2>&1 |
     grep -E 'Mapped dynamic|AppCdsStorageDemo.*shared objects'
~~~

Nếu chỉ thấy core class `java.lang.Object` được nạp từ archive, chưa đủ để chứng minh **application classes** trong top archive được dùng. Hãy tìm class `AppCdsStorageDemo`, `AppCdsStorageDemo$Report` hoặc lớp ứng dụng khác.

### 11.4. Kết quả đúng nhưng không đoán performance

Ba lần in stdout giống nhau **không tự chứng minh**:

- Startup giảm bao nhiêu mili-giây.
- RSS/PSS giảm bao nhiêu MiB.
- File archive được mmap 100% và chia sẻ 100%.
- Có bao nhiêu class được lưu hoặc được tải thành công từ archive.
- Có tương thích khi đổi JDK/JAR hay không.

Các điều đó cần **log, số liệu đo, điều kiện runtime và thí nghiệm đối chứng**. Demo đã xác nhận archive được tạo và một số class ứng dụng được nạp từ top archive; lợi ích performance/footprint của dự án thật phải đo riêng.

## 12. Các loại chi phí ngoài dung lượng file

Để quyết định AppCDS có đáng dùng không, cần tính cả:

| Loại chi phí | Khi nào phát sinh | Hệ quả |
| --- | --- | --- |
| Build/dump CPU | Mỗi lần tạo archive | Tăng CI time/compute |
| I/O đọc JAR và ghi archive | Lúc warm-up và dump | Dùng băng thông/IOPS, tốn thời gian |
| Startup warm-up | Chạy workload để nạp lớp | Phải mô phỏng environment an toàn |
| Disk cho `.jsa` | Sau khi dump | Tăng artifact/image footprint |
| Disk cho classlist | Với static workflow nếu dùng file riêng | Cần quản lý/cleanup file trung gian |
| Temporary workspace | Build CI, container layer | Dễ bị bỏ quên/quota lỗi |
| Distribution/registry traffic | Mỗi rollout/image pull | Có thể tăng startup triển khai |
| Retention/rollback | Giữ nhiều release/JDK builds | Tăng chi phí dài hạn |
| Runtime memory map/page faults | Mỗi lần JVM dùng archive | Có thể cải thiện nhưng vẫn tốn memory/IO theo workload |
| Quản lý incompatibility | JDK/JAR/config thay đổi | Dùng archive cũ có thể thất bại hoặc bị bỏ qua |
| Security/integrity | Artifact storage/quyền truy cập | Archive phải được tin cậy và bảo vệ |
| Observability | Logging, A/B benchmark, metrics | Cần giám sát để phát hiện regression |

Một archive giảm 20 ms startup nhưng thêm 200 MiB vào image có thể đáng hoặc không đáng tùy hệ thống: với job tạo hàng nghìn JVM/ngày, 20 ms có thể có ý nghĩa; với service dài sống 1 JVM, tăng storage có thể không được bù. Không đặt một ngưỡng chung cho mọi dự án.

### 12.1. Chi phí tạo lại khi nâng cấp

Mỗi lần nâng JDK patch, đổi vendor/distribution, đổi app JAR hoặc các module flags quan trọng có thể cần **tạo lại và QA** archive. Nếu tự dump mỗi lần process khởi động rồi bỏ khi process kết thúc, đôi khi tổng chi phí còn cao hơn lợi ích khởi động.

Một pipeline hợp lý thường tạo archive **một lần cho bộ artifact/JDK cụ thể**, đóng gói hoặc publish nó theo version, rồi nhiều JVM instances dùng lại. Khi số phiên bản deploy lớn hoặc thường xuyên đổi config/classpath, tính chi phí invalidation và rebuild vào bài toán ROI.

## 13. AppCDS trong container và Kubernetes

### 13.1. Archive nằm ở đâu trong image?

Các lựa chọn phổ biến:

- Archive đóng trong **image layer** cạnh ứng dụng JAR, được build cùng đúng JDK distribution.
- Archive đặt trên **read-only volume/shared storage** mà nhiều process truy cập đúng underlying file.
- Archive được tạo ở **build stage** rồi copy sang runtime image, giảm số công cụ/JDK build có mặt trong runtime image khi không cần.
- Archive được tạo **tại runtime** trên writable volume; cần quota/permissions và tránh tạo trùng không cần thiết.

Không mặc định writable filesystem của container cho phép dump. Image/container tối giản thường dùng read-only root filesystem; lúc chạy với `-XX:ArchiveClassesAtExit=...` mà đường dẫn không ghi được, tạo archive có thể thất bại.

### 13.2. Dữ liệu giống nhau không chắc được chia sẻ giữa hosts

Các container trên **cùng host** có thể tận dụng file-backed pages nếu dùng đúng underlying file/backing layer và runtime cho phép. Các pod nằm **trên host khác** không tự chia sẻ RAM vật lý; mỗi host có page cache của nó. Registry deduplication và image-layer reuse có thể giúp lưu trữ/băng thông nhưng **không đồng nghĩa với cross-host RAM sharing**.

### 13.3. Lưu theo version không overwrite file đang dùng

Cấu trúc minh họa:

~~~text
/runtime/jdk-build-A/
  apps/
    service-v17/app.jar
    service-v17/app-v17.jsa
    service-v18/app.jar
    service-v18/app-v18.jsa
~~~

Đặt archive path bất biến theo **JDK build + app version + relevant configuration** giúp:

- Dễ rollback mà không nhầm archive;
- Tránh race khi nhiều process dump;
- Tránh overwrite file đã có JVM mmap;
- Dễ dọn phiên bản cũ sau khi không còn process đang dùng;
- Dễ audit artifact provenance.

Nếu image được ký/scan, archive nên được quản lý cùng provenance như JAR/JDK; không cho user không tin cậy thay file `.jsa` bằng file tùy ý.

### 13.4. CI nên làm gì?

Một pipeline minh họa:

~~~text
1. Resolve & pin đúng JDK build.
2. Build/test app JAR và dependencies.
3. Chạy representative workload để tạo archive.
4. Verify archive file được tạo, không rỗng.
5. Chạy smoke test với archive + log class load.
6. So sánh correctness, startup, PSS/CPU trên cùng điều kiện.
7. Publish JDK+JAR+archive dưới version bất biến.
8. Roll out và theo dõi startup/memory; rollback nếu regression.
9. Dọn archive không còn được sử dụng theo retention policy.
~~~

Không nên dump bằng JDK của máy CI rồi chạy một JDK khác trong runtime image mà không có bước kiểm chứng tương thích. Một số containerized workflows dùng đúng cùng base runtime image cho build/dump và deploy để tránh mismatch.

## 14. Đo startup đúng cách và tránh kết luận vội

Benchmark nên so sánh ít nhất:

1. **Baseline production:** khởi động JDK thực tế với default CDS như bình thường (không có top AppCDS).
2. **AppCDS enabled:** cùng JDK/JAR/flags/workload, chỉ thêm top archive đã tạo.
3. **CDS disabled:** `-Xshare:off` như một **đối chứng chẩn đoán**, không dùng nó làm baseline duy nhất nếu production bình thường đã dùng default CDS.

Nếu chỉ so `-Xshare:off` với AppCDS, bạn đang gộp lợi ích **default core CDS** và **application classes CDS**, dễ phóng đại riêng lợi ích AppCDS.

### 14.1. Kiểm soát biến số

- Cùng JDK build và runtime flags.
- Cùng JVM heap/GC settings, CPU quota, memory limits.
- Cùng versions of JAR/dependencies/classpath.
- Cùng khối lượng startup, endpoints cần sẵn sàng và trạng thái external services.
- Có warm-up/điều kiện file cache rõ ràng; disk cache nóng và lạnh cho kết quả khác nhau.
- Chạy **nhiều lần**, so median/percentiles, không chọn một kết quả “đẹp nhất”.
- Tách thời gian JVM startup, framework boot, service readiness, network/database initialization.
- Đo footprint khi có **1 JVM** và khi có **N JVM cùng host**, sử dụng PSS/private memory phù hợp.
- Đo kích thước artifact/registry và thời gian tạo archive.

### 14.2. Metric đề nghị

| Metric | Vì sao cần |
| --- | --- |
| Startup-to-main hoặc main-to-ready | Biết nơi startup được cải thiện |
| p50/p95 startup latency | Tránh đánh giá chỉ một lần |
| Số class app loaded from top archive | Xác minh archive thực sự làm việc |
| Archive bytes, JAR/image bytes | Tính storage overhead |
| Warm-up/dump duration | Tính chi phí build |
| RSS và PSS (khi có) | Phân biệt resident/private/shared memory |
| CPU và page faults | Xác định workload có I/O/class loading bottleneck không |
| Number of JVMs / host | Ước tính cơ hội sharing |
| Count of archive invalidations | Đo chi phí vận hành |
| Startup failures caused by archive | Kiểm tính bền vững của rollout |

### 14.3. Một công thức so sánh chi phí tương đối

Có thể lập mô hình **đơn giản hóa**:

~~~text
Giá trị lợi ích trong một kỳ
≈ (startup_time_saved × number_of_starts × cost_per_time)
  + (shared_memory_saved × duration × cost_per_memory_time)

Chi phí trong cùng kỳ
≈ archive_build_cpu_io
  + extra_storage × retention × cost_per_byte_time
  + extra_distribution_bytes × network_cost
  + operational_testing_and_rebuild_cost

Chỉ dùng nếu các đơn vị, hệ số chi phí và dữ liệu đo có căn cứ.
~~~

Công thức chỉ hỗ trợ **lập luận định lượng**, không thể tính ra chi phí tiền tệ nếu chưa có giá điện, compute, storage, billing policy và số lần startup thực tế. Thời gian startup giảm có thể đem giá trị về SLO/UX mà không biểu diễn đủ bằng tiền; kết luận nên dựa yêu cầu sản phẩm.

## 15. Bảo trì AppCDS: nâng JDK, sửa JAR và rolling deploy

### 15.1. JDK upgrade

Nếu đổi JDK từ build A sang build B:

- **Không mang AppCDS archive cũ sang và mặc định nó sẽ chạy.**
- Chạy lại workflow dump trên JDK build đích hoặc dùng cơ chế tự tạo lại có hợp đồng rõ.
- Kiểm dynamic archive gắn với base JDK tương ứng.
- Chạy smoke test, xác minh app classes load từ archive.
- Gắn version archive với JDK và app artifacts.
- Giữ bản cũ phục vụ rollback nếu còn workload dùng JDK build A.

### 15.2. Cập nhật dependency

Ngay cả khi thay một JAR chỉ một ít:

- Classpath content/checksum hoặc metadata có thể làm archive không tương thích.
- Không ghi đè trực tiếp JAR trong image đang chạy rồi hy vọng archive cũ tự cập nhật.
- Build app artifact + archive cùng transaction phát hành, giữ immutable paths.
- Kiểm thử các tính năng nạp class qua reflection/service loader.
- Nếu file JAR bị thay đổi sau archive, docs Java launcher nêu archive có thể **không được tải**.

### 15.3. Các thay đổi config có tác động khác nhau

Cấu hình business như một cờ tính năng không nhất thiết làm file classpath thay đổi, nhưng nếu nó quyết định **những class nào được load trong trial run** hoặc module graph/classloader behavior, nội dung archive/hiệu quả có thể thay. Không tạo lại chỉ vì bất kỳ biến môi trường nào thay đổi; xác định **những yếu tố thực sự ảnh hưởng archive validity và coverage**.

### 15.4. Điều phối dump / cleanup khi có nhiều instance

Không cho hàng trăm pod cùng ghi `app.jsa` vào cùng đường dẫn trong một shared volume. Cách an toàn thường là dump ở **build/preparation stage** một lần, rồi publish read-only. Nếu phải tự tạo tại runtime, dùng file riêng, khóa/điều phối phù hợp, kiểm toàn vẹn và atomic publication trước khi cho consumers dùng; không tự phát minh một protocol ghi đè live archive.

## 16. Khi nào không nên bật tùy biến AppCDS?

Một hệ thống có thể vẫn dùng **default CDS của JDK** nhưng không cần **top archive tùy biến**.

### 16.1. Không phù hợp về workload

- Startup hiếm, service chạy liên tục rất dài và không có áp lực footprint.
- Thời gian startup bị chi phối bởi network/database migration, không phải class loading.
- Ứng dụng rất nhỏ; overhead file `.jsa`/CI không bù lợi ích.
- Container image size/network pull là chi phí lớn hơn thời gian class loading được tiết kiệm.
- Các class quan trọng do loader/generator không đủ điều kiện archive trong workload hiện tại.
- Thường xuyên nâng JDK/JAR và không có pipeline tái tạo archive đáng tin.
- Không thể đảm bảo writable dump path hoặc publish artifact được bảo vệ.
- Không có khả năng đo/kiểm rằng archive thực sự được nạp.

### 16.2. Khi nào nên thử?

- Nhiều JVM cùng host, chung JDK/artifact;
- Nhiều lần khởi động/scale, nhạy startup latency;
- Framework lớn nạp nhiều classes lúc sẵn sàng phục vụ;
- Dung lượng archive nằm trong quota image/storage hợp lý;
- Có CI/CD build đúng JDK và tái dùng artifact versioned;
- Có log/metrics và rollback nếu lợi ích thấp.

Không cần bật AppCDS chỉ để “chạy Java 10 đúng chuẩn”. Đây là **tùy chọn tối ưu hiệu năng/footprint**, không phải yêu cầu để chạy ứng dụng Java.

## 17. Rủi ro bảo mật và tính toàn vẹn archive

CDS archive chứa dữ liệu nội bộ của JVM đã chuẩn bị để memory-map; **không** nên coi đó là một file text data có thể cho ai sửa tùy ý.

### 17.1. Kiểm soát nguồn gốc

- Tạo archive từ JDK/distribution, application JAR và dependencies **đã được tin cậy**.
- Dùng read-only permissions cho file được deploy.
- Không để user thường có quyền thay archive mà service JVM nạp.
- Ký/kiểm hash artifact theo pipeline supply-chain nếu phù hợp.
- Từ chối archive tải từ nguồn không rõ thay vì cố bật cưỡng chế nạp.
- Duy trì provenance JDK build và app release gắn với archive.

### 17.2. `-XX:+VerifySharedSpaces` không thay thế authentication

Java launcher có tùy chọn `-XX:+VerifySharedSpaces`, kiểm integrity của shared archive bằng **CRC32** để phát hiện hư hỏng ngoài ý muốn. Oracle lưu ý việc bảo đảm archive không bị người không có quyền sửa vẫn là trách nhiệm của người vận hành. **CRC32 không phải chữ ký mật mã** và không chống attacker cố ý thay artifact.

### 17.3. Không cache secret/session trong archive theo giả định

AppCDS không phải cơ chế đóng băng toàn bộ **runtime business state**, secret vault hoặc credentials. Thậm chí với phần dữ liệu JVM được archive, không thiết kế ứng dụng bằng cách đưa thông tin nhạy cảm vào một trial run rồi cho rằng archive là bí mật/được mã hóa. Luôn rà soát nguồn dữ liệu, quy trình sinh artifact và quyền truy cập.

## 18. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân cần điều tra | Bước kiểm tra |
| --- | --- | --- |
| `app.jsa` không xuất hiện sau dump | Process không thoát đúng, thiếu quyền ghi/quota hoặc workload/config không phù hợp | Exit code, stderr, path, disk, flags |
| Có `app.jsa` nhưng app classes không load từ top | Classpath/JAR/loader thay đổi hoặc class không đủ điều kiện | `-Xlog:cds=info` và `-Xlog:class+load=info` |
| Default CDS load nhưng AppCDS không | Base/core archive còn hoạt động, top bị bỏ qua | Tìm dấu vết của **app class** chứ không chỉ Object |
| Nâng JDK xong archive bị bỏ | Archive phụ thuộc build JDK/base khác | Rebuild với JDK runtime chính xác |
| Rolling deployment mất lợi ích AppCDS | Mỗi version/path khác, chưa có archive mới | Package top per release |
| `-Xshare:on` khiến startup fail | Bắt buộc nạp archive không thể dùng | Tránh trong production, dùng auto |
| Image size tăng nhiều | Thêm top + JAR/JDK + nhiều layers/versions | Đo `Length`, image bytes, retention |
| RSS mỗi JVM “tăng” | RSS tính mapped shared pages ở mỗi process | Đo PSS/private và tổng fleet |
| Archive có byte lớn hơn JAR | Biểu diễn tối ưu không nén, fixed overhead | So sánh đúng đơn vị, profile lợi ích |
| Không giảm startup | Workload chưa archive hot classes hoặc bottleneck nằm ngoài class loading | Log loaded classes, startup profile |
| Không giảm RAM với một JVM | Sharing multi-process hạn chế, private memory vẫn còn | Kiểm PSS/USS với nhiều JVM |
| `-cp classes` làm app class CDS không có | Non-empty directory có thể không eligible | Đóng gói classes thành JAR |
| Dynamic archive không dùng được | Mất/thay base archive hoặc điều kiện dump khác | Kiểm JDK, base, logs |
| File có thể bị chỉnh sửa bởi user khác | Supply-chain/integrity risk | Immutable artifact + filesystem permission |
| Một lần benchmark tốt, lần khác xấu | File cache/JIT/container/quota khác | Lặp phép đo, cố định biến số |

### 18.1. Thứ tự điều tra hiệu quả

1. Xác minh **cùng JDK build và JAR** đã dùng lúc dump.
2. Xác minh file `.jsa` có thật, quyền đọc ổn và không bị sửa.
3. Kiểm options JVM và module/class paths.
4. Bật `-Xlog:cds=info` cho thông tin nạp/không nạp archive.
5. Bật `-Xlog:class+load=info` khi cần chứng cứ app classes.
6. Kiểm tỉ lệ classes cần thiết đã archive được.
7. So đối chứng **default CDS vs top AppCDS**.
8. Đo startup, memory PSS/private và storage/CI overhead.
9. Nếu archive không dùng được, **không overwrite đang chạy**; tái tạo artifact versioned đúng quy trình.

## 19. Những hiểu lầm cần loại bỏ khi review thiết kế

| Phát biểu sai | Sửa lại đúng |
| --- | --- |
| “AppCDS nén JAR để giảm disk” | AppCDS tạo **thêm archive**; dữ liệu lớp trong archive thường không nhỏ hơn JAR nén |
| “Archive 100 MiB nghĩa mỗi JVM mất riêng 100 MiB heap” | Archive được memory-map; heap khác resident/shared file pages |
| “Có 20 JVM là 20 bản file `.jsa` trên disk” | Nếu cùng backing file trên host, có thể chỉ một bản |
| “Shared file nghĩa chia sẻ RAM qua mọi host” | RAM vật lý chỉ chia sẻ trong phạm vi OS/host phù hợp |
| “Cộng RSS cho biết tổng RAM vật lý của shared CDS” | RSS có thể double-count, cần PSS/private |
| “File `.jsa` tồn tại chứng minh ứng dụng dùng nó” | Phải kiểm CDS log và app class source |
| “Lớp `java.lang.Object` đến từ shared file là đủ” | Đó có thể là default JDK CDS, không phải top AppCDS |
| “Có archive thì không cần JAR” | Archive phụ trợ, JAR/resources/classpath vẫn quan trọng |
| “Archive tự cập nhật khi JAR thay đổi” | Cần rebuild/verify theo điều kiện compatibility |
| “Dùng cùng major Java là chắc reuse được archive” | Build JDK và VM/config cũng quan trọng |
| “Dynamic archive có từ Java 10” | AppCDS từ Java 10; dynamic dump có từ **Java 13** |
| “Dynamic archive luôn thay thế toàn bộ base CDS” | Top thường **phụ thuộc** base archive |
| “Cứ archive tất cả classes sẽ tối ưu nhất” | Cold classes tạo storage overhead vô ích |
| “`-Xshare:on` tốt hơn trong production” | Oracle khuyên chỉ dùng cờ này để **testing** |
| “`-Xshare:off` là baseline production công bằng” | Production thường có default CDS; so cả hai trường hợp |
| “100% archive size thành RAM resident ngay” | `mmap` không đồng nghĩa mọi trang đang resident |
| “Có thể ghi đè `.jsa` đang mmap để update” | Versioned/immutable archive path an toàn hơn |
| “CRC32 là chữ ký an ninh” | CRC32 phát hiện corruption không có chủ đích, không authenticate |
| “Archive không hoạt động nghĩa ứng dụng không chạy được” | Với `-Xshare:auto`, JVM có thể bỏ archive và tiếp tục chạy |
| “Một file nhỏ không có overhead” | Fixed metadata/alignment có thể lớn so với demo nhỏ |

## 20. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** AppCDS được giới thiệu qua JEP nào và từ JDK mấy?

**Đáp án:** **JEP 310**, từ **JDK 10**. Nó mở rộng CDS tới dữ liệu lớp của ứng dụng khi đủ điều kiện.

**Câu 2.** Dynamic dump bằng `-XX:ArchiveClassesAtExit` có từ Java 10 không?

**Đáp án:** Không; nó xuất hiện từ **JDK 13** (JEP 350), vẫn phù hợp làm workflow trên JDK hiện đại.

**Câu 3.** AppCDS có thay thế file JAR không?

**Đáp án:** Không. AppCDS là archive phụ trợ phục vụ class loading. JAR/dependencies/resources vẫn cần đúng theo chương trình và các ràng buộc archive.

**Câu 4.** Oracle nói dữ liệu lớp trong archive thường có kích thước thế nào so với dữ liệu lớp trong JAR?

**Đáp án:** Khoảng **2–5 lần lớn hơn** do định dạng tối ưu để JVM load. Không được lấy hệ số này nhân toàn bộ JAR/assets và coi là kết quả chính xác.

**Câu 5.** Một app.jar 3 KiB và app.jsa vài trăm KiB có tự chứng minh dump sai không?

**Đáp án:** Không. Fixed overhead, alignment và dữ liệu class/metadata có thể khiến archive lớn hơn nhiều cho ví dụ nhỏ; cần log kiểm archive có được sử dụng.

**Câu 6.** `RSS × số JVM` có chắc bằng tổng RAM vật lý dùng cho shared pages không?

**Đáp án:** Không. RSS có thể đếm cùng file-backed shared pages ở nhiều process; PSS/private metrics hữu ích hơn.

**Câu 7.** AppCDS archive 50 MiB có buộc mỗi JVM tăng 50 MiB heap không?

**Đáp án:** Không. Archive được memory-map, khác heap. RSS và độ resident của mapped pages phụ thuộc workload/OS.

**Câu 8.** Vì sao một archive có thể dùng bởi nhiều JVM nhưng chỉ lưu một file trên disk?

**Đáp án:** Vì các JVM có thể mở/map cùng underlying archive file. Tuy nhiên các hosts khác nhau không tự share RAM vật lý.

**Câu 9.** Sau khi nâng JDK patch, có thể dùng lại AppCDS archive cũ mà không kiểm tra không?

**Đáp án:** Không nên. Archive phụ thuộc JDK build/base và cấu hình; nên tạo lại/verify với bản runtime sẽ deploy.

**Câu 10.** Chỉ thấy `java.lang.String source: shared objects file` thì đã chứng minh AppCDS top dùng được chưa?

**Đáp án:** Chưa. Đó có thể là default CDS của JDK. Cần tìm lớp ứng dụng được load từ top archive.

**Câu 11.** Vì sao nên đóng ứng dụng thành JAR khi thử AppCDS?

**Đáp án:** Vì các ràng buộc CDS/AppCDS ở classpath/module-path ưu tiên JAR và không archive classes từ non-empty directories theo workflow document hiện đại.

**Câu 12.** Nếu chỉ dump một workload không load class quan trọng ở startup, hiệu quả sẽ thế nào?

**Đáp án:** Archive không chứa nhiều classes mục tiêu, nên startup benefit có thể thấp; phải dùng representative workload.

**Câu 13.** Vì sao archiving tất cả thư viện là ý tưởng kém?

**Đáp án:** Nhiều class không được dùng; tăng disk, dump time và artifact churn mà ít ích cho startup.

**Câu 14.** `-Xshare:on` có nên dùng trên production để bảo đảm performance không?

**Đáp án:** Không. Oracle nêu `-Xshare:on` là cho testing vì archive không hợp lệ có thể làm JVM thoát khi start; dùng auto và giám sát phù hợp.

**Câu 15.** Baseline nào công bằng khi đánh giá lợi ích **riêng AppCDS**?

**Đáp án:** So production runtime dùng default CDS **không có top AppCDS** với runtime giống hệt **có top AppCDS**; `-Xshare:off` là đối chứng bổ sung.

**Câu 16.** Dynamic top archive có thể độc lập với default base archive không?

**Đáp án:** Thông thường không. Top có thể chứa thông tin/tham chiếu đến base; cần đúng base/JDK build phù hợp.

**Câu 17.** JDK thay, JAR thay, rollout phải làm gì với archive?

**Đáp án:** Tạo/kiểm archive mới theo version/điều kiện mới, smoke test, publish artifact bất biến và dọn archive cũ sau khi không còn được dùng.

**Câu 18.** Dung lượng image và chi phí network có liên quan AppCDS không?

**Đáp án:** Có. Thêm `.jsa` vào image có thể làm image/pull lớn hơn, dù startup JVM sau khi pull có thể nhanh hơn.

**Câu 19.** `-XX:+VerifySharedSpaces` có thay thế việc ký artifact không?

**Đáp án:** Không. CRC32 chỉ giúp phát hiện hư hỏng ngẫu nhiên, không phải chữ ký mật mã hoặc kiểm quyền ghi.

**Câu 20.** Tại sao dump trên JDK ở laptop rồi deploy archive sang một JDK image khác có thể thất bại?

**Đáp án:** Vì archive specific to JDK build và các VM/classpath điều kiện liên quan; phải dùng môi trường phù hợp runtime thật.

**Câu 21.** Có thể nhìn kích thước `app.jsa` rồi kết luận tiết kiệm RAM cùng số byte không?

**Đáp án:** Không. Đó là disk bytes; memory sharing và resident footprint phải đo riêng theo workload và số JVM.

**Câu 22.** Khi nào việc không dùng top AppCDS là hợp lý?

**Đáp án:** Khi startup không quan trọng, lợi ích đo được rất nhỏ, artifact/storage/CI cost lớn, archive thường invalid, hoặc có nhiều constraints classloader/JDK khó vận hành hơn lợi ích.

## 21. Checklist trước khi bật hoặc phát hành kho AppCDS

1. **KPI cần cải thiện là gì?** Startup-to-ready, PSS, đồng thời nhiều JVM hay chi phí compute?
2. **Đã phân biệt default CDS và custom AppCDS chưa?** Đối chứng có giữ default CDS không?
3. **JDK build dùng dump có khớp runtime image thật không?**
4. **Classpath và JAR version đã cố định chưa?** Có non-empty directories/exploded modules cần xử lý?
5. **Có dynamic top phụ thuộc base archive không?** Base có được đóng cùng image?
6. **Các module/VM flags tại runtime có khớp dump time đủ để dùng archive không?**
7. **Warm-up đã tải lớp thật sự quan trọng chưa?** Có làm phát sinh side effects không?
8. **Sau dump có file không rỗng và exit code thành công không?**
9. **Log đã thấy application classes từ top shared archive chưa?**
10. **Đã đo bytes của JAR, `.jsa` và tổng image artifact chưa?**
11. **Có đo allocated disk blocks/registry transfer nếu chúng quan trọng không?**
12. **Đã tính archive per app version, JDK build và rollback retention chưa?**
13. **Có tránh dump lại trong mỗi pod/process không?**
14. **Có quy trình immutable naming, artifact integrity và access control không?**
15. **Đã đo startup nhiều lần với cùng file cache/CPU/memory quota chưa?**
16. **Đã so PSS/private memory khi chạy nhiều JVM trên cùng host chưa?**
17. **Có kiểm logs khi archive bị bỏ qua sau rollout/JDK upgrade không?**
18. **Có tránh `-Xshare:on` trong production không?**
19. **Có chính sách cleanup top archives cũ khi không còn process dùng không?**
20. **Có bằng chứng tổng lợi ích lớn hơn chi phí disk, CI, image pull và vận hành không?**

## 22. Tài liệu chính thức và nguồn kiểm chứng hiện hành

1. [OpenJDK JEP 310 – Application Class-Data Sharing](https://openjdk.org/jeps/310): mốc JDK 10 và mục tiêu mở rộng class-data sharing tới application classes.
2. [Oracle Java SE 17 – java launcher, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): kích thước archived class data so với JAR, static/dynamic archives, các flags và classpath constraints.
3. [Oracle Java SE 25 – java launcher, AppCDS](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): mô hình base/top, tạo static/dynamic archive, `jcmd VM.cds`, giới hạn archive, tương thích JDK build và các tùy chọn kiểm tra.
4. [Oracle Java SE 25 – Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): memory-mapped class metadata, chia sẻ giữa JVM, `-Xshare:off/auto/on` và khuyến nghị không bật `on` trong production.
5. [OpenJDK JEP 350 – Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic CDS archive từ JDK 13, làm rõ nó không phải tính năng đã có ngay ở Java 10.
6. [OpenJDK JEP 341 – Default CDS Archives](https://openjdk.org/jeps/341): default archive có từ JDK 12, ảnh hưởng baseline khi so hiệu năng.
7. [Oracle Java SE 17 – `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): công cụ diagnostic cho JVM; lệnh VM.cds tùy phiên bản/điều kiện.
8. [Oracle Java SE 17 – Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): cú pháp `-Xlog:cds=info` và `-Xlog:class+load=info`.
9. [Red Hat – Speed up Java application startup time with AppCDS](https://developers.redhat.com/articles/2024/01/23/speed-java-application-startup-time-appcds): ví dụ vận hành thực tế và nhu cầu giữ JDK dump/runtime khớp nhau.
10. [Linux procfs – `/proc/PID/smaps`](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): cách xem RSS/PSS/private/shared mappings trên Linux để đánh giá tác động memory.

**Kết luận:** AppCDS có thể giảm thời gian class loading và tiết kiệm **một phần bộ nhớ metadata chung giữa nhiều JVM** bằng việc tái sử dụng file archive memory-mapped. Nhưng đổi lại là **file `.jsa` trên disk**, thời gian warm-up/dump, chi phí đóng gói/phân phối và trách nhiệm tương thích theo **JDK build, JAR, classpath, module flags, base archive**. Đừng đánh giá bằng một số đo duy nhất. Hãy **chọn classes thực sự quan trọng, đóng gói JAR, tạo archive phù hợp JDK runtime, kiểm log app classes, đo startup cùng PSS/storage** rồi quyết định theo ROI. Bài toán là tối ưu có điều kiện, **không phải cam kết mọi ứng dụng có AppCDS sẽ nhỏ hơn và nhanh hơn**.
