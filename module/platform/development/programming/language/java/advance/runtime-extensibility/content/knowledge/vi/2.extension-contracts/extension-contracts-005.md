# Truyền cấu hình và dịch vụ của ứng dụng chủ qua ngữ cảnh có giới hạn

Trong kiến trúc mở rộng lúc chạy (runtime extensibility), ứng dụng chủ (host) có thể nạp các extension/plugin để bổ sung tính năng. Plugin thường cần biết một vài tham số cấu hình và gọi một số năng lực của host, chẳng hạn ghi sự kiện, truy vấn dữ liệu đã được phép hoặc đọc thời gian hệ thống. Nếu host đưa thẳng toàn bộ đối tượng ứng dụng, kho cấu hình, container DI hay kết nối cơ sở dữ liệu cho plugin, hợp đồng mở rộng trở nên khó kiểm soát: plugin phụ thuộc vào chi tiết nội bộ, dễ sử dụng quá quyền và khó tháo gỡ khi ngừng hoạt động.

Giải pháp là **ngữ cảnh có giới hạn (scoped/limited context)**: host tự tạo một đối tượng tuân theo API công khai, chứa cấu hình tối thiểu dành riêng cho một plugin và chỉ các dịch vụ mà plugin được phép gọi. Chính host quyết định danh tính, phạm vi, hạn mức, vòng đời và cách thực thi của từng dịch vụ; plugin nhận một hợp đồng sử dụng ổn định.

## 1. Phân biệt ba thành phần

- **Hợp đồng extension** định nghĩa điểm vào và vòng đời mà plugin phải thực hiện, ví dụ phương thức start(PluginContext) và stop(). Đây là API mà host và plugin cùng biên dịch.
- **Cấu hình plugin** là dữ liệu cấu hình thuộc phạm vi plugin: cờ tính năng, giới hạn, tên tài nguyên được phép truy cập, chính sách xử lý… Host lọc, kiểm tra và chuyển thành kiểu dữ liệu được định nghĩa rõ.
- **Dịch vụ host** là khả năng hành động do host kiểm soát, ví dụ EventPublisher, DocumentReader hoặc TaskScheduler. Plugin gọi qua một giao diện hẹp; triển khai thật, thông tin xác thực và kết nối hạ tầng nằm ở host.

Điểm mấu chốt là **ngữ cảnh không phải bản sao của toàn bộ host**. Hợp đồng chỉ công khai những gì cần cho tác vụ của plugin.

~~~text
Host / cấu hình hệ thống / hạ tầng
          |
          v
  Xác định danh tính plugin
  Xác thực chính sách, chọn phạm vi
          |
          v
  Tạo PluginContext cho riêng plugin
    - PluginConfig (đã lọc, kiểm tra)
    - EventPublisher (có hạn mức)
    - Clock/Time API (đã chọn)
          |
          v
    Plugin.start(context)
          |
          v
  Plugin dùng API -> Host kiểm tra -> Thực thi
          |
          v
    Host thu hồi khi plugin dừng
~~~

Nếu hai plugin có vai trò khác nhau, host cần cấp **hai context khác nhau**, kể cả khi chúng dùng chung lớp giao diện. Plugin không được tự chọn hoặc tự nâng phạm vi.

## 2. Thiết kế cấu hình theo hợp đồng rõ ràng

### Chỉ đưa dữ liệu tối thiểu

Thay vì chuyển nguyên đối tượng ApplicationConfig, System.getenv(), Spring ApplicationContext hay một Map chứa mọi khóa, hãy xây một kiểu cấu hình chỉ gồm các giá trị cần thiết. Ví dụ plugin chào người dùng chỉ cần lời chào và hạn mức sự kiện, không cần URL nội bộ, mật khẩu cơ sở dữ liệu hay khóa ký token.

Một cấu hình tốt thường đáp ứng các thuộc tính sau:

1. **Tường minh và có kiểu**: dùng record, enum hoặc interface được định nghĩa trước; tránh bắt plugin ép kiểu từ Map<String, Object> tùy ý.
2. **Được host kiểm tra trước khi cấp**: xác thực giá trị thiếu, khoảng số, danh sách cho phép và quan hệ giữa các tham số. Không coi dữ liệu từ manifest/plugin là đáng tin mặc nhiên.
3. **Bất biến theo hợp đồng**: record với String, số nguyên, enum thường thích hợp; nếu chứa List/Map phải sao chép phòng thủ và chú ý phần tử bên trong cũng có thể thay đổi.
4. **Có phạm vi và nguồn gốc rõ ràng**: giá trị nào là mặc định của host, giá trị nào được người quản trị cấu hình, giá trị nào riêng cho từng plugin/tenant.
5. **Có chính sách cập nhật**: snapshot cố định trong một phiên chạy, hoặc cơ chế cập nhật cấu hình tường minh (version/event) nếu hỗ trợ thay đổi động.

Ví dụ, một record PluginConfig(String greeting, int maxEvents) có thể chặn lời chào rỗng và hạn mức ngoài khoảng hợp lệ ngay khi khởi tạo. Các kiểm tra này bảo vệ tính nhất quán của dữ liệu. Tuy nhiên, **giới hạn quyền và quota thực tế phải được host thực thi tại dịch vụ**, không chỉ dựa vào tham số mà plugin nhìn thấy.

### Khi cấu hình thay đổi

Với context dạng snapshot, plugin tiếp tục thấy phiên bản đã nhận cho tới khi host tái cấu hình hoặc khởi tạo lại nó. Nếu ứng dụng phải hỗ trợ cập nhật ngay khi chạy, hãy thiết kế hợp đồng riêng, ví dụ một phương thức đọc snapshot có version, hoặc một callback về thay đổi. Quy định rõ tính nhất quán: bản cập nhật có hiệu lực cho lệnh gọi mới từ khi nào, lệnh đang chạy xử lý ra sao và trường hợp cấu hình mới không hợp lệ.

Không nên để plugin tự giữ tham chiếu tới Map cấu hình nội bộ có thể bị sửa đồng thời, vì kết quả vừa khó dự đoán vừa dễ làm lộ dữ liệu ngoài phạm vi.

## 3. Cấp dịch vụ dưới dạng capability có giới hạn

Một **capability** ở đây là đối tượng cho phép thực hiện một nhóm hành động nhất định. Giao diện nên mô tả nghiệp vụ mà plugin được phép làm, thay vì trả về đối tượng hạ tầng đầy quyền.

| Nhu cầu của plugin | API nên cấp | Tránh cấp trực tiếp |
| --- | --- | --- |
| Ghi sự kiện của plugin | EventPublisher.publish(message) có quota và định danh do host gắn | Message broker client đầy quyền |
| Đọc tài liệu đã duyệt | DocumentReader.read(allowedId) với kiểm tra mỗi lần gọi | DataSource hoặc filesystem root |
| Xem thời gian để xử lý | Clock hoặc phương thức now() | Toàn bộ đối tượng Runtime/host |
| Ghi log gắn nguồn phát | PluginLogger tự gắn pluginId và lọc dữ liệu | Logger cấu hình tự do với mọi sink |
| Gửi tác vụ nền | TaskScheduler giới hạn loại tác vụ, số lượng, thời gian | ExecutorService dùng chung không kiểm soát |

Dịch vụ nên **ràng buộc danh tính và phạm vi tại lúc host tạo adapter**. Plugin không được tự truyền pluginId hay tenantId để mạo danh trong từng lệnh gọi. Kiểm tra quyền trên *mỗi lần gọi* là cần thiết, nhất là khi quyền có thể bị thu hồi trong lúc plugin đang chạy.

Ở phía host, wrapper/adaptor có thể bổ sung giới hạn số lần gọi, kiểm soát kích thước payload, timeout, rate limit, audit, lọc dữ liệu đầu ra và chuyển lỗi hạ tầng sang kiểu lỗi trong hợp đồng. Những giới hạn này nên được kiểm tra tại ranh giới thật của dịch vụ; chỉ chú thích trong tài liệu API không đủ để ngăn gọi sai.

**Nguyên tắc chọn giao diện:** nếu một plugin chỉ cần gửi một sự kiện, API publish(event) phù hợp hơn việc trả về một đối tượng cho phép tạo topic, xóa queue, duyệt tất cả sự kiện và thay đổi cấu hình broker.

