# Quy tắc case folding trong khôi phục tài khoản

Trong chương **Identifier Handling** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **Case folding rules** là các quy tắc quyết định hai định danh chỉ khác chữ hoa và chữ thường có được xem là cùng một định danh khi khôi phục tài khoản hay không.

Một người có thể đăng ký bằng tên “Minh.An” rồi nhập “minh.an” khi quên mật khẩu hoặc mất thiết bị xác thực. Sản phẩm phải biết đó là cùng tài khoản, một tài khoản khác hay đầu vào không được hỗ trợ. Quyết định này phải thống nhất với mô hình định danh đã thiết lập, không phụ thuộc ngôn ngữ của máy chủ hoặc cách một thành phần cơ sở dữ liệu tình cờ so sánh chuỗi.

Tra cứu đúng chỉ giúp xác định tài khoản đích. Quyền đặt lại mật khẩu, thay MFA, khôi phục passkey hay kiểm soát phiên đăng nhập vẫn cần bằng chứng và điều kiện riêng. Một quy tắc so sánh sai có thể đưa cả quy trình xác minh an toàn tới nhầm tài khoản.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt chuyển chữ hoa/thường, case folding và chuẩn hóa Unicode.
- Xác định định danh nào được so sánh không phân biệt hoa/thường và định danh nào phải giữ nguyên.
- Thiết kế khóa tra cứu nhất quán giữa đăng ký, đăng nhập và khôi phục.
- Nhận diện rủi ro do locale, collation, xung đột dữ liệu và thay đổi phiên bản quy tắc.
- Bảo đảm các cách viết hoa/thường không vượt qua giới hạn chống lạm dụng.
- Giữ quyền khôi phục gắn với tài khoản nội bộ ổn định sau bước tra cứu.

## 2. Case folding giải quyết điều gì?

**Case folding** tạo dạng dùng cho việc so sánh chuỗi không phân biệt chữ hoa/thường theo một tập quy tắc xác định. Dạng đó được dùng làm khóa so sánh, không nhất thiết phù hợp để hiển thị cho người dùng.

Với một chính sách chỉ hỗ trợ chữ cái ASCII và không phân biệt hoa/thường:

~~~text
Tên hiển thị khi đăng nhập: Minh.An

Khóa tra cứu:
Minh.An  -> minh.an
MINH.AN  -> minh.an
minh.an  -> minh.an
~~~

Ba đầu vào cùng ánh xạ tới một khóa. Điều đó chỉ hợp lệ nếu chính sách sản phẩm đã xác định chúng thuộc cùng không gian định danh và việc cấp phát tên cũng tuân theo quy tắc này.

Nếu sản phẩm cho phép hai tài khoản riêng “Minh.An” và “minh.an”, hệ thống khôi phục không được tự gộp chúng. Khi đó, chính sách hiện tại là phân biệt hoa/thường hoặc dữ liệu cần được giải quyết trước khi chuyển sang cách so sánh khác.

### Những thao tác dễ bị nhầm lẫn

| Thao tác | Mục đích | Điểm cần phân biệt |
| --- | --- | --- |
| Chuyển sang chữ thường | Tạo dạng chữ thường theo quy tắc của hàm chuyển đổi | Không tự tương đương với đầy đủ quy tắc Unicode case folding |
| Case folding | Tạo dạng phục vụ so sánh không phân biệt hoa/thường | Có thể thay đổi số ký tự; cần chính sách rõ |
| Chuẩn hóa Unicode | Xử lý các dạng biểu diễn Unicode theo dạng chuẩn đã chọn | Không tự quyết định mọi quan hệ hoa/thường |
| Bỏ dấu hoặc bỏ ký tự phân cách | Tạo một quan hệ tương đương khác | Không phải hệ quả mặc định của case folding |
| So khớp ký tự trông giống nhau | Nhận diện tương đồng về hình thức | Không được tự dùng để quyết định cùng chủ tài khoản |

Ví dụ, việc “An” và “an” cùng khóa không cho phép suy ra “an.nguyen” và “annguyen” cũng cùng khóa. Xóa dấu chấm là một quy tắc khác, có thể gây gộp nhầm tài khoản.

Tương tự, hai ký tự trông gần giống nhau nhưng thuộc hai hệ chữ khác nhau không mặc nhiên là một định danh. Case folding không phải thuật toán nhận diện người dùng theo hình dáng của tên.

