# Khởi động chậm và giai đoạn làm nóng của ứng dụng Java

Trong một ứng dụng Java chạy lâu dài, thời gian từ lúc khởi chạy tiến trình đến khi ứng dụng sẵn sàng phục vụ thường không phải là toàn bộ câu chuyện về hiệu năng khởi động. Sau khi ứng dụng báo sẵn sàng, những yêu cầu đầu tiên vẫn có thể chậm hơn đáng kể so với các yêu cầu tiếp theo. JVM còn tải lớp, biên dịch mã thường chạy, tạo các cấu trúc nội bộ và ứng dụng tiếp tục khởi tạo bộ nhớ đệm hoặc kết nối đến dịch vụ bên ngoài. Khoảng thời gian này được gọi là **giai đoạn làm nóng** (*warm-up*).

Trong bối cảnh **CRaC (Coordinated Restore at Checkpoint)**, hai hiện tượng này đặc biệt quan trọng. CRaC cho phép tạo một checkpoint của tiến trình Java đang chạy và khôi phục tiến trình từ checkpoint đó. Nếu checkpoint được tạo sau khi ứng dụng đã khởi tạo và làm nóng đúng cách, lần khôi phục có thể tái sử dụng phần lớn trạng thái đã chuẩn bị, nhờ đó giảm thời gian đưa ứng dụng vào trạng thái phục vụ. Muốn đạt được lợi ích này, cần hiểu ứng dụng đang tốn thời gian ở đâu, chọn đúng thời điểm checkpoint và xử lý những tài nguyên không thể tiếp tục sử dụng sau khi khôi phục.

## 1. Phân biệt khởi động và làm nóng

Hai khái niệm có liên quan nhưng mô tả những giai đoạn khác nhau.

**Khởi động (*startup*)** là quá trình bắt đầu một tiến trình Java mới và đưa ứng dụng đến trạng thái có thể nhận công việc. Quá trình này có thể bao gồm khởi tạo JVM, nạp lớp, tạo đối tượng, khởi tạo framework, đọc cấu hình, mở kết nối và chạy các bước kiểm tra sẵn sàng.

**Làm nóng (*warm-up*)** là quá trình ứng dụng dần đạt hiệu năng ổn định sau khi bắt đầu chạy. JVM quan sát những đoạn mã được thực thi thường xuyên để biên dịch chúng bằng JIT compiler; ứng dụng cũng có thể nạp dữ liệu vào cache, tạo metadata, thiết lập connection pool hoặc hoàn tất khởi tạo lười (*lazy initialization*).

Một ứng dụng có thể hoàn thành startup và vượt qua readiness probe trong khi vẫn đang warm-up. Vì vậy, trạng thái “ready” không nhất thiết đồng nghĩa với trạng thái “đã đạt thông lượng và độ trễ ổn định”. Một hệ thống có thể có thời gian startup ngắn nhưng vẫn có độ trễ cao ở các request đầu tiên.

| Khía cạnh | Startup | Warm-up |
|---|---|---|
| Thời điểm | Từ lúc tiến trình bắt đầu đến khi ứng dụng sẵn sàng | Sau khi tiến trình bắt đầu; có thể tiếp tục sau readiness |
| Công việc thường gặp | Khởi tạo JVM, nạp lớp, dựng framework, đọc cấu hình | JIT biên dịch mã nóng, đi qua các luồng nghiệp vụ, nạp cache |
| Biểu hiện | Thời gian đến readiness cao | Request đầu chậm, CPU tăng, throughput ban đầu thấp |
| Mục tiêu | Đưa ứng dụng vào trạng thái có thể phục vụ | Đưa hiệu năng đến mức ổn định và dự đoán được |

Một dòng thời gian điển hình:

```text
Tiến trình bắt đầu
       |
       v
Khởi tạo JVM và nạp lớp
       |
       v
Khởi tạo framework, cấu hình, tài nguyên
       |
       v
Ứng dụng báo sẵn sàng  <---- startup kết thúc theo readiness
       |
       v
Các request đầu tiên, JIT và cache tiếp tục làm nóng
       |
       v
Độ trễ và throughput tiến gần trạng thái ổn định
```

Ranh giới giữa hai giai đoạn không tuyệt đối. Ví dụ, nếu ứng dụng chủ động thực hiện warm-up trước khi báo readiness, một phần hoặc toàn bộ warm-up sẽ nằm trong thời gian startup được đo. Khi so sánh hai cách triển khai, cần thống nhất định nghĩa điểm bắt đầu và điểm kết thúc.

