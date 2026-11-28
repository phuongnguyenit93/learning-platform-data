# Denylist và giới hạn

## 1. Denylist giải quyết bài toán nào?

Denylist là tập giá trị, mẫu hoặc điều kiện mà hệ thống đã xác định cần từ chối. Khi đầu vào khớp một mục đang có hiệu lực, hệ thống áp dụng hành động đã quy định: từ chối thao tác, cách ly đối tượng, yêu cầu kiểm tra bổ sung hoặc tạo tín hiệu quan sát.

Ví dụ, một dịch vụ có thể cấm dùng các mã dự án `ADMIN`, `ROOT`, `SYSTEM` vì chúng dành cho hệ thống. Một cơ chế xác thực có thể từ chối một định danh phiên đã bị thu hồi. Một bộ lọc tại biên có thể phát hiện mẫu request gắn với một loại lạm dụng đã biết.

Các ví dụ này có chung việc nhận diện điều đã biết cần chặn, nhưng khác nhau về mức độ chắc chắn và hệ quả. Mã dành riêng là chính sách nghiệp vụ rõ ràng. Một mẫu phát hiện hành vi đáng ngờ thường chỉ là tín hiệu và có thể chặn nhầm dữ liệu hợp lệ. Thiết kế yêu cầu bảo mật phải thể hiện được khác biệt đó.

Trong chương Input validation, denylist cần được hiểu như một công cụ có phạm vi. Không khớp denylist chỉ có nghĩa là chưa khớp những điều kiện đang được kiểm tra; nó không chứng minh đầu vào hợp lệ, người gọi có quyền hay thao tác sẽ an toàn tại mọi điểm sử dụng.

Mục tiêu bài học là giúp người học chọn đúng vai trò cho denylist, mô tả giới hạn của nó và chuyển các lựa chọn đó thành yêu cầu có thể triển khai, đo lường và kiểm chứng.

## 2. Mô hình từ chối và kết luận được phép rút ra

### 2.1. Tập cấm không tự định nghĩa tập hợp lệ

Gọi `D` là tập giá trị bị cấm theo một chính sách. Nếu chỉ thực hiện phép kiểm tra:

```text
x thuộc D     -> từ chối theo chính sách D
x không thuộc D -> chưa bị chính sách D từ chối
```

thì nhánh thứ hai không đủ để kết luận `x` thuộc miền hợp lệ của ứng dụng. Với một trường mã dự án, ngoài việc không nằm trong danh sách dành riêng, giá trị còn phải đúng kiểu, độ dài, cấu trúc và quy tắc nghiệp vụ.

Một hợp đồng kết hợp có thể được diễn đạt như sau:

```text
Đạt kiểm tra giá trị =
    đúng kiểu và cấu trúc
    AND thuộc miền đầu vào được hỗ trợ
    AND không thuộc tập giá trị bị cấm đang có hiệu lực
    AND thỏa quan hệ nghiệp vụ giữa các trường
```

Sau bước đó vẫn có các trách nhiệm khác như kiểm tra quyền, giới hạn tần suất, tính nhất quán khi ghi dữ liệu và xử lý an toàn tại điểm sử dụng.

### 2.2. Chính sách phụ thuộc biểu diễn và ngữ cảnh

Một mục denylist không tồn tại độc lập với cách so sánh. Cần xác định nó khớp toàn bộ giá trị hay một phần, có phân biệt hoa thường không, có chuẩn hóa Unicode không và có phụ thuộc tenant hay loại thao tác không.

Ví dụ, quy tắc “cấm `ADMIN`” có ít nhất bốn cách hiểu:

- Cấm đúng token `ADMIN`.
- Cấm token đó không phân biệt hoa thường.
- Cấm mọi chuỗi chứa đoạn `ADMIN`.
- Cấm một giá trị sau một bước chuẩn hóa được quy định.

Các cách hiểu này tạo ra miền bị chặn khác nhau. Không được để lập trình viên tự chọn bằng một hàm `contains()` hoặc `toUpperCase()` trong khi tài liệu yêu cầu chỉ nói “chặn từ nhạy cảm”.

Ngữ cảnh dùng để chọn chính sách cũng cần đáng tin cậy. Nếu có denylist riêng cho từng tenant, tenant phải được xác định từ danh tính và cấu hình phía máy chủ, không lấy trực tiếp từ một thuộc tính request chưa được kiểm soát.

## 3. Những vai trò phù hợp của denylist

