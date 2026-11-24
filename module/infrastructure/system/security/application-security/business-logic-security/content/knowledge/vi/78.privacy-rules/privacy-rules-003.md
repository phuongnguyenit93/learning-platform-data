# Sensitive field masking — Che các trường dữ liệu nhạy cảm

## Mục tiêu bài học

Trong chương **Privacy Rules**, sensitive field masking là việc biến đổi cách biểu diễn một trường nhạy cảm để chỉ tiết lộ phần thông tin được phép cho một người xem, mục đích và kênh sử dụng cụ thể. Ví dụ, nhân viên hỗ trợ có thể cần đối chiếu đuôi số liên hệ nhưng không cần đọc toàn bộ số đó.

Trong bảo mật logic nghiệp vụ, masking không chỉ là thay vài ký tự bằng dấu sao. Hệ thống phải quyết định người gọi có quyền đọc đối tượng nào, được thấy trường nào, thấy ở mức nào và có được chuyển sang xem đầy đủ hay không. Quyết định này còn phải đúng khi dữ liệu đi qua API, log, cache, export và tác vụ nền.

Sau bài học, bạn có thể:

- Phân biệt masking với phân quyền, loại bỏ trường, mã hóa và token hóa.
- Xây dựng chính sách tiết lộ theo đối tượng, trường, mục đích và kênh.
- Thiết kế DTO đầu ra, luồng xem đầy đủ và luồng cập nhật không ghi đè dữ liệu bằng giá trị đã che.
- Nhận diện rò rỉ qua dữ liệu phụ, tìm kiếm, cache và nhiều cách che khác nhau.
- Kiểm thử bằng kết quả quan sát được, thay vì chỉ xác nhận một hàm masking đã chạy.

## 1. Tình huống: một API đúng chức năng nhưng tiết lộ quá mức

Giả sử nền tảng có màn hình hỗ trợ khách hàng. Nhân viên được phép xem tên hiển thị, trạng thái đơn và một phần thông tin liên hệ để đối chiếu người gọi. API hiện trả toàn bộ thực thể khách hàng, còn giao diện dùng JavaScript để che số điện thoại.

Màn hình nhìn có vẻ an toàn, nhưng dữ liệu đầy đủ vẫn tồn tại trong phản hồi HTTP. Người dùng có thể đọc bằng công cụ mạng, một client khác hoặc chức năng xuất dữ liệu. Nếu thực thể cũng được ghi vào log khi xử lý lỗi, dữ liệu còn xuất hiện ở hệ thống quan sát mà nhân viên vận hành có thể truy cập.

Masking đúng cần diễn ra trước khi dữ liệu vượt qua ranh giới đến người nhận không được phép xem đầy đủ. Khi chính sách cho phép hiển thị phần đuôi, server tạo một biểu diễn riêng; nó không gửi kèm giá trị gốc trong thuộc tính ẩn, HTML, mã JavaScript hoặc một trường phụ khác.

Mặt khác, một khách hàng thuộc tổ chức B không trở thành đối tượng được phép đọc chỉ vì API che số điện thoại. Người gọi vẫn phải có quyền trên chính đối tượng trước khi bất kỳ biểu diễn nào của nó được trả về.

## 2. Masking bảo vệ điều gì và có giới hạn gì?

| Cơ chế | Vai trò | Điều cần phân biệt |
|---|---|---|
| Quyền theo đối tượng | Xác định người gọi có được truy cập đối tượng không | Không được bỏ qua vì dữ liệu đã che. |
| Quyền theo trường | Xác định trường nào được đọc và ở mức nào | Một người có quyền xem đơn chưa chắc có quyền xem toàn bộ liên hệ. |
| Masking | Chỉ hiển thị một phần hoặc biểu diễn giảm chi tiết | Phần còn thấy, độ dài và khả năng liên kết vẫn có thể nhạy cảm. |
| Redaction hoặc omission | Thay bằng ký hiệu trung tính hoặc bỏ hẳn trường | Cần chọn theo hợp đồng, kể cả việc có được tiết lộ trường tồn tại không. |
| Mã hóa | Bảo vệ dữ liệu khi lưu hoặc truyền theo mô hình khóa | Sau giải mã, ứng dụng vẫn có thể trả hoặc ghi log quá mức. |
| Token hóa | Thay giá trị bằng một tham chiếu trong một phạm vi | Token và bảng ánh xạ vẫn cần bảo vệ; token ổn định có thể liên kết các bản ghi. |
| Dữ liệu giả danh hoặc bản sao đã biến đổi | Giảm việc dùng giá trị gốc trong một số luồng | Không tự chứng minh rằng không thể nhận diện lại người liên quan. |

Không nên gọi một bộ dữ liệu là vô danh chỉ vì email hoặc số liên hệ đã có dấu sao. Kết hợp tên, địa chỉ, thời điểm giao dịch và phần đuôi còn lại có thể đủ để suy ra một người.