## 2. Vì sao ứng dụng Java có thể khởi động chậm?

Thời gian khởi động thường là tổng của nhiều công việc nhỏ. Tác nhân lớn nhất phụ thuộc vào ứng dụng, framework, thư viện, môi trường chạy và cách triển khai.

### 2.1. Công việc khởi tạo của JVM

Trước khi mã ứng dụng thực sự xử lý nghiệp vụ, JVM phải thiết lập môi trường thực thi. Các công việc có thể bao gồm:

- Khởi tạo các cấu trúc quản lý heap, garbage collector, thread và runtime.
- Nạp, xác minh (*verification*), liên kết (*linking*) và khởi tạo (*initialization*) các lớp cần thiết.
- Tạo class loader và nạp metadata của lớp vào vùng nhớ tương ứng.
- Thiết lập các thành phần phục vụ biên dịch JIT và quản lý mã đã biên dịch.
- Khởi tạo các thư viện chuẩn hoặc thư viện native mà ứng dụng sử dụng.

Không phải mọi lớp đều được nạp ngay khi JVM bắt đầu. Nhiều lớp chỉ được nạp khi một đường đi thực thi cần đến chúng. Do đó, một số chi phí nạp lớp xuất hiện ở request đầu tiên thay vì xuất hiện hoàn toàn trong startup.

### 2.2. Khởi tạo framework và ứng dụng

Các framework Java thường thực hiện nhiều công việc để xây dựng ứng dụng trước khi phục vụ request. Chẳng hạn, một ứng dụng Spring có thể quét component, tạo application context, phân giải dependency, tạo proxy, cấu hình web server, đăng ký converter và khởi tạo bean. Ứng dụng dùng ORM có thể cần đọc mapping, xây dựng metadata, chuẩn bị câu lệnh hoặc khởi tạo các thành phần liên quan đến persistence.

Những thư viện khác cũng có thể thực hiện quét classpath, đọc annotation, nạp schema, biên dịch biểu thức, tạo serializer hoặc xây dựng registry. Một số thao tác tốn thời gian do số lượng lớp và dependency lớn; một số khác tốn thời gian vì thực hiện I/O hoặc chờ dịch vụ bên ngoài.

### 2.3. Đọc cấu hình và phụ thuộc vào dịch vụ bên ngoài

Ứng dụng thường đọc file cấu hình, biến môi trường, secret, chứng thư và thông tin kết nối. Sau đó, ứng dụng có thể kết nối đến cơ sở dữ liệu, message broker, cache, dịch vụ định danh hoặc hệ thống cấu hình tập trung.

Thời gian chờ mạng, DNS, TLS handshake, xác thực và retry có thể làm startup kéo dài. Nếu một dependency tạm thời không phản hồi, ứng dụng có thể chậm hơn nhiều so với khi chạy trong môi trường phát triển. Việc đo startup chỉ trên máy cục bộ có thể bỏ sót các chi phí này.

### 2.4. Khởi tạo lười

Để giảm thời gian startup, ứng dụng hoặc framework có thể trì hoãn một số công việc cho đến lần đầu sử dụng. Cách này giúp tiến trình báo sẵn sàng sớm hơn, nhưng chi phí được chuyển sang request đầu tiên.

Ví dụ, lần đầu gọi một chức năng có thể cần tạo serializer, tải metadata, mở kết nối, nạp một lớp ít dùng hoặc khởi tạo một bean. Nếu chức năng này nằm trên luồng request quan trọng, người dùng sẽ cảm nhận được độ trễ dù readiness probe đã thành công.

## 3. Vì sao request đầu tiên thường chậm?

### 3.1. JIT compilation và mã nóng

Java thường biên dịch bytecode sang mã máy trong lúc chương trình chạy. JIT compiler theo dõi hành vi thực thi, chẳng hạn phương thức nào được gọi thường xuyên và nhánh nào thường được sử dụng. Khi một phương thức trở thành “nóng”, JVM có thể biên dịch nó ở mức tối ưu hóa cao hơn.

Ở giai đoạn đầu, một số đoạn mã có thể chạy bằng interpreter hoặc mã được biên dịch ở mức tối ưu hóa thấp. Khi JVM thu thập đủ thông tin, nó có thể biên dịch lại để cải thiện hiệu năng. Vì vậy, những request đầu tiên vừa thực hiện công việc nghiệp vụ vừa tạo dữ liệu quan sát cho JIT compiler.

