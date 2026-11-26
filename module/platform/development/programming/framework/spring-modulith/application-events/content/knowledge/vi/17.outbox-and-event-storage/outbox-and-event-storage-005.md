# Xóa hoặc lưu lịch sử

Trong module SPRING_MODULITH_APPLICATION_EVENTS, application events giúp các module Spring Modulith giao tiếp qua sự kiện, giảm phụ thuộc trực tiếp và giữ ranh giới nghiệp vụ rõ ràng. Event Publication Registry lưu trạng thái giao sự kiện tới listener để ứng dụng có thể nhận biết publication đã hoàn tất hay còn dang dở. Khi hệ thống chạy lâu, số bản ghi này tăng dần; vì vậy cần quyết định bản ghi nào được xóa, bản ghi nào cần lưu và lịch sử nào phải được đưa sang kho riêng.

Nguyên tắc quan trọng là chọn chính sách theo mục đích của dữ liệu. Lịch sử phục vụ vận hành và khôi phục giao sự kiện có vòng đời khác với lịch sử nghiệp vụ phục vụ kiểm toán hoặc tra cứu.

## 1. Phân biệt lịch sử giao sự kiện và lịch sử nghiệp vụ

| Loại dữ liệu | Mục đích | Chính sách phù hợp |
| --- | --- | --- |
| Event Publication Registry | Theo dõi publication của event tới từng listener target; nhận biết publication đã hoàn tất hay còn chưa hoàn tất để hỗ trợ khôi phục | Giữ publication chưa hoàn tất; giữ publication hoàn tất trong một khoảng thời gian vận hành rồi có thể xóa |
| Audit log hoặc kho lịch sử nghiệp vụ | Trả lời ai đã làm gì, vào thời điểm nào, đối tượng nghiệp vụ thay đổi ra sao | Lưu theo yêu cầu nghiệp vụ, kiểm toán, pháp lý và chính sách bảo vệ dữ liệu |
| Event store phục vụ replay | Lưu event có định danh và phiên bản schema để dựng lại trạng thái hoặc phát lại theo quy trình đã kiểm soát | Quản lý như một kho dữ liệu riêng, có versioning, quyền truy cập và chính sách lưu trữ rõ ràng |

Event Publication Registry là cơ chế theo dõi độ tin cậy của việc giao sự kiện. Một event có thể được gửi tới nhiều listener, và mỗi publication target cần có trạng thái xử lý tương ứng. Khi listener xử lý thành công, publication được đánh dấu hoàn tất. Nếu listener lỗi hoặc tiến trình dừng giữa chừng, publication chưa hoàn tất có thể được dùng cho quá trình kiểm tra và phát lại.

Registry không nên được xem là sổ kiểm toán nghiệp vụ hoặc event store dài hạn. Mục tiêu của registry là theo dõi việc giao và xử lý event. Bản ghi có thể bị xóa theo chính sách retention; cấu trúc payload cũng có thể thay đổi khi ứng dụng nâng cấp. Nếu nghiệp vụ cần biết lịch sử thay đổi trong nhiều năm hoặc cần replay có kiểm soát, hãy lưu dữ liệu đó trong một mô hình riêng.

## 2. Quyết định khi nào xóa và khi nào giữ

Chỉ đưa publication đã hoàn tất vào diện dọn dẹp. Publication chưa hoàn tất cần được giữ lại cho tới khi listener xử lý thành công hoặc đội vận hành giải quyết rõ ràng nguyên nhân. Không đánh dấu hoàn tất thủ công chỉ để làm sạch bảng, vì thao tác đó có thể che giấu một event chưa được xử lý.

Thời gian giữ publication hoàn tất nên dài hơn khoảng thời gian mà đội vận hành thường cần để điều tra sự cố. Hãy cân nhắc thời gian phát hiện lỗi, thời gian khôi phục dịch vụ, thời gian hỗ trợ người dùng và yêu cầu đối soát. Ví dụ 30 ngày có thể là điểm bắt đầu cho một hệ thống, nhưng không phải giá trị mặc định phù hợp với mọi nghiệp vụ.

