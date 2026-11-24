# Coupon brute force defense — Chống dò mã coupon

Trong chương **Coupons**, brute force là việc tự động thử nhiều mã để tìm một mã tồn tại, còn giá trị hoặc có thể dùng cho một giao dịch. Mỗi request có thể đúng cú pháp và đi qua API hợp lệ, nhưng chuỗi request lại làm lộ quyền lợi hoặc tiêu hao ngân sách trái chính sách.

Bảo vệ bài toán này cần nhiều lớp: mã bí mật khó đoán, giới hạn số lần thử, phản hồi không trở thành công cụ xác nhận mã, kiểm tra quyền trên đối tượng và redeem nguyên tử. CAPTCHA hoặc một bộ đếm theo IP riêng lẻ không bảo vệ đầy đủ các bất biến nghiệp vụ.

Bài học sử dụng các chính sách và số liệu giả định để minh họa. Độ dài mã, hạn mức và cách xử lý lỗi phải được chọn theo giá trị ưu đãi, thời hạn tồn tại, tập người được nhận và tải hợp lệ của hệ thống.

Sau bài học, bạn cần có khả năng:

- Phân biệt coupon công khai, coupon bí mật và quyền hưởng ưu đãi được gắn với tài khoản.
- Ước lượng rủi ro dò trúng một mã trong tập mã đang hoạt động.
- Thiết kế giới hạn lượt thử có hiệu lực trên nhiều phiên, tài khoản, API và instance.
- Ngăn phản hồi lỗi, timing và endpoint phụ làm lộ mã hợp lệ.
- Kết hợp chống dò với transaction, state machine và idempotency khi dùng mã.
- Xây dựng tình huống kiểm thử và tín hiệu vận hành cho hành vi dò phân tán.

## 1. Mã nào cần bí mật, quyền nào phải được kiểm tra?

Không phải mọi coupon đều nên khó đoán.

| Loại | Ví dụ ý nghĩa | Ranh giới bảo vệ chính |
| --- | --- | --- |
| Mã chiến dịch công khai | SUMMER10 được quảng bá cho mọi khách đủ điều kiện | Điều kiện, giới hạn theo khách, ngân sách và chống dùng trùng |
| Mã riêng gắn với người nhận | Mã hỗ trợ chỉ tài khoản A được sử dụng | Bí mật của mã kết hợp với quyền của A |
| Mã bearer được phép chuyển nhượng | Ai sở hữu mã hợp lệ có thể dùng theo chính sách | Độ khó đoán, bảo vệ kênh phát, hạn dùng và redeem một lần |
| Mã tham chiếu nội bộ | couponId để nhân viên tra cứu | Quyền truy cập đối tượng; ID không được tự biến thành quyền nhận giảm giá |

Mã công khai không có giá trị bảo mật từ tính khó đoán: người dùng vốn được phép biết nó. Nếu chiến dịch chỉ dành cho khách mới, hệ thống vẫn phải xác minh điều kiện đó trên máy chủ.

Với mã riêng gắn tài khoản, biết mã chưa đủ để sử dụng. Bản ghi quyền phải xác nhận đúng người nhận và tenant. Không coi couponId khó đoán hoặc chuỗi mã bí mật là vật thay thế cho kiểm tra quyền.

Với mã bearer thực sự, việc lộ chuỗi mã có thể làm lộ luôn quyền dùng. Cần thiết kế vòng đời và mức bảo vệ tương ứng. Không áp dụng máy móc mô hình coupon cho gift card hoặc số dư tiền nếu các đối tượng đó có quy tắc tài chính và chuyển nhượng khác.

OWASP WSTG đặt ra các kiểm tra cụ thể cho mã giảm giá: mã có dễ đoán không, có thể tìm thêm mã bằng cách tăng số không và có cơ chế chống brute force không. [OWASP WSTG — Payment Functionality](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/10-Business_Logic/10-Payment_Functionality/).

## 2. Kẻ dò mã có thể khai thác những bề mặt nào?

Một hệ thống thường có nhiều đường kiểm tra cùng một quyền coupon:

~~~text
POST /coupon-checks
POST /carts/{id}/coupons
POST /checkout
POST /mobile/coupon-preview
GraphQL query hoặc mutation
API hỗ trợ khách hàng
API kiểm tra mã từ đối tác
~~~

Chỉ giới hạn endpoint đầu tiên không ngăn việc chuyển sang endpoint khác.

Cần xem xét:

- **Dò nhanh:** nhiều mã khác nhau trong thời gian ngắn.
- **Dò chậm, phân tán:** nhiều tài khoản hoặc nguồn mạng, mỗi nguồn chỉ thử một ít.
- **Một request, nhiều phép thử:** mảng couponCodes, GraphQL alias hoặc endpoint batch.
- **Oracle phản hồi:** mã không tồn tại, mã hết hạn và mã của người khác trả lỗi khác nhau.
- **Oracle từ giá:** tổng tiền thay đổi dù thông báo chung vẫn nói mã không hợp lệ.
- **Đường vòng bằng ID:** endpoint nhận couponId mà bỏ qua kiểm tra chuỗi mã hoặc quyền người nhận.
- **Lộ qua vận hành:** log, analytics, URL, lỗi debug, file xuất hoặc công cụ hỗ trợ.
- **Đốt tài nguyên:** ép tra cứu cơ sở dữ liệu, gọi dịch vụ đánh giá rủi ro hoặc tạo quá nhiều khóa limiter.

Cũng cần phân biệt hai vấn đề:

~~~text
Dò trúng mã:
  Tìm được một chuỗi có ý nghĩa hoặc có thể sử dụng.

Dùng mã trái giới hạn:
  Đã biết mã nhưng dùng sai người, nhiều lần hoặc vượt ngân sách.
~~~

Mã có entropy cao chống được việc đoán ngẫu nhiên nhưng không ngăn mã bị chia sẻ. Rate limit giảm số phép thử nhưng không tự bảo vệ quyền dùng một lần khi hai request chạy đồng thời.

## 3. Tính rủi ro theo không gian mã và số mã còn dùng được

### 3.1. Độ dài nhìn thấy không phải entropy

Nếu phần bí mật có L ký tự được chọn độc lập, đồng đều từ bảng chữ cái A ký tự:

~~~text
N = A^L
H = L × log2(A) bit
~~~

Trong đó N là số chuỗi có thể có, H là entropy lý tưởng.

| Phần thực sự ngẫu nhiên | Không gian | Entropy lý tưởng |
| --- | --- | ---: |
| 8 chữ số | 10^8 | Khoảng 26,6 bit |
| 10 chữ số | 10^10 | Khoảng 33,2 bit |
| 16 ký tự từ bảng 32 ký tự | 32^16 | 80 bit |
| 20 ký tự từ bảng 32 ký tự | 32^20 | 100 bit |

Các ký tự cố định, như tiền tố VIP- hoặc tên chiến dịch, không làm tăng entropy. Ký tự kiểm tra được suy ra từ phần còn lại cũng không tạo thêm bí mật.

