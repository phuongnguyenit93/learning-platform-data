# Nhận diện nguyên nhân cache không phù hợp, không được dùng hoặc bị từ chối

## 1. Mục tiêu và phạm vi

Bài thuộc chương **AOT cache** của module **JAVA_VERSION_JAVA25**. Java 25 tiếp tục hướng cải thiện thời gian khởi động và warm-up của ứng dụng Java thông qua Ahead-of-Time (AOT) cache. Hai cải tiến quan trọng của JDK 25 là:

- **JEP 514 — Ahead-of-Time Command-Line Ergonomics:** đơn giản hóa việc tạo cache bằng tùy chọn `-XX:AOTCacheOutput`.
- **JEP 515 — Ahead-of-Time Method Profiling:** lưu thêm method-execution profiles từ training run vào AOT cache để JIT có dữ liệu tối ưu ngay từ đầu lần chạy tiếp theo.

AOT cache được giới thiệu ở JDK 24 bởi JEP 483. Trong JDK 25, cache hỗ trợ cả thông tin lớp đã nạp/liên kết và method profiles. Khi được sử dụng đúng, ứng dụng có thể giảm công việc class loading/linking và rút ngắn warm-up. Tuy nhiên, cache được tạo cho **một ứng dụng, một JDK và một nền tảng cụ thể**. Thay đổi artifact, dependency, JDK hoặc môi trường triển khai có thể khiến cache không còn phù hợp.

Bài này tập trung vào câu hỏi vận hành: **vì sao file `.aot` tồn tại nhưng JVM không dùng, dùng không đầy đủ, hoặc từ chối nạp?** Ta sẽ phân biệt:

1. Cache không được yêu cầu hoặc bị tắt.
2. JVM không tìm thấy/không đọc được file cache.
3. Cache không tương thích với ứng dụng, JDK, OS/CPU hoặc JVM options.
4. Cache được nạp nhưng không bao phủ các lớp/đường chạy cần thiết.
5. Cache được sử dụng nhưng không cải thiện thời gian khởi động như mong đợi.
6. Training run không đại diện cho workload production.
7. Build/deploy Spring Boot dùng sai dạng JAR hoặc classpath.

**Giới hạn phiên bản:** nội dung lệnh và hành vi dưới đây nhắm tới **HotSpot JDK 25**. Một số ràng buộc có thể được cải thiện ở JDK mới hơn. Không lấy lệnh của JDK 24 hoặc một JDK mới hơn rồi mặc định áp dụng nguyên xi cho Java 25.

Sau bài này, bạn có thể:

- Tạo cache theo quy trình một bước hoặc ba pha.
- Phân biệt `AOTMode=auto`, `off`, `record`, `create` và `on` trong JDK 25.
- Dùng log AOT để phát hiện cache bị bỏ qua hoặc bị từ chối.
- Kiểm tra tính nhất quán của JDK, ứng dụng, classpath/module path, JAR timestamps và JVM flags.
- Thiết kế training run có workload đại diện, bao gồm đường chạy nóng cho JEP 515.
- Phân biệt AOT cache của HotSpot với Spring AOT processing, CDS archive và GraalVM Native Image.
- Thiết lập quy trình tạo, kiểm thử, đóng gói và thay cache theo từng build.

## 2. AOT cache làm gì và không làm gì?

### 2.1. Cache lưu thông tin gì trong JDK 25?

AOT cache là một container chứa những artifact JVM thu thập hoặc chuẩn bị trước khi ứng dụng chạy. Trong JDK 25, các tối ưu hóa liên quan gồm:

- Thông tin lớp đã được đọc, phân tích, nạp và liên kết (*class loading and linking*).
- Các heap objects có thể được chia sẻ theo cơ chế AOT cache.
- Method-execution profiles được ghi trong training run theo JEP 515, giúp JIT có thông tin về hành vi thực thi trước khi production run bắt đầu.

Method profiles không phải native image cố định của toàn bộ ứng dụng. JIT vẫn có thể tiếp tục thu thập dữ liệu và tối ưu khi production workload thay đổi. Cache giúp chuyển một phần công việc sớm hơn, không đóng băng hoàn toàn quyết định tối ưu của JVM.

### 2.2. Những gì AOT cache không phải

| Khái niệm | Vai trò | Quan hệ với AOT cache |
| --- | --- | --- |
| HotSpot AOT cache (`.aot`) | Cache artifact cho lần chạy JVM tiếp theo | Chủ đề chính của bài |
| CDS archive (`.jsa`) | Cơ chế chia sẻ class metadata/data có từ các JDK trước | Tiền thân/cơ chế liên quan; với Java 25 nên ưu tiên AOT cache khi môi trường hỗ trợ |
| Spring AOT processing | Phân tích application context và sinh code/hint cho ứng dụng Spring | Có thể kết hợp với JVM AOT cache nhưng là bước khác |
| GraalVM Native Image | Biên dịch ứng dụng thành executable native | Không phải file `.aot` của HotSpot |
| JIT compilation | Biên dịch động khi ứng dụng chạy | Có thể tận dụng method profiles đã lưu trong AOT cache |

Nếu một ứng dụng đã chạy Spring AOT processing mà chưa tạo JVM AOT cache, điều đó **không có nghĩa** nó đang dùng file `.aot`. Ngược lại, JVM AOT cache không tự sinh các lớp cấu hình Spring AOT.

### 2.3. Vì sao cache có tính đặc thù môi trường?

Oracle JDK 25 xác định AOT cache gắn với:

