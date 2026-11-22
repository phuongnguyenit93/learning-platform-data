# Journal NIO, ASYNCIO và yêu cầu của môi trường chạy

> **Chương:** Lưu trữ Artemis  
> **Phạm vi:** Apache ActiveMQ **Artemis 2.57.x** với *file journal* dùng lưu message bền vững. Bài tập trung vào hai cơ chế I/O **NIO** và **ASYNCIO**, yêu cầu của Linux/`libaio`/filesystem/container, cách cấu hình, nhận biết fallback và kiểm chứng sau restart. Không nhầm với KahaDB của ActiveMQ Classic hoặc giao thức kết nối Java/JMS.

## 1. Câu hỏi cần trả lời trước khi chọn journal type

Trong một broker Artemis, ứng dụng gửi `DeliveryMode.PERSISTENT` không có nghĩa tất cả byte đã an toàn trước mọi sự cố. Cần biết broker đang ghi bằng cơ chế nào, xác nhận ghi ở mốc nào và thiết bị lưu trữ có thực sự đáp ứng lệnh đồng bộ dữ liệu hay không.

Hãy tách ba quyết định:

1. **Backend journal:** `NIO` hay `ASYNCIO` quyết định cơ chế I/O ghi file journal.
2. **Chính sách đồng bộ:** `journal-sync-transactional`, `journal-sync-non-transactional` và `journal-datasync` quyết định mốc chờ ghi bền vững; không nên giảm để chỉ lấy throughput.
3. **Điều kiện runtime:** kernel, thư viện native, filesystem, volume mount, quyền ghi, I/O quota và hành vi của ổ đĩa quyết định cơ chế đã chọn có chạy được và đáng tin cậy hay không.

**Điểm mấu chốt:** `<journal-type>ASYNCIO</journal-type>` là **ý định cấu hình**, không phải bằng chứng broker thực sự dùng AIO. Nếu môi trường thiếu điều kiện, Artemis có thể **fallback sang NIO**. Phải xem **startup log**, không chỉ đọc `broker.xml`.

## 2. Journal của Artemis ghi gì và không ghi gì?

File journal của Artemis là cấu trúc **append-only**: broker bổ sung record cho việc thêm, cập nhật, acknowledge/xóa message và ranh giới transaction. File được chuẩn bị trước với kích thước cố định; record cũ không còn sống có thể được thu hồi hoặc compaction để tái sử dụng dung lượng.

```text
Producer/JMS                                 Artemis broker
       |                                          |
       | send PERSISTENT / commit                 |
       v                                          v
  ┌──────────────┐    append transaction     ┌───────────────┐
  │ Protocol/    │ ────────────────────────▶ │ Message       │
  │ session      │                           │ journal       │
  └──────────────┘                           └──────┬────────┘
                                                  │
                                  ┌───────────────┴───────────────┐
                                  ▼                               ▼
                             NIO writer                     ASYNCIO writer
                             Java NIO                       Linux libaio
                                  │                               │
                                  └───────── disk/volume ─────────┘
```

File journal **không đại diện cho toàn bộ dữ liệu Artemis**:

| Khu vực mặc định (tương đối từ broker instance) | Dữ liệu điển hình | Ảnh hưởng khi đánh giá NIO/ASYNCIO |
|---|---|---|
| `data/journal` | Message records, ACK, transaction, duplicate-ID cache | **Trọng tâm** của `journal-type` |
| `data/bindings` | Metadata address/queue, bindings | Journal khác; phải bảo toàn cùng dữ liệu broker khi backup/restore |
| `data/paging` | Page files khi address chuyển sang paging | I/O paging có cơ chế và nút thắt riêng; không tự nhanh lên cùng tỷ lệ với AIO |
| `data/largemessages` hoặc thư mục large-message tương ứng | Phần body của large message | Cần benchmark riêng; không nằm toàn bộ trong message journal |

Ngoài file journal còn có **JDBC store** như một phương án persistence khác; nếu dùng JDBC thì việc chỉnh `journal-type` **không** biến JDBC thành NIO/ASYNCIO. Bài này giả định cấu hình mặc định dựa trên file journal, `persistence-enabled=true`.

## 3. NIO và ASYNCIO: cùng mục tiêu, khác cách hoàn tất ghi

