# Amount approval threshold — Ngưỡng phê duyệt theo số tiền

## 1. Ngưỡng phê duyệt bảo vệ điều gì?

Trong chương **Approval Limits**, ngưỡng phê duyệt theo số tiền quyết định một yêu cầu cần đi qua cấp xét duyệt nào trước khi tạo ra tác động nghiệp vụ. Ví dụ: lệnh chi nhỏ được tiếp nhận theo chính sách tự động, lệnh lớn cần người quản lý, còn lệnh lớn hơn nữa cần hai người có thẩm quyền độc lập.

Một ngưỡng có ích khi server bảo đảm rằng **đúng số tiền, đúng đối tượng và đúng nội dung đã được phê duyệt mới được thực thi**. Chỉ kiểm tra một biểu thức như `amount <= limit` chưa đủ.

Các tình huống lạm dụng thường gặp:

- Gửi số tiền nhỏ để được duyệt rồi sửa thành số tiền lớn trước khi thực thi.
- Tự gửi `approvalRequired=false` hoặc `status=APPROVED` trong request.
- Chia một nghĩa vụ chi thành nhiều yêu cầu dưới ngưỡng để tránh cấp duyệt cao hơn.
- Bỏ phí, thuế hoặc một phần dòng hàng khỏi số tiền dùng để phân loại.
- Đổi tiền tệ, tỷ giá hoặc đơn vị để làm số tiền trông nhỏ hơn.
- Dùng người duyệt có đúng vai trò nhưng sai tenant, sai phạm vi hoặc không đủ thẩm quyền tiền.
- Gửi đồng thời nhiều yêu cầu để vượt hạn mức tổng hoặc thực thi trùng.

Bài học tập trung vào thiết kế bất biến, biểu diễn tiền, state machine và ranh giới transaction để ngưỡng phê duyệt có hiệu lực trước các tình huống này.

## 2. Phân biệt các loại giới hạn

| Khái niệm | Câu hỏi được trả lời | Ví dụ minh họa |
|---|---|---|
| Ngưỡng định tuyến phê duyệt | Yêu cầu cần quy trình duyệt nào? | Trên 100 triệu cần hai người duyệt cấp cao |
| Thẩm quyền của một người duyệt | Người này được duyệt yêu cầu có giá trị đến đâu? | Có thể duyệt tối đa 80 triệu cho chi nhánh A |
| Hạn mức cộng dồn | Trong một phạm vi và khoảng thời gian, được cam kết thêm bao nhiêu? | Tổng tiền đã cam kết và đang giữ không vượt ngân sách ngày |
| Ngân sách khả dụng | Có đủ nguồn lực thực hiện không? | Tài khoản chi còn đủ số dư hoặc ngân sách được cấp |
| Bất biến nghiệp vụ | Điều gì luôn phải đúng dù ai đã duyệt? | Tiền hoàn không vượt phần tiền còn được hoàn |

Một yêu cầu đi qua đúng cấp duyệt vẫn có thể bị từ chối vì người duyệt không có quyền trên đối tượng, thiếu ngân sách hoặc trái quy tắc nghiệp vụ.

Ngược lại, có tiền trong tài khoản không chứng minh đã có phê duyệt. Một phiên đăng nhập mạnh hoặc một lần xác thực bổ sung cũng không tự nâng thẩm quyền số tiền của người dùng.

Không cộng thẩm quyền một cách tùy ý: hai người mỗi người có quyền tối đa 50 triệu không mặc nhiên được cùng duyệt một lệnh 100 triệu. Điều này chỉ được phép nếu chính sách thực sự định nghĩa một cơ chế phân bổ trách nhiệm như vậy.

## 3. Định nghĩa số tiền phải xét duyệt

### 3.1. Chọn một đại lượng có ý nghĩa nghiệp vụ

Gọi `approvalExposure` là giá trị dùng để so sánh ngưỡng. Nó không nhất thiết trùng một trường `amount` trong body.

| Nghiệp vụ | Đại lượng có thể cần xét | Nguồn phải kiểm tra |
|---|---|---|
| Chi trả nhà cung cấp | Tổng nghĩa vụ chi, có thể gồm phí do bên chi chịu | Hóa đơn, hợp đồng, bảng phí và dữ liệu tính phía server |
| Mua hàng | Giá trị cam kết của đơn hoặc nhóm nghĩa vụ liên quan | Dòng hàng, số lượng, giá được phép áp dụng, thuế và chiết khấu |
| Hoàn tiền | Số tiền hoàn yêu cầu, đồng thời kiểm tra phần còn được hoàn | Giao dịch gốc, tiền đã hoàn và tiền đang giữ cho lệnh chờ |
| Điều chỉnh tín dụng | Mức tăng rủi ro hoặc hạn mức được cấp thêm | Hạn mức trước/sau và quy tắc sản phẩm |
| Lệnh ngoại tệ | Giá trị theo đồng tiền chính sách, kèm tiền gốc | Báo giá quy đổi được server tin cậy và quy tắc định giá |

