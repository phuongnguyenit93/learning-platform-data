# CRaC và CDS hoặc AppCDS: khác biệt về phạm vi trạng thái

CRaC và CDS/AppCDS đều có thể giúp ứng dụng Java khởi động nhanh hơn, nhưng chúng giải quyết hai phần rất khác nhau của quá trình khởi động. **CDS/AppCDS lưu trữ dữ liệu phục vụ việc nạp class và chia sẻ một số dữ liệu đủ điều kiện giữa các JVM; CRaC checkpoint lưu trạng thái của một tiến trình đã chạy để có thể khôi phục tiến trình đó.** Một archive CDS không phải ảnh process, còn một checkpoint CRaC không chỉ là archive class.

CDS (Class Data Sharing) tập trung vào class metadata và cơ chế chia sẻ dữ liệu class. AppCDS (Application Class-Data Sharing) mở rộng phạm vi archive để bao gồm các class của ứng dụng và dependency. Khi một JVM mới khởi động, nó có thể ánh xạ archive phù hợp và giảm công việc đọc, parse, load hoặc tạo một số cấu trúc class.

CRaC (Coordinated Restore at Checkpoint) đi xa hơn phạm vi class loading. Ứng dụng chạy và được chuẩn bị trước; JVM checkpoint trạng thái tiến trình theo khả năng của runtime/nền tảng. Khi restore, ứng dụng tiếp tục từ trạng thái đã lưu, sau đó callback CRaC phục hồi các tài nguyên bên ngoài như socket, connection pool, credential và scheduler theo thiết kế của ứng dụng.

Vì phạm vi trạng thái khác nhau, lựa chọn giữa hai giải pháp phụ thuộc mục tiêu: nếu chỉ cần giảm chi phí class loading, CDS/AppCDS thường đơn giản hơn; nếu cần khôi phục cả trạng thái runtime đã warm-up và một phần trạng thái ứng dụng trong memory, CRaC phù hợp hơn nhưng đòi hỏi quy trình checkpoint/restore và quản lý resource phức tạp hơn. Hai cơ chế cũng có thể được kết hợp nếu runtime và quy trình triển khai hỗ trợ.

## 1. Bắt đầu từ phạm vi trạng thái được lưu

Điểm khác biệt cốt lõi không nằm ở tên gọi mà ở **đối tượng được lưu và khôi phục**.

| Khía cạnh | CDS/AppCDS | CRaC |
| --- | --- | --- |
| Đơn vị được lưu | Archive dữ liệu class, chủ yếu là class metadata và dữ liệu liên quan đủ điều kiện | Trạng thái của một tiến trình JVM đã được checkpoint |
| Phạm vi class | Class nền tảng và, với AppCDS, class ứng dụng/dependency được archive | Các class đã được nạp trong tiến trình và trạng thái runtime liên quan nằm trong process image |
| Heap ứng dụng | Không lưu toàn bộ heap đang hoạt động; chỉ một số archived heap objects đủ điều kiện trong cơ chế CDS | Có thể khôi phục heap state của tiến trình theo khả năng checkpoint runtime |
| Thread và execution state | Không lưu thread stack hoặc trạng thái thực thi đang chạy của một ứng dụng | Là một phần của trạng thái process được checkpoint; resource/thread cần được chuẩn bị theo CRaC lifecycle |
| JIT/runtime warm-up | Archive class giúp giảm class loading; không phải snapshot toàn bộ trạng thái thực thi/JIT của một lần chạy | Có thể giữ trạng thái runtime đã warm-up trong process image, tùy JVM và nền tảng |
| Socket/connection | Không lưu connection đang mở | Có thể có trạng thái descriptor trong checkpoint, nhưng tài nguyên bên ngoài có thể không còn hợp lệ và thường cần đóng/recreate qua callback |
| Cách dùng khi khởi động | JVM mới khởi động và sử dụng archive | JVM/process được restore từ checkpoint image |
| Phạm vi tái sử dụng | Archive có thể được dùng bởi nhiều JVM tương thích | Checkpoint gắn với môi trường/runtime và trạng thái process cụ thể; không phải archive dùng chung cho nhiều JVM độc lập |
| Yêu cầu vận hành | Tạo archive, bảo đảm classpath/module compatibility và kiểm tra CDS log | Warm-up, prepare resources, checkpoint, package, restore đúng môi trường và kiểm tra readiness |

CDS/AppCDS không giữ lại trạng thái một request đang xử lý, object graph tùy ý của ứng dụng hoặc connection pool đã được khởi tạo trong một lần chạy. CRaC có thể khôi phục nhiều trạng thái tiến trình hơn, nhưng không biến các hệ thống bên ngoài thành một phần của snapshot nhất quán.

## 2. CDS là gì?

CDS là cơ chế của HotSpot JVM cho phép lưu một số dữ liệu class vào archive để JVM có thể chia sẻ và tái sử dụng khi khởi chạy. Thay vì mỗi JVM phải tự tạo lại toàn bộ cấu trúc class từ đầu, JVM có thể map archive và sử dụng các cấu trúc đã được chuẩn bị.