| Tiêu chí | `NIO` | `ASYNCIO` |
|---|---|---|
| Cơ chế | Java NIO truy cập filesystem, dùng đồng bộ khi yêu cầu durability | Native wrapper gọi **Linux asynchronous I/O (`libaio`)**, nhận completion khi I/O hoàn tất |
| Phụ thuộc nền tảng | Chạy được trên các hệ điều hành mà Artemis/JVM hỗ trợ | Cần **Linux** và thư viện native/dependency tương thích |
| I/O outstanding | `journal-max-io` nên là **1** | Cho phép nhiều write request pending; có giới hạn queue và giới hạn kernel |
| Ưu điểm chính | Triển khai đơn giản, dễ tái lập, ít phụ thuộc native | Có thể tăng throughput/giảm chi phí chờ I/O khi storage và workload phù hợp |
| Đánh đổi | Ghi đồng bộ chịu latency I/O; throughput có thể thấp hơn dưới tải cao | Phụ thuộc `libaio`, hỗ trợ filesystem/kernel, native ABI và giới hạn AIO của host |
| Khi không hỗ trợ | Hoạt động theo Java NIO | Artemis có thể **tự chuyển sang NIO** |
| Dùng khi | Lab đa hệ điều hành, Windows/macOS native, môi trường không có `libaio`, fallback an toàn | Linux host/container hỗ trợ AIO, có volume phù hợp và số đo thực tế cho thấy lợi ích |

**ASYNCIO không đồng nghĩa “gửi không cần đợi xác nhận”**. Nó mô tả kỹ thuật I/O trong broker, khác với producer JMS async send hoặc `blockOnDurableSend` ở Core client. Với chính sách sync phù hợp, Artemis vẫn có thể **đợi completion của I/O bền vững** trước khi xác nhận send/commit.

### 3.1. Điều gì xảy ra với một message persistent?

Ví dụ producer gửi persistent message **ngoài transaction**:

```text
Producer           Broker/Journaling               Storage
    | SEND                 |                          |
    | ------------------>  | append record            |
    |                      | ---- NIO/AIO write ----> |
    |                      |     sync/completion      |
    |                      | <----------------------- |
    | <---- confirmation -- |                          |
```

Khi `journal-sync-non-transactional=true` và hành vi xác nhận của provider/transport được thiết lập để chờ broker, confirmation gắn với quy tắc đồng bộ journal. Với transaction, mốc quan trọng chuyển sang `commit()` và `journal-sync-transactional=true`.

**Ba giới hạn quan trọng:**

- `send()` return **không luôn** đồng nghĩa dữ liệu đã được đồng bộ, đặc biệt khi producer/core client bật chế độ gửi không chờ xác nhận hoặc transaction chưa commit.
- `journal-type=ASYNCIO` không thể sửa độ bền nếu thiết bị/VM giả vờ flush thành công, volume bị mất, journal bị cấu hình không sync hoặc dữ liệu bị xóa ngoài broker.
- Process restart, broker crash và **mất điện thật** là ba loại thử nghiệm khác nhau. `kill -9` vẫn để nguyên page cache của hệ điều hành; không thể từ đó chứng minh bảo toàn dữ liệu khi mất nguồn.

## 4. Yêu cầu môi trường cho ASYNCIO

Theo tài liệu Artemis, ASYNCIO dùng **Linux native AIO** và yêu cầu Linux kernel 2.6+ cùng `libaio`. Nó không phải cơ chế `io_uring` và không được kích hoạt chỉ vì Java đang chạy trên phiên bản JDK mới.

### 4.1. Checklist nền tảng

| Lớp | Phải kiểm tra | Lỗi thường gặp |
|---|---|---|
| Hệ điều hành | Broker **thực sự chạy trên kernel Linux**; không chỉ máy phát triển dùng Windows/macOS | Chạy Artemis native trên Windows nhưng cấu hình `ASYNCIO`; rốt cuộc dùng NIO |
| Thư viện | Runtime/container có `libaio` và native library tương thích với bản Artemis/JVM/kiến trúc CPU | Chỉ cài libaio trên host nhưng **không** nằm trong image container |
| Kiến trúc và ABI | CPU architecture, distro, libc/native ABI phù hợp image và thư viện | Image slim/Alpine khác base image đã được kiểm thử |
| Filesystem | Volume/data path có filesystem hỗ trợ AIO; tài liệu nêu ext2/ext3/ext4/JFS/XFS/NFSv4 | Overlay, filesystem mạng hoặc mount option không tương thích; I/O không đáp ứng kỳ vọng |
| Quyền & dung lượng | UID chạy broker được phép tạo/ghi và lock file; đủ dung lượng và inode | Volume mount root-owned, mount read-only, quota cạn |
| Kernel AIO resources | `fs.aio-max-nr`, `fs.aio-nr`, tổng số I/O outstanding của **mọi tiến trình** | Nhiều broker/ứng dụng dùng chung quota kernel khiến AIO không lấy đủ request slots |
| Thiết bị & durability | SSD/NVMe/SAN, đồng bộ `fdatasync`, write cache, IOPS/latency thực | Storage latency cao, cache mất điện, mount volume tạm làm mất dữ liệu khi recreate pod |