Quá trình này thường được gọi là **JVM warm-up**. Nó không có một thời lượng cố định: ứng dụng nhỏ có thể ổn định nhanh, trong khi ứng dụng có nhiều đường đi nghiệp vụ hoặc tải biến động có thể cần thời gian lâu hơn. Những đường đi chưa từng được thực thi cũng chưa chắc đã được làm nóng.

### 3.2. Cache và dữ liệu được tạo khi chạy

Ứng dụng thường có các cache ở nhiều lớp:

- Cache trong ứng dụng, ví dụ dữ liệu tham chiếu, kết quả tính toán hoặc metadata.
- Cache của thư viện, framework, ORM và serializer.
- Cache của hệ điều hành, filesystem hoặc DNS resolver.
- Connection pool và các cấu trúc giữ trạng thái phiên làm việc.

Ở lần chạy đầu, cache có thể rỗng. Ứng dụng phải đọc dữ liệu từ nguồn gốc, phân tích, chuyển đổi và lưu lại. Các request tiếp theo có thể nhanh hơn vì dùng lại kết quả đã tạo.

Không phải cache nào cũng có thể hoặc nên được giữ trong checkpoint. Cache chứa dữ liệu dùng chung, có thể tái tạo và không phụ thuộc vào một instance thường phù hợp hơn. Cache chứa thông tin nhạy cảm, dữ liệu theo người dùng hoặc dữ liệu có thời hạn cần được xem xét riêng.

### 3.3. Kết nối và tài nguyên được khởi tạo ở lần dùng đầu

Một connection pool có thể chỉ tạo kết nối khi có request đầu tiên. TLS session, client HTTP, channel đến message broker hoặc client đến dịch vụ khác cũng có thể được tạo lười. Vì vậy, request đầu tiên phải trả chi phí thiết lập tài nguyên trước khi hoàn thành công việc chính.

### 3.4. Tải và hình dạng của workload

Warm-up phụ thuộc vào các đường đi thực thi được chạy. Gửi lặp lại một endpoint đơn giản không đảm bảo các endpoint quan trọng khác đã được làm nóng. Một ứng dụng có nhiều loại request, payload hoặc nhánh xử lý cần một workload đại diện để khởi động các đường đi có ý nghĩa.

## 4. Tác động đến hệ thống

Startup chậm làm tăng thời gian triển khai phiên bản mới, mở rộng số replica hoặc khôi phục dịch vụ sau sự cố. Trong môi trường autoscaling hay serverless, thời gian này có thể trực tiếp làm tăng thời gian người dùng phải chờ một instance mới.

Warm-up chậm tạo ra một giai đoạn mà độ trễ và thông lượng chưa ổn định. Các request đầu có thể làm tăng p95 hoặc p99 latency; CPU có thể tăng do JIT compilation và khởi tạo cache. Nếu hệ thống nhận tải lớn ngay sau khi instance được thêm vào, warm-up có thể diễn ra đồng thời với tải thực, làm giảm năng lực phục vụ đúng lúc hệ thống cần mở rộng.

Do đó, chỉ đo thời gian từ khi chạy lệnh `java` đến khi cổng HTTP mở là chưa đủ. Cần đo cả thời gian đến readiness, độ trễ request đầu, thời gian đạt thông lượng ổn định và tài nguyên tiêu thụ trong quá trình đó.

## 5. Đo lường startup và warm-up

Trước khi tối ưu, hãy xác định phần thời gian đang bị tiêu tốn. Một bộ đo cơ bản nên phân biệt các mốc sau:

| Chỉ số | Ý nghĩa |
|---|---|
| Process start time | Thời điểm tiến trình JVM bắt đầu |
| Application ready time | Thời điểm ứng dụng vượt qua readiness check |
| First-request latency | Độ trễ của request đầu tiên cho từng luồng nghiệp vụ quan trọng |
| Warm-up duration | Thời gian từ khi bắt đầu chạy workload đến khi hiệu năng ổn định theo tiêu chí đã chọn |
| Steady-state latency | Độ trễ khi ứng dụng đã ổn định, nên xem p50, p95 và p99 |
| Throughput | Số request hoặc tác vụ hoàn thành trong một đơn vị thời gian |
| CPU và GC | Chi phí CPU, hoạt động garbage collection và mức sử dụng bộ nhớ trong từng giai đoạn |