Masking động tạo biểu diễn cho từng ngữ cảnh trong khi dữ liệu gốc vẫn được lưu theo nhu cầu nghiệp vụ. Masking tĩnh tạo một bản sao đã biến đổi, chẳng hạn cho môi trường thử nghiệm. Bản sao tĩnh vẫn cần được đánh giá cả trường có cấu trúc, nội dung tự do và khả năng liên kết; chạy một hàm trên vài cột không bảo đảm mọi dữ liệu nhạy cảm đã biến mất.

## 3. Các invariant cần viết trước khi triển khai

Một thiết kế có thể bắt đầu từ các điều kiện bắt buộc sau:

1. Không trả bất kỳ biểu diễn đối tượng nào khi người gọi không có quyền truy cập đối tượng đó.
2. Không trả giá trị đầy đủ cho người nhận chỉ được phép xem biểu diễn đã che.
3. Không đưa giá trị gốc vào trường phụ, lỗi, log hoặc artifact thuộc cùng ngữ cảnh hạn chế.
4. Không cho client tự chọn mức tiết lộ bằng cách gửi `masked=false`, đổi vai trò hoặc khai một mục đích tùy ý.
5. Không ghi đè dữ liệu gốc bằng chuỗi hiển thị đã che trong luồng cập nhật.
6. Không biến thao tác xem đầy đủ thành quyền được cấp vô hạn hoặc dùng cho đối tượng khác.
7. Không trả dữ liệu đầy đủ từ cache hoặc kết quả cũ sau khi quyền hiện tại không còn cho phép.
8. Trường mới hoặc trường chưa có chính sách không tự được xuất ra theo cơ chế mặc định cho phép.

Các invariant này gắn quyền theo đối tượng với quyền theo trường và vòng đời nghiệp vụ. Một hàm xử lý chuỗi đúng vẫn không đủ nếu serializer, export hoặc luồng quản trị bỏ qua chúng.

## 4. Xác định chính sách tiết lộ

### 4.1. Đầu vào của quyết định

Một quyết định nên xét ít nhất:

```text
Chủ thể đã xác thực
+ quan hệ với đối tượng và tổ chức
+ hành động đang thực hiện
+ loại trường và mức nhạy cảm
+ mục đích đã được hệ thống chấp nhận
+ kênh nhận dữ liệu
+ trạng thái nghiệp vụ và các điều kiện phê duyệt
-> mức tiết lộ được phép
```

Ví dụ, mục đích “hỗ trợ đối chiếu liên hệ” có thể được cố định bởi endpoint hoặc gắn với hồ sơ hỗ trợ được xác minh. Một chuỗi `purpose=fraud_investigation` do client tự gửi không phải bằng chứng rằng người gọi được xem dữ liệu đầy đủ.

Vai trò là một đầu vào, không phải câu trả lời duy nhất. Cùng nhân viên hỗ trợ có thể được xem dữ liệu của tổ chức A nhưng không được xem B; một tác vụ giao hàng có thể cần thông tin giao hàng mà không cần lịch sử thanh toán.

### 4.2. Các mức đầu ra

| Mức | Biểu diễn | Khi có thể phù hợp |
|---|---|---|
| `OMIT` | Không có trường trong kết quả | Người nhận không cần trường hoặc không được biết trạng thái hiện diện của nó. |
| `REDACT` | Ký hiệu cố định như `[REDACTED]` | Được biết có một trường bị hạn chế theo hợp đồng, nhưng không được thấy thành phần của giá trị. |
| `MASKED` | Chỉ phần được phép, chẳng hạn `***6789` | Phần đó có ích cho đối chiếu và rủi ro tiết lộ đã được chấp nhận. |
| `FULL` | Giá trị đầy đủ | Quyền, mục đích, đối tượng và kênh đều cho phép. |

Không có quy tắc rằng mọi trường nhạy cảm đều nên giữ bốn ký tự cuối. Với mật khẩu, OTP, bí mật tích hợp hoặc token có thể sử dụng để truy cập, không mặc định hiển thị một phần chỉ vì cùng dùng một tiện ích masking. Trường không phục vụ đầu ra nên được loại khỏi đầu ra; chức năng cung cấp bí mật, nếu có, cần thiết kế riêng.

### 4.3. Ma trận ví dụ

Đây là chính sách minh họa cho một sản phẩm, không phải quy tắc chung cho mọi hệ thống:

| Ngữ cảnh | Quyền trên đối tượng | Liên hệ đầy đủ | Biểu diễn cần thiết |
|---|---|---|---|
| Khách hàng xem hồ sơ của chính mình | Đúng tài khoản và trạng thái truy cập | Có thể được phép theo luồng hồ sơ | Các trường đã được duyệt cho mục đích đó. |
| Nhân viên hỗ trợ xem danh sách | Đúng tổ chức, đúng quyền hỗ trợ | Không | Tên hiển thị và đuôi liên hệ được phép. |
| Nhân viên xem một hồ sơ nhạy cảm | Có quyền đối tượng nhưng thiếu quyền trường | Không | Bỏ trường hoặc ký hiệu cố định. |
| Worker gửi thông báo được cấp quyền | Đúng công việc và người nhận | Có thể cần để gửi | Chỉ liên hệ cần thiết trong kênh nội bộ được bảo vệ. |
| Người dùng tổ chức A yêu cầu khách hàng của B | Không | Không | Từ chối truy cập đối tượng, không trả bản ghi đã che. |
| Người xem báo cáo tổng hợp | Đúng phạm vi báo cáo | Không mặc nhiên | Chỉ dữ liệu phục vụ báo cáo, không kèm bản ghi gốc ngoài nhu cầu. |

## 5. Hợp đồng API phải tách biểu diễn khỏi dữ liệu ghi

### 5.1. Trả DTO có chủ đích

Các giá trị sau hoàn toàn là dữ liệu minh họa; chuỗi `DEMO-PHONE-6789` không phải số liên hệ thực tế:

```json
{
  "customerId": "cus_demo_17",
  "tenantId": "org_A",
  "displayName": "Khách hàng minh họa",
  "phone": "DEMO-PHONE-6789",
  "email": "customer.demo@example.test"
}
```

Một biểu diễn danh sách hỗ trợ có thể chỉ trả:

```json
{
  "customerId": "cus_demo_17",
  "displayName": "Khách hàng minh họa",
  "phoneDisplay": "***6789"
}
```

Không gửi kèm `phoneRaw`, `originalPhone`, một thuộc tính HTML chứa giá trị gốc hoặc dữ liệu đầy đủ trong một object lồng nhau. Chỉ đổi tên trường hoặc đặt nó ngoài vùng hiển thị không làm giảm quyền truy cập thực tế.

Tên như `phoneDisplay` giúp phân biệt biểu diễn với đầu vào dùng để cập nhật. Với ngày sinh, có thể cần một trường năm sinh riêng được chính sách cho phép; không đưa chuỗi dấu sao vào trường có hợp đồng là ngày hợp lệ. Tương tự, không thay một giá trị số nhạy cảm bằng số 0 nếu điều đó có thể được hiểu là giá trị nghiệp vụ thật.

### 5.2. Null, trường vắng và ký hiệu đã che mang ý nghĩa khác nhau

Nếu `null` có nghĩa là “chưa cung cấp”, không dùng cùng giá trị đó cho mọi trường hợp “không có quyền đọc” mà không giải thích hợp đồng. Tuy nhiên, trả thêm `hasValue=true` hoặc trạng thái `MASKED` cũng có thể tiết lộ một thông tin mà người nhận không được biết.

Chọn cách biểu diễn theo quyền được phép tiết lộ cả sự hiện diện của trường. Có trường nên luôn vắng đối với người không có quyền; có trường được phép hiển thị ký hiệu cố định. Không để khác biệt giữa phản hồi, lỗi và bộ đếm danh sách trở thành cách kiểm tra một thuộc tính nhạy cảm có tồn tại hay không.

### 5.3. Không gửi biểu diễn đã che ngược vào luồng ghi

Giả sử giao diện nhận `phoneDisplay = "***6789"`. Nếu nó gửi lại toàn bộ object qua một lệnh cập nhật và backend ánh xạ mọi thuộc tính vào thực thể, số liên hệ thật có thể bị thay bằng chuỗi hiển thị.

Thiết kế an toàn hơn:

- DTO đọc và DTO ghi là các hợp đồng riêng.
- Trường hiển thị được xem là chỉ đọc, không được ánh xạ vào dữ liệu gốc.
- Lệnh cập nhật chỉ chứa các trường được phép sửa và đã được xác thực theo miền dữ liệu.
- Với PATCH, phân biệt rõ trường không được gửi và yêu cầu xóa giá trị.
- Không coi client gửi lại dấu sao là bằng chứng cần giữ nguyên dữ liệu cũ; ý nghĩa giữ nguyên được thể hiện bằng việc không gửi thay đổi hoặc bằng lệnh tường minh.

Quyền đọc đầy đủ và quyền sửa cũng là hai quyền khác nhau. Một người có thể được gửi yêu cầu cập nhật qua một luồng xác minh mà không được đọc giá trị hiện tại; backend phải xử lý theo chính sách, không suy ra quyền này từ quyền kia.

## 6. Hàm masking trong Java: giới hạn phạm vi trách nhiệm

Một hàm giữ phần đuôi có thể được dùng sau khi chính sách đã cho phép loại biểu diễn đó:

```java
final class DisplayMask {
    private static final String REDACTED = "[REDACTED]";

    static String suffix(
            String value,
            int visibleCodePoints,
            int minimumCodePoints) {

        if (visibleCodePoints < 0
                || minimumCodePoints <= visibleCodePoints) {
            throw new IllegalArgumentException("Invalid mask configuration");
        }

        if (value == null) {
            return null;
        }

        int size = value.codePointCount(0, value.length());
        if (visibleCodePoints == 0 || size < minimumCodePoints) {
            return REDACTED;
        }

        int suffixStart = value.offsetByCodePoints(
            0, size - visibleCodePoints
        );
        return "***" + value.substring(suffixStart);
    }
}
```