Lợi ích chính:

- Giảm thời gian nạp và khởi tạo class trong các ứng dụng có nhiều class.
- Giảm một phần chi phí memory khi nhiều JVM dùng chung dữ liệu archive trên cùng host.
- Giảm công việc parse/verify/metadata setup cho class phù hợp.
- Có thể cải thiện startup của nhiều loại ứng dụng mà không cần thay đổi code nghiệp vụ.

CDS không phải cơ chế lưu trạng thái một lần chạy. Mỗi JVM vẫn tạo heap và thực thi chương trình theo vòng đời riêng. JVM mới không tiếp tục từ thread, request, connection hoặc object graph tùy ý của JVM đã tạo archive.

### 2.1 Class metadata và archived data

Archive CDS có thể chứa class metadata và một số dữ liệu liên quan được JVM hỗ trợ chia sẻ. Một số JDK còn hỗ trợ archived Java heap objects, chẳng hạn một số string hoặc object thuộc module graph/class metadata đã được chuẩn bị. Những object này phải đáp ứng quy tắc archive của JVM; điều đó không có nghĩa mọi object đang sống trong heap ứng dụng đều được đưa vào archive.

Vì vậy, cần phân biệt:

- **Class metadata:** thông tin JVM cần để biểu diễn class, method, field, constant pool và các cấu trúc runtime liên quan.
- **Archived heap objects:** một tập object Java cụ thể mà JVM cho phép lưu trong archive, không phải toàn bộ heap ứng dụng.
- **Application runtime state:** object graph nghiệp vụ, session, thread, connection, cache động và trạng thái request trong một process. CDS không phải snapshot cho nhóm trạng thái này.

Khi JVM khởi động từ CDS archive, nó vẫn phải tạo các object runtime cần thiết, chạy static initialization theo semantics phù hợp và thực hiện công việc ứng dụng chưa được archive.

## 3. AppCDS mở rộng archive tới class ứng dụng

AppCDS (Application Class-Data Sharing) cho phép archive class do ứng dụng và dependency cung cấp, bên cạnh class nền tảng mà CDS có thể chia sẻ. Điều này hữu ích với ứng dụng framework lớn có nhiều class được nạp từ JAR/module path.

Ví dụ, một service Spring có thể nạp nhiều class từ:

- Application JAR.
- Spring Framework và Spring Boot.
- JSON/serialization library.
- Database driver.
- Validation, logging và metrics library.
- Các thư viện nội bộ khác.

AppCDS có thể giúp JVM tái sử dụng dữ liệu class cho các class phù hợp trong archive. Nó không tự tạo Spring `ApplicationContext`, không chạy `@PostConstruct`, không mở DataSource và không nạp dữ liệu nghiệp vụ vào cache chỉ vì các class tương ứng đã có trong archive.

### 3.1 Static archive và dynamic archive

Ở mức vận hành, AppCDS thường được tạo theo hai hướng:

| Kiểu archive | Cách tạo khái quát | Đặc điểm |
| --- | --- | --- |
| Static archive | Thu thập class list rồi tạo archive bằng chế độ dump CDS | Archive được tạo rõ ràng trong bước build/provision; thường phù hợp với class set tương đối ổn định. |
| Dynamic archive | Chạy ứng dụng với `-XX:ArchiveClassesAtExit=<file>` để ghi archive class đã được nạp khi JVM thoát bình thường | Thuận tiện thu thập class từ lần chạy đại diện; cần JVM kết thúc bình thường và tuân thủ điều kiện của JDK. |

Tên tùy chọn, điều kiện tạo và khả năng của archive phụ thuộc phiên bản JDK. Hãy kiểm tra tài liệu của đúng vendor/build trước khi đưa lệnh vào pipeline.

### 3.2 Ví dụ tạo dynamic AppCDS archive

Ví dụ khái quát với một ứng dụng classpath:

```bash
java \
  -XX:ArchiveClassesAtExit=app-cds.jsa \
  -cp app.jar \
  com.example.Application
```

Chạy ứng dụng theo workload đại diện, sau đó để JVM thoát bình thường để runtime có cơ hội ghi dynamic archive. Nếu process bị kill cưỡng bức hoặc JVM kết thúc bất thường, archive có thể không được tạo hoàn chỉnh.

Sử dụng archive trong lần khởi chạy sau:

```bash
java \
  -Xshare:auto \
  -XX:SharedArchiveFile=app-cds.jsa \
  -cp app.jar \
  com.example.Application
```

Đây là ví dụ tối giản. Dynamic archive có thể phụ thuộc base archive và các điều kiện classpath/module path được dùng khi tạo. Hãy dùng đúng cấu hình được tài liệu JDK yêu cầu và kiểm tra log CDS để biết archive thực sự được sử dụng hay bị bỏ qua.

## 4. Phạm vi trạng thái của CRaC