| Trạng thái | Điều kiện | Hành động |
| --- | --- | --- |
| Đã hoàn tất, còn trong retention | Listener đã xử lý thành công và bản ghi vẫn nằm trong cửa sổ điều tra | Tiếp tục giữ trong registry |
| Đã hoàn tất, quá retention | Không còn nhu cầu khôi phục hoặc điều tra từ registry | Xóa; nếu cần dấu vết dài hạn thì lưu bản ghi phù hợp sang kho lịch sử riêng trước |
| Chưa hoàn tất | Listener lỗi, chưa chạy, hoặc ứng dụng dừng trước khi ghi nhận hoàn tất | Giữ lại, theo dõi tuổi bản ghi, retry hoặc điều tra |
| Cần kiểm toán hoặc replay dài hạn | Có yêu cầu nghiệp vụ độc lập với vòng đời giao sự kiện | Lưu vào audit log hoặc event store riêng; không phụ thuộc vào retention của registry |

Trước khi đặt retention, hãy trả lời ba câu hỏi:

1. Trong bao lâu đội vận hành cần tra cứu publication đã hoàn tất để điều tra sự cố?
2. Khi một listener ngừng hoạt động lâu hơn dự kiến, khoảng thời gian retry và xử lý thủ công là bao lâu?
3. Có yêu cầu lưu payload hoặc metadata vì kiểm toán, đối soát hay replay không?

Nếu câu trả lời thứ ba là có, hãy xác định rõ trường dữ liệu cần giữ. Không sao chép toàn bộ payload theo thói quen nếu chỉ cần event ID, loại event, thời điểm, listener target và kết quả xử lý. Payload có thể chứa dữ liệu cá nhân hoặc thông tin nghiệp vụ nhạy cảm.

## 3. Dọn dẹp publication hoàn tất bằng Spring Modulith

Spring Modulith cung cấp EventPublicationRegistry để quản lý vòng đời publication. Có thể đặt lịch dọn dẹp định kỳ và gọi phương thức xóa publication đã hoàn tất cũ hơn một khoảng thời gian. Ví dụ sau minh họa một tác vụ chạy mỗi ngày; giá trị retention được cấu hình theo môi trường:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.modulith.events.EventPublicationRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class CompletedPublicationCleanup {

    private final EventPublicationRegistry registry;
    private final Duration retention;

    CompletedPublicationCleanup(
            EventPublicationRegistry registry,
            @Value("${app.events.retention.completed-publications:30d}")
            Duration retention) {
        this.registry = registry;
        this.retention = retention;
    }

    @Scheduled(cron = "${app.events.cleanup-cron:0 0 3 * * *}")
    void clean() {
        registry.deleteCompletedPublicationsOlderThan(retention);
    }
}
~~~

Ví dụ cấu hình:

~~~yaml
app:
  events:
    retention:
      completed-publications: 30d
    cleanup-cron: '0 0 3 * * *'
~~~

Ứng dụng cần bật scheduling bằng cấu hình phù hợp, chẳng hạn @EnableScheduling. Trong môi trường nhiều instance, mỗi instance có thể kích hoạt cùng lịch. Nếu tác vụ có chi phí lớn hoặc yêu cầu chỉ một instance thực hiện tại một thời điểm, hãy dùng cơ chế khóa phân tán hoặc leader election phù hợp với hạ tầng.

Phương thức xóa của registry được thiết kế cho publication đã hoàn tất. Tránh tự viết lệnh DELETE trực tiếp trên bảng lưu publication vì thao tác SQL có thể bỏ qua quy tắc trạng thái hoặc chi tiết triển khai của persistence provider. Hãy dùng API mà phiên bản Spring Modulith của ứng dụng cung cấp.

## 4. Lưu trữ lịch sử trước khi xóa

Khi có yêu cầu lưu dấu vết dài hạn, hãy xây dựng bước archive độc lập trước tác vụ purge:

1. Xác định mục đích lưu: kiểm toán, đối soát, phân tích vận hành hay replay. Mỗi mục đích cần tập trường dữ liệu và thời hạn khác nhau.
2. Chọn metadata ổn định, ví dụ event ID, event type, thời điểm phát sinh, publication target, thời điểm hoàn tất, correlation ID và kết quả xử lý. Chỉ lưu payload khi có lý do cụ thể.
3. Ghi dữ liệu vào kho lưu trữ riêng với quyền truy cập, mã hóa và thời hạn lưu phù hợp.
4. Xác minh số lượng bản ghi, định danh và khả năng đọc lại dữ liệu đã archive.
5. Chỉ sau khi archive thành công mới cho phép tác vụ retention xóa publication tương ứng khỏi registry.

Archive metadata không tự động tạo ra khả năng replay. Nếu cần phát lại event, kho lưu trữ phải giữ payload có thể giải mã, định danh event, phiên bản schema và quy trình replay có kiểm soát. Listener được gọi lại phải có tính idempotent hoặc có cơ chế chống xử lý trùng, vì replay có thể khiến cùng một nghiệp vụ được gửi tới listener nhiều lần.

Với audit log, hãy mô hình hóa sự kiện theo ngôn ngữ nghiệp vụ. Ví dụ, thay vì chỉ lưu rằng một listener đã hoàn tất, audit record nên mô tả hành động nghiệp vụ như đơn hàng được xác nhận, người thực hiện và đối tượng bị tác động. Điều này giúp lịch sử vẫn có ý nghĩa ngay cả khi cấu trúc event nội bộ hoặc danh sách listener thay đổi.

## 5. Quan sát và xử lý ngoại lệ

Dọn dẹp là một tác vụ vận hành nên cần được quan sát như các tác vụ nền khác. Theo dõi tối thiểu:

- Số publication chưa hoàn tất và tuổi của publication chưa hoàn tất lâu nhất.
- Số publication đã hoàn tất đang được giữ trong registry và dung lượng lưu trữ.
- Thời điểm chạy cleanup gần nhất, trạng thái thành công/thất bại và thời gian chạy.
- Số bản ghi đã archive hoặc xóa, nếu tầng lưu trữ cung cấp số liệu này.
- Lỗi khi archive hoặc cleanup, để có thể dừng purge và điều tra.

Đặt cảnh báo khi publication chưa hoàn tất vượt quá ngưỡng tuổi phù hợp với SLA xử lý. Khi cleanup thất bại, giữ nguyên dữ liệu và thử lại sau khi xử lý nguyên nhân. Log nên ưu tiên event ID, event type, target và correlation ID; tránh ghi toàn bộ payload vào log vì có thể làm lộ dữ liệu nhạy cảm.

## 6. Những sai lầm cần tránh

- Xóa mọi publication cũ theo ngày phát hành mà không kiểm tra trạng thái hoàn tất.
- Rút ngắn retention dưới thời gian cần thiết để phát hiện, retry và điều tra sự cố.
- Đánh dấu publication chưa xử lý thành hoàn tất chỉ để giảm số lượng bản ghi.
- Dùng Event Publication Registry làm nguồn lịch sử kiểm toán dài hạn.
- Xóa publication trước khi xác minh bản archive đã được ghi và đọc lại thành công.
- Replay từ archive mà không kiểm tra phiên bản schema và tính idempotent của listener.

## Kết luận

Giữ publication chưa hoàn tất cho tới khi xử lý xong; giữ publication hoàn tất đủ lâu cho nhu cầu vận hành rồi dọn dẹp theo retention. Khi cần lịch sử dài hạn, hãy archive dữ liệu nghiệp vụ cần thiết vào kho riêng trước khi xóa. Cách phân chia này giúp Event Publication Registry tiếp tục phục vụ việc giao sự kiện đáng tin cậy, đồng thời bảo đảm yêu cầu kiểm toán, đối soát và replay có nơi lưu trữ phù hợp.
