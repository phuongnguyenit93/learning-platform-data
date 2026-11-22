# Khả năng tương thích và thích nghi với môi trường

Một ứng dụng Java chạy tốt trên máy lập trình viên nhưng gặp lỗi khi triển khai: đường dẫn lưu báo cáo chỉ tồn tại trên Linux, phiên bản JDK của máy chủ không hỗ trợ một API mới, hoặc hệ thống đối tác không đọc được dữ liệu trả về. Mỗi lỗi xuất hiện ở một vị trí khác nhau, nhưng cùng gợi ra một câu hỏi về chất lượng: **mã nguồn có hoạt động đúng trong những môi trường và với những hệ thống mà nó phải phục vụ hay không?**

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu các thuộc tính khiến mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Bài này thuộc nhóm **Các chiều chất lượng** và tập trung vào hai năng lực có quan hệ chặt chẽ: **khả năng tương thích** với hệ thống khác và **khả năng thích nghi** khi môi trường thực thi thay đổi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **tính tương tác**, **khả năng cùng tồn tại**, **khả năng thích nghi với môi trường** và **tương thích ngược**.
- Nhận ra những giả định ngầm về hệ điều hành, JDK, cấu hình, dữ liệu, tài nguyên và giao diện tích hợp.
- Áp dụng cách viết mã Java giúp ứng dụng thích nghi với đường dẫn, múi giờ và cấu hình triển khai.
- Thiết lập tiêu chí đánh giá và kiểm thử phù hợp với môi trường, phiên bản và các hệ thống thực sự cần hỗ trợ.

## 1. Hiểu đúng hai nhóm khả năng

**Khả năng tương thích (compatibility)** thể hiện việc phần mềm hoạt động phù hợp khi **cùng sử dụng môi trường hoặc trao đổi thông tin với phần mềm khác**. Hai khía cạnh thường gặp là:

1. **Khả năng cùng tồn tại (co-existence):** các ứng dụng dùng chung tài nguyên mà không gây ảnh hưởng không chấp nhận được lên nhau, chẳng hạn không tranh chấp cổng dịch vụ hoặc chiếm hết CPU, RAM, kết nối cơ sở dữ liệu.
2. **Khả năng tương tác (interoperability):** các hệ thống trao đổi và sử dụng thông tin đúng ý nghĩa thông qua API, thông điệp, tệp hoặc giao thức đã thống nhất.

**Khả năng thích nghi với môi trường (adaptability)** thể hiện mức độ phần mềm có thể hoạt động trong **những môi trường đã xác định**, với số thay đổi mã nguồn và công sức điều chỉnh hợp lý. Môi trường có thể khác về hệ điều hành, JDK, cơ sở dữ liệu, cấu hình triển khai, vùng ngôn ngữ hoặc hạ tầng mạng. Khả năng này gắn với nhóm thuộc tính thường được gọi là **tính di động (portability)**; nó không đồng nghĩa với việc một ứng dụng phải chạy được trên mọi nền tảng.

Ngoài ra, **tương thích ngược (backward compatibility)** nói về **quan hệ giữa các phiên bản**: sau khi nâng cấp, các cách sử dụng hoặc định dạng dữ liệu cũ đã cam kết hỗ trợ có tiếp tục hoạt động hay không. Đây là một vấn đề cụ thể thường xuất hiện trong cả tích hợp lẫn chuyển đổi môi trường.

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Cùng tồn tại | Có hoạt động ổn định khi chia sẻ tài nguyên? | Hai dịch vụ trên cùng máy không xung đột cổng hoặc vượt giới hạn bộ nhớ |
| Tương tác | Có trao đổi và hiểu dữ liệu thống nhất? | Dịch vụ bán hàng gửi đúng đơn vị tiền tệ cho dịch vụ thanh toán |
| Thích nghi với môi trường | Có chạy đúng ở các môi trường được yêu cầu hỗ trợ? | Một chương trình chạy trên Linux và Windows khi được cấu hình phù hợp |
| Tương thích ngược | Phiên bản mới có giữ được hợp đồng cũ trong phạm vi hỗ trợ? | API thêm trường tùy chọn mà ứng dụng khách cũ vẫn xử lý được |