Cần chỉ rõ phí và thuế đã nằm trong số tiền xét chưa, chiết khấu nào được chấp nhận và xử lý các khoản tăng thêm sau duyệt thế nào. Không có một công thức tổng tiền đúng cho mọi nghiệp vụ.

Ví dụ trong bài chọn **tổng nghĩa vụ chi đã tính hợp lệ ở server**. Nếu một lệnh có tiền gốc 99 triệu và phí bên chi phải chịu 2 triệu, `approvalExposure` là 101 triệu theo chính sách này, nên không được xử lý như lệnh 99 triệu.

Người dùng vẫn có thể nhập số tiền họ muốn hoàn hoặc số lượng họ muốn mua. Đây là **ý định cần xác minh**, không phải kết quả định giá có thẩm quyền. Server phải kiểm tra ý định đó với dữ liệu gốc và quy tắc áp dụng.

### 3.2. Không cho số âm che phần nghĩa vụ cần duyệt

Giả sử một batch gồm khoản chi 150 triệu và khoản điều chỉnh âm 140 triệu. Tổng ròng là 10 triệu, nhưng nghĩa vụ chi 150 triệu vẫn có thể cần cấp duyệt cao.

Chính sách phải xác định xét giá trị ròng, tổng chi dương, từng lệnh con hay một đại lượng rủi ro khác. Không dùng phép cộng ròng chỉ vì nó tiện triển khai.

Các khoản âm cần loại nghiệp vụ riêng, nguồn gốc và quyền hợp lệ. Không cho client thêm dòng âm tùy ý để kéo tổng xuống dưới ngưỡng.

### 3.3. Tiền tệ và đơn vị là một phần của giá trị

Hai con số `1000 VND` và `1000 USD` không thể so sánh trực tiếp. Cũng không được lẫn đơn vị tiền chính với đơn vị nhỏ nhất của hợp đồng API.

Với mỗi loại tiền được hỗ trợ, quy định:

- Mã tiền tệ được phép sử dụng.
- Đơn vị truyền qua API và lưu trong database.
- Số chữ số thập phân chấp nhận.
- Giá trị tối thiểu, tối đa và quy tắc làm tròn.
- Cách cộng, quy đổi và so sánh với chính sách.

Nếu dùng số nguyên đơn vị nhỏ nhất, phải chặn tràn số khi cộng hoặc nhân. Nếu dùng số thập phân, không đi qua `float` hoặc `double` rồi mới chuyển về kiểu tiền.

Trong Java, `BigDecimal` hỗ trợ số thập phân và quy tắc làm tròn tường minh. `compareTo` so sánh giá trị số; `equals` còn xét cách biểu diễn theo scale, nên không thay hai phép này cho nhau khi kiểm tra biên tiền. [Java BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)

## 4. Chính sách ngưỡng phải không có khoảng trống

### 4.1. Ma trận minh họa

Giả sử hệ thống chỉ xét VND, số tiền nguyên dương, và cấu hình sau đã được phê duyệt. Các con số là giả định để học thiết kế, không phải chuẩn áp dụng chung:

| Giá trị A dùng để xét duyệt | Quy trình yêu cầu |
|---|---|
| `0 < A <= 10.000.000 VND` | Chính sách tự động, nếu mọi điều kiện đủ khác đều thỏa |
| `10.000.000 < A <= 100.000.000 VND` | Một người có quyền MANAGER và thẩm quyền tiền đủ cho toàn bộ A |
| `100.000.000 < A <= 1.000.000.000 VND` | Hai người SENIOR_APPROVER độc lập, mỗi người có thẩm quyền đủ cho toàn bộ A |
| `A > 1.000.000.000 VND` | Chuyển quy trình ngoại lệ; không tự động thực thi |

Trong ví dụ, người tạo yêu cầu không được tính làm người duyệt ở hai hàng cần con người. Hai người cấp cao phải là hai chủ thể độc lập theo mô hình danh tính của tổ chức, không chỉ hai tài khoản khác nhau.

“Chính sách tự động” vẫn là một quyết định phía server. Nó có thể yêu cầu nhà cung cấp đã được xác minh, loại giao dịch được cho phép, dữ liệu đầy đủ, đủ ngân sách và không có điều kiện bắt buộc duyệt thủ công.

### 4.2. Kiểm tra biên tường minh