Danh sách filesystem nói trên phản ánh phạm vi được tài liệu Artemis công bố, **không phải lời bảo đảm NFSv4/CSI/SAN nào cũng phù hợp**. Với storage mạng và container overlay filesystem phải thử trực tiếp trên đúng volume triển khai; kiểm tra cả tính ổn định của file locking và semantics ghi bền vững.

### 4.2. Các lệnh kiểm tra *chỉ đọc* trên Linux/container

Chạy **trong môi trường thực sự chạy broker** (nếu là container, dùng shell bên trong container để kiểm tra thư viện và user; với kernel/volume kiểm tra thêm tại host):

```bash
# Kernel và kiến trúc Linux.
uname -srm

# Số request AIO tối đa / đang dùng theo kernel.
cat /proc/sys/fs/aio-max-nr
cat /proc/sys/fs/aio-nr

# Debian/Ubuntu/RHEL có ldconfig: thư viện native đã được loader thấy?
ldconfig -p 2>/dev/null | grep -E 'libaio\.so' || true

# Đúng path journal đang được cấu hình, ví dụ:
JOURNAL_DIR=/var/lib/artemis-instance/data/journal
df -hT "$JOURNAL_DIR"
findmnt -T "$JOURNAL_DIR" -o TARGET,SOURCE,FSTYPE,OPTIONS

# Chạy bằng đúng UID broker, không dựa vào kết quả root.
id
test -w "$JOURNAL_DIR" && echo "journal writable" || echo "not writable"
```

Với một số image tối giản, lệnh `ldconfig` hoặc `findmnt` có thể **không tồn tại**; khi đó cần công cụ tương đương ở host và kiểm tra package trong image. `ldconfig` chỉ cho biết loader thấy thư viện, **không** bảo đảm native journal khởi tạo thành công. Broker vẫn là nguồn xác nhận cuối cùng.

**Cài package đúng nơi:** với các distro Debian/Ubuntu, runtime package có thể là `libaio1` hoặc tên khác theo release; trên RHEL/Fedora thường là `libaio`. Không hardcode tên gói của một distro vào Dockerfile khác. Trên container cần **build image** kèm thư viện phù hợp và pin phiên bản image; cài trực tiếp vào container đang chạy sẽ mất sau khi recreate.

### 4.3. Kernel quota và concurrency

`journal-max-io` giới hạn số write request mà Artemis xếp chờ/trình lên subsystem I/O; đối với ASYNCIO nó phải phù hợp quota Linux `/proc/sys/fs/aio-max-nr` **và nhu cầu của các tiến trình khác**.

Ví dụ một máy có giới hạn `aio-max-nr=65536`, ba broker được cấu hình mỗi broker `journal-max-io=500`. Con số 1500 chỉ là tổng giới hạn **lý thuyết cho journal**; quota thực tế còn được dùng bởi các bộ phận khác, các tiến trình khác và cách Artemis quản lý hàng đợi. **Không** tự nâng giới hạn kernel hoặc set `journal-max-io=65536` cho mỗi broker; kiểm thử và điều chỉnh theo thống kê I/O, số broker và quyền quản trị OS.

Artemis 2.57 có tài liệu tham chiếu mà các mục `journal-max-io` công bố những giá trị mặc định AIO khác nhau. Để tránh phụ thuộc vào cách diễn giải default giữa release/tài liệu, ở bài thực hành này ta đặt **AIO `500`** và **NIO `1` tường minh**, rồi xác minh qua log và benchmark. Không copy tuning từ ví dụ sang production mà không thử.

### 4.4. Docker, Kubernetes và máy ảo

