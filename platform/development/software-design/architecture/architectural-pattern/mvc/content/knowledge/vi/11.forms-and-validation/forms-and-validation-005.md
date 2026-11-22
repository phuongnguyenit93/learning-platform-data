# Kiểm tra một trường, nhiều trường và điều kiện phụ thuộc

Trong module **MODEL_VIEW_CONTROLLER**, biểu mẫu là ranh giới tiếp nhận dữ liệu từ người dùng vào ứng dụng. Dữ liệu nhập có thể sai định dạng, thiếu trường bắt buộc, mâu thuẫn giữa nhiều trường hoặc không phù hợp với trạng thái nghiệp vụ hiện tại. Vì vậy, kiểm tra dữ liệu không chỉ là gắn một quy tắc cho từng ô nhập; ứng dụng còn phải xác định quy tắc nào áp dụng cho từng trường, quy tắc nào cần nhìn nhiều trường cùng lúc và điều kiện nào khiến một trường trở nên bắt buộc hoặc không còn hợp lệ.

Bài học thuộc chương **Biểu mẫu và kiểm tra**. Trọng tâm là ba mức kiểm tra: **một trường**, **nhiều trường** và **điều kiện phụ thuộc**. Ta sẽ phân biệt validation ở trình duyệt, Controller, application service và Model; tổ chức thông báo lỗi cho form HTML và API; rồi triển khai ví dụ Java Spring MVC với Bean Validation.

## 1. Vì sao cần nhiều mức kiểm tra?

Giả sử người dùng đăng ký thành viên thư viện. Form có họ tên, email, ngày sinh, mật khẩu, xác nhận mật khẩu và loại thành viên. Nếu người dùng chọn loại thành viên là học sinh, ứng dụng yêu cầu tên trường học; nếu chọn thành viên thông thường, trường học không cần nhập.

Các quy tắc không cùng một phạm vi:

- Họ tên không được để trống: quy tắc của một trường.
- Email phải đúng định dạng: quy tắc của một trường.
- Ngày kết thúc phải sau ngày bắt đầu: quy tắc cần hai trường.
- Mật khẩu và xác nhận mật khẩu phải trùng nhau: quy tắc cần so sánh hai trường.
- Trường học chỉ bắt buộc khi loại thành viên là học sinh: quy tắc phụ thuộc vào giá trị của trường khác.
- Người dùng không được tự chọn mức thành viên quản trị: quy tắc bảo mật và phân quyền ở phía server.

Nếu chỉ kiểm tra từng trường độc lập, ứng dụng có thể chấp nhận một biểu mẫu mà các giá trị mâu thuẫn với nhau. Nếu đưa tất cả quy tắc vào một hàm lớn trong Controller, logic dễ bị lặp và khó tái sử dụng khi cùng ca sử dụng được gọi từ API hoặc tác vụ nền.

Một thiết kế tốt xác định đúng chủ sở hữu của từng quy tắc, trả lỗi ở đúng ranh giới và vẫn bảo vệ bất biến nghiệp vụ ở phía server.

## 2. Phân biệt ba loại validation

| Loại kiểm tra | Phạm vi dữ liệu | Ví dụ | Vị trí thường phù hợp |
|---|---|---|---|
| Một trường (field-level) | Một giá trị | Email đúng định dạng, tiêu đề không rỗng | Field constraint trên request/form DTO hoặc Value Object |
| Nhiều trường (cross-field) | Hai hoặc nhiều giá trị trong cùng một đối tượng | Ngày kết thúc sau ngày bắt đầu, mật khẩu trùng xác nhận | Class-level constraint, validator hoặc logic chuyên biệt |
| Điều kiện phụ thuộc (conditional) | Một trường thay đổi quy tắc của trường khác | Chọn giao hàng tận nơi thì phải có địa chỉ | Class-level constraint, nhóm quy tắc hoặc validation theo ngữ cảnh |

Ba loại có thể xuất hiện đồng thời trong cùng một form. Ví dụ, email cần đúng định dạng ở mức field; email và trạng thái đăng ký có thể tham gia quy tắc duy nhất ở tầng nghiệp vụ; loại thành viên quyết định trường bổ sung có bắt buộc hay không.

Cũng cần phân biệt **validation đầu vào** với **quy tắc nghiệp vụ**. Validation đầu vào kiểm tra cấu trúc và tính nhất quán của dữ liệu gửi lên. Quy tắc nghiệp vụ có thể phụ thuộc database, quyền người dùng hoặc trạng thái miền hiện tại, nên phải được kiểm tra trong ca sử dụng hoặc Model ngay cả khi form đã hợp lệ.

## 3. Kiểm tra một trường

Field-level validation kiểm tra một giá trị độc lập với các trường khác. Những quy tắc thường gặp gồm:

- Bắt buộc có giá trị.
- Độ dài tối thiểu hoặc tối đa.
- Định dạng email, số điện thoại, mã bưu chính hoặc mã định danh.
- Giá trị nằm trong khoảng cho phép.
- Ngày nằm trong khoảng hợp lệ.
- Chuỗi chỉ chứa ký tự được chấp nhận.
- Tệp có phần mở rộng, MIME type và kích thước phù hợp.

### 3.1. Chọn quy tắc theo kiểu dữ liệu

| Kiểu dữ liệu | Kiểm tra thường dùng | Ví dụ |
|---|---|---|
| Chuỗi | Không rỗng, độ dài, pattern | Tên không trắng, tối đa 120 ký tự |
| Số nguyên | Giới hạn min/max | Số lượng từ 1 đến 500 |
| Số thập phân | Giới hạn và precision/scale | Tỷ lệ từ 0 đến 100 |
| Ngày/giờ | Có giá trị, khoảng ngày, không nằm trong quá khứ nếu nghiệp vụ yêu cầu | Ngày hẹn không trước hôm nay |
| Email | Định dạng và độ dài | Địa chỉ có cấu trúc hợp lệ |
| Enum | Chỉ nhận một giá trị được định nghĩa | Loại thành viên thuộc danh sách hỗ trợ |
| Tệp | Kích thước, định dạng thực tế và nội dung | PDF tối đa 10 MB |