1. Ứng dụng cụ thể, được nhận diện qua `-classpath`, `-jar` hoặc `--module-path`.
2. Bản phát hành JDK cụ thể.
3. Hệ điều hành và kiến trúc CPU cụ thể.

Vì vậy, cache của `orders-service` không phải cache dùng chung cho `billing-service`. Cache tạo trên Linux x86-64 không phải artifact có thể mặc định mang sang Windows hoặc Linux ARM64. Cache tạo từ build cũ không nên dùng lại sau khi thay code hoặc dependency.

Một quy tắc vận hành an toàn là **gắn cache với chính xác build artifact và target platform**; khi build, JDK hoặc nền tảng thay đổi, tạo lại cache.

## 3. Hiểu đúng quy trình tạo cache trong JDK 25

AOT cache có ba giai đoạn logic:

~~~mermaid
flowchart LR
    T["Training run: chạy workload đại diện"] --> C["AOT configuration: quan sát và thống kê"]
    C --> A["Assembly: tạo file .aot"]
    A --> P["Production run: nạp cache"]
~~~

JEP 514 cho phép gộp training và assembly thành một lệnh phổ biến. Quy trình ba pha vẫn hữu ích khi muốn kiểm soát tài nguyên hoặc tách môi trường.

### 3.1. Quy trình một bước: `AOTCacheOutput`

Với một ứng dụng classpath đơn giản:

~~~bash
# Training + assembly trong một lệnh
java -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.App
~~~

JVM chạy ứng dụng để ghi nhận thông tin cần thiết. Khi tiến trình kết thúc, JVM khởi chạy một JVM thứ hai để assembly và ghi cache `app.aot`.

Lần chạy tiếp theo:

~~~bash
java -XX:AOTCache=app.aot \
     -cp app.jar com.example.App
~~~

Trong JDK 25, chế độ mặc định `AOTMode=auto` tự chuyển sang training khi có `AOTCacheOutput`; nếu không có output path, JVM thử nạp cache có thể sử dụng và nếu không có cache phù hợp thì chạy không dùng AOT cache.

**Chú ý tài nguyên:** JVM assembly là tiến trình riêng. Nếu training run dùng `-Xmx2g`, JVM assembly có thể cần heap cùng kích thước. Môi trường tạo cache một bước có thể cần gần gấp đôi heap được cấu hình, ngoài phần memory native và overhead của hệ điều hành/container. Nếu container bị giới hạn memory, training có thể hoàn thành nhưng bước assembly thất bại do thiếu RAM.

Có thể truyền JVM options bổ sung cho tiến trình assembly qua `JDK_AOT_VM_OPTIONS`. Dùng cách này có chủ đích; không truyền các tùy chọn làm thay đổi môi trường theo cách khiến assembly không còn tương thích với production.

### 3.2. Quy trình ba pha: kiểm soát training và assembly riêng

Khi tài nguyên hạn chế hoặc muốn chạy training ở môi trường gần production rồi assembly ở máy nhiều RAM/CPU hơn:

**Pha 1 — Training:**

~~~bash
java -XX:AOTMode=record \
     -XX:AOTConfiguration=app.aotconfig \
     -cp app.jar com.example.App
~~~

Chạy workload đại diện cho ứng dụng. JVM ghi dữ liệu vào `app.aotconfig`.

**Pha 2 — Assembly:**

~~~bash
java -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconfig \
     -XX:AOTCache=app.aot \
     -cp app.jar
~~~

JVM đọc cấu hình training và tạo `app.aot`. Ở pha này, application main không được chạy như một production invocation.

**Pha 3 — Production:**

~~~bash
java -XX:AOTCache=app.aot \
     -cp app.jar com.example.App
~~~

Ba pha giúp tách chi phí training và assembly. Tuy nhiên, classpath, JDK và nền tảng phải được quản lý nhất quán; không coi file `.aotconfig` là một bản cache có thể tùy ý chuyển sang ứng dụng khác.

### 3.3. Những tùy chọn AOT chính trong JDK 25

| Tùy chọn | Vai trò | Lưu ý |
| --- | --- | --- |
| `-XX:AOTCacheOutput=app.aot` | Ghi cache; ở chế độ mặc định sẽ chạy training rồi assembly | Không dùng cùng `-XX:AOTCache` |
| `-XX:AOTCache=app.aot` | Chỉ định cache để nạp ở production; trong `AOTMode=create` là đích ghi cache | Đường dẫn phải truy cập được |
| `-XX:AOTConfiguration=app.aotconfig` | Chỉ định file cấu hình training/assembly | `create` cần file này |
| `-XX:AOTMode=auto` | Chế độ mặc định, tự quyết định record/on/off | Khuyến nghị cho production có khả năng fallback |
| `-XX:AOTMode=off` | Không dùng AOT cache | Các tùy chọn AOT khác bị bỏ qua |
| `-XX:AOTMode=record` | Chạy training và ghi dữ liệu | Cần cấu hình output hoặc configuration |
| `-XX:AOTMode=create` | Assembly từ file configuration | Không thực thi application main |
| `-XX:AOTMode=on` | Bắt buộc nạp cache; lỗi thì dừng | Dùng để chẩn đoán/fail-fast |

`-XX:AOTCache` và `-XX:AOTCacheOutput` không được dùng đồng thời trong cùng lệnh.

**Đừng dùng `AOTMode=required` trong ví dụ JDK 25.** Các giá trị hợp lệ được tài liệu Java 25 liệt kê là `auto`, `off`, `record`, `create` và `on`. Không lấy tên mode từ tài liệu của một JDK khác rồi áp vào JDK 25.