Có thể ghi timestamp ở các mốc khởi tạo quan trọng trong ứng dụng, đồng thời dùng log startup của framework và readiness probe để xác định thời điểm sẵn sàng. JDK Flight Recorder (JFR), công cụ quan sát JVM và profiler có thể giúp tìm hoạt động nạp lớp, biên dịch JIT, allocation, GC, thread contention và I/O đáng kể.

Khi đo, hãy dùng cùng phiên bản JDK, cấu hình heap, giới hạn CPU/bộ nhớ, image, cấu hình ứng dụng và môi trường mạng. Chạy nhiều lần từ trạng thái lạnh để tránh nhầm cache của hệ điều hành hoặc dịch vụ bên ngoài với cải thiện thật sự. Dùng workload đại diện, tách kết quả startup khỏi kết quả steady-state và ghi lại cả độ trễ lẫn thông lượng.

Một phép đo hữu ích nên trả lời được ba câu hỏi:

1. Ứng dụng mất bao lâu để sẵn sàng nhận request?
2. Những request hoặc tác vụ nào còn chậm trong giai đoạn đầu?
3. Sau bao lâu, với mức tải nào, hiệu năng đạt ngưỡng ổn định đã định?

“Ổn định” cần được định nghĩa bằng tiêu chí đo được, ví dụ p95 latency nằm trong một khoảng mục tiêu và throughput không còn tăng đáng kể qua các cửa sổ đo liên tiếp. Không nên chọn một số lần lặp cố định rồi mặc định rằng mọi ứng dụng đều đã warm-up.

## 6. Các cách giảm startup và warm-up khi chưa dùng CRaC

CRaC là một lựa chọn trong chiến lược tối ưu, nhưng vẫn nên hiểu các biện pháp thông thường vì chúng có thể kết hợp với nhau.

**Giảm công việc khởi tạo không cần thiết.** Loại bỏ dependency không dùng, hạn chế quét classpath quá rộng, tránh khởi tạo client hoặc bean không cần thiết cho đường đi phục vụ chính. Kiểm tra các bước gọi mạng đồng bộ trong startup và đặt timeout phù hợp.

**Chọn thời điểm khởi tạo có chủ đích.** Khởi tạo sớm giúp tránh độ trễ ở request đầu nhưng làm startup dài hơn. Khởi tạo lười giúp ứng dụng sẵn sàng sớm hơn nhưng có thể chuyển chi phí sang người dùng đầu tiên. Quyết định nên dựa trên yêu cầu latency và readiness thực tế.

**Làm nóng bằng workload đại diện.** Gọi các endpoint hoặc tác vụ quan trọng với dữ liệu thử phù hợp để kích hoạt lớp, đường đi nghiệp vụ và JIT compilation cần thiết. Không nên chỉ lặp lại một endpoint không đại diện cho tải thực tế.

**Xem xét Class Data Sharing (CDS/AppCDS).** CDS có thể giúp giảm một phần chi phí nạp lớp bằng cách chia sẻ dữ liệu lớp đã chuẩn bị. Nó không lưu toàn bộ trạng thái đang chạy của ứng dụng và không thay thế việc xử lý warm-up của các đường đi nghiệp vụ.

**Đánh giá biên dịch trước hoặc native image khi phù hợp.** Các giải pháp AOT hoặc native image thay đổi cách ứng dụng được biên dịch và chạy, có thể cải thiện startup trong một số trường hợp. Chúng có mô hình tương thích, tối ưu hóa và vận hành khác với JVM thông thường; cần đo trên ứng dụng thực tế.

## 7. CRaC giải quyết startup và warm-up như thế nào?

CRaC là viết tắt của **Coordinated Restore at Checkpoint**. Ý tưởng chính là đưa ứng dụng đến một trạng thái đã được chuẩn bị, tạo checkpoint của tiến trình tại trạng thái đó, rồi dùng checkpoint để khôi phục một tiến trình mới.

Với cách khởi động thông thường, mỗi replica mới phải chạy lại nhiều bước: khởi tạo JVM, nạp lớp, tạo application context, thực hiện một phần warm-up và thiết lập tài nguyên. Với CRaC, một tiến trình có thể thực hiện các bước tốn thời gian trước, chạy workload warm-up, sau đó tạo checkpoint. Khi khôi phục, tiến trình tiếp tục từ trạng thái đã lưu và thực hiện các callback phục hồi tài nguyên cần thiết.