| A | Tuyến theo ma trận |
|---|---|
| 10.000.000 | Chính sách tự động |
| 10.000.001 | Một MANAGER |
| 100.000.000 | Một MANAGER |
| 100.000.001 | Hai SENIOR_APPROVER |
| 1.000.000.000 | Hai SENIOR_APPROVER |
| 1.000.000.001 | Ngoại lệ |
| 0, số âm, sai tiền tệ hoặc vượt miền giá trị hỗ trợ | Đầu vào hoặc cấu hình không hợp lệ |

Dùng các khoảng không chồng lấn và không bỏ sót. Khi nạp cấu hình, kiểm tra các mốc tăng dần, đơn vị và tiền tệ thống nhất, không có tuyến mặc định làm giảm cấp duyệt khi gặp lỗi.

Nếu không tìm được chính sách, không xác định được số tiền hoặc không có người đủ quyền, yêu cầu phải chờ xử lý phù hợp. Không biến lỗi cấu hình thành “không cần duyệt”.

## 5. Minh họa Java: phân loại số tiền chính xác

Đoạn mã Java 17+ chỉ minh họa phần phân tuyến cho ma trận trên. Nó không thay thế kiểm tra quyền, dữ liệu gốc hoặc transaction.

Quy ước đầu vào chuỗi trong ví dụ là số nguyên VND không có dấu phân cách hoặc ký pháp số mũ. Giới hạn kích thước được đặt trước khi dựng số, để tránh chấp nhận các biểu diễn số quá lớn không cần thiết.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

final class AmountApprovalPolicy {
    enum Route {
        AUTOMATIC_POLICY,
        ONE_MANAGER,
        TWO_SENIOR_APPROVERS,
        EXCEPTION_REQUIRED
    }

    private static final BigDecimal AUTO_MAX =
            new BigDecimal("10000000");
    private static final BigDecimal MANAGER_MAX =
            new BigDecimal("100000000");
    private static final BigDecimal SENIOR_MAX =
            new BigDecimal("1000000000");
    private static final BigDecimal SUPPORTED_MAX =
            new BigDecimal("1000000000000");

    static BigDecimal parseVnd(String raw) {
        if (raw == null || !raw.matches("[0-9]{1,13}")) {
            throw new IllegalArgumentException("Invalid VND representation");
        }
        return validateExposure(new BigDecimal(raw));
    }

    static Route route(String currency, BigDecimal serverExposure) {
        if (!"VND".equals(currency)) {
            throw new IllegalArgumentException("Unsupported policy currency");
        }

        BigDecimal amount = validateExposure(serverExposure);

        if (amount.compareTo(AUTO_MAX) <= 0) {
            return Route.AUTOMATIC_POLICY;
        }
        if (amount.compareTo(MANAGER_MAX) <= 0) {
            return Route.ONE_MANAGER;
        }
        if (amount.compareTo(SENIOR_MAX) <= 0) {
            return Route.TWO_SENIOR_APPROVERS;
        }
        return Route.EXCEPTION_REQUIRED;
    }

    private static BigDecimal validateExposure(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0
                || amount.compareTo(SUPPORTED_MAX) > 0) {
            throw new IllegalArgumentException("Amount outside supported range");
        }

        return amount.setScale(0, RoundingMode.UNNECESSARY);
    }
}
~~~

`serverExposure` phải là số tiền đã được tính và xác minh phía server. Không lấy tổng client gửi rồi chỉ chạy qua hàm `route` là coi như đủ kiểm soát.

Giới hạn miền giá trị của dữ liệu lưu trữ phải áp dụng cả cho phép cộng dòng hàng, phí và quy đổi, không chỉ cho từng số đầu vào. Lỗi vượt miền phải được xử lý rõ ràng, không cắt bớt hoặc đổi dấu.

Chính sách thực tế có thể lưu các mốc trong cấu hình có phiên bản thay vì hằng số. Khi đó cần kiểm tra tính hợp lệ và quyền thay cấu hình trước khi dùng để ra quyết định.

## 6. Xét đúng người duyệt trên đúng đối tượng

### 6.1. Vai trò là một phần của quyết định

Một quyết định duyệt hợp lệ trong ví dụ cần thỏa đồng thời:

~~~text
Người duyệt được xác thực
AND được phép xem và duyệt đối tượng cụ thể
AND đúng tenant, đơn vị, loại nghiệp vụ và phạm vi được giao
AND có vai trò phù hợp với tuyến yêu cầu
AND thẩm quyền tiền >= toàn bộ số tiền cần xét
AND không vi phạm tách biệt trách nhiệm
AND đang duyệt đúng phiên bản yêu cầu
AND việc ủy quyền, nếu có, còn hiệu lực và đúng phạm vi
~~~

OWASP khuyến nghị kiểm tra quyền trên mỗi yêu cầu và mặc định từ chối khi chưa có quyền cho phép. Chỉ có vai trò trong token không đủ để kết luận người đó được duyệt mọi đối tượng. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