- Một container Linux **dùng kernel Linux của host/VM** nhưng có **filesystem và thư viện trong image** của riêng nó. `libaio` cài ở host không đồng nghĩa container load được.
- Docker Desktop trên Windows/macOS dùng Linux VM cho Linux containers; ASYNCIO **có thể hoạt động** nếu image, kernel VM và volume đều hỗ trợ. Đừng quyết định chỉ theo OS của laptop.
- Volume mount cần **lưu bền dữ liệu qua recreate**. Đường dẫn `data/journal` ở container trỏ vào writable layer sẽ biến mất nếu xóa container, dù journal đang ghi đồng bộ hoàn hảo.
- Kubernetes PVC/CSI có các semantics đồng bộ và IOPS khác nhau; benchmark đúng storage class, cùng requests/limits, fsGroup/UID, số replica và topology. `emptyDir` là dữ liệu **ephemeral theo pod**.
- Khi dùng shared-store HA, phải tuân thủ cơ chế lock/ownership của Artemis; không cho hai broker độc lập cùng ghi một journal. Đổi NIO/ASYNCIO không biến một volume thành distributed transactional store.

## 5. Cấu hình `broker.xml`: hai phương án có thể kiểm chứng

Các fragment dưới đây **chỉ là các phần tử nằm trực tiếp trong `<core>`** của `etc/broker.xml`. Hãy sửa các phần tử tương ứng trong file broker hiện hữu; **không** chèn thêm `<core>` hay các cấu hình journal trùng nhau. Việc đổi journal type nên thực hiện trong maintenance window khi broker đã dừng và dữ liệu được sao lưu nhất quán.

### 5.1. Phương án A: Linux + native libaio (ASYNCIO)

```xml
<!-- Chỉnh các phần tử bên trong <core> đã có. -->
<persistence-enabled>true</persistence-enabled>
<journal-type>ASYNCIO</journal-type>
<journal-directory>data/journal</journal-directory>
<journal-file-size>10485760</journal-file-size>
<journal-min-files>4</journal-min-files>
<journal-max-io>500</journal-max-io>
<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
<journal-datasync>true</journal-datasync>
```

Mục đích:

- `journal-type=ASYNCIO` yêu cầu Artemis thử dùng Linux AIO.
- `journal-file-size=10485760` đặt kích thước từng journal file là **10 MiB**, không phải tổng giới hạn dung lượng journal.
- `journal-min-files=4` pre-create ít nhất bốn file để hạn chế chi phí mở rộng ở runtime; chỉ là giá trị **lab**, không phải khuyến nghị cho mọi broker.
- `journal-max-io=500` giới hạn outstanding AIO requests, phải phù hợp khả năng thiết bị và kernel.
- Ba tùy chọn sync/datasync được để **true** nhằm bảo toàn chính sách durability.

Nếu broker log báo “Using NIO Journal”, cấu hình ASYNCIO **không có hiệu lực theo mong đợi**. Cần truy lại kernel, `libaio`, thư viện native, filesystem và startup warning; không tùy tiện giảm các flag sync chỉ để tăng tốc.

### 5.2. Phương án B: NIO tương thích rộng

```xml
<!-- Thay thế các giá trị tương ứng của A, không bật song song. -->
<persistence-enabled>true</persistence-enabled>
<journal-type>NIO</journal-type>
<journal-directory>data/journal</journal-directory>
<journal-file-size>10485760</journal-file-size>
<journal-min-files>4</journal-min-files>
<journal-max-io>1</journal-max-io>
<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
<journal-datasync>true</journal-datasync>
```

Ở NIO, **`journal-max-io=1` là giá trị được tài liệu yêu cầu**; không dùng `500` của ASYNCIO với NIO rồi suy rằng đang có 500 tác vụ async. Về tính đúng đắn, NIO vẫn hỗ trợ transaction bền vững. Khác biệt chủ yếu nằm ở đường I/O và đặc tính hiệu năng.

### 5.3. Những núm tuning không nên thay ngẫu nhiên