Nếu mã được tạo từ ID tăng dần, timestamp hoặc một PRNG có seed dự đoán được, không thể dùng công thức entropy lý tưởng của một chuỗi ngẫu nhiên để khẳng định an toàn.

### 3.2. Dò “bất kỳ mã nào” khác dò một mã cụ thể

Đặt:

- N: số chuỗi có thể có.
- M: số mã có thể tạo kết quả hữu ích cho người dò trong phạm vi đang xét.
- q: số phép thử thực sự đến được bước kiểm tra trong thời gian mã có hiệu lực.

Với các lần đoán ngẫu nhiên độc lập, cho phép lặp:

~~~text
P(tìm được ít nhất một mã hữu ích)
  = 1 - (1 - M/N)^q

Khi M × q / N rất nhỏ:
  P xấp xỉ M × q / N
~~~

Đây là mô hình tính toán đơn giản, không bao gồm mã bị lộ, dự đoán được hoặc thông tin phụ từ phản hồi. Với tập phép thử không lặp, công thức chính xác khác nhưng vẫn phải tính đến số mã mục tiêu M.

Ví dụ, có 100.000 mã hữu ích nằm trong không gian 8 chữ số:

~~~text
N = 100.000.000
M = 100.000
q = 1.000

P = 1 - (1 - 0,001)^1.000
  ≈ 63,2%
~~~

Một nghìn lần thử không cần tìm đúng một người nhận cụ thể; chỉ cần trúng bất kỳ mã có giá trị nào. Đây là lý do một không gian tưởng lớn vẫn có thể rủi ro nếu phát rất nhiều mã ngắn.

Nếu thay bằng 20 ký tự đồng đều từ bảng 32 ký tự:

~~~text
N = 2^100 ≈ 1,27 × 10^30
M = 100.000
q = 1.000.000

P xấp xỉ 7,9 × 10^-20
~~~

Con số này chỉ mô tả rủi ro đoán ngẫu nhiên trong mô hình. Nó không chứng minh kênh phát, lưu trữ, quyền người nhận hoặc redeem đã an toàn.

### 3.3. q phải tính trên toàn bộ bề mặt truy cập

Không dùng q = “số request mỗi IP” nếu người dò có thể:

- Đổi IP.
- Tạo tài khoản mới.
- Đổi cookie hoặc session.
- Gửi batch nhiều mã.
- Chuyển sang mobile hoặc API đối tác.
- Thử liên tục trong nhiều ngày.

Nếu mã gắn đúng một người nhận, M cho khả năng redeem của tài khoản đó có thể nhỏ hơn nhiều so với tổng mã hệ thống. Tuy nhiên, endpoint vẫn có thể làm lộ sự tồn tại của mã thuộc người khác nếu phản hồi phân biệt.

Cần tách **rủi ro lộ thông tin** và **rủi ro sử dụng được lợi ích** khi đánh giá M.

## 4. Chính sách giả định dùng trong bài

Xét một chương trình giảm 100.000 đồng cho đơn có tiền hàng đủ điều kiện từ 1.000.000 đồng:

| Hạng mục | Chính sách minh họa |
| --- | --- |
| Mã riêng | 20 ký tự từ bảng 32 ký tự, sinh bằng CSPRNG |
| Người nhận | Gắn với một tài khoản đã xác thực trong đúng tenant |
| Thời hạn | Hết hạn sau 14 ngày hoặc khi bị thu hồi theo chính sách |
| Số lần dùng | Một lần cho quyền ưu đãi này |
| Tra cứu | Không có endpoint công khai kiểm tra sự tồn tại của mã riêng |
| Giới hạn tài khoản | Tối đa 6 phép kiểm tra mã mới trong bất kỳ 10 phút và 30 phép trong bất kỳ 24 giờ |
| Batch | Mỗi thao tác kiểm tra chỉ chứa một mã; các kênh khác phải cùng giới hạn về tổng số mã được xét |
| Lượt tính thử | Không giữ ngân sách và không đánh dấu đã dùng |
| Redeem | Giữ quyền, ngân sách và snapshot đơn bằng thao tác nguyên tử |
| Thông báo công khai | Các trường hợp mã không khả dụng dùng cùng nhóm phản hồi |
| Khi limiter không hoạt động | Tạm hoãn kiểm tra mã riêng theo hợp đồng; không tự mở không giới hạn |

Các số 6 và 30 chỉ để làm rõ thiết kế và kiểm thử. Chúng không phải khuyến nghị chung cho mọi website. Cần điều chỉnh bằng dữ liệu khách hợp lệ, rủi ro, giá trị mã và khả năng hỗ trợ người bị chặn nhầm.

Giới hạn theo tài khoản không đủ trước tài khoản giả hàng loạt. Cần thêm lớp bảo vệ toàn hệ thống, nguồn mạng, hành vi và quy trình tạo tài khoản, trong khi vẫn giữ kiểm tra quyền người nhận.

## 5. Sinh mã khó đoán và chuẩn hóa nhất quán

### 5.1. Ví dụ Java sinh phần bí mật

Bảng ký tự dưới loại bỏ 0, 1, I và O để giảm nhầm lẫn khi nhập. Nó còn 32 ký tự:

~~~java
import java.security.SecureRandom;

final class CouponCodeGenerator {
    private static final char[] ALPHABET =
            "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".toCharArray();

    private static final SecureRandom RNG = new SecureRandom();
    private static final int LENGTH = 20;

    static String generateCanonicalCode() {
        char[] code = new char[LENGTH];

        for (int i = 0; i < code.length; i++) {
            code[i] = ALPHABET[RNG.nextInt(ALPHABET.length)];
        }

        return new String(code);
    }
}
~~~

