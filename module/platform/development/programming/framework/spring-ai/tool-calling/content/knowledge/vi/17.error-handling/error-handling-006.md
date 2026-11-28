# Yêu cầu bổ sung dữ kiện thay vì tự đoán đối số còn thiếu

Khi mô hình chuẩn bị gọi một công cụ, nó phải tạo arguments theo JSON Schema mà ứng dụng công bố. Nếu người dùng chưa cung cấp một dữ kiện cần thiết, mô hình có thể hỏi lại trước khi gọi công cụ. Tuy nhiên, nếu schema đánh dấu trường đó là bắt buộc trong khi mô hình không có căn cứ để biết giá trị, mô hình có thể tự tạo ra một giá trị có vẻ hợp lý. Spring AI cảnh báo rõ rủi ro này: trường `required` buộc mô hình cung cấp giá trị; nếu không có cách xác định, mô hình có thể bịa ra giá trị.

Vì vậy, ứng dụng cần phối hợp ba lớp: mô tả tool và chỉ dẫn hội thoại yêu cầu hỏi lại khi thiếu dữ kiện; JSON Schema phản ánh đúng khả năng bỏ qua trường; và callback/service kiểm tra đầu vào trước khi thực hiện nghiệp vụ. Không được xem một argument hợp lệ về cú pháp là bằng chứng người dùng đã cung cấp hoặc xác nhận giá trị đó.

Bài học thuộc chương Xử lý lỗi của module Spring AI Tool Calling. Trọng tâm là cách nhận biết thông tin thiếu hoặc mơ hồ, hỏi người dùng bổ sung, sau đó mới thực thi công cụ với arguments có căn cứ.

Sau bài học, bạn có thể:

- Phân biệt dữ kiện thiếu, dữ kiện mơ hồ và dữ kiện sai định dạng.
- Hiểu tác động của `required` trong JSON Schema và `@ToolParam`.
- Viết chỉ dẫn để mô hình hỏi lại thay vì tự điền giá trị.
- Dùng kết quả nghiệp vụ `NEEDS_CLARIFICATION` để callback chặn thực thi khi thiếu dữ kiện.
- Phân biệt yêu cầu làm rõ với lỗi kỹ thuật cần `ToolExecutionException`.
- Kiểm thử để bảo đảm tool không tạo side effect khi arguments chưa đầy đủ hoặc chưa được xác nhận.

## 1. Vì sao mô hình có thể đoán một đối số còn thiếu?

Giả sử người dùng nói: “Đặt lịch họp với Linh vào thứ Ba tuần sau”. Công cụ tạo cuộc họp cần email người tham dự và thời điểm bắt đầu có múi giờ. Câu nói hiện tại chưa cho biết email của Linh và có thể chưa xác định được giờ họp. Nếu tool schema yêu cầu hai trường này, mô hình phải tạo giá trị cho cả hai để hình thành tool call.

Một giá trị do mô hình tạo ra có thể trông hợp lý nhưng không có căn cứ:

- Mô hình có thể đoán email từ tên người tham dự.
- Mô hình có thể tự chọn 9 giờ sáng dù người dùng chưa nói giờ.
- Mô hình có thể hiểu “thứ Ba tuần sau” theo tuần hoặc múi giờ khác với ý người dùng.
- Mô hình có thể chọn một địa chỉ hoặc mã khách hàng giống với dữ liệu từng thấy trong ví dụ.

Nếu công cụ dùng những giá trị này để gửi lời mời, đặt lịch hoặc cập nhật dữ liệu, lỗi sẽ trở thành hành động nghiệp vụ thật. Vì vậy, không được để mô hình lấp chỗ trống bằng phỏng đoán chỉ nhằm hoàn thành schema.

## 2. Phân biệt dữ kiện thiếu, mơ hồ và sai định dạng

Ba trường hợp này cần cách xử lý khác nhau:

| Trường hợp | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| Thiếu dữ kiện | “Đặt cuộc họp với Linh” nhưng chưa có email hoặc thời gian | Hỏi người dùng cung cấp trường còn thiếu. |
| Mơ hồ | “Thứ Sáu tới” khi có thể hiểu là ngày thứ Sáu gần nhất hoặc thứ Sáu của tuần kế tiếp | Hỏi để xác nhận ngày cụ thể. |
| Sai định dạng | Người dùng đưa giờ `25:90` hoặc email không hợp lệ | Giải thích dữ liệu chưa hợp lệ và yêu cầu nhập lại. |
| Đã có đủ căn cứ | Email đã được người dùng nêu rõ và thời gian đã xác định kèm múi giờ | Có thể gọi tool sau khi kiểm tra các điều kiện còn lại. |