## 3. Chọn chính sách theo loại định danh và phạm vi

Không nên đưa mọi chuỗi đầu vào qua một hàm “chuẩn hóa chung”. Trước hết phải xác định đang xử lý loại định danh nào và trong phạm vi nào.

| Dữ liệu | Cách xử lý về mặt chính sách |
| --- | --- |
| Username không phân biệt hoa/thường | Dùng đúng quy tắc tạo khóa đã được đăng ký và đăng nhập áp dụng |
| Username phân biệt hoa/thường | Giữ sự phân biệt; không tự chuyển thành chữ thường trong khôi phục |
| Email | Dùng chính sách email riêng; không áp dụng máy móc quy tắc username cho toàn địa chỉ |
| Định danh từ nhà cung cấp danh tính | Tuân theo hợp đồng của loại định danh và nhà cung cấp |
| Định danh tài khoản nội bộ dạng opaque | Giữ cách so sánh được hệ thống quy định; không tự diễn giải hoặc sửa chuỗi |
| Mật khẩu, token, OTP dạng chữ, mã dự phòng | Không áp dụng quy tắc case folding của username |

Một email có nhiều thành phần với ý nghĩa khác nhau. Việc một thành phần được so sánh không phân biệt hoa/thường không chứng minh toàn bộ địa chỉ có thể được biến đổi tùy ý. Các phép bỏ dấu chấm hoặc bỏ phần hậu tố của địa chỉ cũng không được tự suy rộng từ hành vi của một dịch vụ email cụ thể.

Nếu sản phẩm đã chọn một quan hệ tương đương cho email đăng nhập, quan hệ đó cần được quản lý xuyên suốt vòng đời địa chỉ. Luồng khôi phục không được tự tạo một quan hệ rộng hơn.

### Phạm vi tổ chức vẫn là một phần của khóa

Một khóa tra cứu có thể được hiểu như sau:

~~~text
đích_tra_cứu =
    phạm_vi_đã_xác_định
    + loại_định_danh
    + khóa_so_sánh_theo_chính_sách
~~~

Hai tổ chức có thể cùng có username “minh.an”. Dù khóa sau folding giống nhau, chúng không tự trở thành cùng tài khoản.

Máy chủ phải xác định phạm vi theo hành trình sản phẩm hỗ trợ và kiểm tra ngữ cảnh nhận được. Một giá trị tenant do client gửi không tự tạo quyền thao tác trên tài khoản trong tenant đó.

## 4. Hợp đồng tạo khóa tra cứu phải rõ đến mức nào?

Một quy tắc dùng cho khôi phục nên trả lời được các câu hỏi sau:

1. Loại định danh và phạm vi nào áp dụng quy tắc này?
2. Sản phẩm có phân biệt hoa/thường không?
3. Tập ký tự đầu vào nào được hỗ trợ?
4. Có xử lý khoảng trắng đầu/cuối không, hay từ chối?
5. Có chuẩn hóa Unicode không; nếu có, theo dạng và thứ tự nào?
6. Dùng ASCII folding, Unicode case folding mặc định hay một quy tắc khác?
7. Giới hạn độ dài đầu vào và khóa đầu ra là bao nhiêu?
8. Phiên bản quy tắc được xác định ở đâu?
9. Cơ sở dữ liệu phải so sánh khóa bằng quan hệ nào?
10. Khi hai tài khoản trở thành cùng khóa, hệ thống xử lý ra sao?

Chính sách phải do máy chủ xác định theo không gian định danh. Không chấp nhận việc client chọn “so sánh không phân biệt hoa/thường” hoặc gửi một số phiên bản cũ để thay đổi tài khoản được tra cứu.

Có thể lưu cả giá trị dùng để hiển thị và khóa tra cứu:

~~~text
account_id: tài khoản nội bộ ổn định
username_display: Minh.An
username_lookup_key: minh.an
identifier_policy: username-ascii-ci-v1
~~~

Đây là mô hình minh họa. Khóa tra cứu phục vụ phân giải định danh, còn account_id mới là liên kết ổn định với giao dịch khôi phục.