| Vai trò | Nguồn quyết định | Giá trị của cơ chế | Giới hạn cần ghi rõ |
| --- | --- | --- | --- |
| Tên hoặc mã dành riêng | Chính sách sản phẩm | Ngăn chiếm dụng namespace đã dành cho hệ thống | Không xác định toàn bộ cú pháp mã hợp lệ |
| Định danh đã bị thu hồi | Hệ thống quản lý phiên, khóa hoặc quyền | Chặn một đối tượng đã được quyết định không còn hiệu lực | Cần nhận diện đúng đối tượng, độ trễ và tính nhất quán |
| Chỉ báo lạm dụng đã xác minh | Quy trình điều tra và phản ứng | Giảm tiếp xúc với nguồn hoặc đối tượng đã biết có vấn đề | Chỉ báo có thể hết hiệu lực hoặc bị dùng chung với người hợp lệ |
| Mẫu phát hiện request đáng ngờ | Quy tắc phát hiện tại biên | Hỗ trợ ngăn chặn hoặc quan sát một số hành vi đã biết | Có thể bỏ sót biến thể và gây false positive |
| Dấu vân tay nội dung đã bị cấm | Quy trình phân loại nội dung | Nhận diện lại đúng đối tượng theo thuật toán đã chọn | Nội dung thay đổi có thể không còn khớp; phạm vi của dấu vân tay phải rõ |

Một danh sách định danh phiên bị thu hồi không cần phát hiện mọi kiểu tấn công để có ích: nhiệm vụ cụ thể của nó là nhận diện các phiên đã bị thu hồi. Tuy nhiên, danh sách đó chỉ có ý nghĩa sau khi hệ thống đã xác minh credential đúng giao thức, nhận diện đúng issuer và đối tượng, đồng thời áp dụng chính sách hiệu lực liên quan.

Tương tự, danh sách mã dành riêng không phải là một heuristic phát hiện tấn công. Nó là một phần của hợp đồng namespace. Khi yêu cầu có phạm vi hẹp và tập cấm được quản lý đầy đủ theo phạm vi đó, phép so sánh chính xác là cách triển khai dễ giải thích và kiểm chứng.

## 4. Vì sao denylist tổng quát thường bỏ sót?

### 4.1. Không gian biểu diễn lớn hơn danh sách mẫu

Một chuỗi có thể đi qua các lớp decode, chuẩn hóa, parse và ghép dữ liệu trước khi được sử dụng. Nếu bộ lọc và thành phần thực thi hiểu chuỗi khác nhau, việc không khớp ở lớp đầu không bảo đảm lớp sau nhận cùng một giá trị.

Các nguồn khác biệt thường gặp gồm:

- Một lớp phân biệt hoa thường trong khi lớp sau không phân biệt.
- Một lớp nhìn chuỗi mã hóa, lớp sau nhìn giá trị đã decode.
- Các thành phần chọn giá trị khác nhau khi query parameter hoặc JSON key bị lặp.
- Một lớp kiểm tra tên file, lớp sau xử lý tên hoặc đường dẫn sau một phép biến đổi khác.
- Các lớp dùng quy tắc Unicode hoặc so sánh định danh khác nhau.

Yêu cầu xử lý ở đây không phải là bổ sung vô hạn biến thể vào danh sách. Cần thống nhất hợp đồng parser, biểu diễn dùng để kiểm tra và biểu diễn được sử dụng tiếp, đồng thời giữ các kiểm soát chuyên biệt tại điểm sử dụng.

### 4.2. Chuỗi con không tương đương với ngữ nghĩa nguy hiểm

Một từ trông giống từ khóa truy vấn vẫn có thể là dữ liệu hợp lệ trong một đoạn văn. Ngược lại, một giá trị không chứa từ khóa bị cấm vẫn có thể gây vấn đề nếu ứng dụng dùng nó để dựng cấu trúc câu lệnh thiếu kiểm soát.

Với SQL, yêu cầu cốt lõi cho giá trị dữ liệu là dùng bind parameter đúng cách. Với những phần cấu trúc không thể nhận giá trị tùy ý như tên cột sắp xếp, ứng dụng nên ánh xạ lựa chọn đã được phép sang biểu thức định nghĩa sẵn. Denylist ký tự hoặc từ khóa không thay thế các trách nhiệm đó.

Tên người như `O'Connor` minh họa một false positive quen thuộc: dấu nháy đơn có thể là dữ liệu nghiệp vụ hợp lệ. Cấm ký tự này trên mọi field làm hỏng chức năng mà không tạo ra bằng chứng rằng mọi truy vấn của hệ thống đã an toàn.