Không nên dùng một biểu thức chính quy phức tạp cho mọi loại dữ liệu. Ví dụ, kiểm tra email bằng một regex quá chặt có thể từ chối địa chỉ hợp lệ theo chuẩn. Hãy dùng validator đã được kiểm chứng cho định dạng phổ biến, đồng thời xác nhận email thực sự bằng quy trình gửi mã nếu nghiệp vụ cần.

### 3.2. Kiểm tra bắt buộc và chuỗi chỉ chứa khoảng trắng

Một trường tên có thể không null nhưng vẫn không có nội dung hữu ích:

~~~java
String name = "   ";
~~~

Quy tắc bắt buộc nên xem xét cả null, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng. Với Bean Validation, **@NotNull** chỉ kiểm tra khác null; **@NotEmpty** kiểm tra không null và không rỗng; **@NotBlank** phù hợp với chuỗi phải có ít nhất một ký tự không phải khoảng trắng.

Ví dụ:

~~~java
public record CreateMemberRequest(
    @NotBlank
    @Size(max = 120)
    String fullName,

    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotBlank
    @Size(min = 12, max = 72)
    String password
) {}
~~~

Độ dài mật khẩu trong ví dụ chỉ là chính sách minh họa; hệ thống cần chọn giới hạn phù hợp với thuật toán băm, khả năng sử dụng và chính sách xác thực. Không nên cắt ngắn mật khẩu một cách âm thầm.

### 3.3. Giới hạn số và độ dài

Với số lượng, dùng ràng buộc min/max thay vì chỉ kiểm tra dữ liệu có thể parse thành số:

~~~java
public record AddBookCopiesRequest(
    @NotNull
    @Min(1)
    @Max(500)
    Integer quantity
) {}
~~~

Dùng wrapper như Integer khi cần phân biệt trường bị thiếu (null) với giá trị 0. Nếu dùng kiểu nguyên thủy int, giá trị mặc định 0 có thể làm mất thông tin rằng client không gửi trường.

Với tiền, nên cân nhắc kiểu Money hoặc BigDecimal thay vì double. Nếu dùng BigDecimal, xác định rõ precision, scale, đơn vị tiền tệ và cách làm tròn. Một trường amount hợp lệ về kiểu vẫn có thể không hợp lệ theo nghiệp vụ nếu âm hoặc vượt giới hạn giao dịch.

### 3.4. Chuẩn hóa trước hay sau validation?

Một số giá trị có thể được chuẩn hóa an toàn trước khi kiểm tra, ví dụ trim khoảng trắng ở hai đầu tên hoặc chuẩn hóa chữ hoa/chữ thường cho mã không phân biệt hoa thường. Tuy nhiên, không nên tự ý biến đổi dữ liệu làm thay đổi ý nghĩa người dùng nhập.

Một quy trình thường dùng:

1. Giới hạn kích thước request để tránh đầu vào quá lớn.
2. Binding và chuyển kiểu.
3. Chuẩn hóa có chủ đích, ví dụ trim chuỗi.
4. Kiểm tra ràng buộc cấu trúc.
5. Chuyển thành command hoặc Value Object.
6. Kiểm tra quy tắc nghiệp vụ với trạng thái hiện tại.

Hãy xác định rõ quy tắc có chạy trước hay sau chuẩn hóa. Ví dụ, nếu giới hạn độ dài tính trên chuỗi đã trim, hãy trim trước khi áp dụng giới hạn đó. Với mật khẩu, không trim hoặc đổi hoa/thường trừ khi chính sách xác thực quy định rõ như vậy.

### 3.5. Không nhầm kiểm tra định dạng với xác minh thực tế

Email có định dạng hợp lệ không chứng minh hộp thư tồn tại. Số điện thoại có đủ chữ số không chứng minh số đó thuộc người dùng. Ngày sinh hợp lệ về lịch không chứng minh người đăng ký có quyền khai báo ngày đó.

Validation kiểm tra cấu trúc; xác minh (verification) thu thập bằng chứng bổ sung như email OTP, SMS OTP, giấy tờ hoặc quy trình phê duyệt. Hai việc này có mục đích khác nhau và cần được thể hiện rõ trong trải nghiệm.

## 4. Kiểm tra nhiều trường

Cross-field validation cần đọc đồng thời hai hoặc nhiều giá trị. Quy tắc có thể là so sánh, tính toán hoặc xác định tính nhất quán của một nhóm trường.

Ví dụ:

- Ngày kết thúc phải sau ngày bắt đầu.
- Mật khẩu và xác nhận mật khẩu phải giống nhau.
- Giá trị giảm giá không được vượt giá gốc.
- Ít nhất một trong email hoặc số điện thoại phải được cung cấp.
- Ngày trả sách phải sau ngày mượn.
- Tổng tỷ lệ phân bổ phải bằng 100%.
- Quốc gia và mã bưu chính phải tương thích theo quy tắc của quốc gia đó.

### 4.1. Xác định trường sở hữu lỗi

Một quy tắc nhiều trường có thể gắn lỗi vào một trường cụ thể hoặc vào toàn bộ form. Ví dụ:

- Ngày kết thúc trước ngày bắt đầu: gắn lỗi vào endDate vì người dùng thường sửa trường đó.
- Mật khẩu xác nhận không khớp: gắn lỗi vào confirmPassword.
- Tổng tỷ lệ phân bổ không bằng 100%: hiển thị lỗi ở cấp form hoặc nhóm phân bổ.
- Không có email lẫn số điện thoại: có thể gắn lỗi vào nhóm liên hệ và hiển thị thông báo chung.

Việc gắn lỗi vào đúng vị trí giúp người dùng biết cần sửa ở đâu. Không nên gắn mọi lỗi cross-field vào một trường không liên quan chỉ để tận dụng cơ chế hiển thị lỗi sẵn có.

### 4.2. Ví dụ ngày bắt đầu và ngày kết thúc

Với một form đặt lịch, hai trường ngày cần thỏa mãn:

- Cả hai trường có định dạng hợp lệ.
- Nếu cả hai có giá trị thì endDate phải sau hoặc bằng startDate, tùy nghiệp vụ.
- Nếu một trường là tùy chọn, quy tắc so sánh cần xử lý trường hợp thiếu giá trị.

Một hàm kiểm tra đơn giản:

~~~java
boolean isValidRange(LocalDate startDate, LocalDate endDate) {
    return startDate == null
        || endDate == null
        || !endDate.isBefore(startDate);
}
~~~

Hàm trên chỉ kiểm tra quan hệ giữa hai ngày khi cả hai đã có giá trị. Quy tắc bắt buộc của từng trường cần được kiểm tra riêng. Cách tách này giúp thông báo “Ngày bắt đầu là bắt buộc” khác với “Ngày kết thúc phải sau ngày bắt đầu”.

### 4.3. Ví dụ mật khẩu xác nhận

Mật khẩu xác nhận thường là một trường chỉ tồn tại để giúp người dùng phát hiện lỗi gõ. Nó không cần lưu vào database hoặc chuyển thành dữ liệu miền.

Quy tắc:

~~~java
boolean passwordsMatch(String password, String confirmPassword) {
    return Objects.equals(password, confirmPassword);
}
~~~

Dùng so sánh null-safe để validator không ném NullPointerException khi một trường thiếu. Các ràng buộc bắt buộc và độ dài của password vẫn cần kiểm tra độc lập.

### 4.4. Tổng hợp nhiều giá trị

Với form phân bổ ngân sách, các tỷ lệ có thể phải cộng lại bằng 100. Đây là quy tắc trên một tập hợp chứ không chỉ một cặp trường.

~~~java
boolean totalsOneHundred(List<BigDecimal> percentages) {
    if (percentages == null || percentages.isEmpty()) {
        return false;
    }

    var total = percentages.stream()
        .filter(Objects::nonNull)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

    return total.compareTo(new BigDecimal("100")) == 0;
}
~~~

Trong triển khai thật, cần quyết định cách xử lý phần tử null, scale và sai số làm tròn. Với BigDecimal, dùng compareTo để so sánh giá trị số khi scale khác nhau, thay vì equals trong trường hợp không muốn phân biệt 100.0 với 100.00.

## 5. Kiểm tra điều kiện phụ thuộc

Conditional validation áp dụng khi quy tắc của một trường thay đổi dựa trên giá trị của trường khác hoặc ngữ cảnh request.

Ví dụ:

| Điều kiện | Quy tắc phát sinh |
|---|---|
| Chọn giao hàng tận nơi | Địa chỉ giao hàng bắt buộc |
| Chọn nhận tại cửa hàng | Mã cửa hàng bắt buộc; địa chỉ nhà không cần |
| Chọn thành viên học sinh | Tên trường học bắt buộc |
| Chọn thanh toán chuyển khoản | Tài khoản nhận hoặc thông tin tham chiếu cần có theo hợp đồng |
| Bật xuất hóa đơn | Tên đơn vị và mã số thuế cần được cung cấp |
| Chọn lịch định kỳ | Ngày kết thúc hoặc số lần lặp cần hợp lệ |
| Chọn loại tài khoản doanh nghiệp | Tên tổ chức và mã đăng ký cần có |

### 5.1. Mô tả điều kiện như một quy tắc rõ ràng

Một quy tắc phụ thuộc nên được diễn đạt thành câu điều kiện:

- Nếu deliveryMethod là HOME_DELIVERY thì shippingAddress phải có giá trị.
- Nếu deliveryMethod là STORE_PICKUP thì storeId phải có giá trị.
- Nếu invoiceRequired là true thì companyName và taxCode là bắt buộc.
- Nếu membershipType là STUDENT thì schoolName là bắt buộc.

Cách viết này giúp kiểm thử có thể liệt kê từng nhánh. Tránh đặt một biểu thức boolean quá dài trong Controller vì khó đọc và dễ bỏ sót trường hợp.

### 5.2. Không dựa vào trạng thái ẩn của giao diện

View có thể ẩn hoặc hiện trường theo lựa chọn của người dùng. Ví dụ, khi chọn nhận tại cửa hàng, form ẩn địa chỉ giao hàng và hiện danh sách cửa hàng. Nhưng client có thể gửi request trực tiếp với dữ liệu bất kỳ.

Server phải tự kiểm tra điều kiện phụ thuộc. Việc một trường bị ẩn không có nghĩa server có thể tin rằng nó không xuất hiện trong request. Nếu một field không áp dụng, hãy xác định server sẽ bỏ qua, từ chối hay yêu cầu nó vắng mặt; đừng để hành vi phụ thuộc ngẫu nhiên vào binder.

### 5.3. Trường không áp dụng nên được xử lý thế nào?

Có ba chính sách thường gặp:

1. **Bỏ qua:** giá trị của trường không liên quan bị bỏ qua và không được lưu.
2. **Từ chối:** nếu client gửi trường không áp dụng, server trả lỗi vì request vi phạm hợp đồng.
3. **Chuẩn hóa:** server chủ động đặt trường đó về null hoặc giá trị mặc định trước khi xử lý.

Chọn một chính sách phù hợp với API và bảo mật. Với dữ liệu nhạy cảm hoặc field có thể thay đổi quyền, nên từ chối hoặc loại bỏ có kiểm soát thay vì âm thầm chấp nhận mọi trường client gửi.

## 6. Validation ở các ranh giới MVC

Không có một vị trí duy nhất chịu trách nhiệm cho mọi loại kiểm tra. Mỗi tầng kiểm tra loại quy tắc phù hợp với trách nhiệm của nó.