| Thuộc tính | Đơn vị / tác động | Nguy cơ khi chỉnh sai |
|---|---|---|
| `journal-buffer-timeout` | **Nanosecond**, timeout xả buffer khi chưa đầy | Tăng quá lớn làm tăng latency xác nhận; `0` tắt buffering |
| `journal-buffer-size` | Kích thước timed buffer | Tăng bộ nhớ/buffering mà workload không được lợi |
| `journal-file-size` | **Byte** cho mỗi file journal | File quá nhỏ dẫn đến luân chuyển/compaction nhiều; quá lớn tăng preallocation và dung lượng |
| `journal-min-files` | Số file pre-create | Tạo nhiều file lớn khiến startup/preallocation tốn dung lượng; quá ít tăng cấp phát lúc cao tải |
| `journal-max-io` | Số request I/O tối đa pending | NIO phải là 1; AIO quá cao có thể chạm giới hạn OS hoặc tăng latency |
| `journal-sync-transactional` | Chờ flush các transaction (commit/prepare/rollback) | Tắt có thể giảm độ bền sau crash/mất điện |
| `journal-sync-non-transactional` | Chờ flush cho send/ACK non-transacted | Tắt có thể biến ACK gửi thành công thành dữ liệu mất khi sự cố |
| `journal-datasync` | Dùng cơ chế sync bền vững với journal writes, đặc biệt NIO/MAPPED | `false` làm yếu bảo đảm khi mất nguồn |

Theo tài liệu Artemis, timeout buffer chuẩn tham chiếu khoảng **3.333.333 ns cho NIO** và **500.000 ns cho ASYNCIO**. Đây là giá trị hệ thống tự điều chỉnh theo implementation; muốn thay phải đo p99 send/commit latency lẫn throughput trước và sau. Không cần chỉnh timeout để chứng minh NIO/ASYNCIO chạy được.

## 6. Kiểm tra journal thực sự đang dùng

**Nguồn xác thực quan trọng nhất là log lúc broker khởi động.** Artemis có các thông điệp:

```text
AMQ221012: Using AIO Journal
AMQ221013: Using NIO Journal
```

Đây là **hai ví dụ thay thế**, không phải log của cùng một lần startup. Tìm trong log của **process và lần khởi động hiện tại**:

```bash
# Sửa thành đường dẫn log thực tế của instance/image bạn đang chạy.
grep -E 'AMQ221012|AMQ221013|Using (AIO|NIO) Journal' \
  /var/lib/artemis-instance/log/artemis.log
```

Nếu log được ghi vào stdout của container, dùng công cụ tương ứng như `docker logs` hoặc `kubectl logs` và lọc **bản ghi startup đúng thời điểm**. NIO fallback có thể đi cùng warning native library; kiểm tra cả log lỗi load `libaio`, `UnsatisfiedLinkError`, I/O permission hoặc unsupported filesystem.

| Cấu hình mong muốn | Log startup | Kết luận |
|---|---|---|
| `ASYNCIO` | `AMQ221012: Using AIO Journal` | AIO đã được chọn ở runtime |
| `ASYNCIO` | `AMQ221013: Using NIO Journal` | **Fallback**, cần điều tra nếu AIO là yêu cầu bắt buộc |
| `NIO` | `AMQ221013: Using NIO Journal` | Đúng kế hoạch NIO |
| `NIO` | Không thấy log liên quan | Chưa đủ bằng chứng; xem đúng log, đúng process, đúng broker version |

**Cảnh báo:** `journal-type` đọc từ file chỉ là **cấu hình**, còn `AMQ221012`/`AMQ221013` mới xác nhận implementation thực tế. Các MBean và kết quả client send/receive cũng **không** phân biệt chắc hai implementation nếu thiếu log/config runtime.

### Fallback là thay đổi hiệu năng hay thay đổi độ bền?

Trong một triển khai có cả hai sync flag được giữ true và storage tuân thủ lệnh đồng bộ, fallback AIO → NIO **thường thay đổi hiệu năng/latency hơn là mô hình đảm bảo giao dịch**. Tuy nhiên fallback không vô hại về SLO:

- Throughput có thể giảm; producer thấy latency tăng.
- Broker có thể chuyển sang paging/backpressure sớm hơn dưới cùng tải.
- Cần chỉnh `journal-max-io=1` cho NIO hoặc để Artemis áp dụng default theo implementation khi sử dụng fallback; không ép tuning AIO vào NIO.
- Một fallback bất ngờ có thể phản ánh **thư viện/volume khác môi trường đã kiểm thử**. Hãy đánh dấu degraded và xử lý nguyên nhân trước khi chốt production.