Ví dụ với cấu hình minh họa `visibleCodePoints = 4`, `minimumCodePoints = 8`:

| Đầu vào | Kết quả |
|---|---|
| `DEMO-PHONE-6789` | `***6789` |
| `1234` | `[REDACTED]` |
| Chuỗi rỗng | `[REDACTED]` |
| `null` | `null`, chỉ dùng nếu hợp đồng cho phép tiết lộ trạng thái này |

Ngưỡng độ dài là cấu hình của từng loại trường, không phải quy tắc bảo mật phổ quát. Nếu giữ phần đuôi của một giá trị quá ngắn, hàm ngây thơ có thể tiết lộ toàn bộ giá trị; ở đây trường hợp đó bị thay bằng ký hiệu cố định.

Tiền tố cố định `***` không mã hóa trực tiếp độ dài phần bị che. Một chuỗi gồm số dấu sao bằng đúng số ký tự bị thay sẽ tiết lộ độ dài gốc. Dù vậy, phần đuôi và việc phân biệt giá trị ngắn vẫn có thể tiết lộ thông tin; chính sách phải cân nhắc điều đó trước khi chọn hàm.

Code point giúp không cắt giữa một cặp surrogate của Java, nhưng không đồng nghĩa giữ nguyên mọi cụm ký tự hiển thị phức tạp. Với trường có quy tắc định dạng như số liên hệ hoặc mã định danh, nên xử lý trên biểu diễn chuẩn đã được nghiệp vụ xác minh. Với văn bản tự do, bỏ trường hoặc redaction thường dễ kiểm soát hơn một công thức giữ đuôi chung.

Hàm trên không thực hiện phân quyền, không chuẩn hóa email, không kiểm tra tenant và không bảo đảm dữ liệu vô danh. Các tham số không được lấy tùy ý từ request. Kết quả vẫn phải được mã hóa đầu ra theo ngữ cảnh hiển thị; masking không thay thế biện pháp chống chèn nội dung hoặc XSS.

## 7. Tổ chức điểm thực thi tại backend

Một luồng đọc có thể được tổ chức như sau:

```text
Xác thực người gọi
  -> xác định tổ chức từ ngữ cảnh tin cậy
  -> tải thông tin tối thiểu để xét quyền đối tượng
  -> kiểm tra quyền trên đối tượng
  -> tính kế hoạch tiết lộ theo trường, mục đích và kênh
  -> tải những dữ liệu thực sự cần để dựng biểu diễn
  -> tạo DTO đầu ra bằng danh sách trường cho phép
  -> kiểm tra hợp đồng và serialize DTO
```

Giả mã Java minh họa:

```java
CustomerSummaryView getSupportSummary(Actor actor, CustomerId id) {
    CustomerAccessRef ref = customers.loadAccessRef(actor.tenantId(), id);
    authorization.requireRead(actor, ref);

    FieldPlan plan = privacyPolicy.plan(
        actor,
        ref,
        Purpose.SUPPORT_SUMMARY,
        Channel.API
    );

    CustomerDisplayData data = customers.loadForDisplay(ref, plan);
    return views.supportSummary(data, plan);
}
```

Đây là hợp đồng kiến trúc, không phải chương trình chạy độc lập. `Purpose.SUPPORT_SUMMARY` do luồng nghiệp vụ xác định; client không thể đổi thành một mục đích có quyền cao hơn bằng query parameter. Việc đọc và xét các trạng thái có ảnh hưởng tới quyền cần mức nhất quán phù hợp, đặc biệt ở luồng xem đầy đủ.

Ưu tiên không tải dữ liệu gốc nếu đầu ra không cần nó. Nếu phải tải để tạo phần đuôi, giữ dữ liệu đó trong phạm vi xử lý hẹp, không đưa vào object chung sẽ được serialize hoặc ghi log. Một lựa chọn khác là dùng projection được kiểm soát tại tầng truy vấn, nhưng vẫn phải áp dụng đúng chính sách người xem.

Không trả trực tiếp thực thể lưu trữ rồi chỉ dựa vào một annotation cố định. Annotation có thể hữu ích cho trường luôn bị cấm xuất, nhưng chính sách động còn phụ thuộc đối tượng, mục đích và kênh. Endpoint danh sách, chi tiết, GraphQL, export và API quản trị cần cùng một định nghĩa chính sách, dù mỗi nơi có DTO khác nhau.

Khi thêm trường mới vào thực thể, trường đó không được tự xuất hiện trong response. Cách dựng DTO theo danh sách cho phép giúp giảm nguy cơ vô tình mở rộng dữ liệu tiết lộ.

## 8. Luồng xem đầy đủ là một hành động nghiệp vụ riêng