| Tầng | Nên kiểm tra | Không nên chỉ dựa vào |
|---|---|---|
| View / trình duyệt | Phản hồi nhanh, required, type, min/max, hiển thị lỗi | JavaScript hoặc HTML validation như lớp bảo vệ duy nhất |
| Controller / request DTO | Binding, định dạng, kích thước, field constraints, cross-field của hợp đồng đầu vào | Trạng thái database cũ hoặc quyền nghiệp vụ phức tạp |
| Application Service | Điều kiện của ca sử dụng, quyền theo ngữ cảnh, dữ liệu tồn tại, trạng thái hiện tại | Việc client đã chạy validation |
| Domain Model / Value Object | Bất biến và chuyển trạng thái hợp lệ | Dữ liệu đầu vào chưa được chuyển đổi hoặc chưa có ngữ nghĩa |
| Database | Unique, foreign key, check constraint, tính toàn vẹn đồng thời | Việc mọi quy tắc nghiệp vụ đều có thể biểu diễn bằng SQL |

Một quy tắc có thể được củng cố ở nhiều tầng vì mục đích khác nhau. Ví dụ, email có thể được kiểm tra định dạng ở DTO, chuẩn hóa thành EmailAddress ở miền, và unique constraint được áp dụng ở database. Mỗi lớp bảo vệ một loại lỗi khác nhau.

### 6.1. Client-side validation

HTML có các thuộc tính như required, type=email, minlength, maxlength, min, max và pattern. Chúng giúp trình duyệt cảnh báo sớm mà không cần round trip đến server.

JavaScript có thể bổ sung kiểm tra phụ thuộc tức thời, ví dụ cập nhật trạng thái trường địa chỉ khi đổi phương thức giao hàng. Tuy nhiên, người dùng có thể tắt JavaScript, sửa request hoặc gọi API trực tiếp. Vì vậy, client-side validation chỉ cải thiện trải nghiệm; server vẫn phải kiểm tra lại.

### 6.2. Server-side validation

Server-side validation là nguồn kiểm tra có thẩm quyền cho dữ liệu request. Nó phải chạy ngay cả khi request đến từ một client không phải trình duyệt.

Trong Spring MVC, Bean Validation thường được kích hoạt bằng **@Valid** hoặc **@Validated** trên tham số phù hợp. Lỗi được đưa vào BindingResult hoặc được framework xử lý thành response lỗi, tùy loại Controller và cấu hình.

### 6.3. Quy tắc miền không chỉ là annotation

Một annotation như @NotBlank phù hợp với ràng buộc cấu trúc. Nhưng quy tắc như “không cho đặt lịch trong thời gian nhân viên nghỉ phép” cần dữ liệu từ hệ thống và có thể thay đổi theo trạng thái. Nó phù hợp hơn với application service hoặc domain policy.

Không cố nhồi truy vấn database vào custom validator chỉ để tất cả validation nằm trong một cơ chế. Validator nên tập trung vào điều kiện có thể đánh giá với dữ liệu và ngữ cảnh được cung cấp rõ ràng.

## 7. Triển khai field-level validation bằng Bean Validation

Ví dụ dưới đây dùng Jakarta Bean Validation trong ứng dụng Spring MVC. Các annotation phổ biến gồm:

| Annotation | Ý nghĩa |
|---|---|
| @NotNull | Giá trị không được null |
| @NotEmpty | Không null và không rỗng |
| @NotBlank | Chuỗi phải có ký tự không phải khoảng trắng |
| @Size | Độ dài hoặc số phần tử trong khoảng |
| @Min / @Max | Giới hạn số nguyên |
| @DecimalMin / @DecimalMax | Giới hạn số thập phân |
| @Positive / @PositiveOrZero | Số dương hoặc không âm |
| @Email | Kiểm tra định dạng email cơ bản |
| @Pattern | Giá trị khớp biểu thức chính quy |
| @Past / @PastOrPresent | Ngày/thời điểm trong quá khứ |
| @Future / @FutureOrPresent | Ngày/thời điểm trong tương lai |

Ví dụ request đăng ký thành viên:

~~~java
public record RegisterMemberRequest(
    @NotBlank(message = "Họ tên là bắt buộc")
    @Size(max = 120, message = "Họ tên tối đa 120 ký tự")
    String fullName,

    @NotBlank(message = "Email là bắt buộc")
    @Email(message = "Email không đúng định dạng")
    @Size(max = 254, message = "Email quá dài")
    String email,

    @NotNull(message = "Ngày sinh là bắt buộc")
    @Past(message = "Ngày sinh phải nằm trong quá khứ")
    LocalDate birthDate,

    @NotBlank(message = "Mật khẩu là bắt buộc")
    @Size(min = 12, max = 72, message = "Mật khẩu phải từ 12 đến 72 ký tự")
    String password
) {}
~~~

Annotation xác định quy tắc khai báo. Message có thể được đưa vào message bundle để hỗ trợ đa ngôn ngữ thay vì viết cứng trong DTO. Độ dài và chính sách mật khẩu cần được thống nhất với hệ thống xác thực.

### 7.1. Controller nhận lỗi validation

Với REST Controller:

~~~java
@PostMapping("/members")
public ResponseEntity<MemberResponse> register(
    @Valid @RequestBody RegisterMemberRequest request
) {
    var member = members.register(
        new RegisterMemberCommand(
            request.fullName(),
            request.email(),
            request.birthDate(),
            request.password()
        )
    );

    return ResponseEntity.status(HttpStatus.CREATED).body(member);
}
~~~

Nếu request không hợp lệ, Spring MVC có thể phát sinh MethodArgumentNotValidException. Một exception handler tập trung có thể chuyển lỗi thành cấu trúc API ổn định:

~~~java
public record FieldViolation(
    String field,
    String code,
    String message
) {}