Giá trị hiển thị vẫn là dữ liệu đầu vào không đáng tin khi được đưa vào HTML, log hoặc thông báo. Giữ cách viết người dùng chọn không loại bỏ yêu cầu mã hóa đầu ra và kiểm soát dữ liệu.

## 5. Ví dụ đầy đủ với chính sách ASCII

Giả sử một sản phẩm mới chọn chính sách minh họa sau:

- Username dài từ 3 đến 64 ký tự.
- Chỉ cho phép chữ cái ASCII, chữ số, dấu chấm, gạch dưới và gạch nối.
- Không phân biệt chữ hoa và chữ thường.
- Không bỏ khoảng trắng; khoảng trắng là đầu vào không hợp lệ.
- Không bỏ dấu chấm, không bỏ dấu và không tìm gần đúng.
- Khóa tra cứu giữ nguyên ký tự hợp lệ, chỉ đổi A–Z thành a–z.

Giới hạn và tập ký tự này là lựa chọn của ví dụ, không phải yêu cầu chung cho mọi hệ thống. Không được áp chính sách mới này trực tiếp lên dữ liệu cũ có Unicode hoặc có quy tắc khác.

Một hàm Java minh họa:

~~~java
public final class UsernameLookupKey {

    private UsernameLookupKey() {
    }

    public static String fromAsciiUsername(String raw) {
        if (raw == null || raw.length() < 3 || raw.length() > 64) {
            throw new IllegalArgumentException("Invalid username format");
        }

        StringBuilder key = new StringBuilder(raw.length());

        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);

            if (c >= 'A' && c <= 'Z') {
                c = (char) (c + ('a' - 'A'));
            }

            boolean allowed =
                    (c >= 'a' && c <= 'z')
                    || (c >= '0' && c <= '9')
                    || c == '.'
                    || c == '_'
                    || c == '-';

            if (!allowed) {
                throw new IllegalArgumentException("Invalid username format");
            }

            key.append(c);
        }

        return key.toString();
    }
}
~~~

Hàm này có phạm vi cố ý hẹp: mọi ký tự ngoài tập ASCII đã chọn đều bị từ chối. Vì chỉ chấp nhận các ký tự đó, độ dài chuỗi và số ký tự được chấp nhận không gặp vấn đề cặp surrogate của Unicode.

Việc chuyển A–Z được thực hiện trực tiếp nên không phụ thuộc locale mặc định của tiến trình. Kết quả cũng không phụ thuộc ngôn ngữ mà người dùng chọn trên giao diện.

| Đầu vào | Kết quả theo chính sách ví dụ |
| --- | --- |
| Minh.An | minh.an |
| MINH.AN | minh.an |
| minh.an | minh.an |
| minh-an | minh-an, khác minh.an |
| minh_an | minh_an, khác minh.an |
| minh.an kèm một khoảng trắng cuối | Từ chối theo định dạng |
| Tên chứa chữ có dấu | Từ chối theo tập ký tự của ví dụ |
| Chuỗi chỉ có hai ký tự | Từ chối theo giới hạn độ dài |

Hàm chỉ tạo khóa; nó không truy vấn tài khoản và không xác minh người yêu cầu. Một lỗi định dạng công khai có thể được mô tả theo quy tắc áp dụng cho mọi đầu vào, nhưng không được thêm thông tin như “username có thật nhưng viết sai hoa/thường”.

Hàm tương đương phải được dùng khi cấp phát tên, đăng nhập, đổi username, tạo bí danh và khôi phục. Nếu đăng ký giữ hai tên riêng mà khôi phục gộp chúng, chỉ sửa hàm trong endpoint khôi phục sẽ tạo thêm rủi ro.

### Vì sao không chỉ gọi chuyển sang chữ thường?

Trong Java, việc chuyển chữ thường với locale mặc định có thể phụ thuộc môi trường chạy. Chỉ đổi cấu hình máy chủ cũng có thể khiến cùng đầu vào nhận kết quả khác.

Chọn locale rõ ràng, chẳng hạn Locale.ROOT cho một thao tác phù hợp, giúp loại bỏ sự phụ thuộc vào locale mặc định. Tuy nhiên, chuyển sang chữ thường với locale rõ ràng vẫn không tự trở thành đầy đủ Unicode case folding.

Không thay hợp đồng sản phẩm bằng một hàm có tên nghe gần giống. Với chính sách ASCII ở trên, hàm chuyển đổi trực tiếp đủ rõ. Với định danh Unicode, cần một thiết kế khác được xác định và kiểm tra riêng.