### 4.3. Mẫu đã biết không bao phủ rủi ro chưa được mô tả

Một bộ quy tắc phát hiện chỉ phản ánh phạm vi đã được xây dựng và cấu hình. Kiểu đầu vào mới, đường vào khác hoặc thay đổi thư viện có thể tạo ra hành vi mà danh sách chưa bao phủ.

Vì vậy, không nên viết tiêu chí hoàn thành dạng “request không bị WAF chặn thì được coi là dữ liệu an toàn”. Gateway và WAF có thể là lớp hỗ trợ, còn ứng dụng vẫn phải xác định và thực thi hợp đồng đầu vào của chính nó.

### 4.4. Dữ liệu giống nhau có thể có ý nghĩa khác nhau theo vị trí

Chuỗi được phép trong nội dung mô tả không nhất thiết được phép làm tên file. Một hostname có cú pháp hợp lệ không tự chứng minh đích kết nối phù hợp chính sách mạng. Một ID đúng định dạng không chứng minh quyền đọc tài nguyên mang ID đó.

Denylist dùng chung cho mọi field dễ làm mất thông tin ngữ cảnh. Yêu cầu nên chỉ rõ nguồn, field và điểm sử dụng mà quy tắc áp dụng, thay vì đưa mọi dữ liệu qua một hàm “lọc đầu vào nguy hiểm” không có hợp đồng cụ thể.

## 5. False positive, false negative và cách đo giới hạn

False positive là dữ liệu hoặc thao tác hợp lệ bị quy tắc đánh dấu và xử lý như vi phạm. False negative là trường hợp thực sự thuộc lớp vi phạm cần phát hiện nhưng quy tắc không nhận diện được.

Để đo hai loại lỗi, trước hết phải có nhãn đối chiếu hoặc một quy trình đánh giá. Số request bị chặn trong log tự nó không cho biết bao nhiêu request đã bị chặn đúng.

Giả sử một tập đánh giá đã được gán nhãn có 10.000 request hợp lệ và 100 request thuộc lớp vi phạm đang xét. Một quy tắc chặn 80 request vi phạm, đồng thời chặn nhầm 50 request hợp lệ:

| Kết quả | Số lượng |
| --- | ---: |
| Vi phạm và bị chặn | 80 |
| Vi phạm nhưng không bị chặn | 20 |
| Hợp lệ nhưng bị chặn | 50 |
| Hợp lệ và không bị chặn | 9.950 |

Từ đó, tỷ lệ phát hiện trong tập vi phạm là `80 / 100 = 80%`. Tỷ lệ chặn nhầm trong tập hợp lệ là `50 / 10.000 = 0,5%`. Trong 130 request bị chặn, tỷ lệ được gán nhãn vi phạm chỉ khoảng `61,5%`.

Các con số trên chỉ mô tả tập đánh giá này. Chúng không chứng minh quy tắc sẽ có cùng hiệu quả với lưu lượng sản xuất, một loại tấn công khác hoặc phân bố người dùng khác. Một tỷ lệ chặn nhầm nhỏ vẫn có thể tạo ra nhiều lỗi chức năng khi lưu lượng hợp lệ lớn.

Yêu cầu quan sát nên phân biệt:

- Mức bao phủ đối với lớp hành vi đã xác định.
- Tỷ lệ chặn nhầm trên tập dữ liệu có nhãn và các nhóm sử dụng liên quan.
- Chi phí xử lý, độ trễ và mức tiêu thụ tài nguyên.
- Số trường hợp người dùng phải khắc phục hoặc liên hệ hỗ trợ.
- Thời gian phát hiện một quy tắc gây lỗi và thời gian vô hiệu hóa an toàn.

Không có một ngưỡng chung phù hợp cho mọi denylist. Chính sách dành riêng namespace có thể dùng tập ví dụ xác định rõ; một quy tắc phát hiện hành vi cần đánh giá cả hiệu quả phát hiện lẫn tác động đến người dùng hợp lệ.

## 6. Đặc tả từng quy tắc để tránh diễn giải tùy ý

Một mục denylist có thể cần nhiều thông tin hơn một chuỗi văn bản:

```text
Rule ID: PROJECT-CODE-RESERVED-01
Mục đích: giữ các mã định danh phục vụ chức năng hệ thống.
Phạm vi: trường code của thao tác tạo dự án.
Miền cơ sở: mã ASCII hoa, dài 3..32 ký tự, theo schema đã công bố.
Tập cấm: ADMIN, ROOT, SYSTEM.
Cách so sánh: khớp toàn bộ, phân biệt hoa thường.
Chuẩn hóa: không trim, không đổi hoa thường, không decode bổ sung.
Hành động: từ chối tạo dự án với mã PROJECT_CODE_RESERVED.
Tác động được phép: ghi sự kiện từ chối theo chính sách quan sát.
Tác động bị cấm: không ghi dự án, không phát sự kiện ProjectCreated.
Chủ sở hữu: nhóm quản lý chính sách namespace.
Phiên bản: gắn với snapshot chính sách được sử dụng khi kiểm tra.
```

Miền cơ sở quyết định một giá trị có đúng dạng mã dự án hay không. Denylist quyết định một mã đúng dạng có nằm trong phần namespace bị dành riêng hay không. Hai lý do từ chối nên được thể hiện rõ để người gọi có thể sửa dữ liệu đúng cách.

### 6.1. Exact match, prefix, glob và regex là các hợp đồng khác nhau

| Cách khớp | Ý nghĩa cần xác định | Rủi ro nếu chọn nhầm |
| --- | --- | --- |
| Exact match | Toàn bộ giá trị bằng một mục đã khai báo | Dùng chuỗi con thay thế sẽ chặn rộng hơn chính sách |
| Prefix | Giá trị bắt đầu bằng một tiền tố | Tiền tố quá rộng có thể chiếm gần hết namespace |
| Glob | Mẫu wildcard theo một cú pháp được công bố | Khác biệt cú pháp và ký tự escape gây diễn giải sai |
| Regex | Mẫu theo engine, tùy chọn và cách khớp xác định | Có thể gây chặn nhầm hoặc chi phí xử lý quá lớn |
| Khớp định danh đã parse | So sánh thành phần hoặc đối tượng có cấu trúc | Parse hoặc chuẩn hóa không thống nhất gây sai chính sách |

Không nên chuyển cấu hình literal thành regex mà không có yêu cầu. Nếu một mục là chuỗi literal thì dấu chấm, dấu ngoặc hoặc ký tự khác trong đó phải được hiểu theo nghĩa literal. Việc nhận regex từ nguồn có quyền cấu hình là một khả năng mạnh hơn và cần được quản lý tương ứng.

### 6.2. Chặn hay chỉ quan sát?

Hành động là một phần của chính sách, không chỉ là thuộc tính kỹ thuật của engine. Với một giá trị dành riêng chắc chắn không hợp lệ, từ chối là kết quả rõ ràng. Với một mẫu mới chưa biết tỷ lệ chặn nhầm, có thể triển khai chế độ quan sát theo quy trình đã thống nhất trước khi bật chặn.

Chế độ quan sát không được báo là đã ngăn chặn rủi ro. Báo cáo và dashboard phải phân biệt sự kiện phát hiện, quyết định chặn và kết quả cuối của request.

## 7. Ví dụ: mã dự án có miền cơ sở và tập dành riêng

Giả sử một dịch vụ cung cấp API tạo dự án. Yêu cầu sản phẩm quy định:

1. `code` bắt buộc là JSON string.
2. Mã dài từ 3 đến 32 ký tự ASCII, bắt đầu bằng chữ hoa `A..Z`.
3. Các ký tự tiếp theo chỉ gồm chữ hoa ASCII, chữ số ASCII và `_`.
4. Không tự trim hoặc chuyển đổi hoa thường.
5. Các mã `ADMIN`, `ROOT`, `SYSTEM` được dành riêng.
6. Một mã khác chỉ đạt bước kiểm tra giá trị; việc tạo dự án còn cần quyền và kiểm tra duy nhất theo tenant.

Các kết quả minh họa:

| Đầu vào | Kết quả tại chính sách mã |
| --- | --- |
| `PAYMENTS_2026` | Đạt kiểm tra giá trị |
| `ADMIN` | Từ chối do mã dành riêng |
| `ADMIN_TEAM` | Đạt kiểm tra giá trị nếu chỉ cấm exact match `ADMIN` |
| `admin` | Từ chối do sai miền ký tự |
| ` ADMIN` | Từ chối do sai miền ký tự |
| `ＡＤＭＩＮ` | Từ chối do không thuộc ASCII |
| `AB` | Từ chối do dưới độ dài tối thiểu |
| `null` trong JSON | Từ chối do thiếu giá trị hợp lệ |