public record ValidationErrorResponse(
    String type,
    String title,
    List<FieldViolation> errors
) {}

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationErrorResponse> handleValidation(
        MethodArgumentNotValidException exception
    ) {
        var errors = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> new FieldViolation(
                error.getField(),
                error.getCode(),
                error.getDefaultMessage()
            ))
            .toList();

        var body = new ValidationErrorResponse(
            "validation-error",
            "Dữ liệu gửi lên không hợp lệ",
            errors
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Ví dụ là cấu trúc minh họa; ứng dụng thực tế cần chuẩn hóa mã lỗi, xử lý lỗi object-level, tránh trả dữ liệu đầu vào nhạy cảm và hỗ trợ message localization. Không nên để mỗi Controller tự tạo một format lỗi khác nhau.

### 7.2. Controller nhận form HTML

Với server-rendered MVC, BindingResult cần đứng ngay sau tham số được kiểm tra:

~~~java
@PostMapping("/members")
public String register(
    @Valid @ModelAttribute("form") RegisterMemberForm form,
    BindingResult bindingResult,
    Model model,
    RedirectAttributes redirect
) {
    if (bindingResult.hasErrors()) {
        return "members/register";
    }

    members.register(toCommand(form));
    redirect.addFlashAttribute("message", "Đăng ký thành công");
    return "redirect:/members";
}
~~~

Khi có lỗi, trả lại template cùng dữ liệu đã nhập và lỗi tương ứng. Không chuyển hướng ngay khi validation thất bại nếu form cần giữ các field error trong request hiện tại; nếu dùng redirect, cần một cơ chế lưu lỗi và dữ liệu an toàn có chủ đích.

## 8. Triển khai cross-field validation ở cấp lớp

Bean Validation cho phép tạo constraint áp dụng lên cả một class. Validator nhận toàn bộ đối tượng nên có thể so sánh nhiều field.

Ví dụ, một khoảng thời gian đặt phòng cần ngày kết thúc không trước ngày bắt đầu.

### 8.1. Khai báo annotation

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidDateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Khoảng ngày không hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

### 8.2. Viết validator

~~~java
public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
        BookingRequest value,
        ConstraintValidatorContext context
    ) {
        if (value == null
            || value.startDate() == null
            || value.endDate() == null) {
            return true;
        }

        if (!value.endDate().isBefore(value.startDate())) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate()
            )
            .addPropertyNode("endDate")
            .addConstraintViolation();

        return false;
    }
}
~~~

### 8.3. Gắn constraint vào request

~~~java
@ValidDateRange
public record BookingRequest(
    @NotNull
    LocalDate startDate,

    @NotNull
    LocalDate endDate
) {}
~~~

Validator trả true khi một trong hai ngày null để các constraint @NotNull xử lý lỗi riêng. Khi cả hai có giá trị nhưng thứ tự sai, lỗi được gắn vào endDate. Cách này tránh tạo hai thông báo cho cùng một nguyên nhân.

Ví dụ trên cố định kiểu BookingRequest để tập trung vào cách hoạt động. Nếu muốn dùng lại validator cho nhiều DTO, có thể thiết kế annotation với tên property và dùng BeanWrapper hoặc một interface chung; cần cân nhắc tính an toàn kiểu và khả năng bảo trì.

## 9. Triển khai điều kiện phụ thuộc

Xét form đặt hàng có hai phương thức giao hàng: HOME_DELIVERY và STORE_PICKUP. Nếu giao tận nơi, shippingAddress bắt buộc; nếu nhận tại cửa hàng, storeId bắt buộc.

### 9.1. Mô hình dữ liệu đầu vào

~~~java
public enum DeliveryMethod {
    HOME_DELIVERY,
    STORE_PICKUP
}

@ValidDeliveryDetails
public record PlaceOrderRequest(
    @NotNull
    DeliveryMethod deliveryMethod,

    String shippingAddress,

    UUID storeId
) {}
~~~

### 9.2. Validator theo điều kiện