CRaC cho phép chuẩn bị một JVM đang chạy rồi tạo checkpoint để khôi phục trạng thái tiến trình. So với CDS/AppCDS, phạm vi được khôi phục lớn hơn nhiều.

Một process image có thể giữ các trạng thái như:

- Heap object và trạng thái ứng dụng tại thời điểm checkpoint.
- Các class đã được nạp và cấu trúc runtime đang tồn tại.
- Thread/process execution state theo khả năng checkpoint implementation.
- Một số trạng thái native/process và file descriptor được nền tảng hỗ trợ.
- Các cache và object đã được khởi tạo trong lần chạy trước.
- Trạng thái runtime đã warm-up, có thể giảm công việc khởi động lặp lại.

Phạm vi chính xác phụ thuộc JDK CRaC, CRIU hoặc cơ chế nền tảng và loại resource. Không nên khẳng định mọi socket, native handle, thread hoặc thiết bị đều có thể tiếp tục hoạt động sau restore. Ứng dụng cần dùng `org.crac.Resource` để đóng, làm mới hoặc kiểm tra các tài nguyên có vòng đời bên ngoài process image.

### 4.1 Checkpoint không đồng nghĩa với snapshot mọi dependency

Giả sử ứng dụng có một object `DataSource`, connection pool với 10 connection và cache DNS. Checkpoint có thể giữ các object này trong heap, nhưng database có thể đóng session trong thời gian process tạm dừng; DNS có thể đổi IP; credential có thể hết hạn. Restore object không làm database mở lại session cũ hoặc DNS cập nhật cache tự động.

Vì vậy, một thiết kế CRaC thường:

1. Dừng nhận request/message mới.
2. Drain request và transaction đang chạy.
3. Đóng pool/socket/client theo API được hỗ trợ.
4. Giữ cấu hình logic và factory cần thiết.
5. Tạo checkpoint.
6. Sau restore, refresh endpoint/secret/config và tạo resource mới.
7. Validate dependency rồi mới mở readiness.

Điều này khác hẳn CDS: CDS không yêu cầu một ứng dụng đang chạy phải quiesce và đóng resource để tạo class archive.

## 5. So sánh bằng một ví dụ ứng dụng

Giả sử một ứng dụng Spring Boot có 20.000 class được nạp, một `ApplicationContext`, DataSource, cache sản phẩm và một scheduler.

### Dùng CDS/AppCDS

1. Thu thập/đóng gói class archive từ class set phù hợp.
2. JVM mới khởi động và map archive.
3. JVM vẫn thực hiện startup flow: tạo bean, tạo `ApplicationContext`, khởi tạo service, kết nối database và tạo cache theo code ứng dụng.
4. Lợi ích chính nằm ở phần class loading/metadata setup được archive hỗ trợ.

### Dùng CRaC

1. Khởi động ứng dụng đầy đủ trong môi trường checkpoint.
2. Chạy warm-up để nạp class, chạy các đường code quan trọng, tạo cache phù hợp và làm nóng runtime.
3. Quiesce worker, drain transaction và đóng tài nguyên cần tái tạo.
4. Tạo checkpoint process image.
5. Restore process từ image.
6. Chạy `afterRestore`, tạo lại DataSource/HTTP client/broker consumer và validate dependency.
7. Ứng dụng có thể bỏ qua phần lớn startup/warm-up đã được thực hiện trước checkpoint, tùy phạm vi runtime restore.

### Kết quả về trạng thái

| Thành phần | CDS/AppCDS | CRaC |
| --- | --- | --- |
| Class metadata đã archive | Có thể tái sử dụng | Có thể đã nằm trong trạng thái runtime được checkpoint; không phải archive class dùng chung. |
| Spring bean graph | Được tạo lại khi JVM mới startup | Có thể được giữ trong heap và khôi phục cùng process. |
| `ApplicationContext` | Startup flow tạo context mới | Context đang tồn tại có thể được khôi phục; không tự chạy lại constructor/`@PostConstruct`. |
| Cache ứng dụng | Nạp lại theo startup logic; chỉ archived object đủ điều kiện mới được chia sẻ | Cache trong heap có thể được giữ, nhưng cần freshness/version validation. |
| JIT/runtime warm-up | Không khôi phục toàn bộ trạng thái thực thi từ một lần chạy | Có thể giữ trạng thái runtime đã warm-up theo khả năng implementation. |
| Database pool | Tạo mới theo startup logic | Phải kiểm tra/đóng và thường tạo lại sau restore. |
| Request đang xử lý | Không được khôi phục từ archive | Cần drain trước checkpoint; không nên snapshot giữa transaction/request chưa hoàn tất. |

## 6. Những gì CDS/AppCDS không lưu

CDS/AppCDS không phải công cụ để lưu trạng thái tùy ý của ứng dụng. Cụ thể, không nên kỳ vọng archive giữ:

- Giá trị hiện tại của mọi field trong singleton bean.
- Danh sách session người dùng đang đăng nhập.
- Các request đang chờ hoặc đang xử lý.
- Thread stack và trạng thái monitor/lock của một lần chạy.
- Nội dung connection pool đang mở và socket peer.
- Transaction database chưa commit.
- Offset/ack state của message broker đang xử lý.
- Cache động chứa dữ liệu vừa truy vấn trong lần chạy trước, trừ phần rất giới hạn thuộc archived object mechanism mà JVM hỗ trợ.
- Credential hoặc token vừa được refresh trong một lần chạy.

Một số object tĩnh/immutable có thể được JVM archive nếu đáp ứng điều kiện của CDS, nhưng không được thiết kế ứng dụng dựa trên giả định rằng bất kỳ object nào có thể serialize hoặc static final đều tự động được đưa vào archive.

## 7. Những gì CRaC không bảo đảm

CRaC có phạm vi process state rộng hơn, nhưng cũng không phải snapshot nhất quán toàn hệ thống. Không được mặc định checkpoint bảo đảm:

- Database transaction đang mở có thể tiếp tục sau restore.
- TCP socket còn kết nối tới cùng server hoặc endpoint.
- DNS, route, service discovery và IP giữ nguyên.
- Credential, access token, lease hoặc certificate vẫn còn hạn.
- Broker consumer còn giữ assignment, delivery tag hoặc receipt handle cũ.
- Scheduler đã chạy đúng lịch trong thời gian process bị checkpoint.
- Filesystem, mount, cgroup, PID namespace và CPU/kernel ở host khác hoàn toàn tương thích.
- Cache trong heap còn mới so với dữ liệu nguồn.

CRaC khôi phục process state; ứng dụng và các hệ thống bên ngoài vẫn cần phối hợp lifecycle, consistency và readiness.

## 8. Mô hình trạng thái: archive class và process image

Có thể hình dung hai cơ chế như sau:

```text
CDS / AppCDS
-------------
JDK class data + application class data
                 |
                 v
          Shared archive (.jsa)
                 |
       +---------+---------+
       |                   |
       v                   v
   JVM instance A      JVM instance B
   new heap            new heap
   new threads         new threads
   startup flow        startup flow


CRaC
----
Running JVM process
  heap + runtime + threads + app state
                 |
                 v
       beforeCheckpoint resources
                 |
                 v
          Process checkpoint
                 |
                 v
       Restore same process state
                 |
                 v
       afterRestore resources
                 |
                 v
          Application resumes
```

CDS archive được thiết kế để nhiều JVM tương thích có thể sử dụng. CRaC checkpoint đại diện cho trạng thái một process cụ thể, không phải dữ liệu class dùng chung để nhiều process mới cùng map như một archive AppCDS.

## 9. Startup performance: hai cơ chế giảm chi phí khác nhau

CDS/AppCDS chủ yếu giảm chi phí liên quan tới class data và class loading. Lợi ích thường rõ hơn ở ứng dụng có nhiều class, framework lớn hoặc nhiều JVM khởi động trên cùng host.

CRaC có thể giảm thêm nhiều công việc startup vì tiến trình được restore từ trạng thái đã chạy và warm-up. Nếu ứng dụng đã tạo `ApplicationContext`, nạp cache và thực thi các đường code quan trọng trước checkpoint, những trạng thái đó có thể được khôi phục cùng process. Tuy nhiên, thời gian reconnect dependency, refresh credential và validate readiness vẫn nằm trong startup-to-ready time.

Không nên so sánh hai cơ chế bằng một con số startup duy nhất. Cần đo:

- Cold start không CDS/CRaC.
- Cold start với CDS/AppCDS.
- Restore với CRaC.
- Nếu kết hợp, restore CRaC từ runtime đã dùng CDS/AppCDS khi tạo checkpoint.

Dùng cùng application build, CPU/memory limit, dependency, workload và readiness criteria. Đo nhiều lần, ghi percentile và phân biệt process launch với thời điểm ứng dụng thực sự nhận traffic.

## 10. Tạo và dùng CDS/AppCDS trong pipeline

Một pipeline CDS/AppCDS thường có các bước:

1. Build ứng dụng và dependency.
2. Chạy ứng dụng hoặc class-loading workload để thu thập class list.
3. Tạo archive theo chế độ static hoặc dynamic được JDK hỗ trợ.
4. Khởi chạy JVM mới với archive.
5. Kiểm tra log để xác nhận class archive được sử dụng.
6. Đo startup time và memory so với baseline.

Ví dụ thu thập class list cho một lần chạy:

```bash
java \
  -Xshare:off \
  -XX:DumpLoadedClassList=app.classlist \
  -cp app.jar \
  com.example.Application
```

Sau khi có class list, có thể tạo archive theo cú pháp hỗ trợ của JDK tương ứng, ví dụ:

```bash
java \
  -Xshare:dump \
  -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app-cds.jsa \
  -cp app.jar
```