SecureRandom cung cấp bộ sinh ngẫu nhiên dùng cho mục đích mật mã; nextInt(bound) cho phép chọn chỉ số trong phạm vi bảng ký tự. Không tự seed bằng thời gian hoặc dùng Random để tạo bí mật. [Java SE — SecureRandom](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html), [Java SE — Random.nextInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Random.html#nextInt(int)).

Không dùng phép lấy dư trên một nguồn byte tùy ý nếu chưa chứng minh phân bố đồng đều. Không rút ngắn chuỗi sau khi mã hóa một giá trị có ít entropy rồi coi nó tương đương chuỗi 100 bit.

Khi lưu, vẫn có ràng buộc duy nhất phù hợp và xử lý trùng bằng sinh lại. Xác suất va chạm thấp không thay thế kiểm tra duy nhất.

### 5.2. Phân biệt định dạng hiển thị và giá trị chuẩn

Có thể hiển thị mã theo bốn nhóm 5 ký tự cho dễ nhập. Dấu phân cách không tính vào entropy.

Chính sách chuẩn hóa phải giống nhau ở tất cả endpoint:

1. Giới hạn kích thước đầu vào trước khi xử lý sâu.
2. Chỉ chấp nhận định dạng ASCII đã công bố.
3. Nếu cho phép chữ thường, chuyển theo quy tắc không phụ thuộc locale.
4. Chỉ bỏ khoảng trắng hoặc dấu phân cách được hợp đồng cho phép.
5. Kiểm tra đủ 20 ký tự thuộc bảng sau chuẩn hóa.
6. Dùng cùng giá trị chuẩn cho lookup, fingerprint và kiểm tra idempotency.

Không tự sửa mọi ký tự giống nhau về hình thức, bỏ ký tự Unicode lạ hoặc chấp nhận nhiều cách mã hóa mà không có quy định. Hai endpoint chuẩn hóa khác nhau có thể làm cùng một mã được đếm thành nhiều ý định hoặc được dùng qua đường không được kiểm soát.

Từ chối định dạng sai nhanh hơn định dạng đúng có thể là chấp nhận được nếu quy tắc định dạng là công khai. Điều cần tránh là làm lộ **sự tồn tại hoặc giá trị** của một mã có định dạng hợp lệ.

## 6. Lưu trữ và phân phối mà không làm lộ bí mật

### 6.1. Không mặc định cần lưu mã rõ

Với mã chỉ cần kiểm tra một chiều, có thể lưu fingerprint có khóa:

~~~text
lookupDigest = HMAC(
  K_lookup,
  encode("coupon-lookup:v1", tenantId, canonicalCode)
)
~~~

encode phải có cấu trúc không mơ hồ, chẳng hạn mã hóa các trường với độ dài. Không nối chuỗi tùy ý rồi để hai bộ trường khác nhau tạo cùng một thông điệp.

Bản ghi có thể gồm:

~~~text
couponId
tenantId
lookupKeyId
lookupDigest
recipientId
campaignId
benefitEntitlementId
issuedAt
expiresAt
state
reservationId
redeemedOrderId
~~~

Khóa HMAC được bảo vệ tách khỏi cơ sở dữ liệu coupon. Thiết kế này giúp giảm khả năng kiểm tra ứng viên offline khi chỉ bản dump dữ liệu bị lộ mà khóa vẫn được bảo vệ.

Không khẳng định HMAC sửa được mã yếu khi tấn công online. Endpoint vẫn là nơi kiểm tra ứng viên nếu không có các lớp phòng thủ khác. Nếu cả khóa và dữ liệu đều bị lộ, cần đánh giá sự cố theo phạm vi thực tế.

Nếu cần gửi lại mã rõ cho người nhận, phải thiết kế lưu trữ mã hóa và quyền truy cập riêng. Không dùng cùng một khóa cho lookup, mã hóa và log.

### 6.2. Khóa lookup và tenant là một phần phạm vi

Lookup phải ràng buộc đúng tenant và kiểm tra người nhận từ dữ liệu máy chủ. Không cho phép người dùng thay tenantId trong body để dò tenant khác.

Nếu hỗ trợ chuyển khóa, giới hạn số phiên bản khóa đang được kiểm tra và xác định kế hoạch di chuyển hoặc cấp lại mã. Không thử không giới hạn các khóa cũ trên mỗi request.

Việc đổi khóa lưu trữ không tự làm mã đã bị lộ trở nên bí mật trở lại. Khi chuỗi mã rõ đã bị lộ, có thể phải thu hồi và phát mã mới theo chính sách, đồng thời giữ đúng lịch sử redeem.

### 6.3. Ngăn lộ qua kênh phụ

- Gửi mã trong body qua kết nối được bảo vệ, tránh đưa mã riêng vào URL truy vấn có thể đi vào lịch sử và log.
- Không gửi mã nguyên văn tới analytics hoặc công cụ ghi phiên người dùng.
- Không trả danh sách mã theo prefix cho người không có quyền.
- Không nhúng mã riêng của nhiều khách trong HTML hoặc dữ liệu client.
- Công cụ hỗ trợ chỉ hiển thị phần cần thiết; mở toàn bộ mã phải có quyền và audit nếu nghiệp vụ cho phép.
- Endpoint phát hoặc gửi lại mã cũng cần giới hạn và kiểm tra quyền để tránh lộ hoặc gây spam.

Mã ngẫu nhiên mạnh không giúp được nếu cả lô mã bị xuất ra một đường tra cứu công khai.

## 7. Không biến phản hồi thành công cụ xác nhận mã

### 7.1. Các phản hồi khác nhau có thể tiết lộ từng bước

Một API dễ bị dò có thể trả:

~~~text
NOT_FOUND          → chuỗi này không tồn tại
EXPIRED            → mã có tồn tại nhưng hết hạn
ALREADY_USED       → mã có tồn tại và từng có giá trị
WRONG_CUSTOMER     → mã có tồn tại nhưng thuộc người khác
MIN_SPEND_NOT_MET  → mã có thể dùng nếu tăng giỏ
~~~

Các lý do rất hữu ích cho điều tra nội bộ nhưng không phải lúc nào cũng nên trả cho người chưa chứng minh quyền với mã.

Với mã riêng, chính sách ví dụ dùng cùng một nhóm lỗi công khai cho mã không tồn tại, hết hạn, đã dùng, bị thu hồi hoặc thuộc người khác:

~~~http
HTTP/1.1 422 Unprocessable Content
Cache-Control: no-store
Content-Type: application/json

{
  "code": "COUPON_UNAVAILABLE",
  "message": "Không thể áp dụng mã này cho giao dịch hiện tại."
}
~~~

Mã HTTP 422 ở đây là một lựa chọn hợp đồng API. Điểm bảo mật là các nhánh từ chối không trở thành các loại bằng chứng khác nhau về mã, không phải bắt buộc mọi hệ thống chọn cùng một status.

Có thể giải thích điều kiện chi tiết cho chủ sở hữu sau khi đã kiểm tra đúng quyền và chính sách cho phép. Ví dụ, tài khoản đã được cấp mã có thể được xem ngưỡng tối thiểu của chính mã đó. Không mở cùng mức chi tiết cho tài khoản bất kỳ chỉ vì họ nhập được một chuỗi.

### 7.2. Kiểm tra mọi dữ liệu trả về, không chỉ câu thông báo

Dù message giống nhau, các trường sau vẫn có thể tạo oracle:

- couponId hoặc campaignId chỉ xuất hiện khi mã tồn tại.
- Giá trị giảm, ngày hết hạn hoặc tên người nhận.
- Tổng tiền hoặc dòng phí thay đổi ở một nhánh bị từ chối.
- Header, status code, kích thước body và dữ liệu debug.
- Một endpoint khác trả “mã đã dùng” thay vì lỗi chung.
- GraphQL trả lỗi với đường dẫn hoặc kiểu dữ liệu khác nhau.

Không trả nguyên chuỗi mã trong thông báo lỗi. Không đặt kết quả kiểm tra mã riêng vào cache dùng chung mà thiếu phân vùng theo quyền, tenant và ngữ cảnh giao dịch.

### 7.3. Timing cần được đánh giá theo đường xử lý

Nếu mã không tồn tại trả ngay nhưng mã tồn tại gọi nhiều dịch vụ khác trước khi trả lỗi, người dò có thể thu được tín hiệu thời gian dù message giống nhau.

Nên:

- Dùng đường tra cứu có cấu trúc tương tự cho các mã đúng định dạng.
- Gộp kiểm tra người nhận và phạm vi vào thiết kế lookup hoặc xử lý từ chối.
- Tránh trả sớm các lý do chi tiết trước khi kiểm tra quyền.
- Không đưa thời gian xử lý nội bộ hoặc cache hit vào phản hồi công khai.
- Đo phân bố latency của các nhóm từ chối trong môi trường kiểm thử.

Không hứa “thời gian hoàn toàn bằng nhau” trên mạng. Thêm một sleep cố định không bảo đảm chống timing và có thể giữ tài nguyên lâu hơn khi bị tấn công. So sánh mật mã đúng cách cũng không làm toàn bộ đường HTTP trở thành constant time.

## 8. Thiết kế giới hạn lượt thử theo nhiều chiều

### 8.1. Xác định đơn vị được tính

Cần phân biệt:

| Loại ngân sách | Đơn vị tính | Mục tiêu |
| --- | --- | --- |
| Request admission | Request hoặc chi phí xử lý | Chặn flood, kể cả retry và payload sai |
| Candidate lookup | Mỗi thao tác kiểm tra mã mới được chấp nhận | Giới hạn số cơ hội dò mã |
| Risk signals | Số lần lỗi, số mã khác nhau, hành vi phân tán | Quyết định tăng kiểm soát hoặc điều tra |
| Redemption quota | Số quyền được giữ hoặc tiêu thụ | Bảo vệ giới hạn nghiệp vụ và ngân sách |

Trong chính sách bài học, “một phép kiểm tra mới” là một thao tác mới có thể tra cứu mã. Không cần tạo một tập vô hạn chứa tất cả mã từng thử để đếm số mã duy nhất.

Một retry được máy chủ nhận diện chắc chắn bằng cùng key và payload có thể trả kết quả đã lưu mà không thực hiện lookup mới. Nó vẫn chịu giới hạn request để không bị dùng làm cách tiêu hao CPU hoặc đọc dữ liệu không giới hạn.

Cùng mã nhưng gửi bằng một thao tác mới có thể vẫn bị tính một lượt kiểm tra. Không cho client tự tuyên bố isRetry = true để được miễn đếm.

### 8.2. Các chiều cần phối hợp

| Chiều | Giá trị | Hạn chế cần nhớ |
| --- | --- | --- |
| Tài khoản đã xác thực | Khó reset chỉ bằng xóa cookie | Có thể bị vượt qua bằng tài khoản giả hàng loạt |
| Session | Kiểm soát luồng ngắn hạn | Có thể tạo lại, không phải danh tính bền vững |
| IP hoặc nguồn mạng | Bảo vệ hạ tầng và phát hiện bất thường | NAT dùng chung; người dò có thể phân tán |
| Thiết bị hoặc tín hiệu hành vi | Hỗ trợ đánh giá rủi ro | Có thể thay đổi hoặc giả mạo; không dùng như bằng chứng duy nhất |
| Tenant và nhóm thao tác | Giới hạn tổng lưu lượng liên quan mã | Cần dung lượng phù hợp để không gây chặn nhầm diện rộng |
| Chương trình trong ngữ cảnh hợp lệ | Bảo vệ ngân sách kiểm tra của một chiến dịch | Không được dựa vào thông tin tồn tại của mã để tạo oracle |
| Toàn dịch vụ | Bảo vệ tài nguyên dùng chung | Không thay thế kiểm soát theo người gọi |

Ngữ cảnh campaign dùng trước lookup phải là dữ liệu đã biết hợp lệ từ luồng máy chủ, không phải một campaignId tùy ý để người gọi chọn bucket rỗng. Nếu chưa biết mã thuộc campaign nào, vẫn phải áp các giới hạn sẵn có như account, tenant và loại thao tác trước khi tra cứu.

Không hard lock một coupon chỉ vì nhiều người lạ thử nó. Nếu người dò có thể làm khóa mã của người khác, cơ chế chống dò trở thành công cụ từ chối dịch vụ.

### 8.3. Giới hạn theo IP cần nguồn tin cậy

Nếu ứng dụng đứng sau reverse proxy, chỉ lấy thông tin IP chuyển tiếp từ chuỗi proxy đã cấu hình tin cậy. Không dùng trực tiếp một X-Forwarded-For tự khai báo làm danh tính limiter.

Không khóa mọi khách chung một IP chỉ vì vài lần nhập sai. Có thể kết hợp ngưỡng request để bảo vệ tài nguyên với tín hiệu rủi ro, challenge hoặc cooldown theo tài khoản.

Các quyết định dựa vào thiết bị, vùng mạng hoặc hành vi cần được đánh giá về chặn nhầm. Chúng là tín hiệu hỗ trợ, không phải quyền hưởng coupon.

### 8.4. Đếm trước lookup và không reset tùy kết quả

Lookup permit phải được cấp trước khi tra cứu mã. Nếu chỉ tăng counter sau khi biết mã sai:

- Nhiều request song song có thể cùng vượt giới hạn.
- Mã đúng có thể tạo tín hiệu khác thông qua số lượt còn lại.
- Nhánh lỗi hoặc timeout có thể bị dùng để không bị đếm.
- Người dò có thể tận dụng endpoint phân loại khác để tránh counter thất bại.

Chính sách ví dụ tính mọi lookup mới được chấp nhận, dù kết quả là hợp lệ hay không khả dụng. Counter lỗi riêng có thể dùng cho risk scoring nhưng không thay thế hard budget.

Không tự đưa counter về 0 khi gặp một mã đúng. Nếu mã công khai có thể dùng để reset thất bại, người dò sẽ xen nó vào giữa các phép thử.

## 9. Limiter phải đúng khi nhiều instance cùng chạy

### 9.1. Bộ đếm đọc rồi ghi có thể mất tác dụng

~~~text
Request A đọc used = 5, limit = 6
Request B đọc used = 5, limit = 6
A được cho qua và ghi 6
B được cho qua và ghi 6
~~~

Thực tế đã có hai lượt mới dù chỉ còn một lượt.

Việc kiểm tra và tiêu thụ permit cần nguyên tử trong kho trạng thái dùng chung hoặc một cơ chế tương đương được chứng minh. Chỉ có counter trong bộ nhớ mỗi instance có thể làm giới hạn tăng theo số instance hoặc bị reset khi deploy.

### 9.2. Chọn thuật toán có đúng ý nghĩa của chính sách

Chính sách “6 lượt trong bất kỳ 10 phút” khác với token bucket có sức chứa 6 và liên tục nạp lại:

- Fixed window đơn giản có thể cho burst ở hai bên ranh giới.
- Sliding window chính xác có thể biểu diễn trực tiếp giới hạn trong mọi khoảng 10 phút.
- Token bucket mô tả tốc độ và burst, không tự đồng nghĩa giới hạn rolling window nói trên.

Ví dụ này chọn rolling window chính xác. Các mốc dùng đồng hồ có thẩm quyền của cơ chế limiter, không tin timestamp trong request.

Giả mã hợp đồng:

~~~text
tryAdmitLookup(account, tenant, operation, authoritativeNow):
    thực hiện nguyên tử trong phạm vi các quota cần bảo vệ

    loại các lượt đã nằm ngoài từng rolling window
    kiểm tra quota 10 phút và 24 giờ của tài khoản
    kiểm tra các quota bắt buộc khác

    nếu một quota đã hết:
        trả DENY và thời điểm được thử lại phù hợp

    ghi một lượt tiêu thụ vào các quota áp dụng
    trả ALLOW
~~~

Nếu các quota nằm ở nhiều kho dữ liệu và không thể cập nhật nguyên tử cùng nhau, cần thiết kế cách phối hợp và giới hạn độ vượt cho phép. Tiêu thụ bảo thủ một số token rồi từ chối có thể gây chặn sớm; không được coi việc từng kho đúng riêng lẻ là bằng chứng tổng thể không thể vượt giới hạn.

Không tự hoàn permit sau mọi lỗi cơ sở dữ liệu. Việc hoàn token thiếu kiểm soát có thể tạo đường không bị tính lượt. Cần hợp đồng retry và tính chi phí rõ ràng.

### 9.3. Hạn chế cardinality và tài nguyên

Không tạo một limiter key sống lâu cho mọi chuỗi coupon do người lạ gửi. HMAC chuỗi đó chỉ che nội dung, không giảm số lượng key.

Nên có:

- Kích thước body, số trường và số mã tối đa.
- Giới hạn request trước các bước tạo trạng thái tốn kém.
- Bucket chủ yếu theo danh tính hoặc phạm vi có kiểm soát.
- TTL cho counter, challenge và idempotency record.
- Giới hạn số key hoặc bản ghi có thể tạo theo người gọi.
- Cơ chế quan sát và xử lý khi kho limiter gần đầy.

Cũng không gắn mã hoặc fingerprint riêng lẻ làm label của hệ thống metric có cardinality không giới hạn.

### 9.4. Quy định chế độ suy giảm

Với mã riêng có giá trị, chính sách ví dụ tạm hoãn lookup khi không kiểm tra được quota có thẩm quyền. Các chức năng giỏ hàng không cần mã có thể tiếp tục theo hợp đồng của chúng.

Không chuyển sang “mỗi instance cho thử 6 lần” mà vẫn tuyên bố giữ đúng giới hạn toàn hệ thống. Nếu có fallback cục bộ, phải mô tả giới hạn thực tế, thời gian áp dụng và điều kiện chuyển chế độ.

Phản hồi quá tải hạ tầng không nhất thiết là 429: cần phân biệt người gọi đã hết quota với hệ thống tạm thời không phục vụ được. Không dùng lỗi này để báo rằng một mã chắc chắn sai.

## 10. Pipeline kiểm tra mã có kiểm soát

~~~mermaid
flowchart TD
    A[Request] --> B[Giới hạn request và kích thước payload]
    B --> C[Xác thực và kiểm tra quyền trên giỏ]
    C --> D[Kiểm tra định dạng và chuẩn hóa một mã]
    D --> E[Nhận diện retry theo key và payload]
    E --> F{Có kết quả đã lưu hợp lệ?}
    F -->|Có| G[Trả kết quả đúng quyền]
    F -->|Không| H[Đánh giá rủi ro và challenge nếu cần]
    H --> I[Cấp lookup permit nguyên tử]
    I --> J{Được phép?}
    J -->|Không| K[Từ chối trước tra cứu mã]
    J -->|Có| L[Lookup có phạm vi tenant và người nhận]
    L --> M[Kiểm tra hiệu lực và điều kiện giao dịch]
    M --> N[Lưu kết quả tính thử và trace nội bộ]
    N --> O[Trả phản hồi theo hợp đồng]
~~~

Các điểm cần giữ:

1. Kiểm tra quyền với giỏ trước khi trả kết quả tính giá.
2. Không nhận customerId, role hoặc isVip từ client làm nguồn có thẩm quyền.
3. Không lookup mỗi phần tử của một batch rồi chỉ tính một request.
4. Mọi endpoint nhận một chuỗi mã mới đều đi qua cùng chính sách admission.
5. Các lỗi nội bộ được ghi đủ để điều tra nhưng không trả thông tin tồn tại của mã riêng.
6. Tính thử không tiêu thụ coupon hoặc giữ ngân sách.
7. Khi chốt đơn, kiểm tra lại các điều kiện có thể đã thay đổi.

### 10.1. Idempotency không phải vé miễn giới hạn

Request kiểm tra có thể gửi:

~~~http
POST /carts/cart-42/coupon-checks
Idempotency-Key: coupon-check-42
Content-Type: application/json

{
  "expectedCartVersion": 7,
  "couponCode": "<mã riêng người dùng nhập>"
}
~~~

Payload fingerprint do máy chủ tính cần ràng buộc ít nhất với:

~~~text
tenant
actor
loại thao tác
cartId và cartVersion
fingerprint của mã chuẩn
các đầu vào ảnh hưởng điều kiện kiểm tra
~~~

Cùng key nhưng đổi mã hoặc giỏ phải bị từ chối xung đột trước lookup, không được coi là retry được miễn quota.

Cùng key và payload đã hoàn tất có thể trả kết quả đã lưu sau kiểm tra quyền. Tuy nhiên, một kết quả tính thử được lưu không chứng minh mã còn hiệu lực ở thời điểm commit. Checkout vẫn phải xác minh trạng thái và phiên bản cần thiết.

Nếu request đang xử lý, không cho một request lặp chạy song song nhánh lookup thứ hai một cách tùy ý. Hợp đồng có thể trả trạng thái đang xử lý hoặc chờ kết quả trong giới hạn tài nguyên.

### 10.2. Phản hồi hết quota

Một ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 120
Cache-Control: no-store
Content-Type: application/json

{
  "code": "COUPON_CHECK_LIMIT_REACHED",
  "message": "Bạn đã kiểm tra mã quá nhiều lần. Vui lòng thử lại sau."
}
~~~

RFC 6585 định nghĩa 429 cho trường hợp quá nhiều request trong một khoảng thời gian và cho phép dùng Retry-After. Chuẩn không tự chọn danh tính hay thuật toán đếm thay cho ứng dụng. [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Giá trị Retry-After cần phù hợp chính sách và trạng thái quota. Không trả số giây dựa vào việc mã có tồn tại hay không, vì quyết định giới hạn phải xảy ra trước lookup.

### 10.3. Đường checkout không được là cửa sau

Nếu checkout nhận mã mới trực tiếp, nó phải đi qua cùng kiểm soát lookup. Nếu dùng kết quả đã xác thực trước đó, nó phải tham chiếu dữ liệu hoặc capability máy chủ có phạm vi và quyền rõ ràng.

Không cho phép:

~~~text
/coupon-checks yêu cầu chuỗi mã và có limiter
nhưng
/checkout chỉ cần couponId bất kỳ và không kiểm tra quyền
~~~

Với mã bearer, một couponId nội bộ không tự chứng minh người gọi sở hữu bí mật. Với mã gắn tài khoản, kiểm tra quyền hưởng vẫn bắt buộc dù giao diện có thể hiển thị mã từ danh sách của chính chủ.

## 11. CAPTCHA và tăng xác minh chỉ là một lớp hỗ trợ

Một challenge có thể giúp giảm tự động hóa nhưng không thay thế:

- Không gian mã đủ lớn.
- Hard budget cho phép thử.
- Quyền người nhận.
- Ngân sách chiến dịch.
- Chống dùng một lần nhiều lần.

Không tin captchaSolved = true do client gửi. Kết quả challenge phải được máy chủ xác minh theo giao thức đã tích hợp.

Nên ràng buộc challenge với mục đích kiểm tra coupon, người gọi hoặc session phù hợp, thời hạn, nonce và ngữ cảnh cần thiết. Nếu một challenge chỉ xác nhận một ý định cụ thể, không cho phép dùng kết quả đó để thử một danh sách mã khác.

Một kết quả challenge hợp lệ không reset counter hoặc mở số lookup vô hạn. Trong chính sách ví dụ, giới hạn 6 lượt trong 10 phút vẫn có hiệu lực sau khi giải challenge.

Cũng cần tránh biến challenge thành chi phí không giới hạn cho hệ thống hoặc gây khó cho người dùng hợp lệ. Lớp giới hạn request vẫn chạy trước và luồng hỗ trợ phải có kiểm tra quyền, không trở thành một API tra cứu mã không giới hạn.

## 12. Chống dò phải đi cùng redeem đúng nghiệp vụ

### 12.1. Tách kiểm tra, giữ và tiêu thụ

Một mã có thể hợp lệ khi preview nhưng bị dùng ở giao dịch khác trước khi checkout. Vì vậy:

~~~text
checkCoupon → kết quả tính thử, chưa có quyền giữ

reserveCoupon → giữ quyền dùng và ngân sách cho một giao dịch

consumeCoupon → xác nhận quyền đã đi vào giao dịch hoàn tất
~~~

Không cập nhật used = true chỉ để kiểm tra mã. Làm vậy có thể khiến người dò làm mất quyền của người nhận hợp lệ.

Ngược lại, không coi kết quả check thành công là quyền được dùng mã mãi về sau. Cần kiểm tra lại hiệu lực, quyền, trạng thái, giỏ và giới hạn ở điểm commit.

### 12.2. State machine tối thiểu

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> RESERVED: Giữ quyền và ngân sách nguyên tử
    ISSUED --> EXPIRED: Hết hạn
    ISSUED --> REVOKED: Thu hồi có thẩm quyền
    RESERVED --> REDEEMED: Giao dịch trả tiền được xác nhận
    RESERVED --> ISSUED: Giải phóng hợp lệ và mã còn hiệu lực
    RESERVED --> EXPIRED: Giải phóng hợp lệ sau khi hết hạn
    RESERVED --> REVOKED: Thu hồi theo chính sách khi đủ điều kiện
~~~

RESERVED cần dữ liệu chi tiết về payment attempt. Không giải phóng một reservation chỉ vì TTL cũ đã hết trong khi thanh toán bên ngoài chưa rõ kết quả.

Nếu chính sách không khôi phục mã sau khi hủy, không dùng cạnh RESERVED → ISSUED. Khi hoàn tiền sau REDEEMED, việc có cấp lại quyền hay không là chính sách riêng, không phải tác dụng phụ tự động của refund.

### 12.3. Transaction bảo vệ quyền dùng một lần

Một luồng chốt có thể gồm:

~~~text
BEGIN
  xác thực và kiểm tra quyền đối với giỏ/báo giá
  nhận hoặc khóa idempotency record đúng phạm vi
  kiểm tra key và payload có cùng nghĩa

  khóa coupon hoặc dùng cập nhật có điều kiện theo trạng thái
  kiểm tra đúng tenant, người nhận và quyền hưởng
  kiểm tra thời hạn, điều kiện giỏ, giới hạn dùng và chính sách cộng dồn

  giữ ngân sách chiến dịch theo khoản giảm do máy chủ tính
  chuyển ISSUED → RESERVED và gắn đúng order/reservation
  ghi snapshot đơn và giá đã xác nhận
  ghi ledger, outbox và kết quả idempotency
COMMIT
~~~

Nếu một bước thất bại, không để lại việc giữ ngân sách hoặc giữ mã riêng lẻ ngoài cam kết của transaction.

Hai request dùng key khác nhau nhưng cùng mã một lần vẫn phải có tối đa một reservation hợp lệ. Idempotency theo request không thay thế điều kiện trạng thái và ràng buộc nghiệp vụ.

Một coupon code khác có thể cùng đại diện quyền “khách mới một lần”. Khi đó giới hạn phải gắn với benefitEntitlementId và đối tượng hưởng, không chỉ với chuỗi mã.

### 12.4. Những bất biến cần giữ

- Không lookup mã mới ngoài ngân sách phép thử được chấp nhận.
- Không trả thông tin mã riêng của người khác.
- Không giữ hoặc tiêu thụ mã mà người gọi không có quyền nhận.
- Tổng khoản giảm được giữ và tiêu thụ không vượt ngân sách.
- Quyền dùng một lần không tạo hai giao dịch hưởng lợi.
- Tiền giảm lấy từ chính sách và dữ liệu máy chủ, không từ payload.
- Retry không tăng khoản giảm, lượt dùng hoặc hiệu ứng thanh toán.
- Một kết quả preview không bỏ qua kiểm tra trạng thái khi commit.

Những bất biến này bảo vệ các lớp khác nhau. Không thể lấy việc đã có limiter làm lý do bỏ transaction, hoặc lấy việc coupon có ràng buộc unique làm lý do cho phép dò mã không giới hạn.

## 13. Đặc tả kiểm thử phòng thủ

Bảng dưới là nội dung kiểm thử cần thiết cho chính sách ví dụ; không phải báo cáo một bộ test đã chạy.

| Tình huống | Cách tạo điều kiện | Kết quả cần chứng minh |
| --- | --- | --- |
| Mã đúng, đúng chủ | Tài khoản có mã còn hạn, giỏ đủ điều kiện | Được tính thử đúng giá, chưa thay đổi trạng thái đã dùng |
| Mã công khai | Người dùng biết mã chiến dịch | Vẫn kiểm tra điều kiện và quota, không dựa vào tính bí mật |
| Mã không tồn tại | Gửi chuỗi đúng định dạng nhưng không có bản ghi | Phản hồi không khả dụng và tiêu thụ một lookup permit |
| Mã của người khác | Gửi mã tồn tại nhưng khác người nhận | Cùng nhóm phản hồi công khai như mã không tồn tại; không có lợi ích |
| Mã hết hạn hoặc đã dùng | Kiểm tra các trạng thái không khả dụng | Không lộ trạng thái chi tiết cho người không có quyền |
| Payload sai hoặc quá dài | Gửi chuỗi vượt giới hạn hoặc ký tự bị cấm | Bị chặn trước lookup; vẫn chịu giới hạn request |
| Chuẩn hóa tương đương | Gửi các cách viết được hợp đồng cho phép | Cùng giá trị chuẩn và cùng nghĩa payload |
| Sáu lượt trong rolling window | Tài khoản mới, các quota khác còn, 6 lookup tại cùng thời điểm | Chấp nhận đúng 6 lượt theo giới hạn ngắn hạn |
| Lượt thứ bảy | Gửi thêm trước khi cửa sổ giải phóng | Từ chối trước tra cứu mã |
| Biên cửa sổ | Giữ đồng hồ kiểm thử ở trước và tại mốc hết cửa sổ | Tuân thủ đúng quy ước cửa sổ, không dựa thời gian client |
| Giới hạn 24 giờ | Đã dùng 30 lượt, quota 10 phút đã trống | Vẫn từ chối lookup mới do quota dài hạn |
| Đổi session hoặc cookie | Cùng account tạo phiên mới | Không reset counter tài khoản |
| Đổi IP | Cùng account chuyển nguồn mạng | Không vượt quota tài khoản |
| Giả header IP | Gửi X-Forwarded-For từ nguồn không tin cậy | Không được tự chọn bucket IP mới |
| Nhiều instance | 10 lookup mới đồng thời, counter ban đầu rỗng, đồng hồ cố định | Tổng được nhận tối đa 6; không phải 6 cho mỗi instance |
| Endpoint khác | Chuyển giữa web, mobile và checkout | Cùng ngân sách tra cứu có thẩm quyền |
| Batch hoặc GraphQL alias | Một request mang nhiều mã | Từ chối theo hợp đồng hoặc tính đủ từng lookup; không một token cho nhiều mã |
| Retry đã hoàn tất | Cùng key và payload | Trả kết quả lưu đúng quyền, không lookup thêm; vẫn chịu request limit |
| Key trùng, đổi mã | Cùng key nhưng mã chuẩn khác | Xung đột trước lookup, không miễn quota |
| Tạo nhiều key | Cùng account dùng key mới liên tục | Không vượt hard budget, không tạo trạng thái không giới hạn |
| Challenge hợp lệ | Giải challenge sau khi đã hết quota | Không reset hoặc bỏ qua hard budget |
| Challenge dùng lại sai phạm vi | Đổi người gọi, mục đích hoặc ý định ràng buộc | Không chấp nhận như bằng chứng hợp lệ |
| Kho limiter lỗi | Không thể cấp lookup permit có thẩm quyền | Không tự cho mã riêng được lookup không giới hạn |
| Redis/DB hoặc kho đếm restart | Mô phỏng mất kết nối hoặc chuyển chế độ | Thực thi đúng chính sách suy giảm đã định, không tự mở bucket mới theo instance |
| Đường vòng couponId | Gửi ID hợp lệ nhưng thiếu quyền hoặc bằng chứng cần thiết | Không nhận ưu đãi trái phạm vi |
| Redeem đồng thời | Hai checkout tranh một mã, dùng hai key khác nhau | Tối đa một reservation hợp lệ |
| Giỏ thay đổi | Đạt ngưỡng ở preview rồi xóa hàng trước commit | Không dùng kết quả cũ để nhận khoản giảm không còn hợp lệ |
| Log và analytics | Đi qua nhánh thành công, lỗi và timeout | Không có mã rõ, token hoặc khóa bí mật bị ghi ra |
| Nguồn mạng dùng chung | Nhiều khách hợp lệ sau cùng NAT | Đo chặn nhầm và kiểm tra cách xử lý theo chính sách |
| Tải dò lớn | Nhiều mã ngẫu nhiên đúng định dạng | Tài nguyên và số key bị giới hạn, không tăng vô hạn theo đầu vào |

### 13.1. Kiểm thử phản hồi và timing

Đối với các mã riêng đúng định dạng, so sánh các nhóm:

~~~text
không tồn tại
thuộc người khác
đã dùng
hết hạn
bị thu hồi
~~~

Kiểm tra status, cấu trúc JSON, header, trường phụ, thay đổi tổng tiền và đường đi qua các endpoint. Nếu correlation ID khác nhau theo request, nó không nên mã hóa trạng thái của coupon.

Với timing, lấy đủ mẫu trong điều kiện có kiểm soát và xem phân bố, không kết luận từ một cặp request. Sự khác biệt có thể đến từ cache, kết nối hoặc tải nền; cần tìm nguyên nhân thực sự trước khi tuyên bố không còn oracle.

Không thực hiện dò mã thật của người dùng để tạo dữ liệu kiểm thử. Dùng bộ coupon và tenant thử nghiệm do nhóm kiểm soát.

### 13.2. Kiểm thử thuộc tính và mô hình

Có thể kiểm tra các thuộc tính:

- Mọi endpoint nhận mã mới phải gọi điểm admission có thẩm quyền trước lookup.
- Đổi thứ tự thực thi song song không làm số permit vượt giới hạn tại thời điểm cố định.
- Thay accountId trong body không thay đổi danh tính dùng để đếm và kiểm tra quyền.
- Các cách chuẩn hóa được cho phép không tạo nghĩa payload khác nhau ngoài ý muốn.
- Một coupon bị từ chối không làm thay đổi giá hoặc quyền dùng của người khác.
- Retry và event lặp không tăng số lần redeem hoặc số tiền giảm.
- Quota kiểm tra và quota redeem không bị dùng thay thế cho nhau.

Với generator, kiểm tra độ dài, bảng ký tự, đường cấp và ràng buộc duy nhất. Việc sinh một nghìn mã không trùng không chứng minh bộ sinh đủ an toàn. Cần đánh giá nguồn ngẫu nhiên và cách sử dụng nó, không chỉ một kiểm tra thống kê đơn giản.

## 14. Quan sát hành vi dò phân tán và xử lý sự cố

### 14.1. Chỉ số cần theo dõi

| Chỉ số | Giúp phát hiện |
| --- | --- |
| Request được nhận hoặc chặn trước ứng dụng | Flood hoặc lỗi client |
| Lookup permit cho phép, từ chối, lỗi theo tenant và nhóm thao tác | Giới hạn có thực sự được thực thi |
| Tỷ lệ kết quả không khả dụng và loại lỗi nội bộ | Mẫu dò, mã phát sai hoặc lỗi tích hợp |
| Nhiều mã trên một account, session hoặc nhóm nguồn mạng | Dò nhanh |
| Nhiều account có mẫu thử giống nhau | Dò phân tán hoặc tự động hóa |
| Tỷ lệ challenge, giải thành công và chặn nhầm | Hiệu quả và chi phí tăng xác minh |
| Lookup qua từng endpoint hoặc phiên bản client | Cửa sau chưa dùng chung quota |
| Reservation và redeem vượt quy tắc | Lỗ hổng nghiệp vụ sau khi biết mã |
| Cardinality, bộ nhớ và latency của limiter | Tấn công làm đầy kho trạng thái |
| Chênh lệch giữa lookup dự kiến và thực tế | Batch, retry hoặc resolver bị đếm thiếu |

Không kết luận mọi tỷ lệ lỗi cao là tấn công. Một chiến dịch gửi sai mã, giao diện tự retry hoặc thay đổi quy tắc chuẩn hóa cũng tạo hiện tượng tương tự.

Nên quan sát cả tỷ lệ lẫn tổng số tuyệt đối. Dò chậm có thể không làm tăng đột biến trên từng tài khoản nhưng tạo tổng q lớn khi gộp nhiều nguồn và thời gian.

### 14.2. Log đủ để điều tra mà không lộ mã

Một audit event có thể gồm:

~~~text
requestId
tenantId
actorId hoặc định danh đã giảm lộ phù hợp
operationFamily
endpointVersion
limiterDecision
quotaPolicyVersion
internalOutcomeReason
cartId và cartVersion khi có quyền phù hợp
couponId chỉ sau lookup nội bộ hợp lệ
challengeDecision
latencyBucket
~~~

Nếu cần liên kết cùng chuỗi nhập qua nhiều request, có thể dùng fingerprint HMAC phục vụ quan sát với khóa riêng. Fingerprint không phải lý do để giữ vô hạn mọi chuỗi do người lạ gửi.

Không dùng mã rõ hoặc fingerprint từng mã làm label metric. Dùng tập dữ liệu điều tra có kiểm soát, lấy mẫu hoặc cấu trúc tổng hợp có giới hạn khi cần đánh giá số chuỗi khác nhau.

Quyền truy cập log và thời gian lưu cũng là một phần thiết kế. Lý do WRONG_RECIPIENT có ích nội bộ nhưng vẫn có thể làm lộ thông tin nếu công cụ hỗ trợ hoặc API log không có kiểm tra quyền.

### 14.3. Trình tự ứng phó khi nghi bị dò

1. **Xác định bề mặt:** endpoint nào cho thử, có đường batch hoặc API cũ không.
2. **Xác minh limiter:** đối chiếu số permit với số lookup thực, kiểm tra phạm vi key và các instance.
3. **Thu hẹp cửa sổ khai thác:** áp chính sách chặn hoặc tăng xác minh phù hợp, đóng oracle công khai và kiểm soát các đường vòng.
4. **Đánh giá phạm vi lộ:** phân biệt mã bị thử ngẫu nhiên, mã đã bị xác nhận và mã rõ đã rò rỉ.
5. **Kiểm tra hậu quả:** reservation, redeem, ngân sách, đơn hàng và quyền người nhận có bị vi phạm không.
6. **Thu hồi hoặc cấp lại đúng phạm vi nếu cần:** có quyền, lý do, ledger và thông báo theo quy trình vận hành.
7. **Đối soát và bổ sung tình huống tái hiện:** chứng minh đường khai thác đã được chặn.

Nhiều request dò không tự chứng minh toàn bộ mã đã lộ. Không thu hồi hàng loạt một cách mù quáng làm mất quyền lợi hợp lệ khi chưa đánh giá phạm vi.

Nếu mã rõ bị lộ qua log hoặc kênh phát, chỉ tăng rate limit hoặc đổi khóa HMAC không lấy lại tính bí mật của những mã đó. Cần xử lý nguồn lộ và chính các quyền bị ảnh hưởng.

Việc thu hồi phải giữ nguyên lịch sử giao dịch đã chốt và đi qua quy trình xử lý cam kết hiện có. Không sửa giá đơn đã trả chỉ để làm số liệu chiến dịch trông như chưa từng có sự cố.

## 15. Bài tập vận dụng

### Bài tập 1: Tính đúng không gian bí mật

Một mã dài 20 ký tự, nhưng 12 ký tự đầu là tiền tố cố định, 8 ký tự cuối là chữ số ngẫu nhiên.

Hãy trả lời:

1. Mã này có bao nhiêu bit entropy lý tưởng?
2. Nếu có 100.000 mã đang hoạt động, vì sao không thể dùng xác suất đoán một mã cụ thể để đánh giá toàn bộ hệ thống?
3. Tăng giới hạn từ một nguồn lên nhiều nguồn thay đổi q thế nào?
4. Khi mã gắn đúng người nhận và phản hồi không tiết lộ mã của người khác, tập M cần được diễn giải lại như thế nào?

### Bài tập 2: Tìm đường vòng quota

Hệ thống giới hạn 6 request mỗi 10 phút trên /coupon-checks. Endpoint GraphQL cho phép nhiều alias, còn checkout nhận couponId trực tiếp.

Hãy thiết kế lại:

- Điểm admission và đơn vị tính quota.
- Kiểm tra quyền hoặc bằng chứng sở hữu khi nhận couponId.
- Cách nhận diện retry không cho phép đổi mã.
- Cách giới hạn tài nguyên khi kho idempotency nhận nhiều key mới.

### Bài tập 3: Chứng minh limiter đúng khi đồng thời

Tài khoản đã có 5 lookup trong cửa sổ, hai instance cùng nhận một request mới.

Mô tả cơ chế để tối đa một lookup được thêm vào ngân sách 6 lượt. Sau đó nêu trạng thái khi một instance mất kết nối với kho limiter: nó có được tự cho qua không, và hợp đồng API sẽ phản hồi thế nào?

### Bài tập 4: Phân biệt chống dò và chống dùng trùng

Một hệ thống dùng mã ngẫu nhiên mạnh và chỉ cho thử ít lần, nhưng redeem có quy trình:

~~~text
đọc coupon.used = false
tạo đơn giảm giá
đặt coupon.used = true
~~~

Hãy chỉ ra vì sao hai request vẫn có thể nhận cùng ưu đãi. Thiết kế lại trạng thái giữ, transaction và idempotency để coupon một lần không tạo hai đơn hưởng lợi.

### Bài tập 5: Đánh giá lỗi chung chưa đủ

API luôn trả message “Mã không khả dụng”, nhưng:

- Mã không tồn tại trả 404.
- Mã thuộc người khác trả 403 và có campaignId.
- Mã hết hạn trả 200 với ngày hết hạn.
- Mã đã dùng mất thời gian lâu hơn vì gọi dịch vụ order.

Lập danh sách tín hiệu đang làm lộ thông tin và đề xuất kiểm tra tương ứng. Giải thích vì sao thêm cùng một sleep vào mọi nhánh chưa chứng minh đã xử lý đầy đủ.

## 16. Những điểm cần ghi nhớ

Coupon brute force defense cần đồng thời giảm khả năng đoán trúng và giới hạn số cơ hội thử trên toàn bộ hệ thống. Đánh giá rủi ro phải tính số mã có thể tạo kết quả hữu ích, thời gian tồn tại và số phép thử gộp qua nhiều nguồn.

Mã riêng phải được sinh khó đoán, phân phối và lưu trữ an toàn, ràng buộc đúng người nhận nếu chính sách yêu cầu. Phản hồi, timing và endpoint phụ không được vô tình xác nhận các mã mà người gọi không có quyền biết.

Limiter cần đơn vị tính rõ ràng, cập nhật nguyên tử và chính sách suy giảm. Sau khi biết mã, transaction, state machine và idempotency vẫn phải bảo vệ quyền dùng, giá và ngân sách. Chỉ khi các lớp đó cùng giữ đúng bất biến, việc chống dò mới bảo vệ được lợi ích nghiệp vụ.