Khai báo constraint áp dụng cho toàn bộ request:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidDeliveryDetailsValidator.class)
public @interface ValidDeliveryDetails {
    String message() default "Thông tin giao hàng không hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

~~~java
public class ValidDeliveryDetailsValidator
        implements ConstraintValidator<ValidDeliveryDetails, PlaceOrderRequest> {

    @Override
    public boolean isValid(
        PlaceOrderRequest value,
        ConstraintValidatorContext context
    ) {
        if (value == null || value.deliveryMethod() == null) {
            return true;
        }

        boolean valid = switch (value.deliveryMethod()) {
            case HOME_DELIVERY ->
                value.shippingAddress() != null
                    && !value.shippingAddress().isBlank();

            case STORE_PICKUP ->
                value.storeId() != null;
        };

        if (valid) {
            return true;
        }

        context.disableDefaultConstraintViolation();

        if (value.deliveryMethod() == DeliveryMethod.HOME_DELIVERY) {
            context.buildConstraintViolationWithTemplate(
                    "Địa chỉ giao hàng là bắt buộc"
                )
                .addPropertyNode("shippingAddress")
                .addConstraintViolation();
        } else {
            context.buildConstraintViolationWithTemplate(
                    "Vui lòng chọn cửa hàng nhận hàng"
                )
                .addPropertyNode("storeId")
                .addConstraintViolation();
        }

        return false;
    }
}
~~~

Khi deliveryMethod chưa có giá trị, @NotNull xử lý lỗi riêng. Validator không cần lặp lại thông báo bắt buộc cho trường điều khiển.

### 9.3. Kiểm tra cả trường không áp dụng

Ví dụ trên chỉ yêu cầu trường tương ứng với phương thức giao hàng. Nếu hợp đồng không cho phép gửi shippingAddress khi STORE_PICKUP hoặc storeId khi HOME_DELIVERY, validator có thể kiểm tra thêm và trả lỗi cho field không áp dụng.

Điều đó phụ thuộc thiết kế API. Một số API bỏ qua trường không dùng; API khác muốn request tường minh và nghiêm ngặt. Dù chọn chính sách nào, hãy triển khai nhất quán và không để dữ liệu cũ từ form được lưu ngoài ý muốn khi người dùng đổi lựa chọn.

## 10. Validation có điều kiện dựa trên nhiều bước hoặc ngữ cảnh

Một số điều kiện phụ thuộc không chỉ nằm trong một DTO. Ví dụ, mức chiết khấu phụ thuộc loại khách hàng và chính sách hiện tại; ngày giao hàng phụ thuộc tồn kho và lịch vận chuyển; người dùng có được đổi email hay không phụ thuộc trạng thái xác minh.

Trong những trường hợp đó, cần phân biệt:

- **Điều kiện thuần trên dữ liệu request:** có thể kiểm tra bằng class-level validator.
- **Điều kiện cần dữ liệu ứng dụng:** cần gọi application service hoặc policy có quyền truy cập dữ liệu.
- **Điều kiện cần trạng thái miền:** cần kiểm tra trong use case hoặc Model.
- **Điều kiện cần dữ liệu bên ngoài:** có thể cần kiểm tra bất đồng bộ hoặc quy trình xác minh riêng.

Không nên để custom Bean Validator tự mở transaction hoặc gọi nhiều repository mà không có ranh giới rõ ràng. Validator được thiết kế tốt thường không có tác dụng phụ, dễ kiểm thử và cho kết quả ổn định với cùng một input.

### 10.1. Ví dụ bật hóa đơn

Giả sử request có invoiceRequired. Khi true, companyName và taxCode bắt buộc; khi false, hai trường này không được sử dụng.

Có thể tách thành một policy thuần:

~~~java
public final class InvoiceDetailsPolicy {
    public boolean isValid(PlaceOrderRequest request) {
        if (!request.invoiceRequired()) {
            return true;
        }

        return request.companyName() != null
            && !request.companyName().isBlank()
            && request.taxCode() != null
            && !request.taxCode().isBlank();
    }
}
~~~

Nếu taxCode cần kiểm tra tồn tại trong một hệ thống bên ngoài, policy thuần này chỉ kiểm tra hiện diện và cấu trúc. Việc xác minh mã số thuế cần một bước ứng dụng riêng, có timeout và xử lý lỗi dịch vụ ngoài.

### 10.2. Không dùng client-side state làm điều kiện có thẩm quyền

JavaScript có thể bật/tắt required, disabled hoặc hiển thị nhóm field theo lựa chọn. Nhưng server không được tin thuộc tính disabled hoặc trạng thái component. Client có thể bỏ thuộc tính, gửi giá trị khác hoặc gọi endpoint trực tiếp.

Luôn kiểm tra điều kiện trên request ở server. Với quy tắc phụ thuộc trạng thái database, kiểm tra lại ngay trong use case để tránh dữ liệu thay đổi giữa lúc người dùng mở form và lúc gửi form.

## 11. Nhóm validation và thứ tự kiểm tra

Trong một số form, có thể muốn chia validation theo nhóm hoặc theo giai đoạn. Ví dụ, bước đầu kiểm tra thông tin liên hệ; bước tiếp theo kiểm tra thanh toán; bước cuối kiểm tra toàn bộ đơn hàng.

Bean Validation hỗ trợ validation groups để áp dụng các nhóm constraint khác nhau. Tuy nhiên, chỉ nên dùng khi quy trình thật sự có nhiều giai đoạn và có lý do rõ ràng. Với form đơn giản, một tập constraint minh bạch thường dễ bảo trì hơn.

Thứ tự logic thường nên là:

1. **Binding:** dữ liệu có chuyển được sang kiểu đích không?
2. **Cấu trúc từng trường:** có thiếu giá trị, sai định dạng hoặc vượt giới hạn không?
3. **Quan hệ nhiều trường:** các giá trị có nhất quán với nhau không?
4. **Điều kiện phụ thuộc:** trường nào bắt buộc theo lựa chọn hiện tại?
5. **Quy tắc ca sử dụng:** dữ liệu có phù hợp với quyền và trạng thái hệ thống không?
6. **Ràng buộc lưu trữ:** database có chấp nhận thay đổi trong điều kiện đồng thời không?

Đây là thứ tự tư duy hữu ích, không phải thứ tự callback bắt buộc của mọi framework. Một số validator có thể chạy song song hoặc theo thứ tự không được bảo đảm. Nếu một quy tắc phụ thuộc vào kết quả của quy tắc khác, hãy viết nó sao cho xử lý null và input không hợp lệ an toàn.

### 11.1. Fail-fast và thu thập nhiều lỗi

Có hai cách phản hồi:

- **Fail-fast:** dừng ở lỗi đầu tiên. Phù hợp với bước không thể tiếp tục nếu dữ liệu nền chưa hợp lệ hoặc với kiểm tra bảo mật.
- **Collect-all:** thu thập nhiều lỗi độc lập để người dùng sửa trong một lần. Phù hợp với form đăng ký hoặc form cập nhật nhiều trường.

Không nên thu thập lỗi bằng cách thực thi các phép kiểm tra có tác dụng phụ. Validation nên thuần và an toàn; nếu một bước cần gọi dịch vụ ngoài, hãy xử lý như một phần của ca sử dụng với trạng thái và lỗi riêng.

## 12. Thiết kế thông báo lỗi

Thông báo lỗi cần giúp người dùng biết điều gì sai và cách sửa. Một thông báo như “Invalid input” không hữu ích nếu người dùng không biết field nào và giá trị nào cần thay đổi.

Một lỗi tốt thường có:

- Trường hoặc nhóm trường liên quan.
- Mã lỗi ổn định để client xử lý.
- Nội dung thân thiện với người dùng.
- Thông tin tham số cần thiết, ví dụ giới hạn tối đa.
- Ngôn ngữ phù hợp với locale.
- Không chứa dữ liệu nhạy cảm hoặc chi tiết triển khai.

Ví dụ:

| Mã lỗi | Thông báo |
|---|---|
| REQUIRED | Họ tên là bắt buộc |
| INVALID_EMAIL | Email không đúng định dạng |
| DATE_RANGE_INVALID | Ngày kết thúc phải sau ngày bắt đầu |
| PASSWORD_MISMATCH | Mật khẩu xác nhận chưa khớp |
| SHIPPING_ADDRESS_REQUIRED | Địa chỉ giao hàng là bắt buộc |
| STORE_REQUIRED | Vui lòng chọn cửa hàng nhận hàng |

### 12.1. Field error và global error

Field error gắn với một thuộc tính cụ thể, ví dụ email không đúng định dạng. Global error áp dụng cho toàn form hoặc một nhóm quy tắc, ví dụ tổng tỷ lệ phân bổ không bằng 100%.

Với cross-field validation, có thể gắn lỗi vào một field đại diện hoặc tạo object-level error. Hãy chọn cách phù hợp với UX và giữ cấu trúc ổn định để template hoặc client API hiển thị đúng.

### 12.2. Không đưa giá trị nhạy cảm vào thông báo

Không phản hồi lại mật khẩu, token, số định danh nhạy cảm hoặc toàn bộ request trong lỗi. Với đăng nhập, thông báo chung có thể phù hợp hơn việc nói email tồn tại nhưng mật khẩu sai, tùy chính sách chống dò tài khoản.

Log nội bộ cũng cần lọc dữ liệu nhạy cảm. Việc ghi toàn bộ request body để điều tra validation có thể làm lộ mật khẩu hoặc dữ liệu cá nhân.

### 12.3. Quốc tế hóa thông báo

Thông báo nên dùng message key và resource bundle để có thể dịch. Mã lỗi ổn định không phụ thuộc ngôn ngữ; nội dung hiển thị có thể thay đổi theo locale.

Ví dụ, API có thể trả code PASSWORD_MISMATCH; View tiếng Việt hiển thị “Mật khẩu xác nhận chưa khớp”, còn View tiếng Anh hiển thị nội dung tương ứng. Không dùng câu tiếng Việt làm mã logic mà client phải so sánh.

## 13. Hiển thị lỗi trong form HTML

Với server-rendered MVC, lỗi thường được hiển thị cạnh trường và ở đầu form nếu có global error.

~~~html
<form method="post" action="/members">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" aria-describedby="email-error" />
  <p id="email-error" class="field-error" role="alert">
    Email không đúng định dạng
  </p>