Các tùy chọn và điều kiện classpath/module path có thể thay đổi theo JDK version. Một số workflow AppCDS hiện đại dùng dynamic archive đơn giản hơn. Hãy kiểm tra tài liệu JDK cụ thể thay vì sao chép lệnh giữa các vendor/version mà không xác minh.

Khi chạy với archive, có thể dùng `-Xshare:auto` để JVM dùng archive nếu khả dụng hoặc bỏ qua nếu không phù hợp; `-Xshare:on` yêu cầu CDS phải được sử dụng và có thể làm JVM báo lỗi nếu không thể; `-Xshare:off` tắt chia sẻ class data. Log `-Xlog:cds` hữu ích để xem archive có được map và class nào bị bỏ qua.

## 11. Tạo checkpoint CRaC trong pipeline

Pipeline CRaC cần thêm các bước mà AppCDS không yêu cầu:

1. Provision môi trường tương thích với checkpoint/restore.
2. Start ứng dụng với runtime và cấu hình xác định.
3. Chạy warm-up profile đại diện.
4. Xác nhận warm-up hoàn tất và ứng dụng ở trạng thái phù hợp.
5. Chuyển readiness sang từ chối traffic và drain công việc mới.
6. Đóng/chuẩn bị resource qua `beforeCheckpoint`.
7. Trigger checkpoint theo JDK/CRaC runtime.
8. Xác nhận checkpoint hoàn tất trước khi package.
9. Restore trong môi trường tương thích và chạy smoke test.
10. Refresh dependency và chỉ mở readiness sau validation.

CRaC đòi hỏi quản lý resource lifecycle, artifact compatibility và bảo mật checkpoint image. Một archive AppCDS thường đơn giản hơn về vận hành vì nó không chứa trạng thái heap ứng dụng của một process đang chạy.

## 12. Có thể kết hợp CDS/AppCDS và CRaC không?

Về mặt mục tiêu, hai cơ chế không loại trừ nhau: CDS/AppCDS có thể hỗ trợ class loading trong JVM được dùng để tạo checkpoint; CRaC có thể checkpoint process sau khi ứng dụng đã warm-up. Tuy nhiên, lợi ích thực tế và khả năng kết hợp phụ thuộc JDK/vendor/build, cách tạo archive, cách khởi chạy JVM và runtime CRaC cụ thể.

Một quy trình có thể thử nghiệm:

1. Tạo AppCDS archive từ application build đã pin.
2. Khởi chạy checkpoint builder với cùng JDK và archive.
3. Warm-up ứng dụng.
4. Tạo CRaC checkpoint.
5. Restore bằng đúng runtime image/configuration và kiểm tra kết quả.

Trong mô hình này, AppCDS có thể giúp quá trình khởi chạy builder; CRaC lưu trạng thái tiến trình sau warm-up. Khi restore CRaC, JVM đang khôi phục process image chứ không đơn giản tạo một JVM mới rồi nạp lại AppCDS archive từ đầu.

Không giả định kết hợp hai cơ chế luôn đem lại lợi ích cộng dồn. Nếu CRaC checkpoint đã được tạo sau warm-up đầy đủ, phần tiết kiệm startup của AppCDS trong builder có thể ít ảnh hưởng tới thời gian restore cuối cùng. Nó vẫn có thể giúp tạo checkpoint nhanh hơn hoặc có lợi cho đường cold-start fallback. Cần benchmark cả ba cấu hình.

## 13. Tính tương thích của CDS/AppCDS

CDS archive có ràng buộc với JDK và cách chạy ứng dụng. Archive có thể không được sử dụng hoặc bị từ chối nếu môi trường không tương thích.

Các yếu tố cần kiểm tra:

- JDK vendor, version và build.
- Base archive phù hợp với runtime.
- Classpath/module path và vị trí JAR.
- Class loader và cách nạp class.
- Class bytecode/dependency có thay đổi so với lúc archive được tạo hay không.
- Các tùy chọn JVM ảnh hưởng tới CDS.
- Hệ điều hành, architecture và điều kiện mapping archive.

Một số class có thể không được archive hoặc không được chia sẻ do class loader, bytecode transformation, instrumentation hoặc điều kiện JVM. Điều này không nhất thiết làm ứng dụng thất bại; JVM có thể nạp class theo cách thông thường tùy chế độ `-Xshare`.

Không copy AppCDS archive sang runtime khác mà không kiểm tra. Nếu archive bị bỏ qua trong chế độ auto, ứng dụng có thể vẫn chạy nhưng startup benefit biến mất. Nếu dùng chế độ yêu cầu sharing, mismatch có thể làm JVM không khởi động.

## 14. Tính tương thích của CRaC checkpoint

CRaC checkpoint có ràng buộc môi trường rộng hơn archive class. Khả năng restore phụ thuộc vào process state, runtime, kernel và các resource được checkpoint.

Manifest checkpoint nên ghi:

- Application build và container image digest.
- JDK vendor/version/build và CRaC implementation.
- CRIU version/capabilities nếu sử dụng.
- OS/kernel/CPU architecture và feature baseline.
- Container runtime, namespace, cgroup và mount configuration.
- Native libraries, agents và drivers.
- Checkpoint configuration, resource callback result và artifact checksum.
- Dependency/configuration assumptions cần refresh sau restore.