Một nút “Hiện dữ liệu” có thể làm thay đổi mức tiết lộ, nên không nên chỉ điều khiển bằng trạng thái trong trình duyệt. Backend cần một hành động có quyền và phạm vi rõ ràng.

Ví dụ quy trình với trường nhạy cảm cao:

```text
Người dùng mở hồ sơ đã che
  -> yêu cầu xem một tập trường cụ thể
  -> server kiểm tra quyền đối tượng, quyền trường và mục đích
  -> xác minh bổ sung hoặc phê duyệt nếu chính sách yêu cầu
  -> kiểm tra lại điều kiện và trạng thái hiện hành
  -> ghi metadata của quyết định tiết lộ
  -> trả đúng các trường được cấp cho yêu cầu hiện tại
```

Nếu dùng phê duyệt hoặc bằng chứng xác minh, cần ràng buộc chúng với người xem, tổ chức, đối tượng, tập trường, mục đích và thời hạn. Không dùng một cờ `verified=true` chung cho mọi khách hàng hoặc cho phép thay `customerId` sau khi được duyệt.

State machine của yêu cầu có thể gồm `REQUESTED -> APPROVED -> FULFILLED`, cùng các nhánh `REJECTED`, `EXPIRED` hoặc `REVOKED`. Trạng thái đã được phê duyệt không tự cho phép trả dữ liệu nếu người gọi hiện không còn quyền đối tượng hoặc điều kiện đã thay đổi.

Transaction có thể bảo vệ việc kiểm tra phiên bản, tiêu thụ quyền dùng một lần và ghi quyết định theo một snapshot nhất quán. Nếu phê duyệt gắn với một phiên bản dữ liệu cụ thể, dữ liệu thay đổi cần được đánh giá lại theo chính sách, không mặc nhiên tiết lộ giá trị mới bằng phê duyệt cũ.

Không giữ giao dịch mở để đợi tương tác của người dùng. Việc cấp và thực hiện quyền được thiết kế thành các bước bền vững có kiểm tra lại. Đồng thời, một giao dịch không thể thu hồi dữ liệu đã gửi ra ngoài; thời điểm cấp quyền và giới hạn hiệu lực phải được phát biểu trung thực.

### Idempotency không biến quyền cũ thành quyền vĩnh viễn

Retry cùng một lệnh xem đầy đủ có thể cần nhận diện để không tạo nhiều quyết định hoặc tiêu thụ một phê duyệt nhiều lần. Tuy nhiên, mỗi lần trả dữ liệu vẫn phải kiểm tra người gọi và quyền hiện tại.

Không lưu toàn bộ phản hồi chứa dữ liệu gốc vào kho idempotency dùng chung rồi phát lại chỉ vì khóa trùng. Nếu người xem đã mất quyền, kết quả được ghi nhớ không phải lý do để tiếp tục tiết lộ. Có thể lưu metadata quyết định và tham chiếu thay vì sao chép giá trị nhạy cảm.

Audit quyết định một lần và audit các lần truy cập là hai nhu cầu khác nhau. Một lệnh đã được khử trùng lặp không có nghĩa các lần đọc dữ liệu tiếp theo được bỏ qua hoàn toàn trong dấu vết truy cập.

Giới hạn số lần xem đầy đủ và phát hiện truy cập hàng loạt là lớp chống lạm dụng bổ sung. Chúng không thay thế quyền và không chứng minh rằng một lần đọc dưới ngưỡng là hợp lệ.

## 9. Cache và artifact phải giữ đúng ngữ cảnh

### 9.1. Cache phản hồi

Một lỗi phổ biến là dùng khóa cache chỉ gồm `customerId`. Người có quyền đầy đủ truy cập trước khiến phản hồi đầy đủ được cache; sau đó nhân viên chỉ có quyền xem đã che nhận cùng phản hồi.

Nếu cache biểu diễn, khóa và cơ chế kiểm tra phải phân biệt được các thuộc tính liên quan như tenant, người nhận hoặc lớp quyền tương đương, mục đích, tập trường, mức tiết lộ và phiên bản chính sách. Không để client tự khai các thuộc tính quyền đó.

Ngay cả khi khóa chứa phiên bản, hệ thống vẫn cần biết phiên bản hiện tại đáng tin cậy để không dùng quyết định đã cũ. Việc thu hồi quyền phải có hành vi rõ ràng đối với cache cho phép. Không được bỏ kiểm tra quyền trên đối tượng chỉ vì có cache hit.

Cache dữ liệu nội bộ và cache phản hồi cho người dùng là hai ranh giới khác nhau. Dữ liệu gốc trong cache nội bộ vẫn nhạy cảm và cần giới hạn quyền truy cập; nó không được trả trực tiếp như một DTO đã được phân quyền.