  <button type="submit">Đăng ký</button>
</form>
~~~

Đây là HTML minh họa cấu trúc accessible. Trong template thực tế, phần lỗi chỉ xuất hiện khi BindingResult có lỗi tương ứng. Thuộc tính aria-describedby liên kết trường với thông báo; có thể dùng aria-invalid="true" khi trường không hợp lệ.

Các nguyên tắc UX:

- Giữ lại dữ liệu hợp lệ người dùng đã nhập khi trả form.
- Đặt lỗi gần trường liên quan và có bản tóm tắt lỗi ở đầu form khi form dài.
- Không chỉ dùng màu đỏ; cần có văn bản và dấu hiệu truy cập được.
- Khi submit thất bại, đưa focus đến phần tóm tắt hoặc trường lỗi đầu tiên theo trải nghiệm phù hợp.
- Không xóa mật khẩu hoặc dữ liệu nhạy cảm khỏi trình duyệt theo cách vô tình làm người dùng hiểu rằng chúng đã được lưu.
- Đừng tự động cuộn hoặc chuyển focus liên tục khi người dùng đang sửa từng trường.

## 14. Validation trong API và hợp đồng lỗi

API nên trả cấu trúc lỗi ổn định, không phụ thuộc tên lớp Java hoặc message mặc định của framework.

Ví dụ response:

~~~json
{
  "type": "validation-error",
  "title": "Dữ liệu gửi lên không hợp lệ",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_EMAIL",
      "message": "Email không đúng định dạng"
    },
    {
      "field": "confirmPassword",
      "code": "PASSWORD_MISMATCH",
      "message": "Mật khẩu xác nhận chưa khớp"
    }
  ]
}
~~~

Với HTTP, 400 Bad Request thường dùng cho request không hợp lệ về cú pháp hoặc binding; 422 Unprocessable Content có thể được chọn cho nội dung đúng cú pháp nhưng không thỏa quy tắc validation. Hãy chọn một quy ước nhất quán và ghi trong API contract. Không cần dùng nhiều status code khác nhau cho cùng một loại lỗi nếu client không có lý do phân biệt.

Với xung đột trạng thái nghiệp vụ như email đã được sử dụng hoặc một lịch hẹn vừa bị người khác đặt, có thể dùng 409 Conflict. Đây là kết quả của trạng thái hệ thống, không chỉ là lỗi định dạng field.

## 15. Bảo mật và giới hạn của validation

Validation không thay thế bảo mật. Một request có thể hoàn toàn hợp lệ về định dạng nhưng vẫn không được phép thực hiện.

Các nguyên tắc quan trọng:

- Không tin dữ liệu từ browser, kể cả hidden field.
- Chỉ bind các trường được phép qua request DTO, tránh mass assignment.
- Kiểm tra authorization trên tài nguyên và hành động ở server.
- Dùng parameterized query hoặc ORM an toàn; validation không thay thế chống SQL injection.
- Escape output theo ngữ cảnh; dữ liệu hợp lệ vẫn có thể chứa nội dung nguy hiểm nếu render không an toàn.
- Bật CSRF protection cho form dùng cookie session.
- Giới hạn kích thước request, độ dài chuỗi, số phần tử collection và kích thước file.
- Không tiết lộ chi tiết hệ thống qua lỗi.
- Giới hạn tần suất với các endpoint kiểm tra từ xa như kiểm tra username hoặc mã xác minh.

### 15.1. Validation có truy vấn database và race condition

Ví dụ, validator kiểm tra email chưa tồn tại bằng cách truy vấn database. Hai request đồng thời có thể cùng thấy email chưa tồn tại rồi cùng cố gắng tạo tài khoản. Do đó, kiểm tra trước giúp đưa ra thông báo thân thiện nhưng không bảo đảm tính duy nhất.

Database cần unique constraint; application service xử lý lỗi vi phạm constraint và chuyển thành kết quả nghiệp vụ phù hợp. Nếu validator gọi database, cần tránh biến nó thành lớp bảo đảm duy nhất.

### 15.2. Tránh rò rỉ qua kiểm tra từ xa

Endpoint kiểm tra “email đã đăng ký chưa?” có thể giúp UX nhưng cũng cho phép kẻ tấn công dò tài khoản. Nếu cung cấp chức năng này, cân nhắc rate limit, thông báo không tiết lộ quá mức, xác thực hoặc cơ chế xác minh khác.

## 16. Kiểm thử validation

Kiểm thử cần xác nhận cả từng constraint và quan hệ giữa các trường.