## 4. Phân biệt cache bị từ chối với cache không được sử dụng

Một ứng dụng vẫn khởi động thành công không chứng minh AOT cache đã được nạp.

### 4.1. Chế độ `auto`: có thể fallback âm thầm

Trong JDK 25:

- Nếu chỉ định `AOTCacheOutput`, `auto` chuyển sang `record` để tạo cache.
- Nếu không chỉ định output và cache có thể nạp được, `auto` chuyển sang `on`.
- Nếu không có cache có thể nạp, `auto` chuyển sang `off`.
- Nếu cache bị từ chối vì không tương thích hoặc không thể truy cập, JVM vẫn tiếp tục chạy ứng dụng mà không dùng cache.

Đây là hành vi phù hợp cho production khi muốn ứng dụng tiếp tục phục vụ ngay cả khi tối ưu hóa không hoạt động. Nhưng nó cũng khiến lỗi cache khó phát hiện nếu chỉ kiểm tra HTTP health hoặc exit code.

### 4.2. Chế độ `on`: fail-fast để chẩn đoán

Khi kiểm thử cache, dùng:

~~~bash
java -XX:AOTCache=app.aot \
     -XX:AOTMode=on \
     -Xlog:aot \
     -cp app.jar com.example.App
~~~

Nếu cache không tồn tại hoặc môi trường không đáp ứng điều kiện, JVM báo lỗi và dừng thay vì âm thầm chạy không cache. Đây là chế độ hữu ích trong CI hoặc bài kiểm tra tính tương thích.

Không nên mặc định dùng `AOTMode=on` cho production nếu launcher, agent hoặc nền tảng triển khai có thể thêm JVM options ngoài quyền kiểm soát của ứng dụng. Một option giám sát được thêm vào sau này có thể khiến JVM không khởi động được.

### 4.3. Bảng phân loại trạng thái

| Hiện tượng | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| Ứng dụng chạy, không có log cache | Có thể AOT đang off hoặc không được yêu cầu | Kiểm tra command line và `AOTMode` |
| `auto` chạy nhưng cache bị bỏ qua | Fallback sang chạy bình thường | Thêm `-Xlog:aot` |
| `on` báo lỗi khi khởi động | Cache không nạp được hoặc không tương thích | Đọc nguyên văn log lỗi, kiểm tra file và môi trường |
| Cache nạp nhưng nhiều class vẫn load từ JAR | Cache bao phủ không đầy đủ hoặc classpath lệch | Dùng `-Xlog:class+load` và kiểm tra training coverage |
| Cache được dùng nhưng warm-up vẫn dài | Method profiles không phù hợp workload hoặc runtime vẫn cần tối ưu thêm | Xem training run và JEP 515 |
| Cache tạo không có file đầu ra | Training/assembly chưa hoàn tất, sai đường dẫn hoặc bị thiếu tài nguyên | Kiểm tra exit status, quyền ghi và log tiến trình assembly |

## 5. Ma trận nguyên nhân cache không phù hợp

### 5.1. Ứng dụng hoặc dependency đã thay đổi

AOT cache gắn với ứng dụng cụ thể. Những thay đổi sau là lý do để tạo lại cache:

- Build lại JAR từ source mới.
- Thay đổi class hoặc resource ảnh hưởng tới cấu trúc ứng dụng.
- Thêm, xóa hoặc nâng version dependency.
- Thay đổi cách đóng gói executable JAR hoặc module path.
- Thay đổi classpath order.
- Thay đổi JAR timestamp khi quy trình build/copy không bảo toàn metadata.

Không tái sử dụng cache từ build trước chỉ vì tên file vẫn là `app.aot`. Tên file không xác định danh tính ứng dụng.

**Cách xử lý:** trong pipeline build, tạo cache sau khi artifact cuối cùng đã được đóng gói; gắn cache với build ID/digest và target platform. Khi artifact hoặc dependency đổi, tạo lại cache cùng build.

### 5.2. JDK hoặc vendor/build không khớp

Cache phải được tạo và sử dụng với JDK tương thích. Không mặc định cùng major version `25` là đủ nếu training và production dùng các JDK distribution/build khác nhau.

Kiểm tra:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Trong pipeline, ghi lại:

- JDK vendor.
- JDK version/build.
- Đường dẫn binary `java`.
- JVM options.
- Container base image.

Một lỗi thường gặp là tạo cache bằng JDK trong build container nhưng production image lại lấy `java` từ một distribution khác hoặc patch level khác. Hãy giữ cùng JDK build cho cache creation và deployment theo yêu cầu tương thích của môi trường.

### 5.3. OS hoặc CPU architecture khác

AOT cache không phải artifact portable giữa mọi nền tảng. Ví dụ:

| Training | Production | Quyết định |
| --- | --- | --- |
| Linux x86-64 | Linux x86-64 cùng JDK | Có thể dùng nếu các điều kiện khác khớp |
| Linux x86-64 | Linux AArch64 | Tạo cache riêng cho AArch64 |
| Linux | Windows | Tạo cache riêng |
| Máy developer macOS | Container Linux | Không tái sử dụng cache macOS |
| JDK 25 | JDK 26 | Tạo cache mới cho JDK đích |

Trong CI đa kiến trúc, tạo cache riêng cho mỗi target, ví dụ `app-linux-amd64.aot` và `app-linux-arm64.aot`. Không đẩy một file cache chung cho mọi node.

### 5.4. Classpath, module path và thứ tự JAR