Với phản hồi xem đầy đủ, chính sách HTTP như `Cache-Control: no-store` có thể hỗ trợ hạn chế lưu ở các cache HTTP tuân thủ chỉ dẫn. Nó không tự xóa log, ngăn chụp màn hình hoặc kiểm soát mọi bản sao đã được tạo. Không coi một header là toàn bộ cơ chế bảo vệ.

### 9.2. Export bất đồng bộ

Người có quyền xem danh sách đã che không tự được export dữ liệu đầy đủ. Job export cần lưu ngữ cảnh người yêu cầu, phạm vi đối tượng và chính sách đầu ra, không chỉ lưu tên bảng cùng cờ `isAdmin` tại thời điểm tạo.

Theo một hợp đồng thận trọng, quyền được kiểm tra khi tạo job, khi job thực thi và khi tải artifact. Worker có quyền kỹ thuật đọc dữ liệu không có nghĩa được thay người yêu cầu mở rộng dữ liệu export.

Artifact cần có người nhận hoặc nhóm người nhận xác định, thời hạn và kiểm soát tải phù hợp. Một đường dẫn có thể tải trực tiếp bằng token đã cấp có khoảng hiệu lực riêng; nếu cần thu hồi ngay, phải chọn kiến trúc tải có thể kiểm tra quyền hiện tại thay vì mặc định mọi liên kết đã cấp đều bị vô hiệu ngay.

Gỡ quyền sau khi file đã được tải không thu hồi được bản sao trên máy người nhận. Điều này làm việc giới hạn dữ liệu trước khi tạo artifact quan trọng hơn. Không tạo sẵn file đầy đủ rồi chỉ che tên cột trên giao diện tải.

## 10. Log, lỗi, sự kiện và các bản sao ngoài API

Masking tại response không bảo vệ dữ liệu đã được ghi ở đầu pipeline. Ví dụ, middleware ghi request body trước khi controller chạy có thể lưu toàn bộ liên hệ; một exception có thể chứa thực thể đã tải hoặc câu truy vấn kèm tham số.

Các bề mặt cần kiểm soát gồm:

- Access log, application log và lịch sử thao tác quản trị.
- Request/response capture của APM, trace và công cụ báo lỗi.
- Thông báo email, nội dung nhắn tin và payload gửi hệ thống hỗ trợ.
- Event, queue, dead-letter queue và công cụ xem thông điệp.
- Báo cáo, file tạm, bản sao dữ liệu thử nghiệm và kết quả tìm kiếm.
- URL, query string, tên file và metadata artifact.

Ưu tiên ghi log theo danh sách dữ liệu cần thiết như mã thao tác, ID nội bộ thích hợp, mã lý do và trạng thái. Danh sách đen vài tên trường dễ bỏ sót trường mới, object lồng nhau hoặc tên khác của cùng loại dữ liệu. Không ghi toàn bộ entity bằng `toString()` rồi kỳ vọng hàm che ở response sẽ xử lý.

Lỗi gửi cho client nên có mã và thông tin hỗ trợ phù hợp, không chứa raw value gây lỗi. Dấu vết nội bộ cũng cần được giảm dữ liệu và kiểm soát quyền; không biến “chỉ có trong log” thành lý do cho phép lưu mọi giá trị.

Một consumer gửi thông báo có thể thật sự cần liên hệ đầy đủ. Khi đó, dùng kênh nội bộ có phạm vi, người nhận và quyền phù hợp, chỉ truyền dữ liệu cần thiết. Không phát cùng payload đầy đủ sang topic chung cho analytics hoặc cho các consumer chỉ cần biết trạng thái nghiệp vụ.

Không đưa dữ liệu nhạy cảm vào nhãn metrics có giá trị thay đổi theo từng cá nhân. Định danh giả hoặc giá trị băm vẫn có thể tạo khả năng liên kết và vẫn cần được xem xét.

## 11. Những rò rỉ không nằm ở giá trị đầy đủ

### 11.1. Ghép nhiều biểu diễn có thể khôi phục giá trị

Với giá trị minh họa `ABCD1234`:

```text
Màn hình A: ABCD****
Export B:  ****1234
Ghép hai nguồn: ABCD1234
```

Từng nơi đều “đã che” nhưng tổng thông tin tiết lộ vượt chính sách. Cần xét các phần nhìn thấy trên mọi kênh mà cùng người nhận có thể sử dụng. Không xoay ngẫu nhiên phần được che rồi vô tình cho phép thu thập đủ các phần qua nhiều lần gọi.

Phần đuôi ổn định còn có thể liên kết nhiều bản ghi. Đó có thể là nhu cầu đối chiếu được chấp nhận, nhưng không nên xuất hiện mặc định ở mọi báo cáo chỉ vì tiện.

### 11.2. Tìm kiếm và bộ lọc có thể trở thành oracle

Giả sử API không trả email đầy đủ nhưng cho người không có quyền trường lọc `email = một_giá_trị` và trả số lượng kết quả. Người đó có thể kiểm tra giá trị suy đoán mà không cần đọc trường.