Không dùng checksum làm bằng chứng tương thích. Checksum chỉ xác nhận nội dung không đổi so với lúc hash; restore test mới chứng minh artifact hoạt động trên môi trường mục tiêu.

## 15. Bảo mật và dữ liệu được lưu

CDS/AppCDS archive chủ yếu chứa class data, nhưng vẫn cần quản lý integrity và nguồn gốc artifact. Archive có thể tiết lộ class nội bộ, package name, dependency và cấu trúc ứng dụng.

CRaC checkpoint có rủi ro lớn hơn vì có thể chứa dữ liệu trong memory:

- Password, token, API key và private key.
- Session cookie và thông tin người dùng.
- Request/response payload và dữ liệu nghiệp vụ.
- Cache, connection configuration và endpoint nội bộ.
- Dữ liệu nhạy cảm khác đang tồn tại trong heap/native memory.

Với cả hai, cần kiểm soát quyền đọc/ghi, checksum/signature và retention. Với CRaC, cần mã hóa checkpoint khi lưu/truyền, giới hạn người được phép restore/đọc ảnh và không đính kèm raw image vào ticket/chat thông thường.

Nếu warm-up nạp dữ liệu production vào heap, checkpoint có thể lưu dữ liệu đó. Ưu tiên fixture hoặc dữ liệu test và refresh cache nhạy cảm sau restore.

## 16. Bảng lựa chọn theo nhu cầu

| Nhu cầu | CDS/AppCDS | CRaC |
| --- | --- | --- |
| Giảm thời gian class loading | Phù hợp trực tiếp | Có thể gián tiếp vì class đã nạp nằm trong process state |
| Dùng chung class metadata giữa nhiều JVM | Phù hợp | Không phải mục tiêu của checkpoint |
| Giảm chi phí khởi tạo framework/bean | Chỉ giảm phần class loading; framework vẫn khởi tạo | Có thể khôi phục context/bean state đã tạo |
| Giữ cache đã warm-up | Không giữ cache động tùy ý | Có thể giữ cache trong heap; cần kiểm tra freshness |
| Giữ trạng thái runtime/JIT warm-up | Không phải snapshot runtime của một lần chạy | Có thể giữ một phần runtime state theo implementation |
| Khôi phục process đang chạy | Không | Có |
| Giảm cold start với ít thay đổi vận hành | Thường dễ triển khai hơn | Cần môi trường checkpoint/restore và resource integration |
| Phù hợp nhiều JVM instance độc lập | Archive có thể dùng lại nếu tương thích | Mỗi process cần checkpoint phù hợp; không dùng một ảnh như class archive chung |
| Cần đóng/mở lại network resource | Không có lifecycle checkpoint đặc biệt | Thường cần Resource callbacks |
| Cần bảo vệ snapshot chứa heap data | Không lưu toàn bộ heap ứng dụng | Có, checkpoint có thể chứa dữ liệu nhạy cảm trong memory |

## 17. Khi nào nên chọn CDS/AppCDS?

CDS/AppCDS thường là lựa chọn hợp lý khi:

- Startup chủ yếu bị chi phối bởi class loading và class metadata setup.
- Ứng dụng có nhiều class/framework dependency.
- Muốn giữ mô hình JVM startup thông thường.
- Không cần khôi phục object graph hoặc trạng thái runtime của một process đã chạy.
- Muốn chia sẻ archive giữa nhiều JVM tương thích trên cùng môi trường.
- Không muốn đưa thêm quy trình resource checkpoint/restore vào ứng dụng.

Đây thường là bước tối ưu startup ít xâm lấn hơn. Có thể bắt đầu bằng CDS mặc định của JDK, sau đó đánh giá AppCDS nếu class ứng dụng còn tạo chi phí đáng kể.

## 18. Khi nào nên chọn CRaC?

CRaC phù hợp khi:

- Startup có nhiều bước ngoài class loading: framework initialization, object graph, cache, JIT warm-up hoặc chuẩn bị runtime.
- Cần đưa instance tới trạng thái sẵn sàng nhanh trong môi trường scale-out.
- Có thể tạo môi trường checkpoint/restore tương thích và kiểm soát được.
- Ứng dụng có thể quiesce/drain công việc và quản lý resource lifecycle.
- Có thể refresh dependency, credential, DNS và cache sau restore.
- Tổ chức có thể bảo vệ checkpoint image như artifact nhạy cảm.

CRaC không phải lựa chọn tốt nếu ứng dụng giữ nhiều resource không thể tái tạo, có transaction dài không thể drain, phụ thuộc native library không hỗ trợ hoặc môi trường restore không kiểm soát được. Cần thử nghiệm sớm với dependency thực tế trước khi đưa vào production.

## 19. Khi nào nên dùng cả hai?

Kết hợp có thể hợp lý nếu:

- AppCDS giúp giảm thời gian khởi chạy checkpoint builder hoặc cold-start fallback.
- CRaC giúp giảm thời gian từ restore tới readiness bằng cách giữ trạng thái đã warm-up.
- JDK/runtime cụ thể hỗ trợ workflow kết hợp.
- Đo benchmark chứng minh lợi ích tổng thể lớn hơn chi phí tạo và quản lý cả hai artifact.

Không nên kết hợp chỉ vì cả hai đều là tính năng startup. Thêm archive và checkpoint làm tăng số artifact, compatibility metadata và pipeline stages. Nếu AppCDS không cải thiện đáng kể builder time hoặc fallback path, có thể không cần duy trì nó.

## 20. Thiết kế benchmark công bằng

Để so sánh, dùng cùng:

- Application build, dependency versions và runtime image.
- CPU/memory limit và host class.
- Database/broker/API dependency và network conditions.
- Warm-up request profile và dữ liệu test.
- Readiness criteria và smoke workload.
- Số lần lặp, thời điểm đo và percentile.

Các cấu hình nên đo:

| Cấu hình | Cách chạy | Điều đo được |
| --- | --- | --- |
| Baseline | JVM cold start, không AppCDS/CRaC | Startup baseline. |
| CDS/AppCDS | JVM cold start với archive | Lợi ích class sharing. |
| CRaC | Restore process checkpoint | Lợi ích khôi phục process đã warm-up. |
| CDS + CRaC | Tạo checkpoint từ JVM đã dùng archive, nếu được hỗ trợ | Lợi ích tổng thể và chi phí thêm của archive. |

Đo riêng:

- Process start/restore time.
- Thời gian tới `afterRestore` complete.
- Thời gian reconnect dependency.
- Thời gian tới readiness.
- Thời gian request đầu tiên thành công.
- CPU, RSS, heap và memory footprint.
- Error rate và latency p50/p95/p99 sau khi traffic mở.
- Kích thước archive/checkpoint và thời gian tạo/transfer.

Một cấu hình có thể restore process rất nhanh nhưng mất nhiều thời gian reconnect database. Vì vậy, tiêu chí chính cho user experience thường là restore-to-ready và request latency, không chỉ thời gian JVM process xuất hiện.

## 21. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| AppCDS lưu toàn bộ heap ứng dụng | AppCDS lưu class data và một số archived object đủ điều kiện; không phải heap snapshot tổng quát. |
| CDS giữ Spring bean đã khởi tạo | JVM mới vẫn chạy Spring startup và tạo bean/context mới. |
| CRaC chỉ là AppCDS nâng cao | CRaC checkpoint trạng thái process, gồm nhiều trạng thái runtime/ứng dụng hơn class archive. |
| CRaC giữ mọi socket sống | Socket/resource bên ngoài có thể stale hoặc không hợp lệ; cần chuẩn bị và reconnect. |
| CDS và CRaC dùng chung một loại file | CDS dùng archive class data (thường `.jsa`); CRaC dùng process checkpoint image theo runtime/platform. |
| Checkpoint CRaC có thể dùng chung cho mọi JVM | Checkpoint gắn với process và môi trường tương thích cụ thể. |
| Checksum đúng chứng minh restore được | Checksum chỉ kiểm tra integrity; cần restore test. |
| CRaC luôn nhanh hơn AppCDS | Phụ thuộc startup bottleneck, resource reconnect và chi phí pipeline. |
| Kết hợp cả hai luôn cộng dồn lợi ích | Cần benchmark; AppCDS có thể chủ yếu giúp checkpoint builder hoặc cold-start fallback. |

## 22. Kiểm thử CDS/AppCDS

Test AppCDS nên xác nhận archive thực sự được sử dụng và không làm thay đổi behavior:

1. Tạo archive từ đúng application build và runtime.
2. Chạy JVM mới với `-Xshare:auto` hoặc chế độ được chọn.
3. Bật `-Xlog:cds` để quan sát archive mapping/loading.
4. Xác nhận classpath/module path tương thích.
5. Chạy startup smoke test và workload đại diện.
6. Đo startup time và memory so với baseline.
7. Thử archive không tương thích để xác nhận fallback/error behavior theo `-Xshare` mode.
8. Thử khi dependency/JAR thay đổi để xác định archive có bị bỏ qua hoặc từ chối.

Không chỉ nhìn thấy file `.jsa` là kết luận JVM đã sử dụng archive. Đọc CDS log và kiểm tra kết quả runtime.

## 23. Kiểm thử CRaC

Test CRaC cần xác nhận process state và resource lifecycle:

1. Start ứng dụng bằng JDK/CRaC runtime tương thích.
2. Chạy warm-up workload.
3. Kiểm tra cache/JIT/readiness theo tiêu chí.
4. Gọi `beforeCheckpoint` qua quy trình checkpoint thật và drain worker/transaction.
5. Tạo checkpoint image.
6. Thay đổi dependency trong khoảng checkpoint: DNS, database, broker hoặc credential.
7. Restore process trong môi trường tương thích.
8. Xác nhận `afterRestore` refresh/recreate resource.
9. Kiểm tra readiness và smoke test nghiệp vụ.
10. Đo restore-to-ready và kiểm tra dữ liệu không bị stale/duplicate.