`ADMIN_TEAM` là trường hợp hữu ích để phát hiện một triển khai vô tình dùng `contains("ADMIN")`. Nếu sản phẩm thật sự muốn dành riêng cả tiền tố, yêu cầu phải nói rõ và bộ ví dụ phải được sửa theo chính sách mới.

### 7.1. Yêu cầu có mã định danh

```text
SEC-CODE-01: Adapter từ chối kiểu JSON ngoài string, null và field code bị lặp.
SEC-CODE-02: Backend kiểm tra miền ký tự và độ dài của code.
SEC-CODE-03: Backend từ chối exact match với mục dành riêng trong snapshot hiệu lực.
SEC-CODE-04: Một lần đánh giá dùng đúng một snapshot chính sách bất biến.
SEC-CODE-05: Request bị từ chối không tạo dự án hoặc sự kiện tạo dự án.
SEC-CODE-06: Kết quả đạt chính sách mã không được dùng thay cho kiểm tra quyền.
SEC-CODE-07: Tính duy nhất theo tenant được bảo vệ ở thao tác ghi có kiểm soát cạnh tranh.
SEC-CODE-08: Bản cấu hình sai không được kích hoạt thành chính sách nhận mọi mã.
```

Snapshot là bản chính sách nhất quán mà một lần kiểm tra sử dụng. Nếu danh sách bị sửa ngay khi đang duyệt hoặc mỗi bước đọc một phiên bản khác nhau, khó giải thích request đã được quyết định theo quy tắc nào.

### 7.2. Minh họa Java

Đoạn mã sau chỉ minh họa chính sách giá trị của `code`. HTTP adapter chịu trách nhiệm kiểm tra kiểu JSON gốc, key trùng, schema request và giới hạn body trước khi gọi lớp này. Application service chịu trách nhiệm phân quyền và việc tạo dự án.

```java
import java.util.Set;
import java.util.regex.Pattern;

public final class ProjectCodePolicy {
    private static final Pattern CODE_SYNTAX =
            Pattern.compile("[A-Z][A-Z0-9_]{2,31}");

    private final long version;
    private final Set<String> reservedCodes;

    public ProjectCodePolicy(long version, Set<String> reservedCodes) {
        if (version <= 0 || reservedCodes == null) {
            throw new IllegalArgumentException("INVALID_POLICY_CONFIG");
        }

        Set<String> snapshot = Set.copyOf(reservedCodes);
        for (String code : snapshot) {
            if (code.length() < 3
                    || code.length() > 32
                    || !CODE_SYNTAX.matcher(code).matches()) {
                throw new IllegalArgumentException("INVALID_RESERVED_CODE");
            }
        }

        this.version = version;
        this.reservedCodes = snapshot;
    }

    public Decision evaluate(String rawCode) {
        if (rawCode == null
                || rawCode.length() < 3
                || rawCode.length() > 32
                || !CODE_SYNTAX.matcher(rawCode).matches()) {
            return new Decision(false, "PROJECT_CODE_INVALID", version);
        }

        if (reservedCodes.contains(rawCode)) {
            return new Decision(false, "PROJECT_CODE_RESERVED", version);
        }

        return new Decision(true, "PROJECT_CODE_POLICY_ACCEPTED", version);
    }

    public record Decision(
            boolean accepted,
            String reasonCode,
            long policyVersion) {
    }
}
```

Một snapshot minh họa được tạo bằng:

```java
ProjectCodePolicy policy = new ProjectCodePolicy(
        7L, Set.of("ADMIN", "ROOT", "SYSTEM"));

ProjectCodePolicy.Decision result = policy.evaluate("ADMIN_TEAM");
// accepted = true; policyVersion = 7
```

Các đặc điểm cần chú ý:

- Mẫu cú pháp xác định miền cơ sở, còn `Set.contains()` thực thi denylist exact match.
- Kiểm tra độ dài diễn ra trước regex; mẫu có độ dài bị chặn và cấu trúc đơn giản.
- Không tự biến đổi đầu vào; `admin` không được chuyển thành `ADMIN`.
- Bộ sưu tập cấu hình được sao chép thành tập không sửa đổi; dữ liệu null hoặc phần tử không hợp lệ làm việc dựng snapshot thất bại.
- Kết quả mang phiên bản chính sách để có thể liên kết quyết định với cấu hình đã dùng.
- Mã lỗi không chứa nguyên giá trị đầu vào và không tự thực hiện việc ghi log.