Quyền đọc, quyền tìm kiếm, quyền lọc và quyền sắp xếp theo trường cần được đánh giá riêng. Kết quả gợi ý, số lượng, facet và thông báo trùng cũng có thể tiết lộ sự hiện diện hoặc quan hệ của dữ liệu nhạy cảm. Che giá trị trong từng hàng không tự sửa các kênh này.

### 11.3. Băm không tự thay thế masking hoặc phân quyền

Các giá trị có không gian suy đoán nhỏ có thể được thử lại ngoài hệ thống nếu chỉ băm theo một cách công khai. Một mã băm ổn định cũng có thể liên kết cùng người qua nhiều tập dữ liệu.

Nếu cần tham chiếu ổn định, phải thiết kế phạm vi và quyền sử dụng phù hợp, chẳng hạn tham chiếu do hệ thống quản lý cho một mục đích cụ thể. Dù chọn kỹ thuật nào, không coi tham chiếu đó là dữ liệu công khai hoặc quyền đọc đối tượng gốc.

### 11.4. Một thao tác gián tiếp cũng có thể tiết lộ

Chức năng “gửi thông báo cho khách hàng” có thể không cần trả địa chỉ nhận cho người thao tác. Backend xác định người nhận từ đối tượng đã được cấp quyền, gửi qua dịch vụ phù hợp và chỉ trả trạng thái cần thiết.

Nếu API nhận một địa chỉ tùy ý rồi thông báo nó có thuộc tài khoản nào hay không, hoặc trả lỗi chứa địa chỉ thực, luồng gián tiếp lại thành đường đọc dữ liệu. Cần xét cả nội dung phản hồi và quyền tạo tác động, không chỉ trường hiển thị.

## 12. Bảng lỗi thiết kế thường gặp

| Lỗi | Tác động | Cách điều chỉnh |
|---|---|---|
| Chỉ che bằng CSS hoặc JavaScript | Giá trị gốc đã đến client | Tạo biểu diễn được phép tại backend trước khi gửi. |
| Trả thực thể lưu trữ trực tiếp | Trường mới hoặc trường lồng nhau bị lộ | DTO và projection theo danh sách cho phép. |
| Dùng `role == ADMIN` để trả mọi trường | Bỏ qua phạm vi, mục đích và quyền trường | Chính sách dựa trên ngữ cảnh và đối tượng. |
| Cho client đặt `masked=false` | Người gọi tự nâng mức tiết lộ | Hành động xem đầy đủ có kiểm tra quyền riêng. |
| Giữ bốn ký tự cuối của mọi giá trị | Giá trị ngắn bị lộ hết, secret bị tiết lộ không cần thiết | Chiến lược theo loại trường và giới hạn độ dài. |
| Che response nhưng ghi raw entity vào log | Kênh phụ tiếp tục tiết lộ đầy đủ | Giảm dữ liệu từ lúc thu thập log và bảo vệ hệ thống quan sát. |
| Cache chỉ theo ID đối tượng | Trộn biểu diễn giữa các quyền hoặc tổ chức | Ngữ cảnh cache đúng và kiểm tra quyền tại lần đọc. |
| Export chạy với mọi quyền của worker | Dữ liệu vượt quyền người yêu cầu | Mang theo ngữ cảnh, kiểm tra lại và giới hạn artifact. |
| Gửi lại DTO đã che để cập nhật | Ghi đè dữ liệu gốc bằng dấu sao | Tách hợp đồng đọc/ghi và cập nhật tường minh. |
| Nhớ toàn bộ raw response để xử lý idempotency | Replay dữ liệu sau khi quyền đã thay đổi | Lưu metadata phù hợp và kiểm tra quyền trước mỗi lần trả dữ liệu. |
| Chỉ kiểm tra giá trị trường | Bỏ sót lọc, đếm, gợi ý và metadata | Kiểm thử cả các kênh suy luận dữ liệu. |

## 13. Kiểm thử theo invariant và tình huống tấn công logic

### 13.1. Ma trận quyền và biểu diễn

Tạo các chủ thể thử nghiệm: chủ dữ liệu, người hỗ trợ chỉ được xem đã che, người có quyền xem đầy đủ đúng phạm vi và người thuộc tổ chức khác. Với mỗi nhóm, kiểm tra danh sách, chi tiết, object lồng nhau, endpoint quản trị và export.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Người hỗ trợ đọc khách hàng đúng tổ chức | Chỉ có các trường và phần giá trị được phép. |
| Đổi customer ID sang tổ chức khác | Từ chối đối tượng, không trả bản ghi đã che hoặc metadata ngoài quyền. |
| Gửi `masked=false`, mục đích giả hoặc vai trò tự khai | Không thay đổi mức tiết lộ. |
| Người có quyền đối tượng nhưng không có quyền trường | Không có raw value trong mọi nhánh phản hồi. |
| Giá trị ngắn hơn hoặc bằng phần muốn hiển thị | Không vô tình trả toàn bộ giá trị. |
| Giá trị rỗng, null hoặc chưa tồn tại | Theo đúng hợp đồng tiết lộ sự hiện diện. |
| Có Unicode và ký tự điều khiển | Không cắt sai theo hợp đồng, không tạo chèn nội dung ở nơi hiển thị. |
| Trường mới được thêm vào thực thể | Không tự xuất hiện trong DTO chưa có chính sách. |