## 6. Khi sản phẩm hỗ trợ định danh Unicode

Unicode có nhiều trường hợp quan hệ chữ hoa/thường phức tạp hơn A–Z. Không nên mở rộng hàm ASCII bằng vài phép thay thế thủ công rồi gọi đó là hỗ trợ Unicode đầy đủ.

### 6.1. Folding có thể thay đổi số ký tự

Với Unicode full case folding mặc định, chữ “ß” có thể được ánh xạ thành “ss”. Vì vậy, hai tên như “Straße” và “STRASSE” có thể nhận cùng dạng so sánh theo chính sách đó.

Các dạng sigma “Σ”, “σ” và “ς” cũng minh họa việc quan hệ dùng cho so sánh không luôn giống phép chuyển từng ký tự sang chữ thường.

Hệ quả thiết kế:

- Không giả định một ký tự đầu vào luôn tạo đúng một ký tự đầu ra.
- Không cắt khóa đầu ra để ép vừa cột dữ liệu.
- Kiểm tra giới hạn trên khóa sau biến đổi bên cạnh giới hạn đầu vào.
- Phát hiện xung đột trước khi coi tên mới là duy nhất.
- Không dùng khóa đã folding để thay thế tên hiển thị.

Nếu hai tài khoản đang tồn tại có tên trở thành cùng khóa, quyền khôi phục không được quyết định theo bản ghi được truy vấn ra trước.

### 6.2. Locale và quy tắc mặc định là hai quyết định khác nhau

Các chữ I, i, İ và ı là nhóm ví dụ cho thấy chuyển hoa/thường có thể liên quan tới quy tắc ngôn ngữ.

Một hệ thống định danh toàn sản phẩm thường cần quy tắc ổn định theo chính sách, không phụ thuộc locale của máy chủ, trình duyệt hoặc ngôn ngữ thông báo. Nếu sản phẩm chọn biến thể riêng theo ngôn ngữ, biến thể đó phải thuộc hợp đồng định danh và được áp dụng nhất quán.

Không thử lần lượt nhiều locale cho đến khi tìm thấy tài khoản. Cách làm đó mở rộng quan hệ tương đương theo kết quả dữ liệu và có thể chọn nhầm danh tính.

### 6.3. Chuẩn hóa Unicode phải được quyết định riêng

Một chữ có dấu có thể được biểu diễn bằng một mã dựng sẵn hoặc bằng chuỗi mã gồm chữ và dấu kết hợp. Case folding và chuẩn hóa Unicode giải quyết những vấn đề khác nhau.

Một đặc tả Unicode cần chỉ rõ chuỗi bước, chẳng hạn:

~~~text
Giới hạn kích thước đầu vào
    -> kiểm tra đầu vào theo chính sách
    -> chuẩn hóa theo dạng đã chọn
    -> full case folding theo quy tắc đã chọn
    -> chuẩn hóa sau folding nếu đặc tả yêu cầu
    -> kiểm tra khóa kết quả
    -> tra cứu chính xác trong đúng phạm vi
~~~

Đây là khuôn mô tả để làm rõ hợp đồng, không phải một thuật toán dùng được cho mọi sản phẩm.

NFC và NFKC không thể được thay thế cho nhau chỉ vì cùng mang tên chuẩn hóa. Một dạng có thể duy trì những phân biệt mà dạng khác xử lý theo quan hệ tương thích. Việc chọn dạng ảnh hưởng trực tiếp tới khả năng hai tên trở thành một khóa.

Không bỏ dấu hoặc loại bỏ mọi ký tự “không nhìn thấy” một cách chung chung. Chính sách có thể từ chối một số đầu vào, nhưng tự xóa ký tự rồi tìm một tài khoản khác là một quyết định về danh tính cần được đánh giá riêng.

### 6.4. Quy tắc phải có khả năng tái lập

Nếu dùng thư viện hoặc dữ liệu Unicode, cần biết phiên bản và cấu hình tạo ra khóa. Các thành phần triển khai bằng ngôn ngữ khác nhau phải tạo cùng kết quả cho cùng tập dữ liệu được hỗ trợ.