**Điểm cần nhớ:** một phần mềm có thể chạy trên nhiều hệ điều hành nhưng tích hợp API kém; ngược lại, nó có thể trao đổi dữ liệu rất tốt với hệ thống đối tác nhưng chỉ chạy được trong một môi trường triển khai. Vì vậy phải đánh giá các khía cạnh riêng.

## 2. Vì sao khả năng này liên quan trực tiếp đến chất lượng mã?

Mã nguồn thường chứa các **giả định ngầm** chỉ đúng trong môi trường phát triển:

- Một thư mục luôn tồn tại và tiến trình luôn có quyền ghi.
- Máy chủ dùng cùng múi giờ, ngôn ngữ và bộ mã ký tự với máy của lập trình viên.
- Mọi nơi đều có cùng phiên bản JDK hoặc cùng cấu hình cơ sở dữ liệu.
- Các dịch vụ khác trả về trường JSON ở một định dạng cố định và không bao giờ thêm trường mới.
- Cổng mạng, kết nối cơ sở dữ liệu và bộ nhớ luôn sẵn có.

Khi môi trường thay đổi, những giả định này biến thành lỗi. Nếu chúng rải rác khắp chương trình, sửa lỗi phải đụng đến nhiều nơi, khó kiểm thử và dễ gây hồi quy. Ngược lại, **cấu hình tách khỏi logic nghiệp vụ**, **hợp đồng giao tiếp rõ ràng** và **phụ thuộc được cô lập** giúp mã dễ hiểu, sửa đổi và vận hành hơn.

Mối quan hệ này có thể quan sát theo chuỗi:

~~~
Giả định ngầm trong mã
        ↓
Thay đổi môi trường / phiên bản / đối tác
        ↓
Hành vi khác dự kiến hoặc tích hợp thất bại
        ↓
Cần sửa gấp, tăng rủi ro và chi phí bảo trì
~~~

Mục tiêu thiết kế không phải tạo thêm lớp trừu tượng cho mọi khả năng tưởng tượng, mà là **đưa các biến động thực sự cần hỗ trợ vào những chỗ dễ cấu hình, kiểm tra và thay thế**.

## 3. Thích nghi với hệ điều hành và đường dẫn tệp

Giả sử ứng dụng phải xuất báo cáo CSV ở máy của lập trình viên và trên máy chủ triển khai. Đoạn mã sau phụ thuộc vào một đường dẫn cụ thể:

~~~java
Path output = Path.of("/opt/service/output/report.csv");
Files.writeString(output, csvContent);
~~~

Đường dẫn trên có thể không tồn tại, không ghi được ở môi trường khác hoặc không có ý nghĩa giống nhau trên các hệ điều hành. Vấn đề nằm ở **giả định cố định về cấu trúc thư mục và quyền truy cập**.

Một cách linh hoạt hơn là nhận thư mục đích từ cấu hình triển khai:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReportExporter {
    public void export(String csvContent) throws Exception {
        String reportDir = System.getenv("REPORT_DIR");
        if (reportDir == null || reportDir.isBlank()) {
            throw new IllegalStateException("REPORT_DIR must be configured");
        }

        Path output = Path.of(reportDir).resolve("report.csv");
        Files.createDirectories(output.getParent());
        Files.writeString(output, csvContent, StandardCharsets.UTF_8);
    }
}
~~~

Trong ví dụ này:

- `REPORT_DIR` được cấu hình cho từng môi trường; mã nghiệp vụ không phải sửa khi đổi thư mục.
- `Path.resolve()` ghép các thành phần đường dẫn theo quy tắc của hệ điều hành.
- `StandardCharsets.UTF_8` quy định rõ cách mã hóa dữ liệu.
- Ngoại lệ khi thiếu cấu hình xuất hiện sớm và có thông báo cụ thể, tránh âm thầm ghi vào nơi không mong muốn.