Unit test gọi callback trực tiếp không thay thế test checkpoint/restore thật trên JDK, kernel, CRIU/container runtime mục tiêu.

## 24. Kiểm thử workflow kết hợp

Nếu dùng CDS/AppCDS và CRaC cùng nhau:

1. Build application artifact và tạo AppCDS archive.
2. Xác nhận JVM checkpoint builder thực sự map archive.
3. Chạy warm-up profile.
4. Tạo CRaC checkpoint.
5. Restore bằng runtime image và cấu hình đã pin.
6. Xác nhận callback CRaC và dependency recovery.
7. Đo restore-to-ready.
8. So sánh với cấu hình CRaC không AppCDS và AppCDS không CRaC.
9. Kiểm tra fallback cold start nếu checkpoint không thể sử dụng.
10. Ghi manifest liên kết JAR, AppCDS archive, runtime image và CRaC checkpoint.

Nếu archive AppCDS không còn phù hợp sau khi JAR/dependency thay đổi, phải tạo lại archive và checkpoint từ cùng một build. Không trộn archive class của build mới với process checkpoint của build cũ.

## 25. Bảo mật và vòng đời artifact

CDS/AppCDS archive và CRaC checkpoint đều cần integrity/provenance, nhưng mức nhạy cảm khác nhau.

Với CDS/AppCDS:

- Kiểm soát nguồn tạo archive và runtime version.
- Gắn archive với application build/classpath.
- Xác minh checksum/signature nếu lưu trong artifact registry.
- Không dùng archive từ nguồn không tin cậy.

Với CRaC:

- Giả định checkpoint có thể chứa secret và dữ liệu người dùng trong memory.
- Mã hóa khi lưu/truyền và giới hạn quyền đọc/restore.
- Không đính kèm raw image vào ticket/chat thông thường.
- Dùng retention và cleanup có reference/lease để tránh xóa ảnh đang restore.
- Refresh credential và cache nhạy cảm sau restore.

Không đưa secret vào manifest của cả hai artifact. Manifest chỉ lưu version, checksum, build identity và metadata cần thiết.

## 26. Checklist quyết định

- [ ] Đã xác định bottleneck startup là class loading, framework initialization, warm-up hay dependency reconnect.
- [ ] Nếu chủ yếu là class loading, đã benchmark CDS/AppCDS trước khi triển khai CRaC.
- [ ] Hiểu AppCDS không lưu toàn bộ heap hoặc trạng thái Spring bean.
- [ ] Hiểu CRaC checkpoint lưu process state rộng hơn nhưng không bảo đảm dependency bên ngoài còn hợp lệ.
- [ ] Đã pin JDK vendor/version/build và application dependency.
- [ ] Với AppCDS, archive được tạo từ đúng classpath/module path và được xác nhận qua CDS log.
- [ ] Với CRaC, có warm-up profile, resource callbacks và readiness gate.
- [ ] Đã xác định resource nào đóng trước checkpoint và tạo lại sau restore.
- [ ] Cache/credential/endpoint có freshness policy sau restore.
- [ ] Đã kiểm tra compatibility của archive/checkpoint với runtime đích.
- [ ] Đã restore-test CRaC thật, không chỉ gọi callback thủ công.
- [ ] Nếu kết hợp, đã benchmark cấu hình AppCDS-only, CRaC-only và combined.
- [ ] Manifest liên kết đúng build, archive, runtime image và checkpoint.
- [ ] Artifact được bảo vệ theo mức nhạy cảm; đặc biệt checkpoint có thể chứa dữ liệu heap.

## 27. Kết luận

CDS/AppCDS và CRaC tối ưu startup ở hai phạm vi khác nhau. CDS/AppCDS lưu class data và một số archived object đủ điều kiện để JVM mới nạp class hiệu quả hơn; nó không khôi phục heap ứng dụng, thread, Spring bean graph hay connection pool của một lần chạy trước. CRaC checkpoint một tiến trình đã chạy, có thể giữ trạng thái heap/runtime và warm-up, nhưng cần chuẩn bị và phục hồi resource vì database, DNS, broker, credential và các dependency khác vẫn thay đổi độc lập.

Hãy chọn CDS/AppCDS khi bottleneck chủ yếu là class loading và muốn giữ startup flow thông thường. Chọn CRaC khi cần khôi phục trạng thái runtime đã warm-up và có thể quản lý checkpoint/restore lifecycle. Có thể kết hợp nếu JDK hỗ trợ và benchmark chứng minh lợi ích, nhưng phải liên kết chính xác build, archive và checkpoint. Đánh giá bằng thời gian tới readiness và request đầu tiên thành công, không chỉ bằng thời gian process khởi động.