Không mặc định trình duyệt, Java và cơ sở dữ liệu sẽ hiểu “không phân biệt hoa/thường” giống nhau.

Một số tính chất cần xác minh khi lựa chọn triển khai gồm:

- Cùng đầu vào, phạm vi và chính sách luôn cho cùng khóa.
- Khóa đã chuẩn hóa không tiếp tục thay đổi khi chạy lại cùng phép biến đổi.
- Những cặp tên được tuyên bố tương đương thực sự cùng khóa.
- Những phân biệt cần giữ không bị biến mất.
- Phiên bản mới không được đưa vào sản xuất trước khi kiểm tra xung đột dữ liệu.

Các tính chất này giúp kiểm tra tính nhất quán. Chúng không thay thế việc lựa chọn đúng quan hệ tương đương cho sản phẩm.

## 7. Cơ sở dữ liệu và các thành phần phải cùng một hợp đồng

Một cách triển khai rõ ràng là tạo khóa trong thành phần có thẩm quyền rồi so sánh khóa bằng quan hệ chính xác đã chọn. Collation của cơ sở dữ liệu phải tương thích với cách đó.

Collation là quy tắc so sánh và sắp xếp chuỗi. Một collation không phân biệt hoa/thường có thể có thêm hành vi về dấu hoặc dạng ký tự. Không nên chỉ nhìn nhãn “case insensitive” rồi coi nó giống hệt thuật toán trong ứng dụng.

Ví dụ, nếu ứng dụng muốn giữ “cafe” và “café” khác nhau nhưng cơ sở dữ liệu lại coi chúng bằng nhau, ràng buộc duy nhất hoặc truy vấn có thể không còn phản ánh chính sách đã công bố.

Cần xác định rõ:

- Cột nào lưu giá trị hiển thị, cột nào lưu khóa so sánh.
- Ràng buộc duy nhất bao gồm phạm vi tổ chức và loại định danh nào.
- Các bí danh đang có hiệu lực được tính vào tính duy nhất ra sao.
- So sánh khóa có thực hiện thêm biến đổi ngoài dự kiến không.
- Cache, chỉ mục tìm kiếm và dịch vụ phụ có đang dùng cùng phiên bản quy tắc không.

Một bất biến quan trọng là:

~~~text
Trong cùng phạm vi và loại định danh,
một khóa đang có hiệu lực không được phân giải tới hai tài khoản khác nhau.
~~~

Có thể có nhiều cách viết hoặc bí danh của cùng một tài khoản, nhưng không được để một khóa hiện hành chọn giữa nhiều chủ tài khoản.

### Tra cứu phải trả kết quả có cấu trúc nội bộ

~~~text
resolveRecoveryTarget(rawIdentifier, serverContext):
    scope = determineSupportedScope(serverContext)
    policy = loadActiveIdentifierPolicy(scope, identifierType)

    key = policy.createLookupKey(rawIdentifier)
    matches = authoritativeLookup(scope, identifierType, key)

    if matches points to no account:
        return INTERNAL_NO_MATCH

    if matches points to multiple accounts:
        return INTERNAL_AMBIGUOUS

    account = loadAccount(matches.singleAccountId)

    if account is not eligible for this recovery purpose:
        return INTERNAL_UNAVAILABLE

    return INTERNAL_TARGET(account.id, scope, policy.version)
~~~

Các trạng thái trên phục vụ xử lý nội bộ. Người chưa xác minh không mặc nhiên được biết tài khoản có tồn tại, có bí danh hay đang bị giới hạn.

Truy vấn phải được tham số hóa. Không ghép trực tiếp khóa hoặc username thô vào câu lệnh truy vấn.

Nếu cache có thể trả ánh xạ cũ sau khi đổi tên hoặc đổi chính sách, cần kiểm tra lại dữ liệu có thẩm quyền trước những quyết định cấp quyền nhạy cảm. Cache không được biến một kết quả tra cứu lỗi thời thành quyền khôi phục.

## 8. Xử lý xung đột và chuyển đổi chính sách

Thay đổi case folding là thay đổi quan hệ giữa tên và tài khoản. Đây không chỉ là tối ưu cách lưu chuỗi.

Giả sử hệ thống cũ phân biệt hoa/thường:

~~~text
Tài khoản A: Lan
Tài khoản B: lan
~~~