Ở lớp tải cấu hình, cần dựng và kiểm tra snapshot mới trước khi thay thế snapshot đang hoạt động. Nếu việc dựng thất bại, không được bắt lỗi rồi thay bằng `Set.of()` vì điều đó biến lỗi cấu hình thành việc xóa toàn bộ tập cấm.

Tập rỗng có thể là một trạng thái sản phẩm hợp lệ nếu đã được cho phép rõ ràng. Điều cần phân biệt là “chính sách được phê duyệt có tập cấm rỗng” và “lỗi tải dữ liệu bị diễn giải thành tập cấm rỗng”. Lớp minh họa không tự quản lý nguồn cấu hình, thời hạn hiệu lực hoặc quy trình phê duyệt.

### 7.3. Ràng buộc ở thời điểm sử dụng

Nếu chính sách thay đổi trong lúc request đang xử lý, hệ thống cần xác định thời điểm có hiệu lực. Có thể áp dụng snapshot được chọn lúc bắt đầu xử lý cho toàn bộ request; cũng có nghiệp vụ yêu cầu kiểm tra lại ngay trước một tác động nhạy cảm.

Nếu một mã vừa được thêm vào tập dành riêng, cần quyết định các dự án cũ mang mã đó được giữ nguyên, bị hạn chế hay phải chuyển đổi. Denylist dành cho thao tác tạo mới không mặc nhiên cho phép thay đổi hoặc xóa dữ liệu hiện có.

Tính duy nhất của mã là một yêu cầu khác. Hai request đồng thời đều có thể vượt qua kiểm tra “mã chưa tồn tại” trước khi ghi. Cần cơ chế bảo vệ duy nhất phù hợp ở tầng dữ liệu hoặc giao dịch; thêm denylist không giải quyết được điều kiện cạnh tranh này.

## 8. Vận hành denylist động

### 8.1. Vòng đời một mục

Với danh sách thay đổi theo sự kiện hoặc điều tra, mỗi mục cần có nguồn gốc và phạm vi đủ để vận hành. Các trường có thể gồm mã quy tắc, loại đối tượng, phạm vi áp dụng, lý do, thời điểm bắt đầu, thời điểm hết hạn, chủ sở hữu và phiên bản chính sách.

Không phải mọi danh sách đều cần thời hạn hết hiệu lực giống nhau. Mã namespace dành riêng có thể tồn tại lâu dài. Một địa chỉ mạng bị đánh dấu do lạm dụng có thể thay chủ hoặc phục vụ nhiều người, vì vậy cần quy trình xem xét lại phù hợp.

Đối với thời hạn, cần nói rõ cách xử lý mốc thời gian và độ lệch đồng hồ. Việc xóa vật lý một mục hết hạn có thể là tác vụ nền, nhưng quyết định request phải tuân theo hợp đồng hiệu lực, không phụ thuộc việc tác vụ dọn dẹp đã chạy hay chưa.

### 8.2. Độ trễ lan truyền và cache

Nếu nhiều instance cùng phục vụ request, một cập nhật denylist không tự xuất hiện đồng thời ở mọi instance. Yêu cầu phải xác định mức độ trễ chấp nhận được, cách nhận biết cache cũ và hành vi khi vượt quá ngưỡng.

Ví dụ, yêu cầu “phiên bị thu hồi không được sử dụng tiếp” còn thiếu một giới hạn thời gian và cách đo. Cần mô tả thời gian tối đa từ quyết định thu hồi đến lúc các đường xác thực liên quan phải từ chối, điều kiện vận hành được giả định và cách xử lý khi hệ thống không xác minh được trạng thái.

Giá trị ngưỡng phụ thuộc rủi ro và kiến trúc. Cache giúp giảm độ trễ truy vấn nhưng có thể kéo dài thời gian một mục mới chưa được thực thi; yêu cầu phải ghi nhận đánh đổi đó thay vì chỉ ghi “có cache”.

### 8.3. Hành vi khi nguồn chính sách lỗi

Không có một chế độ lỗi duy nhất đúng cho mọi denylist. Cần đánh giá vai trò của chính sách và các kiểm soát còn lại:

| Chính sách | Câu hỏi phải trả lời khi nguồn lỗi |
| --- | --- |
| Thu hồi credential nhạy cảm | Có thể cho phép thao tác khi không xác minh được trạng thái thu hồi không? Nếu không, từ chối ở đâu? |
| Namespace dành riêng | Có snapshot đã xác minh còn được phép dùng không, và dùng trong bao lâu? |
| Tín hiệu phát hiện bổ sung | Việc mất tín hiệu có chặn toàn bộ dịch vụ không, hay tiếp tục với các kiểm soát nền và cảnh báo? |
| Đích tích hợp bị cấm | Chính sách nào thực sự xác định đích được phép và kiểm soát kết nối khi dữ liệu cấm chưa tải được? |

Nếu một denylist là điều kiện bắt buộc trước khi thực hiện thao tác nhạy cảm, lỗi tải nó không được âm thầm trở thành “không có mục cấm”. Nếu một engine chỉ cung cấp tín hiệu quan sát, mất engine cũng không nên được mô tả thành đã mất toàn bộ cơ chế xác thực hoặc validation.

Tài liệu cần chốt hành vi cụ thể, giới hạn dùng snapshot cũ, cảnh báo và trách nhiệm khôi phục. Các lựa chọn này phải được liên kết với mục tiêu an toàn và tính sẵn sàng của nghiệp vụ.

## 9. Giới hạn tài nguyên của chính cơ chế lọc

Denylist cũng tiêu thụ tài nguyên và có thể trở thành nguồn gây lỗi nếu không được giới hạn. Một request rất dài, số lượng trường lớn hoặc một cấu hình có quá nhiều mẫu đều có thể làm tăng chi phí kiểm tra.

Với regex, cần xác định engine và cách áp dụng. Một số cấu trúc có thể gây backtracking tốn kém trên đầu vào được chọn bất lợi. Không nên cho rằng mọi hàm so khớp đều có thời gian xử lý tuyến tính hoặc có thể được ngắt an toàn chỉ bằng một timeout ở lớp gọi.

Các yêu cầu tài nguyên có thể bao gồm:

- Giới hạn byte request trước khi đọc hoặc parse quá nhiều dữ liệu.
- Giới hạn độ dài field và số phần tử trước khi duyệt danh sách.
- Giới hạn số lượng và kích thước mục chính sách được kích hoạt.
- Không biên dịch lại toàn bộ regex trên mỗi request.
- Đánh giá chi phí mẫu trước khi kích hoạt và đo độ trễ trên tập dữ liệu đại diện.
- Có cơ chế cô lập hoặc chọn bộ máy phù hợp nếu cho phép quy tắc phức tạp do bên khác cấu hình.

Không thay các mục exact match bằng regex chỉ để thống nhất một engine. Một tập giá trị literal có thể được lưu và so sánh trực tiếp, giúp hợp đồng rõ hơn và giảm độ phức tạp không cần thiết.

## 10. Bằng chứng kiểm thử cần có

Phần này mô tả các tiêu chí để kiểm chứng yêu cầu; nó không thay cho việc triển khai và thực thi bộ kiểm thử của dự án.

### 10.1. Kiểm thử ngữ nghĩa khớp

Với chính sách mã dự án, cần kiểm tra từng mã cấm, một mã hợp lệ không bị cấm, giá trị chứa mã cấm nhưng không bằng nó và các biên độ dài. Các trường hợp hoa thường, khoảng trắng, Unicode ngoài ASCII, thiếu trường và kiểu JSON sai phải có kết quả dự kiến rõ ràng.

Không chỉ kiểm tra “hệ thống đã từ chối”. Cần phân biệt từ chối vì sai miền cơ sở, vì thuộc tập dành riêng, vì không có quyền hoặc vì tài nguyên đã tồn tại. Điều đó chứng minh các yêu cầu đang được thực thi ở đúng trách nhiệm.

### 10.2. Kiểm thử vòng đời chính sách

| Tình huống | Bằng chứng cần thu |
| --- | --- |
| Kích hoạt snapshot mới hợp lệ | Request sử dụng được phiên bản mới theo hợp đồng triển khai |
| Cấu hình có mục sai định dạng | Snapshot mới không được kích hoạt; hành vi khôi phục đúng đặc tả |
| Nguồn cấu hình không khả dụng | Hệ thống dùng snapshot cũ hoặc từ chối theo chính sách đã chốt |
| Snapshot quá thời hạn cho phép | Không tiếp tục sử dụng vượt giới hạn đã định |
| Mục hết hạn | Kết quả quyết định đúng ở hai phía của mốc hiệu lực |
| Nhiều instance cập nhật khác thời điểm | Độ trễ lan truyền nằm trong giới hạn yêu cầu |
| Request đi qua consumer hoặc batch | Chính sách tương ứng vẫn được thực thi tại đường vào đó |
| Thay đổi chính sách trong lúc xử lý | Quyết định dùng snapshot và thời điểm kiểm tra đã quy định |