Đây là nhóm nguyên nhân rất phổ biến, nhất là với ứng dụng Spring Boot.

Với classpath:

- Dùng danh sách JAR ổn định.
- Tránh directory entry, wildcard `*` và nested JAR trong quy trình cache.
- Giữ nguyên thứ tự JAR giữa training và production.
- Bảo toàn timestamp của các JAR.
- Production nên dùng cùng classpath (hoặc superset theo hướng dẫn Spring Framework); các entry bổ sung ở cuối không được xem là đã cache.

Với module path, kiểm tra danh sách module và cách ứng dụng được khởi chạy có giống lúc tạo cache hay không.

**Ví dụ dễ sai:**

~~~bash
# Training
java -XX:AOTCacheOutput=app.aot \
     -cp "lib/*:app.jar" com.example.App

# Production
java -XX:AOTCache=app.aot \
     -cp "app.jar:lib/*" com.example.App
~~~

Thứ tự và cách mở rộng wildcard có thể khác giữa các lần chạy. Dùng một classpath tường minh, ổn định trong script build và deploy.

Trên Windows, classpath phân tách bằng dấu chấm phẩy (`;`); Linux/macOS dùng dấu hai chấm (`:`). Không copy nguyên chuỗi classpath từ hệ điều hành này sang hệ điều hành khác.

### 5.5. JVM options hoặc JVMTI agents không tương thích

AOT cache là tối ưu hóa; nó không cam kết tương thích với mọi JVM option hoặc mọi agent có thể sửa class khi runtime.

Một nguyên nhân được tài liệu Oracle nêu là các JVMTI options/agents có thể thay đổi class loading. Ví dụ agent sử dụng các API `AddToBootstrapClassLoaderSearch` hoặc `AddToSystemClassLoaderSearch` có thể làm điều kiện cache không còn phù hợp.

Kiểm tra:

- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và options được truyền bởi container.
- Các `-javaagent` hoặc native JVMTI agent.
- Các option patch/transform bytecode.
- Những khác biệt giữa JVM options của training và production.
- `AOTClassLinking` và các giới hạn của nó nếu được sử dụng.

Đừng gỡ agent giám sát khỏi production chỉ để làm cache hoạt động mà chưa đánh giá yêu cầu bảo mật/observability. Trước tiên thử nạp cache với cùng cấu hình và tách từng option trong môi trường kiểm thử để tìm chính xác xung đột.

### 5.6. Garbage collector và giới hạn riêng của JDK 25

Trong JDK 25, AOT cache chưa hỗ trợ ZGC. Nếu production dùng ZGC, đừng giả định cache sẽ được sử dụng như khi chạy với G1/Parallel GC.

Đây là giới hạn theo phiên bản: JDK 26 bổ sung JEP 516, cho phép AOT object caching với mọi GC. Vì vậy, khi vận hành JDK 25 hãy kiểm tra collector; khi nâng lên JDK 26 hoặc mới hơn, hãy đọc lại tài liệu của release đích thay vì tiếp tục áp dụng giới hạn cũ.

Không đổi collector production chỉ để ép cache hoạt động nếu chưa benchmark và đánh giá pause time/throughput. Cần so sánh cấu hình GC phù hợp workload với lợi ích AOT thực tế.

### 5.7. File không tồn tại, sai đường dẫn hoặc quyền truy cập

Các tình huống đơn giản nhưng thường bị nhầm với lỗi tương thích:

- Đường dẫn tương đối được resolve từ working directory khác.
- Cache chưa được tạo do training/assembly chưa kết thúc.
- Tiến trình assembly không có quyền ghi vào thư mục.
- Production container không chứa file `.aot`.
- File được mount read-only hoặc user chạy ứng dụng không có quyền đọc.
- Pipeline đã đổi tên hoặc xóa artifact cache.
- Cache được tạo ở thư mục tạm nhưng deploy lại tham chiếu đường dẫn khác.

Ưu tiên đường dẫn tuyệt đối trong production:

~~~bash
java -XX:AOTCache=/opt/app/cache/app.aot \
     -XX:AOTMode=auto \
     -jar /opt/app/app.jar
~~~

Kiểm tra file trước khi chạy bằng công cụ hệ điều hành (`ls -l`, `stat` trên Linux/macOS hoặc `Get-Item` trên PowerShell), đồng thời xác minh user của JVM có quyền đọc file.

## 6. Training run không đại diện cho production

### 6.1. Vì sao training coverage quan trọng?

JEP 515 cho phép cache giữ method-execution profiles của training run. Nếu training chỉ khởi động ứng dụng rồi thoát, các đường xử lý sau khởi động có thể không được đại diện.

Ví dụ một dịch vụ Spring Boot có:

- API đăng nhập.
- API đọc dữ liệu.
- API tạo đơn.
- API tính giá.
- API thanh toán.
- Background worker xử lý event.

Nếu training chỉ gọi health check, các method nóng trong luồng tạo đơn/thanh toán không được quan sát đầy đủ. Cache có thể vẫn nạp được nhưng lợi ích warm-up không như mong đợi.

### 6.2. Thiết kế workload đại diện

Một training plan nên có:

1. Startup và initialization path thực tế.
2. Một số request phổ biến.
3. Những nhánh nghiệp vụ thường xuyên.
4. Các thành phần framework/serializer/client thực sự dùng.
5. Tác vụ nền quan trọng nếu chúng chạy trong cùng process.
6. Dữ liệu đầu vào có tính đại diện nhưng không chứa bí mật production.
7. Thời gian chạy đủ để thực thi các path cần profile.