Một MANAGER có trần 80 triệu không được duyệt lệnh 90 triệu, dù lệnh 90 triệu nằm trong tuyến “một MANAGER”. Tuyến quy định loại bằng chứng cần có; hồ sơ thẩm quyền quyết định cá nhân nào đủ điều kiện cung cấp bằng chứng đó.

### 6.2. Tách biệt người lập và người duyệt

Cần xác định “cùng một người” trong mô hình nghiệp vụ:

- Hai tài khoản thuộc cùng một nhân sự có được coi là độc lập không?
- Người được ủy quyền có đại diện cho chính người lập không?
- Tài khoản dịch vụ có đang hành động thay người tạo yêu cầu không?
- Một người có đồng thời nhiều vai trò có được tính nhiều chữ ký không?

Trong ví dụ, một chủ thể chỉ được tính một lần cho cùng yêu cầu và phiên bản. Hai tài khoản của cùng một chủ thể không tạo ra hai phê duyệt độc lập.

Tách biệt trách nhiệm giúp giảm rủi ro lạm dụng đơn lẻ nhưng không loại bỏ mọi khả năng thông đồng. Các giao dịch rủi ro còn cần giám sát và quy trình kiểm soát phù hợp.

### 6.3. Ủy quyền và thay đổi quyền

Ủy quyền cần có người cấp, người nhận, phạm vi, trần tiền, thời hạn và lịch sử thu hồi. Không cho người được ủy quyền tự mở rộng trần hoặc tạo chuỗi ủy quyền làm vượt quyền ban đầu.

Phải định nghĩa tác động khi người duyệt bị thu hồi quyền trước khi thực thi. Ví dụ trong bài yêu cầu cổng tạo lệnh thực thi kiểm tra người duyệt còn đáp ứng quy tắc hiện hành về hiệu lực quyền; bằng chứng cũ không tự vượt qua một quyết định thu hồi có hiệu lực.

Nếu tổ chức chọn chính sách khác cho các giao dịch đã cam kết, cần mô tả rõ ranh giới cam kết và cách hủy. Không để hành vi phụ thuộc việc service đọc cache quyền mới hay cũ.

## 7. Chống chia nhỏ giao dịch để né ngưỡng

### 7.1. Ngưỡng từng lệnh không tự chống chia nhỏ

Với ngưỡng 100 triệu, một nghĩa vụ 180 triệu có thể bị chia thành hai yêu cầu 90 triệu. Nếu chính sách chỉ xét từng lệnh riêng lẻ, cả hai đều đi tuyến thấp hơn.

Muốn coi việc này là vượt chính sách, phải định nghĩa **phạm vi cộng gộp** trong nghiệp vụ. Không thể chỉ ghi “cấm chia nhỏ” mà thiếu quan hệ dữ liệu để thực thi.

Các phạm vi có thể có:

| Phạm vi | Ví dụ sử dụng |
|---|---|
| Cùng hợp đồng hoặc purchase order | Nhiều đợt chi của cùng nghĩa vụ mua hàng |
| Cùng giao dịch gốc | Nhiều yêu cầu hoàn tiền liên quan |
| Cùng đợt thanh toán | Nhiều lệnh con trong một batch |
| Cùng nhóm nghĩa vụ được xác định | Tách dòng hóa đơn hoặc phiếu đề nghị |
| Cửa sổ cộng dồn được chính sách định nghĩa | Phát hiện hoặc xét duyệt nhiều khoản liên quan trong kỳ |

Không tự cộng mọi giao dịch trong ngày nếu hợp đồng chỉ quy định ngưỡng từng lệnh. Ngưỡng cộng gộp và ngưỡng từng lệnh phải là các điều kiện được định nghĩa riêng.

### 7.2. Server quản lý quan hệ nhóm

Client không được tự chọn một `approvalGroupId` mới để lấy lại ngưỡng thấp. Server cần xác minh hoặc xác lập liên kết với hợp đồng, giao dịch gốc hoặc nhóm nghĩa vụ có thẩm quyền.

Trong ví dụ chống chia nhỏ theo một purchase order:

~~~text
Giá trị dùng phân loại nhóm
    = nghĩa vụ liên quan đã được chấp nhận
    + nghĩa vụ đang được giữ
    + phần tăng thêm của yêu cầu mới
~~~

Công thức cụ thể phải tránh đếm hai lần một lệnh vừa chuyển từ “đang giữ” sang “đã chấp nhận”. Khi tổng nhóm vượt ngưỡng, chính sách phải xác định phần nào cần duyệt lại hoặc phần còn lại phải được cấp trên duyệt trước khi thực thi.

Nếu các khoản trước đã thực thi, không thể làm chúng trở thành “chưa từng chi” bằng một phê duyệt mới. Cần chặn hoặc nâng cấp phần nghĩa vụ tiếp theo theo quy tắc đã định.