Tuy nhiên, đoạn mã vẫn cần **quyền ghi hợp lệ**, đủ dung lượng đĩa và quy định rõ cách xử lý khi tệp đã tồn tại. Tính thích nghi chỉ đạt yêu cầu khi cả mã lẫn cấu hình triển khai đã được kiểm chứng.

## 4. Thích nghi với thời gian, vùng ngôn ngữ và dữ liệu

Cùng một thời điểm có thể được hiển thị khác nhau ở Việt Nam và Nhật Bản. Tương tự, dấu phân cách thập phân hoặc cách sắp xếp văn bản có thể khác theo `Locale`. Nếu logic nghiệp vụ ngầm dựa vào múi giờ mặc định của máy chủ, việc chuyển môi trường có thể làm sai hạn thanh toán, ngày báo cáo hoặc lịch chạy tác vụ.

Ví dụ, lưu mốc thời gian tuyệt đối bằng `Instant`, rồi chuyển sang múi giờ yêu cầu khi hiển thị:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant createdAt = Instant.parse("2026-11-16T02:30:00Z");

ZonedDateTime vietnamTime = createdAt.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

`Instant` biểu diễn một thời điểm cụ thể. `ZoneId` làm rõ cách diễn giải thời gian theo khu vực. Cách này tránh phụ thuộc vào múi giờ mặc định của máy, nhưng **quy tắc nghiệp vụ** vẫn phải quyết định khi nào nên dùng thời điểm tuyệt đối và khi nào cần ngày/giờ địa phương (ví dụ lịch mở cửa lúc 09:00 mỗi ngày).

Với số tiền hoặc dữ liệu truyền giữa hệ thống, cần xác định rõ **đơn vị, kiểu dữ liệu và định dạng trao đổi**. Chẳng hạn, chuỗi `"1,500"` có thể được hiểu là một nghìn năm trăm hoặc một phẩy năm tùy quy ước. Nên dùng định dạng máy đọc có quy tắc cố định; chỉ định dạng theo `Locale` ở ranh giới giao diện với người dùng.

## 5. Tương tác giữa các hệ thống: đúng cú pháp chưa đủ

Giả sử dịch vụ đặt hàng trả về:

~~~json
{
  "orderId": "A-102",
  "totalAmount": 150000,
  "currency": "VND",
  "createdAt": "2026-11-16T02:30:00Z"
}
~~~

Để dịch vụ khác **sử dụng đúng** dữ liệu này, cả hai phía phải thống nhất ít nhất:

- `orderId` là định danh chuỗi, không tự động chuyển sang số.
- `totalAmount` là số tiền theo đơn vị đã quy định (ví dụ VND nguyên đơn vị), không phải đơn vị nhỏ hơn không được mô tả.
- `currency` xác định đồng tiền; không suy đoán theo ngôn ngữ người dùng.
- `createdAt` là thời điểm ISO 8601 có chỉ rõ múi giờ (`Z` biểu thị UTC).
- Cách phản hồi khi thiếu dữ liệu, sai định dạng, hết thời gian chờ hoặc yêu cầu được gửi lại.

Hai hệ thống có thể giao tiếp HTTP thành công và cùng parse được JSON nhưng **vẫn không tương tác đúng về ngữ nghĩa**. Ví dụ, nếu một phía coi `totalAmount` là đồng và phía kia coi là xu, giá trị có thể sai gấp 100 lần mà không phát sinh lỗi cú pháp.

### Khi hợp đồng API thay đổi

Giả sử phiên bản mới bổ sung:

~~~json
{
  "orderId": "A-102",
  "totalAmount": 150000,
  "currency": "VND",
  "createdAt": "2026-11-16T02:30:00Z",
  "note": "Giao giờ hành chính"
}
~~~