## 4. Ví dụ Java 17 chạy độc lập

Ví dụ dưới đây minh họa host tạo một context riêng cho extension chào người dùng. Cấu hình có kiểu và được xác thực; host cấp đúng một dịch vụ xuất thông điệp với hạn mức hai lần; nhãn pluginId được gắn bởi host; host có thể thu hồi dịch vụ sau khi extension dừng. Đồng hồ cố định giúp kiểm tra đầu ra chính xác.

Lưu tệp **PluginContextDemo.java** (UTF-8):

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class PluginContextDemo {
    public static void main(String[] args) {
        PluginConfig config = new PluginConfig("Xin chào", 2);
        ScopedPublisher publisher =
                new ScopedPublisher("greeting", config.maxEvents());
        PluginContext context = new SimpleContext(
                config,
                publisher,
                Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"),
                            ZoneOffset.UTC)
        );

        Extension extension = new GreetingExtension();
        extension.start(context);

        // Host thu hồi dịch vụ khi kết thúc vòng đời extension.
        publisher.revoke();
        try {
            context.events().publish("Thông điệp sau khi dừng");
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
    }

    // Hợp đồng công khai dùng chung giữa host và plugin.
    public interface Extension {
        void start(PluginContext context);
    }

    public interface PluginContext {
        PluginConfig config();
        EventPublisher events();
        Instant now();
    }

    public interface EventPublisher {
        void publish(String message);
    }

    public record PluginConfig(String greeting, int maxEvents) {
        public PluginConfig {
            Objects.requireNonNull(greeting, "greeting");
            if (greeting.isBlank() || maxEvents < 1 || maxEvents > 10) {
                throw new IllegalArgumentException("Cấu hình không hợp lệ");
            }
        }
    }

    // Các lớp triển khai thuộc host; không nằm trong API công khai.
    private static final class SimpleContext implements PluginContext {
        private final PluginConfig config;
        private final EventPublisher events;
        private final Clock clock;

        private SimpleContext(PluginConfig config,
                              EventPublisher events,
                              Clock clock) {
            this.config = Objects.requireNonNull(config);
            this.events = Objects.requireNonNull(events);
            this.clock = Objects.requireNonNull(clock);
        }

        @Override
        public PluginConfig config() {
            return config;
        }

        @Override
        public EventPublisher events() {
            return events;
        }

        @Override
        public Instant now() {
            return clock.instant();
        }
    }

    private static final class ScopedPublisher implements EventPublisher {
        private final String pluginId;
        private final int quota;
        private int sent;
        private boolean active = true;

        private ScopedPublisher(String pluginId, int quota) {
            this.pluginId = Objects.requireNonNull(pluginId);
            this.quota = quota;
        }

        @Override
        public synchronized void publish(String message) {
            Objects.requireNonNull(message, "message");
            if (!active) {
                throw new IllegalStateException("dịch vụ đã bị thu hồi");
            }
            if (message.length() > 120) {
                throw new IllegalArgumentException("thông điệp quá dài");
            }
            if (sent >= quota) {
                throw new IllegalStateException("vượt hạn mức sự kiện");
            }

            sent++;
            System.out.println("[" + pluginId + "] " + message);
        }

        private synchronized void revoke() {
            active = false;
        }
    }

    private static final class GreetingExtension implements Extension {
        @Override
        public void start(PluginContext context) {
            context.events().publish(
                    context.config().greeting() + ", Lan @ " + context.now()
            );
            context.events().publish(
                    context.config().greeting() + ", Minh @ " + context.now()
            );

            try {
                context.events().publish("Lượt thứ ba");
            } catch (IllegalStateException ex) {
                System.out.println("Từ chối: " + ex.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 PluginContextDemo.java
java PluginContextDemo
~~~

Kết quả:

~~~text
[greeting] Xin chào, Lan @ 2026-01-01T00:00:00Z
[greeting] Xin chào, Minh @ 2026-01-01T00:00:00Z
Từ chối: vượt hạn mức sự kiện
Từ chối: dịch vụ đã bị thu hồi
~~~

**Diễn giải:**

- Host tạo PluginConfig và ScopedPublisher, rồi chỉ trao PluginContext cho extension. Extension không nhận được đối tượng cấu hình toàn cục hay tham chiếu tới broker thật.
- Hai lần publish đầu tiên thành công. Lần thứ ba bị kiểm tra hạn mức trong ScopedPublisher từ chối, dù plugin vẫn gọi được phương thức trên interface.
- Sau khi host gọi revoke(), ngay cả một tham chiếu EventPublisher còn được giữ lại cũng không thể dùng để xuất thêm thông điệp qua adapter này.
- Phương thức now() đi qua hợp đồng và dùng Clock do host lựa chọn; thời gian trong ví dụ là cố định để kết quả tái lập.
- synchronized làm thao tác kiểm tra hạn mức, tăng bộ đếm và thu hồi quyền nhất quán giữa nhiều thread trong phạm vi ví dụ. Trong sản phẩm thật, không nên giữ khóa nội bộ khi gọi ra dịch vụ chậm hoặc callback của plugin.

Các kiểu công khai đang được lồng trong một tệp để ví dụ tự chạy. Trong dự án thực, hãy đưa Extension, PluginContext, PluginConfig và EventPublisher thành các kiểu public trong một **module/API JAR ổn định**; giữ SimpleContext và ScopedPublisher bên host. Đừng sao chép các lớp triển khai host sang plugin.

## 5. Cấu trúc tích hợp trong hệ plugin thực tế

Một luồng khởi tạo thông thường:

1. **Khám phá extension** qua manifest, ServiceLoader hoặc cơ chế nạp plugin mà host hỗ trợ. Khám phá chỉ xác định ứng viên; chưa cấp quyền truy cập dịch vụ.
2. **Xác định danh tính và chính sách từ phía host**, chẳng hạn pluginId đã được kiểm tra, phiên bản API tương thích, tập quyền mà người quản trị cho phép.
3. **Đọc cấu hình rồi tạo bản nhìn riêng**: lọc khóa, áp mặc định, kiểm tra kiểu và khoảng hợp lệ; từ chối khởi động khi thiếu dữ liệu bắt buộc.
4. **Tạo adapter dịch vụ riêng theo phạm vi**: gắn pluginId/tenantId do host chọn, chỉ cho phép thao tác đã duyệt, giới hạn tài nguyên và bổ sung audit.
5. **Tạo context và gọi lifecycle**: start(context), sau đó phục vụ các lần gọi của plugin. Không cấp toàn bộ service registry chỉ vì plugin có phương thức start.
6. **Dừng và dọn dẹp**: ngăn yêu cầu mới, hủy hoặc chờ công việc đang chạy theo chính sách, thu hồi capability, đóng tài nguyên liên quan và giải phóng tham chiếu để hỗ trợ unload.

Các trạng thái thường hữu ích là CREATED -> ACTIVE -> STOPPING -> CLOSED. Quy định rõ lệnh gọi trong STOPPING bị từ chối hay được hoàn thành, timeout của tác vụ đang chạy và hành vi khi stop được gọi nhiều lần. Context nên có vòng đời gắn với một phiên plugin, tránh tái sử dụng adapter cũ cho một phiên đã khởi động lại.

Nếu hệ thống có nhiều tenant hoặc nhiều phiên chạy cho cùng plugin, phạm vi phải chứa cả tenant/session khi phù hợp. Không dùng một singleton adapter vô tình chia sẻ quyền, quota hoặc dữ liệu giữa các tenant.

## 6. Các ranh giới cần làm rõ

### Ranh giới quyền truy cập và an toàn dữ liệu

- **Tối thiểu hóa dữ liệu**: plugin chỉ thấy phần cấu hình phục vụ chức năng được duyệt; tránh chuyển khóa bí mật, thông tin cá nhân không cần thiết hoặc đối tượng hạ tầng đang giữ credential.
- **Không tin vào tham số do plugin tự khai**: kiểm tra quyền đối với tài nguyên và tenant trong host. Ví dụ, DocumentReader.read(id) phải xác định id thuộc tập cho phép; đừng chỉ kiểm tra khi tạo context rồi bỏ qua từng lần đọc.
- **Không lộ phương thức mở rộng quyền**: một interface chỉ nên cấp nghiệp vụ cụ thể; không cung cấp getHost(), getApplicationContext(), getAllServices(), unwrap() hoặc quyền sửa danh sách cho phép.
- **Theo dõi chi phí**: quota, timeout, kích thước payload, số tác vụ đồng thời và bộ nhớ phải phù hợp với tài nguyên host. Tránh một plugin chiếm toàn bộ pool xử lý chung.
- **Giữ lỗi an toàn**: thông báo trả về plugin không cần chứa chuỗi kết nối, token, đường dẫn máy chủ hoặc stack trace hạ tầng. Host vẫn có thể lưu audit nội bộ với kiểm soát truy cập phù hợp.

Nếu plugin thực sự cần thao tác với dịch vụ có thông tin xác thực, ưu tiên host đứng ra thực hiện thay vì trao credential thô. Nếu bắt buộc dùng token được cấp riêng, cần quyền hạn hẹp, thời hạn ngắn, kế hoạch xoay vòng và ngăn ghi token vào log.

### Ranh giới kỹ thuật không đồng nghĩa sandbox bảo mật

API có giới hạn giúp giảm mức phụ thuộc và quản trị đường truy cập **thông qua API đó**, nhưng **không phải sandbox an toàn cho mã Java bất kỳ**. Plugin chạy cùng JVM vẫn có thể tự gọi các API Java khác, mở kết nối mạng, truy cập tài nguyên theo quyền của tiến trình hoặc dùng reflection tùy môi trường. ClassLoader/module boundary hỗ trợ tổ chức và tương thích lớp; chúng không tự tạo tường ngăn bảo mật với mã không tin cậy. Không dựa vào Java Security Manager như cơ chế sandbox hiện đại.

Đối với plugin do nguồn không tin cậy cung cấp, cần đánh giá chạy **khác process hoặc container** với quyền hệ điều hành, filesystem, mạng, tài nguyên và giao thức IPC được kiểm soát. Context trong trường hợp đó có thể được biểu diễn thành dữ liệu cấu hình cùng các RPC capability thay vì chuyển trực tiếp tham chiếu đối tượng Java.

## 7. Vòng đời, bất đồng bộ và khả năng mở rộng

Khi plugin giữ context để làm việc nền, host phải xác định rõ:

- Adapter vẫn kiểm tra trạng thái ACTIVE và quyền tại **thời điểm gọi**, không chỉ ở start(). Thu hồi quyền là một chuyển trạng thái có hiệu lực cho những yêu cầu tiếp theo.
- Tác vụ đang xử lý lúc stop được phép hoàn tất hay phải hủy; nếu dùng executor, cần có cơ chế cancellation, deadline và giới hạn công việc còn treo.
- Cơ chế thread safety của quota và trạng thái. Ví dụ trên dùng synchronized để giữ đúng đếm số lần; hệ thống có I/O nên tách kiểm tra trạng thái, cập nhật quota và lời gọi mạng sao cho không khóa lâu.
- Context không nên chứa tài nguyên có vòng đời ngắn hơn công việc đã cấp; các handle đã đóng phải trả lỗi rõ ràng, không lặng lẽ thực hiện ở phiên mới.
- Nếu cập nhật policy lúc chạy, dịch vụ phải phản ánh việc thu hồi/mở quyền theo hợp đồng. Snapshot config bất biến không thay thế kiểm tra policy động tại dịch vụ.

Một plugin chậm, treo hoặc ném exception phải được xử lý bằng timeout, cô lập lỗi, thống kê và chính sách phục hồi ở biên host. Không để lỗi callback từ plugin phá hỏng đường xử lý chính của ứng dụng.

## 8. Phiên bản hợp đồng và kiểm thử

Khi host và plugin có thể phát hành độc lập, các interface, record, enum, exception và ngữ nghĩa dịch vụ là một phần của API cần được quản lý tương thích. Nêu rõ phiên bản tối thiểu/tối đa mà plugin hỗ trợ, chính sách bổ sung phương thức, mặc định và xử lý khả năng chưa được cấp. Tăng phiên bản hợp đồng nếu thay đổi gây mất tương thích; tránh plugin truy cập nội bộ host để né hợp đồng.

Các nhóm kiểm thử nên có:

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Cấu hình đúng/thiếu/sai kiểu | Host kiểm tra và tạo context đúng hoặc từ chối khởi động có lý do |
| Plugin không được cấp dịch vụ | Capability vắng mặt hoặc lệnh gọi bị từ chối có kiểm soát |
| Plugin cố đọc tài nguyên khác tenant | Host chặn tại thao tác đọc/ghi thực tế |
| Quota đã đạt ngưỡng | Các lần gọi tiếp theo bị từ chối, kể cả gọi đồng thời |
| Plugin đã dừng | Handle cũ không tiếp tục thực hiện thao tác qua host adapter |
| Reload cấu hình hoặc chính sách | Semantics snapshot/cập nhật/thu hồi đúng như hợp đồng |
| Phiên bản plugin không tương thích | Host báo lỗi tại khâu nạp, không đợi lỗi runtime |
| Plugin ném lỗi hoặc xử lý chậm | Host cô lập lỗi, tôn trọng timeout và dọn tài nguyên |

Trong kiểm thử đơn vị plugin, có thể thay EventPublisher bằng fake và now() bằng đồng hồ cố định để kiểm tra logic mà không cần dựng hạ tầng thật. Trong kiểm thử tích hợp host, dùng adapter thật hoặc test double có thực thi **cùng chính sách**, đặc biệt với quyền, quota và trạng thái sau revoke().

## 9. Những sai lầm thường gặp

1. **Chuyển nguyên DI container/ApplicationContext cho plugin**: plugin có thể tìm bean không thuộc hợp đồng, khó giữ tương thích và khó kiểm tra quyền. Hãy cấp facade/interface chuyên biệt.
2. **Coi Map không sửa được là đã an toàn**: Map.copyOf chỉ khóa cấu trúc map, không làm bất biến một object mutable nằm trong value. Dùng kiểu giá trị bất biến hoặc defensive copy cho cả cấu trúc lồng nhau.
3. **Giao plugin tự báo danh tính hay tenant trong mỗi lệnh gọi**: tạo nguy cơ giả mạo. Host gắn identity trong adapter và kiểm tra tài nguyên tại server side.
4. **Chỉ kiểm tra quyền khi tạo context**: chính sách có thể đổi; cần kiểm tra tại biên thực thi và hỗ trợ thu hồi.
5. **Lộ DataSource, ExecutorService hoặc HTTP client không giới hạn**: rất khó áp quota và audit đúng theo từng plugin. Bao bọc bằng dịch vụ hẹp có giới hạn rõ.
6. **Không định nghĩa stop/unload**: tham chiếu dịch vụ cũ vẫn được gọi, thread bị rò rỉ hoặc task thực thi vào phiên mới. Cần trạng thái, revoke và cleanup.
7. **Nhầm giới hạn API với cách ly mã độc**: interface không ngăn plugin gọi trực tiếp Java/OS API nếu chạy cùng quyền trong JVM; cần cách ly tiến trình khi mô hình đe dọa đòi hỏi.
8. **Ràng buộc plugin với chi tiết triển khai host**: thay đổi nội bộ làm hỏng plugin. Giữ API JAR riêng, versioning và contract tests.

## 10. Checklist thiết kế

Trước khi công bố một PluginContext mới, trả lời rõ: plugin cần **giá trị cấu hình nào** và phải được kiểm tra thế nào; cần **hành động nào** qua dịch vụ; **ai cấp danh tính/phạm vi**; quyền và quota được kiểm tra **ở đâu và mỗi khi nào**; xử lý **cấu hình đổi, stop, timeout, concurrent call** ra sao; API có **tương thích phiên bản** với plugin đã phát hành không; và mức **cách ly an toàn** có phù hợp với độ tin cậy của mã plugin không.

Một ngữ cảnh tốt giúp extension làm đủ chức năng được giao qua hợp đồng nhỏ, dễ giả lập và dễ kiểm tra; host giữ trách nhiệm cấp quyền, áp chính sách, sở hữu hạ tầng và thu hồi khả năng sử dụng khi cần.