```text
Chuẩn bị checkpoint
  Khởi chạy ứng dụng
        |
        v
  Khởi tạo framework và ứng dụng
        |
        v
  Chạy workload warm-up
        |
        v
  Chuẩn bị tài nguyên cho checkpoint
        |
        v
  Lưu checkpoint

Khởi động instance mới
  Khôi phục từ checkpoint
        |
        v
  Phục hồi tài nguyên và trạng thái phụ thuộc môi trường
        |
        v
  Kiểm tra sẵn sàng và phục vụ request
```

Checkpoint lưu trạng thái tiến trình tại một thời điểm. Vì vậy, các trạng thái trong bộ nhớ đã được tạo trước checkpoint có thể được tái sử dụng khi restore, tùy vào JDK CRaC, nền tảng và cấu hình triển khai. Điều này có thể tránh lặp lại nhiều công việc khởi tạo và warm-up. Mức cải thiện thực tế phải được đo trên đúng ứng dụng và môi trường mục tiêu.

CRaC không làm cho mọi chi phí biến mất. Hệ thống vẫn phải khôi phục tiến trình, hoàn tất callback, kết nối lại dịch vụ, xác thực trạng thái, kiểm tra readiness và xử lý những dữ liệu đã thay đổi kể từ lúc checkpoint. Nếu checkpoint được tạo quá sớm, trước khi các đường đi quan trọng được làm nóng, lợi ích warm-up sẽ hạn chế.

## 8. Chọn đúng thời điểm tạo checkpoint

Checkpoint nên đại diện cho trạng thái nền ổn định mà nhiều instance có thể dùng chung. Thông thường, tiến trình cần hoàn thành những bước sau trước khi checkpoint:

1. Đã đọc cấu hình nền và khởi tạo các thành phần ứng dụng cần thiết.
2. Đã tạo những đối tượng, metadata và cache có thể dùng chung an toàn giữa các instance.
3. Đã chạy workload warm-up đại diện cho các đường đi quan trọng.
4. Đã đạt tiêu chí hiệu năng ổn định đã định nghĩa, nếu mục tiêu là lưu cả trạng thái JIT và cache đã làm nóng.
5. Không còn request hoặc giao dịch đang xử lý dở.
6. Đã chuẩn bị các tài nguyên cần đóng, tạm dừng hoặc tái tạo trong vòng đời checkpoint/restore.

Không nên checkpoint khi ứng dụng đang xử lý request của người dùng, đang ghi dữ liệu chưa hoàn tất hoặc đang giữ trạng thái riêng của một phiên làm việc. Một checkpoint được tạo từ trạng thái không nhất quán có thể khiến mọi instance restore từ đó cùng mang theo lỗi.

Warm-up cũng cần tránh tạo dữ liệu nghiệp vụ thật. Hãy dùng dữ liệu thử hoặc thao tác an toàn, có thể lặp lại và không gây side effect. Nếu một request warm-up gửi email, tạo đơn hàng hoặc ghi dữ liệu thật, checkpoint có thể được tạo sau khi side effect đã xảy ra và mỗi lần chạy quy trình chuẩn bị có thể lặp lại side effect đó.

## 9. Quản lý tài nguyên bằng CRaC Resource

Một tiến trình đang chạy có thể giữ các tài nguyên gắn với môi trường cụ thể: socket, kết nối cơ sở dữ liệu, file descriptor, thread nền, lock, timer, client TLS hoặc kết nối đến message broker. Sau khi tiến trình được checkpoint và restore, một số tài nguyên có thể đã hết hạn, không còn hợp lệ hoặc không thể tiếp tục dùng trong môi trường mới.

CRaC cung cấp API `org.crac.Resource` để ứng dụng phối hợp vòng đời của những tài nguyên đó. Một resource triển khai hai callback:

- `beforeCheckpoint(...)`: chuẩn bị tài nguyên trước khi lưu checkpoint. Tùy loại tài nguyên, ứng dụng có thể dừng nhận công việc mới, hoàn tất công việc đang chạy, đóng kết nối hoặc giải phóng lock.
- `afterRestore(...)`: khôi phục hoặc tạo lại tài nguyên sau khi tiến trình được restore. Ví dụ, tạo connection pool mới, mở lại file hoặc khởi động lại worker nền.