Không nên hỏi lại một dữ kiện đã có rõ ràng trong lịch sử hội thoại hoặc có thể lấy từ nguồn tin cậy mà ứng dụng được phép sử dụng. Nhưng cũng không nên suy ra một giá trị chỉ vì nó phổ biến hoặc có vẻ hợp lý. Nếu có nhiều cách hiểu ảnh hưởng đến kết quả, hãy hỏi người dùng chọn.

## 3. JSON Schema required không phải cơ chế hỏi người dùng

Spring AI tạo JSON Schema từ tham số method hoặc kiểu input của function. Theo mặc định, các tham số tool là bắt buộc. Có thể làm tham số tùy chọn bằng `@ToolParam(required = false)` hoặc `@Nullable`.

Ví dụ:

```java
class MeetingTools {

    @Tool(description = "Tạo cuộc họp theo email người tham dự và thời điểm bắt đầu")
    public MeetingResult createMeeting(
            @ToolParam(description = "Email chính xác của người tham dự", required = false)
            String attendeeEmail,
            @ToolParam(
                    description = "Thời điểm bắt đầu ISO-8601 có offset, ví dụ 2026-12-08T09:00:00+07:00",
                    required = false)
            String startAt) {
        // Kiểm tra trước khi gọi dịch vụ lịch.
        return createOnlyWhenComplete(attendeeEmail, startAt);
    }
}
```

Trong ví dụ, `attendeeEmail` và `startAt` là tùy chọn ở cấp JSON Schema. Điều đó chỉ cho phép mô hình bỏ qua trường khi chưa có giá trị. Hai dữ kiện vẫn bắt buộc về mặt nghiệp vụ để tạo cuộc họp; callback phải từ chối tạo cuộc họp khi chúng còn thiếu.

Đây là điểm cần phân biệt:

- **Required trong schema:** mô hình được yêu cầu gửi trường đó khi gọi tool.
- **Optional trong schema:** mô hình có thể bỏ trường nếu chưa có giá trị.
- **Required trong nghiệp vụ:** service không được thực hiện tác vụ nếu thiếu dữ kiện cần thiết.

Một trường có thể optional trong schema nhưng vẫn bắt buộc trong nghiệp vụ. Cách này cho phép ứng dụng nhận biết trường bị bỏ trống, trả yêu cầu làm rõ và không thực hiện hành động.

Không đánh dấu tất cả trường là optional. Chỉ dùng cách này cho dữ kiện có thể thiếu hoặc chưa xác định tại thời điểm mô hình quyết định gọi tool. Những trường có thể lấy chắc chắn từ dữ liệu người dùng hoặc nguồn đáng tin cậy vẫn có thể khai báo required. Tuy nhiên, callback luôn phải kiểm tra runtime.

## 4. Viết mô tả tool để yêu cầu hỏi lại

Mô tả tool nên nêu rõ điều kiện gọi và các giá trị tuyệt đối không được tự suy đoán. Mô tả ngắn, cụ thể thường hữu ích hơn một đoạn hướng dẫn chung chung.

```java
@Tool(
    name = "create_meeting",
    description = "Tạo cuộc họp sau khi đã có email chính xác của người tham dự "
            + "và thời điểm bắt đầu rõ ràng kèm múi giờ. "
            + "Không đoán email, giờ hoặc múi giờ. Nếu thiếu hay mơ hồ, "
            + "hãy hỏi người dùng trước và chưa gọi công cụ."
)
public MeetingResult createMeeting(
        @ToolParam(description = "Email do người dùng cung cấp hoặc được xác minh từ danh bạ", required = false)
        String attendeeEmail,
        @ToolParam(description = "Thời điểm ISO-8601 có UTC offset; không tự chọn giờ", required = false)
        String startAt) {
    // Validation và thực thi được trình bày ở phần sau.
}
```

Mô tả tham số cũng cần chỉ ra nguồn dữ liệu được chấp nhận:

- Email phải được người dùng nêu rõ hoặc lấy từ danh bạ mà ứng dụng có quyền tra cứu.
- Thời gian phải có ngày, giờ và múi giờ rõ ràng.
- Nếu người dùng chỉ nêu một phần, không tự điền phần còn lại.
- Không dùng giá trị mặc định ngầm cho dữ kiện có thể làm thay đổi hành động.

Mô tả tool là hướng dẫn cho mô hình, không phải kiểm soát bảo mật. Callback vẫn phải xác thực và kiểm tra đầy đủ trước khi gọi service.

## 5. Đặt quy tắc hỏi lại trong system prompt

Để mô hình hiểu hành vi hội thoại, hãy đưa quy tắc rõ ràng vào system message. Ví dụ:

```java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultSystem("""
                Bạn là trợ lý lên lịch họp.

                Trước khi gọi create_meeting, hãy kiểm tra email người tham dự
                và thời điểm bắt đầu có múi giờ trong yêu cầu hiện tại hoặc
                lịch sử hội thoại đã được người dùng xác nhận.

                Nếu thiếu hoặc mơ hồ bất kỳ dữ kiện nào, hãy hỏi người dùng
                một câu ngắn để bổ sung. Không tự tạo email, giờ họp, ngày
                hoặc múi giờ. Không gọi công cụ cho đến khi có đủ dữ kiện.

                Chỉ dùng thông tin đã được người dùng cung cấp rõ ràng hoặc
                dữ liệu được ứng dụng xác minh từ nguồn tin cậy.
                """)
        .build();
```

System prompt giúp mô hình lựa chọn hỏi lại trước khi gọi tool. Tuy nhiên, prompt không bảo đảm tuyệt đối mô hình luôn tuân thủ. Nhà cung cấp model có thể trả arguments thiếu, sai hoặc tự tạo giá trị. Do đó, không dùng prompt làm lớp kiểm tra cuối cùng.

## 6. Ví dụ hội thoại: hỏi trước khi gọi tool

Người dùng:

> Đặt lịch họp với Linh vào thứ Ba tuần sau.

Trợ lý cần nhận ra dữ kiện chưa đủ và hỏi:

> Bạn cho mình email của Linh và giờ bắt đầu cuộc họp được không? Mình sẽ dùng múi giờ Việt Nam nếu bạn xác nhận.

Người dùng:

> Email là linh@example.com, ngày 1 tháng 12 lúc 9 giờ sáng theo giờ Việt Nam.

Khi ngày, giờ và múi giờ đã rõ, trợ lý mới tạo arguments đầy đủ, ví dụ:

```json
{
  "attendeeEmail": "linh@example.com",
  "startAt": "2026-12-01T09:00:00+07:00"
}
```

Ví dụ ngày chỉ mang tính minh họa. Trong ứng dụng thật, hãy xác định ngày từ mốc thời gian và múi giờ rõ ràng; không sao chép ngày ví dụ vào request thực tế.

## 7. Phòng vệ ở callback: thiếu dữ kiện thì không gọi service

Ngay cả khi mô hình được hướng dẫn hỏi lại, callback vẫn phải kiểm tra arguments. Nếu thiếu dữ kiện, trả một kết quả nghiệp vụ có trạng thái `NEEDS_CLARIFICATION`. Kết quả này được gửi lại mô hình để nó hỏi người dùng ở lượt tiếp theo.

```java
public record MeetingResult(
        String status,
        List<String> missingFields,
        String clarificationQuestion,
        String meetingId) {
}
```

Method tool có thể kiểm tra trước khi thực hiện:

```java
@Component
public class MeetingTools {

    private final CalendarService calendarService;
    private final EmailPolicy emailPolicy;

    public MeetingTools(CalendarService calendarService, EmailPolicy emailPolicy) {
        this.calendarService = calendarService;
        this.emailPolicy = emailPolicy;
    }

    @Tool(
        name = "create_meeting",
        description = "Tạo cuộc họp khi có email chính xác và thời điểm bắt đầu rõ ràng. "
                + "Không đoán giá trị bị thiếu; nếu thiếu, trả trạng thái NEEDS_CLARIFICATION."
    )
    public MeetingResult createMeeting(
            @ToolParam(description = "Email người tham dự đã được người dùng cung cấp", required = false)
            String attendeeEmail,
            @ToolParam(description = "Thời điểm ISO-8601 có UTC offset", required = false)
            String startAt) {

        List<String> missing = new ArrayList<>();

        if (attendeeEmail == null || attendeeEmail.isBlank()) {
            missing.add("attendeeEmail");
        }
        if (startAt == null || startAt.isBlank()) {
            missing.add("startAt");
        }

        if (!missing.isEmpty()) {
            return new MeetingResult(
                    "NEEDS_CLARIFICATION",
                    missing,
                    "Vui lòng cung cấp email người tham dự và thời điểm bắt đầu "
                            + "có ngày, giờ và múi giờ rõ ràng.",
                    null);
        }

        OffsetDateTime meetingStart;
        try {
            meetingStart = OffsetDateTime.parse(startAt);
        }
        catch (DateTimeParseException exception) {
            return new MeetingResult(
                    "NEEDS_CLARIFICATION",
                    List.of("startAt"),
                    "Thời điểm chưa rõ định dạng. Vui lòng cung cấp ngày, giờ "
                            + "và UTC offset theo ISO-8601.",
                    null);
        }

        if (!emailPolicy.isValid(attendeeEmail)) {
            return new MeetingResult(
                    "NEEDS_CLARIFICATION",
                    List.of("attendeeEmail"),
                    "Email chưa hợp lệ. Vui lòng xác nhận lại địa chỉ email.",
                    null);
        }

        MeetingConfirmation created =
                calendarService.createMeeting(attendeeEmail, meetingStart);

        return new MeetingResult(
                "CREATED",
                List.of(),
                null,
                created.meetingId());
    }
}
```

Trong ví dụ, `EmailPolicy` là validator domain được inject từ ứng dụng. Điểm quan trọng là mọi nhánh thiếu hoặc sai định dạng đều trả về trước dòng gọi `calendarService.createMeeting(...)`. Vì thế, không có lịch họp nào được tạo khi dữ kiện chưa đủ.

Khi callback trả `NEEDS_CLARIFICATION`, `ToolCallingAdvisor` đưa kết quả về mô hình. Mô hình có thể đọc `status`, `missingFields` và `clarificationQuestion`, rồi hỏi người dùng. Sau khi người dùng trả lời, lượt hội thoại mới có thể tiếp tục với dữ kiện đã bổ sung.

Với pattern này, giữ `returnDirect = false` (mặc định) để kết quả `NEEDS_CLARIFICATION` quay lại mô hình và mô hình đặt câu hỏi. Nếu bật `returnDirect = true`, kết quả sẽ được trả thẳng cho caller; khi đó chính ứng dụng phải đọc trạng thái và hiển thị câu hỏi làm rõ, vì mô hình không còn nhận tool result.

## 8. Không dùng exception cho thiếu dữ kiện hội thoại bình thường

Thiếu thông tin để hoàn thành tác vụ thường là một trạng thái nghiệp vụ có thể dự đoán, không phải lỗi kỹ thuật. Nên trả kết quả có cấu trúc để mô hình hỏi tiếp.

| Tình huống | Cách xử lý |
| --- | --- |
| Thiếu email người tham dự | Trả `NEEDS_CLARIFICATION`, nêu trường cần bổ sung. |
| Ngày hoặc giờ mơ hồ | Trả `NEEDS_CLARIFICATION`, yêu cầu ngày/giờ rõ ràng. |
| Sai định dạng ngày giờ | Trả `NEEDS_CLARIFICATION` hoặc `INVALID_ARGUMENT` với hướng dẫn sửa. |
| Người dùng không có quyền tạo cuộc họp | Từ chối theo chính sách authorization; không hỏi để lấy thêm dữ liệu nhằm vượt quyền. |
| Calendar service timeout | Xử lý như lỗi thực thi; dùng exception processor và retry policy phù hợp. |
| Lỗi kết nối hoặc lỗi lập trình | Ghi nhận lỗi kỹ thuật, không giả dạng thành thiếu dữ kiện. |

Nếu callback ném `IllegalArgumentException`, Spring AI có thể chuyển runtime exception thành thông báo gửi lại mô hình tùy cấu hình `ToolExecutionExceptionProcessor`. Cách đó phù hợp với một số lỗi arguments, nhưng không rõ ràng bằng kết quả nghiệp vụ có cấu trúc cho luồng hỏi đáp. Tránh gửi stack trace, SQL hoặc thông tin nội bộ về mô hình.