Thêm một trường **tùy chọn** có thể giữ tương thích ngược **nếu** hợp đồng và ứng dụng khách cũ cho phép bỏ qua trường chưa biết. Một ứng dụng khách kiểm tra schema nghiêm ngặt có thể vẫn bị lỗi. Vì vậy **không thể chỉ nhìn JSON để kết luận** việc thay đổi là an toàn.

Các thay đổi dễ gây phá vỡ hợp đồng gồm đổi tên trường, thay đổi kiểu dữ liệu, đổi ý nghĩa đơn vị, biến trường tùy chọn thành bắt buộc hoặc thay quy tắc trả lỗi. Khi cần thay đổi như vậy, nhóm phát triển có thể phải dùng API versioning, thời gian chuyển đổi hoặc bộ chuyển đổi dữ liệu.

## 6. Cùng tồn tại và chia sẻ tài nguyên

Một dịch vụ hoạt động đúng khi chạy một mình vẫn có thể gây sự cố khi cùng tồn tại với hệ thống khác. Ví dụ:

| Tình huống | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Hai dịch vụ dùng cùng cổng mạng | Một dịch vụ không khởi động được | Cấu hình cổng, kiểm tra xung đột khi triển khai |
| Mỗi yêu cầu tạo thêm kết nối DB nhưng không giải phóng | Cạn kết nối, ảnh hưởng dịch vụ khác | Giới hạn pool, đóng tài nguyên, theo dõi số kết nối |
| Tác vụ nền chiếm toàn bộ CPU | Tăng độ trễ của ứng dụng cùng máy | Giới hạn tài nguyên, điều phối tác vụ, kiểm thử dưới tải |
| Nhiều tiến trình ghi cùng một tệp tạm | Hỏng dữ liệu hoặc ghi đè | Dùng tệp riêng, cơ chế đồng bộ hoặc kho lưu trữ phù hợp |
| Gọi hệ thống đối tác không có timeout | Tài nguyên xử lý bị giữ quá lâu | Timeout, giới hạn đồng thời, retry có kiểm soát |

Khả năng cùng tồn tại vì vậy liên quan cả đến **cách viết mã** (quản lý tài nguyên, đóng kết nối, giới hạn retry) lẫn **cấu hình vận hành** (CPU, RAM, cổng, tài khoản, quyền và chính sách cô lập).

## 7. Các thay đổi môi trường thường bị bỏ sót

| Thứ thay đổi | Ví dụ sai lệch | Bằng chứng cần có |
| --- | --- | --- |
| Phiên bản JDK | Biên dịch trên JDK 21 nhưng triển khai trên JDK 17 với API không được hỗ trợ | Biên dịch và chạy test trên phiên bản đích; dùng `--release` phù hợp khi biên dịch Java |
| Hệ điều hành và hệ thống tệp | Đường dẫn cứng, phân biệt hoa/thường khác nhau, quyền truy cập khác nhau | Kiểm thử tác vụ đọc/ghi trên OS đích |
| Cơ sở dữ liệu | Câu SQL phụ thuộc cú pháp, quy tắc collation, kiểu dữ liệu hoặc transaction | Kiểm thử tích hợp với phiên bản và cấu hình DB đích |
| Mạng và hạ tầng | DNS, proxy, chứng chỉ TLS, timeout, thứ tự khởi động dịch vụ | Kiểm thử kết nối, lỗi mạng và khả năng phục hồi |
| Vùng ngôn ngữ | Parse ngày/tháng hoặc số thập phân theo mặc định máy | Kiểm thử các `Locale`, `ZoneId` đã hỗ trợ |
| Phiên bản API bên ngoài | Trường bị đổi tên, mã lỗi mới hoặc giới hạn tốc độ | Contract test và kiểm thử tích hợp với phiên bản API hỗ trợ |
| Tài nguyên vận hành | Giới hạn bộ nhớ, CPU, số kết nối khác ở production | Kiểm thử tải và đo số liệu ở cấu hình tương đương |