Nếu quy tắc mới đưa cả hai về “lan”, hệ thống đang có xung đột. Không thể giải quyết bằng cách lấy tài khoản mới nhất, tài khoản hoạt động gần nhất hoặc bản ghi đầu tiên.

Một quá trình chuyển đổi cần có các bước về mặt thiết kế:

1. Xác định đầy đủ quy tắc cũ và quy tắc mới.
2. Tính trước khóa mới cho các định danh thuộc phạm vi cần chuyển.
3. Tìm các nhóm xung đột giữa những tài khoản khác nhau.
4. Giải quyết từng nhóm theo quy trình có thẩm quyền, bao gồm ảnh hưởng đến bí danh và tên hiển thị.
5. Ngăn tạo thêm xung đột trong thời gian chuyển đổi.
6. Chuyển đồng bộ các đường cấp phát tên, đăng nhập, khôi phục và dữ liệu liên quan.
7. Kiểm tra lại tính duy nhất, cache và giao dịch đang tồn tại trước khi coi chuyển đổi hoàn tất.

Một trường phiên bản không tự giải quyết vấn đề. Nếu hai phiên bản cùng có hiệu lực và cùng chuỗi nhập có thể trỏ tới hai tài khoản, hệ thống vẫn cần cách phân giải rõ ràng hoặc phải dừng ở trạng thái chưa xác định được đích.

Không thêm tùy tiện một lượt “thử khóa cũ, nếu không có thì thử khóa mới”. Đọc theo hai quy tắc chỉ phù hợp khi đã có thiết kế ngăn mơ hồ, ngăn đổi chủ và kiểm soát việc cấp phát tên trong giai đoạn chuyển đổi.

### Đổi tên và tái sử dụng định danh

Sau khi người dùng đổi username, bí danh cũ có thể được giữ, thu hồi hoặc chỉ lưu cho kiểm toán. Trạng thái nào được phép khởi tạo khôi phục phải được xác định rõ.

Nếu tên cũ được cấp lại cho người khác, giao dịch đã phát hành cho chủ cũ không được chuyển sang chủ mới. Lưu account_id ổn định từ thời điểm xác định đích giúp tránh việc diễn giải lại username ở bước hoàn tất.

Đổi cách viết hoa/thường để hiển thị cũng cần giữ tính nhất quán: nếu “Minh.An” và “minh.an” cùng khóa, thay cách hiển thị không được vô tình tạo một chủ tài khoản mới.

## 9. Sau tra cứu: cố định tài khoản và giới hạn quyền

Case folding chỉ được áp dụng cho định danh theo chính sách. Nó không phải bước “làm sạch” chung cho dữ liệu khôi phục.

Một giao dịch có thể liên kết về mặt khái niệm với:

~~~text
account_id: tài khoản đã được phân giải
tenant_id: phạm vi đã xác định
purpose: hành động khôi phục cụ thể
transaction_id: giao dịch hiện tại
identifier_policy_version: thông tin phục vụ nhất quán và kiểm toán
expires_at: thời hạn theo chính sách
state: trạng thái giao dịch
~~~

Thông tin được lưu ở máy chủ hoặc được bảo vệ theo mô hình token đã chọn. Không tin account_id do client tự thay đổi chỉ vì client cũng gửi đúng một username.

Khi tiếp tục giao dịch, máy chủ xác minh bằng chứng cho đúng tài khoản và hành động. Không lấy username trong biểu mẫu hoặc token rồi chạy một lượt tra cứu mới để quyết định lại chủ thể.

### Không folding bí mật xác thực

Nếu một token có chuỗi “Ab9X” và hệ thống token phân biệt hoa/thường, đổi nó thành “ab9x” làm thay đổi giá trị. Tương tự, mật khẩu hoặc mã dự phòng không được tự chuyển chữ thường theo chính sách username.

Một định dạng mã có thể được thiết kế riêng để chấp nhận nhiều cách nhập. Khi đó, quy tắc thuộc chính định dạng mã và phải được định nghĩa ngay từ lúc phát hành, không được mượn từ hàm tạo khóa username.

Không áp quy tắc chuỗi username lên credential ID hoặc dữ liệu khóa của passkey. Dữ liệu xác thực cần giữ đúng kiểu dữ liệu và cách mã hóa mà giao thức quy định.