Không so sánh chỉ bằng thời gian startup. Phải đo trong tải persistent send/ack/commit tương ứng hệ thống.

## 7. Java/JMS: kiểm chứng dữ liệu còn sau broker restart

Đây là một **smoke test** về persistence, không phải benchmark NIO vs ASYNCIO. Nó cố tình không tạo consumer lúc gửi để message còn pending, sau đó dùng `QueueBrowser` đọc ID mà **không acknowledge** sau restart.

### 7.1. Điều kiện ban đầu

Trên **broker lab**, bảo đảm queue durable đã được tạo. Ví dụ thêm đoạn dưới vào `<addresses>` trong `broker.xml`:

```xml
<address name="lab.journal.survival">
  <anycast>
    <queue name="lab.journal.survival"/>
  </anycast>
</address>
```

Chỉ dùng một broker, một queue mới và không có consumer khác. Broker phải có `persistence-enabled=true`, journal directory nằm trên **volume bền vững**. Lệnh `JMSContext.createQueue` tạo handle phía client; nó không tự bảo đảm queue broker đã tồn tại và durable.

**Maven dependency (Java 17, Artemis Jakarta Core):**

```xml
<dependencies>
  <dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
  </dependency>
</dependencies>
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Trong một `pom.xml` thực tế, `<properties>` phải đặt ở **cấp project**, không nằm trong `<dependencies>`. Ví dụ trên là các fragment để chèn vào cấu trúc Maven hợp lệ có sẵn, **không phải file pom.xml hoàn chỉnh**.

### 7.2. `JournalSurvivalProbe.java`

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Enumeration;

public final class JournalSurvivalProbe {
    private static final String QUEUE = "lab.journal.survival";

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2 ||
                (!"send".equals(args[0]) && !"check".equals(args[0]))) {
            throw new IllegalArgumentException(
                "Usage: JournalSurvivalProbe send|check <runId>");
        }

        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");
        String url = System.getenv().getOrDefault(
            "BROKER_URL", "tcp://127.0.0.1:61616");
        String runId = args[1];

        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(url);
        try {
            if ("send".equals(args[0])) {
                try (JMSContext tx = factory.createContext(
                        user, password, JMSContext.SESSION_TRANSACTED)) {
                    Queue queue = tx.createQueue(QUEUE);
                    TextMessage message = tx.createTextMessage("DATA-" + runId);
                    message.setStringProperty("runId", runId);
                    tx.createProducer()
                      .setDeliveryMode(DeliveryMode.PERSISTENT)
                      .send(queue, message);

                    tx.commit();
                    System.out.println("COMMIT_CONFIRMED " + runId);
                }
            } else {
                try (JMSContext ctx = factory.createContext(user, password)) {
                    QueueBrowser browser = ctx.createBrowser(ctx.createQueue(QUEUE));
                    try {
                        Enumeration<?> entries = browser.getEnumeration();
                        boolean found = false;
                        while (entries.hasMoreElements()) {
                            Message m = (Message) entries.nextElement();
                            if (runId.equals(m.getStringProperty("runId"))) {
                                System.out.println("FOUND runId=" + runId
                                    + " messageId=" + m.getJMSMessageID());
                                found = true;
                            }
                        }
                        if (!found) {
                            throw new IllegalStateException(
                                "Message missing: " + runId);
                        }
                    } finally {
                        browser.close();
                    }
                }
            }
        } finally {
            factory.close();
        }
    }
}
```

**Tại sao ví dụ này kiểm tra đúng mục tiêu?**

- `send` dùng transaction rồi gọi `commit()` rõ ràng; message `PERSISTENT`. Nếu commit trả lỗi do mạng, **không** coi dữ liệu chắc chắn đã mất: kiểm tra broker và retry có event ID ổn định.
- `check` dùng `QueueBrowser`, không gọi `receive`/`acknowledge` nên dữ liệu lab vẫn ở queue. Browser không phải snapshot nhất quán trên hệ thống có consumer đồng thời; bài test được cô lập để tránh nhiễu.
- Trước và sau khi restart, dùng **cùng broker instance/volume**. Nếu vô tình khởi tạo broker mới với data directory mới thì test không phản ánh độ bền của journal cũ.

### 7.3. Quy trình chạy và bằng chứng