**Một lưu ý với Java:** khả năng chạy đa nền tảng của JVM giúp giảm phụ thuộc hệ điều hành, nhưng không tự động giải quyết đường dẫn, thư viện native, cấu hình, mã hóa, mạng hay khác biệt phiên bản JDK. Đóng gói ứng dụng vào container cũng hỗ trợ tái lập môi trường nhưng không loại bỏ khác biệt về kiến trúc CPU, tài nguyên, quyền truy cập và hạ tầng bên ngoài.

## 8. Thiết kế mã để giảm chi phí thích nghi

Một số thực hành thường có ích:

**Tách cấu hình khỏi logic nghiệp vụ.** Đường dẫn, endpoint, timeout, thông tin kết nối và giới hạn tài nguyên cần có nơi cấu hình rõ ràng. Giá trị bắt buộc phải được kiểm tra khi khởi động để phát hiện sớm sai lệch. Không đưa bí mật truy cập vào mã nguồn.

**Đưa các phụ thuộc thay đổi về ranh giới rõ ràng.** Logic tính giá không cần biết cách gọi HTTP tới đối tác; nó nên nhận dữ liệu theo kiểu miền đã thống nhất. Khi đối tác thay API, thay đổi được giới hạn ở lớp tích hợp.

**Ưu tiên API chuẩn và quy ước tường minh.** Dùng `Path` cho đường dẫn, `StandardCharsets` cho mã hóa, `java.time` cho thời gian. Ghi rõ định dạng, đơn vị, múi giờ và quy tắc xử lý lỗi ở hợp đồng dữ liệu.

**Quản lý phiên bản và thay đổi hợp đồng.** Xác định phiên bản JDK, thư viện, API và cơ sở dữ liệu được hỗ trợ. Kiểm tra tương thích trước khi nâng cấp. Không coi tất cả nâng cấp dependency là thay đổi nội bộ không ảnh hưởng người dùng.

**Thiết kế cho khả năng kiểm thử.** Có thể truyền `Clock`, client HTTP hoặc nguồn cấu hình vào thành phần cần kiểm thử, giúp mô phỏng những điều kiện khác nhau mà không phải sửa môi trường thật.

Không phải dự án nào cũng cần hỗ trợ nhiều cơ sở dữ liệu hay tất cả hệ điều hành. Thêm lớp trừu tượng không dùng đến có thể làm giảm khả năng hiểu và bảo trì. **Chỉ nên tối ưu cho những biến động nằm trong yêu cầu sản phẩm hoặc rủi ro đáng kể đã xác định.**

## 9. Đánh giá bằng tiêu chí có thể kiểm chứng

Một lời nhận xét như “ứng dụng tương thích tốt” quá mơ hồ. Hãy lập **ma trận hỗ trợ** thể hiện môi trường, hợp đồng và điều kiện chấp nhận. Bảng dưới đây là **ví dụ giả định**, không phải mức chuẩn cho mọi hệ thống:

| Phạm vi cam kết | Tiêu chí chấp nhận | Cách xác minh |
| --- | --- | --- |
| Ubuntu 22.04, JDK 17 | Khởi động, đọc/ghi báo cáo và xử lý luồng chính thành công | Integration test trên môi trường mục tiêu |
| Windows 11, JDK 17 | Không dùng đường dẫn cố định của Linux | Kiểm thử xuất báo cáo trên Windows |
| API khách hàng phiên bản v1 | Khách cũ vẫn đọc được phản hồi sau khi bổ sung trường `note` | Consumer contract test với khách v1 |
| Hệ thống đặt hàng và thanh toán | Đồng nhất mã tiền tệ, đơn vị tiền và quy tắc xử lý lỗi | Kiểm thử hợp đồng hai phía, test giao dịch |
| Chạy cùng dịch vụ khác | Không vượt giới hạn CPU/RAM và kết nối cho phép ở tải dự kiến | Kiểm thử tải, theo dõi tài nguyên |

Quy trình đánh giá nên gồm:

1. **Xác định phạm vi hỗ trợ:** hệ điều hành, runtime, database, phiên bản API, cấu hình và đặc điểm tải nào thực sự cần.
2. **Liệt kê hợp đồng và giả định:** định dạng dữ liệu, quyền truy cập, timezone, cổng, timeout, dependency.
3. **Kiểm thử nhiều mức:** unit test cho logic, contract test cho giao tiếp, integration test cho môi trường đích, kiểm thử tải cho khả năng cùng tồn tại.
4. **Thử cả các tình huống bất lợi:** thiếu biến môi trường, thư mục không có quyền ghi, đối tác chậm hoặc trả trường mới, máy chủ thiếu tài nguyên.
5. **Ghi nhận kết quả theo cặp điều kiện và phiên bản:** test chạy trên JDK 21 không chứng minh ứng dụng chạy trên JDK 17; test với mock không thay thế hoàn toàn tích hợp thực tế.
6. **Lặp lại khi môi trường hoặc hợp đồng thay đổi:** bổ sung test vào CI/CD đối với những tổ hợp được cam kết để phát hiện hồi quy.

Việc kiểm thử mọi tổ hợp có thể rất tốn kém. Nhóm cần ưu tiên các môi trường đang phục vụ người dùng, các phiên bản được cam kết, các ranh giới tích hợp quan trọng và những khác biệt có khả năng gây lỗi cao.

## 10. Bài tập tình huống

Một dịch vụ Java tạo hóa đơn có các đặc điểm sau:

- Ghi tệp vào `/home/dev/invoices`.
- Lấy `LocalDate.now()` để xác định “ngày chốt hóa đơn” mà không thống nhất múi giờ nghiệp vụ.
- Gửi trường `amount` dưới dạng chuỗi `"1,500"` cho dịch vụ kế toán.
- Không giới hạn số lần thử lại khi hệ thống kế toán không phản hồi.

**Câu hỏi 1.** Mỗi đặc điểm có thể gây ra rủi ro gì đối với khả năng thích nghi, tương tác hoặc cùng tồn tại?

**Câu hỏi 2.** Hãy đề xuất một thay đổi mã hoặc hợp đồng và một cách kiểm chứng cho mỗi rủi ro.

### Gợi ý đáp án

| Vấn đề | Hướng cải thiện | Kiểm chứng |
| --- | --- | --- |
| Đường dẫn gắn với máy phát triển | Đưa thư mục xuất hóa đơn vào cấu hình, dùng `Path` và kiểm tra quyền ghi | Thử trên môi trường triển khai và trường hợp không có quyền ghi |
| Ngày chốt theo múi giờ máy | Xác định múi giờ nghiệp vụ, truyền `Clock` hoặc `ZoneId` tường minh | Test quanh thời điểm chuyển ngày ở các múi giờ |
| Số tiền truyền bằng chuỗi nhập nhằng | Quy định đơn vị tiền, định dạng máy đọc và trường `currency` | Contract test với bên kế toán cho cả trường hợp biên |
| Retry vô hạn | Đặt timeout, số lần retry tối đa, backoff và giới hạn đồng thời phù hợp | Mô phỏng đối tác chậm, kiểm tra số lần gọi và tài nguyên |

## Tổng kết

Khả năng tương thích trả lời câu hỏi **phần mềm có thể cùng tồn tại và tương tác đúng với các hệ thống liên quan hay không**. Khả năng thích nghi trả lời **phần mềm có thể hoạt động trong các môi trường cần hỗ trợ với công sức thay đổi hợp lý hay không**. Cả hai đều góp phần làm cho mã **đáng tin cậy, dễ hiểu và dễ thay đổi**.

Chất lượng ở hai chiều này không thể xác nhận chỉ bằng việc “chạy được trên máy tôi”. Cần xác định rõ **phạm vi hỗ trợ**, công khai các **hợp đồng và giả định**, thiết kế các **ranh giới có thể cấu hình**, rồi kiểm chứng bằng **kiểm thử trên môi trường và phiên bản phù hợp**.