Nhóm dữ liệu không luôn phát hiện được mọi hành vi cố ý lập nhiều hồ sơ khác nhau cho cùng mục đích. Vì vậy, có thể cần đối chiếu nhà cung cấp, người hưởng, chứng từ và dấu hiệu lặp để chuyển kiểm tra thủ công. Không giả định một khóa nhóm là giải pháp đầy đủ cho thông đồng hoặc khai sai quan hệ nghiệp vụ.

### 7.3. Cộng gộp phải an toàn khi đồng thời

Hai request 60 triệu có thể cùng đọc tổng nhóm bằng 0 rồi đều đi tuyến dưới 100 triệu. Bọc phép đọc tổng và ghi mới trong transaction chưa tự ngăn được lỗi này.

Một cách thiết kế là khóa bản ghi đại diện cho nhóm nghĩa vụ, tính lại tổng liên quan rồi cập nhật phần giữ trước khi thả khóa. Các cách khác có thể dùng cập nhật có điều kiện hoặc mức cô lập phù hợp, kèm xử lý retry.

Trong PostgreSQL, Read Committed sử dụng snapshot theo câu lệnh và không tự loại bỏ mọi bất thường khi các transaction cùng ra quyết định. Phải chọn cơ chế điều phối phù hợp với bất biến cần giữ. [PostgreSQL Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

Nếu phải tạo nhóm mới, cần xử lý cả tranh chấp khởi tạo; khóa một bản ghi chưa tồn tại không tự bảo vệ mọi lần tạo cạnh tranh.

## 8. Ràng buộc phê duyệt với nội dung bất biến

### 8.1. Người duyệt đang duyệt cái gì?

Một phê duyệt cần gắn với snapshot có thể giải thích, chẳng hạn:

~~~text
requestId + requestVersion
tenant và chủ thể chịu nghĩa vụ
amount, currency và approvalExposure
người hưởng, tài khoản nhận và nguồn chi
dòng hàng, phí, thuế hoặc căn cứ tính tiền có ảnh hưởng
nhóm nghĩa vụ dùng để cộng gộp
policyVersion và tuyến phê duyệt
thông tin quy đổi nếu có
thời điểm duyệt và hạn hiệu lực của bằng chứng
~~~

OWASP khuyến nghị để người dùng nhận biết dữ liệu giao dịch quan trọng, thực thi xác nhận ở server và có bước kiểm tra trước khi giao dịch được thực hiện. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html)

Không dùng một cờ `approved=true` không gắn với nội dung. Một approval ID hợp lệ cũng không được đem áp cho một yêu cầu khác.

### 8.2. Sửa dữ liệu phải làm mất hiệu lực bằng chứng liên quan

Kịch bản:

~~~text
Phiên bản 7: 9 triệu, người hưởng A -> được chính sách tự động chấp nhận.
Sau đó: sửa thành 90 triệu hoặc đổi người hưởng B.
Lỗi: vẫn giữ trạng thái đã duyệt của phiên bản 7.
~~~

Trong ví dụ của bài, thay đổi dữ liệu quan trọng tạo phiên bản mới và yêu cầu xét duyệt lại. Điều này áp dụng cả khi giảm số tiền nhưng đổi người hưởng hoặc thay đổi ý nghĩa giao dịch.

Nếu nghiệp vụ cho phép một mức dung sai hoặc một số trường được sửa mà không duyệt lại, danh sách đó phải tường minh và không làm tăng rủi ro ngoài phạm vi đã chấp thuận.

Có thể dùng hash của biểu diễn chuẩn hóa để phát hiện khác biệt snapshot. Hash không thay thế kiểm tra quyền, chữ ký hoặc bảo vệ tính toàn vẹn của kho dữ liệu. Nếu kẻ xấu có thể sửa cả dữ liệu lẫn hash, việc lưu hash bên cạnh không tự tạo bằng chứng chống sửa.

### 8.3. State machine tham chiếu

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> PendingApproval: submit và chốt snapshot
    PendingApproval --> Approved: đủ bằng chứng đúng phiên bản
    PendingApproval --> Rejected: từ chối
    PendingApproval --> Draft: sửa nội dung và tăng phiên bản
    Approved --> Draft: sửa nội dung quan trọng
    Approved --> ExecutionQueued: kiểm tra cuối và ghi lệnh thực thi
    Approved --> Expired: bằng chứng hết hiệu lực
    ExecutionQueued --> Executed: xác nhận kết quả
    ExecutionQueued --> ReconciliationRequired: kết quả bên ngoài chưa rõ
~~~

Với tuyến tự động, server có thể ghi bằng chứng quyết định chính sách để đạt `Approved`, thay vì ghi một phê duyệt của người dùng giả.