Sau khi tìm đúng tài khoản, các yêu cầu còn lại về mật khẩu, MFA, token dùng một lần, xác minh danh tính và session vẫn phải được thực thi. Kết quả tra cứu không được tự tạo phiên đăng nhập hoặc thu hồi phiên của chủ tài khoản.

## 10. Chống dò tài khoản và chống lạm dụng

Những cách viết hoa/thường tương đương phải được xem xét cùng nhau trong kiểm soát lạm dụng. Nếu mỗi biến thể được tính như một đích riêng, đối thủ có thể thay đổi cách viết để vượt giới hạn.

~~~text
minh.an
Minh.An
MINH.AN
mInH.aN

Nếu cùng một khóa đăng nhập:
cần cùng được tính vào giới hạn phù hợp cho đích đó.
~~~

Tuy nhiên, giới hạn theo khóa định danh không đủ. Hệ thống còn cần các chiều phù hợp như nguồn gửi, đích nhận thông báo, giao dịch và hành vi bất thường, vì một đối thủ có thể dùng nhiều định danh hoặc nhiều nguồn.

Các bộ đếm cũng không được làm lộ sự tồn tại của tài khoản:

- Tránh chỉ tạo phản hồi giới hạn đặc biệt cho username có thật.
- Áp dụng chính sách công khai nhất quán với các đầu vào tương đương.
- Không trả “đã sửa đúng chữ hoa/thường của tài khoản” trước xác minh.
- Không tiết lộ tên hiển thị, kênh khôi phục hoặc trạng thái MFA qua kết quả tra cứu.
- Kiểm soát các API gửi lại, kiểm tra trạng thái và bước hỗ trợ, không chỉ biểu mẫu đầu tiên.

Một phản hồi chung có thể là:

> Nếu thông tin phù hợp với tài khoản và đường khôi phục được hỗ trợ, hướng dẫn sẽ được gửi.

Câu chữ giống nhau chưa đủ nếu thời gian, mã HTTP, chuyển trang hoặc API phụ vẫn khác theo kết quả. Cần xem xét toàn bộ hành vi có thể quan sát.

### Định danh trong log và bộ đếm

Có thể cần ghi loại định danh, phiên bản quy tắc, kết quả nội bộ và mã sự kiện. Không nhất thiết phải ghi toàn bộ username, email hoặc khóa tra cứu ở mọi tầng.

Nếu dùng một khóa dẫn xuất để giảm việc lưu định danh thô trong bộ đếm, cần xác định rõ mục đích, phạm vi và cách bảo vệ. Băm thông thường một username dễ đoán không tự làm dữ liệu trở thành vô danh.

Cũng không nên ghi cả token hay liên kết khôi phục để “dễ kiểm tra”. Những dữ liệu đó có quyền riêng và có thể tạo đường tiếp quản tài khoản nếu bị lộ.

Yêu cầu chưa xác minh không nên tự khóa tài khoản hoặc thu hồi mọi session. Một người biết các biến thể username không được có khả năng gây mất quyền truy cập chỉ bằng việc gửi yêu cầu khôi phục liên tục.

## 11. Các tình huống thiết kế

### Tình huống A: Người dùng nhập khác cách viết hoa

Minh đăng ký “Minh.An”. Chính sách username của sản phẩm là ASCII không phân biệt hoa/thường.

Khi Minh nhập “MINH.AN”, hệ thống tạo cùng khóa “minh.an”, tìm tài khoản trong đúng phạm vi rồi xử lý bằng chứng khôi phục. Phần công khai không xác nhận tên hiển thị chuẩn trước khi Minh đủ điều kiện biết.

**Điểm quyết định:** sự tương đương đã có từ chính sách cấp phát định danh, không phải một ngoại lệ được thêm riêng để biểu mẫu khôi phục dễ tìm thấy người dùng.

### Tình huống B: Hai tài khoản cũ khác nhau theo chữ hoa/thường

Một hệ thống cũ có “Lan” và “lan” thuộc hai tài khoản. Đội phát triển muốn đổi toàn bộ đường khôi phục sang chữ thường.

Tính khóa mới cho thấy cả hai cùng thành “lan”. Hệ thống phải giải quyết xung đột theo kế hoạch chuyển đổi; không được tự chọn tài khoản theo kết quả truy vấn.