## 9. Khi nào trường nên required, khi nào nên optional?

Hãy quyết định dựa trên nguồn dữ liệu thực tế và hành vi mong muốn:

| Loại trường | Ví dụ | Schema | Kiểm tra runtime |
| --- | --- | --- | --- |
| Luôn có thể xác định từ yêu cầu hoặc context đáng tin cậy | Mã đơn hàng người dùng vừa nêu rõ | Có thể `required` | Kiểm tra tồn tại và quyền truy cập. |
| Người dùng có thể chưa cung cấp | Email người tham dự | `required = false` nếu muốn cho phép hỏi lại qua callback | Thiếu thì trả `NEEDS_CLARIFICATION`. |
| Có thể suy ra từ cấu hình server, không phải mô hình | Tenant ID, actor ID | Không đưa vào schema | Lấy từ security context/`ToolContext`. |
| Có giá trị mặc định an toàn, được công bố rõ | Đơn vị hiển thị mặc định của tài khoản | Có thể optional | Áp dụng default từ cấu hình đáng tin cậy. |
| Mơ hồ và ảnh hưởng kết quả | “Thứ Sáu tới”, “buổi sáng” | Optional cho đến khi rõ | Hỏi người dùng chọn giá trị cụ thể. |

Không dùng default để lấp dữ kiện có ý nghĩa quyết định hành động, chẳng hạn người nhận, tài khoản đích, số tiền, ngày giao hoặc địa chỉ. Default chỉ phù hợp khi đó là chính sách sản phẩm rõ ràng, có thể giải thích và người dùng đã đồng ý.

## 10. Giá trị hợp lệ về cú pháp vẫn có thể là giá trị đoán

Callback có thể xác minh email đúng định dạng hoặc thời gian parse được, nhưng những kiểm tra đó không chứng minh người dùng đã cung cấp giá trị. Ví dụ `linh@example.com` là email hợp lệ về cú pháp; điều đó không chứng minh nó thuộc về người tên Linh trong yêu cầu.

Với dữ kiện quan trọng, ứng dụng cần kiểm tra nguồn gốc giá trị:

- Nếu lấy từ danh bạ, xác minh kết quả tra cứu khớp người được nhắc đến và nằm trong phạm vi quyền truy cập.
- Nếu lấy từ lịch sử hội thoại, yêu cầu giá trị đã được người dùng nói rõ hoặc xác nhận ở lượt trước.
- Nếu không thể xác minh nguồn, hỏi người dùng xác nhận giá trị trước khi thực hiện.
- Với thao tác có tác động, hiển thị chính xác các arguments sẽ được dùng và yêu cầu xác nhận qua cơ chế phía ứng dụng.

Không thêm trường `userConfirmed: true` vào JSON Schema để mô hình tự gửi. Mô hình không thể tự cấp bằng chứng xác nhận của người dùng. Trạng thái xác nhận phải được lưu hoặc tạo bởi ứng dụng, chẳng hạn trong conversation/session state hoặc một approval record phía server.

`@Tool(requiresConfirmation = true)` có thể tạm dừng vòng tool calling để ứng dụng lấy quyết định cho tool call. Confirmation phù hợp để duyệt các giá trị và hành động cụ thể trước khi chạy; nó không thay thế câu hỏi làm rõ khi arguments còn thiếu hoặc mơ hồ.

## 11. Hỏi đúng phần còn thiếu, không hỏi lại toàn bộ

Khi thiếu một vài trường, hãy hỏi ngắn gọn và liệt kê đúng dữ kiện cần bổ sung. Không bắt người dùng nhập lại thông tin đã có.

Ví dụ:

| Dữ kiện đã có | Dữ kiện thiếu | Câu hỏi phù hợp |
| --- | --- | --- |
| Người tham dự, ngày họp | Giờ bắt đầu | “Bạn muốn họp lúc mấy giờ?” |
| Email, giờ | Ngày cụ thể | “Bạn muốn chọn ngày nào? Cho mình ngày theo lịch cụ thể nhé.” |
| Ngày và giờ | Múi giờ chưa rõ | “Thời gian này theo múi giờ Việt Nam hay múi giờ khác?” |
| Đơn hàng | Địa chỉ giao mới thiếu số nhà | “Bạn bổ sung số nhà và tên đường giúp mình nhé.” |
| Sản phẩm | Số lượng | “Bạn muốn đặt bao nhiêu sản phẩm?” |