1. Chỉnh `journal-type=NIO`, giữ sync flag true, khởi động broker lab, chụp log `AMQ221013`.
2. Chạy `JournalSurvivalProbe send nio-001`; xác nhận `COMMIT_CONFIRMED nio-001`.
3. Dừng broker **gracefully**, khởi động lại với **cùng dữ liệu và cấu hình**.
4. Chạy `JournalSurvivalProbe check nio-001`; xác nhận `FOUND` và message ID.
5. Trên **một broker lab sạch/volume độc lập**, đổi sang `ASYNCIO`, kiểm tra `libaio`/filesystem, khởi động và chụp log `AMQ221012`; lặp lại send → restart → check với `aio-001`.
6. Đo latency/throughput tương ứng workload thực sau khi cả hai chế độ đều pass smoke test. Không so sánh kết quả trên hai máy hoặc hai volume có tốc độ khác nhau rồi kết luận chỉ do journal type.

**Bảng nghiệm thu:**

| Ca kiểm thử | NIO | ASYNCIO |
|---|---|---|
| Broker startup trên volume đúng quyền | PASS khi log `AMQ221013` | PASS khi log `AMQ221012` |
| Gửi persistent + commit được xác nhận | `COMMIT_CONFIRMED` | `COMMIT_CONFIRMED` |
| Graceful restart không đổi volume | `FOUND runId=...` | `FOUND runId=...` |
| Kill process rồi restart trên broker lab | Message còn nếu commit và storage đúng | Message còn nếu commit và storage đúng |
| Mất điện/device failure | **Không** được khẳng định chỉ nhờ smoke test | **Không** được khẳng định chỉ nhờ smoke test |

**Thận trọng:** `kill -9` / `docker kill` là fault injection phá hủy tiến trình; chỉ dùng trên môi trường **được cô lập, có backup**, không trên broker production. Một process kill không xóa kernel page cache, nên không thể thay thế bài kiểm tra durability trước mất nguồn thực sự.

## 8. Benchmark đúng cách, không đánh đồng NIO và ASYNCIO với tuning message

Benchmark phải giữ mọi thứ khác bằng nhau:

- Cùng máy/VM, CPU/RAM/JDK, storage class, volume IOPS/latency, bản Artemis và cấu hình broker.
- Cùng kích thước message (ví dụ 1 KiB và 64 KiB), mức concurrency producer, tỷ lệ ACK, transaction batch size, số queue và consumer.
- Cùng `PERSISTENT` và các cờ sync/datasync; nếu một bên tắt sync thì phép đo **không còn công bằng về durability**.
- Cùng điều kiện journal đã warm-up và trạng thái backlog/compaction. Preallocation lần đầu có thể làm lệch số liệu.

**Chỉ số nên báo cáo:**

| Chỉ số | Ý nghĩa |
|---|---|
| Producer publish throughput (msg/s) | Khả năng nhận message có xác nhận theo workload |
| p50/p95/p99 latency của `send` / `commit` | Thời gian consumer/producer phải chờ durability |
| Disk write throughput, IOPS, fsync/datasync latency | Bằng chứng nút thắt I/O thật |
| CPU broker và iowait | Xác định chi phí xử lý so với chờ storage |
| Queue depth/paging/blocked producer count | Phát hiện hệ thống không theo kịp tải |
| Journal errors, AIO quota exhaustion, startup fallback | Phát hiện môi trường không tương thích hoặc degraded |

**Không mặc định ASYNCIO luôn nhanh hơn**: trên SSD nhanh với batch nhỏ, tải thấp hoặc volume mạng, lợi ích có thể nhỏ hoặc biến động. Cần đo p99 latency, sức chịu tải và khả năng phục hồi, không chỉ đỉnh thông lượng. Nếu NIO đáp ứng SLA và vận hành đơn giản hơn, chọn NIO là quyết định hợp lệ.