**Điểm quyết định:** khi chưa xác định được đích duy nhất, dừng cấp quyền cho yêu cầu mơ hồ và hướng người dùng tới đường hỗ trợ phù hợp mà không công khai chi tiết của tài khoản khác.

### Tình huống C: Máy chủ có locale khác nhau

Một dịch vụ dùng locale mặc định để tạo khóa, còn dịch vụ khác dùng quy tắc cố định. Cùng một định danh có thể được hiểu khác nhau giữa đăng ký và khôi phục.

Cách xử lý là đưa chúng về cùng hợp đồng và xử lý dữ liệu chịu ảnh hưởng. Không thử thêm mọi biến thể locale cho đến khi truy vấn có kết quả.

**Điểm quyết định:** môi trường chạy không được tự thay đổi quan hệ giữa tên và chủ tài khoản.

### Tình huống D: Username đổi khi giao dịch đang chờ

An bắt đầu khôi phục, sau đó username cũ được đổi hoặc được cấp lại theo chính sách sản phẩm.

Giao dịch vẫn giữ account_id của An. Tại bước tiếp tục, máy chủ kiểm tra thời hạn, trạng thái, mục đích và điều kiện hiện tại, không chuyển sang tài khoản mới đang dùng tên cũ.

**Điểm quyết định:** khóa so sánh giúp tìm đích ban đầu; nó không thay thế định danh tài khoản ổn định trong suốt giao dịch.

## 12. Ma trận kiểm tra khi đặc tả

Những tình huống dưới đây giúp kiểm tra thiết kế trước khi triển khai. Kết quả cần được điều chỉnh theo chính sách định danh thật của sản phẩm.

| Tình huống | Kết quả cần xác định |
| --- | --- |
| Cùng username ASCII với nhiều cách viết hoa | Cùng khóa nếu chính sách không phân biệt hoa/thường |
| Hai username chỉ khác dấu chấm | Không gộp nếu chính sách chỉ folding chữ hoa/thường |
| Đầu vào có khoảng trắng cuối | Từ chối hoặc xử lý đúng hợp đồng; không tự đoán |
| Cùng đầu vào trên các máy chủ có locale khác nhau | Cùng khóa theo chính sách đã chọn |
| Đầu vào Unicode trong chính sách ASCII | Từ chối định dạng, không tự bỏ dấu |
| Các cặp Unicode mà quy tắc full folding coi tương đương | Cùng khóa; phát hiện xung đột cấp phát |
| Chuỗi có dạng dựng sẵn và dạng dấu kết hợp | Đúng kết quả theo chính sách chuẩn hóa đã công bố |
| Khóa sau biến đổi dài hơn dự kiến | Xử lý theo giới hạn; không cắt ngắn để tra cứu |
| Cùng khóa trong hai tenant | Tra cứu trong đúng tenant, giữ hai chủ thể riêng |
| Ứng dụng và collation có quan hệ so sánh khác nhau | Phát hiện và sửa sự không nhất quán trước khi cấp quyền |
| Hai tài khoản cùng khóa hiện hành | Không chọn bản ghi đầu; xử lý mơ hồ nội bộ |
| Thay đổi quy tắc trong khi còn giao dịch khôi phục | Không đổi chủ tài khoản của giao dịch |
| Biến thể hoa/thường của cùng đích được gửi liên tục | Được tính vào kiểm soát lạm dụng phù hợp |
| Token chỉ khác hoa/thường | So sánh theo hợp đồng token, không theo username |
| Username không tồn tại hoặc không đủ điều kiện | Không làm lộ khác biệt ngoài phạm vi công khai cho phép |

Trước khi chấp nhận thiết kế, cần chỉ ra được nguồn chính sách, khóa tra cứu, phạm vi tính duy nhất và tài khoản mà mỗi giao dịch sẽ giữ cố định. Nếu một thành phần tự thêm quan hệ tương đương, hoặc một kết quả có thể chọn giữa hai tài khoản, luồng khôi phục chưa có căn cứ đáng tin cậy để cấp quyền.

Case folding an toàn bắt đầu từ một hợp đồng định danh nhất quán. Hợp đồng đó giúp hệ thống tìm đúng tài khoản; còn bằng chứng xác thực, token dùng một lần và kiểm soát session quyết định người yêu cầu được phép làm gì tiếp theo.