Nếu có nhiều trường thiếu, có thể hỏi chúng trong một câu để giảm số lượt trao đổi. Nhưng không hỏi những dữ kiện mà ứng dụng có thể xác định an toàn từ context đã xác thực.

## 12. Không nhầm thiếu dữ kiện với quyền truy cập

Một tool có thể thiếu dữ kiện nghiệp vụ hoặc người dùng không đủ quyền. Hai tình huống này không thể xử lý giống nhau:

- **Thiếu dữ kiện:** có thể hỏi người dùng bổ sung, ví dụ chưa có email người nhận.
- **Không đủ quyền:** phải từ chối theo chính sách, ví dụ người dùng không được phép xem tài khoản của người khác.
- **Dữ liệu không tồn tại:** trả trạng thái nghiệp vụ như `NOT_FOUND`; không tự thay bằng một ID khác.
- **Dữ liệu không rõ:** hỏi lại; không tự chọn một đối tượng gần giống.

Không hỏi người dùng cung cấp `actorId`, `tenantId`, role hoặc access token. Những thông tin đó thuộc phạm vi xác thực và `ToolContext` do server quản lý. Mô hình chỉ cung cấp arguments nghiệp vụ nằm trong schema.

## 13. Tránh thực thi một phần khi batch có nhiều tool call

Một model response có thể yêu cầu nhiều tool call cùng lúc. Nếu một tool trong batch phát hiện thiếu dữ kiện, tool đó có thể trả `NEEDS_CLARIFICATION`, nhưng những tool khác có thể đã chạy thành công. Với các thao tác có side effect, cần thiết kế để không tạo trạng thái một phần ngoài ý muốn.

Các nguyên tắc hữu ích:

- Không để mô hình gom nhiều thao tác phụ thuộc nhau thành các tool call song song nếu bước sau cần kết quả bước trước.
- Với quy trình cần đủ dữ kiện trước khi thực hiện, tạo một tool nghiệp vụ điều phối tuần tự hoặc kiểm tra đầy đủ trước khi tạo side effect.
- Dùng idempotency key cho thao tác có thể bị gọi lại sau khi người dùng bổ sung thông tin.
- Không coi việc một tool trong batch trả `NEEDS_CLARIFICATION` là lý do tự động rollback những tool khác đã chạy.
- Nếu cần xác nhận trước thao tác nhạy cảm, dùng cơ chế confirmation của tool; confirmation không thay thế việc hỏi dữ kiện còn thiếu.

## 14. Kiểm thử để chứng minh mô hình không tự đoán

Kiểm thử không chỉ xác minh mô hình có hỏi lại trong một ví dụ. Cần xác minh callback không tạo side effect khi input thiếu, sai hoặc chưa được xác nhận.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Người dùng chưa cung cấp email | Mô hình hỏi email; không gọi tool hoặc callback trả `NEEDS_CLARIFICATION`; calendar service không được gọi. |
| Người dùng chưa nêu giờ họp | Không tự chọn 9 giờ; hỏi người dùng. |
| Ngày tương đối còn mơ hồ | Hỏi ngày cụ thể trước khi tạo cuộc họp. |
| Arguments thiếu trường optional | Callback nhận null/thiếu trường và trả trạng thái cần làm rõ. |
| Arguments chứa email hoặc ngày giờ sai định dạng | Trả hướng dẫn sửa; không gọi service. |
| Mô hình gửi giá trị không có căn cứ nhưng hợp lệ về cú pháp | Không xem cú pháp hợp lệ là xác nhận; kiểm tra nguồn dữ liệu hoặc yêu cầu người dùng xác nhận. |
| Arguments đầy đủ và hợp lệ | Service được gọi đúng một lần. |
| Người dùng bổ sung thông tin ở lượt sau | Tool chỉ chạy sau khi dữ kiện được xác nhận. |
| Service timeout | Xử lý như lỗi kỹ thuật, không hỏi người dùng nhập lại trường hợp lệ. |
| Hai tool call trong một batch | Kiểm tra side effect từng tool và trạng thái một phần theo thiết kế. |