## 9. Sự cố điển hình và quy trình chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra đúng |
|---|---|---|
| Cấu hình `ASYNCIO` nhưng log `Using NIO Journal` | Thiếu `libaio`/native library hoặc filesystem không hỗ trợ | Runtime/container OS, loader, startup warning, mount filesystem |
| Log native `UnsatisfiedLinkError` | Thư viện không khớp CPU/ABI hoặc không có đường dẫn load | Kiến trúc image, thư viện native trong container |
| `journal-max-io` quá lớn, AIO submission lỗi | Vượt `fs.aio-max-nr`/hàng đợi OS | `aio-nr`, `aio-max-nr` và số broker cùng host |
| Broker không startup được, lỗi permission | UID broker không ghi/lock được data directory | `id`, `test -w`, volume ownership/mount options |
| NIO chạy được nhưng latency sync rất cao | Storage/FS quá chậm hoặc noisy neighbors | I/O latency, quota, queue length, journal buffer |
| Send thành công nhưng restart mất message | Dùng volume ephemeral, queue không durable, nonpersistent message hoặc sync bị giảm | Kiểm tra `persistence-enabled`, `DeliveryMode`, journal path/volume, sync |
| Journal ổn nhưng broker vẫn paging chậm | Paging/large-message IO độc lập thành nút thắt | Đo thư mục paging/large messages và address settings |
| Hai broker đụng journal lock | Cùng trỏ vào một path nhưng không có HA shared-store đúng | Kiểm tra topology, node manager, storage ownership |

**Trình tự xử lý:** xác định **đúng broker/version và process** → xem log journal type → kiểm tra `broker.xml` hiện hành → kiểm tra kernel/library/filesystem/UID → đối chiếu sync settings → smoke test persistence → benchmark. Đừng xóa `data/journal` để khắc phục startup lỗi; thao tác đó có thể hủy message, transaction và duplicate-ID cache chưa được tiêu thụ.

## 10. Checklist chọn phương án và bàn giao

- [ ] Đã xác định file journal (không phải JDBC), thư mục message journal và đường volume tương ứng.
- [ ] Nếu chọn ASYNCIO: chạy trên Linux, có `libaio`/native dependency, filesystem hỗ trợ, kernel AIO quota đủ, kiểm tra từ **bên trong runtime broker**.
- [ ] Startup log xác nhận **`AMQ221012` với ASYNCIO** hoặc **`AMQ221013` với NIO**; nếu không khớp thì đánh dấu fallback/degraded.
- [ ] NIO để `journal-max-io=1`; AIO dùng mức outstanding phù hợp OS và số đo, không tăng tùy ý.
- [ ] Giữ `journal-sync-transactional=true`, `journal-sync-non-transactional=true`, `journal-datasync=true` khi yêu cầu dữ liệu tồn tại qua crash/mất điện.
- [ ] Queue durable, message persistent, commit/ACK được xác nhận; test khôi phục bằng cùng volume, không nhầm restart với recreate storage.
- [ ] Có benchmark cùng điều kiện, gồm throughput, p99, journal errors và hành vi paging/compaction.
- [ ] Đã có backup/restore và quy trình dừng broker an toàn; không sửa/xóa journal files khi broker đang chạy.

**Kết luận:** NIO và ASYNCIO là **hai implementation của journal filesystem**. NIO là đường Java tương thích rộng; ASYNCIO dùng Linux `libaio` để khai thác I/O bất đồng bộ khi môi trường thật sự hỗ trợ. Chọn ASYNCIO phải đi kèm kiểm tra **log runtime, thư viện, filesystem, kernel quota, storage durability và hiệu năng đo được**; lựa chọn kiểu journal **không thể thay thế** chính sách sync hoặc quy trình sao lưu/khôi phục dữ liệu.

## Tài liệu chính thức

1. [Apache Artemis 2.57.0 — Persistence](https://artemis.apache.org/components/artemis/documentation/latest/persistence.html): file journal, NIO/ASYNCIO/MAPPED, fallback, Linux `libaio`, hệ thống tệp, `journal-max-io` và sync flags.
2. [Apache Artemis 2.57.0 — Configuration Reference](https://artemis.apache.org/components/artemis/documentation/latest/configuration-index.html): các thuộc tính `journal-type`, `journal-sync-*`, `journal-datasync`, `journal-buffer-timeout` và thông số mặc định.
3. [Apache Artemis — Examples](https://artemis.apache.org/components/artemis/documentation/latest/examples.html): log startup thực tế `AMQ221012: Using AIO Journal`.
4. [Apache Artemis — Network Isolation](https://artemis.apache.org/components/artemis/documentation/latest/network-isolation.html): log `AMQ221013: Using NIO Journal` ở lần khởi động.
5. [Apache Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging.html): paging I/O là cơ chế khác message journal.
6. [Apache Artemis — Large Messages](https://artemis.apache.org/components/artemis/documentation/latest/large-messages.html): dữ liệu large message lưu ngoài message journal.