Ví dụ dưới đây minh họa một resource quản lý một đối tượng có thể đóng và tạo lại. `createPool()` và `close()` đại diện cho logic cụ thể của thư viện connection pool mà ứng dụng đang dùng:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class PoolResource implements Resource {
    private final PoolFactory poolFactory;
    private AutoCloseable pool;

    public PoolResource(PoolFactory poolFactory) throws Exception {
        this.poolFactory = poolFactory;
        this.pool = poolFactory.createPool();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        if (pool != null) {
            pool.close();
            pool = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        pool = poolFactory.createPool();
    }

    public interface PoolFactory {
        AutoCloseable createPool() throws Exception;
    }
}
```

Đây là ví dụ khung để thể hiện vòng đời. Trong ứng dụng thực tế, cần bảo đảm mọi thành phần đang dùng pool đã ngừng sử dụng nó trước khi đóng, và các thành phần phụ thuộc chỉ nhận pool mới sau khi restore hoàn tất. Cách tích hợp cụ thể phụ thuộc vào framework và thư viện kết nối.

Resource có thể được đăng ký với global context hoặc một context phù hợp với cấu trúc ứng dụng. Hãy đọc tài liệu của bản JDK CRaC đang dùng để xác nhận API, thứ tự callback và các giới hạn nền tảng. Nếu một thư viện đã có tích hợp CRaC, ưu tiên sử dụng tích hợp được hỗ trợ thay vì tự quản lý cùng một tài nguyên hai lần.

## 10. Những trạng thái cần kiểm tra trước và sau restore

Không phải mọi đối tượng Java trong heap đều có thể được dùng vô thời hạn sau restore. Hãy rà soát các nhóm trạng thái sau:

| Nhóm trạng thái | Vấn đề có thể gặp | Cách xử lý thường dùng |
|---|---|---|
| Socket và kết nối mạng | Kết nối đã bị peer đóng, địa chỉ hoặc route thay đổi | Đóng trước checkpoint; tạo kết nối mới sau restore |
| Database và connection pool | Connection cũ hết timeout hoặc server đã ngắt | Đóng pool cũ, tạo pool mới và kiểm tra kết nối |
| HTTP/TLS client | Socket, session hoặc chứng thư không còn phù hợp | Tái tạo client hoặc làm mới phần tài nguyên phụ thuộc môi trường |
| DNS và địa chỉ dịch vụ | Kết quả phân giải cũ không còn đúng | Phân giải lại theo chính sách DNS của ứng dụng |
| File và file descriptor | Mount, đường dẫn hoặc trạng thái file thay đổi | Đóng/mở lại file và xác minh quyền truy cập |
| Thread và executor | Worker bị dừng, đang giữ lock hoặc không ở trạng thái hợp lệ | Dừng có kiểm soát trước checkpoint; khởi động lại sau restore |
| Timer và tác vụ định kỳ | Lịch chạy dựa trên thời gian trước checkpoint | Tính lại lịch và tránh chạy bù ngoài ý muốn |
| Token, secret và chứng thư | Hết hạn hoặc bị xoay vòng sau checkpoint | Lấy thông tin mới từ nguồn quản lý secret |
| Cache và dữ liệu cấu hình | Dữ liệu đã lỗi thời hoặc gắn với một instance | Làm mới, vô hiệu hóa hoặc xác nhận thời hạn sau restore |

Một nguyên tắc hữu ích là phân biệt **trạng thái có thể chia sẻ** với **trạng thái phải thuộc riêng từng instance**. Metadata bất biến hoặc cache dùng chung có thể phù hợp để đưa vào checkpoint. Địa chỉ IP, cổng được cấp động, token ngắn hạn, ID instance và trạng thái của request đang chạy thường cần được thiết lập hoặc làm mới sau restore.

Các callback nên có tính lặp lại an toàn khi có thể. Nếu callback phục hồi thất bại, ứng dụng cần báo lỗi rõ ràng và không nhận traffic trước khi tài nguyên thiết yếu sẵn sàng. Readiness probe nên phản ánh trạng thái thực sau restore, thay vì chỉ kiểm tra rằng tiến trình đã tồn tại.

## 11. Quy trình triển khai CRaC ở mức khái quát

Quy trình chính xác phụ thuộc vào bản phân phối JDK có hỗ trợ CRaC, hệ điều hành, container runtime và nền tảng checkpoint/restore. Một quy trình thường có các bước sau:

**Bước 1: Chuẩn bị môi trường tương thích.** Chọn bản JDK CRaC và môi trường được hỗ trợ. Kiểm tra yêu cầu của hệ điều hành, kernel, cơ chế checkpoint/restore, quyền container, thư viện native và cách lưu trữ checkpoint. Checkpoint thường gắn chặt với môi trường tạo ra nó; không mặc định rằng một checkpoint có thể khôi phục trên bất kỳ máy hoặc image nào.

**Bước 2: Khởi chạy ứng dụng để tạo trạng thái nền.** Dùng đúng artifact, cấu hình và phiên bản dependency dự kiến khi triển khai. Tránh đưa dữ liệu riêng của một instance vào trạng thái nền.

**Bước 3: Chạy warm-up.** Gửi workload đại diện để kích hoạt các luồng nghiệp vụ quan trọng, JIT compilation, cache và khởi tạo lười cần thiết. Đo cho đến khi đạt tiêu chí ổn định.

**Bước 4: Chuẩn bị tài nguyên.** Đăng ký `Resource` cho tài nguyên cần phối hợp. Dừng nhận công việc mới, hoàn tất công việc đang chạy, đóng hoặc giải phóng tài nguyên không thể mang qua checkpoint.

**Bước 5: Tạo checkpoint.** Dùng cơ chế checkpoint được tài liệu của bản JDK và nền tảng triển khai chỉ định. Một số bản phân phối cung cấp tùy chọn JVM và lệnh chẩn đoán riêng; cú pháp và khả năng hỗ trợ có thể khác nhau giữa các bản.

**Bước 6: Khởi động bằng checkpoint và xác minh.** Khi restore, callback `afterRestore` cần tái tạo tài nguyên. Kiểm tra readiness, kết nối dịch vụ, log, metric và một số request đại diện trước khi đưa instance vào tải thực.

**Bước 7: Đo và so sánh.** So sánh với cold start thông thường trong cùng điều kiện. Đo thời gian restore đến readiness, request đầu, warm-up còn lại, throughput, p95/p99 latency, CPU và tỷ lệ lỗi. Nếu phần lớn thời gian vẫn nằm ở việc kết nối dịch vụ bên ngoài, CRaC có thể không cải thiện nhiều chỉ số đó.

## 12. So sánh CRaC với CDS và native image

Các kỹ thuật này cùng hướng đến giảm chi phí khởi động nhưng giải quyết vấn đề ở những lớp khác nhau.

| Kỹ thuật | Cách tiếp cận | Phần chi phí có thể giảm | Điểm cần lưu ý |
|---|---|---|---|
| CDS/AppCDS | Chia sẻ dữ liệu lớp đã chuẩn bị | Một phần công việc nạp và xử lý metadata lớp | Không lưu toàn bộ trạng thái ứng dụng đang chạy |
| CRaC | Lưu và khôi phục trạng thái tiến trình tại checkpoint | Có thể tái sử dụng trạng thái JVM và ứng dụng đã khởi tạo/làm nóng | Cần phối hợp tài nguyên và tương thích môi trường restore |
| GraalVM Native Image/AOT | Biên dịch trước thành executable native | Có thể giảm công việc khởi tạo JVM và phụ thuộc JIT lúc chạy | Có trade-off về tương thích, build, tối ưu hóa và mô hình runtime |

Không có lựa chọn tốt nhất cho mọi ứng dụng. Nếu startup chủ yếu bị chi phối bởi khởi tạo framework và warm-up, CRaC có thể đáng thử. Nếu chi phí nạp lớp chiếm phần lớn, CDS có thể hữu ích. Nếu yêu cầu startup cực nhanh và ứng dụng phù hợp với mô hình AOT, native image có thể là hướng khác. Cần đo trên workload và môi trường triển khai thật trước khi quyết định.

## 13. Các lỗi thiết kế thường gặp

**Tạo checkpoint trước khi warm-up có ý nghĩa.** Khi restore, ứng dụng vẫn phải nạp lớp hoặc biên dịch các đường đi chưa được chạy. Hãy dùng workload đại diện và đo hiệu năng sau restore.

**Giữ nguyên kết nối mạng cũ.** Một socket có thể không còn hợp lệ sau thời gian checkpoint hoặc trong môi trường restore. Hãy xử lý vòng đời kết nối qua callback và kiểm tra lỗi kết nối lại.

**Để worker nền chạy trong lúc checkpoint.** Worker có thể đang giữ lock, xử lý message hoặc cập nhật dữ liệu dở dang. Cần dừng nhận công việc mới và xác định cách hoàn tất hoặc đưa công việc về trạng thái có thể phục hồi.

**Đưa dữ liệu riêng của instance vào checkpoint.** Ví dụ, checkpoint chứa địa chỉ IP, token ngắn hạn hoặc ID instance của tiến trình tạo checkpoint. Khi nhiều replica dùng chung checkpoint, trạng thái đó có thể gây xung đột hoặc lỗi định tuyến. Hãy tạo lại dữ liệu riêng sau restore.

**Không cập nhật trạng thái hết hạn.** Token, chứng thư, DNS cache và dữ liệu cấu hình có thể thay đổi trong lúc checkpoint được lưu trữ. Callback restore cần làm mới những dữ liệu có thời hạn hoặc có thể thay đổi.

**Đánh dấu ready quá sớm.** Tiến trình có thể đã restore nhưng pool chưa tạo xong hoặc worker chưa chạy. Readiness phải chờ các tài nguyên thiết yếu sẵn sàng.

**So sánh benchmark không cùng điều kiện.** So sánh cold start trên máy nhàn rỗi với restore trong môi trường có CPU hoặc I/O khác nhau sẽ dẫn đến kết luận sai. Hãy kiểm soát cấu hình và đo nhiều lần.

**Xem checkpoint như artifact vô hại.** Trạng thái bộ nhớ có thể chứa secret, token, dữ liệu người dùng hoặc thông tin nội bộ. Hãy kiểm soát quyền đọc/ghi, nơi lưu trữ, thời hạn lưu và quy trình xóa checkpoint.

## 14. Checklist thiết kế cho một ứng dụng Java dùng CRaC

Trước khi đưa CRaC vào triển khai, nhóm phát triển có thể dùng các câu hỏi sau để rà soát thiết kế:

- [ ] Đã đo riêng startup, readiness, first-request latency và warm-up duration chưa?
- [ ] Workload chuẩn bị checkpoint có đại diện cho các đường đi quan trọng không?
- [ ] Đã xác định trạng thái nào an toàn để chia sẻ giữa các instance chưa?
- [ ] Đã liệt kê socket, pool, file, thread, timer, lock và tài nguyên phụ thuộc môi trường chưa?
- [ ] Mỗi tài nguyên cần thiết đã có cách đóng trước checkpoint và tạo lại sau restore chưa?
- [ ] Ứng dụng có ngăn request hoặc giao dịch đang chạy dở đi vào checkpoint không?
- [ ] Secret, token, chứng thư và dữ liệu có thời hạn có được làm mới khi cần không?
- [ ] Readiness chỉ thành công sau khi callback và tài nguyên thiết yếu đã hoàn tất chưa?
- [ ] Đã thử restore trong đúng image, kernel, JDK và cấu hình triển khai mục tiêu chưa?
- [ ] Đã đo tỷ lệ lỗi, latency, throughput, CPU và bộ nhớ sau restore chưa?
- [ ] Checkpoint có được bảo vệ như một artifact chứa trạng thái bộ nhớ nhạy cảm không?

## Kết luận

Khởi động chậm và warm-up chậm là hai nguồn độ trễ khác nhau. Startup chủ yếu phản ánh chi phí tạo tiến trình và khởi tạo ứng dụng; warm-up phản ánh quá trình JVM và ứng dụng đạt hiệu năng ổn định khi workload thực thi. Cần đo riêng hai giai đoạn để xác định đúng nguyên nhân.

CRaC có thể giảm đáng kể công việc lặp lại khi tạo instance mới bằng cách khôi phục một tiến trình đã được khởi tạo và làm nóng. Hiệu quả phụ thuộc vào chất lượng checkpoint, workload warm-up và khả năng quản lý tài nguyên. Khi ứng dụng đóng/mở đúng các tài nguyên, làm mới trạng thái phụ thuộc môi trường và chỉ báo sẵn sàng sau khi restore hoàn tất, CRaC có thể giúp rút ngắn thời gian đưa ứng dụng Java vào phục vụ mà vẫn giữ được mô hình chạy trên JVM.