Không cần chạy toàn bộ stress test, regression suite hoặc test framework nặng nếu chúng chỉ nạp những class không bao giờ dùng trong production. Cache quá lớn hoặc chứa nhiều class không liên quan có thể làm tăng footprint và giảm hiệu quả.

### 6.3. Khi nào không nên chỉ dùng `spring.context.exit=onRefresh`?

Spring Framework cung cấp chế độ thoát sau khi `ApplicationContext` refresh:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -Dspring.context.exit=onRefresh \
     -jar application.jar
~~~

Cách này hữu ích để ghi nhận class loading/initialization trong startup. Nhưng với Java 25, AOT cache còn chứa method profiles. Nếu mục tiêu là giảm warm-up sau khi phục vụ request, training chỉ thoát sau refresh sẽ không phản ánh đủ phần thực thi nghiệp vụ.

Hãy chọn một trong hai mục tiêu rõ ràng:

- **Startup-focused cache:** training tập trung vào khởi tạo context và các singleton eager.
- **Startup + warm-up cache:** training tiếp tục chạy một workload production-like sau khi context sẵn sàng.

Không so sánh hai cache này bằng một con số duy nhất mà không ghi lại khác biệt workload.

## 7. Quy trình chẩn đoán có thứ tự

~~~mermaid
flowchart TD
    A["Ứng dụng chạy nhưng cache không có tác dụng"] --> B["Xác minh file .aot tồn tại và có quyền đọc"]
    B --> C{"AOTMode=auto?"}
    C -->|Có| D["Bật -Xlog:aot để thấy fallback hoặc cache load"]
    C -->|Không| E["Dùng AOTMode=on để fail-fast"]
    D --> F["Kiểm tra JDK / OS / CPU / application identity"]
    E --> F
    F --> G["Kiểm tra classpath, thứ tự JAR, timestamps, module path"]
    G --> H["Kiểm tra JVM options, JVMTI agents, GC"]
    H --> I["Kiểm tra training workload và class coverage"]
    I --> J["Tạo lại cache từ đúng build và target platform"]
    J --> K["Đo lại startup, warm-up và class loading"]
~~~

### Bước 1 — Xác nhận cache có thật

Kiểm tra:

- File `.aot` tồn tại.
- Kích thước file lớn hơn 0.
- Owner/ACL cho phép JVM đọc.
- Đường dẫn trong command line trỏ đúng file.
- File được tạo sau khi training và assembly kết thúc thành công.

### Bước 2 — Phân biệt auto fallback và fail-fast

Production thường dùng:

~~~bash
java -XX:AOTCache=/opt/app/cache/app.aot \
     -XX:AOTMode=auto \
     -Xlog:aot \
     -jar /opt/app/app.jar
~~~

Trong môi trường kiểm thử:

~~~bash
java -XX:AOTCache=/opt/app/cache/app.aot \
     -XX:AOTMode=on \
     -Xlog:aot \
     -jar /opt/app/app.jar
~~~

Nếu `auto` chạy bình thường nhưng `on` thất bại, hãy xử lý đây là vấn đề cache compatibility, không phải lỗi nghiệp vụ của application.

### Bước 3 — So sánh runtime fingerprint

Ghi lại từ cả training và production:

| Thuộc tính | Cần khớp? | Cách xác minh |
| --- | --- | --- |
| JDK release/build và vendor | Có, dùng cùng JDK build là lựa chọn an toàn | `java -version` |
| OS và CPU architecture | Có | `uname -a`, `uname -m`; Windows xem System Information |
| Artifact ứng dụng | Có | Build ID/SHA-256 của JAR |
| Classpath/module path | Phải tương thích và giữ thứ tự | Ghi command line đầy đủ |
| JAR timestamps | Giữ nguyên | `stat`/`Get-Item` |
| JVM options | Phải tương thích | `jcmd VM.command_line`, cấu hình container |
| JVMTI agents | Tránh các agent làm thay đổi class loading không tương thích | Kiểm tra `-javaagent`, `-agentlib` |
| Garbage collector | JDK 25 không dùng AOT cache với ZGC | Kiểm tra GC flags |

### Bước 4 — Bật log AOT và class loading

Để tìm lý do cache không nạp:

~~~bash
java -XX:AOTCache=app.aot \
     -XX:AOTMode=auto \
     -Xlog:aot \
     -Xlog:class+load=info:file=class-load.log \
     -cp app.jar com.example.App
~~~

`-Xlog:aot` giúp xem các thông báo liên quan đến cache. `-Xlog:class+load=info` ghi lại nguồn nạp class; class được nạp từ cache thường có nguồn `shared objects file`.

Không chỉ tìm một dòng `AOT cache loaded`. Hãy quan sát cả những class không được cache và nguyên nhân tương ứng. Cache có thể được nạp nhưng chỉ bao phủ một phần ứng dụng.

### Bước 5 — Kiểm tra command line thực tế của JVM

Khi ứng dụng đang chạy:

~~~bash
jcmd -l
jcmd <pid> VM.command_line
jcmd <pid> VM.version
jcmd <pid> VM.flags -all
~~~

Thay `<pid>` bằng process ID thật. Lệnh `VM.command_line` giúp phát hiện options do container, service manager hoặc môi trường triển khai thêm vào mà script local không có.

### Bước 6 — Tạo lại cache và đo lại

Sau khi sửa môi trường:

1. Xóa cache cũ khỏi build output hoặc đổi tên file.
2. Build đúng artifact cuối cùng.
3. Chạy training bằng JDK/OS/CPU của target.
4. Exercise workload đại diện.
5. Chờ assembly hoàn tất và xác nhận file `.aot`.
6. Chạy thử với `AOTMode=on`.
7. Chạy benchmark startup/warm-up nhiều lần, so với baseline không cache.
8. Chỉ publish cache cùng build/platform đã kiểm thử.

## 8. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `AOT cache file does not exist` | Sai đường dẫn, chưa tạo hoặc artifact chưa được copy | Kiểm tra path, quyền và pipeline artifact |
| `AOT cache cannot be loaded` | App/JDK/OS/CPU không tương thích | Tạo lại trên đúng build và target |
| `auto` không báo lỗi nhưng startup không cải thiện | JVM fallback sang không dùng cache | Thêm `-Xlog:aot`, thử `AOTMode=on` |
| `on` dừng ngay khi khởi động | Cache bị từ chối hoặc option không tương thích | Đọc log và so sánh runtime fingerprint |
| Một số class không được nạp từ cache | Training không load class đó hoặc classpath lệch | Bổ sung workload, kiểm tra class-load log |
| Cache dùng được local nhưng không dùng trong container | JDK/architecture/working directory/permissions khác | So image, user, JDK build và path |
| Cache tạo được nhưng assembly bị OOM | JVM assembly thứ hai cần heap và native memory | Tách record/create thành ba pha hoặc tăng giới hạn memory |
| Cache không có method profile hữu ích | Training không chạy đường nghiệp vụ | Tạo training run production-like |
| Sau nâng JDK cache không còn dùng được | Cache gắn với JDK release | Tạo lại cache cho JDK đích |
| Sau thêm thư viện cache bị bỏ qua | Application classpath đã thay đổi | Tạo lại cache sau dependency resolution |
| Cache hoạt động với G1 nhưng không với ZGC trên JDK 25 | JDK 25 chưa hỗ trợ AOT cache cùng ZGC | Dùng cấu hình GC được hỗ trợ hoặc nâng JDK có JEP 516 sau khi đánh giá |
| Spring Boot executable JAR không tận dụng cache | Nested JAR/layout không đáp ứng class loading requirements | Extract executable JAR và train/use cùng dạng extracted |
| Cache file rỗng hoặc thiếu sau khi dừng training | JVM bị kill hoặc assembly không hoàn tất | Chờ shutdown hoàn tất hoặc dùng `jcmd AOT.end_recording` |

## 9. Trường hợp Spring Boot: extracted JAR và cache mismatch

AOT cache là tính năng JVM, nhưng cấu trúc executable JAR của Spring Boot có thể ảnh hưởng trực tiếp tới class loading.

### 9.1. Dùng extracted form

Với Spring Boot có hỗ trợ tools jarmode, quy trình cơ bản:

~~~bash
# Extract executable JAR
java -Djarmode=tools -jar my-app.jar extract --destination application

cd application

# Training + cache creation
java -XX:AOTCacheOutput=app.aot \
     -Dspring.context.exit=onRefresh \
     -jar my-app.jar
~~~

Production:

~~~bash
java -XX:AOTCache=app.aot -jar my-app.jar
~~~

Phải chạy cache với **cùng dạng extracted application**. Không tạo cache từ extracted layout rồi chuyển sang chạy nested executable JAR theo một class-loading layout khác.

### 9.2. Muốn cải thiện cả warm-up

Trong Java 25, method profiles được lưu vào AOT cache theo JEP 515. Nếu chỉ dùng `spring.context.exit=onRefresh`, training tập trung vào startup và có thể bỏ qua các method nóng sau khi ứng dụng nhận request.

Để cải thiện cả warm-up:

1. Khởi động ứng dụng bằng đúng extracted layout.
2. Chạy một phần workload gần production (API phổ biến, serialization, business path, client initialization).
3. Kết thúc training một cách có kiểm soát để cache được ghi.
4. Dùng cache với cùng artifact, JDK và nền tảng.
5. Đo startup và thời gian đạt throughput/latency mục tiêu.

Không dùng full integration/regression suite nặng làm training mặc định nếu nó nạp nhiều class không có trong production. Chọn một bộ smoke workflow có chủ đích.

### 9.3. Spring Boot 3.x và 4.x

Tính năng AOT cache của JVM được hỗ trợ khi dùng Java 25+. Các bản Spring Boot có hướng dẫn đóng gói/extract riêng. Hãy dùng tài liệu đúng phiên bản Spring Boot đang triển khai; không sao chép tùy chọn jarmode hoặc cấu trúc thư mục từ một major version khác mà chưa kiểm tra.

Với Java 25+, Spring Boot khuyến nghị AOT cache khi có thể. CDS vẫn tồn tại trong JDK, nhưng không nên dùng hướng dẫn CDS cũ làm đường đi mặc định cho ứng dụng Java 25 mới.

## 10. Training cache cho ứng dụng chạy lâu và cách kết thúc ghi

Training run có thể là một ứng dụng server không tự kết thúc sau khi đã phục vụ một số request. Khi JVM được khởi chạy với `-XX:AOTCacheOutput` hoặc `-XX:AOTMode=record`, có thể kết thúc recording một cách chủ động bằng `jcmd`:

~~~bash
jcmd <pid> AOT.end_recording
~~~

Lệnh này kết thúc AOT training và ghi kết quả vào file được chỉ định bởi `-XX:AOTConfiguration` và/hoặc `-XX:AOTCacheOutput`.

Điều kiện:

- JVM phải được khởi chạy ở AOT training mode.
- `jcmd` phải chạy trên cùng máy với JVM và có effective user/group phù hợp.
- Phải kiểm tra output và file cache sau khi lệnh hoàn tất.
- Không dùng lệnh này trên production process ngoài kế hoạch vận hành đã kiểm soát.

Nếu training process kết thúc bình thường, JVM cũng có thể hoàn tất recording khi shutdown. Tránh `kill -9`, force termination hoặc container eviction trước khi cache được ghi xong.

## 11. Đo cache có thực sự mang lại lợi ích không?

Một cache nạp thành công chưa chắc cải thiện đáng kể trải nghiệm người dùng. Đo ít nhất ba nhóm:

| Chỉ số | Câu hỏi | Cách đo |
| --- | --- | --- |
| Startup time | Từ lúc JVM start đến khi ứng dụng sẵn sàng | Log startup, readiness probe hoặc benchmark harness |
| Warm-up time | Bao lâu để đạt throughput/latency ổn định | Chạy tải đại diện và theo dõi metric theo thời gian |
| Cache coverage | Bao nhiêu class/method profile thực sự hữu ích | `-Xlog:class+load`, AOT logs và JFR training |

### 11.1. Thiết kế phép đo A/B

So sánh ít nhất hai cấu hình:

- Baseline: không dùng cache (`-XX:AOTMode=off`).
- Candidate: dùng cache (`-XX:AOTCache=app.aot`).

Giữ nguyên:

- JDK build và JVM options.
- OS/CPU và giới hạn container.
- Artifact và classpath.
- GC, heap size, environment variables.
- Startup readiness condition và workload.
- Số lần chạy, trạng thái máy và cách xử lý outlier.

Chạy nhiều lần và so median/percentile, không kết luận từ một lần khởi động. Tách thời gian JVM startup khỏi thời gian chờ database/network/service dependency; cache JVM không loại bỏ độ trễ của dịch vụ bên ngoài.

### 11.2. Khi cache không giúp nhiều

Một số nguyên nhân hợp lý:

- Phần lớn startup time nằm ở database migration, remote config, network hoặc external service.
- Training workload không đại diện nên method profile không có ích.
- Ứng dụng đã có startup time rất nhỏ và phần class loading/linking không phải bottleneck.
- Cache chỉ cover một phần classpath.
- Production workload thay đổi nhiều so với training.
- Thời gian đạt peak performance không phải yếu tố quan trọng với process sống lâu.
- Chi phí tạo, lưu và phân phối cache lớn hơn lợi ích thực tế.

Trong trường hợp này, không tiếp tục thêm JVM flags tùy tiện. Hãy dùng profiler/JFR để xác định bottleneck thật trước khi đầu tư vào AOT cache.

## 12. Quy trình CI/CD khuyến nghị

~~~mermaid
flowchart TD
    A["Build application artifact"] --> B["Resolve dependencies và target platform"]
    B --> C["Training run production-like trên JDK 25"]
    C --> D["Assembly tạo .aot"]
    D --> E["Smoke test với AOTMode=on"]
    E --> F{"Cache load thành công?"}
    F -->|Không| G["Fail cache job, lưu log và fingerprint"]
    F -->|Có| H["Benchmark startup/warm-up"]
    H --> I["Publish app + cache theo build/platform"]
    I --> J["Deploy với AOTMode=auto"]
    J --> K["Theo dõi log AOT và startup metrics"]
~~~

Một pipeline có thể lưu kèm metadata:

~~~yaml
application:
  build-id: <commit-or-build-id>
  artifact-sha256: <sha256>
  classpath-fingerprint: <ordered-list-or-hash>

runtime:
  java-vendor: <vendor>
  java-version: <exact-build>
  os: <os-name-and-version>
  architecture: <cpu-architecture>
  gc: <collector>
  jvm-options: <normalized-options>

aot:
  cache-file: app.aot
  training-profile: <workflow-id>
  created-at: <timestamp>
  validation: passed
~~~

Đây là mẫu metadata cho CI artifact, không phải file cấu hình JVM chuẩn. Dùng nó để ngăn cache của build cũ hoặc kiến trúc khác được deploy nhầm.

**Chính sách khuyến nghị:**

- Tạo cache sau khi dependency resolution và packaging hoàn tất.
- Cache được version hóa theo artifact digest + JDK build + OS/architecture.
- Chạy smoke test với `AOTMode=on` trong CI để phát hiện lỗi tương thích.
- Production dùng `AOTMode=auto` nếu ưu tiên ứng dụng vẫn khởi động khi cache bị từ chối.
- Giám sát log AOT và startup metrics để phát hiện fallback.
- Khi cache thất bại, giữ log và metadata của training/production để có thể tái hiện.

## 13. Checklist xử lý sự cố

### Khi JVM không nạp cache

- [ ] File `.aot` tồn tại và không rỗng.
- [ ] Đường dẫn cache chính xác, JVM có quyền đọc.
- [ ] Training và production dùng cùng JDK build.
- [ ] OS và CPU architecture tương thích.
- [ ] Artifact ứng dụng chưa đổi kể từ training.
- [ ] Classpath/module path và thứ tự JAR khớp.
- [ ] JAR timestamps được bảo toàn.
- [ ] Không có wildcard, directory hoặc nested JAR không phù hợp.
- [ ] JVM options/JVMTI agents không làm thay đổi class loading.
- [ ] GC được hỗ trợ trong JDK đang dùng.
- [ ] Đã thử `AOTMode=on` trong môi trường chẩn đoán.
- [ ] Đã bật `-Xlog:aot`.