Các nhánh lỗi và hủy được lược bỏ để làm rõ đường đi chính. Client không được tự chuyển trạng thái bằng cách gửi `status` tùy ý; server cung cấp lệnh nghiệp vụ và kiểm tra điều kiện chuyển trạng thái.

## 9. Giao dịch ngoại tệ và thay đổi giá trị

### 9.1. Quy đổi có nguồn và phiên bản

Nếu ngưỡng tính bằng một tiền tệ cơ sở, cần giữ cả:

- Số tiền gốc và tiền tệ gốc.
- Nguồn và định danh báo giá hoặc tỷ giá phía server.
- Thời điểm hiệu lực và thời hạn được dùng.
- Chiều quy đổi, độ chính xác và quy tắc làm tròn.
- Giá trị quy đổi dùng xét duyệt và phiên bản chính sách.

Không nhận `exchangeRate` từ client như dữ liệu có thẩm quyền. Không cho client chọn một nguồn tỷ giá thuận lợi hơn chỉ để giảm cấp duyệt.

Cần quy định dùng tỷ giá chốt khi tiếp nhận hay đánh giá lại trước khi thực thi. Nếu đánh giá lại làm nghĩa vụ vượt thẩm quyền đã được duyệt, phải giữ lệnh để duyệt bổ sung hoặc thực hiện quy tắc dung sai đã phê duyệt. Không âm thầm tiếp tục với cờ duyệt cũ.

### 9.2. Không làm tròn để lọt ngưỡng

Nếu giá trị quy đổi thực tế vượt ngưỡng một phần nhỏ nhưng bị làm tròn xuống dưới ngưỡng, tuyến duyệt có thể bị hạ sai.

Có thể so sánh ở độ chính xác được chính sách chọn hoặc dùng cách làm tròn bảo thủ cho giá trị xét duyệt. Không mặc định quy tắc làm tròn tiền thanh toán cũng luôn phù hợp với giá trị đánh giá thẩm quyền.

Thiếu báo giá hợp lệ, sai tiền tệ hoặc không giải quyết được độ chính xác phải tạo trạng thái chờ/lỗi rõ ràng. Không thay bằng tỷ giá 1 hoặc giá trị 0.

## 10. Transaction, hạn mức tổng và cổng thực thi cuối

### 10.1. Một luồng phê duyệt tham chiếu

~~~text
BEGIN
  1. Xác định người thao tác từ ngữ cảnh xác thực.
  2. Đọc và điều phối truy cập vào yêu cầu, phiên bản và phạm vi liên quan.
  3. Kiểm tra quyền trên đối tượng và trạng thái PendingApproval.
  4. Đọc snapshot, tuyến chính sách và hiệu lực quyền người duyệt.
  5. Kiểm tra thẩm quyền tiền, tách biệt trách nhiệm và ủy quyền.
  6. Ghi một bằng chứng duyệt cho chủ thể và phiên bản.
  7. Tính lại tập bằng chứng hợp lệ.
  8. Nếu đủ điều kiện, chuyển đúng phiên bản sang Approved.
  9. Ghi kết quả idempotency và audit phù hợp.
COMMIT
~~~

Một ràng buộc như `UNIQUE(requestId, requestVersion, approverPrincipalId)` giúp tránh đếm cùng chủ thể nhiều lần. Nó không thay thế kiểm tra các chủ thể có thực sự độc lập và đủ quyền hay không.

Nếu endpoint nhận `expectedVersion`, phải so sánh với phiên bản thật. Phiên bản khác hoặc dữ liệu đã đổi cần phản hồi xung đột, không ghi phê duyệt lên bản mới mà người dùng chưa xem.

### 10.2. Approved chưa phải giấy phép thực thi mọi nội dung

Trước khi ghi lệnh thực thi, server cần kiểm tra lại:

1. Yêu cầu ở trạng thái cho phép và chưa tạo lệnh thực thi trước đó.
2. Nội dung hiện tại trùng snapshot đã được phê duyệt.
3. Đủ bằng chứng còn hợp lệ cho đúng tuyến và số tiền.
4. Chính sách đã chốt vẫn được phép dùng theo quy tắc quản trị thay đổi.
5. Không có lệnh đình chỉ, hủy hoặc thu hồi có hiệu lực trước cổng này.
6. Các bất biến về số dư, tiền còn được hoàn, nhóm nghĩa vụ và ngân sách vẫn thỏa.
7. Phần ngân sách hoặc nghĩa vụ cần giữ được ghi nhận an toàn.

Trong ví dụ, bước này tạo một lệnh thực thi bất biến và outbox trong cùng transaction. Tác vụ bên ngoài dùng nội dung đã chốt của lệnh, không đọc lại một body có thể sửa rồi gửi số tiền khác.