### 16.1. Test một trường

- Chuỗi null, rỗng và chỉ có khoảng trắng bị xử lý đúng.
- Giá trị ở đúng giới hạn được chấp nhận.
- Giá trị vượt giới hạn bị từ chối.
- Định dạng sai tạo đúng mã lỗi.
- Giá trị Unicode hoặc ký tự hợp lệ không bị từ chối nhầm.

### 16.2. Test nhiều trường

Với khoảng ngày:

| startDate | endDate | Kết quả |
|---|---|---|
| 2026-05-01 | 2026-05-03 | Hợp lệ |
| 2026-05-03 | 2026-05-01 | Không hợp lệ |
| null | 2026-05-03 | Lỗi required của startDate |
| 2026-05-01 | null | Lỗi required của endDate |
| 2026-05-01 | 2026-05-01 | Theo quy tắc: cho phép hoặc từ chối |

Với mật khẩu:

- Hai giá trị giống nhau được chấp nhận nếu các field constraint khác hợp lệ.
- Hai giá trị khác nhau tạo lỗi trên confirmPassword.
- Một trong hai giá trị null không gây exception.
- Thông báo không tiết lộ nội dung mật khẩu.

### 16.3. Test điều kiện phụ thuộc

Với phương thức giao hàng:

- HOME_DELIVERY và địa chỉ có nội dung: hợp lệ.
- HOME_DELIVERY và địa chỉ null/rỗng: lỗi shippingAddress.
- STORE_PICKUP và storeId hợp lệ: hợp lệ.
- STORE_PICKUP và storeId null: lỗi storeId.
- deliveryMethod null: lỗi required riêng, validator không ném exception.
- Trường không áp dụng được xử lý theo chính sách đã định.

### 16.4. Test Controller và tích hợp

- Request sai không gọi application service ghi dữ liệu.
- Form HTML trả lại đúng template và giữ dữ liệu cần thiết.
- API trả status và error schema đúng.
- Không thể gửi thêm field nhạy cảm để thay đổi owner, role hoặc trạng thái.
- Quy tắc nghiệp vụ được kiểm tra dù request DTO hợp lệ.
- Database constraint vẫn bảo vệ dữ liệu khi có request đồng thời.

Có thể dùng Validator API để kiểm thử DTO trực tiếp; dùng MockMvc để kiểm tra binding, validation và response; dùng integration test cho unique constraint hoặc các quy tắc cần database.

## 17. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ dùng HTML required và JavaScript | Request trực tiếp bỏ qua được kiểm tra | Kiểm tra lại ở server |
| Chỉ kiểm tra từng field | Dữ liệu mâu thuẫn giữa nhiều trường vẫn được chấp nhận | Thêm class-level hoặc cross-field constraint |
| Đặt mọi validation trong Controller | Action dài, logic lặp và khó kiểm thử | Dùng DTO constraint, validator hoặc application policy |
| Validator tự truy cập nhiều repository | Khó kiểm thử, có tác dụng phụ và trộn trách nhiệm | Đưa kiểm tra phụ thuộc trạng thái vào application service |
| Dùng @NotNull cho chuỗi bắt buộc | Chuỗi rỗng hoặc toàn khoảng trắng vẫn qua | Dùng @NotBlank khi phù hợp |
| Validator cross-field không xử lý null | Ném exception thay vì trả lỗi | Để field constraint xử lý required và cross-field validator xử lý khi đủ dữ liệu |
| Ẩn trường trên UI nhưng không kiểm tra server | Client vẫn gửi được giá trị không hợp lệ | Kiểm tra điều kiện phụ thuộc phía server |
| Trả mọi lỗi thành một message chung | Người dùng không biết cần sửa trường nào | Trả field error và global error rõ ràng |
| Chỉ kiểm tra email chưa tồn tại | Race condition vẫn tạo trùng | Dùng unique constraint và xử lý conflict |
| Trả toàn bộ request trong lỗi | Có thể lộ mật khẩu hoặc dữ liệu cá nhân | Chỉ trả field, code và message an toàn |
| Dùng regex quá chặt cho dữ liệu phổ biến | Từ chối nhầm dữ liệu hợp lệ | Dùng validator phù hợp và xác minh khi cần |
| Nhầm validation với authorization | Dữ liệu đúng định dạng nhưng người dùng không có quyền vẫn được xử lý | Kiểm tra quyền riêng ở server |

## 18. Checklist thiết kế validation

- [ ] Mỗi trường có quy tắc phù hợp với kiểu dữ liệu và ý nghĩa nghiệp vụ.
- [ ] Phân biệt null, rỗng, khoảng trắng và giá trị mặc định.
- [ ] Giới hạn độ dài, số lượng, precision và kích thước request.
- [ ] Cross-field rule được viết rõ và gắn lỗi vào field hoặc form phù hợp.
- [ ] Conditional rule được kiểm tra ở server, kể cả khi UI ẩn/hiện field.
- [ ] Trường không áp dụng có chính sách rõ: bỏ qua, từ chối hoặc chuẩn hóa.
- [ ] DTO đầu vào chỉ chứa field client được phép gửi.
- [ ] Validation đầu vào được phân biệt với quy tắc nghiệp vụ và authorization.
- [ ] Lỗi có mã ổn định, thông báo dễ hiểu và không chứa dữ liệu nhạy cảm.
- [ ] Unique constraint và các ràng buộc đồng thời được bảo vệ ở database.
- [ ] Có test cho giá trị biên, null, lỗi cross-field, từng nhánh điều kiện và request trực tiếp.

Kiểm tra một trường giúp phát hiện lỗi cấu trúc của từng giá trị; kiểm tra nhiều trường bảo đảm dữ liệu nhất quán; điều kiện phụ thuộc phản ánh quy tắc chỉ xuất hiện khi một lựa chọn hoặc ngữ cảnh cụ thể được áp dụng. Khi đặt từng quy tắc ở đúng ranh giới và kiểm tra lại phía server, biểu mẫu MVC vừa thân thiện với người dùng vừa bảo vệ được tính hợp lệ của dữ liệu ứng dụng.