Ví dụ unit test cho nhánh thiếu dữ kiện:

```java
@Test
void asksForMissingEmailAndDoesNotCreateMeeting() {
    MeetingResult result = meetingTools.createMeeting(
            null,
            "2026-12-01T09:00:00+07:00");

    assertThat(result.status()).isEqualTo("NEEDS_CLARIFICATION");
    assertThat(result.missingFields()).containsExactly("attendeeEmail");
    assertThat(result.clarificationQuestion()).contains("email");

    verifyNoInteractions(calendarService);
}
```

Ví dụ kiểm thử này gọi method trực tiếp để xác minh ranh giới thực thi. Kiểm thử tích hợp với chat model giả có thể xác nhận system prompt và tool result khiến assistant tạo câu hỏi làm rõ. Kiểm thử với model/provider thật chỉ nên bổ sung để quan sát hành vi thực tế; không thay thế unit test của validation.

## 15. Quy trình xử lý một tool call an toàn

Khi nhận yêu cầu người dùng, hãy thực hiện theo trình tự:

1. Xác định tool cần dùng và liệt kê các arguments nghiệp vụ tối thiểu.
2. Đọc yêu cầu hiện tại và lịch sử hội thoại để xác định dữ kiện đã được cung cấp rõ ràng.
3. Dùng nguồn tin cậy của ứng dụng nếu có thể tra cứu dữ kiện và được phép làm vậy.
4. Nếu thiếu hoặc mơ hồ, hỏi người dùng trước khi gọi tool.
5. Công bố schema và mô tả tham số phản ánh đúng required/optional; không ép mô hình điền giá trị không thể biết.
6. Trong callback, kiểm tra null, blank, định dạng, miền giá trị và tính nhất quán.
7. Nếu thiếu dữ kiện, trả `NEEDS_CLARIFICATION` và không gọi service nghiệp vụ.
8. Chỉ sau khi arguments hợp lệ và đủ căn cứ mới thực hiện nghiệp vụ.
9. Phân quyền, audit và idempotency trước các thao tác có tác động.
10. Kiểm thử cả nhánh hỏi lại và nhánh thực thi thành công.

## Những điểm cần nhớ

- JSON Schema hướng dẫn mô hình tạo arguments; nó không bảo đảm mô hình không đoán.
- Spring AI mặc định coi các tham số tool là required. `@ToolParam(required = false)` hoặc `@Nullable` cho phép bỏ trường.
- Tài liệu Spring AI cảnh báo: nếu trường required mà mô hình không có căn cứ xác định, nó có thể tự tạo giá trị.
- Optional trong schema không có nghĩa optional trong nghiệp vụ. Callback có thể trả `NEEDS_CLARIFICATION` và dừng trước khi gọi service.
- Dùng mô tả tool và system prompt để yêu cầu hỏi lại khi thiếu hoặc mơ hồ; luôn kiểm tra lại ở runtime.
- Thiếu dữ kiện là trạng thái hội thoại/nghiệp vụ; lỗi hạ tầng hoặc lỗi thực thi cần exception handling riêng.
- Giá trị hợp lệ về cú pháp không chứng minh nguồn gốc; với thao tác có tác động, xác minh dữ liệu hoặc yêu cầu xác nhận do ứng dụng quản lý.
- Không thực hiện side effect khi arguments thiếu, sai hoặc chưa được xác nhận.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/2.1/api/tools.html)
- [Spring AI 2.1.0 Reference — JSON Schema và Required/Optional Parameters](https://docs.spring.io/spring-ai/reference/2.1/api/tools.html#_json_schema)
- [Spring AI 2.1.0 Reference — Exception Handling](https://docs.spring.io/spring-ai/reference/2.1/api/tools.html#_exception_handling)
- [Spring AI API — ToolParam](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/annotation/ToolParam.html)
- [Spring AI Reference — ChatClient](https://docs.spring.io/spring-ai/reference/2.1/api/chatclient.html)

Các ví dụ dựa trên Spring AI 2.1.0. Hành vi sinh arguments còn phụ thuộc model và provider; hãy kiểm thử với endpoint triển khai thực tế, nhưng luôn giữ validation phía ứng dụng làm ranh giới cuối cùng trước khi gọi dịch vụ nghiệp vụ.