Nếu chính sách yêu cầu quyền còn hợp lệ đến đúng lúc gửi cho đối tác, worker phải có kiểm tra tương ứng. Cần nêu ranh giới hủy đối với lệnh đã cam kết; không thể giả định transaction nội bộ bao trùm cả tác dụng phụ ở hệ thống thanh toán.

### 10.3. Giữ ngân sách và hạn mức tổng

Một điều kiện ví dụ:

~~~text
consumed + reserved + newExposure <= cumulativeLimit
~~~

Trong đó `reserved` là nghĩa vụ đã được giữ cho lệnh chưa xác nhận hoàn tất. Chỉ đếm `consumed` có thể cho nhiều lệnh chờ cùng vượt hạn mức sau đó.

Việc kiểm tra và tăng phần giữ phải an toàn trước xử lý đồng thời. Có thể dùng một bản ghi hạn mức được khóa hoặc cập nhật có điều kiện với số tiền chính xác. Nếu phải cập nhật nhiều phạm vi, quy định thứ tự khóa và xử lý xung đột.

Định nghĩa rõ tiền tệ, phạm vi, chu kỳ thời gian và thời điểm tính. Hạn mức cá nhân, ngân sách tenant và tổng nghĩa vụ của một hợp đồng là các sổ khác nhau; không dùng một bộ đếm để thay cho mọi quy tắc.

Với nghiệp vụ hoàn tiền, bất biến còn có thể là:

~~~text
tiền đã hoàn + tiền đang giữ cho hoàn mới <= tổng tiền đủ điều kiện hoàn của giao dịch gốc
~~~

Phê duyệt của cấp cao không tự cho phép phá bất biến này.

## 11. Idempotency và tác dụng phụ bên ngoài

Một lần retry phê duyệt không được thêm một phiếu duyệt thứ hai. Một lần retry thực thi không được tạo thêm khoản chi.

Thiết kế cần phân biệt:

| Lớp | Cách bảo vệ |
|---|---|
| Cùng ý định gọi API | Idempotency key theo chủ thể và thao tác, kèm kiểm tra payload |
| Cùng người duyệt và phiên bản | Ràng buộc duy nhất trên bằng chứng duyệt |
| Cùng yêu cầu tạo lệnh thực thi | Ràng buộc duy nhất hoặc chuyển trạng thái có điều kiện |
| Gửi lại lệnh cho bên thanh toán | Định danh nghiệp vụ ổn định, cơ chế idempotency của đối tác nếu có |
| Kết quả không rõ sau timeout | Tra cứu, đối soát hoặc chờ xác nhận thay vì tạo ý định mới |

Khi trả kết quả đã lưu, vẫn kiểm tra quyền đọc của người gọi. Cùng key nhưng payload khác phải tạo lỗi xung đột theo hợp đồng.

Outbox giúp gắn bản ghi lệnh với việc chuyển sự kiện, nhưng bản thân nó không bảo đảm tác dụng phụ bên ngoài chỉ xảy ra một lần. Worker cần xử lý sự kiện lặp và phối hợp với cơ chế của đối tác.

Không giải phóng phần tiền đang giữ chỉ vì một lần gọi bị timeout. Giao dịch bên ngoài có thể đã xảy ra. Chỉ giải phóng theo kết quả cuối cùng được xác nhận hoặc quy trình đối soát cho phép.

## 12. Hợp đồng API và bằng chứng audit

### 12.1. Client gửi ý định duyệt

Một request minh họa:

~~~json
{
  "requestId": "payment-request-example",
  "expectedVersion": 7,
  "decision": "APPROVE",
  "comment": "Đã đối chiếu chứng từ."
}
~~~

Danh tính người duyệt lấy từ ngữ cảnh xác thực. Các trường `approverId`, `role`, `approvalLimit`, `requiredApprovalCount`, `approvedAmount` hoặc `status` do client gửi không được tự quyết định thẩm quyền.

Giao diện nên hiển thị số tiền, tiền tệ, người hưởng và nội dung quan trọng của đúng phiên bản đang được duyệt. Bảo vệ phiên, chống request giả mạo khi dùng cơ chế xác thực liên quan và xác thực bổ sung theo rủi ro vẫn cần thiết, nhưng không thay kiểm tra số tiền và quyền ở server.

### 12.2. Audit đủ để giải thích

Bằng chứng nên giúp trả lời:

- Ai hành động, có đại diện hoặc ủy quyền cho ai không?
- Đã duyệt yêu cầu và phiên bản nào?
- Số tiền gốc, số tiền xét duyệt và tiền tệ là gì?
- Chính sách, tuyến và hồ sơ thẩm quyền nào được dùng?
- Tập bằng chứng độc lập nào làm yêu cầu đủ điều kiện?
- Có thay đổi, từ chối, thu hồi hoặc override nào sau đó không?
- Lệnh thực thi nào được tạo và kết quả được xác nhận ra sao?