### Khi cache nạp nhưng hiệu năng chưa cải thiện

- [ ] Training workload có startup path và business path đại diện.
- [ ] Đã exercise các method nóng cần tối ưu.
- [ ] Đã xem class loading log để xác định cache coverage.
- [ ] Đã tách JVM startup khỏi database/network initialization.
- [ ] Đã đo nhiều lần với baseline không cache.
- [ ] Đã so warm-up profile và thời gian đạt throughput/latency mục tiêu.
- [ ] Đã tránh đưa test-only class và workload không dùng vào training.

## 14. Bài thực hành tổng hợp

**Tình huống:** một ứng dụng Java 25 chạy trong container. Local tạo được `app.aot`, nhưng production không thấy startup cải thiện. Khi thêm `AOTMode=on`, JVM báo không thể nạp cache.

### Phần A — Tái hiện baseline

1. Kiểm tra `java -version`, vendor và build.
2. Ghi command line, classpath, JAR timestamps, OS và CPU.
3. Chạy ứng dụng không cache để lấy startup baseline.
4. Tạo cache với `-XX:AOTCacheOutput=app.aot`.
5. Xác nhận file tồn tại sau khi training và assembly kết thúc.

**Đạt** khi có metadata đầy đủ của training environment và file cache hợp lệ về mặt tồn tại.

### Phần B — Tái hiện lỗi mismatch

Thay đổi từng yếu tố trong môi trường thử nghiệm:

1. Dùng một JDK build khác.
2. Thay đổi thứ tự JAR trong classpath.
3. Thay một dependency bằng version khác.
4. Đổi OS/architecture nếu có môi trường phù hợp.
5. Thêm JVMTI/Java agent dùng để transform class.
6. Dùng ZGC trên JDK 25.

Với mỗi lần thử, lưu log AOT và phân biệt lỗi nào làm cache bị từ chối, lỗi nào chỉ làm cache coverage giảm.

**Đạt** khi không gộp mọi hiện tượng thành một nguyên nhân chung “cache lỗi”.

### Phần C — Khắc phục

1. Tạo lại cache trên đúng JDK/platform.
2. Dùng classpath ổn định và bảo toàn timestamp.
3. Loại bỏ option/agent không tương thích trong bài test, hoặc xác nhận phương án production khác.
4. Bổ sung workload đại diện vào training.
5. Kiểm tra với `AOTMode=on`.
6. Chạy lại production mode với `auto` và theo dõi log.

**Đạt** khi có bằng chứng cache được nạp và các class cần thiết có nguồn load từ cache.

### Phần D — Đánh giá lợi ích

1. Chạy nhiều lần với cache off.
2. Chạy nhiều lần với cache on.
3. So sánh startup median, warm-up và class coverage.
4. Phân tích phần thời gian còn lại do external dependency.
5. Quyết định giữ hay bỏ cache dựa trên số đo.

**Đạt** khi kết luận phản ánh workload và môi trường đo, không khẳng định cache luôn giúp ứng dụng nhanh hơn.

## 15. Câu hỏi tự đánh giá

1. AOT cache được giới thiệu trong JDK nào và JEP nào?
2. JEP 514 thay đổi workflow tạo cache trong Java 25 ra sao?
3. JEP 515 bổ sung dữ liệu gì và ảnh hưởng tới giai đoạn nào?
4. Vì sao file `.aot` không thể dùng chung cho mọi ứng dụng?
5. Những thuộc tính môi trường nào phải được giữ nhất quán giữa training và production?
6. `AOTMode=auto` khác `AOTMode=on` thế nào khi cache không nạp được?
7. Vì sao ứng dụng vẫn chạy bình thường nhưng cache có thể đã bị từ chối?
8. Làm thế nào để kiểm tra cache có thực sự được nạp?
9. Vì sao classpath order và JAR timestamps có thể ảnh hưởng cache?
10. Tại sao không nên dùng wildcard hoặc thư mục class trực tiếp trong Spring AOT cache workflow?
11. Vì sao training chỉ chạy health check có thể không cải thiện warm-up?
12. JEP 515 có loại bỏ JIT runtime profiling không?
13. Khi nào nên dùng workflow ba pha thay cho `AOTCacheOutput` một bước?
14. Vì sao one-step cache creation có thể cần gần gấp đôi heap?
15. `JDK_AOT_VM_OPTIONS` có vai trò gì?
16. Khi nào `jcmd AOT.end_recording` hữu ích?
17. Vì sao JDK 25 không nên dùng AOT cache cùng ZGC?
18. Khác biệt giữa HotSpot AOT cache, Spring AOT processing và GraalVM Native Image là gì?
19. Khi nâng JDK hoặc thay dependency, pipeline nên xử lý cache thế nào?
20. Vì sao phải đo startup/warm-up A/B trước khi quyết định giữ cache?

## Tài liệu tham khảo

- [Oracle JDK 25 — The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các mode, options, giới hạn tương thích, fallback và logging.
- [Oracle JDK 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): lệnh `AOT.end_recording` và chẩn đoán JVM.
- [Oracle — Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): JEP 514 và JEP 515.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): nền tảng AOT cache.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): workflow tạo cache một bước.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): method profiles trong cache.
- [Inside Java — Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): training, assembly, workload, memory và chẩn đoán cache.
- [Spring Framework 7.1 — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): classpath, JAR timestamps, extracted layout và method profiles.
- [Spring Boot 4.2 — AOT Cache](https://docs.spring.io/spring-boot/reference/packaging/aot-cache.html): quy trình extract và sử dụng AOT cache cho executable JAR.