### 13.2. Kiểm tra các kênh rò rỉ

Dùng các chuỗi nhạy cảm giả có dấu hiệu nhận biết riêng trong môi trường kiểm thử. Thu thập response, lỗi, log, trace, event và artifact thuộc các ngữ cảnh không được xem đầy đủ, rồi xác minh không có giá trị gốc ngoài nơi được cho phép.

Không chỉ kiểm tra giao diện hoặc tìm chuỗi theo đúng một dạng. Giá trị có thể xuất hiện qua escaping hoặc một cách serialize khác. Kiểm tra dữ liệu sau khi giải mã theo định dạng thực tế, đồng thời kiểm tra các thành phần được phép lộ không thể ghép lại thành toàn bộ giá trị qua nhiều kênh.

Một kiểm thử với canary không chứng minh mọi dữ liệu trong hệ thống đều an toàn. Nó cần đi cùng ma trận đường đi và hợp đồng đầu ra, nhất là các nhánh lỗi và tác vụ bất đồng bộ.

### 13.3. Cache, cạnh tranh và idempotency

1. Người có quyền đầy đủ truy cập trước, sau đó người chỉ xem đã che truy cập cùng đối tượng: cache không trả dữ liệu đầy đủ cho người thứ hai.
2. Hai request của hai tổ chức có ID đối tượng tương tự chạy đồng thời: không dùng chung biểu diễn hoặc ngữ cảnh quyền.
3. Yêu cầu xem đầy đủ được phê duyệt, nhưng quyền bị thu hồi trước khi thực hiện: backend áp dụng kiểm tra hiện hành theo ranh giới đã thiết kế, không chỉ tin cờ phê duyệt cũ.
4. Retry cùng command sau khi quyền bị thu hồi: kho idempotency không phát lại raw response.
5. Cùng command nhưng đổi đối tượng hoặc tập trường: xung đột hoặc yêu cầu quyết định mới, không tái sử dụng quyền cũ.
6. Hai request tranh một quyền dùng một lần: cơ chế tiêu thụ chỉ cho kết quả theo hợp đồng, không cấp hai lần do đọc trước cập nhật sau.
7. Job export được tạo trước khi quyền đổi: kiểm tra đúng các thời điểm tạo, thực thi và tải theo chính sách; worker không tự nâng quyền.

### 13.4. Luồng ghi và các phép suy luận

- Gửi `phoneDisplay` trong lệnh cập nhật: dữ liệu gốc không bị ghi đè.
- Không gửi trường trong PATCH: không bị hiểu nhầm là xóa.
- Người không có quyền trường thử tìm kiếm, lọc, đếm hoặc lấy gợi ý: không suy ra giá trị ngoài quyền qua các chức năng đó.
- Gọi hành động gửi thông báo: không nhận địa chỉ gốc nếu chỉ được quyền tạo tác động có giới hạn.
- Gộp thông tin từ danh sách, chi tiết và export: tổng phần nhìn thấy không vượt chính sách.

Kiểm tra trạng thái dữ liệu bền vững và toàn bộ đầu ra liên quan. Việc một hàm `mask()` được gọi hoặc response có dấu sao không đủ chứng minh các invariant đã được bảo vệ.

## 14. Bài tập thiết kế

Một nhân viên hỗ trợ được xem đuôi liên hệ của khách hàng trong tổ chức A. Người đó có thể lập job export danh sách đã che và đề nghị xem đầy đủ một trường để xử lý một hồ sơ cụ thể. Trong lúc job đang chờ, quyền hỗ trợ của người đó bị thu hồi.

Hãy thiết kế cách xử lý và trả lời:

1. Quyền theo đối tượng và kế hoạch tiết lộ theo trường được kiểm tra ở đâu?
2. Biểu diễn cache của người xem đầy đủ có thể dùng chung với người này không; nếu không, ranh giới nào ngăn trộn dữ liệu?
3. Job export thực thi và tải xuống thế nào sau khi quyền đổi?
4. Phê duyệt xem đầy đủ phải gắn với những thuộc tính nào để không dùng cho khách hàng hoặc trường khác?
5. Retry cùng command có được phát lại dữ liệu gốc từ một kết quả cũ không?
6. Log và event nào thật sự cần liên hệ đầy đủ, và ai có quyền truy cập chúng?
7. Làm sao bảo đảm thao tác cập nhật hồ sơ không ghi `***6789` vào trường liên hệ gốc?
8. Những kiểm thử nào chứng minh người gọi không thể ghép nhiều biểu diễn hoặc dùng bộ lọc để suy ra dữ liệu ngoài quyền?