Nếu danh sách có scope theo tenant hoặc issuer, phải có trường hợp cùng giá trị nhưng khác scope để chứng minh không chặn nhầm hoặc bỏ sót do thiếu thành phần định danh.

### 10.3. Kiểm thử tác động và quan sát

Request bị từ chối phải không tạo tác động nghiệp vụ ngoài hợp đồng. Với API tạo dự án, bằng chứng gồm không có bản ghi dự án mới và không có sự kiện tạo dự án. Một sự kiện từ chối có thể được ghi nếu đã được cho phép và tuân theo chính sách dữ liệu.

Log nên chứa mã quy tắc, phiên bản chính sách, kết quả quyết định và correlation ID khi phù hợp. Không ghi nguyên credential, dữ liệu nhạy cảm hoặc đầu vào không giới hạn. Các trường được ghi phải có cấu trúc và giới hạn để dữ liệu người gọi không làm sai định dạng log.

Đối với quy tắc phát hiện có heuristic, cần thêm tập đánh giá hợp lệ và vi phạm, phân tích false positive, false negative và hiệu quả theo từng nhóm đường vào. Số lần quy tắc khớp chỉ là một số đo vận hành, không phải chứng cứ đầy đủ cho hiệu quả bảo mật.

## 11. Các yêu cầu dễ gây hiểu nhầm và cách viết rõ hơn

| Cách viết thiếu rõ ràng | Hướng đặc tả kiểm chứng được |
| --- | --- |
| “Chặn mọi ký tự nguy hiểm” | Xác định kiểu, miền giá trị và điểm sử dụng của từng field; quy định cơ chế an toàn tương ứng |
| “Cấm từ ADMIN” | Xác định exact match, prefix hay cách khớp khác, cùng chính sách hoa thường và Unicode |
| “Dữ liệu không có từ khóa bị cấm là an toàn” | Mô tả denylist chỉ quyết định những vi phạm đã xác định; giữ validation và kiểm soát tại điểm sử dụng |
| “Thu hồi có hiệu lực ngay” | Chốt thời điểm bắt đầu, giới hạn lan truyền và hành vi khi trạng thái không kiểm chứng được |
| “Nếu danh sách lỗi thì dùng danh sách trống” | Tách chính sách rỗng hợp lệ khỏi lỗi tải và quy định chế độ lỗi theo rủi ro |
| “WAF chịu trách nhiệm validation” | Chỉ rõ WAF phát hiện gì; backend vẫn thực thi schema và quy tắc nghiệp vụ |
| “Mọi cập nhật đều áp dụng cho dữ liệu cũ” | Xác định phạm vi tạo mới, đọc, sửa và xử lý dữ liệu đã tồn tại |

Trong review yêu cầu, cần hỏi “quy tắc này chứng minh điều gì?” và “điều gì vẫn chưa được kiểm soát?”. Nếu câu trả lời chỉ là đã chặn một số chuỗi quen thuộc, không nên nâng kết luận thành bảo đảm ngăn mọi tấn công trên một loại dữ liệu.

## 12. Chọn vai trò denylist trong thiết kế tổng thể

Một cách thiết kế có thể bảo vệ được bằng chứng là bắt đầu từ miền dữ liệu hợp lệ của nghiệp vụ, sau đó thêm các ngoại lệ cần cấm đã có lý do rõ ràng. Khi cần phát hiện lạm dụng đã biết, đặt quy tắc phát hiện vào đúng lớp và ghi rõ độ tin cậy, hành động cùng cách đánh giá tác động.

Với mỗi denylist, tài liệu nên chỉ ra đối tượng bị cấm, cách nhận diện, phạm vi, nguồn chính sách, vòng đời, chế độ lỗi và kiểm soát còn lại. Những yếu tố đó giúp phân biệt một chính sách từ chối cụ thể với một lời hứa bảo mật quá rộng.

Denylist có giá trị khi hệ thống biết rõ điều cần từ chối và thực thi đúng phạm vi đó. Giới hạn của nó phải được thể hiện trong yêu cầu: giá trị chưa bị cấm vẫn cần đạt hợp đồng đầu vào, kiểm tra quyền và cơ chế sử dụng dữ liệu an toàn trước khi tạo tác động nghiệp vụ.