Bảo vệ quyền đọc và sửa audit. Không ghi token bí mật hoặc toàn bộ thông tin tài khoản nhạy cảm vào log không được kiểm soát.

Không cung cấp endpoint “override mọi ngưỡng” chỉ dựa trên một vai trò quản trị rộng. Nếu có ngoại lệ, cần phạm vi riêng, người chịu trách nhiệm, lý do, bằng chứng và giới hạn hiệu lực được thiết kế tường minh.

## 13. Kiểm thử tình huống tấn công logic

Bảng dưới đây là các kịch bản cần kiểm tra khi có triển khai; không phải kết quả đã chạy kiểm thử một hệ thống cụ thể.

| Tình huống | Kết quả cần giữ |
|---|---|
| Số tiền đúng tại ngưỡng và ngay trên ngưỡng | Tuyến khớp với các khoảng đã công bố |
| Dùng số âm, 0, số quá lớn, thập phân không được phép | Không lọt vào tuyến thấp hoặc gây tràn số |
| Đổi VND thành tiền tệ khác nhưng giữ cùng con số | Không so sánh bằng chính sách sai tiền |
| Bỏ phí hoặc thêm dòng âm tùy ý | Không làm giảm exposure trái quy tắc |
| Client sửa `approvalRequired`, `role` hoặc `status` | Không thay quyết định có thẩm quyền |
| Người có vai trò đúng nhưng sai tenant/chi nhánh | Không được duyệt ngoài phạm vi |
| MANAGER có trần 80 triệu duyệt lệnh 90 triệu | Bị chặn dù tuyến chỉ cần một MANAGER |
| Hai người mỗi người có trần thấp hơn toàn bộ lệnh | Không cộng thẩm quyền ngoài chính sách |
| Người lập dùng tài khoản phụ hoặc tài khoản được ủy quyền | Không được tính làm người duyệt độc lập |
| Sửa số tiền hoặc người hưởng sau khi duyệt | Bằng chứng cũ không áp dụng cho bản mới |
| Phê duyệt lại bản cũ sau khi yêu cầu đã tăng phiên bản | Lỗi xung đột, không duyệt nhầm phiên bản |
| Chia một nghĩa vụ thành nhiều khoản dưới ngưỡng | Được cộng gộp hoặc chuyển kiểm tra theo đúng chính sách nhóm |
| Hai khoản đồng thời làm tổng nhóm vượt ngưỡng | Không cùng được tiếp nhận theo quyết định tổng cũ |
| Đổi tỷ giá hoặc báo giá hết hiệu lực | Không hạ cấp duyệt bằng dữ liệu không hợp lệ |
| Thu hồi quyền hoặc đình chỉ trước cổng thực thi | Không dùng bằng chứng cũ để vượt quyết định có hiệu lực |
| Retry phê duyệt cùng ý định | Không tăng số người duyệt |
| Retry lệnh chi hoặc nhận sự kiện lặp | Không tạo tác dụng phụ trùng |
| Timeout bên thanh toán | Không giải phóng tiền hoặc tạo lệnh mới khi kết quả chưa rõ |
| Thiếu chính sách hoặc cấu hình ngưỡng sai | Không tự chuyển sang không cần phê duyệt |
| Nhánh quản trị, batch, import hoặc worker | Không có đường thực thi bỏ qua các bất biến chung |

Kiểm thử đồng thời cần quan sát bản ghi đã commit, phần tiền giữ, bằng chứng duyệt và tác dụng phụ. Chỉ thấy một response bị từ chối chưa chứng minh hệ thống chưa tạo thêm nghĩa vụ.

## 14. Các bất biến cốt lõi

Một thiết kế ngưỡng phê duyệt có hiệu lực cần giữ được:

- Số tiền xét duyệt được tính từ dữ liệu được xác minh, có tiền tệ và đơn vị rõ ràng.
- Mỗi số tiền hợp lệ đi vào đúng một tuyến chính sách.
- Người duyệt đủ quyền trên đối tượng, đủ thẩm quyền tiền và đáp ứng tách biệt trách nhiệm.
- Phê duyệt gắn với nội dung và phiên bản cụ thể.
- Chia nhỏ, gửi đồng thời hoặc đổi kênh không làm mất quy tắc cộng gộp đã định.
- Việc thực thi kiểm tra bằng chứng và bất biến trước khi tạo tác động không thể rút lại dễ dàng.
- Retry không tăng số phê duyệt hoặc tạo thêm giao dịch.

Ngưỡng tiền là cách phân cấp quyết định. Tính an toàn đến từ việc giữ toàn bộ mối liên hệ giữa số tiền, chính sách, người duyệt, đối tượng và nội dung thực sự được thực thi.
